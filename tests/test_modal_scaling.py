from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from advanced_metrics import comac_by_node
from metrics_normalization import install_metrics_normalization
from modal_core import ModePairResult
from modal_scaling import correlation_plot_values


class ModalScalingTests(unittest.TestCase):
    @staticmethod
    def _pair(abaqus_values, experimental_values, abaqus_mode, experimental_mode):
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


if __name__ == "__main__":
    unittest.main()
