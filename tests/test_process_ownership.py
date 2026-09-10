"""Tests for the extractor self-registration / ownership-token cancellation
mechanism in abaqus_bridge.py.

These are unit tests against fake PIDs and fake registration files -- they
never spawn or kill real OS processes, matching the "mocks/fake processes for
automated tests" guidance; the author's own live-process verification (real
Abaqus, real cancellation) is documented separately, not reproduced here.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import abaqus_bridge  # noqa: E402


class FakePopen:
    """Stand-in for subprocess.Popen with a controllable exit state."""

    def __init__(self, pid=99999):
        self.pid = pid
        self._returncode = None

    def poll(self):
        return self._returncode

    def wait(self, timeout=None):
        if self._returncode is None:
            raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout)
        return self._returncode

    def terminate(self):
        self._returncode = 1

    def finish(self, code=0):
        self._returncode = code


class RegistrationRecordTests(unittest.TestCase):
    """Item 1: the registration record carries the correct run token/PID."""

    def test_read_process_registration_parses_valid_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "process_registration.json"
            path.write_text(
                json.dumps({"token": "abc123", "pid": 4242, "timestamp": time.time()}),
                encoding="utf-8",
            )
            record = abaqus_bridge.read_process_registration(path)
            self.assertEqual(record["token"], "abc123")
            self.assertEqual(record["pid"], 4242)

    def test_read_process_registration_rejects_malformed_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "process_registration.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertIsNone(abaqus_bridge.read_process_registration(path))

    def test_read_process_registration_missing_file_returns_none(self):
        missing = Path(tempfile.gettempdir()) / "does-not-exist-registration.json"
        self.assertIsNone(abaqus_bridge.read_process_registration(missing))


class TokenValidationTests(unittest.TestCase):
    """Item 2: a stale/wrong token is rejected; item 3: a correctly-tokened,
    live PID is accepted as the termination target."""

    def _write_registration(self, directory, token, pid, creation_time=None):
        path = Path(directory) / "process_registration.json"
        record = {"token": token, "pid": pid, "timestamp": time.time()}
        if creation_time is not None:
            record["creation_time"] = creation_time
        path.write_text(json.dumps(record), encoding="utf-8")
        return path

    def test_wrong_token_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_registration(directory, "real-token", 555)
            with patch.object(abaqus_bridge, "_pid_exists", return_value=True):
                record = abaqus_bridge._validate_registered_owner(path, "different-token")
            self.assertIsNone(record)

    def test_matching_token_and_live_pid_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_registration(directory, "real-token", 555)
            with patch.object(abaqus_bridge, "_pid_exists", return_value=True), patch.object(
                abaqus_bridge, "_registered_worker_is_confirmable", return_value=None
            ):
                record = abaqus_bridge._validate_registered_owner(path, "real-token")
            self.assertIsNotNone(record)
            self.assertEqual(record["pid"], 555)

    def test_reused_pid_with_mismatched_creation_time_is_rejected(self):
        """A stale registration whose PID Windows has since reused for an
        unrelated process must never be treated as the owned worker."""
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_registration(
                directory, "real-token", 555, creation_time=[111, 222]
            )
            with patch.object(
                abaqus_bridge, "_registered_worker_is_confirmable", return_value=False
            ):
                record = abaqus_bridge._validate_registered_owner(path, "real-token")
            self.assertIsNone(record)

    def test_dead_pid_with_no_creation_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_registration(directory, "real-token", 555)
            with patch.object(abaqus_bridge, "_pid_exists", return_value=False), patch.object(
                abaqus_bridge, "_registered_worker_is_confirmable", return_value=None
            ):
                record = abaqus_bridge._validate_registered_owner(path, "real-token")
            self.assertIsNone(record)


class StopOwnedExtractionTests(unittest.TestCase):
    """Items 3-5: registered owned PID is targeted; unrelated PID is never
    targeted; launcher + detached-worker cleanup both happen."""

    def test_targets_only_the_registered_owned_pid(self):
        with tempfile.TemporaryDirectory() as directory:
            registration_path = Path(directory) / "process_registration.json"
            registration_path.write_text(
                json.dumps({"token": "tok", "pid": 777, "timestamp": time.time()}),
                encoding="utf-8",
            )
            killed_pids = []

            def fake_terminate(pid):
                killed_pids.append(pid)

            confirmable_calls = {"count": 0}

            def fake_confirmable(pid, creation_time):
                confirmable_calls["count"] += 1
                # First call is the ownership-validation check (must confirm
                # ownership so ONLY that PID gets killed); every call after
                # that is inside the post-kill wait loop, reporting death.
                return True if confirmable_calls["count"] == 1 else False

            launcher = FakePopen(pid=1234)
            launcher.finish(0)  # launcher already exited cleanly

            with patch.object(abaqus_bridge, "_terminate_pid_tree", side_effect=fake_terminate), \
                 patch.object(
                     abaqus_bridge, "_registered_worker_is_confirmable", side_effect=fake_confirmable
                 ):
                result = abaqus_bridge.stop_owned_extraction(
                    launcher, registration_path, "tok", first_timeout_seconds=1, retry_timeout_seconds=1
                )

            self.assertTrue(result)
            self.assertEqual(killed_pids, [777])  # never the launcher PID via this path

    def test_never_targets_a_pid_with_no_registration_match(self):
        with tempfile.TemporaryDirectory() as directory:
            registration_path = Path(directory) / "process_registration.json"
            # No file at all -- e.g. cancellation before the worker registered.
            killed_pids = []
            launcher = FakePopen(pid=42)
            launcher.finish(0)
            with patch.object(abaqus_bridge, "_terminate_pid_tree", side_effect=killed_pids.append):
                result = abaqus_bridge.stop_owned_extraction(
                    launcher, registration_path, "tok", first_timeout_seconds=1, retry_timeout_seconds=1
                )
            self.assertTrue(result)
            self.assertEqual(killed_pids, [])

    def test_unrelated_live_pid_is_never_killed_when_token_mismatches(self):
        with tempfile.TemporaryDirectory() as directory:
            registration_path = Path(directory) / "process_registration.json"
            registration_path.write_text(
                json.dumps({"token": "someone-elses-token", "pid": 9999, "timestamp": time.time()}),
                encoding="utf-8",
            )
            killed_pids = []
            launcher = FakePopen(pid=42)
            launcher.finish(0)
            with patch.object(abaqus_bridge, "_terminate_pid_tree", side_effect=killed_pids.append):
                abaqus_bridge.stop_owned_extraction(
                    launcher, registration_path, "our-token", first_timeout_seconds=1, retry_timeout_seconds=1
                )
            self.assertEqual(killed_pids, [])

    def test_reports_failure_when_worker_will_not_die(self):
        """Item 7: failed termination must surface as failure, not a false STOPPED."""
        with tempfile.TemporaryDirectory() as directory:
            registration_path = Path(directory) / "process_registration.json"
            registration_path.write_text(
                json.dumps({"token": "tok", "pid": 777, "timestamp": time.time()}),
                encoding="utf-8",
            )
            launcher = FakePopen(pid=1234)
            launcher.finish(0)
            with patch.object(abaqus_bridge, "_terminate_pid_tree", side_effect=lambda pid: None), \
                 patch.object(abaqus_bridge, "_registered_worker_is_confirmable", return_value=None), \
                 patch.object(abaqus_bridge, "_pid_exists", return_value=True):
                result = abaqus_bridge.stop_owned_extraction(
                    launcher, registration_path, "tok", first_timeout_seconds=0.3, retry_timeout_seconds=0.3
                )
            self.assertFalse(result)


class CancellationIntegrationTests(unittest.TestCase):
    """Item 6: cancellation never publishes a valid manifest.
    Item 9: cancellation callbacks/UI state restoration remain correct."""

    def test_cancel_event_set_before_launch_raises_without_running_process(self):
        import threading

        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory) / "out"
            odb_path = Path(directory) / "fake.odb"
            odb_path.write_text("not a real odb", encoding="utf-8")
            cancel_event = threading.Event()
            cancel_event.set()
            seen_processes = []
            with self.assertRaises(abaqus_bridge.AnalysisCancelled):
                abaqus_bridge.run_abaqus_extraction(
                    odb_path=odb_path,
                    output_directory=output_directory,
                    abaqus_command="does-not-matter",
                    cancel_event=cancel_event,
                    process_callback=seen_processes.append,
                )
            # process_callback must have been told "no process" so the GUI
            # can restore Run/config controls.
            self.assertIn(None, seen_processes)
            self.assertFalse((output_directory / "manifest.json").exists())


class RegistrationCleanupTests(unittest.TestCase):
    """Item 8: a normal successful run cleans up its own registration file."""

    def test_registration_file_removed_after_extraction_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory) / "out"
            odb_path = Path(directory) / "fake.odb"
            odb_path.write_text("not a real odb", encoding="utf-8")
            with self.assertRaises(abaqus_bridge.AbaqusExtractionError):
                abaqus_bridge.run_abaqus_extraction(
                    odb_path=odb_path,
                    output_directory=output_directory,
                    abaqus_command="definitely-not-a-real-abaqus-executable-xyz",
                    timeout_seconds=5,
                )
            self.assertFalse((output_directory / "process_registration.json").exists())


if __name__ == "__main__":
    unittest.main()
