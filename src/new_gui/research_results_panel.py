"""PRIORITY-5A: the Research Results page (PySide6; RESEARCH_ONLY).

The page reads the archived research snapshot (``services.research_results_reader``) only when it is first shown,
and the optional local research record only when the user chooses it with Load local research record...; nothing is
searched for and nothing is computed or started. The specimen chooser (PLATE by default, SP-13, SP-10) switches every
section. The banner says whether the Workspace inputs are the research inputs (by SHA-256); otherwise the tables are
an ARCHIVED RESEARCH SNAPSHOT — NOT VERIFIED FOR CURRENT WORKSPACE INPUTS, still viewable.

PRIORITY-7: for SP-10 the historical PRIORITY-1 table (A) is followed by B. Updated SP-10 FE Results — PRIORITY-6, built
by ``services.sp10_fe_research`` from the small archived PRIORITY-6 records (never the 3.1 GB package): the FE7–FE25
table and the frequency-only diagnostic of EXP1–EXP12 (FREQUENCY_PROXIMITY_ONLY — NOT A CONFIRMED MODE PAIR). Its own
Workspace link (both SHA-256, the chosen modal set, the FE modes read) is separate from the historical banner and
always shows PHYSICAL_REGISTRATION_NOT_VERIFIED.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from new_gui import research_results_model as rm
from new_gui.diagnostic_panel import DiagnosticTable
from services import research_results_reader as rr
from services import sp10_fe_research as sf

_VIRIDIS = ((0.0, (68, 1, 84)), (0.25, (59, 82, 139)), (0.5, (33, 145, 140)), (0.75, (94, 201, 98)),
            (1.0, (253, 231, 37)))
AMBIGUOUS_BRUSH = QColor(255, 236, 179)
ADDED_BRUSH = QColor(197, 225, 165)  # PRIORITY-7: FE16–FE25, added by PRIORITY-6
DEFAULT_RECORD_FOLDER = Path(r"D:\git\abaqus-modal-comparator-work\research\REAL_MODAL_MATCHING_202610")


def colour(value: float) -> QColor:
    value = min(1.0, max(0.0, value))
    for (a, ca), (b, cb) in zip(_VIRIDIS, _VIRIDIS[1:]):
        if value <= b:
            t = (value - a) / (b - a)
            return QColor(*[round(x + (y - x) * t) for x, y in zip(ca, cb)])
    return QColor(*_VIRIDIS[-1][1])


def _label(text: str = "", name: str = "") -> QLabel:
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    label.setMinimumWidth(0)
    return label


def _card(title: str) -> tuple:
    card = QFrame()
    card.setObjectName("card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(8)
    layout.addWidget(_label(title, "cardTitle"))
    return card, layout


class MacHeatmap(QTableWidget):
    """A 0–1 MAC matrix as coloured cells with their values; a click reports the cell. Never a confirmed MAC."""

    def __init__(self, view: dict):
        matrix = view["matrix"]
        super().__init__(len(matrix.values), len(matrix.fe_modes))
        self.setObjectName("researchMacMatrix")
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setHorizontalHeaderLabels(list(view["cols"]))
        self.setVerticalHeaderLabels(list(view["rows"]))
        for i, row in enumerate(matrix.values):
            for j, value in enumerate(row):
                item = QTableWidgetItem(f"{value:.2f}")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setBackground(QBrush(colour(value)))
                item.setForeground(QBrush(QColor("white") if value < 0.6 else QColor("black")))
                item.setToolTip(f"{view['rows'][i]} × {view['cols'][j]}: {value:.4f}")
                self.setItem(i, j, item)
        self.horizontalHeader().setDefaultSectionSize(52)
        self.horizontalHeader().setMinimumSectionSize(44)
        self.resizeRowsToContents()
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)  # inside the matrix, not the page
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)
        height = self.horizontalHeader().height() + sum(self.rowHeight(i) for i in range(self.rowCount()))
        self.setFixedHeight(height + self.horizontalScrollBar().sizeHint().height() + 6)


class ResearchResultsPanel(QWidget):
    """The page's content."""

    def __init__(self, ask_file: Optional[Callable[[str], str]] = None, root: Path = rr.REPO):
        super().__init__()
        self._ask_file = ask_file or self._dialog_file
        self.root = root
        self.snapshot: Optional[rr.Snapshot] = None
        self.snapshot_error = ""
        self.record: Optional[rr.LocalRecord] = None
        self.record_error = ""
        self.workspace = (None, None)  # experimental identity, FE identity
        self.context: Optional[dict] = None  # PRIORITY-7: the chosen modal set and the FE modes read
        self.sp10: Optional[sf.Sp10FeResults] = None  # PRIORITY-7: the small archived PRIORITY-6 records only
        self.sp10_rows: tuple = ()
        self.sp10_error = ""
        self.tables: dict = {}
        self.heatmap: Optional[MacHeatmap] = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        head, head_layout = _card(rm.TITLE)
        head_layout.addWidget(_label(rm.SUBTITLE, "hint"))
        head_layout.addWidget(_label(rm.LABELS_LINE, "warnings"))
        self.status_line = _label("", "hint")  # filled on the first show: nothing archived is shown at start-up
        head_layout.addWidget(self.status_line)
        chooser = QHBoxLayout()
        chooser.addWidget(_label("Specimen", ""), 0)
        self.specimen_combo = QComboBox()
        self.specimen_combo.setObjectName("researchSpecimen")
        self.specimen_combo.currentIndexChanged.connect(lambda _i: self._refresh())
        chooser.addWidget(self.specimen_combo, 1)
        head_layout.addLayout(chooser)
        self.banner = _label("", "warnings")
        self.banner.setObjectName("researchBanner")
        head_layout.addWidget(self.banner)
        self.identity = _label("", "hint")
        head_layout.addWidget(self.identity)
        self.error = _label("", "error")
        head_layout.addWidget(self.error)
        layout.addWidget(head)
        self.matching_card, self.matching_layout = _card("Mode matching — every experimental mode")
        layout.addWidget(self.matching_card)
        # PRIORITY-7: SP-10 only, beside the historical table; its texts are set on the page's first show (no archived
        # text exists in the window at start-up)
        self.sp10_card, sp10_layout = _card("")
        self.sp10_title = sp10_layout.itemAt(0).widget()
        self.sp10_status = _label("", "warnings")
        sp10_layout.addWidget(self.sp10_status)
        self.sp10_proximity = _label("", "error")
        self.sp10_proximity.setObjectName("sp10Proximity")
        bold = self.sp10_proximity.font()
        bold.setBold(True)
        self.sp10_proximity.setFont(bold)
        sp10_layout.addWidget(self.sp10_proximity)
        self.sp10_link = _label("", "warnings")  # the Workspace link of PRIORITY-6 (separate from the banner above)
        self.sp10_link.setObjectName("sp10WorkspaceLink")
        sp10_layout.addWidget(self.sp10_link)
        self.sp10_registration = _label("", "error")
        self.sp10_registration.setObjectName("sp10Registration")
        sp10_layout.addWidget(self.sp10_registration)
        self.sp10_link_lines = _label("", "hint")
        self.sp10_link_lines.setObjectName("sp10WorkspaceLines")
        sp10_layout.addWidget(self.sp10_link_lines)
        self.sp10_package = _label("", "warnings")
        self.sp10_package.setObjectName("sp10PackageStatus")
        sp10_layout.addWidget(self.sp10_package)
        self.sp10_body = QVBoxLayout()
        sp10_layout.addLayout(self.sp10_body)
        layout.addWidget(self.sp10_card)
        self.mac_card, self.mac_layout = _card("Research MAC matrix")
        self.load_button = QPushButton(rm.LOAD_RECORD)
        self.load_button.setObjectName("loadResearchRecord")
        self.load_button.clicked.connect(lambda: self.load_record())
        self.mac_layout.addWidget(self.load_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.mac_warning = _label(rm.MAC_WARNING, "error")
        font = self.mac_warning.font()
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() * 1.15)
        self.mac_warning.setFont(font)
        self.mac_layout.addWidget(self.mac_warning)
        self.mac_body = QVBoxLayout()
        self.mac_layout.addLayout(self.mac_body)
        layout.addWidget(self.mac_card)
        self.sens_card, self.sens_layout = _card("FE Parameter Sensitivities")
        layout.addWidget(self.sens_card)
        self.inverse_card, self.inverse_layout = _card("Inverse Parameter Study — Research Only")
        self.scenario_combo = QComboBox()
        self.scenario_combo.setObjectName("researchScenario")
        for key in rm.SCENARIO_ORDER:
            self.scenario_combo.addItem(key, key)
        self.scenario_combo.currentIndexChanged.connect(lambda _i: self._refresh_scenario())
        self.inverse_static = QVBoxLayout()
        self.inverse_layout.addLayout(self.inverse_static)
        row = QHBoxLayout()
        row.addWidget(_label("Scenario", ""), 0)
        row.addWidget(self.scenario_combo, 1)
        self.inverse_layout.addLayout(row)
        self.scenario_body = QVBoxLayout()
        self.inverse_layout.addLayout(self.scenario_body)
        layout.addWidget(self.inverse_card)
        self.plate_only = _label(rm.PLATE_ONLY, "hint")
        layout.addWidget(self.plate_only)
        layout.addStretch(1)
        self._refresh()

    # ------------------------------------------------------------------------------------------ data

    def load(self) -> None:
        """Read the archived snapshot (once; on the page's first show). A refusal is shown, never replaced."""
        if self.snapshot is not None or self.snapshot_error:
            return
        self.specimen_combo.blockSignals(True)
        for key in rm.SPECIMEN_ORDER:
            self.specimen_combo.addItem(rr.SPECIMENS[key].title, key)
        self.specimen_combo.setCurrentIndex(0)  # PLATE by default
        self.specimen_combo.blockSignals(False)
        self.status_line.setText(rm.SCIENTIFIC_STATUS)
        try:
            self.snapshot = rr.load_snapshot(self.root)
        except rr.SnapshotRefused as error:
            self.snapshot_error = f"The archived research snapshot is not shown: {error}"
        self._load_sp10()
        self.sp10_title.setText(rm.SP10_TITLE)
        self.sp10_status.setText(rm.SP10_STATUS)
        self._refresh()

    def _load_sp10(self) -> None:
        """PRIORITY-7: the small archived PRIORITY-6 records (never the extracted package) and the frequency-only
        diagnostic of the 12 experimental records of the historical table. A refusal is shown, never replaced."""
        try:
            if self.snapshot is None:
                raise sf.Sp10ResearchRefused("the experimental frequencies of the historical PRIORITY-1 table are not "
                                             "available")
            self.sp10 = sf.load_results(self.root)
            self.sp10_rows = sf.frequency_diagnostic(
                self.sp10, [(r.exp_no, r.f_exp_hz) for r in self.snapshot.matching["SP-10"]])
        except sf.Sp10ResearchRefused as error:
            self.sp10, self.sp10_rows = None, ()
            self.sp10_error = f"The updated SP-10 FE results of PRIORITY-6 are not shown: {error}"

    def specimen(self) -> str:
        return self.specimen_combo.currentData() or rm.SPECIMEN_ORDER[0]

    def set_specimen(self, key: str) -> None:
        self.specimen_combo.setCurrentIndex(rm.SPECIMEN_ORDER.index(key))

    def set_scenario(self, key: str) -> None:
        self.scenario_combo.setCurrentIndex(rm.SCENARIO_ORDER.index(key))

    def set_workspace(self, experimental_identity, fe_identity, context: Optional[dict] = None) -> None:
        """The identities of the files read in the Workspace and (PRIORITY-7) the chosen modal set and FE modes; a
        change is shown at once, so no earlier positive link is kept."""
        self.workspace = (experimental_identity, fe_identity)
        self.context = context
        self._refresh_banner()

    def _dialog_file(self, start: str) -> str:
        path, _filter = QFileDialog.getOpenFileName(self, "Choose the local research record (matching_record.json)",
                                                    start, "Research record (*.json)")
        return path

    def load_record(self, path: Optional[str] = None) -> bool:
        start = str(DEFAULT_RECORD_FOLDER) if DEFAULT_RECORD_FOLDER.is_dir() else str(Path.home())
        path = path if path is not None else self._ask_file(start)
        if not path:
            return False
        try:
            self.record, self.record_error = rr.load_local_record(path), ""
        except rr.RecordRefused as error:
            self.record, self.record_error = None, f"The record is not used: {error}"
        self._refresh()
        return self.record is not None

    # ------------------------------------------------------------------------------------------ display

    @staticmethod
    def _clear(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            elif item.layout() is not None:
                ResearchResultsPanel._clear(item.layout())

    def _table(self, layout, key, headers, rows, stretch, text_columns=(), capped=()) -> DiagnosticTable:
        table = DiagnosticTable(headers, rows, stretch, capped, text_columns)
        table.setObjectName(f"research_{key}")
        self.tables[key] = table
        layout.addWidget(table)
        return table

    def _refresh_banner(self) -> None:
        if not self.specimen_combo.count():  # not shown yet: no archived text at start-up
            self.banner.setText("")
            return
        verified, text = rr.workspace_link(self.specimen(), *self.workspace)
        self.banner.setText(text)
        self.banner.setProperty("verified", verified)
        self._refresh_sp10_link()

    def sp10_match(self) -> Optional[sf.WorkspaceMatch]:
        if self.sp10 is None:
            return None
        context = self.context or {}
        return sf.workspace_match(self.sp10, *self.workspace, modal_set=context.get("modal_set"),
                                  fe_modes=context.get("fe_modes"), fe_step=context.get("fe_step"))

    def _refresh_sp10_link(self) -> None:
        match = self.sp10_match()
        self.sp10_link.setText(match.headline if match else "")
        self.sp10_link.setProperty("verified", bool(match and match.matched))
        self.sp10_link_lines.setText("\n".join(match.lines) if match else "")
        self.sp10_package.setText(match.package_line if match else "")
        self.sp10_proximity.setText(sf.PROXIMITY_ONLY if match else "")
        self.sp10_registration.setText(match.registration if match else "")
        for label in (self.sp10_link, self.sp10_registration, self.sp10_link_lines, self.sp10_package,
                      self.sp10_proximity):
            label.setVisible(match is not None)

    def _refresh(self) -> None:
        self._refresh_banner()
        self.error.setText(self.snapshot_error)
        self.error.setVisible(bool(self.snapshot_error))
        self._clear_dynamic()
        if self.snapshot is None:
            self.identity.setText("The archived results are read when this page is first shown." if not
                                  self.snapshot_error else "")
            for card in (self.matching_card, self.sp10_card, self.mac_card, self.sens_card, self.inverse_card):
                card.setVisible(False)
            self.plate_only.setVisible(False)
            return
        key = self.specimen()
        self.identity.setText("\n".join(rm.identity_lines(self.snapshot, key)))
        self.matching_card.setVisible(True)
        if key == "SP-10":  # PRIORITY-7: the historical table is named as such, beside the PRIORITY-6 results
            self.matching_layout.addWidget(_label(rm.SP10_HISTORICAL_HEADING, "sectionTitle"))
        self.matching_layout.addWidget(_label(rm.SPECIMEN_NOTES[key], "warnings"))
        table = self._table(self.matching_layout, "matching", rm.MATCHING_HEADERS, rm.matching_rows(self.snapshot, key),
                            9, text_columns=(2, 3, 6, 7, 8, 9), capped=(2, 6, 7))
        for row in rm.ambiguous_rows(self.snapshot, key):  # close groups and ambiguous assignments
            for column in (7, 8):
                table.item(row, column).setBackground(QBrush(AMBIGUOUS_BRUSH))
                table.item(row, column).setForeground(QBrush(QColor("black")))
        self.matching_layout.addWidget(_label(rm.STATUS_MEANING, "hint"))
        self.mac_card.setVisible(True)
        view = rm.mac_view(self.record, key)
        self.load_button.setVisible(key != "SP-10")
        self.mac_warning.setVisible(view["state"] == "matrix")
        if self.record_error:
            self.mac_body.addWidget(_label(self.record_error, "error"))
        self.mac_body.addWidget(_label(view["text"], "warnings" if view["state"] != "no_record" else "hint"))
        if key == "SP-10":
            self.mac_body.addWidget(_label(rm.SP10_MAC_NOTE, "hint"))
        self._show_sp10(key == "SP-10")
        self.heatmap = None
        if view["state"] == "matrix":
            self.mac_body.addWidget(_label("\n".join(rm.record_lines(self.record)), "hint"))
            scale = _label("MAC scale: 0 (dark) … 1 (yellow)", "hint")
            scale.setStyleSheet("QLabel { color: white; font-weight: bold; padding: 4px; background: "
                                "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #440154, stop:0.5 #21918c, "
                                "stop:1 #fde725); }")
            self.mac_body.addWidget(scale)
            self.heatmap = MacHeatmap(view)
            self.cell = _label("Click a cell to see its value.", "hint")
            self.heatmap.cellClicked.connect(lambda r, c: self.cell.setText(rm.cell_text(self.record, key, r, c)))
            self.mac_body.addWidget(self.heatmap)
            self.mac_body.addWidget(self.cell)
        plate = key == "PLATE"
        self.sens_card.setVisible(plate)
        self.inverse_card.setVisible(plate)
        self.plate_only.setVisible(not plate)
        if plate:
            self.sens_layout.addWidget(_label(rm.SENSITIVITY_NOTE, "hint"))
            sens = self._table(self.sens_layout, "sensitivities", rm.SENSITIVITY_HEADERS,
                               rm.sensitivity_rows(self.snapshot), 6, text_columns=(0, 6), capped=())
            for row, x in enumerate(self.snapshot.sensitivities):
                strong = {"FE7": 4, "FE13": 2, "FE14": 3}.get(x.term)
                if strong is not None:
                    sens.item(row, strong).setBackground(QBrush(QColor(197, 225, 165)))
                    sens.item(row, strong).setForeground(QBrush(QColor("black")))
                if x.term in ("FE8", "FE9", "FE20", "FE15+FE16"):
                    sens.item(row, 6).setBackground(QBrush(AMBIGUOUS_BRUSH))
                    sens.item(row, 6).setForeground(QBrush(QColor("black")))
            self.sens_layout.addWidget(_label("\n".join(f"• {line}" for line in rm.SENSITIVITY_HIGHLIGHTS), "hint"))
            self.sens_layout.addWidget(_label("Sensitivity matrix: " + " · ".join(rm.rank_lines(self.snapshot)),
                                              "warnings"))
            self.inverse_static.addWidget(_label(rm.INVERSE_NOTE, "warnings"))
            self._table(self.inverse_static, "scenarios", rm.SCENARIO_HEADERS, rm.scenario_rows(self.snapshot), 4,
                        text_columns=(0, 4, 5, 6), capped=(5, 6))
            self._refresh_scenario()

    def _show_sp10(self, shown: bool) -> None:
        """PRIORITY-7: B. Updated SP-10 FE Results — PRIORITY-6 (only for SP-10; from the small archived records)."""
        self.sp10_card.setVisible(shown)
        if not shown:
            return
        if self.sp10 is None:
            self.sp10_body.addWidget(_label(self.sp10_error, "error"))
            return
        self.sp10_body.addWidget(_label("\n".join(rm.sp10_identity_lines(self.sp10)), "hint"))
        self.sp10_body.addWidget(_label("FE modes of PRIORITY-6 — FE7–FE25", "sectionTitle"))
        self.sp10_body.addWidget(_label(rm.SP10_RANGE_NOTE, "hint"))
        fe = self._table(self.sp10_body, "sp10_fe", rm.SP10_FE_HEADERS, rm.sp10_fe_rows(self.sp10), 5,
                         text_columns=(0, 2, 3, 4, 5))
        for row in rm.sp10_added_rows(self.sp10):
            fe.item(row, 5).setBackground(QBrush(ADDED_BRUSH))
            fe.item(row, 5).setForeground(QBrush(QColor("black")))
        self.sp10_body.addWidget(_label("Frequency diagnostic — every experimental record (EXP1–EXP12)",
                                        "sectionTitle"))
        self.sp10_body.addWidget(_label(rm.SP10_DIAGNOSTIC_NOTE, "warnings"))
        diagnostic = self._table(self.sp10_body, "sp10_diagnostic", rm.SP10_DIAGNOSTIC_HEADERS,
                                 rm.sp10_diagnostic_rows(self.sp10_rows), 7, text_columns=(0, 2, 5, 7))
        for row in rm.sp10_group_rows(self.sp10_rows):  # close groups: highlighted, never reassigned
            diagnostic.item(row, 7).setBackground(QBrush(AMBIGUOUS_BRUSH))
            diagnostic.item(row, 7).setForeground(QBrush(QColor("black")))
        for row, r in enumerate(self.sp10_rows):
            if r.nearest_in_added_range:
                for column in (2, 3):
                    diagnostic.item(row, column).setBackground(QBrush(ADDED_BRUSH))
                    diagnostic.item(row, column).setForeground(QBrush(QColor("black")))
        focus = _label("\n".join(rm.sp10_focus_lines(self.sp10_rows)), "warnings")
        focus.setObjectName("sp10Focus")
        self.sp10_body.addWidget(focus)
        self.sp10_body.addWidget(_label("\n".join(rm.sp10_group_lines()), "hint"))
        self.sp10_body.addWidget(_label(rm.SP10_LIMITS, "hint"))

    def _clear_dynamic(self) -> None:
        self.tables = {}
        self._clear(self.sp10_body)
        for layout, keep in ((self.matching_layout, 1), (self.sens_layout, 1)):
            while layout.count() > keep:
                item = layout.takeAt(keep)
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)
                    widget.deleteLater()
        for layout in (self.mac_body, self.inverse_static, self.scenario_body):
            self._clear(layout)

    def _refresh_scenario(self) -> None:
        self._clear(self.scenario_body)
        for key in ("branches", "declared", "diagnostic"):
            self.tables.pop(key, None)
        if self.snapshot is None or self.specimen() != "PLATE":
            return
        view = rm.scenario_view(self.snapshot, self.scenario_combo.currentData())
        self.scenario_body.addWidget(_label(view["parameters"], "hint"))
        self.scenario_body.addWidget(_label(view["pairs"], "warnings"))
        self.scenario_body.addWidget(_label("Assumed correspondences: real Abaqus against the experiment",
                                            "sectionTitle"))
        self._table(self.scenario_body, "declared", rm.DECLARED_HEADERS, view["declared"], 0, text_columns=(0,))
        self.scenario_body.addWidget(_label("Every tracked FE branch: baseline, LM prediction and real Abaqus",
                                            "sectionTitle"))
        self._table(self.scenario_body, "branches", rm.BRANCH_HEADERS, view["branches"], 6, text_columns=(0, 5, 6))
        if view["centroid"]:
            self.scenario_body.addWidget(_label(rm.CENTROID_NOTE, "warnings"))
        self.scenario_body.addWidget(_label("Other records against the nearest tracked FE frequency — diagnostic only, "
                                            "never pairs", "sectionTitle"))
        self._table(self.scenario_body, "diagnostic", rm.DIAGNOSTIC_HEADERS, view["diagnostic"], 2,
                    text_columns=(0, 2))
        self.scenario_body.addWidget(_label("Limits: " + view["limits"], "hint"))


__all__ = ["MacHeatmap", "ResearchResultsPanel", "colour"]
