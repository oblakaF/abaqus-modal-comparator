"""APP-DATA.3: a read-only view of the experimental modal data in a UNV / UFF / LMS file (Input file registry).

The view uses the comparator's own importer, unchanged:

- ``universal_reader.resolve_testlab_file`` resolves an LMS project to its companion UNV / UFF;
- ``universal_reader.discover_experimental_modal_sets`` lists the fitted dataset-55 modal sets; none is chosen;
- each set is loaded on its own with the importer the analysis uses (``universal_reader.load_universal_modal_file``
  as installed, with ``modal_set=<key>``), so its records, excluded residual / non-modal records and import warnings
  are the importer's;
- without a dataset-55 set the importer is called without a set: it uses dataset 2414 (with its record
  classification) or, for FRF-only data, dataset 58;
- every record is classified by ``services.modal_data_viewer.experimental_classification``. FRF peak-derived records
  are labelled PROVISIONAL — NOT A VALIDATED FITTED MODE.

Nothing is chosen, merged, excluded, renumbered or paired with an FE model; no MAC is computed. The files are only
read. The importer reads a file in one call, so a cancel takes effect between files / sets, not inside a read.

APP-DATA.4: ``render_record_shape`` draws one record of one set on its own measured points with
``services.modal_data_viewer.render_viewer_mode`` (the drawing, phase alignment and normalisation of the main window's
individual-mode viewer, unchanged). Only the points where the chosen component is a measured DOF of the record are
drawn; a component the importer did not record as measured is refused with its reason, and no value is created.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import threading
from typing import Any, Optional

import numpy as np

import universal_reader
from modal_core import ModalDataset, ModeShape
from services import modal_data_viewer as viewer

DATASET_55 = "DATASET_55_MODAL_SETS"
DATASET_2414 = "DATASET_2414_MODES"
FRF_58 = "FRF_DATASET_58"
PROVISIONAL = "PROVISIONAL — NOT A VALIDATED FITTED MODE"
AMBIGUOUS = "AMBIGUOUS (importer)"
NOTE = ("A view of the experimental data in this file only. Nothing is compared with an FE model, no modal set is "
        "selected for an analysis, no mode is excluded or paired and no MAC is computed.")
KIND_TEXT = {
    DATASET_55: "fitted modal sets (dataset 55)",
    DATASET_2414: ("no usable dataset-55 modal set; the importer used dataset 2414 records (curve-fitted modal "
                   "datasets, with the record classification below)"),
    FRF_58: ("FRF data (dataset 58) without a fitted modal set: the importer derived response snapshots at FRF "
             "peaks. They are PROVISIONAL, NOT validated fitted modes."),
}


class ExperimentalPreviewError(ValueError):
    """The file cannot be previewed (missing, LMS without its companion, unreadable, no modal or FRF data)."""


class PreviewCancelled(RuntimeError):
    """The view was closed while reading; the outcome is discarded."""


@dataclass(frozen=True)
class PreviewRecord:
    number: int
    frequency_hz: float
    classification: str
    source_text: str
    point_count: int
    measured_dof_count: int
    damping_ratio: Optional[float] = None
    # the importer's own classification of the record (dataset 55 / 2414), as recorded in the mode metadata
    record_classification: str = ""
    record_classification_reason: str = ""
    record_reference: str = ""  # "dataset 55 record 2": the wording of the importer's warnings

    @property
    def provisional(self) -> bool:
        return self.classification == viewer.FRF_PEAK_SNAPSHOT

    @property
    def ambiguous(self) -> bool:
        return self.record_classification == "ambiguous"

    @property
    def label(self) -> str:
        if self.provisional:
            return PROVISIONAL
        if self.ambiguous:  # never shown as an unambiguously confirmed fitted mode
            return (f"{AMBIGUOUS} — {self.record_reference or 'record'}, not a confirmed fitted mode: "
                    f"{self.record_classification_reason or 'see the importer warning'}")
        if self.record_classification and self.record_reference:
            return f"{self.source_text} — {self.record_reference} ({self.record_classification}, importer)"
        return self.source_text


@dataclass(frozen=True)
class PreviewSet:
    key: str
    display_name: str
    processing_name: str
    records: tuple
    excluded_residual: tuple  # labels of residual records the importer excluded
    excluded_non_modal: tuple  # labels of non-modal records the importer excluded
    warnings: tuple
    # the importer's dataset of this set (its modes in the order of ``records``), kept for the shape view only
    dataset: Any = field(default=None, compare=False, repr=False)

    @property
    def title(self) -> str:
        name = f"{self.display_name} ({self.key})" if self.key else self.display_name
        return f"{name} — {len(self.records)} record{'s' if len(self.records) != 1 else ''}"


@dataclass(frozen=True)
class ExperimentalPreview:
    selected_path: Path
    source_path: Path  # the UNV / UFF actually read (the companion of an LMS project)
    kind: str
    dataset_types: tuple
    geometry_node_count: int
    sets: tuple  # one PreviewSet per dataset-55 set; one set for dataset 2414 or FRF data
    record_classifications: tuple  # dataset 2414: (record index, classification, included, reason)
    details: tuple  # further importer facts (FRF channels, ...)


def _record(mode, dataset_metadata) -> PreviewRecord:
    classification, text = viewer.experimental_classification(mode, dataset_metadata)
    measured = getattr(mode, "measured_dofs", None)
    dofs = int(np.count_nonzero(measured)) if measured is not None else int(np.asarray(mode.vectors).size)
    damping = getattr(mode, "damping_ratio", None)
    info = dict(getattr(mode, "metadata", {}) or {})
    reference = ""
    for dataset_type in (55, 2414):
        index = info.get(f"dataset_{dataset_type}_record_index")
        if index is not None:
            reference = f"dataset {dataset_type} record {index}"
    return PreviewRecord(number=int(mode.number), frequency_hz=float(mode.frequency_hz), classification=classification,
                         source_text=text, point_count=len(mode.node_ids), measured_dof_count=dofs,
                         damping_ratio=None if damping is None else float(damping),
                         record_classification=str(info.get("record_classification") or ""),
                         record_classification_reason=str(info.get("record_classification_reason") or ""),
                         record_reference=reference)


def _set_from(dataset, key="", display_name="", processing_name="") -> PreviewSet:
    metadata = dict(dataset.metadata or {})
    return PreviewSet(key=key, display_name=display_name, processing_name=processing_name,
                      records=tuple(_record(mode, metadata) for mode in dataset.modes),
                      excluded_residual=tuple(str(x) for x in metadata.get("excluded_residual_labels") or ()),
                      excluded_non_modal=tuple(str(x) for x in metadata.get("excluded_non_modal_labels") or ()),
                      warnings=tuple(str(x) for x in metadata.get("import_warnings") or ()), dataset=dataset)


def _check(cancel_event) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise PreviewCancelled("The experimental data view was closed.")


def _unreadable(error: Exception) -> ExperimentalPreviewError:
    return ExperimentalPreviewError(f"The experimental file cannot be read: {error}")


def preview_experimental_file(path, cancel_event=None) -> ExperimentalPreview:
    """Describe the experimental data of a UNV / UFF / LMS file with the comparator's importer (read-only)."""
    selected = Path(path)
    if not selected.is_file():
        raise ExperimentalPreviewError(f"The file {selected} does not exist.")
    try:
        source = universal_reader.resolve_testlab_file(selected)
    except ValueError as error:  # an LMS project without its companion UNV / UFF
        raise ExperimentalPreviewError(str(error)) from error
    _check(cancel_event)
    try:
        modal_sets = universal_reader.discover_experimental_modal_sets(source)
    except Exception as error:  # noqa: BLE001  (pyuff raises various errors for a damaged file)
        raise _unreadable(error) from error
    loader = universal_reader.load_universal_modal_file  # the importer the analysis uses (as installed)
    sets, details, classifications = [], [], ()
    metadata = {}
    try:
        if modal_sets:
            kind = DATASET_55
            for item in modal_sets:  # each set on its own; none is chosen, nothing is merged
                _check(cancel_event)
                dataset = loader(source, modal_set=item.key)
                metadata = dict(dataset.metadata or {})
                sets.append(_set_from(dataset, item.key, item.display_name, item.processing_name))
        else:
            _check(cancel_event)
            dataset = loader(source)
            metadata = dict(dataset.metadata or {})
            source_text = str(metadata.get("mode_source") or "")
            if "dataset 58" in source_text or "FRF" in source_text:
                kind = FRF_58
                sets.append(_set_from(dataset, display_name="FRF peak-derived response snapshots"))
                if metadata.get("frf_channel_count") is not None:
                    details.append(f"FRF channels: {metadata['frf_channel_count']}")
            else:
                kind = DATASET_2414
                sets.append(_set_from(dataset, display_name="Dataset 2414 records"))
                classifications = tuple(
                    (int(item.get("record_index", -1)), str(item.get("classification", "")),
                     bool(item.get("included")), str(item.get("reason", "")))
                    for item in metadata.get("dataset_2414_record_classifications") or ())
    except PreviewCancelled:
        raise
    except Exception as error:  # noqa: BLE001
        raise _unreadable(error) from error
    _check(cancel_event)
    if metadata.get("dataset_58_role") == "diagnostic_only" or metadata.get("dataset_58_diagnostic_available"):
        details.append("Dataset 58 FRFs are present; with a fitted modal set they are diagnostic only.")
    return ExperimentalPreview(selected_path=selected, source_path=Path(source), kind=kind,
                               dataset_types=tuple(sorted(set(int(x) for x in metadata.get("dataset_types") or ()))),
                               geometry_node_count=int(metadata.get("geometry_node_count") or 0), sets=tuple(sets),
                               record_classifications=classifications, details=tuple(details))


