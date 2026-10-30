"""PLATE-ONLY-R1: the Single Plate — Effective Properties Study page (PySide6; RESEARCH_ONLY).

It uses the files read in the Workspace and their recorded identities. Run plate study is enabled only for the
plate's working source and a member of the plate's FE family (by SHA-256); otherwise the reasons are shown. The result
shows the experimental records, the frequency-only table (never pairs), the registration result, the FE family, the
FE branch sensitivities, the hypothetical design studies, every parameter's outcome, the missing data and the plan.
FE and experimental shapes are viewed independently (unpaired). The iterative estimation button is always disabled:
it is not authorised. Export plate report... writes the study's JSON and Markdown into a folder the user chooses.
No material value of any specimen is shown on this page.

PLATE-ONLY-R2: the result also shows the specimen identity (HUMAN_CONFIRMED by the owner on 2026-10-30, with its
provenance and limits), the archived record of this specimen (M11 measurements of 2026-10-21, never measurements of
27.10), the applicability of the initial FE model to the 261027 test (NOT_VERIFIED), the orientation chain (nothing
chosen) and the uncertainty budget with the archived record.

PLATE-WORKBENCH-RC1 final correction: the test conditions of both series (owner, 2026-10-30; laboratory note;
instrument) and the link of the two scans, from the services.
"""

from __future__ import annotations

from pathlib import Path
import threading
from typing import Callable, Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QBoxLayout, QFileDialog, QFrame, QLabel, QPushButton, QSizePolicy, QVBoxLayout,
                               QWidget)

from new_gui import plate_study_model as psm
from new_gui.diagnostic_panel import DiagnosticTable
from new_gui.shape_panel import ImageView, ShapePanel
from new_gui.workspace_state import EXPERIMENTAL, FE


def _label(text: str = "", name: str = "", wrap: bool = True) -> QLabel:
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    label.setWordWrap(wrap)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    if wrap:
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        label.setMinimumWidth(0)
    return label


