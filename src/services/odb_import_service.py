"""PRIORITY-0 / RC6: direct import of an Abaqus ``.odb`` into the new interface, without Qt.

The user chooses an ``.odb``; the existing extractor (``abaqus_scripts/extract_odb.py``, run by
``abaqus_bridge.run_abaqus_extraction`` through the Abaqus Python interpreter, ``readOnly=True``) writes an extracted
FE package (``manifest.json``, ``geometry.csv``, one CSV per mode) into a folder the user chose. The package is then
read like any extracted package. Nothing here solves, changes a material, rebuilds a model or runs Auto-ID.

- **Nothing starts by itself.** ``plan_extraction`` only looks (the file, the Abaqus launcher, the results folder,
  the free space, the packages already extracted from the same content); ``run_extraction`` runs only when the
  caller passes the user's explicit confirmation.
- **The source is identified by content.** The ODB is hashed (SHA-256, streaming, cancellable) before the
  extraction and the identity is written beside the package (``extraction_source.json``). A package already present
  for the same SHA-256 and the same mode range is offered for reuse; ``verify_source`` hashes the ODB again and
  reports a change by content, never by size and modification time alone.
- **Nothing is overwritten.** Each extraction gets its own new folder in the results folder.
- **Abaqus absent is a state, not a failure.** ``detect_abaqus`` lists the launchers found by the existing
  ``ui_policy.discover_abaqus_installations`` and never runs one; the explanation names the ways to fix it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import datetime as _dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import threading
from typing import Any, Callable, Optional, Sequence

import abaqus_bridge
from abaqus_bridge import AbaqusExtractionError, AnalysisCancelled

SOURCE_RECORD = "extraction_source.json"
SCHEMA = "odb-extraction-source/1"
DEFAULT_START_MODE, DEFAULT_END_MODE = 1, 30  # the whole low range: FE7 (or any first elastic mode) is never skipped
MINIMUM_FREE_BYTES = 200 * 1024 * 1024  # an extracted package of a fine mesh is tens of MB per mode
_CHUNK = 8 * 1024 * 1024
_FREE_FACTOR = 0.5  # the package of a full low-mode range is usually smaller than the ODB; a floor, not a prediction

ABAQUS_FOUND, ABAQUS_NOT_FOUND = "ABAQUS_FOUND", "ABAQUS_NOT_FOUND"
NOT_FOUND_TEXT = ("No Abaqus launcher was found on this computer (PATH, C:\\SIMULIA\\Commands, Dassault Systemes "
                  "SimulationServices). The program itself runs without Abaqus; only the extraction of an .odb needs "
                  "its Python interpreter.")
NOT_FOUND_FIXES = ("Install Abaqus (any release with the odbAccess Python API) on this computer, or run the program "
                   "where it is installed.",
                   "If Abaqus is installed elsewhere, choose its launcher (abaqus.bat / abqXXXX.bat) with Browse.",
                   "Without Abaqus: extract the package on a computer that has it (RUN_PROGRAM.cmd or this dialog) "
                   "and choose the package's manifest.json here as the FE file.")


class OdbImportRefused(ValueError):
    """The import cannot proceed; the message says why and what to do."""


class OdbImportCancelled(RuntimeError):
    """The user cancelled the hashing or the extraction."""


# ------------------------------------------------------------------------------------------------ Abaqus launcher


@dataclass(frozen=True)
class AbaqusAvailability:
    status: str
    command: str = ""
    label: str = ""
    choices: tuple = ()  # (label, command) of every launcher found
    explanation: str = ""
    fixes: tuple = ()

    @property
    def available(self) -> bool:
        return self.status == ABAQUS_FOUND


def detect_abaqus(command: str = "", *, discover: Optional[Callable[[], Sequence]] = None) -> AbaqusAvailability:
    """The Abaqus launchers of this computer, found by name only (nothing is run, so nothing can hang). With
    ``command`` (a path the user chose), that launcher is checked for existence first."""
    from ui_policy import discover_abaqus_installations, resolve_command, select_abaqus_installation

    chosen = str(command or "").strip()
    if chosen:
        resolved = resolve_command(chosen)
        if resolved is None:
            return AbaqusAvailability(ABAQUS_NOT_FOUND, chosen, explanation=f"The chosen launcher does not exist or is "
                                      f"not executable: {chosen}", fixes=NOT_FOUND_FIXES)
        return AbaqusAvailability(ABAQUS_FOUND, str(resolved), f"Chosen launcher: {resolved}",
                                  ((f"Chosen launcher: {resolved}", str(resolved)),), "")
    try:
        installations = tuple((discover or discover_abaqus_installations)())
    except Exception as error:  # noqa: BLE001  (a broken PATH entry must not stop the program)
        installations = ()
        detail = f" (the search failed: {type(error).__name__}: {error})"
    else:
        detail = ""
    choices = tuple((item.label, item.command) for item in installations)
    if not installations:
        return AbaqusAvailability(ABAQUS_NOT_FOUND, explanation=NOT_FOUND_TEXT + detail, fixes=NOT_FOUND_FIXES)
    selected = select_abaqus_installation(installations) or installations[0]
    note = "" if len(installations) == 1 else f"{len(installations)} launchers were found; the first is proposed."
    return AbaqusAvailability(ABAQUS_FOUND, selected.command, selected.label, choices, note)


# ------------------------------------------------------------------------------------------ the ODB and the folder


@dataclass(frozen=True)
class OdbCheck:
    path: Path
    size: int
    lock_file: Optional[Path] = None  # an Abaqus .lck beside it: the job may still be running

    @property
    def warnings(self) -> tuple:
        if self.lock_file is not None:
            return (f"A lock file lies beside the ODB ({self.lock_file.name}): an Abaqus job may still be writing it. "
                    "The extraction opens the ODB read-only; wait for the job to finish for complete results.",)
        return ()


def check_odb(path) -> OdbCheck:
    """The file as an .odb: it exists, has the suffix and is a regular file. Its content is not read here."""
    path = Path(path)
    if path.suffix.lower() != ".odb":
        raise OdbImportRefused(f"{path.name} is not an Abaqus output database (.odb).")
    if not path.is_file():
        raise OdbImportRefused(f"The file does not exist: {path}")
    size = path.stat().st_size
    if size == 0:
        raise OdbImportRefused(f"The file is empty: {path}")
    lock = path.with_suffix(".lck")
    return OdbCheck(path.resolve(), size, lock if lock.exists() else None)


def hash_file(path, cancel_event: Optional[threading.Event] = None,
              progress: Optional[Callable[[str], None]] = None) -> dict:
    """SHA-256 of ``path`` read now, streaming (an ODB is often several hundred MB); refused when the file changes
    while it is read; cancellable."""
    path = Path(path)
    before = path.stat()
    digest = hashlib.sha256()
    done = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(_CHUNK), b""):
            if cancel_event is not None and cancel_event.is_set():
                raise OdbImportCancelled("The hashing of the ODB was cancelled.")
            digest.update(chunk)
            done += len(chunk)
            if progress is not None and before.st_size:
                progress(f"identifying the ODB content: {100 * done // before.st_size} %")
    after = path.stat()
    if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
        raise OdbImportRefused(f"{path} changed while it was being identified; wait for the writer to finish.")
    return {"path": str(path), "size": int(before.st_size), "mtime_ns": int(before.st_mtime_ns),
            "sha256": digest.hexdigest()}


def extractor_script_path() -> Path:
    """The extractor the bridge will run: next to the program (``abaqus_scripts/extract_odb.py``), as
    ``abaqus_bridge.run_abaqus_extraction`` resolves it (also inside the portable build)."""
    return Path(abaqus_bridge.__file__).resolve().parents[1] / "abaqus_scripts" / "extract_odb.py"


def _safe_stem(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "odb"
    return stem[:60]


def new_package_folder(results_folder: Path, odb: Path, start: int, end: int) -> Path:
    """A folder name that does not exist yet: ``<odb stem>_modes_<start>-<end>[_N]``; nothing is overwritten."""
    base = f"{_safe_stem(odb.stem)}_modes_{start}-{end}"
    candidate = results_folder / base
    counter = 2
    while candidate.exists():
        candidate = results_folder / f"{base}_{counter}"
        counter += 1
    return candidate


def read_source_record(package_folder: Path) -> Optional[dict]:
    try:
        data = json.loads((Path(package_folder) / SOURCE_RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("schema") != SCHEMA or not isinstance(data.get("odb"), dict):
        return None
    return data


def existing_packages(results_folder: Path, odb_sha256: str, start: int, end: int, covering: bool = False) -> list:
    """The packages in ``results_folder`` extracted from the same ODB content with the same requested range (or, with
    ``covering``, a requested range that includes it), each complete (manifest and every listed file present)."""
    found = []
    try:
        children = sorted(p for p in Path(results_folder).iterdir() if p.is_dir())
    except OSError:
        return found
    for child in children:
        record = read_source_record(child)
        if record is None or record["odb"].get("sha256") != odb_sha256:
            continue
        requested = int(record.get("start_mode", -1)), int(record.get("end_mode", -1))
        if requested != (int(start), int(end)) and not (covering and 0 <= requested[0] <= int(start)
                                                        and requested[1] >= int(end)):
            continue
        manifest = child / "manifest.json"
        try:
            listed = json.loads(manifest.read_text(encoding="utf-8"))
            complete = bool(listed.get("modes")) and all((child / m["file"]).is_file() for m in listed["modes"])
        except (OSError, ValueError, KeyError, TypeError):
            complete = False
        if complete:
            found.append(child)
    return found


def free_space_check(folder: Path, odb_size: int) -> tuple[int, int]:
    """(free bytes, needed bytes) on the volume of ``folder``; raises when the free space is below the floor."""
    probe = Path(folder)
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    free = shutil.disk_usage(probe).free
    needed = max(MINIMUM_FREE_BYTES, int(odb_size * _FREE_FACTOR))
    if free < needed:
        raise OdbImportRefused(f"Not enough free space in {folder}: {free / 2**20:.0f} MB free, at least "
                               f"{needed / 2**20:.0f} MB are needed for the extracted package. Choose another "
                               "results folder or free space first.")
    return free, needed


# ------------------------------------------------------------------------------------------------ the plan and the run


@dataclass(frozen=True)
class ExtractionPlan:
    odb: OdbCheck
    results_folder: Path
    start_mode: int
    end_mode: int
    abaqus: AbaqusAvailability
    free_bytes: int
    needed_bytes: int
    extractor: Path
    extractor_present: bool
    warnings: tuple = ()

    @property
    def ready(self) -> bool:
        return self.abaqus.available and self.extractor_present

    @property
    def blockers(self) -> tuple:
        out = []
        if not self.abaqus.available:
            out.append(self.abaqus.explanation)
        if not self.extractor_present:
            out.append(f"The extraction script is missing: {self.extractor}. The program's files are incomplete; "
                       "copy the whole program folder again.")
        return tuple(out)

    def summary(self) -> tuple:
        return (("ODB", str(self.odb.path)), ("Size", f"{self.odb.size / 2**20:.1f} MB"),
                ("Results folder", str(self.results_folder)),
                ("Requested modes", f"{self.start_mode}-{self.end_mode} (the ODB's own range is shown afterwards)"),
                ("Abaqus launcher", self.abaqus.command or "not found"),
                ("Extraction script", str(self.extractor) + ("" if self.extractor_present else " (missing)")),
                ("Free space", f"{self.free_bytes / 2**30:.2f} GB free, at least {self.needed_bytes / 2**20:.0f} MB "
                               "needed"))


_CMD_WRAPPER = os.name == "nt"  # abaqus_bridge._windows_command starts the launcher through cmd.exe


def path_space_warning(paths: Sequence) -> tuple:
    """Paths with a space that the launcher line carries. The bridge's cmd.exe wrapper quotes them twice, so a launcher
    receives them split at the space (seen with a stand-in launcher; not tried with a real Abaqus)."""
    spaced = [str(path) for path in paths if " " in str(path)]
    if not spaced:
        return ()
    return ("These paths contain a space, and the extraction will probably fail on them: "
            + "; ".join(spaced) + ". Use paths without spaces: move or copy the ODB or the program folder, or choose "
            "another results folder.",)


def plan_extraction(odb_path, results_folder, start_mode: int = DEFAULT_START_MODE, end_mode: int = DEFAULT_END_MODE,
                    abaqus_command: str = "", *, discover=None) -> ExtractionPlan:
    """What an extraction would do, with everything checked that can be checked without starting anything."""
    odb = check_odb(odb_path)
    folder = Path(results_folder)
    if not str(results_folder or "").strip():
        raise OdbImportRefused("Choose a results folder for the extracted package.")
    if folder.exists() and not folder.is_dir():
        raise OdbImportRefused(f"The results folder is not a folder: {folder}")
    if folder.resolve() == odb.path.parent.resolve():
        pass  # allowed: the package goes into its own new sub-folder next to the ODB
    try:
        start, end = int(start_mode), int(end_mode)
    except (TypeError, ValueError) as error:
        raise OdbImportRefused("The mode range must be two whole numbers.") from error
    if start < 1 or end < start:
        raise OdbImportRefused(f"The mode range {start}-{end} is invalid: the first mode is at least 1 and the last "
                               "mode is not below the first.")
    free, needed = free_space_check(folder, odb.size)
    extractor = extractor_script_path()
    spaces = path_space_warning((odb.path, folder, extractor)) if _CMD_WRAPPER else ()
    return ExtractionPlan(odb, folder, start, end, detect_abaqus(abaqus_command, discover=discover), free, needed,
                          extractor, extractor.is_file(), odb.warnings + spaces)


@dataclass(frozen=True)
class ExtractionResult:
    manifest_path: Path
    package_folder: Path
    source: dict  # the record written beside the package
    reused: bool = False
    extracted_modes: tuple = ()
    requested: tuple = ()
    range_notice: str = ""
    available_range: Optional[tuple] = None  # (first, last) the extractor reported in the ODB, when it did
    log_path: Optional[Path] = None

    @property
    def extracted_range_text(self) -> str:
        if not self.extracted_modes:
            return "no mode"
        first, last = self.extracted_modes[0], self.extracted_modes[-1]
        contiguous = list(self.extracted_modes) == list(range(first, last + 1))
        return f"{first}-{last}" if contiguous else ", ".join(str(m) for m in self.extracted_modes)


def _available_range_from_log(log_path: Path) -> Optional[tuple]:
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = re.search(r"PROGRESS: modes available (\d+)-(\d+);", text)
    return (int(match.group(1)), int(match.group(2))) if match else None


def _classify_failure(error: AbaqusExtractionError) -> str:
    text = str(error)
    if "No frequency-extraction frames" in text:
        return ("The ODB holds no modal results in the requested range: no frequency-extraction frame with "
                "displacement output U was found. Check that the job has a *FREQUENCY step with U in its field "
                "output, or widen the mode range.\n\n" + text)
    if "No valid Abaqus installation" in text:
        return NOT_FOUND_TEXT + "\n\n" + "\n".join(f"- {fix}" for fix in NOT_FOUND_FIXES)
    if "No space left" in text or "not enough space" in text.lower() or "ENOSPC" in text:
        return ("The disk ran out of space while the package was written. Free space or choose another folder.\n\n"
                + text)
    if "timed out" in text or "exceeded" in text:
        return "The extraction took longer than the time limit and was stopped.\n\n" + text
    return text


def run_extraction(plan: ExtractionPlan, *, confirmed: bool, cancel_event: Optional[threading.Event] = None,
                   progress: Optional[Callable[[str], None]] = None, runner: Optional[Callable[..., Path]] = None,
                   reuse_existing: bool = True, process_callback=None) -> ExtractionResult:
    """Run the extraction the plan describes. ``confirmed`` must be the user's explicit confirmation; ``runner``
    replaces ``abaqus_bridge.run_abaqus_extraction`` in tests (same keyword arguments, returns the manifest path)."""
    if not confirmed:
        raise OdbImportRefused("The extraction starts only after the user confirmed it.")
    if not plan.ready:
        raise OdbImportRefused("\n".join(plan.blockers))
    say = progress or (lambda text: None)
    say("identifying the ODB content...")
    identity = hash_file(plan.odb.path, cancel_event, progress)
    plan.results_folder.mkdir(parents=True, exist_ok=True)
    if reuse_existing:
        for folder in existing_packages(plan.results_folder, identity["sha256"], plan.start_mode, plan.end_mode):
            record = read_source_record(folder) or {}
            say(f"a package of this ODB content already exists: {folder.name}; reused, Abaqus not started")
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            modes = tuple(sorted(int(m["mode"]) for m in manifest.get("modes", ())))
            return ExtractionResult(folder / "manifest.json", folder, record, True, modes,
                                    (plan.start_mode, plan.end_mode),
                                    abaqus_bridge.extraction_range_notice(manifest) or "",
                                    tuple(record.get("available_range") or ()) or None,
                                    folder / "abaqus_extraction.log")
    free_space_check(plan.results_folder, plan.odb.size)
    folder = new_package_folder(plan.results_folder, plan.odb.path, plan.start_mode, plan.end_mode)
    folder.mkdir(parents=False)
    say(f"starting Abaqus Python: {plan.abaqus.command}")
    run = runner or abaqus_bridge.run_abaqus_extraction
    try:
        manifest_path = run(odb_path=plan.odb.path, output_directory=folder, abaqus_command=plan.abaqus.command,
                            start_mode=plan.start_mode, end_mode=plan.end_mode, cancel_event=cancel_event,
                            process_callback=process_callback, progress_callback=progress)
    except AnalysisCancelled as error:
        _mark_incomplete(folder, "cancelled")
        raise OdbImportCancelled("The extraction was cancelled; the incomplete folder is marked, not deleted: "
                                 f"{folder}") from error
    except AbaqusExtractionError as error:
        _mark_incomplete(folder, "failed")
        raise OdbImportRefused(_classify_failure(error)
                               + f"\n\nIncomplete folder (kept for inspection): {folder}") from error
    except OSError as error:
        _mark_incomplete(folder, "failed")
        raise OdbImportRefused(f"The extraction could not run ({type(error).__name__}: {error}). "
                               f"Incomplete folder (kept): {folder}") from error
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    modes = tuple(sorted(int(m["mode"]) for m in manifest.get("modes", ())))
    log_path = folder / "abaqus_extraction.log"
    available = _available_range_from_log(log_path)
    record = {"schema": SCHEMA, "odb": identity, "abaqus_command": plan.abaqus.command,
              "start_mode": plan.start_mode, "end_mode": plan.end_mode, "extracted_modes": list(modes),
              "available_range": list(available) if available else None,
              "extracted_utc": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "extractor_script": str(plan.extractor), "extractor_sha256": _sha_of(plan.extractor),
              "read_only": True, "note": "The ODB was opened readOnly=True; nothing was solved or changed."}
    (folder / SOURCE_RECORD).write_text(json.dumps(record, indent=1), encoding="utf-8")
    say(f"package written: {folder}")
    return ExtractionResult(manifest_path, folder, record, False, modes, (plan.start_mode, plan.end_mode),
                            abaqus_bridge.extraction_range_notice(manifest) or "", available, log_path)


def _sha_of(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _mark_incomplete(folder: Path, state: str) -> None:
    try:
        (folder / "INCOMPLETE.txt").write_text(f"This extraction {state}; the package is not complete. It is kept for "
                                               "inspection and is never reused by the program.\n", encoding="utf-8")
    except OSError:
        pass


# ------------------------------------------------------------------------------------------------ the read cache


def cache_folder() -> Optional[Path]:
    """The folder the user chose for the read cache of large packages, or None."""
    import fast_cache

    return fast_cache.cache_folder()


def set_cache_folder(folder) -> Optional[Path]:
    """Set or clear (empty) that folder; ValueError when it cannot be one. Nothing is created here."""
    import fast_cache

    return fast_cache.set_cache_folder(folder)


# ------------------------------------------------------------------------------------------------ re-detection


@dataclass(frozen=True)
class SourceVerification:
    status: str  # SOURCE_UNCHANGED, SOURCE_CHANGED, SOURCE_MISSING, SOURCE_NOT_RECORDED
    text: str
    recorded: Optional[dict] = None
    now: Optional[dict] = None


SOURCE_UNCHANGED, SOURCE_CHANGED, SOURCE_MISSING, SOURCE_NOT_RECORDED = ("SOURCE_UNCHANGED", "SOURCE_CHANGED",
                                                                         "SOURCE_MISSING", "SOURCE_NOT_RECORDED")


def verify_source(package_folder, odb_path=None, cancel_event: Optional[threading.Event] = None,
                  progress: Optional[Callable[[str], None]] = None) -> SourceVerification:
    """Hash the ODB again and compare it with the content recorded when the package was extracted. Size and
    modification time are reported but never decide: only the SHA-256 does."""
    record = read_source_record(Path(package_folder))
    if record is None:
        return SourceVerification(SOURCE_NOT_RECORDED, "This package records no ODB content identity (it was not "
                                  "extracted by this route); the ODB cannot be checked against it.")
    recorded = record["odb"]
    path = Path(odb_path) if odb_path is not None else Path(recorded.get("path", ""))
    if not path.is_file():
        return SourceVerification(SOURCE_MISSING, f"The ODB is no longer at {path}; the package stays readable, but "
                                  "the source cannot be checked.", recorded)
    now = hash_file(path, cancel_event, progress)
    if now["sha256"] == recorded.get("sha256"):
        return SourceVerification(SOURCE_UNCHANGED, f"The ODB content is unchanged (SHA-256 {now['sha256'][:12]}…).",
                                  recorded, now)
    same_stat = (now["size"], now["mtime_ns"]) == (recorded.get("size"), recorded.get("mtime_ns"))
    return SourceVerification(SOURCE_CHANGED, "The ODB content changed since the package was extracted (SHA-256 "
                              f"{recorded.get('sha256', '')[:12]}… then, {now['sha256'][:12]}… now"
                              + ("; size and modification time are the same, so only the content check found it"
                                 if same_stat else "") + "). Extract again before relying on the package.",
                              recorded, now)


__all__ = ["ABAQUS_FOUND", "ABAQUS_NOT_FOUND", "AbaqusAvailability", "DEFAULT_END_MODE", "DEFAULT_START_MODE",
           "ExtractionPlan", "ExtractionResult", "OdbCheck", "OdbImportCancelled", "OdbImportRefused", "SOURCE_RECORD",
           "SourceVerification", "check_odb", "detect_abaqus", "existing_packages", "extractor_script_path",
           "hash_file", "new_package_folder", "plan_extraction", "read_source_record", "run_extraction",
           "verify_source"]
