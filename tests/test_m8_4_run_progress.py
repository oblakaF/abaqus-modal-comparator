"""M8.4 — read-only progress / resume-inspection of an explicitly selected stored run (no execution, no writes).

Synthetic runs use the M4.6 fake solver (``v12_i6_support``); incomplete / interrupted states are genuine journal
prefixes or self-consistent rewrites; the archived RUN_A / RUN_B journals are read store-gated.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.campaign_definition import load_campaign_definition, parse_campaign_definition  # noqa: E402
from domain.experiment_fixture import fixture_roots_from_environment  # noqa: E402
from domain.identification_run import canonical_hash  # noqa: E402
from services import stored_run_evidence as adapter  # noqa: E402
from services.identification_campaign_run import CampaignRun  # noqa: E402
from services.run_progress import ProgressState, inspect_run_progress  # noqa: E402
from test_m7_campaign import synthetic_specimen  # noqa: E402
from test_v12_i1_campaign_question import calibration_definition  # noqa: E402
from test_v12_i6_backend_integration import rechain  # noqa: E402
from v12_i6_support import calibration_run  # noqa: E402

CAMPAIGNS = ROOT / "docs" / "auto_id" / "campaigns"
RUN_A, RUN_B = CAMPAIGNS / "M7_RUN_A.campaign.json", CAMPAIGNS / "M7_RUN_B.campaign.json"
NOT_EVALUATED = "NOT_EVALUATED_FOR_SELECTION"


def _tree(path: Path) -> list[str]:
    return sorted(p.relative_to(path).as_posix() for p in Path(path).rglob("*"))


def _journal(run_root: Path) -> Path:
    found = list(Path(run_root).glob("campaign/*/journal.json"))
    assert len(found) == 1, found
    return found[0]


def _load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path: Path, document: dict) -> None:
    Path(path).write_text(json.dumps(document), encoding="utf-8")


class _Runs(unittest.TestCase):
    _directory = None

    @classmethod
    def setUpClass(cls):
        if _Runs._directory is not None:
            return
        _Runs._directory = tempfile.TemporaryDirectory()
        tmp = Path(_Runs._directory.name)

        def run(name, data=None):
            definition = parse_campaign_definition(data or calibration_definition())
            item, store = synthetic_specimen(definition, "A", tmp / name / "data")
            return calibration_run(tmp / name, definition=definition, item=item), store

        _Runs.base, _Runs.store = run("base")
        data = calibration_definition()
        data["lm"]["max_iterations"] = 1
        _Runs.max_iterations, _ = run("max_iterations", data)
        data = calibration_definition()
        data["lm"]["evaluation_budget"] = 3
        _Runs.budget, _ = run("budget", data)
        data = calibration_definition()
        data["sigma"]["setup"]["sd_ln"] = 0.2
        _Runs.imprecise, _Runs.imprecise_store = run("imprecise", data)
        _Runs.tmp = tmp

    def copy_run(self, run) -> Path:
        target = Path(tempfile.mkdtemp(prefix="m8_4_run_"))
        self.addCleanup(shutil.rmtree, target, ignore_errors=True)
        shutil.copytree(run.campaign.run_dir.parent.parent, target / "runs")
        return target / "runs"

    def inspect(self, journal, run=None, specimens="default", definition=None):
        run = run or self.base
        return inspect_run_progress(definition or run.definition, journal,
                                    [run.item] if specimens == "default" else specimens)

    @staticmethod
    def rows(progress) -> dict:
        return dict(progress.rows)

    def assert_not_verified(self, progress, reason):
        self.assertIs(progress.state, ProgressState.JOURNAL_NOT_VERIFIED)
        self.assertFalse(progress.verified)
        rows = self.rows(progress)
        self.assertIn(reason, rows["Journal verification"])
        self.assertTrue(rows["Journal verification"].startswith("NOT VERIFIED"))
        for counted in ("Campaign evaluations journalled", "LM result", "Authorised budgets", "Run hash"):
            self.assertNotIn(counted, rows)  # unverified evidence never appears as progress


def tearDownModule():
    if _Runs._directory is not None:
        _Runs._directory.cleanup()
        _Runs._directory = None


# ----------------------------------------------------------------------------- derivation from the journals

class ProgressDerivationTests(_Runs):
    def test_converged_run_counts_come_from_the_verified_journals(self):
        run = self.base
        progress = self.inspect(_journal(run.campaign.run_dir.parent.parent))
        self.assertIs(progress.state, ProgressState.RESULT_RECORDED)
        rows = self.rows(progress)
        result = run.campaign.journal.records("result")[0]
        evaluations = run.campaign.journal.records("evaluation")
        self.assertEqual(rows["Run hash"], run.campaign.run_hash)
        self.assertIn("governed run identity verified field by field", rows["Journal verification"])
        self.assertEqual(rows["Campaign evaluations journalled"], f"{len(evaluations)} (0 refused)")
        self.assertEqual(rows["LM result"], f"CONVERGED; iterations {result['iterations']}; LM evaluations "
                                            f"{result['lm_evaluations']}; Abaqus solves used "
                                            f"{result['abaqus_solves_used']}")
        self.assertEqual(rows["Authorised budgets"], f"Abaqus solves {run.definition.abaqus_solve_budget}; LM "
                                                     f"evaluations {run.definition.lm.evaluation_budget} (run identity)")
        counts = run.campaign.pipelines["A"].counts()
        self.assertIn(f"{counts['identification_evaluations_journalled']} evaluation(s) journalled", rows["Specimen A"])
        self.assertIn(f"Abaqus solves recorded {counts['abaqus_solves_executed_total']}", rows["Specimen A"])
        self.assertIn("a converged LM result is not a release", rows["Scientific evaluation"])
        self.assertEqual(rows["Incomplete or missing evidence"], "none found by this inspection")
        self.assertTrue(rows["Execution"].startswith("NOT_AUTHORISED"))
        self.assertIn("production calibration execution BLOCKED / NOT_AUTHORISED", rows["Execution"])
        values = json.dumps([value for _, value in progress.rows])
        for invented in ("%", "remaining", "ETA", "completed", "in progress", "RUNNING"):
            self.assertNotIn(invented, values)  # no percentage, remaining time, live state or completion

    def test_genuine_max_iterations_and_solve_budget(self):
        for run, status in ((self.max_iterations, "MAX_ITERATIONS"), (self.budget, "SOLVE_BUDGET")):
            with self.subTest(status=status):
                self.assertEqual(run.summary["status"], status)
                progress = self.inspect(_journal(run.campaign.run_dir.parent.parent), run)
                rows = self.rows(progress)
                self.assertTrue(rows["LM result"].startswith(status))
                self.assertIn("would refuse it: no single CONVERGED LM result", rows["Scientific evaluation"])

    def test_recorded_refused_and_step_rejected_results(self):
        for status, refusal in (("REFUSED", "TRACKING_LOST: mode 9"), ("STEP_REJECTED", None)):
            with self.subTest(status=status):
                root = self.copy_run(self.base)
                journal = _journal(root)
                _write(journal, rechain(_load(journal), edit=lambda kind, r: dict(r, status=status, refusal=refusal)
                                        if kind == "result" else r))
                rows = self.rows(self.inspect(journal))
                self.assertTrue(rows["LM result"].startswith(status))
                if refusal:
                    self.assertEqual(rows["Recorded refusal / stop"], refusal)
                self.assertIn("would refuse it", rows["Scientific evaluation"])

    def test_no_result_is_not_a_running_process(self):
        root = self.copy_run(self.base)
        journal = _journal(root)
        document = _load(journal)
        _write(journal, dict(document, entries=document["entries"][:-1]))  # a genuine interrupted prefix
        progress = self.inspect(journal)
        self.assertIs(progress.state, ProgressState.NO_RESULT_RECORDED)
        self.assertIn("does not mean a process is running", self.rows(progress)["LM result"])
        self.assertNotIn("RUNNING", {state.value for state in ProgressState})  # no live state exists

    def test_multiple_journalled_results(self):
        root = self.copy_run(self.base)
        journal = _journal(root)
        document = _load(journal)
        result = copy.deepcopy(document["entries"][-1])
        _write(journal, rechain(dict(document, entries=document["entries"] + [result])))
        progress = self.inspect(journal)
        self.assertIs(progress.state, ProgressState.MULTIPLE_RESULTS_RECORDED)
        self.assertIn("2 journalled LM results", self.rows(progress)["Incomplete or missing evidence"])
        self.assertIn("would refuse it", self.rows(progress)["Scientific evaluation"])

    def test_incomplete_pipeline_journal_and_missing_specimen_inputs(self):
        root = self.copy_run(self.base)
        for pipeline in root.glob("specimens/*/*/*/journal.json"):
            pipeline.unlink()
        rows = self.rows(self.inspect(_journal(root)))
        self.assertIn("pipeline journal NOT VERIFIED", rows["Specimen A"])
        self.assertIn("A: pipeline journal not verified", rows["Incomplete or missing evidence"])
        unknown = inspect_run_progress(self.base.definition, _journal(root), None, "stores not configured")
        rows = self.rows(unknown)
        self.assertIn("specimen identities NOT verified", rows["Journal verification"])
        self.assertIn("not inspected", rows["Specimen pipelines"])


# ----------------------------------------------------------------------------- fail closed

class FailClosedTests(_Runs):
    def test_no_campaign_or_no_run(self):
        self.assertIs(inspect_run_progress(None, _journal(self.base.campaign.run_dir.parent.parent)).state,
                      ProgressState.NOT_SELECTED)
        self.assertIs(inspect_run_progress(self.base.definition, None).state, ProgressState.NOT_SELECTED)

    def test_missing_invalid_wrong_schema_broken_chain(self):
        root = self.copy_run(self.base)
        journal = _journal(root)
        original = _load(journal)
        self.assert_not_verified(self.inspect(root / "campaign" / "absent" / "journal.json"), "cannot be read")
        journal.write_text("{invalid", encoding="utf-8")
        self.assert_not_verified(self.inspect(journal), "cannot be read")
        _write(journal, dict(original, schema="another/schema"))
        self.assert_not_verified(self.inspect(journal), "not an identification journal")
        broken = copy.deepcopy(original)
        broken["entries"][1]["record"]["residuals"] = [0.0]
        _write(journal, broken)
        self.assert_not_verified(self.inspect(journal), "hash chain is broken")
        _write(journal, original)
        self.assertTrue(self.inspect(journal).verified)

    def test_wrong_campaign_and_wrong_run_identity(self):
        journal = _journal(self.base.campaign.run_dir.parent.parent)
        self.assert_not_verified(self.inspect(journal, definition=load_campaign_definition(RUN_A)),
                                 "the run belongs to campaign hash")
        root = self.copy_run(self.base)
        original = _journal(root)
        document = _load(original)
        identity = dict(document["run_identity"], abaqus_solve_budget=99)  # same campaign hash, another run identity
        forged = rechain(document, identity=identity)
        target = root / "campaign" / forged["run_hash"] / "journal.json"
        target.parent.mkdir()
        _write(target, forged)
        self.assert_not_verified(self.inspect(target), "abaqus_solve_budget")
        _write(original, dict(document, run_hash=forged["run_hash"]))  # directory != run hash
        self.assert_not_verified(self.inspect(original), "is not <run root>/campaign/<run hash>/journal.json")


# ----------------------------------------------------------------------------- GUI

class _Gui(_Runs):
    def application(self):
        from test_material_identification_ui import _ApplicationHarness

        return _ApplicationHarness()._application()

    def definition_file(self, definition) -> Path:
        folder = Path(tempfile.mkdtemp(prefix="m8_4_def_"))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        path = folder / "synthetic.campaign.json"
        path.write_text(json.dumps(definition.canonical), encoding="utf-8")
        return path

    def patched(self, item=None):
        return (mock.patch.object(adapter, "campaign_specimens", return_value=(item or self.base.item,)),
                mock.patch("domain.experiment_fixture.fixture_roots_from_environment",
                           return_value={"synthetic": self.store}))

    def call(self, function, application, *args, item=None):
        first, second = self.patched(item)
        with first, second:
            function(application, *args)

    @staticmethod
    def progress_rows(application) -> dict:
        return dict(application.material_auto_id_progress_table.items.values())

    @staticmethod
    def progress_state(application) -> str:
        return application.material_auto_id_progress_label.kwargs["text"]

    @staticmethod
    def readiness(application) -> str:
        return application.material_scientific_readiness_status_label.kwargs["text"]

    def selected(self, run_root):
        import material_identification_ui as ui

        application = self.application()
        ui.load_auto_id_source(application, "family", str(self.definition_file(self.base.definition)))
        self.call(ui.select_auto_id_run, application, str(_journal(run_root)))
        return application


class GuiProgressTests(_Gui):
    def test_page_has_refresh_and_reopen_and_an_explicit_empty_state(self):
        application = self.application()
        page = application.material_identification_pages["0. Auto-ID Setup"]
        texts = []

        def walk(widget):
            texts.append(widget.kwargs.get("text"))
            for child in widget.children:
                walk(child)

        walk(page)
        self.assertIn("Refresh run progress", texts)
        self.assertIn("Reopen selected run", texts)
        self.assertEqual(self.progress_state(application), "NOT_SELECTED")
        self.assertEqual(self.progress_rows(application), {})

    def test_selecting_a_run_verifies_and_shows_its_progress(self):
        application = self.selected(self.base.campaign.run_dir.parent.parent)
        self.assertEqual(self.progress_state(application), "RESULT_RECORDED")
        self.assertTrue(self.progress_rows(application)["LM result"].startswith("CONVERGED"))
        self.assertEqual(self.readiness(application), NOT_EVALUATED)  # progress never evaluates

    def test_refresh_reads_fresh_data_and_never_evaluates(self):
        import material_identification_ui as ui

        root = self.copy_run(self.base)
        journal = _journal(root)
        full = _load(journal)
        _write(journal, dict(full, entries=full["entries"][:-1]))  # interrupted: no result yet
        application = self.selected(root)
        self.assertEqual(self.progress_state(application), "NO_RESULT_RECORDED")
        _write(journal, full)  # the journal grew on disk
        with mock.patch.object(adapter, "judge_campaign_run") as judge:
            self.call(ui.refresh_auto_id_progress, application)
        judge.assert_not_called()
        self.assertEqual(self.progress_state(application), "RESULT_RECORDED")
        self.assertEqual(self.readiness(application), NOT_EVALUATED)
        journal.write_text("{", encoding="utf-8")  # corrupted on disk: no stale progress
        self.call(ui.refresh_auto_id_progress, application)
        self.assertEqual(self.progress_state(application), "JOURNAL_NOT_VERIFIED")
        self.assertNotIn("LM result", self.progress_rows(application))

    def test_a_changed_journal_invalidates_the_active_evaluation(self):
        import material_identification_ui as ui

        root = self.copy_run(self.base)
        journal = _journal(root)
        application = self.selected(root)
        self.call(ui.evaluate_auto_id_run, application)
        self.assertEqual(self.readiness(application), "RELEASED")
        self.call(ui.refresh_auto_id_progress, application)  # unchanged journal: the evaluation stays current
        self.assertEqual(self.readiness(application), "RELEASED")
        document = _load(journal)
        _write(journal, rechain(dict(document, entries=document["entries"] + [copy.deepcopy(document["entries"][-1])])))
        record = application.scientific_readiness_record
        self.call(ui.refresh_auto_id_progress, application)
        self.assertEqual(self.readiness(application), NOT_EVALUATED)
        self.assertEqual(self.progress_state(application), "MULTIPLE_RESULTS_RECORDED")
        self.assertIs(application.scientific_readiness_record, record)  # kept, not current

    def test_reopen_reverifies_the_same_selection_and_resets_the_evaluation(self):
        import material_identification_ui as ui

        application = self.selected(self.base.campaign.run_dir.parent.parent)
        self.call(ui.evaluate_auto_id_run, application)
        self.assertEqual(self.readiness(application), "RELEASED")
        self.call(ui.reopen_auto_id_run, application)
        self.assertEqual(self.progress_state(application), "RESULT_RECORDED")
        self.assertEqual(self.readiness(application), NOT_EVALUATED)  # inspection, not a new evaluation
        application = self.application()
        ui.reopen_auto_id_run(application)
        self.assertIn("Nothing to reopen", application.material_auto_id_run_label.kwargs["text"])

    def test_switching_runs_or_campaigns_clears_progress(self):
        import material_identification_ui as ui

        application = self.selected(self.base.campaign.run_dir.parent.parent)
        self.assertEqual(self.progress_state(application), "RESULT_RECORDED")
        self.call(ui.select_auto_id_run, application, str(_journal(self.max_iterations.campaign.run_dir.parent.parent)),
                  item=self.max_iterations.item)
        self.assertEqual(self.progress_state(application), "JOURNAL_NOT_VERIFIED")  # another campaign's run
        self.assertNotIn("LM result", self.progress_rows(application))
        self.assertEqual(self.readiness(application), NOT_EVALUATED)
        ui.load_auto_id_source(application, "family", str(RUN_A))
        self.assertEqual(self.progress_state(application), "NOT_SELECTED")
        self.assertEqual(self.progress_rows(application), {})
        ui.load_auto_id_source(application, "specimen", str(self.tmp / "absent"))
        self.call(ui.refresh_auto_id_progress, application)
        self.assertIn("no governed campaign", self.progress_rows(application)["Progress"])

    def test_no_execution_subprocess_or_writes(self):
        import material_identification_ui as ui
        from services import identification_campaign_run as campaign_module
        from services import identification_step, shape_extraction

        refuse = mock.Mock(side_effect=AssertionError("forbidden call"))
        root = self.copy_run(self.base)
        before, before_docs = _tree(root), _tree(ROOT / "docs" / "auto_id")
        with mock.patch.object(subprocess, "Popen", refuse), mock.patch.object(subprocess, "run", refuse), \
                mock.patch.object(os, "system", refuse), \
                mock.patch.object(identification_step, "run_bounded_lm", refuse), \
                mock.patch.object(campaign_module, "run_bounded_lm", refuse), \
                mock.patch.object(campaign_module, "prepare_run_manifest", refuse), \
                mock.patch.object(campaign_module, "extract_archived_odbs", refuse), \
                mock.patch.object(shape_extraction, "extract_shape_pack", refuse), \
                mock.patch.object(CampaignRun, "__init__", refuse), mock.patch.object(CampaignRun, "run", refuse), \
                mock.patch.object(CampaignRun, "evaluate", refuse):
            application = self.selected(root)
            self.call(ui.refresh_auto_id_progress, application)
            self.call(ui.reopen_auto_id_run, application)
        refuse.assert_not_called()
        self.assertEqual(_tree(root), before)
        self.assertEqual(_tree(ROOT / "docs" / "auto_id"), before_docs)
        source = (ROOT / "src" / "services" / "run_progress.py").read_text(encoding="utf-8")
        for name in ("RunJournal(", "CampaignRun(", "run_bounded_lm", "write_text", "mkdir", "subprocess"):
            self.assertNotIn(name, source)


class PipelineFreshnessTests(_Gui):
    """The freshness identity covers the campaign journal and every governed pipeline journal (M8.4 correction)."""

    def evaluated_copy(self, run=None):
        import material_identification_ui as ui

        run = run or self.base
        root = self.copy_run(run)
        application = self.application()
        ui.load_auto_id_source(application, "family", str(self.definition_file(run.definition)))
        roots = {"synthetic": self.imprecise_store if run is self.imprecise else self.store}
        with mock.patch.object(adapter, "campaign_specimens", return_value=(run.item,)), \
                mock.patch("domain.experiment_fixture.fixture_roots_from_environment", return_value=roots):
            ui.select_auto_id_run(application, str(_journal(root)))
            ui.evaluate_auto_id_run(application)
        return application, root, roots

    def refresh(self, application, run=None, roots=None):
        import material_identification_ui as ui

        with mock.patch.object(adapter, "campaign_specimens", return_value=((run or self.base).item,)), \
                mock.patch("domain.experiment_fixture.fixture_roots_from_environment",
                           return_value=roots or {"synthetic": self.store}):
            ui.refresh_auto_id_progress(application)

    def assert_invalidated(self, application, record, snapshot):
        self.assertEqual(self.readiness(application), NOT_EVALUATED)
        scientific = json.dumps(tuple(application.material_scientific_readiness_table.items.values()))
        for stale in ("RELEASED", "E_in_plane_mpa", "SYA/fake"):
            self.assertNotIn(stale, scientific)
        self.assertIs(application.scientific_readiness_record, record)
        self.assertEqual(json.dumps(record, sort_keys=True), snapshot)

    @staticmethod
    def pipeline_journal(root: Path) -> Path:
        found = list(root.glob("specimens/*/*/*/journal.json"))
        assert len(found) == 1, found
        return found[0]

    def released(self):
        application, root, _ = self.evaluated_copy()
        self.assertEqual(self.readiness(application), "RELEASED")
        record = application.scientific_readiness_record
        return application, root, record, json.dumps(record, sort_keys=True)

    @staticmethod
    def appended(journal: Path) -> None:
        document = _load(journal)
        _write(journal, rechain(dict(document, entries=document["entries"] + [copy.deepcopy(document["entries"][-1])])))

    def test_a_deleted_pipeline_journal_invalidates_the_evaluation(self):
        application, root, record, snapshot = self.released()
        self.pipeline_journal(root).unlink()  # the campaign journal is unchanged
        self.refresh(application)
        self.assertIn("pipeline journal NOT VERIFIED", self.progress_rows(application)["Specimen A"])
        self.assert_invalidated(application, record, snapshot)

    def test_b_a_broken_pipeline_hash_chain_invalidates_the_evaluation(self):
        application, root, record, snapshot = self.released()
        journal = self.pipeline_journal(root)
        document = _load(journal)
        document["entries"][1]["record"]["job_name"] = "TAMPERED"
        _write(journal, document)
        self.refresh(application)
        self.assertIn("pipeline journal NOT VERIFIED", self.progress_rows(application)["Specimen A"])
        self.assert_invalidated(application, record, snapshot)

    def test_c_a_genuine_pipeline_append_makes_the_evaluation_non_current(self):
        application, root, record, snapshot = self.released()
        self.appended(self.pipeline_journal(root))  # valid chain, same governed identity; campaign unchanged
        self.refresh(application)
        self.assertEqual(self.progress_state(application), "RESULT_RECORDED")  # still verified evidence ...
        self.assertNotIn("NOT VERIFIED", self.progress_rows(application)["Specimen A"])
        self.assert_invalidated(application, record, snapshot)  # ... but not the evidence that was evaluated

    def test_d_unchanged_journals_keep_the_evaluation_current(self):
        application, root, record, _ = self.released()
        self.refresh(application)
        self.refresh(application)
        self.assertEqual(self.readiness(application), "RELEASED")
        self.assertIs(application.scientific_readiness_record, record)

    def test_e_genuine_refused_and_not_ready_results_remain_displayable(self):
        import material_identification_ui as ui

        application, root, roots = self.evaluated_copy(self.imprecise)
        self.assertEqual(self.readiness(application), "REFUSED")
        self.refresh(application, self.imprecise, roots)  # unchanged verified evidence: still current
        self.assertEqual(self.readiness(application), "REFUSED")
        root = self.copy_run(self.base)
        self.pipeline_journal(root).unlink()
        application = self.application()
        ui.load_auto_id_source(application, "family", str(self.definition_file(self.base.definition)))
        self.call(ui.select_auto_id_run, application, str(_journal(root)))
        self.call(ui.evaluate_auto_id_run, application)
        self.assertEqual(self.readiness(application), "NOT_READY")  # the genuine backend refusal is shown
        self.assertIn("LM_HISTORY_MISSING",
                      dict(application.material_scientific_readiness_table.items.values())["Refusal reasons"])
        self.refresh(application)  # incomplete evidence never compares equal: a refresh does not keep it current
        self.assertEqual(self.readiness(application), NOT_EVALUATED)

    def test_f_a_new_explicit_evaluation_returns_the_current_backend_result(self):
        import material_identification_ui as ui

        application, root, record, _ = self.released()
        journal = self.pipeline_journal(root)
        self.appended(journal)
        self.refresh(application)
        self.assertEqual(self.readiness(application), NOT_EVALUATED)
        self.call(ui.evaluate_auto_id_run, application)
        # The genuine current backend answer on the changed evidence (here a refusal: the appended copy duplicates a
        # journalled evaluation), exactly as the backend returns it for the same files
        direct = adapter.evaluate_stored_run(self.base.definition, _journal(root), ROOT, {"synthetic": self.store},
                                             [self.base.item]).readiness.to_dict()
        self.assertEqual(application.scientific_readiness_record, direct)
        self.assertIsNot(application.scientific_readiness_record, record)
        self.assertEqual(self.readiness(application), direct["status"])
        self.assertEqual(direct["status"], "NOT_READY")
        self.refresh(application)  # recorded with the same freshness semantics: still current
        self.assertEqual(self.readiness(application), direct["status"])
        journal.unlink()
        self.call(ui.evaluate_auto_id_run, application)
        self.assertEqual(self.readiness(application), "NOT_READY")
        self.assertIn("LM_HISTORY_MISSING",
                      dict(application.material_scientific_readiness_table.items.values())["Refusal reasons"])

    def test_h_reopen_and_switching_still_reset(self):
        import material_identification_ui as ui

        application, root, record, snapshot = self.released()
        self.call(ui.reopen_auto_id_run, application)
        self.assert_invalidated(application, record, snapshot)
        ui.load_auto_id_source(application, "family", str(RUN_A))
        self.assertEqual(self.progress_state(application), "NOT_SELECTED")
        self.assert_invalidated(application, record, snapshot)


class RealTkProgressTests(_Gui):
    def test_real_gui_progress(self):
        try:
            import tkinter as tk

            root = tk.Tk()
        except Exception as error:  # noqa: BLE001
            self.skipTest(f"Tk is unavailable: {error}")
        self.addCleanup(root.destroy)
        root.withdraw()
        import main
        import material_identification_ui as ui
        import ui_workflow

        disabled = {"autosave_enabled": False, "restore_on_startup": False, "show_recovery_notice": False}
        with mock.patch.object(ui_workflow, "load_recovery_preferences", return_value=disabled), \
                mock.patch.object(ui_workflow, "discover_abaqus_installations", return_value=()):
            application = main.app.ModalComparatorApp(root)
        ui.load_auto_id_source(application, "family", str(self.definition_file(self.base.definition)))
        self.call(ui.select_auto_id_run, application, str(_journal(self.base.campaign.run_dir.parent.parent)))
        root.update_idletasks()
        self.assertEqual(application.material_auto_id_progress_label.cget("text"), "RESULT_RECORDED")
        self.assertTrue(application.material_auto_id_progress_table.get_children())
        ui.load_auto_id_source(application, "family", str(RUN_A))
        root.update_idletasks()
        self.assertEqual(application.material_auto_id_progress_label.cget("text"), "NOT_SELECTED")
        self.assertEqual(application.material_auto_id_progress_table.get_children(), ())


# ----------------------------------------------------------------------------- archived RUN_A / RUN_B (store-gated)

class ArchivedProgressTests(unittest.TestCase):
    def setUp(self):
        self.roots = fixture_roots_from_environment()
        if not {"m7-run-a", "m7-run-b", "snadwich", "carbon-project-archive"} <= set(self.roots):
            self.skipTest("data stores m7-run-a / m7-run-b / snadwich / carbon-project-archive not configured")

    def test_run_a_and_run_b_progress_and_switching(self):
        from test_material_identification_ui import _ApplicationHarness
        import material_identification_ui as ui

        application = _ApplicationHarness()._application()
        for campaign, store, evaluations in ((RUN_A, "m7-run-a", 4), (RUN_B, "m7-run-b", 8)):
            with self.subTest(campaign=campaign.name):
                journal = _journal(Path(self.roots[store]))
                before = _tree(Path(self.roots[store]))
                ui.load_auto_id_source(application, "family", str(campaign))
                self.assertEqual(application.material_auto_id_progress_label.kwargs["text"], "NOT_SELECTED")
                ui.select_auto_id_run(application, str(journal))
                rows = dict(application.material_auto_id_progress_table.items.values())
                accepted = _load(CAMPAIGNS / f"{campaign.name.split('.')[0]}.result.json")
                self.assertEqual(application.material_auto_id_progress_label.kwargs["text"], "RESULT_RECORDED")
                self.assertEqual(rows["Run hash"], accepted["run_hash"])
                self.assertIn("governed run identity verified field by field", rows["Journal verification"])
                self.assertEqual(rows["Campaign evaluations journalled"], f"{evaluations} (0 refused)")
                lm = accepted["lm_result"]
                self.assertEqual(rows["LM result"], f"CONVERGED; iterations {lm['iterations']}; LM evaluations "
                                                    f"{lm['lm_evaluations']}; Abaqus solves used "
                                                    f"{accepted['abaqus_solves_used']}")
                specimens = [k for k in rows if k.startswith("Specimen ")]
                self.assertEqual(len(specimens), 2)
                self.assertTrue(all("pipeline " in rows[k] and "NOT VERIFIED" not in rows[k] for k in specimens))
                self.assertIn("a converged LM result is not a release", rows["Scientific evaluation"])
                self.assertEqual(application.material_scientific_readiness_status_label.kwargs["text"], NOT_EVALUATED)
                from services.run_progress import run_evidence_fingerprint

                specimens = application.auto_id_specimens[1]  # the governed inputs prepared for this selection
                fingerprint = run_evidence_fingerprint(application.auto_id_preparation.definition, journal, specimens)
                self.assertIsNotNone(fingerprint)  # campaign + both governed pipeline journals verified
                self.assertEqual(fingerprint, application.auto_id_progress.fingerprint)
                self.assertEqual(run_evidence_fingerprint(application.auto_id_preparation.definition, journal,
                                                          specimens), fingerprint)  # stable on unchanged evidence
                self.assertEqual(_tree(Path(self.roots[store])), before)  # read-only


if __name__ == "__main__":
    unittest.main()
