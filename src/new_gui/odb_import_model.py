"""PRIORITY-0 / RC6: the state of the ODB import of the new interface, with no Qt (testable headless).

An ``.odb`` chosen as the FE file is not viewable itself. The import dialog (``new_gui.odb_import_dialog``) shows what
``services.odb_import_service.plan_extraction`` found (the file, the Abaqus launcher, the results folder, the free
space) and the user's explicit command Extract modal results starts ``run_extraction`` in a worker thread. The
outcome is the extracted package's ``manifest.json``, which the window then puts into the workspace as the FE file
and reads with Inspect file — the existing route, unchanged.

``ImportSlot`` keeps one run: its progress lines, its outcome, and the cancellation of a running one. An outcome of
a cancelled or replaced run is discarded, never shown.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Any, Optional

from services import odb_import_service as svc

TITLE = "Extract modal results from the ODB"
EXTRACT = "Extract modal results"
CONFIRM_TEXT = ("Abaqus Python will be started now with the extraction script, which opens the ODB read-only and "
                "writes the frequencies, the node geometry and the mode shapes (U1, U2, U3) of the requested modes "
                "into a new folder. No analysis is solved and nothing in the ODB is changed. Start it?")
NOTE = ("The program starts nothing by itself: the extraction runs only after you confirm it. The ODB is opened "
        "readOnly=True by the project's existing extractor (abaqus_scripts/extract_odb.py). The package is written "
        "into a new sub-folder of the results folder; existing results are never overwritten. A package already "
        "extracted from the same ODB content (SHA-256) and the same range is reused without starting Abaqus. Reading "
        "the package afterwards uses the program's usual read cache under %LOCALAPPDATA%, which is usually on C:.")
RANGE_NOTE = ("The requested range is clipped to the modes the ODB holds; the range actually extracted is shown "
              "afterwards. The first elastic mode (for example FE7 of a free-free plate) is never skipped by the "
              "program: start the range at 1 to see every mode, rigid-body modes included.")
IDLE, PLANNING, RUNNING, DONE, FAILED, CANCELLED = "idle", "planning", "running", "done", "failed", "cancelled"


@dataclass(frozen=True)
class ImportOutcome:
    token: int
    result: Any = None  # svc.ExtractionResult
    error: str = ""
    cancelled: bool = False


def run_import(plan, token: int, cancel_event: threading.Event, progress, runner=None) -> ImportOutcome:
    """``svc.run_extraction`` as an outcome; every failure becomes a message (worker thread)."""
    try:
        result = svc.run_extraction(plan, confirmed=True, cancel_event=cancel_event, progress=progress, runner=runner)
    except svc.OdbImportCancelled as error:
        return ImportOutcome(token, error=str(error), cancelled=True)
    except svc.OdbImportRefused as error:
        return ImportOutcome(token, error=str(error))
    except Exception as error:  # noqa: BLE001  (anything unexpected: a message, never a crash of the window)
        if cancel_event.is_set():
            return ImportOutcome(token, cancelled=True)
        return ImportOutcome(token, error=f"The extraction could not be completed ({type(error).__name__}: {error}).")
    if cancel_event.is_set():
        return ImportOutcome(token, cancelled=True)
    return ImportOutcome(token, result=result)


class ImportSlot:
    """One extraction run at a time: its state, progress and outcome."""

    def __init__(self) -> None:
        self.token = 0
        self.state = IDLE
        self.plan: Any = None
        self.progress: list = []
        self.outcome: Optional[ImportOutcome] = None
        self.cancel_event: Optional[threading.Event] = None

    def start(self, plan) -> tuple[int, threading.Event]:
        self.reset()
        self.state, self.plan = RUNNING, plan
        self.cancel_event = threading.Event()
        return self.token, self.cancel_event

    def reset(self) -> None:
        if self.cancel_event is not None:
            self.cancel_event.set()
        self.token += 1
        self.state, self.plan, self.progress, self.outcome, self.cancel_event = IDLE, None, [], None, None

    def cancel(self) -> bool:
        if self.state != RUNNING or self.cancel_event is None:
            return False
        self.cancel_event.set()
        return True

    def note(self, token: int, text: str) -> bool:
        if token != self.token or self.state != RUNNING:
            return False
        self.progress.append(text)
        del self.progress[:-200]
        return True

    def finish(self, outcome: ImportOutcome) -> bool:
        if self.state != RUNNING or outcome.token != self.token:
            return False
        self.cancel_event = None
        self.outcome = outcome
        self.state = CANCELLED if outcome.cancelled else (FAILED if outcome.error else DONE)
        return True

    @property
    def manifest_path(self) -> Optional[Path]:
        if self.state == DONE and self.outcome is not None and self.outcome.result is not None:
            return Path(self.outcome.result.manifest_path)
        return None


def result_lines(result) -> tuple:
    """The facts of a finished extraction, worded for display."""
    lines = [("Package", str(result.package_folder)),
             ("Manifest", str(result.manifest_path)),
             ("Requested modes", f"{result.requested[0]}-{result.requested[1]}" if result.requested else "—"),
             ("Extracted modes", f"{result.extracted_range_text} ({len(result.extracted_modes)} modes)")]
    if result.available_range:
        lines.append(("Modes in the ODB", f"{result.available_range[0]}-{result.available_range[1]} (reported by the "
                                          "extractor)"))
    if result.range_notice:
        lines.append(("Range note", result.range_notice))
    lines.append(("Source", "reused: a package of the same ODB content and range already existed; Abaqus was not "
                            "started" if result.reused else "extracted now from the ODB (opened read-only)"))
    sha = (result.source.get("odb") or {}).get("sha256", "")
    if sha:
        lines.append(("ODB SHA-256", sha))
    if result.log_path:
        lines.append(("Log", str(result.log_path)))
    return tuple(lines)


__all__ = ["CANCELLED", "CONFIRM_TEXT", "DONE", "EXTRACT", "FAILED", "IDLE", "ImportOutcome", "ImportSlot", "NOTE",
           "RANGE_NOTE", "RUNNING", "TITLE", "result_lines", "run_import"]
