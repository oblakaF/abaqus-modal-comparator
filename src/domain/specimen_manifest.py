"""Specimen passport (``specimen.json``) — Auto-ID M2.1 / M2.2 (SPEC §4, §4.1, §7, §11, §19).

The passport separates what was *designed* (``family_id``, ``design_id``) from the
*physical* manufactured object (``physical_specimen_id``) and from one experimental
*run* (``test_run_id``).  It carries physical measurements, the geometry calibration
from which registration is built, its uncertainty, and acquisition / remount linkage.

Rules:
- strict, versioned schema; unknown fields are refused;
- the four identity keys are typed and must be distinct;
- missing physical values are never defaulted: a value may be ``null`` only when it
  is declared in ``unavailable`` with a reason (e.g. no measured ``suspension_max_hz``;
  the 18 Hz in the SPEC §4.1 example is illustrative, SPEC §19 item 5);
- no machine-local absolute paths: external files are store + relative path;
- a deterministic canonical hash of the validated content (key order irrelevant).
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

import numpy as np

from coordinate_calibration import LEGACY_GEOMETRIC_FIT, CoordinateCalibration

from .experiment_fixture import ExternalFileReference, FEGeometryIdentity, _file as _external_file


SPECIMEN_MANIFEST_SCHEMA = "auto-id/specimen/v1.1"
SPECIMEN_TYPES = ("sandwich", "bare_plate", "core_tile")
# corner_coordinates_mm / scan_to_panel_edges are the SPEC §4.1 / §11 physical modes.
# documented_centered_alignment is the historical accepted registration basis (documented
# axis convention + centre-to-centre placement); it is never physically complete.
CORNER_COORDINATES = "corner_coordinates_mm"
PANEL_EDGES = "scan_to_panel_edges"
DOCUMENTED_CENTERED = "documented_centered_alignment"
CALIBRATION_MODES = (CORNER_COORDINATES, PANEL_EDGES, DOCUMENTED_CENTERED)
PHYSICAL_CALIBRATION_MODES = (CORNER_COORDINATES, PANEL_EDGES)
ORIENTATION_REFERENCES = ("corner_A_marker", "panel_edges", "documented_convention")
SURFACE_SIDES = ("max_z", "min_z")
REMOUNT_KINDS = ("remount", "re_suspension", "excitation_reinstallation")
MINIMUM_THICKNESS_POINTS = 9  # SPEC §15: every sheet at 9+ points
_AXES = {"+X": (0, 1.0), "-X": (0, -1.0), "+Y": (1, 1.0), "-Y": (1, -1.0), "+Z": (2, 1.0), "-Z": (2, -1.0)}
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/#-]*$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_NULLABLE = ("physical_specimen_id", "plan_mm", "masses_g", "face_thickness_mm", "core_height_mm",
             "suspension_max_hz", "materials")
_TOP_KEYS = {
    "schema", "specimen_type", "family_id", "design_id", "physical_specimen_id", "test_run_id",
    "plan_mm", "masses_g", "face_thickness_mm", "core_height_mm", "materials", "suspension_max_hz",
    "geometry_calibration", "fe_reference", "acquisition", "identify", "unavailable",
}


class SpecimenManifestError(ValueError):
    """The passport is malformed or scientifically ambiguous."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field


def _fail(field: str, message: str):
    raise SpecimenManifestError(field, message)


def _mapping(value: object, field: str, required: set[str], optional: set[str] = frozenset()) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(field, "must be an object.")
    missing = sorted(required - set(value))
    if missing:
        _fail(field, f"missing required field(s) {', '.join(missing)}.")
    unknown = sorted(set(value) - required - set(optional))
    if unknown:
        _fail(field, f"unknown field(s) {', '.join(unknown)}.")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(field, "must be a non-empty string.")
    return value.strip()


