"""WORKING-DRAFT-R2: the analysis project file (``.mcproj``): its format, checks and atomic writing. No Qt, no FE reading.

A project is one ZIP file with exactly these members (see ``docs/gui/PROJECT_FORMAT.md``):

- ``manifest.json``: the schema, and the size and SHA-256 of every other member;
- ``project.json``: the saved sources, results and registration facts, as strict JSON;
- ``images/fe_<n>.png``, ``images/exp_<n>.png``: the saved mode-shape pictures.

Nothing is ever unpickled, executed or extracted to disk: the members are read into memory under fixed limits, only the
names above are accepted, and JSON refuses repeated keys, NaN and infinity. No ODB, UNV, UFF or extracted FE package is
stored; only their paths and hashes are.

MAT-3: ``SCHEMA_V2`` is a separate, explicit version for the results of the Materials page. Its content has its own strict
check (``services.materials_project``). ``read_project`` and ``write_project`` keep reading and writing v1 by default with
the v1 check unchanged, and each version refuses the other by name.

The checks detect damage and careless editing. They are not a signature: someone who rewrites the file and its hashes is
not detected. A project therefore never proves anything. Its results stay a saved snapshot until the source files are
checked and the analysis is run again, and its status is never raised to a stronger one.

A project is written to a temporary file beside the target, read back with the same checks and only then moved into
place, so a failed or cancelled save leaves an existing project untouched.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import struct
from typing import Any, Mapping, Optional
import uuid
import zipfile

SUFFIX = ".mcproj"
SCHEMA = "universal/analysis-project/v1"
SCHEMA_V2 = "universal/analysis-project/v2"  # the Materials page's results: services.materials_project
MANIFEST = "manifest.json"
PROJECT = "project.json"
_IMAGE_NAME = re.compile(r"images/(fe|exp)_[0-9]{1,4}\.png")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

MAX_PROJECT_BYTES = 256 * 2 ** 20
MAX_PROJECT_JSON_BYTES = 32 * 2 ** 20
MAX_MANIFEST_BYTES = 2 ** 20
MAX_IMAGE_BYTES = 8 * 2 ** 20
MAX_IMAGES = 64
MAX_IMAGE_SIDE = 8000  # pixels: a small PNG cannot ask for a huge picture

# what a project may state; none of these is a statement that the current files were checked
REGISTRATION_REQUIRED = "REGISTRATION_REQUIRED"
USER_CONFIRMED = "USER_CONFIRMED_COMPARISON"
VERIFIED = "VERIFIED_COMPARISON"
NO_PAIR = "NO_ADMISSIBLE_PAIR"
STATUSES = (REGISTRATION_REQUIRED, USER_CONFIRMED, VERIFIED, NO_PAIR)
KIND_NONE, KIND_ARCHIVED, KIND_CONFIRMED = "NONE", "ARCHIVED_REGISTRATION", "USER_CONFIRMED_REGISTRATION"
_KINDS_OF_STATUS = {REGISTRATION_REQUIRED: {KIND_NONE}, USER_CONFIRMED: {KIND_CONFIRMED}, VERIFIED: {KIND_ARCHIVED},
                    NO_PAIR: {KIND_ARCHIVED, KIND_CONFIRMED}}

# refusal codes
NOT_A_PROJECT = "PROJECT_NOT_A_PROJECT"
DAMAGED = "PROJECT_DAMAGED"
OTHER_VERSION = "PROJECT_OTHER_VERSION"
TOO_LARGE = "PROJECT_TOO_LARGE"
INVALID = "PROJECT_INVALID"
WRITE_FAILED = "PROJECT_WRITE_FAILED"

_TOP_KEYS = ("schema", "saved_at", "written_at", "program", "scope", "sources", "modal_set", "modes", "result",
             "comparison", "registration", "shapes")
_RESULT_KEYS = ("status", "statement", "set_index", "set_title", "fe_rows", "experimental_rows", "nearest_rows",
                "first_elastic", "rigid_modes", "facts", "notes", "registration_reason", "registration_outcome",
                "unavailable_fe", "experimental_total")
_COMPARISON_KEYS = ("status", "statement", "set_title", "specimen", "fixture_id", "registration", "registration_file",
                    "pair_rows", "mac_fe_modes", "mac_experimental_modes", "mac_cells", "mac_values", "assigned_cells",
                    "candidate_rows", "unmatched_fe_rows", "unmatched_experimental_rows", "unpaired_experimental",
                    "rigid_rows", "close_groups", "warnings", "provenance", "gates", "target_counts", "limits",
                    "auto_id_note")
_PAIR_KEYS = ("index", "abaqus_mode", "experimental_mode", "mac", "frequency_error_percent", "cells")
_REGISTRATION_KEYS = ("kind", "confirmation_path", "draft_path", "confirmed_by", "confirmed_at", "evidence_location",
                      "confirmation_sha256", "draft_sha256", "evidence_sha256", "registration_hash",
                      "registration_file", "limits")
_SHAPE_KEYS = ("number", "label", "image", "lines", "refusal")


class ProjectRefused(ValueError):
    """A project cannot be read or written; ``code`` names the reason and the message is for the user."""

    def __init__(self, code: str, text: str) -> None:
        super().__init__(text)
        self.code = code


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _unique_keys(pairs: list) -> dict:
    keys = [key for key, _value in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("a key is repeated")
    return dict(pairs)


def _no_constant(name: str):
    raise ValueError(f"{name} is not a number")


def _strict_json(data: bytes) -> Any:
    return json.loads(data.decode("utf-8"), object_pairs_hook=_unique_keys, parse_constant=_no_constant)


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=1, allow_nan=False).encode("utf-8")


def _members_hash(members: Mapping) -> str:
    return _sha256(json.dumps(members, sort_keys=True, separators=(",", ":")).encode("utf-8"))


# ---------------------------------------------------------------------------------------------- the content's shape


def _invalid(text: str) -> ProjectRefused:
    return ProjectRefused(INVALID, f"The project's content is not valid: {text}.")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _keys(value: Any, keys: tuple, name: str) -> None:
    if not isinstance(value, dict) or set(value) != set(keys):
        raise _invalid(f"{name} is incomplete or holds unknown fields")


def _texts(value: Any, name: str) -> None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise _invalid(f"{name} is not a list of texts")


def _text_rows(value: Any, name: str) -> None:
    if not isinstance(value, list):
        raise _invalid(f"{name} is not a table")
    for row in value:
        _texts(row, name)


def _ints(value: Any, name: str) -> None:
    if not isinstance(value, list) or not all(_is_int(item) for item in value):
        raise _invalid(f"{name} is not a list of whole numbers")


def _string(value: Any, name: str) -> None:
    if not isinstance(value, str):
        raise _invalid(f"{name} is not a text")


def _sha(value: Any, name: str) -> None:
    if not (isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)):
        raise _invalid(f"{name} is not a SHA-256")


def _check_sources(sources: Any) -> None:
    _keys(sources, ("fe_odb", "fe_package", "experimental"), "sources")
    odb, package, experimental = sources["fe_odb"], sources["fe_package"], sources["experimental"]
    _keys(odb, ("path", "size", "sha256", "relocated_from"), "sources.fe_odb")
    _keys(package, ("manifest_path", "manifest_size", "manifest_sha256", "package_sha256", "total_bytes", "files",
                    "relocated_from"),
          "sources.fe_package")
    _keys(experimental, ("path", "source_path", "size", "sha256", "relocated_from"), "sources.experimental")
    for item, name in ((odb, "the ODB"), (experimental, "the experimental file")):
        _string(item["path"], f"the path of {name}")
        _sha(item["sha256"], f"the hash of {name}")
        if not _is_int(item["size"]) or item["size"] < 0:
            raise _invalid(f"the size of {name} is not valid")
        _texts(item["relocated_from"], "relocated_from")
    _string(experimental["source_path"], "the experimental source path")
    _string(package["manifest_path"], "the FE package path")
    _sha(package["manifest_sha256"], "the FE manifest hash")
    _sha(package["package_sha256"], "the FE package hash")
    if not _is_int(package["total_bytes"]) or not _is_int(package["manifest_size"]) or not isinstance(package["files"], list):
        raise _invalid("the FE package's file list is not valid")
    _texts(package["relocated_from"], "relocated_from")


def _check_result(result: Any) -> None:
    _keys(result, _RESULT_KEYS, "result")
    if result["status"] not in STATUSES:
        raise _invalid(f"the status {result['status']!r} is not known")
    for key in ("statement", "set_title", "registration_reason", "registration_outcome"):
        _string(result[key], key)
    for key in ("fe_rows", "experimental_rows", "nearest_rows"):
        _text_rows(result[key], key)
    for key in ("facts", "notes"):
        _texts(result[key], key)
    for key in ("rigid_modes", "unavailable_fe"):
        _ints(result[key], key)
    if not _is_int(result["set_index"]) or not _is_int(result["experimental_total"]):
        raise _invalid("the modal set's position is not valid")
    if result["first_elastic"] is not None:
        _string(result["first_elastic"], "first_elastic")


def _check_comparison(view: Any) -> None:
    _keys(view, _COMPARISON_KEYS, "comparison")
    for key in ("status", "statement", "set_title", "specimen", "fixture_id", "registration", "registration_file",
                "target_counts", "auto_id_note"):
        _string(view[key], key)
    if not isinstance(view["pair_rows"], list):
        raise _invalid("the mode pairs are not a list")
    for pair in view["pair_rows"]:
        _keys(pair, _PAIR_KEYS, "a mode pair")
        _texts(pair["cells"], "a mode pair's cells")
        if not all(_is_int(pair[key]) for key in ("index", "abaqus_mode", "experimental_mode")):
            raise _invalid("a mode pair's numbers are not valid")
        if not (pair["mac"] is None or _is_number(pair["mac"])) or not _is_number(pair["frequency_error_percent"]):
            raise _invalid("a mode pair's values are not valid")
    _ints(view["mac_fe_modes"], "mac_fe_modes")
    _ints(view["mac_experimental_modes"], "mac_experimental_modes")
    _text_rows(view["mac_cells"], "mac_cells")
    if len(view["mac_cells"]) != len(view["mac_fe_modes"]) or any(
            len(row) != len(view["mac_experimental_modes"]) for row in view["mac_cells"]):
        raise _invalid("the MAC table does not fit its mode lists")
    if not isinstance(view["mac_values"], list) or (view["mac_values"] and len(view["mac_values"]) != len(view["mac_cells"])):
        raise _invalid("the MAC values do not fit the MAC table")
    for row in view["mac_values"]:
        if not isinstance(row, list) or not all(value is None or _is_number(value) for value in row):
            raise _invalid("a MAC value is not a number")
    if not isinstance(view["assigned_cells"], list) or not all(
            isinstance(cell, list) and len(cell) == 2 and all(_is_int(item) for item in cell)
            for cell in view["assigned_cells"]):
        raise _invalid("the assigned MAC cells are not valid")
    for key in ("candidate_rows", "unmatched_fe_rows", "unmatched_experimental_rows", "rigid_rows", "provenance", "gates"):
        _text_rows(view[key], key)
    for key in ("unpaired_experimental", "close_groups", "warnings", "limits"):
        _texts(view[key], key)


def _check_registration(registration: Any, status: str, compared: bool) -> None:
    _keys(registration, _REGISTRATION_KEYS, "registration")
    for key in _REGISTRATION_KEYS:
        if key != "limits":
            _string(registration[key], key)
    _texts(registration["limits"], "the registration's limits")
    kind = registration["kind"]
    if kind not in _KINDS_OF_STATUS[status]:
        raise _invalid(f"the status {status} cannot come from the registration kind {kind!r}")
    if compared != (kind != KIND_NONE):  # no pair and no MAC without a registration, and none lost with one
        raise _invalid("the comparison and the registration do not belong together")


def _check_shapes(shapes: Any, images: Mapping[str, bytes]) -> None:
    _keys(shapes, ("component", "fe", "experimental"), "shapes")
    _string(shapes["component"], "the shapes' component")
    used = []
    for side in ("fe", "experimental"):
        if not isinstance(shapes[side], list):
            raise _invalid("the saved shapes are not a list")
        for entry in shapes[side]:
            _keys(entry, _SHAPE_KEYS, "a saved shape")
            _string(entry["number"], "a saved shape's mode")
            _string(entry["label"], "a saved shape's label")
            _string(entry["refusal"], "a saved shape's refusal")
            _texts(entry["lines"], "a saved shape's caption")
            if entry["image"] is not None:
                _string(entry["image"], "a saved shape's picture")
                used.append(entry["image"])
    if sorted(used) != sorted(images):
        raise _invalid("the saved shapes and the stored pictures differ")


def validate_document(document: Any, images: Mapping[str, bytes]) -> None:
    """The project's content has exactly the documented shape, and its status fits what was computed."""
    _keys(document, _TOP_KEYS, "the project")
    if document["schema"] != SCHEMA:
        raise ProjectRefused(OTHER_VERSION, f"This project has the format {document['schema']!r}; this program reads "
                                            f"{SCHEMA!r}.")
    for key in ("saved_at", "written_at", "program"):
        _string(document[key], key)
    _keys(document["scope"], ("first_mode", "last_mode", "mode_limit"), "scope")
    _check_sources(document["sources"])
    _keys(document["modal_set"], ("index", "key", "display_name", "processing_name", "title", "record_count",
                                  "analyzed_count", "provisional", "all_sets"), "modal_set")
    _keys(document["modes"], ("fe", "experimental"), "modes")
    for side in ("fe", "experimental"):
        modes = document["modes"][side]
        if not isinstance(modes, list) or not all(
                isinstance(item, dict) and _is_int(item.get("number")) and _is_number(item.get("frequency_hz"))
                for item in modes):
            raise _invalid("the saved modes are not valid")
    _check_result(document["result"])
    compared = document["comparison"] is not None
    if compared:
        _check_comparison(document["comparison"])
    _check_registration(document["registration"], document["result"]["status"], compared)
    _check_shapes(document["shapes"], images)


