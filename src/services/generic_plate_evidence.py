"""PRIORITY-8: the physical registration evidence of ANY single rectangular plate (no Qt, no MAC, no FrozenRegistration).

The rules of ``services.plate_registration_readiness`` (PLATE-WORKBENCH-RC1) applied to a plate whose plan comes from
its own passport instead of the M11 constants: a registration needs independent facts for two links,

- **A. scanner → physical plate**: the face towards the scanner, the physical edge each scan-grid axis points to, the
  scan window's offsets to the physical edges, the scan scale, the physical metric of the scan and the measured DOF;
- **B. physical plate → FE model**: which physical edges the FE X axis runs along, the physical corner at FE (0, 0)
  and the physical face the shell normal (+Z) leaves.

Physical plate frame Φ (a bookkeeping device, not a fact): seen from the MARKED face, edge 1 is at the top, 2 right, 3
bottom, 4 left; ``a`` runs from edge 4 to edge 2 along edges 1 / 3 (the passport length), ``b`` from edge 3 to edge 1
(the passport width), ``c`` out of the marked face.

Provenance: MEASURED, INSTRUMENT_RECORD and HUMAN_CONFIRMED are independent evidence; DERIVED only when everything it
is derived from is; CANDIDATE, CONVENTION_ONLY and NOT_VERIFIED never are. SYNTHETIC values belong to a synthetic
demonstration study only: there they stand in for declared evidence (and every result is labelled synthetic); in a
physical study they are refused.

No orientation is chosen from a frequency, a MAC or a shape. A complete, consistent evidence set gives
``EVIDENCE_COMPLETE_NOT_FROZEN`` and the scan → FE map it implies; it is not a registration. Freezing a registration,
pairing modes and computing a MAC remain separate owner decisions, and nothing here creates them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from .plate_registration_readiness import (CANDIDATE, CONVENTION_ONLY, DERIVED, HUMAN_CONFIRMED, INSTRUMENT_RECORD,
                                           MEASURED, NOT_VERIFIED, grid_axes)

SYNTHETIC = "SYNTHETIC"
PROVENANCES = (MEASURED, INSTRUMENT_RECORD, HUMAN_CONFIRMED, DERIVED, CANDIDATE, CONVENTION_ONLY, NOT_VERIFIED,
               SYNTHETIC)
INDEPENDENT = (MEASURED, INSTRUMENT_RECORD, HUMAN_CONFIRMED)
PHYSICAL, SYNTHETIC_DEMO = "PHYSICAL", "SYNTHETIC_DEMO"

COMPLETE = "EVIDENCE_COMPLETE_NOT_FROZEN"
REGISTRATION_NOT_VERIFIED = "PHYSICAL_REGISTRATION_NOT_VERIFIED"
LINK_VERIFIED, LINK_OPEN = "EVIDENCE_COMPLETE", "NOT_VERIFIED"
FACES = ("marked", "unmarked")
EDGE_DIRECTION = {1: np.array([0.0, 1.0, 0.0]), 2: np.array([1.0, 0.0, 0.0]), 3: np.array([0.0, -1.0, 0.0]),
                  4: np.array([-1.0, 0.0, 0.0])}
SCAN_FACTS = ("scanned_face", "grid_plus_u_edge", "grid_plus_v_edge", "scan_window_offsets_mm", "scan_scale",
              "scan_metric_geometry", "measured_dof")
FE_FACTS = ("fe_x_along_edges", "fe_origin_corner", "fe_normal_face")
FACT_KEYS = SCAN_FACTS + FE_FACTS
WHY = {
    "scanned_face": "the face of the plate towards the scanner (marked or unmarked)",
    "grid_plus_u_edge": "the physical edge (1–4) the scan grid's +u axis points to",
    "grid_plus_v_edge": "the physical edge (1–4) the scan grid's +v axis points to",
    "scan_window_offsets_mm": "the distances from the scan window to the physical edges (−u, +u, −v, +v) in mm",
    "scan_scale": "the scale of the scan coordinates (mm per coordinate unit)",
    "scan_metric_geometry": "the scan coordinates are physical positions on the plate (instrument angles and distance, "
                            "or a camera frame), not only a grid representation",
    "measured_dof": "the direction of the measured DOF",
    "fe_x_along_edges": "which physical edges the FE X axis runs along (1/3 or 2/4)",
    "fe_origin_corner": "the physical corner at FE (0, 0), named by two adjacent edges",
    "fe_normal_face": "the physical face the shell normal (+Z) leaves",
}
NOTES = ("No orientation is chosen by MAC, frequency or shape similarity.",
         "A computational convention is never physical evidence.",
         "A complete evidence set is not a frozen registration: freezing, pairing and MAC are separate owner decisions.")


@dataclass(frozen=True)
class EvidenceFact:
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


@dataclass(frozen=True)
class EvidenceResult:
    status: str
    scan_to_plate: LinkResult
    plate_to_fe: LinkResult
    checks: tuple  # (check, state, detail)
    missing: tuple  # (key, reason)
    transform: Optional[dict] = None
    synthetic: bool = False
    frozen: bool = False  # never created here
    mac_computed: bool = False
    notes: tuple = field(default=NOTES)


def _independent(fact: EvidenceFact, facts: Mapping[str, EvidenceFact], kind: str, seen=()) -> bool:
    if fact.provenance in INDEPENDENT or (kind == SYNTHETIC_DEMO and fact.provenance == SYNTHETIC):
        return True
    if fact.provenance != DERIVED or not fact.derived_from:
        return False
    return all(key in facts and key not in seen and _independent(facts[key], facts, kind, seen + (fact.key,))
               for key in fact.derived_from)


def _link(name: str, keys: Sequence[str], facts: Mapping[str, EvidenceFact], kind: str) -> LinkResult:
    missing, shown = [], []
    for key in keys:
        fact = facts.get(key)
        if fact is None or fact.value in (None, ""):
            missing.append((key, f"missing: {WHY[key]}"))
            continue
        shown.append((key, fact.value, fact.provenance, fact.source))
        if fact.provenance == SYNTHETIC and kind != SYNTHETIC_DEMO:
            missing.append((key, f"SYNTHETIC value in a physical study: not evidence ({WHY[key]})"))
        elif fact.provenance == CONVENTION_ONLY:
            missing.append((key, f"a computational convention is not physical evidence ({WHY[key]})"))
        elif not _independent(fact, facts, kind):
            missing.append((key, f"{fact.provenance}: not independent evidence ({WHY[key]})"))
    return LinkResult(name, LINK_VERIFIED if not missing else LINK_OPEN, tuple(shown), tuple(missing))


# ----------------------------------------------------------------------------- values typed by the user

def parse_fact_value(key: str, text: str) -> Any:
    """The typed value of a fact from its text (the GUI's form); raises ValueError with the expected form."""
    text = str(text).strip()
    if key not in FACT_KEYS:
        raise ValueError(f"unknown fact {key!r}")
    if not text:
        return None
    if key in ("grid_plus_u_edge", "grid_plus_v_edge"):
        return int(text)
    if key == "fe_origin_corner":
        parts = [int(p) for p in text.replace("/", ",").split(",") if p.strip()]
        if len(parts) != 2:
            raise ValueError("fe_origin_corner: two adjacent edges, for example 3,4")
        return parts
    if key == "scan_window_offsets_mm":
        out = {}
        for part in text.split(","):
            name, _, number = part.partition("=")
            out[name.strip().replace("−", "-")] = float(number)
        return out
    if key == "scan_scale":
        name, _, number = text.partition("=")
        return {"mm_per_unit": float(number if number else name)}
    if key == "scan_metric_geometry":
        return text.lower() in ("yes", "true", "1", "physical")
    return text


def fact_text(key: str, value: Any) -> str:
    """The form text of a typed value (the inverse of ``parse_fact_value``)."""
    if value is None:
        return ""
    if key == "fe_origin_corner":
        return ",".join(str(v) for v in value)
    if key == "scan_window_offsets_mm" and isinstance(value, Mapping):
        return ", ".join(f"{k}={v:g}" for k, v in value.items())
    if key == "scan_scale" and isinstance(value, Mapping):
        return f"mm_per_unit={value.get('mm_per_unit')}"
    if key == "scan_metric_geometry":
        return "yes" if value else "no"
    return str(value)


# ----------------------------------------------------------------------------- geometry of the evidence

def _edge(value) -> Optional[np.ndarray]:
    try:
        return EDGE_DIRECTION[int(value)]
    except (KeyError, TypeError, ValueError):
        return None


def _corners(plan_mm: Sequence[float]) -> dict:
    a, b = float(plan_mm[0]), float(plan_mm[1])
    return {frozenset((3, 4)): (0.0, 0.0), frozenset((2, 3)): (a, 0.0), frozenset((1, 2)): (a, b),
            frozenset((1, 4)): (0.0, b)}


def _scan_to_phi(facts: Mapping[str, EvidenceFact]) -> tuple[Optional[np.ndarray], list]:
    face = facts["scanned_face"].value
    u_phi, v_phi = _edge(facts["grid_plus_u_edge"].value), _edge(facts["grid_plus_v_edge"].value)
    if face not in FACES:
        return None, [("scanned face", "REFUSED", f"{face!r} is not a physical face {FACES}")]
    if u_phi is None or v_phi is None:
        return None, [("grid edges", "REFUSED", "an edge is not one of 1–4")]
    if abs(float(u_phi @ v_phi)) > 0.5:
        return None, [("grid edges", "REFUSED", "the +u and +v edges must be adjacent edges (not the same or opposite)")]
    rotation = np.column_stack([u_phi, v_phi, np.array([0.0, 0.0, 1.0 if face == "marked" else -1.0])])
    if np.linalg.det(rotation) < 0:
        return None, [("handedness of the scan link", "REFUSED",
                       "the face and the two edges describe a mirror image: they cannot all be true")]
    return rotation, [("handedness of the scan link", "CONSISTENT", "face and edges form a proper rotation")]


def _phi_to_fe(facts: Mapping[str, EvidenceFact], plan_mm) -> tuple:
    """(rotation Φ → FE, FE origin in Φ, FE plan expected (X, Y) in mm, checks)."""
    along = str(facts["fe_x_along_edges"].value).replace(" ", "")
    if along not in ("1/3", "2/4"):
        return None, None, None, [("FE X axis", "REFUSED", "FE X must run along the edges 1/3 or 2/4")]
    try:
        corner = frozenset(int(e) for e in facts["fe_origin_corner"].value)
    except (TypeError, ValueError):
        corner = frozenset()
    corners = _corners(plan_mm)
    if corner not in corners:
        return None, None, None, [("FE origin corner", "REFUSED", "the corner must be named by two adjacent edges")]
    origin = np.array([*corners[corner], 0.0])
    along_a = np.array([1.0 if origin[0] == 0.0 else -1.0, 0.0, 0.0])  # away from the origin along a
    along_b = np.array([0.0, 1.0 if origin[1] == 0.0 else -1.0, 0.0])
    x, y = (along_a, along_b) if along == "1/3" else (along_b, along_a)
    z = np.cross(x, y)  # the FE frame is right-handed
    expected = "marked" if z[2] > 0 else "unmarked"
    face = facts["fe_normal_face"].value
    checks = []
    if face != expected:
        checks.append(("FE normal against the origin corner", "REFUSED",
                       f"with FE (0, 0) at the corner of edges {sorted(corner)} and X along {along} the right-handed FE "
                       f"+Z leaves the {expected} face, not the {face!r} face"))
        return None, None, None, checks
    checks.append(("FE normal against the origin corner", "CONSISTENT", f"+Z leaves the {expected} face"))
    plan = (float(plan_mm[0]), float(plan_mm[1])) if along == "1/3" else (float(plan_mm[1]), float(plan_mm[0]))
    return np.vstack([x, y, z]), origin, plan, checks


def _scale(value) -> Optional[float]:
    try:
        scale = float((value or {}).get("mm_per_unit"))
    except (AttributeError, TypeError, ValueError):
        return None
    return scale if math.isfinite(scale) and scale > 0 else None


def _offsets(value) -> tuple[Optional[dict], str]:
    if not isinstance(value, Mapping):
        return None, f"the offsets {value!r} are not a mapping of −u, +u, −v, +v in mm"
    out = {}
    for key in ("-u", "+u", "-v", "+v"):
        item = value.get(key)
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(float(item)):
            return None, f"the offset {key} is missing or not a finite number of mm"
        if float(item) < 0:
            return None, f"the offset {key} = {item} is negative: it puts measured points outside the plate"
        out[key] = float(item)
    return out, ""


def _window(facts, rotation, coordinates, plan_mm, tolerance_mm) -> tuple:
    angle, u, v = grid_axes(coordinates)
    scale = _scale(facts["scan_scale"].value)
    xy = coordinates[:, :2] - coordinates[:, :2].mean(axis=0)
    su, sv = xy @ u * scale, xy @ v * scale
    offsets, reason = _offsets(facts["scan_window_offsets_mm"].value)
    if offsets is None:
        return ("scan window", "REFUSED", reason), None
    width_u = su.max() - su.min() + offsets["-u"] + offsets["+u"]
    width_v = sv.max() - sv.min() + offsets["-v"] + offsets["+v"]
    length_u = plan_mm[0] if abs(rotation[0, 0]) > 0.5 else plan_mm[1]
    length_v = plan_mm[0] if abs(rotation[0, 1]) > 0.5 else plan_mm[1]
    if abs(width_u - length_u) > tolerance_mm or abs(width_v - length_v) > tolerance_mm:
        return ("scan window", "REFUSED", f"window + offsets give {width_u:.2f} × {width_v:.2f} mm along u × v, the "
                f"plate {length_u:g} × {length_v:g} mm (tolerance {tolerance_mm:g} mm)"), None
    return (("scan window", "CONSISTENT", f"window + offsets close the plate to {width_u:.2f} × {width_v:.2f} mm "
             f"(grid angle {angle:.2f}°)"),
            {"angle_deg": angle, "u": u.tolist(), "v": v.tolist(), "mm_per_unit": scale,
             "centre": coordinates[:, :2].mean(axis=0).tolist(), "su_min": float(su.min()), "sv_min": float(sv.min()),
             "offsets_mm": offsets})


def evaluate(facts: Sequence[EvidenceFact], plan_mm: Optional[Sequence[float]], plan_tolerance_mm: Optional[float],
             kind: str = PHYSICAL, scan_coordinates_m: Optional[np.ndarray] = None,
             fe_plan_mm: Optional[Sequence[float]] = None) -> EvidenceResult:
    """The readiness of a physical registration of this plate from ``facts``. ``plan_mm`` (a, b) and its tolerance
    come from the passport; the data's numbers are used only for compatibility checks, never to choose a fact."""
    by_key = {fact.key: fact for fact in facts}
    scan = _link("scanner → physical plate", SCAN_FACTS, by_key, kind)
    fe = _link("physical plate → FE model", FE_FACTS, by_key, kind)
    checks = []
    plan_ok = (plan_mm is not None and len(plan_mm) == 2 and all(isinstance(v, (int, float)) and math.isfinite(v)
                                                                  and v > 0 for v in plan_mm))
    tolerance_ok = plan_tolerance_mm is not None and math.isfinite(plan_tolerance_mm) and plan_tolerance_mm >= 0
    if not plan_ok:
        checks.append(("plate plan", "REFUSED", "the passport has no measured length and width"))
    if not tolerance_ok:
        checks.append(("plan tolerance", "REFUSED", "the passport gives no uncertainty or resolution of the length and "
                       "width: the closure of the scan window and the FE plan cannot be checked"))
    dof = by_key.get("measured_dof")
    components = "".join(sorted(set(str(dof.value).upper()))) if dof and dof.value else ""
    if components:
        checks.append(("measured DOF", "CONSISTENT" if components == "Z" else "REFUSED",
                       "out-of-plane Z only: compatible with the shell mid-surface normal" if components == "Z" else
                       f"measured components {dof.value!r}: an in-plane DOF needs a full 3-D registration"))
    rotation = fe_rotation = origin = placement = None
    if scan.status == LINK_VERIFIED:
        rotation, scan_checks = _scan_to_phi(by_key)
        checks += scan_checks
        if _scale(by_key["scan_scale"].value) is None:
            checks.append(("scan scale", "REFUSED", "the scale needs a positive, finite mm_per_unit"))
            rotation = None
        if by_key["scan_metric_geometry"].value is not True:
            checks.append(("scan metric", "REFUSED", "the scan coordinates are not stated to be physical positions"))
            rotation = None
    if fe.status == LINK_VERIFIED and plan_ok:
        fe_rotation, origin, expected_fe_plan, fe_checks = _phi_to_fe(by_key, plan_mm)
        checks += fe_checks
        if fe_rotation is not None and fe_plan_mm is not None and tolerance_ok:
            ok = all(abs(float(a) - b) <= plan_tolerance_mm for a, b in zip(fe_plan_mm, expected_fe_plan))
            checks.append(("FE plan against the passport", "CONSISTENT" if ok else "REFUSED",
                           f"FE extent X × Y {float(fe_plan_mm[0]):.2f} × {float(fe_plan_mm[1]):.2f} mm, expected "
                           f"{expected_fe_plan[0]:g} × {expected_fe_plan[1]:g} mm ±{plan_tolerance_mm:g}"))
    if rotation is not None and scan_coordinates_m is not None and plan_ok and tolerance_ok:
        check, placement = _window(by_key, rotation, np.asarray(scan_coordinates_m, dtype=float), plan_mm,
                                   plan_tolerance_mm)
        checks.append(check)
    elif rotation is not None and scan_coordinates_m is None:
        checks.append(("scan window", "OPEN", "no scan coordinates were read: the window cannot be closed"))
    refused = [c for c in checks if c[1] in ("REFUSED", "OPEN")]
    complete = (scan.status == LINK_VERIFIED and fe.status == LINK_VERIFIED and not refused
                and rotation is not None and fe_rotation is not None and placement is not None)
    transform = None
    if complete:
        transform = {"scan_to_phi": rotation.tolist(), "phi_to_fe": fe_rotation.tolist(),
                     "scan_to_fe": (fe_rotation @ rotation).tolist(), "fe_origin_in_phi_mm": origin.tolist(),
                     "plan_mm": [float(plan_mm[0]), float(plan_mm[1])], "grid": placement,
                     "basis": "the evidence only (no MAC, frequency or shape)"}
    missing = scan.missing + fe.missing + tuple((c[0], c[2]) for c in refused)
    return EvidenceResult(COMPLETE if complete else REGISTRATION_NOT_VERIFIED, scan, fe, tuple(checks), missing,
                          transform, synthetic=kind == SYNTHETIC_DEMO)


def map_points_to_fe(result: EvidenceResult, coordinates_m: np.ndarray) -> np.ndarray:
    """FE (X, Y) in mm of scan points under a complete evidence set (a check of the evidence; no pairing, no MAC)."""
    if result.status != COMPLETE or result.transform is None:
        raise ValueError(f"{result.status}: no transform without a complete evidence set")
    t = result.transform
    grid, plan = t["grid"], t["plan_mm"]
    rotation, fe_rotation = np.array(t["scan_to_phi"]), np.array(t["phi_to_fe"])
    origin = np.array(t["fe_origin_in_phi_mm"])
    xy = np.asarray(coordinates_m, dtype=float)[:, :2] - np.array(grid["centre"])
    su = xy @ np.array(grid["u"]) * grid["mm_per_unit"] - grid["su_min"] + grid["offsets_mm"]["-u"]
    sv = xy @ np.array(grid["v"]) * grid["mm_per_unit"] - grid["sv_min"] + grid["offsets_mm"]["-v"]
    start = np.zeros(3)
    for direction in (rotation[:, 0], rotation[:, 1]):
        axis = 0 if abs(direction[0]) > 0.5 else 1
        start[axis] = 0.0 if direction[axis] > 0 else plan[axis]
    phi = start[None, :] + su[:, None] * rotation[:, 0][None, :] + sv[:, None] * rotation[:, 1][None, :]
    return ((phi - origin[None, :]) @ fe_rotation.T)[:, :2]


__all__ = ["COMPLETE", "EvidenceFact", "EvidenceResult", "FACT_KEYS", "PHYSICAL", "PROVENANCES",
           "REGISTRATION_NOT_VERIFIED", "SYNTHETIC", "SYNTHETIC_DEMO", "WHY", "evaluate", "fact_text",
           "map_points_to_fe", "parse_fact_value"]
