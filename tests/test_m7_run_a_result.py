"""M7 RUN_A result (HUMAN gate 2, manifest e4ba607f…, run identity 8ed03be3…; no Abaqus here).

Checks the committed result record against the D-069 reporting rules (engineering estimate kept apart
from the formal M5 verdict; "not externally validated"; G12 fixed) and, with the run store configured
(``AUTO_ID_FIXTURE_ROOT_M7_RUN_A``), rebuilds the report from the journals.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from domain.campaign_definition import (
    EFFECTIVE_ESTIMATE,
    NO_MATERIAL_CLAIM,
    NOT_EXTERNALLY_VALIDATED,
    load_campaign_definition,
)
from domain.experiment_fixture import fixture_roots_from_environment


CAMPAIGNS = ROOT / "docs" / "auto_id" / "campaigns"
RESULT = CAMPAIGNS / "M7_RUN_A.result.json"
MANIFEST_HASH = "e4ba607f06a69311b4d7adab089b5b8fdbbf98aae9d2da0837849e6c5da5bde6"
RUN_HASH = "8ed03be3be86aa83877367ab505cf2d66ae711c6c9a2a7a4dc47ab6c499923a2"


class RunAResultTests(unittest.TestCase):
    def setUp(self):
        self.result = json.loads(RESULT.read_text(encoding="utf-8"))
        self.definition = load_campaign_definition(CAMPAIGNS / "M7_RUN_A.campaign.json")

    def test_identity_and_scope(self):
        r = self.result
        self.assertEqual((r["manifest_hash"], r["run_hash"], r["run_type"]), (MANIFEST_HASH, RUN_HASH, "RUN_A"))
        self.assertEqual(r["campaign_hash"], self.definition.campaign_hash)
        self.assertEqual(r["fixed_parameters"], {"G12_mpa": 4500.0})
        self.assertEqual(list(r["parameters"]), ["E_in_plane_mpa"])
        self.assertEqual(r["lm_status"], "CONVERGED")
        self.assertLessEqual(r["abaqus_solves_used"], 16)
        for evaluation in r["campaign_evaluations"]:
            self.assertEqual(list(evaluation["parameters"]), ["E_in_plane_mpa"])

    def test_rows_keep_the_accepted_roles_and_identity(self):
        rows = self.result["engineering"]["rows"]
        self.assertEqual([(x["term_id"], x["role"]) for x in rows],
                         [("SP02:R1", "FIT"), ("SP02:R2", "FIT"), ("SP02:R3", "HOLDOUT"), ("SP13:R1", "FIT"),
                          ("SP13:R2", "HOLDOUT")])
        for x in rows:
            with self.subTest(row=x["term_id"]):
                self.assertEqual(x["tracked_fe_mode"], x["baseline_fe_mode"])
                self.assertGreaterEqual(x["tracking_mac"], 0.90)
                self.assertGreaterEqual(x["baseline_pair_mac"], 0.80)
                self.assertAlmostEqual(x["relative_error"], x["fe_hz"] / x["experimental_hz"] - 1.0, places=12)
        worst = max(abs(x["relative_error"]) for x in rows)
        self.assertEqual(self.result["engineering"]["max_abs_relative_error"], worst)
        self.assertLessEqual(worst, 0.10)

    def test_engineering_estimate_is_separate_from_the_m5_verdict(self):
        r = self.result
        self.assertEqual(r["engineering"]["estimate"], EFFECTIVE_ESTIMATE)
        self.assertEqual(r["engineering"]["practical_target"], "WITHIN_ACCEPTABLE_TARGET")
        self.assertTrue(r["engineering"]["improved_or_consistent"])
        verdict = r["m5_verdict"]["verdicts"]["E_in_plane_mpa"]
        self.assertEqual(verdict["verdict"], "NOT_IDENTIFIABLE")
        self.assertIsNone(verdict["reported_value"])
        self.assertTrue(any(reason.startswith("FAMILY_CONSISTENCY") for reason in verdict["reasons"]))
        self.assertTrue(any(reason.startswith("HOLDOUT_FAILURE") for reason in verdict["reasons"]))
        self.assertEqual(r["material_claim"], NO_MATERIAL_CLAIM)
        self.assertEqual(r["validation"], NOT_EXTERNALLY_VALIDATED)
        self.assertEqual(r["sigma"]["measurement"]["status"], "NOT_AVAILABLE")
        self.assertNotIn("sd_ln", r["sigma"]["measurement"])

    def test_birge_and_model_form_diagnostics(self):
        d = self.result["m5_diagnostics"]
        self.assertEqual((d["birge"]["status"], d["birge"]["dof"]), ("BLOCKED_PATTERN", 2))
        self.assertTrue(math.isclose(d["birge"]["birge_factor"], math.sqrt(d["birge"]["chi2_per_dof"])))
        self.assertEqual(d["pattern"]["holdout_failures"], ["SP02:R3"])
        cases = {c["family"]: c["removed_term_ids"] for c in d["robustness"]["cases"]}
        self.assertEqual(cases["Px:O|Py:E|nx:1|ny:2"], ["SP02:R2", "SP13:R1"])


class RunStoreTests(unittest.TestCase):
    def test_report_rebuilds_from_the_journals(self):
        roots = fixture_roots_from_environment()
        missing = sorted({"m7-run-a", "snadwich", "carbon-project-archive"} - set(roots))
        if missing:
            self.skipTest(f"data stores {missing} not configured")
        import m7_campaign as tool
        from domain.identification_run import RunJournal
        from services.identification_campaign_run import (
            ARCHIVE_RUN_STORE, build_campaign_report, campaign_run_identity, journalled_archive_records,
            reused_pack_records)
        from domain.identification_run import canonical_hash

        run_root = Path(roots["m7-run-a"])
        roots = dict(roots)
        roots[ARCHIVE_RUN_STORE] = run_root / "archive_reuse"
        definition, reuse, specimens, _, manifest_hash = tool.build(run_root, roots)
        packs = reused_pack_records(reuse, ROOT, journalled_archive_records(reuse, run_root, manifest_hash), specimens)
        identity = campaign_run_identity(definition, specimens, manifest_hash, packs)
        self.assertEqual(canonical_hash(identity), RUN_HASH)
        journal = RunJournal(run_root / "campaign" / RUN_HASH / "journal.json", identity)
        report = build_campaign_report(definition, specimens, journal.records("evaluation"),
                                       journal.records("result")[-1])
        committed = json.loads(RESULT.read_text(encoding="utf-8"))  # historical v1 record (frozen, unchanged)
        report = json.loads(json.dumps(report))
        # Unchanged by D-076: what was computed.
        for key in ("material_claim", "validation", "lm_status"):
            with self.subTest(key=key):
                self.assertEqual(report[key], committed[key])
        self.assertEqual(report["optimizer_candidate"]["values"], committed["parameters"])
        self.assertEqual({k: v for k, v in report["engineering"].items() if k != "estimate"},
                         {k: v for k, v in committed["engineering"].items() if k != "estimate"})
        # Changed by D-076, and only there: SPEC §13 is evaluated (FAIL) and the candidate is not released.
        self.assertEqual(committed["engineering"]["estimate"], "EFFECTIVE_MODEL_PARAMETER_ESTIMATE")
        self.assertEqual(report["engineering"]["estimate"], "DIAGNOSTIC_OPTIMIZER_CANDIDATE_NOT_RELEASED")
        self.assertEqual((committed["m5_verdict"]["guards"]["family_consistency"],
                          report["m5_verdict"]["guards"]["family_consistency"]), ("NOT_AVAILABLE", "FAIL"))

        def without_family(verdict):
            verdict = json.loads(json.dumps(verdict))
            verdict["guards"].pop("family_consistency")
            for item in verdict["verdicts"].values():
                item["reasons"] = [r for r in item["reasons"] if not r.startswith("FAMILY_CONSISTENCY")]
            return verdict

        self.assertEqual(without_family(report["m5_verdict"]), without_family(committed["m5_verdict"]))
        self.assertIn("FAMILY_CONSISTENCY: failed", report["m5_verdict"]["verdicts"]["E_in_plane_mpa"]["reasons"])
        self.assertEqual(report["formal_output"]["status"], "NO_GLOBAL_PARAMETER_VALUE")
        self.assertIn("FAMILY_CONSISTENCY_FAIL", report["formal_output"]["blockers"])
        correction = json.loads((ROOT / "docs/auto_id/audit_corrections/M7_FAMILY_CONSISTENCY_CORRECTION.json")
                                .read_text(encoding="utf-8"))
        self.assertEqual(report["family_consistency"], correction["run_a"]["family_consistency"])
        closure = json.loads((CAMPAIGNS / "M7_CLOSURE.json").read_text(encoding="utf-8"))
        self.assertEqual(json.loads(json.dumps(report["model_form_robustness"])),
                         closure["run_a"]["model_form_robustness"])  # D-075 reporting from the live M5 chain


if __name__ == "__main__":
    unittest.main()
