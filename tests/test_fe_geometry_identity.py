from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import struct
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modal_core import ModalDataset, ModeShape
from scientific_state import (
    FE_GEOMETRY_IDENTITY_SCHEMA,
    fe_geometry_identity,
    modal_dataset_geometry_identity,
)


NODE_IDS = ["PLATE-1:1", "PLATE-1:2", "PLATE-1:3", "CORE-1:1"]
COORDINATES = [
    [0.0, 0.0, 0.0],
    [10.0, 0.0, 0.0],
    [10.0, 5.0, 0.425],
    [0.0, 0.0, 1.0],
]


def make_mode(number, frequency_hz, node_ids=NODE_IDS, coordinates=COORDINATES, seed=0, mask=None):
    rng = np.random.default_rng(seed)
    count = len(node_ids)
    mode = ModeShape(
        number=number,
        frequency_hz=frequency_hz,
        node_ids=np.asarray(node_ids, dtype=object),
        coordinates=np.asarray(coordinates, dtype=float),
        vectors=rng.normal(size=(count, 3)).astype(complex),
        metadata={"frame_index": number, "step_name": "Frequency"},
    )
    mode.measured_dofs = (
        np.ones((count, 3), dtype=bool) if mask is None else np.asarray(mask, dtype=bool)
    )
    return mode


def make_dataset(frequencies=(22.49, 41.3), seeds=(0, 1), **mode_kwargs):
    modes = [
        make_mode(index + 7, frequency, seed=seed, **mode_kwargs)
        for index, (frequency, seed) in enumerate(zip(frequencies, seeds))
    ]
    return ModalDataset(
        source_name="Abaqus ODB",
        source_path=Path("C:/temp/SP13_modal.odb"),
        modes=modes,
        metadata={"step_name": "Frequency", "format_version": 2},
        history=[{"event": "extracted"}],
    )


def identity(dataset):
    return modal_dataset_geometry_identity(dataset)


class FeGeometryIdentityTests(unittest.TestCase):
    def test_return_shape(self):
        result = identity(make_dataset())
        self.assertEqual(
            set(result),
            {"schema_version", "node_count", "instances", "dof_components", "dof_count", "sha256"},
        )
        self.assertEqual(result["schema_version"], FE_GEOMETRY_IDENTITY_SCHEMA)
        self.assertEqual(result["node_count"], 4)
        self.assertEqual(result["instances"], ["CORE-1", "PLATE-1"])
        self.assertEqual(result["dof_components"], ["U1", "U2", "U3"])
        self.assertEqual(result["dof_count"], 12)
        self.assertRegex(result["sha256"], r"^[0-9a-f]{64}$")

    # A
    def test_different_frequencies_keep_identity(self):
        self.assertEqual(
            identity(make_dataset(frequencies=(22.49, 41.3))),
            identity(make_dataset(frequencies=(25.0, 47.9))),
        )

    # B
    def test_different_mode_vectors_keep_identity(self):
        self.assertEqual(
            identity(make_dataset(seeds=(0, 1))),
            identity(make_dataset(seeds=(5, 9))),
        )

    # C
    def test_input_node_order_does_not_matter(self):
        order = [3, 1, 0, 2]
        shuffled = make_dataset(
            node_ids=[NODE_IDS[i] for i in order],
            coordinates=[COORDINATES[i] for i in order],
        )
        self.assertEqual(identity(make_dataset()), identity(shuffled))

    # D
    def test_moving_one_node_changes_identity(self):
        moved = copy.deepcopy(COORDINATES)
        moved[2][1] += 1e-9
        self.assertNotEqual(
            identity(make_dataset())["sha256"],
            identity(make_dataset(coordinates=moved))["sha256"],
        )

    # E
    def test_removing_or_adding_a_node_changes_identity(self):
        base = identity(make_dataset())
        removed = identity(make_dataset(node_ids=NODE_IDS[:-1], coordinates=COORDINATES[:-1]))
        added = identity(
            make_dataset(
                node_ids=NODE_IDS + ["PLATE-1:4"],
                coordinates=COORDINATES + [[0.0, 5.0, 0.425]],
            )
        )
        self.assertEqual(removed["node_count"], 3)
        self.assertEqual(added["node_count"], 5)
        self.assertEqual(len({base["sha256"], removed["sha256"], added["sha256"]}), 3)

    # F
    def test_same_labels_in_a_different_instance_change_identity(self):
        renamed = ["PLATE-2:1", "PLATE-2:2", "PLATE-2:3", "CORE-1:1"]
        self.assertNotEqual(
            identity(make_dataset())["sha256"],
            identity(make_dataset(node_ids=renamed))["sha256"],
        )

    def test_coordinates_stay_bound_to_their_instance(self):
        first = fe_geometry_identity(
            ["AB:1", "A:1"], [[0, 0, 0], [1, 0, 0]], np.ones((2, 3), dtype=bool)
        )
        second = fe_geometry_identity(
            ["A:1", "AB:1"], [[0, 0, 0], [1, 0, 0]], np.ones((2, 3), dtype=bool)
        )
        self.assertNotEqual(first["sha256"], second["sha256"])

    # G
    def test_changing_dof_map_changes_identity(self):
        mask = np.ones((4, 3), dtype=bool)
        mask[1, 2] = False
        changed = identity(make_dataset(mask=mask))
        self.assertEqual(changed["dof_count"], 11)
        self.assertNotEqual(identity(make_dataset())["sha256"], changed["sha256"])

    # H
    def test_repeated_calls_are_identical_and_match_the_documented_encoding(self):
        dataset = make_dataset()
        self.assertEqual(identity(dataset), identity(dataset))

        # Independent re-implementation of the documented byte layout.
        instances = ["CORE-1", "PLATE-1"]
        payload = bytearray(b"fe-geometry-identity/1\nU1,U2,U3\n")
        payload += struct.pack(">I", len(instances))
        for name in instances:
            encoded = name.encode("utf-8")
            payload += struct.pack(">I", len(encoded)) + encoded
        payload += struct.pack(">Q", 4)
        rows = [
            (0, 1, (0.0, 0.0, 1.0)),
            (1, 1, (0.0, 0.0, 0.0)),
            (1, 2, (10.0, 0.0, 0.0)),
            (1, 3, (10.0, 5.0, 0.425)),
        ]
        for instance_index, label, xyz in rows:
            payload += struct.pack(">Iq3dB", instance_index, label, *xyz, 0b111)
        self.assertEqual(identity(dataset)["sha256"], hashlib.sha256(bytes(payload)).hexdigest())

    def test_negative_zero_coordinate_is_canonicalized(self):
        negative = copy.deepcopy(COORDINATES)
        negative[0] = [-0.0, -0.0, -0.0]
        self.assertEqual(identity(make_dataset()), identity(make_dataset(coordinates=negative)))

    # I
    def test_non_geometric_metadata_does_not_affect_identity(self):
        base = identity(make_dataset())
        dataset = make_dataset()
        dataset.source_name = "Other source"
        dataset.source_path = Path("D:/elsewhere/other.odb")
        dataset.metadata.update(
            {
                "step_name": "Changed",
                "odb_path": "D:/elsewhere/other.odb",
                "D11": 1.0e5,
                "D12": 2.0e4,
                "D66": 3.0e4,
                "Ex": 70e9,
                "Ey": 10e9,
                "Gxy": 5e9,
                "basis_km_hash": "f" * 64,
                "optimizer": {"method": "hybrid"},
                "model_template": "SP13_mesh_local_v1",
            }
        )
        dataset.history.append({"event": "inverse iteration"})
        for mode in dataset.modes:
            mode.metadata.update({"Ex": 1.0, "stiffness": [[1.0]]})
            mode.damping_ratio = 0.02
            mode.modal_mass = 3.5
            mode.number += 100
        self.assertEqual(identity(dataset), base)


