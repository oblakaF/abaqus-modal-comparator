"""Physical modal-family classifier and family holdouts — Auto-ID M4.3 (SPEC §12.2–12.3; D-010).

Works on FE shapes of the outer surface: in-plane node coordinates (x, y) and the
out-of-plane component.  Continuous reflection parities about the panel mid-lines,

    P_x = φᵀ R_x φ / φᵀ φ,   P_y = φᵀ R_y φ / φᵀ φ,

use nearest-mirror-node mapping (P ≈ +1 even, ≈ −1 odd, in between mixed).  Near-square
panels also get the parities about both diagonals.  Nodal lines are counted as sign
changes along grid rows and columns.  Holdouts are chosen by physical family, never by
FE mode number.

SPEC §12.2 fixes the quantities but no numeric thresholds; the thresholds live in an
explicit, hashed ``FamilyClassifierPolicy`` marked provisional.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Optional, Sequence

import numpy as np
from scipy.interpolate import griddata
from scipy.spatial import cKDTree


class FamilyClassificationError(ValueError):
    """A shape cannot be classified reliably (for example, too few mirror nodes)."""


@dataclass(frozen=True)
class FamilyClassifierPolicy:
    policy_id: str
    parity_threshold: float  # |P| at or above this is a definite even/odd parity
    mirror_tolerance: float  # largest mirror-node distance, as a fraction of min(Lx, Ly)
    minimum_mirror_coverage: float  # fraction of nodes that must have a mirror node
    near_square_tolerance: float  # |Lx − Ly| / max(Lx, Ly) at or below this: diagonal parities too
    nodal_grid_points: int  # nodal lines are counted on an n × n resampling grid
    nodal_amplitude_floor: float  # |w| below this fraction of max|w| is treated as zero

    def __post_init__(self) -> None:
        for name in ("parity_threshold", "mirror_tolerance", "minimum_mirror_coverage", "near_square_tolerance",
                     "nodal_amplitude_floor"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0.0 < value < 1.0:
                raise ValueError(f"{name} must be in (0, 1).")
        if isinstance(self.nodal_grid_points, bool) or not isinstance(self.nodal_grid_points, int) \
                or self.nodal_grid_points < 9:
            raise ValueError("nodal_grid_points must be an integer of at least 9.")

    @property
    def policy_hash(self) -> str:
        encoded = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


# Provisional (SPEC §12.2 gives no numbers): reviewed with M4.3, revisited on real shapes.
PROVISIONAL_FAMILY_CLASSIFIER = FamilyClassifierPolicy(
    policy_id="auto-id/modal-family/v1-provisional",
    parity_threshold=0.80,
    mirror_tolerance=0.02,
    minimum_mirror_coverage=0.95,
    near_square_tolerance=0.05,
    nodal_grid_points=41,
    nodal_amplitude_floor=0.05,
)


class Parity(str, Enum):
    EVEN = "E"
    ODD = "O"
    MIXED = "M"


@dataclass(frozen=True)
class ModeFamily:
    p_x: float
    p_y: float
    p_diagonal: Optional[float]  # about u = v (normalised), near-square panels only
    p_antidiagonal: Optional[float]  # about u = −v
    parity_x: Parity
    parity_y: Parity
    nodal_lines_x: int  # sign changes moving along x (nodal lines crossing the x direction)
    nodal_lines_y: int
    policy_hash: str

    @property
    def key(self) -> str:
        """Family identity used for holdouts: parities and nodal-line counts (never a mode number)."""
        return f"Px:{self.parity_x.value}|Py:{self.parity_y.value}|nx:{self.nodal_lines_x}|ny:{self.nodal_lines_y}"

    @property
    def torsion_dominated(self) -> bool:
        """Approximately odd-odd about both mid-lines (SPEC §12.3)."""
        return self.parity_x is Parity.ODD and self.parity_y is Parity.ODD


def _parity_class(value: float, policy: FamilyClassifierPolicy) -> Parity:
    if value >= policy.parity_threshold:
        return Parity.EVEN
    if value <= -policy.parity_threshold:
        return Parity.ODD
    return Parity.MIXED


def _mirror_parity(normalised: np.ndarray, values: np.ndarray, mirrored: np.ndarray, tolerance: float,
                   policy: FamilyClassifierPolicy) -> float:
    distance, index = cKDTree(normalised).query(mirrored)
    matched = distance <= tolerance
    if matched.mean() < policy.minimum_mirror_coverage:
        raise FamilyClassificationError(
            f"only {matched.mean():.1%} of surface nodes have a mirror node; the mesh is not symmetric enough.")
    numerator = float(np.dot(values[matched], values[index[matched]]))
    denominator = float(np.dot(values[matched], values[matched]))
    if denominator <= 0.0:
        raise FamilyClassificationError("the shape is zero on the matched nodes.")
    return numerator / denominator


def _sign_changes(line: np.ndarray, floor: float) -> int:
    signs = np.sign(line[np.abs(line) > floor])
    return int(np.count_nonzero(signs[1:] != signs[:-1])) if signs.size > 1 else 0


def classify_surface_mode(coordinates: np.ndarray, values: np.ndarray,
                          policy: FamilyClassifierPolicy = PROVISIONAL_FAMILY_CLASSIFIER) -> ModeFamily:
    """Classify one outer-surface FE shape (``coordinates``: n × 2 in-plane, ``values``: out-of-plane)."""

    coordinates = np.asarray(coordinates, dtype=float)
    values = np.asarray(values, dtype=float).reshape(-1)
    if coordinates.ndim != 2 or coordinates.shape[1] != 2 or len(coordinates) != len(values) or len(values) < 9:
        raise FamilyClassificationError("need n ≥ 9 surface nodes with (x, y) and one shape value each.")
    if not np.all(np.isfinite(coordinates)) or not np.all(np.isfinite(values)):
        raise FamilyClassificationError("coordinates and shape values must be finite.")
    low, high = coordinates.min(axis=0), coordinates.max(axis=0)
    half = (high - low) / 2.0
    if np.any(half <= 0.0):
        raise FamilyClassificationError("the surface has no in-plane extent.")
    centre = (low + high) / 2.0
    normalised = (coordinates - centre) / half  # both axes in [-1, 1]
    tolerance = policy.mirror_tolerance * 2.0 * min(half) / max(half)  # in normalised units of the longer axis

    u, v = normalised[:, 0], normalised[:, 1]
    p_x = _mirror_parity(normalised, values, np.column_stack([-u, v]), tolerance, policy)
    p_y = _mirror_parity(normalised, values, np.column_stack([u, -v]), tolerance, policy)
    p_diagonal = p_antidiagonal = None
    if abs(half[0] - half[1]) / max(half) <= policy.near_square_tolerance:
        p_diagonal = _mirror_parity(normalised, values, np.column_stack([v, u]), tolerance, policy)
        p_antidiagonal = _mirror_parity(normalised, values, np.column_stack([-v, -u]), tolerance, policy)

    n = policy.nodal_grid_points
    axis = np.linspace(-1.0, 1.0, n)
    grid_u, grid_v = np.meshgrid(axis, axis)  # rows: constant v; columns: constant u
    grid = griddata(normalised, values, (grid_u, grid_v), method="nearest")
    floor = policy.nodal_amplitude_floor * float(np.max(np.abs(values)))
    inner = slice(1, n - 1)  # skip the edge rows and columns
    nodal_x = int(np.median([_sign_changes(row, floor) for row in grid[inner, :]]))
    nodal_y = int(np.median([_sign_changes(column, floor) for column in grid[:, inner].T]))
    return ModeFamily(p_x, p_y, p_diagonal, p_antidiagonal, _parity_class(p_x, policy), _parity_class(p_y, policy),
                      nodal_x, nodal_y, policy.policy_hash)


def mirror_coverage(coordinates: np.ndarray,
                    policy: FamilyClassifierPolicy = PROVISIONAL_FAMILY_CLASSIFIER) -> dict[str, float]:
    """Share of surface nodes with a mirror node under each reflection (evidence; same rule as the parities)."""

    coordinates = np.asarray(coordinates, dtype=float)
    low, high = coordinates.min(axis=0), coordinates.max(axis=0)
    half = (high - low) / 2.0
    normalised = (coordinates - (low + high) / 2.0) / half
    tolerance = policy.mirror_tolerance * 2.0 * min(half) / max(half)
    tree = cKDTree(normalised)
    u, v = normalised[:, 0], normalised[:, 1]
    reflections = {"x": np.column_stack([-u, v]), "y": np.column_stack([u, -v]),
                   "diagonal": np.column_stack([v, u]), "antidiagonal": np.column_stack([-v, -u])}
    return {name: float((tree.query(mirrored)[0] <= tolerance).mean()) for name, mirrored in reflections.items()}


def classify_shape_pack_modes(pack, policy: FamilyClassifierPolicy = PROVISIONAL_FAMILY_CLASSIFIER
                              ) -> dict[int, ModeFamily]:
    """Classify every mode of an FE shape pack (outer surface: in-plane x, y and out-of-plane U3)."""

    coordinates = np.asarray(pack.coordinates, dtype=float)[:, :2]
    return {mode: classify_surface_mode(coordinates, np.asarray(pack.displacements[k][:, 2], dtype=float), policy)
            for k, mode in enumerate(pack.mode_numbers)}


@dataclass(frozen=True)
class ClassifiedRow:
    row_id: str
    experimental_hz: float
    family: ModeFamily


@dataclass(frozen=True)
class HoldoutSelection:
    torsion_family: Optional[str]
    validation_family: Optional[str]
    holdout_row_ids: tuple[str, ...]
    fit_row_ids: tuple[str, ...]
    notes: tuple[str, ...]


def select_holdouts(rows: Sequence[ClassifiedRow], k_int_enabled: bool) -> HoldoutSelection:
    """SPEC §12.3 default sandwich holdouts, by physical family.

    - the lowest torsion-dominated (≈ odd-odd) family, when k_int is not enabled;
    - the highest accepted family, as a validation holdout.

    Every row of a held-out family is held out.  Order is by experimental frequency.
    """

    rows = sorted(rows, key=lambda row: row.experimental_hz)
    if len({row.row_id for row in rows}) != len(rows):
        raise ValueError("row ids must be unique.")
    notes, families = [], []
    torsion = None
    if k_int_enabled:
        notes.append("k_int enabled: no torsion-family holdout")
    else:
        torsion_rows = [row for row in rows if row.family.torsion_dominated]
        if torsion_rows:
            torsion = torsion_rows[0].family.key
            families.append(torsion)
        else:
            notes.append("no torsion-dominated (odd-odd) family among the accepted rows")
    validation = rows[-1].family.key if rows else None
    if validation is not None:
        if validation == torsion:
            notes.append("the highest accepted family is the torsion family")
        families.append(validation)
    holdout = tuple(row.row_id for row in rows if row.family.key in families)
    fit = tuple(row.row_id for row in rows if row.family.key not in families)
    return HoldoutSelection(torsion, validation, holdout, fit, tuple(notes))
