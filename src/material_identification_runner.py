"""Execution-lifecycle boundary for material identification.

This module defines orchestration and calls only explicitly injected scientific
executors.  It contains no sensitivity mathematics, optimizer calls, inverse
integration, or Abaqus process integration.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
import json
from typing import ClassVar, Protocol
from uuid import uuid4

from domain.evidence import (
    EvidenceProvenance,
    EvidenceRecord,
    EvidenceScientificBinding,
    EvidenceSourceIdentity,
    IdentificationEvidence,
    IdentifiabilityEvidence,
    SensitivityEvidence,
    ValidationEvidence,
)
from domain.material_identification_session import (
    MaterialIdentificationEvidenceReference,
    MaterialIdentificationSession,
    MaterialIdentificationSourceIdentities,
    SessionReadiness,
)
from identifiability_evidence_adapter import identifiability_evidence_content
from identification_evidence_adapter import identification_evidence_content
from services.sensitivity_service import SensitivityResult
from services.identifiability_service import IdentifiabilityResult
from services.inverse_solver import InverseIdentificationResult


class MaterialIdentificationRunStatus(str, Enum):
    NOT_READY = "NOT_READY"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class MaterialIdentificationRunnerError(RuntimeError):
    """Base error for lifecycle and boundary validation failures."""


class MaterialIdentificationNotReadyError(MaterialIdentificationRunnerError):
    pass


class MaterialIdentificationSourceMismatchError(MaterialIdentificationRunnerError):
    pass


class MaterialIdentificationLifecycleError(MaterialIdentificationRunnerError):
    pass


class MaterialIdentificationSensitivityExecutionError(
    MaterialIdentificationRunnerError
):
    pass


class MaterialIdentificationMissingSensitivityError(
    MaterialIdentificationRunnerError
):
    pass


class MaterialIdentificationIdentifiabilityExecutionError(
    MaterialIdentificationRunnerError
):
    pass


class MaterialIdentificationMissingIdentifiabilityError(
    MaterialIdentificationRunnerError
):
    pass


class MaterialIdentificationIdentificationExecutionError(
    MaterialIdentificationRunnerError
):
    pass


class MaterialIdentificationEvidenceBindingError(MaterialIdentificationRunnerError):
    """Evidence does not scientifically belong to the current session.

    ``reason`` is one of ``"unbound"``, ``"model"``, ``"task"``, ``"registration"``,
    ``"experimental_content"`` (or ``"session_unbound"`` when the session itself
    has no registration to bind to).  Identification input checks use
    ``"sensitivity_unbound"``, ``"identifiability_unbound"``,
    ``"sensitivity_binding"``, ``"identifiability_binding"``,
    ``"input_binding_mismatch"``; a prebuilt output that does not derive from
    exactly the supplied inputs uses ``"parent_ids"``.  Identification results
    whose fitted parameters are not selected session parameters use
    ``"parameter_ids"``; fitted parameters that need more than one model unit
    use ``"mixed_units"``; a declared unit other than the model's uses
    ``"parameter_unit"``.
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def _scientific_binding_for_session(
    session: MaterialIdentificationSession,
) -> EvidenceScientificBinding:
    """The only source of a runner evidence binding: committed session state."""

    registration = session.registration_reference
    if registration is None:
        raise MaterialIdentificationEvidenceBindingError(
            "session_unbound",
            "The session has no FrozenRegistration, so evidence cannot be bound to it.",
        )
    task = session.task_definition
    return EvidenceScientificBinding.create(
        identification_model_id=task.identification_model_id,
        identification_model_hash=task.identification_model_hash,
        # Derived only from the committed task; never caller-supplied.
        identification_task_hash=task.scientific_task_hash,
        registration_hash=registration.registration_hash,
        experimental_content_sha256=registration.experimental_content_sha256,
    )


def _require_session_binding(
    record: EvidenceRecord, expected: EvidenceScientificBinding
) -> None:
    """Refuse evidence whose scientific binding is not exactly the session's.

    The record is only inspected, never rebound or reconstructed.
    """

    binding = record.scientific_binding
    label = f"{record.RECORD_TYPE} evidence {record.evidence_id!r}"
    if binding is None:
        raise MaterialIdentificationEvidenceBindingError(
            "unbound",
            f"{label} is UNBOUND; it cannot be attached to a production session.",
        )
    checks = (
        ("model", ("identification_model_id", "identification_model_hash"),
         "a different identification model definition"),
        ("task", ("identification_task_hash",),
         "a different scientific identification task (selection, bounds, fixed "
         "values, or weighting)"),
        ("registration", ("registration_hash",), "a different FrozenRegistration"),
        ("experimental_content", ("experimental_content_sha256",),
         "different experimental file content"),
    )
    for reason, fields, description in checks:
        if any(getattr(binding, name) != getattr(expected, name) for name in fields):
            raise MaterialIdentificationEvidenceBindingError(
                reason, f"{label} belongs to {description} than the current session."
            )
    if not record.scientifically_compatible_with(**expected.identity()):
        raise MaterialIdentificationEvidenceBindingError(
            "model", f"{label} is not scientifically compatible with the session."
        )


