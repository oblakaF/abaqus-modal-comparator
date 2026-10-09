"""V12-I2 — τ_mf-aware holdout and residual-family-pattern evaluation (SPEC v1.2 §4, D-078; no Abaqus).

v1.2 (declared τ_mf), per governed residual term with its own σ_term, in log-frequency space:

    holdout FAIL       |Δ ln f| > max(3·σ_term, τ_mf)      (whitened: |r| > max(3, τ_mf / σ_term))
    family systematic  ≥ 2 FIT terms, same sign, every |Δ ln f| > max(2·σ_term, τ_mf)

Equality passes.  Without τ_mf (v1.1) the historical rules |r| > 2 / |r| > 3 and records are unchanged.  τ_mf never
enters Σ, the objective, statistical_sd, Birge, model_form_robustness or SPEC §13.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.campaign_definition import (
    MATERIAL_IDENTIFICATION,
    SPECIMEN_ENGINEERING_CALIBRATION,
    CalibrationNotImplementedRefusal,
    parse_campaign_definition,
)
from services.identification_campaign_run import CampaignRun, CampaignRunConfig, build_campaign_report
from services.identification_objective import RowSigma, build_objective_design, evaluate_objective
from services.identification_uncertainty import (
    BirgeStatus,
    PatternStatus,
    ResidualTerm,
    birge_adjustment,
    residual_pattern_test,
    residual_terms,
    statistical_sd,
)
from services.practical_identifiability import PracticalIdentifiabilityInputError
from m4_6_support import FakeExtractor, FakeSolver
from test_identification_objective import CLUSTER, frozen, tracking
from test_identification_uncertainty import CONTEXT, E, G, system
from test_m7_campaign import synthetic_definition, synthetic_specimen
from test_v12_i1_campaign_question import calibration_definition, v12_definition


# The v1.1 records as computed before V12-I2 (main 4e3a1eb): serialisation and hashes must not move.
V1_FAIL_HASH = "1ff4536b3496a311a507090b2d60088ca50fe9f860889738b2b59350a83f1902"
V1_PASS_HASH = "e29014a8f2349f9e2ccc3de698cb23e8097d5b0a0a234fc2e439614ce7d06c2f"
V1_FAIL_DICT = {
    "schema": "auto-id/identification-uncertainty/v1", "quantity": "residual_pattern_test", "status": "FAIL",
    "systematic_families": ["F1"], "holdout_failures": ["H1"],
    "families": [{"family": "F1", "term_ids": ["R1", "R2"], "values": [2.4, 3.1], "eligible": True, "systematic": True},
                 {"family": "F2", "term_ids": ["R3"], "values": [0.5], "eligible": False, "systematic": False}],
    "holdouts": {"H1": 3.2, "H2": -0.4},
    "reasons": ["systematic pattern - probable model-form error: family F1, all fit residuals same sign and |r| > 2",
                "holdout H1: |r| = 3.2 > 3"],
    "rules": {"family_sigma": 2.0, "holdout_sigma": 3.0, "minimum_family_size": 2, "inequalities": "strict"}}


def whitened(term_id, family, value, sigma=None):
    return ResidualTerm(term_id, (term_id,), family, value, sigma)


def physical(term_id, family, delta_ln_f, sigma):
    """A governed term given in log-frequency space: r = Δ ln f / σ_term (the objective's definition)."""
    return ResidualTerm(term_id, (term_id,), family, delta_ln_f / sigma, sigma)


def v1_fail_case():
    return ([whitened("R1", "F1", 2.4), whitened("R2", "F1", 3.1), whitened("R3", "F2", 0.5)],
            [whitened("H1", "T", 3.2), whitened("H2", "T", -0.4)])


def evidence(result, term_id):
    return next(t for t in result.to_dict()["terms"] if t["term_id"] == term_id)


class V11BoundaryTests(unittest.TestCase):
    def test_v1_holdout_and_family_boundaries(self):
        fit = [whitened("R9", "F9", 0.1)]
        self.assertIs(residual_pattern_test(fit, [whitened("H1", "T", 3.0)]).status, PatternStatus.PASS)  # |r| = 3
        self.assertIs(residual_pattern_test(fit, [whitened("H1", "T", 3.0000001)]).status, PatternStatus.FAIL)
        equal = residual_pattern_test([whitened("R1", "F1", 2.0), whitened("R2", "F1", 2.5)], [])
        self.assertEqual(equal.systematic_families, ())  # |r| = 2 is not > 2
        over = residual_pattern_test([whitened("R1", "F1", 2.0000001), whitened("R2", "F1", 2.5)], [])
        self.assertEqual(over.systematic_families, ("F1",))

    def test_v1_serialisation_and_record_hash_are_unchanged(self):
        result = residual_pattern_test(*v1_fail_case())
        self.assertEqual(result.to_dict(), V1_FAIL_DICT)
        self.assertEqual(result.record_hash, V1_FAIL_HASH)
        self.assertIsNone(result.tau_mf)
        passing = residual_pattern_test([whitened("R1", "F1", 0.4), whitened("R2", "F1", -0.1)],
                                        [whitened("H1", "T", 3.0)])
        self.assertEqual(passing.record_hash, V1_PASS_HASH)
        # Carrying σ_term changes nothing in the v1.1 path (no τ_mf declared).
        fit, held = v1_fail_case()
        with_sigma = residual_pattern_test([ResidualTerm(t.term_id, t.row_ids, t.family, t.value, 0.003) for t in fit],
                                           [ResidualTerm(t.term_id, t.row_ids, t.family, t.value, 0.003) for t in held])
        self.assertEqual(with_sigma.record_hash, V1_FAIL_HASH)


class V12BoundaryTests(unittest.TestCase):
    SIGMA, TAU = 0.003, 0.02  # max(2σ, τ) = max(3σ, τ) = 0.02; whitened 0.02 / 0.003 ≈ 6.667

    def holdout(self, delta):
        return residual_pattern_test([physical("R9", "F9", 0.0001, self.SIGMA)],
                                     [physical("H1", "T", delta, self.SIGMA)], self.TAU)

    def family(self, *deltas):
        return residual_pattern_test([physical(f"R{k}", "F1", d, self.SIGMA) for k, d in enumerate(deltas, 1)], [],
                                     self.TAU)

    def test_holdout_below_at_and_above_tau(self):
        self.assertIs(self.holdout(0.019).status, PatternStatus.PASS)
        self.assertIs(self.holdout(0.02).status, PatternStatus.PASS)  # equality passes
        self.assertIs(self.holdout(-0.02).status, PatternStatus.PASS)
        self.assertIs(self.holdout(0.0201).status, PatternStatus.FAIL)
        self.assertEqual(self.holdout(-0.0201).holdout_failures, ("H1",))
        self.assertIs(self.holdout(0.015).status, PatternStatus.PASS)  # |r| = 5 > 3 but within τ_mf
        record = evidence(self.holdout(0.0201), "H1")
        self.assertEqual((record["role"], record["sigma_term"], record["tau_mf"]), ("HOLDOUT", 0.003, 0.02))
        self.assertAlmostEqual(record["abs_delta_ln_f"], 0.0201, places=12)
        self.assertAlmostEqual(record["sigma_threshold_ln"], 0.009, places=12)
        self.assertAlmostEqual(record["effective_threshold_ln"], 0.02, places=12)
        self.assertTrue(record["exceeds"])

    def test_family_below_at_and_above_tau(self):
        self.assertEqual(self.family(0.019, 0.025).systematic_families, ())
        self.assertEqual(self.family(0.02, 0.025).systematic_families, ())  # one member at equality
        self.assertEqual(self.family(0.0201, 0.025).systematic_families, ("F1",))
        self.assertIs(self.family(0.0201, 0.025).status, PatternStatus.FAIL)
        self.assertEqual(self.family(-0.0201, -0.03).systematic_families, ("F1",))
        self.assertEqual(self.family(0.025, 0.03, 0.019).systematic_families, ())  # one member ≤ τ_mf
        self.assertEqual(self.family(0.025, -0.03).systematic_families, ())  # opposite signs
        self.assertEqual(self.family(0.05).systematic_families, ())  # a singleton never triggers
        self.assertEqual(self.family(0.015, 0.018).systematic_families, ())  # |r| > 2 each, but within τ_mf

    def test_reasons_are_physical(self):
        result = residual_pattern_test([physical("R1", "F1", 0.0201, 0.003), physical("R2", "F1", 0.025, 0.003)],
                                       [physical("H1", "T", 0.03, 0.003)], 0.02)
        text = " ".join(result.reasons)
        for phrase in ("|Δ ln f|", "τ_mf", "σ_term", "max(2σ_term, τ_mf)", "max(3σ_term, τ_mf)"):
            self.assertIn(phrase, text)
        record = result.to_dict()
        self.assertEqual(record["rules"]["tau_mf"], 0.02)
        self.assertEqual(record["rules"]["inequalities"], "strict")
        self.assertEqual(record["schema"], "auto-id/identification-uncertainty/v1.2-residual-pattern")
        json.dumps(record, allow_nan=False)


class SigmaDominatedTests(unittest.TestCase):
    """σ = 0.003, τ_mf = 0.005: the σ bounds 0.006 / 0.009 govern; τ_mf is combined by max(), never substituted."""

    SIGMA, TAU = 0.003, 0.005

    def test_family_threshold_is_two_sigma(self):
        def family(a, b):
            return residual_pattern_test([physical("R1", "F1", a, self.SIGMA), physical("R2", "F1", b, self.SIGMA)],
                                         [], self.TAU)

        self.assertEqual(family(0.006, 0.01).systematic_families, ())  # equality with 2σ
        self.assertEqual(family(0.0055, 0.01).systematic_families, ())  # above τ_mf, below 2σ
        self.assertEqual(family(0.00601, 0.01).systematic_families, ("F1",))
        self.assertAlmostEqual(evidence(family(0.00601, 0.01), "R1")["effective_threshold_ln"], 0.006, places=12)

    def test_holdout_threshold_is_three_sigma(self):
        def holdout(delta):
            return residual_pattern_test([physical("R9", "F9", 0.0, self.SIGMA)], [physical("H1", "T", delta, self.SIGMA)],
                                         self.TAU)

        self.assertIs(holdout(0.009).status, PatternStatus.PASS)  # equality with 3σ
        self.assertIs(holdout(0.007).status, PatternStatus.PASS)  # above τ_mf, below 3σ
        self.assertIs(holdout(0.00901).status, PatternStatus.FAIL)
        self.assertAlmostEqual(evidence(holdout(0.00901), "H1")["effective_threshold_ln"], 0.009, places=12)


class TermSpecificSigmaTests(unittest.TestCase):
    def test_each_term_uses_its_own_sigma(self):
        def family(a, b):  # A: σ 0.003 → threshold 0.02;  B: σ 0.012 → threshold 0.024
            return residual_pattern_test([physical("A", "F1", a, 0.003), physical("B", "F1", b, 0.012)], [], 0.02)

        self.assertEqual(family(0.021, 0.023).systematic_families, ())  # B within its own 0.024
        self.assertEqual(family(0.021, 0.024).systematic_families, ())  # B at equality
        self.assertEqual(family(0.021, 0.0241).systematic_families, ("F1",))
        self.assertEqual(family(0.0199, 0.03).systematic_families, ())  # A within 0.02
        result = family(0.021, 0.0241)
        self.assertAlmostEqual(evidence(result, "A")["effective_threshold_ln"], 0.02, places=12)
        self.assertAlmostEqual(evidence(result, "B")["effective_threshold_ln"], 0.024, places=12)
        self.assertEqual((evidence(result, "A")["sigma_term"], evidence(result, "B")["sigma_term"]), (0.003, 0.012))
        held = residual_pattern_test([physical("A", "F1", 0.0, 0.003)], [physical("H", "T", 0.035, 0.012)], 0.02)
        self.assertIs(held.status, PatternStatus.PASS)  # max(3·0.012, 0.02) = 0.036
        self.assertAlmostEqual(evidence(held, "H")["effective_threshold_ln"], 0.036, places=12)

    def test_v1_2_requires_the_governed_term_sigma(self):
        with self.assertRaisesRegex(PracticalIdentifiabilityInputError, "σ"):
            residual_pattern_test([whitened("R1", "F1", 1.0)], [], 0.02)
        with self.assertRaisesRegex(PracticalIdentifiabilityInputError, "σ"):
            residual_pattern_test([whitened("R1", "F1", 1.0, 0.003)], [whitened("H1", "T", 1.0)], 0.02)
        for bad in (0.0, -0.01, 0.03, math.nan, True):
            with self.subTest(tau_mf=bad), self.assertRaises(PracticalIdentifiabilityInputError):
                residual_pattern_test([whitened("R1", "F1", 1.0, 0.003)], [], bad)
        for bad in (0.0, -0.003, math.inf):
            with self.subTest(sigma=bad), self.assertRaises(PracticalIdentifiabilityInputError):
                whitened("R1", "F1", 1.0, bad)


class ClusterSigmaTests(unittest.TestCase):
    def test_cluster_term_uses_the_objective_cluster_sigma(self):
        rows = ("R1", "R2", "R3", "R4", "R5")
        sigmas = {row: RowSigma(None, 0.003, True) for row in rows}
        sigmas["R4"] = RowSigma(0.006, 0.003, True)  # cluster members with different σ
        frozen_set = frozen()
        design = build_objective_design(frozen_set, ["R5"], [CLUSTER], sigmas, parameter_count=2)
        fe = {"R1": 30.0, "R2": 75.0, "R3": 209.0, "R4": 216.5, "R5": 260.0}
        evaluation = evaluate_objective(design, frozen_set, tracking(fe))
        cluster = next(t for t in evaluation.fit_terms if t.term_id == "C(R3+R4)")
        expected = math.sqrt(0.003 ** 2 + math.hypot(0.006, 0.003) ** 2) / 2
        self.assertAlmostEqual(cluster.sigma, expected, places=15)
        families = {"R1": "F1", "R2": "F2", "R3": "F3", "R4": "F3", "R5": "T"}
        term_sigmas = {t.term_id: t.sigma for t in evaluation.fit_terms + evaluation.holdout_terms}
        fit = residual_terms(design.fit_rows, design.fit_clusters, [t.residual for t in evaluation.fit_terms],
                             families, term_sigmas)
        self.assertEqual([t.term_id for t in fit], ["R1", "R2", "C(R3+R4)"])  # the cluster is one term
        term = fit[2]
        self.assertEqual(term.sigma, cluster.sigma)  # the objective's governed cluster σ, not a member σ
        self.assertNotIn(term.sigma, (0.003, math.hypot(0.006, 0.003)))
        self.assertAlmostEqual(term.value * term.sigma, cluster.log_ratio, places=15)  # Δ ln f = r · σ_term
        result = residual_pattern_test(fit, [], 0.005)
        record = evidence(result, "C(R3+R4)")
        self.assertAlmostEqual(record["sigma_term"], cluster.sigma, places=14)  # record rounds to 12 digits
        self.assertAlmostEqual(record["effective_threshold_ln"], max(2 * cluster.sigma, 0.005), places=12)
        self.assertAlmostEqual(record["abs_delta_ln_f"], abs(cluster.log_ratio), places=12)
        with self.assertRaisesRegex(PracticalIdentifiabilityInputError, "σ"):
            residual_terms(design.fit_rows, design.fit_clusters, [t.residual for t in evaluation.fit_terms], families,
                           {k: v for k, v in term_sigmas.items() if k != "C(R3+R4)"})


class BirgeAndUncertaintyTests(unittest.TestCase):
    ROWS = {f"R{k}": (1.0 + 0.1 * k, 0.5 - 0.05 * k) for k in range(1, 7)}

    def chain(self, tau_mf):
        s = system(self.ROWS, (E, G))
        families = {"R1": "F1", "R2": "F1", "R3": "F2", "R4": "F3", "R5": "F4", "R6": "F5"}
        fit = residual_terms(list(self.ROWS), [], [2.5, 2.8, 0.1, -0.2, 0.3, 0.0], families,
                             {r: 0.003 for r in self.ROWS})  # F1: |Δ ln f| = 0.0075, 0.0084 < τ_mf 0.02
        statistical = statistical_sd(s, CONTEXT)
        pattern = residual_pattern_test(fit, [], tau_mf)
        return statistical, pattern, birge_adjustment(s, statistical, pattern, fit)

    def test_birge_formula_unchanged_and_only_gated_by_the_pattern(self):
        statistical_v1, pattern_v1, birge_v1 = self.chain(None)
        statistical_v12, pattern_v12, birge_v12 = self.chain(0.02)
        self.assertIs(pattern_v1.status, PatternStatus.FAIL)  # v1.1: |r| > 2 same sign
        self.assertIs(birge_v1.status, BirgeStatus.BLOCKED_PATTERN)
        self.assertIs(pattern_v12.status, PatternStatus.PASS)  # v1.2: inside τ_mf
        self.assertIs(birge_v12.status, BirgeStatus.AVAILABLE)
        self.assertEqual(statistical_v12.record_hash, statistical_v1.record_hash)  # statistical_sd untouched
        self.assertEqual((birge_v12.chi2, birge_v12.dof, birge_v12.birge_factor),
                         (birge_v1.chi2, birge_v1.dof, birge_v1.birge_factor))  # same χ², dof, s_B
        for p, sd in statistical_v12.statistical_sd_ln.items():
            self.assertEqual(birge_v12.birge_adjusted_sd_ln[p], sd * birge_v1.birge_factor)
        self.assertNotIn("tau", json.dumps(birge_v12.to_dict()))
        self.assertNotIn("tau", json.dumps(statistical_v12.to_dict()))

    def test_a_pattern_fail_still_blocks_birge(self):
        s = system(self.ROWS, (E, G))
        families = {"R1": "F1", "R2": "F1", "R3": "F2", "R4": "F3", "R5": "F4", "R6": "F5"}
        fit = residual_terms(list(self.ROWS), [], [8.0, 9.0, 0.1, -0.2, 0.3, 0.0], families,
                             {r: 0.003 for r in self.ROWS})  # F1: 0.024, 0.027 > τ_mf 0.02
        pattern = residual_pattern_test(fit, [], 0.02)
        self.assertEqual(pattern.systematic_families, ("F1",))
        self.assertIs(birge_adjustment(s, statistical_sd(s, CONTEXT), pattern, fit).status, BirgeStatus.BLOCKED_PATTERN)


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.tmp = Path(self._directory.name)

    def tearDown(self):
        self._directory.cleanup()

    def execute(self, definition, tag):
        items, roots = [], {}
        for label in (s.label for s in definition.specimens):
            item, store = synthetic_specimen(definition, label, self.tmp / tag)
            items.append(item)
            roots["synthetic"] = store
        config = CampaignRunConfig(self.tmp / tag / "runs", roots, "abq2024.bat", FakeSolver(), FakeExtractor(), {},
                                   "m" * 64)
        campaign = CampaignRun(definition, items, "m" * 64, config)
        result = campaign.run()
        return campaign, result, build_campaign_report(definition, campaign.specimens,
                                                       campaign.journal.records("evaluation"), result)

    def test_v1_2_campaign_uses_tau_and_never_touches_sigma_or_section_13(self):
        v1 = parse_campaign_definition(synthetic_definition())
        v12 = parse_campaign_definition(v12_definition(MATERIAL_IDENTIFICATION, 0.02))
        _, result_v1, report_v1 = self.execute(v1, "v1")
        campaign, result_v12, report_v12 = self.execute(v12, "v12")
        # Σ, objective / whitening, residuals and the optimum are identical.
        self.assertEqual({k: result_v12[k] for k in ("status", "parameters", "objective", "local_sd")},
                         {k: result_v1[k] for k in ("status", "parameters", "objective", "local_sd")})
        for key in ("sigma", "uncertainty_basis", "family_consistency", "per_specimen_agreement"):
            self.assertEqual(report_v12[key], report_v1[key], key)  # SPEC §13 unchanged, τ_mf-free
        self.assertNotIn("tau", json.dumps(report_v12["family_consistency"]))
        # The v1.2 pattern record is the τ_mf-aware one; the v1 record keeps its historical form.
        verdict_v1, verdict_v12 = report_v1["m5_verdict"], report_v12["m5_verdict"]
        self.assertNotEqual(verdict_v12["evidence_hashes"]["pattern"], verdict_v1["evidence_hashes"]["pattern"])
        self.assertEqual(verdict_v12["evidence_hashes"]["statistical_sd"], verdict_v1["evidence_hashes"]["statistical_sd"])
        self.assertEqual(report_v12["model_form_robustness"], report_v1["model_form_robustness"])

    def test_calibration_execution_is_still_refused(self):
        calibration = parse_campaign_definition(calibration_definition())
        items, roots = [], {}
        for label in (s.label for s in calibration.specimens):
            item, store = synthetic_specimen(calibration, label, self.tmp / "cal")
            items.append(item)
            roots["synthetic"] = store
        solver = FakeSolver()
        config = CampaignRunConfig(self.tmp / "runs", roots, "abq2024.bat", solver, FakeExtractor(), {}, "m" * 64)
        with self.assertRaises(CalibrationNotImplementedRefusal) as refused:
            CampaignRun(calibration, items, "m" * 64, config)
        self.assertEqual(refused.exception.state, "SPECIMEN_ENGINEERING_CALIBRATION_NOT_IMPLEMENTED")
        self.assertEqual(solver.commands, [])
        self.assertFalse((self.tmp / "runs").exists())
        self.assertEqual(calibration.scientific_question, SPECIMEN_ENGINEERING_CALIBRATION)


if __name__ == "__main__":
    unittest.main()
