"""M8-D2i — guarded Auto-ID execution: Execution Plan → guarded controller → CampaignRun journals → progress → backend.

Everything runs on a synthetic SPEC v1.2 campaign with fake executors (no Abaqus, no Abaqus Python, no real LM on real
specimens).  Authorisation is simulated only by the test-only ``SimulatedAuthority``; the production authority attests
nothing, so the production executor stays blocked.
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))

from services.campaign_lm_provenance import journal_document  # noqa: E402
from m4_6_support import FakeExtractor, FakeSolver  # noqa: E402
from m8_d2i_support import SimulatedAuthority, SyntheticWorld, tree  # noqa: E402
from services.campaign_execution_plan import ExecutionNotAuthorised  # noqa: E402
from services.guarded_execution import (  # noqa: E402
    ARCHIVE_EXTRACTION,
    CAMPAIGN_RUN,
    EXECUTION_LOG,
    NO_TRUSTED_SOURCE,
    PRODUCTION_AUTHORITY,
    SIMULATED,
    ExecutionAuthorisation,
    ExecutionContextError,
    ExecutionState,
    GuardedExecutionController,
    NoTrustedAuthority,
    campaign_journals,
    execution_provenance,
    operation_budget,
    outcome_text,
)
from services.run_progress import ProgressState, inspect_run_progress  # noqa: E402
from services.stored_run_evidence import evaluate_stored_run  # noqa: E402
import test_m7_campaign as m7  # noqa: E402

M7_RUN_A_MANIFEST = "e4ba607f06a69311b4d7adab089b5b8fdbbf98aae9d2da0837849e6c5da5bde6"


class _Synthetic(unittest.TestCase):
    world_changes: dict = {}

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m8_d2i_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.docs_before = tree(ROOT / "docs")
        self.world = SyntheticWorld(self.tmp, **self.world_changes)
        self.work = self.tmp / "work"
        self.plan = self.world.plan(self.work)
        self.context = self.world.context(self.work)
        self.authority = SimulatedAuthority()
        self.solver, self.extractor = FakeSolver(), FakeExtractor()

    def tearDown(self):
        self.assertEqual(tree(ROOT / "docs"), self.docs_before)  # governed records never touched

    def controller(self, authority=None, solver=None, extractor=None):
        solver = solver or self.solver
        extractor = extractor or self.extractor
        return GuardedExecutionController(self.context, authority or self.authority, abaqus_command="abq2024.bat",
                                          solve_executor_factory=lambda: solver,
                                          extraction_executor_factory=lambda: extractor,
                                          recheck=self.world.recheck(self.work))

    def execute(self, controller, operation, authorisation=None):
        authorisation = authorisation or self.authority.issue(controller.context, operation)
        with self.world.patched():
            return controller.execute(operation, authorisation)

    def extracted(self, controller=None):
        controller = controller or self.controller()
        outcome = self.execute(controller, ARCHIVE_EXTRACTION)
        self.assertIs(outcome.state, ExecutionState.COMPLETED, outcome.detail)
        self.extraction_outcome = outcome
        return controller

    def journal(self):
        journals = campaign_journals(self.context)
        self.assertEqual(len(journals), 1)
        return journals[0]


# ----------------------------------------------------------------------------- the authorisation contract

class AuthorisationContractTests(_Synthetic):
    def test_production_has_no_trusted_source_and_runs_nothing(self):
        controller = self.controller(authority=PRODUCTION_AUTHORITY)
        self.assertIsInstance(PRODUCTION_AUTHORITY, NoTrustedAuthority)
        self.assertEqual(controller.start_available(), (False, NO_TRUSTED_SOURCE))
        attested = self.authority.issue(self.context, ARCHIVE_EXTRACTION)  # attested by ANOTHER (test) authority
        for operation in (ARCHIVE_EXTRACTION, CAMPAIGN_RUN):
            with self.subTest(operation=operation), \
                    self.assertRaisesRegex(ExecutionNotAuthorised, "NO_TRUSTED_AUTHORISATION_SOURCE"):
                self.execute(controller, operation, attested)
        self.assertTrue(all("NOT_AUTHORISED" in row[3] for row in controller.gate_rows()))
        self.assertIsNone(PRODUCTION_AUTHORITY.authorisation_for(self.context, CAMPAIGN_RUN))
        self.assertEqual((self.solver.commands, self.extractor.calls), ([], 0))
        self.assertFalse((self.work / "archive_reuse").exists() or (self.work / "campaign").exists())

    def test_nothing_but_an_attested_bound_authorisation_counts(self):
        controller = self.controller()
        genuine = self.authority.issue(self.context, ARCHIVE_EXTRACTION)
        other_authority = SimulatedAuthority().issue(self.context, ARCHIVE_EXTRACTION)
        values = {
            "typed manifest hash": self.context.manifest_hash,
            "typed scope hash": self.context.scope_hash,
            "M7 manifest hash": M7_RUN_A_MANIFEST,
            "decision text": "AUTHORISED by SUPERVISOR: run it now",
            "plain JSON of a genuine record": json.loads(json.dumps(dict(genuine.binding(),
                                                                         attestation=genuine.attestation))),
            "forged attestation": ExecutionAuthorisation(**dict(genuine.binding(), attestation="0" * 64)),
            "attested by another authority": other_authority,
            "M7 authorisation (attested)": self.authority.issue(self.context, ARCHIVE_EXTRACTION,
                                                                manifest_hash=M7_RUN_A_MANIFEST),
            "another scope (attested)": self.authority.issue(self.context, ARCHIVE_EXTRACTION,
                                                             authorisation_scope_hash="f" * 64),
            "another budget (attested)": self.authority.issue(self.context, ARCHIVE_EXTRACTION, budget={
                "archive_extraction_jobs": [], "abaqus_solves": 5, "lm_evaluations": 0}),
        }
        for name, value in values.items():
            with self.subTest(value=name), self.assertRaisesRegex(ExecutionNotAuthorised, "Nothing executed"):
                self.execute(controller, ARCHIVE_EXTRACTION, value)
        self.assertEqual((self.solver.commands, self.extractor.calls), ([], 0))
        self.assertIs(self.execute(controller, ARCHIVE_EXTRACTION, genuine).state, ExecutionState.COMPLETED)

    def test_1_authorised_extraction_of_the_two_archived_odbs(self):
        controller = self.extracted()
        self.assertEqual(self.extractor.calls, 2)
        self.assertEqual(self.solver.commands, [])  # extraction only: no solve
        self.assertEqual(len(self.extraction_outcome.summary["archive_extractions"]), 2)
        journal = json.loads((self.work / "archive_reuse" / "journal.json").read_text(encoding="utf-8"))
        journal_document(journal, "archive")
        records = [e for e in journal["entries"] if e["kind"] == "archive_extraction"]
        self.assertEqual(sorted(r["record"]["job_name"] for r in records),
                         sorted(self.context.operations["archive_extraction_jobs"]))
        self.assertFalse(list((self.work / "archive_reuse" / "odb").glob("*.odb")))  # run-store copies removed
        for entry in self.world.reuse_document["odbs"]:  # the archived originals are unchanged
            path = self.world.archive / entry["odb"]["relative_path"]
            self.assertEqual(tree(path.parent)[path.name], entry["odb"]["sha256"])
        again = self.execute(controller, ARCHIVE_EXTRACTION)  # resumable: journalled extractions are reused
        self.assertIs(again.state, ExecutionState.COMPLETED)
        self.assertEqual(self.extractor.calls, 2)

    def test_2_an_extraction_authorisation_never_authorises_the_run(self):
        controller = self.extracted()
        extraction = self.authority.issue(self.context, ARCHIVE_EXTRACTION)
        relabelled = self.authority.issue(self.context, CAMPAIGN_RUN,
                                          budget=extraction.budget)  # the extraction's budget under another name
        run_budget = self.authority.issue(self.context, ARCHIVE_EXTRACTION,  # an extraction carrying the run budget
                                          budget=operation_budget(self.context.scope, CAMPAIGN_RUN))
        for value in (extraction, relabelled, run_budget):
            with self.subTest(value=value.operation), self.assertRaisesRegex(ExecutionNotAuthorised, "operation|budget"):
                self.execute(controller, CAMPAIGN_RUN, value)
        self.assertEqual(self.solver.commands, [])
        self.assertFalse((self.work / "campaign").exists())

    def test_a_run_without_its_archive_extraction_fails_without_solving(self):
        outcome = self.execute(self.controller(), CAMPAIGN_RUN)
        self.assertIs(outcome.state, ExecutionState.FAILED)
        self.assertIn("no journalled archive extraction", outcome.detail)
        self.assertEqual(self.solver.commands, [])


# ----------------------------------------------------------------------------- the simulated end-to-end run

class EndToEndTests(_Synthetic):
    def test_3_4_5_full_simulated_run_a_journals_and_backend(self):
        controller = self.extracted()
        outcome = self.execute(controller, CAMPAIGN_RUN)
        self.assertIs(outcome.state, ExecutionState.COMPLETED, outcome.detail)
        summary = outcome.summary
        self.assertEqual(summary["status"], "CONVERGED")
        self.assertAlmostEqual(summary["parameters"]["E_in_plane_mpa"], m7.TRUTH_E, delta=m7.TRUTH_E * 2e-3)
        self.assertLessEqual(summary["abaqus_solves_used"], self.context.operations["max_new_abaqus_solves"])
        # 4. the real journal structure: <run root>/campaign/<run hash>/journal.json + governed pipeline journals
        journal = self.journal()
        self.assertEqual(Path(summary["journal"]).resolve(), journal.resolve())
        document = json.loads(journal.read_text(encoding="utf-8"))
        journal_document(document, "campaign")
        self.assertEqual(journal.parent.name, summary["run_hash"])
        self.assertEqual(document["run_identity"]["manifest_hash"], self.context.manifest_hash)
        self.assertEqual(document["run_identity"]["campaign_hash"], self.context.campaign_hash)
        pipelines = sorted((self.work / "specimens").rglob("journal.json"))
        self.assertEqual(len(pipelines), 2)
        for path in pipelines:
            journal_document(json.loads(path.read_text(encoding="utf-8")), "pipeline")
        progress = inspect_run_progress(self.context.definition, journal, self.context.specimens)
        self.assertIs(progress.state, ProgressState.RESULT_RECORDED)
        self.assertIsNotNone(progress.fingerprint)
        # 5. the completed journal goes to the existing backend unchanged
        evaluation = evaluate_stored_run(self.context.definition, journal, self.world.repo, self.context.roots,
                                         specimens=self.context.specimens)
        record = evaluation.readiness.to_dict()
        self.assertEqual(record["campaign"]["run_hash"], summary["run_hash"])
        self.assertEqual(evaluation.notes, ())
        # 12. a simulated run is labelled and never a material result of a real specimen
        self.assertEqual(execution_provenance(journal), SIMULATED)
        self.assertIn(SIMULATED, outcome_text(outcome))
        log = json.loads((self.work / EXECUTION_LOG).read_text(encoding="utf-8"))
        self.assertIn("NOT_GOVERNED_EVIDENCE", log["labels"])
        self.assertEqual([(a["operation"], a["state"], a["simulated"]) for a in log["attempts"]],
                         [(ARCHIVE_EXTRACTION, "COMPLETED", True), (CAMPAIGN_RUN, "COMPLETED", True)])
        self.assertNotIn("attestation", json.dumps(log))  # the opaque attestation is never written out
        self.assertEqual(self.context.definition.campaign_id, "SYN/M8-D2i")
        self.assertIsNone(execution_provenance(self.tmp / "nowhere" / "campaign" / "x" / "journal.json"))

    def test_7_branch_tracking_refusal(self):
        self.extracted()
        outcome = self.execute(self.controller(extractor=m7._SelectiveExchange("SYB", below_e=51000.0)), CAMPAIGN_RUN)
        self.assertIs(outcome.state, ExecutionState.COMPLETED, outcome.detail)
        self.assertEqual(outcome.summary["status"], "REFUSED")
        document = json.loads(self.journal().read_text(encoding="utf-8"))
        refused = [e["record"] for e in document["entries"] if e["kind"] == "evaluation" and e["record"]["refusal"]]
        self.assertEqual(refused[-1]["refusal"]["specimen"], "B")

    def test_background_start_keeps_the_caller_free_and_finishes(self):
        controller = self.extracted()
        with self.world.patched():
            thread = controller.start(CAMPAIGN_RUN, self.authority.issue(self.context, CAMPAIGN_RUN))
            outcome = controller.wait(120)
        self.assertFalse(thread.is_alive())
        self.assertIs(controller.state, ExecutionState.COMPLETED)
        self.assertEqual(outcome.summary["status"], "CONVERGED")
        with self.assertRaisesRegex(ExecutionNotAuthorised, "Nothing executed"):
            controller.start(CAMPAIGN_RUN, "e4ba607f")
        self.assertIs(controller.state, ExecutionState.REFUSED)


class BudgetTests(_Synthetic):
    world_changes = {"abaqus_solve_budget": 1}

    def test_6_hard_solve_budget_stops_without_extension(self):
        self.assertEqual(self.context.operations["max_new_abaqus_solves"], 1)
        self.extracted()
        outcome = self.execute(self.controller(), CAMPAIGN_RUN)
        self.assertEqual(outcome.summary["status"], "SOLVE_BUDGET")
        self.assertEqual(len(self.solver.commands), 1)
        self.assertEqual(outcome.summary["abaqus_solves_used"], 1)


class LMBudgetTests(_Synthetic):
    world_changes = {"lm": dict(m7.synthetic_definition()["lm"], evaluation_budget=4)}

    def test_6_lm_evaluation_budget(self):
        self.assertEqual(self.context.operations["lm_evaluation_budget"], 4)
        self.extracted()
        outcome = self.execute(self.controller(), CAMPAIGN_RUN)
        document = json.loads(self.journal().read_text(encoding="utf-8"))
        evaluations = [e for e in document["entries"] if e["kind"] == "evaluation"]
        self.assertLessEqual(len(evaluations), 4)
        self.assertLessEqual(outcome.summary["lm_evaluations"] or 0, 4)


# ----------------------------------------------------------------------------- failure, stop, resume

class _Stopping(FakeSolver):
    """Requests a stop on the controller after its first solve (the next solve must not start)."""

    def __init__(self, controller_box):
        super().__init__()
        self.box = controller_box

    def __call__(self, command, directory):
        result = super().__call__(command, directory)
        self.box["controller"].stop()
        return result


class _Failing(FakeSolver):
    def __call__(self, command, directory):
        raise OSError("simulated executor error (licence server unavailable)")


class FailureResumeTests(_Synthetic):
    def jobs(self, *solvers):
        return [c.split("job=")[1].split()[0] for solver in solvers for c in solver.commands]

    def test_8_9_11_interruption_reopen_and_resume_without_duplicate_solves(self):
        self.extracted()
        crashing = FakeSolver(crash_after=1)
        outcome = self.execute(self.controller(solver=crashing), CAMPAIGN_RUN)
        self.assertIs(outcome.state, ExecutionState.FAILED)
        self.assertIn("interrupted", outcome.detail)
        self.assertEqual(len(crashing.commands), 1)
        journal = self.journal()
        self.assertFalse(list(journal.parent.glob(".run.lock")))  # the run lock is released
        progress = inspect_run_progress(self.context.definition, journal, self.context.specimens)
        self.assertIsNot(progress.state, ProgressState.JOURNAL_NOT_VERIFIED)  # reopened safely: journals intact and verified
        self.context = self.world.context(self.work)  # the plan folder (now a run root) reopens
        healthy = FakeSolver()
        resumed = self.execute(self.controller(solver=healthy), CAMPAIGN_RUN)
        self.assertEqual(resumed.summary["status"], "CONVERGED")
        jobs = self.jobs(crashing, healthy)
        self.assertEqual(len(jobs), len(set(jobs)))  # every job solved once over both sessions
        self.assertGreater(resumed.summary["evaluations_replayed_this_session"], 0)
        third = FakeSolver()
        replay = self.execute(self.controller(solver=third), CAMPAIGN_RUN)
        self.assertEqual(third.commands, [])  # a completed run replays: no new solve
        self.assertEqual(replay.summary["parameters"], resumed.summary["parameters"])

    def test_8_executor_error_fails_safely(self):
        self.extracted()
        outcome = self.execute(self.controller(solver=_Failing()), CAMPAIGN_RUN)
        self.assertIs(outcome.state, ExecutionState.FAILED)
        self.assertIn("OSError: simulated executor error", outcome.detail)
        progress = inspect_run_progress(self.context.definition, self.journal(), self.context.specimens)
        self.assertIsNot(progress.state, ProgressState.JOURNAL_NOT_VERIFIED)
        resumed = self.execute(self.controller(), CAMPAIGN_RUN)
        self.assertEqual(resumed.summary["status"], "CONVERGED")

    def test_stop_before_the_next_solve_and_resume(self):
        self.extracted()
        box = {}
        stopping = _Stopping(box)
        controller = self.controller(solver=stopping)
        box["controller"] = controller
        outcome = self.execute(controller, CAMPAIGN_RUN)
        self.assertIs(outcome.state, ExecutionState.STOPPED, outcome.detail)
        self.assertEqual(len(stopping.commands), 1)
        self.assertIsNot(inspect_run_progress(self.context.definition, self.journal(), self.context.specimens).state,
                         ProgressState.JOURNAL_NOT_VERIFIED)
        healthy = FakeSolver()
        resumed = self.execute(self.controller(solver=healthy), CAMPAIGN_RUN)
        self.assertEqual(resumed.summary["status"], "CONVERGED")
        jobs = self.jobs(stopping, healthy)
        self.assertEqual(len(jobs), len(set(jobs)))


# ----------------------------------------------------------------------------- changes after authorisation

class ChangeAfterAuthorisationTests(_Synthetic):
    def assert_refused(self, change, pattern):
        controller = self.extracted()
        authorisation = self.authority.issue(self.context, CAMPAIGN_RUN)
        change()
        with self.assertRaisesRegex(ExecutionNotAuthorised, pattern):
            self.execute(controller, CAMPAIGN_RUN, authorisation)
        self.assertEqual(self.solver.commands, [])
        self.assertFalse((self.work / "campaign").exists())

    def test_10_definition_changed(self):
        def change():
            data = json.loads(self.world.definition_path.read_text(encoding="utf-8"))
            data["abaqus_solve_budget"] = 40
            self.world.definition_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        self.assert_refused(change, "STALE: the campaign definition file changed")

    def test_10_archive_plan_changed_gives_another_manifest(self):
        def change():
            document = dict(self.world.reuse_document, provenance=["changed after authorisation"])
            self.world.write_reuse(document)

        self.assert_refused(change, "STALE: the sources or records now give manifest")

    def test_10_plan_manifest_changed(self):
        def change():
            path = self.work / "run_manifest.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["budgets"]["max_new_abaqus_solves"] = 99
            path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")

        self.assert_refused(change, "not one complete, consistent execution plan")

    def test_10_a_source_no_longer_verified(self):
        passing = self.world.passing_prerun

        def failing_prerun(path, *args, **kwargs):  # a pinned source no longer verifies after authorisation
            validation = passing(path)
            return type(validation)(validation.path, validation.rows, dict(validation.sections, Sources="MISMATCH"),
                                    validation.campaign_hash)

        controller = self.extracted()
        authorisation = self.authority.issue(self.context, CAMPAIGN_RUN)
        with mock.patch.object(self.world, "passing_prerun", side_effect=failing_prerun), \
                self.assertRaisesRegex(ExecutionNotAuthorised, "Sources MISMATCH"):
            self.execute(controller, CAMPAIGN_RUN, authorisation)
        self.assertEqual(self.solver.commands, [])

    def test_opening_a_damaged_or_missing_plan_is_refused(self):
        with self.assertRaisesRegex(ExecutionContextError, "cannot be read"):
            self.world.context(self.tmp / "empty")
        (self.work / "notes.txt").write_text("user file", encoding="utf-8")
        with self.assertRaisesRegex(ExecutionContextError, "not one complete, consistent"):
            self.world.context(self.work)


# ----------------------------------------------------------------------------- GUI and CLI

class GuiTests(_Synthetic):
    def application(self):
        import test_m8_d1_campaign_draft as d1

        return d1.GuiTests.application(self)

    @contextlib.contextmanager
    def gui(self, authority=None):
        import material_identification_ui as ui

        from services import forward_solver, shape_extraction

        with self.world.patched(), mock.patch.object(ui, "AUTO_ID_REPO_ROOT", self.world.repo),                 mock.patch.object(ui, "_draft_fixtures", return_value=None), \
                mock.patch("domain.experiment_fixture.fixture_roots_from_environment", return_value=self.world.roots), \
                mock.patch.object(forward_solver, "subprocess_executor", side_effect=lambda *a: self.solver), \
                mock.patch.object(shape_extraction, "pinned_script_executor", side_effect=lambda *a: self.extractor):
            application = self.application()
            if authority is not None:
                application.auto_id_execution_authority = authority  # test-only injection
            yield ui, application

    def test_production_gui_opens_the_plan_and_keeps_start_disabled(self):
        import test_m8_d1_campaign_draft as d1

        with self.gui() as (ui, application):
            buttons = d1.GuiTests.buttons(application)
            for label in (ui.AUTO_ID_EXEC_OPEN_LABEL, ui.AUTO_ID_EXEC_EXTRACT_LABEL, ui.AUTO_ID_EXEC_RUN_LABEL,
                          ui.AUTO_ID_EXEC_STOP_LABEL, ui.AUTO_ID_EXEC_REFRESH_LABEL, ui.AUTO_ID_EXEC_JOURNAL_LABEL):
                self.assertIn(label, buttons)
            starts = application.material_auto_id_exec_start_buttons
            self.assertTrue(all(b.kwargs.get("state") == "disabled" for b in starts))
            ui.open_guarded_execution(application, str(self.work))
            text = application.material_auto_id_exec_label.kwargs["text"]
            self.assertIn("NOT_AUTHORISED", text)
            self.assertIn("NO_TRUSTED_AUTHORISATION_SOURCE", text)
            self.assertTrue(all(b.kwargs.get("state") == "disabled" for b in starts))
            rows = list(application.material_auto_id_exec_table.items.values())
            self.assertIn(("Gate", ARCHIVE_EXTRACTION), {(r[0], r[1]) for r in rows})
            for operation in (ARCHIVE_EXTRACTION, CAMPAIGN_RUN):
                ui.start_guarded_operation(application, operation)
                self.assertIn("not started: NOT_AUTHORISED", application.material_auto_id_exec_label.kwargs["text"])
        self.assertEqual((self.solver.commands, self.extractor.calls), ([], 0))
        self.assertFalse((self.work / "archive_reuse").exists())

    def test_simulated_authority_runs_extraction_then_run_and_shows_progress(self):
        with self.gui(SimulatedAuthority()) as (ui, application):
            ui.open_guarded_execution(application, str(self.work))
            starts = application.material_auto_id_exec_start_buttons
            self.assertTrue(all(b.kwargs.get("state") == "normal" for b in starts))
            for operation in (ARCHIVE_EXTRACTION, CAMPAIGN_RUN):
                ui.start_guarded_operation(application, operation)
                application.auto_id_execution_controller.wait(120)
            ui.refresh_guarded_execution(application)
            text = application.material_auto_id_exec_label.kwargs["text"]
            self.assertIn("COMPLETED", text)
            self.assertIn(SIMULATED, text)
            rows = list(application.material_auto_id_exec_table.items.values())
            self.assertTrue(any(r[0] == "Progress" and r[3] == "RESULT_RECORDED" for r in rows))
            ui.show_guarded_journal(application)
            self.assertEqual(Path(application.auto_id_selected_run_path).resolve(), self.journal().resolve())
            ui.stop_guarded_execution(application)
            self.assertIn("Nothing is running", application.material_auto_id_exec_label.kwargs["text"])
        self.assertGreater(len(self.solver.commands), 0)
        self.assertEqual(execution_provenance(self.journal()), SIMULATED)

    def test_cli_refuses_without_a_trusted_source(self):
        import auto_id_execute as tool

        authorisation = self.tmp / "authorisation.json"
        genuine = self.authority.issue(self.context, ARCHIVE_EXTRACTION)
        authorisation.write_text(json.dumps(dict(genuine.binding(), attestation=genuine.attestation)), encoding="utf-8")
        with self.world.patched(), mock.patch.object(tool, "ROOT", self.world.repo), \
                mock.patch.object(tool, "load_fixtures", return_value=None), \
                mock.patch.object(tool, "fixture_roots_from_environment", return_value=self.world.roots):
            for command in ("extract-archive", "run"):
                self.assertEqual(tool.main([command, "--work-dir", str(self.work), "--authorisation",
                                            str(authorisation)]), 2)
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                self.assertEqual(tool.main(["status", "--work-dir", str(self.work)]), 0)
            status = json.loads(printed.getvalue())
            self.assertEqual(status["manifest_hash"], self.context.manifest_hash)
            self.assertEqual(status["start_available"][0], False)
        self.assertFalse((self.work / "archive_reuse").exists())


class RealPlanTests(unittest.TestCase):
    """The real SP-02 + SP-13 SPEC v1.2 plan opens as current; production execution stays blocked (store-gated)."""

    @classmethod
    def setUpClass(cls):
        from domain.experiment_fixture import fixture_roots_from_environment

        try:
            cls.roots = dict(fixture_roots_from_environment())
        except Exception:  # noqa: BLE001
            cls.roots = {}
        if {"snadwich", "carbon-project-archive"} - set(cls.roots):
            raise unittest.SkipTest("data stores not configured")
        import test_m8_d2g_campaign_finalisation as d2g
        from services.auto_id_wizard import load_fixtures
        from services.campaign_execution_plan import prepare_execution_plan
        from services.campaign_finalisation import export_campaign_definition, finalise_campaign

        cls._tmp = tempfile.TemporaryDirectory(prefix="m8_d2i_real_")
        tmp = Path(cls._tmp.name)
        cls.fixtures = load_fixtures(ROOT)
        draft = d2g.complete_draft(ROOT, cls.fixtures, decision="SUPERVISOR M8-D2i test decision")
        finalised = finalise_campaign(draft, ROOT, cls.fixtures)
        definition = export_campaign_definition(draft, tmp / "sp02_sp13.campaign.json", ROOT, cls.fixtures, (ROOT,),
                                                finalised.campaign_hash).path
        cls.work = tmp / "plan"
        cls.work.mkdir()
        cls.plan = prepare_execution_plan(definition, cls.work, ROOT, cls.fixtures, cls.roots, (ROOT, *cls.roots.values()))
        cls.before = tree(cls.work)
        cls.context = guarded_open(cls.work, cls.fixtures, cls.roots)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "_tmp"):
            cls._tmp.cleanup()

    def test_the_real_plan_opens_current_and_production_refuses(self):
        self.assertEqual(self.context.manifest_hash, self.plan.manifest_hash)
        self.assertEqual(self.context.scope_hash, self.plan.authorisation_scope_hash)
        self.assertEqual(self.context.operations["archive_extractions"], 2)
        self.assertEqual(tree(self.work), self.before)  # opening writes nothing
        solver, extractor = FakeSolver(), FakeExtractor()
        controller = GuardedExecutionController(self.context, PRODUCTION_AUTHORITY,
                                                solve_executor_factory=lambda: solver,
                                                extraction_executor_factory=lambda: extractor)
        self.assertEqual(controller.start_available(), (False, NO_TRUSTED_SOURCE))
        for operation in (ARCHIVE_EXTRACTION, CAMPAIGN_RUN):
            with self.assertRaisesRegex(ExecutionNotAuthorised, "NO_TRUSTED_AUTHORISATION_SOURCE"):
                controller.execute(operation, SimulatedAuthority().issue(self.context, operation))
        self.assertEqual((solver.commands, extractor.calls), ([], 0))
        self.assertEqual(tree(self.work), self.before)


def guarded_open(work, fixtures, roots):
    from services.guarded_execution import open_execution_context

    return open_execution_context(work, ROOT, fixtures, roots)


class GuardTests(unittest.TestCase):
    def test_only_the_no_trusted_authority_exists_in_src(self):
        attesting = []
        for path in list((ROOT / "src").rglob("*.py")) + list((ROOT / "tools").rglob("*.py")):
            tree_ = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree_):
                if isinstance(node, ast.ClassDef) and any(isinstance(b, ast.FunctionDef) and b.name == "attests"
                                                          for b in node.body):
                    attesting.append((path.name, node.name))
                if isinstance(node, ast.Attribute) and node.attr == "auto_id_execution_authority" and \
                        isinstance(node.ctx, ast.Store):
                    self.fail(f"{path.name} assigns an execution authority")
        self.assertEqual(attesting, [("guarded_execution.py", "NoTrustedAuthority")])
        self.assertFalse(NoTrustedAuthority().attests(None))

    def test_the_controller_reuses_the_executor_and_runs_no_process_itself(self):
        source = (ROOT / "src/services/guarded_execution.py").read_text(encoding="utf-8")
        tree_ = ast.parse(source)
        modules = {node.module or "" for node in ast.walk(tree_) if isinstance(node, ast.ImportFrom)}
        imported = {alias.name for node in ast.walk(tree_) if isinstance(node, (ast.Import, ast.ImportFrom))
                    for alias in node.names}
        self.assertFalse(imported & {"subprocess", "run_bounded_lm", "subprocess_executor", "pinned_script_executor"})
        self.assertFalse(any(m.endswith(("forward_solver", "shape_extraction", "identification_step")) for m in modules))
        for name in ("extract_archived_odbs", "journalled_archive_records", "reused_pack_records", "CampaignRun(",
                     "CampaignRunConfig(", "prepare_campaign_plan"):
            self.assertIn(f"executor_module.{name}", source)
        self.assertNotIn("require_executable", source)
        gui = (ROOT / "src/material_identification_ui.py").read_text(encoding="utf-8")
        for name in ("CampaignRun", "judge_campaign_run", "run_bounded_lm", "SimulatedAuthority"):
            self.assertNotIn(name, gui)


if __name__ == "__main__":
    unittest.main()
