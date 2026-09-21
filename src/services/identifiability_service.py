"""Whitening, Fisher/SVD diagnostics, and small-subset identifiability search."""

from __future__ import annotations

from dataclasses import dataclass, field
import itertools
import math
from typing import Any, Mapping, Sequence, Tuple

import numpy as np

from domain.modal_observation import ModalCluster, ModalObservation, ObservationUncertainty

from .sensitivity_service import SensitivityResult


INDEPENDENT_COMPONENT_ASSUMPTION = (
    "measurement, setup, and manufacturing variance components are independent; "
    "combined variance is their sum"
)


@dataclass(frozen=True)
class WhiteningResult:
    sensitivity: np.ndarray
    covariance: np.ndarray | None
    standard_deviations: np.ndarray | None
    observation_ids: Tuple[str, ...]
    parameter_ids: Tuple[str, ...]
    mode: str
    uncertainty_components: Tuple[ObservationUncertainty, ...] = ()
    assumptions: Tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CollinearityResult:
    parameter_ids: Tuple[str, ...]
    gamma: float
    minimum_eigenvalue: float
    warning: bool
    normalization: str = "unit_l2_sensitivity_columns"


@dataclass(frozen=True)
class DeficientDirection:
    singular_value: float
    coefficients: np.ndarray
    parameter_loadings: Mapping[str, float]
    dominant_parameter: str
    dominant_loading: float
    numerical_null_direction: bool


@dataclass(frozen=True)
class SubsetIdentifiability:
    parameter_ids: Tuple[str, ...]
    singular_values: np.ndarray
    rank: int
    condition_number: float
    collinearity: CollinearityResult
    minimum_singular_value: float
    normalized_minimum_singular_value: float
    admissible: bool


@dataclass(frozen=True)
class ParameterPrecisionRequirement:
    """Campaign-specific acceptable one-sigma uncertainty for one parameter.

    ``coordinate`` deliberately names the quantity being gated.  In
    particular, a signed parameter such as D12 can use an absolute physical
    threshold or a scaled threshold based on a separately declared D scale;
    its estimate is never used as a relative-uncertainty denominator.
    """

    maximum_standard_deviation: float
    coordinate: str = "physical"
    reference_scale: float | None = None
    rationale: str = ""

    def __post_init__(self) -> None:
        maximum = float(self.maximum_standard_deviation)
        if not math.isfinite(maximum) or maximum <= 0.0:
            raise ValueError("maximum_standard_deviation must be positive and finite.")
        coordinate = str(self.coordinate).strip().lower()
        if coordinate not in {"scaled", "transformed", "physical"}:
            raise ValueError("precision coordinate must be scaled, transformed, or physical.")
        reference = self.reference_scale
        if reference is not None:
            reference = float(reference)
            if not math.isfinite(reference) or reference <= 0.0:
                raise ValueError("reference_scale must be positive and finite when supplied.")
        object.__setattr__(self, "maximum_standard_deviation", maximum)
        object.__setattr__(self, "coordinate", coordinate)
        object.__setattr__(self, "reference_scale", reference)
        object.__setattr__(self, "rationale", str(self.rationale))


@dataclass(frozen=True)
class ParameterPrecisionAssessment:
    parameter_id: str
    observability_status: str
    observable_fraction: float
    scaled_standard_deviation: float
    transformed_coordinate: str
    transformed_standard_deviation: float
    physical_standard_deviation: float
    requirement_coordinate: str | None
    maximum_standard_deviation: float | None
    reference_scale: float | None
    achieved_fraction_of_reference: float | None
    status: str
    reason: str


@dataclass(frozen=True)
class IdentifiabilityResult:
    parameter_ids: Tuple[str, ...]
    singular_values: np.ndarray
    rank: int
    numerical_rank_tolerance: float
    condition_number: float
    right_singular_vectors: np.ndarray
    fisher_information: np.ndarray
    covariance_proxy: np.ndarray
    correlation_matrix: np.ndarray
    collinearity: CollinearityResult
    deficient_directions: Tuple[DeficientDirection, ...]
    best_identifiable_subset: SubsetIdentifiability | None
    subset_ranking: Tuple[SubsetIdentifiability, ...]
    structurally_identifiable: bool
    directionally_separable: bool
    practically_precise_enough: bool | None
    overall_practical_identifiability: bool
    practically_identifiable: bool
    precision_status: str
    precision_assessments: Tuple[ParameterPrecisionAssessment, ...]
    scaled_standard_deviations: np.ndarray
    transformed_coordinate_ids: Tuple[str, ...]
    transformed_standard_deviations: np.ndarray
    physical_standard_deviations: np.ndarray
    observable_projector: np.ndarray
    nullspace_basis: np.ndarray
    parameter_observability: Mapping[str, str]
    warnings: Tuple[str, ...]
    weighting_mode: str


