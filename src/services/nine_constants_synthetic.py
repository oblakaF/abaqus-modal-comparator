"""Synthetic nine-constant experiments — research track NINE-EC (Phase F). SYNTHETIC / TEST EVIDENCE ONLY.

A synthetic "experiment" is the elastic spectrum of a declared true constant set on the synthetic block model, with
optional Gaussian frequency noise of a DECLARED synthetic sd (a test input, never a real Σ). Observation rows are
frozen once, at the start state, by FE-to-FE shape identity between the true state and the start state (the accepted
tracker, MAC ≥ 0.90, unique); no frequency matching, no re-pairing. Family keys come from the model's exact symmetry
classes. HOLDOUT rows are the highest selected families (SPEC §12.3 analogue: the highest accepted family as
validation holdout); they are never fitted.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional, Sequence

import numpy as np

from domain.forward_model_manifest import EngineeringConstants
from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING

from .branch_tracker import track_branches
from .nine_constants_engine import ObservationRow, Role
from .orthotropic_block_model import BlockForwardModel

SYNTHETIC_LABEL = "SYNTHETIC / TEST EVIDENCE — NOT A MEASUREMENT"
CLUSTER_TRIGGER = 0.03  # SPEC §12.4 cluster trigger |Δf|/f < 3 % (used here only to exclude same-class neighbours)


def perturbed_states(base: EngineeringConstants, ln_step: float = 0.05, poisson_step: float = 0.02
                     ) -> list[EngineeringConstants]:
    """``base`` and its one-at-a-time sensitivity perturbations (moduli ×e^{±h}, ν ± step), admissible ones only."""
    from domain.orthotropic_elasticity import COORDINATES, CoordinateKind, NAMES, admissibility, from_coordinates, \
        to_coordinates

    states = [base]
    x0 = to_coordinates(base)
    for j, name in enumerate(NAMES):
        step = ln_step if COORDINATES[name] is CoordinateKind.LOG else poisson_step
        for sign in (1, -1):
            x = x0.copy()
            x[j] += sign * step
            candidate = from_coordinates(base, NAMES, x)
            if admissibility(candidate).admissible:
                states.append(candidate)
    return states


def separated_modes(forward: BlockForwardModel, states: Sequence[EngineeringConstants], count: int,
                    trigger: float = CLUSTER_TRIGGER) -> list[int]:
    """The lowest ``count`` modes (1-based) whose nearest same-symmetry-class mode is ≥ ``trigger`` apart in every
    listed state. Design-time exclusion of potential clusters (a cluster is never two observations, SPEC §12.4);
    modes of different symmetry classes cross without mixing and are kept."""
    bad: set[int] = set()
    for constants in states:
        solution = forward.solve(constants)
        f = np.array(solution.frequencies_hz)
        classes = solution.symmetry_classes
        for i in range(len(f)):
            same = [j for j in range(len(f)) if j != i and classes[j] == classes[i]]
            if same and min(abs(f[j] - f[i]) / f[i] for j in same) < trigger:
                bad.add(i + 1)
    chosen = [m for m in range(1, len(forward.solve(states[0]).frequencies_hz) + 1) if m not in bad][:count]
    if len(chosen) < count:
        raise ValueError(f"only {len(chosen)} separated modes among {forward.mode_count}; extract more modes.")
    return chosen


@dataclass(frozen=True)
class SyntheticExperiment:
    truth: EngineeringConstants
    rows: tuple[ObservationRow, ...]
    noise_sd_ln: float
    seed: Optional[int]
    label: str = SYNTHETIC_LABEL

    def to_dict(self) -> dict:
        return {"label": self.label, "truth": self.truth.to_dict(), "noise_sd_ln": self.noise_sd_ln,
                "seed": self.seed, "rows": [r.to_dict() for r in self.rows]}


def synthetic_experiment(forward: BlockForwardModel, truth: EngineeringConstants, start: EngineeringConstants,
                         mode_numbers: Sequence[int], holdout_count: int, sd_ln: float, noise_sd_ln: float = 0.0,
                         seed: Optional[int] = None) -> SyntheticExperiment:
    """Rows for the listed TRUE modes (1-based), paired to start-state modes by shape identity only."""
    true_solution = forward.solve(truth)
    start_solution = forward.solve(start)
    geometry = forward.block.geometry_id
    true_state = true_solution.state("truth", geometry)
    start_state = start_solution.state("start", geometry)
    keys = forward.block.family_keys(true_solution)
    tracking = track_branches(STRICT_IDENTIFICATION_PAIRING, true_state, start_state,
                              {f"X{m}": m for m in mode_numbers})
    paired = {b.row_id: b.candidate_mode for b in tracking.branches}
    rng = np.random.default_rng(seed)
    rows = []
    ordered = sorted(mode_numbers)
    holdouts = set(ordered[len(ordered) - holdout_count:]) if holdout_count else set()
    for m in ordered:
        frequency = true_solution.frequencies_hz[m - 1]
        if noise_sd_ln > 0.0:
            frequency *= math.exp(float(rng.normal(0.0, noise_sd_ln)))
        rows.append(ObservationRow(f"X{m}", frequency, paired[f"X{m}"], keys[m - 1],
                                   Role.HOLDOUT if m in holdouts else Role.FIT, sd_ln))
    return SyntheticExperiment(truth, tuple(rows), noise_sd_ln, seed)
