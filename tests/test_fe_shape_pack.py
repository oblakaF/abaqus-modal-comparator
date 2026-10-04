"""Validated FE shape packs (M4.2 integration): pinned records, deterministic content hash, refusals."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.experiment_fixture import fixture_roots_from_environment, load_experiment_fixture_manifest
from domain.specimen_manifest import load_specimen_manifest
from services.fe_shape_pack import (
    PACK_ARRAYS,
    ShapePackError,
    load_shape_pack,
    load_shape_pack_file,
    load_shape_pack_record,
    node_set_sha256,
    parse_shape_pack_record,
    shape_pack_content_sha256,
)


SHAPES = ROOT / "docs" / "auto_id" / "fe_shapes"
FIXTURES = ROOT / "docs" / "auto_id" / "fixtures" / "real_experiment_fixtures.json"
ANCHORS = ROOT / "docs" / "auto_id" / "forward_models" / "accepted_forward_jobs.json"
JOBS = {"SP02_f3e592281bebce66": ("SP02", "BASELINE"), "SP13_a46d08b52995e078": ("SP13", "BASELINE"),
        "SP13_a9df66283a168786": ("SP13", "E_MINUS"), "SP13_0e861d03c333bb0b": ("SP13", "E_PLUS"),
        "SP13_0328066b74b6fd78": ("SP13", "G_MINUS"), "SP13_4c0f189b9727feaf": ("SP13", "G_PLUS")}
GENERATED = "0123456789abcdef" + "0" * 48
JOB = f"SYN_{GENERATED[:16]}"


def synthetic_arrays():
    node_ids = np.array(sorted(f"TOP:{k}" for k in range(1, 7)))
    rng = np.random.default_rng(5)
    return {"node_ids": node_ids, "coordinates": rng.normal(size=(6, 3)),
            "mode_numbers": np.array([7, 8], dtype=np.int32), "frequencies_hz": np.array([22.5, 72.7]),
            "displacements": rng.normal(size=(2, 6, 3)).astype(np.float32)}


def synthetic_record(arrays, file_bytes=b"", **changes):
    record = {
        "schema": "auto-id/fe-shape-pack-record/v1", "job_name": JOB, "specimen": "SYN", "state": "BASELINE",
        "generated_inp_sha256": GENERATED,
        "odb": {"role": "odb", "file_name": f"{JOB}.odb", "sha256": "1" * 64, "size_bytes": 10,
                "location": {"store": "synthetic", "relative_path": f"runs/{JOB}.odb"}},
        "pack": {"role": "pack", "file_name": f"{JOB}.npz", "sha256": "2" * 64, "size_bytes": max(len(file_bytes), 1),
                 "location": {"store": "synthetic", "relative_path": f"fe_shapes/{JOB}.npz"}},
        "content_sha256": shape_pack_content_sha256(arrays),
        "node_set": {"definition": "synthetic", "node_count": len(arrays["node_ids"]),
                     "sha256": node_set_sha256(arrays["node_ids"])},
        "fe_geometry_sha256": "3" * 64, "mode_numbers": [7, 8], "frequencies_hz": [22.5, 72.7],
        "extraction": {}, "validation": {"V1_pass": True, "V8_pass": True},
        "provenance_record": {"role": "provenance", "file_name": f"{JOB}.provenance.json", "sha256": "4" * 64,
                              "size_bytes": 1, "location": {"store": "synthetic",
                                                            "relative_path": f"fe_shapes/{JOB}.provenance.json"}},
    }
    record.update(changes)
    return record


class ContentHashTests(unittest.TestCase):
    def test_hash_is_layout_independent_and_content_sensitive(self):
        arrays = synthetic_arrays()
        base = shape_pack_content_sha256(arrays)
        with tempfile.TemporaryDirectory() as directory:
            for compressed in (False, True):
                path = Path(directory) / f"p{compressed}.npz"
                (np.savez_compressed if compressed else np.savez)(path, **arrays)
                with np.load(path, allow_pickle=False) as loaded:
                    self.assertEqual(shape_pack_content_sha256({k: loaded[k] for k in PACK_ARRAYS}), base)
        changed = copy.deepcopy(arrays)
        changed["displacements"][0, 0, 2] += np.float32(1e-6)
        self.assertNotEqual(shape_pack_content_sha256(changed), base)
        as64 = dict(arrays, displacements=arrays["displacements"].astype(np.float64))
        self.assertNotEqual(shape_pack_content_sha256(as64), base)  # dtype is part of the identity

    def test_node_set_hash_is_the_registration_subset_fingerprint(self):
        import hashlib

        ids = ["TOP:3", "TOP:1", "TOP:2"]
        self.assertEqual(node_set_sha256(ids), hashlib.sha256("TOP:1\nTOP:2\nTOP:3".encode()).hexdigest())


class LoaderTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.arrays = synthetic_arrays()
        self.path = Path(self._directory.name) / f"{JOB}.npz"
        np.savez(self.path, **self.arrays)

    def tearDown(self):
        self._directory.cleanup()

    def load(self, arrays=None, **changes):
        if arrays is not None:
            np.savez(self.path, **arrays)
        return load_shape_pack_file(self.path, parse_shape_pack_record(synthetic_record(self.arrays, **changes)))

    def test_valid_pack(self):
        pack = self.load()
        self.assertEqual(pack.mode_numbers, (7, 8))
        self.assertEqual(pack.displacements.shape, (2, 6, 3))
        np.testing.assert_array_equal(pack.rows(["TOP:2", "TOP:1"]), [1, 0])
        with self.assertRaises(ShapePackError):
            pack.rows(["TOP:99"])
        with self.assertRaises(ShapePackError):
            pack.mode_index(30)

    def test_tampered_content_is_refused(self):
        tampered = copy.deepcopy(self.arrays)
        tampered["displacements"][1, 2, 0] = 9.0
        with self.assertRaises(ShapePackError):
            self.load(tampered)

    def test_record_disagreement_is_refused(self):
        for changes in ({"frequencies_hz": [22.5, 72.8]}, {"mode_numbers": [7, 9]},
                        {"node_set": {"definition": "x", "node_count": 6, "sha256": "5" * 64}},
                        {"content_sha256": "6" * 64}):
            with self.subTest(changes=list(changes)), self.assertRaises(ShapePackError):
                self.load(**changes)

    def test_malformed_records_are_refused(self):
        for changes in ({"validation": {"V1_pass": True, "V6a_pass": False}}, {"validation": {}},
                        {"job_name": "SYN_ffffffffffffffff"}, {"schema": "auto-id/fe-shape-pack-record/v0"},
                        {"frequencies_hz": [22.5]}, {"generated_inp_sha256": "X"}):
            with self.subTest(changes=list(changes)), self.assertRaises(ShapePackError):
                parse_shape_pack_record(synthetic_record(self.arrays, **changes))
        record = synthetic_record(self.arrays)
        record["extra"] = 1
        with self.assertRaises(ShapePackError):
            parse_shape_pack_record(record)
        with self.assertRaises(ShapePackError):  # missing array
            np.savez(self.path, **{k: v for k, v in self.arrays.items() if k != "coordinates"})
            load_shape_pack_file(self.path, parse_shape_pack_record(synthetic_record(self.arrays)))


class PinnedRecordTests(unittest.TestCase):
    """The six gate packs: records bind to M0–M3 identities (no store needed)."""

    def test_records(self):
        fixtures = load_experiment_fixture_manifest(FIXTURES)
        anchors = json.loads(ANCHORS.read_text(encoding="utf-8"))["candidates"]
        names = {"BASELINE": "CARBON-4C BASELINE", "E_MINUS": "CARBON-5A E_MINUS", "E_PLUS": "CARBON-5A E_PLUS",
                 "G_MINUS": "CARBON-5A G_MINUS", "G_PLUS": "CARBON-5A G_PLUS"}
        self.assertEqual(sorted(p.name for p in SHAPES.glob("*.shape-pack.json")),
                         sorted(f"{job}.shape-pack.json" for job in JOBS))
        for job, (specimen, state) in JOBS.items():
            with self.subTest(job=job):
                record = load_shape_pack_record(SHAPES / f"{job}.shape-pack.json")
                anchor = next(c for c in anchors if c["name"] == names[state])["jobs"][specimen]
                passport = load_specimen_manifest(ROOT / f"docs/auto_id/specimens/{specimen}.specimen.json")
                registration = json.loads((ROOT / f"docs/registrations/{specimen}_frozen_registration.json")
                                          .read_text(encoding="utf-8"))
                self.assertEqual((record.specimen, record.state), (specimen, state))
                self.assertEqual(record.generated_inp_sha256, anchor["generated_inp_sha256"])
                self.assertEqual(record.fe_geometry_sha256, passport.fe_reference.geometry_identity.sha256)
                subset = registration["registration_metrics"]["fe_mapping_node_subset"]
                self.assertEqual((record.node_set_count, record.node_set_sha256), (subset["node_count"], subset["sha256"]))
                self.assertEqual(record.mode_numbers, tuple(range(7, 31)))
                self.assertEqual(record.pack.location.store, "carbon-project-archive")
                if state == "BASELINE":
                    fixture = next(f for f in fixtures.fixtures if f.fe.odb_reference.file_name == f"{job}.odb")
                    self.assertEqual(record.odb.sha256, fixture.fe.odb_reference.sha256)
                    self.assertTrue(record.validation["V6a_pass"] and record.validation["V6b_pass"])


class StoreTests(unittest.TestCase):
    def test_all_pinned_packs_load(self):
        roots = fixture_roots_from_environment()
        if "carbon-project-archive" not in roots:
            self.skipTest("data store 'carbon-project-archive' not configured")
        for job in JOBS:
            with self.subTest(job=job):
                pack = load_shape_pack(load_shape_pack_record(SHAPES / f"{job}.shape-pack.json"), roots)
                self.assertEqual(pack.displacements.dtype, np.float32)
                self.assertEqual(pack.displacements.shape[0], 24)


if __name__ == "__main__":
    unittest.main()