def _check_png(name: str, data: bytes) -> None:
    if len(data) < 24 or not data.startswith(_PNG_SIGNATURE) or data[12:16] != b"IHDR":
        raise ProjectRefused(DAMAGED, f"{name} is not a PNG picture.")
    width, height = struct.unpack(">II", data[16:24])
    if not (0 < width <= MAX_IMAGE_SIDE and 0 < height <= MAX_IMAGE_SIDE):
        raise ProjectRefused(TOO_LARGE, f"{name} states a picture of {width} x {height} pixels; the limit is "
                                        f"{MAX_IMAGE_SIDE}.")


# ---------------------------------------------------------------------------------------------- reading


def _limit_of(name: str) -> Optional[int]:
    if name == MANIFEST:
        return MAX_MANIFEST_BYTES
    if name == PROJECT:
        return MAX_PROJECT_JSON_BYTES
    if _IMAGE_NAME.fullmatch(name):
        return MAX_IMAGE_BYTES
    return None


def _read_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int) -> bytes:
    if info.file_size > limit:
        raise ProjectRefused(TOO_LARGE, f"{info.filename} is larger than the limit of {limit} bytes.")
    with archive.open(info) as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ProjectRefused(TOO_LARGE, f"{info.filename} is larger than the limit of {limit} bytes.")
    return data


