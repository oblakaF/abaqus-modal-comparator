"""APP-UI.2-O1: why the window stops repainting at "6/6 Report data generation" (real main window, synthetic data).

Measured on the SHA-verified SP-02 copies (extracted manifest + UNV, Bravo (1); docs/gui/APP_UI2_PROGRESS.md):

- the worker's stage 6 takes milliseconds;
- the completion then runs on the GUI thread for 28.8 s, and the root.after heartbeat stops for 28.9 s;
- 24.2 s of it is the rigid-body classification of the FE modes. ``project_review.refresh_review_table`` calls
  ``_all_elastic_abaqus_modes`` -> ``quality_control._detect_rigid_modes`` (an ``lstsq`` per mode on the full FE
  mesh), twice per completion.

The fix needs ``project_review.py`` / ``project_review_polish.py``, outside the files authorised for APP-UI.2-O1, so it
is not made here. These tests pin the cause:

- the characterisation test passes now;
- the reproducing test is an expected failure until the classification leaves the GUI thread.
"""

from __future__ import annotations

from pathlib import Path
import sys
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from test_app_p1_stale_results import _App  # noqa: E402


class CompletionThreadTests(_App):
    def classifications_during_completion(self):
        """(thread name of every rigid-mode classification while the GUI thread completes an analysis, the result)."""
        import project_review

        application = self.application()
        calls = []
        original = project_review._detect_rigid_modes

        def recorded(dataset):
            calls.append(threading.current_thread().name)
            return original(dataset)

        with mock.patch.object(project_review, "_detect_rigid_modes", side_effect=recorded):
            self.established(application)  # the real Run, then the real completion handlers on the GUI thread
        return calls, application

    def test_the_completion_classifies_the_fe_modes_on_the_gui_thread(self):
        """Characterisation of O-1 (passes now): the review table classifies the rigid modes on the GUI thread, twice."""
        calls, application = self.classifications_during_completion()
        self.assertEqual(calls, ["MainThread", "MainThread"])
        self.assert_active_comparison(application)

    @unittest.expectedFailure
    def test_the_gui_thread_completion_does_no_rigid_mode_classification(self):
        """Reproducer of the proposed fix (expected failure now): the classification is done once, off the GUI thread
        (e.g. at stage 6 on the worker), and the completion only reads it."""
        calls, _application = self.classifications_during_completion()
        self.assertNotIn("MainThread", calls)


if __name__ == "__main__":
    unittest.main()
