"""UNIVERSAL-REG-1: the Set up registration dialog of the Analyze page (PySide6).

The user states the physical evidence; the check runs in a worker thread (``analyze_model.propose_registration``) and
the dialog shows the proposed mapping and every failure. Nothing is prefilled, and the result is diagnostic only.
"""

from __future__ import annotations

import threading
from typing import Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from new_gui import analyze_model as am
from new_gui.diagnostic_panel import DiagnosticTable
from services import generic_registration as gr

TITLE = "Set up registration"
NOT_STATED = "not stated"
CHOOSE = "Choose..."
CHECK = "Check evidence"
CHECKING = "Checking the evidence..."
LANDMARK_HINT = "One per line: experimental point, FE node"
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
        else:
            bad.append(line.strip())
    return tuple(pairs), tuple(bad)


class _Bridge(QObject):
    done = Signal(int, object)


class RegistrationDialog(QDialog):
    """``checked`` carries each finished proposal, for the page's summary."""

    checked = Signal(object)

    def __init__(self, inputs: am.Inputs, set_index: int, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        self.inputs, self.set_index = inputs, set_index
        self.proposal: Optional[gr.Proposal] = None
        self.table: Optional[DiagnosticTable] = None
        self._token = 0
        self._cancel: Optional[threading.Event] = None
        self._threads: list[threading.Thread] = []
        self._bridge = _Bridge(self)
        self._bridge.done.connect(self._done)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        area = QScrollArea()
        area.setWidgetResizable(True)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        area.setWidget(page)
        outer.addWidget(area)
        layout.addWidget(_text("State what you know from the part and the test, not from any modal result.", "hint"))
        layout.addWidget(_text("\n".join(am.registration_geometry(inputs, set_index)), "hint"))
        layout.addLayout(self._build_form())
        row = QHBoxLayout()
        self.check_button = QPushButton(CHECK)
        self.check_button.setObjectName("primary")
        self.check_button.clicked.connect(self.check)
        row.addWidget(self.check_button)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        row.addWidget(close)
        row.addStretch(1)
        layout.addLayout(row)
        self.busy_label = _text(CHECKING, "hint")
        self.busy_label.setVisible(False)
        layout.addWidget(self.busy_label)
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
        self.resize(640, 640)

    def _build_form(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setColumnStretch(1, 1)
        self.fe_unit = _combo(gr.UNITS, "regFeUnit", CHOOSE)
        self.experimental_unit = _combo(gr.UNITS, "regExperimentalUnit", CHOOSE)
        self.axes = tuple(_combo(gr.DIRECTIONS, f"regAxis{name}", NOT_STATED) for name in "xyz")
        self.side = _combo(gr.DIRECTIONS, "regSide", CHOOSE)
        self.dofs = {name: QCheckBox(name) for name in gr.DOFS}
        self.landmarks = QPlainTextEdit()
        self.landmarks.setObjectName("regLandmarks")
        self.landmarks.setPlaceholderText(LANDMARK_HINT)
        self.landmarks.setFixedHeight(84)
        self.source = QLineEdit()
        self.source.setObjectName("regSource")
        self.source.setPlaceholderText("For example: marker photograph, measurement drawing")
        units = QHBoxLayout()
        for caption, combo in (("FE", self.fe_unit), ("Experimental", self.experimental_unit)):
            units.addWidget(QLabel(caption))
            units.addWidget(combo)
        units.addStretch(1)
        axes = QHBoxLayout()
        for name, combo in zip("xyz", self.axes):
            axes.addWidget(QLabel(f"+{name}"))
            axes.addWidget(combo)
        axes.addStretch(1)
        dofs = QHBoxLayout()
        for box in self.dofs.values():
            dofs.addWidget(box)
        dofs.addStretch(1)
        for row, (caption, item) in enumerate((("Units", units), ("Experimental axes in FE", axes),
                                               ("Measured side (FE)", self.side), ("Measured DOFs", dofs),
                                               ("Landmarks", self.landmarks), ("Evidence source", self.source))):
            grid.addWidget(QLabel(caption), row, 0, Qt.AlignmentFlag.AlignTop)
            if isinstance(item, QWidget):
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
                           landmarks=pairs, source=self.source.text().strip()), bad

    def check(self) -> bool:
        """Check the stated evidence in a worker thread; a newer check or a closed dialog discards this one."""
        if self.busy():
            return False
        evidence, bad = self.evidence()
        if bad:
            problem = gr.Problem(gr.LANDMARK, f"These landmark lines are not a pair: {'; '.join(bad)}.")
            self._show(gr.required([problem], evidence=evidence))
            return False
        self._token += 1
        self._cancel = threading.Event()
        token, cancel, inputs, set_index, bridge = self._token, self._cancel, self.inputs, self.set_index, self._bridge

        def work() -> None:
            try:
                value = am.propose_registration(inputs, set_index, evidence, cancel)
            except am.StepCancelled:
                value = None
            except Exception as error:  # noqa: BLE001  (a message, never a crash of the window)
                reason = f"The check could not be completed ({type(error).__name__}: {error})."
                value = gr.required([gr.Problem(gr.GEOMETRY, reason)], evidence=evidence)
            try:
                bridge.done.emit(token, value)
            except RuntimeError:
                pass

        worker = threading.Thread(target=work, name="new-gui-registration", daemon=True)
        self._threads = [thread for thread in self._threads if thread.is_alive()] + [worker]
        worker.start()
        self.check_button.setEnabled(False)
        self.busy_label.setVisible(True)
        return True

    def _done(self, token: int, proposal) -> None:
        if token != self._token:
            return
        self._cancel = None
        self.check_button.setEnabled(True)
        self.busy_label.setVisible(False)
        if proposal is not None:
            self._show(proposal)

    def _show(self, proposal: gr.Proposal) -> None:
        self.proposal = proposal
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
        self.problem_label = None
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
        if proposal.mapping:
            rows = tuple((p.experimental_point, p.fe_node, f"{p.distance:.4g}", "yes" if p.landmark else "")
                         for p in proposal.mapping)
            self.table = DiagnosticTable(MAPPING_HEADERS, rows, 1, text_columns=(0, 1, 3))
            self.table.setObjectName("regMapping")
            self.result_layout.addWidget(self.table)
        self.result.setVisible(True)
        self.checked.emit(proposal)

    def busy(self) -> bool:
        return self._cancel is not None or any(thread.is_alive() for thread in self._threads)

    def stop(self) -> None:
        if self._cancel is not None:
            self._cancel.set()
        self._cancel = None
        self._token += 1
        self.check_button.setEnabled(True)
        self.busy_label.setVisible(False)

    def closeEvent(self, event) -> None:
        self.stop()
        super().closeEvent(event)


__all__ = ["RegistrationDialog", "TITLE", "parse_landmarks"]
