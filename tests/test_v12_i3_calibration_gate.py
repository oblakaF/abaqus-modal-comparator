"""V12-I3 — the pure SPECIMEN_ENGINEERING_CALIBRATION scientific gate (SPEC v1.2 §6–§8; D-078; no Abaqus).

The gate consumes explicit M5 / V12-I2 evidence for one specimen and returns PASS or REFUSED with
machine-readable reasons.  It emits no calibration value and no material property; production calibration
execution stays refused until V12-I4.  A confirmed cluster is one governed TERM (pattern, observability,
Birge, LOO) but two physical ROWS (pairing, tracking, non-degradation); the evidence bundle is bound
numerically (pattern ↔ candidate terms ↔ candidate rows, p̂ ↔ model_form_robustness).
"""

from __future__ import annotations

from dataclasses import fields, replace
import json
import math
from pathlib import Path
import re
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.campaign_definition import (
    MATERIAL_IDENTIFICATION,
    CalibrationNotImplementedRefusal,
    at_search_bound,
    parse_campaign_definition,
)
from m4_6_support import FakeExtractor, FakeSolver
from services.identification_campaign_run import CampaignRun, CampaignRunConfig
from services.identification_uncertainty import (
    BirgeStatus,
    ResidualTerm,
    birge_adjustment,
    residual_pattern_test,
    residual_terms,
    statistical_sd,
)
from services.identification_verdict import EvidenceState, GuardEvidence
from services.model_form_robustness import CaseStatus, linearised_model_form_robustness
from services.practical_identifiability import (
    PracticalIdentifiabilityInputError,
    RankStatus,
    analyse_practical_identifiability,
)
from services.specimen_calibration_gate import (
    CONDITIONAL_COVARIANCE,
    PRECISION_CEILING_LN,
    ROW_RELATIVE_ERROR_CEILING,
    CalibrationGateInputs,
    CalibrationGateStatus,
    GovernedRow,
    GovernedTerm,
    ReportingCompleteness,
    evaluate_calibration_gate,
)
from test_identification_uncertainty import CONTEXT, E, G, system
from test_m7_campaign import synthetic_definition, synthetic_specimen
from test_v12_i1_campaign_question import calibration_definition, v12_definition


SIGMA = 0.003
SIGMA_C = math.sqrt(2 * SIGMA ** 2) / 2  # the objective's cluster σ: sqrt(Σ σ_i²) / n_C
E_ROWS = {"R1": (0.50,), "R2": (0.45,), "R3": (0.55,), "R4": (0.40,)}
E_FAMILIES = {"R1": "F1", "R2": "F1", "R3": "F2", "R4": "F2"}
E_FIT = [0.5, -0.4, 0.3, -0.2]  # whitened; Δ ln f = r·σ_term
P_HAT = {"E_in_plane_mpa": 50000.0}
PASS = GuardEvidence("guard", EvidenceState.PASS, "explicit synthetic evidence")
CLUSTER = ("R3", "R4")
CLUSTER_ID = "C(R3+R4)"


def two_parameter_definition(tau_mf=0.02):
    return parse_campaign_definition(calibration_definition(
        tau_mf, run_type="RUN_B", fitted_parameters=["E_in_plane_mpa", "G12_mpa"], fixed_parameters={},
        start={"E_in_plane_mpa": 52000.0, "G12_mpa": 4500.0},
        bounds={"E_in_plane_mpa": [26000.0, 104000.0], "G12_mpa": [2250.0, 9000.0]}, engineering_plausibility={},
        run_b_gate="D-999"))


