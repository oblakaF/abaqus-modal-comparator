"""Data-only definitions of identification models (parameterizations).

An ``IdentificationModelDefinition`` says *what* is identified: parameter ids,
units, meanings, frozen assumptions, and limitations.  It never says *how*:
solvers and executors are injected elsewhere.  It is independent of any
specimen or data source, so one specimen may be identified with several models
and one model may be applied to many specimens.

``IdentificationParameterDefinition`` is the model-level meaning of a
parameter; it is distinct from ``parameter_model.IdentificationParameter``,
which is a campaign-level parameter instance with values and scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import numbers
import re
from typing import Any, ClassVar, Mapping


IDENTIFICATION_MODEL_SCHEMA = "identification-model/1"

_MODEL_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_PARAMETER_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ModelWorkflowStatus(str, Enum):
    PRODUCTION = "production"
    RESEARCH = "research"
    HISTORICAL = "historical"
    VALIDATION_ONLY = "validation_only"


def _text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty.")
    return normalized


def _identifier(value: object, name: str, pattern: re.Pattern) -> str:
    text = _text(value, name)
    if not pattern.fullmatch(text):
        raise ValueError(f"{name} {text!r} is not a valid identifier.")
    return text


def _texts(value: object, name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise TypeError(f"{name} must be a list or tuple of strings.")
    return tuple(_text(item, name) for item in value)


def _bounds(value: object) -> tuple[float, float] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise TypeError("default_bounds must be a (lower, upper) pair or None.")
    if len(value) != 2:
        raise ValueError("default_bounds must contain exactly two values.")
    numbers_ = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, numbers.Real):
            raise TypeError("default_bounds must contain real numbers.")
        number = float(item)
        if not math.isfinite(number):
            raise ValueError("default_bounds must be finite.")
        numbers_.append(number + 0.0)
    lower, upper = numbers_
    if lower >= upper:
        raise ValueError("default_bounds lower value must be less than upper value.")
    return lower, upper


@dataclass(frozen=True)
class IdentificationParameterDefinition:
    """Model-level meaning of one identified parameter."""

    parameter_id: str
    display_name: str
    unit: str
    meaning: str
    default_bounds: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        set_field = lambda name, value: object.__setattr__(self, name, value)
        set_field(
            "parameter_id",
            _identifier(self.parameter_id, "parameter_id", _PARAMETER_ID_PATTERN),
        )
        set_field("display_name", _text(self.display_name, "display_name"))
        set_field("unit", _text(self.unit, "unit"))
        set_field("meaning", _text(self.meaning, "meaning"))
        set_field("default_bounds", _bounds(self.default_bounds))

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter_id": self.parameter_id,
            "display_name": self.display_name,
            "unit": self.unit,
            "meaning": self.meaning,
            "default_bounds": None
            if self.default_bounds is None
            else list(self.default_bounds),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IdentificationParameterDefinition":
        if not isinstance(payload, Mapping):
            raise TypeError("parameter definition must be a mapping.")
        names = {"parameter_id", "display_name", "unit", "meaning", "default_bounds"}
        unknown = sorted(set(payload) - names)
        if unknown:
            raise ValueError(f"Unknown parameter definition fields: {unknown}.")
        return cls(
            parameter_id=payload["parameter_id"],
            display_name=payload["display_name"],
            unit=payload["unit"],
            meaning=payload["meaning"],
            default_bounds=payload.get("default_bounds"),
        )


def _normalized(
    *,
    model_id: object,
    display_name: object,
    parameter_definitions: object,
    frozen_assumptions: object,
    limitations: object,
    workflow_status: object,
) -> dict[str, Any]:
    if isinstance(parameter_definitions, (str, bytes)) or not isinstance(
        parameter_definitions, (list, tuple)
    ):
        raise TypeError("parameter_definitions must be a list or tuple.")
    parameters = tuple(parameter_definitions)
    if not parameters:
        raise ValueError("A model requires at least one parameter definition.")
    if not all(isinstance(item, IdentificationParameterDefinition) for item in parameters):
        raise TypeError(
            "parameter_definitions must contain IdentificationParameterDefinition records."
        )
    identifiers = [item.parameter_id for item in parameters]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Parameter ids must be unique within a model.")
    try:
        status = ModelWorkflowStatus(workflow_status)
    except ValueError as exc:
        allowed = [item.value for item in ModelWorkflowStatus]
        raise ValueError(f"workflow_status must be one of {allowed}.") from exc
    return {
        "model_id": _identifier(model_id, "model_id", _MODEL_ID_PATTERN),
        "display_name": _text(display_name, "display_name"),
        "parameter_definitions": parameters,
        "frozen_assumptions": _texts(frozen_assumptions, "frozen_assumptions"),
        "limitations": _texts(limitations, "limitations"),
        "workflow_status": status,
    }


def _content(schema_version: str, fields: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "model_id": fields["model_id"],
        "display_name": fields["display_name"],
        # Parameter order is the model's parameter-vector order and is hashed.
        "parameter_definitions": [item.to_dict() for item in fields["parameter_definitions"]],
        "frozen_assumptions": list(fields["frozen_assumptions"]),
        "limitations": list(fields["limitations"]),
        "workflow_status": fields["workflow_status"].value,
    }


def _hash(content: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        content, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class IdentificationModelDefinition:
    """Immutable, hash-sealed definition of what an identification estimates."""

    model_id: str
    display_name: str
    parameter_definitions: tuple[IdentificationParameterDefinition, ...]
    frozen_assumptions: tuple[str, ...]
    limitations: tuple[str, ...]
    workflow_status: ModelWorkflowStatus
    schema_version: str
    definition_hash: str

    FIELD_NAMES: ClassVar[tuple[str, ...]] = (
        "model_id",
        "display_name",
        "parameter_definitions",
        "frozen_assumptions",
        "limitations",
        "workflow_status",
        "schema_version",
        "definition_hash",
    )

    def __post_init__(self) -> None:
        if self.schema_version != IDENTIFICATION_MODEL_SCHEMA:
            raise ValueError(f"schema_version must be {IDENTIFICATION_MODEL_SCHEMA!r}.")
        fields = _normalized(
            **{name: getattr(self, name) for name in self.FIELD_NAMES[:-2]}
        )
        for name, value in fields.items():
            object.__setattr__(self, name, value)
        supplied = self.definition_hash
        if not isinstance(supplied, str) or not _HASH_PATTERN.fullmatch(supplied):
            raise ValueError("definition_hash must be a lowercase SHA-256 digest.")
        if supplied != _hash(_content(self.schema_version, fields)):
            raise ValueError("definition_hash does not match the model definition content.")

    @classmethod
    def create(cls, **fields: Any) -> "IdentificationModelDefinition":
        """Build a definition from its scientific fields and seal its hash."""
        content_names = cls.FIELD_NAMES[:-2]
        missing = [name for name in content_names if name not in fields]
        unknown = sorted(set(fields) - set(content_names))
        if missing or unknown:
            raise TypeError(f"Model definition fields: missing {missing}, unknown {unknown}.")
        normalized = _normalized(**fields)
        return cls(
            **normalized,
            schema_version=IDENTIFICATION_MODEL_SCHEMA,
            definition_hash=_hash(_content(IDENTIFICATION_MODEL_SCHEMA, normalized)),
        )

    @property
    def parameter_ids(self) -> tuple[str, ...]:
        return tuple(item.parameter_id for item in self.parameter_definitions)

    def parameter(self, parameter_id: str) -> IdentificationParameterDefinition:
        for item in self.parameter_definitions:
            if item.parameter_id == parameter_id:
                return item
        raise KeyError(f"Model {self.model_id!r} has no parameter {parameter_id!r}.")

    def to_dict(self) -> dict[str, Any]:
        fields = {name: getattr(self, name) for name in self.FIELD_NAMES[:-2]}
        return {
            **_content(self.schema_version, fields),
            "definition_hash": self.definition_hash,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IdentificationModelDefinition":
        """Restore a definition; the stored hash must match its content."""
        if not isinstance(payload, Mapping):
            raise TypeError("model definition payload must be a mapping.")
        missing = [name for name in cls.FIELD_NAMES if name not in payload]
        unknown = sorted(set(payload) - set(cls.FIELD_NAMES))
        if missing or unknown:
            raise ValueError(
                f"Invalid model definition payload: missing {missing}, unknown {unknown}."
            )
        parameters = payload["parameter_definitions"]
        if isinstance(parameters, (str, bytes)) or not isinstance(parameters, (list, tuple)):
            raise TypeError("parameter_definitions must be a list.")
        values = {name: payload[name] for name in cls.FIELD_NAMES}
        values["parameter_definitions"] = tuple(
            IdentificationParameterDefinition.from_dict(item) for item in parameters
        )
        return cls(**values)


def stage_a_bending_model() -> IdentificationModelDefinition:
    """Stage-A balanced plate-bending stiffness model (current production engine)."""

    return IdentificationModelDefinition.create(
        model_id="stage_a_bending",
        display_name="Stage A plate bending stiffness",
        parameter_definitions=(
            IdentificationParameterDefinition(
                parameter_id="D11",
                display_name="D11",
                unit="N·m",
                meaning="Principal bending stiffness; the balanced model sets D22 = D11.",
            ),
            IdentificationParameterDefinition(
                parameter_id="D12",
                display_name="D12",
                unit="N·m",
                meaning="Bending coupling stiffness, constrained to D12 = r·D11 with |r| < 1.",
            ),
            IdentificationParameterDefinition(
                parameter_id="D66",
                display_name="D66",
                unit="N·m",
                meaning="Twisting bending stiffness; must be positive.",
            ),
        ),
        frozen_assumptions=(
            "Balanced bending stiffness: D22 = D11.",
            "Stiffness is the documented affine approximation in (D11, D12, D66) "
            "about the reference matrices.",
            "Mass is the constant reference mass, or affine in D11 only when a mass "
            "derivative is supplied.",
        ),
        limitations=(
            "Derived E_flex, G12_flex and nu12_flex are apparent flexural properties "
            "derived from bending stiffness; they are not automatically equal to "
            "membrane properties.",
            "The affine stiffness approximation requires model-specific validation evidence.",
            "Final direct Abaqus verification of an identified point is required.",
        ),
        workflow_status=ModelWorkflowStatus.PRODUCTION,
    )


def effective_face_sheet_model() -> IdentificationModelDefinition:
    """Effective homogeneous face-sheet model.

    ``research`` status: no live, validated production inverse executor for
    this model exists yet.
    """

    return IdentificationModelDefinition.create(
        model_id="effective_face_sheet",
        display_name="Effective homogeneous face-sheet properties",
        parameter_definitions=(
            IdentificationParameterDefinition(
                parameter_id="Ex",
                display_name="Ex",
                unit="MPa",
                meaning="Effective homogeneous face-sheet modulus along X.",
            ),
            IdentificationParameterDefinition(
                parameter_id="Ey",
                display_name="Ey",
                unit="MPa",
                meaning="Effective homogeneous face-sheet modulus along Y.",
            ),
            IdentificationParameterDefinition(
                parameter_id="Gxy",
                display_name="Gxy",
                unit="MPa",
                meaning="Effective homogeneous face-sheet in-plane shear modulus.",
            ),
        ),
        frozen_assumptions=(
            "Core representation is frozen.",
            "Density representation is frozen.",
            "Adhesive representation is frozen.",
            "Geometry representation is frozen.",
        ),
        limitations=(
            "Effective homogeneous face-sheet properties; not true fibre properties, "
            "ply properties, or unique laminate constants.",
        ),
        workflow_status=ModelWorkflowStatus.RESEARCH,
    )


def effective_face_sheet_v2_model() -> IdentificationModelDefinition:
    """Effective orthotropic carbon face-sheet Engineering Constants (versioned).

    Successor of ``effective_face_sheet`` (Ex/Ey/Gxy), which stays unchanged
    for historical reproducibility.  The model says what *may* be identified;
    a campaign may fit a subset (for example E1, E2, G12 with nu12 held at a
    declared value).  ``research`` status: no live, validated executor exists.
    """

    return IdentificationModelDefinition.create(
        model_id="effective_face_sheet_v2",
        display_name=(
            "Effective orthotropic carbon face-sheet Engineering Constants for use "
            "in the calibrated sandwich FE model"
        ),
        parameter_definitions=(
            IdentificationParameterDefinition(
                parameter_id="E1",
                display_name="E1",
                unit="MPa",
                meaning="Effective face-sheet modulus along material axis 1 (longitudinal).",
            ),
            IdentificationParameterDefinition(
                parameter_id="E2",
                display_name="E2",
                unit="MPa",
                meaning="Effective face-sheet modulus along material axis 2 (transverse).",
            ),
            IdentificationParameterDefinition(
                parameter_id="G12",
                display_name="G12",
                unit="MPa",
                meaning="Effective face-sheet in-plane shear modulus.",
            ),
            IdentificationParameterDefinition(
                parameter_id="nu12",
                display_name="ν12",
                unit="1",
                meaning="Effective face-sheet major in-plane Poisson ratio.",
            ),
        ),
        frozen_assumptions=(
            "Material axes 1 and 2 follow the orientation declared in the calibrated "
            "sandwich FE model.",
            "Carbon face-sheet density is measured independently and fixed by the "
            "identification campaign.",
            "Face-sheet geometry and thickness are panel-specific inputs fixed by the "
            "identification campaign.",
            "Core geometry and core material are panel-specific inputs, initially fixed.",
            "The interface and adhesive representation is initially fixed.",
            "Transverse Engineering Constants (E3, nu13, nu23, G13, G23) are outside "
            "this model's identified parameter vector.",
        ),
        limitations=(
            "Identified values are effective face-sheet Engineering Constants within "
            "the calibrated sandwich FE model; they are not fibre properties, "
            "constituent properties, or coupon-certified lamina constants.",
            "nu12 may be weakly identifiable or non-identifiable from modal data; a "
            "campaign may fit E1, E2 and G12 while holding nu12 at a declared value.",
            "Final direct Abaqus verification of an identified point is required.",
        ),
        workflow_status=ModelWorkflowStatus.RESEARCH,
    )


STAGE_A_BENDING_MODEL = stage_a_bending_model()
EFFECTIVE_FACE_SHEET_MODEL = effective_face_sheet_model()
EFFECTIVE_FACE_SHEET_V2_MODEL = effective_face_sheet_v2_model()


__all__ = [
    "EFFECTIVE_FACE_SHEET_MODEL",
    "EFFECTIVE_FACE_SHEET_V2_MODEL",
    "IDENTIFICATION_MODEL_SCHEMA",
    "IdentificationModelDefinition",
    "IdentificationParameterDefinition",
    "ModelWorkflowStatus",
    "STAGE_A_BENDING_MODEL",
    "effective_face_sheet_model",
    "effective_face_sheet_v2_model",
    "stage_a_bending_model",
]
