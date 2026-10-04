"""Bounded Levenberg–Marquardt / trust step — Auto-ID M4.8 (SPEC §6 S4, §8).

    x      = ln p                                   (log parameters, physical bounds)
    Δx     = −(J_rᵀ J_r + μ·D)⁻¹ · J_rᵀ r          D = diag(J_rᵀ J_r)
    x_new  = x + Δx, projected onto the bounds
    accept if Φ(x_new) < Φ(x) (one verification solve); otherwise μ ← 10μ
    stop:  max|Δx_j| < 0.2·sd_j, or 5 iterations, or branch/pair loss

J_r comes from central finite differences in ln p (±5 %, 2·n_p solves, SPEC §6 S4),
then Broyden updates; finite differences are repeated only after a step failure.  The
residual function is supplied by the caller (one call = one solve); a branch-identity
refusal it raises stops the loop as REFUSED — there is no re-pairing.  sd_j for the
stop rule is the local sqrt(diag((J_rᵀJ_r)⁻¹)) of the whitened residuals; the
production uncertainty quantities are M5's.

No Abaqus here: this module only computes steps and runs the loop over a callback.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Callable, Mapping, Optional, Sequence

import numpy as np

from domain.frozen_observations import ObservationFreezeRefusal

from .branch_tracker import BranchTrackingRefusal


ResidualFunction = Callable[[Mapping[str, float]], np.ndarray]  # physical parameters → whitened residuals r


class StepError(ValueError):
    """A step cannot be computed (for example, a parameter without sensitivity)."""


class LMStatus(str, Enum):
    CONVERGED = "CONVERGED"  # max|Δx_j| < stop_fraction·sd_j
    MAX_ITERATIONS = "MAX_ITERATIONS"
    REFUSED = "REFUSED"  # branch/pair identity lost: scientific refusal, no re-pairing
    STEP_REJECTED = "STEP_REJECTED"  # no decrease of Φ within the allowed step attempts
    SOLVE_BUDGET = "SOLVE_BUDGET"  # the authorised number of solves is used up


@dataclass(frozen=True)
class LMSettings:
    mu_initial: float  # no SPEC value: explicit
    mu_decrease: float  # μ ← μ / mu_decrease after an accepted step (1 keeps μ); no SPEC value: explicit
    max_step_attempts: int  # rejected trial steps per iteration before STEP_REJECTED
    solve_budget: int  # authorised solves, finite differences included
    max_iterations: int = 5  # SPEC §8
    stop_fraction: float = 0.2  # SPEC §8: max|Δx_j| < 0.2·sd_j
    mu_increase: float = 10.0  # SPEC §8
    finite_difference_step: float = 0.05  # SPEC §6 S4: ±5 % in p

    def __post_init__(self) -> None:
        positive = {"mu_initial": self.mu_initial, "stop_fraction": self.stop_fraction,
                    "finite_difference_step": self.finite_difference_step}
        for name, value in positive.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise StepError(f"{name} must be finite and positive.")
        if not 0.0 < self.finite_difference_step < 1.0:
            raise StepError("finite_difference_step must be in (0, 1).")
        if not (isinstance(self.mu_decrease, (int, float)) and self.mu_decrease >= 1.0):
            raise StepError("mu_decrease must be ≥ 1.")
        if not (isinstance(self.mu_increase, (int, float)) and self.mu_increase > 1.0):
            raise StepError("mu_increase must be > 1.")
        for name in ("max_step_attempts", "solve_budget", "max_iterations"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise StepError(f"{name} must be a positive integer.")


@dataclass(frozen=True)
class ParameterBounds:
    names: tuple[str, ...]
    lower: tuple[float, ...]  # physical, > 0
    upper: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.names or len(set(self.names)) != len(self.names) \
                or not len(self.names) == len(self.lower) == len(self.upper):
            raise StepError("bounds need unique names and one lower/upper value each.")
        for name, low, high in zip(self.names, self.lower, self.upper):
            if not (math.isfinite(low) and math.isfinite(high) and 0.0 < low < high):
                raise StepError(f"{name}: bounds must satisfy 0 < lower < upper.")


def objective(residuals: np.ndarray) -> float:
    """Φ = ½‖r‖²."""
    residuals = np.asarray(residuals, dtype=float)
    return 0.5 * float(residuals @ residuals)


def lm_step(residuals: np.ndarray, jacobian: np.ndarray, mu: float) -> np.ndarray:
    """Δx = −(JᵀJ + μ·diag(JᵀJ))⁻¹ Jᵀ r — note the minus sign."""
    residuals, jacobian = np.asarray(residuals, dtype=float), np.asarray(jacobian, dtype=float)
    normal = jacobian.T @ jacobian
    damping = np.diag(np.diag(normal))
    if np.any(np.diag(normal) <= 0.0):
        raise StepError("a parameter has no sensitivity (zero Jacobian column); no step is defined.")
    return -np.linalg.solve(normal + mu * damping, jacobian.T @ residuals)


def broyden_update(jacobian: np.ndarray, step: np.ndarray, residual_change: np.ndarray) -> np.ndarray:
    """Rank-one secant update: J_new Δx = Δr."""
    step = np.asarray(step, dtype=float)
    denominator = float(step @ step)
    if denominator <= 0.0:
        return np.array(jacobian, dtype=float)
    return jacobian + np.outer(np.asarray(residual_change, dtype=float) - jacobian @ step, step) / denominator


def local_sd(jacobian: np.ndarray) -> np.ndarray:
    """sqrt(diag((JᵀJ)⁻¹)) in ln p for whitened residuals (stop rule only)."""
    normal = np.asarray(jacobian, dtype=float).T @ np.asarray(jacobian, dtype=float)
    try:
        covariance = np.linalg.inv(normal)
    except np.linalg.LinAlgError as exc:
        raise StepError("JᵀJ is singular; the stop rule's sd is undefined.") from exc
    diagonal = np.diag(covariance)
    if np.any(diagonal <= 0.0) or not np.all(np.isfinite(diagonal)):
        raise StepError("JᵀJ is not positive definite.")
    return np.sqrt(diagonal)


@dataclass(frozen=True)
class IterationRecord:
    iteration: int
    mu: float
    x: tuple[float, ...]
    trial_x: tuple[float, ...]
    objective_before: float
    trial_objective: Optional[float]
    accepted: bool
    note: str


@dataclass(frozen=True)
class LMResult:
    status: LMStatus
    parameters: Mapping[str, float]  # physical values at the last accepted point
    x: tuple[float, ...]
    objective: float
    solves: int
    iterations: int
    local_sd: Optional[tuple[float, ...]]
    history: tuple[IterationRecord, ...]
    refusal: Optional[str]


class _Loop:
    def __init__(self, evaluate: ResidualFunction, bounds: ParameterBounds, settings: LMSettings) -> None:
        self.evaluate, self.bounds, self.settings = evaluate, bounds, settings
        self.solves = 0

    def residuals(self, p: np.ndarray) -> np.ndarray:
        """One solve at the physical point ``p`` (values passed exactly, never via exp(ln p))."""
        if self.solves >= self.settings.solve_budget:
            raise _BudgetExhausted()
        self.solves += 1
        parameters = {name: float(value) for name, value in zip(self.bounds.names, p)}
        values = np.asarray(self.evaluate(parameters), dtype=float)
        if values.ndim != 1 or not np.all(np.isfinite(values)):
            raise StepError("the residual function must return a finite residual vector.")
        return values

    def jacobian(self, p: np.ndarray) -> np.ndarray:
        """Central differences at p·(1 ± h), exactly (the accepted ±5 % candidates), in ln p."""
        columns = []
        h = self.settings.finite_difference_step
        for j in range(len(p)):
            up, down = p.copy(), p.copy()
            up[j], down[j] = p[j] * (1.0 + h), p[j] * (1.0 - h)
            columns.append((self.residuals(up) - self.residuals(down)) / (math.log(up[j]) - math.log(down[j])))
        return np.column_stack(columns)


class _BudgetExhausted(Exception):
    pass


def run_bounded_lm(evaluate: ResidualFunction, start: Mapping[str, float], bounds: ParameterBounds,
                   settings: LMSettings) -> LMResult:
    """Bounded LM in ln p over ``evaluate`` (each call is one authorised solve)."""

    if set(start) != set(bounds.names):
        raise StepError("start values must be given for exactly the bounded parameters.")
    p = np.array([float(start[name]) for name in bounds.names])  # physical values are the source of truth
    lower, upper = np.array(bounds.lower), np.array(bounds.upper)
    if np.any(p < lower) or np.any(p > upper):
        raise StepError("the start point lies outside the bounds.")
    loop = _Loop(evaluate, bounds, settings)
    history: list[IterationRecord] = []
    mu = settings.mu_initial
    r = None

    def result(status, refusal=None, jacobian=None):
        sd = None
        if jacobian is not None:
            try:
                sd = tuple(float(v) for v in local_sd(jacobian))
            except StepError:
                sd = None
        parameters = {name: float(value) for name, value in zip(bounds.names, p)}
        return LMResult(status, parameters, tuple(float(v) for v in np.log(p)),
                        objective(r) if r is not None else math.nan, loop.solves,
                        len({h.iteration for h in history}), sd, tuple(history), refusal)

    jacobian = None
    try:
        r = loop.residuals(p)
        jacobian = loop.jacobian(p)
        fresh = True
        for iteration in range(1, settings.max_iterations + 1):
            attempts = 0
            while True:
                x = np.log(p)
                step = lm_step(r, jacobian, mu)
                trial_p = np.clip(np.exp(x + step), lower, upper)  # projected onto the physical bounds
                effective = np.log(trial_p) - x
                sd = local_sd(jacobian)
                if np.max(np.abs(effective) / sd) < settings.stop_fraction:
                    history.append(IterationRecord(iteration, mu, tuple(x), tuple(np.log(trial_p)), objective(r), None,
                                                   False, "step below stop_fraction·sd"))
                    return result(LMStatus.CONVERGED, jacobian=jacobian)
                trial_r = loop.residuals(trial_p)
                accepted = objective(trial_r) < objective(r)
                history.append(IterationRecord(iteration, mu, tuple(x), tuple(np.log(trial_p)), objective(r),
                                               objective(trial_r), accepted, "accepted" if accepted else "rejected"))
                if accepted:
                    jacobian = broyden_update(jacobian, effective, trial_r - r)
                    fresh = False
                    p, r = trial_p, trial_r
                    mu /= settings.mu_decrease
                    break
                mu *= settings.mu_increase
                attempts += 1
                if attempts >= settings.max_step_attempts:
                    return result(LMStatus.STEP_REJECTED, jacobian=jacobian)
                if not fresh:  # finite differences are repeated only after a step failure
                    jacobian = loop.jacobian(p)
                    fresh = True
        return result(LMStatus.MAX_ITERATIONS, jacobian=jacobian)
    except (BranchTrackingRefusal, ObservationFreezeRefusal) as refusal:
        return result(LMStatus.REFUSED, refusal=str(refusal), jacobian=jacobian)
    except _BudgetExhausted:
        return result(LMStatus.SOLVE_BUDGET, jacobian=jacobian)


def parameter_bounds(values: Sequence[tuple[str, float, float]]) -> ParameterBounds:
    names, lower, upper = zip(*values)
    return ParameterBounds(tuple(names), tuple(float(v) for v in lower), tuple(float(v) for v in upper))
