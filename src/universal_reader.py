from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pyuff
from scipy.signal import find_peaks, savgol_filter

from modal_core import ModalDataset, ModeShape


def _as_array(value: Any, length: Optional[int] = None, dtype: Any = float) -> np.ndarray:
    if value is None:
        if length is None:
            return np.array([], dtype=dtype)
        return np.zeros(length, dtype=dtype)
    array = np.asarray(value, dtype=dtype).reshape(-1)
    if length is not None and len(array) != length:
        if len(array) == 0:
            return np.zeros(length, dtype=dtype)
        raise ValueError(f"Unexpected array length {len(array)}; expected {length}.")
    return array


def _dataset_type(dataset: Dict[str, Any]) -> Optional[int]:
    value = dataset.get("type")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _read_geometry(datasets: Iterable[Dict[str, Any]]) -> Tuple[Dict[int, np.ndarray], Dict[str, Any]]:
    geometry: Dict[int, np.ndarray] = {}
    metadata: Dict[str, Any] = {}

    for dataset in datasets:
        dataset_type = _dataset_type(dataset)
        if dataset_type == 151:
            for key in ("model_name", "description", "program", "db_app", "id1", "id2", "id3", "id4", "id5"):
                if dataset.get(key) not in (None, ""):
                    metadata[key] = dataset.get(key)

        if dataset_type == 164:
            metadata["units_code"] = dataset.get("units_code")
            metadata["units_description"] = dataset.get("units_description")
            metadata["length_scale"] = dataset.get("length")

        if dataset_type not in (15, 2411):
            continue

        node_numbers = _as_array(dataset.get("node_nums"), dtype=int)
        if len(node_numbers) == 0:
            continue
        x = _as_array(dataset.get("x"), len(node_numbers), float)
        y = _as_array(dataset.get("y"), len(node_numbers), float)
        z = _as_array(dataset.get("z"), len(node_numbers), float)

        for node, coordinate in zip(node_numbers, np.column_stack((x, y, z))):
            geometry[int(node)] = np.asarray(coordinate, dtype=float)

    return geometry, metadata


def _coordinates_for_nodes(node_numbers: np.ndarray, geometry: Dict[int, np.ndarray]) -> np.ndarray:
    missing = [int(node) for node in node_numbers if int(node) not in geometry]
    if missing:
        sample = ", ".join(str(value) for value in missing[:8])
        raise ValueError(
            "The UNV/UFF file contains vectors but no coordinates for "
            f"{len(missing)} nodes (for example: {sample}). "
            "Export geometry together with the measurement data from Simcenter Testlab."
        )
    return np.vstack([geometry[int(node)] for node in node_numbers])


def _mode_from_dataset_55(dataset: Dict[str, Any], geometry: Dict[int, np.ndarray], index: int) -> ModeShape:
    node_numbers = _as_array(dataset.get("node_nums"), dtype=int)
    if len(node_numbers) == 0:
        raise ValueError("Dataset 55 does not contain node numbers.")

    components: List[np.ndarray] = []
    for component_name in ("r1", "r2", "r3"):
        components.append(_as_array(dataset.get(component_name), len(node_numbers), complex))
    vectors = np.column_stack(components)

    mode_number = dataset.get("mode_n")
    if mode_number in (None, 0):
        mode_number = index
    frequency = dataset.get("freq")
    if frequency in (None, 0):
        eigenvalue = dataset.get("eig")
        if eigenvalue not in (None, 0):
            frequency = abs(complex(eigenvalue).imag) / (2.0 * np.pi)
    if frequency in (None, 0):
        raise ValueError(f"Dataset 55 mode {mode_number} has no usable frequency.")

    return ModeShape(
        number=int(mode_number),
        frequency_hz=float(np.real(frequency)),
        node_ids=node_numbers.astype(object),
        coordinates=_coordinates_for_nodes(node_numbers, geometry),
        vectors=vectors,
        damping_ratio=(
            None
            if dataset.get("modal_damp_vis") is None
            else float(np.real(dataset.get("modal_damp_vis")))
        ),
        modal_mass=(
            None if dataset.get("modal_m") is None else float(np.real(dataset.get("modal_m")))
        ),
        metadata={
            "dataset_type": 55,
            "analysis_type": dataset.get("analysis_type"),
            "data_characteristic": dataset.get("data_ch"),
            "id1": dataset.get("id1"),
            "id2": dataset.get("id2"),
            "mode_source": "curve-fitted modal dataset",
        },
    )


