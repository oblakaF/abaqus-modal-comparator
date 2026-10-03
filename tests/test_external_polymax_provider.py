from __future__ import annotations

from dataclasses import replace
import math
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import universal_reader
from domain.experiment_fixture import (
    FixtureSourceMismatchError,
    fixture_roots_from_environment,
    load_experiment_fixture_manifest,
    resolve_external_file,
)
from domain.modal_fitting import (
    FittingWorkflow,
    ModalFittingProviderIdentity,
    ModalFittingProviderRegistry,
    ModalFittingRefusal,
    ProviderKind,
    validate_fitting_output,
)
from domain.modal_input_source import (
    EXTERNAL_POLYMAX_MODE_SOURCE,
    IdentificationInputSourceRefusal,
    ModalInputSource,
    classify_mode_source,
    require_identification_input,
)
from fixture_support import MANIFEST_PATH, NODE_IDS, build_synthetic_fixture_workspace, manifest_from_record
from services.experiment_fixture_regression import FixtureRegressionError
from services.external_polymax_provider import (
    EXTERNAL_POLYMAX_PROVIDER,
    ExternalPolyMAXProvider,
    admitted_provider_registry,
    default_configuration,
    prepare_external_polymax_modal_dataset,
    prepare_frf_input,
)
from services.production_modal_input import load_production_modal_input


# D-028: fixture-specific M1 gate references (pinned SP13 repeat-a PolyMAX values), not a fixture list.
GATE_REFERENCES_HZ = {"SP13/best": (205.65, 212.66, 228.61)}
GATE_TOLERANCE_HZ = 0.05
KNOWN_FALSE_PEAK_HZ = {"SP13/best": 217.5}
POLES = {1: complex(-0.15, 2 * math.pi * 12.0), 2: complex(-0.40, 2 * math.pi * 31.5)}


def synthetic_export(*, with_dataset_55=True, with_pole=True):
    """Datasets of a tiny PolyMAX-style export: geometry, dataset-55 set 'Set A', dataset-58 FRFs."""
    datasets = [{"type": 2411, "node_nums": np.array(NODE_IDS), "x": np.array([0.0, 0.1, 0.2]),
                 "y": np.zeros(3), "z": np.zeros(3)}]
    if with_dataset_55:
        for number, pole in POLES.items():
            record = {"type": 55, "id1": "Set A", "id2": "Synthetic PolyMAX", "id3": "2026-09-10",
                      "id4": f"MODE NO. {number}", "id5": "", "analysis_type": 3, "mode_n": number,
                      "node_nums": np.array(NODE_IDS), "r1": np.zeros(3), "r2": np.zeros(3),
                      "r3": np.array([1.0, -0.5, 0.25]) * number}
            if with_pole:
                record["eig"] = pole
            else:
                record["freq"] = abs(pole.imag) / (2 * math.pi)
            datasets.append(record)
    axis = np.linspace(1.0, 100.0, 991)
    for index, node in enumerate(NODE_IDS):
        response = sum((index + 1) / (abs(p) ** 2 - (2 * math.pi * axis) ** 2 + 2j * (-p.real) * 2 * math.pi * axis)
                       for p in POLES.values())
        for func_type, data in ((4, response), (6, np.full_like(axis, 0.97))):
            datasets.append({"type": 58, "func_type": func_type, "id1": f"FRF {node}", "id2": "H1",
                             "rsp_node": node, "rsp_dir": 3, "ref_node": NODE_IDS[0], "ref_dir": 3, "x": axis,
                             "data": data, "ordinate_spec_data_type": 11, "orddenom_spec_data_type": 13})
    return datasets


class SyntheticProviderTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.workspace = build_synthetic_fixture_workspace(Path(temp.name))
        self.record = self.workspace.record
        self.datasets = synthetic_export()
        patcher = patch.object(universal_reader, "_read_universal_datasets", side_effect=lambda path: self.datasets)
        patcher.start()
        self.addCleanup(patcher.stop)

    def manifest(self, **changes):
        return manifest_from_record(self.record, **changes)

    def run_chain(self, manifest=None, **kwargs):
        return prepare_external_polymax_modal_dataset(
            "SYN/set-a", roots=self.workspace.roots, manifest=manifest or self.manifest(),
            repo_root=self.workspace.repo_root, **kwargs)

    def provider_and_frf(self):
        manifest = self.manifest()
        fixture = manifest.fixture("SYN/set-a")
        provider = ExternalPolyMAXProvider(roots=self.workspace.roots, manifest=manifest,
                                           repo_root=self.workspace.repo_root)
        frf = prepare_frf_input(fixture, self.workspace.roots)
        return provider, frf, default_configuration(fixture, frf)

    # Provider ---------------------------------------------------------------------------
    def test_successful_execution_preserves_the_frozen_selection(self):
        validated = self.run_chain()
        modes = validated.output.dataset.sorted_modes()
        production = load_production_modal_input("SYN/set-a", roots=self.workspace.roots, manifest=self.manifest(),
                                                 repo_root=self.workspace.repo_root)
        self.assertIs(validated.source_classification.source, ModalInputSource.CURVE_FITTED)
        for mode, reference in zip(modes, production.dataset.sorted_modes(), strict=True):
            pole = POLES[mode.number]
            self.assertEqual(mode.frequency_hz, reference.frequency_hz)
            self.assertAlmostEqual(mode.frequency_hz, abs(pole.imag) / (2 * math.pi), places=12)
            self.assertAlmostEqual(mode.damping_ratio, -pole.real / abs(pole), places=15)
            self.assertEqual(list(mode.node_ids), list(reference.node_ids))
            np.testing.assert_array_equal(mode.vectors, reference.vectors)
            self.assertEqual(mode.metadata["mode_source"], EXTERNAL_POLYMAX_MODE_SOURCE)

    def test_registry_admission(self):
        registry = admitted_provider_registry()
        self.assertIs(registry.require(EXTERNAL_POLYMAX_PROVIDER), EXTERNAL_POLYMAX_PROVIDER)
        self.assertIs(classify_mode_source({"dataset_type": 55, "mode_source": EXTERNAL_POLYMAX_MODE_SOURCE}),
                      ModalInputSource.CURVE_FITTED)
        with self.assertRaises(ModalFittingRefusal) as caught:
            self.run_chain(registry=ModalFittingProviderRegistry())
        self.assertEqual(caught.exception.field, "provider")

    def test_provenance_is_complete(self):
        provenance = self.run_chain().output.provenance
        self.assertEqual(provenance["provider_name"], "external-polymax")
        self.assertEqual(provenance["provider_version"], "1")
        self.assertEqual(provenance["fixture_id"], "SYN/set-a")
        self.assertEqual(provenance["modal_set"], "set-a")
        self.assertEqual(provenance["pole_selection"], "external_frozen_selection")
        self.assertEqual(provenance["source_file"]["sha256"], self.record["experimental_source"]["sha256"])
        self.assertEqual(provenance["frf_source_sha256"], self.record["experimental_source"]["sha256"])
        self.assertEqual(provenance["frequency_band_hz"], [1.0, 100.0])
        self.assertEqual(provenance["registration_hash"], self.workspace.registration.registration_hash)
        self.assertEqual(provenance["frf_quantity"], "velocity/force")
        self.assertEqual(set(provenance["configuration"]), {"fixture_id", "modal_set", "frequency_band_hz"})

    def test_output_is_deterministic(self):
        first, second = self.run_chain().output, self.run_chain().output
        self.assertEqual(first.provenance, second.provenance)
        self.assertEqual(first.qc_summary, second.qc_summary)
        for a, b in zip(first.dataset.sorted_modes(), second.dataset.sorted_modes(), strict=True):
            self.assertEqual((a.frequency_hz, a.damping_ratio), (b.frequency_hz, b.damping_ratio))
            np.testing.assert_array_equal(a.vectors, b.vectors)

    def test_qc_hooks_are_raw_values_only(self):
        output = self.run_chain().output
        self.assertEqual(output.qc_summary["status"], "NOT_EVALUATED")
        self.assertEqual(set(output.qc_summary["hooks"]), {1, 2})
        self.assertEqual(output.confidence[1], {"frequency_sd_hz": None, "damping_sd": None})

    # Refusal ----------------------------------------------------------------------------
    def test_wrong_sha_is_refused(self):
        self.workspace.source_file.write_bytes(b"x" * len(self.workspace.payload))
        with self.assertRaises(FixtureSourceMismatchError):
            self.run_chain()

    def test_wrong_frf_is_refused(self):
        provider, frf, configuration = self.provider_and_frf()
        with self.assertRaises(ModalFittingRefusal) as caught:
            provider.fit(replace(frf, source_sha256="f" * 64), configuration)
        self.assertEqual(caught.exception.field, "frf.source_sha256")

    def test_wrong_fixture_is_refused(self):
        provider, frf, configuration = self.provider_and_frf()
        with self.assertRaises(ModalFittingRefusal) as caught:
            provider.fit(frf, {**configuration, "fixture_id": "SP99/none"})
        self.assertEqual(caught.exception.field, "configuration.fixture_id")
        with self.assertRaises(ModalFittingRefusal):
            prepare_external_polymax_modal_dataset("SP99/none", roots=self.workspace.roots, manifest=self.manifest())

    def test_wrong_configuration_is_refused(self):
        provider, frf, configuration = self.provider_and_frf()
        for changes, field in (
            ({"modal_set": "set-b"}, "configuration.modal_set"),
            ({"frequency_band_hz": [0.5, 100.0]}, "configuration.frequency_band_hz"),
            ({"frequency_band_hz": [20.0, 100.0]}, "configuration.frequency_band_hz"),  # would trim mode 1
            ({"extra": 1}, "configuration"),
        ):
            with self.subTest(changes=changes), self.assertRaises(ModalFittingRefusal) as caught:
                provider.fit(frf, {**configuration, **changes})
            self.assertEqual(caught.exception.field, field)

    def test_wrong_provider_identity_is_refused(self):
        provider, frf, configuration = self.provider_and_frf()
        impostor = ModalFittingProviderIdentity("external-polymax", "1", ProviderKind.EXTERNAL, "impostor label/1")
        provider.identity = impostor
        with self.assertRaises(ModalFittingRefusal) as caught:
            from domain.modal_fitting import run_modal_fitting
            run_modal_fitting(provider, frf, configuration, registry=admitted_provider_registry(),
                              workflow=FittingWorkflow.PRODUCTION)
        self.assertEqual(caught.exception.field, "provider")

    def test_missing_provenance_is_refused(self):
        provider, frf, configuration = self.provider_and_frf()
        output = provider.fit(frf, configuration)
        for key in ("fixture_id", "modal_set", "source_file", "provider_name", "frf_source_sha256"):
            with self.subTest(key=key), self.assertRaises(ModalFittingRefusal) as caught:
                provenance = {name: value for name, value in output.provenance.items() if name != key}
                validate_fitting_output(replace(output, provenance=provenance), frf=frf, configuration=configuration,
                                        registry=admitted_provider_registry(), workflow=FittingWorkflow.PRODUCTION)
            self.assertEqual(caught.exception.field, "provenance")

    def test_wrong_pole_selection_type_is_refused(self):
        provider, frf, configuration = self.provider_and_frf()
        output = provider.fit(frf, configuration)
        for value, field in (("manual_review", "provenance.pole_selection"),
                             ("hand-picked", "provenance.pole_selection")):
            with self.subTest(value=value), self.assertRaises(ModalFittingRefusal) as caught:
                validate_fitting_output(replace(output, provenance={**output.provenance, "pole_selection": value}),
                                        frf=frf, configuration=configuration, registry=admitted_provider_registry(),
                                        workflow=FittingWorkflow.PRODUCTION)
            self.assertEqual(caught.exception.field, field)

    def test_peak_derived_source_is_refused(self):
        # FRF-only export: with a pinned modal set the reader refuses instead of falling back to peak picking.
        self.datasets = synthetic_export(with_dataset_55=False)
        with self.assertRaisesRegex(ValueError, "no valid dataset-55 modal sets"):
            self.run_chain()
        # A manifest record declaring a peak-derived source type is refused by the M1.2 path.
        with self.assertRaises(FixtureRegressionError) as caught:
            self.run_chain(manifest=self.manifest(modal_set__source_type="dataset-58-peak-picking"))
        self.assertEqual(caught.exception.field, "modal_set.source_type")

    def test_unknown_source_is_refused(self):
        with self.assertRaises(FixtureRegressionError) as caught:
            self.run_chain(manifest=self.manifest(modal_set__source_type="unregistered-modal-source"))
        self.assertEqual(caught.exception.field, "modal_set.source_type")

    def test_mode_without_stored_pole_is_refused(self):
        self.datasets = synthetic_export(with_pole=False)
        with self.assertRaises(ModalFittingRefusal) as caught:
            self.run_chain()
        self.assertEqual(caught.exception.field, "dataset")

    # M1.1 -------------------------------------------------------------------------------
    def test_m11_policy_compatibility(self):
        dataset = self.run_chain().output.dataset
        self.assertIs(require_identification_input(dataset).source, ModalInputSource.CURVE_FITTED)
        dataset.modes[0].metadata["mode_source"] = "FRF peak-derived experimental shape"
        with self.assertRaises(IdentificationInputSourceRefusal):
            require_identification_input(dataset)


