"""M4.9 PREPARATION: SP13 twin readiness against the validated packs (no Abaqus, no Abaqus Python).

Checks that the twin's start point and its ±5 % finite-difference points (computed exactly as the
M4.8 loop does) are the M3 jobs of the validated SP13 shape packs, so the M4.9 run reuses them,
and that the truth candidate is not among them (the truth solve is a separate HUMAN gate).
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.experiment_fixture import fixture_roots_from_environment, load_experiment_fixture_manifest
from domain.forward_model_manifest import load_forward_model_manifest
from services.fe_shape_pack import load_shape_pack_record
from services.forward_builder import load_bound_forward_model, prepare_forward_job, read_reference_input
from services.identification_step import LMSettings
from services.synthetic_twin import forward_candidate, perturbed_points


FORWARD = ROOT / "docs" / "auto_id" / "forward_models" / "SP13.forward.json"
SHAPES = ROOT / "docs" / "auto_id" / "fe_shapes"
START = {"E_in_plane_mpa": 52000.0, "G12_mpa": 4500.0}  # M4_DECISION_RECORD §4 twin start
TRUTH = {"E_in_plane_mpa": 45000.0, "G12_mpa": 4000.0}  # M4_DECISION_RECORD §4 twin truth
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
        source = read_reference_input(model, roots)
        points = {"p0": dict(START), **perturbed_points(START, 0.05)}
        with tempfile.TemporaryDirectory() as directory:
            for key, point in points.items():
                job = prepare_forward_job(model, forward_candidate(model, point), source, Path(directory))
                record = load_shape_pack_record(SHAPES / f"{EXPECTED_JOBS[key]}.shape-pack.json")
                with self.subTest(key=key):
                    self.assertEqual((job.job_name, job.generated_inp_sha256),
                                     (record.job_name, record.generated_inp_sha256))
            truth = prepare_forward_job(model, forward_candidate(model, TRUTH), source, Path(directory))
            self.assertNotIn(truth.job_name, EXPECTED_JOBS.values())
            self.assertFalse((SHAPES / f"{truth.job_name}.shape-pack.json").exists())


if __name__ == "__main__":
    unittest.main()
