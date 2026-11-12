"""ABM-PLATE-POINT-MAC-GUI-1: exploratory point MAC under a fixed set of UNCONFIRMED geometric hypotheses.

A research calculation. Nothing here is a physical registration, a mode pair or evidence, and nothing here chooses or
ranks a hypothesis. The set of hypotheses is fixed below and does not depend on any modal amplitude:

  face         T: the measured face is the FE face of largest z (scan +z along FE +Z)
               B: the measured face is the FE face of smallest z (scan +z along FE -Z)
  quarter turn 0, 1, 2, 3 of the measured grid about the plate normal
  placement    the grid centroid on the centre of the FE outline (an ASSUMPTION), and four fixed 5 mm shifts

Every 3-D transform has determinant +1: no reflection, no permutation of points, no scaling of the grid. Each measured
point takes the nearest FE node of the assumed face; a hypothesis is used only when every point is inside the outline,
within half a mesh diagonal of its node and on a node of its own. No point is ever dropped.

Only the measured Z component is used. MAC is ``modal_core.modal_assurance_criterion`` on complex vectors.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence

import numpy as np
from scipy.spatial import cKDTree

from modal_core import modal_assurance_criterion
from reviewed_core import experimental_measurement_masks

LABEL = "EXPLORATORY MAC — UNCONFIRMED GEOMETRIC MAPPING"
SHIFTS = (("C", 0.0, 0.0), ("X+5", 5.0, 0.0), ("X-5", -5.0, 0.0), ("Y+5", 0.0, 5.0), ("Y-5", 0.0, -5.0))  # FE units
FACES = (("T", +1.0), ("B", -1.0))  # name, FE direction of scan +z
TURNS = (0, 1, 2, 3)
EXPERIMENTAL_TO_FE = 1000.0  # ASSUMPTION: measured coordinates in metres, FE coordinates in millimetres
FAMILY_TOLERANCE = 1.0e-6  # two centred matrices closer than this in every entry are one family
_EDGE = 1.0e-6  # relative slack of the outline and of the half-diagonal limit (rounding only)


class TrialUnavailable(ValueError):
    """The data do not have the form this calculation is defined for; the text says why."""


class TrialCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class Trial:
    name: str
    face: str  # "T" or "B"
    turn: int
    shift_name: str
    shift: tuple
    grid_a: tuple  # FE in-plane direction of grid axis a
    grid_b: tuple
    determinant: float  # of the 3-D transform: always +1
    points: int
    valid_points: int
    unique_nodes: int
    rms_distance: float
    max_distance: float
    edge_margin: float  # smallest distance from a placed point to an edge of the outline
    usable: bool
    rejected_because: str
    mac: Optional[np.ndarray] = None  # experimental modes x FE modes; None for a rejected hypothesis
    node_ids: tuple = ()  # the FE node of each measured point, in the order of the points
    placed: Optional[np.ndarray] = None  # the points in FE in-plane coordinates
    fe_at: Optional[np.ndarray] = None  # FE displacement along scan +z at the points, per FE mode

    @property
    def base(self) -> str:
        return f"{self.face}{self.turn}"


@dataclass(frozen=True)
class TrialRun:
    label: str
    fe_numbers: tuple
    fe_frequencies: tuple
    experimental_numbers: tuple
    experimental_frequencies: tuple
    point_ids: tuple
    experimental_z: np.ndarray  # points x experimental modes, complex, as read
    grid: dict
    faces: dict  # name -> FE z of the face
    half_mesh_diagonal: float
    scale: float
    trials: tuple
    families: tuple  # tuples of centred trial names with numerically equal matrices, in the predefined order

    def trial(self, name: str) -> Trial:
        return next(item for item in self.trials if item.name == name)

    @property
    def usable(self) -> tuple:
        return tuple(item for item in self.trials if item.usable)


def _same_points(modes, what: str) -> tuple:
    ids = [str(v) for v in modes[0].node_ids]
    coordinates = np.asarray(modes[0].coordinates, dtype=float)
    for mode in modes[1:]:
        if [str(v) for v in mode.node_ids] != ids or not np.array_equal(np.asarray(mode.coordinates, dtype=float), coordinates):
            raise TrialUnavailable(f"The {what} modes do not all hold the same points in the same order.")
    if len(set(ids)) != len(ids):
        raise TrialUnavailable(f"The {what} point labels are not unique.")
    return ids, coordinates


def _grid(xy: np.ndarray) -> tuple:
    """The lattice directions of a regular square grid from nearest-neighbour vectors only: a rigid turn, no stretch."""
    count = len(xy)
    if count < 9:
        raise TrialUnavailable("The trial needs a regular grid of at least 3 x 3 measured points.")
    distance, index = cKDTree(xy).query(xy, k=2)
    vectors = xy[index[:, 1]] - xy
    angle = np.degrees(np.arctan2(vectors[:, 1], vectors[:, 0])) % 90.0
    theta = (float(np.degrees(np.arctan2(np.mean(np.sin(np.radians(4 * angle))),
                                         np.mean(np.cos(np.radians(4 * angle)))))) / 4.0) % 90.0
    e1 = np.array([np.cos(np.radians(theta)), np.sin(np.radians(theta))])
    e2 = np.array([-e1[1], e1[0]])
    uv = np.column_stack([xy @ e1, xy @ e2])
    uv -= uv.mean(axis=0)
    pitch = float(np.median(distance[:, 1]))
    if not np.isfinite(pitch) or pitch <= 0.0:
        raise TrialUnavailable("The measured points do not form a grid: two points coincide.")
    cells = np.rint((uv - uv.min(axis=0)) / pitch).astype(int)
    counts = cells.max(axis=0) + 1
    if int(counts[0] * counts[1]) != count or len({tuple(c) for c in cells.tolist()}) != count or min(counts) < 3:
        raise TrialUnavailable("The measured points do not form a full regular rectangular grid, which the fixed "
                               "hypotheses of this trial need.")
    return e1, e2, uv, {"theta_deg": theta, "pitch": pitch, "counts": (int(counts[0]), int(counts[1])),
                        "extent": (float(np.ptp(uv[:, 0])), float(np.ptp(uv[:, 1])))}


def _pitch(values: np.ndarray, span: float) -> float:
    levels = np.unique(np.round(values / max(span, 1.0e-30), 9)) * span
    return float(np.diff(levels).max()) if len(levels) > 1 else 0.0


def run_trials(fe_modes: Sequence, experimental_modes: Sequence, cancel_event=None,
               progress: Optional[Callable[[str], None]] = None, scale: float = EXPERIMENTAL_TO_FE) -> TrialRun:
    """All 40 fixed hypotheses for the given elastic FE modes and fitted experimental modes. Reads only; changes nothing."""
    fe_modes, experimental_modes = list(fe_modes), list(experimental_modes)
    if not fe_modes or not experimental_modes:
        raise TrialUnavailable("The trial needs at least one elastic FE mode and one fitted experimental mode.")

    def stop() -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise TrialCancelled()

    point_ids, xyz = _same_points(experimental_modes, "experimental")
    masks = np.asarray(experimental_measurement_masks(experimental_modes, np.asarray(experimental_modes[0].node_ids, dtype=object)),
                       dtype=bool)
    if not masks[:, :, 2].all() or masks[:, :, :2].any():
        raise TrialUnavailable("The trial is defined for a measurement of the Z component alone at every point of every "
                               "mode; this set is measured differently.")
    experimental_z = np.column_stack([np.asarray(mode.vectors)[:, 2] for mode in experimental_modes]).astype(complex)
    if not np.isfinite(experimental_z.real).all() or not np.isfinite(experimental_z.imag).all():
        raise TrialUnavailable("A measured Z amplitude is not a finite number.")
    e1, e2, uv, grid = _grid(xyz[:, :2] * scale)
    if float(np.ptp(xyz[:, 2])) * scale > 0.01 * grid["pitch"]:
        raise TrialUnavailable("The measured points are not in one plane normal to Z.")
    stop()

    _fe_ids, fe_xyz = _same_points(fe_modes, "FE")
    fe_node_ids = np.asarray(fe_modes[0].node_ids, dtype=object)
    low, high = fe_xyz.min(axis=0), fe_xyz.max(axis=0)
    span = float(max(high[0] - low[0], high[1] - low[1]))
    if span <= 0.0:
        raise TrialUnavailable("The FE nodes have no in-plane extent.")
    fe_z = np.column_stack([np.asarray(mode.vectors)[:, 2] for mode in fe_modes])
    centre = (low[:2] + high[:2]) / 2.0
    flat = max(span, 1.0) * 1.0e-8
    surfaces, face_z = {}, {"T": float(high[2]), "B": float(low[2])}
    for name, _sign in FACES:
        rows = np.where(np.abs(fe_xyz[:, 2] - face_z[name]) <= flat)[0]
        if len(rows) < 4:
            raise TrialUnavailable("The FE model has no flat face normal to Z to place the measured points on.")
        surfaces[name] = (rows, cKDTree(fe_xyz[rows, :2]))
    rows = surfaces["T"][0]
    half_diagonal = 0.5 * float(np.hypot(_pitch(fe_xyz[rows, 0], span), _pitch(fe_xyz[rows, 1], span)))
    limit = half_diagonal * (1.0 + _EDGE)
    slack = span * _EDGE
    count = len(point_ids)

    trials = []
    for face, sign in FACES:
        rows, tree = surfaces[face]
        for turn in TURNS:
            c, s = np.cos(np.radians(90.0 * turn)), np.sin(np.radians(90.0 * turn))
            # seen from FE +Z the lower face shows the scan mirrored, (a, b) -> (a, -b); with scan +z along FE -Z the 3-D
            # transform is a proper rotation (determinant +1), not a reflection of the plate
            plane = np.array([[c, -s], [s, c]]) @ (np.eye(2) if sign > 0 else np.diag([1.0, -1.0]))
            rotation = np.zeros((3, 3))
            rotation[:2, :2] = plane @ np.vstack([e1, e2])
            rotation[2, 2] = sign
            for shift_name, dx, dy in SHIFTS:
                stop()
                name = f"{face}{turn}_{shift_name}"
                if progress is not None:
                    progress(f"Trial {len(trials) + 1} of {len(FACES) * len(TURNS) * len(SHIFTS)}: {name}")
                placed = uv @ plane.T + centre + np.array([dx, dy])
                inside = ((placed[:, 0] >= low[0] - slack) & (placed[:, 0] <= high[0] + slack)
                          & (placed[:, 1] >= low[1] - slack) & (placed[:, 1] <= high[1] + slack))
                distance, nearest = tree.query(placed)
                near = distance <= limit
                nodes = rows[nearest]
                unique = len(set(nodes.tolist()))
                usable = bool(inside.all() and near.all() and unique == count)
                reasons = []
                if not inside.all():
                    reasons.append(f"{int((~inside).sum())} points outside the FE outline")
                if not near.all():
                    reasons.append(f"{int((~near).sum())} points farther than half a mesh diagonal from an FE node")
                if unique != count:
                    reasons.append(f"{count - unique} points share an FE node")
                margin = float(min(placed[:, 0].min() - low[0], high[0] - placed[:, 0].max(),
                                   placed[:, 1].min() - low[1], high[1] - placed[:, 1].max()))
                mac = fe_at = None
                if usable:
                    fe_at = sign * fe_z[nodes, :]
                    mac = np.full((experimental_z.shape[1], fe_at.shape[1]), np.nan)
                    for i in range(mac.shape[0]):
                        for j in range(mac.shape[1]):
                            value = modal_assurance_criterion(fe_at[:, j], experimental_z[:, i])
                            if value is not None:
                                mac[i, j] = value
                    mac.flags.writeable = False
                trials.append(Trial(name, face, turn, shift_name, (dx, dy), tuple(plane[:, 0].round(6).tolist()),
                                    tuple(plane[:, 1].round(6).tolist()), float(np.linalg.det(rotation)), count,
                                    int((inside & near).sum()), unique, float(np.sqrt(np.mean(distance ** 2))),
                                    float(distance.max()), margin, usable, "; ".join(reasons), mac,
                                    tuple(str(v) for v in fe_node_ids[nodes]), placed, fe_at))
    stop()
    return TrialRun(LABEL, tuple(int(m.number) for m in fe_modes), tuple(float(m.frequency_hz) for m in fe_modes),
                    tuple(int(m.number) for m in experimental_modes), tuple(float(m.frequency_hz) for m in experimental_modes),
                    tuple(point_ids), experimental_z, grid, face_z, half_diagonal, float(scale), tuple(trials),
                    _families(trials))


def _families(trials) -> tuple:
    """Centred hypotheses whose matrices are numerically equal, grouped in the predefined order. Nothing is ranked."""
    groups: list = []
    for trial in trials:
        if trial.shift_name != SHIFTS[0][0] or not trial.usable:
            continue
        for group in groups:
            if np.allclose(group[0].mac, trial.mac, rtol=0.0, atol=FAMILY_TOLERANCE, equal_nan=True):
                group.append(trial)
                break
        else:
            groups.append([trial])
    return tuple(tuple(trial.name for trial in group) for group in groups)


__all__ = ["EXPERIMENTAL_TO_FE", "FACES", "FAMILY_TOLERANCE", "LABEL", "SHIFTS", "TURNS", "Trial", "TrialCancelled",
           "TrialRun", "TrialUnavailable", "run_trials"]
