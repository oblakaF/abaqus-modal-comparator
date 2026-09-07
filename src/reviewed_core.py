from __future__ import annotations

from itertools import permutations, product
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree

from modal_core import (
    ComparisonResult,
    GeometryMatch,
    ModalDataset,
    ModeCandidateDiagnostic,
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

# ROADMAP Stage 2 #4: minimum common-DOF and spatial-coverage gates.
#
# These are deliberately a sanity floor, not a calibrated acceptance boundary.
# The only real dataset available to calibrate against (docs/baseline/stage0_baseline.json,
# a full 121-point single-LOS-direction Polytec scan) is fully degenerate for this
# purpose: every one of its 8 accepted pairs retains 100% of common DOF, points,
# and spatial extent, so there is no marginal example to learn a real threshold
# from. Until partial/sparse-grid fixtures exist (ROADMAP Stage 6), these values
# are set low enough to act as diagnostics that flag only near-total coverage
# failure (near-empty overlap, a handful of points, or points clustered in one
# corner) rather than to reject anything resembling normal modal-test coverage.
MINIMUM_COMMON_DOF_COUNT = 3
MINIMUM_UNIQUE_POINT_COUNT = 3
MINIMUM_MEASURED_DOF_COVERAGE_FRACTION = 0.05
MINIMUM_POINT_COVERAGE_FRACTION = 0.02
MINIMUM_SPATIAL_EXTENT_FRACTION = 0.02


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


def _inferred_measurement_mask(vectors: np.ndarray) -> np.ndarray:
    """Infer one mode's own measured DOFs from its own vector energy alone.

    A component is considered measured only when its norm exceeds 1e-6 of the
    complete modal-vector norm, in this mode's own vector only -- never
    borrowed from another mode's energy, which would reintroduce the same
    cross-mode leak this function exists to avoid (ROADMAP Stage 2 #3).
    """
    finite = np.isfinite(vectors.real) & np.isfinite(vectors.imag)
    amplitudes = np.where(finite, np.abs(vectors), 0.0)
    component_norms = np.sqrt(np.sum(amplitudes**2, axis=0))
    mode_norm = float(np.linalg.norm(component_norms))
    if mode_norm <= 1.0e-30:
        # No explicit mask and no measurable energy anywhere in this mode's
        # own vector: there is no reliable basis to say anything was
        # measured. Falling back to "everything finite counts as measured"
        # would silently trust every DOF of a mode that is entirely zero
        # (ROADMAP Stage 2 #3).
        return np.zeros_like(finite)
    active_components = component_norms > mode_norm * INFERRED_DOF_RELATIVE_NORM
    return finite & active_components[np.newaxis, :]


def experimental_measurement_masks(
    experimental_modes: Sequence[ModeShape],
    reference_node_ids: np.ndarray,
) -> List[np.ndarray]:
    """Return each experimental mode's own measured-DOF mask, mapped onto the
    reference node order -- never a mask shared or unioned across modes.

    An explicit Testlab mask takes precedence for a mode that has one. A mode
    without an explicit mask falls back to _inferred_measurement_mask using
    only that mode's own vector (ROADMAP Stage 2 #3: "a channel present in
    one mode" must not be "treated as measured in another mode").
    """
    masks: List[np.ndarray] = []
    for mode in experimental_modes:
        explicit = _measurement_mask_on_nodes(mode, reference_node_ids)
        if explicit is not None:
            masks.append(explicit)
            continue
        masks.append(_inferred_measurement_mask(_vectors_on_nodes(mode, reference_node_ids)))
    return masks


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


class _CoverageReport(NamedTuple):
    common_dof_count: int
    unique_point_count: int
    dof_coverage_fraction: float
    point_coverage_fraction: float
    spatial_coverage_fraction: float
    status: str


def _coverage_report(
    dof_mask: np.ndarray,
    own_measured_dof_count: int,
    coordinates: np.ndarray,
    full_grid_point_count: int,
    full_grid_extent: float,
) -> _CoverageReport:
    """ROADMAP Stage 2 #4 coverage gate/diagnostics (see the module-level
    threshold comment for why these are a soft sanity floor, not a
    calibrated cutoff). Status values match ROADMAP.md: "accepted",
    "insufficient DOF coverage", "insufficient point coverage",
    "insufficient spatial coverage"."""
    common_dof_count = int(np.count_nonzero(dof_mask))
    valid_rows = np.any(dof_mask, axis=1)
    unique_point_count = int(np.count_nonzero(valid_rows))
    dof_coverage_fraction = (
        common_dof_count / own_measured_dof_count if own_measured_dof_count else 0.0
    )
    point_coverage_fraction = (
        unique_point_count / full_grid_point_count if full_grid_point_count else 0.0
    )
    if full_grid_extent > 0.0 and unique_point_count >= 2:
        spatial_coverage_fraction = float(
            np.linalg.norm(
                coordinates[valid_rows].max(axis=0) - coordinates[valid_rows].min(axis=0)
            )
        ) / full_grid_extent
    else:
        spatial_coverage_fraction = 0.0

    if common_dof_count < MINIMUM_COMMON_DOF_COUNT or (
        own_measured_dof_count and dof_coverage_fraction < MINIMUM_MEASURED_DOF_COVERAGE_FRACTION
    ):
        status = "insufficient DOF coverage"
    elif unique_point_count < MINIMUM_UNIQUE_POINT_COUNT or (
        full_grid_point_count and point_coverage_fraction < MINIMUM_POINT_COVERAGE_FRACTION
    ):
        status = "insufficient point coverage"
    elif full_grid_extent > 0.0 and spatial_coverage_fraction < MINIMUM_SPATIAL_EXTENT_FRACTION:
        status = "insufficient spatial coverage"
    else:
        status = "accepted"

    return _CoverageReport(
        common_dof_count,
        unique_point_count,
        dof_coverage_fraction,
        point_coverage_fraction,
        spatial_coverage_fraction,
        status,
    )


def _mac_matrix_for_geometry(
    abaqus_rotated_modes: Sequence[np.ndarray],
    experimental_vectors: Sequence[np.ndarray],
    measurement_masks: Sequence[np.ndarray],
    experimental_coordinates: np.ndarray,
    full_grid_point_count: int,
    full_grid_extent: float,
) -> Tuple[np.ndarray, np.ndarray, List[List[_CoverageReport]]]:
    """Return MAC, coverage gate, and coverage-report matrices.

    ``coverage_admissible_matrix``
    is a boolean gate: a cell below the Stage 2 #4 coverage floor must not
    participate in Hungarian assignment as a valid candidate, independent of
    its MAC/frequency admissibility."""
    shape = (len(abaqus_rotated_modes), len(experimental_vectors))
    mac_matrix = np.full(shape, np.nan, dtype=float)
    coverage_admissible = np.zeros(shape, dtype=bool)
    coverage_reports: List[List[_CoverageReport]] = [
        [None] * shape[1] for _ in range(shape[0])
    ]  # type: ignore[list-item]
    own_measured_dof_counts = [int(np.count_nonzero(mask)) for mask in measurement_masks]

    for row, abaqus_rotated in enumerate(abaqus_rotated_modes):
        for column, experimental_values in enumerate(experimental_vectors):
            finite = (
                np.isfinite(abaqus_rotated.real)
                & np.isfinite(abaqus_rotated.imag)
                & np.isfinite(experimental_values.real)
                & np.isfinite(experimental_values.imag)
            )
            # This experimental mode's own mask only -- never another
            # column's (ROADMAP Stage 2 #3).
            dof_mask = measurement_masks[column] & finite
            coverage = _coverage_report(
                dof_mask,
                own_measured_dof_counts[column],
                experimental_coordinates,
                full_grid_point_count,
                full_grid_extent,
            )
            coverage_reports[row][column] = coverage
            coverage_admissible[row, column] = coverage.status == "accepted"
            if np.any(dof_mask):
                value = modal_assurance_criterion(
                    abaqus_rotated[dof_mask],
                    experimental_values[dof_mask],
                )
            else:
                value = None
            mac_matrix[row, column] = np.nan if value is None else value
    return mac_matrix, coverage_admissible, coverage_reports


def _copy_dataset(dataset: ModalDataset) -> ModalDataset:
    return ModalDataset(
        source_name=dataset.source_name,
        source_path=dataset.source_path,
        modes=list(dataset.modes),
        metadata=dict(dataset.metadata),
        history=list(dataset.history),
    )


def _frequency_error_matrices(
    abaqus_modes: Sequence[ModeShape],
    experimental_modes: Sequence[ModeShape],
) -> Tuple[np.ndarray, np.ndarray]:
    """Return (signed, absolute) Abaqus-rows x experimental-columns error matrices."""
    signed = np.zeros((len(abaqus_modes), len(experimental_modes)), dtype=float)
    for row, abaqus_mode in enumerate(abaqus_modes):
        for column, experimental_mode in enumerate(experimental_modes):
            signed[row, column] = frequency_error_percent(
                abaqus_mode.frequency_hz,
                experimental_mode.frequency_hz,
            )
    return signed, np.abs(signed)


def _experimental_vectors_and_mask(
    experimental_modes: Sequence[ModeShape],
    experimental_node_ids: np.ndarray,
) -> Tuple[List[np.ndarray], List[np.ndarray]]:
    """Return per-mode vectors mapped onto the reference node order, plus each
    mode's own measured-DOF mask (never unioned across modes)."""
    experimental_vectors = [
        _vectors_on_nodes(mode, experimental_node_ids)
        for mode in experimental_modes
    ]
    measurement_masks = experimental_measurement_masks(
        experimental_modes,
        experimental_node_ids,
    )
    if not any(np.any(mask) for mask in measurement_masks):
        raise ValueError("No measured experimental degrees of freedom were detected.")
    return experimental_vectors, measurement_masks


def _best_geometry_evaluation(
    candidates: Sequence[GeometryMatch],
    abaqus_modes: Sequence[ModeShape],
    abaqus_reference: ModeShape,
    experimental_vectors: Sequence[np.ndarray],
    measurement_masks: Sequence[np.ndarray],
    experimental_coordinates: np.ndarray,
    full_grid_point_count: int,
    full_grid_extent: float,
    absolute_frequency_matrix: np.ndarray,
    mac_weight: float,
    frequency_weight: float,
    maximum_frequency_error_percent: float,
    minimum_mac: float,
    maximum_frequency_only_error_percent: float,
) -> Tuple[
    GeometryMatch,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    List[List[_CoverageReport]],
]:
    """Evaluate every geometry candidate and return the best-scoring one.

    The score first maximizes the number of admissible one-to-one pairs, then
    minimizes assignment cost plus a geometry-fit penalty; see the module-level
    comment on UNMATCHED_COST for why admissibility, not this score, is the
    acceptance gate.
    """
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
        mac_matrix, coverage_admissible, coverage_reports = _mac_matrix_for_geometry(
            abaqus_rotated_modes,
            experimental_vectors,
            measurement_masks,
            experimental_coordinates,
            full_grid_point_count,
            full_grid_extent,
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
        # ROADMAP Stage 2 #4: a pair below the coverage floor must not
        # participate in Hungarian assignment as an admissible candidate.
        admissible &= coverage_admissible

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
        if best_evaluation is None or score < best_evaluation[0]:
            best_evaluation = (
                score,
                geometry,
                mac_matrix,
                rows,
                columns,
                coverage_reports,
            )

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
        coverage_reports,
    ) = best_evaluation
    return (
        geometry,
        mac_matrix,
        abaqus_indices,
        experimental_indices,
        coverage_reports,
    )


def _build_candidate_diagnostics(
    abaqus_modes: Sequence[ModeShape],
    experimental_modes: Sequence[ModeShape],
    mac_matrix: np.ndarray,
    signed_frequency_matrix: np.ndarray,
    coverage_reports: Sequence[Sequence[_CoverageReport]],
    maximum_frequency_error_percent: float,
    minimum_mac: float,
    maximum_frequency_only_error_percent: float,
) -> Tuple[
    List[ModeCandidateDiagnostic],
    Dict[str, List[Optional[ModeCandidateDiagnostic]]],
]:
    """Describe every cross-product candidate without changing assignment."""
    candidates: List[ModeCandidateDiagnostic] = []
    by_index: Dict[Tuple[int, int], ModeCandidateDiagnostic] = {}
    for row, abaqus_mode in enumerate(abaqus_modes):
        for column, experimental_mode in enumerate(experimental_modes):
            signed_error = float(signed_frequency_matrix[row, column])
            absolute_error = abs(signed_error)
            mac_available = bool(np.isfinite(mac_matrix[row, column]))
            mac_value = float(mac_matrix[row, column]) if mac_available else None
            frequency_gate_passed = (
                absolute_error <= maximum_frequency_error_percent
            )
            mac_gate_passed = (
                mac_value >= minimum_mac if mac_value is not None else None
            )
            frequency_only_passed = (
                mac_value is None
                and absolute_error <= maximum_frequency_only_error_percent
            )
            coverage = coverage_reports[row][column]
            coverage_gate_passed = coverage.status == "accepted"
            admissible = coverage_gate_passed and (
                (
                    frequency_gate_passed
                    and mac_gate_passed is True
                )
                or frequency_only_passed
            )

            reasons: List[str] = []
            if not frequency_gate_passed:
                reasons.append("frequency")
            if mac_value is None:
                if not frequency_only_passed:
                    reasons.append("mac_unavailable")
            elif mac_gate_passed is False:
                reasons.append("mac")
            if not coverage_gate_passed:
                reasons.append("coverage")

            candidate = ModeCandidateDiagnostic(
                abaqus_mode=int(abaqus_mode.number),
                experimental_mode=int(experimental_mode.number),
                abaqus_frequency_hz=float(abaqus_mode.frequency_hz),
                experimental_frequency_hz=float(experimental_mode.frequency_hz),
                frequency_error_percent=signed_error,
                absolute_frequency_error_percent=absolute_error,
                mac=mac_value,
                measured_dof_count=coverage.common_dof_count,
                measured_dof_coverage=coverage.dof_coverage_fraction,
                matched_point_count=coverage.unique_point_count,
                point_coverage=coverage.point_coverage_fraction,
                spatial_coverage=coverage.spatial_coverage_fraction,
                coverage_status=coverage.status,
                frequency_gate_passed=frequency_gate_passed,
                mac_gate_passed=mac_gate_passed,
                coverage_gate_passed=coverage_gate_passed,
                admissible=admissible,
                rejection_reasons=tuple(reasons),
            )
            candidates.append(candidate)
            by_index[(row, column)] = candidate

    nearest_by_abaqus = [
        by_index[(row, int(np.argmin(np.abs(signed_frequency_matrix[row]))))]
        for row in range(len(abaqus_modes))
    ]
    nearest_by_experiment = [
        by_index[(int(np.argmin(np.abs(signed_frequency_matrix[:, column]))), column)]
        for column in range(len(experimental_modes))
    ]

    def best_mac_for_row(row: int) -> Optional[ModeCandidateDiagnostic]:
        finite = np.flatnonzero(np.isfinite(mac_matrix[row]))
        if not len(finite):
            return None
        column = int(finite[np.argmax(mac_matrix[row, finite])])
        return by_index[(row, column)]

    def best_mac_for_column(column: int) -> Optional[ModeCandidateDiagnostic]:
        finite = np.flatnonzero(np.isfinite(mac_matrix[:, column]))
        if not len(finite):
            return None
        row = int(finite[np.argmax(mac_matrix[finite, column])])
        return by_index[(row, column)]

    summaries = {
        "nearest_frequency_by_abaqus": [
            nearest_by_abaqus[row] for row in range(len(abaqus_modes))
        ],
        "best_mac_by_abaqus": [
            best_mac_for_row(row) for row in range(len(abaqus_modes))
        ],
        "nearest_frequency_by_experimental": [
            nearest_by_experiment[column]
            for column in range(len(experimental_modes))
        ],
        "best_mac_by_experimental": [
            best_mac_for_column(column)
            for column in range(len(experimental_modes))
        ],
    }
    return candidates, summaries


def _build_mode_pairs(
    abaqus_modes: Sequence[ModeShape],
    experimental_modes: Sequence[ModeShape],
    winning_abaqus_vectors: Sequence[np.ndarray],
    experimental_vectors: Sequence[np.ndarray],
    experimental_coordinates: np.ndarray,
    experimental_node_ids: np.ndarray,
    measurement_masks: Sequence[np.ndarray],
    full_grid_point_count: int,
    full_grid_extent: float,
    mac_matrix: np.ndarray,
    signed_frequency_matrix: np.ndarray,
    abaqus_indices: np.ndarray,
    experimental_indices: np.ndarray,
) -> List[ModePairResult]:
    """Build one ModePairResult per accepted (Abaqus, experimental) index pair,
    ordered by Abaqus frequency, with order-change flags applied afterward."""
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
        # This pair's own experimental mode mask only (ROADMAP Stage 2 #3).
        dof_mask = measurement_masks[column] & finite
        valid_rows = np.any(dof_mask, axis=1)
        a = abaqus_rotated[valid_rows]
        e = experimental_values[valid_rows]
        local_mask = dof_mask[valid_rows]
        coordinates = experimental_coordinates[valid_rows]
        node_ids = np.asarray(experimental_node_ids)[valid_rows]

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
            node_ids=node_ids,
        )
        setattr(pair, "measured_dof_mask", np.asarray(local_mask, dtype=bool))
        setattr(
            pair,
            "measured_dof_count",
            int(np.count_nonzero(local_mask)),
        )
        # ROADMAP Stage 2 #4 coverage diagnostics for this accepted pair.
        coverage = _coverage_report(
            dof_mask,
            int(np.count_nonzero(measurement_masks[column])),
            experimental_coordinates,
            full_grid_point_count,
            full_grid_extent,
        )
        setattr(pair, "coverage_status", coverage.status)
        setattr(pair, "dof_coverage_fraction", coverage.dof_coverage_fraction)
        setattr(pair, "point_coverage_fraction", coverage.point_coverage_fraction)
        setattr(pair, "spatial_coverage_fraction", coverage.spatial_coverage_fraction)
        pairs.append(pair)

    _recalculate_order_changed(pairs)
    return pairs


