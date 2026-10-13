"""Audit 2026-10-13, findings K1-K4 and V2: a scientific refusal must stay a refusal.

K1  an estimate on a solver-only search bound is never released;
V2  a parameter held on a bound does not give the free parameters a false convergence;
K3  the provisional Σ_setup is fixed at 0.003 (SPEC §7); MEASURED needs evidence the schema cannot carry yet;
K4  the SPEC LM constants (stop fraction, iterations, μ increase, finite-difference step) are not campaign choices.
    Synthetic test campaigns may still change them to exercise the gates, but such a campaign releases nothing and
    the production CLI refuses to execute it.
K2  (gross FIT residuals vs. the D-043 pattern test) is a policy decision and is not changed here.
"""

from __future__ import annotations

import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.campaign_definition import CampaignDefinitionError, parse_campaign_definition  # noqa: E402
from services.identification_step import LMSettings, LMStatus, parameter_bounds, run_bounded_lm  # noqa: E402


def _power_law_problem():
    rng = np.random.default_rng(0)
    n = 8
    c, a, b = rng.uniform(50, 300, n), rng.uniform(0.15, 0.5, n), rng.uniform(0.0, 0.3, n)
    sigma = 0.003

    def f(p):
        return c * (p["E"] / 50000.0) ** a * (p["G"] / 4000.0) ** b

    f_exp = f({"E": 55000.0, "G": 4200.0}) * np.exp(rng.normal(0.0, sigma, n))

    def residuals(p):
        return (np.log(f(p)) - np.log(f_exp)) / sigma

    return residuals, a, b, c, f_exp, sigma


SETTINGS = LMSettings(mu_initial=1e-3, mu_decrease=10.0, max_step_attempts=3, solve_budget=60)


class LMBoundTests(unittest.TestCase):
    def test_interior_optimum_still_converges(self):
        residuals, *_ = _power_law_problem()
        result = run_bounded_lm(residuals, {"E": 45000.0, "G": 6000.0},
                                parameter_bounds([("E", 20000, 120000), ("G", 1000, 20000)]), SETTINGS)
        self.assertIs(result.status, LMStatus.CONVERGED)

    def test_single_parameter_on_bound_is_not_converged(self):
        residuals, *_ = _power_law_problem()

        def only_e(p):
            return residuals({"E": p["E"], "G": 4200.0})

        result = run_bounded_lm(only_e, {"E": 62000.0}, parameter_bounds([("E", 60000, 120000)]), SETTINGS)
        self.assertIs(result.status, LMStatus.AT_BOUND)
        self.assertAlmostEqual(result.parameters["E"], 60000.0)

    def test_free_parameter_reaches_its_conditional_optimum(self):
        residuals, a, b, c, f_exp, sigma = _power_law_problem()
        result = run_bounded_lm(residuals, {"E": 45000.0, "G": 6000.0},
                                parameter_bounds([("E", 20000, 52000), ("G", 1000, 20000)]), SETTINGS)
        self.assertIs(result.status, LMStatus.AT_BOUND)
        self.assertAlmostEqual(result.parameters["E"], 52000.0)
        # conditional least-squares optimum of ln G with E held at 52000 (the model is linear in ln p)
        y = np.log(f_exp) - np.log(c) - a * math.log(52000.0 / 50000.0)
        ln_g = math.log(4000.0) + float(b @ y) / float(b @ b)
        sd_g = sigma / math.sqrt(float(b @ b))
        self.assertLess(abs(math.log(result.parameters["G"]) - ln_g), 0.2 * sd_g + 1e-9)


