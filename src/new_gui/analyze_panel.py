"""UNIVERSAL-UI-1: the primary page: choose two files, click Analyze (PySide6).

Analyze does the rest in order: find or (after the user's consent) extract the ODB's first 20 modes, read both files,
ask for a modal set only when the file holds several, run the frequency-only diagnostic and the registration check, and
show the result. Pairs and MAC appear only with a verified registration; otherwise the status is REGISTRATION_REQUIRED.
The steps are ``new_gui.analyze_model``'s and run in worker threads. Replacing a file or Cancel stops the running step
and discards its outcome.

UNIVERSAL-UI-2: compact progress, the result's scientific notes behind Show details, the tables on tabs. The status, the
registration outcome and the number of warnings stay visible.
"""

from __future__ import annotations

from pathlib import Path
import threading
from typing import Callable, Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QBoxLayout, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSizePolicy, QTabWidget,
                               QVBoxLayout, QWidget)

from new_gui import analyze_model as am
from new_gui import comparison_model as cm
from new_gui.diagnostic_model import NEAREST_TITLE
from new_gui.diagnostic_panel import DiagnosticTable
from new_gui.registration_dialog import RegistrationDialog
from new_gui.shape_panel import ShapePanel
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
REVIEWED_TEXT = ("Registration setup: mapping reviewed by you. Not an accepted physical registration: not applied, so no "
                 "MAC and no mode pairs.")
SHAPE_HINT = ("Click a row to show that EXP record and its nearest FE mode side by side, each on its own coordinates. "
              "They are not a mode pair.")
TAB_TITLES = {"pairs": "Mode pairs", "mac": "MAC", "nearest": "Nearest frequency", "fe": "FE modes",
              "experimental": "Experimental modes"}
BADGE_STATE = {cm.PAIRS_FOUND: "read"}  # any other status is not a verified pairing; a failed check is "blocked"
_FIND, _EXTRACT, _READ, _ANALYSE = "find", "extract", "read", "analyse"


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
    height_cap = TABLE_HEIGHT

    def __init__(self, headers, rows, stretch: int):
        super().__init__(headers, rows, stretch)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)


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


class _Bridge(QObject):
    done = Signal(int, str, object)  # token, step, the step's value or its exception
    progress = Signal(int, str)


