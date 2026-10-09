"""V12-I1 — SPEC v1.2 campaign question and τ_mf: schema, identity and refusals only (D-078; no Abaqus).

A v1.2 campaign definition (``auto-id/identification-campaign/v1.2``) must declare its scientific question and τ_mf
explicitly; both are identity-bound.  Historical v1 definitions keep their exact identities and acquire neither field.
τ_mf has no numerical effect yet (V12-I2), and calibration execution is refused until V12-I3 exists.
"""

from __future__ import annotations

import ast
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.campaign_definition import (
    CALIBRATION_NOT_IMPLEMENTED,
    CAMPAIGN_SCHEMA,
    CAMPAIGN_SCHEMA_V1_2,
    MATERIAL_IDENTIFICATION,
    SPECIMEN_ENGINEERING_CALIBRATION,
    TAU_MF_MAXIMUM,
    CalibrationNotImplementedRefusal,
    CampaignDefinitionError,
    RunGateRefusal,
    load_campaign_definition,
    parse_campaign_definition,
)
from domain.forward_model_manifest import canonical_hash
from m4_6_support import FakeExtractor, FakeSolver
from services.identification_campaign_run import (
    CampaignRun,
    CampaignRunConfig,
    build_campaign_report,
    campaign_run_identity,
    prepare_run_manifest,
    row_sigma,
)
from test_m7_campaign import synthetic_definition, synthetic_specimen


CAMPAIGNS = ROOT / "docs" / "auto_id" / "campaigns"
RUN_A_CAMPAIGN_HASH = "0a21ad0567901034b521b822b52f0c29944e96394f3692e1a8ebcd7ccd8d2ccf"
RUN_B_CAMPAIGN_HASH = "7c1f5db24fa9c4f4e90c82ca802c6dae22cbe5c7ec9e2989e63e439f678540e5"
# The v1.1 synthetic campaign as computed before V12-I1 (main 61b5016): identity must not move.
SYNTHETIC_V1_CAMPAIGN_HASH = "d869796d51a84d4d2fa0b90ab68c480acb8202c4a23086bf4e2f5a1ea4a0461e"
SYNTHETIC_V1_RUN_HASH = "698228cebd5b3de81bde2a78c8ef61450db358076a9309a7464ae6aa2f1b0ab5"


def v12_definition(question=MATERIAL_IDENTIFICATION, tau_mf=0.02, **changes) -> dict:
    data = synthetic_definition()
    data.update(schema=CAMPAIGN_SCHEMA_V1_2, scientific_question=question, tau_mf=tau_mf)
    data.update(changes)
    return data


def without(data: dict, key: str) -> dict:
    data = dict(data)
    del data[key]
    return data


