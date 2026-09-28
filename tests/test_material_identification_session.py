from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain import material_identification_session as session_module
from domain.evidence import EvidenceProvenance, EvidenceSourceIdentity, SensitivityEvidence
from domain.identification_model import (
    EFFECTIVE_FACE_SHEET_MODEL,
    STAGE_A_BENDING_MODEL,
    IdentificationModelDefinition,
    IdentificationParameterDefinition,
)
from domain.material_identification_session import (
    FrozenRegistrationReference,
    MaterialIdentificationEvidenceReference,
    MaterialIdentificationSession,
    MaterialIdentificationSourceIdentities,
    MaterialIdentificationTaskDefinition,
    ParameterBounds,
)
from domain.registration import FrozenRegistration
from scientific_state import calibration_fingerprint


MODELS = (STAGE_A_BENDING_MODEL, EFFECTIVE_FACE_SHEET_MODEL)
STAGE_A_BOUNDS = {
    "D11": ParameterBounds(5.0, 50.0, "N·m"),
    "D12": ParameterBounds(-10.0, 10.0, "N·m"),
    "D66": ParameterBounds(1.0, 20.0, "N·m"),
}
FACE_BOUNDS = {
    "Ex": ParameterBounds(30000.0, 70000.0, "MPa"),
    "Ey": ParameterBounds(30000.0, 70000.0, "MPa"),
    "Gxy": ParameterBounds(2000.0, 12000.0, "MPa"),
}
CALIBRATION = {"mode": "manual", "manual_scale": 1.0}


def _registration(
    *,
    experiment_digit="a",
    geometry_digit="b",
    geometry_schema="fe-geometry-identity/2",
    with_sha256=True,
):
    experimental = {"path": "c:/data/experiment.unv", "size": 2048, "mtime_ns": 7}
    if with_sha256:
        experimental["sha256"] = experiment_digit * 64
    return FrozenRegistration.create(
        experimental_source_identity=experimental,
        experimental_modal_set_identity=None,
        fe_geometry_identity={
            "schema_version": geometry_schema,
            "node_count": 12,
            "instances": ["PLATE-1"],
            "dof_components": ["U1", "U2", "U3"],
            "sha256": geometry_digit * 64,
        },
        calibration=CALIBRATION,
        calibration_fingerprint=calibration_fingerprint(CALIBRATION),
        orientation_candidate_id="geometry-0123456789abcdef",
        rotation=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        translation=[0.0, 0.0, 0.0],
        coordinate_scales=[1.0, 1.0, 1.0],
        experimental_node_ids=[1, 2],
        mapped_fe_node_ids=["PLATE-1:1", "PLATE-1:2"],
        measured_dof_contract=[[False, False, True], [False, False, True]],
        registration_metrics={},
    )


REGISTRATION = _registration()
OTHER_REGISTRATION = _registration(experiment_digit="c", geometry_digit="d")
REGISTRATIONS = (REGISTRATION, OTHER_REGISTRATION)


def _synthetic_model(**changes):
    fields = dict(
        model_id="synthetic_spring",
        display_name="Synthetic spring model",
        parameter_definitions=(
            IdentificationParameterDefinition("k_axial", "k", "N/m", "Synthetic axial spring"),
            IdentificationParameterDefinition("c_loss", "c", "dimensionless", "Synthetic loss"),
        ),
        frozen_assumptions=("Mass fixed",),
        limitations=("Synthetic test model",),
        workflow_status="validation_only",
    )
    fields.update(changes)
    return IdentificationModelDefinition.create(**fields)


SYNTHETIC_BOUNDS = {
    "k_axial": ParameterBounds(1.0, 10.0, "N/m"),
    "c_loss": ParameterBounds(0.0, 0.1, "dimensionless"),
}


