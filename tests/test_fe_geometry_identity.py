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

from domain.registration import FrozenRegistration, RegistrationMismatchError
from modal_core import ModalDataset, ModeShape
from scientific_state import (
    FE_GEOMETRY_IDENTITY_SCHEMA,
    calibration_fingerprint,
    fe_geometry_identity,
    modal_dataset_geometry_identity,
)
from services.matrix_model_service import (
    AbaqusDof,
    GeneralizedEigenResult,
    StageAMatrixNodeMap,
)
from services.stage_a_identification_service import MatrixEigenmodeDatasetAdapter


NODE_IDS = ["PLATE-1:1", "PLATE-1:2", "PLATE-1:3", "CORE-1:1"]
COORDINATES = [
    [0.0, 0.0, 0.0],
    [10.0, 0.0, 0.0],
    [10.0, 5.0, 0.425],
    [0.0, 0.0, 1.0],
]
MISSING = object()


def make_mode(number, frequency_hz, node_ids=NODE_IDS, coordinates=COORDINATES, seed=0, mask=MISSING):
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
    if mask is MISSING:
        mode.measured_dofs = np.ones((count, 3), dtype=bool)  # ODB loader convention
    elif mask is not None:
        mode.measured_dofs = np.asarray(mask, dtype=bool)
    return mode


