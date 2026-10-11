"""V12-I7.2 — final reporting / provenance integration of the companion material verdict (D-080; SPEC v1.2 §1).

Presentation and export only: the wording for a calibration record without the companion field, the companion
NOT_AVAILABLE reasons (definition refused vs run evidence not verified), the recorded companion hashes in the M8.7
Sources / provenance section and a companion record hash reference in the M8.8 export. Nothing is judged again, no
material report is rebuilt and no calibration quantity changes. Synthetic runs use the M4.6 fake solver.
"""

from __future__ import annotations

import copy
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

from domain.identification_run import canonical_hash  # noqa: E402
from services import campaign_scientific_backend as backend  # noqa: E402
from services import stored_run_evidence  # noqa: E402
from services.auto_id_evidence_export import ExportRefusal, ExportRefusalCode, build_evidence_export  # noqa: E402
from services.auto_id_wizard import (  # noqa: E402
    MATERIAL_VERDICT_NOT_COMPUTED,
    material_verdict,
    uncertainty_breakdown,
    verdict_summary,
)
from services.campaign_scientific_backend import judge_campaign_run, readiness_presentation  # noqa: E402
from services.identification_campaign_run import CampaignRun  # noqa: E402
import test_m8_8_evidence_export as m88  # noqa: E402
import test_v12_i6_backend_integration as backend_tests  # noqa: E402
from test_v12_i7_companion_material_verdict import ARCHIVED_RECORD_HASH, HISTORICAL  # noqa: E402
from v12_i6_support import with_journal  # noqa: E402

CAMPAIGNS = ROOT / "docs" / "auto_id" / "campaigns"
SOURCES = "Sources / provenance"
RECORD_ROW = "Companion material verdict · record hash"
REPORT_ROW = "Companion material verdict · material report hash"
UNCERTAINTY_SECTIONS = ("A · Covariance basis", "B · Statistical uncertainty", "C · Birge adjustment",
                        "D · Model-form robustness", "E · Conservative calibration uncertainty")
MATERIAL_ROWS = ("Material verdict — question", "Material verdict — formal output", "Material verdict — status")


class _Fixture(m88._Fixture):
    """The M8.8 GUI / export helpers on genuine synthetic runs built in this module's own directory."""

    _own = None
    _own_runs: dict = {}

    @classmethod
    def setUpClass(cls):
        if _Fixture._own is None:
            _Fixture._own = tempfile.TemporaryDirectory()
            tmp = Path(_Fixture._own.name)
            _Fixture._own_runs = {name: backend_tests._SCENARIOS[name](tmp / name) for name in ("base", "imprecise")}
        cls.base = _Fixture._own_runs["base"]
        cls.imprecise = _Fixture._own_runs["imprecise"]

    def judged(self, run, definition=None, specimens=None, evidence=None):
        return judge_campaign_run(definition or run.definition, specimens or [run.item],
                                  run.evidence if evidence is None else evidence)

    @staticmethod
    def rows(record, report=None):
        return {(section, item): value for section, item, value in uncertainty_breakdown(record, report)}


def tearDownModule():
    if _Fixture._own is not None:
        _Fixture._own.cleanup()
        _Fixture._own = None
        _Fixture._own_runs = {}
    directory = backend_tests.MaterialPathTests._directory
    if directory is not None:
        directory.cleanup()
        backend_tests.MaterialPathTests._directory = None
        backend_tests.MaterialPathTests._runs = {}


# ----------------------------------------------------------------------------- 1-2 legacy and current wording

class WordingTests(_Fixture):
    def test_01_calibration_record_without_companion_is_not_computed(self):
        record = self.judged(self.base).to_dict()
        legacy = {k: v for k, v in record.items() if k != "companion_material_verdict"}
        values = dict(material_verdict(legacy))
        status = values["Material verdict — status"]
        self.assertTrue(status.startswith("MATERIAL_VERDICT_NOT_COMPUTED — the displayed calibration record contains "
                                          "no companion material verdict"))
        self.assertIn("it may be a legacy record", status)
        self.assertIn("this absence is not a computed scientific decision", status)
        self.assertIn("evaluate the stored run again, explicitly, when its evidence is available", status)
        self.assertNotIn("pending V12-I7", MATERIAL_VERDICT_NOT_COMPUTED)
        for dated in ("before V12-I7", "predates", "created"):  # the age of a record is never inferred
            self.assertNotIn(dated, MATERIAL_VERDICT_NOT_COMPUTED)
        self.assertEqual(values["Material verdict — formal output"], "NOT_AVAILABLE (MATERIAL_VERDICT_NOT_COMPUTED)")
        self.assertTrue(values["Calibration verdict"].startswith("RELEASED"))
        self.assertNotIn(RECORD_ROW, {item for _, item in self.rows(legacy)})  # no companion row is invented

    def test_02_current_calibration_record_shows_its_companion(self):
        record = self.judged(self.base).to_dict()
        companion = record["companion_material_verdict"]
        values = dict(material_verdict(record))
        self.assertNotIn("MATERIAL_VERDICT_NOT_COMPUTED", values["Material verdict — status"])
        self.assertIn(f"companion record {companion['record_hash'][:12]}", values["Material verdict — formal output"])
        self.assertTrue(values["Material verdict — status"].startswith("REFUSED: NO_GLOBAL_PARAMETER_VALUE"))


