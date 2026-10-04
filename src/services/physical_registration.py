"""FrozenRegistration from physical calibration — Auto-ID M2.3 (SPEC §6 S2, §11; D-007).

Registration is built only from the specimen passport's ``geometry_calibration``, the
pinned experimental geometry (M0.2 fixture) and the FE geometry, whose identity is
verified against the passport.  It never consults MAC, frequencies, mode shapes or
identification results, and never tries orientations against modal agreement.

Calibration modes:

- ``corner_coordinates_mm`` (SPEC §4.1/§11): rotation from the documented axes, checked
  by the corner-A → x-axis marker; translation from the corner-A correspondence; scale
  from the physical calibration.
- ``scan_to_panel_edges``: rotation from the documented axes; translation from the
  measured offset of the scan grid's minimum corner from the panel's minimum corner.
- ``documented_centered_alignment`` (historical accepted basis): rotation from the
  documented axis convention; centre-to-centre placement of the existing geometric
  alignment.  The candidate whose rotation *equals* the documented rotation is used;
  candidates are never ranked by modal agreement.  Never physically complete.

The registration is deterministic: the same passport, experimental geometry and FE
geometry give the same registration hash.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from scipy.spatial import cKDTree

from coordinate_calibration import millimetres_to_model_units, scale_candidates
from domain.experiment_fixture import (
    ExperimentFixtureManifest,
    fixture_roots_from_environment,
    load_experiment_fixture_manifest,
    resolve_external_file,
)
from domain.registration import FrozenRegistration
from domain.specimen_manifest import (
    CORNER_COORDINATES,
    DOCUMENTED_CENTERED,
    PANEL_EDGES,
    RegistrationBasisStatus,
    SpecimenManifest,
    UncertaintyAvailability,
)
from modal_core import ModalDataset, ModeShape
from reviewed_core import (
    _candidate_summary,
    _geometry_equivalence_key,
    _resolve_fe_mapping_node_ids,
    experimental_measurement_masks,
    geometry_alignment_candidates,
)
from scientific_state import calibration_fingerprint, fe_geometry_identity, geometry_candidate_id
import universal_reader

from .production_modal_input import FIXTURE_MANIFEST_PATH, REPO_ROOT


SURFACE_TOLERANCE_MM = 1.0e-4  # physical; the accepted CARBON-4C replay rule for mm models
PHYSICAL_ORIENTATION_REFERENCES = ("corner_A_marker", "panel_edges")
_COMPONENTS = ("U1", "U2", "U3")


class PhysicalRegistrationRefusal(Exception):
    """The passport and data cannot produce a physical registration; nothing is guessed.

    Not a ValueError/RuntimeError, so generic fallback handlers never swallow it.
    """

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field


@dataclass(frozen=True)
class FEGeometry:
    node_ids: np.ndarray  # "INSTANCE:label" strings
    coordinates: np.ndarray  # (n, 3) FE units
    identity: Mapping[str, Any]

    def surface_node_ids(self, instance: str, side: str, abaqus_unit: str) -> list[str]:
        instances = np.array([value.split(":")[0] for value in self.node_ids])
        z = self.coordinates[:, 2]
        selected = instances == instance
        if not np.any(selected):
            raise PhysicalRegistrationRefusal("measured_surface.fe_instance", f"{instance!r} is not in the FE model.")
        level = float(z[selected].max() if side == "max_z" else z[selected].min())
        tolerance = millimetres_to_model_units(SURFACE_TOLERANCE_MM, abaqus_unit)
        return self.node_ids[selected & (np.abs(z - level) <= tolerance)].tolist()


class ProductionReadinessRefusal(Exception):
    """A registration may be replayed for regression, but is not a production SPEC §11 registration.

    Not a ValueError/RuntimeError, so generic fallback handlers never swallow it.
    """

    def __init__(self, reasons: tuple[str, ...]) -> None:
        super().__init__("not production-ready: " + "; ".join(reasons))
        self.reasons = reasons


@dataclass(frozen=True)
class PhysicalRegistrationResult:
    registration: FrozenRegistration
    calibration_mode: str
    registration_basis_status: RegistrationBasisStatus  # physical basis of the nominal registration
    uncertainty_availability: UncertaintyAvailability  # measured calibration uncertainty, separately
    missing_physical_evidence: tuple[str, ...]  # nominal-registration gaps only
    missing_uncertainty: tuple[str, ...]
    orientation_reference: str
    physical_specimen_id: str | None
    manifest_hash: str
    source_identity_basis: str  # "legacy_accepted_registration" or "content"
    surface_node_ids: tuple[str, ...]

    def production_readiness_issues(self) -> tuple[str, ...]:
        """Why this registration may not be used by production Auto-ID (empty: ready).

        Missing calibration *uncertainty* is not an issue here: it makes the M2.4 diagnostic
        NOT_AVAILABLE / PARTIAL but does not invalidate a physical nominal registration.
        """
        issues = []
        if self.registration_basis_status is RegistrationBasisStatus.LEGACY_REPLAY:
            issues.append("registration basis is LEGACY_REPLAY (historical accepted registration, not SPEC §11 "
                          "physical calibration)")
        elif self.registration_basis_status is not RegistrationBasisStatus.PHYSICAL:
            issues.append(f"registration basis is {self.registration_basis_status.value}")
        issues.extend(f"missing {item}" for item in self.missing_physical_evidence)
        if self.orientation_reference not in PHYSICAL_ORIENTATION_REFERENCES:
            issues.append(f"orientation is not physically traceable (reference {self.orientation_reference!r})")
        if self.source_identity_basis != "content":
            issues.append("experimental source identity is the legacy path/mtime record, not a content identity")
        if self.physical_specimen_id is None:
            issues.append("physical_specimen_id is not recorded")
        return tuple(issues)

    @property
    def production_ready(self) -> bool:
        return not self.production_readiness_issues()

    def require_production_ready(self) -> FrozenRegistration:
        """Return the registration for production Auto-ID, or raise ProductionReadinessRefusal."""
        issues = self.production_readiness_issues()
        if issues:
            raise ProductionReadinessRefusal(issues)
        return self.registration


def require_production_physical_registration(result: PhysicalRegistrationResult) -> FrozenRegistration:
    """Production Auto-ID boundary: a historical replay is never silently upgraded to physical."""
    return result.require_production_ready()


def load_fe_geometry(manifest: SpecimenManifest, roots: Mapping[str, Path]) -> FEGeometry:
    """Read the passport's FE geometry file (instance,node_label,x,y,z) and verify its identity."""

    path = resolve_external_file(manifest.fe_reference.geometry_file, roots)
    table = np.genfromtxt(path, delimiter=",", names=True, dtype=None, encoding="utf-8")
    for column in ("instance", "node_label", "x", "y", "z"):
        if column not in table.dtype.names:
            raise PhysicalRegistrationRefusal("fe_reference.geometry_file", f"column {column!r} is missing.")
    node_ids = np.char.add(np.char.add(table["instance"].astype(str), ":"), table["node_label"].astype(str))
    coordinates = np.column_stack([table["x"], table["y"], table["z"]]).astype(float)
    identity = fe_geometry_identity(node_ids.tolist(), coordinates)
    pinned = manifest.fe_reference.geometry_identity
    if (identity["sha256"], identity["node_count"], identity["schema_version"]) != (
            pinned.sha256, pinned.node_count, pinned.schema_version):
        raise PhysicalRegistrationRefusal("fe_reference.geometry_identity",
                                          "the FE geometry file does not have the passport's FE geometry identity.")
    return FEGeometry(node_ids, coordinates, identity)


