"""PRIORITY-8: B. New Single Plate — Research Workbench (PySide6; RESEARCH_ONLY).

A research study of ANY single rectangular CFRP plate without a core, in eight steps:

1. Specimen & Test Setup — the identifiers (design, physical specimen, test run) and the set-up, each with provenance;
2. FE and Experimental Inputs — the files read in the Workspace, linked by SHA-256 (a change of a file or of the modal
   set is shown at once and invalidates the results); a synthetic demonstration study takes its synthetic inputs;
3. Measurements & Geometry — length, width, mass, density, thickness readings, engineering constants, with units,
   method and provenance; NOT_AVAILABLE when unknown; derived quantities marked DERIVED;
4. Physical Registration Evidence — the facts of the two links with their provenance; a complete set is
   EVIDENCE_COMPLETE_NOT_FROZEN, never a registration (nothing is chosen from a frequency, a MAC or a shape);
5. Modal Diagnostics — every experimental record (EXP1 included) and every elastic FE mode (the code's own rigid-body
   criterion), nearest frequencies only (never pairs), close groups, independent shape views;
6. Parameter Observability — every condition of an identification kept apart, NOT_READY_FOR_IDENTIFICATION with the
   reasons, the plan of the FE sensitivities when there are none;
7. Offline Research Study — only with a sensitivity table of THIS FE model, a declared observation set and the owner's
   registration decision; the existing bounded LM on a log-linear approximation; a DIAGNOSTIC_OPTIMIZER_CANDIDATE;
8. Report & Save — the study file (JSON), its reopening (sources checked by SHA-256), the Markdown / JSON / CSV report.

The business logic lives in ``services.generic_plate_workbench``, ``generic_plate_evidence`` and
``generic_plate_offline_study``; this panel only edits and shows. No Abaqus, no registration, no material value.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)

from new_gui.diagnostic_panel import DiagnosticTable
from new_gui.shape_panel import ShapePanel
from new_gui.workspace_state import EXPERIMENTAL, FE
from services import generic_plate_evidence as gev
from services import generic_plate_offline_study as off
from services import generic_plate_workbench as wb

TITLE = "B. New Single Plate — Research Workbench"
INTRO = ("A research study of one single rectangular CFRP plate without a core, of any size: its own identifiers, "
         "measurements, files and evidence. Nothing is shared with the current plate study (A) and no value of another "
         "specimen is used. Research only; no registration, pair or material value is created here.")
STEPS = ("1. Specimen & Test Setup", "2. FE and Experimental Inputs", "3. Measurements & Geometry",
         "4. Physical Registration Evidence", "5. Modal Diagnostics", "6. Parameter Observability",
         "7. Offline Research Study", "8. Report & Save")
STEP_BUTTONS = ("1. Setup", "2. Inputs", "3. Measurements", "4. Evidence", "5. Diagnostics", "6. Observability",
                "7. Offline study", "8. Report & save")
DONE, WAITING, BLOCKED_TEXT = "done", "waiting for data", "blocked"
PROVENANCE_CHOICES = ("NOT_AVAILABLE", "MEASURED", "INSTRUMENT_RECORD", "HUMAN_CONFIRMED", "DERIVED", "CANDIDATE",
                      "CONVENTION_ONLY", "NOT_VERIFIED", "SYNTHETIC")
CLAIM_LABELS = {"suspension": "Suspension / boundary", "excitation": "Excitation", "measured_face": "Measured face",
                "instrument_axes": "Instrument coordinates and axes", "measured_dofs": "Measured DOF",
                "material_orientation": "Material orientation (warp / fill)", "layup": "Layup",
                "fe_model_version": "FE model and version"}
QUANTITIES = (("length", "Length", "length"), ("width", "Width", "length"), ("mass", "Mass", "mass"),
              ("density", "Density", "density"))
THICKNESS_HEADERS = ("Position", "Value", "Unit", "Provenance", "Method", "Source")
CONSTANT_HEADERS = ("Name", "Value", "Unit", "Role", "Provenance", "Source")
FACT_HEADERS = ("Fact", "Value", "Provenance", "Source", "What it states")
EXAMPLE_FACT = {"scanned_face": "marked", "grid_plus_u_edge": "2", "grid_plus_v_edge": "1",
                "scan_window_offsets_mm": "-u=10, +u=10, -v=10, +v=10", "scan_scale": "mm_per_unit=1000",
                "scan_metric_geometry": "yes", "measured_dof": "Z", "fe_x_along_edges": "1/3", "fe_origin_corner": "3,4",
                "fe_normal_face": "marked"}


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


def _combo(values, name: str = "") -> QComboBox:
    combo = QComboBox()
    for value in values:
        combo.addItem(value, value)
    if name:
        combo.setObjectName(name)
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(8)
    return combo


def _edit(name: str = "", placeholder: str = "") -> QLineEdit:
    edit = QLineEdit()
    if name:
        edit.setObjectName(name)
    edit.setPlaceholderText(placeholder)
    edit.setMinimumWidth(0)
    return edit


def _number(text: str) -> Optional[float]:
    text = str(text).strip().replace(",", ".")
    return None if not text else float(text)


class _RowsEditor(QWidget):
    """Rows of input fields under a header (the window's tables stay read-only): a line edit per column, a choice
    list where the column has fixed choices, a label where the column is not edited."""

    def __init__(self, headers, name: str, choices: Optional[dict] = None, fixed=()):
        super().__init__()
        self.setObjectName(name)
        self.headers, self.choices, self.fixed = tuple(headers), dict(choices or {}), set(fixed)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(6)
        for column, text in enumerate(self.headers):
            self.grid.addWidget(_label(text, "hint"), 0, column)
            self.grid.setColumnStretch(column, 0 if column in self.choices else 1)
        self.widgets: list = []

    def set_rows(self, rows) -> None:
        for row in self.widgets:
            for widget in row:
                self.grid.removeWidget(widget)
                widget.setParent(None)
                widget.deleteLater()
        self.widgets = []
        for values in rows:
            self.add_row(values)

    def add_row(self, values=()) -> None:
        index = len(self.widgets) + 1
        row = []
        for column in range(len(self.headers)):
            value = values[column] if column < len(values) else ""
            text = "" if value is None else str(value)
            if column in self.choices:
                widget = _combo(self.choices[column], f"{self.objectName()}_{index}_{column}")
                widget.setCurrentIndex(max(0, widget.findData(text)))
            elif column in self.fixed:
                widget = _label(text, "")
                widget.setObjectName(f"{self.objectName()}_{index}_{column}")
            else:
                widget = _edit(f"{self.objectName()}_{index}_{column}")
                widget.setText(text)
            self.grid.addWidget(widget, index, column)
            row.append(widget)
        self.widgets.append(row)

    def rows(self) -> list:
        out = []
        for row in self.widgets:
            out.append([(w.currentData() if isinstance(w, QComboBox) else w.text()).strip() for w in row])
        return out


class GenericPlatePanel(QWidget):
    """The workbench of a new single plate (section B of the Plate Study page)."""

    def __init__(self, ask_open: Optional[Callable[[], str]] = None, ask_save: Optional[Callable[[], str]] = None,
                 ask_folder: Optional[Callable[[], str]] = None, ask_file: Optional[Callable[[str], str]] = None):
        super().__init__()
        self._ask_open = ask_open or self._dialog_open
        self._ask_save = ask_save or self._dialog_save
        self._ask_folder = ask_folder or self._dialog_folder
        self._ask_file = ask_file or self._dialog_file
        self.study = wb.new_study()
        self.inputs = (None, None, None, None, None)  # FE preview, FE identity, exp preview, exp identity, set index
        self.messages: dict = {}
        self.tables: dict = {}
        self.last_export: list = []
        self.study_path: Optional[Path] = None
        self.active = False  # nothing is evaluated or shown before the page is first shown or used
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        head, head_layout = _card(TITLE)
        head_layout.addWidget(_label(INTRO, "hint"))
        head_layout.addWidget(_label(wb.SCIENTIFIC_STATUS, "warnings"))
        self.study_line = _label("", "")
        self.study_line.setObjectName("workbenchStudy")
        head_layout.addWidget(self.study_line)
        self.step_line = _label("", "hint")
        self.step_line.setObjectName("workbenchSteps")
        head_layout.addWidget(self.step_line)
        buttons = QVBoxLayout()  # buttons in a column: no page width
        for text, slot, name in (("New study", self.new_study, "wbNew"),
                                 ("New synthetic demo study", lambda: self.new_study(wb.SYNTHETIC_DEMO), "wbNewDemo"),
                                 ("Open study...", lambda: self.open_study(), "wbOpen"),
                                 ("Save study...", lambda: self.save_study(), "wbSave")):
            button = QPushButton(text)
            button.setObjectName(name)
            button.clicked.connect(slot)
            buttons.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
        head_layout.addLayout(buttons)
        self.message = _label("", "hint")
        self.message.setObjectName("workbenchMessage")
        head_layout.addWidget(self.message)
        layout.addWidget(head)
        # the eight steps: a grid of step buttons (two columns: never wider than the page) over the step pages
        steps_card, steps_layout = _card("Steps")
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        self.step_buttons = QButtonGroup(self)
        self.step_buttons.setExclusive(True)
        self.tabs = QStackedWidget()
        self.tabs.setObjectName("workbenchSteps")
        builders = (self._build_setup, self._build_inputs, self._build_measurements, self._build_evidence,
                    self._build_diagnostics, self._build_observability, self._build_offline, self._build_report)
        for index, (title, short, build) in enumerate(zip(STEPS, STEP_BUTTONS, builders)):
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)
            page_layout.setSpacing(10)
            page_layout.addWidget(_label(title, "sectionTitle"))
            build(page_layout)
            page_layout.addStretch(1)
            self.tabs.addWidget(page)
            button = QPushButton(short.replace("&", "&&"))  # "&" is shown, not a mnemonic
            button.setObjectName(f"wbStep{index + 1}")
            button.setCheckable(True)
            button.setToolTip(title)
            self.step_buttons.addButton(button, index)
            grid.addWidget(button, index // 2, index % 2)
        self.step_buttons.button(0).setChecked(True)
        self.step_buttons.idClicked.connect(self.show_step)
        steps_layout.addLayout(grid)
        layout.addWidget(steps_card)
        layout.addWidget(self.tabs)
        self._fill_forms()
        self._refresh()

    # ------------------------------------------------------------------------------------------ dialogs

    def _dialog_open(self) -> str:
        return QFileDialog.getOpenFileName(self, "Open a single-plate study", "", "Study (*.json)")[0]

    def _dialog_save(self) -> str:
        return QFileDialog.getSaveFileName(self, "Save the single-plate study", "single_plate_study.json",
                                           "Study (*.json)")[0]

    def _dialog_folder(self) -> str:
        return QFileDialog.getExistingDirectory(self, "Choose the folder for the single-plate report")

    def _dialog_file(self, title: str) -> str:
        return QFileDialog.getOpenFileName(self, title, "", "JSON (*.json);;All files (*)")[0]

    # ------------------------------------------------------------------------------------------ building the steps

    def _build_setup(self, layout) -> None:
        card, inner = _card("Identifiers and test set-up")
        grid = QGridLayout()
        self.id_edits = {}
        for row, (key, text) in enumerate((("design_id", "Design id"), ("physical_specimen_id", "Physical specimen id"),
                                           ("test_run_id", "Test run id"), ("measurement_date", "Date of the test"),
                                           ("measurement_method", "Measurement method"))):
            grid.addWidget(_label(text), row, 0)
            self.id_edits[key] = _edit(f"wb_{key}")
            grid.addWidget(self.id_edits[key], row, 1, 1, 3)
        self.claim_edits = {}
        base = len(self.id_edits)
        for row, name in enumerate(wb.CLAIMS, start=base):
            grid.addWidget(_label(CLAIM_LABELS.get(name, name)), row, 0)
            value, provenance, source = _edit(f"wb_claim_{name}"), _combo(PROVENANCE_CHOICES, f"wb_claim_{name}_provenance"), _edit(
                f"wb_claim_{name}_source", "source")
            self.claim_edits[name] = (value, provenance, source)
            grid.addWidget(value, row, 1)
            grid.addWidget(provenance, row, 2)
            grid.addWidget(source, row, 3)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(3, 1)
        inner.addLayout(grid)
        apply = QPushButton("Apply identifiers and set-up")
        apply.setObjectName("wbApplySetup")
        apply.clicked.connect(self.apply_setup)
        inner.addWidget(apply, 0, Qt.AlignmentFlag.AlignLeft)
        inner.addWidget(_label("Each statement keeps its provenance; an empty one is NOT_AVAILABLE. The material "
                               "orientation decides whether E1 ≠ E2 could ever be studied (SPEC v1.1 §5.2); without "
                               "it only E1 = E2 = E_in_plane.", "hint"))
        layout.addWidget(card)

    def _build_inputs(self, layout) -> None:
        card, inner = _card("Files of this study (by SHA-256)")
        inner.addWidget(_label("Read the FE results (an extracted package manifest.json) and the experimental file on "
                               "the Workspace page and choose the modal set on the Analysis page; then link them here. "
                               "A different file or set afterwards is shown at once and the results are removed.",
                               "hint"))
        self.inputs_label = _label("", "")
        self.inputs_label.setObjectName("wbInputs")
        inner.addWidget(self.inputs_label)
        row = QVBoxLayout()  # buttons in a column: no page width
        for text, slot, name in (("Link the Workspace inputs", self.link_inputs, "wbLink"),
                                 ("Verify recorded sources", self.verify_sources, "wbVerify"),
                                 ("Choose a moved source file...", self.relocate, "wbRelocate"),
                                 ("Load synthetic inputs...", lambda: self.load_synthetic_inputs(), "wbSynthetic")):
            button = QPushButton(text)
            button.setObjectName(name)
            button.clicked.connect(slot)
            row.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
            if name == "wbSynthetic":
                self.synthetic_button = button
        inner.addLayout(row)
        self.relocate_role = _combo(("experimental", "fe"), "wbRelocateRole")
        role_row = QHBoxLayout()
        role_row.addWidget(_label("Source to relocate"), 0)
        role_row.addWidget(self.relocate_role, 0)
        role_row.addStretch(1)
        inner.addLayout(role_row)
        self.sources_label = _label("", "hint")
        self.sources_label.setObjectName("wbSources")
        inner.addWidget(self.sources_label)
        layout.addWidget(card)

    def _build_measurements(self, layout) -> None:
        card, inner = _card("Measurements (value, unit, uncertainty, provenance, method, source)")
        grid = QGridLayout()
        self.quantity_edits = {}
        for index, (key, text, kind) in enumerate(QUANTITIES):
            row = 2 * index  # two lines per quantity: no page width
            grid.addWidget(_label(text), row, 0)
            value, unit = _edit(f"wb_{key}_value", wb.NOT_AVAILABLE), _combo(tuple(wb.UNITS[kind]), f"wb_{key}_unit")
            uncertainty = _edit(f"wb_{key}_uncertainty", "± uncertainty")
            provenance = _combo(PROVENANCE_CHOICES, f"wb_{key}_provenance")
            method, source = _edit(f"wb_{key}_method", "method"), _edit(f"wb_{key}_source", "source")
            self.quantity_edits[key] = (value, unit, uncertainty, provenance, method, source)
            for column, widget in enumerate((value, unit, uncertainty), start=1):
                grid.addWidget(widget, row, column)
            for column, widget in enumerate((provenance, method, source), start=1):
                grid.addWidget(widget, row + 1, column)
        inner.addLayout(grid)
        inner.addWidget(_label("Thickness readings (one row per point; 9+ measured points for the normative prior)",
                               "sectionTitle"))
        self.thickness_table = _RowsEditor(THICKNESS_HEADERS, "wbThickness",
                                           {2: tuple(wb.UNITS["length"]), 3: PROVENANCE_CHOICES})
        inner.addWidget(self.thickness_table)
        inner.addWidget(_label("Engineering constants of the FE model (role FIXED or INITIAL)", "sectionTitle"))
        self.constant_table = _RowsEditor(CONSTANT_HEADERS, "wbConstants",
                                          {2: ("MPa", "GPa", "1"), 3: wb.ROLES, 4: PROVENANCE_CHOICES})
        inner.addWidget(self.constant_table)
        row = QVBoxLayout()  # buttons in a column: no page width
        for text, slot, name in (("Add thickness row", lambda: self.thickness_table.add_row(("", "", "mm", "MEASURED")),
                                  "wbAddThickness"),
                                 ("Add constant", lambda: self.constant_table.add_row(("", "", "MPa", "FIXED")),
                                  "wbAddConstant"),
                                 ("Apply measurements", self.apply_measurements, "wbApplyMeasurements")):
            button = QPushButton(text)
            button.setObjectName(name)
            button.clicked.connect(slot)
            row.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
        inner.addLayout(row)
        self.derived_label = _label("", "hint")
        self.derived_label.setObjectName("wbDerived")
        inner.addWidget(self.derived_label)
        layout.addWidget(card)

    def _build_evidence(self, layout) -> None:
        card, inner = _card("Physical registration evidence of this plate")
        inner.addWidget(_label("Each fact with its provenance and source. MEASURED, INSTRUMENT_RECORD and HUMAN_CONFIRMED "
                               "are independent evidence; CANDIDATE, CONVENTION_ONLY and NOT_VERIFIED never are. Nothing "
                               "is chosen from a frequency, a MAC or a shape. A complete set is not a registration: "
                               "freezing it is the owner's separate decision.", "hint"))
        self.fact_table = _RowsEditor(FACT_HEADERS, "wbFacts", {2: PROVENANCE_CHOICES}, fixed=(0, 4))
        inner.addWidget(self.fact_table)
        evaluate = QPushButton("Evaluate the evidence")
        evaluate.setObjectName("wbEvaluate")
        evaluate.clicked.connect(self.evaluate_evidence)
        inner.addWidget(evaluate, 0, Qt.AlignmentFlag.AlignLeft)
        self.evidence_label = _label("", "warnings")
        self.evidence_label.setObjectName("wbEvidence")
        inner.addWidget(self.evidence_label)
        layout.addWidget(card)

    def _build_diagnostics(self, layout) -> None:
        card, inner = _card("Modal diagnostics — frequency proximity only, never pairs")
        run = QPushButton("Run modal diagnostics")
        run.setObjectName("wbDiagnostics")
        run.clicked.connect(self.run_diagnostics)
        inner.addWidget(run, 0, Qt.AlignmentFlag.AlignLeft)
        self.diagnostics_body = QVBoxLayout()
        inner.addLayout(self.diagnostics_body)
        layout.addWidget(card)
        shapes, shapes_layout = _card("Shapes — independent views (no registration, no MAC)")
        self.shapes = {FE: ShapePanel(FE), EXPERIMENTAL: ShapePanel(EXPERIMENTAL)}
        for kind in (FE, EXPERIMENTAL):
            shapes_layout.addWidget(self.shapes[kind])
        layout.addWidget(shapes)

    def _build_observability(self, layout) -> None:
        card, inner = _card("Parameter observability — is an identification possible?")
        load = QPushButton("Load FE sensitivity table...")
        load.setObjectName("wbLoadSensitivities")
        load.clicked.connect(lambda: self.load_sensitivities())
        inner.addWidget(load, 0, Qt.AlignmentFlag.AlignLeft)
        self.readiness_status = _label("", "warnings")
        self.readiness_status.setObjectName("wbReadiness")
        inner.addWidget(self.readiness_status)
        self.readiness_body = QVBoxLayout()
        inner.addLayout(self.readiness_body)
        layout.addWidget(card)

    def _build_offline(self, layout) -> None:
        card, inner = _card("Offline research study (bounded LM on a log-linear approximation; no Abaqus)")
        inner.addWidget(_label("Needs: an FE sensitivity table of THIS FE model, an observation set declared before "
                               "the computation (FIT / HOLDOUT, parameters, bounds, σ) and the owner's decision that "
                               "the registration is admissible for a research computation (recorded, never made "
                               "here). The result is a DIAGNOSTIC_OPTIMIZER_CANDIDATE / NOT_A_RELEASE_VALUE / "
                               "NOT_A_MATERIAL_PROPERTY. MAC is never a term of the objective.", "hint"))
        row = QVBoxLayout()  # buttons in a column: no page width
        load = QPushButton("Load declared observation set...")
        load.setObjectName("wbLoadDeclaration")
        load.clicked.connect(lambda: self.load_declaration())
        self.run_button = QPushButton("Run offline research study")
        self.run_button.setObjectName("wbRunOffline")
        self.run_button.clicked.connect(self.run_offline)
        row.addWidget(load, 0, Qt.AlignmentFlag.AlignLeft)
        row.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)
        inner.addLayout(row)
        self.gate_label = _label("", "warnings")
        self.gate_label.setObjectName("wbGate")
        inner.addWidget(self.gate_label)
        self.offline_body = QVBoxLayout()
        inner.addLayout(self.offline_body)
        layout.addWidget(card)

    def _build_report(self, layout) -> None:
        card, inner = _card("Report and study file")
        row = QVBoxLayout()  # buttons in a column: no page width
        export = QPushButton("Export report...")
        export.setObjectName("wbExport")
        export.clicked.connect(lambda: self.export())
        row.addWidget(export, 0, Qt.AlignmentFlag.AlignLeft)
        inner.addLayout(row)
        inner.addWidget(_label("Approved material values: NOT_AVAILABLE — " + wb.SCIENTIFIC_STATUS + ".", "warnings"))
        self.export_label = _label("", "hint")
        self.export_label.setObjectName("wbExportStatus")
        inner.addWidget(self.export_label)
        self.history_label = _label("", "hint")
        self.history_label.setObjectName("wbHistory")
        inner.addWidget(self.history_label)
        layout.addWidget(card)

    # ------------------------------------------------------------------------------------------ the study and forms

    def show_step(self, index: int) -> None:
        """Show one step's page (the step buttons; the first show of a page activates the workbench)."""
        self.tabs.setCurrentIndex(index)
        self.step_buttons.button(index).setChecked(True)

    def _say(self, text: str) -> None:
        self.message.setText(text)

    def activate(self) -> None:
        """The page is shown (or used) for the first time: the study's state is evaluated and shown from now on."""
        if not self.active:
            self.active = True
            self._refresh()

    def new_study(self, kind: str = wb.PHYSICAL) -> None:
        self.active = True
        self.study = wb.new_study(kind)
        self.study_path = None
        self.last_export = []
        self._fill_forms()
        self._say("A new synthetic demonstration study (never a physical experiment)." if kind == wb.SYNTHETIC_DEMO
                  else "A new study of a physical plate.")
        self._refresh()

    def _fill_forms(self) -> None:
        p = self.study.passport
        for key, edit in self.id_edits.items():
            edit.setText(getattr(p, key))
        for name, (value, provenance, source) in self.claim_edits.items():
            claim = p.claim(name)
            value.setText(claim.value or "")
            provenance.setCurrentIndex(max(0, provenance.findData(claim.provenance)))
            source.setText(claim.source)
        for key, (value, unit, uncertainty, provenance, method, source) in self.quantity_edits.items():
            q = getattr(p, key)
            value.setText("" if q.value is None else f"{q.value:g}")
            if q.unit:
                unit.setCurrentIndex(max(0, unit.findData(q.unit)))
            uncertainty.setText("" if q.uncertainty is None else f"{q.uncertainty:g}")
            provenance.setCurrentIndex(max(0, provenance.findData(q.provenance)))
            method.setText(q.method)
            source.setText(q.source)
        self.thickness_table.set_rows([(r.position, f"{r.thickness.value:g}", r.thickness.unit, r.thickness.provenance,
                                        r.method, r.thickness.source) for r in p.thickness])
        self.constant_table.set_rows([(c.name, "" if c.quantity.value is None else f"{c.quantity.value:g}",
                                       c.quantity.unit, c.role, c.quantity.provenance, c.quantity.source)
                                      for c in p.constants])
        facts = {f.key: f for f in self.study.evidence}
        self.fact_table.set_rows([(key, gev.fact_text(key, facts[key].value) if key in facts else "",
                                   facts[key].provenance if key in facts else "NOT_VERIFIED",
                                   facts[key].source if key in facts else "", gev.WHY[key]) for key in gev.FACT_KEYS])

    def apply_setup(self) -> bool:
        self.active = True
        try:
            claims = dict(self.study.passport.claims)
            for name, (value, provenance, source) in self.claim_edits.items():
                text = value.text().strip()
                claims[name] = wb.Claim(text or None, provenance.currentData() if text else wb.NOT_AVAILABLE,
                                        source.text().strip() if text else "")
            passport = replace(self.study.passport, claims=claims,
                               **{key: edit.text().strip() for key, edit in self.id_edits.items()})
        except wb.PassportError as error:
            self._say(f"Not applied: {error}")
            return False
        self.study = replace(self.study, passport=passport).logged("identifiers and set-up applied",
                                                                   passport.physical_specimen_id)
        self._say("Identifiers and set-up applied.")
        self._refresh()
        return True

    def _quantity(self, key: str, kind: str) -> wb.Quantity:
        value, unit, uncertainty, provenance, method, source = self.quantity_edits[key]
        number = _number(value.text())
        if number is None:
            return wb.not_available(kind)
        return wb.Quantity(kind, number, unit.currentData(), provenance.currentData(), source.text().strip(),
                           method.text().strip(), _number(uncertainty.text()))

    def apply_measurements(self) -> bool:
        self.active = True
        try:
            quantities = {key: self._quantity(key, kind) for key, _text, kind in QUANTITIES}
            thickness = tuple(wb.ThicknessReading(pos, wb.Quantity("length", _number(value), unit or "mm", prov,
                                                                    source), method)
                              for pos, value, unit, prov, method, source in self.thickness_table.rows() if pos or value)
            constants = []
            for name, value, unit, role, prov, source in self.constant_table.rows():
                if not name:
                    continue
                kind = "ratio" if unit in ("1", "") and name.lower().startswith("nu") else "modulus"
                constants.append(wb.Constant(name, wb.Quantity(kind, _number(value), unit or ("1" if kind == "ratio"
                                                                                              else "MPa"), prov, source),
                                             role))
        except (wb.PassportError, ValueError, TypeError) as error:
            self._say(f"Measurements not applied: {error}")
            return False
        passport = replace(self.study.passport, thickness=thickness, constants=tuple(constants), **quantities)
        self.study = replace(self.study, passport=passport).logged("measurements applied",
                                                                   f"{len(thickness)} thickness readings")
        self._say("Measurements applied.")
        self._refresh()
        return True

    def evaluate_evidence(self) -> bool:
        self.active = True
        try:
            facts = []
            for key, text, provenance, source, _why in self.fact_table.rows():
                value = gev.parse_fact_value(key, text)
                if value is not None:
                    facts.append(gev.EvidenceFact(key, value, provenance or "NOT_VERIFIED", source))
        except (ValueError, TypeError) as error:
            self._say(f"Evidence not evaluated: {error}")
            return False
        self.study = replace(self.study, evidence=tuple(facts), offline_result=None).logged(
            "evidence evaluated", f"{len(facts)} facts")
        self._say("Evidence evaluated (never a registration).")
        self._refresh()
        return True

    # ------------------------------------------------------------------------------------------ inputs and sources

    def set_inputs(self, fe_preview, fe_identity, experimental_preview, experimental_identity, set_index) -> None:
        self.inputs = (fe_preview, fe_identity, experimental_preview, experimental_identity, set_index)
        self.shapes[FE].set_preview(fe_preview)
        self.shapes[EXPERIMENTAL].set_preview(experimental_preview)
        self._refresh()

    def current_modal_set(self) -> Optional[dict]:
        return wb.modal_set_of(self.inputs[2], self.inputs[4])

    def current_sources(self) -> dict:
        return wb.source_status(self.study, self.inputs[3], self.inputs[1], self.current_modal_set())

    def link_inputs(self) -> bool:
        self.active = True
        if self.study.synthetic:
            self._say("A synthetic demonstration study takes synthetic inputs, never the Workspace files.")
            return False
        try:
            self.study = wb.link_sources(self.study, self.inputs[3], self.inputs[1], self.current_modal_set())
        except wb.StudyRefused as error:
            self._say(str(error))
            return False
        self._say("The Workspace inputs are linked to this study by SHA-256.")
        self._refresh()
        return True

    def verify_sources(self) -> dict:
        self.active = True
        out = {role: wb.verify_source(self.study, role) for role in ("experimental", "fe")}
        self.messages["verify"] = "\n".join(f"{role}: {state} — {detail}" for role, (state, detail) in out.items())
        self._refresh()
        return out

    def relocate(self, path: Optional[str] = None) -> bool:
        self.active = True
        role = self.relocate_role.currentData()
        path = path if path is not None else self._ask_file(f"Choose the moved {role} source")
        if not path:
            return False
        try:
            self.study = wb.relocate_source(self.study, role, path)
        except wb.StudyRefused as error:
            self._say(f"Not relocated: {error}")
            return False
        self._say(f"The {role} source was found at its new location with the recorded SHA-256.")
        self._refresh()
        return True

    def load_synthetic_inputs(self, path: Optional[str] = None) -> bool:
        self.active = True
        path = path if path is not None else self._ask_file("Choose the synthetic inputs (SYNTHETIC only)")
        if not path:
            return False
        try:
            self.study = wb.set_diagnostics(self.study, wb.load_synthetic_inputs(path, self.study))
        except wb.StudyRefused as error:
            self._say(f"Not loaded: {error}")
            return False
        self._say("Synthetic inputs loaded (" + wb.SYNTHETIC_LABEL + ").")
        self._refresh()
        return True

    def run_diagnostics(self) -> bool:
        self.active = True
        if self.study.synthetic:
            self._say("A synthetic study's diagnostics come from its synthetic inputs (step 2).")
            return False
        status = self.current_sources()
        if not status.get("consistent"):
            self._say("Link the Workspace inputs first: the files and the modal set read now are not the study's "
                      f"({', '.join(f'{k}: {v}' for k, v in status.items() if k != 'consistent')}).")
            return False
        try:
            diagnostics = wb.diagnostics_from_previews(self.inputs[2], self.inputs[4], self.inputs[0])
        except wb.StudyRefused as error:
            self._say(str(error))
            return False
        self.study = wb.set_diagnostics(self.study, diagnostics)
        self._say("Modal diagnostics computed (frequency proximity only).")
        self._refresh()
        return True

    # ------------------------------------------------------------------------------------------ offline study

    def load_sensitivities(self, path: Optional[str] = None) -> bool:
        self.active = True
        path = path if path is not None else self._ask_file("Choose the FE sensitivity table of this FE model")
        if not path:
            return False
        try:
            self.study = off.with_sensitivities(self.study, path)
        except off.OfflineRefused as error:
            self._say(f"Sensitivity table refused: {error}")
            return False
        self._say("Sensitivity table of this FE model imported.")
        self._refresh()
        return True

    def load_declaration(self, path: Optional[str] = None) -> bool:
        self.active = True
        path = path if path is not None else self._ask_file("Choose the declared observation set")
        if not path:
            return False
        try:
            self.study = off.with_declaration(self.study, path)
        except off.OfflineRefused as error:
            self._say(f"Declaration refused: {error}")
            return False
        self._say("Observation set declared (FIT / HOLDOUT fixed before any computation).")
        self._refresh()
        return True

    def offline_states(self) -> dict:
        return off.states(self.study, wb.evidence_result(self.study), self.current_sources())

    def run_offline(self) -> bool:
        self.active = True
        states = self.offline_states()
        if states["gate"]:
            self._say("The offline study cannot start: " + "; ".join(states["gate"]))
            return False
        try:
            result = off.run_offline_study(self.study, wb.evidence_result(self.study), states["sensitivities"],
                                           states["declaration"], self.current_sources())
        except off.OfflineRefused as error:
            self._say(f"Refused: {error}")
            return False
        self.study = replace(self.study, offline_result=result).logged(
            "offline research study", f"{result['status']}: " + " / ".join(result["labels"][:3]))
        self._say("Offline research study computed: DIAGNOSTIC_OPTIMIZER_CANDIDATE, not a material property.")
        self._refresh()
        return True

    # ------------------------------------------------------------------------------------------ files

    def save_study(self, path: Optional[str] = None) -> bool:
        self.active = True
        path = path if path is not None else self._ask_save()
        if not path:
            return False
        try:
            self.study = self.study.logged("saved", Path(path).name)
            wb.save_study(self.study, path, wb.evidence_result(self.study))
        except (OSError, ValueError) as error:
            self._say(f"Not saved: {error}")
            return False
        self.study_path = Path(path)
        self._say(f"Study saved: {path}")
        self._refresh()
        return True

    def open_study(self, path: Optional[str] = None) -> bool:
        self.active = True
        path = path if path is not None else self._ask_open()
        if not path:
            return False
        try:
            self.study = wb.open_study(path)
        except wb.StudyRefused as error:
            self._say(f"Not opened: {error}")
            return False
        self.study_path = Path(path)
        self.last_export = []
        self._fill_forms()
        self._say(f"Study opened: {path}. The registration status is recomputed from the evidence; verify the sources "
                  "by SHA-256 on step 2.")
        self._refresh()
        return True

    def export(self, folder: Optional[str] = None) -> bool:
        self.active = True
        folder = folder if folder is not None else self._ask_folder()
        if not folder:
            return False
        evidence = wb.evidence_result(self.study)
        try:
            self.last_export = wb.export_report(self.study, folder, evidence, self.readiness(evidence))
            self.study = self.study.logged("report exported", str(folder))
            self.messages["export"] = "Report written:\n" + "\n".join(str(p) for p in self.last_export)
        except (OSError, ValueError) as error:
            self.messages["export"] = f"The report was not written ({error})."
        self._refresh()
        return bool(self.last_export)

    def readiness(self, evidence=None) -> wb.Readiness:
        evidence = evidence or wb.evidence_result(self.study)
        states = off.states(self.study, evidence, self.current_sources())
        return wb.readiness(self.study, evidence, self.current_sources(), states["sensitivity_state"],
                            states["declaration_state"], states["rank_state"])

    # ------------------------------------------------------------------------------------------ display

    @staticmethod
    def _clear(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _table(self, layout, key, title, headers, rows, stretch, text_columns=()) -> None:
        layout.addWidget(_label(title, "sectionTitle"))
        if not rows:
            layout.addWidget(_label("None.", "hint"))
            return
        table = DiagnosticTable(headers, rows, stretch, (), text_columns)
        table.setObjectName(f"wb_{key}")
        self.tables[key] = table
        layout.addWidget(table)

    def step_states(self, evidence, ready, states, sources) -> list:
        p, s = self.study.passport, self.study
        return [
            DONE if p.physical_specimen_id and p.test_run_id else WAITING,
            DONE if (s.synthetic and s.diagnostics) or (not s.synthetic and sources.get("consistent")) else WAITING,
            DONE if next(c for c in ready.checks if c.name == "geometry and mass").state == wb.PASS else WAITING,
            "evidence complete — not frozen" if evidence.status == gev.COMPLETE else BLOCKED_TEXT,
            DONE if s.diagnostics else WAITING,
            ready.status if ready.status != wb.NOT_READY else "not ready",
            DONE if s.offline_result else (BLOCKED_TEXT if states["gate"] else "ready to run"),
            DONE if self.last_export or self.study_path else WAITING,
        ]

    def _refresh(self) -> None:
        self.synthetic_button.setEnabled(self.study.synthetic)
        self.run_button.setEnabled(False)
        if not self.active:  # before the first show: no evaluated text (as the other research pages)
            for label in (self.study_line, self.step_line, self.inputs_label, self.sources_label, self.derived_label,
                          self.evidence_label, self.readiness_status, self.gate_label, self.export_label,
                          self.history_label):
                label.setText("")
            return
        s = self.study
        evidence = wb.evidence_result(s)
        sources = self.current_sources()
        states = off.states(s, evidence, sources)
        ready = wb.readiness(s, evidence, sources, states["sensitivity_state"], states["declaration_state"],
                             states["rank_state"])
        kind = "synthetic demonstration study — " + wb.SYNTHETIC_LABEL if s.synthetic else "physical study"
        p = s.passport
        self.study_line.setText(f"Study: {kind} · specimen {p.physical_specimen_id or '—'} · design "
                                f"{p.design_id or '—'} · test run {p.test_run_id or '—'}"
                                + (f" · file {self.study_path}" if self.study_path else ""))
        self.step_line.setText(" · ".join(f"{step}: {state}" for step, state in
                                          zip(STEPS, self.step_states(evidence, ready, states, sources))))
        # step 2
        fe_id, exp_id, set_now = self.inputs[1], self.inputs[3], self.current_modal_set()
        self.inputs_label.setText(
            "Read now in the Workspace — FE: " + (f"{fe_id['sha256'][:12]}…" if fe_id else "not read") +
            " · experimental: " + (f"{exp_id['sha256'][:12]}…" if exp_id else "not read") +
            " · modal set: " + (f"{set_now['names'][0]} ({set_now['records']} records)" if set_now else "not chosen"))
        recorded = [f"{role}: {r.path} — SHA-256 {r.sha256[:12]}…" for role, r in s.sources.items()]
        self.sources_label.setText(("Linked: " + "; ".join(recorded) if recorded else "No source linked.") + "\n" +
                                   "Now: " + ", ".join(f"{k} {v}" for k, v in sources.items() if k != "consistent")
                                   + ("\n" + self.messages["verify"] if self.messages.get("verify") else ""))
        # step 3
        derived = wb.derived_quantities(p)
        t = wb.thickness_summary(p, s.kind)
        self.derived_label.setText("\n".join(
            [f"{d.name}: " + (f"{d.value:.6g} {d.unit}" if d.value is not None else wb.NOT_AVAILABLE)
             + f" ({d.provenance}; from {', '.join(d.basis)})" for d in derived] +
            [wb.thickness_readiness(p, s.kind)[1]] +
            ([f"observed thickness scatter {t['sd_mm']:.4f} mm (cv {100 * t['cv']:.2f} %): an observed spread, not an "
              "instrument uncertainty"] if t["sd_mm"] is not None else [])))
        # step 4
        lines = [f"{evidence.status} — scanner → plate: {evidence.scan_to_plate.status}; plate → FE: "
                 f"{evidence.plate_to_fe.status}. Frozen: no; MAC: not computed."]
        lines += [f"• {key}: {why}" for key, why in evidence.missing]
        lines += [f"✓ {c[0]}: {c[1]} — {c[2]}" for c in evidence.checks if c[1] == "CONSISTENT"]
        self.evidence_label.setText(("" if s.evidence else "No evidence entered yet. ") + "\n".join(lines))
        # step 5
        self._clear(self.diagnostics_body)
        for key in ("proximity", "fe", "groups"):
            self.tables.pop(key, None)
        diag = s.diagnostics
        if diag:
            if diag.get("source") == "SYNTHETIC":
                self.diagnostics_body.addWidget(_label(wb.SYNTHETIC_LABEL, "warnings"))
            rows = []
            for r in diag["proximity"]:
                n, second = r.get("nearest"), r.get("second")
                rows.append((f"EXP{r['exp']}", f"{r['f_exp_hz']:.4f}", f"FE{n[0]}" if n else "—",
                             f"{n[1]:.4f}" if n else "—", f"{n[2]:+.2f}" if n else "—",
                             f"FE{second[0]}" if second else "—", f"{second[2]:+.2f}" if second else "—",
                             "admissible record" if r["admissible_record"] else "not admissible (FRF peak / ambiguous)",
                             r["status"]))
            self._table(self.diagnostics_body, "proximity", "Every experimental record (EXP1 included)",
                        ("EXP", "f_EXP (Hz)", "Nearest FE", "f_FE (Hz)", "Δf (%)", "Second", "Δf (%)", "Record",
                         "Status"), rows, 8, text_columns=(0, 2, 5, 7, 8))
            self._table(self.diagnostics_body, "fe", "Every elastic FE mode (the first elastic included)",
                        ("FE mode", "f (Hz)"), [(f"FE{m['number']}", f"{m['hz']:.4f}") for m in diag["fe_elastic"]], 1,
                        text_columns=(0,))
            self.diagnostics_body.addWidget(_label(
                f"Rigid-body FE modes excluded by the code's shape criterion: {diag.get('fe_rigid_excluded') or 'none'}. "
                "Close groups (3 % trigger): " + ("; ".join("/".join(g) for g in diag["experimental_close_groups"]
                                                           + diag["fe_close_groups"]) or "none") +
                ". Pairs: none — " + diag["note"], "hint"))
        else:
            self.diagnostics_body.addWidget(_label("Not run.", "hint"))
        # step 6
        self.readiness_status.setText(f"{ready.status} · {ready.scientific_status}")
        self._clear(self.readiness_body)
        self.tables.pop("readiness", None)
        self._table(self.readiness_body, "readiness", "Conditions of an identification (kept apart)",
                    ("Condition", "State", "Detail"), [(c.name, c.state, c.detail) for c in ready.checks], 2,
                    text_columns=(0, 1, 2))
        if states["sensitivities"] is None:
            self.readiness_body.addWidget(_label("Plan of the FE sensitivities (nothing is run here):\n" + "\n".join(
                f"• {x}" for x in ready.sensitivity_plan), "hint"))
        for error in states["errors"]:
            self.readiness_body.addWidget(_label(error, "error"))
        # step 7
        self.run_button.setEnabled(not states["gate"])
        self.gate_label.setText("The offline study cannot start:\n" + "\n".join(f"• {r}" for r in states["gate"])
                                if states["gate"] else "All conditions are met: the offline research study may run.")
        self._clear(self.offline_body)
        self.tables.pop("offline", None)
        result = s.offline_result
        if result:
            self.offline_body.addWidget(_label(" / ".join(result["labels"]), "warnings"))
            self.offline_body.addWidget(_label(
                f"Status {result['status']} after {result['evaluations']} evaluations of the approximation. Candidate: "
                + "; ".join(f"{k} = {v['value']:.6g} {v['unit']} (×{v['ratio_to_baseline']:.4f} of the table's "
                            f"baseline)" for k, v in result["candidate"].items()), ""))
            self._table(self.offline_body, "offline", "Declared terms (FIT in the objective, HOLDOUT reported only)",
                        ("Term", "Role", "f_EXP (Hz)", "f_model (Hz)", "Residual (σ)"),
                        [(t["term"], t["role"], f"{t['f_exp_hz']:.4f}", f"{t['f_model_hz']:.4f}",
                          f"{t['residual']:+.3f}") for t in result["terms"]], 0, text_columns=(0, 1))
            derived = "; ".join(f"{k} {v:.6g}" if isinstance(v, float) else f"{k} {v}"
                                for k, v in result["derived"].items() if k != "basis")
            self.offline_body.addWidget(_label("\n".join(result["limits"]) + f"\nDerived (assumptions stated): {derived}"
                                               "\nApproved material values: NOT_AVAILABLE.", "hint"))
        # step 8
        self.export_label.setText(self.messages.get("export", ""))
        self.history_label.setText("History:\n" + "\n".join(" ".join(str(x) for x in h) for h in s.history[-12:]))

    def busy(self) -> bool:
        return any(panel.busy() for panel in self.shapes.values())

    def cancel(self) -> None:
        for panel in self.shapes.values():
            panel.cancel()


__all__ = ["GenericPlatePanel", "STEPS", "TITLE"]
