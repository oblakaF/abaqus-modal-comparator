"""Modal fitting provider boundary (Auto-ID M1.3.1; D-021, D-023, D-024, D-026).

FRF-to-modal fitting is a separate experimental preparation stage (D-023):

    FrfInput  ->  ModalFittingProvider.fit  ->  ModalFittingOutput  ->  validated output

This module defines only that boundary: the FRF input contract, the provider identity
and protocol, the output contract, a provider registry, and the validation every
provider output must pass.  It contains no fitting algorithm, no pole selection and
no dataset-58 processing.

A validated output is **not yet production identification input**.  Per D-023 it
must still be pinned as a fixture and pass the M1.2 production path, and its
``mode_source`` label must have been admitted to the M1.1 policy; until then M1.1
classifies it as ``unknown``.  The classification is recorded on the validated
output for transparency.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import re
from typing import Any, Mapping, Protocol, runtime_checkable

import numpy as np

from modal_core import ModalDataset

from .modal_input_source import (
    PEAK_DERIVED_MODE_SOURCES,
    READER_CURVE_FITTED_MODE_SOURCES,
    ModalInputSourceClassification,
    classify_modal_dataset,
)


_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
COHERENCE_STATUSES = ("computed", "unavailable", "parse_error")
QC_STATUSES = ("NOT_EVALUATED", "PASSED", "FLAGGED", "FAILED")
REQUIRED_PROVENANCE_KEYS = (
    "provider_name",
    "provider_version",
    "frf_source_sha256",
    "frf_content_hash",
    "configuration",
    "configuration_hash",
    "frequency_band_hz",
    "pole_selection",
)


class ModalFittingRefusal(Exception):
    """A provider, its identity or its output violates the fitting boundary contract.

    Not a ValueError/RuntimeError, so generic fallback handlers never swallow it.
    """

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field


class ProviderKind(str, Enum):
    EXTERNAL = "external"
    INTERNAL = "internal"


class PoleSelection(str, Enum):
    RULE_BASED = "rule_based"
    MANUAL_REVIEW = "manual_review"  # live manual selection: research/review workflows only (D-026)
    EXTERNAL_FROZEN_SELECTION = "external_frozen_selection"  # frozen, pinned external selection (D-026)


# D-026: a frozen external selection must pin its source file, modal set and provenance.
EXTERNAL_FROZEN_PROVENANCE_KEYS = ("fixture_id", "modal_set", "source_file")


class FittingWorkflow(str, Enum):
    PRODUCTION = "production"
    RESEARCH = "research"


def _require(condition: bool, field: str, message: str) -> None:
    if not condition:
        raise ModalFittingRefusal(field, message)


def canonical_hash(value: object) -> str:
    """SHA-256 of canonical JSON (sorted keys, no whitespace)."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FrfInput:
    """FRF matrix handed to a provider: H[response, reference, frequency]."""

    frequency_hz: np.ndarray
    h: np.ndarray
    response_keys: tuple[tuple[int, int], ...]
    reference_keys: tuple[tuple[int, int], ...]
    quantity: str
    coherence_status: str
    source_sha256: str
    coherence: np.ndarray | None = None

    def __post_init__(self) -> None:
        frequency = np.asarray(self.frequency_hz, dtype=float)
        h = np.asarray(self.h, dtype=complex)
        _require(frequency.ndim == 1 and frequency.size >= 2 and np.all(np.isfinite(frequency)),
                 "frf.frequency_hz", "must be a finite 1-D axis with at least two lines.")
        _require(bool(np.all(np.diff(frequency) > 0.0)), "frf.frequency_hz", "must be strictly increasing.")
        _require(h.shape == (len(self.response_keys), len(self.reference_keys), frequency.size),
                 "frf.h", "must have shape (responses, references, frequency lines).")
        _require(len(self.response_keys) > 0 and len(self.reference_keys) > 0, "frf.keys",
                 "at least one response and one reference are required.")
        _require(len(set(self.response_keys)) == len(self.response_keys)
                 and len(set(self.reference_keys)) == len(self.reference_keys), "frf.keys", "keys must be unique.")
        _require(bool(np.all(np.isfinite(h.real) & np.isfinite(h.imag))), "frf.h", "must be finite.")
        _require(isinstance(self.quantity, str) and bool(self.quantity.strip()), "frf.quantity", "must be declared.")
        _require(self.coherence_status in COHERENCE_STATUSES, "frf.coherence_status",
                 f"must be one of {COHERENCE_STATUSES}.")
        _require((self.coherence is not None) == (self.coherence_status == "computed"), "frf.coherence",
                 "coherence values are present exactly when coherence_status is 'computed'.")
        _require(isinstance(self.source_sha256, str) and bool(_HASH_PATTERN.match(self.source_sha256)),
                 "frf.source_sha256", "must be a 64-character lowercase hex SHA-256.")
        object.__setattr__(self, "frequency_hz", frequency)
        object.__setattr__(self, "h", h)
        if self.coherence is not None:
            object.__setattr__(self, "coherence", np.asarray(self.coherence, dtype=float))

    @property
    def content_hash(self) -> str:
        digest = hashlib.sha256()
        for part in (self.frequency_hz.astype(">f8"), self.h.astype(">c16")):
            digest.update(np.ascontiguousarray(part).tobytes())
        digest.update(json.dumps([list(map(list, self.response_keys)), list(map(list, self.reference_keys)),
                                  self.quantity, self.coherence_status, self.source_sha256]).encode("utf-8"))
        if self.coherence is not None:
            digest.update(np.ascontiguousarray(self.coherence.astype(">f8")).tobytes())
        return digest.hexdigest()


