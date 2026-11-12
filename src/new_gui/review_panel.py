"""GUI-UX-R1: the Review page: the frequency table, its manual candidate choices, the shapes and the plots (PySide6).

The page shows ``AnalyzePanel``'s result; the summary, the shape views and the other tables are the panel's own widgets,
placed here. The table's columns are fixed. A row's click shows that row's shapes. Each pane scrolls by itself.
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QMenu, QMessageBox,
                               QPushButton,
                               QScrollArea, QSizePolicy, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
                               QWidget)

from new_gui import analyze_model as am
from new_gui import review_model as rv
from new_gui.shape_panel import ImageActions, ImageView, ScrollSafeCombo, _label

EMPTY_TEXT = "No result yet. Choose the two files on the Analyze page and click Analyze, or open a saved result."
SWAP, KEEP, CANCEL = "swap", "keep", "cancel"
RESET_ROW, RESET_ALL, SWAP_TEXT = "Reset Row", "Reset All", "Swap"
ACTIONS = "Actions"
TAB_SHAPES, TAB_PLOTS, TAB_FRF, TAB_TABLES = "Mode shapes", "Frequency plots", "FRF spectrum", "All tables"
_MANUAL_TINT = QColor("#fff4d6")
_CONFLICT_TINT = QColor("#fde8e8")
_FE_COLUMN = 3
COMPACT_COLUMNS = (1, 2, 3, 4, 5)  # ABM-UX3: EXP mode and frequency, selected FE mode and frequency, Δf
SHOW_COLUMNS, FEWER_COLUMNS = "Show all columns", "Show fewer columns"
SAVE_RESULT = "Save result"
_SAVE_MESSAGES = ("Saving the project", "Project saved", "Project not saved")  # the panel's own save messages
PICTURE_IN_VIEW = 120  # pixels of a shape picture that count as "on screen" after a row click
VISUAL_ORDER = (0, 1, 2, 4, 5, 3, 6, 7)  # ABM-UX5: EXP mode, EXP Hz, FE Hz, Δf, then the FE mode choice; logical columns stay
SIDE_BY_SIDE_WIDTH = 760  # the two frequency plots stand side by side from this pane width, else one above the other
CELL_PADDING = 22
ROWS_IN_VIEW = 3  # frequency rows the table shows whole at any window size (the page scrolls rather than hide them)


def _title_width(title: str, metrics, lines: int = 3) -> int:
    """The least width at which a column title wraps into at most ``lines`` lines (the header is three lines high)."""
    words = title.split()
    width = max(metrics.horizontalAdvance(word) for word in words)
    while True:
        count, line = 1, ""
        for word in words:
            trial = f"{line} {word}".strip()
            if metrics.horizontalAdvance(trial) <= width:
                line = trial
            else:
                count, line = count + 1, word
        if count <= lines:
            return width
        width += 4


class _RowsTable(QTableWidget):
    """The frequency table is never made lower than its title row and ``ROWS_IN_VIEW`` of its rows."""

    def minimumSizeHint(self) -> QSize:
        header = self.horizontalHeader()
        rows = min(self.rowCount(), ROWS_IN_VIEW)
        height = (max(header.height(), header.sizeHint().height()) + rows * self.verticalHeader().defaultSectionSize()
                  + 2 * self.frameWidth())
        return QSize(super().minimumSizeHint().width(), height)


class _TablePane(QWidget):
    """ABM-REAL-UX-1: the pane of the frequency table is at least as high as its contents need at its own width.

    Its notes wrap into more lines in a narrow window. With one fixed least height they took the pane and left the table
    a strip with no row in it (a 1366 x 768 window at 150 % display scaling); now the pane's least height follows them."""

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        width = max(self.width(), hint.width())
        return QSize(hint.width(), max(hint.height(), self.layout().totalMinimumHeightForWidth(width)))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if event.size().width() != event.oldSize().width():
            self.updateGeometry()  # the splitter asks for the least height again