def _matrix(value: object, name: str) -> np.ndarray:
    matrix = np.asarray(value, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ValueError(f"{name} must be a non-empty two-dimensional matrix.")
    if not np.isfinite(matrix).all():
        raise ValueError(f"{name} must contain only finite values.")
    return matrix


def _identifiers(
    supplied: Sequence[str] | None,
    count: int,
    prefix: str,
) -> Tuple[str, ...]:
    if supplied is None:
        return tuple(f"{prefix}_{index + 1}" for index in range(count))
    identifiers = tuple(str(item).strip() for item in supplied)
    if len(identifiers) != count or any(not item for item in identifiers):
        raise ValueError(f"Exactly {count} non-empty {prefix} identifiers are required.")
    if len(set(identifiers)) != len(identifiers):
        raise ValueError(f"{prefix.capitalize()} identifiers must be unique.")
    return identifiers


def combine_independent_uncertainties(
    uncertainty_components: Sequence[ObservationUncertainty],
    *,
    observation_scales: Sequence[float] | None = None,
) -> tuple[np.ndarray, Tuple[ObservationUncertainty, ...]]:
    """Combine preserved components under one explicit independence assumption.

    If ``observation_scales`` is supplied, absolute standard uncertainties are
    divided by those scales.  Modal log-frequency sensitivities should use the
    corresponding positive modal frequencies as scales.
    """

    components = tuple(uncertainty_components)
    if not components:
        raise ValueError("At least one observation uncertainty is required.")
    if not all(isinstance(item, ObservationUncertainty) for item in components):
        raise TypeError("uncertainty_components must contain ObservationUncertainty values.")

    standard_deviations = np.empty(len(components), dtype=float)
    for index, item in enumerate(components):
        values = tuple(
            value
            for value in (item.measurement, item.setup, item.manufacturing)
            if value is not None
        )
        if not values:
            raise ValueError(
                f"Observation {index} has no uncertainty; use explicit unweighted mode "
                "or provide uncertainty data."
            )
        variance = float(sum(float(value) ** 2 for value in values))
        if not math.isfinite(variance) or variance <= 0.0:
            raise ValueError(
                f"Observation {index} has zero or invalid combined uncertainty."
            )
        standard_deviations[index] = math.sqrt(variance)

    if observation_scales is not None:
        scales = np.asarray(observation_scales, dtype=float)
        if scales.shape != standard_deviations.shape:
            raise ValueError("observation_scales must match the number of observations.")
        if not np.isfinite(scales).all() or np.any(scales <= 0.0):
            raise ValueError("observation_scales must be positive and finite.")
        standard_deviations = standard_deviations / scales
    return standard_deviations, components


def whiten_sensitivity(
    sensitivity: SensitivityResult | np.ndarray,
    *,
    standard_deviations: Sequence[float] | None = None,
    covariance: np.ndarray | None = None,
    uncertainty_components: Sequence[ObservationUncertainty] | None = None,
    observation_scales: Sequence[float] | None = None,
    observation_ids: Sequence[str] | None = None,
    parameter_ids: Sequence[str] | None = None,
    allow_unweighted: bool = False,
) -> WhiteningResult:
    """Apply diagonal ``Sigma**(-1/2)`` to dimensionless sensitivities.

    Missing uncertainty never selects a numerical default.  Callers must either
    supply positive standard deviations/components or explicitly opt into the
    returned ``unweighted`` mode.
    """

    if isinstance(sensitivity, SensitivityResult):
        matrix = _matrix(sensitivity.scaled_sensitivity, "scaled_sensitivity")
        if observation_ids is not None or parameter_ids is not None:
            raise ValueError("SensitivityResult already supplies observation and parameter IDs.")
        observation_ids = sensitivity.observation_ids
        parameter_ids = sensitivity.parameter_ids
    else:
        matrix = _matrix(sensitivity, "sensitivity")
    row_ids = _identifiers(observation_ids, matrix.shape[0], "observation")
    column_ids = _identifiers(parameter_ids, matrix.shape[1], "parameter")

    supplied_modes = sum(
        item is not None
        for item in (standard_deviations, covariance, uncertainty_components)
    )
    if supplied_modes > 1:
        raise ValueError(
            "Supply exactly one of standard_deviations, covariance, or "
            "uncertainty_components."
        )
    if supplied_modes == 0:
        if not allow_unweighted:
            raise ValueError(
                "Observation uncertainty is missing; set allow_unweighted=True "
                "to select explicit unweighted mode."
            )
        return WhiteningResult(
            sensitivity=matrix.copy(),
            covariance=None,
            standard_deviations=None,
            observation_ids=row_ids,
            parameter_ids=column_ids,
            mode="unweighted",
            metadata={"uncertainty_available": False},
        )

    components: Tuple[ObservationUncertainty, ...] = ()
    assumptions: Tuple[str, ...] = ()
    metadata: dict[str, Any] = {"uncertainty_available": True}
    if covariance is not None:
        if observation_scales is not None:
            raise ValueError(
                "observation_scales are only used when combining uncertainty_components."
            )
        covariance_matrix = np.asarray(covariance, dtype=float)
        if covariance_matrix.shape != (matrix.shape[0], matrix.shape[0]):
            raise ValueError("covariance must be square with one row per observation.")
        if not np.isfinite(covariance_matrix).all():
            raise ValueError("covariance must contain only finite values.")
        if not np.allclose(
            covariance_matrix,
            covariance_matrix.T,
            rtol=1.0e-10,
            atol=1.0e-12,
        ):
            raise ValueError("covariance must be symmetric.")
        eigenvalues, eigenvectors = np.linalg.eigh(covariance_matrix)
        scale = max(float(np.max(np.abs(eigenvalues), initial=0.0)), 1.0)
        positive_tolerance = np.finfo(float).eps * matrix.shape[0] * scale
        if np.any(eigenvalues <= positive_tolerance):
            raise ValueError("covariance must be positive definite for whitening.")
        inverse_square_root = (
            eigenvectors * (1.0 / np.sqrt(eigenvalues))[np.newaxis, :]
        ) @ eigenvectors.T
        sigmas = np.sqrt(np.diag(covariance_matrix))
        diagonal = np.diag(np.diag(covariance_matrix))
        mode = (
            "diagonal_covariance"
            if np.allclose(covariance_matrix, diagonal, rtol=1.0e-10, atol=1.0e-12)
            else "full_covariance"
        )
        metadata["uncertainty_domain"] = "input_residual"
        return WhiteningResult(
            sensitivity=inverse_square_root @ matrix,
            covariance=covariance_matrix.copy(),
            standard_deviations=sigmas,
            observation_ids=row_ids,
            parameter_ids=column_ids,
            mode=mode,
            metadata=metadata,
        )
    if uncertainty_components is not None:
        sigmas, components = combine_independent_uncertainties(
            uncertainty_components, observation_scales=observation_scales
        )
        assumptions = (INDEPENDENT_COMPONENT_ASSUMPTION,)
        metadata["component_variances_combined_as_independent"] = True
        metadata["uncertainty_domain"] = (
            "relative_observation" if observation_scales is not None else "input_residual"
        )
        mode = "diagonal_independent_components"
    else:
        if observation_scales is not None:
            raise ValueError(
                "observation_scales are only used when combining uncertainty_components."
            )
        sigmas = np.asarray(standard_deviations, dtype=float)
        mode = "diagonal_standard_deviations"

    if sigmas.shape != (matrix.shape[0],):
        raise ValueError("There must be one standard deviation per sensitivity row.")
    if not np.isfinite(sigmas).all() or np.any(sigmas <= 0.0):
        raise ValueError("Standard deviations must be positive and finite.")
    covariance_matrix = np.diag(sigmas**2)
    whitened = matrix / sigmas[:, np.newaxis]
    return WhiteningResult(
        sensitivity=whitened,
        covariance=covariance_matrix,
        standard_deviations=sigmas,
        observation_ids=row_ids,
        parameter_ids=column_ids,
        mode=mode,
        uncertainty_components=components,
        assumptions=assumptions,
        metadata=metadata,
    )


def whiten_modal_observation_sensitivity(
    sensitivity: SensitivityResult,
    observations: Sequence[ModalObservation | ModalCluster],
    *,
    allow_unweighted: bool = False,
) -> WhiteningResult:
    """Whiten log-frequency sensitivities from modal observation metadata."""

    observations = tuple(observations)
    if any(isinstance(item, ModalCluster) for item in observations):
        raise ValueError("cluster_requires_subspace_sensitivity")
    if not all(isinstance(item, ModalObservation) for item in observations):
        raise TypeError("observations must contain ModalObservation values.")
    by_id = {item.observation_id: item for item in observations}
    if set(by_id) != set(sensitivity.observation_ids):
        raise ValueError("Modal observations must match the sensitivity observation IDs.")
    ordered = tuple(by_id[item] for item in sensitivity.observation_ids)
    if allow_unweighted and all(
        all(
            value is None
            for value in (
                item.uncertainty.measurement,
                item.uncertainty.setup,
                item.uncertainty.manufacturing,
            )
        )
        for item in ordered
    ):
        return whiten_sensitivity(sensitivity, allow_unweighted=True)
    return whiten_sensitivity(
        sensitivity,
        uncertainty_components=tuple(item.uncertainty for item in ordered),
        observation_scales=tuple(item.experimental_frequency_hz for item in ordered),
    )


def _rank_tolerance(singular_values: np.ndarray, shape: tuple[int, int], rcond: float | None) -> float:
    maximum = float(singular_values[0]) if singular_values.size else 0.0
    if rcond is None:
        return max(shape) * np.finfo(float).eps * maximum
    rcond = float(rcond)
    if not math.isfinite(rcond) or rcond < 0.0:
        raise ValueError("rcond must be finite and non-negative.")
    return rcond * maximum


def _column_normalized(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=0)
    normalized = np.zeros_like(matrix)
    nonzero = norms > 0.0
    normalized[:, nonzero] = matrix[:, nonzero] / norms[nonzero]
    return normalized


def collinearity_index(
    sensitivity: np.ndarray,
    parameter_ids: Sequence[str] | None = None,
    *,
    warning_threshold: float = 20.0,
) -> CollinearityResult:
    """Return Brun's gamma using unit-L2-normalized sensitivity columns.

    The implemented definition is ``gamma_K = 1/sqrt(lambda_min(S_K.T S_K))``.
    It is not mixed with alternative collinearity-index definitions.
    """

    matrix = _matrix(sensitivity, "sensitivity")
    identifiers = _identifiers(parameter_ids, matrix.shape[1], "parameter")
    warning_threshold = float(warning_threshold)
    if not math.isfinite(warning_threshold) or warning_threshold <= 0.0:
        raise ValueError("warning_threshold must be positive and finite.")
    normalized = _column_normalized(matrix)
    gram = normalized.T @ normalized
    eigenvalues = np.linalg.eigvalsh(gram)
    minimum = max(float(eigenvalues[0]), 0.0)
    roundoff_floor = np.finfo(float).eps * max(matrix.shape)
    gamma = math.inf if minimum <= roundoff_floor else 1.0 / math.sqrt(minimum)
    return CollinearityResult(
        parameter_ids=identifiers,
        gamma=gamma,
        minimum_eigenvalue=minimum,
        warning=gamma > warning_threshold,
    )


def _subset_result(
    matrix: np.ndarray,
    parameter_ids: Tuple[str, ...],
    *,
    rcond: float | None,
    condition_warning_threshold: float,
    collinearity_warning_threshold: float,
) -> SubsetIdentifiability:
    singular_values = np.linalg.svd(matrix, compute_uv=False)
    tolerance = _rank_tolerance(singular_values, matrix.shape, rcond)
    rank = int(np.count_nonzero(singular_values > tolerance))
    column_count = matrix.shape[1]
    if rank < column_count or singular_values.size < column_count:
        condition = math.inf
        minimum_singular = 0.0
    else:
        minimum_singular = float(singular_values[column_count - 1])
        condition = (
            math.inf
            if minimum_singular == 0.0
            else float(singular_values[0] / minimum_singular)
        )
    collinearity = collinearity_index(
        matrix, parameter_ids, warning_threshold=collinearity_warning_threshold
    )
    normalized_singular = np.linalg.svd(_column_normalized(matrix), compute_uv=False)
    normalized_minimum = (
        float(normalized_singular[column_count - 1])
        if normalized_singular.size >= column_count
        else 0.0
    )
    admissible = bool(
        rank == column_count
        and condition <= condition_warning_threshold
        and not collinearity.warning
    )
    return SubsetIdentifiability(
        parameter_ids=parameter_ids,
        singular_values=singular_values,
        rank=rank,
        condition_number=condition,
        collinearity=collinearity,
        minimum_singular_value=minimum_singular,
        normalized_minimum_singular_value=normalized_minimum,
        admissible=admissible,
    )


def rank_identifiable_subsets(
    sensitivity: np.ndarray,
    parameter_ids: Sequence[str],
    *,
    rcond: float | None = None,
    condition_warning_threshold: float = 100.0,
    collinearity_warning_threshold: float = 20.0,
) -> Tuple[SubsetIdentifiability, ...]:
    """Exhaustively rank non-empty subsets for the small Stage-A parameter set."""

    matrix = _matrix(sensitivity, "sensitivity")
    identifiers = _identifiers(parameter_ids, matrix.shape[1], "parameter")
    results: list[SubsetIdentifiability] = []
    for subset_size in range(1, len(identifiers) + 1):
        for indexes in itertools.combinations(range(len(identifiers)), subset_size):
            subset_ids = tuple(identifiers[index] for index in indexes)
            results.append(
                _subset_result(
                    matrix[:, indexes],
                    subset_ids,
                    rcond=rcond,
                    condition_warning_threshold=condition_warning_threshold,
                    collinearity_warning_threshold=collinearity_warning_threshold,
                )
            )

    def score(item: SubsetIdentifiability) -> tuple[float, ...]:
        finite_condition = item.condition_number if math.isfinite(item.condition_number) else 1.0e300
        finite_gamma = item.collinearity.gamma if math.isfinite(item.collinearity.gamma) else 1.0e300
        return (
            float(item.admissible),
            float(len(item.parameter_ids)),
            item.normalized_minimum_singular_value,
            item.minimum_singular_value,
            -finite_gamma,
            -finite_condition,
        )

    return tuple(sorted(results, key=score, reverse=True))


def _covariance_from_svd(
    right_singular_vectors: np.ndarray,
    singular_values: np.ndarray,
    tolerance: float,
) -> np.ndarray:
    parameter_count = right_singular_vectors.shape[0]
    inverse_squares = np.zeros(parameter_count, dtype=float)
    retained = singular_values > tolerance
    inverse_squares[: singular_values.size][retained] = 1.0 / singular_values[retained] ** 2
    return (right_singular_vectors * inverse_squares[np.newaxis, :]) @ right_singular_vectors.T


def _correlation_from_covariance(covariance: np.ndarray) -> np.ndarray:
    standard_deviations = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    denominator = np.outer(standard_deviations, standard_deviations)
    correlation = np.zeros_like(covariance)
    np.divide(covariance, denominator, out=correlation, where=denominator > 0.0)
    correlation = np.clip(correlation, -1.0, 1.0)
    np.fill_diagonal(correlation, np.where(standard_deviations > 0.0, 1.0, 0.0))
    return correlation


def _validated_scales(
    parameter_ids: Tuple[str, ...],
    supplied: Mapping[str, float] | None,
) -> np.ndarray:
    if supplied is None:
        return np.ones(len(parameter_ids), dtype=float)
    unknown = set(supplied) - set(parameter_ids)
    if unknown:
        raise ValueError(
            "Physical parameter scales contain unknown IDs: "
            + ", ".join(sorted(unknown))
        )
    missing = set(parameter_ids) - set(supplied)
    if missing:
        raise ValueError(
            "A physical parameter scale is required for: "
            + ", ".join(sorted(missing))
        )
    scales = np.asarray([float(supplied[item]) for item in parameter_ids], dtype=float)
    if not np.isfinite(scales).all() or np.any(scales <= 0.0):
        raise ValueError("Physical parameter scales must be positive and finite.")
    return scales


def _validated_transformation(
    parameter_count: int,
    supplied: np.ndarray | None,
) -> np.ndarray:
    if supplied is None:
        return np.eye(parameter_count, dtype=float)
    matrix = np.asarray(supplied, dtype=float)
    if matrix.shape != (parameter_count, parameter_count):
        raise ValueError(
            "transformed_coordinate_jacobian must be square with one row per parameter."
        )
    if not np.isfinite(matrix).all():
        raise ValueError("transformed_coordinate_jacobian must be finite.")
    return matrix


def _observability_statuses(
    projector: np.ndarray,
    parameter_ids: Tuple[str, ...],
) -> tuple[Mapping[str, str], np.ndarray]:
    fractions = np.clip(np.diag(projector), 0.0, 1.0)
    tolerance = 100.0 * np.finfo(float).eps * max(projector.shape[0], 1)
    statuses: dict[str, str] = {}
    for identifier, fraction in zip(parameter_ids, fractions):
        if fraction <= tolerance:
            statuses[identifier] = "UNOBSERVABLE"
        elif fraction >= 1.0 - tolerance:
            statuses[identifier] = "OBSERVABLE"
        else:
            statuses[identifier] = "PARTIALLY_OBSERVABLE"
    return statuses, fractions


def analyze_identifiability(
    whitened_sensitivity: WhiteningResult | np.ndarray,
    parameter_ids: Sequence[str] | None = None,
    *,
    dimensionless: bool = False,
    rcond: float | None = None,
    condition_warning_threshold: float = 100.0,
    collinearity_warning_threshold: float = 20.0,
    precision_requirements: Mapping[str, ParameterPrecisionRequirement] | None = None,
    physical_parameter_scales: Mapping[str, float] | None = None,
    transformed_coordinate_ids: Sequence[str] | None = None,
    transformed_coordinate_jacobian: np.ndarray | None = None,
) -> IdentifiabilityResult:
    """Compute stable SVD/Fisher diagnostics and rank Stage-A subsets.

    Plain arrays require ``dimensionless=True`` so derivatives in physical
    stiffness units cannot be passed accidentally.  ``WhiteningResult`` is the
    preferred API and already represents scaled sensitivity rows.
    """

    if isinstance(whitened_sensitivity, WhiteningResult):
        matrix = _matrix(whitened_sensitivity.sensitivity, "whitened_sensitivity")
        if parameter_ids is not None:
            raise ValueError("WhiteningResult already supplies parameter IDs.")
        identifiers = whitened_sensitivity.parameter_ids
        weighting_mode = whitened_sensitivity.mode
    else:
        if not dimensionless:
            raise ValueError(
                "Identifiability requires dimensionless/scaled sensitivities; "
                "set dimensionless=True to confirm a plain array is scaled."
            )
        matrix = _matrix(whitened_sensitivity, "whitened_sensitivity")
        identifiers = _identifiers(parameter_ids, matrix.shape[1], "parameter")
        weighting_mode = "caller_supplied_whitened"

    condition_warning_threshold = float(condition_warning_threshold)
    collinearity_warning_threshold = float(collinearity_warning_threshold)
    if not math.isfinite(condition_warning_threshold) or condition_warning_threshold <= 0.0:
        raise ValueError("condition_warning_threshold must be positive and finite.")
    if not math.isfinite(collinearity_warning_threshold) or collinearity_warning_threshold <= 0.0:
        raise ValueError("collinearity_warning_threshold must be positive and finite.")

    left_vectors, singular_values, right_transpose = np.linalg.svd(
        matrix, full_matrices=True
    )
    del left_vectors
    tolerance = _rank_tolerance(singular_values, matrix.shape, rcond)
    rank = int(np.count_nonzero(singular_values > tolerance))
    parameter_count = matrix.shape[1]
    if rank < parameter_count or singular_values.size < parameter_count:
        condition = math.inf
    else:
        condition = float(singular_values[0] / singular_values[parameter_count - 1])

    right_vectors = right_transpose.T
    fisher = matrix.T @ matrix
    covariance = _covariance_from_svd(right_vectors, singular_values, tolerance)
    correlation = _correlation_from_covariance(covariance)
    collinearity = collinearity_index(
        matrix,
        identifiers,
        warning_threshold=collinearity_warning_threshold,
    )

    padded_singular_values = np.zeros(parameter_count, dtype=float)
    padded_singular_values[: singular_values.size] = singular_values
    practical_cutoff = (
        float(singular_values[0]) / condition_warning_threshold
        if singular_values.size
        else 0.0
    )
    direction_indexes = [
        index
        for index, value in enumerate(padded_singular_values)
        if value <= tolerance or value < practical_cutoff
    ]
    if collinearity.warning and parameter_count and parameter_count - 1 not in direction_indexes:
        direction_indexes.append(parameter_count - 1)
    direction_indexes.sort()
    directions: list[DeficientDirection] = []
    for index in direction_indexes:
        coefficients = right_transpose[index].copy()
        absolute = np.abs(coefficients)
        dominant_index = int(np.argmax(absolute))
        directions.append(
            DeficientDirection(
                singular_value=float(padded_singular_values[index]),
                coefficients=coefficients,
                parameter_loadings={
                    identifier: float(coefficient)
                    for identifier, coefficient in zip(identifiers, coefficients)
                },
                dominant_parameter=identifiers[dominant_index],
                dominant_loading=float(absolute[dominant_index]),
                numerical_null_direction=bool(
                    padded_singular_values[index] <= tolerance
                ),
            )
        )

    subset_ranking = rank_identifiable_subsets(
        matrix,
        identifiers,
        rcond=rcond,
        condition_warning_threshold=condition_warning_threshold,
        collinearity_warning_threshold=collinearity_warning_threshold,
    )
    best_subset = next((item for item in subset_ranking if item.admissible), None)
    structurally_identifiable = bool(rank == parameter_count)
    directionally_separable = bool(
        condition <= condition_warning_threshold and not collinearity.warning
    )

    retained_vectors = right_vectors[:, :rank]
    observable_projector = retained_vectors @ retained_vectors.T
    nullspace_basis = right_vectors[:, rank:].copy()
    observability, observable_fractions = _observability_statuses(
        observable_projector, identifiers
    )
    physical_scales = _validated_scales(identifiers, physical_parameter_scales)
    transformed_jacobian = _validated_transformation(
        parameter_count, transformed_coordinate_jacobian
    )
    if transformed_coordinate_ids is None:
        transformed_ids = identifiers
    else:
        transformed_ids = _identifiers(
            transformed_coordinate_ids, parameter_count, "transformed_coordinate"
        )
    physical_covariance = (
        physical_scales[:, np.newaxis]
        * covariance
        * physical_scales[np.newaxis, :]
    )
    transformed_covariance = transformed_jacobian @ covariance @ transformed_jacobian.T
    scaled_sigmas = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    physical_sigmas = np.sqrt(np.maximum(np.diag(physical_covariance), 0.0))
    transformed_sigmas = np.sqrt(np.maximum(np.diag(transformed_covariance), 0.0))
    for index, identifier in enumerate(identifiers):
        if observability[identifier] != "OBSERVABLE":
            scaled_sigmas[index] = math.inf
            physical_sigmas[index] = math.inf
            transformed_sigmas[index] = math.inf

    requirements = dict(precision_requirements or {})
    unknown_requirements = set(requirements) - set(identifiers)
    if unknown_requirements:
        raise ValueError(
            "Precision requirements contain unknown parameter IDs: "
            + ", ".join(sorted(unknown_requirements))
        )
    assessments: list[ParameterPrecisionAssessment] = []
    for index, identifier in enumerate(identifiers):
        requirement = requirements.get(identifier)
        observable_status = observability[identifier]
        status = "NOT_ASSESSED"
        reason = "No parameter-specific precision requirement was supplied."
        coordinate = None
        maximum = None
        reference = None
        achieved_fraction = None
        if observable_status != "OBSERVABLE":
            status = observable_status
            reason = (
                "The data do not constrain this individual parameter independently; "
                "no finite ordinary confidence interval is valid."
            )
        elif requirement is not None:
            coordinate = requirement.coordinate
            maximum = requirement.maximum_standard_deviation
            reference = requirement.reference_scale
            achieved = {
                "scaled": scaled_sigmas[index],
                "transformed": transformed_sigmas[index],
                "physical": physical_sigmas[index],
            }[coordinate]
            if reference is not None:
                achieved_fraction = float(achieved / reference)
            status = "PASS" if achieved <= maximum else "FAIL_IMPRECISE"
            reason = (
                f"One-sigma {coordinate} uncertainty {achieved:.6g} "
                f"{'does not exceed' if status == 'PASS' else 'exceeds'} "
                f"the declared parameter-specific maximum {maximum:.6g}."
            )
        assessments.append(
            ParameterPrecisionAssessment(
                parameter_id=identifier,
                observability_status=observable_status,
                observable_fraction=float(observable_fractions[index]),
                scaled_standard_deviation=float(scaled_sigmas[index]),
                transformed_coordinate=transformed_ids[index],
                transformed_standard_deviation=float(transformed_sigmas[index]),
                physical_standard_deviation=float(physical_sigmas[index]),
                requirement_coordinate=coordinate,
                maximum_standard_deviation=maximum,
                reference_scale=reference,
                achieved_fraction_of_reference=achieved_fraction,
                status=status,
                reason=reason,
            )
        )

    requirements_complete = bool(requirements) and set(requirements) == set(identifiers)
    if not requirements_complete:
        practically_precise_enough: bool | None = None
        precision_status = "NOT_ASSESSED_MISSING_PARAMETER_REQUIREMENTS"
    else:
        practically_precise_enough = all(item.status == "PASS" for item in assessments)
        precision_status = "PASS" if practically_precise_enough else "FAIL_IMPRECISE_OR_UNOBSERVABLE"
    overall_practical_identifiability = bool(
        structurally_identifiable
        and directionally_separable
        and practically_precise_enough is True
    )
    practically_identifiable = overall_practical_identifiability

    warnings: list[str] = []
    if rank < parameter_count:
        warnings.append(
            f"Numerical rank {rank} is below the {parameter_count}-parameter model size."
        )
    if condition > condition_warning_threshold:
        warnings.append(
            f"Sensitivity condition number {condition:.6g} exceeds advisory threshold "
            f"{condition_warning_threshold:.6g}."
        )
    if collinearity.warning:
        warnings.append(
            f"Collinearity gamma {collinearity.gamma:.6g} exceeds advisory threshold "
            f"{collinearity_warning_threshold:.6g}."
        )
    if precision_status == "NOT_ASSESSED_MISSING_PARAMETER_REQUIREMENTS":
        warnings.append(
            "Practical precision was not assessed because complete parameter-specific "
            "uncertainty requirements were not supplied."
        )
    elif not practically_precise_enough:
        failed = ", ".join(
            item.parameter_id for item in assessments if item.status != "PASS"
        )
        warnings.append(
            "The full-rank/conditioning result is insufficient for practical precision; "
            f"failed or unobservable parameters: {failed}."
        )
    if weighting_mode == "unweighted":
        warnings.append("Observation uncertainty was unavailable; diagnostics are unweighted.")

    return IdentifiabilityResult(
        parameter_ids=identifiers,
        singular_values=singular_values,
        rank=rank,
        numerical_rank_tolerance=tolerance,
        condition_number=condition,
        right_singular_vectors=right_vectors,
        fisher_information=fisher,
        covariance_proxy=covariance,
        correlation_matrix=correlation,
        collinearity=collinearity,
        deficient_directions=tuple(directions),
        best_identifiable_subset=best_subset,
        subset_ranking=subset_ranking,
        structurally_identifiable=structurally_identifiable,
        directionally_separable=directionally_separable,
        practically_precise_enough=practically_precise_enough,
        overall_practical_identifiability=overall_practical_identifiability,
        practically_identifiable=practically_identifiable,
        precision_status=precision_status,
        precision_assessments=tuple(assessments),
        scaled_standard_deviations=scaled_sigmas,
        transformed_coordinate_ids=transformed_ids,
        transformed_standard_deviations=transformed_sigmas,
        physical_standard_deviations=physical_sigmas,
        observable_projector=observable_projector,
        nullspace_basis=nullspace_basis,
        parameter_observability=observability,
        warnings=tuple(warnings),
        weighting_mode=weighting_mode,
    )


__all__ = [
    "CollinearityResult",
    "DeficientDirection",
    "IdentifiabilityResult",
    "ParameterPrecisionAssessment",
    "ParameterPrecisionRequirement",
    "SubsetIdentifiability",
    "WhiteningResult",
    "analyze_identifiability",
    "collinearity_index",
    "combine_independent_uncertainties",
    "rank_identifiable_subsets",
    "whiten_modal_observation_sensitivity",
    "whiten_sensitivity",
]
