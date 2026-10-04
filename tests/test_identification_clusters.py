"""M4.4 cluster trigger + principal-angle confirmation (SPEC §12.4; D-009), synthetic shapes."""

from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from services.identification_clusters import (
    CARBON_V1_DIRECTIONS,
    ClusterInputError,
    ClusterStatus as S,
    TriggerRow,
    cluster_log_residual,
    cluster_triggers,
    confirm_cluster,
    principal_cos2,
)


RNG = np.random.default_rng(7)
N = 400
A, B, C, D = np.linalg.qr(RNG.normal(size=(N, 4)))[0].T  # orthonormal shapes


def rotate(angle_deg, leak=0.0, third=C):
    angle = math.radians(angle_deg)
    first = math.cos(angle) * A + math.sin(angle) * B + leak * third
    second = -math.sin(angle) * A + math.cos(angle) * B
    return np.array([first, second, D])  # a distant mode is always present too


def directions(angle_deg, leak=0.0):
    return {direction: rotate(angle_deg, leak) for direction in CARBON_V1_DIRECTIONS}


BASELINE = np.array([A, B])


class TriggerTests(unittest.TestCase):
    def test_spacing_is_only_a_trigger_in_either_domain(self):
        rows = [TriggerRow("R1", 100.0, 98.0), TriggerRow("R2", 102.5, 110.0), TriggerRow("R3", 150.0, 140.0),
                TriggerRow("R4", 170.0, 141.0), TriggerRow("R5", 300.0, 290.0)]
        triggers = cluster_triggers(rows)
        self.assertEqual([t.row_ids for t in triggers], [("R1", "R2"), ("R3", "R4")])  # exp 2.5 %; FE 0.7 %
        self.assertAlmostEqual(triggers[0].experimental_spacing, 0.025)

    def test_four_percent_is_not_a_trigger_and_groups_chain(self):
        self.assertEqual(cluster_triggers([TriggerRow("R1", 100.0, 100.0), TriggerRow("R2", 104.0, 104.0)]), ())
        chained = cluster_triggers([TriggerRow("R1", 100.0, 100.0), TriggerRow("R2", 102.0, 102.0),
                                    TriggerRow("R3", 104.0, 104.0)])
        self.assertEqual(chained[0].row_ids, ("R1", "R2", "R3"))

    def test_validation(self):
        with self.assertRaises(ClusterInputError):
            cluster_triggers([TriggerRow("R1", 100.0, 100.0), TriggerRow("R1", 101.0, 101.0)])
        with self.assertRaises(ClusterInputError):
            cluster_triggers([TriggerRow("R1", -1.0, 100.0)])


class ConfirmationTests(unittest.TestCase):
    def test_rotating_pair_is_one_cluster(self):
        result = confirm_cluster(("R1", "R2"), BASELINE, directions(45.0))
        self.assertIs(result.status, S.CONFIRMED)
        for item in result.directions:
            self.assertAlmostEqual(item.individual_macs[0], 0.5, places=9)
            self.assertGreater(min(item.cos2), 0.999)

    def test_close_but_distinct_shapes_stay_two_observations(self):
        result = confirm_cluster(("R1", "R2"), BASELINE, directions(5.0))
        self.assertIs(result.status, S.INDEPENDENT)

    def test_identity_lost_in_one_direction_is_enough(self):
        shapes = directions(5.0)
        shapes["G12_mpa-"] = rotate(40.0)
        self.assertIs(confirm_cluster(("R1", "R2"), BASELINE, shapes).status, S.CONFIRMED)

    def test_subspace_must_be_stable_in_every_direction(self):
        shapes = directions(45.0)
        shapes["E_in_plane_mpa+"] = rotate(45.0, leak=0.5)  # a third shape enters the subspace
        result = confirm_cluster(("R1", "R2"), BASELINE, shapes)
        self.assertIs(result.status, S.UNSTABLE)
        self.assertIn("E_in_plane_mpa+", result.reasons[0])

    def test_ambiguous_subspace_is_refused(self):
        shapes = directions(45.0)
        rotated = rotate(45.0)
        shapes["G12_mpa+"] = np.array([rotated[0], rotated[1], rotated[0] + 1e-6 * C])  # two pairs span it
        self.assertIs(confirm_cluster(("R1", "R2"), BASELINE, shapes).status, S.UNSTABLE)

    def test_more_than_two_modes_are_not_confirmable(self):
        result = confirm_cluster(("R1", "R2", "R3"), np.array([A, B, C]), directions(45.0))
        self.assertIs(result.status, S.UNSUPPORTED)

    def test_all_directions_required_and_validated(self):
        shapes = directions(45.0)
        del shapes["G12_mpa-"]
        with self.assertRaises(ClusterInputError):
            confirm_cluster(("R1", "R2"), BASELINE, shapes)
        with self.assertRaises(ClusterInputError):
            confirm_cluster(("R1", "R2"), BASELINE, directions(45.0), weights=-np.ones(N))

    def test_mass_weighting_is_applied(self):
        weights = np.linspace(1.0, 3.0, N)
        weighted = confirm_cluster(("R1", "R2"), BASELINE, directions(45.0), weights=weights)
        plain = confirm_cluster(("R1", "R2"), BASELINE, directions(45.0))
        self.assertIs(weighted.status, S.CONFIRMED)  # the subspace is invariant under the metric
        self.assertNotAlmostEqual(weighted.directions[0].individual_macs[0], plain.directions[0].individual_macs[0])

    def test_principal_angles(self):
        self.assertEqual(tuple(round(value, 12) for value in principal_cos2(BASELINE, rotate(30.0)[:2])), (1.0, 1.0))
        self.assertAlmostEqual(principal_cos2(BASELINE, np.array([A, C]))[1], 0.0, places=12)


class ResidualTests(unittest.TestCase):
    def test_cluster_residual_is_assignment_invariant(self):
        value = cluster_log_residual([205.0, 210.0], [206.0, 212.0])
        self.assertAlmostEqual(value, (math.log(205 / 206) + math.log(210 / 212)) / 2)
        self.assertAlmostEqual(cluster_log_residual([210.0, 205.0], [206.0, 212.0]), value)
        with self.assertRaises(ClusterInputError):
            cluster_log_residual([205.0], [206.0])
        with self.assertRaises(ClusterInputError):
            cluster_log_residual([205.0, 0.0], [206.0, 212.0])


if __name__ == "__main__":
    unittest.main()
