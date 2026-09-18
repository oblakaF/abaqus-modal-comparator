from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
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