def _positive(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0.0:
        _fail(field, "must be a finite positive number.")
    return float(value)


def _relative_path(value: object, field: str) -> str:
    text = _text(value, field)
    if "\\" in text or re.match(r"^[A-Za-z]:", text) or text.startswith("/") or ".." in PurePosixPath(text).parts:
        _fail(field, "must be a relative POSIX path, never a local absolute path.")
    return text


# --------------------------------------------------------------------------------------
# M2.2 identities: distinct types, so a design id cannot silently stand in for a specimen.
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class _Identity:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _IDENTIFIER.match(self.value):
            raise SpecimenManifestError(type(self).__name__, f"invalid identifier {self.value!r}.")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class FamilyId(_Identity):
    """Material / campaign family."""


@dataclass(frozen=True)
class DesignId(_Identity):
    """Nominal design / geometry definition."""


@dataclass(frozen=True)
class PhysicalSpecimenId(_Identity):
    """One manufactured panel, plate or tile."""


@dataclass(frozen=True)
class TestRunId(_Identity):
    """One experimental acquisition / run."""

    __test__ = False  # not a pytest/unittest test class


# --------------------------------------------------------------------------------------
# Physical measurements
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class PlanDimensions:
    lx_mm: float
    ly_mm: float
    sd_mm: float


@dataclass(frozen=True)
class CoreHeight:
    value_mm: float
    sd_mm: float


@dataclass(frozen=True)
class SuspensionLimit:
    value_hz: float
    source: str  # where the physical value is documented


@dataclass(frozen=True)
class GeometryUncertainty:
    """Measured calibration uncertainty; ``None`` means not measured (never defaulted)."""

    translation_mm: float | None
    scale_rel: float | None
    rotation_deg: float | None

    @property
    def available(self) -> tuple[str, ...]:
        return tuple(name for name in ("translation_mm", "scale_rel", "rotation_deg") if getattr(self, name) is not None)

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(name for name in ("translation_mm", "scale_rel", "rotation_deg") if getattr(self, name) is None)


@dataclass(frozen=True)
class Orientation:
    """Physical orientation: where each experimental axis points in the FE frame."""

    experimental_axes_in_fe: tuple[str, str, str]
    reference: str  # corner_A_marker | panel_edges | documented_convention
    source: str  # traceable document / photograph / convention record

    @property
    def rotation(self) -> np.ndarray:
        """Matrix R of the comparator convention: experimental = (FE @ R) * scale + translation."""
        matrix = np.zeros((3, 3))
        for exp_axis, label in enumerate(self.experimental_axes_in_fe):
            fe_axis, sign = _AXES[label]
            matrix[fe_axis, exp_axis] = sign
        return matrix


@dataclass(frozen=True)
class MeasuredSurface:
    fe_instance: str
    side: str  # max_z | min_z of that instance
    label: str


@dataclass(frozen=True)
class CornerA:
    unv_node: int
    fe_xy_mm: tuple[float, float]
    x_axis_towards_unv_node: int


@dataclass(frozen=True)
class PanelEdgeOffsets:
    """Measured distance from the panel's minimum FE corner to the scan grid's minimum corner."""

    x_mm: float
    y_mm: float


@dataclass(frozen=True)
class LegacyRegistrationReference:
    path: str  # repo-relative accepted FrozenRegistration file
    registration_hash: str


@dataclass(frozen=True)
class GeometryCalibration:
    mode: str
    coordinate_calibration: Mapping[str, Any]
    measured_surface: MeasuredSurface
    orientation: Orientation
    uncertainty: GeometryUncertainty
    corner_a: CornerA | None = None
    panel_edges: PanelEdgeOffsets | None = None
    legacy_registration: LegacyRegistrationReference | None = None

    @property
    def calibration(self) -> CoordinateCalibration:
        return CoordinateCalibration.from_mapping(self.coordinate_calibration)

    @property
    def physically_complete(self) -> bool:
        return self.mode in PHYSICAL_CALIBRATION_MODES and not self.uncertainty.missing

    @property
    def missing_physical_evidence(self) -> tuple[str, ...]:
        missing = []
        if self.mode not in PHYSICAL_CALIBRATION_MODES:
            missing.append("physical registration reference (corner-A marker or measured scan-to-panel-edge offsets)")
        missing.extend(f"geometry_calibration.uncertainty.{name}" for name in self.uncertainty.missing)
        return tuple(missing)


@dataclass(frozen=True)
class FEReference:
    model_name: str
    geometry_identity: FEGeometryIdentity
    geometry_file: ExternalFileReference


@dataclass(frozen=True)
class GridIdentity:
    grid_id: str
    point_count: int


@dataclass(frozen=True)
class Acquisition:
    session: str
    grid: GridIdentity
    fixture_id: str | None
    protocol_id: str | None
    remount_of: TestRunId | None
    remount_kind: str | None
    remount_evidence: str | None


@dataclass(frozen=True)
class SpecimenManifest:
    schema: str
    specimen_type: str
    family_id: FamilyId
    design_id: DesignId
    physical_specimen_id: PhysicalSpecimenId | None
    test_run_id: TestRunId
    plan_mm: PlanDimensions | None
    masses_g: Mapping[str, float] | None
    face_thickness_mm: Mapping[str, tuple[float, ...]] | None
    core_height_mm: CoreHeight | None
    materials: Mapping[str, str] | None
    suspension_max_hz: SuspensionLimit | None
    geometry_calibration: GeometryCalibration
    fe_reference: FEReference
    acquisition: Acquisition
    identify: str
    unavailable: Mapping[str, str]
    canonical: Mapping[str, Any]

    @property
    def manifest_hash(self) -> str:
        return canonical_hash(self.canonical)

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.canonical))

    def trusted_suspension_threshold(self):
        """The passport's physical suspension threshold for M1.4 QC, or ``None`` (never guessed)."""
        from .experimental_qc import TrustedSuspensionThreshold

        if self.suspension_max_hz is None:
            return None
        return TrustedSuspensionThreshold(
            self.suspension_max_hz.value_hz,
            f"specimen passport {self.manifest_hash[:16]} ({self.test_run_id}): {self.suspension_max_hz.source}",
        )


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------------------

