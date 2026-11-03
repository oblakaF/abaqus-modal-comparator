"""UNIVERSAL-REG-1: a diagnostic FE <-> experimental geometry mapping from stated physical evidence, for any geometry.

The user states the coordinate units, the experimental axes in the FE frame, the measured side, the measured DOFs, and
independently identified landmarks (experimental point <-> FE node). The orientation and the position come only from
these statements; the service reads node labels and coordinates, and the measured-DOF masks of the experimental records.
It reads no FE mode shape and no frequency, computes no modal quantity, and never chooses among orientations.

The rule x_fe = R (s x_exp) + t, with s from the units, a proper rotation R and t from the evidence:

- all three axes stated: R is the signed permutation they define, and t comes from at least one landmark;
- four or more non-coplanar landmarks: R is their rigid fit;
- three or more non-collinear coplanar landmarks: R is their rigid fit, and a stated axis out of their plane must fix
  which way the plane faces (the landmarks alone cannot);
- anything less is ambiguous, and a mirrored statement or a mirrored landmark set is refused.

The result is a proposal for these exact data. Any missing, contradictory or ambiguous evidence gives
REGISTRATION_REQUIRED with the reasons. A proposal is not a ``FrozenRegistration``: nothing here can reach a comparator.
The mapping limits are those of the guided registration (the comparator's geometry limits).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import itertools
import json
from typing import Mapping, Optional

import numpy as np
from scipy.spatial import cKDTree

from reviewed_core import experimental_measurement_masks
from scientific_state import modal_dataset_geometry_identity

from .guided_registration import MAXIMUM_NORMALIZED_RMS, MINIMUM_MATCHED_FRACTION

REGISTRATION_REQUIRED = "REGISTRATION_REQUIRED"
REGISTRATION_PROPOSED = "REGISTRATION_PROPOSED"
UNIT_IN_METRES = {"m": 1.0, "cm": 0.01, "mm": 0.001, "in": 0.0254}
UNITS = tuple(UNIT_IN_METRES)
DIRECTIONS = ("+X", "-X", "+Y", "-Y", "+Z", "-Z")
DOFS = ("x", "y", "z")
GEOMETRY_TOLERANCE = 0.03  # of the scan diagonal, the comparator's geometry tolerance
RANK_RATIO = 0.05  # a landmark set thinner than this share of its length has no usable extent in that direction
STATED_AXIS_DEGREES = 5.0  # how far landmarks may turn a stated axis
TIE_SHARE = 0.01  # of the tolerance: two FE nodes this close in distance cannot separate a point
CANDIDATE_NODES = 8
MAX_SYMMETRY_POINTS = 300

# what stops a proposal
MISSING = "MISSING_EVIDENCE"
AMBIGUOUS = "AMBIGUOUS_ORIENTATION"
MIRRORED = "MIRRORED_ORIENTATION"
LANDMARK = "LANDMARK_MISMATCH"
MAPPING = "MAPPING_DISTANCE"
SHARED = "SHARED_FE_NODE"
SIDE = "MEASURED_SIDE_MISMATCH"
DOF = "DOF_INCOMPATIBLE"
GEOMETRY = "GEOMETRY_INVALID"
LOCAL_AXES = "LOCAL_COORDINATE_SYSTEMS"
STALE = "FILES_CHANGED"
LIMIT = "Diagnostic only: this mapping is not applied. No MAC and no mode pair is computed from it."


@dataclass(frozen=True)
class Evidence:
    """What the user states. Nothing has a default that could pass for a statement."""

    fe_unit: str = ""
    experimental_unit: str = ""
    axes: tuple = ("", "", "")  # the FE direction of experimental +x, +y, +z ("" when not stated)
    measured_side: str = ""  # the FE direction the measured face looks towards
    measured_dofs: tuple = ()  # experimental components ("x", "y", "z")
    landmarks: tuple = ()  # (experimental point, FE node) identified independently of any modal result
    source: str = ""  # how the statements were established

    @property
    def evidence_hash(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True, default=str).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Problem:
    code: str
    text: str


@dataclass(frozen=True)
class MappedPoint:
    experimental_point: str
    fe_node: str
    distance: float  # in FE units
    landmark: bool


@dataclass(frozen=True)
class Proposal:
    status: str
    problems: tuple = ()
    warnings: tuple = ()
    checks: tuple = ()
    mapping: tuple = ()  # MappedPoint; empty unless the orientation is settled
    axes_in_fe: tuple = ()  # the FE direction of experimental +x, +y, +z, as text
    rotation: tuple = ()
    translation: tuple = ()
    scale: Optional[float] = None
    metrics: Mapping = field(default_factory=dict)
    evidence_hash: str = ""
    fe_geometry_sha256: str = ""
    limit: str = LIMIT

    @property
    def proposed(self) -> bool:
        return self.status == REGISTRATION_PROPOSED


def _vector(direction: str) -> np.ndarray:
    vector = np.zeros(3)
    vector["XYZ".index(direction[1])] = 1.0 if direction[0] == "+" else -1.0
    return vector


def _names(dataset, label: str, problems: list) -> Optional[tuple]:
    """(labels, coordinates) of a dataset whose records all share one geometry, or None with the reason."""
    modes = list(getattr(dataset, "modes", ()) or ())
    if not modes:
        problems.append(Problem(GEOMETRY, f"The {label} data hold no records."))
        return None
    names = [str(value) for value in np.asarray(modes[0].node_ids, dtype=object)]
    points = np.asarray(modes[0].coordinates, dtype=float)
    if len(set(names)) != len(names):
        problems.append(Problem(GEOMETRY, f"The {label} data repeat a node or point label."))
        return None
    if not np.isfinite(points).all():
        problems.append(Problem(GEOMETRY, f"The {label} coordinates are not all finite."))
        return None
    for mode in modes[1:]:
        if ([str(value) for value in np.asarray(mode.node_ids, dtype=object)] != names
                or not np.array_equal(np.asarray(mode.coordinates, dtype=float), points)):
            problems.append(Problem(GEOMETRY, f"The {label} records do not share one geometry."))
            return None
    return names, points


def _extent(points: np.ndarray) -> float:
    return float(np.linalg.norm(np.ptp(points, axis=0))) if len(points) else 0.0


def geometry_summary(fe_dataset, experimental_dataset) -> tuple:
    """Lines that help the user state the evidence: counts, extents and the label forms; nothing is proposed."""
    lines = []
    for label, dataset in (("FE", fe_dataset), ("Experimental", experimental_dataset)):
        found = _names(dataset, label, [])
        if found is None:
            continue
        names, points = found
        low, high = points.min(axis=0), points.max(axis=0)
        ranges = ", ".join(f"{axis} {a:.4g} to {b:.4g}" for axis, a, b in zip("xyz", low, high))
        lines.append(f"{label}: {len(names)} points ({ranges}). Labels like {names[0]}, {names[-1]}.")
    return tuple(lines)


def _resolve_fe_label(label: str, names: list, lookup: dict) -> tuple:
    """The FE row of a stated node: the exact label, or a bare number found in exactly one instance."""
    if label in lookup:
        return lookup[label], ""
    matches = [row for row, name in enumerate(names) if name.rpartition(":")[2] == label]
    if len(matches) == 1:
        return matches[0], ""
    if len(matches) > 1:
        return None, f"FE node {label} exists in {len(matches)} instances; give it as INSTANCE:{label}."
    return None, f"FE node {label} is not in the FE results."


def _landmarks(evidence: Evidence, experimental_names: list, fe_names: list, problems: list) -> tuple:
    """(experimental rows, FE rows) of the stated landmarks."""
    experimental_lookup = {name: row for row, name in enumerate(experimental_names)}
    fe_lookup = {name: row for row, name in enumerate(fe_names)}
    rows_e, rows_f = [], []
    for point, node in evidence.landmarks:
        point, node = str(point).strip(), str(node).strip()
        if point not in experimental_lookup:
            problems.append(Problem(LANDMARK, f"Experimental point {point} is not in the experimental data."))
            continue
        row, reason = _resolve_fe_label(node, fe_names, fe_lookup)
        if reason:
            problems.append(Problem(LANDMARK, reason))
            continue
        rows_e.append(experimental_lookup[point])
        rows_f.append(row)
    if len(set(rows_e)) != len(rows_e) or len(set(rows_f)) != len(rows_f):
        problems.append(Problem(LANDMARK, "A landmark repeats an experimental point or an FE node."))
    return rows_e, rows_f


def _stated_axes(evidence: Evidence, problems: list) -> list:
    """(experimental axis index, FE vector) of each stated axis."""
    stated = [(index, _vector(text)) for index, text in enumerate(evidence.axes) if text]
    letters = [text[1] for text in evidence.axes if text]
    if len(set(letters)) != len(letters):
        problems.append(Problem(AMBIGUOUS, f"Two experimental axes are stated along one FE axis: {list(evidence.axes)}."))
    return stated


def _rigid_fit(a: np.ndarray, b: np.ndarray) -> tuple:
    """The proper rotation of the rigid fit a -> b, and whether the unconstrained best fit is a reflection."""
    a_c, b_c = a - a.mean(axis=0), b - b.mean(axis=0)
    u, _s, vt = np.linalg.svd(a_c.T @ b_c)
    sign = float(np.sign(np.linalg.det(vt.T @ u.T))) or 1.0
    return vt.T @ np.diag([1.0, 1.0, sign]) @ u.T, sign < 0.0


def _rotation(evidence: Evidence, a: np.ndarray, b: np.ndarray, stated: list, problems: list, checks: list):
    """R from the evidence, or None with the reason. Only the stated axes and landmark coordinates are used."""
    if len(stated) == 3:
        rotation = np.column_stack([vector for _index, vector in stated])
        if float(np.linalg.det(rotation)) < 0.0:
            problems.append(Problem(MIRRORED, f"The stated axes {list(evidence.axes)} are left-handed: they mirror the "
                                              "FE model. A mirrored orientation is not accepted."))
            return None
        checks.append(f"Orientation from the stated axes {list(evidence.axes)} (right-handed).")
        return rotation
    values = np.linalg.svd(a - a.mean(axis=0), compute_uv=False) if len(a) > 1 else np.zeros(3)
    values = np.pad(values, (0, max(0, 3 - len(values))))
    planar = values[0] > 0.0 and values[1] / values[0] >= RANK_RATIO
    solid = planar and len(a) >= 4 and values[2] / values[0] >= RANK_RATIO
    if not planar:
        problems.append(Problem(AMBIGUOUS, "The landmarks lie on a line or are too few, so they leave a rotation free. "
                                           "State all three axes, or give landmarks that span a plane."))
        return None
    rotation, reflected = _rigid_fit(a, b)
    if solid:
        if reflected:
            problems.append(Problem(MIRRORED, "The non-coplanar landmarks fit the FE model only as a mirror image. A "
                                              "mirrored orientation is not accepted."))
            return None
        checks.append(f"Orientation from the rigid fit of {len(a)} non-coplanar landmarks.")
    else:
        _u, _s, vt = np.linalg.svd(a - a.mean(axis=0))
        normal = vt[2]
        if not any(abs(normal[index]) > 0.5 for index, _vector_ in stated):
            problems.append(Problem(AMBIGUOUS, "The landmarks lie in one plane, so they cannot show which way it faces. "
                                               "State an experimental axis that points out of that plane."))
            return None
        checks.append(f"Orientation from the rigid fit of {len(a)} coplanar landmarks; the facing from a stated axis.")
    limit = np.cos(np.radians(STATED_AXIS_DEGREES))
    for index, vector in stated:
        if float(rotation[:, index] @ vector) < limit:
            names = "xyz"
            problems.append(Problem(LANDMARK, f"The landmarks turn experimental +{names[index]} more than "
                                              f"{STATED_AXIS_DEGREES:g} degrees from the stated "
                                              f"{evidence.axes[index]}: the evidence contradicts itself."))
            return None
    return rotation


def _visible(row: int, fe_points: np.ndarray, side: np.ndarray, lateral_tree, lateral: np.ndarray, tolerance: float,
             memory: dict) -> bool:
    """No other FE node lies in front of this node as seen from the measured side."""
    if row not in memory:
        near = lateral_tree.query_ball_point(lateral[row], tolerance)
        depth = fe_points[near] @ side
        memory[row] = bool(depth.max() <= float(fe_points[row] @ side) + tolerance)
    return memory[row]


def _lateral(points: np.ndarray, side: np.ndarray) -> np.ndarray:
    axes = [index for index in range(3) if side[index] == 0.0]
    return points[:, axes]


def _map_points(mapped: np.ndarray, fe_points: np.ndarray, side: np.ndarray, tolerance: float, fixed: dict) -> tuple:
    """Each point's nearest FE node on the measured side (a landmark keeps its stated node).

    Returns (FE rows, hidden rows among the stated or nearest nodes, ties)."""
    tree = cKDTree(fe_points)
    lateral = _lateral(fe_points, side)
    lateral_tree = cKDTree(lateral)
    k = min(CANDIDATE_NODES, len(fe_points))
    distances, rows = tree.query(mapped, k=k)
    distances, rows = np.asarray(distances).reshape(len(mapped), k), np.asarray(rows).reshape(len(mapped), k)
    chosen, hidden, ties, memory = [], [], 0, {}
    for index in range(len(mapped)):
        if index in fixed:
            chosen.append(fixed[index])
            if not _visible(fixed[index], fe_points, side, lateral_tree, lateral, tolerance, memory):
                hidden.append(index)
            continue
        visible = [position for position in range(k)
                   if _visible(int(rows[index, position]), fe_points, side, lateral_tree, lateral, tolerance, memory)]
        if 0 not in visible:
            hidden.append(index)
        position = visible[0] if visible else 0
        chosen.append(int(rows[index, position]))
        if len(visible) > 1 and distances[index, visible[1]] - distances[index, position] <= TIE_SHARE * tolerance:
            ties += 1
    return np.asarray(chosen, dtype=int), hidden, ties


def _other_orientations(mapped: np.ndarray, fe_points: np.ndarray, tolerance: float, diagonal: float) -> int:
    """How many other proper axis-aligned orientations the geometry alone would also accept (never chosen; stated)."""
    points = mapped if len(mapped) <= MAX_SYMMETRY_POINTS else mapped[:: len(mapped) // MAX_SYMMETRY_POINTS + 1]
    centre = points.mean(axis=0)
    tree = cKDTree(fe_points)
    count = 0
    for order in itertools.permutations(range(3)):
        for signs in itertools.product((1.0, -1.0), repeat=3):
            turn = np.zeros((3, 3))
            for column, row in enumerate(order):
                turn[row, column] = signs[column]
            if float(np.linalg.det(turn)) < 0.0 or np.array_equal(turn, np.eye(3)):
                continue
            moved = (points - centre) @ turn.T + centre
            if float(np.linalg.norm(moved - points, axis=1).max()) <= tolerance:
                continue  # this turn moves nothing that can be observed
            distances, _rows = tree.query(moved)
            if (float(np.mean(distances <= tolerance)) >= MINIMUM_MATCHED_FRACTION
                    and float(np.sqrt(np.mean(distances ** 2))) / diagonal <= MAXIMUM_NORMALIZED_RMS):
                count += 1
    return count


def _check_dofs(evidence: Evidence, modes: list, reference: np.ndarray, problems: list, warnings: list,
                checks: list) -> None:
    """The stated measured components against the experimental records' own measured-DOF masks."""
    masks = np.asarray(experimental_measurement_masks(modes, reference))
    records_with = masks.any(axis=1)  # records x components: this record measures this component somewhere
    every = records_with.all(axis=0)
    some = records_with.any(axis=0)
    stated = {"xyz".index(name) for name in evidence.measured_dofs}
    for index, name in enumerate("xyz"):
        if index in stated and not every[index]:
            count = int(records_with[:, index].sum())
            problems.append(Problem(DOF, f"Experimental {name} is stated as measured, but {count} of {len(modes)} "
                                         "records hold it."))
        if index not in stated and some[index]:
            problems.append(Problem(DOF, f"Experimental {name} is measured in the file, but it is not stated."))
    for index in sorted(stated):
        coverage = float(masks[:, :, index].mean())
        if every[index] and coverage < 1.0:
            warnings.append(f"Experimental {'xyz'[index]} covers {coverage:.0%} of the points and records.")
    if not problems:
        checks.append(f"Measured DOFs {'/'.join(sorted(evidence.measured_dofs))} agree with the experimental records.")


