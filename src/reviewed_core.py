from __future__ import annotations

from itertools import permutations, product
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree

from modal_core import (
    ComparisonResult,
    GeometryMatch,
    ModalDataset,
    ModePairResult,
    ModeShape,
    modal_assurance_criterion,
)


FORBIDDEN_COST = 1.0e6
# Admissibility gates are the acceptance criterion. This deliberately high dummy
# cost makes every already-admissible physical pair preferable to two unmatched
# assignments; it is not a second hidden acceptance threshold.
UNMATCHED_COST = 1.15
GEOMETRY_CANDIDATE_LIMIT = 16
GEOMETRY_RMS_FACTOR = 1.5
GEOMETRY_RMS_ABSOLUTE_WINDOW = 1.0e-8
INFERRED_DOF_RELATIVE_NORM = 1.0e-6


def frequency_error_percent(calculated: float, experimental: float) -> float:
    """Signed frequency error: positive means the numerical model is stiffer/higher."""
    experimental_value = float(experimental)
    if not np.isfinite(experimental_value) or abs(experimental_value) <= 1.0e-30:
        raise ValueError("Experimental frequency must be finite and non-zero.")
    return (float(calculated) - experimental_value) / abs(experimental_value) * 100.0


def _node_lookup(mode: ModeShape) -> Dict[str, int]:
    cached = getattr(mode, "_node_index_cache", None)
    if cached is None:
        cached = {str(node_id): index for index, node_id in enumerate(mode.node_ids)}
        setattr(mode, "_node_index_cache", cached)
    return cached


def _map_rows(
    values: np.ndarray,
    source_mode: ModeShape,
    reference_node_ids: np.ndarray,
    fill_value,
    dtype,
) -> np.ndarray:
    lookup = _node_lookup(source_mode)
    output = np.full((len(reference_node_ids), 3), fill_value, dtype=dtype)
    source = np.asarray(values)
    for output_index, node_id in enumerate(reference_node_ids):
        source_index = lookup.get(str(node_id))
        if source_index is not None:
            output[output_index] = source[source_index]
    return output


def _vectors_on_nodes(mode: ModeShape, reference_node_ids: np.ndarray) -> np.ndarray:
    return _map_rows(
        mode.vectors,
        mode,
        reference_node_ids,
        np.nan + 0j,
        complex,
    )


def _explicit_measurement_mask(mode: ModeShape) -> Optional[np.ndarray]:
    mask = getattr(mode, "measured_dofs", None)
    if mask is None:
        mask = mode.metadata.get("measured_dofs")
    if mask is None:
        return None
    mask_array = np.asarray(mask, dtype=bool)
    if mask_array.shape == (3,):
        mask_array = np.broadcast_to(mask_array, mode.vectors.shape).copy()
    if mask_array.shape != mode.vectors.shape:
        return None
    return mask_array


def _measurement_mask_on_nodes(
    mode: ModeShape,
    reference_node_ids: np.ndarray,
) -> Optional[np.ndarray]:
    explicit = _explicit_measurement_mask(mode)
    if explicit is None:
        return None
    return _map_rows(explicit, mode, reference_node_ids, False, bool)


def experimental_measurement_mask(
    experimental_modes: Sequence[ModeShape],
    reference_node_ids: np.ndarray,
) -> np.ndarray:
    """Return the union of genuinely measured experimental DOFs.

    Explicit Testlab masks take precedence. When no explicit mask exists, a
    component is considered measured only when its norm exceeds 1e-6 of the
    complete modal-vector norm in at least one mode. This rejects curve-fitting
    round-off in nominally unmeasured directions.
    """
    union = np.zeros((len(reference_node_ids), 3), dtype=bool)
    inferred_vectors: List[np.ndarray] = []
    explicit_found = False

    for mode in experimental_modes:
        mapped_mask = _measurement_mask_on_nodes(mode, reference_node_ids)
        if mapped_mask is not None:
            union |= mapped_mask
            explicit_found = True
        inferred_vectors.append(_vectors_on_nodes(mode, reference_node_ids))

    if explicit_found:
        return union

    finite_any = np.zeros_like(union)
    for vectors in inferred_vectors:
        finite = np.isfinite(vectors.real) & np.isfinite(vectors.imag)
        finite_any |= finite
        amplitudes = np.where(finite, np.abs(vectors), 0.0)
        component_norms = np.sqrt(np.sum(amplitudes**2, axis=0))
        mode_norm = float(np.linalg.norm(component_norms))
        if mode_norm <= 1.0e-30:
            continue
        active_components = component_norms > mode_norm * INFERRED_DOF_RELATIVE_NORM
        union |= finite & active_components[np.newaxis, :]

    if not np.any(union):
        union = finite_any
    return union


