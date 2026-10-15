"""Quick calibration P1b-B: an FE job is reused only with verified provenance (FakeAbaqus only).

A finished job carries an atomically written provenance record: the generated INP, every INPUT= file (nested), the
requested FE modal range, the solver and extraction identities, the stored node set, the completion of solve and
extraction, and the hash of the mode data. Reuse needs a complete match and intact data; anything else is
INVALIDATED (fail closed) and re-solved at the same path through the P1b-A budget. Decisions are reported.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import quick_calibration_support as S  # noqa: E402
from services import owned_processes  # noqa: E402
from services import quick_calibration as qc  # noqa: E402
from services.quick_calibration import (  # noqa: E402
    BUDGET_EXHAUSTED,
    INVALIDATED,
    NEW_SOLVE,
    STATUS_ESTIMATE,
    VERIFIED_REUSE,
    FESolveBudgetExhausted,
    QuickCalibration,
    QuickCalibrationError,
    TerminationUnconfirmed,
    config_from_dict,
    run_quick_calibration,
)
from test_quick_calibration import E_FACE, _identity_orientation  # noqa: E402
from test_quick_calibration_fe_budget import CountingAbaqus  # noqa: E402


class _Case(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp(prefix="qc_p1bb_"))
        cls.orientation = _identity_orientation(cls.root / "probe")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="case_", dir=self.root))
        self.inner = self.folder / "inner.inp"
        self.outer = self.folder / "outer.inp"
        self.inner.write_text("** mesh data v1\n")
        self.outer.write_text(f"** wrapper\n*Include, input={self.inner}\n")
        (self.folder / "model.inp").write_text(
            S.INP.replace("*Material, name=CFRP_Face", f"*Include, input={self.outer}\n*Material, name=CFRP_Face"))
        S.write_experiment(self.folder / "exp.unv", 0.9 * S.E0, S.G0, noise=0.001)

    def config(self, limit=100, **extra):
        data = {"model_inp": "model.inp", "experiment": "exp.unv", "output_dir": "out",
                "orientation_candidate_id": self.orientation, "parameters": [E_FACE], "max_new_fe_solves": limit}
        data.update(extra)
        return config_from_dict(data, self.folder)

    def run_with(self, limit=100, fake=None, **extra):
        fake = fake or CountingAbaqus()
        result, paths = run_quick_calibration(self.config(limit, **extra), fake.solve, fake.extract)
        return result, paths, fake

    @property
    def work(self) -> Path:
        return self.folder / "out" / "work"

    def baseline_job(self) -> Path:
        calibration = QuickCalibration(self.config(), None, None)
        return self.work / qc._job_name(calibration.model.render({"E_face": 1.0}))

    @staticmethod
    def decisions(result, decision=None):
        items = result["fe_job_cache"]
        return [item for item in items if decision is None or item["decision"] == decision]

    def assert_invalidated(self, result, text):
        invalid = self.decisions(result, INVALIDATED)
        self.assertTrue(invalid, result["fe_job_cache"])
        self.assertIn(text, invalid[0]["reason"])
        self.assertEqual(invalid[0]["stage"], "baseline")


# ----------------------------------------------------------------------------- verified reuse

class ReuseTests(_Case):
    def test_identical_inputs_are_reused_with_a_budget_of_one(self):
        first, _, fake = self.run_with()
        self.assertEqual(first["status"], STATUS_ESTIMATE)
        self.assertEqual(len(self.decisions(first, NEW_SOLVE)), fake.calls)
        again, paths, fake = self.run_with(1)
        self.assertEqual(again["status"], STATUS_ESTIMATE)
        self.assertEqual(fake.calls, 0)  # no new FE solve
        self.assertEqual(self.decisions(again, INVALIDATED) + self.decisions(again, NEW_SOLVE), [])
        reused = self.decisions(again, VERIFIED_REUSE)
        self.assertTrue(reused)
        self.assertEqual(again["estimates"]["E_face"]["multiplier"], first["estimates"]["E_face"]["multiplier"])
        report = Path(paths["report"]).read_text(encoding="utf-8")
        self.assertIn("FE JOB CACHE", report)
        self.assertIn("VERIFIED_REUSE", report)
        self.assertIn("provenance and mode data verified", report)

    def test_the_provenance_record(self):
        self.run_with()
        record = json.loads((self.baseline_job() / qc.PROVENANCE_FILE).read_text(encoding="utf-8"))
        self.assertEqual(record["schema"], qc.CACHE_SCHEMA)
        self.assertEqual([Path(item["path"]).name for item in record["input_files"]], ["outer.inp", "inner.inp"])
        self.assertTrue(all(len(item["sha256"]) == 64 for item in record["input_files"]))
        self.assertEqual(record["fe_last_mode"], 30)
        self.assertEqual(record["solver"]["executable_sha256"], "fake-solver-v1")
        self.assertEqual(record["extraction"]["script_sha256"], "fake-extract-v1")
        self.assertEqual(record["node_set"]["kind"], "ALL")
        self.assertEqual(record["completion"]["solve"], "COMPLETED")
        self.assertIsNone(record["completion"]["solver_version"])  # the fake writes no .dat
        self.assertEqual(record["record_hash"], qc._canonical_hash({k: v for k, v in record.items()
                                                                    if k != "record_hash"}))
        candidates = [p for p in self.work.iterdir() if p != self.baseline_job()]
        subset = json.loads((candidates[0] / qc.PROVENANCE_FILE).read_text(encoding="utf-8"))["node_set"]
        self.assertEqual(subset["kind"], "SUBSET")

    def test_the_solver_version_is_recorded_when_available(self):
        fake = CountingAbaqus()

        def solve_with_dat(inp, job_dir, job_name):
            (Path(job_dir) / f"{job_name}.dat").write_text("   Abaqus/Standard 2024   DATE 14-Oct-2026\n")
            return fake.solve(inp, job_dir, job_name)

        calibration = QuickCalibration(self.config(), solve_with_dat, fake.extract, solver_identity=fake.identity())
        calibration.fe_state({"E_face": 1.0})
        record = json.loads((self.baseline_job() / qc.PROVENANCE_FILE).read_text(encoding="utf-8"))
        self.assertEqual(record["completion"]["solver_version"], "2024")


# ----------------------------------------------------------------------------- invalidation

class InvalidationTests(_Case):
    def setUp(self) -> None:
        super().setUp()
        self.first, _, self.first_fake = self.run_with()

    def test_an_edited_nested_include(self):
        self.inner.write_text("** mesh data v2\n")
        result, _, fake = self.run_with()
        self.assert_invalidated(result, "INPUT= files changed")
        self.assertEqual(fake.calls, self.first_fake.calls)  # everything re-solved
        again, _, fake = self.run_with()
        self.assertEqual(fake.calls, 0)  # the re-solved jobs are verified again

    def test_a_changed_fe_modal_range(self):
        result, _, fake = self.run_with(fe_last_mode=9)
        self.assert_invalidated(result, "requested FE modal range changed")
        self.assertGreater(fake.calls, 0)

    def test_a_changed_abaqus_configuration(self):
        fake = CountingAbaqus()
        fake.solver_identity["executable_sha256"] = "fake-solver-v2"  # another launcher / release
        result, _, _ = self.run_with(fake=fake)
        self.assert_invalidated(result, "Abaqus executable/configuration changed")
        fake = CountingAbaqus()
        fake.solver_identity["command"] = "abq2025"
        result, _, _ = self.run_with(fake=fake)
        self.assert_invalidated(result, "Abaqus executable/configuration changed")

    def test_changed_extraction_script_or_settings(self):
        for key, value in (("script_sha256", "fake-extract-v2"), ("start_mode", 7)):
            fake = CountingAbaqus()
            fake.extraction_identity[key] = value
            with self.subTest(key=key):
                result, _, _ = self.run_with(fake=fake)
                self.assert_invalidated(result, "extraction script/settings changed")

    def test_a_changed_tracking_node_subset(self):
        fake = CountingAbaqus()
        calibration = QuickCalibration(self.config(), fake.solve, fake.extract, solver_identity=fake.identity())
        point = next(e["multipliers"] for e in self.first["evaluations"] if e["multipliers"]["E_face"] != 1.0)
        candidate = calibration.work / qc._job_name(calibration.model.render(point))
        stored = json.loads((candidate / qc.PROVENANCE_FILE).read_text(encoding="utf-8"))["node_set"]
        nodes = list(qc._load_state(candidate / "fe_modes.npz").sorted_modes()[0].node_ids)
        calibration.reference = object()  # candidate stage: the tracking subset is required
        calibration._node_order = [str(n) for n in nodes]
        self.assertEqual(qc._node_set(calibration._node_order, "SUBSET"), stored)
        calibration.fe_state(point)
        self.assertEqual(calibration.cache_decisions[-1]["decision"], VERIFIED_REUSE)  # the same subset
        calibration._cache.clear()
        calibration._node_order = [str(n) for n in nodes[1:]]  # another subset
        calibration.fe_state(point)
        decisions = [d["decision"] for d in calibration.cache_decisions[-2:]]
        self.assertEqual(decisions, [INVALIDATED, NEW_SOLVE])
        self.assertIn("tracking-node subset changed", calibration.cache_decisions[-2]["reason"])
        baseline = calibration.cache_decisions.copy()
        calibration.fe_state({"E_face": 1.0})  # the full-node baseline job contains every tracking node
        self.assertEqual(calibration.cache_decisions[len(baseline)]["decision"], VERIFIED_REUSE)

    def test_partial_or_corrupted_mode_data(self):
        job = self.baseline_job()
        data = job / "fe_modes.npz"
        data.write_bytes(data.read_bytes()[: data.stat().st_size // 2])  # truncated
        result, _, _ = self.run_with()
        self.assert_invalidated(result, "mode data corrupted or replaced")

    def test_a_corrupted_provenance_record(self):
        record_path = self.baseline_job() / qc.PROVENANCE_FILE
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["fe_last_mode"] = 30  # unchanged value, but rewritten by hand ...
        record["completion"]["mode_numbers"] = record["completion"]["mode_numbers"][:-1]  # ... and tampered
        record_path.write_text(json.dumps(record), encoding="utf-8")
        result, _, _ = self.run_with()
        self.assert_invalidated(result, "provenance record corrupted")
        record_path.write_text("{not json", encoding="utf-8")
        shutil.rmtree(self.work)
        self.run_with()
        (self.baseline_job() / qc.PROVENANCE_FILE).write_text("{not json", encoding="utf-8")
        result, _, _ = self.run_with()
        self.assert_invalidated(result, "provenance record unreadable")

    def test_an_old_cache_without_provenance_is_not_verified(self):
        for job in self.work.iterdir():
            (job / qc.PROVENANCE_FILE).unlink()  # fe_modes.npz alone is never sufficient
        result, _, fake = self.run_with()
        self.assert_invalidated(result, "NOT VERIFIED")
        self.assertEqual(fake.calls, self.first_fake.calls)

    def test_an_interrupted_job_without_evidence_needs_recovery(self):
        shutil.rmtree(self.work)
        job = self.baseline_job()
        job.mkdir(parents=True)
        (job / "partial.odb").write_text("half written")  # e.g. left by an older version or a crash
        with self.assertRaisesRegex(QuickCalibrationError, "without trustworthy termination evidence"):
            self.run_with()
        self.assertEqual(sorted(p.name for p in job.iterdir()), ["partial.odb"])  # neither deleted nor overwritten
        fake = CountingAbaqus()
        calibration = QuickCalibration(self.config(), fake.solve, fake.extract, solver_identity=fake.identity())
        with self.assertRaises(QuickCalibrationError):
            calibration.fe_state({"E_face": 1.0})
        self.assertEqual((fake.calls, calibration.new_solve_attempts), (0, 0))  # no budget used, nothing launched
        shutil.rmtree(job)  # the manual recovery
        result, _, fake = self.run_with()
        self.assertEqual(result["status"], STATUS_ESTIMATE)

    def test_an_unavailable_solver_identity_fails_closed(self):
        fake = CountingAbaqus()
        calibration = QuickCalibration(self.config(), fake.solve, fake.extract)  # no identity
        calibration.fe_state({"E_face": 1.0})
        self.assertEqual([d["decision"] for d in calibration.cache_decisions], [INVALIDATED, NEW_SOLVE])
        self.assertIn("current identity unavailable (fail closed)", calibration.cache_decisions[0]["reason"])
        self.assertEqual(fake.calls, 1)


# ----------------------------------------------------------------------------- in-progress safety marker

class InProgressMarkerTests(_Case):
    def calibration(self, solve=None, fake=None):
        fake = fake or CountingAbaqus()
        return QuickCalibration(self.config(), solve or fake.solve, fake.extract, solver_identity=fake.identity()), fake

    def test_completed_jobs_carry_no_marker_and_stay_reusable(self):
        self.run_with()
        self.assertFalse(any(self.work.rglob(qc.IN_PROGRESS_MARKER)))
        again, _, fake = self.run_with(1)
        self.assertEqual((again["status"], fake.calls), (STATUS_ESTIMATE, 0))

    def test_the_marker_exists_while_the_solver_runs(self):
        seen = []
        fake = CountingAbaqus()

        def solve(inp, job_dir, job_name):
            seen.append((Path(job_dir) / qc.IN_PROGRESS_MARKER).is_file())
            return fake.solve(inp, job_dir, job_name)

        calibration, _ = self.calibration(solve, fake)
        calibration.fe_state({"E_face": 1.0})
        self.assertEqual(seen, [True])
        self.assertFalse((self.baseline_job() / qc.IN_PROGRESS_MARKER).exists())

    def test_a_marker_write_failure_launches_no_solve(self):
        original = qc._write_json_atomically

        def failing(path, value):
            if Path(path).name == qc.IN_PROGRESS_MARKER:
                raise OSError("disk full (simulated)")
            return original(path, value)

        calibration, fake = self.calibration()
        with mock.patch.object(qc, "_write_json_atomically", side_effect=failing):
            with self.assertRaisesRegex(QuickCalibrationError, "Abaqus was not started"):
                calibration.fe_state({"E_face": 1.0})
        self.assertEqual(fake.calls, 0)  # zero FE jobs
        self.assertFalse(self.baseline_job().exists())

    def test_unconfirmed_termination_with_a_failed_record_never_cleans_up(self):
        original = qc._write_json_atomically
        identity = owned_processes.ProcessIdentity(4242, (7,))

        def failing(path, value):
            if Path(path).name == qc.UNCONFIRMED_MARKER:
                raise OSError("disk full (simulated)")
            return original(path, value)

        def stuck_solve(inp, job_dir, job_name):
            (Path(job_dir) / f"{job_name}.odb").write_text("being written")
            raise TerminationUnconfirmed("not confirmed", lambda: [identity])

        calibration, _ = self.calibration(stuck_solve)
        with mock.patch.object(qc, "_write_json_atomically", side_effect=failing):
            with self.assertRaises(TerminationUnconfirmed):
                calibration.fe_state({"E_face": 1.0})
        job = self.baseline_job()
        self.assertFalse((job / qc.UNCONFIRMED_MARKER).exists())
        self.assertTrue((job / qc.IN_PROGRESS_MARKER).exists())  # the safety marker remains
        snapshot = {p.name: p.read_bytes() for p in job.iterdir()}
        later, fake = self.calibration()
        later.process_state = lambda pid: (owned_processes.GONE, None)  # even then: no evidence was recorded
        with self.assertRaisesRegex(QuickCalibrationError, "never confirmed finished or stopped"):
            later.fe_state({"E_face": 1.0})
        self.assertEqual({p.name: p.read_bytes() for p in job.iterdir()}, snapshot)
        self.assertEqual((fake.calls, later.new_solve_attempts), (0, 0))

    def test_a_crash_leaves_an_active_marker_that_blocks_reuse_and_overwrite(self):
        self.run_with()
        job = self.baseline_job()
        (job / qc.IN_PROGRESS_MARKER).write_text(json.dumps({"job_name": job.name, "owner_pid": 1}))
        snapshot = {p.name: p.read_bytes() for p in job.iterdir()}
        for limit in (1, 100):  # even a complete-looking job with provenance is not reused while marked active
            with self.subTest(limit=limit), self.assertRaisesRegex(QuickCalibrationError, "may still run"):
                self.run_with(limit)
        self.assertEqual({p.name: p.read_bytes() for p in job.iterdir()}, snapshot)
        shutil.rmtree(self.work)
        job.mkdir(parents=True)  # a crash before anything was completed
        (job / qc.IN_PROGRESS_MARKER).write_text("{}")
        (job / f"{job.name}.odb").write_text("partial")
        with self.assertRaisesRegex(QuickCalibrationError, "may still run"):
            self.run_with()
        self.assertEqual(sorted(p.name for p in job.iterdir()), sorted([qc.IN_PROGRESS_MARKER, f"{job.name}.odb"]))


# ----------------------------------------------------------------------------- include depth

class IncludeDepthTests(_Case):
    def chain(self, levels: int) -> Path:
        """model -> f1 -> f2 -> ... -> f<levels> (each an absolute INPUT= reference)."""
        files = [self.folder / f"level{k}.inp" for k in range(1, levels + 1)]
        files[-1].write_text("** deepest\n")
        for current, deeper in zip(files, files[1:]):
            current.write_text(f"*Include, input={deeper}\n")
        model = self.folder / f"deep{levels}.inp"
        model.write_text(S.INP.replace("*Material, name=CFRP_Face",
                                       f"*Include, input={files[0]}\n*Material, name=CFRP_Face"))
        return model

    def test_nesting_beyond_the_limit_is_refused(self):
        supported = self.chain(qc._INCLUDE_DEPTH)
        report = qc.preflight(self.config(model_inp=supported.name))
        self.assertTrue(report.ready, report.lines())
        self.assertEqual(len(qc.input_file_fingerprints(supported.read_bytes())), qc._INCLUDE_DEPTH)
        too_deep = self.chain(qc._INCLUDE_DEPTH + 1)
        report = qc.preflight(self.config(model_inp=too_deep.name))
        self.assertFalse(report.ready)
        refusal = [c.detail for c in report.checks if c.item == "INP file references" and c.status == "REFUSED"]
        self.assertTrue(any("beyond the supported nesting depth" in text for text in refusal), refusal)
        with self.assertRaisesRegex(QuickCalibrationError, "nesting deeper than"):
            qc.input_file_fingerprints(too_deep.read_bytes())
        fake = CountingAbaqus()
        with self.assertRaises(qc.PreflightRefused):
            run_quick_calibration(self.config(model_inp=too_deep.name), fake.solve, fake.extract)
        self.assertEqual(fake.calls, 0)


# ----------------------------------------------------------------------------- budget and process safety

class SafetyTests(_Case):
    def test_a_cache_miss_with_an_exhausted_budget(self):
        fake = CountingAbaqus()
        calibration = QuickCalibration(self.config(1), fake.solve, fake.extract, solver_identity=fake.identity())
        calibration.fe_state({"E_face": 1.0})
        with self.assertRaises(FESolveBudgetExhausted):
            calibration.fe_state({"E_face": 1.1})
        self.assertEqual(fake.calls, 1)  # no new solve
        self.run_with()
        for job in sorted(self.work.iterdir())[:2]:
            (job / qc.PROVENANCE_FILE).unlink()  # two invalid jobs, budget for one
        result, paths, fake = self.run_with(1)
        self.assertEqual(result["refusal_code"], BUDGET_EXHAUSTED)
        self.assertEqual(fake.calls, 1)
        self.assertNotIn("calibrated_inp", paths)

    def test_provenance_is_written_only_after_a_complete_job(self):
        fake = CountingAbaqus()

        def failing_extract(odb, out, last):
            raise QuickCalibrationError("extraction failed (simulated)")

        calibration = QuickCalibration(self.config(), fake.solve, failing_extract, solver_identity=fake.identity())
        with self.assertRaises(QuickCalibrationError):
            calibration.fe_state({"E_face": 1.0})
        self.assertFalse(self.baseline_job().exists())  # no partial job, no provenance

    def test_unconfirmed_termination_never_deletes_or_overwrites(self):
        fake = CountingAbaqus()
        identity = owned_processes.ProcessIdentity(4242, (7,))

        def stuck_solve(inp, job_dir, job_name):
            (Path(job_dir) / f"{job_name}.odb").write_text("being written")
            raise TerminationUnconfirmed("not confirmed", lambda: [identity])

        calibration = QuickCalibration(self.config(), stuck_solve, fake.extract, solver_identity=fake.identity())
        with self.assertRaises(TerminationUnconfirmed):
            calibration.fe_state({"E_face": 1.0})
        job = self.baseline_job()
        marker = json.loads((job / qc.UNCONFIRMED_MARKER).read_text(encoding="utf-8"))
        self.assertEqual(marker["processes"], [{"pid": 4242, "created": [7]}])
        snapshot = {p.name: p.read_bytes() for p in job.iterdir()}
        later = QuickCalibration(self.config(), fake.solve, fake.extract, solver_identity=fake.identity())
        later.process_state = lambda pid: (owned_processes.ALIVE, (7,))  # still the same process
        with self.assertRaisesRegex(QuickCalibrationError, "neither reused, deleted nor overwritten"):
            later.fe_state({"E_face": 1.0})
        self.assertEqual({p.name: p.read_bytes() for p in job.iterdir()}, snapshot)  # untouched
        self.assertEqual(fake.calls, 0)
        later.process_state = lambda pid: (owned_processes.ALIVE, (99,))  # the PID now belongs to another process
        later.fe_state({"E_face": 1.0})  # confirmed gone: replaced at the same path through the budget
        self.assertEqual(fake.calls, 1)
        self.assertFalse((job / qc.UNCONFIRMED_MARKER).exists())
        self.assertEqual([d["decision"] for d in later.cache_decisions], [INVALIDATED, NEW_SOLVE])


if __name__ == "__main__":
    unittest.main()
