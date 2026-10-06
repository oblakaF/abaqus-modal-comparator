"""M5-C (M5.7): linearised leave-one-family-out model_form_robustness on explicit synthetic cases (no Abaqus).

The M4.9 twin case uses only committed records and is a synthetic records-based control, not
real-specimen model-form robustness (D-039).
"""

from __future__ import annotations

import inspect
import json
import math
from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from services.identification_uncertainty import ResidualTerm, residual_terms
from services.model_form_robustness import CaseStatus, linearised_model_form_robustness
from services.practical_identifiability import (
    G12_PARAMETER,
    RCOND,
    NuisancePrior,
    ObservationCovariance,
    ParameterDefinition,
    ParameterRole,
    PracticalIdentifiabilityInputError,
    assemble_system,
    build_sensitivity_matrix,
    diagonal_component,
    reconstruct_lm_jacobian,
)


E = ParameterDefinition("E_in_plane_mpa", ParameterRole.GLOBAL)
G = ParameterDefinition(G12_PARAMETER, ParameterRole.GLOBAL)
K = ParameterDefinition("k_core", ParameterRole.NUISANCE, "SYN")


def system(rows, parameters, priors=(), clusters=(), provenance="explicit synthetic case definition", sd=1.0):
    ids = [p.parameter_id for p in parameters]
    data = {r: dict(zip(ids, values)) for r, values in rows.items()}
    clustered = {m for c in clusters for m in c}
    m = build_sensitivity_matrix(data, [r for r in rows if r not in clustered], clusters, parameters,
                                 {p: "synthetic column" for p in ids})
    sigma = ObservationCovariance(m.term_ids, (diagonal_component("synthetic_measurement", m.term_ids,
                                                                  {t: sd for t in m.term_ids}, False, provenance),))
    return assemble_system(m, sigma, priors)


P_HAT_E = {"E_in_plane_mpa": 50000.0}


def case(result, family):
    return next(c for c in result.cases if c.family == family)


class TwoFamilyTests(unittest.TestCase):
    def setUp(self):
        # One parameter, Σ = I: A1 (s = 10, r = +0.5) in family A, B1 (s = 10, r = -0.5) in family B.
        self.system = system({"A1": (10.0,), "B1": (10.0,)}, (E,))
        self.fit = residual_terms(["A1", "B1"], [], [0.5, -0.5], {"A1": "A", "B1": "B"})
        self.result = linearised_model_form_robustness(self.system, self.fit, P_HAT_E)

    def test_a_hand_computable(self):
        summary = self.result.parameters["E_in_plane_mpa"]
        self.assertAlmostEqual(summary.min_estimate, 50000.0 * math.exp(-0.05), places=8)
        self.assertAlmostEqual(summary.max_estimate, 50000.0 * math.exp(0.05), places=8)
        self.assertAlmostEqual(summary.range_percent_of_p_hat, 100.0 * (math.exp(0.05) - math.exp(-0.05)), places=10)
        self.assertAlmostEqual(summary.half_range_percent_of_p_hat, summary.range_percent_of_p_hat / 2, places=12)
        self.assertTrue(self.result.supports_green)

    def test_b_removing_family_a(self):
        removed = case(self.result, "A")  # only B remains: δ = -(10 · -0.5) / 100 = +0.05
        self.assertIs(removed.status, CaseStatus.VALID)
        self.assertEqual(removed.removed_term_ids, ("A1",))
        self.assertAlmostEqual(removed.shift_ln["E_in_plane_mpa"], 0.05, places=14)

    def test_c_removing_family_b(self):
        self.assertAlmostEqual(case(self.result, "B").shift_ln["E_in_plane_mpa"], -0.05, places=14)

    def test_n_labelled_model_form_robustness(self):
        record = self.result.to_dict()
        self.assertEqual(record["quantity"], "model_form_robustness")
        self.assertIn("not statistical_sd", record["note"])
        self.assertIn("not 1 sigma", record["note"])
        self.assertFalse(any("sd" in key for key in record["parameters"]["E_in_plane_mpa"]))


