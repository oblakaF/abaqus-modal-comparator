"""ABM-AUD-5: research estimation of plate bending stiffness from a REGISTERED, curve-fitted modal set (no Qt, no Abaqus).

The route joins what the program already has; it adds no optimizer and no registration:

1. The modal set comes from a mode-shape comparison that was made with a verified or a user-confirmed physical registration
   (``new_gui.analyze_model.registered_source``). Its file, SHA-256, modal set, record numbers, measured DOFs and the
   transform of that comparison are kept. Without such a comparison there is no registered set.
2. The user declares the plate: length, width, thickness, mass and nu12, each with its category (measured, declared,
   imported from the FE model), and states that this plate is the registered FE body and along which FE axes it lies. That
   statement is the only link between the Ritz rectangle and the physical frame; it is never assumed.
3. The measurement points and measured directions are taken into the plate frame, and the Ritz shapes are evaluated there
   by ``plate_ritz_forward.evaluate_ritz_observations`` (Kirchhoff surface kinematics; an unsupported direction is refused
   by that service, not treated as transverse motion).
4. A shape review shows the MAC of every record against every Ritz rank at DECLARED reference constants. It proposes
   nothing: the record -> Ritz rank correspondence is fixed by the user before any fit.
5. The fit is ``research_frequency_tuning.run_tuning`` on frequencies only. With a reviewed correspondence each record is
   compared with the Ritz BRANCH that was fixed (followed by the M-weighted MAC between Ritz shapes), so that a change of
   the frequency order during the search does not silently change the correspondence. MAC is never part of the objective.
6. After the fit the fixed branches are followed from the reference to the fitted values in small steps; a branch that
   cannot be followed, or that the fit did not follow, makes the result diagnostic only.

Every result is a conditional research estimate of the Ritz model. Nothing here is a material property, a production
identification or a statement about another sample.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import inspect
import json
import math
from types import SimpleNamespace
from typing import Mapping, Optional, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment

from domain.plate_material_problem import CoordinateObservationSet, ObservationPoint, PlateForwardRefusal
from modal_core import modal_assurance_criterion
from quality_control import _close_mode_groups
from reviewed_core import _explicit_measurement_mask, _vectors_on_nodes
from services import modal_cluster_service as clusters
from services import plate_ritz_forward as prf
from services import research_frequency_tuning as rft

SCHEMA = "registered-ritz-estimation/1"
LABEL = ("REGISTERED_RITZ_RESEARCH_ESTIMATE — CONDITIONAL_ON_THE_DECLARED_INPUTS — NOT_A_MATERIAL_PROPERTY — "
         "NOT_PRODUCTION_AUTO_ID")
MEASURED, DECLARED, IMPORTED_FE, COMPUTED, ESTIMATE = ("MEASURED", "DECLARED ASSUMPTION", "IMPORTED FROM THE FE MODEL",
                                                      "COMPUTED", "RESEARCH ESTIMATE")
INPUT_CATEGORIES = (MEASURED, DECLARED, IMPORTED_FE)
INPUT_NAMES = ("length", "width", "thickness", "mass", "nu12")
AXES = ("X", "Y", "Z")
AXIS_LENGTH, AXIS_WIDTH = "LENGTH", "WIDTH"

# why a request is refused (``EstimationRefused.code``)
REGISTRATION_REQUIRED, LINK_NOT_ESTABLISHED, UNSUPPORTED_MEASUREMENT, INVALID_INPUT, REVIEW_STALE, MODEL_REFUSED = (
    "REGISTRATION_REQUIRED", "PLATE_LINK_NOT_ESTABLISHED", "UNSUPPORTED_MEASUREMENT", "INVALID_INPUT",
    "SHAPE_REVIEW_NOT_CURRENT", "RITZ_MODEL_REFUSED")

# the kind of correspondence that was fitted
SHAPE_REVIEWED, RANK_HYPOTHESIS = "SHAPE_REVIEWED_FIXED_CORRESPONDENCE", "UNVERIFIED_FREQUENCY_RANK_HYPOTHESIS"
# one record against its fixed Ritz rank
AGREES, UNCERTAIN, CONTRADICTS, NOT_COMPARED = ("SHAPE_AGREES", "CLOSE_GROUP_IDENTITY_UNCERTAIN", "SHAPE_CONTRADICTS",
                                                "NOT_COMPARED")
# one fixed branch between the reviewed reference and the fitted values
TRACKED, AMBIGUOUS, LOST = "TRACKED", "AMBIGUOUS_CROSSING", "BRANCH_LOST"
BRANCHES_TRACKED, BRANCH_NOT_IDENTIFIABLE, BRANCHES_NOT_FOLLOWED = ("BRANCHES_TRACKED", "BRANCH_NOT_IDENTIFIABLE",
                                                                    "NOT_FOLLOWED_NO_SHAPE_REVIEW")
# how the estimate may be presented (a research presentation rule; no governed criterion is involved)
SUPPORTED_ESTIMATE, DIAGNOSTIC_ONLY, NO_ESTIMATE = ("NUMERICALLY_SUPPORTED_RESEARCH_ESTIMATE", "DIAGNOSTIC_ONLY",
                                                    "NO_ESTIMATE")

# Numerical policies, none of them new: the Ritz service's own tracking level for a followed branch, and the smallest
# step of the path between the reference and the fitted values (a step count, not a scientific threshold).
TRACKING_MINIMUM_MAC = inspect.signature(prf.ritz_central_difference_check).parameters["tracking_minimum_mac"].default
SMALLEST_PATH_STEP = 1.0 / 64.0
TRACK_MARGIN = 8  # Ritz modes solved above the highest fixed rank, so that a followed branch stays inside the solve
EDGE_ROUNDING = 1.0e-5  # a point this share of the span outside the rectangle is the file's rounding, not a position
DIRECTION_ROUNDING = 1.0e-9  # the unit-vector tolerance of ObservationPoint
_UNIT_TO_M = {"mm": 1.0e-3, "m": 1.0}

ASSUMPTIONS = (
    "The plate is a thin, flat, homogeneous rectangle (Kirchhoff): no transverse shear, no rotary inertia, constant "
    "thickness and surface mass.",
    "Its principal bending axes lie along its edges (no D16, D26); D12 = nu12 x D22 with nu12 held at the declared value.",
    "It is free on all edges. Suspension stiffness, added mass and damping are not in the model.",
    "The dimensions, thickness, mass and nu12 are held at the declared values; none of them is inferred from frequencies.",
    "That the declared plate is the registered FE body, in the stated position, is the user's statement.",
    "Each measured record is compared with the Ritz mode fixed by the user before the fit; no pairing is made by frequency "
    "agreement or by the fit.",
)
VALIDITY_TEXT = ("NOT ESTABLISHED. A converged optimizer, a small frequency residual and a high shape agreement do not make "
                 "a material property: the estimates are conditional on the declared inputs, the registration and the "
                 "Ritz model, and they were not checked by any independent test.")


class EstimationRefused(rft.TuningRefused):
    """The registered estimation cannot do what was asked; ``code`` names the reason and the message says it in words."""

    def __init__(self, code: str, text: str):
        super().__init__(text)
        self.code = code


# ---------------------------------------------------------------------------------------------- the registered modal set


@dataclass(frozen=True)
class RegisteredSet:
    """A curve-fitted modal set with the registration of the comparison it came from. Coordinates are FE coordinates."""

    source: dict  # the experimental file, its SHA-256 and size, the modal set, the FE source hashes
    registration: dict  # kind, hash, who confirmed it, units, measured side
    records: tuple  # (record number as read, Hz)
    labels: tuple  # one per measured DOF: "<point>:<x|y|z>"
    points_fe: np.ndarray  # (DOFs, 3), FE units
    directions_fe: np.ndarray  # (DOFs, 3), unit vectors
    values: np.ndarray  # (records, DOFs), the measured component, complex as read
    fe_low: tuple
    fe_high: tuple
    pairs: tuple  # (record, FE mode, MAC) of the comparison: the independently established FE / EXP pair identities
    identity: str

    @property
    def point_count(self) -> int:
        return len({label.rsplit(":", 1)[0] for label in self.labels})


def _digest(*parts) -> str:
    digest = hashlib.sha256()
    for part in parts:
        if isinstance(part, np.ndarray):
            digest.update(np.ascontiguousarray(part).tobytes())
        else:
            digest.update(json.dumps(part, sort_keys=True, default=str).encode("utf-8"))
    return digest.hexdigest()


def registered_set(*, modes: Sequence, transform: Mapping, fe_low, fe_high, source: Mapping, registration: Mapping,
                   pairs: Sequence = ()) -> RegisteredSet:
    """The records of a compared modal set at their measured DOFs, taken to FE coordinates with the comparison's own
    transform ``x_exp = (x_fe R) s + t`` (so ``x_fe = ((x_exp - t) / s) R^T``; the FE direction of experimental
    component k is column k of R). Nothing is fitted or guessed: a record without an explicit measured-DOF mask, a mask
    that differs between records or a missing value is refused."""
    if not registration.get("registration_hash"):
        raise EstimationRefused(REGISTRATION_REQUIRED, "There is no verified or confirmed registration: a registered "
                                                       "modal set cannot be made.")
    modes = list(modes)
    if not modes:
        raise EstimationRefused(INVALID_INPUT, "The modal set holds no record.")
    numbers = [int(mode.number) for mode in modes]
    if len(set(numbers)) != len(numbers):
        raise EstimationRefused(INVALID_INPUT, "The modal set holds a record number more than once.")
    try:
        rotation = np.asarray(transform["rotation"], dtype=float)
        translation = np.asarray(transform["translation"], dtype=float)
        scales = np.asarray(transform["coordinate_scales"], dtype=float)
    except (KeyError, TypeError, ValueError):
        raise EstimationRefused(REGISTRATION_REQUIRED, "The comparison holds no usable registration transform.") from None
    if (rotation.shape != (3, 3) or translation.shape != (3,) or scales.shape != (3,) or not np.all(scales > 0.0)
            or float(np.max(np.abs(rotation @ rotation.T - np.eye(3)))) > 1.0e-6):
        raise EstimationRefused(REGISTRATION_REQUIRED, "The registration transform is not a rotation with positive scales.")
    reference = np.asarray(modes[0].node_ids, dtype=object)
    masks = []
    for mode in modes:
        explicit = _explicit_measurement_mask(mode)
        if explicit is None:
            raise EstimationRefused(UNSUPPORTED_MEASUREMENT, f"Record {mode.number} has no explicit measured-DOF mask: its "
                                                             "measured directions are not known, and none is assumed.")
        if len(mode.node_ids) != len(reference) or any(str(a) != str(b) for a, b in zip(mode.node_ids, reference)):
            raise EstimationRefused(UNSUPPORTED_MEASUREMENT, f"Record {mode.number} is not given on the same points as "
                                                             f"record {modes[0].number}.")
        masks.append(np.asarray(explicit, dtype=bool))
    if any(not np.array_equal(mask, masks[0]) for mask in masks[1:]):
        raise EstimationRefused(UNSUPPORTED_MEASUREMENT, "The measured DOFs differ between the records of the set.")
    rows, columns = np.nonzero(masks[0])
    if not rows.size:
        raise EstimationRefused(UNSUPPORTED_MEASUREMENT, "The modal set has no measured DOF.")
    coordinates = np.asarray(modes[0].coordinates, dtype=float)
    points = ((coordinates[rows] - translation) / scales) @ rotation.T
    directions = rotation[:, columns].T
    directions = directions / np.linalg.norm(directions, axis=1, keepdims=True)
    values = np.array([_vectors_on_nodes(mode, reference)[rows, columns] for mode in modes])
    if not (np.all(np.isfinite(values.real)) and np.all(np.isfinite(values.imag))):
        raise EstimationRefused(UNSUPPORTED_MEASUREMENT, "A record has no value at a measured DOF.")
    labels = tuple(f"{reference[row]}:{'xyz'[column]}" for row, column in zip(rows, columns))
    records = tuple((int(mode.number), float(mode.frequency_hz)) for mode in modes)
    low, high = tuple(float(v) for v in fe_low), tuple(float(v) for v in fe_high)
    pairs = tuple((int(r), int(m), None if mac is None else float(mac)) for r, m, mac in pairs)
    source, registration = dict(source), dict(registration)
    return RegisteredSet(source, registration, records, labels, points, directions, values, low, high, pairs,
                         _digest(source, registration, records, labels, points, directions, values, low, high))


# ---------------------------------------------------------------------------------------------- the declared plate


@dataclass(frozen=True)
class Plate:
    """What the user declares. Nothing has a default that could pass for a statement."""

    length_mm: float
    width_mm: float
    thickness_mm: float
    mass_g: float
    nu12: float
    categories: tuple = ()  # the category of length, width, thickness, mass and nu12, in that order
    inputs_source: str = ""  # where these values come from
    length_axis: str = ""  # the FE axis the plate length runs along
    width_axis: str = ""
    linked: bool = False  # the user's statement that this plate is the registered FE body, lying along those axes
    material_axis: str = ""  # "", AXIS_LENGTH or AXIS_WIDTH: the plate direction of material axis 1
    material_axis_evidence: str = ""
    suspension: str = ""  # an optional note; the model stays free-free
    reference: tuple = ()  # (E1, E2, G12) in MPa in the fit frame: for the shape review and the "before" column only

    @property
    def x_is_length(self) -> bool:
        """The fit frame: x is material axis 1 when it is stated, otherwise the plate length."""
        return self.material_axis != AXIS_WIDTH

    def direction_names(self) -> tuple:
        return ("length a", "width b") if self.x_is_length else ("width b", "length a")

    def identity(self) -> str:
        return _digest({key: getattr(self, key) for key in self.__dataclass_fields__})


def plate_problems(plate: Plate, need_link: bool = False) -> list:
    problems = []
    for name, value, unit in (("Length", plate.length_mm, "mm"), ("Width", plate.width_mm, "mm"),
                              ("Thickness", plate.thickness_mm, "mm"), ("Mass", plate.mass_g, "g")):
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value <= 0.0:
            problems.append(f"{name} must be a positive number ({unit}).")
    if not isinstance(plate.nu12, (int, float)) or isinstance(plate.nu12, bool) or not math.isfinite(plate.nu12):
        problems.append("nu12 must be a number.")
    if len(plate.categories) != len(INPUT_NAMES) or any(c not in INPUT_CATEGORIES for c in plate.categories):
        problems.append("State for each of length, width, thickness, mass and nu12 whether it is measured, a declared "
                        "assumption or imported from the FE model.")
    elif plate.categories[INPUT_NAMES.index("mass")] == IMPORTED_FE:
        problems.append("The mass cannot be imported from the FE results: state it as measured or as a declared assumption.")
    if not str(plate.inputs_source).strip():
        problems.append("State where the dimensions, thickness, mass and nu12 come from.")
    if plate.material_axis not in ("", AXIS_LENGTH, AXIS_WIDTH):
        problems.append("The material axis 1 is either not stated, along the length or along the width.")
    elif plate.material_axis and not str(plate.material_axis_evidence).strip():
        problems.append("A stated material axis 1 needs its evidence (for example the layup record).")
    if len(plate.reference) != 3 or any(not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0.0
                                        for v in plate.reference):
        problems.append("The reference constants E1, E2 and G12 must be positive numbers (MPa).")
    elif not problems and not 1.0 - plate.nu12 ** 2 * plate.reference[1] / plate.reference[0] > 0.0:
        problems.append("These constants are not admissible: 1 - nu12^2 E2 / E1 must be positive (the stiffness is not "
                        "positive definite).")
    if need_link:
        if plate.length_axis not in AXES or plate.width_axis not in AXES or plate.length_axis == plate.width_axis:
            problems.append("State two different FE axes for the plate length and width.")
    return problems


def validate_plate(plate: Plate) -> None:
    problems = plate_problems(plate)
    if problems:
        raise EstimationRefused(INVALID_INPUT, " ".join(problems))


def plate_inputs(plate: Plate) -> rft.AbaqusPlateInputs:
    """The declared plate in the form the tuning service reads (its INP fields, with no INP): the fit frame's x extent
    first, and the density that the declared mass, plan and thickness give. No value is taken from any file."""
    validate_plate(plate)
    a, b = (plate.length_mm, plate.width_mm) if plate.x_is_length else (plate.width_mm, plate.length_mm)
    density = plate.mass_g * 1.0e-6 / (a * b * plate.thickness_mm)  # t/mm^3
    E1, E2, G12 = (float(v) for v in plate.reference)
    return rft.AbaqusPlateInputs("", "", "declared plate (no INP)", "DECLARED", E1, E2, None, float(plate.nu12), None, None,
                                 G12, None, None, density, float(plate.thickness_mm), float(a), float(b), False)


# ---------------------------------------------------------------------------------------------- the plate frame


@dataclass(frozen=True)
class Frame:
    x_m: np.ndarray
    y_m: np.ndarray
    directions: np.ndarray  # (DOFs, 3) in the plate frame: x, y, normal
    offset_m: Optional[float]  # the height of the measured surface above the mid-plane, when it is known
    lines: tuple  # (what, value): how the Ritz rectangle is tied to the registered FE frame


def _side_vector(text: str) -> Optional[np.ndarray]:
    text = str(text).strip().upper()
    if len(text) == 2 and text[0] in "+-" and text[1] in AXES:
        vector = np.zeros(3)
        vector[AXES.index(text[1])] = 1.0 if text[0] == "+" else -1.0
        return vector
    return None


def _mm(value_m: float) -> str:
    return f"{1000.0 * value_m:.4g}"


def plate_frame(rset: RegisteredSet, plate: Plate) -> Frame:
    """The registered points and measured directions in the plate frame, or the reason they cannot be placed there.

    The only link between the Ritz rectangle and the physical frame is the user's statement: the declared plate is the
    registered FE body, its length and width run along the stated FE axes, and its centre is the centre of the FE nodes.
    The program checks what can be checked without a threshold: every registered point must lie inside the declared
    rectangle. Differences between the declared and the FE extents are shown, not judged."""
    validate_plate(plate)
    if not plate.linked:
        raise EstimationRefused(LINK_NOT_ESTABLISHED,
                                "It is not stated that the plate entered here is the registered FE body. Without that "
                                "statement the Ritz rectangle has no known position in the registered frame, and no Ritz "
                                "shape is compared with a measured shape.")
    problems = plate_problems(plate, need_link=True)
    if problems:
        raise EstimationRefused(LINK_NOT_ESTABLISHED, " ".join(problems))
    unit_name = str(rset.registration.get("fe_unit", ""))
    if unit_name not in _UNIT_TO_M:
        raise EstimationRefused(LINK_NOT_ESTABLISHED, "The registration does not state the FE length unit (mm or m), so "
                                                      "FE coordinates cannot be taken to the plate.")
    unit = _UNIT_TO_M[unit_name]
    axis_x, axis_y = ((plate.length_axis, plate.width_axis) if plate.x_is_length else (plate.width_axis, plate.length_axis))
    ex, ey = np.zeros(3), np.zeros(3)
    ex[AXES.index(axis_x)] = ey[AXES.index(axis_y)] = 1.0
    normal = np.cross(ex, ey)
    low, high = np.asarray(rset.fe_low), np.asarray(rset.fe_high)
    centre = 0.5 * (low + high)
    relative = (rset.points_fe - centre) * unit
    x, y, z = relative @ ex, relative @ ey, relative @ normal
    a, b = (plate.length_mm, plate.width_mm) if plate.x_is_length else (plate.width_mm, plate.length_mm)
    half = np.array([a, b]) * 0.5e-3
    over = np.maximum(np.abs(np.column_stack((x, y))) - half, 0.0)
    outside = np.any(over > EDGE_ROUNDING * 2.0 * half, axis=1)
    if np.any(outside):
        raise EstimationRefused(LINK_NOT_ESTABLISHED,
                                f"{int(np.sum(outside))} of {len(x)} registered measurement DOFs lie outside the entered "
                                f"{plate.length_mm:g} x {plate.width_mm:g} mm rectangle (by up to {_mm(float(np.max(over)))} "
                                "mm) when it is centred on the FE model along the stated axes: the entered plate is not "
                                "the registered body in that position.")
    x, y = np.clip(x, -half[0], half[0]), np.clip(y, -half[1], half[1])
    directions = np.column_stack((rset.directions_fe @ ex, rset.directions_fe @ ey, rset.directions_fe @ normal))
    directions[np.abs(directions) < DIRECTION_ROUNDING] = 0.0
    directions = directions / np.linalg.norm(directions, axis=1, keepdims=True)
    in_plane = np.any(directions[:, :2] != 0.0, axis=1)
    side = _side_vector(rset.registration.get("measured_side", ""))
    along = None if side is None else float(side @ normal)
    offset = None if along is None or abs(abs(along) - 1.0) > DIRECTION_ROUNDING else math.copysign(
        0.5e-3 * plate.thickness_mm, along)
    if np.any(in_plane) and offset is None:
        raise EstimationRefused(UNSUPPORTED_MEASUREMENT,
                                f"{int(np.sum(in_plane))} of {len(x)} measured DOFs are not normal to the plate, and the "
                                "registration states no measured side along the plate normal: the height of the measured "
                                "surface above the mid-plane is unknown, so the motion of that surface cannot be "
                                "evaluated. No measurement is treated as transverse motion.")
    extent = (high - low) * unit
    names = plate.direction_names()
    fe_x, fe_y, fe_n = float(extent @ np.abs(ex)), float(extent @ np.abs(ey)), float(extent @ np.abs(normal))

    def difference(entered_mm: float, fe_m: float) -> str:
        return "FE extent zero" if fe_m <= 0.0 else f"{100.0 * (entered_mm * 1.0e-3 / fe_m - 1.0):+.2f} %"

    lines = (
        ("Link to the registered frame", "DECLARED BY THE USER: the entered plate is the registered FE body. The program "
                                         "does not verify that statement; it checks only that every registered point lies "
                                         "inside the entered rectangle."),
        ("Fit frame", f"x = {names[0]} along FE {axis_x}; y = {names[1]} along FE {axis_y}; normal along FE "
                      f"{AXES[int(np.argmax(np.abs(normal)))]}. Material axis 1: "
                      + ("not stated" if not plate.material_axis else f"along x ({names[0]}), as declared")),
        ("Plate centre (FE coordinates)", "(" + ", ".join(f"{v:.6g}" for v in centre) + f") {unit_name}: the centre of "
                                          f"the FE nodes ({IMPORTED_FE})"),
        ("FE extent along x, y, normal", f"{_mm(fe_x)} x {_mm(fe_y)} x {_mm(fe_n)} mm"
                                         + (" (a mid-surface model: no thickness in the FE nodes)" if fe_n <= 0.0 else "")),
        ("Entered x, y, thickness", f"{a:g} x {b:g} x {plate.thickness_mm:g} mm; difference from the FE extent: "
                                    f"{difference(a, fe_x)}, {difference(b, fe_y)}"
                                    + ("" if fe_n <= 0.0 else f", {difference(plate.thickness_mm, fe_n)}")
                                    + " (shown, not judged; the entered values are used)"),
        ("Registered measurement", f"{len(x)} DOFs at {rset.point_count} points; x from {_mm(float(np.min(x)))} to "
                                   f"{_mm(float(np.max(x)))} mm, y from {_mm(float(np.min(y)))} to {_mm(float(np.max(y)))} "
                                   f"mm from the centre: inside the entered rectangle; distance from the FE mid-position "
                                   f"along the normal {_mm(float(np.min(z)))} to {_mm(float(np.max(z)))} mm"),
        ("Measured directions", f"{int(np.sum(~in_plane))} normal to the plate (transverse w); {int(np.sum(in_plane))} with "
                                "an in-plane part (surface motion -z grad w)"),
        ("Measured side", ("not stated by the registration" if side is None else
                           str(rset.registration.get("measured_side")) + (
                               f": the measured surface is {_mm(offset)} mm from the mid-plane along the plate normal"
                               if offset is not None else ": not along the plate normal"))),
    )
    return Frame(x, y, directions, offset, lines)


def observation_set(rset: RegisteredSet, frame: Frame) -> CoordinateObservationSet:
    points = tuple(ObservationPoint(label, float(x), float(y), tuple(float(v) for v in direction),
                                    frame.offset_m if (direction[0] != 0.0 or direction[1] != 0.0) else None,
                                    "transverse displacement w" if direction[0] == direction[1] == 0.0
                                    else "surface displacement along the measured direction")
                   for label, x, y, direction in zip(rset.labels, frame.x_m, frame.y_m, frame.directions))
    return CoordinateObservationSet(str(rset.registration["registration_hash"]), points)


# ---------------------------------------------------------------------------------------------- shapes and correspondence


def _window(top_rank: int, degree: int) -> int:
    return int(min(max(top_rank + TRACK_MARGIN, 12), (degree + 1) ** 2 - 4))


def _ritz_shapes(solution, observations) -> np.ndarray:
    try:
        return np.asarray(prf.evaluate_ritz_observations(solution, observations).values, dtype=float)
    except PlateForwardRefusal as refusal:
        raise EstimationRefused(UNSUPPORTED_MEASUREMENT, f"The Ritz shapes cannot be evaluated at the registered "
                                                         f"measurement: {refusal.reason}") from refusal


def _mac_table(rset: RegisteredSet, shapes: np.ndarray, count: int) -> list:
    return [[float(modal_assurance_criterion(rset.values[row], shapes[:, column]) or 0.0) for column in range(count)]
            for row in range(len(rset.records))]


def _close_groups(frequencies: Sequence[float]) -> list:
    """Groups of close Ritz ranks (1-based), by the comparator's own close-mode rule and limits."""
    modes = [SimpleNamespace(number=rank, frequency_hz=float(hz)) for rank, hz in enumerate(frequencies, start=1)]
    return [[int(item["mode"]) for item in group] for group in _close_mode_groups(SimpleNamespace(modes=modes))]