def _geometry_center_radius(points: np.ndarray) -> Tuple[np.ndarray, float]:
    points = np.asarray(points, dtype=float)
    center = (np.min(points, axis=0) + np.max(points, axis=0)) / 2.0
    centered = points - center
    radius = float(np.sqrt(np.mean(np.sum(centered * centered, axis=1))))
    if radius <= 1.0e-30:
        raise ValueError("Geometry contains no spatial extent.")
    return center, radius


def _candidate_scales(
    abaqus: np.ndarray,
    experimental: np.ndarray,
    scale_override: Optional[float],
) -> List[float]:
    if scale_override is not None:
        value = float(scale_override)
        if not np.isfinite(value) or value <= 0.0:
            raise ValueError("Manual coordinate scale must be a positive number.")
        return [value]

    abaqus_span = np.sort(np.ptp(abaqus, axis=0))
    experimental_span = np.sort(np.ptp(experimental, axis=0))
    ratios = [
        float(e / a)
        for a, e in zip(abaqus_span, experimental_span)
        if a > 1.0e-30 and e > 1.0e-30
    ]
    if not ratios:
        _, abaqus_radius = _geometry_center_radius(abaqus)
        _, experimental_radius = _geometry_center_radius(experimental)
        ratios = [experimental_radius / abaqus_radius]

    baseline = float(np.median(ratios))
    candidates = [baseline]
    for unit_scale in (1.0e-6, 1.0e-3, 1.0, 1.0e3, 1.0e6):
        if 0.2 <= baseline / unit_scale <= 5.0:
            candidates.append(unit_scale)
    return sorted({round(value, 15) for value in candidates if value > 0.0})


def geometry_alignment_candidates(
    abaqus_coordinates: np.ndarray,
    experimental_coordinates: np.ndarray,
    tolerance_fraction: float = 0.03,
    coordinate_scale_override: Optional[float] = None,
) -> List[GeometryMatch]:
    """Return geometrically plausible signed-axis candidates.

    A single FE KD-tree is reused. Full transformed FE coordinates are not
    materialized for each candidate; only the selected candidate receives that
    array after modal evaluation.
    """
    abaqus = np.asarray(abaqus_coordinates, dtype=float)
    experimental = np.asarray(experimental_coordinates, dtype=float)
    if len(abaqus) < 3 or len(experimental) < 3:
        raise ValueError("At least three coordinates are required in both geometries.")

    abaqus_center, _ = _geometry_center_radius(abaqus)
    experimental_center, experimental_radius = _geometry_center_radius(experimental)
    centered_abaqus = abaqus - abaqus_center
    centered_experimental = experimental - experimental_center
    tree = cKDTree(centered_abaqus)
    experimental_span = max(
        float(np.linalg.norm(np.ptp(experimental, axis=0))),
        experimental_radius,
    )
    tolerance = max(experimental_span * tolerance_fraction, 1.0e-12)

    candidates: List[GeometryMatch] = []
    for coordinate_scale in _candidate_scales(
        abaqus,
        experimental,
        coordinate_scale_override,
    ):
        for permutation in permutations(range(3)):
            permutation_matrix = np.eye(3)[:, permutation]
            for signs in product((-1.0, 1.0), repeat=3):
                rotation = permutation_matrix @ np.diag(signs)
                query_points = (centered_experimental / coordinate_scale) @ rotation.T
                distances_local, indices = tree.query(query_points, k=1)
                distances = np.asarray(distances_local, dtype=float) * coordinate_scale
                normalized_rms = float(
                    np.sqrt(np.mean(distances**2)) / experimental_span
                )
                matched_fraction = float(np.mean(distances <= tolerance))
                translation = (
                    experimental_center
                    - abaqus_center @ rotation * coordinate_scale
                )
                candidates.append(
                    GeometryMatch(
                        experimental_to_abaqus=np.asarray(indices, dtype=int),
                        distances=distances,
                        rotation=rotation,
                        coordinate_scale=float(coordinate_scale),
                        translation=translation,
                        normalized_rms_distance=normalized_rms,
                        matched_fraction=matched_fraction,
                    )
                )

    candidates.sort(
        key=lambda item: (item.normalized_rms_distance, -item.matched_fraction)
    )
    if not candidates:
        raise RuntimeError("No geometry-alignment candidates were generated.")

    best_rms = candidates[0].normalized_rms_distance
    rms_limit = max(
        best_rms * GEOMETRY_RMS_FACTOR,
        best_rms + GEOMETRY_RMS_ABSOLUTE_WINDOW,
    )
    plausible = [
        candidate
        for candidate in candidates
        if candidate.normalized_rms_distance <= rms_limit
    ]
    return plausible[:GEOMETRY_CANDIDATE_LIMIT]