class AnalyzePanel(QWidget):
    """``ask_path(kind, start)``, ``ask_folder(start)``, ``ask_launcher(start)``, ``consent(text)``, ``runner`` and
    ``discover`` are replaced in tests; the program uses the dialogs and the real bridge."""

    changed = Signal()

    def __init__(self, *, ask_path: Optional[Callable[[str, str], str]] = None,
                 ask_folder: Optional[Callable[[str], str]] = None, ask_launcher: Optional[Callable[[str], str]] = None,
                 consent: Optional[Callable[[str], bool]] = None, runner=None, discover=None):
        super().__init__()
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
        self.result_tabs: Optional[QTabWidget] = None
        self.tables: dict = {}
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
        self.result_box = QWidget()
        self.result_layout = QVBoxLayout(self.result_box)
        self.result_layout.setContentsMargins(0, 0, 0, 0)
        self.result_layout.setSpacing(12)
        layout.addWidget(self.result_box)
        self.shapes = QWidget()
        self.shapes_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self.shapes)
        self.shapes_layout.setContentsMargins(0, 0, 0, 0)
        self.shapes_layout.setSpacing(12)
        self.shape_panels = {kind: ShapePanel(kind, compact=True) for kind in (EXPERIMENTAL, FE)}
        for panel in self.shape_panels.values():
            self.shapes_layout.addWidget(panel, 1, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.shapes)
        self.shapes.setVisible(False)
        self._refresh()

    # ---------------------------------------------------------------------------------------------- building

    def _build_inputs(self) -> QFrame:
        card, inner = _card()
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
        self.set_combo = QComboBox()
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
        self.paths[kind] = Path(path).resolve()
        self.fields[kind].setText(str(self.paths[kind]))
        self.fields[kind].setToolTip(str(self.paths[kind]))
        if kind == FE:
            self.folder = None  # the extraction folder belongs to the ODB chosen
        self._reset()
        return ""

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

    def _close_registration(self) -> None:
        dialog, self.registration_dialog = self.registration_dialog, None
        self.proposal = None
        if dialog is not None:
            dialog.checked.disconnect(self._proposal_checked)
            dialog.reviewed.disconnect(self._proposal_reviewed)
            dialog.close()
            dialog.deleteLater()

    def _reset(self) -> None:
        self._stop()
        self.state, self.plan, self.inputs, self.analysis = IDLE, None, None, None
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
        self.state = IDLE
        self._set_message("Cancelled.", "hint")
        self._refresh()

    # ---------------------------------------------------------------------------------------------- the steps

    def analyze(self) -> bool:
        """The one command. Returns False when nothing was started (a missing file, or a step is running)."""
        if self.state == RUNNING or not all(self.paths.values()):
            return False
        for kind, path in self.paths.items():
            problem = am.file_problem(kind, path)  # the file may have gone since it was chosen
            if problem:
                self.file_error.setText(problem)
                self._refresh()
                return False
        self.file_error.setText("")
        self._stop()
        self.analysis, self.inputs = None, None
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
            self.state = IDLE
            self._set_message("Cancelled.", "hint")
            self._refresh()
        elif isinstance(value, am.StepFailed):
            self._block(str(value))
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
        sets = inputs.experimental.sets
        self.set_combo.clear()
        if len(sets) == 1:
            self._analyse(0)
            return
        self.set_combo.addItem(CHOOSE_SET, None)
        for index, item in enumerate(sets):
            self.set_combo.addItem(f"{item.title} ({len(item.records)} records)", index)
        self.state = NEED_SET
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
        self._stop()
        self._cancel = threading.Event()
        self._analyse(index)
        return True

    def _analyse(self, index: int) -> None:
        self.analysis = None
        self._show_result()
        self.state = RUNNING
        self._set_message("Comparing frequencies and checking the registration...", "hint")
        self._refresh()
        inputs, cancel = self.inputs, self._cancel
        self._run(_ANALYSE, lambda _say: am.analyse(inputs, index, cancel))

    def _analysed(self, analysis: am.Analysis) -> None:
        self.analysis = analysis
        self.state = DONE
        self._cancel = None
        self._set_message("", "hint")
        self._show_result()
        self._refresh()
        if analysis.nearest_rows:
            self.show_candidate(0)

    def _block(self, text: str) -> None:
        self.state = BLOCKED
        self._cancel = None
        self._set_message(text, "error")
        self._refresh()

    # ---------------------------------------------------------------------------------------------- the shapes

    def show_candidate(self, row: int) -> bool:
        """Draw one row's EXP record and nearest FE mode side by side (each on its own coordinates)."""
        if self.analysis is None or not 0 <= row < len(self.analysis.nearest_rows):
            return False
        values = self.analysis.nearest_rows[row]
        experimental = self.shape_panels[EXPERIMENTAL]
        fe = self.shape_panels[FE]
        records = self.inputs.experimental.sets[self.analysis.set_index].records
        record = next(i for i, item in enumerate(records) if str(item.number) == values[1])
        experimental.set_combo.setCurrentIndex(experimental.set_combo.findData(self.analysis.set_index))
        experimental.item_combo.setCurrentIndex(experimental.item_combo.findData(record))
        experimental.show_shape()
        mode = next((i for i, item in enumerate(self.inputs.fe.modes) if str(item.number) == values[3]), None)
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

    def _refresh(self) -> None:
        running = self.state == RUNNING
        ready = all(self.paths.values())
        self.analyze_button.setEnabled(ready and not running)
        self.cancel_button.setVisible(running)
        self.file_error.setVisible(bool(self.file_error.text()))
        self.set_row.setVisible(self.set_combo.count() > 1)
        self.set_combo.setEnabled(not running)
        blocked = self.state == BLOCKED
        self.progress.setVisible(running)
        has_log = (running or blocked) and bool(self.log.toPlainText())
        self.log_button.setVisible(has_log)
        self.log.setVisible(has_log and self.log_button.isChecked())
        self.launcher_button.setVisible(blocked and self.plan is not None and not self.plan.ready)
        self.folder_button.setVisible(blocked)
        self.changed.emit()

    def _show_result(self) -> None:
        self._close_registration()  # a proposal belongs to the result it was stated on
        while self.result_layout.count():
            widget = self.result_layout.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        analysis = self.analysis
        for panel in self.shape_panels.values():
            panel.set_preview(None)
        self.shapes.setVisible(analysis is not None)
        self.status_label = self.registration_label = self.warning_label = None
        self.details = self.result_tabs = self.registration_button = self.proposal_label = None
        self.tables: dict = {}
        if analysis is None:
            return
        self._add_summary(analysis)
        self.result_tabs = QTabWidget()
        self.result_tabs.setObjectName("analyzeResults")
        self.result_tabs.setDocumentMode(True)
        tabs_card, tabs_inner = _card()
        tabs_inner.addWidget(self.result_tabs)
        self.result_layout.addWidget(tabs_card)
        if analysis.comparison is not None:
            self._add_comparison(analysis.comparison)
        self._add_table("nearest", NEAREST_TITLE, am.NEAREST_HEADERS, analysis.nearest_rows, 9, SHAPE_HINT)
        self.tables["nearest"].cellClicked.connect(lambda row, _column: self.show_candidate(row))
        self._add_table("fe", "", am.FE_HEADERS, analysis.fe_rows, 2)
        self._add_table("experimental", "", am.EXPERIMENTAL_HEADERS, analysis.experimental_rows, 3)
        self.shape_panels[EXPERIMENTAL].set_preview(self.inputs.experimental)
        self.shape_panels[FE].set_preview(self.inputs.fe)
        for panel in self.shape_panels.values():
            panel.component_combo.setCurrentIndex(panel.component_combo.findData("magnitude"))  # any geometry

    def _add_summary(self, analysis: am.Analysis) -> None:
        """The status, the registration outcome and the warning count are always visible; the wording is behind Details."""
        card, inner = _card()
        failed = analysis.registration_outcome == am.FAILED
        self.status_label = QLabel(analysis.status)
        self.status_label.setObjectName("badge")
        self.status_label.setProperty("state", "blocked" if failed else BADGE_STATE.get(analysis.status, "chosen"))
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        inner.addWidget(self.status_label, 0, Qt.AlignmentFlag.AlignLeft)
        inner.addWidget(_label(analysis.statement))
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
        if analysis.comparison is None:
            self.proposal_label = _label("", "warnings")
            self.proposal_label.setVisible(False)
            inner.addWidget(self.proposal_label)
            self.registration_button = QPushButton(SET_UP_REGISTRATION)
            self.registration_button.setObjectName("analyzeSetUpRegistration")
            self.registration_button.clicked.connect(lambda: self.open_registration())
            inner.addWidget(self.registration_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.result_layout.addWidget(card)

    def _add_table(self, key: str, title: str, headers, rows, stretch: int, hint: str = "") -> None:
        page = QWidget()
        inner = QVBoxLayout(page)
        inner.setContentsMargins(0, 8, 0, 0)
        inner.setSpacing(8)
        for text, name in ((title, "sectionTitle"), (hint, "hint")):
            if text:
                inner.addWidget(_label(text, name))
        table = _ResultTable(headers, rows, stretch)
        self.tables[key] = table
        inner.addWidget(table)
        inner.addStretch(1)
        self.result_tabs.addTab(page, TAB_TITLES[key])

    def _add_comparison(self, view) -> None:
        pairs = tuple(tuple(row.cells[i] for i in am.PAIR_COLUMNS) for row in view.pair_rows)
        if pairs:
            self._add_table("pairs", "", am.PAIR_HEADERS, pairs, 7)
        else:
            card, inner = _card()
            inner.addWidget(_label(cm.NO_PAIR_TEXT, "hint"))
            self.result_layout.insertWidget(self.result_layout.count() - 1, card)
        if view.mac_cells:
            headers = ("FE \\ EXP",) + tuple(str(mode) for mode in view.mac_experimental_modes)
            rows = tuple((str(mode),) + tuple(cells) for mode, cells in zip(view.mac_fe_modes, view.mac_cells))
            self._add_table("mac", "", headers, rows, 0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        need = sum(panel.minimumSizeHint().width() for panel in self.shape_panels.values()) + 12
        self.shapes_layout.setDirection(QBoxLayout.Direction.TopToBottom
                                        if event.size().width() < max(SIDE_BY_SIDE_WIDTH, need)
                                        else QBoxLayout.Direction.LeftToRight)

    def busy(self) -> bool:
        return (self.state == RUNNING or any(thread.is_alive() for thread in self._threads)
                or any(panel.busy() for panel in self.shape_panels.values())
                or (self.registration_dialog is not None and self.registration_dialog.busy()))

    def shutdown(self) -> None:
        self._stop()
        self.state = IDLE
        self._close_registration()
        for panel in self.shape_panels.values():
            panel.cancel()


__all__ = ["AnalyzePanel", "SUBTITLE", "TITLE"]
