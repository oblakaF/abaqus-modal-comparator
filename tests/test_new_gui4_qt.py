"""NEW-GUI.4: the Analysis page's frequency diagnostic in the PySide6 window, driven headless (Qt ``offscreen``).

Run frequency diagnostic is disabled, with the reason shown, until both files are read and an experimental modal
set is chosen; nothing runs by itself. A click runs the existing service in a worker thread and shows
FREQUENCY_ONLY_DIAGNOSTIC: "Nearest by frequency — NOT a mode pair" with MAC NOT_COMPUTED, the elastic FE, rigid-body
FE and experimental frequencies in separate read-only tables, PROVISIONAL for FRF peak records and the importer's
warnings. Another set, a replaced or cleared file, Inspect again or a closed window discards a running diagnostic.
In a narrow window every column stays reachable without a page-level horizontal scroll bar. The Status page and the
NEW-GUI.3 shape panels are kept. No user file changes.

PySide6 comes from ``requirements-new-gui.txt``. Without it these tests are skipped with that reason, except when
``NEW_GUI_REQUIRE_QT=1`` (set in CI), where a missing PySide6 is an error.
"""

from __future__ import annotations

import hashlib
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
    from PySide6.QtWidgets import QAbstractItemView, QApplication, QPushButton
except ImportError as error:  # pragma: no cover - depends on the environment
    if os.environ.get("NEW_GUI_REQUIRE_QT") == "1":
        raise
    raise unittest.SkipTest(f"PySide6 is not installed ({error}); install requirements-new-gui.txt to run the "
                            "new interface tests (CI sets NEW_GUI_REQUIRE_QT=1 and runs them)")

from new_gui import diagnostic_model as dm  # noqa: E402
from new_gui import shape_model as sm  # noqa: E402
from new_gui import window as window_module  # noqa: E402
from new_gui import workspace_state as ws  # noqa: E402
from services import local_input_registry as registry  # noqa: E402
import frf_unv_support as F  # noqa: E402
import synthetic_plate_support as S  # noqa: E402
from test_new_gui3_shapes import geometry_4, mode_55_4  # noqa: E402
from test_new_gui4_diagnostic import ELASTIC_BY_SHAPE, RIGID_BY_SHAPE, write_fe_package  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or window_module.create_application([])


def fingerprint(folder: Path) -> dict:
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.rglob("*")) if p.is_file()}


