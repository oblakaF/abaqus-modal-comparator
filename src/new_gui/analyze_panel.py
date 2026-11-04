"""UNIVERSAL-UI-1: the primary page: choose two files, click Analyze (PySide6).

Analyze does the rest in order: find or (after the user's consent) extract the ODB's first 20 modes, read both files,
ask for a modal set only when the file holds several, run the frequency-only diagnostic and the registration check, and
show the result. Pairs and MAC appear only with a verified registration; otherwise the status is REGISTRATION_REQUIRED.
The steps are ``new_gui.analyze_model``'s and run in worker threads. Replacing a file or Cancel stops the running step
and discards its outcome.

UNIVERSAL-REG-3: Compare with confirmed registration runs only on command, with a confirmation made or opened after this
analysis; the sources and the confirmation are checked again first. A confirmation is never picked up by itself.

UNIVERSAL-UI-2: compact progress, the result's scientific notes behind Show details, the tables on tabs. The status, the
registration outcome and the number of warnings stay visible.

WORKING-DRAFT-R2: Save Project and Open Project. An opened project is a saved snapshot: its tables and pictures come only
from the file, no result can be recalculated from it, and the badge is never the verified one. Analyze stays blocked until
Check source files finds the ODB and the experimental file with their saved content; it then gives a fresh result.

GUI-UX-R1: with ``external_results`` the page keeps only the inputs and the saved result's source check. The result's widgets
stay this panel's, and the program's window places them on the Review and MAC / Points pages.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import threading
from typing import Callable, Optional

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (QAbstractItemView, QBoxLayout, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSizePolicy, QTabWidget,
                               QVBoxLayout, QWidget)

from new_gui import analyze_model as am
from new_gui import analyze_summary as asm
from new_gui import comparison_model as cm
from new_gui.diagnostic_model import NEAREST_TITLE
from new_gui.confirmation_dialog import ConfirmationDialog, FILTER as CONFIRMATION_FILTER
from new_gui.diagnostic_panel import DiagnosticTable
from new_gui import project_model as pj
from new_gui import review_model as rv
from new_gui.project_panel import SavedShapePanel
from new_gui.registration_dialog import RegistrationDialog
from services import analysis_project as ap
from services import confirmed_registration as cs
from new_gui.shape_panel import ImageActions, ImageView, ScrollSafeCombo, ShapePanel
from new_gui import shape_model as sm
from new_gui.workspace_state import EXPERIMENTAL, FE

TITLE = "Analyze"
SUBTITLE = "Choose an Abaqus .odb and an experimental .unv or .uff, then click Analyze."
CAPTIONS = {FE: "FE results (.odb)", EXPERIMENTAL: "Experiment (.unv, .uff)"}
ANALYZE = "Analyze"
CANCEL = "Cancel"
CHOOSE_SET = "Choose a modal set..."
IDLE, RUNNING, NEED_SET, DONE, BLOCKED = "idle", "running", "need_set", "done", "blocked"
SIDE_BY_SIDE_WIDTH = 600  # below this page width the two shapes are stacked
TABLE_HEIGHT = 250  # a long table scrolls, so that the shapes stay near
SHOW_DETAILS, HIDE_DETAILS = "Show details", "Hide details"
SHOW_LOG, HIDE_LOG = "Show log", "Hide log"
SET_UP_REGISTRATION = "Set up registration..."
PROPOSED_TEXT = "Registration setup: the geometry checks passed. Diagnostic only: not applied, so no MAC and no mode pairs."
REFUSED_TEXT = "Registration setup: the evidence does not establish a registration."
OPEN_CONFIRMATION = "Open confirmation..."
COMPARE_CONFIRMED = "Compare with confirmed registration"
READY_TEXT = "Confirmed registration ready. It is checked again against the current files when you click Compare."
UNUSABLE_TEXT = "Confirmation not usable: "
PAIR_HINT = "Click a pair to show its two shapes side by side, each on its own coordinates."
REVIEWED_TEXT = ("Registration setup: mapping reviewed by you. Not an accepted physical registration: not applied, so no "
                 "MAC and no mode pairs.")
SHAPE_HINT = ("Click a row to show that EXP record and its nearest FE mode side by side, each on its own coordinates. "
              "They are not a mode pair.")
TAB_TITLES = {"pairs": "Mode pairs", "mac": "MAC", "nearest": "Nearest frequency", "fe": "FE modes",
              "experimental": "Experimental modes"}
BADGE_STATE = {cm.PAIRS_FOUND: "read"}  # any other status is not a verified pairing; a failed check is "blocked"
_FIND, _EXTRACT, _READ, _ANALYSE, _CONFIRMATION = "find", "extract", "read", "analyse", "confirmation"
_SAVE, _OPEN, _CHECK = "save", "open", "check"
PROJECT_ROW_MARGIN = 80  # the card's margins, the spacing and a reserve: the row's width follows the platform's font
OPEN_PROJECT, SAVE_PROJECT, SAVE_PROJECT_AS = "Open Project...", "Save Project", "Save Project As..."
CHECK_SOURCES, CLOSE_PROJECT = "Check source files", "Close Project"
PROJECT_FILTER = f"Modal Comparator project (*{ap.SUFFIX})"
SNAPSHOT_BADGE = "SAVED SNAPSHOT"
SNAPSHOT_TEXT = ("Saved results, shown from the project file. Nothing was recalculated, and the status below is the one "
                 "found when the project was saved: it is not checked against the current files.")
AS_SAVED = "When saved: "
NOT_CHECKED_TEXT = "A new analysis is blocked until Check source files finds the saved content."
SAME_CONTENT_TEXT = ("The ODB and the experimental file have the saved content. Click Analyze for a fresh result; the "
                     "registration is checked again as in any analysis.")
BLOCKED_TEXT = ("A new analysis stays blocked: the ODB and the experimental file must have the saved content. The saved "
                "results stay readable. Use Choose file... if a file moved.")
FRESH_TEXT = "Fresh analysis of the current files, not the saved snapshot of {saved}."
SCOPE_TEXT = (f"FE modes {am.FIRST_MODE}-{am.LAST_MODE} are requested. Experimental: the first {am.MODE_LIMIT} records of the "
              "chosen modal set, the first record included. The first elastic FE mode is found by shape.")
CANDIDATE_SHOWN = "Shown: EXP {exp} ({exp_hz} Hz) and FE {fe} ({fe_hz} Hz), {origin}. Frequency-based candidate, not a validated pair."
PAIR_SHOWN = "Shown: EXP {exp} and FE {fe}, the comparator's pair. Each view stays on its own coordinates."
REOPEN_TEXT = (" The saved project used the confirmation {path}. It is not applied by itself: use Open confirmation to "
               "compare again.")


def _label(text: str = "", name: str = "") -> QLabel:
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    label.setMinimumWidth(0)
    return label


def _card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(8)
    return frame, layout


class _ResultTable(DiagnosticTable):
    """``fill``: the table takes the height it is given, scrolls by itself and selects its own rows."""

    height_cap = TABLE_HEIGHT

    def __init__(self, headers, rows, stretch: int, fill: bool = False):
        self.fill = fill
        super().__init__(headers, rows, stretch)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        if fill:
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def fit(self) -> None:
        if not self.fill:
            super().fit()
            return
        header = self.horizontalHeader()
        others = sum(header.sectionSize(c) for c in range(self.columnCount()) if c != self.stretch)
        header.resizeSection(self.stretch, max(self._header_width(self.stretch), self.viewport().width() - others))


class _Details(QWidget):
    """A toggle and the text behind it, collapsed until the user asks."""

    def __init__(self, lines):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.toggle = QPushButton(SHOW_DETAILS)
        self.toggle.setObjectName("detailsToggle")
        self.toggle.setCheckable(True)
        self.toggle.toggled.connect(self._toggled)
        layout.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignLeft)
        self.body = _label("\n".join(lines), "hint")
        self.body.setVisible(False)
        layout.addWidget(self.body)

    def _toggled(self, shown: bool) -> None:
        self.toggle.setText(HIDE_DETAILS if shown else SHOW_DETAILS)
        self.body.setVisible(shown)


class _ShapesRow(QWidget):
    """The two shape views; side by side when they fit, wherever the row is placed."""

    def __init__(self, panel):
        super().__init__()
        self.panel = panel

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.panel.fit_shapes(event.size().width())


class _Bridge(QObject):
    done = Signal(int, str, object)  # token, step, the step's value or its exception
    progress = Signal(int, str)


class AnalyzePanel(QWidget):
    """``ask_path(kind, start)``, ``ask_folder(start)``, ``ask_launcher(start)``, ``consent(text)``, ``runner`` and
    ``discover`` are replaced in tests; the program uses the dialogs and the real bridge."""

    changed = Signal()
    result_shown = Signal()  # a new result, or none, is in the widgets
    analysis_ready = Signal()  # a finished analysis or an opened saved result
    analysis_blocked = Signal()
    shapes_shown = Signal(str)
    pair_chosen = Signal(int)
    message_changed = Signal(str)

    def __init__(self, *, ask_path: Optional[Callable[[str, str], str]] = None,
                 ask_folder: Optional[Callable[[str], str]] = None, ask_launcher: Optional[Callable[[str], str]] = None,
                 consent: Optional[Callable[[str], bool]] = None, runner=None, discover=None,
                 external_results: bool = False):
        super().__init__()
        self.external_results = external_results
        self._ask_path = ask_path or self._dialog_path
        self._ask_folder = ask_folder or self._dialog_folder
        self._ask_launcher = ask_launcher or self._dialog_launcher
        self._consent = consent or self._dialog_consent
        self._runner = runner
        self._discover = discover
        self.paths: dict = {FE: None, EXPERIMENTAL: None}
        self.state = IDLE
        self.launcher = ""
        self.folder: Optional[Path] = None
        self.plan = None
        self.inputs: Optional[am.Inputs] = None
        self.analysis: Optional[am.Analysis] = None
        self.discarded = 0
        self.status_label: Optional[QLabel] = None
        self.registration_label: Optional[QLabel] = None
        self.warning_label: Optional[QLabel] = None
        self.details: Optional[_Details] = None
        self.registration_button: Optional[QPushButton] = None
        self.registration_dialog: Optional[RegistrationDialog] = None
        self.proposal = None
        self.proposal_label: Optional[QLabel] = None
        self.confirmation: Optional[dict] = None  # made or opened after this analysis; used only on command
        self.confirmation_view: Optional[ConfirmationDialog] = None
        self.open_confirmation_button: Optional[QPushButton] = None
        self.compare_button: Optional[QPushButton] = None
        self.result_tabs: Optional[QTabWidget] = None
        self.comparison_tabs: Optional[QTabWidget] = None
        self.review_state: Optional[rv.ReviewState] = None
        self.tables: dict = {}
        self.snapshot: Optional[pj.Snapshot] = None  # an opened project: the page shows only what it holds
        self.source_check: Optional[pj.SourceCheck] = None
        self.project_path: Optional[Path] = None
        self.registration_ref: Optional[pj.RegistrationReference] = None  # of the comparison shown
        self.confirmation_ref: Optional[pj.RegistrationReference] = None  # of the confirmation ready to use
        self._compared_with: Optional[pj.RegistrationReference] = None
        self._opened_confirmation = ""
        self._wanted_set_key: Optional[str] = None  # the saved choice of modal set, for a fresh analysis of a project
        self._fresh_text, self._reopen_text = "", ""
        self._state_before_project = IDLE
        self.snapshot_label: Optional[QLabel] = None
        self.source_label: Optional[QLabel] = None
        self.check_button: Optional[QPushButton] = None
        self._token = 0
        self._cancel: Optional[threading.Event] = None
        self._threads: list[threading.Thread] = []
        self._bridge = _Bridge(self)
        self._bridge.done.connect(self._step_done)
        self._bridge.progress.connect(self._progress)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self._build_inputs())
        self.project_box, self.project_layout = self._box()
        self.summary_box, self.summary_layout = self._box()
        layout.addWidget(self.summary_box)
        layout.addWidget(self.project_box)
        self.summary_table: Optional[DiagnosticTable] = None
        self.result_box, self.result_layout = self._box()
        self.registration_box, self.registration_layout = self._box()
        self.comparison_box, self.comparison_layout = self._box()
        self.tables_box, self.tables_layout = self._box()
        self.shapes = _ShapesRow(self)
        self.shapes_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self.shapes)
        self.shapes_layout.setContentsMargins(0, 0, 0, 0)
        self.shapes_layout.setSpacing(12)
        self.shape_panels = {kind: ShapePanel(kind, compact=True) for kind in (EXPERIMENTAL, FE)}
        for panel in self.shape_panels.values():
            self.shapes_layout.addWidget(panel, 1, Qt.AlignmentFlag.AlignTop)
        self.saved_shapes = {kind: SavedShapePanel(kind) for kind in (EXPERIMENTAL, FE)}
        for panel in self.saved_shapes.values():
            self.shapes_layout.addWidget(panel, 1, Qt.AlignmentFlag.AlignTop)
        for box in (self.result_box, self.registration_box, self.comparison_box, self.tables_box, self.shapes):
            if external_results:
                box.setParent(self)  # until the window places it on its page
            else:
                layout.addWidget(box)
        self.shapes.setVisible(False)
        self._refresh()

    # ---------------------------------------------------------------------------------------------- building

    @staticmethod
    def _box() -> tuple:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        return box, layout

    def _build_inputs(self) -> QFrame:
        card, inner = _card()
        self.project_row = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        project_row = self.project_row
        self.open_project_button = QPushButton(OPEN_PROJECT)
        self.open_project_button.setObjectName("projectOpen")
        self.open_project_button.clicked.connect(lambda: self.open_project())
        self.save_project_button = QPushButton(SAVE_PROJECT)
        self.save_project_button.setObjectName("projectSave")
        self.save_project_button.clicked.connect(lambda: self.save_project())
        self.save_as_button = QPushButton(SAVE_PROJECT_AS)
        self.save_as_button.setObjectName("projectSaveAs")
        self.save_as_button.clicked.connect(lambda: self.save_project_as())
        for button in (self.open_project_button, self.save_project_button, self.save_as_button):
            project_row.addWidget(button)
        project_row.addStretch(1)
        inner.addLayout(project_row)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        grid.setColumnStretch(0, 1)
        self.fields, self.choose_buttons = {}, {}
        for row, kind in enumerate((FE, EXPERIMENTAL)):
            grid.addWidget(QLabel(CAPTIONS[kind]), 2 * row, 0, 1, 2)  # above its field: any window width fits
            field = QLineEdit()
            field.setReadOnly(True)
            field.setObjectName(f"analyzeFile_{kind}")
            field.setPlaceholderText("not chosen")
            field.setMinimumWidth(80)
            grid.addWidget(field, 2 * row + 1, 0)
            button = QPushButton("Choose file...")
            button.setObjectName(f"analyzeChoose_{kind}")
            button.clicked.connect(lambda _checked=False, k=kind: self.choose_file(k))
            grid.addWidget(button, 2 * row + 1, 1)
            self.fields[kind], self.choose_buttons[kind] = field, button
        inner.addLayout(grid)
        inner.addWidget(_label(SCOPE_TEXT, "hint"))
        self.file_error = _label("", "error")
        inner.addWidget(self.file_error)
        row = QHBoxLayout()
        self.analyze_button = QPushButton(ANALYZE)
        self.analyze_button.setObjectName("primary")
        self.analyze_button.clicked.connect(self.analyze)
        row.addWidget(self.analyze_button)
        self.cancel_button = QPushButton(CANCEL)
        self.cancel_button.setObjectName("analyzeCancel")
        self.cancel_button.clicked.connect(self.cancel)
        row.addWidget(self.cancel_button)
        row.addStretch(1)
        inner.addLayout(row)
        self.launcher_button = QPushButton("Choose Abaqus launcher...")
        self.launcher_button.setObjectName("analyzeLauncher")
        self.launcher_button.clicked.connect(lambda: self.choose_launcher())
        inner.addWidget(self.launcher_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.folder_button = QPushButton("Choose extraction folder...")
        self.folder_button.setObjectName("analyzeFolder")
        self.folder_button.clicked.connect(lambda: self.choose_folder())
        inner.addWidget(self.folder_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.set_row = QWidget()
        set_layout = QHBoxLayout(self.set_row)
        set_layout.setContentsMargins(0, 0, 0, 0)
        set_layout.addWidget(QLabel("Modal set"))
        self.set_combo = ScrollSafeCombo()
        self.set_combo.setObjectName("analyzeSet")
        self.set_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.set_combo.setMinimumContentsLength(20)
        self.set_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.set_combo.activated.connect(self._set_activated)
        set_layout.addWidget(self.set_combo, 1)
        inner.addWidget(self.set_row)
        self.progress = QProgressBar()
        self.progress.setObjectName("analyzeProgress")
        self.progress.setRange(0, 0)  # the steps report no fraction: it says only that the work goes on
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        inner.addWidget(self.progress)
        self.message = _label("", "hint")
        self.message.setVisible(False)
        inner.addWidget(self.message)
        self.log_button = QPushButton(SHOW_LOG)
        self.log_button.setObjectName("detailsToggle")
        self.log_button.setCheckable(True)
        self.log_button.toggled.connect(self._log_toggled)
        inner.addWidget(self.log_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.log = QPlainTextEdit()
        self.log.setObjectName("analyzeLog")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(200)
        self.log.setFixedHeight(90)
        inner.addWidget(self.log)
        return card

    # ---------------------------------------------------------------------------------------------- dialogs

    def _dialog_path(self, kind: str, start: str) -> str:
        path, _filter = QFileDialog.getOpenFileName(self, f"Choose {CAPTIONS[kind]}", start, am.FILTERS[kind])
        return path

    def _dialog_folder(self, start: str) -> str:
        return QFileDialog.getExistingDirectory(self, "Choose the folder for the extracted modes", start)

    def _dialog_launcher(self, start: str) -> str:
        path, _filter = QFileDialog.getOpenFileName(self, "Choose the Abaqus launcher", start,
                                                    "Abaqus launcher (abaqus*.bat abq*.bat *.cmd *.exe);;All files (*)")
        return path

    def _dialog_consent(self, text: str) -> bool:
        answer = QMessageBox.question(self, am.CONSENT_TITLE, text,
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    # ---------------------------------------------------------------------------------------------- the inputs

    def choose_file(self, kind: str, path: Optional[str] = None) -> str:
        """Choose or replace one file. Any running step stops and the shown result goes. Returns the refusal, if any."""
        if path is None:
            current = self.paths[kind]
            path = self._ask_path(kind, str(current.parent) if current else "")
        if not path or not str(path).strip():
            return ""
        problem = am.file_problem(kind, path)
        self.file_error.setText(problem)
        if problem:
            self._refresh()
            return problem
        self._set_path(kind, Path(path).resolve())
        if self.snapshot is not None:  # a moved source: accepted only if a check finds the saved content there
            self.source_check = None
            self._stop()
            self.state = DONE
            self.check_sources()
            return ""
        if kind == FE:
            self.folder = None  # the extraction folder belongs to the ODB chosen
        self._reset()
        return ""

    def _set_path(self, kind: str, path: Optional[Path]) -> None:
        self.paths[kind] = path
        self.fields[kind].setText(str(path) if path else "")
        self.fields[kind].setToolTip(str(path) if path else "")

    def choose_launcher(self, path: Optional[str] = None) -> bool:
        path = path if path is not None else self._ask_launcher(self.launcher)
        if not path or not str(path).strip():
            return False
        self.launcher = str(path)
        self._set_message(f"Abaqus launcher: {self.launcher}. Click Analyze.", "hint")
        return True

    def choose_folder(self, path: Optional[str] = None) -> bool:
        start = str(self.folder or (self.paths[FE].parent if self.paths[FE] else ""))
        path = path if path is not None else self._ask_folder(start)
        if not path or not str(path).strip():
            return False
        self.folder = Path(path)
        if self.snapshot is not None:
            self.check_sources()
            return True
        self._set_message(f"Extraction folder: {self.folder}. Click Analyze.", "hint")
        return True

    def _log_toggled(self, shown: bool) -> None:
        self.log_button.setText(HIDE_LOG if shown else SHOW_LOG)
        self._refresh()

    def open_registration(self) -> Optional[RegistrationDialog]:
        """The evidence dialog for the shown result; it changes nothing on the page but its own summary line."""
        if self.analysis is None or self.inputs is None or self.analysis.comparison is not None:
            return None
        if self.registration_dialog is None:
            self.registration_dialog = RegistrationDialog(self.inputs, self.analysis.set_index, self)
            self.registration_dialog.checked.connect(self._proposal_checked)
            self.registration_dialog.reviewed.connect(self._proposal_reviewed)
            self.registration_dialog.confirmed.connect(self._use_confirmation)
        self.registration_dialog.show()
        self.registration_dialog.raise_()
        return self.registration_dialog

    def _proposal_checked(self, proposal) -> None:
        self.proposal = proposal
        if self.proposal_label is not None:
            self.proposal_label.setText(PROPOSED_TEXT if proposal.proposed else REFUSED_TEXT)
            self.proposal_label.setVisible(True)

    def _proposal_reviewed(self, reviewed: bool) -> None:
        if self.proposal_label is not None and self.proposal is not None and self.proposal.proposed:
            self.proposal_label.setText(REVIEWED_TEXT if reviewed else PROPOSED_TEXT)

    def _use_confirmation(self, document: dict) -> None:
        self.confirmation = document
        view = self.confirmation_view
        made = getattr(self.registration_dialog, "confirmation_dialog", None)
        if view is not None and document is view.existing:
            self.confirmation_ref = pj.RegistrationReference(document, self._opened_confirmation)
        elif made is not None:
            self.confirmation_ref = pj.RegistrationReference(document, made.saved_path, str(made.draft_path or ""))
        else:
            self.confirmation_ref = pj.RegistrationReference(document)
        if self.proposal_label is not None:
            self.proposal_label.setText(READY_TEXT)
            self.proposal_label.setVisible(True)
        if self.compare_button is not None:
            self.compare_button.setVisible(True)

    def open_confirmation(self, path: Optional[str] = None) -> bool:
        """Check a saved confirmation against the current files and display it; it is used only on command."""
        if self.analysis is None or self.state == RUNNING or self.analysis.comparison is not None or self.inputs is None:
            return False
        if path is None:
            path, _filter = QFileDialog.getOpenFileName(self, OPEN_CONFIRMATION, "", CONFIRMATION_FILTER)
        if not path:
            return False
        self._opened_confirmation = str(path)
        inputs, index = self.inputs, self.analysis.set_index
        self._stop()
        self._cancel = threading.Event()
        cancel = self._cancel
        self.state = RUNNING
        self._set_message("Checking the confirmation against the current files...", "hint")
        self._refresh()

        def work(_say):
            try:
                return am.open_confirmation(inputs, index, path, cancel)
            except cs.ConfirmationRefused as refusal:
                return refusal

        self._run(_CONFIRMATION, work)
        return True

    def _confirmation_opened(self, value) -> None:
        self.state = DONE
        self._cancel = None
        self._set_message("", "hint")
        self._refresh()
        if isinstance(value, cs.ConfirmationRefused):
            self.confirmation = None
            if self.compare_button is not None:
                self.compare_button.setVisible(False)
            if self.proposal_label is not None:
                self.proposal_label.setText(UNUSABLE_TEXT + str(value))
                self.proposal_label.setVisible(True)
            return
        self.confirmation_view = ConfirmationDialog(self.inputs, self.analysis.set_index, value.document["draft"], None,
                                                    self, existing=value.document)
        self.confirmation_view.confirmed.connect(self._use_confirmation)
        self.confirmation_view.show()

    def compare_confirmed(self) -> bool:
        """The comparison with the confirmation, which is checked again first. Returns False when nothing started."""
        if self.confirmation is None or self.analysis is None or self.state == RUNNING or self.inputs is None:
            return False
        inputs, index, confirmation = self.inputs, self.analysis.set_index, self.confirmation
        self._compared_with = self.confirmation_ref
        self._reopen_text = ""
        self._stop()
        self._cancel = threading.Event()
        cancel = self._cancel
        self.state = RUNNING
        self._set_message("Checking the confirmation and comparing the mode shapes...", "hint")
        self._refresh()
        self._run(_ANALYSE, lambda _say: am.analyse(inputs, index, cancel, confirmation))
        return True

    def _close_registration(self) -> None:
        view, self.confirmation_view = self.confirmation_view, None
        if view is not None:
            view.confirmed.disconnect(self._use_confirmation)
            view.close()
            view.deleteLater()
        dialog, self.registration_dialog = self.registration_dialog, None
        self.proposal = None
        if dialog is not None:
            dialog.checked.disconnect(self._proposal_checked)
            dialog.reviewed.disconnect(self._proposal_reviewed)
            dialog.confirmed.disconnect(self._use_confirmation)
            dialog.close()
            dialog.deleteLater()

    def _reset(self) -> None:
        self._stop()
        self.state, self.plan, self.inputs, self.analysis = IDLE, None, None, None
        self.confirmation = None
        self.snapshot, self.source_check, self.project_path = None, None, None
        self.registration_ref, self.confirmation_ref, self._compared_with = None, None, None
        self._wanted_set_key, self._fresh_text, self._reopen_text = None, "", ""
        self.log.clear()
        self.set_combo.clear()
        self._set_message("", "hint")
        self._show_result()
        self._refresh()

    def _stop(self) -> None:
        if self._cancel is not None:
            self._cancel.set()
        self._cancel = None
        self._token += 1

    def cancel(self) -> None:
        """Stop what is running; the owned Abaqus process is stopped by the bridge. Finished results stay."""
        if self.state != RUNNING:
            self._stop()
            return
        self._stop()
        self.state = DONE if self.analysis is not None else IDLE  # the frequency result of a comparison stays
        self._set_message("Cancelled.", "hint")
        self._refresh()

    # ---------------------------------------------------------------------------------------------- the steps

    def analyze(self) -> bool:
        """The one command. Returns False when nothing was started (a missing file, or a step is running)."""
        if self.state == RUNNING or not all(self.paths.values()):
            return False
        if self.snapshot is not None and not self._sources_confirmed():  # before any look at the saved paths
            return False
        for kind, path in self.paths.items():
            problem = am.file_problem(kind, path)  # the file may have gone since it was chosen
            if problem:
                self.file_error.setText(problem)
                self._refresh()
                return False
        if self.snapshot is not None:
            self._leave_snapshot()
        self.file_error.setText("")
        self._stop()
        self.analysis, self.inputs, self.confirmation = None, None, None
        self.registration_ref, self.confirmation_ref, self._compared_with = None, None, None
        self.log.clear()
        self._show_result()
        self.set_combo.clear()
        self._cancel = threading.Event()
        self.state = RUNNING
        self._set_message("Identifying the ODB...", "hint")
        self._refresh()
        try:
            self.plan = am.make_plan(self.paths[FE], self.launcher, self.folder, self._discover)
        except am.StepFailed as error:
            self._block(str(error))
            return True
        for text in am.plan_warnings(self.plan):
            self.log.appendPlainText(text)
        plan, cancel = self.plan, self._cancel
        self._run(_FIND, lambda say: am.find_package(plan, cancel, say))
        return True

    def _run(self, step: str, work: Callable) -> None:
        token = self._token
        bridge = self._bridge

        def say(text: str) -> None:
            try:
                bridge.progress.emit(token, text)
            except RuntimeError:
                pass

        def target() -> None:
            try:
                value = work(say)
            except (am.StepFailed, am.StepCancelled) as error:
                value = error
            except Exception as error:  # noqa: BLE001  (a message, never a crash of the window)
                value = am.StepFailed(f"The analysis could not be completed ({type(error).__name__}: {error}).")
            try:
                bridge.done.emit(token, step, value)
            except RuntimeError:
                pass

        worker = threading.Thread(target=target, name=f"new-gui-analyze-{step}", daemon=True)
        self._threads = [thread for thread in self._threads if thread.is_alive()] + [worker]
        worker.start()

    def _progress(self, token: int, text: str) -> None:
        if token == self._token:
            self.log.appendPlainText(text)
            self._refresh()

    def _step_done(self, token: int, step: str, value) -> None:
        if token != self._token:
            self.discarded += 1
            return
        if isinstance(value, am.StepCancelled):
            self.state = DONE if self.analysis is not None else IDLE
            self._set_message("Cancelled.", "hint")
            self._refresh()
        elif isinstance(value, am.StepFailed):
            self.analysis = None  # for example a file changed: what was read no longer stands
            self._show_result()
            self._block(str(value))
        elif step == _OPEN:
            self._project_opened(value)
        elif step == _SAVE:
            self._project_saved(value)
        elif step == _CHECK:
            self._sources_checked(value)
        elif step == _CONFIRMATION:
            self._confirmation_opened(value)
        elif step == _FIND:
            self._package_found(value)
        elif step == _EXTRACT:
            self._read_files(value)
        elif step == _READ:
            self._files_read(value)
        elif step == _ANALYSE:
            self._analysed(value)

    def _package_found(self, manifest: Optional[Path]) -> None:
        if manifest is not None:
            self.log.appendPlainText("These modes were already extracted from this ODB content; Abaqus is not needed.")
            self._read_files(manifest)
            return
        plan = self.plan
        if not plan.ready:
            self._block("\n".join(plan.blockers + tuple(f"• {fix}" for fix in plan.abaqus.fixes)))
            return
        if not self._consent(am.consent_text(plan)):
            self.state = IDLE
            self._set_message("Not started: Abaqus Python was not confirmed.", "hint")
            self._refresh()
            return
        cancel, runner = self._cancel, self._runner
        self._set_message("Extracting modes with Abaqus Python...", "hint")
        self._run(_EXTRACT, lambda say: am.extract(plan, cancel, say, runner))

    def _read_files(self, manifest: Path) -> None:
        cancel, experimental = self._cancel, self.paths[EXPERIMENTAL]
        self._set_message("Reading both files...", "hint")
        self._run(_READ, lambda _say: am.read_inputs(manifest, experimental, cancel))

    def _files_read(self, inputs: am.Inputs) -> None:
        self.inputs = inputs
        self._show_summary()
        sets = inputs.experimental.sets
        self.set_combo.clear()
        if len(sets) == 1:
            self._analyse(0)
            return
        self.set_combo.addItem(CHOOSE_SET, None)
        for index, item in enumerate(sets):
            self.set_combo.addItem(item.title, index)
        self.state = NEED_SET
        wanted, self._wanted_set_key = self._wanted_set_key, None
        chosen = next((index for index, item in enumerate(sets) if str(item.key) == wanted), None)
        if chosen is not None:  # the set the saved project names, by its identity; never a choice made from results
            self.choose_set(chosen)
            return
        self._set_message(f"This file holds {len(sets)} modal sets. Choose one to continue.", "hint")
        self._refresh()

    def _set_activated(self, _row: int = 0) -> None:
        index = self.set_combo.currentData()
        if index is not None:
            self.choose_set(index)

    def choose_set(self, index: int) -> bool:
        """Continue with (or change to) one modal set; the files are not read again."""
        if self.inputs is None or self.state == RUNNING or not 0 <= index < len(self.inputs.experimental.sets):
            return False
        self.set_combo.setCurrentIndex(self.set_combo.findData(index))
        self.confirmation = None
        self._stop()
        self._cancel = threading.Event()
        self._analyse(index)
        return True

    def _analyse(self, index: int) -> None:
        self.analysis = None
        self._compared_with = None
        self._show_result()
        self.state = RUNNING
        self._set_message("Comparing frequencies and checking the registration...", "hint")
        self._refresh()
        inputs, cancel = self.inputs, self._cancel
        self._run(_ANALYSE, lambda _say: am.analyse(inputs, index, cancel))

    def _analysed(self, analysis: am.Analysis) -> None:
        self.analysis = analysis
        self.confirmation = None  # every comparison asks for it again
        self.registration_ref = self._compared_with if analysis.comparison is not None else None
        self._compared_with = None
        self.state = DONE
        self._cancel = None
        self._set_message("", "hint")
        self._show_result()
        self._refresh()
        pairs = analysis.comparison.pair_rows if analysis.comparison is not None else ()
        if pairs:
            self.show_pair(0)
        elif analysis.nearest_rows:
            self.show_candidate(0)
        self.analysis_ready.emit()

    def _block(self, text: str) -> None:
        self.state = BLOCKED
        self._cancel = None
        self._set_message(text, "error")
        self._refresh()
        self.analysis_blocked.emit()

    # ---------------------------------------------------------------------------------------------- the shapes

    def show_candidate(self, row: int) -> bool:
        """Draw one row's EXP record and nearest FE mode side by side (each on its own coordinates)."""
        if self.analysis is None or not 0 <= row < len(self.analysis.nearest_rows):
            return False
        values = self.analysis.nearest_rows[row]
        if self.review_state is None:
            return self._draw_shapes(values[1], values[3])
        shown = self.review_state.row(row)
        drawn = self._draw_shapes(shown.exp_mode, shown.selected_mode)
        self.shapes_shown.emit(CANDIDATE_SHOWN.format(exp=shown.exp_mode, exp_hz=shown.exp_text, fe=shown.selected_mode,
                                                      fe_hz=shown.selected_text, origin=shown.origin))
        return drawn

    def show_pair(self, row: int) -> bool:
        """Draw one pair's EXP record and FE mode side by side (each on its own coordinates)."""
        pairs = self.analysis.comparison.pair_rows if self.analysis and self.analysis.comparison is not None else ()
        if not 0 <= row < len(pairs):
            return False
        cells = pairs[row].cells
        drawn = self._draw_shapes(cells[3], cells[0])
        self.shapes_shown.emit(PAIR_SHOWN.format(exp=cells[3], fe=cells[0]))
        return drawn

    def _pair_clicked(self, row: int) -> None:
        self.show_pair(row)
        self.pair_chosen.emit(row)

    def _draw_shapes(self, experimental_number: str, fe_number: str) -> bool:
        if self.snapshot is not None:  # the saved pictures; nothing is drawn or read
            shown = self.saved_shapes[EXPERIMENTAL].show_number(experimental_number)
            return self.saved_shapes[FE].show_number(fe_number) or shown
        experimental = self.shape_panels[EXPERIMENTAL]
        fe = self.shape_panels[FE]
        records = self.inputs.experimental.sets[self.analysis.set_index].records
        record = next((i for i, item in enumerate(records) if str(item.number) == experimental_number), None)
        if record is None:
            return False
        experimental.set_combo.setCurrentIndex(experimental.set_combo.findData(self.analysis.set_index))
        experimental.item_combo.setCurrentIndex(experimental.item_combo.findData(record))
        experimental.show_shape()
        mode = next((i for i, item in enumerate(self.inputs.fe.modes) if str(item.number) == fe_number), None)
        if mode is not None:
            fe.item_combo.setCurrentIndex(fe.item_combo.findData(mode))
            fe.show_shape()
        return True

    # ---------------------------------------------------------------------------------------------- display

    def _set_message(self, text: str, name: str) -> None:
        self.message.setObjectName(name)
        self.message.style().unpolish(self.message)
        self.message.style().polish(self.message)
        self.message.setText(text)
        self.message.setVisible(bool(text))
        self.message_changed.emit(text)

    def _refresh(self) -> None:
        running = self.state == RUNNING
        ready = all(self.paths.values())
        check = self.source_check
        allowed = self.snapshot is None or (check is not None and check.hashed and check.can_analyze)
        self.analyze_button.setEnabled(ready and not running and allowed)
        self.open_project_button.setEnabled(not running)
        self.save_project_button.setEnabled(self.can_save())
        self.save_as_button.setEnabled(self.can_save())
        if self.check_button is not None:
            self.check_button.setEnabled(not running)
        self.cancel_button.setVisible(running)
        self.file_error.setVisible(bool(self.file_error.text()))
        self.set_row.setVisible(self.set_combo.count() > 1)
        self.set_combo.setEnabled(not running)
        for button in (self.compare_button, self.open_confirmation_button, self.registration_button):
            if button is not None:
                button.setEnabled(not running)
        blocked = self.state == BLOCKED
        self.progress.setVisible(running)
        has_log = (running or blocked) and bool(self.log.toPlainText())
        self.log_button.setVisible(has_log)
        self.log.setVisible(has_log and self.log_button.isChecked())
        self.launcher_button.setVisible(blocked and self.plan is not None and not self.plan.ready)
        package_lost = self.snapshot is not None and check is not None and check.hashed and check.manifest is None
        self.folder_button.setVisible(blocked or package_lost)
        self.changed.emit()

    def _show_result(self) -> None:
        self._fill_result()
        self.result_shown.emit()

    def _full_frequencies(self) -> tuple:
        """Full-precision frequencies for a manual choice's difference: the saved ones, or the ones read."""
        if self.snapshot is not None:
            modes = self.snapshot.document["modes"]
            return ({str(mode["number"]): mode["frequency_hz"] for mode in modes["fe"]},
                    {mode["record"]: mode["frequency_hz"] for mode in modes["experimental"]})
        records = self.inputs.experimental.sets[self.analysis.set_index].records
        return ({str(mode.number): mode.frequency_hz for mode in self.inputs.fe.modes},
                {f"EXP{position}": record.frequency_hz for position, record in enumerate(records, 1)})

    def registration_kind(self) -> str:
        """The registration behind the result shown: nothing else can make a comparison exist."""
        if self.snapshot is not None:
            return self.snapshot.document["registration"]["kind"]
        if self.analysis is None or self.analysis.comparison is None:
            return ap.KIND_NONE
        return ap.KIND_CONFIRMED if self.registration_ref is not None else ap.KIND_ARCHIVED

    def measured_mode(self):
        """One record of the chosen set as read, for its points and measured DOFs; None without read data."""
        if self.analysis is None or self.inputs is None:
            return None
        modes = self.inputs.full_experimental.sets[self.analysis.set_index].dataset.modes
        return modes[0] if len(modes) else None

    def chosen_dataset(self):
        """The experimental dataset of the shown result, when it was read in this session."""
        if self.analysis is None or self.inputs is None:
            return None
        return self.inputs.experimental.sets[self.analysis.set_index].dataset

    def _show_summary(self) -> None:
        """What is loaded and what can be done with it; empty until the files were read or a saved result opened."""
        while self.summary_layout.count():
            widget = self.summary_layout.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.summary_table = None
        if self.inputs is None and self.analysis is None:
            return
        card, inner = _card()
        inner.addWidget(_label("Loaded data", "sectionTitle"))
        rows = asm.summary_rows(self.paths, self.inputs, self.analysis, self.snapshot, FE, EXPERIMENTAL)
        self.summary_table = DiagnosticTable(asm.HEADERS, rows, 1, text_columns=(0,))
        self.summary_table.setObjectName("analyzeSummary")
        inner.addWidget(self.summary_table)
        self.summary_layout.addWidget(card)

    def _fill_result(self) -> None:
        self._close_registration()  # a proposal belongs to the result it was stated on
        for layout in (self.project_layout, self.result_layout, self.registration_layout, self.comparison_layout,
                       self.tables_layout):
            while layout.count():
                widget = layout.takeAt(0).widget()
                if widget is not None:
                    widget.setParent(None)
                    widget.deleteLater()
        analysis = self.analysis
        self.review_state = rv.ReviewState(analysis, *self._full_frequencies()) if analysis is not None else None
        self._show_summary()
        for panel in self.shape_panels.values():
            panel.set_preview(None)
        for panel in self.saved_shapes.values():
            panel.set_entries((), {})
        self.shapes.setVisible(analysis is not None)
        self.snapshot_label = self.source_label = self.check_button = None
        self.status_label = self.registration_label = self.warning_label = None
        self.details = self.result_tabs = self.comparison_tabs = self.registration_button = self.proposal_label = None
        self.open_confirmation_button = self.compare_button = None
        self.tables: dict = {}
        if analysis is None:
            return
        if self.snapshot is not None:
            self._add_snapshot_card()
        self._add_summary(analysis)
        self.result_tabs = QTabWidget()
        self.result_tabs.setObjectName("analyzeResults")
        self.result_tabs.setDocumentMode(True)
        tabs_card, tabs_inner = _card()
        tabs_inner.addWidget(self.result_tabs)
        self.tables_layout.addWidget(tabs_card, 1)
        if analysis.comparison is not None:
            self._add_comparison(analysis.comparison)
        self._add_table("nearest", NEAREST_TITLE, am.NEAREST_HEADERS, analysis.nearest_rows, 9, SHAPE_HINT)
        self.tables["nearest"].cellClicked.connect(lambda row, _column: self.show_candidate(row))
        self._add_table("fe", "", am.FE_HEADERS, analysis.fe_rows, 2)
        self._add_table("experimental", "", am.EXPERIMENTAL_HEADERS, analysis.experimental_rows, 3)
        if self.snapshot is not None:
            shapes = self.snapshot.document["shapes"]
            self.saved_shapes[EXPERIMENTAL].set_entries(shapes["experimental"], self.snapshot.images)
            self.saved_shapes[FE].set_entries(shapes["fe"], self.snapshot.images)
            return
        self.shape_panels[EXPERIMENTAL].set_preview(self.inputs.experimental)
        self.shape_panels[FE].set_preview(self.inputs.fe)
        for panel in self.shape_panels.values():
            panel.component_combo.setCurrentIndex(panel.component_combo.findData("magnitude"))  # any geometry

    def _add_summary(self, analysis: am.Analysis) -> None:
        """The status, the registration outcome and the warning count are always visible; the wording is behind Details."""
        card, inner = _card()
        failed = analysis.registration_outcome == am.FAILED
        saved = self.snapshot is not None
        self.status_label = QLabel(analysis.status)
        self.status_label.setObjectName("badge")
        self.status_label.setProperty("state", "blocked" if failed else "chosen" if saved
                                      else BADGE_STATE.get(analysis.status, "chosen"))  # a saved status is never green
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        inner.addWidget(self.status_label, 0, Qt.AlignmentFlag.AlignLeft)
        inner.addWidget(_label((AS_SAVED if saved else "") + analysis.statement))
        if self._fresh_text:
            inner.addWidget(_label(self._fresh_text + self._reopen_text, "hint"))
        if analysis.registration_note:
            self.registration_label = _label(analysis.registration_note, "error" if failed else "warnings")
            inner.addWidget(self.registration_label)
        inner.addWidget(_label(analysis.summary, "hint"))
        if analysis.notes:
            count = len(analysis.notes)
            self.warning_label = _label(f"{count} warning{'' if count == 1 else 's'}: see details.", "warnings")
            inner.addWidget(self.warning_label)
        self.details = _Details(analysis.facts + (am.RIGID_NOTE,) + tuple(f"• {note}" for note in analysis.notes))
        inner.addWidget(self.details)
        self.result_layout.addWidget(card)
        if analysis.comparison is None and not saved:
            card, inner = _card()
            self.proposal_label = _label("", "warnings")
            self.proposal_label.setVisible(False)
            inner.addWidget(self.proposal_label)
            self.registration_button = QPushButton(SET_UP_REGISTRATION)
            self.registration_button.setObjectName("analyzeSetUpRegistration")
            self.registration_button.clicked.connect(lambda: self.open_registration())
            inner.addWidget(self.registration_button, 0, Qt.AlignmentFlag.AlignLeft)
            self.open_confirmation_button = QPushButton(OPEN_CONFIRMATION)
            self.open_confirmation_button.setObjectName("analyzeOpenConfirmation")
            self.open_confirmation_button.clicked.connect(lambda: self.open_confirmation())
            inner.addWidget(self.open_confirmation_button, 0, Qt.AlignmentFlag.AlignLeft)
            self.compare_button = QPushButton(COMPARE_CONFIRMED)
            self.compare_button.setObjectName("analyzeCompareConfirmed")
            self.compare_button.setVisible(False)
            self.compare_button.clicked.connect(lambda: self.compare_confirmed())
            inner.addWidget(self.compare_button, 0, Qt.AlignmentFlag.AlignLeft)
            self.registration_layout.addWidget(card)

    def _add_table(self, key: str, title: str, headers, rows, stretch: int, hint: str = "", tabs=None, above=None) -> None:
        page = QWidget()
        inner = QVBoxLayout(page)
        inner.setContentsMargins(0, 8, 0, 0)
        inner.setSpacing(8)
        for text, name in ((title, "sectionTitle"), (hint, "hint")):
            if text:
                inner.addWidget(_label(text, name))
        if above is not None:
            inner.addWidget(above)
        fill = self.external_results and tabs is None
        table = _ResultTable(headers, tuple(tuple(str(cell).replace(sm.PROVISIONAL_TEXT, sm.FRF_PEAK_SHORT) for cell in row)
                                            for row in rows), stretch, fill)
        for row, values in enumerate(rows):
            for column, value in enumerate(values):  # a shortened cell keeps the whole wording in its tooltip
                table.item(row, column).setToolTip(str(value))
        self.tables[key] = table
        inner.addWidget(table, 1 if fill else 0)
        if not fill:
            inner.addStretch(1)
        (tabs or self.result_tabs).addTab(page, TAB_TITLES[key])

    def _add_comparison(self, view) -> None:
        self.comparison_tabs = QTabWidget()
        self.comparison_tabs.setObjectName("macResults")
        self.comparison_tabs.setDocumentMode(True)
        card, inner = _card()
        pairs = tuple(tuple(row.cells[i] for i in am.PAIR_COLUMNS) for row in view.pair_rows)
        if pairs:
            self._add_table("pairs", "", am.PAIR_HEADERS, pairs, 7, PAIR_HINT, tabs=self.comparison_tabs)
            self.tables["pairs"].cellClicked.connect(lambda row, _column: self._pair_clicked(row))
        else:
            inner.addWidget(_label(cm.NO_PAIR_TEXT, "hint"))
        inner.addWidget(self.comparison_tabs)
        self.comparison_layout.addWidget(card)
        if view.mac_cells:
            headers = ("FE \\ EXP",) + tuple(str(mode) for mode in view.mac_experimental_modes)
            rows = tuple((str(mode),) + tuple(cells) for mode, cells in zip(view.mac_fe_modes, view.mac_cells))
            picture = None
            values = getattr(view, "mac_values", ())  # empty when the numbers were not kept: the table still shows the text
            if isinstance(values, tuple) and values and len(values) == len(view.mac_fe_modes):
                self.mac_image = ImageView()
                self.mac_actions = ImageActions(self.mac_image, "mac_matrix")
                picture = QWidget()
                column = QVBoxLayout(picture)
                column.setContentsMargins(0, 0, 0, 0)
                column.addWidget(self.mac_image)
                column.addWidget(self.mac_actions)
                self.mac_image.set_image(rv.mac_plot(view))
            self._add_table("mac", "", headers, rows, 0, tabs=self.comparison_tabs, above=picture)

    # ---------------------------------------------------------------------------------------------- projects

    def can_save(self) -> bool:
        return (self.state == DONE and self.analysis is not None
                and (self.snapshot is not None or self.inputs is not None))

    def _project_step(self, step: str, text: str, work: Callable) -> None:
        """A project step in a worker; a refusal comes back as a value, so the shown result is never lost to it."""
        self._state_before_project = self.state
        self._stop()
        self._cancel = threading.Event()
        cancel = self._cancel
        self.state = RUNNING
        self._set_message(text, "hint")
        self._refresh()

        def guarded(say):
            try:
                return work(cancel, say)
            except am.StepCancelled:
                raise
            except ap.ProjectRefused as refusal:
                return refusal
            except Exception as error:  # noqa: BLE001  (a message, never a crash of the window)
                return ap.ProjectRefused(ap.WRITE_FAILED, f"The project step could not be completed "
                                                          f"({type(error).__name__}: {error}).")

        self._run(step, guarded)

    def save_project(self, path: Optional[str] = None) -> bool:
        if not self.can_save():
            return False
        target = path or self.project_path
        return self._start_save(target) if target else self.save_project_as()

    def save_project_as(self, path: Optional[str] = None) -> bool:
        if not self.can_save():
            return False
        if path is None:
            odb = self.paths[FE]
            start = str(self.project_path or (odb.with_suffix(ap.SUFFIX) if odb else f"analysis{ap.SUFFIX}"))
            path, _filter = QFileDialog.getSaveFileName(self, SAVE_PROJECT_AS, start, PROJECT_FILTER)
        if not path:
            return False
        path = Path(path)
        return self._start_save(path if path.suffix else path.with_name(path.name + ap.SUFFIX))

    def _start_save(self, target) -> bool:
        analysis, inputs, odb, reference = self.analysis, self.inputs, self.paths[FE], self.registration_ref
        snapshot, check = self.snapshot, self.source_check

        def work(cancel, say):
            if snapshot is not None:
                return pj.save_snapshot(snapshot, check, target, cancel)
            return pj.save_analysis(analysis, inputs, odb, reference, target, cancel, say)

        self._project_step(_SAVE, "Saving the project: drawing the shapes, then writing the file...", work)
        return True

    def _project_saved(self, value) -> None:
        self.state = DONE
        self._cancel = None
        if isinstance(value, ap.ProjectRefused):
            self._set_message(f"Project not saved: {value}", "error")
            self._refresh()
            return
        self.project_path = Path(value)
        if self.snapshot is not None:
            self.snapshot = replace(self.snapshot, path=self.project_path,
                                    document=pj.relocated_document(self.snapshot.document, self.source_check))
            self._show_snapshot_facts()
        size = self.project_path.stat().st_size / 2 ** 20
        self._set_message(f"Project saved: {self.project_path} ({size:.1f} MB). The source files are not in it.", "hint")
        self._refresh()

    def open_project(self, path: Optional[str] = None) -> bool:
        """Show a saved project. Only that file is read: no path named in it is looked at, and nothing starts."""
        if self.state == RUNNING:
            return False
        if path is None:
            path, _filter = QFileDialog.getOpenFileName(self, OPEN_PROJECT, str(self.project_path or ""), PROJECT_FILTER)
        if not path:
            return False

        def work(_cancel, _say):
            snapshot = pj.open_project(path)
            return snapshot, pj.not_checked(snapshot.document)

        self._project_step(_OPEN, "Opening the project...", work)
        return True

    def _project_opened(self, value) -> None:
        self._cancel = None
        if isinstance(value, ap.ProjectRefused):
            self.state = self._state_before_project  # what was shown stays
            self._set_message(f"Project not opened: {value}", "error")
            self._refresh()
            return
        snapshot, check = value
        self.snapshot, self.source_check, self.project_path = snapshot, check, snapshot.path
        self.inputs, self.plan, self.confirmation, self.folder = None, None, None, None
        self.registration_ref, self.confirmation_ref, self._compared_with = None, None, None
        self._wanted_set_key, self._fresh_text, self._reopen_text = None, "", ""
        self.analysis = snapshot.analysis
        self.state = DONE
        self.log.clear()
        self.set_combo.clear()
        self.file_error.setText("")
        sources = snapshot.document["sources"]
        self._set_path(FE, Path(sources["fe_odb"]["path"]))
        self._set_path(EXPERIMENTAL, Path(sources["experimental"]["path"]))
        self._set_message("", "hint")
        self._show_result()
        self._refresh()
        pairs = self.analysis.comparison.pair_rows if self.analysis.comparison is not None else ()
        if pairs:
            self.show_pair(0)
        elif self.analysis.nearest_rows:
            self.show_candidate(0)
        self.analysis_ready.emit()

    def check_sources(self) -> bool:
        """Hash the source files now and show what was found; opening a project does not do this by itself."""
        if self.snapshot is None or self.state == RUNNING:
            return False
        document, odb, experimental, folder = self.snapshot.document, self.paths[FE], self.paths[EXPERIMENTAL], self.folder

        def work(cancel, say):
            return pj.check_sources(document, odb, experimental, folder, cancel, say)

        self._project_step(_CHECK, "Checking the source files (hashing them can take a while)...", work)
        return True

    def _sources_checked(self, value) -> None:
        self.state = DONE
        self._cancel = None
        if isinstance(value, ap.ProjectRefused):
            self._set_message(f"Sources not checked: {value}", "error")
            self._refresh()
            return
        self.source_check = value
        if value.extraction_folder is not None:
            self.folder = value.extraction_folder
        self._show_snapshot_facts()
        self._set_message(SAME_CONTENT_TEXT if value.can_analyze else BLOCKED_TEXT, "hint" if value.can_analyze else "error")
        self._refresh()

    def close_project(self) -> bool:
        """Leave what is shown: an empty page, with the saved file untouched."""
        if self.state == RUNNING:
            return False
        self._set_path(FE, None)
        self._set_path(EXPERIMENTAL, None)
        self.folder = None
        self.file_error.setText("")
        self._reset()
        return True

    def _sources_confirmed(self) -> bool:
        check = self.source_check
        if check is None or not check.hashed or not check.can_analyze:
            self._set_message(NOT_CHECKED_TEXT, "error")
            self._refresh()
            return False
        return True

    def _leave_snapshot(self) -> None:
        """Only with the saved content confirmed; the fresh result then owes nothing to the project."""
        document = self.snapshot.document
        self._wanted_set_key = document["modal_set"]["key"]
        self._fresh_text = FRESH_TEXT.format(saved=document["saved_at"])
        path = document["registration"]["confirmation_path"]
        if document["registration"]["kind"] == ap.KIND_CONFIRMED and path:
            self._reopen_text = REOPEN_TEXT.format(path=path)
        self.snapshot, self.source_check, self.project_path = None, None, None

    def _add_snapshot_card(self) -> None:
        card, inner = _card()
        badge = QLabel(SNAPSHOT_BADGE)
        badge.setObjectName("badge")
        badge.setProperty("state", "chosen")
        inner.addWidget(badge, 0, Qt.AlignmentFlag.AlignLeft)
        inner.addWidget(_label(SNAPSHOT_TEXT))
        self.snapshot_label = _label("", "hint")
        inner.addWidget(self.snapshot_label)
        self.source_label = _label("", "hint")
        inner.addWidget(self.source_label)
        row = QHBoxLayout()
        self.check_button = QPushButton(CHECK_SOURCES)
        self.check_button.setObjectName("projectCheckSources")
        self.check_button.clicked.connect(lambda: self.check_sources())
        row.addWidget(self.check_button)
        close = QPushButton(CLOSE_PROJECT)
        close.setObjectName("projectClose")
        close.clicked.connect(lambda: self.close_project())
        row.addWidget(close)
        row.addStretch(1)
        inner.addLayout(row)
        self.project_layout.addWidget(card)
        self._show_snapshot_facts()

    def _show_snapshot_facts(self) -> None:
        if self.snapshot is None or self.snapshot_label is None:
            return
        document = self.snapshot.document
        registration = document["registration"]
        lines = [f"Project: {self.snapshot.path}", f"Saved: {document['saved_at']}",
                 f"Modal set: {document['modal_set']['title']}", f"Registration when saved: {registration['kind']}"]
        if registration["kind"] == ap.KIND_CONFIRMED:
            lines.append(f"Confirmed by {registration['confirmed_by']} on {registration['confirmed_at']}; this records "
                         "a statement, not proof of physical correctness.")
        self.snapshot_label.setText("\n".join(lines))
        rows = self.source_check.rows if self.source_check is not None else ()
        self.source_label.setText("\n".join(row.text for row in rows))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        buttons = (self.open_project_button, self.save_project_button, self.save_as_button)
        room = sum(b.sizeHint().width() for b in buttons) + PROJECT_ROW_MARGIN
        self.project_row.setDirection(QBoxLayout.Direction.TopToBottom if event.size().width() <= room
                                      else QBoxLayout.Direction.LeftToRight)  # a narrow window never scrolls sideways

    def fit_shapes(self, width: int) -> None:
        need = sum(panel.minimumSizeHint().width() for panel in self.shape_panels.values()) + 12
        self.shapes_layout.setDirection(QBoxLayout.Direction.TopToBottom if width < max(SIDE_BY_SIDE_WIDTH, need)
                                        else QBoxLayout.Direction.LeftToRight)

    def busy(self) -> bool:
        return ((self.confirmation_view is not None and self.confirmation_view.busy()) or self.state == RUNNING or any(thread.is_alive() for thread in self._threads)
                or any(panel.busy() for panel in self.shape_panels.values())
                or (self.registration_dialog is not None and self.registration_dialog.busy()))

    def shutdown(self) -> None:
        self._stop()
        self.state = IDLE
        self._close_registration()
        for panel in self.shape_panels.values():
            panel.cancel()


__all__ = ["AnalyzePanel", "SUBTITLE", "TITLE"]