def _identity(cls, value: object, field: str):
    text = _text(value, field)
    try:
        return cls(text)
    except SpecimenManifestError as exc:
        _fail(field, str(exc))


def _nullable(data: Mapping[str, Any], name: str, unavailable: Mapping[str, str]):
    value = data[name]
    if value is None and name not in unavailable:
        _fail(name, "is null but not declared in 'unavailable' with a reason (no defaults are filled in).")
    if value is not None and name in unavailable:
        _fail(name, "has a value but is also declared unavailable.")
    return value


def _orientation(value: object, field: str) -> Orientation:
    data = _mapping(value, field, {"experimental_axes_in_fe", "reference", "source"})
    axes = data["experimental_axes_in_fe"]
    if not isinstance(axes, list) or len(axes) != 3 or any(item not in _AXES for item in axes):
        _fail(f"{field}.experimental_axes_in_fe", f"must be three of {sorted(_AXES)}.")
    if len({_AXES[item][0] for item in axes}) != 3:
        _fail(f"{field}.experimental_axes_in_fe", "must map the three experimental axes to three distinct FE axes.")
    reference = data["reference"]
    if reference not in ORIENTATION_REFERENCES:
        _fail(f"{field}.reference", f"must be one of {ORIENTATION_REFERENCES} (untraceable orientation is refused).")
    return Orientation(tuple(axes), reference, _text(data["source"], f"{field}.source"))


def _uncertainty(value: object, field: str) -> GeometryUncertainty:
    data = _mapping(value, field, {"translation_mm", "scale_rel", "rotation_deg"})
    values = {}
    for name in ("translation_mm", "scale_rel", "rotation_deg"):
        values[name] = None if data[name] is None else _positive(data[name], f"{field}.{name}")
    return GeometryUncertainty(**values)


