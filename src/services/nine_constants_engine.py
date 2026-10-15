"""Nine-constant sensitivity, identifiability and research estimation — research track NINE-EC (Phase D / E).

RESEARCH_DIAGNOSTIC_ONLY. Nothing here produces a governed material-property verdict (SPEC v1.2 §1 A) or a
governed specimen-calibration release (SPEC v1.2 §3a); every record carries RESEARCH_DIAGNOSTIC_ONLY and
NOT_A_VALIDATED_MATERIAL_PROPERTY.

Parameter vector: the nine Engineering Constants in research coordinates (domain.orthotropic_elasticity): x = ln p for
E1, E2, E3, G12, G13, G23 and x = ν for ν12, ν13, ν23 (signed, absolute; never ln ν).

- **Sensitivities** (SPEC S4 reused where it applies): central differences with physical perturbations of the
  moduli, p⁺ = p·1.05 and p⁻ = p·0.95 (SPEC ±5 %), and an explicit absolute ν step (PROPOSAL, not accepted);
  S_ij = (ln f⁺ − ln f⁻)/(x⁺ − x⁻) with the actual coordinates of the perturbed parameters (x = ln p⁺, ln p⁻ for
  moduli). Every perturbed state is checked for elastic admissibility BEFORE evaluation; branches are followed by the
  accepted FE-to-FE tracker (branch_tracker.track_branches, STRICT policy: MAC ≥ 0.90, unique) and a loss is a
  refusal, never a re-pairing. Noise control repeats each column with half steps (SPEC: p·1.025 and p·0.975 must give
  S within 5 %).
- **Identifiability**: the accepted M5 engine (practical_identifiability: rcond 1e-3, rank deficiency = hard block,
  C = (AᵀA)⁻¹, q projections) on the whitened system with explicit Σ and explicit nuisance priors. Per constant: the
  SPEC §10 sd ≤ 0.08 (ln p) rule for moduli; for Poisson ratios no accepted rule exists (POLICY blocker unless the
  caller declares a research limit, recorded as UNACCEPTED). Observation families are counted (SPEC v1.2 §8:
  k + 1 FIT families and one distinct HOLDOUT family for k parameters).
- **Estimation** (optional): only after the gate passes for every estimated constant; LM in x (SPEC §8 step with the
  minus sign, Φ decrease, stop at max|Δx_j| < 0.2·sd_j or 5 iterations), admissibility and branch identity at every
  trial, fresh central sensitivities at p̂, residual table with holdouts. A hard evaluation budget bounds the work.

The forward model is any object with ``evaluate(constants) -> FEModalState`` and ``identity() -> dict``: the synthetic
block model now; an Abaqus adapter later (not connected: real solves need HUMAN approval and the accepted P-series
safeguards).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
from typing import Callable, Mapping, Optional, Protocol, Sequence

import numpy as np

from domain.forward_model_manifest import EngineeringConstants
from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING
from domain.orthotropic_elasticity import (
    COORDINATE_UNITS,
    COORDINATES,
    NAMES,
    CoordinateKind,
    ElasticAdmissibilityError,
    admissibility,
    constants_from,
    from_coordinates,
    to_coordinates,
)

from .branch_tracker import BranchTrackingRefusal, FEModalState, track_branches
from .identification_step import lm_step, objective
from .practical_identifiability import (
    RCOND,
    SD_FIT_LIMIT_LN,
    ObservationCovariance,
    ParameterDefinition,
    ParameterRole,
    NuisancePrior,
    analyse_practical_identifiability,
    assemble_system,
    build_sensitivity_matrix,
    diagonal_component,
)

SCHEMA = "research/nine-constants-analysis/v1"
CLAIM_LABELS = ("RESEARCH_DIAGNOSTIC_ONLY", "NOT_A_VALIDATED_MATERIAL_PROPERTY")
SPEC_RELATIVE_STEP = 0.05  # SPEC S4: p⁺ = p·1.05, p⁻ = p·0.95 (half step: p·1.025, p·0.975)
SPEC_NOISE_RELATIVE = 0.05  # SPEC S4: a repeat with half steps must give S within 5 %
LM_MAX_ITERATIONS = 5  # SPEC §8
LM_STOP_FRACTION = 0.2  # SPEC §8: max|Δx_j| < 0.2·sd_j
LM_MU_INITIAL = 1.0e-3
LM_MU_FACTOR = 10.0
LM_STEP_ATTEMPTS = 3


class ConstantStatus(str, Enum):
    SUPPORTED_RESEARCH_ESTIMATE = "SUPPORTED_RESEARCH_ESTIMATE"
    NOT_IDENTIFIABLE = "NOT_IDENTIFIABLE"
    NOT_EVALUATED = "NOT_EVALUATED"
    FIXED_INPUT_NOT_IDENTIFIED = "FIXED_INPUT_NOT_IDENTIFIED"
    POLICY_OR_EVIDENCE_BLOCKER = "POLICY_OR_EVIDENCE_BLOCKER"
    INVALID_OR_UNSUPPORTED_MODEL = "INVALID_OR_UNSUPPORTED_MODEL"


class Role(str, Enum):
    FIT = "FIT"
    HOLDOUT = "HOLDOUT"


class EvaluationBudgetExhausted(Exception):
    """The hard limit of forward evaluations is reached; nothing further is evaluated."""


class ForwardModel(Protocol):
    def evaluate(self, constants: EngineeringConstants) -> FEModalState: ...

    def identity(self) -> dict: ...


@dataclass(frozen=True)
class ObservationRow:
    """One frozen observation: an experimental frequency paired at the baseline to one FE mode (never re-paired)."""

    row_id: str
    experimental_hz: float
    baseline_fe_mode: int
    family_key: str
    role: Role = Role.FIT
    sd_ln: Optional[float] = None  # Σ diagonal sd in ln f for this row (explicit; required for FIT rows)

    def to_dict(self) -> dict:
        return {"row_id": self.row_id, "experimental_hz": self.experimental_hz,
                "baseline_fe_mode": self.baseline_fe_mode, "family_key": self.family_key, "role": self.role.value,
                "sd_ln": self.sd_ln}


def perturbed_constant(base: EngineeringConstants, name: str, step: float) -> tuple[EngineeringConstants, float]:
    """``base`` with one constant perturbed, and that constant's research coordinate.

    Moduli: the physical factor p·(1 + step) (SPEC S4: step ±0.05 gives p·1.05 and p·0.95), coordinate ln of the
    perturbed value. Poisson ratios: ν + step (absolute, PROPOSAL), coordinate ν. Never p·exp(step).
    """
    values = base.to_dict()
    if COORDINATES[name] is CoordinateKind.LOG:
        values[name] = values[name] * (1.0 + step)
        return constants_from(values), math.log(values[name])
    values[name] = values[name] + step
    return constants_from(values), values[name]


@dataclass(frozen=True)
class SensitivityDesign:
    """Finite-difference steps per coordinate kind. The ν step is a PROPOSAL needing SUPERVISOR acceptance."""

    relative_step: float = SPEC_RELATIVE_STEP  # moduli: p·(1 ± relative_step), SPEC S4
    poisson_step: float = 0.02  # PROPOSAL: absolute ν step (no accepted value)
    noise_check: bool = True  # half-step repeat (SPEC S4 noise control)
    noise_relative: float = SPEC_NOISE_RELATIVE

    def __post_init__(self) -> None:
        if not 0.0 < self.relative_step < 1.0:
            raise ValueError("the relative modulus step must lie in (0, 1).")

    def step(self, name: str, scale: float = 1.0) -> float:
        base = self.relative_step if COORDINATES[name] is CoordinateKind.LOG else self.poisson_step
        return base * scale

    def to_dict(self) -> dict:
        h = self.relative_step
        return {"relative_step": h, "modulus_factors": [1.0 + h, 1.0 - h],
                "modulus_half_step_factors": [1.0 + h / 2.0, 1.0 - h / 2.0],
                "poisson_step": self.poisson_step, "poisson_step_status": "PROPOSAL",
                "noise_check": self.noise_check, "noise_relative": self.noise_relative}


class EvaluationCounter:
    """Hard cap on forward evaluations (every evaluation counts; a synthetic model is counted like an FE solve)."""

    def __init__(self, forward: ForwardModel, limit: int) -> None:
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("the evaluation limit must be a positive integer (never unlimited).")
        self.forward, self.limit, self.count = forward, limit, 0
        self._cache: dict[str, FEModalState] = {}

    @staticmethod
    def key(constants: EngineeringConstants) -> str:
        return hashlib.sha256(json.dumps(constants.to_dict(), sort_keys=True).encode()).hexdigest()

    def evaluate(self, constants: EngineeringConstants) -> FEModalState:
        key = self.key(constants)
        if key in self._cache:
            return self._cache[key]
        report = admissibility(constants)
        if not report.admissible:  # refused before any (FE) evaluation
            raise ElasticAdmissibilityError(report.violations)
        if self.count >= self.limit:
            raise EvaluationBudgetExhausted(f"the limit of {self.limit} forward evaluations is used up.")
        self.count += 1
        state = self.forward.evaluate(constants)
        self._cache[key] = state
        return state


@dataclass
class SensitivityResult:
    estimated: tuple[str, ...]
    values: dict[str, dict[str, float]]  # row id -> constant -> S
    half_step_values: dict[str, dict[str, float]]
    column_status: dict[str, str]  # constant -> EVALUATED / NOT_EVALUATED: reason / NUMERICALLY_UNRESOLVED
    column_reasons: dict[str, str]
    tracking_min_mac: dict[str, float]
    evaluations: int

    def to_dict(self) -> dict:
        return {"estimated": list(self.estimated), "values": self.values, "half_step_values": self.half_step_values,
                "column_status": self.column_status, "column_reasons": self.column_reasons,
                "tracking_min_mac": self.tracking_min_mac, "evaluations": self.evaluations}


def _track(reference: FEModalState, mapping: Mapping[str, int],
           candidate: FEModalState) -> tuple[dict[str, float], dict[str, int], float]:
    """(ln f per row, row → candidate mode, minimum tracking MAC); the frozen rows are followed, never re-paired."""
    tracking = track_branches(STRICT_IDENTIFICATION_PAIRING, reference, candidate, dict(mapping))
    return ({b.row_id: math.log(b.candidate_hz) for b in tracking.branches},
            {b.row_id: b.candidate_mode for b in tracking.branches}, min(b.mac for b in tracking.branches))


def central_sensitivities(counter: EvaluationCounter, base: EngineeringConstants, rows: Sequence[ObservationRow],
                          estimated: Sequence[str], design: SensitivityDesign = SensitivityDesign(),
                          mapping: Optional[Mapping[str, int]] = None) -> SensitivityResult:
    """S_ij = (ln f⁺ − ln f⁻)/(x⁺ − x⁻) per estimated constant, with tracking, admissibility and a noise check.

    x⁺ and x⁻ are the coordinates of the actually perturbed parameters (moduli: ln(p·1.05) and ln(p·0.95)).
    ``mapping`` gives each row's mode in the state at ``base`` (default: the frozen baseline modes).
    """
    reference = counter.evaluate(base)
    mapping = dict(mapping) if mapping is not None else {r.row_id: r.baseline_fe_mode for r in rows}
    values = {r.row_id: {} for r in rows}
    half = {r.row_id: {} for r in rows}
    status, reasons, minimum_mac = {}, {}, {}

    def column(j: int, scale: float):
        name = estimated[j]
        h = design.step(name, scale)
        out = {}
        mac = 1.0
        logs, coordinates = [], []
        for sign in (+1, -1):
            candidate, x = perturbed_constant(base, name, sign * h)
            state = counter.evaluate(candidate)  # refuses an inadmissible state before evaluating
            log_f, _, tracked_mac = _track(reference, mapping, state)
            logs.append(log_f)
            coordinates.append(x)
            mac = min(mac, tracked_mac)
        for r in rows:
            out[r.row_id] = (logs[0][r.row_id] - logs[1][r.row_id]) / (coordinates[0] - coordinates[1])
        return out, mac

    for j, name in enumerate(estimated):
        try:
            full, mac = column(j, 1.0)
            for r in rows:
                values[r.row_id][name] = full[r.row_id]
            minimum_mac[name] = mac
            status[name] = "EVALUATED"
            if design.noise_check:
                repeat, mac_half = column(j, 0.5)
                minimum_mac[name] = min(mac, mac_half)
                for r in rows:
                    half[r.row_id][name] = repeat[r.row_id]
                scale = max(abs(v) for v in full.values())
                difference = max(abs(full[r.row_id] - repeat[r.row_id]) for r in rows)
                if not difference <= design.noise_relative * scale:
                    status[name] = "NUMERICALLY_UNRESOLVED"
                    reasons[name] = (f"half-step repeat differs by {difference:.3g} (> {design.noise_relative:g} × "
                                     f"max|S| = {design.noise_relative * scale:.3g}): sensitivity not resolved above "
                                     "numerical noise (SPEC S4)")
        except ElasticAdmissibilityError as error:
            status[name] = "NOT_EVALUATED"
            reasons[name] = f"a perturbed state is not admissible: {error}"
        except BranchTrackingRefusal as error:
            status[name] = "NOT_EVALUATED"
            reasons[name] = f"branch identity lost under perturbation (no re-pairing): {error}"
    return SensitivityResult(tuple(estimated), values, half, status, reasons, minimum_mac, counter.count)


# ----------------------------------------------------------------------------- identifiability per constant

@dataclass(frozen=True)
class NuisanceColumn:
    """A nuisance parameter with its sensitivity column (per FIT row) and an explicit, evidence-backed prior."""

    parameter_id: str
    specimen: str
    sensitivities: Mapping[str, float]
    prior: NuisancePrior


@dataclass
class ConstantAssessment:
    name: str
    coordinate: str
    input_value: float
    status: ConstantStatus
    reasons: list[str] = field(default_factory=list)
    sd: Optional[float] = None  # in the coordinate's units (ln p, or absolute ν)
    q: Optional[float] = None  # residual information after projection on every other column (SPEC §10)
    null_space_weight: Optional[float] = None  # rank-deficient systems: |component in the numerical null space|
    estimate: Optional[float] = None  # research estimate (only for SUPPORTED_RESEARCH_ESTIMATE)

    def to_dict(self) -> dict:
        return {"constant": self.name, "coordinate": self.coordinate, "input_value": self.input_value,
                "status": self.status.value, "reasons": list(self.reasons), "sd": self.sd, "q": self.q,
                "null_space_weight": self.null_space_weight, "estimate": self.estimate}


@dataclass
class IdentifiabilityAssessment:
    constants: dict[str, ConstantAssessment]
    rank_status: Optional[str]
    rank: Optional[int]
    parameters_in_system: tuple[str, ...]
    fit_terms: int
    fit_families: int
    holdout_families: int
    minimum_observability_met: bool
    analysis: Optional[dict]  # the M5 result record
    supported_combinations: list[dict]  # rank-deficient: right singular vectors above rcond (diagnostic only)
    refusal_reasons: list[str]
    research_limits: dict

    def to_dict(self) -> dict:
        return {"constants": {k: v.to_dict() for k, v in self.constants.items()}, "rank_status": self.rank_status,
                "rank": self.rank, "parameters_in_system": list(self.parameters_in_system),
                "fit_terms": self.fit_terms, "fit_families": self.fit_families,
                "holdout_families": self.holdout_families,
                "minimum_observability_v1_2_section_8": self.minimum_observability_met,
                "analysis": self.analysis, "supported_combinations": self.supported_combinations,
                "refusal_reasons": list(self.refusal_reasons), "research_limits": self.research_limits}


def assess_identifiability(base: EngineeringConstants, rows: Optional[Sequence[ObservationRow]],
                           sensitivities: Optional[Mapping[str, Mapping[str, float]]],
                           estimated: Sequence[str], fixed: Sequence[str] = (),
                           column_status: Optional[Mapping[str, str]] = None,
                           column_reasons: Optional[Mapping[str, str]] = None,
                           formulation_use: Optional[Mapping[str, str]] = None,
                           nuisance: Sequence[NuisanceColumn] = (),
                           sigma_provenance: str = "explicit per-row sd_ln (caller)",
                           sigma_provisional: bool = True,
                           poisson_sd_limit: Optional[float] = None) -> IdentifiabilityAssessment:
    """Per-constant status for the declared question (estimated vs fixed constants). Never fabricates a value.

    ``rows`` None means the observations are not established yet (no frozen baseline pairing): every estimated
    constant is NOT_EVALUATED. An established list with fewer FIT rows than parameters bounds the rank (refusal).
    """
    established = rows is not None
    rows = list(rows or ())
    estimated, fixed = tuple(estimated), tuple(fixed)
    if set(estimated) & set(fixed) or not set(estimated) | set(fixed) <= set(NAMES):
        raise ValueError("estimated and fixed constants must be disjoint subsets of the nine constants.")
    column_status = dict(column_status or {})
    column_reasons = dict(column_reasons or {})
    formulation_use = dict(formulation_use or {})
    result = {name: ConstantAssessment(name, COORDINATE_UNITS[name], getattr(base, name), ConstantStatus.NOT_EVALUATED)
              for name in NAMES}
    for name in fixed:
        result[name].status = ConstantStatus.FIXED_INPUT_NOT_IDENTIFIED
        result[name].reasons.append("declared fixed for this question: the input value is kept, NOT identified")
    for name in NAMES:
        if name not in estimated and name not in fixed:
            result[name].reasons.append("not part of the declared question")
    fit = [r for r in rows if r.role is Role.FIT]
    holdout = [r for r in rows if r.role is Role.HOLDOUT]
    fit_families = {r.family_key for r in fit}
    holdout_families = {r.family_key for r in holdout} - fit_families
    k = len(estimated)
    observability = len(fit_families) >= k + 1 and len(holdout_families) >= 1
    limits = {"rcond": RCOND, "sd_fit_limit_ln": SD_FIT_LIMIT_LN, "sd_fit_limit_ln_status": "SPEC §10 (accepted)",
              "poisson_sd_limit": poisson_sd_limit,
              "poisson_sd_limit_status": ("NOT_DECLARED (no accepted rule)" if poisson_sd_limit is None
                                          else "CALLER_DECLARED_RESEARCH_LIMIT (UNACCEPTED)")}
    refusals = []
    blocked = [n for n in estimated if formulation_use.get(n) == "NOT_USED_BY_ELEMENT_FORMULATION"]
    for name in blocked:
        result[name].status = ConstantStatus.NOT_IDENTIFIABLE
        result[name].reasons.append("not used by the element formulation of this model (it cannot affect any "
                                    "frequency)")
    if blocked:
        refusals.append(f"{', '.join(blocked)} cannot influence this model (element formulation)")
    if sensitivities is None:
        for name in estimated:
            if name not in blocked:
                result[name].reasons.append("no FE sensitivity evaluation available (NOT_EVALUATED)")
        if not established:
            for name in estimated:
                if name not in blocked:
                    result[name].reasons.append("no frozen accepted observations yet (their number is not known)")
        elif len(fit) < k:
            refusals.append(f"{len(fit)} accepted observation(s) for {k} parameters: the sensitivity system has rank "
                            f"≤ {len(fit)} < {k} whatever the FE model gives")
            for name in estimated:
                if name not in blocked:
                    result[name].status = ConstantStatus.NOT_IDENTIFIABLE
                    result[name].reasons.append(f"rank ≤ {len(fit)} accepted observations < {k} parameters")
        return IdentifiabilityAssessment(result, None, None, estimated, len(fit), len(fit_families),
                                         len(holdout_families), observability, None, [], refusals, limits)
    unevaluated = [n for n in estimated if column_status.get(n, "EVALUATED") != "EVALUATED"]
    for name in unevaluated:
        status = column_status[name]
        result[name].status = (ConstantStatus.NOT_IDENTIFIABLE if status == "NUMERICALLY_UNRESOLVED"
                               else ConstantStatus.NOT_EVALUATED)
        result[name].reasons.append(column_reasons.get(name, status))
    if unevaluated:
        refusals.append("columns not usable: " + ", ".join(unevaluated) + " (the joint system is not assessed "
                        "without them: a missing column cannot be assumed independent)")
        for name in estimated:
            if name not in unevaluated and name not in blocked:
                result[name].status = ConstantStatus.NOT_IDENTIFIABLE
                result[name].reasons.append("joint system incomplete (another estimated column is not usable)")
        return IdentifiabilityAssessment(result, None, None, estimated, len(fit), len(fit_families),
                                         len(holdout_families), observability, None, [], refusals, limits)
    if not fit:
        refusals.append("no FIT observation")
        for name in estimated:
            result[name].status = ConstantStatus.NOT_IDENTIFIABLE
            result[name].reasons.append("no FIT observation")
        return IdentifiabilityAssessment(result, None, None, estimated, 0, 0, len(holdout_families), False, None, [],
                                         refusals, limits)
    if any(r.sd_ln is None or not r.sd_ln > 0 for r in fit):
        raise ValueError("every FIT row needs an explicit positive sd_ln (Σ is never invented).")
    parameters = [ParameterDefinition(n, ParameterRole.GLOBAL) for n in estimated]
    parameters += [ParameterDefinition(c.parameter_id, ParameterRole.NUISANCE, c.specimen) for c in nuisance]
    row_values = {r.row_id: {**{n: sensitivities[r.row_id][n] for n in estimated},
                             **{c.parameter_id: c.sensitivities[r.row_id] for c in nuisance}} for r in fit}
    provenance = {n: f"central FD in {COORDINATE_UNITS[n]} (research)" for n in estimated}
    provenance.update({c.parameter_id: "caller nuisance column" for c in nuisance})
    matrix = build_sensitivity_matrix(row_values, [r.row_id for r in fit], [], parameters, provenance)
    covariance = ObservationCovariance(matrix.term_ids, (diagonal_component(
        "Sigma", matrix.term_ids, {r.row_id: r.sd_ln for r in fit}, sigma_provisional, sigma_provenance),))
    system = assemble_system(matrix, covariance, [c.prior for c in nuisance])
    analysis = analyse_practical_identifiability(system)
    record = analysis.to_dict()
    combinations = []
    if not analysis.full_rank:
        design = system.design()
        _, s, vt = np.linalg.svd(design, full_matrices=True)
        smax = float(s[0]) if s.size else 0.0
        null = [vt[i] for i in range(vt.shape[0]) if i >= s.size or s[i] <= RCOND * smax]
        ids = matrix.parameter_ids
        for i in range(min(s.size, vt.shape[0])):
            if s[i] > RCOND * smax:
                combinations.append({"singular_value": float(s[i]),
                                     "direction": {ids[j]: float(vt[i, j]) for j in range(len(ids))}})
        refusals.append(analysis.refusal_reasons[0])
        for j, name in enumerate(estimated):
            weight = float(np.linalg.norm([v[j] for v in null])) if null else 0.0
            result[name].status = ConstantStatus.NOT_IDENTIFIABLE
            result[name].null_space_weight = weight
            result[name].q = analysis.projections[name].q
            result[name].reasons.append(
                f"rank-deficient joint system (rank {analysis.rank} < {len(ids)}): SPEC §10 hard block; "
                f"null-space weight {weight:.3g}")
        return IdentifiabilityAssessment(result, analysis.status.value, analysis.rank, matrix.parameter_ids, len(fit),
                                         len(fit_families), len(holdout_families), observability, record,
                                         combinations, refusals, limits)
    for name in estimated:
        item = result[name]
        item.sd = analysis.sd_ln[name]
        item.q = analysis.projections[name].q
        if COORDINATES[name] is CoordinateKind.LOG:
            if item.sd > SD_FIT_LIMIT_LN:
                item.status = ConstantStatus.NOT_IDENTIFIABLE
                item.reasons.append(f"sd = {item.sd:.3g} in ln p > {SD_FIT_LIMIT_LN} (SPEC §10: not fitted)")
                continue
        else:
            if poisson_sd_limit is None:
                item.status = ConstantStatus.POLICY_OR_EVIDENCE_BLOCKER
                item.reasons.append(f"sd = {item.sd:.3g} (absolute ν); no accepted precision rule exists for Poisson "
                                    "ratios (SPEC §10 is in ln p): REQUIRES_SUPERVISOR_DECISION")
                continue
            if item.sd > poisson_sd_limit:
                item.status = ConstantStatus.NOT_IDENTIFIABLE
                item.reasons.append(f"sd = {item.sd:.3g} (absolute ν) > caller-declared research limit "
                                    f"{poisson_sd_limit:g} (UNACCEPTED)")
                continue
        if not observability:
            item.status = ConstantStatus.POLICY_OR_EVIDENCE_BLOCKER
            item.reasons.append(f"observation families: {len(fit_families)} FIT (need {k + 1} for {k} parameters) "
                                f"and {len(holdout_families)} distinct HOLDOUT (need 1) — SPEC v1.2 §8")
            continue
        item.status = ConstantStatus.SUPPORTED_RESEARCH_ESTIMATE
        item.reasons.append("full-rank joint system; statistical sd within the applicable limit (research only)")
    return IdentifiabilityAssessment(result, analysis.status.value, analysis.rank, matrix.parameter_ids, len(fit),
                                     len(fit_families), len(holdout_families), observability, record, combinations,
                                     refusals, limits)


# ----------------------------------------------------------------------------- research estimation

@dataclass
class EstimationResult:
    status: str  # ESTIMATED_RESEARCH / REFUSED_BEFORE_OPTIMISATION / REFUSED / BUDGET_EXHAUSTED
    start: dict[str, float]
    final: Optional[dict[str, float]]
    iterations: list[dict]
    gate: IdentifiabilityAssessment
    final_assessment: Optional[IdentifiabilityAssessment]
    residuals: list[dict]
    evaluations: int
    reasons: list[str]

    def to_dict(self) -> dict:
        return {"status": self.status, "start": self.start, "final": self.final, "iterations": self.iterations,
                "gate": self.gate.to_dict(),
                "final_assessment": None if self.final_assessment is None else self.final_assessment.to_dict(),
                "residuals": self.residuals, "evaluations": self.evaluations, "reasons": list(self.reasons),
                "claim": list(CLAIM_LABELS)}


def _residuals(log_f: Mapping[str, float], rows: Sequence[ObservationRow]) -> np.ndarray:
    return np.array([(log_f[r.row_id] - math.log(r.experimental_hz)) / r.sd_ln for r in rows])


def estimate_constants(forward: ForwardModel, start: EngineeringConstants, rows: Sequence[ObservationRow],
                       estimated: Sequence[str], fixed: Sequence[str], evaluation_limit: int,
                       design: SensitivityDesign = SensitivityDesign(), poisson_sd_limit: Optional[float] = None,
                       formulation_use: Optional[Mapping[str, str]] = None) -> EstimationResult:
    """Gate (sensitivities + identifiability at the start) → LM in x → fresh sensitivities at p̂ → assessment."""
    counter = EvaluationCounter(forward, evaluation_limit)
    estimated = tuple(estimated)
    fit = [r for r in rows if r.role is Role.FIT]
    holdout = [r for r in rows if r.role is Role.HOLDOUT]

    def refused(status, gate, reasons, final=None, iterations=(), residuals=(), final_assessment=None):
        return EstimationResult(status, start.to_dict(), final, list(iterations), gate, final_assessment,
                                list(residuals), counter.count, reasons)

    try:
        sens = central_sensitivities(counter, start, fit, estimated, design)
    except EvaluationBudgetExhausted as error:
        gate = assess_identifiability(start, rows, None, estimated, fixed, formulation_use=formulation_use)
        return refused("BUDGET_EXHAUSTED", gate, [str(error)])
    gate = assess_identifiability(start, rows, sens.values, estimated, fixed, sens.column_status, sens.column_reasons,
                                  formulation_use, poisson_sd_limit=poisson_sd_limit)
    unsupported = [n for n in estimated if gate.constants[n].status is not ConstantStatus.SUPPORTED_RESEARCH_ESTIMATE]
    if unsupported:
        return refused("REFUSED_BEFORE_OPTIMISATION", gate,
                       [f"not supported for estimation: {', '.join(unsupported)}; no optimisation is run"])
    reference = counter.evaluate(start)  # SPEC §12.1: follow branches from the last accepted state
    mapping = {row.row_id: row.baseline_fe_mode for row in list(fit) + list(holdout)}
    jacobian = np.array([[sens.values[r.row_id][n] / r.sd_ln for n in estimated] for r in fit])
    x = to_coordinates(start, estimated)
    current = start
    log_f, _, _ = _track(reference, {k: v for k, v in mapping.items() if k in {r.row_id for r in fit}}, reference)
    r = _residuals(log_f, fit)
    sd = np.array([gate.constants[n].sd for n in estimated])
    mu, history, status = LM_MU_INITIAL, [], "NOT_CONVERGED"
    try:
        for iteration in range(1, LM_MAX_ITERATIONS + 1):
            accepted = False
            for _ in range(LM_STEP_ATTEMPTS):
                step = lm_step(r, jacobian, mu)
                if np.max(np.abs(step) / sd) < LM_STOP_FRACTION:
                    status = "CONVERGED"
                    history.append({"iteration": iteration, "mu": mu, "note": "step below 0.2·sd (SPEC §8)"})
                    break
                trial_constants = from_coordinates(start, estimated, x + step)
                if not admissibility(trial_constants).admissible:
                    history.append({"iteration": iteration, "mu": mu, "note": "trial inadmissible: rejected"})
                    mu *= LM_MU_FACTOR
                    continue
                state = counter.evaluate(trial_constants)
                all_log_f, trial_mapping, _ = _track(reference, mapping, state)  # fit and holdout rows together
                trial_r = _residuals(all_log_f, fit)
                if objective(trial_r) < objective(r):
                    jacobian = jacobian + np.outer(trial_r - r - jacobian @ step, step) / float(step @ step)
                    x, r, current = x + step, trial_r, trial_constants
                    reference, mapping = state, trial_mapping
                    mu /= LM_MU_FACTOR
                    accepted = True
                    history.append({"iteration": iteration, "mu": mu, "objective": objective(r), "accepted": True})
                    break
                mu *= LM_MU_FACTOR
                history.append({"iteration": iteration, "mu": mu, "objective_trial": objective(trial_r),
                                "accepted": False})
            if status == "CONVERGED":
                break
            if not accepted:
                status = "STEP_REJECTED"
                break
        if status != "CONVERGED":
            return refused("REFUSED", gate, [f"LM ended {status} (no value is published)"], iterations=history)
        final_sens = central_sensitivities(counter, current, fit, estimated, design,
                                           {k: v for k, v in mapping.items() if k in {r.row_id for r in fit}})
        final = assess_identifiability(current, rows, final_sens.values, estimated, fixed, final_sens.column_status,
                                       final_sens.column_reasons, formulation_use, poisson_sd_limit=poisson_sd_limit)
        all_log_f, _, _ = _track(reference, mapping, counter.evaluate(current))
    except BranchTrackingRefusal as error:
        return refused("REFUSED", gate, [f"branch identity lost (no re-pairing): {error}"], iterations=history)
    except EvaluationBudgetExhausted as error:
        return refused("BUDGET_EXHAUSTED", gate, [str(error)], iterations=history)
    residuals = [{"row_id": row.row_id, "role": row.role.value, "family_key": row.family_key,
                  "experimental_hz": row.experimental_hz, "final_fe_hz": math.exp(all_log_f[row.row_id]),
                  "residual_ln": all_log_f[row.row_id] - math.log(row.experimental_hz)}
                 for row in list(fit) + list(holdout)]
    for name in estimated:
        if final.constants[name].status is ConstantStatus.SUPPORTED_RESEARCH_ESTIMATE:
            final.constants[name].estimate = getattr(current, name)
    if any(final.constants[n].status is not ConstantStatus.SUPPORTED_RESEARCH_ESTIMATE for n in estimated):
        return refused("REFUSED", gate, ["the assessment at p̂ does not support every estimated constant"],
                       final=None, iterations=history, residuals=residuals, final_assessment=final)
    return EstimationResult("ESTIMATED_RESEARCH", start.to_dict(), current.to_dict(), history, gate, final, residuals,
                            counter.count, [])


# ----------------------------------------------------------------------------- FE cost planning (Phase E)

@dataclass(frozen=True)
class EvaluationResourceProfile:
    """Per-evaluation resources of one FE model; ``basis`` says MEASURED or ESTIMATE (never mixed silently)."""

    basis: str
    minutes_per_evaluation: tuple[float, float]  # (low, high)
    disk_gb_per_evaluation: float
    scratch_peak_gb: float
    commit_peak_gb: float
    licence_tokens_per_solve: int
    source: str


SP13_MEASURED_PROFILE = EvaluationResourceProfile(
    "MEASURED (P4/P5 SP-13, 1 CPU, scratch on C: NVMe; solve + 30-mode extraction + post-processing)",
    (31.0, 33.0), 4.65, 10.1, 41.5, 3,
    "SP13_P4_pilot_20261014_ops, SP13_P5_lm_20261015_ops monitor records")


@dataclass(frozen=True)
class FECostPlan:
    estimated: int
    verified_cached: int
    potentially_reusable: int
    required_new_minimum: int
    required_new_typical: tuple[int, int]
    authorised_limit: Optional[int]
    within_authorised_limit: Optional[bool]
    breakdown: Mapping[str, int]
    resources: Optional[dict]
    notes: tuple[str, ...]

    def to_dict(self) -> dict:
        return {"estimated_constants": self.estimated, "verified_cached_evaluations": self.verified_cached,
                "potentially_reusable_not_verified": self.potentially_reusable,
                "required_new_minimum": self.required_new_minimum,
                "required_new_typical_range": list(self.required_new_typical),
                "authorised_limit": self.authorised_limit, "within_authorised_limit": self.within_authorised_limit,
                "breakdown": dict(self.breakdown), "resources": self.resources, "notes": list(self.notes)}


def plan_fe_evaluations(estimated: int, verified_cached: Sequence[str] = (), potentially_reusable: int = 0,
                        noise_check: bool = True, lm_trials: tuple[int, int] = (2, 15),
                        authorised_limit: Optional[int] = None,
                        profile: Optional[EvaluationResourceProfile] = None) -> FECostPlan:
    """Evaluation count of one nine-constant campaign. Verified cache entries are named by the caller (after
    verify_job_cache); unverified reuse is never counted as saved. The limit is never raised here."""
    if not 1 <= estimated <= 9:
        raise ValueError("1..9 estimated constants.")
    baseline = 0 if "baseline" in verified_cached else 1
    central = 2 * estimated
    noise = 2 * estimated if noise_check else 0
    final_sensitivities = 2 * estimated + (2 * estimated if noise_check else 0)
    breakdown = {"baseline": baseline, "central_differences_at_start": central, "noise_check_half_steps": noise,
                 "lm_trial_evaluations_min": lm_trials[0], "lm_trial_evaluations_max": lm_trials[1],
                 "fresh_sensitivities_at_optimum": final_sensitivities}
    minimum_gate = baseline + central + noise  # the identifiability gate alone (before any optimisation)
    typical = (minimum_gate + lm_trials[0] + final_sensitivities, minimum_gate + lm_trials[1] + final_sensitivities)
    notes = ["the identifiability gate (baseline + central differences + noise repeat) is evaluated before any "
             "optimisation; a refused gate stops there",
             "potentially reusable evaluations are not subtracted until verified (verify_job_cache)"]
    resources = None
    if profile is not None:
        low = typical[0] * profile.minutes_per_evaluation[0] / 60.0
        high = typical[1] * profile.minutes_per_evaluation[1] / 60.0
        resources = {"basis": profile.basis, "source": profile.source,
                     "hours_range": [round(low, 1), round(high, 1)],
                     "gate_only_hours": round(minimum_gate * profile.minutes_per_evaluation[1] / 60.0, 1),
                     "disk_gb_range_without_cleanup": [round(typical[0] * profile.disk_gb_per_evaluation),
                                                       round(typical[1] * profile.disk_gb_per_evaluation)],
                     "scratch_peak_gb": profile.scratch_peak_gb, "commit_peak_gb": profile.commit_peak_gb,
                     "licence_tokens_per_running_solve": profile.licence_tokens_per_solve,
                     "statement": "ESTIMATE from the per-evaluation profile; not a measurement of this campaign"}
    within = None if authorised_limit is None else typical[1] <= authorised_limit
    return FECostPlan(estimated, len(verified_cached), int(potentially_reusable), minimum_gate, typical,
                      authorised_limit, within, breakdown, resources, tuple(notes))
