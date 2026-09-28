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
from domain.evidence import (
    EvidenceProvenance,
    EvidenceSourceIdentity,
    SensitivityEvidence,
)
from domain.identification_model import (
    EFFECTIVE_FACE_SHEET_MODEL,
    STAGE_A_BENDING_MODEL,
    IdentificationModelDefinition,
    IdentificationParameterDefinition,
)
from domain.material_identification_session import (
    MaterialIdentificationEvidenceReference,
    MaterialIdentificationSession,
    MaterialIdentificationSourceIdentities,
    MaterialIdentificationTaskDefinition,
    ParameterBounds,
)


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


class MaterialIdentificationSessionTests(unittest.TestCase):
    def setUp(self):
        self.sources = self.source_set("specimen-a")
        self.provenance = EvidenceProvenance(
            producer="material-identification-session test",
            method="user-authored task definition",
            artifacts=(self.sources.experimental, self.sources.fe_model, self.sources.calibration),
            details={"scientific_execution": False},
        )

    @staticmethod
    def source(source_id: str, source_type: str, digit: str):
        return EvidenceSourceIdentity(
            source_id=source_id,
            source_type=source_type,
            uri=f"project://{source_id}",
            content_hash=digit * 64,
        )

    def source_set(self, prefix: str, digits="123"):
        return MaterialIdentificationSourceIdentities(
            experimental=self.source(f"{prefix}-experimental", "experimental-modal-data", digits[0]),
            fe_model=self.source(f"{prefix}-fe-model", "abaqus-fe-model", digits[1]),
            calibration=self.source(f"{prefix}-calibration", "coordinate-calibration", digits[2]),
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

    def session(self, task, sources=None, **changes):
        values = dict(
            session_id="session-1",
            created_at=datetime(2026, 9, 29, 8, 0, tzinfo=timezone.utc),
            task_definition=task,
            source_identities=self.sources if sources is None else sources,
        )
        values.update(changes)
        return MaterialIdentificationSession.create(**values)

    # A
    def test_effective_face_sheet_session(self):
        session = self.session(self.task(EFFECTIVE_FACE_SHEET_MODEL))
        task = session.task_definition
        self.assertEqual(task.selected_parameter_ids, ("Ex", "Ey", "Gxy"))
        self.assertEqual(task.identification_model_id, "effective_face_sheet")
        self.assertEqual(task.identification_model_hash, EFFECTIVE_FACE_SHEET_MODEL.definition_hash)
        self.assertEqual(session.readiness().reasons, ())
        self.assertTrue(session.readiness().ready)

    # B
    def test_stage_a_session(self):
        session = self.session(self.task(STAGE_A_BENDING_MODEL))
        task = session.task_definition
        self.assertEqual(task.selected_parameter_ids, ("D11", "D12", "D66"))
        self.assertEqual(task.identification_model_id, "stage_a_bending")
        self.assertEqual(task.identification_model_hash, STAGE_A_BENDING_MODEL.definition_hash)
        self.assertTrue(session.readiness().ready)

    # C
    def test_same_sources_can_use_either_model(self):
        sessions = [self.session(self.task(model)) for model in MODELS]
        self.assertEqual(sessions[0].source_identities, sessions[1].source_identities)
        self.assertNotEqual(
            sessions[0].task_definition.identification_model_hash,
            sessions[1].task_definition.identification_model_hash,
        )
        self.assertTrue(all(item.readiness().ready for item in sessions))

    # D
    def test_same_model_can_serve_different_sources(self):
        task = self.task(STAGE_A_BENDING_MODEL)
        first = self.session(task, self.source_set("specimen-a"))
        second = self.session(task, self.source_set("specimen-b", "456"))
        self.assertNotEqual(first.source_identities, second.source_identities)
        self.assertEqual(first.task_definition, second.task_definition)

    # E / F / G
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

    # H
    def test_synthetic_model_parameters_are_accepted(self):
        model = _synthetic_model()
        task = self.task(
            model,
            bounds={"k_axial": ParameterBounds(1.0, 10.0, "N/m"), "c_loss": ParameterBounds(0.0, 0.1, "dimensionless")},
        )
        session = self.session(task)
        self.assertEqual(task.selected_parameter_ids, ("k_axial", "c_loss"))
        self.assertTrue(session.readiness().ready)
        with self.assertRaises(ValueError):
            self.task(model, selected=("Ex",), bounds={})

    # I / J
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
            MaterialIdentificationSession.from_json(payload, models=(altered, EFFECTIVE_FACE_SHEET_MODEL))
        with self.assertRaisesRegex(ValueError, "Unknown identification model 'stage_a_bending'"):
            MaterialIdentificationSession.from_json(payload, models=EFFECTIVE_FACE_SHEET_MODEL)
        # The right definition among several candidates with the same id is chosen.
        restored = MaterialIdentificationSession.from_json(payload, models=(altered, STAGE_A_BENDING_MODEL))
        self.assertIs(restored.task_definition.model, STAGE_A_BENDING_MODEL)
        tampered = json.loads(payload)
        tampered["task_definition"]["identification_model_hash"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "definition hash mismatch"):
            MaterialIdentificationSession.from_dict(tampered, models=MODELS)

    # K
    def test_campaign_bounds_belong_to_model_parameters_and_units(self):
        self.assertEqual(
            self.task(STAGE_A_BENDING_MODEL).bounds_for("D11"), STAGE_A_BOUNDS["D11"]
        )
        self.assertEqual(
            self.task(EFFECTIVE_FACE_SHEET_MODEL).bounds_for("Gxy"), FACE_BOUNDS["Gxy"]
        )
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
        self.assertEqual(STAGE_A_BENDING_MODEL.definition_hash, before)

    def test_readiness_requires_bounds_for_selected_parameters(self):
        session = self.session(self.task(STAGE_A_BENDING_MODEL, bounds={"D11": STAGE_A_BOUNDS["D11"]}))
        readiness = session.readiness()
        self.assertFalse(readiness.ready)
        self.assertEqual(
            readiness.reasons,
            ("Selected parameter 'D12' has no bounds.", "Selected parameter 'D66' has no bounds."),
        )

    def test_readiness_detects_an_altered_in_memory_model(self):
        model = _synthetic_model()
        task = self.task(model, bounds={"k_axial": ParameterBounds(1.0, 10.0, "N/m"), "c_loss": ParameterBounds(0.0, 0.1, "dimensionless")})
        session = self.session(task)
        object.__setattr__(model, "limitations", ("silently changed",))
        readiness = session.readiness()
        self.assertFalse(readiness.ready)
        self.assertTrue(any("synthetic_spring" in item for item in readiness.reasons))

    # L / M
    def test_frozen_assumptions_come_from_the_model(self):
        face = self.task(EFFECTIVE_FACE_SHEET_MODEL)
        self.assertEqual(face.frozen_assumptions, EFFECTIVE_FACE_SHEET_MODEL.frozen_assumptions)
        self.assertIn("Core representation is frozen.", face.frozen_assumptions)
        self.assertEqual(face.to_dict()["frozen_assumptions"], list(face.frozen_assumptions))
        stage_a = self.task(STAGE_A_BENDING_MODEL)
        text = json.dumps(stage_a.to_dict()).lower()
        for word in ("core", "density", "adhesive"):
            self.assertNotIn(word, text)
        self.assertEqual(stage_a.frozen_assumptions, STAGE_A_BENDING_MODEL.frozen_assumptions)
        payload = self.session(face).to_dict()
        payload["task_definition"]["frozen_assumptions"] = ["Core representation is frozen."]
        with self.assertRaisesRegex(ValueError, "frozen assumptions differ"):
            MaterialIdentificationSession.from_dict(payload, models=MODELS)

    # N
    def test_round_trip_preserves_model_reference_and_order(self):
        for model, selected in ((STAGE_A_BENDING_MODEL, ("D66", "D11")), (EFFECTIVE_FACE_SHEET_MODEL, ("Gxy", "Ex"))):
            with self.subTest(model.model_id):
                session = self.session(self.task(model, selected=selected))
                text = session.to_json()
                payload = json.loads(text)
                self.assertEqual(payload["schema_version"], "material-identification-session/2.0")
                task_payload = payload["task_definition"]
                self.assertEqual(task_payload["identification_model_id"], model.model_id)
                self.assertEqual(task_payload["identification_model_hash"], model.definition_hash)
                self.assertEqual(task_payload["selected_parameter_ids"], list(selected))
                self.assertEqual(
                    [item["parameter_id"] for item in task_payload["parameter_bounds"]],
                    list(model.parameter_ids),
                )
                self.assertNotIn("parameter_definitions", task_payload)
                restored = MaterialIdentificationSession.from_json(text, models=MODELS)
                self.assertEqual(restored, session)
                self.assertEqual(restored.to_json(), text)

    def test_old_schema_is_rejected_explicitly(self):
        payload = self.session(self.task(EFFECTIVE_FACE_SHEET_MODEL)).to_dict()
        payload["schema_version"] = "material-identification-session/1.0"
        with self.assertRaisesRegex(ValueError, "schema 1.0 hard-coded the Ex/Ey/Gxy"):
            MaterialIdentificationSession.from_dict(payload, models=MODELS)
        with self.assertRaisesRegex(ValueError, "schema 1.0"):
            dataclasses.replace(
                self.session(self.task(EFFECTIVE_FACE_SHEET_MODEL)),
                schema_version="material-identification-session/1.0",
            )

    # O
    def test_caller_mutation_cannot_alter_the_session(self):
        bounds = dict(STAGE_A_BOUNDS)
        selected = ["D11", "D66"]
        task = self.task(STAGE_A_BENDING_MODEL, selected=selected, bounds=bounds)
        session = self.session(task)
        before = session.to_json()
        bounds["D11"] = ParameterBounds(0.1, 0.2, "N·m")
        bounds["Ex"] = ParameterBounds(1.0, 2.0, "MPa")
        selected.append("D12")
        self.assertEqual(session.to_json(), before)
        self.assertIsInstance(task.parameter_bounds, tuple)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            task.selected_parameter_ids = ("D12",)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            task.model.parameter_definitions[0].unit = "MPa"

    # P
    def test_validation_never_depends_on_specimen_names(self):
        task = self.task(EFFECTIVE_FACE_SHEET_MODEL)
        tasks = [
            self.session(task, self.source_set(prefix)).task_definition.to_dict()
            for prefix in ("SP13", "SP14", "specimen-x")
        ]
        self.assertTrue(all(item == tasks[0] for item in tasks))
        module_text = Path(session_module.__file__).read_text(encoding="utf-8").lower()
        self.assertNotIn("sp13", module_text)
        for name in ("UNKNOWN_PARAMETER_IDS", "FROZEN_PARAMETER_IDS", "SUPPORTED_PARAMETER_IDS",
                     "MaterialParameterDefinition", "standard_material_parameter_definitions"):
            self.assertFalse(hasattr(session_module, name), name)

    # Q
    def test_evidence_from_different_sources_is_rejected(self):
        evidence = SensitivityEvidence.create(
            evidence_id="sensitivity-1",
            timestamp=datetime(2026, 9, 29, 8, 30, tzinfo=timezone.utc),
            source_identity=self.sources.experimental,
            provenance=self.provenance,
            status="READY",
            content={"stored": True},
        )
        reference = MaterialIdentificationEvidenceReference.from_evidence(
            evidence, self.source_set("specimen-b", "456")
        )
        with self.assertRaisesRegex(ValueError, "source mismatch"):
            self.session(self.task(STAGE_A_BENDING_MODEL), evidence_references=(reference,))

    def test_serialization_round_trip_with_evidence_is_deterministic(self):
        evidence = SensitivityEvidence.create(
            evidence_id="sensitivity-1",
            timestamp=datetime(2026, 9, 29, 8, 30, tzinfo=timezone.utc),
            source_identity=self.sources.experimental,
            provenance=self.provenance,
            status="READY",
            content={"stored": True},
        )
        session = self.session(
            self.task(STAGE_A_BENDING_MODEL),
            evidence_references=(
                MaterialIdentificationEvidenceReference.from_evidence(evidence, self.sources),
            ),
        )
        restored = MaterialIdentificationSession.from_json(session.to_json(), models=MODELS)
        self.assertEqual(restored, session)
        self.assertEqual(restored.to_json(), session.to_json())
        self.assertEqual(restored.evidence_references[0].evidence_id, "sensitivity-1")


if __name__ == "__main__":
    unittest.main()
