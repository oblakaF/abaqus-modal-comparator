from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from universal_hardening import (
    _local_coordinate_diagnostics,
    _safe_mode_55,
    _safe_mode_2414,
    _scalar,
)


class UniversalHardeningTests(unittest.TestCase):
    def setUp(self):
        self.geometry = {
            1: np.array([0.0, 0.0, 0.0]),
            2: np.array([1.0, 0.0, 0.0]),
            3: np.array([0.0, 1.0, 0.0]),
        }

    def test_scalar_accepts_numpy_arrays(self):
        self.assertEqual(_scalar(np.array([7.0])), 7.0)
        self.assertIsNone(_scalar(np.array([]), None))

    def test_dataset_55_array_scalars_and_single_axis_mask(self):
        dataset = {
            "type": np.array([55]),
            "node_nums": np.array([1, 2, 3]),
            "r3": np.array([1.0, -0.5, 0.2]),
            "mode_n": np.array([4]),
            "freq": np.array([123.4]),
            "modal_damp_vis": np.array([0.012]),
            "modal_m": np.array([2.5]),
        }
        mode = _safe_mode_55(dataset, self.geometry, 1)
        self.assertEqual(mode.number, 4)
        self.assertAlmostEqual(mode.frequency_hz, 123.4)
        self.assertTrue(np.all(mode.measured_dofs[:, 2]))
        self.assertFalse(np.any(mode.measured_dofs[:, :2]))

    def test_dataset_2414_key_variants(self):
        dataset = {
            "type": np.array([2414]),
            "node_numbers": np.array([1, 2, 3]),
            "d1": np.array([0.1, 0.2, 0.3]),
            "d2": np.array([0.4, 0.5, 0.6]),
            "mode_n": np.array([8]),
            "freq": np.array([88.0]),
            "damping": np.array([0.02]),
            "mass": np.array([1.7]),
        }
        mode = _safe_mode_2414(dataset, self.geometry, 1)
        self.assertEqual(mode.number, 8)
        self.assertAlmostEqual(mode.frequency_hz, 88.0)
        self.assertTrue(np.all(mode.measured_dofs[:, :2]))
        self.assertFalse(np.any(mode.measured_dofs[:, 2]))

    def test_local_coordinate_system_warning_detection(self):
        diagnostics = _local_coordinate_diagnostics(
            [
                {
                    "type": 2411,
                    "def_cs": np.array([0, 7, 7]),
                    "disp_cs": np.array([0, 0, 0]),
                },
                {"type": 2420},
            ]
        )
        self.assertTrue(diagnostics["coordinate_system_dataset_2420_present"])
        self.assertIn(7, diagnostics["non_default_coordinate_system_ids"])


if __name__ == "__main__":
    unittest.main()
