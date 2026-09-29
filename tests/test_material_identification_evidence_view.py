from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.evidence import (
    EvidenceProvenance,
    EvidenceScientificBinding,
    EvidenceSourceIdentity,
    IdentificationEvidence,
    IdentifiabilityEvidence,
    SensitivityEvidence,
    ValidationEvidence,
    evidence_from_json,
)
from domain.identification_model import (
    EFFECTIVE_FACE_SHEET_MODEL,
    STAGE_A_BENDING_MODEL,
    IdentificationModelDefinition,
)
from material_identification_evidence_view import (
    EvidenceModelBindingError,
    InvalidEvidenceError,
    MaterialIdentificationEvidenceViewModel,
)
from sp13_evidence_adapter import HISTORICAL_STATUS, SP13EvidenceBundle


TIMESTAMP = datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc)
SOURCE = EvidenceSourceIdentity(
    source_id="synthetic-output",
    source_type="service-output",
    uri="project://synthetic/output",
    content_hash="4" * 64,
)
PROVENANCE = EvidenceProvenance(producer="evidence view contract test")


def _binding(model: IdentificationModelDefinition, **overrides) -> EvidenceScientificBinding:
    fields = {
        "identification_model_id": model.model_id,
        "identification_model_hash": model.definition_hash,
        "registration_hash": "a" * 64,
        "experimental_content_sha256": "b" * 64,
    }
    fields.update(overrides)
    return EvidenceScientificBinding.create(**fields)


def _sensitivity(binding, parameter_ids, rows) -> SensitivityEvidence:
    # The shape the production runner stores: the parameter matrix lives in
    # parameter_ids / observation_ids / scaled_sensitivity.
    return SensitivityEvidence.create(
        evidence_id="bound-sensitivity",
        timestamp=TIMESTAMP,
        source_identity=SOURCE,
        provenance=PROVENANCE,
        status="COMPLETED",
        content={
            "raw_sensitivity_matrix": tuple(
                {"observable": observation_id, "baseline_frequency_hz": 30.0}
                for observation_id, _values in rows
            ),
            "observation_ids": tuple(observation_id for observation_id, _values in rows),
            "parameter_ids": tuple(parameter_ids),
            "scaled_sensitivity": tuple(tuple(values) for _id, values in rows),
        },
        scientific_binding=binding,
    )


def _identifiability(binding, parameter_ids, observability) -> IdentifiabilityEvidence:
    return IdentifiabilityEvidence.create(
        evidence_id="bound-identifiability",
        timestamp=TIMESTAMP,
        source_identity=SOURCE,
        provenance=PROVENANCE,
        status="NOT_ASSESSED",
        content={
            "models": {
                "U": {
                    "parameter_order": tuple(parameter_ids),
                    "singular_values": (3.0, 2.0, 1.0),
                    "numerical_rank": 3,
                    "condition_number": 3.0,
                    "deficient_directions": (),
                    "parameter_observability": dict(observability),
                }
            }
        },
        scientific_binding=binding,
    )


def _identification(binding, properties, unit) -> IdentificationEvidence:
    # The committed adapter stores values under "properties_MPa" for every model.
    return IdentificationEvidence.create(
        evidence_id="bound-identification",
        timestamp=TIMESTAMP,
        source_identity=SOURCE,
        provenance=PROVENANCE,
        status="COMPLETED",
        content={
            "identified_properties": {
                "models": {
                    "U": {
                        "properties_MPa": dict(properties),
                        "parameter_unit": unit,
                        "uncertainty": {},
                    }
                }
            }
        },
        scientific_binding=binding,
    )


STAGE_A_VALUES = {"D11": 12.0, "D12": 2.4, "D66": 5.0}
FACE_VALUES = {"Ex": 45000.0, "Ey": 60000.0, "Gxy": 8000.0}