def _mode_from_dataset_2414(dataset: Dict[str, Any], geometry: Dict[int, np.ndarray], index: int) -> ModeShape:
    node_numbers = _as_array(dataset.get("node_nums"), dtype=int)
    if len(node_numbers) == 0:
        raise ValueError("Dataset 2414 does not contain node numbers.")

    x = _as_array(dataset.get("x"), len(node_numbers), complex)
    y = _as_array(dataset.get("y"), len(node_numbers), complex)
    z = _as_array(dataset.get("z"), len(node_numbers), complex)
    vectors = np.column_stack((x, y, z))

    if not np.any(np.abs(vectors)) and dataset.get("d") is not None:
        raw = np.asarray(dataset.get("d"))
        raw = raw.reshape(len(node_numbers), -1)
        vectors = np.zeros((len(node_numbers), 3), dtype=complex)
        vectors[:, : min(3, raw.shape[1])] = raw[:, :3]

    mode_number = dataset.get("mode_number")
    if mode_number in (None, 0):
        mode_number = index
    frequency = dataset.get("frequency")
    if frequency in (None, 0):
        frequency = dataset.get("eigenvalue")
    if frequency in (None, 0):
        raise ValueError(f"Dataset 2414 mode {mode_number} has no usable frequency.")

    return ModeShape(
        number=int(mode_number),
        frequency_hz=float(np.real(frequency)),
        node_ids=node_numbers.astype(object),
        coordinates=_coordinates_for_nodes(node_numbers, geometry),
        vectors=vectors,
        damping_ratio=(
            None
            if dataset.get("viscous_damping") is None
            else float(np.real(dataset.get("viscous_damping")))
        ),
        modal_mass=(
            None if dataset.get("modal_mass") is None else float(np.real(dataset.get("modal_mass")))
        ),
        metadata={
            "dataset_type": 2414,
            "analysis_type": dataset.get("analysis_type"),
            "data_characteristic": dataset.get("data_characteristic"),
            "result_type": dataset.get("result_type"),
            "analysis_dataset_name": dataset.get("analysis_dataset_name"),
            "mode_source": "curve-fitted modal dataset",
        },
    )


def _axis_signature(dataset: Dict[str, Any]) -> Optional[Tuple[int, float, float, float]]:
    x = _as_array(dataset.get("x"), dtype=float)
    if len(x) < 3 or not np.all(np.isfinite(x)):
        return None
    step = float(np.median(np.diff(x)))
    return len(x), round(float(x[0]), 10), round(float(x[-1]), 10), round(step, 10)


def _frf_label(dataset: Dict[str, Any]) -> str:
    return " ".join(
        str(dataset.get(key, ""))
        for key in (
            "id1",
            "id2",
            "ordinate_axis_lab",
            "ordinate_axis_units_lab",
            "orddenom_axis_lab",
            "orddenom_axis_units_lab",
        )
    ).lower()


def _select_frf_group(
    datasets: Sequence[Dict[str, Any]],
    geometry: Dict[int, np.ndarray],
) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = {}

    for dataset in datasets:
        if _dataset_type(dataset) != 58:
            continue
        if int(dataset.get("func_type", -1)) != 4:
            continue
        response_node = dataset.get("rsp_node")
        response_direction = dataset.get("rsp_dir")
        if response_node is None or int(response_node) not in geometry:
            continue
        if response_direction is None or abs(int(response_direction)) not in (1, 2, 3):
            continue
        data = _as_array(dataset.get("data"), dtype=complex)
        signature = _axis_signature(dataset)
        if signature is None or len(data) != signature[0]:
            continue

        label = _frf_label(dataset)
        if "displacement" in label:
            quantity_priority = 3
        elif "velocity" in label:
            quantity_priority = 2
        elif "acceleration" in label or "accelerance" in label:
            quantity_priority = 1
        else:
            quantity_priority = 0

        key = (
            signature,
            int(dataset.get("ref_node", 0) or 0),
            int(dataset.get("ref_dir", 0) or 0),
            quantity_priority,
            str(dataset.get("id2", "")),
        )
        groups.setdefault(key, []).append(dataset)

    if not groups:
        return []

    def group_score(item: Tuple[Tuple[Any, ...], List[Dict[str, Any]]]) -> Tuple[int, int, int]:
        key, group = item
        unique_dofs = {
            (int(dataset.get("rsp_node")), int(dataset.get("rsp_dir")))
            for dataset in group
        }
        quantity_priority = int(key[3])
        return quantity_priority, len(unique_dofs), len(group)

    return max(groups.items(), key=group_score)[1]


