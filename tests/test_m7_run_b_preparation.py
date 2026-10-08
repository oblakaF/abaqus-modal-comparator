"""M7 RUN_B preparation (D-072): definition, archive reuse, store override, diagnostic report semantics (no Abaqus).

RUN_B is the diagnostic EFFECTIVE_MODEL_COMPENSATION_TEST: E_in and G12 from the original governed start,
the same frozen observations, holdouts, Σ and LM settings as RUN_A; G12 is a compensation diagnostic only.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.campaign_definition import (
    EFFECTIVE_ESTIMATE,
    NO_MATERIAL_CLAIM,
    NOT_EXTERNALLY_VALIDATED,
    RUN_B_LABEL,
    load_archive_reuse,
    load_campaign_definition,
    parse_campaign_definition,
)
from domain.experiment_fixture import fixture_roots_from_environment, load_experiment_fixture_manifest
from services.identification_campaign_run import (
    CampaignGateRefusal,
    CampaignRun,
    CampaignRunConfig,
    build_campaign_report,
    compare_to_reference,
    initial_points,
    reused_pack_records,
)
from test_m7_campaign import FakeExtractor, FakeSolver, synthetic_definition, synthetic_specimen


CAMPAIGNS = ROOT / "docs" / "auto_id" / "campaigns"
RUN_A = CAMPAIGNS / "M7_RUN_A.campaign.json"
RUN_B = CAMPAIGNS / "M7_RUN_B.campaign.json"
REUSE_B = CAMPAIGNS / "M7_RUN_B.archive-reuse.json"
RUN_B_HASH = "7c1f5db24fa9c4f4e90c82ca802c6dae22cbe5c7ec9e2989e63e439f678540e5"
RUN_B_MANIFEST = "5fd0946a0c3f4e20562ba97068cdb5b94bf6d10ba789a3b2df20b457882034a1"
G_ODBS = {"SP02_05239a3b56508244": ("carbon5a/runs/G_PLUS_SP02/SP02_05239a3b56508244.odb",
                                    "d3b49b047517d155db88567c57dfb7dab4b83a81f09e7725886c646e2fa7de1a", 4725.0),
          "SP02_ade5dffa2fde3903": ("carbon5a/runs/G_MINUS_SP02/SP02_ade5dffa2fde3903.odb",
                                    "52f7b740d8b3fe736f6255d8ea1e14dd687e0b76b112bbd4c50f31dca52cba49", 4275.0)}


class RunBDefinitionTests(unittest.TestCase):
    def setUp(self):
        self.b = load_campaign_definition(RUN_B)
        self.a = load_campaign_definition(RUN_A)

    def test_run_b_is_the_accepted_diagnostic_design(self):
        b = self.b
        self.assertEqual(b.campaign_hash, RUN_B_HASH)
        self.assertEqual((b.run_type, b.decision, b.run_b_gate), ("RUN_B", "D-072", "D-072"))
        self.assertEqual(b.fitted_parameters, ("E_in_plane_mpa", "G12_mpa"))
        self.assertEqual(dict(b.fixed_parameters), {})
        self.assertEqual(dict(b.start), {"E_in_plane_mpa": 52000.0, "G12_mpa": 4500.0})  # the governed start
        self.assertEqual(dict(b.bounds), {"E_in_plane_mpa": (26000.0, 104000.0), "G12_mpa": (2250.0, 9000.0)})
        self.assertEqual(dict(b.engineering_plausibility), {"E_in_plane_mpa": (35000.0, 75000.0)})  # G12: none
        self.assertEqual((b.abaqus_solve_budget, b.lm.evaluation_budget), (24, 17))
        b.require_executable()  # the SUPERVISOR RUN_B gate exists; the HUMAN manifest gate still applies

    def test_everything_else_equals_run_a(self):
        a, b = self.a, self.b
        self.assertEqual(a.specimens, b.specimens)
        self.assertEqual((a.fit_term_ids(), a.holdout_term_ids()), (b.fit_term_ids(), b.holdout_term_ids()))
        self.assertEqual(a.sigma, b.sigma)
        self.assertEqual({k: v for k, v in vars(a.lm).items() if k != "evaluation_budget"},
                         {k: v for k, v in vars(b.lm).items() if k != "evaluation_budget"})
        self.assertEqual(a.not_fitted, b.not_fitted)
        self.assertEqual((a.preferred_max_abs_relative_error, a.acceptable_max_abs_relative_error),
                         (b.preferred_max_abs_relative_error, b.acceptable_max_abs_relative_error))

    def test_initial_points_are_the_five_central_difference_points(self):
        self.assertEqual(initial_points(self.b), {
            "p0": {"E_in_plane_mpa": 52000.0, "G12_mpa": 4500.0},
            "E_in_plane_mpa+": {"E_in_plane_mpa": 54600.0, "G12_mpa": 4500.0},
            "E_in_plane_mpa-": {"E_in_plane_mpa": 49400.0, "G12_mpa": 4500.0},
            "G12_mpa+": {"E_in_plane_mpa": 52000.0, "G12_mpa": 4725.0},
            "G12_mpa-": {"E_in_plane_mpa": 52000.0, "G12_mpa": 4275.0}})


class RunBReuseTests(unittest.TestCase):
    def setUp(self):
        self.reuse = load_archive_reuse(REUSE_B, "carbon-property-set/v1")
        self.anchors = {c["name"]: c for c in json.loads((ROOT / "docs/auto_id/forward_models/accepted_forward_jobs.json")
                                                        .read_text(encoding="utf-8"))["candidates"]}

    def test_sp02_g12_odbs_are_the_accepted_carbon5a_solves(self):
        odbs = {o.job_name: o for o in self.reuse.odbs}
        self.assertEqual(set(odbs), set(G_ODBS))
        for job, (path, digest, g12) in G_ODBS.items():
            entry = odbs[job]
            name = "CARBON-5A G_PLUS" if g12 > 4500 else "CARBON-5A G_MINUS"
            with self.subTest(job=job):
                self.assertEqual((entry.odb_relative_path, entry.odb_sha256), (path, digest))
                self.assertEqual(dict(entry.point), {"E_in_plane_mpa": 52000.0, "G12_mpa": g12})
                self.assertEqual(entry.generated_inp_sha256, self.anchors[name]["jobs"]["SP02"]["generated_inp_sha256"])
                self.assertEqual(entry.excluded_attempts, ())
                self.assertEqual(entry.expected_mode_numbers, tuple(range(7, 31)))

    def test_reused_packs(self):
        packs = {(p.specimen, p.job_name): p for p in self.reuse.packs}
        self.assertEqual(set(packs), {
            ("SP02", "SP02_f3e592281bebce66"), ("SP02", "SP02_13363f977809dbff"), ("SP02", "SP02_84753f636064e192"),
            ("SP13", "SP13_a46d08b52995e078"), ("SP13", "SP13_0e861d03c333bb0b"), ("SP13", "SP13_a9df66283a168786"),
            ("SP13", "SP13_4c0f189b9727feaf"), ("SP13", "SP13_0328066b74b6fd78")})
        for key in (("SP02", "SP02_13363f977809dbff"), ("SP02", "SP02_84753f636064e192")):
            self.assertEqual(packs[key].pack_store, "m7-run-a-archive")
            self.assertTrue(packs[key].shape_pack_record.startswith("docs/auto_id/campaigns/archive_extraction/"))
        self.assertEqual(dict(packs[("SP13", "SP13_4c0f189b9727feaf")].point)["G12_mpa"], 4725.0)
        self.assertEqual(dict(packs[("SP13", "SP13_0328066b74b6fd78")].point)["G12_mpa"], 4275.0)

    def test_store_override_keeps_every_pin(self):
        records = reused_pack_records(self.reuse, ROOT, {}, [mock.Mock(label="SP02"), mock.Mock(label="SP13")])
        record = records["SP02"]["SP02_13363f977809dbff"]
        original = json.loads((CAMPAIGNS / "archive_extraction/SP02_13363f977809dbff.shape-pack.json")
                              .read_text(encoding="utf-8"))
        self.assertEqual(record.pack.location.store, "m7-run-a-archive")
        self.assertEqual(record.pack.location.relative_path, original["pack"]["location"]["relative_path"])
        self.assertEqual((record.pack.sha256, record.content_sha256), (original["pack"]["sha256"],
                                                                       original["content_sha256"]))
        self.assertEqual(records["SP13"]["SP13_4c0f189b9727feaf"].pack.location.store, "carbon-project-archive")

    def test_run_a_reuse_record_unchanged(self):
        run_a = load_archive_reuse(CAMPAIGNS / "M7_RUN_A.archive-reuse.json", "carbon-property-set/v1")
        self.assertEqual(run_a.reuse_hash, "91c8bc547c738a65ec5bdf4ff1e2d6f3d91e518fd5bdab4ebb547fc7b1a18b92")
        self.assertTrue(all(p.pack_store is None for p in run_a.packs))


class RunBReportSemanticsTests(unittest.TestCase):
    """Synthetic RUN_B campaign (fake executors): the diagnostic label, G12 role and Δln against RUN_A."""

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.tmp = Path(self._directory.name)

    def tearDown(self):
        self._directory.cleanup()

    def run_campaign(self, definition):
        items, roots = [], {}
        for label in ("A", "B"):
            item, store = synthetic_specimen(definition, label, self.tmp)
            items.append(item)
            roots["synthetic"] = store
        config = CampaignRunConfig(self.tmp / "runs", roots, "abq2024.bat", FakeSolver(), FakeExtractor(), {},
                                   "m" * 64)
        run = CampaignRun(definition, items, "m" * 64, config)
        return run, run.run()

    def test_run_b_report_is_a_compensation_test(self):
        definition = parse_campaign_definition(synthetic_definition(
            run_type="RUN_B", fitted_parameters=["E_in_plane_mpa", "G12_mpa"], fixed_parameters={},
            start={"E_in_plane_mpa": 52000.0, "G12_mpa": 4500.0},
            bounds={"E_in_plane_mpa": [26000.0, 104000.0], "G12_mpa": [2250.0, 9000.0]},
            engineering_plausibility={"E_in_plane_mpa": [35000.0, 75000.0]}, run_b_gate="D-072",
            abaqus_solve_budget=24))
        run, result = self.run_campaign(definition)
        self.assertEqual(result["status"], "CONVERGED")
        reference = {"E_in_plane_mpa": 50000.0, "G12_mpa": 4500.0}
        report = build_campaign_report(definition, run.specimens, run.journal.records("evaluation"), result,
                                       reference, "RUN_A synthetic")
        self.assertEqual(report["engineering"]["estimate"], RUN_B_LABEL)
        self.assertNotEqual(report["engineering"]["estimate"], EFFECTIVE_ESTIMATE)
        self.assertEqual(report["parameter_roles"]["G12_mpa"], "COMPENSATION_DIAGNOSTIC_NOT_MATERIAL_PROPERTY")
        g12 = report["m5_verdict"]["verdicts"]["G12_mpa"]
        self.assertEqual(g12["verdict"], "NOT_IDENTIFIABLE")
        self.assertTrue(any(r.startswith("BARE_PLATE_REQUIRED") for r in g12["reasons"]))
        self.assertEqual(report["material_claim"], NO_MATERIAL_CLAIM)
        self.assertEqual(report["validation"], NOT_EXTERNALLY_VALIDATED)
        shifts = report["comparison"]["shifts"]
        self.assertAlmostEqual(shifts["E_in_plane_mpa"]["delta_ln"],
                               math.log(result["parameters"]["E_in_plane_mpa"] / 50000.0), places=12)
        self.assertIn("not a material-identification criterion", report["comparison"]["note"])

    def test_descriptive_bands(self):
        c = compare_to_reference({"E_in_plane_mpa": 55593.4, "G12_mpa": 7364.0},
                                 {"E_in_plane_mpa": 55593.4, "G12_mpa": 4500.0}, "RUN_A")
        self.assertEqual(c["shifts"]["E_in_plane_mpa"]["description"], "WITHIN_0.05_LN")
        self.assertEqual(c["shifts"]["G12_mpa"]["description"], "BEYOND_0.08_LN")
        self.assertEqual(compare_to_reference({"E_in_plane_mpa": 1.0}, {"E_in_plane_mpa": math.exp(-0.07)}, "x")
                         ["shifts"]["E_in_plane_mpa"]["description"], "WITHIN_0.08_LN")

    def test_tool_run_b_refuses_an_unauthorised_hash(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import m7_campaign as tool

        with mock.patch.object(tool, "build", return_value=(None, None, None, {}, "a" * 64)) as build:
            for command in ("run", "extract-archive"):
                with self.assertRaises(CampaignGateRefusal):
                    tool.main([command, "--campaign", "run-b", "--run-root", str(self.tmp / "g"), "--abaqus", "abq",
                               "--authorised-manifest-hash", "b" * 64])
            self.assertEqual(build.call_args[0][2], "run-b")


class RealRunBPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        roots = fixture_roots_from_environment()
        missing = sorted({"snadwich", "carbon-project-archive", "m7-run-a-archive"} - set(roots))
        if missing:
            raise unittest.SkipTest(f"data stores {missing} not configured")
        from services.identification_campaign_run import prepare_campaign_specimens, prepare_run_manifest

        cls._directory = tempfile.TemporaryDirectory()
        definition = load_campaign_definition(RUN_B)
        reuse = load_archive_reuse(REUSE_B, definition.parameterisation_id)
        fixtures = load_experiment_fixture_manifest(ROOT / "docs/auto_id/fixtures/real_experiment_fixtures.json")
        specimens = prepare_campaign_specimens(definition, ROOT, fixtures, roots)
        cls.manifest, cls.manifest_hash = prepare_run_manifest(definition, reuse, specimens, roots, ROOT,
                                                               Path(cls._directory.name))

    @classmethod
    def tearDownClass(cls):
        cls._directory.cleanup()

    def test_manifest_is_pinned_and_reuses_every_initial_point(self):
        self.assertEqual(self.manifest_hash, RUN_B_MANIFEST)
        sources = {(p["specimen"], p["point"]): p["source"] for p in self.manifest["initial_points"]}
        self.assertEqual(len(sources), 10)
        self.assertEqual({k for k, v in sources.items() if v == "archived-odb-extraction"},
                         {("SP02", "G12_mpa+"), ("SP02", "G12_mpa-")})
        self.assertEqual(self.manifest["new_solve_initial_points"], [])
        self.assertEqual(self.manifest["budgets"], {
            "max_new_abaqus_solves": 24, "max_new_solve_extractions": 24, "archive_extractions": 2,
            "max_abaqus_python_extractions": 26, "lm_evaluation_budget": 17, "reused_initial_evaluations": 5,
            "max_new_campaign_evaluations": 12})


if __name__ == "__main__":
    unittest.main()
