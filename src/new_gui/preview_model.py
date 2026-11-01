"""NEW-GUI.2: reading a chosen file for its preview, with no Qt.

``read_preview`` reads one file with the existing preview services, after installing the application's importer
chain with ``services.importer_runtime.ensure_application_importers`` (the function ``src/main.py`` calls). The new
interface therefore shows what the analysis importer reads. Nothing here is computed again: the mode numbers,
frequencies, modal sets, record classifications and warnings are the services' own.

- **FE.** ``services.local_fe_preview.preview_fe_package`` reads an extracted package (``manifest.json``). A plain
  ``.odb`` is not read and Abaqus is never started.
- **Experimental.** ``services.local_experimental_preview.preview_experimental_file`` reads a UNV / UFF or an LMS
  project's companion. Several dataset-55 modal sets are shown separately; none is chosen and nothing is merged. FRF
  peak-derived records (dataset 58) are PROVISIONAL, not validated fitted modes.

NEW-GUI.6-F1: ``run_read`` records the identity (SHA-256 and size) of the file it read: the FE package's
``manifest.json`` or the experimental file the importer read (``source_path``). The file is hashed after the read;
when it is the chosen file and its size or modification time changed during the read, no identity is recorded
(the read data cannot be tied to one content). A comparison and an export compare this identity with the file on
disk and refuse when it changed; a later hash is never attributed to data read earlier.

PLATE-ONLY-R2-F1: for the FE side the identity covers the whole extracted package (``services.fe_package_identity``):
``manifest.json``, its geometry file and every mode file the loader reads, each with a streaming SHA-256, under
``"package"`` (the manifest's own path, size and SHA-256 stay at the top level). The package's files are listed before
the read; when any of them changed during the read, or the package cannot be identified (a missing file, an invalid
dependency path, a cancellation), no identity is recorded. The ODB is never read and never hashed here.

``InspectSlot`` keeps the read of one side. A replaced or cleared file resets it, cancels the read and discards that
read's outcome, so a stale result is never shown. The modules are imported, and the importer chain installed, only
when a file is read, so an empty start reads nothing and creates no cache.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Any, Optional

from new_gui.workspace_state import EXPERIMENTAL, FE, KINDS

INSPECT = "Inspect file"
IDLE, READING, READ, FAILED = "idle", "reading", "read", "failed"
STATE_TEXT = {READING: "Reading the file...", READ: "Content read; preview only", FAILED: "Content not read"}
PREVIEW_NOTE = ("The data as the analysis importer reads them. This is a preview only: nothing is compared with the "
                "other side, no modal set or mode is selected, paired or excluded, no MAC is computed, and the data "
                "are not declared ready for an analysis.")
NOT_INSPECTED = "Not read yet. Click Inspect file to read the file's modal data."
ODB_NOT_READ = ("This is an Abaqus .odb: the new interface cannot view it in this version, and Abaqus is not "
                "started. Choose the manifest.json of a package already extracted from it (with its CSV files) as the "
                "FE file. The existing interface RUN_PROGRAM.cmd keeps its own ODB route.")
PROVISIONAL_NOTE = ("These records are response snapshots at FRF peaks, derived by the importer without a fitted "
                    "modal set. Each one is PROVISIONAL — NOT A VALIDATED FITTED MODE.")
FE_HEADERS = ("Mode", "Frequency (Hz)", "Frequency source", "FE nodes")
EXPERIMENTAL_HEADERS = ("Mode", "Frequency (Hz)", "Status (importer)", "Points", "Measured DOFs", "Damping (%)")

_IMPORTERS = threading.Lock()  # the chain is installed once, even when both sides are read at the same time


class PreviewRefused(ValueError):
    """The file is not read for a preview (an .odb); the reason is shown."""


@dataclass(frozen=True)
class Outcome:
    """The end of one read: a preview, or an error message, or a cancellation."""

    kind: str
    path: Path
    token: int
    preview: Any = None
    error: str = ""
    cancelled: bool = False
    identity: Any = None  # NEW-GUI.6-F1: {"path", "size", "sha256"} of the file read, or None when unconfirmed


def read_preview(kind: str, path, cancel_event: Optional[threading.Event] = None):
    """Read ``path`` with the existing preview service of ``kind``, with the application's importer chain."""
    if kind not in KINDS:
        raise ValueError(f"unknown source kind {kind!r}")
    path = Path(path)
    if kind == FE and path.suffix.lower() == ".odb":
        raise PreviewRefused(ODB_NOT_READ)
    from services.importer_runtime import ensure_application_importers

    with _IMPORTERS:
        ensure_application_importers()
    if kind == FE:
        from services import local_fe_preview

        return local_fe_preview.preview_fe_package(path, cancel_event=cancel_event)
    from services import local_experimental_preview

    return local_experimental_preview.preview_experimental_file(path, cancel_event=cancel_event)


