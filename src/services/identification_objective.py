"""Log-frequency identification objective — Auto-ID M4.7 (SPEC §7, §8, §12.3–12.4).

    r_i = (ln f_FE,i − ln f_EXP,i) / σ_i      for frozen fit rows
    r_C = [(1/n_C)·Σ ln(f_FE / f_EXP)] / σ_C   for each confirmed cluster (one term)
    Φ   = ½ ‖r‖²

- FE frequencies come only from FE-to-FE branch tracking of the frozen rows.
- MAC is not an input: it never enters Φ (MAC is used for identity only).
- Holdout rows are evaluated and reported, never part of Φ.
- σ is explicit per row: σ_i² = σ_meas,i² + σ_setup² (SPEC §7).  The SPEC's provisional
  σ_setup (0.3 %) is available as a named constant, must be passed explicitly, and is
  flagged in every evaluation that uses it.  Missing σ is refused, never defaulted.

Notation (SPEC §8): r is the residual vector, Φ the objective; the Jacobian of r lives
in the step module and never shares a symbol with Φ.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Sequence

import numpy as np

from domain.frozen_observations import FrozenObservationSet

from .branch_tracker import TrackingResult
from .identification_clusters import ClusterConfirmation, ClusterStatus, cluster_log_residual


PROVISIONAL_SETUP_SD = 0.003  # SPEC §7: Σ_setup provisional 0.3 % (relative) until measured; flagged


class ObjectiveInputError(ValueError):
    """Objective inputs are missing, inconsistent or non-physical."""


@dataclass(frozen=True)
class RowSigma:
    """σ of one row in ln-frequency units (relative): measurement and setup parts."""

    measurement_sd: float
    setup_sd: float
    setup_provisional: bool

    def __post_init__(self) -> None:
        for name in ("measurement_sd", "setup_sd"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ObjectiveInputError(f"{name} must be finite and non-negative.")
        if self.sigma <= 0.0:
            raise ObjectiveInputError("σ must be positive.")

    @property
    def sigma(self) -> float:
        return math.hypot(self.measurement_sd, self.setup_sd)


@dataclass(frozen=True)
class ObjectiveDesign:
    fit_rows: tuple[str, ...]
    fit_clusters: tuple[tuple[str, str], ...]
    holdout_rows: tuple[str, ...]
    holdout_clusters: tuple[tuple[str, str], ...]
    sigmas: Mapping[str, RowSigma]
    observation_hash: str

    @property
    def fit_term_count(self) -> int:
        return len(self.fit_rows) + len(self.fit_clusters)

    @property
    def provisional_uncertainty(self) -> bool:
        return any(sigma.setup_provisional for sigma in self.sigmas.values())


@dataclass(frozen=True)
class ObjectiveTerm:
    term_id: str
    row_ids: tuple[str, ...]
    log_ratio: float  # ln(f_FE / f_EXP), or the cluster mean
    sigma: float
    residual: float  # log_ratio / sigma
    holdout: bool


@dataclass(frozen=True)
class ObjectiveEvaluation:
    candidate_state: str
    fit_terms: tuple[ObjectiveTerm, ...]
    holdout_terms: tuple[ObjectiveTerm, ...]
    objective: float  # Φ = ½ Σ r² over fit terms only
    provisional_uncertainty: bool

    @property
    def residuals(self) -> np.ndarray:
        return np.array([term.residual for term in self.fit_terms], dtype=float)


def build_objective_design(frozen: FrozenObservationSet, holdout_rows: Sequence[str],
                           clusters: Sequence[ClusterConfirmation], sigmas: Mapping[str, RowSigma],
                           parameter_count: int) -> ObjectiveDesign:
    """Fit and holdout terms of a frozen observation set; refuses an under-determined design."""

    frozen.require_frozen()
    row_ids = [row.row_id for row in frozen.rows]
    holdout = set(holdout_rows)
    if not holdout <= set(row_ids):
        raise ObjectiveInputError(f"unknown holdout rows {sorted(holdout - set(row_ids))}.")
    missing = sorted(set(row_ids) - set(sigmas))
    if missing:
        raise ObjectiveInputError(f"σ missing for rows {missing}; σ is never defaulted.")
    fit_clusters, holdout_clusters, clustered = [], [], set()
    for confirmation in clusters:
        if confirmation.status is not ClusterStatus.CONFIRMED:
            raise ObjectiveInputError(f"cluster {confirmation.row_ids} is {confirmation.status.value}, not CONFIRMED.")
        members = tuple(confirmation.row_ids)
        if len(members) != 2 or not set(members) <= set(row_ids) or clustered & set(members):
            raise ObjectiveInputError(f"cluster {members} must be two distinct frozen rows in one cluster only.")
        inside = len(set(members) & holdout)
        if inside == 1:
            raise ObjectiveInputError(f"cluster {members} is split between fit and holdout.")
        (holdout_clusters if inside else fit_clusters).append(members)
        clustered.update(members)
    fit_rows = tuple(row for row in row_ids if row not in holdout and row not in clustered)
    holdout_singles = tuple(row for row in row_ids if row in holdout and row not in clustered)
    design = ObjectiveDesign(fit_rows, tuple(fit_clusters), holdout_singles, tuple(holdout_clusters),
                             dict(sigmas), frozen.observation_hash)
    if design.fit_term_count < parameter_count:
        raise ObjectiveInputError(f"{design.fit_term_count} fit terms < {parameter_count} parameters.")
    return design


def _row_term(frozen: FrozenObservationSet, design: ObjectiveDesign, row_id: str, fe_hz: float,
              holdout: bool) -> ObjectiveTerm:
    row = frozen.row(row_id)
    if not math.isfinite(fe_hz) or fe_hz <= 0:
        raise ObjectiveInputError(f"{row_id}: tracked FE frequency must be finite and positive.")
    ratio = math.log(fe_hz) - math.log(row.experimental_hz)
    sigma = design.sigmas[row_id].sigma
    return ObjectiveTerm(row_id, (row_id,), ratio, sigma, ratio / sigma, holdout)


def _cluster_term(frozen: FrozenObservationSet, design: ObjectiveDesign, members: tuple[str, str],
                  fe_hz: Sequence[float], holdout: bool) -> ObjectiveTerm:
    exp = [frozen.row(row).experimental_hz for row in members]
    ratio = cluster_log_residual(list(fe_hz), exp)
    # Mean of n_C independent ln-ratios: σ_C = sqrt(Σ σ_i²) / n_C.
    sigma = math.sqrt(sum(design.sigmas[row].sigma ** 2 for row in members)) / len(members)
    return ObjectiveTerm(f"C({'+'.join(members)})", members, ratio, sigma, ratio / sigma, holdout)


def evaluate_objective(design: ObjectiveDesign, frozen: FrozenObservationSet,
                       tracking: TrackingResult) -> ObjectiveEvaluation:
    """Residuals and Φ for one tracked candidate state."""

    if frozen.observation_hash != design.observation_hash:
        raise ObjectiveInputError("the design was built for another frozen observation set.")
    branches = {branch.row_id: branch.candidate_hz for branch in tracking.branches}
    tracked_clusters = {tuple(cluster.row_ids): cluster.candidate_hz for cluster in tracking.clusters}
    expected_rows = set(design.fit_rows) | set(design.holdout_rows)
    expected_clusters = set(design.fit_clusters) | set(design.holdout_clusters)
    if set(branches) != expected_rows or set(tracked_clusters) != expected_clusters:
        raise ObjectiveInputError("tracking does not cover exactly the frozen rows and clusters of the design.")

    fit = [_row_term(frozen, design, row, branches[row], False) for row in design.fit_rows]
    fit += [_cluster_term(frozen, design, members, tracked_clusters[members], False) for members in design.fit_clusters]
    held = [_row_term(frozen, design, row, branches[row], True) for row in design.holdout_rows]
    held += [_cluster_term(frozen, design, members, tracked_clusters[members], True)
             for members in design.holdout_clusters]
    objective = 0.5 * float(sum(term.residual ** 2 for term in fit))
    return ObjectiveEvaluation(tracking.candidate_state, tuple(fit), tuple(held), objective,
                               design.provisional_uncertainty)
