import ast
import dataclasses
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain import identification_model as model_module
from domain.identification_model import (
    EFFECTIVE_FACE_SHEET_MODEL,
    EFFECTIVE_FACE_SHEET_V2_MODEL,
    IDENTIFICATION_MODEL_SCHEMA,
    STAGE_A_BENDING_MODEL,
    IdentificationModelDefinition,
    IdentificationParameterDefinition,
    ModelWorkflowStatus,
    effective_face_sheet_model,
    effective_face_sheet_v2_model,
    stage_a_bending_model,
)


def _synthetic_parameters():
    return [
        IdentificationParameterDefinition(
            parameter_id="k_axial",
            display_name="Axial spring",
            unit="N/m",
            meaning="Synthetic axial spring stiffness",
            default_bounds=(1.0, 10.0),
        ),
        IdentificationParameterDefinition(
            parameter_id="c_loss",
            display_name="Loss factor",
            unit="dimensionless",
            meaning="Synthetic loss factor",
        ),
    ]


def _synthetic(**changes):
    fields = dict(
        model_id="synthetic_spring",
        display_name="Synthetic spring model",
        parameter_definitions=_synthetic_parameters(),
        frozen_assumptions=["Mass fixed"],
        limitations=["Synthetic test model"],
        workflow_status="validation_only",
    )
    fields.update(changes)
    return IdentificationModelDefinition.create(**fields)


class ConcreteModelDefinitionTests(unittest.TestCase):
    # A
    def test_stage_a_bending_model(self):
        model = stage_a_bending_model()
        self.assertEqual(model.model_id, "stage_a_bending")
        self.assertEqual(model.parameter_ids, ("D11", "D12", "D66"))
        self.assertEqual(model.workflow_status, ModelWorkflowStatus.PRODUCTION)
        self.assertEqual({item.unit for item in model.parameter_definitions}, {"N·m"})
        self.assertTrue(all(item.default_bounds is None for item in model.parameter_definitions))
        self.assertEqual(model, STAGE_A_BENDING_MODEL)

    # B
    def test_effective_face_sheet_model(self):
        model = effective_face_sheet_model()
        self.assertEqual(model.model_id, "effective_face_sheet")
        self.assertEqual(model.parameter_ids, ("Ex", "Ey", "Gxy"))
        self.assertEqual(model.workflow_status, ModelWorkflowStatus.RESEARCH)
        self.assertEqual({item.unit for item in model.parameter_definitions}, {"MPa"})
        self.assertTrue(any("effective homogeneous" in item.lower() for item in model.limitations))
        self.assertEqual(model, EFFECTIVE_FACE_SHEET_MODEL)

    # C
    def test_definitions_carry_no_specimen_or_source_information(self):
        for model in (
            STAGE_A_BENDING_MODEL,
            EFFECTIVE_FACE_SHEET_MODEL,
            EFFECTIVE_FACE_SHEET_V2_MODEL,
        ):
            with self.subTest(model.model_id):
                text = json.dumps(model.to_dict()).lower()
                for forbidden in ("sp13", "specimen", "source", "registration", "sample"):
                    self.assertNotIn(forbidden, text)

    # D / E
    def test_no_field_binds_a_model_to_a_specimen_or_source(self):
        model_fields = {item.name for item in dataclasses.fields(IdentificationModelDefinition)}
        parameter_fields = {
            item.name for item in dataclasses.fields(IdentificationParameterDefinition)
        }
        for name in model_fields | parameter_fields:
            for forbidden in ("specimen", "source", "registration", "sample", "fitted", "value"):
                self.assertNotIn(forbidden, name)
        # Two specimen records may reference either model; the reference is
        # only (model_id, definition_hash), so both specimens see the same model.
        specimen_records = [
            {"specimen": name, "model": (model.model_id, model.definition_hash)}
            for name in ("specimen_a", "specimen_b")
            for model in (STAGE_A_BENDING_MODEL, EFFECTIVE_FACE_SHEET_MODEL)
        ]
        by_model = {}
        for record in specimen_records:
            by_model.setdefault(record["model"], set()).add(record["specimen"])
        self.assertEqual(len(by_model), 2)
        self.assertTrue(all(value == {"specimen_a", "specimen_b"} for value in by_model.values()))
        self.assertEqual(stage_a_bending_model().definition_hash, STAGE_A_BENDING_MODEL.definition_hash)


