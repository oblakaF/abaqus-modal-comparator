from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from coordinate_calibration import CAMERA_GRID, CoordinateCalibration, scale_candidates
from project_review import project_payload
from ui_policy import (
    UI_SCALE_PERCENT_VALUES,
    SettledCallback,
    minimum_window_size,
    normalize_recovery_preferences,
    normalize_ui_scale_percent,
    responsive_layout_width,
)
from ui_workflow import load_recovery_preferences, save_recovery_preferences


class FakeScheduler:
    def __init__(self):
        self.next_job = 0
        self.callbacks = {}
        self.cancelled = []

    def after(self, _delay, callback):
        self.next_job += 1
        self.callbacks[self.next_job] = callback
        return self.next_job

    def after_cancel(self, job):
        self.cancelled.append(job)
        self.callbacks.pop(job, None)

    def run_pending(self):
        callbacks = list(self.callbacks.values())
        self.callbacks.clear()
        for callback in callbacks:
            callback()


class ResizeCoalescingTests(unittest.TestCase):
    def test_resize_burst_has_one_settled_callback_and_no_stale_jobs(self):
        scheduler = FakeScheduler()
        executions = []
        settled = SettledCallback(scheduler, 210, lambda: executions.append("settled"))

        for _ in range(25):
            settled.schedule()

        self.assertEqual(settled.scheduled_count, 25)
        self.assertEqual(settled.cancelled_count, 24)
        self.assertEqual(len(scheduler.callbacks), 1)
        scheduler.run_pending()
        self.assertEqual(executions, ["settled"])
        self.assertIsNone(settled.job)

    def test_cancel_removes_the_only_pending_settled_callback(self):
        scheduler = FakeScheduler()
        settled = SettledCallback(scheduler, 210, self.fail)
        settled.schedule()
        settled.cancel()
        scheduler.run_pending()
        self.assertEqual(settled.executed_count, 0)


class InterfaceScaleTests(unittest.TestCase):
    def test_allowed_values_and_default(self):
        self.assertEqual(UI_SCALE_PERCENT_VALUES, (80, 90, 100, 110, 125))
        self.assertEqual(normalize_ui_scale_percent(None), 100)
        self.assertEqual(normalize_ui_scale_percent(150), 100)
        self.assertEqual(normalize_ui_scale_percent("125"), 125)

    def test_preference_round_trip_is_separate_from_project(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ui_preferences.json"
            save_recovery_preferences(
                {
                    "autosave_enabled": True,
                    "restore_on_startup": False,
                    "show_recovery_notice": True,
                    "ui_scale_percent": 90,
                },
                path,
            )
            loaded = load_recovery_preferences(path)
        self.assertEqual(loaded["ui_scale_percent"], 90)

        project = project_payload(
            abaqus_path="a.odb",
            experimental_path="e.unv",
            workspace_path="out",
            abaqus_command="abaqus",
            start_mode=1,
            end_mode=2,
            coordinate_scale="1",
            manual_reviews={},
        )
        self.assertNotIn("ui_scale", json.dumps(project).lower())

    def test_absent_preference_defaults_to_100(self):
        preferences = normalize_recovery_preferences({"autosave_enabled": False})
        self.assertEqual(preferences["ui_scale_percent"], 100)

    def test_presentation_scale_cannot_change_camera_calibration(self):
        calibration = CoordinateCalibration(
            mode=CAMERA_GRID,
            abaqus_unit="mm",
            scan_coverage="full",
            physical_width=500.0,
            physical_height=500.0,
            dimension_unit="mm",
        )
        coordinates = np.array([[0.0, 0.0, -1.0], [0.332937, 0.328658, -1.0]])
        before = scale_candidates(calibration, coordinates)[0][0].copy()
        for percent in UI_SCALE_PERCENT_VALUES:
            normalize_ui_scale_percent(percent)
        after = scale_candidates(calibration, coordinates)[0][0]
        np.testing.assert_array_equal(before, after)

    def test_window_resize_policy_is_separate_from_interface_scale(self):
        selected = 80
        width_at_80 = responsive_layout_width(1600, 96 / 72, selected)
        width_at_125 = responsive_layout_width(1600, 96 / 72, 125)
        self.assertGreater(width_at_80, width_at_125)
        self.assertEqual(selected, 80)
        self.assertEqual(minimum_window_size(), (1120, 700))


if __name__ == "__main__":
    unittest.main()
