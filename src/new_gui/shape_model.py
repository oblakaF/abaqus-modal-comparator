"""NEW-GUI.3: one mode shape of an inspected file, drawn by the existing services, with no Qt.

After Inspect file (NEW-GUI.2) the window holds the preview the services returned. This module draws one loaded FE
mode or one experimental record of it with the services' own drawing:

- **FE.** ``services.local_fe_preview.render_fe_mode_shape(preview, index, component, directory, cancel_event)``.
- **Experimental.** ``services.local_experimental_preview.render_record_shape(preview_set, index, component,
  directory, cancel_event)``.

The FE mode and the experimental record are chosen by their position in the preview (``preview.modes[index]``,
``preview.sets[set_index].records[index]``), never by parsing a displayed name. Nothing is read again from the file,
and nothing is computed here: the image, its caption and every refusal (a component that was not measured, points
on one line, no spatial data) are the services'. Each shape is drawn on its own coordinates; there is no overlay,
orientation, node correspondence, MAC or mode pairing.

``run_render`` draws into a temporary folder made for that one request, reads the PNG and removes that folder
before it returns, so no image file is left behind. ``ShapeSlot`` keeps the current request of one side. A new
request, a changed choice, a replaced or cleared file, Inspect again or a closed window cancels the request, and
its outcome is discarded.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import tempfile
import threading
from typing import Any, Optional

from new_gui.workspace_state import EXPERIMENTAL, FE, KINDS

COMPONENTS = ("normal", "magnitude", "x", "y", "z")  # the services' SHAPE_COMPONENTS, in their order
COMPONENT_LABEL = {FE: {"normal": "Normal", "magnitude": "Magnitude", "x": "U1", "y": "U2", "z": "U3"},
                   EXPERIMENTAL: {"normal": "Normal", "magnitude": "Magnitude", "x": "X", "y": "Y", "z": "Z"}}
SHOW = "Show shape"
IDLE, DRAWING, SHOWN, REFUSED = "idle", "drawing", "shown", "refused"
CHOOSE_MODE = "Choose a mode..."
CHOOSE_SET = "Choose a modal set..."
CHOOSE_RECORD = "Choose a record..."
NOTHING_CHOSEN = {FE: "Choose a loaded FE mode and a component, then click Show shape.",
                  EXPERIMENTAL: "Choose a modal set, then a record in it and a component, then click Show shape."}
DRAWING_TEXT = "Drawing the shape..."
SHAPE_NOTE = ("One shape on its own coordinates, as the service draws it. It is not compared with the other side: "
              "no overlay, orientation, node correspondence, MAC or mode pair. The normal is taken to the best-fit "
              "plane of this data set alone.")
PROVISIONAL_TEXT = "PROVISIONAL — NOT A VALIDATED FITTED MODE"

_RENDER = threading.Lock()  # one drawing at a time across both sides (matplotlib figures)


@dataclass(frozen=True)
class ShapeOutcome:
    """The end of one drawing request: the PNG bytes and the service's caption, or its refusal, or a cancellation."""

    kind: str
    token: int
    image: bytes = b""
    lines: tuple = ()
    error: str = ""
    cancelled: bool = False


def _number(value: float) -> str:
    return f"{value:.6g}"


# ---------------------------------------------------------------------------------------------- choices


def fe_mode_options(preview) -> list:
    """(index, text) of every loaded FE mode, rigid-body and elastic alike, in the loader's order."""
    from services import local_fe_preview as fp

    return [(index, f"Mode {mode.number} — {fp.frequency_text(mode)} Hz") for index, mode in enumerate(preview.modes)]


def fe_mode_facts(preview, index: int) -> tuple:
    from services import local_fe_preview as fp

    mode = preview.modes[index]
    return (f"FE mode {mode.number}", f"Frequency: {fp.frequency_text(mode)} Hz",
            f"Frequency source: {fp.source_text(mode) or 'not recorded'}", f"FE nodes: {mode.node_count}")


def set_options(preview) -> list:
    """(set index, title) of every modal set of an experimental preview; none is preferred."""
    return [(index, item.title) for index, item in enumerate(preview.sets)]


def record_options(preview_set) -> list:
    """(index, text) of every record of one set, record 1 included, in the importer's order."""
    return [(index, f"Record {index + 1}: mode {record.number} — {_number(record.frequency_hz)} Hz")
            for index, record in enumerate(preview_set.records)]


