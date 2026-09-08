from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from abaqus_bridge import (
    AbaqusExtractionError,
    AnalysisCancelled,
    cancel_owned_process,
    run_abaqus_extraction,
    stop_owned_process_and_wait,
)


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


class _CancellationAfterLaunch:
    def __init__(self):
        self.calls = 0

    def is_set(self):
        self.calls += 1
        return self.calls > 1


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

    def test_preexisting_cancellation_does_not_launch_abaqus(self):
        process = _OwnedProcess()
        cancellation = threading.Event()
        cancellation.set()
        callbacks = []
        with tempfile.TemporaryDirectory() as directory, patch(
            "abaqus_bridge.subprocess.Popen", return_value=process
        ) as launch:
            with self.assertRaises(AnalysisCancelled):
                run_abaqus_extraction(
                    Path(directory) / "model.odb",
                    Path(directory) / "output",
                    abaqus_command="abaqus",
                    cancel_event=cancellation,
                    process_callback=callbacks.append,
                )
        launch.assert_not_called()
        self.assertEqual(callbacks, [None])

    def test_stop_waits_until_the_owned_process_has_exited(self):
        process = _OwnedProcess()
        with patch(
            "abaqus_bridge.cancel_owned_process", side_effect=lambda _process: process.terminate()
        ) as terminate:
            self.assertTrue(stop_owned_process_and_wait(process))
        terminate.assert_called_once_with(process)
        self.assertEqual(process.returncode, -1)

    def test_confirmed_cancellation_releases_the_process_handle(self):
        process = _OwnedProcess()
        callbacks = []
        with tempfile.TemporaryDirectory() as directory, patch(
            "abaqus_bridge.subprocess.Popen", return_value=process
        ), patch(
            "abaqus_bridge.stop_owned_process_and_wait",
            side_effect=lambda owned: (owned.terminate(), True)[1],
        ):
            with self.assertRaises(AnalysisCancelled):
                run_abaqus_extraction(
                    Path(directory) / "model.odb",
                    Path(directory) / "output",
                    abaqus_command="abaqus",
                    cancel_event=_CancellationAfterLaunch(),
                    process_callback=callbacks.append,
                )
        self.assertEqual(callbacks, [process, None])

    def test_normal_completion_releases_the_process_handle(self):
        process = _OwnedProcess()
        process.returncode = 0
        callbacks = []
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            output.mkdir()
            manifest = output / "manifest.json"
            manifest.write_text("{}", encoding="utf-8")
            with patch("abaqus_bridge.subprocess.Popen", return_value=process):
                actual = run_abaqus_extraction(
                    Path(directory) / "model.odb",
                    output,
                    abaqus_command="abaqus",
                    process_callback=callbacks.append,
                )
        self.assertEqual(actual, manifest)
        self.assertEqual(callbacks, [process, None])

    def test_exited_failure_releases_the_process_handle(self):
        process = _OwnedProcess()
        process.returncode = 2
        callbacks = []
        with tempfile.TemporaryDirectory() as directory, patch(
            "abaqus_bridge.subprocess.Popen", return_value=process
        ):
            with self.assertRaises(AbaqusExtractionError):
                run_abaqus_extraction(
                    Path(directory) / "model.odb",
                    Path(directory) / "output",
                    abaqus_command="abaqus",
                    process_callback=callbacks.append,
                )
        self.assertEqual(callbacks, [process, None])

    def test_timeout_confirms_owned_process_exit_before_reporting_failure(self):
        process = _OwnedProcess()
        callbacks = []
        with tempfile.TemporaryDirectory() as directory, patch(
            "abaqus_bridge.subprocess.Popen", return_value=process
        ), patch(
            "abaqus_bridge.time.monotonic", side_effect=[0.0, 1.0]
        ), patch(
            "abaqus_bridge.stop_owned_process_and_wait",
            side_effect=lambda owned: (owned.terminate(), True)[1],
        ) as stop:
            with self.assertRaisesRegex(AbaqusExtractionError, "exceeded"):
                run_abaqus_extraction(
                    Path(directory) / "model.odb",
                    Path(directory) / "output",
                    abaqus_command="abaqus",
                    timeout_seconds=0,
                    process_callback=callbacks.append,
                )
        stop.assert_called_once_with(process)
        self.assertIs(callbacks[0], process)
        self.assertIsNone(callbacks[-1])

    def test_unconfirmed_stop_retains_the_owned_process_handle(self):
        process = _OwnedProcess()
        cancellation = _CancellationAfterLaunch()
        callbacks = []
        with tempfile.TemporaryDirectory() as directory, patch(
            "abaqus_bridge.subprocess.Popen", return_value=process
        ), patch(
            "abaqus_bridge.stop_owned_process_and_wait", return_value=False
        ):
            with self.assertRaisesRegex(AbaqusExtractionError, "did not stop"):
                run_abaqus_extraction(
                    Path(directory) / "model.odb",
                    Path(directory) / "output",
                    abaqus_command="abaqus",
                    cancel_event=cancellation,
                    process_callback=callbacks.append,
                )
        self.assertEqual(callbacks, [process])


if __name__ == "__main__":
    unittest.main()
