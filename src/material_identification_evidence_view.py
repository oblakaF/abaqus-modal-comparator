"""Typed presentation adapter for Effective Material Identification evidence.

This module translates versioned evidence contracts into the existing GUI table
shapes.  It reads stored values only; it performs no scientific calculation.

Two presentation paths are kept apart:

* BOUND production evidence is rendered against its authoritative
  ``IdentificationModelDefinition`` (parameter ids, order, and units).  The
  definition is supplied explicitly and verified against each record's
  scientific binding; it is never reconstructed from the evidence.
* UNBOUND historical SP13 evidence (``from_bundle``) keeps the legacy layout of
  the frozen SP13 artifacts and needs no current model definition.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TypeVar

from domain.evidence import (
    EvidenceRecord,
    IdentificationEvidence,
    IdentifiabilityEvidence,
    SensitivityEvidence,
    ValidationEvidence,
)
from domain.identification_model import IdentificationModelDefinition
from sp13_evidence_adapter import SP13EvidenceBundle


# Legacy layout of the frozen historical SP13 artifacts (and of the empty view).
# These are artifact column names, not model metadata: BOUND evidence is always
# rendered from its IdentificationModelDefinition instead.
_HISTORICAL_PARAMETERS = ("Ex", "Ey", "Gxy")
_HISTORICAL_UNIT = "MPa"
_HISTORICAL_SENSITIVITY_COLUMNS = {
    "Ex": "face_Ex",
    "Ey": "face_Ey",
    "Gxy": "face_Gxy",
}


class InvalidEvidenceError(ValueError):
    """Raised when a typed envelope has an unsupported presentation payload."""


class EvidenceModelBindingError(InvalidEvidenceError):
    """Evidence cannot be presented against the supplied model definition.

    ``reason`` is one of ``"model_required"``, ``"model_id"``, ``"model_hash"``,
    ``"mixed_binding"``, ``"unbound_with_model"``, ``"parameter_ids"``, or
    ``"parameter_unit"``.
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


EvidenceType = TypeVar("EvidenceType", bound=EvidenceRecord)


def _typed_optional(value: object, expected: type[EvidenceType], name: str):
    if value is not None and not isinstance(value, expected):
        raise TypeError(f"{name} must be {expected.__name__} or None.")
    return value


def _mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise InvalidEvidenceError(f"{path} must be a mapping.")
    return value


def _rows(value: object, path: str) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise InvalidEvidenceError(f"{path} must be a sequence of mappings.")
    return tuple(_mapping(item, f"{path}[{index}]") for index, item in enumerate(value))


def _sequence(value: object, path: str) -> tuple:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise InvalidEvidenceError(f"{path} must be a sequence.")
    return tuple(value)


def _required(mapping: Mapping[str, object], key: str, path: str) -> object:
    if key not in mapping:
        raise InvalidEvidenceError(f"{path}.{key} is required.")
    return mapping[key]


def _stored_float(value: object, path: str) -> float:
    if isinstance(value, bool):
        raise InvalidEvidenceError(f"{path} must be a stored number, got {value!r}.")
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise InvalidEvidenceError(f"{path} must be a stored number, got {value!r}.") from error


def _number_text(value: object) -> str:
    if value is None or value == "":
        return "Unavailable"
    try:
        return f"{float(value):.6g}"
    except (TypeError, ValueError) as error:
        raise InvalidEvidenceError(f"Expected a stored numeric value, got {value!r}.") from error


def _status_text(value: object, *, default: str = "Not stated") -> str:
    text = str(value or "").strip()
    return text or default


def _weighting_label(value: object) -> str:
    normalized = _status_text(value, default="").upper()
    if normalized == "WEIGHTING_SENSITIVE":
        return "weighting-sensitive"
    if normalized in {"RELATIVELY_STABLE", "STABLE"}:
        return "relatively stable"
    return normalized or "Unavailable"