def record_facts(preview_set, index: int) -> tuple:
    record = preview_set.records[index]
    damping = "not recorded" if record.damping_ratio is None else f"{record.damping_ratio * 100:.3g} %"
    return (f"Experimental record {record.number} ({preview_set.title})",
            f"Frequency: {_number(record.frequency_hz)} Hz",
            f"Classification: {record.label}",
            f"Points: {record.point_count}; measured DOFs: {record.measured_dof_count}; damping: {damping}")


def record_warnings(preview_set, index: int) -> tuple:
    """The importer's warnings about this record (they name it by its record reference), kept as written."""
    record = preview_set.records[index]
    reference = record.record_reference.lower()
    if not reference:
        return ()
    return tuple(w for w in preview_set.warnings if w.lower().startswith(reference))


def is_provisional(preview_set, index: int) -> bool:
    return bool(preview_set.records[index].provisional)


# ---------------------------------------------------------------------------------------------- drawing


def render(kind: str, source, index: int, component: str, directory, cancel_event=None):
    """Call the service of ``kind``: ``source`` is the FE preview or the experimental PreviewSet."""
    if kind not in KINDS:
        raise ValueError(f"unknown source kind {kind!r}")
    if component not in COMPONENTS:
        raise ValueError(f"unknown component {component!r}")
    with _RENDER:
        if kind == FE:
            from services import local_fe_preview as fp

            return fp.render_fe_mode_shape(source, index, component, directory, cancel_event=cancel_event)
        from services import local_experimental_preview as xp

        return xp.render_record_shape(source, index, component, directory, cancel_event=cancel_event)


def run_render(kind: str, source, index: int, component: str, token: int,
               cancel_event: threading.Event) -> ShapeOutcome:
    """Draw in a folder of this request only, read the PNG, remove the folder; every failure becomes an outcome."""
    folder = Path(tempfile.mkdtemp(prefix="new_gui_shape_"))
    try:
        if cancel_event.is_set():
            return ShapeOutcome(kind, token, cancelled=True)
        view = render(kind, source, index, component, folder, cancel_event)
        image_path = Path(view.image_path)
        if folder.resolve() not in image_path.resolve().parents:
            return ShapeOutcome(kind, token, error="The service wrote the image outside the request's folder.")
        image = image_path.read_bytes()
        if cancel_event.is_set():
            return ShapeOutcome(kind, token, cancelled=True)
        return ShapeOutcome(kind, token, image=image, lines=tuple(view.lines))
    except Exception as error:  # noqa: BLE001  (the services' refusals, cancellation, or anything unexpected)
        name = type(error).__name__
        if cancel_event.is_set() or name in ("AnalysisCancelled", "PreviewCancelled"):
            return ShapeOutcome(kind, token, cancelled=True)
        if name in ("FeShapeUnavailable", "ShapeViewUnavailable"):
            return ShapeOutcome(kind, token, error=str(error))
        return ShapeOutcome(kind, token, error=f"The shape could not be drawn ({name}: {error}).")
    finally:
        shutil.rmtree(folder, ignore_errors=True)  # only this request's own folder


class ShapeSlot:
    """The drawing request of one side: only the outcome of the current request is shown."""

    def __init__(self) -> None:
        self.token = 0
        self.state = IDLE
        self.outcome: Optional[ShapeOutcome] = None
        self.cancel_event: Optional[threading.Event] = None
        self.request: Any = None  # (set index or None, index, component) of the current request

    def start(self, request) -> tuple[int, threading.Event]:
        self.reset()
        self.state, self.request = DRAWING, request
        self.cancel_event = threading.Event()
        return self.token, self.cancel_event

    def reset(self) -> None:
        """Forget the shape and cancel a running request (choice changed, file replaced, closed...)."""
        if self.cancel_event is not None:
            self.cancel_event.set()
        self.token += 1
        self.state, self.outcome, self.cancel_event, self.request = IDLE, None, None, None

    def finish(self, outcome: ShapeOutcome) -> bool:
        if self.state != DRAWING or outcome.token != self.token:
            return False
        self.cancel_event = None
        if outcome.cancelled:
            self.state, self.request = IDLE, None
        elif outcome.error:
            self.state, self.outcome = REFUSED, outcome
        else:
            self.state, self.outcome = SHOWN, outcome
        return True


__all__ = ["COMPONENTS", "COMPONENT_LABEL", "ShapeOutcome", "ShapeSlot", "fe_mode_facts", "fe_mode_options",
           "record_facts", "record_options", "record_warnings", "render", "run_render", "set_options"]
