"""ABM-AUD-4: the FE / experimental modal comparison after an independently stated registration, through the real page.

Synthetic data only, on the ABM-AUD-3 scenario (an FE model 301 mm square, a 17 x 17 scan turned 45 degrees and
confirmed from three dimensioned landmarks). The shapes are cosine products that are exactly orthogonal on the measured
grid, so every expected MAC, mixing angle and subspace value below is computed here, independently of the program: the
FE shape at the FE node nearest to each measured place, the plain MAC formula, and principal angles by QR and SVD.

What must hold: the comparator's pairs are shown as it made them, with the individual MAC; a candidate, a rejection and an
unmatched mode are named as such with the comparator's own reason; a group of close modes shows its permutation, the MAC
of every combination inside it and a separate subspace value, which never changes a pair; and a saved result comes back
identical and stays a snapshot.
"""

from __future__ import annotations

import json
import shutil
import unittest

import numpy as np

import test_abm_aud3_rotated_registration as a3
import test_universal_two_file_analysis as base
import test_working_draft_r2_project as r2

from PySide6.QtWidgets import QLabel

from new_gui import analyze_model as am
from new_gui import analyze_panel
from new_gui import comparison_model as cm
from new_gui import production_window as pw
from new_gui.analyze_panel import DONE
from services import analysis_project as ap
from services import generic_registration as gr

SIDE, MARGIN, GRID = a3.SIDE_MM, a3.MARGIN, a3.GRID
SPAN = SIDE - 2.0 * MARGIN
FIRST = 7  # the first elastic FE mode: modes 1-6 are rigid-body shapes


def shape(a: int, b: int):
    """cos(a pi (i + 1/2) / 17) cos(b pi (j + 1/2) / 17) at grid index (i, j), as a smooth function of the place: the
    DCT-II basis, exactly orthogonal on the 17 x 17 measured grid."""
    def value(points):
        points = np.asarray(points, dtype=float)
        i = (points[:, 0] - MARGIN) / SPAN * (GRID - 1)
        j = (points[:, 1] - MARGIN) / SPAN * (GRID - 1)
        scale = np.sqrt((GRID if a == 0 else GRID / 2.0) * (GRID if b == 0 else GRID / 2.0))  # unit norm on the grid
        return np.cos(a * np.pi * (i + 0.5) / GRID) * np.cos(b * np.pi * (j + 0.5) / GRID) / scale
    return value


def mixed(*terms):
    """A weighted sum of shapes: [(weight, shape), ...]."""
    return lambda points: sum(weight * function(points) for weight, function in terms)


A, B, C, D, E, U1, U2, U3 = (shape(1, 0), shape(0, 1), shape(1, 1), shape(2, 0), shape(0, 2), shape(3, 1), shape(1, 3),
                             shape(4, 2))
PLACES = a3.grid_points()
NODES = a3.fe_points()


def fe_at_places(function, places=PLACES) -> np.ndarray:
    """What the comparator can know of an FE shape: its value at the FE node nearest to each measured place."""
    nearest = [int(np.argmin(np.linalg.norm(NODES - place, axis=1))) for place in places]
    return function(NODES[nearest])


def mac(left, right) -> float:
    left, right = np.asarray(left, dtype=float), np.asarray(right, dtype=float)
    return float((left @ right) ** 2 / ((left @ left) * (right @ right)))


def expected_mac(fe_function, experimental_function, places=PLACES) -> float:
    return mac(fe_at_places(fe_function, places), experimental_function(PLACES))


def expected_subspace(fe_functions, experimental_functions) -> float:
    """The mean squared cosine of the principal angles between the two spans (independent of the service)."""
    q_fe, _ = np.linalg.qr(np.column_stack([fe_at_places(f) for f in fe_functions]))
    q_exp, _ = np.linalg.qr(np.column_stack([f(PLACES) for f in experimental_functions]))
    cosines = np.linalg.svd(q_fe.T @ q_exp, compute_uv=False)
    return float(np.sum(cosines ** 2) / len(fe_functions))


def error_percent(fe_hz: float, experimental_hz: float) -> float:
    return 100.0 * (fe_hz - experimental_hz) / experimental_hz


