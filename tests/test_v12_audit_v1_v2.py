"""SPEC v1.2 external audit corrections V1 / V2 (reporting only; no new scientific computation).

V1: the material verdict is shown first and unchanged, then the calibration verdict (SPEC v1.2 §1). It is read from
the stored backend record only; a calibration run's companion material verdict is not yet computed (D-080, V12-I7):
it is shown as MATERIAL_VERDICT_NOT_COMPUTED and is
never replaced by the calibration result.
V2: the specimen calibration output record carries the statistical_sd and the leave-one-FIT-family-out status that the
gate judged, copied from the bound M5 evidence; anything missing stays NOT_AVAILABLE.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.campaign_definition import load_campaign_definition  # noqa: E402
from domain.experiment_fixture import fixture_roots_from_environment  # noqa: E402
from domain.identification_run import canonical_hash  # noqa: E402
from services.auto_id_wizard import material_verdict, uncertainty_breakdown, verdict_summary  # noqa: E402
from services.calibration_material_preview import PreviewState, calibration_material_preview  # noqa: E402
from services.campaign_scientific_backend import (  # noqa: E402
    judge_campaign_run,
    judge_specimen_calibration,
    readiness_presentation,
)
from services.specimen_calibration_output import SCHEMA, _statistical_report  # noqa: E402
import test_v12_i6_backend_integration as backend_tests  # noqa: E402

CAMPAIGNS = ROOT / "docs" / "auto_id" / "campaigns"
MATERIAL_ROWS = ("Material verdict — question", "Material verdict — formal output", "Material verdict — status")
# historical records (SPEC v1.2 §11): canonical hashes at main e022e76, before the V1 / V2 correction
HISTORICAL = {
    "M7_RUN_A.campaign.json": "0a21ad0567901034b521b822b52f0c29944e96394f3692e1a8ebcd7ccd8d2ccf",
    "M7_RUN_A.result.json": "82501b35c4effc0fd829d40d6e3aaef105d5a70cc8e8a3b0ba306b9caa66c5c2",
    "M7_RUN_B.campaign.json": "7c1f5db24fa9c4f4e90c82ca802c6dae22cbe5c7ec9e2989e63e439f678540e5",
    "M7_RUN_B.result.json": "8a9264eca72827889042fb5430ed057f9d44ebb9305d0b10db9c28d433a2b2de",
    "M7_CLOSURE.json": "e015a935e34301223a3c0e9f70464d4a72d8952292f779fc9353f9a20e702d24",
}
# backend readiness record hashes of the archived runs at main e022e76 (material path; unchanged by V1 / V2)
ARCHIVED_RECORD_HASH = {
    "M7_RUN_A": ("m7-run-a", "42917c2ebb2fe943a089ae018bef989fe72d9ded0c50e89d29a6e8792a77c6a2"),
    "M7_RUN_B": ("m7-run-b", "af512444f695505040c1dd4368af7e07d79c898043a0f042f105de840c478a60"),
}


class _Runs(unittest.TestCase):
    def judged(self, name):
        run = backend_tests._Runs.run_of(name)
        return judge_campaign_run(run.definition, [run.item], run.evidence)

    def material(self, shift):
        run = backend_tests.MaterialPathTests.material_run(self, (0.02, shift))
        return run, judge_campaign_run(run.definition, run.specimens, run.evidence)


# ----------------------------------------------------------------------------- V1 material verdict first

class MaterialVerdictFirstTests(_Runs):
    def test_material_verdict_cannot_be_hidden_by_a_calibration_result(self):
        for name, expected in (("base", "RELEASED"), ("imprecise", "REFUSED")):
            record = self.judged(name).to_dict()
            self.assertEqual(record["status"], expected)
            rows = readiness_presentation(record)
            self.assertEqual(tuple(label for label, _ in rows[:4]), MATERIAL_ROWS + ("Calibration verdict",))
            values = dict(rows)
            self.assertTrue(values["Material verdict — status"].startswith(
                "MATERIAL_VERDICT_NOT_COMPUTED — known temporary SPEC v1.2 §1 non-conformance (D-080); companion "
                "material verdict pending V12-I7; no material property"))
            self.assertIn("companion material verdict", values["Material verdict — question"])
            self.assertNotIn("D-078", " ".join(values[label] for label in MATERIAL_ROWS))
            self.assertEqual(values["Material verdict — formal output"],
                             "NOT_AVAILABLE (MATERIAL_VERDICT_NOT_COMPUTED)")
            self.assertTrue(values["Calibration verdict"].startswith(expected))
            lines = verdict_summary(record)
            first = next(i for i, line in enumerate(lines) if line.startswith("Material verdict — question"))
            calibration = next(i for i, line in enumerate(lines) if line.startswith("Calibration verdict"))
            released = next(i for i, line in enumerate(lines) if line.startswith(("Released", "Backend status")))
            self.assertLess(first, calibration)
            self.assertLess(calibration, released)
        # a forged record cannot present a material release under the calibration question
        forged = dict(self.judged("base").to_dict(), material_formal_output={"status": "VALUES_RELEASED",
                                                                            "released_values": {"E_in_plane_mpa": 1.0}})
        self.assertTrue(dict(material_verdict(forged))["Material verdict — status"].startswith(
            "MATERIAL_VERDICT_NOT_COMPUTED"))

    def test_the_material_path_is_not_run_for_a_calibration_definition(self):
        # V1 shows what the backend recorded; it never re-runs the material question on a calibration campaign
        record = self.judged("base").to_dict()
        self.assertIsNone(record["material_formal_output"])
        self.assertIsNone(record["material_family_consistency"])

    def test_gui_shows_the_material_verdict_first(self):
        from test_material_identification_ui import _ApplicationHarness

        application = _ApplicationHarness()._application()
        application.scientific_readiness_record = self.judged("base").to_dict()
        application._refresh_material_identification_pages()
        table = application.material_scientific_readiness_table
        labels = [table.items[key][0] for key in table.get_children()]
        self.assertEqual(tuple(labels[:4]), MATERIAL_ROWS + ("Calibration verdict",))
        summary = application.material_scientific_readiness_summary_label.kwargs["text"].splitlines()
        self.assertTrue(summary[2].startswith("Material verdict — question"))


class NoGlobalValueIsNeverACalibrationTests(_Runs):
    def test_no_global_parameter_value_does_not_become_a_calibration_release(self):
        run, readiness = self.material(1.12)  # SPEC §13 family consistency FAIL
        record = readiness.to_dict()
        self.assertEqual(record["material_formal_output"]["status"], "NO_GLOBAL_PARAMETER_VALUE")
        values = dict(readiness_presentation(record))
        self.assertTrue(values["Material verdict — status"].startswith(
            "REFUSED: NO_GLOBAL_PARAMETER_VALUE; SPEC §13 family consistency FAIL; no global material property"))
        self.assertIn("FAMILY_CONSISTENCY_FAIL", values["Material verdict — status"])
        self.assertTrue(values["Calibration verdict"].startswith("not applicable"))
        self.assertEqual(values["Released calibration"], "none released")
        self.assertIsNone(record["released_calibration_parameters"])
        self.assertFalse(record["inp_fragment_available"])
        self.assertIsNone(readiness.calibration_record)
        self.assertIs(calibration_material_preview(readiness, {}).state, PreviewState.NOT_AVAILABLE_FOR_SELECTION)
        refused = judge_specimen_calibration(run.definition, run.specimens, run.evidence)  # never a fallback
        self.assertEqual(refused.status.value, "NOT_READY")
        self.assertEqual(refused.refusal_codes, ("WRONG_SCIENTIFIC_QUESTION",))
        forged = dict(record, released_calibration_parameters={"E_in_plane_mpa": {"value": 1.0, "unit": "MPa"}})
        self.assertEqual(dict(readiness_presentation(forged))["Released calibration"], "none released")
        summary = "\n".join(verdict_summary(forged))
        self.assertIn("Material verdict — status: REFUSED: NO_GLOBAL_PARAMETER_VALUE", summary)
        self.assertIn("Released: no value released", summary)

    def test_material_values_released_is_reported_as_material_only(self):
        _, readiness = self.material(1.0)
        values = dict(readiness_presentation(readiness.to_dict()))
        self.assertTrue(values["Material verdict — status"].startswith("MATERIAL_VALUES_RELEASED: E_in_plane_mpa"))
        self.assertTrue(values["Calibration verdict"].startswith("not applicable"))


# ----------------------------------------------------------------------------- V2 calibration uncertainty record

class CalibrationUncertaintyRecordTests(_Runs):
    def test_statistical_sd_and_loo_status_are_copied_from_the_bound_evidence(self):
        readiness = self.judged("base")
        record = readiness.calibration_record
        document = record.to_dict()
        self.assertEqual(document["schema"], SCHEMA)
        binding = record.identity["evidence_binding"]
        self.assertEqual(document["statistical_sd"]["record_hash"], binding["statistical_sd_record_hash"])
        self.assertEqual(document["statistical_sd"]["status"], "AVAILABLE")
        self.assertEqual(sorted(document["statistical_sd"]["statistical_sd_ln"]), ["E_in_plane_mpa"])
        self.assertGreater(document["statistical_sd"]["statistical_sd_ln"]["E_in_plane_mpa"], 0.0)
        self.assertEqual(document["model_form_robustness"]["record_hash"], binding["model_form_robustness_record_hash"])
        self.assertEqual(document["model_form_robustness"]["status"], "AVAILABLE_COMPLETE_LOO")
        self.assertEqual(readiness.to_dict()["calibration"]["statistical_sd"], document["statistical_sd"])

    def test_missing_statistical_sd_stays_not_available(self):
        report = _statistical_report(None, ("E_in_plane_mpa", "G12_mpa"))
        self.assertEqual(report["status"], "NOT_AVAILABLE")
        self.assertEqual(report["statistical_sd_ln"], {"E_in_plane_mpa": None, "G12_mpa": None})
        record = self.judged("rank").calibration_record.to_dict()  # rank-deficient M5 system
        self.assertEqual(record["statistical_sd"]["status"], "REFUSED_RANK_DEFICIENT")
        self.assertEqual(record["statistical_sd"]["statistical_sd_ln"], {"E_in_plane_mpa": None, "G12_mpa": None})
        rows = {(s, i): v for s, i, v in uncertainty_breakdown(self.judged("rank").to_dict())}
        for name in ("E_in_plane_mpa", "G12_mpa"):
            value = rows[("B · Statistical uncertainty", f"statistical_sd · {name}")]
            self.assertTrue(value.startswith("NOT_AVAILABLE — REFUSED_RANK_DEFICIENT"), value)
        older = copy.deepcopy(self.judged("base").to_dict())  # a record from before the correction
        older["calibration"].pop("statistical_sd")
        rows = {(s, i): v for s, i, v in uncertainty_breakdown(older)}
        self.assertEqual(rows[("B · Statistical uncertainty", "statistical_sd · E_in_plane_mpa")],
                         "NOT_AVAILABLE — not recorded in this calibration output record (schema before audit V2)")

    def test_incomplete_loo_gives_no_artificial_range(self):
        readiness = self.judged("one_family")
        record = readiness.calibration_record.to_dict()
        robustness = record["model_form_robustness"]
        self.assertEqual(robustness["status"], "UNAVAILABLE_INCOMPLETE_LOO")
        self.assertTrue(robustness["reasons"])
        self.assertFalse({"half_range_ln", "range_ln", "min_shift_ln", "max_shift_ln"} & set(robustness))
        self.assertIsNone(record["precision"]["parameters"]["E_in_plane_mpa"]["model_form_half_range_ln"])
        self.assertIsNone(record["precision"]["parameters"]["E_in_plane_mpa"]["conservative_uncertainty_ln"])
        rows = {(s, i): v for s, i, v in uncertainty_breakdown(readiness.to_dict())}
        self.assertTrue(rows[("D · Model-form robustness", "Leave-one-FIT-family-out status")]
                        .startswith("UNAVAILABLE_INCOMPLETE_LOO"))
        self.assertEqual(rows[("D · Model-form robustness", "model_form_half_range · E_in_plane_mpa")],
                         "NOT_AVAILABLE — incomplete leave-one-FIT-family-out: no model-form interval")


# ----------------------------------------------------------------------------- historical records unchanged

class HistoricalRecordTests(unittest.TestCase):
    def test_run_a_run_b_records_are_unchanged(self):
        for name, expected in HISTORICAL.items():
            with self.subTest(record=name):
                document = json.loads((CAMPAIGNS / name).read_text(encoding="utf-8"))
                self.assertEqual(canonical_hash(document), expected)
        for name in ("M7_RUN_A", "M7_RUN_B"):
            self.assertEqual(load_campaign_definition(CAMPAIGNS / f"{name}.campaign.json").campaign_hash,
                             HISTORICAL[f"{name}.campaign.json"])

    def test_archived_backend_records_keep_their_hashes(self):
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
                self.assertEqual(evaluation.readiness.status.value, "REFUSED")
                self.assertEqual(dict(material_verdict(evaluation.readiness.to_dict()))["Material verdict — formal output"],
                                 "NO_GLOBAL_PARAMETER_VALUE")


def tearDownModule():
    backend_tests.tearDownModule()
    directory = backend_tests.MaterialPathTests._directory
    if directory is not None:
        directory.cleanup()
        backend_tests.MaterialPathTests._directory = None
        backend_tests.MaterialPathTests._runs = {}
    backend_tests._Runs._directory = None
    backend_tests._Runs._runs = {}


if __name__ == "__main__":
    unittest.main()
