"""M6.4b: the governed transverse-constant screening result (HUMAN Abaqus gate, manifest 6d34179c…).

The result record is the unchanged output of ``tools/m6_4_transverse_screening.py evaluate`` (frozen at
403ff94).  These tests re-check it against the SPEC §5 rule (D-066) without data stores, and, when the
run store is configured (``AUTO_ID_FIXTURE_ROOT_M6_4_SCREENING_RUN`` plus 'snadwich' and
'carbon-project-archive'), reproduce it from the journalled run packs.  No Abaqus is run here.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.experiment_fixture import fixture_roots_from_environment, load_experiment_fixture_manifest
from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING
from domain.identification_run import canonical_hash
from domain.transverse_screening import INCLUDE, NEGLIGIBLE, SPEC_FREQUENCY_CRITERION, load_screening_envelope


SCREENING = ROOT / "docs" / "auto_id" / "screening"
RESULT = SCREENING / "M6_4_transverse_screening_result.json"
RUN_EVIDENCE = SCREENING / "M6_4_run_evidence.json"
MANIFEST_HASH = "6d34179c787c8b0e1619864709290f2824e0435b98fb1ff2689e61d892da3922"
ENVELOPE_HASH = "d29e848566afaadc1a73234d531f83383810e7ec2f7ac0471c0965aa6fd2036d"
PERTURBATIONS = ("E3-low", "E3-high", "nu13-low", "nu13-high", "nu23-low", "nu23-high", "G13-high", "G23-high")
ROWS = {"SP02": {"R1": 8, "R2": 10, "R3": 13}, "SP13": {"R1": 10, "R2": 13}}
RUN_STORE = "m6-4-screening-run"


class ResultRecordTests(unittest.TestCase):
    def setUp(self):
        self.result = json.loads(RESULT.read_text(encoding="utf-8"))

    def test_identity(self):
        result = self.result
        self.assertEqual(result["schema"], "auto-id/transverse-screening-result/v1")
        self.assertEqual(result["manifest_hash"], MANIFEST_HASH)
        self.assertEqual(result["envelope"]["envelope_hash"], ENVELOPE_HASH)
        self.assertEqual(result["envelope"]["basis"], "LITERATURE_INTERIM_SCREENING_ENVELOPE")
        self.assertEqual(result["pairing_policy_hash"], STRICT_IDENTIFICATION_PAIRING.policy_hash)
        self.assertEqual(result["criterion"]["max_abs_relative_frequency_change_strictly_below"],
                         SPEC_FREQUENCY_CRITERION)
        self.assertEqual(result["result_hash"],
                         canonical_hash({k: v for k, v in result.items() if k != "result_hash"}))

    def test_every_authorised_state_and_frozen_row_is_present(self):
        states = {(s["specimen"], s["perturbation_id"]): s for s in self.result["states"]}
        self.assertEqual(set(states), {(sp, p) for sp in ROWS for p in PERTURBATIONS})
        for (specimen, perturbation), entry in states.items():
            with self.subTest(specimen=specimen, perturbation=perturbation):
                if entry["refusal"] is not None:
                    self.assertEqual(entry["rows"], [])
                    continue
                self.assertEqual({r["row_id"]: r["baseline_fe_mode"] for r in entry["rows"]}, ROWS[specimen])
                for row in entry["rows"]:
                    self.assertGreaterEqual(row["tracking_mac"], STRICT_IDENTIFICATION_PAIRING.tracking_minimum_mac)
                    self.assertAlmostEqual(row["relative_change"],
                                           (row["perturbed_hz"] - row["baseline_hz"]) / row["baseline_hz"], places=15)
                    self.assertFalse(entry["diagnostic_all_modes"]["used_for_classification"])

    def test_classification_follows_the_spec_rule(self):
        constants = self.result["constants"]
        for name, item in constants.items():
            entries = [s for s in self.result["states"] if s["constant"] == name]
            refused = [s for s in entries if s["refusal"] is not None]
            with self.subTest(constant=name):
                if refused:
                    self.assertEqual(item["classification"], "NOT_CLASSIFIED_TRACKING_REFUSED")
                    continue
                worst = max(abs(r["relative_change"]) for s in entries for r in s["rows"])
                self.assertEqual(item["max_abs_relative_change"], worst)
                self.assertEqual(item["classification"], NEGLIGIBLE if worst < 0.003 else INCLUDE)
        self.assertEqual(self.result["negligible"],
                         sorted(n for n, i in constants.items() if i["classification"] == NEGLIGIBLE))
        self.assertEqual(self.result["include_in_uncertainty_budget"],
                         sorted(n for n, i in constants.items() if i["classification"] == INCLUDE))
        self.assertEqual(self.result["budget_closed"], not self.result["not_classified"])

    def test_run_evidence_matches_the_authorised_scope(self):
        evidence = json.loads(RUN_EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual(evidence["manifest_hash"], MANIFEST_HASH)
        self.assertEqual(evidence["counts"]["successful_solves"], 16)
        self.assertEqual(evidence["counts"]["successful_extractions"], 16)
        self.assertEqual(evidence["counts"]["solve_failures"], 0)
        self.assertEqual(evidence["counts"]["baseline_solves"], 0)
        jobs = {(j["specimen"], j["perturbation_id"]): j for j in evidence["jobs"]}
        self.assertEqual(set(jobs), {(sp, p) for sp in ROWS for p in PERTURBATIONS})
        names = {(s["specimen"], s["perturbation_id"]): s["job_name"] for s in self.result["states"]}
        for key, job in jobs.items():
            with self.subTest(job=job["job_name"]):
                self.assertEqual(job["job_name"], names[key])
                self.assertTrue(job["job_name"].endswith(job["generated_inp_sha256"][:16]))
                self.assertIn("Abaqus 2024", job["abaqus_version_line"])
                self.assertTrue(all(job["extraction_checks"].values()))


class ReproductionTests(unittest.TestCase):
    """Re-evaluates the journalled run packs with the frozen tool path; the result must be identical."""

    def test_result_reproduces_from_the_run_store(self):
        roots = fixture_roots_from_environment()
        missing = sorted({"snadwich", "carbon-project-archive", RUN_STORE} - set(roots))
        if missing:
            self.skipTest(f"data stores {missing} not configured")
        from services.transverse_screening import (
            bind_screening_specimens,
            evaluate_screening,
            expected_jobs,
            load_screening_states,
            prepare_screening_plan,
        )

        envelope = load_screening_envelope(SCREENING / "M6_4_transverse_envelope.json")
        fixtures = load_experiment_fixture_manifest(ROOT / "docs/auto_id/fixtures/real_experiment_fixtures.json")
        with tempfile.TemporaryDirectory() as directory:
            plan = prepare_screening_plan(envelope, bind_screening_specimens(envelope, ROOT, fixtures), roots,
                                          Path(directory))
        self.assertEqual(plan.manifest_hash, MANIFEST_HASH)
        baselines, candidates = load_screening_states(plan, roots[RUN_STORE], roots)
        result = evaluate_screening(envelope, STRICT_IDENTIFICATION_PAIRING, baselines, candidates,
                                    expected_jobs(plan), plan.manifest_hash)
        self.assertEqual(result, json.loads(RESULT.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
