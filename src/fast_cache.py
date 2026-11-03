from __future__ import annotations

import gzip
import hashlib
import json
import os
import pickle
import shutil
import tempfile
import time
from copy import deepcopy
from dataclasses import MISSING, fields
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

import abaqus_bridge
import universal_reader
from modal_core import ModalDataset, ModeShape


_INSTALLED = False
_MEMORY_UNV: Dict[str, ModalDataset] = {}
_RUNTIME_METADATA_KEYS = {
    "unv_cache_reused",
    "unv_load_seconds",
    "unv_cache_write_failed",
    "binary_odb_cache_reused",
    "odb_dataset_load_seconds",
    "binary_odb_cache_write_failed",
    "unv_cache_write_skipped",
    "binary_odb_cache_write_skipped",
}

# Without a folder the user chose, only small entries go to the per-user cache. The size is the dataset's arrays in
# memory, an upper estimate of the compressed file; the M11 package (10201 nodes, 20 modes) is well below this limit.
IMPLICIT_CACHE_LIMIT_BYTES = 64 * 1024 * 1024
CACHE_FREE_SPACE_RESERVE_BYTES = 200 * 1024 * 1024
SKIPPED_LARGE = "large_without_chosen_folder"
SKIPPED_LOW_SPACE = "low_disk_space"
_CACHE_FOLDER: Optional[Path] = None


def set_cache_folder(folder) -> Optional[Path]:
    """The user's cache folder, or None for no explicit choice. The folder is created only when an entry is written."""
    global _CACHE_FOLDER
    text = "" if folder is None else str(folder).strip()
    if not text:
        _CACHE_FOLDER = None
        return None
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise ValueError(f"The cache folder must be a full path: {text}")
    if path.exists() and not path.is_dir():
        raise ValueError(f"The cache folder is a file: {text}")
    _CACHE_FOLDER = path.resolve()
    return _CACHE_FOLDER


def cache_folder() -> Optional[Path]:
    return _CACHE_FOLDER


def _schema_fingerprint() -> str:
    """Fingerprint cached dataclasses so field changes invalidate old files."""
    payload = []
    for data_class in (ModeShape, ModalDataset):
        class_fields = []
        for item in fields(data_class):
            default = "<missing>" if item.default is MISSING else repr(item.default)
            factory = (
                "<missing>"
                if item.default_factory is MISSING
                else repr(item.default_factory)
            )
            class_fields.append(
                {
                    "name": item.name,
                    "type": str(item.type),
                    "default": default,
                    "factory": factory,
                }
            )
        payload.append({"class": data_class.__name__, "fields": class_fields})
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


# _schema_fingerprint() only catches ModeShape/ModalDataset FIELD-shape changes.
# A semantic change to the derivation algorithm (peak detection, coherence
# handling, CMIF/SVD separation, quality-control thresholds, coordinate-system
# handling, and so on) does not change those dataclasses' fields, so without
# this separate marker an on-disk cache from before the change would keep
# being served after an update. Bump this by hand whenever such logic changes.
_ANALYSIS_PIPELINE_VERSION = "2026.10.13.1-eigfreq-history-frequencies"

_CACHE_VERSION = (
    f"modal-cache-v5-{_ANALYSIS_PIPELINE_VERSION}-" + _schema_fingerprint()
)

# A UNV-importer change that does not concern the FE/ODB side (for example
# APP-IMPORT-2414: normal modes read from pyuff's positional dataset-2414
# layout, which an older parse returned as FRF-only data or no modes) is marked
# here instead of in _CACHE_VERSION, so the extracted-ODB cache keeps its
# identity. Old UNV entries stay on disk but are no longer looked up. Bump this
# by hand whenever the UNV import result for an unchanged file changes.
_UNV_IMPORTER_VERSION = "2026.10.26.1-dataset2414-positional-layout"


