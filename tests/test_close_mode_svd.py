from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cmif_separation
import universal_reader
from modal_core import ModeShape, modal_assurance_criterion


class CloseModeSvdTests(unittest.TestCase):
    def test_single_reference_local_svd_adds_missing_close_mode_candidate(self):
        x, y = np.meshgrid(np.linspace(-1.0, 1.0, 7), np.linspace(-1.0, 1.0, 7))
        coordinates = np.column_stack((x.ravel(), y.ravel(), np.zeros(x.size)))
        node_numbers = np.arange(1, len(coordinates) + 1)
        geometry = {int(node): coordinate for node, coordinate in zip(node_numbers, coordinates)}

        shape_1 = np.sin(np.pi * (x.ravel() + 1.0) / 2.0) * np.sin(
            np.pi * (y.ravel() + 1.0) / 2.0
        )
        shape_2 = np.sin(2.0 * np.pi * (x.ravel() + 1.0) / 2.0) * np.sin(
            np.pi * (y.ravel() + 1.0) / 2.0
        )
        shape_1 /= np.linalg.norm(shape_1)
        shape_2 /= np.linalg.norm(shape_2)

        frequency = np.linspace(86.0, 97.0, 353)
        f1, f2 = 91.35, 92.10
        zeta_1, zeta_2 = 0.010, 0.012
        datasets = []
        for index, node in enumerate(node_numbers):
            denominator_1 = f1**2 - frequency**2 + 2j * zeta_1 * f1 * frequency
            denominator_2 = f2**2 - frequency**2 + 2j * zeta_2 * f2 * frequency
            response = shape_1[index] / denominator_1 + 0.75 * shape_2[index] / denominator_2
            datasets.append(
                {
                    "type": 58,
                    "func_type": 4,
                    "id1": "Transfer Function H1",
                    "id2": "H1 Displacement / Force",
                    "rsp_node": int(node),
                    "rsp_dir": 3,
                    "ref_node": 1,
                    "ref_dir": 3,
                    "x": frequency,
                    "data": response,
                }
            )

        base_vectors = np.zeros((len(node_numbers), 3), dtype=complex)
        base_vectors[:, 2] = shape_1
        base_mode = ModeShape(
            number=1,
            frequency_hz=91.72,
            node_ids=node_numbers.astype(object),
            coordinates=coordinates,
            vectors=base_vectors,
            metadata={"mode_source": "single detected peak"},
        )
        base_mode.measured_dofs = np.column_stack(
            (
                np.zeros(len(node_numbers), dtype=bool),
                np.zeros(len(node_numbers), dtype=bool),
                np.ones(len(node_numbers), dtype=bool),
            )
        )

        def fake_base_reader(*_args, **_kwargs):
            return [base_mode], {"mode_source": "test peak extraction"}

        with patch.object(
            cmif_separation,
            "_ORIGINAL_MODES_FROM_FRF",
            fake_base_reader,
            create=True,
        ):
            modes, metadata = cmif_separation._reviewed_modes_from_frf(
                datasets,
                geometry,
                target_frequencies=[f1, f2],
                target_count=2,
            )

        self.assertGreaterEqual(len(modes), 2)
        separation = metadata["close_mode_separation"]
        self.assertEqual(separation["added_mode_count"], 1)
        self.assertEqual(separation["reference_count"], 1)
        candidate = [
            mode
            for mode in modes
            if mode.metadata.get("mode_source")
            == "local response-matrix SVD close-mode candidate"
        ][0]
        self.assertTrue(np.any(np.abs(candidate.vectors[:, 2]) > 0.0))
        self.assertLess(
            modal_assurance_criterion(base_mode.vectors, candidate.vectors),
            0.98,
        )

    def test_malformed_coherence_dataset_falls_back_conservatively_and_warns(self):
        x, y = np.meshgrid(np.linspace(-1.0, 1.0, 7), np.linspace(-1.0, 1.0, 7))
        coordinates = np.column_stack((x.ravel(), y.ravel(), np.zeros(x.size)))
        node_numbers = np.arange(1, len(coordinates) + 1)
        geometry = {int(node): coordinate for node, coordinate in zip(node_numbers, coordinates)}

        shape_1 = np.sin(np.pi * (x.ravel() + 1.0) / 2.0) * np.sin(
            np.pi * (y.ravel() + 1.0) / 2.0
        )
        shape_2 = np.sin(2.0 * np.pi * (x.ravel() + 1.0) / 2.0) * np.sin(
            np.pi * (y.ravel() + 1.0) / 2.0
        )
        shape_1 /= np.linalg.norm(shape_1)
        shape_2 /= np.linalg.norm(shape_2)

        frequency = np.linspace(86.0, 97.0, 353)
        f1, f2 = 91.35, 92.10
        zeta_1, zeta_2 = 0.010, 0.012
        datasets = []
        for index, node in enumerate(node_numbers):
            denominator_1 = f1**2 - frequency**2 + 2j * zeta_1 * f1 * frequency
            denominator_2 = f2**2 - frequency**2 + 2j * zeta_2 * f2 * frequency
            response = shape_1[index] / denominator_1 + 0.75 * shape_2[index] / denominator_2
            datasets.append(
                {
                    "type": 58,
                    "func_type": 4,
                    "id1": "Transfer Function H1",
                    "id2": "H1 Displacement / Force",
                    "rsp_node": int(node),
                    "rsp_dir": 3,
                    "ref_node": 1,
                    "ref_dir": 3,
                    "x": frequency,
                    "data": response,
                }
            )
        # A normal coherence channel; the failure this test targets is injected
        # below via a patched universal_reader._coherence_by_dof instead of a
        # specific malformed shape, so the fallback stays covered as
        # defense-in-depth even now that universal_hardening.install_universal_hardening
        # hardens _coherence_by_dof itself against malformed pyuff scalars.
        datasets.append(
            {
                "type": 58,
                "func_type": 6,
                "rsp_node": 1,
                "rsp_dir": 3,
                "ref_node": 1,
                "ref_dir": 3,
                "x": frequency,
                "data": np.full_like(frequency, 0.9),
            }
        )

        base_vectors = np.zeros((len(node_numbers), 3), dtype=complex)
        base_vectors[:, 2] = shape_1
        base_mode = ModeShape(
            number=1,
            frequency_hz=91.72,
            node_ids=node_numbers.astype(object),
            coordinates=coordinates,
            vectors=base_vectors,
            metadata={"mode_source": "single detected peak"},
        )
        base_mode.measured_dofs = np.column_stack(
            (
                np.zeros(len(node_numbers), dtype=bool),
                np.zeros(len(node_numbers), dtype=bool),
                np.ones(len(node_numbers), dtype=bool),
            )
        )

        def fake_base_reader(*_args, **_kwargs):
            return [base_mode], {"mode_source": "test peak extraction"}

        with patch.object(
            cmif_separation,
            "_ORIGINAL_MODES_FROM_FRF",
            fake_base_reader,
            create=True,
        ), patch.object(
            universal_reader,
            "_coherence_by_dof",
            side_effect=ValueError("boom"),
        ):
            _modes, metadata = cmif_separation._reviewed_modes_from_frf(
                datasets,
                geometry,
                target_frequencies=[f1, f2],
                target_count=2,
            )

        separation = metadata["close_mode_separation"]
        self.assertTrue(separation["coherence_status"].startswith("error"))
        self.assertIn("Coherence-based weighting could not be computed", separation["scientific_warning"])


if __name__ == "__main__":
    unittest.main()