def _stat(path) -> Optional[tuple]:
    try:
        found = Path(path).stat()
    except OSError:
        return None
    return found.st_size, found.st_mtime_ns


def file_identity(path, cancel_event: Optional[threading.Event] = None) -> Optional[dict]:
    """SHA-256 and size of ``path`` read now (no cache), or None when it cannot be read or changes while read."""
    from services.archived_sensitivity_evidence import fresh_content_identity

    try:
        found = fresh_content_identity(Path(path), cancel_event)
    except Exception:  # noqa: BLE001  (unreadable, changed while read, cancelled: no identity is invented)
        return None
    return {"path": str(path), "size": int(found["size"]), "sha256": str(found["sha256"])}


def fe_package_identity(manifest, cancel_event: Optional[threading.Event] = None,
                        before: Optional[dict] = None) -> Optional[dict]:
    """The FE read's identity: the manifest's path, size and SHA-256 and, under ``"package"``, every file the loader
    reads; None when the package cannot be identified or (with ``before``) changed since the snapshot."""
    from services import fe_package_identity as fpi

    try:
        package = fpi.identify(manifest, cancel_event)
    except Exception:  # noqa: BLE001  (missing, invalid, changed while read, cancelled: no identity is invented)
        return None
    if before is not None and not fpi.unchanged_since(package, before):
        return None
    return {"path": str(manifest), "size": package["manifest"]["size"], "sha256": package["manifest"]["sha256"],
            "package": package}


def confirm_fe_identity(manifest, recorded: Optional[dict], cancel_event: Optional[threading.Event] = None) -> dict:
    """The FE package identified again and equal, file by file, to the identity ``recorded`` at the read; raises
    ``fe_package_identity.PackageChanged`` or ``PackageIdentityRefused`` (missing record, cancellation). No import."""
    from services import fe_package_identity as fpi

    return fpi.confirm(manifest, (recorded or {}).get("package"), cancel_event)


def read_file(kind: str, preview) -> Path:
    """The file whose content a preview holds: the FE manifest or the experimental file the importer read."""
    return Path(preview.manifest_path if kind == FE else preview.source_path)


def run_read(kind: str, path, token: int, cancel_event: threading.Event) -> Outcome:
    """``read_preview`` as an outcome; every failure becomes a message, never an exception (worker thread)."""
    path = Path(path)
    before = _stat(path)
    package_before = None
    if kind == FE:
        from services import fe_package_identity as fpi

        package_before = fpi.stat_snapshot(path)  # the package's files as they are before the read
    try:
        preview = read_preview(kind, path, cancel_event)
    except PreviewRefused as error:
        return Outcome(kind, path, token, error=str(error))
    except Exception as error:  # noqa: BLE001  (the services' errors, cancellation, or anything unexpected)
        if cancel_event.is_set() or type(error).__name__ in ("AnalysisCancelled", "PreviewCancelled"):
            return Outcome(kind, path, token, cancelled=True)
        if type(error).__name__ in ("FePreviewError", "ExperimentalPreviewError"):
            return Outcome(kind, path, token, error=str(error))
        return Outcome(kind, path, token, error=f"The file could not be read ({type(error).__name__}: {error}).")
    if cancel_event.is_set():
        return Outcome(kind, path, token, cancelled=True)
    read = read_file(kind, preview)
    if kind == FE:
        identity = fe_package_identity(read, cancel_event, package_before) if read == path else None
        return Outcome(kind, path, token, preview=preview, identity=identity)
    identity = file_identity(read, cancel_event)
    if identity is not None and read == path and _stat(path) != before:
        identity = None  # the chosen file changed during the read: the data cannot be tied to one content
    return Outcome(kind, path, token, preview=preview, identity=identity)


