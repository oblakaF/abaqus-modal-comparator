from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import advanced_metrics
from advanced_metrics import comac_by_node
from metrics_normalization import install_metrics_normalization
from modal_core import ModePairResult
from modal_scaling import correlation_plot_values


class ModalScalingTests(unittest.TestCase):
    @staticmethod
    def _pair(abaqus_values, experimental_values, abaqus_mode, experimental_mode, node_ids=None):
        coordinates = np.column_stack(
            (np.arange(len(abaqus_values), dtype=float), np.zeros(len(abaqus_values)), np.zeros(len(abaqus_values)))
        )
        abaqus = np.zeros((len(abaqus_values), 3), dtype=complex)
        experiment = np.zeros((len(experimental_values), 3), dtype=complex)
        abaqus[:, 2] = abaqus_values
        experiment[:, 2] = experimental_values
        mask = np.zeros_like(abaqus, dtype=bool)
        mask[:, 2] = True
        pair = ModePairResult(
            abaqus_mode=abaqus_mode,
            experimental_mode=experimental_mode,
            abaqus_frequency_hz=10.0 * abaqus_mode,
            experimental_frequency_hz=10.0 * experimental_mode,
            frequency_error_percent=0.0,
            mac=1.0,
            status="Excellent match",
            order_changed=False,
            mapped_points=len(abaqus_values),
            abaqus_vector=abaqus,
            experimental_vector=experiment,
            coordinates=coordinates,
            node_ids=np.arange(len(abaqus_values)) if node_ids is None else np.asarray(node_ids),
        )
        setattr(pair, "measured_dof_mask", mask)
        return pair

    def test_correlation_plot_is_invariant_to_arbitrary_modal_scale_and_phase(self):
        shape = np.array([-1.0, -0.25, 0.5, 1.0])
        pair = self._pair(
            shape * 2.5e6,
            shape * 3.0e-7 * np.exp(0.83j),
            1,
            1,
        )
        abaqus, experiment, coefficient = correlation_plot_values(pair)
        self.assertGreater(abs(coefficient), 0.0)
        self.assertGreater(np.max(np.abs(experiment)), 0.9)
        np.testing.assert_allclose(abaqus, experiment, atol=1.0e-12)

    def test_comac_is_invariant_to_independent_scale_and_phase_per_mode(self):
        shape_1 = np.array([1.0, 2.0, -1.0, -2.0])
        shape_2 = np.array([-2.0, 0.5, 1.5, -0.25])
        pairs = [
            self._pair(shape_1 * 1.0e5, shape_1 * 2.0e-6 * np.exp(0.4j), 1, 1),
            self._pair(shape_2 * 4.0e-3, shape_2 * 8.0e3 * np.exp(-1.2j), 2, 2),
        ]
        install_metrics_normalization()
        _, comac = comac_by_node(SimpleNamespace(pairs=pairs))
        np.testing.assert_allclose(comac, np.ones_like(comac), atol=1.0e-12)

    def test_common_pair_data_mask_is_the_intersection_of_each_pairs_own_mask(self):
        """Locks in current AutoMAC/COMAC behavior: the DOF mask used to build
        the common columns is the intersection (AND) of every pair's own
        measured_dof_mask, not a union. A DOF unmeasured in only one pair must
        drop out of the common set entirely. This is a different code path
        from the main per-pair MAC computation (see ROADMAP.md Stage 2, risk
        #2, which concerns a suspected union in the core comparison instead)."""
        shape = np.array([1.0, 2.0, -1.0, -2.0])
        pair_full = self._pair(shape * 1.0e5, shape * 2.0e-6, 1, 1)
        pair_partial = self._pair(shape * 4.0e-3, shape * 8.0e3, 2, 2)
        pair_partial.measured_dof_mask[1, 2] = False

        install_metrics_normalization()
        abaqus_columns, experimental_columns, common_mask = advanced_metrics._common_pair_data(
            SimpleNamespace(pairs=[pair_full, pair_partial])
        )

        self.assertFalse(common_mask[1, 2])
        self.assertTrue(common_mask[0, 2])
        self.assertEqual(abaqus_columns.shape[0], int(np.count_nonzero(common_mask)))
        self.assertEqual(experimental_columns.shape[0], int(np.count_nonzero(common_mask)))

    def test_different_node_ids_are_rejected_not_combined_positionally(self):
        """Same row count, different physical node IDs: AutoMAC/COMAC must
        refuse rather than silently correlate the wrong points row-by-row."""
        shape = np.array([1.0, 2.0, -1.0, -2.0])
        pair_a = self._pair(shape, shape, 1, 1, node_ids=[1, 2, 3, 4])
        pair_b = self._pair(shape, shape, 2, 2, node_ids=[5, 6, 7, 8])

        with self.assertRaisesRegex(ValueError, "different measurement grids"):
            advanced_metrics._common_pair_data(SimpleNamespace(pairs=[pair_a, pair_b]))
        with self.assertRaisesRegex(ValueError, "different measurement grids"):
            comac_by_node(SimpleNamespace(pairs=[pair_a, pair_b]))

    def test_same_node_ids_and_order_are_accepted_as_before(self):
        """Same physical grid in the same order: AutoMAC/COMAC compute
        exactly as before this guard was added."""
        shape_1 = np.array([1.0, 2.0, -1.0, -2.0])
        shape_2 = np.array([-2.0, 0.5, 1.5, -0.25])
        pair_a = self._pair(shape_1, shape_1, 1, 1, node_ids=[1, 2, 3, 4])
        pair_b = self._pair(shape_2, shape_2, 2, 2, node_ids=[1, 2, 3, 4])

        install_metrics_normalization()
        _, comac = comac_by_node(SimpleNamespace(pairs=[pair_a, pair_b]))
        np.testing.assert_allclose(comac, np.ones_like(comac), atol=1.0e-12)


if __name__ == "__main__":
    unittest.main()
