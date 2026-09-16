from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import universal_reader
from modal_core import ModeShape


def _geometry():
    return {
        "type": 2411,
        "node_nums": np.array([1, 2]),
        "x": np.array([0.0, 1.0]),
        "y": np.array([0.0, 0.0]),
        "z": np.array([0.0, 0.0]),
    }


def _mode(processing_name, number, frequency):
    return {
        "type": 55,
        "id1": processing_name,
        "id2": "Synthetic PolyMAX result",
        "id3": "2026-09-10",
        "id4": f"MODE NO. {number}, FREQUENCY {frequency}(Hz)",
        "id5": "1 3 8 13",
        "analysis_type": 3,
        "mode_n": number,
        "freq": frequency,
        "node_nums": np.array([1, 2]),
        "r1": np.zeros(2),
        "r2": np.zeros(2),
        "r3": np.array([1.0, -1.0]),
    }


def _residual(processing_name, side, frequency):
    return {
        "type": 55,
        "id1": f"{processing_name}   Residuals {side} {frequency:.4f} Hz",
        "analysis_type": 5,
        "freq_step_n": 99,
        "freq": frequency,
        "node_nums": np.array([1, 2]),
        "r1": np.zeros(2),
        "r2": np.zeros(2),
        "r3": np.array([0.5, 0.5]),
    }


def _mode_2414(number, frequency, analysis_type=3, name="Modal result"):
    return {
        "type": 2414,
        "analysis_dataset_name": name,
        "dataset_location": 1,
        "analysis_type": analysis_type,
        "data_characteristic": 2,
        "result_type": 8,
        "mode_number": number,
        "frequency": frequency,
        "node_nums": np.array([1, 2]),
        "x": np.zeros(2),
        "y": np.zeros(2),
        "z": np.array([1.0, -1.0]),
    }