class _Compared(a3._Turned):
    """``fe`` and ``experimental`` are [(Hz, shape), ...]: FE elastic modes 7, 8, ... and experimental records 1, 2, ..."""

    fe: tuple = ()
    experimental: tuple = ()

    def modes(self):
        nodes = self.nodes()
        points = np.array([n[1:4] for n in nodes])
        rigid = base.rigid_shapes(nodes)
        modes = [(i + 1, 0.0011 + 0.0001 * i, vectors) for i, vectors in enumerate(rigid)]
        for k, (hz, function) in enumerate(self.fe):
            vectors = np.zeros_like(points)
            vectors[:, 2] = function(points)
            modes.append((FIRST + k, hz, vectors))
        return modes

    def scan_file(self, name="turned scan.unv", degrees=45.0, sets=None):
        scan = a3.in_scan_frame(PLACES, degrees)
        nodes = [(k + 1, float(x), float(y), float(z)) for k, (x, y, z) in enumerate(scan)]
        return base.write_unv(self.inputs / name, nodes, tuple(hz for hz, _ in self.experimental), sets,
                              [function(PLACES) for _, function in self.experimental])

    def compared(self, fe, experimental):
        self.fe, self.experimental = tuple(fe), tuple(experimental)
        _window, panel = self.analysed()
        self.confirmed(panel)
        analysis = self.compare(panel)
        self.assertIsNotNone(analysis.comparison, analysis.registration_reason)
        return panel, analysis

    def assert_mac_matrix(self, view, places=PLACES, places_tolerance=0.004):
        """Every FE row against every experimental column, by the independent formula."""
        self.assertEqual(view.mac_fe_modes, tuple(FIRST + k for k in range(len(self.fe))))
        self.assertEqual(view.mac_experimental_modes, tuple(range(1, len(self.experimental) + 1)))
        for row, (_fe_hz, fe_function) in enumerate(self.fe):
            for column, (_hz, experimental_function) in enumerate(self.experimental):
                expected = expected_mac(fe_function, experimental_function, places)
                self.assertAlmostEqual(view.mac_values[row][column], expected, delta=places_tolerance,
                                       msg=f"FE {FIRST + row} / EXP {column + 1}")
                self.assertAlmostEqual(float(view.mac_cells[row][column]), expected, delta=places_tolerance + 0.0006)

    @staticmethod
    def tab_titles(panel) -> list:
        return [panel.comparison_tabs.tabText(index) for index in range(panel.comparison_tabs.count())]

    @staticmethod
    def close_cells(view) -> list:
        return [dict(zip(cm.CLOSE_HEADERS, cells)) for cells in cm.close_group_rows(view)]


CLEAR_FE = ((50.0, A), (80.0, B), (120.0, C), (170.0, D), (230.0, E))
CLEAR_EXP = ((51.0, A), (82.0, B), (123.0, C), (174.0, D), (236.0, E))
CLOSE_FE = ((50.0, A), (110.0, B), (111.0, C), (170.0, D))  # FE 8 and 9 are 1 Hz apart