def _direction_text(vector: np.ndarray) -> str:
    row = int(np.argmax(np.abs(vector)))
    if abs(abs(vector[row]) - 1.0) < 1.0e-9:
        return ("+" if vector[row] > 0 else "-") + "XYZ"[row]
    return "(" + ", ".join(f"{value:+.3f}" for value in vector) + ")"


def _missing(evidence: Evidence) -> list:
    missing = []
    if evidence.fe_unit not in UNIT_IN_METRES or evidence.experimental_unit not in UNIT_IN_METRES:
        missing.append("the coordinate units of both files")
    if evidence.measured_side not in DIRECTIONS:
        missing.append("the measured side")
    if not evidence.measured_dofs or not set(evidence.measured_dofs) <= set(DOFS):
        missing.append("the measured DOFs")
    if not evidence.landmarks:
        missing.append("at least one landmark (experimental point, FE node)")
    if any(text and text not in DIRECTIONS for text in evidence.axes):
        missing.append("valid axis directions")
    if not evidence.source.strip():
        missing.append("how the evidence was established")
    return missing


def required(problems, *, evidence: Optional[Evidence] = None, **fields) -> Proposal:
    return Proposal(REGISTRATION_REQUIRED, tuple(problems), evidence_hash=evidence.evidence_hash if evidence else "",
                    **fields)


