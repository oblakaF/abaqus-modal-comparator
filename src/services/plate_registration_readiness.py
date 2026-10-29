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

SCAN_FACTS = ("scanned_face", "grid_plus_u_edge", "grid_plus_v_edge", "rotation_reference", "scan_window_offsets_mm",
              "scan_scale", "measured_dof")
FE_FACTS = ("fe_x_along_edges", "fe_origin_corner", "fe_normal_face")
WHY = {
    "scanned_face": "the face of the plate towards the scanner (marked or unmarked)",
    "grid_plus_u_edge": "the physical edge (1–4) the scan grid's +u axis points to",
    "grid_plus_v_edge": "the physical edge (1–4) the scan grid's +v axis points to",
    "rotation_reference": "the reference position and direction of the 45° turn",
    "scan_window_offsets_mm": "the distances from the scan window to the physical edges (−u, +u, −v, +v)",
    "scan_scale": "the scale of the scan coordinates (units and the measured distance)",
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
            missing.append((key, f"{fact.provenance}: not independent evidence ({WHY[key]})"))
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
    return RegistrationReadiness(COMPLETE if complete else REGISTRATION_NOT_VERIFIED, scan, fe, tuple(checks),
                                 missing, transform)


def _window(facts: Mapping[str, Fact], rotation: np.ndarray, coordinates: np.ndarray) -> tuple:
    """The scan window placed in Φ by the offsets; it must close the plate plan to the record's resolution."""
    angle, u, v = grid_axes(coordinates)
    scale = float((facts["scan_scale"].value or {}).get("mm_per_unit", 1000.0))
    xy = coordinates[:, :2] - coordinates[:, :2].mean(axis=0)
    su, sv = xy @ u * scale, xy @ v * scale
    offsets = dict(facts["scan_window_offsets_mm"].value or {})
    try:
        width_u = su.max() - su.min() + float(offsets["-u"]) + float(offsets["+u"])
        width_v = sv.max() - sv.min() + float(offsets["-v"]) + float(offsets["+v"])
    except (KeyError, TypeError, ValueError):
        return ("scan window", "REFUSED", "the offsets need the four keys −u, +u, −v, +v in mm"), None
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


# ----------------------------------------------------------------------------- the real series 261027

def real_261027_evidence() -> tuple:
    """What the sources of the 261027 ROTATED series establish today (PLATE-ONLY-R3 audit); nothing is invented."""
    psv = "300by300_plate_only_1mm_ROTATED_261027.unv (PSV export of the .svd; dataset 151 / 164 / 2411 / 58)"
    return (
        Fact("scanned_face", None, NOT_VERIFIED, "no record of the face towards the Polytec; the plate .svd (camera "
             "frame) is named by the PSV export but not delivered"),
        Fact("grid_plus_u_edge", None, NOT_VERIFIED, "no record links a physical edge 1–4 to the scan frame"),
        Fact("grid_plus_v_edge", None, NOT_VERIFIED, "no record links a physical edge 1–4 to the scan frame"),
        Fact("rotation_reference", "45° clockwise as viewed from the Polytec; reference position not stated",
             NOT_VERIFIED, "Read me.txt (lab note): the direction is stated, the reference position is not"),
        Fact("scan_window_offsets_mm", None, NOT_VERIFIED, "no camera frame of the plate session in the delivery"),
        Fact("scan_scale", {"mm_per_unit": 1000.0, "units": "m (dataset 164 METRIC_ABS_(SI))",
                            "distance_m": 1.15}, INSTRUMENT_RECORD,
             f"{psv}; the 1.15 m distance was measured by the lab (Read me.txt)"),
        Fact("measured_dof", "+Z of the scan frame (response direction 3 in all 867 dataset-58 records); the points "
             "lie at z = −1.15 m, so +Z points from the plate towards the scanner", INSTRUMENT_RECORD, psv),
        Fact("fe_x_along_edges", "1/3", HUMAN_CONFIRMED, "M11 §13.1: FE X = the 301 mm dimension"),
        Fact("fe_origin_corner", None, CANDIDATE, "M11 §14.2 / §15.2: candidates A–D; the FE model has no physical "
             "landmark, so no record can fix it (PHYSICAL_FE_ORIENTATION = NOT_DETERMINED)"),
        Fact("fe_normal_face", None, CANDIDATE, "M11 §15.2: follows from the origin corner; not determined"),
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