def _coherence_by_dof(
    datasets: Sequence[Dict[str, Any]],
    x_reference: np.ndarray,
    reference_node: int,
    reference_direction: int,
) -> Dict[Tuple[int, int], np.ndarray]:
    output: Dict[Tuple[int, int], np.ndarray] = {}
    for dataset in datasets:
        if _dataset_type(dataset) != 58 or int(dataset.get("func_type", -1)) != 6:
            continue
        if int(dataset.get("ref_node", 0) or 0) != reference_node:
            continue
        if int(dataset.get("ref_dir", 0) or 0) != reference_direction:
            continue
        x = _as_array(dataset.get("x"), dtype=float)
        data = _as_array(dataset.get("data"), dtype=float)
        if len(x) != len(x_reference) or len(data) != len(x_reference):
            continue
        if not np.allclose(x, x_reference, rtol=1e-8, atol=1e-10):
            continue
        node = int(dataset.get("rsp_node", 0) or 0)
        direction = int(dataset.get("rsp_dir", 0) or 0)
        output[(node, direction)] = np.clip(np.real(data), 0.0, 1.0)
    return output


def _estimate_half_power_damping(
    frequency: np.ndarray,
    indicator: np.ndarray,
    peak_index: int,
) -> Optional[float]:
    peak_value = float(indicator[peak_index])
    peak_frequency = float(frequency[peak_index])
    if peak_value <= 0.0 or peak_frequency <= 0.0:
        return None

    threshold = peak_value / np.sqrt(2.0)
    left = peak_index
    while left > 0 and indicator[left] > threshold:
        left -= 1
    right = peak_index
    while right < len(indicator) - 1 and indicator[right] > threshold:
        right += 1
    if left == 0 or right == len(indicator) - 1:
        return None

    def interpolate(first: int, second: int) -> float:
        first_value = float(indicator[first])
        second_value = float(indicator[second])
        if abs(second_value - first_value) <= 1e-30:
            return float(frequency[second])
        return float(
            frequency[first]
            + (threshold - first_value)
            * (frequency[second] - frequency[first])
            / (second_value - first_value)
        )

    lower_frequency = interpolate(left, left + 1)
    upper_frequency = interpolate(right - 1, right)
    damping = (upper_frequency - lower_frequency) / (2.0 * peak_frequency)
    if not np.isfinite(damping) or damping <= 0.0 or damping >= 0.50:
        return None
    return float(damping)


def _phase_complexity(vector: np.ndarray) -> float:
    flattened = np.asarray(vector, dtype=complex).reshape(-1)
    if not len(flattened) or np.max(np.abs(flattened)) <= 1e-30:
        return 1.0
    reference = flattened[int(np.argmax(np.abs(flattened)))]
    aligned = flattened * np.exp(-1j * np.angle(reference))
    real_norm = float(np.linalg.norm(np.real(aligned)))
    imaginary_norm = float(np.linalg.norm(np.imag(aligned)))
    return imaginary_norm / max(real_norm, 1e-30)