def read_project(path, schema: str = SCHEMA, validate=validate_document) -> tuple:
    """(document, {member name: PNG bytes}) of a project of ``schema`` that passes every check. Raises ``ProjectRefused``."""
    path = Path(path)
    try:
        size = path.stat().st_size
    except OSError as error:
        raise ProjectRefused(NOT_A_PROJECT, f"The project cannot be read: {error}.") from error
    if size > MAX_PROJECT_BYTES:
        raise ProjectRefused(TOO_LARGE, f"{path.name} is larger than a project can be ({MAX_PROJECT_BYTES} bytes).")
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ProjectRefused(NOT_A_PROJECT, f"The project cannot be read: {error}.") from error
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return _read_archive(archive, path.name, schema, validate)
    except zipfile.BadZipFile as error:
        raise ProjectRefused(NOT_A_PROJECT, f"{path.name} is damaged or is not a project file: {error}.") from error
    except (EOFError, OSError, NotImplementedError, RuntimeError, ValueError) as error:
        if isinstance(error, ProjectRefused):
            raise
        raise ProjectRefused(DAMAGED, f"{path.name} is damaged: {error}.") from error


def project_schema(path) -> Optional[str]:
    """The schema a project's manifest states, read under the same limits, or None. Nothing else in the file is read."""
    try:
        path = Path(path)
        if path.stat().st_size > MAX_PROJECT_BYTES:
            return None
        with zipfile.ZipFile(path) as archive:
            manifest = _strict_json(_read_member(archive, archive.getinfo(MANIFEST), MAX_MANIFEST_BYTES))
    except (OSError, EOFError, KeyError, RuntimeError, ValueError, NotImplementedError, zipfile.BadZipFile):
        return None
    schema = manifest.get("schema") if isinstance(manifest, dict) else None
    return schema if isinstance(schema, str) else None


