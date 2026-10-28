"""NEW-GUI.2: Inspect file in the PySide6 window, driven headless (Qt ``offscreen`` platform).

The start stays empty: no file, no read, no cache. A chosen file is read only on Inspect file, in a background
thread, and the window shows the services' modes, frequencies, modal sets (one table each, nothing selectable) and
warnings; FRF peak records are PROVISIONAL and a plain .odb is not read. Replacing or clearing a file, or closing the
window, during a read discards that read's outcome. The cache is created (in an isolated folder) only by a read, and
no user file is changed.

PySide6 comes from ``requirements-new-gui.txt``. Without it these tests are skipped with that reason, except when
``NEW_GUI_REQUIRE_QT=1`` (set in CI), where a missing PySide6 is an error.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
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
    from PySide6.QtWidgets import QAbstractItemView, QApplication, QLabel, QPushButton, QTableWidget
except ImportError as error:  # pragma: no cover - depends on the environment
    if os.environ.get("NEW_GUI_REQUIRE_QT") == "1":
        raise
    raise unittest.SkipTest(f"PySide6 is not installed ({error}); install requirements-new-gui.txt to run the "
                            "new interface tests (CI sets NEW_GUI_REQUIRE_QT=1 and runs them)")

from new_gui import preview_model as pm  # noqa: E402
from new_gui import preview_panel  # noqa: E402
from new_gui import window as window_module  # noqa: E402
from new_gui import workspace_state as ws  # noqa: E402
from services import local_experimental_preview as xp  # noqa: E402
from services import local_fe_preview as fp  # noqa: E402
from services import local_input_registry as registry  # noqa: E402
import frf_unv_support as F  # noqa: E402
import synthetic_plate_support as S  # noqa: E402
from test_local_fe_preview import RIGID, described, write_package  # noqa: E402

CYRILLIC = re.compile("[Ѐ-ӿ]")


def _app() -> QApplication:
    return QApplication.instance() or window_module.create_application([])


def fingerprint(folder: Path) -> dict:
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.rglob("*")) if p.is_file()}


def cells(table: QTableWidget, column: int) -> list[str]:
    return [table.item(row, column).text() for row in range(table.rowCount())]


class _Window(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        cls._tmp = tempfile.TemporaryDirectory()
        cls.shared = Path(cls._tmp.name)
        cls.manifest = write_package(cls.shared / "inputs" / "package", [(n, f, None) for n, f in enumerate(RIGID, 1)]
                                     + [(7, 101.25, described(101.25)), (8, 133.5, described(133.5))])
        cls.other_manifest = write_package(cls.shared / "inputs" / "package_b", [(7, 99.0, described(99.0))])
        cls.two_sets = S.write_experiment(cls.shared / "inputs" / "two_sets.unv", S.E0, S.G0,
                                          sets=(("bravo", 4), ("processing", 6)))
        cls.frf = F.write_frf_only(cls.shared / "inputs" / "frf_only.uff")
        cls.odb = cls.shared / "inputs" / "plate.odb"
        cls.odb.write_bytes(b"synthetic odb; never opened")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        self._own = tempfile.TemporaryDirectory()
        self.addCleanup(self._own.cleanup)
        self.cache = Path(self._own.name) / "cache"
        self.cache.mkdir()
        for patcher in (mock.patch.dict(os.environ, {"LOCALAPPDATA": str(self.cache)}),
                        mock.patch.object(registry, "default_store",
                                          return_value=Path(self._own.name) / "profile" / registry.STORE_NAME),
                        mock.patch("subprocess.Popen", side_effect=AssertionError("no process for a preview"))):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.inputs_before = fingerprint(self.shared / "inputs")
        self.window = window_module.MainWindow(ask_path=lambda kind, start: "")
        self.window.show()
        self.app.processEvents()
        self.addCleanup(self._close)

    def _close(self):
        self.window.close()
        self.window.wait_for_reads(60)
        self.window.deleteLater()
        self.app.processEvents()
        self.assertEqual(fingerprint(self.shared / "inputs"), self.inputs_before)  # no user file changed

    def cache_files(self) -> list[str]:
        return sorted(p.name for p in self.cache.rglob("*") if p.is_file())

    def inspect(self, kind, path):
        self.assertEqual(self.window.choose_file(kind, str(path)), "")
        self.window.cards[kind].inspect_button.click()
        self.assertTrue(self.window.wait_for_reads(120))
        return self.window.panels[kind]


class StartTests(_Window):
    def test_an_empty_start_reads_nothing_and_creates_no_cache(self):
        w = self.window
        for kind in ws.KINDS:
            self.assertFalse(w.cards[kind].inspect_button.isEnabled())
            self.assertFalse(w.panels[kind].isVisible())
            self.assertEqual(w.slots[kind].state, pm.IDLE)
        self.assertFalse(w.inspect_file(ws.FE))  # nothing chosen: nothing is read
        self.assertFalse(w.reading())
        self.assertEqual(self.cache_files(), [])
        self.assertTrue(w.empty_state.isVisible())

    def test_choosing_a_file_does_not_read_it(self):
        w = self.window
        w.choose_file(ws.FE, str(self.manifest))
        self.app.processEvents()
        card, panel = w.cards[ws.FE], w.panels[ws.FE]
        self.assertTrue(card.inspect_button.isEnabled())
        self.assertEqual(card.inspect_button.text(), pm.INSPECT)
        self.assertEqual(card.badge.text(), ws.CHOSEN_NOT_CHECKED)
        self.assertTrue(panel.isVisible())
        self.assertEqual(panel.message.text(), pm.NOT_INSPECTED)
        self.assertEqual(panel.tables, [])
        self.assertFalse(w.reading())
        self.assertEqual(self.cache_files(), [])

    def test_the_interface_stays_english(self):
        self.inspect(ws.EXPERIMENTAL, self.frf)
        texts = [label.text() for label in self.window.findChildren(QLabel)]
        texts += [button.text() for button in self.window.findChildren(QPushButton)]
        for table in self.window.findChildren(QTableWidget):
            texts += [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
            texts += [table.item(r, c).text() for r in range(table.rowCount()) for c in range(table.columnCount())]
        self.assertEqual([t for t in texts if CYRILLIC.search(t)], [])


class FeTests(_Window):
    def test_inspect_shows_the_loaded_modes_and_frequencies(self):
        panel = self.inspect(ws.FE, self.manifest)
        service = fp.preview_fe_package(self.manifest)
        table, = panel.tables
        self.assertEqual(cells(table, 0), [str(m.number) for m in service.modes])
        self.assertEqual(cells(table, 1), [fp.frequency_text(m) for m in service.modes])
        self.assertEqual(cells(table, 2), [fp.source_text(m) or "not recorded" for m in service.modes])
        self.assertEqual(panel.summary.text(), fp.summary(service))
        self.assertEqual(self.window.cards[ws.FE].badge.text(), pm.STATE_TEXT[pm.READ])
        self.assertEqual(self.window.cards[ws.FE].inspect_button.text(), "Inspect again")
        self.assertIn("not declared ready for an analysis", panel.note.text())
        self.assertEqual([name for name in self.cache_files() if name.startswith("odb_")].__len__(), 1)

    def test_a_plain_odb_gets_the_manifest_message(self):
        panel = self.inspect(ws.FE, self.odb)
        self.assertEqual(panel.message.text(), pm.ODB_NOT_READ)
        self.assertTrue(panel.message.isVisible())
        self.assertEqual(panel.tables, [])
        self.assertEqual(self.window.cards[ws.FE].badge.text(), pm.STATE_TEXT[pm.FAILED])
        self.assertEqual(self.cache_files(), [])


class ExperimentalTests(_Window):
    def test_several_sets_are_separate_tables_and_nothing_is_selected(self):
        panel = self.inspect(ws.EXPERIMENTAL, self.two_sets)
        service = xp.preview_experimental_file(self.two_sets)
        self.assertEqual(len(panel.tables), 2)
        self.assertEqual([t.text() for t in panel.section_titles],
                         ["Modal set 1 of 2: bravo (bravo) — 4 records",
                          "Modal set 2 of 2: processing (processing) — 6 records"])
        for table, item in zip(panel.tables, service.sets):
            self.assertEqual(cells(table, 0), [str(r.number) for r in item.records])
            self.assertEqual(cells(table, 1), [f"{r.frequency_hz:.6g}" for r in item.records])
            self.assertEqual(cells(table, 2), [r.label for r in item.records])
            self.assertEqual(table.selectionMode(), QAbstractItemView.SelectionMode.NoSelection)
            self.assertEqual(table.editTriggers(), QAbstractItemView.EditTrigger.NoEditTriggers)
            self.assertEqual(table.selectedItems(), [])
        self.assertEqual(cells(panel.tables[0], 0)[0], "1")  # experimental mode 1 is shown
        self.assertEqual(panel.summary.text(), xp.summary(service))

    def test_frf_peak_records_are_provisional(self):
        panel = self.inspect(ws.EXPERIMENTAL, self.frf)
        table, = panel.tables
        self.assertTrue(table.rowCount())
        self.assertEqual(set(cells(table, 2)), {"PROVISIONAL — NOT A VALIDATED FITTED MODE"})
        self.assertIn(pm.PROVISIONAL_NOTE, panel.section_notes[0].text())


class _Slow:
    """A read that waits until released, to act while it runs."""

    def __init__(self):
        self.started, self.release = threading.Event(), threading.Event()
        self.real = pm.read_preview

    def __call__(self, kind, path, cancel_event=None):
        self.started.set()
        self.release.wait(30)
        return self.real(kind, path, cancel_event)


class StaleReadTests(_Window):
    def start_slow(self, kind, path):
        slow = _Slow()
        patcher = mock.patch.object(pm, "read_preview", slow)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(slow.release.set)
        self.window.choose_file(kind, str(path))
        self.assertTrue(self.window.inspect_file(kind))
        self.assertTrue(slow.started.wait(30))
        return slow

    def test_the_window_stays_usable_while_reading(self):
        slow = self.start_slow(ws.FE, self.manifest)
        w = self.window
        self.assertEqual(w.cards[ws.FE].badge.text(), pm.STATE_TEXT[pm.READING])
        self.assertFalse(w.cards[ws.FE].inspect_button.isEnabled())
        self.assertFalse(w.inspect_file(ws.FE))  # one read per side at a time
        w.choose_file(ws.EXPERIMENTAL, str(self.frf))  # the GUI thread is free
        w.label_edit.setText("plate A")
        self.app.processEvents()
        self.assertEqual(w.workspace.experimental.path.name, self.frf.name)
        slow.release.set()
        self.assertTrue(w.wait_for_reads(120))
        self.assertEqual(w.slots[ws.FE].state, pm.READ)

    def test_a_replaced_file_never_shows_the_old_read(self):
        slow = self.start_slow(ws.FE, self.manifest)
        w = self.window
        w.choose_file(ws.FE, str(self.other_manifest))
        self.assertEqual(w.slots[ws.FE].state, pm.IDLE)
        slow.release.set()
        self.assertTrue(w.wait_for_reads(120))
        self.assertEqual(w.discarded, 1)
        self.assertEqual((w.slots[ws.FE].state, w.slots[ws.FE].preview), (pm.IDLE, None))
        self.assertEqual(w.panels[ws.FE].tables, [])
        self.assertEqual(w.panels[ws.FE].message.text(), pm.NOT_INSPECTED)
        w.cards[ws.FE].inspect_button.click()
        self.assertTrue(w.wait_for_reads(120))
        self.assertEqual(cells(w.panels[ws.FE].tables[0], 0), ["7"])  # the new file's modes only

    def test_a_cleared_file_never_shows_the_old_read(self):
        slow = self.start_slow(ws.EXPERIMENTAL, self.two_sets)
        w = self.window
        w.clear_file(ws.EXPERIMENTAL)
        slow.release.set()
        self.assertTrue(w.wait_for_reads(120))
        self.assertEqual(w.discarded, 1)
        self.assertFalse(w.panels[ws.EXPERIMENTAL].isVisible())
        self.assertEqual(w.panels[ws.EXPERIMENTAL].tables, [])

    def test_a_new_file_shows_nothing_of_the_previous_one(self):
        w = self.window
        self.inspect(ws.EXPERIMENTAL, self.two_sets)
        self.assertEqual(len(w.panels[ws.EXPERIMENTAL].tables), 2)
        w.choose_file(ws.EXPERIMENTAL, str(self.frf))
        self.assertEqual(w.panels[ws.EXPERIMENTAL].tables, [])
        self.assertEqual(w.cards[ws.EXPERIMENTAL].badge.text(), ws.CHOSEN_NOT_CHECKED)
        self.assertEqual(w.panels[ws.EXPERIMENTAL].summary.text(), "")

    def test_closing_the_window_while_reading_discards_the_read(self):
        slow = self.start_slow(ws.FE, self.manifest)
        w = self.window
        w.close()
        self.assertTrue(w.slots[ws.FE].cancel_event is None)
        slow.release.set()
        self.assertTrue(w.wait_for_reads(120))
        self.assertEqual(w.discarded, 1)
        self.assertEqual(w.slots[ws.FE].preview, None)


class LayoutTests(_Window):
    def test_a_long_file_name_does_not_widen_the_card(self):
        long_name = Path(self._own.name) / ("SP99_" + "_".join(["Honeycomb", "TPU", "PlainFiber"] * 6) + ".unv")
        long_name.write_bytes(self.frf.read_bytes())
        card = self.window.cards[ws.EXPERIMENTAL]
        self.window.choose_file(ws.EXPERIMENTAL, str(self.frf))
        self.app.processEvents()
        short_width = card.minimumSizeHint().width()
        self.window.choose_file(ws.EXPERIMENTAL, str(long_name))
        self.app.processEvents()
        self.assertEqual(card.file_name.text(), long_name.name)  # the whole name, also in the tooltip
        self.assertEqual(card.file_name.toolTip(), long_name.name)
        self.assertEqual(card.minimumSizeHint().width(), short_width)

    def test_the_read_content_does_not_widen_the_page(self):
        w = self.window
        w.resize(900, 680)
        w.choose_file(ws.FE, str(self.manifest))
        w.choose_file(ws.EXPERIMENTAL, str(self.two_sets))
        self.app.processEvents()
        w.inspect_file(ws.FE)
        w.inspect_file(ws.EXPERIMENTAL)
        self.assertTrue(w.wait_for_reads(120))
        self.app.processEvents()
        for kind in ws.KINDS:  # long paths and tables add no width to the page (the offscreen font is not Windows')
            self.assertTrue(w.panels[kind].tables)
            self.assertLessEqual(w.panels[kind].minimumSizeHint().width(), w.cards[kind].minimumSizeHint().width())
        for panel in w.panels.values():
            self.assertTrue(all(field.isReadOnly() for field in panel.path_fields))
        for table in w.findChildren(QTableWidget):
            self.assertFalse(table.verticalScrollBar().isVisible())  # every row is shown; the page scrolls
            self.assertEqual(table.height(), table.maximumHeight())

    def assert_tables_readable(self):
        for table in self.window.findChildren(QTableWidget):
            if not table.isVisible():
                continue
            header = table.horizontalHeader()
            bar = table.horizontalScrollBar()
            with self.subTest(columns=table.columnCount(), viewport=table.viewport().width()):
                self.assertLessEqual(header.length(), table.viewport().width() + bar.maximum())  # every column
                self.assertEqual(bar.isVisible(), header.length() > table.viewport().width())  # only when needed
                status = header.sectionSize(preview_panel.STATUS_COLUMN)
                text = table.horizontalHeaderItem(preview_panel.STATUS_COLUMN).text()
                self.assertGreaterEqual(status, header.fontMetrics().horizontalAdvance(text))  # header not cut
                self.assertGreaterEqual(table.viewport().height(), table.verticalHeader().length())  # every row
                self.assertFalse(table.verticalScrollBar().isVisible())

    def test_every_column_is_reachable_in_a_narrow_window_and_no_scroll_bar_in_a_wide_one(self):
        # NEW-GUI.2-F1: a 900 x 680 window at 150 % cut Points, Measured DOFs and Damping off with no scroll bar
        w = self.window
        self.inspect(ws.FE, self.manifest)
        self.inspect(ws.EXPERIMENTAL, self.two_sets)
        w.resize(600, 453)  # 900 x 680 physical pixels at 150 %
        self.app.processEvents()
        self.app.processEvents()
        self.assertTrue(any(t.horizontalScrollBar().isVisible() for t in w.findChildren(QTableWidget)))
        self.assert_tables_readable()
        for kind, panel in w.panels.items():  # the tables scroll themselves and never widen the page
            self.assertLessEqual(panel.minimumSizeHint().width(), w.cards[kind].minimumSizeHint().width())
        w.resize(1600, 900)
        self.app.processEvents()
        self.app.processEvents()
        self.assert_tables_readable()
        self.assertFalse(any(t.horizontalScrollBar().isVisible() for t in w.findChildren(QTableWidget)))


class GlyphTests(_Window):
    """Every visible character can be drawn by the widget's font (no empty boxes). The Qt ``offscreen`` platform on
    Windows has no font database at all, so every glyph is a box there: these tests then skip, and they run on the
    real platform (``QT_QPA_PLATFORM=windows``) or wherever a font database exists."""

    def setUp(self):
        from PySide6.QtGui import QFontDatabase

        if not QFontDatabase.families():
            self.skipTest(f"the Qt platform {QApplication.platformName()!r} has no font database (offscreen on "
                          "Windows); run with QT_QPA_PLATFORM=windows to check glyphs")
        super().setUp()

    def test_english_text_and_a_cyrillic_file_name_have_glyphs(self):
        from PySide6.QtGui import QFontMetrics
        from PySide6.QtWidgets import QAbstractButton, QLineEdit

        cyrillic = Path(self._own.name) / "Образец_пластина_эксперимент.unv"
        cyrillic.write_bytes(self.frf.read_bytes())
        panel = self.inspect(ws.EXPERIMENTAL, cyrillic)
        self.inspect(ws.FE, self.manifest)
        self.assertEqual(self.window.cards[ws.EXPERIMENTAL].file_name.text(), cyrillic.name)
        self.assertEqual([f.text() for f in panel.path_fields], [str(cyrillic)])
        missing = set()
        widgets = (self.window.findChildren(QLabel) + self.window.findChildren(QAbstractButton)
                   + self.window.findChildren(QLineEdit))
        for widget in widgets:
            if widget.isVisible():
                metrics = QFontMetrics(widget.font())
                missing |= {(ch, widget.text()[:40]) for ch in widget.text()
                            if not ch.isspace() and not metrics.inFontUcs4(ord(ch))}
        for table in self.window.findChildren(QTableWidget):
            metrics = QFontMetrics(table.font())
            for r in range(table.rowCount()):
                for c in range(table.columnCount()):
                    text = table.item(r, c).text()
                    missing |= {(ch, text[:40]) for ch in text if not ch.isspace() and not metrics.inFontUcs4(ord(ch))}
        self.assertEqual(missing, set())


if __name__ == "__main__":
    unittest.main()
