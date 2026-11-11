"""REAL-FIT.R1: the Research Tuning page (PySide6). Research-only frequency tuning of the assumed Abaqus CFRP inputs.

Reading and fitting run in one owned worker thread that touches no widget; outcomes return through a queued signal and are
shown only when they belong to the current job. Nothing here starts Abaqus or changes a file it reads.
"""

from __future__ import annotations

import json
from pathlib import Path
import threading
from typing import Callable, Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from new_gui import analyze_model as am
from new_gui import research_tuning_model as rm
from new_gui.diagnostic_panel import DiagnosticTable
from new_gui.shape_panel import _label
from services import registered_ritz_estimation as rre
from services import research_frequency_stability as rfs
from services import research_frequency_tuning as rft
from services import solid_forward_runner as sfr

QUIET_JOBS = (None, "check", "solid_check")  # jobs that never hold the file choice

INTRO = ("The current exploratory workflow for real data: it refines the ASSUMED CFRP inputs (E1, E2, G12) of a supported "
         "shell FE model so that its Kirchhoff-Ritz plate surrogate matches fitted PolyMAX frequencies. Research only: no "
         "Abaqus run, no material property, no mode pairs.")
FILE_ROLES = ("INP: the FE model; its material, density, shell thickness and size are read, and the model check says why "
              "another kind of model cannot be used. UNV / UFF: the measured, curve-fitted PolyMAX frequencies (FRF peak "
              "records are never used). ODB, optional: its already extracted mode shapes tell rigid-body from elastic FE "
              "modes. The Kirchhoff-Ritz surrogate is a thin homogeneous plate: it does not automatically apply to a solid "
              "or sandwich FE model.")
FORMS_TEXT = ("E1=E2, G12: one in-plane modulus for both directions and the shear modulus (two unknowns). E1, E2, G12: "
              "separate moduli (three unknowns); then E1 and E2 exchanged may fit the frequencies equally well.")
KINDS_TEXT = ("Measured: the PolyMAX frequencies. Fixed: the INP's thickness, density, nu12 and other constants, assumed "
              "as written. Fitted: the exploratory E and G values, research estimates only.")
MIRROR_TEXT = ("Why two alternatives: exchanging E1 and E2 gives the same frequencies here, so frequency agreement alone "
               "cannot tell which plate axis is stiff. Neither is chosen; deciding needs independent evidence of the fibre "
               "axes, such as a registered shape comparison or the layup record.")
ROLES = (rft.FIT, rft.HOLDOUT, rft.EXCLUDED)
RECORD_HEADERS = ("EXP record", "Frequency (Hz)", "Role", "Surrogate rank (hypothesis)")


ROLE_STYLE = ("QPushButton { padding: 3px 12px; border: 1px solid #cbd2d9; border-radius: 0px; background: #ffffff; "
              "color: #52606d; min-height: 22px; }"
              "QPushButton:checked { background: #1f2933; border-color: #1f2933; color: #ffffff; font-weight: 600; }"
              "QPushButton:disabled { color: #9aa5b1; }"
              "QPushButton:checked:disabled { background: #7b8794; border-color: #7b8794; color: #ffffff; }")


class _RoleChooser(QWidget):
    """The role of one record: FIT | HOLDOUT | EXCLUDED as three exclusive buttons (ABM-AUD-1). All three states are in
    view, a change takes one deliberate press (a role change clears the shown result; a drop-down under a scrolled page
    also changes with the mouse wheel), and every button is a named control that assistive technology can read and press.
    It answers ``currentData``, ``currentIndex``, ``setCurrentIndex`` and ``currentIndexChanged`` like the drop-down it
    replaces."""

    currentIndexChanged = Signal(int)

    def __init__(self, record: int):
        super().__init__()
        self.setObjectName(f"tuningRole_{record}")
        self.setStyleSheet(ROLE_STYLE)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.buttons = []
        for index, role in enumerate(ROLES):
            button = QPushButton(role)
            button.setCheckable(True)
            button.setObjectName(f"tuningRole_{record}_{role}")
            button.setAccessibleName(f"Record {record}: {role}")
            button.setToolTip({rft.FIT: "Fitted.", rft.HOLDOUT: "Predicted only, not fitted.",
                               rft.EXCLUDED: "Not used; its rank stays unmatched."}[role])
            self._group.addButton(button, index)
            row.addWidget(button)
            self.buttons.append(button)
        row.addStretch(1)
        self.buttons[0].setChecked(True)
        self._group.idToggled.connect(lambda index, on: self.currentIndexChanged.emit(index) if on else None)

    def currentIndex(self) -> int:
        return self._group.checkedId()

    def currentData(self) -> str:
        return ROLES[self._group.checkedId()]

    def setCurrentIndex(self, index: int) -> None:
        self.buttons[index].setChecked(True)


class _Choice(QWidget):
    """ABM-AUD-5: one statement chosen among a few, as exclusive named buttons. Nothing is chosen until the user chooses
    (unless ``checked`` names a neutral option), so no option can pass for a statement the user did not make."""

    changed = Signal()

    def __init__(self, name: str, options, caption: str, checked=None):
        super().__init__()
        self.setObjectName(name)
        self.setStyleSheet(ROLE_STYLE)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._keys, self.buttons = [key for key, _text in options], []
        for index, (key, text) in enumerate(options):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setObjectName(f"{name}_{index}")
            button.setAccessibleName(f"{caption}: {text}")
            self._group.addButton(button, index)
            row.addWidget(button)
            self.buttons.append(button)
        row.addStretch(1)
        if checked is not None:
            self.buttons[self._keys.index(checked)].setChecked(True)
        self._group.idToggled.connect(lambda _index, on: self.changed.emit() if on else None)

    def value(self) -> str:
        index = self._group.checkedId()
        return self._keys[index] if index >= 0 else ""

    def set_value(self, key: str) -> None:
        self.buttons[self._keys.index(key)].setChecked(True)


def _card():
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 12, 16, 12)
    layout.setSpacing(8)
    return frame, layout


class _Bridge(QObject):
    done = Signal(int, str, object)
    solved = Signal(int, int)
    solid_event = Signal(int, object)


