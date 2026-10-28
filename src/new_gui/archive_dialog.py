"""NEW-GUI.1: the research archive, opened only by the user's explicit command; read-only.

The dialog lists the archive's specimen records (``services.specimen_catalog_view``) and shows the passport of the
record the user picks. No record is picked when it opens. It has no action that changes the workspace: it does not
choose a file, transfer a registration or assign a modal status. A missing or damaged archive is shown as a
problem text; the program goes on working.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem, QSplitter,
                               QTextBrowser, QVBoxLayout, QWidget)

from new_gui.workspace_state import ARCHIVE_NOTE, ArchiveListing, load_archive
from services import specimen_catalog_view as catalog

TITLE = "Research archive (read-only)"
UNKNOWN_SHOWN = "Unknown"
PICK_TEXT = "Choose a record on the left to read its passport. Nothing is selected for your workspace."
UNAVAILABLE = "The research archive is not available: {problem}. The rest of the program works without it."


def _shown(text: str) -> str:
    """Escaped for rich text; the catalogue service's bilingual unknown marker is shown in English (the interface is
    English only; the service and the archive are unchanged)."""
    return html.escape(text.replace(catalog.UNKNOWN_TEXT, UNKNOWN_SHOWN))


def passport_html(listing: ArchiveListing, specimen_id: str) -> str:
    parts = []
    for section in listing.passport(specimen_id):
        rows = "".join(f"<tr><td class='caption' width='30%'>{_shown(caption)}</td><td>{_shown(text)}</td></tr>"
                       for caption, text in section.rows)
        note = f"<p class='note'>{_shown(section.note)}</p>" if section.note else ""
        parts.append(f"<h3>{_shown(section.title)}</h3><table width='100%'>{rows}</table>{note}")
    return ("<style>td{padding:2px 8px 2px 0;vertical-align:top}td.caption{color:#52606d}"
            "p.note{color:#52606d;font-style:italic}</style>" + "".join(parts))


class ArchiveDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None, archive_path: Optional[Path] = None):
        super().__init__(parent)
        self.setObjectName("archiveDialog")
        self.setWindowTitle(TITLE)
        self.listing = load_archive(archive_path)
        layout = QVBoxLayout(self)
        note = QLabel(ARCHIVE_NOTE)
        note.setWordWrap(True)
        note.setObjectName("hint")
        layout.addWidget(note)
        self.problem_label = QLabel()
        self.problem_label.setObjectName("error")
        self.problem_label.setWordWrap(True)
        self.records = QListWidget()
        self.records.setObjectName("archiveRecords")
        self.passport = QTextBrowser()
        self.passport.setObjectName("archivePassport")
        self.passport.setOpenLinks(False)
        if self.listing.problem:
            self.problem_label.setText(UNAVAILABLE.format(problem=self.listing.problem))
            layout.addWidget(self.problem_label)
            layout.addStretch(1)
        else:
            self.problem_label.hide()
            for specimen_id, text in self.listing.records:
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, specimen_id)
                self.records.addItem(item)
            self.records.setCurrentRow(-1)
            self.passport.setPlainText(PICK_TEXT)
            self.records.currentItemChanged.connect(self._show_record)
            splitter = QSplitter(Qt.Orientation.Horizontal)
            splitter.addWidget(self.records)
            splitter.addWidget(self.passport)
            splitter.setStretchFactor(1, 3)
            splitter.setChildrenCollapsible(False)
            layout.addWidget(splitter, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        # The first focus goes to Close: a focused list would make its first record current, i.e. pick one.
        buttons.button(QDialogButtonBox.StandardButton.Close).setFocus()
        self.resize(900, 600)

    @property
    def selected_id(self) -> Optional[str]:
        item = self.records.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _show_record(self, item: Optional[QListWidgetItem], _previous=None) -> None:
        if item is None:
            self.passport.setPlainText(PICK_TEXT)
            return
        self.passport.setHtml(passport_html(self.listing, item.data(Qt.ItemDataRole.UserRole)))
