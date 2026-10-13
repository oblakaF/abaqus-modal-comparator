"""Quick calibration P1a: Stop, owned-process termination, timeouts and window closing (no Abaqus).

A dummy "Abaqus" (a Python script that starts a child process and waits) stands in for the solver and the ODB
extraction; termination failures use mocked processes. A stop is reported only after every owned process is
confirmed gone; nothing is left as a completed or reusable job.
"""

from __future__ import annotations

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import quick_calibration_support as S  # noqa: E402
from services import owned_processes  # noqa: E402
from services.quick_calibration import (  # noqa: E402
    AbaqusRunner,
    CalibrationCancelled,
    QuickCalibration,
    QuickCalibrationError,
    TerminationUnconfirmed,
    _save_state,
    config_from_dict,
)

FAKE_ABAQUS = r'''
import json, os, subprocess, sys, time
from pathlib import Path
args = sys.argv[1:]
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
with open(os.environ["FAKE_ABAQUS_PIDS"], "a") as log:
    log.write(f"{os.getpid()} {child.pid}\n")
if "--registration-file" in args:  # the ODB extraction registers its worker like extract_odb.py
    Path(args[args.index("--registration-file") + 1]).write_text(json.dumps(
        {"token": args[args.index("--owner-token") + 1], "pid": os.getpid()}))
time.sleep(300)
'''


def alive(pid: int) -> bool:
    if owned_processes.creation_time(pid) is not None:
        return True
    return os.name == "nt" and pid in owned_processes.process_table()


