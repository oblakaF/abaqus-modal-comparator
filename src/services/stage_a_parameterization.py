"""Physically admissible Stage-A balanced-laminate parameterisation."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Tuple


def _finite(value: float, name: str) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite real number.") from exc
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite.")
    return normalized


def validate_balanced_d_matrix(
    d11: float,
    d22: float,
    d12: float,
    d66: float,
    *,
    r: float | None = None,
) -> None:
    """Validate the Stage-A balanced bending-stiffness invariants.

    Supplying ``r`` additionally proves that the matrix represents that exact
    Stage-A physical parameter, rather than merely some admissible ratio.
    """

    d11 = _finite(d11, "D11")
    d22 = _finite(d22, "D22")
    d12 = _finite(d12, "D12")
    d66 = _finite(d66, "D66")

    if d11 <= 0.0 or d22 <= 0.0:
        raise ValueError("D11 and D22 must be positive.")
    if d66 <= 0.0:
        raise ValueError("D66 must be positive.")
    if d11 != d22:
        raise ValueError("A balanced Stage-A matrix requires D11 == D22.")

    matrix_ratio = d12 / d11
    if not abs(matrix_ratio) < 1.0:
        raise ValueError(
            "The bending normal-block determinant D11*D22 - D12^2 "
            "must be positive."
        )

    if r is not None:
        r = _finite(r, "r")
        if not abs(r) < 1.0:
            raise ValueError("r must satisfy |r| < 1.")
        if d12 != r * d11:
            raise ValueError("A balanced Stage-A matrix requires D12 == r*D11.")


@dataclass(frozen=True)
class StageAParameterization:
    """One balanced Stage-A point in physical and unconstrained coordinates."""

    D: float
    D66: float
    r: float
    x1: float = field(init=False)
    x2: float = field(init=False)
    x3: float = field(init=False)
    D11: float = field(init=False)
    D22: float = field(init=False)
    D12: float = field(init=False)

    def __post_init__(self) -> None:
        d = _finite(self.D, "D")
        d66 = _finite(self.D66, "D66")
        r = _finite(self.r, "r")
        if d <= 0.0:
            raise ValueError("D must be positive.")
        if d66 <= 0.0:
            raise ValueError("D66 must be positive.")
        if not abs(r) < 1.0:
            raise ValueError("r must satisfy |r| < 1.")

        d12 = r * d
        if not math.isfinite(d12):
            raise ValueError("D12 = r*D must be finite.")

        object.__setattr__(self, "D", d)
        object.__setattr__(self, "D66", d66)
        object.__setattr__(self, "r", r)
        object.__setattr__(self, "x1", math.log(d))
        object.__setattr__(self, "x2", math.log(d66))
        object.__setattr__(self, "x3", math.atanh(r))
        object.__setattr__(self, "D11", d)
        object.__setattr__(self, "D22", d)
        object.__setattr__(self, "D12", d12)

        validate_balanced_d_matrix(d, d, d12, d66, r=r)

    @classmethod
    def from_physical(
        cls, D: float, D66: float, r: float
    ) -> "StageAParameterization":
        return cls(D=D, D66=D66, r=r)

    @classmethod
    def from_unconstrained(
        cls, x1: float, x2: float, x3: float
    ) -> "StageAParameterization":
        x1 = _finite(x1, "x1")
        x2 = _finite(x2, "x2")
        x3 = _finite(x3, "x3")
        try:
            d = math.exp(x1)
            d66 = math.exp(x2)
        except OverflowError as exc:
            raise ValueError(
                "The unconstrained variables must map to finite D and D66."
            ) from exc
        return cls(D=d, D66=d66, r=math.tanh(x3))

    @property
    def physical(self) -> Tuple[float, float, float]:
        return self.D, self.D66, self.r

    @property
    def unconstrained(self) -> Tuple[float, float, float]:
        return self.x1, self.x2, self.x3


def physical_to_unconstrained(
    D: float, D66: float, r: float
) -> Tuple[float, float, float]:
    """Convert validated ``(D, D66, r)`` to ``(x1, x2, x3)``."""

    return StageAParameterization.from_physical(D, D66, r).unconstrained


def unconstrained_to_physical(
    x1: float, x2: float, x3: float
) -> Tuple[float, float, float]:
    """Convert ``(x1, x2, x3)`` to validated ``(D, D66, r)``."""

    return StageAParameterization.from_unconstrained(x1, x2, x3).physical
