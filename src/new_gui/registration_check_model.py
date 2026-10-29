"""NEW-GUI.5: whether an archived physical registration applies to the read FE and experimental data, with no Qt.

On the user's explicit command, the existing service
``services.new_odb_comparison.bind_registration_by_fe_geometry(experimental_path, abaqus, experimental_dataset)`` is
called with the data Inspect file already read:

- ``ExperimentalPreview.source_path``: the file the importer actually read (the UNV / UFF companion of an LMS
  project);
- ``FePreview.dataset``;
- ``ExperimentalPreview.sets[set_index].dataset``: the modal set the user chose for the frequency diagnostic
  (NEW-GUI.4); there is no second set choice.

Nothing is read again by the GUI and nothing is checked here: the service alone decides, from the experimental
file's fresh SHA-256 and size, the FE geometry identity, the modal set's replay of the frozen registration and the
sealed registration's content compatibility, whether an accepted registration (SP-02, SP-13) applies, or refuses
with its reason. A refusal does not say that the user's experiment is physically wrong.

The registration is never applied: no MAC is computed, no mode pair or orientation is made, and nothing is saved as
accepted for the workspace. The result is shown with "Verified archived reference for these selected data only.
Registration not applied. Modal identity and MAC not established."

One heavy check at a time: a check and the frequency diagnostic share one lock, because both may work on a large FE
model. ``RegistrationSlot`` keeps the current request; a replaced or cleared file, Inspect again, another modal set
or a closed window cancels it, and its outcome is discarded.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Any, Optional

from new_gui import diagnostic_model as dm

TITLE = "Archived physical registration — applicability check"
RUN = "Check reference registration"
NOT_CHECKED = "Not checked"
CHECKING = "Checking..."
VERIFIED = "Archived reference verified"
NOT_CONFIRMED = "Not confirmed"
CHECK_FAILED = "Check not completed"
CHECKING_TEXT = "Checking the archived registrations against the read data..."
WARNING = ("Verified archived reference for these selected data only. Registration not applied. Modal identity and "
           "MAC not established.")
REFUSAL_NOTE = ("No archived registration applies to these data. This does not mean that your experiment is "
                "physically wrong, and the frequency diagnostic above remains available.")
HINT = ("Checks, with the existing service, whether an accepted archived physical registration applies exactly to "
        "the read FE results and to the modal set chosen above for the frequency diagnostic. Nothing is applied: no "
        "orientation, node correspondence, MAC or mode pair is made, and nothing is saved for your workspace.")
NO_SET = "No modal set chosen above."
PROVISIONAL_TEXT = dm.PROVISIONAL_TEXT
IDLE, RUNNING, VERIFIED_STATE, REFUSED, FAILED = "idle", "running", "verified", "refused", "failed"

# One heavy check at a time, shared with the frequency diagnostic (both may project or hash a large FE model).
SERVICE_LOCK = dm._SERVICE


@dataclass(frozen=True)
class RegistrationView:
    """The service's verified registration, worded for display; nothing here is computed."""

    specimen: str
    fixture_id: str
    selected_set: str  # the modal set the user chose (the preview's wording)
    archived_modal_set: str  # the accepted fixture's modal set
    fe_geometry: str
    experimental_source: str
    registration: str
    registration_file: str
    checks: tuple
    limits: tuple
    warning: str = WARNING


@dataclass(frozen=True)
class RegistrationOutcome:
    """The end of one request: a verified registration, the service's refusal, an error or a cancellation."""

    token: int
    view: Optional[RegistrationView] = None
    refusal: str = ""
    error: str = ""
    cancelled: bool = False


def set_is_provisional(experimental_preview, set_index: Optional[int]) -> bool:
    """FRF peak records (dataset 58) in the chosen set: PROVISIONAL — NOT A VALIDATED FITTED MODE."""
    if experimental_preview is None or set_index is None:
        return False
    return any(record.provisional for record in experimental_preview.sets[set_index].records)