def load_experimental_geometry(manifest: SpecimenManifest, roots: Mapping[str, Path],
                               fixture_manifest: ExperimentFixtureManifest) -> tuple[ModalDataset, Any]:
    """The pinned experimental modal set named by the passport's fixture (size and SHA-256 verified)."""

    fixture_id = manifest.acquisition.fixture_id
    if fixture_id is None:
        raise PhysicalRegistrationRefusal("acquisition.fixture_id", "the passport names no experimental fixture.")
    fixture = fixture_manifest.fixture(fixture_id)
    path = resolve_external_file(fixture.experimental_source, roots)
    dataset = universal_reader.load_universal_modal_file(path, modal_set=fixture.modal_set.name)
    points = len(dataset.sorted_modes()[0].node_ids)
    if points != manifest.acquisition.grid.point_count:
        raise PhysicalRegistrationRefusal("acquisition.grid.point_count",
                                          f"the experimental grid has {points} points, the passport states "
                                          f"{manifest.acquisition.grid.point_count}.")
    return dataset, fixture


def _plain_ids(node_ids) -> list:
    return [value.item() if isinstance(value, np.generic) else value for value in np.asarray(node_ids, dtype=object)]


def _measured_contract(dataset: ModalDataset, measured_dofs: tuple[str, ...]) -> list:
    modes = dataset.sorted_modes()
    masks = experimental_measurement_masks(modes, modes[0].node_ids)
    reference = np.asarray(masks[0], dtype=bool)
    if any(not np.array_equal(np.asarray(mask, dtype=bool), reference) for mask in masks[1:]):
        raise PhysicalRegistrationRefusal("measured_dof_contract", "measured DOFs differ between modes.")
    measured = tuple(name for name, flag in zip(_COMPONENTS, reference.all(axis=0)) if flag)
    if measured != tuple(measured_dofs) or not np.array_equal(reference.all(axis=0), reference.any(axis=0)):
        raise PhysicalRegistrationRefusal("measured_dof_contract",
                                          f"the data measure {measured}; the fixture pins {tuple(measured_dofs)}.")
    return reference.tolist()