def _geometry_calibration(value: object) -> tuple[GeometryCalibration, dict[str, Any]]:
    field = "geometry_calibration"
    data = _mapping(value, field, {"mode", "coordinate_calibration", "measured_surface", "orientation", "uncertainty"},
                    {"corner_A", "panel_edges", "legacy_registration"})
    mode = data["mode"]
    if mode not in CALIBRATION_MODES:
        _fail(f"{field}.mode", f"unknown calibration mode {mode!r}; supported: {CALIBRATION_MODES}.")
    try:
        calibration = CoordinateCalibration.from_mapping(_mapping(data["coordinate_calibration"],
                                                                  f"{field}.coordinate_calibration", {"mode"},
                                                                  {"abaqus_unit", "experimental_unit", "scan_coverage",
                                                                   "physical_width", "physical_height",
                                                                   "dimension_unit", "provenance", "manual_scale"}))
    except ValueError as exc:
        _fail(f"{field}.coordinate_calibration", str(exc))
    if calibration.mode == LEGACY_GEOMETRIC_FIT:
        _fail(f"{field}.coordinate_calibration.mode", "the legacy extent fit is not a physical calibration.")
    if not calibration.provenance.strip():
        _fail(f"{field}.coordinate_calibration.provenance", "must document how the physical scale was obtained.")
    surface_data = _mapping(data["measured_surface"], f"{field}.measured_surface", {"fe_instance", "side", "label"})
    if surface_data["side"] not in SURFACE_SIDES:
        _fail(f"{field}.measured_surface.side", f"must be one of {SURFACE_SIDES}.")
    surface = MeasuredSurface(_text(surface_data["fe_instance"], f"{field}.measured_surface.fe_instance"),
                              surface_data["side"], _text(surface_data["label"], f"{field}.measured_surface.label"))
    orientation = _orientation(data["orientation"], f"{field}.orientation")
    uncertainty = _uncertainty(data["uncertainty"], f"{field}.uncertainty")

    corner = edges = legacy = None
    if mode == CORNER_COORDINATES:
        corner_data = _mapping(data.get("corner_A"), f"{field}.corner_A",
                               {"unv_node", "fe_xy_mm", "x_axis_towards_unv_node"})
        xy = corner_data["fe_xy_mm"]
        if not isinstance(xy, list) or len(xy) != 2 or not all(
                isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in xy):
            _fail(f"{field}.corner_A.fe_xy_mm", "must be [x, y] in mm.")
        nodes = (corner_data["unv_node"], corner_data["x_axis_towards_unv_node"])
        if any(isinstance(n, bool) or not isinstance(n, int) for n in nodes) or nodes[0] == nodes[1]:
            _fail(f"{field}.corner_A", "unv_node and x_axis_towards_unv_node must be two different node numbers.")
        if orientation.reference != "corner_A_marker":
            _fail(f"{field}.orientation.reference", "corner_coordinates_mm requires orientation from the corner-A marker.")
        corner = CornerA(int(nodes[0]), (float(xy[0]), float(xy[1])), int(nodes[1]))
    elif "corner_A" in data:
        _fail(f"{field}.corner_A", f"is only valid for mode {CORNER_COORDINATES!r}.")
    if mode == PANEL_EDGES:
        edge_data = _mapping(data.get("panel_edges"), f"{field}.panel_edges", {"x_mm", "y_mm"})
        offsets = []
        for name in ("x_mm", "y_mm"):
            item = edge_data[name]
            if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) or item < 0.0:
                _fail(f"{field}.panel_edges.{name}", "must be a measured non-negative distance in mm.")
            offsets.append(float(item))
        if orientation.reference not in ("panel_edges", "corner_A_marker"):
            _fail(f"{field}.orientation.reference", "scan_to_panel_edges requires a physical orientation reference.")
        edges = PanelEdgeOffsets(*offsets)
    elif "panel_edges" in data:
        _fail(f"{field}.panel_edges", f"is only valid for mode {PANEL_EDGES!r}.")
    if mode == DOCUMENTED_CENTERED and orientation.reference != "documented_convention":
        _fail(f"{field}.orientation.reference", "documented_centered_alignment uses a documented orientation convention.")
    if "legacy_registration" in data:
        legacy_data = _mapping(data["legacy_registration"], f"{field}.legacy_registration", {"path", "registration_hash"})
        digest = legacy_data["registration_hash"]
        if not isinstance(digest, str) or not _HASH.match(digest):
            _fail(f"{field}.legacy_registration.registration_hash", "must be a 64-character lowercase hex SHA-256.")
        legacy = LegacyRegistrationReference(_relative_path(legacy_data["path"], f"{field}.legacy_registration.path"),
                                             digest)
    calibration_dict = calibration.to_dict()
    result = GeometryCalibration(mode, calibration_dict, surface, orientation, uncertainty, corner, edges, legacy)
    canonical = {
        "mode": mode,
        "coordinate_calibration": calibration_dict,
        "measured_surface": {"fe_instance": surface.fe_instance, "side": surface.side, "label": surface.label},
        "orientation": {"experimental_axes_in_fe": list(orientation.experimental_axes_in_fe),
                        "reference": orientation.reference, "source": orientation.source},
        "uncertainty": {"translation_mm": uncertainty.translation_mm, "scale_rel": uncertainty.scale_rel,
                        "rotation_deg": uncertainty.rotation_deg},
        "corner_A": None if corner is None else {"unv_node": corner.unv_node, "fe_xy_mm": list(corner.fe_xy_mm),
                                                 "x_axis_towards_unv_node": corner.x_axis_towards_unv_node},
        "panel_edges": None if edges is None else {"x_mm": edges.x_mm, "y_mm": edges.y_mm},
        "legacy_registration": None if legacy is None else {"path": legacy.path,
                                                            "registration_hash": legacy.registration_hash},
    }
    return result, canonical