@dataclass(frozen=True)
class ModalFittingProviderIdentity:
    name: str
    version: str
    kind: ProviderKind
    mode_source: str  # exact label the provider writes on every fitted mode

    def __post_init__(self) -> None:
        _require(isinstance(self.name, str) and bool(_NAME_PATTERN.match(self.name)), "provider.name",
                 "must be a lowercase identifier.")
        _require(isinstance(self.version, str) and bool(self.version.strip()), "provider.version", "must be declared.")
        _require(isinstance(self.kind, ProviderKind), "provider.kind", "must be a ProviderKind.")
        _require(isinstance(self.mode_source, str) and bool(self.mode_source.strip()), "provider.mode_source",
                 "must be declared.")
        # A provider never borrows a reader's curve-fitted label or a peak-derived label.
        _require(self.mode_source not in READER_CURVE_FITTED_MODE_SOURCES | PEAK_DERIVED_MODE_SOURCES,
                 "provider.mode_source", "must be the provider's own label, not a reader or peak-derived label.")

    @property
    def key(self) -> tuple[str, str]:
        return self.name, self.version


@runtime_checkable
class ModalFittingProvider(Protocol):
    """Replaceable modal fitting stage (D-021); external or internal (D-023)."""

    identity: ModalFittingProviderIdentity

    def fit(self, frf: FrfInput, configuration: Mapping[str, Any]) -> "ModalFittingOutput": ...


@dataclass(frozen=True)
class ModalFittingOutput:
    dataset: ModalDataset
    provider: ModalFittingProviderIdentity
    provenance: Mapping[str, Any]
    qc_summary: Mapping[str, Any]  # placeholder until M1.4: at least {"status": <QC_STATUSES>}
    confidence: Mapping[int, Mapping[str, float | None]]  # per mode: frequency_sd_hz, damping_sd


@dataclass(frozen=True)
class ValidatedModalFittingOutput:
    output: ModalFittingOutput
    workflow: FittingWorkflow
    frf_content_hash: str
    configuration_hash: str
    source_classification: ModalInputSourceClassification