def _require_identification_inputs(
    sensitivity: SensitivityEvidence,
    identifiability: IdentifiabilityEvidence,
    expected: EvidenceScientificBinding,
) -> None:
    """Both precursors must be bound, to one binding, and that binding the session's."""

    for role, record in (("sensitivity", sensitivity), ("identifiability", identifiability)):
        if record.scientific_binding is None:
            raise MaterialIdentificationEvidenceBindingError(
                f"{role}_unbound",
                f"{role} input evidence {record.evidence_id!r} is UNBOUND; production "
                "identification requires evidence bound to the current session.",
            )
    if sensitivity.scientific_binding != identifiability.scientific_binding:
        raise MaterialIdentificationEvidenceBindingError(
            "input_binding_mismatch",
            "The sensitivity and identifiability inputs belong to different model, "
            "registration, or experiment bindings.",
        )
    for role, record in (("sensitivity", sensitivity), ("identifiability", identifiability)):
        try:
            _require_session_binding(record, expected)
        except MaterialIdentificationEvidenceBindingError as error:
            raise MaterialIdentificationEvidenceBindingError(
                f"{role}_binding", f"{role} input: {error}"
            ) from error


def _require_model_units(
    record: IdentificationEvidence, session: MaterialIdentificationSession
) -> None:
    """Fitted properties must be selected parameters declared in their model unit.

    Units come only from the session's model definition, per actually fitted
    parameter.  The current execution/evidence contract carries one scalar
    ``parameter_unit`` per entry, so fitted parameters needing two units are
    refused rather than mislabelled.  Entries without fitted properties need no
    unit.  The record is only inspected, never repaired.
    """

    identified = record.content.get("identified_properties")
    entries = identified.get("models") if isinstance(identified, Mapping) else None
    if not isinstance(entries, Mapping):
        return
    task = session.task_definition
    model = task.model
    label = f"identification evidence {record.evidence_id!r}"
    for name, entry in entries.items():
        if not isinstance(entry, Mapping) or "properties_MPa" not in entry:
            continue
        # "properties_MPa" is only the stored key name; it never states a unit.
        properties = entry["properties_MPa"]
        if not isinstance(properties, Mapping):
            raise MaterialIdentificationEvidenceBindingError(
                "parameter_ids",
                f"{label} entry {name!r} does not map parameter ids to fitted values.",
            )
        fitted = tuple(str(key) for key in properties)
        if not fitted:
            continue
        # Selected ids are validated against the model by the task definition.
        outside = [item for item in fitted if item not in task.selected_parameter_ids]
        if outside:
            raise MaterialIdentificationEvidenceBindingError(
                "parameter_ids",
                f"{label} entry {name!r} fits {outside}, which are not selected "
                f"parameters {list(task.selected_parameter_ids)} of model "
                f"{model.model_id!r}.",
            )
        units = sorted({model.parameter(item).unit for item in fitted})
        if len(units) != 1:
            raise MaterialIdentificationEvidenceBindingError(
                "mixed_units",
                f"{label} entry {name!r} fits parameters with model units {units}; the "
                "current identification execution/evidence contract has one scalar "
                "parameter_unit and cannot represent this result.",
            )
        declared = entry.get("parameter_unit")
        if declared != units[0]:
            raise MaterialIdentificationEvidenceBindingError(
                "parameter_unit",
                f"{label} entry {name!r} declares parameter_unit {declared!r}, but model "
                f"{model.model_id!r} defines {list(fitted)} in {units[0]!r}.",
            )


def _identification_parent_ids(
    sensitivity: SensitivityEvidence, identifiability: IdentifiabilityEvidence
) -> tuple[str, str]:
    """Canonical ancestry of an identification result (the runner's own order)."""
    return (sensitivity.evidence_id, identifiability.evidence_id)


def _text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty.")
    return normalized


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone.")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: object, name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be an ISO-8601 string or None.")
    try:
        return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")), name)
    except ValueError as error:
        raise ValueError(f"{name} must be a valid ISO-8601 timestamp.") from error


@dataclass(frozen=True)
class MaterialIdentificationEvidenceResults:
    """Typed output slots for scientific services that may be connected later."""

    sensitivity: SensitivityEvidence | None = None
    identifiability: IdentifiabilityEvidence | None = None
    identification: IdentificationEvidence | None = None
    validation: ValidationEvidence | None = None

    def __post_init__(self) -> None:
        expected = {
            "sensitivity": SensitivityEvidence,
            "identifiability": IdentifiabilityEvidence,
            "identification": IdentificationEvidence,
            "validation": ValidationEvidence,
        }
        for name, record_type in expected.items():
            value = getattr(self, name)
            if value is not None and not isinstance(value, record_type):
                raise TypeError(f"{name} must be {record_type.__name__} or None.")

    def records(self) -> tuple:
        return tuple(
            value
            for value in (
                self.sensitivity,
                self.identifiability,
                self.identification,
                self.validation,
            )
            if value is not None
        )


