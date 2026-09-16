"""ROADMAP Stage 2 #2: a real multi-reference FRF/CMIF path.

Current confirmed risk (see ROADMAP.md): universal_hardening._safe_select_frf_group
groups FRF response channels by (frequency-axis signature, ref_node, ref_dir, ...)
and then returns only the single best-scoring group, so cmif_separation._build_frf_block
never sees more than one reference; _FrfBlock.reference_count is consequently always 1
and the "multi-reference CMIF-compatible SVD" label in _reviewed_modes_from_frf's
close_mode_separation metadata never actually triggers. Channels were also keyed only
by (response_node, response_direction), with no way to represent more than one
reference for the same response DOF.

These tests target cmif_separation._build_multi_reference_frf_block, which does not
exist yet: they are expected to fail until it is implemented.
"""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from universal_hardening import install_universal_hardening

install_universal_hardening()

import cmif_separation  # noqa: E402  (import after install_universal_hardening)
from cmif_validation import validate_close_mode_candidates  # noqa: E402
from modal_core import ModeShape  # noqa: E402


def _grid_geometry(n=3):
    x, y = np.meshgrid(np.linspace(-0.2, 0.2, n), np.linspace(-0.2, 0.2, n))
    coordinates = np.column_stack((x.ravel(), y.ravel(), np.zeros(x.size)))
    return {index + 1: coordinate for index, coordinate in enumerate(coordinates)}


def _response_channel(node, direction, ref_node, ref_dir, axis, data):
    return {
        "type": 58,
        "func_type": 4,
        "id1": "Transfer Function H1",
        "id2": "H1 Displacement / Force",
        "rsp_node": node,
        "rsp_dir": direction,
        "ref_node": ref_node,
        "ref_dir": ref_dir,
        "x": axis,
        "data": data,
    }


def _synthetic_frf(axis, frequency_hz, damping, shape_value):
    denominator = frequency_hz**2 - axis**2 + 2j * damping * frequency_hz * axis
    return shape_value / denominator


