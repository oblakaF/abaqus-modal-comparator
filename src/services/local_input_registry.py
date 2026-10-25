"""APP-DATA.1: a local registry of the user's own FE and experimental input files (File > Input file registry...).

The registry is a navigation convenience only:

- a person adds a file through the file dialog; the registry keeps its path and a readable name in the per-user
  configuration folder of the comparator, outside Git and every data store;
- an entry is either an FE result (an Abaqus ODB or an extracted ``manifest.json``) or an experimental result (UNV /
  UFF, or an LMS project whose companion UNV / UFF lies beside it). FE and experimental entries are independent: no
  entry refers to another one, and two entries never establish that a model and a measurement belong to the same
  specimen, test or mode pair;
- using an entry only fills the matching field of 1. Files, the same way as choosing the file there: nothing is
  loaded, compared or run, and no file content is read (only its existence and name are checked);
- a missing file or a damaged registry is a clear error: no field is filled, nothing is substituted, and a damaged
  registry is never rewritten.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import uuid

from universal_reader import resolve_testlab_file

SCHEMA = "comparator/local-input-registry/v1"
STORE_NAME = "local_input_registry.json"
FE, EXPERIMENTAL = "FE", "EXPERIMENTAL"
KINDS = (FE, EXPERIMENTAL)
KIND_TEXT = {FE: "FE result", EXPERIMENTAL: "Experimental result"}
FILETYPES = {
    FE: [("Abaqus ODB", "*.odb"), ("Extracted manifest", "manifest.json"), ("All files", "*.*")],
    EXPERIMENTAL: [("Universal modal files", "*.unv *.uff"), ("Testlab project", "*.lms"), ("All files", "*.*")],
}
NOTE = ("A convenience list of your own file references, kept only in your user profile. It is not a scientific "
        "catalogue: an FE entry and an experimental entry do not establish that they belong to the same specimen, "
        "test or mode pair. Using an entry only fills the field on 1. Files; nothing is loaded, compared or run.")
_FIELDS = ("id", "kind", "label", "path", "added_at")


class RegistryError(ValueError):
    """A registry action refused: damaged registry, missing or unsupported file, unknown entry."""


def default_store() -> Path:
    """The per-user configuration folder of the comparator (project_review.CONFIG_DIRECTORY)."""
    return Path.home() / ".abaqus_simcenter_modal_comparator" / STORE_NAME


def _damaged(store: Path, what: str) -> RegistryError:
    return RegistryError(f"The input file registry {store} is damaged ({what}). It is left unchanged: no entry can be "
                         "used, added or removed until the file is repaired or moved away by a person.")


def _read(store: Path) -> dict:
    """The whole registry, checked entry by entry; a damaged registry raises RegistryError and is never rewritten."""
    try:
        data = json.loads(Path(store).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"schema": SCHEMA, "entries": []}
    except OSError as error:
        raise RegistryError(f"The input file registry {store} cannot be read: {error}") from error
    except ValueError as error:  # invalid JSON or text encoding
        raise _damaged(store, f"not valid JSON: {error}") from error
    if not isinstance(data, dict):
        raise _damaged(store, f"the top level is a {type(data).__name__}, not an object")
    if data.get("schema") != SCHEMA:
        raise _damaged(store, f"schema {data.get('schema')!r} instead of {SCHEMA!r}")
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise _damaged(store, "'entries' is not a list")
    seen = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise _damaged(store, f"entry {index} is not an object")
        missing = [key for key in _FIELDS if not isinstance(entry.get(key), str) or not entry[key].strip()]
        if missing:
            raise _damaged(store, f"entry {index} lacks {', '.join(missing)}")
        if entry["kind"] not in KINDS:
            raise _damaged(store, f"entry {index} has kind {entry['kind']!r}")
        if entry["id"] in seen:
            raise _damaged(store, f"entry {index} repeats id {entry['id']}")
        seen.add(entry["id"])
    return data


def _write(store: Path, data: dict) -> None:
    store = Path(store)
    store.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".local_input_registry_", suffix=".json", dir=str(store.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False)
        os.replace(temporary, store)  # atomic: the registry is never half written
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _same_file_key(path) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(str(path))))


def check_file(kind: str, path) -> Path:
    """The file as an input of this kind now: it must exist and have a supported type. Only its name and existence are
    checked (for an LMS project, the presence of its companion UNV / UFF); its content is not read."""
    if kind not in KINDS:
        raise RegistryError(f"Unknown entry kind {kind!r}.")
    text = str(path or "").strip()
    if not text:
        raise RegistryError("No file was given.")
    file = Path(os.path.abspath(text))
    if not file.is_file():
        raise RegistryError(f"The file {file} does not exist (or is not a file).")
    suffix, name = file.suffix.lower(), file.name.lower()
    if kind == FE:
        if suffix != ".odb" and name != "manifest.json":
            raise RegistryError(f"{file.name} is not an FE result: choose an Abaqus .odb or an extracted manifest.json.")
    elif suffix == ".lms":
        try:
            resolve_testlab_file(file)
        except ValueError as error:
            raise RegistryError(str(error)) from error
    elif suffix not in (".unv", ".uff"):
        raise RegistryError(f"{file.name} is not an experimental result: choose a .unv, .uff or .lms file.")
    return file


def list_entries(store: Path) -> list[dict]:
    return [dict(entry) for entry in _read(Path(store))["entries"]]


def add_entry(store: Path, kind: str, path, label: str = "") -> tuple[dict, bool]:
    """Add a reference to this file. Returns (entry, added): the same file of the same kind already in the registry is
    returned unchanged with added False (no second entry, its name kept)."""
    file = check_file(kind, path)
    data = _read(Path(store))
    key = _same_file_key(file)
    for entry in data["entries"]:
        if entry["kind"] == kind and _same_file_key(entry["path"]) == key:
            return dict(entry), False
    entry = {"id": uuid.uuid4().hex, "kind": kind, "label": str(label or "").strip() or file.name, "path": str(file),
             "added_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    data["entries"].append(entry)
    _write(Path(store), data)
    return dict(entry), True


def remove_entry(store: Path, entry_id: str) -> dict:
    """Remove one reference from the registry; the file itself is never touched."""
    data = _read(Path(store))
    for index, entry in enumerate(data["entries"]):
        if entry["id"] == entry_id:
            del data["entries"][index]
            _write(Path(store), data)
            return dict(entry)
    raise RegistryError("This entry is no longer in the registry.")


def usable_path(entry: dict) -> Path:
    """The file of an entry, checked now; a missing or unsupported file raises RegistryError (nothing substituted)."""
    try:
        return check_file(entry.get("kind"), entry.get("path"))
    except RegistryError as error:
        raise RegistryError(f"The entry '{entry.get('label', '')}' cannot be used: {error}") from error


def entry_state(entry: dict) -> str:
    """'found' or 'missing' for the registry list (existence only)."""
    return "found" if Path(str(entry.get("path", ""))).is_file() else "missing"