@dataclass(frozen=True)
class MaterialIdentificationEvidenceViewModel:
    """Application-facing typed evidence boundary used by the GUI.

    ``model`` is required for BOUND evidence and must be exactly the definition
    each record is bound to.  It must be omitted for UNBOUND historical
    evidence, which is presented through ``from_bundle``.
    """

    sensitivity: SensitivityEvidence | None = None
    identifiability: IdentifiabilityEvidence | None = None
    identification: IdentificationEvidence | None = None
    validation: ValidationEvidence | None = None
    model: IdentificationModelDefinition | None = None

    def __post_init__(self) -> None:
        _typed_optional(self.sensitivity, SensitivityEvidence, "sensitivity")
        _typed_optional(self.identifiability, IdentifiabilityEvidence, "identifiability")
        _typed_optional(self.identification, IdentificationEvidence, "identification")
        _typed_optional(self.validation, ValidationEvidence, "validation")
        if self.model is not None and not isinstance(
            self.model, IdentificationModelDefinition
        ):
            raise TypeError("model must be an IdentificationModelDefinition or None.")
        records = tuple(
            record
            for record in (
                self.sensitivity,
                self.identifiability,
                self.identification,
                self.validation,
            )
            if record is not None
        )
        bound = tuple(record for record in records if record.scientific_binding is not None)
        if bound and len(bound) != len(records):
            raise EvidenceModelBindingError(
                "mixed_binding",
                "BOUND production evidence and UNBOUND historical evidence cannot be "
                "presented in one view.",
            )
        if self.model is None:
            if bound:
                raise EvidenceModelBindingError(
                    "model_required",
                    f"{_label(bound[0])} is BOUND; presenting it requires the "
                    "IdentificationModelDefinition it is bound to.",
                )
            return
        if records and not bound:
            raise EvidenceModelBindingError(
                "unbound_with_model",
                "UNBOUND evidence cannot be verified against a model definition; "
                "present historical evidence through from_bundle().",
            )
        for record in bound:
            binding = record.scientific_binding
            if binding.identification_model_id != self.model.model_id:
                raise EvidenceModelBindingError(
                    "model_id",
                    f"{_label(record)} is bound to model "
                    f"{binding.identification_model_id!r}, not {self.model.model_id!r}.",
                )
            if binding.identification_model_hash != self.model.definition_hash:
                raise EvidenceModelBindingError(
                    "model_hash",
                    f"{_label(record)} is bound to a different definition of model "
                    f"{self.model.model_id!r} (definition hash mismatch).",
                )

    @classmethod
    def from_bundle(
        cls, bundle: SP13EvidenceBundle
    ) -> "MaterialIdentificationEvidenceViewModel":
        if not isinstance(bundle, SP13EvidenceBundle):
            raise TypeError("bundle must be an SP13EvidenceBundle.")
        return cls(
            sensitivity=bundle.sensitivity,
            identifiability=bundle.identifiability,
            identification=bundle.identification,
            validation=bundle.validation,
        )

    def _parameters(self) -> tuple[tuple[str, str], ...]:
        """(parameter id, unit) rows in presentation order."""

        if self.model is None:
            return tuple(
                (parameter, _HISTORICAL_UNIT) for parameter in _HISTORICAL_PARAMETERS
            )
        return tuple(
            (item.parameter_id, item.unit) for item in self.model.parameter_definitions
        )

    def _require_model_parameters(self, parameter_ids: Sequence[str], path: str) -> None:
        """BOUND content may only name parameters of its model definition."""

        if self.model is None:
            return
        unknown = [item for item in parameter_ids if item not in self.model.parameter_ids]
        if unknown:
            raise EvidenceModelBindingError(
                "parameter_ids",
                f"{path} names parameters {unknown} that model "
                f"{self.model.model_id!r} does not define.",
            )

    def _model_sensitivity_rows(
        self, content: Mapping[str, object]
    ) -> tuple[tuple[object, ...], ...]:
        path = "sensitivity.content"
        parameter_ids = tuple(
            str(item)
            for item in _sequence(_required(content, "parameter_ids", path), f"{path}.parameter_ids")
        )
        if len(set(parameter_ids)) != len(parameter_ids):
            raise InvalidEvidenceError(f"{path}.parameter_ids must be unique.")
        self._require_model_parameters(parameter_ids, f"{path}.parameter_ids")
        observation_ids = tuple(
            str(item)
            for item in _sequence(
                _required(content, "observation_ids", path), f"{path}.observation_ids"
            )
        )
        matrix = _sequence(
            _required(content, "scaled_sensitivity", path), f"{path}.scaled_sensitivity"
        )
        if len(matrix) != len(observation_ids):
            raise InvalidEvidenceError(
                f"{path}.scaled_sensitivity rows must match observation_ids."
            )
        # Columns follow the model's parameter order; parameters the evidence
        # does not contain are not invented.
        columns = tuple(
            parameter_ids.index(parameter)
            for parameter in self.model.parameter_ids
            if parameter in parameter_ids
        )
        rows = []
        for row_index, observation_id in enumerate(observation_ids):
            row_path = f"{path}.scaled_sensitivity[{row_index}]"
            row = _sequence(matrix[row_index], row_path)
            if len(row) != len(parameter_ids):
                raise InvalidEvidenceError(f"{row_path} must match parameter_ids.")
            rows.append(
                (
                    observation_id,
                    "Scalar mode",
                    *(_stored_float(row[index], row_path) for index in columns),
                )
            )
        return tuple(rows)

    def sensitivity_view(self) -> dict[str, object]:
        matrix_rows: tuple[tuple[object, ...], ...] = ()
        if self.sensitivity is not None and self.model is not None:
            matrix_rows = self._model_sensitivity_rows(self.sensitivity.content)
        elif self.sensitivity is not None:
            content = self.sensitivity.content
            raw_rows = _rows(
                _required(content, "raw_sensitivity_matrix", "sensitivity.content"),
                "sensitivity.content.raw_sensitivity_matrix",
            )
            matrix_rows = tuple(
                (
                    str(_required(row, "observable", "raw_sensitivity_matrix row")),
                    "Scalar mode",
                    *(
                        float(_required(row, column, "raw_sensitivity_matrix row"))
                        for column in _HISTORICAL_SENSITIVITY_COLUMNS.values()
                    ),
                )
                for row in raw_rows
            )

        parameters = tuple(parameter for parameter, _unit in self._parameters())
        observability = tuple((parameter, "unavailable") for parameter in parameters)
        summary = (
            ("Rank", "Unavailable"),
            ("Condition number", "Unavailable"),
            ("Singular values", "Unavailable"),
            ("Weakest direction", "Unavailable"),
        )
        if self.identifiability is not None:
            models = _mapping(
                _required(self.identifiability.content, "models", "identifiability.content"),
                "identifiability.content.models",
            )
            ordered_models = tuple(
                (name, _mapping(models[name], f"identifiability.content.models.{name}"))
                for name in ("U", "P")
                if name in models
            )
            if not ordered_models:
                raise InvalidEvidenceError(
                    "identifiability.content.models must contain U or P."
                )
            ranks = []
            conditions = []
            singular_summaries = []
            weakest_summaries = []
            observability_by_parameter = {}
            for name, model in ordered_models:
                parameter_order = tuple(
                    str(value)
                    for value in _required(model, "parameter_order", "identifiability model")
                )
                self._require_model_parameters(
                    parameter_order,
                    f"identifiability.content.models.{name}.parameter_order",
                )
                weakest = model.get("weakest_right_singular_vector")
                if weakest is not None:
                    weakest_values = tuple(weakest)
                    if len(parameter_order) != len(weakest_values):
                        raise InvalidEvidenceError(
                            "identifiability parameter_order and weakest vector lengths differ."
                        )
                    weakest_text = ", ".join(
                        f"{parameter} {float(value):+.3f}"
                        for parameter, value in zip(parameter_order, weakest_values)
                    )
                else:
                    directions = model.get("deficient_directions", ())
                    if not isinstance(directions, Sequence) or isinstance(
                        directions, (str, bytes)
                    ):
                        raise InvalidEvidenceError(
                            "identifiability deficient_directions must be a sequence."
                        )
                    if directions:
                        direction = _mapping(
                            directions[-1], "identifiability deficient direction"
                        )
                        loadings = _mapping(
                            _required(
                                direction,
                                "parameter_loadings",
                                "identifiability deficient direction",
                            ),
                            "identifiability deficient direction parameter_loadings",
                        )
                        weakest_text = ", ".join(
                            f"{parameter} {float(loadings[parameter]):+.3f}"
                            for parameter in parameter_order
                            if parameter in loadings
                        )
                    else:
                        weakest_text = "Unavailable"
                singular_values = tuple(
                    _required(model, "singular_values", "identifiability model")
                )
                ranks.append(f"{name}: {_required(model, 'numerical_rank', 'identifiability model')}")
                conditions.append(
                    f"{name}: {_number_text(_required(model, 'condition_number', 'identifiability model'))}"
                )
                singular_summaries.append(
                    f"{name}: {', '.join(_number_text(value) for value in singular_values)}"
                )
                weakest_summaries.append(
                    f"{name}: {weakest_text}"
                )
                stored_observability = model.get("parameter_observability", {})
                if isinstance(stored_observability, Mapping):
                    self._require_model_parameters(
                        tuple(str(key) for key in stored_observability),
                        f"identifiability.content.models.{name}.parameter_observability",
                    )
                    observability_by_parameter.update(stored_observability)
            status_labels = {
                "OBSERVABLE": "strong",
                "PARTIALLY_OBSERVABLE": "weak",
                "UNOBSERVABLE": "unavailable",
            }
            observability = tuple(
                (
                    parameter,
                    status_labels.get(
                        str(observability_by_parameter.get(parameter, "")).upper(),
                        "unavailable",
                    ),
                )
                for parameter in parameters
            )
            summary = (
                ("Rank", "; ".join(ranks)),
                ("Condition number", "; ".join(conditions)),
                ("Singular values", "; ".join(singular_summaries)),
                ("Weakest direction", "; ".join(weakest_summaries)),
            )
        return {
            "available": self.sensitivity is not None or self.identifiability is not None,
            "matrix": matrix_rows,
            "observability": observability,
            "identifiability": summary,
        }

    def identification_view(self) -> dict[str, object]:
        parameters = self._parameters()
        empty_rows = tuple((parameter, None, unit) for parameter, unit in parameters)
        if self.identification is None:
            return {
                "available": False,
                "model_u": empty_rows,
                "model_p": empty_rows,
                "comparison": tuple(
                    (parameter, None, "Unavailable") for parameter, _unit in parameters
                ),
                "status": "NO_IDENTIFICATION_RESULT",
            }

        identified = _mapping(
            _required(
                self.identification.content,
                "identified_properties",
                "identification.content",
            ),
            "identification.content.identified_properties",
        )
        models = _mapping(_required(identified, "models", "identified_properties"), "identified_properties.models")
        stability = _mapping(
            identified.get("stability", {}),
            "identified_properties.stability",
        )
        differences = _mapping(
            stability.get("U_P_symmetric_difference_percent", {}),
            "identified_properties.stability.U_P_symmetric_difference_percent",
        )
        self._require_model_parameters(
            tuple(str(key) for key in differences),
            "identified_properties.stability.U_P_symmetric_difference_percent",
        )

        def model_rows(model_name: str) -> tuple[tuple[object, ...], ...]:
            if model_name not in models:
                return empty_rows
            path = f"identified_properties.models.{model_name}"
            model = _mapping(models[model_name], path)
            # "properties_MPa" is the stored key name only; units always come
            # from the model definition (Stage A stores N·m under this key).
            properties = _mapping(
                _required(model, "properties_MPa", path),
                f"{path}.properties_MPa",
            )
            self._require_model_parameters(
                tuple(str(key) for key in properties), f"{path}.properties_MPa"
            )
            if self.model is not None and "parameter_unit" in model:
                stored_unit = model["parameter_unit"]
                for parameter, unit in parameters:
                    if parameter in properties and stored_unit != unit:
                        raise EvidenceModelBindingError(
                            "parameter_unit",
                            f"{path}.parameter_unit is {stored_unit!r}, but model "
                            f"{self.model.model_id!r} defines {parameter!r} in {unit!r}.",
                        )
            return tuple(
                (parameter, properties.get(parameter), unit)
                for parameter, unit in parameters
            )

        return {
            "available": True,
            "model_u": model_rows("U"),
            "model_p": model_rows("P"),
            "comparison": tuple(
                (
                    parameter,
                    differences.get(parameter),
                    _weighting_label(stability.get(parameter)),
                )
                for parameter, _unit in parameters
            ),
            "status": self.identification.status,
        }

    def validation_view(self) -> dict[str, object]:
        if self.validation is None:
            return {
                "available": False,
                "status": "NO_VALIDATION_EVIDENCE",
                "primary": (),
                "holdout": (),
            }
        rows = _rows(
            _required(self.validation.content, "validation_rows", "validation.content"),
            "validation.content.validation_rows",
        )

        def view_row(row: Mapping[str, object]) -> tuple[object, ...]:
            identity = _status_text(row.get("identity_status"), default="")
            comparison = _status_text(row.get("comparison_to_baseline"), default="")
            status = identity if "PASS" in identity or "DIAGNOSTIC" in identity else comparison
            return (
                _required(row, "model", "validation row"),
                _required(row, "observable", "validation row"),
                _required(row, "experimental_value", "validation row"),
                _required(row, "FE_value", "validation row"),
                _required(row, "equivalent_error_percent", "validation row"),
                status or "Not stated",
            )

        non_baseline = tuple(row for row in rows if str(row.get("model")) != "BASELINE")
        primary = tuple(view_row(row) for row in non_baseline if row.get("category") == "PRIMARY")
        holdout = tuple(
            view_row(row)
            for row in non_baseline
            if row.get("category") in {"HOLDOUT", "HOLDOUT_DIAGNOSTIC"}
        )
        return {
            "available": True,
            "status": self.validation.status,
            "primary": primary,
            "holdout": holdout,
        }


def _label(record: EvidenceRecord) -> str:
    return f"{record.RECORD_TYPE} evidence {record.evidence_id!r}"


EMPTY_EVIDENCE_VIEW_MODEL = MaterialIdentificationEvidenceViewModel()


__all__ = [
    "EMPTY_EVIDENCE_VIEW_MODEL",
    "EvidenceModelBindingError",
    "InvalidEvidenceError",
    "MaterialIdentificationEvidenceViewModel",
]
