"""M8.8 — governed Auto-ID evidence export (deterministic JSON export snapshot of the current typed evaluation).

The export wraps the shared backend's own readiness record (and, for material identification, its formal campaign
report) of the current typed evaluation; the campaign journal and every governed pipeline journal are re-verified from
disk immediately before the snapshot is built.  Nothing is evaluated again, computed or written without an explicit
Save As.  Synthetic runs use the M4.6 fake solver; RUN_A / RUN_B are read store-gated.
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

from domain.experiment_fixture import fixture_roots_from_environment  # noqa: E402
from domain.identification_run import canonical_hash  # noqa: E402
from services import auto_id_evidence_export as export_module  # noqa: E402
from services import campaign_scientific_backend, stored_run_evidence  # noqa: E402
from services import stored_run_evidence as adapter  # noqa: E402
from services.auto_id_evidence_export import (  # noqa: E402
    EXPORT_SCHEMA,
    ExportRefusal,
    ExportRefusalCode,
    build_evidence_export,
    write_export,
)
from services.identification_campaign_run import CampaignRun  # noqa: E402
from services.run_progress import run_evidence_fingerprint  # noqa: E402
from services.stored_run_evidence import StoredRunEvaluation, select_stored_run  # noqa: E402
import test_v12_i6_backend_integration as backend_tests  # noqa: E402
from test_v12_i6_backend_integration import rechain  # noqa: E402

CAMPAIGNS = ROOT / "docs" / "auto_id" / "campaigns"
RUN_A, RUN_B = CAMPAIGNS / "M7_RUN_A.campaign.json", CAMPAIGNS / "M7_RUN_B.campaign.json"
CALIBRATION_LABELS = ("SPECIMEN_ENGINEERING_CALIBRATION", "NOT_A_MATERIAL_PROPERTY",
                      "NOT_TRANSFERABLE_WITHOUT_VALIDATION")


def _journal(run_root: Path) -> Path:
    found = list(Path(run_root).glob("campaign/*/journal.json"))
    assert len(found) == 1, found
    return found[0]


def _tree(path: Path) -> list[str]:
    return sorted(p.relative_to(path).as_posix() for p in Path(path).rglob("*"))


def store_of(run) -> Path:
    return run.campaign.run_dir.parent.parent.parent / "data" / "store"


def breakdown(snapshot) -> dict:
    return {(section, item): value for section, item, value in snapshot["presentation"]["uncertainty_breakdown"]}


def append_entry(journal: Path) -> None:
    document = json.loads(journal.read_text(encoding="utf-8"))
    journal.write_text(json.dumps(rechain(dict(document, entries=document["entries"]
                                               + [copy.deepcopy(document["entries"][-1])]))), encoding="utf-8")


class _Fixture(unittest.TestCase):
    _directory = None
    _runs: dict = {}

    @classmethod
    def setUpClass(cls):
        # genuine synthetic runs of the V12-I6 scenarios, built in this module's own directory (the shared V12-I6
        # cache may be cleaned by another module's teardown)
        if _Fixture._directory is None:
            _Fixture._directory = tempfile.TemporaryDirectory()
            tmp = Path(_Fixture._directory.name)
            _Fixture._runs = {name: backend_tests._SCENARIOS[name](tmp / name)
                              for name in ("base", "imprecise", "one_family")}
        cls.base = _Fixture._runs["base"]
        cls.imprecise = _Fixture._runs["imprecise"]
        cls.one_family = _Fixture._runs["one_family"]

    def setUp(self):
        self.out = Path(tempfile.mkdtemp(prefix="m8_8_out_"))
        self.addCleanup(shutil.rmtree, self.out, ignore_errors=True)

    def material(self, shift=1.0):
        return backend_tests.MaterialPathTests.material_run(self, (0.02, shift))

    def application(self, record=None):
        from test_material_identification_ui import _ApplicationHarness

        application = _ApplicationHarness()._application()
        if record is not None:
            application.scientific_readiness_record = record
        application._refresh_material_identification_pages()
        return application

    def definition_file(self, definition) -> Path:
        folder = Path(tempfile.mkdtemp(prefix="m8_8_def_"))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        path = folder / "campaign.campaign.json"
        path.write_text(json.dumps(definition.canonical), encoding="utf-8")
        return path

    def copy_run(self, run) -> Path:
        target = Path(tempfile.mkdtemp(prefix="m8_8_run_"))
        self.addCleanup(shutil.rmtree, target, ignore_errors=True)
        shutil.copytree(run.campaign.run_dir.parent.parent, target / "runs")
        return target / "runs"

    def patched(self, run):
        specimens = tuple(getattr(run, "specimens", None) or (run.item,))
        return (mock.patch.object(adapter, "campaign_specimens", return_value=specimens),
                mock.patch("domain.experiment_fixture.fixture_roots_from_environment",
                           return_value={"synthetic": store_of(run)}))

    def gui(self, function, application, run, *args):
        first, second = self.patched(run)
        with first, second:
            return function(application, *args)

    def evaluated(self, run=None, root=None):
        import material_identification_ui as ui

        run = run or self.base
        root = root or self.copy_run(run)
        application = self.application()
        ui.load_auto_id_source(application, "family", str(self.definition_file(run.definition)))
        self.gui(ui.select_auto_id_run, application, run, str(_journal(root)))
        self.gui(ui.evaluate_auto_id_run, application, run)
        return application, root

    def export(self, application, run=None, name="evidence.json"):
        import material_identification_ui as ui

        return self.gui(ui.export_auto_id_evidence, application, run or self.base, str(self.out / name))

    def exported(self, run=None, root=None):
        application, root = self.evaluated(run, root)
        path = self.export(application, run)
        self.assertIsNotNone(path, getattr(application, "auto_id_export_message", None))
        return application, root, json.loads(Path(path).read_text(encoding="utf-8"))

    @staticmethod
    def message(application) -> str:
        return application.material_auto_id_export_label.kwargs["text"]

    def assert_refused(self, application, code, run=None):
        self.assertIsNone(self.export(application, run))
        self.assertIn(f"No export: {code.value}", self.message(application))
        self.assertEqual(list(self.out.iterdir()), [])


# ----------------------------------------------------------------------------- selection 1-4

class SelectionTests(_Fixture):
    def test_01_no_selection_no_export(self):
        self.assert_refused(self.application(), ExportRefusalCode.NO_CAMPAIGN)

    def test_02_specimen_folder_only_no_export(self):
        import material_identification_ui as ui

        application = self.application()
        folder = Path(tempfile.mkdtemp(prefix="m8_8_specimen_"))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        ui.load_auto_id_source(application, "specimen", str(folder))
        self.assert_refused(application, ExportRefusalCode.NO_CAMPAIGN)

    def test_03_no_run_no_export(self):
        import material_identification_ui as ui

        application = self.application()
        ui.load_auto_id_source(application, "family", str(self.definition_file(self.base.definition)))
        self.assert_refused(application, ExportRefusalCode.NO_RUN)

    def test_04_run_not_evaluated_no_export(self):
        import material_identification_ui as ui

        application = self.application()
        ui.load_auto_id_source(application, "family", str(self.definition_file(self.base.definition)))
        self.gui(ui.select_auto_id_run, application, self.base, str(_journal(self.copy_run(self.base))))
        self.assert_refused(application, ExportRefusalCode.NOT_EVALUATED)


# ----------------------------------------------------------------------------- integrity 5-9

class IntegrityTests(_Fixture):
    def test_05_valid_current_run_gives_deterministic_json(self):
        application, _ = self.evaluated()
        first = Path(self.export(application, name="first.json")).read_bytes()
        second = Path(self.export(application, name="second.json")).read_bytes()
        self.assertEqual(first, second)
        snapshot = json.loads(first)
        self.assertEqual(first.decode("utf-8"), json.dumps(snapshot, indent=2, sort_keys=True,
                                                           ensure_ascii=False) + "\n")
        content = {k: v for k, v in snapshot.items() if k != "content_hash"}
        self.assertEqual(snapshot["content_hash"], canonical_hash(content))
        self.assertEqual(snapshot["export"]["schema"], EXPORT_SCHEMA)
        self.assertEqual(snapshot["export"]["kind"], "EXPORT_SNAPSHOT")
        self.assertIn("not a scientific verdict", snapshot["export"]["note"])
        self.assertEqual(snapshot["export"]["verification"], "VERIFIED_FRESH_AT_EXPORT")
        text = first.decode("utf-8").lower()
        for volatile in ("timestamp", "created_at", "exported_at", "uuid"):
            self.assertNotIn(volatile, text)
        another, _ = self.evaluated()  # another evaluation of an identical copy: the same scientific content
        other = json.loads(Path(self.export(another, name="third.json")).read_bytes())
        self.assertEqual(other["scientific_evidence"], snapshot["scientific_evidence"])

    def test_06_snapshot_matches_the_backend_record_exactly(self):
        application, _, snapshot = self.exported()
        evaluation = application.auto_id_active_typed[1]
        self.assertEqual(snapshot["scientific_evidence"]["backend_record"], evaluation.readiness.to_dict())
        self.assertEqual(snapshot["scientific_evidence"]["backend_record"], application.scientific_readiness_record)
        self.assertEqual(snapshot["presentation"]["uncertainty_breakdown"],
                         [list(row) for row in __import__("material_identification_ui").uncertainty_breakdown_view(
                             application)])

    def test_07_backend_record_hash_is_preserved(self):
        application, _, snapshot = self.exported()
        readiness = application.auto_id_active_typed[1].readiness
        scientific = snapshot["scientific_evidence"]
        self.assertEqual(scientific["backend_record_hash"], readiness.record_hash)
        self.assertEqual(scientific["backend_record_hash"], canonical_hash(scientific["backend_record"]))

    def test_08_campaign_and_run_identities_match(self):
        application, root, snapshot = self.exported()
        identities = snapshot["verified_identities"]
        definition = self.base.definition
        self.assertEqual((identities["campaign_id"], identities["campaign_hash"], identities["run_type"]),
                         (definition.campaign_id, definition.campaign_hash, definition.run_type))
        self.assertEqual(identities["run_hash"], _journal(root).parent.name)
        self.assertEqual(identities["run_hash"], snapshot["scientific_evidence"]["backend_record"]["campaign"]["run_hash"])
        self.assertEqual(identities["evidence_fingerprint"], application.auto_id_evaluated_fingerprint)

    def test_09_every_specimen_pipeline_identity_is_included(self):
        material = self.material()
        _, root, snapshot = self.exported(material)
        record = snapshot["scientific_evidence"]["backend_record"]
        recorded = record["evidence"]["lm_provenance"]["pipeline_run_hashes"]
        specimens = snapshot["verified_identities"]["specimens"]
        self.assertEqual([s["label"] for s in specimens], ["A", "B"])
        for item in specimens:
            self.assertEqual(item["governed_pipeline_run_hash"], recorded[item["label"]])
            self.assertTrue((root / item["governed_pipeline_journal"]).is_file())
            self.assertEqual(item["recorded_run_identity"]["label"], item["label"])
            self.assertIn("solver_profile_hash", item["recorded_run_identity"])
            self.assertIn("observation_hash", item["recorded_run_identity"])


# ----------------------------------------------------------------------------- freshness 10-14, 27

class FreshnessTests(_Fixture):
    def assert_stale(self, application):
        self.assert_refused(application, ExportRefusalCode.STALE)
        self.assertIsNone(application.auto_id_active_evaluation)
        self.assertIsNone(application.auto_id_active_typed)
        self.assertEqual(application.material_scientific_readiness_status_label.kwargs["text"],
                         "NOT_EVALUATED_FOR_SELECTION")
        self.assertIn("evaluate it again", application.auto_id_run_message)

    def test_10_journal_changed_without_refresh_refuses(self):
        application, root = self.evaluated()
        append_entry(next(root.glob("specimens/*/*/*/journal.json")))  # no Refresh run progress afterwards
        self.assert_stale(application)

    def test_11_broken_campaign_journal_refuses(self):
        application, root = self.evaluated()
        journal = _journal(root)
        document = json.loads(journal.read_text(encoding="utf-8"))
        document["entries"][-1]["record"]["status"] = "FORGED"  # the hash chain no longer verifies
        journal.write_text(json.dumps(document), encoding="utf-8")
        self.assert_stale(application)

    def test_12_deleted_pipeline_journal_refuses(self):
        application, root = self.evaluated()
        next(root.glob("specimens/*/*/*/journal.json")).unlink()
        self.assert_stale(application)
        # deleted before the evaluation: the genuine NOT_READY stays visible; no verified export exists
        root = self.copy_run(self.base)
        for pipeline in root.glob("specimens/*/*/*/journal.json"):
            pipeline.unlink()
        application, _ = self.evaluated(root=root)
        self.assertIsNone(application.auto_id_evaluated_fingerprint)
        self.assert_refused(application, ExportRefusalCode.NOT_VERIFIED)
        self.assertEqual(application.material_scientific_readiness_status_label.kwargs["text"], "NOT_READY")
        self.assertIn("LM_HISTORY_MISSING", application.material_scientific_readiness_summary_label.kwargs["text"])
        self.assertIsNotNone(application.auto_id_active_evaluation)

    def test_13_wrong_run_or_campaign_refuses(self):
        application, root = self.evaluated()
        evaluation = application.auto_id_active_typed[1]
        record = application.scientific_readiness_record
        specimens = (self.base.item,)
        fingerprint = application.auto_id_evaluated_fingerprint
        with self.assertRaises(ExportRefusal) as caught:  # another governed campaign
            build_evidence_export(self.imprecise.definition, _journal(root), specimens, evaluation, record, fingerprint)
        self.assertIs(caught.exception.code, ExportRefusalCode.RUN_MISMATCH)
        other = _journal(self.copy_run(self.imprecise))  # another run
        with self.assertRaises(ExportRefusal) as caught:
            build_evidence_export(self.base.definition, other, specimens, evaluation, record, fingerprint)
        self.assertIs(caught.exception.code, ExportRefusalCode.RUN_MISMATCH)

    def test_14_changed_journal_path_refuses(self):
        import material_identification_ui as ui

        application, root = self.evaluated()
        evaluation = application.auto_id_active_typed[1]
        moved = _journal(self.copy_run(self.base))  # the same run hash at another path
        self.assertEqual(moved.parent.name, _journal(root).parent.name)
        with self.assertRaises(ExportRefusal) as caught:
            build_evidence_export(self.base.definition, moved, (self.base.item,), evaluation,
                                  application.scientific_readiness_record, application.auto_id_evaluated_fingerprint)
        self.assertIs(caught.exception.code, ExportRefusalCode.RUN_MISMATCH)
        self.gui(ui.select_auto_id_run, application, self.base, str(moved))
        self.assert_refused(application, ExportRefusalCode.NOT_EVALUATED)

    def test_27_external_display_only_record_is_never_exported_as_verified(self):
        import material_identification_ui as ui

        evaluated, _ = self.evaluated()
        record = copy.deepcopy(evaluated.scientific_readiness_record)
        application = self.application(record)
        self.assert_refused(application, ExportRefusalCode.NO_CAMPAIGN)
        ui.load_auto_id_source(application, "family", str(self.definition_file(self.base.definition)))
        self.assertIn("Backend status: RELEASED",
                      application.material_scientific_readiness_summary_label.kwargs["text"])
        self.assert_refused(application, ExportRefusalCode.NO_RUN)
        active, evaluation = evaluated.auto_id_active_typed
        evaluated.auto_id_active_typed = (tuple(list(active)), evaluation)  # not bound to the active evaluation
        self.assert_refused(evaluated, ExportRefusalCode.NOT_EVALUATED)
        with self.assertRaises(ExportRefusal) as caught:  # a dictionary is never accepted as the typed evaluation
            build_evidence_export(self.base.definition, active[0], (self.base.item,), record, record,
                                  evaluated.auto_id_evaluated_fingerprint)
        self.assertIs(caught.exception.code, ExportRefusalCode.NOT_EVALUATED)
        evaluated.auto_id_active_typed = (active, evaluation)
        forged = dict(evaluated.scientific_readiness_record, status="REFUSED")
        with self.assertRaises(ExportRefusal) as caught:
            build_evidence_export(self.base.definition, active[0], (self.base.item,), evaluation, forged,
                                  evaluated.auto_id_evaluated_fingerprint)
        self.assertIs(caught.exception.code, ExportRefusalCode.RECORD_BINDING)


# ----------------------------------------------------------------------------- release / refusal 15-23

class ReleaseRefusalTests(_Fixture):
    def test_15_refused_exports_no_released_values(self):
        _, _, snapshot = self.exported(self.imprecise)
        scientific = snapshot["scientific_evidence"]
        record = scientific["backend_record"]
        self.assertEqual(record["status"], "REFUSED")
        self.assertIsNone(record["released_calibration_parameters"])
        self.assertIsNone(scientific["released_specimen_calibration"])
        self.assertEqual(record["diagnostic_candidate"]["labels"],
                         ["DIAGNOSTIC_OPTIMIZER_CANDIDATE", "NOT_A_RELEASE_VALUE"])
        self.assertIn("CALIBRATION_GATE_REFUSED", [r["code"] for r in record["refusal_reasons"]])
        self.assertIn("Released: no value released", snapshot["presentation"]["verdict_summary"])

    def test_16_material_values_released_correctly_labelled(self):
        _, _, snapshot = self.exported(self.material())
        scientific = snapshot["scientific_evidence"]
        record = scientific["backend_record"]
        self.assertEqual(record["status"], "MATERIAL_VALUES_RELEASED")
        self.assertEqual(record["material_formal_output"]["status"], "VALUES_RELEASED")
        self.assertEqual(record["material_family_consistency"], "PASS")
        self.assertEqual(scientific["backend_material_report"]["formal_output"], record["material_formal_output"])
        self.assertEqual(scientific["backend_material_report_hash"],
                         canonical_hash(scientific["backend_material_report"]))
        self.assertIsNone(scientific["released_specimen_calibration"])
        self.assertIsNone(record["released_calibration_parameters"])
        self.assertNotIn("NOT_A_MATERIAL_PROPERTY", json.dumps(record))
        failed = self.material(1.12)
        _, _, snapshot = self.exported(failed)
        record = snapshot["scientific_evidence"]["backend_record"]
        self.assertEqual((record["status"], record["material_family_consistency"]), ("REFUSED", "FAIL"))
        self.assertEqual(record["material_formal_output"]["released_values"], {})

    def test_17_synthetic_released_correctly_labelled(self):
        _, _, snapshot = self.exported()
        record = snapshot["scientific_evidence"]["backend_record"]
        calibration = snapshot["scientific_evidence"]["released_specimen_calibration"]
        self.assertEqual(record["status"], "RELEASED")
        for label in CALIBRATION_LABELS + ("NOT AUTHORISED FOR PRODUCTION", "SYNTHETIC / TEST EVIDENCE"):
            self.assertIn(label, calibration["labels"])
        self.assertEqual(record["calibration"]["labels"], list(CALIBRATION_LABELS))
        self.assertEqual([c["name"] for c in calibration["engineering_constants"]],
                         ["E1", "E2", "E3", "nu12", "nu13", "nu23", "G12", "G13", "G23"])
        released = record["released_calibration_parameters"]["E_in_plane_mpa"]["value"]
        self.assertEqual(calibration["engineering_constants"][0]["value"], released)
        fragment = calibration["material_fragment"]
        self.assertEqual(fragment["labels"], ["GOVERNED_NON_PRODUCTION_PREVIEW", "NOT_AN_INP_FILE",
                                              "NEVER_ATTACHED_TO_A_PRODUCTION_MODEL"])
        self.assertEqual(fragment["source_inp_sha256"], record["calibration"]["identity"]["inp_sha256"])
        self.assertTrue(fragment["material_name"].startswith("CAL_A_"))
        self.assertIn("Solver profiles: A: SYA/fake.", calibration["evidence"])
        self.assertTrue(snapshot["production"]["execution"].startswith("NOT_AUTHORISED"))
        self.assertTrue(snapshot["production"]["calibration"].startswith(
            "NO_HUMAN_AUTHORISED_PRODUCTION_CALIBRATION_RUN"))
        self.assertNotIn("accepted physical evidence", json.dumps(snapshot))
        self.assertEqual(list(self.out.glob("*.inp")), [])

    def test_20_confirmed_cluster_refusal_is_preserved(self):
        # The genuine backend readiness of the journal-declared cluster run (V12-I6), bound to a genuine stored run:
        # the export serialises the refusal unchanged.
        readiness = backend_tests.ClusterReadinessTests(
            "test_a_confirmed_cluster_is_a_readiness_refusal_without_member_matching").journal_declared_cluster()
        root = self.copy_run(self.base)
        run = select_stored_run(_journal(root))
        evaluation = StoredRunEvaluation(run, readiness, (), {})
        fingerprint = run_evidence_fingerprint(self.base.definition, _journal(root), (self.base.item,))
        export = build_evidence_export(self.base.definition, _journal(root), (self.base.item,), evaluation,
                                       readiness.to_dict(), fingerprint)
        record = export.snapshot["scientific_evidence"]["backend_record"]
        self.assertEqual([r["code"] for r in record["refusal_reasons"]], ["CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE"])
        self.assertEqual(record["status"], "NOT_READY")
        self.assertIsNone(export.snapshot["scientific_evidence"]["released_specimen_calibration"])

    def test_21_incomplete_loo_never_gains_an_interval(self):
        _, _, snapshot = self.exported(self.one_family)
        precision = snapshot["scientific_evidence"]["backend_record"]["calibration"]["precision"]
        self.assertIsNone(precision["parameters"]["E_in_plane_mpa"]["model_form_half_range_ln"])
        rows = breakdown(snapshot)
        self.assertEqual(rows[("D · Model-form robustness", "model_form_half_range · E_in_plane_mpa")],
                         "NOT_AVAILABLE — incomplete leave-one-FIT-family-out: no model-form interval")

    def test_22_sigma_meas_not_available_remains_missing(self):
        _, _, snapshot = self.exported()
        basis = snapshot["scientific_evidence"]["backend_record"]["uncertainty_basis"]
        self.assertEqual(basis["covariance_components"]["sigma_meas"], "NOT_AVAILABLE")
        rows = breakdown(snapshot)
        self.assertEqual(rows[("A · Covariance basis", "Σ_meas status")], "NOT_AVAILABLE")
        self.assertEqual(rows[("A · Covariance basis", "Missing components")], "sigma_meas (NOT_AVAILABLE, never zero)")

    def test_23_tau_mf_never_treated_as_uncertainty(self):
        _, _, snapshot = self.exported()
        record = snapshot["scientific_evidence"]["backend_record"]
        self.assertEqual(record["calibration"]["tau_mf"]["role"], "ACCEPTANCE_TOLERANCE")
        self.assertFalse(record["calibration"]["precision"]["tau_mf_in_envelope"])
        self.assertEqual(set(record["uncertainty_basis"]["covariance_components"]), {"sigma_setup", "sigma_meas"})
        rows = breakdown(snapshot)
        self.assertEqual(rows[("F · τ_mf", "τ_mf")], "0.02 — acceptance tolerance on |Δ ln f| only")
        self.assertIn("never part of Σ", rows[("F · τ_mf", "Separation")])


class ArchivedExportTests(unittest.TestCase):
    def setUp(self):
        self.roots = fixture_roots_from_environment()
        if not {"m7-run-a", "m7-run-b", "snadwich", "carbon-project-archive"} <= set(self.roots):
            self.skipTest("data stores m7-run-a / m7-run-b / snadwich / carbon-project-archive not configured")
        self.out = Path(tempfile.mkdtemp(prefix="m8_8_archive_"))
        self.addCleanup(shutil.rmtree, self.out, ignore_errors=True)

    def snapshot(self, campaign: Path, store: str) -> dict:
        from test_material_identification_ui import _ApplicationHarness
        import material_identification_ui as ui

        application = _ApplicationHarness()._application()
        ui.load_auto_id_source(application, "family", str(campaign))
        journal = _journal(Path(self.roots[store]))
        before = journal.read_bytes()
        ui.select_auto_id_run(application, str(journal))
        ui.evaluate_auto_id_run(application)
        path = ui.export_auto_id_evidence(application, str(self.out / f"{store}.json"))
        self.assertIsNotNone(path, getattr(application, "auto_id_export_message", None))
        self.assertEqual(journal.read_bytes(), before)
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def test_18_run_a_archive_compatibility(self):
        snapshot = self.snapshot(RUN_A, "m7-run-a")
        record = snapshot["scientific_evidence"]["backend_record"]
        self.assertEqual(record["status"], "REFUSED")
        self.assertEqual(record["material_family_consistency"], "FAIL")
        self.assertEqual(record["material_formal_output"]["status"], "NO_GLOBAL_PARAMETER_VALUE")
        self.assertEqual(record["material_formal_output"]["released_values"], {})
        self.assertIsNone(record["tau_mf"])
        self.assertEqual([s["label"] for s in snapshot["verified_identities"]["specimens"]], ["SP02", "SP13"])
        self.assertEqual(snapshot["scientific_evidence"]["backend_material_report"]["family_consistency"]["status"],
                         "FAIL")

    def test_19_run_b_archive_compatibility(self):
        snapshot = self.snapshot(RUN_B, "m7-run-b")
        record = snapshot["scientific_evidence"]["backend_record"]
        self.assertEqual(record["status"], "REFUSED")
        self.assertEqual(record["material_formal_output"]["released_values"], {})
        self.assertEqual(record["diagnostic_candidate"]["labels"],
                         ["DIAGNOSTIC_OPTIMIZER_CANDIDATE", "NOT_A_RELEASE_VALUE"])
        self.assertEqual(sorted(record["diagnostic_candidate"]["parameters"]), ["E_in_plane_mpa", "G12_mpa"])
        rows = breakdown(snapshot)
        self.assertTrue(rows[("D · Model-form robustness", "half_range · E_in_plane_mpa (M5 verdict)")]
                        .startswith("NOT_AVAILABLE"))


# ----------------------------------------------------------------------------- write safety 24-26

class WriteSafetyTests(_Fixture):
    def test_24_cancelled_save_as_writes_no_file(self):
        import material_identification_ui as ui

        application, _ = self.evaluated()
        with mock.patch.object(ui.filedialog, "asksaveasfilename", return_value="") as dialog:
            self.assertIsNone(self.gui(ui.export_auto_id_evidence, application, self.base))
        dialog.assert_called_once()
        self.assertEqual(dialog.call_args.kwargs["defaultextension"], ".json")
        self.assertEqual(self.message(application), "Export cancelled: no file written.")
        self.assertEqual(list(self.out.iterdir()), [])

    def test_25_failed_write_leaves_no_partial_output(self):
        application, _ = self.evaluated()
        with mock.patch.object(export_module.os, "replace", side_effect=OSError("disk full")):
            self.assertIsNone(self.export(application))
        self.assertIn("WRITE_FAILED", self.message(application))
        self.assertEqual(list(self.out.iterdir()), [])
        with mock.patch.object(export_module.os, "fsync", side_effect=OSError("device error")):
            self.assertIsNone(self.export(application))
        self.assertEqual(list(self.out.iterdir()), [])
        self.assertIsNotNone(application.auto_id_active_evaluation)  # the verdict is not altered by a failed export
        earlier = Path(self.export(application))  # a failed replacement keeps the earlier export intact
        content = earlier.read_bytes()
        for failure in ("fsync", "replace"):
            with mock.patch.object(export_module.os, failure, side_effect=OSError("interrupted")):
                self.assertIsNone(self.export(application))
            self.assertEqual(earlier.read_bytes(), content)
            self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["evidence.json"])

    def test_26_protected_scientific_paths_are_never_overwritten(self):
        import material_identification_ui as ui

        application, root = self.evaluated()
        definition = Path(application.auto_id_source[1])
        foreign = self.out / "notes.json"
        foreign.write_text('{"mine": true}', encoding="utf-8")
        targets = [_journal(root), next(root.glob("specimens/*/*/*/journal.json")), definition,
                   ROOT / "docs" / "auto_id" / "STATUS.json", ROOT / "docs" / "auto_id" / "DECISIONS.md",
                   store_of(self.base) / "models" / "SYA.inp", root / "new-export.json", foreign]
        before = {path: path.read_bytes() for path in targets if path.exists()}
        for target in targets:
            with self.subTest(target=target.name):
                self.assertIsNone(self.gui(ui.export_auto_id_evidence, application, self.base, str(target)))
                self.assertIn("DESTINATION_REFUSED", self.message(application))
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertFalse((root / "new-export.json").exists())
        first = self.export(application, name="again.json")  # an earlier export may be replaced by a new one
        self.assertIsNotNone(self.export(application, name="again.json"))
        self.assertEqual(Path(first).name, "again.json")


# ----------------------------------------------------------------------------- GUI 28-29, safety 30

class GuiTests(_Fixture):
    def test_28_fake_gui_harness_button_exports_on_direct_action_only(self):
        import material_identification_ui as ui

        application, _ = self.evaluated()
        page = application.material_identification_pages
        buttons = {}

        def collect(widget):
            if "command" in widget.kwargs and widget.kwargs.get("text"):
                buttons[widget.kwargs.get("text")] = widget.kwargs["command"]
            for child in widget.children:
                collect(child)

        for frame in page.values():
            collect(frame)
        self.assertIn(ui.AUTO_ID_EXPORT_LABEL, buttons)
        self.assertEqual(list(self.out.iterdir()), [])  # selection, evaluation and refresh never export
        target = self.out / "button.json"
        with mock.patch.object(ui.filedialog, "asksaveasfilename", return_value=str(target)):
            first, second = self.patched(self.base)
            with first, second:
                buttons[ui.AUTO_ID_EXPORT_LABEL]()
        self.assertTrue(target.is_file())
        self.assertIn("Exported the verified Auto-ID evidence snapshot", self.message(application))
        self.assertIn("not an accepted scientific evidence record", self.message(application))
        self.assertEqual(application.material_scientific_readiness_status_label.kwargs["text"], "RELEASED")
        ui.load_auto_id_source(application, "family", str(RUN_A))
        self.assertNotIn("Exported", self.message(application))  # the message belongs to its selection

    def test_29_real_tk_export(self):
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
        path = self.gui(ui.export_auto_id_evidence, application, self.base, str(self.out / "tk.json"))
        root.update_idletasks()
        self.assertIsNotNone(path)
        self.assertIn("Exported", application.material_auto_id_export_label.cget("text"))
        snapshot = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertEqual(snapshot["scientific_evidence"]["backend_record"]["status"], "RELEASED")


class SafetyTests(_Fixture):
    def test_30_no_abaqus_solver_lm_or_evidence_writes(self):
        import material_identification_ui as ui
        from services import identification_campaign_run as campaign_module
        from services import identification_step, shape_extraction

        refuse = mock.Mock(side_effect=AssertionError("forbidden call"))
        root = self.copy_run(self.base)
        watched = (store_of(self.base), ROOT / "docs", ROOT / "src", root)
        before = [_tree(path) for path in watched]
        with mock.patch.object(subprocess, "Popen", refuse), mock.patch.object(subprocess, "run", refuse), \
                mock.patch.object(os, "system", refuse), \
                mock.patch.object(identification_step, "run_bounded_lm", refuse), \
                mock.patch.object(campaign_module, "prepare_run_manifest", refuse), \
                mock.patch.object(campaign_module, "extract_archived_odbs", refuse), \
                mock.patch.object(shape_extraction, "extract_shape_pack", refuse), \
                mock.patch.object(CampaignRun, "__init__", refuse), mock.patch.object(CampaignRun, "run", refuse):
            application, _ = self.evaluated(root=root)
            with mock.patch.object(campaign_scientific_backend, "judge_campaign_run", refuse), \
                    mock.patch.object(stored_run_evidence, "judge_campaign_run", refuse):
                path = self.export(application)  # never evaluated again
        refuse.assert_not_called()
        self.assertIsNotNone(path)
        self.assertEqual([_tree(path) for path in watched], before)
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["evidence.json"])
        source = (ROOT / "src" / "services" / "auto_id_evidence_export.py").read_text(encoding="utf-8")
        for forbidden in ("subprocess", "judge_campaign_run", "evaluate_stored_run", "run_bounded_lm",
                          "render_calibration_inp_fragment", "require_executable", "tau_mf",
                          "SPECIMEN_ENGINEERING_CALIBRATION", "datetime", "time.time", "import uuid", "import random"):
            self.assertNotIn(forbidden, source)


class ExportSafetyCorrectionTests(_Fixture):
    """M8.8 final export-safety correction: freshness after Save As and fail-closed write errors."""

    def test_31_journal_changed_while_save_as_is_open_refuses(self):
        import material_identification_ui as ui

        application, root = self.evaluated()
        self.assertEqual(application.scientific_readiness_record["status"], "RELEASED")
        target = self.out / "raced.json"

        def save_as(**_):  # the governed pipeline journal changes while the dialog is open
            append_entry(next(root.glob("specimens/*/*/*/journal.json")))
            return str(target)

        with mock.patch.object(ui.filedialog, "asksaveasfilename", side_effect=save_as):
            self.assertIsNone(self.gui(ui.export_auto_id_evidence, application, self.base))
        self.assertIn("No export: EVIDENCE_CHANGED_SINCE_EVALUATION", self.message(application))
        self.assertFalse(target.exists())
        self.assertEqual(list(self.out.iterdir()), [])
        self.assertIsNone(application.auto_id_active_evaluation)
        self.assertIsNone(application.auto_id_active_typed)
        self.assertEqual(application.material_scientific_readiness_status_label.kwargs["text"],
                         "NOT_EVALUATED_FOR_SELECTION")
        # unchanged evidence while the dialog is open: the same deterministic document as a direct export
        application, _ = self.evaluated()
        direct = Path(self.export(application, name="direct.json")).read_bytes()
        with mock.patch.object(ui.filedialog, "asksaveasfilename", return_value=str(self.out / "dialog.json")):
            path = self.gui(ui.export_auto_id_evidence, application, self.base)
        self.assertEqual(Path(path).read_bytes(), direct)

    def test_32_mkstemp_failure_is_a_typed_write_refusal(self):
        application, _ = self.evaluated()
        earlier = Path(self.export(application))
        content = earlier.read_bytes()
        record = application.scientific_readiness_record
        snapshot = copy.deepcopy(record)
        with mock.patch.object(export_module.tempfile, "mkstemp", side_effect=OSError("no space for temporary")):
            self.assertIsNone(self.export(application))
        self.assertIn("No export: WRITE_FAILED", self.message(application))
        self.assertEqual(earlier.read_bytes(), content)
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["evidence.json"])
        self.assertIs(application.scientific_readiness_record, record)
        self.assertEqual(record, snapshot)
        self.assertIsNotNone(application.auto_id_active_evaluation)
        export = build_evidence_export(self.base.definition, application.auto_id_selected_run_path,
                                       (self.base.item,), application.auto_id_active_typed[1], record,
                                       application.auto_id_evaluated_fingerprint)
        with mock.patch.object(export_module.tempfile, "mkstemp", side_effect=OSError("no space for temporary")):
            with self.assertRaises(ExportRefusal) as caught:
                write_export(export, self.out / "service.json", ())
        self.assertIs(caught.exception.code, ExportRefusalCode.WRITE_FAILED)
        self.assertFalse((self.out / "service.json").exists())

    def test_33_undeterminable_protected_roots_refuse(self):
        import material_identification_ui as ui

        application, _ = self.evaluated()
        target = self.out / "unprotected.json"
        with mock.patch.object(adapter, "campaign_specimens", return_value=(self.base.item,)), \
                mock.patch("domain.experiment_fixture.fixture_roots_from_environment",
                           side_effect=RuntimeError("store configuration unreadable")):
            self.assertIsNone(ui.export_auto_id_evidence(application, str(target)))
        self.assertIn("No export: DESTINATION_REFUSED", self.message(application))
        self.assertFalse(target.exists())
        self.assertEqual(list(self.out.iterdir()), [])
        self.assertIsNotNone(application.auto_id_active_evaluation)  # a configuration problem changes no verdict
        export = build_evidence_export(self.base.definition, application.auto_id_selected_run_path,
                                       (self.base.item,), application.auto_id_active_typed[1],
                                       application.scientific_readiness_record,
                                       application.auto_id_evaluated_fingerprint)
        with self.assertRaises(ExportRefusal) as caught:  # an undetermined root is never ignored
            write_export(export, target, (None,))
        self.assertIs(caught.exception.code, ExportRefusalCode.DESTINATION)
        self.assertFalse(target.exists())
        self.assertIsNotNone(self.export(application, name="configured.json"))  # unconfigured stores are not an error


def tearDownModule():
    if _Fixture._directory is not None:
        _Fixture._directory.cleanup()
        _Fixture._directory = None
        _Fixture._runs = {}
    directory = backend_tests.MaterialPathTests._directory
    if directory is not None:
        directory.cleanup()
        backend_tests.MaterialPathTests._directory = None
        backend_tests.MaterialPathTests._runs = {}


if __name__ == "__main__":
    unittest.main()
