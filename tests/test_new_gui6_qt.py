"""NEW-GUI.6: the scientific workbench, the Materials page and the known sources in the PySide6 window (offscreen).

On the synthetic fixture world (G2c / G2d-1, files read through a stand-in of the importer's preview):

- at start every command is disabled with its reason, and the shapes are shown only as unpaired independent views;
- after the check verified the archived registration, Run verified modal comparison shows the comparator's pairs,
  the MAC matrix with the assigned pairs marked, the diagnostics and the drawings of the pair chosen in the table;
- without a verified registration (another set, an FRF set) the comparison stays unavailable, no MAC is shown and the
  diagnostic report can be exported;
- another set, a replaced or cleared file, Inspect again, a new check or a closed window removes a result and discards
  a running comparison (its outcome and its drawings are never shown); a diagnostic waits for a running comparison;
- Export report... writes only into the chosen folder; a cancelled choice writes nothing;
- the Materials page reads the project's records when it is first shown and relates them only to a verified fixture;
- the known-source dialog offers only verified files and works without the local folder.

PySide6 comes from ``requirements-new-gui.txt``; without it these tests are skipped, except with
``NEW_GUI_REQUIRE_QT=1`` (CI).
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

try:
    from PySide6.QtWidgets import QApplication, QPushButton
except ImportError as error:  # pragma: no cover - depends on the environment
    if os.environ.get("NEW_GUI_REQUIRE_QT") == "1":
        raise
    raise unittest.SkipTest(f"PySide6 is not installed ({error}); install requirements-new-gui.txt to run the "
                            "new interface tests (CI sets NEW_GUI_REQUIRE_QT=1 and runs them)")

from new_gui import comparison_model as cm  # noqa: E402
from new_gui import diagnostic_model as dm  # noqa: E402
from new_gui import known_sources as ks  # noqa: E402
from new_gui import materials_model as mm  # noqa: E402
from new_gui import registration_check_model as rm  # noqa: E402
from new_gui import window as window_module  # noqa: E402
from new_gui import workspace_state as ws  # noqa: E402
from test_new_gui5_qt import _Window as _Gui5Window  # noqa: E402
from test_new_gui6_workbench import reporting_restored  # noqa: E402


class _Window(_Gui5Window):
    def setUp(self):
        super().setUp()
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.reports = Path(folder.name)
        self.asked = []
        self.answer = str(self.reports)
        self.window.comparison._ask_folder = lambda: self.asked.append(1) or self.answer
        self.workbench = self.window.comparison

    def verified(self):
        self.ready(0)
        self.click(self.panel.run_button)
        self.assertEqual(self.panel.slot.state, rm.VERIFIED_STATE)

    def compared(self):
        self.verified()
        self.assertTrue(self.workbench.run_button.isEnabled())
        self.assertTrue(self.panel.next_step.isVisible())  # the check applies nothing; the comparison below does
        self.click(self.workbench.run_button)
        self.assertEqual(self.workbench.slot.state, cm.DONE, self.workbench.status.text())


class StartTests(_Window):
    def test_every_command_is_disabled_with_its_reason_and_the_shapes_are_unpaired(self):
        w = self.workbench
        self.assertFalse(w.run_button.isEnabled())
        self.assertFalse(w.export_button.isEnabled())
        self.assertIn(dm.NEED_FE, w.why_unavailable.text())
        self.assertEqual(w.badge.text(), cm.NOT_RUN)
        self.assertFalse(w.views.isTabEnabled(0))
        self.assertEqual(w.views.currentIndex(), 1)
        self.assertEqual(w.views.tabText(1), "Independent views (unpaired)")
        self.assertFalse(w.details.isVisible())
        self.assertIsNone(w.pair_table)
        self.assertFalse(self.window.busy())

    def test_a_disabled_command_does_not_look_enabled(self):
        # The primary style (blue) must not hide the disabled state of Run verified modal comparison.
        button = self.workbench.run_button
        self.assertFalse(button.isEnabled())
        self.window.show_page(1)
        self.app.processEvents()
        image = button.grab().toImage()
        colour = image.pixelColor(image.width() // 2, 3)
        self.assertNotEqual(colour.name(), "#2563eb")
        self.assertLess(abs(colour.red() - colour.blue()), 40)  # grey, not the primary blue

    def test_without_a_verified_registration_no_mac_and_the_diagnostic_report(self):
        self.ready(1)  # another set: the check refuses it
        self.click(self.panel.run_button)
        self.assertEqual(self.panel.slot.state, rm.REFUSED)
        w = self.workbench
        self.assertFalse(w.run_button.isEnabled())
        self.assertIn(cm.NEED_REGISTRATION, w.why_unavailable.text())
        self.assertFalse(w.export_button.isEnabled())  # nothing to report yet
        self.click(self.window.diagnostic.run_button)
        self.assertTrue(w.export_button.isEnabled())
        self.assertIsNone(w.view)
        self.assertEqual(self.window.diagnostic.summary_values["MAC"].text(), dm.NOT_COMPUTED)
        self.assertTrue(w.export())
        self.assertTrue(self.window.wait_for_reads(120))
        self.app.processEvents()
        self.assertIn("Diagnostic report (no MAC, no mode pairs) written", w.export_status.text())
        self.assertEqual(sorted(p.suffix for p in self.reports.iterdir()), [".pdf", ".xlsx"])

    def test_frf_records_are_never_compared(self):
        self.inspect(ws.FE, self.package)
        self.inspect(ws.EXPERIMENTAL, self.frf)
        self.choose_set(0)
        self.assertFalse(self.workbench.run_button.isEnabled())
        self.assertIn(cm.PROVISIONAL_BLOCK, self.workbench.why_unavailable.text())


class ResultTests(_Window):
    def test_the_verified_comparison_shows_pairs_mac_diagnostics_and_drawings(self):
        self.compared()
        w = self.workbench
        view = w.view
        self.assertEqual(view.status, cm.PAIRS_FOUND)
        self.assertEqual(w.badge.text(), cm.PAIRS_FOUND)
        self.assertEqual(w.pair_table.rowCount(), 3)
        self.assertEqual([w.pair_table.item(r, 0).text() for r in range(3)], ["8", "10", "13"])
        self.assertEqual(w.pair_table.item(0, 6).text(), view.pair_rows[0].cells[6])
        self.assertTrue(w.details.isVisible())
        self.assertIn("mac", w.tables)
        self.assertEqual(w.tables["mac"].rowCount(), len(view.mac_fe_modes))
        self.assertTrue(w.views.isTabEnabled(0))
        self.assertEqual(w.views.currentIndex(), 0)
        self.assertTrue(w.pair_badge.text().startswith("COMPUTED PAIR FE 8 / Exp 2"))
        self.assertTrue(all(image.source is not None for image, _ in w.pair_views))
        w.pair_table.selectRow(2)
        self.assertTrue(self.window.wait_for_reads(120))
        self.app.processEvents()
        self.assertTrue(w.pair_badge.text().startswith("COMPUTED PAIR FE 13 / Exp 4"))
        self.assertEqual(sorted(w.images), [0, 2])  # each pair drawn once, then kept
        w.select_pair(0)
        self.assertFalse(w.drawing())  # a drawn pair is not drawn again
        self.assertIn("computed on the registered measured DOFs",
                      self.window.diagnostic.summary_values["MAC"].text())
        self.assertIn(cm.PAIRS_FOUND, self.window.status_text.text())
        self.window.show_page(window_module.MATERIALS_PAGE)
        materials = self.window.materials  # NEW-GUI.6-F1: the registration does not bind the FE model to M7
        self.assertEqual(materials.relevance_badge.text(), mm.NOT_AVAILABLE)
        self.assertTrue(materials.historical.isVisible())
        self.assertIn("not a result of the read FE model", materials.historical.text())

    def test_a_report_message_goes_with_its_result(self):
        self.compared()
        with reporting_restored():
            self.assertTrue(self.workbench.export())
            self.assertTrue(self.window.wait_for_reads(120))
        self.app.processEvents()
        self.assertTrue(self.workbench.export_status.text())
        self.choose_set(1)
        self.assertEqual(self.workbench.export_status.text(), "")
        self.assertFalse(self.workbench.export_status.isVisible())

    def test_the_verified_report_is_written_only_into_the_chosen_folder(self):
        self.compared()
        self.answer = ""  # a cancelled folder choice writes nothing
        self.assertFalse(self.workbench.export())
        self.assertEqual(list(self.reports.iterdir()), [])
        self.answer = str(self.reports)
        with reporting_restored():
            self.assertTrue(self.workbench.export())
            self.assertTrue(self.window.wait_for_reads(120))
        self.app.processEvents()
        self.assertIn("Verified comparison report written", self.workbench.export_status.text())
        self.assertEqual(sorted(p.suffix for p in self.reports.iterdir()), [".json", ".pdf", ".xlsx"])
        self.assertEqual(fingerprint_world(self), self.before)


def fingerprint_world(case):
    from test_new_gui5_registration import fingerprint

    return fingerprint(case.world.root)


class _SlowComparison:
    """A comparison that waits until released."""

    def __init__(self):
        self.started, self.release = threading.Event(), threading.Event()
        self.real = cm.compare

    def __call__(self, *args):
        self.started.set()
        self.release.wait(30)
        return self.real(*args)


class _SlowExport:
    """An export that waits until released (a deterministic delay)."""

    def __init__(self, real):
        self.started, self.release = threading.Event(), threading.Event()
        self.real = real

    def __call__(self, *args, **kwargs):
        self.started.set()
        self.release.wait(30)
        return self.real(*args, **kwargs)


class ExportProvenanceTests(_Window):
    def slow_export(self):
        from new_gui import report_export as rx

        slow = _SlowExport(rx.export_verified)
        patcher = mock.patch.object(rx, "export_verified", slow)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(slow.release.set)
        return slow

    def test_a_report_finished_after_the_inputs_changed_is_announced_as_earlier_data(self):
        import json
        from new_gui import comparison_panel as cp

        for change in (lambda: self.choose_set(1), lambda: self.window.choose_file(ws.FE, str(self.other_odb))):
            with self.subTest(change=change), reporting_restored():
                for item in self.reports.iterdir():
                    item.unlink()
                self.compared()
                read_fe = self.window.slots[ws.FE].identity
                slow = self.slow_export()
                self.assertTrue(self.workbench.export())
                self.assertTrue(slow.started.wait(30))
                change()
                self.app.processEvents()
                self.assertEqual(self.workbench.export_status.text(), cp.EARLIER_RUNNING)
                slow.release.set()
                self.assertTrue(self.window.wait_for_reads(120))
                self.app.processEvents()
                text = self.workbench.export_status.text()
                self.assertTrue(text.startswith(cp.EARLIER_DONE), text)
                written = sorted(self.reports.iterdir())
                self.assertEqual([p.suffix for p in written], [".json", ".pdf", ".xlsx"])  # kept, not removed
                record = json.loads(written[0].read_text(encoding="utf-8"))
                self.assertEqual(record["fe_source"]["sha256"], read_fe["sha256"])  # the earlier data's own source
                self.window.clear_file(ws.FE)
                self.window.clear_file(ws.EXPERIMENTAL)

    def test_a_file_changed_on_disk_after_the_comparison_is_not_exported(self):
        self.compared()
        mode_file = self.package.with_name("mode_0007.csv")  # PLATE-ONLY-R2-F1: a file of the package
        original = mode_file.read_bytes()
        mode_file.write_bytes(original + b"#")
        try:
            with reporting_restored():
                self.assertTrue(self.workbench.export())
                self.assertTrue(self.window.wait_for_reads(120))
        finally:
            mode_file.write_bytes(original)
        self.app.processEvents()
        self.assertIn("changed since it was read", self.workbench.export_status.text())
        self.assertEqual(list(self.reports.iterdir()), [])


class StaleTests(_Window):
    def start_slow(self):
        self.verified()
        slow = _SlowComparison()
        patcher = mock.patch.object(cm, "compare", slow)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(slow.release.set)
        self.assertTrue(self.workbench.run())
        self.assertTrue(slow.started.wait(30))
        self.assertEqual(self.workbench.badge.text(), cm.RUNNING_BADGE)
        self.assertFalse(self.workbench.run_button.isEnabled())
        self.assertTrue(self.window.busy())
        return slow

    def finish(self, slow):
        slow.release.set()
        self.assertTrue(self.window.wait_for_reads(120))
        self.app.processEvents()
        self.assertEqual(self.workbench.discarded, 1)
        self.assertIsNone(self.workbench.view)
        self.assertIsNone(self.workbench.pair_table)
        self.assertEqual(self.workbench.images, {})
        self.assertTrue(all(image.source is None for image, _ in self.workbench.pair_views))
        self.assertEqual(self.workbench.badge.text(), cm.NOT_RUN)

    def test_another_set_discards_the_running_comparison(self):
        slow = self.start_slow()
        self.choose_set(1)
        self.finish(slow)

    def test_a_replaced_fe_file_discards_the_running_comparison(self):
        slow = self.start_slow()
        self.window.choose_file(ws.FE, str(self.other_odb))
        self.finish(slow)

    def test_a_cleared_experimental_file_discards_the_running_comparison(self):
        slow = self.start_slow()
        self.window.clear_file(ws.EXPERIMENTAL)
        self.finish(slow)

    def test_inspect_again_discards_the_running_comparison(self):
        slow = self.start_slow()
        self.assertTrue(self.window.inspect_file(ws.EXPERIMENTAL))
        self.finish(slow)

    def test_a_new_check_discards_the_running_comparison(self):
        slow = self.start_slow()
        self.assertTrue(self.panel.run())
        self.finish(slow)

    def test_a_closed_window_discards_the_running_comparison(self):
        slow = self.start_slow()
        self.window.close()
        slow.release.set()
        self.assertTrue(self.window.wait_for_reads(120))
        self.app.processEvents()
        self.assertEqual(self.workbench.discarded, 1)
        self.assertIsNone(self.workbench.view)

    def test_the_diagnostic_waits_for_a_running_comparison(self):
        slow = self.start_slow()
        diagnostic = self.window.diagnostic
        self.assertTrue(diagnostic.run())
        threading.Event().wait(0.3)
        self.app.processEvents()
        self.assertEqual(diagnostic.slot.state, dm.RUNNING)  # one heavy operation at a time
        slow.release.set()
        self.assertTrue(self.window.wait_for_reads(120))
        self.app.processEvents()
        self.assertEqual(diagnostic.slot.state, dm.DONE)
        self.assertEqual(self.workbench.slot.state, cm.DONE)


class RemovedResultTests(_Window):
    def test_a_shown_result_and_its_drawings_go_with_any_change(self):
        for change in (lambda: self.choose_set(1), lambda: self.window.clear_file(ws.FE),
                       lambda: self.window.choose_file(ws.FE, str(self.other_odb)),
                       lambda: self.window.inspect_file(ws.EXPERIMENTAL)):
            with self.subTest(change=change):
                self.compared()
                self.assertTrue(self.workbench.images)
                change()
                self.window.wait_for_reads(120)
                self.app.processEvents()
                self.assertIsNone(self.workbench.view)
                self.assertEqual(self.workbench.images, {})
                self.assertIsNone(self.workbench.pair_table)
                self.assertFalse(self.workbench.views.isTabEnabled(0))
                self.assertNotIn(cm.PAIRS_FOUND, self.window.status_text.text())
                summary = self.window.diagnostic.summary_values  # the summary never keeps the removed result
                self.assertNotIn("computed on the registered", summary["MAC"].text())
                self.assertNotIn(cm.PAIRS_FOUND, summary["Mode pairs"].text())
                self.window.clear_file(ws.FE)
                self.window.clear_file(ws.EXPERIMENTAL)


class MaterialsPageTests(_Window):
    def test_the_records_are_read_on_first_show_and_relate_only_to_a_verified_fixture(self):
        materials = self.window.materials
        self.assertIsNone(materials.evidence)  # nothing is read at start-up
        self.window.show_page(window_module.MATERIALS_PAGE)
        self.assertIsNotNone(materials.evidence)
        self.assertEqual(set(materials.tables), set(mm.CLASSES))
        self.assertEqual(materials.relevance_badge.text(), mm.NOT_AVAILABLE)
        self.ready(1)
        self.click(self.panel.run_button)  # refused: nothing is related to the data
        self.assertEqual(materials.relevance_badge.text(), mm.NOT_AVAILABLE)
        self.assertEqual(self.window.stack.widget(window_module.MATERIALS_PAGE).widget().findChildren(QPushButton),
                         [])  # the page has no command


class KnownSourceDialogTests(_Window):
    def test_without_the_local_folder_nothing_is_offered_and_own_files_still_work(self):
        self.window._known_root = self.own / "absent"
        dialog = self.window.open_known_sources()
        self.app.processEvents()
        self.assertEqual(dialog.list.count(), 3)
        self.assertFalse(dialog.use_button.isEnabled())
        self.assertIn("None of the known sources is on this computer", dialog.message.text())
        dialog.reject()
        self.inspect(ws.EXPERIMENTAL, self.unv)  # the ordinary choice of one's own file
        self.assertIsNotNone(self.window._read_preview(ws.EXPERIMENTAL))

    def test_a_file_with_another_content_is_refused(self):
        root = self.own / "known"
        source = ks.KNOWN_SOURCES[1]
        path = root / Path(source.relative_path.replace("\\", "/"))
        path.parent.mkdir(parents=True)
        path.write_bytes(b"\0" * source.size_bytes)
        self.window._known_root = root
        dialog = self.window.open_known_sources()
        dialog.list.setCurrentRow(1)
        self.app.processEvents()
        self.assertTrue(dialog.use_button.isEnabled())
        self.assertFalse(dialog.use_selected())
        self.assertIn("is not the declared", dialog.message.text())
        self.assertFalse(self.window.workspace.choice(ws.EXPERIMENTAL).chosen)
        dialog.reject()

    @unittest.skipUnless(ks.DEFAULT_ROOT.is_dir(), "the new experimental folder is not on this computer")
    def test_a_verified_source_only_sets_the_path(self):
        dialog = self.window.open_known_sources()
        dialog.list.setCurrentRow(0)
        self.assertTrue(dialog.use_selected())
        self.app.processEvents()
        choice = self.window.workspace.choice(ws.EXPERIMENTAL)
        self.assertTrue(choice.chosen)
        self.assertEqual(choice.path.name, Path(ks.KNOWN_SOURCES[0].relative_path).name)
        self.assertIsNone(self.window._read_preview(ws.EXPERIMENTAL))  # nothing read until Inspect file


class LayoutTests(_Window):
    def test_the_result_adds_no_width_to_the_page(self):
        # The page-level scroll bar itself is checked on Windows: the offscreen font is not Windows'.
        from PySide6.QtWidgets import QBoxLayout

        self.window.resize(900, 680)
        self.app.processEvents()
        self.assertEqual(self.workbench.unpaired_row.direction(), QBoxLayout.Direction.TopToBottom)
        self.verified()
        before = max(self.workbench.minimumSizeHint().width(), self.window.registration.minimumSizeHint().width())
        self.click(self.workbench.run_button)
        self.assertLessEqual(self.workbench.minimumSizeHint().width(), before)
        self.window.resize(1500, 900)
        self.app.processEvents()
        self.assertEqual(self.workbench.unpaired_row.direction(), QBoxLayout.Direction.LeftToRight)


if __name__ == "__main__":
    unittest.main()