def _read_archive(archive: zipfile.ZipFile, shown: str, schema: str = SCHEMA, validate=validate_document) -> tuple:
    infos = archive.infolist()
    names = [info.filename for info in infos]
    if len(set(names)) != len(names):
        raise ProjectRefused(DAMAGED, f"{shown} names one member twice.")
    unknown = [name for name in names if _limit_of(name) is None]
    if unknown:
        raise ProjectRefused(DAMAGED, f"{shown} holds a member a project cannot hold: {unknown[0]!r}.")
    if MANIFEST not in names or PROJECT not in names:
        raise ProjectRefused(NOT_A_PROJECT, f"{shown} is not a project file: {MANIFEST} or {PROJECT} is missing.")
    image_names = [name for name in names if name not in (MANIFEST, PROJECT)]
    if len(image_names) > MAX_IMAGES:
        raise ProjectRefused(TOO_LARGE, f"{shown} holds more than {MAX_IMAGES} pictures.")
    if sum(info.file_size for info in infos) > MAX_PROJECT_BYTES:
        raise ProjectRefused(TOO_LARGE, f"{shown} states more data than a project can hold.")
    for info in infos:
        if info.file_size > _limit_of(info.filename):  # before anything is decompressed
            raise ProjectRefused(TOO_LARGE, f"{info.filename} is larger than the limit of {_limit_of(info.filename)} bytes.")
        if info.flag_bits & 0x1 or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise ProjectRefused(DAMAGED, f"{info.filename} is stored in a way a project is not.")
    by_name = {info.filename: info for info in infos}
    try:
        manifest = _strict_json(_read_member(archive, by_name[MANIFEST], MAX_MANIFEST_BYTES))
    except ProjectRefused:
        raise
    except ValueError as error:
        raise ProjectRefused(DAMAGED, f"The manifest of {shown} cannot be read: {error}.") from error
    if not isinstance(manifest, dict) or set(manifest) != {"schema", "members", "members_sha256"}:
        raise ProjectRefused(DAMAGED, f"The manifest of {shown} is not valid.")
    if manifest["schema"] != schema:
        raise ProjectRefused(OTHER_VERSION, f"This project has the format {manifest['schema']!r}; this command reads "
                                            f"{schema!r}.")
    members = manifest["members"]
    if not isinstance(members, dict) or _members_hash(members) != manifest["members_sha256"]:
        raise ProjectRefused(DAMAGED, f"The manifest of {shown} does not match its own hash.")
    if set(members) != set(names) - {MANIFEST}:
        raise ProjectRefused(DAMAGED, f"The members of {shown} are not the ones its manifest lists.")
    contents = {}
    for name, stated in members.items():
        content = _read_member(archive, by_name[name], _limit_of(name))
        if not isinstance(stated, dict) or stated.get("size") != len(content) or stated.get("sha256") != _sha256(content):
            raise ProjectRefused(DAMAGED, f"{name} in {shown} does not match its recorded hash: the file is damaged.")
        contents[name] = content
    try:
        document = _strict_json(contents[PROJECT])
    except ValueError as error:
        raise ProjectRefused(DAMAGED, f"The results in {shown} cannot be read: {error}.") from error
    images = {name: content for name, content in contents.items() if name != PROJECT}
    for name, content in images.items():
        _check_png(name, content)
    validate(document, images)
    return document, images


