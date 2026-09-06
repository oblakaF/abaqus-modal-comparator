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

    def __post_init__(self) -> None:
        require_identifier(self.cluster_id, "cluster_id")
        require_identifier(self.physical_specimen_id, "physical_specimen_id")
        require_identifier(self.test_run_id, "test_run_id")
        object.__setattr__(self, "observation_ids", tuple(self.observation_ids))
        if len(self.observation_ids) < 2:
            raise ValueError("A modal cluster requires at least two observations.")
        if len(self.observation_ids) != len(set(self.observation_ids)):
            raise ValueError("A modal cluster cannot contain duplicate observation IDs.")
        for observation_id in self.observation_ids:
            require_identifier(observation_id, "observation_id")
        if self.inclusion_status != InclusionStatus.INCLUDED and not self.reason.strip():
            raise ValueError("A downweighted or excluded modal cluster requires a reason.")

    @property
    def effective_observation_count(self) -> int:
        return 1
