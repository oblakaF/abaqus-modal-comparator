"""Production orchestration for Stage-A inverse identification.

This module connects the existing reviewed modal comparator to the Stage-A
matrix, sensitivity, identifiability, and inverse-solver services.  Pairing,
MAC, geometry registration, measured-DOF masking, and Hungarian assignment
remain owned by the existing comparator.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import math
from typing import Callable, Mapping, Sequence, Tuple

import numpy as np

from domain.modal_observation import InclusionStatus, ModalCluster, ModalObservation
from domain.parameter_model import ParameterPrior
from modal_core import ComparisonResult, ModalDataset, ModeShape, compare_modal_datasets

from .identifiability_service import (
    IdentifiabilityResult,
    analyze_identifiability,
    whiten_sensitivity,
)
from .inverse_solver import (
    ComparisonPairingProvider,
    ExcludedSolverObservation,
    InverseIdentificationResult,
    InverseSolverConfiguration,
    InverseSolverValidationError,
    ModeAssignment,
    ModeTrackingMode,
    PairingResult,
    StageAParameterBounds,
    solve_stage_a_inverse,
)
from .matrix_model_service import (
    AbaqusDof,
    GeneralizedEigenResult,
    MatrixModelError,
    StageAAffineBasis,
    StageAMatrixParameters,
    solve_generalized_eigenproblem,
)
from .modal_cluster_service import cluster_comparison_result
from .sensitivity_service import compute_stage_a_sensitivity


class StageAIdentificationError(RuntimeError):
    """Stage-A orchestration cannot safely proceed or produce a result."""


class ComparatorPairingError(ValueError):
    """The reviewed comparator could not provide a complete current pairing."""


class PairingProviderMode(str, Enum):
    COMPARATOR = "production_comparator"
    FIXED_PAIR_FALLBACK = "fixed_pair_synthetic_fallback"


@dataclass(frozen=True)
class StageACampaignPolicy:
    """Explicit campaign decisions applied before identifiability analysis."""

    cluster_relative_frequency_gap: float | None = None
    excluded_experimental_mode_ids: Tuple[int, ...] = (1,)
    excluded_mode_reason: str = "probable suspension influence"
    approve_recommended_subset: bool = False
    allow_fixed_pair_fallback: bool = False
    condition_warning_threshold: float = 100.0
    collinearity_warning_threshold: float = 20.0

    def __post_init__(self) -> None:
        if self.cluster_relative_frequency_gap is not None:
            value = float(self.cluster_relative_frequency_gap)
            if not math.isfinite(value) or not 0.0 <= value < 1.0:
                raise ValueError(
                    "cluster_relative_frequency_gap must be finite and in [0, 1)."
                )
            object.__setattr__(self, "cluster_relative_frequency_gap", value)
        mode_ids = tuple(int(item) for item in self.excluded_experimental_mode_ids)
        if any(item <= 0 for item in mode_ids) or len(set(mode_ids)) != len(mode_ids):
            raise ValueError("Campaign-excluded mode IDs must be unique and positive.")
        if mode_ids and not self.excluded_mode_reason.strip():
            raise ValueError("Campaign mode exclusions require an explicit reason.")
        object.__setattr__(self, "excluded_experimental_mode_ids", mode_ids)
        for name in ("condition_warning_threshold", "collinearity_warning_threshold"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be positive and finite.")
            object.__setattr__(self, name, value)


@dataclass(frozen=True)
class StageAIdentificationResult:
    observations: Tuple[ModalObservation, ...]
    clusters: Tuple[ModalCluster, ...]
    effective_observation_count: int
    identifiability: IdentifiabilityResult
    requested_parameter_subset: Tuple[str, ...]
    recommended_parameter_subset: Tuple[str, ...] | None
    fitted_parameter_subset: Tuple[str, ...]
    inverse_result: InverseIdentificationResult
    excluded_observations: Tuple[ExcludedSolverObservation, ...]
    excluded_clusters: Tuple[ModalCluster, ...]
    pairing_provider_mode: PairingProviderMode
    warnings: Tuple[str, ...]
    metadata: Mapping[str, object] = field(default_factory=dict)


ComparatorFunction = Callable[..., ComparisonResult]


class MatrixEigenmodeDatasetAdapter:
    """Convert matrix eigenvectors to the comparator's Abaqus dataset contract.

    Translational Abaqus DOFs 1..3 are copied to the existing comparator grid;
    rotational shell DOFs remain matrix-only and are intentionally not exposed
    as displacement components.
    """

    def __init__(
        self,
        reference_abaqus: ModalDataset,
        basis_dofs: Sequence[AbaqusDof],
    ) -> None:
        modes = reference_abaqus.sorted_modes()
        if not modes:
            raise ComparatorPairingError(
                "The reference comparison has no Abaqus mode geometry."
            )
        reference = modes[0]
        node_ids = np.asarray(reference.node_ids, dtype=object).reshape(-1)
        if len(set(_node_key(item) for item in node_ids)) != len(node_ids):
            raise ComparatorPairingError("Reference Abaqus node IDs must be unique.")
        self._reference_abaqus = reference_abaqus
        self._node_ids = node_ids.copy()
        self._coordinates = np.asarray(reference.coordinates, dtype=float).copy()
        self._basis_dofs = tuple(basis_dofs)
        self._row_by_node = {_node_key(item): index for index, item in enumerate(node_ids)}

    def __call__(self, eigenpairs: GeneralizedEigenResult) -> ModalDataset:
        dofs = eigenpairs.dofs if eigenpairs.dofs is not None else self._basis_dofs
        if len(dofs) != eigenpairs.eigenvectors.shape[0]:
            raise ComparatorPairingError(
                "Eigenvector rows do not match the active Abaqus DOF ordering."
            )
        locations: list[tuple[int, int, int]] = []
        for vector_row, dof in enumerate(dofs):
            if not 1 <= dof.dof <= 3:
                continue
            node_row = self._row_by_node.get(_node_key(dof.node_label))
            if node_row is not None:
                locations.append((vector_row, node_row, dof.dof - 1))
        if not locations:
            raise ComparatorPairingError(
                "No translational matrix DOFs map to the reference comparator grid."
            )

        modes: list[ModeShape] = []
        for mode_index, frequency in enumerate(eigenpairs.frequencies_hz):
            vectors = np.zeros((len(self._node_ids), 3), dtype=float)
            for vector_row, node_row, component in locations:
                vectors[node_row, component] = eigenpairs.eigenvectors[
                    vector_row, mode_index
                ]
            modes.append(
                ModeShape(
                    number=mode_index + 1,
                    frequency_hz=float(frequency),
                    node_ids=self._node_ids.copy(),
                    coordinates=self._coordinates.copy(),
                    vectors=vectors,
                    metadata={
                        "source": "stage_a_affine_matrix_eigensolver",
                        "elastic_mode_index": mode_index + 1,
                    },
                )
            )
        return ModalDataset(
            source_name="Stage-A affine matrix candidate",
            source_path=self._reference_abaqus.source_path,
            modes=modes,
            metadata={"source": "stage_a_affine_matrix_eigensolver"},
            history=list(self._reference_abaqus.history),
        )


class ProductionComparisonPairingProvider:
    """Adapt the current reviewed comparator to ``ComparisonPairingProvider``."""

    def __init__(
        self,
        reference_comparison: ComparisonResult,
        candidate_dataset_adapter: MatrixEigenmodeDatasetAdapter,
        *,
        comparator: ComparatorFunction = compare_modal_datasets,
        coordinate_scale_override: float | None = None,
    ) -> None:
        if not reference_comparison.experimental.modes:
            raise ComparatorPairingError(
                "The reference comparison has no experimental mode shapes."
            )
        self.reference_comparison = reference_comparison
        self.candidate_dataset_adapter = candidate_dataset_adapter
        self.comparator = comparator
        self.coordinate_scale_override = coordinate_scale_override
        self.call_count = 0
        self.failure_count = 0
        self.last_error = ""
        self.last_comparison: ComparisonResult | None = None

    def __call__(
        self,
        observations: Tuple[ModalObservation, ...],
        eigenpairs: GeneralizedEigenResult,
    ) -> PairingResult:
        self.call_count += 1
        experimental_ids = tuple(item.experimental_mode_id for item in observations)
        if len(set(experimental_ids)) != len(experimental_ids):
            raise ComparatorPairingError(
                "Fitting observations must reference unique experimental modes."
            )
        by_number = {
            int(mode.number): mode
            for mode in self.reference_comparison.experimental.modes
        }
        missing = tuple(item for item in experimental_ids if item not in by_number)
        if missing:
            raise ComparatorPairingError(
                "Experimental modes required for re-pairing are unavailable: "
                + ", ".join(map(str, missing))
            )
        experimental = ModalDataset(
            source_name=self.reference_comparison.experimental.source_name,
            source_path=self.reference_comparison.experimental.source_path,
            modes=[by_number[item] for item in experimental_ids],
            metadata=dict(self.reference_comparison.experimental.metadata),
            history=list(self.reference_comparison.experimental.history),
        )
        candidate = self.candidate_dataset_adapter(eigenpairs)
        try:
            comparison = self.comparator(
                candidate,
                experimental,
                coordinate_scale_override=self.coordinate_scale_override,
            )
        except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
            self.failure_count += 1
            self.last_error = str(exc)
            raise ComparatorPairingError(
                f"Production comparator pairing failed: {exc}"
            ) from exc
        paired_by_experimental = {
            int(pair.experimental_mode): pair for pair in comparison.pairs
        }
        missing_pairs = tuple(
            item for item in experimental_ids if item not in paired_by_experimental
        )
        if missing_pairs:
            self.failure_count += 1
            self.last_error = (
                "No accepted comparator pair for experimental mode(s): "
                + ", ".join(map(str, missing_pairs))
            )
            raise ComparatorPairingError(self.last_error)
        self.last_comparison = comparison
        self.last_error = ""
        assignments = tuple(
            ModeAssignment(
                observation_id=observation.observation_id,
                fe_mode_id=int(
                    paired_by_experimental[observation.experimental_mode_id].abaqus_mode
                ),
                mac=paired_by_experimental[observation.experimental_mode_id].mac,
            )
            for observation in observations
        )
        return PairingResult(
            assignments=assignments,
            method="existing reviewed modal comparator",
            warnings=tuple(comparison.warnings),
        )


def create_production_pairing_provider(
    comparison: ComparisonResult,
    affine_model: StageAAffineBasis,
    *,
    comparator: ComparatorFunction = compare_modal_datasets,
    coordinate_scale_override: float | None = None,
) -> ProductionComparisonPairingProvider:
    """Create the production adapter without changing comparator thresholds."""

    adapter = MatrixEigenmodeDatasetAdapter(comparison.abaqus, affine_model.dofs)
    return ProductionComparisonPairingProvider(
        comparison,
        adapter,
        comparator=comparator,
        coordinate_scale_override=coordinate_scale_override,
    )


def _node_key(value: object) -> tuple[str, object]:
    if isinstance(value, np.generic):
        value = value.item()
    return type(value).__name__, value


def _apply_campaign_policy(
    observations: Sequence[ModalObservation],
    policy: StageACampaignPolicy,
) -> Tuple[ModalObservation, ...]:
    excluded_ids = set(policy.excluded_experimental_mode_ids)
    result: list[ModalObservation] = []
    for observation in observations:
        if observation.experimental_mode_id not in excluded_ids:
            result.append(observation)
            continue
        metadata = dict(observation.metadata)
        metadata["pre_campaign_inclusion_status"] = observation.inclusion_status.value
        metadata["pre_campaign_inclusion_reason"] = observation.reason
        result.append(
            replace(
                observation,
                inclusion_status=InclusionStatus.EXCLUDED,
                reason=policy.excluded_mode_reason,
                metadata=metadata,
            )
        )
    return tuple(result)


def _excluded_clusters(
    clusters: Sequence[ModalCluster],
) -> Tuple[ModalCluster, ...]:
    result: list[ModalCluster] = []
    for cluster in clusters:
        metadata = dict(cluster.metadata)
        metadata["pre_solver_inclusion_status"] = cluster.inclusion_status.value
        metadata["pre_solver_reason"] = cluster.reason
        result.append(
            replace(
                cluster,
                inclusion_status=InclusionStatus.EXCLUDED,
                reason="cluster_requires_subspace_solver",
                metadata=metadata,
            )
        )
    return tuple(result)


def _usable_scalar_observations(
    observations: Sequence[ModalObservation],
    clusters: Sequence[ModalCluster],
    configuration: InverseSolverConfiguration,
) -> tuple[
    Tuple[ModalObservation, ...],
    np.ndarray,
    Tuple[ExcludedSolverObservation, ...],
]:
    cluster_members = {
        observation_id: cluster.cluster_id
        for cluster in clusters
        for observation_id in cluster.observation_ids
    }
    usable: list[ModalObservation] = []
    weights: list[float] = []
    excluded: list[ExcludedSolverObservation] = []
    for observation in observations:
        if observation.observation_id in cluster_members:
            excluded.append(
                ExcludedSolverObservation(
                    observation.observation_id,
                    "cluster_member_excluded",
                    f"Member of {cluster_members[observation.observation_id]}; not an independent equation.",
                )
            )
        elif observation.inclusion_status == InclusionStatus.EXCLUDED:
            excluded.append(
                ExcludedSolverObservation(
                    observation.observation_id, "excluded", observation.reason
                )
            )
        elif observation.inclusion_status == InclusionStatus.DOWNWEIGHTED:
            weight = configuration.downweighted_observation_weights.get(
                observation.observation_id
            )
            if weight is None:
                excluded.append(
                    ExcludedSolverObservation(
                        observation.observation_id,
                        "downweighted_without_numerical_weight",
                        "DOWNWEIGHTED observations require an explicit numerical weight.",
                    )
                )
            else:
                usable.append(observation)
                weights.append(float(weight))
        else:
            usable.append(observation)
            weights.append(1.0)
    if not usable:
        raise StageAIdentificationError(
            "No usable scalar modal observations remain after campaign and cluster policy."
        )
    return tuple(usable), np.asarray(weights, dtype=float), tuple(excluded)


def _resolved_uncertainty(
    observations: Tuple[ModalObservation, ...],
    all_observations: Tuple[ModalObservation, ...],
    standard_deviations: float | Sequence[float] | Mapping[str, float] | None,
    covariance: np.ndarray | None,
    covariance_observation_ids: Sequence[str] | None,
) -> tuple[np.ndarray | None, np.ndarray | None]:
    if standard_deviations is not None and covariance is not None:
        raise StageAIdentificationError(
            "Supply standard deviations or covariance, not both."
        )
    if standard_deviations is None:
        selected_covariance = None
    elif isinstance(standard_deviations, Mapping):
        missing = tuple(
            item.observation_id
            for item in observations
            if item.observation_id not in standard_deviations
        )
        if missing:
            raise StageAIdentificationError(
                "Missing standard deviations for usable observations: "
                + ", ".join(missing)
            )
        return (
            np.asarray(
                [standard_deviations[item.observation_id] for item in observations],
                dtype=float,
            ),
            None,
        )
    elif np.isscalar(standard_deviations):
        return np.full(len(observations), float(standard_deviations)), None
    else:
        values = np.asarray(standard_deviations, dtype=float)
        if values.shape == (len(observations),):
            return values, None
        if values.shape == (len(all_observations),):
            by_id = {
                item.observation_id: value
                for item, value in zip(all_observations, values)
            }
            return np.asarray(
                [by_id[item.observation_id] for item in observations], dtype=float
            ), None
        raise StageAIdentificationError(
            "Standard deviations must align with all or usable observations."
        )

    if covariance is None:
        return None, None
    matrix = np.asarray(covariance, dtype=float)
    if covariance_observation_ids is None:
        if matrix.shape != (len(observations), len(observations)):
            raise StageAIdentificationError(
                "Covariance without observation IDs must align with usable observations."
            )
        return None, matrix
    identifiers = tuple(str(item) for item in covariance_observation_ids)
    if len(set(identifiers)) != len(identifiers):
        raise StageAIdentificationError("Covariance observation IDs must be unique.")
    if matrix.shape != (len(identifiers), len(identifiers)):
        raise StageAIdentificationError(
            "Covariance shape must match covariance_observation_ids."
        )
    index_by_id = {item: index for index, item in enumerate(identifiers)}
    try:
        indexes = [index_by_id[item.observation_id] for item in observations]
    except KeyError as exc:
        raise StageAIdentificationError(
            f"Covariance is missing usable observation {exc.args[0]}."
        ) from exc
    return None, matrix[np.ix_(indexes, indexes)]


def _fixed_pairing(
    observations: Tuple[ModalObservation, ...], mode_count: int
) -> PairingResult:
    if any(item.fe_mode_id > mode_count for item in observations):
        raise StageAIdentificationError(
            "Fixed-pair fallback cannot map source FE mode IDs into the computed spectrum."
        )
    return PairingResult(
        assignments=tuple(
            ModeAssignment(item.observation_id, item.fe_mode_id)
            for item in observations
        ),
        method="explicit fixed-pair fallback without experimental-vector tracking",
        warnings=(
            "Production comparator re-pairing was unavailable; fixed-pair fallback is active.",
        ),
    )


def identify_stage_a(
    comparison: ComparisonResult,
    affine_model: StageAAffineBasis,
    initial_parameters: StageAMatrixParameters,
    parameter_bounds: StageAParameterBounds,
    requested_parameter_subset: Sequence[str],
    solver_configuration: InverseSolverConfiguration,
    *,
    design_id: str,
    physical_specimen_id: str,
    test_run_id: str,
    campaign_policy: StageACampaignPolicy | None = None,
    observation_standard_deviations: (
        float | Sequence[float] | Mapping[str, float] | None
    ) = None,
    observation_covariance: np.ndarray | None = None,
    covariance_observation_ids: Sequence[str] | None = None,
    priors: Mapping[str, ParameterPrior] | None = None,
    pairing_provider: ComparisonPairingProvider | None = None,
) -> StageAIdentificationResult:
    """Run the complete production Stage-A pipeline through the existing services."""

    if not isinstance(comparison, ComparisonResult):
        raise TypeError("comparison must be ComparisonResult.")
    if not isinstance(affine_model, StageAAffineBasis):
        raise TypeError("affine_model must be StageAAffineBasis.")
    if not isinstance(initial_parameters, StageAMatrixParameters):
        raise TypeError("initial_parameters must be StageAMatrixParameters.")
    if not isinstance(parameter_bounds, StageAParameterBounds):
        raise TypeError("parameter_bounds must be StageAParameterBounds.")
    if not isinstance(solver_configuration, InverseSolverConfiguration):
        raise TypeError("solver_configuration must be InverseSolverConfiguration.")
    policy = campaign_policy or StageACampaignPolicy()
    requested = tuple(str(item).strip() for item in requested_parameter_subset)
    if not requested or len(set(requested)) != len(requested):
        raise StageAIdentificationError(
            "requested_parameter_subset must contain unique Stage-A parameter IDs."
        )

    cluster_analysis = cluster_comparison_result(
        comparison,
        design_id,
        physical_specimen_id,
        test_run_id,
        relative_frequency_gap=policy.cluster_relative_frequency_gap,
    )
    observations = _apply_campaign_policy(cluster_analysis.observations, policy)
    clusters = _excluded_clusters(cluster_analysis.clusters)
    usable, numerical_weights, preliminary_exclusions = _usable_scalar_observations(
        observations, clusters, solver_configuration
    )
    standard_deviations, covariance = _resolved_uncertainty(
        usable,
        observations,
        observation_standard_deviations,
        observation_covariance,
        covariance_observation_ids,
    )

    initial_eigenpairs = solve_generalized_eigenproblem(
        affine_model.reconstruct_stiffness(initial_parameters),
        affine_model.reconstruct_mass(initial_parameters),
        solver_configuration.mode_count,
        expected_rigid_body_modes=solver_configuration.expected_rigid_body_modes,
        dofs=affine_model.dofs,
    )
    active_provider = pairing_provider
    fallback_reason = ""
    if active_provider is None:
        try:
            active_provider = create_production_pairing_provider(
                comparison, affine_model
            )
        except ComparatorPairingError as exc:
            fallback_reason = str(exc)
    pairing_mode = PairingProviderMode.COMPARATOR
    if active_provider is not None:
        try:
            initial_pairing = active_provider(usable, initial_eigenpairs)
        except (ValueError, RuntimeError, MatrixModelError) as exc:
            fallback_reason = str(exc)
            initial_pairing = None
    else:
        initial_pairing = None
    if initial_pairing is None:
        if not policy.allow_fixed_pair_fallback:
            raise StageAIdentificationError(
                "Production comparison-backed pairing is unavailable: " + fallback_reason
            )
        initial_pairing = _fixed_pairing(usable, solver_configuration.mode_count)
        active_provider = None
        pairing_mode = PairingProviderMode.FIXED_PAIR_FALLBACK

    assignment_by_id = {
        item.observation_id: item.fe_mode_id for item in initial_pairing.assignments
    }
    normalized_observations = tuple(
        replace(
            item,
            fe_mode_id=assignment_by_id.get(item.observation_id, item.fe_mode_id),
        )
        for item in observations
    )

    sensitivity = compute_stage_a_sensitivity(
        affine_model,
        initial_parameters,
        solver_configuration.mode_count,
        expected_rigid_body_modes=solver_configuration.expected_rigid_body_modes,
        finite_difference_relative_steps=(),
    )
    mode_indexes = np.asarray(
        [assignment_by_id[item.observation_id] - 1 for item in usable], dtype=int
    )
    try:
        parameter_indexes = [sensitivity.parameter_ids.index(item) for item in requested]
    except ValueError as exc:
        raise StageAIdentificationError(
            f"Unsupported requested Stage-A parameter: {exc.args[0]}."
        ) from exc
    requested_sensitivity = sensitivity.scaled_sensitivity[
        np.ix_(mode_indexes, parameter_indexes)
    ]
    weighted_sensitivity = numerical_weights[:, np.newaxis] ** 0.5 * requested_sensitivity
    whitening = whiten_sensitivity(
        weighted_sensitivity,
        standard_deviations=standard_deviations,
        covariance=covariance,
        observation_ids=tuple(item.observation_id for item in usable),
        parameter_ids=requested,
        allow_unweighted=solver_configuration.allow_unweighted,
    )
    identifiability = analyze_identifiability(
        whitening,
        condition_warning_threshold=policy.condition_warning_threshold,
        collinearity_warning_threshold=policy.collinearity_warning_threshold,
    )
    recommended = (
        None
        if identifiability.best_identifiable_subset is None
        else identifiability.best_identifiable_subset.parameter_ids
    )
    override_used = False
    subset_selection = "requested_subset_identifiable"
    if identifiability.practically_identifiable:
        fitted_subset = requested
    elif solver_configuration.allow_non_identifiable_subset:
        fitted_subset = requested
        override_used = True
        subset_selection = "explicit_non_identifiable_override"
    elif policy.approve_recommended_subset and recommended is not None:
        fitted_subset = recommended
        subset_selection = "explicitly_approved_recommended_subset"
    else:
        raise StageAIdentificationError(
            "The requested Stage-A subset is not practically identifiable; "
            f"recommended subset: {recommended}. Explicitly approve the recommendation "
            "or enable the non-identifiable override."
        )

    tracking_mode = (
        ModeTrackingMode.COMPARISON_BACKED
        if active_provider is not None
        else ModeTrackingMode.FIXED_PAIR_SYNTHETIC
    )
    configured_solver = replace(
        solver_configuration,
        tracking_mode=tracking_mode,
        allow_non_identifiable_subset=override_used,
    )
    reference = f"stage-a/{design_id}/{physical_specimen_id}/{test_run_id}/initial-svd"
    try:
        inverse_result = solve_stage_a_inverse(
            affine_model,
            normalized_observations + clusters,
            fitted_subset,
            initial_parameters,
            parameter_bounds,
            configured_solver,
            observation_standard_deviations=standard_deviations,
            observation_covariance=covariance,
            priors=priors,
            identifiability=identifiability,
            identifiability_metadata_reference=reference,
            comparison_pairing_provider=active_provider,
        )
    except (InverseSolverValidationError, MatrixModelError, ValueError) as exc:
        raise StageAIdentificationError(f"Stage-A inverse solve failed: {exc}") from exc

    cluster_ids = {item.cluster_id for item in clusters}
    inverse_excluded_observations = tuple(
        item
        for item in inverse_result.excluded_observations
        if item.observation_id not in cluster_ids
    )
    exclusions_by_key = {
        (item.observation_id, item.status): item
        for item in preliminary_exclusions + inverse_excluded_observations
    }
    warnings = list(comparison.warnings)
    warnings.extend(identifiability.warnings)
    warnings.extend(inverse_result.warnings)
    if fallback_reason and pairing_mode == PairingProviderMode.FIXED_PAIR_FALLBACK:
        warnings.append(
            "Production pairing unavailable; explicit fixed-pair fallback used: "
            + fallback_reason
        )
    if subset_selection != "requested_subset_identifiable":
        warnings.append(
            f"Stage-A subset selection: {subset_selection}; fitted {fitted_subset}."
        )
    metadata = {
        "identifiability_reference": reference,
        "non_identifiable_override": override_used,
        "recommended_subset_approved": bool(
            subset_selection == "explicitly_approved_recommended_subset"
        ),
        "subset_selection": subset_selection,
        "campaign_excluded_experimental_mode_ids": policy.excluded_experimental_mode_ids,
        "campaign_exclusion_reason": policy.excluded_mode_reason,
        "cluster_scalar_equations_implemented": False,
        "mac_used_in_objective": False,
        "initial_pairing_signature": initial_pairing.signature,
        "pairing_provider_calls": getattr(active_provider, "call_count", None),
        "pairing_provider_failures": getattr(active_provider, "failure_count", None),
        "pairing_fallback_reason": fallback_reason or None,
        "stiffness_model": (
            "documented affine approximation in (D11, D12, D66); not matrix-exact "
            "over the full domain, validated by real Abaqus evaluations to keep "
            "modal-frequency error below 1e-4 (worst observed 1.6394e-05) across "
            "the SP15 CFRP inverse domain"
        ),
        "mass_model": (
            "constant reference mass"
            if affine_model.mass_derivative_D11 is None
            else (
                "affine in D11 (M = M_ref + (D11-D11_ref) * dM/dD11), validated to "
                "machine precision over the SP15 CFRP inverse domain; invariant to "
                "D12 and D66"
            )
        ),
        "final_direct_abaqus_verification_required": True,
    }
    return StageAIdentificationResult(
        observations=observations,
        clusters=clusters,
        effective_observation_count=len(inverse_result.observation_ids),
        identifiability=identifiability,
        requested_parameter_subset=requested,
        recommended_parameter_subset=recommended,
        fitted_parameter_subset=tuple(fitted_subset),
        inverse_result=inverse_result,
        excluded_observations=tuple(exclusions_by_key.values()),
        excluded_clusters=clusters,
        pairing_provider_mode=pairing_mode,
        warnings=tuple(dict.fromkeys(item for item in warnings if item)),
        metadata=metadata,
    )


__all__ = [
    "ComparatorPairingError",
    "MatrixEigenmodeDatasetAdapter",
    "PairingProviderMode",
    "ProductionComparisonPairingProvider",
    "StageACampaignPolicy",
    "StageAIdentificationError",
    "StageAIdentificationResult",
    "create_production_pairing_provider",
    "identify_stage_a",
]
