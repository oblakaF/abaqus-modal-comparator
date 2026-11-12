"""ABM-PLATE-POINT-MAC-GUI-1: "Run trial MAC" on the MAC / Points page. Synthetic plate; Qt ``offscreen``; no Abaqus."""

from __future__ import annotations

import threading
import time
from unittest import mock
import unittest
import zipfile

import numpy as np

import test_trial_point_mac as plate
import test_universal_two_file_analysis as base
import test_working_draft_r2_project as r2

from PySide6.QtWidgets import QLabel

from new_gui import analyze_model as am
from new_gui import mac_points_model as mp
from new_gui import production_window as pw
from new_gui.workspace_state import EXPERIMENTAL, FE
from services import analysis_project as ap
from services import trial_point_mac as tp

FREQUENCIES = (21.0, 42.0, 63.0, 84.0)


def cells(table) -> list:
    return [[table.item(r, c).text() for c in range(table.columnCount())] for r in range(table.rowCount())]


class _Flow(r2._Project):
    nodes = staticmethod(plate.fe_nodes)

    def modes(self):
        nodes = self.nodes()
        xyz = np.array([n[1:] for n in nodes])
        modes = [(i + 1, 0.0011 + 0.0001 * i, shape) for i, shape in enumerate(base.rigid_shapes(nodes))]
        for k in range(19):
            vectors = np.zeros_like(xyz)
            vectors[:, 2] = plate.field(k, xyz[:, 0], xyz[:, 1])
            modes.append((7 + k, 20.0 * (k + 1), vectors))
        return modes

    def measured(self, name="plate scan.unv"):
        return base.write_unv(self.inputs / name, plate.experimental_nodes(), FREQUENCIES,
                              shapes=plate.experimental_shapes(len(FREQUENCIES)))

    def ready(self):
        window, panel = self.analysed(unv=self.measured())
        window.show_page(pw.MAC_PAGE)
        self.app.processEvents()
        return window, panel, window.mac_points.trial

    def finish(self, card, timeout=120.0):
        end = time.monotonic() + timeout
        while (card.busy() or card._cancel is not None) and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()
        self.assertFalse(card.busy())

    def ran(self):
        window, panel, card = self.ready()
        self.assertTrue(card.run())
        self.finish(card)
        self.assertIsNotNone(card.run_result, card.status.text())
        return window, panel, card


class AvailabilityTests(_Flow):
    def test_without_a_result_the_action_is_off_and_says_why(self):
        window = self.window()
        card = window.mac_points.trial
        self.assertEqual(card.run_button.text(), "Run trial MAC")
        self.assertFalse(card.run_button.isEnabled())
        self.assertEqual(card.status.text(), mp.TRIAL_NEEDS_RESULT)
        self.assertFalse(card.run())
        self.assertTrue(card.results.isHidden())

    def test_frf_peak_records_and_saved_results_are_refused_in_words(self):
        provisional = mock.Mock(registration_outcome=am.PROVISIONAL, experimental_rows=())
        fitted = mock.Mock(registration_outcome=am.REFUSED, experimental_rows=())
        self.assertEqual(mp.trial_problem(provisional, object(), False), mp.TRIAL_NEEDS_FITTED)
        self.assertEqual(mp.trial_problem(fitted, object(), True), mp.TRIAL_NEEDS_SOURCE)
        self.assertEqual(mp.trial_problem(fitted, None, False), mp.TRIAL_NEEDS_RESULT)
        self.assertEqual(mp.trial_problem(fitted, object(), False), "")

    def test_a_saved_result_cannot_start_the_trial(self):
        _window, panel, card = self.ran()
        self.saved(panel)
        with zipfile.ZipFile(self.project) as archive:  # nothing of the trial is in the saved result
            for name in archive.namelist():
                data = archive.read(name)
                for word in (b"EXPLORATORY", b"UNCONFIRMED", b"trial", b"Trial", b"T1_C"):
                    self.assertNotIn(word, data, name)
        window, _again = self.reopened()
        card = window.mac_points.trial
        self.assertFalse(card.run_button.isEnabled())
        self.assertEqual(card.status.text(), mp.TRIAL_NEEDS_SOURCE)
        with mock.patch.object(tp, "run_trials", side_effect=AssertionError("no trial on a saved result")):
            self.assertFalse(card.run())
        self.assertIsNone(card.run_result)


