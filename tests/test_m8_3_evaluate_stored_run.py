"""M8.3 — one Auto-ID action: "Auto-ID — Evaluate Stored Run" (read-only; the shared V12-I6 backend judges).

The GUI owns selection and presentation; ``services.stored_run_evidence`` reads an explicitly selected, already
journalled run in the accepted journal layout and calls ``judge_campaign_run``; the backend owns every decision.
Synthetic runs use the M4.6 fake solver (``v12_i6_support``); the archived RUN_A / RUN_B runs are read store-gated.
Nothing is solved, extracted, planned or written.
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

from domain.campaign_definition import (  # noqa: E402
    CalibrationNotImplementedRefusal,
    load_campaign_definition,
    parse_campaign_definition,
)
from domain.experiment_fixture import fixture_roots_from_environment  # noqa: E402
from domain.identification_run import canonical_hash  # noqa: E402
from services import stored_run_evidence as adapter  # noqa: E402
from services.identification_campaign_run import CampaignRun, CampaignRunConfig  # noqa: E402
from services.stored_run_evidence import (  # noqa: E402
    StoredRunRefusal,
    StoredRunRefusalCode,
    evaluate_stored_run,
    select_stored_run,
)
from test_m7_campaign import synthetic_specimen  # noqa: E402
from test_v12_i1_campaign_question import calibration_definition  # noqa: E402
from v12_i6_support import calibration_run  # noqa: E402

CAMPAIGNS = ROOT / "docs" / "auto_id" / "campaigns"
SPECIMENS = ROOT / "docs" / "auto_id" / "specimens"
RUN_A, RUN_B = CAMPAIGNS / "M7_RUN_A.campaign.json", CAMPAIGNS / "M7_RUN_B.campaign.json"
EVALUATE = "Auto-ID — Evaluate Stored Run"
NOT_EVALUATED = "NOT_EVALUATED_FOR_SELECTION"


def _tree(path: Path) -> list[str]:
    return sorted(p.relative_to(path).as_posix() for p in Path(path).rglob("*"))


def _journal(run_root: Path) -> Path:
    found = list(Path(run_root).glob("campaign/*/journal.json"))
    assert len(found) == 1, found
    return found[0]


class _Synthetic(unittest.TestCase):
    """Genuine synthetic journalled runs of one calibration campaign (fake solver), built once."""

    _directory = None
    runs: dict = {}

    @classmethod
    def setUpClass(cls):
        if _Synthetic._directory is not None:
            return
        _Synthetic._directory = tempfile.TemporaryDirectory()
        tmp = Path(_Synthetic._directory.name)
        definition = parse_campaign_definition(calibration_definition())
        # synthetic_specimen is deterministic: each run gets an identical specimen input and store of its own
        item, store = synthetic_specimen(definition, "A", tmp / "first" / "data")
        second, _ = synthetic_specimen(definition, "A", tmp / "second" / "data")
        runs = {"first": calibration_run(tmp / "first", definition=definition, item=item),
                "second": calibration_run(tmp / "second", definition=definition, item=second,
                                          manifest_hash="n" * 64)}
        data = calibration_definition()
        data["sigma"]["setup"]["sd_ln"] = 0.2
        imprecise = parse_campaign_definition(data)
        item_b, _ = synthetic_specimen(imprecise, "A", tmp / "imprecise" / "data")
        runs["imprecise"] = calibration_run(tmp / "imprecise", definition=imprecise, item=item_b)
        _Synthetic.runs.update(runs)
        _Synthetic.definition, _Synthetic.item, _Synthetic.store = definition, item, store
        _Synthetic.tmp = tmp

    def run_root(self, name="first") -> Path:
        return self.tmp / name / "runs"

    def roots(self) -> dict:
        return {"synthetic": self.store}

    def copy_run(self, name="first") -> Path:
        target = Path(tempfile.mkdtemp(prefix="m8_3_run_"))
        self.addCleanup(shutil.rmtree, target, ignore_errors=True)
        shutil.copytree(self.run_root(name), target / "runs")
        return target / "runs"

    def evaluate(self, journal, definition=None, item=None, roots=None):
        run = self.runs.get("imprecise") if definition is not None and definition is self.runs["imprecise"].definition \
            else None
        specimens = [item or (run.item if run else self.item)]
        return evaluate_stored_run(definition or self.definition, journal, ROOT, self.roots() if roots is None else roots,
                                   specimens)


def tearDownModule():
    if _Synthetic._directory is not None:
        _Synthetic._directory.cleanup()
        _Synthetic._directory = None


# ----------------------------------------------------------------------------- the adapter (no GUI)

class AdapterTests(_Synthetic):
    def test_a_genuine_stored_run_is_judged_by_the_shared_backend(self):
        journal = _journal(self.run_root())
        with mock.patch.object(adapter, "judge_campaign_run", wraps=adapter.judge_campaign_run) as judge:
            evaluation = self.evaluate(journal)
        judge.assert_called_once()
        record = evaluation.readiness.to_dict()
        self.assertEqual(record["status"], "RELEASED")
        self.assertEqual(evaluation.run.run_hash, self.runs["first"].campaign.run_hash)
        self.assertEqual(record["campaign"]["run_hash"], evaluation.run.run_hash)
        self.assertEqual(evaluation.notes, ())
        # The very record the backend returns for the very same evidence: nothing is altered on the way
        direct = adapter.judge_campaign_run(self.definition, [self.item], self.runs["first"].evidence).to_dict()
        self.assertEqual(record, direct)

    def test_selection_refusals_never_reach_the_backend(self):
        broken = self.copy_run()
        unreadable = _journal(broken)
        unreadable.write_text("{broken", encoding="utf-8")
        loose = Path(tempfile.mkdtemp(prefix="m8_3_loose_"))
        self.addCleanup(shutil.rmtree, loose, ignore_errors=True)
        shutil.copyfile(_journal(self.run_root()), loose / "journal.json")
        pipeline = next(self.run_root().glob("specimens/*/*/*/journal.json"))
        cases = {
            StoredRunRefusalCode.NO_RUN: (self.definition, None),
            StoredRunRefusalCode.NO_CAMPAIGN: (None, _journal(self.run_root())),
            StoredRunRefusalCode.UNREADABLE_JOURNAL: (self.definition, unreadable),
            StoredRunRefusalCode.NOT_A_CAMPAIGN_RUN: (self.definition, loose / "journal.json"),
            StoredRunRefusalCode.RUN_CAMPAIGN_MISMATCH: (load_campaign_definition(RUN_A), _journal(self.run_root())),
        }
        with mock.patch.object(adapter, "judge_campaign_run") as judge:
            for code, (definition, journal) in cases.items():
                with self.subTest(code=code.value):
                    with self.assertRaises(StoredRunRefusal) as refused:
                        evaluate_stored_run(definition, journal, ROOT, self.roots(), [self.item])
                    self.assertIs(refused.exception.code, code)
            with self.assertRaises(StoredRunRefusal) as refused:  # a pipeline journal is not a campaign run
                select_stored_run(pipeline)
            self.assertIs(refused.exception.code, StoredRunRefusalCode.NOT_A_CAMPAIGN_RUN)
        judge.assert_not_called()

    def test_pipeline_journals_are_located_by_governed_identity_only(self):
        run = self.runs["first"]
        entry = run.evidence.campaign_journal["run_identity"]["specimens"][0]
        governed = canonical_hash(adapter.governed_pipeline_identity(self.definition, self.item,
                                                                     run.campaign.run_hash, entry["archived_packs"]))
        self.assertEqual(governed, run.evidence.pipeline_journals["A"]["run_hash"])
        # A decoy (the genuine pipeline of another run of this campaign) placed first next to it is never picked up
        root = self.copy_run()
        genuine = next(root.glob("specimens/*/*/*"))
        decoy = next(self.run_root("second").glob("specimens/*/*/*"))
        self.assertNotEqual(decoy.name, genuine.name)
        shutil.copytree(decoy, genuine.parent / ("0" * 64))
        evaluation = self.evaluate(_journal(root))
        self.assertEqual(evaluation.readiness.to_dict()["status"], "RELEASED")


# ----------------------------------------------------------------------------- the GUI action

class _Gui(_Synthetic):
    def application(self):
        from test_material_identification_ui import _ApplicationHarness

        return _ApplicationHarness()._application()

    def definition_file(self, definition=None, name="synthetic.campaign.json") -> Path:
        definition = definition or self.definition
        folder = Path(tempfile.mkdtemp(prefix="m8_3_def_"))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        path = folder / name
        path.write_text(json.dumps(definition.canonical), encoding="utf-8")
        return path

    def select(self, application, kind, path):
        import material_identification_ui as ui

        ui.load_auto_id_source(application, kind, str(path))

    def evaluate_run(self, application, journal, roots=None, item=None):
        import material_identification_ui as ui

        ui.select_auto_id_run(application, str(journal))
        with mock.patch.object(adapter, "campaign_specimens", return_value=(item or self.item,)), \
                mock.patch("domain.experiment_fixture.fixture_roots_from_environment",
                           return_value=self.roots() if roots is None else roots):
            ui.evaluate_auto_id_run(application)

    @staticmethod
    def rows(application) -> dict:
        return dict(application.material_scientific_readiness_table.items.values())

    @staticmethod
    def status(application) -> str:
        return application.material_scientific_readiness_status_label.kwargs["text"]

    @staticmethod
    def message(application) -> str:
        return application.material_auto_id_run_label.kwargs["text"]

    @staticmethod
    def click(application):
        page = application.material_identification_pages["0. Auto-ID Setup"]
        found = []

        def walk(widget):
            if widget.kwargs.get("text") == EVALUATE:
                found.append(widget.kwargs["command"])
            for child in widget.children:
                walk(child)

        walk(page)
        assert len(found) == 1
        found[0]()


class EvaluateButtonTests(_Gui):
    def test_01_the_button_exists_in_the_auto_id_page(self):
        application = self.application()
        page = application.material_identification_pages["0. Auto-ID Setup"]
        texts = []

        def walk(widget):
            texts.append(widget.kwargs.get("text"))
            for child in widget.children:
                walk(child)

        walk(page)
        self.assertEqual(texts.count(EVALUATE), 1)
        self.assertIn("Select stored run journal...", texts)
        self.assertEqual(self.message(application), "No stored run selected.")

    def test_02_no_campaign_selected(self):
        application = self.application()
        with mock.patch.object(adapter, "judge_campaign_run") as judge:
            self.click(application)
        judge.assert_not_called()
        self.assertIn("No evaluation: select a governed family / campaign definition", self.message(application))
        self.assertIsNone(getattr(application, "scientific_readiness_record", None))

    def test_03_specimen_folder_only(self):
        folder = Path(tempfile.mkdtemp(prefix="m8_3_specimen_"))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        shutil.copyfile(SPECIMENS / "SP13.physical.specimen.json", folder / "specimen.json")
        application = self.application()
        self.select(application, "specimen", folder)
        with mock.patch.object(adapter, "judge_campaign_run") as judge:
            self.evaluate_run(application, _journal(self.run_root()))
        judge.assert_not_called()
        self.assertIn("a specimen folder declares no campaign", self.message(application))
        self.assertIsNone(getattr(application, "scientific_readiness_record", None))

    def test_04_campaign_without_a_selected_run(self):
        application = self.application()
        self.select(application, "family", self.definition_file())
        with mock.patch.object(adapter, "judge_campaign_run") as judge:
            self.click(application)
        judge.assert_not_called()
        self.assertIn("select the journal of an existing run", self.message(application))
        self.assertEqual(self.status(application), NOT_EVALUATED)

    def test_07_campaign_and_run_identity_mismatch(self):
        application = self.application()
        self.select(application, "family", RUN_A)  # the synthetic run belongs to another campaign
        with mock.patch.object(adapter, "judge_campaign_run") as judge:
            self.evaluate_run(application, _journal(self.run_root()))
        judge.assert_not_called()
        self.assertIn(StoredRunRefusalCode.RUN_CAMPAIGN_MISMATCH.value, self.message(application))
        self.assertEqual(self.status(application), NOT_EVALUATED)
        # Same campaign, a run of other specimen inputs: the backend refuses it as unrelated (typed NOT_READY)
        other, _ = synthetic_specimen(self.definition, "A", self.tmp / "other", 47000.0)
        application = self.application()
        self.select(application, "family", self.definition_file())
        self.evaluate_run(application, _journal(self.run_root()), item=other)
        self.assertEqual(self.status(application), "NOT_READY")
        self.assertIn("LM_HISTORY_UNRELATED", self.rows(application)["Refusal reasons"])

    def test_08_corrupted_journal_or_hash_chain(self):
        root = self.copy_run()
        journal = _journal(root)
        document = json.loads(journal.read_text(encoding="utf-8"))
        document["entries"][1]["record"]["residuals"] = [v * 1.01 for v in document["entries"][1]["record"]["residuals"]]
        journal.write_text(json.dumps(document), encoding="utf-8")
        application = self.application()
        self.select(application, "family", self.definition_file())
        self.evaluate_run(application, journal)
        self.assertEqual(self.status(application), "NOT_READY")  # bound to the run that was evaluated
        self.assertIn("LM_HISTORY_UNRELATED", self.rows(application)["Refusal reasons"])
        self.assertEqual(self.rows(application)["Released calibration"], "none released")
        unreadable = self.copy_run()
        _journal(unreadable).write_text("{", encoding="utf-8")
        import material_identification_ui as ui

        ui.select_auto_id_run(application, str(_journal(unreadable)))
        self.assertIn("Run not selected", self.message(application))
        self.assertIsNone(application.auto_id_selected_run_hash)
        # the evaluated run is no longer selected: its result is not retained as the selection's status
        self.assertEqual(self.status(application), NOT_EVALUATED)
        self.assertEqual(self.rows(application), {})
        self.evaluate_run(application, _journal(unreadable))
        self.assertIn("No evaluation", self.message(application))

    def test_09_missing_pipeline_journal(self):
        root = self.copy_run()
        for journal in root.glob("specimens/*/*/*/journal.json"):
            journal.unlink()
        application = self.application()
        self.select(application, "family", self.definition_file())
        self.evaluate_run(application, _journal(root))
        self.assertEqual(self.status(application), "NOT_READY")
        self.assertIn("LM_HISTORY_MISSING", self.rows(application)["Refusal reasons"])
        self.assertIn("governed pipeline journal not available", self.message(application))

    def test_10_missing_required_fe_evidence(self):
        root = self.copy_run()
        for pack in root.glob("specimens/*/*/*/packs/*.npz"):
            pack.unlink()
            break
        application = self.application()
        self.select(application, "family", self.definition_file())
        self.evaluate_run(application, _journal(root))
        self.assertEqual(self.status(application), "NOT_READY")
        self.assertIn("FE_EVIDENCE_UNVERIFIED", self.rows(application)["Refusal reasons"])
        self.assertIn("FE pack", self.message(application))
        # The pinned source INP of a calibration is required too
        self.evaluate_run(application, _journal(self.run_root()), roots={})
        self.assertEqual(self.status(application), "NOT_READY")
        self.assertIn("FE_EVIDENCE_UNVERIFIED", self.rows(application)["Refusal reasons"])
        self.assertIn("pinned source INP not available", self.message(application))

    def test_11_switching_between_two_runs(self):
        first, second = _journal(self.run_root("first")), _journal(self.run_root("second"))
        self.assertNotEqual(first.parent.name, second.parent.name)
        application = self.application()
        self.select(application, "family", self.definition_file())
        self.evaluate_run(application, first)
        self.assertEqual(self.status(application), "RELEASED")
        import material_identification_ui as ui

        ui.select_auto_id_run(application, str(second))  # not evaluated yet: the first run's result is not its
        self.assertEqual(self.status(application), NOT_EVALUATED)
        self.assertEqual(self.rows(application), {})
        self.assertIn("not the currently selected run",
                      application.material_scientific_readiness_selection_label.kwargs["text"])
        self.evaluate_run(application, second)
        self.assertEqual(self.status(application), "RELEASED")
        self.assertIn(second.parent.name[:12], self.rows(application)["Campaign identity"])
        ui.select_auto_id_run(application, str(first))
        self.assertEqual(self.status(application), NOT_EVALUATED)  # the second run's record never shows for the first
        self.select(application, "family", self.definition_file())  # a new campaign selection resets the run
        self.assertIsNone(application.auto_id_selected_run_hash)
        self.assertEqual(self.message(application), "No stored run selected.")

    def test_12_13_refusal_stays_refusal_and_diagnostic_is_not_released(self):
        imprecise = self.runs["imprecise"]
        application = self.application()
        self.select(application, "family", self.definition_file(imprecise.definition, "imprecise.campaign.json"))
        self.evaluate_run(application, _journal(self.run_root("imprecise")), item=imprecise.item)
        rows = self.rows(application)
        self.assertEqual(self.status(application), "REFUSED")
        self.assertIn("CONSERVATIVE_ABOVE_CEILING", rows["Refusal reasons"])
        self.assertEqual(rows["Released calibration"], "none released")
        self.assertIn("DIAGNOSTIC_OPTIMIZER_CANDIDATE, NOT_A_RELEASE_VALUE", rows["Diagnostic-only candidate"])

    def test_14_synthetic_provenance_and_production_blocked(self):
        application = self.application()
        self.select(application, "family", self.definition_file())
        self.evaluate_run(application, _journal(self.run_root()))
        rows = self.rows(application)
        self.assertIn("SYA/fake", rows["Evidence"])
        self.assertTrue(rows["Production calibration"].startswith("NO_HUMAN_AUTHORISED_PRODUCTION_CALIBRATION_RUN"))
        self.assertTrue(rows["Production execution"].startswith("NOT_AUTHORISED"))
        self.assertIn("not a material property", rows["Released calibration"])
        config = CampaignRunConfig(self.tmp / "never", {}, "abq2024.bat", mock.Mock(), mock.Mock(), {}, "m" * 64)
        with self.assertRaises(CalibrationNotImplementedRefusal):
            CampaignRun(self.definition, [self.item], "m" * 64, config)
        self.assertFalse((self.tmp / "never").exists())

    def test_15_16_no_abaqus_subprocess_solve_or_side_effects(self):
        from services import identification_campaign_run as campaign_module
        from services import identification_step, shape_extraction

        refuse = mock.Mock(side_effect=AssertionError("forbidden call"))
        root = self.copy_run()
        before_run, before_docs = _tree(root), _tree(ROOT / "docs" / "auto_id")
        before_store = _tree(self.store)
        application = self.application()
        with mock.patch.object(subprocess, "Popen", refuse), mock.patch.object(subprocess, "run", refuse), \
                mock.patch.object(os, "system", refuse), \
                mock.patch.object(identification_step, "run_bounded_lm", refuse), \
                mock.patch.object(campaign_module, "run_bounded_lm", refuse), \
                mock.patch.object(campaign_module, "prepare_run_manifest", refuse), \
                mock.patch.object(shape_extraction, "extract_shape_pack", refuse), \
                mock.patch.object(CampaignRun, "run", refuse), mock.patch.object(CampaignRun, "evaluate", refuse), \
                mock.patch.object(CampaignRun, "__init__", refuse):
            self.select(application, "family", self.definition_file())
            self.evaluate_run(application, _journal(root))
            self.assertEqual(self.status(application), "RELEASED")
        refuse.assert_not_called()
        self.assertEqual(_tree(root), before_run)
        self.assertEqual(_tree(ROOT / "docs" / "auto_id"), before_docs)
        self.assertEqual(_tree(self.store), before_store)

    def test_confirmed_cluster_stays_a_refusal(self):
        from services import campaign_lm_provenance as lm_module

        root = self.copy_run()
        pipeline_journal = next(root.glob("specimens/*/*/*/journal.json"))
        document = json.loads(pipeline_journal.read_text(encoding="utf-8"))
        identity = copy.deepcopy(document["run_identity"])
        identity["objective_design"]["fit_clusters"] = [["R1", "R2"]]
        run_hash, entries, previous = canonical_hash(identity), [], None
        previous = run_hash
        for entry in document["entries"]:
            body = {"sequence": len(entries), "kind": entry["kind"], "record": entry["record"], "previous_hash": previous}
            entries.append(dict(body, entry_hash=canonical_hash(body)))
            previous = entries[-1]["entry_hash"]
        target = pipeline_journal.parent.parent / run_hash
        shutil.copytree(pipeline_journal.parent, target)
        (target / "journal.json").write_text(json.dumps(dict(document, run_identity=identity, run_hash=run_hash,
                                                              entries=entries)), encoding="utf-8")
        governance = lm_module.governed_pipeline_identity

        def declaring(*args):  # a governance that declares the confirmed cluster (cf. test_v12_i6 cluster tests)
            expected = governance(*args)
            expected["objective_design"]["fit_clusters"] = [["R1", "R2"]]
            return expected

        with mock.patch.object(lm_module, "governed_pipeline_identity", declaring), \
                mock.patch.object(adapter, "governed_pipeline_identity", declaring):
            evaluation = self.evaluate(_journal(root))
        record = evaluation.readiness.to_dict()
        self.assertEqual(record["status"], "NOT_READY")
        self.assertEqual([r["code"] for r in record["refusal_reasons"]], ["CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE"])
        self.assertIsNone(record["released_calibration_parameters"])


# ----------------------------------------------------------------------------- archived RUN_A / RUN_B (store-gated)

class ArchivedRunTests(unittest.TestCase):
    def setUp(self):
        self.roots = fixture_roots_from_environment()
        if not {"m7-run-a", "m7-run-b", "snadwich", "carbon-project-archive"} <= set(self.roots):
            self.skipTest("data stores m7-run-a / m7-run-b / snadwich / carbon-project-archive not configured")

    def evaluate_in_gui(self, campaign: Path, store: str):
        from test_material_identification_ui import _ApplicationHarness
        import material_identification_ui as ui

        application = _ApplicationHarness()._application()
        journal = _journal(Path(self.roots[store]))
        before = _tree(Path(self.roots[store]))
        ui.load_auto_id_source(application, "family", str(campaign))
        ui.select_auto_id_run(application, str(journal))
        with mock.patch.object(subprocess, "Popen", side_effect=AssertionError("process")):
            ui.evaluate_auto_id_run(application)
        self.assertEqual(_tree(Path(self.roots[store])), before)  # read-only
        rows = dict(application.material_scientific_readiness_table.items.values())
        return application, rows, journal

    def test_05_archived_run_a(self):
        application, rows, journal = self.evaluate_in_gui(RUN_A, "m7-run-a")
        self.assertEqual(application.material_scientific_readiness_status_label.kwargs["text"], "REFUSED")
        self.assertIn("NO_GLOBAL_PARAMETER_VALUE", rows["Global material value"])
        self.assertIn("SPEC §13 family consistency FAIL", rows["Global material value"])
        self.assertEqual(rows["Released calibration"], "none released")
        self.assertEqual(rows["Scientific question"], "not declared (v1 material identification)")
        record = application.scientific_readiness_record
        self.assertEqual(record["campaign"]["run_hash"], journal.parent.name)
        self.assertEqual(record["campaign"]["run_hash"],
                         json.loads((CAMPAIGNS / "M7_RUN_A.result.json").read_text(encoding="utf-8"))["run_hash"])

    def test_06_archived_run_b(self):
        application, rows, _ = self.evaluate_in_gui(RUN_B, "m7-run-b")
        self.assertEqual(application.material_scientific_readiness_status_label.kwargs["text"], "REFUSED")
        self.assertIn("NO_GLOBAL_PARAMETER_VALUE", rows["Global material value"])
        self.assertIn("DIAGNOSTIC_OPTIMIZER_CANDIDATE, NOT_A_RELEASE_VALUE", rows["Diagnostic-only candidate"])
        self.assertEqual(rows["Released calibration"], "none released")
        formal = application.scientific_readiness_record["material_formal_output"]
        self.assertEqual(formal["released_values"], {})

    def test_run_a_record_never_shows_for_run_b(self):
        import material_identification_ui as ui

        application, _, _ = self.evaluate_in_gui(RUN_A, "m7-run-a")
        ui.load_auto_id_source(application, "family", str(RUN_B))
        self.assertEqual(application.material_scientific_readiness_status_label.kwargs["text"], NOT_EVALUATED)
        self.assertEqual(dict(application.material_scientific_readiness_table.items.values()), {})


class RealTkEvaluateTests(_Synthetic):
    def test_real_gui_button_evaluates_a_selected_stored_run(self):
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
        definition_file = Path(tempfile.mkdtemp(prefix="m8_3_tk_")) / "synthetic.campaign.json"
        self.addCleanup(shutil.rmtree, definition_file.parent, ignore_errors=True)
        definition_file.write_text(json.dumps(self.definition.canonical), encoding="utf-8")
        ui.load_auto_id_source(application, "family", str(definition_file))
        ui.select_auto_id_run(application, str(_journal(self.run_root())))
        with mock.patch.object(adapter, "campaign_specimens", return_value=(self.item,)), \
                mock.patch("domain.experiment_fixture.fixture_roots_from_environment", return_value=self.roots()):
            ui.evaluate_auto_id_run(application)
        root.update_idletasks()
        self.assertEqual(application.material_scientific_readiness_status_label.cget("text"), "RELEASED")
        self.assertTrue(application.material_scientific_readiness_table.get_children())
        self.assertIn("Evaluated stored run", application.material_auto_id_run_label.cget("text"))


if __name__ == "__main__":
    unittest.main()