# ----------------------------------------------------------------------------- 3-4 NOT_AVAILABLE reasons

class NotAvailableReasonTests(_Fixture):
    def assert_not_available(self, judge, code, reason):
        readiness = judge()
        record = readiness.to_dict()
        self.assertEqual(record["status"], "NOT_READY")
        self.assertEqual(readiness.refusal_codes, (code,))  # the exact refusal code is preserved
        self.assertIsNone(readiness.calibration_record)
        self.assertIsNone(record["released_calibration_parameters"])
        self.assertEqual(record["scientific_question"], "SPECIMEN_ENGINEERING_CALIBRATION")
        companion = record["companion_material_verdict"]
        self.assertEqual(companion["status"], "NOT_AVAILABLE")
        self.assertIsNone(companion["formal_output"])
        self.assertEqual(len(companion["reasons"]), 1)
        self.assertTrue(companion["reasons"][0].startswith(f"{reason} ({code}): "), companion["reasons"][0])
        self.assertEqual(companion["record_hash"],
                         canonical_hash({k: v for k, v in companion.items() if k != "record_hash"}))
        self.assertEqual(record, judge().to_dict())  # deterministic
        self.assertTrue(dict(readiness_presentation(record))["Material verdict — status"].startswith(
            f"NOT_AVAILABLE — {reason} ({code})"))
        return companion

    def test_03_definition_refused_before_evidence_judgement(self):
        run, spec = self.base, self.base.definition.specimens[0]
        cases = (("SPECIMEN_COUNT", dict(specimens=[run.item, run.item])),
                 ("SPECIMEN_COUNT", dict(definition=replace(run.definition, specimens=(spec, spec)))),
                 ("TAU_MF_NOT_DECLARED", dict(definition=replace(run.definition, tau_mf=None))),
                 ("TAU_MF_NOT_DECLARED", dict(definition=replace(run.definition, tau_mf=0.5))))
        for code, arguments in cases:
            with self.subTest(code=code, arguments=sorted(arguments)):
                companion = self.assert_not_available(lambda: self.judged(run, **arguments), code,
                                                      "companion not judged: calibration definition refused")
                self.assertNotIn("run evidence not verified", companion["reasons"][0])
                self.assertIsNone(companion["provenance"]["run_hash"])  # no evidence was judged

    def test_04_missing_or_unverified_evidence(self):
        run = self.base
        cases = (("LM_HISTORY_MISSING", with_journal(run.evidence, pipeline_journals={})),
                 ("LM_HISTORY_MISSING", object()))
        for code, evidence in cases:
            with self.subTest(code=code, evidence=type(evidence).__name__):
                companion = self.assert_not_available(lambda: self.judged(run, evidence=evidence), code,
                                                      "run evidence not verified")
                self.assertNotIn("calibration definition refused", companion["reasons"][0])


# ----------------------------------------------------------------------------- 5-8 separation and order

