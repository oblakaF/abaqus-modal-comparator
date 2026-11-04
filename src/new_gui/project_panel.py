"""WORKING-DRAFT-R2: one side's saved shape pictures in an opened project (PySide6).

The pictures come only from the project file, in the one component they were saved with. Nothing is drawn or read, and
each picture stays on its own coordinates, as when it was saved.
"""

from __future__ import annotations

from typing import Mapping, Optional

from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout

from new_gui.shape_panel import ImageView, _combo, _label
from new_gui.workspace_state import FE, KIND_TITLE

SAVED_NOTE = "Saved picture of the magnitude, on its own coordinates. Not drawn again and not checked against the files."


class SavedShapePanel(QFrame):
    """A list of the saved modes or records and the chosen one's picture; hidden until a project is shown."""

    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind
        self.setObjectName("card")
        self.entries: tuple = ()
        self.images: Mapping[str, bytes] = {}
        self.shown_number: Optional[str] = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addWidget(_label(f"{KIND_TITLE[kind]}: saved {'mode' if kind == FE else 'record'} shape", "cardTitle"))
        row = QHBoxLayout()
        row.addWidget(QLabel("Mode" if kind == FE else "Record"))
        self.item_combo: QComboBox = _combo("savedModeChoice" if kind == FE else "savedRecordChoice")
        self.item_combo.setMinimumContentsLength(6)
        self.item_combo.currentIndexChanged.connect(self._show_current)
        row.addWidget(self.item_combo, 1)
        layout.addLayout(row)
        self.status = _label("", "error")
        layout.addWidget(self.status)
        self.image = ImageView()
        layout.addWidget(self.image)
        layout.addWidget(_label(SAVED_NOTE, "hint"))
        self.setVisible(False)

    def set_entries(self, entries, images: Mapping[str, bytes]) -> None:
        self.entries, self.images = tuple(entries), images
        self.item_combo.blockSignals(True)
        self.item_combo.clear()
        for entry in self.entries:
            self.item_combo.addItem(entry["label"], entry["number"])
        self.item_combo.blockSignals(False)
        self.setVisible(bool(self.entries))
        self.shown_number = None
        self.image.clear_image()
        self.status.setVisible(False)
        if self.entries:
            self._show_current()

    def show_number(self, number: str) -> bool:
        """Show the saved picture of this mode (as the tables name it); False when the project holds none."""
        row = self.item_combo.findData(number)
        if row < 0:
            return False
        if row == self.item_combo.currentIndex():
            self._show_current()
        else:
            self.item_combo.setCurrentIndex(row)
        return self.image.source is not None

    def _show_current(self) -> None:
        row = self.item_combo.currentIndex()
        if not 0 <= row < len(self.entries):
            return
        entry = self.entries[row]
        self.shown_number = entry["number"]
        data = self.images.get(entry["image"]) if entry["image"] else None
        problem = entry["refusal"] or ("" if data else "No picture was saved.")
        if data and not self.image.set_image(data):
            problem = "The saved picture could not be read."
        if problem:
            self.image.clear_image()
        self.status.setText(f"No saved shape: {problem}" if problem else "")
        self.status.setVisible(bool(problem))
