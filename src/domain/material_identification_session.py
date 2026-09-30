"""Application session contract for material identification.

The session owns configuration, source binding, evidence references, and
readiness checks.  Which parameters exist, what they mean, and which
assumptions are frozen is owned by the referenced
``IdentificationModelDefinition``; the session only selects parameters from it
and stores campaign bounds.  It intentionally has no dependency on Abaqus,
sensitivity services, identifiability services, or inverse solvers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
from types import MappingProxyType
from typing import ClassVar, Iterable, Union
from uuid import uuid4

from .evidence import EvidenceProvenance, EvidenceRecord
from .identification_model import IdentificationModelDefinition
from .registration import FROZEN_REGISTRATION_SCHEMA, FrozenRegistration


EVIDENCE_RECORD_TYPES = frozenset(
    ("sensitivity", "identifiability", "identification", "validation")
)


def _text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty.")
    return normalized


def _sequence(value: object, name: str) -> tuple:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{name} must be a sequence.")
    return tuple(value)


@dataclass(frozen=True)
class ParameterBounds:
    """Campaign/run bounds for one model parameter (never part of the model hash)."""

    lower: float
    upper: float
    unit: str

    def __post_init__(self) -> None:
        lower = float(self.lower)
        upper = float(self.upper)
        if not math.isfinite(lower) or not math.isfinite(upper):
            raise ValueError("Parameter bounds must be finite.")
        if lower >= upper:
            raise ValueError("Parameter lower bound must be less than upper bound.")
        object.__setattr__(self, "lower", lower)
        object.__setattr__(self, "upper", upper)
        object.__setattr__(self, "unit", _text(self.unit, "bound unit"))

    def to_dict(self) -> dict[str, object]:
        return {"lower": self.lower, "upper": self.upper, "unit": self.unit}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "ParameterBounds":
        if not isinstance(payload, Mapping):
            raise TypeError("parameter bounds must be a mapping.")
        return cls(
            lower=payload["lower"],
            upper=payload["upper"],
            unit=payload["unit"],
        )


SCIENTIFIC_TASK_HASH_SCHEMA = "material-identification-task-scientific/1"


@dataclass(frozen=True)
class FixedParameterValue:
    """A declared campaign value for a model parameter that is not fitted.

    Fixed values are never invented: a model parameter that is neither selected
    for fitting nor declared here leaves the session not ready.  No bounds apply.
    """

    value: float
    unit: str

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise TypeError("A fixed parameter value must be a real number.")
        value = float(self.value)
        if not math.isfinite(value):
            raise ValueError("A fixed parameter value must be finite.")
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "unit", _text(self.unit, "fixed value unit"))

    def to_dict(self) -> dict[str, object]:
        return {"value": self.value, "unit": self.unit}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "FixedParameterValue":
        if not isinstance(payload, Mapping):
            raise TypeError("fixed parameter value must be a mapping.")
        return cls(value=payload["value"], unit=payload["unit"])


ModelCatalog = Union[
    IdentificationModelDefinition,
    Mapping[str, IdentificationModelDefinition],
    Iterable[IdentificationModelDefinition],
]


def resolve_identification_model(
    model_id: object, model_hash: object, models: ModelCatalog
) -> IdentificationModelDefinition:
    """Return the exact model definition named by a stored id and hash.

    A model with the same id but a different definition hash is refused; it is
    never substituted for the stored one.
    """

    model_id = _text(model_id, "identification_model_id")
    model_hash = _text(model_hash, "identification_model_hash")
    if isinstance(models, IdentificationModelDefinition):
        candidates = (models,)
    elif isinstance(models, Mapping):
        candidates = tuple(models.values())
    else:
        candidates = tuple(models)
    if not all(isinstance(item, IdentificationModelDefinition) for item in candidates):
        raise TypeError("models must contain IdentificationModelDefinition records.")
    same_id = [item for item in candidates if item.model_id == model_id]
    if not same_id:
        raise ValueError(f"Unknown identification model {model_id!r}.")
    for item in same_id:
        if item.definition_hash == model_hash:
            return item
    raise ValueError(
        f"Identification model {model_id!r} definition hash mismatch: the session "
        "was created for a different definition."
    )


def _bounds_items(value: object) -> tuple[tuple[str, ParameterBounds], ...]:
    if isinstance(value, Mapping):
        items = tuple(value.items())
    elif isinstance(value, (list, tuple)):
        items = tuple(value)
    else:
        raise TypeError("parameter_bounds must be a mapping or a sequence of pairs.")
    result = []
    for item in items:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise TypeError("parameter_bounds entries must be (parameter_id, bounds) pairs.")
        parameter_id, bounds = item
        if not isinstance(bounds, ParameterBounds):
            raise TypeError("parameter_bounds values must be ParameterBounds.")
        result.append((_text(parameter_id, "bounds parameter ID"), bounds))
    return tuple(result)


def _fixed_items(value: object) -> tuple[tuple[str, FixedParameterValue], ...]:
    if isinstance(value, Mapping):
        items = tuple(value.items())
    elif isinstance(value, (list, tuple)):
        items = tuple(value)
    else:
        raise TypeError("fixed_parameter_values must be a mapping or a sequence of pairs.")
    result = []
    for item in items:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise TypeError(
                "fixed_parameter_values entries must be (parameter_id, value) pairs."
            )
        parameter_id, fixed = item
        if not isinstance(fixed, FixedParameterValue):
            raise TypeError("fixed_parameter_values values must be FixedParameterValue.")
        result.append((_text(parameter_id, "fixed parameter ID"), fixed))
    return tuple(result)


@dataclass(frozen=True)
class MaterialIdentificationTaskDefinition:
    """One identification task: a model, a parameter selection, and campaign bounds.

    ``model`` is held in memory for validation; serialization stores only its
    id and definition hash, and restoring requires the exact definition.
    ``selected_parameter_ids`` are fitted; ``fixed_parameter_values`` declare
    the campaign value of model parameters that are not fitted.
    """

    model: IdentificationModelDefinition
    selected_parameter_ids: tuple[str, ...]
    parameter_bounds: tuple[tuple[str, ParameterBounds], ...]
    weighting_selection: str
    provenance: EvidenceProvenance
    fixed_parameter_values: tuple[tuple[str, FixedParameterValue], ...] = ()

    def __post_init__(self) -> None:
        model = self.model
        if not isinstance(model, IdentificationModelDefinition):
            raise TypeError("model must be an IdentificationModelDefinition.")
        known = model.parameter_ids
        if isinstance(self.selected_parameter_ids, (str, bytes)) or not isinstance(
            self.selected_parameter_ids, Sequence
        ):
            raise TypeError("selected_parameter_ids must be a sequence.")
        selected = tuple(
            _text(value, "selected parameter ID") for value in self.selected_parameter_ids
        )
        if not selected or len(selected) != len(set(selected)):
            raise ValueError("Selected parameter IDs must be non-empty and unique.")
        unknown = [item for item in selected if item not in known]
        if unknown:
            raise ValueError(
                f"Selected parameter IDs {unknown} are not defined by identification "
                f"model {model.model_id!r}."
            )
        bounds = dict()
        for parameter_id, value in _bounds_items(self.parameter_bounds):
            if parameter_id not in known:
                raise ValueError(
                    f"Bounds for {parameter_id!r}: the parameter is not defined by "
                    f"identification model {model.model_id!r}."
                )
            if parameter_id in bounds:
                raise ValueError(f"Duplicate bounds for {parameter_id!r}.")
            expected_unit = model.parameter(parameter_id).unit
            if value.unit != expected_unit:
                raise ValueError(
                    f"Bounds for {parameter_id!r} use unit {value.unit!r}; model "
                    f"{model.model_id!r} defines {expected_unit!r}."
                )
            bounds[parameter_id] = value
        fixed = dict()
        for parameter_id, value in _fixed_items(self.fixed_parameter_values):
            if parameter_id not in known:
                raise ValueError(
                    f"Fixed value for {parameter_id!r}: the parameter is not defined by "
                    f"identification model {model.model_id!r}."
                )
            if parameter_id in fixed:
                raise ValueError(f"Duplicate fixed value for {parameter_id!r}.")
            if parameter_id in selected:
                raise ValueError(
                    f"Parameter {parameter_id!r} cannot be both selected for fitting "
                    "and fixed."
                )
            expected_unit = model.parameter(parameter_id).unit
            if value.unit != expected_unit:
                raise ValueError(
                    f"Fixed value for {parameter_id!r} uses unit {value.unit!r}; model "
                    f"{model.model_id!r} defines {expected_unit!r}."
                )
            fixed[parameter_id] = value
        if not isinstance(self.provenance, EvidenceProvenance):
            raise TypeError("provenance must be an EvidenceProvenance record.")
        object.__setattr__(self, "selected_parameter_ids", selected)
        # Stored in the model's parameter order, independent of caller order.
        object.__setattr__(
            self,
            "parameter_bounds",
            tuple((item, bounds[item]) for item in known if item in bounds),
        )
        object.__setattr__(
            self,
            "fixed_parameter_values",
            tuple((item, fixed[item]) for item in known if item in fixed),
        )
        object.__setattr__(
            self,
            "weighting_selection",
            _text(self.weighting_selection, "weighting_selection"),
        )

    @property
    def identification_model_id(self) -> str:
        return self.model.model_id

    @property
    def identification_model_hash(self) -> str:
        return self.model.definition_hash

    @property
    def frozen_assumptions(self) -> tuple[str, ...]:
        return self.model.frozen_assumptions

    @property
    def scientific_task_hash(self) -> str:
        """SHA-256 sealing the scientific execution configuration of this task.

        Covers the model identity, the fitted selection (in its stated order),
        the bounds, the fixed values, and the weighting selection.  Descriptive
        provenance is excluded; frozen assumptions are already sealed by the
        model definition hash.
        """

        document = {
            "schema": SCIENTIFIC_TASK_HASH_SCHEMA,
            "identification_model_id": self.identification_model_id,
            "identification_model_hash": self.identification_model_hash,
            "selected_parameter_ids": list(self.selected_parameter_ids),
            "parameter_bounds": [
                {"parameter_id": parameter_id, **bounds.to_dict()}
                for parameter_id, bounds in self.parameter_bounds
            ],
            "fixed_parameter_values": [
                {"parameter_id": parameter_id, **fixed.to_dict()}
                for parameter_id, fixed in self.fixed_parameter_values
            ],
            "weighting_selection": self.weighting_selection,
        }
        encoded = json.dumps(
            document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def bounds_for(self, parameter_id: str) -> ParameterBounds | None:
        return dict(self.parameter_bounds).get(parameter_id)

    def fixed_value_for(self, parameter_id: str) -> FixedParameterValue | None:
        return dict(self.fixed_parameter_values).get(parameter_id)

    def to_dict(self) -> dict[str, object]:
        return {
            "identification_model_id": self.identification_model_id,
            "identification_model_hash": self.identification_model_hash,
            "frozen_assumptions": list(self.frozen_assumptions),
            "selected_parameter_ids": list(self.selected_parameter_ids),
            "parameter_bounds": [
                {"parameter_id": parameter_id, **bounds.to_dict()}
                for parameter_id, bounds in self.parameter_bounds
            ],
            "fixed_parameter_values": [
                {"parameter_id": parameter_id, **fixed.to_dict()}
                for parameter_id, fixed in self.fixed_parameter_values
            ],
            "weighting_selection": self.weighting_selection,
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, object], *, models: ModelCatalog
    ) -> "MaterialIdentificationTaskDefinition":
        if not isinstance(payload, Mapping):
            raise TypeError("task_definition must be a mapping.")
        model = resolve_identification_model(
            payload["identification_model_id"],
            payload["identification_model_hash"],
            models,
        )
        stored_assumptions = tuple(
            _sequence(payload["frozen_assumptions"], "frozen_assumptions")
        )
        if stored_assumptions != model.frozen_assumptions:
            raise ValueError(
                "Stored frozen assumptions differ from the referenced model definition."
            )
        bounds = []
        for item in _sequence(payload["parameter_bounds"], "parameter_bounds"):
            if not isinstance(item, Mapping):
                raise TypeError("parameter_bounds entries must be mappings.")
            bounds.append(
                (
                    item["parameter_id"],
                    ParameterBounds.from_dict(
                        {key: item[key] for key in ("lower", "upper", "unit")}
                    ),
                )
            )
        # Absent in payloads written before fixed values existed: an empty set.
        fixed = []
        for item in _sequence(
            payload.get("fixed_parameter_values", ()), "fixed_parameter_values"
        ):
            if not isinstance(item, Mapping):
                raise TypeError("fixed_parameter_values entries must be mappings.")
            fixed.append(
                (
                    item["parameter_id"],
                    FixedParameterValue.from_dict(
                        {key: item[key] for key in ("value", "unit")}
                    ),
                )
            )
        return cls(
            model=model,
            selected_parameter_ids=tuple(
                _sequence(payload["selected_parameter_ids"], "selected_parameter_ids")
            ),
            parameter_bounds=tuple(bounds),
            weighting_selection=payload["weighting_selection"],
            provenance=EvidenceProvenance.from_dict(payload["provenance"]),
            fixed_parameter_values=tuple(fixed),
        )


def _optional_text(value: object, name: str) -> str | None:
    return None if value is None else _text(value, name)


@dataclass(frozen=True)
class MaterialIdentificationSourceIdentities:
    """Descriptive, non-authoritative labels for the specimen and its sources.

    The scientific experiment identity (SHA-256 content identity), the FE
    geometry identity, and the calibration are owned by the bound
    ``FrozenRegistration``; nothing here can contradict them.  Evidence
    references are still matched against these labels.
    """

    specimen_label: str
    source_label: str | None = None
    source_uri: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "specimen_label", _text(self.specimen_label, "specimen_label"))
        object.__setattr__(self, "source_label", _optional_text(self.source_label, "source_label"))
        object.__setattr__(self, "source_uri", _optional_text(self.source_uri, "source_uri"))

    def to_dict(self) -> dict[str, object]:
        return {
            "specimen_label": self.specimen_label,
            "source_label": self.source_label,
            "source_uri": self.source_uri,
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, object]
    ) -> "MaterialIdentificationSourceIdentities":
        if not isinstance(payload, Mapping):
            raise TypeError("source_identities must be a mapping.")
        unknown = sorted(set(payload) - {"specimen_label", "source_label", "source_uri"})
        if unknown:
            raise ValueError(f"Unknown source identity fields: {unknown}.")
        return cls(
            specimen_label=payload["specimen_label"],
            source_label=payload.get("source_label"),
            source_uri=payload.get("source_uri"),
        )


_HEX64 = frozenset("0123456789abcdef")
_REFERENCE_ORIGIN = object()  # only from_registration may build a reference
FE_GEOMETRY_IDENTITY_V2 = "fe-geometry-identity/2"


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= _HEX64


def _frozen_json(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _frozen_json(item) for key, item in sorted(value.items())})
    if isinstance(value, (list, tuple)):
        return tuple(_frozen_json(item) for item in value)
    return value


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_json(item) for item in value]
    return value


@dataclass(frozen=True)
class FrozenRegistrationReference:
    """Exact binding of a session to one sealed ``FrozenRegistration``.

    Carries only what identifies the registration: its sealed hash, schema,
    experimental content identity, and FE geometry identity v2.  Calibration,
    orientation, and node mapping stay inside the registration; no FE
    stiffness/model identity is involved.  Built only by ``from_registration``.
    """

    registration_hash: str
    registration_schema_version: str
    experimental_source_identity: Mapping[str, object]
    fe_geometry_identity: Mapping[str, object]
    _origin: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._origin is not _REFERENCE_ORIGIN:
            raise TypeError(
                "FrozenRegistrationReference must be built with from_registration() "
                "from a real FrozenRegistration."
            )
        if not _is_sha256(self.registration_hash):
            raise ValueError("registration_hash must be a lowercase SHA-256 digest.")
        if self.registration_schema_version != FROZEN_REGISTRATION_SCHEMA:
            raise ValueError(
                f"registration_schema_version must be {FROZEN_REGISTRATION_SCHEMA!r}."
            )
        experimental = self.experimental_source_identity
        if not isinstance(experimental, Mapping) or not _is_sha256(experimental.get("sha256")):
            raise ValueError(
                "The registration's experimental source identity has no SHA-256 content "
                "identity; a legacy path/size/mtime identity cannot bind a session."
            )
        geometry = self.fe_geometry_identity
        if not isinstance(geometry, Mapping) or geometry.get("schema_version") != FE_GEOMETRY_IDENTITY_V2:
            raise ValueError(
                f"The registration's FE geometry identity must be {FE_GEOMETRY_IDENTITY_V2!r}."
            )
        if not _is_sha256(geometry.get("sha256")):
            raise ValueError("The FE geometry identity has no SHA-256 digest.")
        object.__setattr__(self, "experimental_source_identity", _frozen_json(experimental))
        object.__setattr__(self, "fe_geometry_identity", _frozen_json(geometry))

    @classmethod
    def from_registration(cls, registration: FrozenRegistration) -> "FrozenRegistrationReference":
        if not isinstance(registration, FrozenRegistration):
            raise TypeError("A real FrozenRegistration is required.")
        return cls(
            registration_hash=registration.registration_hash,
            registration_schema_version=registration.registration_schema_version,
            experimental_source_identity=_plain_json(registration.experimental_source_identity),
            fe_geometry_identity=_plain_json(registration.fe_geometry_identity),
            _origin=_REFERENCE_ORIGIN,
        )

    @property
    def experimental_content_sha256(self) -> str:
        return str(self.experimental_source_identity["sha256"])

    @property
    def fe_geometry_sha256(self) -> str:
        return str(self.fe_geometry_identity["sha256"])

    def to_dict(self) -> dict[str, object]:
        return {
            "registration_hash": self.registration_hash,
            "registration_schema_version": self.registration_schema_version,
            "experimental_source_identity": _plain_json(self.experimental_source_identity),
            "fe_geometry_identity": _plain_json(self.fe_geometry_identity),
        }


RegistrationCatalog = Union[
    FrozenRegistration,
    Mapping[str, FrozenRegistration],
    Iterable[FrozenRegistration],
]


def resolve_registration_reference(
    payload: object, registrations: RegistrationCatalog
) -> FrozenRegistrationReference:
    """Rebuild a stored reference from the exact registration it names.

    The stored fields must equal those derived from the registration, so a
    tampered hash, experimental identity, or geometry identity is refused.
    """

    if not isinstance(payload, Mapping):
        raise TypeError("registration reference must be a mapping.")
    if isinstance(registrations, FrozenRegistration):
        candidates = (registrations,)
    elif isinstance(registrations, Mapping):
        candidates = tuple(registrations.values())
    else:
        candidates = tuple(registrations)
    if not all(isinstance(item, FrozenRegistration) for item in candidates):
        raise TypeError("registrations must contain FrozenRegistration records.")
    stored_hash = payload.get("registration_hash")
    match = next((item for item in candidates if item.registration_hash == stored_hash), None)
    if match is None:
        raise ValueError(f"Unknown FrozenRegistration {stored_hash!r}.")
    reference = FrozenRegistrationReference.from_registration(match)
    if dict(payload) != reference.to_dict():
        raise ValueError(
            "The stored registration reference differs from FrozenRegistration "
            f"{stored_hash!r}."
        )
    return reference


@dataclass(frozen=True)
class MaterialIdentificationEvidenceReference:
    evidence_id: str
    record_type: str
    content_hash: str
    source_identities: MaterialIdentificationSourceIdentities

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _text(self.evidence_id, "evidence_id"))
        record_type = _text(self.record_type, "record_type")
        if record_type not in EVIDENCE_RECORD_TYPES:
            raise ValueError(f"Unsupported evidence record type {record_type!r}.")
        object.__setattr__(self, "record_type", record_type)
        content_hash = _text(self.content_hash, "content_hash").lower()
        if len(content_hash) != 64 or any(
            character not in "0123456789abcdef" for character in content_hash
        ):
            raise ValueError("content_hash must be a lowercase SHA-256 digest.")
        object.__setattr__(self, "content_hash", content_hash)
        if not isinstance(
            self.source_identities, MaterialIdentificationSourceIdentities
        ):
            raise TypeError(
                "source_identities must be MaterialIdentificationSourceIdentities."
            )

    @classmethod
    def from_evidence(
        cls,
        evidence: EvidenceRecord,
        source_identities: MaterialIdentificationSourceIdentities,
    ) -> "MaterialIdentificationEvidenceReference":
        if not isinstance(evidence, EvidenceRecord):
            raise TypeError("evidence must be an EvidenceRecord.")
        return cls(
            evidence_id=evidence.evidence_id,
            record_type=evidence.RECORD_TYPE,
            content_hash=evidence.content_hash,
            source_identities=source_identities,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "record_type": self.record_type,
            "content_hash": self.content_hash,
            "source_identities": self.source_identities.to_dict(),
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, object]
    ) -> "MaterialIdentificationEvidenceReference":
        if not isinstance(payload, Mapping):
            raise TypeError("evidence reference must be a mapping.")
        return cls(
            evidence_id=payload["evidence_id"],
            record_type=payload["record_type"],
            content_hash=payload["content_hash"],
            source_identities=MaterialIdentificationSourceIdentities.from_dict(
                payload["source_identities"]
            ),
        )


@dataclass(frozen=True)
class SessionReadiness:
    ready: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class MaterialIdentificationSession:
    """One identification session with two independent bindings.

    ``task_definition`` binds the identification model (id + definition hash);
    ``registration_reference`` binds the exact FrozenRegistration (hash,
    experimental content identity, FE geometry identity v2).  A session
    without a registration may exist but is never production-ready.
    """

    schema_version: str
    session_id: str
    created_at: datetime
    task_definition: MaterialIdentificationTaskDefinition
    source_identities: MaterialIdentificationSourceIdentities
    registration_reference: FrozenRegistrationReference | None = None
    evidence_references: tuple[MaterialIdentificationEvidenceReference, ...] = ()

    # 3.0: the session binds a FrozenRegistration; source identities are
    # descriptive labels only (no duplicate experiment/FE/calibration identity).
    SCHEMA_VERSION: ClassVar[str] = "material-identification-session/3.0"
    _UNSUPPORTED_SCHEMAS: ClassVar[Mapping[str, str]] = {
        "material-identification-session/1.0": (
            "schema 1.0 hard-coded the Ex/Ey/Gxy parameter set and cannot be "
            "reinterpreted as a model-referenced session; recreate the session "
            "against an IdentificationModelDefinition."
        ),
        "material-identification-session/2.0": (
            "schema 2.0 has no FrozenRegistration binding and stored experiment, FE "
            "model, and calibration identities that the registration now owns; "
            "recreate the session with its FrozenRegistration."
        ),
    }

    def __post_init__(self) -> None:
        schema = _text(self.schema_version, "schema_version")
        if schema in self._UNSUPPORTED_SCHEMAS:
            raise ValueError(
                f"Unsupported session {schema!r}: {self._UNSUPPORTED_SCHEMAS[schema]}"
            )
        if schema != self.SCHEMA_VERSION:
            raise ValueError(f"MaterialIdentificationSession requires {self.SCHEMA_VERSION!r}.")
        object.__setattr__(self, "schema_version", schema)
        object.__setattr__(self, "session_id", _text(self.session_id, "session_id"))
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime.")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must include a timezone.")
        object.__setattr__(self, "created_at", self.created_at.astimezone(timezone.utc))
        if not isinstance(self.task_definition, MaterialIdentificationTaskDefinition):
            raise TypeError("task_definition must be MaterialIdentificationTaskDefinition.")
        if not isinstance(
            self.source_identities, MaterialIdentificationSourceIdentities
        ):
            raise TypeError(
                "source_identities must be MaterialIdentificationSourceIdentities."
            )
        if self.registration_reference is not None and not isinstance(
            self.registration_reference, FrozenRegistrationReference
        ):
            raise TypeError(
                "registration_reference must be a FrozenRegistrationReference or None."
            )
        references = tuple(self.evidence_references)
        if not all(
            isinstance(item, MaterialIdentificationEvidenceReference)
            for item in references
        ):
            raise TypeError(
                "evidence_references must contain MaterialIdentificationEvidenceReference records."
            )
        record_types = tuple(item.record_type for item in references)
        if len(record_types) != len(set(record_types)):
            raise ValueError("Only one evidence reference per record type is allowed.")
        for reference in references:
            if reference.source_identities != self.source_identities:
                raise ValueError(
                    f"Evidence {reference.evidence_id!r} source mismatch: its source "
                    "labels differ from the session."
                )
        object.__setattr__(self, "evidence_references", references)

    @classmethod
    def create(
        cls,
        *,
        task_definition: MaterialIdentificationTaskDefinition,
        source_identities: MaterialIdentificationSourceIdentities,
        registration: FrozenRegistration | None = None,
        evidence_references: tuple[MaterialIdentificationEvidenceReference, ...] = (),
        session_id: str | None = None,
        created_at: datetime | None = None,
    ) -> "MaterialIdentificationSession":
        return cls(
            schema_version=cls.SCHEMA_VERSION,
            session_id=session_id or str(uuid4()),
            created_at=created_at or datetime.now(timezone.utc),
            task_definition=task_definition,
            source_identities=source_identities,
            registration_reference=(
                None
                if registration is None
                else FrozenRegistrationReference.from_registration(registration)
            ),
            evidence_references=evidence_references,
        )

    def readiness(self) -> SessionReadiness:
        """Validate the configuration boundary without executing any service."""

        reasons = []
        task = self.task_definition
        try:
            # Re-derive the sealed hash so an altered in-memory model is caught.
            resolved = IdentificationModelDefinition.from_dict(task.model.to_dict())
        except (TypeError, ValueError) as error:
            resolved = None
            reasons.append(f"Identification model {task.identification_model_id!r} is invalid: {error}")
        if resolved is not None and resolved.definition_hash != task.identification_model_hash:
            reasons.append(
                f"Identification model {task.identification_model_id!r} does not match "
                "its definition hash."
            )
        for parameter_id in task.selected_parameter_ids:
            if parameter_id not in task.model.parameter_ids:
                reasons.append(
                    f"Selected parameter {parameter_id!r} is not defined by the model."
                )
            elif task.bounds_for(parameter_id) is None:
                reasons.append(f"Selected parameter {parameter_id!r} has no bounds.")
        # Every model parameter must be fitted or explicitly fixed; nothing is defaulted.
        accounted = set(task.selected_parameter_ids) | {
            parameter_id for parameter_id, _ in task.fixed_parameter_values
        }
        for parameter_id in task.model.parameter_ids:
            if parameter_id not in accounted:
                reasons.append(
                    f"Model parameter {parameter_id!r} is neither selected nor fixed."
                )
        registration = self.registration_reference
        if registration is None:
            reasons.append(
                "No FrozenRegistration is bound; a production session requires one."
            )
        else:
            if not _is_sha256(registration.registration_hash):
                reasons.append("The bound registration hash is not a SHA-256 digest.")
            if not _is_sha256(registration.experimental_source_identity.get("sha256")):
                reasons.append(
                    "The bound experimental source identity has no SHA-256 content identity."
                )
            if registration.fe_geometry_identity.get("schema_version") != FE_GEOMETRY_IDENTITY_V2:
                reasons.append(
                    f"The bound FE geometry identity is not {FE_GEOMETRY_IDENTITY_V2!r}."
                )
        for reference in self.evidence_references:
            if reference.source_identities != self.source_identities:
                reasons.append(
                    f"Evidence {reference.evidence_id!r} does not match session sources."
                )
        return SessionReadiness(ready=not reasons, reasons=tuple(reasons))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
            "task_definition": self.task_definition.to_dict(),
            "source_identities": self.source_identities.to_dict(),
            "registration": (
                None
                if self.registration_reference is None
                else self.registration_reference.to_dict()
            ),
            "evidence_references": [
                item.to_dict() for item in self.evidence_references
            ],
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
    def from_dict(
        cls,
        payload: Mapping[str, object],
        *,
        models: ModelCatalog,
        registrations: RegistrationCatalog = (),
    ) -> "MaterialIdentificationSession":
        """Restore a session against its exact model definition and registration."""
        if not isinstance(payload, Mapping):
            raise TypeError("session payload must be a mapping.")
        schema = payload.get("schema_version")
        if schema in cls._UNSUPPORTED_SCHEMAS:
            raise ValueError(
                f"Unsupported session {schema!r}: {cls._UNSUPPORTED_SCHEMAS[schema]}"
            )
        created_at = payload["created_at"]
        if not isinstance(created_at, str):
            raise TypeError("created_at must be an ISO-8601 string.")
        try:
            timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("created_at must be a valid ISO-8601 value.") from error
        stored_registration = payload["registration"]
        return cls(
            schema_version=payload["schema_version"],
            session_id=payload["session_id"],
            created_at=timestamp,
            task_definition=MaterialIdentificationTaskDefinition.from_dict(
                payload["task_definition"], models=models
            ),
            source_identities=MaterialIdentificationSourceIdentities.from_dict(
                payload["source_identities"]
            ),
            registration_reference=(
                None
                if stored_registration is None
                else resolve_registration_reference(stored_registration, registrations)
            ),
            evidence_references=tuple(
                MaterialIdentificationEvidenceReference.from_dict(item)
                for item in _sequence(
                    payload.get("evidence_references", ()), "evidence_references"
                )
            ),
        )

    @classmethod
    def from_json(
        cls,
        payload: str,
        *,
        models: ModelCatalog,
        registrations: RegistrationCatalog = (),
    ) -> "MaterialIdentificationSession":
        if not isinstance(payload, str):
            raise TypeError("JSON payload must be a string.")
        return cls.from_dict(json.loads(payload), models=models, registrations=registrations)


__all__ = [
    "FE_GEOMETRY_IDENTITY_V2",
    "FixedParameterValue",
    "FrozenRegistrationReference",
    "MaterialIdentificationEvidenceReference",
    "MaterialIdentificationSession",
    "MaterialIdentificationSourceIdentities",
    "MaterialIdentificationTaskDefinition",
    "ModelCatalog",
    "ParameterBounds",
    "RegistrationCatalog",
    "SCIENTIFIC_TASK_HASH_SCHEMA",
    "SessionReadiness",
    "resolve_identification_model",
    "resolve_registration_reference",
]
