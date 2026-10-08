"""M7 Run A campaign architecture (D-069): definition, Σ, archive reuse, campaign evaluation, report (no Abaqus).

Every solve and extraction is a fake executor.  Real-store tests (freeze on the active physical chains,
the pinned run manifest, the archived-ODB pins) are store-gated and run no Abaqus.
"""

from __future__ import annotations

import ast
import copy
from dataclasses import asdict, replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.campaign_definition import (
    EFFECTIVE_ESTIMATE,
    NO_EFFECTIVE_ESTIMATE,
    NO_MATERIAL_CLAIM,
    NOT_EXTERNALLY_VALIDATED,
    CampaignDefinitionError,
    RunGateRefusal,
    load_archive_reuse,
    load_campaign_definition,
    parse_campaign_definition,
)
from domain.experiment_fixture import fixture_roots_from_environment, load_experiment_fixture_manifest
from domain.forward_model_manifest import bind_forward_model, carbon_candidate
from domain.frozen_observations import BaselineIdentity, FreezeStatus, FrozenObservationSet, ObservationRow
from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING
from domain.identification_run import parse_solver_profile
from m3_support import SYNTHETIC_INP, forward_manifest, synthetic_passport
from m4_6_support import FE_IDENTITY, MODES, NODE_SET, TOP_ROWS, FakeExtractor, FakeSolver, fake_frequencies, profile_dict
from services.fe_shape_pack import parse_shape_pack_record
from services.forward_builder import prepare_forward_job
from services.identification_campaign_run import (
    CampaignGateRefusal,
    CampaignRun,
    CampaignRunConfig,
    CampaignSpecimenInput,
    ObservationSetMismatch,
    build_campaign_report,
    check_observation_set,
    initial_points,
)
from services.identification_objective import RowSigma
from services.shape_extraction import ExtractionExpectation


CAMPAIGNS = ROOT / "docs" / "auto_id" / "campaigns"
DEFINITION = CAMPAIGNS / "M7_RUN_A.campaign.json"
REUSE = CAMPAIGNS / "M7_RUN_A.archive-reuse.json"
CAMPAIGN_HASH = "0a21ad0567901034b521b822b52f0c29944e96394f3692e1a8ebcd7ccd8d2ccf"
MANIFEST_HASH = "e4ba607f06a69311b4d7adab089b5b8fdbbf98aae9d2da0837849e6c5da5bde6"
ACCEPTED_ROWS = {"SP02": [("R1", 2, 8, "FIT"), ("R2", 4, 10, "FIT"), ("R3", 7, 13, "HOLDOUT")],
                 "SP13": [("R1", 4, 10, "FIT"), ("R2", 7, 13, "HOLDOUT")]}


def definition_dict(**changes) -> dict:
    data = json.loads(DEFINITION.read_text(encoding="utf-8"))
    for path, value in changes.items():
        target = data
        *parents, key = path.split("__")
        for part in parents:
            target = target[int(part)] if isinstance(target, list) else target[part]
        target[key] = value
    return data


# ----------------------------------------------------------------------------- the committed Run A definition

