"""PRIORITY-1 real modal matching: the inputs, read read-only with the project's existing importer services.

Nothing here is a new algorithm: the experimental files are read with ``services.local_experimental_preview`` and the
FE packages with ``services.local_fe_preview`` (both after ``services.importer_runtime.ensure_application_importers``,
the chain ``src/main.py`` installs). SP-10 has no extracted FE package: its FE frequencies are read from the
``*.dat`` eigenvalue tables of its own models (no shapes; no Abaqus is run).
"""

from __future__ import annotations

import csv
import hashlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

DELIVERY = Path(r"D:\Snadwich\New  EXP results")
WORK = Path(r"D:\git\abaqus-modal-comparator-work")
SCRATCH_INPUTS = Path(r"C:\Users\VadimKrysko\AppData\Local\Temp\claude\d--git-abaqus-modal-comparator"
                      r"\a3589f4a-43dd-41df-99f2-6a9dd3de2870\scratchpad\rc1_inputs")
PROVENANCE = REPO / "docs" / "experimental" / "new_exp_20261029" / "SOURCE_PROVENANCE.csv"

SERIES = {
    "PLATE": ("NEXP29/PLATE300-1MM/S261027-ROTATED", "Polymax_bravo", 11),
    "SP13": ("NEXP29/SP-13/S261028-ROTATED", "polymax_bravo", 12),
    "SP10": ("NEXP29/SP-10/S261029-ROTATED", "polymax_bravo", 12),
}
FE_PACKAGES = {  # the specimen's own extracted packages (read-only)
    "PLATE": WORK / "runs" / "m11_carbon_plate" / "odb_extraction_r6" / "output" / "manifest.json",
    "SP13": SCRATCH_INPUTS / "SP13" / "fe_extraction" / "manifest.json",
}
SP10_DAT = WORK / "external_models" / "v2_20261019" / "SP-10" / "temp_root"
SP10_MODELS = ("SP10_NEW_E1=E2_NSM_DENSITY", "SP10nemash63000", "SP10newmash", "SP10_new_E_NSM_DENS")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def provenance_rows() -> dict:
    with open(PROVENANCE, newline="", encoding="utf-8") as stream:
        return {row["series_id"]: row for row in csv.DictReader(stream)
                if row["source_status"].startswith("NEW_WORKING_SOURCE")}


@dataclass
class Experimental:
    key: str
    series: str
    path: Path
    sha256: str
    provenance_ok: bool
    set_name: str
    modes: list = field(default_factory=list)  # Mode objects of the importer
    dataset: object = None


def read_experimental(key: str) -> Experimental:
    from services.importer_runtime import ensure_application_importers
    from services import local_experimental_preview

    ensure_application_importers()
    series, set_name, count = SERIES[key]
    row = provenance_rows()[series]
    path = DELIVERY.joinpath(*PureWindowsPath(row["relative_path"]).parts)
    digest = sha256(path)
    preview = local_experimental_preview.preview_experimental_file(path)
    chosen = [s for s in preview.sets if set_name in (s.display_name, s.processing_name, s.key)]
    if len(chosen) != 1:
        raise ValueError(f"{key}: set {set_name!r} not found once in {[(s.key, s.display_name) for s in preview.sets]}")
    dataset = chosen[0].dataset
    modes = list(dataset.sorted_modes())
    if len(modes) != count:
        raise ValueError(f"{key}: {len(modes)} modes, expected {count}")
    return Experimental(key, series, path, digest, digest == row["sha256"].lower() and
                        path.stat().st_size == int(row["size_bytes"]), set_name, modes, dataset)


def read_fe(key: str):
    from services.importer_runtime import ensure_application_importers
    from services import local_fe_preview

    ensure_application_importers()
    preview = local_fe_preview.preview_fe_package(FE_PACKAGES[key])
    return preview


def dat_frequencies(path: Path) -> list:
    """(mode, frequency_hz) from an Abaqus .dat EIGENVALUE OUTPUT table (read-only text)."""
    text = path.read_text(errors="replace")
    start = text.find("E I G E N V A L U E    O U T P U T")
    if start < 0:
        raise ValueError(f"no eigenvalue table in {path.name}")
    rows = []
    for line in text[start:].splitlines()[1:]:
        match = re.match(r"\s+(\d+)\s+([-+.\dEe]+)\s+([-+.\dEe]+)\s+([-+.\dEe]+)\s", line)
        if match:
            rows.append((int(match.group(1)), float(match.group(4))))
        elif rows and not line.strip():
            if len(rows) > 3:
                break
    return rows
