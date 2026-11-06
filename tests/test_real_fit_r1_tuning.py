"""REAL-FIT.R1: the research-only frequency tuning service and its page. The numerical tests use frequencies computed by the
surrogate itself at known values (a software test); the real PolyMAX run is in docs/materials/REAL_FIT_R1_REPORT.md."""

from __future__ import annotations

import ast
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from services import research_frequency_tuning as rft  # noqa: E402

INP = """*Heading
** test plate
*Part, name=PLATE
*Node
      1,           0.,           0.,           0.
      2,         301.,           0.,           0.
      3,         301.,         300.,           0.
      4,           0.,         300.,           0.
*Element, type=S4R
1, 1, 2, 3, 4
*Shell Section, elset=Set-1, material=CFRP_T300_TEST
0.875, 5
*End Part
*Material, name=CFRP_T300_TEST
*Density
 1.498e-09,
*Elastic, type=ENGINEERING CONSTANTS
56000.,56000., 8500.,  0.05,   0.3,   0.3, 5000., 3000.
 3000.,
*Step, name=Modal
*Frequency, eigensolver=Lanczos
20, , , , ,
*End Step
"""
DAT = """
                              E I G E N V A L U E    O U T P U T


 MODE NO      EIGENVALUE              FREQUENCY         GENERALIZED MASS   COMPOSITE MODAL DAMPING
                             (RAD/TIME)   (CYCLES/TIME)

       1     -7.1022E-05      0.0000         0.0000         1.0000          0.0000
       7      14360.          119.83         19.072         1.0000          0.0000
       8      1.4153E+05      376.20         59.874         1.0000          0.0000

                              P A R T I C I P A T I O N   F A C T O R S
"""


def _files():
    folder = Path(tempfile.mkdtemp())
    (folder / "plate.inp").write_text(INP, encoding="latin-1")
    (folder / "plate.dat").write_text(DAT, encoding="latin-1")
    return folder


class ReadingAndConversion(unittest.TestCase):
    def test_the_inputs_are_read_from_the_inp_not_assumed(self):
        inputs = rft.read_inp(_files() / "plate.inp")
        self.assertEqual((inputs.material, inputs.elastic_type), ("CFRP_T300_TEST", "ENGINEERING CONSTANTS"))
        self.assertEqual((inputs.E1, inputs.E2, inputs.E3, inputs.nu12, inputs.G12, inputs.G13, inputs.G23),
                         (56000.0, 56000.0, 8500.0, 0.05, 5000.0, 3000.0, 3000.0))
        self.assertEqual((inputs.density_t_mm3, inputs.thickness_mm, inputs.a_mm, inputs.b_mm), (1.498e-09, 0.875, 301.0, 300.0))
        self.assertFalse(inputs.has_orientation)
        self.assertAlmostEqual(inputs.mass_g, 118.36, places=2)

    def test_a_layup_or_a_second_material_is_refused(self):
        folder = _files()
        (folder / "two.inp").write_text(INP + "*Material, name=OTHER\n*Density\n1e-9,\n", encoding="latin-1")
        with self.assertRaises(rft.TuningRefused):
            rft.read_inp(folder / "two.inp")
        (folder / "layup.inp").write_text(INP.replace("*Shell Section,", "*Shell Section, composite,"), encoding="latin-1")
        with self.assertRaises(rft.TuningRefused):
            rft.read_inp(folder / "layup.inp")

    def test_the_dat_frequencies_are_listed_and_never_classified_by_frequency(self):
        rows = rft.read_dat_frequencies(_files() / "plate.dat")
        self.assertEqual(rows, ((1, 0.0), (7, 19.072), (8, 59.874)))
        self.assertFalse(hasattr(rft, "elastic_fe_frequencies"))  # R1.F1: no frequency cutoff for rigid-body modes

    def test_without_fe_mode_shapes_the_classification_is_unavailable(self):
        from new_gui import research_tuning_model as rm

        self.assertTrue(rm._classify(None, threading.Event())[1].startswith("unavailable"))
        fake = _files() / "plate.odb"
        fake.write_bytes(b"not an odb")
        elastic, text = rm._classify(str(fake), threading.Event())
        self.assertEqual(elastic, ())
        self.assertTrue(text.startswith("unavailable"), text)

    def test_the_isotropic_limit_of_the_bending_stiffness(self):
        E, nu, t = 70000.0, 0.3, 2.0
        d = rft.bending_stiffness(E, E, nu, E / (2 * (1 + nu)), t)
        plate = E * t ** 3 / (12 * (1 - nu ** 2)) * 1e-3
        self.assertAlmostEqual(d.D11, plate, places=9)
        self.assertAlmostEqual(d.D12, nu * plate, places=9)
        self.assertAlmostEqual(d.D11 - d.D12, 2 * d.D66, places=9)  # isotropy: D66 = (D11 - D12) / 2

    def test_the_surrogate_spectrum_is_free_of_rigid_modes_and_scales_with_the_moduli(self):
        inputs = rft.read_inp(_files() / "plate.inp")
        surrogate = rft.Surrogate(inputs, 10, 12)
        base = surrogate.frequencies(56000, 56000, 5000)
        scaled = surrogate.frequencies(4 * 56000, 4 * 56000, 4 * 5000)
        self.assertGreater(base[0], 10.0)  # the first returned frequency is elastic
        self.assertTrue(abs(base[0] - 19.07) / 19.07 < 0.01)  # the twist branch of the model, as the stored S4R
        for left, right in zip(base, scaled):
            self.assertAlmostEqual(right / left, 2.0, places=6)  # f ~ sqrt(D)


