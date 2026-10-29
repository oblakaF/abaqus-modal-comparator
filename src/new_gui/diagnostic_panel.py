"""NEW-GUI.4: the Analysis page's frequency diagnostic (PySide6).

The user chooses one experimental modal set of the read experimental file and clicks Run frequency diagnostic.
Nothing runs by itself: the button is disabled, with the reason shown, until both files are read and a set is
chosen. The service runs in a worker thread (``new_gui.diagnostic_model.run_diagnostic``); its outcome comes back to
the window's thread through a queued signal. A replaced or cleared file, Inspect again, another modal set or a
closed window cancels the request and discards its outcome.

The result shows FREQUENCY_ONLY_DIAGNOSTIC, the chosen set, the nearest and next elastic FE frequencies of every
experimental record ("Nearest by frequency — NOT a mode pair", MAC NOT_COMPUTED), the elastic FE, rigid-body FE and
experimental frequencies in separate tables, and the out-of-range notes. The tables are read-only; a table that does
not fit a narrow window scrolls horizontally itself, never the page.
"""

from __future__ import annotations

import threading
from typing import Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from new_gui import diagnostic_model as dm
from new_gui.workspace_state import ANALYSIS_NOT_RUN, ANALYSIS_NOTE

TEXT_CAP = 280  # a long classification is cut off in its cell (the tooltip and the lists below hold it in full)


def _label(text: str = "", name: str = "", wrap: bool = True) -> QLabel:
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    label.setWordWrap(wrap)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    if wrap:
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)  # long text never widens
        label.setMinimumWidth(0)
    return label


def _card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(8)
    return frame, layout


def _restyle(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class DiagnosticTable(QTableWidget):
    """A read-only table as tall as its rows. ``stretch`` takes the free width (never less than its header);
    ``capped`` text columns are at most TEXT_CAP wide. When the columns do not fit, the table scrolls horizontally."""

    def __init__(self, headers, rows, stretch: int, capped=(), text_columns=()):
        super().__init__(len(rows), len(headers))
        self.setObjectName("diagnosticTable")
        self.stretch = stretch
        self.setHorizontalHeaderLabels(list(headers))
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.verticalHeader().setVisible(False)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)  # the whole text is in the cell's tooltip
        left = set(text_columns) | set(capped) | {stretch}
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if column not in left:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.setItem(row, column, item)
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        for column in range(len(headers)):
            fixed = column == stretch or column in capped
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed if fixed
                                        else QHeaderView.ResizeMode.ResizeToContents)
        for column in capped:
            header.resizeSection(column, max(self._header_width(column),
                                             min(TEXT_CAP, self.sizeHintForColumn(column))))
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)  # only when the columns do not fit
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.resizeRowsToContents()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.fit()

    def _header_width(self, column: int) -> int:
        return self.horizontalHeader().fontMetrics().horizontalAdvance(self.horizontalHeaderItem(column).text()) + 24

    def fit(self) -> None:
        header = self.horizontalHeader()
        others = sum(header.sectionSize(c) for c in range(self.columnCount()) if c != self.stretch)
        header.resizeSection(self.stretch, max(self._header_width(self.stretch), self.viewport().width() - others))
        overflow = header.length() > self.viewport().width()
        height = (header.sizeHint().height() + self.verticalHeader().length() + 2 * self.frameWidth() + 2
                  + (self.horizontalScrollBar().sizeHint().height() if overflow else 0))
        if self.height() != height:
            self.setFixedHeight(height)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fit()


class _Bridge(QObject):
    """Carries a diagnostic's outcome from its worker thread to the window's thread (a queued signal)."""

    done = Signal(object)


