from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pyuff

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
        if dataset_type in (151,):
            for key in ("model_name", "description", "program", "db_app"):
                if dataset.get(key) not in (None, ""):
                    metadata[key] = dataset.get(key)

        if dataset_type in (164,):
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
            "The UNV/UFF file contains modal vectors but no coordinates for "
            f"{len(missing)} nodes (for example: {sample}). "
            "Export geometry together with modal data from Simcenter Testlab."
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
        },
    )


def load_universal_modal_file(file_path: Path) -> ModalDataset:
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

    if not modes:
        found = ", ".join(str(value) for value in sorted(set(metadata["dataset_types"])))
        detail = f" Detected dataset types: {found}." if found else ""
        if errors:
            detail += " " + " | ".join(errors[:3])
        raise ValueError(
            "No experimental mode shapes were found in the UNV/UFF file. "
            "The file must include geometry (dataset 15 or 2411) and modal data "
            f"(dataset 55 or modal dataset 2414).{detail}"
        )

    modes.sort(key=lambda mode: mode.number)
    metadata["mode_count"] = len(modes)
    metadata["import_warnings"] = errors

    return ModalDataset(
        source_name="Simcenter Testlab UNV/UFF",
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
