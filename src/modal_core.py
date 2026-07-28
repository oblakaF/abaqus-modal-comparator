from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np


@dataclass
class ModeShape:
    number: int
    frequency_hz: float
    node_ids: np.ndarray
    coordinates: np.ndarray
    vectors: np.ndarray
    damping_ratio: Optional[float] = None
    modal_mass: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.node_ids = np.asarray(self.node_ids, dtype=object)
        self.coordinates = np.asarray(self.coordinates, dtype=float)
        self.vectors = np.asarray(self.vectors)
        if self.coordinates.ndim != 2 or self.coordinates.shape[1] != 3:
            raise ValueError("Mode coordinates must have shape (N, 3).")
        if self.vectors.ndim != 2 or self.vectors.shape[1] != 3:
            raise ValueError("Mode vectors must have shape (N, 3).")
        if len(self.node_ids) != len(self.coordinates) or len(self.node_ids) != len(self.vectors):
            raise ValueError("Node ids, coordinates, and vectors must have equal lengths.")
        if not np.isfinite(self.frequency_hz) or self.frequency_hz <= 0:
            raise ValueError("Mode frequency must be a positive finite value.")


@dataclass
class ModalDataset:
    source_name: str
    source_path: Path
    modes: List[ModeShape]
    metadata: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)

    def sorted_modes(self) -> List[ModeShape]:
        return sorted(self.modes, key=lambda mode: mode.number)


@dataclass(eq=False)
class GeometryMatch:
    """One geometry transform candidate with identity equality.

    The full transformed FE coordinates are populated only for the selected
    candidate, preventing one large coordinate copy per trial orientation.
    """

    experimental_to_abaqus: np.ndarray
    distances: np.ndarray
    rotation: np.ndarray
    coordinate_scale: float
    translation: np.ndarray
    normalized_rms_distance: float
    matched_fraction: float
    transformed_abaqus_coordinates: Optional[np.ndarray] = None


@dataclass
class ModePairResult:
    abaqus_mode: int
    experimental_mode: int
    abaqus_frequency_hz: float
    experimental_frequency_hz: float
    frequency_error_percent: float
    mac: Optional[float]
    status: str
    order_changed: bool
    mapped_points: int
    abaqus_vector: np.ndarray
    experimental_vector: np.ndarray
    coordinates: np.ndarray


@dataclass
class ComparisonResult:
    abaqus: ModalDataset
    experimental: ModalDataset
    geometry: GeometryMatch
    pairs: List[ModePairResult]
    mac_matrix: np.ndarray
    frequency_error_matrix: np.ndarray
    abaqus_mode_numbers: List[int]
    experimental_mode_numbers: List[int]
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


def modal_assurance_criterion(vector_a: np.ndarray, vector_b: np.ndarray) -> Optional[float]:
    a = np.asarray(vector_a).reshape(-1)
    b = np.asarray(vector_b).reshape(-1)
    valid = np.isfinite(a.real) & np.isfinite(a.imag) & np.isfinite(b.real) & np.isfinite(b.imag)
    a = a[valid]
    b = b[valid]
    if a.size == 0 or b.size == 0:
        return None
    norm_a = np.vdot(a, a).real
    norm_b = np.vdot(b, b).real
    if norm_a <= 1e-30 or norm_b <= 1e-30:
        return None
    value = abs(np.vdot(a, b)) ** 2 / (norm_a * norm_b)
    return float(np.clip(value.real, 0.0, 1.0))


def phase_align(reference: np.ndarray, candidate: np.ndarray) -> np.ndarray:
    ref = np.asarray(reference).reshape(-1)
    cand = np.asarray(candidate).reshape(-1)
    denominator = np.vdot(cand, cand)
    if abs(denominator) <= 1e-30:
        return np.asarray(candidate)
    coefficient = np.vdot(cand, ref) / denominator
    if abs(coefficient) <= 1e-30:
        return np.asarray(candidate)
    return np.asarray(candidate) * (coefficient / abs(coefficient))


def frequency_error_percent(calculated: float, experimental: float) -> float:
    """Compatibility facade for the single reviewed signed-error implementation."""
    from reviewed_core import frequency_error_percent as reviewed_frequency_error

    return reviewed_frequency_error(calculated, experimental)


def compare_modal_datasets(*args, **kwargs):
    """Compatibility facade; no legacy correlation algorithm remains here."""
    from quality_control_reviewed import compare_modal_datasets_with_quality_control

    return compare_modal_datasets_with_quality_control(*args, **kwargs)
