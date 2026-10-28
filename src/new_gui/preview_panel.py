"""NEW-GUI.2: the panel that shows what was read from one chosen file (PySide6).

It shows the state of a ``new_gui.preview_model.InspectSlot``: not read, reading, the read preview (its facts, one
table per FE package or experimental modal set, and the importer's warnings), or why the file could not be read.
The tables are read-only and nothing in them can be selected: the panel chooses no set and no mode.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QGridLayout, QHeaderView, QLabel, QLineEdit, QSizePolicy,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from new_gui.preview_model import (FAILED, IDLE, NOT_INSPECTED, READ, READING, STATE_TEXT, InspectSlot, PREVIEW_NOTE,
                                   Section, view_of)
from new_gui.workspace_state import KIND_TITLE

STATUS_COLUMN = 2  # the experimental status (and the FE frequency source) gets the free width


def _label(text: str = "", name: str = "") -> QLabel:
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def section_table(section: Section) -> QTableWidget:
    """A read-only table of one section, as tall as its rows (the page scrolls, not the table)."""
    table = QTableWidget(len(section.rows), len(section.headers))
    table.setObjectName("previewTable")
    table.setHorizontalHeaderLabels(list(section.headers))
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    table.verticalHeader().setVisible(False)
    table.setWordWrap(False)
    table.setTextElideMode(Qt.TextElideMode.ElideRight)  # the whole text is in the cell's tooltip
    for row, values in enumerate(section.rows):
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setToolTip(value)
            if column != STATUS_COLUMN:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row, column, item)
    header = table.horizontalHeader()
    for column in range(len(section.headers)):
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch if column == STATUS_COLUMN
                                    else QHeaderView.ResizeMode.ResizeToContents)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    table.resizeRowsToContents()
    height = header.sizeHint().height() + table.verticalHeader().length() + 2 * table.frameWidth() + 2
    table.setFixedHeight(height)
    table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return table


class PreviewPanel(QFrame):
    """The content of one side as read by Inspect file; empty and hidden until a file is chosen."""

    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        title = QLabel(f"{KIND_TITLE[kind]}: content")
        title.setObjectName("cardTitle")
        layout.addWidget(title)
        self.badge = QLabel("")
        self.badge.setObjectName("badge")
        layout.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignLeft)
        self.message = _label()
        layout.addWidget(self.message)
        self.summary = _label("", "fileName")
        layout.addWidget(self.summary)
        self.paths = QWidget()  # full paths in read-only fields: a long path never widens the page
        self.paths_layout = QGridLayout(self.paths)
        self.paths_layout.setContentsMargins(0, 0, 0, 0)
        self.paths_layout.setHorizontalSpacing(10)
        self.paths_layout.setColumnStretch(1, 1)
        layout.addWidget(self.paths)
        self.path_fields: list[QLineEdit] = []
        self.facts = _label("", "hint")
        layout.addWidget(self.facts)
        self.sections = QWidget()
        self.sections_layout = QVBoxLayout(self.sections)
        self.sections_layout.setContentsMargins(0, 0, 0, 0)
        self.sections_layout.setSpacing(10)
        layout.addWidget(self.sections)
        self.warnings = _label("", "warnings")
        layout.addWidget(self.warnings)
        self.note = _label(PREVIEW_NOTE, "hint")
        layout.addWidget(self.note)
        self.tables: list[QTableWidget] = []
        self.section_titles: list[QLabel] = []
        self.section_notes: list[QLabel] = []

    def _clear_sections(self) -> None:
        while self.sections_layout.count():
            widget = self.sections_layout.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.tables, self.section_titles, self.section_notes = [], [], []
        while self.paths_layout.count():
            widget = self.paths_layout.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.path_fields = []

    def _show_paths(self, paths) -> None:
        for row, (caption, path) in enumerate(paths):
            self.paths_layout.addWidget(QLabel(caption), row, 0)
            field = QLineEdit(path)
            field.setReadOnly(True)
            field.setToolTip(path)
            field.setCursorPosition(len(path))  # a long path shows its end: folder and file name
            self.path_fields.append(field)
            self.paths_layout.addWidget(field, row, 1)

    def show_slot(self, slot: InspectSlot, chosen: bool) -> None:
        self.setVisible(chosen)
        self._clear_sections()
        state = slot.state
        self.badge.setText(STATE_TEXT.get(state, "Not read"))
        self.badge.setProperty("state", {READ: "read", FAILED: "blocked", READING: "chosen"}.get(state, "empty"))
        self.badge.style().unpolish(self.badge)
        self.badge.style().polish(self.badge)
        self.message.setObjectName("error" if state == FAILED else "")
        self.message.style().unpolish(self.message)
        self.message.style().polish(self.message)
        self.message.setText({IDLE: NOT_INSPECTED, READING: "Reading the file in the background. The window stays "
                              "usable; replacing or clearing the file stops this read.",
                              FAILED: slot.message}.get(state, ""))
        self.message.setVisible(state != READ)
        view = view_of(self.kind, slot.preview) if state == READ else None
        self.summary.setText(view.summary if view else "")
        self.summary.setVisible(view is not None)
        self.paths.setVisible(view is not None)
        if view is not None:
            self._show_paths(view.paths)
        self.facts.setText("\n".join(view.facts) if view else "")
        self.facts.setVisible(bool(view and view.facts))
        self.sections.setVisible(view is not None)
        warnings = view.warnings if view else ()
        self.warnings.setText("Importer and loader messages:\n" + "\n".join(f"• {w}" for w in warnings)
                              if warnings else "")
        self.warnings.setVisible(bool(warnings))
        self.note.setText(view.note + " " + PREVIEW_NOTE if view else PREVIEW_NOTE)
        self.note.setVisible(view is not None)
        if view is None:
            return
        for section in view.sections:
            heading = _label(section.title, "sectionTitle")
            self.section_titles.append(heading)
            self.sections_layout.addWidget(heading)
            if section.rows:
                table = section_table(section)
                self.tables.append(table)
                self.sections_layout.addWidget(table)
            else:
                self.sections_layout.addWidget(_label("No record was loaded.", "hint"))
            if section.notes:
                notes = _label("\n".join(f"• {n}" for n in section.notes), "warnings")
                self.section_notes.append(notes)
                self.sections_layout.addWidget(notes)