class TwoReferenceMatrixConstructionTests(unittest.TestCase):
    def setUp(self):
        self.geometry = _grid_geometry(3)
        self.node_count = len(self.geometry)
        self.axis = np.linspace(1.0, 160.0, 400)

    def _two_reference_datasets(self):
        """9 response nodes, each driven from two independent references
        (node 1 dir 3, and node 5 dir 3) with distinct spatial content."""
        datasets = []
        for node_index in range(self.node_count):
            node = node_index + 1
            shape_a = np.sin(0.7 * node)
            shape_b = np.cos(0.4 * node)
            data_a = _synthetic_frf(self.axis, 80.0, 0.01, shape_a)
            data_b = _synthetic_frf(self.axis, 80.0, 0.01, shape_b)
            datasets.append(_response_channel(node, 3, 1, 3, self.axis, data_a))
            datasets.append(_response_channel(node, 3, 5, 3, self.axis, data_b))
        return datasets

    def test_two_independent_references_are_combined_not_reduced_to_one(self):
        datasets = self._two_reference_datasets()
        block = cmif_separation._build_multi_reference_frf_block(datasets, self.geometry)

        self.assertEqual(block.reference_count, 2)
        self.assertEqual(set(block.reference_keys), {(1, 3), (5, 3)})
        self.assertEqual(
            block.matrix.shape, (self.node_count, 2, len(self.axis))
        )
        # The two reference columns must carry genuinely different data, not one
        # reference's channel silently overwriting the other's.
        reference_a_index = block.reference_keys.index((1, 3))
        reference_b_index = block.reference_keys.index((5, 3))
        self.assertFalse(
            np.allclose(
                block.matrix[:, reference_a_index, :],
                block.matrix[:, reference_b_index, :],
            )
        )

    def test_single_reference_data_reports_reference_count_one(self):
        datasets = [
            item for item in self._two_reference_datasets() if item["ref_node"] == 1
        ]
        block = cmif_separation._build_multi_reference_frf_block(datasets, self.geometry)
        self.assertEqual(block.reference_count, 1)
        self.assertEqual(block.reference_keys, [(1, 3)])
        self.assertEqual(block.matrix.shape, (self.node_count, 1, len(self.axis)))

    def test_equivalent_duplicate_channel_is_kept_once_and_recorded(self):
        datasets = self._two_reference_datasets()
        # A channel exported twice with numerically identical data (for example
        # re-exported without change) is not a corruption; keep one copy and
        # record the duplicate, but do not warn or exclude it.
        duplicate = dict(datasets[0])
        duplicate["data"] = np.array(datasets[0]["data"])
        datasets.append(duplicate)

        block = cmif_separation._build_multi_reference_frf_block(datasets, self.geometry)

        self.assertEqual(block.reference_count, 2)
        self.assertEqual(
            block.duplicate_channels,
            [{"response": (1, 3), "reference": (1, 3), "status": "equivalent"}],
        )
        reference_a_index = block.reference_keys.index((1, 3))
        response_index = block.row_keys.index((1, 3))
        np.testing.assert_allclose(
            block.matrix[response_index, reference_a_index, :],
            datasets[0]["data"],
        )

    def test_conflicting_duplicate_channel_is_excluded_not_silently_chosen(self):
        datasets = self._two_reference_datasets()
        # A corrupted duplicate export of the same (response, reference) channel
        # with genuinely different data must not be averaged in, picked at
        # random, or silently kept as "the first one" -- it must be excluded
        # and recorded so the conflict is visible.
        duplicate = dict(datasets[0])
        duplicate["data"] = _synthetic_frf(self.axis, 80.0, 0.01, 999.0)
        datasets.append(duplicate)

        block = cmif_separation._build_multi_reference_frf_block(datasets, self.geometry)

        self.assertEqual(
            block.duplicate_channels,
            [{"response": (1, 3), "reference": (1, 3), "status": "conflicting"}],
        )
        # Both the legitimate and the corrupted channel are excluded, so node 1
        # is missing under reference (1, 3) and can no longer be a common
        # response DOF across every reference.
        self.assertNotIn((1, 3), block.row_keys)
        self.assertTrue(
            any(entry["node"] == 1 for entry in block.excluded_response_dofs)
        )

    def test_response_dof_missing_for_one_reference_is_excluded_not_fabricated(self):
        datasets = self._two_reference_datasets()
        # Drop reference B's channel for node 1 entirely: node 1 is only driven
        # from reference A, so it cannot appear in a genuine response x
        # reference matrix without fabricating data.
        datasets = [
            item
            for item in datasets
            if not (item["rsp_node"] == 1 and item["ref_node"] == 5)
        ]

        block = cmif_separation._build_multi_reference_frf_block(datasets, self.geometry)

        self.assertEqual(block.reference_count, 2)
        self.assertNotIn((1, 3), block.row_keys)
        self.assertEqual(len(block.excluded_response_dofs), 1)
        self.assertEqual(block.excluded_response_dofs[0]["node"], 1)
        self.assertEqual(block.matrix.shape[0], self.node_count - 1)
        self.assertEqual(block.initial_response_dof_count, self.node_count)
        self.assertAlmostEqual(
            block.response_dof_coverage_fraction,
            (self.node_count - 1) / self.node_count,
        )

    def test_incompatible_frequency_axis_reference_is_rejected_not_merged(self):
        datasets = self._two_reference_datasets()
        # Reference B uses a different frequency axis entirely (different span),
        # so it must be excluded rather than misaligned against reference A's
        # frequency lines.
        other_axis = np.linspace(1.0, 200.0, 400)
        rebuilt = [item for item in datasets if item["ref_node"] == 1]
        for node_index in range(self.node_count):
            node = node_index + 1
            shape_b = np.cos(0.4 * node)
            data_b = _synthetic_frf(other_axis, 80.0, 0.01, shape_b)
            rebuilt.append(_response_channel(node, 3, 5, 3, other_axis, data_b))

        block = cmif_separation._build_multi_reference_frf_block(rebuilt, self.geometry)

        self.assertEqual(block.reference_count, 1)
        self.assertEqual(block.reference_keys, [(1, 3)])
        self.assertEqual(len(block.dropped_references), 1)
        self.assertEqual(block.dropped_references[0]["reference"], (5, 3))
        self.assertIn("axis", block.dropped_references[0]["reason"])

    def test_axis_matching_coarse_signature_but_not_samples_is_rejected(self):
        """Two axes can share length, first value, last value, and median step
        while differing at an interior sample -- the coarse (signature-based)
        grouping alone must not be trusted as proof of alignment; every
        channel's actual samples must be compared with np.allclose against the
        canonical reference axis."""
        distorted_axis = self.axis.copy()
        # A single interior perturbation leaves length/start/end/median-step
        # identical (median is robust to one changed sample among 400), but
        # the array is no longer sample-for-sample identical.
        distorted_axis[200] += 0.5
        step = float(np.median(np.diff(self.axis)))
        distorted_step = float(np.median(np.diff(distorted_axis)))
        self.assertEqual(len(distorted_axis), len(self.axis))
        self.assertEqual(distorted_axis[0], self.axis[0])
        self.assertEqual(distorted_axis[-1], self.axis[-1])
        self.assertAlmostEqual(distorted_step, step, places=8)
        self.assertFalse(np.allclose(distorted_axis, self.axis, rtol=1.0e-8, atol=1.0e-10))

        rebuilt = [item for item in self._two_reference_datasets() if item["ref_node"] == 1]
        for node_index in range(self.node_count):
            node = node_index + 1
            shape_b = np.cos(0.4 * node)
            data_b = _synthetic_frf(distorted_axis, 80.0, 0.01, shape_b)
            rebuilt.append(_response_channel(node, 3, 5, 3, distorted_axis, data_b))

        block = cmif_separation._build_multi_reference_frf_block(rebuilt, self.geometry)

        self.assertEqual(block.reference_count, 1)
        self.assertEqual(block.reference_keys, [(1, 3)])
        self.assertEqual(len(block.dropped_references), 1)
        self.assertEqual(block.dropped_references[0]["reference"], (5, 3))
        self.assertIn("sample-for-sample", block.dropped_references[0]["reason"])


