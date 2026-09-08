from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ui_policy import (
    AnalysisState,
    CloseDecision,
    COMPARISON_COLUMNS,
    DirtyTracker,
    LayoutMode,
    REVIEW_COLUMNS,
    button_grid_columns,
    close_decision,
    completion_state,
    coordinate_scale_from_units,
    discover_abaqus_installations,
    metric_grid_columns,
    logical_window_width,
    non_empty_headings,
    normalize_recovery_preferences,
    resolve_command,
    select_abaqus_installation,
    select_layout_mode,
    status_text,
    tab_labels_for,
    table_width_policy,
    text_wrap_width,
    transition_analysis_state,
    validate_custom_scale,
)
from ui_workflow import dispatch_clipboard_action


class ResponsivePolicyTests(unittest.TestCase):
    def test_breakpoint_selection_covers_target_window_classes(self):
        self.assertIs(select_layout_mode(1920), LayoutMode.WIDE)
        self.assertIs(select_layout_mode(1600), LayoutMode.WIDE)
        self.assertIs(select_layout_mode(1366), LayoutMode.MEDIUM)
        self.assertIs(select_layout_mode(1280), LayoutMode.MEDIUM)
        self.assertIs(select_layout_mode(1024), LayoutMode.COMPACT)

    def test_dpi_scaled_pixels_are_normalized_to_logical_width(self):
        self.assertEqual(logical_window_width(1024, 96 / 72), 1024)
        self.assertEqual(logical_window_width(1280, (96 / 72) * 1.25), 1024)
        self.assertEqual(logical_window_width(1536, (96 / 72) * 1.5), 1024)

    def test_metric_cards_and_buttons_wrap_deterministically(self):
        self.assertEqual(metric_grid_columns(LayoutMode.WIDE, 1920), 4)
        self.assertEqual(metric_grid_columns(LayoutMode.MEDIUM, 1280), 2)
        self.assertEqual(metric_grid_columns(LayoutMode.COMPACT, 1024), 2)
        self.assertEqual(metric_grid_columns(LayoutMode.COMPACT, 640), 1)
        self.assertEqual(button_grid_columns(LayoutMode.WIDE, 6), 6)
        self.assertEqual(button_grid_columns(LayoutMode.MEDIUM, 6), 3)
        self.assertEqual(button_grid_columns(LayoutMode.COMPACT, 6), 2)

    def test_compact_tab_labels_keep_all_nine_tabs(self):
        labels = tab_labels_for(LayoutMode.COMPACT)
        self.assertEqual(len(labels), 9)
        self.assertEqual(labels[0], "1. Files")
        self.assertEqual(labels[-1], "9. Details")

    def test_dynamic_wrap_width_is_bounded_and_increases(self):
        compact = text_wrap_width(1024)
        wide = text_wrap_width(1920)
        self.assertGreater(wide, compact)
        self.assertGreaterEqual(compact, 280)
        self.assertLessEqual(wide, 1320)

    def test_table_policy_keeps_scientific_minimums_and_headings(self):
        policy = table_width_policy("comparison")
        self.assertEqual(policy, COMPARISON_COLUMNS)
        self.assertTrue(all(item.minimum > 0 for item in policy))
        self.assertTrue(all(item.width >= item.minimum for item in policy))
        headings = {item.key: item.heading for item in policy}
        self.assertTrue(non_empty_headings(tuple(headings), headings))
        self.assertTrue(all(item.heading.strip() for item in REVIEW_COLUMNS))
        self.assertEqual(headings["af"], "Abaqus frequency, Hz")
        self.assertEqual(headings["comment"], "Comment")


class CoordinateUnitTests(unittest.TestCase):
    def test_named_units_convert_abaqus_coordinates_to_experimental_units(self):
        self.assertAlmostEqual(coordinate_scale_from_units("mm", "m"), 0.001)
        self.assertAlmostEqual(coordinate_scale_from_units("m", "mm"), 1000.0)
        self.assertAlmostEqual(coordinate_scale_from_units("cm", "mm"), 10.0)

    def test_custom_scale_validation_is_user_friendly(self):
        self.assertAlmostEqual(validate_custom_scale("0,001"), 0.001)
        for value in ("", "auto", "0", "-2"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "positive custom"):
                validate_custom_scale(value)