def _phase_align_masked(
    reference: np.ndarray,
    candidate: np.ndarray,
    mask: np.ndarray,
) -> np.ndarray:
    ref = np.asarray(reference, dtype=complex)[mask]
    cand = np.asarray(candidate, dtype=complex)[mask]
    denominator = np.vdot(cand, cand)
    if abs(denominator) <= 1.0e-30:
        return np.asarray(candidate)
    coefficient = np.vdot(cand, ref) / denominator
    if abs(coefficient) <= 1.0e-30:
        return np.asarray(candidate)
    return np.asarray(candidate) * (coefficient / abs(coefficient))


def _status(mac_value: Optional[float], signed_frequency_error: float) -> str:
    error = abs(signed_frequency_error)
    if mac_value is None:
        if error <= 5.0:
            return "Frequency match"
        if error <= 10.0:
            return "Check frequency"
        return "Large frequency difference"
    if mac_value >= 0.90 and error <= 5.0:
        return "Excellent match"
    if mac_value >= 0.80 and error <= 10.0:
        return "Good match"
    if mac_value >= 0.60 and error <= 15.0:
        return "Review"
    return "Poor match"


def _admissible_assignment(
    cost: np.ndarray,
    admissible: np.ndarray,
    unmatched_cost: float = UNMATCHED_COST,
) -> Tuple[np.ndarray, np.ndarray, float]:
    rows, columns = cost.shape
    size = rows + columns
    augmented = np.full((size, size), FORBIDDEN_COST, dtype=float)
    augmented[:rows, :columns] = np.where(admissible, cost, FORBIDDEN_COST)

    for row in range(rows):
        augmented[row, columns + row] = unmatched_cost
    for column in range(columns):
        augmented[rows + column, column] = unmatched_cost
    augmented[rows:, columns:] = 0.0

    assigned_rows, assigned_columns = linear_sum_assignment(augmented)
    accepted = [
        (row, column)
        for row, column in zip(assigned_rows, assigned_columns)
        if row < rows and column < columns and admissible[row, column]
    ]
    if accepted:
        accepted_rows = np.asarray([item[0] for item in accepted], dtype=int)
        accepted_columns = np.asarray([item[1] for item in accepted], dtype=int)
    else:
        accepted_rows = np.asarray([], dtype=int)
        accepted_columns = np.asarray([], dtype=int)
    normalized_cost = float(
        np.sum(augmented[assigned_rows, assigned_columns])
        / max(rows, columns, 1)
    )
    return accepted_rows, accepted_columns, normalized_cost


def _recalculate_order_changed(pairs: List[ModePairResult]) -> None:
    abaqus_order = sorted(
        pairs,
        key=lambda pair: (pair.abaqus_frequency_hz, pair.abaqus_mode),
    )
    experimental_order = sorted(
        pairs,
        key=lambda pair: (
            pair.experimental_frequency_hz,
            pair.experimental_mode,
        ),
    )
    experimental_rank = {
        id(pair): index for index, pair in enumerate(experimental_order)
    }
    for index, pair in enumerate(abaqus_order):
        pair.order_changed = experimental_rank[id(pair)] != index


def _rotated_abaqus_modes(
    abaqus_modes: Sequence[ModeShape],
    mapped_abaqus_ids: np.ndarray,
    rotation: np.ndarray,
) -> List[np.ndarray]:
    return [
        _vectors_on_nodes(mode, mapped_abaqus_ids) @ rotation
        for mode in abaqus_modes
    ]


