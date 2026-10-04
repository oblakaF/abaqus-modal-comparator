"""FE-to-FE branch tracking — Auto-ID M4.5 (SPEC §12.1, §12.4; D-008; AUDIT V4).

After the baseline freeze, each observation row is followed from a reference FE state
(the baseline, or the last accepted candidate) to a candidate FE state by **FE-to-FE
shape identity only**: MAC ≥ the policy's tracking minimum (0.90) with a unique
assignment.  Confirmed clusters are followed as 2-mode subspaces (both principal-angle
cos² > 0.95).  Experimental data never enter tracking, and no normal-comparator
re-pairing happens.

Any loss, exchange or ambiguity of identity is a scientific refusal
(``BranchTrackingRefusal``); rows are never added or dropped.  A frequency-order change
with stable shapes is tracked correctly and recorded as evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from itertools import combinations
from typing import Mapping, Optional, Sequence

import numpy as np

from domain.identification_pairing_policy import IdentificationPairingPolicy

from .identification_clusters import SUBSPACE_MINIMUM_COS2, principal_cos2


class TrackingInputError(ValueError):
    """Tracking inputs are malformed or the two FE states are not comparable."""


class RefusalKind(str, Enum):
    BRANCH_LOSS = "BRANCH_LOSS"  # no candidate mode reaches the tracking MAC
    BRANCH_EXCHANGE = "BRANCH_EXCHANGE"  # one candidate mode is claimed by several tracked branches
    AMBIGUOUS = "AMBIGUOUS"  # several candidate modes reach the tracking MAC for one branch
    CLUSTER_LOSS = "CLUSTER_LOSS"  # no unique candidate pair spans a cluster subspace


class BranchTrackingRefusal(Exception):
    """Scientific refusal: branch identity is lost.  Never re-paired.

    Not a ValueError/RuntimeError, so generic fallback handlers never swallow it.
    """

    def __init__(self, kind: RefusalKind, details: tuple[str, ...]) -> None:
        super().__init__(f"{kind.value}: " + "; ".join(details))
        self.kind = kind
        self.details = details


@dataclass(frozen=True)
class FEModalState:
    """FE modes of one solved state, on one common node/DOF set."""

    state_id: str  # for example the M3 job name
    fe_geometry_sha256: str
    node_set_sha256: str  # identity of the node/DOF set the shapes are given on
    mode_numbers: tuple[int, ...]
    frequencies_hz: tuple[float, ...]
    shapes: np.ndarray  # modes × DOFs

    def __post_init__(self) -> None:
        shapes = np.asarray(self.shapes, dtype=float)
        object.__setattr__(self, "shapes", shapes)
        if (not self.mode_numbers or shapes.ndim != 2 or shapes.shape[0] != len(self.mode_numbers)
                or len(self.frequencies_hz) != len(self.mode_numbers)):
            raise TrackingInputError(f"{self.state_id}: modes, frequencies and shapes do not match.")
        if any(not np.isfinite(value) or value <= 0 for value in self.frequencies_hz):
            raise TrackingInputError(f"{self.state_id}: frequencies must be finite and positive.")
        if len(set(self.mode_numbers)) != len(self.mode_numbers):
            raise TrackingInputError(f"{self.state_id}: mode numbers must be unique.")
        if not np.all(np.isfinite(shapes)) or np.any(np.einsum("ij,ij->i", shapes, shapes) <= 0):
            raise TrackingInputError(f"{self.state_id}: shapes must be finite and non-zero.")

    def index(self, mode: int) -> int:
        try:
            return self.mode_numbers.index(mode)
        except ValueError:
            raise TrackingInputError(f"{self.state_id}: mode {mode} not present.") from None


@dataclass(frozen=True)
class TrackedBranch:
    row_id: str
    reference_mode: int
    candidate_mode: int
    candidate_hz: float
    mac: float


@dataclass(frozen=True)
class TrackedCluster:
    row_ids: tuple[str, ...]
    reference_modes: tuple[int, int]
    candidate_modes: tuple[int, int]
    candidate_hz: tuple[float, float]
    cos2: tuple[float, float]


@dataclass(frozen=True)
class TrackingResult:
    policy_hash: str
    reference_state: str
    candidate_state: str
    branches: tuple[TrackedBranch, ...]
    clusters: tuple[TrackedCluster, ...]
    order_changes: tuple[tuple[str, str], ...]  # row pairs whose FE frequency order swapped (evidence)

    def candidate_hz(self, row_id: str) -> float:
        for branch in self.branches:
            if branch.row_id == row_id:
                return branch.candidate_hz
        raise KeyError(row_id)


def _weighted(shapes: np.ndarray, weights: Optional[np.ndarray]) -> np.ndarray:
    if weights is None:
        return shapes
    weights = np.asarray(weights, dtype=float).reshape(-1)
    if weights.shape[0] != shapes.shape[1] or np.any(weights <= 0) or not np.all(np.isfinite(weights)):
        raise TrackingInputError("weights must be positive and match the shape length.")
    return shapes * np.sqrt(weights)


def _mac_matrix(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    cross = left @ right.T
    return cross ** 2 / np.outer(np.einsum("ij,ij->i", left, left), np.einsum("ij,ij->i", right, right))


def track_branches(policy: IdentificationPairingPolicy, reference: FEModalState, candidate: FEModalState,
                   rows: Mapping[str, int], clusters: Sequence[Sequence[str]] = (),
                   weights: Optional[np.ndarray] = None) -> TrackingResult:
    """Follow frozen rows (``row_id → reference FE mode``) into the candidate state.

    Rows listed in ``clusters`` (confirmed 2-mode clusters) are followed as one subspace.
    Raises ``BranchTrackingRefusal`` on any loss, exchange or ambiguity of identity.
    """

    if not isinstance(policy, IdentificationPairingPolicy):
        raise TypeError("policy must be an IdentificationPairingPolicy (passed explicitly).")
    if (reference.fe_geometry_sha256, reference.node_set_sha256) != (candidate.fe_geometry_sha256,
                                                                      candidate.node_set_sha256):
        raise TrackingInputError("reference and candidate are not on the same FE geometry and node set.")
    if reference.shapes.shape[1] != candidate.shapes.shape[1]:
        raise TrackingInputError("reference and candidate shapes have different lengths.")
    cluster_rows = [tuple(group) for group in clusters]
    if any(len(group) != 2 for group in cluster_rows):
        raise TrackingInputError("only confirmed 2-mode clusters can be tracked as subspaces.")
    clustered = {row for group in cluster_rows for row in group}
    if not clustered <= set(rows) or len(clustered) != 2 * len(cluster_rows):
        raise TrackingInputError("cluster rows must be distinct frozen rows.")

    ref_shapes, cand_shapes = _weighted(reference.shapes, weights), _weighted(candidate.shapes, weights)
    singles = [row for row in rows if row not in clustered]
    ref_index = [reference.index(rows[row]) for row in singles]
    macs = _mac_matrix(ref_shapes[ref_index], cand_shapes) if singles else np.zeros((0, len(candidate.mode_numbers)))
    admissible = macs >= policy.tracking_minimum_mac

    lost = [row for row, ok in zip(singles, admissible) if not ok.any()]
    if lost:
        raise BranchTrackingRefusal(RefusalKind.BRANCH_LOSS, tuple(
            f"{row} (reference mode {rows[row]}): best FE-to-FE MAC {macs[i].max():.3f} < "
            f"{policy.tracking_minimum_mac}" for i, row in enumerate(singles) if row in lost))
    ambiguous = [row for row, ok in zip(singles, admissible) if ok.sum() > 1]
    if ambiguous:
        raise BranchTrackingRefusal(RefusalKind.AMBIGUOUS, tuple(
            f"{row}: several candidate modes reach MAC ≥ {policy.tracking_minimum_mac}" for row in ambiguous))
    chosen = {row: int(np.argmax(admissible[i])) for i, row in enumerate(singles)}
    claimed: dict[int, list[str]] = {}
    for row, column in chosen.items():
        claimed.setdefault(column, []).append(row)
    exchanged = [rows_ for rows_ in claimed.values() if len(rows_) > 1]
    if exchanged:
        raise BranchTrackingRefusal(RefusalKind.BRANCH_EXCHANGE, tuple(
            f"rows {group} claim the same candidate mode" for group in exchanged))

    branches = tuple(TrackedBranch(row, rows[row], candidate.mode_numbers[column],
                                   float(candidate.frequencies_hz[column]), float(macs[singles.index(row), column]))
                     for row, column in chosen.items())

    used = set(chosen.values())
    tracked_clusters = []
    for group in cluster_rows:
        reference_pair = tuple(rows[row] for row in group)
        basis = ref_shapes[[reference.index(mode) for mode in reference_pair]]
        free = [j for j in range(len(candidate.mode_numbers)) if j not in used]
        passing = []
        for pair in combinations(free, 2):
            cos2 = principal_cos2(basis, cand_shapes[list(pair)])
            if min(cos2) > SUBSPACE_MINIMUM_COS2:
                passing.append((pair, cos2))
        if len(passing) != 1:
            raise BranchTrackingRefusal(RefusalKind.CLUSTER_LOSS, (
                f"cluster {group}: {len(passing)} candidate pairs span the subspace (need exactly one)",))
        pair, cos2 = passing[0]
        used.update(pair)
        tracked_clusters.append(TrackedCluster(
            group, reference_pair, (candidate.mode_numbers[pair[0]], candidate.mode_numbers[pair[1]]),
            (float(candidate.frequencies_hz[pair[0]]), float(candidate.frequencies_hz[pair[1]])),
            (float(cos2[0]), float(cos2[1]))))

    order_changes = []
    reference_hz = {row: reference.frequencies_hz[reference.index(rows[row])] for row in singles}
    candidate_hz = {branch.row_id: branch.candidate_hz for branch in branches}
    for left, right in combinations(sorted(singles, key=lambda row: reference_hz[row]), 2):
        if candidate_hz[left] > candidate_hz[right]:
            order_changes.append((left, right))
    return TrackingResult(policy.policy_hash, reference.state_id, candidate.state_id, branches,
                          tuple(tracked_clusters), tuple(order_changes))