def _solve(inputs: rft.AbaqusPlateInputs, degree: int, count: int, moduli: Sequence[float]):
    try:
        return rft.Surrogate(inputs, int(degree), int(count)).solution(*(float(v) for v in moduli))
    except PlateForwardRefusal as refusal:
        raise EstimationRefused(MODEL_REFUSED, f"The Ritz model refuses these values: {refusal.reason}") from refusal


def shape_review(rset: RegisteredSet, plate: Plate, degree: int = 14) -> dict:
    """The MAC of every record against every Ritz rank at the declared reference constants, on the registered measured
    DOFs. A diagnostic for the user's review: it assigns nothing, and no constant is fitted to make it."""
    inputs = plate_inputs(plate)
    frame = plate_frame(rset, plate)
    observations = observation_set(rset, frame)
    count = _window(len(rset.records), degree)
    solution = _solve(inputs, degree, count, plate.reference)
    shown = min(count, len(rset.records) + 6)
    mac = _mac_table(rset, _ritz_shapes(solution, observations), shown)
    return {"schema": SCHEMA, "degree": int(degree), "set_identity": rset.identity, "plate_identity": plate.identity(),
            "reference": dict(zip(("E1", "E2", "G12"), (float(v) for v in plate.reference))),
            "records": [[record, hz] for record, hz in rset.records], "ranks": list(range(1, shown + 1)),
            "ritz_hz": [float(v) for v in solution.frequencies_hz[:shown]], "mac": mac,
            "close_groups": _close_groups(solution.frequencies_hz[:shown]),
            "degenerate_groups": [[int(i) + 1 for i in cluster] for cluster in solution.clusters if cluster[-1] < shown],
            "frame": [list(line) for line in frame.lines], "dof_count": len(rset.labels)}