class ClearCorrespondenceTests(_Compared):
    def test_pairs_mac_and_signed_errors_equal_the_independent_values(self):
        panel, analysis = self.compared(CLEAR_FE, CLEAR_EXP)
        view = analysis.comparison
        self.assertEqual(analysis.status, am.CONFIRMED_COMPARISON)
        self.assertEqual([(row.abaqus_mode, row.experimental_mode) for row in view.pair_rows],
                         [(FIRST + k, k + 1) for k in range(5)])
        for k, row in enumerate(view.pair_rows):
            expected = expected_mac(CLEAR_FE[k][1], CLEAR_EXP[k][1])
            self.assertGreater(expected, 0.99)
            self.assertAlmostEqual(row.mac, expected, delta=0.003)
            self.assertAlmostEqual(row.frequency_error_percent, error_percent(CLEAR_FE[k][0], CLEAR_EXP[k][0]), places=2)
            self.assertLess(row.frequency_error_percent, 0.0)  # FE below the experiment: the sign is kept
        self.assert_mac_matrix(view)
        off_diagonal = [view.mac_values[r][c] for r in range(5) for c in range(5) if r != c]
        self.assertLess(max(off_diagonal), 0.01)

    def test_the_pair_table_holds_identity_error_mac_coverage_points_and_close_modes(self):
        panel, analysis = self.compared(CLEAR_FE, CLEAR_EXP)
        table = panel.tables["pairs"]
        headers = [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
        self.assertEqual(headers, ["FE mode", "FE (Hz)", "Exp record", "Exp mode", "Exp (Hz)", "Error (%)", "MAC",
                                   "Comparator status", "DOF coverage", "Points", "Close modes"])
        first = [table.item(0, c).text() for c in range(table.columnCount())]
        self.assertEqual(first[:6], ["7", "50.0000", "1", "1", f"{float(first[4]):.4f}", "-1.96"])
        self.assertAlmostEqual(float(first[4]), 51.0, places=3)
        self.assertEqual(first[8:], ["100 %", str(GRID * GRID), cm.DASH])
        self.assertEqual(first[7], str(analysis.comparison_result.pairs[0].status))  # the comparator's own word
        mac_table = panel.tables["mac"]
        self.assertEqual([mac_table.horizontalHeaderItem(c).text() for c in range(mac_table.columnCount())],
                         ["FE \\ EXP", "1", "2", "3", "4", "5"])
        self.assertEqual([mac_table.item(r, 0).text() for r in range(mac_table.rowCount())], ["7", "8", "9", "10", "11"])

    def test_every_diagnostic_is_one_tab_away(self):
        panel, analysis = self.compared(CLEAR_FE, CLEAR_EXP)
        self.assertEqual(self.tab_titles(panel), ["Mode pairs", "MAC", "Candidates", "Unmatched modes", "Close modes",
                                                  "Registered points", "Mapping diagnostics", "Line profile"])
        shown = " ".join(label.text() for label in panel.comparison_tabs.findChildren(QLabel))
        self.assertIn(cm.NO_CLOSE_GROUP, shown)
        self.assertIn(cm.CANDIDATE_NOTE, shown)
        self.assertEqual(analysis.comparison.unmatched_fe_rows, ())
        self.assertEqual(analysis.comparison.close_groups, ())

    def test_experimental_record_1_the_first_elastic_mode_and_the_rigid_modes(self):
        panel, analysis = self.compared(CLEAR_FE, CLEAR_EXP)
        view = analysis.comparison
        self.assertEqual(analysis.rigid_modes, (1, 2, 3, 4, 5, 6))
        self.assertEqual(analysis.first_elastic, str(FIRST))
        self.assertEqual([row[0] for row in view.rigid_rows], ["1", "2", "3", "4", "5", "6"])
        self.assertTrue(all(float(row[2]) <= 0.02 for row in view.rigid_rows))  # by shape; every frequency is ~0.001 Hz
        self.assertEqual(panel.tables["rigid"].rowCount(), 6)
        self.assertEqual((view.pair_rows[0].abaqus_mode, view.pair_rows[0].experimental_mode), (FIRST, 1))
        self.assertEqual(view.candidate_rows[0][:2], ("1", "1"))
        self.assertEqual(len(view.candidate_rows), 5)  # no record is dropped
        self.assertTrue(all(row.cells[-1] == cm.AUTO_ID_USE for row in view.pair_rows))  # never an Auto-ID observation

    def test_the_comparators_limits_are_the_existing_ones(self):
        _panel, analysis = self.compared(CLEAR_FE, CLEAR_EXP)
        gates = dict(analysis.comparison.gates)
        self.assertEqual(float(gates["maximum frequency error percent"]), 15.0)
        self.assertEqual(float(gates["minimum mac"]), 0.5)


class CloseModeTests(_Compared):
    def test_two_close_modes_in_swapped_order_are_paired_by_shape_and_named_as_a_permutation(self):
        experimental = ((51.0, A), (112.0, C), (113.0, B), (174.0, D))  # records 2 and 3 hold FE 9's and FE 8's shapes
        panel, analysis = self.compared(CLOSE_FE, experimental)
        view = analysis.comparison
        self.assertEqual([(row.abaqus_mode, row.experimental_mode) for row in view.pair_rows],
                         [(7, 1), (8, 3), (9, 2), (10, 4)])
        self.assert_mac_matrix(view)
        self.assertAlmostEqual(view.pair_rows[1].frequency_error_percent, error_percent(110.0, 113.0), places=2)
        self.assertAlmostEqual(view.pair_rows[2].frequency_error_percent, error_percent(111.0, 112.0), places=2)
        (group,) = self.close_cells(view)
        self.assertEqual(group["Close group"], "FE 8 / 9 (110.0000, 111.0000 Hz); EXP 2 / 3 (112.0000, 113.0000 Hz)")
        self.assertIn("permuted against the frequency order: FE 8 with EXP 3, FE 9 with EXP 2", group["Order in the group"])
        self.assertIn("no mode is renamed", group["Order in the group"])
        value = float(group["Subspace MAC (group)"].split()[0])
        self.assertAlmostEqual(value, expected_subspace((B, C), (C, B)), delta=0.003)
        self.assertGreater(value, 0.99)
        self.assertIn("on 289 shared measured DOFs", group["Subspace MAC (group)"])
        table = panel.tables["pairs"]
        self.assertEqual(table.item(1, 10).text(), "FE 8 / 9; Exp 2 / 3")
        self.assertEqual(view.mac_fe_modes, (7, 8, 9, 10))  # nothing renamed, nothing removed
        self.assertEqual(view.mac_experimental_modes, (1, 2, 3, 4))
        shown = [label.text() for label in panel.close_labels]
        self.assertEqual(len(shown), 1)
        self.assertIn("Subspace MAC (group): ", shown[0])
        self.assertIn(cm.CLOSE_NOTE, " ".join(label.text() for label in panel.comparison_tabs.findChildren(QLabel)))

    def test_mixed_close_modes_keep_their_low_individual_mac_beside_a_high_subspace_value(self):
        """The experiment holds the two FE shapes turned by 30 degrees inside their span: each vector agrees only to
        cos^2 = 0.75, the span agrees fully. The group value is shown, and no pair is raised by it."""
        c, s = np.cos(np.radians(30.0)), np.sin(np.radians(30.0))
        first, second = mixed((c, B), (s, C)), mixed((-s, B), (c, C))
        experimental = ((51.0, A), (112.0, first), (113.0, second), (174.0, D))
        panel, analysis = self.compared(CLOSE_FE, experimental)
        view = analysis.comparison
        pairs = {(row.abaqus_mode, row.experimental_mode): row for row in view.pair_rows}
        self.assertIn((8, 2), pairs)
        self.assertIn((9, 3), pairs)
        for key, fe_function, experimental_function in (((8, 2), B, first), ((9, 3), C, second)):
            expected = expected_mac(fe_function, experimental_function)
            self.assertAlmostEqual(expected, 0.75, delta=0.02)
            self.assertAlmostEqual(pairs[key].mac, expected, delta=0.01)  # a mixed vector is the most sensitive to the
        self.assert_mac_matrix(view, places_tolerance=0.01)  # file's six digits and the nearest-node reading
        (group,) = self.close_cells(view)
        value = float(group["Subspace MAC (group)"].split()[0])
        self.assertAlmostEqual(value, expected_subspace((B, C), (first, second)), delta=0.003)
        self.assertGreater(value, 0.99)
        self.assertEqual(group["Order in the group"], "as the frequency order on both sides")
        self.assertIn("FE 8: EXP 2 0.7", group["MAC inside the group"])
        self.assertIn("EXP 3 0.2", group["MAC inside the group"])  # sin^2 = 0.25: the mixing is visible
        result = analysis.comparison_result
        table = panel.tables["pairs"]
        for position, pair in enumerate(result.pairs):  # the pair rows are the comparator's, word for word
            self.assertEqual(table.item(position, 7).text(), str(pair.status))
            self.assertEqual(table.item(position, 6).text(), f"{pair.mac:.3f}")
        self.assertNotEqual(table.item(1, 6).text(), group["Subspace MAC (group)"].split()[0])
        self.assertNotIn("validated", " ".join(view.close_groups).lower())

    def test_a_close_group_with_poor_subspace_agreement_says_so_in_numbers(self):
        """Each experimental shape of the group is its FE shape plus 80 % of an unrelated one: individual MAC and the
        span both agree to 1 / 1.64 = 0.61."""
        first, second = mixed((1.0, B), (0.8, U1)), mixed((1.0, C), (0.8, U2))
        experimental = ((51.0, A), (112.0, first), (113.0, second), (174.0, D))
        _panel, analysis = self.compared(CLOSE_FE, experimental)
        view = analysis.comparison
        (group,) = self.close_cells(view)
        value = float(group["Subspace MAC (group)"].split()[0])
        expected = expected_subspace((B, C), (first, second))
        self.assertAlmostEqual(expected, 1.0 / 1.64, delta=0.02)
        self.assertAlmostEqual(value, expected, delta=0.004)
        pairs = {(row.abaqus_mode, row.experimental_mode): row.mac for row in view.pair_rows}
        self.assertAlmostEqual(pairs[(8, 2)], expected_mac(B, first), delta=0.004)
        self.assertAlmostEqual(pairs[(9, 3)], expected_mac(C, second), delta=0.004)

    def test_a_group_with_one_assigned_pair_has_no_subspace_value_and_says_why(self):
        experimental = ((51.0, A), (112.0, B), (113.0, U3), (174.0, D))  # record 3 is no FE shape at all
        panel, analysis = self.compared(CLOSE_FE, experimental)
        view = analysis.comparison
        self.assertEqual([(row.abaqus_mode, row.experimental_mode) for row in view.pair_rows], [(7, 1), (8, 2), (10, 4)])
        (group,) = self.close_cells(view)
        self.assertTrue(group["Subspace MAC (group)"].startswith(cm.NOT_AVAILABLE + ": the group holds 1 assigned pair"))
        self.assertIn("without a pair: FE 9, EXP 3", group["Assigned pairs (individual MAC)"])
        self.assertEqual(group["Order in the group"], cm.DASH)
        (fe_row,) = view.unmatched_fe_rows
        self.assertEqual(fe_row[:2], ("9", "111.0000"))
        self.assertIn("EXP 2 (112.0000 Hz): error -0.89 %", fe_row[2])  # nearest in frequency is not its shape
        self.assertIn("rejected: MAC below the comparator's limit", fe_row[2])
        self.assertEqual(fe_row[4], "No admissible counterpart: every candidate fails a limit of the comparator.")
        (shown,) = [label.text() for label in panel.unmatched_labels["fe"]]
        self.assertTrue(shown.startswith("FE mode 9 (111.0000 Hz): No admissible counterpart"))
        self.assertIn("Nearest in frequency: EXP 2 (112.0000 Hz): error -0.89 %", shown)
        self.assertIn("Highest MAC: ", shown)
        self.assertTrue(panel.unmatched_labels["experimental"][0].text().startswith("EXP mode 3 (113.0000 Hz)"))

    def test_the_diagnostics_change_nothing_in_the_comparators_result(self):
        experimental = ((51.0, A), (112.0, C), (113.0, B), (174.0, D))
        _panel, analysis = self.compared(CLOSE_FE, experimental)
        result = analysis.comparison_result
        before = [(p.abaqus_mode, p.experimental_mode, p.mac, p.status) for p in result.pairs]
        matrix = np.array(result.mac_matrix, dtype=float)
        lines = cm.close_group_lines(result)
        self.assertEqual(lines, cm.close_group_lines(result))
        self.assertEqual([(p.abaqus_mode, p.experimental_mode, p.mac, p.status) for p in result.pairs], before)
        np.testing.assert_array_equal(np.asarray(result.mac_matrix, dtype=float), matrix)


class RejectionTests(_Compared):
    FE = ((50.0, A), (80.0, B), (120.0, C), (170.0, D), (400.0, E))  # FE 11 has record 5's shape, 69 % too high
    EXP = ((51.0, U1), (82.0, B), (123.0, C), (174.0, D), (236.0, E))  # record 1 is at FE 7's frequency, another shape

    def test_good_frequency_with_poor_mac_is_a_rejection_named_mac(self):
        _panel, analysis = self.compared(self.FE, self.EXP)
        view = analysis.comparison
        self.assertNotIn(1, [row.experimental_mode for row in view.pair_rows])
        self.assertLess(expected_mac(A, U1), 0.01)
        fe_row = next(row for row in view.unmatched_fe_rows if row[0] == "7")
        self.assertIn("EXP 1 (", fe_row[2])
        self.assertIn(f"error {error_percent(50.0, 51.0):+.2f} %", fe_row[2])
        self.assertIn("rejected: MAC below the comparator's limit", fe_row[2])
        self.assertNotIn("frequency difference", fe_row[2])
        exp_row = next(row for row in view.unmatched_experimental_rows if row[0] == "1")
        self.assertIn("FE 7 (50.0000 Hz)", exp_row[2])
        self.assert_mac_matrix(view)

    def test_good_mac_with_an_unacceptable_frequency_difference_is_a_rejection_named_frequency(self):
        panel, analysis = self.compared(self.FE, self.EXP)
        view = analysis.comparison
        self.assertNotIn(11, [row.abaqus_mode for row in view.pair_rows])
        candidate = next(row for row in view.candidate_rows if row[1] == "5")
        self.assertEqual(candidate[3], "11")  # its highest-MAC FE mode
        self.assertAlmostEqual(float(candidate[5]), expected_mac(E, E), delta=0.004)
        self.assertAlmostEqual(float(candidate[6]), error_percent(400.0, 236.0), places=1)
        self.assertEqual(candidate[8:], ("no", "frequency", "no"))
        fe_row = next(row for row in view.unmatched_fe_rows if row[0] == "11")
        self.assertIn("rejected: frequency difference above the comparator's limit", fe_row[3])
        self.assertNotIn("MAC below", fe_row[3])
        table = panel.tables["candidates"]
        self.assertEqual(table.rowCount(), 5)
        self.assertEqual([table.horizontalHeaderItem(c).text() for c in range(table.columnCount())],
                         list(cm.CANDIDATE_HEADERS))

    def test_a_candidate_refused_for_coverage_is_named_coverage(self):
        """The comparator's coverage verdict is worded apart from frequency and MAC (its limits are not changed here)."""
        from types import SimpleNamespace

        candidate = SimpleNamespace(abaqus_mode=7, experimental_mode=1, abaqus_frequency_hz=50.0,
                                    experimental_frequency_hz=51.0, frequency_error_percent=-1.96, mac=0.97,
                                    admissible=False, rejection_reasons=("coverage",))
        text = cm._counterpart(candidate, "fe")
        self.assertEqual(text, "EXP 1 (51.0000 Hz): error -1.96 %, MAC 0.970; rejected: insufficient measured-DOF, point "
                               "or spatial coverage")
        missing = SimpleNamespace(**{**vars(candidate), "mac": None, "rejection_reasons": ("mac_unavailable",)})
        self.assertIn("MAC NOT_COMPUTED; rejected: MAC not available on the measured DOFs", cm._counterpart(missing, "exp"))
        self.assertEqual(len(set(cm.REASON_WORDS.values())), 4)  # four different failures, four different sentences

    def test_no_admissible_pair_is_a_completed_comparison(self):
        fe = ((50.0, A), (80.0, B), (120.0, C))
        experimental = ((51.0, U1), (82.0, U2), (123.0, U3))
        panel, analysis = self.compared(fe, experimental)
        view = analysis.comparison
        self.assertEqual(view.status, cm.NO_PAIR)
        self.assertEqual(view.pair_rows, ())
        self.assertEqual(panel.state, DONE)
        self.assertNotIn("pairs", panel.tables)
        self.assertEqual(self.tab_titles(panel)[:4], ["MAC", "Candidates", "Unmatched modes", "Close modes"])
        self.assertIn(cm.NO_PAIR_TEXT, " ".join(label.text() for label in panel.comparison_box.findChildren(QLabel)))
        self.assert_mac_matrix(view, places_tolerance=0.004)
        self.assertEqual([row[0] for row in view.unmatched_fe_rows], ["7", "8", "9"])
        self.assertEqual([row[0] for row in view.unmatched_experimental_rows], ["1", "2", "3"])  # record 1 is not dropped
        self.assertEqual(analysis.first_elastic, str(FIRST))
        self.assertTrue(all(row[8] == "no" for row in view.candidate_rows))
        self.saved(panel)  # a result without a pair is saved and reopened like any other
        _second, again = self.reopened()
        self.assertEqual(again.analysis.comparison, view)

    def test_a_record_without_the_stated_measured_dof_stops_before_any_comparison(self):
        self.fe = ((50.0, A), (80.0, B), (120.0, C))
        self.experimental = ((51.0, A), (82.0, lambda points: 0.0 * points[:, 0]), (123.0, C))
        _window, panel = self.analysed()
        dialog = self.checked(panel)
        self.assertEqual(dialog.proposal.status, gr.REGISTRATION_REQUIRED)
        self.assertIn("Experimental z is stated as measured, but 2 of 3 records hold it", dialog.problem_label.text())
        self.assertFalse(dialog.save_button.isEnabled())
        self.assertIsNone(panel.analysis.comparison)
        self.assertIsNone(panel.comparison_tabs)

    def test_a_wrong_but_confirmed_registration_is_compared_as_stated_and_never_improved(self):
        """The landmarks are stated a quarter turn off. The comparator maps the points as stated; the expected MAC
        is computed here on that same wrong mapping. No better orientation is looked for."""
        self.fe, self.experimental = CLEAR_FE, CLEAR_EXP
        _window, panel = self.analysed()
        dialog = panel.open_registration()
        self.state_evidence(dialog, panel)
        centre = np.array([SIDE / 2.0, SIDE / 2.0, 0.0])
        quarter = a3.turn(90.0)
        stated = (PLACES - centre) @ quarter.T + centre  # where each measured point is (wrongly) said to lie
        dialog.landmarks.setPlainText("\n".join(
            f"{row + 1}, {stated[row][0]:.6f}, {stated[row][1]:.6f}, 0" for row in a3.CORNERS))
        self.assertTrue(dialog.check())
        self.wait(panel)
        self.assertTrue(dialog.proposal.proposed, dialog.proposal.problems)
        dialog.review_box.setChecked(True)
        self.draft_path = self.root / "wrong.json"
        dialog.save_draft(str(self.draft_path))
        self.wait(panel)
        self.sign(self.confirmation_dialog(dialog, panel))
        self.wait(panel)
        analysis = self.compare(panel)
        view = analysis.comparison
        self.assertIsNotNone(view, analysis.registration_reason)
        self.assert_mac_matrix(view, places=stated, places_tolerance=0.006)
        self.assertLess(expected_mac(A, A, stated), 0.01)  # FE "one half wave along X" read along Y
        self.assertNotIn((7, 1), [(row.abaqus_mode, row.experimental_mode) for row in view.pair_rows])
        self.assertLess(len(view.pair_rows), 5)


class RegistrationIsAPrerequisiteTests(_Compared):
    def test_a_reviewed_and_saved_draft_gives_no_mac_and_no_pair(self):
        self.fe, self.experimental = CLEAR_FE, CLEAR_EXP
        _window, panel = self.analysed()
        dialog = self.checked(panel)
        dialog.review_box.setChecked(True)
        self.assertTrue(dialog.save_draft(str(self.root / "draft.json")))
        self.wait(panel)
        self.assertEqual(panel.analysis.status, am.REGISTRATION_REQUIRED)
        self.assertIsNone(panel.analysis.comparison)
        self.assertIsNone(panel.comparison_tabs)
        for key in ("pairs", "mac", "candidates", "rigid"):
            self.assertNotIn(key, panel.tables)
        self.assertTrue(panel.tables["nearest"].rowCount())  # the frequency-only diagnostic stays

    def test_a_file_changed_after_the_confirmation_leaves_the_frequency_only_result(self):
        self.fe, self.experimental = CLOSE_FE, ((51.0, A), (112.0, C), (113.0, B), (174.0, D))
        _window, panel = self.analysed()
        self.confirmed(panel)
        self.exp_path.write_bytes(self.exp_path.read_bytes() + b"\n")
        self.assertTrue(panel.compare_confirmed())
        self.wait(panel)
        self.assertIsNone(getattr(panel.analysis, "comparison", None))
        self.assertIsNone(panel.comparison_tabs)
        self.assertNotIn("mac", panel.tables)


class SavedComparisonTests(_Compared):
    EXP = ((51.0, U1), (112.0, C), (113.0, B), (174.0, D))  # a permuted close pair and an unmatched record

    def test_a_saved_comparison_reopens_with_the_same_identities_values_and_diagnostics(self):
        panel, analysis = self.compared(CLOSE_FE, self.EXP)
        view = analysis.comparison
        self.assertTrue(view.unmatched_fe_rows and cm.close_group_rows(view))
        shown = [label.text() for label in panel.close_labels]
        self.saved(panel)
        _second, again = self.reopened()
        saved = again.analysis.comparison
        self.assertEqual(saved, view)  # every field, the MAC numbers digit for digit
        self.assertEqual(saved.mac_values, view.mac_values)
        self.assertEqual(saved.close_groups, view.close_groups)
        self.assertEqual(saved.unmatched_fe_rows, view.unmatched_fe_rows)
        self.assertEqual(saved.candidate_rows, view.candidate_rows)
        self.assertEqual([label.text() for label in again.close_labels], shown)
        self.assertEqual({side: [label.text() for label in labels] for side, labels in again.unmatched_labels.items()},
                         {side: [label.text() for label in labels] for side, labels in panel.unmatched_labels.items()})
        self.assertEqual(self.tab_titles(again)[:5], ["Mode pairs", "MAC", "Candidates", "Unmatched modes", "Close modes"])
        document, _images = ap.read_project(self.project)
        stored = document["comparison"]
        self.assertEqual(stored["mac_fe_modes"], [7, 8, 9, 10])
        self.assertEqual(stored["mac_experimental_modes"], [1, 2, 3, 4])
        self.assertEqual([(p["abaqus_mode"], p["experimental_mode"]) for p in stored["pair_rows"]], [(8, 3), (9, 2), (10, 4)])
        self.assertEqual(stored["mac_values"], [list(row) for row in view.mac_values])
        self.assertTrue(any(line.startswith(cm.CLOSE_PREFIX) for line in stored["close_groups"]))
        self.assertEqual(document["sources"]["experimental"]["sha256"], base.sha(self.exp_path))
        self.assertEqual(document["registration"]["kind"], ap.KIND_CONFIRMED)

    def test_the_reopened_comparison_is_a_snapshot_and_never_becomes_live_by_itself(self):
        panel, analysis = self.compared(CLOSE_FE, self.EXP)
        self.saved(panel)
        _second, again = self.reopened()
        self.assertIsNotNone(again.snapshot)
        self.assertIsNone(again.inputs)
        self.assertIsNone(again.confirmation)
        self.assertIsNone(again.analysis.comparison_result)  # the comparator's result is not in a project
        self.assertEqual(again.status_label.property("state"), "chosen")
        self.assertIsNone(again.compare_button)
        self.assertFalse(again.compare_confirmed())
        self.assertFalse(again.analyze())
        self.check(again)
        self.assertTrue(again.analyze())
        self.wait(again)
        self.assertEqual(again.analysis.status, am.REGISTRATION_REQUIRED)  # a fresh result needs the registration again
        self.assertIsNone(again.analysis.comparison)
        self.assertIsNone(again.comparison_tabs)

    def test_a_project_saved_before_these_diagnostics_still_opens_and_says_what_it_lacks(self):
        panel, analysis = self.compared(CLOSE_FE, self.EXP)
        self.saved(panel)
        old = self.root / "earlier.mcproj"
        shutil.copy(self.project, old)

        def as_before(document):
            comparison = document["comparison"]
            comparison["close_groups"] = [line for line in comparison["close_groups"] if not line.startswith(cm.CLOSE_PREFIX)]
            for key in ("unmatched_fe_rows", "unmatched_experimental_rows"):
                comparison[key] = [row[:2] for row in comparison[key]]
            for pair in comparison["pair_rows"]:
                self.assertEqual(len(pair["cells"]), len(cm.PAIR_HEADERS))

        r2.rewrite(old, change=as_before)
        _second, again = self.reopened(old)
        self.assertEqual(again.state, DONE, again.message.text())
        view = again.analysis.comparison
        self.assertEqual(view.pair_rows, analysis.comparison.pair_rows)
        self.assertEqual(again.close_labels, [])
        shown = " ".join(label.text() for label in again.comparison_tabs.findChildren(QLabel))
        self.assertIn(cm.CLOSE_NOT_SAVED, shown)
        self.assertIn("FE modes 8 / 9", shown)
        self.assertEqual([label.text() for label in again.unmatched_labels["fe"]], ["FE mode 7 (50.0000 Hz)"])


class ServiceTests(unittest.TestCase):
    def test_the_view_adds_no_threshold_and_forms_no_pair(self):
        source = (a3.reg1.ROOT / "src" / "new_gui" / "comparison_model.py").read_text(encoding="utf-8")
        body = source[source.index("def close_group_lines"):source.index("def close_group_rows")]
        for word in ("ModePairResult(", ".pairs.append", ".pairs =", "pair.mac =", "pair.status =", ">= 0.", "<= 0.", "> 0.", "< 0."):
            self.assertNotIn(word, body)
        self.assertIn("modal_cluster_service", source)

    def test_the_subspace_measure_is_the_existing_service_and_ignores_order_and_mixing(self):
        from services import modal_cluster_service as clusters

        first, second = B(PLACES), C(PLACES)
        turned = np.column_stack((0.6 * first + 0.8 * second, -0.8 * first + 0.6 * second))
        self.assertAlmostEqual(clusters.subspace_mac(np.column_stack((first, second)), turned), 1.0, places=9)
        self.assertAlmostEqual(clusters.subspace_mac(np.column_stack((first, second)),
                                                     np.column_stack((second, first))), 1.0, places=9)
        self.assertAlmostEqual(mac(first, turned[:, 0]), 0.36, places=9)  # the individual vectors do not agree


if __name__ == "__main__":
    unittest.main()
