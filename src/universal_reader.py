from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pyuff
from scipy.signal import find_peaks, savgol_filter

from modal_core import ModalDataset, ModeShape


@dataclass
class ExperimentalModalSet:
    """One fitted dataset-55 result set, detached from pyuff records."""

    key: str
    display_name: str
    modes: List[ModeShape]
    source_dataset: int = 55
    processing_name: str = ""
    record_indices: List[int] = field(default_factory=list)
    residual_record_indices: List[int] = field(default_factory=list)
    residual_labels: List[str] = field(default_factory=list)
    non_modal_record_indices: List[int] = field(default_factory=list)
    non_modal_labels: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def excluded_residual_count(self) -> int:
        return len(self.residual_record_indices)

    @property
    def excluded_non_modal_count(self) -> int:
        return len(self.non_modal_record_indices)


_RESIDUAL_ID1 = re.compile(
    r"^(?P<processing>.*?)\s+residuals?\s+(?P<side>below|above)\b(?P<limit>.*)$",
    re.IGNORECASE,
)

_MODAL_ANALYSIS_TYPES = {2, 3, 7}
_DATASET_55_NON_MODAL_ANALYSIS_TYPES = {1, 4, 5, 6}
_DATASET_2414_NON_MODAL_ANALYSIS_TYPES = {1, 4, 5, 6, 9}

# Dataset-58 peak discovery is intentionally independent of any FE model.
# This is only a computational/sanity ceiling for pathological FRF exports;
# it is not an expected physical mode count and is never derived from Abaqus.
MAX_EXPERIMENTAL_PEAK_CANDIDATES = 40


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


def _text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _modal_set_identity(name: str) -> str:
    return _text(name).casefold()


