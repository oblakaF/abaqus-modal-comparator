"""GUI-UX-R1: the four pages, the candidate review, MAC / Points and Materials. Synthetic data; Qt ``offscreen``; no Abaqus."""

from __future__ import annotations

import json
from pathlib import Path
import threading
from unittest import mock
import unittest
import zipfile

import numpy as np

import test_universal_reg3_confirmed as reg3
import test_universal_two_file_analysis as base
import test_working_draft_r2_project as r2

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QWheelEvent
from PySide6.QtWidgets import QApplication, QComboBox, QGridLayout, QPushButton, QScrollArea, QWidget

from modal_core import ModalDataset, ModeShape
from new_gui import analyze_model as am
from new_gui import analyze_summary as asm
from new_gui import mac_points_model as mp
from new_gui import materials_workspace_model as mw
from new_gui import production_window as pw
from new_gui import review_model as rv
from new_gui import review_panel as rp
from new_gui import shape_model as sm
from new_gui.shape_panel import ImageActions, ImageView
from new_gui.workspace_state import EXPERIMENTAL, FE
from services import analysis_project as ap
from services import modal_data_viewer as viewer

WANTED_HEADERS = ("Row", "EXP mode", "EXP frequency (Hz)", "Selected FE mode", "Selected FE frequency (Hz)", "Δf (%)",
                  "Nearest FE mode (automatic)")


def cells(table) -> list:
    return [[table.item(r, c).text() if table.item(r, c) else "" for c in range(table.columnCount())]
            for r in range(table.rowCount())]


def wheel(widget, delta=-120) -> QWheelEvent:
    event = QWheelEvent(QPointF(5, 5), QPointF(widget.mapToGlobal(QPoint(5, 5))), QPoint(0, 0), QPoint(0, delta),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, event)
    return event


class _Stub:
    """The fields of an analysis the review state reads."""

    def __init__(self, nearest, fe, experimental=()):
        self.nearest_rows, self.fe_rows, self.experimental_rows = nearest, fe, experimental


FE_ROWS = (("1", "0.0010", "rigid-body"), ("7", "95.0000", "elastic"), ("8", "105.0000", "elastic"), ("9", "210.0000", "elastic"))
NEAREST = (("EXP1", "1", "100.0000", "7", "95.0000", "-5.00", "8", "105.0000", "+5.00", "—"),
           ("EXP2", "2", "102.0000", "8", "105.0000", "+2.94", "7", "95.0000", "-6.86", "—"),
           ("EXP3", "3", "200.0000", "9", "210.0000", "+5.00", "8", "105.0000", "-47.50", "—"))


class ReviewStateTests(unittest.TestCase):
    def state(self):
        return rv.ReviewState(_Stub(NEAREST, FE_ROWS))

    def test_the_columns_are_in_the_required_order(self):
        self.assertEqual(rv.HEADERS, WANTED_HEADERS)
        self.assertEqual(self.state().row(0).cells(), ("1", "1", "100.0000", "7", "95.0000", "-5.00", "7"))

    def test_the_automatic_cells_are_the_services_own(self):
        state = self.state()
        for source, row in zip(NEAREST, state.rows()):
            self.assertEqual((row.exp_mode, row.selected_mode, row.selected_text, row.difference_text, row.nearest_mode),
                             (source[1], source[3], source[4], source[5], source[3]))
            self.assertFalse(row.manual)

    def test_a_manual_choice_changes_only_the_selection_and_uses_the_convention(self):
        state = self.state()
        state.assign(0, "9", allow_duplicate=True)
        row = state.row(0)
        self.assertEqual((row.selected_mode, row.selected_text, row.difference_text), ("9", "210.0000", "+110.00"))
        self.assertEqual(row.nearest_mode, "7")  # the automatic suggestion stays
        self.assertEqual(row.exp_mode, "1")
        self.assertTrue(row.manual)
        self.assertEqual(row.origin, rv.USER_HYPOTHESIS)
        self.assertIn(rv.USER_HYPOTHESIS, state.hypothesis_text())

    def test_full_precision_frequencies_are_used_when_known(self):
        state = rv.ReviewState(_Stub(NEAREST, FE_ROWS), {"8": 105.5}, {"EXP1": 100.5})
        state.assign(0, "8", allow_duplicate=True)
        self.assertEqual(state.row(0).difference_text, f"{100.0 * (105.5 - 100.5) / 100.5:+.2f}")

    def test_swap_inspects_the_opposite_order_and_reset_restores_the_automatic_one(self):
        state = self.state()
        self.assertTrue(state.swap(0, 1))
        self.assertEqual((state.selected(0), state.selected(1)), ("8", "7"))
        self.assertEqual(state.row(0).difference_text, "+5.00")
        self.assertEqual(state.row(1).difference_text, "-6.86")
        self.assertEqual(state.duplicate_warning(), "")
        state.reset(0)
        self.assertFalse(state.row(0).manual)
        self.assertTrue(state.row(1).manual)
        state.reset()
        self.assertEqual(state.manual, {})
        self.assertEqual(state.rows(), self.state().rows())

    def test_the_same_fe_mode_twice_needs_a_decision_and_gives_a_warning(self):
        state = self.state()
        with self.assertRaises(rv.DuplicateSelection) as caught:
            state.assign(0, "8")
        self.assertEqual(caught.exception.rows, (1,))
        self.assertFalse(state.row(0).manual)
        state.assign(0, "8", allow_duplicate=True)
        self.assertEqual(state.duplicate_warning(), "Not one-to-one: FE 8 (rows 1, 2).")
        self.assertEqual(state.conflicts(), {"8": [1, 2]})

    def test_an_automatic_duplicate_is_also_stated(self):
        nearest = (NEAREST[0], ("EXP2", "2", "96.0000", "7", "95.0000", "-1.04", "8", "105.0000", "+9.38", "—"))
        self.assertIn("FE 7 (rows 1, 2)", rv.ReviewState(_Stub(nearest, FE_ROWS)).duplicate_warning())

    def test_a_rigid_body_mode_cannot_be_selected(self):
        state = self.state()
        self.assertEqual([number for number, _text in state.options], ["7", "8", "9"])
        with self.assertRaises(ValueError):
            state.assign(0, "1")

    def test_the_plots_draw_stored_frequencies(self):
        state = self.state()
        state.assign(0, "9", allow_duplicate=True)
        for image in (rv.frequency_plot(state, 0), rv.difference_plot(state, 0)):
            self.assertTrue(image.startswith(b"\x89PNG"))

    def test_the_selected_row_changes_both_plots(self):
        state = self.state()
        self.assertEqual(rv.selected_point(state, 1)[0].row, 1)
        self.assertIsNone(rv.selected_point(state, None))
        self.assertNotEqual(rv.frequency_plot(state, 0), rv.frequency_plot(state, 1))
        self.assertNotEqual(rv.difference_plot(state, 0), rv.difference_plot(state, 1))


def _pair(index, fe, exp, mac, error, verdict):
    """A pair row as ``comparison_model.comparison_view`` words it (15 cells, the verdict last)."""
    from new_gui import comparison_model as cm

    cells = (str(fe), f"{100.0 + fe:.4f}", f"EXP{exp}", str(exp), "100.0000", f"{error:+.2f}",
             "MAC NOT COMPUTED (no shape)" if mac is None else f"{mac:.3f}", "Good match", "12", "1.00", "12", "kept", "—",
             "not used", verdict)
    return cm.PairRow(index, fe, exp, mac, error, cells)


class _Compared(_Stub):
    """An analysis as the SP-13 result reads: EXP 4 is nearest in frequency to FE 11 and paired with FE 10."""

    registration_outcome = ""

    def __init__(self, comparison=True, outcome="", experimental=()):
        from new_gui import comparison_model as cm
        from types import SimpleNamespace

        fe = tuple((str(n), f"{100.0 + n:.4f}", "elastic") for n in (8, 9, 10, 11, 12))
        self.verdicts = {
            3: f"{cm.AMBIGUOUS_VERDICT}: paired with FE 8, MAC 0.528, error -10.09 %, but also admissible: FE 9.",
            4: f"{cm.GROUP_VERDICT}: paired with FE 10, MAC 0.958, error -9.05 % (Good match) inside the close group "
               f"FE 10 / 11; EXP 4 / 5. {cm.GROUP_UNRESOLVED}.",
            6: f"{cm.REJECTED_VERDICT}: no FE mode passes the comparator's limits (highest MAC: FE 12, MAC 0.210).",
            7: f"{cm.CONFIRMED_VERDICT}: FE 12, MAC 0.981, error -2.76 %; the only admissible FE mode (Excellent match).",
            8: f"{cm.AMBIGUOUS_VERDICT}: paired with FE 9 by frequency only; the shape is not compared."}
        nearest = tuple((f"EXP{i + 1}", str(exp), "100.0000", str(near), f"{100.0 + near:.4f}", "+1.00", "9", "109.0000",
                         "+9.00", "—", self.verdicts[exp] if comparison else cm.INSUFFICIENT_TEXT)
                        for i, (exp, near) in enumerate(((3, 8), (4, 11), (6, 12), (7, 12), (8, 9))))
        super().__init__(nearest, fe, experimental)
        self.registration_outcome = outcome
        pairs = (_pair(0, 8, 3, 0.5278996171862161, -10.086449352786078, self.verdicts[3]),
                 _pair(1, 10, 4, 0.9584584247911996, -9.054748027603976, self.verdicts[4]),
                 _pair(2, 12, 7, 0.981, -2.76, self.verdicts[7]), _pair(3, 9, 8, None, 0.5, self.verdicts[8]))
        self.comparison = SimpleNamespace(pair_rows=pairs) if comparison else None