class FamilyStructureTests(unittest.TestCase):
    def test_d_multiple_rows_of_a_family_are_removed_together(self):
        s = system({"A1": (10.0,), "A2": (5.0,), "B1": (10.0,)}, (E,))
        fit = residual_terms(["A1", "A2", "B1"], [], [0.5, 0.2, -0.5], {"A1": "A", "A2": "A", "B1": "B"})
        result = linearised_model_form_robustness(s, fit, P_HAT_E)
        self.assertEqual(case(result, "A").removed_term_ids, ("A1", "A2"))
        self.assertAlmostEqual(case(result, "A").shift_ln["E_in_plane_mpa"], 0.05, places=14)
        self.assertAlmostEqual(case(result, "B").shift_ln["E_in_plane_mpa"], -(10 * 0.5 + 5 * 0.2) / 125.0, places=14)

    def test_e_singleton_family(self):
        s = system({"A1": (10.0,), "A2": (5.0,), "B1": (10.0,)}, (E,))
        fit = residual_terms(["A1", "A2", "B1"], [], [0.5, 0.2, -0.5], {"A1": "A", "A2": "A", "B1": "B"})
        single = case(linearised_model_form_robustness(s, fit, P_HAT_E), "B")
        self.assertEqual(single.removed_term_ids, ("B1",))
        self.assertIs(single.status, CaseStatus.VALID)

    def test_f_confirmed_cluster_is_one_term(self):
        rows = {"R1": (1.0, 0.2), "R2": (0.6, 0.6), "R3": (0.5, 0.7), "R4": (0.2, 1.0), "R5": (0.8, 0.4)}
        families = {"R1": "F1", "R2": "C", "R3": "C", "R4": "F4", "R5": "F5"}
        s = system(rows, (E, G), clusters=(("R2", "R3"),))
        fit = residual_terms(["R1", "R4", "R5"], [("R2", "R3")], [0.3, -0.2, 0.1, 0.4], families)
        result = linearised_model_form_robustness(s, fit, {"E_in_plane_mpa": 5e4, G12_PARAMETER: 4e3})
        self.assertEqual(case(result, "C").removed_term_ids, ("C(R2+R3)",))  # one term, not two rows
        self.assertEqual(len(result.cases), 4)

    def test_g_composite_cluster_family_removed_only_under_its_key(self):
        rows = {"R1": (1.0, 0.2), "R2": (0.6, 0.6), "R3": (0.5, 0.7), "R4": (0.2, 1.0), "R5": (0.8, 0.4)}
        families = {"R1": "F1", "R2": "F1", "R3": "F2", "R4": "F2", "R5": "F5"}
        s = system(rows, (E, G), clusters=(("R2", "R3"),))
        fit = residual_terms(["R1", "R4", "R5"], [("R2", "R3")], [0.3, -0.2, 0.1, 0.4], families)
        result = linearised_model_form_robustness(s, fit, {"E_in_plane_mpa": 5e4, G12_PARAMETER: 4e3})
        self.assertEqual({c.family: c.removed_term_ids for c in result.cases},
                         {"F1": ("R1",), "F2": ("R4",), "F1+F2": ("C(R2+R3)",), "F5": ("R5",)})

    def test_h_holdouts_cannot_enter_the_fit(self):
        s = system({"A1": (10.0,), "B1": (10.0,)}, (E,))
        fit = residual_terms(["A1", "B1"], [], [0.5, -0.5], {"A1": "A", "B1": "B"})
        holdout = ResidualTerm("H1", ("H1",), "T", 2.5)
        with self.assertRaises(PracticalIdentifiabilityInputError):
            linearised_model_form_robustness(s, tuple(fit) + (holdout,), P_HAT_E)
        result = linearised_model_form_robustness(s, fit, P_HAT_E)
        self.assertNotIn("T", {c.family for c in result.cases})

    def test_i_prior_rows_stay_in_every_case(self):
        # k_core is informed only by family A; its prior keeps every reduced system full rank, and with A
        # removed the k_core estimate is pulled exactly to the prior centre (the prior residual is present).
        rows = {"A1": (1.0, 0.5), "A2": (0.8, 0.6), "B1": (1.0, 0.0), "B2": (0.7, 0.0)}
        centre = math.log(1.2)
        prior = NuisancePrior("k_core", centre, 0.3, "explicit synthetic prior", True)
        s = system(rows, (E, K), (prior,))
        fit = residual_terms(list(rows), [], [0.4, -0.3, 0.2, 0.1], {"A1": "A", "A2": "A", "B1": "B", "B2": "B"})
        p_hat = {"E_in_plane_mpa": 5e4, "k_core": 1.0}
        result = linearised_model_form_robustness(s, fit, p_hat)
        without_a = case(result, "A")
        self.assertIs(without_a.status, CaseStatus.VALID)
        self.assertAlmostEqual(without_a.estimate["k_core"], 1.2, places=12)
        self.assertTrue(all(c.status is CaseStatus.VALID for c in result.cases))