class _Window(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        cls._tmp = tempfile.TemporaryDirectory()
        inputs = Path(cls._tmp.name) / "inputs"
        cls.inputs = inputs
        cls.manifest = write_fe_package(inputs / "package")
        cls.other_manifest = write_fe_package(inputs / "package_b", [(7, 99.0, "saddle"), (8, 150.0, "bending")])
        cls.two_sets = S.write_experiment(inputs / "two_sets.unv", S.E0, S.G0, sets=(("bravo", 4), ("processing", 6)))
        cls.frf = F.write_frf_only(inputs / "frf_only.uff")
        cls.ambiguous = inputs / "ambiguous.unv"
        cls.ambiguous.write_text("synthetic records", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        self._own = tempfile.TemporaryDirectory()
        self.addCleanup(self._own.cleanup)
        cache = Path(self._own.name) / "cache"
        cache.mkdir()
        for patcher in (mock.patch.dict(os.environ, {"LOCALAPPDATA": str(cache)}),
                        mock.patch.object(registry, "default_store",
                                          return_value=Path(self._own.name) / "profile" / registry.STORE_NAME),
                        mock.patch("subprocess.Popen", side_effect=AssertionError("no process for a diagnostic"))):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.inputs_before = fingerprint(self.inputs)
        self.window = window_module.MainWindow(ask_path=lambda kind, start: "")
        self.window.resize(1100, 800)
        self.window.show()
        self.window.show_page(1)
        self.app.processEvents()
        self.panel = self.window.diagnostic
        self.addCleanup(self._close)

    def _close(self):
        self.window.close()
        self.window.wait_for_reads(60)
        self.window.deleteLater()
        self.app.processEvents()
        self.assertEqual(fingerprint(self.inputs), self.inputs_before)  # no user file changed

    def inspect(self, kind, path):
        self.assertEqual(self.window.choose_file(kind, str(path)), "")
        self.window.cards[kind].inspect_button.click()
        self.assertTrue(self.window.wait_for_reads(120))

    def choose_set(self, index):
        self.panel.set_combo.setCurrentIndex(index + 1)
        self.app.processEvents()

    def run_diagnostic(self):
        self.panel.run_button.click()
        self.assertTrue(self.window.wait_for_reads(120))
        self.app.processEvents()

    def ready(self, experimental=None, set_index=0):
        self.inspect(ws.FE, self.manifest)
        self.inspect(ws.EXPERIMENTAL, experimental or self.two_sets)
        self.choose_set(set_index)


class AvailabilityTests(_Window):
    def test_the_button_is_enabled_only_after_both_reads_and_a_chosen_set_and_nothing_runs_by_itself(self):
        panel, w = self.panel, self.window
        with mock.patch.object(dm, "diagnose", wraps=dm.diagnose) as spy:
            self.assertFalse(panel.run_button.isEnabled())
            self.assertEqual(panel.why_unavailable.text().splitlines(), [dm.NEED_FE, dm.NEED_EXPERIMENTAL])
            self.assertTrue(panel.why_unavailable.isVisible())
            self.inspect(ws.FE, self.manifest)
            self.assertFalse(panel.run_button.isEnabled())
            self.assertEqual(panel.why_unavailable.text(), dm.NEED_EXPERIMENTAL)
            self.inspect(ws.EXPERIMENTAL, self.two_sets)
            self.assertFalse(panel.run_button.isEnabled())
            self.assertEqual(panel.why_unavailable.text(), dm.NEED_SET)
            self.assertEqual(panel.set_combo.currentText(), dm.CHOOSE_SET)  # no set chosen by itself
            self.assertEqual(panel.set_combo.count(), 3)
            self.choose_set(1)
            self.assertTrue(panel.run_button.isEnabled())
            self.assertFalse(panel.why_unavailable.isVisible())
            self.assertFalse(w.busy())
        spy.assert_not_called()  # nothing ran by itself
        self.assertEqual(panel.slot.state, dm.IDLE)
        self.assertEqual(w.analysis_badge.text(), "Analysis not run")
        self.assertIn("Analysis not run", w.status_text.text())
        self.assertFalse(panel.result_card.isVisible())
        self.assertEqual(panel.summary_values["MAC"].text(), "not computed")
        self.assertEqual(panel.summary_values["Mode pairs"].text(), "none")

    def test_an_unread_or_failed_file_keeps_the_button_disabled(self):
        bad = Path(self._own.name) / "plate.odb"
        bad.write_bytes(b"not read for a preview")
        self.inspect(ws.FE, bad)  # an .odb is not read: the read fails with its reason
        self.inspect(ws.EXPERIMENTAL, self.two_sets)
        self.choose_set(0)
        self.assertFalse(self.panel.run_button.isEnabled())
        self.assertEqual(self.panel.why_unavailable.text(), dm.NEED_FE)
        self.assertFalse(self.panel.run())


class ResultTests(_Window):
    def test_a_click_shows_the_frequency_only_diagnostic(self):
        self.ready(set_index=1)
        panel, w = self.panel, self.window
        self.run_diagnostic()
        self.assertEqual(panel.slot.state, dm.DONE)
        self.assertEqual(w.analysis_badge.text(), "FREQUENCY_ONLY_DIAGNOSTIC")
        self.assertIn("FREQUENCY_ONLY_DIAGNOSTIC · Production Auto-ID NOT_AUTHORISED", w.status_text.text())
        self.assertTrue(panel.result_card.isVisible())
        preview = w.slots[ws.EXPERIMENTAL].preview
        self.assertEqual(panel.result_set.text(), f"Experimental modal set: Modal set 2 of 2: {preview.sets[1].title}")
        self.assertEqual(panel.summary_values["MAC"].text(), "NOT_COMPUTED")
        self.assertEqual(panel.summary_values["Mode pairs"].text(), "NONE (physical modal correspondence not verified)")
        titles = [label.text() for label in panel.tables_box.findChildren(type(panel.statement))]
        self.assertIn("Nearest by frequency — NOT a mode pair", titles)
        nearest = panel.tables["nearest"]
        headers = [nearest.horizontalHeaderItem(c).text() for c in range(nearest.columnCount())]
        self.assertEqual(headers, list(dm.NEAREST_HEADERS))
        mac = headers.index("MAC")
        self.assertEqual({nearest.item(r, mac).text() for r in range(nearest.rowCount())}, {"NOT_COMPUTED"})
        self.assertEqual(nearest.rowCount(), 6)  # every record of the chosen set
        self.assertEqual((nearest.item(0, 0).text(), nearest.item(0, 1).text()), ("1", "1"))  # record 1 kept
        self.assertEqual([panel.tables["rigid"].item(r, 0).text() for r in range(panel.tables["rigid"].rowCount())],
                         [str(n) for n in RIGID_BY_SHAPE])
        self.assertEqual([panel.tables["fe"].item(r, 0).text() for r in range(panel.tables["fe"].rowCount())],
                         [str(n) for n in ELASTIC_BY_SHAPE])
        self.assertEqual(panel.tables["experimental"].rowCount(), 6)
        self.assertFalse(panel.provisional.isVisible())
        for table in panel.tables.values():  # read-only, nothing selectable
            self.assertEqual(table.selectionMode(), QAbstractItemView.SelectionMode.NoSelection)
            self.assertEqual(table.editTriggers(), QAbstractItemView.EditTrigger.NoEditTriggers)
        self.assertEqual(w.stack.widget(2).widget().findChildren(QPushButton), [])  # the Status page is unchanged
        self.assertEqual({k: b.text() for k, b in w.status_badges.items()},
                         {"Production Auto-ID": "NOT_AUTHORISED", "M8 gate": "NOT_MET",
                          "D-077 formal output": "NO_GLOBAL_PARAMETER_VALUE"})

    def test_another_set_removes_the_result_until_the_next_click(self):
        self.ready(set_index=1)
        self.run_diagnostic()
        self.choose_set(0)
        self.assertEqual(self.panel.slot.state, dm.IDLE)
        self.assertFalse(self.panel.result_card.isVisible())
        self.assertEqual(self.window.analysis_badge.text(), "Analysis not run")
        self.assertFalse(self.window.busy())  # nothing reruns by itself
        self.run_diagnostic()
        self.assertEqual(self.panel.tables["nearest"].rowCount(), 4)  # the first set's records only

    def test_frf_peak_records_show_provisional(self):
        self.ready(experimental=self.frf)
        self.run_diagnostic()
        self.assertTrue(self.panel.provisional.isVisible())
        self.assertEqual(self.panel.provisional.text(), "PROVISIONAL — NOT A VALIDATED FITTED MODE")
        nearest = self.panel.tables["nearest"]
        classification = dm.NEAREST_HEADERS.index("Classification (importer)")
        self.assertEqual({nearest.item(r, classification).text() for r in range(nearest.rowCount())},
                         {"PROVISIONAL — NOT A VALIDATED FITTED MODE"})

    def test_ambiguous_records_keep_the_importer_warnings(self):
        import universal_reader

        self.inspect(ws.EXPERIMENTAL, self.frf)  # installs the importer chain first
        datasets = [geometry_4(), mode_55_4(1, 10.0), mode_55_4(2, 20.0, ambiguous=True)]
        with mock.patch.object(universal_reader, "_read_universal_datasets", return_value=datasets):
            self.inspect(ws.EXPERIMENTAL, self.ambiguous)
        self.inspect(ws.FE, self.manifest)
        self.choose_set(0)
        self.run_diagnostic()
        notes = " ".join(label.text() for label in self.panel.tables_box.findChildren(type(self.panel.statement)))
        self.assertIn("Importer warnings for this modal set:", notes)
        self.assertIn("dataset 55 record 2", notes.lower())
        nearest = self.panel.tables["nearest"]
        self.assertTrue(nearest.item(1, 10).text().startswith("AMBIGUOUS (importer) — dataset 55 record 2"))

    def test_the_shape_panels_still_draw(self):
        self.ready()
        self.run_diagnostic()
        shape = self.window.shape_panels[ws.FE]
        shape.item_combo.setCurrentIndex(4)  # FE mode 4
        self.app.processEvents()
        shape.show_button.click()
        self.assertTrue(self.window.wait_for_reads(120))
        self.app.processEvents()
        self.assertEqual(shape.slot.state, sm.SHOWN)
        self.assertEqual(self.panel.slot.state, dm.DONE)  # a shape view does not touch the diagnostic


class _Slow:
    """A diagnostic that waits until released."""

    def __init__(self):
        self.started, self.release = threading.Event(), threading.Event()
        self.real = dm.diagnose

    def __call__(self, *args):
        self.started.set()
        self.release.wait(30)
        return self.real(*args)


class StaleTests(_Window):
    def start_slow(self):
        self.ready()
        slow = _Slow()
        patcher = mock.patch.object(dm, "diagnose", slow)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(slow.release.set)
        self.assertTrue(self.panel.run())
        self.assertTrue(slow.started.wait(30))
        self.assertEqual(self.panel.status.text(), dm.RUNNING_TEXT)
        self.assertFalse(self.panel.run_button.isEnabled())
        self.assertTrue(self.window.busy())
        return slow

    def finish(self, slow):
        slow.release.set()
        self.assertTrue(self.window.wait_for_reads(120))
        self.app.processEvents()
        self.assertEqual(self.panel.discarded, 1)
        self.assertIsNone(self.panel.view)
        self.assertFalse(self.panel.result_card.isVisible())
        self.assertEqual(self.window.analysis_badge.text(), "Analysis not run")

    def test_another_set_discards_the_running_diagnostic(self):
        slow = self.start_slow()
        self.choose_set(1)
        self.finish(slow)
        self.assertTrue(self.panel.run_button.isEnabled())  # set 2 is chosen; it runs only on a click

    def test_a_replaced_fe_file_discards_the_running_diagnostic(self):
        slow = self.start_slow()
        self.window.choose_file(ws.FE, str(self.other_manifest))
        self.finish(slow)
        self.assertEqual(self.panel.why_unavailable.text(), dm.NEED_FE)

    def test_a_cleared_experimental_file_discards_the_running_diagnostic(self):
        slow = self.start_slow()
        self.window.clear_file(ws.EXPERIMENTAL)
        self.finish(slow)
        self.assertEqual(self.panel.set_combo.count(), 1)

    def test_inspect_again_discards_the_running_diagnostic_and_the_set(self):
        slow = self.start_slow()
        self.assertTrue(self.window.inspect_file(ws.EXPERIMENTAL))
        self.finish(slow)
        self.assertEqual(self.panel.set_combo.currentText(), dm.CHOOSE_SET)  # a new preview: no set chosen
        self.assertFalse(self.panel.run_button.isEnabled())

    def test_a_closed_window_discards_the_running_diagnostic(self):
        slow = self.start_slow()
        self.window.close()
        slow.release.set()
        self.assertTrue(self.window.wait_for_reads(120))
        self.app.processEvents()
        self.assertEqual(self.panel.discarded, 1)
        self.assertIsNone(self.panel.view)


class LayoutTests(_Window):
    def test_a_narrow_window_keeps_every_column_reachable_and_the_result_adds_no_width(self):
        # The page-level scroll bar itself is checked on Windows: the offscreen font is not Windows'.
        self.ready(set_index=1)
        before = self.panel.minimumSizeHint().width()
        self.run_diagnostic()
        self.assertLessEqual(self.panel.minimumSizeHint().width(), before)  # tables and long texts add no width
        self.assertLessEqual(self.panel.result_card.minimumSizeHint().width(), before)
        w = self.window
        for width in (1366, 900, 600):
            w.resize(width, 680)
            for _ in range(3):
                self.app.processEvents()
            with self.subTest(width=width):
                for key, table in self.panel.tables.items():
                    header, viewport = table.horizontalHeader(), table.viewport().width()
                    self.assertLessEqual(table.width(), self.panel.result_card.width())  # within its card
                    hidden = max(0, header.length() - viewport)
                    self.assertGreaterEqual(table.horizontalScrollBar().maximum(), hidden, key)  # reachable
                    self.assertEqual(table.horizontalScrollBar().isVisible(), hidden > 0, key)
                    rows = table.verticalHeader().length() + header.height()
                    self.assertGreaterEqual(table.height(), rows, key)  # as tall as its rows
        nearest = self.panel.tables["nearest"]
        self.assertGreater(nearest.horizontalScrollBar().maximum(), 0)  # 600 px: the table, not the page, scrolls

    def test_a_long_set_name_does_not_widen_the_page(self):
        self.ready()
        width = self.panel.minimumSizeHint().width()
        self.panel.set_combo.addItem("Modal set 9 of 9: " + "a very long modal set name " * 12, 0)
        self.app.processEvents()
        self.assertEqual(self.panel.minimumSizeHint().width(), width)


if __name__ == "__main__":
    unittest.main()
