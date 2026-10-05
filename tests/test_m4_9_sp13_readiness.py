"""M4.9 PREPARATION: SP13 twin readiness against the validated packs (no Abaqus, no Abaqus Python).

Checks that the twin's start point and its ±5 % finite-difference points (computed exactly as the
M4.8 loop does) are the M3 jobs of the validated SP13 shape packs, so the M4.9 run reuses them,
and that the truth candidate is not among them (its pack is the archived TWIN_TRUTH pack of the
M4.9 truth gate).

Also: the committed SP13 twin definition (fixed seed, SUPERVISOR §8.1) and the branch-exchange
**negative control** on the validated real SP13 packs (§8.4). The negative control injects a
controlled in-memory exchange into one candidate FE state immediately before the M4.5 branch
tracker; it modifies no ODB, pack or permanent artifact, runs no solve, and is **not physical
FE evidence**.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.experiment_fixture import fixture_roots_from_environment, load_experiment_fixture_manifest
from domain.forward_model_manifest import load_forward_model_manifest
from services.fe_shape_pack import load_shape_pack_record
from services.forward_builder import load_bound_forward_model
from services.identification_pipeline import forward_jobs
from services.identification_step import LMSettings
from services.synthetic_twin import TWIN_SCHEMA, load_twin_definition, parse_twin_definition, perturbed_points


FORWARD = ROOT / "docs" / "auto_id" / "forward_models" / "SP13.forward.json"
SHAPES = ROOT / "docs" / "auto_id" / "fe_shapes"
START = {"E_in_plane_mpa": 52000.0, "G12_mpa": 4500.0}  # M4_DECISION_RECORD §4 twin start
TRUTH = {"E_in_plane_mpa": 45000.0, "G12_mpa": 4000.0}  # M4_DECISION_RECORD §4 twin truth
TWIN = ROOT / "docs" / "auto_id" / "twins" / "SP13.twin.json"
TWIN_HASH = "c200b2930671c9fe47c0ab44c792f326e9f5343d2c491a7723ad2f859b3f8668"
EXPECTED_JOBS = {"p0": "SP13_a46d08b52995e078", "E_in_plane_mpa-": "SP13_a9df66283a168786",
                 "E_in_plane_mpa+": "SP13_0e861d03c333bb0b", "G12_mpa-": "SP13_0328066b74b6fd78",
                 "G12_mpa+": "SP13_4c0f189b9727feaf"}


class RecordTests(unittest.TestCase):
    def test_registration_is_the_forward_models(self):
        manifest = load_forward_model_manifest(FORWARD)
        registration = json.loads((ROOT / "docs" / "registrations" / "SP13_frozen_registration.json")
                                  .read_text(encoding="utf-8"))
        self.assertEqual(registration["registration_hash"], manifest.registration_hash)

    def test_validated_packs_cover_the_finite_difference_points(self):
        step = LMSettings(mu_initial=1e-3, mu_decrease=10.0, max_step_attempts=3, solve_budget=20).finite_difference_step
        points = perturbed_points(START, step)
        self.assertEqual(points["E_in_plane_mpa+"], {"E_in_plane_mpa": 52000.0 * 1.05, "G12_mpa": 4500.0})
        for key, job in EXPECTED_JOBS.items():
            with self.subTest(key=key):
                record = load_shape_pack_record(SHAPES / f"{job}.shape-pack.json")
                self.assertEqual(record.mode_numbers, tuple(range(7, 31)))


class StoreTests(unittest.TestCase):
    def test_twin_points_render_to_the_validated_pack_jobs(self):
        roots = fixture_roots_from_environment()
        if "snadwich" not in roots:
            self.skipTest("data store 'snadwich' not configured")
        fixtures = load_experiment_fixture_manifest(ROOT / "docs/auto_id/fixtures/real_experiment_fixtures.json")
        model = load_bound_forward_model(FORWARD, ROOT, fixtures)
        points = {"p0": dict(START), **perturbed_points(START, 0.05), "truth": dict(TRUTH)}
        with tempfile.TemporaryDirectory() as directory:
            jobs = forward_jobs(model, roots, points, Path(directory))  # the twin's M4.6-owned access to M3
            truth = jobs.pop("truth")
            for key, job in jobs.items():
                record = load_shape_pack_record(SHAPES / f"{EXPECTED_JOBS[key]}.shape-pack.json")
                with self.subTest(key=key):
                    self.assertEqual((job.job_name, job.generated_inp_sha256),
                                     (record.job_name, record.generated_inp_sha256))
            self.assertNotIn(truth.job_name, EXPECTED_JOBS.values())
            # Since the truth gate (M4_DECISION_RECORD §9–§10) the truth pack is archived as TWIN_TRUTH.
            record = load_shape_pack_record(SHAPES / f"{truth.job_name}.shape-pack.json")
            self.assertEqual((record.state, record.generated_inp_sha256), ("TWIN_TRUTH", truth.generated_inp_sha256))


class TwinDefinitionTests(unittest.TestCase):
    """SUPERVISOR §8.1: fixed seed 20261005, explicit, part of the twin identity."""

    def setUp(self):
        self.data = json.loads(TWIN.read_text(encoding="utf-8"))

    def test_seed_is_explicit_and_fixed(self):
        self.assertEqual(self.data["noise_seed"], 20261005)
        definition = load_twin_definition(TWIN)
        self.assertEqual(definition.noise_seed, 20261005)
        self.assertEqual(definition.canonical["noise_seed"], 20261005)
        self.assertEqual(definition.definition_hash, TWIN_HASH)
        other = parse_twin_definition(dict(self.data, noise_seed=20261006))
        self.assertNotEqual(other.definition_hash, TWIN_HASH)
        without = {k: v for k, v in self.data.items() if k != "noise_seed"}
        with self.assertRaises(ValueError):
            parse_twin_definition(without)

    def test_definition_follows_the_decision_record(self):
        definition = load_twin_definition(TWIN)
        self.assertEqual(self.data["schema"], TWIN_SCHEMA)
        self.assertEqual(definition.forward_model_id, load_forward_model_manifest(FORWARD).forward_model_id)
        self.assertEqual(dict(definition.truth), TRUTH)
        self.assertEqual(dict(definition.start), START)
        self.assertEqual(definition.mode_numbers, tuple(range(7, 31)))
        self.assertEqual((definition.noise_relative_sd, definition.sigma, definition.k_int_enabled),
                         (0.003, 0.003, False))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BranchExchangeNegativeControlTests(unittest.TestCase):
    """SUPERVISOR §8.4: negative control on the validated real SP13 packs; not physical FE evidence.

    The frozen rows are the M4.2 SP13 set (R1 ↔ FE 10, R2 ↔ FE 11).  The candidate is the
    archived E−5 % pack.  The in-memory transformation is applied to the candidate FE state only,
    immediately before ``track_branches`` (M4.5).
    """

    @classmethod
    def setUpClass(cls):
        roots = fixture_roots_from_environment()
        missing = sorted({"snadwich", "carbon-project-archive"} - set(roots))
        if missing:
            raise unittest.SkipTest(f"data stores {missing} not configured")
        from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING
        from domain.identification_run import load_solver_profile
        from domain.registration import FrozenRegistration
        from domain.specimen_manifest import load_specimen_manifest
        from services import experimental_qc as qc
        from services.archived_baseline import load_archived_baseline, shape_pack_evidence
        from services.baseline_freeze import freeze_baseline
        from services.fe_shape_pack import load_shape_pack
        from services.identification_objective import RowSigma, build_objective_design
        from services.identification_pipeline import PipelineConfig
        from services.identification_step import parameter_bounds
        from services.shape_extraction import ExtractionExpectation

        fixtures = load_experiment_fixture_manifest(ROOT / "docs/auto_id/fixtures/real_experiment_fixtures.json")
        model = load_bound_forward_model(FORWARD, ROOT, fixtures)
        baseline = load_archived_baseline(ROOT / "docs/auto_id/baselines/SP13.carbon4c-baseline.json")
        passport = load_specimen_manifest(ROOT / model.manifest.specimen_passport.path)
        chain = qc.prepare_auto_id_experimental_input(baseline.fixture_id, roots=roots, specimen_passport=passport)
        registration_data = json.loads((ROOT / "docs/registrations/SP13_frozen_registration.json").read_text(
            encoding="utf-8"))
        registration = FrozenRegistration.from_dict(registration_data)
        records = {job: load_shape_pack_record(SHAPES / f"{job}.shape-pack.json") for job in EXPECTED_JOBS.values()}
        p0_pack = load_shape_pack(records[EXPECTED_JOBS["p0"]], roots)
        evidence = shape_pack_evidence(baseline, p0_pack, registration, chain.dataset.sorted_modes(),
                                       model.manifest.forward_model_id, chain.eligibility)
        frozen = freeze_baseline(evidence, STRICT_IDENTIFICATION_PAIRING).require_frozen()
        # Negative control only: both frozen rows as fit terms (this is not an identification design).
        design = build_objective_design(frozen, [], [], {r.row_id: RowSigma(0.003, 0.0, False) for r in frozen.rows},
                                        2)
        identity = model.passport.fe_reference.geometry_identity
        surface = model.passport.geometry_calibration.measured_surface
        subset = registration_data["registration_metrics"]["fe_mapping_node_subset"]
        expectation = ExtractionExpectation(surface.fe_instance, surface.side, 1.0e-4, identity.sha256,
                                            identity.node_count, subset["sha256"], subset["node_count"],
                                            tuple(range(7, 31)))

        def no_abaqus(*_args, **_kwargs):
            raise AssertionError("no Abaqus solve or extraction is allowed in the negative control")

        store = Path(roots["carbon-project-archive"])
        cls.pack_paths = {job: store / r.pack.location.relative_path for job, r in records.items()}
        cls.pack_sha = {job: _sha256(path) for job, path in cls.pack_paths.items()}
        cls.records, cls.frozen = records, frozen
        profile = load_solver_profile(ROOT / "docs/auto_id/solver_profiles/SP13.json")
        cls.make_config = staticmethod(lambda run_root: PipelineConfig(
            run_root=run_root, model=model, profile=profile, frozen=frozen, design=design,
            policy=STRICT_IDENTIFICATION_PAIRING,
            settings=LMSettings(mu_initial=1e-3, mu_decrease=10.0, max_step_attempts=3, solve_budget=20),
            bounds=parameter_bounds([("E_in_plane_mpa", 20000.0, 120000.0), ("G12_mpa", 1000.0, 12000.0)]),
            start=dict(START), expectation=expectation, roots=roots, abaqus_command="not-used",
            solve_executor=no_abaqus, extraction_executor=no_abaqus, archived_packs=records))

    def evaluate_with(self, transform):
        """Evaluate p0, then the archived E−5 % candidate with ``transform`` applied just before M4.5."""
        from services import identification_pipeline
        from services.identification_pipeline import IdentificationPipeline

        original = identification_pipeline.track_branches
        target = EXPECTED_JOBS["E_in_plane_mpa-"]

        def injected(policy, reference, candidate, rows, clusters=()):
            if candidate.state_id == target:
                candidate = replace(candidate, shapes=transform(candidate))
            return original(policy, reference, candidate, rows, clusters)

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        pipeline = IdentificationPipeline(self.make_config(Path(directory.name)))
        point = perturbed_points(START, 0.05)["E_in_plane_mpa-"]
        with mock.patch.object(identification_pipeline, "track_branches", injected):
            pipeline.evaluate(dict(START))
            try:
                pipeline.evaluate(point)
                refusal = None
            except identification_pipeline.BranchTrackingRefusal as caught:
                refusal = caught
        return pipeline, point, refusal

    @staticmethod
    def mixed(candidate, angle_deg=45.0):
        """§4 criterion 3: shape mixing ≥ 45° between two tracked modes (FE 10 / FE 11)."""
        shapes = candidate.shapes.copy()
        i, j = candidate.index(10), candidate.index(11)
        c, s = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
        shapes[i] = c * candidate.shapes[i] + s * candidate.shapes[j]
        shapes[j] = -s * candidate.shapes[i] + c * candidate.shapes[j]
        return shapes

    @staticmethod
    def swapped(candidate):
        shapes = candidate.shapes.copy()
        i, j = candidate.index(10), candidate.index(11)
        shapes[[i, j]] = candidate.shapes[[j, i]]
        return shapes

    def test_injected_exchange_is_refused_without_re_pairing(self):
        from services.identification_pipeline import BranchTrackingRefusal

        before = self.frozen.observation_hash
        pipeline, point, refusal = self.evaluate_with(self.mixed)
        self.assertIsNotNone(refusal)
        self.assertEqual(refusal.kind.value, "BRANCH_LOSS")
        evaluations = pipeline.journal.records("evaluation")
        self.assertEqual([e["refusal"] is None for e in evaluations], [True, False])
        self.assertEqual(evaluations[1]["fe_source"], "archived-validated-pack")
        self.assertEqual(self.frozen.observation_hash, before)  # rows neither added, dropped nor re-paired
        self.assertEqual(pipeline.identity["observation_hash"], before)
        self.assertEqual(pipeline.counts()["abaqus_solves_executed_total"], 0)
        with self.assertRaises(BranchTrackingRefusal):  # stays refused on replay, no solve
            pipeline.evaluate(point)
        self.assertEqual(pipeline.replayed_evaluations, 1)
        for job, path in self.pack_paths.items():  # no permanent artifact touched
            self.assertEqual(_sha256(path), self.pack_sha[job])
            self.assertEqual(self.pack_sha[job], self.records[job].pack.sha256)

    def test_without_injection_the_same_candidate_tracks(self):
        pipeline, _, refusal = self.evaluate_with(lambda candidate: candidate.shapes)
        self.assertIsNone(refusal)
        tracking = pipeline.journal.records("evaluation")[1]["tracking"]
        self.assertEqual({row: value[0] for row, value in tracking.items()}, {"R1": 10, "R2": 11})

    def test_pure_relabelling_is_a_tracked_crossing_not_an_exchange(self):
        # §4 criterion 3: a crossing with stable shapes is not an exchange and must be tracked (M4.5).
        pipeline, _, refusal = self.evaluate_with(self.swapped)
        self.assertIsNone(refusal)
        tracking = pipeline.journal.records("evaluation")[1]["tracking"]
        self.assertEqual({row: value[0] for row, value in tracking.items()}, {"R1": 11, "R2": 10})
        self.assertGreater(min(value[1] for value in tracking.values()), 0.99)


if __name__ == "__main__":
    unittest.main()