class SeparationTests(_Fixture):
    def test_05_06_calibration_verdict_with_material_refusal(self):
        for run, expected in ((self.base, "RELEASED"), (self.imprecise, "REFUSED")):
            with self.subTest(calibration=expected):
                record = self.judged(run).to_dict()
                self.assertEqual(record["status"], expected)
                self.assertEqual(record["companion_material_verdict"]["status"], "NO_GLOBAL_PARAMETER_VALUE")
                self.assertIsNone(record["material_formal_output"])
                values = dict(readiness_presentation(record))
                self.assertTrue(values["Material verdict — status"].startswith("REFUSED: NO_GLOBAL_PARAMETER_VALUE"))
                self.assertTrue(values["Calibration verdict"].startswith(expected))
                self.assertEqual(record["released_calibration_parameters"] is not None, expected == "RELEASED")

    def test_07_companion_has_no_effect_on_the_calibration_gate(self):
        genuine = self.judged(self.base)
        fake = {"formal_output": {"status": "VALUES_RELEASED", "released_values": {"E_in_plane_mpa": 1.0},
                                  "blockers": [], "rule": "fake"},
                "material_claim": "IDENTIFIED_MATERIAL_PROPERTY", "family_consistency": {"status": "PASS"},
                "m5_verdict": {"verdicts": {}}, "uncertainty_basis": None}
        with mock.patch.object(backend, "campaign_report_unchecked", return_value=fake):
            other = self.judged(self.base)
        self.assertEqual(other.status, genuine.status)
        self.assertEqual(other.calibration_record.to_dict(), genuine.calibration_record.to_dict())
        self.assertEqual(other.calibration_record.gate_record_hash, genuine.calibration_record.gate_record_hash)
        changed, kept = other.to_dict(), genuine.to_dict()
        self.assertNotEqual(changed["companion_material_verdict"], kept["companion_material_verdict"])
        self.assertEqual({k: v for k, v in changed.items() if k != "companion_material_verdict"},
                         {k: v for k, v in kept.items() if k != "companion_material_verdict"})
        for section in UNCERTAINTY_SECTIONS:  # the companion never enters the calibration uncertainty rows
            self.assertEqual({k: v for k, v in self.rows(changed).items() if k[0] == section},
                             {k: v for k, v in self.rows(kept).items() if k[0] == section})

    def test_08_material_verdict_is_displayed_first(self):
        record = self.judged(self.base).to_dict()
        rows = readiness_presentation(record)
        self.assertEqual(tuple(label for label, _ in rows[:4]), MATERIAL_ROWS + ("Calibration verdict",))
        lines = verdict_summary(record)
        first = next(i for i, line in enumerate(lines) if line.startswith("Material verdict — question"))
        calibration = next(i for i, line in enumerate(lines) if line.startswith("Calibration verdict"))
        backend_status = next(i for i, line in enumerate(lines) if line.startswith("Backend status"))
        self.assertLess(first, calibration)
        self.assertLess(calibration, backend_status)


# ----------------------------------------------------------------------------- 9 M8.7 provenance rows

class BreakdownProvenanceTests(_Fixture):
    def test_09_companion_provenance_rows(self):
        record = self.judged(self.base).to_dict()
        companion = record["companion_material_verdict"]
        rows = self.rows(record)
        self.assertIn(companion["record_hash"], rows[(SOURCES, RECORD_ROW)])
        self.assertIn("separate material result, D-080; not a calibration uncertainty", rows[(SOURCES, RECORD_ROW)])
        self.assertEqual(rows[(SOURCES, REPORT_ROW)], companion["provenance"]["material_report_hash"])
        for (section, item), value in rows.items():  # never in a calibration uncertainty section
            if section in UNCERTAINTY_SECTIONS:
                self.assertNotIn("ompanion", item)
                self.assertNotIn(companion["record_hash"], value)
        # the companion's M5 uncertainties are never read into the calibration rows: sentinel values change nothing
        sentinel = copy.deepcopy(record)
        for verdict in sentinel["companion_material_verdict"]["m5_verdicts"].values():
            verdict.update(statistical_sd_ln=987.654, birge_adjusted_sd_ln=876.543, conservative_ln=765.432)
        sentinel["companion_material_verdict"]["uncertainty_basis"] = {"basis": "SENTINEL_BASIS"}
        self.assertTrue(companion["m5_verdicts"])
        changed = self.rows(sentinel)
        self.assertEqual({k: v for k, v in changed.items() if k[0] in UNCERTAINTY_SECTIONS},
                         {k: v for k, v in rows.items() if k[0] in UNCERTAINTY_SECTIONS})
        self.assertNotIn("987.654", json.dumps(sorted(changed.items())))
        order = [item for section, item, _ in uncertainty_breakdown(record) if section == SOURCES]
        self.assertLess(order.index(RECORD_ROW), order.index("Production execution"))

    def test_09_not_available_and_absent_companion(self):
        run = self.base
        record = self.judged(run, evidence=with_journal(run.evidence, pipeline_journals={})).to_dict()
        rows = self.rows(record)
        self.assertIn(record["companion_material_verdict"]["record_hash"], rows[(SOURCES, RECORD_ROW)])
        self.assertTrue(rows[(SOURCES, REPORT_ROW)].startswith("NOT_AVAILABLE — no material report recorded "
                                                               "(companion NOT_AVAILABLE)"))
        material_run = self.material()
        material = judge_campaign_run(material_run.definition, material_run.specimens, material_run.evidence)
        items = {item for _, item in self.rows(material.to_dict(), material.material_report)}
        self.assertFalse({RECORD_ROW, REPORT_ROW} & items)  # material records: unchanged, no companion rows


