"""Near-degenerate modal clusters and basis-invariant subspace correlation.

This service operates only on pairs already present in a ``ComparisonResult``.
It deliberately does not reconstruct unmatched modes or change ordinary modal
pairing. Large mode-shape arrays are used transiently and are not copied into
the domain results.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Dict, Hashable, List, Optional, Sequence, Tuple

import numpy as np

from domain.modal_observation import InclusionStatus, ModalCluster, ModalObservation
from modal_core import ComparisonResult, ModePairResult
from .specimen_comparison_service import comparison_to_observations


@dataclass(frozen=True)
class ModalClusterAnalysis:
    """Comparator observations plus any clusters detected among those pairs."""

    observations: Tuple[ModalObservation, ...]
    clusters: Tuple[ModalCluster, ...]

    @property
    def effective_observation_count(self) -> int:
        clustered = sum(cluster.cluster_size for cluster in self.clusters)
        return len(self.observations) - clustered + len(self.clusters)


def _orthonormal_basis(matrix: np.ndarray, relative_tolerance: Optional[float]) -> np.ndarray:
    values = np.asarray(matrix)
    if values.ndim == 1:
        values = values.reshape(-1, 1)
    if values.ndim != 2 or values.shape[0] == 0 or values.shape[1] == 0:
        raise ValueError("A modal subspace must be a non-empty vector or matrix.")
    if not np.all(np.isfinite(values.real)) or not np.all(np.isfinite(values.imag)):
        raise ValueError("Modal subspace values must be finite.")

    basis, singular_values, _ = np.linalg.svd(values, full_matrices=False)
    if singular_values.size == 0 or singular_values[0] <= 0.0:
        raise ValueError("A modal subspace must contain at least one non-zero vector.")
    if relative_tolerance is None:
        tolerance = (
            max(values.shape)
            * np.finfo(singular_values.dtype).eps
            * singular_values[0]
        )
    else:
        if not math.isfinite(float(relative_tolerance)) or relative_tolerance < 0.0:
            raise ValueError("Subspace rank tolerance must be finite and non-negative.")
        tolerance = float(relative_tolerance) * singular_values[0]
    rank = int(np.count_nonzero(singular_values > tolerance))
    if rank == 0:
        raise ValueError("A modal subspace is numerically rank deficient.")
    return basis[:, :rank]


def _subspace_mac_details(
    phi: np.ndarray,
    psi: np.ndarray,
    relative_tolerance: Optional[float] = None,
) -> Tuple[float, int, int]:
    left = np.asarray(phi)
    right = np.asarray(psi)
    if left.ndim == 1:
        left = left.reshape(-1, 1)
    if right.ndim == 1:
        right = right.reshape(-1, 1)
    if left.ndim != 2 or right.ndim != 2 or left.shape[0] != right.shape[0]:
        raise ValueError("Modal subspaces must have the same ambient dimension.")

    q_phi = _orthonormal_basis(left, relative_tolerance)
    q_psi = _orthonormal_basis(right, relative_tolerance)
    canonical_correlations = np.linalg.svd(
        q_phi.conj().T @ q_psi, compute_uv=False
    )
    normalization = min(q_phi.shape[1], q_psi.shape[1])
    value = float(np.sum(canonical_correlations ** 2) / normalization)
    return float(np.clip(value, 0.0, 1.0)), q_phi.shape[1], q_psi.shape[1]


def subspace_mac(
    phi: np.ndarray,
    psi: np.ndarray,
    *,
    relative_tolerance: Optional[float] = None,
) -> float:
    """Return the mean squared canonical correlation of two column spaces.

    The columns of ``phi`` and ``psi`` are modal basis vectors. SVD supplies an
    orthonormal basis for each numerical column space. If ``sigma_i`` are the
    singular values of ``Q_phi.H @ Q_psi`` (the cosines of principal angles),
    this function returns ``sum(sigma_i**2) / min(rank(phi), rank(psi))``.
    Consequently the result is invariant to mode order, sign/phase, scaling,
    and any nonsingular change of basis within either subspace.
    """

    value, _, _ = _subspace_mac_details(phi, psi, relative_tolerance)
    return value


def _relative_frequency_spacing(left: float, right: float) -> float:
    return abs(float(right) - float(left)) / (0.5 * (float(left) + float(right)))


def _near_degenerate_components(
    pairs: Sequence[ModePairResult], relative_frequency_gap: float
) -> List[List[int]]:
    if not math.isfinite(float(relative_frequency_gap)) or not (
        0.0 <= float(relative_frequency_gap) < 1.0
    ):
        raise ValueError("Relative frequency gap must be finite and in [0, 1).")

    neighbours: List[set[int]] = [set() for _ in pairs]
    for left_index, left in enumerate(pairs):
        for right_index in range(left_index + 1, len(pairs)):
            right = pairs[right_index]
            fe_close = (
                _relative_frequency_spacing(
                    left.abaqus_frequency_hz, right.abaqus_frequency_hz
                )
                <= relative_frequency_gap
            )
            experimental_close = (
                _relative_frequency_spacing(
                    left.experimental_frequency_hz,
                    right.experimental_frequency_hz,
                )
                <= relative_frequency_gap
            )
            if fe_close and experimental_close:
                neighbours[left_index].add(right_index)
                neighbours[right_index].add(left_index)

    components: List[List[int]] = []
    unseen = set(range(len(pairs)))
    while unseen:
        start = min(unseen)
        stack = [start]
        component = []
        unseen.remove(start)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbour in sorted(neighbours[current], reverse=True):
                if neighbour in unseen:
                    unseen.remove(neighbour)
                    stack.append(neighbour)
        if len(component) > 1:
            components.append(component)
    return components


def _node_key(node_id: object) -> Tuple[str, str]:
    if isinstance(node_id, np.generic):
        node_id = node_id.item()
    return type(node_id).__name__, repr(node_id)


def _pair_dofs(
    pair: ModePairResult,
) -> Dict[Tuple[Hashable, int], Tuple[complex, complex]]:
    fe = np.asarray(pair.abaqus_vector)
    experimental = np.asarray(pair.experimental_vector)
    if fe.ndim != 2 or experimental.shape != fe.shape:
        raise ValueError("Each pair must provide equally shaped two-dimensional mode vectors.")

    measured = getattr(pair, "measured_dof_mask", None)
    if measured is None:
        measured = np.ones(fe.shape, dtype=bool)
    else:
        measured = np.asarray(measured, dtype=bool)
        if measured.shape != fe.shape:
            raise ValueError("A pair's measured-DOF mask must match its mode vectors.")
    finite = (
        np.isfinite(fe.real)
        & np.isfinite(fe.imag)
        & np.isfinite(experimental.real)
        & np.isfinite(experimental.imag)
    )
    usable = measured & finite

    node_ids = pair.node_ids
    if node_ids is None:
        coordinates = np.asarray(pair.coordinates, dtype=float)
        if coordinates.shape != (len(fe), 3) or not np.all(np.isfinite(coordinates)):
            raise ValueError(
                "A pair without node IDs requires one finite 3-D coordinate per row."
            )
        row_keys: Sequence[Hashable] = tuple(
            ("coordinate", tuple(float(value) for value in coordinate))
            for coordinate in coordinates
        )
    else:
        node_values = np.asarray(node_ids, dtype=object).reshape(-1)
        if len(node_values) != len(fe):
            raise ValueError("A pair's node IDs must match its mode-vector rows.")
        row_keys = tuple(_node_key(value) for value in node_values)

    values: Dict[Tuple[Hashable, int], Tuple[complex, complex]] = {}
    for row, row_key in enumerate(row_keys):
        for component in range(fe.shape[1]):
            if usable[row, component]:
                key = (row_key, component)
                if key in values:
                    raise ValueError("A pair contains duplicate node/component DOFs.")
                values[key] = (fe[row, component], experimental[row, component])
    return values


def _paired_subspace_mac(
    pairs: Sequence[ModePairResult],
) -> Tuple[float, int, int, int]:
    dof_maps = [_pair_dofs(pair) for pair in pairs]
    shared_dofs = set(dof_maps[0])
    for dof_map in dof_maps[1:]:
        shared_dofs.intersection_update(dof_map)
    if not shared_dofs:
        raise ValueError("Cluster members have no common measured finite DOFs.")

    ordered_dofs = sorted(shared_dofs, key=repr)
    phi = np.asarray(
        [[dof_map[dof][0] for dof_map in dof_maps] for dof in ordered_dofs]
    )
    psi = np.asarray(
        [[dof_map[dof][1] for dof_map in dof_maps] for dof in ordered_dofs]
    )
    value, fe_rank, experimental_rank = _subspace_mac_details(phi, psi)
    return value, len(ordered_dofs), fe_rank, experimental_rank


def _validate_observation_pair(
    observation: ModalObservation, pair: ModePairResult
) -> None:
    if (
        observation.fe_mode_id != pair.abaqus_mode
        or observation.experimental_mode_id != pair.experimental_mode
        or observation.fe_frequency_hz != pair.abaqus_frequency_hz
        or observation.experimental_frequency_hz != pair.experimental_frequency_hz
    ):
        raise ValueError("Observations must correspond to ComparisonResult pairs in order.")


def _cluster_inclusion(
    observations: Sequence[ModalObservation],
    subspace_value: Optional[float],
    unavailable_reason: str = "",
) -> Tuple[InclusionStatus, str]:
    if subspace_value is None:
        detail = unavailable_reason or "unknown numerical reason"
        return InclusionStatus.EXCLUDED, f"Subspace MAC unavailable: {detail}"
    excluded = [
        item.observation_id
        for item in observations
        if item.inclusion_status == InclusionStatus.EXCLUDED
    ]
    if excluded:
        return (
            InclusionStatus.EXCLUDED,
            "Source observations are excluded: " + ", ".join(excluded),
        )
    downweighted = [
        item.observation_id
        for item in observations
        if item.inclusion_status == InclusionStatus.DOWNWEIGHTED
    ]
    if downweighted:
        return (
            InclusionStatus.DOWNWEIGHTED,
            "Source observations are downweighted: " + ", ".join(downweighted),
        )
    return InclusionStatus.INCLUDED, "Near-degenerate cluster accepted from included source observations."


def detect_modal_clusters(
    comparison: ComparisonResult,
    observations: Sequence[ModalObservation],
    *,
    relative_frequency_gap: float | None = None,
) -> Tuple[ModalCluster, ...]:
    """Detect conservative FE-and-EXP close groups among existing paired modes.

    No absolute-Hz rule is applied. Two pair records are connected only if both
    their FE frequencies and their experimental frequencies satisfy the supplied
    relative-spacing threshold. Connected groups are returned as clusters;
    ungrouped modes remain ordinary ``ModalObservation`` records.
    """

    source_observations = tuple(observations)
    if len(source_observations) != len(comparison.pairs):
        raise ValueError("One source observation is required for every comparison pair.")
    for observation, pair in zip(source_observations, comparison.pairs):
        _validate_observation_pair(observation, pair)
    identities = {
        (item.physical_specimen_id, item.test_run_id) for item in source_observations
    }
    if len(identities) > 1:
        raise ValueError("Cluster detection cannot mix specimens or test runs.")
    if relative_frequency_gap is None:
        return ()

    clusters = []
    for component in _near_degenerate_components(
        comparison.pairs, relative_frequency_gap
    ):
        members = sorted(
            component,
            key=lambda index: (
                comparison.pairs[index].abaqus_mode,
                comparison.pairs[index].experimental_mode,
                source_observations[index].observation_id,
            ),
        )
        pairs = [comparison.pairs[index] for index in members]
        member_observations = [source_observations[index] for index in members]
        fe_frequencies = tuple(float(pair.abaqus_frequency_hz) for pair in pairs)
        experimental_frequencies = tuple(
            float(pair.experimental_frequency_hz) for pair in pairs
        )
        try:
            mac_value, shared_dof_count, fe_rank, experimental_rank = (
                _paired_subspace_mac(pairs)
            )
            unavailable_reason = ""
        except ValueError as error:
            mac_value = None
            shared_dof_count = 0
            fe_rank = 0
            experimental_rank = 0
            unavailable_reason = str(error)
        inclusion_status, reason = _cluster_inclusion(
            member_observations, mac_value, unavailable_reason
        )
        fe_mode_ids = tuple(int(pair.abaqus_mode) for pair in pairs)
        experimental_mode_ids = tuple(int(pair.experimental_mode) for pair in pairs)
        cluster_id = (
            f"{member_observations[0].physical_specimen_id}/"
            f"{member_observations[0].test_run_id}/cluster/"
            f"A{'-'.join(map(str, sorted(fe_mode_ids)))}/"
            f"E{'-'.join(map(str, sorted(experimental_mode_ids)))}"
        )
        clusters.append(
            ModalCluster(
                cluster_id=cluster_id,
                physical_specimen_id=member_observations[0].physical_specimen_id,
                test_run_id=member_observations[0].test_run_id,
                observation_ids=tuple(item.observation_id for item in member_observations),
                inclusion_status=inclusion_status,
                reason=reason,
                metadata={
                    "relative_frequency_gap": float(relative_frequency_gap),
                    "shared_dof_count": shared_dof_count,
                    "fe_subspace_rank": fe_rank,
                    "experimental_subspace_rank": experimental_rank,
                },
                fe_mode_ids=fe_mode_ids,
                experimental_mode_ids=experimental_mode_ids,
                fe_frequencies_hz=fe_frequencies,
                experimental_frequencies_hz=experimental_frequencies,
                subspace_mac=mac_value,
                frequency_residual=float(
                    np.mean(
                        np.log(
                            np.asarray(fe_frequencies)
                            / np.asarray(experimental_frequencies)
                        )
                    )
                ),
                fe_frequency_splitting_hz=max(fe_frequencies) - min(fe_frequencies),
                experimental_frequency_splitting_hz=(
                    max(experimental_frequencies) - min(experimental_frequencies)
                ),
            )
        )
    return tuple(clusters)


def cluster_comparison_result(
    comparison: ComparisonResult,
    design_id: str,
    physical_specimen_id: str,
    test_run_id: str,
    *,
    relative_frequency_gap: float | None = None,
) -> ModalClusterAnalysis:
    """Adapt current pairs and detect clusters without mutating the comparison."""

    observations = comparison_to_observations(
        comparison,
        design_id,
        physical_specimen_id,
        test_run_id,
    )
    clusters = detect_modal_clusters(
        comparison,
        observations,
        relative_frequency_gap=relative_frequency_gap,
    )
    return ModalClusterAnalysis(observations=observations, clusters=clusters)
