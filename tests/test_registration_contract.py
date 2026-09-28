from __future__ import annotations

import copy
import dataclasses
import json
from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from coordinate_calibration import CoordinateCalibration
from domain.registration import (
    FROZEN_REGISTRATION_SCHEMA,
    REGISTRATION_DOF_COMPONENTS,
    FrozenRegistration,
    RegistrationMismatchError,
)
from scientific_state import calibration_fingerprint


CALIBRATION = CoordinateCalibration(
    mode="calibrated_physical", abaqus_unit="mm", experimental_unit="m"
).to_dict()


def source_identity():
    return {
        "path": "d:\\data\\sp13.unv",
        "size": 1234,
        "mtime_ns": 1_700_000_000_000_000_000,
        "sha256": "a" * 64,
    }


def geometry_identity():
    return {
        "schema_version": "fe-geometry-identity/1",
        "node_count": 1558721,
        "instances": ["CFRP_PLATE_BOT", "CFRP_PLATE_TOP"],
        "dof_components": ["U1", "U2", "U3"],
        "dof_count": 4676163,
        "sha256": "b" * 64,
    }


def base_kwargs():
    return {
        "experimental_source_identity": source_identity(),
        "experimental_modal_set_identity": {"modal_set_key": "SP13/set-1", "mode_count": 24},
        "fe_geometry_identity": geometry_identity(),
        "calibration": dict(CALIBRATION),
        "calibration_fingerprint": calibration_fingerprint(CALIBRATION),
        "orientation_candidate_id": "geometry-0123456789abcdef",
        "rotation": np.eye(3),
        "translation": np.array([0.1, -0.2, 0.0]),
        "coordinate_scales": np.array([1e-3, 1e-3, 1e-3]),
        "experimental_node_ids": [101, 102, 103],
        "mapped_fe_node_ids": np.array(
            ["CFRP_PLATE_TOP:1", "CFRP_PLATE_TOP:7", "CFRP_PLATE_TOP:9"], dtype=object
        ),
        "measured_dof_contract": np.ones((3, 3), dtype=bool),
        "registration_metrics": {"normalized_rms_distance": 0.0123, "matched_fraction": 1.0},
    }


def make(**overrides):
    kwargs = base_kwargs()
    kwargs.update(overrides)
    return FrozenRegistration.create(**kwargs)


class ImmutabilityTests(unittest.TestCase):
    # A
    def test_fields_cannot_be_assigned(self):
        registration = make()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            registration.orientation_candidate_id = "other"
        with self.assertRaises(TypeError):
            registration.calibration["mode"] = "manual"
        with self.assertRaises(TypeError):
            registration.experimental_source_identity["size"] = 0
        with self.assertRaises(TypeError):
            registration.registration_metrics["matched_fraction"] = 0.5
        for name in (
            "rotation",
            "translation",
            "coordinate_scales",
            "experimental_node_ids",
            "mapped_fe_node_ids",
            "measured_dof_contract",
        ):
            with self.subTest(name):
                self.assertIsInstance(getattr(registration, name), tuple)

    def test_mutating_inputs_after_construction_has_no_effect(self):
        kwargs = base_kwargs()
        registration = FrozenRegistration.create(**kwargs)
        snapshot = registration.to_dict()
        kwargs["experimental_source_identity"]["size"] = 1
        kwargs["experimental_modal_set_identity"]["mode_count"] = 1
        kwargs["fe_geometry_identity"]["instances"].append("OTHER")
        kwargs["calibration"]["mode"] = "manual"
        kwargs["rotation"][0, 0] = -1.0
        kwargs["translation"][:] = 9.0
        kwargs["coordinate_scales"][0] = 5.0
        kwargs["experimental_node_ids"].append(104)
        kwargs["mapped_fe_node_ids"][0] = "X:1"
        kwargs["measured_dof_contract"][0, 0] = False
        kwargs["registration_metrics"]["matched_fraction"] = 0.0
        self.assertEqual(registration.to_dict(), snapshot)
        self.assertEqual(hash(registration), hash(make()))

    def test_to_dict_output_is_detached(self):
        registration = make()
        payload = registration.to_dict()
        payload["fe_geometry_identity"]["instances"].append("OTHER")
        payload["rotation"][0][0] = 7.0
        self.assertEqual(registration.to_dict(), make().to_dict())


