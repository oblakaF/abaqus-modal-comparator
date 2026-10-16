"""Guided physical registration of an ODB whose FE geometry has no accepted registration (CORE-E2E-C).

A new FE mesh of a measured specimen is not a dead end when independent physical evidence of the scan exists. The
registration is built by the accepted M2.3 core (``physical_registration.register_from_physical_calibration``): the
orientation, the physical scale and the scan position come only from that evidence; the measured-surface nodes of the
loaded FE geometry receive the experimental points. MAC, frequencies and mode shapes are never read, and no
orientation is ever chosen among geometric candidates.

Evidence sources:

- ``ACCEPTED_SCAN_CALIBRATION``: the experimental file is, by fresh SHA-256 and size, the source of an accepted
  physical passport (``docs/auto_id/specimens/*.physical.specimen.json``) whose calibration is physical (corner-A
  marker or measured scan-to-panel-edge offsets). That passport's orientation is stated in the frame of *its* FE model,
  so the loaded FE model must be in the same frame: every FE instance's bounding box must equal the reference FE
  geometry's (pinned geometry file, SHA-256 checked) within the passport surface tolerance. The old node mapping is
  never reused: the frozen registration of the accepted FE geometry is not applied to another node identity.
- ``EVIDENCE_FILE``: a ``auto-id/guided-physical-evidence/v1`` record with the same ``geometry_calibration`` rules
  as a passport, the experimental source it describes (SHA-256, size, modal set, measured DOFs) and the FE frame it
  refers to (the exact FE geometry identity, or reference instance bounding boxes).

The checks before a registration exists: physical calibration mode and orientation reference; the experimental
content, modal set, point count and measured-DOF contract; the FE frame; the measured surface. After it: the
comparator's own geometry limits (matched fraction >= 0.90, normalised RMS <= 0.03 of the scan diagonal), no
mirroring, every experimental point on its own FE node.

A guided registration is diagnostic engineering registration: it enables the gated comparison (pairs, MAC) of these
exact files. It is not governed evidence, adds no Auto-ID observation and is never production-ready.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from coordinate_calibration import millimetres_to_model_units
from domain.experiment_fixture import (
    FixtureSourceUnavailableError,
    fixture_roots_from_environment,
    load_experiment_fixture_manifest,
    resolve_external_file,
)
from domain.registration import FrozenRegistration, RegistrationMismatchError
from domain.specimen_manifest import (
    PHYSICAL_CALIBRATION_MODES,
    canonical_hash,
    load_specimen_manifest,
    parse_geometry_calibration,
)
from scientific_state import modal_dataset_geometry_identity

from .physical_registration import (
    PHYSICAL_ORIENTATION_REFERENCES,
    SURFACE_TOLERANCE_MM,
    FEGeometry,
    PhysicalRegistrationRefusal,
    register_from_physical_calibration,
)
from .production_modal_input import FIXTURE_MANIFEST_PATH, REPO_ROOT

EVIDENCE_SCHEMA = "auto-id/guided-physical-evidence/v1"
RECORD_SCHEMA = "auto-id/guided-registration/v1"
GUIDED_SOURCE = "GUIDED_PHYSICAL_REGISTRATION"
ACCEPTED_SCAN = "ACCEPTED_SCAN_CALIBRATION"
EVIDENCE_FILE = "EVIDENCE_FILE"
MINIMUM_MATCHED_FRACTION = 0.90  # the comparator's geometry limits (reviewed_core geometry warnings)
MAXIMUM_NORMALIZED_RMS = 0.03
PASSPORTS = "docs/auto_id/specimens"
LIMITS = (
    "diagnostic engineering registration of these exact files: not governed evidence, no Auto-ID observation, "
    "not production-ready (SPEC v1.2 §11 governed passport / fixture route not replaced)",
    "orientation, scale and scan position from the stated physical evidence only; MAC and frequencies never used",
)


class GuidedRegistrationRefusal(Exception):
    """The evidence or the files cannot give a guided registration; ``field`` names what is missing or wrong."""

    def __init__(self, field_name: str, message: str) -> None:
        super().__init__(f"{field_name}: {message}")
        self.field = field_name


def _require(condition: bool, field_name: str, message: str) -> None:
    if not condition:
        raise GuidedRegistrationRefusal(field_name, message)


def _short(value: object) -> str:
    return f"{str(value)[:12]}…"


# ----------------------------------------------------------------------------- FE frame

Box = tuple[float, float, float, float, float, float]


def _instance_boxes(node_ids: Sequence[object], coordinates: np.ndarray) -> dict[str, Box]:
    instances = np.array([str(value).split(":")[0] for value in node_ids])
    boxes = {}
    for name in sorted(set(instances.tolist())):
        points = coordinates[instances == name]
        boxes[name] = tuple(float(v) for v in (*points.min(axis=0), *points.max(axis=0)))
    return boxes


def fe_geometry_of(abaqus) -> FEGeometry:
    """The loaded ODB's nodes as the M2 builder's FE geometry (identity from the loaded modes)."""
    reference = abaqus.sorted_modes()[0]
    node_ids = np.asarray([str(value) for value in np.asarray(reference.node_ids, dtype=object)])
    _require(all(":" in value for value in node_ids[:10]), "fe_geometry",
             "the FE node ids carry no instance name (INSTANCE:label); a measured surface cannot be selected.")
    return FEGeometry(node_ids, np.asarray(reference.coordinates, dtype=float), modal_dataset_geometry_identity(abaqus))


def geometry_file_boxes(path: Path) -> dict[str, Box]:
    """Instance bounding boxes of an FE geometry file (instance,node_label,x,y,z), streamed."""
    boxes: dict[str, list[float]] = {}
    with open(path, newline="", encoding="utf-8") as stream:
        reader = csv.reader(stream)
        header = next(reader)
        _require(header[:5] == ["instance", "node_label", "x", "y", "z"], "fe_frame.geometry_file",
                 f"{path.name} is not an FE geometry file (instance,node_label,x,y,z).")
        for instance, _label, x, y, z in reader:
            point = (float(x), float(y), float(z))
            box = boxes.get(instance)
            if box is None:
                boxes[instance] = [*point, *point]
                continue
            for axis in range(3):
                if point[axis] < box[axis]:
                    box[axis] = point[axis]
                if point[axis] > box[axis + 3]:
                    box[axis + 3] = point[axis]
    return {name: tuple(box) for name, box in sorted(boxes.items())}


def compare_fe_frames(loaded: Mapping[str, Box], reference: Mapping[str, Box], abaqus_unit: str) -> list[str]:
    """Differences between two FE frames (empty: the same frame within the passport surface tolerance)."""
    tolerance = millimetres_to_model_units(SURFACE_TOLERANCE_MM, abaqus_unit)
    problems = []
    if set(loaded) != set(reference):
        problems.append(f"instances {sorted(loaded)} differ from the reference {sorted(reference)}")
    for name in sorted(set(loaded) & set(reference)):
        worst = max(abs(a - b) for a, b in zip(loaded[name], reference[name]))
        if worst > tolerance:
            problems.append(f"{name} bounding box differs by up to {worst:.6g} {abaqus_unit} (limit {tolerance:.3g})")
    return problems


# ----------------------------------------------------------------------------- evidence

@dataclass(frozen=True)
class PhysicalEvidence:
    kind: str  # ACCEPTED_SCAN | EVIDENCE_FILE
    label: str
    physical_specimen_id: Optional[str]
    geometry_calibration: Any  # domain.specimen_manifest.GeometryCalibration
    calibration_document: Mapping[str, Any]  # the canonical geometry_calibration record
    experimental_source: Mapping[str, Any]  # {"sha256", "size", "name"}
    registration_source_identity: Mapping[str, Any]  # what the FrozenRegistration records
    modal_set: str
    measured_dofs: tuple[str, ...]
    point_count: Optional[int]
    fe_frame: Mapping[str, Any]  # {"fe_geometry_identity": {...}} and/or {"instance_boxes": {...}} / {"geometry_file"}
    provenance: tuple[str, ...] = ()
    reference_geometry_file: Any = None  # pinned ExternalFileReference of an accepted passport

    def document(self) -> dict:
        return {"schema": EVIDENCE_SCHEMA, "kind": self.kind, "label": self.label,
                "physical_specimen_id": self.physical_specimen_id,
                "geometry_calibration": json.loads(json.dumps(self.calibration_document)),
                "experimental_source": dict(self.experimental_source), "modal_set": self.modal_set,
                "measured_dofs": list(self.measured_dofs), "point_count": self.point_count,
                "fe_frame": json.loads(json.dumps(self.fe_frame)), "provenance": list(self.provenance)}

    @property
    def evidence_hash(self) -> str:
        return canonical_hash(self.document())


def accepted_scan_evidence(experimental_identity: Mapping[str, Any], *, repo_root: Path = REPO_ROOT,
                           fixture_manifest=None) -> PhysicalEvidence:
    """The physical scan calibration of an accepted passport whose experimental source is this file, or refuse."""
    fixtures = load_experiment_fixture_manifest(Path(repo_root) / FIXTURE_MANIFEST_PATH.relative_to(REPO_ROOT)) \
        if fixture_manifest is None else fixture_manifest
    found = []
    for path in sorted((Path(repo_root) / PASSPORTS).glob("*.physical.specimen.json")):
        manifest = load_specimen_manifest(path)
        fixture_id = manifest.acquisition.fixture_id
        if fixture_id is None:
            continue
        fixture = fixtures.fixture(fixture_id)
        source = fixture.experimental_source
        wanted = (experimental_identity.get("sha256"), experimental_identity.get("size"))
        if (source.sha256, source.size_bytes) == wanted:
            found.append((path, manifest, fixture))
    _require(bool(found), "experimental_source",
             f"the experimental file {_short(experimental_identity.get('sha256'))} is not the source of an accepted "
             "physical passport; load a physical evidence file instead.")
    _require(len(found) == 1, "experimental_source", "several accepted passports name this file; none is chosen.")
    path, manifest, fixture = found[0]
    calibration = manifest.geometry_calibration
    _require(calibration.mode in PHYSICAL_CALIBRATION_MODES, "geometry_calibration.mode",
             f"the accepted passport {path.name} has no physical calibration ({calibration.mode}).")
    _, document = parse_geometry_calibration(json.loads(path.read_text(encoding="utf-8"))["geometry_calibration"])
    source = fixture.experimental_source
    reference = manifest.fe_reference
    return PhysicalEvidence(
        kind=ACCEPTED_SCAN, label=f"accepted physical scan calibration of {fixture.fixture_id} ({path.name})",
        physical_specimen_id=None if manifest.physical_specimen_id is None else str(manifest.physical_specimen_id),
        geometry_calibration=calibration, calibration_document=document,
        experimental_source={"sha256": source.sha256, "size": source.size_bytes, "name": source.file_name},
        registration_source_identity={"path": f"{source.location.store}:{source.location.relative_path}",
                                      "size": source.size_bytes, "mtime_ns": None, "sha256": source.sha256},
        modal_set=fixture.modal_set.name, measured_dofs=tuple(fixture.modal_set.measured_dofs),
        point_count=manifest.acquisition.grid.point_count,
        fe_frame={"model_name": reference.model_name,
                  "fe_geometry_identity": {"schema_version": reference.geometry_identity.schema_version,
                                           "sha256": reference.geometry_identity.sha256,
                                           "node_count": reference.geometry_identity.node_count},
                  "geometry_file": {"file_name": reference.geometry_file.file_name,
                                    "sha256": reference.geometry_file.sha256,
                                    "size_bytes": reference.geometry_file.size_bytes}},
        provenance=(f"passport {path.name} (manifest {_short(manifest.manifest_hash)})",
                    f"orientation: {calibration.orientation.source}"),
        reference_geometry_file=reference.geometry_file)


def evidence_from_document(document: Mapping[str, Any]) -> PhysicalEvidence:
    """A guided physical evidence record (the passport's geometry_calibration rules apply)."""
    _require(isinstance(document, Mapping) and document.get("schema") == EVIDENCE_SCHEMA, "schema",
             f"not a {EVIDENCE_SCHEMA} record.")
    try:
        calibration, canonical = parse_geometry_calibration(document.get("geometry_calibration"))
    except ValueError as error:
        raise GuidedRegistrationRefusal("geometry_calibration", str(error)) from error
    source = document.get("experimental_source") or {}
    _require(isinstance(source.get("sha256"), str) and len(source["sha256"]) == 64
             and isinstance(source.get("size"), int), "experimental_source",
             "the SHA-256 and size of the experimental file the evidence describes are required.")
    dofs = document.get("measured_dofs")
    _require(isinstance(dofs, list) and dofs and all(d in ("U1", "U2", "U3") for d in dofs), "measured_dofs",
             "the measured DOFs (for example [\"U3\"]) are required.")
    frame = document.get("fe_frame") or {}
    _require(isinstance(frame.get("fe_geometry_identity"), Mapping) or isinstance(frame.get("instance_boxes"), Mapping),
             "fe_frame", "the FE frame the orientation refers to is required: the exact FE geometry identity or the "
                         "reference instance bounding boxes.")
    modal_set = document.get("modal_set")
    _require(isinstance(modal_set, str) and modal_set.strip() != "", "modal_set", "the modal set key is required.")
    name = str(source.get("name") or "experimental file")
    return PhysicalEvidence(
        kind=EVIDENCE_FILE, label=str(document.get("label") or "physical evidence file"),
        physical_specimen_id=document.get("physical_specimen_id"), geometry_calibration=calibration,
        calibration_document=canonical,
        experimental_source={"sha256": source["sha256"], "size": source["size"], "name": name},
        registration_source_identity={"path": name, "size": source["size"], "mtime_ns": None,
                                      "sha256": source["sha256"]},
        modal_set=modal_set, measured_dofs=tuple(dofs), point_count=document.get("point_count"),
        fe_frame=dict(frame), provenance=tuple(str(item) for item in document.get("provenance") or ()))


def load_evidence_file(path: Path) -> PhysicalEvidence:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise GuidedRegistrationRefusal("evidence_file", f"{path} cannot be read: {error}") from error
    return evidence_from_document(document)


def evidence_template(abaqus, experimental, experimental_identity: Mapping[str, Any], experimental_name: str) -> dict:
    """An evidence record to fill in: every physical field is explicit and empty; nothing is guessed."""
    modes = experimental.sorted_modes()
    return {
        "schema": EVIDENCE_SCHEMA, "label": "physical evidence of the scan (fill in)", "physical_specimen_id": None,
        "experimental_source": {"name": experimental_name, "sha256": experimental_identity.get("sha256"),
                                "size": experimental_identity.get("size")},
        "modal_set": experimental.metadata.get("modal_set_key"), "measured_dofs": ["U3"],
        "point_count": len(modes[0].node_ids) if modes else None,
        "fe_frame": {"fe_geometry_identity": dict(modal_dataset_geometry_identity(abaqus)),
                     "note": "the orientation below is stated in THIS FE model's axes"},
        "geometry_calibration": {
            "mode": "scan_to_panel_edges or corner_coordinates_mm",
            "coordinate_calibration": {"mode": "camera_grid or metric", "abaqus_unit": "mm", "experimental_unit": "m",
                                       "scan_coverage": "partial or full", "physical_width": None,
                                       "physical_height": None, "dimension_unit": "mm", "manual_scale": None,
                                       "provenance": "how the physical scan window was measured"},
            "measured_surface": {"fe_instance": None, "side": "max_z or min_z",
                                 "label": "which physical face the scanner measured"},
            "orientation": {"experimental_axes_in_fe": ["+X", "+Y", "+Z"],
                            "reference": "panel_edges or corner_A_marker",
                            "source": "photograph / marker record establishing the axes"},
            "uncertainty": {"translation_mm": None, "scale_rel": None, "rotation_deg": None},
            "panel_edges": {"x_mm": None, "y_mm": None}},
        "provenance": []}


# ----------------------------------------------------------------------------- the registration

@dataclass(frozen=True)
class GuidedRegistration:
    registration: FrozenRegistration
    evidence: Mapping[str, Any]  # the evidence document
    evidence_hash: str
    fe_geometry_identity: Mapping[str, Any]
    experimental_identity: Mapping[str, Any]  # {"sha256", "size"}
    checks: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    metrics: Mapping[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict:
        body = {"schema": RECORD_SCHEMA, "status": GUIDED_SOURCE, "limits": list(LIMITS),
                "registration": self.registration.to_dict(), "evidence": json.loads(json.dumps(self.evidence)),
                "evidence_hash": self.evidence_hash, "fe_geometry_identity": dict(self.fe_geometry_identity),
                "experimental_identity": dict(self.experimental_identity), "checks": list(self.checks),
                "warnings": list(self.warnings), "metrics": json.loads(json.dumps(self.metrics))}
        return dict(body, record_hash=canonical_hash(body))

    def provenance(self) -> dict:
        return {"source": GUIDED_SOURCE, "registration_hash": self.registration.registration_hash,
                "evidence": self.evidence.get("label"), "evidence_kind": self.evidence.get("kind"),
                "evidence_hash": self.evidence_hash, "fe_geometry_sha256": self.fe_geometry_identity.get("sha256"),
                "fe_node_count": self.fe_geometry_identity.get("node_count"),
                "experimental_sha256": self.experimental_identity.get("sha256"), "checks": list(self.checks),
                "limits": list(LIMITS), "production_ready": False, "governed": False}

    def warning(self) -> str:
        return (f"Guided physical registration applied ({GUIDED_SOURCE}): registration "
                f"{_short(self.registration.registration_hash)} from {self.evidence.get('label')}, for FE geometry "
                f"{_short(self.fe_geometry_identity.get('sha256'))} ({self.fe_geometry_identity.get('node_count')} "
                f"nodes). " + "; ".join(LIMITS) + ".")


def establish_guided_registration(abaqus, experimental, experimental_identity: Mapping[str, Any],
                                  evidence: PhysicalEvidence, *, roots: Optional[Mapping[str, Path]] = None,
                                  reference_geometry_path: Optional[Path] = None) -> GuidedRegistration:
    """Build the registration the evidence defines for the loaded FE geometry, or refuse with the reason."""
    checks: list[str] = []
    calibration = evidence.geometry_calibration
    unit = calibration.calibration.abaqus_unit
    _require(calibration.mode in PHYSICAL_CALIBRATION_MODES, "geometry_calibration.mode",
             f"{calibration.mode} is not a physical calibration (corner-A marker or scan-to-panel-edge offsets "
             "required).")
    _require(calibration.orientation.reference in PHYSICAL_ORIENTATION_REFERENCES, "orientation.reference",
             f"orientation reference {calibration.orientation.reference!r} is not physically traceable.")
    rotation = calibration.orientation.rotation
    _require(float(np.linalg.det(rotation)) > 0.0, "orientation.experimental_axes_in_fe",
             "the stated axes mirror the FE model (determinant -1); a mirrored scan is not accepted here.")
    axes = list(calibration.orientation.experimental_axes_in_fe)
    checks.append(f"physical calibration {calibration.mode}; orientation {axes} from "
                  f"{calibration.orientation.reference} (not mirrored)")
    _require(experimental_identity.get("sha256") == evidence.experimental_source.get("sha256")
             and experimental_identity.get("size") == evidence.experimental_source.get("size"), "experimental_source",
             f"the loaded experimental file {_short(experimental_identity.get('sha256'))} is not the file the "
             f"evidence describes ({_short(evidence.experimental_source.get('sha256'))}).")
    checks.append(f"experimental content SHA-256 {_short(experimental_identity['sha256'])} = the evidence's "
                  f"{evidence.experimental_source.get('name')}")
    key = experimental.metadata.get("modal_set_key")
    _require(key == evidence.modal_set, "modal_set",
             f"the loaded modal set is {key!r}; the evidence describes {evidence.modal_set!r}.")
    points = len(experimental.sorted_modes()[0].node_ids)
    _require(evidence.point_count in (None, points), "point_count",
             f"the loaded grid has {points} points; the evidence states {evidence.point_count}.")
    checks.append(f"modal set {key!r}, {points} measurement points")

    fe = fe_geometry_of(abaqus)
    loaded_boxes = _instance_boxes(fe.node_ids, fe.coordinates)
    frame = evidence.fe_frame
    identity = frame.get("fe_geometry_identity")
    same_identity = isinstance(identity, Mapping) and identity.get("sha256") == fe.identity["sha256"] \
        and identity.get("node_count") == fe.identity["node_count"]
    if same_identity:
        checks.append(f"FE geometry {_short(fe.identity['sha256'])} is the FE model the evidence refers to")
    else:
        reference = frame.get("instance_boxes")
        source = "the evidence's reference instance boxes"
        if reference is None:
            reference, source = _reference_boxes(evidence, roots, reference_geometry_path)
        problems = compare_fe_frames(loaded_boxes, {k: tuple(v) for k, v in reference.items()}, unit)
        _require(not problems, "fe_frame",
                 "the loaded FE model is not in the frame the orientation is stated in: " + "; ".join(problems))
        checks.append(f"FE frame: every instance bounding box equals {source} within "
                      f"{SURFACE_TOLERANCE_MM:g} mm (FE geometry {_short(fe.identity['sha256'])}, "
                      f"{fe.identity['node_count']} nodes, differs from the reference node identity)")
    try:
        registration, surface_ids = register_from_physical_calibration(
            calibration, fe, experimental, evidence.measured_dofs, evidence.registration_source_identity)
    except PhysicalRegistrationRefusal as error:
        raise GuidedRegistrationRefusal(error.field, str(error)) from error
    metrics = registration.to_dict()["registration_metrics"]  # plain JSON values
    checks.append(f"measured surface {calibration.measured_surface.fe_instance} {calibration.measured_surface.side}: "
                  f"{len(surface_ids)} FE nodes; measured DOFs {'/'.join(evidence.measured_dofs)}")
    _require(metrics["matched_fraction"] >= MINIMUM_MATCHED_FRACTION, "mapping",
             f"only {metrics['matched_fraction']:.1%} of the points lie within the geometry tolerance "
             f"(at least {MINIMUM_MATCHED_FRACTION:.0%} required).")
    _require(metrics["normalized_rms_distance"] <= MAXIMUM_NORMALIZED_RMS, "mapping",
             f"mapping RMS {metrics['normalized_rms_distance']:.2%} of the scan diagonal exceeds "
             f"{MAXIMUM_NORMALIZED_RMS:.0%}.")
    _require(metrics["unique_mapped_abaqus_nodes"] == metrics["experimental_point_count"], "mapping",
             f"{metrics['experimental_point_count'] - metrics['unique_mapped_abaqus_nodes']} points share an FE node.")
    checks.append(f"mapping: matched {metrics['matched_fraction']:.1%}, RMS "
                  f"{metrics['mapping_rms_in_abaqus_units']:.3g} {unit} (max "
                  f"{metrics['mapping_max_residual_in_abaqus_units']:.3g} {unit}), axis permutation "
                  f"{metrics['axis_permutation']}, every point on its own FE node")
    warnings = ()
    if calibration.uncertainty.missing:
        warnings = (f"registration uncertainty not available: {', '.join(calibration.uncertainty.missing)}",)
    return GuidedRegistration(registration, evidence.document(), evidence.evidence_hash, dict(fe.identity),
                              {"sha256": experimental_identity["sha256"], "size": experimental_identity["size"]},
                              tuple(checks), warnings, metrics)


def _reference_boxes(evidence: PhysicalEvidence, roots, reference_geometry_path) -> tuple[dict, str]:
    pinned = evidence.reference_geometry_file
    _require(pinned is not None, "fe_frame", "the evidence names no reference FE geometry for its orientation.")
    if reference_geometry_path is not None:
        from services.archived_sensitivity_evidence import fresh_content_identity

        identity = fresh_content_identity(Path(reference_geometry_path))
        _require((identity["sha256"], identity["size"]) == (pinned.sha256, pinned.size_bytes), "fe_frame.geometry_file",
                 f"{Path(reference_geometry_path).name} is not the pinned reference FE geometry {pinned.file_name} "
                 f"({_short(pinned.sha256)}).")
        path = Path(reference_geometry_path)
    else:
        try:
            path = resolve_external_file(pinned, fixture_roots_from_environment() if roots is None else roots)
        except (FixtureSourceUnavailableError, OSError, ValueError) as error:
            raise GuidedRegistrationRefusal(
                "fe_frame.geometry_file",
                f"the reference FE geometry {pinned.file_name} ({_short(pinned.sha256)}) is not available: {error} "
                "Locate a copy of it (for example the geometry.csv of an extraction of the accepted ODB).") from error
    return geometry_file_boxes(path), f"the reference FE geometry {pinned.file_name} ({_short(pinned.sha256)})"


# ----------------------------------------------------------------------------- save / reopen

def save_guided_registration(guided: GuidedRegistration, path: Path) -> Path:
    path = Path(path)
    path.write_text(json.dumps(guided.to_record(), indent=1), encoding="utf-8")
    return path


def load_guided_registration(path: Path) -> GuidedRegistration:
    """A saved guided registration whose record and registration hashes verify; not yet bound to any files."""
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise GuidedRegistrationRefusal("record", f"{path} cannot be read: {error}") from error
    _require(isinstance(record, dict) and record.get("schema") == RECORD_SCHEMA, "record",
             f"not a {RECORD_SCHEMA} record.")
    body = {k: v for k, v in record.items() if k != "record_hash"}
    _require(record.get("record_hash") == canonical_hash(body), "record_hash",
             "the saved record was changed after it was written.")
    try:
        registration = FrozenRegistration.from_dict(record["registration"])  # verifies the registration hash
    except (KeyError, TypeError, ValueError) as error:
        raise GuidedRegistrationRefusal("registration", f"the saved registration is not valid: {error}") from error
    _require(canonical_hash(record["evidence"]) == record["evidence_hash"], "evidence_hash",
             "the saved evidence does not match its hash.")
    return GuidedRegistration(registration, record["evidence"], record["evidence_hash"],
                              record["fe_geometry_identity"], record["experimental_identity"],
                              tuple(record["checks"]), tuple(record.get("warnings", ())), record.get("metrics", {}))


def verify_for_files(guided: GuidedRegistration, abaqus, experimental,
                     experimental_identity: Mapping[str, Any]) -> tuple[str, ...]:
    """The guided registration may be applied to these loaded files, or raise with the reason."""
    registration = guided.registration
    try:
        fe_identity = modal_dataset_geometry_identity(abaqus)
    except ValueError as error:
        raise GuidedRegistrationRefusal("fe_geometry_identity", str(error)) from error
    try:
        registration.check_content_compatible(experimental_identity, fe_identity)
    except (RegistrationMismatchError, ValueError) as error:
        raise GuidedRegistrationRefusal(
            "files", f"the guided registration {_short(registration.registration_hash)} was made for other files "
                     f"({error}).") from error
    key = experimental.metadata.get("modal_set_key")
    _require(key == registration.experimental_modal_set_identity, "modal_set",
             f"the loaded modal set {key!r} is not the registration's "
             f"{registration.experimental_modal_set_identity!r}.")
    reference = experimental.sorted_modes()[0]
    loaded_points = [value.item() if isinstance(value, np.generic) else value
                     for value in np.asarray(reference.node_ids, dtype=object)]
    _require(list(loaded_points) == list(registration.experimental_node_ids), "measurement_points",
             "the loaded measurement points differ from the registration's.")
    from reviewed_core import experimental_measurement_masks

    modes = experimental.sorted_modes()
    masks = np.asarray(experimental_measurement_masks(modes, modes[0].node_ids)[0], dtype=bool).tolist()
    _require(masks == [list(row) for row in registration.measured_dof_contract], "measured_dof_contract",
             "the loaded measured DOFs differ from the registration's measured-DOF contract.")
    present = {str(value) for value in np.asarray(abaqus.sorted_modes()[0].node_ids, dtype=object)}
    missing = [node for node in registration.mapped_fe_node_ids if node not in present]
    _require(not missing, "mapped_fe_nodes", f"{len(missing)} mapped FE nodes are absent from the ODB.")
    return (f"guided registration {_short(registration.registration_hash)} matches the loaded experimental content, "
            f"modal set {key!r}, measurement points, measured DOFs and FE geometry {_short(fe_identity['sha256'])}",)


def summary_rows(guided: GuidedRegistration) -> list[tuple[str, str]]:
    metrics = guided.metrics
    return [("Status", f"{GUIDED_SOURCE} (diagnostic; not governed; not production-ready)"),
            ("Registration", guided.registration.registration_hash),
            ("Evidence", f"{guided.evidence.get('label')} ({_short(guided.evidence_hash)})"),
            ("FE geometry", "{} ({} nodes)".format(guided.fe_geometry_identity.get("sha256"),
                                                   guided.fe_geometry_identity.get("node_count"))),
            ("Experimental file", "{} ({} bytes)".format(guided.experimental_identity.get("sha256"),
                                                         guided.experimental_identity.get("size"))),
            ("Matched fraction", f"{metrics.get('matched_fraction', math.nan):.1%}"),
            ("Mapping RMS / max", f"{metrics.get('mapping_rms_in_abaqus_units', math.nan):.3g} / "
                                  f"{metrics.get('mapping_max_residual_in_abaqus_units', math.nan):.3g} (FE units)"),
            ("Mirrored / axis permutation", f"{metrics.get('mirrored')} / {metrics.get('axis_permutation')}")]


REQUIRED_EVIDENCE = (
    ("orientation", "physical orientation of the scan grid: corner-A marker or measured scan-to-panel-edge offsets, "
                    "with the photograph / marker record"),
    ("coordinate_calibration", "physical scan window (or metric coordinates) with its provenance and units"),
    ("measured_surface", "the FE instance and side (max_z / min_z) of the face the scanner measured"),
    ("measured_dofs", "the measured DOFs of the experimental modes (for example U3)"),
    ("fe_frame", "the FE frame the orientation is stated in: this FE model's geometry identity, or a reference FE "
                 "geometry in the same frame"),
    ("experimental_source", "the SHA-256 and size of the experimental file the evidence describes, and its modal set"),
)


def evidence_rows(evidence: Optional[PhysicalEvidence]) -> list[tuple[str, str, str]]:
    """The physical fields as the form shows them: (field, value, PROVIDED / MISSING)."""
    if evidence is None:
        return [(name, text, "MISSING") for name, text in REQUIRED_EVIDENCE]
    calibration = evidence.geometry_calibration
    coordinate = calibration.coordinate_calibration
    surface = calibration.measured_surface
    if calibration.panel_edges is not None:
        edges = calibration.panel_edges
        position = f"scan-to-panel-edge offsets x {edges.x_mm:g} mm, y {edges.y_mm:g} mm"
    elif calibration.corner_a is not None:
        corner = calibration.corner_a
        position = (f"corner A = UNV node {corner.unv_node} at FE ({corner.fe_xy_mm[0]:g}, {corner.fe_xy_mm[1]:g}) mm, "
                    f"x axis towards UNV node {corner.x_axis_towards_unv_node}")
    else:
        position = "no physical scan position"
    frame = evidence.fe_frame
    identity = frame.get("fe_geometry_identity") or {}
    reference = frame.get("geometry_file") or {}
    frame_text = (f"stated for FE geometry {_short(identity.get('sha256'))} ({identity.get('node_count')} nodes)"
                  + (f"; reference geometry file {reference.get('file_name')} ({_short(reference.get('sha256'))})"
                     if reference else "")
                  + ("; reference instance boxes given" if frame.get("instance_boxes") else ""))
    uncertainty = calibration.uncertainty
    return [
        ("evidence", f"{evidence.label} [{evidence.kind}]", "PROVIDED"),
        ("physical specimen", str(evidence.physical_specimen_id or "not recorded"),
         "PROVIDED" if evidence.physical_specimen_id else "MISSING"),
        ("calibration mode", calibration.mode,
         "PROVIDED" if calibration.mode in PHYSICAL_CALIBRATION_MODES else "NOT PHYSICAL"),
        ("orientation", f"experimental axes in FE {list(calibration.orientation.experimental_axes_in_fe)}; reference "
                        f"{calibration.orientation.reference}; {calibration.orientation.source}",
         "PROVIDED" if calibration.orientation.reference in PHYSICAL_ORIENTATION_REFERENCES else "NOT TRACEABLE"),
        ("scan position", position, "PROVIDED"),
        ("coordinates and units", f"{coordinate.get('mode')}; experimental {coordinate.get('experimental_unit')}, FE "
                                  f"{coordinate.get('abaqus_unit')}; scan window {coordinate.get('physical_width')} x "
                                  f"{coordinate.get('physical_height')} {coordinate.get('dimension_unit')}; "
                                  f"{coordinate.get('provenance')}", "PROVIDED"),
        ("measured surface", f"{surface.fe_instance} {surface.side}: {surface.label}", "PROVIDED"),
        ("measured DOFs", "/".join(evidence.measured_dofs), "PROVIDED"),
        ("experimental file", "{} {} ({} bytes), modal set {!r}".format(
            evidence.experimental_source.get("name"), _short(evidence.experimental_source.get("sha256")),
            evidence.experimental_source.get("size"), evidence.modal_set),
         "PROVIDED"),
        ("FE frame", frame_text, "PROVIDED"),
        ("registration uncertainty", ", ".join(f"{k} {getattr(uncertainty, k)}" for k in uncertainty.available)
         or "not recorded", "PROVIDED" if not uncertainty.missing else "NOT AVAILABLE"),
    ]