def build(definition=None, rows=E_ROWS, families=E_FAMILIES, fit=E_FIT, holdout=(("H1", "T", 0.6),),
          parameters=(E,), p_hat=P_HAT, tau=0.02, pattern_tau="declared", clusters=(), cluster_offsets=None,
          baseline=None):
    """A consistent, explicit evidence bundle for one specimen (pure; nothing is solved or read).

    ``fit`` gives the whitened residual per term (single rows first, then clusters).  A cluster's member rows are
    its term Δ ln f ± ``cluster_offsets[cluster]`` (their mean stays the term value).
    """
    definition = definition or parse_campaign_definition(calibration_definition(tau))
    clustered = {m for c in clusters for m in c}
    singles = [r for r in rows if r not in clustered]
    term_sigmas = {**{r: SIGMA for r in singles}, **{f"C({'+'.join(c)})": SIGMA_C for c in clusters}}
    s = system(rows, parameters, sd=SIGMA, clusters=clusters)
    fit_terms = residual_terms(singles, list(clusters), fit, families, term_sigmas)
    held = [ResidualTerm(t, (t,), f, v, SIGMA) for t, f, v in holdout]
    pattern = residual_pattern_test(fit_terms, held, definition.tau_mf if pattern_tau == "declared" else pattern_tau)
    statistical = statistical_sd(s, CONTEXT)
    birge = birge_adjustment(s, statistical, pattern, fit_terms)
    robustness = linearised_model_form_robustness(s, fit_terms, p_hat)
    candidate_terms = [GovernedTerm(t.term_id, "FIT", t.value * t.sigma) for t in fit_terms]
    candidate_terms += [GovernedTerm(t.term_id, "HOLDOUT", t.value * t.sigma) for t in held]
    term_rows = {t.term_id: tuple(t.row_ids) for t in list(fit_terms) + held}
    offsets = cluster_offsets or {}
    candidate_rows = []
    for term in candidate_terms:
        members = term_rows[term.term_id]
        if len(members) == 1:
            candidate_rows.append(GovernedRow(members[0], term.role, term.delta_ln_f))
        else:
            x = offsets.get(term.term_id, 0.0)
            candidate_rows += [GovernedRow(members[0], term.role, term.delta_ln_f + x),
                               GovernedRow(members[1], term.role, term.delta_ln_f - x)]
    baseline_rows = [GovernedRow(r.row_id, r.role, (baseline or {}).get(r.row_id, 0.03 if r.delta_ln_f >= 0 else -0.03))
                     for r in candidate_rows]
    all_rows = [r.row_id for r in candidate_rows]
    return CalibrationGateInputs(
        definition=definition, p_hat=dict(p_hat), fit_families={t.term_id: t.family for t in fit_terms},
        holdout_families={t: f for t, f, _ in holdout}, term_rows=term_rows,
        analysis=analyse_practical_identifiability(s), robustness=robustness, pattern=pattern, statistical=statistical,
        birge=birge, baseline_pair_macs={r.row_id: 0.95 for r in candidate_rows if r.role == "FIT"},
        tracking_macs={r: 0.97 for r in all_rows}, branch_pairing=PASS, registration=PASS, peak_derived_input=PASS,
        candidate_terms=candidate_terms, baseline_rows=baseline_rows, candidate_rows=candidate_rows,
        reporting=ReportingCompleteness(True, True, True, True))


def build_cluster(**changes):
    """F1: rows R1, R2 (single terms); F2: one confirmed cluster C(R3+R4) (one term, two physical rows)."""
    arguments = dict(fit=[0.5, -0.4, 0.3], clusters=(CLUSTER,))
    arguments.update(changes)
    return build(**arguments)


def codes(inputs):
    result = evaluate_calibration_gate(inputs)
    return result, set(result.refusal_codes)


def keys(node) -> set:
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in keys(v)}
    if isinstance(node, list):
        return {k for v in node for k in keys(v)}
    return set()


def with_baseline(inputs, values):
    return replace(inputs, baseline_rows=[GovernedRow(r.row_id, r.role, values.get(r.row_id, r.delta_ln_f))
                                          for r in inputs.baseline_rows])


class _Refusing(unittest.TestCase):
    def refuse(self, inputs, code):
        result, found = codes(inputs)
        self.assertIs(result.status, CalibrationGateStatus.REFUSED)
        self.assertIn(code, found, result.refusal_reasons)
        self.assertTrue(all(r["detail"] for r in result.refusal_reasons))
        return result


