"""APP-DATA.2: a read-only view of the FE modes in an extracted Abaqus package (File > Input file registry...).

The view loads the package with the existing loader ``abaqus_bridge.load_extracted_odb`` and shows what it accepted:
the FE source, the loaded mode numbers and their frequencies with the frequency source, and the loader's own
diagnostics (modes refused because their frequency records contradict each other, EIGFREQ not used, a clipped
extraction range). It has no frequency rule of its own: what the loader refuses is not shown as a mode, what it
accepts is shown unchanged, and no mode is excluded, renumbered, classified or paired.

It is a view only: not a physical registration, not a mode pairing; no MAC is computed and nothing is compared with
an experiment. Abaqus is never started; a plain ``.odb`` needs an existing extracted package. The files are only read.

APP-DATA.5: ``render_fe_mode_shape`` draws one loaded mode on its own FE nodes and coordinates with
``services.modal_data_viewer.render_viewer_mode`` (role FE: the drawing of the main window's individual-mode viewer,
unchanged). Every loaded mode can be drawn, rigid-body or elastic; nothing is classified or excluded here. Points on
one line get no out-of-plane view (the same rule as the experimental shape view of APP-DATA.4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import threading
from typing import Any, Optional

from abaqus_bridge import AnalysisCancelled, FREQUENCY_SOURCE_HISTORY, load_extracted_odb
from modal_core import ModalDataset
from services import modal_data_viewer as viewer
from services.local_experimental_preview import _collinear  # one rule for "points on one line" in both views

NOTE = ("A view of the FE modes of an extracted package only. It is not a physical registration and not a mode "
        "pairing: no MAC is computed, nothing is compared with an experiment and no mode is excluded.")
ODB_NEEDS_PACKAGE = ("This entry is an Abaqus .odb. Its modes can be viewed only from an existing extracted package "
                     "(manifest.json with its CSV files): add that manifest.json to the registry. Abaqus is not started "
                     "for a preview.")


class FePreviewError(ValueError):
    """The package cannot be previewed (an .odb, a missing or damaged file, no usable mode)."""


@dataclass(frozen=True)
class PreviewMode:
    number: int
    frequency_hz: float
    frequency_source: str
    node_count: int
    note: str = ""


@dataclass(frozen=True)
class FePreview:
    manifest_path: Path
    fe_source: str
    step_name: str
    modes: tuple
    warnings: tuple
    # the loader's dataset (its modes in the order of ``modes``), kept for the shape view only
    dataset: Any = field(default=None, compare=False, repr=False)

    @property
    def mode_numbers(self) -> list:
        return [mode.number for mode in self.modes]


def _warnings(metadata: dict) -> list:
    """The loader's own diagnostics, as recorded in the dataset metadata."""
    warnings = []
    for mode, item in (metadata.get("rejected_frequency_modes") or {}).items():
        warnings.append(f"Mode {mode} not loaded: {item.get('reason', 'its frequency records contradict each other')}.")
    for mode, note in (metadata.get("eigfreq_not_used_for_consistency") or {}).items():
        warnings.append(f"Mode {mode}: EIGFREQ not used for the consistency check ({note}).")
    notice = metadata.get("extraction_range_notice")
    if notice:
        warnings.append(str(notice))
    return warnings


def preview_fe_package(path, cancel_event=None) -> FePreview:
    """Load an extracted package with ``load_extracted_odb`` and describe what it accepted. Raises FePreviewError for
    an .odb or an unreadable package and AnalysisCancelled when ``cancel_event`` is set during reading."""
    path = Path(path)
    if path.suffix.lower() == ".odb":
        raise FePreviewError(ODB_NEEDS_PACKAGE)
    if not path.is_file():
        raise FePreviewError(f"The file {path} does not exist.")
    try:
        dataset = load_extracted_odb(path, cancel_event=cancel_event)
    except AnalysisCancelled:
        raise
    except FileNotFoundError as error:
        raise FePreviewError(f"The extracted package is incomplete: {error}") from error
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as error:  # invalid JSON, malformed entries
        # or CSV (a manifest that is not a JSON object), no usable mode
        raise FePreviewError(f"The extracted package cannot be read: {error}") from error
    metadata = dataset.metadata or {}
    modes = []
    for mode in dataset.modes:
        info = mode.metadata or {}
        modes.append(PreviewMode(number=int(mode.number), frequency_hz=float(mode.frequency_hz),
                                 frequency_source=str(info.get("frequency_source", "")),
                                 node_count=len(mode.node_ids), note=str(info.get("frequency_history_note") or "")))
    return FePreview(manifest_path=path, fe_source=str(metadata.get("odb_path") or path),
                     step_name=str(metadata.get("step_name") or ""), modes=tuple(modes),
                     warnings=tuple(_warnings(metadata)), dataset=dataset)


