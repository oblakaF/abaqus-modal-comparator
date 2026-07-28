from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np
import pyuff
from scipy.signal import find_peaks, savgol_filter

import universal_reader
from modal_core import ModeShape


_INSTALLED = False
_ORIGINAL_LOAD = None


def _scalar(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    array = np.asarray(value).reshape(-1)
    if array.size == 0:
        return default
    candidate = array[0]
    try:
        if np.iscomplexobj(candidate):
            return complex(candidate)
        return float(candidate)
    except (TypeError, ValueError, OverflowError):
        return default


def _scalar_int(value: Any, default: int = 0) -> int:
    scalar = _scalar(value, None)
    if scalar is None:
        return default
    try:
        return int(np.real(scalar))
    except (TypeError, ValueError, OverflowError):
        return default


def _first(dataset: Dict[str, Any], names: Iterable[str], default=None):
    for name in names:
        if name in dataset and dataset.get(name) is not None:
            return dataset.get(name)
    return default


def _component(
    dataset: Dict[str, Any],
    names: Sequence[str],
    length: int,
) -> tuple[np.ndarray, bool]:
    value = _first(dataset, names)
    if value is None:
        return np.zeros(length, dtype=complex), False
    array = np.asarray(value, dtype=complex).reshape(-1)
    if len(array) != length:
        raise ValueError(
            f"Unexpected modal component length {len(array)}; expected {length}."
        )
    return array, True


def _dataset_type(dataset: Dict[str, Any]) -> Optional[int]:
    value = _scalar(dataset.get("type"), None)
    return None if value is None else int(np.real(value))


def _safe_mode_55(dataset: Dict[str, Any], geometry, index: int) -> ModeShape:
    node_numbers = universal_reader._as_array(dataset.get("node_nums"), dtype=int)
    if len(node_numbers) == 0:
        raise ValueError("Dataset 55 does not contain node numbers.")

    component_specs = (("r1", "x", "d1"), ("r2", "y", "d2"), ("r3", "z", "d3"))
    components = []
    measured = np.zeros((len(node_numbers), 3), dtype=bool)
    for component_index, names in enumerate(component_specs):
        values, present = _component(dataset, names, len(node_numbers))
        components.append(values)
        if present:
            measured[:, component_index] = True
    vectors = np.column_stack(components)

    mode_number = _scalar_int(_first(dataset, ("mode_n", "mode_number", "mode")), index)
    frequency = _scalar(_first(dataset, ("freq", "frequency", "natural_frequency")), None)
    if frequency is None or abs(complex(frequency)) <= 1.0e-30:
        eigenvalue = _scalar(_first(dataset, ("eig", "eigenvalue")), None)
        if eigenvalue is not None:
            frequency = abs(complex(eigenvalue).imag) / (2.0 * np.pi)
    if frequency is None or float(np.real(frequency)) <= 0.0:
        raise ValueError(f"Dataset 55 mode {mode_number} has no usable frequency.")

    mode = ModeShape(
        number=mode_number,
        frequency_hz=float(np.real(frequency)),
        node_ids=node_numbers.astype(object),
        coordinates=universal_reader._coordinates_for_nodes(node_numbers, geometry),
        vectors=vectors,
        damping_ratio=(
            None
            if _scalar(_first(dataset, ("modal_damp_vis", "viscous_damping", "damping")), None) is None
            else float(np.real(_scalar(_first(dataset, ("modal_damp_vis", "viscous_damping", "damping")), 0.0)))
        ),
        modal_mass=(
            None
            if _scalar(_first(dataset, ("modal_m", "modal_mass", "mass")), None) is None
            else float(np.real(_scalar(_first(dataset, ("modal_m", "modal_mass", "mass")), 0.0)))
        ),
        metadata={
            "dataset_type": 55,
            "analysis_type": _scalar_int(dataset.get("analysis_type"), 0),
            "data_characteristic": _scalar_int(dataset.get("data_ch"), 0),
            "id1": dataset.get("id1"),
            "id2": dataset.get("id2"),
            "mode_source": "curve-fitted modal dataset",
        },
    )
    mode.measured_dofs = measured
    return mode


def _safe_mode_2414(dataset: Dict[str, Any], geometry, index: int) -> ModeShape:
    node_numbers = universal_reader._as_array(
        _first(dataset, ("node_nums", "node_numbers", "nodes")), dtype=int
    )
    if len(node_numbers) == 0:
        raise ValueError("Dataset 2414 does not contain node numbers.")

    component_specs = (("x", "r1", "d1"), ("y", "r2", "d2"), ("z", "r3", "d3"))
    components = []
    measured = np.zeros((len(node_numbers), 3), dtype=bool)
    for component_index, names in enumerate(component_specs):
        values, present = _component(dataset, names, len(node_numbers))
        components.append(values)
        if present:
            measured[:, component_index] = True
    vectors = np.column_stack(components)

    raw = _first(dataset, ("d", "data", "values"))
    if not np.any(measured) and raw is not None:
        raw_array = np.asarray(raw, dtype=complex).reshape(len(node_numbers), -1)
        count = min(3, raw_array.shape[1])
        vectors[:, :count] = raw_array[:, :count]
        measured[:, :count] = True

    mode_number = _scalar_int(
        _first(dataset, ("mode_number", "mode_n", "mode", "iteration_number")),
        index,
    )
    frequency = _scalar(
        _first(dataset, ("frequency", "freq", "natural_frequency", "eigenvalue")),
        None,
    )
    if frequency is None or float(np.real(frequency)) <= 0.0:
        raise ValueError(f"Dataset 2414 mode {mode_number} has no usable frequency.")

    mode = ModeShape(
        number=mode_number,
        frequency_hz=float(np.real(frequency)),
        node_ids=node_numbers.astype(object),
        coordinates=universal_reader._coordinates_for_nodes(node_numbers, geometry),
        vectors=vectors,
        damping_ratio=(
            None
            if _scalar(_first(dataset, ("viscous_damping", "modal_damp_vis", "damping")), None) is None
            else float(np.real(_scalar(_first(dataset, ("viscous_damping", "modal_damp_vis", "damping")), 0.0)))
        ),
        modal_mass=(
            None
            if _scalar(_first(dataset, ("modal_mass", "modal_m", "mass")), None) is None
            else float(np.real(_scalar(_first(dataset, ("modal_mass", "modal_m", "mass")), 0.0)))
        ),
        metadata={
            "dataset_type": 2414,
            "analysis_type": _scalar_int(dataset.get("analysis_type"), 0),
            "data_characteristic": _scalar_int(
                _first(dataset, ("data_characteristic", "data_ch")), 0
            ),
            "result_type": _scalar_int(dataset.get("result_type"), 0),
            "analysis_dataset_name": dataset.get("analysis_dataset_name"),
            "mode_source": "curve-fitted modal dataset",
        },
    )
    mode.measured_dofs = measured
    return mode


def _relative_peak_detector(
    frequency: np.ndarray,
    indicator: np.ndarray,
    mean_coherence: np.ndarray,
    target_frequencies: Optional[Sequence[float]],
    target_count: int,
) -> np.ndarray:
    frequency = np.asarray(frequency, dtype=float)
    indicator = np.asarray(indicator, dtype=float)
    safe = np.maximum(indicator, max(float(np.max(indicator)), 1.0e-30) * 1.0e-14)
    logarithmic = np.log10(safe)
    line_count = len(frequency)

    window = max(5, int(round(line_count * 0.004)))
    if window % 2 == 0:
        window += 1
    maximum_window = line_count - 1 if (line_count - 1) % 2 == 1 else line_count - 2
    window = min(window, maximum_window)
    smoothed = savgol_filter(logarithmic, window, 2) if window >= 5 else logarithmic

    minimum_distance = max(2, int(round(line_count * 0.0025)))
    peaks, properties = find_peaks(
        smoothed,
        distance=minimum_distance,
        prominence=max(0.01, 0.02 * float(np.ptp(smoothed))),
    )

    targets = np.asarray(
        [value for value in (target_frequencies or []) if np.isfinite(value) and value > 0.0],
        dtype=float,
    )
    positive_frequency = frequency[frequency > 0.0]
    lower_bound = float(positive_frequency[0]) if len(positive_frequency) else float(frequency[0])
    upper_bound = float(frequency[-1])
    if len(targets):
        lower_bound = max(lower_bound, float(np.min(targets)) * 0.30)
        upper_bound = min(upper_bound, float(np.max(targets)) * 1.80)

    in_band = (frequency[peaks] >= lower_bound) & (frequency[peaks] <= upper_bound)
    peaks = peaks[in_band]
    prominences = properties["prominences"][in_band]
    if not len(peaks):
        raise ValueError(
            f"No FRF resonance peaks were detected between {lower_bound:.6g} and {upper_bound:.6g} Hz."
        )

    amplitude_range = float(np.ptp(smoothed[peaks]))
    normalized_amplitude = (
        smoothed[peaks] - float(np.min(smoothed[peaks]))
    ) / max(amplitude_range, 1.0e-12)
    scores = prominences + 0.25 * np.clip(mean_coherence[peaks], 0.0, 1.0) + 0.15 * normalized_amplitude
    if len(targets):
        relative_distance = np.min(
            np.abs(frequency[peaks, None] - targets[None, :])
            / np.maximum(targets[None, :], 1.0e-12),
            axis=1,
        )
        scores += 0.25 * np.exp(-((relative_distance / 0.15) ** 2))

    requested = max(1, int(target_count))
    maximum_candidates = min(40, max(requested + 6, requested * 3))
    if len(peaks) > maximum_candidates:
        peaks = peaks[np.argsort(scores)[::-1][:maximum_candidates]]
    return np.sort(peaks.astype(int))


def _local_coordinate_diagnostics(datasets: List[Dict[str, Any]]) -> Dict[str, Any]:
    non_default_nodes = 0
    coordinate_dataset_present = False
    identifiers = set()
    for dataset in datasets:
        dataset_type = _dataset_type(dataset)
        if dataset_type == 2420:
            coordinate_dataset_present = True
        if dataset_type not in (15, 2411):
            continue
        for key in ("def_cs", "disp_cs", "def_cs_id", "disp_cs_id"):
            if key not in dataset:
                continue
            values = np.asarray(dataset.get(key)).reshape(-1)
            numeric = []
            for value in values:
                scalar = _scalar(value, None)
                if scalar is not None:
                    numeric.append(int(np.real(scalar)))
            identifiers.update(item for item in numeric if item not in (0, 1))
            non_default_nodes += sum(item not in (0, 1) for item in numeric)
    return {
        "coordinate_system_dataset_2420_present": coordinate_dataset_present,
        "non_default_coordinate_system_node_entries": non_default_nodes,
        "non_default_coordinate_system_ids": sorted(identifiers),
    }


def _postprocess_measurement_masks(modes: List[ModeShape]) -> None:
    if not modes:
        return
    explicit = [getattr(mode, "measured_dofs", None) for mode in modes]
    if any(mask is not None for mask in explicit):
        return

    reference_ids = modes[0].node_ids
    index_maps = [
        {str(node_id): index for index, node_id in enumerate(mode.node_ids)}
        for mode in modes
    ]
    union = np.zeros((len(reference_ids), 3), dtype=bool)
    for mode, lookup in zip(modes, index_maps):
        mapped = np.zeros((len(reference_ids), 3), dtype=complex)
        finite = np.zeros((len(reference_ids), 3), dtype=bool)
        for output_index, node_id in enumerate(reference_ids):
            source_index = lookup.get(str(node_id))
            if source_index is not None:
                mapped[output_index] = mode.vectors[source_index]
                finite[output_index] = np.isfinite(mode.vectors[source_index])
        scale = max(float(np.max(np.abs(mapped))), 1.0e-30)
        union |= finite & (np.abs(mapped) > scale * 1.0e-12)
    if not np.any(union):
        union[:] = True
    for mode in modes:
        if len(mode.node_ids) == len(reference_ids) and np.array_equal(mode.node_ids, reference_ids):
            mode.measured_dofs = union.copy()


def load_universal_modal_file(*args, **kwargs):
    file_path = args[0] if args else kwargs.get("file_path")
    uff = pyuff.UFF(str(file_path))
    raw = uff.read_sets()
    datasets = [raw] if isinstance(raw, dict) else [item for item in raw if isinstance(item, dict)]

    dataset = _ORIGINAL_LOAD(*args, **kwargs)
    _postprocess_measurement_masks(dataset.modes)
    diagnostics = _local_coordinate_diagnostics(datasets)
    dataset.metadata["local_coordinate_system_diagnostics"] = diagnostics
    if diagnostics["coordinate_system_dataset_2420_present"] or diagnostics[
        "non_default_coordinate_system_node_entries"
    ]:
        warning = (
            "The UNV file contains local coordinate-system information. The current importer "
            "does not rotate modal vectors from dataset 2420/local node systems; verify that "
            "the exported response directions are already global before accepting MAC values."
        )
        dataset.metadata.setdefault("import_warnings", []).append(warning)
    return dataset


def install_universal_hardening() -> None:
    global _INSTALLED, _ORIGINAL_LOAD
    if _INSTALLED:
        return
    _ORIGINAL_LOAD = universal_reader.load_universal_modal_file
    universal_reader._dataset_type = _dataset_type
    universal_reader._mode_from_dataset_55 = _safe_mode_55
    universal_reader._mode_from_dataset_2414 = _safe_mode_2414
    universal_reader._detect_frf_peak_indices = _relative_peak_detector
    universal_reader.load_universal_modal_file = load_universal_modal_file
    _INSTALLED = True