def _scrolled(content: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(content)
    return area


class ReviewPanel(QWidget):
    """``ask_duplicate(text)`` answers SWAP, KEEP or CANCEL; tests replace it, the program asks with a dialog."""

    def __init__(self, analyze, ask_duplicate: Optional[Callable[[str], str]] = None,
                 ask_row: Optional[Callable[[tuple], Optional[int]]] = None):
        super().__init__()
        self.analyze = analyze
        self._ask_duplicate = ask_duplicate or self._dialog_duplicate
        self._ask_row = ask_row or self._menu_row  # ABM-UX5: overlapping dots are chosen by the person, never by the program
        self.charts: dict = {}  # kind -> review_model.Chart of what is shown, with where its rows are drawn
        self._drawn_width: dict = {}
        self._redraw = QTimer(self)
        self._redraw.setSingleShot(True)
        self._redraw.setInterval(120)
        self._redraw.timeout.connect(self._draw_plots)
        self.state: Optional[rv.ReviewState] = None
        self.current: Optional[int] = None
        self.combos: list = []
        self.swap_buttons: list = []
        self._building = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        self.empty = _label(EMPTY_TEXT, "hint")
        layout.addWidget(self.empty)
        self.top = QWidget()  # ABM-UX3: the status in one sentence, always visible; its full wording one click away
        top = QVBoxLayout(self.top)
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(4)
        self.status_sentence = _label("", "warnings")
        status_row = QHBoxLayout()  # ABM-UX4: the result is saved where it is read
        status_row.setSpacing(12)
        status_row.addWidget(self.status_sentence, 1)
        self.save_button = QPushButton(SAVE_RESULT)
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(lambda: self.analyze.save_project())
        status_row.addWidget(self.save_button, 0, Qt.AlignmentFlag.AlignTop)
        top.addLayout(status_row)
        self.save_feedback = _label("", "hint")
        self.save_feedback.setVisible(False)
        top.addWidget(self.save_feedback)
        self.saved_note = _label(rv.SAVED_PLOTS_TEXT, "warnings")
        top.addWidget(self.saved_note)
        self.provisional_note = _label(rv.PROVISIONAL_EXPLANATION, "warnings")
        top.addWidget(self.provisional_note)
        layout.addWidget(self.top)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setObjectName("reviewPanes")
        self.splitter.setChildrenCollapsible(False)
        layout.addWidget(self.splitter, 1)
        self.header = QWidget()
        head = QVBoxLayout(self.header)
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(6)
        head.addWidget(analyze.result_box)
        head.addStretch(1)
        self.header_area = _scrolled(self.header)
        self.header_area.setMinimumHeight(70)  # the status card stays visible: registration outcome and warning count
        self.splitter.addWidget(self.header_area)
        self.splitter.addWidget(self._build_table_pane())
        self.splitter.addWidget(self._build_views())
        for index, stretch in enumerate((0, 1, 1)):
            self.splitter.setStretchFactor(index, stretch)
        self.splitter.setSizes([70, 330, 330])  # several table rows and the chosen row's shapes, both without page scrolling
        analyze.result_shown.connect(self.rebuild)
        analyze.shapes_shown.connect(self._shapes_shown)
        analyze.analysis_ready.connect(self._ready)
        analyze.changed.connect(self._save_state)
        analyze.message_changed.connect(self._save_message)
        self.rebuild()
        self._save_state()

    def heightForWidth(self, width: int) -> int:
        """ABM-UX3: the page fills the window and its panes scroll by themselves, so a chosen row's shapes are on screen.

        The wrapped notes take their real height at this width; the panes take their minimum (the page scrolls only below
        it). Without this the page would grow to the panes' preferred heights and push the shapes below the window."""
        margins = self.layout().contentsMargins()
        inner = width - margins.left() - margins.right()
        heights = [max(widget.heightForWidth(inner), widget.minimumSizeHint().height()) if widget is not self.splitter
                   else widget.minimumSizeHint().height() for widget in (self.empty, self.top, self.splitter)
                   if not widget.isHidden()]
        return margins.top() + margins.bottom() + sum(heights) + self.layout().spacing() * max(0, len(heights) - 1)

    # ---------------------------------------------------------------------------------------------- building

    def _build_table_pane(self) -> QWidget:
        pane = _TablePane()
        inner = QVBoxLayout(pane)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(6)
        self.table_title = _label(rv.UNVERIFIED_TITLE, "sectionTitle")
        inner.addWidget(self.table_title)
        inner.addWidget(_label(rv.LIMIT_TEXT, "hint"))
        self.table = _RowsTable(0, len(rv.HEADERS) + 1)
        self.table.setObjectName("reviewFrequencyTable")
        self.table.setMinimumWidth(240)  # its columns stretch to any width; its rows must not widen the page
        self.table.setHorizontalHeaderLabels(list(rv.HEADERS) + [ACTIONS])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)  # ABM-UX5: widths follow the contents (_size_columns)
        header.setSectionResizeMode(_FE_COLUMN, QHeaderView.ResizeMode.Stretch)  # the FE choice takes the rest: no sideways
        header.setSectionResizeMode(len(rv.HEADERS), QHeaderView.ResizeMode.ResizeToContents)  # scrolling
        header.setStretchLastSection(False)
        for visual, logical in enumerate(VISUAL_ORDER):
            header.moveSection(header.visualIndex(logical), visual)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap)
        header.setMinimumHeight(58)
        self.table.itemSelectionChanged.connect(self._row_selected)
        inner.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.reset_row_button = QPushButton(RESET_ROW)
        self.reset_row_button.setObjectName("reviewResetRow")
        self.reset_row_button.clicked.connect(lambda: self.reset_row())
        self.reset_all_button = QPushButton(RESET_ALL)
        self.reset_all_button.setObjectName("reviewResetAll")
        self.reset_all_button.clicked.connect(lambda: self.reset_all())
        self.columns_toggle = QPushButton(SHOW_COLUMNS)
        self.columns_toggle.setObjectName("detailsToggle")
        self.columns_toggle.setCheckable(True)
        self.columns_toggle.setToolTip("Also show the row number, the automatic nearest FE mode and the Swap buttons.")
        self.columns_toggle.toggled.connect(self._columns_toggled)
        row.addWidget(self.columns_toggle)
        self.duplicate_label = _label("", "warnings")
        row.addWidget(self.duplicate_label, 1)
        for button in (self.reset_row_button, self.reset_all_button):
            row.addWidget(button)
        inner.addLayout(row)
        self._columns_toggled(False)
        self.colour_legend = _label("", "hint")  # ABM-UX5: what a tinted cell means, shown only when one is tinted
        inner.addWidget(self.colour_legend)
        self.hypothesis_label = _label("", "warnings")
        inner.addWidget(self.hypothesis_label)
        self.session_label = _label(rv.SESSION_ONLY_TEXT, "hint")
        inner.addWidget(self.session_label)
        return pane

    def _build_views(self) -> QTabWidget:
        self.views = QTabWidget()
        self.views.setObjectName("reviewViews")
        self.views.setDocumentMode(True)
        self.views.setMinimumHeight(140)  # ABM-REAL-UX-1: the table pane keeps its rows; the page still fits a 900 x 700 window
        shapes = QWidget()
        inner = QVBoxLayout(shapes)
        inner.setContentsMargins(0, 8, 0, 0)
        inner.setSpacing(8)
        self.selection_label = _label("", "sectionTitle")
        inner.addWidget(self.selection_label)
        inner.addWidget(self.analyze.shapes)
        inner.addStretch(1)
        self.shapes_area = _scrolled(shapes)
        self.shapes_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)  # two shapes side by side:
        self._kept_scroll: Optional[int] = None  # in a narrow window their right edge is reached, never cut off
        bar = self.shapes_area.verticalScrollBar()
        bar.rangeChanged.connect(self._restore_scroll)
        bar.actionTriggered.connect(lambda _action: setattr(self, "_kept_scroll", None))  # the person scrolled
        self.views.addTab(self.shapes_area, TAB_SHAPES)
        plots = QWidget()
        inner = QVBoxLayout(plots)
        inner.setContentsMargins(0, 8, 0, 0)
        inner.addWidget(_label(rv.PLOTS_EXPLANATION, "hint"))
        self.plot_note = _label("", "hint")
        self.plot_note.setVisible(False)
        inner.addWidget(self.plot_note)
        self.frequency_image, self.difference_image = ImageView(), ImageView()
        self.frequency_actions = ImageActions(self.frequency_image, "fe_vs_exp_frequency")
        self.difference_actions = ImageActions(self.difference_image, "signed_frequency_error")
        self.pictures = QGridLayout()  # side by side in a wide pane, one above the other in a narrow one
        self.pictures.setHorizontalSpacing(8)
        self.pictures.setVerticalSpacing(6)
        self._side_by_side: Optional[bool] = None
        inner.addLayout(self.pictures)
        inner.addStretch(1)
        self.plots_area = _scrolled(plots)
        self.plots_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)  # a drawn chart never narrows its pane
        self._arrange_plots(True)
        self.views.addTab(self.plots_area, TAB_PLOTS)
        for kind, image in (("frequency", self.frequency_image), ("difference", self.difference_image)):
            image.clicked.connect(lambda x, y, k=kind: self._chart_clicked(k, x, y))
            image.setCursor(Qt.CursorShape.PointingHandCursor)
            image.installEventFilter(self)
        frf = QWidget()
        inner = QVBoxLayout(frf)
        inner.setContentsMargins(0, 8, 0, 0)
        self.frf_note = _label("", "hint")
        inner.addWidget(self.frf_note)
        self.frf_image = ImageView()
        self.frf_image.clicked.connect(lambda x, y: self._chart_clicked("frf", x, y))
        self.frf_image.setCursor(Qt.CursorShape.PointingHandCursor)
        self.frf_image.installEventFilter(self)
        inner.addWidget(self.frf_image)
        self.frf_actions = ImageActions(self.frf_image, "frf_spectrum")
        inner.addWidget(self.frf_actions)
        inner.addStretch(1)
        frf_area = _scrolled(frf)
        frf_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.views.addTab(frf_area, TAB_FRF)
        self.views.addTab(self.analyze.tables_box, TAB_TABLES)  # the tables fill the pane and scroll by themselves
        self.views.currentChanged.connect(lambda _index: self._draw_plots())
        self.plots_area.viewport().installEventFilter(self)
        return self.views

    def _arrange_plots(self, side_by_side: bool) -> None:
        if side_by_side == self._side_by_side:
            return
        self._side_by_side = side_by_side
        for widget in (self.frequency_image, self.difference_image, self.frequency_actions, self.difference_actions):
            self.pictures.removeWidget(widget)
        if side_by_side:
            places = ((self.frequency_image, 0, 0), (self.difference_image, 0, 1), (self.frequency_actions, 1, 0),
                      (self.difference_actions, 1, 1))
        else:
            places = ((self.frequency_image, 0, 0), (self.frequency_actions, 1, 0), (self.difference_image, 2, 0),
                      (self.difference_actions, 3, 0))
        for widget, row, column in places:
            self.pictures.addWidget(widget, row, column, Qt.AlignmentFlag.AlignTop)
        self.pictures.setColumnStretch(0, 1)
        self.pictures.setColumnStretch(1, 1 if side_by_side else 0)

    def eventFilter(self, watched, event) -> bool:
        """A changed width redraws the shown charts at their new size (the height a picture takes is not a change)."""
        if event.type() == QEvent.Type.Resize:
            if watched is self.plots_area.viewport():
                self._arrange_plots(watched.width() >= SIDE_BY_SIDE_WIDTH)
            elif watched in (self.frequency_image, self.difference_image, self.frf_image):
                kind = {self.frequency_image: "frequency", self.difference_image: "difference", self.frf_image: "frf"}[watched]
                drawn = self._drawn_width.get(kind)
                if drawn is not None and abs(drawn - watched.width()) > 6:
                    self._redraw.start()
        return super().eventFilter(watched, event)

    # ---------------------------------------------------------------------------------------------- content

    def rebuild(self) -> None:
        """A new result, or none: the table and the plots start again from the automatic selection."""
        self.state = self.analyze.review_state
        has_result = self.state is not None
        self.current = None
        self.empty.setVisible(not has_result)
        self.splitter.setVisible(has_result)
        self.top.setVisible(has_result)
        self.save_feedback.setVisible(False)  # a new or opened result: an earlier save outcome is not about it
        analysis = self.analyze.analysis if has_result else None
        self.status_sentence.setText(rv.status_sentence(analysis, analysis.statement == am.CONFIRMED_TEXT)
                                     if analysis is not None else "")
        self.status_sentence.setObjectName("hint" if analysis is not None and analysis.comparison is not None else "warnings")
        self.status_sentence.style().unpolish(self.status_sentence)
        self.status_sentence.style().polish(self.status_sentence)
        self.table_title.setText(rv.table_title(analysis))
        self.saved_note.setVisible(has_result and self.analyze.snapshot is not None)
        self.provisional_note.setVisible(has_result and self.state.provisional)
        self._fill_table()
        self._selected_changed()

    def _fill_table(self) -> None:
        self._building = True
        self.table.clearContents()
        self.combos = []
        self.swap_buttons = []
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
            if row.row + 1 < len(rows):
                swap = QPushButton(SWAP_TEXT)
                swap.setObjectName("reviewSwap")
                swap.setToolTip("Swap the selected FE modes of this row and the next row. A hypothesis, not a validated identity.")
                swap.clicked.connect(lambda _checked=False, r=row.row: self.swap_with_next(r))
                self.table.setCellWidget(row.row, len(rv.HEADERS), swap)
                self.swap_buttons.append(swap)
        self._size_columns(rows)
        self.table.updateGeometry()  # its least height follows the number of rows
        self._building = False
        self._show_rows()

    def _size_columns(self, rows) -> None:
        """Each fixed column as wide as its widest cell or the longest word of its title: the short EXP mode column stays
        narrow, and the FE mode choice takes the remaining width."""
        metrics = self.table.fontMetrics()
        header_metrics = self.table.horizontalHeader().fontMetrics()
        for column in range(len(rv.HEADERS)):
            if column == _FE_COLUMN:
                continue
            texts = [row.cells()[column] for row in rows]
            width = max([metrics.horizontalAdvance(text) for text in texts] + [_title_width(rv.HEADERS[column], header_metrics)])
            self.table.setColumnWidth(column, width + CELL_PADDING)

    def _show_rows(self) -> None:
        """The cells of the current selection; a manual row is tinted and its origin is in the tooltip and the line below."""
        self._building = True
        conflict_rows = {r for rows in self.state.conflicts().values() for r in rows} if self.state is not None else set()
        for row in self.state.rows() if self.state is not None else ():
            for column, text in enumerate(row.cells()):
                item = self.table.item(row.row, column)
                item.setText(text)
                item.setToolTip(f"{row.record}: {row.origin}")
                item.setBackground(_MANUAL_TINT if row.manual else QColor("#ffffff"))
            if row.row + 1 in conflict_rows:
                conflict = self.table.item(row.row, _FE_COLUMN + 1)
                conflict.setBackground(_CONFLICT_TINT)
                conflict.setToolTip(f"FE mode {row.selected_mode} is also selected for another row: not one-to-one.")
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
        legend = ([rv.CONFLICT_TEXT] if conflict_rows else []) + ([rv.MANUAL_TINT_TEXT] if state is not None and state.manual else [])
        self.colour_legend.setText(" ".join(legend))
        self.colour_legend.setVisible(bool(legend))
        self.session_label.setVisible(bool(text))
        self.reset_all_button.setEnabled(bool(state and state.manual))
        self._buttons()

    def _buttons(self) -> None:
        state, current = self.state, self.current
        self.reset_row_button.setEnabled(state is not None and current in state.manual)

    def _selected_changed(self) -> None:
        self._draw_plots()

    def _ready(self) -> None:
        """A new result opens on Mode shapes, at the top. The row of what the panel has just drawn (the first pair, or else
        row 1) is marked without drawing it again."""
        self.views.setCurrentWidget(self.shapes_area)
        self._shapes_to_top()
        QTimer.singleShot(0, self._shapes_to_top)  # after the window has shown the page and moved the keyboard focus
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

    def _save_state(self) -> None:
        """Enabled exactly when the File menu's Save is: a shown result and nothing running."""
        self.save_button.setEnabled(self.analyze.can_save())

    def _save_message(self, text: str) -> None:
        """The panel's own save outcome, shown beside the button (the status bar shows it too); other messages are not."""
        if not text.startswith(_SAVE_MESSAGES):
            return
        failed = text.startswith("Project not saved")
        self.save_feedback.setObjectName("error" if failed else "hint")
        self.save_feedback.style().unpolish(self.save_feedback)
        self.save_feedback.style().polish(self.save_feedback)
        self.save_feedback.setText(text)
        self.save_feedback.setVisible(True)

    def _columns_toggled(self, shown: bool) -> None:
        """Compact by default; the other columns (row, automatic nearest FE mode, Swap) are one click away."""
        self.columns_toggle.setText(FEWER_COLUMNS if shown else SHOW_COLUMNS)
        for column in range(self.table.columnCount()):
            self.table.setColumnHidden(column, not shown and column not in COMPACT_COLUMNS)

    def _row_selected(self) -> None:
        if self._building:
            return
        rows = self.table.selectionModel().selectedRows()
        if rows:
            if self.views.currentWidget() is self.analyze.tables_box:
                self.views.setCurrentWidget(self.shapes_area)  # a chosen row shows its shapes; the plots mark it themselves
            self.show_row(rows[0].row())
            if self.views.currentWidget() is self.shapes_area:
                self._pictures_into_view()

    def show_row(self, row: int) -> bool:
        if self.state is None or not 0 <= row < len(self.state):
            return False
        self.current = row
        self._buttons()
        self._keep_scroll()
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
            self._building = True
            self.table.selectRow(row)
            self._building = False
            self._keep_scroll()
            self.analyze.show_candidate(row)
        self._buttons()
        self._draw_plots()

    def _chart_clicked(self, kind: str, x: float, y: float) -> Optional[int]:
        """A click on a chart selects the table row drawn there, as a click on that row does (its shapes follow). Several
        rows drawn on the same spot are offered to the person; none is chosen for them."""
        chart = self.charts.get(kind)
        if chart is None or self.state is None:
            return None
        rows = rv.rows_at(chart, x, y)
        if not rows:
            return None
        row = rows[0] if len(rows) == 1 else self._ask_row(rows)
        if row is None or not 0 <= row < len(self.state):
            return None
        self.select_row(row)
        return row

    def row_text(self, row: int) -> str:
        cells = self.state.row(row)
        return (f"Row {row + 1}: EXP {cells.exp_mode} ({cells.exp_text} Hz) with FE {cells.selected_mode} "
                f"({cells.selected_text} Hz)")

    def _menu_row(self, rows: tuple) -> Optional[int]:
        menu = QMenu(self)
        actions = {menu.addAction(self.row_text(row)): row for row in rows}
        chosen = menu.exec(QCursor.pos())
        return actions.get(chosen)

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

    def _keep_scroll(self) -> None:
        """A row's redraw briefly shortens the shapes while their pictures are replaced; the pane keeps its place."""
        self._kept_scroll = self.shapes_area.verticalScrollBar().value()

    def _pictures_into_view(self) -> None:
        """After a row click: when no shape picture is on screen, the pane scrolls to the pictures (above them are the view
        choices). A pane already showing a picture stays where the person left it."""
        self.shapes_area.widget().layout().activate()
        panels = self.analyze.saved_shapes if self.analyze.snapshot is not None else self.analyze.shape_panels
        images = [panel.image for panel in panels.values() if not panel.isHidden()]
        if not images:
            return
        viewport = self.shapes_area.viewport()
        bar = self.shapes_area.verticalScrollBar()
        tops = [image.mapTo(self.shapes_area.widget(), image.rect().topLeft()).y() for image in images]
        shown = [min(top + image.height(), bar.value() + viewport.height()) - max(top, bar.value())
                 for top, image in zip(tops, images)]
        if max(shown) >= min(PICTURE_IN_VIEW, min(image.height() for image in images)):
            return
        target = max(0, min(tops) - 8)
        self._kept_scroll = target  # also over the brief shortening while the pictures are replaced
        bar.setValue(target)

    def _restore_scroll(self, _low: int, high: int) -> None:
        kept = self._kept_scroll
        if kept is not None and high >= kept:
            self._kept_scroll = None
            self.shapes_area.verticalScrollBar().setValue(kept)

    def _shapes_to_top(self) -> None:
        """Only for a new result: Analyze going disabled moves the focus into this pane, and Qt scrolls to the focused widget."""
        self._kept_scroll = None
        self.table.setFocus()
        self.shapes_area.verticalScrollBar().setValue(0)

    def _shapes_shown(self, text: str) -> None:
        self.selection_label.setText(text)

    def _draw_plots(self) -> None:
        """Only the shown tab is drawn: a table click stays quick."""
        state = self.state
        if state is None:
            for image in (self.frequency_image, self.difference_image, self.frf_image):
                image.clear_image()
            self.charts.clear()
            self.plot_note.setVisible(False)
            self.frf_note.setText("")
            self.selection_label.setText("")
            return
        tab = self.views.tabText(self.views.currentIndex())
        if tab == TAB_PLOTS:
            self._arrange_plots(self.plots_area.viewport().width() >= SIDE_BY_SIDE_WIDTH)
            width = self._chart_width(self.frequency_image)
            ratio = self.frequency_image.devicePixelRatioF()
            frequency = rv.frequency_chart(state, self.current, width, min(540, round(width * 0.72)), ratio)
            points = rv._plotted(state)
            values = [abs(p[3]) for p in points]
            detail = bool(values) and max(values) > rv.DETAIL_LIMIT and min(values) <= rv.DETAIL_LIMIT
            difference = rv.difference_chart(state, self.current, width,
                                             min(560, round(width * (0.95 if detail else 0.72))), ratio)
            for kind, image, chart in (("frequency", self.frequency_image, frequency),
                                       ("difference", self.difference_image, difference)):
                self.charts[kind] = chart
                self._drawn_width[kind] = image.width()
                image.set_image(chart.png)
            self.plot_note.setText(frequency.note)
            self.plot_note.setVisible(bool(frequency.note))
        elif tab == TAB_FRF:
            self._draw_frf()

    def _chart_width(self, image) -> int:
        """The logical width the picture will take: its own, or before it is laid out, its share of the pane."""
        if image.width() > 50:
            return image.width()
        pane = self.views.width() - 24
        return max(280, pane // 2 if pane >= SIDE_BY_SIDE_WIDTH else pane)

    def _draw_frf(self) -> None:
        saved = self.analyze.snapshot is not None
        dataset = None if saved else self.analyze.chosen_dataset()
        series = None if saved else rv.frf_series(dataset)
        if series is None:
            self.frf_image.clear_image()
            self.charts.pop("frf", None)
            self.frf_note.setText(rv.frf_missing(dataset, saved))
            return
        records = [(f"EXP {row.exp_mode}", float(row.exp_text)) for row in self.state.rows()]
        self.frf_note.setText(rv.FRF_PEAK_NOTE if self.state.provisional else rv.FITTED_NOTE)
        width = self._chart_width(self.frf_image)
        height = min(560, round(width * (0.52 if series[2] is not None else 0.4)))
        chart = rv.frf_chart(series, records, self.current, self.state.provisional, width, height,
                             self.frf_image.devicePixelRatioF())
        self.charts["frf"] = chart
        self._drawn_width["frf"] = self.frf_image.width()
        self.frf_image.set_image(chart.png)


__all__ = ["CANCEL", "COMPACT_COLUMNS", "KEEP", "ReviewPanel", "SWAP", "VISUAL_ORDER"]
