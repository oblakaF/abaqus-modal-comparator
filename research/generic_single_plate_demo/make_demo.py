"""PRIORITY-8: the SYNTHETIC demonstration of the single-plate workbench — another plate than M11 (no Abaqus, no data).

It writes, into ``docs/examples/generic_single_plate_demo``, a study of a synthetic plate DEMO-SPB-420x260 (420 × 260 ×
2.2 mm, own identifiers, own FE model id), its synthetic inputs (12 experimental records, 10 elastic FE modes, a scan
grid), a synthetic FE sensitivity table of its own FE model and a declared observation set with a SYNTHETIC registration
decision. Everything is labelled SYNTHETIC_DEMONSTRATION — NOT A PHYSICAL EXPERIMENT; the experimental frequencies are
the log-linear approximation at a declared truth with a fixed small perturbation, so the offline study has a known
answer. A second declaration (DEMO_DECLARATION_TWO_ROWS.json) shows a scientific refusal (rank deficiency).

Usage: python research/generic_single_plate_demo/make_demo.py
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "docs" / "examples" / "generic_single_plate_demo"
SPECIMEN = "DEMO-SPB-420x260"
FE_MODEL = "DEMO-SPB-FE v1 (S4R, free-free, synthetic)"
FE_ID = hashlib.sha256(FE_MODEL.encode("utf-8")).hexdigest()  # a synthetic identity: no FE package exists
BASELINE = {"E_in_plane": 50000.0, "G12": 4500.0}
TRUTH = {"E_in_plane": 52000.0, "G12": 4300.0}  # declared before the run: the demo's known answer
FE = [  # (mode, f0 Hz, s_E, s_G): synthetic branches of a free-free plate (s_E + s_G ≈ 0.5)
    (7, 34.20, 0.08, 0.42), (8, 52.60, 0.45, 0.05), (9, 71.10, 0.31, 0.19), (10, 88.40, 0.43, 0.07),
    (11, 96.80, 0.14, 0.36), (12, 121.30, 0.39, 0.11), (13, 139.70, 0.26, 0.24), (14, 162.20, 0.45, 0.05),
    (15, 186.50, 0.22, 0.28), (16, 192.10, 0.33, 0.17)]
PERTURBATION = [0.0004, -0.0003, 0.0002, -0.0005, 0.0003, 0.0001, -0.0002, 0.0004, -0.0001, 0.0002]
SYNTH = "SYNTHETIC"
SOURCE = "PRIORITY-8 synthetic demonstration (research/generic_single_plate_demo/make_demo.py)"


def q(kind, value, unit, uncertainty=None, method="synthetic"):
    return {"kind": kind, "value": value, "unit": unit, "provenance": SYNTH, "source": SOURCE, "method": method,
            "uncertainty": uncertainty, "uncertainty_basis": "synthetic declared resolution" if uncertainty else "",
            "note": ""}


def predict(f0, s_e, s_g, p):
    return f0 * math.exp(s_e * math.log(p["E_in_plane"] / BASELINE["E_in_plane"])
                         + s_g * math.log(p["G12"] / BASELINE["G12"]))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    thickness = [2.18, 2.21, 2.20, 2.23, 2.19, 2.22, 2.20, 2.21, 2.17]
    positions = [f"{row}{col}" for row in ("top", "middle", "bottom") for col in ("-left", "-centre", "-right")]
    passport = {
        "design_id": "DEMO-DESIGN-SPB", "physical_specimen_id": SPECIMEN, "test_run_id": "DEMO-RUN-001",
        "measurement_date": "2026-11-01 (synthetic)", "measurement_method": "synthetic declared values",
        "length": q("length", 420.0, "mm", 0.5), "width": q("length", 260.0, "mm", 0.5),
        "mass": q("mass", 372.4, "g", 0.05), "density": {"kind": "density", "value": None, "unit": "",
                                                       "provenance": "NOT_AVAILABLE", "source": "", "method": "",
                                                       "uncertainty": None, "uncertainty_basis": "", "note": ""},
        "thickness": [{"position": pos, "method": "synthetic micrometer", "thickness": q("length", t, "mm")}
                      for pos, t in zip(positions, thickness)],
        "claims": {name: {"value": value, "provenance": SYNTH, "source": SOURCE} for name, value in (
            ("material_orientation", "warp along the 420 mm edges 1/3"), ("layup", "8 plies plain weave, synthetic"),
            ("suspension", "free-free on two soft elastic cords"), ("measured_face", "marked"),
            ("instrument_axes", "scan +u towards edge 2, +v towards edge 1"), ("measured_dofs", "Z"),
            ("fe_model_version", FE_MODEL), ("excitation", "synthetic"))},
        "constants": [{"name": "nu12", "role": "FIXED", "quantity": q("ratio", 0.05, "1")},
                      {"name": "E_in_plane", "role": "INITIAL", "quantity": q("modulus", 50000.0, "MPa")},
                      {"name": "G12", "role": "INITIAL", "quantity": q("modulus", 4500.0, "MPa")}],
    }
    facts = [("scanned_face", "marked"), ("grid_plus_u_edge", 2), ("grid_plus_v_edge", 1),
             ("scan_window_offsets_mm", {"-u": 10.0, "+u": 10.0, "-v": 10.0, "+v": 10.0}),
             ("scan_scale", {"mm_per_unit": 1000.0}), ("scan_metric_geometry", True), ("measured_dof", "Z"),
             ("fe_x_along_edges", "1/3"), ("fe_origin_corner", [3, 4]), ("fe_normal_face", "marked")]
    study = {"schema": "amc/generic-single-plate-study/v1", "kind": "SYNTHETIC_DEMO", "created": "2026-11-01T00:00:00Z",
             "labels": ["RESEARCH_ONLY", "NOT_A_MATERIAL_PROPERTY", "SYNTHETIC_DEMONSTRATION — NOT A PHYSICAL EXPERIMENT"],
             "passport": passport,
             "sources": {"fe": {"role": "fe", "path": "SYNTHETIC: no FE package (" + FE_MODEL + ")", "sha256": FE_ID,
                                "size": None}},
             "modal_set": None,
             "evidence": [{"key": k, "value": v, "provenance": SYNTH, "source": SOURCE, "derived_from": []}
                          for k, v in facts],
             "history": [["2026-11-01T00:00:00Z", "created", "SYNTHETIC_DEMO by make_demo.py"]]}
    points = [[(-0.2 + 0.05 * i), (-0.12 + 0.04 * j), 0.0] for j in range(7) for i in range(9)]  # 400 × 240 mm
    experimental = []
    for k, ((mode, f0, s_e, s_g), dev) in enumerate(zip(FE, PERTURBATION), start=1):
        experimental.append({"number": k, "hz": round(predict(f0, s_e, s_g, TRUTH) * (1 + dev), 4)})
    experimental += [{"number": 11, "hz": 214.6}, {"number": 12, "hz": 219.9}]  # two records with no FE row
    inputs = {"schema": "amc/synthetic-plate-inputs/v1", "kind": SYNTH, "specimen": {"physical_specimen_id": SPECIMEN},
              "note": "SYNTHETIC_DEMONSTRATION — NOT A PHYSICAL EXPERIMENT",
              "experimental": experimental, "fe_elastic": [{"number": m, "hz": f0} for m, f0, _e, _g in FE],
              "fe_rigid": [1, 2, 3, 4, 5, 6], "scan_points_m": points, "fe_extent_mm": [420.0, 260.0]}
    sensitivities = {"schema": "amc/fe-sensitivity-table/v1", "kind": SYNTH,
                     "fe_model": {"name": FE_MODEL, "manifest_sha256": FE_ID},
                     "specimen": {"physical_specimen_id": SPECIMEN, "design_id": "DEMO-DESIGN-SPB"},
                     "parameters": {p: {"baseline": v, "unit": "MPa"} for p, v in BASELINE.items()},
                     "method": "SYNTHETIC central ±5 % sensitivities (declared; no Abaqus solve)",
                     "provenance": SOURCE, "solved_range_relative": [0.95, 1.05],
                     "rows": [{"fe_mode": m, "f_baseline_hz": f0, "tracked": True,
                               "s": {"E_in_plane": s_e, "G12": s_g}} for m, f0, s_e, s_g in FE]}
    decision = {"status": "ADMISSIBLE_FOR_RESEARCH_COMPUTATION", "provenance": SYNTH,
                "reference": "SYNTHETIC-DECISION-DEMO-001 (declared for the demonstration only)",
                "decided_by": "synthetic", "date": "2026-11-01"}
    roles = {1: "FIT", 2: "FIT", 3: "FIT", 4: "HOLDOUT", 5: "FIT", 6: "FIT", 7: "HOLDOUT", 8: "HOLDOUT"}
    declaration = {"schema": "amc/declared-observations/v1", "kind": SYNTH,
                   "specimen": {"physical_specimen_id": SPECIMEN}, "registration_decision": decision,
                   "parameters": ["E_in_plane", "G12"], "start": dict(BASELINE),
                   "bounds": {"E_in_plane": [25000.0, 100000.0], "G12": [2250.0, 9000.0]},
                   "sigma_ln": {"value": 0.003, "provenance": "Σ_setup 0.3 % PROVISIONAL (synthetic scale)"},
                   "holdout_declared": True,
                   "observations": [{"exp": e, "fe": [FE[e - 1][0]], "role": r,
                                     "basis": "SYNTHETIC declared pair (the demo's construction)"}
                                    for e, r in roles.items()]}
    two = dict(declaration, observations=[  # FE8 and FE14 have nearly the same s: rank deficient for E and G12
        {"exp": 2, "fe": [8], "role": "FIT", "basis": "SYNTHETIC declared pair"},
        {"exp": 8, "fe": [14], "role": "FIT", "basis": "SYNTHETIC declared pair"}], holdout_declared=False)
    for name, data in (("DEMO_STUDY.json", study), ("DEMO_SYNTHETIC_INPUTS.json", inputs),
                       ("DEMO_SENSITIVITIES.json", sensitivities), ("DEMO_DECLARATION.json", declaration),
                       ("DEMO_DECLARATION_TWO_ROWS.json", two)):
        (OUT / name).write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"written: {sorted(p.name for p in OUT.glob('*.json'))}; truth {TRUTH}")


if __name__ == "__main__":
    main()
