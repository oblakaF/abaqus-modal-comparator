"""APP-E2E.2 (P-1): a result whose inputs changed is never left active (real main window, synthetic data, no process).

After an analysis, changing the FE file, the experimental file, the mode range, the modal set, the calibration, the
registration choice or the confirmed orientation makes the shown result inactive at once: tables, cards, plots and mode
views are cleared, the PDF / Excel export of that result is disabled and the status says to run the analysis again.
This holds for an established comparison (pairs and MAC) and for a FREQUENCY_ONLY_DIAGNOSTIC. Settings that do not
change the result (workspace, Abaqus command) keep it. A run whose inputs changed while it was running never shows its
result. Reports already written stay on disk; a new analysis shows its result and enables the export again.
"""

from __future__ import annotations

import copy
import functools
import gc
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import synthetic_plate_support as S  # noqa: E402
from coordinate_calibration import MANUAL  # noqa: E402
from services import modal_data_viewer as viewer  # noqa: E402
from services import new_odb_comparison as new  # noqa: E402
from test_modal_data_viewer import _Files, ambiguity, load_unv  # noqa: E402

STALE = "Inputs changed after the analysis"
DISCARDED = "Inputs changed while the analysis was running"


class _App(_Files):
    @classmethod
    def setUpClass(cls) -> None:
        cls._world_folder = tempfile.mkdtemp(prefix="p1_world_")
        cls._comparison = None

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls._world_folder, ignore_errors=True)

    def comparison_result(self):
        """A real established comparison (pairs and MAC) of the synthetic SP-02 world, as in the viewer tests."""
        cls = type(self)
        if cls._comparison is None:
            from test_g2c_archived_sensitivity_evidence import World
            from test_g2d1_governed_registration import experimental_dataset, fe_dataset
            from test_new_odb_comparison import new_odb_dataset

            import main

            folder = Path(cls._world_folder)
            world = World(str(folder))
            odb, unv = world.files["SP02"]
            baseline = fe_dataset(odb)
            experimental = experimental_dataset(unv, baseline)
            target = folder / "data" / "SP02_new_model.odb"
            target.write_bytes(b"another FE result with the accepted mesh " * 4000)
            fe = new_odb_dataset(target, baseline)
            with world.pins():
                reuse = functools.partial(new.bind_registration_by_fe_geometry, repo_root=world.root)(
                    unv, fe, experimental)
            result = main.app.compare_modal_datasets(fe, experimental, frozen_registration=reuse.registration)
            result.geometry.calibration_details.setdefault("scale_x", 1.0)
            result.geometry.calibration_details.setdefault("scale_y", 1.0)
            result.loaded_modal_data = viewer.LoadedModalData(fe, experimental, directory=folder / "views",
                                                              registration=viewer.ESTABLISHED)
            cls._comparison = result
        self.assertTrue(cls._comparison.pairs)
        return copy.deepcopy(cls._comparison)

    def application(self):
        try:
            import tkinter as tk

            root = tk.Tk()
        except Exception as error:  # noqa: BLE001
            self.skipTest(f"Tk is unavailable: {error}")
        self.addCleanup(gc.collect)  # the window's objects are freed here, on the main thread
        self.addCleanup(lambda: root.destroy() if root.winfo_exists() else None)
        self.addCleanup(self.cancel_after_jobs, root)
        self.addCleanup(self.join_background_threads)  # runs first (cleanups are last in, first out)
        root.withdraw()
        import main
        import ui_workflow

        disabled = {"autosave_enabled": False, "restore_on_startup": False, "show_recovery_notice": False}
        with mock.patch.object(ui_workflow, "load_recovery_preferences", return_value=disabled), \
                mock.patch.object(ui_workflow, "discover_abaqus_installations", return_value=()):
            application = main.app.ModalComparatorApp(root)
        application.mode_viewer.threaded = False  # deterministic rendering in tests
        self.root = root
        self.other_unv = S.write_experiment(self.folder / "other.unv", S.E0 * 1.1, S.G0)
        self.other_odb = self.folder / "other.odb"
        self.other_odb.write_bytes(b"another synthetic ODB stand-in; never opened")
        application.abaqus_path.set(str(self.folder / "plate.odb"))
        application.experimental_path.set(str(self.fitted_path))
        application.workspace_path.set(str(self.folder / "workspace"))
        self.settle(application)
        # the calibration of this experimental file is confirmed, as Run asks before every analysis
        application.experimental_unit_source.set("manually selected")
        self.assertTrue(application._bind_source_calibration())
        return application

    @staticmethod
    def join_background_threads() -> None:
        """The modal-set discovery and the accepted-registration pre-check run on daemon threads that hold the
        window; they end before the window is destroyed, so no Tk object is ever released on another thread."""
        deadline = time.monotonic() + 60
        for thread in threading.enumerate():
            if thread is not threading.main_thread() and thread.daemon:
                thread.join(max(0.0, deadline - time.monotonic()))

    @staticmethod
    def cancel_after_jobs(root) -> None:
        try:
            jobs = root.tk.splitlist(root.tk.call("after", "info"))
        except Exception:  # noqa: BLE001  (already destroyed)
            return
        for job in jobs:
            try:
                root.after_cancel(str(job))
            except Exception:  # noqa: BLE001
                pass

    def settle(self, application) -> None:
        """Let the background modal-set discovery and the accepted-registration pre-check finish (Tk event loop)."""
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and getattr(application, "_modal_set_discovery_state", "") == "loading":
            self.root.update()
            time.sleep(0.02)
        quiet = time.monotonic() + 0.4  # the pre-check of tiny synthetic files posts its answer within this time
        while time.monotonic() < quiet:
            self.root.update()
            time.sleep(0.02)

    def start(self, application) -> None:
        """The real Run: the validation (a calibration confirmation dialog) is answered, the worker does not run;
        the test delivers its outcome through the real completion handlers, as the worker would."""
        values = (Path(application.abaqus_path.get()), Path(application.experimental_path.get()),
                  self.folder / "workspace", 1, 9, "abaqus", 1.0, None)
        with mock.patch.object(application, "_validate", return_value=values), \
                mock.patch.object(application, "_worker", side_effect=lambda *_: None):
            application._start()
        self.assertTrue(application.running)
        application.cache = self.folder / "cache"

    def established(self, application):
        self.start(application)
        application._complete(self.comparison_result())
        self.assert_active_comparison(application)
        return application

    def diagnostic(self, application):
        self.start(application)
        experimental = load_unv(self.fitted_path)
        error = ambiguity()
        error.frequency_only_diagnostic = new.frequency_only_diagnostic(self.fe, experimental, "8 orientations")
        error.loaded_modal_data = viewer.LoadedModalData(
            self.fe, experimental, directory=self.folder / "views", registration=viewer.AMBIGUOUS,
            reason="8 orientations", frequency_diagnostic=error.frequency_only_diagnostic)
        application._failed(error)
        self.assertFalse(application.running)
        self.assertIsNotNone(application._diagnostic_export_source)
        self.assertEqual(application.pdf_button.cget("text"), "Export diagnostic PDF")
        self.assertEqual(str(application.pdf_button.cget("state")), "normal")
        self.assertIsNotNone(application.mode_viewer.loaded)
        return application

    def assert_active_comparison(self, application) -> None:
        self.assertFalse(application.running)
        self.assertIsNotNone(application.result)
        self.assertTrue(application.item_to_pair)
        self.assertEqual(str(application.pdf_button.cget("state")), "normal")
        self.assertEqual(str(application.excel_button.cget("state")), "normal")
        self.assertEqual(application.pdf_button.cget("text"), "Export PDF report")
        self.assertNotIn(STALE, application.status.get())

    def assert_inactive(self, application, message=STALE) -> None:
        self.assertFalse(application.running)
        self.assertIsNone(application.result)
        self.assertIsNone(application.cache)
        self.assertEqual(application.item_to_pair, {})
        rows = [application.table.item(k) for k in application.table.get_children()]
        self.assertTrue(all("empty" in row["tags"] for row in rows), rows)  # only the empty-state row
        for name in ("pdf_button", "excel_button", "export_all_button"):
            button = getattr(application, name, None)
            if button is not None:
                self.assertEqual(str(button.cget("state")), "disabled", name)
        self.assertIsNone(application._diagnostic_export_source)
        self.assertIsNone(application.mode_viewer.loaded)
        self.assertEqual(application.mode_viewer.fe.entries, [])
        self.assertEqual(application.metric_mac.cget("text"), "—")
        self.assertTrue(application.status.get().startswith(message), application.status.get())
        self.assertTrue(application.details.get("1.0", "end").startswith(message))
        with mock.patch("tkinter.messagebox.showinfo") as shown, \
                mock.patch("tkinter.filedialog.asksaveasfilename", side_effect=AssertionError("no export")):
            application._pdf()  # e.g. Reports menu: nothing of the old result can be exported
            application._excel()
        self.assertEqual([call.args[0] for call in shown.call_args_list], ["Not ready yet", "Not ready yet"])


