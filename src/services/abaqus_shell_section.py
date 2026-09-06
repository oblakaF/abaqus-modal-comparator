"""Deterministic Abaqus shell-section representation for Stage A.

The keyword serialization is deliberately isolated here so PR-5 can adjust it
after validation against a real Abaqus installation without affecting the
parameterisation or section data model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Tuple

from .stage_a_parameterization import StageAParameterization


def _finite(value: float, name: str) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite real number.") from exc
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite.")
    return normalized


@dataclass(frozen=True)
class SectionStiffnessBlock:
    """Independent entries of a symmetric 3x3 shell stiffness block."""

    c11: float
    c12: float
    c22: float
    c16: float
    c26: float
    c66: float

    def __post_init__(self) -> None:
        for name in ("c11", "c12", "c22", "c16", "c26", "c66"):
            object.__setattr__(self, name, _finite(getattr(self, name), name))

    @classmethod
    def zero(cls) -> "SectionStiffnessBlock":
        return cls(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    @property
    def abaqus_values(self) -> Tuple[float, float, float, float, float, float]:
        return self.c11, self.c12, self.c22, self.c16, self.c26, self.c66


@dataclass(frozen=True)
class TransverseShearStiffness:
    """Explicit fixed transverse-shear stiffness, independent of the D block."""

    k11: float
    k12: float
    k22: float

    def __post_init__(self) -> None:
        for name in ("k11", "k12", "k22"):
            object.__setattr__(self, name, _finite(getattr(self, name), name))

    @property
    def abaqus_values(self) -> Tuple[float, float, float]:
        """Abaqus data-line order: K11, K22, K12."""

        return self.k11, self.k22, self.k12


@dataclass(frozen=True)
class StageAShellSectionConfiguration:
    """Fixed inputs and the explicit symmetric-layup assumption for Stage A."""

    elset: str
    A: SectionStiffnessBlock
    transverse_shear: TransverseShearStiffness
    B: SectionStiffnessBlock = field(default_factory=SectionStiffnessBlock.zero)
    density: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.elset, str) or not self.elset.strip():
            raise ValueError("elset must be a non-empty string.")
        if any(character in self.elset for character in (",", "\r", "\n")):
            raise ValueError("elset cannot contain commas or line breaks.")
        object.__setattr__(self, "elset", self.elset.strip())
        if self.B != SectionStiffnessBlock.zero():
            raise ValueError("Stage A requires the complete B block to be zero.")
        if self.density is not None:
            density = _finite(self.density, "density")
            if density <= 0.0:
                raise ValueError("density must be positive when supplied.")
            object.__setattr__(self, "density", density)


@dataclass(frozen=True)
class AbaqusShellGeneralSection:
    """Complete data written by the Stage-A Abaqus section renderer."""

    elset: str
    A: SectionStiffnessBlock
    B: SectionStiffnessBlock
    D: SectionStiffnessBlock
    transverse_shear: TransverseShearStiffness
    density: float | None = None

    @property
    def section_stiffness_values(self) -> Tuple[float, ...]:
        """Abaqus packed symmetric 6x6 order, split 8/8/5 when rendered.

        Abaqus packs the upper triangle by successive generalized-strain
        columns.  The membrane-bending block is therefore interleaved with
        the D block; it is not an ``A + B + D`` concatenation.  Stage A uses a
        symmetric B block, so its three off-diagonal values appear twice in
        the general 21-value representation.
        """

        a = self.A
        b = self.B
        d = self.D
        return (
            a.c11,
            a.c12,
            a.c22,
            a.c16,
            a.c26,
            a.c66,
            b.c11,
            b.c12,
            b.c16,
            d.c11,
            b.c12,
            b.c22,
            b.c26,
            d.c12,
            d.c22,
            b.c16,
            b.c26,
            b.c66,
            d.c16,
            d.c26,
            d.c66,
        )


def build_stage_a_shell_section(
    parameters: StageAParameterization,
    configuration: StageAShellSectionConfiguration,
) -> AbaqusShellGeneralSection:
    """Insert Stage-A D values literally; keep caller-supplied A and shear."""

    d_block = SectionStiffnessBlock(
        c11=parameters.D11,
        c12=parameters.D12,
        c22=parameters.D22,
        c16=0.0,
        c26=0.0,
        c66=parameters.D66,
    )
    return AbaqusShellGeneralSection(
        elset=configuration.elset,
        A=configuration.A,
        B=configuration.B,
        D=d_block,
        transverse_shear=configuration.transverse_shear,
        density=configuration.density,
    )


def _format_number(value: float) -> str:
    """Locale-independent, round-trip-safe binary64 formatting."""

    return format(_finite(value, "section stiffness value"), ".17g")


def render_abaqus_shell_general_section(
    section: AbaqusShellGeneralSection,
) -> str:
    """Render isolated Abaqus keyword text with deterministic line wrapping."""

    values = section.section_stiffness_values
    stiffness_lines = (
        values[0:8],
        values[8:16],
        values[16:21],
    )
    keyword = f"*SHELL GENERAL SECTION, ELSET={section.elset}"
    if section.density is not None:
        keyword += f", DENSITY={_format_number(section.density)}"
    lines = [keyword]
    lines.extend(", ".join(_format_number(value) for value in row) for row in stiffness_lines)
    lines.append("*TRANSVERSE SHEAR STIFFNESS")
    lines.append(
        ", ".join(_format_number(value) for value in section.transverse_shear.abaqus_values)
    )
    return "\n".join(lines) + "\n"


def generate_stage_a_shell_general_section(
    parameters: StageAParameterization,
    configuration: StageAShellSectionConfiguration,
) -> str:
    """Build and render a deterministic Stage-A general shell section."""

    return render_abaqus_shell_general_section(
        build_stage_a_shell_section(parameters, configuration)
    )
