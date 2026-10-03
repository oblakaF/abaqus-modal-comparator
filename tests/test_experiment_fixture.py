from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.experiment_fixture import (
    EXPERIMENT_FIXTURE_MANIFEST_SCHEMA,
    FixtureManifestError,
    FixtureSourceMismatchError,
    FixtureSourceUnavailableError,
    fixture_roots_from_environment,
    load_experiment_fixture_manifest,
    parse_experiment_fixture_manifest,
    resolve_external_file,
)


MANIFEST_PATH = ROOT / "docs" / "auto_id" / "fixtures" / "real_experiment_fixtures.json"


def manifest_data():
    with open(MANIFEST_PATH, encoding="utf-8") as handle:
        return json.load(handle)


class RealFixtureManifestTests(unittest.TestCase):
    def test_manifest_parses_with_sp02_and_sp13_records(self):
        manifest = load_experiment_fixture_manifest(MANIFEST_PATH)

        self.assertEqual(manifest.schema_version, EXPERIMENT_FIXTURE_MANIFEST_SCHEMA)
        self.assertEqual([item.fixture_id for item in manifest.fixtures], ["SP02/bravo-1", "SP13/best"])

        sp02 = manifest.fixture("SP02/bravo-1")
        self.assertEqual(sp02.experimental_source.file_name, "SP02_polymax_retry_260803.unv")
        self.assertEqual(sp02.modal_set.name, "bravo-1")
        self.assertEqual(sp02.modal_set.measured_dofs, ("U3",))
        self.assertTrue(sp02.registration.registration_hash.startswith("9bf736d3"))
        self.assertTrue(sp02.fe.geometry_identity.sha256.startswith("72e8597a"))

        sp13 = manifest.fixture("SP13/best")
        self.assertEqual(sp13.experimental_source.file_name, "SP13_a_polymax.unv")
        self.assertEqual(sp13.modal_set.name, "best")
        self.assertEqual(sp13.modal_set.measured_dofs, ("U3",))
        self.assertTrue(sp13.registration.registration_hash.startswith("a8970e52"))
        self.assertTrue(sp13.fe.geometry_identity.sha256.startswith("34d69d79"))

    def test_records_match_the_accepted_frozen_registrations(self):
        for fixture in load_experiment_fixture_manifest(MANIFEST_PATH).fixtures:
            with self.subTest(fixture=fixture.fixture_id):
                with open(ROOT / fixture.registration.path, encoding="utf-8") as handle:
                    registration = json.load(handle)
                source = registration["experimental_source_identity"]
                geometry = registration["fe_geometry_identity"]
                contract = registration["measured_dof_contract"]
                measured = tuple(
                    component
                    for index, component in enumerate(contract["components"])
                    if all(row[index] for row in contract["mask"])
                )

                self.assertEqual(fixture.registration.registration_hash, registration["registration_hash"])
                self.assertEqual(fixture.registration.schema_version, registration["registration_schema_version"])
                self.assertEqual(fixture.modal_set.name, registration["experimental_modal_set_identity"])
                self.assertEqual(fixture.modal_set.measurement_point_count, len(registration["experimental_node_ids"]))
                self.assertEqual(fixture.modal_set.measured_dofs, measured)
                self.assertEqual(fixture.experimental_source.sha256, source["sha256"])
                self.assertEqual(fixture.experimental_source.size_bytes, source["size"])
                self.assertEqual(fixture.fe.geometry_identity.sha256, geometry["sha256"])
                self.assertEqual(fixture.fe.geometry_identity.node_count, geometry["node_count"])
                self.assertEqual(fixture.fe.geometry_identity.schema_version, geometry["schema_version"])

    def test_manifest_stores_no_local_absolute_paths(self):
        text = MANIFEST_PATH.read_text(encoding="utf-8")
        self.assertNotRegex(text, r"[A-Za-z]:[\\/]")
        self.assertNotIn("\\\\", text)

    def test_null_identifiers_are_declared_unresolved(self):
        for fixture in load_experiment_fixture_manifest(MANIFEST_PATH).fixtures:
            declared = {item.field for item in fixture.unresolved}
            for name in ("physical_specimen_id", "experiment_id", "test_run_id"):
                with self.subTest(fixture=fixture.fixture_id, field=name):
                    self.assertEqual(getattr(fixture, name) is None, name in declared)


