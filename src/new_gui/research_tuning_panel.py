"""REAL-FIT.R1: the Research Tuning page (PySide6). Research-only frequency tuning of the assumed Abaqus CFRP inputs.

Reading and fitting run in one owned worker thread that touches no widget; outcomes return through a queued signal and are
shown only when they belong to the current job. Nothing here starts Abaqus or changes a file it reads.
"""

from __future__ import annotations

import json
from pathlib import Path
import threading
from typing import Callable, Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QProgressBar,
                               QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from new_gui import research_tuning_model as rm
from new_gui.diagnostic_panel import DiagnosticTable
from new_gui.shape_panel import _label
from services import research_frequency_tuning as rft

INTRO = ("Refines the ASSUMED CFRP inputs of an Abaqus plate model against measured PolyMAX frequencies, with a "
         "Kirchhoff-Ritz plate surrogate. Research only: no Abaqus run, no material property, no mode pairs.")
ROLES = (rft.FIT, rft.HOLDOUT, rft.EXCLUDED)


def _card():
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 12, 16, 12)
    layout.setSpacing(8)
    return frame, layout


class _Bridge(QObject):
    done = Signal(int, str, object)
    solved = Signal(int, int)


class ResearchTuningPanel(QWidget):
    """``ask_path(kind, start)`` and ``ask_save(start)`` are replaced in tests."""

    def __init__(self, ask_path: Optional[Callable[[str, str], str]] = None, ask_save: Optional[Callable[[str], str]] = None):
        super().__init__()
        self.setObjectName("researchTuning")
        self._ask_path = ask_path or self._dialog_path
        self._ask_save = ask_save or self._dialog_save
        self.paths = {"inp": "", "unv": ""}
        self.sources: Optional[rm.Sources] = None
        self.result: Optional[rft.TuningResult] = None
        self.request: Optional[rft.TuningRequest] = None
        self.plot_data = b""
        self._token = 0
        self._active: Optional[str] = None
        self._cancel: Optional[threading.Event] = None
        self._thread: Optional[threading.Thread] = None
        self._tables: dict = {}
        self._bridge = _Bridge(self)
        self._bridge.done.connect(self._done)
        self._bridge.solved.connect(self._solved)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.banner = _label(rm.LABEL, "badge")
        self.banner.setProperty("state", "chosen")
        layout.addWidget(self.banner)
        layout.addWidget(_label(INTRO, "hint"))
        layout.addWidget(self._build_files())
        layout.addWidget(self._build_setup())
        layout.addWidget(self._build_results())
        layout.addStretch(1)
        self._refresh()

    # ---------------------------------------------------------------------------------------------- building

    def _build_files(self) -> QFrame:
        card, inner = _card()
        inner.addWidget(_label("1. Model and measurement", "sectionTitle"))
        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        self.fields, self.buttons = {}, {}
        for row, (key, caption) in enumerate((("inp", "Abaqus model input (.inp)"), ("unv", "PolyMAX modal set (.unv / .uff)"))):
            grid.addWidget(_label(caption), 2 * row, 0, 1, 2)
            field = QLineEdit()
            field.setReadOnly(True)
            field.setPlaceholderText("not chosen")
            field.setMinimumWidth(80)
            grid.addWidget(field, 2 * row + 1, 0, 1, 2)
            button = QPushButton("Choose file...")
            button.setObjectName(f"tuningChoose_{key}")
            button.clicked.connect(lambda _c=False, k=key: self.choose_file(k))
            grid.addWidget(button, 2 * row + 1, 2)
            self.fields[key], self.buttons[key] = field, button
        inner.addLayout(grid)
        self.read_note = _label("The .dat beside the INP is read too, for the Abaqus frequencies at the INP values.", "hint")
        inner.addWidget(self.read_note)
        self.inputs_box = QVBoxLayout()
        inner.addLayout(self.inputs_box)
        return card

    def _build_setup(self) -> QFrame:
        card, inner = _card()
        inner.addWidget(_label("2. Frequencies and settings", "sectionTitle"))
        inner.addWidget(_label("Roles: FIT frequencies are fitted; HOLDOUT ones are predicted only; EXCLUDED ones are not used. "
                               "Frequencies are compared with the surrogate by rank (a frequency hypothesis, not mode identity).",
                               "hint"))
        self.records_box = QVBoxLayout()
        inner.addLayout(self.records_box)
        grid = QGridLayout()
        for column, share in enumerate((1, 2, 1, 2)):
            grid.setColumnStretch(column, share)
        self.parameterization = QComboBox()
        self.parameterization.setObjectName("tuningParameterization")
        for text in (rft.TIED, rft.FREE):
            self.parameterization.addItem(text, text)
        self.declared = QLineEdit()
        self.declared.setObjectName("tuningDeclared")
        self.declared.setPlaceholderText("optional, e.g. 3:4, 4:3 (record:rank)")
        self.lower = QLineEdit("0.2")
        self.upper = QLineEdit("5")
        self.degree = QLineEdit("14")
        for row, (caption, widget) in enumerate((("Fitted inputs", self.parameterization), ("Declared ranks", self.declared),
                                                 ("Lower bound (× INP)", self.lower), ("Upper bound (× INP)", self.upper),
                                                 ("Ritz basis degree", self.degree))):
            grid.addWidget(_label(caption), row // 2, 2 * (row % 2))
            grid.addWidget(widget, row // 2, 2 * (row % 2) + 1)
        inner.addLayout(grid)
        inner.addWidget(_label("Held fixed at the INP values: thickness, density, nu12, E3, nu13, nu23, G13, G23.", "hint"))
        row = QHBoxLayout()
        self.run_button = QPushButton("Run tuning")
        self.run_button.setObjectName("primary")
        self.run_button.setMinimumHeight(36)
        self.run_button.clicked.connect(lambda: self.run())
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setMinimumHeight(36)
        self.cancel_button.clicked.connect(lambda: self.cancel())
        row.addWidget(self.run_button)
        row.addWidget(self.cancel_button)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(10)
        self.progress.setVisible(False)
        row.addWidget(self.progress, 1)
        inner.addLayout(row)
        self.state = _label("Choose the two files.")
        inner.addWidget(self.state)
        self.message = _label("", "error")
        self.message.setVisible(False)
        inner.addWidget(self.message)
        return card

    def _build_results(self) -> QFrame:
        self.results_card, inner = _card()
        inner.addWidget(_label("3. Result", "sectionTitle"))
        self.status = _label("", "badge")
        inner.addWidget(self.status)
        self.reasons = _label("", "warnings")
        inner.addWidget(self.reasons)
        inner.addWidget(_label(rm.SURROGATE_NOTE, "hint"))
        self.candidate_box = QVBoxLayout()
        inner.addLayout(self.candidate_box)
        self.plot = QLabel()
        self.plot.setObjectName("tuningPlot")
        self.plot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plot.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.plot.setMinimumSize(1, 1)
        inner.addWidget(self.plot)
        self.result_boxes = {}
        for key, title in (("frequencies", "Frequencies: FIT and HOLDOUT"), ("minima", "Minima reached from the starts"),
                           ("diagnostics", "Convergence, rank and coupling"),
                           ("sensitivity", "Sensitivity d ln f / d ln p (FIT rows, at the fitted point)"),
                           ("surrogate", "Surrogate check: Ritz against the stored Abaqus frequencies at the INP values")):
            inner.addWidget(_label(title, "sectionTitle"))
            box = QVBoxLayout()
            inner.addLayout(box)
            self.result_boxes[key] = box
        row = QHBoxLayout()
        self.export_button = QPushButton("Export proposal (JSON)...")
        self.export_button.setObjectName("tuningExport")
        self.export_button.clicked.connect(lambda: self.export())
        row.addWidget(self.export_button)
        row.addStretch(1)
        inner.addLayout(row)
        self.export_note = _label("", "hint")
        inner.addWidget(self.export_note)
        self.results_card.setVisible(False)
        return self.results_card

    # ---------------------------------------------------------------------------------------------- tables

    def _table(self, key: str, box, headers, rows, stretch: int) -> DiagnosticTable:
        old = self._tables.pop(key, None)
        if old is not None:
            old.setParent(None)
            old.deleteLater()
        if not rows:
            return None
        table = DiagnosticTable(headers, rows, stretch, text_columns=tuple(range(len(headers))))
        table.setObjectName(f"tuning_{key}")
        self._tables[key] = table
        box.addWidget(table)
        return table

    def table_cells(self, key: str) -> list:
        table = self._tables[key]
        return [[table.item(r, c).text() for c in range(table.columnCount())] for r in range(table.rowCount())]

    def _show_records(self) -> None:
        records = self.sources.records
        holdout = set(rm.default_holdout(records))
        table = QTableWidget(len(records), 3)
        table.setObjectName("tuning_records")
        table.setHorizontalHeaderLabels(["EXP record", "Frequency (Hz)", "Role"])
        table.verticalHeader().setVisible(False)
        self.role_combos = {}
        for row, (record, hz) in enumerate(records):
            for column, text in enumerate((str(record), f"{hz:.4f}")):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row, column, item)
            combo = QComboBox()
            for role in ROLES:
                combo.addItem(role, role)
            combo.setCurrentIndex(ROLES.index(rft.HOLDOUT if record in holdout else rft.FIT))
            table.setCellWidget(row, 2, combo)
            self.role_combos[record] = combo
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        table.setFixedHeight(min(40 + 30 * len(records), 380))
        old = self._tables.pop("records", None)
        if old is not None:
            old.setParent(None)
            old.deleteLater()
        self._tables["records"] = table
        self.records_box.addWidget(table)

    def roles(self) -> dict:
        return {record: combo.currentData() for record, combo in getattr(self, "role_combos", {}).items()}

    def set_role(self, record: int, role: str) -> None:
        self.role_combos[record].setCurrentIndex(ROLES.index(role))

    # ---------------------------------------------------------------------------------------------- files

    def _dialog_path(self, kind: str, start: str) -> str:
        pattern = "Abaqus input (*.inp)" if kind == "inp" else "Experimental modal data (*.unv *.uff)"
        path, _f = QFileDialog.getOpenFileName(self, "Choose file", start, pattern)
        return path

    def _dialog_save(self, start: str) -> str:
        path, _f = QFileDialog.getSaveFileName(self, "Export proposal", start, rm.EXPORT_FILTER)
        return path

    def choose_file(self, kind: str, path: Optional[str] = None) -> bool:
        if self._active is not None:
            return False
        path = path if path is not None else self._ask_path(kind, str(Path(self.paths[kind]).parent) if self.paths[kind] else "")
        if not path:
            return False
        self.paths[kind] = str(path)
        self.fields[kind].setText(str(path))
        self.fields[kind].setToolTip(str(path))
        self.sources = None
        self._clear_result()
        if all(self.paths.values()):
            inp, unv = self.paths["inp"], self.paths["unv"]
            self.state.setText("Reading the files...")
            self._start("read", lambda cancel, _s: rm.read_sources(inp, unv, cancel))
        self._refresh()
        return True

    # ---------------------------------------------------------------------------------------------- jobs

    def _start(self, kind: str, work: Callable) -> bool:
        if self._active is not None:
            return False
        self._token += 1
        token, bridge = self._token, self._bridge
        cancel = threading.Event()
        self._active, self._cancel = kind, cancel

        def solved(count: int) -> None:
            try:
                bridge.solved.emit(token, count)
            except RuntimeError:
                pass

        def target() -> None:
            try:
                value = work(cancel, solved)
            except (rm.ReadFailed, rft.TuningRefused, ValueError) as error:
                value = error
            except Exception as error:  # noqa: BLE001  (a message, never a crash of the window)
                value = RuntimeError(f"{type(error).__name__}: {error}")
            try:
                bridge.done.emit(token, kind, value)
            except RuntimeError:
                pass

        self._thread = threading.Thread(target=target, name=f"new-gui-research-tuning-{kind}", daemon=True)
        self._thread.start()
        self._refresh()
        return True

    def _solved(self, token: int, count: int) -> None:
        if token == self._token and self._active == "fit":
            self.state.setText(f"Fitting: {count} surrogate solves...")

    def _done(self, token: int, kind: str, value) -> None:
        if token != self._token:
            return
        self._active, self._cancel = None, None
        if isinstance(value, Exception):
            self._say(str(value))
            self.state.setText("Not completed.")
        elif kind == "read":
            self.sources = value
            self._say("")
            self._table("inputs", self.inputs_box, ("Initial assumed Abaqus value", "Value"), rm.input_rows(value), 1)
            self._show_records()
            self.state.setText(f"Read: {len(value.records)} curve-fitted records of {value.set_title}.")
        elif kind == "fit":
            self._show_result(value)
        self._refresh()

    def busy(self) -> bool:
        return self._active is not None or (self._thread is not None and self._thread.is_alive())

    def shutdown(self, timeout: float = 5.0) -> None:
        if self._cancel is not None:
            self._cancel.set()
        self._token += 1
        self._active = None
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout)

    def cancel(self) -> bool:
        if self._active != "fit" or self._cancel is None:
            return False
        self._cancel.set()
        self.state.setText("Cancelling after the current surrogate solve...")
        return True

    # ---------------------------------------------------------------------------------------------- run

    def build_request(self) -> rft.TuningRequest:
        roles = self.roles()
        declared = rm.parse_declared(self.declared.text())
        observations = rft.observations_by_rank(
            self.sources.records, holdout=[r for r, role in roles.items() if role == rft.HOLDOUT],
            excluded=[r for r, role in roles.items() if role == rft.EXCLUDED], declared=declared)
        return rft.TuningRequest(observations, self.parameterization.currentData(),
                                 rft.DECLARED if declared else rft.RANK_ORDER, float(self.lower.text()), float(self.upper.text()),
                                 degree=int(self.degree.text()))

    def run(self) -> bool:
        if self.sources is None or self._active is not None:
            return False
        try:
            request = self.build_request()
            if not 0 < request.lower_factor < 1 < request.upper_factor:
                raise ValueError("The bounds must satisfy 0 < lower < 1 < upper (factors of the INP values).")
            if not 4 <= request.degree <= 24:
                raise ValueError("The Ritz basis degree must be between 4 and 24.")
        except (ValueError, KeyError) as error:
            self._say(f"Not started: {error}")
            return False
        self._say("")
        self._clear_result()
        self.request = request
        sources = self.sources
        self.state.setText("Fitting...")
        return self._start("fit", lambda cancel, solved: rft.run_tuning(sources.inputs, request, sources.fe_elastic, cancel, solved))

    def _say(self, text: str) -> None:
        self.message.setText(text)
        self.message.setVisible(bool(text))

    def _clear_result(self) -> None:
        self.result = None
        self.plot_data = b""
        self.plot.clear()
        for key in ("candidate", "frequencies", "minima", "diagnostics", "sensitivity", "surrogate"):
            self._table(key, None, (), (), 0)
        self.results_card.setVisible(False)
        self.export_note.setText("")

    def _show_result(self, result: rft.TuningResult) -> None:
        self.result = result
        self.results_card.setVisible(True)
        self.status.setText(f"{result.status} | {rft.RESULT_LABEL}")
        self.status.setProperty("state", "chosen" if result.candidate else "blocked")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.reasons.setText("\n".join([rm.STATUS_TEXT.get(result.status, result.status)] + list(result.reasons) + list(result.warnings)))
        self._table("candidate", self.candidate_box, rm.CANDIDATE_HEADERS, rm.candidate_rows(result), 0)
        self._table("frequencies", self.result_boxes["frequencies"], rm.FREQUENCY_HEADERS, rm.frequency_rows(result), 1)
        self._table("minima", self.result_boxes["minima"], ("Minimum", "Fitted values (MPa)", "Cost"), rm.minima_rows(result), 1)
        self._table("diagnostics", self.result_boxes["diagnostics"], ("Item", "Value"), rm.diagnostic_rows(result), 1)
        self._table("sensitivity", self.result_boxes["sensitivity"], ("EXP record",) + tuple(result.parameter_names),
                    rm.sensitivity_rows(result), 0)
        self._table("surrogate", self.result_boxes["surrogate"], rm.SURROGATE_HEADERS, rm.surrogate_rows(result), 0)
        self.state.setText(f"{result.status}: {result.evaluations} surrogate solves.")
        width = max(400, self.plot.width() or 900)
        ratio = self.devicePixelRatioF()
        self.plot_data = rm.error_plot(result, width, 380, ratio) or b""
        pixmap = QPixmap()
        if self.plot_data and pixmap.loadFromData(self.plot_data, "PNG"):
            pixmap.setDevicePixelRatio(ratio)
            self.plot.setPixmap(pixmap)
            self.plot.setFixedHeight(380)

    def export(self, path: Optional[str] = None) -> bool:
        if self.result is None or self.sources is None or self.result.status == rft.CANCELLED:
            return False
        path = path if path is not None else self._ask_save("research_tuning_proposal.json")
        if not path:
            return False
        sources = {"inp": self.sources.inputs.inp_path, "inp_sha256": self.sources.inputs.inp_sha256,
                   "dat": self.sources.dat_path or "", "unv": self.sources.unv_path, "unv_sha256": self.sources.unv_sha256,
                   "modal_set": self.sources.set_title}
        try:
            rft.write_export(rft.export_document(self.result, self.sources.inputs, sources), path)
        except OSError as error:
            self._say(f"Not exported: {error}")
            return False
        self.export_note.setText(f"Exported: {path}")
        return True

    def _refresh(self) -> None:
        running = self._active is not None
        for button in self.buttons.values():
            button.setEnabled(not running)
        for widget in (self.parameterization, self.declared, self.lower, self.upper, self.degree):
            widget.setEnabled(not running)
        self.run_button.setEnabled(not running and self.sources is not None)
        self.cancel_button.setEnabled(self._active == "fit")
        self.progress.setVisible(running)
        self.export_button.setEnabled(not running and self.result is not None and self.result.status != rft.CANCELLED)


__all__ = ["ResearchTuningPanel"]