class AbaqusSelectionTests(unittest.TestCase):
    def test_discovery_returns_only_launchers_that_exist(self):
        with tempfile.TemporaryDirectory() as directory:
            launcher = Path(directory) / "abq2024.bat"
            launcher.write_text("@echo off\n", encoding="utf-8")
            installations = discover_abaqus_installations(
                path="", search_directories=(Path(directory),)
            )
        self.assertEqual(len(installations), 1)
        self.assertIn("2024", installations[0].label)
        self.assertEqual(select_abaqus_installation(installations), installations[0])

    def test_multiple_installations_require_an_explicit_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "abq2023.bat"
            second = Path(directory) / "abq2024.bat"
            first.write_text("", encoding="utf-8")
            second.write_text("", encoding="utf-8")
            installations = discover_abaqus_installations(
                path="", search_directories=(Path(directory),)
            )
        self.assertEqual(len(installations), 2)
        self.assertIsNone(select_abaqus_installation(installations))

    def test_same_version_launchers_keep_unique_selection_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            first_dir = Path(directory) / "one"
            second_dir = Path(directory) / "two"
            first_dir.mkdir()
            second_dir.mkdir()
            (first_dir / "abq2024.bat").write_text("", encoding="utf-8")
            (second_dir / "abq2024.bat").write_text("", encoding="utf-8")
            installations = discover_abaqus_installations(
                path="", search_directories=(first_dir, second_dir)
            )
        self.assertEqual(len(installations), 2)
        self.assertEqual(len({item.label for item in installations}), 2)

    def test_explicit_launcher_path_must_be_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "not-a-launcher.txt"
            invalid.write_text("not executable", encoding="utf-8")
            self.assertIsNone(resolve_command(str(invalid)))


class AnalysisAndProjectStateTests(unittest.TestCase):
    def test_run_stop_state_machine(self):
        state = transition_analysis_state(AnalysisState.READY, "run")
        self.assertIs(state, AnalysisState.RUNNING)
        state = transition_analysis_state(state, "stop")
        self.assertIs(state, AnalysisState.STOPPING)
        state = transition_analysis_state(state, "stopped")
        self.assertIs(state, AnalysisState.STOPPED)
        self.assertEqual(status_text(state), "Analysis stopped by user.")

    def test_diagnostic_completion_is_not_an_error(self):
        state = transition_analysis_state(AnalysisState.RUNNING, "diagnostic")
        self.assertIs(state, AnalysisState.DIAGNOSTIC)
        self.assertIn("0 admissible pairs", status_text(state))
        self.assertIn("gates were not satisfied", status_text(state))

    def test_completion_uses_automatic_acceptance_not_manual_effective_pairs(self):
        self.assertIs(completion_state(0), AnalysisState.DIAGNOSTIC)
        self.assertIs(completion_state(1), AnalysisState.SUCCESS)

    def test_dirty_tracker_resets_only_to_an_explicit_baseline(self):
        tracker = DirtyTracker()
        tracker.reset({"path": "a.odb", "mode": 6})
        self.assertFalse(tracker.dirty)
        self.assertTrue(tracker.update({"path": "b.odb", "mode": 6}))
        tracker.reset({"path": "b.odb", "mode": 6})
        self.assertFalse(tracker.dirty)

    def test_close_decisions_keep_running_and_dirty_choices_separate(self):
        self.assertIs(
            close_decision(running=True, dirty=True, running_choice="keep"),
            CloseDecision.KEEP_RUNNING,
        )
        self.assertIs(
            close_decision(running=True, dirty=True, running_choice="stop"),
            CloseDecision.STOP_AND_CLOSE,
        )
        self.assertIs(
            close_decision(running=False, dirty=True, save_choice="save"),
            CloseDecision.SAVE,
        )
        self.assertIs(
            close_decision(running=False, dirty=False), CloseDecision.CLOSE
        )

    def test_recovery_preferences_are_independent(self):
        value = normalize_recovery_preferences(
            {"autosave_enabled": False, "restore_on_startup": True, "show_recovery_notice": False}
        )
        self.assertFalse(value["autosave_enabled"])
        self.assertTrue(value["restore_on_startup"])
        self.assertFalse(value["show_recovery_notice"])