class SessionTestBase(unittest.TestCase):
    def setUp(self):
        self.sources = MaterialIdentificationSourceIdentities(
            specimen_label="specimen-a", source_label="modal test 1", source_uri="project://a"
        )
        self.provenance = EvidenceProvenance(
            producer="material-identification-session test",
            method="user-authored task definition",
            details={"scientific_execution": False},
        )

    def task(self, model, selected=None, bounds=None, **changes):
        if bounds is None:
            bounds = STAGE_A_BOUNDS if model is STAGE_A_BENDING_MODEL else FACE_BOUNDS
        values = dict(
            model=model,
            selected_parameter_ids=model.parameter_ids if selected is None else selected,
            parameter_bounds=bounds,
            weighting_selection="UNIFORM",
            provenance=self.provenance,
        )
        values.update(changes)
        return MaterialIdentificationTaskDefinition(**values)

    def session(self, task, sources=None, registration=REGISTRATION, **changes):
        values = dict(
            session_id="session-1",
            created_at=datetime(2026, 9, 29, 8, 0, tzinfo=timezone.utc),
            task_definition=task,
            source_identities=self.sources if sources is None else sources,
            registration=registration,
        )
        values.update(changes)
        return MaterialIdentificationSession.create(**values)

    def evidence(self, evidence_id="sensitivity-1"):
        return SensitivityEvidence.create(
            evidence_id=evidence_id,
            timestamp=datetime(2026, 9, 29, 8, 30, tzinfo=timezone.utc),
            source_identity=EvidenceSourceIdentity(source_id="stored-output", source_type="test"),
            provenance=self.provenance,
            status="READY",
            content={"stored": True},
        )


