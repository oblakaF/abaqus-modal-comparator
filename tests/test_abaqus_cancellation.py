from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from abaqus_bridge import AnalysisCancelled, cancel_owned_process, run_abaqus_extraction


class _OwnedProcess:
    pid = 43210
    returncode = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = -1

    def wait(self, timeout=None):
        self.returncode = -1
        return self.returncode


class AbaqusCancellationTests(unittest.TestCase):
    def test_windows_termination_is_scoped_to_owned_pid_tree(self):
        process = _OwnedProcess()
        with patch("abaqus_bridge.subprocess.run") as run:
            self.assertTrue(cancel_owned_process(process))
        command = run.call_args.args[0]
        self.assertEqual(command[:2], ["taskkill", "/PID"])
        self.assertEqual(command[2], str(process.pid))
        self.assertIn("/T", command)
        self.assertIn("/F", command)

    def test_extraction_cancellation_keeps_the_process_handle_explicit(self):
        process = _OwnedProcess()
        cancellation = threading.Event()
        cancellation.set()
        callbacks = []
        with tempfile.TemporaryDirectory() as directory, patch(
            "abaqus_bridge.subprocess.Popen", return_value=process
        ), patch("abaqus_bridge.cancel_owned_process", return_value=True) as terminate:
            with self.assertRaises(AnalysisCancelled):
                run_abaqus_extraction(
                    Path(directory) / "model.odb",
                    Path(directory) / "output",
                    abaqus_command="abaqus",
                    cancel_event=cancellation,
                    process_callback=callbacks.append,
                )
        terminate.assert_called_with(process)
        self.assertIs(callbacks[0], process)
        self.assertIsNone(callbacks[-1])


if __name__ == "__main__":
    unittest.main()