@dataclass(frozen=True)
class SensitivityExecutionOutput:
    """Application metadata accompanying an injected sensitivity result."""

    result: SensitivityResult
    source_identities: MaterialIdentificationSourceIdentities
    source_identity: EvidenceSourceIdentity
    provenance: EvidenceProvenance
    timestamp: datetime
    status: str = "COMPLETED"

    def __post_init__(self) -> None:
        if not isinstance(self.result, SensitivityResult):
            raise TypeError("result must be a SensitivityResult.")
        if not isinstance(
            self.source_identities, MaterialIdentificationSourceIdentities
        ):
            raise TypeError(
                "source_identities must be MaterialIdentificationSourceIdentities."
            )
        if not isinstance(self.source_identity, EvidenceSourceIdentity):
            raise TypeError("source_identity must be an EvidenceSourceIdentity.")
        if not isinstance(self.provenance, EvidenceProvenance):
            raise TypeError("provenance must be an EvidenceProvenance.")
        object.__setattr__(self, "timestamp", _utc(self.timestamp, "timestamp"))
        object.__setattr__(self, "status", _text(self.status, "status").upper())


@dataclass(frozen=True)
class IdentifiabilityExecutionOutput:
    """Application metadata accompanying an injected identifiability result."""

    result: IdentifiabilityResult
    model_id: str
    source_identities: MaterialIdentificationSourceIdentities
    source_identity: EvidenceSourceIdentity
    provenance: EvidenceProvenance
    timestamp: datetime
    status: str

    def __post_init__(self) -> None:
        if not isinstance(self.result, IdentifiabilityResult):
            raise TypeError("result must be an IdentifiabilityResult.")
        object.__setattr__(self, "model_id", _text(self.model_id, "model_id"))
        if not isinstance(
            self.source_identities, MaterialIdentificationSourceIdentities
        ):
            raise TypeError(
                "source_identities must be MaterialIdentificationSourceIdentities."
            )
        if not isinstance(self.source_identity, EvidenceSourceIdentity):
            raise TypeError("source_identity must be an EvidenceSourceIdentity.")
        if not isinstance(self.provenance, EvidenceProvenance):
            raise TypeError("provenance must be an EvidenceProvenance.")
        object.__setattr__(self, "timestamp", _utc(self.timestamp, "timestamp"))
        object.__setattr__(self, "status", _text(self.status, "status").upper())


@dataclass(frozen=True)
class IdentificationExecutionOutput:
    """Application metadata accompanying an injected inverse result."""

    result: InverseIdentificationResult
    model_id: str
    source_identities: MaterialIdentificationSourceIdentities
    source_identity: EvidenceSourceIdentity
    provenance: EvidenceProvenance
    timestamp: datetime
    status: str
    parameter_unit: str = "MPa"
    uncertainty: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.result, InverseIdentificationResult):
            raise TypeError("result must be an InverseIdentificationResult.")
        object.__setattr__(self, "model_id", _text(self.model_id, "model_id"))
        if not isinstance(
            self.source_identities, MaterialIdentificationSourceIdentities
        ):
            raise TypeError(
                "source_identities must be MaterialIdentificationSourceIdentities."
            )
        if not isinstance(self.source_identity, EvidenceSourceIdentity):
            raise TypeError("source_identity must be an EvidenceSourceIdentity.")
        if not isinstance(self.provenance, EvidenceProvenance):
            raise TypeError("provenance must be an EvidenceProvenance.")
        object.__setattr__(self, "timestamp", _utc(self.timestamp, "timestamp"))
        object.__setattr__(self, "status", _text(self.status, "status").upper())
        object.__setattr__(
            self, "parameter_unit", _text(self.parameter_unit, "parameter_unit")
        )
        if not isinstance(self.uncertainty, Mapping):
            raise TypeError("uncertainty must be a mapping.")
        object.__setattr__(self, "uncertainty", dict(self.uncertainty))


class IdentificationExecutor(Protocol):
    """Injected identification boundary used by the lifecycle runner.

    Live executors return ``IdentificationExecutionOutput`` for adaptation by
    the runner.  Read-only adapters for an already frozen result may return its
    complete ``IdentificationEvidence`` envelope directly so no inverse result
    has to be reconstructed or recalculated.
    """

    def __call__(
        self,
        session: MaterialIdentificationSession,
        sensitivity: SensitivityEvidence,
        identifiability: IdentifiabilityEvidence,
    ) -> IdentificationExecutionOutput | IdentificationEvidence: ...


