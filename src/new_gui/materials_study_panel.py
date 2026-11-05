"""MAT-3: the study section of the Materials page (PySide6): input, method, parameters, observations, run and results.

A run happens in one owned worker thread that touches no widget; its outcome returns through a queued signal and is shown
only when it belongs to the current run. Cancel stops the workflow between two forward solves. Only one background job runs
at a time. Opening a saved result reads that one file, starts no calculation and opens none of the paths named in it.
"""

from __future__ import annotations

from pathlib import Path
import threading
import time
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QProgressBar,
                               QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from domain.plate_material_problem import PlateForwardRefusal
from new_gui import APP_NAME
from new_gui import materials_study_model as sm
from new_gui.diagnostic_panel import DiagnosticTable
from new_gui.shape_panel import _label
from services import analysis_project as ap
from services import materials_project as mp

PROJECT_FILTER = "Materials results (*.mcproj)"
PLOT_WIDTH = 480
NOT_RUN = "NOT RUN"
RUNNING, PREPARING = "RUNNING", "PREPARING"
CANCELLED_TEXT = "Cancelled at a safe point between solves. No result of this run is shown as current."
SNAPSHOT_TEXT = ("SAVED SNAPSHOT from {name}. Shown from that file only: nothing was calculated and no saved path was opened. "
                 "Run calculates anew from the form.")
FRESH_TEXT = "Calculated in this session."
INPUTS_CHANGED = "The form differs from the input of the result shown. Run to calculate from the form."
TITLES = {"A": "A. Input", "B": "B. Method", "C": "C. Fitting parameters", "D": "D. Observations", "E": "E. Run",
          "F": "F. Results"}
PARAMETER_KEYS = ("truth", "start", "lower", "upper")
PARAMETER_CAPTIONS = ("Known SYNTHETIC value", "Start", "Lower bound", "Upper bound")


def _card():
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
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


class _Bridge(QObject):
    done = Signal(int, str, object)
    solved = Signal(int, int)


