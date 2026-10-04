"""M3.1 forward-model manifest: specimen data as data, bound to the passport and fixture."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.experiment_fixture import load_experiment_fixture_manifest
from domain.forward_model_manifest import (
    CARBON_PROPERTY_SET_V1,
    PARAMETERISATIONS,
    ForwardModelManifestError,
    bind_forward_model,
    load_forward_model_manifest,
    parse_forward_model_manifest,
)
from domain.specimen_manifest import load_specimen_manifest
from m3_support import FIXTURES, FORWARD_MODELS, forward_dict, forward_manifest, synthetic_passport
from services.shared_carbon_forward import CARBON_PROPERTY_SET_V1_FIXED, sp02_forward_baseline, sp13_forward_baseline


class AcceptedForwardModelTests(unittest.TestCase):
    """The SP02/SP13 manifests carry exactly what the accepted builder hard-coded."""

    def setUp(self):
        self.fixtures = load_experiment_fixture_manifest(FIXTURES)

    def bound(self, name):
        manifest = load_forward_model_manifest(FORWARD_MODELS / f"{name}.forward.json")
        passport = load_specimen_manifest(ROOT / manifest.specimen_passport.path)
        return bind_forward_model(manifest, passport, self.fixtures)

    def test_manifests_bind_to_passport_and_fixture(self):
        for name, oracle in (("SP02", sp02_forward_baseline()), ("SP13", sp13_forward_baseline())):
            with self.subTest(name=name):
                bound = self.bound(name)
                manifest = bound.manifest
                # Material location comes from the passport by role, and equals the accepted name.
                self.assertEqual(bound.material_name, oracle.carbon_material_name)
                self.assertEqual(bound.material_name, bound.passport.materials["face"])
                self.assertEqual(manifest.job_prefix, oracle.job_prefix)
                self.assertEqual(manifest.model_input.sha256, oracle.source_inp_sha256)
                self.assertEqual(manifest.registration_hash, oracle.registration_hash)
                self.assertEqual(manifest.frequency_request.source_eigenvalue_count, oracle.source_eigenvalue_count)
                self.assertEqual(manifest.frequency_request.requested_eigenvalue_count,
                                 oracle.requested_eigenvalue_count)
                self.assertEqual(manifest.frequency_request.elastic_mode_count, oracle.elastic_mode_count)
                self.assertEqual(manifest.source_engineering_constants.to_dict(),
                                 oracle.source_engineering_constants.to_dict())
                # The model input is the fixture's pinned input (store + relative path, no machine path).
                self.assertEqual(manifest.model_input,
                                 self.fixtures.fixture(bound.passport.acquisition.fixture_id).fe.model_input)

    def test_manifest_hash_is_canonical(self):
        path = FORWARD_MODELS / "SP02.forward.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        reordered = {key: data[key] for key in reversed(list(data))}
        self.assertEqual(parse_forward_model_manifest(reordered).manifest_hash,
                         load_forward_model_manifest(path).manifest_hash)
        changed = json.loads(json.dumps(data))
        changed["frequency_request"]["requested_eigenvalue_count"] = 31
        self.assertNotEqual(parse_forward_model_manifest(changed).manifest_hash,
                            load_forward_model_manifest(path).manifest_hash)

    def test_carbon_property_set_matches_the_accepted_builder(self):
        self.assertEqual(dict(CARBON_PROPERTY_SET_V1.fixed_constants), CARBON_PROPERTY_SET_V1_FIXED)
        self.assertEqual(CARBON_PROPERTY_SET_V1.variable_constants, ("E1", "E2", "G12"))
        self.assertEqual(list(PARAMETERISATIONS), ["carbon-property-set/v1"])  # no E1 != E2 parameterisation


class ManifestRefusalTests(unittest.TestCase):
    def assertRefused(self, field_prefix, **overrides):
        with self.assertRaises(ForwardModelManifestError) as caught:
            forward_manifest(**overrides)
        self.assertTrue(caught.exception.field.startswith(field_prefix), caught.exception.field)

    def test_valid_synthetic_manifest(self):
        manifest = forward_manifest()
        self.assertEqual(manifest.material_role, "face")
        self.assertEqual(manifest.frequency_request.elastic_mode_count, 24)

    def test_structure(self):
        data = forward_dict()
        data["extra"] = 1
        with self.assertRaises(ForwardModelManifestError):
            parse_forward_model_manifest(data)
        self.assertRefused("schema", schema="auto-id/forward-model/v0")
        self.assertRefused("forward_model_id", forward_model_id="bad id")
        self.assertRefused("provenance", provenance__source_of_truth=[])

    def test_no_machine_paths(self):
        for path in (r"D:\Snadwich\SP-02\x.inp", "/data/x.inp", "../x.inp"):
            with self.subTest(path=path):
                self.assertRefused("model_input", model_input__location={"store": "synthetic", "relative_path": path})
        self.assertRefused("model_input", model_input__location={"store": "synthetic", "relative_path": "a/other.inp"})
        self.assertRefused("specimen_passport", specimen_passport__path=r"C:\passport.json")

    def test_job_prefix(self):
        for prefix in ("2SP", "SP-02", "", "SP 02"):
            with self.subTest(prefix=prefix):
                self.assertRefused("job_prefix", job_prefix=prefix)

    def test_parameterisation_and_material(self):
        self.assertRefused("parameterisation", parameterisation="carbon-e1-e2-g12/free")
        self.assertRefused("material.role", material__role="core")
        self.assertRefused("material.elastic_type", material__elastic_type="ISOTROPIC")

    def test_fixed_constants_must_match_the_property_set(self):
        for name, value in (("nu12", 0.3), ("E3", 6800.0), ("G23", 2300.0)):
            with self.subTest(name=name):
                self.assertRefused("material.source_engineering_constants",
                                   **{f"material__source_engineering_constants__{name}": value})
        self.assertRefused("material.source_engineering_constants",
                           material__source_engineering_constants__E1=float("nan"))

    def test_eigenvalue_counts_and_registration(self):
        self.assertRefused("frequency_request", frequency_request__requested_eigenvalue_count=6)
        self.assertRefused("frequency_request", frequency_request__source_eigenvalue_count=True)
        self.assertRefused("registration", registration__registration_hash="X" * 64)


class BindingTests(unittest.TestCase):
    def test_passport_pin_and_material_role(self):
        passport = synthetic_passport()
        bound = bind_forward_model(forward_manifest(passport), passport)
        self.assertEqual(bound.material_name, "CFRP_Face")
        other = synthetic_passport(test_run_id="RUN-OTHER")
        with self.assertRaises(ForwardModelManifestError):
            bind_forward_model(forward_manifest(passport), other)
        no_face = synthetic_passport(materials={"core": "PLA_Auxetic"}, specimen_type="core_tile",
                                     face_thickness_mm=None, unavailable={"face_thickness_mm": "no faces"})
        with self.assertRaises(ForwardModelManifestError) as caught:
            bind_forward_model(forward_manifest(no_face), no_face)
        self.assertEqual(caught.exception.field, "material.role")

    def test_material_name_follows_the_passport(self):
        passport = synthetic_passport(materials={"face": "CFRP_Twill", "core": "PLA_Auxetic", "adhesive": "DP420"})
        self.assertEqual(bind_forward_model(forward_manifest(passport), passport).material_name, "CFRP_Twill")

    def test_fixture_disagreement_is_refused(self):
        fixtures = load_experiment_fixture_manifest(FIXTURES)
        manifest = load_forward_model_manifest(FORWARD_MODELS / "SP02.forward.json")
        passport = load_specimen_manifest(ROOT / manifest.specimen_passport.path)
        data = json.loads((FORWARD_MODELS / "SP02.forward.json").read_text(encoding="utf-8"))
        for path, value in ((("registration", "registration_hash"), "b" * 64),
                            (("model_input", "sha256"), "c" * 64),
                            (("registration", "path"), "docs/registrations/SP13_frozen_registration.json")):
            with self.subTest(path=path):
                changed = json.loads(json.dumps(data))
                changed[path[0]][path[1]] = value
                with self.assertRaises(ForwardModelManifestError):
                    bind_forward_model(parse_forward_model_manifest(changed), passport, fixtures)
        bind_forward_model(manifest, passport, fixtures)


if __name__ == "__main__":
    unittest.main()