class InspectSlot:
    """The read of one side: its state, and the preview or error of the current file only."""

    def __init__(self) -> None:
        self.token = 0
        self.state = IDLE
        self.path: Optional[Path] = None
        self.preview: Any = None
        self.identity: Any = None  # NEW-GUI.6-F1: the identity of the file read (Outcome.identity)
        self.message = ""
        self.cancel_event: Optional[threading.Event] = None

    def start(self, path) -> tuple[int, threading.Event]:
        """Begin a read of ``path``; an earlier read is cancelled and its outcome will be discarded."""
        self.reset()
        self.state, self.path = READING, Path(path)
        self.cancel_event = threading.Event()
        return self.token, self.cancel_event

    def reset(self) -> None:
        """Forget the preview and cancel a running read (file replaced, cleared or window closed)."""
        if self.cancel_event is not None:
            self.cancel_event.set()
        self.token += 1
        self.state, self.path, self.preview, self.message, self.cancel_event = IDLE, None, None, "", None
        self.identity = None

    def finish(self, outcome: Outcome) -> bool:
        """Show ``outcome`` only when it is the read now running for the same file; returns whether it was taken."""
        if self.state != READING or outcome.token != self.token or outcome.path != self.path:
            return False
        if outcome.cancelled:
            self.state, self.path, self.cancel_event = IDLE, None, None
            return True
        self.cancel_event = None
        if outcome.error:
            self.state, self.message = FAILED, outcome.error
        else:
            self.state, self.preview, self.identity = READ, outcome.preview, outcome.identity
        return True


# ---------------------------------------------------------------------------------------------- display rows


def _number(value: float) -> str:
    return f"{value:.6g}"


@dataclass(frozen=True)
class Section:
    """One table of a preview: an FE package, or one experimental modal set (never merged with another)."""

    title: str
    headers: tuple
    rows: tuple
    notes: tuple  # the importer's warnings and exclusions for this table


@dataclass(frozen=True)
class PreviewView:
    summary: str
    paths: tuple  # (caption, path) of the files read, shown in full
    facts: tuple  # what was read: step, kind, dataset types, details
    sections: tuple
    warnings: tuple  # warnings of the whole file
    note: str


def fe_view(preview) -> PreviewView:
    from services import local_fe_preview as fp

    rows = tuple((str(mode.number), fp.frequency_text(mode), fp.source_text(mode) or "not recorded",
                  str(mode.node_count)) for mode in preview.modes)
    paths = (("Package", str(preview.manifest_path)), ("FE source", preview.fe_source))
    facts = (f"Step: {preview.step_name}",) if preview.step_name else ()
    count = len(preview.modes)
    section = Section(f"FE modes — {count} mode{'s' if count != 1 else ''}", FE_HEADERS, rows, ())
    return PreviewView(fp.summary(preview), paths, facts, (section,), tuple(preview.warnings), fp.NOTE)


def _damping(record) -> str:
    return "—" if record.damping_ratio is None else f"{record.damping_ratio * 100:.3g}"


def experimental_view(preview) -> PreviewView:
    from services import local_experimental_preview as xp

    paths = [("File", str(preview.selected_path))]
    if Path(preview.source_path) != Path(preview.selected_path):
        paths.append(("Data read from the companion", str(preview.source_path)))
    facts = [f"Content: {xp.KIND_TEXT[preview.kind]}"]
    facts.append(f"Dataset types: {', '.join(str(x) for x in preview.dataset_types) or 'none'}")
    if preview.geometry_node_count:
        facts.append(f"Geometry nodes: {preview.geometry_node_count}")
    facts.extend(preview.details)
    sections = []
    for index, item in enumerate(preview.sets, 1):
        rows = tuple((str(r.number), _number(r.frequency_hz), r.label, str(r.point_count), str(r.measured_dof_count),
                      _damping(r)) for r in item.records)
        notes = []
        if any(r.provisional for r in item.records):
            notes.append(PROVISIONAL_NOTE)
        if item.excluded_residual:
            notes.append("Excluded by the importer as residual records: " + ", ".join(item.excluded_residual))
        if item.excluded_non_modal:
            notes.append("Excluded by the importer as non-modal records: " + ", ".join(item.excluded_non_modal))
        notes.extend(item.warnings)
        prefix = f"Modal set {index} of {len(preview.sets)}: " if preview.kind == xp.DATASET_55 else ""
        sections.append(Section(prefix + item.title, EXPERIMENTAL_HEADERS, rows, tuple(notes)))
    warnings = tuple(f"Dataset 2414 record {i}: {c}{'' if included else ', not loaded'}"
                     + (f" ({reason})" if reason else "")
                     for i, c, included, reason in preview.record_classifications)
    return PreviewView(xp.summary(preview), tuple(paths), tuple(facts), tuple(sections), warnings, xp.NOTE)


def view_of(kind: str, preview) -> PreviewView:
    return fe_view(preview) if kind == FE else experimental_view(preview)


__all__ = ["EXPERIMENTAL", "FE", "INSPECT", "InspectSlot", "Outcome", "PreviewView", "Section", "read_preview",
           "run_read", "view_of"]
