"""NEW-GUI.5: the archived registration applicability check in the PySide6 window (Qt ``offscreen``).

The check uses the modal set chosen for the frequency diagnostic (one shared choice). Check reference registration is
disabled, with the reason shown, until both files are read and a set is chosen; before a click the result is "Not
checked" and nothing runs by itself. On the synthetic fixture world (G2c / G2d-1, files read through a stand-in of
the importer's preview), the accepted set is verified with the service's fixture, set, FE geometry, source, frozen
registration, checks and limits, and the warning that nothing is applied. Another set is refused with the service's
reason and the note that the experiment is not thereby wrong; the frequency diagnostic and the shape panels keep
working; FRF records stay PROVISIONAL. Another set, a replaced or cleared file, Inspect again or a closed window
discards a running check. No user or record file changes.

PySide6 comes from ``requirements-new-gui.txt``. Without it these tests are skipped with that reason, except when
``NEW_GUI_REQUIRE_QT=1`` (set in CI), where a missing PySide6 is an error.
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

from new_gui import diagnostic_model as dm  # noqa: E402
from new_gui import preview_model as pm  # noqa: E402
from new_gui import registration_check_model as rm  # noqa: E402
from new_gui import shape_model as sm  # noqa: E402
from new_gui import window as window_module  # noqa: E402
from new_gui import workspace_state as ws  # noqa: E402
from services import local_input_registry as registry  # noqa: E402
import frf_unv_support as F  # noqa: E402
from test_g2d1_governed_registration import experimental_dataset  # noqa: E402
from test_new_gui5_registration import (WorldCase, experimental_preview, fe_preview, fingerprint,  # noqa: E402
                                        other_set, write_fe_package)
from test_new_odb_comparison import new_odb_dataset  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or window_module.create_application([])


class _Window(WorldCase):
    def setUp(self):
        super().setUp()
        self.app = _app()
        own = tempfile.TemporaryDirectory()
        self.addCleanup(own.cleanup)
        self.own = Path(own.name)
        (self.own / "cache").mkdir()
        self.other_odb = write_fe_package(self.own / "SP02_moved_extraction", "moved")  # another FE package
        self.frf = F.write_frf_only(self.own / "frf_only.uff")
        self.before = fingerprint(self.world.root)
        real_read = pm.read_preview

        def read(kind, path, cancel_event=None):  # the World's datasets as Inspect file returns them
            path = Path(path)
            if path == self.package:
                return fe_preview(path, self.fe)
            if path == self.other_odb:
                return fe_preview(path, new_odb_dataset(path, self.fe, shift=0.5))
            if path == self.unv:
                return experimental_preview(path, [experimental_dataset(path, self.fe), other_set(path, self.fe)])
            return real_read(kind, path, cancel_event)

        for patcher in (mock.patch.object(pm, "read_preview", side_effect=read),
                        mock.patch.dict(os.environ, {"LOCALAPPDATA": str(self.own / "cache")}),
                        mock.patch.object(registry, "default_store",
                                          return_value=self.own / "profile" / registry.STORE_NAME)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.window = window_module.MainWindow(ask_path=lambda kind, start: "")
        self.window.resize(1100, 800)
        self.window.show()
        self.window.show_page(1)
        self.app.processEvents()
        self.panel = self.window.registration
        self.addCleanup(self._close)

    def _close(self):
        self.window.close()
        self.window.wait_for_reads(60)
        self.window.deleteLater()
        self.app.processEvents()

    def inspect(self, kind, path):
        self.assertEqual(self.window.choose_file(kind, str(path)), "")
        self.window.cards[kind].inspect_button.click()
        self.assertTrue(self.window.wait_for_reads(120))

    def choose_set(self, index):
        self.window.diagnostic.set_combo.setCurrentIndex(index + 1)
        self.app.processEvents()

    def click(self, button):
        button.click()
        self.assertTrue(self.window.wait_for_reads(120))
        self.app.processEvents()

    def ready(self, set_index=0, fe=None):
        self.inspect(ws.FE, fe or self.package)
        self.inspect(ws.EXPERIMENTAL, self.unv)
        self.choose_set(set_index)


class AvailabilityTests(_Window):
    def test_not_checked_until_a_click_on_the_shared_set_and_nothing_runs_by_itself(self):
        panel = self.panel
        with mock.patch.object(rm, "check", wraps=rm.check) as spy:
            self.assertEqual(panel.badge.text(), "Not checked")
            self.assertFalse(panel.run_button.isEnabled())
            self.assertEqual(panel.why_unavailable.text().splitlines(), [dm.NEED_FE, dm.NEED_EXPERIMENTAL])
            self.inspect(ws.FE, self.package)
            self.inspect(ws.EXPERIMENTAL, self.unv)
            self.assertFalse(panel.run_button.isEnabled())
            self.assertEqual(panel.why_unavailable.text(), dm.NEED_SET)
            self.assertEqual(panel.chosen_set.text(), rm.NO_SET)
            self.choose_set(0)  # the frequency diagnostic's set choice is the only one
            self.assertTrue(panel.run_button.isEnabled())
            self.assertEqual(panel.chosen_set.text(),
                             f"Modal set: {dm.set_title(self.window.slots[ws.EXPERIMENTAL].preview, 0)}")
            self.assertEqual(panel.badge.text(), "Not checked")
            self.assertFalse(self.window.busy())
        spy.assert_not_called()
        self.assertEqual(panel.slot.state, rm.IDLE)
        self.assertFalse(panel.warning.isVisible())
        self.assertFalse(self.window.diagnostic.result_card.isVisible())  # neither command ran
        analysis = self.window.stack.widget(1).widget()
        # NEW-GUI.6 (authorised): the workbench's commands and its unpaired shape views follow; the analysis commands
        # still share one set choice (the shape views' own choices only choose what is drawn, unpaired).
        self.assertEqual([b.text() for b in analysis.findChildren(QPushButton)],
                         ["Run frequency diagnostic", "Check reference registration", "Run verified modal comparison",
                          "Export report...", "Show shape", "Show shape"])  # no second set choice
        shape_views = self.window.comparison.shapes.values()
        self.assertEqual(len([combo for combo in analysis.findChildren(type(self.window.diagnostic.set_combo))
                              if not any(view.isAncestorOf(combo) for view in shape_views)]), 1)


class ResultTests(_Window):
    def test_the_accepted_set_is_verified_and_shown_as_not_applied(self):
        self.ready(0)
        panel = self.panel
        self.click(panel.run_button)
        self.assertEqual(panel.slot.state, rm.VERIFIED_STATE)
        self.assertEqual(panel.badge.text(), rm.VERIFIED)
        self.assertTrue(panel.warning.isVisible())
        self.assertEqual(panel.warning.text(), "Verified archived reference for these selected data only. "
                                               "Registration not applied. Modal identity and MAC not established.")
        self.assertEqual(panel.fields["Specimen and fixture"].text(), "SP02 — SP02/bravo-1-physical")
        self.assertEqual(panel.fields["Archived modal set"].text(), "set-a")
        self.assertIn(self.world.registrations["SP02"].registration_hash, panel.fields["Frozen registration"].text())
        self.assertIn(str(self.unv), panel.fields["Experimental source"].text())
        self.assertEqual(len(panel.checks.text().splitlines()), 5)  # heading and the service's four checks
        self.assertIn("no acceptance gate or threshold is changed", panel.limits.text())
        self.assertFalse(panel.refusal.isVisible())
        self.assertFalse(panel.provisional.isVisible())
        # nothing applied: the frequency diagnostic is still frequency only, with MAC NOT_COMPUTED
        self.click(self.window.diagnostic.run_button)
        self.assertEqual(self.window.diagnostic.view.mac, "NOT_COMPUTED")
        self.assertEqual(self.window.analysis_badge.text(), "FREQUENCY_ONLY_DIAGNOSTIC")
        self.assertEqual(panel.slot.state, rm.VERIFIED_STATE)  # the diagnostic does not touch the check

    def test_another_set_is_refused_and_the_diagnostic_and_shapes_stay_available(self):
        self.ready(1)
        panel = self.panel
        self.click(panel.run_button)
        self.assertEqual(panel.slot.state, rm.REFUSED)
        self.assertEqual(panel.badge.text(), rm.NOT_CONFIRMED)
        self.assertTrue(panel.refusal.text().startswith("Not confirmed by the service: "))
        self.assertIn("modal_set", panel.refusal.text())
        self.assertTrue(panel.refusal_note.isVisible())
        self.assertIn("does not mean that your experiment is physically wrong", panel.refusal_note.text())
        self.assertFalse(panel.warning.isVisible())
        self.click(self.window.diagnostic.run_button)
        self.assertEqual(self.window.diagnostic.slot.state, dm.DONE)
        shape = self.window.shape_panels[ws.EXPERIMENTAL]
        shape.set_combo.setCurrentIndex(2)
        shape.item_combo.setCurrentIndex(1)
        self.app.processEvents()
        self.click(shape.show_button)
        self.assertEqual(shape.slot.state, sm.SHOWN)

    def test_another_fe_geometry_is_refused(self):
        self.ready(0, fe=self.other_odb)
        self.click(self.panel.run_button)
        self.assertEqual(self.panel.slot.state, rm.REFUSED)
        self.assertIn("is not the accepted SP02 FE geometry", self.panel.refusal.text())

    def test_frf_records_stay_provisional_and_are_refused(self):
        self.inspect(ws.FE, self.package)
        self.inspect(ws.EXPERIMENTAL, self.frf)
        self.choose_set(0)
        self.assertTrue(self.panel.provisional.isVisible())
        self.assertEqual(self.panel.provisional.text(), "PROVISIONAL — NOT A VALIDATED FITTED MODE")
        self.click(self.panel.run_button)
        self.assertEqual(self.panel.slot.state, rm.REFUSED)
        self.assertIn("is not the PolyMAX source of an accepted physical registration", self.panel.refusal.text())
        self.assertTrue(self.panel.provisional.isVisible())


class _Slow:
    """A check that waits until released."""

    def __init__(self):
        self.started, self.release = threading.Event(), threading.Event()
        self.real = rm.check

    def __call__(self, *args):
        self.started.set()
        self.release.wait(30)
        return self.real(*args)


class StaleTests(_Window):
    def start_slow(self):
        self.ready(0)
        slow = _Slow()
        patcher = mock.patch.object(rm, "check", slow)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(slow.release.set)
        self.assertTrue(self.panel.run())
        self.assertTrue(slow.started.wait(30))
        self.assertEqual(self.panel.badge.text(), rm.CHECKING)
        self.assertFalse(self.panel.run_button.isEnabled())
        self.assertTrue(self.window.busy())
        return slow

    def finish(self, slow):
        slow.release.set()
        self.assertTrue(self.window.wait_for_reads(120))
        self.app.processEvents()
        self.assertEqual(self.panel.discarded, 1)
        self.assertIsNone(self.panel.view)
        self.assertEqual(self.panel.badge.text(), "Not checked")
        self.assertFalse(self.panel.warning.isVisible())

    def test_another_set_discards_the_running_check(self):
        slow = self.start_slow()
        self.choose_set(1)
        self.finish(slow)

    def test_a_replaced_fe_file_discards_the_running_check(self):
        slow = self.start_slow()
        self.window.choose_file(ws.FE, str(self.other_odb))
        self.finish(slow)

    def test_a_cleared_experimental_file_discards_the_running_check(self):
        slow = self.start_slow()
        self.window.clear_file(ws.EXPERIMENTAL)
        self.finish(slow)
        self.assertEqual(self.panel.chosen_set.text(), rm.NO_SET)

    def test_inspect_again_discards_the_running_check_and_the_set(self):
        slow = self.start_slow()
        self.assertTrue(self.window.inspect_file(ws.EXPERIMENTAL))
        self.finish(slow)
        self.assertEqual(self.panel.why_unavailable.text(), dm.NEED_SET)  # a new preview: no set chosen

    def test_a_closed_window_discards_the_running_check(self):
        slow = self.start_slow()
        self.window.close()
        slow.release.set()
        self.assertTrue(self.window.wait_for_reads(120))
        self.app.processEvents()
        self.assertEqual(self.panel.discarded, 1)
        self.assertIsNone(self.panel.view)

    def test_the_diagnostic_waits_for_a_running_check(self):
        slow = self.start_slow()
        diagnostic = self.window.diagnostic
        self.assertTrue(diagnostic.run())
        threading.Event().wait(0.3)
        self.app.processEvents()
        self.assertEqual(diagnostic.slot.state, dm.RUNNING)  # one heavy service at a time
        slow.release.set()
        self.assertTrue(self.window.wait_for_reads(120))
        self.app.processEvents()
        self.assertEqual(diagnostic.slot.state, dm.DONE)
        self.assertEqual(self.panel.slot.state, rm.VERIFIED_STATE)


class LayoutTests(_Window):
    def test_the_result_adds_no_width_to_the_page(self):
        # The page-level scroll bar itself is checked on Windows: the offscreen font is not Windows'.
        self.ready(0)
        before = self.panel.minimumSizeHint().width()
        self.click(self.panel.run_button)
        self.assertLessEqual(self.panel.minimumSizeHint().width(), before)


if __name__ == "__main__":
    unittest.main()