def _scale_vector(manifest: SpecimenManifest, experimental_coordinates: np.ndarray) -> tuple[np.ndarray, dict]:
    calibration = manifest.geometry_calibration.calibration
    rotation = manifest.geometry_calibration.orientation.rotation
    swapped = [int(np.argmax(np.abs(rotation[:, axis]))) for axis in (0, 1)] == [1, 0]
    options = [(np.asarray(s, float), d) for s, d in scale_candidates(calibration, experimental_coordinates)]
    # Only a camera-grid calibration offers a swapped and an unswapped scale; the documented
    # orientation (never modal agreement) picks between them.  Metric modes give one scale.
    matching = options if len(options) == 1 else [
        (s, d) for s, d in options if bool(d.get("axes_swapped", False)) == swapped]
    if len(matching) != 1:
        raise PhysicalRegistrationRefusal("geometry_calibration.coordinate_calibration",
                                          "the physical calibration does not give one scale for the documented "
                                          "orientation.")
    return matching[0]


def _bbox(points: np.ndarray, with_span: bool = True) -> dict:
    box = {"minimum": points.min(axis=0).tolist(), "maximum": points.max(axis=0).tolist()}
    if with_span:
        box["span"] = np.ptp(points, axis=0).tolist()
    return box


def _map_to_surface(fe: FEGeometry, surface_indices: np.ndarray, rotation: np.ndarray, scales: np.ndarray,
                    translation: np.ndarray, experimental: np.ndarray):
    """Nearest measured-surface FE node for each experimental point under a fixed transform."""

    surface = fe.coordinates[surface_indices]
    tree = cKDTree(surface)
    in_fe = ((experimental - translation) / scales) @ rotation.T
    count = min(8, len(surface))
    _, nearby = tree.query(in_fe, k=count)
    nearby = np.asarray(nearby, dtype=int).reshape(len(experimental), -1)
    # Same exact-metric refinement as the comparator: residuals in raw experimental units.
    candidates = (surface[nearby] @ rotation) * scales + translation
    residual = np.linalg.norm(candidates - experimental[:, np.newaxis, :], axis=2)
    choice = nearby[np.arange(len(nearby)), np.argmin(residual, axis=1)]
    mapped = surface_indices[choice]
    distances = np.linalg.norm((fe.coordinates[mapped] @ rotation) * scales + translation - experimental, axis=1)
    physical = np.linalg.norm(((fe.coordinates[mapped] @ rotation) * scales + translation - experimental) / scales,
                              axis=1)
    return mapped, distances, physical