@dataclass(frozen=True)
class MaterialIdentificationRunRecord:
    schema_version: str
    session_id: str
    run_id: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    status: MaterialIdentificationRunStatus
    errors: tuple[str, ...] = ()
    evidence_references: tuple[MaterialIdentificationEvidenceReference, ...] = ()

    SCHEMA_VERSION: ClassVar[str] = "material-identification-run/1.0"

    def __post_init__(self) -> None:
        schema_version = _text(self.schema_version, "schema_version")
        if schema_version != self.SCHEMA_VERSION:
            raise ValueError(
                f"MaterialIdentificationRunRecord requires {self.SCHEMA_VERSION!r}."
            )
        object.__setattr__(self, "schema_version", schema_version)
        object.__setattr__(self, "session_id", _text(self.session_id, "session_id"))
        object.__setattr__(self, "run_id", _text(self.run_id, "run_id"))
        object.__setattr__(self, "created_at", _utc(self.created_at, "created_at"))
        if self.started_at is not None:
            object.__setattr__(self, "started_at", _utc(self.started_at, "started_at"))
        if self.finished_at is not None:
            object.__setattr__(self, "finished_at", _utc(self.finished_at, "finished_at"))
        if not isinstance(self.status, MaterialIdentificationRunStatus):
            raise TypeError("status must be a MaterialIdentificationRunStatus.")
        errors = tuple(_text(item, "run error") for item in self.errors)
        references = tuple(self.evidence_references)
        if not all(
            isinstance(item, MaterialIdentificationEvidenceReference)
            for item in references
        ):
            raise TypeError(
                "evidence_references must contain MaterialIdentificationEvidenceReference records."
            )
        if self.status == MaterialIdentificationRunStatus.RUNNING:
            if self.started_at is None or self.finished_at is not None:
                raise ValueError("RUNNING requires started_at and no finished_at.")
        elif self.status in {
            MaterialIdentificationRunStatus.COMPLETED,
            MaterialIdentificationRunStatus.FAILED,
        }:
            if self.started_at is None or self.finished_at is None:
                raise ValueError(f"{self.status.value} requires start and finish timestamps.")
        elif self.started_at is not None or self.finished_at is not None:
            raise ValueError(f"{self.status.value} must not have lifecycle timestamps.")
        if self.status == MaterialIdentificationRunStatus.FAILED and not errors:
            raise ValueError("FAILED requires at least one error.")
        if self.status != MaterialIdentificationRunStatus.FAILED and errors:
            if self.status != MaterialIdentificationRunStatus.NOT_READY:
                raise ValueError("Only NOT_READY or FAILED may store errors.")
        if references and self.status != MaterialIdentificationRunStatus.COMPLETED:
            raise ValueError("Evidence references may only be stored for COMPLETED runs.")
        object.__setattr__(self, "errors", errors)
        object.__setattr__(self, "evidence_references", references)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "created_at": _timestamp(self.created_at),
            "started_at": _timestamp(self.started_at),
            "finished_at": _timestamp(self.finished_at),
            "status": self.status.value,
            "errors": list(self.errors),
            "evidence_references": [item.to_dict() for item in self.evidence_references],
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
        cls, payload: Mapping[str, object]
    ) -> "MaterialIdentificationRunRecord":
        if not isinstance(payload, Mapping):
            raise TypeError("run payload must be a mapping.")
        errors = payload.get("errors", ())
        references = payload.get("evidence_references", ())
        if isinstance(errors, (str, bytes)) or not isinstance(errors, Sequence):
            raise TypeError("errors must be a sequence.")
        if isinstance(references, (str, bytes)) or not isinstance(references, Sequence):
            raise TypeError("evidence_references must be a sequence.")
        return cls(
            schema_version=payload["schema_version"],
            session_id=payload["session_id"],
            run_id=payload["run_id"],
            created_at=_parse_timestamp(payload["created_at"], "created_at"),
            started_at=_parse_timestamp(payload.get("started_at"), "started_at"),
            finished_at=_parse_timestamp(payload.get("finished_at"), "finished_at"),
            status=MaterialIdentificationRunStatus(payload["status"]),
            errors=tuple(errors),
            evidence_references=tuple(
                MaterialIdentificationEvidenceReference.from_dict(item)
                for item in references
            ),
        )

    @classmethod
    def from_json(cls, payload: str) -> "MaterialIdentificationRunRecord":
        if not isinstance(payload, str):
            raise TypeError("JSON payload must be a string.")
        return cls.from_dict(json.loads(payload))


@dataclass(frozen=True)
class MaterialIdentificationRunResult:
    run: MaterialIdentificationRunRecord
    evidence: MaterialIdentificationEvidenceResults


def _array_values(value: object, name: str) -> tuple:
    if not hasattr(value, "tolist"):
        raise TypeError(f"SensitivityResult.{name} must provide tolist().")
    converted = value.tolist()
    if not isinstance(converted, list):
        raise TypeError(f"SensitivityResult.{name} must be an array.")
    return tuple(
        tuple(item) if isinstance(item, list) else item for item in converted
    )


