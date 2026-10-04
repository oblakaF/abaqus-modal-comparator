from __future__ import annotations

import copy
from pathlib import Path
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
    fixture_roots_from_environment,
    load_experiment_fixture_manifest,
    resolve_external_file,
)
from domain.modal_input_source import (
    IdentificationInputSourceRefusal,
    ModalInputSource,
    classify_modal_dataset,
    classify_mode_source,
    require_identification_input,
)
from modal_core import ModalDataset, ModeShape, compare_modal_datasets
import services.stage_a_identification_service as stage_a
from test_polymax_modal_sets import _geometry, _mode, _mode_2414
from test_stage_a_identification_service import SyntheticProductionFixture
from universal_frf_review import modes_from_frf_datasets


MANIFEST_PATH = ROOT / "docs" / "auto_id" / "fixtures" / "real_experiment_fixtures.json"
PEAK = {"dataset_type": 58, "mode_source": "FRF peak-derived experimental shape"}


def _read(datasets, **kwargs):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "fixture.unv"
        path.write_text("fixture", encoding="utf-8")
        with patch.object(universal_reader, "_read_universal_datasets", return_value=datasets):
            return universal_reader.load_universal_modal_file(path, **kwargs)


def _peak_dataset():
    """Real dataset-58 peak extraction on a synthetic single-mode FRF."""
    axis = np.linspace(1.0, 100.0, 991)
    coordinates = np.array([[0.0, 0.0, 0.0], [0.5, 0.0, 0.0], [1.0, 0.0, 0.0]])
    shape = np.array([1.0, 0.2, -0.8])
    datasets = []
    for index, amplitude in enumerate(shape):
        response = amplitude / (40.0**2 - axis**2 + 2j * 0.01 * 40.0 * axis)
        for func_type, data in ((4, response), (6, np.full_like(axis, 0.98))):
            datasets.append({"type": 58, "func_type": func_type, "id2": "H1 / Force", "rsp_node": index + 1,
                             "rsp_dir": 3, "ref_node": 1, "ref_dir": 3, "x": axis, "data": data})
    modes, metadata = modes_from_frf_datasets(
        datasets, {index + 1: point for index, point in enumerate(coordinates)}, target_frequencies=[40.0], target_count=1
    )
    return ModalDataset("FRF", Path("frf.unv"), modes, metadata=metadata)


class SourceClassificationTests(unittest.TestCase):
    def test_reader_dataset_55_modal_set_is_curve_fitted(self):
        dataset = _read([_geometry(), _mode("Best", 1, 10.0), _mode("Best", 2, 20.0)], modal_set="best")
        classification = require_identification_input(dataset)
        self.assertIs(classification.source, ModalInputSource.CURVE_FITTED)
        self.assertEqual([kind for _, kind, _ in classification.modes], [ModalInputSource.CURVE_FITTED] * 2)

    def test_reader_dataset_2414_modes_are_curve_fitted(self):
        dataset = _read([_geometry(), _mode_2414(1, 10.0), _mode_2414(2, 20.0)])
        self.assertIs(classify_modal_dataset(dataset).source, ModalInputSource.CURVE_FITTED)

    def test_reader_frf_peak_modes_are_peak_derived_and_refused(self):
        dataset = _peak_dataset()
        self.assertTrue(dataset.modes)
        self.assertIs(classify_modal_dataset(dataset).source, ModalInputSource.PEAK_DERIVED)
        with self.assertRaises(IdentificationInputSourceRefusal) as caught:
            require_identification_input(dataset)
        self.assertIs(caught.exception.source, ModalInputSource.PEAK_DERIVED)
        self.assertIn("D-002", str(caught.exception))

    def test_cmif_svd_close_mode_candidates_are_peak_derived(self):
        metadata = {"mode_source": "local response-matrix SVD close-mode candidate"}
        self.assertIs(classify_mode_source(metadata), ModalInputSource.PEAK_DERIVED)

    def test_unknown_sources_are_refused(self):
        def mode(number, **metadata):
            return ModeShape(number, 10.0 * number, np.array([1], dtype=object), np.zeros((1, 3)),
                             np.array([[0.0, 0.0, 1.0]]), metadata=metadata)

        cases = {
            "no label, no dataset type": ModalDataset("x", Path("x"), [mode(1)]),
            "unrecognised label": ModalDataset("x", Path("x"), [mode(1, mode_source="manual entry")]),
            "label contradicts dataset type": ModalDataset(
                "x", Path("x"), [mode(1, dataset_type=2411, mode_source="curve-fitted modal dataset")]
            ),
            "curve-fitted modes, unknown dataset source": ModalDataset(
                "x", Path("x"), [mode(1, dataset_type=55)], metadata={"mode_source": "imported table"}
            ),
            "no modes": ModalDataset("x", Path("x"), []),
        }
        for name, dataset in cases.items():
            with self.subTest(name):
                self.assertIs(classify_modal_dataset(dataset).source, ModalInputSource.UNKNOWN)
                with self.assertRaises(IdentificationInputSourceRefusal) as caught:
                    require_identification_input(dataset)
                self.assertIs(caught.exception.source, ModalInputSource.UNKNOWN)

    def test_one_peak_derived_mode_taints_a_curve_fitted_set(self):
        dataset = _read([_geometry(), _mode("Best", 1, 10.0), _mode("Best", 2, 20.0)], modal_set="best")
        dataset.modes[1].metadata.update(mode_source="local response-matrix SVD close-mode candidate")
        classification = classify_modal_dataset(dataset)
        self.assertIs(classification.source, ModalInputSource.PEAK_DERIVED)
        self.assertIn("[2]", classification.reason)

    def test_peak_dataset_type_wins_over_a_curve_fitted_label(self):
        metadata = {"dataset_type": 58, "mode_source": "curve-fitted modal dataset"}
        self.assertIs(classify_mode_source(metadata), ModalInputSource.PEAK_DERIVED)

    def test_refusal_is_not_a_generic_failure_type(self):
        self.assertFalse(issubclass(IdentificationInputSourceRefusal, (ValueError, RuntimeError)))


