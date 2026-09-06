from copy import deepcopy
from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain import InclusionStatus, ModalCluster
from modal_core import ComparisonResult, GeometryMatch, ModalDataset, ModePairResult
from services import cluster_comparison_result, subspace_mac


def mode_vector(values):
    result = np.zeros((len(values), 3), dtype=complex)
    result[:, 0] = values
    return result


def make_pair(
    fe_mode,
    experimental_mode,
    fe_frequency,
    experimental_frequency,
    fe_vector,
    experimental_vector,
):
    pair = ModePairResult(
        abaqus_mode=fe_mode,
        experimental_mode=experimental_mode,
        abaqus_frequency_hz=fe_frequency,
        experimental_frequency_hz=experimental_frequency,
        frequency_error_percent=(fe_frequency - experimental_frequency)
        / experimental_frequency
        * 100.0,
        mac=0.95,
        status="Excellent match",
        order_changed=False,
        mapped_points=len(fe_vector),
        abaqus_vector=mode_vector(fe_vector),
        experimental_vector=mode_vector(experimental_vector),
        coordinates=np.column_stack(
            (np.arange(len(fe_vector), dtype=float), np.zeros((len(fe_vector), 2)))
        ),
        node_ids=np.arange(1, len(fe_vector) + 1),
    )
    pair.measured_dof_mask = np.column_stack(
        (
            np.ones(len(fe_vector), dtype=bool),
            np.zeros((len(fe_vector), 2), dtype=bool),
        )
    )
    return pair


def make_comparison(pairs):
    dataset = ModalDataset("fixture", Path("fixture.unv"), [])
    return ComparisonResult(
        abaqus=dataset,
        experimental=dataset,
        geometry=GeometryMatch(
            experimental_to_abaqus=np.arange(3),
            distances=np.zeros(3),
            rotation=np.eye(3),
            coordinate_scale=1.0,
            translation=np.zeros(3),
            normalized_rms_distance=0.0,
            matched_fraction=1.0,
        ),
        pairs=list(pairs),
        mac_matrix=np.eye(len(pairs)),
        frequency_error_matrix=np.zeros((len(pairs), len(pairs))),
        abaqus_mode_numbers=[pair.abaqus_mode for pair in pairs],
        experimental_mode_numbers=[pair.experimental_mode for pair in pairs],
        warnings=["fixture warning"],
        metadata={"fixture": {"unchanged": True}},
    )


class SubspaceMacTests(unittest.TestCase):
    def setUp(self):
        self.phi = np.array(
            [[1.0, 0.0], [0.0, 1.0], [0.0, 0.0], [0.0, 0.0]]
        )

    def test_identical_subspace_is_invariant_to_permutation_and_sign(self):
        transformed = self.phi[:, [1, 0]] @ np.diag([-3.0, 2.0])
        self.assertAlmostEqual(subspace_mac(self.phi, transformed), 1.0)

    def test_identical_subspace_is_invariant_to_basis_rotation(self):
        angle = 0.37
        rotation = np.array(
            [[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]]
        )
        self.assertAlmostEqual(subspace_mac(self.phi, self.phi @ rotation), 1.0)

    def test_complex_subspace_is_invariant_to_unitary_basis_change(self):
        unitary = np.array(
            [[1.0, 1.0j], [1.0j, 1.0]], dtype=complex
        ) / np.sqrt(2.0)
        complex_basis = self.phi.astype(complex)
        self.assertAlmostEqual(
            subspace_mac(complex_basis, complex_basis @ unitary), 1.0
        )

    def test_orthogonal_subspaces_have_zero_correlation(self):
        psi = np.array(
            [[0.0, 0.0], [0.0, 0.0], [1.0, 0.0], [0.0, 1.0]]
        )
        self.assertAlmostEqual(subspace_mac(self.phi, psi), 0.0)

    def test_partial_overlap_has_intermediate_correlation(self):
        psi = np.array(
            [[1.0, 0.0], [0.0, 0.0], [0.0, 1.0], [0.0, 0.0]]
        )
        self.assertAlmostEqual(subspace_mac(self.phi, psi), 0.5)

    def test_incomplete_cluster_is_not_accepted_when_subspace_mac_is_one(self):
        diagnostic_mac = subspace_mac(self.phi, self.phi[:, :1])
        cluster = ModalCluster(
            "incomplete-cluster",
            "SP-02",
            "run-1",
            ("obs-1", "obs-2"),
            fe_mode_ids=(2, 3),
            experimental_mode_ids=(7,),
            fe_frequencies_hz=(100.0, 102.0),
            experimental_frequencies_hz=(101.0,),
            subspace_mac=diagnostic_mac,
        )

        self.assertAlmostEqual(cluster.subspace_mac, 1.0)
        self.assertEqual(cluster.inclusion_status, InclusionStatus.EXCLUDED)
        self.assertIn("Incomplete modal cluster", cluster.reason)
        self.assertIn("manual review", cluster.reason)


