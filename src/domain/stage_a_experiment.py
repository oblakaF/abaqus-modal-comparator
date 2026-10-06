"""Stage-A bare-plate experimental evidence — Auto-ID M6 (SPEC §4.1, §6 S1, §7, §12.1, §15; D-019, D-026, D-030,
D-031, D-049–D-056; M6_DECISION_RECORD.md).

Typed records of everything a real Stage-A validation run needs before any identification
starts:
- a frozen, curve-fitted modal set (FRF-only packages are refused, D-030);
- the plate thickness characterisation (at least 9 measured points, SPEC §15);
- the excitation route (attachment mass recorded and modelled, or an approved non-contact
  route, SPEC §15);
- a trusted suspension threshold (M1.4, D-031);
- mass and plan dimensions with uncertainties;
- the experiment-to-FE pairing (strict policy, frozen registration; never the legacy fixed-pair
  fallback).

Missing evidence is never filled in: every gap is reported together as one
``StageAInputRefusal`` so the HUMAN sees the complete list. No value here is a default.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import re
from typing import Optional

from .identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING
from .identification_run import canonical_hash
from .modal_input_source import PEAK_DERIVED_DATASET_TYPES, ModalInputSource, ModalInputSourceClassification
from .specimen_manifest import MINIMUM_THICKNESS_POINTS
from .experimental_qc import TrustedSuspensionThreshold


SCHEMA = "auto-id/stage-a-experiment/v1"
MINIMUM_EXCITATION_LOCATIONS = 2  # SPEC §15 "Two excitation points"
LEGACY_FIXED_PAIR_FALLBACK_SOURCE = "fixed_pair_synthetic_fallback"  # legacy PairingProviderMode value (refused)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class StageAEvidenceError(ValueError):
    """A record is malformed (wrong types, non-finite or non-positive values)."""


class RefusalCode(str, Enum):
    FRF_ONLY_INPUT = "FRF_ONLY_INPUT"
    NOT_CURVE_FITTED = "NOT_CURVE_FITTED"
    MISSING_FROZEN_MODAL_SET = "MISSING_FROZEN_MODAL_SET"
    MODAL_SET_MISMATCH = "MODAL_SET_MISMATCH"
    MISSING_THICKNESS = "MISSING_THICKNESS"
    INSUFFICIENT_THICKNESS_POINTS = "INSUFFICIENT_THICKNESS_POINTS"
    MISSING_EXCITATION_EVIDENCE = "MISSING_EXCITATION_EVIDENCE"
    INSUFFICIENT_EXCITATION_LOCATIONS = "INSUFFICIENT_EXCITATION_LOCATIONS"
    MISSING_ATTACHMENT_MASS = "MISSING_ATTACHMENT_MASS"
    NON_CONTACT_ROUTE_NOT_APPROVED = "NON_CONTACT_ROUTE_NOT_APPROVED"
    ATTACHMENT_MASS_NOT_MODELLED = "ATTACHMENT_MASS_NOT_MODELLED"
    MISSING_SUSPENSION = "MISSING_SUSPENSION"
    MODE_BELOW_SUSPENSION = "MODE_BELOW_SUSPENSION"
    MISSING_SPECIMEN_MEASUREMENTS = "MISSING_SPECIMEN_MEASUREMENTS"
    MISSING_GEOMETRY_CALIBRATION = "MISSING_GEOMETRY_CALIBRATION"
    MISSING_PAIRING = "MISSING_PAIRING"
    FIXED_PAIR_FALLBACK = "FIXED_PAIR_FALLBACK"
    NON_STRICT_PAIRING_POLICY = "NON_STRICT_PAIRING_POLICY"
    UNKNOWN_EXPERIMENTAL_MODE = "UNKNOWN_EXPERIMENTAL_MODE"
    TOO_FEW_FIT_TERMS = "TOO_FEW_FIT_TERMS"


class StageAInputRefusal(Exception):
    """The Stage-A inputs are incomplete or inadmissible. Every gap is listed; nothing is defaulted.

    Not a ValueError/RuntimeError, so generic fallback handlers never swallow it.
    """

    def __init__(self, reasons: tuple[tuple[RefusalCode, str], ...]) -> None:
        super().__init__("Stage-A input refused: " + "; ".join(f"{code.value}: {text}" for code, text in reasons))
        self.reasons = tuple(reasons)

    @property
    def codes(self) -> tuple[RefusalCode, ...]:
        return tuple(code for code, _ in self.reasons)


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StageAEvidenceError(f"{name} must be a non-empty string.")
    return value


def _positive(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) \
            or float(value) <= 0.0:
        raise StageAEvidenceError(f"{name} must be a finite positive number.")
    return float(value)


# ----------------------------------------------------------------------------- modal input

@dataclass(frozen=True)
class FrozenModalSetIdentity:
    """A governed frozen modal set (D-026): pinned source file, pinned modal set, provenance."""

    source_sha256: str
    modal_set_key: str
    mode_count: int
    mode_source: str  # the reader / admitted provider label of the curve fit
    provenance: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_sha256, str) or not _SHA256.match(self.source_sha256):
            raise StageAEvidenceError("source_sha256 must be a lower-case SHA-256.")
        _text(self.modal_set_key, "modal_set_key")
        if isinstance(self.mode_count, bool) or not isinstance(self.mode_count, int) or self.mode_count < 1:
            raise StageAEvidenceError("mode_count must be a positive integer.")
        _text(self.mode_source, "mode_source")
        _text(self.provenance, "modal set provenance")

    def to_dict(self) -> dict:
        return {"source_sha256": self.source_sha256, "modal_set_key": self.modal_set_key,
                "mode_count": self.mode_count, "mode_source": self.mode_source, "provenance": self.provenance}


@dataclass(frozen=True)
class ExperimentalMode:
    mode_id: int
    frequency_hz: float

    def __post_init__(self) -> None:
        if isinstance(self.mode_id, bool) or not isinstance(self.mode_id, int) or self.mode_id < 1:
            raise StageAEvidenceError("mode_id must be a positive integer.")
        _positive(self.frequency_hz, f"mode {self.mode_id} frequency_hz")


@dataclass(frozen=True)
class StageAModalInput:
    """The experimental modal input as admitted (or not) by M1: dataset types, M1.1 class, frozen set."""

    dataset_types: tuple[int, ...]  # UNV dataset types present in the source package
    source_classification: Optional[ModalInputSourceClassification]  # M1.1 classification of the modes
    frozen_modal_set: Optional[FrozenModalSetIdentity]
    modes: tuple[ExperimentalMode, ...]

    def __post_init__(self) -> None:
        if any(isinstance(t, bool) or not isinstance(t, int) for t in self.dataset_types):
            raise StageAEvidenceError("dataset_types must be integers.")
        ids = [m.mode_id for m in self.modes]
        if len(set(ids)) != len(ids):
            raise StageAEvidenceError("experimental mode ids must be unique.")

    @property
    def frf_only(self) -> bool:
        types = set(self.dataset_types)
        return bool(types) and types <= set(PEAK_DERIVED_DATASET_TYPES)

    def mode(self, mode_id: int) -> Optional[ExperimentalMode]:
        return next((m for m in self.modes if m.mode_id == mode_id), None)

    def refusals(self) -> list[tuple[RefusalCode, str]]:
        found = []
        if self.frf_only:
            found.append((RefusalCode.FRF_ONLY_INPUT, "the package holds only dataset-58 FRF records; FRF-only "
                          "packages are refused until an admitted internal fitting provider exists (D-030)"))
        classification = self.source_classification
        if classification is None or classification.source is not ModalInputSource.CURVE_FITTED:
            detail = "not classified" if classification is None else \
                f"{classification.source.value}: {classification.reason}"
            found.append((RefusalCode.NOT_CURVE_FITTED, f"modes are not verified curve-fitted input ({detail}; "
                          "SPEC §4, D-019)"))
        if self.frozen_modal_set is None:
            found.append((RefusalCode.MISSING_FROZEN_MODAL_SET, "no governed frozen modal set (pinned source, "
                          "modal set and provenance, D-026)"))
        elif self.frozen_modal_set.mode_count != len(self.modes):
            found.append((RefusalCode.MODAL_SET_MISMATCH, f"frozen set declares {self.frozen_modal_set.mode_count} "
                          f"modes, {len(self.modes)} given"))
        return found

    def to_dict(self) -> dict:
        classification = self.source_classification
        return {"dataset_types": sorted(set(self.dataset_types)),
                "source_class": None if classification is None else classification.source.value,
                "frozen_modal_set": None if self.frozen_modal_set is None else self.frozen_modal_set.to_dict(),
                "modes": [{"mode_id": m.mode_id, "frequency_hz": m.frequency_hz} for m in self.modes]}


# ----------------------------------------------------------------------------- thickness

@dataclass(frozen=True)
class ThicknessPoint:
    position: str  # where on the plate the point was measured
    value_mm: float

    def __post_init__(self) -> None:
        _text(self.position, "thickness position")
        _positive(self.value_mm, f"thickness at {self.position}")


@dataclass(frozen=True)
class GaugeUncertainty:
    """A known instrument (gauge) standard uncertainty: a separate measurement component (never invented)."""

    sd_mm: float
    source: str

    def __post_init__(self) -> None:
        _positive(self.sd_mm, "gauge sd_mm")
        _text(self.source, "gauge uncertainty source")


@dataclass(frozen=True)
class ThicknessCharacterization:
    """Measured plate thickness. The spatial scatter is the sample sd of the points (never divided by √N)."""

    points: tuple[ThicknessPoint, ...]
    provenance: str
    gauge_identity: Optional[str] = None
    gauge_resolution_mm: Optional[float] = None  # metadata only; never converted into an uncertainty
    gauge_uncertainty: Optional[GaugeUncertainty] = None

    def __post_init__(self) -> None:
        _text(self.provenance, "thickness provenance")
        positions = [p.position for p in self.points]
        if len(set(positions)) != len(positions):
            raise StageAEvidenceError("thickness positions must be unique.")
        if self.gauge_identity is not None:
            _text(self.gauge_identity, "gauge_identity")
        if self.gauge_resolution_mm is not None:
            _positive(self.gauge_resolution_mm, "gauge_resolution_mm")

    @property
    def count(self) -> int:
        return len(self.points)

    @property
    def mean_mm(self) -> float:
        return math.fsum(p.value_mm for p in self.points) / len(self.points)

    @property
    def spatial_sd_mm(self) -> float:
        """Sample standard deviation (n − 1) of the measured points: the physical plate non-uniformity."""
        mean = self.mean_mm
        return math.sqrt(math.fsum((p.value_mm - mean) ** 2 for p in self.points) / (len(self.points) - 1))

    def refusals(self) -> list[tuple[RefusalCode, str]]:
        if self.count < MINIMUM_THICKNESS_POINTS:
            return [(RefusalCode.INSUFFICIENT_THICKNESS_POINTS, f"{self.count} thickness points < "
                     f"{MINIMUM_THICKNESS_POINTS} (SPEC §15)")]
        return []

    def to_dict(self) -> dict:
        return {"points": [{"position": p.position, "value_mm": p.value_mm} for p in self.points],
                "provenance": self.provenance, "gauge_identity": self.gauge_identity,
                "gauge_resolution_mm": self.gauge_resolution_mm,
                "gauge_uncertainty": None if self.gauge_uncertainty is None else
                {"sd_mm": self.gauge_uncertainty.sd_mm, "source": self.gauge_uncertainty.source}}

    @property
    def record_hash(self) -> str:
        return canonical_hash(self.to_dict())


# ----------------------------------------------------------------------------- excitation, specimen

class ExcitationRoute(str, Enum):
    CONTACT_ATTACHMENT = "CONTACT_ATTACHMENT"  # shaker / force sensor: the attachment mass must be in the model
    NON_CONTACT = "NON_CONTACT"  # needs an approved route (SPEC §15)


@dataclass(frozen=True)
class ExcitationEvidence:
    route: ExcitationRoute
    locations: tuple[str, ...]
    attachment_mass_g: Optional[float] = None  # CONTACT_ATTACHMENT: measured attached mass
    attachment_mass_source: Optional[str] = None
    non_contact_approval: Optional[str] = None  # NON_CONTACT: the governing approval reference

    def __post_init__(self) -> None:
        if not isinstance(self.route, ExcitationRoute):
            raise StageAEvidenceError("route must be an ExcitationRoute.")
        if len(set(self.locations)) != len(self.locations):
            raise StageAEvidenceError("excitation locations must be unique.")
        for location in self.locations:
            _text(location, "excitation location")
        if self.attachment_mass_g is not None:
            _positive(self.attachment_mass_g, "attachment_mass_g")

    def refusals(self) -> list[tuple[RefusalCode, str]]:
        found = []
        if len(self.locations) < MINIMUM_EXCITATION_LOCATIONS:
            found.append((RefusalCode.INSUFFICIENT_EXCITATION_LOCATIONS, f"{len(self.locations)} excitation "
                          f"location(s) < {MINIMUM_EXCITATION_LOCATIONS} (SPEC §15)"))
        if self.route is ExcitationRoute.CONTACT_ATTACHMENT:
            if self.attachment_mass_g is None or not (self.attachment_mass_source or "").strip():
                found.append((RefusalCode.MISSING_ATTACHMENT_MASS, "contact excitation without a recorded "
                              "attachment mass and its source (SPEC §15)"))
        elif not (self.non_contact_approval or "").strip():
            found.append((RefusalCode.NON_CONTACT_ROUTE_NOT_APPROVED, "non-contact excitation without an approved "
                          "route reference (SPEC §15)"))
        return found

    def to_dict(self) -> dict:
        return {"route": self.route.value, "locations": list(self.locations),
                "attachment_mass_g": self.attachment_mass_g, "attachment_mass_source": self.attachment_mass_source,
                "non_contact_approval": self.non_contact_approval}


@dataclass(frozen=True)
class SpecimenMeasurements:
    """Mass and plan dimensions with their uncertainties (recorded; propagation is an open M6 item)."""

    mass_g: float
    mass_sd_g: float
    length_mm: float
    width_mm: float
    plan_sd_mm: float
    provenance: str

    def __post_init__(self) -> None:
        for name in ("mass_g", "mass_sd_g", "length_mm", "width_mm", "plan_sd_mm"):
            _positive(getattr(self, name), name)
        _text(self.provenance, "specimen measurement provenance")

    def to_dict(self) -> dict:
        return {"mass_g": self.mass_g, "mass_sd_g": self.mass_sd_g, "length_mm": self.length_mm,
                "width_mm": self.width_mm, "plan_sd_mm": self.plan_sd_mm, "provenance": self.provenance}


# ----------------------------------------------------------------------------- pairing (experiment ↔ FE baseline)

class ObservationRole(str, Enum):
    FIT = "FIT"
    HOLDOUT = "HOLDOUT"


@dataclass(frozen=True)
class StageAObservationRow:
    row_id: str
    experimental_mode_id: int
    fe_mode: int  # FE mode number in the baseline (pairing) state
    family: str  # modal-family identity (pattern test, leave-one-family-out)
    role: ObservationRole
    mac: float  # experiment-to-FE MAC of the pairing

    def __post_init__(self) -> None:
        _text(self.row_id, "row_id")
        _text(self.family, f"{self.row_id} family")
        if not isinstance(self.role, ObservationRole):
            raise StageAEvidenceError("role must be an ObservationRole.")
        if isinstance(self.mac, bool) or not isinstance(self.mac, (int, float)) or not 0.0 <= float(self.mac) <= 1.0:
            raise StageAEvidenceError(f"{self.row_id}: MAC must be in [0, 1].")


@dataclass(frozen=True)
class StageAPairingEvidence:
    """Frozen pairing at the baseline FE state (D-008), produced upstream under the strict policy."""

    rows: tuple[StageAObservationRow, ...]
    clusters: tuple[tuple[str, str], ...]  # confirmed 2-mode clusters (fit rows); one fit term each
    policy_id: str
    pairing_source: str
    registration_hash: Optional[str]  # FrozenRegistration from the passport geometry calibration (M2)
    registration_limited: bool  # the M2 registration diagnostic
    provenance: str

    def __post_init__(self) -> None:
        ids = [r.row_id for r in self.rows]
        if len(set(ids)) != len(ids):
            raise StageAEvidenceError("row ids must be unique.")
        _text(self.policy_id, "policy_id")
        _text(self.pairing_source, "pairing_source")
        _text(self.provenance, "pairing provenance")
        if not isinstance(self.registration_limited, bool):
            raise StageAEvidenceError("registration_limited must be a boolean.")
        fit = {r.row_id for r in self.rows if r.role is ObservationRole.FIT}
        members = [m for group in self.clusters for m in group]
        if any(len(group) != 2 for group in self.clusters) or len(set(members)) != len(members) \
                or not set(members) <= fit:
            raise StageAEvidenceError("clusters must be disjoint pairs of FIT rows.")

    @property
    def fit_rows(self) -> tuple[StageAObservationRow, ...]:
        return tuple(r for r in self.rows if r.role is ObservationRole.FIT)

    @property
    def holdout_rows(self) -> tuple[StageAObservationRow, ...]:
        return tuple(r for r in self.rows if r.role is ObservationRole.HOLDOUT)

    @property
    def single_fit_rows(self) -> tuple[str, ...]:
        clustered = {m for group in self.clusters for m in group}
        return tuple(r.row_id for r in self.fit_rows if r.row_id not in clustered)

    @property
    def fit_term_ids(self) -> tuple[str, ...]:
        """M5 fit terms in matrix order: single rows, then one term per confirmed cluster."""
        return self.single_fit_rows + tuple("C(" + "+".join(group) + ")" for group in self.clusters)

    def refusals(self, modal_input: Optional[StageAModalInput]) -> list[tuple[RefusalCode, str]]:
        found = []
        if self.pairing_source == LEGACY_FIXED_PAIR_FALLBACK_SOURCE:
            found.append((RefusalCode.FIXED_PAIR_FALLBACK, "the legacy fixed-pair fallback is not an admissible "
                          "pairing source (D-056)"))
        if self.policy_id != STRICT_IDENTIFICATION_PAIRING.policy_id:
            found.append((RefusalCode.NON_STRICT_PAIRING_POLICY, f"pairing policy {self.policy_id!r} is not the "
                          f"strict identification policy (SPEC §12.1, D-033)"))
        if not (self.registration_hash or "").strip():
            found.append((RefusalCode.MISSING_GEOMETRY_CALIBRATION, "no FrozenRegistration from the passport "
                          "geometry calibration (SPEC §11, D-007)"))
        if len(self.fit_term_ids) < STRICT_IDENTIFICATION_PAIRING.minimum_observations:
            found.append((RefusalCode.TOO_FEW_FIT_TERMS, f"{len(self.fit_term_ids)} fit terms < "
                          f"{STRICT_IDENTIFICATION_PAIRING.minimum_observations} (strict policy)"))
        if modal_input is not None:
            unknown = sorted({r.experimental_mode_id for r in self.rows if modal_input.mode(r.experimental_mode_id)
                              is None})
            if unknown:
                found.append((RefusalCode.UNKNOWN_EXPERIMENTAL_MODE, f"pairing names modes {unknown} that are not "
                              "in the frozen modal set"))
        return found

    def to_dict(self) -> dict:
        return {"rows": [{"row_id": r.row_id, "experimental_mode_id": r.experimental_mode_id, "fe_mode": r.fe_mode,
                          "family": r.family, "role": r.role.value, "mac": r.mac} for r in self.rows],
                "clusters": [list(group) for group in self.clusters], "policy_id": self.policy_id,
                "pairing_source": self.pairing_source, "registration_hash": self.registration_hash,
                "registration_limited": self.registration_limited, "provenance": self.provenance}

    @property
    def record_hash(self) -> str:
        return canonical_hash(self.to_dict())


# ----------------------------------------------------------------------------- the complete evidence set

@dataclass(frozen=True)
class StageAExperimentalEvidence:
    """Every experimental input of one Stage-A test run. ``None`` marks evidence that is still missing."""

    physical_specimen_id: str
    test_run_id: str
    modal_input: Optional[StageAModalInput]
    thickness: Optional[ThicknessCharacterization]
    excitation: Optional[ExcitationEvidence]
    suspension: Optional[TrustedSuspensionThreshold]
    specimen: Optional[SpecimenMeasurements]

    def __post_init__(self) -> None:
        _text(self.physical_specimen_id, "physical_specimen_id")
        _text(self.test_run_id, "test_run_id")

    def refusals(self) -> list[tuple[RefusalCode, str]]:
        found: list[tuple[RefusalCode, str]] = []
        if self.modal_input is None:
            found.append((RefusalCode.MISSING_FROZEN_MODAL_SET, "no experimental modal input"))
        else:
            found.extend(self.modal_input.refusals())
        if self.thickness is None:
            found.append((RefusalCode.MISSING_THICKNESS, "no thickness characterisation (≥ "
                          f"{MINIMUM_THICKNESS_POINTS} measured points, SPEC §15)"))
        else:
            found.extend(self.thickness.refusals())
        if self.excitation is None:
            found.append((RefusalCode.MISSING_EXCITATION_EVIDENCE, "no excitation route / attachment evidence"))
        else:
            found.extend(self.excitation.refusals())
        if self.suspension is None:
            found.append((RefusalCode.MISSING_SUSPENSION, "no trusted suspension threshold (D-031; never "
                          "guessed)"))
        if self.specimen is None:
            found.append((RefusalCode.MISSING_SPECIMEN_MEASUREMENTS, "no mass / plan dimensions with "
                          "uncertainties"))
        return found

    def to_dict(self) -> dict:
        return {"schema": SCHEMA, "physical_specimen_id": self.physical_specimen_id, "test_run_id": self.test_run_id,
                "modal_input": None if self.modal_input is None else self.modal_input.to_dict(),
                "thickness": None if self.thickness is None else self.thickness.to_dict(),
                "excitation": None if self.excitation is None else self.excitation.to_dict(),
                "suspension": None if self.suspension is None else
                {"suspension_max_hz": self.suspension.suspension_max_hz, "source": self.suspension.source},
                "specimen": None if self.specimen is None else self.specimen.to_dict()}

    @property
    def record_hash(self) -> str:
        return canonical_hash(self.to_dict())
