"""GUI-UX-R1: the Review page: the frequency table, its manual candidate choices, the shapes and the plots (PySide6).

The page shows ``AnalyzePanel``'s result; the summary, the shape views and the other tables are the panel's own widgets,
placed here. The table's columns are fixed. A row's click shows that row's shapes. Each pane scrolls by itself.
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
                               QScrollArea, QSizePolicy, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
                               QWidget)

from new_gui import review_model as rv
from new_gui.shape_panel import ImageView, ScrollSafeCombo, _label

EMPTY_TEXT = "No result yet. Choose the two files on the Analyze page and click Analyze, or open a saved result."
SWAP, KEEP, CANCEL = "swap", "keep", "cancel"
RESET_ROW, RESET_ALL, SWAP_NEXT = "Reset row", "Reset all to automatic", "Swap with next"
TAB_SHAPES, TAB_PLOTS, TAB_FRF, TAB_TABLES = "Mode shapes", "Frequency plots", "FRF spectrum", "All tables"
_MANUAL_TINT = QColor("#fff4d6")
_FE_COLUMN = 3


def _scrolled(content: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(content)
    return area


class ReviewPanel(QWidget):
    """``ask_duplicate(text)`` answers SWAP, KEEP or CANCEL; tests replace it, the program asks with a dialog."""

    def __init__(self, analyze, ask_duplicate: Optional[Callable[[str], str]] = None):
        super().__init__()
        self.analyze = analyze
        self._ask_duplicate = ask_duplicate or self._dialog_duplicate
        self.state: Optional[rv.ReviewState] = None
        self.current: Optional[int] = None
        self.combos: list = []
        self._building = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        self.empty = _label(EMPTY_TEXT, "hint")
        layout.addWidget(self.empty)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setObjectName("reviewPanes")
        self.splitter.setChildrenCollapsible(False)
        layout.addWidget(self.splitter, 1)
        self.header = QWidget()
        head = QVBoxLayout(self.header)
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(6)
        self.saved_note = _label(rv.SAVED_PLOTS_TEXT, "warnings")
        head.addWidget(self.saved_note)
        self.provisional_note = _label(rv.PROVISIONAL_EXPLANATION, "warnings")
        head.addWidget(self.provisional_note)
        head.addWidget(analyze.result_box)
        head.addStretch(1)
        self.header_area = _scrolled(self.header)
        self.header_area.setMinimumHeight(70)
        self.splitter.addWidget(self.header_area)
        self.splitter.addWidget(self._build_table_pane())
        self.splitter.addWidget(self._build_views())
        for index, stretch in enumerate((0, 1, 1)):
            self.splitter.setStretchFactor(index, stretch)
        self.splitter.setSizes([84, 330, 320])  # the table shows several rows; the status is one drag away
        analyze.result_shown.connect(self.rebuild)
        analyze.shapes_shown.connect(self._shapes_shown)
        analyze.analysis_ready.connect(self._ready)
        self.rebuild()

    # ---------------------------------------------------------------------------------------------- building

    def _build_table_pane(self) -> QWidget:
        pane = QWidget()
        pane.setMinimumHeight(170)
        inner = QVBoxLayout(pane)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(6)
        inner.addWidget(_label(rv.TITLE, "sectionTitle"))
        inner.addWidget(_label(rv.LIMIT_TEXT, "hint"))
        self.table = QTableWidget(0, len(rv.HEADERS))
        self.table.setObjectName("reviewFrequencyTable")
        self.table.setMinimumWidth(240)  # its columns stretch to any width; its rows must not widen the page
        self.table.setHorizontalHeaderLabels(list(rv.HEADERS))
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)  # all seven always fit: no sideways scrolling
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap)
        header.setMinimumHeight(42)
        self.table.itemSelectionChanged.connect(self._row_selected)
        inner.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.swap_button = QPushButton(SWAP_NEXT)
        self.swap_button.setObjectName("reviewSwapNext")
        self.swap_button.clicked.connect(lambda: self.swap_with_next())
        self.reset_row_button = QPushButton(RESET_ROW)
        self.reset_row_button.setObjectName("reviewResetRow")
        self.reset_row_button.clicked.connect(lambda: self.reset_row())
        self.reset_all_button = QPushButton(RESET_ALL)
        self.reset_all_button.setObjectName("reviewResetAll")
        self.reset_all_button.clicked.connect(lambda: self.reset_all())
        for button in (self.swap_button, self.reset_row_button, self.reset_all_button):
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)  # they share any width: no sideways scroll
            button.setMinimumWidth(70)
            button.setToolTip(button.text())
            row.addWidget(button)
        inner.addLayout(row)
        self.hypothesis_label = _label("", "warnings")
        inner.addWidget(self.hypothesis_label)
        self.duplicate_label = _label("", "error")
        inner.addWidget(self.duplicate_label)
        self.session_label = _label(rv.SESSION_ONLY_TEXT, "hint")
        inner.addWidget(self.session_label)
        return pane

    def _build_views(self) -> QTabWidget:
        self.views = QTabWidget()
        self.views.setObjectName("reviewViews")
        self.views.setDocumentMode(True)
        self.views.setMinimumHeight(220)
        shapes = QWidget()
        inner = QVBoxLayout(shapes)
        inner.setContentsMargins(0, 8, 0, 0)
        inner.setSpacing(8)
        self.selection_label = _label("", "sectionTitle")
        inner.addWidget(self.selection_label)
        inner.addWidget(self.analyze.shapes)
        inner.addStretch(1)
        self.views.addTab(_scrolled(shapes), TAB_SHAPES)
        plots = QWidget()
        inner = QVBoxLayout(plots)
        inner.setContentsMargins(0, 8, 0, 0)
        self.frequency_image, self.difference_image = ImageView(), ImageView()
        pictures = QGridLayout()  # side by side: both fit the pane without scrolling
        pictures.setHorizontalSpacing(8)
        pictures.setColumnStretch(0, 1)
        pictures.setColumnStretch(1, 1)
        pictures.addWidget(self.frequency_image, 0, 0)
        pictures.addWidget(self.difference_image, 0, 1)
        inner.addLayout(pictures)
        inner.addStretch(1)
        self.views.addTab(_scrolled(plots), TAB_PLOTS)
        frf = QWidget()
        inner = QVBoxLayout(frf)
        inner.setContentsMargins(0, 8, 0, 0)
        self.frf_note = _label("", "hint")
        inner.addWidget(self.frf_note)
        self.frf_image = ImageView()
        inner.addWidget(self.frf_image)
        inner.addStretch(1)
        self.views.addTab(_scrolled(frf), TAB_FRF)
        self.views.addTab(_scrolled(self.analyze.tables_box), TAB_TABLES)
        self.views.currentChanged.connect(lambda _index: self._draw_plots())
        return self.views

    # ---------------------------------------------------------------------------------------------- content

    def rebuild(self) -> None:
        """A new result, or none: the table and the plots start again from the automatic selection."""
        self.state = self.analyze.review_state
        has_result = self.state is not None
        self.current = None
        self.empty.setVisible(not has_result)
        self.splitter.setVisible(has_result)
        self.saved_note.setVisible(has_result and self.analyze.snapshot is not None)
        self.provisional_note.setVisible(has_result and self.state.provisional)
        self._fill_table()
        self._selected_changed()

    def _fill_table(self) -> None:
        self._building = True
        self.table.clearContents()
        self.combos = []
        rows = self.state.rows() if self.state is not None else ()
        self.table.setRowCount(len(rows))
        for row in rows:
            for column, text in enumerate(row.cells()):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row.row, column, item)
            combo = ScrollSafeCombo()
            combo.setObjectName("reviewFeMode")
            for number, text in self.state.options:
                combo.addItem(number, number)
            combo.setToolTip("Select another elastic FE mode to inspect it. This is a hypothesis, not a validated identity.")
            combo.activated.connect(lambda _index, r=row.row, c=combo: self.select_mode(r, c.currentData()))
            self.table.setCellWidget(row.row, _FE_COLUMN, combo)
            self.combos.append(combo)
        self._building = False
        self._show_rows()

    def _show_rows(self) -> None:
        """The cells of the current selection; a manual row is tinted and its origin is in the tooltip and the line below."""
        self._building = True
        for row in self.state.rows() if self.state is not None else ():
            for column, text in enumerate(row.cells()):
                item = self.table.item(row.row, column)
                item.setText(text)
                item.setToolTip(f"{row.record}: {row.origin}")
                item.setBackground(_MANUAL_TINT if row.manual else QColor("#ffffff"))
            combo = self.combos[row.row]
            found = combo.findData(row.selected_mode)
            combo.setCurrentIndex(found)
            combo.setEnabled(bool(self.state.options))
        self._building = False
        state = self.state
        text = state.hypothesis_text() if state is not None else ""
        self.hypothesis_label.setText(text)
        self.hypothesis_label.setVisible(bool(text))
        warning = state.duplicate_warning() if state is not None else ""
        self.duplicate_label.setText(warning)
        self.duplicate_label.setVisible(bool(warning))
        self.session_label.setVisible(bool(text))
        self.reset_all_button.setEnabled(bool(state and state.manual))
        self._buttons()

    def _buttons(self) -> None:
        state, current = self.state, self.current
        self.swap_button.setEnabled(state is not None and current is not None and current + 1 < len(state))
        self.reset_row_button.setEnabled(state is not None and current in state.manual)

    def _selected_changed(self) -> None:
        self._draw_plots()

    def _ready(self) -> None:
        """Mark the row of what the panel has just drawn (the first pair, or else row 1), without drawing it again."""
        if self.state is None or not len(self.state):
            return
        view = self.analyze.analysis.comparison
        row = 0
        if view is not None and view.pair_rows:
            mode = view.pair_rows[0].cells[3]
            row = next((r.row for r in self.state.rows() if r.exp_mode == mode), 0)
        self._building = True
        self.table.selectRow(row)
        self._building = False
        self.current = row
        self._buttons()
        self._draw_plots()

    # ---------------------------------------------------------------------------------------------- commands

    def _row_selected(self) -> None:
        if self._building:
            return
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self.show_row(rows[0].row())

    def show_row(self, row: int) -> bool:
        if self.state is None or not 0 <= row < len(self.state):
            return False
        self.current = row
        self._buttons()
        self.analyze.show_candidate(row)
        self._draw_plots()
        return True

    def select_row(self, row: int) -> None:
        """Select a table row as a click does (its shapes follow)."""
        self.table.selectRow(row)

    def select_mode(self, row: int, mode) -> bool:
        """A manual FE choice for one row. A mode already selected elsewhere needs a decision: swap, keep both or cancel."""
        if self.state is None or self._building or mode is None or mode == self.state.selected(row):
            return False
        try:
            self.state.assign(row, mode)
        except rv.DuplicateSelection as taken:
            answer = self._ask_duplicate(f"FE mode {mode} is already selected for row {taken.rows[0] + 1}.\n\nSwap the two "
                                         "rows, or keep both and show a diagnostic warning?")
            if answer == SWAP and self.state.selected(row) in self.state.fe_hz:
                self.state.swap(row, taken.rows[0])
            elif answer == KEEP:
                self.state.assign(row, mode, allow_duplicate=True)
            else:  # cancelled: the combo goes back to the row's selection
                self._show_rows()
                return False
        self._changed(row)
        return True

    def swap_with_next(self, row: Optional[int] = None) -> bool:
        row = self.current if row is None else row
        if self.state is None or row is None or row + 1 >= len(self.state) or not self.state.swap(row, row + 1):
            return False
        self._changed(row)
        return True

    def reset_row(self, row: Optional[int] = None) -> bool:
        row = self.current if row is None else row
        if self.state is None or row is None:
            return False
        self.state.reset(row)
        self._changed(row)
        return True

    def reset_all(self) -> bool:
        if self.state is None:
            return False
        self.state.reset()
        self._changed(self.current)
        return True

    def _changed(self, row: Optional[int]) -> None:
        self._show_rows()
        if row is not None:
            self.current = row
            self.analyze.show_candidate(row)
        self._buttons()
        self._draw_plots()

    def _dialog_duplicate(self, text: str) -> str:
        box = QMessageBox(self)
        box.setWindowTitle("FE mode already selected")
        box.setText(text)
        swap = box.addButton("Swap", QMessageBox.ButtonRole.AcceptRole)
        keep = box.addButton("Keep both", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        return {swap: SWAP, keep: KEEP}.get(box.clickedButton(), CANCEL)

    # ---------------------------------------------------------------------------------------------- display

    def _shapes_shown(self, text: str) -> None:
        self.selection_label.setText(text)

    def _draw_plots(self) -> None:
        """Only the shown tab is drawn: a table click stays quick."""
        state = self.state
        if state is None:
            for image in (self.frequency_image, self.difference_image, self.frf_image):
                image.clear_image()
            self.frf_note.setText("")
            self.selection_label.setText("")
            return
        tab = self.views.tabText(self.views.currentIndex())
        if tab == TAB_PLOTS:
            self.frequency_image.set_image(rv.frequency_plot(state, self.current))
            self.difference_image.set_image(rv.difference_plot(state, self.current))
        elif tab == TAB_FRF:
            self._draw_frf()

    def _draw_frf(self) -> None:
        if self.analyze.snapshot is not None:
            self.frf_image.clear_image()
            self.frf_note.setText(rv.FRF_NEEDS_SOURCE)
            return
        series = rv.frf_series(self.analyze.chosen_dataset())
        if series is None:
            self.frf_image.clear_image()
            self.frf_note.setText(rv.FRF_NOT_IN_FILE)
            return
        rows = self.state.rows()
        marks = [float(row.exp_text) for row in rows]
        current = float(rows[self.current].exp_text) if self.current is not None else None
        self.frf_note.setText("")
        self.frf_image.set_image(rv.frf_plot(series, marks, current))


__all__ = ["CANCEL", "KEEP", "ReviewPanel", "SWAP"]
