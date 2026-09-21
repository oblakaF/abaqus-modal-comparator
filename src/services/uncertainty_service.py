"""Primary-measurement Monte Carlo uncertainty propagation for Stage A.

The service deliberately knows nothing about Abaqus execution.  Each sampled
realisation is handed to a caller-supplied runner which is expected to invoke
the existing fast-matrix Stage-A identification pipeline.  This keeps the
verified affine matrix model in the loop while preventing an Abaqus job per
sample.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import math
from typing import Any, Callable, Mapping, Sequence, Tuple

import numpy as np

from domain.modal_observation import ModalObservation, ObservationUncertainty
from domain.specimen import PhysicalSpecimen, PrimaryMeasurement

from .inverse_solver import InverseIdentificationResult
from .stage_a_identification_service import StageAIdentificationResult, identify_stage_a


FREQUENCY_VARIANCE_ASSUMPTION = (
    "Experimental-frequency measurement and setup components are independent; "
    "their variances are summed. Manufacturing variation is not added for one "
    "bare specimen."
)
APPARENT_FLEXURAL_LABEL = "APPARENT FLEXURAL / EQUIVALENT FLEXURAL PROPERTIES"


class UncertaintyValidationError(ValueError):
    """The requested uncertainty calculation is incomplete or invalid."""


@dataclass(frozen=True)
class MonteCarloConfiguration:
    sample_count: int
    random_seed: int = 1729
    allow_unweighted_frequency: bool = False
    failure_rate_warning_threshold: float = 0.10
    max_resample_attempts: int = 100

    def __post_init__(self) -> None:
        for name, minimum in (("sample_count", 1), ("max_resample_attempts", 1)):
            value = getattr(self, name)
            if isinstance(value, bool) or int(value) != value or int(value) < minimum:
                raise UncertaintyValidationError(f"{name} must be an integer >= {minimum}.")
            object.__setattr__(self, name, int(value))
        seed = self.random_seed
        if isinstance(seed, bool) or int(seed) != seed:
            raise UncertaintyValidationError("random_seed must be an integer.")
        object.__setattr__(self, "random_seed", int(seed))
        threshold = float(self.failure_rate_warning_threshold)
        if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
            raise UncertaintyValidationError(
                "failure_rate_warning_threshold must be finite and in [0, 1]."
            )
        object.__setattr__(self, "failure_rate_warning_threshold", threshold)


@dataclass(frozen=True)
class StageARealisationInput:
    sample_index: int
    specimen: PhysicalSpecimen
    primary_measurements: Mapping[str, float]
    derived_quantities: Mapping[str, float]
    observations: Tuple[ModalObservation, ...]


@dataclass(frozen=True)
class ApparentFlexuralProperties:
    E_flex: float
    G12_flex: float
    nu12_flex: float
    label: str = APPARENT_FLEXURAL_LABEL


@dataclass(frozen=True)
class MonteCarloSample:
    sample_index: int
    primary_measurements: Mapping[str, float]
    derived_quantities: Mapping[str, float]
    fitted_parameters: Mapping[str, float]
    objective: float | None
    converged: bool
    fitted_subset: Tuple[str, ...]
    warnings: Tuple[str, ...]
    apparent_flexural_properties: ApparentFlexuralProperties | None = None
    failure: str | None = None


@dataclass(frozen=True)
class QuantityStatistics:
    mean: float
    median: float
    standard_deviation: float
    percentile_2_5: float
    percentile_97_5: float
    interval_95: Tuple[float, float]
    successful_sample_count: int
    failed_sample_count: int
    convergence_fraction: float


@dataclass(frozen=True)
class LocalCovarianceDiagnostic:
    parameter_ids: Tuple[str, ...]
    covariance: np.ndarray
    standard_deviations: np.ndarray
    intervals_95: Mapping[str, Tuple[float, float] | None]
    rank: int
    numerical_rank_tolerance: float
    nullspace_basis: np.ndarray
    observable_projector: np.ndarray
    parameter_statuses: Mapping[str, str]
    unobservable_parameter_ids: Tuple[str, ...]
    partially_observable_parameter_ids: Tuple[str, ...]
    method: str = (
        "diagnostic pseudoinverse of J.T @ W @ J with explicit nullspace; "
        "pseudoinverse zeros never imply zero physical uncertainty"
    )


@dataclass(frozen=True)
class ThicknessVarianceDiagnostic:
    quantity: str
    thickness_variance_fraction: float
    identified_stiffness_variance_fraction: float
    frequency_and_interaction_variance_fraction: float
    method: str = "approximate log-space variance contribution diagnostic"


@dataclass(frozen=True)
class MonteCarloResult:
    samples: Tuple[MonteCarloSample, ...]
    identified_statistics: Mapping[str, QuantityStatistics]
    derived_statistics: Mapping[str, QuantityStatistics]
    successful_sample_count: int
    failed_sample_count: int
    convergence_fraction: float
    thickness_diagnostics: Mapping[str, ThicknessVarianceDiagnostic]
    assumptions: Tuple[str, ...]
    warnings: Tuple[str, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CoverageValidationResult:
    repetitions: int
    target_coverage: float
    tolerance: float
    empirical_coverage: Mapping[str, float]
    covered_counts: Mapping[str, int]
    successful_experiments: int
    failed_experiments: int
    passed: bool
    random_seed: int
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SyntheticTruthCase:
    """Level-1 virtual experiment driven by a fast parameter estimator.

    ``estimator`` maps one synthetic modal-frequency vector to identified
    parameters.  Production validation supplies an adapter around the existing
    fast-matrix inverse solver; unit tests may use an analytic linear estimator.
    """

    truth: Mapping[str, float]
    nominal_observations: np.ndarray
    observation_standard_deviations: np.ndarray
    estimator: Callable[[np.ndarray], Mapping[str, float]] = field(compare=False)

    def __post_init__(self) -> None:
        nominal = np.asarray(self.nominal_observations, dtype=float)
        sigmas = np.asarray(self.observation_standard_deviations, dtype=float)
        if nominal.ndim != 1 or nominal.size == 0 or sigmas.shape != nominal.shape:
            raise UncertaintyValidationError(
                "Synthetic observations and standard deviations must be matching vectors."
            )
        if (
            not np.isfinite(nominal).all()
            or np.any(nominal <= 0.0)
            or not np.isfinite(sigmas).all()
            or np.any(sigmas < 0.0)
        ):
            raise UncertaintyValidationError(
                "Synthetic frequencies must be positive and sigmas non-negative."
            )
        if not self.truth or not all(
            math.isfinite(float(value)) for value in self.truth.values()
        ):
            raise UncertaintyValidationError("Synthetic truth must be finite and non-empty.")
        if not callable(self.estimator):
            raise TypeError("Synthetic estimator must be callable.")
        object.__setattr__(self, "nominal_observations", nominal.copy())
        object.__setattr__(self, "observation_standard_deviations", sigmas.copy())


IdentificationRunner = Callable[
    [StageARealisationInput], StageAIdentificationResult | InverseIdentificationResult
]
CoverageExperiment = Callable[
    [np.random.Generator, int], tuple[Mapping[str, float], MonteCarloResult]
]
StageAInputFactory = Callable[[StageARealisationInput], Mapping[str, Any]]


def create_stage_a_pipeline_runner(
    input_factory: StageAInputFactory,
) -> IdentificationRunner:
    """Adapt per-realisation inputs to the existing production pipeline.

    The factory owns specimen-specific geometry/mass adaptation and must return
    the keyword arguments accepted by :func:`identify_stage_a`, including the
    already verified ``StageAAffineBasis``.  No Abaqus command is issued here.
    """

    if not callable(input_factory):
        raise TypeError("input_factory must be callable.")

    def run(realisation: StageARealisationInput) -> StageAIdentificationResult:
        arguments = input_factory(realisation)
        if not isinstance(arguments, Mapping):
            raise TypeError("input_factory must return a mapping of identify_stage_a inputs.")
        return identify_stage_a(**dict(arguments))

    return run


def _measurement_distribution(measurement: PrimaryMeasurement) -> str:
    supplied = str(measurement.metadata.get("distribution", "normal")).strip().lower()
    if supplied not in {"normal", "fixed", "deterministic"}:
        raise UncertaintyValidationError(
            f"Unsupported distribution {supplied!r} for primary measurement "
            f"{measurement.name!r}."
        )
    if supplied in {"fixed", "deterministic"} and measurement.standard_uncertainty != 0.0:
        raise UncertaintyValidationError(
            f"Fixed primary measurement {measurement.name!r} must have zero uncertainty."
        )
    return supplied


def sample_primary_measurements(
    specimen: PhysicalSpecimen,
    rng: np.random.Generator,
    *,
    max_resample_attempts: int = 100,
) -> Mapping[str, float]:
    """Draw positive primary measurements using rejection, never silent clipping."""

    if not isinstance(specimen, PhysicalSpecimen):
        raise TypeError("specimen must be PhysicalSpecimen.")
    if not isinstance(rng, np.random.Generator):
        raise TypeError("rng must be numpy.random.Generator.")
    result: dict[str, float] = {}
    for measurement in specimen.primary_measurements:
        distribution = _measurement_distribution(measurement)
        sigma = float(measurement.standard_uncertainty)
        if distribution in {"fixed", "deterministic"} or sigma == 0.0:
            result[measurement.name] = float(measurement.value)
            continue
        for _ in range(max_resample_attempts):
            candidate = float(rng.normal(float(measurement.value), sigma))
            if math.isfinite(candidate) and candidate > 0.0:
                result[measurement.name] = candidate
                break
        else:
            raise UncertaintyValidationError(
                f"Could not draw a positive value for {measurement.name!r} after "
                f"{max_resample_attempts} attempts; values are not clipped."
            )
    return result


def _length_in_metres(value: float, unit: str) -> float:
    normalized = unit.strip().lower()
    factors = {"": 1.0, "m": 1.0, "mm": 1.0e-3, "um": 1.0e-6, "µm": 1.0e-6}
    if normalized not in factors:
        raise UncertaintyValidationError(
            f"Unsupported length unit {unit!r}; use m, mm, um, or µm."
        )
    return float(value) * factors[normalized]


def derive_bare_plate_quantities(
    specimen: PhysicalSpecimen, sampled: Mapping[str, float]
) -> Mapping[str, float]:
    """Derive correlated Stage-A quantities exclusively from primary draws."""

    required = ("m", "L", "W", "h")
    missing = tuple(name for name in required if name not in sampled)
    if missing:
        raise UncertaintyValidationError(
            "Bare-plate Stage A requires primary measurements: " + ", ".join(missing)
        )
    by_name = {item.name: item for item in specimen.primary_measurements}
    mass = float(sampled["m"])
    length = _length_in_metres(sampled["L"], by_name["L"].unit)
    width = _length_in_metres(sampled["W"], by_name["W"].unit)
    thickness = _length_in_metres(sampled["h"], by_name["h"].unit)
    if min(mass, length, width, thickness) <= 0.0:
        raise UncertaintyValidationError("Sampled mass and dimensions must be positive.")
    return {
        "areal_mass": mass / (length * width),
        "h_m": thickness,
        "L_m": length,
        "W_m": width,
    }


def _frequency_sigma(
    uncertainty: ObservationUncertainty,
    *,
    allow_unweighted: bool,
) -> float:
    components = tuple(
        float(value)
        for value in (uncertainty.measurement, uncertainty.setup)
        if value is not None
    )
    if not components:
        if allow_unweighted:
            return 0.0
        raise UncertaintyValidationError(
            "Experimental-frequency uncertainty is missing; explicitly enable "
            "allow_unweighted_frequency to keep observations deterministic."
        )
    return math.sqrt(sum(value * value for value in components))


def perturb_modal_observations(
    observations: Sequence[ModalObservation],
    rng: np.random.Generator,
    *,
    allow_unweighted: bool = False,
    max_resample_attempts: int = 100,
) -> Tuple[ModalObservation, ...]:
    """Perturb frequencies from measurement/setup sigma; manufacturing is preserved only."""

    result: list[ModalObservation] = []
    for observation in observations:
        sigma = _frequency_sigma(
            observation.uncertainty, allow_unweighted=allow_unweighted
        )
        if sigma == 0.0:
            frequency = float(observation.experimental_frequency_hz)
        else:
            for _ in range(max_resample_attempts):
                frequency = float(
                    rng.normal(float(observation.experimental_frequency_hz), sigma)
                )
                if math.isfinite(frequency) and frequency > 0.0:
                    break
            else:
                raise UncertaintyValidationError(
                    f"Could not draw a positive frequency for {observation.observation_id!r}; "
                    "values are not clipped."
                )
        metadata = dict(observation.metadata)
        metadata.update(
            {
                "uncertainty_sampling": "independent normal measurement+setup",
                "manufacturing_uncertainty_sampled": False,
            }
        )
        result.append(
            replace(observation, experimental_frequency_hz=frequency, metadata=metadata)
        )
    return tuple(result)


def apparent_flexural_properties(
    D11: float, D12: float, D66: float, thickness_m: float
) -> ApparentFlexuralProperties:
    values = tuple(float(item) for item in (D11, D12, D66, thickness_m))
    if not all(math.isfinite(item) for item in values):
        raise UncertaintyValidationError("D parameters and thickness must be finite.")
    D11, D12, D66, thickness_m = values
    if D11 <= 0.0 or D66 <= 0.0 or thickness_m <= 0.0 or abs(D12) >= D11:
        raise UncertaintyValidationError("D parameters or thickness are not admissible.")
    ratio = D12 / D11
    return ApparentFlexuralProperties(
        E_flex=12.0 * D11 * (1.0 - ratio * ratio) / thickness_m**3,
        G12_flex=12.0 * D66 / thickness_m**3,
        nu12_flex=ratio,
    )


def summarize_samples(
    values: Sequence[float], *, successful: int, failed: int
) -> QuantityStatistics:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or array.size == 0 or not np.isfinite(array).all():
        raise UncertaintyValidationError("Statistics require finite accepted samples.")
    low, high = np.percentile(array, (2.5, 97.5))
    total = successful + failed
    return QuantityStatistics(
        mean=float(np.mean(array)),
        median=float(np.median(array)),
        standard_deviation=float(np.std(array, ddof=1)) if array.size > 1 else 0.0,
        percentile_2_5=float(low),
        percentile_97_5=float(high),
        interval_95=(float(low), float(high)),
        successful_sample_count=successful,
        failed_sample_count=failed,
        convergence_fraction=float(successful / total) if total else 0.0,
    )


def local_linear_covariance(
    jacobian: np.ndarray,
    parameter_ids: Sequence[str],
    *,
    estimates: Sequence[float] | None = None,
    weights: np.ndarray | Sequence[float] | None = None,
) -> LocalCovarianceDiagnostic:
    """Return the diagnostic local covariance using a Moore-Penrose pseudoinverse."""

    matrix = np.asarray(jacobian, dtype=float)
    identifiers = tuple(str(item) for item in parameter_ids)
    if matrix.ndim != 2 or matrix.shape[1] != len(identifiers) or not identifiers:
        raise UncertaintyValidationError("Jacobian columns must match parameter_ids.")
    if not np.isfinite(matrix).all():
        raise UncertaintyValidationError("Jacobian must be finite.")
    if weights is None:
        information = matrix.T @ matrix
    else:
        supplied = np.asarray(weights, dtype=float)
        if supplied.ndim == 1:
            if (
                supplied.shape != (matrix.shape[0],)
                or not np.isfinite(supplied).all()
                or np.any(supplied < 0.0)
            ):
                raise UncertaintyValidationError("Weight vector is invalid.")
            information = matrix.T @ (supplied[:, None] * matrix)
        elif supplied.shape == (matrix.shape[0], matrix.shape[0]):
            if not np.isfinite(supplied).all():
                raise UncertaintyValidationError("Weight matrix must be finite.")
            information = matrix.T @ supplied @ matrix
        else:
            raise UncertaintyValidationError("weights must be a row vector or square matrix.")
    # Rank and nullspace must correspond to the weighted information matrix,
    # including semidefinite row weights.  Its eigenvectors provide the same
    # observable/null decomposition without inventing an epsilon.
    information_eigenvalues, information_vectors = np.linalg.eigh(information)
    information_scale = float(np.max(np.abs(information_eigenvalues), initial=0.0))
    information_tolerance = (
        max(information.shape) * np.finfo(float).eps * information_scale
    )
    observable_mask = information_eigenvalues > information_tolerance
    rank = int(np.count_nonzero(observable_mask))
    observable_vectors = information_vectors[:, observable_mask]
    nullspace_basis = information_vectors[:, ~observable_mask]
    observable_projector = observable_vectors @ observable_vectors.T
    covariance = np.linalg.pinv(information, rcond=(
        information_tolerance / information_scale if information_scale > 0.0 else 0.0
    ))
    finite_sigmas = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    fractions = np.clip(np.diag(observable_projector), 0.0, 1.0)
    fraction_tolerance = 100.0 * np.finfo(float).eps * max(len(identifiers), 1)
    statuses: dict[str, str] = {}
    for identifier, fraction in zip(identifiers, fractions):
        if fraction <= fraction_tolerance:
            statuses[identifier] = "UNOBSERVABLE"
        elif fraction >= 1.0 - fraction_tolerance:
            statuses[identifier] = "OBSERVABLE"
        else:
            statuses[identifier] = "PARTIALLY_OBSERVABLE"
    standard_deviations = finite_sigmas.copy()
    for index, identifier in enumerate(identifiers):
        if statuses[identifier] != "OBSERVABLE":
            standard_deviations[index] = math.inf
    centres = np.zeros(len(identifiers)) if estimates is None else np.asarray(estimates, dtype=float)
    if centres.shape != (len(identifiers),) or not np.isfinite(centres).all():
        raise UncertaintyValidationError("estimates must match parameter_ids.")
    intervals = {
        name: (
            (float(value - 1.96 * sigma), float(value + 1.96 * sigma))
            if statuses[name] == "OBSERVABLE"
            else None
        )
        for name, value, sigma in zip(identifiers, centres, standard_deviations)
    }
    return LocalCovarianceDiagnostic(
        parameter_ids=identifiers,
        covariance=covariance,
        standard_deviations=standard_deviations,
        intervals_95=intervals,
        rank=rank,
        numerical_rank_tolerance=information_tolerance,
        nullspace_basis=nullspace_basis,
        observable_projector=observable_projector,
        parameter_statuses=statuses,
        unobservable_parameter_ids=tuple(
            name for name in identifiers if statuses[name] == "UNOBSERVABLE"
        ),
        partially_observable_parameter_ids=tuple(
            name for name in identifiers if statuses[name] == "PARTIALLY_OBSERVABLE"
        ),
    )


def _inverse_result(
    result: StageAIdentificationResult | InverseIdentificationResult,
) -> tuple[InverseIdentificationResult, Tuple[str, ...], Tuple[str, ...]]:
    if isinstance(result, StageAIdentificationResult):
        return result.inverse_result, result.fitted_parameter_subset, result.warnings
    if isinstance(result, InverseIdentificationResult):
        return result, tuple(result.fitted_parameters), result.warnings
    raise TypeError("identification_runner returned an unsupported result.")


def _sampled_specimen(
    specimen: PhysicalSpecimen, values: Mapping[str, float]
) -> PhysicalSpecimen:
    measurements = tuple(
        replace(item, value=float(values[item.name]))
        for item in specimen.primary_measurements
    )
    return replace(specimen, primary_measurements=measurements)


def _thickness_diagnostic(
    samples: Sequence[MonteCarloSample], quantity: str
) -> ThicknessVarianceDiagnostic:
    accepted = tuple(
        item for item in samples if item.converged and item.apparent_flexural_properties
    )
    if len(accepted) < 2:
        return ThicknessVarianceDiagnostic(quantity, 0.0, 0.0, 0.0)
    h_term = np.asarray([-3.0 * math.log(item.derived_quantities["h_m"]) for item in accepted])
    if quantity == "E_flex":
        stiffness_term = np.asarray(
            [
                math.log(item.fitted_parameters["D11"])
                + math.log(
                    1.0
                    - (item.fitted_parameters["D12"] / item.fitted_parameters["D11"]) ** 2
                )
                for item in accepted
            ]
        )
    else:
        stiffness_term = np.asarray(
            [math.log(item.fitted_parameters["D66"]) for item in accepted]
        )
    total = np.asarray(
        [
            math.log(getattr(item.apparent_flexural_properties, quantity))
            for item in accepted
        ]
    )
    variances = np.asarray(
        [np.var(h_term, ddof=1), np.var(stiffness_term, ddof=1)], dtype=float
    )
    total_variance = float(np.var(total, ddof=1))
    residual = max(total_variance - float(np.sum(variances)), 0.0)
    denominator = float(np.sum(variances)) + residual
    fractions = np.zeros(3) if denominator == 0.0 else np.r_[variances, residual] / denominator
    return ThicknessVarianceDiagnostic(
        quantity=quantity,
        thickness_variance_fraction=float(fractions[0]),
        identified_stiffness_variance_fraction=float(fractions[1]),
        frequency_and_interaction_variance_fraction=float(fractions[2]),
    )


def run_stage_a_monte_carlo(
    specimen: PhysicalSpecimen,
    observations: Sequence[ModalObservation],
    identification_runner: IdentificationRunner,
    configuration: MonteCarloConfiguration,
) -> MonteCarloResult:
    """Propagate primary and frequency uncertainty through the fast Stage-A runner."""

    if not callable(identification_runner):
        raise TypeError("identification_runner must be callable.")
    observations = tuple(observations)
    if not observations:
        raise UncertaintyValidationError("At least one modal observation is required.")
    # Configuration/data errors are rejected before the sampling loop.  A
    # solver failure is a failed sample; missing uncertainty is not.
    for observation in observations:
        _frequency_sigma(
            observation.uncertainty,
            allow_unweighted=configuration.allow_unweighted_frequency,
        )
    nominal = {item.name: float(item.value) for item in specimen.primary_measurements}
    for measurement in specimen.primary_measurements:
        _measurement_distribution(measurement)
    derive_bare_plate_quantities(specimen, nominal)
    rng = np.random.default_rng(configuration.random_seed)
    samples: list[MonteCarloSample] = []
    for sample_index in range(configuration.sample_count):
        primary: Mapping[str, float] = {}
        derived: Mapping[str, float] = {}
        try:
            primary = sample_primary_measurements(
                specimen, rng, max_resample_attempts=configuration.max_resample_attempts
            )
            derived = derive_bare_plate_quantities(specimen, primary)
            sampled_observations = perturb_modal_observations(
                observations,
                rng,
                allow_unweighted=configuration.allow_unweighted_frequency,
                max_resample_attempts=configuration.max_resample_attempts,
            )
            realisation = StageARealisationInput(
                sample_index=sample_index,
                specimen=_sampled_specimen(specimen, primary),
                primary_measurements=primary,
                derived_quantities=derived,
                observations=sampled_observations,
            )
            inverse, subset, result_warnings = _inverse_result(
                identification_runner(realisation)
            )
            fitted = dict(inverse.fixed_parameters)
            fitted.update(inverse.fitted_parameters)
            required = ("D11", "D12", "D66")
            missing = tuple(name for name in required if name not in fitted)
            if missing:
                raise UncertaintyValidationError(
                    "Identification result is missing " + ", ".join(missing)
                )
            converged = bool(inverse.success)
            apparent = (
                apparent_flexural_properties(
                    fitted["D11"], fitted["D12"], fitted["D66"], derived["h_m"]
                )
                if converged
                else None
            )
            samples.append(
                MonteCarloSample(
                    sample_index=sample_index,
                    primary_measurements=dict(primary),
                    derived_quantities=dict(derived),
                    fitted_parameters={name: float(fitted[name]) for name in required},
                    objective=float(inverse.objective_final),
                    converged=converged,
                    fitted_subset=tuple(subset),
                    warnings=tuple(result_warnings),
                    apparent_flexural_properties=apparent,
                    failure=None if converged else "inverse solver did not converge",
                )
            )
        except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
            samples.append(
                MonteCarloSample(
                    sample_index=sample_index,
                    primary_measurements=dict(primary),
                    derived_quantities=dict(derived),
                    fitted_parameters={},
                    objective=None,
                    converged=False,
                    fitted_subset=(),
                    warnings=(),
                    failure=f"{type(exc).__name__}: {exc}",
                )
            )
    successful = sum(item.converged for item in samples)
    failed = len(samples) - successful
    accepted = tuple(item for item in samples if item.converged)
    identified_statistics = {
        name: summarize_samples(
            [item.fitted_parameters[name] for item in accepted],
            successful=successful,
            failed=failed,
        )
        for name in ("D11", "D12", "D66")
    } if accepted else {}
    derived_statistics = {
        name: summarize_samples(
            [getattr(item.apparent_flexural_properties, name) for item in accepted],
            successful=successful,
            failed=failed,
        )
        for name in ("E_flex", "G12_flex", "nu12_flex")
    } if accepted else {}
    fraction = successful / len(samples)
    warnings: list[str] = []
    if failed / len(samples) > configuration.failure_rate_warning_threshold:
        warnings.append(
            f"Monte Carlo failure rate {failed / len(samples):.1%} exceeds configured "
            f"threshold {configuration.failure_rate_warning_threshold:.1%}."
        )
    if not accepted:
        warnings.append("No successful Monte Carlo realisations; intervals are unavailable.")
    diagnostics = {
        name: _thickness_diagnostic(samples, name)
        for name in ("E_flex", "G12_flex")
    }
    return MonteCarloResult(
        samples=tuple(samples),
        identified_statistics=identified_statistics,
        derived_statistics=derived_statistics,
        successful_sample_count=successful,
        failed_sample_count=failed,
        convergence_fraction=float(fraction),
        thickness_diagnostics=diagnostics,
        assumptions=(FREQUENCY_VARIANCE_ASSUMPTION,),
        warnings=tuple(warnings),
        metadata={
            "random_seed": configuration.random_seed,
            "sample_count": configuration.sample_count,
            "primary_sampling": "normal with rejection; zero sigma is fixed",
            "silent_clipping": False,
            "abaqus_per_sample": False,
            "required_runner": "existing Stage-A fast matrix identification pipeline",
        },
    )


def validate_monte_carlo_coverage(
    experiment: CoverageExperiment,
    *,
    parameter_ids: Sequence[str] = ("D11", "D12", "D66"),
    repetitions: int = 100,
    target_coverage: float = 0.95,
    tolerance: float = 0.10,
    random_seed: int = 8675309,
) -> CoverageValidationResult:
    """Run virtual experiments and test empirical coverage of reported MC intervals."""

    if isinstance(repetitions, bool) or int(repetitions) != repetitions or repetitions <= 0:
        raise UncertaintyValidationError("repetitions must be a positive integer.")
    target_coverage = float(target_coverage)
    tolerance = float(tolerance)
    if not 0.0 < target_coverage < 1.0 or not 0.0 <= tolerance < 1.0:
        raise UncertaintyValidationError("target_coverage and tolerance are invalid.")
    identifiers = tuple(str(item) for item in parameter_ids)
    rng = np.random.default_rng(random_seed)
    counts = {name: 0 for name in identifiers}
    successful = 0
    failed = 0
    for index in range(int(repetitions)):
        try:
            truth, result = experiment(rng, index)
            if any(name not in truth or name not in result.identified_statistics for name in identifiers):
                raise UncertaintyValidationError("Coverage experiment omitted a parameter.")
            successful += 1
            for name in identifiers:
                low, high = result.identified_statistics[name].interval_95
                counts[name] += int(low <= float(truth[name]) <= high)
        except (ValueError, RuntimeError, np.linalg.LinAlgError):
            failed += 1
    empirical = {
        name: (counts[name] / successful if successful else 0.0)
        for name in identifiers
    }
    passed = bool(
        successful > 0
        and all(abs(value - target_coverage) <= tolerance for value in empirical.values())
    )
    return CoverageValidationResult(
        repetitions=int(repetitions),
        target_coverage=target_coverage,
        tolerance=tolerance,
        empirical_coverage=empirical,
        covered_counts=counts,
        successful_experiments=successful,
        failed_experiments=failed,
        passed=passed,
        random_seed=int(random_seed),
        metadata={
            "validation_level": 1,
            "heavy_validation_supported_repetitions": "100-1000",
            "interval_source": "Monte Carlo percentiles",
        },
    )


def validate_synthetic_truth_coverage(
    case: SyntheticTruthCase,
    *,
    repetitions: int = 100,
    monte_carlo_samples: int = 200,
    target_coverage: float = 0.95,
    tolerance: float = 0.10,
    random_seed: int = 314159,
) -> CoverageValidationResult:
    """Run a concrete noisy virtual experiment with percentile intervals.

    For every repetition a new noisy experiment is generated.  A parametric
    Monte Carlo ensemble is then generated around that experiment and every
    member is identified by ``case.estimator``.  The routine is intentionally
    estimator-agnostic so the optional 100--1000 repetition path can reuse the
    verified fast matrix solver without ever starting Abaqus.
    """

    for name, value in (("repetitions", repetitions), ("monte_carlo_samples", monte_carlo_samples)):
        if isinstance(value, bool) or int(value) != value or int(value) <= 0:
            raise UncertaintyValidationError(f"{name} must be a positive integer.")
    target_coverage = float(target_coverage)
    tolerance = float(tolerance)
    if not 0.0 < target_coverage < 1.0 or not 0.0 <= tolerance < 1.0:
        raise UncertaintyValidationError("target_coverage and tolerance are invalid.")
    identifiers = tuple(case.truth)
    counts = {name: 0 for name in identifiers}
    rng = np.random.default_rng(random_seed)
    successful = 0
    failed = 0
    for _ in range(int(repetitions)):
        try:
            observed = rng.normal(
                case.nominal_observations, case.observation_standard_deviations
            )
            if np.any(observed <= 0.0):
                raise UncertaintyValidationError(
                    "Synthetic noise produced non-positive modal frequency."
                )
            estimates = {name: [] for name in identifiers}
            for _ in range(int(monte_carlo_samples)):
                sampled = rng.normal(observed, case.observation_standard_deviations)
                if np.any(sampled <= 0.0):
                    raise UncertaintyValidationError(
                        "Synthetic Monte Carlo produced non-positive modal frequency."
                    )
                fitted = case.estimator(np.asarray(sampled, dtype=float))
                for name in identifiers:
                    value = float(fitted[name])
                    if not math.isfinite(value):
                        raise UncertaintyValidationError(
                            f"Synthetic estimator returned invalid {name}."
                        )
                    estimates[name].append(value)
            successful += 1
            for name in identifiers:
                low, high = np.percentile(estimates[name], (2.5, 97.5))
                counts[name] += int(low <= float(case.truth[name]) <= high)
        except (KeyError, ValueError, RuntimeError, np.linalg.LinAlgError):
            failed += 1
    empirical = {
        name: (counts[name] / successful if successful else 0.0)
        for name in identifiers
    }
    passed = bool(
        successful > 0
        and all(abs(value - target_coverage) <= tolerance for value in empirical.values())
    )
    return CoverageValidationResult(
        repetitions=int(repetitions),
        target_coverage=target_coverage,
        tolerance=tolerance,
        empirical_coverage=empirical,
        covered_counts=counts,
        successful_experiments=successful,
        failed_experiments=failed,
        passed=passed,
        random_seed=int(random_seed),
        metadata={
            "validation_level": 1,
            "synthetic_truth_case": True,
            "monte_carlo_samples_per_experiment": int(monte_carlo_samples),
            "interval_source": "Monte Carlo percentiles",
            "abaqus_per_sample": False,
            "heavy_validation_supported_repetitions": "100-1000",
        },
    )


__all__ = [
    "APPARENT_FLEXURAL_LABEL",
    "ApparentFlexuralProperties",
    "CoverageValidationResult",
    "FREQUENCY_VARIANCE_ASSUMPTION",
    "LocalCovarianceDiagnostic",
    "MonteCarloConfiguration",
    "MonteCarloResult",
    "MonteCarloSample",
    "QuantityStatistics",
    "StageARealisationInput",
    "SyntheticTruthCase",
    "ThicknessVarianceDiagnostic",
    "UncertaintyValidationError",
    "apparent_flexural_properties",
    "create_stage_a_pipeline_runner",
    "derive_bare_plate_quantities",
    "local_linear_covariance",
    "perturb_modal_observations",
    "run_stage_a_monte_carlo",
    "sample_primary_measurements",
    "summarize_samples",
    "validate_monte_carlo_coverage",
    "validate_synthetic_truth_coverage",
]
