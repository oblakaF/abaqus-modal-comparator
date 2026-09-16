from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

import universal_reader
from modal_core import ModeShape
from universal_hardening import _scalar_int


_INSTALLED = False


def modes_from_frf_datasets(
    datasets: Sequence[Dict[str, Any]],
    geometry: Dict[int, np.ndarray],
    target_frequencies: Optional[Sequence[float]] = None,
    target_count: Optional[int] = None,
) -> Tuple[List[ModeShape], Dict[str, Any]]:
    # Legacy compatibility inputs stop here. Candidate existence is determined
    # exclusively from the experimental FRF/coherence data below.
    del target_frequencies, target_count
    frf_group = universal_reader._select_frf_group(datasets, geometry)
    if not frf_group:
        raise ValueError("No usable frequency-response functions were found in dataset 58.")

    x_reference = universal_reader._as_array(frf_group[0].get("x"), dtype=float)
    if len(x_reference) < 5:
        raise ValueError("The selected FRF group contains too few frequency lines.")

    reference_node = _scalar_int(frf_group[0].get("ref_node"), 0)
    reference_direction = _scalar_int(frf_group[0].get("ref_dir"), 0)
    try:
        coherence_lookup = universal_reader._coherence_by_dof(
            datasets,
            x_reference,
            reference_node,
            reference_direction,
        )
        coherence_parse_error: Optional[str] = None
    except (TypeError, ValueError, IndexError, KeyError) as error:
        coherence_lookup = {}
        coherence_parse_error = str(error)

    dof_data: Dict[Tuple[int, int], np.ndarray] = {}
    for dataset in frf_group:
        x = universal_reader._as_array(dataset.get("x"), dtype=float)
        data = universal_reader._as_array(dataset.get("data"), dtype=complex)
        if len(x) != len(x_reference) or len(data) != len(x_reference):
            continue
        if not np.allclose(x, x_reference, rtol=1e-8, atol=1e-10):
            continue
        node = _scalar_int(dataset.get("rsp_node"), 0)
        direction = _scalar_int(dataset.get("rsp_dir"), 0)
        if node in geometry and abs(direction) in (1, 2, 3):
            dof_data[(node, direction)] = data

    if not dof_data:
        raise ValueError("No compatible nodal FRF channels were found.")

    row_keys = sorted(dof_data)
    frf_matrix = np.vstack([dof_data[key] for key in row_keys])
    indicator = np.linalg.norm(frf_matrix, axis=0)
    coherence_rows = [
        coherence_lookup[key]
        for key in row_keys
        if key in coherence_lookup
    ]
    if coherence_parse_error is not None:
        coherence_status = "parse_error"
    elif coherence_rows:
        coherence_status = "computed"
    else:
        coherence_status = "unavailable"

    if coherence_status == "computed":
        mean_coherence = np.mean(np.vstack(coherence_rows), axis=0)
    else:
        # No fabricated 1.0 fallback: a mode without measured coherence must not
        # be able to read as "perfect coherence" downstream (ROADMAP Stage 2 #1).
        mean_coherence = np.full_like(x_reference, np.nan, dtype=float)

    # Peak ranking gets a neutral (no bonus, no penalty) coherence term when
    # coherence was not actually measured, instead of NaN or a fabricated 1.0.
    ranking_coherence = np.nan_to_num(mean_coherence, nan=0.0)

    peak_indices = universal_reader._detect_frf_peak_indices(
        x_reference,
        indicator,
        ranking_coherence,
    )

    node_numbers = np.asarray(sorted({node for node, _ in row_keys}), dtype=int)
    node_index = {int(node): index for index, node in enumerate(node_numbers)}
    coordinates = universal_reader._coordinates_for_nodes(node_numbers, geometry)
    measured_mask = np.zeros((len(node_numbers), 3), dtype=bool)
    for node, signed_direction in row_keys:
        direction = abs(int(signed_direction))
        if direction in (1, 2, 3):
            measured_mask[node_index[int(node)], direction - 1] = True

    modes: List[ModeShape] = []
    for mode_number, peak_index in enumerate(peak_indices, start=1):
        vectors = np.zeros((len(node_numbers), 3), dtype=complex)
        for node, signed_direction in row_keys:
            direction = abs(int(signed_direction))
            if direction not in (1, 2, 3):
                continue
            sign = -1.0 if int(signed_direction) < 0 else 1.0
            vectors[node_index[int(node)], direction - 1] = (
                sign * dof_data[(node, signed_direction)][peak_index]
            )

        damping = universal_reader._estimate_half_power_damping(
            x_reference, indicator, int(peak_index)
        )
        mode = ModeShape(
            number=mode_number,
            frequency_hz=float(x_reference[peak_index]),
            node_ids=node_numbers.astype(object),
            coordinates=coordinates,
            vectors=vectors,
            damping_ratio=damping,
            metadata={
                "dataset_type": 58,
                "mode_source": "FRF peak-derived experimental shape",
                "frequency_line_index": int(peak_index),
                "mean_coherence": (
                    float(mean_coherence[peak_index])
                    if coherence_status == "computed"
                    else None
                ),
                "coherence_status": coherence_status,
                "frf_indicator": float(indicator[peak_index]),
                "phase_complexity_ratio": float(
                    universal_reader._phase_complexity(vectors)
                ),
                "response_quantity": str(frf_group[0].get("id2", "")),
                "reference_node": reference_node,
                "reference_direction": reference_direction,
            },
        )
        mode.measured_dofs = measured_mask.copy()
        modes.append(mode)

    metadata = {
        "mode_source": "dataset 58 FRF peak extraction",
        "candidate_policy": "experimental_only",
        "peak_candidate_safety_cap": universal_reader.MAX_EXPERIMENTAL_PEAK_CANDIDATES,
        "returned_peak_count": len(modes),
        "frf_channel_count": len(dof_data),
        "frf_response_node_count": len(node_numbers),
        "frf_reference_node": reference_node,
        "frf_reference_direction": reference_direction,
        "frf_frequency_start_hz": float(x_reference[0]),
        "frf_frequency_end_hz": float(x_reference[-1]),
        "frf_frequency_lines": len(x_reference),
        "frf_frequency_increment_hz": float(np.median(np.diff(x_reference))),
        "detected_peak_frequencies_hz": [mode.frequency_hz for mode in modes],
        "frf_quantity": str(frf_group[0].get("id2", "")),
        "coherence_channel_count": len(coherence_rows),
        "coherence_status": coherence_status,
        "coherence_parse_error": coherence_parse_error,
        "frf_mode_warning": (
            "Experimental shapes were derived directly from complex FRFs at detected resonance peaks. "
            "They are suitable for screening and MAC comparison, but are not a substitute for a "
            "fully curve-fitted Simcenter modal model when modes overlap strongly."
        ),
        "_frf_frequency_hz": x_reference.tolist(),
        "_frf_indicator": indicator.tolist(),
        "_frf_mean_coherence": mean_coherence.tolist(),
    }
    return modes, metadata


def install_frf_review() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    universal_reader._modes_from_frf_datasets = modes_from_frf_datasets
    _INSTALLED = True