class RealFixtureProviderTests(unittest.TestCase):
    """Every accepted manifest fixture through the full provider chain (store permitting)."""

    def test_accepted_fixtures_reproduce_the_frozen_polymax_result(self):
        roots = fixture_roots_from_environment()
        for fixture in load_experiment_fixture_manifest(MANIFEST_PATH).fixtures:
            with self.subTest(fixture=fixture.fixture_id):
                store = fixture.experimental_source.location.store
                if store not in roots:
                    self.skipTest(f"{fixture.fixture_id}: store {store!r} not configured")
                validated = prepare_external_polymax_modal_dataset(fixture.fixture_id, roots=roots)
                output = validated.output
                modes = output.dataset.sorted_modes()

                # Fixture identity (M0.2 manifest) and M1.1.
                self.assertIs(validated.source_classification.source, ModalInputSource.CURVE_FITTED)
                self.assertEqual(len(modes), fixture.modal_set.mode_count)
                self.assertEqual(len(modes[0].node_ids), fixture.modal_set.measurement_point_count)
                self.assertEqual(tuple(output.provenance["measured_dofs"]), fixture.modal_set.measured_dofs)
                self.assertEqual(output.provenance["registration_hash"], fixture.registration.registration_hash)
                self.assertEqual(output.provenance["fe_geometry_sha256"], fixture.fe.geometry_identity.sha256)
                self.assertEqual(output.provenance["frf_source_sha256"], fixture.experimental_source.sha256)

                # M1.2: identical frequencies, shapes and point order to the production input.
                production = load_production_modal_input(fixture.fixture_id, roots=roots)
                for mode, reference in zip(modes, production.dataset.sorted_modes(), strict=True):
                    self.assertEqual(mode.frequency_hz, reference.frequency_hz)
                    self.assertEqual(list(mode.node_ids), list(reference.node_ids))
                    np.testing.assert_array_equal(mode.vectors, reference.vectors)

                # Damping equals PolyMAX's own stated value (independent: the record's text field).
                records = universal_reader._read_universal_datasets(
                    resolve_external_file(fixture.experimental_source, roots))
                indices = production.dataset.metadata["modal_set_record_indices"]
                for mode, index in zip(modes, indices):
                    stated = float(re.search(r"DAMPING ([\d.eE+-]+)", records[index]["id4"]).group(1))
                    self.assertAlmostEqual(mode.damping_ratio, stated, delta=1.0e-6)

                # Determinism.
                again = prepare_external_polymax_modal_dataset(fixture.fixture_id, roots=roots).output
                self.assertEqual(again.provenance, output.provenance)

                # D-028 gate on fixture-specific references.
                frequencies = np.array([mode.frequency_hz for mode in modes])
                for reference in GATE_REFERENCES_HZ.get(fixture.fixture_id, ()):
                    self.assertLessEqual(float(np.min(np.abs(frequencies - reference))), GATE_TOLERANCE_HZ)
                false_peak = KNOWN_FALSE_PEAK_HZ.get(fixture.fixture_id)
                if false_peak is not None:
                    self.assertGreater(float(np.min(np.abs(frequencies - false_peak))), 1.0)


if __name__ == "__main__":
    unittest.main()
