from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from universal_frf_review import modes_from_frf_datasets
from universal_hardening import install_universal_hardening

install_universal_hardening()


class FrfModeImportTests(unittest.TestCase):
    def test_modes_are_derived_from_complex_frf_dataset_58(self):
        axis = np.linspace(1.0, 160.0, 1273)
        natural_frequencies = [24.0, 71.0, 118.0]
        damping = [0.012, 0.009, 0.015]

        x, y = np.meshgrid(np.linspace(-0.2, 0.2, 5), np.linspace(-0.2, 0.2, 5))
        coordinates = np.column_stack((x.ravel(), y.ravel(), np.zeros(x.size)))
        geometry = {index + 1: coordinate for index, coordinate in enumerate(coordinates)}

        shapes = [
            np.sin(np.pi * (coordinates[:, 0] + 0.2) / 0.4)
            * np.sin(np.pi * (coordinates[:, 1] + 0.2) / 0.4),
            np.sin(2.0 * np.pi * (coordinates[:, 0] + 0.2) / 0.4)
            * np.sin(np.pi * (coordinates[:, 1] + 0.2) / 0.4),
            np.sin(np.pi * (coordinates[:, 0] + 0.2) / 0.4)
            * np.sin(2.0 * np.pi * (coordinates[:, 1] + 0.2) / 0.4),
        ]

        datasets = []
        for node_index in range(len(coordinates)):
            response = np.zeros_like(axis, dtype=complex)
            for mode_frequency, mode_damping, shape in zip(
                natural_frequencies, damping, shapes
            ):
                denominator = (
                    mode_frequency**2
                    - axis**2
                    + 2j * mode_damping * mode_frequency * axis
                )
                response += shape[node_index] / denominator

            datasets.append(
                {
                    "type": 58,
                    "func_type": 4,
                    "id1": "Transfer Function H1",
                    "id2": "H1 Displacement / Force",
                    "rsp_node": node_index + 1,
                    "rsp_dir": 3,
                    "ref_node": 1,
                    "ref_dir": 3,
                    "x": axis,
                    "data": response,
                }
            )
            datasets.append(
                {
                    "type": 58,
                    "func_type": 6,
                    "id2": "Coherence",
                    "rsp_node": node_index + 1,
                    "rsp_dir": 3,
                    "ref_node": 1,
                    "ref_dir": 3,
                    "x": axis,
                    "data": np.full_like(axis, 0.98, dtype=float),
                }
            )

        modes, metadata = modes_from_frf_datasets(
            datasets,
            geometry,
            target_frequencies=natural_frequencies,
            target_count=3,
        )

        detected = np.array([mode.frequency_hz for mode in modes])
        for expected in natural_frequencies:
            self.assertLess(float(np.min(np.abs(detected - expected))), 0.8)

        self.assertEqual(metadata["requested_peak_count"], 3)
        self.assertEqual(metadata["frf_response_node_count"], 25)
        self.assertEqual(metadata["coherence_channel_count"], 25)
        self.assertTrue(all(mode.metadata["dataset_type"] == 58 for mode in modes))
        self.assertTrue(all(mode.vectors.shape == (25, 3) for mode in modes))
        self.assertTrue(all(np.all(mode.measured_dofs[:, 2]) for mode in modes))
        self.assertTrue(all(not np.any(mode.measured_dofs[:, :2]) for mode in modes))


if __name__ == "__main__":
    unittest.main()
