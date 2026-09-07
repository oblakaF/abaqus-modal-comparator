import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app import analysis_completion_status, write_no_pair_diagnostics
from modal_core import (
    ModalDataset,
    ModeShape,
    compare_modal_datasets as compare_with_quality_control,
)
from reviewed_core import compare_modal_datasets


def _grid():
    x, y = np.meshgrid(np.array([0.0, 1.0, 3.0]), np.array([0.0, 2.0, 5.0]))
    coordinates = np.column_stack((x.ravel(), y.ravel(), np.zeros(x.size)))
    return np.arange(1, 10), coordinates


def _mode(number, frequency, values, *, measured_points=9):
    node_ids, coordinates = _grid()
    vectors = np.zeros((9, 3), dtype=float)
    vectors[:, 2] = np.asarray(values, dtype=float)
    mode = ModeShape(number, frequency, node_ids, coordinates, vectors)
    mode.measured_dofs = np.zeros((9, 3), dtype=bool)
    mode.measured_dofs[:measured_points, 2] = True
    return mode


_RNG = np.random.default_rng(812)
SHAPE_X = _RNG.normal(size=9)
SHAPE_X -= np.mean(SHAPE_X)
SHAPE_Y = _RNG.normal(size=9)
SHAPE_Y -= np.mean(SHAPE_Y)
SHAPE_Y -= SHAPE_X * np.dot(SHAPE_X, SHAPE_Y) / np.dot(SHAPE_X, SHAPE_X)


