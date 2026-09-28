from __future__ import annotations

from datetime import datetime, timezone
import json
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
    evidence_content_hash,
    evidence_from_dict,
    evidence_from_json,
    evidence_record_hash,
)


RECORD_TYPES = (
    SensitivityEvidence,
    IdentifiabilityEvidence,
    IdentificationEvidence,
    ValidationEvidence,
)
BINDING_FIELDS = dict(
    identification_model_id="stage_a_bending",
    identification_model_hash="a" * 64,
    registration_hash="b" * 64,
    experimental_content_sha256="c" * 64,
)


class EvidenceContractTests(unittest.TestCase):
    def setUp(self):
        self.source = EvidenceSourceIdentity(
            source_id="SP13/modal-inputs",
            source_type="modal-dataset-and-fe-model",
            uri="project://SP13/evidence",
            content_hash="1" * 64,
        )
        self.provenance = EvidenceProvenance(
            producer="abaqus-modal-comparator",
            producer_version="1",
            commit="97b5c1f",
            method="stored scientific result adapter",
            artifacts=(self.source,),
            details={"calculation_performed_by_contract": False},
        )
        self.timestamp = datetime(2026, 9, 27, 12, 30, tzinfo=timezone.utc)

    def create(self, record_type, content=None):
        return record_type.create(
            evidence_id=f"{record_type.RECORD_TYPE}-001",
            timestamp=self.timestamp,
            source_identity=self.source,
            parent_ids=("project-evidence-001",),
            provenance=self.provenance,
            status="READY",
            content=content or {"available": True},
        )

    def test_each_evidence_type_serializes_with_explicit_schema_and_identity(self):
        for record_type in (
            SensitivityEvidence,
            IdentifiabilityEvidence,
            IdentificationEvidence,
            ValidationEvidence,
        ):
            with self.subTest(record_type=record_type.__name__):
                record = self.create(record_type)
                payload = record.to_dict()
                self.assertEqual(payload["record_type"], record_type.RECORD_TYPE)
                self.assertEqual(payload["schema_version"], record_type.SCHEMA_VERSION)
                self.assertEqual(payload["evidence_id"], record.evidence_id)
                self.assertEqual(payload["timestamp"], "2026-09-27T12:30:00Z")
                self.assertEqual(payload["source_identity"], self.source.to_dict())
                self.assertEqual(payload["parent_ids"], ["project-evidence-001"])
                self.assertEqual(
                    payload["content_hash"], evidence_content_hash(record.content)
                )
                self.assertEqual(payload["provenance"], self.provenance.to_dict())
                self.assertEqual(payload["status"], "READY")

    def test_round_trip_preserves_concrete_type_and_nested_content(self):
        records = (
            self.create(
                SensitivityEvidence,
                {"parameter_ids": ["Ex", "Ey", "Gxy"], "matrix": [[1.0, 0.2]]},
            ),
            self.create(
                IdentifiabilityEvidence,
                {"rank": 3, "singular_values": [5.0, 2.0, 0.5]},
            ),
            self.create(
                IdentificationEvidence,
                {"models": {"U": {"Ex": 1.0}, "P": {"Ex": 1.1}}},
            ),
            self.create(
                ValidationEvidence,
                {"primary": [{"observation_id": "A7", "status": "PASS"}]},
            ),
        )
        for record in records:
            with self.subTest(record_type=type(record).__name__):
                restored = evidence_from_json(record.to_json())
                self.assertEqual(restored, record)
                self.assertIs(type(restored), type(record))
                self.assertEqual(evidence_from_dict(record.to_dict()), record)

    def test_json_is_deterministic_and_contains_no_nonstandard_numbers(self):
        first = self.create(
            SensitivityEvidence,
            {"z": [3, 2, 1], "a": {"finite": 1.25}},
        )
        second = self.create(
            SensitivityEvidence,
            {"a": {"finite": 1.25}, "z": [3, 2, 1]},
        )
        self.assertEqual(first.content_hash, second.content_hash)
        self.assertEqual(json.loads(first.to_json()), first.to_dict())

    def test_rejects_wrong_schema_type_and_tampered_content(self):
        record = self.create(SensitivityEvidence)
        wrong_schema = record.to_dict()
        wrong_schema["schema_version"] = "sensitivity-evidence/9.0"
        with self.assertRaisesRegex(ValueError, "requires schema_version"):
            SensitivityEvidence.from_dict(wrong_schema)

        wrong_type = record.to_dict()
        wrong_type["record_type"] = "validation"
        with self.assertRaisesRegex(ValueError, "Expected record_type"):
            SensitivityEvidence.from_dict(wrong_type)

        tampered = record.to_dict()
        tampered["content"] = {"available": False}
        with self.assertRaisesRegex(ValueError, "content_hash does not match"):
            SensitivityEvidence.from_dict(tampered)

    def test_rejects_invalid_common_field_types(self):
        with self.assertRaisesRegex(ValueError, "timestamp must include a timezone"):
            SensitivityEvidence.create(
                evidence_id="sensitivity-naive",
                timestamp=datetime(2026, 9, 27, 12, 30),
                source_identity=self.source,
                provenance=self.provenance,
                status="READY",
                content={"available": True},
            )
        with self.assertRaisesRegex(TypeError, "source_identity"):
            SensitivityEvidence.create(
                source_identity={"source_id": "not-typed"},
                provenance=self.provenance,
                status="READY",
                content={"available": True},
            )
        with self.assertRaisesRegex(ValueError, "status must be an uppercase identifier"):
            SensitivityEvidence.create(
                source_identity=self.source,
                provenance=self.provenance,
                status="not ready",
                content={"available": True},
            )

    def test_rejects_non_json_and_non_finite_content(self):
        with self.assertRaisesRegex(TypeError, "unsupported value type"):
            self.create(SensitivityEvidence, {"invalid": object()})
        with self.assertRaisesRegex(ValueError, "non-finite"):
            self.create(IdentifiabilityEvidence, {"condition_number": float("inf")})

    def test_rejects_invalid_parent_and_source_hashes(self):
        with self.assertRaisesRegex(ValueError, "own parent"):
            SensitivityEvidence.create(
                evidence_id="same-id",
                source_identity=self.source,
                parent_ids=("same-id",),
                provenance=self.provenance,
                status="READY",
                content={"available": True},
            )
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            EvidenceSourceIdentity(
                source_id="source",
                source_type="dataset",
                content_hash="not-a-hash",
            )

    def test_unknown_record_type_is_not_guessed(self):
        payload = self.create(ValidationEvidence).to_dict()
        payload["record_type"] = "some-future-evidence"
        with self.assertRaisesRegex(ValueError, "Unknown evidence record_type"):
            evidence_from_dict(payload)