def review_is_current(review: Optional[Mapping], rset: RegisteredSet, plate: Plate, degree: int) -> bool:
    return bool(review) and (review.get("set_identity"), review.get("plate_identity"), review.get("degree")) == (
        rset.identity, plate.identity(), int(degree))


def correspondence_table(mac: Sequence[Sequence[float]], ritz_hz: Sequence[float], close_groups, degenerate_groups,
                         rset: RegisteredSet, observations: Sequence[rft.Observation],
                         compared: Optional[Mapping[int, int]] = None) -> dict:
    """Every record against the Ritz mode it is fixed to, from a MAC table (records x Ritz ranks).

    ``compared``: {record: the column (1-based rank at these constants) that stands for the record's fixed branch}; by
    default the fixed rank itself. A verdict uses no MAC limit: a record AGREES when its fixed mode is the mode it
    resembles most and no other included record resembles that mode more; inside a group of close Ritz modes a record
    that resembles another member most is UNCERTAIN (the group is assessed separately); anything else CONTRADICTS."""
    position = {record: row for row, (record, _hz) in enumerate(rset.records)}
    pairs = {record: (fe_mode, value) for record, fe_mode, value in rset.pairs}
    included = [o for o in observations if o.role in (rft.FIT, rft.HOLDOUT)]
    column_of = {o.record: int((compared or {}).get(o.record, o.surrogate_rank)) for o in included}
    width = len(mac[0]) if mac else 0
    group_of = {}
    for index, group in enumerate(list(close_groups) + [g for g in degenerate_groups if g not in close_groups]):
        for rank in group:
            group_of.setdefault(rank, index)
    degenerate = {rank for group in degenerate_groups for rank in group}
    rows = []
    for o in sorted(observations, key=lambda item: item.record):
        row = {"record": o.record, "hz": o.hz, "role": o.role, "rank": o.surrogate_rank if o.role != rft.EXCLUDED else None,
               "compared_rank": None, "ritz_hz": None, "mac": None, "best_rank": None, "best_mac": None,
               "verdict": NOT_COMPARED, "fe_pair": None if o.record not in pairs else list(pairs[o.record]), "group": None}
        if o.role != rft.EXCLUDED and o.record in position and 1 <= column_of[o.record] <= width:
            column = column_of[o.record]
            values = mac[position[o.record]]
            best = int(np.argmax(values)) + 1
            rivals = [mac[position[other.record]][column - 1] for other in included
                      if other.record != o.record and other.record in position]
            mutual = best == column and all(values[column - 1] >= rival for rival in rivals)
            same_group = column in group_of and group_of.get(best) == group_of[column]
            verdict = AGREES if mutual and column not in degenerate else (
                UNCERTAIN if column in degenerate or same_group or (best == column and column in group_of) else CONTRADICTS)
            row.update(compared_rank=column, ritz_hz=float(ritz_hz[column - 1]), mac=float(values[column - 1]),
                       best_rank=best, best_mac=float(values[best - 1]), verdict=verdict, group=group_of.get(column))
        rows.append(row)
    groups = []
    for group in close_groups:
        members = [o for o in included if column_of[o.record] in group and o.record in position]
        item = {"ranks": list(group), "ritz_hz": [float(ritz_hz[rank - 1]) for rank in group if rank <= width],
                "records": [o.record for o in members], "exactly_degenerate": any(rank in degenerate for rank in group),
                "individual": [[o.record, column_of[o.record], float(mac[position[o.record]][column_of[o.record] - 1])]
                               for o in members],
                "subspace_mac": None, "subspace_note": ""}
        groups.append(item)
    return {"rows": rows, "groups": groups,
            "contradicting": [r["record"] for r in rows if r["verdict"] == CONTRADICTS and r["role"] == rft.FIT],
            "uncertain": [r["record"] for r in rows if r["verdict"] == UNCERTAIN and r["role"] == rft.FIT],
            "holdout_not_agreeing": [r["record"] for r in rows if r["verdict"] in (CONTRADICTS, UNCERTAIN)
                                     and r["role"] == rft.HOLDOUT]}


