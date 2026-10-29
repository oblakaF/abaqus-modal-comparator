"""NEW-GUI.4: the frequency diagnostic of the read FE and experimental data, with no Qt.

After Inspect file (NEW-GUI.2) has read both sides and the user has chosen one experimental modal set, the existing
service ``services.new_odb_comparison.frequency_only_diagnostic(abaqus, experimental, reason)`` is called with the
data already read: ``FePreview.dataset`` and ``ExperimentalPreview.sets[set_index].dataset``. Nothing is read again
and nothing is computed here. The FE and experimental frequencies, the nearest and next elastic FE frequencies of
each experimental mode, their signed differences, the FE rigid-body modes (by the comparator's shape criterion, never
a frequency threshold) and the out-of-range notes are the service's.

The diagnostic status is FREQUENCY_ONLY_DIAGNOSTIC because no physical registration between the FE model and the
experiment has been established or verified for this workspace. No accepted registration is looked up or reused,
the research archive is not read, no orientation is chosen, no node correspondence is made, no MAC is computed and
no mode pair is formed: the nearest-frequency columns describe frequency proximity only.

This module only words the service's result for display: every experimental record is kept (record 1 included),
and each row carries the importer's classification of its record (PROVISIONAL for FRF peak records of dataset 58,
AMBIGUOUS with the importer's wording for ambiguous records) and the set keeps the importer's warnings.

``run_diagnostic`` turns every failure into an outcome (worker thread); one diagnostic runs at a time. ``DiagnosticSlot`` keeps the current
request: a replaced or cleared file, Inspect again, another modal set or a closed window cancels it, and its
outcome is discarded.
"""

from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Any, Optional

RUN = "Run frequency diagnostic"
STATUS = "FREQUENCY_ONLY_DIAGNOSTIC"
REASON = ("no physical registration between the FE model and the experiment has been established or verified for "
          "this workspace, so no orientation, node correspondence, MAC or mode pair exists.")
NEAREST_TITLE = "Nearest by frequency — NOT a mode pair"
NOT_COMPUTED = "NOT_COMPUTED"
MODE_PAIRS = "NONE (physical modal correspondence not verified)"
PROVISIONAL_TEXT = "PROVISIONAL — NOT A VALIDATED FITTED MODE"
SIGN_NOTE = ("Difference (%) = (f FE − f EXP) / f EXP × 100, the comparator's sign convention: a positive value means "
             "the FE frequency is higher.")
CHOOSE_SET = "Choose a modal set..."
RUNNING_TEXT = "Computing the frequency diagnostic..."
NEED_FE = "The FE results are not read: choose the FE file on the Workspace page and click Inspect file."
NEED_EXPERIMENTAL = ("The experimental data are not read: choose the experimental file on the Workspace page and "
                     "click Inspect file.")
NEED_SET = "Choose the experimental modal set to compare."
IDLE, RUNNING, DONE, FAILED = "idle", "running", "done", "failed"

NEAREST_HEADERS = ("Exp record", "Exp mode", "Exp frequency (Hz)", "Nearest FE mode", "Nearest FE (Hz)",
                   "Difference (%)", "Next FE mode", "Next FE (Hz)", "Next difference (%)", "MAC",
                   "Classification (importer)", "Note")
FE_HEADERS = ("FE mode", "Frequency (Hz)")
RIGID_HEADERS = ("FE mode", "Frequency (Hz)", "Rigid-body residual")
EXPERIMENTAL_HEADERS = ("Exp record", "Exp mode", "Frequency (Hz)", "Classification (importer)")
DASH = "—"

# One diagnostic at a time: the service cannot be stopped midway, and on a large FE model its rigid-body projection
# needs much memory. A new request waits until a discarded one has ended (the residuals it recorded are then reused).
_SERVICE = threading.Lock()