class RunADefinitionTests(unittest.TestCase):
    def setUp(self):
        self.definition = load_campaign_definition(DEFINITION)

    def test_record_is_the_accepted_run_a_design(self):
        d = self.definition
        self.assertEqual(d.campaign_hash, CAMPAIGN_HASH)
        self.assertEqual((d.run_type, d.decision), ("RUN_A", "D-069"))
        self.assertEqual(d.fitted_parameters, ("E_in_plane_mpa",))
        self.assertEqual(dict(d.fixed_parameters), {"G12_mpa": 4500.0})
        self.assertEqual(dict(d.start), {"E_in_plane_mpa": 52000.0})
        self.assertEqual(d.full_parameters(d.start), {"E_in_plane_mpa": 52000.0, "G12_mpa": 4500.0})
        self.assertEqual(dict(d.bounds), {"E_in_plane_mpa": (26000.0, 104000.0)})
        self.assertEqual(dict(d.engineering_plausibility), {"E_in_plane_mpa": (35000.0, 75000.0)})
        self.assertEqual((d.preferred_max_abs_relative_error, d.acceptable_max_abs_relative_error), (0.05, 0.10))
        self.assertEqual((d.abaqus_solve_budget, d.lm.evaluation_budget), (16, 11))
        self.assertEqual((d.lm.mu_initial, d.lm.mu_decrease, d.lm.max_step_attempts, d.lm.max_iterations,
                          d.lm.finite_difference_step), (1e-3, 10.0, 3, 5, 0.05))
        self.assertEqual(set(d.not_fitted), {"t_face", "k_core", "k_int"})
        self.assertTrue(d.not_fitted["k_int"].startswith("OFF"))
        self.assertIsNone(d.run_b_gate)

    def test_exact_active_fixtures_and_accepted_rows(self):
        d = self.definition
        self.assertEqual([(s.label, s.fixture_id) for s in d.specimens],
                         [("SP02", "SP02/bravo-1-physical"), ("SP13", "SP13/best-physical")])
        for spec in d.specimens:
            with self.subTest(specimen=spec.label):
                self.assertEqual([(r.row_id, r.experimental_mode, r.fe_mode, r.role) for r in spec.rows],
                                 ACCEPTED_ROWS[spec.label])
                self.assertTrue(spec.forward_model.endswith(f"{spec.label}.physical.forward.json"))
        self.assertEqual(d.fit_term_ids(), ("SP02:R1", "SP02:R2", "SP13:R1"))
        self.assertEqual(d.holdout_term_ids(), ("SP02:R3", "SP13:R2"))

    def test_rows_match_the_accepted_physical_freezes(self):
        for spec in self.definition.specimens:
            evidence = json.loads((ROOT / "docs/auto_id/registration_evidence" /
                                   f"{spec.label}_registration_reevaluation.json").read_text(encoding="utf-8"))
            physical = evidence["results"]["PHYSICAL"]
            with self.subTest(specimen=spec.label):
                self.assertEqual([(p["row_id"], p["experimental_mode"], p["fe_mode"]) for p in physical["strict_pairs"]],
                                 [(r.row_id, r.experimental_mode, r.fe_mode) for r in spec.rows])
                self.assertEqual(tuple(physical["holdouts"]["holdout_row_ids"]), spec.holdout_rows)

    def test_sigma_setup_provisional_and_measurement_not_available(self):
        sigma = self.definition.sigma
        self.assertEqual((sigma.setup_sd_ln, sigma.setup_status, sigma.measurement_status),
                         (0.003, "PROVISIONAL", "NOT_AVAILABLE"))
        self.assertTrue(sigma.setup_provisional)
        self.assertFalse(sigma.measurement_available)
        with self.assertRaises(CampaignDefinitionError):
            sigma.measurement_sd_ln()  # NOT_AVAILABLE has no value; never zero
        self.assertNotIn("sd_ln", sigma.to_dict()["measurement"])
        with self.assertRaises(CampaignDefinitionError):
            parse_campaign_definition(definition_dict(sigma__measurement__status="MEASURED"))

    def test_run_a_fits_e_in_only_and_run_b_is_gated(self):
        with self.assertRaises(CampaignDefinitionError):  # RUN_A may not fit G12
            parse_campaign_definition(definition_dict(fitted_parameters=["E_in_plane_mpa", "G12_mpa"],
                                                      fixed_parameters={}, start={"E_in_plane_mpa": 52000.0,
                                                                                  "G12_mpa": 4500.0}))
        run_b = definition_dict(run_type="RUN_B", fitted_parameters=["E_in_plane_mpa", "G12_mpa"], fixed_parameters={},
                                start={"E_in_plane_mpa": 52000.0, "G12_mpa": 4500.0},
                                bounds={"E_in_plane_mpa": [26000.0, 104000.0], "G12_mpa": [2250.0, 9000.0]})
        definition = parse_campaign_definition(run_b)
        with self.assertRaises(RunGateRefusal):
            definition.require_executable()  # RUN_B needs its own later SUPERVISOR gate
        with self.assertRaises(CampaignDefinitionError):  # a RUN_A definition carries no RUN_B gate
            parse_campaign_definition(definition_dict(run_b_gate="D-999"))

    def test_bounds_and_strict_parsing(self):
        cases = {
            "start outside bounds": {"start": {"E_in_plane_mpa": 20000.0}},
            "inverted bounds": {"bounds": {"E_in_plane_mpa": [104000.0, 26000.0]}},
            "plausibility on a fixed parameter": {"engineering_plausibility": {"G12_mpa": [2250.0, 9000.0]}},
            "missing not_fitted entry": {"not_fitted": {"t_face": "x", "k_core": "y"}},
            "single specimen": {"specimens": [definition_dict()["specimens"][0]]},
            "unknown row role": {"specimens__0__rows__0__role": "PROMOTED"},
            "absolute path": {"specimens__0__forward_model": "D:/x/SP02.physical.forward.json"},
            "fixed G12 missing": {"fixed_parameters": {}},
        }
        for label, changes in cases.items():
            with self.subTest(case=label):
                with self.assertRaises(CampaignDefinitionError):
                    parse_campaign_definition(definition_dict(**changes))
        data = definition_dict()
        data["extra"] = 1
        with self.assertRaises(CampaignDefinitionError):
            parse_campaign_definition(data)

    def test_initial_points_are_the_lm_central_differences(self):
        points = initial_points(self.definition)
        self.assertEqual(points, {"p0": {"E_in_plane_mpa": 52000.0, "G12_mpa": 4500.0},
                                  "E_in_plane_mpa+": {"E_in_plane_mpa": 52000.0 * 1.05, "G12_mpa": 4500.0},
                                  "E_in_plane_mpa-": {"E_in_plane_mpa": 52000.0 * 0.95, "G12_mpa": 4500.0}})


