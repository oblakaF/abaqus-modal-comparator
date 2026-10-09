"""Pure SPECIMEN_ENGINEERING_CALIBRATION scientific gate — Auto-ID V12-I3 (SPEC v1.2 §6–§8, §10; D-078).

Consumes explicit, already-computed evidence for **one** physical specimen and returns a deterministic
gate record with status PASS or REFUSED. It runs no Abaqus, no optimisation, reads no files, stores or GUI
state, has no defaults and no override, and **emits no value**: neither a calibration value nor a material
property. A PASS means only that the SPEC v1.2 calibration gates represented here pass; the released
calibration record and its output belong to V12-I4.

Gates (all required; every failure is a machine-readable refusal reason):

1. question / identity: schema v1.2, scientific_question SPECIMEN_ENGINEERING_CALIBRATION, τ_mf declared,
   exactly one physical specimen;
2. observability (§8): ≥ k + 1 distinct FIT family keys, full practical rank at the M5 RCOND, every
   leave-one-FIT-family-out case VALID, ≥ 1 HOLDOUT family, HOLDOUT families disjoint from FIT families;
3. pairing / tracking: strict baseline FIT pair MAC ≥ 0.80, FE-to-FE tracking MAC ≥ 0.90, no branch or
   pairing loss (the strict pairing policy; no lowered MAC);
4. no active parameter bound (the repository's search-bound semantics);
5. registration not limited, no peak-derived input;
6. pattern / holdout: the V12-I2 τ_mf-aware pattern record for the declared τ_mf, no systematic family, no
   holdout failure (consumed, never recomputed);
7. non-degradation (§7): the same governed FIT + HOLDOUT terms; max |Δ ln f| and RMS Δ ln f not worse than
   the baseline; every term |expm1(Δ ln f)| ≤ 0.08;
8. precision (§6): per calibrated parameter, conservative_uncertainty = max(birge_adjusted_sd,
   0.5·(max_shift_ln − min_shift_ln)) ≤ 0.08 in ln p over the complete leave-one-FIT-family-out set;
9. complete reporting evidence (FIT and HOLDOUT residuals, excluded high-MAC diagnostic modes, uncertainty
   basis) — the record itself is V12-I4.

τ_mf is an acceptance tolerance only: it never enters statistical_sd, birge_adjusted_sd,
model_form_robustness or conservative_uncertainty. While Σ_meas is NOT_AVAILABLE or a covariance component
is provisional, the record states UNCERTAINTY_CONDITIONAL_ON_AVAILABLE_COVARIANCE. The material verdict is a
separate question (§1) and is neither an input nor an output here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Mapping, Optional, Sequence

from domain.campaign_definition import (
    CAMPAIGN_SCHEMA_V1_2,
    SPECIMEN_ENGINEERING_CALIBRATION,
    CampaignDefinition,
    at_search_bound,
)
from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING
from domain.identification_run import canonical_hash

from .identification_uncertainty import BirgeResult, BirgeStatus, PatternTestResult, StatisticalSDResult
from .identification_verdict import EvidenceState, GuardEvidence
from .model_form_robustness import CaseStatus, ModelFormRobustnessResult
from .practical_identifiability import RCOND, PracticalIdentifiabilityInputError, PracticalIdentifiabilityResult


SCHEMA = "auto-id/specimen-calibration-gate/v1"
QUANTITY = "specimen_engineering_calibration_gate"
ROW_RELATIVE_ERROR_CEILING = 0.08  # SPEC v1.2 §7: every governed row |relative frequency error| ≤ 8 %
PRECISION_CEILING_LN = 0.08  # SPEC v1.2 §6: conservative_uncertainty ≤ 0.08 in ln p
CONDITIONAL_COVARIANCE = "UNCERTAINTY_CONDITIONAL_ON_AVAILABLE_COVARIANCE"
COMPLETE_COVARIANCE = "COVARIANCE_COMPONENTS_COMPLETE_AND_MEASURED"
_DIGITS = 12


def _r(value):
    return None if value is None else float(f"{float(value):.{_DIGITS}g}")


class CalibrationGateStatus(str, Enum):
    PASS = "PASS"
    REFUSED = "REFUSED"


class CalibrationRefusal(str, Enum):
    WRONG_SCHEMA_OR_QUESTION = "WRONG_SCHEMA_OR_QUESTION"
    TAU_MF_NOT_DECLARED = "TAU_MF_NOT_DECLARED"
    SPECIMEN_COUNT = "SPECIMEN_COUNT"
    INSUFFICIENT_FIT_FAMILIES = "INSUFFICIENT_FIT_FAMILIES"
    NO_HOLDOUT_FAMILY = "NO_HOLDOUT_FAMILY"
    HOLDOUT_FAMILY_OVERLAPS_FIT = "HOLDOUT_FAMILY_OVERLAPS_FIT"
    RANK_DEFICIENT = "RANK_DEFICIENT"
    LOO_INCOMPLETE = "LOO_INCOMPLETE"
    BASELINE_PAIR_MAC = "BASELINE_PAIR_MAC"
    TRACKING_MAC = "TRACKING_MAC"
    BRANCH_OR_PAIRING_LOSS = "BRANCH_OR_PAIRING_LOSS"
    ACTIVE_PARAMETER_BOUND = "ACTIVE_PARAMETER_BOUND"
    REGISTRATION_LIMITED = "REGISTRATION_LIMITED"
    PEAK_DERIVED_INPUT = "PEAK_DERIVED_INPUT"
    PATTERN_EVIDENCE_NOT_V1_2 = "PATTERN_EVIDENCE_NOT_V1_2"
    TAU_MF_MISMATCH = "TAU_MF_MISMATCH"
    SYSTEMATIC_PATTERN = "SYSTEMATIC_PATTERN"
    HOLDOUT_FAILURE = "HOLDOUT_FAILURE"
    TERM_SET_MISMATCH = "TERM_SET_MISMATCH"
    MAX_DEGRADED = "MAX_DEGRADED"
    RMS_DEGRADED = "RMS_DEGRADED"
    ROW_RELATIVE_ERROR_ABOVE_CEILING = "ROW_RELATIVE_ERROR_ABOVE_CEILING"
    BIRGE_UNAVAILABLE = "BIRGE_UNAVAILABLE"
    CONSERVATIVE_ABOVE_CEILING = "CONSERVATIVE_ABOVE_CEILING"
    REPORTING_INCOMPLETE = "REPORTING_INCOMPLETE"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"


@dataclass(frozen=True)
class GovernedTerm:
    """One governed FIT or HOLDOUT term of the specimen, unwhitened: Δ ln f = ln(f_FE / f_EXP)."""

    term_id: str
    role: str  # FIT | HOLDOUT
    delta_ln_f: float

    def __post_init__(self) -> None:
        if not isinstance(self.term_id, str) or not self.term_id or self.role not in ("FIT", "HOLDOUT"):
            raise PracticalIdentifiabilityInputError("a governed term needs an id and the role FIT or HOLDOUT.")
        if isinstance(self.delta_ln_f, bool) or not isinstance(self.delta_ln_f, (int, float)) \
                or not math.isfinite(float(self.delta_ln_f)):
            raise PracticalIdentifiabilityInputError(f"{self.term_id}: Δ ln f must be finite.")


@dataclass(frozen=True)
class ReportingCompleteness:
    """Presence of the evidence the V12-I4 calibration record must carry (the record itself is not built here)."""

    fit_residuals: bool
    holdout_residuals: bool
    excluded_high_mac_modes: bool
    uncertainty_basis: bool

    def to_dict(self) -> dict:
        return {"fit_residuals": self.fit_residuals, "holdout_residuals": self.holdout_residuals,
                "excluded_high_mac_modes": self.excluded_high_mac_modes, "uncertainty_basis": self.uncertainty_basis}


@dataclass(frozen=True)
class CalibrationGateInputs:
    definition: CampaignDefinition  # question, τ_mf, specimen, k, search bounds, Σ
    p_hat: Mapping[str, float]  # the candidate calibration parameters (evidence only; never released here)
    fit_families: Mapping[str, str]  # FIT term id → M4.3 family key (a confirmed cluster is one term)
    holdout_families: Mapping[str, str]  # HOLDOUT term id → family key
    analysis: Optional[PracticalIdentifiabilityResult]
    robustness: Optional[ModelFormRobustnessResult]
    pattern: Optional[PatternTestResult]
    statistical: Optional[StatisticalSDResult]
    birge: Optional[BirgeResult]
    baseline_pair_macs: Mapping[str, float]  # FIT term id → strict baseline pair MAC
    tracking_macs: Mapping[str, float]  # governed term id → FE-to-FE tracking MAC at the candidate
    branch_pairing: GuardEvidence  # PASS = no branch or pairing loss
    registration: GuardEvidence  # PASS = not registration-limited
    peak_derived_input: GuardEvidence  # PASS = no peak-derived modal input
    baseline_terms: Sequence[GovernedTerm]  # the governed baseline FE state
    candidate_terms: Sequence[GovernedTerm]
    reporting: Optional[ReportingCompleteness]


@dataclass(frozen=True)
class CalibrationGateResult:
    status: CalibrationGateStatus
    scientific_question: Optional[str]
    tau_mf: Optional[float]
    campaign_hash: str
    specimen: Optional[Mapping[str, str]]
    parameter_ids: tuple[str, ...]
    observability: Optional[Mapping[str, object]]
    pairing_tracking: Optional[Mapping[str, object]]
    bounds: Optional[Mapping[str, object]]
    registration_peak: Optional[Mapping[str, object]]
    pattern_holdout: Optional[Mapping[str, object]]
    non_degradation: Optional[Mapping[str, object]]
    precision: Optional[Mapping[str, object]]
    uncertainty_basis: Optional[Mapping[str, object]]
    reporting_completeness: Optional[Mapping[str, object]]
    refusal_reasons: tuple[Mapping[str, str], ...]
    note: str = ("SPEC v1.2 specimen-calibration scientific gate only: no calibration value, no material property "
                 "(the released record is V12-I4); a PASS is never IDENTIFIED or WIDE")

    @property
    def passed(self) -> bool:
        return self.status is CalibrationGateStatus.PASS

    @property
    def refusal_codes(self) -> tuple[str, ...]:
        return tuple(r["code"] for r in self.refusal_reasons)

    def to_dict(self) -> dict:
        return {"schema": SCHEMA, "quantity": QUANTITY, "note": self.note, "status": self.status.value,
                "scientific_question": self.scientific_question, "tau_mf": self.tau_mf,
                "campaign_hash": self.campaign_hash, "specimen": self.specimen,
                "parameter_ids": list(self.parameter_ids), "observability": self.observability,
                "pairing_tracking": self.pairing_tracking, "bounds": self.bounds,
                "registration_peak": self.registration_peak, "pattern_holdout": self.pattern_holdout,
                "non_degradation": self.non_degradation, "precision": self.precision,
                "uncertainty_basis": self.uncertainty_basis, "reporting_completeness": self.reporting_completeness,
                "refusal_reasons": [dict(r) for r in self.refusal_reasons]}

    @property
    def record_hash(self) -> str:
        return canonical_hash(self.to_dict())


class _Refusals:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, code: CalibrationRefusal, detail: str) -> None:
        self.items.append({"code": code.value, "detail": detail})


def _bind(inputs: CalibrationGateInputs) -> None:
    """Evidence must belong together; an inconsistent bundle is an input error, never a PASS or a refusal."""
    analysis = inputs.analysis
    if analysis is not None:
        if set(analysis.parameter_ids) != set(inputs.definition.fitted_parameters):
            raise PracticalIdentifiabilityInputError("the M5 analysis does not cover exactly the fitted parameters.")
        for name, record in (("statistical_sd", inputs.statistical), ("model_form_robustness", inputs.robustness)):
            if record is not None and record.system_hash != analysis.system_hash:
                raise PracticalIdentifiabilityInputError(f"{name} evidence belongs to another system.")
    if inputs.birge is not None:
        if inputs.statistical is None or inputs.birge.statistical_record_hash != inputs.statistical.record_hash:
            raise PracticalIdentifiabilityInputError("Birge evidence is not bound to this statistical_sd.")
        if inputs.pattern is None or inputs.birge.pattern_record_hash != inputs.pattern.record_hash:
            raise PracticalIdentifiabilityInputError("Birge evidence is not bound to this pattern test.")
    if inputs.robustness is not None and inputs.robustness.family_mapping_hash != canonical_hash(
            dict(inputs.fit_families)):
        raise PracticalIdentifiabilityInputError("model_form_robustness was computed for another FIT family mapping.")
    if inputs.pattern is not None:
        fit_ids = {t for f in inputs.pattern.families for t in f.term_ids}
        if fit_ids != set(inputs.fit_families) or set(inputs.pattern.holdouts) != set(inputs.holdout_families):
            raise PracticalIdentifiabilityInputError("the pattern record judged other FIT / HOLDOUT terms.")
    if set(inputs.p_hat) != set(inputs.definition.fitted_parameters):
        raise PracticalIdentifiabilityInputError("p̂ must give exactly the fitted calibration parameters.")


def _observability(inputs: CalibrationGateInputs, k: int, refusals: _Refusals) -> dict:
    fit_keys = sorted(set(inputs.fit_families.values()))
    holdout_keys = sorted(set(inputs.holdout_families.values()))
    overlap = sorted(set(fit_keys) & set(holdout_keys))
    if len(fit_keys) < k + 1:
        refusals.add(CalibrationRefusal.INSUFFICIENT_FIT_FAMILIES,
                     f"{len(fit_keys)} distinct FIT families {fit_keys} < k + 1 = {k + 1}")
    if not holdout_keys:
        refusals.add(CalibrationRefusal.NO_HOLDOUT_FAMILY, "no HOLDOUT family")
    if overlap:
        refusals.add(CalibrationRefusal.HOLDOUT_FAMILY_OVERLAPS_FIT, f"HOLDOUT families shared with FIT: {overlap}")
    full_rank = inputs.analysis is not None and inputs.analysis.full_rank
    if inputs.analysis is None:
        refusals.add(CalibrationRefusal.MISSING_EVIDENCE, "practical-rank analysis not available")
    elif not full_rank:
        refusals.add(CalibrationRefusal.RANK_DEFICIENT, "; ".join(inputs.analysis.refusal_reasons) or "rank-deficient")
    loo = _loo_status(inputs.robustness, fit_keys)
    if loo["status"] != "AVAILABLE_COMPLETE_LOO":
        refusals.add(CalibrationRefusal.LOO_INCOMPLETE, "; ".join(loo["reasons"]))
    return {"k": k, "required_fit_families": k + 1, "fit_family_keys": fit_keys, "holdout_family_keys": holdout_keys,
            "holdout_fit_overlap": overlap, "full_rank": full_rank, "rcond": RCOND, "leave_one_fit_family_out": loo}


def _loo_status(robustness: Optional[ModelFormRobustnessResult], fit_keys: Sequence[str]) -> dict:
    if robustness is None:
        return {"status": "NOT_AVAILABLE", "reasons": ["model_form_robustness not available"], "cases": []}
    cases = [{"family": c.family, "status": c.status.value} for c in robustness.cases]
    reasons = []
    refused = [c.family for c in robustness.cases if c.status is not CaseStatus.VALID]
    if refused:
        reasons.append(f"leave-one-FIT-family-out refused for {refused}")
    if sorted(c.family for c in robustness.cases) != sorted(fit_keys):
        reasons.append("leave-one-FIT-family-out cases do not cover exactly the FIT families")
    if not robustness.supports_green:
        reasons.append("model_form_robustness does not support a passing gate")
    status = "AVAILABLE_COMPLETE_LOO" if not reasons else "UNAVAILABLE_INCOMPLETE_LOO"
    return {"status": status, "reasons": reasons, "cases": cases}


def _pairing_tracking(inputs: CalibrationGateInputs, refusals: _Refusals) -> dict:
    pair_minimum = STRICT_IDENTIFICATION_PAIRING.minimum_mac
    tracking_minimum = STRICT_IDENTIFICATION_PAIRING.tracking_minimum_mac
    governed = set(inputs.fit_families) | set(inputs.holdout_families)
    missing_pairs = sorted(set(inputs.fit_families) - set(inputs.baseline_pair_macs))
    missing_tracking = sorted(governed - set(inputs.tracking_macs))
    low_pairs = sorted(k for k, v in inputs.baseline_pair_macs.items() if not v >= pair_minimum)
    low_tracking = sorted(k for k, v in inputs.tracking_macs.items() if not v >= tracking_minimum)
    if missing_pairs or missing_tracking:
        refusals.add(CalibrationRefusal.MISSING_EVIDENCE,
                     f"pair MAC missing for {missing_pairs}; tracking MAC missing for {missing_tracking}")
    if low_pairs:
        refusals.add(CalibrationRefusal.BASELINE_PAIR_MAC, f"strict baseline pair MAC < {pair_minimum}: {low_pairs}")
    if low_tracking:
        refusals.add(CalibrationRefusal.TRACKING_MAC, f"FE-to-FE tracking MAC < {tracking_minimum}: {low_tracking}")
    _guard(inputs.branch_pairing, CalibrationRefusal.BRANCH_OR_PAIRING_LOSS, refusals)
    return {"baseline_pair_minimum_mac": pair_minimum, "tracking_minimum_mac": tracking_minimum,
            "min_baseline_pair_mac": _r(min(inputs.baseline_pair_macs.values(), default=None)),
            "min_tracking_mac": _r(min(inputs.tracking_macs.values(), default=None)),
            "low_baseline_pairs": low_pairs, "low_tracking": low_tracking, "missing_pairs": missing_pairs,
            "missing_tracking": missing_tracking, "branch_pairing": inputs.branch_pairing.state.value}


def _guard(guard: GuardEvidence, code: CalibrationRefusal, refusals: _Refusals) -> None:
    if guard.state is EvidenceState.FAIL:
        refusals.add(code, guard.detail or guard.name)
    elif guard.state is not EvidenceState.PASS:
        refusals.add(CalibrationRefusal.MISSING_EVIDENCE, f"{guard.name} not available")


def _bounds(inputs: CalibrationGateInputs, refusals: _Refusals) -> dict:
    record = {}
    for name in inputs.definition.fitted_parameters:
        low, high = inputs.definition.bounds[name]
        value = float(inputs.p_hat[name])
        active = at_search_bound(value, low, high) or not low < value < high
        record[name] = {"lower": low, "upper": high, "at_or_beyond_bound": active}
        if active:
            refusals.add(CalibrationRefusal.ACTIVE_PARAMETER_BOUND, f"{name} at or beyond a search bound")
    return record


def _pattern(inputs: CalibrationGateInputs, refusals: _Refusals) -> dict:
    pattern, tau = inputs.pattern, inputs.definition.tau_mf
    if pattern is None:
        refusals.add(CalibrationRefusal.MISSING_EVIDENCE, "residual-pattern / holdout evidence not available")
        return {"status": "NOT_AVAILABLE"}
    if pattern.tau_mf is None:
        refusals.add(CalibrationRefusal.PATTERN_EVIDENCE_NOT_V1_2, "the pattern record is a v1.1 (σ-only) record")
    elif pattern.tau_mf != tau:
        refusals.add(CalibrationRefusal.TAU_MF_MISMATCH, f"pattern τ_mf {pattern.tau_mf:g} ≠ declared τ_mf {tau}")
    if pattern.systematic_families:
        refusals.add(CalibrationRefusal.SYSTEMATIC_PATTERN, f"systematic families {list(pattern.systematic_families)}")
    if pattern.holdout_failures:
        refusals.add(CalibrationRefusal.HOLDOUT_FAILURE, f"holdout failures {list(pattern.holdout_failures)}")
    return {"pattern_record_hash": pattern.record_hash, "pattern_tau_mf": pattern.tau_mf,
            "status": pattern.status.value, "systematic_families": list(pattern.systematic_families),
            "holdout_failures": list(pattern.holdout_failures)}


def _non_degradation(inputs: CalibrationGateInputs, refusals: _Refusals) -> dict:
    governed = ({(t, "FIT") for t in inputs.fit_families} | {(t, "HOLDOUT") for t in inputs.holdout_families})
    baseline = {(t.term_id, t.role): float(t.delta_ln_f) for t in inputs.baseline_terms}
    candidate = {(t.term_id, t.role): float(t.delta_ln_f) for t in inputs.candidate_terms}
    duplicated = len(baseline) != len(inputs.baseline_terms) or len(candidate) != len(inputs.candidate_terms)
    same = not duplicated and set(baseline) == set(candidate) == governed
    if not same:
        refusals.add(CalibrationRefusal.TERM_SET_MISMATCH,
                     "baseline and candidate must carry exactly the governed FIT + HOLDOUT terms with their roles "
                     f"(missing {sorted(governed - set(candidate))}, extra {sorted(set(candidate) - governed)}, "
                     f"baseline differs {sorted(set(baseline) ^ governed)}, duplicated {duplicated})")
        return {"same_term_set": False}

    def rms(values):
        return math.sqrt(sum(v * v for v in values) / len(values))

    base_max = max(abs(v) for v in baseline.values())
    cand_max = max(abs(v) for v in candidate.values())
    base_rms, cand_rms = rms(baseline.values()), rms(candidate.values())
    relative = {f"{role}:{term}": math.expm1(v) for (term, role), v in sorted(candidate.items())}
    worst = max(relative, key=lambda k: abs(relative[k]))
    above = sorted(k for k, v in relative.items() if not abs(v) <= ROW_RELATIVE_ERROR_CEILING)
    if not cand_max <= base_max:
        refusals.add(CalibrationRefusal.MAX_DEGRADED,
                     f"candidate max |Δ ln f| {cand_max:.6g} > baseline {base_max:.6g}")
    if not cand_rms <= base_rms:
        refusals.add(CalibrationRefusal.RMS_DEGRADED, f"candidate RMS Δ ln f {cand_rms:.6g} > baseline {base_rms:.6g}")
    if above:
        refusals.add(CalibrationRefusal.ROW_RELATIVE_ERROR_ABOVE_CEILING,
                     f"|relative frequency error| > {ROW_RELATIVE_ERROR_CEILING} for {above}")
    return {"same_term_set": True, "terms": len(candidate),
            "baseline_max_abs_delta_ln_f": _r(base_max), "candidate_max_abs_delta_ln_f": _r(cand_max),
            "baseline_rms_delta_ln_f": _r(base_rms), "candidate_rms_delta_ln_f": _r(cand_rms),
            "candidate_max_abs_relative_error": _r(abs(relative[worst])), "controlling_term": worst,
            "row_relative_error_ceiling": ROW_RELATIVE_ERROR_CEILING, "relative_error": "expm1(Δ ln f)",
            "max_not_worse": cand_max <= base_max, "rms_not_worse": cand_rms <= base_rms,
            "rows_above_ceiling": above}


def _precision(inputs: CalibrationGateInputs, loo_complete: bool, refusals: _Refusals) -> dict:
    birge = inputs.birge
    birge_ok = birge is not None and birge.status is BirgeStatus.AVAILABLE and birge.birge_adjusted_sd_ln is not None
    if not birge_ok:
        refusals.add(CalibrationRefusal.BIRGE_UNAVAILABLE,
                     f"birge_adjusted_sd not available ({'missing' if birge is None else birge.status.value})")
    parameters = {}
    for name in inputs.definition.fitted_parameters:
        sd = birge.birge_adjusted_sd_ln.get(name) if birge_ok else None
        item = inputs.robustness.parameters.get(name) if loo_complete and inputs.robustness is not None else None
        half = None if item is None else 0.5 * (item.max_shift_ln - item.min_shift_ln)
        conservative = None if sd is None or half is None else max(sd, half)
        passed = conservative is not None and conservative <= PRECISION_CEILING_LN
        parameters[name] = {"birge_adjusted_sd_ln": _r(sd), "model_form_half_range_ln": _r(half),
                            "conservative_uncertainty_ln": _r(conservative), "pass": passed}
        if conservative is not None and not passed:
            refusals.add(CalibrationRefusal.CONSERVATIVE_ABOVE_CEILING,
                         f"{name}: conservative_uncertainty {conservative:.6g} > {PRECISION_CEILING_LN} (ln p)")
        elif conservative is None and birge_ok:
            refusals.add(CalibrationRefusal.MISSING_EVIDENCE,
                         f"{name}: conservative_uncertainty undefined (complete leave-one-FIT-family-out required)")
    return {"envelope": "max(birge_adjusted_sd_ln, 0.5 * (max_shift_ln - min_shift_ln))", "space": "ln p",
            "ceiling_ln": PRECISION_CEILING_LN, "tau_mf_in_envelope": False, "parameters": parameters}


def _uncertainty_basis(inputs: CalibrationGateInputs) -> dict:
    sigma = inputs.definition.sigma
    provisional = sigma.setup_provisional or (inputs.statistical is not None and any(
        bool(c.get("provisional")) for c in inputs.statistical.sigma_components))
    conditional = not sigma.measurement_available or provisional
    return {"basis": CONDITIONAL_COVARIANCE if conditional else COMPLETE_COVARIANCE,
            "conditional_on_available_covariance": conditional,
            "covariance_components": {"sigma_setup": sigma.setup_status, "sigma_meas": sigma.measurement_status},
            "note": ("the precision gate is conditional on the available covariance components; it is not a complete "
                     "experimental uncertainty; Σ_meas is never invented and no uncertainty is enlarged or shrunk")
                    if conditional else "all covariance components measured"}


def _reporting(reporting: Optional[ReportingCompleteness], refusals: _Refusals) -> Optional[dict]:
    if reporting is None:
        refusals.add(CalibrationRefusal.REPORTING_INCOMPLETE, "reporting-completeness evidence not available")
        return None
    missing = [k for k, v in reporting.to_dict().items() if v is not True]
    if missing:
        refusals.add(CalibrationRefusal.REPORTING_INCOMPLETE, f"missing reporting evidence {missing}")
    return dict(reporting.to_dict(), complete=not missing)


def evaluate_calibration_gate(inputs: CalibrationGateInputs) -> CalibrationGateResult:
    """V12-I3: the pure SPEC v1.2 specimen-calibration gate. Deterministic; no override; emits no value."""

    if not isinstance(inputs, CalibrationGateInputs):
        raise TypeError("the calibration gate consumes a CalibrationGateInputs evidence record.")
    definition = inputs.definition
    refusals = _Refusals()
    parameter_ids = tuple(definition.fitted_parameters)
    specimen = ({"label": definition.specimens[0].label, "fixture_id": definition.specimens[0].fixture_id}
                if len(definition.specimens) == 1 else None)

    def refused_early() -> CalibrationGateResult:
        return CalibrationGateResult(CalibrationGateStatus.REFUSED, definition.scientific_question, definition.tau_mf,
                                     definition.campaign_hash, specimen, parameter_ids, None, None, None, None, None,
                                     None, None, None, None, tuple(refusals.items))

    # 1. Question and identity: nothing else is evaluated for another question (no fallback, §1).
    if definition.schema != CAMPAIGN_SCHEMA_V1_2 or definition.scientific_question != SPECIMEN_ENGINEERING_CALIBRATION:
        refusals.add(CalibrationRefusal.WRONG_SCHEMA_OR_QUESTION,
                     f"schema {definition.schema}, question {definition.scientific_question}: the calibration gate "
                     f"applies only to {CAMPAIGN_SCHEMA_V1_2} {SPECIMEN_ENGINEERING_CALIBRATION}")
        return refused_early()
    if definition.tau_mf is None:
        refusals.add(CalibrationRefusal.TAU_MF_NOT_DECLARED, "τ_mf is not declared in the campaign identity")
        return refused_early()
    if len(definition.specimens) != 1:
        refusals.add(CalibrationRefusal.SPECIMEN_COUNT,
                     f"{len(definition.specimens)} specimens: a calibration has exactly one physical specimen")
        return refused_early()
    _bind(inputs)

    observability = _observability(inputs, len(parameter_ids), refusals)
    pairing = _pairing_tracking(inputs, refusals)
    bounds = _bounds(inputs, refusals)
    _guard(inputs.registration, CalibrationRefusal.REGISTRATION_LIMITED, refusals)
    _guard(inputs.peak_derived_input, CalibrationRefusal.PEAK_DERIVED_INPUT, refusals)
    registration_peak = {"registration": inputs.registration.state.value,
                         "peak_derived_input": inputs.peak_derived_input.state.value}
    pattern = _pattern(inputs, refusals)
    non_degradation = _non_degradation(inputs, refusals)
    loo_complete = observability["leave_one_fit_family_out"]["status"] == "AVAILABLE_COMPLETE_LOO"
    precision = _precision(inputs, loo_complete, refusals)
    basis = _uncertainty_basis(inputs)
    reporting = _reporting(inputs.reporting, refusals)
    status = CalibrationGateStatus.REFUSED if refusals.items else CalibrationGateStatus.PASS
    return CalibrationGateResult(status, definition.scientific_question, definition.tau_mf, definition.campaign_hash,
                                 specimen, parameter_ids, observability, pairing, bounds, registration_peak, pattern,
                                 non_degradation, precision, basis, reporting, tuple(refusals.items))
