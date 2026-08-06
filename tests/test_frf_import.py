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

    def test_malformed_scalar_fields_are_skipped_not_crashed(self):
        """universal_reader._select_frf_group/_coherence_by_dof used to read
        rsp_node/ref_node/ref_dir with a bare int(x or 0), which raises on a
        multi-element numpy array (pyuff sometimes wraps a scalar this way)
        instead of just not matching. install_universal_hardening() now
        hardens both functions directly, so this exercises the real,
        un-mocked production path end to end, not just the narrower
        cmif_separation fallback."""
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

        # A response channel whose rsp_node is a malformed multi-element array
        # (not a node that exists in the geometry either way) must be skipped,
        # not crash _select_frf_group.
        datasets.append(
            {
                "type": 58,
                "func_type": 4,
                "id1": "Transfer Function H1",
                "id2": "H1 Displacement / Force",
                "rsp_node": np.array([9001, 9002]),
                "rsp_dir": 3,
                "ref_node": 1,
                "ref_dir": 3,
                "x": axis,
                "data": np.zeros_like(axis, dtype=complex),
            }
        )
        # A coherence channel whose ref_node is a malformed multi-element array
        # that does not match the real reference node must be skipped, not
        # crash _coherence_by_dof with numpy's ambiguous-truth-value error.
        datasets.append(
            {
                "type": 58,
                "func_type": 6,
                "id2": "Coherence",
                "rsp_node": 1,
                "rsp_dir": 3,
                "ref_node": np.array([2, 1]),
                "ref_dir": 3,
                "x": axis,
                "data": np.full_like(axis, 0.5, dtype=float),
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
        self.assertEqual(metadata["frf_response_node_count"], 25)
        self.assertEqual(metadata["coherence_channel_count"], 25)

    def _response_only_datasets(self):
        """FRF response channels with no dataset-58 coherence (func_type 6) at all."""
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
        return datasets, geometry, natural_frequencies

    def test_absent_coherence_channels_are_reported_as_unavailable_not_perfect(self):
        """ROADMAP Stage 2 #1: no coherence channels must not read as perfect
        coherence (mean_coherence == 1.0) downstream."""
        datasets, geometry, natural_frequencies = self._response_only_datasets()

        modes, metadata = modes_from_frf_datasets(
            datasets,
            geometry,
            target_frequencies=natural_frequencies,
            target_count=3,
        )

        self.assertEqual(metadata["coherence_channel_count"], 0)
        self.assertEqual(metadata["coherence_status"], "unavailable")
        self.assertIsNone(metadata["coherence_parse_error"])
        self.assertTrue(all(np.isnan(metadata["_frf_mean_coherence"])))
        for mode in modes:
            self.assertIsNone(mode.metadata["mean_coherence"])
            self.assertEqual(mode.metadata["coherence_status"], "unavailable")

    def test_malformed_coherence_dataset_is_reported_as_parse_error(self):
        """A coherence channel that exists but cannot be parsed must not be
        silently treated the same as "no channel was ever exported"."""
        import universal_reader

        datasets, geometry, natural_frequencies = self._response_only_datasets()
        original = universal_reader._coherence_by_dof
        universal_reader._coherence_by_dof = lambda *args, **kwargs: (_ for _ in ()).throw(
            ValueError("malformed coherence dataset")
        )
        try:
            modes, metadata = modes_from_frf_datasets(
                datasets,
                geometry,
                target_frequencies=natural_frequencies,
                target_count=3,
            )
        finally:
            universal_reader._coherence_by_dof = original

        self.assertEqual(metadata["coherence_status"], "parse_error")
        self.assertIn("malformed coherence dataset", metadata["coherence_parse_error"])
        for mode in modes:
            self.assertIsNone(mode.metadata["mean_coherence"])
            self.assertEqual(mode.metadata["coherence_status"], "parse_error")


if __name__ == "__main__":
    unittest.main()