@dataclass(frozen=True)
class DiagnosticOutcome:
    """The end of one request: the service's diagnostic, or an error message, or a cancellation."""

    token: int
    diagnostic: Any = None
    view: Any = None  # the diagnostic worded for display (DiagnosticView)
    error: str = ""
    cancelled: bool = False


# ---------------------------------------------------------------------------------------------- choices


def set_title(preview, index: int) -> str:
    return f"Modal set {index + 1} of {len(preview.sets)}: {preview.sets[index].title}"


def set_options(preview) -> list:
    """(set index, text) of every modal set of an experimental preview; none is preferred."""
    return [(index, set_title(preview, index)) for index in range(len(preview.sets))]


def unavailable(fe_preview, experimental_preview, set_index: Optional[int]) -> tuple:
    """Why the diagnostic cannot run yet (empty when it can), in the order the user acts."""
    reasons = []
    if fe_preview is None:
        reasons.append(NEED_FE)
    if experimental_preview is None:
        reasons.append(NEED_EXPERIMENTAL)
    elif set_index is None:
        reasons.append(NEED_SET)
    return tuple(reasons)


# ---------------------------------------------------------------------------------------------- the service


def diagnose(fe_preview, preview_set):
    """The existing service on the data already read; nothing is read again."""
    from services.new_odb_comparison import frequency_only_diagnostic

    if getattr(fe_preview, "dataset", None) is None or getattr(preview_set, "dataset", None) is None:
        raise ValueError("the read data are not available (Inspect the file again)")
    return frequency_only_diagnostic(fe_preview.dataset, preview_set.dataset, REASON)


def run_diagnostic(fe_preview, experimental_preview, set_index: int, token: int,
                   cancel_event: threading.Event) -> DiagnosticOutcome:
    """``diagnose`` and its display wording as an outcome; every failure becomes a message (worker thread)."""
    try:
        with _SERVICE:
            if cancel_event.is_set():
                return DiagnosticOutcome(token, cancelled=True)
            preview_set = experimental_preview.sets[set_index]
            diagnostic = diagnose(fe_preview, preview_set)
        view = diagnostic_view(diagnostic, preview_set, set_title(experimental_preview, set_index))
    except Exception as error:  # noqa: BLE001  (the service's errors or anything unexpected)
        if cancel_event.is_set():
            return DiagnosticOutcome(token, cancelled=True)
        return DiagnosticOutcome(token, error=f"The frequency diagnostic could not be computed "
                                              f"({type(error).__name__}: {error}).")
    if cancel_event.is_set():  # the service does not stop midway: a late cancellation discards its result
        return DiagnosticOutcome(token, cancelled=True)
    return DiagnosticOutcome(token, diagnostic=diagnostic, view=view)


class DiagnosticSlot:
    """The diagnostic request: only the outcome of the current request for the current inputs is shown."""

    def __init__(self) -> None:
        self.token = 0
        self.state = IDLE
        self.outcome: Optional[DiagnosticOutcome] = None
        self.cancel_event: Optional[threading.Event] = None
        self.request: Any = None  # (FE preview, experimental preview, set index) of the current request

    def start(self, request) -> tuple[int, threading.Event]:
        self.reset()
        self.state, self.request = RUNNING, request
        self.cancel_event = threading.Event()
        return self.token, self.cancel_event

    def reset(self) -> None:
        """Forget the result and cancel a running request (inputs replaced, another set, window closed)."""
        if self.cancel_event is not None:
            self.cancel_event.set()
        self.token += 1
        self.state, self.outcome, self.cancel_event, self.request = IDLE, None, None, None

    def finish(self, outcome: DiagnosticOutcome) -> bool:
        if self.state != RUNNING or outcome.token != self.token:
            return False
        self.cancel_event = None
        if outcome.cancelled:
            self.state, self.request = IDLE, None
        elif outcome.error:
            self.state, self.outcome = FAILED, outcome
        else:
            self.state, self.outcome = DONE, outcome
        return True


# ---------------------------------------------------------------------------------------------- display rows


