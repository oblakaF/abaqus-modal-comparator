"""Versioned evidence envelopes for GUI/backend integration.

The records in this module contain no scientific calculations.  They provide
stable, strictly validated identities and deterministic serialization around
evidence content produced elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from typing import Any, ClassVar, Mapping, TypeVar
from uuid import uuid4


_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_STATUS_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty.")
    return normalized


def _optional_text(value: object, name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, name)


def _content_hash(value: object, name: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    normalized = _required_text(value, name).lower()
    if not _HASH_PATTERN.fullmatch(normalized):
        raise ValueError(f"{name} must be a lowercase SHA-256 hexadecimal digest.")
    return normalized


def _json_value(value: object, path: str = "content") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must not contain non-finite numbers.")
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} keys must be strings.")
            normalized[key] = _json_value(item, f"{path}.{key}")
        return normalized
    if isinstance(value, (tuple, list)):
        return tuple(
            _json_value(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        )
    raise TypeError(f"{path} contains unsupported value type {type(value).__name__}.")


def _schema_major(schema_version: str, version: str) -> str:
    """Return the same schema family at another version, e.g. '.../1.0'."""
    return schema_version.rsplit("/", 1)[0] + "/" + version


def _json_output(value: object) -> Any:
    if isinstance(value, Mapping):
        return {key: _json_output(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_output(item) for item in value]
    return value


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def evidence_content_hash(content: Mapping[str, object]) -> str:
    """Return the canonical SHA-256 digest for validated evidence content."""

    if not isinstance(content, Mapping):
        raise TypeError("content must be a mapping.")
    return hashlib.sha256(_canonical_json(_json_output(_json_value(content)))).hexdigest()


@dataclass(frozen=True)
class EvidenceScientificBinding:
    """Which model definition, registration, and experiment content a result belongs to.

    Hashes only: the registration hash seals calibration, orientation, FE
    geometry, and node mapping; the model hash seals the parameterization; the
    experimental SHA-256 makes the source content explicit.  No payloads and no
    parameter values are carried.  The producer that knows these values (the
    runner) supplies them; nothing here infers them.
    """

    identification_model_id: str
    identification_model_hash: str
    registration_hash: str
    experimental_content_sha256: str

    FIELD_NAMES: ClassVar[tuple[str, ...]] = (
        "identification_model_id",
        "identification_model_hash",
        "registration_hash",
        "experimental_content_sha256",
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "identification_model_id",
            _required_text(self.identification_model_id, "identification_model_id"),
        )
        for name in self.FIELD_NAMES[1:]:
            object.__setattr__(self, name, _content_hash(getattr(self, name), name))

    @classmethod
    def create(
        cls,
        *,
        identification_model_id: str,
        identification_model_hash: str,
        registration_hash: str,
        experimental_content_sha256: str,
    ) -> "EvidenceScientificBinding":
        return cls(
            identification_model_id=identification_model_id,
            identification_model_hash=identification_model_hash,
            registration_hash=registration_hash,
            experimental_content_sha256=experimental_content_sha256,
        )

    def matches(
        self,
        *,
        identification_model_id: str,
        identification_model_hash: str,
        registration_hash: str,
        experimental_content_sha256: str,
    ) -> bool:
        """Exact scientific match on all four identities; descriptive labels play no part."""
        expected = (
            identification_model_id,
            identification_model_hash,
            registration_hash,
            experimental_content_sha256,
        )
        return tuple(getattr(self, name) for name in self.FIELD_NAMES) == expected

    def to_dict(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.FIELD_NAMES}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "EvidenceScientificBinding":
        if not isinstance(payload, Mapping):
            raise TypeError("scientific_binding must be a mapping.")
        missing = [name for name in cls.FIELD_NAMES if name not in payload]
        unknown = sorted(set(payload) - set(cls.FIELD_NAMES))
        if missing or unknown:
            raise ValueError(
                f"Invalid scientific_binding: missing {missing}, unknown {unknown}."
            )
        return cls(**{name: payload[name] for name in cls.FIELD_NAMES})


_BOUND_RECORD_HASH_DOMAIN = b"evidence-scientific-binding/1\n"


def evidence_record_hash(
    content: Mapping[str, object],
    scientific_binding: EvidenceScientificBinding | None,
) -> str:
    """Digest sealing an evidence record's content and scientific binding.

    Unbound records keep the content-only digest.  Bound records hash a
    domain-separated document of content plus binding, so a bound record can
    never share a digest with an unbound one or with a different binding.
    """

    if scientific_binding is None:
        return evidence_content_hash(content)
    if not isinstance(scientific_binding, EvidenceScientificBinding):
        raise TypeError("scientific_binding must be an EvidenceScientificBinding or None.")
    document = {
        "content": _json_output(_json_value(content)),
        "scientific_binding": scientific_binding.to_dict(),
    }
    return hashlib.sha256(_BOUND_RECORD_HASH_DOMAIN + _canonical_json(document)).hexdigest()


@dataclass(frozen=True)
class EvidenceSourceIdentity:
    """Stable identity of the primary source represented by an evidence record."""

    source_id: str
    source_type: str
    uri: str | None = None
    content_hash: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _required_text(self.source_id, "source_id"))
        object.__setattr__(
            self, "source_type", _required_text(self.source_type, "source_type")
        )
        object.__setattr__(self, "uri", _optional_text(self.uri, "uri"))
        object.__setattr__(
            self,
            "content_hash",
            _content_hash(self.content_hash, "source content_hash", optional=True),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "uri": self.uri,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "EvidenceSourceIdentity":
        if not isinstance(payload, Mapping):
            raise TypeError("source_identity must be a mapping.")
        return cls(
            source_id=payload["source_id"],
            source_type=payload["source_type"],
            uri=payload.get("uri"),
            content_hash=payload.get("content_hash"),
        )


@dataclass(frozen=True)
class EvidenceProvenance:
    """Origin of an evidence record without embedding execution behavior."""

    producer: str
    producer_version: str | None = None
    commit: str | None = None
    method: str | None = None
    artifacts: tuple[EvidenceSourceIdentity, ...] = ()
    details: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "producer", _required_text(self.producer, "producer"))
        optional_values = (
            ("producer_version", self.producer_version),
            ("commit", self.commit),
            ("method", self.method),
        )
        for name, value in optional_values:
            object.__setattr__(self, name, _optional_text(value, name))
        artifacts = tuple(self.artifacts)
        if not all(isinstance(item, EvidenceSourceIdentity) for item in artifacts):
            raise TypeError("artifacts must contain EvidenceSourceIdentity records.")
        object.__setattr__(self, "artifacts", artifacts)
        if not isinstance(self.details, Mapping):
            raise TypeError("provenance details must be a mapping.")
        object.__setattr__(self, "details", _json_value(self.details, "provenance.details"))

    def to_dict(self) -> dict[str, object]:
        return {
            "producer": self.producer,
            "producer_version": self.producer_version,
            "commit": self.commit,
            "method": self.method,
            "artifacts": [item.to_dict() for item in self.artifacts],
            "details": _json_output(self.details),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "EvidenceProvenance":
        if not isinstance(payload, Mapping):
            raise TypeError("provenance must be a mapping.")
        artifacts = payload.get("artifacts", ())
        if not isinstance(artifacts, (tuple, list)):
            raise TypeError("provenance artifacts must be a sequence.")
        return cls(
            producer=payload["producer"],
            producer_version=payload.get("producer_version"),
            commit=payload.get("commit"),
            method=payload.get("method"),
            artifacts=tuple(EvidenceSourceIdentity.from_dict(item) for item in artifacts),
            details=payload.get("details", {}),
        )


EvidenceT = TypeVar("EvidenceT", bound="EvidenceRecord")


@dataclass(frozen=True, kw_only=True)
class EvidenceRecord:
    """Base versioned envelope shared by every evidence category.

    ``source_identity`` and ``provenance.artifacts`` say where an artifact came
    from.  ``scientific_binding`` says which model definition, registration, and
    experiment content the scientific result belongs to; ``None`` marks an
    explicitly UNBOUND (historical) record that is never scientifically
    compatible with a bound session.  There is no implied equivalence between
    the two.
    """

    schema_version: str
    evidence_id: str
    timestamp: datetime
    source_identity: EvidenceSourceIdentity
    parent_ids: tuple[str, ...]
    content_hash: str
    provenance: EvidenceProvenance
    status: str
    content: Mapping[str, object]
    scientific_binding: EvidenceScientificBinding | None = None

    RECORD_TYPE: ClassVar[str] = "evidence"
    # 2.0 adds an explicit scientific_binding (object or null) that is sealed
    # into content_hash; 1.0 records had no way to state a binding.
    SCHEMA_VERSION: ClassVar[str] = "evidence/2.0"

    def __post_init__(self) -> None:
        schema = _required_text(self.schema_version, "schema_version")
        if schema == _schema_major(self.SCHEMA_VERSION, "1.0"):
            raise ValueError(
                f"Unsupported evidence schema {schema!r}: 1.0 records cannot state a "
                "scientific binding; re-create the record as "
                f"{self.SCHEMA_VERSION!r} (explicitly unbound if historical)."
            )
        if schema != self.SCHEMA_VERSION:
            raise ValueError(
                f"{type(self).__name__} requires schema_version {self.SCHEMA_VERSION!r}."
            )
        object.__setattr__(self, "schema_version", schema)
        evidence_id = _required_text(self.evidence_id, "evidence_id")
        object.__setattr__(self, "evidence_id", evidence_id)
        if not isinstance(self.timestamp, datetime):
            raise TypeError("timestamp must be a datetime.")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must include a timezone.")
        object.__setattr__(self, "timestamp", self.timestamp.astimezone(timezone.utc))
        if not isinstance(self.source_identity, EvidenceSourceIdentity):
            raise TypeError("source_identity must be an EvidenceSourceIdentity.")
        if not isinstance(self.provenance, EvidenceProvenance):
            raise TypeError("provenance must be an EvidenceProvenance.")
        if isinstance(self.parent_ids, str):
            raise TypeError("parent_ids must be a sequence of identifiers.")
        parents = tuple(_required_text(item, "parent_id") for item in self.parent_ids)
        if len(parents) != len(set(parents)):
            raise ValueError("parent_ids must be unique.")
        if evidence_id in parents:
            raise ValueError("An evidence record cannot be its own parent.")
        object.__setattr__(self, "parent_ids", parents)
        status = _required_text(self.status, "status").upper()
        if not _STATUS_PATTERN.fullmatch(status):
            raise ValueError("status must be an uppercase identifier.")
        object.__setattr__(self, "status", status)
        if not isinstance(self.content, Mapping):
            raise TypeError("content must be a mapping.")
        content = _json_value(self.content)
        object.__setattr__(self, "content", content)
        if self.scientific_binding is not None and not isinstance(
            self.scientific_binding, EvidenceScientificBinding
        ):
            raise TypeError(
                "scientific_binding must be an EvidenceScientificBinding or None."
            )
        supplied_hash = _content_hash(self.content_hash, "content_hash")
        expected_hash = evidence_record_hash(content, self.scientific_binding)
        if supplied_hash != expected_hash:
            raise ValueError(
                "content_hash does not match the canonical evidence content and "
                "scientific binding."
            )
        object.__setattr__(self, "content_hash", supplied_hash)

    @property
    def binding_status(self) -> str:
        return "BOUND" if self.scientific_binding is not None else "UNBOUND"

    def scientifically_compatible_with(
        self,
        *,
        identification_model_id: str,
        identification_model_hash: str,
        registration_hash: str,
        experimental_content_sha256: str,
    ) -> bool:
        """True only for a bound record whose binding matches exactly.

        Unbound (historical) evidence is never compatible, whatever its
        descriptive source labels say.
        """
        if self.scientific_binding is None:
            return False
        return self.scientific_binding.matches(
            identification_model_id=identification_model_id,
            identification_model_hash=identification_model_hash,
            registration_hash=registration_hash,
            experimental_content_sha256=experimental_content_sha256,
        )

    @classmethod
    def create(
        cls: type[EvidenceT],
        *,
        source_identity: EvidenceSourceIdentity,
        provenance: EvidenceProvenance,
        status: str,
        content: Mapping[str, object],
        parent_ids: tuple[str, ...] = (),
        evidence_id: str | None = None,
        timestamp: datetime | None = None,
        scientific_binding: EvidenceScientificBinding | None = None,
    ) -> EvidenceT:
        normalized_content = _json_value(content)
        return cls(
            schema_version=cls.SCHEMA_VERSION,
            evidence_id=evidence_id or str(uuid4()),
            timestamp=timestamp or datetime.now(timezone.utc),
            source_identity=source_identity,
            parent_ids=parent_ids,
            content_hash=evidence_record_hash(normalized_content, scientific_binding),
            provenance=provenance,
            status=status,
            content=normalized_content,
            scientific_binding=scientific_binding,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "record_type": self.RECORD_TYPE,
            "schema_version": self.schema_version,
            "evidence_id": self.evidence_id,
            "timestamp": self.timestamp.isoformat().replace("+00:00", "Z"),
            "source_identity": self.source_identity.to_dict(),
            "parent_ids": list(self.parent_ids),
            "content_hash": self.content_hash,
            "provenance": self.provenance.to_dict(),
            "status": self.status,
            "content": _json_output(self.content),
            "scientific_binding": (
                None
                if self.scientific_binding is None
                else self.scientific_binding.to_dict()
            ),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            indent=indent,
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n"

    @classmethod
    def from_dict(cls: type[EvidenceT], payload: Mapping[str, object]) -> EvidenceT:
        if not isinstance(payload, Mapping):
            raise TypeError("evidence payload must be a mapping.")
        if payload.get("record_type") != cls.RECORD_TYPE:
            raise ValueError(f"Expected record_type {cls.RECORD_TYPE!r}.")
        timestamp = payload["timestamp"]
        if not isinstance(timestamp, str):
            raise TypeError("timestamp must be an ISO-8601 string.")
        try:
            parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("timestamp must be a valid ISO-8601 value.") from error
        parent_ids = payload["parent_ids"]
        if not isinstance(parent_ids, (tuple, list)):
            raise TypeError("parent_ids must be a sequence.")
        if payload.get("schema_version") == _schema_major(cls.SCHEMA_VERSION, "1.0"):
            raise ValueError(
                f"Unsupported evidence schema {payload['schema_version']!r}: 1.0 records "
                "cannot state a scientific binding and are not reinterpreted."
            )
        if "scientific_binding" not in payload:
            raise ValueError(
                "Evidence payload must state scientific_binding explicitly "
                "(null for unbound historical evidence)."
            )
        binding = payload["scientific_binding"]
        return cls(
            schema_version=payload["schema_version"],
            evidence_id=payload["evidence_id"],
            timestamp=parsed_timestamp,
            source_identity=EvidenceSourceIdentity.from_dict(payload["source_identity"]),
            parent_ids=tuple(parent_ids),
            content_hash=payload["content_hash"],
            provenance=EvidenceProvenance.from_dict(payload["provenance"]),
            status=payload["status"],
            content=payload["content"],
            scientific_binding=(
                None if binding is None else EvidenceScientificBinding.from_dict(binding)
            ),
        )

    @classmethod
    def from_json(cls: type[EvidenceT], payload: str) -> EvidenceT:
        if not isinstance(payload, str):
            raise TypeError("JSON payload must be a string.")
        return cls.from_dict(json.loads(payload))


@dataclass(frozen=True, kw_only=True)
class SensitivityEvidence(EvidenceRecord):
    RECORD_TYPE: ClassVar[str] = "sensitivity"
    SCHEMA_VERSION: ClassVar[str] = "sensitivity-evidence/2.0"


@dataclass(frozen=True, kw_only=True)
class IdentifiabilityEvidence(EvidenceRecord):
    RECORD_TYPE: ClassVar[str] = "identifiability"
    SCHEMA_VERSION: ClassVar[str] = "identifiability-evidence/2.0"


@dataclass(frozen=True, kw_only=True)
class IdentificationEvidence(EvidenceRecord):
    RECORD_TYPE: ClassVar[str] = "identification"
    SCHEMA_VERSION: ClassVar[str] = "identification-evidence/2.0"


@dataclass(frozen=True, kw_only=True)
class ValidationEvidence(EvidenceRecord):
    RECORD_TYPE: ClassVar[str] = "validation"
    SCHEMA_VERSION: ClassVar[str] = "validation-evidence/2.0"


_EVIDENCE_TYPES: Mapping[str, type[EvidenceRecord]] = {
    record_type.RECORD_TYPE: record_type
    for record_type in (
        SensitivityEvidence,
        IdentifiabilityEvidence,
        IdentificationEvidence,
        ValidationEvidence,
    )
}


def evidence_from_dict(payload: Mapping[str, object]) -> EvidenceRecord:
    """Deserialize an evidence envelope using its exact type discriminator."""

    if not isinstance(payload, Mapping):
        raise TypeError("evidence payload must be a mapping.")
    record_type = payload.get("record_type")
    if not isinstance(record_type, str) or record_type not in _EVIDENCE_TYPES:
        raise ValueError(f"Unknown evidence record_type {record_type!r}.")
    return _EVIDENCE_TYPES[record_type].from_dict(payload)


def evidence_from_json(payload: str) -> EvidenceRecord:
    if not isinstance(payload, str):
        raise TypeError("JSON payload must be a string.")
    return evidence_from_dict(json.loads(payload))


__all__ = [
    "EvidenceProvenance",
    "EvidenceRecord",
    "EvidenceScientificBinding",
    "EvidenceSourceIdentity",
    "IdentificationEvidence",
    "IdentifiabilityEvidence",
    "SensitivityEvidence",
    "ValidationEvidence",
    "evidence_content_hash",
    "evidence_from_dict",
    "evidence_from_json",
    "evidence_record_hash",
]