def _modal_set_key(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", _text(name).casefold()).strip("-")
    return normalized or "dataset-55"


def _integer_value(value: Any) -> Optional[int]:
    try:
        values = np.asarray(value).reshape(-1)
        return None if len(values) == 0 else int(values[0])
    except (TypeError, ValueError, IndexError):
        return None


def _residual_identity(dataset: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """Return Test.Lab's parent processing name and residual label, if present."""
    label = _text(dataset.get("id1"))
    match = _RESIDUAL_ID1.match(label)
    if match is None:
        return None
    return _text(match.group("processing")), label


def _classify_dataset_55_record(dataset: Dict[str, Any]) -> Dict[str, Any]:
    """Classify one dataset-55 record using UNV structure plus Test.Lab text.

    UNV defines analysis types 2, 3, and 7 as modal/eigenvalue records and
    analysis type 5 as frequency response. Real SP10/SP13 Test.Lab exports use
    type 3 for fitted poles and type 5 for below/above residual shapes. Text is
    therefore supporting identity evidence, never sufficient to discard a
    structurally modal record.
    """
    label = _text(dataset.get("id1"))
    residual_identity = _residual_identity(dataset)
    analysis_type = _integer_value(dataset.get("analysis_type"))
    processing_name = (
        label
        if analysis_type in _MODAL_ANALYSIS_TYPES
        else residual_identity[0] if residual_identity else label
    )
    evidence = {
        "analysis_type": analysis_type,
        "id1_residual_marker": residual_identity is not None,
    }

    if analysis_type in _MODAL_ANALYSIS_TYPES:
        if residual_identity is not None:
            return {
                "classification": "ambiguous",
                "include": True,
                "processing_name": processing_name,
                "label": label,
                "reason": (
                    "id1 resembles a Test.Lab residual label, but UNV analysis_type "
                    f"{analysis_type} is modal; preserved conservatively"
                ),
                "evidence": evidence,
            }
        return {
            "classification": "physical",
            "include": True,
            "processing_name": processing_name,
            "label": label,
            "reason": f"UNV analysis_type {analysis_type} is modal/eigenvalue data",
            "evidence": evidence,
        }

    if analysis_type in _DATASET_55_NON_MODAL_ANALYSIS_TYPES:
        description = (
            "frequency-response data" if analysis_type == 5 else "non-modal analysis data"
        )
        marker = (
            " with a corroborating Test.Lab residual below/above label"
            if residual_identity is not None
            else ""
        )
        return {
            "classification": "residual" if residual_identity is not None else "non_modal",
            "include": False,
            "processing_name": processing_name,
            "label": label,
            "reason": f"UNV analysis_type {analysis_type} is {description}{marker}",
            "evidence": evidence,
        }

    return {
        "classification": "ambiguous",
        "include": True,
        "processing_name": processing_name,
        "label": label,
        "reason": "analysis_type is missing, unknown, or not portable; preserved conservatively",
        "evidence": evidence,
    }


def _classify_dataset_2414_record(dataset: Dict[str, Any]) -> Dict[str, Any]:
    """Classify dataset 2414 without borrowing Test.Lab dataset-55 labels."""
    analysis_type = _integer_value(dataset.get("analysis_type"))
    evidence = {
        "analysis_type": analysis_type,
        "dataset_location": _integer_value(dataset.get("dataset_location")),
        "result_type": _integer_value(dataset.get("result_type")),
    }
    if analysis_type in _MODAL_ANALYSIS_TYPES:
        return {
            "classification": "physical",
            "include": True,
            "reason": f"UNV analysis_type {analysis_type} is modal/eigenvalue data",
            "evidence": evidence,
        }
    if analysis_type in _DATASET_2414_NON_MODAL_ANALYSIS_TYPES:
        description = (
            "frequency-response data" if analysis_type == 5 else "non-modal analysis data"
        )
        return {
            "classification": "non_modal",
            "include": False,
            "reason": f"UNV analysis_type {analysis_type} is {description}",
            "evidence": evidence,
        }
    return {
        "classification": "ambiguous",
        "include": True,
        "reason": "analysis_type is missing, unknown, or not portable; preserved conservatively",
        "evidence": evidence,
    }


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


def _discover_dataset_55_modal_sets(
    datasets: Sequence[Dict[str, Any]],
    geometry: Dict[int, np.ndarray],
) -> List[ExperimentalModalSet]:
    groups: Dict[str, Dict[str, Any]] = {}

    def group_for(processing_name: str) -> Dict[str, Any]:
        identity = _modal_set_identity(processing_name)
        group = groups.get(identity)
        if group is None:
            display_name = _text(processing_name) or "Dataset 55 modal set"
            group = {
                "processing_name": _text(processing_name),
                "display_name": display_name,
                "modes": [],
                "record_indices": [],
                "residual_record_indices": [],
                "residual_labels": [],
                "non_modal_record_indices": [],
                "non_modal_labels": [],
                "errors": [],
                "id2": [],
                "id3": [],
                "id5": [],
                "analysis_types": [],
                "record_classifications": [],
                "ambiguous_record_indices": [],
            }
            groups[identity] = group
        return group

    for record_index, dataset in enumerate(datasets):
        if _dataset_type(dataset) != 55:
            continue

        classification = _classify_dataset_55_record(dataset)
        processing_name = classification["processing_name"]
        group = group_for(processing_name)
        record_audit = {
            "record_index": record_index,
            "record_id": f"dataset55:{record_index}",
            "id1": classification["label"],
            "classification": classification["classification"],
            "included": classification["include"],
            "reason": classification["reason"],
            "evidence": classification["evidence"],
        }
        group["record_classifications"].append(record_audit)
        if not classification["include"]:
            if classification["classification"] == "residual":
                group["residual_record_indices"].append(record_index)
                group["residual_labels"].append(classification["label"])
            else:
                group["non_modal_record_indices"].append(record_index)
                group["non_modal_labels"].append(classification["label"])
            continue

        try:
            mode = _mode_from_dataset_55(dataset, geometry, record_index + 1)
        except ValueError as error:
            group["errors"].append(str(error))
            continue

        mode.metadata.update(
            {
                "source": "curve-fitted dataset 55",
                "modal_set_name": group["display_name"],
                "processing_name": processing_name,
                "dataset_55_record_index": record_index,
                "dataset_55_record_id": f"dataset55:{record_index}",
                "source_frequency_hz": mode.frequency_hz,
                "record_classification": classification["classification"],
                "record_classification_reason": classification["reason"],
                "record_classification_evidence": classification["evidence"],
            }
        )
        if classification["classification"] == "ambiguous":
            group["ambiguous_record_indices"].append(record_index)
            group["errors"].append(
                f"Dataset 55 record {record_index} was preserved as ambiguous: "
                f"{classification['reason']}."
            )
        group["modes"].append(mode)
        group["record_indices"].append(record_index)
        for field_name in ("id2", "id3", "id5"):
            value = _text(dataset.get(field_name))
            if value and value not in group[field_name]:
                group[field_name].append(value)
        analysis_type = dataset.get("analysis_type")
        try:
            analysis_type = int(np.asarray(analysis_type).reshape(-1)[0])
        except (TypeError, ValueError, IndexError):
            analysis_type = None
        if analysis_type is not None and analysis_type not in group["analysis_types"]:
            group["analysis_types"].append(analysis_type)

    results: List[ExperimentalModalSet] = []
    used_keys: Dict[str, str] = {}
    for identity, group in groups.items():
        if not group["modes"]:
            continue
        key = _modal_set_key(group["processing_name"])
        if key in used_keys and used_keys[key] != identity:
            suffix = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:8]
            key = f"{key}-{suffix}"
        used_keys[key] = identity
        for mode in group["modes"]:
            mode.metadata["modal_set_key"] = key
        results.append(
            ExperimentalModalSet(
                key=key,
                display_name=group["display_name"],
                processing_name=group["processing_name"],
                modes=sorted(group["modes"], key=lambda item: item.number),
                record_indices=list(group["record_indices"]),
                residual_record_indices=list(group["residual_record_indices"]),
                residual_labels=list(group["residual_labels"]),
                non_modal_record_indices=list(group["non_modal_record_indices"]),
                non_modal_labels=list(group["non_modal_labels"]),
                metadata={
                    "source": "dataset_55",
                    "record_indices": list(group["record_indices"]),
                    "residual_record_indices": list(group["residual_record_indices"]),
                    "excluded_residual_count": len(group["residual_record_indices"]),
                    "excluded_residual_labels": list(group["residual_labels"]),
                    "non_modal_record_indices": list(group["non_modal_record_indices"]),
                    "excluded_non_modal_count": len(group["non_modal_record_indices"]),
                    "excluded_non_modal_labels": list(group["non_modal_labels"]),
                    "analysis_types": list(group["analysis_types"]),
                    "id2": list(group["id2"]),
                    "id3": list(group["id3"]),
                    "id5": list(group["id5"]),
                    "import_warnings": list(group["errors"]),
                    "record_classifications": list(group["record_classifications"]),
                    "ambiguous_record_indices": list(group["ambiguous_record_indices"]),
                    "residual_classification": (
                        "UNV modal/non-modal analysis_type semantics corroborated by "
                        "Test.Lab id1 residual labels; ambiguous records are preserved"
                    ),
                },
            )
        )
    return results


def _read_universal_datasets(file_path: Path) -> List[Dict[str, Any]]:
    uff = pyuff.UFF(str(file_path))
    datasets = uff.read_sets()
    if isinstance(datasets, dict):
        datasets = [datasets]
    return [item for item in datasets if isinstance(item, dict)]


def discover_experimental_modal_sets(file_path: Path) -> List[ExperimentalModalSet]:
    """Discover fitted dataset-55 groups without choosing or merging them."""
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(file_path)
    datasets = _read_universal_datasets(file_path)
    geometry, _ = _read_geometry(datasets)
    return _discover_dataset_55_modal_sets(datasets, geometry)


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
    target_frequencies: Optional[Sequence[float]] = None,
    target_count: Optional[int] = None,
) -> np.ndarray:
    """Detect experimental FRF peaks using experimental evidence only.

    ``target_frequencies`` and ``target_count`` are retained temporarily for
    compatibility with older callers, but deliberately ignored. FE results
    must not determine whether an experimental resonance/ODS candidate exists.
    """
    del target_frequencies, target_count
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
    peaks, properties = find_peaks(smoothed, distance=minimum_distance, prominence=0.02)

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

    if len(peaks) > MAX_EXPERIMENTAL_PEAK_CANDIDATES:
        selected = np.argsort(scores)[::-1][:MAX_EXPERIMENTAL_PEAK_CANDIDATES]
        peaks = peaks[selected]

    return np.sort(peaks.astype(int))


