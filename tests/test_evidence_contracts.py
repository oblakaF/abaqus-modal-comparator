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
    EvidenceSourceIdentity,
    IdentificationEvidence,
    IdentifiabilityEvidence,
    SensitivityEvidence,
    ValidationEvidence,
    evidence_content_hash,
    evidence_from_dict,
    evidence_from_json,
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


if __name__ == "__main__":
    unittest.main()
