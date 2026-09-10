from __future__ import annotations

from pathlib import Path
from copy import deepcopy
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modal_core import ModalDataset, ModeShape
from polymax_ui import (
    NO_FITTED_SET_TEXT,
    SELECT_MODAL_SET_TEXT,
    experimental_mode_source_label,
    modal_set_choice_text,
    modal_set_summary,
    validate_modal_set_selection,
)
from universal_reader import ExperimentalModalSet


def _set(key: str, name: str, frequencies, residuals: int = 0):
    coordinates = np.array([[0.0, 0.0, 0.0]])
    modes = [
        ModeShape(
            number=index,
            frequency_hz=frequency,
            node_ids=np.array([1], dtype=object),
            coordinates=coordinates,
            vectors=np.array([[0.0, 0.0, 1.0]]),
            metadata={"modal_set_key": key, "modal_set_name": name},
        )
        for index, frequency in enumerate(frequencies, start=1)
    ]
    return ExperimentalModalSet(
        key=key,
        display_name=name,
        processing_name=name,
        modes=modes,
        residual_record_indices=list(range(residuals)),
        residual_labels=[f"residual {index}" for index in range(residuals)],
    )


class PolymaxUiPolicyTests(unittest.TestCase):
    def test_zero_one_and_multiple_set_defaults(self):
        one = _set("only", "Only", [10.0])
        two = _set("second", "Second", [20.0])
        self.assertIsNone(validate_modal_set_selection([], ""))
        self.assertEqual(validate_modal_set_selection([one], ""), "only")
        self.assertEqual(validate_modal_set_selection([one, two], "second"), "second")
        with self.assertRaisesRegex(ValueError, "multiple fitted modal sets"):
            validate_modal_set_selection([one, two], "")

    def test_choice_and_summary_expose_count_source_and_residuals(self):
        modal_set = _set("processing-nice", "Processing_nice", [10.0] * 7, residuals=2)
        self.assertEqual(modal_set_choice_text(modal_set), "Processing_nice — 7 modes")
        summary = modal_set_summary(modal_set)
        self.assertIn("PolyMAX / dataset 55", summary)
        self.assertIn("Physical modes: 7", summary)
        self.assertIn("Residual records excluded: 2", summary)

    def test_result_source_label_includes_modal_set(self):
        self.assertEqual(
            experimental_mode_source_label(
                {"mode_source": "curve-fitted modal dataset", "modal_set_name": "Processing"}
            ),
            "dataset 55 / Processing",
        )
        self.assertEqual(
            experimental_mode_source_label({"mode_source": "FRF peak"}),
            "FRF peak",
        )

    def test_runtime_worker_passes_selected_key_to_universal_loader(self):
        import main
        import runtime_hardening

        mode = ModeShape(
            1,
            10.0,
            np.array([1], dtype=object),
            np.array([[0.0, 0.0, 0.0]]),
            np.array([[0.0, 0.0, 1.0]]),
        )
        abaqus_data = ModalDataset("Abaqus", Path("model.odb"), [mode])

        class Root:
            @staticmethod
            def after(_delay, callback):
                callback()

        application = SimpleNamespace(
            root=Root(),
            _analysis_cancel_event=threading.Event(),
            _owned_analysis_process=None,
            _set_analysis_stage=lambda *_args: None,
            _failed=lambda error: None,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            odb = root / "model.odb"
            unv = root / "scan.unv"
            odb.write_text("fixture", encoding="utf-8")
            unv.write_text("fixture", encoding="utf-8")
            with patch.object(
                main.app, "load_or_extract_odb", return_value=abaqus_data
            ), patch.object(
                runtime_hardening, "_detect_rigid_modes", return_value=([], [mode], 0.0, None)
            ), patch.object(
                runtime_hardening,
                "load_universal_modal_file",
                side_effect=RuntimeError("stop after import call"),
            ) as loader:
                main.app.ModalComparatorApp._worker(
                    application,
                    odb,
                    unv,
                    root / "output",
                    7,
                    15,
                    "abaqus",
                    None,
                    "processing-nice",
                )
        self.assertEqual(loader.call_args.kwargs["modal_set"], "processing-nice")


class PolymaxNativeTkTests(unittest.TestCase):
    def test_discovery_selection_dirty_persistence_and_path_invalidation(self):
        try:
            import tkinter as tk

            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk is unavailable: {error}")
        root.withdraw()
        try:
            import main
            import polymax_ui
            import ui_workflow
            from project_review import read_project, write_project

            disabled = {
                "autosave_enabled": False,
                "restore_on_startup": False,
                "show_recovery_notice": False,
            }
            nice = _set("processing-nice", "Processing_nice", [10.0] * 7, residuals=2)
            full = _set("processing", "Processing", [10.0] * 17, residuals=2)
            only = _set("only", "Only set", [30.0])
            with patch.object(
                ui_workflow, "load_recovery_preferences", return_value=disabled
            ), patch.object(
                ui_workflow, "discover_abaqus_installations", return_value=()
            ), patch.object(
                polymax_ui,
                "discover_experimental_modal_sets",
                side_effect=lambda path: [only] if Path(path).name == "other.unv" else [nice, full],
            ):
                application = main.app.ModalComparatorApp(root)
                with tempfile.TemporaryDirectory() as directory:
                    first = Path(directory) / "first.unv"
                    other = Path(directory) / "other.unv"
                    first.write_text("fixture", encoding="utf-8")
                    other.write_text("fixture", encoding="utf-8")

                    application.experimental_path.set(str(first))
                    self._wait_for_discovery(root, application)
                    self.assertEqual(
                        application.experimental_modal_set_combo.cget("values")[0],
                        SELECT_MODAL_SET_TEXT,
                    )
                    self.assertEqual(application.experimental_modal_set_key.get(), "")
                    with patch("polymax_ui.messagebox.showwarning") as warning:
                        self.assertIsNone(application._validate())
                    self.assertIn("multiple fitted modal sets", warning.call_args.args[1])

                    application.experimental_modal_set_display.set(
                        modal_set_choice_text(nice)
                    )
                    application._experimental_modal_set_selected()
                    self.assertEqual(
                        application.experimental_modal_set_key.get(), "processing-nice"
                    )
                    self.assertIn("Physical modes: 7", application.experimental_modal_set_summary.get())
                    application._reset_dirty()
                    application.experimental_modal_set_display.set(
                        modal_set_choice_text(full)
                    )
                    application._experimental_modal_set_selected()
                    self.assertTrue(application.dirty_tracker.dirty)
                    payload = application._project_payload_for_self()
                    self.assertEqual(
                        payload["inputs"]["experimental_modal_set"], "processing"
                    )
                    project_path = Path(directory) / "saved.amcp.json"
                    write_project(project_path, payload)
                    application._reset_dirty()
                    self.assertFalse(application.dirty_tracker.dirty)

                    application.experimental_path.set(str(other))
                    self._wait_for_discovery(root, application)
                    self.assertEqual(application.experimental_modal_set_key.get(), "only")
                    self.assertEqual(
                        application.experimental_modal_set_display.get(),
                        modal_set_choice_text(only),
                    )

                    application._apply_project_payload(read_project(project_path), project_path)
                    self._wait_for_discovery(root, application)
                    self.assertEqual(
                        application.experimental_modal_set_key.get(), "processing"
                    )
                    self.assertFalse(application.dirty_tracker.dirty)

                    before_stale = [
                        item.key for item in application.available_experimental_modal_sets
                    ]
                    application._apply_discovered_modal_sets(
                        application._modal_set_discovery_generation - 1,
                        first.resolve(),
                        [only],
                        None,
                    )
                    self.assertEqual(
                        [item.key for item in application.available_experimental_modal_sets],
                        before_stale,
                    )

                    missing_payload = deepcopy(payload)
                    missing_payload["inputs"]["experimental_modal_set"] = "removed-set"
                    with patch("polymax_ui.messagebox.showwarning") as warning:
                        application._apply_project_payload(
                            missing_payload, Path(directory) / "missing.amcp.json"
                        )
                        self._wait_for_discovery(root, application)
                    self.assertEqual(application.experimental_modal_set_key.get(), "")
                    self.assertIn("no longer exists", warning.call_args.args[1])

                    no_set = Path(directory) / "none.unv"
                    no_set.write_text("fixture", encoding="utf-8")
                    with patch.object(
                        polymax_ui, "discover_experimental_modal_sets", return_value=[]
                    ):
                        application.experimental_path.set(str(no_set))
                        self._wait_for_discovery(root, application)
                    self.assertEqual(application.experimental_modal_set_key.get(), "")
                    self.assertEqual(
                        application.experimental_modal_set_display.get(),
                        NO_FITTED_SET_TEXT,
                    )
        finally:
            root.destroy()

    @staticmethod
    def _wait_for_discovery(root, application):
        deadline = time.monotonic() + 3.0
        while application._modal_set_discovery_state == "loading":
            root.update()
            if time.monotonic() > deadline:
                raise AssertionError("modal-set discovery did not finish")
            time.sleep(0.01)
        root.update()


if __name__ == "__main__":
    unittest.main()
