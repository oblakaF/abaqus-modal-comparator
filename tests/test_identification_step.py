"""M4.8 bounded LM / trust step (SPEC §6 S4, §8): analytic models only, no solver."""

from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from services.branch_tracker import BranchTrackingRefusal, RefusalKind
from services.identification_step import (
    LMSettings,
    LMStatus as S,
    StepError,
    broyden_update,
    lm_step,
    local_sd,
    objective,
    parameter_bounds,
    run_bounded_lm,
)


NAMES = ("E_in_plane_mpa", "G12_mpa")
BOUNDS = parameter_bounds([("E_in_plane_mpa", 20000.0, 120000.0), ("G12_mpa", 1000.0, 12000.0)])
START = {"E_in_plane_mpa": 52000.0, "G12_mpa": 4500.0}
TRUTH = {"E_in_plane_mpa": 45000.0, "G12_mpa": 4000.0}
# Sandwich-like log-sensitivities of six branches to (E, G12); G12 weaker, as in CARBON-5A.
EXPONENTS = np.array([[0.48, 0.02], [0.45, 0.05], [0.40, 0.10], [0.30, 0.20], [0.46, 0.04], [0.35, 0.15]])
SIGMA = 0.003


def frequencies(p):
    x = np.log([p["E_in_plane_mpa"], p["G12_mpa"]])
    return np.exp(np.log(np.linspace(70.0, 260.0, len(EXPONENTS))) + EXPONENTS @ (x - np.log([52000.0, 4500.0])))


def residual_function(experiment, nonlinear=0.0, calls=None):
    def evaluate(p):
        if calls is not None:
            calls.append(dict(p))
        x = np.log([p["E_in_plane_mpa"], p["G12_mpa"]]) - np.log([52000.0, 4500.0])
        model = np.log(frequencies(p)) + nonlinear * np.sin(4.0 * x[0]) * np.ones(len(EXPONENTS))
        return (model - np.log(experiment)) / SIGMA
    return evaluate


def settings(**changes):
    values = dict(mu_initial=1e-3, mu_decrease=10.0, max_step_attempts=4, solve_budget=20)
    values.update(changes)
    return LMSettings(**values)


class StepTests(unittest.TestCase):
    def test_step_is_a_descent_direction(self):
        jacobian = EXPONENTS / SIGMA
        r = np.array([1.0, 2.0, -0.5, 0.3, 1.1, 0.2])
        step = lm_step(r, jacobian, 1e-3)
        gradient = jacobian.T @ r  # ∇Φ
        self.assertLess(float(gradient @ step), 0.0)  # the minus sign is present
        self.assertLess(objective(r + jacobian @ step), objective(r))

    def test_zero_sensitivity_is_refused(self):
        with self.assertRaises(StepError):
            lm_step(np.ones(3), np.array([[1.0, 0.0], [2.0, 0.0], [1.0, 0.0]]), 1e-3)

    def test_broyden_secant_condition(self):
        jacobian = np.array([[1.0, 0.5], [0.2, 1.0], [0.3, 0.1]])
        step, change = np.array([0.1, -0.05]), np.array([0.2, 0.0, 0.1])
        updated = broyden_update(jacobian, step, change)
        np.testing.assert_allclose(updated @ step, change, atol=1e-15)

    def test_local_sd(self):
        jacobian = np.diag([2.0, 4.0])
        np.testing.assert_allclose(local_sd(jacobian), [0.5, 0.25])


