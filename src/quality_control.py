from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

from coordinate_calibration import CoordinateCalibration
from modal_core import ComparisonResult, ModalDataset, ModeShape
from reviewed_core import compare_modal_datasets

MAX_ACCEPTED_FREQUENCY_ERROR_PERCENT = 15.0
MIN_ACCEPTED_MAC = 0.50
MAX_FREQUENCY_ONLY_ERROR_PERCENT = 10.0
RIGID_SHAPE_RESIDUAL_THRESHOLD = 0.02
MIN_POSITIVE_FREQUENCY_HZ = 1.0e-8
CLOSE_MODE_ABSOLUTE_GAP_HZ = 3.0
CLOSE_MODE_RELATIVE_GAP = 0.03


def _copy_dataset_with_modes(dataset: ModalDataset, modes) -> ModalDataset:
    return ModalDataset(
        source_name=dataset.source_name,
        source_path=dataset.source_path,
        modes=list(modes),
        metadata=dict(dataset.metadata),
        history=list(dataset.history),
    )


def _rigid_body_residual_fraction(mode: ModeShape) -> float:
    coordinates = np.asarray(mode.coordinates, dtype=float)
    vectors = np.asarray(mode.vectors, dtype=complex)
    finite_rows = (
        np.all(np.isfinite(coordinates), axis=1)
        & np.all(np.isfinite(vectors.real), axis=1)
        & np.all(np.isfinite(vectors.imag), axis=1)
    )
    coordinates = coordinates[finite_rows]
    vectors = vectors[finite_rows]
    if len(coordinates) < 2:
        return 1.0
    vector = vectors.reshape(-1)
    vector_norm = float(np.linalg.norm(vector))
    if vector_norm <= 1.0e-30:
        return 1.0

    centered = coordinates - np.mean(coordinates, axis=0)
    x, y, z = centered[:, 0], centered[:, 1], centered[:, 2]
    basis = np.zeros((3 * len(centered), 6), dtype=float)
    basis[0::3, 0] = 1.0
    basis[1::3, 1] = 1.0
    basis[2::3, 2] = 1.0
    basis[1::3, 3] = -z
    basis[2::3, 3] = y
    basis[0::3, 4] = z
    basis[2::3, 4] = -x
    basis[0::3, 5] = -y
    basis[1::3, 5] = x

    coefficients, _, _, _ = np.linalg.lstsq(basis, vector, rcond=None)
    residual = vector - basis @ coefficients
    return float(np.linalg.norm(residual) / vector_norm)


def _rigid_residuals(dataset: ModalDataset) -> Dict[int, float]:
    return {
        int(mode.number): _rigid_body_residual_fraction(mode)
        for mode in dataset.modes
    }


def _detect_rigid_modes(
    dataset: ModalDataset,
) -> Tuple[List[ModeShape], List[ModeShape], float, Optional[float]]:
    modes = sorted(dataset.modes, key=lambda mode: mode.frequency_hz)
    residuals = _rigid_residuals(dataset)
    excluded = [
        mode
        for mode in modes
        if residuals[int(mode.number)] <= RIGID_SHAPE_RESIDUAL_THRESHOLD
    ]
    excluded_ids = {id(mode) for mode in excluded}
    retained = [mode for mode in modes if id(mode) not in excluded_ids]
    highest_excluded = max((mode.frequency_hz for mode in excluded), default=0.0)
    first_elastic = min((mode.frequency_hz for mode in retained), default=None)
    return excluded, retained, highest_excluded, first_elastic