def propose(fe_dataset, experimental_dataset, evidence: Evidence) -> Proposal:
    """The mapping the evidence defines on these data, or REGISTRATION_REQUIRED with every reason found."""
    problems: list = []
    missing = _missing(evidence)
    if missing:
        problems.append(Problem(MISSING, "Still needed: " + "; ".join(missing) + "."))
    fe = _names(fe_dataset, "FE", problems)
    experimental = _names(experimental_dataset, "experimental", problems)
    if experimental is not None and len(experimental[0]) < 2:
        problems.append(Problem(GEOMETRY, "At least two experimental points are needed."))
    diagnostics = dict(getattr(experimental_dataset, "metadata", None) or {}).get("local_coordinate_system_diagnostics")
    if isinstance(diagnostics, Mapping) and any(diagnostics.values()):
        problems.append(Problem(LOCAL_AXES, "The experimental file uses local coordinate systems, and the importer does "
                                            "not rotate into them, so the stated axes cannot be checked."))
    if missing or fe is None or experimental is None or problems:
        return required(problems, evidence=evidence)

    checks: list = [f"Evidence stated by the user: {evidence.source.strip()}."]
    warnings: list = []
    fe_names, fe_points = fe
    experimental_names, experimental_points = experimental
    scale = UNIT_IN_METRES[evidence.experimental_unit] / UNIT_IN_METRES[evidence.fe_unit]
    checks.append(f"Units: experimental {evidence.experimental_unit}, FE {evidence.fe_unit} (factor {scale:g}).")
    scaled = experimental_points * scale
    diagonal = _extent(scaled)
    if diagonal <= 0.0:
        return required([Problem(GEOMETRY, "All experimental points coincide.")], evidence=evidence)
    tolerance = max(GEOMETRY_TOLERANCE * diagonal, 1.0e-12)

    modes = list(experimental_dataset.modes)
    _check_dofs(evidence, modes, np.asarray(modes[0].node_ids, dtype=object), problems, warnings, checks)
    stated = _stated_axes(evidence, problems)
    rows_e, rows_f = _landmarks(evidence, experimental_names, fe_names, problems)
    if any(problem.code in (LANDMARK, AMBIGUOUS) for problem in problems) or not rows_e:
        return required(problems, evidence=evidence, checks=tuple(checks))

    a, b = scaled[rows_e], fe_points[rows_f]
    rotation = _rotation(evidence, a, b, stated, problems, checks)
    if rotation is None:
        return required(problems, evidence=evidence, checks=tuple(checks))
    translation = (b - a @ rotation.T).mean(axis=0)
    residuals = np.linalg.norm(a @ rotation.T + translation - b, axis=1)
    worst = float(residuals.max())
    if worst > tolerance:
        hint = ""
        spread_a, spread_b = float(np.linalg.norm(a - a.mean(axis=0))), float(np.linalg.norm(b - b.mean(axis=0)))
        if spread_a > 0.0 and not 0.8 <= spread_b / spread_a <= 1.25:
            hint = f" The landmark distances differ by a factor of {spread_b / spread_a:.3g}: check the units."
        problems.append(Problem(LANDMARK, f"The landmarks disagree with the stated orientation: worst distance "
                                          f"{worst:.4g} {evidence.fe_unit}, limit {tolerance:.4g}.{hint}"))
        return required(problems, evidence=evidence, checks=tuple(checks))
    if len(rows_e) == 1:
        warnings.append("One landmark fixes the position and cannot check it; a second one would.")
    else:
        checks.append(f"{len(rows_e)} landmarks agree: worst distance {worst:.4g} {evidence.fe_unit}.")

    mapped = scaled @ rotation.T + translation
    side = _vector(evidence.measured_side)
    if float(np.ptp(fe_points @ side)) <= tolerance:
        warnings.append(f"The FE nodes have no depth along {evidence.measured_side}: the measured side is stated, and "
                        "the mesh cannot confirm it.")
    chosen, hidden, ties = _map_points(mapped, fe_points, side, tolerance, dict(zip(rows_e, rows_f)))
    distances = np.linalg.norm(fe_points[chosen] - mapped, axis=1)
    matched = float(np.mean(distances <= tolerance))
    rms = float(np.sqrt(np.mean(distances ** 2)))
    if hidden and (matched < MINIMUM_MATCHED_FRACTION or set(hidden) & set(rows_e)):
        problems.append(Problem(SIDE, f"{len(hidden)} points lie on FE nodes hidden from the stated side "
                                      f"{evidence.measured_side}."))
    if matched < MINIMUM_MATCHED_FRACTION:
        problems.append(Problem(MAPPING, f"Only {matched:.1%} of the points lie within {tolerance:.4g} "
                                         f"{evidence.fe_unit} of an FE node (at least "
                                         f"{MINIMUM_MATCHED_FRACTION:.0%} required)."))
    if rms / diagonal > MAXIMUM_NORMALIZED_RMS:
        problems.append(Problem(MAPPING, f"The mapping RMS is {rms / diagonal:.2%} of the scan diagonal (at most "
                                         f"{MAXIMUM_NORMALIZED_RMS:.0%})."))
    if len(set(chosen.tolist())) != len(chosen):
        problems.append(Problem(SHARED, f"{len(chosen) - len(set(chosen.tolist()))} points share an FE node."))
    if ties:
        warnings.append(f"{ties} points are equally near two FE nodes.")
    others = _other_orientations(mapped, fe_points, tolerance, diagonal)
    if others:
        warnings.append(f"The geometry alone also fits {others} other orientations: only your evidence separates them.")
    checks.append(f"Mapping: {matched:.1%} within {tolerance:.4g} {evidence.fe_unit}, RMS {rms:.4g}, largest distance "
                  f"{float(distances.max()):.4g}.")

    landmark_rows = set(rows_e)
    points = tuple(MappedPoint(experimental_names[row], fe_names[int(chosen[row])], float(distances[row]),
                               row in landmark_rows) for row in range(len(chosen)))
    common = dict(warnings=tuple(warnings), checks=tuple(checks), mapping=points, scale=scale,
                  axes_in_fe=tuple(_direction_text(rotation[:, index]) for index in range(3)),
                  rotation=tuple(map(tuple, rotation.tolist())), translation=tuple(translation.tolist()),
                  metrics={"matched_fraction": matched, "rms": rms, "normalized_rms": rms / diagonal,
                           "tolerance": tolerance, "other_orientations": others},
                  evidence_hash=evidence.evidence_hash,
                  fe_geometry_sha256=str(modal_dataset_geometry_identity(fe_dataset)["sha256"]))
    if problems:
        return Proposal(REGISTRATION_REQUIRED, tuple(problems), **common)
    return Proposal(REGISTRATION_PROPOSED, (), **common)


__all__ = ["DIRECTIONS", "DOFS", "Evidence", "LIMIT", "MappedPoint", "Problem", "Proposal", "REGISTRATION_PROPOSED",
           "REGISTRATION_REQUIRED", "UNITS", "geometry_summary", "propose", "required"]