class ChangedInputTests(_App):
    def changes(self, application):
        return {
            "experimental file": lambda: application.experimental_path.set(str(self.other_unv)),
            "FE file": lambda: application.abaqus_path.set(str(self.other_odb)),
            "first mode": lambda: application.start_mode.set(2),
            "last mode": lambda: application.end_mode.set(8),
            "modal set": lambda: application.experimental_modal_set_key.set("another-set"),
            "model length unit": lambda: application.abaqus_model_unit.set("m"),
            "mapping mode": lambda: application.coordinate_mapping_mode.set(MANUAL),
            "accepted registration option": lambda: application.use_governed_registration.set(True),
        }

    def test_each_input_of_a_comparison_clears_it_and_its_export(self):
        for number, name in enumerate(self.changes(None)):
            with self.subTest(change=name):
                application = self.established(self.application())
                written = self.folder / f"earlier_{number}.pdf"
                written.write_bytes(b"%PDF report exported before the change")
                self.changes(application)[name]()
                self.assert_inactive(application)
                self.assertEqual(written.read_bytes(), b"%PDF report exported before the change")  # never deleted

    def test_a_frequency_only_diagnostic_is_cleared_with_its_diagnostic_export(self):
        for name in ("experimental file", "FE file", "last mode"):
            with self.subTest(change=name):
                application = self.diagnostic(self.application())
                self.changes(application)[name]()
                self.assert_inactive(application)
                self.assertEqual(application.pdf_button.cget("text"), "Export PDF report")

    def test_an_unusable_experiment_diagnostic_is_cleared(self):
        application = self.application()
        self.start(application)
        error = viewer.ExperimentalDataUnavailable("The experimental file could not be used")
        error.loaded_modal_data = viewer.LoadedModalData(self.fe, None, experimental_error="no modal vectors",
                                                         directory=self.folder / "views")
        application._failed(error)
        self.assertIsNotNone(application._diagnostic_export_source)
        application.abaqus_path.set(str(self.other_odb))
        self.assert_inactive(application)

    def test_settings_that_do_not_change_the_result_keep_it(self):
        application = self.established(self.application())
        application.workspace_path.set(str(self.folder / "another_workspace"))
        application.abaqus_command.set("abq2025")
        application.experimental_path.set(str(self.fitted_path))  # the same file chosen again
        self.settle(application)
        self.assert_active_comparison(application)

    def test_choosing_a_file_with_several_modal_sets_again_needs_its_set_again(self):
        application = self.application()
        several = S.write_experiment(self.folder / "several.unv", S.E0, S.G0, sets=(("Bravo", 6), ("Charlie", 4)))
        application.experimental_path.set(str(several))
        self.settle(application)
        keys = [item.key for item in application.available_experimental_modal_sets]
        self.assertEqual(len(keys), 2)
        application.experimental_modal_set_key.set(keys[0])  # the user's choice of set
        application.experimental_unit_source.set("manually selected")
        self.assertTrue(application._bind_source_calibration())
        self.established(application)
        application.experimental_path.set(str(several))  # the same file again: the set must be chosen again
        self.settle(application)
        self.assertEqual(application.experimental_modal_set_key.get(), "")
        self.assert_inactive(application)

    def test_a_new_analysis_shows_its_result_and_enables_the_export_again(self):
        application = self.established(self.application())
        application.experimental_path.set(str(self.other_unv))
        self.settle(application)
        self.assert_inactive(application)
        self.start(application)
        application._complete(self.comparison_result())
        self.assert_active_comparison(application)
        application.end_mode.set(8)  # and the new result is guarded in the same way
        self.assert_inactive(application)


