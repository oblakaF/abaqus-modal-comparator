"""M7 RUN_B result (HUMAN solve gate, manifest 5fd0946a…, run identity fb523411…; no Abaqus here).

Checks the committed RUN_B record against the D-072 diagnostic rules (EFFECTIVE_MODEL_COMPENSATION_TEST;
G12 a compensation diagnostic, never a material property; engineering kept apart from the formal M5 verdict;
"not externally validated"; Δ ln against the accepted RUN_A) and, with the run store configured
(``AUTO_ID_FIXTURE_ROOT_M7_RUN_B``), rebuilds the report from the journals.
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
    NO_MATERIAL_CLAIM,
    NOT_EXTERNALLY_VALIDATED,
    RUN_B_LABEL,
    load_campaign_definition,
)
from domain.experiment_fixture import fixture_roots_from_environment


CAMPAIGNS = ROOT / "docs" / "auto_id" / "campaigns"
RESULT = CAMPAIGNS / "M7_RUN_B.result.json"
RUN_A_RESULT = CAMPAIGNS / "M7_RUN_A.result.json"
MANIFEST_HASH = "5fd0946a0c3f4e20562ba97068cdb5b94bf6d10ba789a3b2df20b457882034a1"
RUN_HASH = "fb5234116c6e9413e4b070e901f97b8c6e210d535daefe15f0cdb5b9f8ad87f0"


class RunBResultTests(unittest.TestCase):
    def setUp(self):
        self.result = json.loads(RESULT.read_text(encoding="utf-8"))
        self.run_a = json.loads(RUN_A_RESULT.read_text(encoding="utf-8"))
        self.definition = load_campaign_definition(CAMPAIGNS / "M7_RUN_B.campaign.json")

    def test_identity_and_scope(self):
        r = self.result
        self.assertEqual((r["manifest_hash"], r["run_hash"], r["run_type"]), (MANIFEST_HASH, RUN_HASH, "RUN_B"))
        self.assertEqual(r["campaign_hash"], self.definition.campaign_hash)
        self.assertEqual(r["fixed_parameters"], {})
        self.assertEqual(list(r["parameters"]), ["E_in_plane_mpa", "G12_mpa"])
        self.assertEqual(r["lm_status"], "CONVERGED")
        self.assertLessEqual(r["abaqus_solves_used"], 24)
        self.assertEqual(r["journals"]["campaign"]["run_hash"], RUN_HASH)

    def test_started_from_the_governed_point_not_the_run_a_optimum(self):
        evaluations = self.result["campaign_evaluations"]
        self.assertEqual(evaluations[0]["parameters"], {"E_in_plane_mpa": 52000.0, "G12_mpa": 4500.0})
        self.assertEqual([set(e["fe_sources"].values()) for e in evaluations[:5]], [{"archived-validated-pack"}] * 5)
        run_a_e = self.run_a["parameters"]["E_in_plane_mpa"]
        self.assertFalse(any(e["parameters"]["E_in_plane_mpa"] == run_a_e for e in evaluations))
        new = sum(1 for e in evaluations if set(e["fe_sources"].values()) == {"new-solve"})
        self.assertEqual(2 * new, self.result["abaqus_solves_used"])

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

    def test_compensation_labels_and_no_material_claim(self):
        r = self.result
        self.assertEqual(r["engineering"]["estimate"], RUN_B_LABEL)
        self.assertEqual(r["parameter_roles"]["G12_mpa"], "COMPENSATION_DIAGNOSTIC_NOT_MATERIAL_PROPERTY")
        self.assertEqual(r["material_claim"], NO_MATERIAL_CLAIM)
        self.assertEqual(r["validation"], NOT_EXTERNALLY_VALIDATED)
        self.assertEqual(r["sigma"]["measurement"]["status"], "NOT_AVAILABLE")
        self.assertNotIn("sd_ln", r["sigma"]["measurement"])
        verdicts = r["m5_verdict"]["verdicts"]
        for name in ("E_in_plane_mpa", "G12_mpa"):
            with self.subTest(parameter=name):
                self.assertEqual(verdicts[name]["verdict"], "NOT_IDENTIFIABLE")
                self.assertIsNone(verdicts[name]["reported_value"])
        g12 = " ".join(verdicts["G12_mpa"]["reasons"])
        self.assertIn("BARE_PLATE_REQUIRED", g12)
        self.assertIn("NUISANCE_NOT_INDEPENDENTLY_CONSTRAINED", g12)

    def test_shifts_against_the_accepted_run_a(self):
        comparison = self.result["comparison"]
        self.assertEqual(comparison["reference"], f"RUN_A {self.run_a['run_hash']}")
        reference = {**self.run_a["parameters"], **self.run_a["fixed_parameters"]}
        for name, shift in comparison["shifts"].items():
            with self.subTest(parameter=name):
                self.assertEqual(shift["reference"], reference[name])
                self.assertEqual(shift["value"], self.result["parameters"][name])
                self.assertAlmostEqual(shift["delta_ln"], math.log(shift["value"] / shift["reference"]), places=12)
        self.assertIn("descriptive", comparison["note"])

    def test_birge_and_model_form_diagnostics(self):
        d = self.result["m5_diagnostics"]
        self.assertEqual((d["birge"]["status"], d["birge"]["dof"]), ("BLOCKED_PATTERN", 1))
        self.assertEqual(sorted(d["pattern"]["holdout_failures"]), ["SP02:R3", "SP13:R2"])
        statuses = {c["family"]: c["status"] for c in d["robustness"]["cases"]}
        self.assertEqual(statuses["Px:O|Py:E|nx:1|ny:2"], "REFUSED_RANK_DEFICIENT")


class RunStoreTests(unittest.TestCase):
    def test_report_rebuilds_from_the_journals(self):
        roots = fixture_roots_from_environment()
        missing = sorted({"m7-run-b", "m7-run-a-archive", "snadwich", "carbon-project-archive"} - set(roots))
        if missing:
            self.skipTest(f"data stores {missing} not configured")
        import m7_campaign as tool
        from domain.identification_run import RunJournal, canonical_hash
        from services.identification_campaign_run import (
            ARCHIVE_RUN_STORE, build_campaign_report, campaign_run_identity, journalled_archive_records,
            reused_pack_records)

        run_root = Path(roots["m7-run-b"])
        roots = dict(roots)
        roots[ARCHIVE_RUN_STORE] = run_root / "archive_reuse"
        definition, reuse, specimens, _, manifest_hash = tool.build(run_root, roots, "run-b")
        packs = reused_pack_records(reuse, ROOT, journalled_archive_records(reuse, run_root, manifest_hash), specimens)
        identity = campaign_run_identity(definition, specimens, manifest_hash, packs)
        self.assertEqual(canonical_hash(identity), RUN_HASH)
        journal = RunJournal(run_root / "campaign" / RUN_HASH / "journal.json", identity)
        run_a = json.loads(RUN_A_RESULT.read_text(encoding="utf-8"))
        report = build_campaign_report(definition, specimens, journal.records("evaluation"),
                                       journal.records("result")[-1],
                                       {**run_a["parameters"], **run_a["fixed_parameters"]},
                                       f"RUN_A {run_a['run_hash']}")
        committed = json.loads(RESULT.read_text(encoding="utf-8"))
        for key in ("engineering", "m5_verdict", "material_claim", "validation", "parameters", "lm_status",
                    "parameter_roles", "comparison"):
            with self.subTest(key=key):
                self.assertEqual(json.loads(json.dumps(report[key])), committed[key])
        closure = json.loads((CAMPAIGNS / "M7_CLOSURE.json").read_text(encoding="utf-8"))
        self.assertEqual(json.loads(json.dumps(report["model_form_robustness"])),
                         closure["run_b"]["model_form_robustness"])  # D-075 reporting from the live M5 chain


if __name__ == "__main__":
    unittest.main()
