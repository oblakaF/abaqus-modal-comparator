"""M5-A (M5.1–M5.4): practical identifiability on explicit synthetic systems (no Abaqus).

Every synthetic case defines its sensitivities, Σ and nuisance priors explicitly; tolerances such
as "q ≈ 0" belong to the tests only and are not scientific thresholds (M5_DECISION_RECORD §1).
The M4.9 twin positive control uses only committed records and is not real-specimen evidence.
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

from services.practical_identifiability import (
    G12_PARAMETER,
    RCOND,
    SD_FIT_LIMIT_LN,
    NuisancePrior,
    NuisancePriorRefusal,
    ObservationCovariance,
    ObservationTerm,
    ParameterDefinition,
    ParameterRole,
    PracticalIdentifiabilityInputError,
    RankDeficiencyRefusal,
    RankStatus,
    SensitivityMatrix,
    analyse_practical_identifiability,
    assemble_system,
    build_sensitivity_matrix,
    diagonal_component,
    reconstruct_lm_jacobian,
)


E = ParameterDefinition("E_in_plane_mpa", ParameterRole.GLOBAL)
G = ParameterDefinition(G12_PARAMETER, ParameterRole.GLOBAL)
K = ParameterDefinition("k_core", ParameterRole.NUISANCE, "SYN")
T = ParameterDefinition("t_face", ParameterRole.NUISANCE, "SYN")
SIGMA = 0.003
# Synthetic, explicitly defined log-sensitivities (d ln f / d ln p) of 8 fit rows.
S_E = [0.48, 0.32, 0.42, 0.36, 0.50, 0.30, 0.44, 0.38]
S_G = [0.02, 0.18, 0.08, 0.14, 0.00, 0.20, 0.05, 0.12]
S_T = [0.40, 0.35, 0.30, 0.45, 0.25, 0.50, 0.33, 0.41]
ROWS = [f"R{k}" for k in range(1, 9)]


def matrix(columns, parameters, rows=ROWS, clusters=()):
    data = {row: {p.parameter_id: columns[p.parameter_id][i] for p in parameters} for i, row in enumerate(rows)}
    singles = [r for r in rows if not any(r in c for c in clusters)]
    return build_sensitivity_matrix(data, singles, clusters, parameters,
                                    {p.parameter_id: f"synthetic case column {p.parameter_id}" for p in parameters})


def sigma(m, sd=SIGMA, provisional=False):
    return ObservationCovariance(m.term_ids, (diagonal_component("synthetic_measurement", m.term_ids,
                                                                 {t: sd for t in m.term_ids}, provisional,
                                                                 "explicit synthetic case definition"),))


def prior(parameter_id, sd, provisional=False):
    return NuisancePrior(parameter_id, 0.0, sd, "explicit synthetic case prior", provisional)


def analyse(columns, parameters, priors=(), **kw):
    m = matrix(columns, parameters, **kw)
    return analyse_practical_identifiability(assemble_system(m, sigma(m), priors))


class SystemTests(unittest.TestCase):
    def test_a_full_rank_global_only(self):
        result = analyse({"E_in_plane_mpa": S_E, G12_PARAMETER: S_G}, (E, G))
        self.assertIs(result.status, RankStatus.FULL_RANK)
        self.assertEqual(result.rank, 2)
        a = np.column_stack([S_E, S_G]) / SIGMA
        expected = np.sqrt(np.diag(np.linalg.inv(a.T @ a)))
        np.testing.assert_allclose([result.sd_ln["E_in_plane_mpa"], result.sd_ln[G12_PARAMETER]], expected, rtol=1e-12)
        self.assertEqual(result.refusal_reasons, ())
        self.assertIs(result.require_full_rank(), result)

    def test_b_full_rank_global_plus_nuisance_with_explicit_prior(self):
        columns = {"E_in_plane_mpa": S_E, G12_PARAMETER: S_G, "t_face": S_T}
        result = analyse(columns, (E, G, T), (prior("t_face", 0.02, provisional=True),))
        self.assertIs(result.status, RankStatus.FULL_RANK)
        self.assertEqual(result.parameter_ids, ("E_in_plane_mpa", G12_PARAMETER, "t_face"))
        a = np.vstack([np.column_stack([S_E, S_G, S_T]) / SIGMA, [[0.0, 0.0, 1.0 / 0.02]]])
        expected = np.sqrt(np.diag(np.linalg.inv(a.T @ a)))
        np.testing.assert_allclose([result.sd_ln[p] for p in result.parameter_ids], expected, rtol=1e-12)
        self.assertEqual(result.provisional_inputs, ("prior:t_face",))  # PROVISIONAL flag carried
        self.assertIsNone(result.projections["t_face"].projected_sd_ln)  # has a prior row

    def test_c_missing_nuisance_prior_is_refused(self):
        m = matrix({"E_in_plane_mpa": S_E, G12_PARAMETER: S_G, "t_face": S_T}, (E, G, T))
        with self.assertRaises(NuisancePriorRefusal):
            assemble_system(m, sigma(m), ())
        with self.assertRaises(NuisancePriorRefusal):  # no prior rows for global parameters
            assemble_system(m, sigma(m), (prior("t_face", 0.02), prior(G12_PARAMETER, 0.1)))
        with self.assertRaises(NuisancePriorRefusal):
            assemble_system(m, sigma(m), (prior("t_face", 0.02), prior("t_face", 0.03)))

    def test_d_non_positive_prior_sd_is_refused(self):
        for sd in (0.0, -0.01):
            with self.subTest(sd=sd), self.assertRaises(NuisancePriorRefusal):
                prior("t_face", sd)
        with self.assertRaises(PracticalIdentifiabilityInputError):
            prior("t_face", float("nan"))

    def test_e_rank_deficient_full_system_is_a_hard_refusal(self):
        collinear = [2.0 * v for v in S_E]  # G column exactly parallel to E
        result = analyse({"E_in_plane_mpa": S_E, G12_PARAMETER: collinear}, (E, G))
        self.assertIs(result.status, RankStatus.RANK_DEFICIENT)
        self.assertEqual(result.rank, 1)
        self.assertIsNone(result.covariance_ln)
        self.assertIsNone(result.sd_ln)
        self.assertIsNone(result.exceeds_sd_fit_limit)
        self.assertIn("hard block", result.refusal_reasons[0])
        with self.assertRaises(RankDeficiencyRefusal):
            result.require_full_rank()

    def test_f_no_override_exists(self):
        parameters = inspect.signature(analyse_practical_identifiability).parameters
        self.assertEqual(list(parameters), ["system"])  # no rcond, override or pseudo-inverse switch
        result = analyse({"E_in_plane_mpa": S_E, G12_PARAMETER: [2.0 * v for v in S_E]}, (E, G))
        with self.assertRaises(Exception):
            result.status = RankStatus.FULL_RANK  # frozen record
        with self.assertRaises(TypeError):
            analyse_practical_identifiability(assemble_system(*self._deficient()), rcond=1e-12)
        self.assertEqual(RCOND, 1.0e-3)

    def _deficient(self):
        m = matrix({"E_in_plane_mpa": S_E, G12_PARAMETER: [2.0 * v for v in S_E]}, (E, G))
        return m, sigma(m), ()

    def test_g_behaviour_around_rcond(self):
        rows = [f"R{k}" for k in range(1, 5)]
        u = np.linalg.qr(np.random.default_rng(5).normal(size=(4, 2)))[0]
        v = np.array([[0.6, 0.8], [-0.8, 0.6]])
        for ratio, status in ((1.01e-3, RankStatus.FULL_RANK), (0.99e-3, RankStatus.RANK_DEFICIENT)):
            s = u @ np.diag([1.0, ratio]) @ v.T  # whitened by Σ = I: singular values exactly 1 and `ratio`
            columns = {"E_in_plane_mpa": list(s[:, 0]), G12_PARAMETER: list(s[:, 1])}
            m = matrix(columns, (E, G), rows=rows)
            result = analyse_practical_identifiability(assemble_system(m, sigma(m, sd=1.0), ()))
            with self.subTest(ratio=ratio):
                self.assertIs(result.status, status)
                self.assertAlmostEqual(result.singular_values[1] / result.singular_values[0], ratio, places=12)

    def test_h_whitening_by_explicit_sigma(self):
        m = matrix({"E_in_plane_mpa": S_E, G12_PARAMETER: S_G}, (E, G))
        sds = [0.002, 0.003, 0.004, 0.003, 0.005, 0.002, 0.003, 0.004]
        meas = diagonal_component("meas", m.term_ids, dict(zip(m.term_ids, sds)), False, "synthetic")
        setup = diagonal_component("setup", m.term_ids, {t: 0.003 for t in m.term_ids}, True, "synthetic provisional")
        covariance = ObservationCovariance(m.term_ids, (meas, setup))
        system = assemble_system(m, covariance, ())
        weights = 1.0 / np.sqrt(np.square(sds) + 0.003 ** 2)
        np.testing.assert_allclose(system.whitened_sensitivities(), m.array() * weights[:, None], rtol=1e-12)
        self.assertEqual(system.provisional_inputs, ("Σ:setup",))
        correlated = np.diag(np.square(sds)) + 0.5e-6 * (np.ones((8, 8)) - np.eye(8))
        full = ObservationCovariance(m.term_ids, (
            __import__("services.practical_identifiability", fromlist=["CovarianceComponent"]).CovarianceComponent(
                "full", tuple(map(tuple, correlated)), False, "synthetic correlated"),))
        a = np.linalg.solve(np.linalg.cholesky(correlated), m.array())
        result = analyse_practical_identifiability(assemble_system(m, full, ()))
        np.testing.assert_allclose(np.array(result.covariance_ln), np.linalg.inv(a.T @ a), rtol=1e-9)
        with self.assertRaises(PracticalIdentifiabilityInputError):  # not positive definite
            ObservationCovariance(m.term_ids, (diagonal_component("x", m.term_ids, {t: 1.0 for t in m.term_ids},
                                                                  False, "s"),
                                               __import__("services.practical_identifiability",
                                                          fromlist=["CovarianceComponent"]).CovarianceComponent(
                                                   "neg", tuple(map(tuple, -2.0 * np.eye(8))), False, "s")))

    def test_i_confirmed_cluster_is_one_sensitivity_row(self):
        m = matrix({"E_in_plane_mpa": S_E, G12_PARAMETER: S_G}, (E, G), clusters=(("R3", "R4"),))
        self.assertEqual(len(m.terms), 7)
        cluster = [t for t in m.terms if t.is_cluster]
        self.assertEqual([t.row_ids for t in cluster], [("R3", "R4")])
        row = m.values[m.term_ids.index(cluster[0].term_id)]
        np.testing.assert_allclose(row, [(S_E[2] + S_E[3]) / 2, (S_G[2] + S_G[3]) / 2], rtol=1e-15)
        with self.assertRaises(PracticalIdentifiabilityInputError):  # a row in two terms
            SensitivityMatrix((ObservationTerm("R1", ("R1",)), ObservationTerm("C", ("R1", "R2"))), (E,),
                              ((0.1,), (0.2,)), {"E_in_plane_mpa": "s"})

    def test_j_q_near_one_when_g12_orthogonal_to_nuisance(self):
        rows = [f"R{k}" for k in range(1, 7)]
        basis = np.linalg.qr(np.random.default_rng(3).normal(size=(6, 3)))[0]
        columns = {"E_in_plane_mpa": list(basis[:, 0]), G12_PARAMETER: list(basis[:, 1]), "k_core": list(basis[:, 2])}
        result = analyse(columns, (E, G, K), (prior("k_core", 0.15),), rows=rows)
        self.assertIs(result.status, RankStatus.FULL_RANK)
        self.assertAlmostEqual(result.q_g, 1.0, places=10)  # test tolerance only

    def test_k_l_g12_absorbed_by_k_core(self):
        # Synthetic absorption case: k_core is data-relevant (its sensitivity equals G12's) and only weakly
        # constrained by its explicit (PROVISIONAL) prior, so G12 information lives in a nuisance direction.
        s_k = [0.10, 0.12, 0.09, 0.15, 0.11, 0.14, 0.10, 0.13]
        columns = {"E_in_plane_mpa": S_E, G12_PARAMETER: list(s_k), "k_core": s_k}
        result = analyse(columns, (E, G, K), (prior("k_core", 0.5, provisional=True),))
        # K: q_G ≈ 0 (the tolerance is the test's, not a policy threshold).
        self.assertLess(result.q_g, 0.05)
        projection = result.projections[G12_PARAMETER]
        self.assertGreater(projection.projected_sd_ln, SD_FIT_LIMIT_LN)
        # L: the full system cannot support G12: its posterior sd exceeds the SPEC §10 fit limit, so the
        # evidence handed to the M5.9 verdict engine is NOT_IDENTIFIABLE-compatible, never green.
        self.assertIs(result.status, RankStatus.FULL_RANK)  # the prior row keeps A full rank
        self.assertGreater(result.sd_ln[G12_PARAMETER], SD_FIT_LIMIT_LN)
        self.assertTrue(result.exceeds_sd_fit_limit[G12_PARAMETER])
        self.assertFalse(result.exceeds_sd_fit_limit["E_in_plane_mpa"])
        self.assertEqual(result.provisional_inputs, ("prior:k_core",))
        # Without the k_core prior the case is refused before any number exists (no default prior).
        m = matrix(columns, (E, G, K))
        with self.assertRaises(NuisancePriorRefusal):
            assemble_system(m, sigma(m), ())

    def test_weak_nuisance_column_does_not_absorb_g12(self):
        # Contrast: a k_core column two orders of magnitude weaker than G12's (CARBON-5F-like scale) with the
        # same prior cannot absorb G12; q_G stays far from 0. The full calculation decides, not the cosine.
        s_k = [0.0010, 0.0012, 0.0009, 0.0015, 0.0011, 0.0014, 0.0010, 0.0013]
        columns = {"E_in_plane_mpa": S_E, G12_PARAMETER: [100.0 * v for v in s_k], "k_core": s_k}
        result = analyse(columns, (E, G, K), (prior("k_core", 0.5, provisional=True),))
        self.assertAlmostEqual(result.pairwise_cosines[f"{G12_PARAMETER}|k_core"], 1.0, places=12)
        self.assertGreater(result.q_g, 0.2)  # an order of magnitude above the absorption case (test bound only)
        self.assertFalse(result.exceeds_sd_fit_limit[G12_PARAMETER])

    def test_m_condition_and_cosine_are_diagnostics_only(self):
        rows = [f"R{k}" for k in range(1, 5)]
        a = np.array([1.0, 0.5, 0.25, 0.75])
        b = a + 1e-2 * np.array([1.0, -1.0, 1.0, -1.0])  # cosine ≈ 0.9999, condition number in the hundreds
        result = analyse({"E_in_plane_mpa": list(a), G12_PARAMETER: list(b)}, (E, G), rows=rows)
        self.assertIs(result.status, RankStatus.FULL_RANK)
        self.assertGreater(result.pairwise_cosines[f"E_in_plane_mpa|{G12_PARAMETER}"], 0.999)
        self.assertGreater(result.condition_number, 100.0)
        self.assertEqual(result.refusal_reasons, ())

    def test_n_deterministic_records_and_hashes(self):
        columns = {"E_in_plane_mpa": S_E, G12_PARAMETER: S_G, "t_face": S_T}
        first = analyse(columns, (E, G, T), (prior("t_face", 0.02),))
        second = analyse(columns, (E, G, T), (prior("t_face", 0.02),))
        self.assertEqual(first.record_hash, second.record_hash)
        self.assertEqual(first.system_hash, second.system_hash)
        self.assertEqual(first.system_hash, "9e847695429a4b6fbfb0d7c40bb3bf46bbba54e98f3c729e0b30d3c20cd513ce")
        changed = analyse(columns, (E, G, T), (prior("t_face", 0.03),))
        self.assertNotEqual(changed.system_hash, first.system_hash)
        self.assertNotEqual(changed.record_hash, first.record_hash)
        json.dumps(first.to_dict(), allow_nan=False)


class ModuleBoundaryTests(unittest.TestCase):
    def test_no_abaqus_m3_or_legacy_imports(self):
        import ast

        for module in ("practical_identifiability.py", "identification_uncertainty.py", "model_form_robustness.py"):
            tree = ast.parse((ROOT / "src" / "services" / module).read_text(encoding="utf-8"))
            imported = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module]
            imported += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
            for forbidden in ("subprocess", "abaqus_bridge", "forward_builder", "shared_carbon_forward",
                              "identifiability_service", "uncertainty_service", "sensitivity_service", "inverse_solver"):
                with self.subTest(module=module, forbidden=forbidden):
                    self.assertFalse([m for m in imported if m == forbidden or m.endswith("." + forbidden)])


class TwinPositiveControlTests(unittest.TestCase):
    """M5_DECISION_RECORD §2: the accepted M4.9 twin as a records-based positive control (not real evidence)."""

    LOOP = ROOT / "docs" / "auto_id" / "twins" / "SP13_identification_loop"

    def test_broyden_jacobian_reconstruction_and_full_system(self):
        journal = json.loads((self.LOOP / "journal.json").read_text(encoding="utf-8"))
        result = json.loads((self.LOOP / "loop_result.json").read_text(encoding="utf-8"))
        identity = json.loads((self.LOOP / "run_identity.json").read_text(encoding="utf-8"))
        evaluations = [e["record"] for e in journal["entries"] if e["kind"] == "evaluation"]
        names = identity["bounds"]["names"]
        reconstructed = reconstruct_lm_jacobian(evaluations, result["history"], identity["start"], names,
                                                identity["lm_settings"]["finite_difference_step"])
        again = reconstruct_lm_jacobian(evaluations, result["history"], identity["start"], names,
                                        identity["lm_settings"]["finite_difference_step"])
        self.assertEqual(reconstructed, again)  # deterministic
        self.assertEqual(reconstructed.updates, 1)
        self.assertIn("Broyden-updated", reconstructed.provenance)
        self.assertEqual(reconstructed.point, result["parameters"])
        # Full M5 system: global-only (the twin has no nuisance parameters), Σ = the twin's synthetic noise.
        rows = identity["objective_design"]["fit_rows"]
        whitened = np.array(reconstructed.whitened)
        sensitivities = {row: {n: whitened[i, j] * SIGMA for j, n in enumerate(names)} for i, row in enumerate(rows)}
        parameters = (ParameterDefinition(names[0], ParameterRole.GLOBAL), ParameterDefinition(names[1], ParameterRole.GLOBAL))
        m = build_sensitivity_matrix(sensitivities, rows, (), parameters, {n: reconstructed.provenance for n in names})
        covariance = ObservationCovariance(m.term_ids, (diagonal_component(
            "twin_noise", m.term_ids, {t: SIGMA for t in m.term_ids}, False,
            "M4.9 twin synthetic noise definition (sigma 0.003, D-036); not real-data uncertainty"),))
        analysis = analyse_practical_identifiability(assemble_system(m, covariance, ()))
        self.assertIs(analysis.status, RankStatus.FULL_RANK)
        # The M5 posterior sd of this global-only, prior-free system coincides numerically with the M4 stop-rule
        # sd; it is computed here from the M5 system and is not relabelled as statistical_sd (that is M5.5).
        np.testing.assert_allclose([analysis.sd_ln[n] for n in names], result["local_sd_ln"], rtol=1e-9)
        self.assertGreater(analysis.q_g, 0.7)
        self.assertFalse(any(analysis.exceeds_sd_fit_limit.values()))


if __name__ == "__main__":
    unittest.main()
