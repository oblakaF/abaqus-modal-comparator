from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modal_core import ModalDataset, ModeShape, compare_modal_datasets, modal_assurance_criterion
from reporting import export_excel, export_pdf, render_pair_images


class ModalCoreTests(unittest.TestCase):
    def synthetic_result(self):
        x, y = np.meshgrid(np.linspace(0.0, 500.0, 13), np.linspace(0.0, 510.0, 11))
        abaqus_coordinates = np.column_stack((x.ravel(), y.ravel(), np.zeros(x.size)))
        abaqus_ids = np.arange(len(abaqus_coordinates))

        experimental_indices = np.arange(0, len(abaqus_coordinates), 4)
        selected = abaqus_coordinates[experimental_indices]
        true_rotation = np.array(
            [
                [0.0, -1.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0],
            ]
        )
        center = (abaqus_coordinates.min(axis=0) + abaqus_coordinates.max(axis=0)) / 2.0
        experimental_coordinates = (selected - center) @ true_rotation * 0.001 + np.array([2.0, 3.0, 0.0])

        abaqus_modes = []
        experimental_modes = []
        frequencies = [105.0, 148.0, 221.0]
        experimental_order = [1, 2, 3]
        experimental_frequencies = [106.5, 224.0, 150.0]

        for index, frequency in enumerate(frequencies, start=1):
            vectors = np.zeros_like(abaqus_coordinates)
            vectors[:, 2] = (
                np.sin(index * np.pi * abaqus_coordinates[:, 0] / 500.0)
                * np.sin((index + 1) * np.pi * abaqus_coordinates[:, 1] / 510.0)
            )
            abaqus_modes.append(
                ModeShape(
                    number=index + 5,
                    frequency_hz=frequency,
                    node_ids=abaqus_ids,
                    coordinates=abaqus_coordinates,
                    vectors=vectors,
                )
            )
            experimental_modes.append(
                ModeShape(
                    number=experimental_order[index - 1],
                    frequency_hz=experimental_frequencies[index - 1],
                    node_ids=np.arange(len(experimental_indices)),
                    coordinates=experimental_coordinates,
                    vectors=vectors[experimental_indices] @ true_rotation,
                )
            )

        return compare_modal_datasets(
            ModalDataset("Abaqus", Path("model.odb"), abaqus_modes),
            ModalDataset("Testlab", Path("panel.unv"), experimental_modes),
        )

    def test_mac_identical_vectors(self):
        vector = np.array([1.0, -2.0, 3.0, 0.5])
        self.assertAlmostEqual(modal_assurance_criterion(vector, -4.0 * vector), 1.0)

    def test_geometry_alignment_and_mode_matching(self):
        result = self.synthetic_result()
        self.assertGreaterEqual(result.geometry.matched_fraction, 0.95)
        self.assertLess(result.geometry.normalized_rms_distance, 1e-8)
        self.assertEqual(len(result.pairs), 3)
        available_mac = [pair.mac for pair in result.pairs if pair.mac is not None]
        self.assertTrue(available_mac)
        self.assertGreater(min(available_mac), 0.98)
        self.assertTrue(any(pair.order_changed for pair in result.pairs))

    def test_report_generation(self):
        result = self.synthetic_result()
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            render_pair_images(result.pairs[0], directory_path / "images")
            excel_path = export_excel(result, directory_path / "report.xlsx", directory_path / "report_images")
            pdf_path = export_pdf(result, directory_path / "report.pdf", directory_path / "report_images")
            self.assertGreater(excel_path.stat().st_size, 1000)
            self.assertGreater(pdf_path.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