def _group_subspaces(table: dict, rset: RegisteredSet, shapes: np.ndarray) -> None:
    """The subspace MAC of each close group (the cluster service's own value): the records fixed into the group against
    the Ritz modes they are fixed to. A group value says nothing about which record is which mode."""
    position = {record: row for row, (record, _hz) in enumerate(rset.records)}
    for group in table["groups"]:
        if len(group["individual"]) < 2:
            group["subspace_note"] = (f"NOT_AVAILABLE: {len(group['individual'])} record(s) fixed into this group; a "
                                      "subspace needs at least two.")
            continue
        measured = np.column_stack([rset.values[position[record]] for record, _rank, _mac in group["individual"]])
        model = np.column_stack([shapes[:, rank - 1] for _record, rank, _mac in group["individual"]])
        try:
            group["subspace_mac"] = float(clusters.subspace_mac(model, measured))
            group["subspace_note"] = (f"{len(group['individual'])} records against their {len(group['individual'])} Ritz "
                                      f"modes on {measured.shape[0]} DOFs; a group value, not an identity of any record")
        except ValueError as error:
            group["subspace_note"] = f"NOT_AVAILABLE: {error}"


def review_correspondence(review: Mapping, rset: RegisteredSet, plate: Plate, observations: Sequence[rft.Observation]) -> dict:
    """The fixed correspondence against the reviewed shapes at the reference constants."""
    table = correspondence_table(review["mac"], review["ritz_hz"], review["close_groups"], review["degenerate_groups"],
                                 rset, observations)
    solution = _solve(plate_inputs(plate), review["degree"], _window(len(rset.records), review["degree"]), plate.reference)
    _group_subspaces(table, rset, _ritz_shapes(solution, observation_set(rset, plate_frame(rset, plate))))
    return table