class RunningAnalysisTests(_App):
    def test_inputs_changed_while_running_never_show_the_comparison(self):
        application = self.application()
        self.start(application)
        application.experimental_path.set(str(self.other_unv))  # e.g. a project opened meanwhile
        application._complete(self.comparison_result())
        self.assert_inactive(application, DISCARDED)

    def test_inputs_changed_while_running_never_show_the_diagnostic(self):
        application = self.application()
        self.start(application)
        application.end_mode.set(8)
        experimental = load_unv(self.fitted_path)
        error = ambiguity()
        error.frequency_only_diagnostic = new.frequency_only_diagnostic(self.fe, experimental, "8 orientations")
        error.loaded_modal_data = viewer.LoadedModalData(self.fe, experimental, directory=self.folder / "views",
                                                         registration=viewer.AMBIGUOUS, reason="8 orientations",
                                                         frequency_diagnostic=error.frequency_only_diagnostic)
        application._failed(error)
        self.assert_inactive(application, DISCARDED)

    def test_an_input_changed_and_restored_while_running_keeps_the_result(self):
        application = self.application()
        started_with = application.end_mode.get()
        self.start(application)
        application.end_mode.set(started_with + 3)
        application.end_mode.set(started_with)  # the value the run was started with
        application._complete(self.comparison_result())
        self.assert_active_comparison(application)

    def test_a_cancelled_run_is_not_reported_as_changed_inputs(self):
        application = self.application()
        self.start(application)
        application._analysis_cancel_event.set()
        application._complete(self.comparison_result())
        self.assertIsNone(application.result)
        self.assertEqual(str(application.pdf_button.cget("state")), "disabled")
        application.end_mode.set(8)
        self.assertNotIn(STALE, application.status.get())


