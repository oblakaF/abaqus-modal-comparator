from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modal_core import GeometryMatch, ModalDataset, ModeShape
from reviewed_core import (
    GeometryOrientationAmbiguousError,
    _admissible_assignment,
    _coverage_report,
    _frequency_error_matrices,
    _geometry_warnings_and_transform,
    _select_unambiguous_geometry,
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
        # The fourth corner is nudged off the exact unit square so the point
        # set has exactly one geometrically admissible registration; an
        # exact square is invariant under all 8 axis-permutation/reflection
        # operations, which would make this fixture geometrically ambiguous
        # for a reason unrelated to what this test verifies.
        coordinates = np.array(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [1.15, 0.95, 0.0],
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
        # The interior points are deliberately off the unit square's
        # symmetry lines (not exactly x=0.5 or y=0.5) so the point set has
        # exactly one geometrically admissible registration; a coordinate
        # sitting exactly on a mirror line would make an incorrect
        # reflection candidate register with zero residual too, which is a
        # fixture-symmetry artifact unrelated to what this test verifies.
        coordinates = np.array(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [1.0, 1.0, 0.0],
                [0.55, 0.3, 0.0],
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
        # Fourth corner nudged off the exact unit square -- see the
        # comment in test_pair_uses_only_its_own_experimental_modes_measured_dofs
        # for why an exact square is geometrically ambiguous here.
        coordinates = np.array(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [1.15, 0.95, 0.0],
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
        # A complete, evenly-spaced rectangular grid is invariant under a
        # 180-degree rotation and both axis mirrors regardless of aspect
        # ratio; nudge the far corner off that exact symmetry so the point
        # set has exactly one geometrically admissible registration, for a
        # reason unrelated to what this test verifies. Only unmeasured
        # DOFs of the far corner (never part of either mask below) are
        # affected.
        coordinates[-1] = [2.1, 2.05, 0.0]
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
        # Fourth corner nudged off the exact unit square -- an exact square
        # is invariant under all 8 axis-permutation/reflection operations,
        # which would make this fixture geometrically ambiguous for a
        # reason unrelated to what this test verifies (see the comment in
        # test_pair_uses_only_its_own_experimental_modes_measured_dofs).
        result = compare_modal_datasets(
            ModalDataset(
                "Abaqus",
                Path("model.odb"),
                [ModeShape(1, 100.0, np.arange(4), np.array(
                    [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.15, 0.95, 0.0]]
                ), np.column_stack([np.zeros(4), np.zeros(4), [1.0, -1.0, -1.0, 1.0]]))],
            ),
            ModalDataset(
                "Experiment",
                Path("scan.unv"),
                [ModeShape(1, 100.2, np.arange(4), np.array(
                    [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.15, 0.95, 0.0]]
                ), np.column_stack([np.zeros(4), np.zeros(4), [1.0, -1.0, -1.0, 1.0]]))],
            ),
            coordinate_scale_override=1.0,
        )
        self.assertEqual(len(result.pairs), 1)
        self.assertEqual(getattr(result.pairs[0], "coverage_status"), "accepted")
        self.assertAlmostEqual(getattr(result.pairs[0], "dof_coverage_fraction"), 1.0)
        self.assertAlmostEqual(getattr(result.pairs[0], "point_coverage_fraction"), 1.0)
        self.assertAlmostEqual(getattr(result.pairs[0], "spatial_coverage_fraction"), 1.0)


class GeometryOrientationSelectionTests(unittest.TestCase):
    """Scientific-audit regression tests for finding P0-1: geometry/orientation
    selection must use ONLY geometric evidence and must never be resolved by
    MAC/frequency/modal correlation. See docs/scientific_audit/
    SCIENTIFIC_RISK_REGISTER.md (P0-1) and docs/literature/SCIENTIFIC_RULES.md
    (rule 5)."""

    _SQUARE = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [1.0, 1.0, 0.0],
        ]
    )

    def test_ambiguous_orientation_is_not_resolved_by_a_large_mac_difference(self):
        """An exact unit square is geometrically invariant under all eight
        axis-permutation/reflection candidates (identity, three more
        rotations/reflections, and their four Z-flip duplicates that are
        already collapsed as equivalent). One candidate ('identity') is
        constructed to give a near-perfect MAC and another (a 180-degree,
        point-swap candidate) is constructed to give a much lower MAC. The
        comparator must refuse to pick either -- proving the huge MAC gap
        between orientation candidates was NOT used to break the tie. This
        test fails on the pre-fix implementation (which silently selects
        the high-MAC orientation) and passes after the fix."""
        node_ids = np.arange(1, 5)
        # A strictly increasing shape: identical at every point on both
        # sides gives MAC = 1 for the identity correspondence, but a very
        # different value for the point-swapped (180-degree) correspondence
        # (comparing [1,2,3,4] against [4,3,2,1] is far from collinear).
        shape = np.array([1.0, 2.0, 3.0, 4.0])
        abaqus_vector = np.zeros((4, 3))
        abaqus_vector[:, 2] = shape
        experimental_vector = np.zeros((4, 3))
        experimental_vector[:, 2] = shape

        abaqus = ModalDataset(
            "Abaqus",
            Path("model.odb"),
            [ModeShape(1, 100.0, node_ids, self._SQUARE, abaqus_vector)],
        )
        experiment = ModalDataset(
            "Experiment",
            Path("scan.unv"),
            [ModeShape(1, 100.1, node_ids, self._SQUARE, experimental_vector)],
        )

        # Sanity check: the identity correspondence really does give a much
        # higher MAC than the 180-degree point-swap correspondence, so a
        # MAC-driven selection (the pre-fix bug) would have a strong signal
        # to (wrongly) act on.
        from modal_core import modal_assurance_criterion

        identity_mac = modal_assurance_criterion(shape, shape)
        swapped_mac = modal_assurance_criterion(shape, shape[::-1])
        self.assertGreater(identity_mac, 0.999)
        self.assertLess(swapped_mac, 0.7)

        with self.assertRaises(GeometryOrientationAmbiguousError) as raised:
            compare_modal_datasets(abaqus, experiment, coordinate_scale_override=1.0)
        self.assertGreaterEqual(len(raised.exception.ambiguous_candidates), 2)

    def test_asymmetric_geometry_with_unique_orientation_proceeds_normally(self):
        """A genuinely asymmetric point set (no axis-permutation/reflection
        maps it onto itself) must resolve to a single geometry and proceed
        through the normal pairing pipeline without raising."""
        coordinates = np.array(
            [
                [0.0, 0.0, 0.0],
                [2.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [2.3, 1.4, 0.0],
                [0.6, 0.2, 0.0],
            ]
        )
        node_ids = np.arange(1, 6)
        shape = np.array([1.0, -0.5, 0.3, -0.8, 0.2])
        vectors = np.zeros((5, 3))
        vectors[:, 2] = shape

        abaqus = ModalDataset(
            "Abaqus", Path("model.odb"), [ModeShape(1, 50.0, node_ids, coordinates, vectors)]
        )
        experiment = ModalDataset(
            "Experiment", Path("scan.unv"), [ModeShape(1, 50.1, node_ids, coordinates, vectors)]
        )

        result = compare_modal_datasets(abaqus, experiment, coordinate_scale_override=1.0)
        self.assertEqual(len(result.pairs), 1)
        self.assertGreater(result.pairs[0].mac, 0.999)

    def test_geometry_selection_is_independent_of_modal_vectors(self):
        """Changing the modal vectors while keeping geometry identical must
        not change which geometry is selected -- geometry selection depends
        only on coordinates, never on mode shapes."""
        coordinates = np.array(
            [
                [0.0, 0.0, 0.0],
                [2.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [2.3, 1.4, 0.0],
                [0.6, 0.2, 0.0],
            ]
        )
        candidates = geometry_alignment_candidates(
            coordinates, coordinates, coordinate_scale_override=1.0
        )
        geometry_a = _select_unambiguous_geometry(candidates)

        # Re-running geometry selection against the very same coordinate
        # candidates (mode-shape data never enters geometry_alignment_candidates
        # or _select_unambiguous_geometry at all) must reproduce the identical
        # transform -- this is the structural guarantee that no modal
        # quantity could have influenced the outcome.
        candidates_again = geometry_alignment_candidates(
            coordinates, coordinates, coordinate_scale_override=1.0
        )
        geometry_b = _select_unambiguous_geometry(candidates_again)

        np.testing.assert_array_equal(
            geometry_a.experimental_to_abaqus, geometry_b.experimental_to_abaqus
        )
        np.testing.assert_array_equal(geometry_a.rotation, geometry_b.rotation)

        # And end-to-end: two comparisons over the same geometry with
        # completely different, unrelated mode shapes must select the same
        # geometry transform.
        node_ids = np.arange(1, 6)
        vectors_1 = np.zeros((5, 3))
        vectors_1[:, 2] = np.array([1.0, -0.5, 0.3, -0.8, 0.2])
        vectors_2 = np.zeros((5, 3))
        vectors_2[:, 0] = np.array([-2.0, 4.0, 0.1, -3.0, 5.0])

        result_1 = compare_modal_datasets(
            ModalDataset("Abaqus", Path("model.odb"), [ModeShape(1, 50.0, node_ids, coordinates, vectors_1)]),
            ModalDataset("Experiment", Path("scan.unv"), [ModeShape(1, 50.1, node_ids, coordinates, vectors_1)]),
            coordinate_scale_override=1.0,
        )
        result_2 = compare_modal_datasets(
            ModalDataset("Abaqus", Path("model.odb"), [ModeShape(1, 50.0, node_ids, coordinates, vectors_2)]),
            ModalDataset("Experiment", Path("scan.unv"), [ModeShape(1, 50.1, node_ids, coordinates, vectors_2)]),
            coordinate_scale_override=1.0,
        )
        np.testing.assert_array_equal(
            result_1.geometry.experimental_to_abaqus,
            result_2.geometry.experimental_to_abaqus,
        )
        np.testing.assert_array_equal(result_1.geometry.rotation, result_2.geometry.rotation)

    def test_unresolved_orientation_raises_instead_of_an_arbitrary_mapping(self):
        """When geometry alone cannot determine orientation, the comparator
        must raise an explicit diagnostic (never silently return a
        ComparisonResult built on an arbitrarily chosen candidate)."""
        node_ids = np.arange(1, 5)
        vectors = np.zeros((4, 3))
        vectors[:, 2] = [1.0, -1.0, 0.5, -0.5]

        abaqus = ModalDataset(
            "Abaqus", Path("model.odb"), [ModeShape(1, 100.0, node_ids, self._SQUARE, vectors)]
        )
        experiment = ModalDataset(
            "Experiment", Path("scan.unv"), [ModeShape(1, 100.1, node_ids, self._SQUARE, vectors)]
        )

        with self.assertRaises(GeometryOrientationAmbiguousError):
            compare_modal_datasets(abaqus, experiment, coordinate_scale_override=1.0)

        # The exception must carry enough geometry-only detail (no MAC or
        # frequency information) for a caller to present the ambiguity.
        try:
            compare_modal_datasets(abaqus, experiment, coordinate_scale_override=1.0)
            self.fail("Expected GeometryOrientationAmbiguousError")
        except GeometryOrientationAmbiguousError as error:
            self.assertGreaterEqual(len(error.ambiguous_candidates), 2)
            for candidate in error.ambiguous_candidates:
                self.assertIn("rotation", candidate)
                self.assertIn("normalized_rms_distance", candidate)
                self.assertIn("matched_fraction", candidate)
                self.assertNotIn("mac", candidate)

    def test_user_confirmed_geometry_candidate_is_applied_without_modal_selection(self):
        node_ids = np.arange(1, 5)
        vectors = np.zeros((4, 3))
        vectors[:, 2] = [1.0, -1.0, 0.5, -0.5]
        abaqus = ModalDataset(
            "Abaqus", Path("model.odb"),
            [ModeShape(1, 100.0, node_ids, self._SQUARE, vectors)],
        )
        experiment = ModalDataset(
            "Experiment", Path("scan.unv"),
            [ModeShape(1, 100.1, node_ids, self._SQUARE, vectors)],
        )

        with self.assertRaises(GeometryOrientationAmbiguousError) as raised:
            compare_modal_datasets(abaqus, experiment, coordinate_scale_override=1.0)
        candidate = raised.exception.ambiguous_candidates[0]
        self.assertIn("candidate_id", candidate)
        self.assertIn("translation", candidate)

        result = compare_modal_datasets(
            abaqus,
            experiment,
            coordinate_scale_override=1.0,
            orientation_selection=candidate,
        )
        self.assertEqual(result.metadata["orientation_source"], "user_confirmed")
        self.assertEqual(
            result.metadata["selected_geometry_transform"]["orientation_source"],
            "user_confirmed",
        )
        np.testing.assert_allclose(result.geometry.rotation, candidate["rotation"])
        np.testing.assert_allclose(result.geometry.translation, candidate["translation"])

    def test_obsolete_manual_candidate_does_not_weaken_ambiguity_stop(self):
        node_ids = np.arange(1, 5)
        vectors = np.zeros((4, 3))
        vectors[:, 2] = [1.0, -1.0, 0.5, -0.5]
        abaqus = ModalDataset(
            "Abaqus", Path("model.odb"),
            [ModeShape(1, 100.0, node_ids, self._SQUARE, vectors)],
        )
        experiment = ModalDataset(
            "Experiment", Path("scan.unv"),
            [ModeShape(1, 100.1, node_ids, self._SQUARE, vectors)],
        )
        with self.assertRaises(GeometryOrientationAmbiguousError):
            compare_modal_datasets(
                abaqus,
                experiment,
                coordinate_scale_override=1.0,
                orientation_selection={"candidate_id": "geometry-obsolete"},
            )


if __name__ == "__main__":
    unittest.main()
