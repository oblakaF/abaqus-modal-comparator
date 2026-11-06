"""MAT-3, MAT-4.UX1: the study part of the Materials page (PySide6): four tabs, Calculation, Results, Plots and Diagnostics.

A run happens in one owned worker thread that touches no widget; its outcome returns through a queued signal and is shown
only when it belongs to the current run. Cancel stops the workflow between two forward solves. Only one background job runs
at a time. Opening a saved result reads that one file, starts no calculation and opens none of the paths named in it.

The plots are drawn on this thread from the result's numbers, at the size they are shown and at the screen's own scale, so
nothing is ever enlarged from a smaller picture. Drawing computes no result.
"""

from __future__ import annotations

from pathlib import Path
import threading
import time
from typing import Callable, Optional

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QProgressBar,
                               QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from domain.plate_material_problem import PlateForwardRefusal
from new_gui import APP_NAME
from new_gui import materials_study_model as sm
from new_gui.diagnostic_panel import DiagnosticTable
from new_gui.shape_panel import _label
from services import analysis_project as ap
from services import materials_project as mp

PROJECT_FILTER = "Materials results (*.mcproj)"
PLOT_FILTER = "PNG image (*.png)"
TAB_RUN, TAB_RESULTS, TAB_PLOTS, TAB_DIAGNOSTICS = 0, 1, 2, 3
TAB_TITLES = ("Calculation", "Results", "Plots", "Diagnostics")
NOT_RUN = "Not run yet"
RUNNING, PREPARING = "RUNNING", "PREPARING"
CANCELLED_TEXT = "Cancelled at a safe point between solves. No result of this run is shown."
SNAPSHOT_TEXT = "SAVED RESULT from {name}. Nothing was calculated, and no path named in the file was opened."
FRESH_TEXT = "Calculated in this session."
INPUTS_CHANGED = "The settings have changed: the result shown belongs to the previous settings. Run the calculation again."
NO_RESULT_TEXT = "No result yet. Run a calculation on the Calculation tab, or open a saved result."
NO_PLOT_TEXT = "Plots appear after a calculation or after a saved result is opened."
NO_POINTS_TEXT = "This result has no data to plot."
NO_DIAGNOSTICS_TEXT = "Diagnostics appear after a calculation or after a saved result is opened."
PARAMETER_KEYS = ("truth", "start", "lower", "upper")
PARAMETER_CAPTIONS = ("Known synthetic", "Start", "Lower bound", "Upper bound")
SYNTHETIC_CHOICE, REAL_CHOICE = "Built-in synthetic example", "Real file: view only"
BUILT_IN_PACKAGE, CHOSEN_PACKAGE = "Built-in synthetic package", "Package folder chosen here"
TABLE_HEIGHT = 340  # a longer table scrolls inside itself
PLOT_RATIOS = {"error": (0.62, 520, 760), "objective": (0.44, 320, 560)}  # height for a width: share, least, most
PLOT_FILES = {"error": "frequency_error.png", "objective": "objective_convergence.png"}
RESULT_TABLES = ("status", "parameters", "frequencies", "iterations", "identifiability", "holdout", "families", "convergence",
                 "uncertainty", "conditional", "summary_parameters", "summary_frequencies")


def _card():
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 12, 16, 12)
    layout.setSpacing(8)
    return frame, layout


def _caption(text: str) -> QLabel:
    """A label beside a field. It wraps, so it never widens the page; ``_pairs`` gives its column a share of the width."""
    return _label(text)


def _pairs(grid: QGridLayout) -> None:
    """Two caption and field pairs per row: the captions keep a third of the width."""
    for column, share in enumerate((1, 2, 1, 2)):
        grid.setColumnStretch(column, share)


def _field(text: str, name: str) -> QLineEdit:
    field = QLineEdit(text)
    field.setObjectName(name)
    field.setMinimumWidth(56)
    return field


def _combo(items, name: str) -> QComboBox:
    combo = QComboBox()
    combo.setObjectName(name)
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)  # never widens the page
    combo.setMinimumContentsLength(6)
    for text, value in items:
        combo.addItem(text, value)
    return combo


