"""Freeze the SP-13 physical registration from its physical passport (M2 builder, unchanged), and report the
geometry-only metrics of the physically admissible FE sign alternatives. No modal data and no MAC are used.

    python tools/build_sp13_physical_registration.py --write
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.specimen_manifest import parse_specimen_manifest  # noqa: E402
from services.physical_registration import build_physical_registration  # noqa: E402

PASSPORT = ROOT / "docs/auto_id/specimens/SP13.physical.specimen.json"
REGISTRATION = ROOT / "docs/registrations/SP13_physical_registration.json"
RECORD = ROOT / "docs/auto_id/registration_evidence/SP13_physical_registration_reconstruction.json"
# Physically admissible proper mappings (viewer on the measured face, label at the top):
# TOP face seen from +Z, or BOTTOM face seen from -Z.
ALTERNATIVES = {
    "+x->+X, +y->+Y (TOP face, det +1)": (["+X", "+Y", "+Z"], "CFRP_PLATE_TOP", "max_z"),
    "+x->-X, +y->-Y (TOP face, det +1, 180 deg)": (["-X", "-Y", "+Z"], "CFRP_PLATE_TOP", "max_z"),
    "+x->-X, +y->+Y (BOTTOM face, det -1)": (["-X", "+Y", "-Z"], "CFRP_PLATE_BOT", "min_z"),
    "+x->+X, +y->-Y (BOTTOM face, det -1)": (["+X", "-Y", "-Z"], "CFRP_PLATE_BOT", "min_z"),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write the nominal registration file")
    args = parser.parse_args()
    raw = json.loads(PASSPORT.read_text(encoding="utf-8"))
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    nominal = build_physical_registration(parse_specimen_manifest(raw))
    print("production readiness issues:", nominal.production_readiness_issues() or "none")
    print("registration hash:", nominal.registration.registration_hash)
    summary = {}
    for name, (axes, instance, side) in ALTERNATIVES.items():
        variant = copy.deepcopy(raw)
        gc = variant["geometry_calibration"]
        gc["orientation"]["experimental_axes_in_fe"] = axes
        gc["measured_surface"]["fe_instance"], gc["measured_surface"]["side"] = instance, side
        gc["panel_edges"] = {"x_mm": round(record["fe_sign_alternatives"][name]["x_mm"], 4),
                             "y_mm": round(record["fe_sign_alternatives"][name]["y_mm"], 4)}
        result = build_physical_registration(parse_specimen_manifest(variant))
        m = result.registration.registration_metrics
        summary[name] = {"mapping_rms_mm": m["mapping_rms_in_abaqus_units"],
                         "mapping_max_mm": m["mapping_max_residual_in_abaqus_units"],
                         "unique_mapped_nodes": m["unique_mapped_abaqus_nodes"],
                         "panel_edges": gc["panel_edges"], "registration_hash": result.registration.registration_hash}
        print(f"{name}: rms {m['mapping_rms_in_abaqus_units']:.4f} mm, max {m['mapping_max_residual_in_abaqus_units']:.4f} mm,"
              f" unique nodes {m['unique_mapped_abaqus_nodes']}")
    print(json.dumps(summary, indent=1))
    if args.write:
        REGISTRATION.write_text(json.dumps(nominal.registration.to_dict(), indent=2, sort_keys=True) + "\n",
                                encoding="utf-8", newline="\n")
        print("wrote", REGISTRATION.relative_to(ROOT))


if __name__ == "__main__":
    main()