class RunTests(_Flow):
    def test_the_action_shows_the_forty_placements_and_the_services_own_values(self):
        window, panel, card = self.ran()
        run = card.run_result
        expected = tp.run_trials(*mp.trial_modes(panel.inputs, panel.analysis))
        self.assertEqual(len(run.trials), 40)
        self.assertEqual(run.fe_numbers, tuple(range(7, 21)))
        self.assertEqual(run.experimental_numbers, (1, 2, 3, 4))
        rows = cells(card.mapping_table)
        self.assertEqual([row[0] for row in rows], [t.name for t in expected.trials])
        for row, trial in zip(rows, expected.trials):
            self.assertEqual(row[5:9], ["25 of 25", "25", f"{trial.rms_distance:.3f}", f"{trial.max_distance:.3f}"])
            self.assertEqual(row[10], "Mapped")
        self.assertEqual(card.trial_combo.count(), 40)
        for index in (0, 7, 23, 39):  # each placement can be inspected: its own matrix, to four decimals
            card.trial_combo.setCurrentIndex(index)
            self.app.processEvents()
            trial = expected.trials[index]
            shown = cells(card.matrix_table)
            self.assertEqual(len(shown), 4)
            for i, row in enumerate(shown):
                self.assertTrue(row[0].startswith(f"EXP {i + 1} "))
                self.assertEqual(row[1:], [f"{value:.4f}" for value in trial.mac[i]])
            self.assertIsNotNone(card.shape_image.source)
        np.testing.assert_array_equal(run.trial("T1_C").mac, expected.trial("T1_C").mac)
        self.assertGreater(run.trial("T1_C").mac[0, 0], 0.9)  # the shapes were made at T1; shown, never chosen
        self.assertEqual(card.trial_combo.currentIndex(), 39)

    def test_the_mode_shape_comparison_follows_the_three_choices(self):
        _window, _panel, card = self.ran()
        first = card.shape_image.data
        self.assertTrue(first)
        card.exp_combo.setCurrentIndex(2)
        second = card.shape_image.data
        card.fe_combo.setCurrentIndex(5)
        third = card.shape_image.data
        card.trial_combo.setCurrentIndex(6)
        self.assertEqual(len({first, second, third, card.shape_image.data}), 4)
        self.assertTrue(card.shape_actions.copy_button.isEnabled())

    def test_the_families_are_shown_side_by_side_and_none_is_marked(self):
        _window, _panel, card = self.ran()
        self.assertEqual(card.run_result.families, (("T0_C", "T2_C", "B0_C", "B2_C"), ("T1_C", "T3_C", "B1_C", "B3_C")))
        text = card.family_text.text()
        self.assertIn("Family A: T0_C, T2_C, B0_C, B2_C", text)
        self.assertIn("Family B: T1_C, T3_C, B1_C, B3_C", text)
        self.assertIsNotNone(card.family_image.source)
        self.assertGreater(card.family_image.source.width(), card.family_image.source.height())  # two matrices in a row
        shown = " ".join(label.text() for label in card.findChildren(QLabel)).lower()
        for word in ("best", "preferred", "recommended", "most likely", "correct placement", "validated", "verified"):
            self.assertNotIn(word, shown, word)
        self.assertEqual(card.trial_combo.currentIndex(), 0)  # the first of the fixed order, not a choice by value

    def test_every_part_of_the_result_carries_the_label(self):
        _window, _panel, card = self.ran()
        label = "EXPLORATORY MAC — UNCONFIRMED GEOMETRIC MAPPING"
        badges = [w for w in card.findChildren(QLabel) if w.objectName() == "badge"]
        self.assertEqual([b.text() for b in badges], [label] * 4)  # the card, the mapping, the families, one placement
        self.assertTrue(all(not b.isHidden() for b in badges))
        self.assertEqual(card.run_result.label, label)

    def test_the_results_do_not_make_the_page_scroll_sideways(self):
        window, _panel, card = self.ran()
        for size in ((900, 680), (1366, 768)):
            window.resize(*size)
            self.app.processEvents()
            area = window.stack.currentWidget()
            self.assertFalse(card.results.isHidden())
            self.assertEqual(area.horizontalScrollBar().maximum(), 0, size)

    def test_the_normal_result_stays_registration_required_with_no_pair(self):
        window, panel, card = self.ran()
        mac = window.mac_points
        self.assertEqual(panel.analysis.status, am.REGISTRATION_REQUIRED)
        self.assertIsNone(panel.analysis.comparison)
        self.assertIsNone(panel.comparison_tabs)
        self.assertNotIn("mac", panel.tables)
        self.assertIsNone(mac.result)
        self.assertIsNone(mac.point_table)
        self.assertFalse(mac.badge.isHidden())
        self.assertEqual(mac.badge.text(), mp.UNAVAILABLE_BADGE)
        self.assertEqual(mac.reason.text(), mp.REASONS[am.REFUSED])
        self.assertTrue(mac.readiness_answers()["MAC"].startswith("No"))
        self.assertTrue(mac.pair_card.isHidden())
        self.assertEqual(cells(mac.evidence_table)[1][1], "Not available")
        self.assertEqual(panel.registration_kind(), ap.KIND_NONE)
        self.assertEqual(len(panel.review_state.manual), 0)
        self.assertIsNone(panel.confirmation)
        self.assertFalse(card.isAncestorOf(panel.registration_box))
        self.assertFalse(card.isAncestorOf(panel.comparison_box))

    def test_no_process_and_no_extraction_are_started(self):
        window, panel, card = self.ready()
        calls = len(self.runner.calls)
        with mock.patch("subprocess.Popen", side_effect=AssertionError("no process")) as popen, \
                mock.patch("subprocess.run", side_effect=AssertionError("no process")) as run:
            self.assertTrue(card.run())
            self.assertTrue(window.busy())
            self.finish(card)
        self.assertIsNotNone(card.run_result, card.status.text())
        self.assertEqual((popen.call_count, run.call_count, len(self.runner.calls)), (0, 0, calls))

    def test_the_source_files_are_unchanged(self):
        window, panel, card = self.ready()
        def state() -> dict:  # the ODB, the UNV, the FE package and everything else the test made: nothing new either
            return {str(p): base.sha(p) for p in sorted(self.root.rglob("*")) if p.is_file()}

        before = state()
        self.assertIn(str(self.odb), before)
        self.assertIn(str(self.exp_path), before)
        self.assertGreater(len(before), 20)
        self.assertTrue(card.run())
        self.finish(card)
        self.assertIsNotNone(card.run_result)
        self.assertEqual(state(), before)


