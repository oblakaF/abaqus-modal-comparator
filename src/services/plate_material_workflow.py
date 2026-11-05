"""One governed offline inverse workflow over both plate forward backends (MAT-2).

The workflow composes the existing owners and adds no optimizer:

- ``identification_step.run_bounded_lm``: the bounded LM loop, in its opt-in mixed coordinates;
- ``identification_pairing.pair_baseline``: the strict baseline admissibility check;
- ``domain.frozen_observations`` and ``identification_objective``: frozen rows and the whitened
  ln-frequency residuals, where MAC is not an input;
- ``branch_tracker.track_branches`` and ``identification_clusters``: model-to-model identity only;
- ``practical_identifiability``, ``identification_uncertainty``: rank, statistical_sd, pattern, Birge.

Experimental rows are never re-paired. A rejected trial never replaces the accepted state. A result
is at most a DIAGNOSTIC_OPTIMIZER_CANDIDATE, and synthetic recovery is not experimental validation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from pathlib import Path
import time
from typing import Any, Callable, Mapping, Optional, Sequence, Tuple

import numpy as np

from domain.frozen_observations import BaselineIdentity, FreezeStatus, FrozenObservationSet, ObservationRow
from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING
from domain.modal_input_source import ModalInputSource, classify_mode_source
from domain.plate_inverse_problem import (
    FrozenPlateObservation,
    IdentifiabilityDiagnostics,
    InverseRefusalCode,
    InverseScientificStatus,
    LeaveOneFamilyOutRow,
    MaterialReleaseRefusal,
    ModalFrequencyRow,
    ModeIdentityRow,
    NumericalStatus,
    ObservationRole,
    PlateInverseDeclaration,
    PlateInverseResult,
    ResidualTableRow,
    StudyIntent,
    SYNTHETIC_NO_PHYSICAL_SOURCE,
    UncertaintyReport,
    finite_positive,
)
from domain.plate_material_problem import (
    CoordinateObservationSet,
    DofObservationSet,
    EvidenceKind,
    ExecutionStatus,
    ForwardBackendId,
    ForwardProvenance,
    PlateBendingParameters,
    PlateForwardRefusal,
    RefusalCode,
    effective_engineering_constants,
)

from .branch_tracker import BranchTrackingRefusal, FEModalState, TrackingInputError, TrackingResult, track_branches
from .identification_clusters import (
    CLUSTER_TRIGGER_RELATIVE_SPACING,
    ClusterConfirmation,
    ClusterInputError,
    ClusterStatus,
    TriggerRow,
    cluster_triggers,
    confirm_cluster,
)
from .identification_objective import (
    ObjectiveDesign,
    ObjectiveEvaluation,
    ObjectiveInputError,
    RowSigma,
    build_objective_design,
    evaluate_objective,
)
from .identification_pairing import BaselinePairingStatus, ModeFrequency, PairingInputError, pair_baseline
from .identification_step import (
    CoordinateKind,
    EvaluationRefusal,
    InadmissibleTrial,
    LMResult,
    LMSettings,
    LMStatus,
    MixedParameterBounds,
    StepError,
    run_bounded_lm,
)
from .identification_uncertainty import birge_adjustment, residual_pattern_test, residual_terms, statistical_sd
from .plate_forward_adapter import RitzForwardBackend, StageAMatrixForwardBackend
from .plate_ritz_forward import (
    RitzNumericalConfig,
    assemble_ritz_matrices,
    ritz_model_identity,
    ritz_sensitivities,
)
from .practical_identifiability import (
    SD_FIT_LIMIT_LN,
    ObservationCovariance,
    ObservationTerm,
    ParameterDefinition,
    ParameterRole,
    PracticalIdentifiabilityInputError,
    PracticalIdentifiabilityResult,
    PracticalSystem,
    SensitivityMatrix,
    analyse_practical_identifiability,
    assemble_system,
    diagonal_component,
)
from .sensitivity_service import StageASensitivityCoordinate


RITZ_PARAMETERS = ("D11", "D22", "D66", "u")
STAGE_A_PARAMETERS = ("D", "D66", "r")
_POLICY = STRICT_IDENTIFICATION_PAIRING
_INADMISSIBLE_FORWARD_CODES = {RefusalCode.INADMISSIBLE_PARAMETERS, RefusalCode.OUTSIDE_VALIDITY_DOMAIN}
_ROBUSTNESS_NOTE = "range of re-fitted leave-one-family-out estimates; not a standard deviation and not 1 sigma"


class _StudyRefusal(Exception):
    def __init__(self, code: InverseRefusalCode, reason: str, forward_code: Optional[str] = None) -> None:
        super().__init__(f"{code.value}: {reason}")
        self.code = code
        self.reason = reason
        self.forward_code = forward_code


def release_material_property(result: PlateInverseResult) -> None:
    """Always refuses: this workflow cannot release a material property or a calibration."""

    raise MaterialReleaseRefusal(
        f"Status {result.scientific_status.value} with {result.release_status.value} is a diagnostic result. "
        "It cannot be exported as an accepted material property or a released engineering calibration, and "
        "it does not change into either one."
    )


@dataclass(frozen=True)
class ForwardState:
    """One solved model state. ``shapes`` are modes by DOFs; ``observed`` are observations by modes."""

    parameters: Mapping[str, float]
    mode_numbers: Tuple[int, ...]
    frequencies_hz: Tuple[float, ...]
    shapes: np.ndarray
    observed: np.ndarray
    max_eigen_residual: float
    max_orthonormality_error: float


class RitzInverseModel:
    """``KIRCHHOFF_RITZ_4D`` in (ln D11, ln D22, ln D66, u), with D12 = u*D22."""

    names = RITZ_PARAMETERS
    kinds = (CoordinateKind.LOG, CoordinateKind.LOG, CoordinateKind.LOG, CoordinateKind.LINEAR)
    backend_id = ForwardBackendId.KIRCHHOFF_RITZ_4D

    def __init__(self, declaration: PlateInverseDeclaration) -> None:
        self.declaration = declaration
        if declaration.geometry is None or declaration.degree_x is None or declaration.degree_y is None:
            raise _StudyRefusal(InverseRefusalCode.DECLARATION_INVALID, "The Ritz backend needs geometry and basis degrees.")
        self.config = RitzNumericalConfig(declaration.degree_x, declaration.degree_y, declaration.forward_mode_count)
        self.backend = RitzForwardBackend(
            declaration.geometry,
            self.config,
            ForwardProvenance(declaration.evidence_kind, declaration.provenance),
            limits=declaration.budget.limits,
        )
        self.model_identity = ritz_model_identity(declaration.geometry, self.config)
        matrices = assemble_ritz_matrices(declaration.geometry, self.config, declaration.budget.limits)
        self.weights = np.diag(matrices.M_area).copy()
        self.node_set_identity = f"ritz-coefficients:{self.config.degree_x}:{self.config.degree_y}"
        self.package_validation_text: Optional[str] = None
        self.package_validation_status = "NOT_APPLICABLE"

    def stiffness(self, parameters: Mapping[str, float]) -> PlateBendingParameters:
        return PlateBendingParameters(
            parameters["D11"], parameters["D22"], parameters["u"] * parameters["D22"], parameters["D66"]
        )

    def validated_range_refusal(self, declaration: PlateInverseDeclaration) -> Optional[str]:
        return None  # the Ritz model has no stored domain; admissibility is checked at each point

    def solve(self, parameters: Mapping[str, float]) -> ForwardState:
        result = self.backend.evaluate(self.stiffness(parameters), self.declaration.observation_set)
        if result.execution_status is not ExecutionStatus.COMPLETED:
            raise PlateForwardRefusal(result.refusal_code, result.refusal_reason)
        return _state_from_result(parameters, result)

    def analytic_sensitivities(self, parameters: Mapping[str, float], mode_count: int) -> Optional[np.ndarray]:
        """Rows are modes 1..mode_count. Modes without a single-branch derivative are NaN."""

        return ritz_sensitivities(self.backend.solve(self.stiffness(parameters))).mixed[:mode_count]


class StageAInverseModel:
    """``STAGE_A_MATRIX_3D`` in the existing (D, D66, r) parameterization, with D22 = D11 = D."""

    names = STAGE_A_PARAMETERS
    kinds = (CoordinateKind.LOG, CoordinateKind.LOG, CoordinateKind.LINEAR)
    backend_id = ForwardBackendId.STAGE_A_MATRIX_3D
    weights = None

    def __init__(self, declaration: PlateInverseDeclaration, package_directory: Path | str) -> None:
        self.declaration = declaration
        try:
            self.backend = StageAMatrixForwardBackend.open(
                package_directory,
                expected_specimen_id=declaration.specimen_id,
                expected_model_id=declaration.stage_a_model_id,
                limits=declaration.budget.limits,
            )
        except PlateForwardRefusal as refusal:
            raise _StudyRefusal(InverseRefusalCode.PACKAGE_REFUSED, refusal.reason, refusal.code.value) from refusal
        if declaration.stage_a_model_id is None:
            raise _StudyRefusal(InverseRefusalCode.DECLARATION_INVALID, "A Stage-A study must name its expected model.")
        self.model_identity = self.backend.model_identity
        self.node_set_identity = self.backend.basis_identity["dof_mapping_hash"]
        # A package's own statement is carried as text. It is not physical proof and changes no status.
        self.package_validation_text = self.backend.inspection.manifest.get("validation_evidence")
        self.package_validation_status = "NOT_ASSESSED_NOT_PHYSICAL_PROOF"

    def stiffness(self, parameters: Mapping[str, float]) -> PlateBendingParameters:
        d = parameters["D"]
        return PlateBendingParameters(d, d, parameters["r"] * d, parameters["D66"])

    def validated_range_refusal(self, declaration: PlateInverseDeclaration) -> Optional[str]:
        domain = self.backend.validity_domain_si()
        box = {item.name: item for item in declaration.parameters}
        checks = {
            "D": (box["D"].lower, box["D"].upper, domain["D11"]),
            "D66": (box["D66"].lower, box["D66"].upper, domain["D66"]),
        }
        for name, (low, high, (lower, upper)) in checks.items():
            if low < lower or high > upper:
                return f"{name} bounds [{low:g}, {high:g}] exceed the stored domain [{lower:g}, {upper:g}] N*m."
        corners = [r * d for r in (box["r"].lower, box["r"].upper) for d in (box["D"].lower, box["D"].upper)]
        lower, upper = domain["D12"]
        if min(corners) < lower or max(corners) > upper:
            return f"D12 = r*D spans [{min(corners):g}, {max(corners):g}], beyond the stored domain [{lower:g}, {upper:g}] N*m."
        return None

    def solve(self, parameters: Mapping[str, float]) -> ForwardState:
        result = self.backend.evaluate(
            self.stiffness(parameters), self.declaration.forward_mode_count, self.declaration.observation_set
        )
        if result.execution_status is not ExecutionStatus.COMPLETED:
            raise PlateForwardRefusal(result.refusal_code, result.refusal_reason)
        return _state_from_result(parameters, result)

    def analytic_sensitivities(self, parameters: Mapping[str, float], mode_count: int) -> Optional[np.ndarray]:
        """Existing Stage-A sensitivities with the stored mass term; None when a mode has none."""

        try:
            result = self.backend.sensitivities(
                self.stiffness(parameters), mode_count, coordinate_system=StageASensitivityCoordinate.BALANCED
            )
        except PlateForwardRefusal:
            return None
        return np.asarray(result.scaled_sensitivity, dtype=float)


def _state_from_result(parameters: Mapping[str, float], result: Any) -> ForwardState:
    frequencies = tuple(float(value) for value in result.frequencies_hz)
    return ForwardState(
        parameters=dict(parameters),
        mode_numbers=tuple(range(1, len(frequencies) + 1)),
        frequencies_hz=frequencies,
        shapes=np.asarray(result.shape.values, dtype=float).T,
        observed=np.asarray(result.observation.values, dtype=float),
        max_eigen_residual=float(result.diagnostics["max_eigen_residual"]),
        max_orthonormality_error=float(result.diagnostics["max_orthonormality_error"]),
    )


def _declaration_refusal(declaration: PlateInverseDeclaration) -> Optional[Tuple[InverseRefusalCode, str]]:
    """Checks that need no solve. Each returns one specific reason."""

    invalid = InverseRefusalCode.DECLARATION_INVALID
    if not isinstance(declaration.intent, StudyIntent):
        return (
            InverseRefusalCode.UNSUPPORTED_STUDY_INTENT,
            f"Study intent {declaration.intent!r} is not supported. This workflow has no specimen-calibration "
            "path, and a material refusal never falls back to one.",
        )
    if declaration.intent is not StudyIntent.SYNTHETIC_SOFTWARE_TEST or declaration.evidence_kind is not EvidenceKind.SYNTHETIC:
        return (
            InverseRefusalCode.NOT_AUTHORIZED,
            f"MAT-2 authorizes SYNTHETIC inverse execution only; this is {declaration.intent.value} with "
            f"{declaration.evidence_kind.value} evidence. Text in execution_authorization does not change that.",
        )
    rows = declaration.rows
    identifiers = [row.row_id for row in rows]
    if not rows or len(set(identifiers)) != len(identifiers):
        return invalid, "Row identities must be present and unique."
    model_modes = [row.model_mode for row in rows]
    if len(set(model_modes)) != len(model_modes) or any(
        isinstance(mode, bool) or not isinstance(mode, int) or mode < 1 for mode in model_modes
    ):
        return invalid, "Frozen model modes must be unique positive integers."
    if max(model_modes) >= declaration.forward_mode_count:
        return invalid, "The solved window needs at least one mode above the highest frozen mode."
    for row in rows:
        if not finite_positive(row.experimental_hz):
            return invalid, f"{row.row_id}: the experimental frequency must be finite and positive."
        source = classify_mode_source({"mode_source": row.mode_source, "dataset_type": row.dataset_type})
        if source is not ModalInputSource.CURVE_FITTED:
            return (
                InverseRefusalCode.INPUT_SOURCE_REFUSED,
                f"{row.row_id}: mode source {row.mode_source!r} is {source.value}; only curve-fitted modes are "
                "identification input. FRF peaks stay available for viewing only.",
            )
    fit_families = {row.family for row in rows if row.role is ObservationRole.FIT}
    holdout_families = {row.family for row in rows if row.role is ObservationRole.HOLDOUT}
    if not holdout_families:
        return InverseRefusalCode.MISSING_HOLDOUT, "The declaration has no HOLDOUT family."
    if fit_families & holdout_families:
        return (
            InverseRefusalCode.HOLDOUT_NOT_INDEPENDENT,
            f"Families {sorted(fit_families & holdout_families)} appear in both FIT and HOLDOUT.",
        )
    if not fit_families:
        return invalid, "The declaration has no FIT family."
    for row in rows:
        if row.setup_sd_ln is None:
            return InverseRefusalCode.INCOMPLETE_COVARIANCE, f"{row.row_id}: Sigma_setup is missing and is never defaulted."
        sds = [row.setup_sd_ln] + ([] if row.measurement_sd_ln is None else [row.measurement_sd_ln])
        if not all(finite_positive(value) for value in sds):
            return InverseRefusalCode.INCOMPLETE_COVARIANCE, f"{row.row_id}: covariance entries must be finite and positive."
    known = set(identifiers)
    for cluster in declaration.confirmed_clusters:
        if len(cluster) != 2 or not set(cluster) <= known:
            return invalid, f"Cluster {cluster} must name two frozen rows."
    return None


class _Study:
    """Solve accounting and health checks. Every forward evaluation passes through ``solve``."""

    def __init__(self, declaration: PlateInverseDeclaration, model: Any, cancel, clock) -> None:
        self.declaration, self.model, self.cancel, self.clock = declaration, model, cancel, clock
        self.started = clock()
        self.solves = 0
        self.stop: Optional[_StudyRefusal] = None
        self.last_inadmissible: Optional[str] = None
        self.max_eigen_residual = 0.0
        self.max_orthonormality_error = 0.0

    def _halt(self, code: InverseRefusalCode, reason: str, forward_code: Optional[str] = None) -> None:
        self.stop = _StudyRefusal(code, reason, forward_code)
        raise EvaluationRefusal(self.stop.reason)

    @property
    def remaining(self) -> int:
        return self.declaration.budget.max_solves - self.solves

    def solve(self, parameters: Mapping[str, float]) -> ForwardState:
        if self.cancel is not None and self.cancel():
            self._halt(InverseRefusalCode.CANCELLED, "Cancelled at a safe point between solves.")
        if self.clock() - self.started > self.declaration.budget.max_elapsed_seconds:
            self._halt(InverseRefusalCode.BUDGET_EXHAUSTED, "The elapsed-time budget is used up.")
        if self.remaining <= 0:
            self._halt(InverseRefusalCode.BUDGET_EXHAUSTED, "The solve budget is used up.")
        self.solves += 1
        try:
            state = self.model.solve(parameters)
        except PlateForwardRefusal as refusal:
            if refusal.code in _INADMISSIBLE_FORWARD_CODES:
                self.last_inadmissible = refusal.reason
                raise InadmissibleTrial(refusal.reason) from refusal
            self._halt(InverseRefusalCode.FORWARD_REFUSED, refusal.reason, refusal.code.value)
        policy = self.declaration.policy
        self.max_eigen_residual = max(self.max_eigen_residual, state.max_eigen_residual)
        self.max_orthonormality_error = max(self.max_orthonormality_error, state.max_orthonormality_error)
        if not (state.max_eigen_residual <= policy.max_eigen_residual):
            self._halt(
                InverseRefusalCode.NUMERICAL_HEALTH_FAILED,
                f"Eigenpair residual {state.max_eigen_residual:.3g} exceeds the declared {policy.max_eigen_residual:.3g}.",
            )
        if not (state.max_orthonormality_error <= policy.max_orthonormality_error):
            self._halt(
                InverseRefusalCode.NUMERICAL_HEALTH_FAILED,
                f"Orthonormality error {state.max_orthonormality_error:.3g} exceeds the declared "
                f"{policy.max_orthonormality_error:.3g}.",
            )
        return state

    def fe_state(self, state: ForwardState, label: str) -> FEModalState:
        return FEModalState(
            label, self.model.model_identity, self.model.node_set_identity,
            state.mode_numbers, state.frequencies_hz, state.shapes,
        )

    def bounds(self) -> MixedParameterBounds:
        policy = self.declaration.policy
        parameters = self.declaration.parameters
        return MixedParameterBounds(
            tuple(item.name for item in parameters),
            tuple(float(item.lower) for item in parameters),
            tuple(float(item.upper) for item in parameters),
            tuple(self.model.kinds),
            tuple(
                policy.linear_finite_difference_step if kind is CoordinateKind.LINEAR else None
                for kind in self.model.kinds
            ),
        )

    def settings(self, solve_budget: int) -> LMSettings:
        policy = self.declaration.policy
        return LMSettings(
            mu_initial=policy.mu_initial,
            mu_decrease=policy.mu_decrease,
            max_step_attempts=policy.max_step_attempts,
            solve_budget=max(solve_budget, 1),
            max_iterations=policy.max_iterations,
            stop_fraction=policy.stop_fraction,
            finite_difference_step=policy.finite_difference_step,
        )


class _TrackedEvaluator:
    """Residuals of one design, tracked from the last accepted state only."""

    def __init__(
        self,
        study: _Study,
        design: ObjectiveDesign,
        frozen: FrozenObservationSet,
        clusters: Sequence[Tuple[str, str]],
        reference: ForwardState,
        rows: Mapping[str, int],
    ) -> None:
        self.study, self.design, self.frozen, self.clusters = study, design, frozen, clusters
        self.reference, self.rows = reference, dict(rows)
        self.min_mac = {row: 1.0 for row in rows}
        self.last: Optional[Tuple[Tuple[float, ...], ForwardState, TrackingResult, ObjectiveEvaluation]] = None

    def _weights(self) -> Optional[np.ndarray]:
        return self.study.model.weights

    def evaluate(self, parameters: Mapping[str, float]) -> ObjectiveEvaluation:
        state = self.study.solve(parameters)
        tracking = track_branches(
            _POLICY,
            self.study.fe_state(self.reference, "accepted"),
            self.study.fe_state(state, "candidate"),
            self.rows,
            self.clusters,
            self._weights(),
        )
        evaluation = evaluate_objective(self.design, self.frozen, tracking)
        self.last = (tuple(parameters[name] for name in self.study.model.names), state, tracking, evaluation)
        return evaluation

    def residuals(self, parameters: Mapping[str, float]) -> np.ndarray:
        return self.evaluate(parameters).residuals

    def accept(self, parameters: Mapping[str, float]) -> None:
        key = tuple(parameters[name] for name in self.study.model.names)
        if self.last is None or self.last[0] != key:
            raise EvaluationRefusal("The accepted point is not the last evaluated trial.")
        _, state, tracking, _ = self.last
        self.reference = state
        for branch in tracking.branches:
            self.rows[branch.row_id] = branch.candidate_mode
            self.min_mac[branch.row_id] = min(self.min_mac[branch.row_id], branch.mac)
        for cluster in tracking.clusters:
            for row, mode in zip(cluster.row_ids, cluster.candidate_modes):
                self.rows[row] = mode
                self.min_mac[row] = min(self.min_mac[row], min(cluster.cos2))


def _complex_mac(left: np.ndarray, right: np.ndarray) -> float:
    denominator = float(np.real(np.vdot(left, left)) * np.real(np.vdot(right, right)))
    if denominator <= 0.0:
        return math.nan
    return float(abs(np.vdot(left, right)) ** 2 / denominator)


def _subspace_min_cos2(left: np.ndarray, right: np.ndarray) -> float:
    q_left, _ = np.linalg.qr(left)
    q_right, _ = np.linalg.qr(right.astype(complex))
    return float(np.min(np.linalg.svd(q_left.conj().T @ q_right, compute_uv=False)) ** 2)


def _experimental_shape(row: FrozenPlateObservation, count: int) -> np.ndarray:
    if len(row.shape) != count:
        raise _StudyRefusal(
            InverseRefusalCode.DECLARATION_INVALID,
            f"{row.row_id}: {len(row.shape)} shape values for {count} declared observations.",
        )
    return np.asarray(row.shape, dtype=complex)


def _baseline_check(
    declaration: PlateInverseDeclaration, state: ForwardState, clusters: Sequence[Tuple[str, str]]
) -> Mapping[str, float]:
    """Verify the frozen mapping under the strict policy. It never chooses or changes a mapping."""

    count = state.observed.shape[0]
    by_id = {row.row_id: row for row in declaration.rows}
    macs: dict[str, float] = {}
    clustered = {row for pair in clusters for row in pair}
    for left, right in clusters:
        rows = [by_id[left], by_id[right]]
        experimental = np.column_stack([_experimental_shape(row, count) for row in rows])
        model = state.observed[:, [row.model_mode - 1 for row in rows]]
        cos2 = _subspace_min_cos2(experimental, model)
        if not cos2 >= _POLICY.minimum_mac:
            raise _StudyRefusal(
                InverseRefusalCode.BASELINE_PAIRING_REFUSED,
                f"Cluster {left}+{right}: subspace cos^2 {cos2:.3f} is below {_POLICY.minimum_mac}.",
            )
        for row in rows:
            error = state.frequencies_hz[row.model_mode - 1] / float(row.experimental_hz) - 1.0
            if abs(error) > _POLICY.maximum_relative_frequency_error:
                raise _StudyRefusal(
                    InverseRefusalCode.BASELINE_PAIRING_REFUSED,
                    f"{row.row_id}: start frequency differs by {error:+.1%}, outside the strict gate.",
                )
            macs[row.row_id] = cos2
    singles = [row for row in declaration.rows if row.row_id not in clustered]
    if not singles:
        return macs
    cluster_modes = {by_id[row].model_mode for row in clustered}
    columns = [index for index, mode in enumerate(state.mode_numbers) if mode not in cluster_modes]
    mac = np.array(
        [[_complex_mac(_experimental_shape(row, count), state.observed[:, column]) for column in columns] for row in singles]
    )
    pairing = pair_baseline(
        _POLICY,
        [ModeFrequency(row.experimental_mode, float(row.experimental_hz)) for row in singles],
        [ModeFrequency(state.mode_numbers[column], state.frequencies_hz[column]) for column in columns],
        mac,
    )
    if pairing.status is not BaselinePairingStatus.COMPLETE:
        raise _StudyRefusal(
            InverseRefusalCode.BASELINE_PAIRING_REFUSED,
            f"The strict baseline pairing is {pairing.status.value}: {[item.reason for item in pairing.unpaired]}.",
        )
    assigned = {pair.experimental_mode: pair.fe_mode for pair in pairing.pairs}
    for index, row in enumerate(singles):
        if assigned.get(row.experimental_mode) != row.model_mode:
            raise _StudyRefusal(
                InverseRefusalCode.BASELINE_PAIRING_REFUSED,
                f"{row.row_id}: frozen as model mode {row.model_mode}, but the strict baseline check assigns "
                f"{assigned.get(row.experimental_mode)}. The mapping is not changed here.",
            )
        macs[row.row_id] = float(mac[index, columns.index(row.model_mode - 1)])
    return macs


def _refuse_repeated_rows(declaration: PlateInverseDeclaration, baseline: ForwardState) -> None:
    """A frozen mode on a numerically repeated eigenvalue has no defined individual eigenvector.

    The eigensolver returns an arbitrary basis of the eigenspace, and it differs between platforms. The
    review below and the baseline check compare individual shapes, so their outcome would depend on that
    basis. The partner may be a mode that no row selects, so each frozen mode is compared with its two
    neighbours in the whole solved ascending spectrum. Only frequencies are read here. The declaration
    check guarantees a solved mode above the highest frozen mode, so no upper neighbour goes unchecked.
    """

    limit = declaration.policy.repeated_frequency_relative_spacing
    spectrum = baseline.frequencies_hz
    frozen = {row.model_mode: row.row_id for row in declaration.rows}
    for mode in sorted(frozen):
        for neighbour in (mode - 1, mode + 1):
            if not 1 <= neighbour <= len(spectrum):
                continue
            low, high = sorted((spectrum[mode - 1], spectrum[neighbour - 1]))
            if high / low - 1.0 <= limit:
                partner = (
                    f"row {frozen[neighbour]} (model mode {neighbour})"
                    if neighbour in frozen
                    else f"model mode {neighbour}, which is not frozen"
                )
                raise _StudyRefusal(
                    InverseRefusalCode.UNRESOLVED_MODAL_CLUSTER,
                    f"Row {frozen[mode]} (model mode {mode}) and {partner}: model frequencies coincide within "
                    f"{limit:g} at the start point, so these shapes are an arbitrary basis of the eigenspace and "
                    "neither individual identity nor the cluster review is defined there.",
                )


def _cluster_review(
    study: _Study, baseline: ForwardState, p0: np.ndarray, bounds: MixedParameterBounds
) -> Tuple[ClusterConfirmation, ...]:
    """Examine each frequency trigger under the governed perturbations; refuse whatever stays unresolved."""

    declaration = study.declaration
    _refuse_repeated_rows(declaration, baseline)
    triggers = cluster_triggers(
        [
            TriggerRow(row.row_id, float(row.experimental_hz), baseline.frequencies_hz[row.model_mode - 1])
            for row in declaration.rows
        ],
        CLUSTER_TRIGGER_RELATIVE_SPACING,
    )
    declared = {frozenset(pair) for pair in declaration.confirmed_clusters}
    if not triggers:
        if declared:
            raise _StudyRefusal(
                InverseRefusalCode.UNRESOLVED_MODAL_CLUSTER, "A declared cluster has no frequency trigger at the start point."
            )
        return ()
    step = declaration.policy.cluster_perturbation_step
    perturbed: dict[str, np.ndarray] = {}
    for j, name in enumerate(bounds.names):
        up, down = bounds.stencil(p0, j, step, step)
        for sign, point in (("+", up), ("-", down)):
            state = study.solve({key: float(value) for key, value in zip(bounds.names, point)})
            perturbed[name + sign] = state.shapes
    directions = tuple(perturbed)
    by_id = {row.row_id: row for row in declaration.rows}
    confirmed = []
    resolved = set()
    weights = study.model.weights
    for trigger in triggers:
        modes = [by_id[row].model_mode - 1 for row in trigger.row_ids]
        review = confirm_cluster(trigger.row_ids, baseline.shapes[modes], perturbed, weights, directions)
        if review.status is ClusterStatus.CONFIRMED:
            if frozenset(trigger.row_ids) not in declared:
                raise _StudyRefusal(
                    InverseRefusalCode.UNRESOLVED_MODAL_CLUSTER,
                    f"Rows {trigger.row_ids} form a cluster that the declaration treats as separate observations.",
                )
            confirmed.append(review)
            resolved.add(frozenset(trigger.row_ids))
        elif review.status is not ClusterStatus.INDEPENDENT:
            raise _StudyRefusal(
                InverseRefusalCode.UNRESOLVED_MODAL_CLUSTER,
                f"Rows {trigger.row_ids}: {review.status.value}. {' '.join(review.reasons)}",
            )
    if declared - resolved:
        raise _StudyRefusal(
            InverseRefusalCode.UNRESOLVED_MODAL_CLUSTER,
            f"Declared clusters {[sorted(item) for item in declared - resolved]} were not confirmed.",
        )
    return tuple(confirmed)


def _row_sigmas(declaration: PlateInverseDeclaration) -> Mapping[str, RowSigma]:
    return {
        row.row_id: RowSigma(row.measurement_sd_ln, float(row.setup_sd_ln), bool(row.setup_provisional))
        for row in declaration.rows
    }


def _point(bounds: MixedParameterBounds, values: np.ndarray) -> Mapping[str, float]:
    return {name: float(value) for name, value in zip(bounds.names, values)}


def _fit_sensitivity(
    evaluator: _TrackedEvaluator, p: np.ndarray, bounds: MixedParameterBounds, step: float
) -> np.ndarray:
    """Central differences of tracked ln-frequency terms per coordinate; a cluster stays one term."""

    columns = []
    for j in range(len(p)):
        up, down = bounds.stencil(p, j, step, step)
        high = evaluator.evaluate(_point(bounds, up)).fit_terms
        low = evaluator.evaluate(_point(bounds, down)).fit_terms
        difference = bounds.to_x(up)[j] - bounds.to_x(down)[j]
        columns.append([(a.log_ratio - b.log_ratio) / difference for a, b in zip(high, low)])
    return np.column_stack(columns)


def _practical_system(
    bounds: MixedParameterBounds, evaluation: ObjectiveEvaluation, sensitivity: np.ndarray, provisional: bool
) -> PracticalSystem:
    terms = tuple(ObservationTerm(term.term_id, term.row_ids) for term in evaluation.fit_terms)
    term_ids = tuple(term.term_id for term in terms)
    matrix = SensitivityMatrix(
        terms,
        tuple(ParameterDefinition(name, ParameterRole.GLOBAL) for name in bounds.names),
        tuple(tuple(float(value) for value in row) for row in sensitivity),
        {name: "tracked central differences of ln f per declared coordinate" for name in bounds.names},
    )
    component = diagonal_component(
        "Sigma_declared_diagonal",
        term_ids,
        {term.term_id: term.sigma for term in evaluation.fit_terms},
        provisional,
        "declared per-row measurement and setup standard deviations; no off-diagonal terms were supplied",
    )
    return assemble_system(matrix, ObservationCovariance(term_ids, (component,)), ())


def _not_observable(
    analysis: PracticalIdentifiabilityResult, bounds: MixedParameterBounds
) -> Tuple[str, ...]:
    """SPEC 10 limit of 8 % applies to log coordinates only. A signed coordinate has no approved limit."""

    log_names = {name for name, kind in zip(bounds.names, bounds.kinds) if kind is CoordinateKind.LOG}
    return tuple(
        f"{name}: sd {analysis.sd_ln[name]:.3g} in ln p exceeds {SD_FIT_LIMIT_LN}"
        for name in bounds.names
        if name in log_names and analysis.exceeds_sd_fit_limit[name]
    )


def _diagnostics(
    analysis: PracticalIdentifiabilityResult, sensitivity: np.ndarray, term_ids: Sequence[str]
) -> IdentifiabilityDiagnostics:
    return IdentifiabilityDiagnostics(
        status=analysis.status.value,
        rank=analysis.rank,
        parameter_ids=analysis.parameter_ids,
        singular_values=analysis.singular_values,
        condition_number=analysis.condition_number,
        correlation=analysis.correlation,
        pairwise_cosines=dict(analysis.pairwise_cosines),
        projection_q={name: item.q for name, item in analysis.projections.items()},
        sensitivity=tuple(tuple(float(value) for value in row) for row in sensitivity),
        term_ids=tuple(term_ids),
    )


def _frozen_set(
    declaration: PlateInverseDeclaration, baseline: ForwardState, macs: Mapping[str, float]
) -> FrozenObservationSet:
    """The frozen rows of a SYNTHETIC study, which has no input deck, geometry file or measurement file.

    Model, registration and declaration identities stay in the declaration, under their own names.
    """

    if declaration.evidence_kind is not EvidenceKind.SYNTHETIC:
        raise _StudyRefusal(
            InverseRefusalCode.NOT_AUTHORIZED, "Physical-source identities cannot be verified by this workflow."
        )
    observations = declaration.observation_set
    items = observations.points if isinstance(observations, CoordinateObservationSet) else observations.items
    identity = BaselineIdentity(
        forward_model_id=declaration.backend_id.value,
        job_name=SYNTHETIC_NO_PHYSICAL_SOURCE,
        generated_inp_sha256=SYNTHETIC_NO_PHYSICAL_SOURCE,
        fe_geometry_sha256=SYNTHETIC_NO_PHYSICAL_SOURCE,
        registration_hash=SYNTHETIC_NO_PHYSICAL_SOURCE,
        experimental_source_sha256=SYNTHETIC_NO_PHYSICAL_SOURCE,
        modal_set=declaration.study_id,
        measured_dofs=tuple(item.observation_id for item in items),
        evidence_source=declaration.evidence_kind.value,
        evidence_record_sha256=None,
    )
    rows = tuple(
        ObservationRow(
            row.row_id,
            row.experimental_mode,
            float(row.experimental_hz),
            row.model_mode,
            baseline.frequencies_hz[row.model_mode - 1],
            float(macs[row.row_id]),
            baseline.frequencies_hz[row.model_mode - 1] / float(row.experimental_hz) - 1.0,
        )
        for row in declaration.rows
    )
    return FrozenObservationSet(
        identity, _POLICY.policy_id, _POLICY.policy_hash, FreezeStatus.FROZEN, (), rows, (), (), ()
    )


def _residual_table(
    initial: Sequence[Any], final: Sequence[Any], role: ObservationRole, families: Mapping[str, str]
) -> Tuple[ResidualTableRow, ...]:
    table = []
    for before, after in zip(initial, final):
        names = sorted({families[row] for row in after.row_ids})
        table.append(
            ResidualTableRow(
                after.term_id, after.row_ids, role, "+".join(names), after.sigma,
                before.log_ratio, after.log_ratio, before.residual, after.residual,
            )
        )
    return tuple(table)


def _analytic_difference(
    model: Any, parameters: Mapping[str, float], rows: Mapping[str, int], evaluation: ObjectiveEvaluation, sensitivity: np.ndarray
) -> Optional[float]:
    """Largest difference from the analytic derivatives on single-row FIT terms; None when none is defined."""

    needed = max(rows.values())
    analytic = model.analytic_sensitivities(parameters, needed)
    if analytic is None:
        return None
    worst = None
    for index, term in enumerate(evaluation.fit_terms):
        if len(term.row_ids) != 1:
            continue
        row = analytic[rows[term.row_ids[0]] - 1]
        if not np.isfinite(row).all():
            continue
        difference = float(np.max(np.abs(row - sensitivity[index])))
        worst = difference if worst is None else max(worst, difference)
    return worst


def _leave_one_family_out(
    study: _Study,
    frozen: FrozenObservationSet,
    clusters: Sequence[ClusterConfirmation],
    final_state: ForwardState,
    rows: Mapping[str, int],
    p_hat: np.ndarray,
    bounds: MixedParameterBounds,
    system: PracticalSystem,
) -> Tuple[Tuple[LeaveOneFamilyOutRow, ...], Mapping[str, Tuple[float, float]]]:
    """Re-fit without each FIT family, on the same frozen rows. HOLDOUT rows never enter a fit."""

    declaration = study.declaration
    families = {row.row_id: row.family for row in declaration.rows}
    fit_families = sorted({row.family for row in declaration.rows if row.role is ObservationRole.FIT})
    holdout = [row.row_id for row in declaration.rows if row.role is ObservationRole.HOLDOUT]
    cases = []
    for family in fit_families:
        removed = [row.row_id for row in declaration.rows if row.family == family]
        removed_ids = tuple(term.term_id for term in system.matrix.terms if set(term.row_ids) & set(removed))
        keep = [index for index, term in enumerate(system.matrix.terms) if not set(term.row_ids) & set(removed)]
        if len(keep) < len(bounds.names):
            cases.append(LeaveOneFamilyOutRow(
                family, removed_ids, "REFUSED_RANK_DEFICIENT", None,
                (f"{len(keep)} FIT terms remain for {len(bounds.names)} parameters.",),
            ))
            continue
        matrix = SensitivityMatrix(
            tuple(system.matrix.terms[i] for i in keep), system.matrix.parameters,
            tuple(system.matrix.values[i] for i in keep), dict(system.matrix.column_provenance),
        )
        component = system.covariance.components[0]
        reduced = replace(component, matrix=tuple(tuple(component.matrix[i][j] for j in keep) for i in keep))
        analysis = analyse_practical_identifiability(
            assemble_system(matrix, ObservationCovariance(matrix.term_ids, (reduced,)), ())
        )
        if not analysis.full_rank:
            cases.append(LeaveOneFamilyOutRow(family, removed_ids, "REFUSED_RANK_DEFICIENT", None, analysis.refusal_reasons))
            continue
        try:
            design = build_objective_design(
                frozen, holdout + removed, clusters, _row_sigmas(declaration), len(bounds.names)
            )
        except ObjectiveInputError as error:
            cases.append(LeaveOneFamilyOutRow(family, removed_ids, "REFUSED_DESIGN", None, (str(error),)))
            continue
        tracked = _TrackedEvaluator(study, design, frozen, [c.row_ids for c in clusters], final_state, rows)
        if study.remaining < 1:
            cases.append(LeaveOneFamilyOutRow(family, removed_ids, "NOT_RUN_BUDGET", None, ("The solve budget is used up.",)))
            continue
        try:
            outcome = run_bounded_lm(
                tracked.residuals, _point(bounds, p_hat), bounds, study.settings(study.remaining), tracked.accept
            )
        except StepError as error:
            cases.append(LeaveOneFamilyOutRow(family, removed_ids, "REFUSED_STEP", None, (str(error),)))
            continue
        if outcome.status is LMStatus.CONVERGED:
            cases.append(LeaveOneFamilyOutRow(family, removed_ids, "VALID", dict(outcome.parameters), ()))
        else:
            cases.append(LeaveOneFamilyOutRow(
                family, removed_ids, f"NOT_VALID_{outcome.status.value}", None, (outcome.refusal or outcome.status.value,),
            ))
    valid = [case.estimate for case in cases if case.status == "VALID"]
    ranges = {
        name: (min(item[name] for item in valid), max(item[name] for item in valid)) for name in bounds.names
    } if valid else {}
    return tuple(cases), ranges


def _at_bound(p: np.ndarray, bounds: MixedParameterBounds) -> Tuple[str, ...]:
    return tuple(
        name for name, value, low, high in zip(bounds.names, p, bounds.lower, bounds.upper) if value <= low or value >= high
    )


def _missing_components(declaration: PlateInverseDeclaration) -> Tuple[str, ...]:
    missing = [
        "Sigma off-diagonal terms: none declared; the diagonal form is an assumption",
        "registration uncertainty: not propagated",
        "covariance of conditional effective constants: not propagated",
        "signed-coordinate precision policy near zero: not approved",
    ]
    absent = [row.row_id for row in declaration.rows if row.measurement_sd_ln is None]
    if absent:
        missing.insert(0, f"Sigma_meas NOT_AVAILABLE for rows {absent}: excluded from sigma, not taken as zero")
    if declaration.geometry is not None:
        with_uncertainty = {
            item.name for item in declaration.geometry.evidence if item.standard_uncertainty_si is not None
        }
        missing.extend(f"{name} uncertainty: NOT_AVAILABLE" for name in ("a", "b", "mass", "thickness") if name not in with_uncertainty)
    else:
        missing.append("specimen geometry and mass uncertainty: not part of a Stage-A declaration")
    return tuple(missing)


def _refused(
    declaration: PlateInverseDeclaration, refusal: _StudyRefusal, study: Optional[_Study] = None, **extra: Any
) -> PlateInverseResult:
    status = {
        InverseRefusalCode.BUDGET_EXHAUSTED: ExecutionStatus.BUDGET_EXHAUSTED,
        InverseRefusalCode.CANCELLED: ExecutionStatus.CANCELLED,
    }.get(refusal.code, ExecutionStatus.REFUSED)
    return PlateInverseResult(
        declaration_hash=declaration.declaration_hash,
        execution_status=status,
        numerical_status=extra.pop("numerical_status", NumericalStatus.NOT_RUN),
        scientific_status=InverseScientificStatus.NO_RESULT,
        evidence_kind=declaration.evidence_kind,
        backend_id=declaration.backend_id,
        refusal_code=refusal.code,
        refusal_reason=refusal.reason,
        forward_refusal_code=refusal.forward_code,
        solves=0 if study is None else study.solves,
        **extra,
    )


def _build_model(declaration: PlateInverseDeclaration, stage_a_package: Optional[Path | str]) -> Any:
    if declaration.backend_id is ForwardBackendId.KIRCHHOFF_RITZ_4D:
        if not isinstance(declaration.observation_set, CoordinateObservationSet):
            raise _StudyRefusal(InverseRefusalCode.DECLARATION_INVALID, "The Ritz backend takes coordinate observations.")
        return RitzInverseModel(declaration)
    if not isinstance(declaration.observation_set, DofObservationSet):
        raise _StudyRefusal(InverseRefusalCode.DECLARATION_INVALID, "The Stage-A backend takes matrix-DOF observations.")
    if stage_a_package is None:
        raise _StudyRefusal(
            InverseRefusalCode.PACKAGE_REFUSED, "No Stage-A package was given for this study.", RefusalCode.PACKAGE_MISSING.value
        )
    return StageAInverseModel(declaration, stage_a_package)


def run_plate_inverse_study(
    declaration: PlateInverseDeclaration,
    *,
    stage_a_package: Optional[Path | str] = None,
    model: Any = None,
    cancel: Optional[Callable[[], bool]] = None,
    clock: Callable[[], float] = time.monotonic,
) -> PlateInverseResult:
    """Run one frozen declaration. Refusals return a result with a code and no candidate.

    ``model`` replaces the backend adapter in tests; it must keep the same interface and identity.
    """

    problem = _declaration_refusal(declaration)
    if problem is not None:
        return _refused(declaration, _StudyRefusal(*problem))
    try:
        if model is None:
            model = _build_model(declaration, stage_a_package)
        return _execute(declaration, model, cancel, clock)
    except _StudyRefusal as refusal:
        return _refused(declaration, refusal)
    except PlateForwardRefusal as refusal:
        return _refused(
            declaration, _StudyRefusal(InverseRefusalCode.FORWARD_REFUSED, refusal.reason, refusal.code.value)
        )


def _execute(declaration: PlateInverseDeclaration, model: Any, cancel, clock) -> PlateInverseResult:
    if tuple(item.name for item in declaration.parameters) != tuple(model.names):
        raise _StudyRefusal(
            InverseRefusalCode.DECLARATION_INVALID,
            f"This backend fits exactly {tuple(model.names)}, in that order.",
        )
    if declaration.model_identity != model.model_identity:
        raise _StudyRefusal(
            InverseRefusalCode.MODEL_IDENTITY_MISMATCH,
            "The declared model identity differs from the model that was opened.",
        )
    if isinstance(model, StageAInverseModel) and model.backend.provenance.evidence_kind is not declaration.evidence_kind:
        raise _StudyRefusal(
            InverseRefusalCode.EVIDENCE_KIND_MISMATCH,
            f"The package is {model.backend.provenance.evidence_kind.value}; the declaration says "
            f"{declaration.evidence_kind.value}.",
        )
    outside = model.validated_range_refusal(declaration)
    if outside is not None:
        raise _StudyRefusal(InverseRefusalCode.OUTSIDE_VALIDATED_RANGE, outside)
    study = _Study(declaration, model, cancel, clock)
    try:
        return _run_stages(declaration, model, study)
    except _StudyRefusal as refusal:
        return _refused(declaration, refusal, study)
    except InadmissibleTrial as refusal:
        return _refused(declaration, _StudyRefusal(InverseRefusalCode.INADMISSIBLE_POINT, str(refusal)), study)
    except BranchTrackingRefusal as refusal:
        return _refused(declaration, _StudyRefusal(InverseRefusalCode.BRANCH_IDENTITY_LOST, str(refusal)), study)
    except EvaluationRefusal as refusal:
        stop = study.stop or _StudyRefusal(InverseRefusalCode.FORWARD_REFUSED, str(refusal))
        return _refused(declaration, stop, study)
    except (PairingInputError, ClusterInputError, TrackingInputError) as error:
        return _refused(declaration, _StudyRefusal(InverseRefusalCode.DECLARATION_INVALID, str(error)), study)
    except (StepError, ObjectiveInputError, PracticalIdentifiabilityInputError, np.linalg.LinAlgError) as error:
        return _refused(declaration, _StudyRefusal(InverseRefusalCode.STEP_UNDEFINED, str(error)), study)


def _run_stages(declaration: PlateInverseDeclaration, model: Any, study: _Study) -> PlateInverseResult:
    try:
        bounds = study.bounds()
    except StepError as error:
        raise _StudyRefusal(InverseRefusalCode.DECLARATION_INVALID, str(error)) from error
    p0 = np.array([float(item.start) for item in declaration.parameters])
    if np.any(p0 < np.array(bounds.lower)) or np.any(p0 > np.array(bounds.upper)):
        raise _StudyRefusal(InverseRefusalCode.OUTSIDE_VALIDATED_RANGE, "The start point lies outside the declared bounds.")
    families = {row.row_id: row.family for row in declaration.rows}
    baseline = study.solve(_point(bounds, p0))
    review = _cluster_review(study, baseline, p0, bounds)
    cluster_rows = [item.row_ids for item in review]
    macs = _baseline_check(declaration, baseline, cluster_rows)
    frozen = _frozen_set(declaration, baseline, macs)
    holdout_ids = [row.row_id for row in declaration.rows if row.role is ObservationRole.HOLDOUT]
    try:
        design = build_objective_design(frozen, holdout_ids, review, _row_sigmas(declaration), len(bounds.names))
    except ObjectiveInputError as error:
        if "fit terms <" in str(error):
            raise _StudyRefusal(InverseRefusalCode.RANK_DEFICIENT, str(error)) from error
        raise _StudyRefusal(InverseRefusalCode.DECLARATION_INVALID, str(error)) from error
    provisional = any(row.setup_provisional for row in declaration.rows)
    rows0 = {row.row_id: row.model_mode for row in declaration.rows}
    evaluator = _TrackedEvaluator(study, design, frozen, cluster_rows, baseline, rows0)
    initial = evaluator.evaluate(_point(bounds, p0))

    # Practical identifiability of the complete matrix comes before any fit (SPEC 6 S5).
    sensitivity0 = _fit_sensitivity(evaluator, p0, bounds, declaration.policy.final_sensitivity_step)
    analysis0 = analyse_practical_identifiability(_practical_system(bounds, initial, sensitivity0, provisional))
    start_block = _diagnostics(analysis0, sensitivity0, [term.term_id for term in initial.fit_terms])
    if not analysis0.full_rank:
        raise _StudyRefusal(InverseRefusalCode.RANK_DEFICIENT, " ".join(analysis0.refusal_reasons))
    too_weak = _not_observable(analysis0, bounds)
    if too_weak:
        raise _StudyRefusal(InverseRefusalCode.PARAMETER_NOT_OBSERVABLE, " ".join(too_weak))

    lm = run_bounded_lm(evaluator.residuals, _point(bounds, p0), bounds, study.settings(study.remaining), evaluator.accept)
    common = _common_fields(declaration, model, study, bounds, p0, baseline, lm, initial, start_block)
    if lm.status is LMStatus.REFUSED:
        stop = study.stop
        if stop is None and lm.refusal == study.last_inadmissible:
            stop = _StudyRefusal(InverseRefusalCode.INADMISSIBLE_POINT, lm.refusal)
        if stop is None:
            stop = _StudyRefusal(InverseRefusalCode.BRANCH_IDENTITY_LOST, lm.refusal or "Branch identity was lost.")
        return _refused(declaration, stop, study, numerical_status=NumericalStatus.REFUSED, **common)

    p_hat = np.array([lm.parameters[name] for name in bounds.names])
    # Replay the accepted point: same state, same objective. Rejected trials played no part in it.
    final = evaluator.evaluate(_point(bounds, p_hat))
    final_state = evaluator.last[1]
    replay = abs(final.objective - lm.objective)
    if replay > declaration.policy.max_objective_replay_difference * max(lm.objective, 1.0):
        raise _StudyRefusal(
            InverseRefusalCode.NUMERICAL_HEALTH_FAILED,
            f"The accepted objective {lm.objective:.12g} does not replay ({final.objective:.12g}).",
        )
    numerical = {
        LMStatus.CONVERGED: NumericalStatus.CONVERGED,
        LMStatus.MAX_ITERATIONS: NumericalStatus.MAX_ITERATIONS,
        LMStatus.STEP_REJECTED: NumericalStatus.STEP_REJECTED,
        LMStatus.SOLVE_BUDGET: NumericalStatus.SOLVE_BUDGET,
    }[lm.status]
    active = _at_bound(p_hat, bounds)
    if numerical is NumericalStatus.CONVERGED and active:
        numerical = NumericalStatus.CONVERGED_AT_BOUND

    rows_final = dict(evaluator.rows)
    reasons = ["A forward-model fit is a diagnostic result, not a material property.", "Physical validity was not assessed."]
    if declaration.evidence_kind is EvidenceKind.SYNTHETIC:
        reasons.append("SYNTHETIC data: recovery of known values is software behaviour, not material validation.")
    if active:
        reasons.append(f"Active bounds at the final point: {list(active)}.")
    if provisional:
        reasons.append("Sigma_setup is provisional.")
    linear = [name for name, kind in zip(bounds.names, bounds.kinds) if kind is CoordinateKind.LINEAR]
    reasons.append(f"No precision policy is approved for the signed coordinate {linear}.")
    if model.package_validation_status != "NOT_APPLICABLE":
        reasons.append("Package validation text was not assessed and is not physical proof.")

    table_fit = _residual_table(initial.fit_terms, final.fit_terms, ObservationRole.FIT, families)
    table_holdout = _residual_table(initial.holdout_terms, final.holdout_terms, ObservationRole.HOLDOUT, families)
    by_id = {row.row_id: row for row in declaration.rows}
    frequencies = tuple(
        ModalFrequencyRow(
            row.row_id, row.role, float(row.experimental_hz),
            baseline.frequencies_hz[row.model_mode - 1], final_state.frequencies_hz[rows_final[row.row_id] - 1],
        )
        for row in declaration.rows
    )
    identity = tuple(
        ModeIdentityRow(
            row.row_id, row.experimental_mode, row.model_mode, rows_final[row.row_id], macs[row.row_id],
            _final_mac(row, final_state, rows_final, by_id, cluster_rows), evaluator.min_mac[row.row_id],
        )
        for row in declaration.rows
    )
    order_changes = _order_changes(declaration, baseline, final_state, rows_final)
    sensitivity = _fit_sensitivity(evaluator, p_hat, bounds, declaration.policy.final_sensitivity_step)
    system = _practical_system(bounds, final, sensitivity, provisional)
    analysis = analyse_practical_identifiability(system)
    block = _diagnostics(analysis, sensitivity, [term.term_id for term in final.fit_terms])
    analytic_gap = _analytic_difference(model, _point(bounds, p_hat), rows_final, final, sensitivity)
    if analytic_gap is not None and analytic_gap > declaration.policy.max_analytic_sensitivity_difference:
        numerical = NumericalStatus.SENSITIVITY_CHECK_FAILED
        reasons.append(f"Analytic and tracked sensitivities differ by {analytic_gap:.3g}.")
    elif analytic_gap is None:
        reasons.append("No single-branch analytic sensitivity was available to cross-check.")

    term_sigma = {term.term_id: term.sigma for term in tuple(final.fit_terms) + tuple(final.holdout_terms)}
    fit_terms = residual_terms(design.fit_rows, design.fit_clusters, final.residuals, families, term_sigma)
    holdout_terms = residual_terms(
        design.holdout_rows, design.holdout_clusters, [term.residual for term in final.holdout_terms], families, term_sigma
    )
    pattern = residual_pattern_test(fit_terms, holdout_terms)
    statistics = statistical_sd(system, f"{declaration.evidence_kind.value} plate study {declaration.study_id}")
    birge = birge_adjustment(system, statistics, pattern, fit_terms)
    if analysis.full_rank and numerical is NumericalStatus.CONVERGED:
        cases, ranges = _leave_one_family_out(study, frozen, review, final_state, rows_final, p_hat, bounds, system)
    else:
        cases, ranges = (), {}
    if study.stop is not None:  # a budget or cancel stop inside the checks leaves them incomplete, not passed
        reasons.append(f"Checks stopped early: {study.stop.reason}")

    weak = _not_observable(analysis, bounds) if analysis.full_rank else ()
    if numerical is not NumericalStatus.CONVERGED:
        scientific = InverseScientificStatus.NOT_CONVERGED_NO_CANDIDATE
        reasons.append(f"Numerical status {numerical.value} provides no candidate.")
    elif not analysis.full_rank or weak:
        scientific = InverseScientificStatus.NOT_IDENTIFIABLE
        reasons.extend(analysis.refusal_reasons + weak)
    elif not pattern.passed:
        scientific = InverseScientificStatus.MODEL_FORM_CHECK_FAILED
        reasons.extend(pattern.reasons)
    elif not cases or any(case.status != "VALID" for case in cases):
        scientific = InverseScientificStatus.ROBUSTNESS_INCOMPLETE
        reasons.extend(f"Leave-one-family-out {case.family}: {case.status}." for case in cases if case.status != "VALID")
    else:
        scientific = InverseScientificStatus.DIAGNOSTIC_OPTIMIZER_CANDIDATE

    final_d = model.stiffness(_point(bounds, p_hat))
    thickness = None if declaration.geometry is None else declaration.geometry.thickness_m
    constants = effective_engineering_constants(final_d, thickness)
    available = [f"statistical_sd: {statistics.status.value}", f"birge_adjusted_sd: {birge.status.value}"]
    if ranges:
        available.append("model_form_robustness range")
    uncertainty = UncertaintyReport(
        statistical_sd=statistics.statistical_sd_ln,
        birge_status=birge.status.value,
        birge_adjusted_sd=birge.birge_adjusted_sd_ln,
        robustness_range=ranges,
        robustness_note=_ROBUSTNESS_NOTE,
        pattern_status=pattern.status.value,
        pattern_reasons=pattern.reasons,
        available_components=tuple(available),
        missing_components=_missing_components(declaration),
    )
    common.pop("identifiability")
    return PlateInverseResult(
        declaration_hash=declaration.declaration_hash,
        execution_status=ExecutionStatus.BUDGET_EXHAUSTED if numerical is NumericalStatus.SOLVE_BUDGET else ExecutionStatus.COMPLETED,
        numerical_status=numerical,
        scientific_status=scientific,
        evidence_kind=declaration.evidence_kind,
        backend_id=declaration.backend_id,
        scientific_reasons=tuple(reasons),
        final_parameters=dict(lm.parameters),
        final_stiffness=final_d.identity(),
        conditional_effective_constants={
            "nu12": constants.nu12,
            "nu21": constants.nu21,
            "E1_flex_pa": constants.E1_flex_pa,
            "E2_flex_pa": constants.E2_flex_pa,
            "G12_flex_pa": constants.G12_flex_pa,
        },
        frequencies=frequencies,
        fit_residuals=table_fit,
        holdout_residuals=table_holdout,
        mode_identity=identity,
        order_changes=order_changes,
        final_objective=final.objective,
        solves=study.solves,
        identifiability=block,
        uncertainty=uncertainty,
        leave_one_family_out=cases,
        max_analytic_sensitivity_difference=analytic_gap,
        max_eigen_residual_seen=study.max_eigen_residual,
        max_orthonormality_error_seen=study.max_orthonormality_error,
        package_validation_text=model.package_validation_text,
        package_validation_status=model.package_validation_status,
        **common,
    )


def _common_fields(declaration, model, study, bounds, p0, baseline, lm: LMResult, initial, start_block) -> dict:
    return {
        "initial_parameters": _point(bounds, p0),
        "initial_stiffness": model.stiffness(_point(bounds, p0)).identity(),
        "iterations": lm.history,
        "initial_objective": initial.objective,
        "identifiability": start_block,
    }


def _final_mac(row, state: ForwardState, rows_final, by_id, clusters) -> float:
    count = state.observed.shape[0]
    for pair in clusters:
        if row.row_id in pair:
            experimental = np.column_stack([_experimental_shape(by_id[item], count) for item in pair])
            model = state.observed[:, [rows_final[item] - 1 for item in pair]]
            return _subspace_min_cos2(experimental, model)
    return _complex_mac(_experimental_shape(row, count), state.observed[:, rows_final[row.row_id] - 1])


def _order_changes(declaration, baseline: ForwardState, final: ForwardState, rows_final) -> Tuple[Tuple[str, str], ...]:
    """Row pairs whose model frequency order differs between the start and the final point."""

    changes = []
    rows = declaration.rows
    for index, left in enumerate(rows):
        for right in rows[index + 1:]:
            before = baseline.frequencies_hz[left.model_mode - 1] - baseline.frequencies_hz[right.model_mode - 1]
            after = final.frequencies_hz[rows_final[left.row_id] - 1] - final.frequencies_hz[rows_final[right.row_id] - 1]
            if before * after < 0.0:
                changes.append((left.row_id, right.row_id))
    return tuple(changes)


__all__ = [
    "RITZ_PARAMETERS",
    "STAGE_A_PARAMETERS",
    "RitzInverseModel",
    "StageAInverseModel",
    "ForwardState",
    "release_material_property",
    "run_plate_inverse_study",
]