def _fe_reference(value: object) -> tuple[FEReference, dict[str, Any]]:
    field = "fe_reference"
    data = _mapping(value, field, {"model_name", "geometry_identity", "geometry_file"})
    geometry = _mapping(data["geometry_identity"], f"{field}.geometry_identity", {"schema_version", "sha256", "node_count"})
    if not isinstance(geometry["sha256"], str) or not _HASH.match(geometry["sha256"]):
        _fail(f"{field}.geometry_identity.sha256", "must be a 64-character lowercase hex SHA-256.")
    count = geometry["node_count"]
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        _fail(f"{field}.geometry_identity.node_count", "must be a positive integer.")
    identity = FEGeometryIdentity(_text(geometry["schema_version"], f"{field}.geometry_identity.schema_version"),
                                  geometry["sha256"], count)
    try:
        file_ref = _external_file(data["geometry_file"], f"{field}.geometry_file")
    except ValueError as exc:
        _fail(f"{field}.geometry_file", str(exc))
    reference = FEReference(_text(data["model_name"], f"{field}.model_name"), identity, file_ref)
    canonical = {
        "model_name": reference.model_name,
        "geometry_identity": {"schema_version": identity.schema_version, "sha256": identity.sha256,
                              "node_count": identity.node_count},
        "geometry_file": {"role": file_ref.role, "file_name": file_ref.file_name, "sha256": file_ref.sha256,
                          "size_bytes": file_ref.size_bytes,
                          "location": {"store": file_ref.location.store,
                                       "relative_path": file_ref.location.relative_path}},
    }
    return reference, canonical