class LoopTests(unittest.TestCase):
    def test_synthetic_recovery_within_budget(self):
        noise = 1.0 + 0.003 * np.random.default_rng(11).standard_normal(len(EXPONENTS))
        experiment = frequencies(TRUTH) * noise
        result = run_bounded_lm(residual_function(experiment), START, BOUNDS, settings())
        self.assertIs(result.status, S.CONVERGED)
        self.assertLessEqual(result.solves, 20)
        sd = np.array(result.local_sd)
        error = np.abs(np.log([result.parameters[n] for n in NAMES]) - np.log([TRUTH[n] for n in NAMES]))
        self.assertTrue(np.all(error <= sd), (error, sd))  # within 1σ

    def test_exact_data_recover_the_truth(self):
        result = run_bounded_lm(residual_function(frequencies(TRUTH)), START, BOUNDS, settings())
        self.assertIs(result.status, S.CONVERGED)
        # Converged: the remaining step is below 0.2·sd, so the distance to the exact optimum is too.
        error = np.abs(np.log([result.parameters[n] / TRUTH[n] for n in NAMES]))
        self.assertTrue(np.all(error <= 0.2 * np.array(result.local_sd)), (error, result.local_sd))

    def test_finite_differences_use_five_percent_in_ln_p(self):
        calls = []
        run_bounded_lm(residual_function(frequencies(TRUTH), calls=calls), START, BOUNDS,
                       settings(solve_budget=3))
        self.assertEqual(len(calls), 3)  # r(x0), then ±5 % for E (the budget stops before G12)
        self.assertAlmostEqual(calls[1]["E_in_plane_mpa"], 52000.0 * 1.05)
        self.assertAlmostEqual(calls[2]["E_in_plane_mpa"], 52000.0 * 0.95)
        self.assertEqual(calls[1]["G12_mpa"], 4500.0)

    def test_bounds_are_respected(self):
        tight = parameter_bounds([("E_in_plane_mpa", 48000.0, 60000.0), ("G12_mpa", 1000.0, 12000.0)])
        calls = []
        result = run_bounded_lm(residual_function(frequencies(TRUTH), calls=calls), START, tight, settings())
        self.assertGreaterEqual(min(call["E_in_plane_mpa"] for call in calls[3:]), 48000.0 * (1 - 1e-12))
        self.assertAlmostEqual(result.parameters["E_in_plane_mpa"], 48000.0, places=6)

    def test_rejected_step_increases_mu_and_refreshes_the_jacobian(self):
        # Solves: 1 = r(x0), 2-5 = finite differences, 6 = first trial (accepted, Broyden update),
        # 7 = second trial, forced worse → rejected: μ × 10 and, because J was Broyden-updated,
        # finite differences are repeated (8-11) around the accepted point before the next trial.
        calls = []
        inner = residual_function(frequencies(TRUTH), calls=calls)

        def evaluate(p):
            values = inner(p)
            return values * 100.0 if len(calls) == 7 else values

        result = run_bounded_lm(evaluate, START, BOUNDS, settings(mu_initial=1.0, mu_decrease=1.0, solve_budget=40))
        rejected = [h for h in result.history if h.trial_objective is not None and not h.accepted]
        self.assertEqual(len(rejected), 1)
        index = result.history.index(rejected[0])
        self.assertAlmostEqual(result.history[index + 1].mu, rejected[0].mu * 10.0)
        accepted_point = calls[5]
        self.assertAlmostEqual(calls[7]["E_in_plane_mpa"], accepted_point["E_in_plane_mpa"] * 1.05)
        self.assertAlmostEqual(calls[8]["E_in_plane_mpa"], accepted_point["E_in_plane_mpa"] * 0.95)
        self.assertAlmostEqual(calls[9]["G12_mpa"], accepted_point["G12_mpa"] * 1.05)
        objectives = [h.objective_before for h in result.history]
        self.assertTrue(all(b <= a + 1e-12 for a, b in zip(objectives, objectives[1:])))  # Φ never increases

    def test_finite_difference_points_are_exact(self):
        calls = []
        run_bounded_lm(residual_function(frequencies(TRUTH), calls=calls), START, BOUNDS, settings(solve_budget=5))
        self.assertEqual(calls[0], START)  # p0 itself, not exp(ln p0)
        self.assertEqual([c["E_in_plane_mpa"] for c in calls[1:3]], [54600.0, 49400.0])  # the CARBON-5A E± points
        self.assertEqual([c["G12_mpa"] for c in calls[3:5]], [4725.0, 4275.0])  # the CARBON-5A G± points

    def test_branch_loss_stops_the_loop_as_refused(self):
        calls = []
        inner = residual_function(frequencies(TRUTH), calls=calls)

        def evaluate(p):
            if len(calls) == 4:
                raise BranchTrackingRefusal(RefusalKind.BRANCH_LOSS, ("R3: best FE-to-FE MAC 0.61 < 0.9",))
            return inner(p)

        result = run_bounded_lm(evaluate, START, BOUNDS, settings())
        self.assertIs(result.status, S.REFUSED)
        self.assertIn("BRANCH_LOSS", result.refusal)
        self.assertEqual(len(calls), 4)  # no further solves, no re-pairing
        self.assertEqual(result.parameters, START)  # the refused trial is never accepted

    def test_budget_and_iteration_limits(self):
        result = run_bounded_lm(residual_function(frequencies(TRUTH)), START, BOUNDS, settings(solve_budget=5))
        self.assertIs(result.status, S.SOLVE_BUDGET)
        self.assertEqual(result.solves, 5)
        slow = run_bounded_lm(residual_function(frequencies(TRUTH)), START, BOUNDS,
                              settings(mu_initial=50.0, mu_decrease=1.0, solve_budget=100))
        self.assertIs(slow.status, S.MAX_ITERATIONS)
        self.assertEqual(slow.iterations, 5)

    def test_settings_and_bounds_validation(self):
        for changes in ({"mu_initial": 0.0}, {"mu_decrease": 0.5}, {"solve_budget": 0}, {"max_iterations": True},
                        {"finite_difference_step": 1.5}, {"mu_increase": 1.0}):
            with self.subTest(changes=changes), self.assertRaises(StepError):
                settings(**changes)
        self.assertEqual((LMSettings(1e-3, 10.0, 4, 20).max_iterations, LMSettings(1e-3, 10.0, 4, 20).stop_fraction),
                         (5, 0.2))
        with self.assertRaises(StepError):
            parameter_bounds([("E", 10.0, 5.0)])
        with self.assertRaises(StepError):
            run_bounded_lm(residual_function(frequencies(TRUTH)), {"E_in_plane_mpa": 5000.0, "G12_mpa": 4500.0},
                           BOUNDS, settings())
        with self.assertRaises(StepError):
            run_bounded_lm(residual_function(frequencies(TRUTH)), {"E_in_plane_mpa": 52000.0}, BOUNDS, settings())


if __name__ == "__main__":
    unittest.main()
