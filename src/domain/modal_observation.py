from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Dict, Optional, Tuple

from .specimen import require_identifier


class InclusionStatus(str, Enum):
    INCLUDED = "included"
    DOWNWEIGHTED = "downweighted"
    EXCLUDED = "excluded"


@dataclass(frozen=True)
class ObservationUncertainty:
    measurement: Optional[float] = None
    setup: Optional[float] = None
    manufacturing: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        for name, value in (
            ("measurement", self.measurement),
            ("setup", self.setup),
            ("manufacturing", self.manufacturing),
        ):
            if value is not None and (
                not math.isfinite(float(value)) or float(value) < 0.0
            ):
                raise ValueError(f"Observation {name} uncertainty must be non-negative and finite.")


@dataclass(frozen=True)
class ModalObservation:
    """Adapter record produced from one accepted or reviewed comparator pair."""

    observation_id: str
    physical_specimen_id: str
    test_run_id: str
    fe_mode_id: int
    experimental_mode_id: int
    fe_frequency_hz: float
    experimental_frequency_hz: float
    mac: Optional[float]
    inclusion_status: InclusionStatus = InclusionStatus.INCLUDED
    reason: str = ""
    mode_class: Optional[str] = None
    uncertainty: ObservationUncertainty = field(default_factory=ObservationUncertainty)
    metadata: Dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        require_identifier(self.observation_id, "observation_id")
        require_identifier(self.physical_specimen_id, "physical_specimen_id")
        require_identifier(self.test_run_id, "test_run_id")
        if int(self.fe_mode_id) <= 0 or int(self.experimental_mode_id) <= 0:
            raise ValueError("FE and experimental mode identifiers must be positive.")
        for name, value in (
            ("FE frequency", self.fe_frequency_hz),
            ("Experimental frequency", self.experimental_frequency_hz),
        ):
            if not math.isfinite(float(value)) or float(value) <= 0.0:
                raise ValueError(f"{name} must be positive and finite.")
        if self.mac is not None and (
            not math.isfinite(float(self.mac)) or not 0.0 <= float(self.mac) <= 1.0
        ):
            raise ValueError("MAC must be between zero and one when available.")
        if self.inclusion_status != InclusionStatus.INCLUDED and not self.reason.strip():
            raise ValueError("A downweighted or excluded observation requires a reason.")


@dataclass(frozen=True)
class ModalCluster:
    """A near-degenerate mode group that counts as one statistical observation."""

    cluster_id: str
    physical_specimen_id: str
    test_run_id: str
    observation_ids: Tuple[str, ...]
    inclusion_status: InclusionStatus = InclusionStatus.INCLUDED
    reason: str = ""
    mode_class: Optional[str] = "cluster"
    uncertainty: ObservationUncertainty = field(default_factory=ObservationUncertainty)
    metadata: Dict[str, Any] = field(default_factory=dict, compare=False)
    fe_mode_ids: Tuple[int, ...] = ()
    experimental_mode_ids: Tuple[int, ...] = ()
    fe_frequencies_hz: Tuple[float, ...] = ()
    experimental_frequencies_hz: Tuple[float, ...] = ()
    subspace_mac: Optional[float] = None
    frequency_residual: Optional[float] = None
    fe_frequency_splitting_hz: Optional[float] = None
    experimental_frequency_splitting_hz: Optional[float] = None

    def __post_init__(self) -> None:
        require_identifier(self.cluster_id, "cluster_id")
        require_identifier(self.physical_specimen_id, "physical_specimen_id")
        require_identifier(self.test_run_id, "test_run_id")
        object.__setattr__(self, "observation_ids", tuple(self.observation_ids))
        object.__setattr__(self, "fe_mode_ids", tuple(self.fe_mode_ids))
        object.__setattr__(
            self, "experimental_mode_ids", tuple(self.experimental_mode_ids)
        )
        object.__setattr__(self, "fe_frequencies_hz", tuple(self.fe_frequencies_hz))
        object.__setattr__(
            self,
            "experimental_frequencies_hz",
            tuple(self.experimental_frequencies_hz),
        )
        if len(self.observation_ids) < 2:
            raise ValueError("A modal cluster requires at least two observations.")
        if len(self.observation_ids) != len(set(self.observation_ids)):
            raise ValueError("A modal cluster cannot contain duplicate observation IDs.")
        for observation_id in self.observation_ids:
            require_identifier(observation_id, "observation_id")
        fe_detail_lengths = {len(self.fe_mode_ids), len(self.fe_frequencies_hz)}
        experimental_detail_lengths = {
            len(self.experimental_mode_ids),
            len(self.experimental_frequencies_hz),
        }
        if fe_detail_lengths not in ({0}, {len(self.fe_mode_ids)}) or (
            experimental_detail_lengths
            not in ({0}, {len(self.experimental_mode_ids)})
        ):
            raise ValueError(
                "Modal cluster member identifiers and frequencies must be supplied "
                "together for each side."
            )
        for mode_id in self.fe_mode_ids + self.experimental_mode_ids:
            if int(mode_id) <= 0:
                raise ValueError("Modal cluster member mode identifiers must be positive.")
        for frequency in self.fe_frequencies_hz + self.experimental_frequencies_hz:
            if not math.isfinite(float(frequency)) or float(frequency) <= 0.0:
                raise ValueError("Modal cluster member frequencies must be positive and finite.")
        fe_member_count = len(self.fe_mode_ids)
        experimental_member_count = len(self.experimental_mode_ids)
        if (fe_member_count or experimental_member_count) and (
            fe_member_count != experimental_member_count
        ):
            incomplete_reason = (
                "Incomplete modal cluster requires manual review: "
                f"{fe_member_count} FE member modes and "
                f"{experimental_member_count} experimental member modes."
            )
            existing_reason = self.reason.strip()
            object.__setattr__(self, "inclusion_status", InclusionStatus.EXCLUDED)
            object.__setattr__(
                self,
                "reason",
                incomplete_reason
                if not existing_reason
                else f"{incomplete_reason} {existing_reason}",
            )
        if self.inclusion_status != InclusionStatus.INCLUDED and not self.reason.strip():
            raise ValueError("A downweighted or excluded modal cluster requires a reason.")
        if self.subspace_mac is not None and (
            not math.isfinite(float(self.subspace_mac))
            or not 0.0 <= float(self.subspace_mac) <= 1.0
        ):
            raise ValueError("Subspace MAC must be between zero and one when available.")
        if self.frequency_residual is not None and not math.isfinite(
            float(self.frequency_residual)
        ):
            raise ValueError("Modal cluster frequency residual must be finite when available.")
        for name, splitting in (
            ("FE", self.fe_frequency_splitting_hz),
            ("Experimental", self.experimental_frequency_splitting_hz),
        ):
            if splitting is not None and (
                not math.isfinite(float(splitting)) or float(splitting) < 0.0
            ):
                raise ValueError(f"{name} cluster frequency splitting must be finite and non-negative.")

    @property
    def cluster_size(self) -> int:
        return len(self.observation_ids)

    @property
    def effective_observation_count(self) -> int:
        if self.inclusion_status == InclusionStatus.EXCLUDED:
            return 0
        return 1