def _acquisition(value: object, test_run_id: TestRunId) -> tuple[Acquisition, dict[str, Any]]:
    field = "acquisition"
    data = _mapping(value, field, {"session", "grid", "fixture_id", "protocol_id", "remount_of"},
                    {"remount_kind", "remount_evidence"})
    grid_data = _mapping(data["grid"], f"{field}.grid", {"grid_id", "point_count"})
    count = grid_data["point_count"]
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        _fail(f"{field}.grid.point_count", "must be a positive integer.")
    grid = GridIdentity(_text(grid_data["grid_id"], f"{field}.grid.grid_id"), count)
    fixture_id = None if data["fixture_id"] is None else _text(data["fixture_id"], f"{field}.fixture_id")
    protocol = None if data["protocol_id"] is None else _text(data["protocol_id"], f"{field}.protocol_id")
    remount_of = None
    kind = evidence = None
    if data["remount_of"] is not None:
        remount_of = _identity(TestRunId, data["remount_of"], f"{field}.remount_of")
        if remount_of == test_run_id:
            _fail(f"{field}.remount_of", "a run cannot be a remount of itself.")
        kind = data.get("remount_kind")
        if kind not in REMOUNT_KINDS:
            _fail(f"{field}.remount_kind", f"a remount link must state its kind {REMOUNT_KINDS}.")
        evidence = _text(data.get("remount_evidence"), f"{field}.remount_evidence")
    elif data.get("remount_kind") is not None or data.get("remount_evidence") is not None:
        _fail(f"{field}.remount_kind", "is only valid together with remount_of.")
    acquisition = Acquisition(_text(data["session"], f"{field}.session"), grid, fixture_id, protocol, remount_of,
                              kind, evidence)
    canonical = {
        "session": acquisition.session,
        "grid": {"grid_id": grid.grid_id, "point_count": grid.point_count},
        "fixture_id": fixture_id, "protocol_id": protocol,
        "remount_of": None if remount_of is None else str(remount_of),
        "remount_kind": kind, "remount_evidence": evidence,
    }
    return acquisition, canonical


