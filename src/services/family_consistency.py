"""Family (campaign) consistency test — SPEC §13 (D-076; audit iteration 2, finding K2).

Pure and deterministic.  No Abaqus and no new FE evaluation: it works on the linearised model at the shared
optimum, from the whitened FIT residuals ``r`` and the whitened Jacobian ``J`` (d r / d ln p) that the campaign
journal already holds (the same reconstructed Jacobian M5 uses).

    χ²_shared      = min_δ ‖r + J δ‖²                      (one shared parameter vector)
    χ²_separate,s  = min_δs ‖r_s + J_s δ_s‖²                 (each specimen its own vector)
    Δχ²  = χ²_shared − Σ_s χ²_separate,s
    Δdof = k · (N − 1)

The shared set is rejected at p < 0.01 (SPEC §13).  The χ²(Δdof) path is used only when every SPEC §13
condition holds; otherwise the parametric bootstrap on the linearised model is the decisive path.  Both are
always reported.  A separate model that cannot identify every parameter of a specimen is refused
(``NOT_EVALUABLE_RANK_DEFICIENT``) — no p-value is produced for it.

Rows are put in a canonical order (specimen, term id) before anything is computed, so the result, including
the bootstrap draw, does not depend on the input row order.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Mapping, Optional, Sequence

import numpy as np
from scipy import stats

from .practical_identifiability import RCOND


SCHEMA = "auto-id/family-consistency/v1"
SPEC_ALPHA = 0.01  # SPEC §13: the shared set is rejected at p < 0.01 (not configurable)
MINIMUM_BOOTSTRAP_SAMPLES = 2000  # SPEC §13
CHI2_CONDITIONS = ("sigma_fixed", "interior_optimum", "observation_model_comparable",
                   "practical_identifiability_adequate", "no_influential_priors_or_bounds")


class FamilyConsistencyStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_EVALUABLE_RANK_DEFICIENT = "NOT_EVALUABLE_RANK_DEFICIENT"
    NOT_EVALUABLE = "NOT_EVALUABLE"


class FamilyConsistencyInputError(ValueError):
    """The inputs do not describe one linearised campaign system."""


@dataclass(frozen=True)
class FamilyConsistencyResult:
    status: FamilyConsistencyStatus
    path: Optional[str]  # "CHI2" or "BOOTSTRAP": the decisive path; None when not evaluable
    alpha: float
    delta_chi2: Optional[float]
    delta_dof: Optional[int]
    p_chi2: Optional[float]
    log10_p_chi2: Optional[float]
    bootstrap_p: Optional[float]
    bootstrap_samples: int
    bootstrap_seed: int
    shared_model: Mapping
    separate_model: Mapping
    chi2_conditions: Mapping[str, bool]
    sigma: Mapping
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return {"schema": SCHEMA, "status": self.status.value, "path": self.path, "alpha": self.alpha,
                "delta_chi2": self.delta_chi2, "delta_dof": self.delta_dof, "p_chi2": self.p_chi2,
                "log10_p_chi2": self.log10_p_chi2, "bootstrap_p": self.bootstrap_p,
                "bootstrap_samples": self.bootstrap_samples, "bootstrap_seed": self.bootstrap_seed,
                "shared_model": dict(self.shared_model), "separate_model": dict(self.separate_model),
                "chi2_conditions": dict(self.chi2_conditions), "sigma": dict(self.sigma),
                "reasons": list(self.reasons)}


def _rank(matrix: np.ndarray) -> int:
    if matrix.size == 0:
        return 0
    values = np.linalg.svd(matrix, compute_uv=False)
    return int(np.sum(values > RCOND * values[0])) if values[0] > 0 else 0


def _least_squares(residuals: np.ndarray, design: np.ndarray) -> tuple[float, np.ndarray]:
    shift = np.linalg.lstsq(design, -residuals, rcond=None)[0]
    remainder = residuals + design @ shift
    return float(remainder @ remainder), shift


def _projector_residual(design: np.ndarray) -> np.ndarray:
    """I − A(AᵀA)⁻¹Aᵀ for a full-column-rank A."""
    q, _ = np.linalg.qr(design)
    return np.eye(design.shape[0]) - q @ q.T


def family_consistency(term_ids: Sequence[str], specimen_of: Mapping[str, str], residuals: Sequence[float],
                       jacobian: Sequence[Sequence[float]], parameter_ids: Sequence[str],
                       p_hat: Mapping[str, float], *, chi2_conditions: Mapping[str, bool], sigma: Mapping,
                       bootstrap_samples: int, bootstrap_seed: int) -> FamilyConsistencyResult:
    """SPEC §13 on the linearised campaign system (whitened FIT residuals at the shared optimum)."""

    if bootstrap_samples < MINIMUM_BOOTSTRAP_SAMPLES:
        raise FamilyConsistencyInputError(f"SPEC §13 needs at least {MINIMUM_BOOTSTRAP_SAMPLES} bootstrap samples.")
    if set(chi2_conditions) != set(CHI2_CONDITIONS):
        raise FamilyConsistencyInputError(f"chi2_conditions must state exactly {CHI2_CONDITIONS}.")
    r = np.asarray(residuals, dtype=float)
    j = np.asarray(jacobian, dtype=float).reshape(len(r), -1)
    k = len(parameter_ids)
    if len(term_ids) != len(r) or j.shape != (len(r), k) or len(set(term_ids)) != len(term_ids):
        raise FamilyConsistencyInputError("residuals, Jacobian rows and term ids must match one to one.")
    if not np.all(np.isfinite(r)) or not np.all(np.isfinite(j)):
        raise FamilyConsistencyInputError("residuals and Jacobian must be finite.")
    order = sorted(range(len(r)), key=lambda i: (specimen_of[term_ids[i]], term_ids[i]))  # canonical order
    terms = [term_ids[i] for i in order]
    r, j = r[order], j[order]
    labels = sorted({specimen_of[t] for t in terms})
    rows_of = {s: [i for i, t in enumerate(terms) if specimen_of[t] == s] for s in labels}

    def estimates(shift):
        return {name: float(p_hat[name]) * math.exp(float(shift[i])) for i, name in enumerate(parameter_ids)}

    reasons = []
    shared_rank = _rank(j)
    shared = {"terms": terms, "rank": shared_rank, "parameters": list(parameter_ids)}
    if shared_rank < k:
        reasons.append(f"shared model rank {shared_rank} < {k} parameters")
    else:
        chi2_shared, shared_shift = _least_squares(r, j)
        shared.update(chi2=chi2_shared, chi2_at_p_hat=float(r @ r), estimate=estimates(shared_shift))
    separate = {}
    for s in labels:
        rows = rows_of[s]
        rank = _rank(j[rows])
        entry = {"terms": [terms[i] for i in rows], "rank": rank, "fit_rows": len(rows)}
        if rank < k:
            reasons.append(f"specimen {s}: {len(rows)} FIT row(s), rank {rank} < {k} parameters "
                           f"({', '.join(parameter_ids)}): the separate model is not identifiable")
        else:
            chi2_s, shift = _least_squares(r[rows], j[rows])
            entry.update(chi2=chi2_s, estimate=estimates(shift))
        separate[s] = entry
    separate_model = {"specimens": separate}
    if len(labels) < 2:
        reasons.append("a family test needs at least two specimens")
    rank_deficient = any(item["rank"] < k for item in separate.values()) or shared_rank < k
    if reasons:
        status = (FamilyConsistencyStatus.NOT_EVALUABLE_RANK_DEFICIENT if rank_deficient
                  else FamilyConsistencyStatus.NOT_EVALUABLE)
        return FamilyConsistencyResult(status, None, SPEC_ALPHA, None, None, None, None, None, bootstrap_samples,
                                       bootstrap_seed, shared, separate_model, dict(chi2_conditions), dict(sigma),
                                       tuple(reasons))

    chi2_separate = sum(item["chi2"] for item in separate.values())
    separate_model["chi2_sum"] = chi2_separate
    delta = shared["chi2"] - chi2_separate
    dof = k * (len(labels) - 1)
    statistic = max(delta, 0.0)
    p_chi2 = float(stats.chi2.sf(statistic, dof))
    log10_p = float(stats.chi2.logsf(statistic, dof) / math.log(10.0))

    # Parametric bootstrap under the shared linearised model: whitened noise only (Σ is the whitening).
    rng = np.random.default_rng(bootstrap_seed)
    noise = rng.standard_normal((bootstrap_samples, len(r)))
    shared_projector = _projector_residual(j)
    draws = np.einsum("bi,ij,bj->b", noise, shared_projector, noise)
    for s in labels:
        rows = rows_of[s]
        projector = _projector_residual(j[rows])
        block = noise[:, rows]
        draws -= np.einsum("bi,ij,bj->b", block, projector, block)
    exceed = int(np.sum(draws >= delta))
    bootstrap_p = (1 + exceed) / (bootstrap_samples + 1)

    chi2_valid = all(chi2_conditions.values())
    path = "CHI2" if chi2_valid else "BOOTSTRAP"
    decisive = p_chi2 if chi2_valid else bootstrap_p
    status = FamilyConsistencyStatus.FAIL if decisive < SPEC_ALPHA else FamilyConsistencyStatus.PASS
    if not chi2_valid:
        reasons.append("χ²(Δdof) approximation not valid: " +
                       ", ".join(name for name, ok in chi2_conditions.items() if not ok) + "; bootstrap is decisive")
    if status is FamilyConsistencyStatus.FAIL:
        reasons.append("one carbon material vector does not explain the family (SPEC §13): no global material value; "
                       "each specimen is shown separately")
    return FamilyConsistencyResult(status, path, SPEC_ALPHA, float(delta), dof, p_chi2, log10_p, bootstrap_p,
                                   bootstrap_samples, bootstrap_seed, shared, separate_model, dict(chi2_conditions),
                                   dict(sigma), tuple(reasons))
