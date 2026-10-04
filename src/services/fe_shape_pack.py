"""Validated FE shape packs — Auto-ID M4.2 integration (ODB shape-extraction gate, HUMAN-authorised 2026-10-04).

A shape pack (schema ``auto-id/fe-shape-pack/v1``, NumPy ``.npz`` without pickle) holds the elastic FE
modes of one solved forward job on the passport's measured outer surface:

- ``node_ids``        "INSTANCE:label", sorted;
- ``coordinates``     (n, 3) float64, model units;
- ``mode_numbers``    (k,) int32;
- ``frequencies_hz``  (k,) float64, the exact ODB eigenfrequencies (history output EIGFREQ);
- ``displacements``   (k, n, 3) U1/U2/U3 (float32 when the ODB is single precision; lossless).

Each pack is pinned by a repository record (schema ``auto-id/fe-shape-pack-record/v1``): the pack file
(store + relative path, SHA-256, size), its **content hash** (independent of the zip layout), the
node-set hash, the ODB and job identities, and the gate's validation summary.  Loading verifies the
file SHA-256, the content hash, the node-set hash and the frequencies against the record; any
difference is refused, never repaired.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping

import numpy as np

from domain.experiment_fixture import ExternalFileReference, FixtureManifestError, resolve_external_file
from domain.experiment_fixture import _file as _external_file


SHAPE_PACK_SCHEMA = "auto-id/fe-shape-pack/v1"
SHAPE_PACK_RECORD_SCHEMA = "auto-id/fe-shape-pack-record/v1"
PACK_ARRAYS = ("node_ids", "coordinates", "mode_numbers", "frequencies_hz", "displacements")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_RECORD_KEYS = {"schema", "job_name", "specimen", "state", "generated_inp_sha256", "odb", "pack",
                "content_sha256", "node_set", "fe_geometry_sha256", "mode_numbers", "frequencies_hz",
                "extraction", "validation", "provenance_record"}


class ShapePackError(ValueError):
    """A shape pack or its record is malformed or does not match its pin."""


def shape_pack_content_sha256(arrays: Mapping[str, np.ndarray]) -> str:
    """SHA-256 over (name, dtype, shape, little-endian C-order bytes) of the five arrays, in fixed order.

    Independent of the ``.npz`` (zip) layout and timestamps; identical to the extraction gate's hash.
    """
    digest = hashlib.sha256()
    for name in PACK_ARRAYS:
        array = np.ascontiguousarray(arrays[name])
        if array.dtype.kind == "U":
            payload = "\n".join(array.tolist()).encode("utf-8")
            dtype = "utf-8-lines"
        else:
            array = array.astype(array.dtype.newbyteorder("<"), copy=False)
            payload = array.tobytes(order="C")
            dtype = array.dtype.str
        digest.update(f"{name}|{dtype}|{list(array.shape)}|".encode("utf-8"))
        digest.update(hashlib.sha256(payload).digest())
    return digest.hexdigest()


def node_set_sha256(node_ids) -> str:
    """Same definition as the registration's FE mapping-node subset fingerprint (sorted ids, newline-joined)."""
    return hashlib.sha256("\n".join(sorted(str(value) for value in node_ids)).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ShapePackRecord:
    job_name: str
    specimen: str
    state: str
    generated_inp_sha256: str
    odb: ExternalFileReference
    pack: ExternalFileReference
    content_sha256: str
    node_set_count: int
    node_set_sha256: str
    node_set_definition: str
    fe_geometry_sha256: str
    mode_numbers: tuple[int, ...]
    frequencies_hz: tuple[float, ...]
    validation: Mapping[str, bool]


@dataclass(frozen=True)
class FEShapePack:
    record: ShapePackRecord
    node_ids: tuple[str, ...]
    coordinates: np.ndarray
    mode_numbers: tuple[int, ...]
    frequencies_hz: tuple[float, ...]
    displacements: np.ndarray  # (k, n, 3)

    def mode_index(self, mode: int) -> int:
        try:
            return self.mode_numbers.index(mode)
        except ValueError:
            raise ShapePackError(f"{self.record.job_name}: mode {mode} is not in the pack.") from None

    def rows(self, node_ids) -> np.ndarray:
        lookup = {node: i for i, node in enumerate(self.node_ids)}
        missing = [str(node) for node in node_ids if str(node) not in lookup]
        if missing:
            raise ShapePackError(f"{self.record.job_name}: {len(missing)} nodes not in the pack (e.g. {missing[:3]}).")
        return np.array([lookup[str(node)] for node in node_ids], dtype=int)


def _hash(value: object, field: str) -> str:
    if not isinstance(value, str) or not _HASH.match(value):
        raise ShapePackError(f"{field}: must be a 64-character lowercase hex SHA-256.")
    return value


def parse_shape_pack_record(data: object) -> ShapePackRecord:
    if not isinstance(data, Mapping) or set(data) != _RECORD_KEYS:
        found = set(data) if isinstance(data, Mapping) else set()
        raise ShapePackError(f"record: missing {sorted(_RECORD_KEYS - found)}, unknown {sorted(found - _RECORD_KEYS)}.")
    if data["schema"] != SHAPE_PACK_RECORD_SCHEMA:
        raise ShapePackError(f"schema: must be {SHAPE_PACK_RECORD_SCHEMA!r}.")
    try:
        odb = _external_file(data["odb"], "odb")
        pack = _external_file(data["pack"], "pack")
    except FixtureManifestError as exc:
        raise ShapePackError(str(exc)) from exc
    job = str(data["job_name"])
    generated = _hash(data["generated_inp_sha256"], "generated_inp_sha256")
    if not job.endswith("_" + generated[:16]) or odb.file_name != f"{job}.odb" or pack.file_name != f"{job}.npz":
        raise ShapePackError("job_name, ODB and pack names must be the content-addressed job name.")
    node_set = data["node_set"]
    if not isinstance(node_set, Mapping) or set(node_set) != {"definition", "node_count", "sha256"}:
        raise ShapePackError("node_set: needs definition, node_count and sha256.")
    modes = tuple(int(value) for value in data["mode_numbers"])
    frequencies = tuple(float(value) for value in data["frequencies_hz"])
    if len(modes) != len(frequencies) or not modes or any(not math.isfinite(f) or f <= 0 for f in frequencies):
        raise ShapePackError("mode_numbers / frequencies_hz must match and be finite and positive.")
    validation = {str(k): bool(v) for k, v in dict(data["validation"]).items()}
    if not validation or not all(validation.values()):
        raise ShapePackError(f"{job}: the extraction gate validation did not pass {validation}.")
    return ShapePackRecord(job, str(data["specimen"]), str(data["state"]), generated, odb, pack,
                           _hash(data["content_sha256"], "content_sha256"), int(node_set["node_count"]),
                           _hash(node_set["sha256"], "node_set.sha256"), str(node_set["definition"]),
                           _hash(data["fe_geometry_sha256"], "fe_geometry_sha256"), modes, frequencies, validation)


def load_shape_pack_record(path: Path) -> ShapePackRecord:
    with open(path, encoding="utf-8") as handle:
        return parse_shape_pack_record(json.load(handle))


def load_shape_pack_file(path: Path, record: ShapePackRecord) -> FEShapePack:
    """Load a pack file and verify it against its record (content, node set, modes, frequencies)."""

    with np.load(Path(path), allow_pickle=False) as data:
        if set(data.files) != set(PACK_ARRAYS):
            raise ShapePackError(f"{record.job_name}: pack arrays {sorted(data.files)} != {sorted(PACK_ARRAYS)}.")
        arrays = {name: data[name] for name in PACK_ARRAYS}
    if shape_pack_content_sha256(arrays) != record.content_sha256:
        raise ShapePackError(f"{record.job_name}: pack content hash differs from the record.")
    node_ids = tuple(str(value) for value in arrays["node_ids"].tolist())
    if list(node_ids) != sorted(node_ids) or len(set(node_ids)) != len(node_ids):
        raise ShapePackError(f"{record.job_name}: node ids must be unique and sorted.")
    if len(node_ids) != record.node_set_count or node_set_sha256(node_ids) != record.node_set_sha256:
        raise ShapePackError(f"{record.job_name}: node set differs from the record.")
    modes = tuple(int(value) for value in arrays["mode_numbers"].tolist())
    frequencies = tuple(float(value) for value in arrays["frequencies_hz"].tolist())
    if modes != record.mode_numbers or frequencies != record.frequencies_hz:
        raise ShapePackError(f"{record.job_name}: modes or frequencies differ from the record.")
    displacements = arrays["displacements"]
    if displacements.shape != (len(modes), len(node_ids), 3) or not np.all(np.isfinite(displacements)):
        raise ShapePackError(f"{record.job_name}: displacements must be finite with shape (modes, nodes, 3).")
    coordinates = np.asarray(arrays["coordinates"], dtype=float)
    if coordinates.shape != (len(node_ids), 3):
        raise ShapePackError(f"{record.job_name}: coordinates must be (nodes, 3).")
    return FEShapePack(record, node_ids, coordinates, modes, frequencies, displacements)


def load_shape_pack(record: ShapePackRecord, roots: Mapping[str, Path]) -> FEShapePack:
    """Resolve the pinned pack from its store (size + file SHA-256 verified) and load it."""
    return load_shape_pack_file(resolve_external_file(record.pack, roots), record)


def record_summary(record: ShapePackRecord) -> dict[str, Any]:
    return {"job_name": record.job_name, "content_sha256": record.content_sha256,
            "node_set_sha256": record.node_set_sha256, "file_sha256": record.pack.sha256}
