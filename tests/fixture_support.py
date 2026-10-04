"""Shared synthetic experiment-fixture workspace for fixture regression / production-input tests.

Builds, in a temporary directory, a tiny external store file, a hash-sealed FrozenRegistration
and a manifest record derived from the first real record, so refusal paths run without large data.
Not a test module (no TestCase here); imported by test_*.py files.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from coordinate_calibration import CoordinateCalibration
from domain.experiment_fixture import parse_experiment_fixture_manifest
from domain.registration import FrozenRegistration
from modal_core import ModalDataset, ModeShape
from scientific_state import calibration_fingerprint


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "auto_id" / "fixtures" / "real_experiment_fixtures.json"
CALIBRATION = CoordinateCalibration(
    mode="calibrated_physical", abaqus_unit="mm", experimental_unit="m"
).to_dict()
NODE_IDS = [101, 102, 103]
U3_ONLY = [[False, False, True]] * len(NODE_IDS)
# Per-mode labels as written by universal_reader for a dataset-55 modal set.
CURVE_FITTED_MODE_METADATA = {"dataset_type": 55, "mode_source": "curve-fitted modal dataset"}


def build_synthetic_fixture_workspace(base: Path) -> SimpleNamespace:
    repo_root = base / "repo"
    store_root = base / "store"
    payload = b"synthetic PolyMAX export"
    source_file = store_root / "SP-XX" / "synthetic.unv"
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes(payload)

    registration = FrozenRegistration.create(
        experimental_source_identity={
            "path": "synthetic.unv",
            "size": len(payload),
            "mtime_ns": 0,
            "sha256": hashlib.sha256(payload).hexdigest(),
        },
        experimental_modal_set_identity="set-a",
        fe_geometry_identity={
            "schema_version": "fe-geometry-identity/2",
            "node_count": 10,
            "sha256": "c" * 64,
        },
        calibration=dict(CALIBRATION),
        calibration_fingerprint=calibration_fingerprint(CALIBRATION),
        orientation_candidate_id="geometry-0123456789abcdef",
        rotation=np.eye(3),
        translation=np.zeros(3),
        coordinate_scales=np.full(3, 1e-3),
        experimental_node_ids=NODE_IDS,
        mapped_fe_node_ids=["TOP:1", "TOP:2", "TOP:3"],
        measured_dof_contract=U3_ONLY,
        registration_metrics={"matched_fraction": 1.0},
    )
    registration_path = repo_root / "docs" / "registrations" / "SYN_frozen_registration.json"
    registration_path.parent.mkdir(parents=True)
    registration_path.write_text(json.dumps(registration.to_dict()), encoding="utf-8")

    with open(MANIFEST_PATH, encoding="utf-8") as handle:
        record = copy.deepcopy(json.load(handle)["fixtures"][0])
    record["fixture_id"] = "SYN/set-a"
    record["experimental_source"].update(
        file_name="synthetic.unv",
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
        location={"store": "snadwich", "relative_path": "SP-XX/synthetic.unv"},
    )
    record["modal_set"].update(name="set-a", display_name="Set A", mode_count=2, measurement_point_count=3)
    record["registration"].update(
        path="docs/registrations/SYN_frozen_registration.json",
        registration_hash=registration.registration_hash,
        fe_geometry_sha256="c" * 64,
    )
    record["fe"]["geometry_identity"] = {"schema_version": "fe-geometry-identity/2", "sha256": "c" * 64, "node_count": 10}
    return SimpleNamespace(
        repo_root=repo_root,
        store_root=store_root,
        roots={"snadwich": store_root},
        payload=payload,
        source_file=source_file,
        registration=registration,
        record=record,
    )


def manifest_from_record(record: dict, **changes):
    """Parse a one-record manifest from a modified copy; ``a__b=value`` sets ``record[a][b]``."""
    record = copy.deepcopy(record)
    for path, value in changes.items():
        target = record
        *parents, key = path.split("__")
        for part in parents:
            target = target[part]
        target[key] = value
    return parse_experiment_fixture_manifest(
        {"schema_version": "experiment-fixture-manifest/1", "fixtures": [record]}
    )


def fixture_from_record(record: dict, **changes):
    return manifest_from_record(record, **changes).fixtures[0]


def synthetic_modal_dataset(path, modal_set, *, mode_source="curve-fitted dataset 55", z_only=True,
                            mode_metadata=None):
    modes = []
    for number in (1, 2):
        vectors = np.zeros((len(NODE_IDS), 3))
        vectors[:, 2] = [1.0, -0.5, 0.25]
        if not z_only:
            vectors[:, 0] = 0.3
        metadata = dict(CURVE_FITTED_MODE_METADATA if mode_metadata is None else mode_metadata)
        modes.append(ModeShape(number, 10.0 * number, np.array(NODE_IDS, dtype=object), np.zeros((3, 3)),
                               vectors, metadata=metadata))
    return ModalDataset(
        "synthetic",
        Path(path),
        modes,
        metadata={
            "mode_source": mode_source,
            "modal_set_key": modal_set,
            "available_modal_sets": [{"key": "set-a"}, {"key": "set-b"}],
        },
    )