def _close_mode_groups(dataset: ModalDataset) -> List[List[Dict[str, float]]]:
    modes = sorted(dataset.modes, key=lambda mode: mode.frequency_hz)
    groups: List[List[Dict[str, float]]] = []
    current = []
    for left, right in zip(modes, modes[1:]):
        average = 0.5 * (left.frequency_hz + right.frequency_hz)
        threshold = max(
            CLOSE_MODE_ABSOLUTE_GAP_HZ,
            CLOSE_MODE_RELATIVE_GAP * max(average, MIN_POSITIVE_FREQUENCY_HZ),
        )
        if right.frequency_hz - left.frequency_hz <= threshold:
            if not current:
                current = [left]
            if current[-1].number != right.number:
                current.append(right)
        elif current:
            groups.append([
                {"mode": int(mode.number), "frequency_hz": float(mode.frequency_hz)}
                for mode in current
            ])
            current = []
    if current:
        groups.append([
            {"mode": int(mode.number), "frequency_hz": float(mode.frequency_hz)}
            for mode in current
        ])
    return groups


def _format_close_groups(groups: List[List[Dict[str, float]]]) -> str:
    return "; ".join(
        " / ".join(
            f"mode {int(item['mode'])} ({item['frequency_hz']:.4g} Hz)"
            for item in group
        )
        for group in groups
    )


