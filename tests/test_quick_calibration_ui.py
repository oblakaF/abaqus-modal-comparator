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
        self.assertEqual([menu.entrycget(i, "label") for i in range(menu.index("end") + 1)
                          if menu.type(i) == "command"],
                         [ui.COMPARE_LABEL, ui.CALIBRATE_LABEL + "...", ui.NINE_LABEL + "..."])
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
        confirm = mock.patch("quick_calibration_window.messagebox.askokcancel", return_value=True)  # the run consent
        confirm.start()
        self.addCleanup(confirm.stop)
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

    def test_the_comparison_waits_for_a_running_calibration(self):
        application, window = self.running_window()
        application._validate = mock.Mock(return_value=None)  # the comparison's own first step
        with mock.patch("quick_calibration_ui.messagebox.showwarning") as warned:
            application._start()  # the comparison entry point itself, not only its button
            application.run_button.invoke()
        self.assertEqual(warned.call_count, 2)
        application._validate.assert_not_called()
        self.assertIn("a quick calibration is running", application.status.get())
        window.stop()
        with mock.patch("quick_calibration_ui.messagebox.showwarning") as warned:
            application._start()  # still stopping: refused, nothing interrupted
        self.assertIn("stopping", warned.call_args[0][1])
        self.assertTrue(self.pump(lambda: not window.running() and window.summary.get().startswith("STOPPED")))
        self.assert_all_gone()
        application._start()  # idle again: the comparison is available
        application._validate.assert_called_once()


