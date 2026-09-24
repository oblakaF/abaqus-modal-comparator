"""Assignment-invariant two-mode residuals for real modal identification.

Shape/subspace evidence is an admissibility gate only.  It is deliberately
absent from the numerical least-squares residual returned by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Sequence, Tuple

import numpy as np


SP13_PRIMARY_OBSERVABLE_IDS = ("A7", "A12", "A8_A9_CENTER", "A8_A9_SPLITTING")
SP13_FITTED_PARAMETER_IDS = ("effective_face_Ex", "effective_face_Ey", "effective_face_Gxy")


class FamilyResidualValidationError(ValueError):
    """The family residual inputs are incomplete or non-physical."""


class FamilyIdentityError(FamilyResidualValidationError):
    """The candidate FE eigenspace is not the frozen physical family."""


@dataclass(frozen=True)
class TwoModeFamilyFeatures:
    center: float
    squared_splitting: float


@dataclass(frozen=True)
class FamilyIdentityEvidence:
    squared_canonical_correlations: Tuple[float, float]
    principal_angles_degrees: Tuple[float, float]
    baseline_member_ids: Tuple[int, int]
    candidate_member_ids: Tuple[int, int]

    @property
    def minimum_squared_canonical_correlation(self) -> float:
        return min(self.squared_canonical_correlations)

    @property
    def maximum_principal_angle_degrees(self) -> float:
        return max(self.principal_angles_degrees)


@dataclass(frozen=True)
class FamilyIdentityGate:
    minimum_squared_canonical_correlation: float
    maximum_principal_angle_degrees: float

    def __post_init__(self) -> None:
        correlation = float(self.minimum_squared_canonical_correlation)
        angle = float(self.maximum_principal_angle_degrees)
        if not math.isfinite(correlation) or not 0.0 <= correlation <= 1.0:
            raise FamilyResidualValidationError(
                "minimum_squared_canonical_correlation must be in [0, 1]."
            )
        if not math.isfinite(angle) or not 0.0 <= angle <= 90.0:
            raise FamilyResidualValidationError(
                "maximum_principal_angle_degrees must be in [0, 90]."
            )
        object.__setattr__(self, "minimum_squared_canonical_correlation", correlation)
        object.__setattr__(self, "maximum_principal_angle_degrees", angle)

    def accepts(self, evidence: FamilyIdentityEvidence) -> bool:
        return bool(
            evidence.minimum_squared_canonical_correlation
            >= self.minimum_squared_canonical_correlation
            and evidence.maximum_principal_angle_degrees
            <= self.maximum_principal_angle_degrees
        )


@dataclass(frozen=True)
class SP13PrimaryResidualEvaluation:
    residuals: np.ndarray
    standardized_residuals: np.ndarray
    objective: float
    fe_family_features: TwoModeFamilyFeatures
    experimental_family_features: TwoModeFamilyFeatures
    family_identity_evidence: FamilyIdentityEvidence
    fe_family_member_frequencies_hz: Tuple[float, float]
    experimental_family_member_frequencies_hz: Tuple[float, float]

    def log_record(self) -> Mapping[str, object]:
        return {
            "observable_ids": SP13_PRIMARY_OBSERVABLE_IDS,
            "fe_family_member_frequencies_hz": self.fe_family_member_frequencies_hz,
            "experimental_family_member_frequencies_hz": (
                self.experimental_family_member_frequencies_hz
            ),
            "fe_family_center": self.fe_family_features.center,
            "fe_family_squared_splitting": self.fe_family_features.squared_splitting,
            "experimental_family_center": self.experimental_family_features.center,
            "experimental_family_squared_splitting": (
                self.experimental_family_features.squared_splitting
            ),
            "minimum_squared_canonical_correlation": (
                self.family_identity_evidence.minimum_squared_canonical_correlation
            ),
            "maximum_principal_angle_degrees": (
                self.family_identity_evidence.maximum_principal_angle_degrees
            ),
            "baseline_family_member_ids": self.family_identity_evidence.baseline_member_ids,
            "candidate_family_member_ids": self.family_identity_evidence.candidate_member_ids,
            "residuals": tuple(float(value) for value in self.residuals),
            "standardized_residuals": tuple(
                float(value) for value in self.standardized_residuals
            ),
            "objective": self.objective,
            "subspace_metrics_used_in_objective": False,
        }


def _positive_pair(values: Sequence[float], name: str) -> Tuple[float, float]:
    pair = tuple(float(value) for value in values)
    if len(pair) != 2:
        raise FamilyResidualValidationError(f"{name} requires exactly two frequencies.")
    if not all(math.isfinite(value) and value > 0.0 for value in pair):
        raise FamilyResidualValidationError(f"{name} frequencies must be positive and finite.")
    return pair


def two_mode_family_features(frequencies_hz: Sequence[float]) -> TwoModeFamilyFeatures:
    """Return the exact REAL-2D permutation-invariant ``m`` and ``s2`` features."""

    first, second = _positive_pair(frequencies_hz, "two-mode family")
    log_first, log_second = math.log(first), math.log(second)
    return TwoModeFamilyFeatures(
        center=0.5 * (log_first + log_second),
        squared_splitting=0.25 * (log_first - log_second) ** 2,
    )


def scalar_log_frequency_residual(fe_frequency_hz: float, experimental_frequency_hz: float) -> float:
    fe, exp = _positive_pair((fe_frequency_hz, experimental_frequency_hz), "scalar residual")
    return math.log(fe / exp)


def family_frequency_residual(
    fe_frequencies_hz: Sequence[float], experimental_frequencies_hz: Sequence[float]
) -> tuple[np.ndarray, TwoModeFamilyFeatures, TwoModeFamilyFeatures]:
    fe = two_mode_family_features(fe_frequencies_hz)
    experimental = two_mode_family_features(experimental_frequencies_hz)
    return (
        np.asarray(
            [
                fe.center - experimental.center,
                fe.squared_splitting - experimental.squared_splitting,
            ],
            dtype=float,
        ),
        fe,
        experimental,
    )


def two_mode_subspace_evidence(
    baseline_mode_vectors: np.ndarray,
    candidate_mode_vectors: np.ndarray,
    *,
    baseline_member_ids: Sequence[int],
    candidate_member_ids: Sequence[int],
) -> FamilyIdentityEvidence:
    baseline = np.asarray(baseline_mode_vectors, dtype=float)
    candidate = np.asarray(candidate_mode_vectors, dtype=float)
    if baseline.ndim != 2 or candidate.ndim != 2 or baseline.shape != candidate.shape:
        raise FamilyResidualValidationError(
            "Baseline and candidate family vectors must have the same 2 x N shape."
        )
    if baseline.shape[0] != 2 or baseline.shape[1] < 2:
        raise FamilyResidualValidationError("A two-mode subspace requires a 2 x N array.")
    if not np.isfinite(baseline).all() or not np.isfinite(candidate).all():
        raise FamilyResidualValidationError("Family vectors must be finite.")
    baseline_ids = tuple(int(value) for value in baseline_member_ids)
    candidate_ids = tuple(int(value) for value in candidate_member_ids)
    if len(baseline_ids) != 2 or len(candidate_ids) != 2:
        raise FamilyResidualValidationError("Family member identity requires two IDs per basis.")
    qb = np.linalg.qr(baseline.T)[0][:, :2]
    qc = np.linalg.qr(candidate.T)[0][:, :2]
    singular = np.linalg.svd(qb.T @ qc, compute_uv=False)
    squared = np.clip(singular**2, 0.0, 1.0)
    angles = np.degrees(np.arccos(np.clip(singular, -1.0, 1.0)))
    return FamilyIdentityEvidence(
        squared_canonical_correlations=tuple(float(value) for value in squared),
        principal_angles_degrees=tuple(float(value) for value in angles),
        baseline_member_ids=baseline_ids,
        candidate_member_ids=candidate_ids,
    )


def evaluate_sp13_primary_residual(
    *,
    fe_A7_hz: float,
    fe_A12_hz: float,
    fe_A8_A9_hz: Sequence[float],
    experimental_A7_hz: float,
    experimental_A12_hz: float,
    experimental_A8_A9_hz: Sequence[float],
    standard_deviations: Sequence[float],
    family_identity_evidence: FamilyIdentityEvidence,
    family_identity_gate: FamilyIdentityGate,
) -> SP13PrimaryResidualEvaluation:
    """Evaluate SP13 M0; shape evidence gates but never changes the objective."""

    if not family_identity_gate.accepts(family_identity_evidence):
        raise FamilyIdentityError(
            "A8/A9 candidate failed the frozen-baseline subspace identity gate."
        )
    fe_pair = _positive_pair(fe_A8_A9_hz, "FE A8/A9 family")
    exp_pair = _positive_pair(experimental_A8_A9_hz, "experimental A8/A9 family")
    family_residual, fe_features, experimental_features = family_frequency_residual(
        fe_pair, exp_pair
    )
    residuals = np.asarray(
        [
            scalar_log_frequency_residual(fe_A7_hz, experimental_A7_hz),
            scalar_log_frequency_residual(fe_A12_hz, experimental_A12_hz),
            family_residual[0],
            family_residual[1],
        ],
        dtype=float,
    )
    sigmas = np.asarray(standard_deviations, dtype=float)
    if sigmas.shape != (4,) or not np.isfinite(sigmas).all() or np.any(sigmas <= 0.0):
        raise FamilyResidualValidationError(
            "SP13 M0 requires four positive finite standard deviations."
        )
    standardized = residuals / sigmas
    objective = float(standardized @ standardized)
    return SP13PrimaryResidualEvaluation(
        residuals=residuals,
        standardized_residuals=standardized,
        objective=objective,
        fe_family_features=fe_features,
        experimental_family_features=experimental_features,
        family_identity_evidence=family_identity_evidence,
        fe_family_member_frequencies_hz=fe_pair,
        experimental_family_member_frequencies_hz=exp_pair,
    )


__all__ = [
    "FamilyIdentityError",
    "FamilyIdentityEvidence",
    "FamilyIdentityGate",
    "FamilyResidualValidationError",
    "SP13_FITTED_PARAMETER_IDS",
    "SP13_PRIMARY_OBSERVABLE_IDS",
    "SP13PrimaryResidualEvaluation",
    "TwoModeFamilyFeatures",
    "evaluate_sp13_primary_residual",
    "family_frequency_residual",
    "scalar_log_frequency_residual",
    "two_mode_family_features",
    "two_mode_subspace_evidence",
]
