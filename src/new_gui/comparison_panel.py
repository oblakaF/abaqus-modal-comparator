"""NEW-GUI.6: the Analysis page's scientific workbench (PySide6).

One card, below the registration check, with the verified modal comparison of the read data:

1. **Visualization** on top, in two clearly separated tabs. *Computed pair*: after a verified comparison, the pair
   chosen in the table is drawn by the program's own pair drawing (``amplitude_correlation.render_pair_images``): the
   FE shape and the experimental shape on the same registered measured points, and their amplitude correlation.
   *Independent views (unpaired)*: one FE mode and one experimental record, each on its own coordinates
   (NEW-GUI.3 ``ShapePanel``), labelled as unpaired; there is no pseudo-overlay without a verified registration.
2. **Mode pairs**: the comparator's pairs (FE and experimental mode, frequencies, signed error, MAC, the
   comparator's status, measured DOFs and coverage, order changes, close modes). The table chooses the pair drawn.
3. **Scientific diagnostics**: the full MAC matrix (table and the program's drawing), the unpaired modes, the best
   candidate of every experimental mode with its rejection reasons, the warnings, the registration and geometry
   provenance, the admissibility gates and the limits.

Run verified modal comparison is enabled only when the NEW-GUI.5 check has verified an archived registration for
exactly the current FE results, experimental file and modal set; the comparison verifies it again before it runs
(``new_gui.comparison_model``). A replaced or cleared file, Inspect again, another set, a new check or a closed window
cancels a running comparison and removes the shown result, images included. Export report... writes the verified
comparison's report, or without one the diagnostic report of the frequency diagnostic shown, into a folder the user
chooses (``new_gui.report_export``).
"""

from __future__ import annotations

from pathlib import Path
import threading
from typing import Callable, Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QBoxLayout, QFileDialog, QFrame, QLabel, QPushButton,
                               QSizePolicy, QTabBar, QVBoxLayout, QWidget)

from new_gui import comparison_model as cm
from new_gui import diagnostic_model as dm
from new_gui import registration_check_model as rm
from new_gui import report_export as rx
from new_gui.diagnostic_panel import DiagnosticTable
from new_gui.shape_panel import ImageView, ShapePanel
from new_gui.workspace_state import EXPERIMENTAL, FE

WIDE_CONTENT = 1000  # from this content width of the window on, the views and commands sit side by side
VIEW_PAIR, VIEW_UNPAIRED = 0, 1
EXPORT_TITLE = "Choose the folder for the report"
EXPORT_HINT = ("Writes the verified comparison report (Excel, PDF and a JSON record with the sources' SHA-256), or, "
               "without a verified comparison, the diagnostic report of the frequency diagnostic shown (no MAC, no "
               "mode pairs). Only into the folder you choose; nothing else is written.")
NEED_RESULT = "Run the frequency diagnostic or the verified comparison first: the report states their result."


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


def _restyle(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()


class TabbedBox(QWidget):
    """Tabs whose pages lie in the page's own vertical layout: only the current page is visible, so a page that grows
    after it is shown (an image drawn later, a table built) always gets its full height. The tab bar scrolls its tabs
    in a narrow window instead of widening the page."""

    def __init__(self, name: str):
        super().__init__()
        self.setObjectName(name)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.bar = QTabBar()
        self.bar.setObjectName(f"{name}Tabs")
        self.bar.setExpanding(False)
        self.bar.setUsesScrollButtons(True)
        self.bar.setDocumentMode(True)
        self.bar.currentChanged.connect(self._show)
        layout.addWidget(self.bar)
        self.pages: list[QWidget] = []

    def addTab(self, page: QWidget, text: str) -> int:
        self.pages.append(page)
        self.layout().addWidget(page)
        index = self.bar.addTab(text)
        self._show(self.bar.currentIndex())
        return index

    def _show(self, index: int) -> None:
        for position, page in enumerate(self.pages):
            page.setVisible(position == index)

    def count(self) -> int:
        return self.bar.count()

    def currentIndex(self) -> int:
        return self.bar.currentIndex()

    def setCurrentIndex(self, index: int) -> None:
        self.bar.setCurrentIndex(index)

    def tabText(self, index: int) -> str:
        return self.bar.tabText(index)

    def isTabEnabled(self, index: int) -> bool:
        return self.bar.isTabEnabled(index)

    def setTabEnabled(self, index: int, enabled: bool) -> None:
        self.bar.setTabEnabled(index, enabled)

    def widget(self, index: int) -> QWidget:
        return self.pages[index]


class PairTable(DiagnosticTable):
    """The pair table: one row is chosen at a time and chooses the pair drawn."""

    def __init__(self, headers, rows, stretch: int, capped=(), text_columns=()):
        super().__init__(headers, rows, stretch, capped, text_columns)
        self.setObjectName("pairTable")
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)