# ----------------------------------------------------------------------------- 10-12 M8.8 export

class ExportTests(_Fixture):
    def test_10_companion_record_hash_reference(self):
        application, _, snapshot = self.exported()
        readiness = application.auto_id_active_typed[1].readiness
        scientific = snapshot["scientific_evidence"]
        companion = scientific["backend_record"]["companion_material_verdict"]
        self.assertEqual(scientific["companion_material_verdict_record_hash"], companion["record_hash"])
        self.assertEqual(companion, readiness.companion_material_verdict)  # the typed evaluation's own record
        self.assertEqual(scientific["backend_record"], readiness.to_dict())  # backend_record unchanged
        self.assertEqual(scientific["backend_record_hash"], readiness.record_hash)
        self.assertIsNone(scientific["backend_material_report"])  # no second material report
        rows = m88.breakdown(snapshot)
        self.assertIn(companion["record_hash"], rows[(SOURCES, RECORD_ROW)])

    def test_10_material_export_has_no_companion_reference(self):
        run = self.material()
        readiness = judge_campaign_run(run.definition, run.specimens, run.evidence)
        self.assertNotIn("companion_material_verdict", readiness.to_dict())
        source = (ROOT / "src" / "services" / "auto_id_evidence_export.py").read_text(encoding="utf-8")
        self.assertIn('if "companion_material_verdict" in record:', source)  # calibration records only

    def test_11_deterministic_repeated_export(self):
        application, _ = self.evaluated()
        first = Path(self.export(application, name="first.json")).read_bytes()
        second = Path(self.export(application, name="second.json")).read_bytes()
        self.assertEqual(first, second)
        snapshot = json.loads(first)
        self.assertEqual(snapshot["content_hash"],
                         canonical_hash({k: v for k, v in snapshot.items() if k != "content_hash"}))
        self.assertIn("companion_material_verdict_record_hash", snapshot["scientific_evidence"])

    def test_12_external_display_only_record_is_never_exported_as_verified(self):
        evaluated, _ = self.evaluated()
        record = copy.deepcopy(evaluated.scientific_readiness_record)
        active, evaluation = evaluated.auto_id_active_typed
        with self.assertRaises(ExportRefusal) as caught:  # a dictionary is never the typed evaluation
            build_evidence_export(self.base.definition, active[0], (self.base.item,), record, record,
                                  evaluated.auto_id_evaluated_fingerprint)
        self.assertIs(caught.exception.code, ExportRefusalCode.NOT_EVALUATED)
        forged = copy.deepcopy(record)
        forged["companion_material_verdict"]["status"] = "VALUES_RELEASED"
        with self.assertRaises(ExportRefusal) as caught:  # a forged companion is not the evaluated record
            build_evidence_export(self.base.definition, active[0], (self.base.item,), evaluation, forged,
                                  evaluated.auto_id_evaluated_fingerprint)
        self.assertIs(caught.exception.code, ExportRefusalCode.RECORD_BINDING)
        display_only = self.application(record)
        self.assert_refused(display_only, ExportRefusalCode.NO_CAMPAIGN)


# ----------------------------------------------------------------------------- 13-14 unchanged records

class UnchangedTests(_Fixture):
    def test_13_run_a_run_b_records_and_hashes(self):
        for name, expected in HISTORICAL.items():
            with self.subTest(record=name):
                self.assertEqual(canonical_hash(json.loads((CAMPAIGNS / name).read_text(encoding="utf-8"))), expected)
        from domain.campaign_definition import load_campaign_definition
        from domain.experiment_fixture import fixture_roots_from_environment
        from services.stored_run_evidence import evaluate_stored_run

        roots = fixture_roots_from_environment()
        if not {"m7-run-a", "m7-run-b", "snadwich", "carbon-project-archive"} <= set(roots):
            self.skipTest("data stores m7-run-a / m7-run-b / snadwich / carbon-project-archive not configured")
        for name, (store, expected) in ARCHIVED_RECORD_HASH.items():
            with self.subTest(run=name):
                definition = load_campaign_definition(CAMPAIGNS / f"{name}.campaign.json")
                journal = next(Path(roots[store]).glob("campaign/*/journal.json"))
                evaluation = evaluate_stored_run(definition, journal, ROOT, roots)
                self.assertEqual(evaluation.readiness.record_hash, expected)
                items = {item for _, item, _ in uncertainty_breakdown(evaluation.readiness.to_dict(),
                                                                   evaluation.readiness.material_report)}
                self.assertFalse({RECORD_ROW, REPORT_ROW} & items)

    def test_14_material_campaigns_unchanged(self):
        for shift, expected in ((1.0, "MATERIAL_VALUES_RELEASED"), (1.12, "REFUSED")):
            with self.subTest(shift=shift):
                run = backend_tests.MaterialPathTests.material_run(self, (0.02, shift))
                readiness = judge_campaign_run(run.definition, run.specimens, run.evidence)
                record = readiness.to_dict()
                self.assertEqual(record["status"], expected)
                self.assertNotIn("companion_material_verdict", record)
                self.assertNotIn("MATERIAL_VERDICT_NOT_COMPUTED", " ".join(v for _, v in readiness_presentation(record)))