class Tuning(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = rft.read_inp(_files() / "plate.inp")
        cls.surrogate = rft.Surrogate(cls.inputs, 10, 16)

    def synthetic(self, E1, E2, G12, count=9):
        spectrum = self.surrogate.frequencies(E1, E2, G12)
        return [(k + 1, float(spectrum[k])) for k in range(count)]

    def request(self, records, holdout=(8, 9), parameterization=rft.TIED, **kw):
        return rft.TuningRequest(rft.observations_by_rank(records, holdout=holdout), parameterization, degree=10, **kw)

    def test_known_values_are_recovered_and_supported(self):
        result = rft.run_tuning(self.inputs, self.request(self.synthetic(42000, 42000, 6500)))
        self.assertEqual(result.status, rft.SUPPORTED, result.reasons)
        self.assertAlmostEqual(result.estimates["E (E1 = E2)"] / 42000, 1.0, places=5)
        self.assertAlmostEqual(result.candidate["E1"] / 42000, 1.0, places=5)
        self.assertAlmostEqual(result.candidate["G12"] / 6500, 1.0, places=5)
        self.assertLess(result.rms_holdout_after, 1e-6)
        self.assertEqual(result.label, rft.RESULT_LABEL)
        self.assertEqual(result.practical_rank, 2)
        self.assertEqual([w for w in result.warnings if not w.startswith("FE classification unavailable")], [])

    def test_an_exchange_of_e1_and_e2_is_reported_not_chosen(self):
        result = rft.run_tuning(self.inputs, self.request(self.synthetic(60000, 44000, 4800), parameterization=rft.FREE))
        self.assertEqual(result.status, rft.MIRROR, result.reasons)
        self.assertIsNone(result.candidate)
        self.assertEqual(len(result.minima), 2)
        self.assertAlmostEqual(result.estimates["E_stiff"] / 60000, 1.0, delta=0.02)  # estimates without an axis
        self.assertAlmostEqual(result.estimates["E_soft"] / 44000, 1.0, delta=0.02)
        self.assertEqual(len(result.axis_assignments), 2)  # both assignments, none chosen
        firsts = sorted(round(a["E1 (FE X)"], -2) for a in result.axis_assignments)
        self.assertLess(firsts[0], firsts[1])
        values = sorted((round(m["values"]["E1"]), round(m["values"]["E2"])) for m in result.minima)
        self.assertAlmostEqual(values[0][0] / 44000, 1.0, delta=0.02)
        self.assertAlmostEqual(values[0][1] / 60000, 1.0, delta=0.02)

    def test_too_few_fit_frequencies_are_refused(self):
        records = self.synthetic(56000, 56000, 5000, count=4)
        with self.assertRaises(rft.TuningRefused):
            rft.run_tuning(self.inputs, self.request(records, holdout=(2, 3)))

    def test_holdout_frequencies_do_not_enter_the_fit(self):
        records = self.synthetic(50000, 50000, 5500)
        moved = [(r, hz * (1.3 if r == 9 else 1.0)) for r, hz in records]
        first = rft.run_tuning(self.inputs, self.request(records))
        second = rft.run_tuning(self.inputs, self.request(moved))
        self.assertEqual(first.fitted, second.fitted)
        self.assertGreater(second.rms_holdout_after, 0.1)
        self.assertTrue(any("HOLDOUT" in w for w in second.warnings))

    def test_a_poor_parameterization_is_warned_about(self):
        records = self.synthetic(60000, 44000, 4800)
        result = rft.run_tuning(self.inputs, self.request(records))  # E1 = E2 cannot follow a split
        self.assertTrue(any("model-form" in w for w in result.warnings), result.warnings)

    def test_a_bound_is_reported(self):
        records = self.synthetic(60000, 44000, 4800)  # an E1 = E2 fit of a split spectrum, in a very narrow range
        result = rft.run_tuning(self.inputs, self.request(records, search_factor=1.0001))
        self.assertEqual(result.status, rft.AT_BOUND)
        self.assertIsNone(result.candidate)
        self.assertIsNone(result.estimates)
        self.assertTrue(result.active_bounds)

    def test_the_start_and_bounds_come_from_the_data_not_from_the_inp(self):
        records = self.synthetic(42000, 42000, 6500)
        first = rft.run_tuning(self.inputs, self.request(records))
        from dataclasses import replace

        other = replace(self.inputs, E1=3 * self.inputs.E1, E2=3 * self.inputs.E2, G12=0.3 * self.inputs.G12)
        second = rft.run_tuning(other, self.request(records))
        self.assertEqual(first.initialization["start"], second.initialization["start"])
        self.assertEqual(first.initialization["bounds"], second.initialization["bounds"])
        self.assertAlmostEqual(first.fitted["E1"], second.fitted["E1"], places=3)
        self.assertEqual(first.initialization["inp_values_used"], "no (shown for comparison only)")

    def test_the_lowest_record_is_checked_not_removed(self):
        records = self.synthetic(42000, 42000, 6500)
        result = rft.run_tuning(self.inputs, self.request(records))
        self.assertTrue(result.first_mode_check["done"])
        self.assertEqual(result.first_mode_check["left_out_record"], 1)
        self.assertLess(result.first_mode_check["largest_change"], 1e-4)  # exact data: nothing leans on it
        self.assertIn(1, [r["record"] for r in result.rows if r["role"] == rft.FIT])  # it stays in the fit

    def test_quantities_and_the_accuracy_statement_are_explicit(self):
        result = rft.run_tuning(self.inputs, self.request(self.synthetic(42000, 42000, 6500)))
        categories = {q["category"] for q in result.quantities}
        self.assertTrue({"MEASURED", "FITTED", "ASSUMED (INP), FIXED", "FIXED, NOT IDENTIFIED", "UNAVAILABLE"} <= categories)
        self.assertIn("nu12", next(q["quantity"] for q in result.quantities if q["category"] == "FIXED, NOT IDENTIFIED"))
        self.assertIn("not a demonstrated or certified", result.accuracy_statement)
        factors = {row["assumption"]: row["moduli_factor"] for row in result.assumption_sensitivity}
        self.assertAlmostEqual(factors["thickness +5%, surface mass held (measured mass)"], 1.05 ** -3)

    def test_cancel_returns_no_result(self):
        cancel = threading.Event()
        cancel.set()
        result = rft.run_tuning(self.inputs, self.request(self.synthetic(50000, 50000, 5000)), cancel=cancel)
        self.assertEqual(result.status, rft.CANCELLED)
        self.assertIsNone(result.candidate)

    def test_the_export_names_the_label_and_keeps_the_other_constants(self):
        result = rft.run_tuning(self.inputs, self.request(self.synthetic(42000, 42000, 6500)))
        document = rft.export_document(result, self.inputs, {"inp": "x.inp"})
        self.assertIn(rft.RESULT_LABEL, document["statement"])
        line = document["abaqus_elastic_candidate"]
        self.assertTrue(line.startswith("*Elastic, type=ENGINEERING CONSTANTS"))
        self.assertIn("8500, 0.05, 0.3, 0.3", line)
        self.assertEqual(json.loads(json.dumps(document, default=str))["status"], rft.SUPPORTED)
        mirror = rft.run_tuning(self.inputs, self.request(self.synthetic(60000, 44000, 4800), parameterization=rft.FREE))
        self.assertIsNone(rft.export_document(mirror, self.inputs, {})["abaqus_elastic_candidate"])

    def test_the_governed_workflow_is_not_used(self):
        tree = ast.parse((ROOT / "src" / "services" / "research_frequency_tuning.py").read_text(encoding="utf-8"))
        imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        self.assertNotIn("services.plate_material_workflow", imported)
        self.assertNotIn("services.identification_step", imported)


class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def window(self):
        from new_gui import production_window as pw

        window = pw.ProductionWindow()
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        window.resize(1366, 768)
        window.show()
        window.show_page(pw.TUNING_PAGE)
        self.app.processEvents()
        return window, window.research_tuning

    def wait(self, panel, limit=60.0):
        end = time.monotonic() + limit
        while panel.busy() and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()

    def loaded(self, records):
        from new_gui import research_tuning_model as rm

        folder = _files()
        inputs = rft.read_inp(folder / "plate.inp")
        sources = rm.Sources(inputs, str(folder / "plate.dat"), ((7, 19.072), (8, 59.874)), ((7, 19.072), (8, 59.874)),
                             "shape-based (test)", "exp.unv", "0" * 64, "Set", tuple(records))
        window, panel = self.window()
        with mock.patch.object(rm, "read_sources", return_value=sources):
            panel.choose_file("inp", str(folder / "plate.inp"))
            panel.choose_file("unv", "exp.unv")
            self.wait(panel)
        return window, panel, inputs

    def test_the_page_runs_shows_and_exports_a_candidate(self):
        surrogate = rft.Surrogate(rft.read_inp(_files() / "plate.inp"), 14, 16)
        spectrum = surrogate.frequencies(45000, 45000, 6000)
        window, panel, _inputs = self.loaded([(k + 1, float(spectrum[k])) for k in range(10)])
        self.assertEqual(dict(panel.table_cells("inputs"))["E1"], "56000 MPa")
        self.assertEqual(panel.roles()[10], rft.HOLDOUT)
        self.assertEqual(panel.roles()[9], rft.HOLDOUT)
        self.assertTrue(panel.run())
        self.assertFalse(panel.choose_file("inp", "other.inp"))  # nothing changes under a running fit
        self.wait(panel)
        self.assertEqual(panel.result.status, rft.SUPPORTED)
        cells = {row[0]: row for row in panel.table_cells("candidate")}
        self.assertAlmostEqual(float(cells["E1"][2]) / 45000, 1.0, places=3)  # whole MPa
        self.assertIn(rft.RESULT_LABEL, panel.status.text())
        self.assertEqual([row[0] for row in panel.table_cells("estimates")], ["E (E1 = E2)", "G12"])
        self.assertIn("FIXED, NOT IDENTIFIED", [row[1] for row in panel.table_cells("quantities")])
        self.assertIn("not a demonstrated", panel.accuracy.text())
        self.assertTrue(panel.plot_data.startswith(b"\x89PNG"))
        self.assertEqual(len(panel.table_cells("frequencies")), 10)
        target = Path(tempfile.mkdtemp()) / "proposal.json"
        self.assertTrue(panel.export(str(target)))
        document = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(document["label"], rft.RESULT_LABEL)
        self.assertIsNotNone(document["abaqus_elastic_candidate"])

    def test_roles_and_cancel(self):
        surrogate = rft.Surrogate(rft.read_inp(_files() / "plate.inp"), 14, 16)
        spectrum = surrogate.frequencies(60000, 44000, 4800)
        window, panel, _inputs = self.loaded([(k + 1, float(spectrum[k])) for k in range(10)])
        panel.set_role(3, rft.EXCLUDED)
        panel.parameterization.setCurrentIndex(panel.parameterization.findData(rft.FREE))
        request = panel.build_request()
        self.assertEqual([o.role for o in request.observations if o.record == 3], [rft.EXCLUDED])
        self.assertTrue(panel.run())
        self.assertTrue(panel.cancel())
        self.wait(panel)
        self.assertIn(panel.result.status if panel.result else rft.CANCELLED, (rft.CANCELLED, rft.MIRROR))
        panel.run()
        self.wait(panel)
        self.assertEqual(panel.result.status, rft.MIRROR)
        self.assertEqual([row[0] for row in panel.table_cells("estimates")], ["E_stiff", "E_soft", "G12"])
        self.assertEqual(len(panel.table_cells("axes")), 2)
        self.assertNotIn("candidate", panel._tables)  # no oriented block
        self.assertIn("unresolved", panel.candidate_none.text())
        self.assertTrue(panel.run_button.isEnabled())

    def test_a_bad_setting_is_said_and_nothing_starts(self):
        window, panel, _inputs = self.loaded([(k + 1, 20.0 * (k + 1)) for k in range(8)])
        panel.search.setText("1")
        self.assertFalse(panel.run())
        self.assertIn("search range", panel.message.text())
        self.assertFalse(panel.busy())


if __name__ == "__main__":
    unittest.main()