def _corner_translation(manifest, fe, surface_indices, rotation, scales, dataset) -> tuple[np.ndarray, dict]:
    corner = manifest.geometry_calibration.corner_a
    reference = dataset.sorted_modes()[0]
    lookup = {int(value): index for index, value in enumerate(_plain_ids(reference.node_ids))}
    for node in (corner.unv_node, corner.x_axis_towards_unv_node):
        if node not in lookup:
            raise PhysicalRegistrationRefusal("geometry_calibration.corner_A", f"UNV node {node} is not on the grid.")
    a = reference.coordinates[lookup[corner.unv_node]]
    b = reference.coordinates[lookup[corner.x_axis_towards_unv_node]]
    unit = manifest.geometry_calibration.calibration.abaqus_unit
    surface_z = float(fe.coordinates[surface_indices, 2].mean())
    fe_corner = np.array([millimetres_to_model_units(corner.fe_xy_mm[0], unit),
                          millimetres_to_model_units(corner.fe_xy_mm[1], unit), surface_z])
    translation = a - (fe_corner @ rotation) * scales
    direction = ((b - a) / scales) @ rotation.T
    angle = math.degrees(math.atan2(direction[1], direction[0]))
    if abs(angle) >= 45.0:
        raise PhysicalRegistrationRefusal(
            "geometry_calibration.orientation",
            f"the corner-A x-axis marker points {angle:.1f} deg from FE +X; it contradicts the documented axes.")
    return translation, {"corner_A_marker_angle_deg": angle}


def _edge_translation(manifest, fe, surface_indices, rotation, scales, dataset) -> tuple[np.ndarray, dict]:
    offsets = manifest.geometry_calibration.panel_edges
    experimental = dataset.sorted_modes()[0].coordinates
    in_fe = (experimental / scales) @ rotation.T
    unit = manifest.geometry_calibration.calibration.abaqus_unit
    surface = fe.coordinates[surface_indices]
    target = np.array([surface[:, 0].min() + millimetres_to_model_units(offsets.x_mm, unit),
                       surface[:, 1].min() + millimetres_to_model_units(offsets.y_mm, unit),
                       float(surface[:, 2].mean())])
    shift = target - np.array([in_fe[:, 0].min(), in_fe[:, 1].min(), float(in_fe[:, 2].mean())])
    return -(shift @ rotation) * scales, {}


def _source_identity(manifest: SpecimenManifest, fixture, repo_root: Path) -> tuple[dict, str]:
    source = fixture.experimental_source
    legacy = manifest.geometry_calibration.legacy_registration
    if legacy is None:
        return ({"path": f"{source.location.store}:{source.location.relative_path}", "size": source.size_bytes,
                 "mtime_ns": None, "sha256": source.sha256}, "content")
    with open(Path(repo_root) / legacy.path, encoding="utf-8") as handle:
        accepted = FrozenRegistration.from_dict(json.load(handle))  # verifies the content hash
    if accepted.registration_hash != legacy.registration_hash:
        raise PhysicalRegistrationRefusal("geometry_calibration.legacy_registration",
                                          "the referenced accepted registration has a different hash.")
    identity = dict(accepted.experimental_source_identity)
    if identity.get("sha256") != source.sha256 or identity.get("size") != source.size_bytes:
        raise PhysicalRegistrationRefusal("geometry_calibration.legacy_registration",
                                          "the accepted registration was made for different experimental content.")
    return identity, "legacy_accepted_registration"