# ---------------------------------------------------------------------------------------------- following the fixed branches


class BranchTracker:
    """The spectrum in which place ``rank - 1`` holds the frequency of the branch that had that rank at the reviewed
    reference constants (``TuningRequest.tracked_spectrum``).

    A branch is recognised by the M-weighted MAC between Ritz coefficient vectors of the same basis, the measure the
    Ritz service uses to track its own modes; the fixed branches are assigned one-to-one to the current modes. Measured
    shapes take no part, and nothing here is optimized: the fit still minimizes frequency residuals only."""

    def __init__(self, inputs: rft.AbaqusPlateInputs, reference: Sequence[float], top_rank: int, degree: int,
                 fit_ranks: Sequence[int] = ()):
        self.inputs, self.degree, self.top = inputs, int(degree), int(top_rank)
        # the FIT branches are recognised first and by themselves, so that no HOLDOUT or unused rank can move one of them
        self.first = np.array(sorted({int(rank) - 1 for rank in fit_ranks if 1 <= int(rank) <= self.top}), dtype=int)
        self.count = _window(self.top, self.degree)
        self.reference_moduli = tuple(float(v) for v in reference)
        self.reference = _solve(inputs, self.degree, self.count, self.reference_moduli)
        self.solves = 1

    def solve(self, moduli: Sequence[float]):
        self.solves += 1
        return _solve(self.inputs, self.degree, self.count, moduli)

    def assign(self, solution, start=None, index=None) -> tuple:
        """(the current mode index of every fixed branch, its MAC), from ``start`` (by default the reference)."""
        start = self.reference if start is None else start
        index = np.arange(self.top) if index is None else index
        cross = start.coefficients[:, index].T @ start.mass @ solution.coefficients
        mac = cross * cross
        columns = np.full(self.top, -1, dtype=int)
        rest = np.setdiff1d(np.arange(self.top), self.first)
        if self.first.size:
            rows, found = linear_sum_assignment(-mac[self.first])
            columns[self.first[rows]] = found
        free = np.setdiff1d(np.arange(mac.shape[1]), columns[columns >= 0])
        if rest.size:
            rows, found = linear_sum_assignment(-mac[np.ix_(rest, free)])
            columns[rest[rows]] = free[found]
        return columns, mac[np.arange(self.top), columns]

    def __call__(self, _surrogate, E1: float, E2: float, G12: float) -> np.ndarray:
        solution = self.solve((E1, E2, G12))
        columns, _mac = self.assign(solution)
        frequencies = np.array(solution.frequencies_hz, dtype=float)
        frequencies[:self.top] = np.asarray(solution.frequencies_hz, dtype=float)[columns]
        return frequencies

    def follow(self, moduli: Sequence[float]) -> dict:
        """The fixed branches followed along the straight path (in ln p) from the reference to ``moduli``: a step is
        taken only when every branch is found again at the Ritz service's tracking level; otherwise it is halved, down
        to the smallest step, below which the branch is reported as ambiguous at that place."""
        start, end = np.log(self.reference_moduli), np.log([float(v) for v in moduli])
        current, index = self.reference, np.arange(self.top)
        lowest = np.ones(self.top)
        ambiguous, place, step, steps = {}, 0.0, 1.0, 0
        solution = current
        while place < 1.0:
            step = min(step, 1.0 - place)
            solution = self.solve(np.exp(start + (place + step) * (end - start)))
            columns, mac = self.assign(solution, current, index)
            clear = bool(np.all(mac >= TRACKING_MINIMUM_MAC))
            if not clear and step > SMALLEST_PATH_STEP:
                step *= 0.5
                continue
            for branch in np.flatnonzero(mac < TRACKING_MINIMUM_MAC):
                ambiguous.setdefault(int(branch) + 1, {"at": place + step, "mac": float(mac[branch])})
            lowest = np.minimum(lowest, mac)
            current, index, place, steps = solution, columns, place + step, steps + 1
            step *= 2.0
        return {"index": [int(i) for i in index], "lowest_step_mac": [float(v) for v in lowest], "ambiguous": ambiguous,
                "steps": steps, "solution": solution}


def branch_report(tracker: BranchTracker, fitted: Sequence[float], observations: Sequence[rft.Observation]) -> tuple:
    """(report, the fitted solution, {record: the fitted mode column that stood for it}). Each fixed branch at the fitted
    values: the mode the fit compared (direct recognition from the reference) and the mode the followed path arrives at.
    They must be the same mode, found without an ambiguous step."""
    path = tracker.follow(fitted)
    solution = path.pop("solution")
    direct, direct_mac = tracker.assign(solution)
    frequencies = np.asarray(solution.frequencies_hz, dtype=float)
    close = _close_groups(frequencies)
    degenerate = {int(i) + 1 for cluster in solution.clusters for i in cluster}
    rows, compared = [], {}
    for o in sorted((o for o in observations if o.role in (rft.FIT, rft.HOLDOUT)), key=lambda item: item.surrogate_rank):
        branch = o.surrogate_rank - 1
        used, followed = int(direct[branch]) + 1, int(path["index"][branch]) + 1
        doubt = path["ambiguous"].get(o.surrogate_rank)
        status = LOST if used != followed else AMBIGUOUS if doubt or used in degenerate else TRACKED
        compared[o.record] = used
        rows.append({"record": o.record, "role": o.role, "reference_rank": o.surrogate_rank, "fitted_rank": used,
                     "followed_rank": followed, "fitted_hz": float(frequencies[used - 1]),
                     "mac_to_reference": float(direct_mac[branch]), "lowest_step_mac": float(path["lowest_step_mac"][branch]),
                     "status": status,
                     "note": (f"the followed path arrives at rank {followed}, the fit compared rank {used}"
                              if status == LOST else
                              f"no clear continuation at {doubt['at']:.0%} of the path (MAC {doubt['mac']:.3f})" if doubt else
                              "exactly degenerate at the fitted values: its own shape is not defined" if used in degenerate
                              else "rank changed against the reference; the branch was followed" if used != o.surrogate_rank
                              else ""),
                     "close_group": next((group for group in close if used in group), None)})
    failed = [r for r in rows if r["status"] != TRACKED and r["role"] == rft.FIT]
    report = {"verdict": BRANCH_NOT_IDENTIFIABLE if failed else BRANCHES_TRACKED, "rows": rows, "path_steps": path["steps"],
              "tracking_minimum_mac": TRACKING_MINIMUM_MAC, "smallest_path_step": SMALLEST_PATH_STEP,
              "close_groups_at_fitted_values": close,
              "statement": ("Every fixed FIT branch was followed from the reviewed reference to the fitted values, and the "
                            "fit compared that same mode." if not failed else
                            "FIT record(s) " + ", ".join(str(r["record"]) for r in failed) + " are compared with a Ritz "
                            "branch that could not be followed from the reviewed reference to the fitted values (a lost "
                            "branch or an ambiguous crossing). Their identity at the fitted values is not established, so "
                            "the estimate is diagnostic only.")}
    return report, solution, compared