def _sensitivity_evidence_content(
    session: MaterialIdentificationSession,
    result: SensitivityResult,
) -> dict[str, object]:
    """Serialize a service result without recomputing or changing its values."""

    observation_ids = tuple(str(item) for item in result.observation_ids)
    parameter_ids = tuple(str(item) for item in result.parameter_ids)
    selected = tuple(session.task_definition.selected_parameter_ids)
    if set(parameter_ids) != set(selected) or len(parameter_ids) != len(selected):
        raise ValueError(
            "Sensitivity service parameter IDs must match the session selection."
        )
    scaled = _array_values(result.scaled_sensitivity, "scaled_sensitivity")
    raw = _array_values(result.raw_derivatives, "raw_derivatives")
    frequencies = _array_values(result.frequencies_hz, "frequencies_hz")
    if len(scaled) != len(observation_ids) or len(raw) != len(observation_ids):
        raise ValueError(
            "Sensitivity service matrix rows must match observation IDs."
        )
    if len(frequencies) != len(observation_ids):
        raise ValueError(
            "Sensitivity service frequencies must match observation IDs."
        )
    parameter_indexes = {
        parameter_id: index for index, parameter_id in enumerate(parameter_ids)
    }
    gui_columns = {"Ex": "face_Ex", "Ey": "face_Ey", "Gxy": "face_Gxy"}
    raw_sensitivity_matrix = []
    for row_index, observation_id in enumerate(observation_ids):
        row = scaled[row_index]
        if not isinstance(row, tuple) or len(row) != len(parameter_ids):
            raise ValueError(
                "Sensitivity service matrix columns must match parameter IDs."
            )
        serialized_row: dict[str, object] = {
            "observable": observation_id,
            "baseline_frequency_hz": frequencies[row_index],
        }
        for parameter_id, column_name in gui_columns.items():
            if parameter_id in parameter_indexes:
                serialized_row[column_name] = row[parameter_indexes[parameter_id]]
        raw_sensitivity_matrix.append(serialized_row)

    coordinates = tuple(
        {
            "parameter_id": item.parameter_id,
            "derivative_coordinate": item.derivative_coordinate,
            "scale": item.scale,
            "scaling": item.scaling,
        }
        for item in result.parameter_coordinates
    )
    excluded = tuple(
        {"observation_id": item.observation_id, "status": item.status}
        for item in result.excluded_cluster_observations
    )
    validation = None
    if result.derivative_validation is not None:
        item = result.derivative_validation
        validation = {
            "relative_steps": tuple(item.relative_steps),
            "parameter_step_sizes": _array_values(
                item.parameter_step_sizes, "derivative_validation.parameter_step_sizes"
            ),
            "worst_relative_errors": _array_values(
                item.worst_relative_errors, "derivative_validation.worst_relative_errors"
            ),
            "worst_relative_error": item.worst_relative_error,
            "consistent": item.consistent,
            "method": item.method,
        }
    coordinate_system = getattr(result.coordinate_system, "value", result.coordinate_system)
    return {
        "raw_sensitivity_matrix": tuple(raw_sensitivity_matrix),
        "observation_ids": observation_ids,
        "parameter_ids": parameter_ids,
        "raw_derivatives": raw,
        "scaled_sensitivity": scaled,
        "frequencies_hz": frequencies,
        "parameter_coordinates": coordinates,
        "excluded_cluster_observations": excluded,
        "derivative_validation": validation,
        "coordinate_system": str(coordinate_system),
    }


