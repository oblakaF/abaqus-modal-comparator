"""M5.9 verdict engine: guard-by-guard behaviour on explicit synthetic evidence (no Abaqus)."""

from __future__ import annotations

from dataclasses import replace
import inspect
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import m5_gate_support as S
from services.identification_verdict import (
    IDENTIFIED_LIMIT_LN,
    WIDE_LIMIT_LN,
    EvidenceState,
    GuardEvidence,
    Verdict,
    VerdictContext,
    decide_verdicts,
    fitting_pair_mac_evidence,
)
from services.practical_identifiability import G12_PARAMETER, PracticalIdentifiabilityInputError


E_ID = "E_in_plane_mpa"


def verdicts(inputs):
    return decide_verdicts(inputs).verdicts


class GuardTests(unittest.TestCase):
    def test_positive_case_baseline(self):
        report = decide_verdicts(S.case_positive()[0])
        self.assertEqual({k: v.verdict for k, v in report.verdicts.items()},
                         {E_ID: Verdict.IDENTIFIED, G12_PARAMETER: Verdict.IDENTIFIED})
        self.assertNotIn("k_core", report.verdicts)  # nuisance parameters are not material verdict subjects
        self.assertEqual(report.guards["family_consistency"], "NOT_AVAILABLE")  # D-044, synthetic gate

    def test_every_guard_failure_or_absence_blocks(self):
        failing = {
            "fitting_pair_mac": fitting_pair_mac_evidence({"R1": 0.75, "R2": 0.95}, S.SYNTHETIC),
            "registration": GuardEvidence("registration", EvidenceState.FAIL, S.SYNTHETIC, "registration-limited"),
            "peak_derived_input": GuardEvidence("peak_derived_input", EvidenceState.FAIL, S.SYNTHETIC, "peak-derived"),
            "tracking": GuardEvidence("tracking", EvidenceState.FAIL, S.SYNTHETIC, "BRANCH_LOSS"),
            "family_consistency": GuardEvidence("family_consistency", EvidenceState.FAIL, S.SYNTHETIC, "Δχ² fail"),
        }
        expected = {"fitting_pair_mac": "FITTING_PAIR_MAC", "registration": "REGISTRATION_LIMITED",
                    "peak_derived_input": "PEAK_DERIVED_INPUT", "tracking": "BRANCH_OR_PAIRING_LOSS",
                    "family_consistency": "FAMILY_CONSISTENCY"}
        for name, guard in failing.items():
            with self.subTest(guard=name, state="FAIL"):
                result = verdicts(S.case_positive(**{name: guard})[0])
                self.assertTrue(all(v.verdict is Verdict.NOT_IDENTIFIABLE for v in result.values()))
                self.assertTrue(any(r.startswith(expected[name]) for r in result[E_ID].reasons))
        for name in ("fitting_pair_mac", "registration", "peak_derived_input", "tracking"):
            with self.subTest(guard=name, state="NOT_AVAILABLE"):
                missing = GuardEvidence(name, EvidenceState.NOT_AVAILABLE, S.SYNTHETIC)
                result = verdicts(S.case_positive(**{name: missing})[0])
                self.assertTrue(all(v.verdict is Verdict.NOT_IDENTIFIABLE for v in result.values()))
                self.assertTrue(any(r.startswith("MISSING_EVIDENCE") for r in result[E_ID].reasons))

    def test_family_consistency_not_available_is_not_pass_in_production(self):
        inputs = S.case_positive(context=VerdictContext.PRODUCTION)[0]
        result = verdicts(inputs)
        self.assertTrue(all(v.verdict is Verdict.NOT_IDENTIFIABLE for v in result.values()))
        self.assertTrue(any("FAMILY_CONSISTENCY" in r for r in result[E_ID].reasons))
        passed = GuardEvidence("family_consistency", EvidenceState.PASS, "explicit family-consistency evidence")
        production = verdicts(S.case_positive(context=VerdictContext.PRODUCTION, family_consistency=passed)[0])
        self.assertIs(production[E_ID].verdict, Verdict.IDENTIFIED)

    def test_sandwich_g12_policy(self):
        passed = GuardEvidence("family_consistency", EvidenceState.PASS, "explicit family-consistency evidence")
        # Production: a synthetic-definition constraint does not count, and neither does a provisional prior.
        production = verdicts(S.case_positive(context=VerdictContext.PRODUCTION, family_consistency=passed)[0])
        self.assertIs(production[G12_PARAMETER].verdict, Verdict.NOT_IDENTIFIABLE)
        self.assertTrue(any(r.startswith("BARE_PLATE_REQUIRED") for r in production[G12_PARAMETER].reasons))
        real_but_provisional = S.sandwich(independent=True, synthetic_definition=False, provisional=True)
        blocked = verdicts(S.case_positive(context=VerdictContext.PRODUCTION, family_consistency=passed,
                                           sandwich_evidence=real_but_provisional)[0])
        self.assertTrue(any(r.startswith("NUISANCE_NOT_INDEPENDENTLY_CONSTRAINED")
                            for r in blocked[G12_PARAMETER].reasons))
        independent = S.sandwich(independent=True, synthetic_definition=False, provisional=False)
        allowed = verdicts(S.case_positive(context=VerdictContext.PRODUCTION, family_consistency=passed,
                                           sandwich_evidence=independent)[0])
        self.assertIs(allowed[G12_PARAMETER].verdict, Verdict.IDENTIFIED)
        # A constraint record cannot hide a PROVISIONAL prior that the system itself carries.
        provisional_prior = (S.NuisancePrior("k_core", 0.0, 0.05, S.SYNTHETIC, True),)
        hidden = verdicts(S.case_positive(context=VerdictContext.PRODUCTION, family_consistency=passed,
                                          sandwich_evidence=independent, priors=provisional_prior)[0])
        self.assertIs(hidden[G12_PARAMETER].verdict, Verdict.NOT_IDENTIFIABLE)
        # Not applicable: G12 estimated with a bare-plate primary source is not subject to the sandwich rule.
        bare = verdicts(S.case_positive(sandwich_evidence=S.sandwich(applies=False))[0])
        self.assertIs(bare[G12_PARAMETER].verdict, Verdict.IDENTIFIED)

    def test_upstream_refusal_blocks(self):
        result = verdicts(S.case_positive(upstream=("M4 evaluation REFUSED: BRANCH_LOSS",))[0])
        self.assertTrue(all(v.verdict is Verdict.NOT_IDENTIFIABLE for v in result.values()))

    def test_wide_never_hides_a_block(self):
        inputs = S.case_wide()[0]
        self.assertIs(verdicts(inputs)[E_ID].verdict, Verdict.WIDE)
        blocked = replace(inputs, registration=GuardEvidence("registration", EvidenceState.FAIL, S.SYNTHETIC))
        self.assertIs(verdicts(blocked)[E_ID].verdict, Verdict.NOT_IDENTIFIABLE)
        no_robustness = replace(inputs, robustness=None)
        self.assertIs(verdicts(no_robustness)[E_ID].verdict, Verdict.NOT_IDENTIFIABLE)

    def test_thresholds_are_ln_space_and_values_reported_only_when_permitted(self):
        self.assertEqual((IDENTIFIED_LIMIT_LN, WIDE_LIMIT_LN), (0.05, 0.08))
        wide = verdicts(S.case_wide()[0])[E_ID]
        self.assertTrue(IDENTIFIED_LIMIT_LN < wide.conservative_ln <= WIDE_LIMIT_LN)
        self.assertEqual(wide.conservative_ln, max(wide.birge_adjusted_sd_ln, wide.model_form_robustness["half_range_ln"]))
        self.assertEqual(wide.reported_value, wide.fitted_estimate)
        absorbed = verdicts(S.case_absorption()[0])[G12_PARAMETER]
        self.assertIsNone(absorbed.reported_value)
        self.assertEqual(absorbed.fitted_estimate, S.P_HAT[G12_PARAMETER])  # preserved for provenance only

    def test_no_override_and_binding(self):
        self.assertEqual(list(inspect.signature(decide_verdicts).parameters), ["inputs"])
        with self.assertRaises(TypeError):
            decide_verdicts({"verdict": "IDENTIFIED"})
        inputs, _ = S.case_positive()
        other, _ = S.case_wide()
        with self.assertRaises(PracticalIdentifiabilityInputError):
            decide_verdicts(replace(inputs, robustness=other.robustness))
        with self.assertRaises(PracticalIdentifiabilityInputError):
            decide_verdicts(replace(inputs, birge=other.birge))

    def test_labels_kept_separate_and_deterministic(self):
        report = decide_verdicts(S.case_positive()[0])
        record = report.to_dict()
        entry = record["verdicts"][E_ID]
        for label in ("statistical_sd_ln", "birge_adjusted_sd_ln", "model_form_robustness", "conservative_ln"):
            self.assertIn(label, entry)
        self.assertFalse(any(key == "uncertainty" for key in entry))
        self.assertEqual(report.record_hash, decide_verdicts(S.case_positive()[0]).record_hash)
        json.dumps(record, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
