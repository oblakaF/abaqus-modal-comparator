"""M4.7 log-frequency objective (SPEC §7, §8): Φ = ½‖r‖², explicit σ, no MAC, holdouts reported only."""

from __future__ import annotations

from dataclasses import fields
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.frozen_observations import (
    BaselineIdentity,
    FreezeStatus,
    FrozenObservationSet,
    ObservationFreezeRefusal,
    ObservationRow,
)
from services.branch_tracker import TrackedBranch, TrackedCluster, TrackingResult
from services.identification_clusters import ClusterConfirmation, ClusterStatus
from services.identification_objective import (
    PROVISIONAL_SETUP_SD,
    ObjectiveEvaluation,
    ObjectiveInputError,
    ObjectiveTerm,
    RowSigma,
    build_objective_design,
    evaluate_objective,
)


IDENTITY = BaselineIdentity("SYN", "SYN_0123456789abcdef", "0" * 64, "1" * 64, "2" * 64, "3" * 64, "set", ("U3",),
                            "synthetic", None)
EXP = {"R1": 30.0, "R2": 75.0, "R3": 205.0, "R4": 212.0, "R5": 260.0}
FE = {"R1": 7, "R2": 8, "R3": 13, "R4": 14, "R5": 17}


def frozen(status=FreezeStatus.FROZEN):
    rows = tuple(ObservationRow(row, k + 1, EXP[row], FE[row], EXP[row], 0.95, 0.0) for k, row in enumerate(EXP))
    return FrozenObservationSet(IDENTITY, "strict", "p" * 64, status, () if status is FreezeStatus.FROZEN else ("x",),
                                rows if status is FreezeStatus.FROZEN else (), (), (), ())


def sigmas(measurement=0.001, setup=PROVISIONAL_SETUP_SD, provisional=True):
    return {row: RowSigma(measurement, setup, provisional) for row in EXP}


CLUSTER = ClusterConfirmation(("R3", "R4"), ClusterStatus.CONFIRMED, (), ())


def tracking(fe_hz):
    branches = tuple(TrackedBranch(row, FE[row], FE[row], hz, 0.99) for row, hz in fe_hz.items()
                     if row not in ("R3", "R4"))
    cluster = TrackedCluster(("R3", "R4"), (13, 14), (13, 14), (fe_hz["R3"], fe_hz["R4"]), (0.99, 0.98))
    return TrackingResult("p" * 64, "BASE", "CAND", branches, (cluster,), ())


class ObjectiveTests(unittest.TestCase):
    def setUp(self):
        self.frozen = frozen()
        self.design = build_objective_design(self.frozen, ["R5"], [CLUSTER], sigmas(), parameter_count=2)

    def test_residuals_and_objective_by_hand(self):
        fe = {"R1": 30.3, "R2": 74.0, "R3": 204.0, "R4": 214.0, "R5": 250.0}
        result = evaluate_objective(self.design, self.frozen, tracking(fe))
        sigma = math.hypot(0.001, 0.003)
        r1 = math.log(30.3 / 30.0) / sigma
        r2 = math.log(74.0 / 75.0) / sigma
        rc = ((math.log(204.0 / 205.0) + math.log(214.0 / 212.0)) / 2) / (math.sqrt(2) * sigma / 2)
        self.assertEqual([t.term_id for t in result.fit_terms], ["R1", "R2", "C(R3+R4)"])
        for term, expected in zip(result.fit_terms, (r1, r2, rc)):
            self.assertAlmostEqual(term.residual, expected, places=12)
        self.assertTrue(math.isclose(result.objective, 0.5 * (r1 ** 2 + r2 ** 2 + rc ** 2), rel_tol=1e-12))
        self.assertAlmostEqual(result.holdout_terms[0].log_ratio, math.log(250.0 / 260.0))
        self.assertTrue(result.provisional_uncertainty)

    def test_cluster_is_one_term_and_holdouts_never_enter_phi(self):
        fe = {"R1": 30.0, "R2": 75.0, "R3": 205.0, "R4": 212.0, "R5": 999.0}  # only the holdout is wrong
        result = evaluate_objective(self.design, self.frozen, tracking(fe))
        self.assertAlmostEqual(result.objective, 0.0, places=15)
        self.assertEqual(len(result.fit_terms), 3)
        self.assertGreater(abs(result.holdout_terms[0].residual), 100)

    def test_mac_is_not_an_input(self):
        names = {f.name for cls in (ObjectiveTerm, ObjectiveEvaluation) for f in fields(cls)}
        self.assertFalse({name for name in names if "mac" in name.lower()})
        fe = {"R1": 30.3, "R2": 74.0, "R3": 204.0, "R4": 214.0, "R5": 250.0}
        low_mac = TrackingResult("p" * 64, "BASE", "CAND",
                                 tuple(TrackedBranch(b.row_id, b.reference_mode, b.candidate_mode, b.candidate_hz, 0.91)
                                       for b in tracking(fe).branches), tracking(fe).clusters, ())
        self.assertEqual(evaluate_objective(self.design, self.frozen, low_mac).objective,
                         evaluate_objective(self.design, self.frozen, tracking(fe)).objective)

    def test_sigma_is_explicit(self):
        partial = sigmas()
        del partial["R2"]
        with self.assertRaises(ObjectiveInputError):
            build_objective_design(self.frozen, [], [], partial, parameter_count=2)
        for bad in ((-0.001, 0.003), (0.0, 0.0), (float("nan"), 0.003)):
            with self.subTest(bad=bad), self.assertRaises(ObjectiveInputError):
                RowSigma(bad[0], bad[1], False)
        measured = build_objective_design(self.frozen, [], [], sigmas(setup=0.002, provisional=False), 2)
        self.assertFalse(measured.provisional_uncertainty)

    def test_design_refusals(self):
        with self.assertRaises(ObservationFreezeRefusal):
            build_objective_design(frozen(FreezeStatus.NOT_FROZEN), [], [], sigmas(), 2)
        with self.assertRaises(ObjectiveInputError):  # under-determined
            build_objective_design(self.frozen, ["R1", "R2", "R5"], [CLUSTER], sigmas(), 2)
        with self.assertRaises(ObjectiveInputError):  # cluster split between fit and holdout
            build_objective_design(self.frozen, ["R3"], [CLUSTER], sigmas(), 2)
        with self.assertRaises(ObjectiveInputError):
            build_objective_design(self.frozen, [], [ClusterConfirmation(("R3", "R4"), ClusterStatus.INDEPENDENT, (), ())],
                                   sigmas(), 2)
        with self.assertRaises(ObjectiveInputError):
            build_objective_design(self.frozen, ["R9"], [], sigmas(), 2)

    def test_tracking_must_match_the_design(self):
        fe = {"R1": 30.3, "R2": 74.0, "R3": 204.0, "R4": 214.0, "R5": 250.0}
        incomplete = tracking(fe)
        incomplete = TrackingResult(incomplete.policy_hash, "BASE", "CAND", incomplete.branches[:-1],
                                    incomplete.clusters, ())
        with self.assertRaises(ObjectiveInputError):
            evaluate_objective(self.design, self.frozen, incomplete)
        other = build_objective_design(self.frozen, ["R5"], [CLUSTER], sigmas(), 2)
        self.assertEqual(other.observation_hash, self.design.observation_hash)


if __name__ == "__main__":
    unittest.main()
