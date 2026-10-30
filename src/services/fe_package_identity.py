"""PLATE-ONLY-R2-F1: the content identity of an extracted FE package, as the loader reads it (no Qt, no import).

An extracted package is what ``abaqus_bridge.load_extracted_odb`` reads: ``manifest.json``, its ``geometry_file``
(format 2 and later) and the ``modes[].file`` of every mode entry the loader keeps (an entry whose frequency records
contradict each other is refused by the loader and its file is not read). ``dependencies`` lists exactly those files,
with the loader's own selection functions (``reliable_eigfreq``, ``manifest_frequency_problem``), so the identity
covers the data a read produced and nothing else.

``identify`` hashes the manifest and every dependency with a streaming SHA-256 (``fresh_content_identity``: chunked,
cancellable, a file that changes while it is hashed is refused). The dependency list is parsed from the very bytes
that were hashed. ``confirm`` identifies the package again and compares it with a recorded identity, file by file; a
missing, changed, added or removed dependency, or another manifest, refuses. No mode shape is imported again.

A dependency path must be a plain relative path inside the package folder: an absolute path, a drive, ``..`` or a
path that resolves outside the folder is refused (``INVALID_PATH``). The ODB named in the manifest is never read:
its hash is not part of this identity, and this identity is never presented as the ODB's.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import threading
from typing import Any, Mapping, Optional

SCHEMA = "fe-package-identity/v1"
BASIS = ("SHA-256 of manifest.json and of the geometry_file and modes[].file that abaqus_bridge.load_extracted_odb "
         "reads from it; the ODB named in the manifest is not read and its hash is not part of this identity")

NOT_A_PACKAGE = "NOT_A_PACKAGE"
INVALID_PATH = "INVALID_PATH"
MISSING = "MISSING"
UNREADABLE = "UNREADABLE"
CHANGED_DURING_READ = "CHANGED_DURING_READ"
CANCELLED = "CANCELLED"
CHANGED = "CHANGED"


class PackageIdentityRefused(ValueError):
    """No identity can be given to the package now; ``kind`` says why."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


class PackageChanged(ValueError):
    """The package on disk is not the package that was identified; ``differences`` names each file."""

    def __init__(self, message: str, differences: tuple = ()) -> None:
        super().__init__(message)
        self.kind = CHANGED
        self.differences = tuple(differences)


def _cancelled(cancel) -> bool:
    return cancel is not None and cancel.is_set()


def dependency_path(folder: Path, relative: Any) -> Path:
    """``folder / relative`` for a plain relative path inside ``folder``; else ``INVALID_PATH``."""
    if not isinstance(relative, str) or not relative.strip():
        raise PackageIdentityRefused(INVALID_PATH, f"a dependency path of the package is not a file name: {relative!r}")
    for pure in (PureWindowsPath(relative), PurePosixPath(relative)):
        if pure.is_absolute() or pure.drive or pure.root or ".." in pure.parts:
            raise PackageIdentityRefused(INVALID_PATH, f"the dependency path {relative!r} leaves the package folder")
    path = folder / relative
    try:
        inside = path.resolve().is_relative_to(folder.resolve())
    except OSError as error:
        raise PackageIdentityRefused(INVALID_PATH, f"the dependency path {relative!r} cannot be resolved: {error}")
    if not inside:
        raise PackageIdentityRefused(INVALID_PATH, f"the dependency path {relative!r} leaves the package folder")
    return path


def dependencies(manifest: Mapping[str, Any]) -> tuple:
    """((role, relative path), ...) of the files ``load_extracted_odb`` reads for ``manifest``, in its order."""
    from abaqus_bridge import manifest_frequency_problem, reliable_eigfreq

    if not isinstance(manifest, Mapping):
        raise PackageIdentityRefused(NOT_A_PACKAGE, "the manifest is not a JSON object")
    try:
        found = []
        if int(manifest.get("format_version", 1)) >= 2:
            geometry = manifest.get("geometry_file")
            if not geometry:
                raise PackageIdentityRefused(NOT_A_PACKAGE, "the manifest declares format 2 but no geometry_file")
            found.append(("geometry", geometry))
        eigfreq, _notes = reliable_eigfreq(manifest)
        for entry in manifest.get("modes", []):
            mode = int(entry["mode"])
            if manifest_frequency_problem(mode, float(entry["frequency_hz"]), entry.get("description"),
                                          eigfreq) is None:
                found.append((f"mode {mode}", entry["file"]))
    except PackageIdentityRefused:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise PackageIdentityRefused(NOT_A_PACKAGE, f"the manifest is not an extracted package: {error}") from error
    if not any(role.startswith("mode ") for role, _ in found):
        raise PackageIdentityRefused(NOT_A_PACKAGE, "the manifest lists no mode file the loader reads")
    return tuple(found)


def _hash(path: Path, cancel) -> dict:
    from services.archived_sensitivity_evidence import SensitivityCheckCancelled, fresh_content_identity

    if _cancelled(cancel):
        raise PackageIdentityRefused(CANCELLED, "cancelled")
    if not path.is_file():
        raise PackageIdentityRefused(MISSING, f"the package file {path} is missing")
    try:
        found = fresh_content_identity(path, cancel)
    except SensitivityCheckCancelled as error:
        raise PackageIdentityRefused(CANCELLED, "cancelled") from error
    except ValueError as error:
        kind = CHANGED_DURING_READ if "changed while" in str(error) else UNREADABLE
        raise PackageIdentityRefused(kind, str(error)) from error
    return {"size": int(found["size"]), "mtime_ns": int(found["mtime_ns"]), "sha256": str(found["sha256"])}