class SafetyTests(_Flow):
    def test_cancel_stops_the_worker_and_shows_nothing(self):
        window, _panel, card = self.ready()
        started = threading.Event()

        def slow(_fe, _experimental, cancel_event=None, *_more):
            started.set()
            cancel_event.wait(30)
            raise tp.TrialCancelled()

        with mock.patch.object(tp, "run_trials", side_effect=slow):
            self.assertTrue(card.run())
            self.assertFalse(card.run_button.isEnabled())
            self.assertTrue(card.cancel_button.isEnabled())
            self.assertFalse(card.run())  # one calculation at a time
            self.assertTrue(started.wait(30))
            card.cancel()
            self.finish(card)
        self.assertIsNone(card.run_result)
        self.assertIsNone(card.mapping_table)
        self.assertEqual(card.status.text(), mp.TRIAL_CANCELLED)
        self.assertTrue(card.results.isHidden())
        self.assertTrue(card.run_button.isEnabled())
        self.assertFalse(window.busy())

    def test_a_file_changed_after_the_read_gives_no_value(self):
        _window, _panel, card = self.ready()
        self.exp_path.write_text(self.exp_path.read_text() + "\n")
        with mock.patch.object(tp, "run_trials", side_effect=AssertionError("changed sources are not used")):
            self.assertTrue(card.run())
            self.finish(card)
        self.assertIsNone(card.run_result)
        self.assertEqual(card.status.text(), am.STALE_TEXT)
        self.assertTrue(card.results.isHidden())

    def test_a_file_changed_during_the_calculation_gives_no_value(self):
        _window, _panel, card = self.ready()
        real = tp.run_trials

        def then_changed(*args, **kwargs):
            run = real(*args, **kwargs)
            self.exp_path.write_text(self.exp_path.read_text() + "\n")
            return run

        with mock.patch.object(tp, "run_trials", side_effect=then_changed):
            self.assertTrue(card.run())
            self.finish(card)
        self.assertIsNone(card.run_result)
        self.assertEqual(card.status.text(), am.STALE_TEXT)

    def test_a_new_analysis_removes_the_trial_values(self):
        _window, panel, card = self.ran()
        self.run_analysis(panel)
        self.assertEqual(panel.analysis.status, am.REGISTRATION_REQUIRED)
        self.assertIsNone(card.run_result)
        self.assertIsNone(card.matrix_table)
        self.assertTrue(card.results.isHidden())
        self.assertEqual(card.status.text(), "")
        self.assertTrue(card.run_button.isEnabled())

    def test_a_result_for_replaced_data_is_never_shown(self):
        _window, panel, card = self.ready()
        release = threading.Event()
        real = tp.run_trials

        def held(*args, **kwargs):
            release.wait(30)
            return real(*args, **kwargs)

        with mock.patch.object(tp, "run_trials", side_effect=held):
            self.assertTrue(card.run())
            panel.choose_file(EXPERIMENTAL, str(self.measured("another scan.unv")))  # the result shown is gone
            self.app.processEvents()
            release.set()
            self.finish(card)
        self.assertIsNone(card.run_result)
        self.assertTrue(card.results.isHidden())
        self.assertFalse(card.run_button.isEnabled())

    def test_data_the_trial_is_not_defined_for_are_refused_in_words(self):
        window, panel = self.analysed()  # the base fixture: experimental points on the FE nodes' own labels, random shapes
        card = window.mac_points.trial
        self.assertTrue(card.run_button.isEnabled())
        self.assertTrue(card.run())
        self.finish(card)
        self.assertIsNone(card.run_result)
        self.assertTrue(card.status.text())
        self.assertTrue(card.results.isHidden())
        self.assertEqual(panel.analysis.status, am.REGISTRATION_REQUIRED)

    def test_closing_the_window_stops_the_trial(self):
        window, _panel, card = self.ready()

        def slow(_fe, _experimental, cancel_event=None, *_more):
            cancel_event.wait(30)
            raise tp.TrialCancelled()

        with mock.patch.object(tp, "run_trials", side_effect=slow):
            self.assertTrue(card.run())
            window.close()
            self.finish(card)
        self.assertIsNone(card.run_result)


if __name__ == "__main__":
    unittest.main()
