from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Dict, Optional

from .specimen import require_identifier


class ParameterScope(str, Enum):
    GLOBAL = "global"
    SPECIMEN = "specimen"


class ParameterRole(str, Enum):
    FIXED = "fixed"
    FITTED = "fitted"


class ParameterResultStatus(str, Enum):
    IDENTIFIED = "identified"
    WEAKLY_IDENTIFIABLE = "weakly_identifiable"
    NOT_IDENTIFIABLE = "not_identifiable"
    BOUNDED = "bounded"
    FIXED = "fixed"


@dataclass(frozen=True)
class ParameterPrior:
    mean: float
    standard_uncertainty: float
    distribution: str = "normal"
    metadata: Dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.mean)):
            raise ValueError("Prior mean must be finite.")
        if (
            not math.isfinite(float(self.standard_uncertainty))
            or float(self.standard_uncertainty) <= 0.0
        ):
            raise ValueError("Prior uncertainty must be positive and finite.")
        require_identifier(self.distribution, "Prior distribution")


@dataclass(frozen=True)
class IdentificationParameter:
    parameter_id: str
    scope: ParameterScope
    role: ParameterRole
    physical_specimen_id: Optional[str] = None
    initial_value: Optional[float] = None
    fixed_value: Optional[float] = None
    prior: Optional[ParameterPrior] = None
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None
    transformation: str = "identity"
    transformation_metadata: Dict[str, Any] = field(default_factory=dict, compare=False)
    result_status: Optional[ParameterResultStatus] = None
    metadata: Dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        require_identifier(self.parameter_id, "parameter_id")
        require_identifier(self.transformation, "Parameter transformation")
        if self.scope == ParameterScope.GLOBAL and self.physical_specimen_id is not None:
            raise ValueError("A global parameter cannot belong to one physical specimen.")
        if self.scope == ParameterScope.SPECIMEN:
            if self.physical_specimen_id is None:
                raise ValueError(
                    "A specimen-specific parameter requires physical_specimen_id."
                )
            require_identifier(self.physical_specimen_id, "physical_specimen_id")

        for name, value in (
            ("initial_value", self.initial_value),
            ("fixed_value", self.fixed_value),
            ("lower_bound", self.lower_bound),
            ("upper_bound", self.upper_bound),
        ):
            if value is not None and not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite when provided.")
        if (
            self.lower_bound is not None
            and self.upper_bound is not None
            and self.lower_bound >= self.upper_bound
        ):
            raise ValueError("Parameter lower_bound must be less than upper_bound.")

        if self.role == ParameterRole.FIXED:
            if self.fixed_value is None:
                raise ValueError("A fixed parameter requires fixed_value.")
            if self.result_status not in (None, ParameterResultStatus.FIXED):
                raise ValueError("A fixed parameter can only have result status 'fixed'.")
            if self.result_status is None:
                object.__setattr__(self, "result_status", ParameterResultStatus.FIXED)
        elif self.fixed_value is not None:
            raise ValueError("A fitted parameter cannot have fixed_value.")
        if self.role == ParameterRole.FITTED and self.result_status == ParameterResultStatus.FIXED:
            raise ValueError("A fitted parameter cannot have result status 'fixed'.")

        candidate_values = [self.initial_value, self.fixed_value]
        if self.prior is not None:
            candidate_values.append(self.prior.mean)
        for value in candidate_values:
            if value is None:
                continue
            if self.lower_bound is not None and value < self.lower_bound:
                raise ValueError("Parameter value or prior mean is below lower_bound.")
            if self.upper_bound is not None and value > self.upper_bound:
                raise ValueError("Parameter value or prior mean is above upper_bound.")