def _detect_frf_peak_indices(
    frequency: np.ndarray,
    indicator: np.ndarray,
    mean_coherence: np.ndarray,
    target_frequencies: Optional[Sequence[float]],
    target_count: int,
) -> np.ndarray:
    safe_indicator = np.maximum(indicator, max(float(np.max(indicator)), 1e-30) * 1e-14)
    logarithmic = np.log10(safe_indicator)
    frequency_step = float(np.median(np.diff(frequency)))

    window = max(5, int(round(2.0 / max(frequency_step, 1e-12))))
    if window % 2 == 0:
        window += 1
    maximum_window = len(frequency) - 1 if (len(frequency) - 1) % 2 == 1 else len(frequency) - 2
    window = min(window, maximum_window)
    smoothed = savgol_filter(logarithmic, window, 2) if window >= 5 else logarithmic

    minimum_distance = max(2, int(round(1.25 / max(frequency_step, 1e-12))))
    peaks, properties = find_peaks(smoothed, distance=minimum_distance, prominence=0.04)

    targets = np.asarray(
        [value for value in (target_frequencies or []) if np.isfinite(value) and value > 0.0],
        dtype=float,
    )
    if len(targets):
        lower_frequency = max(float(frequency[0]), 5.0, float(np.min(targets)) * 0.35)
        upper_frequency = min(float(frequency[-1]), float(np.max(targets)) * 1.80)
    else:
        lower_frequency = max(float(frequency[0]), 5.0)
        upper_frequency = float(frequency[-1])

    in_band = (frequency[peaks] >= lower_frequency) & (frequency[peaks] <= upper_frequency)
    peaks = peaks[in_band]
    prominences = properties["prominences"][in_band]
    if not len(peaks):
        raise ValueError(
            f"No FRF resonance peaks were detected between {lower_frequency:.3f} and {upper_frequency:.3f} Hz."
        )

    amplitude_range = float(np.ptp(smoothed[peaks]))
    normalized_amplitude = (
        (smoothed[peaks] - float(np.min(smoothed[peaks]))) / max(amplitude_range, 1e-12)
    )
    scores = (
        prominences
        + 0.25 * np.clip(mean_coherence[peaks], 0.0, 1.0)
        + 0.15 * normalized_amplitude
    )

    if len(targets):
        relative_distance = np.min(
            np.abs(frequency[peaks, None] - targets[None, :])
            / np.maximum(targets[None, :], 1.0),
            axis=1,
        )
        scores += 0.25 * np.exp(-((relative_distance / 0.15) ** 2))

    damping_values = [
        _estimate_half_power_damping(frequency, indicator, int(index)) for index in peaks
    ]
    physically_plausible = np.array(
        [value is None or value <= 0.15 for value in damping_values], dtype=bool
    )
    if np.count_nonzero(physically_plausible) >= max(1, target_count):
        peaks = peaks[physically_plausible]
        scores = scores[physically_plausible]

    maximum_candidates = min(40, max(target_count + 6, target_count * 3))
    if len(peaks) > maximum_candidates:
        selected = np.argsort(scores)[::-1][:maximum_candidates]
        peaks = peaks[selected]

    return np.sort(peaks.astype(int))


def _modes_from_frf_datasets(
    datasets: Sequence[Dict[str, Any]],
    geometry: Dict[int, np.ndarray],
    target_frequencies: Optional[Sequence[float]],
    target_count: int,
) -> Tuple[List[ModeShape], Dict[str, Any]]:
    frf_group = _select_frf_group(datasets, geometry)
    if not frf_group:
        raise ValueError(
            "No usable frequency-response functions were found in dataset 58."
        )

    x_reference = _as_array(frf_group[0].get("x"), dtype=float)
    if len(x_reference) < 5:
        raise ValueError("The selected FRF group contains too few frequency lines.")

    reference_node = int(frf_group[0].get("ref_node", 0) or 0)
    reference_direction = int(frf_group[0].get("ref_dir", 0) or 0)
    coherence_lookup = _coherence_by_dof(
        datasets,
        x_reference,
        reference_node,
        reference_direction,
    )

    dof_data: Dict[Tuple[int, int], np.ndarray] = {}
    for dataset in frf_group:
        x = _as_array(dataset.get("x"), dtype=float)
        data = _as_array(dataset.get("data"), dtype=complex)
        if len(x) != len(x_reference) or len(data) != len(x_reference):
            continue
        if not np.allclose(x, x_reference, rtol=1e-8, atol=1e-10):
            continue
        node = int(dataset.get("rsp_node"))
        direction = int(dataset.get("rsp_dir"))
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
    if coherence_rows:
        mean_coherence = np.mean(np.vstack(coherence_rows), axis=0)
    else:
        mean_coherence = np.ones_like(x_reference, dtype=float)

    peak_indices = _detect_frf_peak_indices(
        x_reference,
        indicator,
        mean_coherence,
        target_frequencies,
        max(1, target_count),
    )

    node_numbers = np.asarray(sorted({node for node, _ in row_keys}), dtype=int)
    node_index = {int(node): index for index, node in enumerate(node_numbers)}
    coordinates = _coordinates_for_nodes(node_numbers, geometry)
    modes: List[ModeShape] = []

    for mode_number, peak_index in enumerate(peak_indices, start=1):
        vectors = np.zeros((len(node_numbers), 3), dtype=complex)
        for node, signed_direction in row_keys:
            direction = abs(int(signed_direction))
            sign = -1.0 if int(signed_direction) < 0 else 1.0
            if direction not in (1, 2, 3):
                continue
            vectors[node_index[int(node)], direction - 1] = (
                sign * dof_data[(node, signed_direction)][peak_index]
            )

        damping = _estimate_half_power_damping(x_reference, indicator, int(peak_index))
        modes.append(
            ModeShape(
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
                    "mean_coherence": float(mean_coherence[peak_index]),
                    "frf_indicator": float(indicator[peak_index]),
                    "phase_complexity_ratio": float(_phase_complexity(vectors)),
                    "response_quantity": str(frf_group[0].get("id2", "")),
                    "reference_node": reference_node,
                    "reference_direction": reference_direction,
                },
            )
        )

    metadata = {
        "mode_source": "dataset 58 FRF peak extraction",
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
        "frf_mode_warning": (
            "Experimental shapes were derived directly from complex FRFs at detected resonance peaks. "
            "They are suitable for automatic screening and MAC comparison, but they are not a substitute "
            "for a fully curve-fitted Simcenter modal model when modes are strongly overlapping."
        ),
        "_frf_frequency_hz": x_reference.tolist(),
        "_frf_indicator": indicator.tolist(),
        "_frf_mean_coherence": mean_coherence.tolist(),
    }
    return modes, metadata