def _restyle(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class _Bridge(QObject):
    done = Signal(object)


class PlateStudyPanel(QWidget):
    """The page's content."""

    changed = Signal()

    def __init__(self, ask_folder: Optional[Callable[[], str]] = None, family_root: Optional[Path] = None):
        super().__init__()
        self.inputs = (None, None, None, None, None)  # FE preview, FE identity, exp preview, exp identity, set index
        self.family_root = family_root
        self.slot = psm.PlateSlot()
        self.discarded = 0
        self.export_message = ""
        self._ask_folder = ask_folder or self._dialog_folder
        self._threads: list[threading.Thread] = []
        self._bridge = _Bridge(self)
        self._bridge.done.connect(self._done)
        self.tables: dict[str, DiagnosticTable] = {}
        self.spectrum: Optional[ImageView] = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        card = QFrame()
        card.setObjectName("card")
        inner = QVBoxLayout(card)
        inner.setContentsMargins(16, 14, 16, 14)
        inner.setSpacing(8)
        inner.addWidget(_label(psm.TITLE, "cardTitle"))
        self.badge = _label(psm.NOT_RUN, "badge", wrap=False)
        inner.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignLeft)
        self.mode_line = _label("", "")  # the comparison mode, on its own wrapping line (a badge never wraps)
        inner.addWidget(self.mode_line)
        inner.addWidget(_label(psm.NOTE, "hint"))
        self.why = _label("", "hint")
        inner.addWidget(self.why)
        self.buttons = QBoxLayout(QBoxLayout.Direction.TopToBottom)
        self.run_button = QPushButton(psm.RUN)
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self.run)
        self.export_button = QPushButton(psm.EXPORT)
        self.export_button.clicked.connect(lambda: self.export())
        self.gate_button = QPushButton(psm.GATE)
        self.gate_button.setObjectName("iterationGate")
        self.gate_button.setEnabled(False)  # never enabled in PLATE-ONLY-R1
        self.gate_button.setToolTip(psm.GATE_NOTE)
        for button in (self.run_button, self.export_button, self.gate_button):
            self.buttons.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
        inner.addLayout(self.buttons)
        inner.addWidget(_label(psm.GATE_NOTE, "warnings"))
        self.status = _label("", "hint")
        inner.addWidget(self.status)
        self.export_status = _label("", "hint")
        inner.addWidget(self.export_status)
        layout.addWidget(card)
        shapes = QFrame()
        shapes.setObjectName("card")
        shapes_layout = QVBoxLayout(shapes)
        shapes_layout.setContentsMargins(16, 14, 16, 14)
        shapes_layout.addWidget(_label("Shapes — independent, UNPAIRED views (no registration, no MAC)", "cardTitle"))
        self.shapes = {FE: ShapePanel(FE), EXPERIMENTAL: ShapePanel(EXPERIMENTAL)}
        for kind in (FE, EXPERIMENTAL):
            shapes_layout.addWidget(self.shapes[kind])
        layout.addWidget(shapes)
        self.result_card = QFrame()
        self.result_card.setObjectName("card")
        self.result_layout = QVBoxLayout(self.result_card)
        self.result_layout.setContentsMargins(16, 14, 16, 14)
        self.result_layout.setSpacing(8)
        layout.addWidget(self.result_card)
        self._refresh()

    # ------------------------------------------------------------------------------------------ inputs and running

    def set_inputs(self, fe_preview, fe_identity, experimental_preview, experimental_identity, set_index) -> None:
        self.shapes[FE].set_preview(fe_preview)
        self.shapes[EXPERIMENTAL].set_preview(experimental_preview)
        inputs = (fe_preview, fe_identity, experimental_preview, experimental_identity, set_index)
        # PLATE-ONLY-R1-F1: a preview is compared by object, never by value: Inspect file again (even of the same
        # path) gives a new preview, and the earlier result and its export status are removed
        same = (fe_preview is self.inputs[0] and experimental_preview is self.inputs[2]
                and fe_identity == self.inputs[1] and experimental_identity == self.inputs[3]
                and set_index == self.inputs[4])
        if same:
            return
        self.inputs = inputs
        self.slot.reset()
        self.export_message = ""
        self._refresh()

    def unavailable(self) -> tuple:
        return psm.unavailable(*self.inputs)

    def run(self) -> bool:
        if self.unavailable() or self.slot.state == psm.RUNNING:
            return False
        token, cancel_event = self.slot.start()
        worker = threading.Thread(target=self._work, args=(*self.inputs, token, cancel_event), daemon=True,
                                  name="new-gui-plate-study")
        self._threads = [t for t in self._threads if t.is_alive()] + [worker]
        worker.start()
        self._refresh()
        return True

    def _work(self, fe, fe_id, exp, exp_id, set_index, token, cancel_event) -> None:
        outcome = psm.run_study(fe, fe_id, exp, exp_id, set_index, token, cancel_event, self.family_root)
        try:
            self._bridge.done.emit(outcome)
        except RuntimeError:
            pass

    def _done(self, outcome) -> None:
        if not self.slot.finish(outcome):
            self.discarded += 1
            return
        self._refresh()

    def busy(self) -> bool:
        return (self.slot.state == psm.RUNNING or any(t.is_alive() for t in self._threads)
                or any(panel.busy() for panel in self.shapes.values()))

    def cancel(self) -> None:
        for panel in self.shapes.values():
            panel.cancel()
        self.slot.reset()
        self._refresh()

    @property
    def view(self) -> Optional[psm.PlateStudyView]:
        outcome = self.slot.outcome
        return outcome.view if self.slot.state == psm.DONE and outcome is not None else None

    def _dialog_folder(self) -> str:
        from services.report_directory import default_report_directory

        return QFileDialog.getExistingDirectory(self, "Choose the folder for the plate report",
                                                str(default_report_directory()))

    def export(self, folder: Optional[str] = None) -> bool:
        view = self.view
        if view is None:
            return False
        folder = folder if folder is not None else self._ask_folder()
        if not folder:
            return False
        try:
            written = psm.export_report(view, folder)  # confirms the files read before writing
            self.export_message = "Plate study report written:\n" + "\n".join(str(p) for p in written)
        except (OSError, ValueError) as error:  # ExportRefused is a ValueError: nothing was written
            self.export_message = f"The report was not written ({error})."
        self._refresh()
        return True

    # ------------------------------------------------------------------------------------------ display

    def _clear(self) -> None:
        while self.result_layout.count():
            widget = self.result_layout.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.tables = {}
        self.spectrum = None  # PLATE-WORKBENCH-RC1: the spectra image of the shown result

    def _table(self, key, title, headers, rows, stretch, text_columns=(), capped=()) -> None:
        self.result_layout.addWidget(_label(title, "sectionTitle"))
        if not rows:
            self.result_layout.addWidget(_label("None.", "hint"))
            return
        table = DiagnosticTable(headers, rows, stretch, capped, text_columns)
        self.tables[key] = table
        self.result_layout.addWidget(table)

    def _refresh(self) -> None:
        reasons = self.unavailable()
        state = self.slot.state
        self.run_button.setEnabled(not reasons and state != psm.RUNNING)
        self.why.setText("\n".join(reasons))
        self.why.setVisible(bool(reasons))
        view = self.view
        self.export_button.setEnabled(view is not None)
        readiness = view.status.split(" / ")[-1] if view is not None else None
        self.badge.setText(readiness if view is not None else ("Computing..." if state == psm.RUNNING
                                                               else psm.NOT_RUN))
        self.mode_line.setText(f"Comparison: {view.status.split(' / ')[0]} — no registration, no MAC, no mode pair"
                               if view is not None else "")
        self.mode_line.setVisible(view is not None)
        self.badge.setProperty("state", "chosen" if view is not None else "empty")
        _restyle(self.badge)
        outcome = self.slot.outcome
        self.status.setText(psm.RUNNING_TEXT if state == psm.RUNNING else
                            (outcome.error if state == psm.FAILED and outcome is not None else ""))
        self.status.setVisible(state in (psm.RUNNING, psm.FAILED))
        self.export_status.setText(self.export_message)
        self.export_status.setVisible(bool(self.export_message))
        self._clear()
        self.result_card.setVisible(view is not None)
        if view is not None:
            from services import plate_study as ps

            self.result_layout.addWidget(_label(f"FE package: {view.member}", ""))
            self.result_layout.addWidget(_label(f"Registration: {view.registration}", "warnings"))
            self._table("chain", "Workbench chain: Source UNV → Physical specimen → Test conditions and scan "
                        "orientation → FE model → Registration → Mode pairs → Parameter estimation",
                        ("Link", "Status", "Confirmation", "Source", "Missing and blocking", "Diagnostics available"),
                        view.chain_rows, 4, (0, 1, 2, 3, 4, 5), capped=(0, 1, 2, 3, 5))
            self._table("conditions", "Test conditions: 261016 (HISTORY_ONLY, four rubber bands) and 261027 (the "
                        "primary experiment, two rubber bands, turned 45°)",
                        ("Series", "Item", "Value", "Provenance", "Source / status"), view.conditions_rows, 2,
                        (0, 1, 2, 3, 4), capped=(1, 3, 4))
            self.result_layout.addWidget(_label(ps.CONDITIONS_CORRECTION + "\nNot established by the conditions:\n"
                                                + "\n".join(f"• {item}" for item in
                                                            ps.NOT_ESTABLISHED_BY_THE_CONDITIONS), "warnings"))
            self._table("identity", f"Specimen identity: {view.record.get('plate_identity')} (owner, 2026-10-30; "
                        "physical identity only)", ("Evidence", "Content", "Weight"), view.identity, 1, (0, 1, 2))
            self._table("specimen", "Archived record of this specimen (M11 measurements, 2026-10-21) — NOT "
                        "measurements of 27.10", ("Quantity", "Value", "Recorded", "Method", "Uncertainty", "Status"),
                        view.specimen_rows, 4, (0, 1, 2, 3, 4, 5), capped=(1, 2, 3, 5))
            self.result_layout.addWidget(_label(view.record.get("specimen_record_note", ""), "hint"))
            self._table("thickness", "Thickness: edge readings only — the real uncertainty of E / G is UNKNOWN",
                        ("Item", "Value", "Status"), view.thickness_rows, 1, (0, 1, 2), capped=(0, 2))
            self._table("experiment", "MEASURED experimental records (every record; descriptive invariants)",
                        ("Record", "Mode", "Measured Hz", "MPC", "Measured DOF", "Points", "Rigid plane", "Saddle",
                         "Dome", "Classification", "Saddle on grid axes (uv)", "Saddle on grid diagonals (u²−v²)"),
                        view.experimental_rows, 9, (4, 9))
            self._table("geometry", "Scan geometry", ("Item", "Value"), view.geometry, 1)
            self._table("frequency", "Measured frequencies against the INITIAL FE model's frequencies (M11, same "
                        "specimen) — the nearest FE frequency is NOT a mode pair (frequency only)",
                        ("Exp mode", "Measured Hz", "Nearest initial FE mode", "Initial FE Hz",
                         "Difference (%)", "MAC", "Note"), view.frequency_rows, 6, (5, 6))
            self.result_layout.addWidget(_label("Measured and FE spectra (frequency only, NOT mode pairs)",
                                                "sectionTitle"))
            self.spectrum = ImageView()
            self.spectrum.setObjectName("plateSpectrum")
            self.spectrum.set_image(view.spectrum_png)
            self.result_layout.addWidget(self.spectrum)
            self._table("applicability", f"Applicability of the initial FE model to the 261027 test: "
                        f"{ps.APPLICABILITY_NOT_VERIFIED}", ("Aspect", "State", "FE model", "Specimen / test", "Note"),
                        view.applicability_rows, 4, (0, 1, 2, 3, 4), capped=(1, 2, 3))  # long states elide
            self._table("orientation", "Orientation chain — nothing is chosen by MAC, frequency or shape",
                        ("Link", "State", "Known", "Open"), view.orientation_rows, 3, (0, 1, 2, 3), capped=(0, 2))
            self.result_layout.addWidget(_label("\n".join(f"• {line}" for line in ps.ORIENTATION_NOTES), "hint"))
            self._table("series", "Link of the scans 261016 → 261027 — instrument geometry only (no mode, frequency "
                        "or MAC)", ("Item", "Value", "State"), view.series_rows, 1, (0, 1, 2), capped=(0, 2))
            self._table("registration", f"Physical registration readiness: {view.registration_status} (no "
                        "orientation from MAC, frequency or shape; nothing frozen)",
                        ("Link", "Fact", "Value", "Provenance", "Source"), view.registration_rows, 4,
                        (0, 1, 2, 3, 4), capped=(0, 2))
            self.result_layout.addWidget(_label("Missing or refused for a physical registration:\n" + "\n".join(
                f"• {key}: {reason}" for key, reason in view.registration_missing), "warnings"))
            closing = view.record.get("registration_readiness", {}).get("closing_evidence", ())
            self.result_layout.addWidget(_label("What would close them (from the existing records):\n" + "\n".join(
                f"• {item['facts']}: {item['evidence']}" for item in closing), "hint"))
            self._table("instrument", "Instrument records found in the delivered files",
                        ("Item", "Content", "Provenance"), view.instrument_rows, 1, (0, 1, 2))
            self._table("family", "FE family of the specimen (INITIAL FE model and variants; SHA-256 verified)",
                        ("Member", "Description", "Status", "Changed", "Files"), view.family_rows, 4, (0, 1, 2, 4))
            self._table("sensitivity", "Sensitivities of the INITIAL FE model's branches s = Δ ln f / Δ ln p "
                        "(secants; FE-to-FE tracking)",
                        ("Branch", "Initial FE Hz", "s E1", "s E2", "s G12", "Cluster", "Tracking"),
                        view.sensitivity_rows, 6, (0, 5, 6))
            self._table("clusters", "Close FE pairs (3 % trigger; confirm_cluster)", ("Pair", "Status", "Reason"),
                        view.cluster_rows, 2, (0, 1, 2))
            self._table("design", "HYPOTHETICAL distinguishability of parameters (design study, M5) — conditional, "
                        "not the real accuracy",
                        ("Case", "Parameters", "Terms", "Rank status", "Conditional sd (ln), provisional Σ_setup",
                         "Refusal"), view.design_rows, 5, (0, 1, 3, 5))
            self.result_layout.addWidget(_label(psm.CONDITIONAL_NOTE, "warnings"))
            self._table("outcomes", "Parameter outcomes now", ("Parameter", "Outcome", "Reason"), view.outcome_rows,
                        2, (0, 1, 2))
            self._table("target", "The ±10 % goal, part by part — no part is a material accuracy",
                        ("Part", "Value", "Status", "Note"), view.target_rows, 3, (0, 1, 2, 3), capped=(0,))
            self._table("campaign", "Prepared FE campaign — NOT authorised, nothing run (jobs per phase)",
                        ("Phase", "Jobs", "Prerequisite", "Content"), view.campaign_rows, 3, (0, 2, 3), capped=(0, 2))
            self.result_layout.addWidget(_label("\n".join(f"• {line}" for line in view.campaign_lines), "hint"))
            self._table("budget", "Uncertainty budget of ln E / ln G12 with the archived record (no estimate exists)",
                        ("Source", "Established ln sd", "Illustrative", "Note"), view.budget_rows, 3, (0, 2, 3),
                        capped=(0,))
            self.result_layout.addWidget(_label("Missing for an identification:\n" + "\n".join(
                f"• {line}" for line in view.missing), "warnings"))
            self.result_layout.addWidget(_label("Plan before a first authorised iterative campaign:\n" + "\n".join(
                view.plan), "hint"))
            self.result_layout.addWidget(_label("Limits:\n" + "\n".join(f"• {line}" for line in view.limits),
                                                "hint"))
        self.changed.emit()


__all__ = ["PlateStudyPanel"]
