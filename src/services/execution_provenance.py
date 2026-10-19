"""Execution provenance of a journalled campaign run root — Auto-ID M8-D2i (read-only, presentation and export guard).

A run executed through the guarded controller (``services.guarded_execution``) leaves two independent records in its
run root:

- the attempt log ``guarded_execution.json``;
- for a run attested by a simulated (test-only) authority, the marker ``SIMULATED_TEST_EXECUTION.json``.

``run_execution_provenance`` reads them and gives one state:

| State | Meaning | Blocking |
|---|---|---|
| ``SIMULATED_TEST_EXECUTION_NEVER_A_MATERIAL_RESULT`` | the marker exists or the log records a simulated attempt | yes |
| ``EXECUTION_LOG_UNREADABLE`` | the log exists but cannot be read or is not an attempt log; a simulated origin cannot be excluded | yes |
| ``GUARDED_EXECUTION_RECORDED`` | the log records only non-simulated attempts | no |
| ``NO_GUARDED_EXECUTION_RECORD`` | no guarded record at all, for example the archived M7 CLI runs | no |

For the non-blocking states the existing journal and evidence checks apply unchanged.  ``NO_GUARDED_EXECUTION_RECORD``
is **not** evidence of a real origin: it only says that this guard has nothing to add.

A blocking run is never presented as a material result of a real specimen, never shows Engineering Constants and is
never exported as ordinary material evidence.  The scientific backend's own record is never changed.
"""

from __future__ import annotations

from enum import Enum
import json
from pathlib import Path
from typing import Mapping

EXECUTION_LOG = "guarded_execution.json"
EXECUTION_LOG_SCHEMA = "auto-id/guarded-execution-log/v1"
SIMULATED_MARKER = "SIMULATED_TEST_EXECUTION.json"
SIMULATED = "SIMULATED_TEST_EXECUTION_NEVER_A_MATERIAL_RESULT"


class ProvenanceState(str, Enum):
    SIMULATED = SIMULATED
    LOG_UNREADABLE = "EXECUTION_LOG_UNREADABLE"
    GUARDED = "GUARDED_EXECUTION_RECORDED"
    NO_RECORD = "NO_GUARDED_EXECUTION_RECORD"


BLOCKING = (ProvenanceState.SIMULATED, ProvenanceState.LOG_UNREADABLE)


def run_root(journal_path) -> Path:
    """``<run root>/campaign/<run hash>/journal.json`` → ``<run root>``."""
    return Path(journal_path).resolve().parents[2]


def run_execution_provenance(journal_path) -> tuple[ProvenanceState, str]:
    """The execution provenance of the run root of a campaign journal (read-only)."""

    try:
        root = run_root(journal_path)
    except IndexError:
        return ProvenanceState.NO_RECORD, "no run root (not the campaign-run journal layout); no guarded record"
    if (root / SIMULATED_MARKER).exists():
        return ProvenanceState.SIMULATED, (f"{root / SIMULATED_MARKER} marks a simulated test execution: never a "
                                           "material result")
    log = root / EXECUTION_LOG
    if not log.exists():
        return ProvenanceState.NO_RECORD, ("no guarded-execution record: the run was not executed through the M8-D2i "
                                           "controller (for example the archived M7 CLI runs). This is not evidence "
                                           "of a real origin; the existing journal and evidence checks apply unchanged")
    try:
        document = json.loads(log.read_text(encoding="utf-8"))
        attempts = document["attempts"] if document.get("schema") == EXECUTION_LOG_SCHEMA else None
        if not isinstance(attempts, list):
            raise ValueError("not an attempt log")
    except (OSError, UnicodeDecodeError, ValueError, KeyError, AttributeError, TypeError) as error:
        return ProvenanceState.LOG_UNREADABLE, (f"{log} cannot be read ({error}); a simulated origin cannot be "
                                                "excluded")
    if any(not isinstance(a, Mapping) or a.get("simulated") is not False for a in attempts):
        return ProvenanceState.SIMULATED, f"{log} records a simulated (or unlabelled) attempt: never a material result"
    return ProvenanceState.GUARDED, f"{log} records {len(attempts)} non-simulated guarded attempt(s)"


def blocking(state: ProvenanceState) -> bool:
    return state in BLOCKING


__all__ = ["BLOCKING", "EXECUTION_LOG", "EXECUTION_LOG_SCHEMA", "ProvenanceState", "SIMULATED", "SIMULATED_MARKER",
           "blocking", "run_execution_provenance", "run_root"]
