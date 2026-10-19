"""M8-D2i review corrections (PR #92).

A. The attempt log ``guarded_execution.json`` is written in two phases.  A write error or a damaged earlier log never
   leaves the controller RUNNING, never silently overwrites the earlier log, never presents a completed operation as
   confirmed, and never touches the computation journals; the plan can always be reopened.
B. A simulated run (or one whose execution provenance cannot be established) is never presented, shown as Engineering
   Constants or exported as a material result; the backend record is kept unchanged; archived M7 runs behave as before.

Synthetic campaign and fake executors only (no Abaqus, no extraction, no LM on real specimens).
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from m4_6_support import FakeExtractor, FakeSolver  # noqa: E402
from m8_d2i_support import SimulatedAuthority, SyntheticWorld, tree  # noqa: E402
from services import guarded_execution as guarded_module  # noqa: E402
from services import stored_run_evidence  # noqa: E402
from services.auto_id_evidence_export import ExportRefusalCode  # noqa: E402
from services.campaign_lm_provenance import journal_document  # noqa: E402
from services.execution_provenance import (  # noqa: E402
    EXECUTION_LOG,
    SIMULATED,
    SIMULATED_MARKER,
    ProvenanceState,
    run_execution_provenance,
)
from services.guarded_execution import (  # noqa: E402
    ARCHIVE_EXTRACTION,
    CAMPAIGN_RUN,
    ExecutionLogError,
    ExecutionState,
    GuardedExecutionController,
    campaign_journals,
)


@contextlib.contextmanager
def failing_log_writes(*failing_calls):
    """Make the n-th replace of the attempt log fail (1 = the STARTED entry, 2 = the outcome)."""

    real, calls = os.replace, {"n": 0}

    def replace(source, destination):
        if Path(destination).name == EXECUTION_LOG:
            calls["n"] += 1
            if calls["n"] in failing_calls:
                raise OSError(f"injected write error #{calls['n']} of {EXECUTION_LOG}")
        return real(source, destination)

    with mock.patch.object(guarded_module.os, "replace", side_effect=replace):
        yield calls


class _World(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m8_d2i_pr92_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.docs_before = tree(ROOT / "docs")
        self.world = SyntheticWorld(self.tmp)
        self.work = self.tmp / "work"
        self.world.plan(self.work)
        self.context = self.world.context(self.work)
        self.authority = SimulatedAuthority()
        self.solver, self.extractor = FakeSolver(), FakeExtractor()

    def tearDown(self):
        self.assertEqual(tree(ROOT / "docs"), self.docs_before)

    def controller(self):
        return GuardedExecutionController(self.context, self.authority, abaqus_command="abq2024.bat",
                                          solve_executor_factory=lambda: self.solver,
                                          extraction_executor_factory=lambda: self.extractor,
                                          recheck=self.world.recheck(self.work))

    def execute(self, controller, operation):
        with self.world.patched():
            return controller.execute(operation, self.authority.issue(controller.context, operation))

    def log(self) -> dict:
        return json.loads((self.work / EXECUTION_LOG).read_text(encoding="utf-8"))

    def run_through(self):
        controller = self.controller()
        for operation in (ARCHIVE_EXTRACTION, CAMPAIGN_RUN):
            self.assertIs(self.execute(controller, operation).state, ExecutionState.COMPLETED)
        return campaign_journals(self.context)[0]


# ----------------------------------------------------------------------------- A. attempt log robustness

class AttemptLogTests(_World):
    def test_a_damaged_earlier_log_refuses_before_running_and_is_never_overwritten(self):
        log = self.work / EXECUTION_LOG
        log.write_bytes(b'{"schema": "something else"')
        before = log.read_bytes()
        with self.assertRaisesRegex(ExecutionLogError, "damaged or unrecognised.*never overwritten"):
            self.execute(self.controller(), ARCHIVE_EXTRACTION)
        self.assertEqual(log.read_bytes(), before)
        self.assertEqual((self.solver.commands, self.extractor.calls), ([], 0))
        self.assertFalse((self.work / "archive_reuse").exists())
        self.assertEqual(self.world.context(self.work).manifest_hash, self.context.manifest_hash)  # still reopens

    def test_a_started_entry_that_cannot_be_written_runs_nothing(self):
        with failing_log_writes(1), self.assertRaisesRegex(ExecutionLogError, "could not be written"):
            self.execute(self.controller(), ARCHIVE_EXTRACTION)
        self.assertEqual((self.solver.commands, self.extractor.calls), ([], 0))
        self.assertFalse((self.work / EXECUTION_LOG).exists())
        self.assertFalse(list(self.work.glob(f".{EXECUTION_LOG}.partial")))

    def test_sync_outcome_write_error_is_completed_but_unconfirmed(self):
        controller = self.controller()
        with failing_log_writes(2):
            outcome = self.execute(controller, ARCHIVE_EXTRACTION)
        self.assertIs(outcome.state, ExecutionState.COMPLETED_LOG_NOT_RECORDED)
        self.assertIn("injected write error #2", outcome.log_error)
        self.assertIn("attempt log NOT recorded", outcome.detail)
        self.assertIn("ATTEMPT LOG NOT RECORDED", guarded_module.outcome_text(outcome))
        self.assertEqual(self.log()["attempts"][-1]["state"], "STARTED")  # never a confirmed success
        archive = json.loads((self.work / "archive_reuse" / "journal.json").read_text(encoding="utf-8"))
        journal_document(archive, "archive")  # the computation journal is intact
        self.assertFalse(list(self.work.glob(f".{EXECUTION_LOG}.partial")))
        reopened = self.world.context(self.work)  # the plan reopens; a later attempt is logged normally
        self.context = reopened
        run = self.execute(self.controller(), CAMPAIGN_RUN)
        self.assertIs(run.state, ExecutionState.COMPLETED)
        self.assertEqual([a["state"] for a in self.log()["attempts"]], ["STARTED", "COMPLETED"])
        journal_document(json.loads(campaign_journals(self.context)[0].read_text(encoding="utf-8")), "campaign")

    def test_sync_run_outcome_write_error_keeps_the_journals(self):
        controller = self.controller()
        self.execute(controller, ARCHIVE_EXTRACTION)
        with failing_log_writes(2):
            outcome = self.execute(controller, CAMPAIGN_RUN)
        self.assertIs(outcome.state, ExecutionState.COMPLETED_LOG_NOT_RECORDED)
        self.assertEqual(outcome.summary["status"], "CONVERGED")
        journal_document(json.loads(campaign_journals(self.context)[0].read_text(encoding="utf-8")), "campaign")

    def test_background_outcome_write_error_ends_in_a_final_state(self):
        controller = self.controller()
        self.execute(controller, ARCHIVE_EXTRACTION)
        with self.world.patched(), failing_log_writes(2):
            controller.start(CAMPAIGN_RUN, self.authority.issue(self.context, CAMPAIGN_RUN))
            outcome = controller.wait(120)
        self.assertFalse(controller.running)
        self.assertIs(controller.state, ExecutionState.COMPLETED_LOG_NOT_RECORDED)
        self.assertIn("injected write error", outcome.log_error)

    def test_background_started_write_error_is_refused_not_running(self):
        controller = self.controller()
        with self.world.patched(), failing_log_writes(1):
            controller.start(ARCHIVE_EXTRACTION, self.authority.issue(self.context, ARCHIVE_EXTRACTION))
            outcome = controller.wait(120)
        self.assertFalse(controller.running)
        self.assertIs(controller.state, ExecutionState.REFUSED)
        self.assertIn("nothing executed", outcome.detail)
        self.assertEqual(self.extractor.calls, 0)

    def test_background_unexpected_error_never_leaves_running(self):
        controller = self.controller()
        with mock.patch.object(controller, "execute", side_effect=RuntimeError("unexpected worker failure")):
            controller.start(ARCHIVE_EXTRACTION, self.authority.issue(self.context, ARCHIVE_EXTRACTION))
            outcome = controller.wait(30)
        self.assertFalse(controller.running)
        self.assertIs(controller.state, ExecutionState.FAILED)
        self.assertIn("unexpected worker failure", outcome.detail)

    def test_gui_shows_the_final_state_and_the_log_error(self):
        import material_identification_ui as ui
        import test_m8_d1_campaign_draft as d1

        from services import forward_solver, shape_extraction

        with self.world.patched(), mock.patch.object(ui, "AUTO_ID_REPO_ROOT", self.world.repo), \
                mock.patch.object(ui, "_draft_fixtures", return_value=None), \
                mock.patch("domain.experiment_fixture.fixture_roots_from_environment", return_value=self.world.roots), \
                mock.patch.object(forward_solver, "subprocess_executor", side_effect=lambda *a: self.solver), \
                mock.patch.object(shape_extraction, "pinned_script_executor", side_effect=lambda *a: self.extractor):
            application = d1.GuiTests.application(self)
            application.auto_id_execution_authority = self.authority  # test-only injection
            ui.open_guarded_execution(application, str(self.work))
            with failing_log_writes(2):
                ui.start_guarded_operation(application, ARCHIVE_EXTRACTION)
                application.auto_id_execution_controller.wait(120)
            ui.refresh_guarded_execution(application)
            text = application.material_auto_id_exec_label.kwargs["text"]
        self.assertIn("COMPLETED_ATTEMPT_LOG_NOT_RECORDED", text)
        self.assertIn("ATTEMPT LOG NOT RECORDED", text)
        self.assertIn("injected write error #2", text)


# ----------------------------------------------------------------------------- B. synthetic results never released

class SimulatedResultTests(_World):
    def evaluated(self):
        import material_identification_ui as ui
        from test_material_identification_ui import _ApplicationHarness

        journal = self.run_through()
        application = _ApplicationHarness()._application()
        with self.patches():
            ui.load_auto_id_source(application, "family", str(self.world.definition_path))
            ui.select_auto_id_run(application, str(journal))
            ui.evaluate_auto_id_run(application)
        return application, journal

    def patches(self):
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(stored_run_evidence, "campaign_specimens",
                                              return_value=tuple(self.world.items)))
        stack.enter_context(mock.patch("domain.experiment_fixture.fixture_roots_from_environment",
                                       return_value=self.context.roots))
        return stack

    def export(self, application):
        import material_identification_ui as ui

        target = self.tmp / "out" / "evidence.json"
        target.parent.mkdir()
        with self.patches():
            path = ui.export_auto_id_evidence(application, str(target))
        return path, target

    def assert_withheld(self, application, label):
        import material_identification_ui as ui

        view = ui.scientific_readiness_view(application)
        self.assertTrue(view["status"].startswith(label), view["status"])
        rows = dict(view["rows"])
        self.assertTrue(rows["Execution provenance"].startswith(label))
        self.assertTrue(all("not a material result" in value for name, value in view["rows"]
                            if name != "Execution provenance"))
        self.assertTrue(view["summary"][0].startswith(label))
        with mock.patch("services.calibration_material_preview.calibration_material_preview",
                        side_effect=AssertionError("Engineering Constants built for a blocked run")):
            preview = ui.calibration_preview_view(application)  # never even asked for constants
        self.assertNotEqual(preview["state"], "PREVIEW_AVAILABLE")
        self.assertEqual((preview["constants"], preview["fragment"]), ((), ""))
        self.assertEqual(ui.uncertainty_breakdown_view(application)[0][:2], ("Execution provenance", label))

    def test_simulated_result_is_labelled_withheld_and_never_exported(self):
        application, journal = self.evaluated()
        record = application.scientific_readiness_record
        evaluation = application.auto_id_active_typed[1]
        self.assertEqual(record, evaluation.readiness.to_dict())  # the backend record itself is unchanged
        self.assertEqual(record["status"], "MATERIAL_VALUES_RELEASED")  # the algorithm's own judgement (test only)
        self.assertIn(SIMULATED, application.auto_id_run_message)
        self.assertEqual(run_execution_provenance(journal)[0], ProvenanceState.SIMULATED)
        self.assertTrue((self.work / SIMULATED_MARKER).exists())
        self.assert_withheld(application, SIMULATED)
        path, target = self.export(application)
        self.assertIsNone(path)
        self.assertIn(f"No export: {ExportRefusalCode.SIMULATED.value}", application.auto_id_export_message)
        self.assertFalse(target.exists())

    def test_the_marker_alone_still_blocks_when_the_log_is_removed(self):
        application, journal = self.evaluated()
        (self.work / EXECUTION_LOG).unlink()
        self.assertEqual(run_execution_provenance(journal)[0], ProvenanceState.SIMULATED)
        self.assert_withheld(application, SIMULATED)
        self.assertIsNone(self.export(application)[0])

    def test_an_unreadable_log_blocks_presentation_and_export(self):
        application, journal = self.evaluated()
        (self.work / SIMULATED_MARKER).unlink()
        (self.work / EXECUTION_LOG).write_bytes(b"{")
        state, detail = run_execution_provenance(journal)
        self.assertIs(state, ProvenanceState.LOG_UNREADABLE)
        self.assert_withheld(application, "EXECUTION_LOG_UNREADABLE")
        path, _ = self.export(application)
        self.assertIsNone(path)
        self.assertIn(ExportRefusalCode.PROVENANCE_UNREADABLE.value, application.auto_id_export_message)

    def test_an_unlabelled_attempt_counts_as_simulated(self):
        application, journal = self.evaluated()
        (self.work / SIMULATED_MARKER).unlink()
        log = self.log()
        for attempt in log["attempts"]:
            attempt.pop("simulated")
        (self.work / EXECUTION_LOG).write_text(json.dumps(log), encoding="utf-8")
        self.assertIs(run_execution_provenance(journal)[0], ProvenanceState.SIMULATED)


class ArchivedRunRegressionTests(unittest.TestCase):
    """The archived M7 journals have no guarded record: presentation and export are exactly as before."""

    def setUp(self):
        from domain.experiment_fixture import fixture_roots_from_environment

        try:
            self.roots = dict(fixture_roots_from_environment())
        except Exception:  # noqa: BLE001
            self.roots = {}
        if not {"m7-run-a", "snadwich", "carbon-project-archive"} <= set(self.roots):
            self.skipTest("data stores m7-run-a / snadwich / carbon-project-archive not configured")
        self.out = Path(tempfile.mkdtemp(prefix="m8_d2i_archive_"))
        self.addCleanup(shutil.rmtree, self.out, ignore_errors=True)

    def test_run_a_is_no_guarded_record_and_exports_unchanged(self):
        import material_identification_ui as ui
        from test_material_identification_ui import _ApplicationHarness

        journal = next(Path(self.roots["m7-run-a"]).glob("campaign/*/journal.json"))
        state, detail = run_execution_provenance(journal)
        self.assertIs(state, ProvenanceState.NO_RECORD)
        self.assertIn("not evidence of a real origin", detail)
        before = journal.read_bytes()
        application = _ApplicationHarness()._application()
        ui.load_auto_id_source(application, "family", str(ROOT / "docs/auto_id/campaigns/M7_RUN_A.campaign.json"))
        ui.select_auto_id_run(application, str(journal))
        ui.evaluate_auto_id_run(application)
        view = ui.scientific_readiness_view(application)
        self.assertNotIn("Execution provenance", dict(view["rows"]))
        self.assertEqual(view["status"], "REFUSED")
        self.assertNotIn(SIMULATED, application.auto_id_run_message)
        path = ui.export_auto_id_evidence(application, str(self.out / "run_a.json"))
        self.assertIsNotNone(path, getattr(application, "auto_id_export_message", None))
        record = json.loads(Path(path).read_text(encoding="utf-8"))["scientific_evidence"]["backend_record"]
        self.assertEqual(record["material_formal_output"]["status"], "NO_GLOBAL_PARAMETER_VALUE")  # D-077 unchanged
        self.assertEqual(journal.read_bytes(), before)
        self.assertFalse((journal.parents[2] / EXECUTION_LOG).exists())


if __name__ == "__main__":
    unittest.main()
