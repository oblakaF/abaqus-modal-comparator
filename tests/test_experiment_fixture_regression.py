from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from coordinate_calibration import CoordinateCalibration
from domain.experiment_fixture import (
    FixtureSourceMismatchError,
    FixtureSourceUnavailableError,
    fixture_roots_from_environment,
    load_experiment_fixture_manifest,
    parse_experiment_fixture_manifest,
)
from domain.registration import FrozenRegistration
from modal_core import ModalDataset, ModeShape
from scientific_state import calibration_fingerprint
from services.experiment_fixture_regression import (
    FixtureRegressionError,
    verify_experiment_fixture,
)


MANIFEST_PATH = ROOT / "docs" / "auto_id" / "fixtures" / "real_experiment_fixtures.json"
CALIBRATION = CoordinateCalibration(
    mode="calibrated_physical", abaqus_unit="mm", experimental_unit="m"
).to_dict()
NODE_IDS = [101, 102, 103]
U3_ONLY = [[False, False, True]] * len(NODE_IDS)


class RealFixtureRegressionTests(unittest.TestCase):
    """Every manifest record must still be reproduced from its real external data.

    The fixture list comes only from the M0.2 manifest.  A record is skipped, with
    the reason, when its experimental-source store root is not configured on this
    machine (AUTO_ID_FIXTURE_ROOT_<STORE>); a configured root that does not hold
    the pinned file fails.
    """

    def test_every_manifest_fixture_is_reproduced(self):
        manifest = load_experiment_fixture_manifest(MANIFEST_PATH)
        roots = fixture_roots_from_environment()
        for fixture in manifest.fixtures:
            with self.subTest(fixture=fixture.fixture_id):
                store = fixture.experimental_source.location.store
                if store not in roots:
                    self.skipTest(
                        f"{fixture.fixture_id}: store {store!r} not configured "
                        f"(set AUTO_ID_FIXTURE_ROOT_{store.upper().replace('-', '_')})"
                    )
                report = verify_experiment_fixture(fixture, roots, repo_root=ROOT)

                self.assertEqual(report.fixture_id, fixture.fixture_id)
                self.assertEqual(report.modal_set_key, fixture.modal_set.name)
                self.assertEqual(report.mode_count, fixture.modal_set.mode_count)
                self.assertEqual(report.point_count, fixture.modal_set.measurement_point_count)
                self.assertEqual(report.measured_dofs, fixture.modal_set.measured_dofs)
                self.assertEqual(report.registration_hash, fixture.registration.registration_hash)
                self.assertEqual(report.fe_geometry_sha256, fixture.fe.geometry_identity.sha256)


