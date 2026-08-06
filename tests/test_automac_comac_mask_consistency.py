"""ROADMAP Stage 2 #3 required test: "AutoMAC and COMAC consistency" after
per-experimental-mode measured-DOF masks replaced the prior cross-mode union
(see tests/test_reviewed_core.py's
test_pair_uses_only_its_own_experimental_modes_measured_dofs for the MAC/pair
level fix this builds on).

advanced_metrics._common_pair_data ANDs every accepted pair's own
measured_dof_mask together to get one common row grid for AutoMAC/COMAC's
Gram-matrix computation. Before the reviewed_core.py fix, every pair shared
the same leaked union mask, so this AND silently included DOFs that were
never actually measured for a given pair's own experimental mode. After the
fix, each pair's mask is genuinely that pair's own experimental mode's mask,
so ANDing two pairs whose experimental modes measured disjoint components
correctly finds no common ground -- it must raise a clear error instead of
silently computing AutoMAC/COMAC over falsely-shared DOFs.
"""

from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from advanced_metrics import automac_matrices, comac_by_node
from modal_core import ModalDataset, ModeShape
from reviewed_core import compare_modal_datasets


class AutomacComacMaskConsistencyTests(unittest.TestCase):
    def _disjoint_mask_result(self):
        coordinates = np.array(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [1.0, 1.0, 0.0],
            ]
        )
        node_ids = np.arange(1, 5)
        shape_z = np.array([1.0, -1.0, 0.5, -0.5])
        abaqus_x = np.array([1.0, -1.0, 1.0, -1.0])
        phantom_x = np.array([1.0, 1.0, -1.0, -1.0])

        abaqus_vector_1 = np.zeros((4, 3))
        abaqus_vector_1[:, 2] = shape_z
        abaqus_vector_1[:, 0] = abaqus_x
        abaqus_vector_2 = np.zeros((4, 3))
        abaqus_vector_2[:, 0] = abaqus_x

        experimental_vector_1 = np.zeros((4, 3))
        experimental_vector_1[:, 2] = shape_z
        experimental_vector_1[:, 0] = phantom_x
        experimental_mode_1 = ModeShape(
            1, 100.5, node_ids, coordinates, experimental_vector_1
        )
        experimental_mode_1.measured_dofs = np.zeros((4, 3), dtype=bool)
        experimental_mode_1.measured_dofs[:, 2] = True  # Z only

        experimental_vector_2 = np.zeros((4, 3))
        experimental_vector_2[:, 0] = abaqus_x
        experimental_mode_2 = ModeShape(
            2, 200.5, node_ids, coordinates, experimental_vector_2
        )
        experimental_mode_2.measured_dofs = np.zeros((4, 3), dtype=bool)
        experimental_mode_2.measured_dofs[:, 0] = True  # X only

        abaqus = ModalDataset(
            "Abaqus",
            Path("model.odb"),
            [
                ModeShape(1, 100.0, node_ids, coordinates, abaqus_vector_1),
                ModeShape(2, 200.0, node_ids, coordinates, abaqus_vector_2),
            ],
        )
        experiment = ModalDataset(
            "Experiment",
            Path("scan.unv"),
            [experimental_mode_1, experimental_mode_2],
        )
        return compare_modal_datasets(abaqus, experiment, coordinate_scale_override=1.0)

    def test_automac_raises_instead_of_silently_using_falsely_shared_dofs(self):
        result = self._disjoint_mask_result()
        # Sanity: the two pairs really do carry disjoint per-mode masks now.
        pair_1 = next(p for p in result.pairs if p.experimental_mode == 1)
        pair_2 = next(p for p in result.pairs if p.experimental_mode == 2)
        self.assertFalse(
            np.any(pair_1.measured_dof_mask & pair_2.measured_dof_mask)
        )
        with self.assertRaises(ValueError):
            automac_matrices(result)
        with self.assertRaises(ValueError):
            comac_by_node(result)

    def test_automac_uses_the_genuine_per_pair_mask_when_shared(self):
        """Same geometry, but both experimental modes measure the same
        component (Z only): AutoMAC/COMAC must succeed and use exactly that
        shared, genuine per-pair mask -- not a coincidentally wider one."""
        coordinates = np.array(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [1.0, 1.0, 0.0],
            ]
        )
        node_ids = np.arange(1, 5)
        shape_a = np.array([1.0, -1.0, 0.5, -0.5])
        shape_b = np.array([0.3, 0.6, -0.2, -0.7])

        abaqus_vector_1 = np.zeros((4, 3))
        abaqus_vector_1[:, 2] = shape_a
        abaqus_vector_2 = np.zeros((4, 3))
        abaqus_vector_2[:, 2] = shape_b

        experimental_mode_1 = ModeShape(
            1, 100.5, node_ids, coordinates, np.column_stack([np.zeros(4), np.zeros(4), shape_a])
        )
        experimental_mode_1.measured_dofs = np.zeros((4, 3), dtype=bool)
        experimental_mode_1.measured_dofs[:, 2] = True
        experimental_mode_2 = ModeShape(
            2, 200.5, node_ids, coordinates, np.column_stack([np.zeros(4), np.zeros(4), shape_b])
        )
        experimental_mode_2.measured_dofs = np.zeros((4, 3), dtype=bool)
        experimental_mode_2.measured_dofs[:, 2] = True

        abaqus = ModalDataset(
            "Abaqus",
            Path("model.odb"),
            [
                ModeShape(1, 100.0, node_ids, coordinates, abaqus_vector_1),
                ModeShape(2, 200.0, node_ids, coordinates, abaqus_vector_2),
            ],
        )
        experiment = ModalDataset(
            "Experiment",
            Path("scan.unv"),
            [experimental_mode_1, experimental_mode_2],
        )
        result = compare_modal_datasets(abaqus, experiment, coordinate_scale_override=1.0)

        abaqus_automac, experimental_automac = automac_matrices(result)
        self.assertEqual(abaqus_automac.shape, (2, 2))
        self.assertEqual(experimental_automac.shape, (2, 2))
        np.testing.assert_allclose(np.diag(abaqus_automac), [1.0, 1.0], atol=1e-9)
        np.testing.assert_allclose(np.diag(experimental_automac), [1.0, 1.0], atol=1e-9)

        coordinates_out, node_scores = comac_by_node(result)
        self.assertEqual(len(node_scores), 4)
        self.assertTrue(np.all(np.isfinite(node_scores)))


if __name__ == "__main__":
    unittest.main()
