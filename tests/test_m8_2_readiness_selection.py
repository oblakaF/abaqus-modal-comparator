"""M8.2 — selection-aware Data Readiness Check (presentation only; no Abaqus, no new scientific engine).

The V12-I6 readiness record is presented only under its own governed selection: a source selected in the M8.1 setup
page never inherits the scientific result of another campaign.  The binding is by governed identity (campaign hash,
run type, specimens, declared question and τ_mf, run hash when selected), never by names.  The stored record is never
changed and a match is not proof of authenticity.
"""

from __future__ import annotations

from dataclasses import replace
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
)
from domain.experiment_fixture import fixture_roots_from_environment  # noqa: E402
from services.auto_id_wizard import (  # noqa: E402
    SelectionState,
    prepare_family,
    prepare_specimen_folder,
    readiness_selection,
)
from services.campaign_scientific_backend import (  # noqa: E402
    ReadinessStatus,
    ScientificReadiness,
    _campaign,
    judge_campaign_run,
)
from services.identification_campaign_run import CampaignRun, CampaignRunConfig  # noqa: E402

CAMPAIGNS = ROOT / "docs" / "auto_id" / "campaigns"
SPECIMENS = ROOT / "docs" / "auto_id" / "specimens"
RUN_A, RUN_B = CAMPAIGNS / "M7_RUN_A.campaign.json", CAMPAIGNS / "M7_RUN_B.campaign.json"
NOT_EVALUATED = SelectionState.NOT_EVALUATED_FOR_SELECTION.value
RUN_B_CANDIDATE = {"E_in_plane_mpa": 50886.241471158406, "G12_mpa": 6872.052773289999}


def stored_material_record(path: Path, candidate=None, run_hash="r" * 64, **changes) -> dict:
    """A backend readiness record (``ScientificReadiness.to_dict``) with the campaign's governed identity."""
    definition = load_campaign_definition(path)
    formal = {"status": "NO_GLOBAL_PARAMETER_VALUE", "released_values": {}, "blockers": ["FAMILY_CONSISTENCY_FAIL"]}
    record = ScientificReadiness(
        ReadinessStatus.REFUSED, definition.scientific_question, definition.tau_mf, _campaign(definition, run_hash),
        ({"code": "NO_GLOBAL_PARAMETER_VALUE", "detail": "FAMILY_CONSISTENCY_FAIL"},),
        {"solver_profiles": {}, "fe_sources": {}, "lm_provenance": None}, None,
        None if candidate is None else {"labels": ["DIAGNOSTIC_OPTIMIZER_CANDIDATE", "NOT_A_RELEASE_VALUE"],
                                        "parameters": candidate},
        material_report={"formal_output": formal, "family_consistency": {"status": "FAIL"},
                         "material_claim": "NO_MATERIAL_PROPERTY_CLAIM"}).to_dict()
    record.update(changes)
    return record


def _text(application) -> str:
    rows = tuple(application.material_scientific_readiness_table.items.values())
    return json.dumps(rows) + application.material_scientific_readiness_status_label.kwargs["text"]