def load_universal_modal_file(
    file_path: Path,
    target_frequencies: Optional[Sequence[float]] = None,
    target_count: Optional[int] = None,
) -> ModalDataset:
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(file_path)

    uff = pyuff.UFF(str(file_path))
    datasets = uff.read_sets()
    if isinstance(datasets, dict):
        datasets = [datasets]

    dataset_list: List[Dict[str, Any]] = [item for item in datasets if isinstance(item, dict)]
    geometry, metadata = _read_geometry(dataset_list)
    set_types = [_dataset_type(item) for item in dataset_list]
    metadata["dataset_types"] = [value for value in set_types if value is not None]
    metadata["geometry_node_count"] = len(geometry)

    modes: List[ModeShape] = []
    errors: List[str] = []

    for index, dataset in enumerate(dataset_list, start=1):
        dataset_type = _dataset_type(dataset)
        try:
            if dataset_type == 55:
                modes.append(_mode_from_dataset_55(dataset, geometry, index))
            elif dataset_type == 2414:
                analysis_type = dataset.get("analysis_type")
                mode_number = dataset.get("mode_number")
                if mode_number not in (None, 0) or analysis_type in (2, 3, 7):
                    modes.append(_mode_from_dataset_2414(dataset, geometry, index))
        except ValueError as error:
            errors.append(str(error))

    source_name = "Simcenter Testlab UNV/UFF"
    if not modes:
        if 58 not in metadata["dataset_types"]:
            found = ", ".join(str(value) for value in sorted(set(metadata["dataset_types"])))
            raise ValueError(
                "No experimental modal vectors or FRFs were found in the UNV/UFF file. "
                f"Detected dataset types: {found}."
            )
        frf_modes, frf_metadata = _modes_from_frf_datasets(
            dataset_list,
            geometry,
            target_frequencies,
            target_count or max(1, len(target_frequencies or [])),
        )
        modes.extend(frf_modes)
        metadata.update(frf_metadata)
        source_name = "Simcenter Testlab UNV/UFF — FRF-derived modes"

    modes.sort(key=lambda mode: mode.number)
    metadata["mode_count"] = len(modes)
    metadata["import_warnings"] = errors

    return ModalDataset(
        source_name=source_name,
        source_path=file_path,
        modes=modes,
        metadata=metadata,
    )


def resolve_testlab_file(file_path: Path) -> Path:
    """Resolve a selected Testlab project to its companion universal file."""
    file_path = Path(file_path)
    if file_path.suffix.lower() != ".lms":
        return file_path

    candidates = [
        file_path.with_suffix(".unv"),
        file_path.with_suffix(".uff"),
        file_path.with_suffix(".UNV"),
        file_path.with_suffix(".UFF"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    universal_files = sorted(file_path.parent.glob("*.unv")) + sorted(file_path.parent.glob("*.uff"))
    if len(universal_files) == 1:
        return universal_files[0]

    raise ValueError(
        "A Simcenter Testlab .lms file was selected, but no companion .unv/.uff file "
        "was found next to it. Select the UNV/UFF file that was supplied with the LMS project."
    )