class RowSigmaNotAvailableTests(unittest.TestCase):
    def test_measurement_not_available_is_excluded_not_zero(self):
        sigma = RowSigma(None, 0.003, True)
        self.assertFalse(sigma.measurement_available)
        self.assertEqual(sigma.sigma, 0.003)
        self.assertIsNone(asdict(sigma)["measurement_sd"])  # recorded as null in run identities
        self.assertEqual(RowSigma(0.003, 0.0, False).sigma, 0.003)  # numeric behaviour unchanged
        self.assertAlmostEqual(RowSigma(0.003, 0.004, False).sigma, 0.005)
        for bad in (-0.1, float("nan")):
            with self.assertRaises(Exception):
                RowSigma(bad, 0.003, True)
        with self.assertRaises(Exception):
            RowSigma(None, 0.0, True)  # σ must still be positive


# ----------------------------------------------------------------------------- archive reuse (record level)

class ArchiveReuseRecordTests(unittest.TestCase):
    def setUp(self):
        self.reuse = load_archive_reuse(REUSE, "carbon-property-set/v1")
        self.anchors = {c["name"]: c for c in json.loads((ROOT / "docs/auto_id/forward_models/accepted_forward_jobs.json")
                                                        .read_text(encoding="utf-8"))["candidates"]}

    def test_governed_packs_and_anchors(self):
        packs = {p.job_name: p for p in self.reuse.packs}
        self.assertEqual(set(packs), {"SP02_f3e592281bebce66", "SP13_a46d08b52995e078", "SP13_a9df66283a168786",
                                      "SP13_0e861d03c333bb0b"})
        for entry in self.reuse.packs:
            record = json.loads((ROOT / entry.shape_pack_record).read_text(encoding="utf-8"))
            with self.subTest(job=entry.job_name):
                self.assertEqual(record["generated_inp_sha256"], entry.generated_inp_sha256)
                self.assertTrue(all(record["validation"].values()))

    def test_sp02_archived_odbs_are_the_accepted_carbon5a_solves(self):
        odbs = {o.job_name: o for o in self.reuse.odbs}
        self.assertEqual(set(odbs), {"SP02_84753f636064e192", "SP02_13363f977809dbff"})
        minus, plus = odbs["SP02_84753f636064e192"], odbs["SP02_13363f977809dbff"]
        self.assertEqual(minus.generated_inp_sha256,
                         self.anchors["CARBON-5A E_MINUS"]["jobs"]["SP02"]["generated_inp_sha256"])
        self.assertEqual(plus.generated_inp_sha256,
                         self.anchors["CARBON-5A E_PLUS"]["jobs"]["SP02"]["generated_inp_sha256"])
        self.assertEqual(minus.odb_relative_path, "carbon5a/runs/E_MINUS_SP02_retry1/SP02_84753f636064e192.odb")
        self.assertEqual(minus.odb_sha256, "bae6a7c133a8eb4b3bc9eef77d25b45173cb32144875c5591ff2b61a79858e4c")
        self.assertEqual(plus.odb_sha256, "ba38cb698c5cb2dc3ed6fb4861e343ebf3f7250eabd2b1517cabdeb1378b74f5")
        self.assertEqual([a["relative_path"] for a in minus.excluded_attempts], ["carbon5a/runs/E_MINUS_SP02"])
        self.assertIn("space exhausted", minus.excluded_attempts[0]["reason"])
        for entry in (minus, plus):
            self.assertEqual(entry.expected_mode_numbers, tuple(range(7, 31)))
            self.assertEqual(dict(entry.point)["G12_mpa"], 4500.0)
        self.assertEqual((dict(minus.point)["E_in_plane_mpa"], dict(plus.point)["E_in_plane_mpa"]), (49400.0, 54600.0))


# ----------------------------------------------------------------------------- synthetic two-specimen campaign

TRUTH_E = 48000.0
ROWS = {"A": [("R1", 8, False), ("R2", 10, False), ("R3", 13, True)], "B": [("R1", 10, False), ("R2", 13, True)]}


def synthetic_definition(**changes) -> dict:
    data = definition_dict()
    data["campaign_id"] = "SYN/RUN_A"
    data["specimens"] = [
        {"label": label, "fixture_id": f"SYN/{label}", "forward_model": f"x/{label}.forward.json",
         "solver_profile": f"x/{label}.json", "baseline_shape_pack": f"x/{label}.pack.json",
         "archived_baseline": f"x/{label}.baseline.json", "registration_evidence": f"x/{label}.m24.json",
         "rows": [{"row_id": r, "experimental_mode": k + 1, "fe_mode": m, "role": "HOLDOUT" if h else "FIT"}
                  for k, (r, m, h) in enumerate(ROWS[label])]} for label in ("A", "B")]
    data.update(changes)
    return data


