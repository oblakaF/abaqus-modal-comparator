"""NEW-GUI.3: the shape panels of the PySide6 window, driven headless (Qt ``offscreen`` platform).

After Inspect file each side shows a shape panel with nothing chosen and no image. A shape is drawn only after the
user chooses a mode (FE) or a set and then a record (experimental), a component, and clicks Show shape. The drawing
runs in a worker thread; a changed choice, a replaced or cleared file, Inspect again or a closed window discards it.
The image is the service's PNG scaled to the panel with its proportions kept, so it never widens the window. FRF
peak records show PROVISIONAL beside the image, ambiguous records keep the importer's warning, and a component that
was not measured is refused with the service's reason. The NEW-GUI.2 tables stay read-only. No user file changes.

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
    from PySide6.QtWidgets import QAbstractItemView, QApplication, QTableWidget
except ImportError as error:  # pragma: no cover - depends on the environment
    if os.environ.get("NEW_GUI_REQUIRE_QT") == "1":
        raise
    raise unittest.SkipTest(f"PySide6 is not installed ({error}); install requirements-new-gui.txt to run the "
                            "new interface tests (CI sets NEW_GUI_REQUIRE_QT=1 and runs them)")

from new_gui import shape_model as sm  # noqa: E402
from new_gui import window as window_module  # noqa: E402
from new_gui import workspace_state as ws  # noqa: E402
from services import local_input_registry as registry  # noqa: E402
import frf_unv_support as F  # noqa: E402
import synthetic_plate_support as S  # noqa: E402
import test_local_fe_preview as fe_support  # noqa: E402
from test_local_fe_preview import RIGID, described, write_package  # noqa: E402
from test_new_gui3_shapes import PLANE, geometry_4, mode_55_4  # noqa: E402


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
        with mock.patch.object(fe_support, "NODES", PLANE):
            cls.manifest = write_package(inputs / "package", [(n, f, None) for n, f in enumerate(RIGID, 1)]
                                         + [(7, 101.25, described(101.25)), (8, 133.5, described(133.5))])
            cls.other_manifest = write_package(inputs / "package_b", [(7, 99.0, described(99.0))])
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
                        mock.patch("subprocess.Popen", side_effect=AssertionError("no process for a shape"))):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.folders: list[Path] = []
        real_mkdtemp = tempfile.mkdtemp

        def recorded(*args, **kwargs):
            path = real_mkdtemp(*args, **kwargs)
            if kwargs.get("prefix") == "new_gui_shape_":
                self.folders.append(Path(path))
            return path

        patcher = mock.patch.object(sm.tempfile, "mkdtemp", side_effect=recorded)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.inputs_before = fingerprint(self.inputs)
        self.window = window_module.MainWindow(ask_path=lambda kind, start: "")
        self.window.resize(1100, 800)
        self.window.show()
        self.app.processEvents()
        self.addCleanup(self._close)

    def _close(self):
        self.window.close()
        self.window.wait_for_reads(60)
        self.window.deleteLater()
        self.app.processEvents()
        self.assertEqual(fingerprint(self.inputs), self.inputs_before)  # no user file changed
        self.assertFalse(any(folder.exists() for folder in self.folders))  # every request folder removed

    def inspect(self, kind, path):
        self.assertEqual(self.window.choose_file(kind, str(path)), "")
        self.window.cards[kind].inspect_button.click()
        self.assertTrue(self.window.wait_for_reads(120))
        return self.window.shape_panels[kind]

    def choose(self, panel, index=None, component=None, set_index=None):
        if set_index is not None:
            panel.set_combo.setCurrentIndex(set_index + 1)
        if index is not None:
            panel.item_combo.setCurrentIndex(index + 1)
        if component is not None:
            panel.component_combo.setCurrentIndex(sm.COMPONENTS.index(component))
        self.app.processEvents()

    def show(self, panel):
        panel.show_button.click()
        self.assertTrue(self.window.wait_for_reads(120))
        self.app.processEvents()


class StartTests(_Window):
    def test_nothing_is_chosen_or_drawn_before_the_user_acts(self):
        w = self.window
        for kind in ws.KINDS:
            self.assertFalse(w.shape_panels[kind].isVisible())  # no file, no panel
        fe = self.inspect(ws.FE, self.manifest)
        exp = self.inspect(ws.EXPERIMENTAL, self.two_sets)
        for panel in (fe, exp):
            self.assertTrue(panel.isVisible())
            self.assertIsNone(panel.chosen_index())
            self.assertFalse(panel.show_button.isEnabled())
            self.assertIsNone(panel.image.source)
            self.assertEqual(panel.slot.state, sm.IDLE)
            self.assertFalse(panel.busy())
            self.assertTrue(panel.hint.isVisible())
        self.assertEqual(fe.item_combo.itemText(0), sm.CHOOSE_MODE)
        self.assertEqual(exp.set_combo.itemText(0), sm.CHOOSE_SET)
        self.assertFalse(exp.item_combo.isEnabled())  # a record only after a set
        self.assertEqual(self.folders, [])  # nothing was drawn

    def test_the_nugui2_tables_stay_read_only(self):
        self.inspect(ws.EXPERIMENTAL, self.two_sets)
        for table in self.window.findChildren(QTableWidget):
            self.assertEqual(table.selectionMode(), QAbstractItemView.SelectionMode.NoSelection)
            self.assertEqual(table.editTriggers(), QAbstractItemView.EditTrigger.NoEditTriggers)


class FeTests(_Window):
    def test_every_loaded_mode_is_selectable_and_drawn_on_request(self):
        panel = self.inspect(ws.FE, self.manifest)
        preview = self.window.slots[ws.FE].preview
        self.assertEqual([panel.item_combo.itemData(i) for i in range(1, panel.item_combo.count())],
                         list(range(len(preview.modes))))  # rigid-body modes 1-6 and elastic modes 7, 8
        self.assertEqual([panel.component_combo.itemText(i) for i in range(5)],
                         ["Normal", "Magnitude", "U1", "U2", "U3"])
        for index in (0, 6):  # a rigid-body mode and the first elastic mode
            self.choose(panel, index=index, component="z")
            self.assertEqual(panel.facts.text().splitlines()[0], f"FE mode {preview.modes[index].number}")
            self.assertIsNone(panel.image.source)  # choosing draws nothing
            self.show(panel)
            self.assertEqual(panel.slot.state, sm.SHOWN)
            self.assertFalse(panel.image.source.isNull())
            lines = tuple(sm.render(ws.FE, preview, index, "z", Path(self._own.name) / f"svc{index}").lines)
            self.assertEqual(tuple(panel.caption.text().splitlines()), lines)
        self.assertFalse(panel.provisional.isVisible())

    def test_a_changed_choice_removes_the_shape_until_show_is_clicked(self):
        panel = self.inspect(ws.FE, self.manifest)
        self.choose(panel, index=6, component="normal")
        self.show(panel)
        self.assertIsNotNone(panel.image.source)
        self.choose(panel, component="magnitude")
        self.assertEqual(panel.slot.state, sm.IDLE)
        self.assertIsNone(panel.image.source)
        self.assertEqual(panel.caption.text(), "")
        self.assertFalse(panel.busy())  # nothing is redrawn by itself


class ExperimentalTests(_Window):
    def test_a_set_then_a_record_of_that_set(self):
        panel = self.inspect(ws.EXPERIMENTAL, self.two_sets)
        preview = self.window.slots[ws.EXPERIMENTAL].preview
        self.assertEqual([panel.component_combo.itemText(i) for i in range(5)], ["Normal", "Magnitude", "X", "Y", "Z"])
        self.choose(panel, set_index=1)
        self.assertEqual(panel.item_combo.count(), 1 + len(preview.sets[1].records))
        self.assertEqual(panel.item_combo.itemText(1).split(":")[0], "Record 1")  # record 1 is offered
        self.assertIsNone(panel.chosen_index())  # no record chosen by itself
        self.choose(panel, index=0, component="normal")
        self.assertIs(panel.chosen_set(), preview.sets[1])
        self.show(panel)
        self.assertIn(f"Record 1 of {preview.sets[1].title}", panel.caption.text())
        self.choose(panel, set_index=0)  # another set: the record and the shape are gone
        self.assertIsNone(panel.chosen_index())
        self.assertIsNone(panel.image.source)

    def test_an_unmeasured_component_shows_the_services_refusal(self):
        panel = self.inspect(ws.EXPERIMENTAL, self.two_sets)
        self.choose(panel, set_index=0, index=0, component="x")
        self.show(panel)
        self.assertEqual(panel.slot.state, sm.REFUSED)
        self.assertTrue(panel.status.text().startswith("No shape drawn: X (measurement axes) is not a measured"))
        self.assertIsNone(panel.image.source)

    def test_frf_records_show_provisional_beside_the_image(self):
        panel = self.inspect(ws.EXPERIMENTAL, self.frf)
        self.choose(panel, set_index=0, index=0, component="normal")
        self.assertTrue(panel.provisional.isVisible())
        self.assertEqual(panel.provisional.text(), "PROVISIONAL — NOT A VALIDATED FITTED MODE")
        self.show(panel)
        self.assertTrue(panel.provisional.isVisible())
        self.assertEqual(panel.caption.text().splitlines()[0], sm.PROVISIONAL_TEXT)

    def test_ambiguous_records_keep_the_importer_warning(self):
        import universal_reader

        self.inspect(ws.EXPERIMENTAL, self.frf)  # installs the importer chain first
        datasets = [geometry_4(), mode_55_4(1, 10.0), mode_55_4(2, 20.0, ambiguous=True)]
        with mock.patch.object(universal_reader, "_read_universal_datasets", return_value=datasets):
            panel = self.inspect(ws.EXPERIMENTAL, self.ambiguous)
        self.choose(panel, set_index=0, index=1)
        self.assertTrue(panel.record_warnings.isVisible())
        self.assertIn("dataset 55 record 2", panel.record_warnings.text().lower())
        self.show(panel)
        self.assertTrue(panel.caption.text().startswith("AMBIGUOUS (importer) — dataset 55 record 2"))
        self.choose(panel, index=0)
        self.assertFalse(panel.record_warnings.isVisible())


class _Slow:
    """A drawing that waits until released."""

    def __init__(self):
        self.started, self.release = threading.Event(), threading.Event()
        self.real = sm.render

    def __call__(self, *args, **kwargs):
        self.started.set()
        self.release.wait(30)
        return self.real(*args, **kwargs)


class StaleTests(_Window):
    def start_slow(self, kind, path, **choice):
        panel = self.inspect(kind, path)
        slow = _Slow()
        patcher = mock.patch.object(sm, "render", slow)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(slow.release.set)
        self.choose(panel, **choice)
        self.assertTrue(panel.show_shape())
        self.assertTrue(slow.started.wait(30))
        self.assertEqual(panel.status.text(), sm.DRAWING_TEXT)
        self.assertFalse(panel.show_button.isEnabled())
        return panel, slow

    def finish(self, panel, slow):
        slow.release.set()
        self.assertTrue(self.window.wait_for_reads(120))
        self.app.processEvents()
        self.assertEqual(panel.discarded, 1)
        self.assertIsNone(panel.image.source)

    def test_a_changed_component_discards_the_running_drawing(self):
        panel, slow = self.start_slow(ws.FE, self.manifest, index=6, component="normal")
        self.choose(panel, component="z")
        self.finish(panel, slow)
        self.assertEqual(panel.slot.state, sm.IDLE)

    def test_a_changed_record_discards_the_running_drawing(self):
        panel, slow = self.start_slow(ws.EXPERIMENTAL, self.two_sets, set_index=0, index=0, component="normal")
        self.choose(panel, index=1)
        self.finish(panel, slow)

    def test_a_replaced_file_discards_the_running_drawing(self):
        panel, slow = self.start_slow(ws.FE, self.manifest, index=6, component="normal")
        self.window.choose_file(ws.FE, str(self.other_manifest))
        self.assertFalse(panel.isVisible())
        self.finish(panel, slow)
        self.assertIsNone(panel.preview)

    def test_inspect_again_discards_the_running_drawing_and_the_choice(self):
        panel, slow = self.start_slow(ws.FE, self.manifest, index=6, component="normal")
        self.assertTrue(self.window.inspect_file(ws.FE))  # Inspect again while the shape is drawn
        self.assertFalse(panel.isVisible())
        self.finish(panel, slow)
        self.assertTrue(panel.isVisible())  # the new preview, with nothing chosen
        self.assertIsNone(panel.chosen_index())  # a new preview: nothing chosen

    def test_a_cleared_file_or_a_closed_window_discards_the_running_drawing(self):
        panel, slow = self.start_slow(ws.EXPERIMENTAL, self.two_sets, set_index=0, index=0, component="normal")
        self.window.clear_file(ws.EXPERIMENTAL)
        self.finish(panel, slow)
        panel, slow = self.start_slow(ws.FE, self.manifest, index=6, component="normal")
        self.window.close()
        slow.release.set()
        self.assertTrue(self.window.wait_for_reads(120))
        self.app.processEvents()
        self.assertEqual(panel.discarded, 1)


class LayoutTests(_Window):
    def test_the_image_is_scaled_with_its_proportions_and_never_widens_the_window(self):
        w = self.window
        panel = self.inspect(ws.EXPERIMENTAL, self.two_sets)
        self.choose(panel, set_index=0, index=0, component="normal")
        before = panel.minimumSizeHint().width()
        self.show(panel)
        self.assertLessEqual(panel.minimumSizeHint().width(), before)
        self.assertLessEqual(panel.minimumSizeHint().width(), w.cards[ws.EXPERIMENTAL].minimumSizeHint().width())
        source = panel.image.source
        for width in (1300, 900, 600):
            w.resize(width, 700)
            for _ in range(3):
                self.app.processEvents()
            shown = panel.image.pixmap()
            ratio = shown.devicePixelRatio()
            self.assertLessEqual(shown.width() / ratio, panel.image.width() + 1)  # never wider than the panel
            self.assertAlmostEqual(shown.width() / shown.height(), source.width() / source.height(), delta=0.02)
            self.assertLessEqual(panel.image.height(), panel.image.width() * source.height() / source.width() + 2)

    def test_a_long_mode_name_does_not_widen_the_panel(self):
        panel = self.inspect(ws.FE, self.manifest)
        width = panel.minimumSizeHint().width()
        panel.item_combo.addItem("Mode 7 — " + "a very long description " * 12, 6)
        self.app.processEvents()
        self.assertEqual(panel.minimumSizeHint().width(), width)


if __name__ == "__main__":
    unittest.main()