class MaterialsStudyPanel(QWidget):
    """``workspace`` gives the files chosen on the page; they are read only for the real-data facts shown here."""

    def __init__(self, workspace):
        super().__init__()
        self.setObjectName("materialsStudy")
        self.workspace = workspace
        self.record: Optional[dict] = None  # the document of the result shown; a cancelled run leaves none
        self.snapshot_path: Optional[Path] = None
        self.project_path: Optional[Path] = None
        self.solves_done = 0
        self._token = 0
        self._active: Optional[str] = None
        self._cancel: Optional[threading.Event] = None
        self._thread: Optional[threading.Thread] = None
        self._started = 0.0
        self._tables: dict = {}
        self._bridge = _Bridge(self)
        self._bridge.done.connect(self._job_done)
        self._bridge.solved.connect(self._solved)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self._build_header())
        layout.addWidget(self._build_input())
        layout.addWidget(self._build_method())
        layout.addWidget(self._build_parameters())
        layout.addWidget(self._build_observations())
        layout.addWidget(self._build_run())
        layout.addWidget(self._build_results())
        self.method_combo.currentIndexChanged.connect(self._method_changed)
        self.source_combo.currentIndexChanged.connect(self._refresh)
        self.package_source.currentIndexChanged.connect(self._refresh)
        self.mass_basis.currentIndexChanged.connect(self._refresh)
        for field in self._all_inputs():
            (field.textChanged if isinstance(field, QLineEdit) else field.currentIndexChanged).connect(self._refresh)
        self._method_changed()

    # ---------------------------------------------------------------------------------------------- building

    def _build_header(self) -> QFrame:
        card, inner = _card()
        inner.addWidget(_label("Diagnostic model study", "sectionTitle"))
        inner.addWidget(_label("Fits a bending model through the shared inverse workflow. It runs SYNTHETIC software tests with "
                               "known values. A result is a diagnostic candidate at most, never a material property, a ply "
                               "constant or a calibration, and it is kept apart from the material status further down.", "hint"))
        grid = QGridLayout()
        grid.addWidget(_caption("Study data"), 0, 0)
        self.source_combo = _combo((("Built-in SYNTHETIC example", sm.SYNTHETIC_SOURCE),
                                    ("Real experimental file: view only", sm.REAL_SOURCE)), "materialsSource")
        grid.addWidget(self.source_combo, 0, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 5)
        inner.addLayout(grid)
        return card

    def _build_input(self) -> QFrame:
        card, inner = _card()
        inner.addWidget(_label(TITLES["A"], "sectionTitle"))
        form = sm.default_form()["geometry"]
        self.geometry_grid = QGridLayout()
        self.a_field, self.b_field = _field(form["a"], "materialsA"), _field(form["b"], "materialsB")
        self.length_unit = _combo((("mm", "mm"), ("m", "m")), "materialsLengthUnit")
        self.mass_basis = _combo((("Mass", "mass"), ("Surface mass (kg/m2)", "surface")), "materialsMassBasis")
        self.mass_field = _field(form["mass"], "materialsMass")
        self.mass_unit = _combo((("g", "g"), ("kg", "kg")), "materialsMassUnit")
        self.thickness_field = _field(form["thickness"], "materialsThickness")
        rows = (("Length a", self.a_field), ("Width b", self.b_field), ("Length unit", self.length_unit),
                ("Mass given as", self.mass_basis), ("Value", self.mass_field), ("Mass unit", self.mass_unit),
                ("Thickness (optional)", self.thickness_field))
        for index, (text, widget) in enumerate(rows):
            self.geometry_grid.addWidget(_caption(text), index // 2, 2 * (index % 2))
            self.geometry_grid.addWidget(widget, index // 2, 2 * (index % 2) + 1)
        _pairs(self.geometry_grid)
        inner.addLayout(self.geometry_grid)
        self.geometry_note = _label("", "hint")
        inner.addWidget(self.geometry_note)
        self.source_note = _label("Source of these values: declared for this SYNTHETIC test, not measured. Their uncertainty is "
                                  "NOT_AVAILABLE and is not taken as zero.", "hint")
        inner.addWidget(self.source_note)
        return card

    def _build_method(self) -> QFrame:
        card, inner = _card()
        inner.addWidget(_label(TITLES["B"], "sectionTitle"))
        self.method_combo = _combo(tuple((sm.METHOD_NAMES[key], key) for key in (sm.RITZ, sm.STAGE_A)), "materialsMethod")
        inner.addWidget(self.method_combo)
        self.method_text = _label("", "hint")
        inner.addWidget(self.method_text)
        self.scope_text = _label("", "warnings")
        inner.addWidget(self.scope_text)
        self.availability = _label("")
        self.availability.setObjectName("materialsAvailability")
        inner.addWidget(self.availability)
        self.package_row = QWidget()
        row = QHBoxLayout(self.package_row)
        row.setContentsMargins(0, 0, 0, 0)
        self.package_source = _combo((("Built-in SYNTHETIC test package", sm.BUILT_IN), ("Package chosen here", sm.SELECTED)),
                                     "materialsPackageSource")
        row.addWidget(self.package_source)
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

    def _build_parameters(self) -> QFrame:
        card, inner = _card()
        inner.addWidget(_label(TITLES["C"], "sectionTitle"))
        self.parameter_grids, self.parameter_fields = {}, {}
        for backend in (sm.RITZ, sm.STAGE_A):
            self.parameter_grids[backend], self.parameter_fields[backend] = self._parameter_grid(backend)
            inner.addWidget(self.parameter_grids[backend])
        self.parameter_note = _label("", "hint")
        inner.addWidget(self.parameter_note)
        numerics = sm.default_form()["numerics"]
        grid = QGridLayout()
        self.numeric_fields = {key: _field(numerics[key], f"materialsNumeric_{key}") for key in numerics}
        rows = (("Basis degree", "degree"), ("Solved modes", "mode_count"), ("Observed modes", "observed_modes"),
                ("HOLDOUT modes (last)", "holdout_modes"), ("Sigma per row (ln f)", "sigma"))
        for index, (text, key) in enumerate(rows):
            grid.addWidget(_caption(text), index // 2, 2 * (index % 2))
            grid.addWidget(self.numeric_fields[key], index // 2, 2 * (index % 2) + 1)
        _pairs(grid)
        inner.addLayout(grid)
        return card

    def _build_observations(self) -> QFrame:
        card, inner = _card()
        inner.addWidget(_label(TITLES["D"], "sectionTitle"))
        row = QHBoxLayout()
        self.prepare_button = QPushButton("Prepare observations")
        self.prepare_button.setObjectName("materialsPrepare")
        self.prepare_button.clicked.connect(lambda: self.prepare())
        row.addWidget(self.prepare_button)
        row.addStretch(1)
        inner.addLayout(row)
        self.observation_note = _label("Observations are made from the known values when you prepare or run the study.", "hint")
        inner.addWidget(self.observation_note)
        self.observation_box = QVBoxLayout()
        inner.addLayout(self.observation_box)
        self.real_note = _label(sm.REAL_NOTE, "warnings")
        inner.addWidget(self.real_note)
        self.real_box = QVBoxLayout()
        inner.addLayout(self.real_box)
        return card

    def _build_run(self) -> QFrame:
        card, inner = _card()
        inner.addWidget(_label(TITLES["E"], "sectionTitle"))
        budget = sm.default_form()["budget"]
        grid = QGridLayout()
        self.solves_field = _field(budget["max_solves"], "materialsMaxSolves")
        self.seconds_field = _field(budget["max_seconds"], "materialsMaxSeconds")
        self.note_field = QLineEdit()
        self.note_field.setObjectName("materialsAuthorizationNote")
        self.note_field.setPlaceholderText("recorded with the study; it enables nothing")
        self.note_field.setMinimumWidth(80)
        grid.addWidget(_caption("Solve limit"), 0, 0)
        grid.addWidget(self.solves_field, 0, 1)
        grid.addWidget(_caption("Time limit (s)"), 0, 2)
        grid.addWidget(self.seconds_field, 0, 3)
        grid.addWidget(_caption("Authorization note"), 1, 0)
        grid.addWidget(self.note_field, 1, 1, 1, 3)
        _pairs(grid)
        inner.addLayout(grid)
        self.preflight_box = QVBoxLayout()
        inner.addLayout(self.preflight_box)
        row = QHBoxLayout()
        self.run_button = QPushButton("Run")
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(lambda: self.run())
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("materialsCancel")
        self.cancel_button.clicked.connect(lambda: self.cancel())
        row.addWidget(self.run_button)
        row.addWidget(self.cancel_button)
        row.addStretch(1)
        inner.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        inner.addWidget(self.progress)
        self.run_state = _label(NOT_RUN)
        self.run_state.setObjectName("materialsRunState")
        inner.addWidget(self.run_state)
        self.blocked = _label(sm.RUN_BLOCKED, "error")
        inner.addWidget(self.blocked)
        self.message = _label("", "error")
        self.message.setVisible(False)
        inner.addWidget(self.message)
        return card

    def _build_results(self) -> QFrame:
        card, inner = _card()
        inner.addWidget(_label(TITLES["F"], "sectionTitle"))
        row = QHBoxLayout()
        self.save_button = QPushButton("Save results...")
        self.save_button.setObjectName("materialsSave")
        self.save_button.clicked.connect(lambda: self.save_results())
        self.open_button = QPushButton("Open results...")
        self.open_button.setObjectName("materialsOpen")
        self.open_button.clicked.connect(lambda: self.open_results())
        row.addWidget(self.save_button)
        row.addWidget(self.open_button)
        row.addStretch(1)
        inner.addLayout(row)
        self.badge = _label(NOT_RUN, "badge")
        inner.addWidget(self.badge)
        self.origin_note = _label("", "hint")
        inner.addWidget(self.origin_note)
        self.changed_note = _label(INPUTS_CHANGED, "warnings")
        self.changed_note.setVisible(False)
        inner.addWidget(self.changed_note)
        self.statement = _label("", "warnings")
        inner.addWidget(self.statement)
        self.results_box = QVBoxLayout()
        self.results_box.setSpacing(8)
        inner.addLayout(self.results_box)
        self.objective_view, self.error_view = QLabel(), QLabel()
        for view, name in ((self.objective_view, "materialsObjectivePlot"), (self.error_view, "materialsErrorPlot")):
            view.setObjectName(name)
            view.setVisible(False)
            view.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)  # a picture never widens the page
            inner.addWidget(view)
        self.reasons = _label("", "hint")
        inner.addWidget(self.reasons)
        return card

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
        self.method_text.setText(sm.METHOD_TEXT[backend])
        self.scope_text.setText(sm.APPLICABILITY[backend])
        self.package_row.setVisible(backend == sm.STAGE_A)
        ritz = backend == sm.RITZ
        for widget in (self.a_field, self.b_field, self.length_unit, self.mass_basis, self.mass_field, self.mass_unit,
                       self.thickness_field):
            widget.setEnabled(ritz)
        numerics = sm.default_form(backend)["numerics"]
        for key, field in self.numeric_fields.items():
            field.setText(numerics[key])
            field.setEnabled(ritz or key == "sigma")  # the Stage-A example's modes are those of its fixture
        self.parameter_note.setText(
            "Stiffness in N*m. D12 = u*D22 and u is dimensionless. Physical limits: D11, D22, D66 > 0 and D12^2 < D11*D22."
            if ritz else "Stiffness in N*m. D22 = D11 = D and D12 = r*D. The bounds must lie inside the package's stored domain.")
        self._clear_observations()
        self._refresh()

    def _availability_text(self) -> str:
        if self.backend == sm.RITZ:
            return "Available: this method needs no ODB, Abaqus or matrix file."
        if self.package_source.currentData() == sm.BUILT_IN:
            return "Available for the SYNTHETIC example: the built-in test package is generated for the run and not kept."
        if not self.package_field.text():
            return "Not available: no package is chosen. Run gives the workflow's refusal; nothing is substituted."
        return "Package chosen: the workflow judges it against this study when you run, and refuses one that does not match."

    def _refresh(self) -> None:
        running = self._active is not None
        form = self.form()
        rows, problems = sm.preflight(form)
        self._table("preflight", self.preflight_box, sm.PREFLIGHT_HEADERS, rows, 0)
        self.availability.setText(self._availability_text())
        self.geometry_note.setText(sm.geometry_text(form) if self.backend == sm.RITZ else "Not used by this method.")
        self.mass_unit.setEnabled(self.backend == sm.RITZ and self.mass_basis.currentData() == "mass")
        self.package_source.setEnabled(not running)
        self.package_button.setEnabled(not running and self.package_source.currentData() == sm.SELECTED)
        self.package_field.setEnabled(self.package_source.currentData() == sm.SELECTED)
        real = self.real_source
        self.blocked.setVisible(real)
        self.real_note.setVisible(real)
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

    def _table(self, key: str, box, headers, rows, stretch: int, text_columns=()) -> None:
        old = self._tables.pop(key, None)
        if old is not None:
            old.setParent(None)
            old.deleteLater()
        if not rows:
            return
        table = DiagnosticTable(headers, rows, stretch, text_columns=text_columns or tuple(range(len(headers))))
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
        self._table("real", self.real_box, ("Fact", "Value"), rows, 1, (0,))

    def _clear_observations(self) -> None:
        self._table("observations", self.observation_box, (), (), 0)
        self.observation_note.setText("Observations are made from the known values when you prepare or run the study.")

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
        self.run_state.setText("Preparing the observations...")
        return self._start(PREPARING, lambda: sm.prepare_rows(form))

    def _prepared(self, value, _cancelled: bool) -> None:
        self.run_state.setText(NOT_RUN if self.record is None else self.run_state.text())
        if isinstance(value, Exception):
            self._clear_observations()
            self._say(f"The observations could not be prepared: {value}", False)
            return
        rows, note = value
        self._table("observations", self.observation_box, sm.OBSERVATION_HEADERS, rows, 6)
        self.observation_note.setText(note)

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
        self.run_state.setText(f"Running: 0 of at most {limit} solves")
        return self._start(RUNNING, lambda: sm.execute_study(form, cancel, on_solve), cancel)

    def _solved(self, token: int, count: int) -> None:
        if token != self._token or self._active != RUNNING:
            return
        self.solves_done = count
        self.progress.setValue(min(count, self.progress.maximum()))
        self.run_state.setText(f"Running: {count} of at most {self.progress.maximum()} solves, "
                               f"{time.monotonic() - self._started:.1f} s")

    def cancel(self) -> bool:
        if self._active != RUNNING or self._cancel is None:
            return False
        self._cancel.set()
        self.run_state.setText("Cancelling at the next safe point...")
        return True

    def _run_done(self, value, cancelled: bool) -> None:
        if isinstance(value, Exception):
            self.run_state.setText("Not run.")
            self._say(f"The study did not start: {value}", False)
            return
        if cancelled or sm.is_cancelled(value):
            self.run_state.setText(CANCELLED_TEXT)
            self.badge.setText("CANCELLED")
            self.badge.setProperty("state", "")
            self._repolish()
            return
        self.snapshot_path = None
        self.project_path = None
        self._show_section(mp.materials_document(value, APP_NAME), FRESH_TEXT)
        self._table("observations", self.observation_box, sm.OBSERVATION_HEADERS, sm.observation_rows(value["declaration"]), 6)
        self.observation_note.setText(sm.registration_text(value["declaration"]))

    # ---------------------------------------------------------------------------------------------- showing a result

    def _repolish(self) -> None:
        self.badge.style().unpolish(self.badge)
        self.badge.style().polish(self.badge)

    def _clear_results(self) -> None:
        self.record = None
        for key in ("status", "parameters", "frequencies", "iterations", "identifiability", "holdout", "families", "convergence",
                    "uncertainty", "conditional"):
            self._table(key, self.results_box, (), (), 0)
        for view in (self.objective_view, self.error_view):
            view.clear()
            view.setVisible(False)
        for label in (self.origin_note, self.statement, self.reasons):
            label.setText("")
        self.badge.setText(NOT_RUN)
        self.badge.setProperty("state", "")
        self._repolish()

    def _show_section(self, document: dict, origin: str) -> None:
        self._clear_results()
        self.record = document
        section = document["materials"]
        result = section["result"]
        scientific = result["scientific_status"]
        self.badge.setText(f"{scientific} | {result['release_status']}")
        self.badge.setProperty("state", "blocked" if result["refusal_code"] else "chosen")  # never the green of a verified result
        self._repolish()
        self.origin_note.setText(origin)
        self.statement.setText(section["statement"])
        self.reasons.setText(sm.reason_text(section))
        self.run_state.setText(f"{result['execution_status']}: {result['numerical_status']}, {result['solves']} solves")
        box = self.results_box
        self._table("status", box, ("Status", "Value"), sm.status_rows(section), 1)
        self._table("parameters", box, sm.PARAMETER_HEADERS, sm.parameter_rows(section), 6)
        self._table("frequencies", box, sm.FREQUENCY_HEADERS, sm.frequency_rows(section), 8)
        self._table("iterations", box, sm.ITERATION_HEADERS, sm.iteration_rows(section), 5)
        self._table("identifiability", box, ("Rank and observability", "Value"), sm.identifiability_rows(section), 1)
        self._table("holdout", box, sm.HOLDOUT_HEADERS, sm.holdout_rows(section), 0)
        self._table("families", box, sm.FAMILY_HEADERS, sm.family_rows(section), 2)
        self._table("convergence", box, ("Convergence and numerical checks", "Value"), sm.convergence_rows(section), 1)
        self._table("uncertainty", box, ("Uncertainty components", "Value"), sm.uncertainty_rows(section), 1)
        self._table("conditional", box, ("Conditional effective flexural values", "Value"), sm.conditional_rows(section), 1)
        self._show_plot(self.objective_view, sm.objective_plot(section))
        self._show_plot(self.error_view, sm.error_plot(section))

    @staticmethod
    def _show_plot(view: QLabel, data: Optional[bytes]) -> None:
        if data is None:
            view.clear()
            view.setVisible(False)
            return
        pixmap = QPixmap()
        pixmap.loadFromData(data, "PNG")
        scaled = pixmap.scaledToWidth(PLOT_WIDTH)
        view.setPixmap(scaled)
        view.setFixedHeight(scaled.height())
        view.setVisible(True)

    # ---------------------------------------------------------------------------------------------- the package

    def choose_package(self, path: Optional[str] = None) -> bool:
        """Show a package's identity, ranges and readiness. No matrix is loaded here."""
        if self._active is not None:
            return False
        if path is None:
            path = QFileDialog.getExistingDirectory(self, "Choose a matrix package folder", self.package_field.text())
        if not path:
            return False
        self.package_source.setCurrentIndex(self.package_source.findData(sm.SELECTED))
        self.package_field.setText(str(path))
        self.package_field.setToolTip(str(path))
        self.package_note.setText("Reading the package's manifest...")
        self._table("package", self.package_box, (), (), 0)
        return self._start("package", lambda: sm.package_facts(path))

    def _package_read(self, value, _cancelled: bool) -> None:
        if isinstance(value, Exception):
            self.package_note.setText(f"This package cannot be used: {value}")
            return
        self.package_note.setText("Read from the package's manifest. Its matrices were not loaded.")
        self._table("package", self.package_box, ("Fact", "Value"), value, 1, (0,))

    # ---------------------------------------------------------------------------------------------- save and open

    def save_results(self, path: Optional[str] = None) -> bool:
        if self.record is None or self._active is not None:
            return False
        if path is None:
            start = str(self.project_path or self.snapshot_path or f"materials{ap.SUFFIX}")
            path, _filter = QFileDialog.getSaveFileName(self, "Save results", start, PROJECT_FILTER)
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
        self.origin_note.setText(f"Saved: {self.project_path}. No source file is in it.")

    def open_results(self, path: Optional[str] = None) -> bool:
        """Show a saved result: only that file is read, no calculation starts and no path named in it is opened."""
        if self._active is not None:
            return False
        if path is None:
            path, _filter = QFileDialog.getOpenFileName(self, "Open results", str(self.project_path or ""), PROJECT_FILTER)
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
        self._table("observations", self.observation_box, sm.OBSERVATION_HEADERS, sm.observation_rows(section["declaration"]), 6)
        self.observation_note.setText(sm.registration_text(section["declaration"]))


__all__ = ["MaterialsStudyPanel"]
