"""ABM-PLATE-POINT-MAC-GUI-1: "Run trial MAC" on the MAC / Points page. Synthetic plate; Qt ``offscreen``; no Abaqus."""

from __future__ import annotations

import csv
import gc
import io
import json
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
from new_gui import mac_points_panel as panel_module
from new_gui import production_window as pw
from new_gui.workspace_state import EXPERIMENTAL, FE
from services import analysis_project as ap
from services import trial_mac_export as te
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


class ExportTests(_Flow):
    """TRIAL-MAC-EXPORT-1: "Export all Trial MAC..." writes the values shown, of the data shown, and nothing else."""

    def export(self, card, path, expect=True):
        card.ask_export_path = lambda: str(path)
        self.assertEqual(card.export(), expect)
        end = time.monotonic() + 120.0
        while (card.busy() or card._exporting is not None) and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()
        self.assertIsNone(card._exporting)

    def left(self) -> list:
        return sorted(p.name for p in self.inputs.iterdir() if p.suffix in (".zip", ".partial"))

    def test_the_button_is_off_until_a_trial_is_shown_and_while_one_runs(self):
        window, _panel, card = self.ready()
        self.assertEqual(card.export_button.text(), "Export all Trial MAC...")
        self.assertFalse(card.export_button.isEnabled())  # analyzed, but no trial yet
        asked = []
        card.ask_export_path = lambda: asked.append(1) or str(self.inputs / "early.zip")
        self.assertFalse(card.export())
        release = threading.Event()
        real = tp.run_trials

        def held(*args, **kwargs):
            release.wait(30)
            return real(*args, **kwargs)

        with mock.patch.object(tp, "run_trials", side_effect=held):
            self.assertTrue(card.run())
            self.assertFalse(card.export_button.isEnabled())  # during the calculation
            self.assertFalse(card.export())
            release.set()
            self.finish(card)
        self.assertIsNotNone(card.run_result)
        self.assertTrue(card.export_button.isEnabled())
        self.assertEqual((asked, self.left()), ([], []))
        self.assertFalse(self.window().mac_points.trial.export_button.isEnabled())  # no result at all

    def test_the_archive_holds_the_forty_placements_of_the_run_shown(self):
        _window, panel, card = self.ran()
        run, target = card.run_result, self.inputs / "all trials"  # no suffix given: .zip is added
        self.export(card, target)
        target = target.with_name("all trials.zip")
        self.assertEqual(card.export_status.text(), f"Exported to {target}")
        self.assertFalse(card.export_status.isHidden())
        self.assertEqual(self.left(), ["all trials.zip"])
        with zipfile.ZipFile(target) as archive:
            self.assertIsNone(archive.testzip())
            names = archive.namelist()
            self.assertEqual(names, ["README.txt", "manifest.json", "placements.csv", "point_mapping.csv", "families.csv"]
                             + [f"matrices/{t.name}.csv" for t in run.trials])
            manifest = json.loads(archive.read("manifest.json"))
            readme = archive.read("README.txt").decode("utf-8-sig")
            for trial in run.trials:
                rows = list(csv.reader(io.StringIO(archive.read(f"matrices/{trial.name}.csv").decode("utf-8-sig"))))
                self.assertEqual([r[0] for r in rows[1:]], ["EXP 1", "EXP 2", "EXP 3", "EXP 4"])
                self.assertEqual([h.split(" (")[0] for h in rows[0][2:]], [f"FE {n}" for n in range(7, 21)])
                np.testing.assert_array_equal(np.array([[float(v) for v in r[2:]] for r in rows[1:]]), trial.mac)
            points = list(csv.reader(io.StringIO(archive.read("point_mapping.csv").decode("utf-8-sig"))))
            self.assertEqual(len(points), 1 + 40 * 25)
            self.assertEqual({r[0] for r in points[1:]}, {"UNCONFIRMED"})
            for data in (archive.read(n) for n in names):  # the source files are not in the archive
                self.assertNotEqual(data, self.exp_path.read_bytes())
        self.assertTrue(readme.startswith("EXPLORATORY MAC — UNCONFIRMED GEOMETRIC MAPPING"))
        self.assertEqual(manifest["label"], "EXPLORATORY MAC — UNCONFIRMED GEOMETRIC MAPPING")
        sources = manifest["sources"]
        self.assertEqual((sources["experimental"]["verified_at_export"], sources["experimental"]["sha256"]),
                         (True, base.sha(self.exp_path)))
        self.assertEqual(sources["experimental"]["path"], str(self.exp_path))
        package = panel.inputs.identities["fe"]["package"]
        self.assertEqual((sources["fe_package"]["verified_at_export"], sources["fe_package"]["package_sha256"]),
                         (True, package["package_sha256"]))
        self.assertEqual(len(sources["fe_package"]["files"]), len(package["files"]))
        self.assertEqual((sources["odb"]["verified_at_export"], sources["odb"]["check"], sources["odb"]["recorded_sha256"]),
                         (True, "SOURCE_UNCHANGED", base.sha(self.odb)))  # hashed again by the existing source check
        self.assertIn("the ODB was hashed again", readme)
        self.assertEqual(manifest["modal_set"]["index"], panel.analysis.set_index)
        self.assertEqual(manifest["modal_set"]["record_count"], 4)
        self.assertEqual(manifest["rigid_body_fe_modes_excluded"], sorted(int(n) for n in panel.analysis.rigid_modes))
        self.assertEqual([m["number"] for m in manifest["fe_modes"]], list(run.fe_numbers))
        self.assertEqual([m["frequency_hz"] for m in manifest["experimental_modes"]], list(run.experimental_frequencies))

    def test_an_odb_that_no_longer_matches_the_package_is_never_stated_as_verified(self):
        _window, _panel, card = self.ran()
        recorded = base.sha(self.odb)
        self.odb.write_bytes(self.odb.read_bytes() + b"later")  # the package read is still the package: the values stand
        target = self.inputs / "odb changed.zip"
        self.export(card, target)
        self.assertEqual(card.export_status.text(), f"Exported to {target}")
        with zipfile.ZipFile(target) as archive:
            odb = json.loads(archive.read("manifest.json"))["sources"]["odb"]
            readme = archive.read("README.txt").decode("utf-8-sig")
        self.assertEqual((odb["verified_at_export"], odb["check"], odb["recorded_sha256"]), (False, "SOURCE_CHANGED", recorded))
        self.assertIn("the ODB identity is only the one recorded with the package and was not verified by this export", readme)
        self.assertNotIn("the ODB was hashed again", readme)

    def test_exporting_changes_no_status_no_pair_and_no_value(self):
        window, panel, card = self.ran()
        run, analysis, mac = card.run_result, panel.analysis, window.mac_points
        matrices = [t.mac.copy() for t in run.trials]
        shown = (cells(card.mapping_table), cells(card.matrix_table), card.summary.text(), card.family_text.text(),
                 mac.badge.text(), mac.reason.text(), mac.readiness_answers(), cells(mac.evidence_table))
        calls = len(self.runner.calls)
        with mock.patch.object(tp, "run_trials", side_effect=AssertionError("nothing is recomputed")), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("no process")) as popen, \
                mock.patch("subprocess.run", side_effect=AssertionError("no process")) as started:
            self.export(card, self.inputs / "unchanged.zip")
        self.assertTrue(card.export_status.text().startswith("Exported to "), card.export_status.text())
        self.assertEqual((popen.call_count, started.call_count, len(self.runner.calls)), (0, 0, calls))
        self.assertIs(card.run_result, run)
        self.assertIs(panel.analysis, analysis)
        for trial, before in zip(run.trials, matrices):
            np.testing.assert_array_equal(trial.mac, before)
        self.assertEqual((cells(card.mapping_table), cells(card.matrix_table), card.summary.text(), card.family_text.text(),
                          mac.badge.text(), mac.reason.text(), mac.readiness_answers(), cells(mac.evidence_table)), shown)
        self.assertEqual(panel.analysis.status, am.REGISTRATION_REQUIRED)
        self.assertIsNone(panel.analysis.comparison)
        self.assertEqual(panel.registration_kind(), ap.KIND_NONE)
        self.assertEqual(len(panel.review_state.manual), 0)
        self.assertIsNone(panel.confirmation)
        self.assertIsNone(mac.result)
        self.assertTrue(card.export_button.isEnabled())  # and it can be exported again, to another file
        self.assertTrue(card.run_button.isEnabled())

    def test_the_source_files_are_unchanged_and_only_the_archive_is_new(self):
        _window, _panel, card = self.ran()

        def state() -> dict:
            return {str(p): base.sha(p) for p in sorted(self.root.rglob("*")) if p.is_file()}

        before, target = state(), self.inputs / "only this.zip"
        self.export(card, target)
        after = state()
        self.assertEqual(set(after) - set(before), {str(target)})
        self.assertEqual({k: v for k, v in after.items() if k in before}, before)

    def test_a_cancelled_file_choice_writes_nothing(self):
        _window, _panel, card = self.ran()
        card.ask_export_path = lambda: ""
        self.assertFalse(card.export())
        self.assertIsNone(card._exporting)
        self.assertEqual((card.export_status.text(), self.left()), ("", []))
        self.assertIsNotNone(card.run_result)
        self.assertTrue(card.export_button.isEnabled())

    def test_an_existing_archive_is_not_replaced_and_the_message_says_so(self):
        _window, _panel, card = self.ran()
        target = self.inputs / "kept.zip"
        target.write_bytes(b"an earlier export")
        self.export(card, target)
        self.assertIn("already exists and is not replaced", card.export_status.text())
        self.assertTrue(card.export_status.text().startswith("Not exported: "))
        self.assertEqual(target.read_bytes(), b"an earlier export")
        self.assertEqual(self.left(), ["kept.zip"])
        self.assertIsNotNone(card.run_result)  # the values are still those of the files read
        self.export(card, self.inputs / "new name.zip")
        self.assertEqual(self.left(), ["kept.zip", "new name.zip"])
        self.assertTrue(card.export_status.text().startswith("Exported to "))

    def test_a_write_failure_is_said_and_leaves_no_partial_archive(self):
        _window, _panel, card = self.ran()
        with mock.patch.object(zipfile.ZipFile, "writestr", side_effect=OSError("disk full")):
            self.export(card, self.inputs / "broken.zip")
        self.assertTrue(card.export_status.text().startswith("Not exported: "))
        self.assertIn("disk full", card.export_status.text())
        self.assertEqual(self.left(), [])
        self.export(card, self.inputs / "no such folder" / "x.zip")
        self.assertTrue(card.export_status.text().startswith("Not exported: "))
        self.assertIsNotNone(card.run_result)
        self.assertTrue(card.export_button.isEnabled())

    def test_a_source_changed_after_the_trial_is_not_exported_and_the_values_go(self):
        _window, _panel, card = self.ran()
        self.exp_path.write_text(self.exp_path.read_text() + "\n")
        with mock.patch.object(te, "write_archive", side_effect=AssertionError("changed sources are not exported")):
            self.export(card, self.inputs / "stale.zip")
        self.assertEqual(self.left(), [])
        self.assertIsNone(card.run_result)
        self.assertEqual(card.status.text(), am.STALE_TEXT)
        self.assertEqual(card.export_status.text(), "")
        self.assertTrue(card.results.isHidden())
        self.assertFalse(card.export_button.isEnabled())

    def test_a_source_changed_while_the_archive_is_written_leaves_no_archive(self):
        _window, _panel, card = self.ran()
        real = te.build_files

        def then_changed(*args, **kwargs):
            files = real(*args, **kwargs)
            self.exp_path.write_text(self.exp_path.read_text() + "\n")
            return files

        with mock.patch.object(te, "build_files", side_effect=then_changed):
            self.export(card, self.inputs / "late.zip")
        self.assertEqual(self.left(), [])
        self.assertIsNone(card.run_result)
        self.assertEqual(card.status.text(), am.STALE_TEXT)
        self.assertFalse(card.export_button.isEnabled())

    def test_a_new_analysis_or_another_file_turns_the_export_off(self):
        _window, panel, card = self.ran()
        self.assertTrue(card.export_button.isEnabled())
        self.run_analysis(panel)  # the same files analyzed again: the values shown before belong to no current result
        self.assertIsNone(card.run_result)
        self.assertFalse(card.export_button.isEnabled())
        asked = []
        card.ask_export_path = lambda: asked.append(1) or str(self.inputs / "old.zip")
        self.assertFalse(card.export())
        self.assertTrue(card.run())
        self.finish(card)
        self.assertTrue(card.export_button.isEnabled())
        panel.choose_file(EXPERIMENTAL, str(self.measured("another scan.unv")))
        self.app.processEvents()
        self.assertFalse(card.export_button.isEnabled())
        self.assertFalse(card.export())
        self.assertEqual((asked, self.left()), ([], []))

    def test_data_replaced_while_the_file_is_being_chosen_are_not_exported(self):
        _window, panel, card = self.ran()

        def choosing() -> str:  # the dialog is open while the result shown is replaced
            panel.choose_file(EXPERIMENTAL, str(self.measured("another scan.unv")))
            self.app.processEvents()
            return str(self.inputs / "replaced.zip")

        card.ask_export_path = choosing
        with mock.patch.object(mp, "export_trial", side_effect=AssertionError("values of replaced data are not exported")):
            self.assertFalse(card.export())
        self.assertEqual(self.left(), [])
        self.assertIsNone(card._exporting)

    def test_the_export_control_does_not_make_the_page_scroll_sideways(self):
        window, _panel, card = self.ran()
        self.export(card, self.inputs / "wide.zip")
        for size in ((900, 680), (1366, 768)):
            window.resize(*size)
            self.app.processEvents()
            self.assertEqual(window.stack.currentWidget().horizontalScrollBar().maximum(), 0, size)


