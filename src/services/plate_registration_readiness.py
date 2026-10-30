"""PLATE-WORKBENCH-RC1 / PLATE-ONLY-R3: is the physical registration of the single plate ready for an owner decision?

No Qt, no import of modes, no MAC, no FrozenRegistration. The service takes structured evidence (``Fact``: a value
with its provenance and source) and checks whether every independent fact a physical registration of one scan of
``PLATE-300x300x1mm`` needs is present, whether they are compatible with each other, the specimen record and the FE
geometry, and returns the exact list of what is missing. It never chooses an orientation from a numerical result
(MAC, frequency, shape similarity): an orientation comes only from the evidence.

Two links are kept apart:

- **A. scanner → physical plate**: the face towards the scanner, the physical edge each scan-grid axis points to, the
  reference of the 45° turn, the scan window's offsets to the physical edges, the scan scale and the measured DOF.
- **B. physical plate → FE model**: the FE axis along the 301 mm edges, the physical corner at FE (0, 0) and the
  physical face the S4R normal (+Z) leaves.

Provenance classes (PLATE-WORKBENCH-RC1 §4.2): ``MEASURED``, ``INSTRUMENT_RECORD`` and ``HUMAN_CONFIRMED`` are
independent evidence; ``DERIVED`` is evidence only when every fact it is derived from is; ``CANDIDATE``,
``CONVENTION_ONLY`` and ``NOT_VERIFIED`` never are. A computational convention (for example picture D of M11 §16.2)
is reported as a convention and refused as physical evidence.

Physical plate frame (``Φ``) used by the checks, from the HUMAN records of M11 §13.1: seen from the MARKED face, edge
1 is at the top, 2 right, 3 bottom, 4 left; edges 1 and 3 are the 301 mm edges. ``a`` runs from edge 4 to edge 2
(0…301 mm), ``b`` from edge 3 to edge 1 (0…300 mm), ``c`` out of the marked face. The frame is a bookkeeping device
for the evidence, not a physical fact.

A complete and consistent set of evidence gives ``EVIDENCE_COMPLETE_NOT_FROZEN`` with the scan-to-FE transform it
implies. Freezing a registration, pairing modes and computing a MAC remain separate owner decisions:
``mac_permitted`` is False unless a frozen registration is supplied, and this service never creates one.

PLATE-WORKBENCH-RC1 final correction (owner, 2026-10-30: the same plate, the same physical points and the same
measured face in 261016 and 261027; two rubber bands instead of four; turned 45°):

- a RELATIVE fact (the same face, the same points) is kept apart from an ABSOLUTE one (which face, which edge): it
  carries the reference series' evidence over, never more. If the 261016 face is only a candidate, so is the 261027
  face;
- ``series_link`` relates two scans by their instrument geometry only (point ids and grid axes; no mode, frequency or
  MAC): ``SAME_PHYSICAL_POINTS_HUMAN_CONFIRMED`` (the owner) is kept apart from the point-to-point map, which is
  ``POINT_TO_POINT_MAPPING_DERIVED`` when one proper grid symmetry preserves every id and
  ``POINT_TO_POINT_MAPPING_INSTRUMENT_VERIFIED`` only on the instrument's own records of both sessions (scanner angles
  and camera frames);
- the physical metric of the scan is a fact of its own (``scan_metric_geometry``): the PSV UNV grid is a
  representation, not a physical calibration (M11 §15.4: in 261016 the UNV grid is near-square, the scanner angles
  give an aspect of 0.775). The suspension facts are test conditions, never registration evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Optional, Sequence

import numpy as np

MEASURED = "MEASURED"
INSTRUMENT_RECORD = "INSTRUMENT_RECORD"
HUMAN_CONFIRMED = "HUMAN_CONFIRMED"
DERIVED = "DERIVED"
CANDIDATE = "CANDIDATE"
CONVENTION_ONLY = "CONVENTION_ONLY"
NOT_VERIFIED = "NOT_VERIFIED"
PROVENANCES = (MEASURED, INSTRUMENT_RECORD, HUMAN_CONFIRMED, DERIVED, CANDIDATE, CONVENTION_ONLY, NOT_VERIFIED)
INDEPENDENT = (MEASURED, INSTRUMENT_RECORD, HUMAN_CONFIRMED)

COMPLETE = "EVIDENCE_COMPLETE_NOT_FROZEN"
REGISTRATION_NOT_VERIFIED = "PHYSICAL_REGISTRATION_NOT_VERIFIED"
LINK_VERIFIED = "EVIDENCE_COMPLETE"
LINK_OPEN = "NOT_VERIFIED"

PLATE_MM = (301.0, 300.0)  # a (edges 1 / 3, the 301 mm edges) × b (edges 2 / 4)
PLAN_RESOLUTION_MM = 1.0  # the plan record's last digit (services.plate_study): offsets must close the plan to it
FACES = ("marked", "unmarked")
EDGE_DIRECTION = {1: np.array([0.0, 1.0, 0.0]), 2: np.array([1.0, 0.0, 0.0]), 3: np.array([0.0, -1.0, 0.0]),
                  4: np.array([-1.0, 0.0, 0.0])}  # the outward direction of each physical edge in Φ
CORNERS = {frozenset((3, 4)): (0.0, 0.0), frozenset((2, 3)): (PLATE_MM[0], 0.0), frozenset((1, 2)): PLATE_MM,
           frozenset((1, 4)): (0.0, PLATE_MM[1])}

SAME_POINTS_HUMAN = "SAME_PHYSICAL_POINTS_HUMAN_CONFIRMED"
MAPPING_INSTRUMENT_VERIFIED = "POINT_TO_POINT_MAPPING_INSTRUMENT_VERIFIED"
MAPPING_DERIVED = "POINT_TO_POINT_MAPPING_DERIVED"  # ids preserved by one proper grid symmetry; not instrument-verified
MAPPING_REFUSED = "POINT_TO_POINT_MAPPING_REFUSED"

SCAN_FACTS = ("scanned_face", "grid_plus_u_edge", "grid_plus_v_edge", "rotation_reference", "scan_window_offsets_mm",
              "scan_scale", "scan_metric_geometry", "measured_dof")
FE_FACTS = ("fe_x_along_edges", "fe_origin_corner", "fe_normal_face")
WHY = {
    "scanned_face": "the face of the plate towards the scanner (marked or unmarked)",
    "grid_plus_u_edge": "the physical edge (1–4) the scan grid's +u axis points to",
    "grid_plus_v_edge": "the physical edge (1–4) the scan grid's +v axis points to",
    "rotation_reference": "the reference position and direction of the 45° turn",
    "scan_window_offsets_mm": "the distances from the scan window to the physical edges (−u, +u, −v, +v)",
    "scan_scale": "the scale of the scan coordinates (units and the measured distance)",
    "scan_metric_geometry": "the scan coordinates are physical positions on the plate (the instrument's scanner angles "
                            "and distance, or a camera frame), not only a grid representation",
    "measured_dof": "the direction of the measured DOF",
    "fe_x_along_edges": "which physical edges the FE X axis runs along",
    "fe_origin_corner": "the physical corner at FE (0, 0)",
    "fe_normal_face": "the physical face the S4R normal (+Z) leaves",
}


@dataclass(frozen=True)
class Fact:
    key: str
    value: Any
    provenance: str
    source: str
    derived_from: tuple = ()

    def __post_init__(self) -> None:
        if self.provenance not in PROVENANCES:
            raise ValueError(f"unknown provenance {self.provenance!r} for {self.key}")


@dataclass(frozen=True)
class LinkResult:
    link: str
    status: str
    facts: tuple  # (key, value, provenance, source)
    missing: tuple  # (key, reason)
    conventions: tuple  # keys offered only as a convention


@dataclass(frozen=True)
class RegistrationReadiness:
    status: str
    scan_to_plate: LinkResult
    plate_to_fe: LinkResult
    checks: tuple  # (check, state, detail)
    missing: tuple  # (key, reason), both links
    transform: Optional[dict] = None  # the scan → FE map the evidence implies (only when complete)
    supporting: tuple = ()  # (key, value, provenance, source) of the facts the link facts are derived from
    frozen: bool = False  # never created here
    mac_computed: bool = False
    notes: tuple = field(default=(
        "No orientation is chosen by MAC, frequency or shape similarity.",
        "A computational convention is never physical evidence.",
        "A complete evidence set is not a frozen registration: freezing, pairing and MAC are separate owner "
        "decisions."))


def _independent(fact: Fact, facts: Mapping[str, Fact], seen=()) -> bool:
    if fact.provenance in INDEPENDENT:
        return True
    if fact.provenance != DERIVED or not fact.derived_from:
        return False
    return all(key in facts and key not in seen and _independent(facts[key], facts, seen + (fact.key,))
               for key in fact.derived_from)


def _weak_inputs(fact: Fact, facts: Mapping[str, Fact], seen=()) -> list:
    """The non-independent facts a DERIVED fact rests on (``key (PROVENANCE)``), for an exact missing list."""
    weak = []
    for key in fact.derived_from:
        source = facts.get(key)
        if source is None or key in seen:
            weak.append(f"{key} (missing)")
        elif source.provenance == DERIVED and source.derived_from:
            weak += _weak_inputs(source, facts, seen + (fact.key,))
        elif source.provenance not in INDEPENDENT:
            weak.append(f"{key} ({source.provenance})")
    return weak


def _link(name: str, keys: Sequence[str], facts: Mapping[str, Fact]) -> LinkResult:
    missing, conventions, shown = [], [], []
    for key in keys:
        fact = facts.get(key)
        if fact is None:
            missing.append((key, f"missing: {WHY[key]}"))
            continue
        shown.append((key, fact.value, fact.provenance, fact.source))
        if fact.provenance == CONVENTION_ONLY:
            conventions.append(key)
            missing.append((key, f"a computational convention is not physical evidence ({WHY[key]})"))
        elif not _independent(fact, facts):
            rests_on = ", ".join(dict.fromkeys(_weak_inputs(fact, facts))) if fact.provenance == DERIVED else ""
            missing.append((key, f"{fact.provenance}: not independent evidence ({WHY[key]})"
                            + (f"; rests on {rests_on}" if rests_on else "")))
    return LinkResult(name, LINK_VERIFIED if not missing else LINK_OPEN, tuple(shown), tuple(missing),
                      tuple(conventions))


def _vector_of_edge(edge) -> Optional[np.ndarray]:
    try:
        return EDGE_DIRECTION[int(edge)]
    except (KeyError, TypeError, ValueError):
        return None


def grid_axes(coordinates_m: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    """(angle °, u, v) of a planar scan grid in the scan frame: u along the median nearest-neighbour direction
    (mod 90°), v = z × u. Instrument geometry only."""
    xy = np.asarray(coordinates_m, dtype=float)[:, :2]
    distances = np.linalg.norm(xy[:, None, :] - xy[None, :, :], axis=2)
    np.fill_diagonal(distances, np.inf)
    vectors = xy[distances.argmin(axis=1)] - xy
    angle = float(np.median(np.degrees(np.arctan2(vectors[:, 1], vectors[:, 0])) % 90.0))
    u = np.array([math.cos(math.radians(angle)), math.sin(math.radians(angle))])
    return angle, u, np.array([-u[1], u[0]])


def _scan_to_phi(facts: Mapping[str, Fact]) -> tuple[Optional[np.ndarray], list]:
    """The rotation scan (u, v, z towards the scanner) → Φ, and the checks."""
    checks = []
    face = facts["scanned_face"].value
    u_phi, v_phi = _vector_of_edge(facts["grid_plus_u_edge"].value), _vector_of_edge(facts["grid_plus_v_edge"].value)
    if face not in FACES:
        checks.append(("scanned face", "REFUSED", f"{face!r} is not a physical face {FACES}"))
        return None, checks
    if u_phi is None or v_phi is None:
        checks.append(("grid edges", "REFUSED", "an edge is not one of 1–4"))
        return None, checks
    if abs(float(u_phi @ v_phi)) > 0.5:
        checks.append(("grid edges", "REFUSED",
                       "the +u and +v edges must be adjacent edges (not the same or opposite)"))
        return None, checks
    z_phi = np.array([0.0, 0.0, 1.0 if face == "marked" else -1.0])  # z points from the plate towards the scanner
    rotation = np.column_stack([u_phi, v_phi, z_phi])
    if np.linalg.det(rotation) < 0:
        checks.append(("handedness of the scan link", "REFUSED",
                       "the face and the two edges describe a mirror image: they cannot all be true"))
        return None, checks
    checks.append(("handedness of the scan link", "CONSISTENT", "face and edges form a proper rotation"))
    return rotation, checks


def _phi_to_fe(facts: Mapping[str, Fact]) -> tuple[Optional[np.ndarray], Optional[np.ndarray], list]:
    """(rotation Φ → FE, FE origin in Φ, checks)."""
    checks = []
    along = str(facts["fe_x_along_edges"].value)
    if along != "1/3":
        checks.append(("FE X axis", "REFUSED", "FE X must run along the 301 mm edges 1 / 3 (M11 §13.1)"))
        return None, None, checks
    try:
        corner = frozenset(int(e) for e in facts["fe_origin_corner"].value)
    except (TypeError, ValueError):
        corner = frozenset()
    if corner not in CORNERS:
        checks.append(("FE origin corner", "REFUSED", "the corner must be named by two adjacent edges"))
        return None, None, checks
    origin = np.array([*CORNERS[corner], 0.0])
    x = np.array([1.0 if origin[0] == 0.0 else -1.0, 0.0, 0.0])
    y = np.array([0.0, 1.0 if origin[1] == 0.0 else -1.0, 0.0])
    z = np.cross(x, y)  # the FE frame is right-handed (M11 §15.1)
    face = facts["fe_normal_face"].value
    expected = "marked" if z[2] > 0 else "unmarked"
    if face != expected:
        checks.append(("FE normal against the origin corner", "REFUSED",
                       f"with FE (0, 0) at the corner of edges {sorted(corner)} and X along 1 / 3 the right-handed "
                       f"FE +Z leaves the {expected} face, not the {face!r} face"))
        return None, None, checks
    checks.append(("FE normal against the origin corner", "CONSISTENT", f"+Z leaves the {expected} face"))
    return np.vstack([x, y, z]), origin, checks


def evaluate(facts: Sequence[Fact], scan_coordinates_m: Optional[np.ndarray] = None,
             measured_components: str = "Z", fe_plan_mm: Optional[Sequence[float]] = None) -> RegistrationReadiness:
    """The readiness of a physical registration from ``facts``; numbers of the data are used only for
    compatibility checks, never to choose a fact."""
    by_key = {fact.key: fact for fact in facts}
    scan = _link("scanner → physical plate", SCAN_FACTS, by_key)
    fe = _link("physical plate → FE model", FE_FACTS, by_key)
    checks = []
    if fe_plan_mm is not None:
        ok = all(abs(float(a) - b) <= PLAN_RESOLUTION_MM for a, b in zip(fe_plan_mm, PLATE_MM))
        checks.append(("FE plan against the specimen", "CONSISTENT" if ok else "REFUSED",
                       f"FE {tuple(round(float(v), 3) for v in fe_plan_mm[:2])} mm, specimen {PLATE_MM} mm"))
    components = "".join(sorted(set(str(measured_components).upper())))
    checks.append(("measured DOF", "CONSISTENT" if components == "Z" else "REFUSED",
                   "out-of-plane Z only: compatible with the S4R mid-surface normal" if components == "Z" else
                   f"measured components {measured_components!r}: an in-plane DOF needs a full 3-D registration"))
    transform = None
    if scan.status == LINK_VERIFIED:
        rotation, scan_checks = _scan_to_phi(by_key)
        checks += scan_checks
        scale = _scale(by_key["scan_scale"].value)
        if scale is None:
            checks.append(("scan scale", "REFUSED", f"{by_key['scan_scale'].value!r}: the scale needs a positive, "
                           "finite mm_per_unit"))
            rotation = None
    else:
        rotation = None
    if fe.status == LINK_VERIFIED:
        fe_rotation, origin, fe_checks = _phi_to_fe(by_key)
        checks += fe_checks
    else:
        fe_rotation = origin = None
    if rotation is not None and scan_coordinates_m is not None:
        window_check = _window(by_key, rotation, np.asarray(scan_coordinates_m, dtype=float))
        checks.append(window_check[0])
        placement = window_check[1]
    else:
        placement = None
    refused = [c for c in checks if c[1] == "REFUSED"]
    complete = (scan.status == LINK_VERIFIED and fe.status == LINK_VERIFIED and not refused
                and rotation is not None and fe_rotation is not None and placement is not None)
    if complete:
        transform = {"scan_to_phi": rotation.tolist(), "phi_to_fe": fe_rotation.tolist(),
                     "scan_to_fe": (fe_rotation @ rotation).tolist(), "fe_origin_in_phi_mm": origin.tolist(),
                     "grid": placement, "basis": "the evidence only (no MAC, frequency or shape)"}
    missing = scan.missing + fe.missing + tuple((c[0], c[2]) for c in refused)
    supporting = tuple((f.key, f.value, f.provenance, f.source) for f in facts
                       if f.key not in SCAN_FACTS and f.key not in FE_FACTS)
    return RegistrationReadiness(COMPLETE if complete else REGISTRATION_NOT_VERIFIED, scan, fe, tuple(checks),
                                 missing, transform, supporting)


def _scale(value) -> Optional[float]:
    try:
        scale = float((value or {}).get("mm_per_unit"))
    except (AttributeError, TypeError, ValueError):
        return None
    return scale if math.isfinite(scale) and scale > 0 else None


def _window(facts: Mapping[str, Fact], rotation: np.ndarray, coordinates: np.ndarray) -> tuple:
    """The scan window placed in Φ by the offsets; it must close the plate plan to the record's resolution and lie
    on the plate (no negative offset)."""
    angle, u, v = grid_axes(coordinates)
    scale = _scale(facts["scan_scale"].value)
    xy = coordinates[:, :2] - coordinates[:, :2].mean(axis=0)
    su, sv = xy @ u * scale, xy @ v * scale
    offsets = dict(facts["scan_window_offsets_mm"].value or {})
    try:
        width_u = su.max() - su.min() + float(offsets["-u"]) + float(offsets["+u"])
        width_v = sv.max() - sv.min() + float(offsets["-v"]) + float(offsets["+v"])
    except (KeyError, TypeError, ValueError):
        return ("scan window", "REFUSED", "the offsets need the four keys −u, +u, −v, +v in mm"), None
    if any(float(offsets[key]) < 0 for key in ("-u", "+u", "-v", "+v")):
        return ("scan window", "REFUSED", f"a negative offset {offsets} puts measured points outside the plate"), None
    u_phi, v_phi = rotation[:, 0], rotation[:, 1]
    length_u = PLATE_MM[0] if abs(u_phi[0]) > 0.5 else PLATE_MM[1]
    length_v = PLATE_MM[0] if abs(v_phi[0]) > 0.5 else PLATE_MM[1]
    if abs(width_u - length_u) > PLAN_RESOLUTION_MM or abs(width_v - length_v) > PLAN_RESOLUTION_MM:
        return ("scan window", "REFUSED", f"window + offsets give {width_u:.2f} × {width_v:.2f} mm along u × v, the "
                f"plate {length_u:.0f} × {length_v:.0f} mm"), None
    return (("scan window", "CONSISTENT", f"window + offsets close the plate to {width_u:.2f} × {width_v:.2f} mm "
             f"(grid angle {angle:.2f}°)"),
            {"angle_deg": angle, "u": u.tolist(), "v": v.tolist(), "mm_per_unit": scale,
             "centre": coordinates[:, :2].mean(axis=0).tolist(), "su_min": float(su.min()), "sv_min": float(sv.min()),
             "offsets_mm": offsets})


def map_points_to_fe(readiness: RegistrationReadiness, coordinates_m: np.ndarray) -> np.ndarray:
    """FE (X, Y) in mm of scan points under a complete evidence set (synthetic checks; no pairing, no MAC)."""
    if readiness.status != COMPLETE or readiness.transform is None:
        raise ValueError(f"{readiness.status}: no transform without a complete evidence set")
    grid = readiness.transform["grid"]
    rotation = np.array(readiness.transform["scan_to_phi"])
    fe_rotation = np.array(readiness.transform["phi_to_fe"])
    origin = np.array(readiness.transform["fe_origin_in_phi_mm"])
    xy = np.asarray(coordinates_m, dtype=float)[:, :2] - np.array(grid["centre"])
    su = xy @ np.array(grid["u"]) * grid["mm_per_unit"] - grid["su_min"] + grid["offsets_mm"]["-u"]
    sv = xy @ np.array(grid["v"]) * grid["mm_per_unit"] - grid["sv_min"] + grid["offsets_mm"]["-v"]
    # distances from the −u / −v physical edges, placed along the Φ directions of +u / +v
    u_phi, v_phi = rotation[:, 0], rotation[:, 1]
    start = np.zeros(3)
    for direction in (u_phi, v_phi):  # the −u (−v) edge lies where the +u (+v) direction starts
        axis = 0 if abs(direction[0]) > 0.5 else 1
        start[axis] = 0.0 if direction[axis] > 0 else PLATE_MM[axis]
    phi = start[None, :] + su[:, None] * u_phi[None, :] + sv[:, None] * v_phi[None, :]
    fe = (phi - origin[None, :]) @ fe_rotation.T
    return fe[:, :2]


def mac_permitted(readiness: RegistrationReadiness, frozen_registration: Any = None) -> bool:
    """A MAC is computed only on a frozen registration of complete evidence; this service never freezes one."""
    return readiness.status == COMPLETE and frozen_registration is not None


# ----------------------------------------------------------------------------- two scans of the same points

_SYMMETRIES = {  # the eight symmetries of a square grid acting on (i, j) relative to its centre
    "identity": ((1, 0), (0, 1)), "turn 90°": ((0, -1), (1, 0)), "turn 180°": ((-1, 0), (0, -1)),
    "turn 270°": ((0, 1), (-1, 0)), "mirror i": ((-1, 0), (0, 1)), "mirror j": ((1, 0), (0, -1)),
    "mirror diagonal": ((0, 1), (1, 0)), "mirror antidiagonal": ((0, -1), (-1, 0)),
}


@dataclass(frozen=True)
class SeriesLink:
    status: str  # MAPPING_DERIVED / MAPPING_INSTRUMENT_VERIFIED / MAPPING_REFUSED / NOT_VERIFIED
    same_points: str  # SAME_POINTS_HUMAN or NOT_VERIFIED
    symmetry: Optional[str]  # the grid symmetry that preserves every id (None: none does)
    proper: Optional[bool]
    ids_preserved: int
    points: int
    turn_deg: Optional[float]  # reference grid axes → this scan's, in the scan frame (+ counter-clockwise from +Z)
    sense: str
    representation_scale: Optional[float]  # pitch ratio of the two UNV grids (a representation, not a metric)
    reasons: tuple


def grid_indices(coordinates_m: np.ndarray) -> Optional[np.ndarray]:
    """Integer (i, j) of each point along the grid's own u / v axes, or None when the points are not one regular grid
    (two points in one cell). Instrument geometry only."""
    xy = np.asarray(coordinates_m, dtype=float)[:, :2]
    _angle, u, v = grid_axes(xy)
    distances = np.linalg.norm(xy[:, None, :] - xy[None, :, :], axis=2)
    np.fill_diagonal(distances, np.inf)
    pitch = float(np.median(distances.min(axis=1)))
    s = np.column_stack([(xy - xy.mean(axis=0)) @ u, (xy - xy.mean(axis=0)) @ v])
    cells = np.rint((s - s.min(axis=0)) / pitch).astype(int)
    if len({tuple(c) for c in cells}) != len(cells):
        return None
    return cells


def series_link(reference_ids: Sequence[int], reference_coordinates_m: np.ndarray, ids: Sequence[int],
                coordinates_m: np.ndarray, same_points: Optional[Fact], same_face: Optional[Fact] = None,
                instrument_records_of_both: bool = False) -> SeriesLink:
    """How the points of a scan relate to those of a reference scan of the same plate, from the two scan geometries
    only (point ids and grid axes; never a mode, a frequency or a MAC).

    The owner's statement that the points are the same (``same_points``) is kept apart from the map: the map is
    DERIVED when exactly one symmetry of the square grid preserves every id and it is a proper one (a mirror cannot
    relate the same measured face). It is INSTRUMENT_VERIFIED only on the instrument's own records of both sessions
    (``instrument_records_of_both``: the scanner angles and the camera frames). Relabelled ids refuse the map; they
    are never a reason to call the specimen another one."""
    reasons = []
    human = same_points is not None and same_points.provenance == HUMAN_CONFIRMED
    if not human:
        reasons.append("the same physical points are not confirmed (HUMAN) — the map is not derived")
    ref = dict(zip((int(i) for i in reference_ids), np.asarray(reference_coordinates_m, dtype=float)[:, :2]))
    cur = dict(zip((int(i) for i in ids), np.asarray(coordinates_m, dtype=float)[:, :2]))
    common = sorted(set(ref) & set(cur))
    empty = SeriesLink(MAPPING_REFUSED, SAME_POINTS_HUMAN if human else NOT_VERIFIED, None, None, 0,
                       len(cur), None, "—", None, ())
    if set(ref) != set(cur):
        return SeriesLink(**{**empty.__dict__, "reasons": tuple(reasons) + (
            f"the id sets differ ({len(ref)} and {len(cur)} points, {len(common)} common): the instrument's own "
            "point records of both sessions are needed",)})
    ref_xy, cur_xy = np.array([ref[i] for i in common]), np.array([cur[i] for i in common])
    ref_cells, cur_cells = grid_indices(ref_xy), grid_indices(cur_xy)
    if ref_cells is None or cur_cells is None:
        return SeriesLink(**{**empty.__dict__, "reasons": tuple(reasons) + ("a scan is not one regular grid",)})
    ref_c = ref_cells - (ref_cells.max(axis=0) + ref_cells.min(axis=0)) / 2.0
    cur_c = cur_cells - (cur_cells.max(axis=0) + cur_cells.min(axis=0)) / 2.0
    matched = {name: int(np.sum(np.all(np.isclose(ref_c @ np.array(m).T, cur_c), axis=1)))
               for name, m in _SYMMETRIES.items()}
    full = [name for name, count in matched.items() if count == len(common)]
    best = max(matched.values())
    if len(full) != 1:
        return SeriesLink(**{**empty.__dict__, "ids_preserved": best, "reasons": tuple(reasons) + (
            f"no single grid symmetry preserves every id (best {best} of {len(common)}): the ids are relabelled; the "
            "map needs the instrument's own point records of both sessions (not a reason to call it another "
            "specimen)",)})
    name = full[0]
    matrix = np.array(_SYMMETRIES[name], dtype=float)
    proper = bool(np.linalg.det(matrix) > 0)
    _a, ref_u, _rv = grid_axes(ref_xy)
    _b, cur_u, cur_v = grid_axes(cur_xy)
    image = matrix @ np.array([1.0, 0.0])  # the reference +u in this scan's (u, v) index directions
    direction = image[0] * cur_u + image[1] * cur_v
    turn = math.degrees(math.atan2(ref_u[0] * direction[1] - ref_u[1] * direction[0], float(ref_u @ direction)))
    pitch = [float(np.median(np.sort(np.linalg.norm(p[:, None] - p[None], axis=2), axis=1)[:, 1]))
             for p in (ref_xy, cur_xy)]
    if not proper:
        reasons.append("the id layouts are mirror images: the same measured face cannot give them"
                       + (" (the owner confirmed the same face)" if same_face is not None else ""))
    status = (MAPPING_REFUSED if not proper or not human else
              MAPPING_INSTRUMENT_VERIFIED if instrument_records_of_both else MAPPING_DERIVED)
    if status == MAPPING_DERIVED:
        reasons.append("derived from the owner's same points and the two UNV geometries; not instrument-verified "
                       "(needs the scanner angles and camera frames of both sessions)")
    sense = ("—" if not proper else "clockwise as viewed from the scanner (+Z towards it)" if turn < 0
             else "counter-clockwise as viewed from the scanner (+Z towards it)")
    return SeriesLink(status, SAME_POINTS_HUMAN if human else NOT_VERIFIED, name, proper, matched[name], len(common),
                      round(turn, 2) if proper else None, sense, round(pitch[1] / pitch[0], 4), tuple(reasons))


# ----------------------------------------------------------------------------- the real series 261027

# The two scans of the plate, related by ``series_link`` on 2026-10-30 (PLATE-WORKBENCH-RC1 final correction; read
# only). The reference is the 261016 PSV export (the M11 session; its POLYMAX file has the same geometry).
SERIES_LINK_INPUTS = {
    "reference": ("300by300_plate_only_1mm_261016.unv",
                  "6d66eafe6558e22614b8068046a1c0454c1c96e3e713a3fad6e3ab72781d48e6"),
    "reference_polymax": ("300by300_plate_only_1mm_261016_POLYMAX.unv",
                          "117c893bafbbeba2c38861d5781e291e4c3bf37b91a29b7766419e764bacd3ff"),
    "series": ("300by300_plate_only_1mm_ROTATED_Polytec_261027.unv",
               "76db80aed1b4ba7062c0bf914cae85b55ea2665d80cb643c8cd54ba6c8bedc4d"),
}
SERIES_LINK_261016_261027 = {
    "status": MAPPING_DERIVED, "same_points": SAME_POINTS_HUMAN, "symmetry": "identity", "proper": True,
    "ids_preserved": 289, "points": 289, "turn_deg": -44.17,
    "sense": "clockwise as viewed from the scanner (+Z towards it)", "representation_scale": 1.1196,
    "grid_axis_deg": {"261016": 89.42, "261027": 45.24},
    "unv_grid_span_m": {"261016": (0.2502, 0.2494), "261027": (0.2777, 0.2770)},
    "unv_z_m": {"261016": -1.0, "261027": -1.15},
}
SERIES_LINK_NOTES = (
    "Every id k of 261027 sits in the grid cell of id k of 261016 after one proper turn of the grid (289 of 289): id "
    "k ↔ id k. With the owner's same physical points this is the point-to-point map (DERIVED, not "
    "instrument-verified).",
    "The grid turned −44.17° in the scan frame, i.e. clockwise as viewed from the Polytec: it agrees with the "
    "laboratory note (45° clockwise) and the owner (45°). The ids fix the turn modulo 360°, not only modulo 90°.",
    "A mirrored relation does not fit (no id preserved): consistent with the owner's same measured face. It does not "
    "say WHICH face that is.",
    "The scanner's node numbering in the scan frame changes with the turn (laboratory note); on the plate the ids "
    "stay with their points.",
    "The UNV grids are near-square representations (z = −1 m default in 261016, −1.15 m measured in 261027); their "
    "pitch ratio 1.120 is not a physical scale. M11 §15.4: the 261016 scanner angles give a grid aspect of 0.775, so "
    "the physical 261027 window is the 261016 one (diagnostic ≈ 215.4 × 285.2 mm), not the 277.7 × 277.0 of its UNV.",
)


def real_261027_evidence() -> tuple:
    """What the sources of the 261027 ROTATED series establish today (PLATE-ONLY-R3 audit, with the owner's
    clarification of 2026-10-30); nothing is invented. The relative facts (same points, same face) carry the 261016
    evidence over and never raise it: a candidate of 261016 stays a candidate of 261027."""
    psv = "300by300_plate_only_1mm_ROTATED_261027.unv (PSV export of the .svd; dataset 151 / 164 / 2411 / 58)"
    link = SERIES_LINK_261016_261027
    owner = "owner, 2026-10-30 (PLATE-WORKBENCH-RC1 final correction)"
    return (
        # the relative facts of the owner and the reference series (supporting facts)
        Fact("same_points_as_261016", "the same physical measured points", HUMAN_CONFIRMED, owner),
        Fact("same_face_as_261016", "the same measured face (relative: which face is not stated)", HUMAN_CONFIRMED,
             owner),
        Fact("turn_from_261016", "turned 45° from the 261016 position", HUMAN_CONFIRMED, owner),
        Fact("scan_geometry_261016", "289 points, 17 × 17 grid, ids 1–289", INSTRUMENT_RECORD,
             f"{SERIES_LINK_INPUTS['reference'][0]} ({SERIES_LINK_INPUTS['reference'][1][:12]}…)"),
        Fact("scan_geometry_261027", "289 points, 17 × 17 grid, ids 1–289", INSTRUMENT_RECORD,
             f"{SERIES_LINK_INPUTS['series'][0]} ({SERIES_LINK_INPUTS['series'][1][:12]}…)"),
        Fact("point_map_261016_261027", f"id k ↔ id k ({link['ids_preserved']} of {link['points']} ids preserved by "
             f"the grid {link['symmetry']}); grid turn {link['turn_deg']}°, {link['sense']}", DERIVED,
             f"series_link of the two scan geometries: {MAPPING_DERIVED} (not instrument-verified: the 261027 .svd "
             "is not delivered); the laboratory note's 45° clockwise agrees",
             derived_from=("same_points_as_261016", "scan_geometry_261016", "scan_geometry_261027")),
        Fact("scan_axes_261016", "scan +y up and +x right in the camera frame; the grid +u is +y (0.58° tilt)",
             INSTRUMENT_RECORD, "261016 .svd video alignment (M11 §14.2, §14.4, §15.3)"),
        Fact("top_edge_261016", 1, HUMAN_CONFIRMED, "M11 §13.1: edge 1 at the top in the 261016 test (owner's sketch)"),
        Fact("scanned_face_261016", "unmarked", CANDIDATE, "M11 §13.2 / §15.3: supported by the PSV frame (the shaker "
             "is behind the plate, mirrored), SCANNER_FACE = HUMAN_CONFIRMATION_PENDING"),
        Fact("window_offsets_261016", {"-u": 7.02, "+u": 7.78, "-v": 29.19, "+v": 56.4}, CANDIDATE,
             "M11 §14.2 / §15.4: the 261016 diagnostic reconstruction W301xH300 (SCAN_WINDOW_CALIBRATION = "
             "DIAGNOSTIC_ONLY: deviation 1 confirmed by the scanner angles, deviations 2 and 3 only supported)"),
        Fact("metric_reconstruction_261016", "scanner angles and camera frame: window ≈ 215.4 × 285.2 mm", CANDIDATE,
             "M11 §14.3 / §15.4 (DIAGNOSTIC_ONLY)"),
        # the registration facts of 261027
        Fact("scanned_face", "unmarked (the 261016 face)", DERIVED, "the owner's same face carries the 261016 "
             "candidate over; it does not establish which face", derived_from=("same_face_as_261016",
                                                                              "scanned_face_261016")),
        Fact("grid_plus_u_edge", 1, DERIVED, "the 261016 grid +u pointed up to edge 1; id k ↔ id k keeps it on the "
             "plate", derived_from=("point_map_261016_261027", "scan_axes_261016", "top_edge_261016")),
        Fact("grid_plus_v_edge", 2, DERIVED, "the 261016 grid +v pointed to the scanner's left: edge 2 if the "
             "unmarked face was scanned, edge 4 if the marked one",
             derived_from=("point_map_261016_261027", "scan_axes_261016", "scanned_face")),
        Fact("rotation_reference", "the 261016 position, turned 45° clockwise as viewed from the Polytec", DERIVED,
             "the owner (45° from the 261016 position) and the id-preserving grid turn (clockwise); the laboratory "
             "note agrees", derived_from=("turn_from_261016", "point_map_261016_261027")),
        Fact("scan_window_offsets_mm", {"-u": 7.02, "+u": 7.78, "-v": 29.19, "+v": 56.4}, DERIVED,
             "the 261016 offsets, carried over by the same points", derived_from=("point_map_261016_261027",
                                                                                 "window_offsets_261016")),
        Fact("scan_scale", {"mm_per_unit": 1000.0, "units": "m (dataset 164 METRIC_ABS_(SI))",
                            "distance_m": 1.15}, INSTRUMENT_RECORD,
             f"{psv}; the 1.15 m distance was measured by the lab (Read me.txt). Units and distance only: see "
             "scan_metric_geometry"),
        Fact("scan_metric_geometry", "the 261016 physical positions of the same points", DERIVED,
             "the 261027 UNV grid (277.7 × 277.0) is a representation, not a physical calibration (M11 §15.4)",
             derived_from=("point_map_261016_261027", "metric_reconstruction_261016")),
        Fact("measured_dof", "+Z of the scan frame (response direction 3 in all 867 dataset-58 records); the points "
             "lie at z = −1.15 m, so +Z points from the plate towards the scanner", INSTRUMENT_RECORD, psv),
        Fact("fe_x_along_edges", "1/3", HUMAN_CONFIRMED, "M11 §13.1: FE X = the 301 mm dimension"),
        Fact("fe_origin_corner", None, CANDIDATE, "M11 §14.2 / §15.2: candidates A–D; the FE model has no physical "
             "landmark, so no record can fix it (PHYSICAL_FE_ORIENTATION = NOT_DETERMINED)"),
        Fact("fe_normal_face", None, CANDIDATE, "M11 §15.2: follows from the origin corner; not determined"),
    )


# What would close the open facts of the real series, from the existing records (no new experiment is assumed).
CLOSING_EVIDENCE = (
    ("scanned_face, grid_plus_v_edge", "the 261016 SCANNER_FACE answer (M11 §15.3: did the laser see the face "
     "without marks? one yes / no); the owner's same face then carries it to 261027. This is the absolute face, not "
     "a second confirmation of the same face"),
    ("scan_window_offsets_mm, scan_metric_geometry", "the 261016 scan calibration: the PSV screenshot of a copy of "
     "the 261016 .svd with the points on the video frame, or the SUPERVISOR's decision on deviations 2 and 3 (M11 "
     "§15.4); or the 261027 .svd itself"),
    ("fe_origin_corner, fe_normal_face", "an FE model built with a measured asymmetry (for example the edge "
     "thicknesses) or a SUPERVISOR convention recorded as CONVENTION_ONLY (M11 §15.2); a convention never becomes a "
     "physical registration"),
)


INSTRUMENT_NOTES = (
    ("excitation reference", "dataset 58 'Cross Spectrum, Ref1, Force * Velocity, N * m/s': the reference channel is a "
     "force; the force sensor's location and attachment are not recorded", INSTRUMENT_RECORD),
    ("PSV project", "the PSV export names 300by300_plate_only_1mm_ROTATED_261027.svd, PSV 10.2.1.1, 27-Oct-26 "
     "11:38:17; the .svd itself is not in the delivery", INSTRUMENT_RECORD),
    ("workbook pictures", "the 11 plate-ROTATED pictures of Experiment_Freq_damping_LMS_Rotated.xlsx are Testlab "
     "mode-shape displays on the grid: no camera frame, no plate edge, no mark", INSTRUMENT_RECORD),
    ("display triad", "the Testlab display shows the grid square with its triad turned 45°: a display convention, "
     "not a physical orientation", CONVENTION_ONLY),
)


__all__ = [name for name in dir() if not name.startswith("_")]
