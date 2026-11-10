"""UNIVERSAL-REG-1: the Set up registration dialog of the Analyze page (PySide6).

The user states the physical evidence; the check runs in a worker thread (``analyze_model.propose_registration``) and
the dialog shows the proposed mapping and every failure. Nothing is prefilled, and the result is diagnostic only.

UNIVERSAL-REG-2: Save draft and Open draft keep and check again a proposal. Saving needs the user's explicit review of
what is on the screen; an opened draft is shown unreviewed. A draft is never an accepted physical registration.

UNIVERSAL-REG-3: Confirm registration... revalidates the saved draft now and only then opens the separate confirmation.

ABM-AUD-3: the form says what is needed and where each statement comes from (the FE model, the experiment, the physical
evidence). A scan turned in its plane by any angle is stated by its out-of-plane axis and three landmarks; a landmark is
an FE node or an FE position. The result shows the rotation, the translation, the unit factor, the landmark consistency
and the extent of the measurement grid against the FE outer dimensions. The dialog never exceeds the screen.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from new_gui import analyze_model as am
from new_gui.confirmation_dialog import ConfirmationDialog
from new_gui.diagnostic_panel import DiagnosticTable
from services import generic_registration as gr

TITLE = "Set up registration"
NOT_STATED = "not stated"
CHOOSE = "Choose..."
CHECK = "Check evidence"
CHECKING = "Checking the evidence..."
SAVE_DRAFT = "Save draft..."
OPEN_DRAFT = "Open draft..."
CONFIRM = "Confirm registration..."
NEED_DRAFT = "Review the mapping and save it as a draft first."
OPENING = "Checking the draft against the current files..."
SAVING = "Saving the draft..."
REVIEW = "I have reviewed this mapping and its evidence."
DRAFT_FILTER = "Registration draft (*.json);;All files (*)"
NOT_ACCEPTED = "A draft is not an accepted physical registration."
REPRODUCED = "This draft was reproduced on the current files. Review it. " + NOT_ACCEPTED
NEED_REVIEW = "Review the mapping and confirm it first."
FORM_CHANGED = "The form changed after the check. Check the evidence again."
LANDMARK_HINT = "One per line: experimental point, FE node   or   experimental point, X, Y, Z (FE position, FE units)"
INTRO = "State what you know from the part and the test, not from any modal result."
NEEDED = ("Needed: the coordinate units of both files, the measured side, the measured DOFs, landmarks and where the "
          "evidence comes from. Nothing is prefilled, and nothing is taken from frequencies or MAC.")
TURNED = ("A flat scan turned in its plane by any angle (for example 45 degrees): state only the experimental axis that "
          "points out of the plane, leave the two in-plane axes not stated, and give at least three landmarks that are "
          "not on one line. The landmarks give the rotation.")
LANDMARK_NOTE = ("A landmark is an experimental point and the place where it physically lies on the FE model: an FE node "
                 "label, or its FE position X, Y, Z in FE units. Measure the place on the part; the outermost scan "
                 "points are usually not on the FE edges.")
SECTIONS = ("FE model", "Experiment", "Physical evidence (from the part and the test set-up)")
SIDE_NOTE = "The FE direction the measured face looks towards."
DOF_NOTE = "The experimental components that were measured."
DETAILS_TITLE = "Transform and coverage"
ACROSS = object()  # a form row that takes both columns
MAPPING_HEADERS = ("Experimental point", "FE node", "Distance", "Landmark")
BADGE_STATE = {gr.REGISTRATION_PROPOSED: "read", gr.REGISTRATION_REQUIRED: "chosen"}


def _text(text: str = "", name: str = "") -> QLabel:
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    label.setMinimumWidth(0)
    return label


class _MappingTable(DiagnosticTable):
    height_cap = 260  # hundreds of points scroll inside the table, so the transform above it stays in reach

    def __init__(self, headers, rows, stretch, **kwargs):
        super().__init__(headers, rows, stretch, **kwargs)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)


def _combo(items, name: str, first: str) -> QComboBox:
    combo = QComboBox()
    combo.setObjectName(name)
    combo.addItem(first, "")
    for item in items:
        combo.addItem(item, item)
    return combo


def parse_landmarks(text: str) -> tuple:
    """(pairs, lines that are not a pair)."""
    pairs, bad = [], []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.replace(";", ",").split(",")]
        if len(parts) == 1:
            parts = line.split()
        if len(parts) == 2 and all(parts):
            pairs.append((parts[0], parts[1]))
            continue
        if len(parts) == 4 and parts[0]:  # a point and its FE position, written x, y, z or (x, y, z)
            try:
                pairs.append((parts[0], gr.position_text(*(float(part.strip("() ")) for part in parts[1:]))))
                continue
            except ValueError:
                pass
        bad.append(line.strip())
    return tuple(pairs), tuple(bad)


def fit_to_screen(dialog: QDialog, width: int, height: int) -> None:
    """The wanted size, never more than the screen offers (a 150 % scale on a small screen leaves little)."""
    screen = dialog.screen() or QGuiApplication.primaryScreen()
    if screen is not None:
        available = screen.availableGeometry()
        width, height = min(width, available.width() - 40), min(height, available.height() - 60)
    dialog.resize(max(width, 320), max(height, 240))


class _Bridge(QObject):
    done = Signal(int, object)


class RegistrationDialog(QDialog):
    """``checked`` carries each finished proposal, ``reviewed`` the user's review of it, for the page's summary."""

    checked = Signal(object)
    reviewed = Signal(bool)
    confirmed = Signal(object)

    def __init__(self, inputs: am.Inputs, set_index: int, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        self.inputs, self.set_index = inputs, set_index
        self.proposal: Optional[gr.Proposal] = None
        self.checked_evidence: Optional[gr.Evidence] = None
        self.table: Optional[DiagnosticTable] = None
        self._handler: Optional[Callable] = None
        self.draft_path: Optional[str] = None  # the draft file that holds the shown proposal
        self.confirmation_dialog: Optional[ConfirmationDialog] = None
        self._token = 0
        self._cancel: Optional[threading.Event] = None
        self._threads: list[threading.Thread] = []
        self._bridge = _Bridge(self)
        self._bridge.done.connect(self._done)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)  # the page wraps; a table scrolls itself
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        area.setWidget(page)
        outer.addWidget(area)
        layout.addWidget(_text(INTRO, "hint"))
        self.needed_label = _text(NEEDED, "hint")
        layout.addWidget(self.needed_label)
        layout.addWidget(_text("\n".join(am.registration_geometry(inputs, set_index)), "hint"))
        layout.addLayout(self._build_form())
        row, second = QHBoxLayout(), QHBoxLayout()  # two short rows: five commands in one do not fit a small window
        self.check_button = QPushButton(CHECK)
        self.check_button.setObjectName("primary")
        self.check_button.clicked.connect(self.check)
        row.addWidget(self.check_button)
        self.open_button = QPushButton(OPEN_DRAFT)
        self.open_button.setObjectName("regOpenDraft")
        self.open_button.clicked.connect(lambda: self.open_draft())
        row.addWidget(self.open_button)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        row.addWidget(close)
        row.addStretch(1)
        self.save_button = QPushButton(SAVE_DRAFT)
        self.save_button.setObjectName("regSaveDraft")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(lambda: self.save_draft())
        second.addWidget(self.save_button)
        self.confirm_button = QPushButton(CONFIRM)
        self.confirm_button.setObjectName("regConfirm")
        self.confirm_button.setEnabled(False)
        self.confirm_button.clicked.connect(lambda: self.confirm_registration())
        second.addWidget(self.confirm_button)
        second.addStretch(1)
        layout.addLayout(row)
        layout.addLayout(second)
        self.busy_label = _text(CHECKING, "hint")
        self.busy_label.setVisible(False)
        layout.addWidget(self.busy_label)
        self.draft_note = _text("", "hint")
        self.draft_note.setVisible(False)
        layout.addWidget(self.draft_note)
        self.result = QFrame()
        self.result.setObjectName("card")
        self.result_layout = QVBoxLayout(self.result)
        self.result_layout.setContentsMargins(12, 10, 12, 10)
        self.result_layout.setSpacing(6)
        self.result.setVisible(False)
        layout.addWidget(self.result)
        layout.addStretch(1)
        self.status_label: Optional[QLabel] = None
        self.problem_label: Optional[QLabel] = None
        self.details_label: Optional[QLabel] = None
        self.review_box: Optional[QCheckBox] = None
        fit_to_screen(self, 700, 700)

    def _build_form(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setColumnStretch(1, 1)
        self.fe_unit = _combo(gr.UNITS, "regFeUnit", CHOOSE)
        self.experimental_unit = _combo(gr.UNITS, "regExperimentalUnit", CHOOSE)
        self.axes = tuple(_combo(gr.DIRECTIONS, f"regAxis{name}", NOT_STATED) for name in "xyz")
        self.side = _combo(gr.DIRECTIONS, "regSide", CHOOSE)
        instances = am.registration_instances(self.inputs)
        self.instance = _combo(instances if len(instances) > 1 else (), "regInstance", CHOOSE)
        self.instance.setVisible(len(instances) > 1)
        self.instance_caption = QLabel("Measured FE part")
        self.instance_caption.setVisible(len(instances) > 1)
        self.dofs = {name: QCheckBox(name) for name in gr.DOFS}
        self.landmarks = QPlainTextEdit()
        self.landmarks.setObjectName("regLandmarks")
        self.landmarks.setPlaceholderText(LANDMARK_HINT)
        self.landmarks.setFixedHeight(84)
        self.source = QLineEdit()
        self.source.setObjectName("regSource")
        self.source.setPlaceholderText("For example: marker photograph, measurement drawing")
        self.turned_label = _text(TURNED, "hint")
        self.landmark_label = _text(LANDMARK_NOTE, "hint")
        axes = QHBoxLayout()
        for name, combo in zip("xyz", self.axes):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
            axes.addWidget(QLabel(f"+{name}"))
            axes.addWidget(combo)
        axes.addStretch(1)
        dofs = QHBoxLayout()
        for box in self.dofs.values():
            dofs.addWidget(box)
        dofs.addStretch(1)
        fe_title, experiment_title, evidence_title = (_text(title, "sectionTitle") for title in SECTIONS)
        rows = ((fe_title, None), ("Coordinate unit", self.fe_unit),
                ("Measured side", self.side), (None, _text(SIDE_NOTE, "hint")),
                (self.instance_caption, self.instance),
                (experiment_title, None), ("Coordinate unit", self.experimental_unit),
                ("Measured DOFs", dofs), (None, _text(DOF_NOTE, "hint")),
                (evidence_title, None), (QLabel("Experimental axes in FE"), None), (ACROSS, axes),
                (ACROSS, self.turned_label),
                ("Landmarks", self.landmarks), (None, self.landmark_label), ("Evidence source", self.source))
        for row, (caption, item) in enumerate(rows):
            if item is None:  # a section title across the form
                grid.addWidget(caption, row, 0, 1, 2)
                continue
            if caption is ACROSS:  # three choices side by side need the whole width
                if isinstance(item, QWidget):
                    grid.addWidget(item, row, 0, 1, 2)
                else:
                    grid.addLayout(item, row, 0, 1, 2)
                continue
            if caption is not None:  # short, on one line: the explanation is the hint under the field
                label = caption if isinstance(caption, QLabel) else QLabel(caption)
                grid.addWidget(label, row, 0, Qt.AlignmentFlag.AlignTop)
            if isinstance(item, QWidget):
                if isinstance(item, QComboBox):
                    grid.addWidget(item, row, 1, Qt.AlignmentFlag.AlignLeft)
                else:
                    grid.addWidget(item, row, 1)
            else:
                grid.addLayout(item, row, 1)
        return grid

    def evidence(self) -> tuple:
        """(the stated evidence, landmark lines that could not be read)."""
        pairs, bad = parse_landmarks(self.landmarks.toPlainText())
        return gr.Evidence(fe_unit=self.fe_unit.currentData(), experimental_unit=self.experimental_unit.currentData(),
                           axes=tuple(combo.currentData() for combo in self.axes),
                           measured_side=self.side.currentData(),
                           measured_dofs=tuple(name for name, box in self.dofs.items() if box.isChecked()),
                           landmarks=pairs, source=self.source.text().strip(),
                           measured_instance=self.instance.currentData()), bad

    def check(self) -> bool:
        """Check the stated evidence in a worker thread; a newer check or a closed dialog discards this one."""
        if self.busy():
            return False
        evidence, bad = self.evidence()
        if bad:
            problem = gr.Problem(gr.LANDMARK, f"These landmark lines are not a pair: {'; '.join(bad)}.")
            self._show(gr.required([problem], evidence=evidence))
            return False
        inputs, set_index = self.inputs, self.set_index
        self._note("")

        def done(proposal) -> None:
            if proposal is not None:
                self.checked_evidence = evidence
                self._show(proposal)

        def failed(error: Exception):
            reason = f"The check could not be completed ({type(error).__name__}: {error})."
            return gr.required([gr.Problem(gr.GEOMETRY, reason)], evidence=evidence)

        return self._run(CHECKING, lambda cancel: am.propose_registration(inputs, set_index, evidence, cancel), done,
                         failed)

    def _run(self, text: str, work: Callable, handler: Callable, failed: Callable) -> bool:
        """One step in a worker thread; a cancelled step gives None; a newer step or a closed dialog discards it."""
        if self.busy():
            return False
        self._token += 1
        self._cancel = threading.Event()
        self._handler = handler
        token, cancel, bridge = self._token, self._cancel, self._bridge

        def target() -> None:
            try:
                value = work(cancel)
            except am.StepCancelled:
                value = None
            except Exception as error:  # noqa: BLE001  (a message, never a crash of the window)
                value = failed(error)
            try:
                bridge.done.emit(token, value)
            except RuntimeError:
                pass

        worker = threading.Thread(target=target, name="new-gui-registration", daemon=True)
        self._threads = [thread for thread in self._threads if thread.is_alive()] + [worker]
        worker.start()
        for button in (self.check_button, self.save_button, self.open_button, self.confirm_button):
            button.setEnabled(False)
        self.busy_label.setText(text)
        self.busy_label.setVisible(True)
        return True

    def _done(self, token: int, value) -> None:
        if token != self._token:
            return
        self._cancel = None
        self.check_button.setEnabled(True)
        self.open_button.setEnabled(True)
        self.busy_label.setVisible(False)
        self._handler(value)
        self._refresh_save()

    # ---------------------------------------------------------------------------------------------- the draft

    def _note(self, text: str, name: str = "hint") -> None:
        self.draft_note.setObjectName(name)
        self.draft_note.style().unpolish(self.draft_note)
        self.draft_note.style().polish(self.draft_note)
        self.draft_note.setText(text)
        self.draft_note.setVisible(bool(text))

    def is_reviewed(self) -> bool:
        return self.review_box is not None and self.review_box.isChecked()

    def _refresh_save(self) -> None:
        ready = self.proposal is not None and self.proposal.proposed and self.is_reviewed() and self._cancel is None
        self.save_button.setEnabled(ready)
        self.confirm_button.setEnabled(ready and self.draft_path is not None)

    def _review_changed(self, reviewed: bool) -> None:
        self._refresh_save()
        self.reviewed.emit(reviewed)

    def save_draft(self, path: Optional[str] = None) -> bool:
        """Save what was checked and reviewed. Returns False when nothing was started."""
        if self.proposal is None or not self.proposal.proposed or not self.is_reviewed():
            self._note(NEED_REVIEW, "error")
            return False
        evidence, _bad = self.evidence()
        if evidence != self.checked_evidence:
            self._note(FORM_CHANGED, "error")
            return False
        if path is None:
            path, _filter = QFileDialog.getSaveFileName(self, SAVE_DRAFT, "registration_draft.json", DRAFT_FILTER)
        if not path:
            return False
        inputs, set_index, proposal = self.inputs, self.set_index, self.proposal

        def done(saved) -> None:
            if saved is None:
                return
            if isinstance(saved, Exception):
                self._note(str(saved), "error")
            else:
                self.draft_path = str(saved)
                self._note(f"Saved {saved}. {NOT_ACCEPTED}")

        def work(cancel):
            try:
                return am.save_registration_draft(inputs, set_index, evidence, proposal, path, cancel)
            except (gr.DraftRefused, am.StepFailed) as error:
                return error

        return self._run(SAVING, work, done, lambda error: error)

    def open_draft(self, path: Optional[str] = None) -> bool:
        """Check a saved draft against the current files; its evidence fills the form only when it is reproduced."""
        if path is None:
            path, _filter = QFileDialog.getOpenFileName(self, OPEN_DRAFT, "", DRAFT_FILTER)
        if not path:
            return False
        inputs, set_index = self.inputs, self.set_index
        self._note("")

        def done(result) -> None:
            if result is None:
                return
            if result.proposal.proposed:
                self._fill(result.evidence)
                if self.evidence()[0] != result.evidence:
                    problem = gr.Problem(gr.DRAFT_INVALID, "The draft's evidence cannot be shown in this form.")
                    self.checked_evidence = None
                    self._show(gr.required([problem]))
                    return
                self.checked_evidence = result.evidence
                self.draft_path = str(path)
                self._note(REPRODUCED)
            else:
                self.checked_evidence = None
                self.draft_path = None
            self._show(result.proposal)

        def failed(error: Exception):
            problem = gr.Problem(gr.DRAFT_INVALID, f"The draft could not be checked ({type(error).__name__}: {error}).")
            return gr.DraftResult(gr.required([problem]))

        return self._run(OPENING, lambda cancel: am.open_registration_draft(inputs, set_index, path, cancel), done,
                         failed)

    def confirm_registration(self) -> bool:
        """Revalidate the saved draft now; only a reproduced one, unchanged on the form, opens the confirmation."""
        if self.proposal is None or not self.proposal.proposed or not self.is_reviewed() or self.draft_path is None:
            self._note(NEED_DRAFT, "error")
            return False
        evidence, _bad = self.evidence()
        if evidence != self.checked_evidence:
            self._note(FORM_CHANGED, "error")
            return False
        inputs, set_index, path = self.inputs, self.set_index, self.draft_path
        self._note("")

        def done(result) -> None:
            if result is None:
                return
            if not result.proposal.proposed or result.evidence != evidence:
                self.draft_path = None
                self.checked_evidence = None
                self._show(result.proposal if not result.proposal.proposed else gr.required(
                    [gr.Problem(gr.DRAFT_NOT_REPRODUCED, "The saved draft is not the evidence on this form.")]))
                return
            self.confirmation_dialog = ConfirmationDialog(inputs, set_index, result.document, path, self)
            self.confirmation_dialog.confirmed.connect(self.confirmed)
            self.confirmation_dialog.show()

        def failed(error: Exception):
            problem = gr.Problem(gr.DRAFT_INVALID, f"The draft could not be checked ({type(error).__name__}: {error}).")
            return gr.DraftResult(gr.required([problem]))

        return self._run(OPENING, lambda cancel: am.open_registration_draft(inputs, set_index, path, cancel), done,
                         failed)

    def _fill(self, evidence: gr.Evidence) -> None:
        for combo, value in ((self.fe_unit, evidence.fe_unit), (self.experimental_unit, evidence.experimental_unit),
                             (self.side, evidence.measured_side), (self.instance, evidence.measured_instance)):
            combo.setCurrentIndex(combo.findData(value))
        for combo, value in zip(self.axes, evidence.axes):
            combo.setCurrentIndex(combo.findData(value))
        for name, box in self.dofs.items():
            box.setChecked(name in evidence.measured_dofs)
        self.landmarks.setPlainText("\n".join(f"{point}, {node}" for point, node in evidence.landmarks))
        self.source.setText(evidence.source)

    def _show(self, proposal: gr.Proposal) -> None:
        self.proposal = proposal
        self.review_box = None  # a new result is unreviewed
        while self.result_layout.count():
            widget = self.result_layout.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.table = None
        self.status_label = QLabel(proposal.status)
        self.status_label.setObjectName("badge")
        self.status_label.setProperty("state", BADGE_STATE[proposal.status])
        self.result_layout.addWidget(self.status_label, 0, Qt.AlignmentFlag.AlignLeft)
        self.result_layout.addWidget(_text(proposal.limit))
        self.result_layout.addWidget(_text(proposal.heuristics_note, "hint"))
        self.problem_label = None
        self.details_label = None
        if proposal.problems:
            self.problem_label = _text("\n".join(f"• {problem.text}" for problem in proposal.problems), "error")
            self.result_layout.addWidget(self.problem_label)
        if proposal.warnings:
            self.result_layout.addWidget(_text("\n".join(f"• {text}" for text in proposal.warnings), "warnings"))
        if proposal.checks:
            self.result_layout.addWidget(_text("\n".join(proposal.checks), "hint"))
        if proposal.axes_in_fe:
            axes = ", ".join(f"+{name} → {text}" for name, text in zip("xyz", proposal.axes_in_fe))
            self.result_layout.addWidget(_text(f"Experimental axes in FE: {axes}."))
        if proposal.details:
            self.result_layout.addWidget(_text(DETAILS_TITLE, "sectionTitle"))
            self.details_label = _text("\n".join(proposal.details))
            self.details_label.setObjectName("regDetails")
            self.result_layout.addWidget(self.details_label)
        if proposal.mapping:
            rows = tuple((p.experimental_point, p.fe_node, f"{p.distance:.4g}", "yes" if p.landmark else "")
                         for p in proposal.mapping)
            self.table = _MappingTable(MAPPING_HEADERS, rows, 1, text_columns=(0, 1, 3))
            self.table.setObjectName("regMapping")
            self.result_layout.addWidget(self.table)
        if proposal.proposed:
            self.review_box = QCheckBox(REVIEW)
            self.review_box.setObjectName("regReview")
            self.review_box.toggled.connect(self._review_changed)
            self.result_layout.addWidget(self.review_box)
        self.result.setVisible(True)
        self._refresh_save()
        self.checked.emit(proposal)

    def busy(self) -> bool:
        return (self._cancel is not None or any(thread.is_alive() for thread in self._threads)
                or (self.confirmation_dialog is not None and self.confirmation_dialog.busy()))

    def stop(self) -> None:
        if self._cancel is not None:
            self._cancel.set()
        self._cancel = None
        self._token += 1
        self.check_button.setEnabled(True)
        self.open_button.setEnabled(True)
        self.busy_label.setVisible(False)

    def closeEvent(self, event) -> None:
        self.stop()
        if self.confirmation_dialog is not None:
            self.confirmation_dialog.close()
        super().closeEvent(event)


__all__ = ["RegistrationDialog", "TITLE", "fit_to_screen", "parse_landmarks"]
