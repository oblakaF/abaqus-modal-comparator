"""Registration uncertainty diagnostic — Auto-ID M2.4 (SPEC §11; D-007).

Perturbs the *nominal* physical registration only within the passport's measured
calibration uncertainty (deterministic set: ±translation along FE X and Y, ±scale,
±in-plane rotation) and reports, per accepted pair, the nominal MAC and its range.

It is a diagnostic only.  It never selects, returns or feeds back a "best" perturbation:
the nominal registration is unchanged and is the only registration in use.  Missing
uncertainty components are NOT_AVAILABLE and are never invented.

``registration_limited`` (SPEC §11) is set when a physically allowed perturbation makes
an accepted pair's MAC cross the production threshold 0.8.  The second trigger in SPEC
§11 — a change of the accepted pairing — needs the M4 IdentificationPairingPolicy and is
reported as ``DEFERRED_M4``; it is not emulated here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import math
from typing import Mapping, Sequence

import numpy as np
from scipy.spatial import cKDTree

from domain.registration import FrozenRegistration
from domain.specimen_manifest import GeometryUncertainty
from modal_core import ModalDataset, modal_assurance_criterion

from .physical_registration import FEGeometry


PRODUCTION_MAC_THRESHOLD = 0.8  # SPEC §3 / §11
_COMPONENTS = {"U1": 0, "U2": 1, "U3": 2}


class UncertaintyStatus(str, Enum):
    EVALUATED = "EVALUATED"
    PARTIAL = "PARTIAL"  # some uncertainty components are not measured
    NOT_AVAILABLE = "NOT_AVAILABLE"


@dataclass(frozen=True)
class Perturbation:
    name: str
    translation_mm: tuple[float, float] = (0.0, 0.0)
    scale_rel: float = 0.0
    rotation_deg: float = 0.0


@dataclass(frozen=True)
class PerturbationOutcome:
    perturbation: Perturbation
    mapped_ids_sha256: str
    remapped_points: int


@dataclass(frozen=True)
class PairMacRange:
    experimental_mode: int
    fe_mode: int
    nominal_mac: float
    minimum_mac: float
    maximum_mac: float
    per_perturbation: tuple[tuple[str, float], ...]
    crosses_threshold: bool


@dataclass(frozen=True)
class RegistrationUncertaintyReport:
    status: UncertaintyStatus
    nominal_registration_hash: str  # the registration in use; never replaced
    available_components: tuple[str, ...]
    unavailable_components: tuple[str, ...]
    perturbations: tuple[PerturbationOutcome, ...]
    pairs: tuple[PairMacRange, ...]
    registration_limited: bool | None  # None: not evaluable (no measured uncertainty)
    mac_threshold_crossing_evaluated: bool
    pairing_change_evaluation: str  # "DEFERRED_M4"
    threshold: float = PRODUCTION_MAC_THRESHOLD


def perturbation_set(uncertainty: GeometryUncertainty) -> tuple[tuple[Perturbation, ...], tuple[str, ...]]:
    """Deterministic ±σ set for the measured components only; the rest are listed as unavailable."""

    perturbations = []
    if uncertainty.translation_mm is not None:
        step = float(uncertainty.translation_mm)
        perturbations += [Perturbation("+translation_x", (step, 0.0)), Perturbation("-translation_x", (-step, 0.0)),
                          Perturbation("+translation_y", (0.0, step)), Perturbation("-translation_y", (0.0, -step))]
    if uncertainty.scale_rel is not None:
        perturbations += [Perturbation("+scale", scale_rel=float(uncertainty.scale_rel)),
                          Perturbation("-scale", scale_rel=-float(uncertainty.scale_rel))]
    if uncertainty.rotation_deg is not None:
        perturbations += [Perturbation("+rotation", rotation_deg=float(uncertainty.rotation_deg)),
                          Perturbation("-rotation", rotation_deg=-float(uncertainty.rotation_deg))]
    return tuple(perturbations), uncertainty.missing


def _experimental_in_fe(registration: FrozenRegistration, coordinates: np.ndarray) -> np.ndarray:
    rotation = np.asarray(registration.rotation, float)
    scales = np.asarray(registration.coordinate_scales, float)
    translation = np.asarray(registration.translation, float)
    return ((np.asarray(coordinates, float) - translation) / scales) @ rotation.T


def _perturbed_points(points: np.ndarray, perturbation: Perturbation) -> np.ndarray:
    """Apply a perturbation in the FE frame about the grid centroid (in-plane rotation about FE Z)."""
    centre = points.mean(axis=0)
    local = points - centre
    angle = math.radians(perturbation.rotation_deg)
    turn = np.array([[math.cos(angle), -math.sin(angle), 0.0], [math.sin(angle), math.cos(angle), 0.0], [0, 0, 1.0]])
    local = (local @ turn.T) / (1.0 + perturbation.scale_rel)
    return local + centre + np.array([perturbation.translation_mm[0], perturbation.translation_mm[1], 0.0])


def _map(points: np.ndarray, fe: FEGeometry, surface_indices: np.ndarray) -> list[str]:
    tree = cKDTree(fe.coordinates[surface_indices])
    _, nearest = tree.query(points)
    return [str(value) for value in fe.node_ids[surface_indices[np.asarray(nearest, dtype=int)]]]


def _pair_mac(registration, fe_modes: Mapping[int, Mapping[str, np.ndarray]], experimental: ModalDataset,
              mapped_ids: Sequence[str], exp_mode: int, fe_mode: int, components: list[int]) -> float:
    rotation = np.asarray(registration.rotation, float)
    exp = {mode.number: mode for mode in experimental.modes}[exp_mode]
    fe_vectors = np.array([fe_modes[fe_mode][node_id] for node_id in mapped_ids], dtype=complex) @ rotation
    value = modal_assurance_criterion(fe_vectors[:, components], np.asarray(exp.vectors)[:, components])
    return float("nan") if value is None else float(value)


def evaluate_registration_uncertainty(
    registration: FrozenRegistration,
    uncertainty: GeometryUncertainty,
    fe: FEGeometry,
    surface_node_ids: Sequence[str],
    experimental: ModalDataset,
    fe_mode_shapes: Mapping[int, Mapping[str, np.ndarray]],
    accepted_pairs: Sequence[tuple[int, int]],
    measured_dofs: Sequence[str],
    threshold: float = PRODUCTION_MAC_THRESHOLD,
) -> RegistrationUncertaintyReport:
    """MAC range of each accepted (experimental, FE) pair under physically allowed perturbations.

    ``fe_mode_shapes`` maps FE mode number -> {"INSTANCE:label": (U1, U2, U3)}.  The nominal
    registration is never altered and no perturbation is ever returned as a registration.
    """

    perturbations, unavailable = perturbation_set(uncertainty)
    components = [_COMPONENTS[name] for name in measured_dofs]
    lookup = {value: index for index, value in enumerate(fe.node_ids.tolist())}
    surface_indices = np.array(sorted(lookup[node] for node in surface_node_ids), dtype=int)
    nominal_ids = list(registration.mapped_fe_node_ids)
    nominal_points = _experimental_in_fe(registration, experimental.sorted_modes()[0].coordinates)

    outcomes, mapped_sets = [], []
    for perturbation in perturbations:
        mapped = _map(_perturbed_points(nominal_points, perturbation), fe, surface_indices)
        mapped_sets.append(mapped)
        outcomes.append(PerturbationOutcome(
            perturbation,
            hashlib.sha256("\n".join(mapped).encode("utf-8")).hexdigest(),
            int(sum(a != b for a, b in zip(mapped, nominal_ids))),
        ))

    pairs, limited = [], False
    for exp_mode, fe_mode in accepted_pairs:
        nominal = _pair_mac(registration, fe_mode_shapes, experimental, nominal_ids, exp_mode, fe_mode, components)
        values = tuple((outcome.perturbation.name,
                        _pair_mac(registration, fe_mode_shapes, experimental, mapped, exp_mode, fe_mode, components))
                       for outcome, mapped in zip(outcomes, mapped_sets))
        allowed = [nominal] + [value for _, value in values]
        crosses = bool(values) and min(allowed) < threshold <= max(allowed)
        limited |= crosses
        pairs.append(PairMacRange(int(exp_mode), int(fe_mode), nominal, min(allowed), max(allowed), values, crosses))

    if not perturbations:
        status = UncertaintyStatus.NOT_AVAILABLE
    elif unavailable:
        status = UncertaintyStatus.PARTIAL
    else:
        status = UncertaintyStatus.EVALUATED
    # A found crossing is conclusive; "not limited" needs every component evaluated.
    if limited:
        flag = True
    else:
        flag = False if status is UncertaintyStatus.EVALUATED else None
    return RegistrationUncertaintyReport(
        status=status,
        nominal_registration_hash=registration.registration_hash,
        available_components=uncertainty.available,
        unavailable_components=tuple(unavailable),
        perturbations=tuple(outcomes),
        pairs=tuple(pairs),
        registration_limited=flag,
        mac_threshold_crossing_evaluated=bool(perturbations),
        pairing_change_evaluation="DEFERRED_M4",
        threshold=threshold,
    )