def make_dataset(frequencies=(22.49, 41.3), seeds=(0, 1), masks=None, **mode_kwargs):
    masks = masks or [MISSING] * len(frequencies)
    modes = [
        make_mode(index + 7, frequency, seed=seed, mask=mask, **mode_kwargs)
        for index, (frequency, seed, mask) in enumerate(zip(frequencies, seeds, masks))
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


class FeGeometryIdentityContractTests(unittest.TestCase):
    # I / J
    def test_return_shape_schema_and_component_namespace(self):
        result = identity(make_dataset())
        self.assertEqual(
            set(result), {"schema_version", "node_count", "instances", "dof_components", "sha256"}
        )
        self.assertEqual(FE_GEOMETRY_IDENTITY_SCHEMA, "fe-geometry-identity/2")
        self.assertEqual(result["schema_version"], "fe-geometry-identity/2")
        self.assertEqual(result["node_count"], 4)
        self.assertEqual(result["instances"], ["CORE-1", "PLATE-1"])
        self.assertEqual(result["dof_components"], ["U1", "U2", "U3"])
        self.assertNotIn("dof_count", result)
        self.assertRegex(result["sha256"], r"^[0-9a-f]{64}$")

    def test_core_api_takes_only_node_ids_and_coordinates(self):
        self.assertEqual(
            fe_geometry_identity(NODE_IDS, COORDINATES), identity(make_dataset())
        )
        with self.assertRaises(TypeError):
            fe_geometry_identity(NODE_IDS, COORDINATES, np.ones((4, 3), dtype=bool))

    # H (encoding) -- independent re-implementation of the documented layout
    def test_hash_matches_documented_binary_encoding(self):
        instances = ["CORE-1", "PLATE-1"]
        payload = bytearray(b"fe-geometry-identity/2\nU1,U2,U3\n")
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
            payload += struct.pack(">Iq3d", instance_index, label, *xyz)
        dataset = make_dataset()
        self.assertEqual(identity(dataset), identity(dataset))
        self.assertEqual(identity(dataset)["sha256"], hashlib.sha256(bytes(payload)).hexdigest())


class FeGeometryIdentityAvailabilityTests(unittest.TestCase):
    # A
    def test_odb_and_partial_availability_masks_share_identity(self):
        partial = np.zeros((4, 3), dtype=bool)
        partial[:, 2] = True
        partial[3, :] = False
        self.assertEqual(
            identity(make_dataset()),
            identity(make_dataset(masks=[partial, partial])),
        )

    # B
    def test_dataset_without_measured_dofs_gets_the_same_identity(self):
        self.assertEqual(identity(make_dataset()), identity(make_dataset(masks=[None, None])))

    # C
    def test_different_masks_between_modes_are_tolerated(self):
        first = np.ones((4, 3), dtype=bool)
        second = np.zeros((4, 3), dtype=bool)
        second[0, 0] = True
        self.assertEqual(
            identity(make_dataset(masks=[first, second])), identity(make_dataset())
        )

    # L -- key acceptance: matrix candidate vs ODB reference of the same mesh
    def test_matrix_candidate_shares_identity_with_odb_reference(self):
        reference_ids = ("PART-B:1", "PART-A:1", "PART-A:2")
        reference = make_dataset(
            frequencies=(10.0,),
            seeds=(0,),
            node_ids=reference_ids,
            coordinates=[[10.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 5.0, 0.0]],
        )
        dofs = (AbaqusDof(101, 1), AbaqusDof(101, 3), AbaqusDof(102, 3), AbaqusDof(103, 4))
        node_map = StageAMatrixNodeMap.from_mapping(
            {101: "PART-A:1", 102: "PART-B:1", 103: "PART-A:2"}
        )
        candidate = MatrixEigenmodeDatasetAdapter(reference, dofs, node_map=node_map)(
            GeneralizedEigenResult(
                eigenvalues=np.array([1.0, 4.0]),
                frequencies_hz=np.array([11.0, 22.0]),
                eigenvectors=np.arange(1.0, 9.0).reshape(4, 2),
                dofs=dofs,
                rigid_body_eigenvalues=np.array([]),
            )
        )
        for mode in candidate.modes:
            self.assertFalse(hasattr(mode, "measured_dofs"))
            self.assertFalse(bool(np.all(mode.metadata["fe_available_dofs"])))
        self.assertEqual(identity(candidate), identity(reference))


class FeGeometryIdentitySensitivityTests(unittest.TestCase):
    # D
    def test_moving_one_node_changes_identity(self):
        moved = copy.deepcopy(COORDINATES)
        moved[2][1] += 1e-9
        self.assertNotEqual(
            identity(make_dataset())["sha256"],
            identity(make_dataset(coordinates=moved))["sha256"],
        )

    # E
    def test_changed_instance_changes_identity(self):
        renamed = ["PLATE-2:1", "PLATE-2:2", "PLATE-2:3", "CORE-1:1"]
        self.assertNotEqual(
            identity(make_dataset())["sha256"],
            identity(make_dataset(node_ids=renamed))["sha256"],
        )
        swapped = fe_geometry_identity(["AB:1", "A:1"], [[0, 0, 0], [1, 0, 0]])
        original = fe_geometry_identity(["A:1", "AB:1"], [[0, 0, 0], [1, 0, 0]])
        self.assertNotEqual(swapped["sha256"], original["sha256"])

    # F
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

    # G
    def test_input_row_order_does_not_matter(self):
        order = [3, 1, 0, 2]
        shuffled = make_dataset(
            node_ids=[NODE_IDS[i] for i in order],
            coordinates=[COORDINATES[i] for i in order],
        )
        self.assertEqual(identity(make_dataset()), identity(shuffled))

    # H
    def test_frequencies_vectors_metadata_and_mode_order_do_not_matter(self):
        base = identity(make_dataset())
        changed = make_dataset(frequencies=(25.0, 47.9), seeds=(5, 9))
        changed.modes.reverse()
        changed.metadata.update({"D11": 1.0e5, "Ex": 7e10, "basis_km_hash": "f" * 64})
        for mode in changed.modes:
            mode.metadata["fe_available_dofs"] = np.zeros((4, 3), dtype=bool)
            mode.damping_ratio = 0.02
        self.assertEqual(identity(changed), base)

    def test_negative_zero_coordinate_is_canonicalized(self):
        negative = copy.deepcopy(COORDINATES)
        negative[0] = [-0.0, -0.0, -0.0]
        self.assertEqual(identity(make_dataset()), identity(make_dataset(coordinates=negative)))


class FeGeometryIdentityValidationTests(unittest.TestCase):
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
        cases = {
            "duplicate": (["P-1:1", "P-1:1"], [[0, 0, 0], [1, 0, 0]]),
            "no instance": (["1", "P-1:2"], [[0, 0, 0], [1, 0, 0]]),
            "empty instance": ([":1", "P-1:2"], [[0, 0, 0], [1, 0, 0]]),
            "non-integer label": (["P-1:a", "P-1:2"], [[0, 0, 0], [1, 0, 0]]),
            "non-finite": (["P-1:1", "P-1:2"], [[np.nan, 0, 0], [1, 0, 0]]),
            "coordinate shape": (["P-1:1", "P-1:2"], [[0, 0], [1, 0]]),
        }
        for name, (node_ids, coordinates) in cases.items():
            with self.subTest(name):
                with self.assertRaises(ValueError):
                    fe_geometry_identity(node_ids, coordinates)
        with self.assertRaises(ValueError):
            modal_dataset_geometry_identity(
                ModalDataset(source_name="empty", source_path=Path("x"), modes=[])
            )


class FeGeometryIdentityVersionCompatibilityTests(unittest.TestCase):
    def test_v1_registration_is_refused_against_v2_identity(self):
        v2 = identity(make_dataset())
        v1 = {**v2, "schema_version": "fe-geometry-identity/1", "dof_count": 12}
        source = {"path": "exp.unv", "size": 1, "mtime_ns": 1, "sha256": "a" * 64}
        calibration = {"mode": "manual", "manual_scale": 1.0}
        registration = FrozenRegistration.create(
            experimental_source_identity=source,
            experimental_modal_set_identity=None,
            fe_geometry_identity=v1,
            calibration=calibration,
            calibration_fingerprint=calibration_fingerprint(calibration),
            orientation_candidate_id="geometry-0000000000000000",
            rotation=np.eye(3),
            translation=[0.0, 0.0, 0.0],
            coordinate_scales=[1.0, 1.0, 1.0],
            experimental_node_ids=[1],
            mapped_fe_node_ids=["PLATE-1:1"],
            measured_dof_contract=[[False, False, True]],
            registration_metrics={},
        )
        with self.assertRaises(RegistrationMismatchError) as context:
            registration.check_compatible(source, v2)
        self.assertEqual(context.exception.field, "fe_geometry_identity")


if __name__ == "__main__":
    unittest.main()