class ModelDrivenEvidenceViewContractTests(unittest.TestCase):
    """BOUND evidence is presented only against its own model definition."""

    def stage_a_records(self, binding=None):
        binding = binding or _binding(STAGE_A_BENDING_MODEL)
        return {
            "sensitivity": _sensitivity(
                binding, ("D11", "D12", "D66"), (("EXP1_A7", (0.1, 0.2, 0.3)),)
            ),
            "identifiability": _identifiability(
                binding, ("D11", "D12", "D66"), {"D11": "OBSERVABLE"}
            ),
            "identification": _identification(binding, STAGE_A_VALUES, "N·m"),
        }

    def assert_refused(self, reason, **fields):
        with self.assertRaises(EvidenceModelBindingError) as context:
            MaterialIdentificationEvidenceViewModel(**fields)
        self.assertEqual(context.exception.reason, reason)
        return context.exception

    # D
    def test_bound_evidence_without_model_is_refused(self):
        for name, record in self.stage_a_records().items():
            with self.subTest(name):
                self.assert_refused("model_required", **{name: record})

    # E
    def test_bound_evidence_with_wrong_model_id_is_refused(self):
        for name, record in self.stage_a_records().items():
            with self.subTest(name):
                self.assert_refused(
                    "model_id", **{name: record, "model": EFFECTIVE_FACE_SHEET_MODEL}
                )

    # F
    def test_bound_evidence_with_wrong_model_hash_is_refused(self):
        altered = IdentificationModelDefinition.create(
            model_id=STAGE_A_BENDING_MODEL.model_id,
            display_name="Stage A plate bending stiffness (altered)",
            parameter_definitions=STAGE_A_BENDING_MODEL.parameter_definitions,
            frozen_assumptions=STAGE_A_BENDING_MODEL.frozen_assumptions,
            limitations=STAGE_A_BENDING_MODEL.limitations,
            workflow_status=STAGE_A_BENDING_MODEL.workflow_status,
        )
        self.assertEqual(altered.model_id, STAGE_A_BENDING_MODEL.model_id)
        self.assertNotEqual(altered.definition_hash, STAGE_A_BENDING_MODEL.definition_hash)
        for name, record in self.stage_a_records().items():
            with self.subTest(name):
                self.assert_refused("model_hash", **{name: record, "model": altered})

    # G
    def test_stored_parameter_unit_inconsistent_with_model_is_refused(self):
        cases = (
            (STAGE_A_BENDING_MODEL, STAGE_A_VALUES, "MPa"),
            (EFFECTIVE_FACE_SHEET_MODEL, FACE_VALUES, "N·m"),
        )
        for model, values, wrong_unit in cases:
            with self.subTest(model.model_id):
                view = MaterialIdentificationEvidenceViewModel(
                    identification=_identification(_binding(model), values, wrong_unit),
                    model=model,
                )
                with self.assertRaises(EvidenceModelBindingError) as context:
                    view.identification_view()
                self.assertEqual(context.exception.reason, "parameter_unit")

    # H
    def test_effective_face_production_evidence_renders_from_its_model(self):
        binding = _binding(EFFECTIVE_FACE_SHEET_MODEL)
        # Stored column order differs from the model order; the view follows the model.
        sensitivity = _sensitivity(
            binding, ("Gxy", "Ex", "Ey"), (("EXP1_A7", (0.3, 0.1, 0.2)),)
        )
        identification = _identification(binding, FACE_VALUES, "MPa")
        view = MaterialIdentificationEvidenceViewModel(
            sensitivity=sensitivity,
            identification=identification,
            model=EFFECTIVE_FACE_SHEET_MODEL,
        )

        self.assertEqual(
            view.sensitivity_view()["matrix"], (("EXP1_A7", "Scalar mode", 0.1, 0.2, 0.3),)
        )
        self.assertEqual(
            view.identification_view()["model_u"],
            (("Ex", 45000.0, "MPa"), ("Ey", 60000.0, "MPa"), ("Gxy", 8000.0, "MPa")),
        )
        self.assertEqual(
            view.identification_view()["model_p"],
            (("Ex", None, "MPa"), ("Ey", None, "MPa"), ("Gxy", None, "MPa")),
        )

    def test_stage_a_sensitivity_subset_is_not_padded_with_invented_columns(self):
        binding = _binding(STAGE_A_BENDING_MODEL)
        sensitivity = _sensitivity(binding, ("D66", "D11"), (("EXP1_A7", (0.6, 0.1)),))
        view = MaterialIdentificationEvidenceViewModel(
            sensitivity=sensitivity, model=STAGE_A_BENDING_MODEL
        )
        self.assertEqual(
            view.sensitivity_view()["matrix"], (("EXP1_A7", "Scalar mode", 0.1, 0.6),)
        )

    def test_bound_content_naming_parameters_outside_the_model_is_refused(self):
        binding = _binding(STAGE_A_BENDING_MODEL)
        views = {
            "sensitivity": lambda: MaterialIdentificationEvidenceViewModel(
                sensitivity=_sensitivity(
                    binding, ("Ex", "Ey", "Gxy"), (("EXP1_A7", (0.1, 0.2, 0.3)),)
                ),
                model=STAGE_A_BENDING_MODEL,
            ).sensitivity_view(),
            "identifiability": lambda: MaterialIdentificationEvidenceViewModel(
                identifiability=_identifiability(
                    binding, ("Ex", "Ey", "Gxy"), {"Ex": "OBSERVABLE"}
                ),
                model=STAGE_A_BENDING_MODEL,
            ).sensitivity_view(),
            "identification": lambda: MaterialIdentificationEvidenceViewModel(
                identification=_identification(binding, FACE_VALUES, "N·m"),
                model=STAGE_A_BENDING_MODEL,
            ).identification_view(),
        }
        for name, render in views.items():
            with self.subTest(name):
                with self.assertRaises(EvidenceModelBindingError) as context:
                    render()
                self.assertEqual(context.exception.reason, "parameter_ids")

    # J
    def test_mixed_bound_and_unbound_presentation_is_refused(self):
        bound = self.stage_a_records()
        unbound = _identification(None, STAGE_A_VALUES, "N·m")
        self.assertEqual(unbound.binding_status, "UNBOUND")
        for model in (None, STAGE_A_BENDING_MODEL):
            with self.subTest(model=getattr(model, "model_id", None)):
                self.assert_refused(
                    "mixed_binding",
                    sensitivity=bound["sensitivity"],
                    identification=unbound,
                    model=model,
                )

    def test_unbound_evidence_cannot_be_presented_against_a_model(self):
        unbound = _identification(None, STAGE_A_VALUES, "N·m")
        self.assert_refused(
            "unbound_with_model", identification=unbound, model=STAGE_A_BENDING_MODEL
        )

    def test_empty_model_view_uses_the_model_parameters(self):
        view = MaterialIdentificationEvidenceViewModel(model=STAGE_A_BENDING_MODEL)
        self.assertEqual(
            view.identification_view()["model_u"],
            (("D11", None, "N·m"), ("D12", None, "N·m"), ("D66", None, "N·m")),
        )
        self.assertEqual(
            view.sensitivity_view()["observability"],
            (("D11", "unavailable"), ("D12", "unavailable"), ("D66", "unavailable")),
        )