def compare_modal_datasets_with_quality_control(
    abaqus: ModalDataset,
    experimental: ModalDataset,
    mac_weight: float = 0.75,
    frequency_weight: float = 0.25,
    coordinate_scale_override: Optional[float] = None,
    geometry_calibration: Optional[CoordinateCalibration] = None,
) -> ComparisonResult:
    rigid_residuals = _rigid_residuals(abaqus)
    excluded_modes, retained_modes, rigid_threshold, first_elastic = _detect_rigid_modes(abaqus)
    if not retained_modes:
        raise ValueError("No elastic Abaqus modes remain after rigid-body shape projection.")

    filtered_abaqus = _copy_dataset_with_modes(abaqus, retained_modes)
    filtered_abaqus.metadata["quality_control"] = {
        "rigid_mode_method": "six-vector rigid-body subspace projection",
        "rigid_shape_residual_threshold": RIGID_SHAPE_RESIDUAL_THRESHOLD,
        "rigid_body_residual_fraction_by_mode": rigid_residuals,
        "highest_excluded_rigid_frequency_hz": rigid_threshold,
        "first_elastic_frequency_hz": first_elastic,
        "maximum_accepted_frequency_error_percent": MAX_ACCEPTED_FREQUENCY_ERROR_PERCENT,
        "minimum_accepted_mac": MIN_ACCEPTED_MAC,
        "maximum_frequency_only_error_percent": MAX_FREQUENCY_ONLY_ERROR_PERCENT,
        "close_mode_absolute_gap_hz": CLOSE_MODE_ABSOLUTE_GAP_HZ,
        "close_mode_relative_gap": CLOSE_MODE_RELATIVE_GAP,
        "excluded_abaqus_modes": [mode.number for mode in excluded_modes],
        "frequency_error_sign_convention": (
            "positive: Abaqus frequency is higher than experiment; "
            "negative: Abaqus frequency is lower than experiment"
        ),
        "assignment_method": "admissibility gates before Hungarian assignment",
    }

    result = compare_modal_datasets(
        filtered_abaqus,
        experimental,
        mac_weight=mac_weight,
        frequency_weight=frequency_weight,
        maximum_frequency_error_percent=MAX_ACCEPTED_FREQUENCY_ERROR_PERCENT,
        minimum_mac=MIN_ACCEPTED_MAC,
        maximum_frequency_only_error_percent=MAX_FREQUENCY_ONLY_ERROR_PERCENT,
        coordinate_scale_override=coordinate_scale_override,
        geometry_calibration=geometry_calibration,
    )

    if excluded_modes:
        details = ", ".join(
            f"mode {mode.number} ({mode.frequency_hz:.6g} Hz, residual "
            f"{rigid_residuals.get(int(mode.number), float('nan')):.3g})"
            for mode in excluded_modes
        )
        result.warnings.append(
            "Automatically excluded rigid-body mode(s) by shape projection: "
            + details
            + f". Residual limit: {RIGID_SHAPE_RESIDUAL_THRESHOLD:.3g}."
        )

    paired_abaqus_modes = {pair.abaqus_mode for pair in result.pairs}
    paired_experimental_modes = {pair.experimental_mode for pair in result.pairs}
    unmatched_abaqus_modes = [
        mode for mode in retained_modes if mode.number not in paired_abaqus_modes
    ]
    if unmatched_abaqus_modes:
        details = ", ".join(
            f"mode {mode.number} ({mode.frequency_hz:.6g} Hz)"
            for mode in unmatched_abaqus_modes
        )
        result.warnings.append(
            "No admissible one-to-one experimental counterpart was found for Abaqus "
            + details
            + f" (limits applied before assignment: |error| <= "
            f"{MAX_ACCEPTED_FREQUENCY_ERROR_PERCENT:.1f}%, MAC >= {MIN_ACCEPTED_MAC:.2f})."
        )

    minimum_frequency = min(mode.frequency_hz for mode in retained_modes) * 0.75
    maximum_frequency = max(mode.frequency_hz for mode in retained_modes) * 1.25
    unmatched_experimental_modes = [
        mode
        for mode in experimental.sorted_modes()
        if mode.number not in paired_experimental_modes
        and minimum_frequency <= mode.frequency_hz <= maximum_frequency
    ]
    if unmatched_experimental_modes:
        details = ", ".join(
            f"mode {mode.number} ({mode.frequency_hz:.6g} Hz)"
            for mode in unmatched_experimental_modes
        )
        result.warnings.append(
            "Experimental mode candidate(s) inside the Abaqus comparison band have no "
            "admissible numerical counterpart: "
            + details
            + ". Check omitted components, joints, boundary conditions, local coordinate "
            "systems, or other missing model physics."
        )

    close_abaqus_groups = _close_mode_groups(filtered_abaqus)
    close_experimental_groups = _close_mode_groups(experimental)
    result.abaqus.metadata["close_abaqus_mode_groups"] = close_abaqus_groups
    result.abaqus.metadata["close_experimental_mode_groups"] = close_experimental_groups
    if close_abaqus_groups:
        result.warnings.append(
            "Closely spaced Abaqus modes may appear as mixed experimental shapes: "
            + _format_close_groups(close_abaqus_groups)
            + "."
        )

    # A missing coherence_status (legacy cache/project data saved before this
    # field existed) is normalized to "unavailable" rather than silently
    # skipped, so old projects surface this warning too.
    uncomputed_coherence_modes = [
        mode
        for mode in experimental.sorted_modes()
        if mode.metadata.get("dataset_type") == 58
        and mode.metadata.get("coherence_status") != "computed"
    ]
    if uncomputed_coherence_modes:
        parse_error_count = sum(
            1
            for mode in uncomputed_coherence_modes
            if mode.metadata.get("coherence_status") == "parse_error"
        )
        detail = (
            f"{parse_error_count} could not be parsed"
            if parse_error_count
            else "no dataset-58 coherence channels were present"
        )
        result.warnings.append(
            f"{len(uncomputed_coherence_modes)} FRF-derived experimental mode(s) have no "
            f"measured coherence ({detail}); their confidence is reported as "
            "peak-derived only and was not allowed to read as high-confidence."
        )

    result.abaqus.metadata["matched_pair_count_after_quality_control"] = len(result.pairs)
    result.abaqus.metadata["unmatched_abaqus_modes"] = [
        {"mode": mode.number, "frequency_hz": mode.frequency_hz}
        for mode in unmatched_abaqus_modes
    ]
    result.abaqus.metadata["unmatched_experimental_candidates"] = [
        {"mode": mode.number, "frequency_hz": mode.frequency_hz}
        for mode in unmatched_experimental_modes
    ]
    return result


def install_quality_control() -> None:
    return None
