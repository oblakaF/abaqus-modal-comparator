"""P6.1: one application, two workflows (no Abaqus).

The main application offers 1. Compare modes (ODB + UNV/UFF) and 2. Calibrate effective material properties
(INP + UNV/UFF); the calibration window opens as a Toplevel of the main Tk root, runs with the fake Abaqus, shows the
status, the effective value and its band and grade as NOT A MATERIAL PROPERTY, and closing the application (window
"X" or File > Exit) never bypasses the calibration's stop safeguards (dummy Abaqus processes).
"""

from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import quick_calibration_support as S  # noqa: E402
from quick_calibration_window import (  # noqa: E402
    STATUS_COLOURS,
    summary_colour,
    summary_text,
)
from services.quick_calibration import AbaqusRunner  # noqa: E402
from test_quick_calibration_cancellation import _Dummy  # noqa: E402


def estimate(grade: str, k: float = 1.1401227249435821, band: float = 10.33600334013618) -> dict:
    constants = {c: {"inp_value": 52000.0, "calibrated_value": 52000.0 * k} for c in ("E1", "E2")}
    return {"status": "ESTIMATE", "overall_grade": grade,
            "estimates": {"E_face": {"multiplier": k, "band_percent": band, "grade": grade, "material": "CFRP_Face",
                                     "constants": constants}}}


class SummaryTests(unittest.TestCase):
    def test_an_approximate_estimate_is_not_presented_as_material_data(self):
        result = estimate("APPROXIMATE")
        text = summary_text(result)
        self.assertTrue(text.startswith("ESTIMATE, grade APPROXIMATE"), text)
        for part in ("E1 = 59,286", "E2 = 59,286", "k = 1.1401", "band ±10.3 %", "NOT A MATERIAL PROPERTY",
                     "NOT validated material data"):
            self.assertIn(part, text)
        self.assertEqual(summary_colour(result), STATUS_COLOURS["APPROXIMATE"])

    def test_good_and_unreliable_estimates_keep_the_label(self):
        good = summary_text(estimate("GOOD", k=0.9, band=1.2))
        self.assertTrue(good.startswith("ESTIMATE, grade GOOD"))
        self.assertIn("NOT A MATERIAL PROPERTY", good)
        self.assertIn("not validated material data", good)
        unreliable = estimate("UNRELIABLE", band=35.0)
        self.assertIn("do not use as a material value", summary_text(unreliable))
        self.assertEqual(summary_colour(unreliable), STATUS_COLOURS["UNRELIABLE"])

    def test_refused_and_baseline_only_show_no_value(self):
        refused = {"status": "REFUSED", "refusal_code": "BUDGET_EXHAUSTED", "estimates": {},
                   "refusal_reasons": ["BUDGET_EXHAUSTED: the limit of 2 new Abaqus FE solve(s) is used up"]}
        text = summary_text(refused)
        self.assertTrue(text.startswith("REFUSED (no value): BUDGET_EXHAUSTED"), text)
        self.assertNotIn("E1", text)
        self.assertEqual(summary_colour(refused), STATUS_COLOURS["REFUSED"])
        baseline = {"status": "BASELINE_ONLY", "estimates": {}, "registration": {"pairs": [
            {"experimental_mode": 4, "fe_mode": 10, "mac": 0.9584584, "fitted_row": True},
            {"experimental_mode": 2, "fe_mode": 9, "mac": 0.5784897, "fitted_row": False}]}}
        text = summary_text(baseline)
        self.assertTrue(text.startswith("BASELINE_ONLY (no estimate, no calibrated INP)"), text)
        self.assertIn("EXP 4 <-> FE 10 MAC 0.9585", text)
        self.assertNotIn("effective", text)
        self.assertEqual(summary_colour(baseline), STATUS_COLOURS["BASELINE_ONLY"])


