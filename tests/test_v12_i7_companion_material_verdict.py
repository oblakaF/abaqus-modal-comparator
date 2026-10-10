"""V12-I7.1 — companion material verdict of a specimen calibration run (D-080; SPEC v1.2 §1).

The companion verdict is the accepted M7 material report judged read-only on the calibration run's existing journals.
It is a separate record with its own hash: it never enters the calibration gate, output or release, never changes
the declared scientific question and is never a fallback. Synthetic runs use the M4.6 fake solver; nothing is solved.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
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
from services import campaign_scientific_backend as backend  # noqa: E402
from services.auto_id_wizard import material_verdict, verdict_summary  # noqa: E402
from services.campaign_lm_provenance import journal_document  # noqa: E402
from services.campaign_scientific_backend import (  # noqa: E402
    COMPANION_LABELS,
    COMPANION_ROLE,
    COMPANION_SCHEMA,
    judge_campaign_run,
    judge_specimen_calibration,
    readiness_presentation,
)
from services.identification_campaign_run import build_campaign_report, campaign_report_unchecked  # noqa: E402
from test_v12_i1_campaign_question import calibration_definition  # noqa: E402
import test_v12_i6_backend_integration as backend_tests  # noqa: E402
from v12_i6_support import with_journal  # noqa: E402

CAMPAIGNS = ROOT / "docs" / "auto_id" / "campaigns"
CALIBRATION_FIELDS = {"calibration", "calibration_parameters", "released_calibration_parameters", "precision",
                      "gate_record_hash", "diagnostic_candidate", "diagnostic_optimizer_candidate",
                      "inp_fragment_available", "governed_rows"}
HISTORICAL = {  # canonical hashes at main 8dc6955 (unchanged by V12-I7)
    "M7_RUN_A.campaign.json": "0a21ad0567901034b521b822b52f0c29944e96394f3692e1a8ebcd7ccd8d2ccf",
    "M7_RUN_A.result.json": "82501b35c4effc0fd829d40d6e3aaef105d5a70cc8e8a3b0ba306b9caa66c5c2",
    "M7_RUN_B.campaign.json": "7c1f5db24fa9c4f4e90c82ca802c6dae22cbe5c7ec9e2989e63e439f678540e5",
    "M7_RUN_B.result.json": "8a9264eca72827889042fb5430ed057f9d44ebb9305d0b10db9c28d433a2b2de",
}
ARCHIVED_RECORD_HASH = {  # backend readiness record hashes of the archived runs (material path; unchanged)
    "M7_RUN_A": ("m7-run-a", "42917c2ebb2fe943a089ae018bef989fe72d9ded0c50e89d29a6e8792a77c6a2"),
    "M7_RUN_B": ("m7-run-b", "af512444f695505040c1dd4368af7e07d79c898043a0f042f105de840c478a60"),
}


class _Fixture(unittest.TestCase):
    _directory = None
    _runs: dict = {}

    @classmethod
    def setUpClass(cls):
        if _Fixture._directory is None:  # genuine synthetic runs in this module's own directory
            _Fixture._directory = tempfile.TemporaryDirectory()
            tmp = Path(_Fixture._directory.name)
            _Fixture._runs = {name: backend_tests._SCENARIOS[name](tmp / name)
                              for name in ("base", "imprecise", "one_family", "rank")}

    def run_of(self, name):
        return _Fixture._runs[name]

    def judged(self, name, evidence=None):
        run = self.run_of(name)
        return judge_campaign_run(run.definition, [run.item], run.evidence if evidence is None else evidence)

    def material(self, shift):
        run = backend_tests.MaterialPathTests.material_run(self, (0.02, shift))
        return run, judge_campaign_run(run.definition, run.specimens, run.evidence)


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


# ----------------------------------------------------------------------------- the companion verdict

class CompanionVerdictTests(_Fixture):
    def assert_companion(self, record, status):
        companion = record["companion_material_verdict"]
        self.assertEqual((companion["schema"], companion["role"]), (COMPANION_SCHEMA, COMPANION_ROLE))
        self.assertEqual(companion["labels"], list(COMPANION_LABELS))
        self.assertEqual(companion["question"], "MATERIAL_IDENTIFICATION")
        self.assertEqual(companion["status"], status)
        body = {k: v for k, v in companion.items() if k != "record_hash"}
        self.assertEqual(companion["record_hash"], canonical_hash(body))
        provenance = companion["provenance"]
        self.assertEqual(provenance["campaign_hash"], record["campaign"]["campaign_hash"])
        self.assertEqual(provenance["run_hash"], record["campaign"]["run_hash"])
        self.assertIn("existing journalled evidence", provenance["source"])
        self.assertEqual((provenance["abaqus_solves"], provenance["lm_executions"],
                          provenance["new_journal_entries"]), (0, 0, 0))
        return companion

    def test_calibration_released_with_companion_no_global_parameter_value(self):
        readiness = self.judged("base")
        record = readiness.to_dict()
        self.assertEqual(record["status"], "RELEASED")
        companion = self.assert_companion(record, "NO_GLOBAL_PARAMETER_VALUE")
        self.assertEqual(companion["formal_output"]["status"], "NO_GLOBAL_PARAMETER_VALUE")
        self.assertEqual(companion["formal_output"]["released_values"], {})
        self.assertEqual(companion["family_consistency"], "NOT_EVALUABLE")  # one physical specimen (SPEC §6)
        self.assertEqual(companion["m5_verdicts"]["E_in_plane_mpa"]["verdict"], "NOT_IDENTIFIABLE")
        self.assertEqual(companion["material_claim"], "NO_MATERIAL_PROPERTY_CLAIM")
        self.assertIsNotNone(companion["provenance"]["material_report_hash"])
        rows = readiness_presentation(record)
        self.assertEqual([label for label, _ in rows[:4]], ["Material verdict — question",
                                                           "Material verdict — formal output",
                                                           "Material verdict — status", "Calibration verdict"])
        values = dict(rows)
        self.assertTrue(values["Material verdict — status"].startswith(
            "REFUSED: NO_GLOBAL_PARAMETER_VALUE; SPEC §13 family consistency NOT_EVALUABLE; no global material "
            "property"))
        self.assertIn(companion["record_hash"][:12], values["Material verdict — formal output"])
        self.assertTrue(values["Calibration verdict"].startswith("RELEASED"))
        lines = verdict_summary(record)
        material = next(i for i, l in enumerate(lines) if l.startswith("Material verdict — status: REFUSED"))
        calibration = next(i for i, l in enumerate(lines) if l.startswith("Calibration verdict: RELEASED"))
        self.assertLess(material, calibration)

    def test_calibration_refused_with_companion(self):
        for name in ("imprecise", "one_family", "rank"):  # rank: a RUN_B-typed calibration definition
            with self.subTest(run=name):
                record = self.judged(name).to_dict()
                self.assertEqual(record["status"], "REFUSED")
                companion = self.assert_companion(record, "NO_GLOBAL_PARAMETER_VALUE")
                self.assertTrue(companion["family_consistency"].startswith("NOT_EVALUABLE"))  # rank: _RANK_DEFICIENT

    def test_not_ready_gives_companion_not_available(self):
        run = self.run_of("base")
        readiness = self.judged("base", with_journal(run.evidence, pipeline_journals={}))
        record = readiness.to_dict()
        self.assertEqual(record["status"], "NOT_READY")
        self.assertEqual(readiness.refusal_codes, ("LM_HISTORY_MISSING",))
        companion = self.assert_companion(record, "NOT_AVAILABLE")
        self.assertIsNone(companion["formal_output"])
        self.assertIn("LM_HISTORY_MISSING", companion["reasons"][0])
        values = dict(readiness_presentation(record))
        self.assertTrue(values["Material verdict — status"].startswith("NOT_AVAILABLE — run evidence not verified"))
        self.assertTrue(values["Calibration verdict"].startswith("NOT_READY"))

    def test_companion_is_deterministic(self):
        first, second = self.judged("base").to_dict(), self.judged("base").to_dict()
        self.assertEqual(first["companion_material_verdict"], second["companion_material_verdict"])
        text = json.dumps(first["companion_material_verdict"], sort_keys=True)
        self.assertEqual(json.loads(text), first["companion_material_verdict"])


# ----------------------------------------------------------------------------- separation from the calibration

class SeparationTests(_Fixture):
    def test_companion_does_not_influence_the_calibration(self):
        for name in ("base", "imprecise"):
            with self.subTest(run=name):
                genuine = self.judged(name)
                fake = {"formal_output": {"status": "VALUES_RELEASED", "released_values": {"E_in_plane_mpa": 1.0},
                                          "blockers": [], "rule": "fake"},
                        "material_claim": "IDENTIFIED_MATERIAL_PROPERTY", "family_consistency": {"status": "PASS"},
                        "m5_verdict": {"verdicts": {}}, "uncertainty_basis": None}
                for patch in (mock.patch.object(backend, "campaign_report_unchecked", return_value=fake),
                              mock.patch.object(backend, "campaign_report_unchecked",
                                                side_effect=RuntimeError("companion failure"))):
                    with patch:
                        other = self.judged(name)
                    self.assertEqual(other.status, genuine.status)
                    self.assertEqual(other.refusal_codes, genuine.refusal_codes)
                    self.assertEqual(other.calibration_record.to_dict(), genuine.calibration_record.to_dict())
                    self.assertEqual(other.calibration_record.gate_record_hash,
                                     genuine.calibration_record.gate_record_hash)
                    record = other.to_dict()
                    self.assertEqual(record["released_calibration_parameters"],
                                     genuine.to_dict()["released_calibration_parameters"])
                    self.assertIsNone(record["material_formal_output"])  # never a material release of this run
                    self.assertNotEqual(record["status"], "MATERIAL_VALUES_RELEASED")
                    self.assertIn(record["companion_material_verdict"]["status"], ("VALUES_RELEASED", "NOT_AVAILABLE"))

    def test_companion_contains_no_calibration_fields(self):
        companion = self.judged("base").to_dict()["companion_material_verdict"]
        self.assertFalse(CALIBRATION_FIELDS & set(companion))
        self.assertFalse(CALIBRATION_FIELDS & set(companion["provenance"]))
        text = json.dumps(companion)
        for token in ("calibration_parameters", "gate_record_hash", "CAL_", "inp_fragment"):
            self.assertNotIn(token, text)

    def test_scientific_question_and_campaign_hash_do_not_change(self):
        run = self.run_of("base")
        definition_before = copy.deepcopy(run.definition.canonical)
        hash_before = run.definition.campaign_hash
        record = self.judged("base").to_dict()
        self.assertEqual(record["scientific_question"], "SPECIMEN_ENGINEERING_CALIBRATION")
        self.assertEqual(run.definition.scientific_question, "SPECIMEN_ENGINEERING_CALIBRATION")
        self.assertEqual(run.definition.canonical, definition_before)
        self.assertEqual(run.definition.campaign_hash, hash_before)
        self.assertEqual(parse_campaign_definition(calibration_definition()).campaign_hash, hash_before)
        self.assertEqual(record["campaign"]["campaign_hash"], hash_before)
        self.assertEqual(record["companion_material_verdict"]["provenance"]["campaign_hash"], hash_before)

    def test_public_material_report_still_refuses_a_calibration_definition(self):
        run = self.run_of("base")
        _, _, entries = journal_document(run.evidence.campaign_journal, "campaign")
        evaluations = [dict(e["record"]) for e in entries if e.get("kind") == "evaluation"]
        with self.assertRaises(CalibrationNotImplementedRefusal):
            build_campaign_report(run.definition, [run.item], evaluations, {"status": "CONVERGED"})
        with self.assertRaises(CalibrationNotImplementedRefusal):
            run.definition.require_executable()
        users = sorted(p.relative_to(ROOT).as_posix() for folder in ("src", "tools") for p in (ROOT / folder).rglob("*.py")
                       if "campaign_report_unchecked" in p.read_text(encoding="utf-8"))
        self.assertEqual(users, ["src/services/campaign_scientific_backend.py",
                                 "src/services/identification_campaign_run.py"])

    def test_the_m7_report_is_unchanged_by_the_split(self):
        run, readiness = self.material(1.12)
        lm = backend._lm(run.definition, run.specimens, run.evidence)
        _, _, entries = journal_document(run.evidence.campaign_journal, "campaign")
        evaluations = [dict(e["record"]) for e in entries if e.get("kind") == "evaluation"]
        public = build_campaign_report(run.definition, run.specimens, evaluations, dict(lm.result))
        unchecked = campaign_report_unchecked(run.definition, run.specimens, evaluations, dict(lm.result))
        self.assertEqual(canonical_hash(public), canonical_hash(unchecked))
        self.assertEqual(canonical_hash(public), canonical_hash(readiness.material_report))


# ----------------------------------------------------------------------------- no fallback, history unchanged

class NoFallbackTests(_Fixture):
    def test_material_refusal_never_becomes_a_calibration_and_has_no_companion(self):
        run, readiness = self.material(1.12)
        record = readiness.to_dict()
        self.assertEqual(record["status"], "REFUSED")
        self.assertNotIn("companion_material_verdict", record)  # material records are unchanged
        self.assertIsNone(readiness.calibration_record)
        self.assertIsNone(record["released_calibration_parameters"])
        refused = judge_specimen_calibration(run.definition, run.specimens, run.evidence)
        self.assertEqual(refused.refusal_codes, ("WRONG_SCIENTIFIC_QUESTION",))
        self.assertNotIn("companion_material_verdict", refused.to_dict())
        with self.assertRaises(ValueError):  # a companion belongs to a calibration run only
            backend._companion_material_verdict(run.definition, run.specimens, run.evidence, None)

    def test_missing_companion_is_shown_as_not_computed_never_inferred(self):
        record = self.judged("base").to_dict()
        old = {k: v for k, v in record.items() if k != "companion_material_verdict"}  # a record before V12-I7
        values = dict(material_verdict(old))
        self.assertTrue(values["Material verdict — status"].startswith(
            "MATERIAL_VERDICT_NOT_COMPUTED — known temporary SPEC v1.2 §1 non-conformance (D-080); companion "
            "material verdict pending V12-I7"))
        self.assertEqual(values["Material verdict — formal output"], "NOT_AVAILABLE (MATERIAL_VERDICT_NOT_COMPUTED)")
        self.assertTrue(values["Calibration verdict"].startswith("RELEASED"))  # the calibration stays as recorded

    def test_no_solver_or_lm_runs_while_judging(self):
        from services import identification_step

        refuse = mock.Mock(side_effect=AssertionError("forbidden execution"))
        with mock.patch.object(subprocess, "Popen", refuse), mock.patch.object(subprocess, "run", refuse), \
                mock.patch.object(os, "system", refuse), \
                mock.patch.object(identification_step, "run_bounded_lm", refuse):
            record = self.judged("base").to_dict()
        refuse.assert_not_called()
        self.assertEqual(record["companion_material_verdict"]["status"], "NO_GLOBAL_PARAMETER_VALUE")

    def test_run_a_run_b_records_are_unchanged(self):
        for name, expected in HISTORICAL.items():
            with self.subTest(record=name):
                self.assertEqual(canonical_hash(json.loads((CAMPAIGNS / name).read_text(encoding="utf-8"))), expected)

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
                self.assertNotIn("companion_material_verdict", evaluation.readiness.to_dict())


if __name__ == "__main__":
    unittest.main()
