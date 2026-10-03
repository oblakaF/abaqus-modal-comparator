"""Identification input-source policy for experimental modes (Auto-ID M1.1).

SPEC §4 / DECISIONS D-002 / AUDIT K1: production identification accepts only
curve-fitted experimental modes (Testlab PolyMAX dataset 55, or dataset 2414).
Peak-derived modes (FRF peak picking, response-matrix SVD candidates) stay
available for viewing, diagnostics and QC, but never enter identification.

Classification uses only the exact source labels and dataset types the readers
emit.  A label this module does not know is ``unknown``, never guessed from a
substring, and ``unknown`` is refused for identification like ``peak_derived``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence


class ModalInputSource(str, Enum):
    CURVE_FITTED = "curve_fitted"
    PEAK_DERIVED = "peak_derived"
    UNKNOWN = "unknown"


# Exact ``mode_source`` labels written by the readers (per mode and per dataset).
CURVE_FITTED_MODE_SOURCES = frozenset(
    {
        "curve-fitted modal dataset",  # universal_reader / universal_hardening, datasets 55 and 2414
        "curve-fitted dataset 55",  # universal_reader, selected dataset-55 modal set
    }
)
PEAK_DERIVED_MODE_SOURCES = frozenset(
    {
        "FRF peak-derived experimental shape",  # dataset 58 peak picking, per mode
        "dataset 58 FRF peak extraction",  # dataset 58 peak picking, per dataset
        "local response-matrix SVD close-mode candidate",  # cmif_separation
    }
)
CURVE_FITTED_DATASET_TYPES = frozenset({55, 2414})
PEAK_DERIVED_DATASET_TYPES = frozenset({58})


class IdentificationInputSourceRefusal(Exception):
    """Experimental modes are not admissible identification input.

    Deliberately not a ValueError or RuntimeError, so generic failure and
    fallback handlers never swallow it.
    """

    def __init__(self, source: ModalInputSource, message: str) -> None:
        super().__init__(message)
        self.source = source


@dataclass(frozen=True)
class ModalInputSourceClassification:
    source: ModalInputSource
    reason: str
    # (mode number, per-mode class, recorded mode_source label or None)
    modes: tuple[tuple[int, ModalInputSource, str | None], ...]


def _dataset_type(metadata: Mapping[str, Any]) -> int | None:
    value = metadata.get("dataset_type")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def classify_mode_source(metadata: Mapping[str, Any] | None) -> ModalInputSource:
    """Classify one mode (or a dataset) from its ``mode_source`` label and dataset type."""

    metadata = metadata or {}
    label = metadata.get("mode_source")
    dataset_type = _dataset_type(metadata)
    if label is None:
        if dataset_type in CURVE_FITTED_DATASET_TYPES:
            return ModalInputSource.CURVE_FITTED
        if dataset_type in PEAK_DERIVED_DATASET_TYPES:
            return ModalInputSource.PEAK_DERIVED
        return ModalInputSource.UNKNOWN
    label = str(label)
    if label in PEAK_DERIVED_MODE_SOURCES or dataset_type in PEAK_DERIVED_DATASET_TYPES:
        return ModalInputSource.PEAK_DERIVED
    if label in CURVE_FITTED_MODE_SOURCES and dataset_type in (None, *CURVE_FITTED_DATASET_TYPES):
        return ModalInputSource.CURVE_FITTED
    return ModalInputSource.UNKNOWN


def classify_modal_dataset(dataset: object) -> ModalInputSourceClassification:
    """Classify an experimental ``ModalDataset``; every mode must be curve-fitted."""

    modes: Sequence[Any] = list(getattr(dataset, "modes", None) or [])
    per_mode = tuple(
        (
            int(getattr(mode, "number", index + 1)),
            classify_mode_source(getattr(mode, "metadata", None)),
            (getattr(mode, "metadata", None) or {}).get("mode_source"),
        )
        for index, mode in enumerate(modes)
    )
    dataset_metadata = getattr(dataset, "metadata", None) or {}
    dataset_label = dataset_metadata.get("mode_source")
    dataset_class = None if dataset_label is None else classify_mode_source({"mode_source": dataset_label})

    if not per_mode:
        return ModalInputSourceClassification(
            ModalInputSource.UNKNOWN, "the experimental dataset has no modes", per_mode
        )
    peak = [number for number, kind, _ in per_mode if kind is ModalInputSource.PEAK_DERIVED]
    if peak or dataset_class is ModalInputSource.PEAK_DERIVED:
        detail = f"modes {peak}" if peak else f"dataset source {dataset_label!r}"
        return ModalInputSourceClassification(
            ModalInputSource.PEAK_DERIVED, f"peak-derived experimental modes ({detail})", per_mode
        )
    unknown = [(number, label) for number, kind, label in per_mode if kind is ModalInputSource.UNKNOWN]
    if unknown or dataset_class is ModalInputSource.UNKNOWN:
        detail = f"modes {unknown}" if unknown else f"dataset source {dataset_label!r}"
        return ModalInputSourceClassification(
            ModalInputSource.UNKNOWN, f"experimental mode source not recognised as curve-fitted ({detail})", per_mode
        )
    return ModalInputSourceClassification(
        ModalInputSource.CURVE_FITTED, "all experimental modes are curve-fitted", per_mode
    )


def require_identification_input(dataset: object) -> ModalInputSourceClassification:
    """Return the classification if the dataset is admissible identification input; else refuse."""

    classification = classify_modal_dataset(dataset)
    if classification.source is ModalInputSource.PEAK_DERIVED:
        raise IdentificationInputSourceRefusal(
            classification.source,
            "Peak-derived experimental modes are refused as identification input "
            f"(SPEC §4, D-002, audit K1): {classification.reason}. Use a curve-fitted "
            "modal set (Testlab PolyMAX dataset 55/2414); peak-derived modes remain "
            "available for viewing, diagnostics and QC only.",
        )
    if classification.source is ModalInputSource.UNKNOWN:
        raise IdentificationInputSourceRefusal(
            classification.source,
            "Experimental mode source cannot be verified as curve-fitted, so it is "
            f"refused as identification input: {classification.reason}.",
        )
    return classification
