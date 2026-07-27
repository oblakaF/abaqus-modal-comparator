from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from modal_core import ComparisonResult, ModalDataset
from reviewed_core import compare_modal_datasets


MAX_ACCEPTED_FREQUENCY_ERROR_PERCENT = 15.0
MIN_ACCEPTED_MAC = 0.50
MAX_FREQUENCY_ONLY_ERROR_PERCENT = 10.0
RIGID_MODE_RELATIVE_THRESHOLD = 0.01
RIGID_MODE_GAP_RATIO = 20.0
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


def _detect_rigid_modes(dataset: ModalDataset) -> Tuple[List, List, float, Optional[float]]:
    """Detect a near-zero cluster from a large relative gap, not a fixed 1 Hz cut-off."""
    modes = sorted(dataset.modes, key=lambda mode: mode.frequency_hz)
    positive = [mode for mode in modes if mode.frequency_hz > MIN_POSITIVE_FREQUENCY_HZ]
    if len(positive) < 2:
        return [], modes, 0.0, positive[0].frequency_hz if positive else None

    ratios = [
        right.frequency_hz / max(left.frequency_hz, MIN_POSITIVE_FREQUENCY_HZ)
        for left, right in zip(positive, positive[1:])
    ]
    largest_index = max(range(len(ratios)), key=ratios.__getitem__)
    largest_ratio = ratios[largest_index]
    if largest_ratio < RIGID_MODE_GAP_RATIO:
        return [], modes, 0.0, positive[0].frequency_hz

    first_elastic_frequency = positive[largest_index + 1].frequency_hz
    threshold = first_elastic_frequency * RIGID_MODE_RELATIVE_THRESHOLD
    excluded = [mode for mode in modes if mode.frequency_hz < threshold]
    retained = [mode for mode in modes if mode.frequency_hz >= threshold]
    return excluded, retained, threshold, first_elastic_frequency


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
            groups.append(
                [
                    {"mode": int(mode.number), "frequency_hz": float(mode.frequency_hz)}
                    for mode in current
                ]
            )
            current = []

    if current:
        groups.append(
            [
                {"mode": int(mode.number), "frequency_hz": float(mode.frequency_hz)}
                for mode in current
            ]
        )
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
) -> ComparisonResult:
    excluded_modes, retained_modes, rigid_threshold, first_elastic = _detect_rigid_modes(abaqus)
    if not retained_modes:
        raise ValueError("No elastic Abaqus modes remain after near-zero mode detection.")

    filtered_abaqus = _copy_dataset_with_modes(abaqus, retained_modes)
    filtered_abaqus.metadata["quality_control"] = {
        "rigid_mode_method": "relative gap detection",
        "rigid_mode_relative_threshold": RIGID_MODE_RELATIVE_THRESHOLD,
        "rigid_mode_gap_ratio": RIGID_MODE_GAP_RATIO,
        "rigid_mode_threshold_hz": rigid_threshold,
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
    )

    if excluded_modes:
        details = ", ".join(
            f"mode {mode.number} ({mode.frequency_hz:.6g} Hz)"
            for mode in excluded_modes
        )
        result.warnings.append(
            "Automatically excluded near-zero rigid-body mode(s): "
            + details
            + f". Relative threshold: {rigid_threshold:.6g} Hz."
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
    """Backward-compatible no-op; callers should import the wrapper directly."""
    return None