def summary(preview: ExperimentalPreview) -> str:
    sets = len(preview.sets)
    if preview.kind == DATASET_55:
        head = f"{sets} fitted modal set{'s' if sets != 1 else ''} (dataset 55), shown separately"
    elif preview.kind == DATASET_2414:
        head = f"{len(preview.sets[0].records)} dataset-2414 record(s) loaded"
    else:
        head = f"{len(preview.sets[0].records)} FRF peak-derived record(s), {PROVISIONAL}"
    ambiguous = sum(1 for item in preview.sets for record in item.records if record.ambiguous)
    if ambiguous:
        head += f"; {ambiguous} record{'s' if ambiguous != 1 else ''} {AMBIGUOUS}"
    return head + f"; dataset types {', '.join(str(x) for x in preview.dataset_types) or 'none'}"


# ----------------------------------------------------------------------------- APP-DATA.4: one record's shape

SHAPE_COMPONENTS = viewer.COMPONENTS
COMPONENT_TEXT = viewer.COMPONENT_TEXT[viewer.EXPERIMENTAL]
_RENDER_LOCK = threading.Lock()  # one matplotlib figure at a time, as in the main window's viewer


class ShapeViewUnavailable(ValueError):
    """No spatial view of the record can be drawn; the reason is stated and nothing is created."""