# ---------------------------------------------------------------------------------------------- the estimate


def stiffness_report(fitted: Mapping[str, float], plate: Plate, status: str, minima: Sequence[Mapping],
                     parameter_names: Sequence[str]) -> dict:
    """D11, D22, D66 and D12 in the fit frame (N m) from the fitted values, by the tuning service's own conversion."""
    names = plate.direction_names()

    def bending(E1, E2, G12) -> dict:
        d = rft.bending_stiffness(E1, E2, plate.nu12, G12, plate.thickness_mm)
        return {"D11": d.D11, "D22": d.D22, "D66": d.D66, "D12": d.D12}

    values = bending(fitted["E1"], fitted["E2"], fitted["G12"])
    alternatives = []
    if status == rft.MIRROR:
        for label, minimum in zip(("alternative A", "alternative B"), minima[:2]):
            m = rft._moduli(parameter_names, [minimum["values"][n] for n in parameter_names], None)
            alternatives.append({"alternative": label, **bending(m["E1"], m["E2"], m["G12"]), "E1": m["E1"], "E2": m["E2"],
                                 "G12": m["G12"], "cost": minimum["cost"]})
    return {"unit": "N m", "frame": {"x": names[0], "y": names[1]}, "values": values, "alternatives": alternatives,
            "D12_note": f"D12 = nu12 x D22 with nu12 = {plate.nu12:g} held fixed: a constitutive assumption, not an estimate",
            "surface_mass_kg_m2": plate.mass_g * 1.0e-3 / (plate.length_mm * plate.width_mm * 1.0e-6),
            "note": ("Bending stiffness depends on the mass and the plan dimensions, not on the thickness: the frequencies "
                     "fix D / (surface mass). The moduli follow from D only through the declared thickness (E ~ h^-3).")}


def presentation_of(status: str, quality: Mapping, block: Mapping) -> dict:
    """Whether the estimate may be shown as a numerically supported research estimate, from the saved facts alone. Every
    reason is listed; a research presentation rule, which uses the existing diagnostic levels and adds none."""
    if status not in (rft.SUPPORTED, rft.MIRROR):
        return {"verdict": NO_ESTIMATE, "reasons": [f"The optimizer status {status} gives no estimate."]}
    reasons = []
    correspondence, branch = block.get("correspondence", {}), block.get("branch", {})
    if quality.get("verdict") != rft.FIT_WITHIN:
        reasons.append(f"Spectral fit quality {quality.get('verdict')}: the model and correspondence do not reproduce the "
                       "FIT frequencies.")
    if quality.get("holdout_verdict") == rft.HOLDOUT_DISAGREES:
        reasons.append("HOLDOUT record(s) " + ", ".join(map(str, quality.get("holdout_records_off", []))) + " are not "
                       "predicted: the fit does not predict the frequencies it did not use.")
    if correspondence.get("kind") != SHAPE_REVIEWED:
        reasons.append("The correspondence is an unverified frequency-rank hypothesis: no measured shape was compared "
                       "with a Ritz shape.")
    for key, text in (("reference", "at the reviewed reference constants"), ("fitted", "at the fitted values")):
        table = correspondence.get(key) or {}
        if table.get("contradicting"):
            reasons.append("FIT record(s) " + ", ".join(map(str, table["contradicting"])) + f" contradict their fixed Ritz "
                           f"mode by shape {text}.")
        if table.get("uncertain"):
            reasons.append("FIT record(s) " + ", ".join(map(str, table["uncertain"])) + " lie in a group of close Ritz modes "
                           f"{text}, where their individual identity is not established (group agreement is not an "
                           "identity).")
    if correspondence.get("kind") == SHAPE_REVIEWED and branch.get("verdict") != BRANCHES_TRACKED:
        reasons.append(branch.get("statement") or "The fixed branches were not followed to the fitted values.")
    return {"verdict": DIAGNOSTIC_ONLY if reasons else SUPPORTED_ESTIMATE, "reasons": reasons}


def constants_report(fitted: Mapping[str, float], plate: Plate, status: str, presentation: Mapping,
                     parameter_names: Sequence[str]) -> dict:
    """Conditional E1, E2, G12 only when the fit is a supported estimate, the optimizer found one oriented minimum and the
    material axis 1 is stated with its evidence. Otherwise the values are kept without an axis name, or withheld."""
    names = plate.direction_names()
    tied = "E" in parameter_names
    reasons = []
    if presentation["verdict"] != SUPPORTED_ESTIMATE:
        reasons.append("The estimate is not numerically supported (see the presentation reasons).")
    if status == rft.MIRROR:
        reasons.append("Two minima with the in-plane moduli exchanged fit equally: which direction is stiff is not "
                       "identifiable from these frequencies.")
    if not plate.material_axis:
        reasons.append("The direction of material axis 1 is not stated with independent evidence.")
    conditions = (f"thickness {plate.thickness_mm:g} mm, mass {plate.mass_g:g} g, {plate.length_mm:g} x {plate.width_mm:g} "
                  f"mm, nu12 {plate.nu12:g}, the registration, the fixed correspondence and the Ritz model")
    if presentation["verdict"] == NO_ESTIMATE:
        return {"kind": "WITHHELD", "rows": [], "reasons": reasons, "conditions": conditions}
    if not reasons:
        rows = [["E1 (material axis 1, along " + names[0] + ")", fitted["E1"]],
                ["E2 (material axis 2, along " + names[1] + ")", fitted["E2"]], ["G12", fitted["G12"]]]
        if tied:
            rows = [["E1 = E2 (tied by the chosen form)", fitted["E1"]], ["G12", fitted["G12"]]]
        return {"kind": "CONDITIONAL_ENGINEERING_CONSTANTS", "rows": rows, "reasons": [], "conditions": conditions,
                "axis_evidence": plate.material_axis_evidence}
    if tied:
        rows = [["E (one in-plane modulus, tied by the chosen form)", fitted["E1"]], ["G12 (in the plate's edge axes)",
                                                                                     fitted["G12"]]]
    elif status == rft.MIRROR:
        rows = [["E_stiff (direction not identifiable)", max(fitted["E1"], fitted["E2"])],
                ["E_soft (direction not identifiable)", min(fitted["E1"], fitted["E2"])], ["G12", fitted["G12"]]]
    else:
        stiff = names[0] if fitted["E1"] >= fitted["E2"] else names[1]
        rows = [["E_stiff (no material axis named)", max(fitted["E1"], fitted["E2"])],
                ["E_soft (no material axis named)", min(fitted["E1"], fitted["E2"])], ["G12 (in the plate's edge axes)",
                                                                                      fitted["G12"]],
                ["Stiffer plate direction in this fit", f"{stiff}: it follows from the registered shapes and the fixed "
                                                        "correspondence under this model; it is not independent evidence "
                                                        "of the material axes"]]
    kind = "DIAGNOSTIC_ONLY_VALUES" if presentation["verdict"] != SUPPORTED_ESTIMATE else "AXIS_FREE_VALUES"
    return {"kind": kind, "rows": rows, "reasons": reasons, "conditions": conditions,
            "axis_evidence": plate.material_axis_evidence}


