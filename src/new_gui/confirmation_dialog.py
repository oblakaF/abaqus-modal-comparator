"""UNIVERSAL-REG-3: the separate confirmation step of a revalidated registration draft (PySide6).

Everything the confirmation covers is displayed: the evidence, the axes, the measured side, the DOFs, the point mapping,
the provenance and the exact sources. Each physical statement is confirmed on its own and the person is named. An
existing confirmation is displayed the same way, already checked against the current files, and is used only on command.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from new_gui import analyze_model as am
from new_gui.diagnostic_panel import DiagnosticTable
from services import confirmed_registration as cs

TITLE = "Confirm physical registration"
CONFIRM_AND_SAVE = "Confirm and save..."
USE = "Use for comparison"
FILTER = "Registration confirmation (*.json);;All files (*)"
INTRO = "Read every value below against your physical records. You are stating that they are correct."
MAPPING_HEADERS = ("Experimental point", "FE node", "Distance", "Landmark")
NEED_ALL = "Confirm every statement, and give your name and where the evidence is kept."


def _text(text: str = "", name: str = "") -> QLabel:
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    label.setMinimumWidth(0)
    return label


def facts_of(draft: dict) -> tuple:
    """(section title, lines) of everything a confirmation covers, in reading order."""
    evidence, result, sources = draft["evidence"], draft["result"], draft["sources"]
    axes = ", ".join(f"+{name} → {text or 'not stated'}" for name, text in zip("xyz", evidence["axes"]))
    resulting = ", ".join(f"+{name} → {text}" for name, text in zip("xyz", result["axes_in_fe"]))
    landmarks = [f"Experimental point {point} = FE node {node}" for point, node in evidence["landmarks"]]
    modal = draft["modal_set"]
    return (("Physical evidence", (f"Units: FE {evidence['fe_unit']}, experimental {evidence['experimental_unit']}",
                                   f"Stated axes: {axes}", f"Resulting axes: {resulting}",
                                   f"Measured side (FE): {evidence['measured_side']}",
                                   f"Measured FE part: {evidence['measured_instance'] or 'the only one'}",
                                   f"Measured DOFs: {', '.join(evidence['measured_dofs'])}")),
            ("Landmarks", tuple(landmarks)),
            ("Provenance", (f"Evidence source: {evidence['source']}",)),
            ("Exact data", (f"Modal set: {modal['display_name']} ({modal['key']}), {modal['record_count']} records",
                            f"Experimental file SHA-256: {sources['experimental']['sha256']}",
                            f"FE package SHA-256: {sources['fe']['package_sha256']}",
                            f"FE geometry SHA-256: {draft['fe_geometry_sha256']}",
                            f"Experimental geometry SHA-256: {draft['experimental_geometry_sha256']}")),
            ("Warnings", tuple(result["warnings"]) or ("None.",)),
            ("Checks", tuple(result["checks"])))


class _Bridge(QObject):
    done = Signal(int, object)


class ConfirmationDialog(QDialog):
    """With ``existing`` it displays that confirmation; otherwise it asks for a new one of ``draft``."""

    confirmed = Signal(object)

    def __init__(self, inputs: am.Inputs, set_index: int, draft: dict, draft_path, parent: Optional[QWidget] = None,
                 existing: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        self.inputs, self.set_index, self.draft_path, self.existing = inputs, set_index, draft_path, existing
        self.document: Optional[dict] = existing
        self._token = 0
        self._cancel: Optional[threading.Event] = None
        self._threads: list[threading.Thread] = []
        self._bridge = _Bridge(self)
        self._bridge.done.connect(self._done)
        self.boxes: dict = {}
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
        layout.addWidget(_text(INTRO))
        layout.addWidget(_text("\n".join(cs.LIMITS), "warnings"))
        for title, lines in facts_of(draft):
            heading = _text(title, "sectionTitle")
            layout.addWidget(heading)
            layout.addWidget(_text("\n".join(lines), "hint"))
        layout.addWidget(_text("Point mapping", "sectionTitle"))
        rows = tuple((row[0], row[1], f"{row[2]:.4g}", "yes" if row[3] else "") for row in draft["result"]["mapping"])
        self.table = DiagnosticTable(MAPPING_HEADERS, rows, 1, text_columns=(0, 1, 3))
        self.table.setObjectName("confirmMapping")
        layout.addWidget(self.table)
        layout.addWidget(_text(draft["limit"]))
        layout.addWidget(_text(gr_note(draft), "hint"))
        self.message = _text("", "hint")
        self.message.setVisible(False)
        if existing is None:
            self._build_form(layout)
        else:
            layout.addWidget(_text(f"Confirmed by {existing['confirmed_by']} on {existing['confirmed_at']}. Evidence "
                                   f"kept at: {existing['evidence_location']}."))
            self.action = QPushButton(USE)
            self.action.clicked.connect(self.use_existing)
        layout.addWidget(self.message)
        row = QHBoxLayout()
        self.action.setObjectName("primary")
        row.addWidget(self.action)
        close = QPushButton("Cancel")
        close.clicked.connect(self.close)
        row.addWidget(close)
        row.addStretch(1)
        layout.addLayout(row)
        self.resize(720, 680)

    def _build_form(self, layout: QVBoxLayout) -> None:
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(separator)
        for key, text in cs.STATEMENTS:
            box = QCheckBox(text)
            box.setObjectName(f"confirm_{key}")
            box.toggled.connect(self._refresh)
            self.boxes[key] = box
            layout.addWidget(box)
        self.name = QLineEdit()
        self.name.setObjectName("confirmName")
        self.name.setPlaceholderText("Your name")
        self.name.textChanged.connect(self._refresh)
        layout.addWidget(self.name)
        self.location = QLineEdit()
        self.location.setObjectName("confirmLocation")
        self.location.setPlaceholderText("Where the physical evidence is kept")
        self.location.textChanged.connect(self._refresh)
        layout.addWidget(self.location)
        self.action = QPushButton(CONFIRM_AND_SAVE)
        self.action.clicked.connect(lambda: self.confirm())
        self._refresh()

    def ready(self) -> bool:
        return (all(box.isChecked() for box in self.boxes.values()) and bool(self.name.text().strip())
                and bool(self.location.text().strip()) and self._cancel is None)

    def _refresh(self, *_args) -> None:
        self.action.setEnabled(self.ready())

    def _say(self, text: str, name: str = "hint") -> None:
        self.message.setObjectName(name)
        self.message.style().unpolish(self.message)
        self.message.style().polish(self.message)
        self.message.setText(text)
        self.message.setVisible(bool(text))

    def confirm(self, path: Optional[str] = None) -> bool:
        """Revalidate the draft on the current files, then write the confirmation to its own file."""
        if not self.ready():
            self._say(NEED_ALL, "error")
            return False
        if path is None:
            path, _filter = QFileDialog.getSaveFileName(self, CONFIRM_AND_SAVE, "registration_confirmation.json", FILTER)
        if not path:
            return False
        inputs, set_index, draft_path = self.inputs, self.set_index, self.draft_path
        name, location, statements = self.name.text(), self.location.text(), tuple(self.boxes)
        self._token += 1
        self._cancel = threading.Event()
        token, cancel, bridge = self._token, self._cancel, self._bridge

        def work() -> None:
            try:
                value = am.confirm_registration(inputs, set_index, draft_path, name, location, statements, path, cancel)
            except Exception as error:  # noqa: BLE001  (a message, never a crash of the window)
                value = error
            try:
                bridge.done.emit(token, value)
            except RuntimeError:
                pass

        worker = threading.Thread(target=work, name="new-gui-confirmation", daemon=True)
        self._threads = [thread for thread in self._threads if thread.is_alive()] + [worker]
        worker.start()
        self.action.setEnabled(False)
        self._say("Checking the draft against the current files...")
        return True

    def _done(self, token: int, value) -> None:
        if token != self._token:
            return
        self._cancel = None
        self._refresh()
        if isinstance(value, Exception):
            self._say(str(value), "error")
            return
        self.document = value
        self._say("Saved. The confirmation records your statement; it is not proof of physical correctness.")
        self.confirmed.emit(value)

    def use_existing(self) -> None:
        self.confirmed.emit(self.existing)

    def busy(self) -> bool:
        return self._cancel is not None or any(thread.is_alive() for thread in self._threads)

    def closeEvent(self, event) -> None:
        if self._cancel is not None:
            self._cancel.set()
        self._cancel = None
        self._token += 1
        super().closeEvent(event)


def gr_note(draft: dict) -> str:
    rows = draft["provisional_heuristics"]
    named = ", ".join(f"{row['name'].replace('_', ' ')} {row['value']:g}" for row in rows)
    return f"Provisional diagnostic heuristics, not approved scientific gates: {named}."


__all__ = ["ConfirmationDialog", "TITLE", "facts_of"]
