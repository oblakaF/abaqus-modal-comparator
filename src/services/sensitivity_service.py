"""Analytic modal sensitivities for the Stage-A affine matrix model.

The production derivative is the generalized-eigenvalue derivative.  Central
finite differences are deliberately kept as a verification path and only use
the already reconstructed affine matrices; they never launch Abaqus.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Sequence, Tuple

import numpy as np
from scipy import sparse

from domain.modal_observation import ModalCluster, ModalObservation

from .matrix_model_service import (
    GeneralizedEigenResult,
    StageAAffineBasis,
    StageAMatrixParameters,
    solve_generalized_eigenproblem,
)


class StageASensitivityCoordinate(str, Enum):
    """The physical coordinate held fixed while taking each derivative."""

    AFFINE = "affine_D11_D12_D66"
    BALANCED = "balanced_D_D66_r"


@dataclass(frozen=True)
class ParameterSensitivityCoordinate:
    """Derivative coordinate and the non-singular scale used for SVD input."""

    parameter_id: str
    derivative_coordinate: str
    scale: float
    scaling: str

    def __post_init__(self) -> None:
        scale = float(self.scale)
        if not math.isfinite(scale) or scale <= 0.0:
            raise ValueError("A sensitivity characteristic scale must be positive and finite.")
        object.__setattr__(self, "scale", scale)


class ScalarModeSensitivityRefusal(ValueError):
    """An explicitly requested scalar mode has no reliable single-mode sensitivity."""


@dataclass(frozen=True)
class ExcludedSensitivityObservation:
    observation_id: str
    status: str = "cluster_requires_subspace_sensitivity"


@dataclass(frozen=True)
class DerivativeValidation:
    """Central-FD agreement for the dimensionless sensitivity matrix."""

    relative_steps: Tuple[float, ...]
    parameter_step_sizes: np.ndarray
    worst_relative_errors: np.ndarray
    worst_relative_error: float
    consistent: bool
    method: str = "central_finite_difference_on_reconstructed_stage_a_matrices"


@dataclass(frozen=True)
class SensitivityResult:
    observation_ids: Tuple[str, ...]
    parameter_ids: Tuple[str, ...]
    raw_derivatives: np.ndarray
    scaled_sensitivity: np.ndarray
    frequencies_hz: np.ndarray
    parameter_coordinates: Tuple[ParameterSensitivityCoordinate, ...]
    excluded_cluster_observations: Tuple[ExcludedSensitivityObservation, ...]
    derivative_validation: DerivativeValidation | None
    coordinate_system: StageASensitivityCoordinate


def _as_square_matrix(matrix: object, name: str) -> object:
    shape = getattr(matrix, "shape", None)
    if shape is None or len(shape) != 2 or shape[0] != shape[1]:
        raise ValueError(f"{name} must be a square matrix.")
    return matrix


def _real_scalar(value: complex, name: str) -> float:
    scalar = complex(value)
    tolerance = 1.0e-10 * max(abs(scalar.real), 1.0)
    if abs(scalar.imag) > tolerance:
        raise ValueError(f"{name} has a significant imaginary component.")
    if not math.isfinite(scalar.real):
        raise ValueError(f"{name} must be finite.")
    return float(scalar.real)


def analytic_eigenvalue_derivative(
    eigenvalue: float,
    eigenvector: np.ndarray,
    mass: object,
    stiffness_derivative: object,
    mass_derivative: object | None = None,
) -> float:
    """Return ``d(lambda)/dp`` for one simple generalized eigenpair.

    No mass-normalisation is assumed.  ``numpy.vdot`` supplies the conjugate
    transpose, so arbitrary real or complex eigenvector scaling cancels between
    numerator and denominator.  A mass derivative is accepted even though it
    is zero for the current Stage-A stiffness coordinates.
    """

    eigenvalue = float(eigenvalue)
    if not math.isfinite(eigenvalue):
        raise ValueError("eigenvalue must be finite.")
    vector = np.asarray(eigenvector)
    if vector.ndim != 1 or vector.size == 0:
        raise ValueError("eigenvector must be a non-empty one-dimensional vector.")
    if not np.isfinite(vector).all():
        raise ValueError("eigenvector must contain only finite values.")

    mass = _as_square_matrix(mass, "mass")
    stiffness_derivative = _as_square_matrix(
        stiffness_derivative, "stiffness_derivative"
    )
    if mass.shape != (vector.size, vector.size) or stiffness_derivative.shape != mass.shape:
        raise ValueError("Eigenvector and derivative matrix dimensions do not agree.")
    if mass_derivative is not None:
        mass_derivative = _as_square_matrix(mass_derivative, "mass_derivative")
        if mass_derivative.shape != mass.shape:
            raise ValueError("mass_derivative must have the same shape as mass.")

    mass_vector = mass @ vector
    denominator = complex(np.vdot(vector, mass_vector))
    denominator_scale = float(np.linalg.norm(vector)) * float(np.linalg.norm(mass_vector))
    if denominator_scale == 0.0 or (
        abs(denominator) <= np.finfo(float).eps * denominator_scale
    ):
        raise ValueError("The eigenvector has zero generalized mass.")

    numerator_vector = stiffness_derivative @ vector
    if mass_derivative is not None:
        numerator_vector = numerator_vector - eigenvalue * (mass_derivative @ vector)
    numerator = np.vdot(vector, numerator_vector)
    return _real_scalar(numerator / denominator, "eigenvalue derivative")


def eigenvalue_to_frequency_derivative(
    eigenvalue: float, eigenvalue_derivative: float
) -> float:
    """Convert ``d(lambda)/dp`` to ``df/dp`` for ``f=sqrt(lambda)/(2*pi)``."""

    eigenvalue = float(eigenvalue)
    eigenvalue_derivative = float(eigenvalue_derivative)
    if not math.isfinite(eigenvalue) or eigenvalue <= 0.0:
        raise ValueError("A frequency derivative requires a positive finite eigenvalue.")
    if not math.isfinite(eigenvalue_derivative):
        raise ValueError("eigenvalue_derivative must be finite.")
    return eigenvalue_derivative / (4.0 * math.pi * math.sqrt(eigenvalue))


def _normalise_observations(
    observations: Sequence[str | ModalObservation | ModalCluster] | None,
    mode_count: int,
) -> tuple[Tuple[str, ...], np.ndarray, Tuple[ExcludedSensitivityObservation, ...]]:
    if observations is None:
        observations = tuple(f"mode_{index + 1}" for index in range(mode_count))
    if len(observations) != mode_count:
        raise ValueError("There must be exactly one observation descriptor per eigenpair.")

    included_ids: list[str] = []
    included_indexes: list[int] = []
    excluded: list[ExcludedSensitivityObservation] = []
    seen: set[str] = set()
    for index, observation in enumerate(observations):
        if isinstance(observation, ModalCluster):
            observation_id = observation.cluster_id
            excluded.append(ExcludedSensitivityObservation(observation_id))
        elif isinstance(observation, ModalObservation):
            observation_id = observation.observation_id
            included_ids.append(observation_id)
            included_indexes.append(index)
        elif isinstance(observation, str) and observation.strip():
            observation_id = observation.strip()
            included_ids.append(observation_id)
            included_indexes.append(index)
        else:
            raise TypeError(
                "Each observation must be a non-empty ID, ModalObservation, or ModalCluster."
            )
        if observation_id in seen:
            raise ValueError("Sensitivity observation identifiers must be unique.")
        seen.add(observation_id)
    return tuple(included_ids), np.asarray(included_indexes, dtype=int), tuple(excluded)


def _validated_observed_mode_ids(
    observed_mode_ids: Sequence[int], returned_count: int
) -> Tuple[int, ...]:
    requested = tuple(observed_mode_ids)
    if not requested:
        raise ValueError("observed_mode_ids must name at least one FE mode.")
    for mode_id in requested:
        if isinstance(mode_id, (bool, np.bool_)) or not isinstance(
            mode_id, (int, np.integer)
        ):
            raise TypeError("observed_mode_ids must be 1-based integer FE mode IDs.")
        if not 1 <= mode_id <= returned_count:
            raise ValueError(
                f"Observed FE mode {mode_id} is outside the returned elastic modes "
                f"1..{returned_count}."
            )
    if len(set(requested)) != len(requested):
        raise ValueError("observed_mode_ids must be unique.")
    return tuple(int(mode_id) for mode_id in requested)


def _numerically_degenerate_partners(
    eigenpairs: GeneralizedEigenResult, mode_ids: Sequence[int]
) -> dict[int, Tuple[str, ...]]:
    """Return, per requested FE mode ID, the modes it is numerically tied with.

    This is the same machine-precision unresolvedness rule the inverse solver
    applies to fitted modes (``100 * eps * n * spectral scale``, the rule the
    generalized eigensolver uses for numerical zero), evaluated on the same
    returned spectrum and including the already-computed eigenvalue just above
    the returned window.  It is not a physical closeness, cluster-gap, or
    modal-family policy and has no configurable threshold.
    """

    values = np.asarray(eigenpairs.eigenvalues, dtype=float)
    spectrum = np.concatenate(
        (values, np.asarray(eigenpairs.rigid_body_eigenvalues, dtype=float))
    )
    scale = max(float(np.max(np.abs(spectrum))), 1.0)
    resolution = (
        100.0 * np.finfo(float).eps * scale * max(eigenpairs.eigenvectors.shape[0], 1)
    )
    compared = values
    if eigenpairs.next_elastic_eigenvalue is not None:
        compared = np.append(values, float(eigenpairs.next_elastic_eigenvalue))
    partners: dict[int, Tuple[str, ...]] = {}
    for mode_id in mode_ids:
        tied = np.flatnonzero(np.abs(compared - values[mode_id - 1]) <= resolution)
        names = tuple(
            f"FE mode {index + 1}"
            if index < values.size
            else "the next elastic eigenvalue above the returned mode window"
            for index in tied
            if index != mode_id - 1
        )
        if names:
            partners[mode_id] = names
    return partners


def _require_scalar_observed_modes(
    eigenpairs: GeneralizedEigenResult, mode_ids: Tuple[int, ...]
) -> None:
    """Refuse requested modes without a reliable single-eigenvector sensitivity."""

    partners = _numerically_degenerate_partners(eigenpairs, mode_ids)
    if partners:
        raise ScalarModeSensitivityRefusal(
            "Scalar sensitivity refused: "
            + "; ".join(
                f"FE mode {mode_id} is numerically degenerate with "
                + ", ".join(names)
                for mode_id, names in partners.items()
            )
            + ". Ordinary scalar single-eigenvector Rayleigh sensitivity is not "
            "scientifically defined reliably for that eigenspace (its eigenvectors "
            "are an arbitrary basis of the tie). Subspace sensitivity would be a "
            "separate method and is not an automatic fallback."
        )
    guard_mode = int(np.asarray(eigenpairs.eigenvalues).size)
    if guard_mode in mode_ids:
        raise ScalarModeSensitivityRefusal(
            f"Scalar sensitivity refused: FE mode {guard_mode} is the computational "
            "guard mode (the highest returned elastic mode); a scientifically "
            f"requested scalar mode must have an ID below {guard_mode}. Request more "
            "modal headroom (a larger mode_count)."
        )


def generalized_eigen_sensitivity(
    eigenpairs: GeneralizedEigenResult,
    mass: object,
    stiffness_derivatives: Sequence[object],
    parameter_coordinates: Sequence[ParameterSensitivityCoordinate],
    *,
    mass_derivatives: Sequence[object | None] | None = None,
    observations: Sequence[str | ModalObservation | ModalCluster] | None = None,
    coordinate_system: StageASensitivityCoordinate = StageASensitivityCoordinate.AFFINE,
    observed_mode_ids: Sequence[int] | None = None,
) -> SensitivityResult:
    """Compute physical and scaled derivatives for simple eigenpairs.

    ``raw_derivatives`` contains ``df/dq`` in each declared physical coordinate
    ``q``.  ``scaled_sensitivity`` contains ``(q_scale/f) * df/dq``.  Positive
    parameters use their current value as ``q_scale`` and are therefore the
    usual log/log sensitivities.  Signed parameters use a declared,
    non-vanishing characteristic scale instead.

    ``observed_mode_ids`` (1-based FE elastic mode IDs) is an explicit
    scientific request: only those rows are returned, in the requested order,
    as ``mode_<id>``.  Each requested mode must be numerically resolved and
    below the computational guard mode, otherwise the whole request raises
    :class:`ScalarModeSensitivityRefusal`; degenerate modes that were not
    requested do not matter.  ``None`` keeps the legacy full-spectrum,
    positional ``observations`` behaviour without those checks.
    """

    coordinates = tuple(parameter_coordinates)
    derivatives = tuple(stiffness_derivatives)
    if not coordinates or len(coordinates) != len(derivatives):
        raise ValueError("A coordinate descriptor is required for every derivative matrix.")
    if mass_derivatives is None:
        mass_derivatives = (None,) * len(derivatives)
    else:
        mass_derivatives = tuple(mass_derivatives)
        if len(mass_derivatives) != len(derivatives):
            raise ValueError("A mass derivative must be supplied for every parameter.")

    values = np.asarray(eigenpairs.eigenvalues, dtype=float)
    frequencies = np.asarray(eigenpairs.frequencies_hz, dtype=float)
    vectors = np.asarray(eigenpairs.eigenvectors)
    if values.ndim != 1 or frequencies.shape != values.shape:
        raise ValueError("Eigenvalue and frequency arrays must be matching vectors.")
    if vectors.shape != (getattr(mass, "shape", (None, None))[0], values.size):
        raise ValueError("Eigenvectors must be stored by columns and match the mass matrix.")

    if observed_mode_ids is None:
        observation_ids, included_indexes, excluded = _normalise_observations(
            observations, values.size
        )
    else:
        if observations is not None:
            raise ValueError(
                "observations and observed_mode_ids are mutually exclusive: "
                "observations are positional over the whole returned spectrum."
            )
        requested = _validated_observed_mode_ids(observed_mode_ids, values.size)
        _require_scalar_observed_modes(eigenpairs, requested)
        observation_ids = tuple(f"mode_{mode_id}" for mode_id in requested)
        included_indexes = np.asarray(requested, dtype=int) - 1
        excluded = ()
    raw = np.empty((included_indexes.size, len(derivatives)), dtype=float)
    for result_index, mode_index in enumerate(included_indexes):
        eigenvalue = values[mode_index]
        for parameter_index, (stiffness_derivative, mass_derivative) in enumerate(
            zip(derivatives, mass_derivatives)
        ):
            lambda_derivative = analytic_eigenvalue_derivative(
                eigenvalue,
                vectors[:, mode_index],
                mass,
                stiffness_derivative,
                mass_derivative,
            )
            raw[result_index, parameter_index] = eigenvalue_to_frequency_derivative(
                eigenvalue, lambda_derivative
            )

    included_frequencies = frequencies[included_indexes]
    scales = np.asarray([item.scale for item in coordinates], dtype=float)
    scaled = raw * scales[np.newaxis, :] / included_frequencies[:, np.newaxis]
    return SensitivityResult(
        observation_ids=observation_ids,
        parameter_ids=tuple(item.parameter_id for item in coordinates),
        raw_derivatives=raw,
        scaled_sensitivity=scaled,
        frequencies_hz=included_frequencies,
        parameter_coordinates=coordinates,
        excluded_cluster_observations=excluded,
        derivative_validation=None,
        coordinate_system=coordinate_system,
    )


def _stage_a_coordinates_and_derivatives(
    basis: StageAAffineBasis,
    parameters: StageAMatrixParameters,
    coordinate_system: StageASensitivityCoordinate,
    ratio_characteristic_scale: float,
) -> tuple[
    Tuple[ParameterSensitivityCoordinate, ...],
    Tuple[sparse.csr_matrix, ...],
    Tuple[sparse.csr_matrix | None, ...] | None,
]:
    """Return coordinates, ``dK/dq``, and ``dM/dq`` (``None`` entries mean 0).

    ``D`` (physical ``D11``) is the only coordinate with a non-zero mass
    derivative, and only when ``basis`` carries a recovered
    ``mass_derivative_D11`` -- ``D12``/``D66``/``r`` were verified to leave
    the mass matrix unchanged.  The overall mass-derivative tuple is
    ``None`` for a legacy constant-``M`` basis, so callers can distinguish
    "no D-dependence was ever evidenced" from "this coordinate's slope is
    zero".
    """

    affine = basis.basis_matrices
    mass_slope = basis.mass_derivative_D11
    if coordinate_system == StageASensitivityCoordinate.AFFINE:
        mass_derivatives = (
            None if mass_slope is None else (mass_slope, None, None)
        )
        return (
            (
                ParameterSensitivityCoordinate(
                    "D11",
                    "physical balanced D11=D22 at fixed D12,D66",
                    parameters.D11,
                    "relative",
                ),
                ParameterSensitivityCoordinate(
                    "D12",
                    "physical signed D12 at fixed D11,D66",
                    parameters.D11,
                    "characteristic_D11",
                ),
                ParameterSensitivityCoordinate(
                    "D66", "physical D66 at fixed D11,D12", parameters.D66, "relative"
                ),
            ),
            affine,
            mass_derivatives,
        )
    if coordinate_system == StageASensitivityCoordinate.BALANCED:
        point = parameters.as_parameterization()
        ratio_characteristic_scale = float(ratio_characteristic_scale)
        if not math.isfinite(ratio_characteristic_scale) or ratio_characteristic_scale <= 0.0:
            raise ValueError("ratio_characteristic_scale must be positive and finite.")
        d_derivative = sparse.csr_matrix(affine[0] + point.r * affine[1])
        ratio_derivative = sparse.csr_matrix(point.D * affine[1])
        mass_derivatives = (
            None if mass_slope is None else (mass_slope, None, None)
        )
        return (
            (
                ParameterSensitivityCoordinate(
                    "D", "physical D at fixed D66,r", point.D, "relative"
                ),
                ParameterSensitivityCoordinate(
                    "D66", "physical D66 at fixed D,r", point.D66, "relative"
                ),
                ParameterSensitivityCoordinate(
                    "r",
                    "signed ratio r=D12/D at fixed D,D66",
                    ratio_characteristic_scale,
                    "characteristic_ratio",
                ),
            ),
            (d_derivative, affine[2], ratio_derivative),
            mass_derivatives,
        )
    raise ValueError(f"Unsupported Stage-A sensitivity coordinate: {coordinate_system!r}")


def _perturb_stage_a_parameters(
    parameters: StageAMatrixParameters,
    coordinate_system: StageASensitivityCoordinate,
    parameter_index: int,
    requested_step: float,
) -> tuple[StageAMatrixParameters, StageAMatrixParameters, float]:
    point = parameters.as_parameterization()
    if coordinate_system == StageASensitivityCoordinate.AFFINE:
        values = parameters.values.copy()
        if parameter_index == 0:
            limit = min(parameters.D11, parameters.D11 - abs(parameters.D12))
        elif parameter_index == 1:
            limit = parameters.D11 - abs(parameters.D12)
        else:
            limit = parameters.D66
        step = min(requested_step, 0.49 * limit)
        if not step > 0.0:
            raise ValueError("No admissible central finite-difference step is available.")
        lower = values.copy()
        upper = values.copy()
        lower[parameter_index] -= step
        upper[parameter_index] += step
        return StageAMatrixParameters(*lower), StageAMatrixParameters(*upper), step

    values = np.asarray((point.D, point.D66, point.r), dtype=float)
    limit = values[parameter_index] if parameter_index < 2 else 1.0 - abs(point.r)
    step = min(requested_step, 0.49 * limit)
    if not step > 0.0:
        raise ValueError("No admissible central finite-difference step is available.")
    lower = values.copy()
    upper = values.copy()
    lower[parameter_index] -= step
    upper[parameter_index] += step

    def converted(candidate: np.ndarray) -> StageAMatrixParameters:
        d, d66, ratio = candidate
        return StageAMatrixParameters(d, ratio * d, d66)

    return converted(lower), converted(upper), step


def _finite_difference_validation(
    basis: StageAAffineBasis,
    parameters: StageAMatrixParameters,
    result: SensitivityResult,
    included_indexes: np.ndarray,
    *,
    mode_count: int,
    expected_rigid_body_modes: int | None,
    relative_steps: Tuple[float, ...],
    validation_relative_tolerance: float,
) -> DerivativeValidation:
    step_sizes = np.empty((len(relative_steps), len(result.parameter_ids)), dtype=float)
    worst_errors = np.empty(len(relative_steps), dtype=float)
    scales = np.asarray([item.scale for item in result.parameter_coordinates], dtype=float)
    analytic = result.scaled_sensitivity

    for relative_index, relative_step in enumerate(relative_steps):
        finite_difference = np.empty_like(analytic)
        for parameter_index, scale in enumerate(scales):
            lower, upper, step = _perturb_stage_a_parameters(
                parameters,
                result.coordinate_system,
                parameter_index,
                relative_step * scale,
            )
            step_sizes[relative_index, parameter_index] = step
            lower_result = solve_generalized_eigenproblem(
                basis.reconstruct_stiffness(lower),
                basis.reconstruct_mass(lower),
                mode_count,
                expected_rigid_body_modes=expected_rigid_body_modes,
                dofs=basis.dofs,
            )
            upper_result = solve_generalized_eigenproblem(
                basis.reconstruct_stiffness(upper),
                basis.reconstruct_mass(upper),
                mode_count,
                expected_rigid_body_modes=expected_rigid_body_modes,
                dofs=basis.dofs,
            )
            derivative = (upper_result.frequencies_hz - lower_result.frequencies_hz) / (
                2.0 * step
            )
            finite_difference[:, parameter_index] = (
                derivative[included_indexes]
                * scale
                / result.frequencies_hz
            )

        denominator = np.maximum(np.abs(analytic), 1.0e-8)
        relative_error = np.abs(finite_difference - analytic) / denominator
        worst_errors[relative_index] = float(np.max(relative_error, initial=0.0))

    worst = float(np.max(worst_errors, initial=0.0))
    return DerivativeValidation(
        relative_steps=relative_steps,
        parameter_step_sizes=step_sizes,
        worst_relative_errors=worst_errors,
        worst_relative_error=worst,
        consistent=bool(np.isfinite(worst) and worst <= validation_relative_tolerance),
    )


def compute_stage_a_sensitivity(
    basis: StageAAffineBasis,
    parameters: StageAMatrixParameters,
    mode_count: int,
    *,
    coordinate_system: StageASensitivityCoordinate = StageASensitivityCoordinate.AFFINE,
    observations: Sequence[str | ModalObservation | ModalCluster] | None = None,
    expected_rigid_body_modes: int | None = None,
    ratio_characteristic_scale: float = 1.0,
    finite_difference_relative_steps: Sequence[float] = (0.005, 0.01, 0.02),
    validation_relative_tolerance: float = 5.0e-3,
    observed_mode_ids: Sequence[int] | None = None,
) -> SensitivityResult:
    """Compute Stage-A analytic sensitivities and optional reconstructed-FD checks.

    ``observed_mode_ids`` has the meaning documented on
    :func:`generalized_eigen_sensitivity`.
    """

    coordinate_system = StageASensitivityCoordinate(coordinate_system)
    if observed_mode_ids is not None:
        observed_mode_ids = tuple(observed_mode_ids)
    if not isinstance(parameters, StageAMatrixParameters):
        raise TypeError("parameters must be StageAMatrixParameters.")
    if isinstance(mode_count, bool) or int(mode_count) != mode_count or mode_count <= 0:
        raise ValueError("mode_count must be a positive integer.")
    mode_count = int(mode_count)
    relative_steps = tuple(float(item) for item in finite_difference_relative_steps)
    if any(not math.isfinite(item) or item <= 0.0 for item in relative_steps):
        raise ValueError("Finite-difference relative steps must be positive and finite.")
    validation_relative_tolerance = float(validation_relative_tolerance)
    if not math.isfinite(validation_relative_tolerance) or validation_relative_tolerance <= 0.0:
        raise ValueError("validation_relative_tolerance must be positive and finite.")

    stiffness = basis.reconstruct_stiffness(parameters)
    mass = basis.reconstruct_mass(parameters)
    eigenpairs = solve_generalized_eigenproblem(
        stiffness,
        mass,
        mode_count,
        expected_rigid_body_modes=expected_rigid_body_modes,
        dofs=basis.dofs,
    )
    coordinates, derivatives, mass_derivatives = _stage_a_coordinates_and_derivatives(
        basis, parameters, coordinate_system, ratio_characteristic_scale
    )
    result = generalized_eigen_sensitivity(
        eigenpairs,
        mass,
        derivatives,
        coordinates,
        mass_derivatives=mass_derivatives,
        observations=observations,
        coordinate_system=coordinate_system,
        observed_mode_ids=observed_mode_ids,
    )
    if not relative_steps:
        return result

    if observed_mode_ids is None:
        _, included_indexes, _ = _normalise_observations(observations, mode_count)
    else:
        included_indexes = np.asarray(observed_mode_ids, dtype=int) - 1
    validation = _finite_difference_validation(
        basis,
        parameters,
        result,
        included_indexes,
        mode_count=mode_count,
        expected_rigid_body_modes=expected_rigid_body_modes,
        relative_steps=relative_steps,
        validation_relative_tolerance=validation_relative_tolerance,
    )
    return SensitivityResult(
        observation_ids=result.observation_ids,
        parameter_ids=result.parameter_ids,
        raw_derivatives=result.raw_derivatives,
        scaled_sensitivity=result.scaled_sensitivity,
        frequencies_hz=result.frequencies_hz,
        parameter_coordinates=result.parameter_coordinates,
        excluded_cluster_observations=result.excluded_cluster_observations,
        derivative_validation=validation,
        coordinate_system=result.coordinate_system,
    )


__all__ = [
    "DerivativeValidation",
    "ExcludedSensitivityObservation",
    "ParameterSensitivityCoordinate",
    "ScalarModeSensitivityRefusal",
    "SensitivityResult",
    "StageASensitivityCoordinate",
    "analytic_eigenvalue_derivative",
    "compute_stage_a_sensitivity",
    "eigenvalue_to_frequency_derivative",
    "generalized_eigen_sensitivity",
]
