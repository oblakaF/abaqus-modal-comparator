"""M7-entry wiring (SUPERVISOR 2026-10-08, D-068): the active SP-02 / SP-13 inputs use the physical registrations.

Active chain: physical passport → physical fixture (accepted physical registration) → physical forward manifest.
Historical chain (M0-M5, unchanged): legacy passport → legacy fixture (legacy registration) → legacy forward
manifest → archived CARBON-4C baseline.  Both chains render the same FE job, so the validated baseline packs stay
reusable.  No Abaqus, no identification run.
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
from domain.forward_model_manifest import bind_forward_model, carbon_candidate, load_forward_model_manifest
from domain.identification_run import load_solver_profile
from domain.specimen_manifest import load_specimen_manifest


DOCS = ROOT / "docs" / "auto_id"
FIXTURES = DOCS / "fixtures" / "real_experiment_fixtures.json"
CHAINS = {
    "SP02": {
        "active": {"passport": "SP02.physical.specimen.json", "passport_hash":
                   "bddc543721edacf47ca4bc7d72dbd93a76179b63689d0cbc5d1f6d69d6c65d0f",
                   "fixture": "SP02/bravo-1-physical", "forward": "SP02.physical.forward.json", "forward_hash":
                   "f53226a05eabb2af1a49153880e67cba4a9a723e72f7fb32ea09f2537f7080af",
                   "registration": "9b63f6c891331ba55a6ee2797f142bf0b75117d9bffbf3ab312ee08a418e882c"},
        "historical": {"passport": "SP02.specimen.json", "passport_hash":
                       "c84274ec9c2b428b96b10f8402cd8e68bcafbb262875875ec5ce62ddcd9f0e9a",
                       "fixture": "SP02/bravo-1", "forward": "SP02.forward.json", "forward_hash":
                       "bc3d9b867ba7099e2ea2829acac9c88949678de587632eba36f6bd2c944e26ba",
                       "registration": "9bf736d3650b491f8abf5f1a9abd60f6616639fa5f2f8811a896c5a04fbdc164"},
        "baseline_job": "SP02_f3e592281bebce66",
    },
    "SP13": {
        "active": {"passport": "SP13.physical.specimen.json", "passport_hash":
                   "8366c163581a79796915ccbf913a9ac170180c079294f577984b1901ff870b77",
                   "fixture": "SP13/best-physical", "forward": "SP13.physical.forward.json", "forward_hash":
                   "ec6f5ee2afd2aed60edcc90c5fa8ceb5b9afa75efd94a7020de59ff72da4d8b7",
                   "registration": "2eeeaa8698851baf33c640a5e741a91a67c6629b436700a920ba9333061cd823"},
        "historical": {"passport": "SP13.specimen.json", "passport_hash":
                       "e8162c3f472e4dae366e78a13c599d8d32a1a0e254109d40c6622bd26670f61f",
                       "fixture": "SP13/best", "forward": "SP13.forward.json", "forward_hash":
                       "f54079004c953749feb06bc0cf81c24a8545a74eb9f40d38cb3cd5fc831aa2b9",
                       "registration": "a8970e525d10173af3d3b030b1150ca24432b616e1b52f6e8cfeefe2946f58a4"},
        "baseline_job": "SP13_a46d08b52995e078",
    },
}
FE_FIELDS = ("forward_model_id", "model_input", "job_prefix", "material_role", "source_engineering_constants",
             "parameterisation", "frequency_request")


class WiringTests(unittest.TestCase):
    def setUp(self):
        self.fixtures = load_experiment_fixture_manifest(FIXTURES)

    def test_both_chains_bind_and_are_pinned(self):
        for label, chains in CHAINS.items():
            for role in ("active", "historical"):
                chain = chains[role]
                with self.subTest(specimen=label, chain=role):
                    passport = load_specimen_manifest(DOCS / "specimens" / chain["passport"])
                    manifest = load_forward_model_manifest(DOCS / "forward_models" / chain["forward"])
                    self.assertEqual(passport.manifest_hash, chain["passport_hash"])
                    self.assertEqual(manifest.manifest_hash, chain["forward_hash"])
                    self.assertEqual(passport.acquisition.fixture_id, chain["fixture"])
                    self.assertEqual(manifest.registration_hash, chain["registration"])
                    self.assertEqual(self.fixtures.fixture(chain["fixture"]).registration.registration_hash,
                                     chain["registration"])
                    bind_forward_model(manifest, passport, self.fixtures)

    def test_active_chain_is_physical_and_identified(self):
        for label, chains in CHAINS.items():
            with self.subTest(specimen=label):
                passport = load_specimen_manifest(DOCS / "specimens" / chains["active"]["passport"])
                fixture = self.fixtures.fixture(chains["active"]["fixture"])
                self.assertEqual(passport.physical_specimen_id.value, f"SP-{label[2:]}")
                self.assertEqual(fixture.physical_specimen_id, f"SP-{label[2:]}")
                self.assertTrue(fixture.registration.path.endswith("_physical_registration.json"))

    def test_active_and_historical_forward_models_are_the_same_fe_model(self):
        for label, chains in CHAINS.items():
            active = load_forward_model_manifest(DOCS / "forward_models" / chains["active"]["forward"])
            historical = load_forward_model_manifest(DOCS / "forward_models" / chains["historical"]["forward"])
            with self.subTest(specimen=label):
                for field in FE_FIELDS:
                    self.assertEqual(getattr(active, field), getattr(historical, field), field)
                profile = load_solver_profile(DOCS / "solver_profiles" / f"{label}.json")
                self.assertEqual((profile.forward_model_id, profile.job_prefix),
                                 (active.forward_model_id, active.job_prefix))
                self.assertEqual(self.fixtures.fixture(chains["active"]["fixture"]).fe,
                                 self.fixtures.fixture(chains["historical"]["fixture"]).fe)

    def test_archived_m4_records_still_reference_the_historical_chain(self):
        for label, chains in CHAINS.items():
            baseline = json.loads((DOCS / "baselines" / f"{label}.carbon4c-baseline.json").read_text(encoding="utf-8"))
            with self.subTest(specimen=label):
                self.assertEqual(baseline["forward_model"]["manifest_hash"], chains["historical"]["forward_hash"])
                self.assertEqual(baseline["registration_hash"], chains["historical"]["registration"])


class StoreTests(unittest.TestCase):
    def test_active_chain_renders_the_archived_baseline_job_and_carries_the_physical_registration(self):
        roots = fixture_roots_from_environment()
        if "snadwich" not in roots:
            self.skipTest("data store 'snadwich' not configured")
        from services.forward_builder import load_bound_forward_model, prepare_forward_job, read_reference_input
        from services.production_modal_input import load_production_modal_input

        fixtures = load_experiment_fixture_manifest(FIXTURES)
        with tempfile.TemporaryDirectory() as directory:
            for label, chains in CHAINS.items():
                model = load_bound_forward_model(DOCS / "forward_models" / chains["active"]["forward"], ROOT, fixtures)
                job = prepare_forward_job(model, carbon_candidate(52000.0, 4500.0), read_reference_input(model, roots),
                                          Path(directory))
                record = json.loads((DOCS / "fe_shapes" / f"{chains['baseline_job']}.shape-pack.json")
                                    .read_text(encoding="utf-8"))
                with self.subTest(specimen=label):
                    self.assertEqual((job.job_name, job.generated_inp_sha256),
                                     (chains["baseline_job"], record["generated_inp_sha256"]))
                    self.assertEqual(job.registration_hash, chains["active"]["registration"])
                    loaded = load_production_modal_input(chains["active"]["fixture"])
                    self.assertEqual(loaded.registration.registration_hash, chains["active"]["registration"])


if __name__ == "__main__":
    unittest.main()
