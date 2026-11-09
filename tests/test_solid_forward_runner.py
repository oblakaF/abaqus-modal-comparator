"""ABM-SOLID-5: supervised child-process solid forward runs (synthetic models and fake workers only).

The fake workers exercise the supervision itself: identity handshake, memory limit, silence and wall-clock limits,
cancellation and the termination of processes the worker started. No real FE model is solved here.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import textwrap
import threading
import time
import unittest

os.environ.setdefault("OMP_NUM_THREADS", "1")
ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "src", ROOT / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import numpy as np  # noqa: E402

from services import solid_c3d8i_model as sm  # noqa: E402
from services import solid_c3d8i_solver as ss  # noqa: E402
from services import solid_forward_runner as sfr  # noqa: E402
from test_solid_c3d8i_model import box_inp  # noqa: E402

FAKE = textwrap.dedent('''
    import json, os, subprocess, sys, time
    mode = sys.argv[1]
    def emit(event):
        sys.stdout.write(json.dumps(event) + "\\n"); sys.stdout.flush()
    if mode == "silent":
        time.sleep(120)
    elif mode == "wrong_pid":
        emit({"event": "hello", "pid": int(sys.argv[2])}); time.sleep(120)
    elif mode == "noise":
        emit({"event": "progress", "stage": "before hello"}); time.sleep(120)
    elif mode == "quiet":
        emit({"event": "hello", "pid": os.getpid()}); time.sleep(120)
    elif mode == "chatty":
        emit({"event": "hello", "pid": os.getpid()})
        while True:
            emit({"event": "progress", "stage": "tick"}); time.sleep(0.2)
    elif mode == "hog":
        emit({"event": "hello", "pid": os.getpid()})
        try:
            block = bytearray(int(sys.argv[2]))
            emit({"event": "result", "result": {"size": len(block)}})
        except MemoryError:
            emit({"event": "error", "kind": "MEMORY_LIMIT", "message": "allocation refused"})
    elif mode == "grandchild":
        emit({"event": "hello", "pid": os.getpid()})
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
        emit({"event": "progress", "stage": "spawned", "grandchild": child.pid}); time.sleep(300)
''')


class RunnerCase(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.folder = Path(self._dir.name)
        self.fake = self.folder / "fake_worker.py"
        self.fake.write_text(FAKE, encoding="utf-8")

    def model_path(self, **kwargs):
        path = self.folder / "box.inp"
        path.write_text(box_inp(**kwargs), encoding="latin-1")
        return path

    def request(self, **kwargs):
        path = self.model_path(nx=6, ny=3, nz=1, lx=60.0, ly=30.0, lz=5.0, **kwargs)
        return sfr.ForwardRequest(str(path), sfr.sha256_of(path))

    def fake_run(self, *args, limits=None, progress=None, cancel=None):
        return sfr.run(sfr.ForwardRequest("unused.inp", "0" * 64), limits or sfr.RunnerLimits(),
                       child_argv=[sys.executable, str(self.fake), *map(str, args)], skip_preflight=True,
                       progress=progress, cancel=cancel)

    def assertNothingLeft(self, outcome):
        self.assertEqual(outcome.active_processes_after, 0)
        for pid in (outcome.launcher_pid, outcome.worker_pid):
            if pid and pid != os.getpid():
                self.assertFalse(sfr.process_alive(pid), pid)


class SupervisedSolveTests(RunnerCase):
    def test_one_supervised_solve_matches_the_in_process_solver(self):
        request = self.request()
        stages = []
        outcome = sfr.run(request, progress=lambda event: stages.append(event.get("stage")))
        self.assertEqual(outcome.status, sfr.SOLVED, outcome.message)
        self.assertTrue(outcome.worker_in_job)
        self.assertIsNotNone(outcome.worker_pid)
        self.assertGreater(outcome.peak_job_memory_bytes, 0)
        self.assertGreater(outcome.peak_worker_commit_bytes, 0)
        self.assertGreaterEqual(outcome.peak_job_memory_bytes, outcome.peak_worker_commit_bytes)
        self.assertGreater(outcome.available_memory_before_bytes, 0)
        self.assertLessEqual(outcome.min_available_memory_bytes, outcome.available_memory_before_bytes)
        self.assertNothingLeft(outcome)
        self.assertTrue({"preflight", "worker verified", "assemble stiffness", "factorise"} <= set(stages))
        direct = ss.SolidForwardModel(sm.load_solid_inp(request.inp_path)).solve(14)
        np.testing.assert_allclose(outcome.result["frequencies_hz"], direct.frequencies_hz, rtol=1e-10)
        self.assertTrue(outcome.result["rigid"]["passed"])
        self.assertEqual(outcome.result["abaqus_equivalence"], "NOT_VERIFIED")
        self.assertEqual(outcome.result["material"]["e1"], 70000.0)  # the INP value, unchanged

    def test_the_venv_launcher_is_not_mistaken_for_the_worker(self):
        outcome = sfr.run(self.request())
        self.assertEqual(outcome.status, sfr.SOLVED, outcome.message)
        if Path(sys.executable).parent.name.lower() == "scripts" and (Path(sys.prefix) / "pyvenv.cfg").is_file():
            self.assertNotEqual(outcome.worker_pid, outcome.launcher_pid)  # the real interpreter was resolved
        self.assertTrue(outcome.worker_in_job)


class RefusalTests(RunnerCase):
    def test_insufficient_memory_is_refused_before_any_worker_starts(self):
        outcome = sfr.run(self.request(), sfr.RunnerLimits(reserve_free_memory_bytes=10 ** 18))
        self.assertEqual(outcome.status, sfr.REFUSED)
        self.assertIn("does not fit", outcome.message)
        self.assertIsNone(outcome.launcher_pid)
        outcome = sfr.run(self.request(), sfr.RunnerLimits(max_job_memory_bytes=10_000))
        self.assertEqual(outcome.status, sfr.REFUSED)
        self.assertIsNone(outcome.launcher_pid)

    def test_a_changed_inp_is_refused_in_the_parent_and_in_the_worker(self):
        request = self.request()
        changed = sfr.ForwardRequest(request.inp_path, "f" * 64)
        outcome = sfr.run(changed)
        self.assertEqual(outcome.status, sfr.REFUSED)
        self.assertIn("changed", outcome.message)
        outcome = sfr.run(changed, skip_preflight=True)
        self.assertEqual(outcome.status, sfr.FAILED)
        self.assertIn("changed", outcome.message)
        self.assertIsNone(outcome.result)
        self.assertNothingLeft(outcome)

    def test_a_worker_that_never_identifies_itself_is_refused(self):
        outcome = self.fake_run("silent", limits=sfr.RunnerLimits(handshake_seconds=2.0))
        self.assertEqual(outcome.status, sfr.REFUSED)
        self.assertIn("identity could not be established", outcome.message)
        self.assertLess(outcome.runtime_seconds, 30.0)
        self.assertNothingLeft(outcome)

    def test_a_worker_reporting_a_pid_outside_the_job_is_refused(self):
        outcome = self.fake_run("wrong_pid", os.getpid())
        self.assertEqual(outcome.status, sfr.REFUSED)
        self.assertIn("not under supervision", outcome.message)
        self.assertFalse(outcome.worker_in_job)
        self.assertIsNone(outcome.result)
        self.assertNothingLeft(outcome)

    def test_output_before_the_identity_handshake_is_refused(self):
        outcome = self.fake_run("noise")
        self.assertEqual(outcome.status, sfr.REFUSED)
        self.assertIn("before identifying", outcome.message)
        self.assertNothingLeft(outcome)


class LimitTests(RunnerCase):
    def test_the_kernel_memory_limit_covers_the_worker_and_is_measured(self):
        limit = 300 * 1024 ** 2
        outcome = self.fake_run("hog", 800 * 1024 ** 2, limits=sfr.RunnerLimits(max_job_memory_bytes=limit))
        self.assertEqual(outcome.status, sfr.FAILED)
        self.assertIn("MEMORY_LIMIT", outcome.message)  # the allocation was refused inside the worker
        self.assertTrue(outcome.worker_in_job)
        # Windows counts the refused request in the job peak: reported as "limit reached", not as usage
        self.assertTrue(outcome.memory_limit_reached)
        self.assertNothingLeft(outcome)
        within = self.fake_run("hog", 100 * 1024 ** 2, limits=sfr.RunnerLimits(max_job_memory_bytes=limit))
        self.assertEqual(within.status, sfr.SOLVED)
        self.assertFalse(within.memory_limit_reached)
        self.assertGreaterEqual(within.peak_job_memory_bytes, 100 * 1024 ** 2)  # measured, includes the 100 MB block
        self.assertLessEqual(within.peak_job_memory_bytes, limit)
        self.assertNothingLeft(within)

    def test_silence_and_wall_clock_limits_terminate_the_worker(self):
        outcome = self.fake_run("quiet", limits=sfr.RunnerLimits(max_silence_seconds=1.0))
        self.assertEqual(outcome.status, sfr.KILLED)
        self.assertIn("No progress", outcome.message)
        self.assertNothingLeft(outcome)
        outcome = self.fake_run("chatty", limits=sfr.RunnerLimits(max_seconds=2.0))
        self.assertEqual(outcome.status, sfr.KILLED)
        self.assertIn("Wall-clock", outcome.message)
        self.assertNothingLeft(outcome)


class CancellationTests(RunnerCase):
    def test_cancel_terminates_the_worker_and_the_processes_it_started(self):
        cancel = threading.Event()
        seen = {}

        def progress(event):
            if "grandchild" in event:
                seen["grandchild"] = int(event["grandchild"])
                cancel.set()

        outcome = self.fake_run("grandchild", progress=progress, cancel=cancel)
        self.assertEqual(outcome.status, sfr.CANCELLED)
        self.assertIn("grandchild", seen)
        self.assertNothingLeft(outcome)
        self.assertFalse(sfr.process_alive(seen["grandchild"]))

    def test_cancel_during_a_real_solve(self):
        cancel = threading.Event()

        def progress(event):
            if event.get("stage") == "assemble mass":
                cancel.set()

        outcome = sfr.run(self.request(), progress=progress, cancel=cancel)
        self.assertIn(outcome.status, (sfr.CANCELLED, sfr.SOLVED))  # a tiny model may finish first
        if outcome.status == sfr.CANCELLED:
            self.assertIsNone(outcome.result)
        self.assertNothingLeft(outcome)

    def test_cancel_before_start(self):
        cancel = threading.Event()
        cancel.set()
        outcome = sfr.run(self.request(), cancel=cancel)
        self.assertEqual(outcome.status, sfr.CANCELLED)
        self.assertIsNone(outcome.launcher_pid)


if __name__ == "__main__":
    unittest.main()