class EffectiveFaceSheetV2ModelTests(unittest.TestCase):
    """The versioned carbon face-sheet model; earlier definitions stay reproducible."""

    # Hashes of the definitions as committed before the v2 model was added.
    STAGE_A_BENDING_HASH = "e46578b6364f5d5d5c3030e356d96f55abbef7c67e22d861631dfb1b7b715ac0"
    EFFECTIVE_FACE_SHEET_HASH = "c00a1efbbd4b9f514c2e5254b7db8d1fb7e5648937de55522965b9c867de715c"

    def test_existing_models_are_unchanged(self):
        self.assertEqual(STAGE_A_BENDING_MODEL.definition_hash, self.STAGE_A_BENDING_HASH)
        self.assertEqual(stage_a_bending_model().definition_hash, self.STAGE_A_BENDING_HASH)
        self.assertEqual(STAGE_A_BENDING_MODEL.parameter_ids, ("D11", "D12", "D66"))
        self.assertEqual(
            EFFECTIVE_FACE_SHEET_MODEL.definition_hash, self.EFFECTIVE_FACE_SHEET_HASH
        )
        self.assertEqual(
            effective_face_sheet_model().definition_hash, self.EFFECTIVE_FACE_SHEET_HASH
        )
        self.assertEqual(EFFECTIVE_FACE_SHEET_MODEL.parameter_ids, ("Ex", "Ey", "Gxy"))
        self.assertNotEqual(
            EFFECTIVE_FACE_SHEET_V2_MODEL.definition_hash, self.EFFECTIVE_FACE_SHEET_HASH
        )

    def test_identity_parameters_units_and_status(self):
        model = effective_face_sheet_v2_model()
        self.assertEqual(model, EFFECTIVE_FACE_SHEET_V2_MODEL)
        self.assertEqual(model.model_id, "effective_face_sheet_v2")
        self.assertEqual(model.parameter_ids, ("E1", "E2", "G12", "nu12"))
        self.assertEqual(
            tuple(item.unit for item in model.parameter_definitions),
            ("MPa", "MPa", "MPa", "1"),
        )
        self.assertEqual(model.workflow_status, ModelWorkflowStatus.RESEARCH)
        self.assertTrue(all(item.default_bounds is None for item in model.parameter_definitions))

    def test_scientific_scope_is_declared_without_panel_values(self):
        model = EFFECTIVE_FACE_SHEET_V2_MODEL
        assumptions = " ".join(model.frozen_assumptions).lower()
        for statement in ("density", "thickness", "core geometry", "interface", "transverse"):
            self.assertIn(statement, assumptions)
        limitations = " ".join(model.limitations).lower()
        self.assertIn("effective face-sheet engineering constants", limitations)
        self.assertIn("not fibre properties", limitations)
        self.assertIn("nu12", limitations)
        # No panel-specific numbers (thickness, density, core modulus, adhesive mass).
        text = json.dumps(model.to_dict())
        for number in ("0.425", "1.429", "2580", "83.2", "52000"):
            self.assertNotIn(number, text)

    def test_round_trip_preserves_definition_and_hash(self):
        payload = json.loads(json.dumps(EFFECTIVE_FACE_SHEET_V2_MODEL.to_dict()))
        restored = IdentificationModelDefinition.from_dict(payload)
        self.assertEqual(restored, EFFECTIVE_FACE_SHEET_V2_MODEL)
        self.assertEqual(restored.definition_hash, EFFECTIVE_FACE_SHEET_V2_MODEL.definition_hash)
        self.assertEqual(restored.to_dict(), EFFECTIVE_FACE_SHEET_V2_MODEL.to_dict())

    def test_changing_scientific_content_changes_the_hash(self):
        base = EFFECTIVE_FACE_SHEET_V2_MODEL
        fields = {name: getattr(base, name) for name in base.FIELD_NAMES[:-2]}
        parameters = list(base.parameter_definitions)
        variants = {
            "nu12 unit": [*parameters[:3], dataclasses.replace(parameters[3], unit="dimensionless")],
            "parameter order": [parameters[1], parameters[0], *parameters[2:]],
            "without nu12": parameters[:3],
        }
        for name, changed in variants.items():
            with self.subTest(name):
                variant = IdentificationModelDefinition.create(
                    **dict(fields, parameter_definitions=changed)
                )
                self.assertNotEqual(variant.definition_hash, base.definition_hash)
        for name, change in (
            ("status", dict(workflow_status=ModelWorkflowStatus.PRODUCTION)),
            ("assumption", dict(frozen_assumptions=base.frozen_assumptions[:-1])),
            ("limitation", dict(limitations=base.limitations[:-1])),
        ):
            with self.subTest(name):
                variant = IdentificationModelDefinition.create(**dict(fields, **change))
                self.assertNotEqual(variant.definition_hash, base.definition_hash)
        tampered = base.to_dict()
        tampered["parameter_definitions"][3]["unit"] = "%"
        with self.assertRaisesRegex(ValueError, "definition_hash"):
            IdentificationModelDefinition.from_dict(tampered)


