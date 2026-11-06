"""REAL-FIT.R2: stability of the research frequency-tuning estimates. The numerical tests use frequencies computed by the
surrogate itself at known values (a software test); the real PolyMAX run is in docs/materials/REAL_FIT_R2_REPORT.md."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", Path(__file__).resolve().parent):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from services import research_frequency_stability as rfs  # noqa: E402
from services import research_frequency_tuning as rft  # noqa: E402
from test_real_fit_r1_tuning import _files  # noqa: E402  (the same test plate INP)


class Stability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = rft.read_inp(_files() / "plate.inp")
        cls.surrogate = rft.Surrogate(cls.inputs, 10, 16)

    def synthetic(self, E1, E2, G12, count=9, shift=None):
        spectrum = self.surrogate.frequencies(E1, E2, G12)
        records = [(k + 1, float(spectrum[k])) for k in range(count)]
        if shift:
            record, factor = shift
            records = [(r, hz * factor if r == record else hz) for r, hz in records]
        return records

    def fitted(self, records, parameterization=rft.TIED, holdout=(9,), declared=None):
        request = rft.TuningRequest(rft.observations_by_rank(records, holdout=holdout, declared=declared), parameterization,
                                    rft.DECLARED if declared else rft.RANK_ORDER, degree=10)
        return request, rft.run_tuning(self.inputs, request)

    def test_exact_data_are_stable_and_the_accuracy_is_still_not_demonstrated(self):
        request, result = self.fitted(self.synthetic(42000, 42000, 6500))
        before = json.dumps(result.to_dict(), default=str, sort_keys=True)
        stability = rfs.run_stability(self.inputs, request, result)
        self.assertEqual(json.dumps(result.to_dict(), default=str, sort_keys=True), before)  # the baseline is untouched
        self.assertEqual(stability["status"], "DONE")
        self.assertEqual(stability["label"], rft.RESULT_LABEL)
        self.assertEqual([item["record"] for item in stability["leave_one_out"]], [1, 2, 3, 4, 5, 6, 7, 8])
        for item in stability["leave_one_out"]:
            self.assertTrue(item["converged"])
            self.assertEqual(item["practical_rank"], 2)
            self.assertEqual(item["active_bounds"], [])
            self.assertLess(max(abs(v) for v in item["change"].values()), 1e-4)
            self.assertLess(abs(item["left_out_residual_ln"]), 1e-4)  # the left-out frequency is predicted
        self.assertFalse(any(c["disproportionate"] for c in stability["control"]))
        assessment = stability["assessment"]
        self.assertEqual(assessment["numerical_stability"]["verdict"], rfs.STABLE)
        self.assertEqual(assessment["parameter_accuracy"]["verdict"], rfs.NOT_DEMONSTRATED)  # never from a small residual
        self.assertTrue(assessment["statement"].startswith("10 % TARGET: NOT DEMONSTRATED."))

    def test_every_refit_keeps_the_declared_ranks_and_roles(self):
        spectrum = self.surrogate.frequencies(42000, 42000, 6500)
        records = [(1, float(spectrum[0])), (2, float(spectrum[1]))] + [(k, float(spectrum[k])) for k in range(3, 10)]
        declared = {k: k + 1 for k in range(3, 10)}  # surrogate rank 3 was not measured
        request, result = self.fitted(records, declared=declared)
        seen = []
        original = rft._Problem

        def recording(inputs, names, rows, degree, cancel, progress):
            seen.append(tuple((o.record, o.role, o.surrogate_rank) for o in rows))
            return original(inputs, names, rows, degree, cancel, progress)

        with mock.patch.object(rft, "_Problem", side_effect=recording):
            stability = rfs.run_stability(self.inputs, request, result)
        ranks = {1: 1, 2: 2, **declared}
        for item in stability["leave_one_out"]:
            expected = {r: k for r, k in ranks.items() if r not in (item["record"], 9)}
            self.assertEqual(item["ranks_kept"], expected)  # never renumbered or rematched
            self.assertEqual(item["rank"], ranks[item["record"]])
            self.assertLess(max(abs(v) for v in item["change"].values()), 1e-4)
        for rows in seen:  # every problem solved holds the declared rank of each record it names
            self.assertTrue(all(rank == ranks[record] for record, _role, rank in rows), rows)
            self.assertNotIn((9, rft.FIT, 10), rows)  # the HOLDOUT never enters a fit

    def test_one_shifted_record_is_found_to_control_an_estimate(self):
        request, result = self.fitted(self.synthetic(42000, 42000, 6500, shift=(1, 1.03)))
        stability = rfs.run_stability(self.inputs, request, result)
        without = next(item for item in stability["leave_one_out"] if item["record"] == 1)
        # the other records are exact: leaving the shifted one out recovers the generating values
        self.assertAlmostEqual(without["estimates"]["E (E1 = E2)"] / 42000, 1.0, places=4)
        self.assertAlmostEqual(without["estimates"]["G12"] / 6500, 1.0, places=4)
        self.assertLess(without["fit_rms_ln"], 1e-5)
        self.assertAlmostEqual(without["left_out_residual_ln"], -math.log(1.03), places=4)
        control = {c["parameter"]: c for c in stability["control"]}
        self.assertEqual(control["G12"]["record"], 1)
        self.assertTrue(control["G12"]["disproportionate"])
        self.assertEqual(control["G12"]["local_top_record"], 1)
        linear = next(item for item in stability["influence"]["linearized_leave_one_out"] if item["record"] == 1)
        for name, change in without["change"].items():  # the linearized leave-one-out agrees with the refit
            self.assertAlmostEqual(linear["change"][name], change, delta=0.1 * abs(change) + 1e-4)

    def test_the_influence_coefficients_come_from_the_full_fit_sensitivity(self):
        request, result = self.fitted(self.synthetic(42000, 42000, 6500))
        local = rfs.influence(result)
        self.assertEqual((local["practical_rank"], local["rank_deficient"], local["undetermined"]), (2, False, []))
        for name, total in local["coefficient_sums"].items():  # a common frequency factor c moves every modulus by c^2
            self.assertAlmostEqual(total, 2.0, places=4, msg=name)
        self.assertAlmostEqual(sum(c["leverage"] for c in local["coefficients"]), 2.0, places=8)  # trace of the hat matrix
        names = result.parameter_names
        J = [[row[n] for n in names] for row in result.sensitivity]
        pinv = [[c[q] for c in local["coefficients"]] for q in ("E (E1 = E2)", "G12")]
        for i in range(2):  # pinv @ J = identity at full rank
            for j in range(2):
                value = sum(pinv[i][k] * J[k][j] for k in range(len(J)))
                self.assertAlmostEqual(value, 1.0 if i == j else 0.0, places=8)

    def test_a_rank_deficient_sensitivity_marks_the_parameters_undetermined(self):
        rows = [{"record": k, "E": 0.5, "G12": 0.5} for k in (1, 2, 3, 4)]  # one direction only: E and G12 move together
        baseline = SimpleNamespace(parameter_names=("E", "G12"), sensitivity=rows,
                                   rows=[{"record": k, "role": rft.FIT, "ln_after": 0.0} for k in (1, 2, 3, 4)],
                                   minima=[{"values": {"E": 40000.0, "G12": 5000.0}}])
        local = rfs.influence(baseline)
        self.assertEqual(local["practical_rank"], 1)
        self.assertTrue(local["rank_deficient"])
        self.assertEqual(sorted(local["undetermined"]), ["E (E1 = E2)", "G12"])
        self.assertIn("not determined", local["rank_note"])
        self.assertIn("minimum-norm convention", local["rank_note"])

    def test_thickness_and_density_scale_the_moduli_exactly(self):
        request, result = self.fitted(self.synthetic(42000, 42000, 6500))
        fixed = rfs.fixed_input_dependence(self.inputs, result, 10)
        self.assertEqual(fixed["exponents"], {"d ln E / d ln t (density held)": -2.0,
                                              "d ln E / d ln t (surface mass held)": -3.0, "d ln E / d ln rho": 1.0})
        for check in fixed["verification"]:
            self.assertLess(check["largest_relative_frequency_difference"], 1e-10, check["case"])
        bands = fixed["input_factor_for_a_10_percent_modulus_change"]
        self.assertAlmostEqual(bands["thickness, density held"][0], 1.1 ** -0.5)
        self.assertAlmostEqual(bands["thickness, surface mass held"][1], 0.9 ** (-1.0 / 3.0))
        self.assertEqual(bands["density"], [0.9, 1.1])
        self.assertIn("not an uncertainty", fixed["factor_note"])
        self.assertNotIn("sd", json.dumps(fixed).lower().replace("surface", ""))  # no distribution is invented

    def test_the_orthotropic_model_is_compared_without_an_axis(self):
        request, result = self.fitted(self.synthetic(60000, 44000, 4800), rft.FREE)
        self.assertEqual(result.status, rft.MIRROR)
        stability = rfs.run_stability(self.inputs, request, result)
        self.assertEqual(tuple(stability["baseline"]["estimates"]), ("E_stiff", "E_soft", "G12"))
        for item in stability["leave_one_out"]:
            self.assertEqual(set(item["change"]), {"E_stiff", "E_soft", "G12"})
            self.assertTrue(item["mirror"])
            self.assertLess(max(abs(v) for v in item["change"].values()), 1e-3)
        self.assertEqual(stability["assessment"]["parameter_accuracy"]["verdict"], rfs.NOT_DEMONSTRATED)
        self.assertTrue(any("axis assignment is unresolved" in r for r in stability["assessment"]["parameter_accuracy"]["reasons"]))

    def test_a_change_above_the_target_is_said(self):
        request, result = self.fitted(self.synthetic(42000, 42000, 6500, shift=(1, 1.15)))  # G12 moves by about 17 % without it
        stability = rfs.run_stability(self.inputs, request, result)
        numerical = stability["assessment"]["numerical_stability"]
        self.assertEqual(numerical["verdict"], rfs.UNSTABLE)
        self.assertIn("more than 10 %", stability["assessment"]["statement"])
        self.assertEqual(stability["assessment"]["parameter_accuracy"]["verdict"], rfs.NOT_DEMONSTRATED)

    def test_refusals_and_cancel(self):
        request, result = self.fitted(self.synthetic(42000, 42000, 6500))
        other = rft.TuningRequest(rft.observations_by_rank(self.synthetic(42000, 42000, 6500), holdout=(8, 9)), degree=10)
        with self.assertRaises(rft.TuningRefused):
            rfs.run_stability(self.inputs, other, result)  # not the request of this result
        with self.assertRaises(rft.TuningRefused):
            rfs.run_stability(self.inputs, request, rft._cancelled(self.inputs, request, ("E", "G12")))
        cancel = threading.Event()
        cancel.set()
        self.assertEqual(rfs.run_stability(self.inputs, request, result, cancel)["status"], rft.CANCELLED)

    def test_the_export_carries_the_stability_check(self):
        request, result = self.fitted(self.synthetic(42000, 42000, 6500))
        stability = rfs.run_stability(self.inputs, request, result)
        document = rft.export_document(result, self.inputs, {"inp": "plate.inp"}, stability)
        self.assertEqual(document["stability"]["schema"], rfs.SCHEMA)
        target = rft.write_export(document, Path(tempfile.mkdtemp()) / "proposal.json")
        self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["stability"]["assessment"]["parameter_accuracy"]
                         ["verdict"], rfs.NOT_DEMONSTRATED)
        self.assertIsNone(rft.export_document(result, self.inputs, {})["stability"])


class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def wait(self, panel, limit=120.0):
        end = time.monotonic() + limit
        while panel.busy() and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()

    def test_the_page_shows_and_exports_the_stability_check(self):
        from new_gui import production_window as pw
        from new_gui import research_tuning_model as rm

        folder = _files()
        inputs = rft.read_inp(folder / "plate.inp")
        spectrum = rft.Surrogate(inputs, 14, 16).frequencies(45000, 45000, 6000)
        records = tuple((k + 1, float(spectrum[k] * (1.02 if k == 0 else 1.0))) for k in range(9))
        sources = rm.Sources(inputs, None, (), (), "unavailable (test)", "exp.unv", "0" * 64, "Set", records)
        window = pw.ProductionWindow()
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        window.resize(1366, 768)
        window.show()
        window.show_page(pw.TUNING_PAGE)
        panel = window.research_tuning
        with mock.patch.object(rm, "read_sources", return_value=sources):
            panel.choose_file("inp", str(folder / "plate.inp"))
            panel.choose_file("unv", "exp.unv")
            self.wait(panel)
        self.assertFalse(panel.run_stability())  # no result yet
        panel.degree.setText("10")
        self.assertTrue(panel.run())
        self.wait(panel)
        self.assertTrue(panel.stability_button.isEnabled())
        self.assertTrue(panel.run_stability())
        self.assertTrue(panel.cancel())  # the check can be cancelled
        self.wait(panel)
        self.assertTrue(panel.stability is None or panel.stability["status"] == "DONE")
        self.assertTrue(panel.run_stability())
        self.assertFalse(panel.run_button.isEnabled())
        self.wait(panel)
        self.assertEqual(panel.stability["status"], "DONE")
        self.assertIn("10 % TARGET: NOT DEMONSTRATED", panel.stability_statement.text())
        self.assertIn(rft.RESULT_LABEL, panel.stability_statement.text())
        self.assertEqual([row[0] for row in panel.table_cells("stability_loo")], [str(k) for k in range(1, 8)])
        control = {row[0]: row for row in panel.table_cells("stability_control")}
        self.assertEqual(control["G12"][3], "1")
        self.assertEqual(len(panel.table_cells("stability_influence")), 7)
        self.assertIn("NOT_DEMONSTRATED", [row[1] for row in panel.table_cells("stability_assessment")])
        self.assertTrue(any("Relation" == row[0] for row in panel.table_cells("stability_fixed")))
        target = Path(tempfile.mkdtemp()) / "proposal.json"
        self.assertTrue(panel.export(str(target)))
        document = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(document["stability"]["status"], "DONE")
        panel.parameterization.setCurrentIndex(panel.parameterization.findData(rft.TIED))
        self.assertTrue(panel.run())  # a new fit clears the old check
        self.assertIsNone(panel.stability)
        self.assertNotIn("stability_loo", panel._tables)
        self.wait(panel)


if __name__ == "__main__":
    unittest.main()
