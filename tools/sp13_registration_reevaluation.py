"""SP-13 strict-pairing re-evaluation: LEGACY centred registration vs PHYSICAL registration (M6 gate).

Zero Abaqus: only the archived CARBON-4C baseline record, the validated M4 FE shape packs (baseline and
±5 % E / G12) and the accepted experimental fixture are read. Both registrations are frozen files whose
hashes are pinned before this runs; this tool never selects, adjusts or compares-to-choose a registration.
The STRICT policy, the M4.3 classifier, the M4.4 cluster rule and the experimental / FE modes are unchanged.

    python tools/sp13_registration_reevaluation.py --write
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.experiment_fixture import fixture_roots_from_environment  # noqa: E402
from domain.forward_model_manifest import load_forward_model_manifest  # noqa: E402
from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING as STRICT  # noqa: E402
from domain.registration import FrozenRegistration  # noqa: E402
from domain.specimen_manifest import load_specimen_manifest, parse_specimen_manifest  # noqa: E402
from services import experimental_qc as qc  # noqa: E402
from services.archived_baseline import (  # noqa: E402
    load_archived_baseline,
    reregistered_shape_pack_evidence,
    shape_pack_evidence,
)
from services.baseline_freeze import freeze_baseline  # noqa: E402
from services.branch_tracker import BranchTrackingRefusal, FEModalState, track_branches  # noqa: E402
from services.fe_shape_pack import load_shape_pack, load_shape_pack_record  # noqa: E402
from services.identification_clusters import (  # noqa: E402
    CARBON_V1_DIRECTIONS,
    TriggerRow,
    cluster_triggers,
    confirm_cluster,
)
from services.modal_family_classifier import ClassifiedRow, classify_shape_pack_modes, select_holdouts  # noqa: E402
from services.physical_registration import build_physical_registration  # noqa: E402

BASELINE = ROOT / "docs/auto_id/baselines/SP13.carbon4c-baseline.json"
LEGACY = ROOT / "docs/registrations/SP13_frozen_registration.json"
PHYSICAL = ROOT / "docs/registrations/SP13_physical_registration.json"
PASSPORT = ROOT / "docs/auto_id/specimens/SP13.physical.specimen.json"
RECORD = ROOT / "docs/auto_id/registration_evidence/SP13_physical_registration_reconstruction.json"
OUT = ROOT / "docs/auto_id/registration_evidence/SP13_registration_reevaluation.json"
PACKS = {"BASELINE": "SP13_a46d08b52995e078", "E_in_plane_mpa+": "SP13_0e861d03c333bb0b",
         "E_in_plane_mpa-": "SP13_a9df66283a168786", "G12_mpa+": "SP13_4c0f189b9727feaf",
         "G12_mpa-": "SP13_0328066b74b6fd78"}
STEP = math.log(1.05) - math.log(0.95)
SIGMA_PROVISIONAL = 0.003  # SPEC §7 provisional Σ_setup (diagnostic conditioning only; not an M5 verdict)


def state(pack, name):
    shapes = np.asarray(pack.displacements, dtype=float)[:, :, 2]  # U3 on the measured surface
    return FEModalState(name, pack.record.fe_geometry_sha256, pack.record.node_set_sha256, tuple(pack.mode_numbers),
                        tuple(pack.frequencies_hz), shapes)


def evaluate(label, evidence, packs, families):
    frozen = freeze_baseline(evidence, STRICT)
    rows = frozen.rows if frozen.frozen else frozen.provisional_rows
    matrix = evidence.mac_matrix()
    fe_hz = {m.number: m.frequency_hz for m in evidence.fe_modes}
    best = []
    for i, mode in enumerate(evidence.experimental_modes):
        j = int(np.argmax(matrix[i]))
        fe = evidence.fe_modes[j]
        best.append({"experimental_mode": mode.number, "experimental_hz": mode.frequency_hz,
                     "best_fe_mode": fe.number, "best_mac": float(matrix[i, j]),
                     "relative_frequency_error": (fe.frequency_hz - mode.frequency_hz) / mode.frequency_hz})
    out = {"label": label, "registration_hash": evidence.identity.registration_hash,
           "status": frozen.status.value, "reasons": list(frozen.reasons),
           "strict_pairs": [{"row_id": r.row_id, "experimental_mode": r.experimental_mode,
                             "experimental_hz": r.experimental_hz, "fe_mode": r.fe_mode, "fe_hz": r.fe_hz,
                             "mac": r.mac, "relative_frequency_error": r.relative_frequency_error,
                             "family": families[r.fe_mode].key,
                             "torsion_dominated": families[r.fe_mode].torsion_dominated} for r in rows],
           "best_match_per_experimental_mode": best,
           "excluded": [{"experimental_mode": e.experimental_mode, "reason": e.reason} for e in frozen.excluded]}
    if len(rows) < 2:
        out["observation_sufficient"] = False
        return out
    holdouts = select_holdouts([ClassifiedRow(r.row_id, r.experimental_hz, families[r.fe_mode]) for r in rows], False)
    out["holdouts"] = {"holdout_row_ids": list(holdouts.holdout_row_ids), "fit_row_ids": list(holdouts.fit_row_ids),
                       "torsion_family": holdouts.torsion_family, "validation_family": holdouts.validation_family,
                       "notes": list(holdouts.notes)}
    triggers = cluster_triggers([TriggerRow(r.row_id, r.experimental_hz, r.fe_hz) for r in rows])
    base = state(packs["BASELINE"], "BASELINE")
    by_row = {r.row_id: r for r in rows}
    clusters = []
    for trigger in triggers:
        baseline_shapes = np.array([base.shapes[base.index(by_row[k].fe_mode)] for k in trigger.row_ids])
        perturbed = {d: state(packs[d], d).shapes for d in CARBON_V1_DIRECTIONS}
        confirmation = confirm_cluster(trigger.row_ids, baseline_shapes, perturbed)
        clusters.append({"row_ids": list(trigger.row_ids), "status": confirmation.status.value,
                         "reasons": list(confirmation.reasons)})
    out["cluster_triggers"] = clusters
    # branch-tracked ±5 % sensitivities (FE-to-FE identity only)
    sens, refusals = {}, []
    rows_map = {r.row_id: r.fe_mode for r in rows}
    tracked = {}
    for d in CARBON_V1_DIRECTIONS:
        try:
            result = track_branches(STRICT, base, state(packs[d], d), rows_map)
            tracked[d] = {b.row_id: b.candidate_hz for b in result.branches}
        except BranchTrackingRefusal as refusal:
            refusals.append(f"{d}: {refusal}")
    if not refusals:
        for r in rows:
            sens[r.row_id] = {
                "S_E": (math.log(tracked["E_in_plane_mpa+"][r.row_id]) - math.log(tracked["E_in_plane_mpa-"][r.row_id])) / STEP,
                "S_G12": (math.log(tracked["G12_mpa+"][r.row_id]) - math.log(tracked["G12_mpa-"][r.row_id])) / STEP}
    out["sensitivities"] = sens
    out["tracking_refusals"] = refusals
    fit = list(holdouts.fit_row_ids)
    if sens and len(fit) >= 2:
        S = np.array([[sens[k]["S_E"], sens[k]["S_G12"]] for k in fit])
        J = S / SIGMA_PROVISIONAL
        sv = np.linalg.svd(J, compute_uv=False)
        cov = np.linalg.inv(J.T @ J)
        rows_angle = []
        for a in range(len(fit)):
            for b in range(a + 1, len(fit)):
                c = S[a] @ S[b] / np.linalg.norm(S[a]) / np.linalg.norm(S[b])
                rows_angle.append(math.degrees(math.acos(min(1.0, abs(c)))))
        col_cos = float(S[:, 0] @ S[:, 1] / np.linalg.norm(S[:, 0]) / np.linalg.norm(S[:, 1]))
        out["conditioning_fit_rows"] = {
            "fit_rows": fit, "condition_number": float(sv[0] / sv[-1]), "rcond_ratio": float(sv[-1] / sv[0]),
            "max_row_angle_deg": max(rows_angle), "column_cosine_E_G12": col_cos,
            "local_sd_ln_E": float(math.sqrt(cov[0, 0])), "local_sd_ln_G12": float(math.sqrt(cov[1, 1])),
            "note": "diagnostic only: sigma = SPEC provisional 0.3 %, carbon-only (no nuisance); not an M5 verdict"}
    out["observation_sufficient"] = bool(sens and len(fit) >= 2 and "conditioning_fit_rows" in out)
    return out


def compute(include_alternative: bool = True) -> dict:
    roots = fixture_roots_from_environment()
    baseline = load_archived_baseline(BASELINE)
    forward = load_forward_model_manifest(ROOT / baseline.forward_model_path)
    legacy_passport = load_specimen_manifest(ROOT / forward.specimen_passport.path)
    chain = qc.prepare_auto_id_experimental_input(baseline.fixture_id, roots=roots, specimen_passport=legacy_passport)
    modes = chain.dataset.sorted_modes()
    legacy = FrozenRegistration.from_dict(json.loads(LEGACY.read_text(encoding="utf-8")))
    physical = FrozenRegistration.from_dict(json.loads(PHYSICAL.read_text(encoding="utf-8")))
    packs = {k: load_shape_pack(load_shape_pack_record(ROOT / "docs/auto_id/fe_shapes" / f"{v}.shape-pack.json"), roots)
             for k, v in PACKS.items()}
    families = classify_shape_pack_modes(packs["BASELINE"])
    results = {
        "LEGACY": evaluate("LEGACY centred registration (historical provenance)",
                           shape_pack_evidence(baseline, packs["BASELINE"], legacy, modes, forward.forward_model_id,
                                               chain.eligibility), packs, families),
        "PHYSICAL": evaluate("PHYSICAL registration (nominal, frozen before evaluation)",
                             reregistered_shape_pack_evidence(baseline, packs["BASELINE"], physical, modes,
                                                              forward.forward_model_id, chain.eligibility),
                             packs, families),
    }
    if include_alternative:
        # The 180-degree TOP-face sign alternative (physically indistinguishable) is REPORTED, never selected.
        raw = json.loads(PASSPORT.read_text(encoding="utf-8"))
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        alt_name = "+x->-X, +y->-Y (TOP face, det +1, 180 deg)"
        variant = copy.deepcopy(raw)
        variant["geometry_calibration"]["orientation"]["experimental_axes_in_fe"] = ["-X", "-Y", "+Z"]
        variant["geometry_calibration"]["panel_edges"] = {
            k: round(v, 4) for k, v in record["fe_sign_alternatives"][alt_name].items()}
        alternative = build_physical_registration(parse_specimen_manifest(variant)).registration
        results["PHYSICAL_ALTERNATIVE_180"] = evaluate(
            f"reported alternative {alt_name} (not selected)",
            reregistered_shape_pack_evidence(baseline, packs["BASELINE"], alternative, modes,
                                             forward.forward_model_id, chain.eligibility), packs, families)
        results["BOTTOM_FACE_ALTERNATIVES"] = (
            "not evaluable: the validated packs hold the TOP measured surface only; a bottom-face extraction "
            "would need Abaqus Python (not authorised)")
    return {"schema": "auto-id/sp13-registration-reevaluation/v1", "policy_id": STRICT.policy_id,
            "policy_hash": STRICT.policy_hash, "packs": PACKS, "baseline_record_sha256": baseline.record_sha256,
            "physical_registration_file": "docs/registrations/SP13_physical_registration.json",
            "legacy_registration_file": "docs/registrations/SP13_frozen_registration.json",
            "abaqus_solves": 0, "abaqus_python_extractions": 0, "results": results}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    document = compute()
    for k, v in document["results"].items():
        if isinstance(v, dict):
            print(k, v["status"], [(r["experimental_mode"], r["fe_mode"], round(r["mac"], 4)) for r in v["strict_pairs"]],
                  "| fit:", (v.get("holdouts") or {}).get("fit_row_ids"), "| sufficient:", v.get("observation_sufficient"))
    if args.write:
        OUT.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        print("wrote", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