class PassingGateTests(unittest.TestCase):
    def test_a_complete_synthetic_case_passes_and_releases_no_value(self):
        for name, inputs in (("single rows", build()), ("with a confirmed cluster", build_cluster())):
            with self.subTest(case=name):
                result = evaluate_calibration_gate(inputs)
                self.assertIs(result.status, CalibrationGateStatus.PASS, result.refusal_reasons)
                self.assertEqual(result.refusal_reasons, ())
                record = result.to_dict()
                for forbidden in ("value", "calibration_value", "reported_value", "estimate", "p_hat",
                                  "material_property", "verdict"):
                    self.assertNotIn(forbidden, keys(record))
                text = json.dumps(record)
                self.assertNotIn("50000", text)  # the candidate parameter is evidence only, never released
                for label in ("IDENTIFIED", "WIDE", "NOT_IDENTIFIABLE"):
                    self.assertNotIn(f'"{label}"', text)
                self.assertEqual(record["scientific_question"], "SPECIMEN_ENGINEERING_CALIBRATION")
                self.assertEqual((record["tau_mf"], record["specimen"]["label"]), (0.02, "A"))
                self.assertEqual(record["observability"]["fit_family_keys"], ["F1", "F2"])
                self.assertEqual(record["observability"]["leave_one_fit_family_out"]["status"],
                                 "AVAILABLE_COMPLETE_LOO")
                self.assertTrue(record["non_degradation"]["same_row_set"])
                self.assertEqual(record["non_degradation"]["rows"], 5)  # R1–R4 and H1, every physical row

    def test_record_is_deterministic_and_carries_no_paths_or_times(self):
        first, second = evaluate_calibration_gate(build()), evaluate_calibration_gate(build())
        self.assertEqual(first.record_hash, second.record_hash)
        text = json.dumps(first.to_dict(), allow_nan=False)
        for marker in (":\\\\", ":/", "utc", "time", "gui"):
            self.assertNotIn(marker, text.lower())

    def test_uncertainty_basis_stays_conditional_on_incomplete_covariance(self):
        inputs = build()
        self.assertEqual(inputs.definition.sigma.measurement_status, "NOT_AVAILABLE")
        result = evaluate_calibration_gate(inputs)
        self.assertTrue(result.passed)  # the gate may pass ...
        basis = result.to_dict()["uncertainty_basis"]
        self.assertEqual(basis["basis"], CONDITIONAL_COVARIANCE)  # ... but stays conditional
        self.assertTrue(basis["conditional_on_available_covariance"])
        self.assertIn("not a complete experimental uncertainty", basis["note"])


