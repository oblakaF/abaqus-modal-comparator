"""Orthotropic elasticity of the nine Abaqus Engineering Constants — research track NINE-EC (Phase C).

Solver-independent and pure. It reuses ``EngineeringConstants`` (the nine values of one
``*Elastic, type=ENGINEERING CONSTANTS`` record, in Abaqus record order E1, E2, E3, ν12, ν13, ν23, G12, G13, G23)
and adds:

- the reciprocal (dependent) Poisson ratios ν21 = ν12·E2/E1, ν31 = ν13·E3/E1, ν32 = ν23·E3/E2. The Abaqus input
  ratios ν_ij (i < j) are the *input* ratios; the reciprocal ones are derived and never input;
- the 6×6 compliance and stiffness matrices in Abaqus Voigt order (11, 22, 33, 12, 13, 23), engineering shear strain;
- physical admissibility: finite positive moduli, the Abaqus stability conditions and a positive-definite compliance.
  An inadmissible set is refused before any FE job is prepared (``require_admissible``);
- the research parameter coordinates: x = ln p for the six positive moduli (E1, E2, E3, G12, G13, G23) and x = ν
  (linear, signed, dimensionless) for the three input Poisson ratios. ln ν is never used: ν may be zero or negative.

Material axes are not inferred here; a caller must state them from the model (never from MAC).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Mapping, Sequence

import numpy as np

from .forward_model_manifest import EngineeringConstants

NAMES: tuple[str, ...] = EngineeringConstants.names()  # E1, E2, E3, nu12, nu13, nu23, G12, G13, G23
MODULI: tuple[str, ...] = ("E1", "E2", "E3", "G12", "G13", "G23")
POISSON: tuple[str, ...] = ("nu12", "nu13", "nu23")
VOIGT_ORDER: tuple[str, ...] = ("11", "22", "33", "12", "13", "23")  # Abaqus order, engineering shear strain


class ElasticAdmissibilityError(ValueError):
    """The nine constants are not a physically admissible orthotropic material; nothing is solved."""

    def __init__(self, violations: Sequence[str]) -> None:
        super().__init__("inadmissible orthotropic constants: " + "; ".join(violations))
        self.violations = tuple(violations)


class CoordinateKind(str, Enum):
    LOG = "LOG"  # x = ln p (positive moduli); a step is a relative change of p
    LINEAR = "LINEAR"  # x = ν (signed Poisson ratio); a step is an absolute change of ν


COORDINATES: Mapping[str, CoordinateKind] = {name: (CoordinateKind.LINEAR if name in POISSON else CoordinateKind.LOG)
                                             for name in NAMES}
COORDINATE_UNITS: Mapping[str, str] = {name: ("ν (dimensionless, absolute)" if name in POISSON else "ln p")
                                       for name in NAMES}


def reciprocal_poisson(c: EngineeringConstants) -> dict[str, float]:
    """The dependent ratios ν21, ν31, ν32 (requires positive moduli)."""
    return {"nu21": c.nu12 * c.E2 / c.E1, "nu31": c.nu13 * c.E3 / c.E1, "nu32": c.nu23 * c.E3 / c.E2}


def compliance_matrix(c: EngineeringConstants) -> np.ndarray:
    """S (6×6) with ε = S σ, Abaqus Voigt order (11, 22, 33, 12, 13, 23), engineering shear strain."""
    s = np.zeros((6, 6))
    s[0, 0], s[1, 1], s[2, 2] = 1.0 / c.E1, 1.0 / c.E2, 1.0 / c.E3
    s[0, 1] = s[1, 0] = -c.nu12 / c.E1
    s[0, 2] = s[2, 0] = -c.nu13 / c.E1
    s[1, 2] = s[2, 1] = -c.nu23 / c.E2
    s[3, 3], s[4, 4], s[5, 5] = 1.0 / c.G12, 1.0 / c.G13, 1.0 / c.G23
    return s


@dataclass(frozen=True)
class AdmissibilityReport:
    admissible: bool
    violations: tuple[str, ...]
    reciprocal: Mapping[str, float]
    determinant_condition: float  # 1 − ν12ν21 − ν23ν32 − ν31ν13 − 2ν21ν32ν13 (must be > 0)
    min_normalised_compliance_eigenvalue: float  # of D^(−1/2) S D^(−1/2), D = diag(S); > 0 for a stable material

    def to_dict(self) -> dict:
        return {"admissible": self.admissible, "violations": list(self.violations),
                "reciprocal_poisson": dict(self.reciprocal), "determinant_condition": self.determinant_condition,
                "min_normalised_compliance_eigenvalue": self.min_normalised_compliance_eigenvalue}


def admissibility(c: EngineeringConstants) -> AdmissibilityReport:
    """All violated conditions (Abaqus *Elastic material stability for ENGINEERING CONSTANTS); never a partial check."""
    violations = []
    for name in MODULI:
        if not getattr(c, name) > 0.0:
            violations.append(f"{name} = {getattr(c, name):g} must be positive")
    if violations:  # the remaining conditions divide by the moduli
        return AdmissibilityReport(False, tuple(violations), {}, math.nan, math.nan)
    for nu, (a, b) in (("nu12", ("E1", "E2")), ("nu13", ("E1", "E3")), ("nu23", ("E2", "E3"))):
        limit = math.sqrt(getattr(c, a) / getattr(c, b))
        if not abs(getattr(c, nu)) < limit:
            violations.append(f"|{nu}| = {abs(getattr(c, nu)):g} must be below sqrt({a}/{b}) = {limit:g}")
    r = reciprocal_poisson(c)
    determinant = 1.0 - c.nu12 * r["nu21"] - c.nu23 * r["nu32"] - r["nu31"] * c.nu13 - 2.0 * r["nu21"] * r["nu32"] * c.nu13
    if not determinant > 0.0:
        violations.append(f"1 - ν12ν21 - ν23ν32 - ν31ν13 - 2ν21ν32ν13 = {determinant:g} must be positive")
    s = compliance_matrix(c)
    scale = 1.0 / np.sqrt(np.diag(s))
    eigenvalue = float(np.linalg.eigvalsh(s * np.outer(scale, scale)).min())
    if not eigenvalue > 0.0:
        violations.append(f"the compliance matrix is not positive definite (smallest normalised eigenvalue {eigenvalue:g})")
    return AdmissibilityReport(not violations, tuple(violations), r, determinant, eigenvalue)


def require_admissible(c: EngineeringConstants) -> EngineeringConstants:
    report = admissibility(c)
    if not report.admissible:
        raise ElasticAdmissibilityError(report.violations)
    return c


def stiffness_matrix(c: EngineeringConstants) -> np.ndarray:
    """C = S⁻¹ (6×6, Abaqus Voigt order) of an admissible material."""
    return np.linalg.inv(compliance_matrix(require_admissible(c)))


def constants_from(values: Mapping[str, float]) -> EngineeringConstants:
    """Nine named values (exactly the nine names) to EngineeringConstants; finite values are required."""
    if set(values) != set(NAMES):
        raise ValueError(f"exactly the nine constants {', '.join(NAMES)} are required.")
    return EngineeringConstants(**{name: values[name] for name in NAMES})


def to_coordinates(c: EngineeringConstants, names: Sequence[str] = NAMES) -> np.ndarray:
    """x: ln p for moduli, ν for Poisson ratios (requires positive moduli)."""
    out = []
    for name in names:
        value = getattr(c, name)
        if COORDINATES[name] is CoordinateKind.LOG:
            if not value > 0.0:
                raise ElasticAdmissibilityError([f"{name} = {value:g} must be positive"])
            out.append(math.log(value))
        else:
            out.append(value)
    return np.array(out, dtype=float)


def from_coordinates(base: EngineeringConstants, names: Sequence[str], x: Sequence[float]) -> EngineeringConstants:
    """Replace the listed constants of ``base`` from coordinates x; every other constant is kept exactly."""
    values = base.to_dict()
    for name, value in zip(names, x, strict=True):
        values[name] = math.exp(float(value)) if COORDINATES[name] is CoordinateKind.LOG else float(value)
    return constants_from(values)