class _Campaigns(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.tmp = Path(self._directory.name)

    def tearDown(self):
        self._directory.cleanup()

    def specimens(self, definition, tag: str):
        items, roots = [], {}
        for label in ("A", "B"):
            item, store = synthetic_specimen(definition, label, self.tmp / tag)
            items.append(item)
            roots["synthetic"] = store
        return items, roots

    def execute(self, definition, tag: str):
        items, roots = self.specimens(definition, tag)
        solver = FakeSolver()
        config = CampaignRunConfig(self.tmp / tag / "runs", roots, "abq2024.bat", solver, FakeExtractor(), {},
                                   "m" * 64)
        campaign = CampaignRun(definition, items, "m" * 64, config)
        return campaign, campaign.run()


class HistoricalV11Tests(_Campaigns):
    def test_historical_run_a_and_run_b_keep_their_identities(self):
        for name, expected in (("M7_RUN_A", RUN_A_CAMPAIGN_HASH), ("M7_RUN_B", RUN_B_CAMPAIGN_HASH)):
            definition = load_campaign_definition(CAMPAIGNS / f"{name}.campaign.json")
            record = json.loads((CAMPAIGNS / f"{name}.result.json").read_text(encoding="utf-8"))
            with self.subTest(campaign=name):
                self.assertEqual(definition.schema, CAMPAIGN_SCHEMA)
                self.assertEqual(definition.campaign_hash, expected)
                self.assertEqual(record["campaign_hash"], expected)
                self.assertIsNone(definition.scientific_question)  # no implicit question
                self.assertIsNone(definition.tau_mf)  # no implicit τ_mf
                self.assertFalse({"scientific_question", "tau_mf"} & set(definition.canonical))
        load_campaign_definition(CAMPAIGNS / "M7_RUN_A.campaign.json").require_executable()
        load_campaign_definition(CAMPAIGNS / "M7_RUN_B.campaign.json").require_executable()  # D-072 gate

    def test_a_v1_definition_cannot_carry_v1_2_fields(self):
        for key, value in (("scientific_question", MATERIAL_IDENTIFICATION), ("tau_mf", 0.02)):
            with self.subTest(key=key), self.assertRaisesRegex(CampaignDefinitionError, "unknown"):
                parse_campaign_definition(dict(synthetic_definition(), **{key: value}))

    def test_historical_v1_execution_is_unchanged(self):
        definition = parse_campaign_definition(synthetic_definition())
        self.assertEqual(definition.campaign_hash, SYNTHETIC_V1_CAMPAIGN_HASH)
        campaign, result = self.execute(definition, "v1")
        self.assertEqual(campaign.run_hash, SYNTHETIC_V1_RUN_HASH)
        self.assertEqual(result["status"], "CONVERGED")
        self.assertNotIn("scientific_question", campaign.identity)
        with self.assertRaises(RunGateRefusal):  # the RUN_B gate is unchanged
            parse_campaign_definition(synthetic_definition(
                run_type="RUN_B", fitted_parameters=["E_in_plane_mpa", "G12_mpa"], fixed_parameters={},
                start={"E_in_plane_mpa": 52000.0, "G12_mpa": 4500.0},
                bounds={"E_in_plane_mpa": [26000.0, 104000.0], "G12_mpa": [2250.0, 9000.0]},
                engineering_plausibility={})).require_executable()


class V12SchemaTests(unittest.TestCase):
    def test_valid_v1_2_definitions_parse(self):
        for question in (MATERIAL_IDENTIFICATION, SPECIMEN_ENGINEERING_CALIBRATION):
            definition = parse_campaign_definition(v12_definition(question))
            with self.subTest(question=question):
                self.assertEqual((definition.schema, definition.scientific_question, definition.tau_mf),
                                 (CAMPAIGN_SCHEMA_V1_2, question, 0.02))
                self.assertEqual((definition.canonical["scientific_question"], definition.canonical["tau_mf"]),
                                 (question, 0.02))
                self.assertEqual(definition.canonical["schema"], CAMPAIGN_SCHEMA_V1_2)

    def test_tau_mf_range(self):
        self.assertEqual(TAU_MF_MAXIMUM, 0.02)
        for accepted in (0.02, 0.0199, 0.01, 0.005, 1e-6):
            with self.subTest(tau_mf=accepted):
                self.assertEqual(parse_campaign_definition(v12_definition(tau_mf=accepted)).tau_mf, accepted)
        for rejected in (0.0200001, 0.03, 1, 0, 0.0, -0.01, math.nan, math.inf, -math.inf, True, False, "0.02",
                         None, [0.02]):
            with self.subTest(tau_mf=rejected), self.assertRaisesRegex(CampaignDefinitionError, "tau_mf"):
                parse_campaign_definition(v12_definition(tau_mf=rejected))

    def test_tau_mf_from_json_nan_and_infinity_is_rejected(self):
        for token in ("NaN", "Infinity", "-Infinity"):
            text = json.dumps(v12_definition()).replace('"tau_mf": 0.02', f'"tau_mf": {token}')
            with self.subTest(token=token), self.assertRaisesRegex(CampaignDefinitionError, "tau_mf"):
                parse_campaign_definition(json.loads(text))

    def test_question_and_tau_mf_are_mandatory_and_never_inferred(self):
        for key in ("scientific_question", "tau_mf"):
            with self.subTest(missing=key), self.assertRaisesRegex(CampaignDefinitionError, f"missing.*{key}"):
                parse_campaign_definition(without(v12_definition(), key))
        with self.assertRaisesRegex(CampaignDefinitionError, "missing"):
            parse_campaign_definition(without(without(v12_definition(), "tau_mf"), "scientific_question"))

    def test_unknown_question_and_unexpected_keys_are_rejected(self):
        for question in ("MATERIAL_CALIBRATION", "material_identification", "", None, 1, True,
                         [MATERIAL_IDENTIFICATION]):
            with self.subTest(question=question), self.assertRaisesRegex(CampaignDefinitionError,
                                                                         "scientific_question"):
                parse_campaign_definition(v12_definition(question))
        with self.assertRaisesRegex(CampaignDefinitionError, "unknown"):
            parse_campaign_definition(v12_definition(tau_mf_source="campaign"))
        with self.assertRaisesRegex(CampaignDefinitionError, "schema"):
            parse_campaign_definition(v12_definition(schema="auto-id/identification-campaign/v2"))

    def test_canonical_serialisation_is_deterministic(self):
        first = parse_campaign_definition(v12_definition())
        reordered = dict(reversed(list(v12_definition().items())))
        second = parse_campaign_definition(json.loads(json.dumps(reordered)))
        self.assertEqual(first.campaign_hash, second.campaign_hash)
        self.assertEqual(canonical_hash(first.canonical), first.campaign_hash)
        self.assertNotEqual(first.campaign_hash, SYNTHETIC_V1_CAMPAIGN_HASH)  # never confused with the v1 campaign


class V12IdentityTests(_Campaigns):
    def test_question_and_tau_mf_each_change_campaign_and_run_identity(self):
        base = parse_campaign_definition(v12_definition(MATERIAL_IDENTIFICATION, 0.02))
        variants = {"question": parse_campaign_definition(v12_definition(SPECIMEN_ENGINEERING_CALIBRATION, 0.02)),
                    "tau_mf": parse_campaign_definition(v12_definition(MATERIAL_IDENTIFICATION, 0.015))}
        items, _ = self.specimens(base, "identity")

        def run_hash(definition):  # the run identity binds the campaign hash (identity only; nothing executes)
            return canonical_hash(campaign_run_identity(definition, items, "m" * 64, {}))

        for name, other in variants.items():
            with self.subTest(changed=name):
                self.assertNotEqual(other.campaign_hash, base.campaign_hash)
                self.assertNotEqual(run_hash(other), run_hash(base))
                self.assertEqual(campaign_run_identity(other, items, "m" * 64, {})["campaign_hash"],
                                 other.campaign_hash)
        self.assertEqual(parse_campaign_definition(v12_definition()).campaign_hash, base.campaign_hash)


class CalibrationRefusalTests(_Campaigns):
    def setUp(self):
        super().setUp()
        self.calibration = parse_campaign_definition(v12_definition(SPECIMEN_ENGINEERING_CALIBRATION))

    def test_calibration_execution_is_refused_until_v12_i3(self):
        self.assertEqual(CALIBRATION_NOT_IMPLEMENTED, "SPECIMEN_ENGINEERING_CALIBRATION_NOT_IMPLEMENTED")
        with self.assertRaises(CalibrationNotImplementedRefusal) as refused:
            self.calibration.require_executable()
        self.assertEqual(refused.exception.state, CALIBRATION_NOT_IMPLEMENTED)
        self.assertIn("V12-I3", str(refused.exception))
        self.assertFalse(isinstance(refused.exception, ValueError))  # generic fallback handlers never swallow it
        items, roots = self.specimens(self.calibration, "calibration")
        solver = FakeSolver()
        config = CampaignRunConfig(self.tmp / "runs", roots, "abq2024.bat", solver, FakeExtractor(), {}, "m" * 64)
        with self.assertRaises(CalibrationNotImplementedRefusal):
            CampaignRun(self.calibration, items, "m" * 64, config)
        self.assertEqual(solver.commands, [])
        self.assertFalse((self.tmp / "runs").exists())  # no run directory, no journal
        with self.assertRaises(CalibrationNotImplementedRefusal):
            prepare_run_manifest(self.calibration, None, items, roots, ROOT, self.tmp / "jobs")
        with self.assertRaises(CalibrationNotImplementedRefusal):  # no effective-estimate report either
            build_campaign_report(self.calibration, items, [], {"status": "CONVERGED", "parameters": None})

    def test_no_automatic_fallback(self):
        # A calibration definition is refused whatever its run type or RUN_B gate; it is never run as material ID.
        gated = parse_campaign_definition(v12_definition(
            SPECIMEN_ENGINEERING_CALIBRATION, run_type="RUN_B", fitted_parameters=["E_in_plane_mpa", "G12_mpa"],
            fixed_parameters={}, start={"E_in_plane_mpa": 52000.0, "G12_mpa": 4500.0},
            bounds={"E_in_plane_mpa": [26000.0, 104000.0], "G12_mpa": [2250.0, 9000.0]},
            engineering_plausibility={}, run_b_gate="D-999"))
        with self.assertRaises(CalibrationNotImplementedRefusal):
            gated.require_executable()
        # A material-identification campaign that refuses emits no calibration result.
        material = parse_campaign_definition(v12_definition(MATERIAL_IDENTIFICATION))
        campaign, result = self.execute(material, "material")
        report = build_campaign_report(material, campaign.specimens, campaign.journal.records("evaluation"), result)
        self.assertNotIn(SPECIMEN_ENGINEERING_CALIBRATION, json.dumps(report, default=str))
        # The question constant appears nowhere in production code except the schema module.
        users = [p.relative_to(ROOT / "src").as_posix() for p in (ROOT / "src").rglob("*.py")
                 if SPECIMEN_ENGINEERING_CALIBRATION in p.read_text(encoding="utf-8")]
        self.assertEqual(users, ["domain/campaign_definition.py"])


class TauMfHasNoNumericalEffectTests(_Campaigns):
    def test_tau_mf_does_not_enter_sigma_objective_whitening_m5_or_family_consistency(self):
        reference = parse_campaign_definition(synthetic_definition())
        runs = {"v1": self.execute(reference, "v1")}
        for tau in (0.02, 0.005):
            definition = parse_campaign_definition(v12_definition(MATERIAL_IDENTIFICATION, tau))
            self.assertEqual(row_sigma(definition), row_sigma(reference))  # Σ unchanged
            runs[tau] = self.execute(definition, f"tau-{tau}")
        base_campaign, base_result = runs["v1"]
        base_report = build_campaign_report(reference, base_campaign.specimens,
                                            base_campaign.journal.records("evaluation"), base_result)
        for tau in (0.02, 0.005):
            campaign, result = runs[tau]
            report = build_campaign_report(campaign.definition, campaign.specimens,
                                           campaign.journal.records("evaluation"), result)
            with self.subTest(tau_mf=tau):
                for label, pipeline in campaign.pipelines.items():  # objective design: Σ / whitening
                    self.assertEqual(pipeline.identity["objective_design"],
                                     base_campaign.pipelines[label].identity["objective_design"])
                self.assertEqual([e["residuals"] for e in campaign.journal.records("evaluation")],
                                 [e["residuals"] for e in base_campaign.journal.records("evaluation")])
                self.assertEqual({k: result[k] for k in ("status", "parameters", "objective", "local_sd")},
                                 {k: base_result[k] for k in ("status", "parameters", "objective", "local_sd")})
                for key in ("m5_verdict", "family_consistency", "sigma", "uncertainty_basis", "formal_output",
                            "model_form_robustness", "per_specimen_agreement", "excluded_mode_diagnostics"):
                    self.assertEqual(report[key], base_report[key], key)
                self.assertEqual({k: v for k, v in report.items() if k != "campaign_hash"},
                                 {k: v for k, v in base_report.items() if k != "campaign_hash"})

    def test_tau_mf_is_confined_to_the_schema_module(self):
        users = [p.relative_to(ROOT / "src").as_posix() for p in (ROOT / "src").rglob("*.py")
                 if "tau_mf" in p.read_text(encoding="utf-8")]
        self.assertEqual(users, ["domain/campaign_definition.py"])


class NoProcessTests(unittest.TestCase):
    def test_opening_a_v1_2_campaign_launches_no_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "campaign.json"
            path.write_text(json.dumps(v12_definition(SPECIMEN_ENGINEERING_CALIBRATION)), encoding="utf-8")
            forbidden = mock.Mock(side_effect=AssertionError("a process was launched"))
            with mock.patch.object(subprocess, "Popen", forbidden), mock.patch.object(subprocess, "run", forbidden), \
                    mock.patch("os.system", forbidden):
                definition = load_campaign_definition(path)
            self.assertEqual(definition.scientific_question, SPECIMEN_ENGINEERING_CALIBRATION)
            forbidden.assert_not_called()
        tree = ast.parse((ROOT / "src" / "domain" / "campaign_definition.py").read_text(encoding="utf-8"))
        imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)
                    for alias in node.names}
        imported |= {(node.module or "").split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        self.assertFalse(imported & {"subprocess", "os", "multiprocessing", "services"})


if __name__ == "__main__":
    unittest.main()
