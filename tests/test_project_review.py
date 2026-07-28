from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modal_core import ComparisonResult, GeometryMatch, ModalDataset, ModeShape
from project_review import (
    build_manual_pair,
    project_payload,
    read_project,
    write_project,
)


class ProjectReviewTests(unittest.TestCase):
    def test_project_round_trip_preserves_inputs_and_manual_decisions(self):
        payload = project_payload(
            abaqus_path="C:/models/panel.odb",
            experimental_path="C:/tests/panel.unv",
            workspace_path="C:/results/panel",
            abaqus_command="abq2024",
            start_mode=6,
            end_mode=15,
            coordinate_scale="auto",
            manual_reviews={
                "11": {
                    "decision": "unresolved",
                    "experimental_mode": None,
                    "comment": "Needs a curve-fitted Testlab mode.",
                },
                "14": {
                    "decision": "accepted",
                    "experimental_mode": 7,
                    "comment": "Reviewed visually.",
                },
            },
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "panel.amcp.json"
            write_project(path, payload)
            loaded = read_project(path)

        self.assertEqual(loaded["inputs"]["start_mode"], 6)
        self.assertEqual(loaded["inputs"]["end_mode"], 15)
        self.assertEqual(loaded["manual_reviews"]["11"]["decision"], "unresolved")
        self.assertEqual(loaded["manual_reviews"]["14"]["experimental_mode"], 7)
        self.assertEqual(loaded["manual_reviews"]["14"]["comment"], "Reviewed visually.")

    @staticmethod
    def _dataset(name, path, frequencies, scale=1.0):
        node_ids = np.asarray([1, 2, 3, 4], dtype=object)
        coordinates = np.asarray(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 0.0]],
            dtype=float,
        )
        base_shapes = (
            np.asarray([1.0, -1.0, -1.0, 1.0]),
            np.asarray([1.0, 1.0, -1.0, -1.0]),
        )
        modes = []
        for index, frequency in enumerate(frequencies):
            vectors = np.zeros((4, 3), dtype=complex)
            vectors[:, 2] = base_shapes[index] * scale
            mode = ModeShape(
                number=index + 1,
                frequency_hz=frequency,
                node_ids=node_ids,
                coordinates=coordinates,
                vectors=vectors,
                metadata={"measured_dofs": [False, False, True]},
            )
            modes.append(mode)
        return ModalDataset(name, Path(path), modes)

    def test_build_manual_pair_uses_existing_geometry_and_measured_dofs(self):
        abaqus = self._dataset("Abaqus", "a.odb", [10.0, 20.0], scale=1.0e5)
        experimental = self._dataset("Experiment", "e.unv", [10.2, 19.8], scale=1.0e-5)
        geometry = GeometryMatch(
            experimental_to_abaqus=np.asarray([0, 1, 2, 3], dtype=int),
            distances=np.zeros(4),
            transformed_abaqus_coordinates=abaqus.modes[0].coordinates.copy(),
            rotation=np.eye(3),
            coordinate_scale=1.0,
            translation=np.zeros(3),
            normalized_rms_distance=0.0,
            matched_fraction=1.0,
        )
        result = ComparisonResult(
            abaqus=abaqus,
            experimental=experimental,
            geometry=geometry,
            pairs=[],
            mac_matrix=np.zeros((2, 2)),
            frequency_error_matrix=np.zeros((2, 2)),
            abaqus_mode_numbers=[1, 2],
            experimental_mode_numbers=[1, 2],
        )

        pair = build_manual_pair(result, 2, 2)
        self.assertEqual(pair.abaqus_mode, 2)
        self.assertEqual(pair.experimental_mode, 2)
        self.assertAlmostEqual(pair.mac, 1.0, places=12)
        self.assertAlmostEqual(pair.frequency_error_percent, (20.0 - 19.8) / 19.8 * 100.0)
        self.assertEqual(pair.mapped_points, 4)
        self.assertEqual(getattr(pair, "measured_dof_count"), 4)


if __name__ == "__main__":
    unittest.main()