class RefusalTests(_Refusing):
    def test_01_wrong_scientific_question(self):
        for definition in (parse_campaign_definition(v12_definition(MATERIAL_IDENTIFICATION)),
                           parse_campaign_definition(synthetic_definition())):
            result = self.refuse(replace(build(), definition=definition), "WRONG_SCHEMA_OR_QUESTION")
            self.assertIsNone(result.precision)  # nothing is evaluated for another question

    def test_02_specimen_count(self):
        inputs = build()
        two = replace(inputs.definition, specimens=inputs.definition.specimens * 2)
        self.refuse(replace(inputs, definition=two), "SPECIMEN_COUNT")

    def test_03_fewer_than_k_plus_one_fit_families(self):
        result = self.refuse(build(families={r: "F1" for r in E_ROWS}), "INSUFFICIENT_FIT_FAMILIES")
        self.assertEqual(result.observability["fit_family_keys"], ["F1"])  # four rows, one family key

    def test_04_no_holdout_family(self):
        self.refuse(build(holdout=()), "NO_HOLDOUT_FAMILY")

    def test_05_holdout_family_overlaps_fit(self):
        self.refuse(build(holdout=(("H1", "F1", 0.6),)), "HOLDOUT_FAMILY_OVERLAPS_FIT")

    def test_06_rank_deficient(self):
        inputs = build()
        self.refuse(replace(inputs, analysis=replace(inputs.analysis, status=RankStatus.RANK_DEFICIENT)),
                    "RANK_DEFICIENT")

    def test_07_one_loo_family_refused(self):
        inputs = build()
        cases = list(inputs.robustness.cases)
        cases[1] = replace(cases[1], status=CaseStatus.REFUSED_RANK_DEFICIENT, shift_ln=None, estimate=None)
        broken = replace(inputs.robustness, cases=tuple(cases), refused_families=(cases[1].family,),
                         supports_green=False)
        result = self.refuse(replace(inputs, robustness=broken), "LOO_INCOMPLETE")
        # the valid-subset range is never used as the model-form half-range
        self.assertIsNone(result.precision["parameters"]["E_in_plane_mpa"]["model_form_half_range_ln"])
        self.assertIsNone(result.precision["parameters"]["E_in_plane_mpa"]["conservative_uncertainty_ln"])

    def test_08_baseline_pair_mac_below_080(self):
        inputs = build()
        self.refuse(replace(inputs, baseline_pair_macs=dict(inputs.baseline_pair_macs, R2=0.7999)),
                    "BASELINE_PAIR_MAC")

    def test_09_tracking_mac_below_090(self):
        inputs = build()
        self.refuse(replace(inputs, tracking_macs=dict(inputs.tracking_macs, H1=0.8999)), "TRACKING_MAC")

    def test_10_branch_or_pairing_loss(self):
        inputs = build()
        self.refuse(replace(inputs, branch_pairing=GuardEvidence("tracking", EvidenceState.FAIL, "x", "branch lost")),
                    "BRANCH_OR_PAIRING_LOSS")
        self.refuse(replace(inputs, tracking_macs={k: v for k, v in inputs.tracking_macs.items() if k != "R1"}),
                    "MISSING_EVIDENCE")

    def test_11_active_parameter_bound(self):
        for value in (26000.0, 104000.0, 104000.0 * (1 + 1e-13), 20000.0):  # robustness computed at that p̂
            with self.subTest(value=value):
                self.refuse(build(p_hat={"E_in_plane_mpa": value}), "ACTIVE_PARAMETER_BOUND")
        self.assertTrue(at_search_bound(26000.0 * (1 + 1e-13), 26000.0, 104000.0))  # the M7 report semantics

    def test_12_13_registration_and_peak_input(self):
        inputs = build()
        failing = GuardEvidence("guard", EvidenceState.FAIL, "x", "failed")
        self.refuse(replace(inputs, registration=failing), "REGISTRATION_LIMITED")
        self.refuse(replace(inputs, peak_derived_input=failing), "PEAK_DERIVED_INPUT")
        missing = GuardEvidence("registration", EvidenceState.NOT_AVAILABLE, "x")
        self.refuse(replace(inputs, registration=missing), "MISSING_EVIDENCE")

    def test_14_v1_pattern_evidence(self):
        self.refuse(build(pattern_tau=None), "PATTERN_EVIDENCE_NOT_V1_2")
        self.refuse(build(pattern_tau=0.01), "TAU_MF_MISMATCH")

    def test_15_systematic_family(self):
        self.refuse(build(fit=[8.0, 9.0, 0.3, -0.2]), "SYSTEMATIC_PATTERN")  # 0.024, 0.027 > τ 0.02

    def test_16_holdout_failure(self):
        self.refuse(build(holdout=(("H1", "T", 7.0),)), "HOLDOUT_FAILURE")  # 0.021 > max(0.009, 0.02)

    def test_17_row_sets_differ(self):
        inputs = build()
        self.refuse(replace(inputs, candidate_rows=inputs.candidate_rows[:-1]), "ROW_SET_MISMATCH")
        swapped = [GovernedRow(r.row_id, "FIT", r.delta_ln_f) for r in inputs.candidate_rows]
        self.refuse(replace(inputs, candidate_rows=swapped), "ROW_SET_MISMATCH")
        self.refuse(replace(inputs, baseline_rows=list(inputs.baseline_rows) + [GovernedRow("X", "FIT", 0.0)]),
                    "ROW_SET_MISMATCH")
        self.refuse(replace(inputs, baseline_rows=list(inputs.baseline_rows) + [inputs.baseline_rows[0]]),
                    "ROW_SET_MISMATCH")  # duplicate row

    def test_18_19_max_and_rms_must_not_worsen(self):
        inputs = build()  # candidate rows: 0.0015, -0.0012, 0.0009, -0.0006 and H1 0.0018
        self.refuse(with_baseline(inputs, {r: 0.0017 for r in ("R1", "R2", "R3", "R4", "H1")}), "MAX_DEGRADED")
        worse_rms = with_baseline(inputs, {"R1": 0.0, "R2": 0.0, "R3": 0.0, "R4": 0.0, "H1": 0.0018})
        result = self.refuse(worse_rms, "RMS_DEGRADED")
        self.assertNotIn("MAX_DEGRADED", result.refusal_codes)  # max not worse (equal); RMS worse
        record = result.non_degradation
        for key in ("baseline_max_abs_delta_ln_f", "candidate_max_abs_delta_ln_f", "baseline_rms_delta_ln_f",
                    "candidate_rms_delta_ln_f", "candidate_max_abs_relative_error", "controlling_row"):
            self.assertIn(key, record)
        self.assertFalse(record["rms_not_worse"])
        # rows need not improve individually: R2 and R4 worse than their baseline rows, max and RMS not worse
        mixed = with_baseline(inputs, {"R1": 0.01, "R2": 0.0001, "R3": 0.001, "R4": 0.0001, "H1": 0.002})
        self.assertFalse({"MAX_DEGRADED", "RMS_DEGRADED"} & set(evaluate_calibration_gate(mixed).refusal_codes))

    def test_20_21_row_relative_error_ceiling(self):
        baseline = {r: 0.1 for r in ("R1", "R2", "R3", "R4", "H1")}
        above = with_baseline(build(fit=[math.log1p(0.0800001) / SIGMA, -25.0, 0.3, -0.2]), baseline)
        result = self.refuse(above, "ROW_RELATIVE_ERROR_ABOVE_CEILING")
        self.assertEqual(result.non_degradation["controlling_row"], "FIT:R1")
        for exact in (0.08, -0.08):
            with self.subTest(relative=exact):
                at = with_baseline(build(fit=[math.log1p(exact) / SIGMA, -25.0 * math.copysign(1, exact), 0.3, -0.2]),
                                   baseline)
                outcome = evaluate_calibration_gate(at)
                self.assertTrue(outcome.passed, outcome.refusal_reasons)  # inclusive 8 %
        self.assertEqual(ROW_RELATIVE_ERROR_CEILING, 0.08)

    def test_22_birge_unavailable(self):
        inputs = build()
        blocked = replace(inputs.birge, status=BirgeStatus.REFUSED_DOF, birge_adjusted_sd_ln=None)
        result = self.refuse(replace(inputs, birge=blocked), "BIRGE_UNAVAILABLE")
        self.assertIsNone(result.precision["parameters"]["E_in_plane_mpa"]["birge_adjusted_sd_ln"])  # no substitute

    def test_23_robustness_missing(self):
        self.refuse(replace(build(), robustness=None), "LOO_INCOMPLETE")

    def test_24_25_conservative_uncertainty_ceiling(self):
        inputs = build()
        for value, passes in ((PRECISION_CEILING_LN, True), (0.0800001, False)):
            with self.subTest(birge=value):
                birge = replace(inputs.birge, birge_adjusted_sd_ln={"E_in_plane_mpa": value})
                outcome = evaluate_calibration_gate(replace(inputs, birge=birge))
                self.assertEqual(outcome.passed, passes, outcome.refusal_reasons)
                self.assertEqual(outcome.precision["parameters"]["E_in_plane_mpa"]["conservative_uncertainty_ln"],
                                 value)
        parameter = inputs.robustness.parameters["E_in_plane_mpa"]
        for half, passes in ((0.08, True), (0.0800001, False)):
            with self.subTest(half_range=half):
                wide = replace(inputs.robustness, parameters={"E_in_plane_mpa": replace(
                    parameter, min_shift_ln=-half, max_shift_ln=half)})
                outcome = evaluate_calibration_gate(replace(inputs, robustness=wide))
                self.assertEqual(outcome.passed, passes, outcome.refusal_reasons)

    def test_26_reporting_incomplete(self):
        inputs = build()
        for flag in ("fit_residuals", "holdout_residuals", "excluded_high_mac_modes", "uncertainty_basis"):
            with self.subTest(missing=flag):
                partial = replace(inputs.reporting, **{flag: False})
                self.refuse(replace(inputs, reporting=partial), "REPORTING_INCOMPLETE")
        self.refuse(replace(inputs, reporting=None), "REPORTING_INCOMPLETE")