def _hz(value: Optional[float]) -> str:
    return DASH if value is None else f"{value:.4f}"


def _percent(value: Optional[float]) -> str:
    return DASH if value is None else f"{value:+.2f}"


def _mode(value: Optional[int]) -> str:
    return DASH if value is None else str(value)


def _records_in_row_order(diagnostic, preview_set) -> list:
    """(record position, record) for each row: the service lists the set's modes by number, in a stable order."""
    records = list(preview_set.records)
    order = sorted(range(len(records)), key=lambda i: records[i].number)  # as ModalDataset.sorted_modes
    matched = [(i, records[i]) for i in order]
    if len(matched) != len(diagnostic.rows) or any(
            record.number != row.experimental_mode or abs(record.frequency_hz - row.experimental_hz) > 1e-9
            * max(1.0, abs(row.experimental_hz)) for (_, record), row in zip(matched, diagnostic.rows)):
        raise ValueError("the diagnostic's experimental modes are not the records of the chosen set")
    return matched


@dataclass(frozen=True)
class DiagnosticView:
    status: str
    statement: str
    reason: str
    set_title: str
    experimental_source: str
    provisional: bool
    nearest_rows: tuple
    fe_rows: tuple
    rigid_rows: tuple
    rigid_criterion: str
    experimental_rows: tuple
    range_warnings: tuple  # experimental frequencies outside the extracted FE range
    importer_warnings: tuple  # the importer's warnings of the chosen set, as written
    mac: str = NOT_COMPUTED
    mode_pairs: str = MODE_PAIRS


def diagnostic_view(diagnostic, preview_set, title: str) -> DiagnosticView:
    """The service's diagnostic worded for display; no value is computed or changed here."""
    from services.new_odb_comparison import RIGID_BODY_CRITERION

    matched = _records_in_row_order(diagnostic, preview_set)
    nearest, experimental, out_of_range = [], [], []
    for (position, record), row in zip(matched, diagnostic.rows):
        note = diagnostic.range_note(row.experimental_hz)
        notes = [PROVISIONAL_TEXT] if record.provisional else []
        if record.ambiguous:
            notes.append("AMBIGUOUS (importer)")
        if note:
            notes.append(note)
            out_of_range.append(f"Exp record {position + 1} (mode {row.experimental_mode}, "
                                f"{row.experimental_hz:.4f} Hz): {note}.")
        if row.nearest_fe_mode is None:
            notes.append("no elastic FE frequency")
        nearest.append((str(position + 1), str(row.experimental_mode), _hz(row.experimental_hz),
                        _mode(row.nearest_fe_mode), _hz(row.nearest_fe_hz), _percent(row.nearest_difference_percent),
                        _mode(row.next_fe_mode), _hz(row.next_fe_hz), _percent(row.next_difference_percent),
                        NOT_COMPUTED, record.label, "; ".join(notes) or DASH))
        experimental.append((str(position + 1), str(row.experimental_mode), _hz(row.experimental_hz), record.label))
    return DiagnosticView(
        status=diagnostic.status, statement=diagnostic.statement, reason=diagnostic.reason, set_title=title, experimental_source=diagnostic.experimental_source,
        provisional=diagnostic.provisional_experimental, nearest_rows=tuple(nearest),
        fe_rows=tuple((str(n), f"{f:.4f}") for n, f in diagnostic.fe_modes),
        rigid_rows=tuple((str(n), f"{f:.6g}", f"{r:.2g}") for n, f, r in diagnostic.rigid_fe_modes),
        rigid_criterion=RIGID_BODY_CRITERION, experimental_rows=tuple(experimental),
        range_warnings=tuple(out_of_range), importer_warnings=tuple(preview_set.warnings))


__all__ = ["DiagnosticOutcome", "DiagnosticSlot", "DiagnosticView", "diagnose", "diagnostic_view", "run_diagnostic",
           "set_options", "set_title", "unavailable"]
