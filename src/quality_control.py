from __future__ import annotations

from typing import List

import modal_core
from modal_core import ComparisonResult, ModalDataset, ModePairResult


_ORIGINAL_COMPARE = modal_core.compare_modal_datasets
_INSTALLED = False


MIN_ABAQUS_FREQUENCY_HZ = 1.0
MAX_ACCEPTED_FREQUENCY_ERROR_PERCENT = 15.0
MIN_ACCEPTED_MAC = 0.50
MAX_FREQUENCY_ONLY_ERROR_PERCENT = 10.0


def _copy_dataset_with_modes(dataset: ModalDataset, modes) -> ModalDataset:
    return ModalDataset(
        source_name=dataset.source_name,
        source_path=dataset.source_path,
        modes=list(modes),
        metadata=dict(dataset.metadata),
        history=list(dataset.history),
    )


def _is_reliable_pair(pair: ModePairResult) -> bool:
    if pair.mac is None:
        return pair.frequency_error_percent <= MAX_FREQUENCY_ONLY_ERROR_PERCENT
    return (
        pair.frequency_error_percent <= MAX_ACCEPTED_FREQUENCY_ERROR_PERCENT
        and pair.mac >= MIN_ACCEPTED_MAC
    )


def _recalculate_order_changes(pairs: List[ModePairResult]) -> None:
    if not pairs:
        return

    abaqus_order = sorted(
        pairs,
        key=lambda pair: (pair.abaqus_frequency_hz, pair.abaqus_mode),
    )
    experimental_order = sorted(
        pairs,
        key=lambda pair: (pair.experimental_frequency_hz, pair.experimental_mode),
    )
    experimental_rank = {
        id(pair): rank for rank, pair in enumerate(experimental_order)
    }

    for abaqus_rank, pair in enumerate(abaqus_order):
        pair.order_changed = experimental_rank[id(pair)] != abaqus_rank


def compare_modal_datasets_with_quality_control(
    abaqus: ModalDataset,
    experimental: ModalDataset,
    mac_weight: float = 0.75,
    frequency_weight: float = 0.25,
) -> ComparisonResult:
    excluded_modes = [
        mode
        for mode in abaqus.sorted_modes()
        if mode.frequency_hz < MIN_ABAQUS_FREQUENCY_HZ
    ]
    retained_modes = [
        mode
        for mode in abaqus.sorted_modes()
        if mode.frequency_hz >= MIN_ABAQUS_FREQUENCY_HZ
    ]

    if not retained_modes:
        raise ValueError(
            "All selected Abaqus modes are below the rigid-mode frequency threshold "
            f"of {MIN_ABAQUS_FREQUENCY_HZ:.3f} Hz."
        )

    filtered_abaqus = _copy_dataset_with_modes(abaqus, retained_modes)
    filtered_abaqus.metadata["quality_control"] = {
        "minimum_abaqus_frequency_hz": MIN_ABAQUS_FREQUENCY_HZ,
        "maximum_accepted_frequency_error_percent": MAX_ACCEPTED_FREQUENCY_ERROR_PERCENT,
        "minimum_accepted_mac": MIN_ACCEPTED_MAC,
        "maximum_frequency_only_error_percent": MAX_FREQUENCY_ONLY_ERROR_PERCENT,
        "excluded_abaqus_modes": [mode.number for mode in excluded_modes],
    }

    result = _ORIGINAL_COMPARE(
        filtered_abaqus,
        experimental,
        mac_weight=mac_weight,
        frequency_weight=frequency_weight,
    )

    reliable_pairs = [pair for pair in result.pairs if _is_reliable_pair(pair)]
    rejected_pairs = [pair for pair in result.pairs if not _is_reliable_pair(pair)]
    _recalculate_order_changes(reliable_pairs)
    result.pairs = reliable_pairs

    if excluded_modes:
        details = ", ".join(
            f"mode {mode.number} ({mode.frequency_hz:.6g} Hz)"
            for mode in excluded_modes
        )
        result.warnings.append(
            "Automatically excluded near-zero rigid-body mode(s): " + details + "."
        )

    paired_abaqus_modes = {pair.abaqus_mode for pair in reliable_pairs}
    unmatched_abaqus_modes = [
        mode for mode in retained_modes if mode.number not in paired_abaqus_modes
    ]
    if unmatched_abaqus_modes:
        details = ", ".join(
            f"mode {mode.number} ({mode.frequency_hz:.6g} Hz)"
            for mode in unmatched_abaqus_modes
        )
        result.warnings.append(
            "No reliable one-to-one experimental counterpart was found for Abaqus "
            + details
            + f". Such modes are left unmatched instead of being forced to a remote peak "
            f"(limits: error <= {MAX_ACCEPTED_FREQUENCY_ERROR_PERCENT:.1f}%, "
            f"MAC >= {MIN_ACCEPTED_MAC:.2f})."
        )

    if rejected_pairs:
        result.abaqus.metadata["rejected_forced_pairs"] = [
            {
                "abaqus_mode": pair.abaqus_mode,
                "experimental_mode": pair.experimental_mode,
                "abaqus_frequency_hz": pair.abaqus_frequency_hz,
                "experimental_frequency_hz": pair.experimental_frequency_hz,
                "frequency_error_percent": pair.frequency_error_percent,
                "mac": pair.mac,
            }
            for pair in rejected_pairs
        ]

    result.abaqus.metadata["matched_pair_count_after_quality_control"] = len(
        reliable_pairs
    )
    result.abaqus.metadata["unmatched_abaqus_modes"] = [
        mode.number for mode in unmatched_abaqus_modes
    ]

    if not reliable_pairs:
        raise ValueError(
            "No reliable Abaqus–experimental pairs met the frequency and MAC quality limits."
        )

    return result


def install_quality_control() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    modal_core.compare_modal_datasets = compare_modal_datasets_with_quality_control
    _INSTALLED = True