def _mac_matrix_for_geometry(
    abaqus_rotated_modes: Sequence[np.ndarray],
    experimental_vectors: Sequence[np.ndarray],
    measurement_mask: np.ndarray,
) -> np.ndarray:
    matrix = np.full(
        (len(abaqus_rotated_modes), len(experimental_vectors)),
        np.nan,
        dtype=float,
    )
    for row, abaqus_rotated in enumerate(abaqus_rotated_modes):
        for column, experimental_values in enumerate(experimental_vectors):
            finite = (
                np.isfinite(abaqus_rotated.real)
                & np.isfinite(abaqus_rotated.imag)
                & np.isfinite(experimental_values.real)
                & np.isfinite(experimental_values.imag)
            )
            dof_mask = measurement_mask & finite
            if np.any(dof_mask):
                value = modal_assurance_criterion(
                    abaqus_rotated[dof_mask],
                    experimental_values[dof_mask],
                )
            else:
                value = None
            matrix[row, column] = np.nan if value is None else value
    return matrix


def _copy_dataset(dataset: ModalDataset) -> ModalDataset:
    return ModalDataset(
        source_name=dataset.source_name,
        source_path=dataset.source_path,
        modes=list(dataset.modes),
        metadata=dict(dataset.metadata),
        history=list(dataset.history),
    )