# ----------------------------------------------------------------------------- 15 GUI

class GuiTests(_Fixture):
    def test_15_fake_gui_harness(self):
        import material_identification_ui as ui

        application, _ = self.evaluated()
        rows = ui.scientific_readiness_view(application)["rows"]
        labels = [row[0] for row in rows]
        first = labels.index("Material verdict — question")
        self.assertLess(first, labels.index("Calibration verdict"))
        companion = application.scientific_readiness_record["companion_material_verdict"]
        shown = {(section, item): value for section, item, value in ui.uncertainty_breakdown_view(application)}
        self.assertIn(companion["record_hash"], shown[(SOURCES, RECORD_ROW)])
        self.assertEqual(shown[(SOURCES, REPORT_ROW)], companion["provenance"]["material_report_hash"])

    def test_15_real_tk(self):
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
        self.gui(ui.select_auto_id_run, application, self.base, str(m88._journal(self.copy_run(self.base))))
        self.gui(ui.evaluate_auto_id_run, application, self.base)
        root.update_idletasks()
        table = application.material_scientific_readiness_table
        items = [tuple(table.item(k, "values"))[0] for k in table.get_children()]
        self.assertLess(items.index("Material verdict — question"), items.index("Calibration verdict"))
        companion = application.scientific_readiness_record["companion_material_verdict"]
        widget = application.material_uncertainty_breakdown_table
        shown = {tuple(widget.item(k, "values"))[1]: tuple(widget.item(k, "values"))[2]
                 for k in widget.get_children()}
        self.assertIn(companion["record_hash"], str(shown[RECORD_ROW]))
        self.assertEqual(str(shown[REPORT_ROW]), companion["provenance"]["material_report_hash"])
        path = self.gui(ui.export_auto_id_evidence, application, self.base, str(self.out / "tk.json"))
        snapshot = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertEqual(snapshot["scientific_evidence"]["companion_material_verdict_record_hash"],
                         companion["record_hash"])


# ----------------------------------------------------------------------------- 16 safety

class SafetyTests(_Fixture):
    def test_16_no_abaqus_fe_lm_or_journal_writes(self):
        import material_identification_ui as ui
        from services import identification_campaign_run as campaign_module
        from services import identification_step, shape_extraction

        refuse = mock.Mock(side_effect=AssertionError("forbidden call"))
        root = self.copy_run(self.base)
        watched = (m88.store_of(self.base), ROOT / "docs", ROOT / "src", root)
        before = [m88._tree(path) for path in watched]
        with mock.patch.object(subprocess, "Popen", refuse), mock.patch.object(subprocess, "run", refuse), \
                mock.patch.object(os, "system", refuse), \
                mock.patch.object(identification_step, "run_bounded_lm", refuse), \
                mock.patch.object(campaign_module, "prepare_run_manifest", refuse), \
                mock.patch.object(campaign_module, "extract_archived_odbs", refuse), \
                mock.patch.object(shape_extraction, "extract_shape_pack", refuse), \
                mock.patch.object(CampaignRun, "__init__", refuse), mock.patch.object(CampaignRun, "run", refuse):
            for run in (self.base, self.imprecise):
                self.judged(run)
                self.judged(run, specimens=[run.item, run.item])
            application, _ = self.evaluated(root=root)
            ui.uncertainty_breakdown_view(application)
            with mock.patch.object(backend, "judge_campaign_run", refuse), \
                    mock.patch.object(stored_run_evidence, "judge_campaign_run", refuse), \
                    mock.patch.object(backend, "campaign_report_unchecked", refuse):
                path = self.export(application)  # never judged again, no material report rebuilt
        refuse.assert_not_called()
        self.assertIsNotNone(path)
        self.assertEqual([m88._tree(path) for path in watched], before)
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["evidence.json"])


if __name__ == "__main__":
    unittest.main()
