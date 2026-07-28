from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from idle_ui_state import restore_idle_controls


class FakeButton:
    def __init__(self):
        self.state = "disabled"

    def configure(self, **kwargs):
        self.state = kwargs.get("state", self.state)


class FakeProgress:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


class FakeApplication:
    def __init__(self, running=False):
        self.running = running
        self.run_button = FakeButton()
        self.folder_button = FakeButton()
        self.progress = FakeProgress()


class IdleUiStateTests(unittest.TestCase):
    def test_force_restore_enables_startup_controls(self):
        application = FakeApplication(running=True)
        restored = restore_idle_controls(application, force=True)
        self.assertTrue(restored)
        self.assertFalse(application.running)
        self.assertEqual(application.run_button.state, "normal")
        self.assertEqual(application.folder_button.state, "normal")
        self.assertTrue(application.progress.stopped)

    def test_active_worker_is_not_overridden_without_force(self):
        application = FakeApplication(running=True)
        restored = restore_idle_controls(application)
        self.assertFalse(restored)
        self.assertTrue(application.running)
        self.assertEqual(application.run_button.state, "disabled")
        self.assertEqual(application.folder_button.state, "disabled")
        self.assertFalse(application.progress.stopped)


if __name__ == "__main__":
    unittest.main()
