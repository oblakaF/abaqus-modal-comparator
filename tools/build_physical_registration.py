"""Freeze a physical registration from a scan_to_panel_edges passport (M2 builder, unchanged), and report the
geometry-only metrics of the physically admissible FE sign alternatives. No modal data and no MAC are used.

    python tools/build_physical_registration.py \
        --passport docs/auto_id/specimens/SP02.physical.specimen.json \
        --record docs/auto_id/registration_evidence/SP02_physical_registration_reconstruction.json \
        --out docs/registrations/SP02_physical_registration.json

(SP-13 keeps its own accepted tool, tools/build_sp13_physical_registration.py.)
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

# Physically admissible proper mappings (viewer on the measured face, label at the top): TOP face seen from
# +Z, or BOTTOM face seen from -Z. The bottom-face instance is the TOP instance name with TOP -> BOT.
ALTERNATIVES = {
    "+x->+X, +y->+Y (TOP face, det +1)": (["+X", "+Y", "+Z"], "max_z"),
    "+x->-X, +y->-Y (TOP face, det +1, 180 deg)": (["-X", "-Y", "+Z"], "max_z"),
    "+x->-X, +y->+Y (BOTTOM face, det -1)": (["-X", "+Y", "-Z"], "min_z"),
    "+x->+X, +y->-Y (BOTTOM face, det -1)": (["+X", "-Y", "-Z"], "min_z"),
}
BOTTOM_INSTANCE = {"CFRP_PLATE_TOP": "CFRP_PLATE_BOT", "CFRP_FACESHEET-TOP": "CFRP_FACESHEET-BOT"}


def variants(raw: dict, record: dict) -> dict:
    out = {}
    top = raw["geometry_calibration"]["measured_surface"]["fe_instance"]
    for name, (axes, side) in ALTERNATIVES.items():
        variant = copy.deepcopy(raw)
        gc = variant["geometry_calibration"]
        gc["orientation"]["experimental_axes_in_fe"] = axes
        gc["measured_surface"]["side"] = side
        gc["measured_surface"]["fe_instance"] = top if side == "max_z" else BOTTOM_INSTANCE[top]
        gc["panel_edges"] = {k: round(v, 4) for k, v in record["fe_sign_alternatives"][name].items()}
        out[name] = variant
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--passport", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--out", type=Path, help="write the nominal registration file")
    args = parser.parse_args()
    raw = json.loads((ROOT / args.passport).read_text(encoding="utf-8"))
    record = json.loads((ROOT / args.record).read_text(encoding="utf-8"))
    nominal = build_physical_registration(parse_specimen_manifest(raw))
    print("production readiness issues:", nominal.production_readiness_issues() or "none")
    print("registration hash:", nominal.registration.registration_hash)
    summary = {}
    for name, variant in variants(raw, record).items():
        try:
            result = build_physical_registration(parse_specimen_manifest(variant))
        except Exception as error:  # an alternative that cannot be built is reported, never substituted
            summary[name] = {"status": f"not buildable: {error}"}
            continue
        m = result.registration.registration_metrics
        summary[name] = {"mapping_rms_mm": m["mapping_rms_in_abaqus_units"],
                         "mapping_max_mm": m["mapping_max_residual_in_abaqus_units"],
                         "unique_mapped_nodes": m["unique_mapped_abaqus_nodes"],
                         "panel_edges": variant["geometry_calibration"]["panel_edges"],
                         "registration_hash": result.registration.registration_hash}
    print(json.dumps(summary, indent=1))
    if args.out:
        (ROOT / args.out).write_text(json.dumps(nominal.registration.to_dict(), indent=2, sort_keys=True) + "\n",
                                     encoding="utf-8", newline="\n")
        print("wrote", args.out)


if __name__ == "__main__":
    main()