def quantity_table(rset: RegisteredSet, plate: Plate, kind: str, parameter_names: Sequence[str]) -> list:
    """What is measured, declared, imported, computed and estimated, with the source of each."""
    registration, source = rset.registration, rset.source
    categories = dict(zip(INPUT_NAMES, plate.categories))
    where = str(plate.inputs_source).strip()
    surface = plate.mass_g * 1.0e-3 / (plate.length_mm * plate.width_mm * 1.0e-6)
    fitted = ", ".join("E1 = E2" if n == "E" else n for n in parameter_names)
    return [
        {"quantity": f"Natural frequencies and shapes ({len(rset.records)} records, {len(rset.labels)} measured DOFs)",
         "category": MEASURED, "source": f"{source.get('experimental_file', '')}, SHA-256 "
                                         f"{str(source.get('experimental_sha256', ''))[:12]}…, modal set "
                                         f"{source.get('modal_set_title', '')}"},
        {"quantity": "Physical registration", "category": "INDEPENDENTLY ESTABLISHED: " + str(registration.get("kind", "")),
         "source": f"registration {str(registration.get('registration_hash', ''))[:12]}…"
                   + (f", confirmed by {registration['confirmed_by']} on {registration.get('confirmed_at', '')}; evidence: "
                      f"{registration.get('evidence_location', '')}" if registration.get("confirmed_by") else "")},
        {"quantity": f"Length a {plate.length_mm:g} mm", "category": categories["length"], "source": where},
        {"quantity": f"Width b {plate.width_mm:g} mm", "category": categories["width"], "source": where},
        {"quantity": f"Thickness {plate.thickness_mm:g} mm", "category": categories["thickness"], "source": where},
        {"quantity": f"Mass {plate.mass_g:g} g", "category": categories["mass"], "source": where},
        {"quantity": f"nu12 = {plate.nu12:g}", "category": categories["nu12"] + ", FIXED, NOT IDENTIFIED", "source": where},
        {"quantity": f"Surface mass {surface:.5g} kg/m²", "category": COMPUTED, "source": "mass / (length x width)"},
        {"quantity": "Position of the plate in the registered frame", "category": DECLARED + " + " + IMPORTED_FE,
         "source": f"the user's statement; length along FE {plate.length_axis}, width along FE {plate.width_axis}, centre "
                   "of the FE nodes"},
        {"quantity": "Material axis 1", "category": DECLARED if plate.material_axis else "NOT STATED",
         "source": (f"along the {'length' if plate.material_axis == AXIS_LENGTH else 'width'}; evidence: "
                    f"{plate.material_axis_evidence}" if plate.material_axis else "no evidence given: no E1 / E2 is named")},
        {"quantity": "Reference constants " + ", ".join(f"{n} {v:g}" for n, v in zip(("E1", "E2", "G12"), plate.reference))
                     + " MPa", "category": DECLARED, "source": "for the shape review and the comparison column only; they "
                                                               "set neither the start nor the bounds of the fit"},
        {"quantity": "Record -> Ritz mode correspondence", "category": "FIXED BY THE USER BEFORE THE FIT",
         "source": "reviewed against the Ritz shapes on the registered DOFs" if kind == SHAPE_REVIEWED else
                   "frequency rank only: an unverified hypothesis"},
        {"quantity": "Support", "category": DECLARED, "source": "free on all edges; "
                                                               + (str(plate.suspension).strip() or "no suspension note")},
        {"quantity": f"{fitted}; D11, D22, D66", "category": ESTIMATE, "source": "this fit (Kirchhoff-Ritz model)"},
    ]


def statements(result: rft.TuningResult, block: Mapping) -> list:
    """The seven separate statements of a result: [title, verdict, text]. None of them implies another."""
    quality = result.fit_quality or rft.assess_fit_quality(result.rows)
    correspondence, branch = block["correspondence"], block["branch"]
    reference = correspondence.get("reference") or {}

    def rms(value) -> str:
        return "—" if value is None else f"{value:.2%}"

    return [
        ["1. Optimizer convergence", result.status, "; ".join(result.reasons) or "converged from every start"],
        ["2. Parameter identifiability", f"practical rank {result.practical_rank} of {len(result.parameter_names)}",
         f"condition number {result.condition_number:.4g}; {len(result.minima)} minimum/minima reached"
         if result.condition_number is not None else "not assessed"],
        ["3. FIT spectral residuals", quality.get("verdict", rft.FIT_NOT_ASSESSED),
         f"RMS {rms(quality.get('fit_rms_ln'))} (ln f) over {quality.get('fit_count', 0)} FIT record(s)"],
        ["4. HOLDOUT predictive residuals", quality.get("holdout_verdict", rft.NO_HOLDOUT),
         f"RMS {rms(quality.get('holdout_rms_ln'))} (ln f) over {quality.get('holdout_count', 0)} HOLDOUT record(s); they "
         "took no part in the fit"],
        ["5. Modal correspondence and branches", f"{correspondence['kind']}; {branch['verdict']}",
         (f"{len(reference.get('contradicting', []))} FIT record(s) contradict and {len(reference.get('uncertain', []))} "
          "are uncertain by shape at the reference; " + branch.get("statement", ""))
         if correspondence["kind"] == SHAPE_REVIEWED else correspondence["statement"]],
        ["6. Model assumptions", "DECLARED, NOT VERIFIED", " ".join(ASSUMPTIONS)],
        ["7. Physical validity", rft.NOT_ESTABLISHED, VALIDITY_TEXT],
    ]


def _plain(value):
    """JSON form with record numbers as numbers again, so that a live result and a reopened one are the same data."""
    return rft.restore_record_keys(json.loads(json.dumps(value, default=lambda item: item.tolist()
                                                         if isinstance(item, np.ndarray) else float(item))))


def plate_document(plate: Plate) -> dict:
    return {key: (list(value) if isinstance(value, tuple) else value)
            for key, value in ((key, getattr(plate, key)) for key in plate.__dataclass_fields__)}


def plate_from_document(document: Mapping) -> Plate:
    try:
        return Plate(**{key: (tuple(value) if isinstance(value, list) else value) for key, value in document.items()})
    except TypeError as error:
        raise EstimationRefused(INVALID_INPUT, f"The saved plate declaration is damaged ({error}).") from None


def tracked_request(rset: RegisteredSet, plate: Plate, request: rft.TuningRequest,
                    review: Optional[Mapping] = None) -> rft.TuningRequest:
    """``request`` checked against the registered set and, with a current shape ``review``, given the tracker that
    follows the fixed branches (the same request serves the fit and its stability check). Refusals are raised here,
    before anything is solved."""
    inputs = plate_inputs(plate)
    rft.validate_correspondence(request.observations)
    known = {record for record, _hz in rset.records}
    if {o.record for o in request.observations} != known:
        raise EstimationRefused(INVALID_INPUT, "The correspondence does not name exactly the records of the registered set.")
    if request.parameterization == rft.TIED and inputs.E1 != inputs.E2:
        raise EstimationRefused(INVALID_INPUT, "The form E1 = E2 needs equal reference E1 and E2; enter equal values or "
                                               "choose the three-parameter form.")
    if review is None:
        return replace(request, tracked_spectrum=None)
    if not review_is_current(review, rset, plate, request.degree):
        raise EstimationRefused(REVIEW_STALE, "The shape review was made for other inputs (the registered set, the plate "
                                              "or the basis degree changed). Review the shapes again before the fit.")
    included = [o for o in request.observations if o.role in (rft.FIT, rft.HOLDOUT)]
    top = max(o.surrogate_rank for o in included) if included else 1
    if top > len(review["ranks"]):
        raise EstimationRefused(INVALID_INPUT, f"Rank {top} is above the {len(review['ranks'])} reviewed Ritz ranks.")
    return replace(request, tracked_spectrum=BranchTracker(inputs, plate.reference, top, request.degree,
                                                           [o.surrogate_rank for o in included if o.role == rft.FIT]))