def _atomic_pickle_dump(value: Any, destination: Path, compressed: bool) -> None:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    opener = gzip.open if compressed else open
    try:
        with opener(temporary, "wb") as stream:
            pickle.dump(value, stream, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(temporary, destination)
    except BaseException:  # a full disk must not keep the partial file of this write
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def _pickle_load(source: Path, compressed: bool) -> Any:
    opener = gzip.open if compressed else open
    with opener(source, "rb") as stream:
        return pickle.load(stream)


def _file_signature(path: Path) -> Dict[str, Any]:
    path = Path(path).resolve()
    stat = path.stat()
    return {
        "path": str(path),
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }


def _user_cache_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        root = Path(local_app_data) / "AbaqusModalComparator" / "cache"
    else:
        root = Path(tempfile.gettempdir()) / "AbaqusModalComparator" / "cache"
    root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(root, 0o700)
    except OSError:
        pass
    return root.resolve()


def _user_cache_path(file_name: str) -> Path:
    root = _user_cache_root()
    candidate = (root / file_name).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError("Cache path escaped the current-user cache directory.") from error
    return candidate


def _lookup_paths(file_name: str) -> list:
    """Where an entry may be read from: the chosen folder first, then the per-user cache."""
    paths = [] if _CACHE_FOLDER is None else [_CACHE_FOLDER / file_name]
    return paths + [_user_cache_path(file_name)]


def _estimated_cache_bytes(dataset: ModalDataset) -> int:
    total = 0
    for mode in dataset.modes:
        for array in (mode.coordinates, mode.vectors, getattr(mode, "measured_dofs", None)):
            total += int(getattr(array, "nbytes", 0))
        total += 64 * len(mode.node_ids)  # node ids are Python strings, not counted by nbytes
    return total


def _has_room(folder: Path, needed_bytes: int) -> bool:
    existing = Path(folder)
    while not existing.exists() and existing.parent != existing:
        existing = existing.parent
    try:
        return shutil.disk_usage(existing).free >= needed_bytes + CACHE_FREE_SPACE_RESERVE_BYTES
    except OSError:
        return False


def _store_entry(file_name: str, payload: Dict[str, Any], canonical: ModalDataset) -> Optional[str]:
    """Write an entry where policy allows. Returns why it was skipped, or None; OSError means the write failed."""
    estimate = _estimated_cache_bytes(canonical)
    if _CACHE_FOLDER is None and estimate > IMPLICIT_CACHE_LIMIT_BYTES:
        return SKIPPED_LARGE
    path = _user_cache_path(file_name) if _CACHE_FOLDER is None else _CACHE_FOLDER / file_name
    if not _has_room(path.parent, estimate):
        return SKIPPED_LOW_SPACE
    _atomic_pickle_dump(payload, path, compressed=True)
    return None


def _clean_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    copied = deepcopy(dict(metadata))
    for key in _RUNTIME_METADATA_KEYS:
        copied.pop(key, None)
    return copied


def _clone_mode(mode: ModeShape) -> ModeShape:
    clone = ModeShape(
        number=mode.number,
        frequency_hz=mode.frequency_hz,
        node_ids=mode.node_ids,
        coordinates=mode.coordinates,
        vectors=mode.vectors,
        damping_ratio=mode.damping_ratio,
        modal_mass=mode.modal_mass,
        metadata=deepcopy(dict(mode.metadata)),
    )
    measured_dofs = getattr(mode, "measured_dofs", None)
    if measured_dofs is not None:
        clone.measured_dofs = measured_dofs
    return clone


def _clone_dataset(dataset: ModalDataset) -> ModalDataset:
    """Clone mutable containers while sharing the large numerical arrays."""
    return ModalDataset(
        source_name=dataset.source_name,
        source_path=dataset.source_path,
        modes=[_clone_mode(mode) for mode in dataset.modes],
        metadata=_clean_metadata(dataset.metadata),
        history=deepcopy(list(dataset.history)),
    )


def _unv_cache_key(
    file_path: Path,
    target_frequencies: Optional[Sequence[float]],
    target_count: Optional[int],
    modal_set: Optional[str],
) -> str:
    # target_frequencies/target_count are legacy compatibility inputs. They no
    # longer affect UNV import, so they must not fragment cache identity.
    del target_frequencies, target_count
    payload = {
        "version": _CACHE_VERSION,
        "unv_importer": _UNV_IMPORTER_VERSION,
        "source": _file_signature(file_path),
        "modal_set": None if modal_set is None else str(modal_set),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _returned_dataset(
    canonical: ModalDataset,
    cache_source,
    started: float,
    load_key: str,
) -> ModalDataset:
    dataset = _clone_dataset(canonical)
    dataset.metadata[load_key] = cache_source
    if load_key == "unv_cache_reused":
        dataset.metadata["unv_load_seconds"] = time.perf_counter() - started
    else:
        dataset.metadata["odb_dataset_load_seconds"] = time.perf_counter() - started
    return dataset


def _cached_universal_loader(
    file_path: Path,
    target_frequencies: Optional[Sequence[float]] = None,
    target_count: Optional[int] = None,
    modal_set: Optional[str] = None,
):
    source = Path(file_path).resolve()
    key = _unv_cache_key(source, target_frequencies, target_count, modal_set)
    started = time.perf_counter()

    canonical = _MEMORY_UNV.get(key)
    if canonical is not None:
        return _returned_dataset(canonical, "memory", started, "unv_cache_reused")

    file_name = f"unv_{key}.pkl.gz"
    for cache_path in _lookup_paths(file_name):
        if not cache_path.exists():
            continue
        try:
            payload = _pickle_load(cache_path, compressed=True)
            if payload.get("version") == _CACHE_VERSION:
                canonical = _clone_dataset(payload["dataset"])
                _MEMORY_UNV[key] = canonical
                return _returned_dataset(canonical, "disk", started, "unv_cache_reused")
        except Exception:
            pass  # an unreadable entry is left in place; a new write replaces it

    loaded = _ORIGINAL_UNIVERSAL_LOADER(
        source,
        modal_set=modal_set,
    )
    canonical = _clone_dataset(loaded)
    try:
        skipped = _store_entry(file_name, {"version": _CACHE_VERSION, "dataset": canonical}, canonical)
    except OSError:
        returned = _returned_dataset(canonical, False, started, "unv_cache_reused")
        returned.metadata["unv_cache_write_failed"] = True
        _MEMORY_UNV[key] = canonical
        return returned

    _MEMORY_UNV[key] = canonical
    returned = _returned_dataset(canonical, False, started, "unv_cache_reused")
    if skipped:
        returned.metadata["unv_cache_write_skipped"] = skipped
    return returned


def _manifest_signature(manifest_path: Path) -> Dict[str, Any]:
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = []
    for item in manifest.get("modes", []):
        path = manifest_path.parent / item["file"]
        files.append(_file_signature(path))
    geometry_file = manifest.get("geometry_file")
    geometry_signature = (
        _file_signature(manifest_path.parent / geometry_file)
        if geometry_file
        else None
    )
    return {
        "version": _CACHE_VERSION,
        "manifest": _file_signature(manifest_path),
        "mode_files": files,
        "geometry_file": geometry_signature,
    }


def _raise_if_cancelled(cancel_event) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise abaqus_bridge.AnalysisCancelled("Analysis stopped by user.")


def _cached_extracted_odb_loader(manifest_path: Path, cancel_event=None):
    _raise_if_cancelled(cancel_event)
    manifest_path = Path(manifest_path).resolve()
    signature = _manifest_signature(manifest_path)
    signature_text = json.dumps(signature, sort_keys=True)
    key = hashlib.sha256(signature_text.encode("utf-8")).hexdigest()
    file_name = f"odb_{key}.pkl.gz"
    started = time.perf_counter()

    for cache_path in _lookup_paths(file_name):
        if not cache_path.exists():
            continue
        try:
            payload = _pickle_load(cache_path, compressed=True)
        except Exception:
            pass  # an unreadable entry is left in place; a new write replaces it
        else:
            _raise_if_cancelled(cancel_event)
            if payload.get("signature") == signature:
                canonical = _clone_dataset(payload["dataset"])
                returned = _returned_dataset(
                    canonical, True, started, "binary_odb_cache_reused"
                )
                _raise_if_cancelled(cancel_event)
                return returned

    loaded = _ORIGINAL_EXTRACTED_ODB_LOADER(
        manifest_path,
        cancel_event=cancel_event,
    )
    canonical = _clone_dataset(loaded)
    try:
        skipped = _store_entry(file_name, {"signature": signature, "dataset": canonical}, canonical)
    except OSError:
        returned = _returned_dataset(
            canonical,
            False,
            started,
            "binary_odb_cache_reused",
        )
        returned.metadata["binary_odb_cache_write_failed"] = True
        _raise_if_cancelled(cancel_event)
        return returned

    returned = _returned_dataset(canonical, False, started, "binary_odb_cache_reused")
    if skipped:
        returned.metadata["binary_odb_cache_write_skipped"] = skipped
    _raise_if_cancelled(cancel_event)
    return returned


def install_fast_cache() -> None:
    global _INSTALLED, _ORIGINAL_UNIVERSAL_LOADER, _ORIGINAL_EXTRACTED_ODB_LOADER
    if _INSTALLED:
        return

    _ORIGINAL_UNIVERSAL_LOADER = universal_reader.load_universal_modal_file
    universal_reader.load_universal_modal_file = _cached_universal_loader

    _ORIGINAL_EXTRACTED_ODB_LOADER = abaqus_bridge.load_extracted_odb
    abaqus_bridge.load_extracted_odb = _cached_extracted_odb_loader
    _INSTALLED = True
