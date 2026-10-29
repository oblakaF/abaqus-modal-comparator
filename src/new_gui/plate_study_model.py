"""PLATE-ONLY-R1: the Single Plate — Effective Properties Study of the new interface, with no Qt (RESEARCH_ONLY).

The page works on the files read in the Workspace and the identities recorded when they were read (NEW-GUI.6-F1):

- the experimental file must be the plate's working source, recognised by its SHA-256 only
  (``services.plate_study.classify_source``); the M11 session and the auxiliary FRF file never replace it;
- the FE file must be a member of the plate's FE family (``PLATE_FE_FAMILY``) by the SHA-256 of its manifest: a
  CANDIDATE_FE_REFERENCE, never a confirmed model of this specimen.

On the explicit command Run plate study the service computes, with the project's existing services: the experimental
summary (every record), the frequency-only diagnostic (proximity only, never a pair), the archived registration check
(refused for this plate), the FE branch sensitivities over the four controlled variants (verified by SHA-256 under
the chosen family root), the hypothetical design studies, the readiness and every parameter's outcome. Nothing is
fitted and no material value is produced. The iterative estimation is behind ``plate_study.request_iteration``,
which refuses: the page has no working command for it.

The study shares the heavy-operation lock of NEW-GUI.4–6; a replaced or cleared file cancels it and discards its
outcome.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
import threading
from typing import Any, Optional

from new_gui import diagnostic_model as dm

TITLE = "Single Plate — Effective Properties Study"
RUN = "Run plate study"
EXPORT = "Export plate report..."
GATE = "Run iterative estimation (not authorised)"
NOT_RUN = "Not run"
RUNNING_TEXT = "Computing the plate study (no fit, no FE solve)..."
NOTE = ("Research only. One specimen: PLATE-300x300x1mm, series NEXP29/PLATE300-1MM/S261027-ROTATED. No sandwich and "
        "no other specimen's result is used or shown. Frequencies close to each other are not mode pairs; nothing is "
        "fitted and no material value is produced.")
GATE_NOTE = ("The iterative estimation is prepared but NOT AUTHORISED: it needs a separate, explicit owner "
             "authorisation naming the FE model, the parameters, the solve budget and the campaign definition. This "
             "page cannot start it.")
NEED_EXPERIMENT = ("Read the plate's working source on the Workspace page (File > Choose a known new experimental "
                   "source... > PLATE-300x300x1mm).")
NEED_FE = "Read an FE package of the plate's FE family on the Workspace page (for example the M11 S4R extraction)."
NEED_SET = "Choose the modal set on the Analysis page."
IDLE, RUNNING, DONE, FAILED = "idle", "running", "done", "failed"


def unavailable(fe_preview, fe_identity, experimental_preview, experimental_identity, set_index) -> tuple:
    """Why the study cannot run (empty when it can): the working source and a family member, by SHA-256."""
    from services import plate_study as ps

    reasons = []
    if experimental_preview is None:
        reasons.append(NEED_EXPERIMENT)
    elif experimental_identity is None:
        reasons.append("The experimental file's identity was not recorded when it was read; Inspect it again.")
    elif ps.classify_source(experimental_identity["sha256"]) != ps.WORKING:
        reasons.append(f"The experimental file is {ps.classify_source(experimental_identity['sha256'])}, not the "
                       f"working source of {ps.SERIES}. {NEED_EXPERIMENT}")
    if fe_preview is None:
        reasons.append(NEED_FE)
    elif fe_identity is None:
        reasons.append("The FE manifest's identity was not recorded when it was read; Inspect it again.")
    elif member_of(fe_identity) is None:
        reasons.append("The FE package is not a member of the plate's FE family (by the SHA-256 of its manifest). "
                       + NEED_FE)
    if experimental_preview is not None and set_index is None:
        reasons.append(NEED_SET)
    return tuple(reasons)


def member_of(fe_identity):
    from services import plate_study as ps

    if not fe_identity:
        return None
    return next((m for m in ps.PLATE_FE_FAMILY if m.manifest and m.manifest.sha256 == fe_identity["sha256"]), None)


@dataclass(frozen=True)
class PlateStudyView:
    status: str
    member: str
    experimental_rows: tuple
    geometry: tuple
    frequency_rows: tuple
    registration: str
    family_rows: tuple
    sensitivity_rows: tuple
    cluster_rows: tuple
    design_rows: tuple
    outcome_rows: tuple
    missing: tuple
    identity: tuple
    limits: tuple
    plan: tuple
    record: Any = None  # the JSON-ready record of the study (the report states it)


@dataclass(frozen=True)
class PlateOutcome:
    token: int
    view: Any = None
    error: str = ""
    cancelled: bool = False


def _f(value, digits=4):
    return "—" if value is None else f"{value:.{digits}f}"


def compute(fe_preview, fe_identity, experimental_preview, experimental_identity, set_index: int,
            family_root: Optional[Path] = None, cancel_event: Optional[threading.Event] = None) -> PlateStudyView:
    """The plate study on the read data; raises ``PlateStudyRefusal`` for data that are not the plate's."""
    from new_gui import preview_model as pm
    from new_gui import workspace_state as ws
    from services import plate_study as ps
    from services.new_odb_comparison import (AcceptedReferenceRefusal, bind_registration_by_fe_geometry,
                                             frequency_only_diagnostic)

    ps.require_working_source(experimental_identity["sha256"])
    member = member_of(fe_identity)
    if member is None:
        raise ps.PlateStudyRefusal("the FE package is not a member of the plate's FE family.")
    root = Path(family_root) if family_root is not None else ps.WORK_ROOT
    dataset = experimental_preview.sets[set_index].dataset
    summary = ps.experimental_summary(dataset, experimental_identity["sha256"])
    diagnostic = frequency_only_diagnostic(fe_preview.dataset, dataset, (
        "PLATE-ONLY-R1: no physical registration between the plate FE model and the ROTATED scan"))
    try:
        bind_registration_by_fe_geometry(Path(experimental_preview.source_path), fe_preview.dataset, dataset,
                                         cancel=cancel_event)
        registration = "an archived registration was verified (unexpected for this plate); not used here"
    except AcceptedReferenceRefusal as refusal:
        registration = f"{ps.NOT_VERIFIED}: {refusal}"
    family_rows, datasets = [], {}
    for item in ps.PLATE_FE_FAMILY:
        checks = ps.verify_member(item, root)
        family_rows.append((item.member_id, item.description, item.status, item.changed or "—",
                            ", ".join(f"{c.role} {c.state}" for c in checks)))
        if item.variant_of and all(c.state == "VERIFIED" for c in checks) and item.manifest is not None:
            if cancel_event is not None and cancel_event.is_set():
                raise ps.PlateStudyRefusal("cancelled")
            path = root.joinpath(*Path(item.manifest.relative).parts)
            datasets[item.member_id] = (pm.read_preview(ws.FE, path, cancel_event).dataset, item.changed,
                                        item.parameters[item.changed] / ps.PLATE_FE_FAMILY[0].parameters[item.changed])
    sensitivity_rows, cluster_rows, design_rows, d_sens = [], [], [], {}
    if member.member_id == "S4R_0875_BASELINE" and datasets:
        table = ps.sensitivity_table(fe_preview.dataset, datasets)
        for row in table.rows:
            sensitivity_rows.append((row.row_id, _f(row.baseline_hz, 3), *[_f(row.sensitivity.get(p)) for p in
                                                                          ("E1", "E2", "G12")],
                                     "+".join(row.cluster) if row.cluster else "—",
                                     "; ".join(f"{k}: {v[3][:40]}" for k, v in row.tracked.items()
                                               if v is not None and v[3] not in ("TRACKED", "TRACKED_CLUSTER"))
                                     or "tracked in every variant"))
        cluster_rows = tuple((" / ".join(ids), status, "; ".join(reasons)) for ids, status, reasons in table.clusters)
        d_sens = ps.d_sensitivities(table, member.parameters)
        rows = list(d_sens)
        sens = {r: {**d_sens[r], "D": d_sens[r]["D11"] + d_sens[r]["D22"]} for r in rows}
        h = ps.thickness_column(rows, d_sens, ("D11", "D22", "D66"))
        for label, params, selected, source in (
                ("all tracked terms: D (D11 = D22) and D66", ("D", "D66"), rows, sens),
                ("all tracked terms: D11, D22, D66 (research; SPEC §5.2 blocks E1 ≠ E2)", ("D11", "D22", "D66"),
                 rows, sens),
                ("FE 7 only: D and D66", ("D", "D66"), [r for r in rows if r == "FE7"], sens),
                ("all tracked terms with thickness h at measured mass", ("D11", "D22", "D66", "h"), rows,
                 {r: {**d_sens[r], "h": h[r]} for r in rows})):
            if not selected:
                continue
            study = ps.design_study(source, selected, params, label)
            design_rows.append((label, ", ".join(study.parameters), str(len(study.rows)), study.status,
                                "—" if study.sd_ln is None else ", ".join(f"{100 * v:.2f} %" for v in study.sd_ln),
                                "; ".join(study.refusal_reasons) or "—"))
    readiness = ps.plate_readiness(registration_verified=False)
    record = {
        "schema": "plate-only-r1/study/v1", "created": datetime.now().isoformat(timespec="seconds"),
        "labels": [ps.RESEARCH_ONLY, ps.CANDIDATE_FE_REFERENCE, ps.FREQUENCY_ONLY], "specimen": ps.SPECIMEN,
        "series": ps.SERIES, "plate_identity": ps.PLATE_IDENTITY, "experimental_source": experimental_identity,
        "fe_member": member.member_id, "fe_manifest": fe_identity, "registration": registration,
        "experiment": [r.__dict__ for r in summary.records], "frequency_only": diagnostic.to_dict(),
        "fe_family": [dict(zip(("member", "description", "status", "changed", "files"), r)) for r in family_rows],
        "sensitivity_basis": ps.SECANT, "d_sensitivity": d_sens,
        "design_studies": [dict(zip(("label", "parameters", "terms", "status", "sd_ln", "refusal"), r))
                           for r in design_rows],
        "readiness": readiness.status, "missing": list(readiness.missing),
        "outcomes": [{"parameter": o.parameter, "outcome": o.outcome, "reasons": list(o.reasons)}
                     for o in readiness.outcomes],
        "iteration_gate": ps.ITERATION_GATE.status, "plan": list(ps.ITERATION_PLAN), "limits": list(ps.FE_LIMITS)}
    rows_by_number = {row.experimental_mode: row for row in diagnostic.rows}
    return PlateStudyView(
        status=f"{ps.FREQUENCY_ONLY} / {readiness.status}", member=f"{member.member_id} ({member.status})",
        experimental_rows=tuple((str(r.position), str(r.mode), _f(r.frequency_hz), _f(r.mpc, 3),
                                 r.measured_components, str(r.points), _f(r.rigid_plane_fraction, 3),
                                 _f(r.saddle_fraction, 3), _f(r.dome_fraction, 3), r.classification)
                                for r in summary.records),
        geometry=(("Points", str(summary.point_count)),
                  ("Span (m)", " × ".join(f"{v:.4f}" for v in summary.span_m[:2])),
                  ("Grid spacing (m)", f"{summary.grid_spacing_m:.4f}"),
                  ("Grid axis angle in the camera frame (°)", f"{summary.grid_axis_angle_deg:.2f}"),
                  ("Scan distance (m)", f"{summary.scan_distance_m:.3f}"),
                  ("Close groups (3 % trigger)", "; ".join(" / ".join(g) for g in summary.close_groups) or "none"),
                  ("Damping", summary.damping_note)),
        frequency_rows=tuple((str(r.mode), _f(r.frequency_hz),
                              str(rows_by_number[r.mode].nearest_fe_mode) if rows_by_number.get(r.mode) else "—",
                              _f(rows_by_number[r.mode].nearest_fe_hz) if rows_by_number.get(r.mode) else "—",
                              _f(rows_by_number[r.mode].nearest_difference_percent, 2)
                              if rows_by_number.get(r.mode) else "—", dm.NOT_COMPUTED, "NOT a mode pair")
                             for r in summary.records),
        registration=registration, family_rows=tuple(family_rows), sensitivity_rows=tuple(sensitivity_rows),
        cluster_rows=cluster_rows, design_rows=tuple(design_rows),
        outcome_rows=tuple((o.parameter, o.outcome, "; ".join(o.reasons[:2]) + (" …" if len(o.reasons) > 2 else ""))
                           for o in readiness.outcomes),
        missing=readiness.missing, identity=tuple((a, b, c) for a, b, c in ps.IDENTITY_EVIDENCE),
        limits=tuple(ps.FE_LIMITS) + tuple(summary.limits), plan=tuple(ps.ITERATION_PLAN), record=record)