class ModelDrivenSessionTests(SessionTestBase):
    """Model binding (C4-R2 behaviour, now with a registration bound)."""

    def test_effective_face_sheet_session(self):
        session = self.session(self.task(EFFECTIVE_FACE_SHEET_MODEL))
        task = session.task_definition
        self.assertEqual(task.selected_parameter_ids, ("Ex", "Ey", "Gxy"))
        self.assertEqual(task.identification_model_id, "effective_face_sheet")
        self.assertEqual(task.identification_model_hash, EFFECTIVE_FACE_SHEET_MODEL.definition_hash)
        self.assertEqual(session.readiness().reasons, ())

    def test_same_model_can_serve_different_sources(self):
        task = self.task(STAGE_A_BENDING_MODEL)
        first = self.session(task)
        second = self.session(task, MaterialIdentificationSourceIdentities(specimen_label="specimen-b"))
        self.assertNotEqual(first.source_identities, second.source_identities)
        self.assertEqual(first.task_definition, second.task_definition)

    def test_parameters_outside_the_model_are_refused(self):
        cases = (
            (STAGE_A_BENDING_MODEL, ("Ex", "Ey", "Gxy")),
            (STAGE_A_BENDING_MODEL, ("D11", "Gxy")),
            (EFFECTIVE_FACE_SHEET_MODEL, ("D11", "D12", "D66")),
            (STAGE_A_BENDING_MODEL, ("PoissonRatio",)),
            (EFFECTIVE_FACE_SHEET_MODEL, ("PoissonRatio",)),
        )
        for model, selected in cases:
            with self.subTest(model=model.model_id, selected=selected):
                with self.assertRaisesRegex(
                    ValueError, f"not defined by identification model '{model.model_id}'"
                ):
                    self.task(model, selected=selected)

    def test_selection_must_be_non_empty_unique_and_ordered(self):
        for selected in ((), ("D11", "D11")):
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                self.task(STAGE_A_BENDING_MODEL, selected=selected)
        task = self.task(STAGE_A_BENDING_MODEL, selected=("D66", "D11"))
        self.assertEqual(task.selected_parameter_ids, ("D66", "D11"))

    def test_synthetic_model_parameters_are_accepted(self):
        model = _synthetic_model()
        session = self.session(self.task(model, bounds=SYNTHETIC_BOUNDS))
        self.assertEqual(session.task_definition.selected_parameter_ids, ("k_axial", "c_loss"))
        self.assertTrue(session.readiness().ready)
        with self.assertRaises(ValueError):
            self.task(model, selected=("Ex",), bounds={})

    # G
    def test_restoring_requires_the_exact_model_definition(self):
        payload = self.session(self.task(STAGE_A_BENDING_MODEL)).to_json()
        altered = IdentificationModelDefinition.create(
            **{
                **{
                    name: getattr(STAGE_A_BENDING_MODEL, name)
                    for name in IdentificationModelDefinition.FIELD_NAMES[:-2]
                },
                "limitations": STAGE_A_BENDING_MODEL.limitations + ("Extra limitation.",),
            }
        )
        with self.assertRaisesRegex(ValueError, "definition hash mismatch"):
            MaterialIdentificationSession.from_json(
                payload, models=(altered, EFFECTIVE_FACE_SHEET_MODEL), registrations=REGISTRATIONS
            )
        with self.assertRaisesRegex(ValueError, "Unknown identification model 'stage_a_bending'"):
            MaterialIdentificationSession.from_json(
                payload, models=EFFECTIVE_FACE_SHEET_MODEL, registrations=REGISTRATIONS
            )
        restored = MaterialIdentificationSession.from_json(
            payload, models=(altered, STAGE_A_BENDING_MODEL), registrations=REGISTRATIONS
        )
        self.assertIs(restored.task_definition.model, STAGE_A_BENDING_MODEL)
        tampered = json.loads(payload)
        tampered["task_definition"]["identification_model_hash"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "definition hash mismatch"):
            MaterialIdentificationSession.from_dict(tampered, models=MODELS, registrations=REGISTRATIONS)

    # Q
    def test_campaign_bounds_belong_to_model_parameters_and_units(self):
        self.assertEqual(self.task(STAGE_A_BENDING_MODEL).bounds_for("D11"), STAGE_A_BOUNDS["D11"])
        self.assertEqual(self.task(EFFECTIVE_FACE_SHEET_MODEL).bounds_for("Gxy"), FACE_BOUNDS["Gxy"])
        invalid = {
            "absent parameter": {**STAGE_A_BOUNDS, "Ex": ParameterBounds(1.0, 2.0, "MPa")},
            "wrong unit": {**STAGE_A_BOUNDS, "D11": ParameterBounds(5.0, 50.0, "MPa")},
            "face in N·m": {**FACE_BOUNDS, "Ex": ParameterBounds(1.0, 2.0, "N·m")},
        }
        for name, bounds in invalid.items():
            model = STAGE_A_BENDING_MODEL if "D11" in bounds else EFFECTIVE_FACE_SHEET_MODEL
            with self.subTest(name), self.assertRaises(ValueError):
                self.task(model, bounds=bounds)
        for lower, upper in ((10.0, 1.0), (1.0, float("nan"))):
            with self.subTest(lower=lower, upper=upper), self.assertRaises(ValueError):
                ParameterBounds(lower, upper, "N·m")
        before = STAGE_A_BENDING_MODEL.definition_hash
        wide = self.task(STAGE_A_BENDING_MODEL, bounds={"D11": ParameterBounds(1.0, 1000.0, "N·m")})
        self.assertEqual(wide.identification_model_hash, before)

    def test_readiness_requires_bounds_for_selected_parameters(self):
        session = self.session(self.task(STAGE_A_BENDING_MODEL, bounds={"D11": STAGE_A_BOUNDS["D11"]}))
        self.assertEqual(
            session.readiness().reasons,
            ("Selected parameter 'D12' has no bounds.", "Selected parameter 'D66' has no bounds."),
        )

    def test_readiness_detects_an_altered_in_memory_model(self):
        model = _synthetic_model()
        session = self.session(self.task(model, bounds=SYNTHETIC_BOUNDS))
        object.__setattr__(model, "limitations", ("silently changed",))
        readiness = session.readiness()
        self.assertFalse(readiness.ready)
        self.assertTrue(any("synthetic_spring" in item for item in readiness.reasons))

    def test_frozen_assumptions_come_from_the_model(self):
        face = self.task(EFFECTIVE_FACE_SHEET_MODEL)
        self.assertIn("Core representation is frozen.", face.frozen_assumptions)
        stage_a = self.task(STAGE_A_BENDING_MODEL)
        text = json.dumps(stage_a.to_dict()).lower()
        for word in ("core", "density", "adhesive"):
            self.assertNotIn(word, text)
        payload = self.session(face).to_dict()
        payload["task_definition"]["frozen_assumptions"] = ["Core representation is frozen."]
        with self.assertRaisesRegex(ValueError, "frozen assumptions differ"):
            MaterialIdentificationSession.from_dict(payload, models=MODELS, registrations=REGISTRATIONS)

    def test_caller_mutation_cannot_alter_the_session(self):
        bounds = dict(STAGE_A_BOUNDS)
        selected = ["D11", "D66"]
        session = self.session(self.task(STAGE_A_BENDING_MODEL, selected=selected, bounds=bounds))
        before = session.to_json()
        bounds["D11"] = ParameterBounds(0.1, 0.2, "N·m")
        selected.append("D12")
        self.assertEqual(session.to_json(), before)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            session.task_definition.selected_parameter_ids = ("D12",)
        with self.assertRaises(TypeError):
            session.registration_reference.experimental_source_identity["sha256"] = "0" * 64

    def test_evidence_from_different_sources_is_rejected(self):
        reference = MaterialIdentificationEvidenceReference.from_evidence(
            self.evidence(), MaterialIdentificationSourceIdentities(specimen_label="specimen-b")
        )
        with self.assertRaisesRegex(ValueError, "source mismatch"):
            self.session(self.task(STAGE_A_BENDING_MODEL), evidence_references=(reference,))


