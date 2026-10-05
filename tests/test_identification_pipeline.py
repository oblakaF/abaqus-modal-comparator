"""M4.6 resumable identification pipeline: fake solver / extractor only (no Abaqus, no Abaqus Python)."""

from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.forward_model_manifest import ForwardCandidate, load_forward_model_manifest
from domain.identification_run import (
    RunIdentityError,
    RunJournal,
    RunLock,
    load_solver_profile,
    parse_solver_profile,
)
from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING
from m4_6_support import P0, TRUTH, FakeExtractor, FakeSolver, build_config, profile_dict
from services.fe_shape_pack import parse_shape_pack_record
from services.forward_builder import render_forward_input
from services.forward_solver import SolveFailure, verify_solve
from services.identification_pipeline import IdentificationPipeline
from services.identification_step import LMStatus, LMSettings
from services.shape_extraction import ExtractionRefusal


class _Tmp(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.tmp = Path(self._directory.name)

    def tearDown(self):
        self._directory.cleanup()

    def pipeline(self, **changes):
        return IdentificationPipeline(build_config(self.tmp, **changes))


class ChainTests(_Tmp):
    def test_end_to_end_chain_recovers_the_truth(self):
        pipeline = self.pipeline()
        result = pipeline.run()
        self.assertIs(result.status, LMStatus.CONVERGED)
        for name in TRUTH:
            self.assertAlmostEqual(result.parameters[name] / TRUTH[name], 1.0, places=3)
        counts = pipeline.counts()
        self.assertEqual(counts["identification_evaluations_journalled"], result.solves)
        self.assertEqual(counts["abaqus_solves_executed_total"], result.solves)  # no reuse configured
        kinds = [entry["kind"] for entry in pipeline.journal.entries]
        self.assertEqual(kinds[:3], ["solve", "extraction", "evaluation"])
        self.assertEqual(kinds[-1], "result")
        self.assertFalse(list(pipeline.run_dir.glob(".run.lock")))
        self.assertFalse(list((pipeline.run_dir / "packs").glob("raw_*")))  # retention: raw deleted

    def test_inp_is_the_m3_rendering(self):
        pipeline = self.pipeline()
        pipeline.run()
        config = pipeline.config
        source = (self.tmp / "store" / "models" / "syn.inp").read_bytes()
        for record in pipeline.journal.records("evaluation"):
            candidate = ForwardCandidate.create(config.model.manifest.parameterisation.parameterisation_id,
                                                **record["parameters"])
            rendered = render_forward_input(config.model, candidate, source)
            self.assertEqual((pipeline.run_dir / "jobs" / f"{record['job_name']}.inp").read_bytes(), rendered.content)
            self.assertEqual(record["generated_inp_sha256"], rendered.sha256)

    def test_identity_chain_in_the_journal(self):
        pipeline = self.pipeline()
        pipeline.run()
        solves = {s["job_name"]: s for s in pipeline.journal.records("solve")}
        extractions = {e["job_name"]: e for e in pipeline.journal.records("extraction")}
        for evaluation in pipeline.journal.records("evaluation"):
            job = evaluation["job_name"]
            self.assertEqual(solves[job]["generated_inp_sha256"], evaluation["generated_inp_sha256"])
            self.assertEqual(extractions[job]["odb_sha256"], solves[job]["odb_sha256"])
            self.assertEqual(extractions[job]["pack_content_sha256"], evaluation["pack_content_sha256"])
            self.assertEqual(solves[job]["profile_hash"], pipeline.config.profile.profile_hash)
        text = json.dumps(pipeline.journal.entries)
        self.assertNotIn(str(self.tmp), text)  # no machine paths
        self.assertNotIn("mtime", text)

    def test_deterministic_hashes(self):
        first = self.pipeline()
        first.run()
        second = IdentificationPipeline(build_config(self.tmp / "other"))
        second.run()
        self.assertEqual(first.run_hash, second.run_hash)
        hashes = lambda p: [e["evaluation_hash"] for e in p.journal.records("evaluation")]  # noqa: E731
        self.assertEqual(hashes(first), hashes(second))
        self.assertEqual(first.journal.records("result")[0]["parameters"],
                         second.journal.records("result")[0]["parameters"])


class ResumeTests(_Tmp):
    def test_resume_after_interruption_has_no_duplicate_solves(self):
        crashing = FakeSolver(crash_after=3)
        with self.assertRaises(KeyboardInterrupt):
            self.pipeline(solve_executor=crashing).run()
        healthy = FakeSolver()
        resumed = self.pipeline(solve_executor=healthy)
        result = resumed.run()
        self.assertIs(result.status, LMStatus.CONVERGED)
        jobs = [c.split("job=")[1].split()[0] for c in crashing.commands + healthy.commands]
        self.assertEqual(len(jobs), len(set(jobs)))  # every job solved exactly once over both sessions
        self.assertEqual(resumed.counts()["abaqus_solves_executed_total"], len(jobs))
        self.assertEqual(resumed.counts()["evaluations_replayed_this_session"], 3)

    def test_resume_after_completion_replays_everything(self):
        first = self.pipeline()
        result = first.run()
        solver = FakeSolver()
        again = self.pipeline(solve_executor=solver)
        replay = again.run()
        self.assertEqual(replay.parameters, result.parameters)
        self.assertEqual(solver.commands, [])
        self.assertEqual(again.counts()["evaluations_replayed_this_session"], replay.solves)
        self.assertEqual(len(again.journal.records("evaluation")), len(first.journal.records("evaluation")))
        self.assertEqual(len(again.journal.records("result")), 1)

    def test_interrupted_extraction_reuses_the_journalled_solve(self):
        with self.assertRaises(KeyboardInterrupt):
            self.pipeline(extraction_executor=FakeExtractor(fail=True)).run()
        solver = FakeSolver()
        resumed = self.pipeline(solve_executor=solver)
        resumed.run()
        first_job = resumed.journal.records("solve")[0]["job_name"]
        self.assertNotIn(first_job, " ".join(solver.commands))  # the journalled solve was not repeated

    def test_tampered_odb_is_refused_on_resume(self):
        with self.assertRaises(KeyboardInterrupt):
            self.pipeline(extraction_executor=FakeExtractor(fail=True)).run()
        pipeline = self.pipeline()
        solve = pipeline.journal.records("solve")[0]
        odb = pipeline.run_dir / "solves" / solve["job_name"] / f"{solve['job_name']}.odb"
        stat = odb.stat()
        odb.write_text(odb.read_text(encoding="utf-8").replace("52000", "52001"), encoding="utf-8")
        os.utime(odb, ns=(stat.st_atime_ns, stat.st_mtime_ns))  # same mtime: identity is by content
        with self.assertRaises(RunIdentityError):
            pipeline.run()

    def test_tampered_pack_is_refused(self):
        pipeline = self.pipeline()
        pipeline.run()
        extraction = pipeline.journal.records("extraction")[0]
        pack = pipeline.run_dir / "packs" / f"{extraction['job_name']}.npz"
        data = bytearray(pack.read_bytes())
        data[len(data) // 2] ^= 0xFF
        pack.write_bytes(bytes(data))
        from services.shape_extraction import load_run_pack

        with self.assertRaises(ExtractionRefusal):
            load_run_pack(pipeline.run_dir / "packs", extraction["job_name"], extraction["pack_content_sha256"])


class ReuseAndBudgetTests(_Tmp):
    def archive_from_first_run(self):
        first = IdentificationPipeline(build_config(self.tmp / "archive"))
        first.run()
        p0, h = P0, 0.05
        wanted = [dict(P0)]
        for name in P0:
            for factor in (1 + h, 1 - h):
                wanted.append(dict(P0, **{name: P0[name] * factor}))
        records = {}
        for evaluation in first.journal.records("evaluation"):
            if evaluation["parameters"] in wanted:
                path = first.run_dir / "packs" / f"{evaluation['job_name']}.shape-pack.json"
                records[evaluation["job_name"]] = parse_shape_pack_record(json.loads(path.read_text(encoding="utf-8")))
        return records, {"auto-id-run": first.run_dir}

    def test_reused_validated_packs_count_as_evaluations_not_solves(self):
        records, roots = self.archive_from_first_run()
        self.assertEqual(len(records), 5)  # p0 and the four +/-5 % points
        solver = FakeSolver()
        config = build_config(self.tmp / "fresh", archived_packs=records, solve_executor=solver)
        pipeline = IdentificationPipeline(replace(config, roots=dict(config.roots, **roots)))
        result = pipeline.run()
        self.assertIs(result.status, LMStatus.CONVERGED)
        counts = pipeline.counts()
        self.assertEqual(counts["reused_archived_evaluations"], 5)
        self.assertEqual(counts["abaqus_solves_executed_total"], result.solves - 5)
        self.assertEqual(len(solver.commands), result.solves - 5)

    def test_budget_counts_reused_evaluations(self):
        records, roots = self.archive_from_first_run()
        settings = LMSettings(mu_initial=1e-3, mu_decrease=10.0, max_step_attempts=3, solve_budget=5)
        config = build_config(self.tmp / "budget", archived_packs=records, settings=settings)
        pipeline = IdentificationPipeline(replace(config, roots=dict(config.roots, **roots)))
        result = pipeline.run()
        self.assertIs(result.status, LMStatus.SOLVE_BUDGET)
        self.assertEqual(result.solves, 5)
        self.assertEqual(pipeline.counts()["abaqus_solves_executed_total"], 0)

    def test_budget_without_reuse(self):
        settings = LMSettings(mu_initial=1e-3, mu_decrease=10.0, max_step_attempts=3, solve_budget=4)
        pipeline = self.pipeline(settings=settings)
        result = pipeline.run()
        self.assertIs(result.status, LMStatus.SOLVE_BUDGET)
        self.assertEqual(pipeline.counts()["abaqus_solves_executed_total"], 4)


class RefusalTests(_Tmp):
    def test_branch_exchange_refuses_and_stays_refused_on_resume(self):
        pipeline = self.pipeline(extraction_executor=FakeExtractor(exchange_below_e=48000.0))
        result = pipeline.run()
        self.assertIs(result.status, LMStatus.REFUSED)
        self.assertIn("BRANCH_LOSS", result.refusal)
        refused = [e for e in pipeline.journal.records("evaluation") if e["refusal"]]
        self.assertEqual(len(refused), 1)
        self.assertEqual(pipeline.counts()["abaqus_solves_executed_total"], result.solves)  # nothing after refusal
        solver = FakeSolver()
        again = self.pipeline(solve_executor=solver, extraction_executor=FakeExtractor(exchange_below_e=48000.0))
        self.assertIs(again.run().status, LMStatus.REFUSED)
        self.assertEqual(solver.commands, [])

    def test_failed_solve_stops_without_retry(self):
        first = self.pipeline()
        p0_job = first.config.frozen.identity.job_name
        pipeline = self.pipeline(solve_executor=FakeSolver(fail_jobs={p0_job}))
        with self.assertRaises(SolveFailure):
            pipeline.run()
        self.assertEqual(pipeline.journal.records("solve"), [])
        self.assertFalse((pipeline.run_dir / ".run.lock").exists())

    def test_failed_solve_is_not_retried_on_resume_without_authorisation(self):
        p0_job = build_config(self.tmp).frozen.identity.job_name
        with self.assertRaises(SolveFailure):
            self.pipeline(solve_executor=FakeSolver(fail_jobs={p0_job})).run()
        healthy = FakeSolver()
        with self.assertRaises(SolveFailure):  # plain resume: no silent retry
            self.pipeline(solve_executor=healthy).run()
        self.assertEqual(healthy.commands, [])
        retried = self.pipeline(solve_executor=healthy, retry_failed_solves=True)
        result = retried.run()
        self.assertIs(result.status, LMStatus.CONVERGED)
        self.assertEqual(len(retried.journal.records("solve_retry")), 1)
        counts = retried.counts()
        self.assertEqual(counts["failed_solves"], 1)
        self.assertEqual(counts["abaqus_solves_executed_total"], len(healthy.commands) + 1)  # the failed attempt too

    def test_configuration_identity_mismatches_are_refused(self):
        config = build_config(self.tmp)
        with self.assertRaises(RunIdentityError):
            IdentificationPipeline(replace(config, profile=parse_solver_profile(
                profile_dict(forward_model_id="OTHER/carbon-property-set-v1"))))
        other_frozen = replace(config.frozen, rows=config.frozen.rows[:-1])
        with self.assertRaises(RunIdentityError):
            IdentificationPipeline(replace(config, frozen=other_frozen))  # design built on another frozen set
        with self.assertRaises(RunIdentityError):  # start point is not the frozen baseline job
            IdentificationPipeline(replace(config, start=dict(P0, E_in_plane_mpa=52001.0))).run()

    def test_wrong_fe_geometry_expectation_is_refused(self):
        config = build_config(self.tmp)
        wrong = replace(config.expectation, fe_geometry_sha256="f" * 64)
        with self.assertRaises(ExtractionRefusal):
            IdentificationPipeline(replace(config, expectation=wrong)).run()


class JournalAndProfileTests(_Tmp):
    def test_journal_chain_and_identity(self):
        journal = RunJournal(self.tmp / "journal.json", {"run": 1})
        journal.append("evaluation", {"x": 1})
        journal.append("evaluation", {"x": 2})
        self.assertEqual(len(RunJournal(self.tmp / "journal.json", {"run": 1}).entries), 2)
        self.assertFalse((self.tmp / "journal.json.partial").exists())
        with self.assertRaises(RunIdentityError):
            RunJournal(self.tmp / "journal.json", {"run": 2})
        document = json.loads((self.tmp / "journal.json").read_text(encoding="utf-8"))
        document["entries"][0]["record"]["x"] = 9
        (self.tmp / "journal.json").write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaises(RunIdentityError):
            RunJournal(self.tmp / "journal.json", {"run": 1})

    def test_one_writer_per_run(self):
        with RunLock(self.tmp, "a"):
            with self.assertRaises(RunIdentityError):
                with RunLock(self.tmp, "b"):
                    pass
        with RunLock(self.tmp, "c"):
            pass

    def test_accepted_solver_profiles_render_the_archived_convention(self):
        profiles = ROOT / "docs" / "auto_id" / "solver_profiles"
        sp13 = load_solver_profile(profiles / "SP13.json")
        self.assertEqual(sp13.render_command(r"C:\SIMULIA\Commands\abq2024.bat", "SP13_a46d08b52995e078",
                                             r"D:\x\SP13_a46d08b52995e078.inp", None),
                         r"C:\SIMULIA\Commands\abq2024.bat job=SP13_a46d08b52995e078 "
                         r"input=D:\x\SP13_a46d08b52995e078.inp cpus=1 interactive ask_delete=OFF")
        sp02 = load_solver_profile(profiles / "SP02.json")
        self.assertEqual(sp02.render_command("abq2024.bat", "SP02_05239a3b56508244", "in.inp", r"D:\scratch"),
                         r"abq2024.bat job=SP02_05239a3b56508244 input=in.inp cpus=8 scratch=D:\scratch "
                         r"interactive ask_delete=OFF")
        with self.assertRaises(RunIdentityError):  # scratch required by the SP02 profile
            sp02.render_command("abq2024.bat", "SP02_x", "in.inp", None)
        for name, profile in (("SP02", sp02), ("SP13", sp13)):
            manifest = load_forward_model_manifest(ROOT / "docs" / "auto_id" / "forward_models" / f"{name}.forward.json")
            self.assertEqual((profile.forward_model_id, profile.job_prefix),
                             (manifest.forward_model_id, manifest.job_prefix))

    def test_profile_validation(self):
        for changes in ({"command_template": "abq2024.bat job={job} input={inp} cpus={cpus}{scratch}"},
                        {"command_template": r"C:\SIMULIA\abq.bat {abaqus} job={job} input={inp} cpus={cpus}{scratch}"},
                        {"cpus": 0}, {"scratch": {"path": "D:/x"}}, {"schema": "auto-id/solver-profile/v0"}):
            with self.subTest(changes=list(changes)), self.assertRaises(RunIdentityError):
                parse_solver_profile(profile_dict(**changes))
        self.assertNotEqual(parse_solver_profile(profile_dict(cpus=2)).profile_hash,
                            parse_solver_profile(profile_dict()).profile_hash)
        self.assertEqual(parse_solver_profile(profile_dict(provenance=["other"])).profile_hash,
                         parse_solver_profile(profile_dict()).profile_hash)  # provenance is not identity

    def test_verify_solve(self):
        pipeline = self.pipeline()
        pipeline.run()
        solve = pipeline.journal.records("solve")[0]
        directory = pipeline.run_dir / "solves" / solve["job_name"]
        verify_solve(solve, directory)
        (directory / f"{solve['job_name']}.odb").write_text("{}", encoding="utf-8")
        with self.assertRaises(RunIdentityError):
            verify_solve(solve, directory)


if __name__ == "__main__":
    unittest.main()