class ClusterRowTests(_Refusing):
    """A confirmed cluster: one term for observability / pattern / LOO, two physical rows for everything per row."""

    def test_cluster_is_one_family_observation_and_two_rows(self):
        inputs = build_cluster()
        self.assertEqual(inputs.term_rows[CLUSTER_ID], CLUSTER)
        result = evaluate_calibration_gate(inputs)
        self.assertTrue(result.passed, result.refusal_reasons)
        self.assertEqual(result.observability["fit_family_keys"], ["F1", "F2"])  # the cluster is family F2, once
        self.assertEqual(len(result.observability["leave_one_fit_family_out"]["cases"]), 2)
        self.assertEqual(result.non_degradation["rows"], 5)  # R3 and R4 are checked as two rows
        cluster_term = next(t for t in inputs.pattern.terms if t["term_id"] == CLUSTER_ID)
        self.assertEqual(cluster_term["sigma_term"], SIGMA_C)  # the governed cluster σ, bound to the term Δ ln f
        delta = next(t.delta_ln_f for t in inputs.candidate_terms if t.term_id == CLUSTER_ID)
        self.assertTrue(math.isclose(cluster_term["r"] * cluster_term["sigma_term"], delta, rel_tol=1e-12))

    def test_cluster_mean_cannot_hide_a_row_above_8_percent(self):
        baseline = {r: 0.1 for r in ("R1", "R2", "R3", "R4", "H1")}
        inputs = with_baseline(build_cluster(cluster_offsets={CLUSTER_ID: 0.0775}), baseline)
        cluster = next(t for t in inputs.candidate_terms if t.term_id == CLUSTER_ID)
        self.assertLess(abs(math.expm1(cluster.delta_ln_f)), 0.08)  # the cluster mean is fine ...
        result = self.refuse(inputs, "ROW_RELATIVE_ERROR_ABOVE_CEILING")  # ... a member row is not
        self.assertEqual(result.non_degradation["controlling_row"], "FIT:R3")
        self.assertEqual(result.refusal_codes, ("ROW_RELATIVE_ERROR_ABOVE_CEILING",))

    def test_cluster_member_row_max_and_rms_degradation(self):
        worse_max = with_baseline(build_cluster(cluster_offsets={CLUSTER_ID: 0.05}),
                                  {r: 0.03 for r in ("R1", "R2", "R3", "R4", "H1")})
        self.refuse(worse_max, "MAX_DEGRADED")
        worse_rms = with_baseline(build_cluster(cluster_offsets={CLUSTER_ID: 0.045}),
                                  {"R1": 0.06, "R2": 0.0, "R3": 0.0, "R4": 0.0, "H1": 0.0})
        result = self.refuse(worse_rms, "RMS_DEGRADED")
        self.assertNotIn("MAX_DEGRADED", result.refusal_codes)

    def test_cluster_member_row_mac_evidence(self):
        inputs = build_cluster()
        self.assertIn("R4", inputs.baseline_pair_macs)  # member rows carry their own MAC, no aggregate
        self.assertNotIn(CLUSTER_ID, inputs.baseline_pair_macs)
        missing = {k: v for k, v in inputs.baseline_pair_macs.items() if k != "R4"}
        self.refuse(replace(inputs, baseline_pair_macs=missing), "MISSING_EVIDENCE")
        self.refuse(replace(inputs, baseline_pair_macs=dict(inputs.baseline_pair_macs, R4=0.79)), "BASELINE_PAIR_MAC")
        self.refuse(replace(inputs, tracking_macs=dict(inputs.tracking_macs, R3=0.89)), "TRACKING_MAC")


