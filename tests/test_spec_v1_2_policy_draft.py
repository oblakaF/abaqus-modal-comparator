"""SPEC v1.2 policy draft — design-level checks only (PROPOSED, not normative; no production behaviour).

The draft must stay a proposal, keep SPEC v1.1 untouched, keep τ_mf out of Σ / the objective / §13, and its
threshold table must follow from its stated rules.  Nothing in ``src`` may implement τ_mf before acceptance.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "auto_id"
SPEC_V1_1_CONTENT_SHA256 = "62f206176a73c224f6f8fea0b2aed84c8154b9eb30bee87240d2c0b808ebb665"  # at main 9bff6c7


def _text(name: str) -> str:
    return (DOCS / name).read_text(encoding="utf-8")


class PolicyDraftTests(unittest.TestCase):
    def setUp(self):
        self.options = json.loads(_text("SPEC_V1_2_POLICY_OPTIONS.json"))

    def test_draft_is_a_proposal_and_v1_1_is_unchanged(self):
        self.assertIn("PROPOSED — NOT NORMATIVE — AWAITING SUPERVISOR ACCEPTANCE", _text("SPEC_V1_2_DRAFT.md"))
        self.assertEqual(self.options["status"], "PROPOSED_NOT_NORMATIVE")
        content = (DOCS / "SPEC_V1_1.md").read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual(hashlib.sha256(content).hexdigest(), SPEC_V1_1_CONTENT_SHA256)
        self.assertFalse((DOCS / "SPEC_V1_2.md").exists())  # no normative v1.2

    def test_threshold_table_follows_the_stated_rules(self):
        sigma = self.options["threshold_arithmetic_reference"]["sigma_setup_ln"]
        self.assertEqual(self.options["v1_1_bounds_ln"], {"holdout": round(3 * sigma, 12),
                                                          "family_pattern": round(2 * sigma, 12)})
        s_max = self.options["parameter_scale_reference"]["max_frequency_sensitivity_s_e"]
        for option in self.options["options"]:
            if not isinstance(option["tau_mf"], float):
                self.assertFalse(option["recommended"])  # option C (per family) is not recommended
                continue
            with self.subTest(option=option["id"]):
                tau = option["tau_mf"]
                self.assertAlmostEqual(option["holdout_bound_ln"], max(3 * sigma, tau))
                self.assertAlmostEqual(option["family_pattern_bound_ln"], max(2 * sigma, tau))
                self.assertAlmostEqual(option["implied_min_parameter_scale_ln_e"], tau / s_max)
        recommended = [o for o in self.options["options"] if o["recommended"]]
        self.assertEqual([o["id"] for o in recommended], ["A"])
        self.assertEqual(self.options["tau_mf_properties"]["specification_maximum"], recommended[0]["tau_mf"])

    def test_tau_mf_never_enters_sigma_objective_or_family_consistency(self):
        props = self.options["tau_mf_properties"]
        for key in ("in_sigma", "in_objective", "in_whitening", "inflates_uncertainty", "used_by_family_consistency",
                    "per_mode_or_family"):
            self.assertFalse(props[key], key)
        self.assertTrue(props["declared_before_execution"] and props["identity_bound"])
        family = self.options["family_consistency"]
        self.assertEqual((family["uses_tau_mf"], family["tau_mf_can_convert_fail_to_pass"], family["alpha"]),
                         (False, False, 0.01))
        self.assertIn("τ_mf can never convert family_consistency FAIL into PASS", _text("SPEC_V1_2_DRAFT.md"))

    def test_choice_was_frozen_without_historical_results(self):
        freeze = self.options["freeze"]
        self.assertTrue(freeze["declared_before_new_fe_results"])
        self.assertFalse(freeze["selected_from_historical_runs"])
        self.assertFalse(freeze["evaluated_on_historical_runs"])
        self.assertEqual(self.options["historical_results"]["run_a_family"], "NO_GLOBAL_PARAMETER_VALUE (v1.1; unchanged)")

    def test_specimen_calibration_is_drafted_not_implemented(self):
        calibration = self.options["specimen_engineering_calibration"]
        self.assertFalse(calibration["implemented"])
        self.assertFalse(calibration["replaces_or_softens_a_refusal"])
        self.assertEqual(calibration["qualifiers"], ["NOT_A_MATERIAL_PROPERTY", "NOT_TRANSFERABLE_WITHOUT_VALIDATION"])
        self.assertEqual(calibration["minimum_observability"]["one_parameter_minimum"], "2 FIT families + 1 HOLDOUT family")
        for path in (ROOT / "src").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(module=path.name):
                self.assertNotIn("tau_mf", text)
                self.assertNotIn("SPECIMEN_ENGINEERING_CALIBRATION", text)

    def test_review_covers_every_required_topic(self):
        review = _text("SPEC_V1_2_POLICY_REVIEW.md")
        for topic in ("**τ_mf**", "**Holdout**", "**Pattern test**", "**Family consistency**",
                      "**Specimen calibration class**", "**Per-specimen non-degradation**", "**Minimum observability**",
                      "**S8 output**", "**Uncertainty wording**", "**Scan / excluded-mode diagnostics**"):
            self.assertIn(f"| {topic} |", review)


if __name__ == "__main__":
    unittest.main()
