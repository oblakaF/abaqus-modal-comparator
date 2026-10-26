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
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

import universal_reader
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
                      warnings=tuple(str(x) for x in metadata.get("import_warnings") or ()))


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