def _modes_from_frf_datasets(
    datasets: Sequence[Dict[str, Any]],
    geometry: Dict[int, np.ndarray],
    target_frequencies: Optional[Sequence[float]] = None,
    target_count: Optional[int] = None,
) -> Tuple[List[ModeShape], Dict[str, Any]]:
    del target_frequencies, target_count
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


def _frf_diagnostic_metadata(
    datasets: Sequence[Dict[str, Any]],
    geometry: Dict[int, np.ndarray],
) -> Dict[str, Any]:
    """Parse dataset-58 FRF/coherence arrays without deriving modal candidates."""
    frf_group = _select_frf_group(datasets, geometry)
    if not frf_group:
        raise ValueError("No usable frequency-response functions were found in dataset 58.")

    x_reference = _as_array(frf_group[0].get("x"), dtype=float)
    if len(x_reference) < 5:
        raise ValueError("The selected FRF group contains too few frequency lines.")
    reference_node = int(np.asarray(frf_group[0].get("ref_node", 0)).reshape(-1)[0])
    reference_direction = int(np.asarray(frf_group[0].get("ref_dir", 0)).reshape(-1)[0])

    dof_data: Dict[Tuple[int, int], np.ndarray] = {}
    for dataset in frf_group:
        x = _as_array(dataset.get("x"), dtype=float)
        data = _as_array(dataset.get("data"), dtype=complex)
        if len(x) != len(x_reference) or len(data) != len(x_reference):
            continue
        if not np.allclose(x, x_reference, rtol=1e-8, atol=1e-10):
            continue
        node = int(np.asarray(dataset.get("rsp_node", 0)).reshape(-1)[0])
        direction = int(np.asarray(dataset.get("rsp_dir", 0)).reshape(-1)[0])
        if node in geometry and abs(direction) in (1, 2, 3):
            dof_data[(node, direction)] = data
    if not dof_data:
        raise ValueError("No compatible nodal FRF channels were found.")

    indicator = np.linalg.norm(np.vstack(list(dof_data.values())), axis=0)
    try:
        coherence_lookup = _coherence_by_dof(
            datasets, x_reference, reference_node, reference_direction
        )
        coherence_parse_error: Optional[str] = None
    except (TypeError, ValueError, IndexError, KeyError) as error:
        coherence_lookup = {}
        coherence_parse_error = str(error)
    coherence_rows = [
        coherence_lookup[key] for key in dof_data if key in coherence_lookup
    ]
    if coherence_parse_error is not None:
        coherence_status = "parse_error"
        mean_coherence = np.full_like(x_reference, np.nan, dtype=float)
    elif coherence_rows:
        coherence_status = "computed"
        mean_coherence = np.mean(np.vstack(coherence_rows), axis=0)
    else:
        coherence_status = "unavailable"
        mean_coherence = np.full_like(x_reference, np.nan, dtype=float)

    return {
        "dataset_58_role": "diagnostic_only",
        "dataset_58_diagnostic_available": True,
        "dataset_58_derived_mode_count": 0,
        "frf_channel_count": len(dof_data),
        "frf_response_node_count": len({node for node, _ in dof_data}),
        "frf_reference_node": reference_node,
        "frf_reference_direction": reference_direction,
        "frf_frequency_start_hz": float(x_reference[0]),
        "frf_frequency_end_hz": float(x_reference[-1]),
        "frf_frequency_lines": len(x_reference),
        "frf_frequency_increment_hz": float(np.median(np.diff(x_reference))),
        "frf_quantity": str(frf_group[0].get("id2", "")),
        "coherence_channel_count": len(coherence_rows),
        "coherence_status": coherence_status,
        "coherence_parse_error": coherence_parse_error,
        "_frf_frequency_hz": x_reference.tolist(),
        "_frf_indicator": indicator.tolist(),
        "_frf_mean_coherence": mean_coherence.tolist(),
    }