def scrolled(content: QWidget, always_bar: bool = False) -> QScrollArea:
    """A tab's own scrolling. ``always_bar`` keeps the width steady for content whose height follows its width."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    if always_bar:
        area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
    area.setWidget(content)
    return area


class Section(QWidget):
    """A titled part that opens and closes with its own button (Space or a click). Closed, its content stays alive."""

    def __init__(self, title: str, help_text: str = "", name: str = "", expanded: bool = False):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.toggle = QToolButton()
        self.toggle.setObjectName("sectionToggle")
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)  # a long title never widens the page
        self.toggle.setMinimumWidth(1)
        self.toggle.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        if name:
            self.toggle.setAccessibleName(name)
        if help_text:
            self.toggle.setToolTip(help_text)
        layout.addWidget(self.toggle)
        self.body = QWidget()
        self.inner = QVBoxLayout(self.body)
        self.inner.setContentsMargins(18, 0, 0, 6)
        self.inner.setSpacing(8)
        layout.addWidget(self.body)
        if help_text:
            self.inner.addWidget(_label(help_text, "hint"))
        self.toggle.toggled.connect(self._toggled)
        self.toggle.setChecked(expanded)
        self._toggled(expanded)

    def _toggled(self, opened: bool) -> None:
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if opened else Qt.ArrowType.RightArrow)
        self.body.setVisible(opened)


class _Table(DiagnosticTable):
    """As tall as its rows up to a limit, and then it scrolls inside itself. It can take the keyboard focus to scroll.

    ``fill``: no column is narrower than its header or its longest cell, so no text is cut, and the free width is shared
    equally instead of going to one column. Only when even that does not fit does the table scroll sideways inside itself."""

    height_cap = TABLE_HEIGHT
    filling = False

    def __init__(self, *args, fill: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        if fill:
            self.filling = True
            header = self.horizontalHeader()
            self.natural = [max(header.sectionSizeHint(column), self.sizeHintForColumn(column)) for column in range(self.columnCount())]
            for column in range(self.columnCount()):
                header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.fit()

    def fit(self) -> None:
        if not self.filling:
            super().fit()
            return
        header = self.horizontalHeader()
        extra = max(0, self.viewport().width() - sum(self.natural))
        for column, width in enumerate(self.natural):
            header.resizeSection(column, width + extra // len(self.natural) + (1 if column < extra % len(self.natural) else 0))
        overflow = header.length() > self.viewport().width()
        height = (header.sizeHint().height() + self.verticalHeader().length() + 2 * self.frameWidth() + 2
                  + (self.horizontalScrollBar().sizeHint().height() if overflow else 0))
        height = min(height, self.height_cap)
        if self.height() != height:
            self.setFixedHeight(height)


class PlotView(QLabel):
    """One plot, drawn from the result's numbers at the size shown and at the screen's scale. Never scaled from a smaller one."""

    def __init__(self, kind: str, draw: Callable, name: str):
        super().__init__()
        self.kind = kind
        self.draw = draw
        self.section = None
        self.data = b""  # the PNG now shown
        self.setObjectName(name)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)  # a picture never widens the page
        self.setMinimumSize(1, 1)
        self._drawn = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self.render_now)
        share, least, most = PLOT_RATIOS[kind]
        self._height = lambda width: max(least, min(most, round(width * share)))

    def set_section(self, section) -> None:
        self.section = section
        self._drawn = None
        self.data = b""
        self.clear()
        if self.isVisible():
            self.render_now()

    def scale(self) -> float:
        return self.devicePixelRatioF()

    def render_now(self) -> bool:
        """Draw for the present width and scale, unless this exact picture is already shown."""
        self._timer.stop()
        if self.section is None or not self.isVisible():
            return False
        width, ratio = max(1, self.width()), self.scale()
        height = self._height(width)
        if self.height() != height:
            self.setFixedHeight(height)
        if self._drawn == (width, height, ratio):
            return False
        data = self.draw(self.section, width, height, ratio)
        if data is None:
            return False
        pixmap = QPixmap()
        pixmap.loadFromData(data, "PNG")
        pixmap.setDevicePixelRatio(ratio)
        self.setPixmap(pixmap)
        self.data = data
        self._drawn = (width, height, ratio)
        return True

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._timer.start()  # once the resizing stops

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._timer.start(0)

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.DevicePixelRatioChange:  # moved to a screen with another scale
            self._timer.start(0)
        return super().event(event)


class _Bridge(QObject):
    done = Signal(int, str, object)
    solved = Signal(int, int)


class MaterialsStudyPanel(QStackedWidget):
    """``workspace`` gives the files chosen on the page; they are read only for the real-data facts shown here.

    The pages are this widget's four tabs; the page's tab bar belongs to ``MaterialsWorkspace``. ``real_card`` is shown on
    the fifth tab. ``tab_wanted`` asks for a tab when a result arrives.
    """

    tab_wanted = Signal(int)

    def __init__(self, workspace):
        super().__init__()
        self.setObjectName("materialsStudy")
        self.workspace = workspace
        self.record: Optional[dict] = None  # the document of the result shown; a cancelled run leaves none
        self.snapshot_path: Optional[Path] = None
        self.project_path: Optional[Path] = None
        self.solves_done = 0
        self.summary_cells: list = []
        self._token = 0
        self._active: Optional[str] = None
        self._cancel: Optional[threading.Event] = None
        self._thread: Optional[threading.Thread] = None
        self._started = 0.0
        self._tables: dict = {}
        self._bridge = _Bridge(self)
        self._bridge.done.connect(self._job_done)
        self._bridge.solved.connect(self._solved)
        self.addWidget(scrolled(self._build_run_page()))
        self.addWidget(scrolled(self._build_results_page()))
        self.addWidget(scrolled(self._build_plots_page(), always_bar=True))
        self.addWidget(scrolled(self._build_diagnostics_page()))
        self.real_card = self._build_real_card()
        self.method_combo.currentIndexChanged.connect(self._method_changed)
        self.source_combo.currentIndexChanged.connect(self._refresh)
        self.package_source.currentIndexChanged.connect(self._refresh)
        self.mass_basis.currentIndexChanged.connect(self._refresh)
        for field in self._all_inputs():
            (field.textChanged if isinstance(field, QLineEdit) else field.currentIndexChanged).connect(self._refresh)
        self._method_changed()

    # ---------------------------------------------------------------------------------------------- the Calculation tab

    def _build_run_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 8, 10)
        layout.setSpacing(10)
        layout.addWidget(self._build_choice())
        layout.addWidget(self._build_geometry())
        layout.addWidget(self._build_run())
        self.advanced = Section("Advanced settings", name="materialsAdvanced")
        self.advanced.toggle.setObjectName("sectionToggle")
        self._build_advanced(self.advanced.inner)
        card, inner = _card()
        inner.addWidget(self.advanced)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _build_choice(self) -> QFrame:
        card, inner = _card()
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        self.method_combo = _combo(tuple((sm.METHOD_NAMES[key], key) for key in (sm.RITZ, sm.STAGE_A)), "materialsMethod")
        for index, key in enumerate((sm.RITZ, sm.STAGE_A)):
            self.method_combo.setItemData(index, key, Qt.ItemDataRole.ToolTipRole)
        self.source_combo = _combo(((SYNTHETIC_CHOICE, sm.SYNTHETIC_SOURCE), (REAL_CHOICE, sm.REAL_SOURCE)), "materialsSource")
        grid.addWidget(_caption("Method"), 0, 0)
        grid.addWidget(self.method_combo, 0, 1)
        grid.addWidget(_caption("Data"), 1, 0)
        grid.addWidget(self.source_combo, 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 5)
        inner.addLayout(grid)
        self.method_text = _label("", "hint")
        inner.addWidget(self.method_text)
        return card

    def _build_geometry(self) -> QFrame:
        self.geometry_card, inner = _card()
        inner.addWidget(_label("Plate", "sectionTitle"))
        form = sm.default_form()["geometry"]
        self.geometry_grid = QGridLayout()
        self.a_field, self.b_field = _field(form["a"], "materialsA"), _field(form["b"], "materialsB")
        self.length_unit = _combo((("mm", "mm"), ("m", "m")), "materialsLengthUnit")
        self.mass_field = _field(form["mass"], "materialsMass")
        self.mass_unit = _combo((("g", "g"), ("kg", "kg")), "materialsMassUnit")
        self.mass_caption = _caption("Mass")
        rows = ((("Length a", self.a_field), ("Width b", self.b_field), ("Unit", self.length_unit)),
                ((self.mass_caption, self.mass_field), ("Unit", self.mass_unit)))
        for row, pairs in enumerate(rows):
            for index, (text, widget) in enumerate(pairs):
                self.geometry_grid.addWidget(text if isinstance(text, QLabel) else _caption(text), row, 2 * index)
                self.geometry_grid.addWidget(widget, row, 2 * index + 1)
        for column, share in enumerate((2, 3, 2, 3, 2, 3)):
            self.geometry_grid.setColumnStretch(column, share)
        inner.addLayout(self.geometry_grid)
        self.geometry_note = _label("", "hint")
        inner.addWidget(self.geometry_note)
        return self.geometry_card

    def _build_run(self) -> QFrame:
        card, inner = _card()
        row = QHBoxLayout()
        self.run_button = QPushButton("Run calculation")
        self.run_button.setObjectName("primary")
        self.run_button.setMinimumHeight(36)
        self.run_button.clicked.connect(lambda: self.run())
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("materialsCancel")
        self.cancel_button.setMinimumHeight(36)
        self.cancel_button.clicked.connect(lambda: self.cancel())
        row.addWidget(self.run_button)
        row.addWidget(self.cancel_button)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(10)
        self.progress.setVisible(False)
        row.addWidget(self.progress, 1)
        inner.addLayout(row)
        self.run_state = _label(NOT_RUN)
        self.run_state.setObjectName("materialsRunState")
        inner.addWidget(self.run_state)
        self.blocked = _label(sm.RUN_BLOCKED + ". File details are on the FE / Experiment tab.", "error")
        inner.addWidget(self.blocked)
        self.message = _label("", "error")
        self.message.setVisible(False)
        inner.addWidget(self.message)
        return card

    def _parameter_grid(self, backend: str) -> tuple:
        widget = QWidget()
        grid = QGridLayout(widget)
        grid.setContentsMargins(0, 0, 0, 0)
        for column, caption in enumerate(PARAMETER_CAPTIONS, start=1):
            grid.addWidget(_label(caption, "hint"), 0, column)
            grid.setColumnStretch(column, 1)
        fields = {}
        for row, (name, values) in enumerate(sm.default_form(backend)["parameters"].items(), start=1):
            grid.addWidget(QLabel(name), row, 0)
            fields[name] = {}
            for column, key in enumerate(PARAMETER_KEYS, start=1):
                fields[name][key] = _field(values[key], f"materialsParameter_{name}_{key}")
                grid.addWidget(fields[name][key], row, column)
        return widget, fields

    def _build_advanced(self, inner: QVBoxLayout) -> None:
        self.scope_text = _label("", "warnings")
        inner.addWidget(self.scope_text)

        self.plate_extra = QWidget()
        extra = QVBoxLayout(self.plate_extra)
        extra.setContentsMargins(0, 0, 0, 0)
        extra.setSpacing(8)
        inner.addWidget(self.plate_extra)
        extra.addWidget(_label("Plate: more", "sectionTitle"))
        form = sm.default_form()["geometry"]
        grid = QGridLayout()
        self.mass_basis = _combo((("Mass", "mass"), ("Surface mass", "surface")), "materialsMassBasis")  # the unit is in the caption
        self.thickness_field = _field(form["thickness"], "materialsThickness")
        grid.addWidget(_caption("Mass given as"), 0, 0)
        grid.addWidget(self.mass_basis, 0, 1)
        grid.addWidget(_caption("Thickness (optional)"), 0, 2)
        grid.addWidget(self.thickness_field, 0, 3)
        for column, share in enumerate((1, 2, 1, 1)):  # the choice list keeps room for its longest entry (D3)
            grid.setColumnStretch(column, share)
        extra.addLayout(grid)
        self.source_note = _label("These values are stated for the synthetic test, not measured. Their uncertainty is "
                                  "NOT_AVAILABLE and is not taken as zero.", "hint")
        extra.addWidget(self.source_note)

        self.package_title = _label("Matrix package", "sectionTitle")
        inner.addWidget(self.package_title)
        self.availability = _label("")
        self.availability.setObjectName("materialsAvailability")
        inner.addWidget(self.availability)
        self.package_row = QWidget()  # D3: the choice has the card's width, so its text is never cut; the path goes below
        rows = QGridLayout(self.package_row)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setHorizontalSpacing(10)
        self.package_source = _combo(((BUILT_IN_PACKAGE, sm.BUILT_IN), (CHOSEN_PACKAGE, sm.SELECTED)), "materialsPackageSource")
        for index, tip in enumerate(("A small diagonal SYNTHETIC test fixture, created for the run and not kept",
                                     "A matrix package folder chosen with Choose folder...")):
            self.package_source.setItemData(index, tip, Qt.ItemDataRole.ToolTipRole)
        rows.addWidget(_caption("Package"), 0, 0)
        rows.addWidget(self.package_source, 0, 1)
        rows.setColumnStretch(0, 1)
        rows.setColumnStretch(1, 5)
        row = QHBoxLayout()
        rows.addLayout(row, 1, 1)
        self.package_field = QLineEdit()
        self.package_field.setReadOnly(True)
        self.package_field.setPlaceholderText("no package chosen")
        self.package_field.setMinimumWidth(80)
        row.addWidget(self.package_field, 1)
        self.package_button = QPushButton("Choose folder...")
        self.package_button.setObjectName("materialsChoosePackage")
        self.package_button.clicked.connect(lambda: self.choose_package())
        row.addWidget(self.package_button)
        inner.addWidget(self.package_row)
        self.package_note = _label("", "hint")
        inner.addWidget(self.package_note)
        self.package_box = QVBoxLayout()
        inner.addLayout(self.package_box)

        inner.addWidget(_label("Fit parameters", "sectionTitle"))
        self.parameter_grids, self.parameter_fields = {}, {}
        for backend in (sm.RITZ, sm.STAGE_A):
            self.parameter_grids[backend], self.parameter_fields[backend] = self._parameter_grid(backend)
            inner.addWidget(self.parameter_grids[backend])
        self.parameter_note = _label("", "hint")
        inner.addWidget(self.parameter_note)

        inner.addWidget(_label("Model and observations", "sectionTitle"))
        numerics = sm.default_form()["numerics"]
        grid = QGridLayout()
        self.numeric_fields = {key: _field(numerics[key], f"materialsNumeric_{key}") for key in numerics}
        rows = (("Basis degree", "degree", ""), ("Solved modes", "mode_count", ""), ("Observed modes", "observed_modes", ""),
                ("HOLDOUT modes (last)", "holdout_modes", sm.TERM_HELP["HOLDOUT"]), ("Sigma per row (ln f)", "sigma", sm.TERM_HELP["sigma"]))
        for index, (text, key, tip) in enumerate(rows):
            caption = _caption(text)
            caption.setToolTip(tip)
            self.numeric_fields[key].setToolTip(tip)
            grid.addWidget(caption, index // 2, 2 * (index % 2))
            grid.addWidget(self.numeric_fields[key], index // 2, 2 * (index % 2) + 1)
        _pairs(grid)
        inner.addLayout(grid)
        row = QHBoxLayout()
        self.prepare_button = QPushButton("Prepare observations")
        self.prepare_button.setObjectName("materialsPrepare")
        self.prepare_button.clicked.connect(lambda: self.prepare())
        row.addWidget(self.prepare_button)
        row.addStretch(1)
        inner.addLayout(row)
        self.prepare_note = _label("Shows the frozen FIT and HOLDOUT rows on the Diagnostics tab, without a fit.", "hint")
        inner.addWidget(self.prepare_note)

        inner.addWidget(_label("Run limits", "sectionTitle"))
        budget = sm.default_form()["budget"]
        grid = QGridLayout()
        self.solves_field = _field(budget["max_solves"], "materialsMaxSolves")
        self.seconds_field = _field(budget["max_seconds"], "materialsMaxSeconds")
        self.note_field = QLineEdit()
        self.note_field.setObjectName("materialsAuthorizationNote")
        self.note_field.setPlaceholderText("recorded with the run; it authorizes nothing")
        self.note_field.setMinimumWidth(80)
        grid.addWidget(_caption("Solve limit"), 0, 0)
        grid.addWidget(self.solves_field, 0, 1)
        grid.addWidget(_caption("Time limit, s"), 0, 2)
        grid.addWidget(self.seconds_field, 0, 3)
        grid.addWidget(_caption("Authorization note"), 1, 0)
        grid.addWidget(self.note_field, 1, 1, 1, 3)
        _pairs(grid)
        inner.addLayout(grid)
        self.preflight_box = QVBoxLayout()
        inner.addLayout(self.preflight_box)

    def _build_real_card(self) -> QFrame:
        card, inner = _card()
        inner.addWidget(_label("Real files and readiness", "sectionTitle"))
        self.real_note = _label(sm.REAL_NOTE, "warnings")
        inner.addWidget(self.real_note)
        self.real_state = _label(sm.RUN_BLOCKED, "error")
        inner.addWidget(self.real_state)
        self.real_hint = _label(f"A summary appears when Data on the Calculation tab is set to \"{REAL_CHOICE}\". "
                                "No fit is started.", "hint")
        inner.addWidget(self.real_hint)
        self.real_box = QVBoxLayout()
        inner.addLayout(self.real_box)
        return card

    # ---------------------------------------------------------------------------------------------- the Results tab

    def _build_results_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 8, 10)
        layout.setSpacing(10)
        card, inner = _card()
        self.badge = _label(NOT_RUN, "badge")  # the long status codes wrap at their own row and never widen the page
        inner.addWidget(self.badge)
        row = QHBoxLayout()
        self.save_button = QPushButton("Save result")
        self.save_button.setObjectName("materialsSave")
        self.save_button.clicked.connect(lambda: self.save_results())
        self.open_button = QPushButton("Open result")
        self.open_button.setObjectName("materialsOpen")
        self.open_button.clicked.connect(lambda: self.open_results())
        row.addWidget(self.save_button)
        row.addWidget(self.open_button)
        row.addStretch(1)
        self.summary_grid = QGridLayout()
        self.summary_grid.setHorizontalSpacing(12)
        self.summary_grid.setVerticalSpacing(4)
        self.summary_grid.setColumnStretch(0, 1)
        self.summary_grid.setColumnStretch(1, 5)
        inner.addLayout(self.summary_grid)
        inner.addLayout(row)
        self.results_empty = _label(NO_RESULT_TEXT, "hint")
        inner.addWidget(self.results_empty)
        self.statement = _label("", "warnings")
        inner.addWidget(self.statement)
        self.origin_note = _label("", "hint")
        inner.addWidget(self.origin_note)
        self.changed_note = _label(INPUTS_CHANGED, "warnings")
        self.changed_note.setVisible(False)
        inner.addWidget(self.changed_note)
        self.results_message = _label("", "error")
        self.results_message.setVisible(False)
        inner.addWidget(self.results_message)
        layout.addWidget(card)
        self.parameter_card, inner = _card()
        inner.addWidget(_label("Model parameters", "sectionTitle"))
        self.summary_parameter_box = QVBoxLayout()
        inner.addLayout(self.summary_parameter_box)
        layout.addWidget(self.parameter_card)
        self.frequency_card, inner = _card()
        title = _label("Frequencies and HOLDOUT", "sectionTitle")
        title.setToolTip(sm.TERM_HELP["HOLDOUT"])
        inner.addWidget(title)
        self.holdout_line = _label("")
        self.holdout_line.setToolTip(sm.TERM_HELP["HOLDOUT"])
        inner.addWidget(self.holdout_line)
        self.summary_frequency_box = QVBoxLayout()
        inner.addLayout(self.summary_frequency_box)
        layout.addWidget(self.frequency_card)
        layout.addStretch(1)
        self.parameter_card.setVisible(False)
        self.frequency_card.setVisible(False)
        return page

    # ---------------------------------------------------------------------------------------------- the Plots tab

    def _plot_card(self, title: str, kind: str, view: PlotView) -> tuple:
        card, inner = _card()
        row = QHBoxLayout()
        row.addWidget(_label(title, "sectionTitle"), 1)
        button = QPushButton("Save plot (PNG)...")
        button.setObjectName(f"materialsSavePlot_{kind}")
        button.clicked.connect(lambda _checked=False, k=kind: self.save_plot(k))
        row.addWidget(button)
        inner.addLayout(row)
        inner.addWidget(view)
        return card, button

    def _build_plots_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 8, 10)
        layout.setSpacing(10)
        self.plots_empty = _label(NO_PLOT_TEXT, "hint")
        layout.addWidget(self.plots_empty)
        self.error_view = PlotView("error", sm.error_plot, "materialsErrorPlot")
        self.objective_view = PlotView("objective", sm.objective_plot, "materialsObjectivePlot")
        self.plot_views = {"error": self.error_view, "objective": self.objective_view}
        self.error_card, error_button = self._plot_card(sm.ERROR_TITLE, "error", self.error_view)
        self.objective_card, objective_button = self._plot_card("Objective convergence", "objective", self.objective_view)
        self.plot_buttons = {"error": error_button, "objective": objective_button}
        layout.addWidget(self.error_card)
        layout.addWidget(self.objective_card)
        self.plot_message = _label("", "error")
        self.plot_message.setVisible(False)
        layout.addWidget(self.plot_message)
        layout.addStretch(1)
        self.error_card.setVisible(False)
        self.objective_card.setVisible(False)
        return page

    # ---------------------------------------------------------------------------------------------- the Diagnostics tab

    def _build_diagnostics_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 8, 10)
        layout.setSpacing(10)
        self.diagnostics_empty = _label(NO_DIAGNOSTICS_TEXT, "hint")
        layout.addWidget(self.diagnostics_empty)
        card, inner = _card()
        inner.setSpacing(4)
        self.sections: dict = {}
        self._boxes: dict = {}

        def group(key, title, help_text, expanded=False):
            section = Section(title, help_text, f"materialsDiagnostics_{key}", expanded)
            self.sections[key] = section
            inner.addWidget(section)
            return section

        def box(section, key, caption=""):
            if caption:
                section.inner.addWidget(_label(caption, "sectionTitle"))
            holder = QVBoxLayout()
            section.inner.addLayout(holder)
            self._boxes[key] = holder

        section = group("status", "Statuses and reasons", "The exact result codes and the full refusal reasons.", True)
        box(section, "status")
        section.inner.addWidget(_label("Reasons and the workflow statement (original text, part of the recorded result)", "sectionTitle"))
        self.reasons = _label("", "hint")
        section.inner.addWidget(self.reasons)
        self.original_statement = _label("", "hint")
        section.inner.addWidget(self.original_statement)
        section = group("parameters", "Parameters and uncertainty", sm.TERM_HELP["uncertainty"])
        box(section, "parameters", "All parameters")
        box(section, "uncertainty", "Uncertainty components")
        section = group("conditional", "Conditional effective bending values",
                        "The stiffnesses converted at the stated thickness. " + sm.CONDITIONAL_NOTE + ".")
        box(section, "conditional")
        section = group("modes", "Mode identity and MAC", sm.TERM_HELP["MAC"])
        box(section, "frequencies")
        section = group("fit", "FIT and HOLDOUT", sm.TERM_HELP["HOLDOUT"])
        self.observation_note = _label("", "hint")
        section.inner.addWidget(self.observation_note)
        box(section, "observations", "Frozen rows")
        box(section, "holdout", "HOLDOUT residuals")
        section = group("convergence", "Iterations and convergence",
                        "The fit steps and numerical checks: residuals, orthonormality, sensitivities and mode order changes.")
        box(section, "iterations", "Iteration history")
        box(section, "convergence", "Convergence and numerical checks")
        section = group("rank", "Rank and observability", sm.TERM_HELP["rank"])
        box(section, "identifiability")
        section = group("families", "Leave one family out",
                        "The fit is repeated without one family of FIT modes: it shows whether the result depends on that family.")
        box(section, "families")
        layout.addWidget(card)
        layout.addStretch(1)
        self.diagnostics_card = card
        card.setVisible(False)
        return page

    def _all_inputs(self) -> tuple:
        parameters = tuple(field for fields in self.parameter_fields.values() for entry in fields.values() for field in entry.values())
        return parameters + tuple(self.numeric_fields.values()) + (
            self.a_field, self.b_field, self.mass_field, self.thickness_field, self.solves_field, self.seconds_field, self.note_field,
            self.length_unit, self.mass_unit, self.package_field)

    # ---------------------------------------------------------------------------------------------- the form

    @property
    def backend(self) -> str:
        return self.method_combo.currentData()

    @property
    def real_source(self) -> bool:
        return self.source_combo.currentData() == sm.REAL_SOURCE

    def form(self) -> dict:
        backend = self.backend
        return {"backend": backend,
                "geometry": {"a": self.a_field.text(), "b": self.b_field.text(), "length_unit": self.length_unit.currentData(),
                             "mass_basis": self.mass_basis.currentData(), "mass": self.mass_field.text(),
                             "mass_unit": self.mass_unit.currentData(), "thickness": self.thickness_field.text()},
                "parameters": {name: {key: field.text() for key, field in entry.items()}
                               for name, entry in self.parameter_fields[backend].items()},
                "numerics": {key: field.text() for key, field in self.numeric_fields.items()},
                "budget": {"max_solves": self.solves_field.text(), "max_seconds": self.seconds_field.text()},
                "package": {"source": self.package_source.currentData(), "path": self.package_field.text()},
                "authorization_note": self.note_field.text()}

    def set_form(self, form: dict) -> None:
        """Fill the fields from saved text; a value that no field offers is left as it is, and nothing is computed."""
        self.method_combo.setCurrentIndex(max(self.method_combo.findData(form["backend"]), 0))
        for key, field in (("a", self.a_field), ("b", self.b_field), ("mass", self.mass_field), ("thickness", self.thickness_field)):
            field.setText(form["geometry"][key])
        for key, combo in (("length_unit", self.length_unit), ("mass_basis", self.mass_basis), ("mass_unit", self.mass_unit)):
            combo.setCurrentIndex(max(combo.findData(form["geometry"][key]), 0))
        fields = self.parameter_fields[self.backend]
        for name, entry in form["parameters"].items():
            for key, value in entry.items():
                if name in fields:
                    fields[name][key].setText(value)
        for key, field in self.numeric_fields.items():
            field.setText(form["numerics"][key])
        self.solves_field.setText(form["budget"]["max_solves"])
        self.seconds_field.setText(form["budget"]["max_seconds"])
        self.package_source.setCurrentIndex(max(self.package_source.findData(form["package"]["source"]), 0))
        self.package_field.setText(form["package"]["path"])
        self.note_field.setText(form["authorization_note"])

    def _method_changed(self) -> None:
        backend = self.backend
        for key, grid in self.parameter_grids.items():
            grid.setVisible(key == backend)
        self.method_combo.setToolTip(backend)
        self.method_text.setText(sm.METHOD_TEXT[backend])
        self.scope_text.setText(sm.APPLICABILITY[backend])
        ritz = backend == sm.RITZ
        self.geometry_card.setVisible(ritz)  # the matrix package holds its own model: geometry and mass are not its inputs
        self.plate_extra.setVisible(ritz)
        self.package_title.setVisible(not ritz)
        self.availability.setVisible(not ritz)
        self.package_row.setVisible(not ritz)
        self.package_note.setVisible(not ritz)
        for widget in (self.a_field, self.b_field, self.length_unit, self.mass_basis, self.mass_field, self.mass_unit,
                       self.thickness_field):
            widget.setEnabled(ritz)
        numerics = sm.default_form(backend)["numerics"]
        for key, field in self.numeric_fields.items():
            field.setText(numerics[key])
            field.setEnabled(ritz or key == "sigma")  # the Stage-A example's modes are those of its fixture
        self.parameter_note.setText(
            "Stiffnesses in N·m. D12 = u*D22, and u is dimensionless. Physical limits: D11, D22, D66 > 0 and D12² < D11*D22."
            if ritz else "Stiffnesses in N·m. D22 = D11 = D and D12 = r*D. The bounds must lie inside the range stored in the package.")
        self._clear_observations()
        self._refresh()

    def _availability_text(self) -> str:
        if self.package_source.currentData() == sm.BUILT_IN:
            return "Available for the synthetic example: the built-in package is created for the run and not kept."
        if not self.package_field.text():
            return "Not available: no package is chosen. A run is refused by the workflow; nothing is substituted."
        return "Package chosen: a run checks it against this study and is refused if it does not match."

    def _refresh(self) -> None:
        running = self._active is not None
        form = self.form()
        rows, problems = sm.preflight(form)
        self._table("preflight", self.preflight_box, sm.PREFLIGHT_HEADERS, rows, 0)
        self.availability.setText(self._availability_text())
        self.geometry_note.setText(sm.geometry_text(form) if self.backend == sm.RITZ else "")
        surface = self.mass_basis.currentData() == "surface"
        self.mass_caption.setText("Surface mass, kg/m²" if surface else "Mass")
        self.mass_unit.setEnabled(self.backend == sm.RITZ and not surface)
        self.package_source.setEnabled(not running)
        self.package_button.setEnabled(not running and self.package_source.currentData() == sm.SELECTED)
        self.package_field.setEnabled(self.package_source.currentData() == sm.SELECTED)
        real = self.real_source
        self.blocked.setVisible(real)
        self.real_hint.setVisible(not real)
        self.prepare_button.setEnabled(not running and not real)
        self.run_button.setEnabled(not running and not real and not problems)
        self.cancel_button.setEnabled(self._active == RUNNING)
        self.save_button.setEnabled(not running and self.record is not None)
        self.open_button.setEnabled(not running)
        self.changed_note.setVisible(self.record is not None and form != self.record["materials"]["input"])
        self.refresh_real()
        if problems and not running:
            self._say("; ".join(problems))
        elif self.message.text() and self._message_is_form:
            self._say("")

    _message_is_form = False

    def _say(self, text: str, from_form: bool = True) -> None:
        self.message.setText(text)
        self.message.setVisible(bool(text))
        self._message_is_form = bool(text) and from_form
        shown = "" if from_form else text  # an outcome of Save or Open is also said where those commands are
        self.results_message.setText(shown)
        self.results_message.setVisible(bool(shown))

    def _table(self, key: str, box, headers, rows, stretch: int, text_columns=(), fill: bool = False) -> None:
        old = self._tables.pop(key, None)
        if old is not None:
            old.setParent(None)
            old.deleteLater()
        if not rows:
            return
        table = _Table(headers, rows, stretch, text_columns=text_columns or tuple(range(len(headers))), fill=fill)
        table.setObjectName(f"materials_{key}")
        self._tables[key] = table
        box.addWidget(table)

    def table_cells(self, key: str) -> list:
        table = self._tables[key]
        return [[table.item(row, column).text() for column in range(table.columnCount())] for row in range(table.rowCount())]

    def refresh_real(self) -> None:
        """What the page knows about the real file it holds. Reading it stays on the page's own read-only workers."""
        if not self.real_source:
            self._table("real", self.real_box, (), (), 0)
            return
        facts = self.workspace.facts.get(self.workspace.experimental_kind)
        rows = sm.real_data_rows(facts, self.workspace.registration_text(), self.note_field.text())
        self._table("real", self.real_box, ("Item", "Value"), rows, 1, (0,))

    def _clear_observations(self) -> None:
        self._table("observations", self._boxes["observations"], (), (), 0)
        self.observation_note.setText("The observations are built from the known values when you prepare or run.")

    # ---------------------------------------------------------------------------------------------- background jobs

    def _free(self) -> bool:
        """No job is current and the last worker has ended; it ends right after sending its outcome."""
        if self._active is not None:
            return False
        if self._thread is not None:
            self._thread.join(2.0)
        return self._thread is None or not self._thread.is_alive()

    def _start(self, kind: str, work: Callable, cancel: Optional[threading.Event] = None) -> bool:
        if not self._free():
            return False
        self._token += 1
        token, bridge = self._token, self._bridge
        self._active = kind
        self._cancel = cancel or threading.Event()

        def target() -> None:
            try:
                value = work()
            except sm.FormProblem as problem:
                value = problem
            except ap.ProjectRefused as refusal:
                value = refusal
            except PlateForwardRefusal as refusal:
                value = refusal
            except Exception as error:  # noqa: BLE001  (a message, never a crash of the window)
                value = RuntimeError(f"{type(error).__name__}: {error}")
            try:
                bridge.done.emit(token, kind, value)
            except RuntimeError:
                pass

        self._thread = threading.Thread(target=target, name=f"new-gui-materials-study-{kind}", daemon=True)
        self._thread.start()
        self._refresh()
        return True

    def _job_done(self, token: int, kind: str, value) -> None:
        if token != self._token:
            return  # the page moved on: this outcome is not current
        cancelled = self._cancel is not None and self._cancel.is_set()
        self._active = None
        self._cancel = None
        self.progress.setVisible(False)
        {RUNNING: self._run_done, PREPARING: self._prepared, "package": self._package_read, "open": self._opened,
         "save": self._saved}[kind](value, cancelled)
        self._refresh()

    def busy(self) -> bool:
        return self._active is not None or (self._thread is not None and self._thread.is_alive())

    def shutdown(self, timeout: float = 5.0) -> None:
        """Stop the worker at its next safe point, wait for it briefly, and drop whatever it still sends."""
        if self._cancel is not None:
            self._cancel.set()
        self._token += 1
        self._active = None
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout)

    # ---------------------------------------------------------------------------------------------- run and cancel

    def prepare(self) -> bool:
        if self.real_source or self._active is not None:
            return False
        form = self.form()
        self._say("")
        self.run_state.setText("Preparing observations...")
        return self._start(PREPARING, lambda: sm.prepare_rows(form))

    def _prepared(self, value, _cancelled: bool) -> None:
        self.run_state.setText(NOT_RUN if self.record is None else FRESH_TEXT)
        if isinstance(value, Exception):
            self._clear_observations()
            self._say(f"Observations not prepared: {value}", False)
            return
        rows, note = value
        self._table("observations", self._boxes["observations"], sm.OBSERVATION_HEADERS, rows, 6)
        self.observation_note.setText(note)
        self.prepare_note.setText("Observations prepared: see Diagnostics, FIT and HOLDOUT.")
        self.diagnostics_card.setVisible(True)
        self.diagnostics_empty.setVisible(False)

    def run(self) -> bool:
        """Start one study. Refuses a second one, a real source and a form over the limits; each says why."""
        if not self._free():
            return False
        if self.real_source:
            code, reason = sm.real_data_gate(self.note_field.text())
            self._say(f"{sm.RUN_BLOCKED}. {code}: {reason}", False)
            return False
        form = self.form()
        _rows, problems = sm.preflight(form)
        if problems:
            self._say("; ".join(problems))
            return False
        self._say("")
        self._clear_results()
        cancel = threading.Event()
        token_solves = self._token + 1
        bridge = self._bridge
        count = [0]

        def on_solve() -> None:
            count[0] += 1
            try:
                bridge.solved.emit(token_solves, count[0])
            except RuntimeError:
                pass

        self.solves_done = 0
        self._started = time.monotonic()
        limit = int(form["budget"]["max_solves"])
        self.progress.setRange(0, limit)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.run_state.setText(f"Running: 0 solves, at most {limit}")
        return self._start(RUNNING, lambda: sm.execute_study(form, cancel, on_solve), cancel)

    def _solved(self, token: int, count: int) -> None:
        if token != self._token or self._active != RUNNING:
            return
        self.solves_done = count
        self.progress.setValue(min(count, self.progress.maximum()))
        self.run_state.setText(f"Running: {count} solves, at most {self.progress.maximum()}, "
                               f"{time.monotonic() - self._started:.1f} s")

    def cancel(self) -> bool:
        if self._active != RUNNING or self._cancel is None:
            return False
        self._cancel.set()
        self.run_state.setText("Cancelling at the next safe point...")
        return True

    def _run_done(self, value, cancelled: bool) -> None:
        if isinstance(value, Exception):
            self.run_state.setText("Calculation not started.")
            self._say(f"Calculation not started: {value}", False)
            return
        if cancelled or sm.is_cancelled(value):
            self.run_state.setText(CANCELLED_TEXT)
            self.badge.setText("CANCELLED")
            self.badge.setProperty("state", "")
            self._repolish()
            self._show_summary(sm.cancelled_summary(self.backend))
            self.results_empty.setVisible(False)
            return
        self.snapshot_path = None
        self.project_path = None
        self._show_section(mp.materials_document(value, APP_NAME), FRESH_TEXT)
        self._table("observations", self._boxes["observations"], sm.OBSERVATION_HEADERS, sm.observation_rows(value["declaration"]), 6)
        self.observation_note.setText(sm.registration_text(value["declaration"]))
        self.tab_wanted.emit(TAB_RESULTS)

    # ---------------------------------------------------------------------------------------------- showing a result

    def _repolish(self) -> None:
        self.badge.style().unpolish(self.badge)
        self.badge.style().polish(self.badge)

    def _show_summary(self, rows) -> None:
        while self.summary_grid.count():
            widget = self.summary_grid.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.summary_cells = [list(row) for row in rows]
        for index, (caption, text) in enumerate(rows):
            self.summary_grid.addWidget(_label(caption, "summaryCaption"), index, 0)
            self.summary_grid.addWidget(_label(text, "summaryValue"), index, 1)

    def _clear_results(self) -> None:
        self.record = None
        for key in RESULT_TABLES:
            self._table(key, None, (), (), 0)
        self._show_summary(())
        for label in (self.origin_note, self.statement, self.reasons, self.holdout_line, self.original_statement):
            label.setText("")
        self.badge.setText(NOT_RUN)
        self.badge.setProperty("state", "")
        self._repolish()
        for view in self.plot_views.values():
            view.set_section(None)
        for widget in (self.parameter_card, self.frequency_card, self.error_card, self.objective_card, self.diagnostics_card):
            widget.setVisible(False)
        self.results_empty.setVisible(True)
        self.plots_empty.setText(NO_PLOT_TEXT)
        self.plots_empty.setVisible(True)
        self.diagnostics_empty.setVisible(True)
        self.plot_message.setVisible(False)

    def _show_section(self, document: dict, origin: str) -> None:
        self._clear_results()
        self.record = document
        section = document["materials"]
        result = section["result"]
        scientific = result["scientific_status"]
        self.badge.setText(f"{scientific} | {result['release_status']}")
        self.badge.setProperty("state", "blocked" if result["refusal_code"] else "chosen")  # never the green of a verified result
        self._repolish()
        self.results_empty.setVisible(False)
        self.diagnostics_empty.setVisible(False)
        self.diagnostics_card.setVisible(True)
        self._show_summary(sm.result_summary(section))
        self.origin_note.setText(origin)
        self.statement.setText(sm.RESULT_STATEMENT)
        self.original_statement.setText(section["statement"])
        self.reasons.setText(sm.reason_text(section))
        self.run_state.setText(f"{result['execution_status']}: {result['numerical_status']}, {result['solves']} solves")
        boxes = self._boxes
        self._table("summary_parameters", self.summary_parameter_box, sm.SUMMARY_PARAMETER_HEADERS, sm.summary_parameter_rows(section), 0)
        self.parameter_card.setVisible(True)
        frequencies = sm.summary_frequency_rows(section)
        self._table("summary_frequencies", self.summary_frequency_box, sm.SUMMARY_FREQUENCY_HEADERS, frequencies, 1, fill=True)
        self.holdout_line.setText(sm.holdout_summary(section))
        self.frequency_card.setVisible(bool(frequencies))
        self._table("status", boxes["status"], ("Status", "Value"), sm.status_rows(section), 1)
        self._table("parameters", boxes["parameters"], sm.PARAMETER_HEADERS, sm.parameter_rows(section), 6)
        self._table("frequencies", boxes["frequencies"], sm.FREQUENCY_HEADERS, sm.frequency_rows(section), 8)
        self._table("iterations", boxes["iterations"], sm.ITERATION_HEADERS, sm.iteration_rows(section), 5)
        self._table("identifiability", boxes["identifiability"], ("Rank and observability", "Value"), sm.identifiability_rows(section), 1)
        self._table("holdout", boxes["holdout"], sm.HOLDOUT_HEADERS, sm.holdout_rows(section), 0)
        self._table("families", boxes["families"], sm.FAMILY_HEADERS, sm.family_rows(section), 2)
        self._table("convergence", boxes["convergence"], ("Convergence and numerical checks", "Value"), sm.convergence_rows(section), 1)
        self._table("uncertainty", boxes["uncertainty"], ("Uncertainty components", "Value"), sm.uncertainty_rows(section), 1)
        self._table("conditional", boxes["conditional"], ("Conditional effective bending values", "Value"), sm.conditional_rows(section), 1)
        self.sections["conditional"].setVisible(bool(sm.conditional_rows(section)))
        self.error_card.setVisible(bool(sm.error_rows(section)))
        self.objective_card.setVisible(bool(sm.objective_points(section)))
        self.error_view.set_section(section)
        self.objective_view.set_section(section)
        drawn = self.error_card.isVisibleTo(self.error_card.parentWidget()) or self.objective_card.isVisibleTo(self.objective_card.parentWidget())
        self.plots_empty.setText(NO_POINTS_TEXT)
        self.plots_empty.setVisible(not drawn)

    # ---------------------------------------------------------------------------------------------- saving a plot

    def save_plot(self, kind: str, path: Optional[str] = None) -> bool:
        """Save a plot drawn anew from the numbers at a fixed high resolution, whatever the size of the window."""
        section = self.plot_views[kind].section
        if section is None:
            return False
        if path is None:
            path, _filter = QFileDialog.getSaveFileName(self, "Save plot", PLOT_FILES[kind], PLOT_FILTER)
        if not path:
            return False
        target = Path(path)
        target = target if target.suffix else target.with_name(target.name + ".png")
        data = (sm.error_plot if kind == "error" else sm.objective_plot)(section, *sm.EXPORT_SIZE)
        try:
            target.write_bytes(data)
        except OSError as error:
            self.plot_message.setText(f"Plot not saved: {error}")
            self.plot_message.setVisible(True)
            return False
        self.plot_message.setVisible(False)
        return True

    # ---------------------------------------------------------------------------------------------- the package

    def choose_package(self, path: Optional[str] = None) -> bool:
        """Show a package's identity, ranges and readiness. No matrix is loaded here."""
        if self._active is not None:
            return False
        if path is None:
            path = QFileDialog.getExistingDirectory(self, "Choose the matrix package folder", self.package_field.text())
        if not path:
            return False
        self.package_source.setCurrentIndex(self.package_source.findData(sm.SELECTED))
        self.package_field.setText(str(path))
        self.package_field.setToolTip(str(path))
        self.package_note.setText("Reading the package manifest...")
        self._table("package", self.package_box, (), (), 0)
        return self._start("package", lambda: sm.package_facts(path))

    def _package_read(self, value, _cancelled: bool) -> None:
        if isinstance(value, Exception):
            self.package_note.setText(f"This package cannot be used: {value}")
            return
        self.package_note.setText("Read from the package manifest. No matrix was loaded.")
        self._table("package", self.package_box, ("Item", "Value"), value, 1, (0,))

    # ---------------------------------------------------------------------------------------------- save and open

    def save_results(self, path: Optional[str] = None) -> bool:
        if self.record is None or self._active is not None:
            return False
        if path is None:
            start = str(self.project_path or self.snapshot_path or f"materials{ap.SUFFIX}")
            path, _filter = QFileDialog.getSaveFileName(self, "Save result", start, PROJECT_FILTER)
        if not path:
            return False
        section = self.record["materials"]
        saved_at = self.record["saved_at"] if self.snapshot_path is not None else ""
        document = mp.materials_document(section, APP_NAME, saved_at)
        self._say("")
        return self._start("save", lambda: mp.write_materials_project(document, path))

    def _saved(self, value, _cancelled: bool) -> None:
        if isinstance(value, Exception):
            self._say(f"Not saved: {value}", False)
            return
        self.project_path = Path(value)
        self.origin_note.setText(f"Saved: {self.project_path}. It holds no source file.")

    def open_results(self, path: Optional[str] = None) -> bool:
        """Show a saved result: only that file is read, no calculation starts and no path named in it is opened."""
        if self._active is not None:
            return False
        if path is None:
            path, _filter = QFileDialog.getOpenFileName(self, "Open result", str(self.project_path or ""), PROJECT_FILTER)
        if not path:
            return False
        self._say("")
        return self._start("open", lambda: (Path(path), mp.read_materials_project(path)))

    def _opened(self, value, _cancelled: bool) -> None:
        if isinstance(value, Exception):
            self._say(f"Not opened: {value}", False)
            return
        path, document = value
        self.source_combo.setCurrentIndex(self.source_combo.findData(sm.SYNTHETIC_SOURCE))
        self.set_form(document["materials"]["input"])
        self.snapshot_path = self.project_path = path
        self._show_section(document, SNAPSHOT_TEXT.format(name=path.name))
        section = document["materials"]
        self._table("observations", self._boxes["observations"], sm.OBSERVATION_HEADERS, sm.observation_rows(section["declaration"]), 6)
        self.observation_note.setText(sm.registration_text(section["declaration"]))
        self.tab_wanted.emit(TAB_RESULTS)


__all__ = ["MaterialsStudyPanel", "PlotView", "Section", "TAB_DIAGNOSTICS", "TAB_PLOTS", "TAB_RESULTS", "TAB_RUN", "TAB_TITLES", "scrolled"]
