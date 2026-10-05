"""Validated extraction to FE shape packs — Auto-ID M4.6 (approved design, M4_DECISION_RECORD.md §6).

Brings the ODB shape-extraction gate's validated pack build into the repository:

- the raw extraction is the pinned, unchanged ``abaqus_scripts/extract_odb.py`` format 2
  (executor injectable; the real one runs it through ``abaqus_bridge.run_abaqus_extraction``
  as an execution helper only — the ``abaqus_bridge`` path/mtime cache is never used);
- checks: modes and history complete, values finite and real, FE geometry identity and node
  count, exact EIGFREQ frequencies, the measured-surface node set equal to the expected
  (registration) subset, lossless storage, deterministic content hash on reload;
- the pack (``auto-id/fe-shape-pack/v1``) and its record are written; the raw extraction is
  deleted after the pack validates (retention rule).

No new extractor: any other Abaqus Python script needs a separate gate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import hashlib
import json
from pathlib import Path
import shutil
from typing import Callable, Mapping, Sequence

import numpy as np

from domain.identification_run import canonical_hash
from scientific_state import fe_geometry_identity

from .fe_shape_pack import (
    SHAPE_PACK_RECORD_SCHEMA,
    FEShapePack,
    load_shape_pack_file,
    node_set_sha256,
    parse_shape_pack_record,
    shape_pack_content_sha256,
)


PINNED_EXTRACT_SCRIPT = "abaqus_scripts/extract_odb.py"
PINNED_EXTRACT_SCRIPT_SHA256 = "039aa067adeac83e457ccacc9036c767f98c41517fb1ffdd5293fdd01dc6534d"
RUN_STORE = "auto-id-run"
ExtractionExecutor = Callable[[Path, Path, int, int], Path]  # (odb, raw directory, start, end) -> manifest.json


class ExtractionRefusal(Exception):
    """An extraction does not validate; no pack is produced.  Not a ValueError/RuntimeError."""


@dataclass(frozen=True)
class ExtractionExpectation:
    surface_instance: str
    surface_side: str  # "max_z" | "min_z"
    surface_tolerance: float  # model units (1e-4 mm in mm models)
    fe_geometry_sha256: str
    fe_node_count: int
    node_set_sha256: str  # the registration's FE mapping-node subset fingerprint
    node_count: int
    mode_numbers: tuple[int, ...]


@dataclass(frozen=True)
class ExtractionRecord:
    job_name: str
    extraction_id: str
    odb_sha256: str
    script_sha256: str
    abaqus_release: str
    pack_content_sha256: str
    pack_file_sha256: str
    node_set_sha256: str
    checks: Mapping[str, bool]
    raw_deleted: bool

    def to_dict(self) -> dict:
        return asdict(self)


def extraction_identity(odb_sha256: str, abaqus_release: str, mode_numbers: Sequence[int]) -> str:
    return canonical_hash({"odb_sha256": odb_sha256, "script_sha256": PINNED_EXTRACT_SCRIPT_SHA256,
                           "abaqus_release": abaqus_release, "start_mode": min(mode_numbers),
                           "end_mode": max(mode_numbers), "format_version": 2})


def pinned_script_executor(repository: Path, abaqus_command: str, timeout_seconds: int = 7200) -> ExtractionExecutor:
    """Real Abaqus Python extraction (use only under an authorised HUMAN gate)."""

    script = Path(repository) / PINNED_EXTRACT_SCRIPT
    if hashlib.sha256(script.read_bytes()).hexdigest() != PINNED_EXTRACT_SCRIPT_SHA256:
        raise ExtractionRefusal("extract_odb.py differs from the pinned, validated script.")

    def run(odb: Path, raw: Path, start: int, end: int) -> Path:
        from abaqus_bridge import run_abaqus_extraction  # execution helper only; its cache is not used

        return Path(run_abaqus_extraction(odb, raw, abaqus_command=abaqus_command, start_mode=start, end_mode=end,
                                          timeout_seconds=timeout_seconds))

    return run


def _read_table(path: Path, numeric_columns: Sequence[int]):
    instances = np.loadtxt(path, delimiter=",", skiprows=1, usecols=0, dtype=str, encoding="utf-8", ndmin=1)
    labels = np.loadtxt(path, delimiter=",", skiprows=1, usecols=1, dtype=np.int64, ndmin=1)
    values = np.loadtxt(path, delimiter=",", skiprows=1, usecols=numeric_columns, dtype=np.float64, ndmin=2)
    return instances, labels, values


def build_shape_pack_arrays(raw: Path, expectation: ExtractionExpectation) -> tuple[dict, dict]:
    """Arrays of a shape pack from a format-2 raw extraction, with the gate's checks."""

    raw = Path(raw)
    manifest = json.loads((raw / "manifest.json").read_text(encoding="utf-8"))
    g_instances, g_labels, g_xyz = _read_table(raw / "geometry.csv", (2, 3, 4))
    node_ids = np.char.add(np.char.add(g_instances, ":"), g_labels.astype(str))
    z = g_xyz[:, 2]
    selected = g_instances == expectation.surface_instance
    checks = {"format_version_2": manifest.get("format_version") == 2, "surface_instance_present": bool(selected.any())}
    if not selected.any():
        return {}, checks
    level = float(z[selected].max() if expectation.surface_side == "max_z" else z[selected].min())
    rows = np.flatnonzero(selected & (np.abs(z - level) <= expectation.surface_tolerance))
    order = np.argsort(node_ids[rows])
    rows = rows[order]
    entries = {int(item["mode"]): item for item in manifest["modes"]}
    history = next((item for item in manifest.get("history", ()) if item.get("name") == "EIGFREQ"), None)
    history_hz = {int(a): float(b) for a, b in history["data"]} if history else {}
    checks["modes_complete"] = set(expectation.mode_numbers) <= set(entries)
    checks["history_complete"] = set(expectation.mode_numbers) <= set(history_hz)
    if not (checks["modes_complete"] and checks["history_complete"]):
        return {}, checks
    displacements = np.empty((len(expectation.mode_numbers), len(rows), 3))
    finite = imaginary_zero = rows_match = True
    worst = 0.0
    for k, mode in enumerate(expectation.mode_numbers):
        m_instances, m_labels, values = _read_table(raw / entries[mode]["file"], (2, 3, 4, 5, 6, 7))
        rows_match &= np.array_equal(m_instances, g_instances) and np.array_equal(m_labels, g_labels)
        finite &= bool(np.isfinite(values).all())
        imaginary_zero &= bool(np.all(values[:, 3:] == 0.0))
        real = values[:, :3]
        scale = np.maximum(np.abs(real), np.finfo(np.float64).tiny)
        worst = max(worst, float(np.max(np.abs(real.astype(np.float32).astype(np.float64) - real) / scale)))
        displacements[k] = real[rows]
    identity = fe_geometry_identity(node_ids.tolist(), g_xyz)
    surface_ids = node_ids[rows]
    lossless32 = worst <= 1.0e-15
    checks.update({
        "mode_rows_match_geometry": bool(rows_match), "finite": finite, "imaginary_zero": imaginary_zero,
        "fe_geometry_identity": identity["sha256"] == expectation.fe_geometry_sha256
        and identity["node_count"] == expectation.fe_node_count,
        "node_set": node_set_sha256(surface_ids.tolist()) == expectation.node_set_sha256
        and len(surface_ids) == expectation.node_count,
    })
    arrays = {"node_ids": surface_ids, "coordinates": g_xyz[rows],
              "mode_numbers": np.array(expectation.mode_numbers, dtype=np.int32),
              "frequencies_hz": np.array([history_hz[m] for m in expectation.mode_numbers]),
              "displacements": displacements.astype(np.float32) if lossless32 else displacements}
    return arrays, checks