class ModalClusterServiceTests(unittest.TestCase):
    def close_pairs(self):
        angle = 0.61
        return [
            make_pair(
                2,
                7,
                100.0,
                99.0,
                [1.0, 0.0, 0.0],
                [np.cos(angle), np.sin(angle), 0.0],
            ),
            make_pair(
                3,
                8,
                102.0,
                101.0,
                [0.0, 1.0, 0.0],
                [-np.sin(angle), np.cos(angle), 0.0],
            ),
        ]

    def analyze(self, pairs, threshold=0.03):
        return cluster_comparison_result(
            make_comparison(pairs),
            "design-A",
            "SP-02",
            "run-1",
            relative_frequency_gap=threshold,
        )

    def test_simple_mode_remains_an_observation_without_a_cluster(self):
        pair = make_pair(2, 7, 100.0, 99.0, [1, 0, 0], [1, 0, 0])
        result = self.analyze([pair])
        self.assertEqual(len(result.observations), 1)
        self.assertEqual(result.clusters, ())
        self.assertEqual(result.effective_observation_count, 1)

    def test_automatic_detection_is_disabled_without_an_explicit_threshold(self):
        result = cluster_comparison_result(
            make_comparison(self.close_pairs()), "design-A", "SP-02", "run-1"
        )
        self.assertEqual(result.clusters, ())
        self.assertEqual(result.effective_observation_count, 2)

    def test_two_close_modes_form_one_cluster_with_required_diagnostics(self):
        result = self.analyze(self.close_pairs())
        self.assertEqual(len(result.clusters), 1)
        cluster = result.clusters[0]
        self.assertEqual(cluster.cluster_size, 2)
        self.assertEqual(cluster.effective_observation_count, 1)
        self.assertEqual(cluster.fe_mode_ids, (2, 3))
        self.assertEqual(cluster.experimental_mode_ids, (7, 8))
        self.assertEqual(cluster.fe_frequencies_hz, (100.0, 102.0))
        self.assertEqual(cluster.experimental_frequencies_hz, (99.0, 101.0))
        self.assertAlmostEqual(cluster.subspace_mac, 1.0)
        self.assertAlmostEqual(cluster.fe_frequency_splitting_hz, 2.0)
        self.assertAlmostEqual(cluster.experimental_frequency_splitting_hz, 2.0)
        self.assertEqual(cluster.inclusion_status, InclusionStatus.INCLUDED)
        self.assertTrue(cluster.reason)

    def test_two_distant_modes_do_not_form_a_cluster(self):
        pairs = self.close_pairs()
        pairs[1].abaqus_frequency_hz = 110.0
        pairs[1].experimental_frequency_hz = 111.0
        result = self.analyze(pairs)
        self.assertEqual(result.clusters, ())
        self.assertEqual(result.effective_observation_count, 2)

    def test_cluster_result_is_invariant_to_member_pairing_permutation(self):
        original_pairs = self.close_pairs()
        original = self.analyze(original_pairs).clusters[0]

        swapped_pairs = self.close_pairs()
        first_experimental_vector = swapped_pairs[0].experimental_vector.copy()
        first_experimental_frequency = swapped_pairs[0].experimental_frequency_hz
        first_experimental_mode = swapped_pairs[0].experimental_mode
        swapped_pairs[0].experimental_vector = swapped_pairs[1].experimental_vector.copy()
        swapped_pairs[0].experimental_frequency_hz = swapped_pairs[1].experimental_frequency_hz
        swapped_pairs[0].experimental_mode = swapped_pairs[1].experimental_mode
        swapped_pairs[1].experimental_vector = first_experimental_vector
        swapped_pairs[1].experimental_frequency_hz = first_experimental_frequency
        swapped_pairs[1].experimental_mode = first_experimental_mode
        swapped = self.analyze(list(reversed(swapped_pairs))).clusters[0]

        self.assertAlmostEqual(swapped.subspace_mac, original.subspace_mac)
        self.assertAlmostEqual(swapped.frequency_residual, original.frequency_residual)
        self.assertEqual(set(swapped.fe_mode_ids), set(original.fe_mode_ids))
        self.assertEqual(
            set(swapped.experimental_mode_ids), set(original.experimental_mode_ids)
        )

    def test_cluster_residual_is_invariant_to_member_order(self):
        forward = self.analyze(self.close_pairs()).clusters[0]
        reverse = self.analyze(list(reversed(self.close_pairs()))).clusters[0]
        expected = 0.5 * (np.log(100.0 / 99.0) + np.log(102.0 / 101.0))
        self.assertAlmostEqual(forward.frequency_residual, expected)
        self.assertAlmostEqual(reverse.frequency_residual, expected)

    def test_source_comparison_is_not_mutated(self):
        comparison = make_comparison(self.close_pairs())
        pair_snapshots = [deepcopy(vars(pair)) for pair in comparison.pairs]
        matrix_snapshot = comparison.mac_matrix.copy()
        metadata_snapshot = deepcopy(comparison.metadata)

        cluster_comparison_result(
            comparison,
            "design-A",
            "SP-02",
            "run-1",
            relative_frequency_gap=0.03,
        )

        np.testing.assert_array_equal(comparison.mac_matrix, matrix_snapshot)
        self.assertEqual(comparison.metadata, metadata_snapshot)
        for pair, snapshot in zip(comparison.pairs, pair_snapshots):
            self.assertEqual(vars(pair).keys(), snapshot.keys())
            for name, original in snapshot.items():
                current = getattr(pair, name)
                if isinstance(original, np.ndarray):
                    np.testing.assert_array_equal(current, original)
                else:
                    self.assertEqual(current, original)


if __name__ == "__main__":
    unittest.main()
