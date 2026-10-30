"""NEW-GUI.6: the known new experimental working sources of 2026-10-29, offered for an explicit choice, with no Qt.

The accepted provenance map ``docs/experimental/new_exp_20261029/SOURCE_PROVENANCE.csv`` (NEW-EXP-R1) lists every file
of the delivery. Exactly three files are the new main working sources: the fitted dataset-55 PolyMAX sets of the
ROTATED sessions of SP-13 (28.10.2026), SP-10 (29.10.2026) and PLATE-300x300x1mm (27.10.2026).

They are declared here as typed entries (series identity, relative path, size, SHA-256, modal-set type). The CSV is
interpreted strictly, never by searching a description: an entry is offered only when the CSV row with the same
relative path has the same series identity, size and SHA-256, its status's leading token is exactly
``NEW_WORKING_SOURCE`` and its dataset list holds the fitted modal-set dataset 55. A file is used only when it exists
under the chosen root and its size and fresh SHA-256 are the declared ones.

WINDOWS-RC1-A: the folder is portable. ``DEFAULT_ROOT`` is only the first suggestion; the user may choose another
folder in the dialog (never a scan of the disks). The chosen folder is either the delivery folder (holding
``SPname_files_ROTATED_261028``) or that subfolder itself. A file found there is still used only with the declared size
and a fresh SHA-256: a matching name is never evidence of the source.

Nothing is loaded at start-up and nothing is read before the user asks. Choosing an entry only puts its path into the
workspace's experimental slot: the user still clicks Inspect file. No registration, FE model or material record is
assigned from a specimen identifier: there is no accepted physical registration of these ROTATED series, and SP-10
and the plate have no confirmed FE package of their own.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
from pathlib import Path, PureWindowsPath
import re
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
PROVENANCE = REPO_ROOT / "docs" / "experimental" / "new_exp_20261029" / "SOURCE_PROVENANCE.csv"
DEFAULT_ROOT = Path(r"D:\Snadwich\New  EXP results")  # two spaces between "New" and "EXP"
WORKING_STATUS = "NEW_WORKING_SOURCE"
FITTED_DATASET = 55
MODAL_SET_TYPE = "fitted dataset-55 PolyMAX modal set"
TITLE = "Known new experimental sources (2026-10-29)"
NOTE = ("The three fitted dataset-55 PolyMAX files of the ROTATED sessions, from the accepted provenance map. Choosing "
        "one only puts its path into the experimental file; click Inspect file to read it. No archived physical "
        "registration applies to these series, and none is assigned from a specimen name.")


@dataclass(frozen=True)
class KnownSource:
    series_id: str
    specimen: str
    session: str
    relative_path: str
    size_bytes: int
    sha256: str
    fe_note: str
    modal_set_type: str = MODAL_SET_TYPE

    @property
    def title(self) -> str:
        return f"{self.specimen} — {self.session}"


KNOWN_SOURCES = (
    KnownSource("NEXP29/SP-13/S261028-ROTATED", "SP-13", "ROTATED 28.10.2026, polymax_bravo",
                r"SPname_files_ROTATED_261028\SP13_500by500_Glue420_Auxetic_ROTATED_Polytec_261028.unv", 448211,
                "8abf951dba4b8a942922cb4af96074fc1ce8fce2a3f0de8ce082bc5820eeda10",
                "No accepted physical registration of this ROTATED series: a verified comparison is not available."),
    KnownSource("NEXP29/SP-10/S261029-ROTATED", "SP-10", "ROTATED 29.10.2026, polymax_bravo",
                r"SPname_files_ROTATED_261028\SP10_b_rotated_500by500_Glue420_Honeycomb_ROTATED_Polytec_261029.unv",
                448391, "432adf963085b012b07a6b235e1dde3c4df83ea87b85326497df0a89a9eeef1f",
                "No confirmed SP-10 FE package and no accepted registration: compare frequencies with your own FE "
                "model of SP-10 only; another specimen's FE results are not its FE↔EXP result."),
    KnownSource("NEXP29/PLATE300-1MM/S261027-ROTATED", "PLATE-300x300x1mm", "ROTATED 27.10.2026, Polymax_bravo",
                r"SPname_files_ROTATED_261028\300by300_plate_only_1mm_ROTATED_Polytec_261027.unv", 421096,
                "76db80aed1b4ba7062c0bf914cae85b55ea2665d80cb643c8cd54ba6c8bedc4d",
                "No confirmed plate FE package and no accepted registration: compare frequencies with your own FE "
                "model of the plate only; another specimen's FE results are not its FE↔EXP result."),
)


class ProvenanceMismatch(ValueError):
    """The provenance map does not confirm a declared source; the message says why."""


def _status_token(status: str) -> str:
    """The leading token of a status cell ('NEW_WORKING_SOURCE (fitted ...); ...' -> 'NEW_WORKING_SOURCE')."""
    match = re.match(r"\s*([A-Z0-9_]+)", status or "")
    return match.group(1) if match else ""


def _datasets(file_type: str) -> tuple:
    match = re.search(r"datasets\s*\[([0-9,\s]+)\]", file_type or "")
    return tuple(int(item) for item in match.group(1).split(",")) if match else ()


def _key(relative: str) -> str:
    return str(PureWindowsPath(relative)).lower()


def confirmed_sources(provenance: Path = PROVENANCE) -> tuple:
    """The declared sources the provenance map confirms, in declaration order; raises on any disagreement."""
    with open(provenance, newline="", encoding="utf-8") as stream:
        rows = {_key(row["relative_path"]): row for row in csv.DictReader(stream)}
    confirmed = []
    for source in KNOWN_SOURCES:
        row = rows.get(_key(source.relative_path))
        if row is None:
            raise ProvenanceMismatch(f"{source.relative_path} is not in {provenance.name}.")
        checks = ((row["series_id"] == source.series_id, f"series {row['series_id']!r} ≠ {source.series_id!r}"),
                  (int(row["size_bytes"]) == source.size_bytes, f"size {row['size_bytes']} ≠ {source.size_bytes}"),
                  (row["sha256"].lower() == source.sha256, "SHA-256 differs from the declared one"),
                  (_status_token(row["source_status"]) == WORKING_STATUS,
                   f"status {_status_token(row['source_status'])!r} is not {WORKING_STATUS}"),
                  (FITTED_DATASET in _datasets(row["file_type"]),
                   f"datasets {_datasets(row['file_type'])} hold no fitted dataset {FITTED_DATASET}"))
        problems = [text for ok, text in checks if not ok]
        if problems:
            raise ProvenanceMismatch(f"{source.relative_path}: " + "; ".join(problems) + ".")
        confirmed.append(source)
    working = [row["relative_path"] for row in rows.values() if _status_token(row["source_status"]) == WORKING_STATUS]
    if sorted(map(_key, working)) != sorted(_key(s.relative_path) for s in KNOWN_SOURCES):
        raise ProvenanceMismatch(f"{provenance.name} lists other {WORKING_STATUS} files than the declared three.")
    return tuple(confirmed)


AVAILABLE, MISSING, CHANGED = "available", "missing", "changed"


@dataclass(frozen=True)
class Availability:
    source: KnownSource
    path: Path
    state: str
    text: str


def locate(source: KnownSource, root: Path) -> Path:
    """Where the declared file would lie under ``root``: the delivery folder, or the declared subfolder itself (when
    ``root`` is named like it). Only a place to look; the size and SHA-256 decide."""
    parts = PureWindowsPath(source.relative_path).parts  # the same on Windows and Linux
    root = Path(root)
    path = root.joinpath(*parts)
    if not path.is_file() and len(parts) > 1 and root.name.lower() == parts[-2].lower():
        return root / parts[-1]
    return path


def availability(source: KnownSource, root: Path = DEFAULT_ROOT) -> Availability:
    """Whether the file exists under ``root`` with the declared size (no content is read)."""
    path = locate(source, root)
    try:
        size = path.stat().st_size if path.is_file() else None
    except OSError:
        size = None
    if size is None:
        return Availability(source, path, MISSING, "Not found in the chosen folder")
    if size != source.size_bytes:
        return Availability(source, path, CHANGED, f"Size {size} bytes differs from the declared {source.size_bytes}")
    return Availability(source, path, AVAILABLE, "Available (size matches; SHA-256 is checked when chosen)")


def verify(source: KnownSource, root: Path = DEFAULT_ROOT) -> Path:
    """The file's path when its size and fresh SHA-256 are the declared ones; else ``ProvenanceMismatch``."""
    found = availability(source, root)
    if found.state != AVAILABLE:
        raise ProvenanceMismatch(f"{source.title}: {found.text.lower()} ({found.path}).")
    digest = hashlib.sha256()
    with open(found.path, "rb") as stream:  # read-only
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    if digest.hexdigest() != source.sha256:
        raise ProvenanceMismatch(f"{source.title}: the file's SHA-256 {digest.hexdigest()[:12]}… is not the declared "
                                 f"{source.sha256[:12]}…; it is not used.")
    return found.path


def find(series_id: str) -> Optional[KnownSource]:
    return next((source for source in KNOWN_SOURCES if source.series_id == series_id), None)


__all__ = ["AVAILABLE", "Availability", "CHANGED", "DEFAULT_ROOT", "KNOWN_SOURCES", "KnownSource", "MISSING",
           "ProvenanceMismatch", "availability", "confirmed_sources", "find", "locate", "verify"]