class RunConfirmationTests(unittest.TestCase):
    """Conservative window defaults and the explicit consent before a real Abaqus run (no solver executes)."""

    def setUp(self) -> None:
        try:
            import tkinter as tk

            self.root = tk.Tk()
        except Exception as error:  # noqa: BLE001
            self.skipTest(f"Tk is unavailable: {error}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.folder = Path(tempfile.mkdtemp(prefix="qc_p6_confirm_"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        (self.folder / "model.inp").write_text(S.INP)
        S.write_experiment(self.folder / "exp.unv", 0.9 * S.E0, S.G0, noise=0.001)

    def window(self, *args, **kwargs):
        from quick_calibration_window import QuickCalibrationWindow

        window = QuickCalibrationWindow(self.root, *args, threaded=False, **kwargs)
        window.set_inp(str(self.folder / "model.inp"))
        window.unv.set(str(self.folder / "exp.unv"))
        window.out.set(str(self.folder / "out"))
        return window

    def test_conservative_defaults_stay_editable(self):
        from services.quick_calibration import DEFAULT_MAX_NEW_FE_SOLVES

        window = self.window()
        self.assertEqual((window.cpus.get(), window.max_new_fe_solves.get()), ("1", "8"))
        data = window.config_data()
        self.assertEqual((data["cpus"], data["max_new_fe_solves"]), (1, "8"))
        window.cpus.set("2")
        window.max_new_fe_solves.set("12")
        self.assertEqual((window.config_data()["cpus"], window.config_data()["max_new_fe_solves"]), (2, "12"))
        window.baseline_only.set(True)
        window._baseline_only_changed()
        self.assertEqual(window.max_new_fe_solves.get(), "1")  # baseline only: exactly one new FE solve
        self.assertEqual(DEFAULT_MAX_NEW_FE_SOLVES, 24)  # the service cap is unchanged (CLI: test_..._fe_budget)

    def test_cancel_starts_nothing(self):
        factory = mock.Mock()
        window = self.window(runner_factory=factory)
        with mock.patch("quick_calibration_window.messagebox.askokcancel", return_value=False) as asked:
            window.start()
        asked.assert_called_once()
        message = asked.call_args[0][1]
        for part in ("CPUs: 1", "Maximum NEW FE solve attempts: 8", f"Output folder: {self.folder / 'out'}", "RAM",
                     "paging file", "scratch space", "GB in the output folder", "licence"):
            self.assertIn(part, message)
        factory.assert_not_called()  # no runner, so no Abaqus process
        self.assertFalse((self.folder / "out").exists())  # nothing written
        self.assertTrue(window.summary.get().startswith("NOT STARTED: cancelled by the user"), window.summary.get())
        self.assertEqual(str(window.run_button["state"]), "normal")

    def test_baseline_only_consent_names_the_single_solve(self):
        window = self.window(runner_factory=mock.Mock())
        window.baseline_only.set(True)
        window._baseline_only_changed()
        with mock.patch("quick_calibration_window.messagebox.askokcancel", return_value=False) as asked:
            window.start()
        self.assertIn("Maximum NEW FE solve attempts: 1 (baseline only", asked.call_args[0][1])

    def test_accepted_run_uses_the_runner_with_the_fake_solver(self):
        fake = S.FakeAbaqus()
        factory = mock.Mock(return_value=SimpleNamespace(solve=fake.solve, extract=fake.extract))
        window = self.window(runner_factory=factory)
        with mock.patch("quick_calibration_window.messagebox.askokcancel", return_value=True) as asked:
            window.start()
            self.assertIn("Orientation is ambiguous", window.summary.get())
            identity = next(c for c in window.orientation_box["values"]
                            if c.startswith("exp X = +FE X, exp Y = +FE Y, exp Z = +FE Z"))
            window.orientation.set(identity)
            window.start()
        self.assertEqual(asked.call_count, 2)  # every run asks
        self.assertEqual(factory.call_count, 2)
        self.assertGreater(fake.solves, 0)
        self.assertTrue(window.summary.get().startswith("ESTIMATE, grade GOOD"), window.summary.get())

    def test_injected_fake_abaqus_runs_without_a_dialog(self):
        fake = S.FakeAbaqus()
        window = self.window(fake.solve, fake.extract)
        with mock.patch("quick_calibration_window.messagebox.askokcancel",
                        side_effect=AssertionError("no consent dialog for an injected solver")):
            window.start()
        self.assertGreater(fake.solves, 0)
        self.assertIn("Orientation is ambiguous", window.summary.get())


class MutualExclusionTests(_Application, unittest.TestCase):
    """Never both workflows at once; both stay available when idle; nothing running is interrupted."""

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="qc_p6_exclusive_"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        (self.folder / "model.inp").write_text(S.INP)
        S.write_experiment(self.folder / "exp.unv", 0.9 * S.E0, S.G0, noise=0.001)

    def fake_window(self, application, fake):
        from quick_calibration_window import QuickCalibrationWindow

        window = application._open_quick_calibration(
            factory=lambda top: QuickCalibrationWindow(top, fake.solve, fake.extract, threaded=False))
        window.set_inp(str(self.folder / "model.inp"))
        window.unv.set(str(self.folder / "exp.unv"))
        window.out.set(str(self.folder / "out"))
        return window

    def test_no_calibration_while_the_comparison_runs_stops_or_owns_a_process(self):
        from ui_policy import AnalysisState

        application = self.start_application()
        fake = S.FakeAbaqus()
        window = self.fake_window(application, fake)
        states = (
            ({"running": True}, "the ODB comparison (workflow 1) is running"),
            ({"running": True, "analysis_state": AnalysisState.STOPPING}, "the ODB comparison (workflow 1) is stopping"),
            ({"running": False, "_owned_analysis_process": mock.Mock(poll=mock.Mock(return_value=None))},
             "an Abaqus process of the ODB comparison (workflow 1) is still active"),
        )
        original = {name: getattr(application, name) for name in ("running", "analysis_state",
                                                                   "_owned_analysis_process")}
        for state, reason in states:
            with self.subTest(reason=reason):
                for name, value in state.items():
                    setattr(application, name, value)
                with mock.patch("quick_calibration_window.messagebox.showwarning") as warned:
                    window.start()
                warned.assert_called_once()
                self.assertIn(reason, warned.call_args[0][1])
                self.assertTrue(window.summary.get().startswith(f"NOT STARTED: {reason}"), window.summary.get())
                self.assertEqual(fake.solves, 0)
                self.assertFalse((self.folder / "out").exists())
                self.assertTrue(application.running == state["running"])  # the comparison is not interrupted
                for name, value in original.items():
                    setattr(application, name, value)
        window.start()  # idle: the calibration is available
        self.assertGreater(fake.solves, 0)

    def test_no_comparison_while_a_calibration_runs_stops_or_is_unconfirmed(self):
        application = self.start_application()
        window = application._open_quick_calibration()
        application._validate = mock.Mock(return_value=None)

        def refused(reason: str) -> None:
            with mock.patch("quick_calibration_ui.messagebox.showwarning") as warned:
                application._start()
            warned.assert_called_once()
            self.assertIn(reason, warned.call_args[0][1])
            self.assertIn(reason, application.status.get())
            application._validate.assert_not_called()
            self.assertFalse(application.running)

        with mock.patch.object(window, "running", return_value=True):
            refused("a quick calibration is running")
            window.cancel_event.set()
            refused("a quick calibration is stopping")
        window.cancel_event.clear()
        window.closing = True
        refused("the quick calibration window is closing")
        window.closing = False
        window.unconfirmed = SimpleNamespace(still_running=lambda: None)  # UNKNOWN: never treated as stopped
        refused("not confirmed")
        window.unconfirmed = SimpleNamespace(still_running=lambda: [mock.Mock(pid=4242)])
        refused("not confirmed")
        window.unconfirmed = SimpleNamespace(still_running=lambda: [])  # confirmed gone by the tracker
        application._start()
        application._validate.assert_called_once()  # idle: the comparison is available

    def test_runtime_contract_guards_the_comparison_entry_point(self):
        import main

        self.assertEqual(main.app.ModalComparatorApp._start.__module__, "quick_calibration_ui")


if __name__ == "__main__":
    unittest.main()