@dataclass(frozen=True)
class ShapeView:
    image_path: Path
    set_title: str
    index: int  # the record's position in its set
    record: PreviewRecord
    component: str
    points_shown: int
    lines: tuple  # the caption: classification, record, what is drawn, measured components


def _measured_mask(mode) -> Optional[np.ndarray]:
    """The importer's measured-DOF mask of the record (points x X, Y, Z), or None when it recorded none."""
    measured = getattr(mode, "measured_dofs", None)
    if measured is None:
        return None
    mask = np.asarray(measured, dtype=bool)
    return mask if mask.shape == np.asarray(mode.vectors).shape else None


def _measured_text(mode, mask: Optional[np.ndarray]) -> str:
    if mask is None:
        axes = viewer.measured_axes(mode)
        return (f"Measured DOFs are not recorded by the importer; components with data: "
                f"{', '.join(a.upper() for a in axes) or 'none'}.")
    measured = [axis.upper() for axis, used in zip("xyz", mask.any(axis=0)) if used]
    missing = [axis.upper() for axis, used in zip("xyz", mask.any(axis=0)) if not used]
    text = f"Measured components (importer): {', '.join(measured) or 'none'}."
    if missing:
        text += f" Not measured: {', '.join(missing)} — not drawn as measured; no values are created."
    return text