class ModalFittingProviderRegistry:
    """Known providers by (name, version); no global state.  Empty means no provider is admitted."""

    def __init__(self, identities: tuple[ModalFittingProviderIdentity, ...] = ()) -> None:
        self._identities: dict[tuple[str, str], ModalFittingProviderIdentity] = {}
        for identity in identities:
            self.register(identity)

    def register(self, identity: ModalFittingProviderIdentity) -> None:
        _require(isinstance(identity, ModalFittingProviderIdentity), "provider", "must be a provider identity.")
        _require(identity.key not in self._identities, "provider", f"{identity.key} is already registered.")
        _require(all(item.mode_source != identity.mode_source for item in self._identities.values()),
                 "provider.mode_source", "is already used by another registered provider.")
        self._identities[identity.key] = identity

    def require(self, identity: object) -> ModalFittingProviderIdentity:
        _require(isinstance(identity, ModalFittingProviderIdentity), "provider", "must be a provider identity.")
        registered = self._identities.get(identity.key)
        _require(registered is not None, "provider", f"unknown provider {identity.key}.")
        _require(registered == identity, "provider", f"{identity.key} differs from its registered identity.")
        return registered


def _check_dataset(dataset: object, provider: ModalFittingProviderIdentity) -> None:
    _require(isinstance(dataset, ModalDataset), "dataset", "must be a ModalDataset.")
    modes = dataset.sorted_modes()
    _require(bool(modes), "dataset", "contains no modes.")
    numbers = [mode.number for mode in modes]
    _require(len(set(numbers)) == len(numbers), "dataset", "mode numbers must be unique.")
    node_ids = list(modes[0].node_ids)
    for mode in modes:
        _require(math.isfinite(mode.frequency_hz) and mode.frequency_hz > 0.0, "dataset",
                 f"mode {mode.number} frequency must be finite and positive.")
        _require(mode.damping_ratio is not None and math.isfinite(mode.damping_ratio) and mode.damping_ratio >= 0.0,
                 "dataset", f"mode {mode.number} must carry a finite, non-negative damping ratio.")
        vectors = np.asarray(mode.vectors)
        _require(vectors.shape == (len(node_ids), 3)
                 and bool(np.all(np.isfinite(vectors.real) & np.isfinite(vectors.imag))),
                 "dataset", f"mode {mode.number} shape must be finite with one row per measurement point.")
        _require(list(mode.node_ids) == node_ids, "dataset", "all modes must share one measurement point list.")
        _require(mode.metadata.get("mode_source") == provider.mode_source, "dataset.mode_source",
                 f"mode {mode.number} is not labelled with the provider's mode_source.")
    _require(dataset.metadata.get("mode_source") == provider.mode_source, "dataset.mode_source",
             "the dataset is not labelled with the provider's mode_source.")


