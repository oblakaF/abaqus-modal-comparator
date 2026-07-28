from __future__ import annotations

import gzip
import hashlib
import json
import os
import pickle
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

import abaqus_bridge
import universal_reader


_INSTALLED = False
_CACHE_VERSION = "modal-cache-v4-conservative-svd-validation"
_MEMORY_UNV: Dict[str, Any] = {}


def _atomic_pickle_dump(value: Any, destination: Path, compressed: bool) -> None:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    opener = gzip.open if compressed else open
    with opener(temporary, "wb") as stream:
        pickle.dump(value, stream, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(temporary, destination)


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
    return root


def _unv_cache_key(
    file_path: Path,
    target_frequencies: Optional[Sequence[float]],
    target_count: Optional[int],
) -> str:
    payload = {
        "version": _CACHE_VERSION,
        "source": _file_signature(file_path),
        "target_frequencies": [
            round(float(value), 8)
            for value in (target_frequencies or [])
            if value is not None
        ],
        "target_count": None if target_count is None else int(target_count),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _cached_universal_loader(
    file_path: Path,
    target_frequencies: Optional[Sequence[float]] = None,
    target_count: Optional[int] = None,
):
    source = Path(file_path).resolve()
    key = _unv_cache_key(source, target_frequencies, target_count)
    started = time.perf_counter()

    if key in _MEMORY_UNV:
        dataset = _MEMORY_UNV[key]
        dataset.metadata["unv_cache_reused"] = "memory"
        dataset.metadata["unv_load_seconds"] = time.perf_counter() - started
        return dataset

    cache_path = _user_cache_root() / f"unv_{key}.pkl.gz"
    if cache_path.exists():
        try:
            payload = _pickle_load(cache_path, compressed=True)
            if payload.get("version") == _CACHE_VERSION:
                dataset = payload["dataset"]
                dataset.metadata["unv_cache_reused"] = "disk"
                dataset.metadata["unv_load_seconds"] = time.perf_counter() - started
                _MEMORY_UNV[key] = dataset
                return dataset
        except Exception:
            try:
                cache_path.unlink()
            except OSError:
                pass

    dataset = _ORIGINAL_UNIVERSAL_LOADER(
        source,
        target_frequencies=target_frequencies,
        target_count=target_count,
    )
    dataset.metadata["unv_cache_reused"] = False
    dataset.metadata["unv_load_seconds"] = time.perf_counter() - started
    try:
        _atomic_pickle_dump(
            {"version": _CACHE_VERSION, "dataset": dataset},
            cache_path,
            compressed=True,
        )
    except OSError:
        dataset.metadata["unv_cache_write_failed"] = True
    _MEMORY_UNV[key] = dataset
    return dataset


def _manifest_signature(manifest_path: Path) -> Dict[str, Any]:
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = []
    for item in manifest.get("modes", []):
        path = manifest_path.parent / item["file"]
        files.append(_file_signature(path))
    return {
        "version": _CACHE_VERSION,
        "manifest": _file_signature(manifest_path),
        "mode_files": files,
    }


def _cached_extracted_odb_loader(manifest_path: Path):
    manifest_path = Path(manifest_path).resolve()
    signature = _manifest_signature(manifest_path)
    signature_text = json.dumps(signature, sort_keys=True)
    key = hashlib.sha256(signature_text.encode("utf-8")).hexdigest()
    cache_path = manifest_path.parent / f"modal_dataset_{key[:16]}.pickle"
    started = time.perf_counter()

    if cache_path.exists():
        try:
            payload = _pickle_load(cache_path, compressed=False)
            if payload.get("signature") == signature:
                dataset = payload["dataset"]
                dataset.metadata["binary_odb_cache_reused"] = True
                dataset.metadata["odb_dataset_load_seconds"] = time.perf_counter() - started
                return dataset
        except Exception:
            try:
                cache_path.unlink()
            except OSError:
                pass

    dataset = _ORIGINAL_EXTRACTED_ODB_LOADER(manifest_path)
    dataset.metadata["binary_odb_cache_reused"] = False
    dataset.metadata["odb_dataset_load_seconds"] = time.perf_counter() - started
    try:
        _atomic_pickle_dump(
            {"signature": signature, "dataset": dataset},
            cache_path,
            compressed=False,
        )
        # Remove stale binary caches from earlier extractions in the same directory.
        for stale in manifest_path.parent.glob("modal_dataset_*.pickle"):
            if stale != cache_path:
                try:
                    stale.unlink()
                except OSError:
                    pass
    except OSError:
        dataset.metadata["binary_odb_cache_write_failed"] = True
    return dataset


def install_fast_cache() -> None:
    global _INSTALLED, _ORIGINAL_UNIVERSAL_LOADER, _ORIGINAL_EXTRACTED_ODB_LOADER
    if _INSTALLED:
        return

    _ORIGINAL_UNIVERSAL_LOADER = universal_reader.load_universal_modal_file
    universal_reader.load_universal_modal_file = _cached_universal_loader

    _ORIGINAL_EXTRACTED_ODB_LOADER = abaqus_bridge.load_extracted_odb
    abaqus_bridge.load_extracted_odb = _cached_extracted_odb_loader
    _INSTALLED = True