class _Application:
    """The real main application (every install_* layer of main.py) on a hidden Tk root."""

    def start_application(self):
        import tkinter as tk

        try:
            self.root = tk.Tk()
        except Exception as error:  # noqa: BLE001
            self.skipTest(f"Tk is unavailable: {error}")
        self.root.withdraw()
        self.addCleanup(self._destroy_root)
        import main
        import ui_workflow

        disabled = {"autosave_enabled": False, "restore_on_startup": False, "show_recovery_notice": False}
        with mock.patch.object(ui_workflow, "load_recovery_preferences", return_value=disabled), \
                mock.patch.object(ui_workflow, "discover_abaqus_installations", return_value=()):
            self.application = main.app.ModalComparatorApp(self.root)
        detection = mock.patch("ui_policy.discover_abaqus_installations", return_value=())
        detection.start()
        self.addCleanup(detection.stop)
        return self.application

    def _destroy_root(self) -> None:
        try:
            for job in self.root.tk.splitlist(self.root.tk.call("after", "info")):
                self.root.after_cancel(job)
            self.root.destroy()
        except Exception:  # noqa: BLE001 - already closed by the test
            pass

    def closed(self) -> bool:
        try:
            return not bool(self.root.winfo_exists())
        except Exception:  # noqa: BLE001 - "application has been destroyed"
            return True

    def pump(self, condition, timeout: float = 90.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                self.root.update()
            except Exception:  # noqa: BLE001 - the window was destroyed
                return condition()
            if condition():
                return True
            time.sleep(0.02)
        return condition()


class MainApplicationWorkflowTests(_Application, unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="qc_p6_"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        (self.folder / "model.inp").write_text(S.INP)
        S.write_experiment(self.folder / "exp.unv", 0.9 * S.E0, S.G0, noise=0.001)

    def test_both_workflows_are_offered_in_one_application(self):
        import main
        import quick_calibration_ui as ui
        from runtime_contracts import verify_runtime_contracts

        verify_runtime_contracts(main.app)  # the close owners are the guarded ones
        application = self.start_application()
        bar = application.menu_bar
        cascades = [bar.entrycget(i, "label") for i in range(bar.index("end") + 1) if bar.type(i) == "cascade"]
        self.assertEqual(cascades[:2], ["File", "Workflow"])
        menu = application.workflow_menu
        self.assertEqual([menu.entrycget(i, "label") for i in range(menu.index("end") + 1)],
                         [ui.COMPARE_LABEL, ui.CALIBRATE_LABEL + "..."])
        self.assertEqual(application.compare_workflow_button["text"], "1. Compare modes (ODB + UNV/UFF)")
        self.assertEqual(application.calibrate_workflow_button["text"],
                         "2. Calibrate effective material properties (INP + UNV/UFF)")
        application.tabs.select(application.tabs.tabs()[-1])
        application.compare_workflow_button.invoke()  # workflow 1: the ODB comparison inputs
        self.assertEqual(application.tabs.select(), str(application.input_tab))

    def test_the_calibration_opens_inside_the_application(self):
        import tkinter as tk

        application = self.start_application()
        application.calibrate_workflow_button.invoke()
        window = application._quick_calibration
        self.assertIsInstance(window.root, tk.Toplevel)  # no second Tk root
        self.assertIs(window.root.master, self.root)
        self.assertEqual(window.root.title(), "Quick material calibration (Abaqus + Polytec)")
        application.calibrate_workflow_button.invoke()  # raised again, never duplicated
        self.assertIs(application._quick_calibration, window)
        self.assertEqual([c for c in self.root.winfo_children() if isinstance(c, tk.Toplevel)], [window.root])
        for widget in (window.check_button, window.run_button, window.stop_button, window.open_button,
                       window.report_button):
            self.assertTrue(widget.winfo_exists())
        window.close()  # its own close: idle, so it closes; the application stays open
        self.assertTrue(window.destroyed)
        self.assertFalse(self.closed())
        application._open_quick_calibration()
        self.assertIsNot(application._quick_calibration, window)

    def test_fake_abaqus_calibration_result_report_and_close(self):
        from quick_calibration_window import QuickCalibrationWindow

        application = self.start_application()
        fake = S.FakeAbaqus()
        window = application._open_quick_calibration(
            factory=lambda top: QuickCalibrationWindow(top, fake.solve, fake.extract, threaded=False))
        window.set_inp(str(self.folder / "model.inp"))
        window.unv.set(str(self.folder / "exp.unv"))
        window.out.set(str(self.folder / "out"))
        window.check_inputs()
        self.assertIn("READY", window.readiness.get())
        window.start()
        self.assertIn("Orientation is ambiguous", window.summary.get())
        identity = next(c for c in window.orientation_box["values"]
                        if c.startswith("exp X = +FE X, exp Y = +FE Y, exp Z = +FE Z"))
        window.orientation.set(identity)
        window.start()
        summary = window.summary.get()
        self.assertTrue(summary.startswith("ESTIMATE, grade GOOD"), summary)
        self.assertIn("NOT A MATERIAL PROPERTY", summary)
        self.assertEqual(str(window.summary_label.cget("foreground")), STATUS_COLOURS["GOOD"])
        with mock.patch("quick_calibration_window._open_path") as opened:
            window.report_button.invoke()
            window.open_button.invoke()
        self.assertEqual([call.args[0] for call in opened.call_args_list],
                         [str(self.folder / "out" / "report.txt"), str(self.folder / "out")])
        with mock.patch("quick_calibration_ui.messagebox") as dialogs:
            application._close_requested()  # window "X": an idle calibration closes with the application
        dialogs.showinfo.assert_not_called()
        self.assertTrue(self.closed())

    def test_an_unconfirmed_stop_keeps_the_application_open(self):
        application = self.start_application()
        window = application._open_quick_calibration()
        window.unconfirmed = SimpleNamespace(still_running=lambda: None)  # termination state UNKNOWN
        with mock.patch("quick_calibration_window.messagebox.askyesno", return_value=False) as asked:
            application._close_requested()
        asked.assert_called_once()
        self.assertFalse(self.closed())
        self.assertFalse(window.destroyed)
        self.assertTrue(window.summary.get().startswith("NOT CLOSED"), window.summary.get())
        with mock.patch("quick_calibration_window.messagebox.askyesno", return_value=False):
            application._close_with_session_save()  # File > Exit: the same safeguard
        self.assertFalse(self.closed())
        with mock.patch("quick_calibration_window.messagebox.askyesno", return_value=True):
            application._close_requested()  # verified in Task Manager by the user
        self.assertTrue(window.destroyed)
        self.assertTrue(self.closed())


class ClosingDuringARunTests(_Application, _Dummy):
    """Dummy Abaqus processes (real child processes) run inside the application while it is closed."""

    def setUp(self) -> None:
        super().setUp()
        self.addCleanup(self._kill_leftovers)  # before the folder (and its PID list) is removed, even on failure
        (self.folder / "model.inp").write_text(S.INP)
        S.write_experiment(self.folder / "exp.unv", 0.9 * S.E0, S.G0)

    def running_window(self):
        from quick_calibration_window import QuickCalibrationWindow

        application = self.start_application()
        window = application._open_quick_calibration(factory=lambda top: QuickCalibrationWindow(
            top, runner_factory=lambda config, cancel: AbaqusRunner(self.command, 1, 120.0, cancel)))
        window.set_inp(str(self.folder / "model.inp"))
        window.unv.set(str(self.folder / "exp.unv"))
        window.out.set(str(self.folder / "out"))
        self.assertTrue(self.pump(lambda: window.modal_set.get().startswith("PolyMAX")))
        window.start()
        self.assertTrue(self.pump(lambda: len(self.pids()) >= 2))
        time.sleep(1.5)
        return application, window

    def test_exit_stops_the_run_and_waits_for_confirmed_termination(self):
        application, window = self.running_window()
        with mock.patch("quick_calibration_ui.messagebox.showinfo") as info:
            application._close_with_session_save()  # File > Exit
        info.assert_called_once()
        self.assertFalse(self.closed())  # never closed while the solve may still run
        self.assertTrue(window.summary.get().startswith("CLOSING"), window.summary.get())
        self.assertTrue(self.pump(lambda: window.destroyed))
        self.assert_all_gone()
        self.assertFalse(self.closed())  # the user closes the application again
        application._close_requested()
        self.assertTrue(self.closed())

    def test_window_close_button_is_guarded_the_same_way(self):
        application, window = self.running_window()
        with mock.patch("quick_calibration_ui.messagebox.showinfo"):
            self.root.tk.call(self.root.protocol("WM_DELETE_WINDOW"))  # the main window's "X"
        self.assertFalse(self.closed())
        self.assertTrue(self.pump(lambda: window.destroyed))
        self.assert_all_gone()


if __name__ == "__main__":
    unittest.main()
