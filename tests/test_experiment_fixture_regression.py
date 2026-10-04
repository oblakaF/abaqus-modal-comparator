from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.experiment_fixture import (
    FixtureSourceMismatchError,
    FixtureSourceUnavailableError,
    fixture_roots_from_environment,
    load_experiment_fixture_manifest,
)
from fixture_support import (
    MANIFEST_PATH,
    build_synthetic_fixture_workspace,
    fixture_from_record,
    synthetic_modal_dataset,
)
from services.experiment_fixture_regression import (
    FixtureRegressionError,
    verify_experiment_fixture,
)


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
        workspace = build_synthetic_fixture_workspace(Path(temp.name))
        self.repo_root = workspace.repo_root
        self.store_root = workspace.store_root
        self.roots = workspace.roots
        self.payload = workspace.payload
        self.source_file = workspace.source_file
        self.registration = workspace.registration
        self.record = workspace.record
        self.mode_source = "curve-fitted dataset 55"
        self.z_only = True

    def fixture(self, **changes):
        return fixture_from_record(self.record, **changes)

    def loader(self, path, modal_set=None):
        self.assertEqual(Path(path), self.source_file)
        return synthetic_modal_dataset(path, modal_set, mode_source=self.mode_source, z_only=self.z_only)

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