def load_universal_modal_file(
    file_path: Path,
    target_frequencies: Optional[Sequence[float]] = None,
    target_count: Optional[int] = None,
    modal_set: Optional[str] = None,
) -> ModalDataset:
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(file_path)

    dataset_list = _read_universal_datasets(file_path)
    geometry, metadata = _read_geometry(dataset_list)
    set_types = [_dataset_type(item) for item in dataset_list]
    metadata["dataset_types"] = [value for value in set_types if value is not None]
    metadata["geometry_node_count"] = len(geometry)

    modes: List[ModeShape] = []
    errors: List[str] = []

    modal_sets = _discover_dataset_55_modal_sets(dataset_list, geometry)
    metadata["available_modal_sets"] = [
        {
            "key": item.key,
            "display_name": item.display_name,
            "processing_name": item.processing_name,
            "mode_count": len(item.modes),
            "excluded_residual_count": item.excluded_residual_count,
            "excluded_non_modal_count": item.excluded_non_modal_count,
        }
        for item in modal_sets
    ]

    selected_set: Optional[ExperimentalModalSet] = None
    if modal_sets:
        if modal_set is None:
            if len(modal_sets) > 1:
                available = ", ".join(
                    f"{item.display_name} ({item.key})" for item in modal_sets
                )
                raise ValueError(
                    "Multiple dataset-55 modal sets are available; select one explicitly "
                    f"with modal_set=. Available sets: {available}."
                )
            selected_set = modal_sets[0]
            selection_policy = "implicit_single_set"
        else:
            requested = _text(modal_set)
            matches = [
                item
                for item in modal_sets
                if requested.casefold()
                in {
                    item.key.casefold(),
                    item.display_name.casefold(),
                    item.processing_name.casefold(),
                }
            ]
            if not matches:
                available = ", ".join(
                    f"{item.display_name} ({item.key})" for item in modal_sets
                )
                raise ValueError(
                    f"Dataset-55 modal set {modal_set!r} was not found. Available sets: {available}."
                )
            selected_set = matches[0]
            selection_policy = "explicit"

        modes.extend(selected_set.modes)
        metadata.update(
            {
                "mode_source": "curve-fitted dataset 55",
                "modal_set_key": selected_set.key,
                "modal_set_name": selected_set.display_name,
                "processing_name": selected_set.processing_name,
                "modal_set_selection_policy": selection_policy,
                "modal_set_record_indices": list(selected_set.record_indices),
                "excluded_residual_count": selected_set.excluded_residual_count,
                "excluded_residual_labels": list(selected_set.residual_labels),
                "excluded_residual_record_indices": list(
                    selected_set.residual_record_indices
                ),
                "excluded_non_modal_count": selected_set.excluded_non_modal_count,
                "excluded_non_modal_labels": list(selected_set.non_modal_labels),
                "excluded_non_modal_record_indices": list(
                    selected_set.non_modal_record_indices
                ),
                "modal_record_classifications": list(
                    selected_set.metadata.get("record_classifications", [])
                ),
                "ambiguous_modal_record_indices": list(
                    selected_set.metadata.get("ambiguous_record_indices", [])
                ),
            }
        )
        errors.extend(selected_set.metadata.get("import_warnings", []))
    else:
        if modal_set is not None:
            raise ValueError(
                f"Dataset-55 modal set {modal_set!r} was requested, but the file "
                "contains no valid dataset-55 modal sets."
            )
        dataset_2414_classifications: List[Dict[str, Any]] = []
        for index, dataset in enumerate(dataset_list, start=1):
            if _dataset_type(dataset) != 2414:
                continue
            record_index = index - 1
            classification = _classify_dataset_2414_record(dataset)
            record_audit = {
                "record_index": record_index,
                "record_id": f"dataset2414:{record_index}",
                "identity": _text(dataset.get("analysis_dataset_name")),
                "classification": classification["classification"],
                "included": classification["include"],
                "reason": classification["reason"],
                "evidence": classification["evidence"],
            }
            dataset_2414_classifications.append(record_audit)
            if not classification["include"]:
                continue
            try:
                mode_number = dataset.get("mode_number")
                analysis_type = _integer_value(dataset.get("analysis_type"))
                if mode_number not in (None, 0) or analysis_type in _MODAL_ANALYSIS_TYPES:
                    mode = _mode_from_dataset_2414(dataset, geometry, index)
                    mode.metadata.update(
                        {
                            "dataset_2414_record_index": record_index,
                            "dataset_2414_record_id": f"dataset2414:{record_index}",
                            "record_classification": classification["classification"],
                            "record_classification_reason": classification["reason"],
                            "record_classification_evidence": classification["evidence"],
                        }
                    )
                    modes.append(mode)
                    if classification["classification"] == "ambiguous":
                        errors.append(
                            f"Dataset 2414 record {record_index} was preserved as ambiguous: "
                            f"{classification['reason']}."
                        )
            except ValueError as error:
                errors.append(str(error))
        if dataset_2414_classifications:
            metadata["dataset_2414_record_classifications"] = dataset_2414_classifications
            metadata["excluded_dataset_2414_record_indices"] = [
                item["record_index"]
                for item in dataset_2414_classifications
                if not item["included"]
            ]
            metadata["ambiguous_dataset_2414_record_indices"] = [
                item["record_index"]
                for item in dataset_2414_classifications
                if item["classification"] == "ambiguous"
            ]

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
        )
        modes.extend(frf_modes)
        metadata.update(frf_metadata)
        source_name = "Simcenter Testlab UNV/UFF — FRF-derived modes"

    elif selected_set is not None and 58 in metadata["dataset_types"]:
        try:
            frf_metadata = _frf_diagnostic_metadata(dataset_list, geometry)
        except ValueError as error:
            metadata.update(
                {
                    "dataset_58_role": "diagnostic_only",
                    "dataset_58_diagnostic_available": False,
                    "dataset_58_diagnostic_error": str(error),
                }
            )
            errors.append(f"Dataset 58 diagnostics: {error}")
        else:
            metadata.update(frf_metadata)

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