class EvidenceScientificBindingTests(unittest.TestCase):
    """C5-R1: evidence proves which model, registration and experiment it belongs to."""

    def setUp(self):
        self.source = EvidenceSourceIdentity(
            source_id="specimen-a/modal-inputs",
            source_type="modal-dataset",
            uri="project://specimen-a/evidence",
        )
        self.provenance = EvidenceProvenance(producer="abaqus-modal-comparator")
        self.timestamp = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)

    def binding(self, **changes):
        return EvidenceScientificBinding.create(**{**BINDING_FIELDS, **changes})

    def create(self, record_type=SensitivityEvidence, binding=None, content=None, source=None):
        return record_type.create(
            evidence_id=f"{record_type.RECORD_TYPE}-001",
            timestamp=self.timestamp,
            source_identity=source or self.source,
            provenance=self.provenance,
            status="COMPLETED",
            content=content or {"rank": 3, "values": [1.0, 2.0]},
            scientific_binding=binding,
        )

    # A
    def test_bound_evidence(self):
        record = self.create(binding=self.binding())
        self.assertEqual(record.binding_status, "BOUND")
        self.assertEqual(record.scientific_binding.to_dict(), BINDING_FIELDS)
        self.assertEqual(
            record.content_hash, evidence_record_hash(record.content, record.scientific_binding)
        )

    # B
    def test_unbound_historical_evidence_is_explicit(self):
        record = self.create()
        self.assertIsNone(record.scientific_binding)
        self.assertEqual(record.binding_status, "UNBOUND")
        self.assertIsNone(record.to_dict()["scientific_binding"])
        self.assertEqual(record.content_hash, evidence_content_hash(record.content))

    # C / D / E / F
    def test_binding_changes_the_record_hash(self):
        base = self.create(binding=self.binding())
        variants = {
            "model hash": self.create(binding=self.binding(identification_model_hash="d" * 64)),
            "model id": self.create(binding=self.binding(identification_model_id="effective_face_sheet")),
            "registration hash": self.create(binding=self.binding(registration_hash="e" * 64)),
            "experimental sha256": self.create(binding=self.binding(experimental_content_sha256="f" * 64)),
            "unbound": self.create(binding=None),
        }
        for name, variant in variants.items():
            with self.subTest(name):
                self.assertEqual(variant.content, base.content)
                self.assertNotEqual(variant.content_hash, base.content_hash)
                self.assertNotEqual(variant, base)
        hashes = {item.content_hash for item in variants.values()} | {base.content_hash}
        self.assertEqual(len(hashes), len(variants) + 1)

    def test_bound_hash_cannot_collide_with_unbound_lookalike_content(self):
        bound = self.create(binding=self.binding())
        lookalike = self.create(
            content={"content": dict(bound.content), "scientific_binding": BINDING_FIELDS}
        )
        self.assertNotEqual(lookalike.content_hash, bound.content_hash)

    # G / H / R
    def test_round_trip_preserves_binding_for_every_record_type(self):
        for record_type in RECORD_TYPES:
            for binding in (self.binding(), None):
                with self.subTest(record_type=record_type.__name__, bound=binding is not None):
                    record = self.create(record_type, binding=binding)
                    self.assertTrue(record.schema_version.endswith("/2.0"))
                    restored = evidence_from_json(record.to_json())
                    self.assertIs(type(restored), record_type)
                    self.assertEqual(restored, record)
                    self.assertEqual(restored.scientific_binding, binding)
                    self.assertEqual(restored.binding_status, record.binding_status)
                    self.assertEqual(restored.content_hash, record.content_hash)

    # I / J / K
    def test_tampered_binding_is_detected(self):
        payload = self.create(binding=self.binding()).to_dict()
        for name in ("identification_model_hash", "registration_hash", "experimental_content_sha256"):
            with self.subTest(name):
                tampered = json.loads(json.dumps(payload))
                tampered["scientific_binding"][name] = "9" * 64
                with self.assertRaisesRegex(ValueError, "content_hash does not match"):
                    SensitivityEvidence.from_dict(tampered)
        stripped = json.loads(json.dumps(payload))
        stripped["scientific_binding"] = None
        with self.assertRaisesRegex(ValueError, "content_hash does not match"):
            SensitivityEvidence.from_dict(stripped)
        malformed = json.loads(json.dumps(payload))
        malformed["scientific_binding"]["registration_hash"] = "not-a-hash"
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            SensitivityEvidence.from_dict(malformed)

    def test_binding_validation(self):
        invalid = {
            "empty model id": dict(identification_model_id=" "),
            "short model hash": dict(identification_model_hash="a" * 63),
            "non-hex registration": dict(registration_hash="g" * 64),
            "missing sha": dict(experimental_content_sha256=None),
        }
        for name, change in invalid.items():
            with self.subTest(name), self.assertRaises((TypeError, ValueError)):
                self.binding(**change)
        upper = self.binding(registration_hash="B" * 64)
        self.assertEqual(upper.registration_hash, "b" * 64)
        with self.assertRaisesRegex(ValueError, "unknown"):
            EvidenceScientificBinding.from_dict({**BINDING_FIELDS, "calibration": {}})
        with self.assertRaises(Exception):
            self.binding().registration_hash = "e" * 64

    # L / M / N / O / P
    def test_scientific_compatibility_is_exact(self):
        bound = self.create(binding=self.binding())
        self.assertTrue(bound.scientifically_compatible_with(**BINDING_FIELDS))
        self.assertTrue(self.binding().matches(**BINDING_FIELDS))
        mismatches = {
            "model id": dict(identification_model_id="effective_face_sheet"),
            "model hash": dict(identification_model_hash="d" * 64),
            "registration": dict(registration_hash="e" * 64),
            "experiment": dict(experimental_content_sha256="f" * 64),
        }
        for name, change in mismatches.items():
            with self.subTest(name):
                expected = {**BINDING_FIELDS, **change}
                self.assertFalse(bound.scientifically_compatible_with(**expected))
                self.assertFalse(self.binding().matches(**expected))
        unbound = self.create()
        self.assertFalse(unbound.scientifically_compatible_with(**BINDING_FIELDS))

    # Q
    def test_identical_source_labels_do_not_imply_compatibility(self):
        record = self.create(binding=self.binding(registration_hash="e" * 64))
        self.assertEqual(record.source_identity, self.source)
        self.assertFalse(record.scientifically_compatible_with(**BINDING_FIELDS))
        unbound = self.create(source=self.source)
        self.assertFalse(unbound.scientifically_compatible_with(**BINDING_FIELDS))

    # S / T
    def test_binding_carries_hashes_only(self):
        payload = self.create(binding=self.binding()).to_dict()["scientific_binding"]
        self.assertEqual(set(payload), set(BINDING_FIELDS))
        text = json.dumps(payload).lower()
        for forbidden in (
            "calibration", "orientation", "rotation", "geometry", "node", "mapped",
            "basis_km", "d11\"", "d12\"", "d66\"", "\"ex\"", "\"ey\"", "gxy",
        ):
            self.assertNotIn(forbidden, text)
        self.assertEqual(
            EvidenceScientificBinding.FIELD_NAMES,
            ("identification_model_id", "identification_model_hash",
             "registration_hash", "experimental_content_sha256"),
        )

    def test_old_and_implicit_schemas_are_rejected(self):
        payload = self.create(binding=self.binding()).to_dict()
        old = dict(payload, schema_version="sensitivity-evidence/1.0")
        del old["scientific_binding"]
        with self.assertRaisesRegex(ValueError, "1.0 records cannot state a scientific binding"):
            SensitivityEvidence.from_dict(old)
        implicit = dict(self.create().to_dict())
        del implicit["scientific_binding"]
        with self.assertRaisesRegex(ValueError, "state scientific_binding explicitly"):
            SensitivityEvidence.from_dict(implicit)
        with self.assertRaisesRegex(TypeError, "EvidenceScientificBinding"):
            self.create(binding=BINDING_FIELDS)


if __name__ == "__main__":
    unittest.main()