class CmifSingularValueTests(unittest.TestCase):
    def setUp(self):
        self.geometry = _grid_geometry(3)
        self.axis = np.linspace(60.0, 100.0, 800)

    def _two_close_mode_two_reference_datasets(self):
        """Two spatially independent, closely spaced modes, each dominantly
        excited by a different reference -- the textbook case a single
        reference cannot resolve but two references can."""
        datasets = []
        for node_index in range(len(self.geometry)):
            node = node_index + 1
            shape_1 = np.sin(0.9 * node)
            shape_2 = np.cos(0.5 * node)
            data_a = _synthetic_frf(self.axis, 80.0, 0.006, shape_1) + _synthetic_frf(
                self.axis, 81.5, 0.006, 0.05 * shape_2
            )
            data_b = _synthetic_frf(self.axis, 81.5, 0.006, shape_2) + _synthetic_frf(
                self.axis, 80.0, 0.006, 0.05 * shape_1
            )
            datasets.append(_response_channel(node, 3, 1, 3, self.axis, data_a))
            datasets.append(_response_channel(node, 3, 5, 3, self.axis, data_b))
        return datasets

    def test_two_reference_matrix_rank_reaches_two_near_two_independent_modes(self):
        datasets = self._two_close_mode_two_reference_datasets()
        block = cmif_separation._build_multi_reference_frf_block(datasets, self.geometry)
        singular_values = cmif_separation._cmif_singular_values(block)

        self.assertEqual(singular_values.shape, (len(self.axis), 2))
        near_modes = (self.axis >= 79.0) & (self.axis <= 82.5)
        second_to_first_ratio = np.max(
            singular_values[near_modes, 1] / np.maximum(singular_values[near_modes, 0], 1e-30)
        )
        # A single reference could never produce a second singular value at
        # all (rank capacity 1); two independent references resolving two
        # close modes should show non-negligible second-singular-value energy
        # somewhere in the band.
        self.assertGreater(second_to_first_ratio, 0.05)

    def test_single_reference_matrix_has_rank_capacity_one(self):
        datasets = [
            item
            for item in self._two_close_mode_two_reference_datasets()
            if item["ref_node"] == 1
        ]
        block = cmif_separation._build_multi_reference_frf_block(datasets, self.geometry)
        singular_values = cmif_separation._cmif_singular_values(block)
        self.assertEqual(singular_values.shape, (len(self.axis), 1))


