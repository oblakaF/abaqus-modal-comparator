"""APP-DATA.2: a read-only view of the FE modes in an extracted Abaqus package (File > Input file registry...).

The view loads the package with the existing loader ``abaqus_bridge.load_extracted_odb`` and shows what it accepted:
the FE source, the loaded mode numbers and their frequencies with the frequency source, and the loader's own
diagnostics (modes refused because their frequency records contradict each other, EIGFREQ not used, a clipped
extraction range). It has no frequency rule of its own: what the loader refuses is not shown as a mode, what it
accepts is shown unchanged, and no mode is excluded, renumbered, classified or paired.

It is a view only: not a physical registration, not a mode pairing; no MAC is computed and nothing is compared with
an experiment. Abaqus is never started; a plain ``.odb`` needs an existing extracted package. The files are only read.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from abaqus_bridge import AnalysisCancelled, FREQUENCY_SOURCE_HISTORY, load_extracted_odb

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
                     warnings=tuple(_warnings(metadata)))


def frequency_text(mode: PreviewMode) -> str:
    return f"{mode.frequency_hz:.6g}"


def source_text(mode: PreviewMode) -> str:
    if mode.frequency_source == FREQUENCY_SOURCE_HISTORY:
        return "EIGFREQ history"
    return mode.frequency_source + (f" ({mode.note})" if mode.note else "")


def summary(preview: Optional[FePreview]) -> str:
    if preview is None:
        return ""
    count = len(preview.modes)
    return (f"{count} mode{'s' if count != 1 else ''} loaded"
            + (f" ({preview.mode_numbers[0]}–{preview.mode_numbers[-1]})" if count else "")
            + (f"; {len(preview.warnings)} diagnostic message{'s' if len(preview.warnings) != 1 else ''}"
               if preview.warnings else "; no diagnostic messages"))