class _PolicyPassed(Exception):
    pass


class StageAIdentificationInputPolicyTests(unittest.TestCase):
    def setUp(self):
        self.fixture = SyntheticProductionFixture()
        # Anything after the policy check signals "policy passed" without running the solver.
        patcher = patch.object(stage_a, "cluster_comparison_result", side_effect=_PolicyPassed)
        self.cluster = patcher.start()
        self.addCleanup(patcher.stop)

    def relabel(self, **metadata):
        for mode in self.fixture.comparison.experimental.modes:
            mode.metadata.clear()
            mode.metadata.update(metadata)

    def test_curve_fitted_input_is_accepted(self):
        with self.assertRaises(_PolicyPassed):
            self.fixture.identify()
        self.cluster.assert_called_once()

    def test_peak_derived_input_is_refused_before_any_computation(self):
        self.relabel(**PEAK)
        with self.assertRaises(IdentificationInputSourceRefusal) as caught:
            self.fixture.identify()
        self.assertIs(caught.exception.source, ModalInputSource.PEAK_DERIVED)
        self.cluster.assert_not_called()

    def test_unknown_input_is_refused_before_any_computation(self):
        self.relabel()
        with self.assertRaises(IdentificationInputSourceRefusal) as caught:
            self.fixture.identify()
        self.assertIs(caught.exception.source, ModalInputSource.UNKNOWN)
        self.cluster.assert_not_called()

    def test_refusal_also_applies_with_an_injected_pairing_provider(self):
        self.relabel(**PEAK)
        with self.assertRaises(IdentificationInputSourceRefusal):
            self.fixture.identify(pairing_provider=lambda observations, eigenpairs: None)
        self.cluster.assert_not_called()


class NormalComparisonUnchangedTests(unittest.TestCase):
    def test_comparison_of_peak_derived_modes_is_unchanged(self):
        fixture = SyntheticProductionFixture()
        reference = fixture.comparison
        experimental = copy.deepcopy(reference.experimental)
        for mode in experimental.modes:
            mode.metadata.clear()
            mode.metadata.update(PEAK)
        comparison = compare_modal_datasets(reference.abaqus, experimental, geometry_calibration=fixture.calibration)

        def summary(result):
            return [(pair.experimental_mode, pair.abaqus_mode, pair.status, round(pair.mac, 12),
                     round(pair.frequency_error_percent, 12)) for pair in result.pairs]

        self.assertTrue(comparison.pairs)
        self.assertEqual(summary(comparison), summary(reference))


class RealFixtureSourceTests(unittest.TestCase):
    def test_accepted_polymax_fixtures_are_curve_fitted(self):
        roots = fixture_roots_from_environment()
        for fixture in load_experiment_fixture_manifest(MANIFEST_PATH).fixtures:
            with self.subTest(fixture=fixture.fixture_id):
                store = fixture.experimental_source.location.store
                if store not in roots:
                    self.skipTest(f"{fixture.fixture_id}: store {store!r} not configured")
                path = resolve_external_file(fixture.experimental_source, roots)
                dataset = universal_reader.load_universal_modal_file(path, modal_set=fixture.modal_set.name)
                self.assertIs(require_identification_input(dataset).source, ModalInputSource.CURVE_FITTED)


if __name__ == "__main__":
    unittest.main()