COLLINEAR_TOLERANCE = 1.0e-6  # second singular value of the centred points, relative to the first


def _collinear(coordinates) -> bool:
    """Whether the points span no plane (the out-of-plane direction would be arbitrary)."""
    points = np.asarray(coordinates, dtype=float)
    points = points[np.all(np.isfinite(points), axis=1)]
    if len(points) < 3:
        return True
    spread = np.linalg.svd(points - points.mean(axis=0), compute_uv=False)
    return bool(spread[0] <= 0.0 or spread[1] <= COLLINEAR_TOLERANCE * spread[0])


def render_record_shape(preview_set: PreviewSet, index: int, component: str, directory,
                        cancel_event=None) -> ShapeView:
    """Draw record ``index`` of ``preview_set`` on its measured points with the main window's viewer (read-only)."""
    if component not in SHAPE_COMPONENTS:
        raise ValueError(f"unknown component {component!r}; choose one of {', '.join(SHAPE_COMPONENTS)}.")
    dataset = preview_set.dataset
    if dataset is None or not 0 <= int(index) < len(preview_set.records) or len(dataset.modes) != len(
            preview_set.records):
        raise ShapeViewUnavailable("The record is not in the loaded data of this set.")
    record, mode = preview_set.records[index], dataset.modes[index]
    if (int(mode.number), float(mode.frequency_hz)) != (record.number, record.frequency_hz):
        raise ShapeViewUnavailable("The record does not match the loaded data of this set.")
    mask = _measured_mask(mode)
    points = len(mode.node_ids)
    if component in ("x", "y", "z"):
        axis = "xyz".index(component)
        if mask is not None:
            keep = mask[:, axis]
            if not keep.any():
                raise ShapeViewUnavailable(f"{COMPONENT_TEXT[component]} is not a measured component of this record "
                                           "(the importer recorded no measured DOF in it); no view is drawn and no "
                                           "value is created.")
        elif component not in viewer.measured_axes(mode):
            raise ShapeViewUnavailable(f"{COMPONENT_TEXT[component]} holds no data in this record; no view is drawn "
                                       "and no value is created.")
        else:
            keep = np.ones(points, dtype=bool)
    else:
        keep = mask.any(axis=1) if mask is not None else np.ones(points, dtype=bool)
    # Only the record's own measured points, with their imported values: a subset, never a new value.
    shown = ModeShape(number=mode.number, frequency_hz=mode.frequency_hz, node_ids=mode.node_ids[keep],
                      coordinates=mode.coordinates[keep], vectors=np.asarray(mode.vectors)[keep],
                      damping_ratio=mode.damping_ratio, modal_mass=mode.modal_mass, metadata=dict(mode.metadata))
    available, reason = viewer.spatial_status(shown)
    if not available:
        raise ShapeViewUnavailable(f"No spatial view of this record: {reason}")
    if component == "normal" and _collinear(shown.coordinates):
        raise ShapeViewUnavailable("The drawn points lie on one line: no best-fit plane and no normal to it are "
                                   "defined, so no out-of-plane view is drawn. Choose X, Y, Z or magnitude.")
    _check(cancel_event)
    single = ModalDataset(dataset.source_name, dataset.source_path, [shown], metadata=dict(dataset.metadata or {}))
    with _RENDER_LOCK:
        path, _ = viewer.render_viewer_mode(single, viewer.EXPERIMENTAL, shown.number, component, Path(directory))
    _check(cancel_event)
    lines = (record.label,  # the row's own wording: PROVISIONAL, AMBIGUOUS (importer) or the fitted-mode source
             f"Record {index + 1} of {preview_set.title}: experimental record {record.number}, "
             f"{record.frequency_hz:.6g} Hz.",
             f"Shown: {COMPONENT_TEXT[component]} on {int(np.count_nonzero(keep))} of {points} points, at their own "
             "measured coordinates. No FE model, mapping or MAC.",
             _measured_text(mode, mask))
    return ShapeView(image_path=Path(path), set_title=preview_set.title, index=int(index), record=record,
                     component=component, points_shown=int(np.count_nonzero(keep)), lines=lines)