class PolymaxModalSetTests(unittest.TestCase):
    def _load(self, datasets, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.unv"
            path.write_text("fixture", encoding="utf-8")
            with patch.object(universal_reader, "_read_universal_datasets", return_value=datasets):
                return universal_reader.load_universal_modal_file(path, **kwargs)

    def test_single_unnamed_dataset_55_set_remains_implicit(self):
        result = self._load([_geometry(), _mode("", 1, 10.0)])
        self.assertEqual([mode.frequency_hz for mode in result.modes], [10.0])
        self.assertEqual(result.metadata["modal_set_key"], "dataset-55")
        self.assertEqual(result.metadata["modal_set_name"], "Dataset 55 modal set")
        self.assertEqual(result.metadata["modal_set_selection_policy"], "implicit_single_set")

    def test_multiple_sets_are_discovered_without_concatenation(self):
        datasets = [
            _geometry(),
            _mode("Processing_nice", 1, 10.0),
            _mode("Processing", 1, 10.0),
            _mode("Processing", 2, 20.0),
        ]
        sets = universal_reader._discover_dataset_55_modal_sets(
            datasets, universal_reader._read_geometry(datasets)[0]
        )
        self.assertEqual([item.key for item in sets], ["processing-nice", "processing"])
        self.assertEqual([len(item.modes) for item in sets], [1, 2])
        with self.assertRaisesRegex(ValueError, "select one explicitly"):
            self._load(datasets)

    def test_public_discovery_api_returns_project_owned_sets(self):
        datasets = [_geometry(), _mode("Processing", 1, 10.0)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.unv"
            path.write_text("fixture", encoding="utf-8")
            with patch.object(
                universal_reader, "_read_universal_datasets", return_value=datasets
            ):
                sets = universal_reader.discover_experimental_modal_sets(path)
        self.assertEqual(len(sets), 1)
        self.assertIsInstance(sets[0], universal_reader.ExperimentalModalSet)
        self.assertEqual(sets[0].source_dataset, 55)
        self.assertEqual(sets[0].record_indices, [1])

    def test_residual_records_are_excluded_by_id1_semantics_not_frequency(self):
        datasets = [
            _geometry(),
            _mode("Processing", 1, 30.0),
            _residual("Processing", "below", 30.0),
            _residual("Processing", "above", 500.0),
        ]
        result = self._load(datasets, modal_set="processing")
        self.assertEqual([mode.frequency_hz for mode in result.modes], [30.0])
        self.assertEqual(result.metadata["excluded_residual_count"], 2)
        self.assertEqual(result.metadata["excluded_residual_record_indices"], [2, 3])
        self.assertTrue(all("Residuals" in value for value in result.metadata["excluded_residual_labels"]))

        audits = result.metadata["modal_record_classifications"]
        self.assertEqual(
            [item["classification"] for item in audits],
            ["physical", "residual", "residual"],
        )
        self.assertEqual(audits[0]["evidence"]["analysis_type"], 3)
        self.assertEqual(audits[1]["evidence"]["analysis_type"], 5)
        self.assertTrue(audits[1]["evidence"]["id1_residual_marker"])

    def test_all_verified_modal_analysis_types_are_physical(self):
        datasets = [_geometry()]
        for number, analysis_type in enumerate((2, 3, 7), start=1):
            mode = _mode("Processing", number, 10.0 * number)
            mode["analysis_type"] = analysis_type
            datasets.append(mode)

        result = self._load(datasets, modal_set="processing")

        self.assertEqual([mode.frequency_hz for mode in result.modes], [10.0, 20.0, 30.0])
        self.assertEqual(
            [mode.metadata["record_classification"] for mode in result.modes],
            ["physical", "physical", "physical"],
        )

    def test_dataset_55_structure_handles_label_variants_and_disagreement(self):
        lower = _residual("Processing", "below", 12.0)
        lower["id1"] = "  Processing    ReSiDuAlS    BeLoW   12.0 Hz  "
        mislabeled_physical = _mode(
            "Processing Residuals above 999.0 Hz", 2, 20.0
        )
        datasets = [
            _geometry(),
            _mode("Processing", 1, 12.0),
            lower,
        ]

        result = self._load(datasets, modal_set="processing")

        self.assertEqual([mode.frequency_hz for mode in result.modes], [12.0])
        self.assertEqual(result.metadata["excluded_residual_record_indices"], [2])

        disagreement_sets = universal_reader._discover_dataset_55_modal_sets(
            [_geometry(), mislabeled_physical],
            universal_reader._read_geometry([_geometry()])[0],
        )
        self.assertEqual(len(disagreement_sets), 1)
        disagreement = disagreement_sets[0]
        self.assertEqual(
            disagreement.processing_name,
            "Processing Residuals above 999.0 Hz",
        )
        self.assertEqual(disagreement.metadata["ambiguous_record_indices"], [1])
        self.assertEqual(
            disagreement.modes[0].metadata["record_classification"], "ambiguous"
        )
        self.assertTrue(
            any(
                "preserved as ambiguous" in warning
                for warning in disagreement.metadata["import_warnings"]
            )
        )

    def test_physical_processing_name_containing_residual_is_not_dropped(self):
        result = self._load(
            [_geometry(), _mode("Residual review set", 1, 42.0)],
            modal_set="residual-review-set",
        )
        self.assertEqual([mode.frequency_hz for mode in result.modes], [42.0])
        self.assertEqual(result.metadata["excluded_residual_count"], 0)
        self.assertEqual(result.modes[0].metadata["record_classification"], "physical")

    def test_unlabeled_frequency_response_record_is_structurally_non_modal(self):
        non_modal = _residual("Processing", "below", 30.0)
        non_modal["id1"] = "Processing"
        result = self._load(
            [_geometry(), _mode("Processing", 1, 30.0), non_modal],
            modal_set="processing",
        )
        self.assertEqual([mode.frequency_hz for mode in result.modes], [30.0])
        self.assertEqual(result.metadata["excluded_residual_record_indices"], [])
        self.assertEqual(result.metadata["excluded_non_modal_record_indices"], [2])
        audit = result.metadata["modal_record_classifications"][1]
        self.assertEqual(audit["classification"], "non_modal")
        self.assertFalse(audit["evidence"]["id1_residual_marker"])

    def test_dataset_2414_uses_structure_and_preserves_unknown_records(self):
        physical = _mode_2414(1, 25.0, analysis_type=3)
        non_modal = _mode_2414(2, 25.0, analysis_type=5, name="Frequency response")
        ambiguous = _mode_2414(3, 35.0, analysis_type=None, name="Legacy modal result")
        result = self._load([_geometry(), physical, non_modal, ambiguous])

        self.assertEqual([mode.frequency_hz for mode in result.modes], [25.0, 35.0])
        self.assertEqual(
            [mode.metadata["record_classification"] for mode in result.modes],
            ["physical", "ambiguous"],
        )
        self.assertEqual(result.metadata["excluded_dataset_2414_record_indices"], [2])
        self.assertEqual(result.metadata["ambiguous_dataset_2414_record_indices"], [3])
        audits = result.metadata["dataset_2414_record_classifications"]
        self.assertEqual(
            [item["classification"] for item in audits],
            ["physical", "non_modal", "ambiguous"],
        )
        self.assertTrue(
            any("preserved as ambiguous" in warning for warning in result.metadata["import_warnings"])
        )

    def test_explicit_selection_accepts_key_or_processing_name(self):
        datasets = [
            _geometry(),
            _mode("Processing_nice", 1, 11.0),
            _mode("Processing", 1, 22.0),
        ]
        by_key = self._load(datasets, modal_set="processing-nice")
        by_name = self._load(datasets, modal_set="Processing")
        self.assertEqual([mode.frequency_hz for mode in by_key.modes], [11.0])
        self.assertEqual([mode.frequency_hz for mode in by_name.modes], [22.0])
        self.assertEqual(by_key.metadata["modal_set_selection_policy"], "explicit")

    def test_invalid_selection_lists_available_sets(self):
        datasets = [_geometry(), _mode("First", 1, 10.0), _mode("Second", 1, 20.0)]
        with self.assertRaisesRegex(ValueError, "Available sets: First.*Second"):
            self._load(datasets, modal_set="missing")

    def test_selected_modes_retain_record_and_set_provenance(self):
        result = self._load([_geometry(), _mode("Processing", 1, 12.5)], modal_set="processing")
        metadata = result.modes[0].metadata
        self.assertEqual(metadata["source"], "curve-fitted dataset 55")
        self.assertEqual(metadata["modal_set_key"], "processing")
        self.assertEqual(metadata["modal_set_name"], "Processing")
        self.assertEqual(metadata["dataset_55_record_index"], 1)
        self.assertEqual(metadata["dataset_55_record_id"], "dataset55:1")
        self.assertEqual(metadata["source_frequency_hz"], 12.5)

    def test_dataset_58_is_diagnostic_only_when_dataset_55_is_selected(self):
        datasets = [_geometry(), _mode("Processing", 1, 12.5), {"type": 58}]
        diagnostics = {
            "dataset_58_role": "diagnostic_only",
            "dataset_58_diagnostic_available": True,
            "dataset_58_derived_mode_count": 0,
            "_frf_frequency_hz": [1.0, 2.0],
            "_frf_indicator": [3.0, 4.0],
            "_frf_mean_coherence": [0.8, 0.9],
        }
        with patch.object(
            universal_reader,
            "_frf_diagnostic_metadata",
            return_value=diagnostics,
        ) as parse_frf:
            result = self._load(datasets, modal_set="processing")
        parse_frf.assert_called_once()
        self.assertEqual([mode.frequency_hz for mode in result.modes], [12.5])
        self.assertEqual(result.metadata["mode_source"], "curve-fitted dataset 55")
        self.assertEqual(result.metadata["dataset_58_role"], "diagnostic_only")
        self.assertTrue(result.metadata["dataset_58_diagnostic_available"])
        self.assertEqual(result.metadata["_frf_frequency_hz"], [1.0, 2.0])

    def test_dataset_58_diagnostic_arrays_are_actually_parsed(self):
        axis = np.linspace(1.0, 5.0, 5)
        datasets = [_geometry(), _mode("Processing", 1, 12.5)]
        for node in (1, 2):
            datasets.append(
                {
                    "type": 58,
                    "func_type": 4,
                    "id2": "H1 Displacement / Force",
                    "rsp_node": node,
                    "rsp_dir": 3,
                    "ref_node": 1,
                    "ref_dir": 3,
                    "x": axis,
                    "data": np.asarray([node * value for value in axis], dtype=complex),
                }
            )
            datasets.append(
                {
                    "type": 58,
                    "func_type": 6,
                    "id2": "Coherence",
                    "rsp_node": node,
                    "rsp_dir": 3,
                    "ref_node": 1,
                    "ref_dir": 3,
                    "x": axis,
                    "data": np.full(5, 0.9),
                }
            )
        result = self._load(datasets, modal_set="processing")
        self.assertEqual([mode.frequency_hz for mode in result.modes], [12.5])
        self.assertEqual(result.metadata["frf_channel_count"], 2)
        self.assertEqual(result.metadata["coherence_channel_count"], 2)
        self.assertEqual(result.metadata["coherence_status"], "computed")
        self.assertEqual(result.metadata["_frf_frequency_hz"], axis.tolist())
        self.assertEqual(result.metadata["dataset_58_derived_mode_count"], 0)

    def test_no_dataset_55_keeps_dataset_58_fallback(self):
        datasets = [_geometry(), {"type": 58}]
        fallback_mode = ModeShape(
            1,
            40.0,
            np.array([1, 2], dtype=object),
            np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
            np.array([[0.0, 0.0, 1.0], [0.0, 0.0, -1.0]]),
        )
        with patch.object(
            universal_reader,
            "_modes_from_frf_datasets",
            return_value=([fallback_mode], {"mode_source": "dataset 58 FRF peak extraction"}),
        ):
            result = self._load(
                datasets,
                target_frequencies=[39.0],
                target_count=1,
            )
        self.assertEqual([mode.frequency_hz for mode in result.modes], [40.0])
        self.assertEqual(result.metadata["mode_source"], "dataset 58 FRF peak extraction")

    def test_fe_targets_do_not_affect_dataset_55_discovery_or_selection(self):
        datasets = [
            _geometry(),
            _mode("First", 1, 10.0),
            _mode("Second", 1, 20.0),
        ]
        first = self._load(
            datasets,
            modal_set="first",
            target_frequencies=[9999.0],
            target_count=100,
        )
        second = self._load(
            datasets,
            modal_set="first",
            target_frequencies=[0.1],
            target_count=1,
        )
        self.assertEqual([mode.frequency_hz for mode in first.modes], [10.0])
        self.assertEqual([mode.frequency_hz for mode in second.modes], [10.0])


if __name__ == "__main__":
    unittest.main()
