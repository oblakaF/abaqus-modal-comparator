"""PRIORITY-3: targeted tests of the research inverse fit (synthetic data only; no real file is needed).

- the bounded LM of ``identification_step`` recovers known parameters through the log-linear approximation (one
  parameter, and E1 = E2 = E with G12);
- a rank-deficient scenario gives a refusal, never a number;
- a changed sensitivity table is refused by its SHA-256;
- MAC is not an input of the fit (frequencies and the approximation only).
"""

from __future__ import annotations

import inspect
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_inverse as R  # noqa: E402


def synthetic():
    return {"T1": {"f0": 20.0, "E1": 0.01, "E2": 0.01, "G12": 0.48},
            "T2": {"f0": 170.0, "E1": 0.22, "E2": 0.23, "G12": 0.05},
            "T3": {"f0": 170.0, "E1": 0.22, "E2": 0.23, "G12": 0.05}}  # T3 duplicates T2: collinear


class InverseTests(unittest.TestCase):
    def test_known_parameters_are_recovered(self):
        sens = synthetic()
        truth = R.full_parameters({"E": 56000 * 0.8, "G12": 5000 * 0.95})
        f_exp = {1: R.predict(sens, "T1", truth), 2: R.predict(sens, "T2", truth)}
        result = R.fit(R.Scenario("X", ((1, "T1"), (2, "T2")), ("E", "G12"), "synthetic"), sens, f_exp)
        self.assertEqual(result["status"], "CONVERGED")
        self.assertAlmostEqual(result["ratios"]["E"], 0.8, places=3)
        self.assertAlmostEqual(result["ratios"]["G12"], 0.95, places=3)
        self.assertIn("E", result["extrapolation_beyond_5_percent"])  # −20 % lies outside the solved ±5 %
        one = R.fit(R.Scenario("Y", ((1, "T1"),), ("G12",), "synthetic"), sens,
                    {1: R.predict(sens, "T1", R.full_parameters({"G12": 4800.0}))})
        self.assertAlmostEqual(one["parameters"]["G12"], 4800.0, delta=5.0)
        self.assertEqual(one["parameters"]["E1"], 56000.0)  # not fitted, never changed

    def test_a_rank_deficient_scenario_is_refused(self):
        sens = synthetic()
        result = R.fit(R.Scenario("Z", ((2, "T2"), (3, "T3")), ("E", "G12"), "collinear"), sens, {2: 160.0, 3: 160.0})
        self.assertEqual(result["status"], "REFUSED_RANK_DEFICIENT")
        self.assertNotIn("parameters", result)

    def test_a_changed_sensitivity_table_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "table.csv"
            path.write_text("term,f_baseline_hz\n", encoding="utf-8")
            with self.assertRaises(R.Refused):
                R.load_sensitivities(path)

    def test_mac_is_not_an_input_of_the_fit(self):
        self.assertEqual(list(inspect.signature(R.fit).parameters), ["scenario", "sens", "f_exp"])
        self.assertNotIn("mac", inspect.getsource(R.fit).lower().replace("mac 0.79", ""))


if __name__ == "__main__":
    unittest.main()
