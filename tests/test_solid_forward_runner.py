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


THREE = ((70000.0, 20000.0, 9000.0), (60000.0, 25000.0, 7000.0), (90000.0, 15000.0, 11000.0))


class WhatIfTests(RunnerCase):
    """ABM-SOLID-6: manual E1/E2/G12 points, synthetic models only."""

    def independent(self, path, point):
        """A fresh import and a fresh forward model for one point: nothing is shared with the What-If run."""
        e1, e2, g12 = point
        return ss.SolidForwardModel(sm.load_solid_inp(path)).solve(14, e1=e1, e2=e2, g12=g12).frequencies_hz

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


if __name__ == "__main__":
    unittest.main()