class PairClarityTests(unittest.TestCase):
    """PREVIEW-01-REVIEW-PAIR-CLARITY-01: the frequency candidate and the comparator's pair of a record are said apart."""

    def said(self, analysis, row, saved=False, manual=None):
        state = rv.ReviewState(analysis)
        if manual:
            state.assign(row, manual, allow_duplicate=True)
        return rv.row_statements(analysis, state, row, saved), state

    def test_the_nearest_fe_candidate_and_the_assigned_pair_are_two_statements(self):
        analysis = _Compared()
        said, _state = self.said(analysis, 1)  # EXP 4: nearest in frequency FE 11, paired by the comparator with FE 10
        self.assertTrue(said.candidate.startswith("Frequency-based FE candidate for EXP 4: FE 11 (111.0000 Hz, Δf +1.00 %)"))
        self.assertIn("automatic nearest frequency", said.candidate)
        self.assertIn("Not a mode pair.", said.candidate)
        self.assertNotIn("FE 10", said.candidate)
        self.assertTrue(said.pair.startswith("Comparator-assigned FE pair for EXP 4: FE 10 (110.0000 Hz, error -9.05 %, "
                                             "MAC 0.958)."))
        self.assertIn("Not the frequency-based candidate (FE 11).", said.pair)
        self.assertEqual((said.pair_mode, said.differs), ("10", True))
        same, _state = self.said(analysis, 0)  # EXP 3: the candidate and the pair are the same FE mode
        self.assertEqual((same.pair_mode, same.differs), ("8", False))
        self.assertNotIn("Not the frequency-based candidate", same.pair)

    def test_group_level_ambiguous_and_confirmed_verdicts_stay_distinct(self):
        from new_gui import comparison_model as cm

        analysis = _Compared()
        wanted = {0: (cm.AMBIGUOUS_VERDICT, "not a confirmed correspondence"),
                  1: (cm.GROUP_VERDICT, "a group of close modes; the individual mode is not identified"),
                  3: (cm.CONFIRMED_VERDICT, "confirmed for the registration used")}
        for row, (word, gloss) in wanted.items():
            said, _state = self.said(analysis, row)
            self.assertEqual(said.verdict, word)
            self.assertIn(f"Verdict: {word} ({gloss}", said.pair)
            for other, _gloss in wanted.values():
                if other != word:
                    self.assertNotIn(other, said.pair, row)
            self.assertEqual(said.detail, analysis.verdicts[int(analysis.nearest_rows[row][1])])  # the verdict as worded
        self.assertNotIn("confirmed for the registration", self.said(analysis, 1)[0].pair)
        self.assertNotIn("confirmed for the registration", self.said(analysis, 0)[0].pair)
        unscored, _state = self.said(analysis, 4)  # a pair without a MAC says so in the comparison's own words
        self.assertIn("MAC NOT COMPUTED (no shape)).", unscored.pair)
        self.assertNotIn("MAC MAC", unscored.pair)

    def test_a_record_without_a_pair_says_that_no_pair_was_assigned(self):
        from new_gui import comparison_model as cm

        said, _state = self.said(_Compared(), 2)  # EXP 6: nearest FE 12, which the comparator gave to EXP 7
        self.assertTrue(said.pair.startswith("Comparator-assigned FE pair for EXP 6: none. The comparator assigned no FE "
                                             "mode to this record."))
        self.assertIn(f"Verdict: {cm.REJECTED_VERDICT}", said.pair)
        self.assertIsNone(said.pair_mode)
        self.assertFalse(said.differs)
        self.assertNotIn("FE 12", said.pair)  # the candidate's FE mode is not offered as a pair
        self.assertIn("FE 12", said.candidate)

    def test_without_a_registration_no_pair_is_shown(self):
        from new_gui import analyze_model as analyze

        cases = ((_Compared(False), rv.NO_PAIR_REASONS[rv.STATUS_UNREGISTERED]),
                 (_Compared(False, "failed"), rv.NO_PAIR_REASONS[rv.STATUS_FAILED]),
                 (_Compared(False, analyze.PROVISIONAL, (("EXP1", "3", "100.0", sm.PROVISIONAL_TEXT),)),
                  rv.NO_PAIR_REASONS[rv.STATUS_FRF_PEAKS]))
        for analysis, reason in cases:
            for row in range(len(analysis.nearest_rows)):
                said, _state = self.said(analysis, row)
                exp = analysis.nearest_rows[row][1]
                self.assertEqual(said.pair, f"Comparator-assigned FE pair for EXP {exp}: not available. {reason}")
                self.assertIsNone(said.pair_mode)
                self.assertEqual((said.verdict, said.detail, said.differs), ("", "", False))
                self.assertNotIn("FE ", said.pair.split(":", 1)[1])  # no FE mode is named as a pair
                self.assertTrue(said.candidate.startswith(f"Frequency-based FE candidate for EXP {exp}: FE "))

    def test_a_manual_candidate_does_not_change_the_comparator_pair(self):
        analysis = _Compared()
        pairs = analysis.comparison.pair_rows
        automatic, _state = self.said(analysis, 1)
        manual, state = self.said(analysis, 1, manual="9")
        self.assertIn("FE 9 (109.0000 Hz, Δf +9.00 %), your manual choice (USER_REVIEW_HYPOTHESIS)", manual.candidate)
        self.assertIn("automatic nearest: FE 11", manual.candidate)
        self.assertIn("it changes no comparator pair", manual.candidate)
        self.assertEqual((manual.pair_mode, manual.verdict, manual.detail),
                         (automatic.pair_mode, automatic.verdict, automatic.detail))
        self.assertEqual(manual.pair.replace("(FE 9)", "(FE 11)"), automatic.pair)  # only the candidate it names differs
        chosen, state = self.said(analysis, 1, manual="10")  # choosing the paired mode by hand: still two statements
        self.assertFalse(chosen.differs)
        self.assertIn("your manual choice", chosen.candidate)
        state.reset(1)
        self.assertEqual(rv.row_statements(analysis, state, 1), automatic)
        self.assertIs(analysis.comparison.pair_rows, pairs)
        self.assertEqual([(p.abaqus_mode, p.experimental_mode, p.mac) for p in pairs],
                         [(8, 3, 0.5278996171862161), (10, 4, 0.9584584247911996), (12, 7, 0.981), (9, 8, None)])

    def test_a_stored_comparison_is_told_from_a_fresh_one(self):
        analysis = _Compared()
        for row in range(len(analysis.nearest_rows)):
            fresh, _state = self.said(analysis, row)
            stored, _state = self.said(analysis, row, saved=True)
            self.assertTrue(fresh.pair.endswith(rv.FRESH_ORIGIN))
            self.assertTrue(stored.pair.endswith(rv.STORED_ORIGIN))
            self.assertEqual(stored.pair[:-len(rv.STORED_ORIGIN)], fresh.pair[:-len(rv.FRESH_ORIGIN)])
            self.assertEqual(stored.candidate, fresh.candidate)
        self.assertIn("source files were not read in this session", rv.STORED_ORIGIN)
        without, _state = self.said(_Compared(False), 0, saved=True)
        self.assertTrue(without.pair.endswith(rv.STORED_NO_COMPARISON))
        self.assertIn("not available", without.pair)

    def test_no_row_no_result_and_an_older_saved_result_are_handled(self):
        analysis = _Compared()
        state = rv.ReviewState(analysis)
        for index in (None, -1, len(state)):
            self.assertIsNone(rv.row_statements(analysis, state, index))
        self.assertIsNone(rv.row_statements(None, state, 0))
        self.assertIsNone(rv.row_statements(analysis, None, 0))
        analysis.nearest_rows = tuple(row[:10] for row in analysis.nearest_rows)  # saved before the verdicts were kept
        analysis.comparison.pair_rows = tuple(rp_row.__class__(rp_row.index, rp_row.abaqus_mode, rp_row.experimental_mode,
                                                               rp_row.mac, rp_row.frequency_error_percent, rp_row.cells[:14])
                                              for rp_row in analysis.comparison.pair_rows)
        old = rv.ReviewState(analysis)
        self.assertIn(f"FE 10 (110.0000 Hz, error -9.05 %, MAC 0.958). {rv.NO_VERDICT}", rv.row_statements(analysis, old, 1).pair)
        self.assertIn(f"none. The comparator assigned no FE mode to this record. {rv.NO_VERDICT}",
                      rv.row_statements(analysis, old, 2).pair)
        for text in (rv.SELECT_A_ROW, rv.FRESH_ORIGIN, rv.STORED_ORIGIN, rv.STORED_NO_COMPARISON, rv.NO_VERDICT,
                     *rv.NO_PAIR_REASONS.values(), *rv.VERDICT_GLOSS.values()):
            self.assertTrue(text.isascii(), text)  # English only

    def test_the_one_line_form_keeps_the_candidate_the_pair_the_mac_the_verdict_and_the_origin(self):
        """PREVIEW-01-REVIEW-PAIR-CLARITY-01-F1: what the page shows on one line; the full statements are unchanged."""
        analysis = _Compared()
        wanted = {0: ("Frequency candidate: FE 8 (nearest)", "Comparator pair: FE 8, MAC 0.528, AMBIGUOUS"),
                  1: ("Frequency candidate: FE 11 (nearest)", "Comparator pair: FE 10, MAC 0.958, GROUP_LEVEL_ONLY"),
                  2: ("Frequency candidate: FE 12 (nearest)", "Comparator pair: none (REJECTED)"),
                  3: ("Frequency candidate: FE 12 (nearest)", "Comparator pair: FE 12, MAC 0.981, CONFIRMED"),
                  4: ("Frequency candidate: FE 9 (nearest)", "Comparator pair: FE 9, MAC NOT COMPUTED (no shape), AMBIGUOUS")}
        words = []
        for row, (candidate, pair) in wanted.items():
            fresh, _state = self.said(analysis, row)
            stored, _state = self.said(analysis, row, saved=True)
            self.assertEqual((fresh.candidate_short, stored.candidate_short), (candidate, candidate))
            self.assertEqual(fresh.pair_short, f"{pair} \u00b7 fresh result")
            self.assertEqual(stored.pair_short, f"{pair} \u00b7 saved snapshot")
            words.append(pair.rstrip(")").split()[-1].lstrip("("))
            self.assertEqual(fresh.verdict, rv.VERDICT_PREFIX + words[-1])  # the full word stays in the full statement
            self.assertIn(fresh.verdict, fresh.pair)
        self.assertEqual(sorted(set(words)), ["AMBIGUOUS", "CONFIRMED", "GROUP_LEVEL_ONLY", "REJECTED"])  # none merged
        manual, _state = self.said(analysis, 1, manual="9")
        self.assertEqual(manual.candidate_short, "Frequency candidate: FE 9 (manual choice; nearest FE 11)")
        self.assertEqual(manual.pair_short, wanted[1][1] + " \u00b7 fresh result")  # the pair is not the person's to change
        for unregistered in (_Compared(False), _Compared(False, "failed")):
            none, _state = self.said(unregistered, 1, saved=True)
            self.assertEqual(none.pair_short, "Comparator pair: not available")  # no FE mode is named as a pair
            self.assertEqual(none.candidate_short, "Frequency candidate: FE 11 (nearest)")
        analysis.nearest_rows = tuple(row[:10] for row in analysis.nearest_rows)  # saved before the verdicts were kept
        analysis.comparison.pair_rows = tuple(cm_row.__class__(cm_row.index, cm_row.abaqus_mode, cm_row.experimental_mode,
                                                               cm_row.mac, cm_row.frequency_error_percent, cm_row.cells[:14])
                                              for cm_row in analysis.comparison.pair_rows)
        old = rv.row_statements(analysis, rv.ReviewState(analysis), 1, True)
        self.assertEqual(old.pair_short, "Comparator pair: FE 10, MAC 0.958, no verdict stored \u00b7 saved snapshot")