def run_study(fe_preview, fe_identity, experimental_preview, experimental_identity, set_index: int, token: int,
              cancel_event: threading.Event, family_root: Optional[Path] = None) -> PlateOutcome:
    """``compute`` as an outcome under the shared heavy-operation lock (worker thread)."""
    try:
        with dm._SERVICE:
            if cancel_event.is_set():
                return PlateOutcome(token, cancelled=True)
            view = compute(fe_preview, fe_identity, experimental_preview, experimental_identity, set_index,
                           family_root, cancel_event)
    except Exception as error:  # noqa: BLE001  (refusals, unreadable family files, anything unexpected)
        if cancel_event.is_set():
            return PlateOutcome(token, cancelled=True)
        return PlateOutcome(token, error=f"The plate study was not computed ({type(error).__name__}: {error}).")
    if cancel_event.is_set():
        return PlateOutcome(token, cancelled=True)
    return PlateOutcome(token, view=view)


def export_report(view: PlateStudyView, folder) -> tuple:
    """Write the study's JSON record and a Markdown summary into ``folder`` (time-stamped; atomic; no replacement)."""
    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError(f"{folder} is not an existing folder.")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    lines = [f"# {TITLE}", "", f"Status: **{view.status}** — RESEARCH_ONLY; no material value.", "",
             f"FE member: {view.member}", "", f"Registration: {view.registration}", "", "## Experimental records", "",
             "| Record | Mode | Hz | MPC | Saddle | Dome |", "|---|---|---|---|---|---|"]
    lines += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[7]} | {r[8]} |" for r in view.experimental_rows]
    lines += ["", "## Parameter outcomes", "", "| Parameter | Outcome | Reason |", "|---|---|---|"]
    lines += [f"| {a} | {b} | {c} |" for a, b, c in view.outcome_rows]
    lines += ["", "## Missing", ""] + [f"- {m}" for m in view.missing] + ["", "## Plan", ""] + list(view.plan)
    written = []
    for suffix, text in ((".json", json.dumps(view.record, indent=2, ensure_ascii=False, default=str)),
                         (".md", "\n".join(lines) + "\n")):
        target = folder / f"plate_study_{stamp}{suffix}"
        index = 2
        while target.exists():
            target = folder / f"plate_study_{stamp}_{index}{suffix}"
            index += 1
        handle, temporary = tempfile.mkstemp(prefix=".~report_", suffix=suffix, dir=folder)
        os.close(handle)
        try:
            Path(temporary).write_text(text, encoding="utf-8")
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
        written.append(target)
    return tuple(written)


class PlateSlot:
    def __init__(self) -> None:
        self.token = 0
        self.state = IDLE
        self.outcome: Optional[PlateOutcome] = None
        self.cancel_event: Optional[threading.Event] = None

    def start(self) -> tuple[int, threading.Event]:
        self.reset()
        self.state = RUNNING
        self.cancel_event = threading.Event()
        return self.token, self.cancel_event

    def reset(self) -> None:
        if self.cancel_event is not None:
            self.cancel_event.set()
        self.token += 1
        self.state, self.outcome, self.cancel_event = IDLE, None, None

    def finish(self, outcome: PlateOutcome) -> bool:
        if self.state != RUNNING or outcome.token != self.token:
            return False
        self.cancel_event = None
        if outcome.cancelled:
            self.state = IDLE
        else:
            self.state, self.outcome = (DONE if outcome.view is not None else FAILED), outcome
        return True


__all__ = ["PlateOutcome", "PlateSlot", "PlateStudyView", "compute", "export_report", "member_of", "run_study",
           "unavailable"]