class CampaignBoundReleaseTests(unittest.TestCase):
    def test_bound_estimate_is_not_released(self):
        from services.identification_campaign_run import CampaignRun, CampaignRunConfig, build_campaign_report
        from test_m7_campaign import FakeExtractor, FakeSolver, synthetic_definition, synthetic_specimen

        definition = parse_campaign_definition(synthetic_definition(bounds={"E_in_plane_mpa": [50000.0, 104000.0]}))
        tmp = Path(tempfile.mkdtemp())
        a, store = synthetic_specimen(definition, "A", tmp, 48000.0)
        b, _ = synthetic_specimen(definition, "B", tmp, 48000.0)
        config = CampaignRunConfig(tmp / "runs", {"synthetic": store}, "abq2024.bat", FakeSolver(), FakeExtractor(),
                                   {}, "m" * 64)
        run = CampaignRun(definition, [a, b], "m" * 64, config)
        result = run.run()
        report = build_campaign_report(definition, run.specimens, run.journal.records("evaluation"), result)
        self.assertEqual(result["status"], LMStatus.AT_BOUND.value)
        self.assertEqual(report["formal_output"]["released_values"], {})
        self.assertNotEqual(report["formal_output"]["status"], "VALUES_RELEASED")
        self.assertEqual(report["material_claim"], "NO_MATERIAL_PROPERTY_CLAIM")


class CampaignConstantsTests(unittest.TestCase):
    @staticmethod
    def _definition(**changes):
        from test_m7_campaign import synthetic_definition
        return parse_campaign_definition(synthetic_definition(**changes))

    def _sigma(self, sd, status="PROVISIONAL"):
        return self._definition(sigma={"setup": {"sd_ln": sd, "status": status, "source": "x"},
                                       "measurement": {"status": "NOT_AVAILABLE", "source": "y"}})

    def test_spec_definition_has_no_violation(self):
        definition = self._definition()
        self.assertEqual(definition.spec_constant_violations(), ())
        definition.require_spec_constants()

    def test_provisional_sigma_is_fixed(self):
        for sd in (0.002, 0.02):
            with self.subTest(sd=sd):
                definition = self._sigma(sd)
                self.assertTrue(definition.spec_constant_violations())
                with self.assertRaises(CampaignDefinitionError):
                    definition.require_spec_constants()

    def test_measured_sigma_needs_evidence(self):
        self.assertTrue(self._sigma(0.003, "MEASURED").spec_constant_violations())

    def test_lm_constants_are_fixed(self):
        from test_m7_campaign import synthetic_definition
        base = synthetic_definition()
        for key, value in (("stop_fraction", 100.0), ("max_iterations", 50), ("finite_difference_step", 0.3),
                           ("mu_increase", 2.0)):
            with self.subTest(key=key):
                definition = parse_campaign_definition(synthetic_definition(lm=dict(base["lm"], **{key: value})))
                self.assertTrue(definition.spec_constant_violations())

    def test_inflated_sigma_releases_nothing(self):
        """The audit reproduction: σ_setup 0.02 turned a §13 FAIL into a released value."""
        from services.identification_campaign_run import CampaignRun, CampaignRunConfig, build_campaign_report
        from test_m7_campaign import FakeExtractor, FakeSolver, synthetic_specimen

        definition = self._sigma(0.02)
        tmp = Path(tempfile.mkdtemp())
        a, store = synthetic_specimen(definition, "A", tmp, 48000.0)
        b, _ = synthetic_specimen(definition, "B", tmp, 56000.0)
        config = CampaignRunConfig(tmp / "runs", {"synthetic": store}, "abq2024.bat", FakeSolver(), FakeExtractor(),
                                   {}, "m" * 64)
        run = CampaignRun(definition, [a, b], "m" * 64, config)
        result = run.run()
        report = build_campaign_report(definition, run.specimens, run.journal.records("evaluation"), result)
        self.assertEqual(report["formal_output"]["released_values"], {})
        self.assertTrue(any(b.startswith("SPEC_CONSTANT_CHANGED") for b in report["formal_output"]["blockers"]))
        self.assertEqual(report["material_claim"], "NO_MATERIAL_PROPERTY_CLAIM")


if __name__ == "__main__":
    unittest.main()
