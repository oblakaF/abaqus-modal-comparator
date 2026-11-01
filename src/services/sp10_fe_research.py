"""PRIORITY-7: the SP-10 FE results of PRIORITY-6, read and checked for the new interface (no Qt; RESEARCH_ONLY).

PRIORITY-6 extracted the existing ODB of the SP-10 model SP10_NEW_E1=E2_NSM_DENSITY once with the pinned extractor
(step SP_10_MODAL_FREE, FE7–FE25, 1 667 491 nodes). Its archived records in ``docs/research/
sp10_existing_fe_shapes_202610`` (SP10_FE_PACKAGE.json, SP10_FE_VS_DAT.csv) are read here only when their SHA-256 is
the one recorded below (text read with CRLF as LF, the same digest on every checkout); a changed or damaged file, a
foreign model, ODB, FE manifest or step, a missing or repeated mode, a non-finite, non-positive or non-increasing
frequency, or a disagreement between the two records refuses the whole view with the reason. No value is invented.

From the 19 archived FE frequencies and the 12 experimental frequencies of the historical PRIORITY-1 table (polymax_bravo
of the 261029 series) a frequency-only diagnostic is built: for every experimental record the nearest and the second
nearest FE frequency with Δf (%) = 100 × (f_FE − f_EXP) / f_EXP. It is FREQUENCY_PROXIMITY_ONLY — NOT A CONFIRMED MODE
PAIR: no MAC, registration, orientation, assignment or permutation is made, and nothing is computed from the shapes.

The extracted package itself (about 3.1 GB) is never read here: it is chosen and read on the Workspace page by the
existing importer. ``workspace_match`` only compares the SHA-256 of the files read there (the FE manifest's exact
bytes, the experimental file), the chosen modal set and the read FE modes with this record. A match of the files is
never a physical registration: SP-10 261029 stays PHYSICAL_REGISTRATION_NOT_VERIFIED.

Labels: RESEARCH_ONLY / FREQUENCY_ONLY_DIAGNOSTIC / NOT_A_MATERIAL_PROPERTY. M8 GATE NOT_MET, D-077
NO_GLOBAL_PARAMETER_VALUE and production Auto-ID BLOCKED are unchanged.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
LABELS = ("RESEARCH_ONLY", "FREQUENCY_ONLY_DIAGNOSTIC", "NOT_A_MATERIAL_PROPERTY")
PROXIMITY_ONLY = "FREQUENCY_PROXIMITY_ONLY — NOT A CONFIRMED MODE PAIR"
REGISTRATION_STATUS = "PHYSICAL_REGISTRATION_NOT_VERIFIED"
MATCH = "PRIORITY-6 DATA SOURCES MATCH THE WORKSPACE INPUTS"
NO_MATCH = "PRIORITY-6 DATA SOURCES DO NOT MATCH THE WORKSPACE INPUTS"
PACKAGE_NOT_LOADED = "FE SHAPES EXTRACTED IN PRIORITY-6 — LOCAL PACKAGE NOT LOADED"
PACKAGE_LOADED = "FE SHAPES EXTRACTED IN PRIORITY-6 — LOCAL PACKAGE LOADED IN THE WORKSPACE"

# (published path, SHA-256 of the committed content with LF line ends, research commit)
ARCHIVE_FILES = {
    "PACKAGE": ("docs/research/sp10_existing_fe_shapes_202610/SP10_FE_PACKAGE.json",
                "a43637a1d84ddb108ca2973b1191b49120a72a0d8ffae9d1db889930861ba567", "9b86af4"),
    "FE_VS_DAT": ("docs/research/sp10_existing_fe_shapes_202610/SP10_FE_VS_DAT.csv",
                  "647db42e83cd2edae35d694bbba8a2449d8108531a6a7d8f606c122b8a344317", "9b86af4"),
}
MODEL = "SP10_NEW_E1=E2_NSM_DENSITY"
ODB_SHA256 = "87a9036fb5dc314e14a1fcb0d9ef4e0175d80bc6dfb05ceeea926d1ae767302c"
FE_MANIFEST_SHA256 = "035b274c43fb8b7143bceb4dec99fdb2926a0f094cdafe1a0355faa45d8b1542"
EXTRACTOR_SHA256 = "039aa067adeac83e457ccacc9036c767f98c41517fb1ffdd5293fdd01dc6534d"
STEP = "SP_10_MODAL_FREE"
SERIES = "NEXP29/SP-10/S261029-ROTATED"
EXPERIMENT_SHA256 = "432adf963085b012b07a6b235e1dde3c4df83ea87b85326497df0a89a9eeef1f"
MODAL_SET = "polymax_bravo"
MODAL_SET_NAMES = ("polymax_bravo", "polymax-bravo")  # the importer's display name and key of the set
EXPERIMENTAL_RECORDS = 12
NODES = 1667491
FE_MODES = tuple(range(7, 26))
PREVIOUS_RANGE = tuple(range(7, 16))  # FE7–FE15: the FE modes of PRIORITY-1 (the .dat of step 1)
ADDED_RANGE = tuple(range(16, 26))  # FE16–FE25: added by PRIORITY-6 beyond the earlier range (FE15 is 220.044 Hz)
# close groups of the experimental records and the FE spectrum near them, as identified in PRIORITY-1 / PRIORITY-6
# (RESULTS.md §4): highlighted for the reader only — never an assignment or a permutation
CLOSE_GROUPS = (((4, 5), (10, 11)), ((7, 8), (13, 14)), ((11, 12), (17, 18)))
FE_RELATIVE_TOLERANCE = 1e-6  # a Workspace FE frequency (EIGFREQ history) against the archived EIGFREQ


class Sp10ResearchRefused(ValueError):
    """The PRIORITY-6 records are missing, changed or inconsistent; the updated view is not shown."""


@dataclass(frozen=True)
class FeMode:
    number: int
    frequency_hz: float  # the ODB's EIGFREQ history (full precision)
    dat_hz: float  # the job's .dat, five significant digits
    node_count: int
    shape_file: str  # the mode file of the extracted package (outside Git)
    shape_sha256: str

    @property
    def added(self) -> bool:
        return self.number in ADDED_RANGE


@dataclass(frozen=True)
class Candidate:
    fe: int
    frequency_hz: float
    df_percent: float


@dataclass(frozen=True)
class DiagnosticRow:
    exp_no: int
    f_exp_hz: float
    nearest: Candidate
    second: Optional[Candidate]
    group: str  # "" or "EXP11/EXP12 near FE17/FE18"
    status: str = PROXIMITY_ONLY

    @property
    def nearest_in_added_range(self) -> bool:
        return self.nearest.fe in ADDED_RANGE


@dataclass(frozen=True)
class Sp10FeResults:
    files: dict  # key → (path, sha256, commit)
    model: str
    odb_sha256: str
    odb_bytes: int
    fe_manifest_sha256: str
    extractor_sha256: str
    step: str
    nodes: int
    instances: dict
    package_bytes: int
    fe_modes: tuple  # FeMode, FE7–FE25
    labels: tuple = LABELS

    def frequency(self, number: int) -> float:
        return next(m.frequency_hz for m in self.fe_modes if m.number == number)


def _read(key: str, root: Path) -> str:
    relative, expected, _commit = ARCHIVE_FILES[key]
    path = Path(root) / relative
    if not path.is_file():
        raise Sp10ResearchRefused(f"{relative} is missing")
    data = path.read_bytes().replace(b"\r\n", b"\n")  # the committed (LF) form, whatever the checkout wrote
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected:
        raise Sp10ResearchRefused(f"{relative}: SHA-256 {digest[:12]}… is not the archived {expected[:12]}… — the "
                                  "file changed, so the PRIORITY-6 results are not shown")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise Sp10ResearchRefused(f"{relative} cannot be read: {error}") from error


def _positive(value, what: str) -> float:
    if isinstance(value, bool):
        raise Sp10ResearchRefused(f"{what}: {value!r} is not a number")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise Sp10ResearchRefused(f"{what}: {value!r} is not a number") from None
    if not math.isfinite(number) or number <= 0:
        raise Sp10ResearchRefused(f"{what}: {value!r} is not a finite positive frequency")
    return number


def _expect(condition: bool, reason: str) -> None:
    if not condition:
        raise Sp10ResearchRefused(reason)


def _printed(value: float, printed: float) -> bool:
    """``value`` printed to the five significant digits of an Abaqus .dat gives ``printed``."""
    digits = 5 - 1 - int(math.floor(math.log10(abs(printed))))
    return round(value, digits) == round(printed, digits)


def load_results(root: Path = REPO) -> Sp10FeResults:
    """The checked PRIORITY-6 record; raises Sp10ResearchRefused with the reason."""
    try:
        record = json.loads(_read("PACKAGE", root))
    except json.JSONDecodeError as error:
        raise Sp10ResearchRefused(f"{ARCHIVE_FILES['PACKAGE'][0]} is not valid JSON: {error}") from error
    _expect(isinstance(record, dict), "the PRIORITY-6 record is not a JSON object")
    try:
        source, extraction, geometry = record["source"], record["extraction"], record["geometry"]
        identity, frequencies, history = record["identity"], record["frequencies"], record["odb_history_vs_dat"]
    except (KeyError, TypeError) as error:
        raise Sp10ResearchRefused(f"the PRIORITY-6 record has no {error} section") from None
    _expect(record.get("result") == "PASS" and record.get("problems") == [],
            "the PRIORITY-6 record is not a passed verification")
    _expect(source.get("job") == MODEL, f"the model {source.get('job')!r} is not {MODEL}")
    _expect(source.get("odb_sha256") == ODB_SHA256, "the ODB SHA-256 is not the one extracted in PRIORITY-6")
    _expect(identity.get("manifest_sha256") == FE_MANIFEST_SHA256,
            "the FE manifest SHA-256 is not the one extracted in PRIORITY-6")
    _expect(extraction.get("step") == STEP, f"the modal step {extraction.get('step')!r} is not {STEP}")
    _expect(extraction.get("extractor_sha256") == EXTRACTOR_SHA256, "the extractor is not the pinned one")
    _expect(geometry.get("nodes") == NODES, f"the geometry has {geometry.get('nodes')} nodes, not {NODES}")
    _expect(isinstance(frequencies, list) and isinstance(history, list), "the frequency tables are missing")
    numbers = [row.get("mode") if isinstance(row, dict) else None for row in frequencies]
    _expect(numbers == list(FE_MODES), f"the FE modes are {numbers}, not FE7–FE25 in order")
    files = identity.get("files")
    _expect(isinstance(files, dict), "the package file list is missing")
    eigfreq = {}
    for row in history:
        _expect(isinstance(row, dict) and row.get("equal_to_dat") is True,
                "an ODB history frequency does not equal the .dat")
        if row.get("mode") in FE_MODES:
            eigfreq[row["mode"]] = _positive(row.get("odb_eigfreq_hz"), f"FE{row.get('mode')} EIGFREQ")
    _expect(sorted(eigfreq) == list(FE_MODES), "the ODB history does not hold FE7–FE25")
    modes = []
    for row in frequencies:
        n = row["mode"]
        frequency = _positive(row.get("odb_eigfreq_hz"), f"FE{n} frequency")
        dat = _positive(row.get("dat_step2_hz"), f"FE{n} .dat frequency")
        _expect(frequency == eigfreq[n], f"FE{n}: the two ODB frequency tables differ")
        _expect(row.get("equal_to_dat") is True and _printed(frequency, dat),
                f"FE{n}: {frequency} Hz does not equal the .dat {dat} Hz")
        _expect(row.get("node_count") == NODES, f"FE{n}: the shape does not hold every node")
        shape = row.get("file")
        _expect(shape == f"mode_{n:04d}.csv" and isinstance(files.get(shape), dict)
                and isinstance(files[shape].get("sha256"), str), f"FE{n}: no extracted shape file is recorded")
        modes.append(FeMode(n, frequency, dat, NODES, shape, files[shape]["sha256"]))
    values = [m.frequency_hz for m in modes]
    _expect(all(a < b for a, b in zip(values, values[1:])), "the FE frequencies are not increasing")
    table = list(csv.DictReader(io.StringIO(_read("FE_VS_DAT", root))))
    _expect([r.get("mode") for r in table] == [str(n) for n in FE_MODES],
            "SP10_FE_VS_DAT.csv does not hold FE7–FE25 in order")
    for row, mode in zip(table, modes):
        try:
            csv_frequency, csv_dat = float(row["odb_eigfreq_hz"]), float(row["dat_step2_hz"])
        except (KeyError, TypeError, ValueError):
            raise Sp10ResearchRefused(f"SP10_FE_VS_DAT.csv FE{mode.number}: no frequency") from None
        _expect(math.isclose(csv_frequency, mode.frequency_hz, rel_tol=1e-7) and csv_dat == mode.dat_hz
                and row.get("equal_to_dat") == "True", f"FE{mode.number}: the two PRIORITY-6 records disagree")
    return Sp10FeResults({k: v for k, v in ARCHIVE_FILES.items()}, MODEL, ODB_SHA256, int(source.get("odb_bytes", 0)),
                         FE_MANIFEST_SHA256, EXTRACTOR_SHA256, STEP, NODES, dict(geometry.get("instances") or {}),
                         int(identity.get("total_bytes", 0)), tuple(modes))


def _candidate(mode: FeMode, f_exp: float) -> Candidate:
    return Candidate(mode.number, mode.frequency_hz, 100.0 * (mode.frequency_hz - f_exp) / f_exp)


def _group(exp_no: int) -> str:
    for exps, fes in CLOSE_GROUPS:
        if exp_no in exps:
            return f"{'/'.join(f'EXP{e}' for e in exps)} near {'/'.join(f'FE{f}' for f in fes)}"
    return ""


def frequency_diagnostic(results: Sp10FeResults, experimental) -> tuple:
    """For every experimental record (number, Hz) of polymax_bravo: the nearest and second nearest FE frequency, by
    |Δf|, with the signed Δf. Frequency proximity only: no pair, MAC, assignment or permutation."""
    experimental = [(int(n), _positive(hz, f"EXP{n} frequency")) for n, hz in experimental]
    _expect([n for n, _hz in experimental] == list(range(1, EXPERIMENTAL_RECORDS + 1)),
            f"the experimental records are not EXP1–EXP{EXPERIMENTAL_RECORDS}")
    rows = []
    for n, f_exp in experimental:
        ranked = sorted(results.fe_modes, key=lambda m: (abs(m.frequency_hz - f_exp), m.number))
        rows.append(DiagnosticRow(n, f_exp, _candidate(ranked[0], f_exp),
                                  _candidate(ranked[1], f_exp) if len(ranked) > 1 else None, _group(n)))
    return tuple(rows)


# ----------------------------------------------------------------------------- the Workspace link (by SHA-256)

@dataclass(frozen=True)
class WorkspaceMatch:
    matched: bool
    headline: str
    lines: tuple
    package_loaded: bool
    package_line: str
    registration: str = REGISTRATION_STATUS


def workspace_match(results: Sp10FeResults, experimental_identity=None, fe_identity=None,
                    modal_set: Optional[dict] = None, fe_modes=None, fe_step: Optional[str] = None) -> WorkspaceMatch:
    """Compare the files read in the Workspace with the PRIORITY-6 sources, by SHA-256 only.

    ``modal_set``: {"names": (display name, key), "records": count} of the set chosen for the frequency diagnostic, or
    None when none is chosen; ``fe_modes``: ((number, Hz), ...) of the FE package read, with ``fe_step``."""
    exp_sha = (experimental_identity or {}).get("sha256")
    fe_sha = (fe_identity or {}).get("sha256")
    lines, problems = [], []
    if exp_sha == EXPERIMENT_SHA256:
        lines.append(f"Experimental file: SHA-256 {exp_sha[:12]}… matches {SERIES}")
    else:
        problems.append("the experimental file read in the Workspace is "
                        + (f"{exp_sha[:12]}…" if exp_sha else "none") + f", not {EXPERIMENT_SHA256[:12]}… of {SERIES}")
    fe_ok = fe_sha == results.fe_manifest_sha256
    if fe_ok:
        lines.append(f"FE manifest: SHA-256 {fe_sha[:12]}… matches the PRIORITY-6 package")
        expected = {m.number: m.frequency_hz for m in results.fe_modes}
        got = {int(n): float(hz) for n, hz in (fe_modes or ())}
        if fe_step != results.step or sorted(got) != list(FE_MODES) or not all(
                math.isclose(got[n], expected[n], rel_tol=FE_RELATIVE_TOLERANCE) for n in FE_MODES):
            problems.append("the FE modes read in the Workspace are not FE7–FE25 of step "
                            f"{results.step} with the archived frequencies")
            fe_ok = False
        else:
            lines.append(f"FE modes read: FE7–FE25 of {results.step}, frequencies equal to the archive")
    else:
        problems.append("the FE manifest read in the Workspace is " + (f"{fe_sha[:12]}…" if fe_sha else "none")
                        + f", not the PRIORITY-6 package's {results.fe_manifest_sha256[:12]}…")
    if modal_set is None:
        lines.append(f"Modal set: none chosen on the Analysis page — its identity with {MODAL_SET} is not claimed")
    elif (any(name in MODAL_SET_NAMES for name in modal_set.get("names", ()))
          and modal_set.get("records") == EXPERIMENTAL_RECORDS):
        lines.append(f"Modal set chosen: {MODAL_SET}, {EXPERIMENTAL_RECORDS} records")
    else:
        problems.append(f"the modal set chosen ({' / '.join(n for n in modal_set.get('names', ()) if n) or 'unknown'}"
                        f", {modal_set.get('records')} records) is not {MODAL_SET} with {EXPERIMENTAL_RECORDS} records")
    package_line = (f"{PACKAGE_LOADED} (manifest {results.fe_manifest_sha256[:12]}…): view its shapes on the Workspace "
                    "page" if fe_ok else PACKAGE_NOT_LOADED + " — the archived frequencies are shown; choose its "
                    "manifest.json on the Workspace page to view the shapes")
    if problems:
        return WorkspaceMatch(False, NO_MATCH + ": " + "; ".join(problems), tuple(lines), fe_ok, package_line)
    return WorkspaceMatch(True, MATCH, tuple(lines), fe_ok, package_line)


__all__ = ["ADDED_RANGE", "ARCHIVE_FILES", "CLOSE_GROUPS", "Candidate", "DiagnosticRow", "FE_MANIFEST_SHA256",
           "FeMode", "LABELS", "MATCH", "MODAL_SET", "NO_MATCH", "ODB_SHA256", "PACKAGE_LOADED", "PACKAGE_NOT_LOADED",
           "PREVIOUS_RANGE", "PROXIMITY_ONLY", "REGISTRATION_STATUS", "Sp10FeResults", "Sp10ResearchRefused",
           "WorkspaceMatch", "frequency_diagnostic", "load_results", "workspace_match"]