class SerializationTests(unittest.TestCase):
    # B
    def test_round_trip_preserves_content_and_hash(self):
        registration = make()
        restored = FrozenRegistration.from_dict(registration.to_dict())
        self.assertEqual(restored, registration)
        self.assertEqual(restored.registration_hash, registration.registration_hash)
        self.assertEqual(restored.to_dict(), registration.to_dict())
        via_json = FrozenRegistration.from_dict(json.loads(json.dumps(registration.to_dict())))
        self.assertEqual(via_json.to_dict(), registration.to_dict())
        self.assertEqual(restored.registration_schema_version, FROZEN_REGISTRATION_SCHEMA)
        self.assertEqual(
            registration.to_dict()["measured_dof_contract"]["components"],
            list(REGISTRATION_DOF_COMPONENTS),
        )

    # C
    def test_hash_is_stable_across_equivalent_inputs(self):
        first = make()
        reordered = {
            key: value for key, value in reversed(list(geometry_identity().items()))
        }
        second = make(
            fe_geometry_identity=reordered,
            calibration={key: CALIBRATION[key] for key in reversed(list(CALIBRATION))},
            rotation=[[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            translation=(0.1, -0.2, -0.0),
            coordinate_scales=[1e-3] * 3,
            experimental_node_ids=np.array([101, 102, 103]),
            mapped_fe_node_ids=["CFRP_PLATE_TOP:1", "CFRP_PLATE_TOP:7", "CFRP_PLATE_TOP:9"],
            measured_dof_contract=[[True] * 3] * 3,
            registration_metrics={"matched_fraction": 1.0, "normalized_rms_distance": 0.0123},
        )
        self.assertEqual(first.registration_hash, second.registration_hash)
        self.assertEqual(first, second)
        self.assertRegex(first.registration_hash, r"^[0-9a-f]{64}$")

    # D
    def test_every_scientific_category_changes_the_hash(self):
        base = make().registration_hash
        mask = np.ones((3, 3), dtype=bool)
        mask[2, 1] = False
        manual = CoordinateCalibration(mode="manual", manual_scale=0.001).to_dict()
        rotated = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
        changes = {
            "source identity": {"experimental_source_identity": {**source_identity(), "sha256": "c" * 64}},
            "modal-set identity": {"experimental_modal_set_identity": {"modal_set_key": "SP13/set-2", "mode_count": 24}},
            "FE geometry identity": {"fe_geometry_identity": {**geometry_identity(), "sha256": "d" * 64}},
            "calibration": {"calibration": manual, "calibration_fingerprint": calibration_fingerprint(manual)},
            "orientation candidate": {"orientation_candidate_id": "geometry-fedcba9876543210"},
            "rotation": {"rotation": rotated},
            "translation": {"translation": [0.1, -0.2, 0.001]},
            "coordinate scales": {"coordinate_scales": [1e-3, 1e-3, 2e-3]},
            "experimental nodes": {"experimental_node_ids": [101, 102, 104]},
            "mapped FE nodes": {"mapped_fe_node_ids": ["CFRP_PLATE_TOP:1", "CFRP_PLATE_TOP:7", "CFRP_PLATE_TOP:8"]},
            "measured DOF contract": {"measured_dof_contract": mask},
            "registration metrics": {"registration_metrics": {"normalized_rms_distance": 0.02, "matched_fraction": 1.0}},
        }
        for name, override in changes.items():
            with self.subTest(name):
                self.assertNotEqual(make(**override).registration_hash, base)

    # F
    def test_tampered_payload_with_stale_hash_is_rejected(self):
        payload = make().to_dict()
        tampered_cases = {
            "metric": ("registration_metrics", lambda p: p["registration_metrics"].update(matched_fraction=0.5)),
            "node": ("mapped_fe_node_ids", lambda p: p["mapped_fe_node_ids"].__setitem__(0, "CFRP_PLATE_TOP:2")),
            "geometry": ("fe_geometry_identity", lambda p: p["fe_geometry_identity"].update(sha256="e" * 64)),
            "dof": ("measured_dof_contract", lambda p: p["measured_dof_contract"]["mask"][0].__setitem__(0, False)),
        }
        for name, (_, tamper) in tampered_cases.items():
            with self.subTest(name):
                modified = copy.deepcopy(payload)
                tamper(modified)
                with self.assertRaisesRegex(ValueError, "registration_hash does not match"):
                    FrozenRegistration.from_dict(modified)

    def test_payload_schema_and_hash_format_are_validated(self):
        payload = make().to_dict()
        wrong_schema = {**payload, "registration_schema_version": "frozen-registration/2"}
        with self.assertRaisesRegex(ValueError, "registration_schema_version"):
            FrozenRegistration.from_dict(wrong_schema)
        with self.assertRaisesRegex(ValueError, "registration_hash"):
            FrozenRegistration.from_dict({**payload, "registration_hash": "not-a-hash"})
        missing = dict(payload)
        del missing["fe_geometry_identity"]
        with self.assertRaisesRegex(ValueError, "fe_geometry_identity"):
            FrozenRegistration.from_dict(missing)


class CompatibilityTests(unittest.TestCase):
    # E
    def test_matching_identities_pass(self):
        registration = make()
        self.assertTrue(registration.check_compatible(source_identity(), geometry_identity()))
        reordered = dict(reversed(list(geometry_identity().items())))
        self.assertTrue(registration.check_compatible(source_identity(), reordered))

    def test_changed_experiment_raises(self):
        registration = make()
        for change in ({"sha256": "c" * 64}, {"mtime_ns": 1}, {"path": "d:\\data\\sp05.unv"}):
            with self.subTest(change):
                with self.assertRaises(RegistrationMismatchError) as context:
                    registration.check_compatible({**source_identity(), **change}, geometry_identity())
                self.assertEqual(context.exception.field, "experimental_source_identity")
        legacy_only = {key: source_identity()[key] for key in ("path", "size", "mtime_ns")}
        with self.assertRaises(RegistrationMismatchError):
            registration.check_compatible(legacy_only, geometry_identity())
        with self.assertRaises(RegistrationMismatchError):
            registration.check_compatible(None, geometry_identity())

    def test_changed_fe_geometry_raises(self):
        registration = make()
        for change in ({"sha256": "d" * 64}, {"node_count": 3}, {"schema_version": "fe-geometry-identity/2"}):
            with self.subTest(change):
                with self.assertRaises(RegistrationMismatchError) as context:
                    registration.check_compatible(source_identity(), {**geometry_identity(), **change})
                self.assertEqual(context.exception.field, "fe_geometry_identity")
        with self.assertRaises(RegistrationMismatchError):
            registration.check_compatible(source_identity(), None)

    def test_type_confusion_is_a_mismatch(self):
        registration = make()
        with self.assertRaises(RegistrationMismatchError):
            registration.check_compatible({**source_identity(), "size": 1234.0}, geometry_identity())


class ContractScopeTests(unittest.TestCase):
    # G
    def test_no_full_fe_model_or_material_fields(self):
        names = {field.name for field in dataclasses.fields(FrozenRegistration)}
        self.assertEqual(
            names,
            {
                "experimental_source_identity",
                "experimental_modal_set_identity",
                "fe_geometry_identity",
                "calibration",
                "calibration_fingerprint",
                "orientation_candidate_id",
                "rotation",
                "translation",
                "coordinate_scales",
                "experimental_node_ids",
                "mapped_fe_node_ids",
                "measured_dof_contract",
                "registration_metrics",
                "registration_schema_version",
                "registration_hash",
            },
        )
        forbidden = ("stiff", "mass", "material", "basis", "d11", "d12", "d66", "ex", "ey", "gxy", "optimizer", "model")
        for name in names:
            tokens = name.lower().split("_")
            with self.subTest(name):
                self.assertFalse(set(tokens) & set(forbidden))

    def test_unknown_payload_keys_are_rejected(self):
        payload = make().to_dict()
        with self.assertRaisesRegex(ValueError, "basis_km_hash"):
            FrozenRegistration.from_dict({**payload, "basis_km_hash": "f" * 64})

    # H
    def test_non_json_safe_values_are_rejected_not_stringified(self):
        invalid = {
            "object in metrics": {"registration_metrics": {"note": object()}},
            "complex in metrics": {"registration_metrics": {"value": 1 + 2j}},
            "array in metrics": {"registration_metrics": {"distances": np.zeros(3)}},
            "path in identity": {"experimental_source_identity": {**source_identity(), "path": Path("x")}},
            "non-string key": {"calibration": {**CALIBRATION, 1: "x"}},
            "set in modal set": {"experimental_modal_set_identity": {"modes": {1, 2}}},
        }
        for name, override in invalid.items():
            with self.subTest(name):
                with self.assertRaises(TypeError):
                    make(**override)
        with self.assertRaises(ValueError):
            make(registration_metrics={"value": float("nan")})
        with self.assertRaises(TypeError):
            make(experimental_node_ids=[101, 102, 1.5])
        with self.assertRaises(TypeError):
            make(measured_dof_contract=np.ones((3, 3), dtype=int))

    def test_structural_validation(self):
        invalid = {
            "fingerprint mismatch": {"calibration_fingerprint": "0" * 64},
            "non-orthogonal rotation": {"rotation": [[2, 0, 0], [0, 1, 0], [0, 0, 1]]},
            "rotation shape": {"rotation": np.eye(2)},
            "non-positive scale": {"coordinate_scales": [1e-3, 0.0, 1e-3]},
            "non-finite translation": {"translation": [0.0, np.inf, 0.0]},
            "mapping length": {"mapped_fe_node_ids": ["CFRP_PLATE_TOP:1"]},
            "DOF shape": {"measured_dof_contract": np.ones((3, 2), dtype=bool)},
            "duplicate experimental node": {"experimental_node_ids": [101, 101, 103]},
            "empty candidate id": {"orientation_candidate_id": "  "},
            "empty mapping": {"experimental_node_ids": [], "mapped_fe_node_ids": [], "measured_dof_contract": np.ones((0, 3), dtype=bool)},
            "source identity keys": {"experimental_source_identity": {"path": "x"}},
            "geometry identity hash": {"fe_geometry_identity": {**geometry_identity(), "sha256": "short"}},
        }
        for name, override in invalid.items():
            with self.subTest(name):
                with self.assertRaises(ValueError):
                    make(**override)

    def test_mirrored_rotation_is_allowed(self):
        mirrored = make(rotation=np.diag([1.0, 1.0, -1.0]))
        self.assertNotEqual(mirrored.registration_hash, make().registration_hash)

    def test_package_exports(self):
        import domain

        self.assertIs(domain.FrozenRegistration, FrozenRegistration)
        self.assertIs(domain.RegistrationMismatchError, RegistrationMismatchError)


if __name__ == "__main__":
    unittest.main()