class FeGeometryIdentityValidationTests(unittest.TestCase):
    def test_missing_dof_map_is_rejected_not_inferred(self):
        dataset = make_dataset()
        del dataset.modes[0].measured_dofs
        with self.assertRaisesRegex(ValueError, "DOF map"):
            identity(dataset)

    def test_modes_with_different_geometry_are_rejected(self):
        dataset = make_dataset()
        moved = copy.deepcopy(COORDINATES)
        moved[0][0] = 99.0
        dataset.modes[1] = make_mode(8, 41.3, coordinates=moved)
        with self.assertRaisesRegex(ValueError, "same FE geometry"):
            identity(dataset)

    def test_modes_with_reordered_but_equal_geometry_are_accepted(self):
        dataset = make_dataset()
        order = [2, 0, 3, 1]
        dataset.modes[1] = make_mode(
            8,
            41.3,
            node_ids=[NODE_IDS[i] for i in order],
            coordinates=[COORDINATES[i] for i in order],
        )
        self.assertEqual(identity(dataset), identity(make_dataset()))

    def test_invalid_inputs_are_rejected(self):
        ones = np.ones((2, 3), dtype=bool)
        cases = {
            "duplicate": (["P-1:1", "P-1:1"], [[0, 0, 0], [1, 0, 0]], ones),
            "no instance": (["1", "P-1:2"], [[0, 0, 0], [1, 0, 0]], ones),
            "empty instance": ([":1", "P-1:2"], [[0, 0, 0], [1, 0, 0]], ones),
            "non-integer label": (["P-1:a", "P-1:2"], [[0, 0, 0], [1, 0, 0]], ones),
            "non-finite": (["P-1:1", "P-1:2"], [[np.nan, 0, 0], [1, 0, 0]], ones),
            "coordinate shape": (["P-1:1", "P-1:2"], [[0, 0], [1, 0]], ones),
            "mask shape": (["P-1:1", "P-1:2"], [[0, 0, 0], [1, 0, 0]], np.ones((2, 2), dtype=bool)),
        }
        for name, (node_ids, coordinates, mask) in cases.items():
            with self.subTest(name):
                with self.assertRaises(ValueError):
                    fe_geometry_identity(node_ids, coordinates, mask)
        with self.assertRaises(TypeError):
            fe_geometry_identity(["P-1:1"], [[0, 0, 0]], np.ones((1, 3), dtype=int))
        with self.assertRaises(ValueError):
            modal_dataset_geometry_identity(
                ModalDataset(source_name="empty", source_path=Path("x"), modes=[])
            )


if __name__ == "__main__":
    unittest.main()
