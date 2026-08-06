from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modal_core import ModalDataset, ModeShape
from quality_control_reviewed import (
    _rigid_body_residual_fraction,
    compare_modal_datasets_with_quality_control,
)


class QualityControlTests(unittest.TestCase):
    def test_rigid_shape_and_forced_remote_pair_are_removed(self):
        x, y = np.meshgrid(
            np.linspace(0.0, 1.0, 5),
            np.linspace(0.0, 1.0, 5),
        )
        coordinates = np.column_stack(
            (x.ravel(), y.ravel(), np.zeros(x.size))
        )
        node_ids = np.arange(1, len(coordinates) + 1)

        rigid_translation = np.zeros_like(coordinates)
        rigid_translation[:, 0] = 1.0
        shape_1 = np.zeros_like(coordinates)
        shape_1[:, 2] = (
            np.sin(np.pi * coordinates[:, 0])
            * np.sin(np.pi * coordinates[:, 1])
        )
        shape_2 = np.zeros_like(coordinates)
        shape_2[:, 2] = (
            np.sin(2.0 * np.pi * coordinates[:, 0])
            * np.sin(np.pi * coordinates[:, 1])
        )
        shape_3 = np.zeros_like(coordinates)
        shape_3[:, 2] = (
            np.sin(np.pi * coordinates[:, 0])
            * np.sin(2.0 * np.pi * coordinates[:, 1])
        )

        self.assertLess(
            _rigid_body_residual_fraction(
                ModeShape(
                    6,
                    0.0094,
                    node_ids,
                    coordinates,
                    rigid_translation,
                )
            ),
            1.0e-10,
        )
        self.assertGreater(
            _rigid_body_residual_fraction(
                ModeShape(7, 25.0, node_ids, coordinates, shape_1)
            ),
            0.1,
        )

        abaqus = ModalDataset(
            "Abaqus",
            Path("model.odb"),
            [
                ModeShape(
                    6,
                    0.0094,
                    node_ids,
                    coordinates,
                    rigid_translation,
                ),
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
                ModeShape(2, 60.0, node_ids, coordinates, shape_1 + shape_2),
                ModeShape(3, 89.8, node_ids, coordinates, shape_2),
                ModeShape(4, 220.0, node_ids, coordinates, shape_1),
            ],
        )

        result = compare_modal_datasets_with_quality_control(
            abaqus,
            experiment,
        )

        self.assertEqual(
            [pair.abaqus_mode for pair in result.pairs],
            [7, 8],
        )
        self.assertEqual(
            [pair.experimental_mode for pair in result.pairs],
            [1, 3],
        )
        self.assertTrue(all(not pair.order_changed for pair in result.pairs))
        self.assertIn(
            6,
            result.abaqus.metadata["quality_control"][
                "excluded_abaqus_modes"
            ],
        )
        unmatched_numbers = [
            item["mode"]
            for item in result.abaqus.metadata[
                "unmatched_abaqus_modes"
            ]
        ]
        self.assertIn(9, unmatched_numbers)
        unmatched_experimental = [
            item["mode"]
            for item in result.abaqus.metadata[
                "unmatched_experimental_candidates"
            ]
        ]
        self.assertIn(2, unmatched_experimental)
        close_groups = result.abaqus.metadata[
            "close_abaqus_mode_groups"
        ]
        self.assertTrue(
            any(
                {8, 9}.issubset(
                    {item["mode"] for item in group}
                )
                for group in close_groups
            )
        )
        self.assertTrue(
            any("rigid-body" in warning for warning in result.warnings)
        )
        self.assertTrue(
            any("No admissible" in warning for warning in result.warnings)
        )
        self.assertTrue(
            any(
                "Experimental mode candidate" in warning
                for warning in result.warnings
            )
        )
        self.assertTrue(
            any("Closely spaced" in warning for warning in result.warnings)
        )

    def test_frf_modes_without_computed_coherence_raise_a_visible_warning(self):
        """ROADMAP Stage 2 #1: missing coherence must be visible in the
        aggregated ComparisonResult.warnings list, which reaches the GUI,
        Excel export, and PDF export alike."""
        x, y = np.meshgrid(np.linspace(0.0, 1.0, 5), np.linspace(0.0, 1.0, 5))
        coordinates = np.column_stack((x.ravel(), y.ravel(), np.zeros(x.size)))
        node_ids = np.arange(1, len(coordinates) + 1)
        shape = np.zeros_like(coordinates)
        shape[:, 2] = np.sin(np.pi * coordinates[:, 0]) * np.sin(np.pi * coordinates[:, 1])

        abaqus = ModalDataset(
            "Abaqus", Path("model.odb"), [ModeShape(1, 25.0, node_ids, coordinates, shape)]
        )
        experiment = ModalDataset(
            "Experiment",
            Path("scan.unv"),
            [
                ModeShape(
                    1,
                    25.2,
                    node_ids,
                    coordinates,
                    shape,
                    metadata={
                        "dataset_type": 58,
                        "mode_source": "FRF peak-derived experimental shape",
                        "mean_coherence": None,
                        "coherence_status": "unavailable",
                    },
                )
            ],
        )

        result = compare_modal_datasets_with_quality_control(abaqus, experiment)

        self.assertTrue(
            any(
                "no measured coherence" in warning
                for warning in result.warnings
            )
        )


if __name__ == "__main__":
    unittest.main()