class DiagnosticPanel(QWidget):
    """The Analysis page's content: the result summary, the diagnostic's inputs and command, and its result."""

    changed = Signal()  # the shown state changed (the window updates its status bar)

    def __init__(self):
        super().__init__()
        self.fe_preview = None
        self.experimental_preview = None
        self.slot = dm.DiagnosticSlot()
        self.discarded = 0  # outcomes of cancelled or stale requests, never shown
        self.tables: dict[str, DiagnosticTable] = {}
        self._threads: list[threading.Thread] = []
        self._bridge = _Bridge(self)
        self._bridge.done.connect(self._done)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self._build_summary())
        layout.addWidget(self._build_inputs())
        layout.addWidget(self._build_result())
        self._refresh()

    # ------------------------------------------------------------------------------------------ building

    def _build_summary(self) -> QFrame:
        card, inner = _card()
        inner.addWidget(_label("Result", "cardTitle", wrap=False))
        self.badge = _label(ANALYSIS_NOT_RUN, "badge", wrap=False)  # below the title: a narrow window keeps both
        inner.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignLeft)
        self.summary_note = _label(ANALYSIS_NOTE)
        inner.addWidget(self.summary_note)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        self.summary_values = {}
        for row, caption in enumerate(("Frequencies", "MAC", "Mode pairs")):
            grid.addWidget(_label(caption, wrap=False), row, 0)
            self.summary_values[caption] = _label("", "hint")
            grid.addWidget(self.summary_values[caption], row, 1)
        grid.setColumnStretch(1, 1)
        inner.addLayout(grid)
        return card

    def _build_inputs(self) -> QFrame:
        card, inner = _card()
        inner.addWidget(_label("Frequency diagnostic", "cardTitle"))
        inner.addWidget(_label("Compares the frequencies of the read FE results with those of one experimental modal "
                               "set. There is no geometric registration, MAC or mode pairing: the nearest FE "
                               "frequency is frequency proximity only.", "hint"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setColumnStretch(1, 1)
        grid.addWidget(_label("FE results", wrap=False), 0, 0, Qt.AlignmentFlag.AlignTop)
        self.fe_input = _label("", "hint")
        grid.addWidget(self.fe_input, 0, 1)
        grid.addWidget(_label("Experimental data", wrap=False), 1, 0, Qt.AlignmentFlag.AlignTop)
        self.experimental_input = _label("", "hint")
        grid.addWidget(self.experimental_input, 1, 1)
        grid.addWidget(_label("Modal set", wrap=False), 2, 0)
        self.set_combo = QComboBox()
        self.set_combo.setObjectName("diagnosticSet")
        self.set_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.set_combo.setMinimumContentsLength(14)  # a long set name never widens the window
        self.set_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.set_combo.currentIndexChanged.connect(self._set_changed)
        grid.addWidget(self.set_combo, 2, 1)
        inner.addLayout(grid)
        buttons = QHBoxLayout()
        self.run_button = QPushButton(dm.RUN)
        self.run_button.setObjectName("primary")
        self.run_button.setToolTip("Compute the frequency-only diagnostic of the read data. Nothing is paired, "
                                   "registered or selected.")
        self.run_button.clicked.connect(self.run)
        buttons.addWidget(self.run_button)
        buttons.addStretch(1)
        inner.addLayout(buttons)
        self.why_unavailable = _label("", "hint")
        inner.addWidget(self.why_unavailable)
        self.status = _label("", "hint")
        inner.addWidget(self.status)
        return card

    def _build_result(self) -> QFrame:
        self.result_card, inner = _card()
        inner.addWidget(_label("Frequency diagnostic result", "cardTitle"))
        self.result_badge = _label(dm.STATUS, "badge", wrap=False)
        self.result_badge.setProperty("state", "chosen")
        inner.addWidget(self.result_badge, 0, Qt.AlignmentFlag.AlignLeft)
        self.statement = _label("", "")
        inner.addWidget(self.statement)
        self.reason = _label("", "hint")
        inner.addWidget(self.reason)
        self.result_set = _label("", "fileName")
        inner.addWidget(self.result_set)
        self.source = _label("", "hint")
        inner.addWidget(self.source)
        self.provisional = _label(dm.PROVISIONAL_TEXT, "error")
        inner.addWidget(self.provisional)
        self.mac_line = _label(f"MAC: {dm.NOT_COMPUTED}. Mode pairs: {dm.MODE_PAIRS}.", "")
        inner.addWidget(self.mac_line)
        self.tables_box = QWidget()
        self.tables_layout = QVBoxLayout(self.tables_box)
        self.tables_layout.setContentsMargins(0, 0, 0, 0)
        self.tables_layout.setSpacing(8)
        inner.addWidget(self.tables_box)
        return self.result_card

    # ------------------------------------------------------------------------------------------ inputs

    def set_inputs(self, fe_preview, experimental_preview) -> None:
        """The previews read now (None when a side is not read). A new preview discards the result."""
        fe_changed = fe_preview is not self.fe_preview
        experimental_changed = experimental_preview is not self.experimental_preview
        if not (fe_changed or experimental_changed):
            return
        self.fe_preview, self.experimental_preview = fe_preview, experimental_preview
        if experimental_changed:  # a new set list, with nothing chosen
            self.set_combo.blockSignals(True)
            self.set_combo.clear()
            self.set_combo.addItem(dm.CHOOSE_SET, None)
            if experimental_preview is not None:
                for index, text in dm.set_options(experimental_preview):
                    self.set_combo.addItem(text, index)
            self.set_combo.setCurrentIndex(0)
            self.set_combo.blockSignals(False)
        self._reset()

    def chosen_set_index(self) -> Optional[int]:
        return self.set_combo.currentData() if self.experimental_preview is not None else None

    def unavailable(self) -> tuple:
        return dm.unavailable(self.fe_preview, self.experimental_preview, self.chosen_set_index())

    def ready(self) -> bool:
        return not self.unavailable()

    def _set_changed(self) -> None:
        self._reset()  # another set never keeps the previous result

    def _reset(self) -> None:
        self.slot.reset()
        self._refresh()

    # ------------------------------------------------------------------------------------------ running

    def run(self) -> bool:
        """Run the diagnostic in a worker thread; returns False when it cannot run now."""
        if not self.ready() or self.slot.state == dm.RUNNING:
            return False
        set_index = self.chosen_set_index()
        fe_preview, experimental_preview = self.fe_preview, self.experimental_preview
        token, cancel_event = self.slot.start((fe_preview, experimental_preview, set_index))
        worker = threading.Thread(target=self._work, args=(fe_preview, experimental_preview, set_index, token,
                                                           cancel_event), name="new-gui-diagnostic", daemon=True)
        self._threads = [thread for thread in self._threads if thread.is_alive()] + [worker]
        worker.start()
        self._refresh()
        return True

    def _work(self, fe_preview, experimental_preview, set_index, token, cancel_event) -> None:
        outcome = dm.run_diagnostic(fe_preview, experimental_preview, set_index, token, cancel_event)  # no widget
        try:
            self._bridge.done.emit(outcome)
        except RuntimeError:  # the panel is already gone
            pass

    def _done(self, outcome: dm.DiagnosticOutcome) -> None:
        if not self.slot.finish(outcome):
            self.discarded += 1  # a cancelled or stale request: the current state is kept
            return
        self._refresh()

    def busy(self) -> bool:
        return self.slot.state == dm.RUNNING or any(thread.is_alive() for thread in self._threads)

    def cancel(self) -> None:
        self._reset()

    # ------------------------------------------------------------------------------------------ display

    @property
    def view(self) -> Optional[dm.DiagnosticView]:
        outcome = self.slot.outcome
        return outcome.view if self.slot.state == dm.DONE and outcome is not None else None

    @property
    def status_text(self) -> str:
        return dm.STATUS if self.view is not None else ANALYSIS_NOT_RUN

    def _clear_tables(self) -> None:
        while self.tables_layout.count():
            widget = self.tables_layout.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.tables = {}

    def _add_table(self, key: str, title: str, headers, rows, stretch: int, capped=(), text_columns=()) -> None:
        self.tables_layout.addWidget(_label(title, "sectionTitle"))
        if not rows:
            self.tables_layout.addWidget(_label("None.", "hint"))
            return
        table = DiagnosticTable(headers, rows, stretch, capped, text_columns)
        self.tables[key] = table
        self.tables_layout.addWidget(table)

    def _add_notes(self, lines, heading: str) -> None:
        if lines:
            self.tables_layout.addWidget(_label(heading + "\n" + "\n".join(f"• {line}" for line in lines),
                                                "warnings"))

    def _show_view(self, view: dm.DiagnosticView) -> None:
        self.statement.setText(view.statement)
        self.reason.setText(f"Why: {view.reason}")
        self.result_set.setText(f"Experimental modal set: {view.set_title}")
        self.source.setText(f"Experimental frequencies: {view.experimental_source}")
        self.provisional.setVisible(view.provisional)
        self._add_table("nearest", dm.NEAREST_TITLE, dm.NEAREST_HEADERS, view.nearest_rows, stretch=11,
                        capped=(10,))
        self.tables_layout.addWidget(_label(dm.SIGN_NOTE, "hint"))
        self._add_notes(view.range_warnings, "Experimental frequencies outside the extracted FE range:")
        self._add_notes(view.importer_warnings, "Importer warnings for this modal set:")
        self._add_table("fe", "Extracted FE frequencies (elastic modes)", dm.FE_HEADERS, view.fe_rows, stretch=1)
        self._add_table("rigid", "FE rigid-body modes (diagnostic records, not elastic modes)", dm.RIGID_HEADERS,
                        view.rigid_rows, stretch=2)
        self.tables_layout.addWidget(_label(f"Criterion: {view.rigid_criterion}.", "hint"))
        self._add_table("experimental", "Experimental frequencies (every record of the set)",
                        dm.EXPERIMENTAL_HEADERS, view.experimental_rows, stretch=3)

    def _refresh(self) -> None:
        state = self.slot.state
        fe, experimental = self.fe_preview, self.experimental_preview
        self.fe_input.setText("Not read" if fe is None else
                              f"{fe.manifest_path.name}: {len(fe.modes)} mode{'s' if len(fe.modes) != 1 else ''} "
                              "read")
        self.experimental_input.setText(
            "Not read" if experimental is None else
            f"{experimental.selected_path.name}: {len(experimental.sets)} modal "
            f"set{'s' if len(experimental.sets) != 1 else ''} read")
        self.set_combo.setEnabled(experimental is not None)
        reasons = self.unavailable()
        self.run_button.setEnabled(not reasons and state != dm.RUNNING)
        self.why_unavailable.setText("\n".join(reasons))
        self.why_unavailable.setVisible(bool(reasons))
        outcome = self.slot.outcome
        self.status.setObjectName("error" if state == dm.FAILED else "hint")
        _restyle(self.status)
        self.status.setText({dm.RUNNING: dm.RUNNING_TEXT,
                             dm.FAILED: outcome.error if outcome is not None else ""}.get(state, ""))
        self.status.setVisible(state in (dm.RUNNING, dm.FAILED))
        self._clear_tables()
        view = self.view
        self.result_card.setVisible(view is not None)
        if view is not None:
            self._show_view(view)
        self.badge.setText(self.status_text)
        self.badge.setProperty("state", "chosen" if view is not None else "empty")
        _restyle(self.badge)
        self.summary_note.setText(view.statement if view is not None else ANALYSIS_NOTE)
        values = ((f"{dm.STATUS}: {len(view.experimental_rows)} experimental, {len(view.fe_rows)} elastic FE and "
                   f"{len(view.rigid_rows)} rigid-body FE frequencies", dm.NOT_COMPUTED, dm.MODE_PAIRS)
                  if view is not None else ("not computed", "not computed", "none"))
        for caption, value in zip(("Frequencies", "MAC", "Mode pairs"), values):
            self.summary_values[caption].setText(value)
        self.changed.emit()


__all__ = ["DiagnosticPanel", "DiagnosticTable"]