class ProjectAndRegistrationTests(_App):
    def test_a_new_project_clears_the_result(self):
        application = self.established(self.application())
        with mock.patch("tkinter.messagebox.askyesno", return_value=True):
            application._new_project()
        self.assertIsNone(application.result)
        self.assertEqual(str(application.pdf_button.cget("state")), "disabled")
        self.assertIsNone(application.mode_viewer.loaded)
        self.assertEqual(application.item_to_pair, {})

    def test_opening_another_project_clears_the_result(self):
        application = self.established(self.application())
        payload = application._project_payload_for_self()
        payload["inputs"]["simcenter_results"] = str(self.other_unv)
        application._apply_project_payload(payload, None)
        self.settle(application)
        self.assert_inactive(application)

    def test_confirming_an_orientation_makes_the_frequency_diagnostic_inactive(self):
        application = self.diagnostic(self.application())
        with mock.patch("tkinter.messagebox.showwarning", side_effect=AssertionError("calibration expected")):
            confirmed = application._confirm_orientation_candidate({"candidate_id": "geometry-3"})
        self.assertTrue(confirmed)
        self.assertIsNone(application._diagnostic_export_source)
        self.assertEqual(str(application.pdf_button.cget("state")), "disabled")
        self.assertIsNone(application.mode_viewer.loaded)
        self.assertIn("Run analysis again", application.status.get())

    def test_clearing_the_guided_registration_makes_its_result_inactive(self):
        from guided_registration_ui import GuidedRegistrationDialog

        application = self.application()
        application._guided_registration = SimpleNamespace(registration=SimpleNamespace(registration_hash="g" * 64))
        application._guided_fe_input_path = self.folder / "model.inp"
        self.established(application)
        dialog = SimpleNamespace(app=application, _invalidate=lambda: 0, _set_status=lambda _text: None)
        GuidedRegistrationDialog.clear(dialog)
        self.assert_inactive(application)


if __name__ == "__main__":
    unittest.main()