def build_physical_registration(
    manifest: SpecimenManifest,
    *,
    roots: Mapping[str, Path] | None = None,
    fixture_manifest: ExperimentFixtureManifest | None = None,
    repo_root: Path = REPO_ROOT,
    fe_geometry: FEGeometry | None = None,
    experimental: tuple[ModalDataset, Any] | None = None,
) -> PhysicalRegistrationResult:
    """Freeze the registration defined by the passport's physical calibration."""

    roots = fixture_roots_from_environment() if roots is None else roots
    fixture_manifest = load_experiment_fixture_manifest(FIXTURE_MANIFEST_PATH) if fixture_manifest is None else fixture_manifest
    fe = load_fe_geometry(manifest, roots) if fe_geometry is None else fe_geometry
    dataset, fixture = load_experimental_geometry(manifest, roots, fixture_manifest) if experimental is None else experimental
    if fe.identity["sha256"] != manifest.fe_reference.geometry_identity.sha256:
        raise PhysicalRegistrationRefusal("fe_reference.geometry_identity", "FE geometry identity differs.")
    if fixture.fe.geometry_identity.sha256 != manifest.fe_reference.geometry_identity.sha256:
        raise PhysicalRegistrationRefusal("fe_reference.geometry_identity",
                                          "the passport's FE geometry differs from the fixture's FE identity.")

    calibration = manifest.geometry_calibration
    reference = dataset.sorted_modes()[0]
    experimental_coordinates = np.asarray(reference.coordinates, dtype=float)
    surface = calibration.measured_surface
    surface_ids = fe.surface_node_ids(surface.fe_instance, surface.side, calibration.calibration.abaqus_unit)
    holder = ModeShape(0, 1.0, fe.node_ids.astype(object), fe.coordinates, np.zeros((len(fe.node_ids), 3)))
    surface_indices, subset = _resolve_fe_mapping_node_ids(holder, surface_ids)
    rotation = calibration.orientation.rotation
    calibration_state = calibration.calibration.to_dict()

    if calibration.mode == DOCUMENTED_CENTERED:
        candidates = geometry_alignment_candidates(
            fe.coordinates, experimental_coordinates, geometry_calibration=calibration.calibration,
            fe_node_indices=surface_indices, fe_mapping_node_subset=subset)
        documented, keys = [], set()
        for candidate in candidates:
            key = _geometry_equivalence_key(candidate)
            if np.array_equal(candidate.rotation, rotation) and key not in keys:
                keys.add(key)
                documented.append(candidate)
        if len(documented) != 1:
            raise PhysicalRegistrationRefusal(
                "geometry_calibration.orientation",
                f"{len(documented)} geometrically plausible placements have the documented rotation; exactly one "
                "is required (orientation is never chosen by modal agreement).")
        geometry = documented[0]
        summary = _candidate_summary(geometry)
        mapped, distances, physical = geometry.experimental_to_abaqus, geometry.distances, geometry.physical_distances
        scales, translation = geometry.coordinate_scales, geometry.translation
        metrics = {
            "orientation_source": "user_confirmed",
            "normalized_rms_distance": geometry.normalized_rms_distance,
            "matched_fraction": geometry.matched_fraction,
            "coordinate_scale": geometry.coordinate_scale,
            "evaluated_geometry_candidate_count": len(candidates),
            "geometry_calibration": dict(geometry.calibration_details),
        }
        candidate_id = summary["candidate_id"]
    else:
        scales, details = _scale_vector(manifest, experimental_coordinates)
        locate = _corner_translation if calibration.mode == CORNER_COORDINATES else _edge_translation
        translation, extra = locate(manifest, fe, surface_indices, rotation, scales, dataset)
        mapped, distances, physical = _map_to_surface(fe, surface_indices, rotation, scales, translation,
                                                      experimental_coordinates)
        span = max(float(np.linalg.norm(np.ptp(experimental_coordinates, axis=0))), 1.0e-30)
        determinant = float(np.linalg.det(rotation))
        summary = {
            "rotation": rotation.tolist(), "translation": np.asarray(translation).tolist(),
            "coordinate_scales": np.asarray(scales).tolist(),
            "normalized_rms_distance": float(np.sqrt(np.mean(distances ** 2)) / span),
            "matched_fraction": float(np.mean(distances <= 0.03 * span)),
            "determinant": determinant, "mirrored": determinant < 0.0,
            "axis_permutation": np.argmax(np.abs(rotation), axis=0).astype(int).tolist(),
            "calibration": dict(details), "fe_mapping_node_subset": dict(subset),
        }
        candidate_id = geometry_candidate_id(summary)
        metrics = {
            "orientation_source": "corner_A_marker" if calibration.mode == CORNER_COORDINATES else "panel_edges",
            "calibration_mode": calibration.mode,
            "normalized_rms_distance": summary["normalized_rms_distance"],
            "matched_fraction": summary["matched_fraction"],
            "coordinate_scale": float(np.sqrt(scales[0] * scales[1])),
            "geometry_calibration": dict(details),
            **extra,
        }

    transformed = (fe.coordinates @ rotation) * scales + translation
    determinant = float(np.linalg.det(rotation))
    permutation = np.argmax(np.abs(rotation), axis=0).astype(int).tolist()
    metrics.update({
        "mapping_rms": float(np.sqrt(np.mean(np.asarray(distances) ** 2))),
        "mapping_max_residual": float(np.max(distances)),
        "mapping_rms_in_abaqus_units": float(np.sqrt(np.mean(np.asarray(physical) ** 2))),
        "mapping_max_residual_in_abaqus_units": float(np.max(physical)),
        "raw_experimental_bbox": _bbox(experimental_coordinates),
        "mapped_fe_bbox": _bbox(fe.coordinates[np.asarray(mapped, dtype=int)]),
        "transformed_full_fe_bbox_in_experimental_coordinates": _bbox(transformed, with_span=False),
        "fe_mapping_node_subset": dict(subset),
        "determinant": determinant, "mirrored": determinant < 0.0, "axis_permutation": permutation,
        "planar_axes_swapped": permutation[:2] == [1, 0],
        "unique_mapped_abaqus_nodes": int(len(np.unique(mapped))),
        "experimental_point_count": int(len(mapped)),
    })
    source_identity, basis = _source_identity(manifest, fixture, repo_root)
    registration = FrozenRegistration.create(
        experimental_source_identity=source_identity,
        experimental_modal_set_identity=dataset.metadata.get("modal_set_key"),
        fe_geometry_identity=dict(fe.identity),
        calibration=calibration_state,
        calibration_fingerprint=calibration_fingerprint(calibration_state),
        orientation_candidate_id=candidate_id,
        rotation=np.asarray(rotation, float),
        translation=np.asarray(translation, float),
        coordinate_scales=np.asarray(scales, float),
        experimental_node_ids=_plain_ids(reference.node_ids),
        mapped_fe_node_ids=[str(value) for value in fe.node_ids[np.asarray(mapped, dtype=int)]],
        measured_dof_contract=_measured_contract(dataset, fixture.modal_set.measured_dofs),
        registration_metrics=metrics,
    )
    return PhysicalRegistrationResult(
        registration=registration,
        calibration_mode=calibration.mode,
        registration_basis_status=calibration.registration_basis_status,
        uncertainty_availability=calibration.uncertainty_availability,
        missing_physical_evidence=calibration.missing_physical_evidence,
        missing_uncertainty=calibration.missing_uncertainty,
        orientation_reference=calibration.orientation.reference,
        physical_specimen_id=None if manifest.physical_specimen_id is None else str(manifest.physical_specimen_id),
        manifest_hash=manifest.manifest_hash,
        source_identity_basis=basis,
        surface_node_ids=tuple(surface_ids),
    )