class _Gui(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m8_2_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def application(self, record=None):
        from test_material_identification_ui import _ApplicationHarness

        application = _ApplicationHarness()._application()
        if record is not None:
            application.scientific_readiness_record = record
        application._refresh_material_identification_pages()
        return application

    @staticmethod
    def select(application, kind, path):
        import material_identification_ui as ui

        ui.load_auto_id_source(application, kind, str(path))

    @staticmethod
    def rows(application) -> dict:
        return dict(application.material_scientific_readiness_table.items.values())

    @staticmethod
    def status(application) -> str:
        return application.material_scientific_readiness_status_label.kwargs["text"]

    @staticmethod
    def selection(application) -> str:
        return application.material_scientific_readiness_selection_label.kwargs["text"]

    def assert_not_evaluated(self, application, reason: str):
        self.assertEqual(self.rows(application), {})
        self.assertEqual(self.status(application), NOT_EVALUATED)
        self.assertIn(reason, self.selection(application))

    def specimen_folder(self) -> Path:
        folder = self.tmp / "specimen"
        folder.mkdir()
        shutil.copyfile(SPECIMENS / "SP13.physical.specimen.json", folder / "specimen.json")
        return folder

    def definition_file(self, definition, name="synthetic.campaign.json") -> Path:
        path = self.tmp / name
        path.write_text(json.dumps(definition.canonical), encoding="utf-8")
        self.assertEqual(load_campaign_definition(path).campaign_hash, definition.campaign_hash)
        return path


# ----------------------------------------------------------------------------- the binding rule (pure)

class BindingRuleTests(_Gui):
    def test_identity_is_governed_never_a_name(self):
        family = prepare_family(RUN_A, ROOT, roots=None)
        record = stored_material_record(RUN_A)
        self.assertIs(readiness_selection(True, family, record).state, SelectionState.MATCHED_STORED_RECORD)
        definition = family.definition
        forged = {
            "same campaign name, another hash": dict(record, campaign=dict(record["campaign"], campaign_hash="0" * 64)),
            "another run type": dict(record, campaign=dict(record["campaign"], run_type="RUN_B")),
            "contradictory specimens": dict(record, campaign=dict(record["campaign"], specimens=["SP13", "SP02"])),
            "a declared question for a v1 campaign": dict(record, scientific_question="MATERIAL_IDENTIFICATION"),
            "a fabricated tau_mf": dict(record, tau_mf=0.02),
            "no readiness schema": dict(record, schema="another/schema"),
        }
        self.assertEqual(record["campaign"]["campaign_id"], definition.campaign_id)
        for name, other in forged.items():
            with self.subTest(case=name):
                binding = readiness_selection(True, family, other)
                self.assertIs(binding.state, SelectionState.NOT_EVALUATED_FOR_SELECTION)
                self.assertFalse(binding.show_record)
        # A selected run must be the record's run
        self.assertIs(readiness_selection(True, family, record, "r" * 64).state, SelectionState.MATCHED_STORED_RECORD)
        self.assertIs(readiness_selection(True, family, record, "s" * 64).state,
                      SelectionState.NOT_EVALUATED_FOR_SELECTION)
        matched = readiness_selection(True, family, record)
        self.assertIn("not proof", matched.detail)

    def test_states_are_presentation_only_and_not_backend_verdicts(self):
        import services.campaign_scientific_backend as backend

        self.assertNotIn(NOT_EVALUATED, {s.value for s in ReadinessStatus})
        self.assertNotIn("NOT_EVALUATED_FOR_SELECTION", (ROOT / "src" / "services" /
                                                         "campaign_scientific_backend.py").read_text(encoding="utf-8"))
        self.assertTrue(hasattr(backend, "readiness_presentation"))


# ----------------------------------------------------------------------------- the GUI cases 1–7

class SelectionGuiTests(_Gui):
    def test_01_nothing_selected(self):
        application = self.application()
        self.assertEqual(self.rows(application), {})
        self.assertEqual(self.status(application), "NOT AVAILABLE")
        self.assertIn("no source selected", self.selection(application))
        record = stored_material_record(RUN_A)
        application = self.application(record)  # V12-I6 behaviour kept: the record under its own identity
        self.assertEqual(self.rows(application)["Readiness"], "REFUSED")
        self.assertIn("not for a selection", self.selection(application))

    def test_02_run_a_without_a_record(self):
        application = self.application()
        self.select(application, "family", RUN_A)
        self.assert_not_evaluated(application, "no stored backend readiness record")

    def test_03_run_a_with_its_matching_record(self):
        record = stored_material_record(RUN_A)
        application = self.application(record)
        self.select(application, "family", RUN_A)
        rows = self.rows(application)
        self.assertEqual(rows["Readiness"], "REFUSED")
        self.assertIn("NO_GLOBAL_PARAMETER_VALUE", rows["Global material value"])
        self.assertIn("SPEC §13 family consistency FAIL", rows["Global material value"])
        self.assertEqual(self.status(application), "REFUSED")
        self.assertIn("not proof", self.selection(application))
        self.assertIs(application.scientific_readiness_record, record)

    def test_04_run_a_selected_with_a_run_b_record(self):
        record = stored_material_record(RUN_B, candidate=RUN_B_CANDIDATE)
        before = json.dumps(record, sort_keys=True)
        application = self.application(record)
        self.assertIn("50886.2", json.dumps(self.rows(application)))  # visible only under no / its own selection
        self.select(application, "family", RUN_A)
        self.assert_not_evaluated(application, "belongs to another campaign")
        text = _text(application)
        for value in ("50886", "6872", "REFUSED", "NO_GLOBAL_PARAMETER_VALUE", "DIAGNOSTIC_OPTIMIZER_CANDIDATE"):
            self.assertNotIn(value, text)
        self.assertEqual(json.dumps(application.scientific_readiness_record, sort_keys=True), before)  # unchanged

    def test_05_switching_run_a_to_run_b(self):
        record = stored_material_record(RUN_A)
        application = self.application(record)
        self.select(application, "family", RUN_A)
        self.assertEqual(self.status(application), "REFUSED")
        self.select(application, "family", RUN_B)  # the readiness page follows the selection at once
        self.assert_not_evaluated(application, "belongs to another campaign")
        self.select(application, "family", RUN_A)
        self.assertEqual(self.status(application), "REFUSED")  # the stored record was kept, only not shown for B

    def test_06_specimen_folder_without_a_campaign(self):
        folder = self.specimen_folder()
        application = self.application(stored_material_record(RUN_A))
        self.select(application, "specimen", folder)
        self.assert_not_evaluated(application, "declares no governed campaign")
        self.assertIn("no scientific question is inferred", self.selection(application))
        binding = readiness_selection(True, prepare_specimen_folder(folder, ROOT, roots=None),
                                      stored_material_record(RUN_A))
        self.assertIs(binding.state, SelectionState.NOT_EVALUATED_FOR_SELECTION)
        self.assertFalse(binding.show_record)

    def test_07_invalid_selection_after_a_valid_one(self):
        application = self.application(stored_material_record(RUN_A))
        self.select(application, "family", RUN_A)
        self.assertEqual(self.status(application), "REFUSED")
        for kind, path in (("family", self.tmp / "absent.campaign.json"), ("specimen", self.tmp / "absent")):
            with self.subTest(kind=kind):
                self.select(application, kind, path)
                self.assertEqual(self.rows(application), {})
                self.assertEqual(self.status(application), NOT_EVALUATED)
        self.select(application, "family", RUN_A)
        with mock.patch("services.auto_id_wizard.prepare_family", side_effect=RuntimeError("unexpected")):
            self.select(application, "family", RUN_A)
        self.assert_not_evaluated(application, "could not be loaded")


# ----------------------------------------------------------------------------- the scientific content 8–15

class ScientificContentTests(_Gui):
    @classmethod
    def setUpClass(cls):
        from test_v12_i6_backend_integration import ClusterReadinessTests, _Runs

        cls.runs = _Runs
        base = _Runs.run_of("base")
        cls.base = base
        cls.released = judge_campaign_run(base.definition, [base.item], base.evidence)
        imprecise = _Runs.run_of("imprecise")
        cls.imprecise = imprecise
        cls.refused = judge_campaign_run(imprecise.definition, [imprecise.item], imprecise.evidence)
        probe = ClusterReadinessTests("test_a_confirmed_cluster_is_a_readiness_refusal_without_member_matching")
        cls.cluster = probe.journal_declared_cluster()

    def matched(self, readiness, definition, name):
        application = self.application(readiness.to_dict())
        self.select(application, "family", self.definition_file(definition, name))
        self.assertIn("not proof", self.selection(application))
        return application

    def test_08_v1_question_is_not_fabricated(self):
        application = self.application(stored_material_record(RUN_A))
        self.select(application, "family", RUN_A)
        rows = self.rows(application)
        self.assertEqual(rows["Scientific question"], "not declared (v1 material identification)")
        self.assertEqual(rows["τ_mf"], "not declared")
        forged = stored_material_record(RUN_A, scientific_question="MATERIAL_IDENTIFICATION", tau_mf=0.02)
        application = self.application(forged)
        self.select(application, "family", RUN_A)
        self.assert_not_evaluated(application, "scientific question, τ_mf differ")

    def test_09_v12_question_and_tau_mf_are_preserved(self):
        application = self.matched(self.released, self.base.definition, "base.campaign.json")
        rows = self.rows(application)
        self.assertEqual(rows["Scientific question"], "SPECIMEN_ENGINEERING_CALIBRATION")
        self.assertIn("0.02 in |Δ ln f|", rows["τ_mf"])
        forged = dict(self.released.to_dict(), tau_mf=0.015)
        application = self.application(forged)
        self.select(application, "family", self.definition_file(self.base.definition, "base2.campaign.json"))
        self.assert_not_evaluated(application, "τ_mf differ")

    def test_10_scientific_refused_remains_refused(self):
        application = self.matched(self.refused, self.imprecise.definition, "imprecise.campaign.json")
        self.assertEqual(self.status(application), "REFUSED")
        self.assertIn("CONSERVATIVE_ABOVE_CEILING", self.rows(application)["Refusal reasons"])

    def test_11_diagnostic_only_values_are_never_released(self):
        rows = self.rows(self.matched(self.refused, self.imprecise.definition, "imprecise.campaign.json"))
        self.assertEqual(rows["Released calibration"], "none released")
        self.assertIn("DIAGNOSTIC_OPTIMIZER_CANDIDATE, NOT_A_RELEASE_VALUE", rows["Diagnostic-only candidate"])
        released = self.rows(self.matched(self.released, self.base.definition, "base.campaign.json"))
        self.assertIn("E_in_plane_mpa = ", released["Released calibration"])
        self.assertEqual(released["Diagnostic-only candidate"], "none")

    def test_12_cluster_refusal_remains_visible(self):
        application = self.matched(self.cluster, self.base.definition, "cluster.campaign.json")
        self.assertEqual(self.status(application), "NOT_READY")
        self.assertEqual(self.rows(application)["Cluster member evidence"],
                         "NOT AVAILABLE: a confirmed cluster cannot be released")

    def test_13_synthetic_solver_provenance_remains_explicit(self):
        rows = self.rows(self.matched(self.released, self.base.definition, "base.campaign.json"))
        self.assertIn("SYA/fake", rows["Evidence"])

    def test_14_real_production_execution_stays_blocked(self):
        rows = self.rows(self.matched(self.released, self.base.definition, "base.campaign.json"))
        self.assertTrue(rows["Production calibration"].startswith("NO_HUMAN_AUTHORISED_PRODUCTION_CALIBRATION_RUN"))
        self.assertTrue(rows["Production execution"].startswith("NOT_AUTHORISED"))
        config = CampaignRunConfig(self.tmp / "runs", {}, "abq2024.bat", mock.Mock(), mock.Mock(), {}, "m" * 64)
        with self.assertRaises(CalibrationNotImplementedRefusal):
            CampaignRun(self.base.definition, [self.base.item], "m" * 64, config)
        self.assertFalse((self.tmp / "runs").exists())

    def test_15_no_abaqus_subprocess_or_new_fe_calculation(self):
        from services import identification_step

        refuse = mock.Mock(side_effect=AssertionError("forbidden call"))
        before = sorted(p.as_posix() for p in (ROOT / "docs" / "auto_id").rglob("*"))
        with mock.patch.object(subprocess, "Popen", refuse), mock.patch.object(subprocess, "run", refuse), \
                mock.patch.object(os, "system", refuse), \
                mock.patch.object(identification_step, "run_bounded_lm", refuse), \
                mock.patch.object(CampaignRun, "evaluate", refuse), mock.patch.object(CampaignRun, "run", refuse):
            application = self.application(self.released.to_dict())
            for kind, path in (("family", RUN_A), ("family", RUN_B), ("specimen", self.specimen_folder()),
                               ("family", self.definition_file(self.base.definition, "base.campaign.json"))):
                self.select(application, kind, path)
            application._refresh_material_identification_pages()
        refuse.assert_not_called()
        self.assertEqual(sorted(p.as_posix() for p in (ROOT / "docs" / "auto_id").rglob("*")), before)
        source = (ROOT / "src" / "material_identification_ui.py").read_text(encoding="utf-8")
        for name in ("judge_campaign_run", "verify_lm_history", "evaluate_calibration_gate", "CampaignRun"):
            self.assertNotIn(name, source)  # the GUI judges nothing


class RealArchivedRecordTests(_Gui):
    def test_real_run_a_record_is_shown_only_for_run_a(self):
        """READ-ONLY (store-gated): the real RUN_A readiness record from the archived journals."""
        roots = fixture_roots_from_environment()
        if not {"m7-run-a", "snadwich", "carbon-project-archive"} <= set(roots):
            self.skipTest("data stores m7-run-a / snadwich / carbon-project-archive not configured")
        from domain.experiment_fixture import load_experiment_fixture_manifest
        from services.campaign_scientific_backend import CampaignRunEvidence
        from services.identification_campaign_run import prepare_campaign_specimens

        definition = load_campaign_definition(RUN_A)
        specimens = prepare_campaign_specimens(definition, ROOT, load_experiment_fixture_manifest(
            ROOT / "docs/auto_id/fixtures/real_experiment_fixtures.json"), roots)
        store = Path(roots["m7-run-a"])
        load = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))  # noqa: E731
        evidence = CampaignRunEvidence(load(next(store.glob("campaign/*/journal.json"))),
                                       {d["run_identity"]["extra"]["specimen"]: d for d in
                                        (load(p) for p in store.glob("specimens/*/*/*/journal.json"))}, {}, {})
        record = judge_campaign_run(definition, specimens, evidence).to_dict()
        application = self.application(record)
        self.select(application, "family", RUN_A)
        self.assertEqual(self.status(application), "REFUSED")
        self.assertIn("SPEC §13 family consistency FAIL", self.rows(application)["Global material value"])
        self.select(application, "family", RUN_B)
        self.assert_not_evaluated(application, "belongs to another campaign")


class RealTkSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import tkinter as tk

            cls.root = tk.Tk()
        except Exception as error:  # noqa: BLE001
            raise unittest.SkipTest(f"Tk is unavailable: {error}")
        cls.root.withdraw()
        import main
        import ui_workflow

        disabled = {"autosave_enabled": False, "restore_on_startup": False, "show_recovery_notice": False}
        with mock.patch.object(ui_workflow, "load_recovery_preferences", return_value=disabled), \
                mock.patch.object(ui_workflow, "discover_abaqus_installations", return_value=()):
            cls.application = main.app.ModalComparatorApp(cls.root)
        cls.root.update_idletasks()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "root"):
            cls.root.destroy()

    def test_real_gui_never_shows_another_campaigns_record(self):
        import material_identification_ui as ui

        application = self.application
        application.scientific_readiness_record = stored_material_record(RUN_B, candidate=RUN_B_CANDIDATE)
        ui.load_auto_id_source(application, "family", str(RUN_B))
        self.root.update_idletasks()
        self.assertEqual(application.material_scientific_readiness_status_label.cget("text"), "REFUSED")
        self.assertTrue(application.material_scientific_readiness_table.get_children())
        ui.load_auto_id_source(application, "family", str(RUN_A))
        self.root.update_idletasks()
        self.assertEqual(application.material_scientific_readiness_status_label.cget("text"), NOT_EVALUATED)
        self.assertEqual(application.material_scientific_readiness_table.get_children(), ())
        self.assertIn("belongs to another campaign",
                      application.material_scientific_readiness_selection_label.cget("text"))


def tearDownModule():
    from test_v12_i6_backend_integration import _Runs

    if _Runs._directory is not None:
        _Runs._directory.cleanup()
        _Runs._directory = None
        _Runs._runs.clear()


if __name__ == "__main__":
    unittest.main()
