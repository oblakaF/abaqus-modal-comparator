from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modal_core import ModalDataset, ModeShape
from quality_control import compare_modal_datasets_with_quality_control


class QualityControlTests(unittest.TestCase):
    def test_rigid_mode_and_forced_remote_pair_are_removed(self):
        x, y = np.meshgrid(np.linspace(0.0, 1.0, 5), np.linspace(0.0, 1.0, 5))
        coordinates = np.column_stack((x.ravel(), y.ravel(), np.zeros(x.size)))
        node_ids = np.arange(1, len(coordinates) + 1)

        shape_1 = np.zeros_like(coordinates)
        shape_1[:, 2] = np.sin(np.pi * coordinates[:, 0]) * np.sin(np.pi * coordinates[:, 1])
        shape_2 = np.zeros_like(coordinates)
        shape_2[:, 2] = np.sin(2.0 * np.pi * coordinates[:, 0]) * np.sin(np.pi * coordinates[:, 1])
        shape_3 = np.zeros_like(coordinates)
        shape_3[:, 2] = np.sin(np.pi * coordinates[:, 0]) * np.sin(2.0 * np.pi * coordinates[:, 1])

        abaqus = ModalDataset(
            "Abaqus",
            Path("model.odb"),
            [
                ModeShape(6, 0.0094, node_ids, coordinates, shape_1),
                ModeShape(7, 25.0, node_ids, coordinates, shape_1),
                ModeShape(8, 90.0, node_ids, coordinates, shape_2),
                ModeShape(9, 91.0, node_ids, coordinates, shape_3),
            ],
        )
        experiment = ModalDataset(
            "Experiment",
            Path("scan.unv"),
            [
                ModeShape(1, 25.2, node_ids, coordinates, shape_1),
                ModeShape(2, 89.8, node_ids, coordinates, shape_2),
                ModeShape(3, 220.0, node_ids, coordinates, shape_1),
            ],
        )

        result = compare_modal_datasets_with_quality_control(abaqus, experiment)

        self.assertEqual([pair.abaqus_mode for pair in result.pairs], [7, 8])
        self.assertEqual([pair.experimental_mode for pair in result.pairs], [1, 2])
        self.assertTrue(all(not pair.order_changed for pair in result.pairs))
        self.assertIn(6, result.abaqus.metadata["quality_control"]["excluded_abaqus_modes"])
        self.assertIn(9, result.abaqus.metadata["unmatched_abaqus_modes"])
        self.assertTrue(any("rigid-body" in warning for warning in result.warnings))
        self.assertTrue(any("left unmatched" in warning for warning in result.warnings))


if __name__ == "__main__":
    unittest.main()