def check(fe_preview, experimental_preview, set_index: int, cancel_event=None):
    """The existing service on the data already read; raises its refusal (``AcceptedReferenceRefusal``)."""
    from services.new_odb_comparison import bind_registration_by_fe_geometry

    preview_set = experimental_preview.sets[set_index]
    if getattr(fe_preview, "dataset", None) is None or getattr(preview_set, "dataset", None) is None:
        raise ValueError("the read data are not available (Inspect the file again)")
    return bind_registration_by_fe_geometry(Path(experimental_preview.source_path), fe_preview.dataset,
                                            preview_set.dataset, cancel=cancel_event)


def registration_view(bound, experimental_preview, set_index: int) -> RegistrationView:
    provenance = bound.provenance()
    experimental = bound.experimental
    return RegistrationView(
        specimen=str(provenance["specimen"]), fixture_id=str(provenance["fixture_id"]),
        selected_set=dm.set_title(experimental_preview, set_index),
        archived_modal_set=str(provenance["modal_set"]),
        fe_geometry=f"SHA-256 {provenance['fe_geometry_sha256']} ({provenance['fe_node_count']} nodes)",
        experimental_source=(f"{experimental_preview.source_path} — SHA-256 {provenance['experimental_sha256']}, "
                             f"{experimental['size']} bytes (archived source "
                             f"{bound.fixture.experimental_source.file_name})"),
        registration=str(provenance["registration_hash"]), registration_file=str(provenance["registration_file"]),
        checks=tuple(str(item) for item in provenance["checks"]),
        limits=tuple(str(item) for item in provenance["limits"]))


def run_check(fe_preview, experimental_preview, set_index: int, token: int,
              cancel_event: threading.Event) -> RegistrationOutcome:
    """``check`` as an outcome; a refusal is the service's reason, never an exception (worker thread)."""
    from services.new_odb_comparison import AcceptedReferenceRefusal

    try:
        with SERVICE_LOCK:
            if cancel_event.is_set():
                return RegistrationOutcome(token, cancelled=True)
            bound = check(fe_preview, experimental_preview, set_index, cancel_event)
        view = registration_view(bound, experimental_preview, set_index)
    except AcceptedReferenceRefusal as refusal:
        if cancel_event.is_set():
            return RegistrationOutcome(token, cancelled=True)
        return RegistrationOutcome(token, refusal=str(refusal))
    except Exception as error:  # noqa: BLE001  (cancellation, the service's errors or anything unexpected)
        if cancel_event.is_set() or type(error).__name__ == "SensitivityCheckCancelled":
            return RegistrationOutcome(token, cancelled=True)
        return RegistrationOutcome(token, error=f"The check could not be completed ({type(error).__name__}: "
                                                f"{error}).")
    if cancel_event.is_set():  # the service does not stop midway: a late cancellation discards its result
        return RegistrationOutcome(token, cancelled=True)
    return RegistrationOutcome(token, view=view)


class RegistrationSlot:
    """The check request: only the outcome of the current request for the current inputs is shown."""

    def __init__(self) -> None:
        self.token = 0
        self.state = IDLE
        self.outcome: Optional[RegistrationOutcome] = None
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

    def finish(self, outcome: RegistrationOutcome) -> bool:
        if self.state != RUNNING or outcome.token != self.token:
            return False
        self.cancel_event = None
        if outcome.cancelled:
            self.state, self.request = IDLE, None
        elif outcome.view is not None:
            self.state, self.outcome = VERIFIED_STATE, outcome
        elif outcome.refusal:
            self.state, self.outcome = REFUSED, outcome
        else:
            self.state, self.outcome = FAILED, outcome
        return True


__all__ = ["RegistrationOutcome", "RegistrationSlot", "RegistrationView", "check", "registration_view", "run_check",
           "set_is_provisional"]