class _FakeEntry:
    def __init__(self, value="alpha beta", state="normal"):
        self.value = value
        self.state = state
        self.selection = (0, 0)
        self.insert_index = len(value)
        self.clipboard = ""

    def winfo_class(self):
        return "TEntry"

    def cget(self, key):
        return self.state

    def get(self):
        return self.value

    def selection_present(self):
        return self.selection[0] != self.selection[1]

    def index(self, index):
        if index == "sel.first":
            return self.selection[0]
        if index == "sel.last":
            return self.selection[1]
        return self.insert_index

    def selection_range(self, first, last):
        self.selection = (int(first), len(self.value) if last == "end" else int(last))

    def icursor(self, index):
        self.insert_index = len(self.value) if index == "end" else int(index)

    def clipboard_clear(self):
        self.clipboard = ""

    def clipboard_append(self, value):
        self.clipboard += value

    def clipboard_get(self):
        return self.clipboard

    def delete(self, first, last):
        start = self.index(first) if isinstance(first, str) else int(first)
        end = self.index(last) if isinstance(last, str) else int(last)
        self.value = self.value[:start] + self.value[end:]
        self.insert_index = start
        self.selection = (start, start)

    def insert(self, index, value):
        position = self.index(index) if isinstance(index, str) else int(index)
        self.value = self.value[:position] + value + self.value[position:]


class ClipboardDispatchTests(unittest.TestCase):
    def test_copy_cut_paste_and_select_all(self):
        entry = _FakeEntry()
        self.assertTrue(dispatch_clipboard_action(entry, "select_all"))
        self.assertTrue(dispatch_clipboard_action(entry, "copy"))
        self.assertEqual(entry.clipboard, "alpha beta")
        entry.selection = (0, 5)
        self.assertTrue(dispatch_clipboard_action(entry, "cut"))
        self.assertEqual(entry.value, " beta")
        entry.clipboard = "path"
        entry.insert_index = 0
        self.assertTrue(dispatch_clipboard_action(entry, "paste"))
        self.assertEqual(entry.value, "path beta")

    def test_read_only_text_can_copy_but_not_cut(self):
        entry = _FakeEntry(state="readonly")
        entry.selection = (0, 5)
        self.assertTrue(dispatch_clipboard_action(entry, "copy"))
        self.assertFalse(dispatch_clipboard_action(entry, "cut"))
        self.assertEqual(entry.value, "alpha beta")


