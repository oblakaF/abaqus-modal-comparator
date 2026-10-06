"""Linearised leave-one-family-out `model_form_robustness` — Auto-ID M5.7 (SPEC §9, §14; D-042, D-043).

At p̂ the full M5 system is linear in δ = x − x̂ (ln p):

    r(x̂ + δ) ≈ r̂ + A δ,   A = [Σ^(−1/2)·S ; C_prior^(−1/2)·E_nuis],   r̂ = [r_fit ; (x̂_nuis − x_0)/sd]

For each fitted modal family F (the M4.3 family identity of M5.8; a confirmed cluster is one term
under its shared or composite key):
1. remove every fit term of F (its observations: the raw residuals e = L·r are re-whitened with
   the reduced Σ);
2. keep all other fit terms and every nuisance-prior row unchanged;
3. apply the same practical-rank rule (rcond = 1e-3) through the M5.3 analysis. A rank-deficient
   reduced system is REFUSED, with no estimate and no pseudo-inverse;
4. otherwise δ_F = −(A_Fᵀ A_F)⁻¹ A_Fᵀ r̂_F, so the estimate is x̂ + δ_F.

`model_form_robustness` is the range of the valid leave-one-family-out estimates per parameter,
in % of p̂. It is **not** `statistical_sd`, not `birge_adjusted_sd`, not part of Σ, and never 1σ.
Holdouts are never part of the fit. Any refused case means the result cannot support a green
verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Mapping, Optional, Sequence

import numpy as np

from domain.identification_run import canonical_hash

from .identification_uncertainty import ResidualTerm
from .practical_identifiability import (
    RCOND,
    CovarianceComponent,
    ObservationCovariance,
    PracticalIdentifiabilityInputError,
    PracticalSystem,
    SensitivityMatrix,
    analyse_practical_identifiability,
    assemble_system,
)


SCHEMA = "auto-id/model-form-robustness/v1"
QUANTITY = "model_form_robustness"
_DIGITS = 12


def _r(value: float) -> float:
    return float(f"{float(value):.{_DIGITS}g}")


class CaseStatus(str, Enum):
    VALID = "VALID"
    REFUSED_RANK_DEFICIENT = "REFUSED_RANK_DEFICIENT"
    REFUSED_NO_FIT_TERMS = "REFUSED_NO_FIT_TERMS"


@dataclass(frozen=True)
class LeaveOneFamilyOutCase:
    family: str
    removed_term_ids: tuple[str, ...]
    status: CaseStatus
    shift_ln: Optional[Mapping[str, float]]  # δ_F (ln p), only when VALID
    estimate: Optional[Mapping[str, float]]  # p̂·exp(δ_F), only when VALID
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ParameterRobustness:
    parameter_id: str
    p_hat: float
    min_estimate: float
    max_estimate: float
    range: float  # max − min (physical units of the parameter)
    half_range: float
    range_percent_of_p_hat: float
    half_range_percent_of_p_hat: float
    min_shift_ln: float
    max_shift_ln: float


@dataclass(frozen=True)
class ModelFormRobustnessResult:
    quantity: str  # always "model_form_robustness"
    system_hash: str
    family_mapping_hash: str
    p_hat: Mapping[str, float]
    p_hat_hash: str
    sigma_hash: str
    prior_hash: str
    rcond: float
    cases: tuple[LeaveOneFamilyOutCase, ...]
    parameters: Mapping[str, ParameterRobustness]  # over VALID cases only; empty if none is valid
    refused_families: tuple[str, ...]
    supports_green: bool  # False when any case is refused or no case is valid (D-042)
    reasons: tuple[str, ...]
    note: str = ("range of linearised leave-one-family-out estimates at p̂ (SPEC §9/§14, D-042); not statistical_sd, "
                 "not birge_adjusted_sd, not part of Σ, not 1 sigma")

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA, "quantity": self.quantity, "note": self.note, "system_hash": self.system_hash,
            "family_mapping_hash": self.family_mapping_hash, "p_hat": {k: _r(v) for k, v in sorted(self.p_hat.items())},
            "p_hat_hash": self.p_hat_hash, "sigma_hash": self.sigma_hash, "prior_hash": self.prior_hash,
            "rcond": self.rcond,
            "cases": [{"family": c.family, "removed_term_ids": list(c.removed_term_ids), "status": c.status.value,
                       "shift_ln": None if c.shift_ln is None else {k: _r(v) for k, v in sorted(c.shift_ln.items())},
                       "estimate": None if c.estimate is None else {k: _r(v) for k, v in sorted(c.estimate.items())},
                       "reasons": list(c.reasons)} for c in self.cases],
            "parameters": {k: {f: (_r(getattr(v, f)) if isinstance(getattr(v, f), float) else getattr(v, f))
                               for f in ParameterRobustness.__dataclass_fields__}
                           for k, v in sorted(self.parameters.items())},
            "refused_families": list(self.refused_families), "supports_green": self.supports_green,
            "reasons": list(self.reasons),
        }

    @property
    def record_hash(self) -> str:
        return canonical_hash(self.to_dict())


def _reduced_system(system: PracticalSystem, keep: Sequence[int]) -> PracticalSystem:
    matrix = system.matrix
    reduced = SensitivityMatrix(tuple(matrix.terms[i] for i in keep), matrix.parameters,
                                tuple(matrix.values[i] for i in keep), dict(matrix.column_provenance))
    components = tuple(CovarianceComponent(c.name, tuple(tuple(c.matrix[i][j] for j in keep) for i in keep),
                                           c.provisional, c.provenance) for c in system.covariance.components)
    return assemble_system(reduced, ObservationCovariance(reduced.term_ids, components), system.priors)


def linearised_model_form_robustness(system: PracticalSystem, fit_terms: Sequence[ResidualTerm],
                                     p_hat: Mapping[str, float]) -> ModelFormRobustnessResult:
    """M5.7 (D-042): linearised leave-one-family-out at p̂ over the M5.8 fit families."""

    if not isinstance(system, PracticalSystem):
        raise TypeError("model_form_robustness is computed from the full M5 PracticalSystem at p̂.")
    term_ids = system.matrix.term_ids
    if tuple(t.term_id for t in fit_terms) != term_ids:
        raise PracticalIdentifiabilityInputError("fit terms must be exactly the system's fit terms, in order "
                                                 "(holdouts are never part of the fit).")
    parameter_ids = system.matrix.parameter_ids
    if set(p_hat) != set(parameter_ids):
        raise PracticalIdentifiabilityInputError("p̂ must give every system parameter.")
    for name, value in p_hat.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise PracticalIdentifiabilityInputError(f"p̂[{name}] must be finite and positive.")
    analysis = analyse_practical_identifiability(system)
    if not analysis.full_rank:
        raise PracticalIdentifiabilityInputError("the full system is rank-deficient; M5.7 needs an accepted full system.")

    x_hat = {k: math.log(float(v)) for k, v in p_hat.items()}
    lower = np.linalg.cholesky(system.covariance.matrix())
    raw = lower @ np.array([t.value for t in fit_terms], dtype=float)  # e = L·r (unwhitened fit residuals)
    prior_residuals = np.array([(x_hat[p.parameter_id] - p.center_ln) / p.sd_ln for p in system.priors], dtype=float)

    families: dict[str, list[int]] = {}
    for index, term in enumerate(fit_terms):
        families.setdefault(term.family, []).append(index)
    cases = []
    for family in sorted(families):
        removed = families[family]
        keep = [i for i in range(len(fit_terms)) if i not in removed]
        removed_ids = tuple(term_ids[i] for i in removed)
        if not keep:
            cases.append(LeaveOneFamilyOutCase(family, removed_ids, CaseStatus.REFUSED_NO_FIT_TERMS, None, None,
                                               ("no fit terms remain without this family",)))
            continue
        reduced = _reduced_system(system, keep)
        reduced_analysis = analyse_practical_identifiability(reduced)
        if not reduced_analysis.full_rank:
            cases.append(LeaveOneFamilyOutCase(family, removed_ids, CaseStatus.REFUSED_RANK_DEFICIENT, None, None,
                                               reduced_analysis.refusal_reasons))
            continue
        reduced_lower = np.linalg.cholesky(reduced.covariance.matrix())
        residual = np.concatenate([np.linalg.solve(reduced_lower, raw[keep]), prior_residuals])
        design = reduced.design()
        covariance = np.array(reduced_analysis.covariance_ln, dtype=float)  # (A_FᵀA_F)⁻¹ of a full-rank A_F
        shift = -covariance @ (design.T @ residual)
        shift_map = {p: float(v) for p, v in zip(parameter_ids, shift)}
        estimate = {p: float(p_hat[p]) * math.exp(shift_map[p]) for p in parameter_ids}
        cases.append(LeaveOneFamilyOutCase(family, removed_ids, CaseStatus.VALID, shift_map, estimate, ()))

    valid = [c for c in cases if c.status is CaseStatus.VALID]
    refused = tuple(c.family for c in cases if c.status is not CaseStatus.VALID)
    parameters = {}
    for p in parameter_ids if valid else ():
        estimates = [c.estimate[p] for c in valid]
        shifts = [c.shift_ln[p] for c in valid]
        low, high, centre = min(estimates), max(estimates), float(p_hat[p])
        parameters[p] = ParameterRobustness(p, centre, low, high, high - low, 0.5 * (high - low),
                                            100.0 * (high - low) / centre, 50.0 * (high - low) / centre,
                                            min(shifts), max(shifts))
    reasons = []
    if refused:
        reasons.append(f"leave-one-family-out refused for {list(refused)}: model_form_robustness cannot support a "
                       "green verdict")
    if not valid:
        reasons.append("no valid leave-one-family-out case")
    mapping = {t.term_id: t.family for t in fit_terms}
    return ModelFormRobustnessResult(
        QUANTITY, system.system_hash, canonical_hash(mapping), {k: float(v) for k, v in p_hat.items()},
        canonical_hash({k: float(v) for k, v in sorted(p_hat.items())}), canonical_hash(system.covariance.to_dict()),
        canonical_hash([p.to_dict() for p in system.priors]), RCOND, tuple(cases), parameters, refused,
        not refused and bool(valid), tuple(reasons))
