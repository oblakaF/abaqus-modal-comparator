from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from abaqus_bridge import load_extracted_odb, run_abaqus_extraction
from coordinate_calibration import CAMERA_GRID, CoordinateCalibration
from quality_control import _detect_rigid_modes, compare_modal_datasets_with_quality_control
from universal_reader import load_universal_modal_file


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the SP15 coordinate-calibration validation against supplied real inputs."
    )
    parser.add_argument("--odb", type=Path, required=True)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--abaqus-command", default="abaqus")
    parser.add_argument("--start-mode", type=int, default=1)
    parser.add_argument("--end-mode", type=int, default=20)
    args = parser.parse_args()

    odb = args.odb
    unv = args.experiment
    if not odb.is_file() or not unv.is_file():
        raise FileNotFoundError(f"Real SP15 input unavailable: ODB={odb.is_file()}, UNV={unv.is_file()}")
    with tempfile.TemporaryDirectory(prefix="sp15_calibration_") as directory:
        manifest = run_abaqus_extraction(
            odb,
            Path(directory),
            args.abaqus_command,
            args.start_mode,
            args.end_mode,
        )
        abaqus = load_extracted_odb(manifest)
        _, retained, _, _ = _detect_rigid_modes(abaqus)
        experimental = load_universal_modal_file(
            unv,
            target_frequencies=[mode.frequency_hz for mode in retained],
            target_count=max(len(retained), 1),
        )
        result = compare_modal_datasets_with_quality_control(
            abaqus,
            experimental,
            geometry_calibration=CoordinateCalibration(
                mode=CAMERA_GRID,
                abaqus_unit="mm",
                scan_coverage="full",
                physical_width=500.0,
                physical_height=500.0,
                dimension_unit="mm",
                provenance="Nominal SP15 500 x 500 identifier; validation fallback.",
            ),
        )
        print(
            json.dumps(
                {
                    "odb": str(odb),
                    "unv": str(unv),
                    "format_version": abaqus.metadata.get("format_version"),
                    "extracted_modes": [mode.number for mode in abaqus.sorted_modes()],
                    "scale_x": result.geometry.coordinate_scales[0],
                    "scale_y": result.geometry.coordinate_scales[1],
                    "matched_fraction": result.geometry.matched_fraction,
                    "normalized_rms": result.geometry.normalized_rms_distance,
                    "accepted_pairs": len(result.pairs),
                    "determinant": result.metadata["selected_geometry_transform"]["determinant"],
                    "planar_axes_swapped": result.metadata["selected_geometry_transform"]["planar_axes_swapped"],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
