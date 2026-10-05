"""M4.5 FE-to-FE branch tracker (SPEC §12.1; D-008; AUDIT V4): identity by FE shapes only, refusal on loss."""

from __future__ import annotations

import inspect
import math
from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING as STRICT
from services.branch_tracker import (
    BranchTrackingRefusal,
    FEModalState,
    RefusalKind as K,
    TrackingInputError,
    track_branches,
)


N = 300
SHAPES = np.linalg.qr(np.random.default_rng(3).normal(size=(N, 6)))[0].T  # orthonormal mode shapes
GEOMETRY, NODES = "a" * 64, "b" * 64


def state(name, shapes, frequencies, numbers=None, geometry=GEOMETRY):
    numbers = numbers or tuple(range(7, 7 + len(frequencies)))
    return FEModalState(name, geometry, NODES, tuple(numbers), tuple(float(f) for f in frequencies), np.array(shapes))


def mix(first, second, angle_deg):
    angle = math.radians(angle_deg)
    return (math.cos(angle) * first + math.sin(angle) * second,
            -math.sin(angle) * first + math.cos(angle) * second)


BASE = state("BASE", SHAPES, (70.0, 75.0, 85.0, 88.0, 140.0, 200.0))
ROWS = {"R1": 7, "R2": 8, "R3": 9, "R4": 10}


class TrackingTests(unittest.TestCase):
    def test_identity_is_followed_by_shape(self):
        result = track_branches(STRICT, BASE, state("CAND", SHAPES * 1.3, (68.0, 73.0, 83.0, 86.0, 137.0, 196.0)), ROWS)
        self.assertEqual({b.row_id: b.candidate_mode for b in result.branches}, {"R1": 7, "R2": 8, "R3": 9, "R4": 10})
        self.assertAlmostEqual(result.candidate_hz("R3"), 83.0)
        self.assertEqual(result.policy_hash, STRICT.policy_hash)
        self.assertEqual(result.order_changes, ())

    def test_frequency_crossing_with_stable_shapes_is_tracked_and_recorded(self):
        # Modes 9 and 10 swap frequency order; shapes are unchanged, so identity is unambiguous.
        swapped = SHAPES[[0, 1, 3, 2, 4, 5]]
        result = track_branches(STRICT, BASE, state("CAND", swapped, (70.0, 75.0, 86.0, 87.0, 140.0, 200.0)), ROWS)
        self.assertEqual({b.row_id: b.candidate_mode for b in result.branches}["R3"], 10)
        self.assertEqual(result.order_changes, (("R3", "R4"),))

    def test_artificial_branch_exchange_is_refused(self):
        a, b = mix(SHAPES[2], SHAPES[3], 45.0)  # modes 9 and 10 exchange character between iterations
        shapes = SHAPES.copy()
        shapes[2], shapes[3] = a, b
        with self.assertRaises(BranchTrackingRefusal) as caught:
            track_branches(STRICT, BASE, state("CAND", shapes, (70.0, 75.0, 85.0, 88.0, 140.0, 200.0)), ROWS)
        self.assertIs(caught.exception.kind, K.BRANCH_LOSS)
        self.assertFalse(issubclass(BranchTrackingRefusal, (ValueError, RuntimeError)))

    def test_partial_mixing_below_the_tracking_mac_is_branch_loss(self):
        shapes = SHAPES.copy()
        shapes[0], _ = mix(SHAPES[0], SHAPES[5], 20.0)  # MAC cos²20° = 0.883 < 0.90
        with self.assertRaises(BranchTrackingRefusal) as caught:
            track_branches(STRICT, BASE, state("CAND", shapes, BASE.frequencies_hz), ROWS)
        self.assertIs(caught.exception.kind, K.BRANCH_LOSS)
        shapes[0], _ = mix(SHAPES[0], SHAPES[5], 15.0)  # MAC 0.933 ≥ 0.90: still the same branch
        track_branches(STRICT, BASE, state("CAND", shapes, BASE.frequencies_hz), ROWS)

    def test_two_candidates_for_one_branch_are_ambiguous(self):
        shapes = np.vstack([SHAPES, SHAPES[0] + 0.05 * SHAPES[5]])
        candidate = state("CAND", shapes, BASE.frequencies_hz + (71.0,))
        with self.assertRaises(BranchTrackingRefusal) as caught:
            track_branches(STRICT, BASE, candidate, ROWS)
        self.assertIs(caught.exception.kind, K.AMBIGUOUS)

    def test_one_candidate_claimed_by_two_branches_is_an_exchange(self):
        reference = state("REF", np.vstack([SHAPES[:1], SHAPES[0] + 0.1 * SHAPES[1], SHAPES[2:]]),
                          (70.0, 71.0, 85.0, 88.0, 140.0, 200.0))
        candidate = state("CAND", np.vstack([SHAPES[:1], SHAPES[1], SHAPES[2:]]), (70.0, 75.0, 85.0, 88.0, 140.0, 200.0))
        with self.assertRaises(BranchTrackingRefusal) as caught:
            track_branches(STRICT, reference, candidate, {"R1": 7, "R2": 8})
        self.assertIs(caught.exception.kind, K.BRANCH_EXCHANGE)


class ClusterTrackingTests(unittest.TestCase):
    def test_confirmed_cluster_is_followed_as_a_subspace(self):
        shapes = SHAPES.copy()
        shapes[2], shapes[3] = mix(SHAPES[2], SHAPES[3], 45.0)  # individual identity rotates
        result = track_branches(STRICT, BASE, state("CAND", shapes, (70.0, 75.0, 85.5, 87.5, 140.0, 200.0)), ROWS,
                                clusters=[("R3", "R4")])
        self.assertEqual(result.clusters[0].candidate_modes, (9, 10))
        self.assertGreater(min(result.clusters[0].cos2), 0.999)
        self.assertEqual({b.row_id for b in result.branches}, {"R1", "R2"})

    def test_cluster_subspace_loss_is_refused(self):
        shapes = SHAPES.copy()
        shapes[2], _ = mix(SHAPES[2], SHAPES[5], 40.0)  # the cluster subspace leaks into another mode
        with self.assertRaises(BranchTrackingRefusal) as caught:
            track_branches(STRICT, BASE, state("CAND", shapes, BASE.frequencies_hz), ROWS, clusters=[("R3", "R4")])
        self.assertIs(caught.exception.kind, K.CLUSTER_LOSS)


class InputTests(unittest.TestCase):
    def test_states_must_share_geometry_and_node_set(self):
        with self.assertRaises(TrackingInputError):
            track_branches(STRICT, BASE, state("CAND", SHAPES, BASE.frequencies_hz, geometry="c" * 64), ROWS)

    def test_state_and_row_validation(self):
        with self.assertRaises(TrackingInputError):
            state("BAD", SHAPES[:2], (70.0,))
        with self.assertRaises(TrackingInputError):
            state("BAD", np.zeros((1, N)), (70.0,))
        with self.assertRaises(TrackingInputError):
            track_branches(STRICT, BASE, BASE, {"R1": 99})
        with self.assertRaises(TrackingInputError):
            track_branches(STRICT, BASE, BASE, ROWS, clusters=[("R1", "R9")])
        with self.assertRaises(TypeError):
            track_branches(None, BASE, BASE, ROWS)

    def test_tracking_takes_no_experimental_input(self):
        parameters = set(inspect.signature(track_branches).parameters)
        self.assertEqual(parameters, {"policy", "reference", "candidate", "rows", "clusters", "weights"})


if __name__ == "__main__":
    unittest.main()
