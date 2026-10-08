"""SPEC v1.2 policy draft — design-level checks only (PROPOSED, not normative; no production behaviour).

The draft must stay a proposal, keep SPEC v1.1 untouched, keep τ_mf out of Σ / the objective / §13 and out of any
parameter-uncertainty argument, require a pre-declared calibration question without automatic fallback, and leave
the historical M7 records untouched.  Nothing in ``src`` may implement τ_mf or the calibration class before
acceptance.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.identification_run import canonical_hash


DOCS = ROOT / "docs" / "auto_id"
SPEC_V1_1_CONTENT_SHA256 = "62f206176a73c224f6f8fea0b2aed84c8154b9eb30bee87240d2c0b808ebb665"  # at main 9bff6c7


def _text(name: str) -> str:
    return (DOCS / name).read_text(encoding="utf-8")


def _keys(node) -> set:
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in _keys(v)}
    if isinstance(node, list):
        return {k for v in node for k in _keys(v)}
    return set()


class PolicyDraftTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads(_text("SPEC_V1_2_POLICY_OPTIONS.json"))
        self.draft = " ".join(_text("SPEC_V1_2_DRAFT.md").split())  # phrases may wrap across lines

    def test_draft_is_a_proposal_and_v1_1_is_unchanged(self):
        self.assertIn("PROPOSED — NOT NORMATIVE — AWAITING FINAL SUPERVISOR ACCEPTANCE", self.draft)
        self.assertEqual(self.policy["status"], "PROPOSED_NOT_NORMATIVE")
        content = (DOCS / "SPEC_V1_1.md").read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual(hashlib.sha256(content).hexdigest(), SPEC_V1_1_CONTENT_SHA256)
        self.assertFalse((DOCS / "SPEC_V1_2.md").exists())  # no normative v1.2

    def test_upper_rule_is_amended_with_two_predeclared_questions_and_no_fallback(self):
        self.assertIn("## 1. Amended §1 — Upper rule", self.draft)
        for phrase in ("**A. Material identification.**", "**B. Specimen / FE-model calibration.**",
                       "**No automatic fallback.**", "selected before execution"):
            self.assertIn(phrase, self.draft)
        rule = self.policy["upper_rule"]
        self.assertTrue(rule["amended"] and rule["question_declared_before_execution"] and rule["question_identity_bound"])
        self.assertFalse(rule["automatic_fallback_from_refusal_to_calibration"])
        self.assertTrue(rule["material_verdict_always_computed_and_shown_separately"])

    def test_tau_mf_is_a_campaign_level_frequency_tolerance_with_maximum_0_02(self):
        props = self.policy["tau_mf_properties"]
        self.assertEqual(props["specification_maximum"], 0.02)
        self.assertTrue(props["campaign_may_declare_smaller"])
        self.assertFalse(props["campaign_may_declare_larger"])
        for key in ("per_mode", "per_family", "per_parameter", "selected_after_fit_result"):
            self.assertFalse(props[key], key)
        self.assertTrue(props["declared_before_execution"] and props["identity_bound"])
        accepted = [o for o in self.policy["options"] if o["accepted"]]
        self.assertEqual([(o["id"], o["tau_mf"]) for o in accepted], [("A", 0.02)])
        sigma = self.policy["threshold_arithmetic_reference"]["sigma_setup_ln"]
        for option in self.policy["options"]:
            if isinstance(option["tau_mf"], float):
                with self.subTest(option=option["id"]):
                    self.assertAlmostEqual(option["holdout_bound_ln"], max(3 * sigma, option["tau_mf"]))
                    self.assertAlmostEqual(option["family_pattern_bound_ln"], max(2 * sigma, option["tau_mf"]))

    def test_tau_mf_never_enters_sigma_objective_or_section_13(self):
        props = self.policy["tau_mf_properties"]
        for key in ("in_sigma", "in_covariance_matrix", "in_objective", "in_whitening", "inflates_uncertainty",
                    "used_by_family_consistency"):
            self.assertFalse(props[key], key)
        family = self.policy["family_consistency"]
        self.assertTrue(family["unchanged"])
        self.assertFalse(family["uses_tau_mf"] or family["tau_mf_in_sigma_delta_chi2_bootstrap_or_p"]
                         or family["tau_mf_can_convert_fail_to_pass"] or family["not_evaluable_produces_family_value"])
        self.assertEqual((family["alpha"], family["fail_output"]), (0.01, "NO_GLOBAL_PARAMETER_VALUE"))
        self.assertIn("τ_mf can never convert family_consistency FAIL into PASS", self.draft)

    def test_no_parameter_uncertainty_is_inferred_from_tau_mf(self):
        self.assertNotIn("implied_min_parameter_scale_ln_e", _keys(self.policy))
        self.assertNotIn("parameter_scale_reference", _keys(self.policy))
        props = self.policy["tau_mf_properties"]
        self.assertFalse(props["is_parameter_uncertainty"] or props["is_calibration_uncertainty"]
                         or props["converted_to_parameter_uncertainty"])
        self.assertFalse(self.policy["rules"]["passing_a_tau_gate_establishes_parameter_precision"])
        self.assertIn("No mathematical conversion from τ_mf to a parameter uncertainty is made or used", self.draft)
        self.assertIn("does not itself establish parameter precision", self.draft)
        for withdrawn in ("inside the IDENTIFIED threshold", "inside the 5 % IDENTIFIED"):
            self.assertNotIn(withdrawn, self.draft)

    def test_calibration_is_predeclared_separately_labelled_and_not_implemented(self):
        calibration = self.policy["specimen_engineering_calibration"]
        self.assertFalse(calibration["implemented"])
        self.assertTrue(calibration["intent_declared_before_execution"] and calibration["intent_identity_bound"])
        self.assertFalse(calibration["automatic_fallback_from_not_identifiable"])
        self.assertEqual(calibration["labels"], ["SPECIMEN_ENGINEERING_CALIBRATION", "NOT_A_MATERIAL_PROPERTY",
                                                 "NOT_TRANSFERABLE_WITHOUT_VALIDATION"])
        self.assertEqual(set(calibration["required_identities"]),
                         {"physical_specimen", "test_run", "forward_model", "inp_sha256", "registration",
                          "campaign_run", "tau_mf"})
        self.assertFalse(calibration["appears_in_material_property_field"])
        self.assertFalse(calibration["manual_override"] or calibration["post_hoc_mode_substitution"]
                         or calibration["lowered_mac"])
        self.assertEqual(calibration["uncertainty_reporting"]["tau_mf_reported_as"], "ACCEPTANCE_TOLERANCE")
        self.assertEqual(calibration["uncertainty_reporting"]["conditional_wording"],
                         "UNCERTAINTY_CONDITIONAL_ON_AVAILABLE_COVARIANCE")
        for path in (ROOT / "src").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(module=path.name):
                self.assertNotIn("tau_mf", text)
                self.assertNotIn("SPECIMEN_ENGINEERING_CALIBRATION", text)

    def test_non_degradation_checks_max_and_rms_with_an_8_percent_ceiling(self):
        rule = self.policy["specimen_engineering_calibration"]["non_degradation"]
        self.assertTrue(rule["max_abs_ln_not_worse"] and rule["rms_ln_not_worse"])
        self.assertEqual(rule["row_ceiling_relative_error"], 0.08)
        self.assertFalse(rule["every_row_must_improve"] or rule["campaign_global_maximum_used"])
        self.assertIn("RMS_i Δ ln f_i(candidate) ≤ RMS_i Δ ln f_i(baseline)", self.draft)
        self.assertIn("≤ 8 %", self.draft)

    def test_minimum_observability_for_one_parameter(self):
        rule = self.policy["specimen_engineering_calibration"]["minimum_observability"]
        self.assertEqual(rule["k1_minimum"], {"fit_families": 2, "holdout_families": 1})
        self.assertEqual((rule["fit_families"], rule["holdout_families"], rule["cluster_counts_as_families"]),
                         ("k + 1", 1, 1))
        self.assertTrue(rule["full_rank"] and rule["leave_one_fit_family_out_complete"])
        self.assertFalse(rule["single_torsion_sensitive_mixed_mode_sufficient"])

    def test_historical_m7_records_cannot_be_mutated_or_relabelled(self):
        history = self.policy["historical_results"]
        self.assertFalse(history["records_mutable"] or history["relabel_as_v1_2_calibration"])
        self.assertEqual(history["allowed_use_after_v1_2"], "RETROSPECTIVE_DIAGNOSTIC_ONLY")
        self.assertIn("new v1.2 campaign / run identity", history["accepted_v1_2_calibration_requires"])
        closure = json.loads((DOCS / "campaigns" / "M7_CLOSURE.json").read_text(encoding="utf-8"))
        for key, name in (("run_a", "M7_RUN_A.result.json"), ("run_b", "M7_RUN_B.result.json")):
            record = json.loads((DOCS / "campaigns" / name).read_text(encoding="utf-8"))
            with self.subTest(run=key):
                self.assertEqual(canonical_hash(record), closure[key]["result_record"]["canonical_content_sha256"])
                self.assertNotIn("SPECIMEN_ENGINEERING_CALIBRATION", json.dumps(record))

    def test_review_covers_every_required_topic(self):
        review = _text("SPEC_V1_2_POLICY_REVIEW.md")
        for topic in ("**Upper rule (§1)**", "**τ_mf**", "**Holdout**", "**Pattern test**", "**Family consistency**",
                      "**Specimen calibration class**", "**Per-specimen non-degradation**", "**Minimum observability**",
                      "**S8 output**", "**Uncertainty wording**", "**Scan / excluded-mode diagnostics**",
                      "**Historical data**"):
            self.assertIn(f"| {topic} |", review)
        self.assertIn("is **withdrawn**", review)


if __name__ == "__main__":
    unittest.main()
