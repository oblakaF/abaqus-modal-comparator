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
from services import research_frequency_stability as rfs
from services import research_frequency_tuning as rft

INTRO = ("The current exploratory workflow for real data: it refines the ASSUMED CFRP inputs (E1, E2, G12) of a supported "
         "shell FE model so that its Kirchhoff-Ritz plate surrogate matches fitted PolyMAX frequencies. Research only: no "
         "Abaqus run, no material property, no mode pairs.")
FILE_ROLES = ("INP: the FE model; its material, density, shell thickness and size are read, and the model check says why "
              "another kind of model cannot be used. UNV / UFF: the measured, curve-fitted PolyMAX frequencies (FRF peak "
              "records are never used). ODB, optional: its already extracted mode shapes tell rigid-body from elastic FE "
              "modes. The Kirchhoff-Ritz surrogate is a thin homogeneous plate: it does not automatically apply to a solid "
              "or sandwich FE model.")
FORMS_TEXT = ("E1=E2, G12: one in-plane modulus for both directions and the shear modulus (two unknowns). E1, E2, G12: "
              "separate moduli (three unknowns); then E1 and E2 exchanged may fit the frequencies equally well.")
KINDS_TEXT = ("Measured: the PolyMAX frequencies. Fixed: the INP's thickness, density, nu12 and other constants, assumed "
              "as written. Fitted: the exploratory E and G values, research estimates only.")