class BindingTests(unittest.TestCase):
    """Inconsistent evidence is an input error, never a scientific PASS or REFUSED."""

    def raises(self, inputs, text=""):
        with self.assertRaisesRegex(PracticalIdentifiabilityInputError, text):
            evaluate_calibration_gate(inputs)

    def test_extra_mac_keys(self):
        inputs = build_cluster()
        self.raises(replace(inputs, baseline_pair_macs=dict(inputs.baseline_pair_macs, R9=0.99)), "outside")
        self.raises(replace(inputs, baseline_pair_macs=dict(inputs.baseline_pair_macs, H1=0.99)), "outside")
        self.raises(replace(inputs, tracking_macs=dict(inputs.tracking_macs, **{CLUSTER_ID: 0.99})), "outside")
        self.raises(replace(inputs, tracking_macs=dict(inputs.tracking_macs, R1=math.nan)), "finite")

    def test_pattern_and_candidate_terms_describe_one_candidate(self):
        inputs = build()

        def changed(term_id, factor):
            terms = [GovernedTerm(t.term_id, t.role, t.delta_ln_f * factor if t.term_id == term_id else t.delta_ln_f)
                     for t in inputs.candidate_terms]
            rows = [GovernedRow(r.row_id, r.role, r.delta_ln_f * factor if r.row_id == term_id else r.delta_ln_f)
                    for r in inputs.candidate_rows]  # rows follow, so only the pattern binding can fail
            return replace(inputs, candidate_terms=terms, candidate_rows=rows)

        self.raises(changed("R1", 1.01), "pattern term R1")  # numerically different candidate
        self.raises(changed("R1", -1.0), "pattern term R1")  # same magnitude, opposite sign
        self.raises(changed("H1", 1.01), "pattern term H1")

    def test_cluster_term_binds_to_its_member_rows(self):
        inputs = build_cluster(cluster_offsets={CLUSTER_ID: 0.004})
        evaluate_calibration_gate(inputs)  # the cluster pattern term binds through its own Δ ln f
        rows = [GovernedRow(r.row_id, r.role, r.delta_ln_f + 0.001 if r.row_id == "R3" else r.delta_ln_f)
                for r in inputs.candidate_rows]
        self.raises(replace(inputs, candidate_rows=rows), re.escape(CLUSTER_ID))
        moved = dict(inputs.term_rows, **{CLUSTER_ID: ("R3",), "R1": ("R1", "R4")})
        self.raises(replace(inputs, term_rows=moved))
        self.raises(replace(inputs, term_rows=dict(inputs.term_rows, R1=("R1", "R2"))), "distinct")
        self.raises(replace(inputs, term_rows={k: v for k, v in inputs.term_rows.items() if k != "H1"}), "term_rows")

    def test_model_form_robustness_must_be_at_the_evaluated_p_hat(self):
        inputs = build()
        self.raises(replace(inputs, p_hat={"E_in_plane_mpa": 50001.0}), "another p̂")
        for bad in (math.nan, math.inf, -math.inf, True, "50000", None):
            with self.subTest(p_hat=bad):
                self.raises(replace(inputs, p_hat={"E_in_plane_mpa": bad}), "p̂")
        self.raises(replace(inputs, p_hat={"E_in_plane_mpa": -50000.0}), "positive")
        self.raises(replace(inputs, p_hat={"E_in_plane_mpa": 50000.0, "G12_mpa": 4500.0}), "exactly")

    def test_other_inconsistencies(self):
        inputs = build()
        other = build(fit=[0.4, -0.4, 0.3, -0.2])
        self.raises(replace(inputs, pattern=other.pattern), "Birge")
        self.raises(replace(inputs, fit_families=dict(inputs.fit_families, R4="F3")), "family mapping")
        self.raises(replace(inputs, candidate_terms=inputs.candidate_terms[:-1]), "candidate_terms")
        with self.assertRaises(TypeError):
            evaluate_calibration_gate({"definition": inputs.definition})