class ModelDefinitionContractTests(unittest.TestCase):
    # F
    def test_caller_mutation_cannot_change_definition(self):
        parameters = _synthetic_parameters()
        assumptions = ["Mass fixed"]
        model = _synthetic(parameter_definitions=parameters, frozen_assumptions=assumptions)
        before = (model.definition_hash, model.to_dict())
        parameters.append(parameters[0])
        assumptions[0] = "changed"
        self.assertEqual((model.definition_hash, model.to_dict()), before)
        self.assertIsInstance(model.parameter_definitions, tuple)
        self.assertIsInstance(model.frozen_assumptions, tuple)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            model.model_id = "other"
        with self.assertRaises(dataclasses.FrozenInstanceError):
            model.parameter_definitions[0].unit = "Pa"
        exported = model.to_dict()
        exported["parameter_definitions"][0]["unit"] = "Pa"
        self.assertEqual(model.to_dict(), before[1])

    # G
    def test_hash_is_independent_of_mapping_key_order(self):
        model = _synthetic()
        payload = model.to_dict()
        reordered = {key: payload[key] for key in reversed(list(payload))}
        reordered["parameter_definitions"] = [
            {key: item[key] for key in reversed(list(item))}
            for item in payload["parameter_definitions"]
        ]
        restored = IdentificationModelDefinition.from_dict(reordered)
        self.assertEqual(restored.definition_hash, model.definition_hash)
        self.assertEqual(_synthetic().definition_hash, model.definition_hash)
        self.assertRegex(model.definition_hash, r"^[0-9a-f]{64}$")

    # H
    def test_any_scientific_change_changes_the_hash(self):
        base = _synthetic()
        parameters = _synthetic_parameters()
        changed_unit = [dataclasses.replace(parameters[0], unit="kN/m"), parameters[1]]
        changed_bounds = [dataclasses.replace(parameters[0], default_bounds=(1.0, 20.0)), parameters[1]]
        variants = {
            "parameter id": _synthetic(
                parameter_definitions=[
                    dataclasses.replace(parameters[0], parameter_id="k_shear"),
                    parameters[1],
                ]
            ),
            "parameter order": _synthetic(parameter_definitions=parameters[::-1]),
            "unit": _synthetic(parameter_definitions=changed_unit),
            "bounds": _synthetic(parameter_definitions=changed_bounds),
            "limitation": _synthetic(limitations=["Other limitation"]),
            "assumption": _synthetic(frozen_assumptions=["Mass free"]),
            "status": _synthetic(workflow_status="research"),
            "model id": _synthetic(model_id="synthetic_spring_2"),
        }
        for name, variant in variants.items():
            with self.subTest(name):
                self.assertNotEqual(variant.definition_hash, base.definition_hash)
                self.assertNotEqual(variant, base)

    # I
    def test_round_trip_preserves_hash_and_content(self):
        for model in (STAGE_A_BENDING_MODEL, EFFECTIVE_FACE_SHEET_MODEL, _synthetic()):
            with self.subTest(model.model_id):
                payload = json.loads(json.dumps(model.to_dict()))
                restored = IdentificationModelDefinition.from_dict(payload)
                self.assertEqual(restored, model)
                self.assertEqual(restored.definition_hash, model.definition_hash)
                self.assertEqual(restored.to_dict(), model.to_dict())
                self.assertEqual(payload["schema_version"], IDENTIFICATION_MODEL_SCHEMA)

    # J
    def test_tampered_payload_is_refused(self):
        payload = STAGE_A_BENDING_MODEL.to_dict()
        tampered = json.loads(json.dumps(payload))
        tampered["parameter_definitions"][0]["unit"] = "N·mm"
        with self.assertRaisesRegex(ValueError, "definition_hash"):
            IdentificationModelDefinition.from_dict(tampered)
        status_changed = dict(payload, workflow_status="historical")
        with self.assertRaisesRegex(ValueError, "definition_hash"):
            IdentificationModelDefinition.from_dict(status_changed)
        for name, value in (("definition_hash", "not-a-hash"), ("schema_version", "identification-model/0")):
            with self.subTest(name), self.assertRaises(ValueError):
                IdentificationModelDefinition.from_dict(dict(payload, **{name: value}))
        with self.assertRaisesRegex(ValueError, "unknown"):
            IdentificationModelDefinition.from_dict(dict(payload, solver="scipy"))
        with self.assertRaises(ValueError):
            IdentificationModelDefinition(**{**{f.name: getattr(STAGE_A_BENDING_MODEL, f.name) for f in dataclasses.fields(IdentificationModelDefinition)}, "definition_hash": "0" * 64})

    # L
    def test_class_is_not_limited_to_the_two_concrete_parameterizations(self):
        model = _synthetic()
        self.assertEqual(model.parameter_ids, ("k_axial", "c_loss"))
        self.assertEqual(model.parameter("k_axial").default_bounds, (1.0, 10.0))
        self.assertEqual(model.workflow_status, ModelWorkflowStatus.VALIDATION_ONLY)

    def test_generic_validation(self):
        parameter = _synthetic_parameters()[0]
        invalid_parameters = {
            "empty id": dict(parameter_id=" "),
            "id with spaces": dict(parameter_id="k axial"),
            "empty unit": dict(unit=""),
            "empty meaning": dict(meaning=""),
            "reversed bounds": dict(default_bounds=(10.0, 1.0)),
            "non-finite bounds": dict(default_bounds=(1.0, float("inf"))),
            "bounds length": dict(default_bounds=(1.0,)),
            "boolean bound": dict(default_bounds=(True, 2.0)),
        }
        for name, change in invalid_parameters.items():
            with self.subTest(name), self.assertRaises((TypeError, ValueError)):
                dataclasses.replace(parameter, **change)
        invalid_models = {
            "no parameters": dict(parameter_definitions=[]),
            "duplicate ids": dict(parameter_definitions=[parameter, parameter]),
            "bad status": dict(workflow_status="experimental"),
            "bad model id": dict(model_id="Synthetic Spring"),
            "empty assumption": dict(frozen_assumptions=[""]),
            "non-definition parameter": dict(parameter_definitions=[{"parameter_id": "x"}]),
        }
        for name, change in invalid_models.items():
            with self.subTest(name), self.assertRaises((TypeError, ValueError)):
                _synthetic(**change)

    # K
    def test_module_is_data_only(self):
        tree = ast.parse(Path(model_module.__file__).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0] if node.level == 0 else "." + (node.module or ""))
        allowed = {"__future__", "dataclasses", "enum", "hashlib", "json", "math", "numbers", "re", "typing"}
        self.assertLessEqual(imported, allowed, imported - allowed)
        for cls in (IdentificationModelDefinition, IdentificationParameterDefinition):
            for item in dataclasses.fields(cls):
                self.assertNotIn("Callable", str(item.type))
        for model in (
            STAGE_A_BENDING_MODEL,
            EFFECTIVE_FACE_SHEET_MODEL,
            EFFECTIVE_FACE_SHEET_V2_MODEL,
        ):
            for item in dataclasses.fields(model):
                self.assertFalse(callable(getattr(model, item.name)))

    def test_domain_package_exports_model_definitions(self):
        import domain

        for name in (
            "IdentificationModelDefinition",
            "IdentificationParameterDefinition",
            "ModelWorkflowStatus",
            "STAGE_A_BENDING_MODEL",
            "EFFECTIVE_FACE_SHEET_MODEL",
            "EFFECTIVE_FACE_SHEET_V2_MODEL",
        ):
            self.assertIs(getattr(domain, name), getattr(model_module, name))
            self.assertIn(name, domain.__all__)


if __name__ == "__main__":
    unittest.main()
