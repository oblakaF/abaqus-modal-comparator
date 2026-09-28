from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat as stat_module
from typing import Any, Mapping, Optional


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