MIRROR_TEXT = ("Why two alternatives: exchanging E1 and E2 gives the same frequencies here, so frequency agreement alone "
               "cannot tell which plate axis is stiff. Neither is chosen; deciding needs independent evidence of the fibre "
               "axes, such as a registered shape comparison or the layup record.")
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
        self.paths = {"inp": "", "unv": "", "odb": ""}
        self.sources: Optional[rm.Sources] = None
        self.result: Optional[rft.TuningResult] = None
        self.request: Optional[rft.TuningRequest] = None
        self.stability: Optional[dict] = None  # REAL-FIT.R2: the stability check of the shown result, when it was run
        self.plot_data = b""
        self.saved_path: Optional[str] = None  # set while a saved (exported) result is shown
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
        for row, (key, caption) in enumerate((("inp", "Abaqus model input (.inp)"), ("unv", "PolyMAX modal set (.unv / .uff)"),
                                              ("odb", "Abaqus results (.odb), optional: shape-based FE classification"))):
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
        self.roles_note = _label(FILE_ROLES, "hint")
        inner.addWidget(self.roles_note)
        self.read_note = _label("The .dat beside the INP is listed unclassified. Rigid-body and elastic FE modes are told apart "
                                "only by shape, from modes already extracted from the chosen ODB; Abaqus is never started.",
                                "hint")
        inner.addWidget(self.read_note)
        self.compat_title = _label("Model check", "sectionTitle")
        self.compat_verdict = _label("", "hint")
        self.compat_box = QVBoxLayout()
        self.compat_notes = _label("", "hint")
        inner.addWidget(self.compat_title)
        inner.addWidget(self.compat_verdict)
        inner.addLayout(self.compat_box)
        inner.addWidget(self.compat_notes)
        self._clear_compatibility()
        self.inputs_box = QVBoxLayout()
        inner.addLayout(self.inputs_box)
        row = QHBoxLayout()
        self.open_button = QPushButton("Open result...")
        self.open_button.setObjectName("tuningOpenResult")
        self.open_button.clicked.connect(lambda: self.open_result())
        row.addWidget(self.open_button)
        row.addStretch(1)
        inner.addLayout(row)
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
        self.parameterization.setToolTip(FORMS_TEXT)
        self.declared = QLineEdit()
        self.declared.setObjectName("tuningDeclared")
        self.declared.setPlaceholderText("optional, e.g. 3:4, 4:3 (record:rank)")
        self.search = QLineEdit("10")
        self.search.setObjectName("tuningSearch")
        self.search.setToolTip("Bounds: the data-scaled start divided and multiplied by this factor. The INP values do not "
                               "set the start or the bounds.")
        self.degree = QLineEdit("14")
        for row, (caption, widget) in enumerate((("Fitted inputs", self.parameterization), ("Declared ranks", self.declared),
                                                 ("Search range (× data-scaled start)", self.search),
                                                 ("Ritz basis degree", self.degree))):
            grid.addWidget(_label(caption), row // 2, 2 * (row % 2))
            grid.addWidget(widget, row // 2, 2 * (row % 2) + 1)
        inner.addLayout(grid)
        inner.addWidget(_label(FORMS_TEXT, "hint"))
        inner.addWidget(_label("Held fixed at the INP values (assumed, not identified): thickness, density, nu12, E3, nu13, "
                               "nu23, G13, G23. The start comes from the measured frequencies alone.", "hint"))
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
        self.saved_note = _label("", "warnings")
        self.saved_note.setVisible(False)
        inner.addWidget(self.saved_note)
        self.reasons = _label("", "warnings")
        inner.addWidget(self.reasons)
        self.mirror_note = _label(MIRROR_TEXT, "hint")
        self.mirror_note.setVisible(False)
        inner.addWidget(self.mirror_note)
        inner.addWidget(_label(rm.SURROGATE_NOTE, "hint"))
        inner.addWidget(_label(KINDS_TEXT, "hint"))
        self.accuracy = _label("", "warnings")
        inner.addWidget(self.accuracy)
        self.estimate_box, self.axis_box = QVBoxLayout(), QVBoxLayout()
        inner.addWidget(_label("Numerical research estimates", "sectionTitle"))
        inner.addLayout(self.estimate_box)
        inner.addLayout(self.axis_box)
        inner.addWidget(_label("Oriented Abaqus input candidate (only when the axes are resolved)", "sectionTitle"))
        self.candidate_none = _label("", "hint")
        inner.addWidget(self.candidate_none)
        self.candidate_box = QVBoxLayout()
        inner.addLayout(self.candidate_box)
        self.plot = QLabel()
        self.plot.setObjectName("tuningPlot")
        self.plot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plot.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.plot.setMinimumSize(1, 1)
        inner.addWidget(self.plot)
        self.result_boxes = {}
        for key, title in (("quantities", "What is measured, assumed, fitted and fixed"),
                           ("frequencies", "Frequencies: FIT and HOLDOUT"),
                           ("first_mode", "Dependence on the lowest experimental record (it stays in the fit)"),
                           ("assumptions", "What the fixed inputs carry: factor on the estimated moduli"),
                           ("minima", "Minima reached from the starts"),
                           ("diagnostics", "Convergence, rank and coupling"),
                           ("sensitivity", "Sensitivity d ln f / d ln p (FIT rows, at the fitted point)"),
                           ("surrogate", "Surrogate check: Ritz against the stored Abaqus frequencies at the INP values")):
            inner.addWidget(_label(title, "sectionTitle"))
            box = QVBoxLayout()
            inner.addLayout(box)
            self.result_boxes[key] = box
        inner.addWidget(_label("4. Stability: leave one FIT record out", "sectionTitle"))
        inner.addWidget(_label(rm.STABILITY_NOTE, "hint"))
        row = QHBoxLayout()
        self.stability_button = QPushButton("Check stability")
        self.stability_button.setObjectName("tuningStability")
        self.stability_button.setMinimumHeight(32)
        self.stability_button.clicked.connect(lambda: self.run_stability())
        row.addWidget(self.stability_button)
        row.addStretch(1)
        inner.addLayout(row)
        self.stability_statement = _label("", "warnings")
        self.stability_statement.setVisible(False)
        inner.addWidget(self.stability_statement)
        self.stability_boxes = {}
        for key, title in (("stability_assessment", "The 10 % objective: three separate questions"),
                           ("stability_loo", "Refits without one FIT record (changes against the full-data estimates)"),
                           ("stability_control", "Which records control each estimate"),
                           ("stability_influence", "Local influence d ln p / d ln f_exp (from the full fit's sensitivity matrix)"),
                           ("stability_fixed", "Exact dependence on the assumed thickness and density")):
            caption = _label(title, "sectionTitle")
            caption.setVisible(False)
            inner.addWidget(caption)
            box = QVBoxLayout()
            inner.addLayout(box)
            self.stability_boxes[key] = (caption, box)
        self.influence_note = _label("", "hint")
        self.influence_note.setVisible(False)
        self.stability_boxes["stability_influence"][1].addWidget(self.influence_note)
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
        pattern = {"inp": "Abaqus input (*.inp)", "odb": "Abaqus ODB (*.odb)", "result": rm.EXPORT_FILTER}.get(
            kind, "Experimental modal data (*.unv *.uff)")
        path, _f = QFileDialog.getOpenFileName(self, "Choose file", start, pattern)
        return path

    def _dialog_save(self, start: str) -> str:
        path, _f = QFileDialog.getSaveFileName(self, "Export proposal", start, rm.EXPORT_FILTER)
        return path

    def choose_file(self, kind: str, path: Optional[str] = None) -> bool:
        if self._active not in (None, "check"):
            return False
        path = path if path is not None else self._ask_path(kind, str(Path(self.paths[kind]).parent) if self.paths[kind] else "")
        if not path:
            return False
        self.paths[kind] = str(path)
        self.fields[kind].setText(str(path))
        self.fields[kind].setToolTip(str(path))
        self.sources = None
        self._clear_result()
        inp, unv, odb = self.paths["inp"], self.paths["unv"], self.paths["odb"] or None
        if kind == "inp":
            self._clear_compatibility()
            self._say("")
        if self._active == "check" and (kind == "inp" or unv):  # the new job checks the model again
            self._token += 1
            self._active, self._cancel = None, None
        if inp and unv:
            self.state.setText("Reading the files...")
            self._start("read", lambda cancel, _s: rm.read_sources(inp, unv, cancel, odb))
        elif kind == "inp":
            self.state.setText("Checking the model...")
            self._start("check", lambda _cancel, _s: rm.check_model(inp))
        self._refresh()
        return True

    def open_result(self, path: Optional[str] = None) -> bool:
        """Show an exported result as it was saved. Only that file is read; nothing named in it is opened and nothing is
        recalculated. An invalid file is said and the page keeps what it showed."""
        if self._active not in (None, "check"):
            return False
        path = path if path is not None else self._ask_path("result", str(Path(self.saved_path).parent) if self.saved_path else "")
        if not path:
            return False
        try:
            result, stability = rm.open_saved(path)
        except rft.TuningRefused as error:
            self._say(f"Not opened: {error}")
            return False
        self._say("")
        if self._active == "check":  # a saved result replaces the pending model check
            self._token += 1
            self._active, self._cancel = None, None
        self._clear_result()
        self.request = None  # the saved run's request is not live: the stability check stays off
        index = self.parameterization.findData(result.request.get("parameterization"))
        if index >= 0:  # the setting shown matches the saved result
            self.parameterization.setCurrentIndex(index)
        self._show_result(result)
        if stability:
            self._show_stability(stability)
        self.saved_path = str(path)
        self.saved_note.setText(rm.SAVED_NOTE.format(name=Path(path).name))
        self.saved_note.setVisible(True)
        self.state.setText(f"Saved result opened: {Path(path).name}. No calculation was run.")
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
        elif token == self._token and self._active == "stability":
            self.state.setText(f"Stability check: {count} surrogate solves...")

    def _done(self, token: int, kind: str, value) -> None:
        if token != self._token:
            return
        self._active, self._cancel = None, None
        if isinstance(value, Exception):
            report = getattr(value, "compatibility", None)
            if report is not None:
                self._show_compatibility(report)
                self._say("Research Tuning cannot use this INP; the model check above says why.")
            else:
                self._say(str(value))
            self.state.setText("Not completed.")
        elif kind == "check":
            self._show_compatibility(value)
            self.state.setText("Model checked. Choose the PolyMAX modal set.")
        elif kind == "read":
            self.sources = value
            self._say("")
            if value.compatibility is not None:
                self._show_compatibility(value.compatibility)
            self._table("inputs", self.inputs_box, ("Initial assumed Abaqus value", "Value"), rm.input_rows(value), 1)
            self._show_records()
            self.state.setText(f"Read: {len(value.records)} curve-fitted records of {value.set_title}.")
        elif kind == "fit":
            self._show_result(value)
        elif kind == "stability":
            if value.get("status") == rft.CANCELLED:
                self.state.setText("Stability check cancelled. No stability result.")
            else:
                self._show_stability(value)
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
        if self._active not in ("fit", "stability") or self._cancel is None:
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
                                 rft.DECLARED if declared else rft.RANK_ORDER, float(self.search.text()),
                                 degree=int(self.degree.text()))

    def run(self) -> bool:
        if self.sources is None or self._active is not None:
            return False
        try:
            request = self.build_request()
            if not request.search_factor > 1.0:
                raise ValueError("The search range factor must exceed 1.")
            if not 4 <= request.degree <= 24:
                raise ValueError("The Ritz basis degree must be between 4 and 24.")
            rft.validate_correspondence(request.observations)  # R1.F2: before anything starts or is cleared
        except (ValueError, KeyError) as error:
            self._say(f"Not started: {error}")
            return False
        self._say("")
        self._clear_result()
        self.request = request
        sources = self.sources
        self.state.setText("Fitting...")
        return self._start("fit", lambda cancel, solved: rft.run_tuning(sources.inputs, request, sources.fe_elastic, cancel,
                                                                         solved, sources.fe_classification))

    def run_stability(self) -> bool:
        """REAL-FIT.R2: leave each FIT record out of the shown result's own request, in the background."""
        result, request, sources = self.result, self.request, self.sources
        if self._active is not None or self.saved_path is not None or result is None or request is None or sources is None or result.status == rft.CANCELLED:
            return False
        self._say("")
        self._clear_stability()
        self.state.setText("Stability check...")
        return self._start("stability", lambda cancel, solved: rfs.run_stability(sources.inputs, request, result, cancel,
                                                                                 solved))

    def _clear_stability(self) -> None:
        self.stability = None
        self.stability_statement.setText("")
        self.stability_statement.setVisible(False)
        self.influence_note.setVisible(False)
        for key, (caption, _box) in self.stability_boxes.items():
            self._table(key, None, (), (), 0)
            caption.setVisible(False)

    def _show_stability(self, stability: dict) -> None:
        self.stability = stability
        self.stability_statement.setText(stability["assessment"]["statement"] + " " + rft.RESULT_LABEL)
        self.stability_statement.setVisible(True)
        tables = {"stability_assessment": (("Question", "Verdict", "Basis"), rm.assessment_rows(stability), 2),
                  "stability_loo": (rm.stability_headers(stability), rm.stability_rows(stability), 0),
                  "stability_control": (rm.CONTROL_HEADERS, rm.control_rows(stability), 6),
                  "stability_influence": (rm.influence_headers(stability), rm.influence_rows(stability), 0),
                  "stability_fixed": (("Item", "Value"), rm.fixed_input_rows(stability), 1)}
        for key, (headers, rows, stretch) in tables.items():
            caption, box = self.stability_boxes[key]
            caption.setVisible(True)
            self._table(key, box, headers, rows, stretch)
        influence = stability["influence"]
        self.influence_note.setText(f"{influence['rank_note']}. {influence['share_note']}.")
        self.influence_note.setVisible(True)
        self.state.setText(f"Stability check done: {stability['solves']} surrogate solves.")

    def _clear_compatibility(self) -> None:
        self.compat_verdict.setText("")
        self.compat_notes.setText("")
        for widget in (self.compat_title, self.compat_verdict, self.compat_notes):
            widget.setVisible(False)
        self._table("compatibility", None, (), (), 0)

    def _show_compatibility(self, report) -> None:
        """ABM-REAL-INPUT-1: what the INP is; for a model this page does not read, what was read and what stays available."""
        self.compat_title.setVisible(True)
        self.compat_verdict.setText(report.reason)
        self.compat_verdict.setObjectName("hint" if report.supported else "warnings")
        self.compat_verdict.style().unpolish(self.compat_verdict)
        self.compat_verdict.style().polish(self.compat_verdict)
        self.compat_verdict.setVisible(True)
        self._table("compatibility", self.compat_box, ("Read from the INP", "Value"),
                    () if report.supported else rm.compatibility_rows(report), 1)
        notes = rm.compatibility_notes(report)
        self.compat_notes.setText(notes)
        self.compat_notes.setVisible(bool(notes))

    def _say(self, text: str) -> None:
        self.message.setText(text)
        self.message.setVisible(bool(text))

    def _clear_result(self) -> None:
        self.result = None
        self.plot_data = b""
        self.plot.clear()
        for key in ("estimates", "axes", "candidate", "quantities", "frequencies", "first_mode", "assumptions", "minima",
                    "diagnostics", "sensitivity", "surrogate"):
            self._table(key, None, (), (), 0)
        self._clear_stability()
        self.results_card.setVisible(False)
        self.export_note.setText("")
        self.saved_path = None
        self.saved_note.setText("")
        self.saved_note.setVisible(False)

    def _show_result(self, result: rft.TuningResult) -> None:
        self.result = result
        self.results_card.setVisible(True)
        self.status.setText(f"{result.status} | {rft.RESULT_LABEL}")
        self.status.setProperty("state", "chosen" if result.candidate else "blocked")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.reasons.setText("\n".join([rm.STATUS_TEXT.get(result.status, result.status)] + list(result.reasons) + list(result.warnings)))
        self.accuracy.setText(result.accuracy_statement)
        self.mirror_note.setVisible(result.status == rft.MIRROR)
        self._table("estimates", self.estimate_box, rm.ESTIMATE_HEADERS, rm.estimate_rows(result), 0)
        self._table("axes", self.axis_box, rm.AXIS_HEADERS, rm.axis_rows(result), 0)
        self._table("candidate", self.candidate_box, rm.CANDIDATE_HEADERS, rm.candidate_rows(result), 0)
        self.candidate_none.setText("" if result.candidate else "None: " + ("the E1 / E2 axis assignment is unresolved, so no "
                                    "oriented *Elastic block is given." if result.status == rft.MIRROR else
                                    "the fit is not numerically supported."))
        self.candidate_none.setVisible(not result.candidate)
        self._table("quantities", self.result_boxes["quantities"], rm.QUANTITY_HEADERS, rm.quantity_rows(result), 2)
        self._table("first_mode", self.result_boxes["first_mode"], ("Check", "Value"), rm.first_mode_rows(result), 1)
        self._table("assumptions", self.result_boxes["assumptions"], ("Fixed input changed", "Moduli factor"),
                    rm.assumption_rows(result), 0)
        self._table("frequencies", self.result_boxes["frequencies"], rm.FREQUENCY_HEADERS, rm.frequency_rows(result), 1)
        self._table("minima", self.result_boxes["minima"], ("Minimum", "Fitted values (MPa)", "Cost"), rm.minima_rows(result), 1)
        self._table("diagnostics", self.result_boxes["diagnostics"], ("Item", "Value"), rm.diagnostic_rows(result), 1)
        self._table("sensitivity", self.result_boxes["sensitivity"], ("EXP record",) + tuple(result.parameter_names),
                    rm.sensitivity_rows(result), 0)
        if result.surrogate:
            self._table("surrogate", self.result_boxes["surrogate"], rm.SURROGATE_HEADERS, rm.surrogate_rows(result), 0)
        else:
            self._table("surrogate", self.result_boxes["surrogate"], ("Surrogate check",), (("Not made: FE classification "
                        "unavailable. Choose an ODB whose modes are already extracted.",),), 0)
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
        if self.result is None or self.sources is None or self.saved_path is not None or self.result.status == rft.CANCELLED:
            return False
        path = path if path is not None else self._ask_save("research_tuning_proposal.json")
        if not path:
            return False
        sources = {"inp": self.sources.inputs.inp_path, "inp_sha256": self.sources.inputs.inp_sha256,
                   "dat": self.sources.dat_path or "", "unv": self.sources.unv_path, "unv_sha256": self.sources.unv_sha256,
                   "modal_set": self.sources.set_title}
        try:
            rft.write_export(rft.export_document(self.result, self.sources.inputs, sources, self.stability), path)
        except OSError as error:
            self._say(f"Not exported: {error}")
            return False
        self.export_note.setText(f"Exported: {path}")
        return True

    def _refresh(self) -> None:
        running = self._active not in (None, "check")  # a model check never holds the file choice
        for button in self.buttons.values():
            button.setEnabled(not running)
        for widget in (self.parameterization, self.declared, self.search, self.degree):
            widget.setEnabled(not running)
        self.run_button.setEnabled(not running and self.sources is not None)
        self.cancel_button.setEnabled(self._active in ("fit", "stability"))
        live = self.result is not None and self.result.status != rft.CANCELLED and self.saved_path is None
        self.stability_button.setEnabled(not running and live)
        self.progress.setVisible(running)
        self.export_button.setEnabled(not running and live)
        self.open_button.setEnabled(not running)


__all__ = ["ResearchTuningPanel"]