def _geometry_warnings_and_transform(
    geometry: GeometryMatch,
) -> Tuple[List[str], Dict[str, object]]:
    """Return user-facing geometry warnings plus the selected-transform metadata
    that quality_control/reporting attach to the Abaqus dataset."""
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
    if determinant < 0.0:
        warnings.append(
            "The selected coordinate transformation includes a reflection "
            "(determinant -1). Verify axis signs and specimen orientation."
        )
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
    return warnings, selected_transform


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
    full_grid_point_count = len(experimental_node_ids)
    full_grid_extent = float(
        np.linalg.norm(
            experimental_coordinates.max(axis=0) - experimental_coordinates.min(axis=0)
        )
    ) if full_grid_point_count >= 2 else 0.0

    signed_frequency_matrix, absolute_frequency_matrix = _frequency_error_matrices(
        abaqus_modes, experimental_modes
    )
    experimental_vectors, measurement_masks = _experimental_vectors_and_mask(
        experimental_modes, experimental_node_ids
    )

    candidates = geometry_alignment_candidates(
        abaqus_reference.coordinates,
        experimental_coordinates,
        coordinate_scale_override=coordinate_scale_override,
    )
    (
        geometry,
        mac_matrix,
        abaqus_indices,
        experimental_indices,
        coverage_reports,
    ) = _best_geometry_evaluation(
        candidates,
        abaqus_modes,
        abaqus_reference,
        experimental_vectors,
        measurement_masks,
        experimental_coordinates,
        full_grid_point_count,
        full_grid_extent,
        absolute_frequency_matrix,
        mac_weight,
        frequency_weight,
        maximum_frequency_error_percent,
        minimum_mac,
        maximum_frequency_only_error_percent,
    )

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

    pairs = _build_mode_pairs(
        abaqus_modes,
        experimental_modes,
        winning_abaqus_vectors,
        experimental_vectors,
        experimental_coordinates,
        experimental_node_ids,
        measurement_masks,
        full_grid_point_count,
        full_grid_extent,
        mac_matrix,
        signed_frequency_matrix,
        abaqus_indices,
        experimental_indices,
    )

    warnings, selected_transform = _geometry_warnings_and_transform(geometry)
    result_abaqus = _copy_dataset(abaqus)
    result_abaqus.metadata["selected_geometry_transform"] = selected_transform
    candidate_diagnostics, diagnostic_summaries = _build_candidate_diagnostics(
        abaqus_modes,
        experimental_modes,
        mac_matrix,
        signed_frequency_matrix,
        coverage_reports,
        maximum_frequency_error_percent,
        minimum_mac,
        maximum_frequency_only_error_percent,
    )
    diagnostic_state = "comparison" if pairs else "no_accepted_pairs"
    if not pairs:
        warnings.append(
            "Diagnostic result only: zero mode pairs passed the unchanged "
            "frequency, MAC, and coverage admissibility gates."
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
            "admissibility_gates": {
                "maximum_frequency_error_percent": maximum_frequency_error_percent,
                "minimum_mac": minimum_mac,
                "maximum_frequency_only_error_percent": (
                    maximum_frequency_only_error_percent
                ),
                "minimum_common_dof_count": MINIMUM_COMMON_DOF_COUNT,
                "minimum_unique_point_count": MINIMUM_UNIQUE_POINT_COUNT,
                "minimum_measured_dof_coverage_fraction": (
                    MINIMUM_MEASURED_DOF_COVERAGE_FRACTION
                ),
                "minimum_point_coverage_fraction": (
                    MINIMUM_POINT_COVERAGE_FRACTION
                ),
                "minimum_spatial_extent_fraction": (
                    MINIMUM_SPATIAL_EXTENT_FRACTION
                ),
            },
            "measurement_mask_relative_norm_threshold": (
                INFERRED_DOF_RELATIVE_NORM
            ),
        },
        candidate_diagnostics=candidate_diagnostics,
        diagnostic_summaries=diagnostic_summaries,
        diagnostic_state=diagnostic_state,
    )