def _manifest(path: Path, cancel) -> tuple[dict, Any]:
    """The manifest's identity and its parsed content, both from the same bytes."""
    if _cancelled(cancel):
        raise PackageIdentityRefused(CANCELLED, "cancelled")
    try:
        before = path.stat()
        data = path.read_bytes()
        after = path.stat()
    except FileNotFoundError as error:
        raise PackageIdentityRefused(MISSING, f"the manifest {path} is missing") from error
    except OSError as error:
        raise PackageIdentityRefused(UNREADABLE, f"the manifest {path} cannot be read: {error}") from error
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or len(data) != before.st_size:
        raise PackageIdentityRefused(CHANGED_DURING_READ, f"the manifest {path} changed while it was being read")
    try:
        content = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PackageIdentityRefused(NOT_A_PACKAGE, f"{path} is not a JSON manifest: {error}") from error
    identity = {"size": len(data), "mtime_ns": int(before.st_mtime_ns), "sha256": hashlib.sha256(data).hexdigest()}
    return identity, content


def identify(manifest_path, cancel: Optional[threading.Event] = None) -> dict:
    """The package's identity now: the manifest and every file the loader reads (streaming SHA-256)."""
    manifest_path = Path(manifest_path)
    manifest, content = _manifest(manifest_path, cancel)
    folder = manifest_path.parent
    files = []
    for role, relative in dependencies(content):
        files.append({"role": role, "relative": relative,
                      **_hash(dependency_path(folder, relative), cancel)})
    digest = hashlib.sha256(json.dumps(
        [manifest["sha256"]] + [[f["role"], f["relative"], f["size"], f["sha256"]] for f in files]).encode("utf-8"))
    declared = content.get("odb_path") if isinstance(content, Mapping) else None
    return {"schema": SCHEMA, "manifest": {"path": str(manifest_path), **manifest}, "files": files,
            "package_sha256": digest.hexdigest(), "declared_odb_path": declared, "odb_sha256": None,
            "basis": BASIS}


def stat_snapshot(manifest_path) -> Optional[dict]:
    """{relative path: (size, mtime_ns)} of the manifest ("") and its dependencies now, without hashing; None when
    the package cannot be listed."""
    manifest_path = Path(manifest_path)
    try:
        content = json.loads(manifest_path.read_text(encoding="utf-8"))
        status = manifest_path.stat()
        snapshot = {"": (int(status.st_size), int(status.st_mtime_ns))}
        for _role, relative in dependencies(content):
            found = dependency_path(manifest_path.parent, relative).stat()
            snapshot[relative] = (int(found.st_size), int(found.st_mtime_ns))
    except (OSError, ValueError):
        return None
    return snapshot


def unchanged_since(identity: Mapping[str, Any], snapshot: Optional[Mapping[str, tuple]]) -> bool:
    """Whether every file of ``identity`` has the size and modification time of ``snapshot`` (taken before a read)."""
    if not snapshot:
        return False
    now = {"": (identity["manifest"]["size"], identity["manifest"]["mtime_ns"])}
    now.update({f["relative"]: (f["size"], f["mtime_ns"]) for f in identity["files"]})
    return {k: tuple(v) for k, v in snapshot.items()} == now


def confirm(manifest_path, recorded: Optional[Mapping[str, Any]], cancel: Optional[threading.Event] = None) -> dict:
    """The package identified again and equal, file by file, to ``recorded``; else ``PackageChanged`` (or
    ``PackageIdentityRefused`` for a cancellation, a missing record or a package that cannot be identified)."""
    if not recorded or recorded.get("schema") != SCHEMA:
        raise PackageIdentityRefused(NOT_A_PACKAGE, "the identity of the package's files was not recorded when it "
                                                    "was read; Inspect it again")
    try:
        now = identify(manifest_path, cancel)
    except PackageIdentityRefused as refusal:
        if refusal.kind in (MISSING, INVALID_PATH, NOT_A_PACKAGE, UNREADABLE):
            raise PackageChanged(f"the FE package {manifest_path} changed since it was read and cannot be identified "
                                 f"now: {refusal}",
                                 (str(refusal),)) from refusal
        raise
    differences = []
    if (now["manifest"]["sha256"], now["manifest"]["size"]) != (recorded["manifest"]["sha256"],
                                                                recorded["manifest"]["size"]):
        differences.append("manifest.json changed")
    old = {(f["role"], f["relative"]): f for f in recorded["files"]}
    new = {(f["role"], f["relative"]): f for f in now["files"]}
    for key in sorted(set(old) | set(new)):
        if key not in new:
            differences.append(f"{key[0]} ({key[1]}) is no longer read")
        elif key not in old:
            differences.append(f"{key[0]} ({key[1]}) was not read before")
        elif (new[key]["sha256"], new[key]["size"]) != (old[key]["sha256"], old[key]["size"]):
            differences.append(f"{key[0]} ({key[1]}) changed")
    if differences:
        raise PackageChanged(f"the FE package {manifest_path} changed since it was read: " + "; ".join(differences),
                             tuple(differences))
    return now


__all__ = ["BASIS", "PackageChanged", "PackageIdentityRefused", "SCHEMA", "confirm", "dependencies",
           "dependency_path", "identify", "stat_snapshot", "unchanged_since"]