class NoPairDiagnosticTests(unittest.TestCase):
    def test_normal_successful_pairing_is_unchanged(self):
        abaqus = ModalDataset(
            "Abaqus",
            Path("model.odb"),
            [_mode(7, 100.0, SHAPE_X), _mode(8, 200.0, SHAPE_Y)],
        )
        experiment = ModalDataset(
            "Experiment",
            Path("scan.unv"),
            [_mode(1, 101.0, SHAPE_X), _mode(2, 198.0, SHAPE_Y)],
        )

        result = compare_modal_datasets(
            abaqus, experiment, coordinate_scale_override=1.0
        )

        self.assertEqual(
            [(pair.abaqus_mode, pair.experimental_mode) for pair in result.pairs],
            [(7, 1), (8, 2)],
        )
        self.assertEqual(result.diagnostic_state, "comparison")

    def test_zero_pairs_returns_diagnostic_result_with_full_inputs_and_matrices(self):
        abaqus = ModalDataset(
            "Abaqus", Path("model.odb"), [_mode(7, 100.0, SHAPE_X)]
        )
        experiment = ModalDataset(
            "Experiment", Path("scan.unv"), [_mode(1, 140.0, SHAPE_X)]
        )

        result = compare_modal_datasets(
            abaqus, experiment, coordinate_scale_override=1.0
        )

        self.assertEqual(result.pairs, [])
        self.assertEqual(result.diagnostic_state, "no_accepted_pairs")
        self.assertEqual(result.mac_matrix.shape, (1, 1))
        self.assertEqual(result.frequency_error_matrix.shape, (1, 1))
        self.assertGreater(result.mac_matrix[0, 0], 0.999)
        self.assertAlmostEqual(result.frequency_error_matrix[0, 0], -28.57142857)
        self.assertEqual(result.abaqus.modes[0].number, 7)
        self.assertIs(result.experimental, experiment)

    def test_rejection_reasons_cover_frequency_mac_coverage_and_unavailable_mac(self):
        zero = np.zeros(9)
        abaqus = ModalDataset(
            "Abaqus", Path("model.odb"), [_mode(7, 100.0, SHAPE_X)]
        )
        experiment = ModalDataset(
            "Experiment",
            Path("scan.unv"),
            [
                _mode(1, 130.0, SHAPE_X),
                _mode(2, 100.0, SHAPE_Y),
                _mode(3, 100.0, SHAPE_X, measured_points=2),
                _mode(4, 112.0, zero),
            ],
        )

        result = compare_modal_datasets(
            abaqus, experiment, coordinate_scale_override=1.0
        )
        candidates = {
            candidate.experimental_mode: candidate
            for candidate in result.candidate_diagnostics
        }

        self.assertEqual(result.pairs, [])
        self.assertEqual(candidates[1].rejection_reasons, ("frequency",))
        self.assertEqual(candidates[2].rejection_reasons, ("mac",))
        self.assertEqual(candidates[3].rejection_reasons, ("coverage",))
        self.assertEqual(candidates[4].rejection_reasons, ("mac_unavailable",))
        self.assertTrue(candidates[1].mac_gate_passed)
        self.assertFalse(candidates[2].mac_gate_passed)
        self.assertFalse(candidates[3].coverage_gate_passed)
        self.assertIsNone(candidates[4].mac_gate_passed)

    def test_nearest_frequency_and_best_mac_summaries_are_diagnostic_only(self):
        abaqus = ModalDataset(
            "Abaqus",
            Path("model.odb"),
            [_mode(7, 100.0, SHAPE_X), _mode(8, 200.0, SHAPE_Y)],
        )
        experiment = ModalDataset(
            "Experiment",
            Path("scan.unv"),
            [_mode(1, 400.0, SHAPE_Y), _mode(2, 500.0, SHAPE_X)],
        )

        result = compare_modal_datasets(
            abaqus, experiment, coordinate_scale_override=1.0
        )
        summaries = result.diagnostic_summaries

        self.assertEqual(result.pairs, [])
        self.assertEqual(
            [(item.abaqus_mode, item.experimental_mode) for item in summaries["nearest_frequency_by_abaqus"]],
            [(7, 1), (8, 1)],
        )
        self.assertEqual(
            [(item.abaqus_mode, item.experimental_mode) for item in summaries["best_mac_by_abaqus"]],
            [(7, 2), (8, 1)],
        )
        self.assertEqual(
            [(item.abaqus_mode, item.experimental_mode) for item in summaries["nearest_frequency_by_experimental"]],
            [(8, 1), (8, 2)],
        )
        self.assertEqual(
            [(item.abaqus_mode, item.experimental_mode) for item in summaries["best_mac_by_experimental"]],
            [(8, 1), (7, 2)],
        )
        self.assertFalse(any(candidate.admissible for candidate in result.candidate_diagnostics))

    def test_gui_completion_classifies_zero_pairs_as_diagnostic_not_crash(self):
        # This is the production service facade called by runtime_hardening._worker,
        # including the quality-control layer used by the GUI.
        result = compare_with_quality_control(
            ModalDataset("Abaqus", Path("model.odb"), [_mode(7, 100.0, SHAPE_X)]),
            ModalDataset("Experiment", Path("scan.unv"), [_mode(1, 140.0, SHAPE_X)]),
            coordinate_scale_override=1.0,
        )

        self.assertEqual(
            analysis_completion_status(result),
            "Diagnostic result: 0 admissible pairs",
        )

    def test_no_pair_workspace_outputs_are_machine_readable_and_deterministic(self):
        result = compare_modal_datasets(
            ModalDataset("Abaqus", Path("model.odb"), [_mode(7, 100.0, SHAPE_X)]),
            ModalDataset("Experiment", Path("scan.unv"), [_mode(1, 140.0, SHAPE_X)]),
            coordinate_scale_override=1.0,
        )

        with tempfile.TemporaryDirectory() as directory:
            json_path, csv_path = write_no_pair_diagnostics(result, Path(directory))
            payload = json.loads(json_path.read_text(encoding="utf-8"))

            self.assertEqual(payload["diagnostic_state"], "no_accepted_pairs")
            self.assertEqual(payload["accepted_pair_count"], 0)
            self.assertEqual(len(payload["candidates"]), 1)
            self.assertEqual(payload["mac_matrix"], [[1.0]])
            self.assertIn("frequency", payload["candidates"][0]["rejection_reasons"])
            self.assertIn("rejection_reasons", csv_path.read_text(encoding="utf-8"))

    def test_rejected_candidates_never_appear_in_result_pairs(self):
        result = compare_modal_datasets(
            ModalDataset("Abaqus", Path("model.odb"), [_mode(7, 100.0, SHAPE_X)]),
            ModalDataset("Experiment", Path("scan.unv"), [_mode(1, 130.0, SHAPE_X)]),
            coordinate_scale_override=1.0,
        )

        self.assertEqual(result.pairs, [])
        self.assertEqual(len(result.candidate_diagnostics), 1)
        self.assertFalse(result.candidate_diagnostics[0].admissible)


if __name__ == "__main__":
    unittest.main()
