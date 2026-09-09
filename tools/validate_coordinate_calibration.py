from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from abaqus_bridge import load_extracted_odb
from coordinate_calibration import CAMERA_GRID, CoordinateCalibration
from quality_control import _detect_rigid_modes, compare_modal_datasets_with_quality_control
from universal_reader import load_universal_modal_file


def summarize(result, include_matrix: bool = True) -> dict:
    transform = result.metadata["selected_geometry_transform"]
    summary = {
        "calibration": result.geometry.calibration_details,
        "coordinate_scale": result.geometry.coordinate_scale,
        "coordinate_scales": result.geometry.coordinate_scales.tolist(),
        "matched_fraction": result.geometry.matched_fraction,
        "normalized_rms": result.geometry.normalized_rms_distance,
        "mapping_rms": result.metadata["mapping_rms"],
        "mapping_max_residual": result.metadata["mapping_max_residual"],
        "mapping_rms_in_abaqus_units": result.metadata["mapping_rms_in_abaqus_units"],
        "mapping_max_residual_in_abaqus_units": result.metadata["mapping_max_residual_in_abaqus_units"],
        "raw_experimental_bbox": result.metadata["raw_experimental_bbox"],
        "mapped_fe_bbox": result.metadata["mapped_fe_bbox"],
        "rotation": transform["rotation"],
        "determinant": transform["determinant"],
        "axis_permutation": transform["axis_permutation"],
        "planar_axes_swapped": transform["planar_axes_swapped"],
        "accepted_pairs": [
            {
                "abaqus_mode": pair.abaqus_mode,
                "experimental_mode": pair.experimental_mode,
                "mac": pair.mac,
                "frequency_error_percent": pair.frequency_error_percent,
            }
            for pair in result.pairs
        ],
        "warnings": result.warnings,
    }
    if include_matrix:
        summary["mac_matrix"] = np.asarray(result.mac_matrix).tolist()
    return summary


def main() -> None:
    root = ROOT / ".sandwich_postfix_benchmark"
    abaqus = load_extracted_odb(root / "after_7_16" / "manifest.json")
    _, retained, _, _ = _detect_rigid_modes(abaqus)
    experimental = load_universal_modal_file(
        root / "500by500_Glue420_Auxetic_full_scan_260624.unv",
        target_frequencies=[mode.frequency_hz for mode in retained],
        target_count=max(len(retained), 1),
    )
    fixed = compare_modal_datasets_with_quality_control(
        abaqus, experimental, coordinate_scale_override=0.001
    )
    legacy = compare_modal_datasets_with_quality_control(abaqus, experimental)
    camera = compare_modal_datasets_with_quality_control(
        abaqus,
        experimental,
        geometry_calibration=CoordinateCalibration(
            mode=CAMERA_GRID,
            abaqus_unit="mm",
            scan_coverage="full",
            physical_width=500.0,
            physical_height=500.0,
            dimension_unit="mm",
            provenance=(
                "Nominal 500 x 500 mm fallback; no independent measurement record was found locally."
            ),
        ),
    )
    include_matrix = "--summary" not in sys.argv[1:]
    print(json.dumps({"fixed_0.001": summarize(fixed, include_matrix), "legacy_auto": summarize(legacy, include_matrix), "camera_nominal_500x500": summarize(camera, include_matrix)}, indent=2))


if __name__ == "__main__":
    main()