class FrfTests(unittest.TestCase):
    def test_no_frf_data_gives_no_curve(self):
        dataset = ModalDataset("EXP", Path("x.unv"), [], metadata={"mode_source": "dataset 55"})
        self.assertIsNone(rv.frf_series(dataset))
        self.assertIsNone(rv.frf_series(None))
        self.assertIsNone(rv.frf_series(ModalDataset("EXP", Path("x.unv"), [], metadata={
            "_frf_frequency_hz": [1.0, 2.0], "_frf_indicator": [1.0]})))

    def test_read_frf_data_is_drawn_as_read(self):
        dataset = ModalDataset("EXP", Path("x.unv"), [], metadata={
            "_frf_frequency_hz": [1.0, 2.0, 3.0], "_frf_indicator": [0.5, 2.0, 0.1], "_frf_mean_coherence": [0.9, 0.95, 0.8]})
        frequency, indicator, coherence = rv.frf_series(dataset)
        self.assertEqual(frequency.tolist(), [1.0, 2.0, 3.0])
        self.assertEqual(indicator.tolist(), [0.5, 2.0, 0.1])
        records = (("EXP 1", 2.0), ("EXP 2", 3.0))
        peaks = rv.frf_plot((frequency, indicator, coherence), records, 0, True)
        self.assertTrue(peaks.startswith(b"\x89PNG"))
        self.assertNotEqual(peaks, rv.frf_plot((frequency, indicator, coherence), records, 1, True))
        self.assertNotEqual(peaks, rv.frf_plot((frequency, indicator, coherence), records, 0, False))
        self.assertTrue(rv.frf_plot((frequency, indicator, None)).startswith(b"\x89PNG"))

    def test_spread_labels_keep_their_order_and_gap_and_stay_near(self):
        positions = [10.0, 10.5, 11.0, 50.0, 100.0]
        places = rv.spread_labels(positions, 4.0, 0.0, 120.0)
        self.assertEqual(places, sorted(places))
        self.assertTrue(all(b - a >= 4.0 - 1e-9 for a, b in zip(places, places[1:])))
        self.assertEqual(places[3:], [50.0, 100.0])  # a label with room stays at its record
        self.assertAlmostEqual(places[1], 10.5)
        self.assertEqual(rv.spread_labels([], 4.0, 0.0, 1.0), [])

    def test_spread_labels_stay_inside_the_axis_in_input_order(self):
        places = rv.spread_labels([9.9, 0.1, 10.0, 0.0], 3.0, 0.0, 10.0)
        self.assertTrue(all(0.0 <= place <= 10.0 for place in places))
        self.assertLess(places[3], places[1])
        self.assertLess(places[0], places[2])
        ordered = sorted(places)
        self.assertTrue(all(b - a >= 3.0 - 1e-9 for a, b in zip(ordered, ordered[1:])))

    def test_close_frf_labels_do_not_overlap_and_the_data_stay_as_read(self):
        # the frequencies of the real file where the labels ran together
        hz = (8.75, 15.3125, 33.4375, 55.3125, 68.125, 71.875, 116.9, 144.7, 149.1, 158.8, 169.4, 180.9, 200.6, 213.4, 275.9,
              282.5, 294.7, 318.4, 326.2, 333.8)
        frequency = np.linspace(0.0, 400.0, 1601)
        indicator = 1.0 + np.sin(frequency / 7.0) ** 2
        coherence = np.full_like(frequency, 0.9)
        records = tuple((f"EXP {i + 1}", value) for i, value in enumerate(hz))
        kept = indicator.copy()
        figure = rv.frf_figure((frequency, indicator, coherence), records, 5, True)
        figure.canvas.draw()
        renderer = figure.canvas.get_renderer()
        axis = figure.axes[0]
        labels = axis.texts  # ABM-UX5: each other record carries its number only; the selected one its name and frequency
        others = [i for i in range(len(records)) if i != 5]
        self.assertEqual([t.get_text() for t in labels], [str(i + 1) for i in others] + [f"EXP 6: {hz[5]:.2f} Hz"])
        boxes = sorted((t.get_window_extent(renderer) for t in labels[:-1]), key=lambda box: box.x0)
        for left, right in zip(boxes, boxes[1:]):
            self.assertLessEqual(left.x1, right.x0 + 0.5)
        self.assertEqual(labels[-1].get_weight(), "bold")
        for label, index in zip(labels, others + [5]):
            self.assertEqual(label.xy[0], hz[index])  # each leader ends at the record's own frequency
        self.assertEqual([round(float(c.get_offsets()[0][0]), 6) for c in axis.collections], [round(v, 6) for v in hz])
        curve = axis.lines[0]
        np.testing.assert_array_equal(curve.get_xdata(), frequency)
        np.testing.assert_array_almost_equal(curve.get_ydata(), indicator / indicator.max())
        np.testing.assert_array_equal(figure.axes[1].lines[0].get_ydata(), coherence)
        np.testing.assert_array_equal(indicator, kept)

    def test_what_is_missing_is_named(self):
        self.assertEqual(rv.frf_missing(None, True), rv.FRF_NEEDS_SOURCE)
        self.assertEqual(rv.frf_missing(ModalDataset("EXP", Path("x"), [], metadata={"dataset_types": [15, 55]}), False), rv.FRF_NOT_IN_FILE)
        self.assertEqual(rv.frf_missing(ModalDataset("EXP", Path("x"), [], metadata={"dataset_types": [58]}), False), rv.FRF_NOT_USABLE)


