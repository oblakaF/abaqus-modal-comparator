"""NEW-GUI.6: the dialog that offers the known new experimental working sources (PySide6).

It lists the three declared sources the provenance map confirms (``new_gui.known_sources``), with whether each file
is on this computer. Nothing is read until the user chooses one: then its size and fresh SHA-256 are checked, and only
its path is put into the experimental file of the workspace (the user still clicks Inspect file). Without the local
folder the dialog says so, and choosing one's own file works as before.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem, QSizePolicy,
                               QVBoxLayout)

from new_gui import known_sources as ks


def _label(text: str, name: str = "") -> QLabel:
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    label.setMinimumWidth(0)
    return label


class KnownSourcesDialog(QDialog):
    """Choose one known source; ``chosen_path`` holds the verified path after Use this file."""

    def __init__(self, parent=None, root: Optional[Path] = None, provenance: Optional[Path] = None):
        super().__init__(parent)
        self.setWindowTitle(ks.TITLE)
        self.root = Path(root) if root is not None else ks.DEFAULT_ROOT
        self.chosen_path: Optional[Path] = None
        self.entries: list = []
        layout = QVBoxLayout(self)
        layout.addWidget(_label(ks.TITLE, "cardTitle"))
        layout.addWidget(_label(ks.NOTE, "hint"))
        layout.addWidget(_label(f"Folder: {self.root}", "hint"))
        self.list = QListWidget()
        self.list.setObjectName("knownSources")
        self.list.setWordWrap(True)
        layout.addWidget(self.list, 1)
        self.message = _label("", "error")
        layout.addWidget(self.message)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.use_button = self.buttons.addButton("Use this file", QDialogButtonBox.ButtonRole.AcceptRole)
        self.use_button.setObjectName("useKnownSource")
        self.buttons.accepted.connect(self.use_selected)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        try:
            sources = ks.confirmed_sources(provenance or ks.PROVENANCE)
        except (OSError, ValueError, KeyError) as error:
            sources = ()
            self.message.setText(f"The provenance map does not confirm the known sources: {error}")
        for source in sources:
            found = ks.availability(source, self.root)
            self.entries.append(found)
            item = QListWidgetItem(f"{source.title}\n{source.series_id} · {source.modal_set_type}\n"
                                   f"{Path(source.relative_path).name}\n{found.text}\n{source.fe_note}")
            if found.state != ks.AVAILABLE:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled & ~Qt.ItemFlag.ItemIsSelectable)
            self.list.addItem(item)
        if sources and not any(entry.state == ks.AVAILABLE for entry in self.entries):
            self.message.setText("None of the known sources is on this computer. Choose your own file with Choose "
                                 "file... as before.")
        self.list.itemSelectionChanged.connect(self._selection)
        self._selection()
        self.resize(640, 520)

    def _selection(self) -> None:
        row = self.list.currentRow()
        self.use_button.setEnabled(0 <= row < len(self.entries) and self.list.item(row).isSelected()
                                   and self.entries[row].state == ks.AVAILABLE)

    def use_selected(self) -> bool:
        row = self.list.currentRow()
        if not 0 <= row < len(self.entries):
            return False
        try:
            self.chosen_path = ks.verify(self.entries[row].source, self.root)
        except (OSError, ks.ProvenanceMismatch) as error:
            self.message.setText(str(error))
            return False
        self.accept()
        return True


__all__ = ["KnownSourcesDialog"]
