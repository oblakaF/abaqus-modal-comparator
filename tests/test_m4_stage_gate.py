"""M4 stage gate on the accepted records (SPEC §17 M4; M4_DECISION_RECORD §4, §8–§11).

Records only: no Abaqus, no temporary run directories, no ODBs.  The accepted M4.9 evidence is
read from the committed provenance copies in ``docs/auto_id/twins/``.

Each copy is pinned by a line-ending-normalised SHA-256, so the pins hold on Windows and Linux
checkouts alike.  Each copy is also bound to the permanent archive manifest, the committed copy
of ``carbon-project-archive/m4_twin/*/ARCHIVE_MANIFEST.json``, whose raw SHA-256 entries are for
the CRLF files.  When the ``carbon-project-archive`` / ``snadwich`` stores are configured, the
archive itself and the M3 renderings are verified as well.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.experiment_fixture import fixture_roots_from_environment, load_experiment_fixture_manifest
from domain.forward_model_manifest import load_forward_model_manifest
from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING
from domain.identification_run import RunJournal, canonical_hash, load_solver_profile
from domain.specimen_manifest import load_specimen_manifest
from services.fe_shape_pack import load_shape_pack_record
from services.identification_step import LMSettings
from services.synthetic_twin import load_twin_definition


DOCS = ROOT / "docs" / "auto_id"
LOOP = DOCS / "twins" / "SP13_identification_loop"
TRUTH_GATE = DOCS / "twins" / "SP13_truth_gate"
SHAPES = DOCS / "fe_shapes"

RUN_HASH = "3503c7d472c1a5733a5688f3649434cb5a680c2f0e85a21e94c95a93f5e39931"
OBSERVATION_HASH = "05a5443a2f8eef4985b8176b762dcf4905600dd0fd0e89551a3ab6f4604e1311"
TWIN_HASH = "c200b2930671c9fe47c0ab44c792f326e9f5343d2c491a7723ad2f859b3f8668"
TRUTH_JOB = "SP13_bb3e5d7d131bed4f"
NEW_JOB = "SP13_aad55d259c1164ca"
REUSED = {"p0": "SP13_a46d08b52995e078", "E_in_plane_mpa+": "SP13_0e861d03c333bb0b",
          "E_in_plane_mpa-": "SP13_a9df66283a168786", "G12_mpa+": "SP13_4c0f189b9727feaf",
          "G12_mpa-": "SP13_0328066b74b6fd78"}
ANCHOR_NAMES = {"p0": "CARBON-4C BASELINE", "E_in_plane_mpa+": "CARBON-5A E_PLUS",
                "E_in_plane_mpa-": "CARBON-5A E_MINUS", "G12_mpa+": "CARBON-5A G_PLUS", "G12_mpa-": "CARBON-5A G_MINUS"}
APPROVED_LM = LMSettings(mu_initial=1e-3, mu_decrease=10.0, max_step_attempts=3, solve_budget=20)
BOUNDS = {"names": ["E_in_plane_mpa", "G12_mpa"], "lower": [26000.0, 2250.0], "upper": [104000.0, 9000.0]}
MAX_NEW_SOLVES = APPROVED_LM.solve_budget - len(REUSED)  # 15 (HUMAN gate, M4_DECISION_RECORD §11.1)

# Line-ending-normalised SHA-256 of the accepted provenance copies.
PINS = {
    LOOP / "ARCHIVE_MANIFEST.json": "7d8f2c0498b6910b76010a1178b26a96a7f3aa7f7eb514f3039c98ce8b31e095",
    LOOP / "determinism_replay.json": "40013d83b449b099efb7bede5058851de9ae082da847edc6e0914ee41f41cf66",
    LOOP / "journal.json": "47356db7674a1645e36b8d6e92eb6212c4c6edbb3f71bea55c030c16577d4c66",
    LOOP / "loop_result.json": "fb93d53ce81fe4a9927026643b17a23afa01cf5150cc17f5c4897aae2757c1eb",
    LOOP / "run_identity.json": "76d0fccff4113a472643a699277e78b9cae510f68ed22d6cc435c7de6d6d0513",
    LOOP / f"{NEW_JOB}.run-shape-pack.json": "1ed89223ca80d77fc3d424318b2bf8712671910cbaf116f0fc72e25183ef2e92",
    TRUTH_GATE / "ARCHIVE_MANIFEST.json": "b91a4222965e6fed97889ff2773b4e7abf94d0e9a6815a35f72ed27d5903dea5",
    TRUTH_GATE / "readiness_report.json": "3b8f840b3ad15e7046c6e8f0725551769246eaab6bf9bc7fae8451adefd842d6",
    TRUTH_GATE / "readiness_report_a1.json": "e9f6173e768d89381dc00fadef7c4194b54fc0b02c7b0cbf57817f8ee3a6a381",
    TRUTH_GATE / f"{TRUTH_JOB}.shape-pack.json": "5ef8ccd0b572bd5c4835bd577432a5171f198dbc6730d442c24425f8211ae68b",
    TRUTH_GATE / "truth_extraction_manifest.json": "24b1019a423904760b1c0af45d68835d8ae3b6dddceb779334c4d04c599330b0",
    TRUTH_GATE / "truth_journal.json": "c9f32966604fd02a7096e2d7bbf7ddcfaf9cd82b264ec60a2b79104750f36b21",
    TRUTH_GATE / "twin_provenance.json": "090566a1cc0317e8f566926fc79839e90b3739cdc7cfe71d0e6e73c67952e90a",
}
# Committed copy → name of the archived file in the archive manifest.
ARCHIVED_AS = {
    LOOP / "journal.json": "m4_twin/SP13_identification_loop/journal.json",
    LOOP / "loop_result.json": "m4_twin/SP13_identification_loop/loop_result.json",
    LOOP / "run_identity.json": "m4_twin/SP13_identification_loop/run_identity.json",
    LOOP / "determinism_replay.json": "m4_twin/SP13_identification_loop/determinism_replay.json",
    LOOP / f"{NEW_JOB}.run-shape-pack.json": f"m4_twin/SP13_identification_loop/packs/{NEW_JOB}.run-shape-pack.json",
    TRUTH_GATE / "truth_journal.json": "m4_twin/SP13_truth_gate/journal.json",
    TRUTH_GATE / "readiness_report.json": "m4_twin/SP13_truth_gate/readiness_report.json",
    TRUTH_GATE / "twin_provenance.json": "m4_twin/SP13_truth_gate/twin_provenance.json",
    TRUTH_GATE / "truth_extraction_manifest.json": "m4_twin/SP13_truth_gate/truth_extraction_manifest.json",
    TRUTH_GATE / f"{TRUTH_JOB}.shape-pack.json": f"m4_twin/SP13_truth_gate/{TRUTH_JOB}.run-shape-pack.json",
}


def lf_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def archive_entries(manifest: Path) -> dict:
    return {entry["file"]: entry for entry in load(manifest)["files"]}


class ProvenanceRecordTests(unittest.TestCase):
    """The committed copies are the accepted records and bound to the permanent archive."""

    def test_copies_are_pinned(self):
        for path, expected in PINS.items():
            with self.subTest(path=path.name):
                self.assertEqual(hashlib.sha256(lf_bytes(path)).hexdigest(), expected)

    def test_copies_are_bound_to_the_archive_manifests(self):
        entries = {**archive_entries(LOOP / "ARCHIVE_MANIFEST.json"),
                   **archive_entries(TRUTH_GATE / "ARCHIVE_MANIFEST.json")}
        for path, archived in ARCHIVED_AS.items():
            with self.subTest(path=path.name):
                crlf = lf_bytes(path).replace(b"\n", b"\r\n")  # the archived files are CRLF
                self.assertEqual(hashlib.sha256(crlf).hexdigest(), entries[archived]["sha256"])
        loop = load(LOOP / "ARCHIVE_MANIFEST.json")
        self.assertEqual(loop["run_hash"], RUN_HASH)
        self.assertEqual(entries[f"m4_twin/SP13_identification_loop/packs/{NEW_JOB}.npz"]["sha256"],
                         load(LOOP / f"{NEW_JOB}.run-shape-pack.json")["pack"]["sha256"])

    def test_permanent_archive(self):
        roots = fixture_roots_from_environment()
        if "carbon-project-archive" not in roots:
            self.skipTest("data store 'carbon-project-archive' not configured")
        archive = Path(roots["carbon-project-archive"])
        index = load(archive / "ARCHIVE_MANIFEST.json")["m4_twin"]
        for key, copy in (("SP13_identification_loop", LOOP), ("SP13_truth_gate", TRUTH_GATE)):
            manifest = archive / index[key]["manifest"]
            with self.subTest(gate=key):
                self.assertEqual(hashlib.sha256(manifest.read_bytes()).hexdigest(), index[key]["manifest_sha256"])
                self.assertEqual(lf_bytes(manifest), lf_bytes(copy / "ARCHIVE_MANIFEST.json"))
                for entry in load(manifest)["files"]:
                    self.assertEqual(hashlib.sha256((archive / entry["file"]).read_bytes()).hexdigest(), entry["sha256"])


class RunIdentityTests(unittest.TestCase):
    """The accepted run is bound to the accepted twin, freeze, design, policies and M3 identities."""

    def setUp(self):
        self.identity = load(LOOP / "run_identity.json")
        self.result = load(LOOP / "loop_result.json")

    def test_run_hash(self):
        self.assertEqual(canonical_hash(self.identity), RUN_HASH)
        self.assertEqual(self.result["run_hash"], RUN_HASH)
        self.assertEqual(load(LOOP / "journal.json")["run_hash"], RUN_HASH)

    def test_twin_freeze_and_design(self):
        twin = load_twin_definition(DOCS / "twins" / "SP13.twin.json")
        a1 = load(TRUTH_GATE / "readiness_report_a1.json")
        self.assertEqual(twin.definition_hash, TWIN_HASH)
        bound = self.identity["extra"]["twin"]
        self.assertEqual((bound["twin_definition_hash"], bound["noise_seed"]), (TWIN_HASH, 20261005))
        self.assertEqual(bound["synthetic_experiment_sha256"], a1["synthetic_experiment_sha256"])
        self.assertEqual(bound["truth_pack_content_sha256"],
                         load_shape_pack_record(SHAPES / f"{TRUTH_JOB}.shape-pack.json").content_sha256)
        self.assertEqual(self.identity["observation_hash"], OBSERVATION_HASH)
        self.assertEqual((a1["verdict"], a1["freeze"]["observation_hash"]), ("READY_FOR_IDENTIFICATION", OBSERVATION_HASH))
        self.assertTrue(all(group["status"] == "INDEPENDENT" for group in a1["trigger_groups"]))  # A1 / D-032
        design = self.identity["objective_design"]
        self.assertEqual(design["fit_rows"], [f"R{k}" for k in range(2, 23)])
        self.assertEqual((design["holdout_rows"], design["fit_clusters"], design["holdout_clusters"]), (["R1", "R23"], [], []))
        self.assertEqual(design["fit_rows"], a1["design"]["fit_rows"])
        self.assertEqual(set(design["sigmas"]), {f"R{k}" for k in range(1, 24)})
        self.assertTrue(all(s == {"measurement_sd": 0.003, "setup_sd": 0.0, "setup_provisional": False}
                            for s in design["sigmas"].values()))
        self.assertEqual(self.result["twin_definition_hash"], TWIN_HASH)
        self.assertEqual(self.result["observation_hash"], OBSERVATION_HASH)

    def test_policies_settings_bounds_and_profile(self):
        self.assertEqual(self.identity["pairing_policy_hash"], STRICT_IDENTIFICATION_PAIRING.policy_hash)
        self.assertEqual(self.identity["lm_settings"], asdict(APPROVED_LM))
        self.assertEqual(self.identity["bounds"], BOUNDS)  # development-only twin bounds (§11.1)
        self.assertIn("development-only", self.identity["extra"]["bounds_status"])
        self.assertEqual(self.identity["start"], {"E_in_plane_mpa": 52000.0, "G12_mpa": 4500.0})
        self.assertEqual(self.identity["solver_profile_hash"],
                         load_solver_profile(DOCS / "solver_profiles" / "SP13.json").profile_hash)
        self.assertEqual(self.identity["extraction_expectation"]["mode_numbers"], list(range(7, 31)))

    def test_m3_identities(self):
        manifest = load_forward_model_manifest(DOCS / "forward_models" / "SP13.forward.json")
        passport = load_specimen_manifest(ROOT / manifest.specimen_passport.path)
        self.assertEqual(self.identity["forward_model"], {"forward_model_id": manifest.forward_model_id,
                                                          "manifest_hash": manifest.manifest_hash,
                                                          "passport_manifest_hash": passport.manifest_hash})
        anchors = {c["name"]: c for c in load(DOCS / "forward_models" / "accepted_forward_jobs.json")["candidates"]}
        archived = self.identity["archived_packs"]
        self.assertEqual(set(archived), set(REUSED.values()))
        for key, job in REUSED.items():
            record = load_shape_pack_record(SHAPES / f"{job}.shape-pack.json")
            with self.subTest(job=job):
                self.assertEqual(archived[job], record.content_sha256)
                self.assertEqual(record.generated_inp_sha256, anchors[ANCHOR_NAMES[key]]["jobs"]["SP13"]["generated_inp_sha256"])
                self.assertTrue(job.endswith(record.generated_inp_sha256[:16]))


class JournalTests(unittest.TestCase):
    """The archived journal: hash chain, evaluations, solve accounting and the result record."""

    @classmethod
    def setUpClass(cls):
        identity = load(LOOP / "run_identity.json")
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / "journal.json"
            shutil.copyfile(LOOP / "journal.json", copy)
            cls.journal = RunJournal(copy, identity)  # verifies the identity and the whole hash chain
        cls.result = load(LOOP / "loop_result.json")
        cls.evaluations = cls.journal.records("evaluation")

    def test_hash_chain_and_entries(self):
        kinds = [entry["kind"] for entry in self.journal.entries]
        self.assertEqual(kinds, ["evaluation"] * 5 + ["solve", "extraction", "evaluation", "result"])
        self.assertEqual(self.journal.entries[-1]["entry_hash"], self.result["journal_last_entry_hash"])

    def test_evaluations(self):
        self.assertEqual(len(self.evaluations), 6)
        for record in self.evaluations:
            with self.subTest(job=record["job_name"]):
                body = {k: v for k, v in record.items() if k != "evaluation_hash"}
                self.assertEqual(canonical_hash(body), record["evaluation_hash"])
                self.assertIsNone(record["refusal"])
                self.assertEqual(len(record["residuals"]), 21)
                self.assertAlmostEqual(0.5 * sum(r * r for r in record["residuals"]), record["objective"], places=9)
                self.assertEqual(set(record["tracking"]), {f"R{k}" for k in range(1, 24)})
                self.assertGreaterEqual(min(mac for _, mac in record["tracking"].values()), 0.9)
                self.assertTrue(record["job_name"].endswith(record["generated_inp_sha256"][:16]))
        reused = [r for r in self.evaluations if r["fe_source"] == "archived-validated-pack"]
        self.assertEqual({r["job_name"]: r["pack_content_sha256"] for r in reused},
                         load(LOOP / "run_identity.json")["archived_packs"])
        new = [r for r in self.evaluations if r["fe_source"] == "new-solve"]
        self.assertEqual([r["job_name"] for r in new], [NEW_JOB])
        self.assertEqual(self.evaluations[0]["parameters"], {"E_in_plane_mpa": 52000.0, "G12_mpa": 4500.0})

    def test_new_solve_and_extraction(self):
        solve = self.journal.find("solve", job_name=NEW_JOB)
        extraction = self.journal.find("extraction", job_name=NEW_JOB)
        pack = load(LOOP / f"{NEW_JOB}.run-shape-pack.json")
        self.assertTrue(solve["executed"])
        self.assertEqual(solve["odb_sha256"], pack["odb"]["sha256"])
        self.assertEqual(extraction["odb_sha256"], solve["odb_sha256"])
        self.assertEqual(extraction["pack_content_sha256"], pack["content_sha256"])
        self.assertTrue(all(extraction["checks"].values()) and extraction["raw_deleted"])
        self.assertEqual(self.evaluations[-1]["pack_content_sha256"], pack["content_sha256"])

    def test_result_record(self):
        record = self.journal.records("result")[0]
        self.assertEqual(record["status"], self.result["status"])
        self.assertEqual(record["parameters"], self.result["parameters"])
        self.assertEqual(record["identification_evaluations"], self.result["identification_evaluations"])
        self.assertEqual(record["local_sd"], self.result["local_sd_ln"])
        self.assertEqual(record["objective"], self.evaluations[-1]["objective"])


class M4GateTests(unittest.TestCase):
    """SPEC §17 M4 and M4_DECISION_RECORD §4: the accepted synthetic-twin result."""

    def setUp(self):
        self.result = load(LOOP / "loop_result.json")
        self.twin = load_twin_definition(DOCS / "twins" / "SP13.twin.json")

    def test_converged_within_budget(self):
        self.assertEqual(self.result["status"], "CONVERGED")
        self.assertIsNone(self.result["refusal"])
        self.assertLessEqual(self.result["identification_evaluations"], APPROVED_LM.solve_budget)
        self.assertEqual(self.result["identification_evaluations"], 6)
        counts = self.result["counts"]
        self.assertEqual(counts["identification_evaluations_journalled"], 6)
        self.assertEqual(counts["reused_archived_evaluations"], 5)
        self.assertEqual(counts["abaqus_solves_executed_total"], 1)
        self.assertEqual(counts["failed_solves"], 0)
        self.assertEqual((self.result["solver_calls"], self.result["extractor_calls"]), (1, 1))
        self.assertLessEqual(counts["abaqus_solves_executed_total"], MAX_NEW_SOLVES)
        self.assertEqual(MAX_NEW_SOLVES, 15)

    def test_recovered_within_one_sigma(self):
        self.assertEqual(self.result["truth"], dict(self.twin.truth))
        for index, name in enumerate(self.result["bounds"]["names"]):
            with self.subTest(parameter=name):
                error = abs(math.log(self.result["parameters"][name] / self.twin.truth[name]))
                self.assertLessEqual(error, self.result["local_sd_ln"][index])
                item = self.result["assessment"]["parameters"][name]
                self.assertTrue(item["within_1_sigma"])
                self.assertAlmostEqual(item["abs_ln_error"], error, places=12)
        self.assertTrue(self.result["assessment"]["criterion_1_converged"])
        self.assertTrue(self.result["assessment"]["criterion_2_within_1_sigma"])

    def test_no_active_bound(self):
        self.assertFalse(self.result["bound_active"])
        self.assertEqual(self.result["bounds"], BOUNDS)
        for name, low, high in zip(BOUNDS["names"], BOUNDS["lower"], BOUNDS["upper"]):
            self.assertTrue(low < self.result["parameters"][name] < high)

    def test_lm_history(self):
        history = self.result["history"]
        self.assertEqual([(h["iteration"], h["accepted"]) for h in history], [(1, True), (2, False)])
        self.assertEqual(history[0]["mu"], APPROVED_LM.mu_initial)
        self.assertEqual(history[1]["mu"], APPROVED_LM.mu_initial / APPROVED_LM.mu_decrease)
        self.assertLess(history[0]["trial_objective"], history[0]["objective_before"])
        self.assertIsNone(history[1]["trial_objective"])  # converged on the step rule, no further solve

    def test_deterministic_replay(self):
        replay = load(LOOP / "determinism_replay.json")
        for flag in ("run_hash_equal", "identity_file_equal", "parameters_equal", "local_sd_equal", "objective_equal",
                     "status_equal", "journal_unchanged"):
            with self.subTest(flag=flag):
                self.assertIs(replay[flag], True)
        self.assertEqual((replay["evaluations_replayed"], replay["new_solves"], replay["new_extractions"]), (6, 0, 0))
        self.assertEqual(replay["journal_entries"], len(load(LOOP / "journal.json")["entries"]))

    def test_truth_gate_binding(self):
        truth = load(TRUTH_GATE / "truth_journal.json")
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / "journal.json"
            shutil.copyfile(TRUTH_GATE / "truth_journal.json", copy)
            journal = RunJournal(copy, truth["run_identity"])
        report = load(TRUTH_GATE / "readiness_report.json")
        self.assertEqual(journal.run_hash, report["truth_run_hash"])
        self.assertEqual([e["kind"] for e in journal.entries], ["truth_solve", "truth_extraction"])
        self.assertEqual(journal.records("truth_extraction")[0]["pack_content_sha256"],
                         load_shape_pack_record(SHAPES / f"{TRUTH_JOB}.shape-pack.json").content_sha256)
        self.assertEqual(truth["run_identity"]["twin_definition_hash"], TWIN_HASH)


class NegativeControlBindingTests(unittest.TestCase):
    """§8.4: the accepted branch-exchange negative control runs on exactly the accepted reused packs."""

    def test_bound_to_the_accepted_records(self):
        import test_m4_9_sp13_readiness as readiness

        self.assertEqual(set(readiness.EXPECTED_JOBS.values()), set(load(LOOP / "run_identity.json")["archived_packs"]))
        self.assertEqual(readiness.EXPECTED_JOBS, REUSED)
        control = readiness.BranchExchangeNegativeControlTests
        for name in ("test_injected_exchange_is_refused_without_re_pairing",
                     "test_pure_relabelling_is_a_tracked_crossing_not_an_exchange"):
            self.assertTrue(callable(getattr(control, name)))
        evidence = (DOCS / "EVIDENCE.md").read_text(encoding="utf-8")
        self.assertIn("ACCEPTED (SUPERVISOR, 2026-10-05)", evidence.split("## M4.9 — SP13 synthetic-twin identification loop")[1])


class M3ContractTests(unittest.TestCase):
    """No M3 regression: the accepted jobs are reproduced by the unchanged M3 builder (store-gated)."""

    def test_jobs_rerender_identically(self):
        roots = fixture_roots_from_environment()
        if "snadwich" not in roots:
            self.skipTest("data store 'snadwich' not configured")
        from services.forward_builder import load_bound_forward_model
        from services.identification_pipeline import forward_jobs

        fixtures = load_experiment_fixture_manifest(DOCS / "fixtures" / "real_experiment_fixtures.json")
        model = load_bound_forward_model(DOCS / "forward_models" / "SP13.forward.json", ROOT, fixtures)
        evaluations = load(LOOP / "journal.json")["entries"]
        points = {e["record"]["job_name"]: e["record"]["parameters"] for e in evaluations if e["kind"] == "evaluation"}
        points[TRUTH_JOB] = {"E_in_plane_mpa": 45000.0, "G12_mpa": 4000.0}
        expected = {e["record"]["job_name"]: e["record"]["generated_inp_sha256"] for e in evaluations
                    if e["kind"] == "evaluation"}
        expected[TRUTH_JOB] = load_shape_pack_record(SHAPES / f"{TRUTH_JOB}.shape-pack.json").generated_inp_sha256
        with tempfile.TemporaryDirectory() as directory:
            jobs = forward_jobs(model, roots, points, Path(directory))
        for name, job in jobs.items():
            with self.subTest(job=name):
                self.assertEqual((job.job_name, job.generated_inp_sha256), (name, expected[name]))


if __name__ == "__main__":
    unittest.main()