class PrecisionTests(unittest.TestCase):
    ROWS = {"R1": (0.50, 0.010), "R2": (0.45, 0.004), "R3": (0.55, 0.012), "R4": (0.40, 0.005),
            "R5": (0.48, 0.015), "R6": (0.52, 0.003)}
    FAMILIES = {"R1": "F1", "R2": "F1", "R3": "F2", "R4": "F2", "R5": "F3", "R6": "F3"}

    def inputs(self, tau=0.02):
        return build(definition=two_parameter_definition(tau), rows=self.ROWS, families=self.FAMILIES,
                     fit=[0.5, -0.4, 0.3, -0.2, 0.1, -0.3], parameters=(E, G),
                     p_hat={"E_in_plane_mpa": 50000.0, "G12_mpa": 4500.0})

    def test_one_parameter_above_the_ceiling_refuses_the_whole_gate(self):
        result = evaluate_calibration_gate(self.inputs())
        parameters = result.precision["parameters"]
        self.assertTrue(parameters["E_in_plane_mpa"]["pass"])
        self.assertFalse(parameters["G12_mpa"]["pass"])  # weakly observed G12
        self.assertIs(result.status, CalibrationGateStatus.REFUSED)
        self.assertEqual([r["code"] for r in result.refusal_reasons], ["CONSERVATIVE_ABOVE_CEILING"])
        for item in parameters.values():
            self.assertEqual(set(item), {"birge_adjusted_sd_ln", "model_form_half_range_ln",
                                         "conservative_uncertainty_ln", "pass"})
            self.assertEqual(item["conservative_uncertainty_ln"],
                             max(item["birge_adjusted_sd_ln"], item["model_form_half_range_ln"]))

    def test_tau_mf_never_enters_the_precision_envelope(self):
        strict, loose = evaluate_calibration_gate(self.inputs(0.005)), evaluate_calibration_gate(self.inputs(0.02))
        self.assertEqual(strict.precision, loose.precision)  # τ_mf changes the pattern only, never the envelope
        self.assertFalse(loose.precision["tau_mf_in_envelope"])
        inputs = self.inputs()
        sd = inputs.birge.birge_adjusted_sd_ln["E_in_plane_mpa"]
        item = inputs.robustness.parameters["E_in_plane_mpa"]
        expected = max(sd, 0.5 * (item.max_shift_ln - item.min_shift_ln))
        self.assertAlmostEqual(loose.precision["parameters"]["E_in_plane_mpa"]["conservative_uncertainty_ln"],
                               expected, places=12)
        self.assertNotIn("tau", json.dumps(inputs.birge.to_dict()) + json.dumps(inputs.statistical.to_dict())
                         + json.dumps(inputs.robustness.to_dict()))