class RegistrationBindingTests(SessionTestBase):
    """C4-R3: exact FrozenRegistration binding."""

    # A
    def test_stage_a_session_with_registration_is_ready(self):
        session = self.session(self.task(STAGE_A_BENDING_MODEL))
        reference = session.registration_reference
        self.assertIsInstance(reference, FrozenRegistrationReference)
        self.assertEqual(reference.registration_hash, REGISTRATION.registration_hash)
        self.assertEqual(reference.experimental_content_sha256, "a" * 64)
        self.assertEqual(reference.fe_geometry_identity["schema_version"], "fe-geometry-identity/2")
        self.assertEqual(session.readiness().reasons, ())
        self.assertTrue(session.readiness().ready)

    # B / M
    def test_same_registration_with_either_model(self):
        stage_a = self.session(self.task(STAGE_A_BENDING_MODEL))
        face = self.session(self.task(EFFECTIVE_FACE_SHEET_MODEL))
        self.assertEqual(stage_a.registration_reference, face.registration_reference)
        self.assertNotEqual(
            stage_a.task_definition.identification_model_hash,
            face.task_definition.identification_model_hash,
        )
        self.assertEqual(REGISTRATION.registration_hash, _registration().registration_hash)
        self.assertEqual(STAGE_A_BENDING_MODEL.definition_hash, stage_a.task_definition.identification_model_hash)
        self.assertTrue(stage_a.readiness().ready and face.readiness().ready)

    # L
    def test_same_model_with_two_registrations(self):
        task = self.task(STAGE_A_BENDING_MODEL)
        first = self.session(task, registration=REGISTRATION)
        second = self.session(task, registration=OTHER_REGISTRATION)
        self.assertEqual(first.task_definition, second.task_definition)
        self.assertNotEqual(first.registration_reference, second.registration_reference)
        self.assertNotEqual(first.to_json(), second.to_json())
        self.assertTrue(first.readiness().ready and second.readiness().ready)

    # C
    def test_session_without_registration_is_not_ready(self):
        session = self.session(self.task(STAGE_A_BENDING_MODEL), registration=None)
        self.assertIsNone(session.registration_reference)
        readiness = session.readiness()
        self.assertFalse(readiness.ready)
        self.assertEqual(
            readiness.reasons,
            ("No FrozenRegistration is bound; a production session requires one.",),
        )
        restored = MaterialIdentificationSession.from_json(session.to_json(), models=MODELS)
        self.assertIsNone(restored.registration_reference)

    # D
    def test_fake_registration_is_refused(self):
        fake = REGISTRATION.to_dict()
        for candidate in (fake, dict(fake, registration_hash="f" * 64)):
            with self.assertRaisesRegex(TypeError, "real FrozenRegistration"):
                FrozenRegistrationReference.from_registration(candidate)
            with self.assertRaisesRegex(TypeError, "real FrozenRegistration"):
                self.session(self.task(STAGE_A_BENDING_MODEL), registration=candidate)
        with self.assertRaisesRegex(TypeError, "from_registration"):
            FrozenRegistrationReference(
                registration_hash=REGISTRATION.registration_hash,
                registration_schema_version=REGISTRATION.registration_schema_version,
                experimental_source_identity={"sha256": "a" * 64},
                fe_geometry_identity={"schema_version": "fe-geometry-identity/2", "sha256": "b" * 64},
            )

    # E
    def test_legacy_experimental_identity_is_refused(self):
        legacy = _registration(with_sha256=False)
        with self.assertRaisesRegex(ValueError, "no SHA-256 content identity"):
            FrozenRegistrationReference.from_registration(legacy)

    # F
    def test_geometry_identity_v1_is_refused(self):
        v1 = _registration(geometry_schema="fe-geometry-identity/1")
        with self.assertRaisesRegex(ValueError, "fe-geometry-identity/2"):
            FrozenRegistrationReference.from_registration(v1)

    # H
    def test_round_trip_preserves_both_bindings(self):
        for model, selected in ((STAGE_A_BENDING_MODEL, ("D66", "D11")), (EFFECTIVE_FACE_SHEET_MODEL, ("Gxy", "Ex"))):
            with self.subTest(model.model_id):
                session = self.session(self.task(model, selected=selected))
                text = session.to_json()
                payload = json.loads(text)
                self.assertEqual(payload["schema_version"], "material-identification-session/3.0")
                self.assertEqual(payload["task_definition"]["identification_model_hash"], model.definition_hash)
                self.assertEqual(payload["task_definition"]["selected_parameter_ids"], list(selected))
                registration = payload["registration"]
                self.assertEqual(registration["registration_hash"], REGISTRATION.registration_hash)
                self.assertEqual(registration["experimental_source_identity"]["sha256"], "a" * 64)
                self.assertEqual(registration["fe_geometry_identity"]["schema_version"], "fe-geometry-identity/2")
                restored = MaterialIdentificationSession.from_json(
                    text, models=MODELS, registrations=REGISTRATIONS
                )
                self.assertEqual(restored, session)
                self.assertEqual(restored.to_json(), text)

    # I / J / K
    def test_tampered_registration_reference_is_refused(self):
        payload = self.session(self.task(STAGE_A_BENDING_MODEL)).to_dict()
        tampers = {
            "registration hash": ("registration_hash", None, "e" * 64, "Unknown FrozenRegistration"),
            "experimental identity": ("experimental_source_identity", "sha256", "9" * 64, "differs"),
            "geometry identity": ("fe_geometry_identity", "sha256", "8" * 64, "differs"),
            "geometry schema": ("fe_geometry_identity", "schema_version", "fe-geometry-identity/1", "differs"),
        }
        for name, (field_name, key, value, message) in tampers.items():
            with self.subTest(name):
                tampered = json.loads(json.dumps(payload))
                if key is None:
                    tampered["registration"][field_name] = value
                else:
                    tampered["registration"][field_name][key] = value
                with self.assertRaisesRegex(ValueError, message):
                    MaterialIdentificationSession.from_dict(
                        tampered, models=MODELS, registrations=REGISTRATIONS
                    )
        with self.assertRaisesRegex(ValueError, "Unknown FrozenRegistration"):
            MaterialIdentificationSession.from_dict(payload, models=MODELS)

    # N / O
    def test_reference_holds_no_calibration_or_stiffness_identity(self):
        session = self.session(self.task(STAGE_A_BENDING_MODEL))
        reference_payload = session.registration_reference.to_dict()
        self.assertEqual(
            set(reference_payload),
            {"registration_hash", "registration_schema_version",
             "experimental_source_identity", "fe_geometry_identity"},
        )
        reference_text = json.dumps(reference_payload).lower()
        for forbidden in ("calibration", "manual_scale", "basis_km", "stiffness", "fe_model", "optimizer"):
            self.assertNotIn(forbidden, reference_text)
        # The model's own assumptions may say "stiffness"; the session as a whole
        # still carries no calibration payload and no FE model/stiffness identity.
        text = session.to_json().lower()
        for forbidden in ("calibration", "manual_scale", "basis_km", "fe_model", "optimizer"):
            self.assertNotIn(forbidden, text)
        self.assertEqual(
            set(session.to_dict()["source_identities"]),
            {"specimen_label", "source_label", "source_uri"},
        )

    # P
    def test_bindings_do_not_depend_on_specimen_labels(self):
        task = self.task(EFFECTIVE_FACE_SHEET_MODEL)
        sessions = [
            self.session(task, MaterialIdentificationSourceIdentities(specimen_label=label))
            for label in ("SP13", "SP14", "specimen-x")
        ]
        self.assertTrue(all(item.readiness().ready for item in sessions))
        self.assertTrue(
            all(item.registration_reference == sessions[0].registration_reference for item in sessions)
        )
        self.assertEqual(len({item.task_definition.identification_model_hash for item in sessions}), 1)
        module_text = Path(session_module.__file__).read_text(encoding="utf-8").lower()
        self.assertNotIn("sp13", module_text)
        for name in ("UNKNOWN_PARAMETER_IDS", "FROZEN_PARAMETER_IDS", "SUPPORTED_PARAMETER_IDS",
                     "MaterialParameterDefinition", "standard_material_parameter_definitions"):
            self.assertFalse(hasattr(session_module, name), name)

    def test_older_schemas_are_rejected_explicitly(self):
        payload = self.session(self.task(EFFECTIVE_FACE_SHEET_MODEL)).to_dict()
        for schema, message in (
            ("material-identification-session/1.0", "schema 1.0 hard-coded the Ex/Ey/Gxy"),
            ("material-identification-session/2.0", "schema 2.0 has no FrozenRegistration binding"),
        ):
            with self.subTest(schema):
                with self.assertRaisesRegex(ValueError, message):
                    MaterialIdentificationSession.from_dict(
                        dict(payload, schema_version=schema), models=MODELS, registrations=REGISTRATIONS
                    )

    # R
    def test_evidence_references_bind_only_to_descriptive_source_labels(self):
        # EVIDENCE BINDING GAP: EvidenceRecord carries no model hash, registration
        # hash, or experimental content identity, so a reference can prove only
        # that it was made for the same descriptive source labels.
        reference = MaterialIdentificationEvidenceReference.from_evidence(self.evidence(), self.sources)
        stage_a = self.session(self.task(STAGE_A_BENDING_MODEL), evidence_references=(reference,))
        other = self.session(
            self.task(EFFECTIVE_FACE_SHEET_MODEL),
            registration=OTHER_REGISTRATION,
            evidence_references=(reference,),
        )
        self.assertTrue(stage_a.readiness().ready and other.readiness().ready)
        self.assertNotIn("registration_hash", reference.to_dict())
        self.assertNotIn("identification_model_hash", reference.to_dict())
        restored = MaterialIdentificationSession.from_json(
            stage_a.to_json(), models=MODELS, registrations=REGISTRATIONS
        )
        self.assertEqual(restored.evidence_references, (reference,))


if __name__ == "__main__":
    unittest.main()