class MaterialIdentificationRunner:
    """Stateful orchestration boundary around explicitly injected executors."""

    def __init__(
        self,
        session: MaterialIdentificationSession,
        *,
        run_id: str | None = None,
        clock: Callable[[], datetime] | None = None,
        sensitivity_executor: Callable[
            [MaterialIdentificationSession], SensitivityExecutionOutput
        ]
        | None = None,
        identifiability_executor: Callable[
            [MaterialIdentificationSession, SensitivityEvidence],
            IdentifiabilityExecutionOutput,
        ]
        | None = None,
        identification_executor: IdentificationExecutor | None = None,
    ) -> None:
        if not isinstance(session, MaterialIdentificationSession):
            raise TypeError("session must be a MaterialIdentificationSession.")
        self._session = session
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        if sensitivity_executor is not None and not callable(sensitivity_executor):
            raise TypeError("sensitivity_executor must be callable or None.")
        self._sensitivity_executor = sensitivity_executor
        if identifiability_executor is not None and not callable(
            identifiability_executor
        ):
            raise TypeError("identifiability_executor must be callable or None.")
        self._identifiability_executor = identifiability_executor
        if identification_executor is not None and not callable(
            identification_executor
        ):
            raise TypeError("identification_executor must be callable or None.")
        self._identification_executor = identification_executor
        self._record = MaterialIdentificationRunRecord(
            schema_version=MaterialIdentificationRunRecord.SCHEMA_VERSION,
            session_id=session.session_id,
            run_id=run_id or str(uuid4()),
            created_at=self._now(),
            started_at=None,
            finished_at=None,
            status=MaterialIdentificationRunStatus.NOT_READY,
        )

    @property
    def session(self) -> MaterialIdentificationSession:
        return self._session

    @property
    def record(self) -> MaterialIdentificationRunRecord:
        return self._record

    def _now(self) -> datetime:
        return _utc(self._clock(), "runner clock value")

    def _require_status(self, expected: MaterialIdentificationRunStatus) -> None:
        if self._record.status != expected:
            raise MaterialIdentificationLifecycleError(
                f"Expected run state {expected.value}, got {self._record.status.value}."
            )

    def _validate_references(
        self,
        references: tuple[MaterialIdentificationEvidenceReference, ...],
    ) -> None:
        seen = set()
        for reference in references:
            if not isinstance(reference, MaterialIdentificationEvidenceReference):
                raise TypeError(
                    "evidence references must be MaterialIdentificationEvidenceReference records."
                )
            if reference.source_identities != self._session.source_identities:
                raise MaterialIdentificationSourceMismatchError(
                    f"Evidence {reference.evidence_id!r} does not match session sources."
                )
            if reference.record_type in seen:
                raise ValueError("Only one evidence reference per record type is allowed.")
            seen.add(reference.record_type)

    def prepare(self) -> MaterialIdentificationRunRecord:
        self._require_status(MaterialIdentificationRunStatus.NOT_READY)
        readiness = self._session.readiness()
        if not isinstance(readiness, SessionReadiness):
            raise TypeError("session.readiness() must return SessionReadiness.")
        if not readiness.ready:
            errors = readiness.reasons or ("Session is not ready.",)
            self._record = replace(self._record, errors=errors)
            raise MaterialIdentificationNotReadyError("; ".join(errors))
        self._validate_references(self._session.evidence_references)
        self._record = replace(
            self._record,
            status=MaterialIdentificationRunStatus.READY,
            errors=(),
        )
        return self._record

    def start(self) -> MaterialIdentificationRunRecord:
        """Enter RUNNING state without invoking any execution backend."""

        self._require_status(MaterialIdentificationRunStatus.READY)
        self._record = replace(
            self._record,
            status=MaterialIdentificationRunStatus.RUNNING,
            started_at=self._now(),
        )
        return self._record

    def complete(
        self,
        *,
        evidence: MaterialIdentificationEvidenceResults | None = None,
        evidence_references: tuple[MaterialIdentificationEvidenceReference, ...] = (),
    ) -> MaterialIdentificationRunResult:
        """Record externally supplied outputs; perform no scientific execution."""

        self._require_status(MaterialIdentificationRunStatus.RUNNING)
        results = evidence or MaterialIdentificationEvidenceResults()
        if not isinstance(results, MaterialIdentificationEvidenceResults):
            raise TypeError("evidence must be MaterialIdentificationEvidenceResults.")
        references = tuple(evidence_references)
        self._validate_references(references)
        if results.records():
            # Scientific ownership is authoritative: every record must already
            # carry exactly this session's binding before it is referenced.
            expected = _scientific_binding_for_session(self._session)
            for record in results.records():
                _require_session_binding(record, expected)
            # Every accepted identification record, however it was produced.
            if results.identification is not None:
                _require_model_units(results.identification, self._session)
        reference_by_type = {item.record_type: item for item in references}
        for record in results.records():
            reference = reference_by_type.get(record.RECORD_TYPE)
            if reference is None:
                raise ValueError(
                    f"Typed {record.RECORD_TYPE} evidence requires a matching reference."
                )
            if (
                reference.evidence_id != record.evidence_id
                or reference.content_hash != record.content_hash
            ):
                raise ValueError(
                    f"Typed {record.RECORD_TYPE} evidence does not match its reference."
                )
        if set(reference_by_type) != {record.RECORD_TYPE for record in results.records()}:
            raise ValueError("Every evidence reference must have a typed evidence result.")
        self._record = replace(
            self._record,
            status=MaterialIdentificationRunStatus.COMPLETED,
            finished_at=self._now(),
            evidence_references=references,
        )
        return MaterialIdentificationRunResult(run=self._record, evidence=results)

    def run_sensitivity(self) -> MaterialIdentificationRunResult:
        """Run only the injected sensitivity executor and wrap its stored output."""

        if self._sensitivity_executor is None:
            raise MaterialIdentificationRunnerError(
                "No sensitivity executor is configured."
            )
        self.prepare()
        self.start()
        try:
            output = self._sensitivity_executor(self._session)
            if not isinstance(output, SensitivityExecutionOutput):
                raise TypeError(
                    "sensitivity_executor must return SensitivityExecutionOutput."
                )
            if output.source_identities != self._session.source_identities:
                raise MaterialIdentificationSourceMismatchError(
                    "Sensitivity output does not match session sources."
                )
            content = _sensitivity_evidence_content(self._session, output.result)
            evidence = SensitivityEvidence.create(
                evidence_id=f"{self._record.run_id}-sensitivity",
                timestamp=output.timestamp,
                source_identity=output.source_identity,
                provenance=output.provenance,
                status=output.status,
                content=content,
                scientific_binding=_scientific_binding_for_session(self._session),
            )
            reference = MaterialIdentificationEvidenceReference.from_evidence(
                evidence, output.source_identities
            )
            return self.complete(
                evidence=MaterialIdentificationEvidenceResults(
                    sensitivity=evidence
                ),
                evidence_references=(reference,),
            )
        except (
            MaterialIdentificationSourceMismatchError,
            MaterialIdentificationEvidenceBindingError,
        ) as error:
            self.fail(str(error))
            raise
        except Exception as error:
            message = str(error).strip() or type(error).__name__
            self.fail(message)
            raise MaterialIdentificationSensitivityExecutionError(message) from error

    def run_identifiability(
        self,
        sensitivity: SensitivityEvidence | None,
        sensitivity_reference: MaterialIdentificationEvidenceReference | None,
    ) -> MaterialIdentificationRunResult:
        """Run only the injected identifiability executor on typed sensitivity."""

        if self._identifiability_executor is None:
            raise MaterialIdentificationRunnerError(
                "No identifiability executor is configured."
            )
        self.prepare()
        if sensitivity is None or sensitivity_reference is None:
            raise MaterialIdentificationMissingSensitivityError(
                "Sensitivity evidence and its source-bound reference are required."
            )
        if not isinstance(sensitivity, SensitivityEvidence):
            raise TypeError("sensitivity must be SensitivityEvidence or None.")
        if not isinstance(
            sensitivity_reference, MaterialIdentificationEvidenceReference
        ):
            raise TypeError(
                "sensitivity_reference must be MaterialIdentificationEvidenceReference or None."
            )
        self._validate_references((sensitivity_reference,))
        if sensitivity_reference.record_type != SensitivityEvidence.RECORD_TYPE:
            raise ValueError("sensitivity_reference must reference sensitivity evidence.")
        if (
            sensitivity_reference.evidence_id != sensitivity.evidence_id
            or sensitivity_reference.content_hash != sensitivity.content_hash
        ):
            raise ValueError(
                "Sensitivity evidence does not match its source-bound reference."
            )
        self.start()
        try:
            output = self._identifiability_executor(self._session, sensitivity)
            if not isinstance(output, IdentifiabilityExecutionOutput):
                raise TypeError(
                    "identifiability_executor must return IdentifiabilityExecutionOutput."
                )
            if output.source_identities != self._session.source_identities:
                raise MaterialIdentificationSourceMismatchError(
                    "Identifiability output does not match session sources."
                )
            model = identifiability_evidence_content(
                output.result, output.model_id
            )
            evidence = IdentifiabilityEvidence.create(
                evidence_id=f"{self._record.run_id}-identifiability",
                timestamp=output.timestamp,
                source_identity=output.source_identity,
                provenance=output.provenance,
                status=output.status,
                parent_ids=(sensitivity.evidence_id,),
                content={"models": {output.model_id: model}},
                scientific_binding=_scientific_binding_for_session(self._session),
            )
            reference = MaterialIdentificationEvidenceReference.from_evidence(
                evidence, output.source_identities
            )
            return self.complete(
                evidence=MaterialIdentificationEvidenceResults(
                    identifiability=evidence
                ),
                evidence_references=(reference,),
            )
        except (
            MaterialIdentificationSourceMismatchError,
            MaterialIdentificationEvidenceBindingError,
        ) as error:
            self.fail(str(error))
            raise
        except Exception as error:
            message = str(error).strip() or type(error).__name__
            self.fail(message)
            raise MaterialIdentificationIdentifiabilityExecutionError(
                message
            ) from error

    def run_identification(
        self,
        sensitivity: SensitivityEvidence | None,
        sensitivity_reference: MaterialIdentificationEvidenceReference | None,
        identifiability: IdentifiabilityEvidence | None,
        identifiability_reference: MaterialIdentificationEvidenceReference | None,
    ) -> MaterialIdentificationRunResult:
        """Run only the injected identification executor on typed prerequisites."""

        if self._identification_executor is None:
            raise MaterialIdentificationRunnerError(
                "No identification executor is configured."
            )
        self.prepare()
        if sensitivity is None or sensitivity_reference is None:
            raise MaterialIdentificationMissingSensitivityError(
                "Sensitivity evidence and its source-bound reference are required."
            )
        if identifiability is None or identifiability_reference is None:
            raise MaterialIdentificationMissingIdentifiabilityError(
                "Identifiability evidence and its source-bound reference are required."
            )
        if not isinstance(sensitivity, SensitivityEvidence):
            raise TypeError("sensitivity must be SensitivityEvidence or None.")
        if not isinstance(identifiability, IdentifiabilityEvidence):
            raise TypeError("identifiability must be IdentifiabilityEvidence or None.")
        if not isinstance(
            sensitivity_reference, MaterialIdentificationEvidenceReference
        ):
            raise TypeError(
                "sensitivity_reference must be MaterialIdentificationEvidenceReference or None."
            )
        if not isinstance(
            identifiability_reference, MaterialIdentificationEvidenceReference
        ):
            raise TypeError(
                "identifiability_reference must be MaterialIdentificationEvidenceReference or None."
            )
        self._validate_references(
            (sensitivity_reference, identifiability_reference)
        )
        if sensitivity_reference.record_type != SensitivityEvidence.RECORD_TYPE:
            raise ValueError("sensitivity_reference must reference sensitivity evidence.")
        if (
            identifiability_reference.record_type
            != IdentifiabilityEvidence.RECORD_TYPE
        ):
            raise ValueError(
                "identifiability_reference must reference identifiability evidence."
            )
        if (
            sensitivity_reference.evidence_id != sensitivity.evidence_id
            or sensitivity_reference.content_hash != sensitivity.content_hash
        ):
            raise ValueError(
                "Sensitivity evidence does not match its source-bound reference."
            )
        if (
            identifiability_reference.evidence_id != identifiability.evidence_id
            or identifiability_reference.content_hash != identifiability.content_hash
        ):
            raise ValueError(
                "Identifiability evidence does not match its source-bound reference."
            )
        if sensitivity.evidence_id not in identifiability.parent_ids:
            raise ValueError(
                "Identifiability evidence is not derived from the supplied sensitivity evidence."
            )
        self.start()
        try:
            session_binding = _scientific_binding_for_session(self._session)
            # The precursors must belong to this session before anything runs.
            _require_identification_inputs(sensitivity, identifiability, session_binding)
            expected_parents = _identification_parent_ids(sensitivity, identifiability)
            output = self._identification_executor(
                self._session, sensitivity, identifiability
            )
            if isinstance(output, IdentificationEvidence):
                # Prebuilt evidence is accepted as-is only if it already carries
                # exactly this session's binding and derives from exactly the
                # supplied inputs; it is never rebound or re-parented.
                _require_session_binding(output, session_binding)
                if output.parent_ids != expected_parents:
                    raise MaterialIdentificationEvidenceBindingError(
                        "parent_ids",
                        f"identification evidence {output.evidence_id!r} has parent_ids "
                        f"{output.parent_ids}, not the supplied inputs {expected_parents}.",
                    )
                evidence = output
            elif isinstance(output, IdentificationExecutionOutput):
                if output.source_identities != self._session.source_identities:
                    raise MaterialIdentificationSourceMismatchError(
                        "Identification output does not match session sources."
                    )
                if (
                    output.result.identifiability_metadata_reference is not None
                    and output.result.identifiability_metadata_reference
                    != identifiability.evidence_id
                ):
                    raise ValueError(
                        "Identification output does not reference the supplied "
                        "identifiability evidence."
                    )
                content = identification_evidence_content(
                    output.result,
                    model_id=output.model_id,
                    parameter_unit=output.parameter_unit,
                    uncertainty=output.uncertainty,
                )
                evidence = IdentificationEvidence.create(
                    evidence_id=f"{self._record.run_id}-identification",
                    timestamp=output.timestamp,
                    source_identity=output.source_identity,
                    provenance=output.provenance,
                    status=output.status,
                    parent_ids=expected_parents,
                    content=content,
                    scientific_binding=session_binding,
                )
            else:
                raise TypeError(
                    "identification_executor must return IdentificationExecutionOutput "
                    "or IdentificationEvidence."
                )
            reference = MaterialIdentificationEvidenceReference.from_evidence(
                evidence, self._session.source_identities
            )
            return self.complete(
                evidence=MaterialIdentificationEvidenceResults(
                    identification=evidence
                ),
                evidence_references=(reference,),
            )
        except (
            MaterialIdentificationSourceMismatchError,
            MaterialIdentificationEvidenceBindingError,
        ) as error:
            self.fail(str(error))
            raise
        except Exception as error:
            message = str(error).strip() or type(error).__name__
            self.fail(message)
            raise MaterialIdentificationIdentificationExecutionError(
                message
            ) from error

    def fail(self, *errors: str) -> MaterialIdentificationRunRecord:
        self._require_status(MaterialIdentificationRunStatus.RUNNING)
        normalized = tuple(_text(item, "run error") for item in errors)
        if not normalized:
            raise ValueError("At least one failure error is required.")
        self._record = replace(
            self._record,
            status=MaterialIdentificationRunStatus.FAILED,
            finished_at=self._now(),
            errors=normalized,
        )
        return self._record


__all__ = [
    "MaterialIdentificationEvidenceResults",
    "MaterialIdentificationEvidenceBindingError",
    "IdentificationExecutionOutput",
    "IdentificationExecutor",
    "MaterialIdentificationIdentificationExecutionError",
    "IdentifiabilityExecutionOutput",
    "MaterialIdentificationIdentifiabilityExecutionError",
    "MaterialIdentificationLifecycleError",
    "MaterialIdentificationNotReadyError",
    "MaterialIdentificationMissingSensitivityError",
    "MaterialIdentificationMissingIdentifiabilityError",
    "MaterialIdentificationRunRecord",
    "MaterialIdentificationRunResult",
    "MaterialIdentificationRunner",
    "MaterialIdentificationRunnerError",
    "MaterialIdentificationRunStatus",
    "MaterialIdentificationSourceMismatchError",
    "MaterialIdentificationSensitivityExecutionError",
    "SensitivityExecutionOutput",
]