class FixtureRegressionContractTests(unittest.TestCase):
    """Synthetic fixture (no large data) exercising every refusal path."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.repo_root = base / "repo"
        self.store_root = base / "store"
        self.payload = b"synthetic PolyMAX export"
        self.source_file = self.store_root / "SP-XX" / "synthetic.unv"
        self.source_file.parent.mkdir(parents=True)
        self.source_file.write_bytes(self.payload)
        self.roots = {"snadwich": self.store_root}

        registration = FrozenRegistration.create(
            experimental_source_identity={
                "path": "synthetic.unv",
                "size": len(self.payload),
                "mtime_ns": 0,
                "sha256": hashlib.sha256(self.payload).hexdigest(),
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
        registration_path = self.repo_root / "docs" / "registrations" / "SYN_frozen_registration.json"
        registration_path.parent.mkdir(parents=True)
        registration_path.write_text(json.dumps(registration.to_dict()), encoding="utf-8")
        self.registration = registration

        with open(MANIFEST_PATH, encoding="utf-8") as handle:
            record = copy.deepcopy(json.load(handle)["fixtures"][0])
        record["fixture_id"] = "SYN/set-a"
        record["experimental_source"].update(
            file_name="synthetic.unv",
            sha256=hashlib.sha256(self.payload).hexdigest(),
            size_bytes=len(self.payload),
            location={"store": "snadwich", "relative_path": "SP-XX/synthetic.unv"},
        )
        record["modal_set"].update(name="set-a", display_name="Set A", mode_count=2, measurement_point_count=3)
        record["registration"].update(
            path="docs/registrations/SYN_frozen_registration.json",
            registration_hash=registration.registration_hash,
            fe_geometry_sha256="c" * 64,
        )
        record["fe"]["geometry_identity"] = {"schema_version": "fe-geometry-identity/2", "sha256": "c" * 64, "node_count": 10}
        self.record = record
        self.mode_source = "curve-fitted dataset 55"
        self.z_only = True

    def fixture(self, **changes):
        record = copy.deepcopy(self.record)
        for path, value in changes.items():
            target = record
            *parents, key = path.split("__")
            for part in parents:
                target = target[part]
            target[key] = value
        return parse_experiment_fixture_manifest(
            {"schema_version": "experiment-fixture-manifest/1", "fixtures": [record]}
        ).fixtures[0]

    def loader(self, path, modal_set=None):
        self.assertEqual(Path(path), self.source_file)
        modes = []
        for number in (1, 2):
            vectors = np.zeros((len(NODE_IDS), 3))
            vectors[:, 2] = [1.0, -0.5, 0.25]
            if not self.z_only:
                vectors[:, 0] = 0.3
            modes.append(ModeShape(number, 10.0 * number, np.array(NODE_IDS, dtype=object), np.zeros((3, 3)), vectors))
        return ModalDataset(
            "synthetic",
            Path(path),
            modes,
            metadata={
                "mode_source": self.mode_source,
                "modal_set_key": modal_set,
                "available_modal_sets": [{"key": "set-a"}, {"key": "set-b"}],
            },
        )

    def verify(self, fixture):
        return verify_experiment_fixture(fixture, self.roots, repo_root=self.repo_root, load_modal_dataset=self.loader)

    def assertRegression(self, fixture, field):
        with self.assertRaises(FixtureRegressionError) as caught:
            self.verify(fixture)
        self.assertEqual(caught.exception.field, field)

    def test_valid_fixture_passes(self):
        report = self.verify(self.fixture())
        self.assertEqual(
            (report.mode_count, report.point_count, report.measured_dofs, report.registration_hash),
            (2, 3, ("U3",), self.registration.registration_hash),
        )

    def test_missing_source_root_fails(self):
        with self.assertRaises(FixtureSourceUnavailableError):
            verify_experiment_fixture(self.fixture(), {}, repo_root=self.repo_root, load_modal_dataset=self.loader)

    def test_missing_source_file_fails(self):
        self.source_file.unlink()
        with self.assertRaises(FixtureSourceUnavailableError):
            self.verify(self.fixture())

    def test_wrong_sha_fails(self):
        self.source_file.write_bytes(b"x" * len(self.payload))
        with self.assertRaises(FixtureSourceMismatchError):
            self.verify(self.fixture())

    def test_wrong_mode_count_fails(self):
        self.assertRegression(self.fixture(modal_set__mode_count=3), "modal_set.mode_count")

    def test_wrong_point_count_fails(self):
        self.assertRegression(self.fixture(modal_set__measurement_point_count=4), "modal_set.measurement_point_count")

    def test_missing_modal_set_fails(self):
        self.assertRegression(self.fixture(modal_set__name="set-c"), "registration.experimental_modal_set_identity")

    def test_peak_derived_source_cannot_substitute(self):
        self.mode_source = "dataset 58 FRF peak extraction"
        self.assertRegression(self.fixture(), "modal_set.source_type")

    def test_unregistered_source_type_fails(self):
        self.assertRegression(self.fixture(modal_set__source_type="peak-picked-frf"), "modal_set.source_type")

    def test_wrong_registration_hash_fails(self):
        self.assertRegression(self.fixture(registration__registration_hash="d" * 64), "registration.registration_hash")

    def test_edited_registration_file_fails(self):
        path = self.repo_root / "docs" / "registrations" / "SYN_frozen_registration.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["mapped_fe_node_ids"][0] = "TOP:99"
        path.write_text(json.dumps(payload), encoding="utf-8")
        self.assertRegression(self.fixture(), "registration")

    def test_wrong_fe_identity_fails(self):
        self.assertRegression(
            self.fixture(registration__fe_geometry_sha256="e" * 64, fe__geometry_identity__sha256="e" * 64),
            "fe.geometry_identity",
        )
        self.assertRegression(self.fixture(fe__geometry_identity__node_count=11), "fe.geometry_identity")

    def test_wrong_dof_contract_fails(self):
        self.assertRegression(self.fixture(modal_set__measured_dofs=["U1", "U2", "U3"]), "modal_set.measured_dofs")

    def test_imported_dofs_outside_the_frozen_contract_fail(self):
        self.z_only = False
        self.assertRegression(self.fixture(), "measured_dof_contract")


if __name__ == "__main__":
    unittest.main()
