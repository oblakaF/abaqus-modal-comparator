from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modal_core import ModalDataset, ModeShape
from reviewed_core import (
    _admissible_assignment,
    compare_modal_datasets,
    frequency_error_percent,
    geometry_alignment_candidates,
)


class ReviewedCoreTests(unittest.TestCase):
    def test_signed_frequency_error(self):
        self.assertAlmostEqual(frequency_error_percent(110.0, 100.0), 10.0)
        self.assertAlmostEqual(frequency_error_percent(90.0, 100.0), -10.0)

    def test_mac_uses_only_measured_experimental_dofs(self):
        coordinates = np.array(
            [
                [0.0, 0.0, 0.0],
                [2.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [2.0, 1.0, 0.0],
                [0.7, 0.4, 0.0],
            ]
        )
        node_ids = np.arange(1, len(coordinates) + 1)
        measured_shape = np.array([1.0, -0.5, 0.25, -1.0, 0.7])
        abaqus_vector = np.column_stack(
            (
                50.0 * np.arange(1, 6),
                -30.0 * np.arange(1, 6),
                measured_shape,
            )
        )
        experimental_vector = np.zeros_like(abaqus_vector)
        experimental_vector[:, 2] = 3.0 * measured_shape

        abaqus_mode = ModeShape(1, 100.0, node_ids, coordinates, abaqus_vector)
        experimental_mode = ModeShape(
            1, 100.5, node_ids, coordinates, experimental_vector
        )
        experimental_mode.measured_dofs = np.zeros_like(experimental_vector, dtype=bool)
        experimental_mode.measured_dofs[:, 2] = True

        result = compare_modal_datasets(
            ModalDataset("Abaqus", Path("model.odb"), [abaqus_mode]),
            ModalDataset("Experiment", Path("scan.unv"), [experimental_mode]),
            coordinate_scale_override=1.0,
        )
        self.assertEqual(len(result.pairs), 1)
        self.assertGreater(result.pairs[0].mac, 0.999999)
        self.assertEqual(result.pairs[0].mapped_points, len(coordinates))
        self.assertEqual(result.pairs[0].measured_dof_count, len(coordinates))

    def test_assignment_allows_unmatched_without_stealing_valid_partner(self):
        cost = np.array([[0.40, 0.95], [0.39, 0.50]])
        admissible = np.array([[True, False], [False, True]])
        rows, columns, _ = _admissible_assignment(cost, admissible)
        self.assertEqual(list(zip(rows.tolist(), columns.tolist())), [(0, 0), (1, 1)])

    def test_partial_noisy_geometry_with_manual_scale(self):
        x, y = np.meshgrid(np.linspace(0.0, 500.0, 21), np.linspace(0.0, 300.0, 13))
        abaqus = np.column_stack((x.ravel(), y.ravel(), np.zeros(x.size)))
        interior = (
            (abaqus[:, 0] >= 50.0)
            & (abaqus[:, 0] <= 450.0)
            & (abaqus[:, 1] >= 30.0)
            & (abaqus[:, 1] <= 270.0)
        )
        selected = abaqus[interior][::7]
        rotation = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
        rng = np.random.default_rng(4)
        experiment = selected @ rotation * 0.001 + np.array([2.0, -1.0, 0.0])
        experiment += rng.normal(scale=2.0e-5, size=experiment.shape)

        candidates = geometry_alignment_candidates(
            abaqus,
            experiment,
            coordinate_scale_override=0.001,
        )
        self.assertTrue(candidates)
        self.assertGreater(candidates[0].matched_fraction, 0.95)
        self.assertLess(candidates[0].normalized_rms_distance, 0.005)


if __name__ == "__main__":
    unittest.main()
