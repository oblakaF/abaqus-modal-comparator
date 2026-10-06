"""M5-B (M5.5 statistical_sd, M5.8 residual-pattern test, M5.6 Birge) on explicit synthetic cases (no Abaqus).

The M4.9 twin case uses only committed records and is a synthetic records-based control, not
real-specimen uncertainty (D-039).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from services.identification_uncertainty import (
    BirgeStatus,
    PatternStatus,
    ResidualTerm,
    StatisticalStatus,
    birge_adjustment,
    residual_pattern_test,
    residual_terms,
    statistical_sd,
)
from services.practical_identifiability import (
    G12_PARAMETER,
    NuisancePrior,
    ObservationCovariance,
    ParameterDefinition,
    ParameterRole,
    PracticalIdentifiabilityInputError,
    RankDeficiencyRefusal,
    assemble_system,
    build_sensitivity_matrix,
    diagonal_component,
    reconstruct_lm_jacobian,
)


E = ParameterDefinition("E_in_plane_mpa", ParameterRole.GLOBAL)
G = ParameterDefinition(G12_PARAMETER, ParameterRole.GLOBAL)
K = ParameterDefinition("k_core", ParameterRole.NUISANCE, "SYN")
CONTEXT = "synthetic M5 test case (explicit definition)"


def system(rows, parameters, priors=(), sd=1.0, provenance="explicit synthetic case definition", clusters=()):
    ids = [p.parameter_id for p in parameters]
    names = list(rows)
    data = {r: dict(zip(ids, values)) for r, values in rows.items()}
    clustered = {m for c in clusters for m in c}
    m = build_sensitivity_matrix(data, [r for r in names if r not in clustered], clusters, parameters,
                                 {p: "synthetic column" for p in ids})
    sigma = ObservationCovariance(m.term_ids, (diagonal_component("synthetic_measurement", m.term_ids,
                                                                  {t: sd for t in m.term_ids}, False, provenance),))
    return assemble_system(m, sigma, priors)


def term(term_id, family, value, rows=None):
    return ResidualTerm(term_id, rows or (term_id,), family, value)


THREE = {"R1": (1.0, 0.0), "R2": (0.0, 1.0), "R3": (1.0, 1.0)}  # AᵀA = [[2,1],[1,2]] with Σ = I


class StatisticalSDTests(unittest.TestCase):
    def test_a_hand_computable_system(self):
        result = statistical_sd(system(THREE, (E, G)), CONTEXT)
        self.assertIs(result.status, StatisticalStatus.AVAILABLE)
        # C = (1/3)[[2, -1], [-1, 2]] -> sd = sqrt(2/3) for both parameters.
        for p in ("E_in_plane_mpa", G12_PARAMETER):
            self.assertAlmostEqual(result.statistical_sd_ln[p], math.sqrt(2.0 / 3.0), places=14)
            self.assertAlmostEqual(result.statistical_sd_percent_first_order[p], 100.0 * math.sqrt(2.0 / 3.0), places=12)
        self.assertIn("full M5 system", result.source)

    def test_b_nuisance_prior_changes_posterior_sd(self):
        rows = {"R1": (1.0, 0.2, 0.5), "R2": (0.3, 1.0, 0.4), "R3": (0.6, 0.5, 0.9), "R4": (0.9, 0.1, 0.7)}
        sds = {}
        for prior_sd in (10.0, 1.0, 0.1):
            prior = NuisancePrior("k_core", 0.0, prior_sd, "explicit synthetic prior", True)
            result = statistical_sd(system(rows, (E, G, K), (prior,)), CONTEXT)
            sds[prior_sd] = result.statistical_sd_ln
            # Hand check: A = [S ; 0 0 1/sd]
            a = np.vstack([np.array(list(rows.values())), [[0.0, 0.0, 1.0 / prior_sd]]])
            np.testing.assert_allclose([result.statistical_sd_ln[p] for p in result.parameter_ids],
                                       np.sqrt(np.diag(np.linalg.inv(a.T @ a))), rtol=1e-12)
            self.assertIn("prior:k_core", result.provisional_inputs)
        for p in ("E_in_plane_mpa", G12_PARAMETER, "k_core"):  # a tighter prior never widens a posterior sd
            self.assertGreaterEqual(sds[10.0][p], sds[1.0][p])
            self.assertGreaterEqual(sds[1.0][p], sds[0.1][p])
        self.assertLess(sds[0.1]["k_core"], sds[10.0]["k_core"])

    def test_c_rank_deficient_still_hard_refuses(self):
        result = statistical_sd(system({"R1": (1.0, 2.0), "R2": (2.0, 4.0), "R3": (3.0, 6.0)}, (E, G)), CONTEXT)
        self.assertIs(result.status, StatisticalStatus.REFUSED_RANK_DEFICIENT)
        self.assertIsNone(result.statistical_sd_ln)
        with self.assertRaises(RankDeficiencyRefusal):
            result.require_available()

    def test_d_m4_local_sd_cannot_be_passed_off(self):
        for not_a_system in ((0.002064, 0.009951), {"local_sd": [0.002, 0.01]}, None):
            with self.subTest(value=not_a_system), self.assertRaises(TypeError):
                statistical_sd(not_a_system, CONTEXT)
        with self.assertRaises(PracticalIdentifiabilityInputError):
            statistical_sd(system(THREE, (E, G)), "  ")
        self.assertEqual(statistical_sd(system(THREE, (E, G)), CONTEXT).to_dict()["quantity"], "statistical_sd")

    def test_e_sigma_provenance_survives_serialisation(self):
        first = statistical_sd(system(THREE, (E, G), provenance="Σ source A"), CONTEXT)
        second = statistical_sd(system(THREE, (E, G), provenance="Σ source B"), CONTEXT)
        record = first.to_dict()
        self.assertEqual(record["sigma_components"][0]["provenance"], "Σ source A")
        json.dumps(record, allow_nan=False)
        self.assertNotEqual(first.record_hash, second.record_hash)
        self.assertNotEqual(first.system_hash, second.system_hash)
        self.assertEqual(first.record_hash, statistical_sd(system(THREE, (E, G), provenance="Σ source A"), CONTEXT).record_hash)


class PatternTests(unittest.TestCase):
    def test_f_singleton_above_two_sigma_does_not_trigger(self):
        result = residual_pattern_test([term("R1", "F1", 3.5), term("R2", "F2", -2.6), term("R3", "F3", 2.9)], [])
        self.assertIs(result.status, PatternStatus.PASS)
        self.assertEqual(result.systematic_families, ())
        self.assertTrue(all(not f.eligible for f in result.families))  # singletons, never merged

    def test_g_two_same_sign_above_two_sigma_trigger(self):
        result = residual_pattern_test([term("R1", "F1", 2.4), term("R2", "F1", 3.1), term("R3", "F2", 0.5)], [])
        self.assertIs(result.status, PatternStatus.FAIL)
        self.assertEqual(result.systematic_families, ("F1",))
        negative = residual_pattern_test([term("R1", "F1", -2.4), term("R2", "F1", -3.1)], [])
        self.assertEqual(negative.systematic_families, ("F1",))

    def test_mixed_sign_or_one_member_not_above_two_does_not_trigger(self):
        mixed = residual_pattern_test([term("R1", "F1", 2.4), term("R2", "F1", -3.1)], [])
        self.assertIs(mixed.status, PatternStatus.PASS)
        weak = residual_pattern_test([term("R1", "F1", 2.4), term("R2", "F1", 3.1), term("R3", "F1", 1.9)], [])
        self.assertIs(weak.status, PatternStatus.PASS)
        exactly = residual_pattern_test([term("R1", "F1", 2.4), term("R2", "F1", 2.0)], [])  # strict |r| > 2
        self.assertIs(exactly.status, PatternStatus.PASS)

    def test_h_holdout_above_three_fails_strictly(self):
        fit = [term("R2", "F2", 0.3)]
        self.assertIs(residual_pattern_test(fit, [term("R1", "T", 3.2)]).status, PatternStatus.FAIL)
        self.assertEqual(residual_pattern_test(fit, [term("R1", "T", -3.2)]).holdout_failures, ("R1",))
        self.assertIs(residual_pattern_test(fit, [term("R1", "T", 3.0)]).status, PatternStatus.PASS)  # strict > 3
        self.assertIs(residual_pattern_test(fit, [term("R1", "T", 2.99)]).status, PatternStatus.PASS)

    def test_i_cluster_counts_once(self):
        families = {"R1": "F1", "R2": "F1", "R3": "F1", "R4": "F2"}
        terms = residual_terms(["R1", "R4"], [("R2", "R3")], [2.5, 0.1, 2.7], families)
        self.assertEqual([t.term_id for t in terms], ["R1", "R4", "C(R2+R3)"])
        self.assertEqual(terms[2].family, "F1")
        result = residual_pattern_test(terms, [])
        f1 = next(f for f in result.families if f.family == "F1")
        self.assertEqual(f1.term_ids, ("R1", "C(R2+R3)"))  # two terms, not three
        self.assertEqual(result.systematic_families, ("F1",))
        mixed = residual_terms([], [("R3", "R4")], [3.0], families)  # members of different families
        self.assertEqual(mixed[0].family, "F1+F2")
        with self.assertRaises(PracticalIdentifiabilityInputError):
            residual_pattern_test([term("R1", "F1", 0.1)], [term("R1", "F1", 0.1)])


class BirgeTests(unittest.TestCase):
    ROWS = {f"R{k}": (1.0 + 0.1 * k, 0.5 - 0.05 * k) for k in range(1, 7)}

    def case(self, residuals, priors=(), parameters=(E, G), rows=None, holdouts=(), families=None):
        rows = rows or self.ROWS
        s = system(rows, parameters, priors)
        families = families or {r: f"F{i}" for i, r in enumerate(rows)}
        fit = residual_terms(list(rows), [], residuals, families)
        statistical = statistical_sd(s, CONTEXT)
        pattern = residual_pattern_test(fit, list(holdouts))
        return birge_adjustment(s, statistical, pattern, fit), statistical

    def test_j_chi2_excludes_priors_and_holdouts(self):
        rows = {f"R{k}": (1.0 + 0.1 * k, 0.5 - 0.05 * k, 0.2 + 0.03 * k) for k in range(1, 7)}
        prior = NuisancePrior("k_core", 0.0, 0.01, "explicit synthetic prior", False)  # a heavy prior row
        residuals = [1.0, -1.5, 0.5, 2.0, -0.5, 1.0]
        birge, _ = self.case(residuals, (prior,), (E, G, K), rows, [term("H1", "T", 2.9)])
        self.assertAlmostEqual(birge.chi2, sum(r * r for r in residuals), places=12)

    def test_k_dof_includes_nuisance_parameters(self):
        rows = {f"R{k}": (1.0 + 0.1 * k, 0.5 - 0.05 * k, 0.2 + 0.03 * k) for k in range(1, 7)}
        prior = NuisancePrior("k_core", 0.0, 0.5, "explicit synthetic prior", True)
        birge, _ = self.case([1.0] * 6, (prior,), (E, G, K), rows)
        self.assertEqual((birge.n_fit_terms, birge.n_fitted_parameters, birge.dof), (6, 3, 3))

    def test_l_dof_not_positive_refuses(self):
        rows = {"R1": (1.0, 0.0), "R2": (0.0, 1.0)}
        birge, statistical = self.case([0.5, -0.5], rows=rows)
        self.assertIs(birge.status, BirgeStatus.REFUSED_DOF)
        self.assertEqual(birge.dof, 0)
        self.assertIsNone(birge.birge_adjusted_sd_ln)
        self.assertEqual(birge.statistical_sd_ln, statistical.statistical_sd_ln)  # kept separately

    def test_m_chi2_per_dof_below_one_leaves_sd_unscaled(self):
        birge, statistical = self.case([0.5, -0.5, 0.3, 0.2, -0.4, 0.1])
        self.assertLess(birge.chi2_per_dof, 1.0)
        self.assertEqual(birge.birge_factor, 1.0)
        self.assertEqual(birge.birge_adjusted_sd_ln, statistical.statistical_sd_ln)

    def test_n_chi2_per_dof_above_one_scales(self):
        residuals = [1.8, -1.6, 1.5, -1.9, 1.7, -1.4]
        birge, statistical = self.case(residuals)
        ratio = sum(r * r for r in residuals) / 4
        self.assertGreater(ratio, 1.0)
        self.assertAlmostEqual(birge.birge_factor, math.sqrt(ratio), places=14)
        for p, sd in statistical.statistical_sd_ln.items():
            self.assertAlmostEqual(birge.birge_adjusted_sd_ln[p], sd * math.sqrt(ratio), places=14)
        self.assertIs(birge.status, BirgeStatus.AVAILABLE)

    def test_o_pattern_failure_blocks_birge_but_keeps_statistical_sd(self):
        families = {"R1": "F1", "R2": "F1", "R3": "F2", "R4": "F3", "R5": "F4", "R6": "F5"}
        birge, statistical = self.case([2.5, 2.8, 0.1, -0.2, 0.3, 0.0], families=families)
        self.assertIs(birge.status, BirgeStatus.BLOCKED_PATTERN)
        self.assertIsNone(birge.birge_adjusted_sd_ln)
        self.assertEqual(birge.statistical_sd_ln, statistical.statistical_sd_ln)
        self.assertIn("NOT_AVAILABLE", birge.reasons[0])
        held, _ = self.case([0.1] * 6, holdouts=[term("H1", "T", 3.4)])
        self.assertIs(held.status, BirgeStatus.BLOCKED_PATTERN)

    def test_rank_deficient_statistical_refuses_birge(self):
        rows = {"R1": (1.0, 2.0), "R2": (2.0, 4.0), "R3": (3.0, 6.0)}
        birge, _ = self.case([0.1, 0.2, 0.3], rows=rows)
        self.assertIs(birge.status, BirgeStatus.REFUSED_STATISTICAL)

    def test_terms_must_match_the_system(self):
        s = system(self.ROWS, (E, G))
        fit = residual_terms(list(self.ROWS)[::-1], [], [0.1] * 6, {r: "F" for r in self.ROWS})
        with self.assertRaises(PracticalIdentifiabilityInputError):
            birge_adjustment(s, statistical_sd(s, CONTEXT), residual_pattern_test(fit, []), fit)


class TwinRecordsControlTests(unittest.TestCase):
    """P: the accepted M4.9 twin, a synthetic records-based control (not real-specimen uncertainty)."""

    LOOP = ROOT / "docs" / "auto_id" / "twins" / "SP13_identification_loop"
    GATE = ROOT / "docs" / "auto_id" / "twins" / "SP13_truth_gate"

    def test_p_twin_control_is_not_refused(self):
        journal = json.loads((self.LOOP / "journal.json").read_text(encoding="utf-8"))
        result = json.loads((self.LOOP / "loop_result.json").read_text(encoding="utf-8"))
        identity = json.loads((self.LOOP / "run_identity.json").read_text(encoding="utf-8"))
        readiness = json.loads((self.GATE / "readiness_report_a1.json").read_text(encoding="utf-8"))
        evaluations = [e["record"] for e in journal["entries"] if e["kind"] == "evaluation"]
        names = identity["bounds"]["names"]
        jac = reconstruct_lm_jacobian(evaluations, result["history"], identity["start"], names,
                                      identity["lm_settings"]["finite_difference_step"])
        design = identity["objective_design"]
        fit_rows, sigma = design["fit_rows"], 0.003
        whitened = np.array(jac.whitened)
        data = {row: {n: whitened[i, j] * sigma for j, n in enumerate(names)} for i, row in enumerate(fit_rows)}
        parameters = tuple(ParameterDefinition(n, ParameterRole.GLOBAL) for n in names)
        m = build_sensitivity_matrix(data, fit_rows, design["fit_clusters"], parameters,
                                     {n: jac.provenance for n in names})
        cov = ObservationCovariance(m.term_ids, (diagonal_component(
            "twin_noise", m.term_ids, {t: sigma for t in m.term_ids}, False,
            "M4.9 twin synthetic experiment noise (sigma 0.003, D-036); not real-data uncertainty"),))
        s = assemble_system(m, cov, ())
        statistical = statistical_sd(s, "synthetic records-based control: accepted M4.9 SP13 twin "
                                        "(Broyden-updated Jacobian from the committed journal); not real-specimen "
                                        "uncertainty")
        self.assertIs(statistical.status, StatisticalStatus.AVAILABLE)
        final = next(e for e in evaluations if e["parameters"] == result["parameters"])
        families = {row["row_id"]: row["family"] for row in readiness["rows"]}
        fit = residual_terms(fit_rows, design["fit_clusters"], final["residuals"], families)
        holdouts = [ResidualTerm(k, (k,), families[k], v) for k, v in sorted(final["holdout_residuals"].items())]
        pattern = residual_pattern_test(fit, holdouts)
        self.assertIs(pattern.status, PatternStatus.PASS)  # 21 singleton families; holdouts |r| < 3
        birge = birge_adjustment(s, statistical, pattern, fit)
        self.assertIs(birge.status, BirgeStatus.AVAILABLE)
        self.assertEqual((birge.n_fit_terms, birge.n_fitted_parameters, birge.dof), (21, 2, 19))
        self.assertAlmostEqual(birge.chi2, 2.0 * final["objective"], places=9)
        self.assertGreater(birge.birge_factor, 1.0)
        for n in names:  # separately labelled quantities, never merged
            self.assertGreater(birge.birge_adjusted_sd_ln[n], statistical.statistical_sd_ln[n])
            self.assertLess(birge.birge_adjusted_sd_ln[n], 0.08)
        self.assertIn("records-based control", statistical.context)


if __name__ == "__main__":
    unittest.main()
