"""SP-02 strict-pairing re-evaluation: LEGACY centred registration vs PHYSICAL registration (M6 gate), and the
combined SP-02 + SP-13 observation picture (diagnostic; no M7 fitting).

Zero Abaqus. Read: the archived CARBON-4C SP-02 baseline record, the validated M4 SP-02 BASELINE shape pack,
the accepted SP-02 experimental fixture, both frozen SP-02 registrations (hashes pinned before this runs), the
accepted CARBON-5A ±5 % E / G12 frequency and FE-to-FE branch-tracking tables (SP-02 has no ±5 % shape
packs), and the SP-13 re-evaluation record. The STRICT policy, the M4.3 classifier and holdout rule and the
M4.4 cluster trigger are unchanged. Nothing here selects, adjusts or compares-to-choose a registration.

    python tools/sp02_registration_reevaluation.py --write
"""

from __future__ import annotations

import argparse
import copy
import csv
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
from services.fe_shape_pack import load_shape_pack, load_shape_pack_record  # noqa: E402
from services.identification_clusters import TriggerRow, cluster_triggers  # noqa: E402
from services.modal_family_classifier import ClassifiedRow, classify_shape_pack_modes, select_holdouts  # noqa: E402
from services.physical_registration import build_physical_registration  # noqa: E402

BASELINE = ROOT / "docs/auto_id/baselines/SP02.carbon4c-baseline.json"
LEGACY = ROOT / "docs/registrations/SP02_frozen_registration.json"
PHYSICAL = ROOT / "docs/registrations/SP02_physical_registration.json"
PASSPORT = ROOT / "docs/auto_id/specimens/SP02.physical.specimen.json"
RECORD = ROOT / "docs/auto_id/registration_evidence/SP02_physical_registration_reconstruction.json"
SP13_REEVALUATION = ROOT / "docs/auto_id/registration_evidence/SP13_registration_reevaluation.json"
OUT = ROOT / "docs/auto_id/registration_evidence/SP02_registration_reevaluation.json"
PACK = "SP02_f3e592281bebce66"
CARBON5A_STORE = "carbon-project-archive"
CARBON5A_FREQUENCIES = "carbon5a/frequencies.csv"
CARBON5A_TRACKING = "carbon5a/branch_tracking.csv"
STATES = {"E_in_plane_mpa+": "E_PLUS", "E_in_plane_mpa-": "E_MINUS", "G12_mpa+": "G_PLUS", "G12_mpa-": "G_MINUS"}
STEP = math.log(1.05) - math.log(0.95)
SIGMA_PROVISIONAL = 0.003  # SPEC §7 provisional Σ_setup (diagnostic conditioning only; not an M5 verdict)
FLOAT32_REL = 1.0e-6  # CARBON-5A stores single-precision frequencies