def compare_modal_datasets(
    abaqus: ModalDataset,
    experimental: ModalDataset,
    mac_weight: float = 0.75,
    frequency_weight: float = 0.25,
    maximum_frequency_error_percent: float = 15.0,
    minimum_mac: float = 0.50,
    maximum_frequency_only_error_percent: float = 10.0,
    coordinate_scale_override: Optional[float] = None,
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

    signed_frequency_matrix = np.zeros(
        (len(abaqus_modes), len(experimental_modes)),
        dtype=float,
    )
    for row, abaqus_mode in enumerate(abaqus_modes):
        for column, experimental_mode in enumerate(experimental_modes):
            signed_frequency_matrix[row, column] = frequency_error_percent(
                abaqus_mode.frequency_hz,
                experimental_mode.frequency_hz,
            )
    absolute_frequency_matrix = np.abs(signed_frequency_matrix)

    experimental_vectors = [
        _vectors_on_nodes(mode, experimental_node_ids)
        for mode in experimental_modes
    ]
    measurement_mask = experimental_measurement_mask(
        experimental_modes,
        experimental_node_ids,
    )
    if not np.any(measurement_mask):
        raise ValueError("No measured experimental degrees of freedom were detected.")

    candidates = geometry_alignment_candidates(
        abaqus_reference.coordinates,
        experimental_coordinates,
        coordinate_scale_override=coordinate_scale_override,
    )
    best_evaluation = None

    for geometry in candidates:
        mapped_abaqus_ids = abaqus_reference.node_ids[
            geometry.experimental_to_abaqus
        ]
        abaqus_rotated_modes = _rotated_abaqus_modes(
            abaqus_modes,
            mapped_abaqus_ids,
            geometry.rotation,
        )
        mac_matrix = _mac_matrix_for_geometry(
            abaqus_rotated_modes,
            experimental_vectors,
            measurement_mask,
        )

        mac_available = np.isfinite(mac_matrix)
        admissible = (
            absolute_frequency_matrix <= maximum_frequency_error_percent
        )
        admissible &= np.where(
            mac_available,
            mac_matrix >= minimum_mac,
            absolute_frequency_matrix <= maximum_frequency_only_error_percent,
        )

        mac_cost = 1.0 - np.nan_to_num(mac_matrix, nan=0.0)
        frequency_cost = np.minimum(
            absolute_frequency_matrix / 20.0,
            5.0,
        )
        cost = mac_weight * mac_cost + frequency_weight * frequency_cost
        rows, columns, assignment_cost = _admissible_assignment(
            cost,
            admissible,
        )
        geometry_penalty = (
            3.0 * geometry.normalized_rms_distance
            + 0.5 * (1.0 - geometry.matched_fraction)
        )
        score = (
            -len(rows),
            assignment_cost + geometry_penalty,
        )
        evaluation = (
            score,
            geometry,
            mac_matrix,
            rows,
            columns,
        )
        if best_evaluation is None or score < best_evaluation[0]:
            best_evaluation = evaluation

    if best_evaluation is None:
        raise RuntimeError(
            "No valid geometry and modal alignment could be calculated."
        )

    (
        _,
        geometry,
        mac_matrix,
        abaqus_indices,
        experimental_indices,
    ) = best_evaluation

    geometry.transformed_abaqus_coordinates = (
        abaqus_reference.coordinates
        @ geometry.rotation
        * geometry.coordinate_scale
        + geometry.translation
    )
    mapped_abaqus_ids = abaqus_reference.node_ids[
        geometry.experimental_to_abaqus
    ]
    winning_abaqus_vectors = _rotated_abaqus_modes(
        abaqus_modes,
        mapped_abaqus_ids,
        geometry.rotation,
    )

    pairs: List[ModePairResult] = []
    for row, column in sorted(
        zip(abaqus_indices, experimental_indices),
        key=lambda item: abaqus_modes[item[0]].frequency_hz,
    ):
        abaqus_mode = abaqus_modes[row]
        experimental_mode = experimental_modes[column]
        abaqus_rotated = winning_abaqus_vectors[row]
        experimental_values = experimental_vectors[column]
        finite = (
            np.isfinite(abaqus_rotated.real)
            & np.isfinite(abaqus_rotated.imag)
            & np.isfinite(experimental_values.real)
            & np.isfinite(experimental_values.imag)
        )
        dof_mask = measurement_mask & finite
        valid_rows = np.any(dof_mask, axis=1)
        a = abaqus_rotated[valid_rows]
        e = experimental_values[valid_rows]
        local_mask = dof_mask[valid_rows]
        coordinates = experimental_coordinates[valid_rows]

        mac_value = (
            None
            if not np.isfinite(mac_matrix[row, column])
            else float(mac_matrix[row, column])
        )
        signed_error = float(signed_frequency_matrix[row, column])
        aligned_a = _phase_align_masked(e, a, local_mask)
        pair = ModePairResult(
            abaqus_mode=abaqus_mode.number,
            experimental_mode=experimental_mode.number,
            abaqus_frequency_hz=abaqus_mode.frequency_hz,
            experimental_frequency_hz=experimental_mode.frequency_hz,
            frequency_error_percent=signed_error,
            mac=mac_value,
            status=_status(mac_value, signed_error),
            order_changed=False,
            mapped_points=int(np.count_nonzero(np.any(local_mask, axis=1))),
            abaqus_vector=np.asarray(aligned_a),
            experimental_vector=np.asarray(e),
            coordinates=np.asarray(coordinates),
        )
        setattr(pair, "measured_dof_mask", np.asarray(local_mask, dtype=bool))
        setattr(
            pair,
            "measured_dof_count",
            int(np.count_nonzero(local_mask)),
        )
        pairs.append(pair)

    _recalculate_order_changed(pairs)

    warnings: List[str] = []
    if geometry.matched_fraction < 0.90:
        warnings.append(
            f"Only {geometry.matched_fraction:.1%} of experimental points are "
            "within the automatic geometry tolerance."
        )
    if geometry.normalized_rms_distance > 0.03:
        warnings.append(
            f"Geometry alignment RMS is "
            f"{geometry.normalized_rms_distance:.2%} "
            "of the test-model diagonal."
        )
    unique_nodes = len(np.unique(geometry.experimental_to_abaqus))
    if unique_nodes < len(geometry.experimental_to_abaqus):
        warnings.append(
            f"{len(geometry.experimental_to_abaqus) - unique_nodes} "
            "experimental point(s) map to already-used Abaqus nodes; "
            "MAC weighting may be locally duplicated."
        )

    determinant = float(np.linalg.det(geometry.rotation))
    selected_transform = {
        "coordinate_scale": geometry.coordinate_scale,
        "rotation": geometry.rotation.tolist(),
        "translation": geometry.translation.tolist(),
        "determinant": determinant,
        "mirrored": determinant < 0.0,
        "unique_mapped_abaqus_nodes": unique_nodes,
        "experimental_point_count": len(
            geometry.experimental_to_abaqus
        ),
    }
    result_abaqus = _copy_dataset(abaqus)
    result_abaqus.metadata["selected_geometry_transform"] = selected_transform

    if determinant < 0.0:
        warnings.append(
            "The selected coordinate transformation includes a reflection "
            "(determinant -1). Verify axis signs and specimen orientation."
        )
    if not pairs:
        raise ValueError(
            "No admissible one-to-one mode pairs satisfy the frequency and MAC limits."
        )

    return ComparisonResult(
        abaqus=result_abaqus,
        experimental=experimental,
        geometry=geometry,
        pairs=pairs,
        mac_matrix=mac_matrix,
        frequency_error_matrix=signed_frequency_matrix,
        abaqus_mode_numbers=[mode.number for mode in abaqus_modes],
        experimental_mode_numbers=[
            mode.number for mode in experimental_modes
        ],
        warnings=warnings,
        metadata={
            "selected_geometry_transform": selected_transform,
            "evaluated_geometry_candidate_count": len(candidates),
            "measurement_mask_relative_norm_threshold": (
                INFERRED_DOF_RELATIVE_NORM
            ),
        },
    )
