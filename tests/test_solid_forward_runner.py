"""ABM-SOLID-5: supervised child-process solid forward runs (synthetic models and fake workers only).

The fake workers exercise the supervision itself: identity handshake, memory limit, silence and wall-clock limits,
cancellation and the termination of processes the worker started. No real FE model is solved here.

ABM-AUD-2: the supervision is Win32 (a Job Object with a kernel memory limit, a suspended child, process identity by
IsProcessInJob, kill-on-job-close). Every test that needs it carries ``WINDOWS_ONLY`` and is reported on another platform
as SKIPPED_WINDOWS_ONLY, never as a pass; the Windows CI job runs them all and accepts no skip. What does not need Win32
(the validation of What-If points, the reuse of the model, and the honest refusal on a platform without job objects)
runs everywhere.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from unittest import mock

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

WINDOWS_ONLY_REASON = ("SKIPPED_WINDOWS_ONLY: Win32 Job Object supervision (kernel memory limit, suspended start, process "
                       "identity, kill-on-job-close); run natively by the Windows CI job")
WINDOWS_ONLY = unittest.skipUnless(sys.platform == "win32", WINDOWS_ONLY_REASON)

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
    elif mode == "points":  # What-If: point 1 solved, point 2 failed, then the final result (point 3 never reported)
        emit({"event": "hello", "pid": os.getpid()})
        p = {"e1": 1.0, "e2": 1.0, "g12": 1.0}
        emit({"event": "point", "point": {"index": 1, "parameters": p, "status": "SOLVED", "error": None,
              "mass_matrix_reused": True, "result": {"frequencies_hz": [1.0, 2.0]}}})
        emit({"event": "point", "point": {"index": 2, "parameters": p, "status": "FAILED", "result": None,
              "error": {"kind": "RIGID_BODY_CLASSIFICATION_FAILED", "message": "synthetic"}}})
        emit({"event": "result", "result": {"reuse": {"one_forward_model": True,
              "mass_matrix_reused_for_every_point": True, "points_attempted": 2}}})
    elif mode == "point_then_wait":
        emit({"event": "hello", "pid": os.getpid()})
        emit({"event": "point", "point": {"index": 1, "parameters": {"e1": 1.0, "e2": 1.0, "g12": 1.0},
              "status": "SOLVED", "error": None, "result": {"frequencies_hz": [1.0]}}})
        while True:
            emit({"event": "progress", "stage": "point 2 of 3"}); time.sleep(0.2)
    elif mode == "point_then_memory":
        emit({"event": "hello", "pid": os.getpid()})
        emit({"event": "point", "point": {"index": 1, "parameters": {"e1": 1.0, "e2": 1.0, "g12": 1.0},
              "status": "SOLVED", "error": None, "result": {"frequencies_hz": [1.0]}}})
        emit({"event": "error", "kind": "MEMORY_LIMIT", "message": "The job memory limit stopped an allocation."})
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

    def fake_run(self, *args, limits=None, progress=None, cancel=None, points=()):
        return sfr.run(sfr.ForwardRequest("unused.inp", "0" * 64, points=points), limits or sfr.RunnerLimits(),
                       child_argv=[sys.executable, str(self.fake), *map(str, args)], skip_preflight=True,
                       progress=progress, cancel=cancel)

    def assertNothingLeft(self, outcome):
        self.assertEqual(outcome.active_processes_after, 0)
        for pid in (outcome.launcher_pid, outcome.worker_pid):
            if pid and pid != os.getpid():
                self.assertFalse(sfr.process_alive(pid), pid)


@WINDOWS_ONLY
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


@WINDOWS_ONLY
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


@WINDOWS_ONLY
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


@WINDOWS_ONLY
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


THREE = ((70000.0, 20000.0, 9000.0), (60000.0, 25000.0, 7000.0), (90000.0, 15000.0, 11000.0))


class WhatIfTests(RunnerCase):
    """ABM-SOLID-6: manual E1/E2/G12 points, synthetic models only."""

    def independent(self, path, point):
        """A fresh import and a fresh forward model for one point: nothing is shared with the What-If run."""
        e1, e2, g12 = point
        return ss.SolidForwardModel(sm.load_solid_inp(path)).solve(14, e1=e1, e2=e2, g12=g12).frequencies_hz

    @WINDOWS_ONLY
    def test_two_and_three_point_runs_match_independent_single_point_solves_in_the_given_order(self):
        base = self.request()
        for points in (THREE[1:], THREE):
            request = sfr.ForwardRequest(base.inp_path, base.inp_sha256, points=points)
            outcome = sfr.run(request)
            self.assertEqual(outcome.status, sfr.SOLVED, outcome.message)
            self.assertEqual(outcome.label, sfr.WHATIF_LABEL)
            self.assertTrue(outcome.worker_in_job)
            self.assertEqual(outcome.preflight["solve_count"], len(points))
            self.assertEqual([p["index"] for p in outcome.points], list(range(1, len(points) + 1)))
            for record, point in zip(outcome.points, points):
                self.assertEqual(record["status"], sfr.POINT_SOLVED)
                self.assertEqual(tuple(record["parameters"].values()), point)  # E1, E2, G12 in the entered order
                used = record["result"]["material"]
                self.assertEqual((used["e1"], used["e2"], used["g12"]), point)
                self.assertEqual((used["e3"], used["nu12"], used["g13"], used["g23"]), (15000.0, 0.0, 7000.0, 6000.0))
                self.assertEqual(record["result"]["density"], 2.7e-9)
                self.assertTrue(record["result"]["rigid"]["passed"])
                np.testing.assert_allclose(record["result"]["frequencies_hz"], self.independent(base.inp_path, point),
                                           rtol=1e-10)
            self.assertTrue(outcome.result["reuse"]["mass_matrix_reused_for_every_point"])
            self.assertEqual(outcome.result["reuse"]["points_attempted"], len(points))
            self.assertIn(f"All {len(points)} What-If points solved", outcome.message)
            self.assertNothingLeft(outcome)
        # different points give different spectra: the parameters really reached the stiffness
        self.assertFalse(np.allclose(outcome.points[0]["result"]["frequencies_hz"],
                                     outcome.points[1]["result"]["frequencies_hz"]))

    def test_the_mesh_geometry_cache_and_mass_matrix_are_built_once_for_all_points(self):
        path = self.request().inp_path
        model = sm.load_solid_inp(path)
        forward = ss.SolidForwardModel(model)
        geometries = forward.preflight(14).distinct_element_geometries
        events = []
        with mock.patch.object(ss, "consistent_mass", wraps=ss.consistent_mass) as mass_kernel, \
                mock.patch.object(ss, "c3d8i_reference_stiffness", wraps=ss.c3d8i_reference_stiffness) as stiffness, \
                mock.patch.object(sm, "load_solid_inp", side_effect=AssertionError("re-imported")), \
                mock.patch.object(ss.SolidForwardModel, "__init__", side_effect=AssertionError("second model")):
            reuse = sfr.solve_points(forward, THREE, 14, 4, events.append)
        self.assertEqual(mass_kernel.call_count, geometries)          # element mass once per distinct geometry
        self.assertEqual(stiffness.call_count, 3 * geometries)        # stiffness once per geometry and point
        self.assertTrue(reuse["mass_matrix_reused_for_every_point"])
        points = [e["point"] for e in events if e["event"] == "point"]
        self.assertEqual([p["index"] for p in points], [1, 2, 3])
        self.assertTrue(all(p["mass_matrix_reused"] for p in points))

    def test_invalid_points_are_rejected_before_anything_runs(self):
        from services import solid_c3d8i_forward as sf

        material = sm.load_solid_inp(self.request().inp_path).material
        for bad, part in (((0.0, 1.0, 1.0), "E1 must be positive"), ((1.0, -2.0, 1.0), "E2 must be positive"),
                          ((1.0, 1.0, float("nan")), "G12 must be a finite"), ((float("inf"), 1.0, 1.0), "E1 must be a finite"),
                          (("abc", 1.0, 1.0), "E1 is not a number"), ((1.0, 1.0), "Enter E1, E2 and G12")):
            with self.subTest(bad=bad):
                with self.assertRaises(sfr.RunnerRefused) as caught:
                    sfr.validate_points(material, (bad,))
                self.assertIn(part, str(caught.exception))
        poisson = sf.OrthotropicEngineeringConstants(70000.0, 20000.0, 15000.0, 0.3, 0.3, 0.3, 9000.0, 7000.0, 6000.0)
        with self.assertRaises(sfr.RunnerRefused) as caught:  # nu12^2 E2 / E1 > 1: not positive definite
            sfr.validate_points(poisson, ((10000.0, 200000.0, 9000.0),))
        self.assertIn("Not physically admissible", str(caught.exception))
        self.assertEqual(sfr.validate_points(poisson, ((70000, 20000, 9000),)), ((70000.0, 20000.0, 9000.0),))
        for points, part in ((THREE + THREE[:1], "1 to 3"), ((), "1 to 3"), ((THREE[0], THREE[0]), "identical")):
            with self.assertRaises(sfr.RunnerRefused) as caught:
                sfr.validate_points(material, points)
            self.assertIn(part, str(caught.exception))

    @WINDOWS_ONLY
    def test_invalid_points_are_refused_by_the_parent_and_again_by_the_worker(self):
        base = self.request()
        outcome = sfr.run(sfr.ForwardRequest(base.inp_path, base.inp_sha256, points=((70000.0, 0.0, 9000.0),)))
        self.assertEqual(outcome.status, sfr.REFUSED)
        self.assertIn("Point 1: E2 must be positive", outcome.message)
        self.assertIsNone(outcome.launcher_pid)  # refused in the parent: no worker was started
        worker = sfr.run(sfr.ForwardRequest(base.inp_path, base.inp_sha256, points=((70000.0, 0.0, 9000.0),)),
                         skip_preflight=True)  # the worker validates again
        self.assertEqual(worker.status, sfr.FAILED)
        self.assertIn("E2 must be positive", worker.message)
        self.assertEqual([p["status"] for p in worker.points], [sfr.POINT_NOT_RUN])
        self.assertNothingLeft(worker)

    def test_a_failed_point_is_reported_not_retried_and_the_others_kept(self):
        model = sm.load_solid_inp(self.request().inp_path)
        forward = ss.SolidForwardModel(model)
        real = forward.solve
        calls = []

        def flaky(*args, **kwargs):
            calls.append(kwargs["e1"])
            if len(calls) == 2:
                raise ss.SolidSolverError("synthetic ARPACK failure")
            return real(*args, **kwargs)

        events = []
        with mock.patch.object(forward, "solve", side_effect=flaky):
            sfr.solve_points(forward, THREE, 14, 4, events.append)
        self.assertEqual(calls, [70000.0, 60000.0, 90000.0])  # each point once, in order: no retry
        points = [e["point"] for e in events if e["event"] == "point"]
        self.assertEqual([p["status"] for p in points], ["SOLVED", "FAILED", "SOLVED"])
        self.assertIn("synthetic ARPACK failure", points[1]["error"]["message"])
        calls.clear()
        events.clear()

        def exhausted(*args, **kwargs):
            calls.append(kwargs["e1"])
            if len(calls) == 2:
                raise ss.ResourceLimitExceeded("synthetic limit")
            return real(*args, **kwargs)

        with mock.patch.object(forward, "solve", side_effect=exhausted):
            reuse = sfr.solve_points(forward, THREE, 14, 4, events.append)
        self.assertEqual(calls, [70000.0, 60000.0])  # a resource limit stops the remaining points
        self.assertEqual(reuse["points_attempted"], 2)

    @WINDOWS_ONLY
    def test_partial_completion_is_reported_honestly(self):
        outcome = self.fake_run("points", points=THREE)
        self.assertEqual(outcome.status, sfr.PARTIAL)
        self.assertEqual([p["status"] for p in outcome.points], ["SOLVED", "FAILED", "NOT_RUN"])
        self.assertIn("1 of 3 What-If points solved", outcome.message)
        self.assertIn("point 2 FAILED (RIGID_BODY_CLASSIFICATION_FAILED", outcome.message)
        self.assertIn("point 3 NOT_RUN", outcome.message)
        self.assertIn("Nothing was retried", outcome.message)
        self.assertEqual(outcome.points[2]["parameters"], dict(zip(sfr.WHATIF_PARAMETERS, THREE[2])))
        self.assertNothingLeft(outcome)

    @WINDOWS_ONLY
    def test_cancel_and_memory_stop_keep_the_completed_points(self):
        cancel = threading.Event()

        def progress(event):
            if event.get("stage") == "point 1 SOLVED":
                cancel.set()

        outcome = self.fake_run("point_then_wait", points=THREE, progress=progress, cancel=cancel)
        self.assertEqual(outcome.status, sfr.CANCELLED)
        self.assertEqual([p["status"] for p in outcome.points], ["SOLVED", "NOT_RUN", "NOT_RUN"])
        self.assertIn("1 of 3 What-If points had been solved", outcome.message)
        self.assertNothingLeft(outcome)
        memory = self.fake_run("point_then_memory", points=THREE)
        self.assertEqual(memory.status, sfr.FAILED)
        self.assertIn("MEMORY_LIMIT", memory.message)
        self.assertEqual([p["status"] for p in memory.points], ["SOLVED", "NOT_RUN", "NOT_RUN"])
        self.assertNothingLeft(memory)
        refused = sfr.run(sfr.ForwardRequest(self.request().inp_path, self.request().inp_sha256, points=THREE),
                          sfr.RunnerLimits(max_job_memory_bytes=10_000))
        self.assertEqual(refused.status, sfr.REFUSED)  # the memory decision covers What-If runs as well
        self.assertIsNone(refused.launcher_pid)
        self.assertEqual([p["status"] for p in refused.points], [sfr.POINT_NOT_RUN] * 3)
        self.assertIn("No What-If point was solved", refused.message)
        early = threading.Event()
        early.set()  # cancelled before the worker starts: still one NOT_RUN record per requested point
        before = sfr.run(sfr.ForwardRequest(self.request().inp_path, self.request().inp_sha256, points=THREE),
                         cancel=early)
        self.assertEqual(before.status, sfr.CANCELLED)
        self.assertEqual([p["index"] for p in before.points], [1, 2, 3])
        self.assertEqual([p["status"] for p in before.points], [sfr.POINT_NOT_RUN] * 3)
        self.assertEqual(before.label, sfr.WHATIF_LABEL)

    @WINDOWS_ONLY
    def test_a_real_what_if_run_can_be_cancelled(self):
        cancel = threading.Event()
        base = self.request()

        def progress(event):
            if event.get("stage") == "point 2 of 3":
                cancel.set()

        outcome = sfr.run(sfr.ForwardRequest(base.inp_path, base.inp_sha256, points=THREE), progress=progress,
                          cancel=cancel)
        self.assertIn(outcome.status, (sfr.CANCELLED, sfr.SOLVED))  # the tiny model may finish first
        self.assertEqual(len(outcome.points), 3)
        if outcome.status == sfr.CANCELLED:
            self.assertEqual(outcome.points[0]["status"], sfr.POINT_SOLVED)
            self.assertEqual(outcome.points[2]["status"], sfr.POINT_NOT_RUN)
        self.assertNothingLeft(outcome)


# WINDOWS-PREVIEW-01-SOLID-WORKER-FIX: what the packaged program's entry script does, with a Python process standing in
# for the packaged program: the standard streams of the interpreter are taken away (a windowed program must not rely on
# them), the worker question is asked first, and a start that is no worker invocation "opens the interface" (it waits).
STAND_IN = textwrap.dedent('''
    import sys, time
    sys.path.insert(0, {src!r})
    sys.stdin = sys.stdout = sys.stderr = None
    from services.solid_forward_runner import frozen_worker_dispatch
    code = frozen_worker_dispatch(sys.argv[1:])
    if code is None:
        time.sleep(300)  # the interface
    raise SystemExit(code)
''')


class PackagedWorkerTests(RunnerCase):
    """The packaged program as its own supervised worker: dispatch, request check, pipes, supervision."""

    def setUp(self):
        super().setUp()
        self.stand_in = self.folder / "packaged_stand_in.py"
        self.stand_in.write_text(STAND_IN.format(src=str(ROOT / "src")), encoding="utf-8")
        self.packaged = [sys.executable, str(self.stand_in)]

    def start(self, arguments, request=None):
        pipes = request is not None
        done = subprocess.run(
            self.packaged + list(arguments), input=request if pipes else None,
            stdin=None if pipes else subprocess.DEVNULL,
            stdout=subprocess.PIPE if pipes else subprocess.DEVNULL, timeout=120)
        return done.returncode, [json.loads(line) for line in (done.stdout or b"").splitlines()]

    def test_the_source_command_is_kept_and_the_packaged_program_starts_itself_with_one_argument(self):
        self.assertFalse(sfr.is_frozen())
        self.assertEqual(sfr._child_argv(), [sys.executable, "-m", "services.solid_forward_runner", "--child"])
        with mock.patch.object(sfr.sys, "frozen", True, create=True), \
                mock.patch.object(sfr.sys, "executable", r"X:\Preview\AbaqusModalComparator.exe"):
            self.assertTrue(sfr.is_frozen())
            self.assertEqual(sfr._child_argv(), [r"X:\Preview\AbaqusModalComparator.exe", sfr.WORKER_OPTION])
        self.assertEqual(sfr.WORKER_OPTION, "--solid-forward-worker")

    def test_only_the_exact_worker_argument_is_a_worker_and_every_other_form_is_refused(self):
        solved = AssertionError("a calculation was started")
        with mock.patch.object(sfr, "_child_main", side_effect=solved), \
                mock.patch.object(sfr, "_inherited_pipes", side_effect=solved):
            for ordinary in ([], ["--research"], ["C:\\data\\plate.mcproj"], ["--worker"], ["-m", "new_gui"]):
                self.assertIsNone(sfr.frozen_worker_dispatch(ordinary), ordinary)  # the program starts as usual
            for malformed in (["-m", "services.solid_forward_runner", "--child"], ["--child"],
                              [sfr.WORKER_OPTION, "extra"], [sfr.WORKER_OPTION, sfr.WORKER_OPTION],
                              [sfr.WORKER_OPTION + "=1"], ["--research", sfr.WORKER_OPTION],
                              ["services/solid_forward_runner.py"]):
                self.assertTrue(sfr.is_worker_invocation(malformed), malformed)
                self.assertEqual(sfr.frozen_worker_dispatch(malformed), sfr.EXIT_MALFORMED_INVOCATION, malformed)
        with mock.patch.object(sfr, "_child_main", side_effect=solved), \
                mock.patch.object(sfr, "_inherited_pipes", side_effect=sfr.RunnerRefused("no pipe")):
            self.assertEqual(sfr.frozen_worker_dispatch([sfr.WORKER_OPTION]), sfr.EXIT_NO_PIPES)
        streams = [mock.Mock(), mock.Mock()]
        with mock.patch.object(sfr, "_inherited_pipes", return_value=tuple(streams)):
            with mock.patch.object(sfr, "_child_main", return_value=0) as worker:
                self.assertEqual(sfr.frozen_worker_dispatch([sfr.WORKER_OPTION]), 0)
            worker.assert_called_once_with(*streams)  # the inherited pipes, not the interpreter's streams
            with mock.patch.object(sfr, "_child_main", side_effect=RuntimeError("unexpected")):
                self.assertEqual(sfr.frozen_worker_dispatch([sfr.WORKER_OPTION]), sfr.EXIT_WORKER_CRASH)  # never raised
        self.assertEqual(len({sfr.EXIT_MALFORMED_INVOCATION, sfr.EXIT_NO_PIPES, sfr.EXIT_MALFORMED_REQUEST,
                              sfr.EXIT_WORKER_CRASH, 0, 1, 2, 3}), 8)

    def test_a_malformed_request_is_refused_before_anything_is_imported_or_solved(self):
        import io

        good = {"inp_path": "box.inp", "inp_sha256": "0" * 64, "elastic_modes": 14, "guard_modes": 4,
                "max_memory_bytes": 1 << 30, "max_seconds": 60.0, "points": [[1.0, 2.0, 3.0]]}
        self.assertEqual(sfr._read_request(io.StringIO(json.dumps(good) + "\n")), good)
        self.assertEqual(sfr._read_request(io.BytesIO(json.dumps(good).encode() + b"\n")), good)
        bad = ["", "\n", "not json\n", "[1, 2]\n", "{}\n"]
        for key, value in (("inp_path", ""), ("inp_path", 5), ("inp_sha256", "abc"), ("inp_sha256", "G" * 64),
                           ("elastic_modes", 0), ("elastic_modes", "14"), ("elastic_modes", True), ("guard_modes", -1),
                           ("max_memory_bytes", 0), ("max_seconds", 0), ("max_seconds", "60"), ("points", "x"),
                           ("points", [[1.0, 2.0]]), ("points", [[1.0, 2.0, "3"]]), ("points", [[1.0, 2.0, 3.0]] * 4)):
            bad.append(json.dumps(dict(good, **{key: value})) + "\n")
        for missing in good:
            if missing != "points":
                bad.append(json.dumps({k: v for k, v in good.items() if k != missing}) + "\n")
        for line in bad:
            with self.subTest(line=line[:60]):
                with self.assertRaises(sfr.RunnerRefused) as caught:
                    sfr._read_request(io.StringIO(line))
                self.assertIn("Malformed worker request", str(caught.exception))
                out = io.StringIO()
                with mock.patch.object(sm, "load_solid_inp", side_effect=AssertionError("imported a model")), \
                        mock.patch.object(sfr, "sha256_of", side_effect=AssertionError("opened the INP")):
                    self.assertEqual(sfr._child_main(io.StringIO(line), out), sfr.EXIT_MALFORMED_REQUEST)
                events = [json.loads(e) for e in out.getvalue().splitlines()]
                self.assertEqual([e["event"] for e in events], ["hello", "error"])
                self.assertEqual(events[1]["kind"], "MALFORMED_REQUEST")
                self.assertIn("Nothing was solved", events[1]["message"])

    @WINDOWS_ONLY
    def test_the_packaged_single_solve_matches_the_source_worker_and_the_in_process_solver(self):
        request = self.request()
        stages = []
        packaged = sfr.run(request, child_argv=self.packaged + [sfr.WORKER_OPTION],
                           progress=lambda event: stages.append(event.get("stage")))
        self.assertEqual(packaged.status, sfr.SOLVED, packaged.message)
        self.assertTrue(packaged.worker_in_job)
        self.assertGreater(packaged.peak_job_memory_bytes, 0)
        self.assertGreater(packaged.peak_worker_commit_bytes, 0)
        self.assertTrue({"preflight", "worker verified", "import", "assemble stiffness", "factorise"} <= set(stages))
        self.assertNothingLeft(packaged)
        source = sfr.run(request)
        self.assertEqual(source.status, sfr.SOLVED, source.message)
        self.assertEqual(packaged.result["frequencies_hz"], source.result["frequencies_hz"])  # the same lines
        self.assertEqual(packaged.result["material"], source.result["material"])
        direct = ss.SolidForwardModel(sm.load_solid_inp(request.inp_path)).solve(14)
        np.testing.assert_allclose(packaged.result["frequencies_hz"], direct.frequencies_hz, rtol=1e-10)
        self.assertEqual(packaged.result["abaqus_equivalence"], "NOT_VERIFIED")

    @WINDOWS_ONLY
    def test_the_packaged_what_if_route_matches_independent_solves(self):
        base = self.request()
        points = THREE[1:]
        outcome = sfr.run(sfr.ForwardRequest(base.inp_path, base.inp_sha256, points=points),
                          child_argv=self.packaged + [sfr.WORKER_OPTION])
        self.assertEqual(outcome.status, sfr.SOLVED, outcome.message)
        self.assertEqual(outcome.label, sfr.WHATIF_LABEL)
        self.assertTrue(outcome.worker_in_job)
        self.assertEqual([p["status"] for p in outcome.points], [sfr.POINT_SOLVED] * 2)
        for record, (e1, e2, g12) in zip(outcome.points, points):
            independent = ss.SolidForwardModel(sm.load_solid_inp(base.inp_path)).solve(14, e1=e1, e2=e2, g12=g12)
            np.testing.assert_allclose(record["result"]["frequencies_hz"], independent.frequencies_hz, rtol=1e-10)
        self.assertTrue(outcome.result["reuse"]["mass_matrix_reused_for_every_point"])
        self.assertNothingLeft(outcome)

    @WINDOWS_ONLY
    def test_refused_packaged_invocations_end_by_themselves_and_solve_nothing(self):
        code, events = self.start(["-m", "services.solid_forward_runner", "--child"])
        self.assertEqual((code, events), (sfr.EXIT_MALFORMED_INVOCATION, []))
        code, events = self.start([sfr.WORKER_OPTION, "extra"], b"{}\n")
        self.assertEqual((code, events), (sfr.EXIT_MALFORMED_INVOCATION, []))  # not even the identity line
        code, events = self.start([sfr.WORKER_OPTION])  # the null device is not a supervisor's pipe
        self.assertEqual((code, events), (sfr.EXIT_NO_PIPES, []))
        code, events = self.start([sfr.WORKER_OPTION], b"{}\n")
        self.assertEqual(code, sfr.EXIT_MALFORMED_REQUEST)
        self.assertEqual([e["event"] for e in events], ["hello", "error"])
        self.assertEqual(events[1]["kind"], "MALFORMED_REQUEST")
        code, events = self.start([sfr.WORKER_OPTION], b"")  # the supervisor closed the pipe without a request
        self.assertEqual((code, events[-1]["kind"]), (sfr.EXIT_MALFORMED_REQUEST, "MALFORMED_REQUEST"))

    @WINDOWS_ONLY
    def test_a_failed_packaged_request_is_reported_by_the_supervisor_and_nothing_is_left(self):
        base = self.request()
        # the supervisor of the source command given to the packaged program: it ends, it is not taken for a worker
        refused = sfr.run(base, child_argv=self.packaged + ["-m", "services.solid_forward_runner", "--child"],
                          skip_preflight=True)
        self.assertEqual(refused.status, sfr.FAILED)
        self.assertIn(f"ended without a result (exit code {sfr.EXIT_MALFORMED_INVOCATION})", refused.message)
        self.assertIsNone(refused.worker_pid)
        self.assertIsNone(refused.result)
        self.assertNothingLeft(refused)
        # a request the worker does not accept: reported, nothing solved
        malformed = sfr.run(sfr.ForwardRequest(base.inp_path, base.inp_sha256, elastic_modes=0),
                            child_argv=self.packaged + [sfr.WORKER_OPTION], skip_preflight=True)
        self.assertEqual(malformed.status, sfr.FAILED)
        self.assertIn("MALFORMED_REQUEST", malformed.message)
        self.assertIn("Nothing was solved", malformed.message)
        self.assertTrue(malformed.worker_in_job)
        self.assertIsNone(malformed.result)
        self.assertNothingLeft(malformed)
        # a changed INP is refused by the packaged worker as by the source worker
        changed = sfr.run(sfr.ForwardRequest(base.inp_path, "f" * 64), child_argv=self.packaged + [sfr.WORKER_OPTION],
                          skip_preflight=True)
        self.assertEqual(changed.status, sfr.FAILED)
        self.assertIn("changed", changed.message)
        self.assertNothingLeft(changed)
        # a start that is no worker at all (the interface would open) never identifies itself: refused and terminated
        window = sfr.run(base, sfr.RunnerLimits(handshake_seconds=2.0), child_argv=self.packaged, skip_preflight=True)
        self.assertEqual(window.status, sfr.REFUSED)
        self.assertIn("identity could not be established", window.message)
        self.assertNothingLeft(window)

    @WINDOWS_ONLY
    def test_cancelling_a_packaged_run_terminates_it_and_the_limits_still_hold(self):
        cancel = threading.Event()
        base = self.request()

        def progress(event):
            if event.get("stage") == "worker verified":
                cancel.set()

        outcome = sfr.run(sfr.ForwardRequest(base.inp_path, base.inp_sha256, points=THREE), progress=progress,
                          cancel=cancel, child_argv=self.packaged + [sfr.WORKER_OPTION])
        self.assertEqual(outcome.status, sfr.CANCELLED)
        self.assertTrue(outcome.worker_in_job)
        self.assertEqual([p["status"] for p in outcome.points], [sfr.POINT_NOT_RUN] * 3)
        self.assertNothingLeft(outcome)
        limited = sfr.run(base, sfr.RunnerLimits(max_job_memory_bytes=10_000),
                          child_argv=self.packaged + [sfr.WORKER_OPTION])
        self.assertEqual(limited.status, sfr.REFUSED)  # the memory decision is taken before any worker starts
        self.assertIsNone(limited.launcher_pid)


class UnsupportedPlatformTests(RunnerCase):
    """ABM-AUD-2: without Windows job objects there is no supervision, so nothing is solved. The refusal is said, no
    process is started and no unsupervised fallback exists. These run on every platform."""

    def refuse(self):
        raise sfr.RunnerRefused("Supervised solid solves need Windows job objects; this platform is not supported.")

    def test_the_kernel_interface_is_refused_off_windows(self):
        with mock.patch.object(sfr.os, "name", "posix"):
            with self.assertRaises(sfr.RunnerRefused) as caught:
                sfr._kernel32()
        self.assertIn("need Windows job objects; this platform is not supported", str(caught.exception))
        if sys.platform != "win32":  # the real thing, not a patched name
            for call in (sfr.available_memory_bytes, sfr.own_peak_commit_bytes, lambda: sfr.process_alive(os.getpid())):
                with self.assertRaises(sfr.RunnerRefused):
                    call()

    def test_a_run_without_job_objects_is_refused_and_starts_no_process(self):
        request = self.request()
        started = AssertionError("a worker process was started without supervision")
        for points, skip in (((), False), (THREE, False), ((), True), (THREE, True)):
            with self.subTest(points=len(points), skip_preflight=skip),                     mock.patch.object(sfr, "_kernel32", side_effect=self.refuse),                     mock.patch.object(sfr.subprocess, "Popen", side_effect=started):
                outcome = sfr.run(sfr.ForwardRequest(request.inp_path, request.inp_sha256, points=points),
                                  child_argv=[sys.executable, str(self.fake), "quiet"], skip_preflight=skip)
            self.assertEqual(outcome.status, sfr.REFUSED)
            self.assertIn("this platform is not supported", outcome.message)
            self.assertIsNone(outcome.launcher_pid)
            self.assertIsNone(outcome.worker_pid)
            self.assertFalse(outcome.worker_in_job)
            self.assertIsNone(outcome.result)
            self.assertEqual([p["status"] for p in outcome.points], [sfr.POINT_NOT_RUN] * len(points))
            if points:
                self.assertIn("No What-If point was solved", outcome.message)

    def test_the_preflight_is_refused_too(self):
        request = self.request()
        with mock.patch.object(sfr, "_kernel32", side_effect=self.refuse):
            with self.assertRaises(sfr.RunnerRefused) as caught:
                sfr.preflight(request)
        self.assertIn("this platform is not supported", str(caught.exception))

    def test_the_windows_only_marker_names_itself(self):
        self.assertTrue(WINDOWS_ONLY_REASON.startswith("SKIPPED_WINDOWS_ONLY"))


if __name__ == "__main__":
    unittest.main()
