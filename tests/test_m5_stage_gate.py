"""M5 stage gate (SPEC §17 M5; ROADMAP M5 GATE; M5_DECISION_RECORD §19).

Deterministic and records/synthetic only: 0 Abaqus, 0 Abaqus Python, no temporary D:\\ dependencies.
- synthetic G12 absorbed by k_core gives q_G ≈ 0 (diagnostic) and NOT_IDENTIFIABLE;
- rank-deficient cases cannot be overridden;
- systematic model error gives no green verdict;
- WIDE only when every scientific guard passes;
- the uncertainty quantities stay separately labelled;
- the accepted M4.9 twin is a consistent, non-refused synthetic records-based control;
- the M3 / M4 accepted contracts are unchanged.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import inspect
import json
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import m5_gate_support as S
from domain.forward_model_manifest import load_forward_model_manifest
from services.identification_uncertainty import BirgeStatus, PatternStatus, StatisticalStatus
from services.identification_verdict import (
    EvidenceState,
    GuardEvidence,
    Verdict,
    VerdictContext,
    decide_verdicts,
)
from services.practical_identifiability import (
    G12_PARAMETER,
    RCOND,
    RankStatus,
    analyse_practical_identifiability,
)


E_ID = "E_in_plane_mpa"


class M5GateTests(unittest.TestCase):
    def test_1_k_core_absorption(self):
        inputs, chain = S.case_absorption()
        report = decide_verdicts(inputs)
        self.assertLess(report.q_g, 0.05)  # diagnostic only (test tolerance, not policy)
        g12 = report.verdicts[G12_PARAMETER]
        self.assertIs(g12.verdict, Verdict.NOT_IDENTIFIABLE)
        # The verdict follows from the full calculation (sd_ln > 0.08), not from a q_G threshold.
        self.assertTrue(any(r.startswith("SD_ABOVE_8_PERCENT") for r in g12.reasons))
        self.assertFalse(any("q_G" in r for r in g12.reasons))
        self.assertIs(report.verdicts[E_ID].verdict, Verdict.IDENTIFIED)

    def test_2_rank_deficient_is_a_hard_block(self):
        inputs, chain = S.case_rank_deficient()
        self.assertIs(chain.analysis.status, RankStatus.RANK_DEFICIENT)
        self.assertEqual(chain.analysis.rcond, RCOND)
        self.assertIsNone(chain.analysis.covariance_ln)  # no pseudo-inverse
        self.assertIs(chain.statistical.status, StatisticalStatus.REFUSED_RANK_DEFICIENT)
        self.assertIs(chain.birge.status, BirgeStatus.REFUSED_STATISTICAL)
        self.assertIsNone(chain.robustness)
        report = decide_verdicts(inputs)
        for verdict in report.verdicts.values():
            self.assertIs(verdict.verdict, Verdict.NOT_IDENTIFIABLE)
            self.assertTrue(verdict.reasons[0].startswith("RANK_DEFICIENT"))
            self.assertIsNone(verdict.reported_value)
        # No override exists anywhere on the path.
        self.assertEqual(list(inspect.signature(analyse_practical_identifiability).parameters), ["system"])
        self.assertEqual(list(inspect.signature(decide_verdicts).parameters), ["inputs"])
        with self.assertRaises(Exception):
            chain.analysis.status = RankStatus.FULL_RANK

    def test_3_systematic_model_error_gives_no_green_verdict(self):
        for holdout in (False, True):
            with self.subTest(holdout=holdout):
                inputs, chain = S.case_model_error(holdout=holdout)
                self.assertIs(chain.pattern.status, PatternStatus.FAIL)
                self.assertIs(chain.birge.status, BirgeStatus.BLOCKED_PATTERN)
                self.assertIsNone(chain.birge.birge_adjusted_sd_ln)
                self.assertIs(chain.statistical.status, StatisticalStatus.AVAILABLE)  # preserved separately
                report = decide_verdicts(inputs)
                self.assertTrue(all(v.verdict is Verdict.NOT_IDENTIFIABLE for v in report.verdicts.values()))

    def test_4_wide_only_when_all_guards_pass(self):
        inputs, _ = S.case_wide()
        self.assertIs(decide_verdicts(inputs).verdicts[E_ID].verdict, Verdict.WIDE)
        for name in ("registration", "tracking", "peak_derived_input", "fitting_pair_mac"):
            failed = replace(inputs, **{name: GuardEvidence(name, EvidenceState.FAIL, S.SYNTHETIC)})
            with self.subTest(guard=name):
                self.assertIs(decide_verdicts(failed).verdicts[E_ID].verdict, Verdict.NOT_IDENTIFIABLE)
        production = replace(inputs, context=VerdictContext.PRODUCTION)  # family consistency NOT_AVAILABLE
        self.assertIs(decide_verdicts(production).verdicts[E_ID].verdict, Verdict.NOT_IDENTIFIABLE)

    def test_5_uncertainty_quantities_stay_separate(self):
        report = decide_verdicts(S.case_positive()[0])
        entry = report.to_dict()["verdicts"][E_ID]
        self.assertIn("statistical_sd_ln", entry)
        self.assertIn("birge_adjusted_sd_ln", entry)
        self.assertIn("model_form_robustness", entry)
        self.assertNotIn("uncertainty", entry)
        self.assertIn("kept separately", report.note)
        _, chain = S.case_positive()
        self.assertEqual(chain.statistical.to_dict()["quantity"], "statistical_sd")
        self.assertEqual(chain.birge.to_dict()["quantity"], "birge_adjusted_sd")
        self.assertEqual(chain.robustness.to_dict()["quantity"], "model_form_robustness")

    def test_missing_physical_evidence_case(self):
        report = decide_verdicts(S.case_missing_physical_evidence()[0])
        g12 = report.verdicts[G12_PARAMETER]
        self.assertIs(g12.verdict, Verdict.NOT_IDENTIFIABLE)
        self.assertTrue(any(r.startswith("BARE_PLATE_REQUIRED") for r in g12.reasons))
        self.assertTrue(any(r.startswith("NUISANCE_NOT_INDEPENDENTLY_CONSTRAINED") for r in g12.reasons))
        self.assertIs(report.verdicts[E_ID].verdict, Verdict.IDENTIFIED)

    def test_positive_control(self):
        report = decide_verdicts(S.case_positive()[0])
        self.assertEqual({v.verdict for v in report.verdicts.values()}, {Verdict.IDENTIFIED})


class TwinControlTests(unittest.TestCase):
    """6: the accepted M4.9 twin, synthetic records-based control (not real-specimen identification)."""

    def test_6_twin_control_consistent_and_non_refused(self):
        inputs, chain = S.twin_control()
        loop = json.loads((ROOT / "docs/auto_id/twins/SP13_identification_loop/loop_result.json").read_text(encoding="utf-8"))
        self.assertIs(chain.analysis.status, RankStatus.FULL_RANK)
        for i, name in enumerate(chain.analysis.parameter_ids):  # the M5 posterior of this system reproduces the record
            self.assertAlmostEqual(chain.statistical.statistical_sd_ln[name], loop["local_sd_ln"][i], places=9)
        self.assertIs(chain.pattern.status, PatternStatus.PASS)
        self.assertIs(chain.birge.status, BirgeStatus.AVAILABLE)
        self.assertEqual(chain.birge.dof, 19)
        self.assertTrue(chain.robustness.supports_green)
        self.assertEqual(len(chain.robustness.cases), 21)
        report = decide_verdicts(inputs)
        self.assertEqual(report.guards["family_consistency"], "NOT_AVAILABLE")
        self.assertIn("records-based control", report.case_label)
        for verdict in report.verdicts.values():
            self.assertIs(verdict.verdict, Verdict.IDENTIFIED)  # synthetic-gate context only
            self.assertLess(verdict.conservative_ln, 0.05)
            self.assertTrue(math.isfinite(verdict.conservative_ln))
        # The same evidence never yields a production identification (D-039, D-044).
        production = decide_verdicts(S.twin_control(VerdictContext.PRODUCTION)[0])
        self.assertTrue(all(v.verdict is Verdict.NOT_IDENTIFIABLE for v in production.verdicts.values()))


class AcceptedContractsTests(unittest.TestCase):
    """7: M3 / M4 accepted contracts unchanged (records only)."""

    def test_7_m4_records_and_m3_identities_unchanged(self):
        import test_m4_stage_gate as m4

        for path, expected in m4.PINS.items():
            with self.subTest(path=path.name):
                self.assertEqual(hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest(), expected)
        identity = json.loads((m4.LOOP / "run_identity.json").read_text(encoding="utf-8"))
        manifest = load_forward_model_manifest(ROOT / "docs/auto_id/forward_models/SP13.forward.json")
        self.assertEqual(identity["forward_model"]["manifest_hash"], manifest.manifest_hash)
        anchors = {c["name"]: c for c in json.loads((ROOT / "docs/auto_id/forward_models/accepted_forward_jobs.json")
                                                     .read_text(encoding="utf-8"))["candidates"]}
        for key, job in m4.REUSED.items():
            with self.subTest(job=job):
                self.assertTrue(job.endswith(anchors[m4.ANCHOR_NAMES[key]]["jobs"]["SP13"]["generated_inp_sha256"][:16]))


if __name__ == "__main__":
    unittest.main()
