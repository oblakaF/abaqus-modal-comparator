"""Typed contracts for offline forward plate models in the Materials workspace.

A forward computation answers "what does this model predict at these parameters?". It is not a
material identification. Execution status, data provenance and scientific status are therefore
three separate fields, and no field here can express a released material property.

Internal units are SI: metre, kilogram, second, N*m for bending stiffness per unit width.
Conversions happen only in the explicit ``from_units`` constructors.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping, Optional, Sequence, Tuple


PLATE_FORWARD_CONTRACT_VERSION = "abm/plate-forward-contract/v1"
PLATE_CENTERED_FRAME = "PLATE_CENTERED_MATERIAL_AXES"

_LENGTH_TO_M = {"m": 1.0, "mm": 1.0e-3}
_MASS_TO_KG = {"kg": 1.0, "g": 1.0e-3, "t": 1.0e3}
_BENDING_TO_N_M = {"N*m": 1.0, "N*mm": 1.0e-3}


class ForwardBackendId(str, Enum):
    KIRCHHOFF_RITZ_4D = "KIRCHHOFF_RITZ_4D"
    STAGE_A_MATRIX_3D = "STAGE_A_MATRIX_3D"


class ExecutionStatus(str, Enum):
    COMPLETED = "COMPLETED"
    REFUSED = "REFUSED"
    CANCELLED = "CANCELLED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


class EvidenceKind(str, Enum):
    SYNTHETIC = "SYNTHETIC"
    RESEARCH = "RESEARCH"
    PHYSICAL = "PHYSICAL"


class ScientificStatus(str, Enum):
    """A forward result carries no scientific verdict; MAT-2 owns any later diagnostic status."""

    FORWARD_ONLY_NOT_AN_IDENTIFICATION = "FORWARD_ONLY_NOT_AN_IDENTIFICATION"


class QuantitySource(str, Enum):
    MEASURED = "MEASURED"
    DECLARED = "DECLARED"
    FE_INPUT = "FE_INPUT"
    SYNTHETIC = "SYNTHETIC"


class ShapeKind(str, Enum):
    LEGENDRE_TENSOR_COEFFICIENTS = "LEGENDRE_TENSOR_COEFFICIENTS"
    MATRIX_DOF_VECTOR = "MATRIX_DOF_VECTOR"


class RefusalCode(str, Enum):
    INVALID_INPUT = "INVALID_INPUT"
    INADMISSIBLE_PARAMETERS = "INADMISSIBLE_PARAMETERS"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    NON_FINITE_MATRIX = "NON_FINITE_MATRIX"
    ASYMMETRIC_MATRIX = "ASYMMETRIC_MATRIX"
    MASS_NOT_POSITIVE_DEFINITE = "MASS_NOT_POSITIVE_DEFINITE"
    RIGID_SUBSPACE_NOT_VERIFIED = "RIGID_SUBSPACE_NOT_VERIFIED"
    NON_POSITIVE_ELASTIC_EIGENVALUE = "NON_POSITIVE_ELASTIC_EIGENVALUE"
    EIGENSOLVE_FAILED = "EIGENSOLVE_FAILED"
    DEGENERATE_BRANCH = "DEGENERATE_BRANCH"
    BRANCH_NOT_TRACKED = "BRANCH_NOT_TRACKED"
    UNSUPPORTED_KINEMATICS = "UNSUPPORTED_KINEMATICS"
    UNSUPPORTED_OBSERVATION_KIND = "UNSUPPORTED_OBSERVATION_KIND"
    OBSERVATION_OUTSIDE_MODEL = "OBSERVATION_OUTSIDE_MODEL"
    PACKAGE_MISSING = "PACKAGE_MISSING"
    PACKAGE_CORRUPT = "PACKAGE_CORRUPT"
    PACKAGE_UNSUPPORTED = "PACKAGE_UNSUPPORTED"
    PACKAGE_WRONG_MODEL = "PACKAGE_WRONG_MODEL"
    PACKAGE_WRONG_SPECIMEN = "PACKAGE_WRONG_SPECIMEN"
    STAGE_A_REQUIRES_D22_EQUAL_D11 = "STAGE_A_REQUIRES_D22_EQUAL_D11"
    OUTSIDE_VALIDITY_DOMAIN = "OUTSIDE_VALIDITY_DOMAIN"
    MATRIX_MODEL_FAILED = "MATRIX_MODEL_FAILED"


class PlateForwardRefusal(Exception):
    """A specific reason why a forward service will not produce a number."""

    def __init__(self, code: RefusalCode, reason: str) -> None:
        super().__init__(f"{code.value}: {reason}")
        self.code = RefusalCode(code)
        self.reason = str(reason)


def _refuse(code: RefusalCode, reason: str) -> PlateForwardRefusal:
    return PlateForwardRefusal(code, reason)


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool):
        raise _refuse(RefusalCode.INVALID_INPUT, f"{name} must be a finite real number.")
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise _refuse(RefusalCode.INVALID_INPUT, f"{name} must be a finite real number.") from exc
    if not math.isfinite(normalized):
        raise _refuse(RefusalCode.INVALID_INPUT, f"{name} must be finite.")
    return normalized


def _positive(value: float, name: str) -> float:
    normalized = _finite(value, name)
    if normalized <= 0.0:
        raise _refuse(RefusalCode.INVALID_INPUT, f"{name} must be positive.")
    return normalized


def _unit_factor(table: Mapping[str, float], unit: str, name: str) -> float:
    try:
        return table[unit]
    except (KeyError, TypeError) as exc:
        raise _refuse(
            RefusalCode.INVALID_INPUT,
            f"Unsupported {name} unit {unit!r}; supported: {', '.join(sorted(table))}.",
        ) from exc


def _canonical(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return value
    if isinstance(value, float):
        return {"float_hex": value.hex()}
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    item_method = getattr(value, "item", None)
    if callable(item_method):
        return _canonical(item_method())
    raise TypeError(f"Value of type {type(value).__name__} has no canonical identity form.")


def identity_hash(payload: Mapping[str, Any]) -> str:
    """Return the SHA-256 of a canonical form; floats enter exactly, never rounded."""

    text = json.dumps(_canonical(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class QuantityEvidence:
    """Where one input quantity came from. A missing uncertainty stays ``None``."""

    name: str
    source: QuantitySource
    standard_uncertainty_si: Optional[float] = None
    reference: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", QuantitySource(self.source))
        if not str(self.name).strip():
            raise _refuse(RefusalCode.INVALID_INPUT, "A quantity evidence record needs a name.")
        if self.standard_uncertainty_si is not None:
            object.__setattr__(
                self,
                "standard_uncertainty_si",
                _positive(self.standard_uncertainty_si, f"{self.name} uncertainty"),
            )

    def identity(self) -> Mapping[str, Any]:
        return {
            "name": self.name,
            "source": self.source,
            "standard_uncertainty_si": self.standard_uncertainty_si,
            "reference": self.reference,
        }


@dataclass(frozen=True)
class PlateGeometry:
    """A flat rectangle x in [-a/2,a/2], y in [-b/2,b/2], with uniform surface mass."""

    a_m: float
    b_m: float
    surface_mass_kg_m2: float
    thickness_m: Optional[float] = None
    mass_kg: Optional[float] = None
    evidence: Tuple[QuantityEvidence, ...] = ()

    def __post_init__(self) -> None:
        a = _positive(self.a_m, "a")
        b = _positive(self.b_m, "b")
        mu = _positive(self.surface_mass_kg_m2, "surface mass")
        object.__setattr__(self, "a_m", a)
        object.__setattr__(self, "b_m", b)
        object.__setattr__(self, "surface_mass_kg_m2", mu)
        if self.thickness_m is not None:
            object.__setattr__(self, "thickness_m", _positive(self.thickness_m, "thickness"))
        if self.mass_kg is not None:
            mass = _positive(self.mass_kg, "mass")
            object.__setattr__(self, "mass_kg", mass)
            if mu != mass / (a * b):
                raise _refuse(RefusalCode.INVALID_INPUT, "mass_kg does not equal mu*a*b; use from_units.")
        object.__setattr__(self, "evidence", tuple(self.evidence))

    @classmethod
    def from_units(
        cls,
        a: float,
        b: float,
        length_unit: str,
        *,
        mass: Optional[float] = None,
        mass_unit: str = "kg",
        surface_mass_kg_m2: Optional[float] = None,
        thickness: Optional[float] = None,
        evidence: Sequence[QuantityEvidence] = (),
    ) -> "PlateGeometry":
        """Build from stated units. Exactly one of ``mass`` or ``surface_mass_kg_m2`` is required."""

        if (mass is None) == (surface_mass_kg_m2 is None):
            raise _refuse(RefusalCode.INVALID_INPUT, "Give exactly one of mass or surface mass.")
        to_m = _unit_factor(_LENGTH_TO_M, length_unit, "length")
        a_m = _positive(a, "a") * to_m
        b_m = _positive(b, "b") * to_m
        thickness_m = None if thickness is None else _positive(thickness, "thickness") * to_m
        if mass is None:
            return cls(a_m, b_m, _positive(surface_mass_kg_m2, "surface mass"), thickness_m, None, tuple(evidence))
        mass_kg = _positive(mass, "mass") * _unit_factor(_MASS_TO_KG, mass_unit, "mass")
        return cls(a_m, b_m, mass_kg / (a_m * b_m), thickness_m, mass_kg, tuple(evidence))

    def identity(self) -> Mapping[str, Any]:
        return {
            "a_m": self.a_m,
            "b_m": self.b_m,
            "surface_mass_kg_m2": self.surface_mass_kg_m2,
            "thickness_m": self.thickness_m,
            "mass_kg": self.mass_kg,
            "units": "SI",
            "evidence": [item.identity() for item in self.evidence],
        }


@dataclass(frozen=True)
class MixedCoordinateReference:
    """The fixed reference of the mixed coordinates; never a claim about a material."""

    D11_ref: float
    D22_ref: float
    D66_ref: float

    def __post_init__(self) -> None:
        for name in ("D11_ref", "D22_ref", "D66_ref"):
            object.__setattr__(self, name, _positive(getattr(self, name), name))


@dataclass(frozen=True)
class PlateBendingParameters:
    """D11, D22, D12, D66 in N*m, with D11,D22,D66 > 0 and D12^2 < D11*D22."""

    D11: float
    D22: float
    D12: float
    D66: float

    def __post_init__(self) -> None:
        values = {name: getattr(self, name) for name in ("D11", "D22", "D12", "D66")}
        for name, value in values.items():
            try:
                object.__setattr__(self, name, _finite(value, name))
            except PlateForwardRefusal as exc:
                raise _refuse(RefusalCode.INADMISSIBLE_PARAMETERS, exc.reason) from exc
        if self.D11 <= 0.0 or self.D22 <= 0.0 or self.D66 <= 0.0:
            raise _refuse(RefusalCode.INADMISSIBLE_PARAMETERS, "D11, D22 and D66 must be positive.")
        if not self.D12 * self.D12 < self.D11 * self.D22:
            raise _refuse(RefusalCode.INADMISSIBLE_PARAMETERS, "D12^2 must be less than D11*D22.")

    @classmethod
    def from_units(cls, D11: float, D22: float, D12: float, D66: float, unit: str) -> "PlateBendingParameters":
        factor = _unit_factor(_BENDING_TO_N_M, unit, "bending stiffness")
        return cls(
            _finite(D11, "D11") * factor,
            _finite(D22, "D22") * factor,
            _finite(D12, "D12") * factor,
            _finite(D66, "D66") * factor,
        )

    @classmethod
    def from_engineering_constants(
        cls, E1: float, E2: float, nu12: float, G12: float, thickness_m: float
    ) -> "PlateBendingParameters":
        """Exact plane-stress form in SI, the inverse of :func:`effective_engineering_constants`.

        ``nu12`` follows the project convention ``nu12 = D12/D22`` and ``nu21 = D12/D11``.
        """

        e1 = _positive(E1, "E1")
        e2 = _positive(E2, "E2")
        g12 = _positive(G12, "G12")
        h = _positive(thickness_m, "thickness")
        nu = _finite(nu12, "nu12")
        nu21 = nu * e2 / e1
        denominator = 1.0 - nu * nu21
        if denominator <= 0.0:
            raise _refuse(RefusalCode.INADMISSIBLE_PARAMETERS, "1 - nu12*nu21 must be positive.")
        scale = h**3 / 12.0
        d11 = scale * e1 / denominator
        d22 = scale * e2 / denominator
        return cls(d11, d22, nu * d22, scale * g12)

    @classmethod
    def from_mixed_coordinates(
        cls, theta: Sequence[float], reference: MixedCoordinateReference
    ) -> "PlateBendingParameters":
        """Map (ln(D11/ref), ln(D22/ref), ln(D66/ref), u) with u = D12/D22; u is not logged."""

        if len(theta) != 4:
            raise _refuse(RefusalCode.INVALID_INPUT, "Mixed coordinates have exactly four components.")
        t1, t2, t3, u = (_finite(value, f"theta[{index}]") for index, value in enumerate(theta))
        try:
            d11 = reference.D11_ref * math.exp(t1)
            d22 = reference.D22_ref * math.exp(t2)
            d66 = reference.D66_ref * math.exp(t3)
        except OverflowError as exc:
            raise _refuse(RefusalCode.INADMISSIBLE_PARAMETERS, "theta maps to a non-finite stiffness.") from exc
        return cls(d11, d22, u * d22, d66)

    def mixed_coordinates(self, reference: MixedCoordinateReference) -> Tuple[float, float, float, float]:
        return (
            math.log(self.D11 / reference.D11_ref),
            math.log(self.D22 / reference.D22_ref),
            math.log(self.D66 / reference.D66_ref),
            self.D12 / self.D22,
        )

    @property
    def u(self) -> float:
        return self.D12 / self.D22

    def identity(self) -> Mapping[str, Any]:
        return {"D11": self.D11, "D22": self.D22, "D12": self.D12, "D66": self.D66, "unit": "N*m"}


@dataclass(frozen=True)
class EffectiveEngineeringConstants:
    """Conditional effective flexural constants of the equivalent plate, not ply properties."""

    nu12: float
    nu21: float
    E1_flex_pa: Optional[float]
    E2_flex_pa: Optional[float]
    G12_flex_pa: Optional[float]
    missing_reason: str = ""


def effective_engineering_constants(
    parameters: PlateBendingParameters, thickness_m: Optional[float]
) -> EffectiveEngineeringConstants:
    """Convert D to effective constants. Without a thickness, E and G stay missing."""

    nu12 = parameters.D12 / parameters.D22
    nu21 = parameters.D12 / parameters.D11
    if thickness_m is None:
        return EffectiveEngineeringConstants(nu12, nu21, None, None, None, "No thickness: E and G are not reported.")
    scale = 12.0 / _positive(thickness_m, "thickness") ** 3
    return EffectiveEngineeringConstants(
        nu12,
        nu21,
        scale * (parameters.D11 - parameters.D12**2 / parameters.D22),
        scale * (parameters.D22 - parameters.D12**2 / parameters.D11),
        scale * parameters.D66,
    )


@dataclass(frozen=True)
class ObservationPoint:
    """One registered point and measured direction, both in the plate-centred material frame.

    ``surface_offset_m`` is the height of the measured surface above the mid-plane. It is required
    for any direction with an in-plane part, since Kirchhoff in-plane motion is ``-z*grad(w)``.
    """

    observation_id: str
    x_m: float
    y_m: float
    direction: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    surface_offset_m: Optional[float] = None
    component_meaning: str = "transverse displacement w"

    def __post_init__(self) -> None:
        if not str(self.observation_id).strip():
            raise _refuse(RefusalCode.INVALID_INPUT, "An observation point needs an identifier.")
        object.__setattr__(self, "x_m", _finite(self.x_m, "x"))
        object.__setattr__(self, "y_m", _finite(self.y_m, "y"))
        direction = tuple(_finite(value, "direction component") for value in self.direction)
        if len(direction) != 3:
            raise _refuse(RefusalCode.INVALID_INPUT, "A measured direction has three components.")
        if abs(math.sqrt(sum(value * value for value in direction)) - 1.0) > 1.0e-9:
            raise _refuse(RefusalCode.INVALID_INPUT, f"{self.observation_id}: direction must be a unit vector.")
        object.__setattr__(self, "direction", direction)
        if self.surface_offset_m is not None:
            object.__setattr__(self, "surface_offset_m", _finite(self.surface_offset_m, "surface offset"))

    def identity(self) -> Mapping[str, Any]:
        return {
            "id": self.observation_id,
            "x_m": self.x_m,
            "y_m": self.y_m,
            "direction": self.direction,
            "surface_offset_m": self.surface_offset_m,
            "component_meaning": self.component_meaning,
        }


@dataclass(frozen=True)
class CoordinateObservationSet:
    """Points placed by an independent registration; this contract never derives one from shapes."""

    registration_id: str
    points: Tuple[ObservationPoint, ...]
    coordinate_frame: str = PLATE_CENTERED_FRAME

    def __post_init__(self) -> None:
        if not str(self.registration_id).strip():
            raise _refuse(RefusalCode.INVALID_INPUT, "Observations need an explicit registration identity.")
        points = tuple(self.points)
        if not points:
            raise _refuse(RefusalCode.INVALID_INPUT, "An observation set must not be empty.")
        identifiers = [point.observation_id for point in points]
        if len(set(identifiers)) != len(identifiers):
            raise _refuse(RefusalCode.INVALID_INPUT, "Observation identifiers must be unique.")
        if self.coordinate_frame != PLATE_CENTERED_FRAME:
            raise _refuse(RefusalCode.UNSUPPORTED_KINEMATICS, f"Unsupported coordinate frame {self.coordinate_frame!r}.")
        object.__setattr__(self, "points", points)

    def identity(self) -> Mapping[str, Any]:
        return {
            "kind": "COORDINATE",
            "registration_id": self.registration_id,
            "coordinate_frame": self.coordinate_frame,
            "points": [point.identity() for point in self.points],
        }


@dataclass(frozen=True)
class DofObservation:
    observation_id: str
    node_label: int
    dof: int


@dataclass(frozen=True)
class DofObservationSet:
    """Observations addressed by exact stored matrix DOF identities."""

    registration_id: str
    items: Tuple[DofObservation, ...]

    def __post_init__(self) -> None:
        if not str(self.registration_id).strip():
            raise _refuse(RefusalCode.INVALID_INPUT, "Observations need an explicit registration identity.")
        items = tuple(self.items)
        if not items:
            raise _refuse(RefusalCode.INVALID_INPUT, "An observation set must not be empty.")
        identifiers = [item.observation_id for item in items]
        if len(set(identifiers)) != len(identifiers):
            raise _refuse(RefusalCode.INVALID_INPUT, "Observation identifiers must be unique.")
        object.__setattr__(self, "items", items)

    def identity(self) -> Mapping[str, Any]:
        return {
            "kind": "MATRIX_DOF",
            "registration_id": self.registration_id,
            "items": [[item.observation_id, int(item.node_label), int(item.dof)] for item in self.items],
        }


@dataclass(frozen=True)
class ObservationEvaluation:
    """Model shapes at the observations: rows are observations, columns are elastic modes."""

    observation_ids: Tuple[str, ...]
    values: Any
    component_meanings: Tuple[str, ...]
    registration_id: str
    w: Any = None
    w_x: Any = None
    w_y: Any = None


@dataclass(frozen=True)
class ResourceLimits:
    """Bounds checked before allocation. Development resource limits, not scientific tolerances."""

    max_dofs: int = 1024
    max_allocation_bytes: int = 512 * 1024 * 1024
    max_package_file_bytes: int = 256 * 1024 * 1024
    max_package_uncompressed_bytes: int = 512 * 1024 * 1024
    max_manifest_bytes: int = 4 * 1024 * 1024
    max_matrix_nonzeros: int = 10_000_000
    max_matrix_dofs: int = 100_000

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise _refuse(RefusalCode.INVALID_INPUT, f"{name} must be a positive integer.")


@dataclass(frozen=True)
class BackendCapabilities:
    backend_id: ForwardBackendId
    backend_version: str
    independent_parameters: Tuple[str, ...]
    parameter_constraints: Tuple[str, ...]
    shape_kind: ShapeKind
    observation_kinds: Tuple[str, ...]
    mass_depends_on_parameters: str
    sum_of_energy_fractions_applies: bool
    requires_matrix_package: bool
    computes_frequencies: bool = True
    computes_shapes: bool = True
    computes_sensitivities: bool = True
    requires_abaqus_installation: bool = False
    requires_odb: bool = False
    can_generate_matrices: bool = False
    performs_material_identification: bool = False


@dataclass(frozen=True)
class BackendAvailability:
    backend_id: ForwardBackendId
    available: bool
    refusal_code: Optional[RefusalCode] = None
    reason: str = ""


@dataclass(frozen=True)
class ForwardProvenance:
    evidence_kind: EvidenceKind
    description: str
    source_identities: Tuple[Tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_kind", EvidenceKind(self.evidence_kind))
        object.__setattr__(self, "source_identities", tuple(tuple(item) for item in self.source_identities))

    def identity(self) -> Mapping[str, Any]:
        return {
            "evidence_kind": self.evidence_kind,
            "description": self.description,
            "source_identities": [list(item) for item in self.source_identities],
        }


@dataclass(frozen=True)
class ShapeRepresentation:
    """Mass-orthonormal shapes stored by columns, with the exact meaning of each row."""

    kind: ShapeKind
    values: Any
    row_labels: Tuple[Tuple[int, int], ...]
    row_meaning: str
    coordinate_meaning: str
    component_meaning: str
    normalization: str = "MASS_ORTHONORMAL"


@dataclass(frozen=True)
class PlateForwardResult:
    execution_status: ExecutionStatus
    provenance: ForwardProvenance
    backend_id: ForwardBackendId
    backend_version: str
    scientific_status: ScientificStatus = ScientificStatus.FORWARD_ONLY_NOT_AN_IDENTIFICATION
    model_identity: str = ""
    run_identity: str = ""
    parameters: Optional[PlateBendingParameters] = None
    frequencies_hz: Tuple[float, ...] = ()
    eigenvalues: Tuple[float, ...] = ()
    shape: Optional[ShapeRepresentation] = None
    observation: Optional[ObservationEvaluation] = None
    diagnostics: Mapping[str, Any] = None  # type: ignore[assignment]
    refusal_code: Optional[RefusalCode] = None
    refusal_reason: str = ""

    def __post_init__(self) -> None:
        status = ExecutionStatus(self.execution_status)
        object.__setattr__(self, "execution_status", status)
        object.__setattr__(self, "backend_id", ForwardBackendId(self.backend_id))
        object.__setattr__(self, "scientific_status", ScientificStatus(self.scientific_status))
        object.__setattr__(self, "diagnostics", dict(self.diagnostics or {}))
        if status is ExecutionStatus.COMPLETED:
            if self.refusal_code is not None or not self.frequencies_hz or self.shape is None:
                raise ValueError("A completed forward result holds frequencies and shapes and no refusal.")
        elif status is ExecutionStatus.REFUSED:
            if self.refusal_code is None or self.frequencies_hz or self.shape is not None:
                raise ValueError("A refused forward result holds a reason and no numbers.")
