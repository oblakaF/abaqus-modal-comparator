"""SCIENTIFIC-CROSSCHECK-F1: a FE <-> experimental cell whose MAC is undefined is never an assigned mode pair.

A cell can pass the coverage floor (enough measured DOFs) while one of the two shapes is zero on those DOFs, for example
a FE in-plane mode written with U3 = 0 against a U3 scan, or an experimental record with an explicit measured-DOF mask
and a zero vector. ``modal_assurance_criterion`` then returns None and the cell's MAC is NaN. Before the fix the
comparator's frequency-only branch admitted such a cell when |Δf| <= 10 % and the Hungarian assignment always took it,
so the new GUI showed "N admissible pairs" including a pair with MAC NOT_COMPUTED. Now:

- the cell's coverage status is ``UNDEFINED_MAC_COVERAGE_STATUS`` and it is not admissible (reason "mac_unavailable");
- the MAC matrix keeps NaN there (diagnostic, unchanged) and the numerical gates (15 %, MAC 0.5, 10 %) are unchanged;
- pairs whose MAC is defined are unchanged, on the geometry-search path and on the verified frozen-registration path
  of the new GUI.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import modal_core  # noqa: E402
import quality_control  # noqa: E402
import reviewed_core  # noqa: E402
from modal_core import ModalDataset, ModeShape  # noqa: E402
from new_gui import comparison_model as cm  # noqa: E402
import test_new_gui6_workbench as w6  # noqa: E402
from test_g2d1_governed_registration import experimental_dataset  # noqa: E402
from test_new_gui5_registration import experimental_preview, other_set  # noqa: E402
from test_no_pair_diagnostics import SHAPE_X, SHAPE_Y, _mode  # noqa: E402


def _pairs(result):
    return [(int(p.abaqus_mode), int(p.experimental_mode)) for p in result.pairs]


def _candidate(result, fe, exp):
    return next(c for c in result.candidate_diagnostics if (c.abaqus_mode, c.experimental_mode) == (fe, exp))


class GeometrySearchPathTests(unittest.TestCase):
    """reviewed_core.compare_modal_datasets without a registration (the legacy geometry-search path)."""

    def compare(self, abaqus_modes, experimental_modes):
        return reviewed_core.compare_modal_datasets(ModalDataset("Abaqus", Path("model.odb"), abaqus_modes),
                                                    ModalDataset("Experiment", Path("scan.unv"), experimental_modes),
                                                    coordinate_scale_override=1.0)

    def assert_undefined_and_unassigned(self, result, fe, exp):
        self.assertNotIn((fe, exp), _pairs(result))
        candidate = _candidate(result, fe, exp)
        self.assertIsNone(candidate.mac)
        self.assertFalse(candidate.admissible)
        self.assertEqual(candidate.coverage_status, reviewed_core.UNDEFINED_MAC_COVERAGE_STATUS)
        self.assertEqual(candidate.rejection_reasons, ("mac_unavailable",))
        self.assertGreaterEqual(candidate.measured_dof_count, reviewed_core.MINIMUM_COMMON_DOF_COUNT)
        row = list(result.abaqus_mode_numbers).index(fe)
        column = list(result.experimental_mode_numbers).index(exp)
        self.assertTrue(np.isnan(result.mac_matrix[row, column]))  # the diagnostic matrix keeps NaN

    def test_a_zero_fe_shape_on_the_measured_dofs_is_not_paired_by_frequency(self):
        result = self.compare([_mode(7, 100.0, np.zeros(9))], [_mode(1, 104.0, SHAPE_X)])  # |Δf| 3.8 %
        self.assertEqual(result.pairs, [])
        self.assert_undefined_and_unassigned(result, 7, 1)

    def test_b_zero_experimental_shape_with_an_explicit_mask_is_not_paired_by_frequency(self):
        result = self.compare([_mode(7, 100.0, SHAPE_X)], [_mode(1, 104.0, np.zeros(9))])
        self.assertEqual(result.pairs, [])
        self.assert_undefined_and_unassigned(result, 7, 1)

    def test_a_defined_pair_is_unchanged_next_to_an_undefined_cell(self):
        result = self.compare([_mode(7, 100.0, SHAPE_X), _mode(8, 150.0, np.zeros(9)), _mode(9, 200.0, SHAPE_Y)],
                              [_mode(1, 101.0, SHAPE_X), _mode(2, 152.0, SHAPE_Y), _mode(3, 198.0, SHAPE_Y)])
        self.assertEqual(_pairs(result), [(7, 1), (9, 3)])
        self.assertGreater(result.pairs[0].mac, 0.999999)
        self.assertGreater(result.pairs[1].mac, 0.999999)
        self.assert_undefined_and_unassigned(result, 8, 2)

    def test_the_numerical_gates_are_unchanged(self):
        result = self.compare([_mode(7, 100.0, SHAPE_X)], [_mode(1, 101.0, SHAPE_X)])
        gates = result.metadata["admissibility_gates"]
        self.assertEqual((gates["maximum_frequency_error_percent"], gates["minimum_mac"],
                          gates["maximum_frequency_only_error_percent"]), (15.0, 0.5, 10.0))
        self.assertEqual((quality_control.MAX_ACCEPTED_FREQUENCY_ERROR_PERCENT, quality_control.MIN_ACCEPTED_MAC,
                          quality_control.MAX_FREQUENCY_ONLY_ERROR_PERCENT), (15.0, 0.50, 10.0))


def in_plane(dataset: ModalDataset, number: int, frequency: float) -> ModalDataset:
    """FE mode ``number`` as an elastic in-plane shape: U3 = 0 at every node, U1/U2 not rigid; same mesh."""
    modes = []
    for m in dataset.sorted_modes():
        if m.number == number:
            x, y = m.coordinates[:, 0] / 10.0, m.coordinates[:, 1] / 10.0
            vectors = np.zeros_like(m.vectors, dtype=float)
            vectors[:, 0] = np.sin(1.3 * x) * np.cos(0.7 * y) + 0.3 * x * y
            vectors[:, 1] = np.cos(1.1 * x * y) - 0.5 * y ** 2
            m = ModeShape(m.number, frequency, m.node_ids, m.coordinates, vectors)
        modes.append(m)
    return ModalDataset(dataset.source_name, dataset.source_path, modes, metadata=dict(dataset.metadata))


VALID = [(8, 2), (10, 3), (13, 4)]  # the synthetic world's pairs, MAC 1.0 each


class VerifiedNewGuiPathTests(w6._Comparison):
    """The new GUI: the frozen registration verified again, then the comparator (run_compare) and the view."""

    def assert_only_valid_pairs(self, outcome):
        self.assertEqual(outcome.error, "")
        self.assertEqual(outcome.refusal, "")
        self.assertEqual(_pairs(outcome.result), VALID)
        self.assertEqual([p.mac for p in outcome.result.pairs], [1.0, 1.0, 1.0])
        view = outcome.view
        self.assertEqual(view.status, cm.PAIRS_FOUND)
        self.assertIn(": 3 admissible pairs assigned", view.statement)
        self.assertFalse(any(cm.MAC_NOT_COMPUTED in row.cells[6] for row in view.pair_rows))
        self.assertTrue(any(text.startswith("Exp record 1 (mode 1") for text in view.unpaired_experimental))

    def test_0_the_valid_pairs_are_unchanged(self):
        self.assert_only_valid_pairs(self.run_compare())

    def test_a_in_plane_fe_mode_within_10_percent_is_not_shown_as_a_pair(self):
        fe = in_plane(self.fe, 7, 23.0)  # experimental mode 1 is at 24 Hz: |Δf| = 4.2 %
        self.assertGreater(quality_control._rigid_body_residual_fraction(fe.sorted_modes()[0]),
                           quality_control.RIGID_SHAPE_RESIDUAL_THRESHOLD)  # an elastic mode, not excluded as rigid
        fe_prev, exp_prev = self.previews(fe=fe)
        outcome = self.run_compare(fe_prev, exp_prev)
        self.assert_only_valid_pairs(outcome)
        candidate = _candidate(outcome.result, 7, 1)
        self.assertFalse(candidate.admissible)
        self.assertEqual(candidate.coverage_status, reviewed_core.UNDEFINED_MAC_COVERAGE_STATUS)
        self.assertTrue(np.isnan(np.asarray(outcome.result.mac_matrix)[0]).all())  # FE 7 row: NaN, as before
        self.assertIn(cm.MAC_NOT_COMPUTED, outcome.view.mac_cells[0][0])

    def test_b_zero_experimental_vector_with_an_explicit_mask_is_not_shown_as_a_pair(self):
        modes = []
        for m in experimental_dataset(self.unv, self.fe).sorted_modes():
            if m.number == 1:
                mask = np.zeros((len(m.node_ids), 3), dtype=bool)
                mask[:, 2] = True
                m = ModeShape(m.number, m.frequency_hz, m.node_ids, m.coordinates, np.zeros_like(m.vectors),
                              metadata={"measured_dofs": mask.tolist()})
            modes.append(m)
        base = experimental_dataset(self.unv, self.fe)
        exp = ModalDataset(base.source_name, base.source_path, modes, metadata=dict(base.metadata))
        fe_prev, _ = self.previews(fe=w6.with_frequencies(self.fe, {7: 23.0}))
        outcome = self.run_compare(fe_prev, experimental_preview(self.unv, [exp, other_set(self.unv, self.fe)]))
        self.assert_only_valid_pairs(outcome)
        self.assertFalse(_candidate(outcome.result, 7, 1).admissible)

    def test_the_10_percent_boundary_and_a_neighbouring_defined_pair_are_unchanged(self):
        for frequency in (26.5, 70.5):  # +10.4 % from experimental mode 1; next to experimental mode 2 (FE 8, MAC 1)
            with self.subTest(frequency=frequency):
                fe_prev, exp_prev = self.previews(fe=in_plane(self.fe, 7, frequency))
                self.assert_only_valid_pairs(self.run_compare(fe_prev, exp_prev))

    def test_the_comparator_result_equals_the_direct_call(self):
        fe = in_plane(self.fe, 7, 23.0)
        fe_prev, exp_prev = self.previews(fe=fe)
        outcome = self.run_compare(fe_prev, exp_prev)
        direct = modal_core.compare_modal_datasets(fe, experimental_dataset(self.unv, self.fe),
                                                   frozen_registration=self.world.registrations["SP02"])
        self.assertEqual([(p.abaqus_mode, p.experimental_mode, p.mac) for p in outcome.result.pairs],
                         [(p.abaqus_mode, p.experimental_mode, p.mac) for p in direct.pairs])


if __name__ == "__main__":
    unittest.main()
