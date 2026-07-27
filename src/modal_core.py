from __future__ import annotations

from dataclasses import dataclass, field
from itertools import permutations, product
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree


@dataclass
class ModeShape:
    number: int
    frequency_hz: float
    node_ids: np.ndarray
    coordinates: np.ndarray
    vectors: np.ndarray
    damping_ratio: Optional[float] = None
    modal_mass: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.node_ids = np.asarray(self.node_ids, dtype=object)
        self.coordinates = np.asarray(self.coordinates, dtype=float)
        self.vectors = np.asarray(self.vectors)

        if self.coordinates.ndim != 2 or self.coordinates.shape[1] != 3:
            raise ValueError("Mode coordinates must have shape (N, 3).")
        if self.vectors.ndim != 2 or self.vectors.shape[1] != 3:
            raise ValueError("Mode vectors must have shape (N, 3).")
        if len(self.node_ids) != len(self.coordinates) or len(self.node_ids) != len(self.vectors):
            raise ValueError("Node ids, coordinates, and vectors must have equal lengths.")
        if not np.isfinite(self.frequency_hz) or self.frequency_hz <= 0:
            raise ValueError("Mode frequency must be a positive finite value.")


@dataclass
class ModalDataset:
    source_name: str
    source_path: Path
    modes: List[ModeShape]
    metadata: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)

    def sorted_modes(self) -> List[ModeShape]:
        return sorted(self.modes, key=lambda mode: mode.number)


@dataclass
class GeometryMatch:
    experimental_to_abaqus: np.ndarray
    distances: np.ndarray
    transformed_abaqus_coordinates: np.ndarray
    rotation: np.ndarray
    coordinate_scale: float
    translation: np.ndarray
    normalized_rms_distance: float
    matched_fraction: float


@dataclass
class ModePairResult:
    abaqus_mode: int
    experimental_mode: int
    abaqus_frequency_hz: float
    experimental_frequency_hz: float
    frequency_error_percent: float
    mac: Optional[float]
    status: str
    order_changed: bool
    mapped_points: int
    abaqus_vector: np.ndarray
    experimental_vector: np.ndarray
    coordinates: np.ndarray


@dataclass
class ComparisonResult:
    abaqus: ModalDataset
    experimental: ModalDataset
    geometry: GeometryMatch
    pairs: List[ModePairResult]
    mac_matrix: np.ndarray
    frequency_error_matrix: np.ndarray
    abaqus_mode_numbers: List[int]
    experimental_mode_numbers: List[int]
    warnings: List[str] = field(default_factory=list)


def frequency_error_percent(calculated: float, experimental: float) -> float:
    return abs(float(calculated) - float(experimental)) / abs(float(experimental)) * 100.0


def modal_assurance_criterion(vector_a: np.ndarray, vector_b: np.ndarray) -> Optional[float]:
    a = np.asarray(vector_a).reshape(-1)
    b = np.asarray(vector_b).reshape(-1)

    valid = np.isfinite(a.real) & np.isfinite(a.imag) & np.isfinite(b.real) & np.isfinite(b.imag)
    a = a[valid]
    b = b[valid]

    if a.size == 0 or b.size == 0:
        return None

    norm_a = np.vdot(a, a).real
    norm_b = np.vdot(b, b).real
    if norm_a <= 1e-30 or norm_b <= 1e-30:
        return None

    value = abs(np.vdot(a, b)) ** 2 / (norm_a * norm_b)
    return float(np.clip(value.real, 0.0, 1.0))


def phase_align(reference: np.ndarray, candidate: np.ndarray) -> np.ndarray:
    ref = np.asarray(reference).reshape(-1)
    cand = np.asarray(candidate).reshape(-1)
    denominator = np.vdot(cand, cand)
    if abs(denominator) <= 1e-30:
        return np.asarray(candidate)
    coefficient = np.vdot(cand, ref) / denominator
    if abs(coefficient) <= 1e-30:
        return np.asarray(candidate)
    phase = coefficient / abs(coefficient)
    return np.asarray(candidate) * phase


def _principal_basis(points: np.ndarray) -> Tuple[np.ndarray, np.ndarray, float]:
    points = np.asarray(points, dtype=float)
    center = (np.min(points, axis=0) + np.max(points, axis=0)) / 2.0
    centered = points - center
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    basis = vt.T
    radius = float(np.sqrt(np.mean(np.sum(centered * centered, axis=1))))
    if radius <= 1e-30:
        raise ValueError("Geometry contains no spatial extent.")
    return center, basis, radius


