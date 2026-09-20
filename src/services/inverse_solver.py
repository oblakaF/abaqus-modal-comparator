"""Stage-A inverse identification using the verified affine matrix model.

The solver deliberately contains no Abaqus execution path.  Global and local
objective evaluations reconstruct the affine stiffness matrix and use SciPy's
generalized eigensolver through :mod:`matrix_model_service`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Callable, Mapping, Sequence, Tuple

import numpy as np
from scipy import optimize, sparse

from domain.modal_observation import InclusionStatus, ModalCluster, ModalObservation
from domain.parameter_model import ParameterPrior

from .identifiability_service import IdentifiabilityResult
from .matrix_model_service import (
    GeneralizedEigenResult,
    MatrixModelError,
    StageAAffineBasis,
    StageAMatrixParameters,
    solve_generalized_eigenproblem,
)
from .sensitivity_service import (
    ParameterSensitivityCoordinate,
    StageASensitivityCoordinate,
    generalized_eigen_sensitivity,
)
from .stage_a_parameterization import StageAParameterization


STAGE_A_PARAMETER_IDS = ("D11", "D12", "D66")
_FAILED_OBJECTIVE = 1.0e100


class InverseSolverValidationError(ValueError):
    """The inverse problem is incomplete, ambiguous, or inconsistent."""


class ModeTrackingMode(str, Enum):
    """Explicitly distinguishes synthetic tracking from experimental pairing."""

    FIXED_PAIR_SYNTHETIC = "fixed_pair_synthetic"
    COMPARISON_BACKED = "comparison_backed_repairing"


@dataclass(frozen=True)
class StageAParameterBounds:
    """Finite physical bounds converted to the PR-4 safe coordinates."""

    D11: Tuple[float, float]
    D66: Tuple[float, float]
    coupling_ratio: Tuple[float, float]

    def __post_init__(self) -> None:
        normalized: list[Tuple[float, float]] = []
        for name, supplied in (
            ("D11", self.D11),
            ("D66", self.D66),
            ("coupling_ratio", self.coupling_ratio),
        ):
            if len(supplied) != 2:
                raise InverseSolverValidationError(
                    f"{name} bounds require exactly (lower, upper)."
                )
            lower, upper = (float(value) for value in supplied)
            if not math.isfinite(lower) or not math.isfinite(upper) or lower >= upper:
                raise InverseSolverValidationError(
                    f"{name} bounds must be finite with lower < upper."
                )
            normalized.append((lower, upper))
        d11, d66, ratio = normalized
        if d11[0] <= 0.0 or d66[0] <= 0.0:
            raise InverseSolverValidationError("D11 and D66 bounds must be positive.")
        if not -1.0 < ratio[0] < ratio[1] < 1.0:
            raise InverseSolverValidationError(
                "coupling_ratio bounds must lie strictly inside (-1, 1)."
            )
        object.__setattr__(self, "D11", d11)
        object.__setattr__(self, "D66", d66)
        object.__setattr__(self, "coupling_ratio", ratio)


@dataclass(frozen=True)
class ModeAssignment:
    observation_id: str
    fe_mode_id: int
    mac: float | None = None
    tracking_mac: float | None = None

    def __post_init__(self) -> None:
        identifier = str(self.observation_id).strip()
        if not identifier:
            raise InverseSolverValidationError("A mode assignment needs an observation ID.")
        if isinstance(self.fe_mode_id, bool) or int(self.fe_mode_id) != self.fe_mode_id:
            raise InverseSolverValidationError("Assigned FE mode IDs must be integers.")
        if int(self.fe_mode_id) <= 0:
            raise InverseSolverValidationError("Assigned FE mode IDs must be positive.")
        for name, value in (("MAC", self.mac), ("tracking MAC", self.tracking_mac)):
            if value is not None and (
                not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0
            ):
                raise InverseSolverValidationError(f"{name} must be in [0, 1].")
        object.__setattr__(self, "observation_id", identifier)
        object.__setattr__(self, "fe_mode_id", int(self.fe_mode_id))


@dataclass(frozen=True)
class PairingResult:
    """One complete accepted pairing for the current candidate.

    Comparison-backed providers apply their existing MAC quality gate before
    returning this object.  MAC values are retained as pairing evidence and
    never enter the frequency objective.
    """

    assignments: Tuple[ModeAssignment, ...]
    method: str
    warnings: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        assignments = tuple(self.assignments)
        if not assignments:
            raise InverseSolverValidationError("A pairing result cannot be empty.")
        observation_ids = tuple(item.observation_id for item in assignments)
        mode_ids = tuple(item.fe_mode_id for item in assignments)
        if len(set(observation_ids)) != len(observation_ids):
            raise InverseSolverValidationError("Pairing observation IDs must be unique.")
        if len(set(mode_ids)) != len(mode_ids):
            raise InverseSolverValidationError(
                "One FE mode cannot be paired to multiple fitting observations."
            )
        method = str(self.method).strip()
        if not method:
            raise InverseSolverValidationError("A pairing result needs a method.")
        object.__setattr__(self, "assignments", assignments)
        object.__setattr__(self, "method", method)
        object.__setattr__(self, "warnings", tuple(str(item) for item in self.warnings))

    @property
    def signature(self) -> Tuple[Tuple[str, int], ...]:
        return tuple(
            sorted((item.observation_id, item.fe_mode_id) for item in self.assignments)
        )


ComparisonPairingProvider = Callable[
    [Tuple[ModalObservation, ...], GeneralizedEigenResult], PairingResult
]


@dataclass(frozen=True)
class ExcludedSolverObservation:
    observation_id: str
    status: str
    reason: str


@dataclass(frozen=True)
class OptimizationHistoryEntry:
    stage: str
    evaluation: int
    transformed_parameters: Tuple[float, ...]
    physical_parameters: Mapping[str, float]
    objective: float
    success: bool
    pairing_signature: Tuple[Tuple[str, int], ...] = ()
    message: str = ""


@dataclass(frozen=True)
class InverseSolverConfiguration:
    mode_count: int
    expected_rigid_body_modes: int | None = None
    tracking_mode: ModeTrackingMode = ModeTrackingMode.FIXED_PAIR_SYNTHETIC
    random_seed: int = 1729
    global_max_iterations: int = 100
    global_population_size: int = 12
    global_tolerance: float = 1.0e-8
    global_absolute_tolerance: float = 1.0e-10
    local_max_evaluations: int = 300
    local_xtol: float = 1.0e-12
    local_ftol: float = 1.0e-12
    local_gtol: float = 1.0e-12
    allow_unweighted: bool = False
    allow_non_identifiable_subset: bool = False
    downweighted_observation_weights: Mapping[str, float] = field(
        default_factory=dict, compare=False
    )
    cache_decimals: int = 12

    def __post_init__(self) -> None:
        integer_fields = (
            ("mode_count", self.mode_count, 1),
            ("global_max_iterations", self.global_max_iterations, 0),
            ("global_population_size", self.global_population_size, 1),
            ("local_max_evaluations", self.local_max_evaluations, 1),
            ("cache_decimals", self.cache_decimals, 0),
        )
        for name, value, minimum in integer_fields:
            if isinstance(value, bool) or int(value) != value or int(value) < minimum:
                raise InverseSolverValidationError(
                    f"{name} must be an integer >= {minimum}."
                )
            object.__setattr__(self, name, int(value))
        if self.expected_rigid_body_modes is not None and (
            isinstance(self.expected_rigid_body_modes, bool)
            or int(self.expected_rigid_body_modes) != self.expected_rigid_body_modes
            or int(self.expected_rigid_body_modes) < 0
        ):
            raise InverseSolverValidationError(
                "expected_rigid_body_modes must be a non-negative integer."
            )
        if self.expected_rigid_body_modes is not None:
            object.__setattr__(
                self, "expected_rigid_body_modes", int(self.expected_rigid_body_modes)
            )
        object.__setattr__(self, "tracking_mode", ModeTrackingMode(self.tracking_mode))
        for name in (
            "global_tolerance",
            "global_absolute_tolerance",
            "local_xtol",
            "local_ftol",
            "local_gtol",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise InverseSolverValidationError(f"{name} must be positive and finite.")
            object.__setattr__(self, name, value)
        weights = {str(key): float(value) for key, value in self.downweighted_observation_weights.items()}
        for value in weights.values():
            if not math.isfinite(value) or not 0.0 < value < 1.0:
                raise InverseSolverValidationError(
                    "Every explicit downweighted-observation weight must satisfy 0 < w < 1."
                )
        object.__setattr__(self, "downweighted_observation_weights", weights)


@dataclass(frozen=True)
class InverseIdentificationResult:
    fitted_parameters: Mapping[str, float]
    fixed_parameters: Mapping[str, float]
    transformed_parameters: Mapping[str, float]
    initial_parameters: Mapping[str, float]
    objective_initial: float
    objective_global: float
    objective_final: float
    residuals_initial: np.ndarray
    residuals_final: np.ndarray
    predicted_frequencies_initial: np.ndarray
    predicted_frequencies_final: np.ndarray
    experimental_frequencies: np.ndarray
    observation_ids: Tuple[str, ...]
    global_evaluations: int
    global_optimizer_evaluations: int
    local_iterations: int
    convergence_history: Tuple[OptimizationHistoryEntry, ...]
    pairing_changed_at_optimum: bool
    initial_pairing: PairingResult
    global_pairing: PairingResult
    final_pairing: PairingResult
    excluded_observations: Tuple[ExcludedSolverObservation, ...]
    warnings: Tuple[str, ...]
    identifiability_metadata_reference: str | None
    weighting_mode: str
    global_success: bool
    global_message: str
    local_success: bool
    local_message: str
    success: bool


@dataclass(frozen=True)
class _CandidateEvaluation:
    parameters: StageAMatrixParameters
    eigenpairs: GeneralizedEigenResult
    pairing: PairingResult
    predicted_frequencies: np.ndarray
    residuals: np.ndarray
    least_squares_residuals: np.ndarray
    objective: float


def _parameter_mapping(parameters: StageAMatrixParameters) -> dict[str, float]:
    return {
        "D11": parameters.D11,
        "D12": parameters.D12,
        "D66": parameters.D66,
    }


def _normalize_subset(parameter_subset: Sequence[str]) -> Tuple[str, ...]:
    supplied = tuple(str(item).strip() for item in parameter_subset)
    if not supplied:
        raise InverseSolverValidationError("At least one Stage-A parameter must be fitted.")
    if len(set(supplied)) != len(supplied):
        raise InverseSolverValidationError("The fitted parameter subset contains duplicates.")
    unsupported = tuple(item for item in supplied if item not in STAGE_A_PARAMETER_IDS)
    if unsupported:
        raise InverseSolverValidationError(
            f"Unsupported Stage-A fitted parameters: {', '.join(unsupported)}."
        )
    return supplied


def _validate_initial_and_bounds(
    initial: StageAMatrixParameters,
    bounds: StageAParameterBounds,
    subset: Tuple[str, ...],
) -> None:
    ratio = initial.D12 / initial.D11
    values = (("D11", initial.D11, bounds.D11), ("D66", initial.D66, bounds.D66))
    for name, value, interval in values:
        if not interval[0] <= value <= interval[1]:
            raise InverseSolverValidationError(
                f"Initial {name}={value:.12g} lies outside its physical bounds."
            )
    if not bounds.coupling_ratio[0] <= ratio <= bounds.coupling_ratio[1]:
        raise InverseSolverValidationError(
            "The initial D12/D11 coupling ratio lies outside its physical bounds."
        )

    if "D11" in subset and "D12" not in subset:
        endpoint_ratios = tuple(initial.D12 / value for value in bounds.D11)
        if any(
            value < bounds.coupling_ratio[0] or value > bounds.coupling_ratio[1]
            for value in endpoint_ratios
        ):
            raise InverseSolverValidationError(
                "D11 bounds would make fixed D12 violate the coupling-ratio bounds."
            )


def _transformed_vector(
    parameters: StageAMatrixParameters, subset: Tuple[str, ...]
) -> np.ndarray:
    point = parameters.as_parameterization()
    values = {"D11": point.x1, "D12": point.x3, "D66": point.x2}
    return np.asarray([values[item] for item in subset], dtype=float)


def _transformed_bounds(
    bounds: StageAParameterBounds, subset: Tuple[str, ...]
) -> Tuple[Tuple[float, float], ...]:
    transformed = {
        "D11": tuple(math.log(value) for value in bounds.D11),
        "D12": tuple(math.atanh(value) for value in bounds.coupling_ratio),
        "D66": tuple(math.log(value) for value in bounds.D66),
    }
    return tuple(transformed[item] for item in subset)


def _parameters_from_vector(
    vector: Sequence[float],
    subset: Tuple[str, ...],
    initial: StageAMatrixParameters,
) -> StageAMatrixParameters:
    coordinates = dict(zip(subset, (float(item) for item in vector)))
    d11 = math.exp(coordinates["D11"]) if "D11" in coordinates else initial.D11
    d66 = math.exp(coordinates["D66"]) if "D66" in coordinates else initial.D66
    if "D12" in coordinates:
        ratio = math.tanh(coordinates["D12"])
        d12 = ratio * d11
    else:
        d12 = initial.D12
        ratio = d12 / d11
    point = StageAParameterization.from_physical(d11, d66, ratio)
    return StageAMatrixParameters.from_parameterization(point)


def _prepare_observations(
    observations: Sequence[ModalObservation | ModalCluster],
    configuration: InverseSolverConfiguration,
) -> tuple[
    Tuple[ModalObservation, ...],
    np.ndarray,
    Tuple[ExcludedSolverObservation, ...],
]:
    supplied = tuple(observations)
    cluster_members: dict[str, str] = {}
    excluded: list[ExcludedSolverObservation] = []
    seen_cluster_ids: set[str] = set()
    for item in supplied:
        if isinstance(item, ModalCluster):
            if item.cluster_id in seen_cluster_ids:
                raise InverseSolverValidationError("Modal cluster IDs must be unique.")
            seen_cluster_ids.add(item.cluster_id)
            for member in item.observation_ids:
                if member in cluster_members:
                    raise InverseSolverValidationError(
                        "A modal observation cannot belong to multiple clusters."
                    )
                cluster_members[member] = item.cluster_id
            excluded.append(
                ExcludedSolverObservation(
                    item.cluster_id,
                    "cluster_requires_subspace_solver",
                    "Near-degenerate clusters are excluded until block/subspace fitting is implemented.",
                )
            )
        elif not isinstance(item, ModalObservation):
            raise TypeError("observations must contain ModalObservation or ModalCluster values.")

    fitted: list[ModalObservation] = []
    weights: list[float] = []
    seen_observation_ids: set[str] = set()
    downweighted_ids: set[str] = set()
    for item in supplied:
        if not isinstance(item, ModalObservation):
            continue
        if item.observation_id in seen_observation_ids:
            raise InverseSolverValidationError("Modal observation IDs must be unique.")
        seen_observation_ids.add(item.observation_id)
        if item.observation_id in cluster_members:
            excluded.append(
                ExcludedSolverObservation(
                    item.observation_id,
                    "cluster_member_excluded",
                    f"Member of {cluster_members[item.observation_id]}; not an independent equation.",
                )
            )
            continue
        if item.inclusion_status == InclusionStatus.EXCLUDED:
            excluded.append(
                ExcludedSolverObservation(item.observation_id, "excluded", item.reason)
            )
            continue
        if item.inclusion_status == InclusionStatus.DOWNWEIGHTED:
            downweighted_ids.add(item.observation_id)
            weight = configuration.downweighted_observation_weights.get(item.observation_id)
            if weight is None:
                excluded.append(
                    ExcludedSolverObservation(
                        item.observation_id,
                        "downweighted_without_numerical_weight",
                        "DOWNWEIGHTED observations require an explicit numerical weight.",
                    )
                )
                continue
        else:
            weight = 1.0
        fitted.append(item)
        weights.append(weight)

    unused_weights = set(configuration.downweighted_observation_weights) - downweighted_ids
    if unused_weights:
        raise InverseSolverValidationError(
            "Numerical downweights were supplied for observations not marked DOWNWEIGHTED: "
            + ", ".join(sorted(unused_weights))
        )
    if not fitted:
        raise InverseSolverValidationError("No included modal observations remain for fitting.")
    return tuple(fitted), np.asarray(weights, dtype=float), tuple(excluded)


def _build_whitener(
    observation_count: int,
    *,
    standard_deviations: Sequence[float] | None,
    covariance: np.ndarray | None,
    allow_unweighted: bool,
) -> tuple[np.ndarray, str]:
    supplied = int(standard_deviations is not None) + int(covariance is not None)
    if supplied > 1:
        raise InverseSolverValidationError(
            "Supply observation_standard_deviations or observation_covariance, not both."
        )
    if supplied == 0:
        if not allow_unweighted:
            raise InverseSolverValidationError(
                "Observation uncertainty is missing; explicitly enable unweighted mode."
            )
        return np.eye(observation_count), "unweighted"
    if standard_deviations is not None:
        sigmas = np.asarray(standard_deviations, dtype=float)
        if sigmas.shape != (observation_count,):
            raise InverseSolverValidationError(
                "There must be one standard deviation per fitting observation."
            )
        if not np.isfinite(sigmas).all() or np.any(sigmas <= 0.0):
            raise InverseSolverValidationError(
                "Observation standard deviations must be positive and finite."
            )
        return np.diag(1.0 / sigmas), "diagonal_standard_deviations"

    covariance_matrix = np.asarray(covariance, dtype=float)
    if covariance_matrix.shape != (observation_count, observation_count):
        raise InverseSolverValidationError(
            "Observation covariance must be square with one row per fitting observation."
        )
    if not np.isfinite(covariance_matrix).all():
        raise InverseSolverValidationError("Observation covariance must be finite.")
    if not np.allclose(covariance_matrix, covariance_matrix.T, rtol=1.0e-10, atol=1.0e-12):
        raise InverseSolverValidationError("Observation covariance must be symmetric.")
    try:
        factor = np.linalg.cholesky(covariance_matrix)
    except np.linalg.LinAlgError as exc:
        raise InverseSolverValidationError(
            "Observation covariance must be positive definite."
        ) from exc
    diagonal = np.diag(np.diag(covariance_matrix))
    mode = (
        "diagonal_covariance"
        if np.allclose(covariance_matrix, diagonal, rtol=1.0e-10, atol=1.0e-12)
        else "full_covariance"
    )
    return np.linalg.inv(factor), mode


def _validate_identifiability(
    subset: Tuple[str, ...],
    identifiability: IdentifiabilityResult | None,
    allow_override: bool,
) -> Tuple[str, ...]:
    if identifiability is None:
        return ()
    if not set(subset).issubset(set(identifiability.parameter_ids)):
        raise InverseSolverValidationError(
            "The requested fitted subset is absent from the identifiability result."
        )
    subset_set = set(subset)
    if subset_set == set(identifiability.parameter_ids):
        admissible = identifiability.practically_identifiable
    else:
        diagnostic = next(
            (
                item
                for item in identifiability.subset_ranking
                if set(item.parameter_ids) == subset_set
            ),
            None,
        )
        admissible = diagnostic is not None and diagnostic.admissible
    if admissible:
        return ()
    message = (
        "The requested fitted parameter subset was not marked practically identifiable."
    )
    if not allow_override:
        raise InverseSolverValidationError(message + " Use an explicit override to proceed.")
    return (message + " Explicit override accepted.",)


def _mass_mac_matrix(
    reference: GeneralizedEigenResult,
    candidate: GeneralizedEigenResult,
    basis: StageAAffineBasis,
) -> np.ndarray:
    if reference.dofs != candidate.dofs:
        raise MatrixModelError("Same-grid MAC requires identical active DOF ordering.")
    if reference.dofs is None or reference.dofs == basis.dofs:
        mass = basis.mass
    else:
        by_dof = {dof: index for index, dof in enumerate(basis.dofs)}
        indexes = [by_dof[dof] for dof in reference.dofs]
        mass = basis.mass[indexes][:, indexes]
    left = np.asarray(reference.eigenvectors, dtype=float)
    right = np.asarray(candidate.eigenvectors, dtype=float)
    cross = left.T @ (mass @ right)
    left_norm = np.sum(left * (mass @ left), axis=0)
    right_norm = np.sum(right * (mass @ right), axis=0)
    denominator = left_norm[:, np.newaxis] * right_norm[np.newaxis, :]
    if np.any(denominator <= 0.0):
        raise MatrixModelError("Same-grid MAC encountered a non-positive modal mass.")
    return np.clip(np.abs(cross) ** 2 / denominator, 0.0, 1.0)


def _synthetic_pairing(
    observations: Tuple[ModalObservation, ...],
    reference: GeneralizedEigenResult,
    candidate: GeneralizedEigenResult,
    basis: StageAAffineBasis,
) -> PairingResult:
    mac = _mass_mac_matrix(reference, candidate, basis)
    reference_indexes, candidate_indexes = optimize.linear_sum_assignment(-mac)
    tracked = {
        int(reference_index) + 1: (int(candidate_index) + 1, float(mac[reference_index, candidate_index]))
        for reference_index, candidate_index in zip(reference_indexes, candidate_indexes)
    }
    assignments = tuple(
        ModeAssignment(
            observation_id=item.observation_id,
            fe_mode_id=tracked[item.fe_mode_id][0],
            tracking_mac=tracked[item.fe_mode_id][1],
        )
        for item in observations
    )
    warnings = ()
    if any(item.fe_mode_id != assignment.fe_mode_id for item, assignment in zip(observations, assignments)):
        warnings = ("Same-grid MAC detected FE eigenvalue-order reordering.",)
    return PairingResult(
        assignments=assignments,
        method="fixed experimental pair with same-grid FE MAC identity tracking",
        warnings=warnings,
    )


def _validated_pairing(
    result: PairingResult,
    observations: Tuple[ModalObservation, ...],
    mode_count: int,
) -> PairingResult:
    if not isinstance(result, PairingResult):
        raise InverseSolverValidationError(
            "A comparison-backed pairing provider must return PairingResult."
        )
    expected = {item.observation_id for item in observations}
    actual = {item.observation_id for item in result.assignments}
    if actual != expected:
        raise InverseSolverValidationError(
            "Comparison-backed pairing must assign every fitting observation exactly once."
        )
    if any(item.fe_mode_id > mode_count for item in result.assignments):
        raise InverseSolverValidationError(
            "Comparison-backed pairing selected an FE mode outside the computed spectrum."
        )
    return result


def _predicted_frequencies(
    pairing: PairingResult,
    observations: Tuple[ModalObservation, ...],
    eigenpairs: GeneralizedEigenResult,
) -> np.ndarray:
    by_id = {item.observation_id: item.fe_mode_id for item in pairing.assignments}
    return np.asarray(
        [eigenpairs.frequencies_hz[by_id[item.observation_id] - 1] for item in observations],
        dtype=float,
    )


def _prior_residuals(
    parameters: StageAMatrixParameters,
    priors: Mapping[str, ParameterPrior],
) -> np.ndarray:
    values = _parameter_mapping(parameters)
    return np.asarray(
        [(values[name] - prior.mean) / prior.standard_uncertainty for name, prior in priors.items()],
        dtype=float,
    )


def _reduce_to_eigen_dofs(
    basis: StageAAffineBasis,
    eigenpairs: GeneralizedEigenResult,
    matrices: Sequence[sparse.spmatrix],
) -> Tuple[sparse.csr_matrix, ...]:
    """Restrict ``matrices`` (basis-DOF ordered) to the solved active DOFs."""

    if eigenpairs.dofs is None or eigenpairs.dofs == basis.dofs:
        return tuple(sparse.csr_matrix(item) for item in matrices)
    by_dof = {dof: index for index, dof in enumerate(basis.dofs)}
    indexes = [by_dof[dof] for dof in eigenpairs.dofs]
    return tuple(sparse.csr_matrix(item)[indexes][:, indexes].tocsr() for item in matrices)


def _analytic_local_jacobian(
    vector: np.ndarray,
    evaluation: _CandidateEvaluation,
    subset: Tuple[str, ...],
    basis: StageAAffineBasis,
    observations: Tuple[ModalObservation, ...],
    whitener: np.ndarray,
    square_root_weights: np.ndarray,
    priors: Mapping[str, ParameterPrior],
) -> np.ndarray:
    del vector
    parameters = evaluation.parameters
    point = parameters.as_parameterization()
    affine = basis.basis_matrices
    derivatives = (
        sparse.csr_matrix(affine[0] + point.r * affine[1]),
        sparse.csr_matrix(affine[2]),
        sparse.csr_matrix(point.D * affine[1]),
    )
    coordinates = (
        ParameterSensitivityCoordinate("D", "physical D at fixed D66,r", point.D, "relative"),
        ParameterSensitivityCoordinate("D66", "physical D66 at fixed D,r", point.D66, "relative"),
        ParameterSensitivityCoordinate("r", "signed ratio at fixed D,D66", 1.0, "characteristic_ratio"),
    )
    mass_point = basis.reconstruct_mass(parameters)
    if basis.mass_derivative_D11 is None:
        mass, *derivatives = _reduce_to_eigen_dofs(
            basis, evaluation.eigenpairs, (mass_point, *derivatives)
        )
        mass_derivatives = None
    else:
        mass, *rest = _reduce_to_eigen_dofs(
            basis,
            evaluation.eigenpairs,
            (mass_point, *derivatives, basis.mass_derivative_D11),
        )
        derivatives = rest[:-1]
        mass_derivatives = (rest[-1], None, None)
    sensitivity = generalized_eigen_sensitivity(
        evaluation.eigenpairs,
        mass,
        derivatives,
        coordinates,
        mass_derivatives=mass_derivatives,
        coordinate_system=StageASensitivityCoordinate.BALANCED,
    )
    paired_modes = {
        item.observation_id: item.fe_mode_id for item in evaluation.pairing.assignments
    }
    mode_indexes = np.asarray(
        [paired_modes[item.observation_id] - 1 for item in observations], dtype=int
    )
    raw = sensitivity.raw_derivatives[mode_indexes]
    frequencies = evaluation.predicted_frequencies
    modal_columns: list[np.ndarray] = []
    for name in subset:
        if name == "D11":
            column = point.D * raw[:, 0]
            if "D12" not in subset:
                column = column - point.r * raw[:, 2]
        elif name == "D12":
            column = (1.0 - point.r**2) * raw[:, 2]
        else:
            column = point.D66 * raw[:, 1]
        modal_columns.append(column / frequencies)
    modal_jacobian = np.column_stack(modal_columns)
    weighted_modal_jacobian = whitener @ (
        square_root_weights[:, np.newaxis] * modal_jacobian
    )

    if not priors:
        return weighted_modal_jacobian
    physical_derivatives = np.zeros((len(priors), len(subset)), dtype=float)
    prior_names = tuple(priors)
    prior_indexes = {name: index for index, name in enumerate(prior_names)}
    for column_index, selected_name in enumerate(subset):
        if selected_name == "D11":
            if "D11" in priors:
                physical_derivatives[prior_indexes["D11"], column_index] = point.D
            if "D12" in priors and "D12" in subset:
                physical_derivatives[prior_indexes["D12"], column_index] = parameters.D12
        elif selected_name == "D12" and "D12" in priors:
            physical_derivatives[prior_indexes["D12"], column_index] = point.D * (1.0 - point.r**2)
        elif selected_name == "D66" and "D66" in priors:
            physical_derivatives[prior_indexes["D66"], column_index] = point.D66
    prior_sigmas = np.asarray(
        [item.standard_uncertainty for item in priors.values()], dtype=float
    )
    return np.vstack((weighted_modal_jacobian, physical_derivatives / prior_sigmas[:, np.newaxis]))


def solve_stage_a_inverse(
    affine_model: StageAAffineBasis,
    observations: Sequence[ModalObservation | ModalCluster],
    parameter_subset: Sequence[str],
    initial_parameters: StageAMatrixParameters,
    parameter_bounds: StageAParameterBounds,
    configuration: InverseSolverConfiguration,
    *,
    observation_standard_deviations: Sequence[float] | None = None,
    observation_covariance: np.ndarray | None = None,
    priors: Mapping[str, ParameterPrior] | None = None,
    identifiability: IdentifiabilityResult | None = None,
    identifiability_metadata_reference: str | None = None,
    comparison_pairing_provider: ComparisonPairingProvider | None = None,
) -> InverseIdentificationResult:
    """Estimate an explicitly selected Stage-A parameter subset.

    Standard deviations and covariance are in the dimensionless log-frequency
    residual domain.  Omitting both is an error unless ``allow_unweighted`` was
    explicitly selected in ``configuration``.
    """

    if not isinstance(affine_model, StageAAffineBasis):
        raise TypeError("affine_model must be StageAAffineBasis.")
    if not isinstance(initial_parameters, StageAMatrixParameters):
        raise TypeError("initial_parameters must be StageAMatrixParameters.")
    if not isinstance(parameter_bounds, StageAParameterBounds):
        raise TypeError("parameter_bounds must be StageAParameterBounds.")
    if not isinstance(configuration, InverseSolverConfiguration):
        raise TypeError("configuration must be InverseSolverConfiguration.")

    subset = _normalize_subset(parameter_subset)
    _validate_initial_and_bounds(initial_parameters, parameter_bounds, subset)
    fitted_observations, observation_weights, excluded = _prepare_observations(
        observations, configuration
    )
    if configuration.mode_count <= len(fitted_observations):
        raise InverseSolverValidationError(
            "mode_count must exceed the number of fitting observations for tracking headroom."
        )
    if max(item.fe_mode_id for item in fitted_observations) > configuration.mode_count:
        raise InverseSolverValidationError(
            "mode_count does not include every initially paired FE mode."
        )
    if (
        configuration.tracking_mode == ModeTrackingMode.COMPARISON_BACKED
        and comparison_pairing_provider is None
    ):
        raise InverseSolverValidationError(
            "Comparison-backed tracking requires comparison_pairing_provider."
        )
    if (
        configuration.tracking_mode == ModeTrackingMode.FIXED_PAIR_SYNTHETIC
        and comparison_pairing_provider is not None
    ):
        raise InverseSolverValidationError(
            "A comparison pairing provider is incompatible with fixed-pair synthetic mode."
        )

    warnings = list(
        _validate_identifiability(
            subset, identifiability, configuration.allow_non_identifiable_subset
        )
    )
    whitener, weighting_mode = _build_whitener(
        len(fitted_observations),
        standard_deviations=observation_standard_deviations,
        covariance=observation_covariance,
        allow_unweighted=configuration.allow_unweighted,
    )
    square_root_weights = np.sqrt(observation_weights)
    experimental = np.asarray(
        [item.experimental_frequency_hz for item in fitted_observations], dtype=float
    )
    normalized_priors = dict(priors or {})
    unsupported_priors = set(normalized_priors) - set(STAGE_A_PARAMETER_IDS)
    if unsupported_priors or not all(
        isinstance(item, ParameterPrior) for item in normalized_priors.values()
    ):
        raise InverseSolverValidationError(
            "Priors must map Stage-A parameter IDs to ParameterPrior values."
        )
    if any(item.distribution.lower() != "normal" for item in normalized_priors.values()):
        raise InverseSolverValidationError(
            "Only explicit normal priors are compatible with the least-squares objective."
        )

    initial_vector = _transformed_vector(initial_parameters, subset)
    transformed_bounds = _transformed_bounds(parameter_bounds, subset)
    tracking_reference_eigenpairs = solve_generalized_eigenproblem(
        affine_model.reference_stiffness,
        affine_model.mass,
        configuration.mode_count,
        expected_rigid_body_modes=configuration.expected_rigid_body_modes,
        dofs=affine_model.dofs,
    )

    def dynamic_pairing(eigenpairs: GeneralizedEigenResult) -> PairingResult:
        if configuration.tracking_mode == ModeTrackingMode.FIXED_PAIR_SYNTHETIC:
            return _synthetic_pairing(
                fitted_observations,
                tracking_reference_eigenpairs,
                eigenpairs,
                affine_model,
            )
        assert comparison_pairing_provider is not None
        return _validated_pairing(
            comparison_pairing_provider(fitted_observations, eigenpairs),
            fitted_observations,
            configuration.mode_count,
        )

    def evaluate(
        vector: Sequence[float], pairing: PairingResult | None = None
    ) -> _CandidateEvaluation:
        parameters = _parameters_from_vector(vector, subset, initial_parameters)
        eigenpairs = solve_generalized_eigenproblem(
            affine_model.reconstruct_stiffness(parameters),
            affine_model.reconstruct_mass(parameters),
            configuration.mode_count,
            expected_rigid_body_modes=configuration.expected_rigid_body_modes,
            dofs=affine_model.dofs,
        )
        selected_pairing = dynamic_pairing(eigenpairs) if pairing is None else pairing
        predicted = _predicted_frequencies(
            selected_pairing, fitted_observations, eigenpairs
        )
        residuals = np.log(predicted / experimental)
        weighted = whitener @ (square_root_weights * residuals)
        prior_residuals = _prior_residuals(parameters, normalized_priors)
        least_squares_residuals = np.concatenate((weighted, prior_residuals))
        objective = float(least_squares_residuals @ least_squares_residuals)
        if not math.isfinite(objective):
            raise MatrixModelError("The Stage-A objective is non-finite.")
        return _CandidateEvaluation(
            parameters=parameters,
            eigenpairs=eigenpairs,
            pairing=selected_pairing,
            predicted_frequencies=predicted,
            residuals=residuals,
            least_squares_residuals=least_squares_residuals,
            objective=objective,
        )

    initial_evaluation = evaluate(initial_vector)
    history: list[OptimizationHistoryEntry] = [
        OptimizationHistoryEntry(
            stage="initial",
            evaluation=0,
            transformed_parameters=tuple(float(item) for item in initial_vector),
            physical_parameters=_parameter_mapping(initial_parameters),
            objective=initial_evaluation.objective,
            success=True,
            pairing_signature=initial_evaluation.pairing.signature,
        )
    ]
    cache: dict[Tuple[float, ...], _CandidateEvaluation | str] = {}
    global_evaluation_count = 0
    best_evaluation = initial_evaluation
    best_vector = initial_vector.copy()

    def global_objective(vector: np.ndarray) -> float:
        nonlocal global_evaluation_count, best_evaluation, best_vector
        key = tuple(round(float(item), configuration.cache_decimals) for item in vector)
        cached = cache.get(key)
        if isinstance(cached, _CandidateEvaluation):
            return cached.objective
        if isinstance(cached, str):
            return _FAILED_OBJECTIVE
        global_evaluation_count += 1
        try:
            candidate = evaluate(vector)
        except (ValueError, MatrixModelError, np.linalg.LinAlgError) as exc:
            cache[key] = str(exc)
            history.append(
                OptimizationHistoryEntry(
                    stage="global",
                    evaluation=global_evaluation_count,
                    transformed_parameters=tuple(float(item) for item in vector),
                    physical_parameters=_parameter_mapping(
                        _parameters_from_vector(vector, subset, initial_parameters)
                    ),
                    objective=_FAILED_OBJECTIVE,
                    success=False,
                    message=str(exc),
                )
            )
            return _FAILED_OBJECTIVE
        cache[key] = candidate
        if candidate.objective < best_evaluation.objective:
            best_evaluation = candidate
            best_vector = np.asarray(vector, dtype=float).copy()
        history.append(
            OptimizationHistoryEntry(
                stage="global",
                evaluation=global_evaluation_count,
                transformed_parameters=tuple(float(item) for item in vector),
                physical_parameters=_parameter_mapping(candidate.parameters),
                objective=candidate.objective,
                success=True,
                pairing_signature=candidate.pairing.signature,
            )
        )
        return candidate.objective

    global_success = False
    global_message = ""
    global_optimizer_evaluations = 0
    try:
        global_result = optimize.differential_evolution(
            global_objective,
            transformed_bounds,
            seed=configuration.random_seed,
            maxiter=configuration.global_max_iterations,
            popsize=configuration.global_population_size,
            tol=configuration.global_tolerance,
            atol=configuration.global_absolute_tolerance,
            polish=False,
            workers=1,
            updating="immediate",
        )
        global_optimizer_evaluations = int(global_result.nfev)
        global_success = bool(global_result.success)
        global_message = str(global_result.message)
        try:
            result_evaluation = evaluate(global_result.x)
        except (ValueError, MatrixModelError, np.linalg.LinAlgError):
            result_evaluation = best_evaluation
        if result_evaluation.objective <= best_evaluation.objective:
            best_evaluation = result_evaluation
            best_vector = np.asarray(global_result.x, dtype=float).copy()
    except (RuntimeError, ValueError, FloatingPointError) as exc:
        global_message = f"differential_evolution failed: {exc}"
    if not global_success:
        warnings.append(global_message or "differential_evolution did not converge.")

    global_evaluation = best_evaluation
    frozen_pairing = global_evaluation.pairing
    local_evaluation_count = 0
    latest_local_evaluation = global_evaluation

    def local_residual(vector: np.ndarray) -> np.ndarray:
        nonlocal local_evaluation_count, latest_local_evaluation
        local_evaluation_count += 1
        try:
            latest_local_evaluation = evaluate(vector, frozen_pairing)
            history.append(
                OptimizationHistoryEntry(
                    stage="local",
                    evaluation=local_evaluation_count,
                    transformed_parameters=tuple(float(item) for item in vector),
                    physical_parameters=_parameter_mapping(latest_local_evaluation.parameters),
                    objective=latest_local_evaluation.objective,
                    success=True,
                    pairing_signature=frozen_pairing.signature,
                )
            )
            return latest_local_evaluation.least_squares_residuals
        except (ValueError, MatrixModelError, np.linalg.LinAlgError) as exc:
            history.append(
                OptimizationHistoryEntry(
                    stage="local",
                    evaluation=local_evaluation_count,
                    transformed_parameters=tuple(float(item) for item in vector),
                    physical_parameters=_parameter_mapping(
                        _parameters_from_vector(vector, subset, initial_parameters)
                    ),
                    objective=_FAILED_OBJECTIVE,
                    success=False,
                    pairing_signature=frozen_pairing.signature,
                    message=str(exc),
                )
            )
            return np.full(
                len(fitted_observations) + len(normalized_priors), 1.0e50, dtype=float
            )

    def local_jacobian(vector: np.ndarray) -> np.ndarray:
        candidate = evaluate(vector, frozen_pairing)
        return _analytic_local_jacobian(
            vector,
            candidate,
            subset,
            affine_model,
            fitted_observations,
            whitener,
            square_root_weights,
            normalized_priors,
        )

    lower = np.asarray([item[0] for item in transformed_bounds], dtype=float)
    upper = np.asarray([item[1] for item in transformed_bounds], dtype=float)
    try:
        local_result = optimize.least_squares(
            local_residual,
            best_vector,
            jac=local_jacobian,
            bounds=(lower, upper),
            method="trf",
            max_nfev=configuration.local_max_evaluations,
            xtol=configuration.local_xtol,
            ftol=configuration.local_ftol,
            gtol=configuration.local_gtol,
        )
        local_success = bool(local_result.success)
        local_message = str(local_result.message)
        local_iterations = int(local_result.nfev)
        local_frozen_evaluation = evaluate(local_result.x, frozen_pairing)
        final_vector = np.asarray(local_result.x, dtype=float)
    except (RuntimeError, ValueError, FloatingPointError, MatrixModelError) as exc:
        local_success = False
        local_message = f"least_squares failed: {exc}"
        local_iterations = local_evaluation_count
        local_frozen_evaluation = global_evaluation
        final_vector = best_vector
    if not local_success:
        warnings.append(local_message or "least_squares did not converge.")

    final_evaluation = evaluate(final_vector)
    pairing_changed = final_evaluation.pairing.signature != frozen_pairing.signature
    if pairing_changed:
        warnings.append(
            "Pairing changed at the local optimum; repeat the global/local cycle or review manually."
        )
    warnings.extend(final_evaluation.pairing.warnings)
    final_parameters = final_evaluation.parameters
    final_values = _parameter_mapping(final_parameters)
    transformed_point = final_parameters.as_parameterization()
    transformed_mapping = {
        "x1_log_D11": transformed_point.x1,
        "x2_log_D66": transformed_point.x2,
        "x3_atanh_D12_over_D11": transformed_point.x3,
    }
    fitted_values = {name: final_values[name] for name in subset}
    fixed_values = {
        name: final_values[name] for name in STAGE_A_PARAMETER_IDS if name not in subset
    }
    del local_frozen_evaluation
    return InverseIdentificationResult(
        fitted_parameters=fitted_values,
        fixed_parameters=fixed_values,
        transformed_parameters=transformed_mapping,
        initial_parameters=_parameter_mapping(initial_parameters),
        objective_initial=initial_evaluation.objective,
        objective_global=global_evaluation.objective,
        objective_final=final_evaluation.objective,
        residuals_initial=initial_evaluation.residuals.copy(),
        residuals_final=final_evaluation.residuals.copy(),
        predicted_frequencies_initial=initial_evaluation.predicted_frequencies.copy(),
        predicted_frequencies_final=final_evaluation.predicted_frequencies.copy(),
        experimental_frequencies=experimental.copy(),
        observation_ids=tuple(item.observation_id for item in fitted_observations),
        global_evaluations=global_evaluation_count,
        global_optimizer_evaluations=global_optimizer_evaluations,
        local_iterations=local_iterations,
        convergence_history=tuple(history),
        pairing_changed_at_optimum=pairing_changed,
        initial_pairing=initial_evaluation.pairing,
        global_pairing=global_evaluation.pairing,
        final_pairing=final_evaluation.pairing,
        excluded_observations=excluded,
        warnings=tuple(dict.fromkeys(item for item in warnings if item)),
        identifiability_metadata_reference=identifiability_metadata_reference,
        weighting_mode=weighting_mode,
        global_success=global_success,
        global_message=global_message,
        local_success=local_success,
        local_message=local_message,
        success=bool(global_success and local_success and not pairing_changed),
    )


__all__ = [
    "ComparisonPairingProvider",
    "ExcludedSolverObservation",
    "InverseIdentificationResult",
    "InverseSolverConfiguration",
    "InverseSolverValidationError",
    "ModeAssignment",
    "ModeTrackingMode",
    "OptimizationHistoryEntry",
    "PairingResult",
    "StageAParameterBounds",
    "solve_stage_a_inverse",
]
