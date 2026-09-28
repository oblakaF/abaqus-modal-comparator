from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat as stat_module
from typing import Any, Mapping, Optional, Sequence

import numpy as np


def experimental_source_identity(path: str | Path) -> Optional[dict[str, Any]]:
    """Return the persisted identity of an experimental source file.

    Path, size, and modification time match the application's existing cache
    identity convention.  Missing files are deliberately not bindable
    scientific sources.
    """
    text = str(path).strip()
    if not text:
        return None
    source = Path(text).expanduser().resolve(strict=False)
    try:
        stat = source.stat()
    except OSError:
        return None
    return {
        "path": os.path.normcase(str(source)),
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }


# SHA-256 digests keyed by (normalized path, size, mtime_ns).  The key only
# decides when a file must be re-read; the identity itself is the digest.
_CONTENT_HASH_CACHE: dict[tuple[str, int, int], str] = {}
_CONTENT_HASH_CACHE_LIMIT = 256
_CONTENT_HASH_CHUNK_BYTES = 1 << 20


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(_CONTENT_HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def experimental_source_content_identity(
    path: str | Path,
) -> Optional[dict[str, Any]]:
    """Return a content-based identity of an experimental source file.

    Extends the legacy ``experimental_source_identity`` keys with the SHA-256
    of the file content, so ``source_identity_matches`` still accepts existing
    saved bindings.  Missing, empty, and non-regular paths (directories) are
    not bindable and return None.  A file that changes while it is being
    hashed also returns None rather than an identity of mixed state.
    """
    text = str(path).strip()
    if not text:
        return None
    source = Path(text).expanduser().resolve(strict=False)
    try:
        before = source.stat()
    except OSError:
        return None
    if not stat_module.S_ISREG(before.st_mode):
        return None
    normalized = os.path.normcase(str(source))
    key = (normalized, int(before.st_size), int(before.st_mtime_ns))
    digest = _CONTENT_HASH_CACHE.get(key)
    if digest is None:
        try:
            digest = _file_sha256(source)
            after = source.stat()
        except OSError:
            return None
        if (int(after.st_size), int(after.st_mtime_ns)) != key[1:]:
            return None
        if len(_CONTENT_HASH_CACHE) >= _CONTENT_HASH_CACHE_LIMIT:
            _CONTENT_HASH_CACHE.pop(next(iter(_CONTENT_HASH_CACHE)))
        _CONTENT_HASH_CACHE[key] = digest
    return {
        "path": normalized,
        "size": key[1],
        "mtime_ns": key[2],
        "sha256": digest,
    }


def source_identity_matches(left: object, right: object) -> bool:
    if not isinstance(left, Mapping) or not isinstance(right, Mapping):
        return False
    required = ("path", "size", "mtime_ns")
    return all(left.get(key) == right.get(key) for key in required)


FE_GEOMETRY_IDENTITY_SCHEMA = "fe-geometry-identity/1"
FE_DOF_COMPONENTS = ("U1", "U2", "U3")

# One canonical record per node, big-endian and packed:
# instance index (uint32), node label (int64), x/y/z (float64), DOF bits (uint8,
# bit 0 = U1, bit 1 = U2, bit 2 = U3).
_FE_GEOMETRY_RECORD = np.dtype(
    [("instance", ">u4"), ("label", ">i8"), ("xyz", ">f8", (3,)), ("dofs", "u1")]
)


def _split_fe_node_id(node_id: object) -> tuple[str, int]:
    if not isinstance(node_id, str):
        raise ValueError(f"FE node id must be an 'INSTANCE:label' string: {node_id!r}")
    instance, separator, label = node_id.rpartition(":")
    if not separator or not instance:
        raise ValueError(f"FE node id has no instance name: {node_id!r}")
    try:
        return instance, int(label)
    except ValueError as error:
        raise ValueError(f"FE node label is not an integer: {node_id!r}") from error


def fe_geometry_identity(
    node_ids: Sequence[object],
    coordinates: object,
    dof_mask: object,
) -> dict[str, Any]:
    """Return a deterministic identity of FE registration geometry.

    Only node identity ("INSTANCE:label"), node coordinates, and the explicit
    per-node translational DOF map enter the SHA-256.  The result is
    independent of input node order; coordinates are hashed as exact IEEE-754
    float64 values (with -0.0 folded to 0.0), not as formatted text.
    """
    parsed = [_split_fe_node_id(node_id) for node_id in node_ids]
    count = len(parsed)
    xyz = np.asarray(coordinates, dtype=float)
    if xyz.shape != (count, 3):
        raise ValueError("FE coordinates must have shape (node_count, 3).")
    if not np.all(np.isfinite(xyz)):
        raise ValueError("FE coordinates must be finite.")
    mask = np.asarray(dof_mask)
    if mask.dtype != np.bool_:
        raise TypeError("FE DOF map must be a boolean array.")
    if mask.shape != (count, len(FE_DOF_COMPONENTS)):
        raise ValueError("FE DOF map must have shape (node_count, 3).")

    instances = sorted({instance for instance, _ in parsed})
    instance_index = {name: index for index, name in enumerate(instances)}
    records = np.empty(count, dtype=_FE_GEOMETRY_RECORD)
    records["instance"] = [instance_index[instance] for instance, _ in parsed]
    records["label"] = [label for _, label in parsed]
    records["xyz"] = xyz + 0.0
    records["dofs"] = mask.astype(np.uint8) @ np.array([1, 2, 4], dtype=np.uint8)
    records = records[np.lexsort((records["label"], records["instance"]))]
    duplicate = (np.diff(records["instance"].astype(np.int64)) == 0) & (
        np.diff(records["label"]) == 0
    )
    if np.any(duplicate):
        raise ValueError("FE node ids must be unique.")

    digest = hashlib.sha256()
    digest.update(FE_GEOMETRY_IDENTITY_SCHEMA.encode("ascii") + b"\n")
    digest.update(",".join(FE_DOF_COMPONENTS).encode("ascii") + b"\n")
    digest.update(len(instances).to_bytes(4, "big"))
    for name in instances:
        encoded = name.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big") + encoded)
    digest.update(count.to_bytes(8, "big"))
    digest.update(records.tobytes())
    return {
        "schema_version": FE_GEOMETRY_IDENTITY_SCHEMA,
        "node_count": count,
        "instances": instances,
        "dof_components": list(FE_DOF_COMPONENTS),
        "dof_count": int(np.count_nonzero(mask)),
        "sha256": digest.hexdigest(),
    }


def modal_dataset_geometry_identity(dataset: object) -> dict[str, Any]:
    """Return the FE geometry identity shared by every mode of a dataset.

    Frequencies, mode vectors, and all dataset/mode metadata are ignored.  Each
    mode must carry an explicit ``measured_dofs`` map (it is never inferred)
    and all modes must describe the same geometry.
    """
    modes = list(getattr(dataset, "modes", None) or ())
    if not modes:
        raise ValueError("FE geometry identity requires at least one mode.")

    def mode_inputs(mode: object) -> tuple[Any, Any, Any]:
        mask = getattr(mode, "measured_dofs", None)
        if mask is None:
            raise ValueError(
                f"Mode {getattr(mode, 'number', '?')} has no explicit DOF map "
                "(measured_dofs); it is not inferred."
            )
        return mode.node_ids, mode.coordinates, mask

    reference_inputs = mode_inputs(modes[0])
    reference = fe_geometry_identity(*reference_inputs)
    for mode in modes[1:]:
        inputs = mode_inputs(mode)
        if all(
            np.array_equal(np.asarray(current), np.asarray(expected))
            for current, expected in zip(inputs, reference_inputs)
        ):
            continue
        if fe_geometry_identity(*inputs) != reference:
            raise ValueError("All modes must share the same FE geometry and DOF map.")
    return reference


def calibration_fingerprint(calibration: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(calibration), sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def geometry_candidate_id(candidate: Mapping[str, Any]) -> str:
    """Stable geometry-only candidate ID; never includes modal evidence."""
    payload = {
        "rotation": candidate.get("rotation"),
        "translation": candidate.get("translation"),
        "coordinate_scales": candidate.get("coordinate_scales"),
        "axis_permutation": candidate.get("axis_permutation"),
        "determinant": candidate.get("determinant"),
        "mirrored": candidate.get("mirrored"),
        "calibration": candidate.get("calibration"),
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return "geometry-" + hashlib.sha256(encoded).hexdigest()[:16]


def orientation_registration_valid(
    registration: object,
    source_identity: object,
    calibration: Mapping[str, Any],
) -> bool:
    if not isinstance(registration, Mapping):
        return False
    return (
        registration.get("orientation_source") == "user_confirmed"
        and source_identity_matches(
            registration.get("experimental_source_identity"), source_identity
        )
        and registration.get("calibration_fingerprint")
        == calibration_fingerprint(calibration)
        and isinstance(registration.get("candidate"), Mapping)
        and bool(registration["candidate"].get("candidate_id"))
    )
