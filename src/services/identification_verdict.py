"""IDENTIFIED / WIDE / NOT_IDENTIFIABLE verdict engine — Auto-ID M5.9 (SPEC §1, §3, §5.1, §9, §10; D-001, D-012,
D-039–D-044; M5_DECISION_RECORD.md §19).

A pure function of explicit evidence records: no Abaqus, no file system, no GUI state, no hidden
defaults. Missing evidence is never an implicit PASS, and there is no user override.

Per **global** parameter j (material constants; nuisance parameters are specimen parameters, not
verdict subjects), in ln p:

    conservative_ln = max(birge_adjusted_sd_ln, model_form_half_range_ln)
    ≤ 0.05 → IDENTIFIED;  ≤ 0.08 → WIDE;  > 0.08 → NOT_IDENTIFIABLE   (SPEC §3, decided in ln p)

These are applied only when every guard passes. **NOT_IDENTIFIABLE** (with reasons) results from
any of the following:
- practical rank deficiency;
- `statistical_sd` sd_ln > 0.08 (SPEC §10, not fitted; the estimate is preserved for provenance,
  with no refit);
- the systematic residual pattern or a holdout with |r| > 3;
- `birge_adjusted_sd` unavailable;
- a refused or missing `model_form_robustness`;
- a fitting-pair MAC violation;
- branch or pairing loss;
- `registration_limited`;
- peak-derived input;
- family consistency FAIL, or NOT_AVAILABLE outside the explicit SYNTHETIC_GATE context (D-044);
- the sandwich-G12 policy (SPEC §5.1);
- any explicit upstream refusal.

WIDE never hides any of these.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Optional, Sequence

from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING
from domain.identification_run import canonical_hash

from .identification_uncertainty import (
    BirgeResult,
    BirgeStatus,
    PatternTestResult,
    ResidualTerm,
    StatisticalSDResult,
    StatisticalStatus,
    birge_adjustment,
    residual_pattern_test,
    statistical_sd,
)
from .model_form_robustness import ModelFormRobustnessResult, linearised_model_form_robustness
from .practical_identifiability import (
    G12_PARAMETER,
    SD_FIT_LIMIT_LN,
    ParameterRole,
    PracticalIdentifiabilityInputError,
    PracticalIdentifiabilityResult,
    PracticalSystem,
    analyse_practical_identifiability,
)


SCHEMA = "auto-id/identification-verdict/v1"
IDENTIFIED_LIMIT_LN = 0.05  # SPEC §3 (5 %), compared in ln p (M5_DECISION_RECORD §19)
WIDE_LIMIT_LN = 0.08  # SPEC §3 (8 %), compared in ln p
FITTING_PAIR_MINIMUM_MAC = STRICT_IDENTIFICATION_PAIRING.minimum_mac  # SPEC §3 "all fitting pairs MAC ≥ 0.8"
_DIGITS = 12


def _r(value):
    return None if value is None else float(f"{float(value):.{_DIGITS}g}")


class Verdict(str, Enum):
    IDENTIFIED = "IDENTIFIED"
    WIDE = "WIDE"
    NOT_IDENTIFIABLE = "NOT_IDENTIFIABLE"


class VerdictContext(str, Enum):
    SYNTHETIC_GATE = "SYNTHETIC_GATE"  # explicit synthetic M5 stage-gate case (D-039, D-044)
    PRODUCTION = "PRODUCTION"  # real data


class EvidenceState(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class Reason(str, Enum):
    RANK_DEFICIENT = "RANK_DEFICIENT"
    SD_ABOVE_8_PERCENT = "SD_ABOVE_8_PERCENT"
    CONSERVATIVE_ABOVE_8_PERCENT = "CONSERVATIVE_ABOVE_8_PERCENT"
    SYSTEMATIC_PATTERN = "SYSTEMATIC_PATTERN"
    HOLDOUT_FAILURE = "HOLDOUT_FAILURE"
    BIRGE_UNAVAILABLE = "BIRGE_UNAVAILABLE"
    MODEL_FORM_ROBUSTNESS_REFUSED = "MODEL_FORM_ROBUSTNESS_REFUSED"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    FITTING_PAIR_MAC = "FITTING_PAIR_MAC"
    BRANCH_OR_PAIRING_LOSS = "BRANCH_OR_PAIRING_LOSS"
    REGISTRATION_LIMITED = "REGISTRATION_LIMITED"
    PEAK_DERIVED_INPUT = "PEAK_DERIVED_INPUT"
    FAMILY_CONSISTENCY = "FAMILY_CONSISTENCY"
    BARE_PLATE_REQUIRED = "BARE_PLATE_REQUIRED"
    NUISANCE_NOT_INDEPENDENTLY_CONSTRAINED = "NUISANCE_NOT_INDEPENDENTLY_CONSTRAINED"
    UPSTREAM_REFUSAL = "UPSTREAM_REFUSAL"


@dataclass(frozen=True)
class GuardEvidence:
    """One explicit guard input. PASS means the guard is satisfied (for example `registration_limited` is false)."""

    name: str
    state: EvidenceState
    provenance: str
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.state, EvidenceState):
            raise PracticalIdentifiabilityInputError(f"{self.name}: state must be an EvidenceState.")
        if not isinstance(self.provenance, str) or not self.provenance.strip():
            raise PracticalIdentifiabilityInputError(f"{self.name}: provenance required.")

    def to_dict(self) -> dict:
        return {"name": self.name, "state": self.state.value, "provenance": self.provenance, "detail": self.detail}


def fitting_pair_mac_evidence(fit_row_macs: Mapping[str, float], provenance: str) -> GuardEvidence:
    """SPEC §3: every fitting pair has MAC ≥ 0.8 (the strict pairing minimum; no second threshold)."""
    if not fit_row_macs:
        return GuardEvidence("fitting_pair_mac", EvidenceState.NOT_AVAILABLE, provenance, "no fitting-pair MAC given")
    low = {k: v for k, v in fit_row_macs.items() if not v >= FITTING_PAIR_MINIMUM_MAC}
    state = EvidenceState.FAIL if low else EvidenceState.PASS
    return GuardEvidence("fitting_pair_mac", state, provenance,
                         f"min MAC {min(fit_row_macs.values()):.6g}; below {FITTING_PAIR_MINIMUM_MAC}: {sorted(low)}")


@dataclass(frozen=True)
class NuisanceConstraint:
    """Whether a nuisance quantity is constrained independently of the modal fit being evaluated (SPEC §5.1)."""

    parameter_id: str
    independent_source: bool  # provenance independent of the evaluated modal fit (never its own residuals)
    provisional: bool
    synthetic_definition: bool  # an explicit part of a synthetic case definition
    provenance: str

    def satisfied(self, context: VerdictContext) -> bool:
        if not self.independent_source:
            return False
        if context is VerdictContext.SYNTHETIC_GATE and self.synthetic_definition:
            return True
        return not self.provisional and not self.synthetic_definition

    def to_dict(self) -> dict:
        return {"parameter_id": self.parameter_id, "independent_source": self.independent_source,
                "provisional": self.provisional, "synthetic_definition": self.synthetic_definition,
                "provenance": self.provenance}


@dataclass(frozen=True)
class SandwichG12Evidence:
    """SPEC §5.1 inputs for a sandwich G12 parameter."""

    applies: bool  # True when G12 is estimated from sandwich modal data
    bare_plate: EvidenceState  # Stage-A bare-plate support: PASS present, NOT_AVAILABLE absent
    required_nuisance_ids: tuple[str, ...]  # core (and interface where relevant) quantities
    constraints: Mapping[str, NuisanceConstraint]
    provenance: str

    def to_dict(self) -> dict:
        return {"applies": self.applies, "bare_plate": self.bare_plate.value,
                "required_nuisance_ids": list(self.required_nuisance_ids),
                "constraints": {k: v.to_dict() for k, v in sorted(self.constraints.items())},
                "provenance": self.provenance}


@dataclass(frozen=True)
class VerdictInputs:
    context: VerdictContext
    case_label: str
    analysis: PracticalIdentifiabilityResult
    statistical: Optional[StatisticalSDResult]
    pattern: Optional[PatternTestResult]
    birge: Optional[BirgeResult]
    robustness: Optional[ModelFormRobustnessResult]
    fitting_pair_mac: GuardEvidence
    registration: GuardEvidence  # PASS = not registration-limited (M2 diagnostic; explicit false for synthetic)
    peak_derived_input: GuardEvidence  # PASS = no peak-derived modal input
    tracking: GuardEvidence  # PASS = no branch / pairing loss
    family_consistency: GuardEvidence
    sandwich_g12: SandwichG12Evidence
    p_hat: Mapping[str, float]  # the accepted fitted estimates (preserved for provenance)
    parameter_roles: Mapping[str, ParameterRole]
    upstream_refusals: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParameterVerdict:
    parameter_id: str
    verdict: Verdict
    reasons: tuple[str, ...]
    fitted_estimate: float  # preserved for provenance; never promoted unless IDENTIFIED / WIDE
    reported_value: Optional[float]  # only for IDENTIFIED / WIDE (SPEC §3)
    statistical_sd_ln: Optional[float]
    birge_adjusted_sd_ln: Optional[float]
    model_form_robustness: Optional[Mapping[str, float]]  # range / half-range in ln p, % of p̂ for readability
    conservative_ln: Optional[float]  # verdict envelope: max(birge_adjusted_sd_ln, model_form half-range ln)

    def to_dict(self) -> dict:
        return {"parameter_id": self.parameter_id, "verdict": self.verdict.value, "reasons": list(self.reasons),
                "fitted_estimate": _r(self.fitted_estimate), "reported_value": _r(self.reported_value),
                "statistical_sd_ln": _r(self.statistical_sd_ln), "birge_adjusted_sd_ln": _r(self.birge_adjusted_sd_ln),
                "model_form_robustness": None if self.model_form_robustness is None else
                {k: _r(v) for k, v in sorted(self.model_form_robustness.items())},
                "conservative_ln": _r(self.conservative_ln)}


@dataclass(frozen=True)
class VerdictReport:
    context: VerdictContext
    case_label: str
    verdicts: Mapping[str, ParameterVerdict]
    guards: Mapping[str, str]  # guard name → PASS / FAIL / NOT_AVAILABLE
    q_g: Optional[float]  # diagnostic only, no threshold
    evidence_hashes: Mapping[str, Optional[str]]
    sandwich_g12: Mapping[str, object]
    upstream_refusals: tuple[str, ...]
    note: str = ("statistical_sd, birge_adjusted_sd and model_form_robustness are kept separately; conservative_ln "
                 "is only the verdict envelope (SPEC §9, D-012)")

    def to_dict(self) -> dict:
        return {"schema": SCHEMA, "context": self.context.value, "case_label": self.case_label, "note": self.note,
                "verdicts": {k: v.to_dict() for k, v in sorted(self.verdicts.items())},
                "guards": dict(sorted(self.guards.items())), "q_g": _r(self.q_g),
                "evidence_hashes": dict(sorted(self.evidence_hashes.items())), "sandwich_g12": self.sandwich_g12,
                "upstream_refusals": list(self.upstream_refusals)}

    @property
    def record_hash(self) -> str:
        return canonical_hash(self.to_dict())


def _bind(inputs: VerdictInputs) -> None:
    system_hash = inputs.analysis.system_hash
    for name, record in (("statistical", inputs.statistical), ("robustness", inputs.robustness)):
        if record is not None and record.system_hash != system_hash:
            raise PracticalIdentifiabilityInputError(f"{name} evidence belongs to another system.")
    if inputs.birge is not None:
        if inputs.statistical is None or inputs.birge.statistical_record_hash != inputs.statistical.record_hash:
            raise PracticalIdentifiabilityInputError("Birge evidence is not bound to this statistical_sd.")
        if inputs.pattern is None or inputs.birge.pattern_record_hash != inputs.pattern.record_hash:
            raise PracticalIdentifiabilityInputError("Birge evidence is not bound to this pattern test.")
    if set(inputs.p_hat) != set(inputs.analysis.parameter_ids) or set(inputs.parameter_roles) != set(inputs.p_hat):
        raise PracticalIdentifiabilityInputError("p̂ and parameter roles must cover exactly the system parameters.")


def decide_verdicts(inputs: VerdictInputs) -> VerdictReport:
    """M5.9: parameter-level verdicts from explicit evidence. Pure; no override; missing evidence never passes."""

    if not isinstance(inputs, VerdictInputs):
        raise TypeError("decide_verdicts consumes a VerdictInputs evidence record.")
    if not isinstance(inputs.context, VerdictContext):
        raise PracticalIdentifiabilityInputError("an explicit VerdictContext is required.")
    _bind(inputs)
    synthetic = inputs.context is VerdictContext.SYNTHETIC_GATE

    # Stage-level blocks, common to every parameter.
    common: list[str] = []
    if not inputs.analysis.full_rank:
        common.append(f"{Reason.RANK_DEFICIENT.value}: " + "; ".join(inputs.analysis.refusal_reasons))
    for refusal in inputs.upstream_refusals:
        common.append(f"{Reason.UPSTREAM_REFUSAL.value}: {refusal}")
    guard_reason = {"fitting_pair_mac": Reason.FITTING_PAIR_MAC, "registration": Reason.REGISTRATION_LIMITED,
                    "peak_derived_input": Reason.PEAK_DERIVED_INPUT, "tracking": Reason.BRANCH_OR_PAIRING_LOSS}
    guards = {"fitting_pair_mac": inputs.fitting_pair_mac, "registration": inputs.registration,
              "peak_derived_input": inputs.peak_derived_input, "tracking": inputs.tracking}
    for key, guard in guards.items():
        if guard.state is EvidenceState.FAIL:
            common.append(f"{guard_reason[key].value}: {guard.detail}".rstrip(": "))
        elif guard.state is EvidenceState.NOT_AVAILABLE:
            common.append(f"{Reason.MISSING_EVIDENCE.value}: {key} not available")
    family = inputs.family_consistency.state
    if family is EvidenceState.FAIL:
        common.append(f"{Reason.FAMILY_CONSISTENCY.value}: failed")
    elif family is EvidenceState.NOT_AVAILABLE and not synthetic:
        common.append(f"{Reason.FAMILY_CONSISTENCY.value}: required family consistency NOT_AVAILABLE "
                      "(blocks IDENTIFIED for production; D-044)")
    pattern_state = holdout_state = EvidenceState.NOT_AVAILABLE
    if inputs.pattern is None:
        common.append(f"{Reason.MISSING_EVIDENCE.value}: residual-pattern test not available")
    else:
        pattern_state = EvidenceState.FAIL if inputs.pattern.systematic_families else EvidenceState.PASS
        holdout_state = EvidenceState.FAIL if inputs.pattern.holdout_failures else EvidenceState.PASS
        if inputs.pattern.systematic_families:
            common.append(f"{Reason.SYSTEMATIC_PATTERN.value}: families {list(inputs.pattern.systematic_families)} "
                          "(probable model-form error)")
        if inputs.pattern.holdout_failures:
            common.append(f"{Reason.HOLDOUT_FAILURE.value}: {list(inputs.pattern.holdout_failures)} |r| > 3")
    if inputs.birge is None or inputs.birge.status is not BirgeStatus.AVAILABLE:
        status = "missing" if inputs.birge is None else inputs.birge.status.value
        common.append(f"{Reason.BIRGE_UNAVAILABLE.value}: birge_adjusted_sd not available ({status}); model form")
    if inputs.robustness is None:
        common.append(f"{Reason.MISSING_EVIDENCE.value}: model_form_robustness not available")
    elif not inputs.robustness.supports_green:
        common.append(f"{Reason.MODEL_FORM_ROBUSTNESS_REFUSED.value}: refused families "
                      f"{list(inputs.robustness.refused_families)}")
    if inputs.statistical is None or inputs.statistical.status is not StatisticalStatus.AVAILABLE:
        common.append(f"{Reason.MISSING_EVIDENCE.value}: statistical_sd not available")

    sandwich = inputs.sandwich_g12
    verdicts = {}
    for parameter, role in inputs.parameter_roles.items():
        if role is not ParameterRole.GLOBAL:
            continue
        reasons = list(common)
        sd = None if inputs.statistical is None or inputs.statistical.statistical_sd_ln is None else \
            inputs.statistical.statistical_sd_ln.get(parameter)
        if inputs.analysis.full_rank and inputs.analysis.exceeds_sd_fit_limit.get(parameter):
            reasons.append(f"{Reason.SD_ABOVE_8_PERCENT.value}: sd_ln {inputs.analysis.sd_ln[parameter]:.4g} > "
                           f"{SD_FIT_LIMIT_LN:g} (SPEC §10: not fitted; estimate preserved, no refit)")
        birge = None if inputs.birge is None or inputs.birge.birge_adjusted_sd_ln is None else \
            inputs.birge.birge_adjusted_sd_ln.get(parameter)
        robustness = None
        half_range_ln = None
        if inputs.robustness is not None and parameter in inputs.robustness.parameters:
            item = inputs.robustness.parameters[parameter]
            half_range_ln = 0.5 * (item.max_shift_ln - item.min_shift_ln)
            robustness = {"range_ln": item.max_shift_ln - item.min_shift_ln, "half_range_ln": half_range_ln,
                          "range_percent_of_p_hat": item.range_percent_of_p_hat,
                          "half_range_percent_of_p_hat": item.half_range_percent_of_p_hat}
        if parameter == G12_PARAMETER and sandwich.applies:
            missing = [n for n in sandwich.required_nuisance_ids
                       if n not in sandwich.constraints or not _constraint_satisfied(
                           sandwich.constraints[n], inputs.context, inputs.analysis)]
            family_ok = family is EvidenceState.PASS or (synthetic and family is EvidenceState.NOT_AVAILABLE)
            sandwich_path = not missing and family_ok
            if sandwich.bare_plate is not EvidenceState.PASS and not sandwich_path:
                reasons.append(f"{Reason.BARE_PLATE_REQUIRED.value}: sandwich G12 without bare-plate support and "
                               "without a complete SPEC §5.1 sandwich path")
            if missing:
                reasons.append(f"{Reason.NUISANCE_NOT_INDEPENDENTLY_CONSTRAINED.value}: {missing}")
        conservative = None if birge is None or half_range_ln is None else max(birge, half_range_ln)
        if not reasons:
            if conservative is None:
                reasons.append(f"{Reason.MISSING_EVIDENCE.value}: conservative envelope not computable")
            elif conservative > WIDE_LIMIT_LN:
                reasons.append(f"{Reason.CONSERVATIVE_ABOVE_8_PERCENT.value}: conservative_ln {conservative:.4g} > "
                               f"{WIDE_LIMIT_LN:g}")
        if reasons:
            verdict = Verdict.NOT_IDENTIFIABLE
        elif conservative <= IDENTIFIED_LIMIT_LN:
            verdict = Verdict.IDENTIFIED
        else:
            verdict = Verdict.WIDE
        estimate = float(inputs.p_hat[parameter])
        verdicts[parameter] = ParameterVerdict(parameter, verdict, tuple(reasons), estimate,
                                               estimate if verdict is not Verdict.NOT_IDENTIFIABLE else None,
                                               sd, birge, robustness, conservative)
    guard_states = {k: g.state.value for k, g in guards.items()}
    guard_states.update({"family_consistency": family.value, "residual_pattern": pattern_state.value,
                         "holdout_validation": holdout_state.value})
    hashes = {"system": inputs.analysis.system_hash, "analysis": inputs.analysis.record_hash,
              "statistical_sd": None if inputs.statistical is None else inputs.statistical.record_hash,
              "pattern": None if inputs.pattern is None else inputs.pattern.record_hash,
              "birge": None if inputs.birge is None else inputs.birge.record_hash,
              "model_form_robustness": None if inputs.robustness is None else inputs.robustness.record_hash}
    return VerdictReport(inputs.context, inputs.case_label, verdicts, guard_states, inputs.analysis.q_g, hashes,
                         sandwich.to_dict(), tuple(inputs.upstream_refusals))


def _constraint_satisfied(constraint: NuisanceConstraint, context: VerdictContext,
                          analysis: PracticalIdentifiabilityResult) -> bool:
    # A prior flagged PROVISIONAL in the system is provisional, whatever the constraint record says.
    provisional = constraint.provisional or f"prior:{constraint.parameter_id}" in analysis.provisional_inputs
    effective = NuisanceConstraint(constraint.parameter_id, constraint.independent_source, provisional,
                                   constraint.synthetic_definition, constraint.provenance)
    if context is VerdictContext.SYNTHETIC_GATE and constraint.synthetic_definition:
        return constraint.independent_source
    return effective.satisfied(context)


@dataclass(frozen=True)
class EvidenceChain:
    analysis: PracticalIdentifiabilityResult
    statistical: StatisticalSDResult
    pattern: PatternTestResult
    birge: BirgeResult
    robustness: Optional[ModelFormRobustnessResult]  # None when the full system is rank-deficient


def compute_evidence_chain(system: PracticalSystem, fit_terms: Sequence[ResidualTerm],
                           holdout_terms: Sequence[ResidualTerm], p_hat: Mapping[str, float],
                           context_label: str) -> EvidenceChain:
    """M5.3 → M5.5 → M5.8 → M5.6 → M5.7 on one accepted system at p̂ (pure; no refit, no Abaqus)."""
    analysis = analyse_practical_identifiability(system)
    statistical = statistical_sd(system, context_label)
    pattern = residual_pattern_test(fit_terms, holdout_terms)
    birge = birge_adjustment(system, statistical, pattern, fit_terms)
    robustness = linearised_model_form_robustness(system, fit_terms, p_hat) if analysis.full_rank else None
    return EvidenceChain(analysis, statistical, pattern, birge, robustness)
