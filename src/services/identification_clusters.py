"""Modal-cluster trigger and principal-angle confirmation — Auto-ID M4.4 (SPEC §12.4; D-009).

Frequency closeness |Δf| / f < 3 % (experimental or FE) is **only a trigger**.  A 2-mode
cluster is confirmed when, under the allowed parameter perturbations (±5 % in each relevant
direction):

- individual branch identity becomes unstable — the FE-to-FE MAC of at least one mode
  falls below 0.9 in at least one direction — **but**
- the two-dimensional modal subspace stays stable in **every** tested direction:
  cos²θ₁ > 0.95 and cos²θ₂ > 0.95 (principal angles / canonical correlations).

A confirmed cluster contributes one residual, r_C = (1/n_C)·Σ ln(f_FE / f_EXP), which is
assignment-invariant; it is never counted as two independent observations.

Groups of more than two modes (M4_DECISION_RECORD §10, option A1): they are never confirmed
as one cluster (SPEC §12.4 defines 2-mode clusters).  They are INDEPENDENT only when, in every
tested direction, every member has exactly one distinct FE-to-FE counterpart with MAC ≥ 0.9
and the N-dimensional subspace those counterparts span is stable (every principal-angle
cos² > 0.95).  Otherwise they are UNSUPPORTED.  The 2-mode path is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from itertools import combinations
import math
from typing import Mapping, Optional, Sequence

import numpy as np


CLUSTER_TRIGGER_RELATIVE_SPACING = 0.03  # SPEC §12.4: a trigger only
SUBSPACE_MINIMUM_COS2 = 0.95  # SPEC §12.4, both principal angles
BRANCH_MINIMUM_MAC = 0.90  # SPEC §12.1/§12.4 FE-to-FE branch identity
CARBON_V1_DIRECTIONS = ("E_in_plane_mpa+", "E_in_plane_mpa-", "G12_mpa+", "G12_mpa-")  # ±5 % in E and G12


class ClusterInputError(ValueError):
    """Cluster inputs are malformed."""


class ClusterStatus(str, Enum):
    CONFIRMED = "CONFIRMED"  # one cluster observation
    INDEPENDENT = "INDEPENDENT"  # individual identity stable in every direction: two observations
    UNSTABLE = "UNSTABLE"  # subspace not stable, or not uniquely identified: a scientific refusal
    UNSUPPORTED = "UNSUPPORTED"  # more than two modes triggered together, not individually stable (A1)


@dataclass(frozen=True)
class TriggerRow:
    row_id: str
    experimental_hz: float
    fe_hz: float


@dataclass(frozen=True)
class ClusterTrigger:
    row_ids: tuple[str, ...]
    experimental_spacing: float  # largest adjacent relative spacing inside the group
    fe_spacing: float


def _relative(a: float, b: float) -> float:
    return abs(a - b) / min(a, b)


def cluster_triggers(rows: Sequence[TriggerRow], spacing: float = CLUSTER_TRIGGER_RELATIVE_SPACING
                     ) -> tuple[ClusterTrigger, ...]:
    """Groups of rows linked by |Δf| / f < ``spacing`` in experimental **or** FE frequency."""

    rows = list(rows)
    if len({row.row_id for row in rows}) != len(rows):
        raise ClusterInputError("row ids must be unique.")
    for row in rows:
        if not (math.isfinite(row.experimental_hz) and row.experimental_hz > 0 and math.isfinite(row.fe_hz)
                and row.fe_hz > 0):
            raise ClusterInputError(f"row {row.row_id}: frequencies must be finite and positive.")
    parent = {row.row_id: row.row_id for row in rows}

    def find(item):
        while parent[item] != item:
            item = parent[item]
        return item

    for left, right in combinations(rows, 2):
        if (_relative(left.experimental_hz, right.experimental_hz) < spacing
                or _relative(left.fe_hz, right.fe_hz) < spacing):
            parent[find(left.row_id)] = find(right.row_id)
    groups: dict[str, list[TriggerRow]] = {}
    for row in rows:
        groups.setdefault(find(row.row_id), []).append(row)
    triggers = []
    for members in groups.values():
        if len(members) < 2:
            continue
        exp = sorted(member.experimental_hz for member in members)
        fe = sorted(member.fe_hz for member in members)
        triggers.append(ClusterTrigger(
            tuple(member.row_id for member in sorted(members, key=lambda m: m.experimental_hz)),
            max(_relative(a, b) for a, b in zip(exp, exp[1:])), max(_relative(a, b) for a, b in zip(fe, fe[1:]))))
    return tuple(sorted(triggers, key=lambda trigger: trigger.row_ids))


def _weighted(vectors: np.ndarray, weights: Optional[np.ndarray]) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=float)
    if weights is None:
        return vectors
    weights = np.asarray(weights, dtype=float).reshape(-1)
    if weights.shape[0] != vectors.shape[-1] or np.any(weights <= 0) or not np.all(np.isfinite(weights)):
        raise ClusterInputError("weights must be positive and match the shape length.")
    return vectors * np.sqrt(weights)


def fe_mac(left: np.ndarray, right: np.ndarray) -> float:
    numerator = float(np.dot(left, right)) ** 2
    denominator = float(np.dot(left, left) * np.dot(right, right))
    if denominator <= 0.0:
        raise ClusterInputError("a shape vector is zero.")
    return numerator / denominator


def principal_cos2(left: np.ndarray, right: np.ndarray) -> tuple[float, ...]:
    """Squared cosines of the principal angles between the column spaces (largest first)."""
    q_left, _ = np.linalg.qr(np.asarray(left, dtype=float).T)
    q_right, _ = np.linalg.qr(np.asarray(right, dtype=float).T)
    singular = np.linalg.svd(q_left.T @ q_right, compute_uv=False)
    return tuple(float(min(1.0, value * value)) for value in singular)


@dataclass(frozen=True)
class DirectionEvidence:
    direction: str
    individual_macs: tuple[float, ...]  # best FE-to-FE MAC of each baseline mode in this direction
    individual_stable: bool  # every mode has a unique perturbed counterpart with MAC ≥ 0.9
    subspace_modes: Optional[tuple[int, ...]]  # indices of the perturbed modes spanning the subspace
    cos2: tuple[float, ...]
    subspace_stable: bool
    subspace_unique: bool


@dataclass(frozen=True)
class ClusterConfirmation:
    row_ids: tuple[str, ...]
    status: ClusterStatus
    directions: tuple[DirectionEvidence, ...]
    reasons: tuple[str, ...]


def _individual(baseline: np.ndarray, perturbed: np.ndarray) -> tuple[tuple[float, float], bool]:
    macs = np.array([[fe_mac(a, b) for b in perturbed] for a in baseline])
    best = tuple(float(value) for value in macs.max(axis=1))
    admissible = macs >= BRANCH_MINIMUM_MAC
    unique = (all(admissible[i].sum() == 1 for i in range(2))
              and int(np.argmax(admissible[0])) != int(np.argmax(admissible[1])))
    return best, bool(unique)


def _subspace(baseline: np.ndarray, perturbed: np.ndarray) -> tuple[Optional[tuple[int, int]], tuple[float, float], bool]:
    scored = []
    for pair in combinations(range(len(perturbed)), 2):
        cos2 = principal_cos2(baseline, perturbed[list(pair)])
        scored.append((min(cos2), pair, (cos2[0], cos2[1])))
    scored.sort(reverse=True)
    best_min, pair, cos2 = scored[0]
    passing = [item for item in scored if item[0] > SUBSPACE_MINIMUM_COS2]
    return pair, cos2, len(passing) <= 1


def _independent_group(row_ids: tuple[str, ...], baseline: np.ndarray, perturbed_shapes: Mapping[str, np.ndarray],
                       weights: Optional[np.ndarray], required_directions: Sequence[str]) -> ClusterConfirmation:
    """A1 (M4_DECISION_RECORD §10): an N > 2 group is INDEPENDENT or UNSUPPORTED, never CONFIRMED."""

    evidence, failures = [], []
    for direction in required_directions:
        perturbed = _weighted(perturbed_shapes[direction], weights)
        if perturbed.ndim != 2 or perturbed.shape[0] < len(row_ids) or perturbed.shape[1] != baseline.shape[1]:
            raise ClusterInputError(f"{direction}: need at least {len(row_ids)} perturbed shapes of the baseline length.")
        macs = np.array([[fe_mac(a, b) for b in perturbed] for a in baseline])
        admissible = macs >= BRANCH_MINIMUM_MAC
        counterparts = [int(np.argmax(row)) for row in admissible]
        unique = all(row.sum() == 1 for row in admissible) and len(set(counterparts)) == len(counterparts)
        cos2 = principal_cos2(baseline, perturbed[counterparts]) if unique else tuple(0.0 for _ in row_ids)
        stable = unique and min(cos2) > SUBSPACE_MINIMUM_COS2
        evidence.append(DirectionEvidence(direction, tuple(float(v) for v in macs.max(axis=1)), unique,
                                          tuple(counterparts) if unique else None, tuple(float(v) for v in cos2),
                                          stable, unique))
        if not unique:
            failures.append(f"{direction}: not every member has exactly one distinct counterpart with MAC ≥ "
                            f"{BRANCH_MINIMUM_MAC}")
        elif not stable:
            failures.append(f"{direction}: {len(row_ids)}-dimensional subspace not stable "
                            f"(min cos² {min(cos2):.4f} ≤ {SUBSPACE_MINIMUM_COS2})")
    if failures:
        return ClusterConfirmation(row_ids, ClusterStatus.UNSUPPORTED, tuple(evidence),
                                   (f"{len(row_ids)}-mode group is not individually stable (A1); SPEC §12.4 "
                                    "defines 2-mode clusters only",) + tuple(failures))
    return ClusterConfirmation(row_ids, ClusterStatus.INDEPENDENT, tuple(evidence),
                               (f"{len(row_ids)}-mode group: every member individually stable with a stable "
                                "subspace in every direction (A1): independent observations",))


def confirm_cluster(row_ids: Sequence[str], baseline_shapes: np.ndarray, perturbed_shapes: Mapping[str, np.ndarray],
                    weights: Optional[np.ndarray] = None,
                    required_directions: Sequence[str] = CARBON_V1_DIRECTIONS) -> ClusterConfirmation:
    """Confirm (or not) a triggered 2-mode cluster from baseline and perturbed FE shapes.

    ``baseline_shapes`` is 2 × n (the two baseline FE modes); ``perturbed_shapes[direction]``
    is k × n (the FE modes of the perturbed state considered for this cluster, k ≥ 2).
    Shapes are on one common node/DOF set; ``weights`` (for example nodal masses) is optional.
    Groups of N > 2 modes (N × n baseline) are only examined for independence (A1).
    """

    row_ids = tuple(row_ids)
    baseline = _weighted(baseline_shapes, weights)
    if len(row_ids) > 2 and baseline.ndim == 2 and baseline.shape[0] == len(row_ids):
        missing = sorted(set(required_directions) - set(perturbed_shapes))
        if missing:
            raise ClusterInputError(f"perturbed shapes missing for directions {missing}.")
        return _independent_group(row_ids, baseline, perturbed_shapes, weights, required_directions)
    if len(row_ids) != 2 or baseline.ndim != 2 or baseline.shape[0] != 2:
        return ClusterConfirmation(row_ids, ClusterStatus.UNSUPPORTED, (),
                                   ("SPEC §12.4 defines 2-mode clusters; this group is not confirmable",))
    missing = sorted(set(required_directions) - set(perturbed_shapes))
    if missing:
        raise ClusterInputError(f"perturbed shapes missing for directions {missing}.")
    evidence = []
    for direction in required_directions:
        perturbed = _weighted(perturbed_shapes[direction], weights)
        if perturbed.ndim != 2 or perturbed.shape[0] < 2 or perturbed.shape[1] != baseline.shape[1]:
            raise ClusterInputError(f"{direction}: need at least two perturbed shapes of the baseline length.")
        best, stable = _individual(baseline, perturbed)
        pair, cos2, unique = _subspace(baseline, perturbed)
        evidence.append(DirectionEvidence(direction, best, stable, pair, cos2,
                                          min(cos2) > SUBSPACE_MINIMUM_COS2, unique))
    evidence = tuple(evidence)
    if not all(item.subspace_stable and item.subspace_unique for item in evidence):
        bad = [item.direction for item in evidence if not (item.subspace_stable and item.subspace_unique)]
        return ClusterConfirmation(row_ids, ClusterStatus.UNSTABLE, evidence,
                                   (f"two-mode subspace not stable or not unique in {bad}",))
    if all(item.individual_stable for item in evidence):
        return ClusterConfirmation(row_ids, ClusterStatus.INDEPENDENT, evidence,
                                   ("individual branch identity stable in every direction: two observations",))
    unstable = [item.direction for item in evidence if not item.individual_stable]
    return ClusterConfirmation(row_ids, ClusterStatus.CONFIRMED, evidence,
                               (f"individual identity unstable in {unstable}; subspace stable in all directions",))


def cluster_log_residual(fe_hz: Sequence[float], experimental_hz: Sequence[float]) -> float:
    """r_C = (1/n_C)·Σ ln(f_FE / f_EXP) = mean ln f_FE − mean ln f_EXP (independent of member pairing)."""
    fe, exp = list(fe_hz), list(experimental_hz)
    if len(fe) != len(exp) or len(fe) < 2:
        raise ClusterInputError("a cluster residual needs the same number (≥ 2) of FE and experimental values.")
    if any(not math.isfinite(value) or value <= 0 for value in fe + exp):
        raise ClusterInputError("cluster frequencies must be finite and positive.")
    return (sum(math.log(value) for value in fe) - sum(math.log(value) for value in exp)) / len(fe)
