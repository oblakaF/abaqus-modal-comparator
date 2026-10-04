"""Experimental QC subsystem (Auto-ID M1.4).

Evaluates a validated provider output (M1.3) against its pinned fixture (M0.2/M1.2)
and the FRF data it was prepared from, and returns an ``ExperimentalQCReport``.
The modal dataset is only read: QC never modifies, repairs, reorders or deletes modes.

Checks (hard = may FAIL and refuse; diagnostic = PASS / WARNING / NOT_AVAILABLE):

- provenance            (hard)        provider admission, provenance keys and hashes;
- measurement_contract  (hard)        registration, points, ordering, measured DOFs;
- frf_completeness      (hard for source identity; completeness issues are warnings);
- coherence_quality     (diagnostic)  SPEC §6 S1 flag: coherence at resonance < 0.9;
- frequency_resolution  (diagnostic)  SPEC §6 S1 flag: unresolved resonance 2*zeta*f < 3*df;
                                      SPEC §12.4 trigger: close modes |df|/f < 3 %;
- modal_confidence      (diagnostic)  uncertainty availability; phase complexity (metric
                                      only, the SPEC gives no limit); SPEC §6 S1 flag:
                                      experimental AutoMAC off-diagonal > 0.5;
- suspension_threshold  (diagnostic)  SPEC §6 S1 / §19 item 5: modes below a *trusted*
                                      physical suspension_max_hz; NOT_AVAILABLE without one.

No threshold other than these SPEC flag rules is applied.  The suspension threshold is
never guessed: it is accepted only as a ``TrustedSuspensionThreshold`` (M2 passport /
acquisition record).  Which modes may enter material identification is a separate
``ExperimentalModeEligibility``; the provider dataset itself is never changed.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from domain.experiment_fixture import (
    ExperimentFixture,
    ExperimentFixtureManifest,
    fixture_roots_from_environment,
    load_experiment_fixture_manifest,
)
from domain.experimental_qc import (
    QC_POLICY_VERSION,
    ExperimentalModeEligibility,
    ExperimentalQCCheck,
    ExperimentalQCMetric,
    ExperimentalQCRefusal,
    ExperimentalQCReport,
    ExperimentalQCStatus,
    QCWarning,
    TrustedSuspensionThreshold,
)
from domain.modal_fitting import (
    EXTERNAL_FROZEN_PROVENANCE_KEYS,
    REQUIRED_PROVENANCE_KEYS,
    FrfInput,
    ModalFittingProviderRegistry,
    ModalFittingRefusal,
    PoleSelection,
    ValidatedModalFittingOutput,
    canonical_hash,
)
from domain.registration import REGISTRATION_DOF_COMPONENTS, FrozenRegistration
from modal_core import ModalDataset, modal_assurance_criterion
from reviewed_core import experimental_measurement_masks

from .external_polymax_provider import (
    admitted_provider_registry,
    prepare_external_polymax_modal_dataset,
    prepare_frf_input,
)
from .production_modal_input import FIXTURE_MANIFEST_PATH, REPO_ROOT


PROVENANCE = "provenance"
MEASUREMENT_CONTRACT = "measurement_contract"
FRF_COMPLETENESS = "frf_completeness"
COHERENCE_QUALITY = "coherence_quality"
FREQUENCY_RESOLUTION = "frequency_resolution"
MODAL_CONFIDENCE = "modal_confidence"
SUSPENSION_THRESHOLD = "suspension_threshold"

# Flag rules taken from the SPEC; diagnostic only (warnings), never refusals.
SPEC_COHERENCE_FLAG = 0.9  # SPEC §6 S1: coherence at resonance < 0.9
SPEC_UNRESOLVED_FACTOR = 3.0  # SPEC §6 S1: unresolved resonance 2*zeta*f < 3*df
SPEC_CLUSTER_TRIGGER = 0.03  # SPEC §12.4: |df|/f < 3 % triggers cluster examination
SPEC_AUTOMAC_FLAG = 0.5  # SPEC §6 S1: AutoMAC off-diagonal > 0.5 -> indistinguishable by grid
_DIRECTIONS = {"U1": 1, "U2": 2, "U3": 3}


def _status(warnings: list, failures: list | None = None) -> ExperimentalQCStatus:
    if failures:
        return ExperimentalQCStatus.FAIL
    return ExperimentalQCStatus.WARNING if warnings else ExperimentalQCStatus.PASS


def _nodes(mode) -> list:
    return [item.item() if isinstance(item, np.generic) else item for item in np.asarray(mode.node_ids, dtype=object)]


def _load_registration(fixture: ExperimentFixture, repo_root: Path) -> FrozenRegistration | None:
    try:
        with open(Path(repo_root) / fixture.registration.path, encoding="utf-8") as handle:
            return FrozenRegistration.from_dict(json.load(handle))
    except (OSError, TypeError, ValueError):
        return None


def _provenance_check(validated, frf, fixture, registry) -> ExperimentalQCCheck:
    output, failures = validated.output, []
    provenance = output.provenance if isinstance(output.provenance, Mapping) else {}
    try:
        provider = registry.require(output.provider)
    except ModalFittingRefusal as exc:
        provider = None
        failures.append(f"provider not admitted ({exc})")
    required = list(REQUIRED_PROVENANCE_KEYS)
    if provenance.get("pole_selection") == PoleSelection.EXTERNAL_FROZEN_SELECTION.value:
        required += list(EXTERNAL_FROZEN_PROVENANCE_KEYS)
    missing = [key for key in required if provenance.get(key) in (None, "", {}, [], ())]
    if missing:
        failures.append(f"missing provenance {missing}")
    source = fixture.experimental_source
    expectations = (
        ("fixture_id", provenance.get("fixture_id"), fixture.fixture_id),
        ("frf_source_sha256", provenance.get("frf_source_sha256"), source.sha256),
        ("frf input source", frf.source_sha256, source.sha256),
        ("frf_content_hash", provenance.get("frf_content_hash"), frf.content_hash),
        ("validated frf_content_hash", validated.frf_content_hash, frf.content_hash),
        ("configuration_hash", provenance.get("configuration_hash"),
         canonical_hash(dict(provenance.get("configuration") or {}))),
        ("validated configuration_hash", validated.configuration_hash, provenance.get("configuration_hash")),
        ("source_file sha256", (provenance.get("source_file") or {}).get("sha256"), source.sha256),
        ("registration_hash", provenance.get("registration_hash"), fixture.registration.registration_hash),
        ("dataset mode_source", output.dataset.metadata.get("mode_source"),
         None if provider is None else provider.mode_source),
    )
    for name, actual, expected in expectations:
        if actual != expected:
            failures.append(f"{name} {actual!r} != {expected!r}")
    metrics = (
        ExperimentalQCMetric("provider", f"{output.provider.name}/{output.provider.version}"),
        ExperimentalQCMetric("pole_selection", provenance.get("pole_selection")),
        ExperimentalQCMetric("provenance_hash", canonical_hash(_jsonable(provenance))),
    )
    return ExperimentalQCCheck(PROVENANCE, _status([], failures), True,
                               "provenance intact" if not failures else "broken provenance", metrics,
                               failures=tuple(failures))


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (np.generic,)):
        return value.item()
    return value


def _contract_check(dataset: ModalDataset, fixture: ExperimentFixture, repo_root: Path) -> ExperimentalQCCheck:
    failures = []
    registration = _load_registration(fixture, repo_root)
    if registration is None:
        failures.append("FrozenRegistration cannot be restored")
    elif registration.registration_hash != fixture.registration.registration_hash:
        failures.append("registration hash differs from the fixture")
    modes = dataset.sorted_modes()
    nodes = _nodes(modes[0]) if modes else []
    if len(modes) != fixture.modal_set.mode_count:
        failures.append(f"{len(modes)} modes, fixture pins {fixture.modal_set.mode_count}")
    if dataset.metadata.get("modal_set_key") != fixture.modal_set.name:
        failures.append(f"modal set {dataset.metadata.get('modal_set_key')!r} != {fixture.modal_set.name!r}")
    if any(_nodes(mode) != nodes for mode in modes):
        failures.append("modes do not share one point list")
    if len(nodes) != fixture.modal_set.measurement_point_count:
        failures.append(f"{len(nodes)} points, fixture pins {fixture.modal_set.measurement_point_count}")
    if registration is not None and modes:
        if nodes != list(registration.experimental_node_ids):
            failures.append("point ordering differs from the frozen registration")
        frozen = np.asarray(registration.measured_dof_contract, dtype=bool)
        contract = tuple(name for name, flag in zip(REGISTRATION_DOF_COMPONENTS, frozen.all(axis=0)) if flag)
        if contract != fixture.modal_set.measured_dofs:
            failures.append(f"frozen contract {contract} != fixture {fixture.modal_set.measured_dofs}")
        for mode, mask in zip(modes, experimental_measurement_masks(modes, modes[0].node_ids)):
            if np.asarray(mask, dtype=bool).shape != frozen.shape or not np.array_equal(mask, frozen):
                failures.append(f"mode {mode.number} measured DOFs differ from the frozen contract")
    for mode in modes:
        values = np.asarray(mode.vectors)
        if not np.all(np.isfinite(values.real) & np.isfinite(values.imag)):
            failures.append(f"mode {mode.number} shape has non-finite values")
    metrics = (
        ExperimentalQCMetric("mode_count", len(modes)),
        ExperimentalQCMetric("measurement_point_count", len(nodes)),
        ExperimentalQCMetric("measured_dofs", ",".join(fixture.modal_set.measured_dofs)),
    )
    return ExperimentalQCCheck(MEASUREMENT_CONTRACT, _status([], failures), True,
                               "measurement contract holds" if not failures else "invalid measurement contract",
                               metrics, failures=tuple(failures))


def _frf_check(frf: FrfInput, dataset: ModalDataset, fixture: ExperimentFixture) -> ExperimentalQCCheck:
    failures, warnings = [], []
    if frf.source_sha256 != fixture.experimental_source.sha256:
        failures.append("FRF source is not the pinned fixture export")
    modes = dataset.sorted_modes()
    points = _nodes(modes[0]) if modes else []
    expected = {(int(point), _DIRECTIONS[dof]) for point in points for dof in fixture.modal_set.measured_dofs}
    present = set(frf.response_keys)
    missing = sorted(expected - present)
    dead = [key for key, row in zip(frf.response_keys, frf.h) if not np.any(np.abs(row) > 0.0)]
    if missing:
        warnings.append(QCWarning("FRF_CHANNELS_MISSING", f"{len(missing)} measured point/DOF channels have no FRF",
                                  FRF_COMPLETENESS))
    if dead:
        warnings.append(QCWarning("FRF_CHANNELS_EMPTY", f"{len(dead)} FRF channels are identically zero",
                                  FRF_COMPLETENESS))
    frf_points = {node for node, _ in frf.response_keys}
    if len(frf_points) != fixture.modal_set.measurement_point_count:
        warnings.append(QCWarning("FRF_POINT_COUNT", f"FRF covers {len(frf_points)} points, fixture pins "
                                  f"{fixture.modal_set.measurement_point_count}", FRF_COMPLETENESS))
    metrics = (
        ExperimentalQCMetric("frf_response_channels", len(frf.response_keys)),
        ExperimentalQCMetric("frf_reference_channels", len(frf.reference_keys)),
        ExperimentalQCMetric("frf_points", len(frf_points)),
        ExperimentalQCMetric("frf_missing_channels", len(missing)),
        ExperimentalQCMetric("frf_extra_channels", len(present - expected)),
        ExperimentalQCMetric("frf_empty_channels", len(dead)),
        ExperimentalQCMetric("frf_frequency_lines", int(frf.frequency_hz.size)),
        ExperimentalQCMetric("frf_band_low", float(frf.frequency_hz[0]), "Hz"),
        ExperimentalQCMetric("frf_band_high", float(frf.frequency_hz[-1]), "Hz"),
        ExperimentalQCMetric("frf_quantity", frf.quantity),
    )
    status = _status(warnings, failures)
    summary = "FRF source identity broken" if failures else ("FRF complete" if not warnings else "FRF incomplete")
    return ExperimentalQCCheck(FRF_COMPLETENESS, status, True, summary, metrics, tuple(warnings), tuple(failures))


def _coherence_check(frf: FrfInput, dataset: ModalDataset) -> ExperimentalQCCheck:
    modes = dataset.sorted_modes()
    if frf.coherence is None:
        metrics = tuple(ExperimentalQCMetric("coherence_at_resonance", None, mode=mode.number,
                                             note=f"coherence {frf.coherence_status}") for mode in modes)
        warning = QCWarning("COHERENCE_NOT_AVAILABLE",
                            f"coherence is {frf.coherence_status}; coherence at resonance cannot be evaluated",
                            COHERENCE_QUALITY, rule="SPEC §6 S1")
        return ExperimentalQCCheck(COHERENCE_QUALITY, ExperimentalQCStatus.NOT_AVAILABLE, False,
                                   "coherence not available", metrics, (warning,))
    coherence = np.asarray(frf.coherence, dtype=float)
    if coherence.ndim > 1:
        coherence = coherence.reshape(-1, coherence.shape[-1]).mean(axis=0)
    metrics, low = [], []
    for mode in modes:
        inside = frf.frequency_hz[0] <= mode.frequency_hz <= frf.frequency_hz[-1]
        value = float(coherence[int(np.argmin(np.abs(frf.frequency_hz - mode.frequency_hz)))]) if inside else None
        metrics.append(ExperimentalQCMetric("coherence_at_resonance", value, mode=mode.number,
                                            note="" if inside else "mode outside FRF band"))
        if value is not None and value < SPEC_COHERENCE_FLAG:
            low.append(mode.number)
    warnings = [QCWarning("LOW_COHERENCE_AT_RESONANCE", f"coherence at resonance < {SPEC_COHERENCE_FLAG}",
                          COHERENCE_QUALITY, tuple(low), "SPEC §6 S1")] if low else []
    available = any(metric.available for metric in metrics)
    status = _status(warnings) if available else ExperimentalQCStatus.NOT_AVAILABLE
    return ExperimentalQCCheck(COHERENCE_QUALITY, status, False,
                               f"coherence evaluated; {len(low)} mode(s) flagged", tuple(metrics), tuple(warnings))


def _resolution_check(frf: FrfInput, dataset: ModalDataset) -> ExperimentalQCCheck:
    spacing = np.diff(frf.frequency_hz)
    resolution = float(np.median(spacing))
    modes = dataset.sorted_modes()
    metrics = [
        ExperimentalQCMetric("frequency_resolution", resolution, "Hz"),
        ExperimentalQCMetric("frequency_spacing_nonuniformity", float((spacing.max() - spacing.min()) / resolution)),
    ]
    unresolved, undamped, bandwidths = [], [], {}
    for mode in modes:
        zeta = mode.damping_ratio
        if zeta is None or not math.isfinite(zeta):
            undamped.append(mode.number)
            metrics.append(ExperimentalQCMetric("half_power_bandwidth", None, "Hz", mode.number, "damping not available"))
            continue
        bandwidth = 2.0 * zeta * mode.frequency_hz
        bandwidths[mode.number] = bandwidth
        metrics.append(ExperimentalQCMetric("half_power_bandwidth", bandwidth, "Hz", mode.number))
        metrics.append(ExperimentalQCMetric("bandwidth_in_lines", bandwidth / resolution, "lines", mode.number))
        if bandwidth < SPEC_UNRESOLVED_FACTOR * resolution:
            unresolved.append(mode.number)
    close = []
    for first, second in zip(modes, modes[1:]):
        gap = second.frequency_hz - first.frequency_hz
        centre = 0.5 * (first.frequency_hz + second.frequency_hz)
        relative = gap / centre
        pair = f"{first.number}-{second.number}"
        metrics.append(ExperimentalQCMetric("adjacent_mode_gap", gap, "Hz", note=f"modes {pair}"))
        metrics.append(ExperimentalQCMetric("adjacent_mode_gap_relative", relative, note=f"modes {pair}"))
        metrics.append(ExperimentalQCMetric("adjacent_mode_gap_in_lines", gap / resolution, "lines", note=f"modes {pair}"))
        if first.number in bandwidths and second.number in bandwidths and gap > 0.0:
            overlap = 0.5 * (bandwidths[first.number] + bandwidths[second.number]) / gap
            metrics.append(ExperimentalQCMetric("modal_overlap", overlap, note=f"modes {pair}"))
        if relative < SPEC_CLUSTER_TRIGGER:
            close.append((first.number, second.number))
    warnings = []
    if unresolved:
        warnings.append(QCWarning("UNRESOLVED_RESONANCE",
                                  f"half-power bandwidth 2*zeta*f < {SPEC_UNRESOLVED_FACTOR:g}*df "
                                  f"(df = {resolution:g} Hz)", FREQUENCY_RESOLUTION, tuple(unresolved), "SPEC §6 S1"))
    if close:
        warnings.append(QCWarning("CLOSE_MODES",
                                  f"adjacent modes closer than {SPEC_CLUSTER_TRIGGER:.0%} in frequency: "
                                  + ", ".join(f"{a}-{b}" for a, b in close) + " (cluster examination trigger only)",
                                  FREQUENCY_RESOLUTION, tuple(sorted({n for pair in close for n in pair})),
                                  "SPEC §12.4"))
    if undamped:
        warnings.append(QCWarning("DAMPING_NOT_AVAILABLE", "resolution versus bandwidth cannot be evaluated",
                                  FREQUENCY_RESOLUTION, tuple(undamped)))
    return ExperimentalQCCheck(FREQUENCY_RESOLUTION, _status(warnings), False,
                               f"df = {resolution:g} Hz; {len(unresolved)} unresolved, {len(close)} close pair(s)",
                               tuple(metrics), tuple(warnings))


def _phase_collinearity(vector: np.ndarray) -> float | None:
    """Modal phase collinearity (1 = real/monophase); eigenvalue form of the real/imag covariance."""
    values = np.asarray(vector, dtype=complex).reshape(-1)
    values = values[np.isfinite(values.real) & np.isfinite(values.imag) & (np.abs(values) > 0.0)]
    if values.size == 0:
        return None
    real, imag = values.real, values.imag
    moments = np.array([[real @ real, real @ imag], [real @ imag, imag @ imag]])  # invariant to phase rotation
    low, high = np.linalg.eigvalsh(moments)
    total = high + low
    return None if total <= 0.0 else float(((high - low) / total) ** 2)


def _confidence_check(validated: ValidatedModalFittingOutput, fixture: ExperimentFixture) -> ExperimentalQCCheck:
    output = validated.output
    modes = output.dataset.sorted_modes()
    columns = [_DIRECTIONS[dof] - 1 for dof in fixture.modal_set.measured_dofs]
    metrics, any_uncertainty = [], False
    for mode in modes:
        entry = output.confidence.get(mode.number, {}) if isinstance(output.confidence, Mapping) else {}
        for key, name in (("frequency_sd_hz", "frequency_uncertainty"), ("damping_sd", "damping_uncertainty")):
            value = entry.get(key)
            any_uncertainty |= value is not None
            metrics.append(ExperimentalQCMetric(name, value, "Hz" if key == "frequency_sd_hz" else "", mode.number,
                                                "" if value is not None else "not provided by the source"))
        metrics.append(ExperimentalQCMetric("shape_uncertainty", None, mode=mode.number, note="not provided by the source"))
        metrics.append(ExperimentalQCMetric("damping_ratio", mode.damping_ratio, mode=mode.number))
        metrics.append(ExperimentalQCMetric("phase_collinearity", _phase_collinearity(np.asarray(mode.vectors)[:, columns]),
                                            mode=mode.number, note="metric only; SPEC §6 S1 gives no limit"))
    flagged = []
    for i, first in enumerate(modes):
        for second in modes[i + 1:]:
            value = modal_assurance_criterion(np.asarray(first.vectors)[:, columns], np.asarray(second.vectors)[:, columns])
            if value is not None and value > SPEC_AUTOMAC_FLAG:
                flagged.append((first.number, second.number, value))
    off_diagonal = [
        modal_assurance_criterion(np.asarray(a.vectors)[:, columns], np.asarray(b.vectors)[:, columns])
        for i, a in enumerate(modes) for b in modes[i + 1:]
    ]
    off_diagonal = [value for value in off_diagonal if value is not None]
    metrics.append(ExperimentalQCMetric("automac_max_off_diagonal", max(off_diagonal) if off_diagonal else None))
    warnings = []
    if flagged:
        warnings.append(QCWarning("AUTOMAC_INDISTINGUISHABLE",
                                  "experimental AutoMAC off-diagonal > 0.5: "
                                  + ", ".join(f"{a}-{b} ({value:.2f})" for a, b, value in flagged),
                                  MODAL_CONFIDENCE, tuple(sorted({n for a, b, _ in flagged for n in (a, b)})),
                                  "SPEC §6 S1"))
    if not any_uncertainty:
        warnings.append(QCWarning("UNCERTAINTY_NOT_AVAILABLE",
                                  "the modal source provides no frequency, damping or shape uncertainty",
                                  MODAL_CONFIDENCE))
    if flagged:
        status = ExperimentalQCStatus.WARNING
    else:
        status = ExperimentalQCStatus.NOT_AVAILABLE if not any_uncertainty else ExperimentalQCStatus.PASS
    return ExperimentalQCCheck(MODAL_CONFIDENCE, status, False,
                               "uncertainty not available" if not any_uncertainty else "uncertainty recorded",
                               tuple(metrics), tuple(warnings))


def _require_trusted(threshold: object) -> TrustedSuspensionThreshold | None:
    if threshold is not None and not isinstance(threshold, TrustedSuspensionThreshold):
        raise TypeError("suspension threshold must be a TrustedSuspensionThreshold (documented physical value) or None.")
    return threshold


def _suspension_check(dataset: ModalDataset, threshold: TrustedSuspensionThreshold | None) -> ExperimentalQCCheck:
    modes = dataset.sorted_modes()
    if threshold is None:
        metric = ExperimentalQCMetric("suspension_max_hz", None, "Hz", note="no trusted physical value (M2 passport)")
        warning = QCWarning("SUSPENSION_THRESHOLD_NOT_AVAILABLE",
                            "no trusted suspension_max_hz is supplied; suspension modes cannot be screened "
                            "(the value is a physical passport property and is never guessed)",
                            SUSPENSION_THRESHOLD, rule="SPEC §6 S1, §19 item 5")
        return ExperimentalQCCheck(SUSPENSION_THRESHOLD, ExperimentalQCStatus.NOT_AVAILABLE, False,
                                   "suspension threshold not available", (metric,), (warning,))
    limit = float(threshold.suspension_max_hz)
    below = tuple(mode.number for mode in modes if mode.frequency_hz < limit)
    above = [mode for mode in modes if mode.frequency_hz >= limit]
    metrics = (
        ExperimentalQCMetric("suspension_max_hz", limit, "Hz", note=threshold.source),
        ExperimentalQCMetric("modes_below_suspension_threshold", len(below)),
        ExperimentalQCMetric("lowest_mode_at_or_above_threshold", above[0].number if above else None),
        ExperimentalQCMetric("lowest_frequency_at_or_above_threshold", above[0].frequency_hz if above else None, "Hz"),
    )
    warnings = (QCWarning("MODES_BELOW_SUSPENSION_THRESHOLD",
                          f"modes below the trusted suspension threshold {limit:g} Hz must not enter material "
                          "identification", SUSPENSION_THRESHOLD, below, "SPEC §6 S1"),) if below else ()
    return ExperimentalQCCheck(SUSPENSION_THRESHOLD, _status(list(warnings)), False,
                               f"threshold {limit:g} Hz; {len(below)} mode(s) below", metrics, warnings)


def evaluate_mode_eligibility(
    dataset: ModalDataset,
    suspension_threshold: TrustedSuspensionThreshold | None = None,
) -> ExperimentalModeEligibility:
    """Which modes may enter material identification (SPEC §6 S1); the dataset is only read."""

    threshold = _require_trusted(suspension_threshold)
    modes = dataset.sorted_modes()
    numbers = tuple(mode.number for mode in modes)
    if threshold is None:
        return ExperimentalModeEligibility(ExperimentalQCStatus.NOT_AVAILABLE, None, numbers, ())
    excluded = tuple(mode.number for mode in modes if mode.frequency_hz < threshold.suspension_max_hz)
    eligible = tuple(number for number in numbers if number not in excluded)
    return ExperimentalModeEligibility(ExperimentalQCStatus.PASS, threshold, eligible, excluded)


def evaluate_experimental_qc(
    validated: ValidatedModalFittingOutput,
    frf: FrfInput,
    fixture: ExperimentFixture,
    *,
    repo_root: Path = REPO_ROOT,
    registry: ModalFittingProviderRegistry | None = None,
    suspension_threshold: TrustedSuspensionThreshold | None = None,
) -> ExperimentalQCReport:
    """Return the QC report for a validated provider output; never modifies the dataset."""

    registry = admitted_provider_registry() if registry is None else registry
    threshold = _require_trusted(suspension_threshold)
    dataset = validated.output.dataset
    provenance = validated.output.provenance if isinstance(validated.output.provenance, Mapping) else {}
    checks = (
        _provenance_check(validated, frf, fixture, registry),
        _contract_check(dataset, fixture, repo_root),
        _frf_check(frf, dataset, fixture),
        _coherence_check(frf, dataset),
        _resolution_check(frf, dataset),
        _confidence_check(validated, fixture),
        _suspension_check(dataset, threshold),
    )
    provider = validated.output.provider
    return ExperimentalQCReport(
        fixture_id=fixture.fixture_id,
        modal_source=str(dataset.metadata.get("mode_source")),
        provider={"name": provider.name, "version": provider.version, "kind": provider.kind.value},
        provenance_reference={
            "provenance_hash": canonical_hash(_jsonable(provenance)),
            "configuration_hash": str(provenance.get("configuration_hash")),
            "frf_content_hash": frf.content_hash,
            "source_sha256": fixture.experimental_source.sha256,
            "registration_hash": fixture.registration.registration_hash,
        },
        checks=checks,
        policy={
            "hard_checks": [PROVENANCE, MEASUREMENT_CONTRACT, FRF_COMPLETENESS + " (source identity only)"],
            "flag_rules": {
                "coherence_at_resonance": f"< {SPEC_COHERENCE_FLAG} (SPEC §6 S1)",
                "unresolved_resonance": f"2*zeta*f < {SPEC_UNRESOLVED_FACTOR:g}*df (SPEC §6 S1)",
                "close_modes": f"|df|/f < {SPEC_CLUSTER_TRIGGER:.0%} trigger (SPEC §12.4)",
                "automac": f"off-diagonal > {SPEC_AUTOMAC_FLAG} (SPEC §6 S1)",
                "phase_collinearity": "metric only (no limit in the SPEC)",
                "suspension_threshold": "modes below a trusted physical suspension_max_hz (SPEC §6 S1, §19 item 5); "
                                        "NOT_AVAILABLE without one; never guessed",
            },
            "note": "Diagnostic warnings never refuse or modify modes; no automatic mode rejection.",
        },
    )


@dataclass(frozen=True)
class AutoIDExperimentalInput:
    """Experimental input admitted to Auto-ID: provider output, QC report and mode eligibility.

    ``dataset`` is the provider dataset, unchanged.  ``identification_dataset()`` is the
    explicit view material identification must use: it leaves out the modes the
    eligibility result excludes (below a trusted suspension threshold).
    """

    dataset: ModalDataset
    provider_output: ValidatedModalFittingOutput
    qc_report: ExperimentalQCReport
    eligibility: ExperimentalModeEligibility

    def identification_dataset(self) -> ModalDataset:
        keep = set(self.eligibility.eligible_modes)
        return ModalDataset(
            source_name=self.dataset.source_name,
            source_path=self.dataset.source_path,
            modes=[mode for mode in self.dataset.modes if mode.number in keep],
            metadata={**self.dataset.metadata, "mode_eligibility": self.eligibility.to_dict()},
            history=list(self.dataset.history),
        )


def prepare_auto_id_experimental_input(
    fixture_id: str,
    *,
    roots: Mapping[str, Path] | None = None,
    manifest: ExperimentFixtureManifest | None = None,
    repo_root: Path = REPO_ROOT,
    suspension_threshold: TrustedSuspensionThreshold | None = None,
) -> AutoIDExperimentalInput:
    """M1.2 -> M1.3 provider -> M1.1 -> M1.4 QC -> mode eligibility.

    Refuses only on a hard QC failure.  ``suspension_threshold`` must be a trusted
    physical value (M2 passport); without it, suspension screening is NOT_AVAILABLE.
    """

    manifest = load_experiment_fixture_manifest(FIXTURE_MANIFEST_PATH) if manifest is None else manifest
    roots = fixture_roots_from_environment() if roots is None else roots
    validated = prepare_external_polymax_modal_dataset(fixture_id, roots=roots, manifest=manifest, repo_root=repo_root)
    fixture = manifest.fixture(fixture_id)
    threshold = _require_trusted(suspension_threshold)
    report = evaluate_experimental_qc(validated, prepare_frf_input(fixture, roots), fixture, repo_root=repo_root,
                                      suspension_threshold=threshold)
    if not report.admissible:
        raise ExperimentalQCRefusal(report)
    eligibility = evaluate_mode_eligibility(validated.output.dataset, threshold)
    return AutoIDExperimentalInput(validated.output.dataset, validated, report, eligibility)