class SeparationTests(unittest.TestCase):
    def test_material_refusal_is_not_converted_into_a_calibration_value(self):
        self.assertFalse({f.name for f in fields(CalibrationGateInputs)} & {"verdict", "material_verdict"})
        material = replace(build(), definition=parse_campaign_definition(v12_definition(MATERIAL_IDENTIFICATION)))
        result = evaluate_calibration_gate(material)  # e.g. a NOT_IDENTIFIABLE material campaign
        self.assertEqual(result.refusal_codes, ("WRONG_SCHEMA_OR_QUESTION",))
        self.assertFalse({"value", "calibration_value", "estimate"} & keys(result.to_dict()))


class ProductionStillBlockedTests(unittest.TestCase):
    def test_calibration_campaign_execution_is_still_refused(self):
        calibration = parse_campaign_definition(calibration_definition())
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            item, store = synthetic_specimen(calibration, "A", tmp)
            solver = FakeSolver()
            config = CampaignRunConfig(tmp / "runs", {"synthetic": store}, "abq2024.bat", solver, FakeExtractor(), {},
                                       "m" * 64)
            with self.assertRaises(CalibrationNotImplementedRefusal) as refused:
                CampaignRun(calibration, [item], "m" * 64, config)
            self.assertIn("scientific gate (V12-I3)", str(refused.exception))
            self.assertIn("blocked pending V12-I5", str(refused.exception))
            self.assertEqual(solver.commands, [])
            self.assertFalse((tmp / "runs").exists())


if __name__ == "__main__":
    unittest.main()
