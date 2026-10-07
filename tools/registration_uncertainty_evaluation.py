"""M2.4 registration-uncertainty diagnostic of a frozen PHYSICAL registration on the existing FE shape pack.

Zero Abaqus: the FE surface (node ids, coordinates) and the FE mode shapes come from the validated M4 shape
pack, which holds the passport's measured outer surface; the experimental modes come from the accepted
fixture chain. The accepted pairs are the strict pairs already frozen in the registration re-evaluation
record (they are read, never chosen here). The nominal registration is unchanged and never replaced.

The service reports the second SPEC §11 trigger (a change of the accepted pairing) as DEFERRED_M4. Here it is
evaluated as a diagnostic with the accepted M4 machinery: under every perturbation the full MAC matrix is
recomputed on the pack and the unchanged STRICT freeze is re-run; any change of the strict pair set is reported.

    python tools/registration_uncertainty_evaluation.py \
        --passport docs/auto_id/specimens/SP13.physical.specimen.json \
        --registration docs/registrations/SP13_physical_registration.json \
        --baseline docs/auto_id/baselines/SP13.carbon4c-baseline.json --pack SP13_a46d08b52995e078 \
        --pairs docs/auto_id/registration_evidence/SP13_registration_reevaluation.json \
        --out docs/auto_id/registration_evidence/SP13_registration_uncertainty.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.experiment_fixture import fixture_roots_from_environment  # noqa: E402
from domain.forward_model_manifest import load_forward_model_manifest  # noqa: E402
from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING as STRICT  # noqa: E402
from domain.registration import FrozenRegistration  # noqa: E402
from domain.specimen_manifest import load_specimen_manifest  # noqa: E402
from services import experimental_qc as qc  # noqa: E402
from services.archived_baseline import _mac_matrix, load_archived_baseline, reregistered_shape_pack_evidence  # noqa: E402
from services.baseline_freeze import build_baseline_evidence, freeze_baseline  # noqa: E402
from services.fe_shape_pack import load_shape_pack, load_shape_pack_record  # noqa: E402
from services.physical_registration import FEGeometry  # noqa: E402
from services.registration_uncertainty import (  # noqa: E402
    _experimental_in_fe,
    _map,
    _perturbed_points,
    evaluate_registration_uncertainty,
    perturbation_set,
)


def strict_pairs(evidence) -> list[list[int]]:
    frozen = freeze_baseline(evidence, STRICT)
    rows = frozen.rows if frozen.frozen else frozen.provisional_rows
    return sorted([int(r.experimental_mode), int(r.fe_mode)] for r in rows)


def pairing_change(baseline, pack, registration, uncertainty, chain, forward_model_id) -> dict:
    """Strict pair set under every perturbation (same perturbations as M2.4; diagnostic only)."""
    modes = chain.dataset.sorted_modes()
    nominal_evidence = reregistered_shape_pack_evidence(baseline, pack, registration, modes, forward_model_id,
                                                        chain.eligibility)
    nominal = strict_pairs(nominal_evidence)
    surface = np.arange(len(pack.node_ids))
    fe = FEGeometry(np.array(pack.node_ids, dtype=object), np.asarray(pack.coordinates, dtype=float), {})
    points = _experimental_in_fe(registration, modes[0].coordinates)
    unit = str(registration.calibration.get("abaqus_unit", "mm"))
    perturbations, _ = perturbation_set(uncertainty)
    out = {}
    for perturbation in perturbations:
        mapped = _map(_perturbed_points(points, perturbation, unit), fe, surface)
        view = SimpleNamespace(rotation=registration.rotation, measured_dof_contract=registration.measured_dof_contract,
                               experimental_node_ids=registration.experimental_node_ids, mapped_fe_node_ids=mapped)
        matrix = _mac_matrix(baseline, pack, view, modes)
        evidence = build_baseline_evidence(nominal_evidence.identity, baseline.experimental_modes, chain.eligibility,
                                           baseline.fe_modes, matrix)
        out[perturbation.name] = strict_pairs(evidence)
    changed = sorted(name for name, pairs in out.items() if pairs != nominal)
    return {"nominal_strict_pairs": nominal, "per_perturbation": out, "changed_by": changed,
            "pairing_changed": bool(changed)}


def lf_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def compute(passport: Path, registration_path: Path, baseline_path: Path, pack_id: str, pairs_path: Path) -> dict:
    roots = fixture_roots_from_environment()
    manifest = load_specimen_manifest(ROOT / passport)
    registration = FrozenRegistration.from_dict(json.loads((ROOT / registration_path).read_text(encoding="utf-8")))
    baseline = load_archived_baseline(ROOT / baseline_path)
    forward = load_forward_model_manifest(ROOT / baseline.forward_model_path)
    legacy_passport = load_specimen_manifest(ROOT / forward.specimen_passport.path)
    chain = qc.prepare_auto_id_experimental_input(baseline.fixture_id, roots=roots, specimen_passport=legacy_passport)
    reevaluation = json.loads((ROOT / pairs_path).read_text(encoding="utf-8"))
    physical = reevaluation["results"]["PHYSICAL"]
    if physical["registration_hash"] != registration.registration_hash:
        raise SystemExit("the re-evaluation record was not computed on this registration")
    pairs = [(row["experimental_mode"], row["fe_mode"]) for row in physical["strict_pairs"]]
    pack = load_shape_pack(load_shape_pack_record(ROOT / "docs/auto_id/fe_shapes" / f"{pack_id}.shape-pack.json"), roots)
    node_ids = np.array(pack.node_ids, dtype=object)
    if not set(registration.mapped_fe_node_ids) <= set(pack.node_ids):
        raise SystemExit("the registration maps outside the pack's measured surface")
    first = chain.dataset.sorted_modes()[0]
    if [str(v) for v in first.node_ids] != [str(v) for v in registration.experimental_node_ids]:
        raise SystemExit("experimental point order differs from the registration")
    fe = FEGeometry(node_ids, np.asarray(pack.coordinates, dtype=float),
                    {"source": "shape pack measured surface", "pack": pack_id})
    shapes = {int(mode): {node: pack.displacements[k][i] for i, node in enumerate(pack.node_ids)}
              for k, mode in enumerate(pack.mode_numbers)}
    uncertainty = manifest.geometry_calibration.uncertainty
    report = evaluate_registration_uncertainty(registration, uncertainty, fe, list(pack.node_ids), chain.dataset,
                                               shapes, pairs, list(baseline.measured_dofs))
    change = pairing_change(baseline, pack, registration, uncertainty, chain, forward.forward_model_id)
    mac_crossing = report.registration_limited
    if change["pairing_changed"] or mac_crossing is True:
        overall = True
    elif mac_crossing is False:
        overall = False
    else:
        overall = None
    return {
        "schema": "auto-id/registration-uncertainty-evaluation/v1",
        "passport": str(passport).replace("\\", "/"), "passport_sha256_lf": lf_sha256(ROOT / passport),
        "registration_file": str(registration_path).replace("\\", "/"),
        "registration_hash": report.nominal_registration_hash, "pack": pack_id,
        "pairs_source": str(pairs_path).replace("\\", "/"), "accepted_pairs": [list(p) for p in pairs],
        "uncertainty": {"translation_mm": uncertainty.translation_mm, "scale_rel": uncertainty.scale_rel,
                        "rotation_deg": uncertainty.rotation_deg},
        "status": report.status.value, "available_components": list(report.available_components),
        "unavailable_components": list(report.unavailable_components),
        "perturbations": [{"name": o.perturbation.name, "remapped_points": o.remapped_points}
                          for o in report.perturbations],
        "pairs": [{"experimental_mode": p.experimental_mode, "fe_mode": p.fe_mode, "nominal_mac": p.nominal_mac,
                   "minimum_mac": p.minimum_mac, "maximum_mac": p.maximum_mac,
                   "per_perturbation": dict(p.per_perturbation), "invalid_perturbations": list(p.invalid_perturbations),
                   "crosses_threshold": p.crosses_threshold} for p in report.pairs],
        "registration_limited": report.registration_limited, "threshold": report.threshold,
        "pairing_change_evaluation": report.pairing_change_evaluation,
        "pairing_change_diagnostic": change,
        "registration_limited_both_triggers": overall,
        "abaqus_solves": 0, "abaqus_python_extractions": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name in ("--passport", "--registration", "--baseline", "--pairs", "--out"):
        parser.add_argument(name, type=Path, required=name != "--out")
    parser.add_argument("--pack", required=True)
    args = parser.parse_args()
    document = compute(args.passport, args.registration, args.baseline, args.pack, args.pairs)
    print(json.dumps({k: document[k] for k in ("status", "unavailable_components", "registration_limited",
                                                "registration_limited_both_triggers")}))
    print("pairing change:", json.dumps({k: v for k, v in document["pairing_change_diagnostic"].items()
                                         if k != "per_perturbation"}))
    for p in document["pairs"]:
        print(p["experimental_mode"], p["fe_mode"], "nominal %.4f min %.4f max %.4f" % (
            p["nominal_mac"], p["minimum_mac"], p["maximum_mac"]), "crosses", p["crosses_threshold"])
    if args.out:
        (ROOT / args.out).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                                     newline="\n")
        print("wrote", args.out)


if __name__ == "__main__":
    main()
