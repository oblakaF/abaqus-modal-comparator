"""PRIORITY-0 / RC6: the direct ODB import in the PySide6 window, driven headless (Qt ``offscreen``), with a fake
runner in place of the Abaqus bridge (no Abaqus is installed or started).

The user scenario: choose an .odb → Extract modal results... → the dialog shows the launcher found (or that none was
found, with the fixes), the results folder and the range → Extract modal results asks for confirmation → the
extraction runs in a worker thread with progress → Use this package puts the package's manifest.json into the
workspace and reads it (Inspect file), so the modes, frequencies and shapes (U1/U2/U3) are available as for any
extracted package. A refused confirmation, a cancellation and an error start or keep nothing.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

try:
    from PySide6.QtWidgets import QApplication
except ImportError as error:  # pragma: no cover - depends on the environment
    if os.environ.get("NEW_GUI_REQUIRE_QT") == "1":
        raise
    raise unittest.SkipTest(f"PySide6 is not installed ({error})")

from abaqus_bridge import AbaqusExtractionError  # noqa: E402
from new_gui import odb_import_model as om  # noqa: E402
from new_gui import preview_model as pm  # noqa: E402
from new_gui import window as window_module  # noqa: E402
from new_gui import workspace_state as ws  # noqa: E402
from new_gui.odb_import_dialog import OdbImportDialog  # noqa: E402
from new_gui.shape_model import COMPONENT_LABEL  # noqa: E402
from services import local_input_registry as registry  # noqa: E402
from services import odb_import_service as svc  # noqa: E402
from test_odb_import_service import FOUND, NONE, fake_runner  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or window_module.create_application([])


class _Case(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.odb = self.root / "inputs" / "plate.odb"
        self.odb.parent.mkdir()
        self.odb.write_bytes(b"synthetic odb; never opened " * 50)
        self.results = self.root / "results"
        self.cache = self.root / "cache"
        self.cache.mkdir()
        for patcher in (mock.patch.dict(os.environ, {"LOCALAPPDATA": str(self.cache)}),
                        mock.patch.object(registry, "default_store",
                                          return_value=self.root / "profile" / registry.STORE_NAME),
                        mock.patch("subprocess.Popen", side_effect=AssertionError("no process: Abaqus is never "
                                                                                   "started in these tests"))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def wait(self, dialog, timeout=60.0):
        import time
        end = time.monotonic() + timeout
        while dialog.busy() and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.02)
        self.app.processEvents()
        return not dialog.busy()


class DialogTests(_Case):
    def dialog(self, **kwargs):
        options = {"results_folder": self.results, "runner": fake_runner(), "confirm": lambda: True,
                   "discover": FOUND}
        options.update(kwargs)
        dialog = OdbImportDialog(self.odb, **options)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_the_plan_is_shown_and_nothing_starts_by_itself(self):
        dialog = self.dialog()
        self.assertTrue(dialog.extract_button.isEnabled())
        self.assertFalse(dialog.cancel_button.isEnabled())
        self.assertFalse(dialog.use_button.isEnabled())
        self.assertIn("Abaqus found", dialog.availability.text())
        self.assertEqual((dialog.start_mode.value(), dialog.end_mode.value()), (1, 30))
        self.assertEqual(dialog.slot.state, om.IDLE)
        self.assertFalse(self.results.exists())
        self.assertEqual(dialog._runner.calls, [])

    def test_without_abaqus_the_explanation_and_the_fixes_are_shown_and_the_button_is_disabled(self):
        dialog = self.dialog(discover=NONE)
        self.assertFalse(dialog.extract_button.isEnabled())
        self.assertIn("No Abaqus launcher was found", dialog.availability.text())
        self.assertIn("Install Abaqus", dialog.fixes.text())
        self.assertIn("manifest.json", dialog.fixes.text())
        self.assertFalse(dialog.extract())
        self.assertEqual(dialog._runner.calls, [])
        bat = self.root / "abaqus.bat"
        bat.write_text("@echo off\n", encoding="utf-8")
        os.chmod(bat, 0o755)  # on POSIX (CI) a launcher must be executable to count
        self.assertTrue(dialog.choose_launcher(str(bat)))  # Browse: a launcher the user points to
        self.assertTrue(dialog.extract_button.isEnabled())

    def test_a_refused_confirmation_starts_nothing(self):
        dialog = self.dialog(confirm=lambda: False)
        self.assertFalse(dialog.extract())
        self.assertIn("not confirmed", dialog.message.text())
        self.assertEqual(dialog._runner.calls, [])
        self.assertEqual(dialog.slot.state, om.IDLE)

    def test_a_confirmed_extraction_runs_with_progress_and_offers_the_package(self):
        dialog = self.dialog()
        self.assertTrue(dialog.extract())
        self.assertEqual(dialog.slot.state, om.RUNNING)
        self.assertTrue(dialog.cancel_button.isEnabled())
        self.assertTrue(self.wait(dialog))
        self.assertEqual(dialog.slot.state, om.DONE, dialog.message.text())
        self.assertEqual(dialog.manifest_path, self.results / "plate_modes_1-30" / "manifest.json")
        self.assertTrue(dialog.use_button.isEnabled())
        log = dialog.log.toPlainText()
        self.assertIn("identifying the ODB content", log)
        self.assertIn("starting Abaqus Python", log)
        self.assertIn("package written", log)
        rows = {dialog.result.itemAt(i, dialog.result.ItemRole.LabelRole).widget().text():
                dialog.result.itemAt(i, dialog.result.ItemRole.FieldRole).widget().text()
                for i in range(dialog.result.rowCount())}
        self.assertEqual(rows["Extracted modes"], "7-9 (3 modes)")
        self.assertIn("1-16", rows["Modes in the ODB"])
        self.assertIn("Requested Abaqus modes 1-30", rows["Range note"])
        self.assertTrue((dialog.manifest_path.parent / svc.SOURCE_RECORD).is_file())

    def test_a_failed_extraction_is_explained_and_offers_no_package(self):
        def failing(**kwargs):
            raise AbaqusExtractionError("Abaqus could not extract the ODB results.\n\nFatal licence error\n\n"
                                        "Full log: x")

        dialog = self.dialog(runner=failing)
        self.assertTrue(dialog.extract())
        self.assertTrue(self.wait(dialog))
        self.assertEqual(dialog.slot.state, om.FAILED)
        self.assertIn("Fatal licence error", dialog.message.text())
        self.assertIsNone(dialog.manifest_path)
        self.assertFalse(dialog.use_button.isEnabled())
        self.assertTrue(dialog.extract_button.isEnabled())  # it can be tried again

    def test_cancellation_stops_the_run_and_keeps_nothing(self):
        started = __import__("threading").Event()

        def slow(**kwargs):
            started.set()
            cancel = kwargs["cancel_event"]
            while not cancel.is_set():
                __import__("time").sleep(0.01)
            from abaqus_bridge import AnalysisCancelled
            raise AnalysisCancelled("Analysis stopped by user.")

        dialog = self.dialog(runner=slow)
        self.assertTrue(dialog.extract())
        self.assertTrue(started.wait(10))
        self.assertTrue(dialog.cancel_extraction())
        self.assertTrue(self.wait(dialog))
        self.assertEqual(dialog.slot.state, om.CANCELLED)
        self.assertIn("cancelled", dialog.message.text())
        self.assertIsNone(dialog.manifest_path)
        self.assertTrue((self.results / "plate_modes_1-30" / "INCOMPLETE.txt").is_file())

    def test_the_range_is_the_users_and_the_first_elastic_mode_is_kept(self):
        dialog = self.dialog(runner=fake_runner(modes=(1, 2, 3, 4, 5, 6, 7, 8), available=(1, 8)))
        dialog.start_mode.setValue(7)
        dialog.end_mode.setValue(8)
        self.assertTrue(dialog.extract())
        self.assertTrue(self.wait(dialog))
        self.assertEqual(dialog.slot.outcome.result.extracted_modes, (7, 8))
        self.assertEqual(dialog.manifest_path.parent.name, "plate_modes_7-8")


class WindowTests(_Case):
    def setUp(self):
        super().setUp()
        self.runner = fake_runner()
        self.window = window_module.MainWindow(
            ask_path=lambda kind, start: "",
            odb_import_options={"results_folder": self.results, "runner": self.runner, "confirm": lambda: True,
                                "discover": FOUND})
        self.window.show()
        self.app.processEvents()
        self.addCleanup(self._close)

    def _close(self):
        self.window.close()
        self.window.wait_for_reads(60)
        self.window.deleteLater()
        self.app.processEvents()

    def test_the_odb_is_offered_for_extraction_and_the_package_reaches_the_workspace(self):
        w = self.window
        self.assertEqual(w.choose_file(ws.FE, str(self.odb)), "")
        card = w.cards[ws.FE]
        self.assertTrue(card.extract_button.isVisible())
        self.assertTrue(card.odb_note.isVisible())
        self.assertIn("extracted on your command", w.workspace.fe.file_type)
        self.assertFalse(card.extract_button.isVisible() and self.results.exists())  # choosing starts nothing
        dialog = w.open_odb_import()
        self.assertIsNotNone(dialog)
        self.assertTrue(dialog.extract())
        self.assertTrue(w.wait_for_reads(120))
        self.assertEqual(dialog.slot.state, om.DONE, dialog.message.text())
        dialog.use_button.click()
        self.assertTrue(w.wait_for_reads(120))
        self.assertEqual(w.workspace.fe.path, self.results / "plate_modes_1-30" / "manifest.json")
        self.assertFalse(card.extract_button.isVisible())
        self.assertEqual(w.slots[ws.FE].state, pm.READ, w.slots[ws.FE].message)
        preview = w.slots[ws.FE].preview
        self.assertEqual([m.number for m in preview.modes], [7, 8, 9])
        self.assertIsNotNone(w.slots[ws.FE].identity)  # the package identity, as for any extracted package
        # every mode and U1 / U2 / U3 are offered by the existing shape panel
        panel = w.shape_panels[ws.FE]
        self.assertEqual(panel.item_combo.count(), 1 + 3)  # "choose" + every extracted mode, the first included
        self.assertIn("7", panel.item_combo.itemText(1))
        components = [panel.component_combo.itemText(i) for i in range(panel.component_combo.count())]
        for label in ("U1", "U2", "U3"):
            self.assertIn(COMPONENT_LABEL[ws.FE][{"U1": "x", "U2": "y", "U3": "z"}[label]], components)
        self.assertEqual(len(self.runner.calls), 1)

    def test_inspect_of_an_odb_points_to_the_extraction(self):
        w = self.window
        w.choose_file(ws.FE, str(self.odb))
        w.cards[ws.FE].inspect_button.click()
        self.assertTrue(w.wait_for_reads(60))
        self.assertEqual(w.slots[ws.FE].state, pm.FAILED)
        self.assertIn("Extract modal results", w.slots[ws.FE].message)
        self.assertEqual(self.runner.calls, [])

    def test_a_manifest_is_still_imported_directly(self):
        from test_local_fe_preview import described, write_package

        manifest = write_package(self.root / "inputs" / "package", [(7, 101.25, described(101.25))])
        w = self.window
        self.assertEqual(w.choose_file(ws.FE, str(manifest)), "")
        self.assertFalse(w.cards[ws.FE].extract_button.isVisible())
        self.assertIsNone(w.open_odb_import())
        w.cards[ws.FE].inspect_button.click()
        self.assertTrue(w.wait_for_reads(60))
        self.assertEqual(w.slots[ws.FE].state, pm.READ)
        self.assertEqual(self.runner.calls, [])


if __name__ == "__main__":
    unittest.main()