def _synthetic_historical_bundle() -> SP13EvidenceBundle:
    """Small synthetic UNBOUND bundle in the legacy historical SP13 layout.

    Presentation fixture only: the frozen-artifact loader has its own tests
    (test_sp13_evidence_adapter).  Values are synthetic, not REAL-4 results.
    """

    source = EvidenceSourceIdentity(
        source_id="synthetic/sp13_historical",
        source_type="frozen-sp13-artifact",
        uri="synthetic://sp13/historical",
        content_hash="5" * 64,
    )
    provenance = EvidenceProvenance(
        producer="synthetic historical SP13 view fixture",
        method="synthetic stand-in for read-only serialization of frozen artifacts",
        details={"specimen": "SP13", "historical_status": HISTORICAL_STATUS},
    )

    def record(record_type, name, status, content):
        return record_type.create(
            evidence_id=f"sp13-{name}-synthetic",
            timestamp=TIMESTAMP,
            source_identity=source,
            provenance=provenance,
            status=status,
            content=content,
            scientific_binding=None,
        )

    svd = {
        "parameter_order": ("face_Ex", "face_Ey", "face_Gxy", "core_scale"),
        "singular_values": (4.0, 3.0, 2.0, 1.0),
        "numerical_rank": 4,
        "condition_number": 4.0,
        "weakest_right_singular_vector": (0.1, 0.2, 0.3, -0.9),
    }
    return SP13EvidenceBundle(
        sensitivity=record(
            SensitivityEvidence,
            "sensitivity",
            "SYNTHETIC_FROZEN",
            {
                # CSV cells are stored as text in the historical layout.
                "raw_sensitivity_matrix": (
                    {"observable": "SYN_A1", "baseline_frequency_hz": "10.0",
                     "face_Ex": "0.125", "face_Ey": "0.25", "face_Gxy": "0.5",
                     "core_scale": "0.0625"},
                    {"observable": "SYN_A2", "baseline_frequency_hz": "20.0",
                     "face_Ex": "0.75", "face_Ey": "0.375", "face_Gxy": "0.125",
                     "core_scale": "0.25"},
                ),
            },
        ),
        identifiability=record(
            IdentifiabilityEvidence,
            "identifiability",
            "SYNTHETIC_FROZEN",
            {"models": {"U": dict(svd), "P": dict(svd)}},
        ),
        identification=record(
            IdentificationEvidence,
            "identification",
            "SYNTHETIC_HISTORICAL_RECOMMENDATION",
            {
                "identified_properties": {
                    "models": {
                        "U": {"properties_MPa": {"Ex": 41000.0, "Ey": 52000.0, "Gxy": 6100.0}},
                        "P": {"properties_MPa": {"Ex": 43000.0, "Ey": 51000.0, "Gxy": 7300.0}},
                    },
                    "stability": {
                        "Ex": "RELATIVELY_STABLE",
                        "Ey": "RELATIVELY_STABLE",
                        "Gxy": "WEIGHTING_SENSITIVE",
                        "U_P_symmetric_difference_percent": {"Ex": 5.0, "Ey": 2.0, "Gxy": 18.0},
                    },
                }
            },
        ),
        validation=record(
            ValidationEvidence,
            "validation",
            "SYNTHETIC_HISTORICAL_RECOMMENDATION",
            {
                "validation_rows": (
                    {"model": "BASELINE", "observable": "SYN_A1", "category": "PRIMARY",
                     "experimental_value": "10.0", "FE_value": "11.0",
                     "equivalent_error_percent": "10.0", "identity_status": "PASS"},
                    {"model": "U", "observable": "SYN_A1", "category": "PRIMARY",
                     "experimental_value": "10.0", "FE_value": "10.5",
                     "equivalent_error_percent": "5.0", "identity_status": "PASS"},
                    {"model": "U", "observable": "SYN_A3", "category": "HOLDOUT",
                     "experimental_value": "30.0", "FE_value": "33.0",
                     "equivalent_error_percent": "10.0", "identity_status": "",
                     "comparison_to_baseline": "WORSE"},
                ),
            },
        ),
    )


class MaterialIdentificationEvidenceViewModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = _synthetic_historical_bundle()

    def test_missing_evidence_produces_explicit_empty_views(self):
        view_model = MaterialIdentificationEvidenceViewModel.from_bundle(
            SP13EvidenceBundle(None, None, None, None)
        )

        self.assertFalse(view_model.sensitivity_view()["available"])
        self.assertEqual(
            view_model.identification_view()["status"],
            "NO_IDENTIFICATION_RESULT",
        )
        self.assertEqual(
            view_model.validation_view()["status"],
            "NO_VALIDATION_EVIDENCE",
        )

    def test_invalid_evidence_type_is_rejected_without_field_guessing(self):
        invalid_bundle = SP13EvidenceBundle(
            sensitivity=self.bundle.identification,
            identifiability=None,
            identification=None,
            validation=None,
        )
        with self.assertRaisesRegex(TypeError, "SensitivityEvidence"):
            MaterialIdentificationEvidenceViewModel.from_bundle(invalid_bundle)

    def test_invalid_typed_payload_is_reported(self):
        original = self.bundle.sensitivity
        malformed = SensitivityEvidence.create(
            evidence_id="malformed-sensitivity",
            timestamp=original.timestamp,
            source_identity=original.source_identity,
            provenance=original.provenance,
            status=original.status,
            content={"unexpected": "shape"},
        )
        view_model = MaterialIdentificationEvidenceViewModel(
            sensitivity=malformed
        )

        with self.assertRaisesRegex(
            InvalidEvidenceError, "raw_sensitivity_matrix"
        ):
            view_model.sensitivity_view()

    def test_serialized_contracts_follow_the_same_typed_rendering_path(self):
        restored = SP13EvidenceBundle(
            sensitivity=evidence_from_json(self.bundle.sensitivity.to_json()),
            identifiability=evidence_from_json(self.bundle.identifiability.to_json()),
            identification=evidence_from_json(self.bundle.identification.to_json()),
            validation=evidence_from_json(self.bundle.validation.to_json()),
        )
        original_view = MaterialIdentificationEvidenceViewModel.from_bundle(
            self.bundle
        )
        restored_view = MaterialIdentificationEvidenceViewModel.from_bundle(
            restored
        )
        # The comparison is only meaningful for populated views.
        self.assertTrue(original_view.sensitivity_view()["available"])
        self.assertTrue(original_view.identification_view()["available"])
        self.assertTrue(original_view.validation_view()["available"])

        self.assertEqual(restored_view.sensitivity_view(), original_view.sensitivity_view())
        self.assertEqual(restored_view.identification_view(), original_view.identification_view())
        self.assertEqual(restored_view.validation_view(), original_view.validation_view())


if __name__ == "__main__":
    unittest.main()
