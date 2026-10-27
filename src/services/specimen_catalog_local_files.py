"""APP-CATALOG.2: check one local file the user located for a specimen-catalogue source.

Only the file the user chose is examined; no disk, store or folder is searched. The file is opened read-only, and its
SHA-256 is computed in blocks, never by loading the whole file. The result is one of:

- ``BYTE_VERIFIED``: the full SHA-256 equals the catalogue's reference SHA-256 of that source (for a zip member, of
  that member). This is byte identity only, not a scientific confirmation that the data suit a comparison.
- ``HASH_MISMATCH``: the file differs from the reference (a different size already proves it); it cannot be used
  through the catalogue.
- ``NOT_VERIFIED_NO_REFERENCE``: the catalogue records no SHA-256. Name and size are diagnostic hints only; the file
  can be used only after a separate warning is confirmed, and it is never called verified.
- ``FILE_MISSING`` / ``UNREADABLE`` / ``UNSUPPORTED_TYPE`` / ``NOT_AN_INPUT``: the file cannot be used.

Nothing here sets an input of the program, chooses a modal set or registration, or starts anything.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from typing import Optional

from services.specimen_catalog_view import CatalogueSource, EXPERIMENTAL_SUFFIXES, FE_SIDE

BYTE_VERIFIED = "BYTE_VERIFIED"
HASH_MISMATCH = "HASH_MISMATCH"
NOT_VERIFIED_NO_REFERENCE = "NOT_VERIFIED_NO_REFERENCE"
FILE_MISSING = "FILE_MISSING"
UNREADABLE = "UNREADABLE"
UNSUPPORTED_TYPE = "UNSUPPORTED_TYPE"
NOT_AN_INPUT = "NOT_AN_INPUT"
BLOCK = 1 << 20  # bytes per read while hashing
IDENTITY_NOTE = ("Byte identity is not a scientific confirmation: it proves neither the FE-experiment pairing, the "
                 "modal set, the registration nor the orientation.")


@dataclass(frozen=True)
class LocalCheck:
    status: str
    path: Optional[Path]
    message: str
    size: Optional[int] = None
    mtime_ns: Optional[int] = None
    sha256: Optional[str] = None  # computed only when a reference exists and the sizes agree

    @property
    def usable(self) -> bool:
        return self.status in (BYTE_VERIFIED, NOT_VERIFIED_NO_REFERENCE)

    @property
    def needs_confirmation(self) -> bool:
        return self.status == NOT_VERIFIED_NO_REFERENCE


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def allowed_suffixes(source: CatalogueSource) -> tuple[str, ...]:
    """Suffixes a located copy may have: the catalogue file's own, within what the program reads for that side."""
    if not source.loadable:
        return ()
    if source.side == FE_SIDE:
        return (".odb",)
    return (source.suffix,) if source.suffix in EXPERIMENTAL_SUFFIXES else ()


def check_local_file(source: CatalogueSource, path) -> LocalCheck:
    """Check the file the user located for ``source``; reads only that file."""
    if not source.loadable:
        return LocalCheck(NOT_AN_INPUT, None, source.reason)
    text = str(path or "").strip()
    if not text:
        return LocalCheck(FILE_MISSING, None, "No file was chosen.")
    file = Path(os.path.abspath(text))
    if not file.is_file():
        return LocalCheck(FILE_MISSING, file, f"The file {file} does not exist (or is not a file). The fields of the "
                                              "program are unchanged.")
    suffixes = allowed_suffixes(source)
    if file.suffix.lower() not in suffixes:
        member = (f" Extract {source.file_name} from {source.reference.get('relative_path')} yourself and locate the "
                  "extracted copy; an archive is never passed to the UNV reader." if source.reference.get("zip_member")
                  else "")
        return LocalCheck(UNSUPPORTED_TYPE, file, f"{file.name} is not a {' / '.join(suffixes)} file, as the catalogue "
                                                  f"source {source.file_name} is.{member}")
    try:
        stat = file.stat()
        with open(file, "rb") as stream:
            stream.read(1)
    except OSError as error:
        return LocalCheck(UNREADABLE, file, f"The file {file} cannot be read ({error.__class__.__name__}). The fields "
                                            "of the program are unchanged.")
    size, mtime = stat.st_size, stat.st_mtime_ns
    target = (f"the member {source.file_name} of {source.reference.get('relative_path')}"
              if source.reference.get("zip_member") else source.file_name)
    if source.sha256 is None:
        hint = ""
        if source.size_bytes is not None:
            same = "equals" if size == source.size_bytes else "differs from"
            hint = f" Its size {same} the size the catalogue records ({source.size_bytes} bytes): a hint only."
        return LocalCheck(NOT_VERIFIED_NO_REFERENCE, file,
                          f"The catalogue records no SHA-256 for {target}, so this file cannot be byte-verified.{hint} "
                          "It can be used only after you confirm the warning, and it is not called verified.",
                          size, mtime)
    if source.size_bytes is not None and size != source.size_bytes:
        return LocalCheck(HASH_MISMATCH, file, f"{file.name} has {size} bytes, the reference of {target} has "
                                               f"{source.size_bytes}: its SHA-256 cannot match. It cannot be used "
                                               "through the catalogue.", size, mtime)
    try:
        digest = sha256_of(file)
    except OSError as error:
        return LocalCheck(UNREADABLE, file, f"The file {file} could not be read to the end "
                                            f"({error.__class__.__name__}). The fields of the program are unchanged.",
                          size, mtime)
    if digest != source.sha256:
        return LocalCheck(HASH_MISMATCH, file, f"The SHA-256 of {file.name} ({digest[:12]}…) differs from the "
                                               f"reference of {target} ({source.sha256[:12]}…). It cannot be used "
                                               "through the catalogue.", size, mtime, digest)
    return LocalCheck(BYTE_VERIFIED, file, f"The SHA-256 of {file.name} equals the reference of {target} "
                                           f"({digest[:12]}…). {IDENTITY_NOTE}", size, mtime, digest)


def unchanged_since(check: LocalCheck) -> bool:
    """The checked file is still there with the same size and modification time (else it must be checked again)."""
    if check.path is None:
        return False
    try:
        stat = check.path.stat()
    except OSError:
        return False
    return (stat.st_size, stat.st_mtime_ns) == (check.size, check.mtime_ns)