# ---------------------------------------------------------------------------------------------- writing


def _same_file(target: Path, other) -> bool:
    other = Path(other)
    try:
        if target.resolve() == other.resolve():
            return True
        return target.exists() and other.exists() and os.path.samefile(target, other)
    except OSError:
        return False


def project_bytes(document: Mapping, images: Mapping[str, bytes], schema: str = SCHEMA) -> bytes:
    """The ZIP file of a valid document: JSON compressed, pictures stored as they are (PNG is compressed already)."""
    content = _json_bytes(document)
    if len(content) > MAX_PROJECT_JSON_BYTES:
        raise ProjectRefused(TOO_LARGE, "The results are larger than a project can hold.")
    members = {PROJECT: {"size": len(content), "sha256": _sha256(content)}}
    members.update({name: {"size": len(data), "sha256": _sha256(data)} for name, data in sorted(images.items())})
    manifest = _json_bytes({"schema": schema, "members": members, "members_sha256": _members_hash(members)})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(zipfile.ZipInfo(MANIFEST), manifest, zipfile.ZIP_DEFLATED)
        archive.writestr(zipfile.ZipInfo(PROJECT), content, zipfile.ZIP_DEFLATED)
        for name, data in sorted(images.items()):
            archive.writestr(zipfile.ZipInfo(name), data, zipfile.ZIP_STORED)
    return buffer.getvalue()