class DisplayGridTests(unittest.TestCase):
    """The artifact: a fixed 220-cell grid finer than the mesh left most cells empty, drawn as a dotted field."""

    @staticmethod
    def regular(count=101, pitch=3.0):
        x, y = np.meshgrid(np.arange(count) * pitch, np.arange(count) * pitch)
        return x.ravel(), y.ravel()

    def test_the_fixed_grid_reproduces_the_holes(self):
        x, y = self.regular()
        count, _, _ = np.histogram2d(x, y, bins=(viewer.DISPLAY_GRID_CELLS, viewer.DISPLAY_GRID_CELLS))
        self.assertGreater(viewer.display_hole_fraction(count), 0.5)

    def test_the_grid_follows_the_node_spacing(self):
        x, y = self.regular()
        cells = viewer.display_cells(x, y)
        self.assertLess(cells, 101)
        count, _, _ = np.histogram2d(x, y, bins=(cells, cells))
        self.assertEqual(viewer.display_hole_fraction(count), 0.0)

    def test_a_cell_just_under_the_pitch_leaves_no_stripes_at_the_same_places_in_any_mode(self):
        # the real sandwich: 3 mm skin nodes, and 2.948 mm cells left whole empty rows in every picture
        x, y = self.regular(171, 3.0)
        count, _, _ = np.histogram2d(x, y, bins=(173, 173))
        self.assertGreater(viewer.display_hole_fraction(count), 0.0)
        cells = viewer.display_cells(x, y)
        count, _, _ = np.histogram2d(x, y, bins=(cells, cells))
        self.assertEqual(int((count == 0).sum()), 0)
        for shift in (20.0, 40.0, 75.0):
            image, _extent = viewer._binned(x, y, np.sin(x / shift) * np.cos(y / shift), cells)
            self.assertTrue(np.isfinite(image).all())

    def test_runs_of_two_and_three_empty_cells_count_as_gaps(self):
        for gap in (1, 2, 3):
            count = np.ones((12, 12))
            count[4:4 + gap, 5] = 0
            self.assertGreater(viewer.display_hole_fraction(count), 0.0, gap)
        count = np.ones((20, 20))
        count[5:15, 5:15] = 0  # a real hole
        self.assertEqual(viewer.display_hole_fraction(count), 0.0)

    def test_every_cell_value_is_a_mean_of_real_nodes_and_a_cut_out_stays_blank(self):
        x, y = self.regular()
        keep = ~((x > 100) & (x < 200) & (y > 100) & (y < 200))
        x, y = x[keep], y[keep]
        values = np.sin(x / 40.0) + y / 300.0
        cells = viewer.display_cells(x, y)
        image, _extent = viewer._binned(x, y, values, cells)
        self.assertTrue(np.isnan(image[cells // 2, cells // 2]))  # no value invented inside the cut-out
        finite = image[np.isfinite(image)]
        self.assertGreaterEqual(finite.min(), values.min())
        self.assertLessEqual(finite.max(), values.max())

    def test_a_large_regular_mode_is_drawn_and_states_the_grid(self):
        x, y = self.regular()
        points = np.column_stack([x, y, np.zeros_like(x)])
        vectors = np.zeros_like(points)
        vectors[:, 2] = np.sin(x / 40.0)
        with mock.patch("matplotlib.figure.Figure.savefig", autospec=True) as save:
            with mock.patch.object(viewer.Path, "mkdir"):
                viewer.render_mode(ModeShape(7, 58.1, np.arange(len(x)), points, vectors), viewer.FE, "normal", Path("x.png"), "t")
        figure = save.call_args.args[0]
        self.assertIn("mean per display cell", figure.axes[0].get_xlabel())
        self.assertIn("empty cells blank", figure.axes[0].get_xlabel())
        self.assertNotIn("through the depth", figure.axes[0].get_xlabel())


class OrientationTests(unittest.TestCase):
    points = np.array([[10.0, 1.0, 5.0], [20.0, 1.0, 5.0], [10.0, 4.0, 5.0], [20.0, 4.0, 5.5]])

    def test_source_axes_keep_the_coordinates_and_name_them(self):
        kept = self.points.copy()
        x, y, first, second = viewer.display_coordinates(self.points, viewer.DisplayView("source"))
        self.assertEqual((first, second), ("X", "Y"))
        self.assertEqual(x.tolist(), self.points[:, 0].tolist())
        self.assertEqual(y.tolist(), self.points[:, 1].tolist())
        np.testing.assert_array_equal(self.points, kept)

    def test_each_source_plane_can_be_chosen(self):
        for plane, names in (("xy", ("X", "Y")), ("xz", ("X", "Z")), ("yz", ("Y", "Z"))):
            self.assertEqual(viewer.display_coordinates(self.points, viewer.DisplayView(plane))[2:], names)

    def test_rotation_and_mirror_change_only_the_layout(self):
        kept = self.points.copy()
        x, y, first, second = viewer.display_coordinates(self.points, viewer.DisplayView("xy", 90))
        self.assertEqual((first, second), ("\u2212Y", "X"))
        self.assertEqual(x.tolist(), (-self.points[:, 1]).tolist())
        self.assertEqual(y.tolist(), self.points[:, 0].tolist())
        x, _y, first, _second = viewer.display_coordinates(self.points, viewer.DisplayView("xy", 0, True))
        self.assertEqual(first, "\u2212X")
        self.assertEqual(x.tolist(), (-self.points[:, 0]).tolist())
        x, y, first, second = viewer.display_coordinates(self.points, viewer.DisplayView("xy", 180))
        self.assertEqual((first, second), ("\u2212X", "\u2212Y"))
        np.testing.assert_array_equal(self.points, kept)

    def test_an_unknown_view_is_refused(self):
        with self.assertRaises(ValueError):
            viewer.display_coordinates(self.points, viewer.DisplayView("uv"))


class ImageViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def picture(self):
        return rv.frequency_plot(rv.ReviewState(_Stub(NEAREST, FE_ROWS)))

    def test_a_scroll_bars_width_does_not_change_the_height(self):
        view = ImageView()
        self.addCleanup(view.close)
        view.resize(400, 10)
        view.show()
        self.app.processEvents()
        view.set_image(self.picture())
        height = view.height()
        view.resize(400 - 17, height)
        self.app.processEvents()
        self.assertEqual(view.height(), height)
        view.resize(700, height)
        self.app.processEvents()
        self.assertGreater(view.height(), height)

    def test_pictures_in_a_scroll_area_settle_at_every_height(self):
        # the loop: the picture's height shows the scroll bar, the bar narrows the picture, the lower picture hides the bar
        area = QScrollArea()
        area.setWidgetResizable(True)
        content = QWidget()
        grid = QGridLayout(content)
        views = (ImageView(), ImageView())
        for column, view in enumerate(views):
            grid.addWidget(view, 0, column)
        area.setWidget(content)
        area.resize(900, 400)
        area.show()
        self.addCleanup(area.close)
        self.app.processEvents()
        for view in views:
            view.set_image(self.picture())
        for height in range(150, 420, 3):
            area.resize(900, height)
            self.app.processEvents()
        self.assertTrue(all(view.source is not None for view in views))


class _Flow(r2._Project):
    def setUp(self):
        super().setUp()
        self.addCleanup(self.app.processEvents)


class NavigationTests(_Flow):
    def test_four_pages_and_review_after_an_analysis(self):
        window = self.window()
        self.assertEqual([b.text() for b in window.sidebar.findChildren(QPushButton)],
                         ["Analyze", "Review", "MAC / Points", "Materials", "Research Tuning"])
        self.assertEqual(window.stack.currentIndex(), pw.ANALYZE_PAGE)
        _window, panel = self.analysed()
        self.assertEqual(_window.stack.currentIndex(), pw.REVIEW_PAGE)
        self.assertEqual(_window.nav.checkedId(), pw.REVIEW_PAGE)
        self.assertIs(panel.result_box.window(), _window)

    def test_the_analyze_page_holds_only_the_inputs(self):
        window, panel = self.analysed()
        page = window.stack.widget(pw.ANALYZE_PAGE).widget()
        for widget in (panel.fields[FE], panel.fields[EXPERIMENTAL], panel.analyze_button, panel.advanced_toggle,
                       panel.advanced):
            self.assertTrue(page.isAncestorOf(widget))
        for widget in (panel.result_box, panel.shapes, panel.tables_box, panel.comparison_box):
            self.assertFalse(page.isAncestorOf(widget))
        self.assertIn("FE modes 1-20", " ".join(l.text() for l in panel.findChildren(type(panel.message))))

    def test_a_comparison_started_on_mac_points_stays_there(self):
        window, panel = self.analysed()
        self.confirmed(panel)
        window.show_page(pw.MAC_PAGE)
        self.compare(panel)
        self.assertEqual(window.stack.currentIndex(), pw.MAC_PAGE)

    def test_a_failure_returns_to_analyze_with_its_message(self):
        window, panel = self.analysed()
        panel._block("something failed")
        self.assertEqual(window.stack.currentIndex(), pw.ANALYZE_PAGE)
        self.assertEqual(window.statusBar().currentMessage(), "something failed")

    def test_no_page_scrolls_sideways_at_the_usual_sizes(self):
        window, _panel = self.analysed()
        for size in ((900, 680), (1366, 768)):
            window.resize(*size)
            for page in range(window.stack.count()):
                window.show_page(page)
                self.app.processEvents()
                area = window.stack.currentWidget()
                self.assertIsInstance(area, QScrollArea)
                self.assertEqual(area.horizontalScrollBar().maximum(), 0, (size, page))

    def test_the_tuning_page_rows_continue_on_the_next_line_instead_of_widening_the_page(self):
        """RESEARCH-TUNING-RESPONSIVE-FIX-01: a row of wide buttons wraps; no button is cut, hidden or pushed out of view."""
        window = self.window()
        window.show()
        tuning = window.research_tuning
        tuning.results_card.setVisible(True)  # the cards a result or a solid model shows: their rows, layout only
        tuning.solid_card.setVisible(True)
        rows = ((tuning.sandwich_read_button, tuning.sandwich_folder_button),
                (tuning.export_button, tuning.abaqus_button),
                (tuning.solid_run_button, tuning.solid_cancel_button),
                (tuning.run_button, tuning.cancel_button), (tuning.use_registered_button,))
        for size in ((900, 680), (1366, 768)):
            window.resize(*size)
            window.show_page(pw.TUNING_PAGE)
            self.app.processEvents()
            self.app.processEvents()
            area = window.stack.currentWidget()
            self.assertEqual(area.horizontalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAsNeeded, size)  # not masked
            self.assertEqual(area.horizontalScrollBar().maximum(), 0, size)
            self.assertFalse(area.horizontalScrollBar().isVisible(), size)
            view = area.viewport()
            for row in rows:
                for button in row:
                    name = (size, button.text())
                    self.assertTrue(button.isVisibleTo(window), name)
                    self.assertGreaterEqual(button.width(), button.sizeHint().width(), name)  # its whole text
                    self.assertGreaterEqual(button.height(), button.sizeHint().height(), name)
                    left = button.mapTo(view, QPoint(0, 0)).x()
                    self.assertGreaterEqual(left, 0, name)
                    self.assertLessEqual(left + button.width(), view.width(), name)
                if len(row) == 2:  # side by side whenever both fit; otherwise the second directly below, left-aligned
                    first, second = row
                    room = first.parentWidget().contentsRect().width() - 32  # the card's own margins
                    fits = first.sizeHint().width() + 6 + second.sizeHint().width() <= room
                    one_line = abs(first.geometry().center().y() - second.geometry().center().y()) <= 2
                    self.assertEqual(one_line, fits, (size, first.text(), room))
                    if not one_line:
                        self.assertEqual(second.x(), first.x(), (size, second.text()))
                        self.assertGreaterEqual(second.y(), first.y() + first.height(), (size, second.text()))
        # at the wide size every two-button row is on one line, as before
        for first, second in (r for r in rows if len(r) == 2):
            self.assertLess(first.x(), second.x(), first.text())
            self.assertLessEqual(abs(first.geometry().center().y() - second.geometry().center().y()), 2, first.text())
        # and the narrow size did wrap at least the widest row, so the test is not empty
        window.resize(900, 680)
        self.app.processEvents()
        self.app.processEvents()
        wide = tuning.export_button.sizeHint().width() + 6 + tuning.abaqus_button.sizeHint().width()
        if wide > tuning.export_button.parentWidget().contentsRect().width() - 32:
            self.assertGreater(tuning.abaqus_button.y(), tuning.export_button.y())

    def test_save_from_the_menu_stays_on_the_page(self):
        window, panel = self.analysed()
        panel.save_project_as(str(self.project))
        self.wait(panel)
        window.project_actions["save"].trigger()
        self.wait(panel)
        self.assertEqual(window.stack.currentIndex(), pw.REVIEW_PAGE)
        self.assertIn("Project saved", window.statusBar().currentMessage())


class ReviewPageTests(_Flow):
    def test_the_table_has_the_required_columns_and_every_record(self):
        window, panel = self.analysed()
        table = window.review.table
        self.assertEqual(tuple(table.horizontalHeaderItem(c).text() for c in range(table.columnCount())),
                         WANTED_HEADERS + ("Actions",))
        self.assertEqual(table.rowCount(), len(panel.analysis.nearest_rows))
        self.assertEqual(table.item(0, 1).text(), panel.analysis.nearest_rows[0][1])  # EXP mode 1 is kept
        self.assertEqual(table.item(0, 6).text(), panel.analysis.nearest_rows[0][3])
        self.assertEqual(window.review.combos[0].currentData(), panel.analysis.nearest_rows[0][3])

    def test_ux3_compact_columns_by_default_and_all_columns_on_request(self):
        window, panel = self.analysed()
        self.wait(panel)
        review = window.review
        table = review.table
        shown = [table.horizontalHeaderItem(c).text() for c in range(table.columnCount()) if not table.isColumnHidden(c)]
        self.assertEqual(shown, ["EXP mode", "EXP frequency (Hz)", "Selected FE mode", "Selected FE frequency (Hz)", "Δf (%)"])
        self.assertEqual(review.columns_toggle.text(), rp.SHOW_COLUMNS)
        self.assertTrue(review.combos[0].isVisibleTo(table))  # the manual FE choice stays in the compact view
        review.columns_toggle.setChecked(True)
        self.assertFalse(any(table.isColumnHidden(c) for c in range(table.columnCount())))
        self.assertEqual(review.columns_toggle.text(), rp.FEWER_COLUMNS)
        self.assertEqual(table.cellWidget(0, table.columnCount() - 1).text(), "Swap")
        review.columns_toggle.setChecked(False)
        self.assertTrue(table.isColumnHidden(0) and table.isColumnHidden(6) and table.isColumnHidden(7))
        for size in ((900, 680), (1366, 768)):
            window.resize(*size)
            self.app.processEvents()
            self.assertEqual(window.stack.currentWidget().horizontalScrollBar().maximum(), 0, size)
            self.assertEqual(table.horizontalScrollBar().maximum(), 0, size)

    def test_review_ux1_each_shape_view_says_which_side_it_is_also_when_stacked(self):
        from PySide6.QtWidgets import QBoxLayout

        from new_gui import analyze_panel as apanel

        window, panel = self.analysed()
        self.wait(panel)
        review = window.review
        self.assertEqual(apanel.SHAPE_BANNER[EXPERIMENTAL][0], "EXPERIMENT (EXP)")
        self.assertEqual(apanel.SHAPE_BANNER[FE][0], "ABAQUS FE")
        for saved, panels in ((False, panel.shape_panels), (True, panel.saved_shapes)):
            for kind, shape in panels.items():
                banner = panel.shape_banners[(kind, saved)]
                self.assertIs(shape.layout().itemAt(0).widget(), banner)  # the first thing of its own view
                name, frame = apanel.SHAPE_BANNER[kind]
                self.assertIn(name, banner.text())
                self.assertIn("own coordinate frame", banner.text())
                self.assertEqual(banner.accessibleName(), f"{name}. {frame}")
                other = apanel.SHAPE_BANNER[FE if kind == EXPERIMENTAL else EXPERIMENTAL][0]
                self.assertNotIn(other, banner.text())
        live = [panel.shape_banners[(kind, False)] for kind in (EXPERIMENTAL, FE)]
        self.assertGreaterEqual(min(b.font().pointSizeF() for b in live), 9.0)
        self.assertIn("font-size:13pt", live[0].text())  # larger than the card title (12 pt)
        for width, direction in ((1300, QBoxLayout.Direction.LeftToRight), (300, QBoxLayout.Direction.TopToBottom)):
            panel.fit_shapes(width)
            self.app.processEvents()
            self.assertEqual(panel.shapes_layout.direction(), direction)
            for kind in (EXPERIMENTAL, FE):  # side by side or stacked, the band is inside the view it names
                banner, shape = panel.shape_banners[(kind, False)], panel.shape_panels[kind]
                self.assertTrue(banner.isVisibleTo(shape))
                self.assertTrue(shape.rect().contains(banner.geometry()))
        # the two frames are independent, and likeness is no correspondence: said once, above both views
        self.assertIn("independent coordinate frames", review.frames_note.text())
        self.assertIn("not aligned", review.frames_note.text())
        self.assertIn("not a validated modal correspondence", review.frames_note.text())
        self.assertTrue(review.frames_note.isVisibleTo(review.shapes_area))
        inner = review.shapes_area.widget().layout()
        self.assertLess(inner.indexOf(review.frames_note), inner.indexOf(panel.shapes))
        for size in ((900, 700), (1366, 768)):  # both sentences are read whole, whatever the views below them need
            window.resize(*size)
            self.app.processEvents()
            pane = review.shapes_area.viewport().width()
            for label in (review.selection_label, review.frames_note):
                self.assertLessEqual(label.x() + label.width(), pane, size)
            self.assertEqual(window.stack.currentWidget().horizontalScrollBar().maximum(), 0, size)
        for text in [b.text() for b in panel.shape_banners.values()] + [review.frames_note.text()]:
            self.assertTrue(text.isascii(), text)  # English only

    def _shape_views_fit_the_pane(self, window, panel, saved):
        """The two views stand side by side where the pane that is seen has room for both at their least widths, else one
        above the other. The window's size alone does not say which: the live views, with their controls, need more room
        than the views of a saved result, so at 900 x 700 the live ones are stacked while the saved ones may fit side by
        side (REVIEW-UX-1-F2; whether they do depends on the fonts of the platform). Never a sideways scroll."""
        from PySide6.QtWidgets import QBoxLayout
        from new_gui.analyze_panel import SIDE_BY_SIDE_WIDTH

        review = window.review
        review.select_row(1)
        self.wait(panel)
        self.assertIs(review.views.currentWidget(), review.shapes_area)
        area, views = review.shapes_area, (panel.saved_shapes if saved else panel.shape_panels)
        others = panel.shape_panels if saved else panel.saved_shapes
        row = panel.shapes_layout.parentWidget()
        shown = {}
        for size in ((1600, 900), (900, 700), (1366, 768), (900, 700), (1600, 900), (1366, 768)):
            window.resize(*size)
            for _ in range(5):
                self.app.processEvents()
            self.assertTrue(all(not view.isHidden() for view in views.values()), (size, saved))  # the views in question
            self.assertTrue(all(view.isHidden() for view in others.values()), (size, saved))
            pane = area.viewport().width()
            room = min(pane, row.width())  # what the two views can take without a sideways scroll
            # the rule of the layout: side by side from the least widths of the two views shown plus the gap between them,
            # and never below the least page width for two views
            need = max(SIDE_BY_SIDE_WIDTH, sum(view.minimumSizeHint().width() for view in views.values()) + 12)
            direction = QBoxLayout.Direction.LeftToRight if room >= need else QBoxLayout.Direction.TopToBottom
            if size == (1600, 900):
                self.assertGreaterEqual(room, need, (size, saved))  # a wide window: room for both, live or saved
            elif size == (900, 700) and not saved:
                self.assertLess(room, need, (size, saved))  # the reported case: the live views do not fit side by side
            self.assertEqual(panel.shapes_layout.direction(), direction, (size, pane, room, need, saved))
            if direction == QBoxLayout.Direction.LeftToRight:  # side by side only where both really fit
                for view in views.values():
                    left = view.mapTo(area.viewport(), view.rect().topLeft()).x()
                    self.assertGreaterEqual(view.width(), view.minimumSizeHint().width(), (size, saved))
                    self.assertTrue(0 <= left and left + view.width() <= pane, (size, saved, left, view.width(), pane))
            self.assertEqual(area.horizontalScrollBar().maximum(), 0, (size, pane, saved))  # the pane as it is seen
            self.assertEqual(window.stack.currentWidget().horizontalScrollBar().maximum(), 0, size)
            self.assertLessEqual(area.widget().width(), pane, size)
            for kind in (EXPERIMENTAL, FE):
                banner, view = panel.shape_banners[(kind, saved)], views[kind]
                self.assertTrue(view.isVisibleTo(area) and banner.isVisibleTo(area), (size, kind))
                left = banner.mapTo(area.viewport(), banner.rect().topLeft()).x()
                self.assertGreaterEqual(left, 0, (size, kind))
                self.assertLessEqual(left + banner.width(), pane, (size, kind))  # the whole band, no sideways scrolling
                # its two lines (the side, and whose frame) have the height they need at this width
                self.assertGreaterEqual(banner.height(), banner.heightForWidth(banner.width()), (size, kind))
            exp, fe = (views[kind].mapTo(area.widget(), views[kind].rect().topLeft()) for kind in (EXPERIMENTAL, FE))
            if direction == QBoxLayout.Direction.TopToBottom:
                self.assertEqual(exp.x(), fe.x(), size)
                self.assertGreater(fe.y(), exp.y(), size)  # EXPERIMENT above ABAQUS FE
            else:
                self.assertGreater(fe.x(), exp.x(), size)
                self.assertEqual(exp.y(), fe.y(), size)
            for label in (review.selection_label, review.frames_note):
                self.assertTrue(label.isVisibleTo(area))
                self.assertLessEqual(label.x() + label.width(), pane, size)
            table = cells(review.table)
            shown[size] = (review.selection_label.text(), tuple(table[1]), tuple(map(tuple, table)),
                           review.table.currentRow())
        # the chosen row, its modes and frequencies, and the whole table are the same at every size
        self.assertEqual(len(set(shown.values())), 1)
        return shown[(900, 700)]

    def test_review_ux1_the_two_views_stack_in_a_narrow_window_and_stand_side_by_side_in_a_wide_one(self):
        window, panel = self.analysed()
        self.wait(panel)
        live = self._shape_views_fit_the_pane(window, panel, saved=False)
        for kind in (EXPERIMENTAL, FE):  # the controls and the picture of each view are still there
            self.assertFalse(panel.shape_panels[kind].isHidden())
        self.saved(panel)
        again_window, again = self.reopened()
        self.wait(again)
        self.assertTrue(again.saved_shapes[FE].entries and again.saved_shapes[EXPERIMENTAL].entries)
        reopened = self._shape_views_fit_the_pane(again_window, again, saved=True)
        self.assertIsNotNone(again.saved_shapes[FE].image.source)
        self.assertEqual(reopened[1], live[1])  # the same row of the table

    def test_review_ux1_the_fe_mode_choice_is_compact_and_still_chooses(self):
        window, panel = self.analysed()
        self.wait(panel)
        review = window.review
        table, widths = review.table, []
        for size in ((900, 700), (1366, 768)):
            window.resize(*size)
            self.app.processEvents()
            self.assertEqual(window.stack.currentWidget().horizontalScrollBar().maximum(), 0, size)
            self.assertEqual(table.horizontalScrollBar().maximum(), 0, size)
            for row, combo in enumerate(review.combos):
                self.assertGreaterEqual(combo.width(), rp.FE_CHOICE_WIDTH[0])
                self.assertLessEqual(combo.width(), rp.FE_CHOICE_WIDTH[1])
                self.assertTrue(combo.isVisibleTo(table))
                self.assertIs(combo.parentWidget(), table.cellWidget(row, 3))
            self.assertLess(review.combos[0].width(), table.columnWidth(3), size)  # no longer stretched over it
            widths.append((review.combos[0].width(), table.columnWidth(3)))
            self.assertGreaterEqual(table.height(), table.minimumSizeHint().height())  # its rows stay whole
        self.assertEqual(widths[0][0], widths[1][0])  # a wider window widens the column, never the selector
        self.assertGreater(widths[1][1], widths[0][1])
        self.assertGreater(widths[1][1], 2 * widths[1][0])
        self.assertEqual(table.rowCount(), len(panel.analysis.nearest_rows))
        before = review.state.selected(0)
        other = next(number for number, _text in review.state.options
                     if number != before and number not in [review.state.selected(r) for r in range(len(review.state))])
        review.combos[0].setCurrentIndex(review.combos[0].findData(other))
        review.combos[0].activated.emit(review.combos[0].currentIndex())  # as a click on the list does
        self.wait(panel)
        row = review.state.row(0)
        self.assertEqual(review.state.selected(0), other)
        self.assertEqual(review.combos[0].currentData(), other)
        self.assertEqual([table.item(0, c).text() for c in range(len(rv.HEADERS))], list(row.cells()))
        self.assertRegex(table.item(0, 5).text(), r"^[+\-−]")  # the signed difference of the new choice
        review._ask_duplicate = lambda _text: rp.KEEP
        self.assertTrue(review.select_mode(1, other))
        self.assertTrue(review.duplicate_label.text())  # the duplicate warning is still raised
        self.assertTrue(review.reset_all())
        self.assertEqual(review.state.selected(0), before)

    def test_ux3_one_sentence_status_and_unverified_candidates_without_a_registration(self):
        window, panel = self.analysed()
        self.wait(panel)
        review = window.review
        self.assertIsNone(panel.analysis.comparison)
        self.assertEqual(review.status_sentence.text(), rv.STATUS_UNREGISTERED)
        self.assertEqual(review.status_sentence.text().count(". "), 0)  # one sentence
        self.assertFalse(review.status_sentence.isHidden())
        self.assertIn("unverified", review.status_sentence.text())
        self.assertIn("no MAC", review.status_sentence.text())
        self.assertEqual(review.table_title.text(), rv.UNVERIFIED_TITLE)
        top = review.status_sentence.mapTo(review, review.status_sentence.rect().topLeft()).y()
        self.assertLess(top, review.splitter.mapTo(review, review.splitter.rect().topLeft()).y())  # above the status card
        self.assertTrue(review.header_area.widget().isAncestorOf(panel.status_label))
        self.assertEqual(panel.status_label.text(), am.REGISTRATION_REQUIRED)

    def test_ux3_a_confirmed_comparison_says_so_and_keeps_the_table_frequency_based(self):
        window, panel = self.analysed()
        self.confirmed(panel)
        window.show_page(pw.REVIEW_PAGE)
        self.compare(panel)
        self.wait(panel)
        review = window.review
        self.assertEqual(review.status_sentence.text(), rv.STATUS_CONFIRMED)
        self.assertEqual(review.table_title.text(), rv.PAIRED_TITLE)
        self.assertNotIn("unverified", review.status_sentence.text())

    def test_ux3_a_row_chosen_from_all_tables_opens_its_shapes(self):
        window, panel = self.analysed()
        self.wait(panel)
        review = window.review
        review.views.setCurrentWidget(panel.tables_box)
        review.select_row(3)
        self.wait(panel)
        self.assertIs(review.views.currentWidget(), review.shapes_area)
        row = panel.analysis.nearest_rows[3]
        fe = panel.shape_panels[FE]
        self.assertEqual(fe.preview.modes[fe.chosen_index()].number, int(row[3]))
        self.assertEqual(panel.shape_panels[EXPERIMENTAL].chosen_index(), 3)
        review.views.setCurrentIndex(1)  # the plots mark the chosen row themselves: the tab stays
        review.select_row(1)
        self.wait(panel)
        self.assertEqual(review.views.currentIndex(), 1)
        self.assertEqual(review.current, 1)

    def test_ux3_a_row_click_brings_the_shape_pictures_on_screen_without_page_scrolling(self):
        window, panel = self.analysed()
        self.wait(panel)
        review = window.review
        window.resize(900, 700)
        self.app.processEvents()
        self.assertEqual(window.stack.currentWidget().verticalScrollBar().maximum(), 0)  # the page fills the window
        review.select_row(4)
        self.wait(panel)
        self.app.processEvents()
        bar, viewport = review.shapes_area.verticalScrollBar(), review.shapes_area.viewport()
        # REVIEW-UX-1: in a pane too narrow for both views they are one above the other; the upper picture (EXPERIMENT)
        # is then the one brought on screen, the lower one is reached by scrolling the pane down, never sideways
        from PySide6.QtWidgets import QBoxLayout
        stacked = panel.shapes_layout.direction() == QBoxLayout.Direction.TopToBottom
        self.assertEqual(review.shapes_area.horizontalScrollBar().maximum(), 0)
        for kind in ((EXPERIMENTAL,) if stacked else (FE, EXPERIMENTAL)):
            image = panel.shape_panels[kind].image
            top = image.mapTo(review.shapes_area.widget(), image.rect().topLeft()).y()
            self.assertLess(top, bar.value() + viewport.height() - 60, kind)  # a good part of each picture is in view
            self.assertGreater(top + image.height(), bar.value(), kind)
        kept = bar.value()
        review.show_row(5)  # a programmatic redraw keeps the place
        self.wait(panel)
        self.assertEqual(bar.value(), kept)

    def test_selecting_a_row_shows_its_shapes(self):
        window, panel = self.analysed()
        self.wait(panel)
        window.review.select_row(2)
        self.wait(panel)
        row = panel.analysis.nearest_rows[2]
        fe = panel.shape_panels[FE]
        self.assertEqual(fe.preview.modes[fe.chosen_index()].number, int(row[3]))
        self.assertEqual(panel.shape_panels[EXPERIMENTAL].chosen_index(), 2)
        self.assertEqual(fe.slot.state, sm.SHOWN)
        self.assertIn(f"FE {row[3]}", window.review.selection_label.text())
        self.assertIn("not a validated pair", window.review.selection_label.text())

    def test_a_manual_choice_follows_into_the_table_shapes_and_marks(self):
        window, panel = self.analysed()
        self.wait(panel)
        review = window.review
        other = next(n for n, _t in review.state.options if n not in {review.state.selected(i) for i in range(len(review.state))})
        self.assertTrue(review.select_mode(1, other))
        self.wait(panel)
        row = review.state.row(1)
        self.assertEqual(review.table.item(1, 4).text(), row.selected_text)
        self.assertEqual(review.table.item(1, 5).text(), row.difference_text)
        self.assertEqual(review.table.item(1, 6).text(), panel.analysis.nearest_rows[1][3])
        self.assertIn(rv.USER_HYPOTHESIS, review.hypothesis_label.text())
        self.assertFalse(review.session_label.isHidden())
        fe = panel.shape_panels[FE]
        self.assertEqual(str(fe.preview.modes[fe.chosen_index()].number), other)
        review.reset_all()
        self.wait(panel)
        self.assertEqual(review.state.manual, {})
        self.assertTrue(review.hypothesis_label.isHidden())
        self.assertEqual(review.table.item(1, 3).text(), panel.analysis.nearest_rows[1][3])

    def test_a_duplicate_asks_and_cancel_keeps_the_selection(self):
        window, panel = self.analysed()
        self.wait(panel)
        review = window.review
        taken = review.state.selected(0)
        before = review.state.selected(1)
        review._ask_duplicate = lambda _text: rp.CANCEL
        self.assertFalse(review.select_mode(1, taken))
        self.assertEqual(review.state.selected(1), before)
        self.assertEqual(review.combos[1].currentData(), before)
        review._ask_duplicate = lambda _text: rp.KEEP
        self.assertTrue(review.select_mode(1, taken))
        self.wait(panel)
        self.assertIn("Not one-to-one", review.duplicate_label.text())
        self.assertLess(len(review.duplicate_label.text()), 80)
        review.reset_all()
        self.wait(panel)
        review._ask_duplicate = lambda _text: rp.SWAP
        self.assertTrue(review.select_mode(1, taken))
        self.wait(panel)
        self.assertEqual((review.state.selected(0), review.state.selected(1)), (before, taken))
        self.assertTrue(review.duplicate_label.isHidden())

    def test_swap_is_in_the_last_column_of_each_applicable_row(self):
        window, panel = self.analysed()
        self.wait(panel)
        review = window.review
        last = review.table.columnCount() - 1
        rows = review.table.rowCount()
        self.assertEqual([review.table.cellWidget(r, last).text() for r in range(rows - 1)], ["Swap"] * (rows - 1))
        self.assertIsNone(review.table.cellWidget(rows - 1, last))
        before = (review.state.selected(0), review.state.selected(1))
        review.table.cellWidget(0, last).click()
        self.wait(panel)
        self.assertEqual((review.state.selected(0), review.state.selected(1)), before[::-1])
        self.assertEqual(review.current, 0)
        self.assertEqual(review.combos[0].currentData(), before[1])
        self.assertIn(rv.USER_HYPOTHESIS, review.hypothesis_label.text())
        self.assertFalse(hasattr(review, "swap_button"))

    def test_the_wheel_changes_no_tab_and_no_list_on_any_page(self):
        window, panel = self.analysed()
        self.wait(panel)
        tabs = window.review.views
        index = tabs.currentIndex()
        self.assertFalse(wheel(tabs.tabBar()).isAccepted())
        self.assertEqual(tabs.currentIndex(), index)
        fe = panel.shape_panels[FE]
        before = [fe.item_combo.currentIndex(), fe.component_combo.currentIndex(), fe.view_combo.currentIndex()]
        for combo in (fe.item_combo, fe.component_combo, fe.view_combo):
            wheel(combo)
        self.assertEqual([fe.item_combo.currentIndex(), fe.component_combo.currentIndex(), fe.view_combo.currentIndex()], before)
        plain = QComboBox(window)  # any list, also one not made by the program's own helpers
        plain.addItems(["a", "b"])
        wheel(plain)
        self.assertEqual(plain.currentIndex(), 0)

    def test_a_new_result_opens_mode_shapes_at_the_top_and_a_redraw_keeps_the_scroll(self):
        window, panel = self.analysed()
        self.wait(panel)
        window.resize(1180, 620)
        review = window.review
        self.app.processEvents()
        bar = review.shapes_area.verticalScrollBar()
        self.assertGreater(bar.maximum(), 0)
        bar.setValue(bar.maximum())
        review.views.setCurrentIndex(1)
        self.run_analysis(panel)  # a new result
        self.wait(panel)
        self.app.processEvents()
        self.assertIs(review.views.currentWidget(), review.shapes_area)
        self.assertEqual(bar.value(), 0)
        self.assertTrue(review.shapes_area.widget().isAncestorOf(panel.shape_panels[FE].view_combo))
        bar.setValue(min(120, bar.maximum()))
        kept = bar.value()
        self.assertGreater(kept, 0)
        review.show_row(1)  # ordinary redraws
        self.wait(panel)
        panel.shape_panels[FE].show_shape()
        self.wait(panel)
        self.app.processEvents()
        self.assertEqual(bar.value(), kept)

    def test_a_focused_show_button_is_not_possible_so_a_redraw_cannot_move_the_pane(self):
        window, panel = self.analysed()
        self.assertEqual(panel.shape_panels[FE].show_button.focusPolicy(), Qt.FocusPolicy.NoFocus)

    def test_the_shape_view_can_be_chosen_and_redraws(self):
        window, panel = self.analysed()
        self.wait(panel)
        fe = panel.shape_panels[FE]
        first = fe.image.data
        self.assertEqual(fe.display(), sm.DEFAULT_VIEW)
        self.assertIn("Source coordinates", fe.projection.text())
        fe.rotation_combo.setCurrentIndex(fe.rotation_combo.findData(90))
        self.assertTrue(fe.show_shape())
        self.wait(panel)
        self.assertEqual(fe.display(), ("source", 90, False))
        self.assertEqual(fe.slot.state, sm.SHOWN)
        self.assertNotEqual(fe.image.data, first)
        fe.view_combo.setCurrentIndex(fe.view_combo.findData("best_fit"))
        self.assertIn("best-fit plane", fe.projection.text())
        self.assertIn("MAC", fe.projection.text())
        self.assertIs(panel.analysis, panel.analysis)
        coordinates = np.asarray(panel.inputs.fe.dataset.modes[0].coordinates)
        self.assertEqual(coordinates.shape[1], 3)
        self.assertEqual(panel.status_label.text(), am.REGISTRATION_REQUIRED)

    def test_all_tables_fill_the_pane_and_select_their_own_rows(self):
        window, panel = self.analysed()
        self.wait(panel)
        window.resize(1180, 800)
        review = window.review
        review.views.setCurrentIndex(3)
        review.splitter.setSizes([60, 200, 520])
        self.app.processEvents()
        table = panel.tables["fe"]
        panel.result_tabs.setCurrentIndex(1)
        self.app.processEvents()
        self.assertGreater(table.height(), 250)
        self.assertIs(review.views.widget(3), panel.tables_box)
        table.selectRow(2)
        self.assertEqual([i.row() for i in table.selectionModel().selectedRows()], [2])

    def test_a_manual_choice_changes_no_result_no_saved_file_and_no_pair(self):
        window, panel = self.analysed()
        self.confirmed(panel)
        window.show_page(pw.REVIEW_PAGE)
        analysis = self.compare(panel)
        self.wait(panel)
        pairs, mac = analysis.comparison.pair_rows, analysis.comparison.mac_values
        before = r2.displayed(panel)
        self.saved(panel)
        with zipfile.ZipFile(self.project) as archive:
            clean = json.loads(archive.read(ap.PROJECT))
        window.review.swap_with_next(0)
        self.wait(panel)
        self.assertTrue(window.review.state.manual)
        self.assertIs(panel.analysis, analysis)
        self.assertEqual(analysis.comparison.pair_rows, pairs)
        self.assertEqual(analysis.comparison.mac_values, mac)
        self.assertEqual(r2.displayed(panel), before)
        self.assertEqual(panel.status_label.text(), am.CONFIRMED_COMPARISON)
        second = self.root / "with manual.mcproj"
        self.saved(panel, second)
        with zipfile.ZipFile(second) as archive:
            names = set(archive.namelist())
            again = json.loads(archive.read(ap.PROJECT))
        for key in ("saved_at", "written_at"):
            clean.pop(key), again.pop(key)
        self.assertEqual(again, clean)
        self.assertFalse(any(rv.USER_HYPOTHESIS in name for name in names))
        self.assertNotIn(rv.USER_HYPOTHESIS, json.dumps(again))

    def test_a_new_result_starts_again_from_the_automatic_selection(self):
        window, panel = self.analysed()
        self.wait(panel)
        window.review.swap_with_next(0)
        self.wait(panel)
        self.run_analysis(panel)
        self.assertEqual(window.review.state.manual, {})

    def test_the_wheel_over_a_closed_choice_changes_nothing_and_goes_on(self):
        window, panel = self.analysed()
        self.wait(panel)
        combo = window.review.combos[0]
        chosen = combo.currentIndex()
        event = wheel(combo)
        self.assertEqual(combo.currentIndex(), chosen)
        self.assertEqual(window.review.state.manual, {})
        self.assertFalse(event.isAccepted())
        shape = panel.shape_panels[FE].item_combo
        chosen = shape.currentIndex()
        wheel(shape)
        self.assertEqual(shape.currentIndex(), chosen)
        self.assertEqual(panel.shape_panels[FE].slot.state, sm.SHOWN)

    def test_the_views_are_read_only_and_the_frf_tab_never_makes_a_curve(self):
        window, panel = self.analysed()
        self.wait(panel)
        review = window.review
        review.views.setCurrentIndex(1)
        self.app.processEvents()
        self.assertIsNotNone(review.frequency_image.source)
        self.assertIsNotNone(review.difference_image.source)
        review.views.setCurrentIndex(2)
        self.app.processEvents()
        self.assertIsNone(review.frf_image.source)
        self.assertEqual(review.frf_note.text(), rv.FRF_NOT_IN_FILE)

    def test_frf_curves_are_shown_when_the_importer_read_them(self):
        window, panel = self.analysed()
        self.wait(panel)
        panel.chosen_dataset().metadata.update({"_frf_frequency_hz": [10.0, 20.0, 30.0], "_frf_indicator": [1.0, 3.0, 2.0]})
        window.review.views.setCurrentIndex(2)
        self.app.processEvents()
        self.assertIsNotNone(window.review.frf_image.source)
        self.assertEqual(window.review.frf_note.text(), rv.FITTED_NOTE)
        self.assertTrue(window.review.frf_actions.copy_button.isEnabled())

    def test_frf_peak_records_get_a_short_label_one_explanation_and_full_details(self):
        window, panel = self.analysed()
        rows = tuple(row[:3] + (sm.PROVISIONAL_TEXT,) for row in panel.analysis.experimental_rows)
        from dataclasses import replace

        panel.analysis = replace(panel.analysis, experimental_rows=rows)
        panel._show_result()
        table = panel.tables["experimental"]
        self.assertEqual(table.item(0, 3).text(), sm.FRF_PEAK_SHORT)
        self.assertEqual(table.item(0, 3).toolTip(), sm.PROVISIONAL_TEXT)
        self.assertFalse(window.review.provisional_note.isHidden())
        self.assertTrue(window.review.state.provisional)
        self.assertEqual(panel.analysis.experimental_rows[0][3], sm.PROVISIONAL_TEXT)  # the data keep the full wording


class ImageActionTests(_Flow):
    def test_copy_and_save_use_the_original_picture_and_are_off_without_one(self):
        window, panel = self.analysed()
        self.wait(panel)
        fe = panel.shape_panels[FE]
        data = fe.image.data
        self.assertTrue(data.startswith(b"\x89PNG"))
        actions = fe.image_actions
        self.assertTrue(actions.copy_button.isEnabled())
        self.assertTrue(actions.copy())
        original = QImage.fromData(data, "PNG")
        copied = QApplication.clipboard().image()
        self.assertEqual((copied.width(), copied.height()), (original.width(), original.height()))
        target = self.root / "shape.png"
        actions.ask_path = lambda: str(target)
        self.assertTrue(actions.save())
        self.assertEqual(target.read_bytes(), data)
        fe.image.clear_image()
        self.assertFalse(actions.copy_button.isEnabled())
        self.assertFalse(actions.save_button.isEnabled())
        self.assertFalse(actions.copy())
        self.assertFalse(actions.save())

    def test_every_plotted_result_has_the_actions(self):
        window, panel = self.analysed()
        self.wait(panel)
        review = window.review
        for actions in (review.frequency_actions, review.difference_actions, review.frf_actions,
                        panel.shape_panels[EXPERIMENTAL].image_actions, window.mac_points.measured_actions):
            self.assertIsInstance(actions, ImageActions)
        self.assertFalse(review.frf_actions.copy_button.isEnabled())  # no picture yet
        review.views.setCurrentIndex(1)
        self.app.processEvents()
        self.assertTrue(review.frequency_actions.save_button.isEnabled())

    def test_a_saved_picture_can_be_exported_as_stored(self):
        _window, panel = self.analysed()
        self.wait(panel)
        self.saved(panel)
        _second, again = self.reopened()
        saved = again.saved_shapes[FE]
        entry = next(e for e in saved.entries if e["number"] == saved.shown_number)
        target = self.root / "saved.png"
        saved.image_actions.ask_path = lambda: str(target)
        self.assertTrue(saved.image_actions.save())
        self.assertEqual(target.read_bytes(), again.snapshot.images[entry["image"]])
        self.assertTrue(saved.image_actions.copy())


class SummaryTests(_Flow):
    def test_analyze_says_what_is_loaded_and_available(self):
        window, panel = self.analysed()
        self.wait(panel)
        rows = dict(cells(panel.summary_table))
        self.assertEqual(rows["FE results"], self.odb.name)
        self.assertEqual(rows["Experiment"], Path(self.exp_path).name)
        self.assertIn("first elastic", rows["FE modes"])
        self.assertIn(asm.FITTED, rows["Experimental records"])
        self.assertEqual(rows["Frequency table and plots"], asm.AVAILABLE)
        self.assertIn("no usable FRF curve", rows["FRF spectrum"])
        self.assertEqual(rows["MAC and mode pairs"], mp.REASONS[am.REFUSED])
        self.assertTrue(window.stack.widget(pw.ANALYZE_PAGE).widget().isAncestorOf(panel.summary_table))

    def test_a_saved_result_says_what_needs_the_sources(self):
        _window, panel = self.analysed()
        self.wait(panel)
        self.saved(panel)
        _second, again = self.reopened()
        rows = dict(cells(again.summary_table))
        self.assertEqual(rows["FRF spectrum"], asm.NEEDS_SOURCE)
        self.assertEqual(rows["Mode shapes"], "Saved magnitude pictures only")

    def test_frf_peak_records_are_named_as_such(self):
        self.assertEqual(asm._record_type(3, 3), asm.FRF_PEAKS)
        self.assertEqual(asm._record_type(0, 3), asm.FITTED)
        self.assertEqual(asm._record_type(1, 3), asm.MIXED)


class SaveFromReviewTests(_Flow):
    """ABM-UX4: Save result on the Review page is the File menu's Save Project, with its dialog and its messages."""

    @staticmethod
    def _content(path):
        with zipfile.ZipFile(path) as archive:
            names = sorted(archive.namelist())
            document = json.loads(archive.read(ap.PROJECT))
            pictures = {n: archive.read(n) for n in names if not n.endswith(".json")}  # a manifest hashes the timestamps
        for key in ("saved_at", "written_at"):
            document.pop(key, None)
        return names, document, pictures

    def test_disabled_without_a_result_and_while_running(self):
        window = self.window()
        review = window.review
        self.assertEqual(review.save_button.text(), rp.SAVE_RESULT)
        self.assertFalse(review.save_button.isEnabled())
        _window, panel = self.analysed()
        self.wait(panel)
        review = _window.review
        self.assertTrue(review.save_button.isEnabled())
        self.assertTrue(review.save_button.isVisible())
        self.assertLess(review.save_button.mapTo(review, review.save_button.rect().topLeft()).y(),
                        review.splitter.mapTo(review, review.splitter.rect().topLeft()).y())  # beside the status
        self.assertTrue(panel.analyze())  # another operation starts: saving waits for it
        self.assertTrue(panel.busy())
        self.assertFalse(review.save_button.isEnabled())
        self.assertFalse(_window.project_actions["save"].isEnabled())
        self.wait(panel)
        self.assertTrue(review.save_button.isEnabled())

    def test_first_save_asks_where_and_a_repeated_save_writes_the_same_file(self):
        window, panel = self.analysed()
        self.wait(panel)
        review = window.review
        asked = []
        with mock.patch.object(analyze_panel_module().QFileDialog, "getSaveFileName",
                               side_effect=lambda *a, **k: (asked.append(1), (str(self.project), ""))[1]):
            review.save_button.click()
            self.wait(panel)
            self.assertEqual(len(asked), 1)
            self.assertTrue(self.project.is_file())
            self.assertIn("Project saved", review.save_feedback.text())
            self.assertFalse(review.save_feedback.isHidden())
            self.assertEqual(window.statusBar().currentMessage(), review.save_feedback.text())
            self.assertEqual(window.stack.currentIndex(), pw.REVIEW_PAGE)
            first = self._content(self.project)
            review.save_button.click()  # the project has a path now: no dialog
            self.wait(panel)
            self.assertEqual(len(asked), 1)
        self.assertEqual(self._content(self.project), first)
        menu = self.root / "from the menu.mcproj"
        with mock.patch.object(analyze_panel_module().QFileDialog, "getSaveFileName", return_value=(str(menu), "")):
            window.project_actions["save_as"].trigger()
            self.wait(panel)
        names, document, pictures = self._content(menu)
        self.assertEqual((names, pictures), (first[0], first[2]))  # the same format, files and saved shapes
        self.assertEqual(json.dumps(document, sort_keys=True).replace(menu.name, "X"),
                         json.dumps(first[1], sort_keys=True).replace(self.project.name, "X"))

    def test_a_cancelled_dialog_saves_nothing_and_says_nothing(self):
        window, panel = self.analysed()
        self.wait(panel)
        with mock.patch.object(analyze_panel_module().QFileDialog, "getSaveFileName", return_value=("", "")):
            window.review.save_button.click()
        self.wait(panel)
        self.assertFalse(self.project.exists())
        self.assertTrue(window.review.save_feedback.isHidden())
        self.assertTrue(window.review.save_button.isEnabled())

    def test_a_failed_save_is_shown_as_an_error_and_the_result_stays(self):
        window, panel = self.analysed()
        self.wait(panel)
        analysis = panel.analysis
        with mock.patch.object(analyze_panel_module().pj, "save_analysis", side_effect=OSError("disk full")):
            self.assertTrue(panel.save_project(str(self.project)))
            self.wait(panel)
        review = window.review
        self.assertIn("Project not saved", review.save_feedback.text())
        self.assertEqual(review.save_feedback.objectName(), "error")
        self.assertFalse(self.project.exists())
        self.assertIs(panel.analysis, analysis)
        self.assertTrue(review.save_button.isEnabled())
        self.assertEqual(window.stack.currentIndex(), pw.REVIEW_PAGE)

    def test_a_saved_result_reopens_with_the_same_frequencies_shapes_and_status(self):
        window, panel = self.analysed()
        self.wait(panel)
        before = r2.displayed(panel)
        status = panel.status_label.text()
        with mock.patch.object(analyze_panel_module().QFileDialog, "getSaveFileName", return_value=(str(self.project), "")):
            window.review.save_button.click()
            self.wait(panel)
        again_window, again = self.reopened()
        self.assertEqual(r2.displayed(again), before)
        self.assertEqual(again.status_label.text(), status)
        self.assertEqual(again_window.review.status_sentence.text(), window.review.status_sentence.text())
        self.assertTrue(again.saved_shapes[FE].entries and again.saved_shapes[EXPERIMENTAL].entries)
        self.assertTrue(again_window.review.save_button.isEnabled())  # a reopened result can be saved again
        self.assertTrue(again_window.review.save_feedback.isHidden())


def analyze_panel_module():
    from new_gui import analyze_panel
    return analyze_panel


class SavedResultTests(_Flow):
    def test_opening_shows_review_with_no_computation_and_says_what_needs_the_sources(self):
        _window, panel = self.analysed()
        self.wait(panel)
        self.saved(panel)
        with mock.patch("services.odb_import_service.hash_file", side_effect=AssertionError("no hash")):
            window, again = self.reopened()
        self.assertEqual(window.stack.currentIndex(), pw.REVIEW_PAGE)
        review = window.review
        self.assertEqual(cells(review.table)[0][1], again.analysis.nearest_rows[0][1])
        self.assertFalse(review.saved_note.isHidden())
        self.assertIsNotNone(again.saved_shapes[FE].image.source)
        self.assertEqual(review.status_sentence.text(), rv.STATUS_UNREGISTERED)  # ABM-UX3: the same sentence when reopened
        self.assertEqual(review.table_title.text(), rv.UNVERIFIED_TITLE)
        self.assertTrue(review.table.isColumnHidden(0))
        review.select_row(2)
        self.assertEqual(again.saved_shapes[FE].shown_number, again.analysis.nearest_rows[2][3])
        review.views.setCurrentIndex(1)
        self.assertIsNotNone(review.frequency_image.source)
        review.views.setCurrentIndex(2)
        self.assertIsNone(review.frf_image.source)
        self.assertEqual(review.frf_note.text(), rv.FRF_NEEDS_SOURCE)
        self.assertIsNotNone(again.check_button)
        self.assertTrue(window.stack.widget(pw.ANALYZE_PAGE).widget().isAncestorOf(again.check_button))

    def test_a_row_and_a_manual_choice_use_the_saved_pictures_and_full_frequencies(self):
        _window, panel = self.analysed()
        self.wait(panel)
        self.saved(panel)
        window, again = self.reopened()
        review = window.review
        document = again.snapshot.document
        review.show_row(1)
        self.assertEqual(again.saved_shapes[FE].shown_number, again.analysis.nearest_rows[1][3])
        other = next(n for n, _t in review.state.options if n not in {review.state.selected(i) for i in range(len(review.state))})
        self.assertTrue(review.select_mode(1, other))
        self.assertEqual(again.saved_shapes[FE].shown_number, other)
        fe = next(m["frequency_hz"] for m in document["modes"]["fe"] if str(m["number"]) == other)
        experimental = next(m["frequency_hz"] for m in document["modes"]["experimental"] if m["record"] == "EXP2")
        self.assertEqual(review.state.row(1).difference_text, f"{100.0 * (fe - experimental) / experimental:+.2f}")

    def test_the_marked_row_is_the_row_of_the_pair_on_show(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        self.compare(panel)
        self.wait(panel)
        self.saved(panel)
        window, again = self.reopened()
        pair = again.analysis.comparison.pair_rows[0].cells
        current = window.review.current
        self.assertEqual(window.review.state.row(current).exp_mode, pair[3])
        self.assertEqual([i.row() for i in window.review.table.selectionModel().selectedRows()], [current])
        self.assertIn(f"EXP {pair[3]} and FE {pair[0]}", window.review.selection_label.text())

    def test_an_opened_result_also_starts_at_the_top_of_mode_shapes(self):
        _window, panel = self.analysed()
        self.wait(panel)
        self.saved(panel)
        window, _again = self.reopened()
        self.app.processEvents()
        self.assertIs(window.review.views.currentWidget(), window.review.shapes_area)
        self.assertEqual(window.review.shapes_area.verticalScrollBar().value(), 0)

    def test_old_project_files_still_open_and_the_format_is_unchanged(self):
        self.assertEqual(ap.SCHEMA, "universal/analysis-project/v1")

    def test_mac_points_of_a_saved_comparison_shows_what_is_stored(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        self.compare(panel)
        self.wait(panel)
        self.saved(panel)
        window, again = self.reopened()
        mac = window.mac_points
        self.assertEqual(again.tables["pairs"].rowCount(), reg3.RECORDS)
        self.assertTrue(mac.badge.isHidden())
        self.assertIsNone(mac.point_table)
        self.assertEqual(mac.coverage_table.rowCount(), reg3.RECORDS)
        self.assertEqual(mac.pair_status.text(), mp.NEEDS_SOURCE)
        self.assertFalse(mac.show_pair_images(0))


class MacPointsTests(_Flow):
    def test_without_a_registration_the_reason_is_shown_and_nothing_is_made_up(self):
        window, panel = self.analysed()
        mac = window.mac_points
        self.assertFalse(mac.badge.isHidden())
        self.assertEqual(mac.reason.text(), mp.REASONS[am.REFUSED])
        self.assertIsNone(panel.comparison_tabs)
        self.assertNotIn("mac", panel.tables)
        self.assertIsNone(mac.point_table)
        self.assertTrue(window.stack.widget(pw.MAC_PAGE).widget().isAncestorOf(panel.registration_button))

    def test_the_measured_points_are_shown_with_no_registration(self):
        window, panel = self.analysed()
        mac = window.mac_points
        mode = panel.measured_mode()
        self.assertIsNone(panel.analysis.comparison)
        self.assertEqual(mac.measured_table.rowCount(), len(mode.node_ids))
        self.assertEqual(mac.measured_table.item(0, 0).text(), str(mode.node_ids[0]))
        self.assertIsNotNone(mac.measured_image.source)
        self.assertTrue(mac.measured_actions.copy_button.isEnabled())
        self.assertIn(f"{len(mode.node_ids)} points", mac.measured_status.text())
        self.assertNotIn("MAC", " ".join(mp.MEASURED_HEADERS))
        self.assertFalse(mac.badge.isHidden())

    def test_a_saved_result_says_the_measured_points_need_the_sources(self):
        _window, panel = self.analysed()
        self.wait(panel)
        self.saved(panel)
        window, _again = self.reopened()
        self.assertEqual(window.mac_points.measured_status.text(), mp.MEASURED_NEEDS_SOURCE)
        self.assertIsNone(window.mac_points.measured_table)

    def test_the_provisional_reason_and_every_outcome_have_their_own_text(self):
        for outcome in (am.PROVISIONAL, am.REFUSED, am.FAILED, am.NOT_CONFIRMED):
            stub = mock.Mock(comparison=None, registration_outcome=outcome)
            self.assertEqual(mp.unavailable_reason(stub, False), mp.REASONS[outcome])
        self.assertIn("FRF peak", mp.REASONS[am.PROVISIONAL])

    def test_the_evidence_levels_stay_separate(self):
        window, panel = self.analysed()
        self.wait(panel)
        table = window.mac_points.evidence_table
        rows = cells(table)
        self.assertEqual([row[0] for row in rows],
                         ["Frequency-based candidate selection", "MAC-based modal identity diagnostics",
                          "User-confirmed registration", "Physically validated archived evidence"])
        self.assertEqual(rows[1][1], "Not available")
        self.assertEqual(rows[2][1], "None applied")
        self.assertEqual(rows[3][1], "None applied")
        window.review.swap_with_next(0)
        self.wait(panel)
        window.show_page(pw.MAC_PAGE)
        rows = cells(window.mac_points.evidence_table)
        self.assertIn(rv.USER_HYPOTHESIS, rows[0][1])
        self.assertEqual(rows[1][1], "Not available")  # a manual choice opens no gate
        self.assertEqual(rows[2][1], "None applied")
        self.assertIsNone(panel.analysis.comparison)

    def compared(self):
        window, panel = self.analysed()
        self.confirmed(panel)
        self.compare(panel)
        self.wait(panel)
        self.assertEqual(panel.analysis.status, am.CONFIRMED_COMPARISON)
        return window, panel

    def test_a_comparison_shows_pairs_mac_points_and_coverage(self):
        window, panel = self.compared()
        mac = window.mac_points
        self.assertEqual([panel.comparison_tabs.tabText(i) for i in range(panel.comparison_tabs.count())],
                         ["Mode pairs", "MAC", "Candidates", "Unmatched modes", "Close modes",  # ABM-AUD-4
                          "Registered points", "Mapping diagnostics", "Line profile"])
        self.assertTrue(panel.mac_actions.copy_button.isEnabled())
        result = panel.analysis.comparison_result
        self.assertEqual(mac.point_table.rowCount(), len(result.experimental.modes[0].node_ids))
        self.assertEqual(mac.coverage_table.rowCount(), reg3.RECORDS)
        rows = cells(mac.point_table)
        mapped = np.asarray(result.abaqus.modes[0].node_ids)[np.asarray(result.geometry.experimental_to_abaqus)]
        self.assertEqual([row[4] for row in rows], [str(node) for node in mapped])
        self.assertEqual(rows[0][0], str(result.experimental.modes[0].node_ids[0]))
        self.assertNotIn("MAC", " ".join(mp.POINT_HEADERS))  # no value per point
        evidence = cells(mac.evidence_table)
        self.assertEqual(evidence[2][1], "Applied to this result")
        self.assertEqual(evidence[3][1], "None applied")

    def test_the_comparator_result_is_never_saved(self):
        _window, panel = self.compared()
        self.saved(panel)
        with zipfile.ZipFile(self.project) as archive:
            self.assertNotIn("comparison_result", json.dumps(json.loads(archive.read(ap.PROJECT))))

    def test_clicking_a_pair_draws_its_pictures(self):
        window, panel = self.compared()
        mac = window.mac_points
        panel._pair_clicked(1)
        self.assertTrue(window.wait_for_reads())
        self.assertTrue(all(image.source is not None for image in mac.pair_images))

    def test_a_profile_is_drawn_only_for_a_measured_component(self):
        window, panel = self.compared()
        mac = window.mac_points
        self.assertTrue(mac.lines)
        self.assertTrue(all(len(line.indices) >= 3 for line in mac.lines))
        mac.axis_combo.setCurrentIndex(2)  # the fixture measures Z
        self.assertIsNotNone(mac.profile_image.source)
        pair = panel.analysis.comparison_result.pairs[0]
        points = np.asarray(pair.coordinates)
        for line in mac.lines:
            others = [a for a in range(3) if a != line.axis]
            spread = np.ptp(points[list(line.indices)][:, others], axis=0)
            self.assertTrue((spread < 1e-2).all())
        masked = mock.Mock(wraps=pair)
        masked.measured_dof_mask = np.zeros_like(np.asarray(pair.abaqus_vector), dtype=bool)
        masked.abaqus_vector, masked.experimental_vector = pair.abaqus_vector, pair.experimental_vector
        self.assertIsNone(mp.profile_plot(masked, mac.lines[0], 0))


class MaterialsTests(_Flow):
    def test_the_page_states_what_is_missing_and_issues_no_value(self):
        window = self.window()
        workspace = window.materials_workspace
        rows = cells(workspace.property_table)
        self.assertEqual([row[0] for row in rows], list(mw.INPUT_PROPERTIES))
        for row in rows:
            self.assertEqual(row[1:], [mw.NOT_STORED, mw.NOT_PROVIDED, mw.NOT_ISSUED])
        self.assertIn("INP or CAE", workspace.material_statement.text())
        text = " ".join(mw.WORKFLOW)
        self.assertIn("explicitly authorized", text)
        self.assertIn("scientific refusal", text)
        self.assertEqual(window.materials.table.item(0, 1).text(), "Not identified")

    def test_its_files_are_its_own_and_start_nothing(self):
        window = self.window()
        workspace = window.materials_workspace
        self.assertTrue(workspace.choose_file(FE, str(self.odb)))
        self.assertTrue(workspace.choose_file(EXPERIMENTAL, str(self.unv(base.plate_nodes()))))
        self.assertTrue(window.wait_for_reads())
        self.assertEqual(window.analyze.paths, {FE: None, EXPERIMENTAL: None})
        self.assertIsNone(window.analyze.analysis)
        self.assertIn(mw.NO_PACKAGE, workspace.fact_notes[FE].text())
        rows = dict(cells(workspace.fact_tables[FE]))
        self.assertEqual(rows["FE package"], "Not found")
        self.assertEqual(rows["INP beside the ODB"], "None found")
        self.assertEqual(workspace.fact_tables[EXPERIMENTAL].item(0, 1).text(), "exp data.unv")
        self.assertEqual(self.consents, [])

    def test_a_wrong_file_is_refused(self):
        workspace = self.window().materials_workspace
        self.assertFalse(workspace.choose_file(FE, str(self.root / "x.unv")))
        self.assertFalse(workspace.message.isHidden())

    def test_a_package_of_this_odb_gives_the_geometry_without_the_mode_files(self):
        window, panel = self.analysed()
        self.wait(panel)
        manifest = Path(panel.inputs.full_fe.manifest_path)
        self.odb.with_suffix(".inp").write_text("*Heading\n", encoding="utf-8")
        found = dict(mw.read_fe_facts(self.odb, threading.Event()).rows)
        self.assertEqual(found["Nodes"], str(len(self.nodes())))
        self.assertIn("Found", found["FE package"])
        self.assertEqual(found["INP beside the ODB"], f"{self.odb.stem}.inp exists but was not parsed")
        for mode_file in manifest.parent.glob("mode_*.csv"):
            mode_file.rename(mode_file.with_suffix(".hidden"))  # the geometry facts do not need them
        table = dict(mw.geometry_facts(manifest))
        self.assertEqual(table["Nodes"], str(len(self.nodes())))
        self.assertIn("X extent", table)
        self.assertEqual(table["Units"], "Not stated by the extracted data")
        self.assertNotIn("E1", table)

    def test_reusing_the_files_of_analyze(self):
        window, panel = self.analysed()
        self.wait(panel)
        workspace = window.materials_workspace
        self.assertTrue(workspace.use_analyze_files())
        self.assertTrue(window.wait_for_reads())
        self.assertEqual(workspace.paths, panel.paths)
        self.assertIsNotNone(workspace.facts[FE])
        self.assertIsNotNone(workspace.facts[EXPERIMENTAL])

    def test_reusing_a_saved_result_looks_at_no_path(self):
        _window, panel = self.analysed()
        self.wait(panel)
        self.saved(panel)
        window, again = self.reopened()
        with mock.patch("pathlib.Path.is_file", side_effect=AssertionError("no path is looked at")), \
                mock.patch("services.odb_import_service.hash_file", side_effect=AssertionError("no hash")):
            self.assertTrue(window.materials_workspace.use_analyze_files())
        self.assertFalse(window.materials_workspace.busy())
        self.assertIn("not looked at", window.materials_workspace.fact_notes[FE].text())

    def test_nothing_to_reuse_is_said(self):
        workspace = self.window().materials_workspace
        self.assertFalse(workspace.use_analyze_files())
        self.assertFalse(workspace.message.isHidden())


class SourceGuards(unittest.TestCase):
    def test_the_new_pages_install_nothing_and_run_no_solver(self):
        root = Path(__file__).resolve().parents[1] / "src" / "new_gui"
        for name in ("review_model.py", "review_panel.py", "mac_points_model.py", "mac_points_panel.py",
                     "materials_workspace_model.py", "materials_workspace.py"):
            text = (root / name).read_text(encoding="utf-8")
            for forbidden in ("install_", "subprocess", "run_extraction", "compare_modal_datasets", "modal_assurance_criterion"):
                self.assertNotIn(forbidden, text, name)


if __name__ == "__main__":
    unittest.main()