class RefusalTests(unittest.TestCase):
    def setUp(self):
        # Family A informs only E, family B only G12: removing either makes the reduced system rank-deficient.
        self.system = system({"A1": (1.0, 0.0), "A2": (0.5, 0.0), "B1": (0.0, 1.0), "B2": (0.0, 0.7)}, (E, G))
        self.fit = residual_terms(["A1", "A2", "B1", "B2"], [], [0.1, 0.2, -0.1, 0.3],
                                  {"A1": "A", "A2": "A", "B1": "B", "B2": "B"})
        self.p_hat = {"E_in_plane_mpa": 5e4, G12_PARAMETER: 4e3}

    def test_j_reduced_rank_deficiency_is_refused(self):
        result = linearised_model_form_robustness(self.system, self.fit, self.p_hat)
        for family in ("A", "B"):
            with self.subTest(family=family):
                refused = case(result, family)
                self.assertIs(refused.status, CaseStatus.REFUSED_RANK_DEFICIENT)
                self.assertIsNone(refused.shift_ln)
                self.assertIsNone(refused.estimate)
                self.assertIn("hard block", refused.reasons[0])
        self.assertFalse(result.supports_green)
        self.assertEqual(result.refused_families, ("A", "B"))
        self.assertEqual(result.parameters, {})  # no pseudo-inverse estimate is ever produced

    def test_k_l_no_pseudo_inverse_and_no_override(self):
        self.assertEqual(list(inspect.signature(linearised_model_form_robustness).parameters),
                         ["system", "fit_terms", "p_hat"])
        with self.assertRaises(TypeError):
            linearised_model_form_robustness(self.system, self.fit, self.p_hat, rcond=1e-12)
        self.assertEqual(linearised_model_form_robustness(self.system, self.fit, self.p_hat).rcond, RCOND)
        partial = system({"A1": (1.0, 0.0), "B1": (0.0, 1.0), "C1": (0.6, 0.8), "C2": (0.5, 0.5)}, (E, G))
        fit = residual_terms(["A1", "B1", "C1", "C2"], [], [0.1, -0.1, 0.2, 0.0], {"A1": "A", "B1": "B", "C1": "C", "C2": "C"})
        result = linearised_model_form_robustness(partial, fit, self.p_hat)
        self.assertTrue(all(c.status is CaseStatus.VALID for c in result.cases))
        self.assertTrue(result.supports_green)

    def test_full_system_must_be_full_rank_and_inputs_valid(self):
        deficient = system({"A1": (1.0, 2.0), "B1": (2.0, 4.0)}, (E, G))
        fit = residual_terms(["A1", "B1"], [], [0.1, 0.2], {"A1": "A", "B1": "B"})
        with self.assertRaises(PracticalIdentifiabilityInputError):
            linearised_model_form_robustness(deficient, fit, self.p_hat)
        with self.assertRaises(PracticalIdentifiabilityInputError):
            linearised_model_form_robustness(self.system, self.fit, {"E_in_plane_mpa": 5e4})
        with self.assertRaises(TypeError):
            linearised_model_form_robustness(None, self.fit, self.p_hat)


