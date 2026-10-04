"""Shared synthetic passport / geometry builders for the M2 tests (not a test module)."""

from __future__ import annotations

import copy
from pathlib import Path

import numpy as np

from domain.experiment_fixture import parse_experiment_fixture_manifest
from domain.specimen_manifest import parse_specimen_manifest
from modal_core import ModalDataset, ModeShape
from scientific_state import fe_geometry_identity

from fixture_support import MANIFEST_PATH  # noqa: F401  (keeps the shared manifest path in one place)

import json


CALIBRATION = {"mode": "calibrated_physical", "abaqus_unit": "mm", "experimental_unit": "m",
               "provenance": "synthetic: PSV geometry exported in metres (METRIC_ABS)"}
PLATE_X, PLATE_Y, STEP = 100.0, 80.0, 2.0
TOP_Z = 2.0


def passport_dict(**overrides) -> dict:
    """A complete, valid sandwich passport; ``a__b=value`` sets a nested key."""
    data = {
        "schema": "auto-id/specimen/v1.1",
        "specimen_type": "sandwich",
        "family_id": "FAM-plain-0.45",
        "design_id": "DES-SYN",
        "physical_specimen_id": "PANEL-SYN-1",
        "test_run_id": "RUN-SYN-A",
        "plan_mm": {"Lx": 100.0, "Ly": 80.0, "sd": 0.5},
        "masses_g": {"panel": 410.0, "core": 178.6},
        "face_thickness_mm": {"top": [0.45, 0.46, 0.44, 0.45, 0.47, 0.45, 0.44, 0.46, 0.45],
                              "bottom": [0.45, 0.45, 0.46, 0.44, 0.45, 0.46, 0.45, 0.44, 0.45]},
        "core_height_mm": {"value": 1.96, "sd": 0.02},
        "materials": {"face": "CFRP_Face", "core": "PLA_Auxetic", "adhesive": "DP420"},
        "suspension_max_hz": {"value_hz": 20.0, "source": "measured suspension modes (rig log)"},
        "geometry_calibration": {
            "mode": "corner_coordinates_mm",
            "coordinate_calibration": dict(CALIBRATION),
            "measured_surface": {"fe_instance": "TOP", "side": "max_z", "label": "TOP exterior face"},
            "orientation": {"experimental_axes_in_fe": ["+X", "+Y", "+Z"], "reference": "corner_A_marker",
                            "source": "photograph with corner A marked"},
            "uncertainty": {"translation_mm": 1.0, "scale_rel": 0.005, "rotation_deg": 0.5},
            "corner_A": {"unv_node": 1, "fe_xy_mm": [10.0, 10.0], "x_axis_towards_unv_node": 2},
        },
        "fe_reference": {
            "model_name": "SYN_MODEL",
            "geometry_identity": {"schema_version": "fe-geometry-identity/2", "sha256": "0" * 64, "node_count": 1},
            "geometry_file": {"role": "FE node coordinates", "file_name": "geo.csv", "sha256": "1" * 64,
                              "size_bytes": 10, "location": {"store": "archive", "relative_path": "fe/geo.csv"}},
        },
        "acquisition": {"session": "S1", "grid": {"grid_id": "G-20", "point_count": 20}, "fixture_id": "SYN/set-a",
                        "protocol_id": "P-1", "remount_of": None},
        "identify": "default",
        "unavailable": {},
    }
    for path, value in overrides.items():
        target = data
        *parents, key = path.split("__")
        for part in parents:
            target = target[part]
        target[key] = value
    return data


def parse(**overrides):
    return parse_specimen_manifest(passport_dict(**overrides))


def calibration(unit: str = "mm") -> dict:
    """The synthetic coordinate calibration for an FE model whose length unit is ``unit``."""
    return {**CALIBRATION, "abaqus_unit": unit}


def synthetic_fe(unit: str = "mm"):
    """The same physical plate (dimensions in mm) expressed in the FE model length unit ``unit``."""
    from coordinate_calibration import millimetres_to_model_units
    from services.physical_registration import FEGeometry

    factor = millimetres_to_model_units(1.0, unit)
    xs = np.arange(0.0, PLATE_X + STEP / 2, STEP)
    ys = np.arange(0.0, PLATE_Y + STEP / 2, STEP)
    grid = np.array([(x, y) for x in xs for y in ys])
    ids, coords = [], []
    for instance, z in (("BOT", 0.0), ("CORE", 1.0), ("TOP", TOP_Z)):
        for label, (x, y) in enumerate(grid, start=1):
            ids.append(f"{instance}:{label}")
            coords.append((x, y, z))
    ids = np.array(ids)
    coords = np.array(coords, dtype=float) * factor
    return FEGeometry(ids, coords, fe_geometry_identity(ids.tolist(), coords))


def grid_points_mm(nx=5, ny=4, x0=10.0, y0=10.0, pitch=20.0) -> np.ndarray:
    return np.array([(x0 + pitch * i, y0 + pitch * j, TOP_Z) for j in range(ny) for i in range(nx)], dtype=float)


def experiment(rotation=np.eye(3), translation=(0.25, -0.1, -1.002), scale=1.0e-3, frequencies=(12.0, 31.5),
               fe_points=None, shapes=None) -> ModalDataset:
    """Experimental grid = (FE point @ R) * scale + t; node 1 is the grid's FE (x0, y0) corner, node 2 next along +x."""
    fe_points = grid_points_mm() if fe_points is None else fe_points
    coords = (fe_points @ np.asarray(rotation, float)) * scale + np.asarray(translation, float)
    node_ids = np.arange(1, len(coords) + 1).astype(object)
    modes = []
    for number, frequency in enumerate(frequencies, start=1):
        vectors = np.zeros((len(coords), 3), dtype=complex)
        if shapes is None:
            vectors[:, 2] = np.sin(number * np.pi * fe_points[:, 0] / PLATE_X) * np.cos(np.pi * fe_points[:, 1] / PLATE_Y)
        else:
            vectors[:, 2] = shapes(number, fe_points)
        modes.append(ModeShape(number, frequency, node_ids, coords, vectors,
                               metadata={"dataset_type": 55, "mode_source": "curve-fitted modal dataset"}))
    return ModalDataset("synthetic", Path("synthetic.unv"), modes, metadata={"modal_set_key": "set-a"})


def fixture_for(fe, points: int = 20):
    with open(MANIFEST_PATH, encoding="utf-8") as handle:
        record = copy.deepcopy(json.load(handle)["fixtures"][0])
    record["fixture_id"] = "SYN/set-a"
    record["modal_set"].update(name="set-a", mode_count=2, measurement_point_count=points)
    identity = {"schema_version": fe.identity["schema_version"], "sha256": fe.identity["sha256"],
                "node_count": fe.identity["node_count"]}
    record["fe"]["geometry_identity"] = identity
    record["registration"]["fe_geometry_sha256"] = fe.identity["sha256"]
    return parse_experiment_fixture_manifest(
        {"schema_version": "experiment-fixture-manifest/1", "fixtures": [record]}).fixtures[0]


def passport_for(fe, **overrides):
    return parse(**{"fe_reference__geometry_identity": {"schema_version": fe.identity["schema_version"],
                                                        "sha256": fe.identity["sha256"],
                                                        "node_count": fe.identity["node_count"]}, **overrides})
