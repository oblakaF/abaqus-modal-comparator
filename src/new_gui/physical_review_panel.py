"""PRIORITY-9: C. Physical Readiness Review of the Plate Study page (PySide6; RESEARCH_ONLY).

The dossier of ``services.plate_physical_review`` for one single plate, built only on an explicit command:

- **from the Workspace**: PLATE-300x300x1mm 261027 with the M11 FE package (both recognised by SHA-256; any other file
  is refused as SOURCE_NOT_VERIFIED);
- **from study B**: any other single plate, from its Single-Plate Workbench study (no M11 identifier enters).

Seven sections: the source audit, the evidence chains A / B, the owner's question package, the modal evidence, the
observability (FE-only rank apart from the experimental readiness), the FE applicability plan and the report /
export. Nothing here creates a registration, a mode pair, a MAC, a FIT / HOLDOUT set or a fit, and nothing starts
Abaqus, a solver, an LM or Auto-ID. A review built for other inputs is STALE: its tables are not shown as current and
it is not exported (the RC3-F2 rule). A reopened review is CURRENT only when its sources verify on disk again.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QFileDialog, QFrame, QGridLayout, QLabel, QPushButton,
                               QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)

from new_gui.diagnostic_panel import DiagnosticTable
from services import generic_plate_workbench as wb
from services import plate_physical_review as pr

TITLE = "C. Physical Readiness Review"
INTRO = ("A reproducible dossier of what is established, what is only supposed and what blocks a physical "
         "identification of one single plate: sources by SHA-256, the evidence chains scanner → plate → FE, the owner's "
         "questions, the modal evidence, the observability and the FE applicability plan. It creates no registration, "
         "pair, MAC, fit or material value, and starts no Abaqus, solver, LM or Auto-ID.")
STEPS = ("1. Sources", "2. Evidence A / B", "3. Owner questions", "4. Modal evidence", "5. Observability",
         "6. FE applicability", "7. Report & export")
STATE_NAMES = (("sources", "Sources"), ("registration", "Registration"), ("mode_pairs", "Mode pairs"),
               ("identification", "Identification"), ("review_package", "Review package"))
WORKSPACE, STUDY, FILE = "the Workspace", "study B", "a saved review"


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
    if title:
        layout.addWidget(_label(title, "cardTitle"))
    return card, layout


def _cell(value) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    return str(value)


class PhysicalReviewPanel(QWidget):
    """Section C of the Plate Study page."""

    def __init__(self, study_source: Optional[Callable[[], wb.Study]] = None,
                 ask_folder: Optional[Callable[[], str]] = None, ask_open: Optional[Callable[[], str]] = None,
                 ask_save: Optional[Callable[[], str]] = None, ask_file: Optional[Callable[[str], str]] = None):
        super().__init__()
        self._study_source = study_source or (lambda: None)
        self._ask_folder = ask_folder or self._dialog_folder
        self._ask_open = ask_open or self._dialog_open
        self._ask_save = ask_save or self._dialog_save
        self._ask_file = ask_file or self._dialog_file
        self.inputs = (None, None, None, None, None)  # FE preview, FE identity, exp preview, exp identity, set index
        self.record: Optional[dict] = None
        self.origin: Optional[str] = None
        self.built_with = None  # what the review was built from (to tell a STALE review)
        self.review_inputs: Optional[pr.ReviewInputs] = None
        self.reopened: Optional[dict] = None
        self.inp_path: Optional[str] = None
        self.owner_documents: list = []
        self.tables: dict = {}
        self.export_message = ""
        self.last_export: tuple = ()
        self.refusal: Optional[tuple] = None
        self.active = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        head, head_layout = _card(TITLE)
        head_layout.addWidget(_label(INTRO, "hint"))
        head_layout.addWidget(_label(pr.SCIENTIFIC_STATUS, "warnings"))
        self.identity_line = _label("", "")
        self.identity_line.setObjectName("prIdentity")
        head_layout.addWidget(self.identity_line)
        self.state_labels = {}
        for key, caption in STATE_NAMES:
            label = _label("", "")
            label.setObjectName(f"prState_{key}")
            self.state_labels[key] = (caption, label)
            head_layout.addWidget(label)
        self.freshness_line = _label("", "error")
        self.freshness_line.setObjectName("prFreshness")
        head_layout.addWidget(self.freshness_line)
        buttons = QVBoxLayout()  # buttons in a column: no page width; clicked(bool) never reaches an optional argument
        for text, slot, name in (("Build review from the Workspace (PLATE 261027 + M11)",
                                  lambda: self.build_from_workspace(), "prBuildWorkspace"),
                                 ("Build review from study B", lambda: self.build_from_study(), "prBuildStudy"),
                                 ("Open review...", lambda: self.open_review(), "prOpen"),
                                 ("Save review...", lambda: self.save_review(), "prSave")):
            button = QPushButton(text)
            button.setObjectName(name)
            button.clicked.connect(slot)
            buttons.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
        head_layout.addLayout(buttons)
        self.message = _label("", "hint")
        self.message.setObjectName("prMessage")
        head_layout.addWidget(self.message)
        layout.addWidget(head)
        steps_card, steps_layout = _card("Sections")
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        self.step_buttons = QButtonGroup(self)
        self.step_buttons.setExclusive(True)
        self.pages = QStackedWidget()
        self.pages.setObjectName("prSections")
        self.bodies = []
        for index, title in enumerate(STEPS):
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)
            page_layout.setSpacing(10)
            page_layout.addWidget(_label(title, "sectionTitle"))
            if index == 0:
                self._build_source_controls(page_layout)
            if index == len(STEPS) - 1:
                self._build_export_controls(page_layout)
            body = QVBoxLayout()
            body.setSpacing(8)
            page_layout.addLayout(body)
            page_layout.addStretch(1)
            self.bodies.append(body)
            self.pages.addWidget(page)
            button = QPushButton(title)
            button.setObjectName(f"prStep{index + 1}")
            button.setCheckable(True)
            self.step_buttons.addButton(button, index)
            grid.addWidget(button, index // 2, index % 2)
        self.step_buttons.button(0).setChecked(True)
        self.step_buttons.idClicked.connect(self.show_step)
        steps_layout.addLayout(grid)
        layout.addWidget(steps_card)
        layout.addWidget(self.pages)
        self._refresh()

    # ------------------------------------------------------------------------------------------ dialogs

    def _dialog_folder(self) -> str:
        return QFileDialog.getExistingDirectory(self, "Choose the folder for the physical readiness dossier")

    def _dialog_open(self) -> str:
        return QFileDialog.getOpenFileName(self, "Open a physical readiness review", "", "Review (*.json)")[0]

    def _dialog_save(self) -> str:
        return QFileDialog.getSaveFileName(self, "Save the physical readiness review", "physical_readiness.json",
                                           "Review (*.json)")[0]

    def _dialog_file(self, title: str) -> str:
        return QFileDialog.getOpenFileName(self, title, "", "All files (*)")[0]

    # ------------------------------------------------------------------------------------------ building

    def _build_source_controls(self, layout) -> None:
        card, inner = _card("Documents chosen as evidence (recorded by SHA-256; their reading is NOT confirmed)")
        inner.addWidget(_label("The program does not search any disk. Choose a document explicitly; it is hashed and "
                               "recorded with the kind of claim it may support. Loading it never confirms its "
                               "scientific interpretation: the owner's answer does.", "hint"))
        self.claim_choice = QComboBox()
        self.claim_choice.setObjectName("prClaim")
        for claim in pr.CLAIM_TYPES:
            self.claim_choice.addItem(claim, claim)
        inner.addWidget(self.claim_choice, 0, Qt.AlignmentFlag.AlignLeft)
        for text, slot, name in (("Add evidence document...", lambda: self.add_document(), "prAddDocument"),
                                 ("Choose the FE input (INP) to hash...", lambda: self.choose_inp(), "prChooseInp")):
            button = QPushButton(text)
            button.setObjectName(name)
            button.clicked.connect(slot)
            inner.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(card)

    def _build_export_controls(self, layout) -> None:
        card, inner = _card("Export the dossier")
        inner.addWidget(_label("Writes the seven documents of the dossier (the readiness record, the evidence matrix, "
                               "the modal observations, the reuse of the sensitivities, the FE applicability plan, the "
                               "owner's evidence request and the readable report), with the owner's request also as "
                               "JSON, into a new folder inside the folder you choose, outside the program. The sources "
                               "are confirmed on disk first; nothing is overwritten.", "hint"))
        self.export_button = QPushButton("Export dossier...")
        self.export_button.setObjectName("prExport")
        self.export_button.clicked.connect(lambda: self.export())
        inner.addWidget(self.export_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.export_label = _label("", "hint")
        self.export_label.setObjectName("prExportStatus")
        inner.addWidget(self.export_label)
        layout.addWidget(card)

    def show_step(self, index: int) -> None:
        self.activate()
        self.pages.setCurrentIndex(index)
        self.step_buttons.button(index).setChecked(True)

    def activate(self) -> None:
        if not self.active:
            self.active = True
            self._refresh()

    def _say(self, text: str) -> None:
        self.message.setText(text)

    # ------------------------------------------------------------------------------------------ inputs and freshness

    def set_inputs(self, fe_preview, fe_identity, experimental_preview, experimental_identity, set_index) -> None:
        self.inputs = (fe_preview, fe_identity, experimental_preview, experimental_identity, set_index)
        self._refresh()

    def _workspace_key(self) -> tuple:
        fe_preview, fe_identity, exp_preview, exp_identity, set_index = self.inputs
        return (id(fe_preview), (fe_identity or {}).get("sha256"), id(exp_preview), (exp_identity or {}).get("sha256"),
                set_index, self.inp_path, tuple(d.sha256 for d in self.owner_documents))

    def _study_key(self) -> Optional[tuple]:
        study = self._study_source()
        if study is None:
            return None
        return (wb.passport_fingerprint(study.passport), wb.evidence_fingerprint(study),
                str(wb.input_fingerprint(study)), str((study.diagnostics or {}).get("inputs")),
                (study.sensitivities or {}).get("file_sha256"), study.kind,
                tuple(d.sha256 for d in self.owner_documents))

    def freshness(self) -> tuple:
        """(state, reason) of the shown review: CURRENT, STALE (built for other inputs) or NOT_CURRENT (a reopened
        review whose sources do not verify on disk)."""
        if self.record is None:
            return "NONE", ""
        if self.origin == FILE:
            state = (self.reopened or {}).get("state", "NOT_CURRENT")
            return ("CURRENT", "") if state == "CURRENT" else ("NOT_CURRENT", "; ".join(
                (self.reopened or {}).get("reasons", ())) or "its sources do not verify on disk")
        now = self._workspace_key() if self.origin == WORKSPACE else self._study_key()
        if now != self.built_with:
            what = ("the Workspace files, the modal set or the evidence documents changed" if self.origin == WORKSPACE
                    else "study B (its passport, evidence, linked files, diagnostics or sensitivities) changed")
            return "STALE", what
        return "CURRENT", ""

    # ------------------------------------------------------------------------------------------ commands

    def build_from_workspace(self) -> bool:
        self.activate()
        try:
            inputs = pr.inputs_from_workspace(*self.inputs, documents=tuple(self.owner_documents),
                                              inp_path=self.inp_path)
            record = pr.build_review(inputs)
        except pr.ReviewRefused as refusal:
            self._fail(refusal)
            return False
        self._take(record, WORKSPACE, inputs, self._workspace_key())
        self._say("The review of PLATE-300x300x1mm 261027 and M11 was built from the Workspace files (verified by "
                  "SHA-256).")
        return True

    def build_from_study(self) -> bool:
        self.activate()
        study = self._study_source()
        if study is None:
            self._say("No study in B. New Single Plate.")
            return False
        try:
            inputs = pr.inputs_from_study(study, tuple(self.owner_documents))
            record = pr.build_review(inputs)
        except pr.ReviewRefused as refusal:
            self._fail(refusal)
            return False
        self._take(record, STUDY, inputs, self._study_key())
        self._say(f"The review of {record['identity']['specimen']} was built from study B.")
        return True

    def _fail(self, refusal: pr.ReviewRefused) -> None:
        self.record, self.origin, self.built_with, self.review_inputs, self.reopened = None, None, None, None, None
        self.export_message = ""
        self.refusal = (refusal.state, str(refusal))
        self._say(f"Not built — {refusal.state}: {refusal}")
        self._refresh()

    def _take(self, record: dict, origin: str, inputs, key) -> None:
        self.record, self.origin, self.review_inputs, self.built_with, self.reopened = record, origin, inputs, key, None
        self.export_message = ""
        self.refusal = None
        self._refresh()

    def add_document(self, path: Optional[str] = None, claim: Optional[str] = None) -> bool:
        self.activate()
        path = path if path is not None else self._ask_file("Choose a document offered as evidence")
        if not path:
            return False
        claim = claim or self.claim_choice.currentData()
        doc = pr.document(pr.OWNER_DOCUMENT, path, "chosen by the user as evidence", claim)
        if doc.sha256 is None:
            self._say(f"{path} cannot be read; nothing was recorded.")
            return False
        self.owner_documents.append(doc)
        self._say(f"Recorded {Path(path).name} ({doc.sha256[:12]}…, {doc.size} bytes) as possible evidence of "
                  f"{claim}; its interpretation is not confirmed. Build the review again to include it.")
        self._refresh()
        return True

    def choose_inp(self, path: Optional[str] = None) -> bool:
        self.activate()
        path = path if path is not None else self._ask_file("Choose the FE input (INP) of M11 (hashed only)")
        if not path:
            return False
        self.inp_path = path
        self._say(f"The INP {Path(path).name} will be hashed (never run) when the review is built again.")
        self._refresh()
        return True

    def export(self, folder: Optional[str] = None) -> bool:
        self.activate()
        state, reason = self.freshness()
        if self.record is None or state != "CURRENT":
            self.export_message = ("Not exported: " + (f"the review is {state} ({reason})" if self.record is not None
                                                      else "no review is built"))
            self._refresh()
            return False
        folder = folder if folder is not None else self._ask_folder()
        if not folder:
            return False
        try:
            written = pr.export_dossier(self.record, folder)
        except (pr.ExportRefused, OSError) as error:
            self.export_message = f"Not exported (nothing written): {error}"
            self._refresh()
            return False
        self.last_export = written
        self.export_message = "Dossier written:\n" + "\n".join(str(p) for p in written)
        self._refresh()
        return True

    def save_review(self, path: Optional[str] = None) -> bool:
        self.activate()
        if self.record is None:
            self._say("No review to save.")
            return False
        path = path if path is not None else self._ask_save()
        if not path:
            return False
        pr.save_review(self.record, path)
        self._say(f"Review saved: {path}")
        return True

    def open_review(self, path: Optional[str] = None) -> bool:
        self.activate()
        path = path if path is not None else self._ask_open()
        if not path:
            return False
        try:
            record = pr.open_review(path)
        except pr.ReviewRefused as refusal:
            self._say(f"Not opened — {refusal}")
            return False
        self.record, self.origin, self.review_inputs, self.built_with = record, FILE, None, None
        self.reopened = pr.reopened_state(record)
        self.export_message = ""
        self.refusal = None
        self._say(f"Review opened: {path}. Its sources were verified on disk again: {self.reopened['state']}.")
        self._refresh()
        return True

    # ------------------------------------------------------------------------------------------ display

    @staticmethod
    def _clear(layout) -> None:
        while layout.count():
            widget = layout.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _table(self, body, key, title, headers, rows, stretch, text_columns=()) -> None:
        body.addWidget(_label(title, "sectionTitle"))
        if not rows:
            body.addWidget(_label("None.", "hint"))
            return
        table = DiagnosticTable(headers, [tuple(_cell(v) for v in row) for row in rows], stretch, (), text_columns)
        table.setObjectName(f"pr_{key}")
        self.tables[key] = table
        body.addWidget(table)

    def _refresh(self) -> None:
        for body in self.bodies:
            self._clear(body)
        self.tables = {}
        record = self.record
        state, reason = self.freshness()
        refusal = self.refusal
        if record is None:
            self.identity_line.setText("No review built yet." if not refusal else f"Refused: {refusal[1]}")
            for key, (caption, label) in self.state_labels.items():
                label.setText(f"{caption}: {pr.SOURCE_NOT_VERIFIED}" if refusal and key == "sources" else "")
                label.setVisible(bool(refusal and key == "sources"))
            self.freshness_line.setVisible(False)
            self.export_button.setEnabled(False)
            self.export_label.setText(self.export_message)
            return
        i = record["identity"]
        self.identity_line.setText(f"Specimen {i['specimen']} · series {i['series']} · modal set {i['modal_set']} · FE "
                                   f"{i['fe_model']} · experimental {str(i['experimental_sha256'])[:12]}… · FE "
                                   f"manifest {str(i['fe_manifest_sha256'])[:12]}… · built from {self.origin}")
        for key, (caption, label) in self.state_labels.items():
            label.setText(f"{caption}: {record['states'][key]}")
            label.setVisible(True)
        current = state == "CURRENT"
        self.freshness_line.setText("" if current else f"Review {state} — NOT CURRENT: {reason}. Its tables are not "
                                    "shown and it is not exported; build it again.")
        self.freshness_line.setVisible(not current)
        self.export_button.setEnabled(current)
        self.export_label.setText(self.export_message)
        if not current:
            return
        self._show_sources(record, self.bodies[0])
        self._show_evidence(record, self.bodies[1])
        self._show_questions(record, self.bodies[2])
        self._show_modal(record, self.bodies[3])
        self._show_observability(record, self.bodies[4])
        self._show_applicability(record, self.bodies[5])
        self._show_report(record, self.bodies[6])

    def _show_sources(self, record, body) -> None:
        self._table(body, "sources", f"Source audit — {record['sources']['state']}",
                    ("Role", "Path", "SHA-256", "Size", "Origin", "May support", "Expected SHA-256", "State"),
                    [(r["role"], r["path"], r["sha256"], r["size"], r["origin"], r["supports"], r["expected_sha256"],
                      r["state"]) for r in record["sources"]["audit"]], 5, (0, 1, 4, 5, 7))
        body.addWidget(_label(f"Archive: {record['sources']['archive']}", "hint"))
        if self.reopened:
            body.addWidget(_label("Verified on disk when reopened: " + "; ".join(
                f"{role}: {state}" for role, _path, state in self.reopened["checks"]), "hint"))
        if self.owner_documents:
            body.addWidget(_label("Documents recorded in this session (included when the review is built again): "
                                  + "; ".join(f"{Path(d.path).name} {d.sha256[:12]}… ({d.supports})"
                                              for d in self.owner_documents), "hint"))

    def _show_evidence(self, record, body) -> None:
        evidence = record["evidence"]
        body.addWidget(_label(f"Registration: {evidence['registration']} · open facts ({len(evidence['open_facts'])}): "
                              + (", ".join(evidence["open_facts"]) or "none"), "warnings"))
        for chain in (pr.CHAIN_A, pr.CHAIN_B, pr.SUPPORTING):
            rows = [r for r in evidence["rows"] if r["chain"] == chain]
            if rows:
                key = {pr.CHAIN_A: "chainA", pr.CHAIN_B: "chainB"}.get(chain, "supporting")
                self._table(body, key, chain, ("Fact", "Topic", "Value", "Provenance", "Source", "Source SHA-256",
                                               "Dependencies", "Status", "Blocking reason"),
                            [(r["fact"], r["topic"], r["value"], r["provenance"], r["source"], r["source_sha256"],
                              r["dependencies"], r["status"], r["blocking_reason"]) for r in rows], 8,
                            (0, 1, 2, 3, 4, 5, 6, 7, 8))
        body.addWidget(_label("\n".join(f"• {rule}" for rule in evidence["rules"]), "hint"))
        if evidence["closing_evidence"]:
            body.addWidget(_label("What would close the open facts (existing records):\n" + "\n".join(
                f"• {c['facts']}: {c['evidence']}" for c in evidence["closing_evidence"]), "hint"))
        if record["test_conditions"]:
            self._table(body, "conditions", "Test conditions: 261016 (history only) and 261027 (primary)",
                        ("Series", "Item", "Value", "Provenance", "Source"),
                        [(c["series"], c["item"], c["value"], c["provenance"], c["source"])
                         for c in record["test_conditions"]], 2, (0, 1, 2, 3, 4))

    def _show_questions(self, record, body) -> None:
        questions = record["owner_evidence_request"]["questions"]
        body.addWidget(_label(f"{len(questions)} questions for the owner (the answer fields stay empty here; they are "
                              "exported in OWNER_EVIDENCE_REQUEST.md and owner_evidence_request.json).", "warnings"))
        self._table(body, "questions", "Owner evidence request", ("Id", "Group", "Question", "Closes",
                                                                  "Acceptable evidence"),
                    [(q["id"], q["group"], q["question"], q["closes"], q["acceptable_evidence"]) for q in questions], 2,
                    (0, 1, 2, 3, 4))

    def _show_modal(self, record, body) -> None:
        modal = record["modal_evidence"]
        body.addWidget(_label(f"Experimental records: {modal['experimental_records']} ({modal['fitted_set']}) · elastic "
                              f"FE modes: {modal['fe_elastic_modes']} · rigid-body FE excluded: "
                              + (", ".join(f"FE{n}" for n in modal["fe_rigid_excluded"]) or "none")
                              + f" · registration: {modal['registration']} · MAC: {modal['mac']} · pairs: none · FIT / "
                              f"HOLDOUT: {modal['fit_holdout']}", "warnings"))
        body.addWidget(_label("\n".join(f"• {s}" for s in modal["statements"]), "hint"))
        self._table(body, "modal", "Modal observations (frequency diagnostics only; never pairs)",
                    ("Kind", "Record", "Hz", "Nearest", "Δf %", "Diagnostic", "Close group", "Research MAC",
                     "Archived research status", "Pair", "History"),
                    [(r["kind"], r["record"], r["frequency_hz"], r["nearest"], r["difference_percent"], r["diagnostic"],
                      r["close_group"], r["research_mac"], r["archived_research_status"], r["pair"], r["history"])
                     for r in modal["rows"]], 10, (0, 1, 3, 5, 6, 7, 8, 9, 10))
        if modal["archived_clusters"]:
            body.addWidget(_label("Archived close pairs (PRIORITY-2 confirm_cluster): " + "; ".join(
                f"{c['pair']} {c['status']}" for c in modal["archived_clusters"]), "hint"))

    def _show_observability(self, record, body) -> None:
        observe = record["observability"]
        body.addWidget(_label("1. What the FE model distinguishes mathematically — " + observe["fe_only_statement"],
                              "hint"))
        self._table(body, "fe_only", "FE-only rank of the sensitivity matrix",
                    ("Parameters", "Rank", "Of", "Condition", "Terms", "Status", "Valid for", "Basis"),
                    [(r["parameters"], r["rank"], r["of"], r["condition"], r["terms"], r["status"], r["valid_for"],
                      r["basis"]) for r in observe["fe_only"]], 7, (0, 5, 6, 7))
        body.addWidget(_label(f"2. What the confirmed experimental observations support — "
                              f"{observe['experimental']['status']}: {observe['experimental']['reason']}.", "warnings"))
        if observe["hypotheses"]:
            self._table(body, "hypotheses", f"Archived hypotheses — {pr.HYPOTHESIS_LABELS}",
                        ("Scenario", "E1 (MPa)", "E2 (MPa)", "G12 (MPa)", "Assumed pairs", "Status"),
                        [(h["scenario"], h["E1_MPa"], h["E2_MPa"], h["G12_MPa"], h["assumed_pairs"], h["status"])
                         for h in observe["hypotheses"]], 4, (0, 4, 5))
        self._table(body, "reuse", "Reuse of the archived sensitivities",
                    ("Existing result", "Parameterisation", "FE identity", "Branch tracking", "Reuse status", "Reason"),
                    [tuple(r[c] for c in pr.REUSE_COLUMNS) for r in record["sensitivity_reuse"]], 5,
                    (0, 1, 2, 3, 4, 5))

    def _show_applicability(self, record, body) -> None:
        plan = record["fe_applicability_plan"]
        body.addWidget(_label(plan["status"], "warnings"))
        self._table(body, "applicability", "FE applicability variants",
                    ("Variant", "Available inputs", "Missing inputs", "Existing FE assets", "Future runs",
                     "Owner authorisation", "Scientific purpose"),
                    [tuple(r[c] for c in pr.APPLICABILITY_COLUMNS) for r in plan["variants"]], 6,
                    (0, 1, 2, 3, 4, 5, 6))
        self._table(body, "stages", "Stages kept apart (none is authorised)",
                    ("Stage", "Purpose", "Existing results", "New FE runs", "Prerequisites", "Authorisation"),
                    [(s["stage"], s["purpose"], s["existing_results"], s["new_fe_runs"], s["prerequisites"],
                      s["authorisation"]) for s in plan["stages"]], 1, (0, 1, 2, 3, 4, 5))
        body.addWidget(_label("\n".join(f"• {n}" for n in plan["never"]), "hint"))

    def _show_report(self, record, body) -> None:
        body.addWidget(_label("What blocks a physical identification:\n" + "\n".join(
            f"• {b}" for b in record["blocking"]), "warnings"))
        body.addWidget(_label("\n".join(record["state_notes"]), "hint"))


__all__ = ["PhysicalReviewPanel", "STEPS", "TITLE"]
