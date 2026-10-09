"""Statistical uncertainty, residual-pattern test and Birge adjustment — Auto-ID M5.5 / M5.8 / M5.6.

(SPEC §6 S7, §9, §10, §14; D-012, D-039–D-043; M5_DECISION_RECORD.md.)

- **M5.5 `statistical_sd`:** sqrt(C_jj), with C = (AᵀA)⁻¹ of the full M5 system: whitened fit
  sensitivities plus nuisance-prior rows, with an explicit, provenance-bound Σ. Reported in ln p,
  plus a labelled first-order percent equivalent (100·sd_ln). It is built only from a
  ``PracticalSystem``; an M4 ``local_sd`` cannot be passed in. Rank deficiency is a hard refusal
  (M5.3).
- **M5.8 pattern test (D-043):**
  - a fit family (M4.3 family identity) signals SYSTEMATIC_PATTERN only when it has at least two
    fit terms, all of the same sign and each with |r| > 2 (whitened);
  - singleton families never trigger and are never merged;
  - any holdout term with |r| > 3 fails the check;
  - both inequalities are strict;
  - a confirmed cluster is one term.
- **SPEC v1.2 §4 (D-078, V12-I2), only when a campaign declares τ_mf:** each term is judged in
  log-frequency space with its own governed σ_term (Δ ln f = r·σ_term):
  - a family is systematic when it has ≥ 2 fit terms, all of the same sign, and every
    |Δ ln f| > max(2·σ_term, τ_mf), i.e. |r| > max(2, τ_mf/σ_term);
  - a holdout fails when |Δ ln f| > max(3·σ_term, τ_mf), i.e. |r| > max(3, τ_mf/σ_term);
  - equality passes. τ_mf never enters Σ, χ², statistical_sd or Birge; without τ_mf the v1.1 rules and
    records above are unchanged.
- **M5.6 Birge (D-041):**
  - χ² = Σ r² over fit terms only (no prior rows, no holdouts);
  - dof = n_fit_terms − n_fitted_parameters (global and nuisance); dof ≤ 0 is refused;
  - s_B = sqrt(max(1, χ²/dof));
  - `birge_adjusted_sd` = `statistical_sd`·s_B, populated **only** when the pattern test passed.
    Otherwise it is NOT_AVAILABLE with a reason, and `statistical_sd` is kept separately.

The quantities are never merged into one "uncertainty" (D-012). Model discrepancy never enters Σ
(D-003).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Mapping, Optional, Sequence

from domain.campaign_definition import TAU_MF_MAXIMUM
from domain.identification_run import canonical_hash

from .practical_identifiability import (
    PracticalIdentifiabilityInputError,
    PracticalSystem,
    RankDeficiencyRefusal,
    analyse_practical_identifiability,
)


SCHEMA = "auto-id/identification-uncertainty/v1"
FAMILY_PATTERN_SIGMA = 2.0  # SPEC §6 S7 (strict: |r| > 2)
HOLDOUT_SIGMA = 3.0  # SPEC §6 S7 (strict: |r| > 3)
MINIMUM_PATTERN_FAMILY_SIZE = 2  # D-043: a singleton family cannot establish a family-wide pattern
PATTERN_SCHEMA_V1_2 = "auto-id/identification-uncertainty/v1.2-residual-pattern"  # τ_mf-aware record (V12-I2)
_DIGITS = 12


def _r(value: float) -> float:
    return float(f"{float(value):.{_DIGITS}g}")


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise PracticalIdentifiabilityInputError(f"{name} must be a finite number.")
    return float(value)


# ----------------------------------------------------------------------------- M5.5 statistical_sd

class StatisticalStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    REFUSED_RANK_DEFICIENT = "REFUSED_RANK_DEFICIENT"


@dataclass(frozen=True)
class StatisticalSDResult:
    """`statistical_sd` of the full M5 system at p̂ (SPEC §9/§10). Never an M4 stop-rule sd."""

    context: str  # what the system describes, for example a synthetic records-based control
    system_hash: str
    analysis_hash: str
    status: StatisticalStatus
    parameter_ids: tuple[str, ...]
    statistical_sd_ln: Optional[Mapping[str, float]]
    statistical_sd_percent_first_order: Optional[Mapping[str, float]]  # 100·sd_ln (label, not a conversion)
    sigma_components: tuple[Mapping[str, object], ...]  # name, provenance, provisional (Σ binding)
    priors: tuple[Mapping[str, object], ...]
    provisional_inputs: tuple[str, ...]
    refusal_reasons: tuple[str, ...]
    source: str = "full M5 system: C = (AᵀA)⁻¹ of [Σ^(−1/2)·S ; C_prior^(−1/2)·E_nuis] (SPEC §10)"

    def require_available(self) -> "StatisticalSDResult":
        if self.status is not StatisticalStatus.AVAILABLE:
            raise RankDeficiencyRefusal(self.refusal_reasons)
        return self

    def to_dict(self) -> dict:
        def rounded(values):
            return None if values is None else {k: _r(v) for k, v in sorted(values.items())}

        return {"schema": SCHEMA, "quantity": "statistical_sd", "context": self.context, "source": self.source,
                "system_hash": self.system_hash, "analysis_hash": self.analysis_hash, "status": self.status.value,
                "parameter_ids": list(self.parameter_ids), "statistical_sd_ln": rounded(self.statistical_sd_ln),
                "statistical_sd_percent_first_order": rounded(self.statistical_sd_percent_first_order),
                "sigma_components": [dict(c) for c in self.sigma_components], "priors": [dict(p) for p in self.priors],
                "provisional_inputs": list(self.provisional_inputs), "refusal_reasons": list(self.refusal_reasons)}

    @property
    def record_hash(self) -> str:
        return canonical_hash(self.to_dict())


def statistical_sd(system: PracticalSystem, context: str) -> StatisticalSDResult:
    """M5.5: `statistical_sd` from the full M5 system (explicit Σ, nuisance prior rows)."""
    if not isinstance(system, PracticalSystem):
        raise TypeError("statistical_sd is computed only from a full M5 PracticalSystem (never from an M4 local_sd).")
    if not isinstance(context, str) or not context.strip():
        raise PracticalIdentifiabilityInputError("context must describe the system (for example a synthetic control).")
    analysis = analyse_practical_identifiability(system)
    sigma = tuple({"name": c.name, "provenance": c.provenance, "provisional": c.provisional}
                  for c in system.covariance.components)
    priors = tuple({"parameter_id": p.parameter_id, "provenance": p.provenance, "provisional": p.provisional,
                    "sd_ln": p.sd_ln, "center_ln": p.center_ln} for p in system.priors)
    if not analysis.full_rank:
        return StatisticalSDResult(context, system.system_hash, analysis.record_hash,
                                   StatisticalStatus.REFUSED_RANK_DEFICIENT, analysis.parameter_ids, None, None, sigma,
                                   priors, analysis.provisional_inputs, analysis.refusal_reasons)
    sd = dict(analysis.sd_ln)
    return StatisticalSDResult(context, system.system_hash, analysis.record_hash, StatisticalStatus.AVAILABLE,
                               analysis.parameter_ids, sd, {k: 100.0 * v for k, v in sd.items()}, sigma, priors,
                               analysis.provisional_inputs, ())


# ----------------------------------------------------------------------------- M5.8 residual-pattern test

@dataclass(frozen=True)
class ResidualTerm:
    """One whitened residual term with its modal family; a confirmed cluster is one term.

    ``sigma`` is the term's governed σ in ln-frequency units, exactly as the objective whitened it
    (σ_C for a cluster), so Δ ln f = value·sigma. It is needed only for the SPEC v1.2 τ_mf rules and
    is never serialised in a v1.1 record.
    """

    term_id: str
    row_ids: tuple[str, ...]
    family: str
    value: float
    sigma: Optional[float] = None

    def __post_init__(self) -> None:
        if not isinstance(self.term_id, str) or not self.term_id or not self.row_ids:
            raise PracticalIdentifiabilityInputError("a residual term needs an id and its rows.")
        if not isinstance(self.family, str) or not self.family:
            raise PracticalIdentifiabilityInputError(f"{self.term_id}: family identity required.")
        object.__setattr__(self, "value", _finite(self.value, f"{self.term_id} residual"))
        if self.sigma is not None:
            sigma = _finite(self.sigma, f"{self.term_id} σ")
            if sigma <= 0.0:
                raise PracticalIdentifiabilityInputError(f"{self.term_id}: σ must be positive.")
            object.__setattr__(self, "sigma", sigma)


def residual_terms(fit_rows: Sequence[str], fit_clusters: Sequence[Sequence[str]], residuals: Sequence[float],
                   row_families: Mapping[str, str],
                   term_sigmas: Optional[Mapping[str, float]] = None) -> tuple[ResidualTerm, ...]:
    """Bind an M4.7 residual vector (fit rows first, then confirmed clusters) to M4.3 family identities.

    A cluster term belongs to its members' family when they share one. Otherwise it gets the
    composite key of its members' families: it is never merged into an unrelated family.
    ``term_sigmas`` (term id → the objective's governed σ, σ_C for a cluster) attaches each term's σ.
    """
    residuals = list(residuals)
    if len(residuals) != len(fit_rows) + len(fit_clusters):
        raise PracticalIdentifiabilityInputError("residual count differs from the fit terms.")
    ids = [str(row) for row in fit_rows] + ["C(" + "+".join(str(m) for m in members) + ")" for members in fit_clusters]
    if term_sigmas is not None and set(ids) - set(term_sigmas):
        raise PracticalIdentifiabilityInputError(f"σ missing for terms {sorted(set(ids) - set(term_sigmas))}.")

    def sigma(term_id: str) -> Optional[float]:
        return None if term_sigmas is None else term_sigmas[term_id]

    terms = []
    for row, value in zip(fit_rows, residuals):
        terms.append(ResidualTerm(str(row), (str(row),), row_families[row], value, sigma(str(row))))
    for members, value in zip(fit_clusters, residuals[len(fit_rows):]):
        members = tuple(str(m) for m in members)
        families = sorted({row_families[m] for m in members})
        term_id = "C(" + "+".join(members) + ")"
        terms.append(ResidualTerm(term_id, members, families[0] if len(families) == 1 else "+".join(families), value,
                                  sigma(term_id)))
    return tuple(terms)


class PatternStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True)
class FamilyPatternEvidence:
    family: str
    term_ids: tuple[str, ...]
    values: tuple[float, ...]
    eligible: bool  # at least two fit terms (D-043)
    systematic: bool


@dataclass(frozen=True)
class PatternTestResult:
    status: PatternStatus
    systematic_families: tuple[str, ...]
    holdout_failures: tuple[str, ...]
    families: tuple[FamilyPatternEvidence, ...]
    holdouts: Mapping[str, float]
    reasons: tuple[str, ...]
    tau_mf: Optional[float] = None  # SPEC v1.2 τ_mf; None: the v1.1 rules and record
    terms: tuple[Mapping[str, object], ...] = ()  # v1.2 per-term evidence in ln-frequency units

    @property
    def passed(self) -> bool:
        return self.status is PatternStatus.PASS

    def to_dict(self) -> dict:
        record = {"schema": SCHEMA, "quantity": "residual_pattern_test", "status": self.status.value,
                  "systematic_families": list(self.systematic_families),
                  "holdout_failures": list(self.holdout_failures),
                  "families": [{"family": f.family, "term_ids": list(f.term_ids), "values": [_r(v) for v in f.values],
                                "eligible": f.eligible, "systematic": f.systematic} for f in self.families],
                  "holdouts": {k: _r(v) for k, v in sorted(self.holdouts.items())}, "reasons": list(self.reasons),
                  "rules": {"family_sigma": FAMILY_PATTERN_SIGMA, "holdout_sigma": HOLDOUT_SIGMA,
                            "minimum_family_size": MINIMUM_PATTERN_FAMILY_SIZE, "inequalities": "strict"}}
        if self.tau_mf is None:  # v1.1: the historical record, unchanged
            return record
        record["schema"] = PATTERN_SCHEMA_V1_2
        record["rules"].update({"tau_mf": self.tau_mf, "space": "ln f per governed term",
                                "family": "|Δ ln f| > max(2σ_term, τ_mf)", "holdout": "|Δ ln f| > max(3σ_term, τ_mf)"})
        record["terms"] = [{k: _r(v) if isinstance(v, float) else v for k, v in t.items()} for t in self.terms]
        return record

    @property
    def record_hash(self) -> str:
        return canonical_hash(self.to_dict())


def _tau_limit(term: ResidualTerm, multiple: float, tau_mf: float, role: str) -> dict:
    """SPEC v1.2 §4 for one governed term: |Δ ln f| > max(k·σ_term, τ_mf) ⇔ |r| > max(k, τ_mf/σ_term)."""
    if term.sigma is None:
        raise PracticalIdentifiabilityInputError(f"{term.term_id}: the governed σ of the term is required with τ_mf.")
    limit = max(multiple, tau_mf / term.sigma)  # whitened form of the same rule (equality passes)
    return {"term_id": term.term_id, "role": role, "family": term.family, "r": term.value, "sigma_term": term.sigma,
            "abs_delta_ln_f": abs(term.value) * term.sigma, "sigma_threshold_ln": multiple * term.sigma,
            "tau_mf": tau_mf, "effective_threshold_ln": max(multiple * term.sigma, tau_mf),
            "exceeds": abs(term.value) > limit}


def _tau_detail(evidence: Mapping[str, object], multiple: int) -> str:
    return (f"{evidence['term_id']}: |Δ ln f| = {evidence['abs_delta_ln_f']:.4g} > max({multiple}σ_term, τ_mf) = "
            f"max({evidence['sigma_threshold_ln']:.4g}, {evidence['tau_mf']:g}) = "
            f"{evidence['effective_threshold_ln']:.4g} (σ_term = {evidence['sigma_term']:.4g})")


def _tau_pattern_test(fit_terms: Sequence[ResidualTerm], holdout_terms: Sequence[ResidualTerm],
                      tau_mf: float) -> PatternTestResult:
    if isinstance(tau_mf, bool) or not isinstance(tau_mf, (int, float)) or not math.isfinite(float(tau_mf)) \
            or not 0.0 < float(tau_mf) <= TAU_MF_MAXIMUM:
        raise PracticalIdentifiabilityInputError(f"tau_mf must satisfy 0 < tau_mf <= {TAU_MF_MAXIMUM}.")
    tau_mf = float(tau_mf)
    fit_evidence = {t.term_id: _tau_limit(t, FAMILY_PATTERN_SIGMA, tau_mf, "FIT") for t in fit_terms}
    held_evidence = {t.term_id: _tau_limit(t, HOLDOUT_SIGMA, tau_mf, "HOLDOUT") for t in holdout_terms}
    groups: dict[str, list[ResidualTerm]] = {}
    for term in fit_terms:
        groups.setdefault(term.family, []).append(term)
    evidence, systematic = [], []
    for family in sorted(groups):
        members = groups[family]
        values = tuple(t.value for t in members)
        eligible = len(members) >= MINIMUM_PATTERN_FAMILY_SIZE
        same_sign = all(v > 0 for v in values) or all(v < 0 for v in values)
        flagged = eligible and same_sign and all(fit_evidence[t.term_id]["exceeds"] for t in members)
        evidence.append(FamilyPatternEvidence(family, tuple(t.term_id for t in members), values, eligible, flagged))
        if flagged:
            systematic.append(family)
    holdouts = {t.term_id: t.value for t in holdout_terms}
    failures = sorted(k for k in holdouts if held_evidence[k]["exceeds"])
    reasons = [f"systematic pattern - probable model-form error: family {f}, all fit residuals same sign and every "
               f"|Δ ln f| > max(2σ_term, τ_mf) (" + "; ".join(_tau_detail(fit_evidence[t.term_id], 2)
                                                         for t in groups[f]) + ")" for f in systematic]
    reasons += [f"holdout {_tau_detail(held_evidence[k], 3)}" for k in failures]
    status = PatternStatus.FAIL if systematic or failures else PatternStatus.PASS
    return PatternTestResult(status, tuple(systematic), tuple(failures), tuple(evidence), holdouts, tuple(reasons),
                             tau_mf, tuple(fit_evidence.values()) + tuple(held_evidence.values()))


def residual_pattern_test(fit_terms: Sequence[ResidualTerm], holdout_terms: Sequence[ResidualTerm],
                          tau_mf: Optional[float] = None) -> PatternTestResult:
    """SPEC §6 S7 with D-043: family systematic pattern (≥ 2 terms) and holdout > 3σ.

    With a declared τ_mf (SPEC v1.2 §4) each term is judged by max(kσ_term, τ_mf) in ln f instead.
    """
    ids = [t.term_id for t in fit_terms] + [t.term_id for t in holdout_terms]
    if len(set(ids)) != len(ids):
        raise PracticalIdentifiabilityInputError("term ids must be unique across fit and holdout terms.")
    if tau_mf is not None:
        return _tau_pattern_test(fit_terms, holdout_terms, tau_mf)
    groups: dict[str, list[ResidualTerm]] = {}
    for term in fit_terms:
        groups.setdefault(term.family, []).append(term)
    evidence, systematic = [], []
    for family in sorted(groups):
        members = groups[family]
        values = tuple(t.value for t in members)
        eligible = len(members) >= MINIMUM_PATTERN_FAMILY_SIZE
        same_sign = all(v > 0 for v in values) or all(v < 0 for v in values)
        flagged = eligible and same_sign and all(abs(v) > FAMILY_PATTERN_SIGMA for v in values)
        evidence.append(FamilyPatternEvidence(family, tuple(t.term_id for t in members), values, eligible, flagged))
        if flagged:
            systematic.append(family)
    holdouts = {t.term_id: t.value for t in holdout_terms}
    failures = sorted(k for k, v in holdouts.items() if abs(v) > HOLDOUT_SIGMA)
    reasons = [f"systematic pattern - probable model-form error: family {f}, all fit residuals same sign and "
               f"|r| > {FAMILY_PATTERN_SIGMA:g}" for f in systematic]
    reasons += [f"holdout {k}: |r| = {abs(holdouts[k]):.3g} > {HOLDOUT_SIGMA:g}" for k in failures]
    status = PatternStatus.FAIL if systematic or failures else PatternStatus.PASS
    return PatternTestResult(status, tuple(systematic), tuple(failures), tuple(evidence), holdouts, tuple(reasons))


# ----------------------------------------------------------------------------- M5.6 Birge adjustment

class BirgeStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    BLOCKED_PATTERN = "BLOCKED_PATTERN"  # pattern test failed: not filled (SPEC §9)
    REFUSED_DOF = "REFUSED_DOF"  # dof ≤ 0 (D-041)
    REFUSED_STATISTICAL = "REFUSED_STATISTICAL"  # statistical_sd unavailable (rank-deficient system)


@dataclass(frozen=True)
class BirgeResult:
    status: BirgeStatus
    statistical_record_hash: str
    pattern_record_hash: str
    chi2: float
    n_fit_terms: int
    n_fitted_parameters: int
    dof: int
    chi2_per_dof: Optional[float]
    birge_factor: Optional[float]
    statistical_sd_ln: Optional[Mapping[str, float]]  # kept separately (never merged)
    birge_adjusted_sd_ln: Optional[Mapping[str, float]]  # only when AVAILABLE
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        def rounded(values):
            return None if values is None else {k: _r(v) for k, v in sorted(values.items())}

        return {"schema": SCHEMA, "quantity": "birge_adjusted_sd", "status": self.status.value,
                "statistical_record_hash": self.statistical_record_hash, "pattern_record_hash": self.pattern_record_hash,
                "chi2": _r(self.chi2), "n_fit_terms": self.n_fit_terms, "n_fitted_parameters": self.n_fitted_parameters,
                "dof": self.dof, "chi2_per_dof": None if self.chi2_per_dof is None else _r(self.chi2_per_dof),
                "birge_factor": None if self.birge_factor is None else _r(self.birge_factor),
                "statistical_sd_ln": rounded(self.statistical_sd_ln),
                "birge_adjusted_sd_ln": rounded(self.birge_adjusted_sd_ln), "reasons": list(self.reasons)}

    @property
    def record_hash(self) -> str:
        return canonical_hash(self.to_dict())


def birge_adjustment(system: PracticalSystem, statistical: StatisticalSDResult, pattern: PatternTestResult,
                     fit_terms: Sequence[ResidualTerm]) -> BirgeResult:
    """M5.6 (D-041): conditional Birge scaling; populated only when the pattern test passed."""
    if statistical.system_hash != system.system_hash:
        raise PracticalIdentifiabilityInputError("statistical_sd belongs to another system.")
    if tuple(t.term_id for t in fit_terms) != system.matrix.term_ids:
        raise PracticalIdentifiabilityInputError("fit residual terms must be exactly the system's fit terms, in order.")
    chi2 = float(sum(t.value * t.value for t in fit_terms))  # fit terms only: no prior rows, no holdouts
    n_terms, n_parameters = len(fit_terms), len(system.matrix.parameter_ids)
    dof = n_terms - n_parameters
    base = dict(statistical_record_hash=statistical.record_hash, pattern_record_hash=pattern.record_hash, chi2=chi2,
                n_fit_terms=n_terms, n_fitted_parameters=n_parameters, dof=dof,
                statistical_sd_ln=None if statistical.statistical_sd_ln is None else dict(statistical.statistical_sd_ln))
    if statistical.status is not StatisticalStatus.AVAILABLE:
        return BirgeResult(BirgeStatus.REFUSED_STATISTICAL, chi2_per_dof=None, birge_factor=None,
                           birge_adjusted_sd_ln=None, reasons=("statistical_sd unavailable: " +
                                                               "; ".join(statistical.refusal_reasons),), **base)
    if dof <= 0:
        return BirgeResult(BirgeStatus.REFUSED_DOF, chi2_per_dof=None, birge_factor=None, birge_adjusted_sd_ln=None,
                           reasons=(f"dof = {n_terms} fit terms - {n_parameters} fitted parameters = {dof} <= 0",),
                           **base)
    ratio = chi2 / dof
    factor = math.sqrt(max(1.0, ratio))
    if not pattern.passed:
        return BirgeResult(BirgeStatus.BLOCKED_PATTERN, chi2_per_dof=ratio, birge_factor=factor,
                           birge_adjusted_sd_ln=None,
                           reasons=("residual-pattern test failed: birge_adjusted_sd is NOT_AVAILABLE (SPEC §9)",)
                           + pattern.reasons, **base)
    adjusted = {k: v * factor for k, v in statistical.statistical_sd_ln.items()}
    return BirgeResult(BirgeStatus.AVAILABLE, chi2_per_dof=ratio, birge_factor=factor, birge_adjusted_sd_ln=adjusted,
                       reasons=(), **base)