class DeterminismTests(unittest.TestCase):
    def test_m_deterministic_and_hash_bound(self):
        rows = {"R1": (1.0, 0.2), "R2": (0.6, 0.6), "R3": (0.2, 1.0), "R4": (0.8, 0.4)}
        families = {"R1": "F1", "R2": "F2", "R3": "F3", "R4": "F4"}
        fit = residual_terms(list(rows), [], [0.3, -0.2, 0.1, 0.4], families)
        p_hat = {"E_in_plane_mpa": 5e4, G12_PARAMETER: 4e3}
        first = linearised_model_form_robustness(system(rows, (E, G)), fit, p_hat)
        again = linearised_model_form_robustness(system(rows, (E, G)), fit, p_hat)
        self.assertEqual(first.record_hash, again.record_hash)
        other_sigma = linearised_model_form_robustness(system(rows, (E, G), provenance="other Σ source"), fit, p_hat)
        self.assertNotEqual(other_sigma.sigma_hash, first.sigma_hash)
        self.assertNotEqual(other_sigma.record_hash, first.record_hash)
        other_p = linearised_model_form_robustness(system(rows, (E, G)), fit, dict(p_hat, G12_mpa=4100.0))
        self.assertNotEqual(other_p.p_hat_hash, first.p_hat_hash)
        other_families = residual_terms(list(rows), [], [0.3, -0.2, 0.1, 0.4], dict(families, R4="F1"))
        self.assertNotEqual(linearised_model_form_robustness(system(rows, (E, G)), other_families, p_hat)
                            .family_mapping_hash, first.family_mapping_hash)
        json.dumps(first.to_dict(), allow_nan=False)


class TwinRecordsControlTests(unittest.TestCase):
    """O: the accepted M4.9 twin, synthetic records-based control (not real-specimen model-form robustness)."""

    LOOP = ROOT / "docs" / "auto_id" / "twins" / "SP13_identification_loop"
    GATE = ROOT / "docs" / "auto_id" / "twins" / "SP13_truth_gate"

    def test_o_twin_control_finite_without_abaqus(self):
        journal = json.loads((self.LOOP / "journal.json").read_text(encoding="utf-8"))
        loop = json.loads((self.LOOP / "loop_result.json").read_text(encoding="utf-8"))
        identity = json.loads((self.LOOP / "run_identity.json").read_text(encoding="utf-8"))
        readiness = json.loads((self.GATE / "readiness_report_a1.json").read_text(encoding="utf-8"))
        evaluations = [e["record"] for e in journal["entries"] if e["kind"] == "evaluation"]
        names = identity["bounds"]["names"]
        jac = reconstruct_lm_jacobian(evaluations, loop["history"], identity["start"], names,
                                      identity["lm_settings"]["finite_difference_step"])
        design, sigma = identity["objective_design"], 0.003
        whitened = np.array(jac.whitened)
        data = {row: {n: whitened[i, j] * sigma for j, n in enumerate(names)} for i, row in enumerate(design["fit_rows"])}
        m = build_sensitivity_matrix(data, design["fit_rows"], design["fit_clusters"],
                                     tuple(ParameterDefinition(n, ParameterRole.GLOBAL) for n in names),
                                     {n: jac.provenance for n in names})
        s = assemble_system(m, ObservationCovariance(m.term_ids, (diagonal_component(
            "twin_noise", m.term_ids, {t: sigma for t in m.term_ids}, False,
            "M4.9 twin synthetic experiment noise (sigma 0.003, D-036); not real-data uncertainty"),)), ())
        final = next(e for e in evaluations if e["parameters"] == loop["parameters"])
        families = {row["row_id"]: row["family"] for row in readiness["rows"]}
        fit = residual_terms(design["fit_rows"], design["fit_clusters"], final["residuals"], families)
        result = linearised_model_form_robustness(s, fit, loop["parameters"])
        self.assertEqual(len(result.cases), 21)  # 21 fitted families, one fit term each
        self.assertEqual(result.refused_families, ())
        self.assertTrue(result.supports_green)
        for name in names:
            summary = result.parameters[name]
            self.assertTrue(math.isfinite(summary.range_percent_of_p_hat))
            self.assertLess(summary.half_range_percent_of_p_hat, 5.0)
        self.assertEqual(result.quantity, "model_form_robustness")


if __name__ == "__main__":
    unittest.main()