def run_estimation(rset: RegisteredSet, plate: Plate, request: rft.TuningRequest, review: Optional[Mapping] = None,
                   cancel=None, progress=None) -> tuple:
    """(result, block). ``request`` holds the FIXED correspondence: the rank of each record is the Ritz rank at the
    reference constants. With a current shape ``review`` the fit follows those branches and the result is checked by
    shape; without one the fit is the plain rank fit, labelled an unverified frequency-rank hypothesis.

    Refused before anything is solved: an inadmissible plate, an invalid or duplicated correspondence, too few FIT
    records, and a review that was made for other inputs."""
    inputs = plate_inputs(plate)
    names = rft.PARAMETERIZATIONS[request.parameterization]
    request = tracked_request(rset, plate, request, review)
    tracker = request.tracked_spectrum
    kind = SHAPE_REVIEWED if tracker is not None else RANK_HYPOTHESIS
    try:
        result = rft.run_tuning(inputs, request, (), cancel, progress,
                                "not used: measured frequencies are compared with the Ritz model only")
    except PlateForwardRefusal as refusal:
        raise EstimationRefused(MODEL_REFUSED, f"The Ritz model refused a value during the fit: {refusal.reason}") from refusal
    if result.status == rft.CANCELLED:
        return result, None
    correspondence = {"kind": kind, "reference": None, "fitted": None,
                      "statement": ("Each record is compared with the Ritz mode fixed by the user after a shape review on "
                                    "the registered DOFs; the fit followed those modes by Ritz shape."
                                    if kind == SHAPE_REVIEWED else
                                    "UNVERIFIED CORRESPONDENCE HYPOTHESIS: records are matched to Ritz modes by frequency "
                                    "rank only. No measured shape was compared, so a wrong, missing or extra mode cannot "
                                    "be ruled out.")}
    branch = {"verdict": BRANCHES_NOT_FOLLOWED, "rows": [], "statement": "No shape review: the fixed ranks are plain "
                                                                         "frequency ranks, and no branch was followed."}
    fitted = (result.fitted["E1"], result.fitted["E2"], result.fitted["G12"])
    if tracker is not None:
        correspondence["reference"] = review_correspondence(review, rset, plate, request.observations)
        branch, solution, compared = branch_report(tracker, fitted, request.observations)
        shapes = _ritz_shapes(solution, observation_set(rset, plate_frame(rset, plate)))
        frequencies = [float(v) for v in solution.frequencies_hz]
        table = correspondence_table(_mac_table(rset, shapes, tracker.count), frequencies, _close_groups(frequencies),
                                     [[int(i) + 1 for i in cluster] for cluster in solution.clusters], rset,
                                     request.observations, compared)
        _group_subspaces(table, rset, shapes)
        correspondence["fitted"] = table
    block = {"schema": SCHEMA, "label": LABEL, "source": rset.source, "registration": rset.registration,
             "set_identity": rset.identity, "plate": plate_document(plate),
             "records": [[record, hz] for record, hz in rset.records],
             "fe_pairs": [list(pair) for pair in rset.pairs], "dof_count": len(rset.labels), "point_count": rset.point_count,
             "frame": [] if review is None else review["frame"], "review": review, "correspondence": correspondence,
             "branch": branch, "assumptions": list(ASSUMPTIONS), "validity": VALIDITY_TEXT}
    block = _plain(block)
    complete(block, result)
    statistical = {n: math.exp(v) - 1.0 for n, v in (result.log_sd or {}).items()}
    result = replace(
        result, quantities=quantity_table(rset, plate, kind, names), assumptions=ASSUMPTIONS, label=rft.RESULT_LABEL,
        warnings=[w for w in result.warnings if not w.startswith("FE classification unavailable")],
        accuracy_statement=("Frequency errors are not parameter errors. The statistical SD is conditional on the model, the "
                            "fixed correspondence and the declared inputs; it leaves out the thickness, mass and dimension "
                            "uncertainty, the support and any wrong correspondence."
                            + (" Statistical SD: " + ", ".join(f"{n} ±{v:.1%}" for n, v in statistical.items())
                               if statistical else "")))
    block["statements"] = _plain(statements(result, block))
    return result, block


def complete(block: dict, result: rft.TuningResult) -> dict:
    """The parts of a block that follow from its saved facts and the result: how it may be presented, the stiffnesses and
    the constants. They are computed here every time, also when a file is opened, and are never read from a file."""
    plate = plate_from_document(block["plate"])
    quality = result.fit_quality or rft.assess_fit_quality(result.rows)
    block["presentation"] = presentation_of(result.status, quality, block)
    block["stiffness"] = _plain(stiffness_report(result.fitted, plate, result.status, result.minima,
                                                 result.parameter_names))
    block["constants"] = _plain(constants_report(result.fitted, plate, result.status, block["presentation"],
                                                 result.parameter_names))
    return block


def export_document(result: rft.TuningResult, block: Mapping, stability: Optional[Mapping] = None) -> dict:
    """The tuning service's export of the result with the registered-estimation block; no Abaqus block is written."""
    plate = plate_from_document(block["plate"])
    sources = {"inp": "", "inp_sha256": "", "dat": "", "unv": block["source"].get("experimental_file", ""),
               "unv_sha256": block["source"].get("experimental_sha256", ""),
               "modal_set": block["source"].get("modal_set_title", "")}
    document = rft.export_document(result, plate_inputs(plate), sources, stability)
    document["registered_estimation"] = dict(block)
    document["statement"] = ("Conditional research estimates of a Kirchhoff-Ritz plate from a registered modal set. Not an "
                             "FE result, not a material property, not a production identification. " + LABEL)
    return document


_BLOCK_KEYS = ("schema", "label", "source", "registration", "set_identity", "plate", "records", "fe_pairs", "frame",
               "correspondence", "branch", "assumptions", "validity")


def block_from_export(document: Mapping, result: rft.TuningResult) -> Optional[dict]:
    """The registered-estimation block of an export, or None when the export has none. The presentation, the stiffnesses
    and the constants are computed again from the saved facts; a file cannot raise its own status."""
    block = document.get("registered_estimation")
    if block is None:
        return None
    if not isinstance(block, dict) or block.get("schema") != SCHEMA or block.get("label") != LABEL:
        raise rft.TuningRefused("The export holds a registered-estimation part of another version; it is not opened.")
    missing = [key for key in _BLOCK_KEYS if key not in block]
    if missing:
        raise rft.TuningRefused(f"The registered-estimation part is incomplete: {', '.join(missing)} missing.")
    block = rft.restore_record_keys(dict(block))
    try:
        if block["correspondence"]["kind"] not in (SHAPE_REVIEWED, RANK_HYPOTHESIS):
            raise rft.TuningRefused("The registered-estimation part names an unknown kind of correspondence.")
        complete(block, result)
        block["statements"] = _plain(statements(result, block))
    except rft.TuningRefused:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, IndexError) as error:
        raise rft.TuningRefused(f"The registered-estimation part is damaged ({type(error).__name__}: {error}).") from None
    return block


__all__ = ["AGREES", "AMBIGUOUS", "ASSUMPTIONS", "AXES", "AXIS_LENGTH", "AXIS_WIDTH", "BRANCHES_NOT_FOLLOWED",
           "BRANCHES_TRACKED", "BRANCH_NOT_IDENTIFIABLE", "BranchTracker", "COMPUTED", "CONTRADICTS", "DECLARED",
           "DIAGNOSTIC_ONLY", "ESTIMATE", "EstimationRefused", "Frame", "IMPORTED_FE", "INPUT_CATEGORIES", "INPUT_NAMES",
           "INVALID_INPUT", "LABEL", "LINK_NOT_ESTABLISHED", "LOST", "MEASURED", "MODEL_REFUSED", "NOT_COMPARED",
           "NO_ESTIMATE", "Plate", "RANK_HYPOTHESIS", "REGISTRATION_REQUIRED", "REVIEW_STALE", "RegisteredSet", "SCHEMA",
           "SHAPE_REVIEWED", "SUPPORTED_ESTIMATE", "TRACKED", "TRACKING_MINIMUM_MAC", "UNCERTAIN",
           "UNSUPPORTED_MEASUREMENT", "block_from_export", "branch_report", "complete", "constants_report",
           "correspondence_table", "export_document", "observation_set", "plate_frame", "plate_inputs", "plate_problems",
           "presentation_of", "quantity_table", "registered_set", "review_correspondence", "review_is_current",
           "run_estimation", "shape_review", "statements", "stiffness_report", "tracked_request", "validate_plate"]