def geometry_alignment_candidates(
    abaqus_coordinates: np.ndarray,
    experimental_coordinates: np.ndarray,
    tolerance_fraction: float = 0.03,
) -> List[GeometryMatch]:
    """Return signed-axis-permutation alignment candidates sorted by geometry error."""
    abaqus = np.asarray(abaqus_coordinates, dtype=float)
    experimental = np.asarray(experimental_coordinates, dtype=float)

    if len(abaqus) < 3:
        raise ValueError("At least three Abaqus coordinates are required.")
    if len(experimental) < 3:
        raise ValueError("At least three experimental coordinates are required.")

    ca, _, ra = _principal_basis(abaqus)
    ce, _, re = _principal_basis(experimental)
    abaqus_span = float(np.linalg.norm(np.ptp(abaqus, axis=0)))
    experimental_span = float(np.linalg.norm(np.ptp(experimental, axis=0)))
    coordinate_scale = experimental_span / abaqus_span if abaqus_span > 1e-30 else re / ra
    centered_a = abaqus - ca
    span = experimental_span if experimental_span > 1e-30 else re
    tolerance = max(span * tolerance_fraction, 1e-12)

    candidates: List[GeometryMatch] = []
    for permutation in permutations(range(3)):
        permutation_matrix = np.eye(3)[:, permutation]
        for signs in product((-1.0, 1.0), repeat=3):
            rotation = permutation_matrix @ np.diag(signs)
            transformed = centered_a @ rotation * coordinate_scale + ce
            tree = cKDTree(transformed)
            distances, indices = tree.query(experimental, k=1)
            normalized_rms = float(np.sqrt(np.mean(distances**2)) / span)
            matched_fraction = float(np.mean(distances <= tolerance))
            translation = ce - ca @ rotation * coordinate_scale
            candidates.append(
                GeometryMatch(
                    experimental_to_abaqus=np.asarray(indices, dtype=int),
                    distances=np.asarray(distances, dtype=float),
                    transformed_abaqus_coordinates=transformed,
                    rotation=rotation,
                    coordinate_scale=float(coordinate_scale),
                    translation=translation,
                    normalized_rms_distance=normalized_rms,
                    matched_fraction=matched_fraction,
                )
            )

    candidates.sort(key=lambda item: (item.normalized_rms_distance, -item.matched_fraction))
    return candidates


def align_geometries(
    abaqus_coordinates: np.ndarray,
    experimental_coordinates: np.ndarray,
    tolerance_fraction: float = 0.03,
) -> GeometryMatch:
    """Return the best geometry-only alignment candidate."""
    return geometry_alignment_candidates(
        abaqus_coordinates, experimental_coordinates, tolerance_fraction
    )[0]


def _mode_vectors_on_reference_nodes(mode: ModeShape, reference_node_ids: np.ndarray) -> np.ndarray:
    lookup = {str(node_id): index for index, node_id in enumerate(mode.node_ids)}
    output = np.full((len(reference_node_ids), 3), np.nan + 0j, dtype=complex)
    for output_index, node_id in enumerate(reference_node_ids):
        source_index = lookup.get(str(node_id))
        if source_index is not None:
            output[output_index] = mode.vectors[source_index]
    return output


def _status(mac_value: Optional[float], frequency_error: float) -> str:
    if mac_value is None:
        if frequency_error <= 5.0:
            return "Frequency match"
        if frequency_error <= 10.0:
            return "Check frequency"
        return "Large frequency difference"

    if mac_value >= 0.90 and frequency_error <= 5.0:
        return "Excellent match"
    if mac_value >= 0.80 and frequency_error <= 10.0:
        return "Good match"
    if mac_value >= 0.60 and frequency_error <= 15.0:
        return "Review"
    return "Poor match"