def frequency_text(mode: PreviewMode) -> str:
    return f"{mode.frequency_hz:.6g}"


def source_text(mode: PreviewMode) -> str:
    if mode.frequency_source == FREQUENCY_SOURCE_HISTORY:
        return "EIGFREQ history"
    return mode.frequency_source + (f" ({mode.note})" if mode.note else "")


SHAPE_COMPONENTS = viewer.COMPONENTS
COMPONENT_TEXT = viewer.COMPONENT_TEXT[viewer.FE]
_RENDER_LOCK = threading.Lock()  # one matplotlib figure at a time


class FeShapeUnavailable(ValueError):
    """No spatial view of the FE mode can be drawn; the reason is stated and nothing is created."""


@dataclass(frozen=True)
class FeShapeView:
    image_path: Path
    index: int  # the mode's position in the package's loaded modes
    mode: PreviewMode
    component: str
    points_shown: int
    lines: tuple  # the caption: mode, frequency and its source, what is drawn


def _check(cancel_event) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise AnalysisCancelled("The FE mode view was closed.")


def render_fe_mode_shape(preview: FePreview, index: int, component: str, directory,
                         cancel_event=None) -> FeShapeView:
    """Draw loaded mode ``index`` of ``preview`` on its own FE nodes with the main window's viewer (read-only)."""
    if component not in SHAPE_COMPONENTS:
        raise ValueError(f"unknown component {component!r}; choose one of {', '.join(SHAPE_COMPONENTS)}.")
    dataset = preview.dataset
    if dataset is None or not 0 <= int(index) < len(preview.modes) or len(dataset.modes) != len(preview.modes):
        raise FeShapeUnavailable("The mode is not in the loaded data of this package.")
    row, mode = preview.modes[index], dataset.modes[index]
    if (int(mode.number), float(mode.frequency_hz)) != (row.number, row.frequency_hz):
        raise FeShapeUnavailable("The mode does not match the loaded data of this package.")
    available, reason = viewer.spatial_status(mode)
    if not available:
        raise FeShapeUnavailable(f"No spatial view of this mode: {reason}")
    if component == "normal" and _collinear(mode.coordinates):
        raise FeShapeUnavailable("The FE nodes lie on one line: no best-fit plane and no normal to it are defined, "
                                 "so no out-of-plane view is drawn. Choose U1, U2, U3 or magnitude.")
    _check(cancel_event)
    # The loaded mode itself, alone in a dataset: the drawing cannot pick another mode of the package.
    single = ModalDataset(dataset.source_name, dataset.source_path, [mode], metadata=dict(dataset.metadata or {}))
    with _RENDER_LOCK:
        path, _ = viewer.render_viewer_mode(single, viewer.FE, int(mode.number), component, Path(directory))
    _check(cancel_event)
    lines = [f"FE mode {row.number} — {frequency_text(row)} Hz; frequency source: {source_text(row) or 'not recorded'}.",
             f"Shown: {COMPONENT_TEXT[component]} on {row.node_count} FE nodes at their own coordinates (extracted "
             "package). No experiment, mapping or MAC.",
             "Every loaded mode can be viewed: rigid-body and elastic modes are not classified or excluded here."]
    mode_warnings = [text for text in preview.warnings if text.startswith(f"Mode {row.number}:")]
    lines.extend(f"Loader: {text}" for text in mode_warnings)
    return FeShapeView(image_path=Path(path), index=int(index), mode=row, component=component,
                       points_shown=row.node_count, lines=tuple(lines))


def summary(preview: Optional[FePreview]) -> str:
    if preview is None:
        return ""
    count = len(preview.modes)
    return (f"{count} mode{'s' if count != 1 else ''} loaded"
            + (f" ({preview.mode_numbers[0]}–{preview.mode_numbers[-1]})" if count else "")
            + (f"; {len(preview.warnings)} diagnostic message{'s' if len(preview.warnings) != 1 else ''}"
               if preview.warnings else "; no diagnostic messages"))