class ResearchTuningPanel(QWidget):
    """``ask_path(kind, start)``, ``ask_save(start)`` and ``ask_confirm(title, text)`` are replaced in tests.
    ``registered_source()`` (ABM-AUD-5) gives the validated source of the comparison shown on Analyze, or raises
    ``analyze_model.StepFailed`` with the reason there is none."""

    def __init__(self, ask_path: Optional[Callable[[str, str], str]] = None, ask_save: Optional[Callable[[str], str]] = None,
                 ask_confirm: Optional[Callable[[str, str], bool]] = None,
                 registered_source: Optional[Callable[[], dict]] = None):
        super().__init__()
        self._registered_source = registered_source
        self.registered: Optional[rre.RegisteredSet] = None  # ABM-AUD-5: the registered set in use
        self.registered_data: Optional[dict] = None  # what Analyze gave for it (its inputs are checked before a fit)
        self.review: Optional[dict] = None  # the shape review of the entered plate, when it is current
        self.review_table: Optional[dict] = None
        self.block: Optional[dict] = None  # the registered-estimation part of the shown result
        self._review_plate = self._run_plate = self._run_review = None
        self._fixed_signature = None
        self.setObjectName("researchTuning")
        self._ask_path = ask_path or self._dialog_path
        self._ask_save = ask_save or self._dialog_save
        self._ask_confirm = ask_confirm or self._dialog_confirm
        self._ask_save_summary = self._dialog_save_summary  # ABM-AUD-6; replaced in tests
        self.uncertainty: Optional[dict] = None  # the input assessment of the shown registered result, when it was made
        self.reg_ranges: dict = {}
        self.solid: Optional[rm.SolidSummary] = None  # ABM-SOLID-5: the checked solid model
        self.solid_outcome: Optional[sfr.RunnerOutcome] = None
        self.whatif_outcome: Optional[sfr.RunnerOutcome] = None  # ABM-SOLID-6
        self.solid_limits = sfr.RunnerLimits()
        self.paths = {"inp": "", "unv": "", "odb": ""}
        self.sources: Optional[rm.Sources] = None
        self.result: Optional[rft.TuningResult] = None
        self.request: Optional[rft.TuningRequest] = None
        self.stability: Optional[dict] = None  # REAL-FIT.R2: the stability check of the shown result, when it was run
        self.plot_data = b""
        self.saved_path: Optional[str] = None  # set while a saved (exported) result is shown
        self._token = 0
        self._active: Optional[str] = None
        self._cancel: Optional[threading.Event] = None
        self._thread: Optional[threading.Thread] = None
        self._tables: dict = {}
        self._bridge = _Bridge(self)
        self._bridge.done.connect(self._done)
        self._bridge.solved.connect(self._solved)
        self._bridge.solid_event.connect(self._solid_event)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.banner = _label(rm.LABEL, "badge")
        self.banner.setProperty("state", "chosen")
        layout.addWidget(self.banner)
        layout.addWidget(_label(INTRO, "hint"))
        layout.addWidget(self._build_files())
        layout.addWidget(self._build_registered())
        layout.addWidget(self._build_solid())
        layout.addWidget(self._build_setup())
        layout.addWidget(self._build_results())
        layout.addStretch(1)
        self._refresh()

    # ---------------------------------------------------------------------------------------------- building

    def _build_files(self) -> QFrame:
        card, inner = _card()
        inner.addWidget(_label("1. Model and measurement", "sectionTitle"))
        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        self.fields, self.buttons = {}, {}
        for row, (key, caption) in enumerate((("inp", "Abaqus model input (.inp)"), ("unv", "PolyMAX modal set (.unv / .uff)"),
                                              ("odb", "Abaqus results (.odb), optional: shape-based FE classification"))):
            grid.addWidget(_label(caption), 2 * row, 0, 1, 2)
            field = QLineEdit()
            field.setReadOnly(True)
            field.setPlaceholderText("not chosen")
            field.setMinimumWidth(80)
            grid.addWidget(field, 2 * row + 1, 0, 1, 2)
            button = QPushButton("Choose file...")
            button.setObjectName(f"tuningChoose_{key}")
            button.clicked.connect(lambda _c=False, k=key: self.choose_file(k))
            grid.addWidget(button, 2 * row + 1, 2)
            self.fields[key], self.buttons[key] = field, button
        inner.addLayout(grid)
        self.roles_note = _label(FILE_ROLES, "hint")
        inner.addWidget(self.roles_note)
        self.read_note = _label("The .dat beside the INP is listed unclassified. Rigid-body and elastic FE modes are told apart "
                                "only by shape, from modes already extracted from the chosen ODB; Abaqus is never started.",
                                "hint")
        inner.addWidget(self.read_note)
        self.compat_title = _label("Model check", "sectionTitle")
        self.compat_verdict = _label("", "hint")
        self.compat_box = QVBoxLayout()
        self.compat_notes = _label("", "hint")
        inner.addWidget(self.compat_title)
        inner.addWidget(self.compat_verdict)
        inner.addLayout(self.compat_box)
        inner.addWidget(self.compat_notes)
        self._clear_compatibility()
        self.inputs_box = QVBoxLayout()
        inner.addLayout(self.inputs_box)
        row = QHBoxLayout()
        self.open_button = QPushButton("Open result...")
        self.open_button.setObjectName("tuningOpenResult")
        self.open_button.clicked.connect(lambda: self.open_result())
        row.addWidget(self.open_button)
        row.addStretch(1)
        inner.addLayout(row)
        return card

    def _build_solid(self) -> QFrame:
        """ABM-SOLID-5: the separate solid mode, shown only for an INP the solid importer reads."""
        self.solid_card, inner = _card()
        self.solid_card.setObjectName("card")
        inner.addWidget(_label(rm.SOLID_TITLE, "sectionTitle"))
        self.solid_badge = _label(sfr.RESULT_LABEL, "badge")
        self.solid_badge.setProperty("state", "blocked")
        inner.addWidget(self.solid_badge)
        inner.addWidget(_label(rm.SOLID_INTRO, "hint"))
        inner.addWidget(_label(rm.SOLID_LIMITS, "hint"))
        self.solid_boxes = {}
        for key, title in (("solid_identity", "Model identity"), ("solid_material", "Material (from the INP, unchanged)"),
                           ("solid_reference", "Abaqus reference beside the INP (FE, not experiment)")):
            inner.addWidget(_label(title, "sectionTitle"))
            box = QVBoxLayout()
            inner.addLayout(box)
            self.solid_boxes[key] = box
        self.solid_resources = _label("", "hint")
        inner.addWidget(self.solid_resources)
        row = QHBoxLayout()
        self.solid_run_button = QPushButton("Calculate frequencies (one FE solve)...")
        self.solid_run_button.setObjectName("primary")
        self.solid_run_button.setMinimumHeight(36)
        self.solid_run_button.clicked.connect(lambda: self.run_solid())
        self.solid_cancel_button = QPushButton("Stop calculation")
        self.solid_cancel_button.setMinimumHeight(36)
        self.solid_cancel_button.clicked.connect(lambda: self.cancel_solid())
        row.addWidget(self.solid_run_button)
        row.addWidget(self.solid_cancel_button)
        self.solid_progress = QProgressBar()
        self.solid_progress.setRange(0, 0)
        self.solid_progress.setTextVisible(False)
        self.solid_progress.setFixedHeight(10)
        self.solid_progress.setVisible(False)
        row.addWidget(self.solid_progress, 1)
        inner.addLayout(row)
        self.solid_state = _label("")
        inner.addWidget(self.solid_state)
        self.solid_status = _label("", "badge")
        self.solid_status.setVisible(False)
        inner.addWidget(self.solid_status)
        self.solid_fe_note = _label(rm.SOLID_FE_FE_NOTE, "hint")
        self.solid_fe_note.setVisible(False)
        inner.addWidget(self.solid_fe_note)
        for key, title in (("solid_frequencies", "Elastic frequencies"), ("solid_diagnostics", "Supervision and numerical diagnostics")):
            caption = _label(title, "sectionTitle")
            caption.setVisible(False)
            inner.addWidget(caption)
            box = QVBoxLayout()
            inner.addLayout(box)
            self.solid_boxes[key] = box
            self.solid_boxes[key + "_caption"] = caption
        self._build_whatif(inner)
        self.solid_card.setVisible(False)
        return self.solid_card

    def _build_whatif(self, inner) -> None:
        """ABM-SOLID-6: up to three owner-entered E1/E2/G12 points, solved once each after one confirmation."""
        inner.addWidget(_label(rm.WHATIF_TITLE, "sectionTitle"))
        self.whatif_badge = _label(sfr.WHATIF_LABEL, "badge")
        self.whatif_badge.setProperty("state", "blocked")
        inner.addWidget(self.whatif_badge)
        inner.addWidget(_label(rm.WHATIF_INTRO, "hint"))
        grid = QGridLayout()
        for column, name in enumerate(rm.WHATIF_FIELDS, 1):
            grid.addWidget(_label(f"{name} (MPa)"), 0, column)
            grid.setColumnStretch(column, 1)
        self.whatif_fields = []
        for row in range(sfr.MAX_WHATIF_POINTS):
            grid.addWidget(_label(f"Point {row + 1}"), row + 1, 0)
            cells = []
            for column, name in enumerate(rm.WHATIF_FIELDS, 1):
                field = QLineEdit()
                field.setObjectName(f"whatif_{row + 1}_{name}")
                field.setMinimumWidth(60)
                field.textChanged.connect(lambda _t: self._whatif_changed())
                grid.addWidget(field, row + 1, column)
                cells.append(field)
            self.whatif_fields.append(cells)
        inner.addLayout(grid)
        self.whatif_check = _label("", "hint")
        inner.addWidget(self.whatif_check)
        self.whatif_parameters_box = QVBoxLayout()
        inner.addLayout(self.whatif_parameters_box)
        row = QHBoxLayout()
        self.whatif_button = QPushButton("Calculate What-If points...")
        self.whatif_button.setMinimumHeight(36)
        self.whatif_button.clicked.connect(lambda: self.run_whatif())
        row.addWidget(self.whatif_button)
        row.addStretch(1)
        inner.addLayout(row)
        self.whatif_status = _label("", "badge")
        self.whatif_status.setVisible(False)
        inner.addWidget(self.whatif_status)
        self.whatif_note = _label(rm.WHATIF_NOTE, "hint")
        self.whatif_note.setVisible(False)
        inner.addWidget(self.whatif_note)
        for key, title in (("whatif_frequencies", "What-If frequencies by ascending order"),
                           ("whatif_diagnostics", "What-If supervision and numerical diagnostics, per point")):
            caption = _label(title, "sectionTitle")
            caption.setVisible(False)
            inner.addWidget(caption)
            box = QVBoxLayout()
            inner.addLayout(box)
            self.solid_boxes[key] = box
            self.solid_boxes[key + "_caption"] = caption
        self.whatif_points: tuple = ()
        self.whatif_problems: dict = {}
        self._whatif_result_points: tuple = ()  # the points of the displayed What-If result (ABM-SOLID-6-F1)

    def _build_setup(self) -> QFrame:
        card, inner = _card()
        inner.addWidget(_label("2. Frequencies and settings", "sectionTitle"))
        inner.addWidget(_label("Roles: FIT frequencies are fitted; HOLDOUT ones are predicted only; EXCLUDED ones are not used. "
                               "Frequencies are compared with the surrogate by rank (a frequency hypothesis, not mode identity).",
                               "hint"))
        self.records_box = QVBoxLayout()
        inner.addLayout(self.records_box)
        self.correspondence_hint = _label(rm.CORRESPONDENCE_HINT, "hint")
        inner.addWidget(self.correspondence_hint)
        self.correspondence_note = _label("", "error")  # ABM-AUD-1: why the correspondence shown above cannot be fitted
        self.correspondence_note.setVisible(False)
        inner.addWidget(self.correspondence_note)
        grid = QGridLayout()
        for column, share in enumerate((1, 2, 1, 2)):
            grid.setColumnStretch(column, share)
        self.parameterization = QComboBox()
        self.parameterization.setObjectName("tuningParameterization")
        for text in (rft.TIED, rft.FREE):
            self.parameterization.addItem(text, text)
        self.parameterization.setToolTip(FORMS_TEXT)
        self.declared = QLineEdit()
        self.declared.setObjectName("tuningDeclared")
        self.declared.setPlaceholderText("optional, e.g. 3:4, 4:3 (record:rank)")
        self.search = QLineEdit("10")
        self.search.setObjectName("tuningSearch")
        self.search.setToolTip("Bounds: the data-scaled start divided and multiplied by this factor. The INP values do not "
                               "set the start or the bounds.")
        self.degree = QLineEdit("14")
        self.parameterization.currentIndexChanged.connect(lambda _i: self._settings_changed())
        for field in (self.declared, self.search, self.degree):
            field.textChanged.connect(lambda _t: self._settings_changed())
        for row, (caption, widget) in enumerate((("Fitted inputs", self.parameterization), ("Declared ranks", self.declared),
                                                 ("Search range (× data-scaled start)", self.search),
                                                 ("Ritz basis degree", self.degree))):
            grid.addWidget(_label(caption), row // 2, 2 * (row % 2))
            grid.addWidget(widget, row // 2, 2 * (row % 2) + 1)
        inner.addLayout(grid)
        inner.addWidget(_label(FORMS_TEXT, "hint"))
        inner.addWidget(_label("Held fixed at the INP values (assumed, not identified): thickness, density, nu12, E3, nu13, "
                               "nu23, G13, G23. The start comes from the measured frequencies alone.", "hint"))
        row = QHBoxLayout()
        self.run_button = QPushButton("Run tuning")
        self.run_button.setObjectName("primary")
        self.run_button.setMinimumHeight(36)
        self.run_button.clicked.connect(lambda: self.run())
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setMinimumHeight(36)
        self.cancel_button.clicked.connect(lambda: self.cancel())
        row.addWidget(self.run_button)
        row.addWidget(self.cancel_button)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(10)
        self.progress.setVisible(False)
        row.addWidget(self.progress, 1)
        inner.addLayout(row)
        self.state = _label("Choose the two files.")
        inner.addWidget(self.state)
        self.message = _label("", "error")
        self.message.setVisible(False)
        inner.addWidget(self.message)
        return card

    def _build_results(self) -> QFrame:
        self.results_card, inner = _card()
        inner.addWidget(_label("3. Result", "sectionTitle"))
        self.saved_note = _label("", "warnings")
        self.saved_note.setVisible(False)
        inner.addWidget(self.saved_note)
        # ABM-AUD-1: three separate statements, each on its own line: the optimizer, the spectral fit, physical validity
        self.status = _label("", "badge")
        inner.addWidget(self.status)
        self.quality = _label("", "badge")
        inner.addWidget(self.quality)
        self.validity = _label("", "badge")
        self.validity.setProperty("state", "blocked")
        inner.addWidget(self.validity)
        self.reasons = _label("", "warnings")
        inner.addWidget(self.reasons)
        self.mirror_note = _label(MIRROR_TEXT, "hint")
        self.mirror_note.setVisible(False)
        inner.addWidget(self.mirror_note)
        self.registered_results = self._build_registered_results()  # ABM-AUD-5: shown for a registered result only
        inner.addWidget(self.registered_results)
        self.inp_notes = [_label(rm.SURROGATE_NOTE, "hint"), _label(KINDS_TEXT, "hint")]  # they speak of the INP route
        for note in self.inp_notes:
            inner.addWidget(note)
        self.accuracy = _label("", "warnings")
        inner.addWidget(self.accuracy)
        self.estimate_box, self.axis_box = QVBoxLayout(), QVBoxLayout()
        self.estimate_title = _label("Numerical research estimates", "sectionTitle")
        inner.addWidget(self.estimate_title)
        self.estimate_note = _label(rm.DIAGNOSTIC_ESTIMATE_NOTE, "warnings")
        self.estimate_note.setVisible(False)
        inner.addWidget(self.estimate_note)
        inner.addLayout(self.estimate_box)
        inner.addLayout(self.axis_box)
        self.candidate_title = _label(rm.CANDIDATE_TITLE, "sectionTitle")
        inner.addWidget(self.candidate_title)
        self.candidate_none = _label("", "hint")
        inner.addWidget(self.candidate_none)
        self.candidate_box = QVBoxLayout()
        inner.addLayout(self.candidate_box)
        self.plot = QLabel()
        self.plot.setObjectName("tuningPlot")
        self.plot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plot.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.plot.setMinimumSize(1, 1)
        inner.addWidget(self.plot)
        self.result_boxes = {}
        for key, title in (("fit_quality", "Spectral fit quality (separate from the optimizer status)"),
                           ("correspondence", "Frequency correspondence that was fitted (a hypothesis, not mode identity)"),
                           ("quantities", "What is measured, assumed, fitted and fixed"),
                           ("frequencies", "Frequencies: FIT and HOLDOUT"),
                           ("first_mode", "Dependence on the lowest experimental record (it stays in the fit)"),
                           ("assumptions", "What the fixed inputs carry: factor on the estimated moduli"),
                           ("minima", "Minima reached from the starts"),
                           ("diagnostics", "Convergence, rank and coupling"),
                           ("sensitivity", "Sensitivity d ln f / d ln p (FIT rows, at the fitted point)"),
                           ("surrogate", "Surrogate check: Ritz against the stored Abaqus frequencies at the INP values")):
            inner.addWidget(_label(title, "sectionTitle"))
            box = QVBoxLayout()
            inner.addLayout(box)
            self.result_boxes[key] = box
        inner.addWidget(_label("4. Stability: leave one FIT record out", "sectionTitle"))
        inner.addWidget(_label(rm.STABILITY_NOTE, "hint"))
        row = QHBoxLayout()
        self.stability_button = QPushButton("Check stability")
        self.stability_button.setObjectName("tuningStability")
        self.stability_button.setMinimumHeight(32)
        self.stability_button.clicked.connect(lambda: self.run_stability())
        row.addWidget(self.stability_button)
        row.addStretch(1)
        inner.addLayout(row)
        self.stability_statement = _label("", "warnings")
        self.stability_statement.setVisible(False)
        inner.addWidget(self.stability_statement)
        self.stability_boxes = {}
        for key, title in (("stability_assessment", "The 10 % objective: three separate questions"),
                           ("stability_loo", "Refits without one FIT record (changes against the full-data estimates)"),
                           ("stability_control", "Which records control each estimate"),
                           ("stability_influence", "Local influence d ln p / d ln f_exp (from the full fit's sensitivity matrix)"),
                           ("stability_fixed", "Exact dependence on the assumed thickness and density")):
            caption = _label(title, "sectionTitle")
            caption.setVisible(False)
            inner.addWidget(caption)
            box = QVBoxLayout()
            inner.addLayout(box)
            self.stability_boxes[key] = (caption, box)
        self.influence_note = _label("", "hint")
        self.influence_note.setVisible(False)
        self.stability_boxes["stability_influence"][1].addWidget(self.influence_note)
        row = QHBoxLayout()
        self.export_button = QPushButton("Export proposal (JSON)...")
        self.export_button.setObjectName("tuningExport")
        self.export_button.clicked.connect(lambda: self.export())
        row.addWidget(self.export_button)
        self.summary_button = QPushButton("Export readable summary (.txt)...")  # ABM-AUD-6: a registered result only
        self.summary_button.setObjectName("tuningExportSummary")
        self.summary_button.clicked.connect(lambda: self.export_summary())
        row.addWidget(self.summary_button)
        row.addStretch(1)
        inner.addLayout(row)
        self.export_note = _label("", "hint")
        inner.addWidget(self.export_note)
        self.results_card.setVisible(False)
        return self.results_card

    # ---------------------------------------------------------------------------------------------- ABM-AUD-5

    def _build_registered(self) -> QFrame:
        """The registered route: the modal set of the Analyze comparison, the declared plate and the shape review."""
        card, inner = _card()
        inner.addWidget(_label(rm.REGISTERED_TITLE, "sectionTitle"))
        inner.addWidget(_label(rm.REGISTERED_INTRO, "hint"))
        row = QHBoxLayout()
        self.use_registered_button = QPushButton("Use the comparison shown on Analyze")
        self.use_registered_button.setObjectName("tuningUseRegistered")
        self.use_registered_button.clicked.connect(lambda: self.use_registered())
        row.addWidget(self.use_registered_button)
        row.addStretch(1)
        inner.addLayout(row)
        self.registered_state = _label(rm.REGISTERED_NONE, "hint")
        self.registered_state.setObjectName("tuningRegisteredState")
        inner.addWidget(self.registered_state)
        self.registered_identity_box = QVBoxLayout()
        inner.addLayout(self.registered_identity_box)
        self.registered_form = QFrame()  # filled by _build_registered_form when a registered set is first taken
        self.reg_fields, self.reg_categories, self.reg_axes, self.review_boxes = {}, {}, {}, {}
        inner.addWidget(self.registered_form)
        self.registered_form.setVisible(False)
        return card

    def _build_registered_form(self) -> None:
        """The form of the registered route, built once, when it is first needed: a window that never takes a registered
        set carries none of its widgets (every window of the program holds this page)."""
        if self.reg_fields:
            return
        form = QVBoxLayout(self.registered_form)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(8)
        form.addWidget(_label("Measured and fixed inputs (nothing is taken from a file unless you ask for it)", "sectionTitle"))
        form.addWidget(_label(rm.CATEGORY_NOTE, "hint"))
        grid = QGridLayout()
        grid.setColumnMinimumWidth(0, 130)  # the captions wrap and never ask for a width of their own
        grid.setColumnStretch(3, 1)
        for line, (key, caption) in enumerate(rm.PLATE_FIELDS):
            grid.addWidget(_label(caption), line, 0)
            field = QLineEdit()
            field.setObjectName(f"reg_{key}")
            field.setAccessibleName(caption)
            field.setMinimumWidth(70)
            field.setMaximumWidth(160)
            field.textChanged.connect(lambda _t: self._registered_changed())
            grid.addWidget(field, line, 1)
            choice = _Choice(f"regCategory_{key}", rm.CATEGORY_CHOICES, caption)
            choice.changed.connect(self._registered_changed)
            grid.addWidget(choice, line, 2)
            self.reg_fields[key], self.reg_categories[key] = field, choice
        form.addLayout(grid)
        self._line(form, "source", "Source of these values (for example the measurement sheet)")
        form.addWidget(_label(rm.RANGES_TITLE, "sectionTitle"))
        form.addWidget(_label(rm.RANGES_NOTE, "hint"))
        ranges = QGridLayout()
        ranges.setColumnMinimumWidth(0, 130)
        ranges.setColumnStretch(3, 1)
        ranges.addWidget(_label("lowest"), 0, 1)
        ranges.addWidget(_label("highest"), 0, 2)
        for line, (key, caption) in enumerate(rm.PLATE_FIELDS, start=1):
            ranges.addWidget(_label(caption), line, 0)
            for column, end in enumerate(("low", "high"), start=1):
                field = QLineEdit()
                field.setObjectName(f"reg_{end}_{key}")
                field.setAccessibleName(f"{caption}: {'lowest' if end == 'low' else 'highest'} value")
                field.setPlaceholderText("not stated")
                field.setMinimumWidth(70)
                field.setMaximumWidth(160)
                field.textChanged.connect(lambda _t: self._ranges_changed())
                ranges.addWidget(field, line, column)
                self.reg_ranges[f"{end}_{key}"] = field
        form.addLayout(ranges)
        self.ranges_check = _label("", "warnings")
        self.ranges_check.setObjectName("tuningRangesCheck")
        self.ranges_check.setVisible(False)
        form.addWidget(self.ranges_check)
        self._line(form, "suspension", "Support note, optional (the model is free on all edges)")
        form.addWidget(_label("Position in the registered FE frame", "sectionTitle"))
        axes = QGridLayout()
        axes.setColumnMinimumWidth(0, 200)
        axes.setColumnStretch(2, 1)
        for line, (key, caption) in enumerate((("length_axis", "Length a runs along FE axis"),
                                               ("width_axis", "Width b runs along FE axis"))):
            axes.addWidget(_label(caption), line, 0)
            choice = _Choice(f"reg_{key}", rm.AXIS_CHOICES, caption)
            choice.changed.connect(self._registered_changed)
            axes.addWidget(choice, line, 1)
            self.reg_axes[key] = choice
        form.addLayout(axes)
        row = QHBoxLayout()
        self.take_fe_button = QPushButton("Take length and width from the FE model")
        self.take_fe_button.setObjectName("regTakeFe")
        self.take_fe_button.clicked.connect(lambda: self.take_fe_dimensions())
        row.addWidget(self.take_fe_button)
        row.addStretch(1)
        form.addLayout(row)
        self.reg_linked = QCheckBox(rm.LINK_CHECK)  # a short caption: a check box does not wrap its text
        self.reg_linked.setObjectName("regLinked")
        self.reg_linked.toggled.connect(lambda _on: self._registered_changed())
        form.addWidget(self.reg_linked)
        form.addWidget(_label(rm.LINK_TEXT, "hint"))
        form.addWidget(_label("Material axis 1 (needed only to name E1 and E2)", "sectionTitle"))
        self.reg_material_axis = _Choice("regMaterialAxis", rm.MATERIAL_AXIS_CHOICES, "Material axis 1", checked="")
        self.reg_material_axis.changed.connect(self._registered_changed)
        form.addWidget(self.reg_material_axis)
        self._line(form, "axis_evidence", "Evidence of that direction (for example the layup record)")
        form.addWidget(_label(rm.REFERENCE_NOTE, "hint"))
        reference = QGridLayout()
        for column, key in enumerate(("E1", "E2", "G12")):
            reference.addWidget(_label(f"Reference {key} (MPa)"), 0, 2 * column)
            field = QLineEdit()
            field.setObjectName(f"reg_{key}")
            field.setAccessibleName(f"Reference {key} (MPa)")
            field.setMinimumWidth(70)
            field.textChanged.connect(lambda _t: self._registered_changed())
            reference.addWidget(field, 0, 2 * column + 1)
            reference.setColumnStretch(2 * column + 1, 1)
            self.reg_fields[key] = field
        form.addLayout(reference)
        self.registered_check = _label("", "warnings")
        self.registered_check.setObjectName("tuningRegisteredCheck")
        form.addWidget(self.registered_check)
        row = QHBoxLayout()
        self.review_button = QPushButton("Review Ritz shapes")
        self.review_button.setObjectName("regReview")
        self.review_button.setMinimumHeight(32)
        self.review_button.clicked.connect(lambda: self.review_shapes())
        row.addWidget(self.review_button)
        row.addStretch(1)
        form.addLayout(row)
        self.review_note = _label(rm.RANK_ONLY_NOTE, "hint")
        self.review_note.setObjectName("tuningReviewNote")
        form.addWidget(self.review_note)
        for key, title in (("reg_frame", "How the Ritz rectangle is tied to the registered frame"),
                           ("reg_mac", "Shape review: MAC of the records against the Ritz modes"),
                           ("reg_correspondence", "The correspondence of section 2 against the reviewed shapes"),
                           ("reg_groups", "Close Ritz modes: individual and group agreement, kept apart")):
            caption = _label(title, "sectionTitle")
            caption.setVisible(False)
            form.addWidget(caption)
            box = QVBoxLayout()
            form.addLayout(box)
            self.review_boxes[key] = (caption, box)
        self.review_summary = _label("", "warnings")
        self.review_summary.setObjectName("tuningReviewSummary")
        self.review_summary.setVisible(False)
        form.addWidget(self.review_summary)
        self.reg_fixed = QCheckBox(rm.FIX_CHECK)
        self.reg_fixed.setObjectName("regFixed")
        self.reg_fixed.toggled.connect(lambda on: self._fix_toggled(on))
        form.addWidget(self.reg_fixed)
        form.addWidget(_label(rm.FIX_TEXT, "hint"))

    def _line(self, layout, key: str, caption: str) -> None:
        layout.addWidget(_label(caption))
        field = QLineEdit()
        field.setObjectName(f"reg_{key}")
        field.setAccessibleName(caption)
        field.setMinimumWidth(80)
        field.textChanged.connect(lambda _t: self._registered_changed())
        layout.addWidget(field)
        self.reg_fields[key] = field

    def _build_registered_results(self) -> QFrame:
        """The registered route's own statements, above the common tables; hidden for an INP result."""
        frame = QFrame()
        inner = QVBoxLayout(frame)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(8)
        self.presentation = _label("", "badge")
        self.presentation.setObjectName("tuningPresentation")
        inner.addWidget(self.presentation)
        self.registered_result_boxes = {}
        for key, title in (("reg_summary", "Research summary (the details are in the tables below)"),
                           ("reg_statements", "Seven separate statements (none implies another)"),
                           ("reg_stiffness", "Bending stiffness of the plate (in its edge axes)"),
                           ("reg_constants", "Engineering constants, conditional"),
                           ("reg_unc_inputs", "Input uncertainty: what was stated"),
                           ("reg_unc_sensitivity", "Local sensitivity of the estimates to each input"),
                           ("reg_unc_ranges", "Estimates at the ends of the stated ranges (one input at a time)")):
            inner.addWidget(_label(title, "sectionTitle"))
            box = QVBoxLayout()
            inner.addLayout(box)
            self.registered_result_boxes[key] = box
        self.uncertainty_note = _label(rm.UNCERTAINTY_NONE, "warnings")
        self.uncertainty_note.setObjectName("tuningUncertaintyNote")
        self.registered_result_boxes["reg_unc_inputs"].addWidget(_label(rm.UNCERTAINTY_NOTE, "hint"))
        row = QHBoxLayout()
        self.uncertainty_button = QPushButton("Assess input sensitivity and ranges")
        self.uncertainty_button.setObjectName("tuningUncertainty")
        self.uncertainty_button.setMinimumHeight(32)
        self.uncertainty_button.clicked.connect(lambda: self.run_uncertainty())
        row.addWidget(self.uncertainty_button)
        row.addStretch(1)
        self.registered_result_boxes["reg_unc_inputs"].addLayout(row)
        self.registered_result_boxes["reg_unc_inputs"].addWidget(self.uncertainty_note)
        self.stiffness_note = _label("", "hint")
        self.registered_result_boxes["reg_stiffness"].addWidget(self.stiffness_note)
        self.constants_note = _label("", "warnings")
        self.constants_note.setObjectName("tuningConstantsNote")
        self.registered_result_boxes["reg_constants"].addWidget(self.constants_note)
        for key, title in (("reg_branch", "Fixed branches: from the reviewed reference to the fitted values"),
                           ("reg_fitted", "The fixed correspondence against the Ritz shapes at the fitted values"),
                           ("reg_fitted_groups", "Close Ritz modes at the fitted values"),
                           ("reg_reference", "The fixed correspondence against the reviewed shapes (reference constants)"),
                           ("reg_result_frame", "How the Ritz rectangle was tied to the registered frame")):
            inner.addWidget(_label(title, "sectionTitle"))
            box = QVBoxLayout()
            inner.addLayout(box)
            self.registered_result_boxes[key] = box
        self.branch_statement = _label("", "hint")
        self.branch_statement.setObjectName("tuningBranchStatement")
        self.registered_result_boxes["reg_branch"].addWidget(self.branch_statement)
        frame.setVisible(False)
        return frame

    def _plate(self) -> tuple:
        """(plate or None, problems) of what is entered now."""
        texts = {key: field.text() for key, field in self.reg_fields.items()}
        categories = {key: choice.value() for key, choice in self.reg_categories.items()}
        choices = {"length_axis": self.reg_axes["length_axis"].value(), "width_axis": self.reg_axes["width_axis"].value(),
                   "linked": self.reg_linked.isChecked(), "material_axis": self.reg_material_axis.value()}
        return rm.parse_plate(texts, categories, choices)

    def set_ranges(self, **values) -> None:
        """Fill range fields (tests and checks): ``low_length=...``, ``high_length=...`` and so on; "" clears one."""
        self._build_registered_form()
        for key, value in values.items():
            self.reg_ranges[key].setText(value if isinstance(value, str) else f"{value:g}")

    def set_plate(self, **values) -> None:
        """Fill the registered form (tests and checks): field texts by key, ``categories`` {name: category},
        ``length_axis``, ``width_axis``, ``linked``, ``material_axis``."""
        self._build_registered_form()
        for key, choice in self.reg_categories.items():
            if key in values.get("categories", {}):
                choice.set_value(values["categories"][key])
        for key in ("length_axis", "width_axis"):
            if key in values:
                self.reg_axes[key].set_value(values[key])
        if "material_axis" in values:
            self.reg_material_axis.set_value(values["material_axis"])
        if "linked" in values:
            self.reg_linked.setChecked(bool(values["linked"]))
        for key, field in self.reg_fields.items():
            if key in values:
                field.setText(values[key] if isinstance(values[key], str) else f"{values[key]:g}")

    def use_registered(self) -> bool:
        """Take the modal set, sources and registration of the comparison shown on Analyze. A refusal says what is
        missing; nothing is taken from a saved snapshot or from a comparison without a registration."""
        if self._active not in QUIET_JOBS:
            return False
        if self._registered_source is None:
            self.registered_state.setText("Not available: this page is not connected to an Analyze page.")
            return False
        try:
            source = self._registered_source()
            rset = rm.load_registered(source)
        except (am.StepFailed, ValueError) as error:  # a refusal of the registered service is a ValueError
            self.release_registered(f"Not available: {error}")
            return False
        if self._active in ("check", "solid_check"):
            self._token += 1
            self._active, self._cancel = None, None
        for kind in self.paths:  # one source at a time: the INP route's files are released
            self.paths[kind] = ""
            self.fields[kind].setText("")
            self.fields[kind].setToolTip("")
        self._clear_result()
        self._clear_compatibility()
        self._clear_solid()
        self._table("inputs", None, (), (), 0)
        self._say("")
        self._build_registered_form()
        self.registered, self.registered_data = rset, source
        self._drop_review()
        self.sources = rm.Sources(None, None, (), (), "", str(rset.source.get("experimental_file", "")),
                                  str(rset.source.get("experimental_sha256", "")), str(rset.source.get("modal_set_title", "")),
                                  rset.records)
        self._table("registered_identity", self.registered_identity_box, ("Registered set", "Value"),
                    rm.registered_identity_rows(rset), 1)
        self.registered_form.setVisible(True)
        self.registered_state.setText(f"Registered set in use: {len(rset.records)} records, {len(rset.labels)} measured "
                                      f"DOFs, registration {str(rset.registration.get('registration_hash', ''))[:12]}….")
        self._show_records()
        self._registered_changed()
        self.state.setText("Registered set taken. Enter the inputs, review the shapes and fix the correspondence.")
        self._refresh()
        return True

    def release_registered(self, text: str = "") -> None:
        """Forget the registered set, its review and its live result."""
        had = self.registered is not None
        self.registered, self.registered_data = None, None
        self._drop_review()
        self._table("registered_identity", None, (), (), 0)
        self.registered_form.setVisible(False)
        self.registered_state.setText(text or rm.REGISTERED_NONE)
        if had:
            self.sources = None
            self._clear_result()
            old = self._tables.pop("records", None)
            if old is not None:
                old.hide()  # never a stray window
                old.setParent(None)
                old.deleteLater()
            self.role_combos, self.rank_items = {}, {}
            self.state.setText("Choose the two files, or take the comparison from Analyze.")
        self._refresh()

    def analysis_changed(self) -> None:
        """The Analyze page changed. A registered set stays only while it is that page's current comparison."""
        if self.registered is None or self._registered_source is None:
            return
        try:
            now = self._registered_source()
            same = now["inputs"] is self.registered_data["inputs"] and now["analysis"] is self.registered_data["analysis"]
        except (am.StepFailed, ValueError, KeyError):
            same = False
        if not same:
            if self._cancel is not None and self._active in ("review", "registered_fit", "stability"):
                self._cancel.set()
                self._token += 1
                self._active, self._cancel = None, None
            self.release_registered("Released: the comparison on Analyze is no longer the one this set was taken from. "
                                    "Nothing of it is carried into a new calculation; take the current comparison again.")

    def take_fe_dimensions(self) -> bool:
        """An explicit import: the FE extents along the two chosen axes become the length and width, marked as such."""
        if self.registered is None:
            return False
        length = rm.fe_extent_mm(self.registered, self.reg_axes["length_axis"].value())
        width = rm.fe_extent_mm(self.registered, self.reg_axes["width_axis"].value())
        if length is None or width is None or length <= 0.0 or width <= 0.0:
            self.registered_check.setText("Not taken: choose the two FE axes first (the registration must state the FE "
                                          "length unit, and the FE model must have an extent along them).")
            return False
        self.set_plate(length=f"{length:.6g}", width=f"{width:.6g}",
                       categories={"length": rre.IMPORTED_FE, "width": rre.IMPORTED_FE})
        return True

    def _correspondence_signature(self) -> tuple:
        return (tuple(sorted(self.roles().items())), self.declared.text().strip(),
                None if self.review is None else (self.review["set_identity"], self.review["plate_identity"]))

    def _fix_toggled(self, on: bool) -> None:
        self._fixed_signature = self._correspondence_signature() if on else None
        self._stale_registered_result()
        self._refresh()

    def _unfix(self) -> None:
        self._fixed_signature = None
        if self.reg_fields and self.reg_fixed.isChecked():
            self.reg_fixed.blockSignals(True)
            self.reg_fixed.setChecked(False)
            self.reg_fixed.blockSignals(False)

    def _drop_review(self) -> None:
        self.review, self._review_plate = None, None
        for key, (caption, _box) in self.review_boxes.items():
            self._table(key, None, (), (), 0)
            caption.setVisible(False)
        if self.reg_fields:
            self.review_summary.setVisible(False)
            self.review_note.setText(rm.RANK_ONLY_NOTE)
        self._unfix()

    def _stale_registered_result(self) -> None:
        if self.registered is not None and self.result is not None and self.saved_path is None and self._active is None:
            self._clear_result()
            self.request = None
            self.state.setText(rm.STALE_TEXT)

    def _registered_changed(self) -> None:
        """An input of the registered form was edited: the review made for other inputs, the fixing and a live result of
        other inputs are dropped at once, and what is still missing is said."""
        if self.registered is None:
            return
        plate, problems = self._plate()
        if self.review is not None and (plate is None or plate != self._review_plate):
            self._drop_review()
        self._stale_registered_result()
        self.registered_check.setText("Not ready: " + " ".join(problems) if problems else "")
        self.registered_check.setVisible(bool(problems))
        self._refresh()

    def review_shapes(self) -> bool:
        """The MAC of every record against every Ritz rank at the reference constants, in the background."""
        if self.registered is None or self._active is not None:
            return False
        plate, problems = self._plate()
        if problems:
            self._say("Not reviewed: " + " ".join(problems))
            return False
        try:
            degree = int(self.degree.text())
            if not 4 <= degree <= 24:
                raise ValueError
        except ValueError:
            self._say("Not reviewed: the Ritz basis degree must be a whole number between 4 and 24.")
            return False
        self._say("")
        self._drop_review()
        rset = self.registered
        self._review_plate = plate
        self.state.setText("Evaluating the Ritz shapes at the registered points...")
        return self._start("review", lambda _cancel, _s: rre.shape_review(rset, plate, degree))

    def _show_review(self, review: dict) -> None:
        self.review = review
        self.review_note.setText(rm.REVIEW_NOTE)
        tables = {"reg_frame": (("Item", "Value"), rm.frame_rows(review), 1),
                  "reg_mac": (rm.review_headers(review), rm.review_rows(review), 0)}
        for key, (headers, rows, stretch) in tables.items():
            caption, box = self.review_boxes[key]
            caption.setVisible(True)
            self._table(key, box, headers, rows, stretch)
        self._show_review_correspondence()
        self.state.setText(f"Shapes reviewed at the reference constants: {len(review['records'])} records against "
                           f"{len(review['ranks'])} Ritz modes on {review['dof_count']} measured DOFs.")

    def _show_review_correspondence(self) -> None:
        """The correspondence that section 2 states now, against the reviewed shapes. Nothing is assigned here."""
        self.review_table = None
        if self.review is None or self.registered is None:
            return
        try:
            observations = self.build_request().observations
            rft.validate_correspondence(observations)
            table = rre.review_correspondence(self.review, self.registered, self._review_plate, observations)
        except (ValueError, KeyError) as error:
            for key in ("reg_correspondence", "reg_groups"):
                self._table(key, None, (), (), 0)
                self.review_boxes[key][0].setVisible(False)
            self.review_summary.setText(f"The correspondence of section 2 cannot be compared: {error}")
            self.review_summary.setVisible(True)
            return
        self.review_table = table
        caption, box = self.review_boxes["reg_correspondence"]
        caption.setVisible(True)
        self._table("reg_correspondence", box, rm.CORRESPONDENCE_HEADERS, rm.correspondence_table_rows(table), 8)
        caption, box = self.review_boxes["reg_groups"]
        rows = rm.group_rows(table)
        caption.setVisible(bool(rows))
        self._table("reg_groups", box, rm.GROUP_HEADERS, rows, 2)
        self.review_summary.setText(rm.correspondence_summary_text(table))
        self.review_summary.setVisible(True)

    def _run_registered(self) -> bool:
        plate, problems = self._plate()
        if problems:
            self._say("Not started: " + " ".join(problems))
            return False
        try:
            request = self.build_request()
            if not request.search_factor > 1.0:
                raise ValueError("The search range factor must exceed 1.")
            if not 4 <= request.degree <= 24:
                raise ValueError("The Ritz basis degree must be between 4 and 24.")
            review = self.review if rre.review_is_current(self.review, self.registered, plate, request.degree) else None
            rre.tracked_request(self.registered, plate, request, review)  # every refusal, before anything starts
            if len(request.fit_rows()) <= len(rft.PARAMETERIZATIONS[request.parameterization]):
                raise ValueError(f"{len(request.fit_rows())} FIT frequencies cannot determine "
                                 f"{len(rft.PARAMETERIZATIONS[request.parameterization])} parameters; keep more in the fit.")
        except (ValueError, KeyError) as error:
            self._say(f"Not started: {error}")
            return False
        if not self.reg_fixed.isChecked() or self._fixed_signature != self._correspondence_signature():
            self._unfix()
            self._say("Not started: the record -> Ritz rank correspondence is not fixed. Review it and tick the fixing "
                      "statement; a fit never starts on a correspondence nobody fixed.")
            return False
        text = rm.confirmation_text(self.registered, plate, request, review is not None, self.review_table)
        if not self._ask_confirm("Run one research fit", text):
            self._say("")
            self.state.setText("Not started: the calculation was not confirmed.")
            return False
        self._say("")
        self._clear_result()
        self.request = request
        source, rset = self.registered_data, self.registered
        self._run_plate, self._run_review = plate, review
        self.state.setText("Checking the source files and fitting...")
        return self._start("registered_fit", lambda cancel, solved: rm.run_registered(source, rset, plate, request, review,
                                                                                       cancel, solved))

    def _show_registered(self, block: dict) -> None:
        """The registered route's statements, stiffnesses, constants, branches and correspondence of a result."""
        self.block = block
        self.registered_results.setVisible(True)
        verdict = block["presentation"]["verdict"]
        self.presentation.setText(rm.presentation_text(block) + " | " + rre.LABEL)
        self.presentation.setProperty("state", "chosen" if verdict == rre.SUPPORTED_ESTIMATE else "blocked")
        self.presentation.style().unpolish(self.presentation)
        self.presentation.style().polish(self.presentation)
        boxes = self.registered_result_boxes
        self._table("reg_statements", boxes["reg_statements"], ("Statement", "Verdict", "Basis"), rm.statement_rows(block), 2)
        self._table("reg_stiffness", boxes["reg_stiffness"], rm.STIFFNESS_HEADERS, rm.stiffness_rows(block), 2)
        self.stiffness_note.setText(block["stiffness"]["note"] + f" Surface mass {block['stiffness']['surface_mass_kg_m2']:.5g} "
                                    "kg/m² (computed from the declared mass and plan).")
        self._table("reg_constants", boxes["reg_constants"], rm.CONSTANT_HEADERS, rm.constant_rows(block), 2)
        self.constants_note.setText(rm.constants_note(block))
        self._table("reg_branch", boxes["reg_branch"], rm.BRANCH_HEADERS, rm.branch_rows(block), 8)
        self.branch_statement.setText(block["branch"].get("statement", ""))
        fitted, reference = block["correspondence"].get("fitted"), block["correspondence"].get("reference")
        self._table("reg_fitted", boxes["reg_fitted"], rm.CORRESPONDENCE_HEADERS,
                    rm.correspondence_table_rows(fitted) if fitted else (), 8)
        self._table("reg_fitted_groups", boxes["reg_fitted_groups"], rm.GROUP_HEADERS, rm.group_rows(fitted) if fitted else (), 2)
        self._table("reg_reference", boxes["reg_reference"], rm.CORRESPONDENCE_HEADERS,
                    rm.correspondence_table_rows(reference) if reference else (), 8)
        self._table("reg_result_frame", boxes["reg_result_frame"], ("Item", "Value"), rm.frame_rows(block), 1)
        self._show_uncertainty(self.uncertainty)  # and the summary with it

    # ---------------------------------------------------------------------------------------------- ABM-AUD-6

    def _range_texts(self) -> dict:
        return {key: field.text() for key, field in self.reg_ranges.items()}

    def _ranges(self) -> tuple:
        """({input: (low, high)}, problems) of the range fields against the entered plate."""
        plate, _problems = self._plate()
        return rm.parse_ranges(self._range_texts(), plate)

    def _ranges_changed(self) -> None:
        """A range was edited: an assessment made for other ranges is dropped at once; the fit itself is not touched."""
        if self.registered is None:
            return
        _ranges, problems = self._ranges()
        self.ranges_check.setText("Ranges not usable: " + " ".join(problems) if problems else "")
        self.ranges_check.setVisible(bool(problems))
        if self.uncertainty is not None and self.saved_path is None and self._active is None:
            self._show_uncertainty(None)
            self.state.setText("The ranges changed: the previous assessment was cleared. Assess again for these ranges.")
        self._refresh()

    def run_uncertainty(self) -> bool:
        """The sensitivity of the shown estimate to its inputs and its values over the stated ranges, in the background."""
        if (self.registered is None or self.block is None or self.result is None or self.saved_path is not None
                or self._active is not None or self.request is None):
            return False
        ranges, problems = self._ranges()
        if problems:
            self._say("Not assessed: " + " ".join(problems))
            return False
        self._say("")
        self._show_uncertainty(None)
        source, rset, plate, review = self.registered_data, self.registered, self._run_plate, self._run_review
        request, result = self.request, self.result
        self.state.setText("Assessing the inputs: the same fit is repeated with one input changed at a time...")
        return self._start("uncertainty", lambda cancel, solved: rm.run_uncertainty(source, rset, plate, request, review,
                                                                                   result, ranges, cancel, solved))

    def _show_uncertainty(self, uncertainty: Optional[dict]) -> None:
        self.uncertainty = uncertainty
        boxes = self.registered_result_boxes
        if uncertainty:
            self._table("reg_unc_inputs", boxes["reg_unc_inputs"], rm.UNCERTAINTY_INPUT_HEADERS,
                        rm.uncertainty_input_rows(uncertainty), 2)
            self._table("reg_unc_sensitivity", boxes["reg_unc_sensitivity"], rm.SENSITIVITY_HEADERS,
                        rm.uncertainty_sensitivity_rows(uncertainty), 1)
            self._table("reg_unc_ranges", boxes["reg_unc_ranges"], rm.RANGE_HEADERS, rm.uncertainty_range_rows(uncertainty), 1)
        else:
            for key in ("reg_unc_inputs", "reg_unc_sensitivity", "reg_unc_ranges"):
                self._table(key, None, (), (), 0)
        self.uncertainty_note.setText(rm.uncertainty_text(uncertainty))
        self._show_summary()

    def _show_summary(self) -> None:
        """The ten-point summary of the shown registered result, from what is on the page now."""
        self._table("reg_summary", None, (), (), 0)  # the blocks shown before, if any
        self.summary_labels = []
        if self.block is None or self.result is None:
            return
        frame = QFrame()  # wrapped words, not a table: a table cell would cut every sentence
        frame.setObjectName("tuning_reg_summary")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        rows = rm.summary_rows(self.result, self.block, self.stability, self.uncertainty)
        for index, (title, text) in enumerate(rows, start=1):
            head, body = _label(title, "sectionTitle"), _label(text)
            head.setObjectName(f"summaryTitle_{index}")
            body.setObjectName(f"summaryPoint_{index}")
            layout.addWidget(head)
            layout.addWidget(body)
            self.summary_labels.append((head, body))
        self._tables["reg_summary"] = frame
        self.registered_result_boxes["reg_summary"].addWidget(frame)

    def summary_points(self) -> list:
        """[(point, text)] of the summary as it is shown."""
        return [(head.text(), body.text()) for head, body in getattr(self, "summary_labels", [])]

    def summary_document(self) -> str:
        return rm.summary_text(self.result, self.block, self.stability, self.uncertainty,
                               Path(self.saved_path).name if self.saved_path else "")

    def export_summary(self, path: Optional[str] = None) -> bool:
        """The readable summary of the shown registered result as a text file. Also for a saved result: it is a rendering
        of the snapshot and says so; nothing is recalculated."""
        if self.block is None or self.result is None or self._active not in QUIET_JOBS:
            return False
        path = path if path is not None else self._ask_save_summary("registered_ritz_summary.txt")
        if not path:
            return False
        try:
            Path(path).write_text(self.summary_document(), encoding="utf-8")
        except Exception as error:  # noqa: BLE001  (a message, never a silent failure of an export)
            self._say(f"Not exported: {type(error).__name__}: {error}")
            return False
        self.export_note.setText(f"Summary exported: {path}")
        return True

    def _dialog_save_summary(self, start: str) -> str:
        path, _f = QFileDialog.getSaveFileName(self, "Export readable summary", start, rm.SUMMARY_FILTER)
        return path

    # ---------------------------------------------------------------------------------------------- tables

    def _table(self, key: str, box, headers, rows, stretch: int) -> DiagnosticTable:
        old = self._tables.pop(key, None)
        if old is not None:
            old.hide()  # hidden for good first: a table taken out of the page must never stay behind as a window
            old.setParent(None)
            old.deleteLater()
        if not rows:
            return None
        table = DiagnosticTable(headers, rows, stretch, text_columns=tuple(range(len(headers))))
        table.setObjectName(f"tuning_{key}")
        self._tables[key] = table
        box.addWidget(table)
        return table

    def table_cells(self, key: str) -> list:
        table = self._tables[key]
        return [[table.item(r, c).text() for c in range(table.columnCount())] for r in range(table.rowCount())]

    def _show_records(self) -> None:
        records = self.sources.records
        holdout = set(rm.default_holdout(records))
        # ABM-AUD-1: a grid of named controls, not a table with cell widgets: Qt does not expose a table's cell widgets to
        # the accessibility interface, so the role of a record could not be read or set by assistive technology.
        table = QFrame()
        table.setObjectName("tuning_records")
        grid = QGridLayout(table)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(4)
        for column, (text, share, width) in enumerate(zip(RECORD_HEADERS, (0, 0, 0, 1), (100, 130, 280, 220))):
            grid.addWidget(_label(text, "sectionTitle"), 0, column)
            grid.setColumnStretch(column, share)
            grid.setColumnMinimumWidth(column, width)  # the labels wrap and never ask for a width of their own
        self.role_combos, self.rank_items = {}, {}
        for row, (record, hz) in enumerate(records, start=1):
            grid.addWidget(_label(str(record)), row, 0)
            grid.addWidget(_label(f"{hz:.4f}"), row, 1)
            combo = _RoleChooser(record)
            combo.setCurrentIndex(ROLES.index(rft.HOLDOUT if record in holdout else rft.FIT))
            combo.currentIndexChanged.connect(lambda _i: self._settings_changed())  # after the default is set
            grid.addWidget(combo, row, 2)
            self.role_combos[record] = combo
            rank = _label("")
            rank.setObjectName(f"tuningRank_{record}")
            grid.addWidget(rank, row, 3)
            self.rank_items[record] = rank
        old = self._tables.pop("records", None)
        if old is not None:
            old.hide()  # never a stray window
            old.setParent(None)
            old.deleteLater()
        self._tables["records"] = table
        self.records_box.addWidget(table)
        self._show_correspondence()

    def _show_correspondence(self) -> None:
        """ABM-AUD-1: the rank every record would be compared with now, and why that correspondence cannot be fitted,
        when it cannot. Read from the service's own rules; nothing is decided here."""
        if self.sources is None or not getattr(self, "rank_items", None):
            self.correspondence_note.setVisible(False)
            return
        texts, problem = rm.correspondence_preview(self.sources.records, self.roles(), self.declared.text())
        for record, item in self.rank_items.items():
            item.setText(texts.get(record, ""))
        self.correspondence_note.setText(f"This correspondence cannot be fitted: {problem}" if problem else "")
        self.correspondence_note.setVisible(bool(problem))

    def rank_texts(self) -> dict:
        return {record: item.text() for record, item in getattr(self, "rank_items", {}).items()}

    def _settings_changed(self) -> None:
        """A role, a declared rank or a setting was edited. The correspondence shown follows at once, and a live result
        of other settings is cleared: old numbers are never shown as the result of the settings on the page."""
        self._show_correspondence()
        if self.registered is not None and self._active is None:  # ABM-AUD-5
            try:
                degree = int(self.degree.text())
            except ValueError:
                degree = None
            if self.review is not None and degree != self.review["degree"]:
                self._drop_review()  # the review was made with another basis
            elif self._fixed_signature is not None and self._fixed_signature != self._correspondence_signature():
                self._unfix()  # the correspondence that was fixed is not the one shown now
            self._show_review_correspondence()
        if self._active is not None or self.result is None or self.saved_path is not None or self.request is None:
            return
        try:
            same = self.build_request() == self.request
        except (ValueError, KeyError):
            same = False
        if not same:
            self._clear_result()
            self.request = None
            self.state.setText(rm.STALE_TEXT)
            self._refresh()

    def roles(self) -> dict:
        return {record: combo.currentData() for record, combo in getattr(self, "role_combos", {}).items()}

    def set_role(self, record: int, role: str) -> None:
        self.role_combos[record].setCurrentIndex(ROLES.index(role))

    # ---------------------------------------------------------------------------------------------- files

    def _dialog_path(self, kind: str, start: str) -> str:
        pattern = {"inp": "Abaqus input (*.inp)", "odb": "Abaqus ODB (*.odb)", "result": rm.EXPORT_FILTER}.get(
            kind, "Experimental modal data (*.unv *.uff)")
        path, _f = QFileDialog.getOpenFileName(self, "Choose file", start, pattern)
        return path

    def _dialog_save(self, start: str) -> str:
        path, _f = QFileDialog.getSaveFileName(self, "Export proposal", start, rm.EXPORT_FILTER)
        return path

    def _dialog_confirm(self, title: str, text: str) -> bool:
        if len(text.splitlines()) > 15:  # ABM-AUD-5: a long statement scrolls inside a dialog that fits the screen
            dialog = QDialog(self)
            dialog.setObjectName("tuningConfirm")
            dialog.setWindowTitle(title)
            layout = QVBoxLayout(dialog)
            view = QPlainTextEdit(text)
            view.setObjectName("tuningConfirmText")
            view.setReadOnly(True)
            layout.addWidget(view, 1)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No)
            buttons.button(QDialogButtonBox.StandardButton.No).setDefault(True)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            screen = self.screen() or QGuiApplication.primaryScreen()
            free = screen.availableGeometry() if screen is not None else None
            dialog.resize(min(720, int(free.width() * 0.9)) if free else 720, min(600, int(free.height() * 0.85)) if free else 600)
            return dialog.exec() == QDialog.DialogCode.Accepted
        answer = QMessageBox.question(self, title, text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    def choose_file(self, kind: str, path: Optional[str] = None) -> bool:
        if self._active not in QUIET_JOBS:
            return False
        path = path if path is not None else self._ask_path(kind, str(Path(self.paths[kind]).parent) if self.paths[kind] else "")
        if not path:
            return False
        self.paths[kind] = str(path)
        self.fields[kind].setText(str(path))
        self.fields[kind].setToolTip(str(path))
        if self.registered is not None:  # ABM-AUD-5: one source at a time
            self.release_registered("Released: the INP route's files were chosen.")
        self.sources = None
        self._clear_result()
        inp, unv, odb = self.paths["inp"], self.paths["unv"], self.paths["odb"] or None
        if kind == "inp":
            self._clear_compatibility()
            self._clear_solid()
            self._say("")
        if self._active == "solid_check" and kind == "inp":  # the solid check of the old INP is dropped
            self._token += 1
            self._active, self._cancel = None, None
        if self._active == "check" and (kind == "inp" or unv):  # the new job checks the model again
            self._token += 1
            self._active, self._cancel = None, None
        if inp and unv:
            self.state.setText("Reading the files...")
            self._start("read", lambda cancel, _s: rm.read_sources(inp, unv, cancel, odb))
        elif kind == "inp":
            self.state.setText("Checking the model...")
            self._start("check", lambda _cancel, _s: rm.check_model(inp))
        self._refresh()
        return True

    def open_result(self, path: Optional[str] = None) -> bool:
        """Show an exported result as it was saved. Only that file is read; nothing named in it is opened and nothing is
        recalculated. An invalid file is said and the page keeps what it showed."""
        if self._active not in QUIET_JOBS:
            return False
        path = path if path is not None else self._ask_path("result", str(Path(self.saved_path).parent) if self.saved_path else "")
        if not path:
            return False
        try:
            result, stability, block = rm.open_saved_registered(path)
        except rft.TuningRefused as error:
            self._say(f"Not opened: {error}")
            return False
        self._say("")
        if self.registered is not None:  # a saved result is not this session's registered set
            self.release_registered()
        if self._active in ("check", "solid_check"):  # a saved result replaces the pending model check
            self._token += 1
            self._active, self._cancel = None, None
        self._clear_result()
        self.request = None  # the saved run's request is not live: the stability check stays off
        index = self.parameterization.findData(result.request.get("parameterization"))
        if index >= 0:  # the setting shown matches the saved result
            self.parameterization.setCurrentIndex(index)
        self.block = block
        self.uncertainty = (block or {}).get("uncertainty")
        self._show_result(result)
        if stability:
            self._show_stability(stability)
        self.saved_path = str(path)
        self._show_summary()  # with the stability part and the name of the saved file's snapshot
        self.saved_note.setText(rm.SAVED_NOTE.format(name=Path(path).name)
                                + (rm.REGISTERED_SAVED_NOTE if block is not None else ""))
        self.saved_note.setVisible(True)
        self.state.setText(f"Saved result opened: {Path(path).name}. No calculation was run.")
        self._refresh()
        return True

    # ---------------------------------------------------------------------------------------------- jobs

    def _start(self, kind: str, work: Callable) -> bool:
        if self._active is not None:
            return False
        self._token += 1
        token, bridge = self._token, self._bridge
        cancel = threading.Event()
        self._active, self._cancel = kind, cancel

        def solved(count: int) -> None:
            try:
                bridge.solved.emit(token, count)
            except RuntimeError:
                pass

        def target() -> None:
            try:
                value = work(cancel, solved)
            except (rm.ReadFailed, rft.TuningRefused, ValueError) as error:
                value = error
            except Exception as error:  # noqa: BLE001  (a message, never a crash of the window)
                value = RuntimeError(f"{type(error).__name__}: {error}")
            try:
                bridge.done.emit(token, kind, value)
            except RuntimeError:
                pass

        self._thread = threading.Thread(target=target, name=f"new-gui-research-tuning-{kind}", daemon=True)
        self._thread.start()
        self._refresh()
        return True

    def _solved(self, token: int, count: int) -> None:
        if token == self._token and self._active in ("fit", "registered_fit"):
            self.state.setText(f"Fitting: {count} surrogate solves...")
        elif token == self._token and self._active == "uncertainty":
            self.state.setText(f"Assessing the inputs: {count} surrogate solves in the current refit...")
        elif token == self._token and self._active == "stability":
            self.state.setText(f"Stability check: {count} surrogate solves...")

    def _done(self, token: int, kind: str, value) -> None:
        if token != self._token:
            return
        self._active, self._cancel = None, None
        if kind in ("solid_check", "solid_run", "solid_whatif"):
            self._solid_done(kind, value)
            self._refresh()
            return
        if isinstance(value, Exception):
            report = getattr(value, "compatibility", None)
            if report is not None:
                self._show_compatibility(report)
                self._say("Research Tuning cannot use this INP; the model check above says why.")
            else:
                self._say(str(value))
            self.state.setText("Not completed.")
            if report is not None and self.paths["inp"]:  # ABM-SOLID-5: perhaps a supported solid model
                inp = self.paths["inp"]
                self._start("solid_check", lambda _cancel, _s: rm.check_solid(inp))
        elif kind == "check":
            self._show_compatibility(value)
            self.state.setText("Model checked. Choose the PolyMAX modal set.")
        elif kind == "read":
            self.sources = value
            self._say("")
            if value.compatibility is not None:
                self._show_compatibility(value.compatibility)
            self._table("inputs", self.inputs_box, ("Initial assumed Abaqus value", "Value"), rm.input_rows(value), 1)
            self._show_records()
            self.state.setText(f"Read: {len(value.records)} curve-fitted records of {value.set_title}.")
        elif kind == "fit":
            self._show_result(value)
        elif kind == "review":
            self._show_review(value)
        elif kind == "uncertainty":
            if value is None:
                self.state.setText("Assessment cancelled. No uncertainty result.")
            else:
                self._show_uncertainty(value)
                self.state.setText(f"Inputs assessed: {value['refits']} refits, one input changed at a time.")
        elif kind == "registered_fit":
            result, block = value
            self.block = block
            if block is not None and self.sources is not None:  # the stability check and the export read these inputs
                self.sources = rm.Sources(rre.plate_inputs(self._run_plate), *tuple(
                    getattr(self.sources, name) for name in ("dat_path", "dat_rows", "fe_elastic", "fe_classification",
                                                             "unv_path", "unv_sha256", "set_title", "records")))
            self._show_result(result)
        elif kind == "stability":
            if value.get("status") == rft.CANCELLED:
                self.state.setText("Stability check cancelled. No stability result.")
            else:
                self._show_stability(value)
        self._refresh()

    def busy(self) -> bool:
        return self._active is not None or (self._thread is not None and self._thread.is_alive())

    def shutdown(self, timeout: float = 5.0) -> None:
        if self._cancel is not None:
            self._cancel.set()
        self._token += 1
        self._active = None
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout)

    def cancel(self) -> bool:
        if self._active not in ("fit", "registered_fit", "stability", "uncertainty") or self._cancel is None:
            return False
        self._cancel.set()
        self.state.setText("Cancelling after the current surrogate solve...")
        return True

    # ---------------------------------------------------------------------------------------------- ABM-SOLID-5

    def run_solid(self) -> bool:
        """ONE supervised offline FE solve of the checked solid INP at its own values, after explicit confirmation."""
        summary = self.solid
        if summary is None or self._active not in (None,) or summary.preflight.get("decision") != "ALLOW":
            return False
        if not self._ask_confirm("Run one offline FE calculation", rm.solid_confirmation_text(summary)):
            self.solid_state.setText("Not started: the calculation was not confirmed.")
            return False
        self._clear_solid_result()
        request = sfr.ForwardRequest(summary.inp_path, summary.sha256)
        limits = self.solid_limits
        bridge = self._bridge
        token = self._token + 1  # the token _start gives this job; bound before the worker can report

        def emit(event) -> None:
            try:
                bridge.solid_event.emit(token, dict(event))
            except RuntimeError:
                pass

        self.solid_state.setText("Starting the supervised worker...")
        return self._start("solid_run", lambda cancel, _s: sfr.run(request, limits, cancel=cancel, progress=emit))

    def set_whatif(self, rows) -> None:
        """Fill the What-If fields: ``rows`` holds up to three (E1, E2, G12) entries; missing rows are left empty."""
        rows = list(rows)
        for index, cells in enumerate(self.whatif_fields):
            values = rows[index] if index < len(rows) else ("", "", "")
            for field, value in zip(cells, values):
                field.setText("" if value in (None, "") else (value if isinstance(value, str) else f"{value:g}"))

    def _whatif_texts(self) -> list:
        return [[field.text() for field in cells] for cells in self.whatif_fields]

    def _whatif_changed(self) -> None:
        if self.solid is None:
            self.whatif_points, self.whatif_problems = (), {}
            self.whatif_check.setText("")
            self._table("whatif_parameters", self.whatif_parameters_box, (), (), 0)
            self._refresh()
            return
        points, problems = rm.parse_whatif(rm.solid_material_constants(self.solid), self._whatif_texts())
        self.whatif_points, self.whatif_problems = points, problems
        if self.whatif_outcome is not None and (problems or tuple(points) != self._whatif_result_points):
            # the displayed result belongs to other inputs: never show it next to the edited ones
            self._clear_whatif_result()
            self.solid_state.setText("The What-If inputs changed: the previous What-If results were cleared. "
                                     "Calculate again to see results for these inputs.")
        if problems:
            self.whatif_check.setText("Not ready: " + " ".join(
                (f"Row {row}: " if row else "") + " ".join(messages) for row, messages in sorted(problems.items())))
        elif points:
            self.whatif_check.setText(f"{len(points)} point{'s' if len(points) != 1 else ''} ready: "
                                      f"{len(points)} FE solve{'s' if len(points) != 1 else ''} after confirmation.")
        else:
            self.whatif_check.setText("No What-If point entered.")
        shown = points if not problems else ()
        self._table("whatif_parameters", self.whatif_parameters_box, rm.whatif_parameter_headers(shown),
                    rm.whatif_parameter_rows(self.solid, shown) if shown else (), 1)
        self._refresh()

    def run_whatif(self) -> bool:
        """The confirmed What-If points, each solved once, in order, in ONE supervised worker."""
        summary = self.solid
        if summary is None or self._active is not None or summary.preflight.get("decision") != "ALLOW":
            return False
        self._whatif_changed()
        points = self.whatif_points
        if self.whatif_problems or not points:
            self.solid_state.setText("What-If not started: " + (self.whatif_check.text() or "no point entered."))
            return False
        if not self._ask_confirm(f"Run {len(points)} What-If FE calculation{'s' if len(points) != 1 else ''}",
                                 rm.whatif_confirmation_text(summary, points)):
            self.solid_state.setText("What-If not started: the calculation was not confirmed.")
            return False
        self._clear_whatif_result()
        self._whatif_result_points = tuple(points)
        request = sfr.ForwardRequest(summary.inp_path, summary.sha256, points=points)
        limits = self.solid_limits
        bridge = self._bridge
        token = self._token + 1  # the token _start gives this job; bound before the worker can report

        def emit(event) -> None:
            try:
                bridge.solid_event.emit(token, dict(event))
            except RuntimeError:
                pass

        self.solid_state.setText("Starting the supervised worker for the What-If points...")
        return self._start("solid_whatif", lambda cancel, _s: sfr.run(request, limits, cancel=cancel, progress=emit))

    def _clear_whatif_result(self) -> None:
        self.whatif_outcome = None
        self._whatif_result_points = ()
        self.whatif_status.setVisible(False)
        self.whatif_note.setVisible(False)
        for key in ("whatif_frequencies", "whatif_diagnostics"):
            self._table(key, None, (), (), 0)
            self.solid_boxes[key + "_caption"].setVisible(False)

    def _show_whatif_outcome(self, outcome: sfr.RunnerOutcome) -> None:
        self.whatif_outcome = outcome
        solved = sum(p.get("status") == sfr.POINT_SOLVED for p in outcome.points)
        self.whatif_status.setText(f"{outcome.status}: {solved} of {len(outcome.points)} points solved | "
                                   f"{sfr.WHATIF_LABEL}")
        self.whatif_status.setProperty("state", "chosen" if outcome.status == sfr.SOLVED else "blocked")
        self.whatif_status.style().unpolish(self.whatif_status)
        self.whatif_status.style().polish(self.whatif_status)
        self.whatif_status.setVisible(True)
        if solved:
            self.solid_boxes["whatif_frequencies_caption"].setVisible(True)
            self._table("whatif_frequencies", self.solid_boxes["whatif_frequencies"], rm.whatif_frequency_headers(outcome),
                        rm.whatif_frequency_rows(outcome), 0)
            self.whatif_note.setVisible(True)
        self.solid_boxes["whatif_diagnostics_caption"].setVisible(True)
        self._table("whatif_diagnostics", self.solid_boxes["whatif_diagnostics"], ("Item", "Value"),
                    rm.whatif_diagnostic_rows(outcome), 1)
        self.solid_state.setText(f"What-If {outcome.status}: {outcome.message}")

    def cancel_solid(self) -> bool:
        if self._active not in ("solid_run", "solid_whatif") or self._cancel is None:
            return False
        self._cancel.set()
        self.solid_state.setText("Stopping: the worker and all its processes are being terminated...")
        return True

    def _solid_event(self, token: int, event: dict) -> None:
        if token != self._token or self._active not in ("solid_run", "solid_whatif"):
            return
        stage = event.get("stage", "")
        detail = f" ({event['done']} / {event['total']})" if event.get("total") else ""
        memory = ""
        if event.get("peak_job_memory_bytes") is not None:
            memory = (f" | peak memory so far {event['peak_job_memory_bytes'] / 1024 ** 3:.2f} GiB, available "
                      f"{event.get('available_memory_bytes', 0) / 1024 ** 3:.2f} GiB")
        self.solid_state.setText(f"Running: {stage}{detail}{memory}")

    def _solid_done(self, kind: str, value) -> None:
        if kind == "solid_check":
            if isinstance(value, Exception):
                self.solid = None
                self.solid_card.setVisible(True)
                self.solid_state.setText(str(value))
                self.solid_run_button.setVisible(False)
                self.solid_cancel_button.setVisible(False)
                return
            self._show_solid(value)
            self._say("The Kirchhoff-Ritz tuning cannot use this INP. Its frequencies can be calculated in the solid "
                      "offline FE section below.")
            return
        if isinstance(value, Exception):
            self.solid_state.setText(f"Not completed: {value}")
            return
        if kind == "solid_whatif":
            self._show_whatif_outcome(value)
            return
        self._show_solid_outcome(value)

    def _clear_solid_result(self) -> None:
        self.solid_outcome = None
        self.solid_status.setVisible(False)
        self.solid_fe_note.setVisible(False)
        for key in ("solid_frequencies", "solid_diagnostics"):
            self._table(key, None, (), (), 0)
            self.solid_boxes[key + "_caption"].setVisible(False)

    def _clear_solid(self) -> None:
        self.solid = None
        self._clear_solid_result()
        self._clear_whatif_result()
        self.set_whatif(())  # the points belonged to the previous INP's material
        self._whatif_changed()
        for key in ("solid_identity", "solid_material", "solid_reference"):
            self._table(key, None, (), (), 0)
        self.solid_resources.setText("")
        self.solid_state.setText("")
        self.solid_card.setVisible(False)

    def _show_solid(self, summary: rm.SolidSummary) -> None:
        self.solid = summary
        self.solid_card.setVisible(True)
        self.solid_run_button.setVisible(True)
        self.solid_cancel_button.setVisible(True)
        self._table("solid_identity", self.solid_boxes["solid_identity"], ("Item", "Value"), rm.solid_identity_rows(summary), 1)
        self._table("solid_material", self.solid_boxes["solid_material"], ("Input", "Value"), rm.solid_material_rows(summary), 1)
        self._table("solid_reference", self.solid_boxes["solid_reference"], ("Item", "Value"),
                    rm.solid_reference_rows(summary), 1)
        self.solid_resources.setText(rm.solid_resource_text(summary))
        allowed = summary.preflight.get("decision") == "ALLOW"
        self.solid_state.setText("Ready. Nothing is calculated until you start and confirm it." if allowed
                                 else "The calculation is not allowed on this computer now; see the resources line.")
        for cells in self.whatif_fields:  # the original values as hints only; nothing is pre-filled
            for field, key in zip(cells, ("e1", "e2", "g12")):
                field.setPlaceholderText(f"INP {summary.material[key]:g}")
        self._whatif_changed()

    def _show_solid_outcome(self, outcome: sfr.RunnerOutcome) -> None:
        self.solid_outcome = outcome
        solved = outcome.status == sfr.SOLVED
        self.solid_status.setText(f"{outcome.status} | {sfr.RESULT_LABEL}" if solved else f"{outcome.status}: no frequencies")
        self.solid_status.setProperty("state", "chosen" if solved else "blocked")
        self.solid_status.style().unpolish(self.solid_status)
        self.solid_status.style().polish(self.solid_status)
        self.solid_status.setVisible(True)
        if solved:
            self.solid_boxes["solid_frequencies_caption"].setVisible(True)
            self._table("solid_frequencies", self.solid_boxes["solid_frequencies"], rm.SOLID_FREQUENCY_HEADERS,
                        rm.solid_frequency_rows(outcome.result, self.solid), 0)
            self.solid_fe_note.setVisible(True)
        self.solid_boxes["solid_diagnostics_caption"].setVisible(True)
        self._table("solid_diagnostics", self.solid_boxes["solid_diagnostics"], ("Item", "Value"),
                    rm.solid_diagnostic_rows(outcome), 1)
        self.solid_state.setText(f"{outcome.status}: {outcome.message}")

    # ---------------------------------------------------------------------------------------------- run

    def build_request(self) -> rft.TuningRequest:
        roles = self.roles()
        declared = rm.parse_declared(self.declared.text())
        observations = rft.observations_by_rank(
            self.sources.records, holdout=[r for r, role in roles.items() if role == rft.HOLDOUT],
            excluded=[r for r, role in roles.items() if role == rft.EXCLUDED], declared=declared)
        return rft.TuningRequest(observations, self.parameterization.currentData(),
                                 rft.DECLARED if declared else rft.RANK_ORDER, float(self.search.text()),
                                 degree=int(self.degree.text()))

    def run(self) -> bool:
        if self.sources is None or self._active is not None:
            return False
        if self.registered is not None:
            return self._run_registered()
        try:
            request = self.build_request()
            if not request.search_factor > 1.0:
                raise ValueError("The search range factor must exceed 1.")
            if not 4 <= request.degree <= 24:
                raise ValueError("The Ritz basis degree must be between 4 and 24.")
            rft.validate_correspondence(request.observations)  # R1.F2: before anything starts or is cleared
        except (ValueError, KeyError) as error:
            self._say(f"Not started: {error}")
            return False
        self._say("")
        self._clear_result()
        self.request = request
        sources = self.sources
        self.state.setText("Fitting...")
        return self._start("fit", lambda cancel, solved: rft.run_tuning(sources.inputs, request, sources.fe_elastic, cancel,
                                                                         solved, sources.fe_classification))

    def run_stability(self) -> bool:
        """REAL-FIT.R2: leave each FIT record out of the shown result's own request, in the background."""
        result, request, sources = self.result, self.request, self.sources
        if self._active is not None or self.saved_path is not None or result is None or request is None or sources is None or result.status == rft.CANCELLED:
            return False
        self._say("")
        self._clear_stability()
        self.state.setText("Stability check...")
        if self.registered is not None:  # ABM-AUD-5: the refits follow the same fixed branches as the fit
            try:
                request = rre.tracked_request(self.registered, self._run_plate, request, self._run_review)
            except rft.TuningRefused as error:
                self._say(f"Not started: {error}")
                return False
        return self._start("stability", lambda cancel, solved: rfs.run_stability(sources.inputs, request, result, cancel,
                                                                                 solved))

    def _clear_stability(self) -> None:
        self.stability = None
        self.stability_statement.setText("")
        self.stability_statement.setVisible(False)
        self.influence_note.setVisible(False)
        for key, (caption, _box) in self.stability_boxes.items():
            self._table(key, None, (), (), 0)
            caption.setVisible(False)

    def _show_stability(self, stability: dict) -> None:
        self.stability = stability
        self.stability_statement.setText(stability["assessment"]["statement"] + " " + rft.RESULT_LABEL)
        self.stability_statement.setVisible(True)
        tables = {"stability_assessment": (("Question", "Verdict", "Basis"), rm.assessment_rows(stability), 2),
                  "stability_loo": (rm.stability_headers(stability), rm.stability_rows(stability), 0),
                  "stability_control": (rm.CONTROL_HEADERS, rm.control_rows(stability), 6),
                  "stability_influence": (rm.influence_headers(stability), rm.influence_rows(stability), 0),
                  "stability_fixed": (("Item", "Value"), rm.fixed_input_rows(stability), 1)}
        for key, (headers, rows, stretch) in tables.items():
            caption, box = self.stability_boxes[key]
            caption.setVisible(True)
            self._table(key, box, headers, rows, stretch)
        influence = stability["influence"]
        self.influence_note.setText(f"{influence['rank_note']}. {influence['share_note']}.")
        self.influence_note.setVisible(True)
        self._show_summary()  # ABM-AUD-6: the summary names the stability verdict
        self.state.setText(f"Stability check done: {stability['solves']} surrogate solves.")

    def _clear_compatibility(self) -> None:
        self.compat_verdict.setText("")
        self.compat_notes.setText("")
        for widget in (self.compat_title, self.compat_verdict, self.compat_notes):
            widget.setVisible(False)
        self._table("compatibility", None, (), (), 0)

    def _show_compatibility(self, report) -> None:
        """ABM-REAL-INPUT-1: what the INP is; for a model this page does not read, what was read and what stays available."""
        self.compat_title.setVisible(True)
        self.compat_verdict.setText(report.reason)
        self.compat_verdict.setObjectName("hint" if report.supported else "warnings")
        self.compat_verdict.style().unpolish(self.compat_verdict)
        self.compat_verdict.style().polish(self.compat_verdict)
        self.compat_verdict.setVisible(True)
        self._table("compatibility", self.compat_box, ("Read from the INP", "Value"),
                    () if report.supported else rm.compatibility_rows(report), 1)
        notes = rm.compatibility_notes(report)
        self.compat_notes.setText(notes)
        self.compat_notes.setVisible(bool(notes))

    def _say(self, text: str) -> None:
        self.message.setText(text)
        self.message.setVisible(bool(text))

    def _clear_result(self) -> None:
        self.result = None
        self.plot_data = b""
        self.plot.clear()
        for key in ("estimates", "axes", "candidate", "fit_quality", "correspondence", "quantities", "frequencies",
                    "first_mode", "assumptions", "minima", "diagnostics", "sensitivity", "surrogate", "reg_statements",
                    "reg_stiffness", "reg_constants", "reg_branch", "reg_fitted", "reg_fitted_groups", "reg_reference",
                    "reg_result_frame"):
            self._table(key, None, (), (), 0)
        self.block = None
        self.uncertainty = None
        for key in ("reg_summary", "reg_unc_inputs", "reg_unc_sensitivity", "reg_unc_ranges"):
            self._table(key, None, (), (), 0)
        self.uncertainty_note.setText(rm.UNCERTAINTY_NONE)
        self.registered_results.setVisible(False)
        for label in (self.status, self.quality, self.validity, self.reasons, self.accuracy):
            label.setText("")
        self._clear_stability()
        self.results_card.setVisible(False)
        self.export_note.setText("")
        self.saved_path = None
        self.saved_note.setText("")
        self.saved_note.setVisible(False)

    def _show_result(self, result: rft.TuningResult) -> None:
        self.result = result
        self.results_card.setVisible(True)
        block = self.block if result.status != rft.CANCELLED else None  # ABM-AUD-5: the registered route's own part
        registered = block is not None
        head = rm.headline(result)  # ABM-AUD-1: optimizer, spectral fit and physical validity are three statements
        if registered and block["presentation"]["verdict"] != rre.SUPPORTED_ESTIMATE:
            head["state"] = "blocked"  # never the success colour for an estimate that is diagnostic only
        self.status.setText(f"{head['optimizer']} | {rft.RESULT_LABEL}")
        self.quality.setText(head["fit"])
        self.validity.setText(head["validity"])
        for widget in (*self.inp_notes, self.estimate_title, self.candidate_title, self.candidate_none):
            widget.setVisible(not registered)
        if registered:
            self._show_registered(block)
        else:
            self.registered_results.setVisible(False)
        for label, state in ((self.status, head["state"]), (self.quality, head["fit_state"]), (self.validity, "blocked")):
            label.setProperty("state", state)  # never the success colour for a HIGH MISFIT or a HOLDOUT disagreement
            label.style().unpolish(label)
            label.style().polish(label)
        self.reasons.setText("\n".join([rm.STATUS_TEXT.get(result.status, result.status)] + list(result.reasons) + list(result.warnings)))
        self.accuracy.setText(result.accuracy_statement)
        self.mirror_note.setVisible(result.status == rft.MIRROR)
        self.estimate_note.setVisible(head["high_misfit"] and bool(result.estimates) and not registered)
        # a registered result shows its own stiffness and constants, under its own presentation rule
        self._table("estimates", self.estimate_box, rm.estimate_headers(result), () if registered else rm.estimate_rows(result), 0)
        self._table("axes", self.axis_box, rm.AXIS_HEADERS, rm.axis_rows(result), 0)
        self._table("candidate", self.candidate_box, rm.candidate_headers(result),
                    () if registered else rm.candidate_rows(result), 0)
        self.candidate_none.setText(rm.candidate_note(result))
        self.candidate_none.setObjectName("warnings" if result.candidate_presentation == rft.DIAGNOSTIC_ONLY else "hint")
        self.candidate_none.style().unpolish(self.candidate_none)
        self.candidate_none.style().polish(self.candidate_none)
        self.candidate_none.setVisible(not registered)
        self._table("fit_quality", self.result_boxes["fit_quality"], ("Item", "Value"), rm.fit_quality_rows(result), 1)
        self._table("correspondence", self.result_boxes["correspondence"], ("Item", "Value"), rm.correspondence_rows(result), 1)
        self._table("quantities", self.result_boxes["quantities"], rm.QUANTITY_HEADERS, rm.quantity_rows(result), 2)
        self._table("first_mode", self.result_boxes["first_mode"], ("Check", "Value"), rm.first_mode_rows(result), 1)
        self._table("assumptions", self.result_boxes["assumptions"], ("Fixed input changed", "Moduli factor"),
                    rm.assumption_rows(result), 0)
        self._table("frequencies", self.result_boxes["frequencies"],
                    rm.REGISTERED_FREQUENCY_HEADERS if registered else rm.FREQUENCY_HEADERS, rm.frequency_rows(result), 1)
        self._table("minima", self.result_boxes["minima"], ("Minimum", "Fitted values (MPa)", "Cost"), rm.minima_rows(result), 1)
        self._table("diagnostics", self.result_boxes["diagnostics"], ("Item", "Value"), rm.diagnostic_rows(result), 1)
        self._table("sensitivity", self.result_boxes["sensitivity"], ("EXP record",) + tuple(result.parameter_names),
                    rm.sensitivity_rows(result), 0)
        if result.surrogate:
            self._table("surrogate", self.result_boxes["surrogate"], rm.SURROGATE_HEADERS, rm.surrogate_rows(result), 0)
        elif registered:
            self._table("surrogate", self.result_boxes["surrogate"], ("Surrogate check",), (("Not applicable: this route "
                        "compares the measured frequencies with the Ritz model only; no FE spectrum is used.",),), 0)
        else:
            self._table("surrogate", self.result_boxes["surrogate"], ("Surrogate check",), (("Not made: FE classification "
                        "unavailable. Choose an ODB whose modes are already extracted.",),), 0)
        self.state.setText(f"Optimizer {result.status}; spectral fit {rm.quality_of(result).get('verdict')}: "
                           f"{result.evaluations} surrogate solves.")
        width = max(400, self.plot.width() or 900)
        ratio = self.devicePixelRatioF()
        self.plot_data = rm.error_plot(result, width, 380, ratio,
                                       "Ritz at reference values" if registered else "Ritz at INP values") or b""
        pixmap = QPixmap()
        if self.plot_data and pixmap.loadFromData(self.plot_data, "PNG"):
            pixmap.setDevicePixelRatio(ratio)
            self.plot.setPixmap(pixmap)
            self.plot.setFixedHeight(380)

    def export(self, path: Optional[str] = None) -> bool:
        if self.result is None or self.sources is None or self.saved_path is not None or self.result.status == rft.CANCELLED:
            return False
        if self.block is not None and self.registered_data is not None:  # ABM-AUD-5
            changed = rm.sources_unchanged(self.registered_data)
            if changed:  # the result no longer belongs to the files on disk: it is not exported and not kept
                self.release_registered(f"Released: a source file changed after the calculation. {changed}")
                self._say("Not exported: a source file changed after the calculation; the result was cleared.")
                return False
        path = path if path is not None else self._ask_save(
            "registered_ritz_estimate.json" if self.block is not None else "research_tuning_proposal.json")
        if not path:
            return False
        if self.block is not None:
            block = self.block if self.uncertainty is None else dict(self.block, uncertainty=self.uncertainty)
            try:
                rft.write_export(rre.export_document(self.result, block, self.stability), path)
            except OSError as error:
                self._say(f"Not exported: {error}")
                return False
            self.export_note.setText(f"Exported: {path}")
            return True
        sources = {"inp": self.sources.inputs.inp_path, "inp_sha256": self.sources.inputs.inp_sha256,
                   "dat": self.sources.dat_path or "", "unv": self.sources.unv_path, "unv_sha256": self.sources.unv_sha256,
                   "modal_set": self.sources.set_title}
        try:
            rft.write_export(rft.export_document(self.result, self.sources.inputs, sources, self.stability), path)
        except OSError as error:
            self._say(f"Not exported: {error}")
            return False
        self.export_note.setText(f"Exported: {path}")
        return True

    def _refresh(self) -> None:
        running = self._active not in QUIET_JOBS  # a model check never holds the file choice
        solid_ok = self.solid is not None and self.solid.preflight.get("decision") == "ALLOW"
        solid_running = self._active in ("solid_run", "solid_whatif")
        self.solid_run_button.setEnabled(self._active is None and solid_ok)
        self.solid_cancel_button.setEnabled(solid_running)
        self.solid_progress.setVisible(solid_running)
        self.whatif_button.setEnabled(self._active is None and solid_ok and bool(self.whatif_points)
                                      and not self.whatif_problems)
        for cells in self.whatif_fields:
            for field in cells:
                field.setEnabled(not solid_running)
        for button in self.buttons.values():
            button.setEnabled(not running)
        for widget in (self.parameterization, self.declared, self.search, self.degree,
                       *getattr(self, "role_combos", {}).values()):  # ABM-AUD-1: no role changes under a running fit
            widget.setEnabled(not running)
        self.run_button.setEnabled(not running and self.sources is not None)
        self.cancel_button.setEnabled(self._active in ("fit", "registered_fit", "stability", "uncertainty"))
        estimate = (self.block is not None and self.result is not None
                    and self.result.status in (rft.SUPPORTED, rft.MIRROR))
        self.uncertainty_button.setEnabled(not running and estimate and self.saved_path is None
                                           and self.registered is not None and self.request is not None)
        self.summary_button.setEnabled(not running and self.block is not None and self.result is not None)
        self.summary_button.setVisible(self.block is not None)
        self.use_registered_button.setEnabled(not running)
        self.registered_form.setEnabled(not running)
        if self.reg_fields:
            self.review_button.setEnabled(not running and self.registered is not None)
        self.run_button.setText("Run research fit..." if self.registered is not None else "Run tuning")
        live = self.result is not None and self.result.status != rft.CANCELLED and self.saved_path is None
        self.stability_button.setEnabled(not running and live)
        self.progress.setVisible(running and not solid_running)
        self.export_button.setEnabled(not running and live)
        self.open_button.setEnabled(not running)


__all__ = ["ResearchTuningPanel"]
