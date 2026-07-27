from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from enhanced_reporting import (
    quality_control_text,
    render_frf_diagnostics,
    render_verified_mac_matrix,
)
from modal_core import ModalDataset, ModeShape
from quality_control import compare_modal_datasets_with_quality_control


class EnhancedReportingTests(unittest.TestCase):
    def make_result(self):
        x, y = np.meshgrid(np.linspace(0.0, 1.0, 6), np.linspace(0.0, 1.0, 6))
        coordinates = np.column_stack((x.ravel(), y.ravel(), np.zeros(x.size)))
        node_ids = np.arange(1, len(coordinates) + 1)

        shapes = []
        for order in (1, 2):
            vectors = np.zeros_like(coordinates)
            vectors[:, 2] = np.sin(order * np.pi * coordinates[:, 0]) * np.sin(
                np.pi * coordinates[:, 1]
            )
            shapes.append(vectors)

        abaqus = ModalDataset(
            "Abaqus",
            Path("model.odb"),
            [
                ModeShape(7, 25.0, node_ids, coordinates, shapes[0]),
                ModeShape(8, 75.0, node_ids, coordinates, shapes[1]),
            ],
        )
        frequency = np.linspace(1.0, 120.0, 600)
        indicator = (
            1.0 / np.sqrt((25.0**2 - frequency**2) ** 2 + (0.5 * frequency) ** 2)
            + 0.6
            / np.sqrt((75.0**2 - frequency**2) ** 2 + (0.8 * frequency) ** 2)
        )
        experiment = ModalDataset(
            "Experiment",
            Path("scan.unv"),
            [
                ModeShape(1, 25.2, node_ids, coordinates, shapes[0]),
                ModeShape(2, 74.6, node_ids, coordinates, shapes[1]),
            ],
            metadata={
                "_frf_frequency_hz": frequency.tolist(),
                "_frf_indicator": indicator.tolist(),
                "_frf_mean_coherence": np.full_like(frequency, 0.95).tolist(),
            },
        )
        return compare_modal_datasets_with_quality_control(abaqus, experiment)

    def test_frf_and_verified_mac_images(self):
        result = self.make_result()
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            frf = render_frf_diagnostics(result, directory / "frf.png")
            matrix = render_verified_mac_matrix(result, directory / "verified.png")
            self.assertGreater(frf.stat().st_size, 1000)
            self.assertGreater(matrix.stat().st_size, 1000)

    def test_quality_summary_contains_decisions(self):
        text = quality_control_text(self.make_result())
        self.assertIn("Reliable matched pairs: 2", text)
        self.assertIn("Unmatched Abaqus modes: none", text)
        self.assertIn("Accepted-pair limits", text)


if __name__ == "__main__":
    unittest.main()