class SeparationTests(r2._Project):
    """PREVIEW-01-MAC-TRIAL-SEPARATION-01: beside a comparison with mode pairs the exploratory card is closed until it is
    opened on purpose, so its label is not read as the status of the registered comparison."""

    SIZES = ((900, 680), (1366, 768), (1600, 900))

    def setUp(self):
        # the windows of earlier tests are freed here, in the GUI thread: a collection that starts inside a drawing
        # thread would destroy their widgets there
        gc.collect()
        super().setUp()
        self.addCleanup(gc.collect)

    def compared(self):
        window, panel = self.analysed()
        self.confirmed(panel)
        self.compare(panel)
        self.wait(panel)
        self.assertEqual(panel.analysis.status, am.CONFIRMED_COMPARISON)
        window.show_page(pw.MAC_PAGE)
        self.app.processEvents()
        return window, panel, window.mac_points.trial

    def labels(self, card) -> list:
        return [label for label in card.findChildren(QLabel) if label.text() == mp.TRIAL_LABEL]

    def registered(self, window, panel) -> dict:
        mac = window.mac_points
        return {"pairs": cells(panel.tables["pairs"]), "mac": cells(panel.tables["mac"]),
                "evidence": cells(mac.evidence_table), "coverage": cells(mac.coverage_table),
                "tabs": [panel.comparison_tabs.tabText(i) for i in range(panel.comparison_tabs.count())],
                "status": panel.analysis.status, "answers": mac.readiness_answers(),
                "result": panel.analysis.comparison_result, "view": panel.analysis.comparison}

    def test_beside_a_registered_comparison_the_card_is_closed_at_first(self):
        window, panel, card = self.compared()
        self.assertTrue(card.registered())
        self.assertFalse(card.is_open())
        self.assertTrue(card.toggle.isVisible())
        self.assertFalse(card.toggle.isChecked())
        self.assertEqual(card.toggle.text(), panel_module.TRIAL_SHOW)
        self.assertEqual(card.toggle.accessibleName(), panel_module.TRIAL_SHOW)
        self.assertTrue(card.separate.isVisible())
        for words in ("independent of the registered comparison", "does not establish a physical registration"):
            self.assertIn(words, card.separate.text())
            self.assertIn(words, card.toggle.toolTip())
        self.assertIn("starts no calculation", card.toggle.toolTip())
        self.assertTrue(self.labels(card))
        self.assertFalse(any(label.isVisible() for label in self.labels(card)))  # the label is not beside the pairs
        self.assertFalse(card.run_button.isVisible())
        self.assertTrue(panel.tables["pairs"].isVisible())
        self.assertTrue(window.mac_points.badge.isHidden())  # the registered comparison's own state: MAC is available

    def test_opening_and_closing_start_nothing_and_change_nothing_registered(self):
        window, panel, card = self.compared()
        before, token = self.registered(window, panel), card.token
        with mock.patch.object(mp, "run_trial", side_effect=AssertionError("opening starts no trial")), \
                mock.patch.object(tp, "run_trials", side_effect=AssertionError("opening starts no trial")):
            card.toggle.click()
            self.app.processEvents()
            self.assertTrue(card.is_open())
            self.assertEqual(card.toggle.text(), panel_module.TRIAL_HIDE)
            self.assertTrue(self.labels(card)[0].isVisible())  # the warning, whole and unchanged, when open
            self.assertEqual(self.labels(card)[0].text(), tp.LABEL)
            self.assertTrue(card.run_button.isVisible() and card.run_button.isEnabled())
            self.assertTrue(card.separate.isVisible())
            self.assertEqual((card.token, card._cancel, card.run_result, card.busy()), (token, None, None, False))
            opened = self.registered(window, panel)
            card.toggle.click()
            self.app.processEvents()
        self.assertFalse(card.is_open())
        self.assertFalse(card.run_button.isVisible())
        self.assertEqual(card.token, token)
        closed = self.registered(window, panel)
        for name, value in before.items():
            if name in ("result", "view"):
                self.assertIs(opened[name], value)
                self.assertIs(closed[name], value)
            else:
                self.assertEqual(opened[name], value, name)
                self.assertEqual(closed[name], value, name)

    def test_without_a_registered_comparison_the_card_is_as_it_was(self):
        window, panel = self.analysed()
        window.show_page(pw.MAC_PAGE)
        self.app.processEvents()
        card = window.mac_points.trial
        self.assertFalse(card.registered())
        self.assertTrue(card.is_open())
        self.assertFalse(card.toggle.isVisible())
        self.assertFalse(card.separate.isVisible())
        self.assertTrue(self.labels(card)[0].isVisible())
        self.assertTrue(card.run_button.isVisible() and card.run_button.isEnabled())
        self.assertIsNone(panel.analysis.comparison)

    def test_a_saved_comparison_is_closed_and_cannot_run_the_trial_when_opened(self):
        window, panel, _card = self.compared()
        stored = cells(panel.tables["pairs"])
        self.saved(panel)
        window, again = self.reopened()
        window.show_page(pw.MAC_PAGE)
        self.app.processEvents()
        card = window.mac_points.trial
        self.assertIsNotNone(again.snapshot)
        self.assertTrue(card.registered())
        self.assertFalse(card.is_open())
        with mock.patch.object(mp, "run_trial", side_effect=AssertionError("no trial on a saved result")), \
                mock.patch.object(tp, "run_trials", side_effect=AssertionError("no trial on a saved result")):
            card.toggle.click()
            self.app.processEvents()
            self.assertTrue(card.is_open())
            self.assertFalse(card.run_button.isEnabled())
            self.assertFalse(card.export_button.isEnabled())
            self.assertEqual(card.status.text(), mp.TRIAL_NEEDS_SOURCE)
            self.assertTrue(card.status.isVisible())
            card.run_button.click()
            self.assertFalse(card.run())
            self.assertFalse(card.export())
            self.app.processEvents()
        self.assertIsNone(card.run_result)
        self.assertFalse(card.busy())
        self.assertEqual(cells(again.tables["pairs"]), stored)

    def held(self, release):
        def work(_inputs, _analysis, token, _cancel):
            release.wait(30)
            return mp.TrialOutcome(token, cancelled=True)
        return work

    def finish(self, card):
        end = time.monotonic() + 60
        while card.busy() and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()
        self.assertFalse(card.busy())

    def test_a_new_analysis_stops_the_running_trial_and_resets_the_section(self):
        _window, panel, card = self.compared()
        release = threading.Event()
        self.addCleanup(release.set)
        with mock.patch.object(mp, "run_trial", side_effect=self.held(release)):
            card.toggle.click()
            self.assertTrue(card.run())
            self.app.processEvents()
            self.assertFalse(card.toggle.isEnabled())  # not closed over a running trial: Cancel stays in view
            self.assertTrue(card.cancel_button.isVisible() and card.cancel_button.isEnabled())
            token = card.token
            self.run_analysis(panel)  # another result, without a comparison
            self.assertIsNone(panel.analysis.comparison)
            self.assertIsNone(card._cancel)
            self.assertNotEqual(card.token, token)
            self.assertIsNone(card.run_result)
            self.assertFalse(card.toggle.isChecked())
            self.assertFalse(card.toggle.isVisible())
            self.assertTrue(card.is_open())  # no registered comparison: the card as it always was
            self.assertTrue(card.run_button.isEnabled())
            release.set()
            self.finish(card)
        self.assertIsNone(card.run_result)
        self.assertTrue(card.results.isHidden())

    def test_a_comparison_that_arrives_closes_the_section_and_the_same_result_keeps_it_as_set(self):
        window, panel = self.analysed()
        window.show_page(pw.MAC_PAGE)
        card = window.mac_points.trial
        self.assertTrue(card.is_open())
        self.confirmed(panel)
        self.compare(panel)
        self.wait(panel)
        self.assertTrue(card.registered())
        self.assertFalse(card.is_open())
        card.toggle.click()
        self.assertTrue(card.is_open())
        window.show_page(pw.REVIEW_PAGE)  # the same result: what the user opened stays open
        window.show_page(pw.MAC_PAGE)
        window.mac_points.rebuild()
        self.assertTrue(card.is_open())
        self.run_analysis(panel)
        self.assertFalse(card.toggle.isChecked())

    def test_a_trial_still_running_when_the_comparison_arrives_keeps_its_cancel_in_view(self):
        window, panel = self.analysed()
        self.confirmed(panel)
        window.show_page(pw.MAC_PAGE)
        card = window.mac_points.trial
        release = threading.Event()
        self.addCleanup(release.set)
        with mock.patch.object(mp, "run_trial", side_effect=self.held(release)):
            self.assertTrue(card.run())
            self.compare(panel)
            self.wait(panel)
            self.assertTrue(card.registered())
            self.assertIsNotNone(card._cancel)  # the same data: the trial goes on, and can still be cancelled
            self.assertTrue(card.is_open())
            self.assertTrue(card.cancel_button.isVisible() and card.cancel_button.isEnabled())
            card.cancel()
            self.assertTrue(card.toggle.isEnabled())
            release.set()
            self.finish(card)
        self.assertIsNone(card.run_result)

    def settle(self):
        for _ in range(8):
            self.app.processEvents()

    def test_the_section_adds_no_sideways_scroll_of_its_own_and_is_shorter_closed(self):
        window, _panel, card = self.compared()
        for size in self.SIZES:
            window.resize(*size)
            self.settle()
            area = window.stack.currentWidget()
            self.assertFalse(card.is_open())
            card.setVisible(False)  # the page without the card: the comparison's own tables set its width
            self.settle()
            sideways = area.horizontalScrollBar().maximum()
            card.setVisible(True)
            self.settle()
            self.assertEqual(area.horizontalScrollBar().maximum(), sideways, size)
            closed = area.verticalScrollBar().maximum()
            card.toggle.click()
            self.settle()
            self.assertEqual(area.horizontalScrollBar().maximum(), sideways, size)
            self.assertGreater(area.verticalScrollBar().maximum(), closed, size)
            card.toggle.click()
            self.settle()
            self.assertEqual(area.horizontalScrollBar().maximum(), sideways, size)
            self.assertEqual(area.verticalScrollBar().maximum(), closed, size)


if __name__ == "__main__":
    unittest.main()
