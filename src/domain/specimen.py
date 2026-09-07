from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Dict, Optional, Tuple


_DERIVED_MEASUREMENT_NAMES = {"areal_mass", "mu", "μ", "face_offset", "d"}


def require_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")


@dataclass(frozen=True)
class FaceSectionFamily:
    face_section_family_id: str
    name: str
    metadata: Dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        require_identifier(self.face_section_family_id, "face_section_family_id")
        require_identifier(self.name, "Face section family name")


@dataclass(frozen=True)
class CoreFamily:
    core_family_id: str
    name: str
    metadata: Dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        require_identifier(self.core_family_id, "core_family_id")
        require_identifier(self.name, "Core family name")


@dataclass(frozen=True)
class InterfaceFamily:
    interface_family_id: str
    name: str
    metadata: Dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        require_identifier(self.interface_family_id, "interface_family_id")
        require_identifier(self.name, "Interface family name")


@dataclass(frozen=True)
class Design:
    """Nominal construction shared by one or more manufactured specimens."""

    design_id: str
    face_section_family_id: str
    core_family_id: Optional[str] = None
    interface_family_id: Optional[str] = None
    nominal_geometry: Dict[str, float] = field(default_factory=dict, compare=False)
    metadata: Dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        require_identifier(self.design_id, "design_id")
        require_identifier(self.face_section_family_id, "face_section_family_id")
        for field_name, value in (
            ("core_family_id", self.core_family_id),
            ("interface_family_id", self.interface_family_id),
        ):
            if value is not None:
                require_identifier(value, field_name)
        for name, value in self.nominal_geometry.items():
            if not math.isfinite(float(value)) or float(value) <= 0.0:
                raise ValueError(f"Nominal geometry {name!r} must be positive and finite.")


@dataclass(frozen=True)
class PrimaryMeasurement:
    """An independently measured quantity and its measurement prior."""

    name: str
    value: float
    standard_uncertainty: float
    unit: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        require_identifier(self.name, "Primary measurement name")
        normalized_name = self.name.strip().lower().replace(" ", "_")
        if normalized_name in _DERIVED_MEASUREMENT_NAMES:
            raise ValueError(
                f"{self.name!r} is derived and cannot be registered as an independent "
                "primary measurement prior."
            )
        if not math.isfinite(float(self.value)) or float(self.value) <= 0.0:
            raise ValueError("Primary measurement value must be positive and finite.")
        if (
            not math.isfinite(float(self.standard_uncertainty))
            or float(self.standard_uncertainty) < 0.0
        ):
            raise ValueError(
                "Primary measurement uncertainty must be non-negative and finite."
            )


@dataclass(frozen=True)
class PhysicalSpecimen:
    """One manufactured object; distinct from its nominal design."""

    physical_specimen_id: str
    design_id: str
    primary_measurements: Tuple[PrimaryMeasurement, ...] = ()
    metadata: Dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        require_identifier(self.physical_specimen_id, "physical_specimen_id")
        require_identifier(self.design_id, "design_id")
        object.__setattr__(self, "primary_measurements", tuple(self.primary_measurements))
        names = [measurement.name for measurement in self.primary_measurements]
        if len(names) != len(set(names)):
            raise ValueError(
                f"Physical specimen {self.physical_specimen_id!r} has duplicate "
                "primary measurement names."
            )

    def measurement_value(self, name: str) -> float:
        for measurement in self.primary_measurements:
            if measurement.name == name:
                return float(measurement.value)
        raise ValueError(
            f"Physical specimen {self.physical_specimen_id!r} has no primary "
            f"measurement {name!r}."
        )

    @property
    def areal_mass(self) -> float:
        """Derived μ = m / (L W); it is never stored as an independent prior."""

        return self.measurement_value("m") / (
            self.measurement_value("L") * self.measurement_value("W")
        )

    @property
    def face_offset(self) -> float:
        """Derived d = (H_total - h_face) / 2."""

        value = (
            self.measurement_value("H_total") - self.measurement_value("h_face")
        ) / 2.0
        if value <= 0.0:
            raise ValueError("Derived face offset must be positive.")
        return value


@dataclass(frozen=True)
class TestRun:
    """One modal measurement session for one physical specimen."""

    test_run_id: str
    physical_specimen_id: str
    metadata: Dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        require_identifier(self.test_run_id, "test_run_id")
        require_identifier(self.physical_specimen_id, "physical_specimen_id")