class TkRuntimeSmokeTests(unittest.TestCase):
    def test_runtime_builds_nine_resizable_tabs_with_complete_headings(self):
        try:
            import tkinter as tk
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk is unavailable: {error}")
        root.withdraw()
        try:
            import main
            import ui_workflow

            disabled = {
                "autosave_enabled": False,
                "restore_on_startup": False,
                "show_recovery_notice": False,
            }
            with patch.object(ui_workflow, "load_recovery_preferences", return_value=disabled), patch.object(
                ui_workflow, "discover_abaqus_installations", return_value=()
            ):
                application = main.app.ModalComparatorApp(root)
            root.geometry("1024x700")
            root.update_idletasks()
            application._apply_responsive_layout()
            self.assertEqual(len(application.tabs.tabs()), 9)
            self.assertEqual(application._layout_mode, LayoutMode.COMPACT)
            self.assertEqual(
                tuple(application.tabs.tab(tab, "text") for tab in application.tabs.tabs()),
                tab_labels_for(LayoutMode.COMPACT),
            )
            for table in (application.table, application.review_table):
                headings = {column: table.heading(column, "text") for column in table["columns"]}
                self.assertTrue(non_empty_headings(table["columns"], headings))
                self.assertIsNotNone(getattr(table, "_horizontal_scrollbar", None))

            for width, height in (
                (1920, 1080),
                (1600, 900),
                (1366, 768),
                (1280, 720),
                (1024, 700),
                (1366, 768),
            ):
                root.geometry(f"{width}x{height}")
                root.update_idletasks()
                application._apply_responsive_layout()
                logical = logical_window_width(
                    root.winfo_width(), float(root.tk.call("tk", "scaling"))
                )
                self.assertEqual(application._layout_mode, select_layout_mode(logical))
                for tab in application.tabs.tabs():
                    application.tabs.select(tab)
                    root.update_idletasks()

            application.abaqus_path_entry.delete(0, "end")
            application.abaqus_path_entry.insert(0, "C:/very/long/model/path/panel.odb")
            dispatch_clipboard_action(application.abaqus_path_entry, "select_all")
            self.assertTrue(dispatch_clipboard_action(application.abaqus_path_entry, "copy"))
            self.assertTrue(application.dirty_tracker.dirty)
            application._reset_dirty()
            self.assertFalse(application.dirty_tracker.dirty)
            application.coordinate_mapping_mode.set("custom")
            application.custom_coordinate_scale.set("0.001")
            application._sync_coordinate_mapping()
            self.assertEqual(application.computed_coordinate_scale.get(), "0.001")

            from modal_core import (
                ComparisonResult,
                GeometryMatch,
                ModalDataset,
                ModePairResult,
                ModeShape,
            )

            coordinates = np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
            vectors = np.asarray([[0.0, 0.0, 1.0], [0.0, 0.0, -1.0]], dtype=complex)
            mode = ModeShape(1, 10.0, np.asarray([1, 2], dtype=object), coordinates, vectors)
            abaqus = ModalDataset("Abaqus", Path("a.odb"), [mode])
            experiment = ModalDataset("Experiment", Path("e.unv"), [mode])
            geometry = GeometryMatch(
                experimental_to_abaqus=np.asarray([0, 1]),
                distances=np.zeros(2),
                transformed_abaqus_coordinates=coordinates,
                rotation=np.eye(3),
                coordinate_scale=1.0,
                translation=np.zeros(3),
                normalized_rms_distance=0.0,
                matched_fraction=1.0,
            )
            result = ComparisonResult(
                abaqus=abaqus,
                experimental=experiment,
                geometry=geometry,
                pairs=[],
                mac_matrix=np.zeros((1, 1)),
                frequency_error_matrix=np.zeros((1, 1)),
                abaqus_mode_numbers=[1],
                experimental_mode_numbers=[1],
                diagnostic_state="no_admissible_pairs",
            )
            with patch("project_review._all_elastic_abaqus_modes", return_value=[]):
                application._populate(result)
            self.assertEqual(application.metric_pairs.cget("text"), "0")
            self.assertIn("Diagnostic", application.metric_geometry.cget("text"))
            self.assertTrue(application.table.get_children())

            manual_pair = ModePairResult(
                abaqus_mode=1,
                experimental_mode=1,
                abaqus_frequency_hz=10.0,
                experimental_frequency_hz=10.0,
                frequency_error_percent=0.0,
                mac=1.0,
                status="manual acceptance",
                order_changed=False,
                mapped_points=2,
                abaqus_vector=vectors,
                experimental_vector=vectors,
                coordinates=coordinates,
            )
            manual_pair.manual_decision = "accepted"
            result.pairs = [manual_pair]
            application._automatic_admissible_pair_count = 0
            with patch("project_review._all_elastic_abaqus_modes", return_value=[]):
                application._populate(result)
            self.assertEqual(application.metric_pairs.cget("text"), "1 manual")
            self.assertIn("manual review only", application.metric_geometry.cget("text"))
            self.assertEqual(result.pairs, [manual_pair])

            posted = []
            self.assertTrue(application._post_to_ui(lambda: posted.append("done")))
            root.update()
            self.assertEqual(posted, ["done"])
            application._ui_closing = True
            self.assertFalse(application._post_to_ui(lambda: posted.append("late")))
            self.assertEqual(posted, ["done"])
            application._ui_closing = False

            application.details.configure(state="normal")
            application.details.insert("end", "\nclipboard smoke")
            application.details.configure(state="disabled")
            self.assertTrue(dispatch_clipboard_action(application.details, "select_all"))
            self.assertTrue(dispatch_clipboard_action(application.details, "copy"))

            close_calls = []
            real_finish_close = application._finish_close
            application._finish_close = lambda: close_calls.append("closed")
            application._close_after_cancel = True
            application.running = True
            application._owned_analysis_process = None
            with patch("tkinter.messagebox.showerror"), patch("tkinter.messagebox.showwarning"):
                application._failed(RuntimeError("queued failure"))
            self.assertEqual(close_calls, ["closed"])

            class _StillRunning:
                def poll(self):
                    return None

            close_calls.clear()
            application._close_after_cancel = True
            application.running = True
            application._owned_analysis_process = _StillRunning()
            with patch("tkinter.messagebox.showerror"), patch(
                "tkinter.messagebox.showwarning"
            ) as warning:
                application._failed(RuntimeError("termination not confirmed"))
            self.assertEqual(close_calls, [])
            warning.assert_called_once()
            application._finish_close = real_finish_close
            application._owned_analysis_process = None
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
