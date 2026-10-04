from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.experiment_fixture import (
    FixtureSourceMismatchError,
    FixtureSourceUnavailableError,
    fixture_roots_from_environment,
    load_experiment_fixture_manifest,
    resolve_external_file,
)
from domain.modal_input_source import IdentificationInputSourceRefusal, ModalInputSource
from fixture_support import (
    MANIFEST_PATH,
    build_synthetic_fixture_workspace,
    manifest_from_record,
    synthetic_modal_dataset,
)
from services.experiment_fixture_regression import FixtureRegressionError
from services.production_modal_input import FIXTURE_MANIFEST_PATH, load_production_modal_input
from universal_reader import load_universal_modal_file


class RealProductionModalInputTests(unittest.TestCase):
    """Every accepted manifest fixture loads through the production path (store permitting)."""

    def test_accepted_fixtures_load_with_preserved_data_and_provenance(self):
        self.assertEqual(FIXTURE_MANIFEST_PATH, MANIFEST_PATH)
        roots = fixture_roots_from_environment()
        for fixture in load_experiment_fixture_manifest(MANIFEST_PATH).fixtures:
            with self.subTest(fixture=fixture.fixture_id):
                store = fixture.experimental_source.location.store
                if store not in roots:
                    self.skipTest(f"{fixture.fixture_id}: store {store!r} not configured")
                loaded = load_production_modal_input(fixture.fixture_id, roots=roots)
                provenance = loaded.provenance()

                self.assertEqual(provenance["experimental_source"]["sha256"], fixture.experimental_source.sha256)
                self.assertEqual(provenance["modal_set"], fixture.modal_set.name)
                self.assertEqual(provenance["mode_count"], fixture.modal_set.mode_count)
                self.assertEqual(provenance["measurement_point_count"], fixture.modal_set.measurement_point_count)
                self.assertEqual(tuple(provenance["measured_dofs"]), fixture.modal_set.measured_dofs)
                self.assertEqual(provenance["registration_hash"], fixture.registration.registration_hash)
                self.assertEqual(provenance["fe_geometry_sha256"], fixture.fe.geometry_identity.sha256)
                self.assertEqual(provenance["input_source_class"], ModalInputSource.CURVE_FITTED.value)
                self.assertEqual(loaded.registration.registration_hash, fixture.registration.registration_hash)

                # Frequencies, damping, node order and shapes are the reader's, untouched.
                direct = load_universal_modal_file(
                    resolve_external_file(fixture.experimental_source, roots), modal_set=fixture.modal_set.name
                )
                for produced, expected in zip(loaded.dataset.sorted_modes(), direct.sorted_modes(), strict=True):
                    self.assertEqual(produced.number, expected.number)
                    self.assertEqual(produced.frequency_hz, expected.frequency_hz)
                    self.assertEqual(produced.damping_ratio, expected.damping_ratio)
                    self.assertEqual(list(produced.node_ids), list(expected.node_ids))
                    np.testing.assert_array_equal(produced.vectors, expected.vectors)


class ProductionModalInputContractTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.workspace = build_synthetic_fixture_workspace(Path(temp.name))
        self.mode_source = "curve-fitted dataset 55"
        self.mode_metadata = None
        self.z_only = True
        self.returned = []

    def loader(self, path, modal_set=None):
        dataset = synthetic_modal_dataset(path, modal_set, mode_source=self.mode_source, z_only=self.z_only,
                                          mode_metadata=self.mode_metadata)
        self.returned.append(dataset)
        return dataset

    def load(self, roots=None, **changes):
        return load_production_modal_input(
            "SYN/set-a",
            roots=self.workspace.roots if roots is None else roots,
            manifest=manifest_from_record(self.workspace.record, **changes),
            repo_root=self.workspace.repo_root,
            load_modal_dataset=self.loader,
        )

    def assertRegression(self, field, **changes):
        with self.assertRaises(FixtureRegressionError) as caught:
            self.load(**changes)
        self.assertEqual(caught.exception.field, field)

    def test_valid_fixture_returns_the_reader_dataset_with_provenance(self):
        loaded = self.load()
        self.assertIs(loaded.dataset, self.returned[-1])
        self.assertEqual([mode.frequency_hz for mode in loaded.dataset.sorted_modes()], [10.0, 20.0])
        self.assertEqual(loaded.registration, self.workspace.registration)
        provenance = loaded.provenance()
        self.assertEqual(
            (provenance["fixture_id"], provenance["modal_set"], provenance["mode_count"],
             provenance["measurement_point_count"], provenance["measured_dofs"], provenance["input_source_class"]),
            ("SYN/set-a", "set-a", 2, 3, ["U3"], "curve_fitted"),
        )

    def test_fixture_is_selected_only_by_manifest_id(self):
        with self.assertRaises(KeyError):
            load_production_modal_input(str(self.workspace.source_file), roots=self.workspace.roots)

    def test_default_manifest_is_the_accepted_fixture_manifest(self):
        # The real record is found; with no store root it is refused, never substituted.
        with self.assertRaises(FixtureSourceUnavailableError):
            load_production_modal_input("SP02/bravo-1", roots={})

    def test_missing_store_root_is_refused(self):
        with self.assertRaises(FixtureSourceUnavailableError):
            self.load(roots={})

    def test_wrong_source_is_refused(self):
        other = self.workspace.store_root / "SP-XX" / "other.unv"
        other.write_bytes(b"another export, not the pinned one")
        with self.assertRaises(FixtureSourceMismatchError):
            self.load(experimental_source__file_name="other.unv",
                      experimental_source__location={"store": "snadwich", "relative_path": "SP-XX/other.unv"})

    def test_wrong_sha_is_refused(self):
        self.assertRaises(FixtureSourceMismatchError, self.load, experimental_source__sha256="0" * 64)

    def test_wrong_modal_set_is_refused(self):
        self.assertRegression("registration.experimental_modal_set_identity", modal_set__name="set-b")

    def test_wrong_point_count_is_refused(self):
        self.assertRegression("modal_set.measurement_point_count", modal_set__measurement_point_count=4)

    def test_wrong_dof_contract_is_refused(self):
        self.assertRegression("modal_set.measured_dofs", modal_set__measured_dofs=["U1", "U2", "U3"])
        self.z_only = False
        self.assertRegression("measured_dof_contract")

    def test_peak_derived_dataset_is_refused(self):
        self.mode_source = "dataset 58 FRF peak extraction"
        self.assertRegression("modal_set.source_type")

    def test_peak_derived_mode_inside_a_fitted_set_is_refused(self):
        self.mode_metadata = {"dataset_type": 58, "mode_source": "FRF peak-derived experimental shape"}
        with self.assertRaises(IdentificationInputSourceRefusal) as caught:
            self.load()
        self.assertIs(caught.exception.source, ModalInputSource.PEAK_DERIVED)

    def test_unclassifiable_modes_are_refused(self):
        self.mode_metadata = {}
        with self.assertRaises(IdentificationInputSourceRefusal) as caught:
            self.load()
        self.assertIs(caught.exception.source, ModalInputSource.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
