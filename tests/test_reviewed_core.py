from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modal_core import GeometryMatch, ModalDataset, ModeShape
from reviewed_core import (
    _admissible_assignment,
    _frequency_error_matrices,
    _geometry_warnings_and_transform,
    compare_modal_datasets,
    experimental_measurement_mask,
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
        experimental_mode.measured_dofs = np.zeros_like(
            experimental_vector, dtype=bool
        )
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

    def test_inferred_mask_rejects_tiny_unmeasured_component_noise(self):
        coordinates = np.column_stack(
            (np.arange(5.0), np.zeros(5), np.zeros(5))
        )
        node_ids = np.arange(5)
        vectors = np.zeros((5, 3), dtype=float)
        vectors[:, 0] = 1.0e-9 * np.arange(1.0, 6.0)
        vectors[:, 2] = np.arange(1.0, 6.0)
        mode = ModeShape(1, 10.0, node_ids, coordinates, vectors)
        mask = experimental_measurement_mask([mode], node_ids)
        self.assertFalse(np.any(mask[:, 0]))
        self.assertTrue(np.all(mask[:, 2]))

    def test_assignment_allows_unmatched_without_stealing_valid_partner(self):
        cost = np.array([[0.40, 0.95], [0.39, 0.50]])
        admissible = np.array([[True, False], [False, True]])
        rows, columns, _ = _admissible_assignment(cost, admissible)
        self.assertEqual(
            list(zip(rows.tolist(), columns.tolist())),
            [(0, 0), (1, 1)],
        )

    def test_partial_noisy_geometry_without_modal_correlation_import(self):
        x, y = np.meshgrid(
            np.linspace(0.0, 500.0, 21),
            np.linspace(0.0, 300.0, 13),
        )
        abaqus = np.column_stack((x.ravel(), y.ravel(), np.zeros(x.size)))
        interior = (
            (abaqus[:, 0] >= 50.0)
            & (abaqus[:, 0] <= 450.0)
            & (abaqus[:, 1] >= 30.0)
            & (abaqus[:, 1] <= 270.0)
        )
        selected = abaqus[interior][::7]
        rotation = np.array(
            [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]
        )
        rng = np.random.default_rng(4)
        experiment = (
            selected @ rotation * 0.001
            + np.array([2.0, -1.0, 0.0])
        )
        experiment += rng.normal(scale=2.0e-5, size=experiment.shape)

        candidates = geometry_alignment_candidates(
            abaqus,
            experiment,
            coordinate_scale_override=0.001,
        )
        self.assertTrue(candidates)
        self.assertGreater(candidates[0].matched_fraction, 0.95)
        self.assertLess(candidates[0].normalized_rms_distance, 0.005)
        self.assertTrue(
            all(
                item.transformed_abaqus_coordinates is None
                for item in candidates
            )
        )

    def test_automatic_coordinate_scale_is_covered(self):
        x, y = np.meshgrid(
            np.linspace(0.0, 500.0, 7),
            np.linspace(0.0, 300.0, 5),
        )
        abaqus = np.column_stack((x.ravel(), y.ravel(), np.zeros(x.size)))
        rotation = np.array(
            [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]
        )
        experiment = (
            abaqus @ rotation * 0.001
            + np.array([0.2, -0.4, 0.0])
        )
        candidates = geometry_alignment_candidates(abaqus, experiment)
        self.assertTrue(candidates)
        self.assertAlmostEqual(candidates[0].coordinate_scale, 0.001)
        self.assertLess(candidates[0].normalized_rms_distance, 1.0e-10)

    def test_different_node_sets_between_modes_are_supported(self):
        coordinates = np.array(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [1.0, 1.0, 0.0],
                [0.5, 0.3, 0.0],
                [0.2, 0.8, 0.0],
            ]
        )
        ids = np.arange(1, 7)
        shape_a = np.zeros((6, 3))
        shape_a[:, 2] = np.array([0.0, 1.0, -1.0, 0.0, 0.4, -0.3])
        shape_b = np.zeros((6, 3))
        shape_b[:, 2] = np.array([1.0, -1.0, 1.0, -1.0, 0.2, -0.2])

        abaqus = ModalDataset(
            "Abaqus",
            Path("model.odb"),
            [
                ModeShape(7, 20.0, ids, coordinates, shape_a),
                ModeShape(8, 40.0, ids[:-1], coordinates[:-1], shape_b[:-1]),
            ],
        )
        experiment = ModalDataset(
            "Experiment",
            Path("scan.unv"),
            [
                ModeShape(1, 20.2, ids[:-1], coordinates[:-1], shape_a[:-1]),
                ModeShape(
                    2,
                    39.8,
                    ids[1:],
                    coordinates[1:],
                    2.0 * shape_b[1:],
                ),
            ],
        )
        result = compare_modal_datasets(
            abaqus,
            experiment,
            coordinate_scale_override=1.0,
        )
        self.assertEqual(len(result.pairs), 2)
        self.assertTrue(all(pair.mapped_points >= 4 for pair in result.pairs))

    def test_frequency_error_matrix_is_signed_abaqus_rows_by_experimental_columns(self):
        node_ids = np.arange(4)
        coordinates = np.zeros((4, 3))
        vectors = np.zeros((4, 3))
        abaqus_modes = [
            ModeShape(1, 110.0, node_ids, coordinates, vectors),
            ModeShape(2, 90.0, node_ids, coordinates, vectors),
        ]
        experimental_modes = [ModeShape(1, 100.0, node_ids, coordinates, vectors)]

        signed, absolute = _frequency_error_matrices(abaqus_modes, experimental_modes)

        self.assertEqual(signed.shape, (2, 1))
        self.assertAlmostEqual(signed[0, 0], 10.0)
        self.assertAlmostEqual(signed[1, 0], -10.0)
        np.testing.assert_allclose(absolute, np.abs(signed))

    def test_geometry_warnings_flag_reflection_and_sparse_matched_fraction(self):
        reflection = np.diag([1.0, 1.0, -1.0])
        geometry = GeometryMatch(
            experimental_to_abaqus=np.array([0, 1, 2], dtype=int),
            distances=np.zeros(3),
            rotation=reflection,
            coordinate_scale=1.0,
            translation=np.zeros(3),
            normalized_rms_distance=0.10,
            matched_fraction=0.50,
        )

        warnings, selected_transform = _geometry_warnings_and_transform(geometry)

        self.assertTrue(any("50.0%" in warning for warning in warnings))
        self.assertTrue(any("reflection" in warning for warning in warnings))
        self.assertTrue(any("alignment RMS" in warning for warning in warnings))
        self.assertTrue(selected_transform["mirrored"])
        self.assertAlmostEqual(selected_transform["determinant"], -1.0)
        self.assertEqual(selected_transform["unique_mapped_abaqus_nodes"], 3)

    def test_geometry_warnings_are_empty_for_a_clean_non_reflected_match(self):
        geometry = GeometryMatch(
            experimental_to_abaqus=np.array([0, 1, 2], dtype=int),
            distances=np.zeros(3),
            rotation=np.eye(3),
            coordinate_scale=1.0,
            translation=np.zeros(3),
            normalized_rms_distance=0.001,
            matched_fraction=1.0,
        )

        warnings, selected_transform = _geometry_warnings_and_transform(geometry)

        self.assertEqual(warnings, [])
        self.assertFalse(selected_transform["mirrored"])

    def test_comparison_does_not_mutate_input_metadata(self):
        coordinates = np.array(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [1.0, 1.0, 0.0],
            ]
        )
        ids = np.arange(4)
        vectors = np.zeros((4, 3))
        vectors[:, 2] = [1.0, -1.0, -1.0, 1.0]
        abaqus = ModalDataset(
            "Abaqus",
            Path("model.odb"),
            [ModeShape(7, 30.0, ids, coordinates, vectors)],
            metadata={"source_marker": "unchanged"},
        )
        experiment = ModalDataset(
            "Experiment",
            Path("scan.unv"),
            [ModeShape(1, 30.1, ids, coordinates, vectors)],
        )
        result = compare_modal_datasets(
            abaqus,
            experiment,
            coordinate_scale_override=1.0,
        )
        self.assertEqual(abaqus.metadata, {"source_marker": "unchanged"})
        self.assertIn("selected_geometry_transform", result.abaqus.metadata)
        self.assertIsNotNone(result.geometry.transformed_abaqus_coordinates)


if __name__ == "__main__":
    unittest.main()