class FixtureManifestValidationTests(unittest.TestCase):
    def assertRejected(self, data, field_fragment):
        with self.assertRaises(FixtureManifestError) as caught:
            parse_experiment_fixture_manifest(data)
        self.assertIn(field_fragment, str(caught.exception))

    def test_missing_required_field_is_rejected(self):
        for path, key in (
            ((), "fixture_id"),
            (("modal_set",), "measured_dofs"),
            (("registration",), "registration_hash"),
            (("experimental_source",), "sha256"),
            (("fe",), "geometry_identity"),
            (("provenance",), "source_of_truth"),
        ):
            with self.subTest(key=key):
                data = manifest_data()
                target = data["fixtures"][0]
                for part in path:
                    target = target[part]
                del target[key]
                self.assertRejected(data, key)

    def test_unknown_field_is_rejected(self):
        data = manifest_data()
        data["fixtures"][0]["modal_set"]["mode_shapes"] = []
        self.assertRejected(data, "unknown field(s) mode_shapes")

    def test_hash_format_is_enforced(self):
        for bad in ("9bf736d3", "9BF736D3650B491F8ABF5F1A9ABD60F6616639FA5F2F8811A896C5A04FBDC164", "g" * 64, None):
            with self.subTest(value=bad):
                data = manifest_data()
                data["fixtures"][0]["registration"]["registration_hash"] = bad
                self.assertRejected(data, "registration.registration_hash")

    def test_local_absolute_or_escaping_paths_are_rejected(self):
        for bad in (r"D:\Snadwich\SP-02\SP02_polymax_retry_260803.unv", "/data/SP02_polymax_retry_260803.unv",
                    "C:/Snadwich/SP02_polymax_retry_260803.unv", "../SP02_polymax_retry_260803.unv"):
            with self.subTest(value=bad):
                data = manifest_data()
                data["fixtures"][0]["experimental_source"]["location"]["relative_path"] = bad
                self.assertRejected(data, "experimental_source.location.relative_path")

    def test_relative_path_must_name_the_pinned_file(self):
        data = manifest_data()
        data["fixtures"][0]["experimental_source"]["location"]["relative_path"] = "SP-02/other.unv"
        self.assertRejected(data, "relative_path must end with file_name")

    def test_registration_and_fe_geometry_must_agree(self):
        data = manifest_data()
        data["fixtures"][0]["registration"]["fe_geometry_sha256"] = "0" * 64
        self.assertRejected(data, "does not match fe.geometry_identity.sha256")

    def test_undeclared_null_identifier_is_rejected(self):
        data = manifest_data()
        data["fixtures"][0]["test_run_id"] = None
        self.assertRejected(data, "test_run_id")

    def test_identifier_cannot_be_both_set_and_unresolved(self):
        data = manifest_data()
        data["fixtures"][0]["physical_specimen_id"] = "SP02-panel"
        self.assertRejected(data, "also declared unresolved")

    def test_invalid_measured_dofs_and_counts_are_rejected(self):
        for key, value, fragment in (
            ("measured_dofs", [], "measured_dofs"),
            ("measured_dofs", ["U3", "U3"], "measured_dofs"),
            ("measured_dofs", ["UR1"], "measured_dofs"),
            ("mode_count", 0, "mode_count"),
            ("measurement_point_count", True, "measurement_point_count"),
        ):
            with self.subTest(key=key, value=value):
                data = manifest_data()
                data["fixtures"][0]["modal_set"][key] = value
                self.assertRejected(data, fragment)

    def test_schema_version_and_duplicate_ids_are_rejected(self):
        data = manifest_data()
        data["schema_version"] = "experiment-fixture-manifest/0"
        self.assertRejected(data, "manifest.schema_version")

        data = manifest_data()
        data["fixtures"].append(copy.deepcopy(data["fixtures"][0]))
        self.assertRejected(data, "duplicate fixture_id SP02/bravo-1")


class ExternalFileResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload = b"fitted modes"
        data = manifest_data()
        source = data["fixtures"][0]["experimental_source"]
        source.update(
            file_name="sample.unv",
            sha256=hashlib.sha256(self.payload).hexdigest(),
            size_bytes=len(self.payload),
            location={"store": "snadwich", "relative_path": "SP-02/sample.unv"},
        )
        self.reference = parse_experiment_fixture_manifest(data).fixtures[0].experimental_source

    def write(self, payload):
        path = self.root / "SP-02" / "sample.unv"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    def test_unconfigured_store_is_refused(self):
        with self.assertRaises(FixtureSourceUnavailableError) as caught:
            resolve_external_file(self.reference, {})
        self.assertIn("AUTO_ID_FIXTURE_ROOT_SNADWICH", str(caught.exception))

    def test_missing_source_is_refused(self):
        with self.assertRaises(FixtureSourceUnavailableError):
            resolve_external_file(self.reference, {"snadwich": self.root})

    def test_size_or_hash_mismatch_is_refused(self):
        self.write(b"other bytes!")  # same length, different content
        with self.assertRaises(FixtureSourceMismatchError):
            resolve_external_file(self.reference, {"snadwich": self.root})
        self.write(b"short")
        with self.assertRaises(FixtureSourceMismatchError):
            resolve_external_file(self.reference, {"snadwich": self.root})

    def test_verified_source_resolves_under_its_store_root(self):
        path = self.write(self.payload)
        self.assertEqual(resolve_external_file(self.reference, {"snadwich": self.root}), path)

    def test_roots_come_from_environment_variables(self):
        roots = fixture_roots_from_environment(
            {
                "AUTO_ID_FIXTURE_ROOT_SNADWICH": str(self.root),
                "AUTO_ID_FIXTURE_ROOT_CARBON_PROJECT_ARCHIVE": str(self.root / "archive"),
                "AUTO_ID_FIXTURE_ROOT_EMPTY": "  ",
                "UNRELATED": "x",
            }
        )
        self.assertEqual(roots, {"snadwich": self.root, "carbon-project-archive": self.root / "archive"})


if __name__ == "__main__":
    unittest.main()
