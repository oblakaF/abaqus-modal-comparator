"""Baseline identification pairing under an explicit policy — Auto-ID M4.1 (SPEC §12.1; AUDIT V4).

The policy's gates are applied to every experimental/FE pair *before* the assignment;
the assignment (Hungarian, maximum number of pairs first, then maximum total MAC) runs
only over admissible entries.  Nothing is silently resolved:

- a MAC entry that is not available (NaN) for a frequency-admissible pair makes the
  evidence incomplete — its admissibility is unknown, so the pairing cannot be final;
- an optimal assignment that is not unique (within the policy's tie tolerance) is
  ambiguous;
- fewer pairs than the policy's coverage is insufficient.

This module never calls the normal comparator and never changes its defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment

from domain.identification_pairing_policy import IdentificationPairingPolicy


class PairingInputError(ValueError):
    """Pairing inputs are malformed."""


class BaselinePairingStatus(str, Enum):
    COMPLETE = "COMPLETE"
    INCOMPLETE_EVIDENCE = "INCOMPLETE_EVIDENCE"  # some frequency-admissible MAC entries are unknown
    AMBIGUOUS = "AMBIGUOUS"  # the optimal assignment is not unique
    INSUFFICIENT_COVERAGE = "INSUFFICIENT_COVERAGE"  # fewer pairs than the policy requires


@dataclass(frozen=True)
class ModeFrequency:
    number: int
    frequency_hz: float


@dataclass(frozen=True)
class IdentificationPair:
    experimental_mode: int
    fe_mode: int
    experimental_hz: float
    fe_hz: float
    mac: float
    relative_frequency_error: float  # (f_FE − f_EXP) / f_EXP


@dataclass(frozen=True)
class UnpairedExperimentalMode:
    experimental_mode: int
    reason: str


@dataclass(frozen=True)
class BaselinePairingResult:
    policy_id: str
    policy_hash: str
    status: BaselinePairingStatus
    pairs: tuple[IdentificationPair, ...]  # final only when status is COMPLETE; otherwise provisional
    unpaired: tuple[UnpairedExperimentalMode, ...]
    unknown_entries: tuple[tuple[int, int], ...]  # (experimental, FE) pairs whose MAC is not available
    ambiguous_pairs: tuple[tuple[int, int], ...]

    @property
    def final(self) -> bool:
        return self.status is BaselinePairingStatus.COMPLETE


def _modes(values: Sequence[ModeFrequency], name: str) -> tuple[ModeFrequency, ...]:
    modes = tuple(values)
    if not modes:
        raise PairingInputError(f"{name} modes are empty.")
    numbers = [mode.number for mode in modes]
    if len(set(numbers)) != len(numbers):
        raise PairingInputError(f"{name} mode numbers must be unique.")
    for mode in modes:
        if isinstance(mode.number, bool) or not isinstance(mode.number, int):
            raise PairingInputError(f"{name} mode numbers must be integers.")
        if not math.isfinite(mode.frequency_hz) or mode.frequency_hz <= 0.0:
            raise PairingInputError(f"{name} mode {mode.number}: frequency must be finite and positive.")
    return modes


def _assignment(weights: np.ndarray, admissible: np.ndarray) -> tuple[list[tuple[int, int]], int, float]:
    """Maximum-cardinality, then maximum-total-MAC assignment over admissible entries."""
    if not admissible.any():
        return [], 0, 0.0
    big = float(min(weights.shape) + 1)
    cost = np.where(admissible, -(big + weights), 0.0)
    rows, columns = linear_sum_assignment(cost)
    pairs = [(int(i), int(j)) for i, j in zip(rows, columns) if admissible[i, j]]
    return pairs, len(pairs), float(sum(weights[i, j] for i, j in pairs))


def pair_baseline(policy: IdentificationPairingPolicy, experimental: Sequence[ModeFrequency],
                  fe: Sequence[ModeFrequency], mac: np.ndarray) -> BaselinePairingResult:
    """Pair eligible experimental modes with elastic FE modes under ``policy``.

    ``mac[i, j]`` is the MAC of experimental mode ``experimental[i]`` with FE mode
    ``fe[j]`` on the measured DOFs, or NaN where it is not available.
    """

    if not isinstance(policy, IdentificationPairingPolicy):
        raise TypeError("policy must be an IdentificationPairingPolicy (passed explicitly).")
    experimental, fe = _modes(experimental, "experimental"), _modes(fe, "FE")
    mac = np.asarray(mac, dtype=float)
    if mac.shape != (len(experimental), len(fe)):
        raise PairingInputError(f"MAC matrix shape {mac.shape} != ({len(experimental)}, {len(fe)}).")
    known = np.isfinite(mac)
    if np.any(known & ((mac < 0.0) | (mac > 1.0 + 1e-12))):
        raise PairingInputError("MAC values must lie in [0, 1].")

    f_exp = np.array([mode.frequency_hz for mode in experimental])[:, None]
    f_fe = np.array([mode.frequency_hz for mode in fe])[None, :]
    relative = (f_fe - f_exp) / f_exp
    frequency_ok = np.abs(relative) <= policy.maximum_relative_frequency_error
    weights = np.where(known, mac, 0.0)
    admissible = frequency_ok & known & (weights >= policy.minimum_mac)
    unknown = frequency_ok & ~known

    assigned, count, total = _assignment(weights, admissible)
    ambiguous = []
    for i, j in assigned:
        blocked = admissible.copy()
        blocked[i, j] = False
        _, other_count, other_total = _assignment(weights, blocked)
        if other_count == count and abs(other_total - total) <= policy.assignment_tie_tolerance:
            ambiguous.append((experimental[i].number, fe[j].number))

    pairs = tuple(IdentificationPair(experimental[i].number, fe[j].number, experimental[i].frequency_hz,
                                     fe[j].frequency_hz, float(mac[i, j]), float(relative[i, j]))
                  for i, j in sorted(assigned, key=lambda item: experimental[item[0]].number))
    paired_rows = {i for i, _ in assigned}
    unpaired = []
    for i, mode in enumerate(experimental):
        if i in paired_rows:
            continue
        if not frequency_ok[i].any():
            reason = "no FE mode within the frequency gate"
        elif unknown[i].any():
            reason = "MAC not available for frequency-admissible FE modes; admissibility unknown"
        elif not admissible[i].any():
            reason = "MAC below the policy minimum for every frequency-admissible FE mode"
        else:
            reason = "its admissible FE modes are assigned to other experimental modes"
        unpaired.append(UnpairedExperimentalMode(mode.number, reason))

    if ambiguous:
        status = BaselinePairingStatus.AMBIGUOUS
    elif unknown.any():
        status = BaselinePairingStatus.INCOMPLETE_EVIDENCE
    elif count < policy.minimum_observations:
        status = BaselinePairingStatus.INSUFFICIENT_COVERAGE
    else:
        status = BaselinePairingStatus.COMPLETE
    unknown_entries = tuple((experimental[i].number, fe[j].number) for i, j in zip(*np.nonzero(unknown)))
    return BaselinePairingResult(policy.policy_id, policy.policy_hash, status, pairs, tuple(unpaired),
                                 unknown_entries, tuple(ambiguous))