def carbon5a_sensitivities(roots, baseline) -> dict:
    """S_E, S_G12 per baseline FE mode from the accepted CARBON-5A ±5 % runs, only where the FE-to-FE branch
    tracking resolved the same branch in all four states; the baseline must be the CARBON-4C FE job."""
    root = roots[CARBON5A_STORE]
    fe_hz = {m.number: m.frequency_hz for m in baseline.fe_modes}
    hz, tracking = {}, {}
    with open(root / CARBON5A_FREQUENCIES, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["specimen"] == "SP02":
                hz[(row["state"], int(row["fe_mode"]))] = float(row["hz"])
    with open(root / CARBON5A_TRACKING, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["specimen"] == "SP02":
                tracking[(row["state"], int(row["baseline_fe_mode"]))] = row
    out = {}
    for mode, f0 in fe_hz.items():
        base = hz.get(("BASELINE", mode))
        if base is None or abs(base - f0) > FLOAT32_REL * f0 * 10:
            continue
        rows = [tracking.get((state, mode)) for state in STATES.values()]
        if any(r is None or r["resolved"] != "True" for r in rows):
            out[mode] = {"status": "NOT_RESOLVED"}
            continue
        f = {name: hz[(state, int(tracking[(state, mode)]["tracked_fe_mode"]))] for name, state in STATES.items()}
        out[mode] = {"status": "RESOLVED",
                     "tracked": {name: int(tracking[(state, mode)]["tracked_fe_mode"]) for name, state in STATES.items()},
                     "min_tracked_mac_u3": min(float(r["mac_u3_tracked"]) for r in rows),
                     "S_E": (math.log(f["E_in_plane_mpa+"]) - math.log(f["E_in_plane_mpa-"])) / STEP,
                     "S_G12": (math.log(f["G12_mpa+"]) - math.log(f["G12_mpa-"])) / STEP}
    return out


def conditioning(rows: list[tuple[str, float, float]]) -> dict | None:
    if len(rows) < 2:
        return None if not rows else {"rows": [r[0] for r in rows], "rank": 1, "local_sd_ln_E_with_G12_fixed":
                                      SIGMA_PROVISIONAL / abs(rows[0][1])}
    S = np.array([[e, g] for _, e, g in rows])
    sv = np.linalg.svd(S / SIGMA_PROVISIONAL, compute_uv=False)
    angles = []
    for a in range(len(rows)):
        for b in range(a + 1, len(rows)):
            c = S[a] @ S[b] / np.linalg.norm(S[a]) / np.linalg.norm(S[b])
            angles.append(math.degrees(math.acos(min(1.0, abs(c)))))
    out = {"rows": [r[0] for r in rows], "rank": int(np.linalg.matrix_rank(S, tol=1e-3 * sv[0] * SIGMA_PROVISIONAL)),
           "condition_number": float(sv[0] / sv[-1]), "max_row_angle_deg": max(angles),
           "column_cosine_E_G12": float(S[:, 0] @ S[:, 1] / np.linalg.norm(S[:, 0]) / np.linalg.norm(S[:, 1]))}
    out["local_sd_ln_E_with_G12_fixed"] = float(SIGMA_PROVISIONAL / np.linalg.norm(S[:, 0]))
    if sv[-1] > 0:
        J = S / SIGMA_PROVISIONAL
        cov = np.linalg.inv(J.T @ J)
        out.update({"local_sd_ln_E": float(math.sqrt(cov[0, 0])), "local_sd_ln_G12": float(math.sqrt(cov[1, 1]))})
    out["note"] = "diagnostic only: sigma = SPEC provisional 0.3 %, carbon-only (no nuisance); not an M5 verdict"
    return out


def evaluate(label, evidence, families, sensitivities):
    frozen = freeze_baseline(evidence, STRICT)
    rows = frozen.rows if frozen.frozen else frozen.provisional_rows
    matrix = evidence.mac_matrix()
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
    out["sensitivities_carbon5a"] = {r.row_id: sensitivities.get(r.fe_mode, {"status": "NOT_AVAILABLE"}) for r in rows}
    if len(rows) < 2:
        out["observation_sufficient"] = False
        return out
    holdouts = select_holdouts([ClassifiedRow(r.row_id, r.experimental_hz, families[r.fe_mode]) for r in rows], False)
    out["holdouts"] = {"holdout_row_ids": list(holdouts.holdout_row_ids), "fit_row_ids": list(holdouts.fit_row_ids),
                       "torsion_family": holdouts.torsion_family, "validation_family": holdouts.validation_family,
                       "notes": list(holdouts.notes)}
    triggers = cluster_triggers([TriggerRow(r.row_id, r.experimental_hz, r.fe_hz) for r in rows])
    out["cluster_triggers"] = [{"row_ids": list(t.row_ids), "status": "NOT_CONFIRMABLE",
                                "reasons": ["no SP-02 ±5 % shape packs (M4.4 confirmation needs perturbed shapes)"]}
                               for t in triggers]
    by_id = {r.row_id: r for r in rows}
    fit = [(k, sensitivities[by_id[k].fe_mode]) for k in holdouts.fit_row_ids
           if sensitivities.get(by_id[k].fe_mode, {}).get("status") == "RESOLVED"]
    out["conditioning_fit_rows"] = conditioning([(k, s["S_E"], s["S_G12"]) for k, s in fit])
    out["observation_sufficient"] = bool(len(holdouts.fit_row_ids) >= 2 and out["conditioning_fit_rows"]
                                         and not out["cluster_triggers"])
    return out


def legacy_vs_physical_geometry(legacy: FrozenRegistration, physical: FrozenRegistration, modes) -> dict:
    """Where each registration puts every scan point on the FE surface (FE frame, mm). Geometry only."""
    coords = np.asarray(modes[0].coordinates, dtype=float)

    def in_fe(reg):
        return ((coords - np.asarray(reg.translation)) / np.asarray(reg.coordinate_scales)) @ np.asarray(reg.rotation).T

    d = np.linalg.norm((in_fe(legacy) - in_fe(physical))[:, :2], axis=1)
    return {"point_count": int(len(d)), "median_mm": float(np.median(d)), "p95_mm": float(np.percentile(d, 95)),
            "max_mm": float(d.max()),
            "legacy_scales": list(map(float, legacy.coordinate_scales)),
            "physical_scales": list(map(float, physical.coordinate_scales)),
            "same_mapped_fe_nodes": int(sum(a == b for a, b in zip(legacy.mapped_fe_node_ids,
                                                                   physical.mapped_fe_node_ids)))}


def combined(sp02: dict, sp13: dict) -> dict:
    """Stack the strict rows of both specimens (diagnostic). Holdouts stay per frozen set (M4.3 unchanged)."""
    def rows(name, result, sens_of):
        holdout = set((result.get("holdouts") or {}).get("holdout_row_ids", []))
        out = []
        for r in result["strict_pairs"]:
            s = sens_of(r)
            out.append({"specimen": name, "row_id": r["row_id"], "experimental_mode": r["experimental_mode"],
                        "fe_mode": r["fe_mode"], "mac": r["mac"], "family": r["family"],
                        "torsion_dominated": r["torsion_dominated"], "held_out": r["row_id"] in holdout,
                        "S_E": None if s is None else s[0], "S_G12": None if s is None else s[1]})
        return out

    p13 = sp13["results"]["PHYSICAL"]
    p02 = sp02["results"]["PHYSICAL"]
    all_rows = (rows("SP-13", p13, lambda r: (p13["sensitivities"][r["row_id"]]["S_E"],
                                              p13["sensitivities"][r["row_id"]]["S_G12"])
                     if r["row_id"] in p13.get("sensitivities", {}) else None)
                + rows("SP-02", p02, lambda r: (p02["sensitivities_carbon5a"][r["row_id"]]["S_E"],
                                                p02["sensitivities_carbon5a"][r["row_id"]]["S_G12"])
                       if p02["sensitivities_carbon5a"].get(r["row_id"], {}).get("status") == "RESOLVED" else None))
    usable = [r for r in all_rows if r["S_E"] is not None]
    fit = [r for r in usable if not r["held_out"]]

    def leave_one_family_out(key):
        out = {}
        for family in sorted({key(r) for r in fit}):
            kept = [r for r in fit if key(r) != family]
            c = conditioning([(f'{r["specimen"]}:{r["row_id"]}', r["S_E"], r["S_G12"]) for r in kept])
            out[f"without {family}"] = ({"rows": [], "rank": 0} if c is None else
                           {k: c[k] for k in ("rows", "rank", "condition_number", "max_row_angle_deg",
                                              "local_sd_ln_E_with_G12_fixed") if k in c})
        return out

    return {
        "rows": all_rows,
        "strict_rows_before_holdout": len(all_rows),
        "fit_rows_after_per_specimen_holdout": len([r for r in all_rows if not r["held_out"]]),
        "families_before_holdout": sorted({f'{r["specimen"]}:{r["family"]}' for r in all_rows}),
        "families_after_holdout": sorted({f'{r["specimen"]}:{r["family"]}' for r in all_rows if not r["held_out"]}),
        "conditioning_all_strict_rows": conditioning([(f'{r["specimen"]}:{r["row_id"]}', r["S_E"], r["S_G12"])
                                                      for r in usable]),
        "conditioning_fit_rows": conditioning([(f'{r["specimen"]}:{r["row_id"]}', r["S_E"], r["S_G12"])
                                               for r in fit]),
        "leave_one_family_out_fit_rows": {
            "by_specimen_family": leave_one_family_out(lambda r: f'{r["specimen"]}:{r["family"]}'),
            "by_family_pooled_over_specimens": leave_one_family_out(lambda r: r["family"])},
        "note": ("diagnostic stacking of strict rows; a joint SP-02 + SP-13 estimate is not an M4/M5 contract "
                 "(each specimen is frozen and held out separately) and is not an M7 fit"),
    }


def compute(include_alternative: bool = True) -> dict:
    roots = fixture_roots_from_environment()
    baseline = load_archived_baseline(BASELINE)
    forward = load_forward_model_manifest(ROOT / baseline.forward_model_path)
    legacy_passport = load_specimen_manifest(ROOT / forward.specimen_passport.path)
    chain = qc.prepare_auto_id_experimental_input(baseline.fixture_id, roots=roots, specimen_passport=legacy_passport)
    modes = chain.dataset.sorted_modes()
    legacy = FrozenRegistration.from_dict(json.loads(LEGACY.read_text(encoding="utf-8")))
    physical = FrozenRegistration.from_dict(json.loads(PHYSICAL.read_text(encoding="utf-8")))
    geometry = legacy_vs_physical_geometry(legacy, physical, modes)  # geometry first, before any MAC
    pack = load_shape_pack(load_shape_pack_record(ROOT / "docs/auto_id/fe_shapes" / f"{PACK}.shape-pack.json"), roots)
    families = classify_shape_pack_modes(pack)
    sensitivities = carbon5a_sensitivities(roots, baseline)
    results = {
        "LEGACY": evaluate("LEGACY centred registration (historical provenance)",
                           shape_pack_evidence(baseline, pack, legacy, modes, forward.forward_model_id,
                                               chain.eligibility), families, sensitivities),
        "PHYSICAL": evaluate("PHYSICAL registration (nominal, frozen before evaluation)",
                             reregistered_shape_pack_evidence(baseline, pack, physical, modes,
                                                              forward.forward_model_id, chain.eligibility),
                             families, sensitivities),
    }
    if include_alternative:
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
            reregistered_shape_pack_evidence(baseline, pack, alternative, modes, forward.forward_model_id,
                                             chain.eligibility), families, sensitivities)
        results["BOTTOM_FACE_ALTERNATIVES"] = (
            "not evaluable: the validated pack holds the TOP measured surface only; a bottom-face extraction "
            "would need Abaqus Python (not authorised)")
    document = {"schema": "auto-id/sp02-registration-reevaluation/v1", "policy_id": STRICT.policy_id,
                "policy_hash": STRICT.policy_hash, "pack": PACK, "baseline_record_sha256": baseline.record_sha256,
                "physical_registration_file": "docs/registrations/SP02_physical_registration.json",
                "legacy_registration_file": "docs/registrations/SP02_frozen_registration.json",
                "sensitivity_source": {"store": CARBON5A_STORE, "frequencies": CARBON5A_FREQUENCIES,
                                       "branch_tracking": CARBON5A_TRACKING,
                                       "rule": "S = (ln f+ - ln f-) / (ln 1.05 - ln 0.95) on the FE-to-FE tracked "
                                               "branch; only rows resolved in all four states"},
                "legacy_vs_physical_geometry": geometry, "abaqus_solves": 0, "abaqus_python_extractions": 0,
                "results": results}
    document["combined_sp02_sp13"] = combined(document, json.loads(SP13_REEVALUATION.read_text(encoding="utf-8")))
    return document


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    document = compute()
    print("geometry", json.dumps(document["legacy_vs_physical_geometry"]))
    for k, v in document["results"].items():
        if isinstance(v, dict):
            print(k, v["status"], [(r["experimental_mode"], r["fe_mode"], round(r["mac"], 4),
                                    round(r["relative_frequency_error"], 4)) for r in v["strict_pairs"]],
                  "| fit:", (v.get("holdouts") or {}).get("fit_row_ids"), "| sufficient:", v.get("observation_sufficient"))
    print(json.dumps({k: v for k, v in document["combined_sp02_sp13"].items() if k != "rows"}, indent=1))
    if args.write:
        OUT.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        print("wrote", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