def compare_modal_datasets(
    abaqus: ModalDataset,
    experimental: ModalDataset,
    mac_weight: float = 0.75,
    frequency_weight: float = 0.25,
) -> ComparisonResult:
    abaqus_modes = abaqus.sorted_modes()
    experimental_modes = experimental.sorted_modes()

    if not abaqus_modes:
        raise ValueError("No Abaqus modes are available.")
    if not experimental_modes:
        raise ValueError("No experimental modes are available.")

    abaqus_reference = abaqus_modes[0]
    experimental_reference = experimental_modes[0]
    experimental_node_ids = experimental_reference.node_ids
    experimental_coordinates = experimental_reference.coordinates

    frequency_matrix = np.zeros((len(abaqus_modes), len(experimental_modes)), dtype=float)
    for i, abaqus_mode in enumerate(abaqus_modes):
        for j, experimental_mode in enumerate(experimental_modes):
            frequency_matrix[i, j] = frequency_error_percent(
                abaqus_mode.frequency_hz,
                experimental_mode.frequency_hz,
            )

    best_evaluation = None
    candidates = geometry_alignment_candidates(
        abaqus_reference.coordinates,
        experimental_reference.coordinates,
    )

    for geometry in candidates:
        mapped_abaqus_ids = abaqus_reference.node_ids[geometry.experimental_to_abaqus]
        mac_matrix = np.full((len(abaqus_modes), len(experimental_modes)), np.nan, dtype=float)
        mapped_vectors: Dict[Tuple[int, int], Tuple[np.ndarray, np.ndarray, np.ndarray]] = {}

        for i, abaqus_mode in enumerate(abaqus_modes):
            abaqus_all = _mode_vectors_on_reference_nodes(abaqus_mode, mapped_abaqus_ids)
            abaqus_rotated = abaqus_all @ geometry.rotation

            for j, experimental_mode in enumerate(experimental_modes):
                experimental_vectors = _mode_vectors_on_reference_nodes(
                    experimental_mode, experimental_node_ids
                )
                valid_rows = (
                    np.all(
                        np.isfinite(abaqus_rotated.real)
                        & np.isfinite(abaqus_rotated.imag),
                        axis=1,
                    )
                    & np.all(
                        np.isfinite(experimental_vectors.real)
                        & np.isfinite(experimental_vectors.imag),
                        axis=1,
                    )
                )
                a = abaqus_rotated[valid_rows]
                e = experimental_vectors[valid_rows]
                mapped_vectors[(i, j)] = (
                    a,
                    e,
                    experimental_coordinates[valid_rows],
                )
                mac_value = None if len(a) == 0 else modal_assurance_criterion(a, e)
                mac_matrix[i, j] = np.nan if mac_value is None else mac_value

        if np.all(np.isnan(mac_matrix)):
            cost = np.minimum(frequency_matrix / 20.0, 5.0)
        else:
            mac_cost = 1.0 - np.nan_to_num(mac_matrix, nan=0.0)
            frequency_cost = np.minimum(frequency_matrix / 20.0, 5.0)
            cost = mac_weight * mac_cost + frequency_weight * frequency_cost

        abaqus_indices, experimental_indices = linear_sum_assignment(cost)
        assignment_cost = float(np.mean(cost[abaqus_indices, experimental_indices]))
        geometry_penalty = (
            3.0 * geometry.normalized_rms_distance
            + 0.5 * (1.0 - geometry.matched_fraction)
        )
        total_score = assignment_cost + geometry_penalty

        evaluation = (
            total_score,
            geometry,
            mac_matrix,
            mapped_vectors,
            abaqus_indices,
            experimental_indices,
        )
        if best_evaluation is None or total_score < best_evaluation[0]:
            best_evaluation = evaluation

    if best_evaluation is None:
        raise RuntimeError("No valid geometry and modal alignment could be calculated.")

    (
        _,
        geometry,
        mac_matrix,
        mapped_vectors,
        abaqus_indices,
        experimental_indices,
    ) = best_evaluation

    abaqus_rank = {
        mode.number: rank
        for rank, mode in enumerate(
            sorted(abaqus_modes, key=lambda item: item.frequency_hz), start=1
        )
    }
    experimental_rank = {
        mode.number: rank
        for rank, mode in enumerate(
            sorted(experimental_modes, key=lambda item: item.frequency_hz), start=1
        )
    }

    pairs: List[ModePairResult] = []
    for i, j in sorted(
        zip(abaqus_indices, experimental_indices),
        key=lambda item: abaqus_modes[item[0]].number,
    ):
        abaqus_mode = abaqus_modes[i]
        experimental_mode = experimental_modes[j]
        a, e, pair_coordinates = mapped_vectors[(i, j)]
        mac_value = None if np.isnan(mac_matrix[i, j]) else float(mac_matrix[i, j])
        error = float(frequency_matrix[i, j])
        aligned_a = phase_align(e, a)

        pairs.append(
            ModePairResult(
                abaqus_mode=abaqus_mode.number,
                experimental_mode=experimental_mode.number,
                abaqus_frequency_hz=abaqus_mode.frequency_hz,
                experimental_frequency_hz=experimental_mode.frequency_hz,
                frequency_error_percent=error,
                mac=mac_value,
                status=_status(mac_value, error),
                order_changed=(
                    abaqus_rank[abaqus_mode.number]
                    != experimental_rank[experimental_mode.number]
                ),
                mapped_points=len(a),
                abaqus_vector=np.asarray(aligned_a),
                experimental_vector=np.asarray(e),
                coordinates=np.asarray(pair_coordinates),
            )
        )

    warnings: List[str] = []
    if geometry.matched_fraction < 0.90:
        warnings.append(
            f"Only {geometry.matched_fraction:.1%} of experimental points are within the automatic geometry tolerance."
        )
    if geometry.normalized_rms_distance > 0.03:
        warnings.append(
            f"Geometry alignment RMS is {geometry.normalized_rms_distance:.2%} of the test-model diagonal."
        )
    if np.all(np.isnan(mac_matrix)):
        warnings.append("MAC could not be calculated; mode pairing used frequencies only.")

    return ComparisonResult(
        abaqus=abaqus,
        experimental=experimental,
        geometry=geometry,
        pairs=pairs,
        mac_matrix=mac_matrix,
        frequency_error_matrix=frequency_matrix,
        abaqus_mode_numbers=[mode.number for mode in abaqus_modes],
        experimental_mode_numbers=[mode.number for mode in experimental_modes],
        warnings=warnings,
    )