def _mark_cells(table: DiagnosticTable, cells) -> None:
    """Bold, tinted cells: the assigned pairs in the MAC table."""
    font = QFont(table.font())
    font.setBold(True)
    for row, column in cells:
        item = table.item(row, column + 1)
        if item is not None:
            item.setFont(font)
            item.setBackground(QBrush(QColor("#dbeafe")))
            item.setToolTip(item.toolTip() + " — assigned pair")


class _Bridge(QObject):
    """Carries worker outcomes to the window's thread (queued signals)."""

    compared = Signal(object)
    drawn = Signal(object)
    exported = Signal(object)


class ComparisonPanel(QFrame):
    """The verified modal comparison workbench card."""

    changed = Signal()  # the shown state changed (the window updates its status bar and the materials page)

    def __init__(self, ask_folder: Optional[Callable[[], str]] = None):
        super().__init__()
        self.setObjectName("card")
        self.fe_preview = None
        self.experimental_preview = None
        self.set_index: Optional[int] = None
        self.registration_view: Optional[rm.RegistrationView] = None
        self.registration_refusal = ""
        self.diagnostic = None  # the frequency diagnostic shown for the current inputs (for the diagnostic report)
        self.slot = cm.ComparisonSlot()
        self.discarded = 0  # outcomes of cancelled or stale requests, never shown
        self.images: dict[int, cm.PairImages] = {}
        self.pair_index: Optional[int] = None
        self._draw_token = 0
        self._draw_cancel: Optional[threading.Event] = None
        self._exporting = False
        self.export_message = ""
        self._ask_folder = ask_folder or self._dialog_folder
        self._threads: list[threading.Thread] = []
        self._bridge = _Bridge(self)
        self._bridge.compared.connect(self._compared)
        self._bridge.drawn.connect(self._drawn)
        self._bridge.exported.connect(self._exported)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(_label(cm.TITLE, "cardTitle"))
        self.badge = _label(cm.NOT_RUN, "badge", wrap=False)
        layout.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(_label(cm.HINT, "hint"))
        self.registration_line = _label("", "hint")
        layout.addWidget(self.registration_line)
        buttons = QBoxLayout(QBoxLayout.Direction.TopToBottom)  # side by side in a wide window (set_narrow)
        self.buttons = buttons
        self.run_button = QPushButton(cm.RUN)
        self.run_button.setObjectName("primary")
        self.run_button.setToolTip("Verify the archived registration again and run the scientific comparator on the "
                                   "read data. Available only after Check reference registration verified it.")
        self.run_button.clicked.connect(self.run)
        buttons.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.export_button = QPushButton(rx.EXPORT)
        self.export_button.setObjectName("exportReport")
        self.export_button.setToolTip(EXPORT_HINT)
        self.export_button.clicked.connect(lambda: self.export())
        buttons.addWidget(self.export_button, 0, Qt.AlignmentFlag.AlignLeft)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self.why_unavailable = _label("", "hint")
        layout.addWidget(self.why_unavailable)
        self.status = _label("", "hint")
        layout.addWidget(self.status)
        self.export_status = _label("", "hint")
        layout.addWidget(self.export_status)
        self.statement = _label("", "")
        layout.addWidget(self.statement)

        layout.addWidget(_label("Shapes", "sectionTitle"))
        self.views = TabbedBox("shapeViews")
        self.views.addTab(self._build_pair_view(), "Computed pair")
        self.views.addTab(self._build_unpaired_view(), "Independent views (unpaired)")
        layout.addWidget(self.views)

        layout.addWidget(_label("Mode pairs — the comparator's assignment", "sectionTitle"))
        self.pairs_box = QWidget()
        self.pairs_layout = QVBoxLayout(self.pairs_box)
        self.pairs_layout.setContentsMargins(0, 0, 0, 0)
        self.pairs_layout.setSpacing(6)
        layout.addWidget(self.pairs_box)
        self.pair_table: Optional[PairTable] = None

        layout.addWidget(_label("Scientific diagnostics", "sectionTitle"))
        self.details = TabbedBox("scientificDiagnostics")
        self.detail_layouts = {}
        for name in ("MAC matrix", "Unpaired and rejected", "Warnings", "Registration and geometry", "Limits"):
            page = QWidget()
            inner = QVBoxLayout(page)
            inner.setContentsMargins(0, 8, 0, 0)
            inner.setSpacing(6)
            self.detail_layouts[name] = inner
            self.details.addTab(page, name)
        layout.addWidget(self.details)
        self.tables: dict[str, DiagnosticTable] = {}
        self._shown_view = 0  # never a view: the first refresh builds the empty state
        self._refresh()

    # ------------------------------------------------------------------------------------------ building

    def _build_pair_view(self) -> QWidget:
        page = QWidget()
        inner = QVBoxLayout(page)
        inner.setContentsMargins(0, 8, 0, 0)
        inner.setSpacing(6)
        self.pair_badge = _label("", "badge", wrap=False)
        inner.addWidget(self.pair_badge, 0, Qt.AlignmentFlag.AlignLeft)
        self.pair_note = _label(cm.PAIR_NOTE, "hint")
        inner.addWidget(self.pair_note)
        self.pair_facts = _label("", "")
        inner.addWidget(self.pair_facts)
        self.pair_status = _label("", "hint")
        inner.addWidget(self.pair_status)
        self.pair_images_row = QBoxLayout(QBoxLayout.Direction.TopToBottom)
        self.pair_images_row.setSpacing(10)
        self.pair_views = []
        for _key, caption in cm.PAIR_CAPTIONS:
            column = QVBoxLayout()
            column.setSpacing(4)
            view = ImageView()
            column.addWidget(view)
            text = _label(caption, "hint")
            column.addWidget(text)
            self.pair_views.append((view, text))
            self.pair_images_row.addLayout(column, 1)
        inner.addLayout(self.pair_images_row)
        return page

    def _build_unpaired_view(self) -> QWidget:
        page = QWidget()
        inner = QVBoxLayout(page)
        inner.setContentsMargins(0, 8, 0, 0)
        inner.setSpacing(6)
        self.unpaired_badge = _label("UNPAIRED SHAPES", "badge", wrap=False)
        self.unpaired_badge.setProperty("state", "chosen")
        inner.addWidget(self.unpaired_badge, 0, Qt.AlignmentFlag.AlignLeft)
        inner.addWidget(_label(cm.UNPAIRED_NOTE, "hint"))
        self.unpaired_empty = _label("Inspect the FE and experimental files on the Workspace page to view their "
                                     "shapes here.", "hint")
        inner.addWidget(self.unpaired_empty)
        self.shapes = {FE: ShapePanel(FE), EXPERIMENTAL: ShapePanel(EXPERIMENTAL)}
        self.unpaired_row = QBoxLayout(QBoxLayout.Direction.TopToBottom)
        self.unpaired_row.setSpacing(10)
        for kind in (FE, EXPERIMENTAL):
            self.unpaired_row.addWidget(self.shapes[kind], 1, Qt.AlignmentFlag.AlignTop)
        inner.addLayout(self.unpaired_row)
        return page

    # ------------------------------------------------------------------------------------------ inputs

    def set_inputs(self, fe_preview, experimental_preview, set_index: Optional[int]) -> None:
        """The read previews and the chosen set; any change removes the result, its images included."""
        for kind, preview in ((FE, fe_preview), (EXPERIMENTAL, experimental_preview)):
            self.shapes[kind].set_preview(preview)
        if (fe_preview is self.fe_preview and experimental_preview is self.experimental_preview
                and set_index == self.set_index):
            return
        self.fe_preview, self.experimental_preview, self.set_index = fe_preview, experimental_preview, set_index
        self.diagnostic = None
        self._reset()

    def set_registration(self, view: Optional[rm.RegistrationView], refusal: str = "") -> None:
        """The registration check's verified view for the current inputs (or None); a new check removes the result."""
        self.registration_refusal = refusal
        if view is self.registration_view:
            self._refresh()
            return
        self.registration_view = view
        self._reset()

    def set_diagnostic(self, diagnostic) -> None:
        """The frequency diagnostic shown for the current inputs (the diagnostic report states it), or None."""
        if diagnostic is not self.diagnostic:
            self.diagnostic = diagnostic
            self._refresh()

    def unavailable(self) -> tuple:
        return cm.unavailable(self.fe_preview, self.experimental_preview, self.set_index, self.registration_view)

    def ready(self) -> bool:
        return not self.unavailable()

    def _reset(self) -> None:
        self.slot.reset()
        self._forget_images()
        if not self._exporting:
            self.export_message = ""  # the message of a written report belongs to the result that is gone
        self._refresh()

    def _forget_images(self) -> None:
        if self._draw_cancel is not None:
            self._draw_cancel.set()
        self._draw_token += 1
        self._draw_cancel = None
        self.images = {}
        self.pair_index = None

    # ------------------------------------------------------------------------------------------ running

    def run(self) -> bool:
        """Run the verified comparison in a worker thread; returns False when it cannot run now."""
        if not self.ready() or self.slot.state == cm.RUNNING:
            return False
        request = (self.fe_preview, self.experimental_preview, self.set_index, self.registration_view.registration)
        token, cancel_event = self.slot.start(request)
        self._forget_images()
        self._start(self._work, (*request, token, cancel_event), "new-gui-comparison")
        self._refresh()
        return True

    def _start(self, target, args, name: str) -> None:
        worker = threading.Thread(target=target, args=args, name=name, daemon=True)
        self._threads = [thread for thread in self._threads if thread.is_alive()] + [worker]
        worker.start()

    def _work(self, fe_preview, experimental_preview, set_index, registration, token, cancel_event) -> None:
        outcome = cm.run_compare(fe_preview, experimental_preview, set_index, registration, token, cancel_event)
        try:
            self._bridge.compared.emit(outcome)
        except RuntimeError:  # the panel is already gone
            pass

    def _compared(self, outcome: cm.ComparisonOutcome) -> None:
        if not self.slot.finish(outcome):
            self.discarded += 1  # a cancelled or stale request: the current state is kept
            return
        self._refresh()
        if self.view is not None and self.view.pair_rows:
            self.select_pair(0)  # the first pair is drawn; the table chooses another

    def select_pair(self, row: int) -> bool:
        """Draw the pair of table row ``row`` (cached per result); returns False when there is no such pair."""
        view = self.view
        if view is None or not 0 <= row < len(view.pair_rows):
            return False
        index = view.pair_rows[row].index
        self.pair_index = index
        if self.pair_table is not None and self.pair_table.currentRow() != row:
            self.pair_table.blockSignals(True)
            self.pair_table.selectRow(row)
            self.pair_table.blockSignals(False)
        if index not in self.images:
            if self._draw_cancel is not None:
                self._draw_cancel.set()
            self._draw_token += 1
            self._draw_cancel = threading.Event()
            self._start(self._draw, (self.slot.outcome.result, index, self._draw_token, self._draw_cancel),
                        "new-gui-pair-images")
        self.views.setCurrentIndex(VIEW_PAIR)
        self._show_pair()
        return True

    def _draw(self, result, index, token, cancel_event) -> None:
        images = cm.run_pair_images(result, index, token, cancel_event)
        try:
            self._bridge.drawn.emit(images)
        except RuntimeError:
            pass

    def _drawn(self, images: cm.PairImages) -> None:
        if images.token != self._draw_token or images.cancelled or self.view is None:
            self.discarded += 1  # images of a removed result or of a replaced request are never shown
            return
        self._draw_cancel = None
        self.images[images.index] = images
        self._show_pair()

    def drawing(self) -> bool:
        return self._draw_cancel is not None

    def busy(self) -> bool:
        return (self.slot.state == cm.RUNNING or self._exporting or self.drawing()
                or any(thread.is_alive() for thread in self._threads)
                or any(panel.busy() for panel in self.shapes.values()))

    def cancel(self) -> None:
        for panel in self.shapes.values():
            panel.cancel()
        self._reset()

    # ------------------------------------------------------------------------------------------ export

    def export_ready(self) -> tuple:
        """(kind, reason): 'verified', 'diagnostic' or '' with the reason the export is unavailable."""
        if self._exporting:
            return "", "An export is running."
        if self.view is not None:
            return "verified", ""
        if self.slot.state == cm.RUNNING:
            return "", "The comparison is running."
        if self.diagnostic is not None and self.fe_preview is not None and self.experimental_preview is not None \
                and self.set_index is not None:
            return "diagnostic", ""
        return "", NEED_RESULT

    def _dialog_folder(self) -> str:
        from services.report_directory import default_report_directory

        return QFileDialog.getExistingDirectory(self, EXPORT_TITLE, str(default_report_directory()))

    def export(self, folder: Optional[str] = None) -> bool:
        """Write the report of the result shown into a folder the user chooses; returns False when nothing starts."""
        kind, _reason = self.export_ready()
        if not kind:
            return False
        if folder is None:
            folder = self._ask_folder()
        if not folder or not str(folder).strip():  # cancelled: nothing is written
            return False
        if kind == "verified":
            outcome = self.slot.outcome
            args = (kind, (outcome.result, outcome.bound, outcome.view, self.fe_preview, self.experimental_preview,
                           self.set_index, folder))
        else:
            reason = (f"no archived physical registration applies: {self.registration_refusal}"
                      if self.registration_refusal else dm.REASON)
            args = (kind, (self.fe_preview, self.experimental_preview, self.set_index, self.diagnostic, reason,
                           folder))
        self._exporting = True
        self.export_message = "Writing the report..."
        self._start(self._export_work, args, "new-gui-export")
        self._refresh()
        return True

    def _export_work(self, kind: str, args: tuple) -> None:
        try:
            written = rx.export_verified(*args) if kind == "verified" else rx.export_diagnostic(*args)
            message = (("Verified comparison report" if kind == "verified" else "Diagnostic report (no MAC, no mode "
                        "pairs)") + " written:\n" + "\n".join(str(path) for path in written))
        except Exception as error:  # noqa: BLE001  (refusals, unwritable folders, writer errors)
            message = f"The report was not written ({type(error).__name__}: {error})."
        try:
            self._bridge.exported.emit(message)
        except RuntimeError:
            pass

    def _exported(self, message: str) -> None:
        self._exporting = False
        self.export_message = message
        self._refresh()

    # ------------------------------------------------------------------------------------------ display

    @property
    def view(self) -> Optional[cm.ComparisonView]:
        outcome = self.slot.outcome
        return outcome.view if self.slot.state == cm.DONE and outcome is not None else None

    @property
    def status_text(self) -> str:
        view = self.view
        return f"{view.status} ({len(view.pair_rows)} pairs)" if view is not None else ""

    def _table(self, layout, key: str, title: str, headers, rows, stretch: int, capped=(), text_columns=(),
               cls=DiagnosticTable):
        if title:
            layout.addWidget(_label(title, "sectionTitle"))
        if not rows:
            layout.addWidget(_label("None.", "hint"))
            return None
        table = cls(headers, rows, stretch, capped, text_columns)
        self.tables[key] = table
        layout.addWidget(table)
        return table

    def _notes(self, layout, heading: str, lines, name: str = "hint") -> None:
        if lines:
            layout.addWidget(_label((heading + "\n" if heading else "") + "\n".join(f"• {line}" for line in lines),
                                    name))

    def _refresh(self) -> None:
        state = self.slot.state
        registration = self.registration_view
        self.registration_line.setText(
            f"Archived registration: {registration.specimen} {registration.fixture_id}, "
            f"{registration.registration[:12]}… (verified by the check above)" if registration is not None
            else "Archived registration: not verified for these data.")
        reasons = self.unavailable()
        self.run_button.setEnabled(not reasons and state != cm.RUNNING)
        self.why_unavailable.setText("\n".join(reasons))
        self.why_unavailable.setVisible(bool(reasons))
        outcome = self.slot.outcome
        self.badge.setText({cm.RUNNING: cm.RUNNING_BADGE, cm.REFUSED: cm.REFUSED_BADGE, cm.FAILED: cm.FAILED_BADGE}
                           .get(state, self.view.status if self.view is not None else cm.NOT_RUN))
        self.badge.setProperty("state", {cm.DONE: "read", cm.REFUSED: "blocked", cm.FAILED: "blocked",
                                         cm.RUNNING: "chosen"}.get(state, "empty"))
        _restyle(self.badge)
        self.status.setObjectName("error" if state in (cm.FAILED, cm.REFUSED) else "hint")
        _restyle(self.status)
        self.status.setText({cm.RUNNING: cm.RUNNING_TEXT,
                             cm.REFUSED: f"Not run: {outcome.refusal}" if outcome is not None else "",
                             cm.FAILED: outcome.error if outcome is not None else ""}.get(state, ""))
        self.status.setVisible(state in (cm.RUNNING, cm.REFUSED, cm.FAILED))
        kind, export_reason = self.export_ready()
        self.export_button.setEnabled(bool(kind))
        self.export_button.setToolTip(EXPORT_HINT if kind else f"{EXPORT_HINT}\n{export_reason}")
        self.export_status.setText(self.export_message)
        self.export_status.setVisible(bool(self.export_message))
        view = self.view
        self.statement.setText(view.statement if view is not None else "")
        self.statement.setVisible(view is not None)
        if view is not self._shown_view or self.pair_table is None and view is not None and view.pair_rows:
            self._shown_view = view  # the tables and the MAC image are built once per result
            self._show_pairs(view)
            self._show_details(view, outcome)
        self.views.setTabEnabled(VIEW_PAIR, view is not None and bool(view.pair_rows))
        if view is None or not view.pair_rows:
            self.views.setCurrentIndex(VIEW_UNPAIRED)
        self.unpaired_empty.setVisible(self.fe_preview is None and self.experimental_preview is None)
        self._show_pair()
        self.changed.emit()

    def _show_pairs(self, view: Optional[cm.ComparisonView]) -> None:
        _clear(self.pairs_layout)
        self.pair_table = None
        self.tables.pop("pairs", None)
        if view is None:
            self.pairs_layout.addWidget(_label("No verified comparison: no mode pairs and no MAC are shown. The "
                                               "frequency diagnostic is frequency proximity only.", "hint"))
            return
        if not view.pair_rows:
            self.pairs_layout.addWidget(_label(cm.NO_PAIR_TEXT, ""))
        else:
            self.pair_table = self._table(self.pairs_layout, "pairs", "", cm.PAIR_HEADERS,
                                          [row.cells for row in view.pair_rows], stretch=12, capped=(6, 7),
                                          text_columns=(7, 11, 13), cls=PairTable)
            self.pair_table.itemSelectionChanged.connect(self._table_selection)
            if self.pair_index is not None:
                rows = [r.index for r in view.pair_rows]
                if self.pair_index in rows:
                    self.pair_table.blockSignals(True)
                    self.pair_table.selectRow(rows.index(self.pair_index))
                    self.pair_table.blockSignals(False)
        self.pairs_layout.addWidget(_label(cm.SIGN_NOTE, "hint"))
        self.pairs_layout.addWidget(_label(f"{view.target_counts} {cm.ENGINEERING_TARGET}", "hint"))
        self.pairs_layout.addWidget(_label(view.auto_id_note, "warnings"))

    def _table_selection(self) -> None:
        if self.pair_table is not None and self.pair_table.selectedItems():
            self.select_pair(self.pair_table.currentRow())

    def _show_details(self, view: Optional[cm.ComparisonView], outcome) -> None:
        for key in [k for k in self.tables if k != "pairs"]:
            self.tables.pop(key)
        for name, layout in self.detail_layouts.items():
            _clear(layout)
            if view is None:
                layout.addWidget(_label("Shown after a verified comparison.", "hint"))
        self.details.setVisible(view is not None)
        if view is None:
            return
        mac = self.detail_layouts["MAC matrix"]
        mac.addWidget(_label(f"MAC on the registered measured DOFs only: {len(view.mac_fe_modes)} elastic FE modes × "
                             f"{len(view.mac_experimental_modes)} experimental modes. Assigned pairs are marked. "
                             f"{cm.MAC_NOT_COMPUTED} = not computable on the measured DOFs.", "hint"))
        headers = ("FE \\ Exp",) + tuple(str(n) for n in view.mac_experimental_modes)
        table = self._table(mac, "mac", "", headers,
                            [(str(fe),) + cells for fe, cells in zip(view.mac_fe_modes, view.mac_cells)],
                            stretch=len(headers) - 1)
        if table is not None:
            _mark_cells(table, view.assigned_cells)
        image = ImageView()
        mac.addWidget(image)
        if outcome is not None and outcome.mac_image:
            image.set_image(outcome.mac_image)
        mac.addWidget(_label("Drawn by the program's MAC matrix drawing (reporting_hardening.render_mac_matrix).",
                             "hint"))
        unpaired = self.detail_layouts["Unpaired and rejected"]
        self._table(unpaired, "unmatched_fe", "FE elastic modes without an admissible counterpart (comparator)",
                    cm.UNMATCHED_HEADERS, view.unmatched_fe_rows, stretch=1)
        self._table(unpaired, "unmatched_exp", "Experimental modes inside the FE comparison band without a counterpart "
                    "(comparator)", cm.UNMATCHED_HEADERS, view.unmatched_experimental_rows, stretch=1)
        self._notes(unpaired, "Every experimental record of the set without a pair:", view.unpaired_experimental)
        self._table(unpaired, "rigid", "FE rigid-body modes excluded by the comparator's shape criterion",
                    cm.RIGID_HEADERS, view.rigid_rows, stretch=2)
        self._table(unpaired, "candidates", "Best-MAC candidate of every experimental mode and why it was rejected",
                    cm.CANDIDATE_HEADERS, view.candidate_rows, stretch=9, text_columns=(7, 9))
        unpaired.addWidget(_label("Rejected by: frequency = outside the frequency gate; mac = below the MAC gate; "
                                  "mac_unavailable = no MAC on the measured DOFs; coverage = too few measured DOFs or "
                                  "points. A candidate is diagnostic evidence only; only the table above holds pairs.",
                                  "hint"))
        warnings = self.detail_layouts["Warnings"]
        self._notes(warnings, "Close or degenerate modes (the comparator's groups):", view.close_groups, "warnings")
        self._notes(warnings, "Warnings of the comparison:", view.warnings, "warnings")
        provenance = self.detail_layouts["Registration and geometry"]
        self._table(provenance, "provenance", "", ("Item", "Value"), view.provenance, stretch=1)
        self._table(provenance, "gates", "Admissibility gates applied by the comparator (unchanged)",
                    ("Gate", "Value"), view.gates, stretch=1)
        limits = self.detail_layouts["Limits"]
        self._notes(limits, "", view.limits)
        limits.addWidget(_label(view.auto_id_note, "warnings"))

    def _show_pair(self) -> None:
        view = self.view
        row = None
        if view is not None and self.pair_index is not None:
            row = next((r for r in view.pair_rows if r.index == self.pair_index), None)
        if row is None:
            self.pair_badge.setText("No computed pair shown")
            self.pair_badge.setProperty("state", "empty")
            _restyle(self.pair_badge)
            self.pair_facts.setText("")
            self.pair_status.setText("")
            for image, _text in self.pair_views:
                image.clear_image()
            return
        self.pair_badge.setText(f"COMPUTED PAIR FE {row.abaqus_mode} / Exp {row.experimental_mode}")
        self.pair_badge.setProperty("state", "read")
        _restyle(self.pair_badge)
        cells = dict(zip(cm.PAIR_HEADERS, row.cells))
        self.pair_facts.setText(
            f"Verified archived registration {view.fixture_id} ({view.registration[:12]}…). "
            f"FE mode {cells['FE mode']}: {cells['FE (Hz)']} Hz · Exp record {cells['Exp record']} (mode "
            f"{cells['Exp mode']}): {cells['Exp (Hz)']} Hz · error {cells['Error (%)']} % · MAC {cells['MAC']} · "
            f"{cells['Comparator status']} · measured DOFs {cells['Measured DOFs']} ({cells['DOF coverage']}) · "
            f"points {cells['Points']}")
        images = self.images.get(row.index)
        self.pair_status.setObjectName("error" if images is not None and images.error else "hint")
        _restyle(self.pair_status)
        self.pair_status.setText("Drawing the pair..." if images is None else images.error)
        for position, (image, _text) in enumerate(self.pair_views):
            if images is not None and position < len(images.images):
                image.set_image(images.images[position][1])
            else:
                image.clear_image()

    def set_narrow(self, narrow: bool) -> None:
        """Stack the commands and views in a narrow window (decided by the window from its content width: the
        panel's own width cannot decide it, since side-by-side views set its minimum width)."""
        direction = QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight
        for row in (self.buttons, self.unpaired_row, self.pair_images_row):
            if row.direction() != direction:
                row.setDirection(direction)


__all__ = ["ComparisonPanel", "PairTable"]