def validate_fitting_output(
    output: object,
    *,
    frf: FrfInput,
    configuration: Mapping[str, Any],
    registry: ModalFittingProviderRegistry,
    workflow: FittingWorkflow,
) -> ValidatedModalFittingOutput:
    """Return the validated output, or raise ``ModalFittingRefusal`` naming the violated field."""

    _require(isinstance(output, ModalFittingOutput), "output", "must be a ModalFittingOutput.")
    _require(isinstance(workflow, FittingWorkflow), "workflow", "must be a FittingWorkflow.")
    provider = registry.require(output.provider)
    _check_dataset(output.dataset, provider)

    provenance = output.provenance
    _require(isinstance(provenance, Mapping), "provenance", "must be a mapping.")
    missing = [key for key in REQUIRED_PROVENANCE_KEYS if provenance.get(key) in (None, "", {}, [], ())]
    _require(not missing, "provenance", f"missing {missing}.")
    _require(provenance["provider_name"] == provider.name and provenance["provider_version"] == provider.version,
             "provenance.provider", "does not name the provider that produced the output.")
    _require(provenance["frf_source_sha256"] == frf.source_sha256, "provenance.frf_source_sha256",
             "does not match the FRF input source.")
    frf_hash = frf.content_hash
    _require(provenance["frf_content_hash"] == frf_hash, "provenance.frf_content_hash",
             "does not match the FRF input content.")
    configuration_hash = canonical_hash(dict(configuration))
    _require(canonical_hash(dict(provenance["configuration"])) == configuration_hash
             and provenance["configuration_hash"] == configuration_hash,
             "provenance.configuration", "does not match the configuration the provider was given.")
    band = provenance["frequency_band_hz"]
    _require(isinstance(band, (list, tuple)) and len(band) == 2 and all(isinstance(v, (int, float)) for v in band)
             and frf.frequency_hz[0] <= band[0] < band[1] <= frf.frequency_hz[-1],
             "provenance.frequency_band_hz", "must be a [low, high] band inside the FRF axis.")
    try:
        selection = PoleSelection(provenance["pole_selection"])
    except ValueError:
        raise ModalFittingRefusal("provenance.pole_selection", f"must be one of {[s.value for s in PoleSelection]}.")
    # D-026: live manual mode selection only in research/review workflows.
    _require(not (workflow is FittingWorkflow.PRODUCTION and selection is PoleSelection.MANUAL_REVIEW),
             "provenance.pole_selection", "live manual mode selection is not allowed in a production workflow (D-026).")
    if selection is PoleSelection.EXTERNAL_FROZEN_SELECTION:
        # D-026: only an external provider can carry a frozen external selection, and only with
        # its source file, modal set and provenance pinned.
        _require(provider.kind is ProviderKind.EXTERNAL, "provenance.pole_selection",
                 "a frozen external selection requires an external provider (D-026).")
        absent = [key for key in EXTERNAL_FROZEN_PROVENANCE_KEYS if provenance.get(key) in (None, "", {}, [], ())]
        _require(not absent, "provenance", f"frozen external selection is missing {absent} (D-026).")
        source_file = provenance["source_file"]
        _require(isinstance(source_file, Mapping) and isinstance(source_file.get("sha256"), str)
                 and bool(_HASH_PATTERN.match(source_file["sha256"])) and bool(source_file.get("file_name")),
                 "provenance.source_file", "must pin the source file name and SHA-256 (D-026).")

    qc = output.qc_summary
    _require(isinstance(qc, Mapping) and qc.get("status") in QC_STATUSES, "qc_summary",
             f"must declare a status in {QC_STATUSES}.")

    confidence = output.confidence
    numbers = {mode.number for mode in output.dataset.modes}
    _require(isinstance(confidence, Mapping) and set(confidence) == numbers, "confidence",
             "must have one entry per fitted mode.")
    for number, entry in confidence.items():
        _require(isinstance(entry, Mapping) and {"frequency_sd_hz", "damping_sd"} <= set(entry), "confidence",
                 f"mode {number} must declare frequency_sd_hz and damping_sd (None while not evaluated).")
        for key in ("frequency_sd_hz", "damping_sd"):
            value = entry[key]
            _require(value is None or (isinstance(value, (int, float)) and math.isfinite(value) and value >= 0.0),
                     "confidence", f"mode {number} {key} must be None or finite and non-negative.")

    return ValidatedModalFittingOutput(
        output=output,
        workflow=workflow,
        frf_content_hash=frf_hash,
        configuration_hash=configuration_hash,
        source_classification=classify_modal_dataset(output.dataset),
    )


def run_modal_fitting(
    provider: object,
    frf: FrfInput,
    configuration: Mapping[str, Any],
    *,
    registry: ModalFittingProviderRegistry,
    workflow: FittingWorkflow,
) -> ValidatedModalFittingOutput:
    """Call a registered provider and validate its output; refuse anything else."""

    _require(isinstance(provider, ModalFittingProvider), "provider", "does not implement ModalFittingProvider.")
    registry.require(provider.identity)
    _require(isinstance(frf, FrfInput), "frf", "must be an FrfInput.")
    output = provider.fit(frf, configuration)
    _require(isinstance(output, ModalFittingOutput) and output.provider == provider.identity, "output.provider",
             "the output does not come from the called provider.")
    return validate_fitting_output(output, frf=frf, configuration=configuration, registry=registry,
                                   workflow=workflow)