def parse_specimen_manifest(data: object) -> SpecimenManifest:
    """Validate a decoded passport; refuses malformed or scientifically ambiguous content."""

    data = _mapping(data, "manifest", _TOP_KEYS)
    if data["schema"] != SPECIMEN_MANIFEST_SCHEMA:
        _fail("schema", f"must be {SPECIMEN_MANIFEST_SCHEMA!r}.")
    specimen_type = data["specimen_type"]
    if specimen_type not in SPECIMEN_TYPES:
        _fail("specimen_type", f"unsupported specimen type {specimen_type!r}; supported: {SPECIMEN_TYPES}.")

    unavailable_data = data["unavailable"]
    if not isinstance(unavailable_data, Mapping):
        _fail("unavailable", "must be an object {field: reason}.")
    unavailable = {}
    for key, reason in unavailable_data.items():
        if key not in _NULLABLE:
            _fail("unavailable", f"{key!r} cannot be declared unavailable.")
        unavailable[key] = _text(reason, f"unavailable.{key}")

    family = _identity(FamilyId, data["family_id"], "family_id")
    design = _identity(DesignId, data["design_id"], "design_id")
    run = _identity(TestRunId, data["test_run_id"], "test_run_id")
    specimen = None
    if _nullable(data, "physical_specimen_id", unavailable) is not None:
        specimen = _identity(PhysicalSpecimenId, data["physical_specimen_id"], "physical_specimen_id")
    values = [str(item) for item in (family, design, specimen, run) if item is not None]
    if len(set(values)) != len(values):
        _fail("identities", "family_id, design_id, physical_specimen_id and test_run_id must be distinct "
                            "(a design is not a physical specimen, and a specimen is not a run).")

    plan = None
    if _nullable(data, "plan_mm", unavailable) is not None:
        plan_data = _mapping(data["plan_mm"], "plan_mm", {"Lx", "Ly", "sd"})
        plan = PlanDimensions(_positive(plan_data["Lx"], "plan_mm.Lx"), _positive(plan_data["Ly"], "plan_mm.Ly"),
                              _positive(plan_data["sd"], "plan_mm.sd"))
    masses = None
    if _nullable(data, "masses_g", unavailable) is not None:
        if not isinstance(data["masses_g"], Mapping) or not data["masses_g"]:
            _fail("masses_g", "must be a non-empty object {part: grams}.")
        masses = {str(k): _positive(v, f"masses_g.{k}") for k, v in sorted(data["masses_g"].items())}
    thickness = None
    if _nullable(data, "face_thickness_mm", unavailable) is not None:
        if specimen_type == "core_tile":
            _fail("face_thickness_mm", "a core tile has no face sheets.")
        expected = {"top", "bottom"} if specimen_type == "sandwich" else {"plate"}
        raw = _mapping(data["face_thickness_mm"], "face_thickness_mm", expected)
        thickness = {}
        for sheet in sorted(expected):
            points = raw[sheet]
            if not isinstance(points, list) or len(points) < MINIMUM_THICKNESS_POINTS:
                _fail(f"face_thickness_mm.{sheet}", f"needs at least {MINIMUM_THICKNESS_POINTS} measured points (SPEC §15).")
            thickness[sheet] = tuple(_positive(v, f"face_thickness_mm.{sheet}") for v in points)
    core = None
    if _nullable(data, "core_height_mm", unavailable) is not None:
        if specimen_type == "bare_plate":
            _fail("core_height_mm", "a bare plate has no core.")
        core_data = _mapping(data["core_height_mm"], "core_height_mm", {"value", "sd"})
        core = CoreHeight(_positive(core_data["value"], "core_height_mm.value"),
                          _positive(core_data["sd"], "core_height_mm.sd"))
    materials = None
    if _nullable(data, "materials", unavailable) is not None:
        required = {"sandwich": {"face", "core"}, "bare_plate": {"face"}, "core_tile": {"core"}}[specimen_type]
        materials_data = _mapping(data["materials"], "materials", required, {"adhesive"})
        materials = {k: _text(v, f"materials.{k}") for k, v in sorted(materials_data.items())}
    suspension = None
    if _nullable(data, "suspension_max_hz", unavailable) is not None:
        suspension_data = _mapping(data["suspension_max_hz"], "suspension_max_hz", {"value_hz", "source"})
        suspension = SuspensionLimit(_positive(suspension_data["value_hz"], "suspension_max_hz.value_hz"),
                                     _text(suspension_data["source"], "suspension_max_hz.source"))

    calibration, calibration_canonical = _geometry_calibration(data["geometry_calibration"])
    fe_reference, fe_canonical = _fe_reference(data["fe_reference"])
    acquisition, acquisition_canonical = _acquisition(data["acquisition"], run)
    identify = _text(data["identify"], "identify")

    canonical = {
        "schema": SPECIMEN_MANIFEST_SCHEMA,
        "specimen_type": specimen_type,
        "family_id": str(family), "design_id": str(design),
        "physical_specimen_id": None if specimen is None else str(specimen),
        "test_run_id": str(run),
        "plan_mm": None if plan is None else {"Lx": plan.lx_mm, "Ly": plan.ly_mm, "sd": plan.sd_mm},
        "masses_g": masses,
        "face_thickness_mm": None if thickness is None else {k: list(v) for k, v in thickness.items()},
        "core_height_mm": None if core is None else {"value": core.value_mm, "sd": core.sd_mm},
        "materials": materials,
        "suspension_max_hz": None if suspension is None else {"value_hz": suspension.value_hz,
                                                              "source": suspension.source},
        "geometry_calibration": calibration_canonical,
        "fe_reference": fe_canonical,
        "acquisition": acquisition_canonical,
        "identify": identify,
        "unavailable": dict(sorted(unavailable.items())),
    }
    return SpecimenManifest(
        schema=SPECIMEN_MANIFEST_SCHEMA, specimen_type=specimen_type, family_id=family, design_id=design,
        physical_specimen_id=specimen, test_run_id=run, plan_mm=plan, masses_g=masses, face_thickness_mm=thickness,
        core_height_mm=core, materials=materials, suspension_max_hz=suspension, geometry_calibration=calibration,
        fe_reference=fe_reference, acquisition=acquisition, identify=identify, unavailable=unavailable,
        canonical=canonical,
    )


def load_specimen_manifest(path: Path) -> SpecimenManifest:
    with open(path, encoding="utf-8") as handle:
        return parse_specimen_manifest(json.load(handle))