def _record_stub(job, prefix):
    def file(name):
        return {"role": "x", "file_name": name, "sha256": "0" * 64, "size_bytes": 1,
                "location": {"store": "x", "relative_path": name}}

    return parse_shape_pack_record({
        "schema": "auto-id/fe-shape-pack-record/v1", "job_name": job.job_name, "specimen": prefix, "state": "BASELINE",
        "generated_inp_sha256": job.generated_inp_sha256, "odb": file(f"{job.job_name}.odb"),
        "pack": file(f"{job.job_name}.npz"), "content_sha256": "0" * 64,
        "node_set": {"definition": "TOP", "node_count": len(TOP_ROWS), "sha256": NODE_SET},
        "fe_geometry_sha256": FE_IDENTITY["sha256"], "mode_numbers": list(MODES), "frequencies_hz": [1.0] * 24,
        "extraction": {}, "validation": {"ok": True}, "provenance_record": {}})


def synthetic_specimen(definition, label, tmp: Path, experimental_e: float = TRUTH_E):
    prefix = {"A": "SYA", "B": "SYB"}[label]
    store = tmp / "store"
    (store / "models").mkdir(parents=True, exist_ok=True)
    text = SYNTHETIC_INP.replace("15, , , , ,", "30, , , , ,")
    if label == "B":
        text = text.replace("3.32e-05", "3.33e-05")  # another specimen model (different INP identity)
    raw = text.encode("latin-1")
    (store / "models" / f"{prefix}.inp").write_bytes(raw)
    passport = synthetic_passport(design_id=f"DES-{label}", test_run_id=f"RUN-{label}")
    manifest = forward_manifest(passport, raw, forward_model_id=f"{prefix}_MODEL/carbon-property-set-v1",
                                job_prefix=prefix, frequency_request__source_eigenvalue_count=30,
                                model_input__file_name=f"{prefix}.inp",
                                model_input__location={"store": "synthetic", "relative_path": f"models/{prefix}.inp"})
    model = bind_forward_model(manifest, passport)
    profile = parse_solver_profile(profile_dict(profile_id=f"{prefix}/fake",
                                                forward_model_id=manifest.forward_model_id, job_prefix=prefix))
    p0 = prepare_forward_job(model, carbon_candidate(52000.0, 4500.0), raw, tmp / "p0" / label)
    identity = BaselineIdentity(manifest.forward_model_id, p0.job_name, p0.generated_inp_sha256, FE_IDENTITY["sha256"],
                                manifest.registration_hash, "3" * 64, "set", ("U3",), "synthetic", None)
    exp = fake_frequencies(experimental_e, 4500.0)
    base = fake_frequencies(52000.0, 4500.0)
    rows = tuple(ObservationRow(r, k + 1, exp[m - 7], m, base[m - 7], 0.99, base[m - 7] / exp[m - 7] - 1)
                 for k, (r, m, _) in enumerate(ROWS[label]))
    frozen = FrozenObservationSet(identity, STRICT_IDENTIFICATION_PAIRING.policy_id,
                                  STRICT_IDENTIFICATION_PAIRING.policy_hash, FreezeStatus.FROZEN, (), rows, (), (), ())
    spec = definition.specimen(label)
    holdouts = tuple(r for r, _, h in ROWS[label] if h)
    families = {"R1": f"FAM-{label}1", "R2": "FAM-12" if label == "A" else "FAM-12", "R3": "FAM-03"}
    families = {r: families[r] for r, _, _ in ROWS[label]}
    if label == "B":
        families["R2"] = "FAM-03"
    expectation = ExtractionExpectation("TOP", "max_z", 1e-4, FE_IDENTITY["sha256"], FE_IDENTITY["node_count"],
                                        NODE_SET, len(TOP_ROWS), MODES)
    return CampaignSpecimenInput(spec, model, profile, frozen, holdouts, families, expectation,
                                 _record_stub(p0, prefix), False, "synthetic M2.4 record"), store


class _SelectiveExchange:
    """Extraction executor: exchanges modes 9/10 only for one specimen's jobs (in-memory test fake)."""

    def __init__(self, prefix: str, below_e: float):
        self.prefix, self.exchanging, self.normal = prefix, FakeExtractor(exchange_below_e=below_e), FakeExtractor()

    def __call__(self, odb, raw, start, end):
        target = self.exchanging if Path(odb).name.startswith(self.prefix + "_") else self.normal
        return target(odb, raw, start, end)


class SyntheticCampaignTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.tmp = Path(self._directory.name)
        self.definition = parse_campaign_definition(synthetic_definition())

    def tearDown(self):
        self._directory.cleanup()

    def campaign(self, definition=None, solver=None, extractor=None, authorised="m" * 64, experimental_e=TRUTH_E,
                 run_root=None):
        definition = definition or self.definition
        items, roots = [], {}
        for label in ("A", "B"):
            item, store = synthetic_specimen(definition, label, self.tmp, experimental_e)
            items.append(item)
            roots["synthetic"] = store
        self.solver = solver or FakeSolver()
        config = CampaignRunConfig(run_root or self.tmp / "runs", roots, "abq2024.bat", self.solver,
                                   extractor or FakeExtractor(), {}, authorised)
        return CampaignRun(definition, items, "m" * 64, config), items

    def test_shared_e_in_g12_fixed_and_residual_order(self):
        run, items = self.campaign()
        result = run.run()
        self.assertEqual(result["status"], "CONVERGED")
        self.assertAlmostEqual(result["parameters"]["E_in_plane_mpa"], TRUTH_E, delta=TRUTH_E * 2e-3)
        evaluations = run.journal.records("evaluation")
        self.assertTrue(evaluations)
        for e in evaluations:
            self.assertEqual(e["fit_term_ids"], ["A:R1", "A:R2", "B:R1"])
            self.assertEqual(e["full_parameters"]["G12_mpa"], 4500.0)
            self.assertEqual(set(e["holdout_residuals"]), {"A:R3", "B:R2"})
            self.assertEqual(len(e["residuals"]), 3)
            stacked = e["specimens"]["A"]["residuals"] + e["specimens"]["B"]["residuals"]
            self.assertEqual(e["residuals"], stacked)
        # One shared E_in per evaluation: both specimens' journalled jobs carry the same candidate.
        for label, pipeline in run.pipelines.items():
            for record in pipeline.journal.records("evaluation"):
                self.assertEqual(record["parameters"]["G12_mpa"], 4500.0)
        shared = [{p.journal.records("evaluation")[k]["parameters"]["E_in_plane_mpa"] for p in run.pipelines.values()}
                  for k in range(len(run.pipelines["A"].journal.records("evaluation")))]
        self.assertTrue(all(len(values) == 1 for values in shared))

    def test_no_cross_specimen_mode_mixing(self):
        run, items = self.campaign()
        run.run()
        final = run.journal.records("evaluation")[-1]
        self.assertEqual(set(final["specimens"]["A"]["tracking"]), {"R1", "R2", "R3"})
        self.assertEqual(set(final["specimens"]["B"]["tracking"]), {"R1", "R2"})
        self.assertEqual(final["specimens"]["B"]["tracking"]["R1"][0], 10)  # B's own baseline mode, tracked by B
        self.assertTrue(final["specimens"]["A"]["job_name"].startswith("SYA_"))
        self.assertTrue(final["specimens"]["B"]["job_name"].startswith("SYB_"))

    def test_deterministic_campaign_hash(self):
        first, _ = self.campaign(run_root=self.tmp / "r1")
        second, _ = self.campaign(run_root=self.tmp / "r2")
        self.assertEqual(first.run_hash, second.run_hash)
        changed = parse_campaign_definition(synthetic_definition(sigma={
            "setup": {"sd_ln": 0.004, "status": "PROVISIONAL", "source": "x"},
            "measurement": {"status": "NOT_AVAILABLE", "source": "y"}}))
        third, _ = self.campaign(definition=changed, run_root=self.tmp / "r3")
        self.assertNotEqual(third.run_hash, first.run_hash)
        self.assertEqual(first.identity["run_type"], "RUN_A")
        self.assertEqual(first.identity["sigma"]["measurement"]["status"], "NOT_AVAILABLE")
        for specimen in first.identity["specimens"]:
            self.assertIn("observation_hash", specimen)
            self.assertIn("registration_hash", specimen)
        # Σ_meas NOT_AVAILABLE reaches every specimen pipeline identity as null, never as a zero value.
        for pipeline in first.pipelines.values():
            for sigma in pipeline.identity["objective_design"]["sigmas"].values():
                self.assertIsNone(sigma["measurement_sd"])
                self.assertEqual((sigma["setup_sd"], sigma["setup_provisional"]), (0.003, True))

    def test_resume_never_duplicates_an_evaluation_or_solve(self):
        run, _ = self.campaign()
        result = run.run()
        first_solver = self.solver
        solves = len(first_solver.commands)
        self.assertGreater(solves, 0)
        resumed_solver = FakeSolver()
        again, _ = self.campaign(solver=resumed_solver)
        repeat = again.run()
        self.assertEqual(len(first_solver.commands), solves)
        self.assertEqual(resumed_solver.commands, [])  # zero new solves on resume
        self.assertGreater(again.replayed_evaluations, 0)
        self.assertEqual(repeat["parameters"], result["parameters"])
        self.assertEqual(len(again.journal.records("result")), 1)

    def test_hard_solve_budget_stops_without_extension(self):
        tight = parse_campaign_definition(synthetic_definition(abaqus_solve_budget=3))
        run, _ = self.campaign(definition=tight)
        result = run.run()
        self.assertEqual(result["status"], "SOLVE_BUDGET")
        self.assertLessEqual(len(self.solver.commands), 3)
        self.assertEqual(result["abaqus_solves_used"], 3)

    def test_branch_refusal_propagates_and_blocks_the_estimate(self):
        run, _ = self.campaign(extractor=_SelectiveExchange("SYB", below_e=51000.0))
        result = run.run()
        self.assertEqual(result["status"], "REFUSED")
        refused = [e for e in run.journal.records("evaluation") if e["refusal"] is not None]
        self.assertEqual(refused[-1]["refusal"]["specimen"], "B")
        report = build_campaign_report(self.definition, run.specimens, run.journal.records("evaluation"), result)
        self.assertEqual(report["engineering"]["estimate"], NO_EFFECTIVE_ESTIMATE)
        self.assertIsNone(report["m5_verdict"])
        self.assertEqual(report["model_form_robustness"]["status"], "NOT_EVALUATED")
        self.assertEqual(report["validation"], NOT_EXTERNALLY_VALIDATED)

    def test_gates(self):
        with self.assertRaises(CampaignGateRefusal):
            self.campaign(authorised="f" * 64)
        self.assertEqual(getattr(self, "solver", FakeSolver()).commands, [])
        run_b = parse_campaign_definition(synthetic_definition(
            run_type="RUN_B", fitted_parameters=["E_in_plane_mpa", "G12_mpa"], fixed_parameters={},
            start={"E_in_plane_mpa": 52000.0, "G12_mpa": 4500.0},
            bounds={"E_in_plane_mpa": [26000.0, 104000.0], "G12_mpa": [2250.0, 9000.0]}, engineering_plausibility={}))
        with self.assertRaises(RunGateRefusal):
            self.campaign(definition=run_b)

    def test_report_effective_estimate_versus_m5_verdict(self):
        run, _ = self.campaign()
        result = run.run()
        report = build_campaign_report(self.definition, run.specimens, run.journal.records("evaluation"), result)
        engineering = report["engineering"]
        self.assertEqual(engineering["practical_target"], "WITHIN_PREFERRED_TARGET")
        self.assertTrue(engineering["improved_or_consistent"])
        self.assertEqual([r["term_id"] for r in engineering["rows"]], ["A:R1", "A:R2", "A:R3", "B:R1", "B:R2"])
        self.assertEqual([r["role"] for r in engineering["rows"]], ["FIT", "FIT", "HOLDOUT", "FIT", "HOLDOUT"])
        verdict = report["m5_verdict"]
        self.assertEqual(verdict["context"], "PRODUCTION")
        # D-076: SPEC §13 is evaluated from the journal; both synthetic specimens share one truth, so it passes.
        self.assertEqual((report["family_consistency"]["status"], verdict["guards"]["family_consistency"]),
                         ("PASS", "PASS"))
        e_in = verdict["verdicts"]["E_in_plane_mpa"]
        self.assertEqual(e_in["verdict"], "IDENTIFIED")
        self.assertEqual(report["formal_output"]["released_values"], {"E_in_plane_mpa": e_in["reported_value"]})
        self.assertEqual(engineering["estimate"], EFFECTIVE_ESTIMATE)  # released by M5, so the label may be used
        self.assertEqual(report["optimizer_candidate"]["values"], result["parameters"])
        self.assertEqual(report["material_claim"], "IDENTIFIED_MATERIAL_PROPERTY")
        self.assertEqual(report["validation"], NOT_EXTERNALLY_VALIDATED)
        self.assertIn(NOT_EXTERNALLY_VALIDATED, report["reporting"])
        self.assertEqual(report["sigma"]["measurement"], {"status": "NOT_AVAILABLE",
                                                          "source": self.definition.sigma.measurement_source})
        self.assertNotIn("G12_mpa", verdict["verdicts"])
        robustness = report["model_form_robustness"]  # D-075: a range only from a complete LOO set
        self.assertIn(robustness["status"], ("AVAILABLE_COMPLETE_LOO", "UNAVAILABLE_INCOMPLETE_LOO"))
        if robustness["status"] == "UNAVAILABLE_INCOMPLETE_LOO":
            self.assertIsNone(robustness["parameters"])
        else:
            self.assertEqual(robustness["label"], "MODEL_DEPENDENCE_DIAGNOSTIC")

    def test_inconsistent_specimens_fail_section_13_and_release_no_global_value(self):
        # D-076: specimen A behaves like E 48 000 MPa, specimen B like 56 000 MPa.  No shared value is released;
        # the optimiser output stays visible as a diagnostic candidate.
        item_a, store = synthetic_specimen(self.definition, "A", self.tmp, 48000.0)
        item_b, _ = synthetic_specimen(self.definition, "B", self.tmp, 56000.0)
        self.solver = FakeSolver()
        config = CampaignRunConfig(self.tmp / "split", {"synthetic": store}, "abq2024.bat", self.solver,
                                   FakeExtractor(), {}, "m" * 64)
        run = CampaignRun(self.definition, [item_a, item_b], "m" * 64, config)
        result = run.run()
        report = build_campaign_report(self.definition, run.specimens, run.journal.records("evaluation"), result)
        self.assertEqual(report["family_consistency"]["status"], "FAIL")
        self.assertEqual(report["m5_verdict"]["guards"]["family_consistency"], "FAIL")
        self.assertEqual(report["m5_verdict"]["verdicts"]["E_in_plane_mpa"]["verdict"], "NOT_IDENTIFIABLE")
        self.assertIsNone(report["m5_verdict"]["verdicts"]["E_in_plane_mpa"]["reported_value"])
        self.assertEqual(report["formal_output"]["status"], "NO_GLOBAL_PARAMETER_VALUE")
        self.assertEqual(report["formal_output"]["released_values"], {})
        self.assertIn("FAMILY_CONSISTENCY_FAIL", report["formal_output"]["blockers"])
        self.assertNotEqual(report["engineering"]["estimate"], EFFECTIVE_ESTIMATE)
        self.assertEqual(report["optimizer_candidate"]["values"], result["parameters"])  # still visible
        self.assertIn("DIAGNOSTIC_ONLY", report["optimizer_candidate"]["role"])
        self.assertEqual(report["material_claim"], NO_MATERIAL_CLAIM)
        separate = report["family_consistency"]["separate_model"]["specimens"]
        self.assertLess(separate["A"]["estimate"]["E_in_plane_mpa"], separate["B"]["estimate"]["E_in_plane_mpa"])

    def test_engineering_window_is_reported_not_rejected(self):
        narrow = parse_campaign_definition(synthetic_definition(
            engineering_plausibility={"E_in_plane_mpa": [60000.0, 75000.0]}))
        run, _ = self.campaign(definition=narrow)
        result = run.run()
        report = build_campaign_report(narrow, run.specimens, run.journal.records("evaluation"), result)
        self.assertEqual(report["engineering"]["engineering_plausibility"]["E_in_plane_mpa"],
                         "OUTSIDE_REPORTED_NOT_REJECTED")
        self.assertEqual(report["engineering"]["estimate"], EFFECTIVE_ESTIMATE)

    def test_observation_set_mismatch_stops(self):
        item, _ = synthetic_specimen(self.definition, "A", self.tmp)
        check_observation_set(item.spec, item.frozen, item.holdout_rows, 0)
        moved = replace(item.frozen, rows=tuple(replace(r, fe_mode=r.fe_mode + 1) if r.row_id == "R2" else r
                                                for r in item.frozen.rows))
        with self.assertRaises(ObservationSetMismatch):
            check_observation_set(item.spec, moved, item.holdout_rows, 0)
        with self.assertRaises(ObservationSetMismatch):
            check_observation_set(item.spec, item.frozen, ("R2",), 0)
        with self.assertRaises(ObservationSetMismatch):
            check_observation_set(item.spec, item.frozen, item.holdout_rows, 1)