def write_project(document: Mapping, images: Mapping[str, bytes], path, protected=(), cancel_event=None,
                  schema: str = SCHEMA, validate=validate_document) -> Path:
    """Write the project all or nothing; a source file is never overwritten. Raises ``ProjectRefused``."""
    path = Path(path)
    if path.suffix.lower() != SUFFIX:
        raise ProjectRefused(WRITE_FAILED, f"A project is a {SUFFIX} file.")
    for item in protected:
        if item and _same_file(path, item):
            raise ProjectRefused(WRITE_FAILED, f"{path.name} is a source file of this analysis; it is not overwritten.")
    if not all(_IMAGE_NAME.fullmatch(name) and len(data) <= MAX_IMAGE_BYTES for name, data in images.items()) \
            or len(images) > MAX_IMAGES:
        raise ProjectRefused(TOO_LARGE, "The saved pictures are outside what a project can hold.")
    for name, data in images.items():
        _check_png(name, data)
    validate(document, images)
    data = project_bytes(document, images, schema)
    if len(data) > MAX_PROJECT_BYTES:
        raise ProjectRefused(TOO_LARGE, "The results are larger than a project can hold.")
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        read_project(temporary, schema, validate)  # what was written is read back with the same checks before it takes the name
        if cancel_event is not None and cancel_event.is_set():
            raise ProjectRefused(WRITE_FAILED, "The save was cancelled.")
        os.replace(temporary, path)
    except OSError as error:
        raise ProjectRefused(WRITE_FAILED, f"The project could not be written: {error}") from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return path


__all__ = ["DAMAGED", "INVALID", "KIND_ARCHIVED", "KIND_CONFIRMED", "KIND_NONE", "MAX_IMAGE_BYTES", "MAX_IMAGES",
           "MAX_PROJECT_BYTES", "NOT_A_PROJECT", "NO_PAIR", "OTHER_VERSION", "ProjectRefused", "REGISTRATION_REQUIRED",
           "SCHEMA", "SCHEMA_V2", "STATUSES", "project_schema", "SUFFIX", "TOO_LARGE", "USER_CONFIRMED", "VERIFIED", "WRITE_FAILED", "project_bytes",
           "read_project", "validate_document", "write_project"]
