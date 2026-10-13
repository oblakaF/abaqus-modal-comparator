"""Quick calibration P1b-A: a hard per-run cap on NEW Abaqus FE solve attempts (FakeAbaqus only).

The cap covers the whole workflow (baseline, optimiser, final evaluation, central-difference sensitivities). It is
enforced in ``QuickCalibration.fe_state`` immediately before the solver is called; a failed attempt counts, a reused
finished job does not. A reached cap ends the run as an explicit BUDGET_EXHAUSTED refusal: no further solve, no
calibrated value, no calibrated INP. The LM evaluation budget stays separate.

Synthetic one-parameter profile (unlimited): baseline 1, optimiser 3, final evaluation 0 (the optimiser's own point,
reused), sensitivities 2 - six new solves in total.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import quick_calibration_support as S  # noqa: E402
from services import quick_calibration as qc  # noqa: E402
from services.quick_calibration import (  # noqa: E402
    BUDGET_EXHAUSTED,
    DEFAULT_MAX_NEW_FE_SOLVES,
    STATUS_ESTIMATE,
    STATUS_REFUSED,
    FESolveBudgetExhausted,
    QuickCalibration,
    QuickCalibrationError,
    config_from_dict,
    config_template,
    run_quick_calibration,
)
from test_quick_calibration import E_FACE, _identity_orientation  # noqa: E402

FULL_RUN = {"baseline": 1, "optimiser": 3, "sensitivities": 2}


class CountingAbaqus(S.FakeAbaqus):
    """FakeAbaqus that records every solver call and can fail chosen calls."""

    def __init__(self, fail_calls=()) -> None:
        super().__init__()
        self.calls = 0
        self.fail_calls = set(fail_calls)

    def solve(self, inp_path, job_dir, job_name):
        self.calls += 1
        if self.calls in self.fail_calls:
            raise QuickCalibrationError(f"Abaqus job {job_name} did not complete (simulated failure)")
        return super().solve(inp_path, job_dir, job_name)


class _Case(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp(prefix="qc_p1b_"))
        cls.orientation = _identity_orientation(cls.root / "probe")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="case_", dir=self.root))
        (self.folder / "model.inp").write_text(S.INP)
        S.write_experiment(self.folder / "exp.unv", 0.9 * S.E0, S.G0, noise=0.001)

    def config(self, limit, **extra):
        data = {"model_inp": "model.inp", "experiment": "exp.unv", "output_dir": "out",
                "orientation_candidate_id": self.orientation, "parameters": [E_FACE], "max_new_fe_solves": limit}
        data.update(extra)
        return config_from_dict(data, self.folder)

    def run_with(self, limit, fake=None, **extra):
        fake = fake or CountingAbaqus()
        result, paths = run_quick_calibration(self.config(limit, **extra), fake.solve, fake.extract)
        return result, paths, fake

    def assert_exhausted(self, result, paths, fake, limit, stage):
        self.assertEqual(result["status"], STATUS_REFUSED)
        self.assertEqual(result["refusal_code"], BUDGET_EXHAUSTED)
        self.assertEqual(result["budget_exhausted_stage"], stage)
        self.assertIn(BUDGET_EXHAUSTED, result["refusal_reasons"][0])
        self.assertLessEqual(fake.calls, limit)  # the solver is never called beyond the cap
        budget = result["fe_solve_budget"]
        self.assertEqual((budget["max_new_fe_solves"], budget["attempted_new_solves"]), (limit, fake.calls))
        self.assertEqual(budget["completed_new_solves"], fake.solves)
        self.assertEqual(result["estimates"], {})  # no calibrated value ...
        self.assertIsNone(result.get("diagnostic_candidate"))
        self.assertNotIn("calibrated_inp", paths)  # ... and no calibrated INP
        self.assertFalse(any(Path(self.folder / "out").glob("*_calibrated.inp")))
        self.assertNotIn("last_point", result.get("lm", {}))  # the optimiser point is withheld
        self.assertNotIn("history", result.get("lm", {}))
        report = Path(paths["report"]).read_text(encoding="utf-8")
        self.assertIn(f"RESULT: NO VALUE ({BUDGET_EXHAUSTED})", report)
        self.assertIn(f"{fake.calls} attempted, {fake.solves} completed, limit {limit}", report)
        self.assertNotIn("multiplier", json.dumps(result["evaluations"]))


# ----------------------------------------------------------------------------- the whole workflow is capped

class WorkflowTests(_Case):
    def test_unlimited_profile_and_reporting(self):
        result, paths, fake = self.run_with(100)
        self.assertEqual(result["status"], STATUS_ESTIMATE)
        self.assertEqual(result["fe_solve_budget"]["attempts_by_stage"], FULL_RUN)
        self.assertEqual(fake.calls, sum(FULL_RUN.values()))
        self.assertIn("calibrated_inp", paths)

    def test_exhaustion_during_the_optimiser(self):
        result, paths, fake = self.run_with(2)
        self.assert_exhausted(result, paths, fake, 2, "optimiser")
        self.assertEqual(fake.calls, 2)
        self.assertEqual(result["fe_solve_budget"]["attempts_by_stage"], {"baseline": 1, "optimiser": 1})

    def test_exhaustion_immediately_after_convergence(self):
        result, paths, fake = self.run_with(4)  # baseline + the three optimiser solves: none left afterwards
        self.assert_exhausted(result, paths, fake, 4, "sensitivities")
        self.assertEqual(result["lm"]["status"], "CONVERGED")  # converged, yet no value without sensitivities
        self.assertEqual(fake.calls, 4)

    def test_exhaustion_during_the_central_differences(self):
        result, paths, fake = self.run_with(5)
        self.assert_exhausted(result, paths, fake, 5, "sensitivities")
        self.assertEqual(result["fe_solve_budget"]["attempts_by_stage"]["sensitivities"], 1)

    def test_exhaustion_at_the_final_evaluation(self):
        original = qc.run_bounded_lm

        def lm_then_forget(evaluate, start, bounds, settings):
            outcome = original(evaluate, start, bounds, settings)
            calibration = evaluate.__self__  # force a new solve for the final evaluation
            calibration._cache.clear()
            job = qc._job_name(calibration.model.render(dict(outcome.parameters)))
            shutil.rmtree(calibration.work / job)
            return outcome

        with mock.patch.object(qc, "run_bounded_lm", side_effect=lm_then_forget):
            result, paths, fake = self.run_with(4)
        self.assert_exhausted(result, paths, fake, 4, "final evaluation")

    def test_exhaustion_before_a_failing_solver_attempt(self):
        fake = CountingAbaqus(fail_calls={2})  # the second solve would fail: it must never be launched
        result, paths, _ = self.run_with(1, fake)
        self.assert_exhausted(result, paths, fake, 1, "optimiser")
        self.assertEqual(fake.calls, 1)

    def test_the_lm_evaluation_budget_stays_separate(self):
        result, _, fake = self.run_with(100, solve_budget=3)  # LM budget, not the FE cap
        self.assertNotEqual(result.get("refusal_code"), BUDGET_EXHAUSTED)
        self.assertLess(fake.calls, 100)


# ----------------------------------------------------------------------------- counting

class CountingTests(_Case):
    def test_a_failed_attempt_consumes_the_budget(self):
        fake = CountingAbaqus(fail_calls={1})
        calibration = QuickCalibration(self.config(2), fake.solve, fake.extract)
        with self.assertRaises(QuickCalibrationError):
            calibration.fe_state({"E_face": 1.0})
        self.assertEqual((calibration.new_solve_attempts, calibration.abaqus_solves), (1, 0))
        calibration.fe_state({"E_face": 1.1})
        with self.assertRaises(FESolveBudgetExhausted) as caught:
            calibration.fe_state({"E_face": 1.2})
        self.assertEqual(fake.calls, 2)  # the third solve was never invoked
        self.assertEqual((caught.exception.attempted, caught.exception.completed, caught.exception.limit), (2, 1, 2))
        self.assertFalse((calibration.work / qc._job_name(calibration.model.render({"E_face": 1.2}))).exists())

    def test_reused_finished_jobs_do_not_consume_the_budget(self):
        first, _, _ = self.run_with(100)
        self.assertEqual(first["status"], STATUS_ESTIMATE)
        again, paths, fake = self.run_with(1)  # every job is finished: nothing new is solved
        self.assertEqual(again["status"], STATUS_ESTIMATE)
        self.assertEqual(fake.calls, 0)
        self.assertEqual(again["fe_solve_budget"]["attempted_new_solves"], 0)
        self.assertGreaterEqual(again["fe_solve_budget"]["reused_finished_jobs"], sum(FULL_RUN.values()))
        self.assertIn("calibrated_inp", paths)

    def test_partially_reused_jobs(self):
        self.run_with(100)
        jobs = sorted((self.folder / "out" / "work").iterdir())
        shutil.rmtree(jobs[0])
        _, _, fake = self.run_with(1)  # one finished job is missing: exactly one new solve
        self.assertEqual(fake.calls, 1)
        for job in sorted((self.folder / "out" / "work").iterdir())[:2]:
            shutil.rmtree(job)
        result, paths, fake = self.run_with(1)  # two are missing, one may be solved: refused
        self.assert_exhausted(result, paths, fake, 1, result["budget_exhausted_stage"])
        self.assertEqual(fake.calls, 1)


# ----------------------------------------------------------------------------- configuration, CLI, window

class ConfigurationTests(_Case):
    def test_finite_default_and_validation(self):
        self.assertEqual(DEFAULT_MAX_NEW_FE_SOLVES, 24)
        data = {"model_inp": "model.inp", "experiment": "exp.unv", "output_dir": "out", "parameters": [E_FACE]}
        self.assertEqual(config_from_dict(data, self.folder).max_new_fe_solves, DEFAULT_MAX_NEW_FE_SOLVES)
        self.assertEqual(config_template()["max_new_fe_solves"], DEFAULT_MAX_NEW_FE_SOLVES)
        self.assertEqual(config_from_dict(dict(data, max_new_fe_solves="7"), self.folder).max_new_fe_solves, 7)
        for value in (None, 0, -1, 1.5, "inf", float("inf"), float("nan"), True, "", "many"):
            with self.subTest(value=value), self.assertRaises(QuickCalibrationError):
                config_from_dict(dict(data, max_new_fe_solves=value), self.folder)
        with self.assertRaises(QuickCalibrationError):
            qc.QuickCalibrationConfig(Path("a.inp"), Path("b.unv"), (qc.ParameterSpec("k", "m", ("E",)),), Path("o"),
                                      max_new_fe_solves=None)

    def test_preflight_reports_the_cap(self):
        report = qc.preflight(self.config(2))
        abaqus = next(c for c in report.checks if c.item == "Abaqus")
        self.assertIn("at most 2 new FE solve(s) in this run", abaqus.detail)
        low = next(c for c in report.checks if c.item == "FE solve budget")
        self.assertIn("BUDGET_EXHAUSTED", low.detail)
        self.assertTrue(report.ready)  # informative: reusable jobs may still make it possible

    def test_cli_flag(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import quick_calibration as tool

        self.assertEqual(tool.DEFAULT_MAX_NEW_FE_SOLVES, DEFAULT_MAX_NEW_FE_SOLVES)
        common = ["quick", "--inp", str(self.folder / "model.inp"), "--unv", str(self.folder / "exp.unv"),
                  "--material", "CFRP_Face", "--out", str(self.folder / "out"), "--check-only"]
        for flag, expected_code, text in ((["--max-new-fe-solves", "3"], 0, "at most 3 new FE solve(s)"),
                                          ([], 0, f"at most {DEFAULT_MAX_NEW_FE_SOLVES} new FE solve(s)"),
                                          (["--max-new-fe-solves", "0"], 2, "finite positive integer")):
            out, err = io.StringIO(), io.StringIO()
            with self.subTest(flag=flag), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = tool.main(common + flag)
            self.assertEqual(code, expected_code)
            self.assertIn(text, out.getvalue() + err.getvalue())

    def test_window_field(self):
        try:
            import tkinter as tk

            root = tk.Tk()
        except Exception as error:  # noqa: BLE001
            self.skipTest(f"Tk is unavailable: {error}")
        self.addCleanup(root.destroy)
        root.withdraw()
        import quick_calibration_window as qw

        fake = CountingAbaqus()
        window = qw.QuickCalibrationWindow(root, fake.solve, fake.extract, threaded=False)
        self.assertEqual(window.max_new_fe_solves.get(), str(DEFAULT_MAX_NEW_FE_SOLVES))
        window.set_inp(str(self.folder / "model.inp"))
        window.unv.set(str(self.folder / "exp.unv"))
        window.out.set(str(self.folder / "out"))
        window.orientation_ids = {"identity": self.orientation}
        window.orientation.set("identity")
        window.max_new_fe_solves.set("0")
        with mock.patch.object(qw.messagebox, "showerror") as error:
            window.start()
        error.assert_called_once()
        self.assertIn("finite positive integer", error.call_args[0][1])
        self.assertEqual(fake.calls, 0)
        window.max_new_fe_solves.set("2")
        window.start()
        self.assertTrue(window.summary.get().startswith(f"NO VALUE: {BUDGET_EXHAUSTED}"), window.summary.get())
        self.assertEqual(fake.calls, 2)
        self.assertEqual(json.loads((self.folder / "out" / "config.json").read_text())["max_new_fe_solves"], "2")


if __name__ == "__main__":
    unittest.main()