# ----------------------------------------------------------------------------- architecture guards

def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    found |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    return found


class GuardTests(unittest.TestCase):
    MODULES = (ROOT / "src/domain/campaign_definition.py", ROOT / "src/services/identification_campaign_run.py")

    def test_controlled_imports_and_one_optimiser(self):
        forbidden = ("subprocess", "abaqus_bridge", "shared_carbon_forward", "matrix_model_service", "modal_core",
                     "sp13_evidence_adapter", "scipy")
        for module in self.MODULES:
            for imported in _imports(module):
                with self.subTest(module=module.name, imported=imported):
                    self.assertFalse(any(imported == n or imported.endswith("." + n) for n in forbidden))
        text = self.MODULES[1].read_text(encoding="utf-8")
        self.assertIn("run_bounded_lm(", text)
        self.assertNotIn("def lm_step", text)

    def test_no_specimen_or_machine_literals(self):
        for module in self.MODULES:
            text = module.read_text(encoding="utf-8")
            for token in ("SP02", "SP13", "SP-02", "SP-13", "Snadwich", "D:\\", "CFRP_Face", "CFRP_T300"):
                with self.subTest(module=module.name, token=token):
                    self.assertNotIn(token, text)

    def test_legacy_identification_campaign_module_untouched(self):
        import subprocess as sp

        changed = sp.run(["git", "diff", "--name-only", "9f5f63a968759d6237facda00a4415cfe29c2257", "--",
                          "src/domain/identification_campaign.py"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(changed.stdout.strip(), "")

    def test_tool_run_refuses_an_unauthorised_hash(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import m7_campaign as tool

        with mock.patch.object(tool, "build", return_value=(None, None, None, {}, "a" * 64)):
            with self.assertRaises(CampaignGateRefusal):
                tool.main(["run", "--run-root", str(Path(tempfile.gettempdir()) / "m7-guard"), "--abaqus", "abq",
                           "--authorised-manifest-hash", "b" * 64])
            with self.assertRaises(CampaignGateRefusal):
                tool.main(["extract-archive", "--run-root", str(Path(tempfile.gettempdir()) / "m7-guard"),
                           "--abaqus", "abq", "--authorised-manifest-hash", "b" * 64])


# ----------------------------------------------------------------------------- real stores (no Abaqus)

class RealCampaignPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        roots = fixture_roots_from_environment()
        missing = sorted({"snadwich", "carbon-project-archive"} - set(roots))
        if missing:
            raise unittest.SkipTest(f"data stores {missing} not configured")
        from services.identification_campaign_run import prepare_campaign_specimens, prepare_run_manifest

        cls._directory = tempfile.TemporaryDirectory()
        cls.roots = roots
        cls.definition = load_campaign_definition(DEFINITION)
        cls.reuse = load_archive_reuse(REUSE, cls.definition.parameterisation_id)
        cls.fixtures = load_experiment_fixture_manifest(ROOT / "docs/auto_id/fixtures/real_experiment_fixtures.json")
        cls.specimens = prepare_campaign_specimens(cls.definition, ROOT, cls.fixtures, roots)
        cls.manifest, cls.manifest_hash = prepare_run_manifest(cls.definition, cls.reuse, cls.specimens, roots, ROOT,
                                                               Path(cls._directory.name))

    @classmethod
    def tearDownClass(cls):
        cls._directory.cleanup()

    def test_active_chains_reproduce_the_accepted_rows(self):
        for item in self.specimens:
            with self.subTest(specimen=item.label):
                rows = [(r.row_id, r.experimental_mode, r.fe_mode,
                         "HOLDOUT" if r.row_id in item.holdout_rows else "FIT") for r in item.frozen.rows]
                self.assertEqual(rows, ACCEPTED_ROWS[item.label])
                self.assertEqual(item.frozen.identity.registration_hash, self.fixtures.fixture(
                    item.spec.fixture_id).registration.registration_hash)
                self.assertFalse(item.registration_limited)

    def test_manifest_is_pinned_and_reuses_every_initial_point(self):
        self.assertEqual(self.manifest_hash, MANIFEST_HASH)
        sources = {(p["specimen"], p["point"]): (p["job_name"], p["source"]) for p in self.manifest["initial_points"]}
        self.assertEqual(sources, {
            ("SP02", "p0"): ("SP02_f3e592281bebce66", "archived-validated-pack"),
            ("SP02", "E_in_plane_mpa+"): ("SP02_13363f977809dbff", "archived-odb-extraction"),
            ("SP02", "E_in_plane_mpa-"): ("SP02_84753f636064e192", "archived-odb-extraction"),
            ("SP13", "p0"): ("SP13_a46d08b52995e078", "archived-validated-pack"),
            ("SP13", "E_in_plane_mpa+"): ("SP13_0e861d03c333bb0b", "archived-validated-pack"),
            ("SP13", "E_in_plane_mpa-"): ("SP13_a9df66283a168786", "archived-validated-pack")})
        self.assertEqual(self.manifest["new_solve_initial_points"], [])
        self.assertEqual(self.manifest["budgets"], {
            "max_new_abaqus_solves": 16, "max_new_solve_extractions": 16, "archive_extractions": 2,
            "max_abaqus_python_extractions": 18, "lm_evaluation_budget": 11, "reused_initial_evaluations": 3,
            "max_new_campaign_evaluations": 8})

    def test_archived_odb_identity_checks(self):
        from services.identification_campaign_run import ArchiveReuseRefusal, verify_archived_odb

        for entry in self.reuse.odbs:
            verify_archived_odb(entry, self.roots)
        entry = self.reuse.odbs[0]
        with self.assertRaises(ArchiveReuseRefusal):
            verify_archived_odb(replace(entry, odb_sha256="0" * 64), self.roots)
        with self.assertRaises(ArchiveReuseRefusal):
            verify_archived_odb(replace(entry, odb_relative_path="carbon5a/runs/E_MINUS_SP02/SP02_84753f636064e192.odb"),
                                self.roots)  # the failed, excluded attempt is never reused

    def test_tampered_accepted_rows_stop_the_campaign(self):
        from services.identification_campaign_run import prepare_campaign_specimen

        data = definition_dict(specimens__1__rows__0__fe_mode=11)
        tampered = parse_campaign_definition(data)
        with self.assertRaises(ObservationSetMismatch):
            prepare_campaign_specimen(tampered, tampered.specimen("SP13"), ROOT, self.fixtures, self.roots)


if __name__ == "__main__":
    unittest.main()
