from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from coordinate_calibration import (
    CALIBRATED_PHYSICAL,
    CAMERA_GRID,
    LEGACY_GEOMETRIC_FIT,
    CoordinateCalibration,
    scale_candidates,
)
from project_review import PROJECT_SCHEMA_VERSION, project_payload, read_project, write_project
from reviewed_core import geometry_alignment_candidates


class CoordinateCalibrationTests(unittest.TestCase):
    def test_calibrated_units_are_exact_and_never_extent_fit(self):
        calibration = CoordinateCalibration(
            mode=CALIBRATED_PHYSICAL,
            abaqus_unit="mm",
            experimental_unit="m",
            provenance="calibrated scanner",
        )
        scales = scale_candidates(calibration, np.array([[0, 0, 0], [99, 12, 0]]))
        self.assertEqual(len(scales), 1)
        np.testing.assert_array_equal(scales[0][0], np.array([0.001, 0.001, 0.001]))
        self.assertEqual(scales[0][1]["mode"], CALIBRATED_PHYSICAL)

    def test_full_camera_grid_has_independent_xy_calibration(self):
        coordinates = np.array([[0.0, 0.0, -1.0], [0.332937, 0.328658, -1.0]])
        calibration = CoordinateCalibration(
            mode=CAMERA_GRID,
            abaqus_unit="mm",
            scan_coverage="full",
            physical_width=500.0,
            physical_height=500.0,
            dimension_unit="mm",
            provenance="nominal full-panel fallback",
        )
        candidates = scale_candidates(calibration, coordinates)
        self.assertAlmostEqual(candidates[0][0][0], 0.332937 / 500.0)
        self.assertAlmostEqual(candidates[0][0][1], 0.328658 / 500.0)
        self.assertNotEqual(candidates[0][0][0], candidates[0][0][1])

    def test_partial_camera_grid_without_scan_window_dimensions_fails(self):
        calibration = CoordinateCalibration(
            mode=CAMERA_GRID,
            abaqus_unit="mm",
            scan_coverage="partial",
            dimension_unit="mm",
            provenance="partial scan",
        )
        with self.assertRaisesRegex(ValueError, "partial.*scan-window"):
            calibration.validate()

    def test_swapped_width_height_candidate_is_explicit(self):
        coordinates = np.array([[0.0, 0.0, 0.0], [0.4, 0.2, 0.0]])
        calibration = CoordinateCalibration(
            mode=CAMERA_GRID,
            abaqus_unit="mm",
            scan_coverage="full",
            physical_width=400.0,
            physical_height=100.0,
            dimension_unit="mm",
        )
        candidates = scale_candidates(calibration, coordinates)
        self.assertEqual([item[1]["axes_swapped"] for item in candidates], [False, True])
        self.assertAlmostEqual(candidates[1][0][0], 0.4 / 100.0)
        self.assertAlmostEqual(candidates[1][0][1], 0.2 / 400.0)

    def test_registration_keeps_reflection_candidates_admissible(self):
        abaqus = np.array(
            [[0.0, 0.0, 0.0], [100.0, 0.0, 0.0], [0.0, 80.0, 0.0], [35.0, 20.0, 0.0]]
        )
        experimental = np.column_stack((-abaqus[:, 0] * 0.001, abaqus[:, 1] * 0.001, np.zeros(4)))
        calibration = CoordinateCalibration(
            mode=CALIBRATED_PHYSICAL, abaqus_unit="mm", experimental_unit="m"
        )
        candidates = geometry_alignment_candidates(
            abaqus, experimental, geometry_calibration=calibration
        )
        self.assertTrue(any(np.linalg.det(item.rotation) < 0 for item in candidates))
        self.assertLess(candidates[0].normalized_rms_distance, 1.0e-12)

    def test_legacy_auto_is_migrated_without_reinterpretation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.amcp.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "inputs": {"coordinate_scale": "auto"},
                        "manual_reviews": {},
                    }
                ),
                encoding="utf-8",
            )
            payload = read_project(path)
        self.assertEqual(payload["schema_version"], PROJECT_SCHEMA_VERSION)
        self.assertEqual(payload["inputs"]["geometry_calibration"]["mode"], LEGACY_GEOMETRIC_FIT)
        self.assertIn("not reinterpreted", payload["load_warnings"][0])

    def test_project_persists_explicit_camera_provenance(self):
        calibration = CoordinateCalibration(
            mode=CAMERA_GRID,
            abaqus_unit="mm",
            scan_coverage="full",
            physical_width=500.0,
            physical_height=499.5,
            dimension_unit="mm",
            provenance="caliper record 42",
        )
        payload = project_payload(
            abaqus_path="a.odb",
            experimental_path="e.unv",
            workspace_path="out",
            abaqus_command="abaqus",
            start_mode=1,
            end_mode=10,
            coordinate_scale="camera_grid",
            manual_reviews={},
            geometry_calibration=calibration.to_dict(),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = write_project(Path(directory) / "project.amcp.json", payload)
            loaded = read_project(path)
        self.assertEqual(loaded["inputs"]["geometry_calibration"], calibration.to_dict())


if __name__ == "__main__":
    unittest.main()