class EndToEndPromotionTests(unittest.TestCase):
    """Confirms the fix reaches _reviewed_modes_from_frf and
    validate_close_mode_candidates end to end: a genuinely independent
    second reference can promote a close-mode candidate, which a single
    reference structurally cannot (ROADMAP Stage 2 #2 required test
    "confirmation that single-reference candidates are not automatically
    promoted" and its two-reference counterpart)."""

    def setUp(self):
        self.geometry = _grid_geometry(3)
        self.axis = np.linspace(60.0, 100.0, 800)
        self.f1, self.f2 = 80.0, 81.5

    def _datasets(self):
        datasets = []
        for node_index in range(len(self.geometry)):
            node = node_index + 1
            shape_1 = np.sin(0.9 * node)
            shape_2 = np.cos(0.5 * node)
            data_a = _synthetic_frf(self.axis, self.f1, 0.006, shape_1) + _synthetic_frf(
                self.axis, self.f2, 0.006, 0.05 * shape_2
            )
            data_b = _synthetic_frf(self.axis, self.f2, 0.006, shape_2) + _synthetic_frf(
                self.axis, self.f1, 0.006, 0.05 * shape_1
            )
            datasets.append(_response_channel(node, 3, 1, 3, self.axis, data_a))
            datasets.append(_response_channel(node, 3, 5, 3, self.axis, data_b))
        return datasets

    def _base_mode(self):
        node_numbers = np.array(sorted(self.geometry), dtype=int)
        coordinates = np.array([self.geometry[int(node)] for node in node_numbers])
        vectors = np.zeros((len(node_numbers), 3), dtype=complex)
        vectors[:, 2] = [np.sin(0.9 * node) for node in node_numbers]
        mode = ModeShape(
            number=1,
            frequency_hz=self.f1,
            node_ids=node_numbers.astype(object),
            coordinates=coordinates,
            vectors=vectors,
            metadata={"mode_source": "single detected peak"},
        )
        mode.measured_dofs = np.column_stack(
            (
                np.zeros(len(node_numbers), dtype=bool),
                np.zeros(len(node_numbers), dtype=bool),
                np.ones(len(node_numbers), dtype=bool),
            )
        )
        return mode

    def test_two_independent_references_report_reference_count_two(self):
        base_mode = self._base_mode()

        def fake_base_reader(*_args, **_kwargs):
            return [base_mode], {"mode_source": "test peak extraction"}

        with patch.object(
            cmif_separation, "_ORIGINAL_MODES_FROM_FRF", fake_base_reader, create=True
        ):
            modes, metadata = cmif_separation._reviewed_modes_from_frf(
                self._datasets(),
                self.geometry,
                target_frequencies=[self.f1, self.f2],
                target_count=2,
            )
            modes_with_unrelated_fe, metadata_with_unrelated_fe = (
                cmif_separation._reviewed_modes_from_frf(
                    self._datasets(),
                    self.geometry,
                    target_frequencies=[10.0, 150.0, 300.0],
                    target_count=300,
                )
            )

        np.testing.assert_allclose(
            [mode.frequency_hz for mode in modes],
            [mode.frequency_hz for mode in modes_with_unrelated_fe],
        )
        for left, right in zip(modes, modes_with_unrelated_fe):
            np.testing.assert_allclose(left.vectors, right.vectors)
        self.assertEqual(
            metadata["close_mode_separation"],
            metadata_with_unrelated_fe["close_mode_separation"],
        )

        separation = metadata["close_mode_separation"]
        self.assertEqual(separation["reference_count"], 2)
        self.assertEqual(separation["matrix_rank_capacity"], 2)
        candidates = [
            mode
            for mode in modes
            if mode.metadata.get("mode_source")
            == "local response-matrix SVD close-mode candidate"
        ]
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].metadata["reference_count"], 2)

        # The two independent references must produce a genuine, non-negligible
        # per-frequency CMIF second singular value near this cluster -- this is
        # the actual evidence validate_close_mode_candidates now decides on.
        cluster_diagnostic = separation["clusters"][0]
        cmif_ratio = cluster_diagnostic["cmif_max_second_to_first_singular_ratio"]
        self.assertIsNotNone(cmif_ratio)
        self.assertGreater(cmif_ratio, 0.05)

        # Full chain: FRF datasets -> response x reference matrix H(f) ->
        # per-frequency CMIF -> computed ratio -> automatic acceptance. The
        # real metadata produced above is passed through unmodified -- unlike
        # a single reference (test_cmif_validation.py's
        # test_single_reference_candidate_is_diagnostic_only), a genuinely
        # independent second reference lets the candidate be promoted.
        final_modes, _ = validate_close_mode_candidates(modes, metadata)
        self.assertEqual(len(final_modes), 2)
        promoted = [
            mode
            for mode in final_modes
            if "SVD/CMIF" in mode.metadata.get("source_label", "")
        ]
        self.assertEqual(len(promoted), 1)

    def test_single_reference_candidate_is_not_promoted_through_the_full_chain(self):
        """Same chain, but with only one reference: the candidate must stay
        diagnostic-only, confirming the real (not hand-built) CMIF ratio
        correctly reports no second-reference evidence when there is none."""
        base_mode = self._base_mode()
        single_reference_datasets = [
            item for item in self._datasets() if item["ref_node"] == 1
        ]

        def fake_base_reader(*_args, **_kwargs):
            return [base_mode], {"mode_source": "test peak extraction"}

        with patch.object(
            cmif_separation, "_ORIGINAL_MODES_FROM_FRF", fake_base_reader, create=True
        ):
            modes, metadata = cmif_separation._reviewed_modes_from_frf(
                single_reference_datasets,
                self.geometry,
                target_frequencies=[self.f1, self.f2],
                target_count=2,
            )

        separation = metadata["close_mode_separation"]
        self.assertEqual(separation["reference_count"], 1)
        self.assertEqual(separation["method"], "not required")
        self.assertEqual(separation["clusters"], [])

        final_modes, _ = validate_close_mode_candidates(modes, metadata)
        self.assertEqual(len(final_modes), 1)


if __name__ == "__main__":
    unittest.main()
