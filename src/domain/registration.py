"""Frozen geometric registration between an experiment and FE geometry.

A registration binds the experimental source, the experimental modal set, and
the FE *geometry* (node identity, coordinates, DOF layout).  It deliberately
does not bind FE stiffness, material, or any other model parameter: an inverse
solver may change those while the registration stays valid.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import numbers
import re
from types import MappingProxyType
from typing import Any, ClassVar, Mapping


FROZEN_REGISTRATION_SCHEMA = "frozen-registration/1"
REGISTRATION_DOF_COMPONENTS = ("U1", "U2", "U3")

_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_IDENTITY_KEYS = ("path", "size", "mtime_ns")
_ROTATION_TOLERANCE = 1.0e-6


class RegistrationMismatchError(ValueError):
    """Current inputs do not match the inputs a registration was frozen for."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


def _freeze_json(value: object, path: str) -> Any:
    """Return an immutable copy of a JSON-safe value.

    Mappings become sorted read-only mappings and sequences become tuples.
    Anything that is not plain JSON data is rejected, never stringified.
    """
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{path} must not contain non-finite numbers.")
        return number
    if isinstance(value, Mapping):
        items = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} keys must be strings, not {type(key).__name__}.")
            items[key] = _freeze_json(item, f"{path}.{key}")
        return MappingProxyType(dict(sorted(items.items())))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item, f"{path}[{index}]") for index, item in enumerate(value))
    raise TypeError(f"{path} contains unsupported value type {type(value).__name__}.")


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        _thaw_json(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sequence(value: object, name: str) -> list:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{name} must be a sequence, not {type(value).__name__}.")
    return list(value)


def _float_vector(value: object, name: str, length: int) -> tuple[float, ...]:
    items = _sequence(value, name)
    if len(items) != length:
        raise ValueError(f"{name} must contain {length} values.")
    result = []
    for item in items:
        if isinstance(item, bool) or not isinstance(item, numbers.Real):
            raise TypeError(f"{name} must contain real numbers.")
        number = float(item)
        if not math.isfinite(number):
            raise ValueError(f"{name} must contain finite numbers.")
        result.append(number + 0.0)  # fold -0.0 into 0.0
    return tuple(result)


def _hash_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not _HASH_PATTERN.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 hexadecimal digest.")
    return value


def _identity_mapping(value: object, name: str) -> MappingProxyType:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping.")
    frozen = _freeze_json(value, name)
    if not frozen:
        raise ValueError(f"{name} must not be empty.")
    return frozen


def _source_identity(value: object) -> MappingProxyType:
    frozen = _identity_mapping(value, "experimental_source_identity")
    missing = [key for key in _SOURCE_IDENTITY_KEYS if key not in frozen]
    if missing:
        raise ValueError(f"experimental_source_identity is missing {missing}.")
    return frozen


def _geometry_identity(value: object) -> MappingProxyType:
    frozen = _identity_mapping(value, "fe_geometry_identity")
    schema = frozen.get("schema_version")
    if not isinstance(schema, str) or not schema.strip():
        raise ValueError("fe_geometry_identity must declare a schema_version.")
    _hash_text(frozen.get("sha256"), "fe_geometry_identity sha256")
    return frozen


def _calibration_fingerprint(calibration: Mapping[str, Any]) -> str:
    # Same canonical encoding as scientific_state.calibration_fingerprint.
    encoded = json.dumps(
        _thaw_json(calibration), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _rotation(value: object) -> tuple[tuple[float, ...], ...]:
    rows = _sequence(value, "rotation")
    if len(rows) != 3:
        raise ValueError("rotation must be a 3x3 matrix.")
    matrix = tuple(_float_vector(row, "rotation", 3) for row in rows)
    for i in range(3):
        for j in range(3):
            product = sum(matrix[i][k] * matrix[j][k] for k in range(3))
            if abs(product - (1.0 if i == j else 0.0)) > _ROTATION_TOLERANCE:
                raise ValueError("rotation must be orthonormal (proper or mirrored).")
    return matrix


def _experimental_node_ids(value: object) -> tuple[str | int, ...]:
    result = []
    for item in _sequence(value, "experimental_node_ids"):
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
        elif isinstance(item, numbers.Integral) and not isinstance(item, bool):
            result.append(int(item))
        else:
            raise TypeError("experimental_node_ids must be non-empty strings or integers.")
    if not result:
        raise ValueError("A registration requires at least one mapped node.")
    if len(set(result)) != len(result):
        raise ValueError("experimental_node_ids must be unique.")
    return tuple(result)


def _mapped_fe_node_ids(value: object) -> tuple[str, ...]:
    result = []
    for item in _sequence(value, "mapped_fe_node_ids"):
        if not isinstance(item, str) or not item.strip():
            raise TypeError("mapped_fe_node_ids must be non-empty strings.")
        result.append(item.strip())
    return tuple(result)


def _measured_dof_contract(value: object) -> tuple[tuple[bool, ...], ...]:
    if isinstance(value, Mapping):
        components = _sequence(value.get("components"), "measured_dof_contract components")
        if tuple(components) != REGISTRATION_DOF_COMPONENTS:
            raise ValueError(
                f"measured_dof_contract components must be {list(REGISTRATION_DOF_COMPONENTS)}."
            )
        value = value.get("mask")
    rows = []
    for row in _sequence(value, "measured_dof_contract"):
        items = _sequence(row, "measured_dof_contract row")
        if len(items) != len(REGISTRATION_DOF_COMPONENTS):
            raise ValueError("measured_dof_contract rows must have one flag per DOF component.")
        if not all(isinstance(item, bool) for item in items):
            raise TypeError("measured_dof_contract must contain booleans only.")
        rows.append(tuple(items))
    return tuple(rows)


@dataclass(frozen=True, eq=False)
class FrozenRegistration:
    """Immutable, hash-sealed experiment-to-FE-geometry registration."""

    experimental_source_identity: Mapping[str, Any]
    experimental_modal_set_identity: Any
    fe_geometry_identity: Mapping[str, Any]
    calibration: Mapping[str, Any]
    calibration_fingerprint: str
    orientation_candidate_id: str
    rotation: tuple[tuple[float, ...], ...]
    translation: tuple[float, ...]
    coordinate_scales: tuple[float, ...]
    experimental_node_ids: tuple[str | int, ...]
    mapped_fe_node_ids: tuple[str, ...]
    measured_dof_contract: tuple[tuple[bool, ...], ...]
    registration_metrics: Mapping[str, Any]
    registration_schema_version: str
    registration_hash: str

    FIELD_NAMES: ClassVar[tuple[str, ...]] = (
        "experimental_source_identity",
        "experimental_modal_set_identity",
        "fe_geometry_identity",
        "calibration",
        "calibration_fingerprint",
        "orientation_candidate_id",
        "rotation",
        "translation",
        "coordinate_scales",
        "experimental_node_ids",
        "mapped_fe_node_ids",
        "measured_dof_contract",
        "registration_metrics",
        "registration_schema_version",
        "registration_hash",
    )

    def __post_init__(self) -> None:
        if self.registration_schema_version != FROZEN_REGISTRATION_SCHEMA:
            raise ValueError(
                f"registration_schema_version must be {FROZEN_REGISTRATION_SCHEMA!r}."
            )
        self._normalize()
        supplied = _hash_text(self.registration_hash, "registration_hash")
        if supplied != self._compute_hash():
            raise ValueError("registration_hash does not match the registration content.")

    def _normalize(self) -> None:
        """Validate every scientific field and replace it with an immutable copy."""
        set_field = lambda name, value: object.__setattr__(self, name, value)
        set_field("experimental_source_identity", _source_identity(self.experimental_source_identity))
        set_field(
            "experimental_modal_set_identity",
            _freeze_json(self.experimental_modal_set_identity, "experimental_modal_set_identity"),
        )
        set_field("fe_geometry_identity", _geometry_identity(self.fe_geometry_identity))

        calibration = _identity_mapping(self.calibration, "calibration")
        fingerprint = _hash_text(self.calibration_fingerprint, "calibration_fingerprint")
        if fingerprint != _calibration_fingerprint(calibration):
            raise ValueError("calibration_fingerprint does not match calibration.")
        set_field("calibration", calibration)

        candidate_id = self.orientation_candidate_id
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            raise ValueError("orientation_candidate_id must be a non-empty string.")
        set_field("orientation_candidate_id", candidate_id.strip())
        set_field("rotation", _rotation(self.rotation))
        set_field("translation", _float_vector(self.translation, "translation", 3))
        scales = _float_vector(self.coordinate_scales, "coordinate_scales", 3)
        if any(scale <= 0.0 for scale in scales):
            raise ValueError("coordinate_scales must be positive.")
        set_field("coordinate_scales", scales)

        experimental = _experimental_node_ids(self.experimental_node_ids)
        mapped = _mapped_fe_node_ids(self.mapped_fe_node_ids)
        dofs = _measured_dof_contract(self.measured_dof_contract)
        if not (len(experimental) == len(mapped) == len(dofs)):
            raise ValueError(
                "experimental_node_ids, mapped_fe_node_ids, and measured_dof_contract "
                "must have one entry per mapped node."
            )
        set_field("experimental_node_ids", experimental)
        set_field("mapped_fe_node_ids", mapped)
        set_field("measured_dof_contract", dofs)

        if not isinstance(self.registration_metrics, Mapping):
            raise TypeError("registration_metrics must be a mapping.")
        set_field(
            "registration_metrics",
            _freeze_json(self.registration_metrics, "registration_metrics"),
        )

    @classmethod
    def create(cls, **fields: Any) -> "FrozenRegistration":
        """Build a registration from its scientific fields and seal its hash."""
        content_names = cls.FIELD_NAMES[:-2]
        missing = [name for name in content_names if name not in fields]
        unknown = sorted(set(fields) - set(content_names))
        if missing or unknown:
            raise TypeError(f"Registration fields: missing {missing}, unknown {unknown}.")
        unsealed = object.__new__(cls)
        for name in content_names:
            object.__setattr__(unsealed, name, fields[name])
        object.__setattr__(unsealed, "registration_schema_version", FROZEN_REGISTRATION_SCHEMA)
        unsealed._normalize()
        values = {name: getattr(unsealed, name) for name in cls.FIELD_NAMES[:-1]}
        return cls(**values, registration_hash=unsealed._compute_hash())

    def _content_dict(self) -> dict[str, Any]:
        return {
            "experimental_source_identity": _thaw_json(self.experimental_source_identity),
            "experimental_modal_set_identity": _thaw_json(self.experimental_modal_set_identity),
            "fe_geometry_identity": _thaw_json(self.fe_geometry_identity),
            "calibration": _thaw_json(self.calibration),
            "calibration_fingerprint": self.calibration_fingerprint,
            "orientation_candidate_id": self.orientation_candidate_id,
            "rotation": [list(row) for row in self.rotation],
            "translation": list(self.translation),
            "coordinate_scales": list(self.coordinate_scales),
            "experimental_node_ids": list(self.experimental_node_ids),
            "mapped_fe_node_ids": list(self.mapped_fe_node_ids),
            "measured_dof_contract": {
                "components": list(REGISTRATION_DOF_COMPONENTS),
                "mask": [list(row) for row in self.measured_dof_contract],
            },
            "registration_metrics": _thaw_json(self.registration_metrics),
            "registration_schema_version": self.registration_schema_version,
        }

    def _compute_hash(self) -> str:
        return hashlib.sha256(_canonical_bytes(self._content_dict())).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {**self._content_dict(), "registration_hash": self.registration_hash}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FrozenRegistration":
        """Restore a registration; the stored hash must match its content."""
        if not isinstance(payload, Mapping):
            raise TypeError("registration payload must be a mapping.")
        missing = [name for name in cls.FIELD_NAMES if name not in payload]
        unknown = sorted(set(payload) - set(cls.FIELD_NAMES))
        if missing or unknown:
            raise ValueError(
                f"Invalid registration payload: missing {missing}, unknown {unknown}."
            )
        _hash_text(payload["registration_hash"], "registration_hash")
        return cls(**{name: payload[name] for name in cls.FIELD_NAMES})

    def check_compatible(
        self,
        experimental_identity: object,
        fe_geometry_identity: object,
    ) -> bool:
        """Return True, or raise RegistrationMismatchError on any difference.

        Both identities must equal the frozen ones exactly after canonical
        encoding (key order is irrelevant; value types are not).
        """
        checks = (
            ("experimental_source_identity", experimental_identity, self.experimental_source_identity),
            ("fe_geometry_identity", fe_geometry_identity, self.fe_geometry_identity),
        )
        for field, supplied, frozen in checks:
            try:
                matches = isinstance(supplied, Mapping) and _canonical_bytes(
                    _freeze_json(supplied, field)
                ) == _canonical_bytes(frozen)
            except (TypeError, ValueError):
                matches = False
            if not matches:
                raise RegistrationMismatchError(
                    field, f"The registration is not valid for the current {field}."
                )
        return True

    def check_content_compatible(
        self,
        experimental_identity: object,
        fe_geometry_identity: object,
    ) -> bool:
        """Content-based compatibility: return True, or raise RegistrationMismatchError.

        The experimental source must have the frozen SHA-256 and size; its path and
        modification time are workstation details and are ignored.  The FE geometry
        identity must equal the frozen one exactly (it is already content-based).  A
        registration frozen without a content hash cannot be checked this way.
        """
        frozen = self.experimental_source_identity
        if not isinstance(frozen.get("sha256"), str):
            raise RegistrationMismatchError(
                "experimental_source_identity",
                "The registration records no content hash; only the legacy exact check applies.",
            )
        supplied = experimental_identity if isinstance(experimental_identity, Mapping) else {}
        if supplied.get("sha256") != frozen.get("sha256") or supplied.get("size") != frozen.get("size"):
            raise RegistrationMismatchError(
                "experimental_source_identity",
                "The registration is not valid for the current experimental source content.",
            )
        try:
            matches = isinstance(fe_geometry_identity, Mapping) and _canonical_bytes(
                _freeze_json(fe_geometry_identity, "fe_geometry_identity")
            ) == _canonical_bytes(self.fe_geometry_identity)
        except (TypeError, ValueError):
            matches = False
        if not matches:
            raise RegistrationMismatchError(
                "fe_geometry_identity", "The registration is not valid for the current fe_geometry_identity."
            )
        return True

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FrozenRegistration):
            return NotImplemented
        return self.registration_hash == other.registration_hash

    def __hash__(self) -> int:
        return hash(self.registration_hash)


__all__ = [
    "FROZEN_REGISTRATION_SCHEMA",
    "REGISTRATION_DOF_COMPONENTS",
    "FrozenRegistration",
    "RegistrationMismatchError",
]
