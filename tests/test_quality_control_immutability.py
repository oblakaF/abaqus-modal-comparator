from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modal_core import ModalDataset, ModeShape
from quality_control_reviewed import compare_modal_datasets_with_quality_control


class QualityControlImmutabilityTests(unittest.TestCase):
    def test_input_datasets_are_not_mutated(self):
        # Fourth corner nudged off the exact unit square -- see the comment
        # in tests/test_reviewed_core.py on the same pattern -- so the point
        # set has exactly one geometrically admissible registration.
        coordinates = np.array(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [1.15, 0.95, 0.0],
            ]
        )
        vectors = np.zeros((4, 3))
        vectors[:, 2] = [1.0, -1.0, -1.0, 1.0]
        ids = np.arange(4)
        abaqus = ModalDataset(
            "Abaqus",
            Path("model.odb"),
            [ModeShape(7, 30.0, ids, coordinates, vectors)],
            metadata={"owner": "caller"},
        )
        experiment = ModalDataset(
            "Experiment",
            Path("scan.unv"),
            [ModeShape(1, 30.1, ids, coordinates, vectors)],
            metadata={"owner": "caller"},
        )

        compare_modal_datasets_with_quality_control(
            abaqus,
            experiment,
            coordinate_scale_override=1.0,
        )

        self.assertEqual(abaqus.metadata, {"owner": "caller"})
        self.assertEqual(experiment.metadata, {"owner": "caller"})


if __name__ == "__main__":
    unittest.main()
