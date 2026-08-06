from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modal_core import GeometryMatch, ModalDataset, ModeShape
from reviewed_core import (
    _admissible_assignment,
    _coverage_report,
    _frequency_error_matrices,
    _geometry_warnings_and_transform,
    compare_modal_datasets,
    experimental_measurement_masks,
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
        masks = experimental_measurement_masks([mode], node_ids)
        self.assertEqual(len(masks), 1)
        mask = masks[0]
        self.assertFalse(np.any(mask[:, 0]))
        self.assertTrue(np.all(mask[:, 2]))

    def test_all_zero_mode_without_explicit_mask_is_not_treated_as_fully_measured(self):
        """A mode with zero energy everywhere and no explicit measured_dofs
        has no reliable basis for saying anything was measured; it must not
        default to 'every finite DOF counts as measured' (ROADMAP Stage 2
        #3 legacy-fallback fix)."""
        coordinates = np.column_stack((np.arange(5.0), np.zeros(5), np.zeros(5)))
        node_ids = np.arange(5)
        vectors = np.zeros((5, 3), dtype=float)  # all zero, finite everywhere
        mode = ModeShape(1, 10.0, node_ids, coordinates, vectors)
        masks = experimental_measurement_masks([mode], node_ids)
        self.assertFalse(np.any(masks[0]))

    def test_inferred_mask_is_computed_per_mode_not_from_other_modes_energy(self):
        """ROADMAP Stage 2 #3 inferred-mask fallback: a component active in one
        mode's own vector must not make another, genuinely-inactive mode's
        same component read as measured."""
        coordinates = np.column_stack((np.arange(5.0), np.zeros(5), np.zeros(5)))
        node_ids = np.arange(5)
        active_in_x = np.zeros((5, 3), dtype=float)
        active_in_x[:, 0] = np.arange(1.0, 6.0)
        inactive_in_x = np.zeros((5, 3), dtype=float)
        inactive_in_x[:, 2] = np.arange(1.0, 6.0)

        mode_with_x = ModeShape(1, 10.0, node_ids, coordinates, active_in_x)
        mode_without_x = ModeShape(2, 20.0, node_ids, coordinates, inactive_in_x)
        masks = experimental_measurement_masks([mode_with_x, mode_without_x], node_ids)

        self.assertTrue(np.all(masks[0][:, 0]))
        # mode_without_x has zero energy in X; inferring from its own vector
        # alone must leave X unmeasured, even though mode_with_x measured X.
        self.assertFalse(np.any(masks[1][:, 0]))

    def test_pair_uses_only_its_own_experimental_modes_measured_dofs(self):
        """ROADMAP Stage 2 #3: a channel measured only in one experimental mode
        must not be treated as measured for a different experimental mode's
        pair. Reproduces the confirmed union-mask risk described in
        ROADMAP.md Stage 2 #3."""
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
        # Deliberately near-zero correlation with abaqus_x, so if X ever leaks
        # into experimental mode 1's pair (which never measured X), the MAC
        # visibly collapses instead of coincidentally staying high.
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
        experimental_mode_1.measured_dofs[:, 2] = True

        experimental_vector_2 = np.zeros((4, 3))
        experimental_vector_2[:, 0] = abaqus_x
        experimental_mode_2 = ModeShape(
            2, 200.5, node_ids, coordinates, experimental_vector_2
        )
        experimental_mode_2.measured_dofs = np.zeros((4, 3), dtype=bool)
        experimental_mode_2.measured_dofs[:, 0] = True

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

        result = compare_modal_datasets(
            abaqus, experiment, coordinate_scale_override=1.0
        )
        self.assertEqual(len(result.pairs), 2)
        pair_1 = next(p for p in result.pairs if p.experimental_mode == 1)
        pair_2 = next(p for p in result.pairs if p.experimental_mode == 2)

        # Pair 1 must be scored only on Z (experimental mode 1's own measured
        # DOF), not on X, even though experimental mode 2 measured X.
        self.assertGreater(pair_1.mac, 0.999)
        self.assertFalse(np.any(pair_1.measured_dof_mask[:, 0]))

        # Pair 2 must be scored only on X (measured only in experimental mode
        # 2), not on Z.
        self.assertGreater(pair_2.mac, 0.999)
        self.assertFalse(np.any(pair_2.measured_dof_mask[:, 2]))

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

    def test_coverage_report_status_thresholds(self):
        """ROADMAP Stage 2 #4: unit-level check of the soft coverage-gate
        status transitions (see reviewed_core.py's module-level comment on
        why these thresholds are a sanity floor, not a calibrated cutoff)."""
        coordinates = np.column_stack((np.arange(10.0), np.zeros(10), np.zeros(10)))
        full_grid_point_count = 10
        full_grid_extent = float(
            np.linalg.norm(coordinates.max(axis=0) - coordinates.min(axis=0))
        )

        # Plenty of DOF, points, and spread: accepted.
        mask = np.zeros((10, 3), dtype=bool)
        mask[:, 2] = True
        report = _coverage_report(mask, 10, coordinates, full_grid_point_count, full_grid_extent)
        self.assertEqual(report.status, "accepted")

        # Only 2 DOF true: below MINIMUM_COMMON_DOF_COUNT.
        mask_low_dof = np.zeros((10, 3), dtype=bool)
        mask_low_dof[0:2, 2] = True
        report = _coverage_report(
            mask_low_dof, 10, coordinates, full_grid_point_count, full_grid_extent
        )
        self.assertEqual(report.status, "insufficient DOF coverage")

        # Enough DOF (all 3 components at 2 points = 6), but only 2 unique
        # points: below MINIMUM_UNIQUE_POINT_COUNT.
        mask_low_points = np.zeros((10, 3), dtype=bool)
        mask_low_points[0:2, :] = True
        report = _coverage_report(
            mask_low_points, 10, coordinates, full_grid_point_count, full_grid_extent
        )
        self.assertEqual(report.status, "insufficient point coverage")

        # Enough DOF and points, but all measured points sit at the same
        # location: zero spatial extent.
        clustered_coordinates = coordinates.copy()
        clustered_coordinates[0:3] = coordinates[0]
        mask_clustered = np.zeros((10, 3), dtype=bool)
        mask_clustered[0:3, :] = True
        report = _coverage_report(
            mask_clustered, 10, clustered_coordinates, full_grid_point_count, full_grid_extent
        )
        self.assertEqual(report.status, "insufficient spatial coverage")

    def test_insufficient_coverage_pair_is_not_assigned(self):
        """A candidate pair with genuinely insufficient coverage must not be
        admitted into Hungarian assignment, even if its MAC/frequency would
        otherwise be admissible (ROADMAP Stage 2 #4)."""
        x, y = np.meshgrid(np.linspace(0.0, 2.0, 3), np.linspace(0.0, 2.0, 3))
        coordinates = np.column_stack((x.ravel(), y.ravel(), np.zeros(x.size)))
        node_ids = np.arange(1, 10)

        shape_1 = np.sin(np.pi * coordinates[:, 0] / 2.0)
        shape_2 = np.cos(np.pi * coordinates[:, 1] / 2.0)

        abaqus_vector_1 = np.zeros((9, 3))
        abaqus_vector_1[:, 2] = shape_1
        abaqus_vector_2 = np.zeros((9, 3))
        abaqus_vector_2[:, 2] = shape_2
        abaqus = ModalDataset(
            "Abaqus",
            Path("model.odb"),
            [
                ModeShape(1, 100.0, node_ids, coordinates, abaqus_vector_1),
                ModeShape(2, 200.0, node_ids, coordinates, abaqus_vector_2),
            ],
        )

        experimental_vector_1 = np.zeros((9, 3))
        experimental_vector_1[:, 2] = shape_1
        experimental_mode_1 = ModeShape(
            1, 100.2, node_ids, coordinates, experimental_vector_1
        )
        experimental_mode_1.measured_dofs = np.zeros((9, 3), dtype=bool)
        experimental_mode_1.measured_dofs[:, 2] = True  # full coverage

        experimental_vector_2 = np.zeros((9, 3))
        experimental_vector_2[:, 2] = shape_2
        experimental_mode_2 = ModeShape(
            2, 200.2, node_ids, coordinates, experimental_vector_2
        )
        experimental_mode_2.measured_dofs = np.zeros((9, 3), dtype=bool)
        # Only 2 of 9 points measured: below MINIMUM_UNIQUE_POINT_COUNT (3),
        # even though its shape would otherwise match abaqus mode 2 well.
        experimental_mode_2.measured_dofs[0:2, 2] = True

        experiment = ModalDataset(
            "Experiment",
            Path("scan.unv"),
            [experimental_mode_1, experimental_mode_2],
        )

        result = compare_modal_datasets(
            abaqus, experiment, coordinate_scale_override=1.0
        )

        self.assertEqual(len(result.pairs), 1)
        self.assertEqual(result.pairs[0].experimental_mode, 1)
        self.assertEqual(result.pairs[0].abaqus_mode, 1)
        self.assertEqual(getattr(result.pairs[0], "coverage_status"), "accepted")

    def test_sufficient_coverage_pair_reports_accepted_status(self):
        result = compare_modal_datasets(
            ModalDataset(
                "Abaqus",
                Path("model.odb"),
                [ModeShape(1, 100.0, np.arange(4), np.array(
                    [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 0.0]]
                ), np.column_stack([np.zeros(4), np.zeros(4), [1.0, -1.0, -1.0, 1.0]]))],
            ),
            ModalDataset(
                "Experiment",
                Path("scan.unv"),
                [ModeShape(1, 100.2, np.arange(4), np.array(
                    [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 0.0]]
                ), np.column_stack([np.zeros(4), np.zeros(4), [1.0, -1.0, -1.0, 1.0]]))],
            ),
            coordinate_scale_override=1.0,
        )
        self.assertEqual(len(result.pairs), 1)
        self.assertEqual(getattr(result.pairs[0], "coverage_status"), "accepted")
        self.assertAlmostEqual(getattr(result.pairs[0], "dof_coverage_fraction"), 1.0)
        self.assertAlmostEqual(getattr(result.pairs[0], "point_coverage_fraction"), 1.0)
        self.assertAlmostEqual(getattr(result.pairs[0], "spatial_coverage_fraction"), 1.0)


if __name__ == "__main__":
    unittest.main()
