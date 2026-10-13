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
        """Test cleanup only: the dummy recorded these PIDs itself."""
        for pid in self.pids():
            identity = owned_processes.ProcessIdentity(pid, owned_processes.creation_time(pid))
            owned_processes.kill_verified(identity)

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

    @unittest.skipIf(os.name == "nt", "POSIX zombie semantics")
    def test_a_killed_unreaped_child_is_not_alive(self):
        import abaqus_bridge
        import signal

        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
        self.addCleanup(child.wait)
        self.assertTrue(abaqus_bridge._pid_exists(child.pid))
        os.kill(child.pid, signal.SIGKILL)
        deadline = time.monotonic() + 10
        while abaqus_bridge._pid_exists(child.pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(abaqus_bridge._pid_exists(child.pid))  # a zombie (not reaped yet) has exited
        self.assertIsNone(owned_processes.creation_time(child.pid))

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

    tracker_available = True

    def __init__(self, process) -> None:
        self.process = process
        self.terminate_calls = 0
        self.gone = False  # set by a test: the processes ended on their own later

    def refresh(self) -> None:
        pass

    def unconfirmed(self):
        if not self.tracker_available:
            return None  # identities cannot be established: unknown, never "stopped"
        return [] if self.gone else [owned_processes.ProcessIdentity(self.process.pid, (1,))]

    def terminate(self, timeout_seconds: float = 0.0) -> bool:
        self.terminate_calls += 1
        return False

    def describe(self, identities=None) -> str:
        return f"PID {self.process.pid}"


class NoTrackerTree(StuckTree):
    tracker_available = False


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

    def interrupted_runner(self, tree_class):
        trees = []

        class Interrupted(NeverEnding):
            def wait(self, timeout=None):
                raise KeyboardInterrupt

        runner = AbaqusRunner("abaqus", 1, 120.0, threading.Event(), popen=Interrupted,
                              tree_factory=lambda process: trees.append(tree_class(process)) or trees[-1])
        return runner, trees

    def test_ctrl_c_with_confirmed_termination_keeps_the_interrupt(self):
        class Stoppable(StuckTree):
            def terminate(self, timeout_seconds: float = 0.0) -> bool:
                self.terminate_calls += 1
                return True

        runner, trees = self.interrupted_runner(Stoppable)
        with self.assertRaises(KeyboardInterrupt):
            self.solve(runner)
        self.assertEqual(trees[0].terminate_calls, 1)

    def test_ctrl_c_with_a_tree_that_refuses_termination(self):
        runner, trees = self.interrupted_runner(StuckTree)
        with self.assertRaises(TerminationUnconfirmed) as caught:
            self.solve(runner)
        self.assertIsInstance(caught.exception.__cause__, KeyboardInterrupt)
        self.assertIn("interrupted (KeyboardInterrupt)", str(caught.exception))
        self.assertIn("could not be confirmed", str(caught.exception))
        self.assertEqual(len(caught.exception.still_running()), 1)  # the unconfirmed state is preserved
        self.assertFalse(caught.exception.resolved())

    def test_ctrl_c_during_the_extraction_with_a_tree_that_refuses_termination(self):
        import abaqus_bridge

        def interrupted(*args, process_callback=None, **kwargs):
            process_callback(NeverEnding())
            raise KeyboardInterrupt

        runner = AbaqusRunner("abaqus", 1, 120.0, threading.Event(), tree_factory=StuckTree)
        with mock.patch.object(abaqus_bridge, "run_abaqus_extraction", side_effect=interrupted):
            with self.assertRaises(TerminationUnconfirmed) as caught:
                runner.extract(Path("x.odb"), Path("out"), 10)
        self.assertIsInstance(caught.exception.__cause__, KeyboardInterrupt)

    def test_a_missing_tracker_is_never_all_stopped(self):
        unknown = TerminationUnconfirmed("not confirmed", None)
        self.assertIsNone(unknown.still_running())
        self.assertFalse(unknown.resolved())
        failing = TerminationUnconfirmed("not confirmed", mock.Mock(side_effect=OSError("tracker broken")))
        self.assertIsNone(failing.still_running())
        self.assertFalse(failing.resolved())
        self.assertTrue(TerminationUnconfirmed("x", lambda: []).resolved())  # confirmed gone by a tracker
        runner = AbaqusRunner("abaqus", 1, 120.0, threading.Event(), popen=NeverEnding, tree_factory=NoTrackerTree)
        runner.POLL_SECONDS = 0.01
        runner.timeout_seconds = 0
        with self.assertRaises(TerminationUnconfirmed) as caught:
            self.solve(runner)
        self.assertIsNone(caught.exception.still_running())
        import abaqus_bridge

        def unconfirmed(*args, **kwargs):  # the extraction's own stop failed before any tracker existed
            raise abaqus_bridge.ExtractionTerminationUnconfirmed("Cancellation could not be confirmed")

        with mock.patch.object(abaqus_bridge, "run_abaqus_extraction", side_effect=unconfirmed):
            with self.assertRaises(TerminationUnconfirmed) as caught:
                AbaqusRunner("abaqus", 1, 120.0, threading.Event()).extract(Path("x.odb"), Path("out"), 10)
        self.assertIsNone(caught.exception.still_running())
        self.assertFalse(caught.exception.resolved())


# ----------------------------------------------------------------------------- ownership (fake process tables)

class FakeSystem:
    """A process table with creation identities; ``kill`` removes exactly the identity it is given."""

    def __init__(self, processes) -> None:
        self.processes = dict(processes)  # pid -> (parent, created)
        self.killed: list[tuple] = []
        self.table_fails = False  # a failed / incomplete process-table read (empty snapshot)

    def table(self):
        if self.table_fails:
            return {}
        return {pid: parent for pid, (parent, _) in self.processes.items()}

    def reparent_orphans(self, dead: int) -> None:
        """Like the OS: the children of an exited process get another parent and keep running."""
        for pid, (parent, created) in list(self.processes.items()):
            if parent == dead:
                self.processes[pid] = (1, created)

    def state(self, pid):
        if pid not in self.processes:
            return owned_processes.GONE, None
        created = self.processes[pid][1]
        return (owned_processes.UNKNOWN, None) if created is None else (owned_processes.ALIVE, created)

    def kill(self, identity) -> None:
        current = self.processes.get(identity.pid)
        if current is not None and current[1] == identity.created:  # identity-checked, like kill_verified
            self.killed.append((identity.pid, identity.created))
            del self.processes[identity.pid]

    def tree(self, root_pid: int = 10):
        system = self

        return owned_processes.OwnedProcessTree(self.launcher(root_pid), table=self.table, state=self.state,
                                                kill=self.kill)

    def launcher(self, root_pid: int = 10):
        system = self

        class Launcher:
            pid = root_pid

            def __init__(self, *args, **kwargs) -> None:
                pass

            def poll(self):
                return None if root_pid in system.processes else -9

            def wait(self, timeout=None):
                if root_pid in system.processes:
                    raise subprocess.TimeoutExpired("abaqus", timeout)
                return -9

            def kill(self):
                if root_pid in system.processes:
                    system.killed.append((root_pid, system.processes[root_pid][1]))
                    del system.processes[root_pid]
                    system.reparent_orphans(root_pid)

        return Launcher()


class OwnershipTests(unittest.TestCase):
    def test_owned_descendants_are_terminated_and_confirmed(self):
        system = FakeSystem({10: (1, (5,)), 11: (10, (6,)), 12: (11, (7,)), 99: (1, (1,))})
        tree = system.tree()
        tree.refresh()
        self.assertEqual(set(tree.members), {10, 11, 12})  # 99 is not ours
        self.assertTrue(tree.terminate(timeout_seconds=2, poll_seconds=0.01))
        self.assertEqual(sorted(pid for pid, _ in system.killed), [10, 11, 12])
        self.assertIn(99, system.processes)

    def test_a_reused_pid_and_its_children_are_never_killed(self):
        system = FakeSystem({10: (1, (5,)), 11: (10, (6,))})
        tree = system.tree()
        tree.refresh()
        self.assertEqual(set(tree.members), {10, 11})
        del system.processes[11]  # the owned child exits ...
        system.processes[11] = (1, (20,))  # ... its PID is reused by an unrelated process ...
        system.processes[12] = (11, (21,))  # ... which creates children
        system.processes[13] = (12, (22,))
        tree.refresh()
        self.assertEqual(tree.members[11].created, (6,))  # still the original identity
        self.assertNotIn(12, tree.members)
        self.assertNotIn(13, tree.members)
        self.assertTrue(tree.terminate(timeout_seconds=2, poll_seconds=0.01))
        self.assertEqual(system.killed, [(10, (5,))])  # only the launcher; none of the unrelated processes
        self.assertEqual(set(system.processes), {11, 12, 13})

    def test_stale_parent_links_are_not_ours(self):
        system = FakeSystem({10: (1, (5,)), 13: (10, (2,))})  # 13 is older than the recorded parent 10
        tree = system.tree()
        tree.refresh()
        self.assertNotIn(13, tree.members)
        tree.terminate(timeout_seconds=1, poll_seconds=0.01)
        self.assertIn(13, system.processes)

    def test_unreadable_identity_is_never_killed_and_never_confirmed(self):
        system = FakeSystem({10: (1, (5,)), 11: (10, None)})  # a child whose identity cannot be read
        tree = system.tree()
        tree.refresh()
        self.assertNotIn(11, tree.members)
        self.assertFalse(tree.terminate(timeout_seconds=0.2, poll_seconds=0.01))
        self.assertIn(11, system.processes)  # not killed
        self.assertEqual([i.pid for i in tree.unconfirmed()], [11])
        self.assertIn("identity unreadable", tree.describe())
        del system.processes[11]  # once it is gone, the state is confirmed
        self.assertEqual(tree.unconfirmed(), [])

    def test_a_launcher_without_identity_cannot_confirm(self):
        system = FakeSystem({10: (1, None), 11: (10, (6,))})
        tree = system.tree()
        self.assertFalse(tree.identity_available)
        tree.refresh()
        self.assertNotIn(11, tree.members)  # descendants cannot be attributed
        self.assertFalse(tree.terminate(timeout_seconds=0.5, poll_seconds=0.01))
        self.assertIsNone(tree.unconfirmed())
        self.assertIn(11, system.processes)

    def test_a_reparented_unknown_child_stays_unconfirmed(self):
        system = FakeSystem({10: (1, (5,)), 11: (10, None), 99: (1, (1,))})  # 11: an UNKNOWN child of the launcher
        tree = system.tree()
        tree.refresh()
        self.assertEqual(list(tree.unverified), [11])
        self.assertFalse(tree.terminate(timeout_seconds=0.3, poll_seconds=0.01))  # never True while 11 may run
        self.assertEqual(system.processes[11], (1, None))  # the launcher died; 11 was reparented and still runs
        self.assertEqual(system.killed, [(10, (5,))])  # only the verified launcher: neither 11 nor 99
        self.assertEqual([identity.pid for identity in tree.unconfirmed()], [11])
        for _ in range(3):
            tree.refresh()  # repeated snapshots with the new parent never drop it
        self.assertEqual([identity.pid for identity in tree.unconfirmed()], [11])
        self.assertIn("identity unreadable", tree.describe())

    def test_a_failed_process_table_read_never_drops_an_unknown_child(self):
        system = FakeSystem({10: (1, (5,)), 11: (10, None)})
        tree = system.tree()
        tree.refresh()
        system.table_fails = True  # the child is missing from the snapshot, but alive
        tree.refresh()
        self.assertEqual([identity.pid for identity in tree.unconfirmed()], [10, 11])  # launcher not stopped yet
        self.assertFalse(tree.terminate(timeout_seconds=0.2, poll_seconds=0.01))
        self.assertIn(11, system.processes)

    def test_only_a_confirmed_exit_resolves_an_unknown_child(self):
        system = FakeSystem({10: (1, (5,)), 11: (10, None)})
        tree = system.tree()
        tree.refresh()
        self.assertFalse(tree.terminate(timeout_seconds=0.2, poll_seconds=0.01))
        system.table_fails = True
        del system.processes[11]  # the child really exits: its own state is GONE (independent of the table)
        self.assertEqual(tree.unconfirmed(), [])
        self.assertTrue(tree.terminate(timeout_seconds=0.2, poll_seconds=0.01))

    def test_an_unknown_member_state_is_not_gone(self):
        system = FakeSystem({10: (1, (5,)), 11: (10, (6,))})
        tree = system.tree()
        tree.refresh()
        system.processes[11] = (10, None)  # the owned child's state can no longer be read
        self.assertFalse(tree.terminate(timeout_seconds=0.2, poll_seconds=0.01))
        self.assertEqual([i.pid for i in tree.unconfirmed()], [11])


class UnknownChildWorkflowTests(unittest.TestCase):
    """Stop with an UNKNOWN child that survives its launcher: never STOPPED, the job folder stays."""

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="qc_p1a_unknown_"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.system = FakeSystem({10: (1, (5,)), 11: (10, None), 99: (1, (1,))})

    def runner(self, cancel) -> AbaqusRunner:
        system = self.system

        def tree_factory(process):
            return owned_processes.OwnedProcessTree(process, table=system.table, state=system.state, kill=system.kill)

        runner = AbaqusRunner("abaqus", 1, 120.0, cancel, popen=lambda *a, **k: system.launcher(),
                              tree_factory=tree_factory)
        runner.POLL_SECONDS = 0.01
        runner.STOP_TIMEOUT_SECONDS = 0.3
        return runner

    def test_stop_is_unconfirmed_and_the_job_is_kept(self):
        (self.folder / "model.inp").write_text(S.INP)
        S.write_experiment(self.folder / "exp.unv", 0.9 * S.E0, S.G0)
        config = config_from_dict({"model_inp": "model.inp", "experiment": "exp.unv", "output_dir": "out",
                                   "parameters": [{"name": "E", "material": "CFRP_Face", "constants": ["E1", "E2"]}]},
                                  self.folder)
        cancel = threading.Event()
        runner = self.runner(cancel)
        threading.Timer(0.2, cancel.set).start()
        calibration = QuickCalibration(config, runner.solve, runner.extract, cancel=cancel)
        with self.assertRaises(TerminationUnconfirmed) as caught:
            calibration.fe_state({"E": 1.0})
        self.assertNotIsInstance(caught.exception, CalibrationCancelled)  # STOPPED is never reported
        self.assertEqual([identity.pid for identity in caught.exception.still_running()], [11])
        self.assertFalse(caught.exception.resolved())
        self.assertEqual(self.system.killed, [(10, (5,))])  # no unrelated or unverifiable process killed
        (job,) = list(calibration.work.iterdir())
        self.assertTrue((job / f"{job.name}.inp").is_file())  # no cleanup without confirmed termination
        self.assertFalse((job / "fe_modes.npz").exists())
        fake = S.FakeAbaqus()
        later = QuickCalibration(config, fake.solve, fake.extract)
        later.process_state = self.system.state  # the recorded processes are re-checked (not the host's PIDs)
        with self.assertRaisesRegex(QuickCalibrationError, "neither reused, deleted nor overwritten"):
            later.fe_state({"E": 1.0})  # child 11 may still run: refused, untouched
        self.assertTrue((job / f"{job.name}.inp").is_file())
        del self.system.processes[11]  # the child exits: now confirmed
        self.assertTrue(caught.exception.resolved())
        later.fe_state({"E": 1.0})  # only now cleared and solved
        self.assertEqual(fake.solves, 1)


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
        before = sorted(p.name for p in job.iterdir())
        fake = S.FakeAbaqus()
        with self.assertRaisesRegex(QuickCalibrationError, "neither reused, deleted nor overwritten"):
            self.calibration(fake.solve, fake.extract).fe_state({"E": 1.0})  # unknown processes: refused (P1b-B)
        self.assertEqual(fake.solves, 0)
        self.assertEqual(sorted(p.name for p in job.iterdir()), before)  # untouched

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

    def stuck_window(self, tree_class):
        trees = []

        def stuck_runner(config, cancel):
            runner = AbaqusRunner("abaqus", 1, 120.0, cancel, popen=NeverEnding,
                                  tree_factory=lambda process: trees.append(tree_class(process)) or trees[-1])
            runner.POLL_SECONDS = 0.01
            return runner

        window = self.window(stuck_runner)
        return window, trees

    def close_during_a_stuck_run(self, window, trees):
        import quick_calibration_window as qw

        window.start()
        self.assertTrue(self.pump(lambda: bool(trees)))
        seen = []
        with mock.patch.object(qw.messagebox, "askyesno", return_value=False) as ask:
            window.close()
            self.assertTrue(self.pump(lambda: seen.append(window.summary.get()) or not window.running()))
            self.pump(lambda: window.summary.get().startswith("NOT CLOSED"), timeout=5)
        self.assertFalse(window.destroyed)
        self.assertFalse(any(text.startswith("STOPPED") for text in seen))  # never a premature success
        self.assertTrue(window.summary.get().startswith("NOT CLOSED"), window.summary.get())
        self.assertTrue(ask.called)  # the user is asked; the default answer keeps the window
        self.assertIn("could not be confirmed", window.log.get("1.0", "end"))

    def test_unconfirmed_termination_keeps_the_window(self):
        import quick_calibration_window as qw

        window, trees = self.stuck_window(StuckTree)
        self.close_during_a_stuck_run(window, trees)
        with mock.patch.object(qw.messagebox, "askyesno", return_value=False):
            window.start()  # a new run is refused while the owned processes may run
        self.assertTrue(window.summary.get().startswith("NOT STARTED"))
        trees[0].gone = True
        with mock.patch.object(qw.messagebox, "askyesno") as ask:
            window.close()  # confirmed gone by the tracker: closes without asking
        ask.assert_not_called()
        self.assertTrue(window.destroyed)

    def test_unknown_reparented_child_never_shows_stopped(self):
        import quick_calibration_window as qw

        system = FakeSystem({10: (1, (5,)), 11: (10, None), 99: (1, (1,))})

        def unknown_child_runner(config, cancel):
            runner = AbaqusRunner("abaqus", 1, 120.0, cancel, popen=lambda *a, **k: system.launcher(),
                                  tree_factory=lambda process: owned_processes.OwnedProcessTree(
                                      process, table=system.table, state=system.state, kill=system.kill))
            runner.POLL_SECONDS = 0.01
            runner.STOP_TIMEOUT_SECONDS = 0.3
            return runner

        window = self.window(unknown_child_runner)
        window.start()
        self.assertTrue(self.pump(lambda: window.running() and system.processes.get(11) is not None))
        time.sleep(0.2)
        seen = []
        window.stop_button.invoke()
        self.assertTrue(self.pump(lambda: seen.append(window.summary.get()) or not window.running()))
        self.pump(lambda: window.summary.get().startswith("STOP NOT CONFIRMED"), timeout=5)
        self.assertFalse(any(text.startswith("STOPPED") for text in seen))
        self.assertTrue(window.summary.get().startswith("STOP NOT CONFIRMED"), window.summary.get())
        self.assertEqual(system.killed, [(10, (5,))])
        self.assertTrue(any((self.folder / "out" / "work").iterdir()))  # the job folder is kept
        with mock.patch.object(qw.messagebox, "askyesno", return_value=False):
            window.close()
        self.assertFalse(window.destroyed)
        del system.processes[11]  # confirmed exit
        with mock.patch.object(qw.messagebox, "askyesno") as ask:
            window.close()
        ask.assert_not_called()
        self.assertTrue(window.destroyed)

    def test_missing_tracker_stays_blocked_until_the_user_confirms(self):
        import quick_calibration_window as qw

        window, trees = self.stuck_window(NoTrackerTree)
        self.close_during_a_stuck_run(window, trees)
        self.assertIn("UNKNOWN", window.summary.get())
        trees[0].gone = True  # irrelevant: without a tracker nothing can be confirmed
        with mock.patch.object(qw.messagebox, "askyesno", return_value=False):
            window.close()
            window.start()
        self.assertFalse(window.destroyed)
        self.assertTrue(window.summary.get().startswith("NOT STARTED"))
        with mock.patch.object(qw.messagebox, "askyesno", return_value=True):
            window.close()  # the user verified Task Manager explicitly
        self.assertTrue(window.destroyed)

    def test_closing_when_idle(self):
        window = self.window(self.dummy_runner)
        window.close()
        self.assertTrue(window.destroyed)


if __name__ == "__main__":
    unittest.main()