class _Dummy(unittest.TestCase):
    """A dummy Abaqus command; every PID it starts is recorded and killed at the end, whatever happens."""

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="qc_p1a_"))
        self.pids_file = self.folder / "pids.txt"
        script = self.folder / "fake_abaqus.py"
        script.write_text(FAKE_ABAQUS, encoding="utf-8")
        if os.name == "nt":
            wrapper = self.folder / "fake_abaqus.cmd"
            wrapper.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="ascii")
            self.command = str(wrapper)
        else:
            self.command = f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"
        patcher = mock.patch.dict(os.environ, {"FAKE_ABAQUS_PIDS": str(self.pids_file)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._kill_leftovers)
        self.addCleanup(shutil.rmtree, self.folder, True)

    def pids(self) -> list[int]:
        try:
            return [int(value) for value in self.pids_file.read_text().split()]
        except (OSError, ValueError):
            return []

    def _kill_leftovers(self) -> None:
        for pid in self.pids():
            if alive(pid):
                owned_processes.kill_process(pid)

    def wait_for_dummy(self, count: int = 2, settle: float = 1.5) -> None:
        deadline = time.monotonic() + 30
        while len(self.pids()) < count and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertGreaterEqual(len(self.pids()), count, "the dummy Abaqus did not start")
        time.sleep(settle)  # at least two process-table snapshots of the running tree

    def in_thread(self, target):
        outcome = {}

        def run():
            try:
                outcome["value"] = target()
            except BaseException as error:  # noqa: BLE001 - inspected by the test
                outcome["error"] = error

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread, outcome

    def assert_all_gone(self) -> None:
        self.assertTrue(self.pids())
        self.assertEqual([pid for pid in self.pids() if alive(pid)], [])


# ----------------------------------------------------------------------------- dummy subprocesses

class SolveStopTests(_Dummy):
    def runner(self, cancel=None) -> AbaqusRunner:
        return AbaqusRunner(self.command, 1, 120.0, cancel or threading.Event())

    def test_stop_during_the_model_solve(self):
        cancel = threading.Event()
        job = self.folder / "job"
        job.mkdir()
        (job / "qc_x.inp").write_text("*Heading\n")
        thread, outcome = self.in_thread(lambda: self.runner(cancel).solve(job / "qc_x.inp", job, "qc_x"))
        self.wait_for_dummy()
        self.assertTrue(all(alive(pid) for pid in self.pids()))
        cancel.set()
        thread.join(90)
        self.assertFalse(thread.is_alive())
        self.assertIsInstance(outcome.get("error"), CalibrationCancelled)
        self.assertIn("terminated (confirmed)", str(outcome["error"]))
        self.assert_all_gone()  # launcher and its child, confirmed before the report

    def test_solve_timeout_terminates_and_confirms(self):
        runner = self.runner()
        runner.timeout_seconds = 2
        job = self.folder / "job"
        job.mkdir()
        (job / "qc_t.inp").write_text("*Heading\n")
        with self.assertRaises(QuickCalibrationError) as caught:
            runner.solve(job / "qc_t.inp", job, "qc_t")
        self.assertNotIsInstance(caught.exception, (CalibrationCancelled, TerminationUnconfirmed))
        self.assertIn("terminated (confirmed)", str(caught.exception))
        self.assert_all_gone()


class ExtractionStopTests(_Dummy):
    def test_stop_during_the_odb_extraction(self):
        cancel = threading.Event()
        runner = AbaqusRunner(self.command, 1, 120.0, cancel)
        odb = self.folder / "job.odb"
        odb.write_text("odb")
        out = self.folder / "extraction"
        thread, outcome = self.in_thread(lambda: runner.extract(odb, out, 10))
        self.wait_for_dummy()
        cancel.set()
        thread.join(90)
        self.assertFalse(thread.is_alive())
        self.assertIsInstance(outcome.get("error"), CalibrationCancelled)
        self.assert_all_gone()
        self.assertFalse((out / "manifest.json").exists())
        self.assertFalse((out / "process_registration.json").exists())

    def test_unconfirmed_extraction_stop_is_never_reported_as_stopped(self):
        import abaqus_bridge

        cancel = threading.Event()
        runner = AbaqusRunner(self.command, 1, 120.0, cancel)
        odb = self.folder / "job.odb"
        odb.write_text("odb")
        with mock.patch.object(abaqus_bridge, "stop_owned_extraction", return_value=False):
            thread, outcome = self.in_thread(lambda: runner.extract(odb, self.folder / "x", 10))
            self.wait_for_dummy(settle=0.5)
            cancel.set()
            thread.join(90)
        error = outcome.get("error")
        self.assertIsInstance(error, TerminationUnconfirmed)
        self.assertNotIsInstance(error, CalibrationCancelled)
        self.assertIn("could not be confirmed", str(error))
        self._kill_leftovers()  # the test itself cleans up what the mocked stop left running
        deadline = time.monotonic() + 30
        while any(alive(pid) for pid in self.pids()) and time.monotonic() < deadline:
            time.sleep(0.2)
        self.assert_all_gone()


# ----------------------------------------------------------------------------- mocked processes (no process at all)

class NeverEnding:
    """A mocked launcher that never exits by itself."""

    pid = 424242

    def __init__(self, *args, **kwargs) -> None:
        self.killed = False

    def wait(self, timeout=None):
        raise subprocess.TimeoutExpired("abaqus", timeout)

    def poll(self):
        return None


class StuckTree:
    """An owned tree whose termination can never be confirmed."""

    def __init__(self, process) -> None:
        self.process = process
        self.terminate_calls = 0
        self.gone = False  # set by a test: the processes ended on their own later

    def refresh(self) -> None:
        pass

    def alive(self):
        return [] if self.gone else [owned_processes.ProcessIdentity(self.process.pid, None)]

    def terminate(self, timeout_seconds: float = 0.0) -> bool:
        self.terminate_calls += 1
        return False

    def describe(self, identities=None) -> str:
        return f"PID {self.process.pid}"


class TerminationFailureTests(unittest.TestCase):
    def runner(self, cancel) -> AbaqusRunner:
        runner = AbaqusRunner("abaqus", 1, 120.0, cancel, popen=NeverEnding, tree_factory=StuckTree)
        runner.POLL_SECONDS = 0.01
        return runner

    def solve(self, runner):
        folder = Path(tempfile.mkdtemp(prefix="qc_p1a_mock_"))
        self.addCleanup(shutil.rmtree, folder, True)
        return runner.solve(folder / "j.inp", folder, "j")

    def test_stop_with_unconfirmed_termination(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(CalibrationCancelled):  # set before the solve: nothing is started
            self.solve(self.runner(cancel))
        cancel = threading.Event()
        runner = self.runner(cancel)
        timer = threading.Timer(0.1, cancel.set)
        timer.start()
        with self.assertRaises(TerminationUnconfirmed) as caught:
            self.solve(runner)
        self.assertIn("could not be confirmed", str(caught.exception))
        self.assertIn("PID 424242", str(caught.exception))
        self.assertEqual(len(caught.exception.still_running()), 1)

    def test_timeout_with_unconfirmed_termination(self):
        runner = self.runner(threading.Event())
        runner.timeout_seconds = 0
        with self.assertRaises(TerminationUnconfirmed) as caught:
            self.solve(runner)
        self.assertNotIn("terminated (confirmed)", str(caught.exception))

    def test_ctrl_c_terminates_the_owned_solve(self):
        trees = []

        class Interrupted(NeverEnding):
            def wait(self, timeout=None):
                raise KeyboardInterrupt

        runner = AbaqusRunner("abaqus", 1, 120.0, threading.Event(), popen=Interrupted,
                              tree_factory=lambda process: trees.append(StuckTree(process)) or trees[-1])
        with self.assertRaises(KeyboardInterrupt):
            self.solve(runner)
        self.assertEqual(trees[0].terminate_calls, 1)

    def test_tree_reports_confirmation_only_when_nothing_remains(self):
        process = mock.Mock(pid=10, **{"poll.return_value": None})
        table = {10: 1, 11: 10, 12: 11, 99: 1}
        created = {10: (5,), 11: (6,), 12: (7,), 99: (1,)}
        killed = []

        def kill(pid):
            killed.append(pid)
            created.pop(pid, None)
            table.pop(pid, None)
            if pid == 10:
                process.poll.return_value = -9

        tree = owned_processes.OwnedProcessTree(process, table=lambda: dict(table), created=created.get, kill=kill)
        tree.refresh()
        self.assertEqual(set(tree.members), {10, 11, 12})  # 99 is not ours
        self.assertTrue(tree.terminate(timeout_seconds=2, poll_seconds=0.01))
        self.assertEqual(sorted(killed), [10, 11, 12])
        reused = owned_processes.OwnedProcessTree(process, table=lambda: {10: 1, 13: 10},
                                                  created={10: (5,), 13: (2,)}.get, kill=lambda pid: None)
        reused.refresh()
        self.assertNotIn(13, reused.members)  # created before its "parent": a reused PID, never killed
        stuck = owned_processes.OwnedProcessTree(mock.Mock(pid=20, **{"poll.return_value": None}),
                                                 table=lambda: {20: 1}, created={20: (1,)}.get, kill=lambda pid: None)
        self.assertFalse(stuck.terminate(timeout_seconds=0.1, poll_seconds=0.01))


# ----------------------------------------------------------------------------- the workflow leaves no partial cache

class CacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="qc_p1a_cache_"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        (self.folder / "model.inp").write_text(S.INP)
        S.write_experiment(self.folder / "exp.unv", 0.9 * S.E0, S.G0)
        self.config = config_from_dict({"model_inp": "model.inp", "experiment": "exp.unv", "output_dir": "out",
                                        "parameters": [{"name": "E", "material": "CFRP_Face",
                                                        "constants": ["E1", "E2"]}]}, self.folder)

    def calibration(self, solve, extract, cancel=None) -> QuickCalibration:
        return QuickCalibration(self.config, solve, extract, cancel=cancel)

    def test_cancellation_leaves_no_completed_marker_or_partial_job(self):
        fake, cancel = S.FakeAbaqus(), threading.Event()

        def stopped_solve(inp, job_dir, job_name):
            (Path(job_dir) / f"{job_name}.odb").write_text("partial")
            (Path(job_dir) / f"{job_name}.lck").write_text("lock")
            cancel.set()
            raise CalibrationCancelled("stopped by the user; the owned Abaqus solve was terminated (confirmed).")

        calibration = self.calibration(stopped_solve, fake.extract, cancel)
        with self.assertRaises(CalibrationCancelled):
            calibration.fe_state({"E": 1.0})
        self.assertEqual(list(calibration.work.iterdir()), [])  # the partial job is gone
        calibration = self.calibration(fake.solve, fake.extract)  # a new run solves again (nothing reused)
        calibration.fe_state({"E": 1.0})
        self.assertEqual(fake.solves, 1)

    def test_stop_after_the_solve_discards_the_job(self):
        fake, cancel = S.FakeAbaqus(), threading.Event()

        def extract(odb, out, last):
            cancel.set()  # Stop pressed while the extraction finished
            return fake.extract(odb, out, last)

        calibration = self.calibration(fake.solve, extract, cancel)
        with self.assertRaises(CalibrationCancelled):
            calibration.fe_state({"E": 1.0})
        self.assertFalse(any(calibration.work.rglob("fe_modes.npz")))

    def test_unconfirmed_stop_keeps_the_job_untouched_and_unmarked(self):
        def stuck_solve(inp, job_dir, job_name):
            raise TerminationUnconfirmed("not confirmed")

        calibration = self.calibration(stuck_solve, S.FakeAbaqus().extract)
        with self.assertRaises(TerminationUnconfirmed):
            calibration.fe_state({"E": 1.0})
        (job,) = list(calibration.work.iterdir())
        self.assertFalse((job / "fe_modes.npz").exists())  # never a completed job
        fake = S.FakeAbaqus()
        self.calibration(fake.solve, fake.extract).fe_state({"E": 1.0})  # the leftover is cleared, then solved
        self.assertEqual(fake.solves, 1)

    def test_completion_marker_is_written_atomically(self):
        dataset = S.FakeAbaqus().extract(self._odb(), self.folder, 9)
        target = self.folder / "fe_modes.npz"
        with mock.patch("numpy.savez_compressed", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                _save_state(target, dataset)
        self.assertEqual(sorted(p.name for p in self.folder.glob("*fe_modes*")), [])
        _save_state(target, dataset)
        self.assertTrue(target.is_file())

    def _odb(self) -> Path:
        odb = self.folder / "x.odb"
        odb.write_text('{"E1": 52000.0, "E2": 52000.0, "G12": 4500.0}')
        return odb


# ----------------------------------------------------------------------------- the window (real Tk lifecycle)

class WindowLifecycleTests(_Dummy):
    def setUp(self) -> None:
        super().setUp()
        try:
            import tkinter as tk

            self.root = tk.Tk()
        except Exception as error:  # noqa: BLE001
            self.skipTest(f"Tk is unavailable: {error}")
        self.root.withdraw()
        self.addCleanup(self._destroy)
        (self.folder / "model.inp").write_text(S.INP)
        S.write_experiment(self.folder / "exp.unv", 0.9 * S.E0, S.G0)

    def _destroy(self) -> None:
        try:
            self.root.destroy()
        except Exception:  # noqa: BLE001 - already closed by the test
            pass

    def window(self, runner_factory):
        from quick_calibration_window import QuickCalibrationWindow

        window = QuickCalibrationWindow(self.root, runner_factory=runner_factory)
        window.set_inp(str(self.folder / "model.inp"))
        window.unv.set(str(self.folder / "exp.unv"))
        window.out.set(str(self.folder / "out"))
        self.pump(lambda: window.modal_set.get().startswith("PolyMAX"))
        return window

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

    def dummy_runner(self, config, cancel):
        return AbaqusRunner(self.command, 1, 120.0, cancel)

    def test_stop_button_during_the_solve(self):
        window = self.window(self.dummy_runner)
        self.assertEqual(str(window.stop_button["state"]), "disabled")
        window.start()
        self.assertTrue(self.pump(lambda: len(self.pids()) >= 2))
        time.sleep(1.5)
        self.assertEqual(str(window.stop_button["state"]), "normal")
        window.stop_button.invoke()
        self.assertTrue(window.summary.get().startswith("STOPPING"))  # not STOPPED before confirmation
        self.assertTrue(self.pump(lambda: not window.running() and window.summary.get().startswith("STOPPED")))
        self.assert_all_gone()
        self.assertIn("terminated (confirmed)", window.summary.get())
        self.assertEqual(str(window.run_button["state"]), "normal")
        self.assertEqual(str(window.stop_button["state"]), "disabled")
        self.assertFalse(any((self.folder / "out").rglob("fe_modes.npz")))
        self.assertFalse(any((self.folder / "out" / "work").iterdir()))  # no partial job left

    def test_closing_during_a_run_waits_for_termination(self):
        window = self.window(self.dummy_runner)
        window.start()
        self.assertTrue(self.pump(lambda: len(self.pids()) >= 2))
        time.sleep(1.5)
        self.assertTrue(self.root.protocol("WM_DELETE_WINDOW"))  # the close handler is installed
        window.close()
        self.assertFalse(window.destroyed)  # never closed while the solve may still run
        self.assertTrue(window.summary.get().startswith("CLOSING"))
        self.assertTrue(self.pump(lambda: window.destroyed))
        self.assert_all_gone()

    def test_unconfirmed_termination_keeps_the_window(self):
        trees = []

        def stuck_runner(config, cancel):
            runner = AbaqusRunner("abaqus", 1, 120.0, cancel, popen=NeverEnding,
                                  tree_factory=lambda process: trees.append(StuckTree(process)) or trees[-1])
            runner.POLL_SECONDS = 0.01
            return runner

        window = self.window(stuck_runner)
        window.start()
        self.assertTrue(self.pump(lambda: bool(trees)))
        window.close()
        seen = []
        self.assertTrue(self.pump(lambda: seen.append(window.summary.get()) or not window.running()))
        self.pump(lambda: window.summary.get().startswith("NOT CLOSED"), timeout=5)
        self.assertFalse(window.destroyed)
        self.assertFalse(any(text.startswith("STOPPED") for text in seen))  # never a premature success
        self.assertTrue(window.summary.get().startswith("NOT CLOSED"), window.summary.get())
        self.assertIn("could not be confirmed", window.log.get("1.0", "end"))
        window.start()  # a new run is refused while the owned processes may run
        self.assertTrue(window.summary.get().startswith("NOT STARTED"))
        trees[0].gone = True
        window.close()  # once they are gone, the window closes
        self.assertTrue(window.destroyed)

    def test_closing_when_idle(self):
        window = self.window(self.dummy_runner)
        window.close()
        self.assertTrue(window.destroyed)


if __name__ == "__main__":
    unittest.main()
