"""Frozen declaration and result contracts of the shared offline plate inverse workflow (MAT-2).

A declaration fixes everything before the first solve: backend and model identity, specimen identity,
observations and their frozen mode identities, FIT and HOLDOUT families, parameters, numerical policy
and resource budget. A result keeps execution, numerical and scientific status apart. Its release
status is always NOT_A_RELEASE_VALUE: nothing here can express an accepted material property or a
released engineering calibration.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Mapping, Optional, Tuple

from .plate_material_problem import (
    CoordinateObservationSet,
    DofObservationSet,
    EvidenceKind,
    ExecutionStatus,
    ForwardBackendId,
    PlateGeometry,
    ResourceLimits,
    identity_hash,
)


PLATE_INVERSE_DECLARATION_SCHEMA = "abm/plate-inverse-declaration/v1"
# Stands in the baseline-identity fields that name physical source files. A synthetic study has no such
# files, so these fields hold no hash at all: no other identity is put in their place.
SYNTHETIC_NO_PHYSICAL_SOURCE = "SYNTHETIC_NO_PHYSICAL_SOURCE"
RESTRICTIONS_UNCHANGED = (
    "M8 GATE NOT_MET",
    "D-077 NO_GLOBAL_PARAMETER_VALUE",
    "production Auto-ID BLOCKED",
)


class StudyIntent(str, Enum):
    SYNTHETIC_SOFTWARE_TEST = "SYNTHETIC_SOFTWARE_TEST"
    MATERIAL_IDENTIFICATION_RESEARCH = "MATERIAL_IDENTIFICATION_RESEARCH"  # not authorized to run in MAT-2


class ObservationRole(str, Enum):
    FIT = "FIT"
    HOLDOUT = "HOLDOUT"


class NumericalStatus(str, Enum):
    NOT_RUN = "NOT_RUN"
    CONVERGED = "CONVERGED"
    CONVERGED_AT_BOUND = "CONVERGED_AT_BOUND"
    MAX_ITERATIONS = "MAX_ITERATIONS"
    STEP_REJECTED = "STEP_REJECTED"
    SOLVE_BUDGET = "SOLVE_BUDGET"
    REFUSED = "REFUSED"
    SENSITIVITY_CHECK_FAILED = "SENSITIVITY_CHECK_FAILED"


class InverseScientificStatus(str, Enum):
    NO_RESULT = "NO_RESULT"
    NOT_CONVERGED_NO_CANDIDATE = "NOT_CONVERGED_NO_CANDIDATE"
    NOT_IDENTIFIABLE = "NOT_IDENTIFIABLE"
    MODEL_FORM_CHECK_FAILED = "MODEL_FORM_CHECK_FAILED"
    ROBUSTNESS_INCOMPLETE = "ROBUSTNESS_INCOMPLETE"
    DIAGNOSTIC_OPTIMIZER_CANDIDATE = "DIAGNOSTIC_OPTIMIZER_CANDIDATE"


class ReleaseStatus(str, Enum):
    NOT_A_RELEASE_VALUE = "NOT_A_RELEASE_VALUE"


class InverseRefusalCode(str, Enum):
    DECLARATION_INVALID = "DECLARATION_INVALID"
    UNSUPPORTED_STUDY_INTENT = "UNSUPPORTED_STUDY_INTENT"
    MISSING_HOLDOUT = "MISSING_HOLDOUT"
    HOLDOUT_NOT_INDEPENDENT = "HOLDOUT_NOT_INDEPENDENT"
    INCOMPLETE_COVARIANCE = "INCOMPLETE_COVARIANCE"
    INPUT_SOURCE_REFUSED = "INPUT_SOURCE_REFUSED"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    MODEL_IDENTITY_MISMATCH = "MODEL_IDENTITY_MISMATCH"
    PACKAGE_REFUSED = "PACKAGE_REFUSED"
    EVIDENCE_KIND_MISMATCH = "EVIDENCE_KIND_MISMATCH"
    OUTSIDE_VALIDATED_RANGE = "OUTSIDE_VALIDATED_RANGE"
    INADMISSIBLE_POINT = "INADMISSIBLE_POINT"
    FORWARD_REFUSED = "FORWARD_REFUSED"
    NUMERICAL_HEALTH_FAILED = "NUMERICAL_HEALTH_FAILED"
    BASELINE_PAIRING_REFUSED = "BASELINE_PAIRING_REFUSED"
    UNRESOLVED_MODAL_CLUSTER = "UNRESOLVED_MODAL_CLUSTER"
    RANK_DEFICIENT = "RANK_DEFICIENT"
    PARAMETER_NOT_OBSERVABLE = "PARAMETER_NOT_OBSERVABLE"
    BRANCH_IDENTITY_LOST = "BRANCH_IDENTITY_LOST"
    STEP_UNDEFINED = "STEP_UNDEFINED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    CANCELLED = "CANCELLED"


class MaterialReleaseRefusal(Exception):
    """A diagnostic candidate is not a material property or a calibration. There is no override."""


@dataclass(frozen=True)
class FrozenPlateObservation:
    """One experimental mode with its fixed model identity at the start point.

    ``shape`` holds complex modal values at the declared observation set. It enters identity checks
    only, never the objective. ``measurement_sd_ln=None`` means NOT_AVAILABLE, never zero. A row with
    no ``setup_sd_ln`` has incomplete covariance.
    """

    row_id: str
    experimental_mode: int
    experimental_hz: float
    model_mode: int
    role: ObservationRole
    family: str
    mode_source: Optional[str]
    shape: Tuple[complex, ...]
    measurement_sd_ln: Optional[float] = None
    setup_sd_ln: Optional[float] = None
    setup_provisional: bool = True
    dataset_type: Optional[int] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", ObservationRole(self.role))
        object.__setattr__(self, "shape", tuple(complex(value) for value in self.shape))
        if not str(self.row_id).strip() or not str(self.family).strip():
            raise ValueError("A frozen observation needs a row identity and a modal family.")

    def identity(self) -> Mapping[str, Any]:
        return {
            "row_id": self.row_id,
            "experimental_mode": self.experimental_mode,
            "experimental_hz": float(self.experimental_hz),
            "model_mode": self.model_mode,
            "role": self.role,
            "family": self.family,
            "mode_source": self.mode_source,
            "dataset_type": self.dataset_type,
            "measurement_sd_ln": self.measurement_sd_ln,
            "setup_sd_ln": self.setup_sd_ln,
            "setup_provisional": self.setup_provisional,
            "shape": [[float(value.real), float(value.imag)] for value in self.shape],
        }


@dataclass(frozen=True)
class FittedParameter:
    """Start and bounds in physical units: N*m for stiffness, and dimensionless for a ratio."""

    name: str
    start: float
    lower: float
    upper: float

    def identity(self) -> Mapping[str, Any]:
        return {"name": self.name, "start": float(self.start), "lower": float(self.lower), "upper": float(self.upper)}


@dataclass(frozen=True)
class InverseNumericalPolicy:
    """Explicit numerical settings. They are bound into the run identity; none is a scientific threshold."""

    mu_initial: float = 1.0e-3
    mu_decrease: float = 10.0
    max_step_attempts: int = 8
    max_iterations: int = 5  # SPEC 8
    stop_fraction: float = 0.2  # SPEC 8
    finite_difference_step: float = 0.05  # SPEC 6 S4
    linear_finite_difference_step: float = 0.02
    final_sensitivity_step: float = 1.0e-3
    cluster_perturbation_step: float = 0.05
    max_eigen_residual: float = 1.0e-8
    max_orthonormality_error: float = 1.0e-8
    max_analytic_sensitivity_difference: float = 1.0e-4
    max_objective_replay_difference: float = 1.0e-9
    # At or below this spacing two frozen modes have no defined individual eigenvectors, only a subspace.
    repeated_frequency_relative_spacing: float = 1.0e-9

    def identity(self) -> Mapping[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class InverseResourceBudget:
    max_solves: int = 400
    max_elapsed_seconds: float = 60.0
    limits: ResourceLimits = ResourceLimits()

    def identity(self) -> Mapping[str, Any]:
        return {
            "max_solves": self.max_solves,
            "max_elapsed_seconds": float(self.max_elapsed_seconds),
            "limits": {name: getattr(self.limits, name) for name in self.limits.__dataclass_fields__},
        }


@dataclass(frozen=True)
class PlateInverseDeclaration:
    """Everything a run depends on, fixed before the first solve."""

    study_id: str
    intent: StudyIntent
    evidence_kind: EvidenceKind
    backend_id: ForwardBackendId
    model_identity: str
    specimen_id: str
    observation_set: Any  # CoordinateObservationSet or DofObservationSet
    rows: Tuple[FrozenPlateObservation, ...]
    parameters: Tuple[FittedParameter, ...]
    confirmed_clusters: Tuple[Tuple[str, str], ...] = ()
    geometry: Optional[PlateGeometry] = None
    degree_x: Optional[int] = None
    degree_y: Optional[int] = None
    forward_mode_count: int = 12
    stage_a_model_id: Optional[str] = None
    execution_authorization: Optional[str] = None  # recorded text only: it never enables an execution
    provenance: str = ""
    policy: InverseNumericalPolicy = InverseNumericalPolicy()
    budget: InverseResourceBudget = InverseResourceBudget()

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "intent", StudyIntent(self.intent))
        except ValueError:  # kept as text, so that the workflow can refuse it with a result and a code
            object.__setattr__(self, "intent", str(self.intent))
        object.__setattr__(self, "evidence_kind", EvidenceKind(self.evidence_kind))
        object.__setattr__(self, "backend_id", ForwardBackendId(self.backend_id))
        object.__setattr__(self, "rows", tuple(self.rows))
        object.__setattr__(self, "parameters", tuple(self.parameters))
        object.__setattr__(self, "confirmed_clusters", tuple(tuple(item) for item in self.confirmed_clusters))
        if not isinstance(self.observation_set, (CoordinateObservationSet, DofObservationSet)):
            raise ValueError("observation_set must be a registered coordinate or matrix-DOF observation set.")

    def identity(self) -> Mapping[str, Any]:
        return {
            "schema": PLATE_INVERSE_DECLARATION_SCHEMA,
            "study_id": self.study_id,
            "intent": self.intent,
            "evidence_kind": self.evidence_kind,
            "backend_id": self.backend_id,
            "model_identity": self.model_identity,
            "specimen_id": self.specimen_id,
            "observation_set": self.observation_set.identity(),
            "rows": [row.identity() for row in self.rows],
            "parameters": [parameter.identity() for parameter in self.parameters],
            "confirmed_clusters": [list(item) for item in self.confirmed_clusters],
            "geometry": None if self.geometry is None else self.geometry.identity(),
            "degree_x": self.degree_x,
            "degree_y": self.degree_y,
            "forward_mode_count": self.forward_mode_count,
            "stage_a_model_id": self.stage_a_model_id,
            "execution_authorization": self.execution_authorization,
            "provenance": self.provenance,
            "policy": self.policy.identity(),
            "budget": self.budget.identity(),
        }

    @property
    def declaration_hash(self) -> str:
        return identity_hash(self.identity())


@dataclass(frozen=True)
class ResidualTableRow:
    term_id: str
    row_ids: Tuple[str, ...]
    role: ObservationRole
    family: str
    sigma_ln: float
    initial_log_ratio: float
    final_log_ratio: float
    initial_whitened: float
    final_whitened: float


@dataclass(frozen=True)
class ModalFrequencyRow:
    row_id: str
    role: ObservationRole
    experimental_hz: float
    initial_model_hz: float
    final_model_hz: float


@dataclass(frozen=True)
class ModeIdentityRow:
    """Identity evidence only. MAC here never enters the objective or its weights."""

    row_id: str
    experimental_mode: int
    initial_model_mode: int
    final_model_mode: int
    initial_experimental_mac: float
    final_experimental_mac: float
    minimum_model_to_model_mac: float


@dataclass(frozen=True)
class LeaveOneFamilyOutRow:
    family: str
    removed_term_ids: Tuple[str, ...]
    status: str
    estimate: Optional[Mapping[str, float]]
    reasons: Tuple[str, ...]


@dataclass(frozen=True)
class IdentifiabilityDiagnostics:
    status: str
    rank: int
    parameter_ids: Tuple[str, ...]
    singular_values: Tuple[float, ...]
    condition_number: float
    correlation: Optional[Tuple[Tuple[float, ...], ...]]
    pairwise_cosines: Mapping[str, float]
    projection_q: Mapping[str, float]
    sensitivity: Tuple[Tuple[float, ...], ...]
    term_ids: Tuple[str, ...]


@dataclass(frozen=True)
class UncertaintyReport:
    """Separate quantities, never merged into one 1-sigma figure. Missing parts are named."""

    statistical_sd: Optional[Mapping[str, float]]
    birge_status: str
    birge_adjusted_sd: Optional[Mapping[str, float]]
    robustness_range: Mapping[str, Tuple[float, float]]
    robustness_note: str
    pattern_status: str
    pattern_reasons: Tuple[str, ...]
    available_components: Tuple[str, ...]
    missing_components: Tuple[str, ...]


@dataclass(frozen=True)
class PlateInverseResult:
    declaration_hash: str
    execution_status: ExecutionStatus
    numerical_status: NumericalStatus
    scientific_status: InverseScientificStatus
    evidence_kind: EvidenceKind
    backend_id: ForwardBackendId
    release_status: ReleaseStatus = ReleaseStatus.NOT_A_RELEASE_VALUE
    restrictions_unchanged: Tuple[str, ...] = RESTRICTIONS_UNCHANGED
    refusal_code: Optional[InverseRefusalCode] = None
    refusal_reason: str = ""
    forward_refusal_code: Optional[str] = None
    scientific_reasons: Tuple[str, ...] = ()
    initial_parameters: Optional[Mapping[str, float]] = None
    final_parameters: Optional[Mapping[str, float]] = None
    initial_stiffness: Optional[Mapping[str, float]] = None
    final_stiffness: Optional[Mapping[str, float]] = None
    conditional_effective_constants: Optional[Mapping[str, Optional[float]]] = None
    frequencies: Tuple[ModalFrequencyRow, ...] = ()
    fit_residuals: Tuple[ResidualTableRow, ...] = ()
    holdout_residuals: Tuple[ResidualTableRow, ...] = ()
    mode_identity: Tuple[ModeIdentityRow, ...] = ()
    order_changes: Tuple[Tuple[str, str], ...] = ()
    iterations: Tuple[Any, ...] = ()
    initial_objective: Optional[float] = None
    final_objective: Optional[float] = None
    solves: int = 0
    identifiability: Optional[IdentifiabilityDiagnostics] = None
    uncertainty: Optional[UncertaintyReport] = None
    leave_one_family_out: Tuple[LeaveOneFamilyOutRow, ...] = ()
    max_analytic_sensitivity_difference: Optional[float] = None
    max_eigen_residual_seen: Optional[float] = None
    max_orthonormality_error_seen: Optional[float] = None
    package_validation_text: Optional[str] = None
    package_validation_status: str = "NOT_APPLICABLE"

    def __post_init__(self) -> None:
        if self.release_status is not ReleaseStatus.NOT_A_RELEASE_VALUE:
            raise ValueError("This workflow has no release status other than NOT_A_RELEASE_VALUE.")

    def identity(self) -> Mapping[str, Any]:
        """Every computed field, for reproducibility checks. Floats enter exactly."""

        def rows(items):
            return [{name: getattr(item, name) for name in item.__dataclass_fields__} for item in items]

        def block(item):
            return None if item is None else {name: getattr(item, name) for name in item.__dataclass_fields__}

        return {
            "declaration_hash": self.declaration_hash,
            "execution_status": self.execution_status,
            "numerical_status": self.numerical_status,
            "scientific_status": self.scientific_status,
            "refusal_code": self.refusal_code,
            "initial_parameters": self.initial_parameters,
            "final_parameters": self.final_parameters,
            "frequencies": rows(self.frequencies),
            "fit_residuals": rows(self.fit_residuals),
            "holdout_residuals": rows(self.holdout_residuals),
            "mode_identity": rows(self.mode_identity),
            "iterations": rows(self.iterations),
            "solves": self.solves,
            "identifiability": block(self.identifiability),
            "uncertainty": block(self.uncertainty),
            "leave_one_family_out": rows(self.leave_one_family_out),
        }

    @property
    def result_hash(self) -> str:
        return identity_hash(self.identity())


def finite_positive(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value) > 0.0
    )