def extract_shape_pack(job_name: str, generated_inp_sha256: str, odb: Path, odb_sha256: str, odb_size: int,
                       expectation: ExtractionExpectation, packs_directory: Path, executor: ExtractionExecutor,
                       abaqus_release: str) -> tuple[FEShapePack, ExtractionRecord]:
    """Raw extraction → validated pack + record; the raw extraction is deleted after validation."""

    packs_directory = Path(packs_directory)
    packs_directory.mkdir(parents=True, exist_ok=True)
    raw = packs_directory / f"raw_{job_name}"
    if raw.exists():
        shutil.rmtree(raw)
    executor(Path(odb), raw, min(expectation.mode_numbers), max(expectation.mode_numbers))
    arrays, checks = build_shape_pack_arrays(raw, expectation)
    if not arrays or not all(checks.values()):
        raise ExtractionRefusal(f"{job_name}: extraction does not validate {checks}.")
    content = shape_pack_content_sha256(arrays)
    pack_path = packs_directory / f"{job_name}.npz"
    np.savez(pack_path, **arrays)
    with np.load(pack_path, allow_pickle=False) as data:
        checks["deterministic_content"] = shape_pack_content_sha256({k: data[k] for k in data.files}) == content
    if not checks["deterministic_content"]:
        raise ExtractionRefusal(f"{job_name}: pack content changed on reload.")
    file_sha = hashlib.sha256(pack_path.read_bytes()).hexdigest()
    identity = extraction_identity(odb_sha256, abaqus_release, expectation.mode_numbers)
    record = {
        "schema": SHAPE_PACK_RECORD_SCHEMA, "job_name": job_name, "specimen": job_name.split("_")[0],
        "state": "CANDIDATE", "generated_inp_sha256": generated_inp_sha256,
        "odb": {"role": "candidate ODB", "file_name": f"{job_name}.odb", "sha256": odb_sha256, "size_bytes": odb_size,
                "location": {"store": RUN_STORE, "relative_path": f"solves/{job_name}/{job_name}.odb"}},
        "pack": {"role": "FE shape pack (auto-id/fe-shape-pack/v1)", "file_name": pack_path.name, "sha256": file_sha,
                 "size_bytes": pack_path.stat().st_size,
                 "location": {"store": RUN_STORE, "relative_path": f"packs/{pack_path.name}"}},
        "content_sha256": content,
        "node_set": {"definition": f"{expectation.surface_instance}, {expectation.surface_side}, "
                                   f"tolerance {expectation.surface_tolerance} model units",
                     "node_count": expectation.node_count, "sha256": expectation.node_set_sha256},
        "fe_geometry_sha256": expectation.fe_geometry_sha256,
        "mode_numbers": list(expectation.mode_numbers),
        "frequencies_hz": arrays["frequencies_hz"].tolist(),
        "extraction": {"script": PINNED_EXTRACT_SCRIPT, "script_sha256": PINNED_EXTRACT_SCRIPT_SHA256,
                       "abaqus": abaqus_release, "extraction_id": identity, "format_version": 2},
        "validation": {name: bool(value) for name, value in checks.items()},
        "provenance_record": {"role": "identification run journal (hash-chained; this pack's extraction entry)",
                              "location": {"store": RUN_STORE, "relative_path": "journal.json"}},
    }
    record_path = packs_directory / f"{job_name}.shape-pack.json"
    record_path.write_text(json.dumps(record, indent=1), encoding="utf-8")
    pack = load_shape_pack_file(pack_path, parse_shape_pack_record(record))
    shutil.rmtree(raw)  # retention: raw extraction is temporary validation material
    return pack, ExtractionRecord(job_name, identity, odb_sha256, PINNED_EXTRACT_SCRIPT_SHA256, abaqus_release,
                                  content, file_sha, expectation.node_set_sha256, dict(checks), True)


def load_run_pack(packs_directory: Path, job_name: str, expected_content_sha256: str) -> FEShapePack:
    """Reuse a journalled pack: file SHA-256 and content hash are re-verified."""

    record = parse_shape_pack_record(json.loads((Path(packs_directory) / f"{job_name}.shape-pack.json")
                                                .read_text(encoding="utf-8")))
    pack_path = Path(packs_directory) / record.pack.file_name
    if record.content_sha256 != expected_content_sha256 or \
            hashlib.sha256(pack_path.read_bytes()).hexdigest() != record.pack.sha256:
        raise ExtractionRefusal(f"{job_name}: the pack on disk differs from the journal; not reused.")
    return load_shape_pack_file(pack_path, record)
