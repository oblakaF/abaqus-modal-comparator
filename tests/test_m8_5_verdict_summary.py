"""M8.5 — concise read-only verdict summary on the Data Readiness Check (backend records only).

The summary is read from the shared backend's ``ScientificReadiness`` record shown under the current selection (M8.2 /
M8.3 / M8.4 protections); it computes nothing.  Synthetic runs use the M4.6 fake solver; RUN_A / RUN_B are read
store-gated.
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

from domain.campaign_definition import parse_campaign_definition  # noqa: E402
from domain.experiment_fixture import fixture_roots_from_environment  # noqa: E402
from services import stored_run_evidence as adapter  # noqa: E402
from services.auto_id_wizard import verdict_summary  # noqa: E402
from services.campaign_scientific_backend import judge_campaign_run  # noqa: E402
from services.identification_campaign_run import CampaignRun  # noqa: E402
from test_m7_campaign import synthetic_specimen  # noqa: E402
from test_v12_i1_campaign_question import calibration_definition  # noqa: E402
from test_v12_i6_backend_integration import rechain  # noqa: E402
from v12_i6_support import calibration_run  # noqa: E402

CAMPAIGNS = ROOT / "docs" / "auto_id" / "campaigns"
RUN_A, RUN_B = CAMPAIGNS / "M7_RUN_A.campaign.json", CAMPAIGNS / "M7_RUN_B.campaign.json"
NOT_EVALUATED = "NOT_EVALUATED_FOR_SELECTION"
CALIBRATION_LABELS = "SPECIMEN_ENGINEERING_CALIBRATION, NOT_A_MATERIAL_PROPERTY, NOT_TRANSFERABLE_WITHOUT_VALIDATION"


def _journal(run_root: Path) -> Path:
    found = list(Path(run_root).glob("campaign/*/journal.json"))
    assert len(found) == 1, found
    return found[0]


def _tree(path: Path) -> list[str]:
    return sorted(p.relative_to(path).as_posix() for p in Path(path).rglob("*"))


class _Fixture(unittest.TestCase):
    _directory = None

    @classmethod
    def setUpClass(cls):
        if _Fixture._directory is not None:
            return
        _Fixture._directory = tempfile.TemporaryDirectory()
        tmp = Path(_Fixture._directory.name)
        definition = parse_campaign_definition(calibration_definition())
        item, store = synthetic_specimen(definition, "A", tmp / "base" / "data")
        _Fixture.base = calibration_run(tmp / "base", definition=definition, item=item)
        _Fixture.store = store
        data = calibration_definition()
        data["sigma"]["setup"]["sd_ln"] = 0.2
        imprecise = parse_campaign_definition(data)
        item_b, store_b = synthetic_specimen(imprecise, "A", tmp / "imprecise" / "data")
        _Fixture.imprecise = calibration_run(tmp / "imprecise", definition=imprecise, item=item_b)
        _Fixture.imprecise_store = store_b
        _Fixture.tmp = tmp

    def application(self, record=None):
        from test_material_identification_ui import _ApplicationHarness

        application = _ApplicationHarness()._application()
        if record is not None:
            application.scientific_readiness_record = record
        application._refresh_material_identification_pages()
        return application

    def definition_file(self, definition) -> Path:
        folder = Path(tempfile.mkdtemp(prefix="m8_5_def_"))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        path = folder / "campaign.campaign.json"
        path.write_text(json.dumps(definition.canonical), encoding="utf-8")
        return path

    def copy_run(self, run) -> Path:
        target = Path(tempfile.mkdtemp(prefix="m8_5_run_"))
        self.addCleanup(shutil.rmtree, target, ignore_errors=True)
        shutil.copytree(run.campaign.run_dir.parent.parent, target / "runs")
        return target / "runs"

    def patched(self, run):
        store = self.imprecise_store if run is self.imprecise else self.store
        return (mock.patch.object(adapter, "campaign_specimens", return_value=(run.item,)),
                mock.patch("domain.experiment_fixture.fixture_roots_from_environment",
                           return_value={"synthetic": store}))

    def gui(self, function, application, run, *args):
        first, second = self.patched(run)
        with first, second:
            function(application, *args)

    def evaluated(self, run=None, root=None):
        import material_identification_ui as ui

        run = run or self.base
        root = root or self.copy_run(run)
        application = self.application()
        ui.load_auto_id_source(application, "family", str(self.definition_file(run.definition)))
        self.gui(ui.select_auto_id_run, application, run, str(_journal(root)))
        self.gui(ui.evaluate_auto_id_run, application, run)
        return application, root

    @staticmethod
    def summary(application) -> str:
        return application.material_scientific_readiness_summary_label.kwargs["text"]

    @staticmethod
    def status(application) -> str:
        return application.material_scientific_readiness_status_label.kwargs["text"]

    def assert_no_current_verdict(self, application):
        text = self.summary(application)
        self.assertEqual(self.status(application), NOT_EVALUATED)
        self.assertIn("GUI presentation state, not a backend scientific verdict", text)
        for stale in ("Released:", "E_in_plane_mpa", "Diagnostic only", "Backend status", "SYA/fake"):
            self.assertNotIn(stale, text)


def tearDownModule():
    if _Fixture._directory is not None:
        _Fixture._directory.cleanup()
        _Fixture._directory = None


# ----------------------------------------------------------------------------- states 1-9

class VerdictStateTests(_Fixture):
    def test_01_no_selection(self):
        application = self.application()
        self.assertEqual(self.summary(application), "No scientific verdict available.")
        self.assertEqual(self.status(application), "NOT AVAILABLE")

    def test_02_campaign_without_an_evaluated_run(self):
        import material_identification_ui as ui

        application = self.application()
        ui.load_auto_id_source(application, "family", str(self.definition_file(self.base.definition)))
        self.assert_no_current_verdict(application)

    def test_05_synthetic_calibration_released_with_specimen_labels(self):
        application, _ = self.evaluated()
        text = self.summary(application)
        record = application.scientific_readiness_record
        value = record["released_calibration_parameters"]["E_in_plane_mpa"]["value"]
        self.assertIn("Backend status: RELEASED", text)
        self.assertIn(f"Released: E_in_plane_mpa = {value:.6g} MPa — {CALIBRATION_LABELS}", text)
        self.assertIn("specimen-specific engineering calibration", text)
        self.assertIn("not a material property", text)
        self.assertIn("Scientific question: SPECIMEN_ENGINEERING_CALIBRATION; τ_mf 0.02 (acceptance tolerance only)",
                      text)
        self.assertIn("Evidence solver profiles: A: SYA/fake", text)
        self.assertIn("Physical calibration status: NO_HUMAN_AUTHORISED_PRODUCTION_CALIBRATION_RUN", text)
        self.assertIn("not an accepted physical calibration", text)
        self.assertIn("Production execution: NOT_AUTHORISED", text)
        self.assertIn(f"run {record['campaign']['run_hash'][:12]}", text)
        self.assertNotIn("Diagnostic only", text)

    def test_06_synthetic_refused_keeps_the_candidate_diagnostic(self):
        application, _ = self.evaluated(self.imprecise)
        text = self.summary(application)
        self.assertIn("Backend status: REFUSED", text)
        self.assertIn("Released: no value released", text)
        self.assertIn("Refused: CALIBRATION_GATE_REFUSED: CONSERVATIVE_ABOVE_CEILING", text)
        self.assertIn("Diagnostic only (not released): E_in_plane_mpa = ", text)
        self.assertIn("DIAGNOSTIC_OPTIMIZER_CANDIDATE, NOT_A_RELEASE_VALUE", text)
        self.assertNotIn("NOT_A_MATERIAL_PROPERTY, NOT_TRANSFERABLE", text)  # no release labels on a refusal

    def test_07_genuine_not_ready_shows_its_refusal_reasons(self):
        root = self.copy_run(self.base)
        for pipeline in root.glob("specimens/*/*/*/journal.json"):
            pipeline.unlink()
        application, _ = self.evaluated(root=root)
        text = self.summary(application)
        self.assertIn("Backend status: NOT_READY", text)
        self.assertIn("Not ready — missing or invalid evidence: LM_HISTORY_MISSING", text)
        self.assertIn("Released: no value released", text)
        self.assertNotIn("Diagnostic only", text)

    def test_08_confirmed_cluster_refusal_is_preserved(self):
        from test_v12_i6_backend_integration import ClusterReadinessTests

        record = ClusterReadinessTests("test_a_confirmed_cluster_is_a_readiness_refusal_without_member_matching") \
            .journal_declared_cluster().to_dict()
        text = "\n".join(verdict_summary(record))
        self.assertIn("Not ready — missing or invalid evidence: CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE", text)
        self.assertIn("Released: no value released", text)
        application = self.application(record)  # an external record, no selection
        self.assertIn("CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE", self.summary(application))

    def test_09_material_values_released(self):
        import material_identification_ui as ui
        from test_v12_i6_backend_integration import MaterialPathTests

        material = MaterialPathTests.material_run(self, (0.02, 1.0))
        record = judge_campaign_run(material.definition, material.specimens, material.evidence).to_dict()
        self.assertEqual(record["status"], "MATERIAL_VALUES_RELEASED")
        application = self.application(record)
        ui.load_auto_id_source(application, "family", str(self.definition_file(material.definition)))
        text = self.summary(application)
        released = record["material_formal_output"]["released_values"]
        self.assertIn(f"Released (formal output {record['material_formal_output']['status']}): "
                      f"E_in_plane_mpa = {released['E_in_plane_mpa']:.6g} (effective material-model values)", text)
        self.assertIn(f"Result type: material identification; material claim {record['material_claim']}", text)
        self.assertIn("Scientific question: MATERIAL_IDENTIFICATION", text)
        self.assertNotIn("NOT_A_MATERIAL_PROPERTY", text)
        self.assertNotIn("Diagnostic only", text)

    def test_partial_material_output_under_a_refused_status_releases_nothing(self):
        # The backend maps a D-076 PARTIAL_VALUES_RELEASED formal output to REFUSED: the summary follows the backend
        # status and never presents those values as a released material verdict.
        from test_v12_i6_backend_integration import MaterialPathTests

        material = MaterialPathTests.material_run(self, (0.02, 1.0))
        record = judge_campaign_run(material.definition, material.specimens, material.evidence).to_dict()
        partial = dict(record, status="REFUSED", material_formal_output=dict(
            record["material_formal_output"], status="PARTIAL_VALUES_RELEASED"))
        text = "\n".join(verdict_summary(partial))
        self.assertIn("Released: no value released", text)
        self.assertIn("Material formal output: PARTIAL_VALUES_RELEASED", text)
        self.assertNotIn("Released (formal output", text)

    def test_summary_is_read_from_the_record_only(self):
        record = judge_campaign_run(self.base.definition, [self.base.item], self.base.evidence).to_dict()
        self.assertEqual(verdict_summary(record), verdict_summary(copy.deepcopy(record)))
        forged = dict(record, released_calibration_parameters={"E_in_plane_mpa": {"value": 1.0, "unit": "MPa"}})
        self.assertIn("E_in_plane_mpa = 1 MPa", "\n".join(verdict_summary(forged)))  # echoes, never recomputes
        self.assertEqual(verdict_summary(dict(record, schema="other")), ())
        self.assertEqual(verdict_summary(None), ())
        refused = dict(record, status="REFUSED", released_calibration_parameters=None)
        self.assertIn("Released: no value released", "\n".join(verdict_summary(refused)))


# ----------------------------------------------------------------------------- safety 10-15

class VerdictSafetyTests(_Fixture):
    def test_10_changing_selection_shows_no_stale_verdict(self):
        import material_identification_ui as ui

        application, _ = self.evaluated()
        self.assertIn("Backend status: RELEASED", self.summary(application))
        self.gui(ui.select_auto_id_run, application, self.base, str(_journal(self.copy_run(self.base))))
        self.assert_no_current_verdict(application)
        application, _ = self.evaluated()
        ui.load_auto_id_source(application, "family", str(RUN_A))
        self.assert_no_current_verdict(application)

    def test_11_refresh_after_changed_evidence_shows_no_stale_verdict(self):
        import material_identification_ui as ui

        application, root = self.evaluated()
        self.gui(ui.refresh_auto_id_progress, application, self.base)  # unchanged: still current
        self.assertIn("Backend status: RELEASED", self.summary(application))
        pipeline = next(root.glob("specimens/*/*/*/journal.json"))
        document = json.loads(pipeline.read_text(encoding="utf-8"))
        pipeline.write_text(json.dumps(rechain(dict(document, entries=document["entries"]
                                                     + [copy.deepcopy(document["entries"][-1])]))), encoding="utf-8")
        self.gui(ui.refresh_auto_id_progress, application, self.base)
        self.assert_no_current_verdict(application)

    def test_12_reopen_shows_no_stale_verdict(self):
        import material_identification_ui as ui

        application, _ = self.evaluated(self.imprecise)
        self.assertIn("Backend status: REFUSED", self.summary(application))
        self.gui(ui.reopen_auto_id_run, application, self.imprecise)
        self.assert_no_current_verdict(application)

    def test_13_external_stored_records_keep_the_m8_2_behaviour(self):
        import material_identification_ui as ui

        record = judge_campaign_run(self.base.definition, [self.base.item], self.base.evidence).to_dict()
        application = self.application(record)
        self.assertIn("Backend status: RELEASED", self.summary(application))  # no selection: its own identity
        ui.load_auto_id_source(application, "family", str(self.definition_file(self.base.definition)))
        self.assertIn("Backend status: RELEASED", self.summary(application))
        ui.load_auto_id_source(application, "family", str(RUN_A))
        self.assert_no_current_verdict(application)

    def test_15_no_execution_writes_or_gui_science(self):
        import material_identification_ui as ui
        from services import identification_campaign_run as campaign_module
        from services import identification_step, shape_extraction

        refuse = mock.Mock(side_effect=AssertionError("forbidden call"))
        root = self.copy_run(self.base)
        before, before_docs = _tree(root), _tree(ROOT / "docs" / "auto_id")
        with mock.patch.object(subprocess, "Popen", refuse), mock.patch.object(subprocess, "run", refuse), \
                mock.patch.object(os, "system", refuse), \
                mock.patch.object(identification_step, "run_bounded_lm", refuse), \
                mock.patch.object(campaign_module, "prepare_run_manifest", refuse), \
                mock.patch.object(campaign_module, "extract_archived_odbs", refuse), \
                mock.patch.object(shape_extraction, "extract_shape_pack", refuse), \
                mock.patch.object(CampaignRun, "__init__", refuse), mock.patch.object(CampaignRun, "run", refuse):
            application, _ = self.evaluated(root=root)
            self.gui(ui.refresh_auto_id_progress, application, self.base)
            application._refresh_material_identification_pages()
        refuse.assert_not_called()
        self.assertEqual(_tree(root), before)
        self.assertEqual(_tree(ROOT / "docs" / "auto_id"), before_docs)
        import ast

        tree = ast.parse((ROOT / "src" / "services" / "auto_id_wizard.py").read_text(encoding="utf-8"))
        summary = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "verdict_summary")
        calls = {getattr(n.func, "id", getattr(n.func, "attr", None)) for n in ast.walk(summary)
                 if isinstance(n, ast.Call)}
        self.assertLessEqual(calls, {"isinstance", "str", "get", "join", "append", "_values", "len", "tuple",
                                     "sorted", "items", "material_verdict"})  # reads and formats only
        material = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "material_verdict")
        calls = {getattr(n.func, "id", getattr(n.func, "attr", None)) for n in ast.walk(material)
                 if isinstance(n, ast.Call)}
        self.assertLessEqual(calls, {"isinstance", "str", "get", "join", "_values"})  # audit V1: reads and formats only


class RealTkVerdictTests(_Fixture):
    def test_14_real_gui_summary_follows_the_selection(self):
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
        self.gui(ui.select_auto_id_run, application, self.base, str(_journal(self.copy_run(self.base))))
        self.gui(ui.evaluate_auto_id_run, application, self.base)
        root.update_idletasks()
        text = application.material_scientific_readiness_summary_label.cget("text")
        self.assertIn("Backend status: RELEASED", text)
        self.assertIn(CALIBRATION_LABELS, text)
        ui.load_auto_id_source(application, "family", str(RUN_A))
        root.update_idletasks()
        self.assertIn("not a backend scientific verdict",
                      application.material_scientific_readiness_summary_label.cget("text"))


class ArchivedVerdictTests(unittest.TestCase):
    def setUp(self):
        self.roots = fixture_roots_from_environment()
        if not {"m7-run-a", "m7-run-b", "snadwich", "carbon-project-archive"} <= set(self.roots):
            self.skipTest("data stores m7-run-a / m7-run-b / snadwich / carbon-project-archive not configured")

    def verdict(self, campaign: Path, store: str) -> str:
        from test_material_identification_ui import _ApplicationHarness
        import material_identification_ui as ui

        application = _ApplicationHarness()._application()
        ui.load_auto_id_source(application, "family", str(campaign))
        ui.select_auto_id_run(application, str(_journal(Path(self.roots[store]))))
        ui.evaluate_auto_id_run(application)
        return application.material_scientific_readiness_summary_label.kwargs["text"]

    def test_03_run_a_refused_section_13_fail(self):
        text = self.verdict(RUN_A, "m7-run-a")
        self.assertIn("Backend status: REFUSED", text)
        self.assertIn("Released: no value released", text)
        self.assertIn("Material formal output: NO_GLOBAL_PARAMETER_VALUE; SPEC §13 family consistency FAIL", text)
        self.assertIn("Scientific question: not declared (historical v1 definition; none inferred); τ_mf not declared",
                      text)
        self.assertIn("Result type: material identification; no global material property released", text)
        self.assertNotIn("Physical calibration status", text)

    def test_04_run_b_refused_diagnostic_only(self):
        text = self.verdict(RUN_B, "m7-run-b")
        self.assertIn("Backend status: REFUSED", text)
        self.assertIn("Released: no value released", text)
        self.assertIn("Diagnostic only (not released): E_in_plane_mpa = 50886.2, G12_mpa = 6872.05", text)
        self.assertIn("Material formal output: NO_GLOBAL_PARAMETER_VALUE", text)
        self.assertIn("τ_mf not declared", text)


if __name__ == "__main__":
    unittest.main()
