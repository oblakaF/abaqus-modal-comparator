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


class Correspondence(unittest.TestCase):
    """REAL-FIT.R1.F2: a declared correspondence is validated before any fit and kept intact by every check."""

    @classmethod
    def setUpClass(cls):
        cls.inputs = rft.read_inp(_files() / "plate.inp")
        cls.spectrum = rft.Surrogate(cls.inputs, 10, 16).frequencies(42000, 42000, 6500)

    def skipped_third(self):
        """Measured records 1..9 with surrogate rank 3 not measured: record k >= 3 holds rank k + 1."""
        records = [(1, float(self.spectrum[0])), (2, float(self.spectrum[1]))]
        records += [(k, float(self.spectrum[k])) for k in range(3, 10)]
        return records, {k: k + 1 for k in range(3, 10)}

    def test_a_custom_mapping_is_fitted_and_kept_by_the_first_mode_check(self):
        records, declared = self.skipped_third()
        observations = rft.observations_by_rank(records, holdout=(9,), declared=declared)
        self.assertEqual({o.record: o.surrogate_rank for o in observations}, {1: 1, 2: 2, **declared})
        result = rft.run_tuning(self.inputs, rft.TuningRequest(observations, rft.TIED, rft.DECLARED, degree=10))
        self.assertEqual(result.status, rft.SUPPORTED, result.reasons)
        self.assertAlmostEqual(result.fitted["E1"] / 42000, 1.0, places=5)
        check = result.first_mode_check
        self.assertTrue(check["done"])
        self.assertEqual((check["left_out_record"], check["left_out_rank"]), (1, 1))
        self.assertEqual(check["ranks_kept"], {2: 2, **{k: k + 1 for k in range(3, 9)}})  # never renumbered or rematched
        self.assertNotIn(9, check["ranks_kept"])  # HOLDOUT stays out of the fit
        self.assertLess(check["largest_change"], 1e-4)  # exact data under the declared mapping: nothing moves
        self.assertEqual([r["role"] for r in result.rows if r["record"] == 1], [rft.FIT])  # it stays in the main fit

    def test_the_default_hypothesis_check_leaves_only_the_lowest_record_out(self):
        records = [(k + 1, float(self.spectrum[k])) for k in range(9)]
        result = rft.run_tuning(self.inputs, rft.TuningRequest(rft.observations_by_rank(records, holdout=(8, 9)), degree=10))
        check = result.first_mode_check
        self.assertEqual(check["ranks_kept"], {k: k for k in range(2, 8)})

    def test_a_partial_mapping_that_duplicates_a_rank_is_refused_before_the_fit(self):
        records = [(k + 1, float(self.spectrum[k])) for k in range(9)]
        observations = rft.observations_by_rank(records, holdout=(9,), declared={3: 4})  # record 4 keeps rank 4 by default
        with mock.patch.object(rft, "least_squares", side_effect=AssertionError("no fit on an invalid correspondence")):
            with self.assertRaises(rft.TuningRefused) as caught:
                rft.run_tuning(self.inputs, rft.TuningRequest(observations, degree=10))
        self.assertIn("rank 4 is assigned to records 3, 4", str(caught.exception))

    def test_invalid_ranks_and_unknown_records_are_refused(self):
        records = [(k + 1, float(self.spectrum[k])) for k in range(9)]
        with self.assertRaises(rft.TuningRefused):
            rft.observations_by_rank(records, declared={12: 3})
        with self.assertRaises(rft.TuningRefused):
            rft.observations_by_rank(records, excluded=(5,), declared={5: 6})
        for rank in (0, -2, rft.MAX_SURROGATE_RANK + 1):
            with self.subTest(rank=rank), self.assertRaises(rft.TuningRefused) as caught:
                rft.validate_correspondence(rft.observations_by_rank(records, declared={2: rank}) if rank > 0 else
                                            tuple(rft.Observation(o.record, o.hz, o.role, rank if o.record == 2 else o.surrogate_rank)
                                                  for o in rft.observations_by_rank(records)))
            self.assertIn("record 2", str(caught.exception))
        excluded_rank = tuple(rft.Observation(o.record, o.hz, o.role, o.surrogate_rank) for o in
                              rft.observations_by_rank(records, excluded=(9,)))
        rft.validate_correspondence(excluded_rank)  # an EXCLUDED record carries no rank and is not checked

    def test_the_declared_text_is_parsed_with_clear_messages(self):
        from new_gui import research_tuning_model as rm

        self.assertEqual(rm.parse_declared(" 3:4, 4 : 3 "), {3: 4, 4: 3})
        for text, part in (("3-4", "not record:rank"), ("3:4, 3:5", "more than once"), ("3:0", "a rank starts at 1"),
                           ("a:b", "not record:rank")):
            with self.subTest(text=text), self.assertRaises(ValueError) as caught:
                rm.parse_declared(text)
            self.assertIn(part, str(caught.exception))


class _PageHarness(unittest.TestCase):
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


class Page(_PageHarness):
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

    def test_an_invalid_correspondence_is_said_and_every_input_is_kept(self):
        window, panel, _inputs = self.loaded([(k + 1, 20.0 * (k + 1)) for k in range(8)])
        panel.set_role(2, rft.EXCLUDED)
        panel.declared.setText("3:4")  # ABM-AUD-1: excluding record 2 renumbers nothing, so record 4 still holds rank 4
        panel.search.setText("7")
        roles = panel.roles()
        self.assertFalse(panel.run())
        self.assertIn("rank 4 is assigned to records 3, 4", panel.message.text())
        self.assertTrue(panel.correspondence_note.isVisible())  # said beside the table too, before Run is pressed
        self.assertIn("rank 4 is assigned to records 3, 4", panel.correspondence_note.text())
        self.assertFalse(panel.busy())
        self.assertEqual((panel.declared.text(), panel.search.text(), panel.roles()), ("3:4", "7", roles))
        panel.declared.setText("2:3")  # an EXCLUDED record has no rank
        self.assertFalse(panel.run())
        self.assertIn("EXCLUDED", panel.message.text())

    def test_a_bad_setting_is_said_and_nothing_starts(self):
        window, panel, _inputs = self.loaded([(k + 1, 20.0 * (k + 1)) for k in range(8)])
        panel.search.setText("1")
        self.assertFalse(panel.run())
        self.assertIn("search range", panel.message.text())
        self.assertFalse(panel.busy())


class SavedResult(_PageHarness):
    """ABM: an exported Research Tuning result is reopened as saved: only that file is read, nothing is recomputed."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        surrogate = rft.Surrogate(rft.read_inp(_files() / "plate.inp"), 14, 16)
        cls.spectrum = surrogate.frequencies(60000, 44000, 4800)

    def shown(self, panel):
        def cells(table):
            return [[table.item(r, c).text() if table.item(r, c) else "" for c in range(table.columnCount())]
                    for r in range(table.rowCount())]

        return {"tables": {key: cells(table) for key, table in sorted(panel._tables.items())
                           if key not in ("inputs", "records")},  # the live input tables are not part of a result
                "status": panel.status.text(), "reasons": panel.reasons.text(), "accuracy": panel.accuracy.text(),
                "quality": panel.quality.text(), "validity": panel.validity.text(),
                "states": [w.property("state") for w in (panel.status, panel.quality, panel.validity)],
                "candidate_none": panel.candidate_none.text(), "stability": panel.stability_statement.text()}

    def exported(self, stability=True):
        """A FREE (mirror, both A/B) result, optionally with its stability check, exported; returns (path, shown, folder)."""
        window, panel, _inputs = self.loaded([(k + 1, float(self.spectrum[k])) for k in range(10)])
        panel.parameterization.setCurrentIndex(panel.parameterization.findData(rft.FREE))
        self.assertTrue(panel.run())
        self.wait(panel)
        self.assertEqual(panel.result.status, rft.MIRROR)
        if stability:
            self.assertTrue(panel.run_stability())
            self.wait(panel, 300)
            self.assertIsNotNone(panel.stability)
        folder = Path(tempfile.mkdtemp())
        target = folder / "proposal.json"
        self.assertTrue(panel.export(str(target)))
        return target, self.shown(panel), panel.plot_data

    def fresh(self):
        return self.window()[1]

    def test_a_saved_result_is_restored_identically_without_recalculation_or_source_access(self):
        from new_gui import research_tuning_model as rm
        from new_gui import research_tuning_panel as rtp

        target, before, _plot = self.exported(stability=True)
        document = json.loads(target.read_text(encoding="utf-8"))
        named = [document["sources"]["inp"], document["sources"]["unv"]]
        for name in named:  # the source files are gone: the saved result must not need them
            if Path(name).exists():
                Path(name).unlink()
        panel = self.fresh()
        opened = []
        real_open = open

        def recording_open(file, *args, **kwargs):
            opened.append(str(file))
            return real_open(file, *args, **kwargs)

        refuse = mock.Mock(side_effect=AssertionError("recomputed"))
        with mock.patch.object(rm, "read_sources", refuse), mock.patch.object(rft, "run_tuning", refuse), \
                mock.patch.object(rtp.rfs, "run_stability", refuse), mock.patch("builtins.open", recording_open), \
                mock.patch.object(rm, "_classify", refuse):
            self.assertTrue(panel.open_result(str(target)))
        self.app.processEvents()
        refuse.assert_not_called()
        self.assertFalse(panel.busy())
        self.assertEqual([Path(p).resolve() for p in opened if not p.endswith((".ttf", ".otf", ".json"))
                          and "matplotlib" not in p.lower()], [])
        self.assertTrue(all(Path(p).resolve() == target.resolve() for p in opened if p.endswith(".json")))
        self.assertEqual(self.shown(panel), before)  # every table, the status, the warnings and the stability, as saved
        self.assertEqual(len(panel.table_cells("axes")), 2)  # both A/B alternatives
        self.assertEqual(panel.parameterization.currentData(), rft.FREE)  # the setting shown matches the saved result
        self.assertTrue(panel.plot_data.startswith(b"\x89PNG"))
        self.assertTrue(panel.saved_note.isVisible())
        self.assertIn("SAVED RESULT", panel.saved_note.text())
        self.assertIn("not re-read or revalidated", panel.saved_note.text())
        self.assertFalse(panel.stability_button.isEnabled())
        self.assertFalse(panel.export_button.isEnabled())
        self.assertFalse(panel.run_button.isEnabled())  # no live inputs: nothing can be calculated
        self.assertFalse(panel.run_stability())
        self.assertFalse(panel.export(str(target.with_name("again.json"))))

    def test_invalid_files_are_refused_and_the_shown_result_is_kept(self):
        target, _before, _plot = self.exported(stability=False)
        panel = self.fresh()
        self.assertTrue(panel.open_result(str(target)))
        shown = self.shown(panel)
        document = json.loads(target.read_text(encoding="utf-8"))
        folder = target.parent
        bad = {"corrupt.json": "{ not json", "array.json": "[1, 2]",
               "schema.json": json.dumps(dict(document, schema="other/1")),
               "label.json": json.dumps(dict(document, label="A MATERIAL PROPERTY")),
               "missing.json": json.dumps({k: v for k, v in document.items() if k != "rows"}),
               "damaged.json": json.dumps(dict(document, rows=[{"record": 1}])),
               "cancelled.json": json.dumps(dict(document, status=rft.CANCELLED))}
        for name, text in bad.items():
            (folder / name).write_text(text, encoding="utf-8")
            self.assertFalse(panel.open_result(str(folder / name)), name)
            self.assertIn("Not opened", panel.message.text(), name)
            self.assertEqual(self.shown(panel), shown, name)
            self.assertEqual(panel.saved_path, str(target), name)
        self.assertFalse(panel.open_result(str(folder / "absent.json")))
        self.assertIn("cannot be read", panel.message.text())
        with self.assertRaises(rft.TuningRefused) as caught:
            rft.read_export(target, max_bytes=100)
        self.assertIn("at most", str(caught.exception))

    def test_choosing_live_inputs_ends_the_saved_view(self):
        target, _before, _plot = self.exported(stability=False)
        window, panel, _inputs = self.loaded([(k + 1, float(self.spectrum[k])) for k in range(10)])
        self.assertTrue(panel.open_result(str(target)))
        self.assertTrue(panel.run_button.isEnabled())  # the live inputs loaded before stay usable
        self.assertFalse(panel.export_button.isEnabled())
        panel.parameterization.setCurrentIndex(panel.parameterization.findData(rft.FREE))
        self.assertTrue(panel.run())
        self.wait(panel)
        self.assertIsNone(panel.saved_path)
        self.assertFalse(panel.saved_note.isVisible())
        self.assertTrue(panel.export_button.isEnabled() and panel.stability_button.isEnabled())


# ================================================================================================== ABM-AUD-1

LEGACY_EXPORT = Path(__file__).resolve().parent / "fixtures" / "research_tuning_export_8ae998d.json"


def _plate_inputs():
    return rft.read_inp(_files() / "plate.inp")


class StableRanks(unittest.TestCase):
    """ABM-AUD-1 A: the default rank of a record is its place in the frequency order of the FULL measured set. No role
    change renumbers another record; a declared rank moves the named record only; nothing invalid reaches the optimizer."""

    RECORDS = tuple((k, 20.0 * k) for k in range(1, 10))

    def ranks(self, records=None, **kw):
        return {o.record: o.surrogate_rank for o in rft.observations_by_rank(records or self.RECORDS, **kw)}

    def roles(self, **kw):
        return {o.record: o.role for o in rft.observations_by_rank(self.RECORDS, **kw)}

    def test_every_record_takes_its_place_in_the_full_set(self):
        self.assertEqual(self.ranks(), {k: k for k in range(1, 10)})
        self.assertEqual(set(self.roles().values()), {rft.FIT})
        self.assertEqual(rft.default_ranks(self.RECORDS), {k: k for k in range(1, 10)})

    def test_excluding_a_record_never_renumbers_another(self):
        for excluded in ((1,), (5,), (9,), (1, 4, 8), (2, 3), tuple(range(1, 9))):
            with self.subTest(excluded=excluded):
                ranks = self.ranks(excluded=excluded)
                self.assertEqual({r: k for r, k in ranks.items() if r not in excluded},
                                 {k: k for k in range(1, 10) if k not in excluded})
                self.assertEqual({ranks[r] for r in excluded}, {0})  # no active rank, and nobody takes its place
                roles = self.roles(excluded=excluded)
                self.assertEqual({r for r, role in roles.items() if role == rft.EXCLUDED}, set(excluded))

    def test_fit_holdout_and_excluded_can_be_changed_back_and_forth(self):
        base = self.ranks()
        self.assertEqual(self.ranks(holdout=(3, 9)), base)  # FIT -> HOLDOUT
        self.assertEqual(self.roles(holdout=(3, 9))[3], rft.HOLDOUT)
        self.assertEqual(self.ranks(holdout=(9,)), base)  # HOLDOUT -> FIT
        self.assertEqual(self.ranks(excluded=(3,))[4], 4)
        self.assertEqual(self.ranks(), base)  # EXCLUDED -> FIT restores the original correspondence
        self.assertEqual(self.ranks(holdout=(1,), excluded=(2,)), {**base, 2: 0})

    def test_unsorted_input_and_nonconsecutive_record_numbers(self):
        records = [(40, 95.0), (7, 20.0), (103, 61.5), (12, 33.0), (55, 140.25)]
        expected = {7: 1, 12: 2, 103: 3, 40: 4, 55: 5}  # by frequency; a record number is an identity, not a rank
        self.assertEqual(self.ranks(records), expected)
        for order in (sorted(records), sorted(records, key=lambda r: -r[1]), records[2:] + records[:2]):
            observations = rft.observations_by_rank(order, holdout=(55,), excluded=(12,))
            self.assertEqual([o.record for o in observations], [7, 12, 40, 55, 103])  # one deterministic order
            self.assertEqual({o.record: o.surrogate_rank for o in observations}, {**expected, 12: 0})
            self.assertEqual({o.record: o.hz for o in observations}, dict(records))  # identities and frequencies kept
        self.assertEqual(self.ranks([(2, 50.0), (1, 50.0), (3, 10.0)]), {3: 1, 1: 2, 2: 3})  # equal Hz: by record number

    def test_a_declared_rank_moves_the_named_record_only(self):
        ranks = self.ranks(excluded=(3,), declared={4: 3})  # record 4 declared at the rank the excluded record left
        self.assertEqual(ranks, {1: 1, 2: 2, 3: 0, 4: 3, 5: 5, 6: 6, 7: 7, 8: 8, 9: 9})
        rft.validate_correspondence(rft.observations_by_rank(self.RECORDS, excluded=(3,), declared={4: 3}))
        self.assertEqual(self.ranks(declared={9: 12})[9], 12)
        self.assertEqual({r: k for r, k in self.ranks(declared={9: 12}).items() if r != 9}, {k: k for k in range(1, 9)})

    def test_invalid_correspondences_are_refused_with_the_reason(self):
        cases = (({"declared": {3: 4}}, "rank 4 is assigned to records 3, 4"),  # a partial mapping against the defaults
                 ({"holdout": (9,), "declared": {9: 2}}, "rank 2 is assigned to records 2, 9"),  # FIT and HOLDOUT
                 ({"declared": {2: 0}}, "record 2: the rank 0 is not positive"),
                 ({"declared": {2: -3}}, "record 2: the rank -3 is not positive"),
                 ({"declared": {2: rft.MAX_SURROGATE_RANK + 1}}, "above the highest allowed rank"),
                 ({"declared": {2: 2.5}}, "record 2: the rank 2.5 is not a whole number"),
                 ({"declared": {2: "3"}}, "is not a whole number"),
                 ({"declared": {2: True}}, "is not a whole number"))
        for kw, part in cases:
            with self.subTest(kw=kw), self.assertRaises(rft.TuningRefused) as caught:
                rft.validate_correspondence(rft.observations_by_rank(self.RECORDS, **kw))
            self.assertIn(part, str(caught.exception))
        for kw, part in (({"declared": {12: 3}}, "record(s) 12 that the experimental set does not hold"),
                         ({"holdout": (77,)}, "HOLDOUT role names record(s) 77"),
                         ({"excluded": (0,)}, "EXCLUDED role names record(s) 0"),
                         ({"holdout": (4,), "excluded": (4,)}, "both HOLDOUT and EXCLUDED"),
                         ({"excluded": (5,), "declared": {5: 6}}, "EXCLUDED record(s) 5; an excluded record has no rank")):
            with self.subTest(kw=kw), self.assertRaises(rft.TuningRefused) as caught:
                rft.observations_by_rank(self.RECORDS, **kw)
            self.assertIn(part, str(caught.exception))
        with self.assertRaises(rft.TuningRefused) as caught:
            rft.observations_by_rank(self.RECORDS + ((4, 99.0),))
        self.assertIn("record(s) 4 more than once", str(caught.exception))
        self.assertEqual(self.ranks(declared={2: 2.0})[2], 2)  # a whole number written as a float is that whole number

    def test_no_optimizer_runs_on_an_invalid_correspondence(self):
        inputs = _plate_inputs()
        spectrum = rft.Surrogate(inputs, 10, 16).frequencies(42000, 42000, 6500)
        records = [(k + 1, float(spectrum[k])) for k in range(9)]
        good = rft.observations_by_rank(records, holdout=(9,))
        broken = (tuple(rft.Observation(o.record, o.hz, o.role, 0 if o.record == 2 else o.surrogate_rank) for o in good),
                  tuple(rft.Observation(o.record, o.hz, o.role, 3 if o.record == 9 else o.surrogate_rank) for o in good),
                  tuple(rft.Observation(o.record, o.hz, o.role, 2.5 if o.record == 4 else o.surrogate_rank) for o in good))
        refuse = AssertionError("the optimizer or the surrogate ran on an invalid correspondence")
        for observations in broken:
            with mock.patch.object(rft, "least_squares", side_effect=refuse), \
                    mock.patch.object(rft.Surrogate, "frequencies", side_effect=refuse):
                with self.assertRaises(rft.TuningRefused) as caught:
                    rft.run_tuning(inputs, rft.TuningRequest(observations, degree=10))
            self.assertIn("The frequency correspondence is invalid", str(caught.exception))

    def test_the_lowest_record_is_fitted_by_default_and_never_excluded_automatically(self):
        from new_gui import research_tuning_model as rm

        for count in (4, 6, 11):
            records = [(k, 18.6 * k) for k in range(1, count + 1)]
            holdout = rm.default_holdout(records)
            self.assertNotIn(1, holdout)
            observations = rft.observations_by_rank(records, holdout=holdout)
            lowest = min(observations, key=lambda o: o.hz)
            self.assertEqual((lowest.record, lowest.role, lowest.surrogate_rank), (1, rft.FIT, 1))
            self.assertFalse([o for o in observations if o.role == rft.EXCLUDED])  # nothing is excluded unless asked


class AuditFit(unittest.TestCase):
    """ABM-AUD-1 A and B on synthetic spectra of the surrogate itself: the correspondence a fit states, and the three
    separate statements (optimizer status, spectral fit quality, physical validity)."""

    @classmethod
    def setUpClass(cls):
        cls.inputs = _plate_inputs()
        cls.spectrum = rft.Surrogate(cls.inputs, 10, 16).frequencies(42000, 42000, 6500)
        cls.records = [(k + 1, float(cls.spectrum[k])) for k in range(9)]

    def fit(self, records=None, parameterization=rft.TIED, inputs=None, search_factor=10.0, holdout=(8, 9), **kw):
        observations = rft.observations_by_rank(records or self.records, holdout=holdout, **kw)
        request = rft.TuningRequest(observations, parameterization, rft.DECLARED if kw.get("declared") else rft.RANK_ORDER,
                                    search_factor, degree=10)
        return rft.run_tuning(inputs or self.inputs, request)

    def scaled(self, factors):
        return [(record, hz * factor) for (record, hz), factor in zip(self.records, factors)]

    def test_the_diagnostic_threshold_is_unchanged(self):
        self.assertEqual(rft.MISFIT_RMS, 0.02)
        self.assertEqual(rft.fit_verdict(0.02), rft.FIT_WITHIN)
        self.assertEqual(rft.fit_verdict(0.0200001), rft.HIGH_MISFIT)
        self.assertEqual(rft.fit_verdict(None), rft.FIT_NOT_ASSESSED)

    def test_exact_data_low_rms_and_three_separate_statements(self):
        result = self.fit()
        self.assertEqual(result.status, rft.SUPPORTED, result.reasons)
        quality = result.fit_quality
        self.assertEqual((quality["verdict"], quality["holdout_verdict"]), (rft.FIT_WITHIN, rft.HOLDOUT_WITHIN))
        self.assertLess(quality["fit_rms_ln"], 1e-8)
        self.assertEqual((quality["fit_count"], quality["holdout_count"], quality["threshold_ln"]), (7, 2, rft.MISFIT_RMS))
        self.assertEqual(result.candidate_presentation, rft.PROPOSAL)
        self.assertEqual(result.validity["physical_validation"], rft.NOT_ESTABLISHED)  # never from a small residual
        self.assertEqual(result.validity["material_property"], "NOT_A_MATERIAL_PROPERTY")
        self.assertIn("not a parameter accuracy and not a physical validation", quality["statement"])
        self.assertIn("NOT_A_MODE_IDENTITY", result.correspondence["identity"])
        self.assertIn("cannot show whether a measured mode is missing or extra", result.correspondence["identity_note"])
        self.assertEqual(result.label, rft.RESULT_LABEL)

    def test_excluding_the_first_record_keeps_every_other_rank_and_says_so(self):
        result = self.fit(excluded=(1,))
        self.assertEqual({r["record"]: r["rank"] for r in result.rows}, {1: None, **{k: k for k in range(2, 10)}})
        self.assertEqual(result.status, rft.SUPPORTED, result.reasons)
        self.assertAlmostEqual(result.fitted["E1"] / 42000, 1.0, places=5)  # records 2..9 are still ranks 2..9
        self.assertAlmostEqual(result.fitted["G12"] / 6500, 1.0, places=5)
        self.assertEqual(result.fit_quality["verdict"], rft.FIT_WITHIN)
        c = result.correspondence
        self.assertEqual((c["lowest_measured_record"], c["lowest_measured_role"]), (1, rft.EXCLUDED))
        self.assertEqual((c["excluded_records"], c["unmatched_ranks"], c["declared"]), ([1], [1], {}))
        said = " ".join(result.warnings)
        self.assertIn("The lowest measured record 1", said)
        self.assertIn("EXCLUDED by the user", said)
        self.assertIn("Record 2 stays at surrogate rank 2: it is not treated as the first mode", said)
        check = result.first_mode_check  # rank stability in the built-in check: record 2 leaves, nothing is renumbered
        self.assertEqual((check["lowest_measured_record"], check["lowest_measured_role"]), (1, rft.EXCLUDED))
        self.assertEqual((check["left_out_record"], check["left_out_rank"]), (2, 2))
        self.assertEqual(check["ranks_kept"], {k: k for k in range(3, 8)})

    def test_excluding_an_intermediate_record_keeps_every_other_rank(self):
        result = self.fit(excluded=(4,))
        self.assertEqual({r["record"]: r["rank"] for r in result.rows}, {**{k: k for k in range(1, 10)}, 4: None})
        self.assertAlmostEqual(result.fitted["G12"] / 6500, 1.0, places=5)
        self.assertEqual(result.correspondence["unmatched_ranks"], [4])
        self.assertEqual(result.first_mode_check["ranks_kept"], {2: 2, 3: 3, 5: 5, 6: 6, 7: 7})
        self.assertFalse([w for w in result.warnings if "lowest measured record" in w])  # record 1 is still fitted

    def test_the_audit_failure_class_is_a_high_misfit_and_never_a_proposal(self):
        """The mechanism the audit met: record 1 excluded and records 2..9 compared with ranks 1..8 (what the old default
        did silently; here it has to be declared). The optimizer converges and is NUMERICALLY_SUPPORTED at a 20 % RMS."""
        shifted = {k: k - 1 for k in range(2, 10)}
        result = self.fit(excluded=(1,), declared=shifted)
        self.assertEqual(result.status, rft.SUPPORTED)  # the optimizer status is not redefined
        self.assertTrue(all(start["success"] for start in result.starts))
        self.assertEqual(result.reasons, [])
        quality = result.fit_quality
        self.assertEqual(quality["verdict"], rft.HIGH_MISFIT)
        self.assertGreater(quality["fit_rms_ln"], 5 * rft.MISFIT_RMS)
        self.assertEqual(quality["fit_rms_ln"], result.rms_fit_after)  # the actual RMS, not a rounded verdict
        self.assertIn("do not adequately reproduce the measured spectrum", quality["statement"])
        self.assertGreater(result.fitted["G12"] / 6500, 2.0)  # an implausible shear modulus from the wrong correspondence
        self.assertEqual(result.candidate_presentation, rft.DIAGNOSTIC_ONLY)
        self.assertIsNotNone(result.candidate)  # the raw optimizer result is kept for investigation
        self.assertTrue(any(w.startswith("HIGH MISFIT") and "diagnostic only" in w for w in result.warnings))
        signed = [r["ln_after"] for r in result.rows if r["role"] == rft.FIT]
        self.assertTrue(min(signed) < 0 < max(signed))  # signed residuals per record are kept
        self.assertEqual(result.correspondence["declared"], shifted)
        self.assertEqual(len(result.starts), 3)
        self.assertTrue(result.minima and result.singular_values and result.practical_rank == 2)
        document = rft.export_document(result, self.inputs, {"inp": "plate.inp"})
        self.assertIsNone(document["abaqus_elastic_candidate"])  # no ready *Elastic block for a HIGH MISFIT
        self.assertNotIn("*Elastic, type", json.dumps(document))
        self.assertIn("HIGH MISFIT", document["abaqus_elastic_candidate_withheld"])
        self.assertIn("DIAGNOSTIC_ONLY", document["abaqus_elastic_candidate_withheld"])
        self.assertEqual(document["candidate"], result.candidate)  # the numbers stay in the report
        self.assertEqual(document["candidate_presentation"], rft.DIAGNOSTIC_ONLY)
        self.assertEqual(document["fit_quality"]["fit_rms_ln"], result.rms_fit_after)
        for part in ("Optimizer status: NUMERICALLY_SUPPORTED", "Spectral fit quality: HIGH_MISFIT",
                     "Physical validity: NOT_ESTABLISHED", rft.RESULT_LABEL):
            self.assertIn(part, document["statement"])

    def test_conflicting_frequencies_converge_to_a_high_misfit(self):
        result = self.fit(self.scaled([1.12, 0.88] * 4 + [1.12]))
        self.assertEqual(result.status, rft.SUPPORTED)
        self.assertEqual(result.fit_quality["verdict"], rft.HIGH_MISFIT)
        self.assertEqual(result.candidate_presentation, rft.DIAGNOSTIC_ONLY)
        self.assertEqual(result.fit_quality["holdout_verdict"], rft.HOLDOUT_DISAGREES)

    def test_small_noise_is_a_low_rms_proposal_without_any_accuracy_claim(self):
        result = self.fit(self.scaled([1.004, 0.996, 1.003, 0.997, 1.004, 0.996, 1.002, 0.998, 1.003]))
        self.assertEqual((result.status, result.fit_quality["verdict"]), (rft.SUPPORTED, rft.FIT_WITHIN))
        self.assertTrue(0.001 < result.fit_quality["fit_rms_ln"] < rft.MISFIT_RMS)
        self.assertEqual(result.candidate_presentation, rft.PROPOSAL)
        document = rft.export_document(result, self.inputs, {})
        self.assertTrue(document["abaqus_elastic_candidate"].startswith("*Elastic"))
        self.assertIsNone(document["abaqus_elastic_candidate_withheld"])
        self.assertIn("not a demonstrated or certified", result.accuracy_statement)
        self.assertEqual(result.validity["physical_validation"], rft.NOT_ESTABLISHED)

    def test_a_holdout_disagreement_is_reported_apart_from_an_acceptable_fit(self):
        result = self.fit([(r, hz * (1.3 if r == 9 else 1.0)) for r, hz in self.records])
        quality = result.fit_quality
        self.assertEqual((quality["verdict"], quality["holdout_verdict"]), (rft.FIT_WITHIN, rft.HOLDOUT_DISAGREES))
        self.assertEqual(quality["holdout_records_off"], [9])
        self.assertLess(quality["fit_rms_ln"], 1e-6)  # FIT and HOLDOUT are separate numbers
        self.assertGreater(quality["holdout_rms_ln"], 0.1)
        self.assertEqual((quality["fit_rms_ln"], quality["holdout_rms_ln"]), (result.rms_fit_after, result.rms_holdout_after))
        self.assertEqual(quality["largest_holdout_residual"]["record"], 9)
        self.assertIn("does not predict the frequencies it did not use", quality["statement"])

    def test_a_bound_gives_no_candidate_and_still_reports_the_fit_quality(self):
        result = self.fit([(k + 1, float(hz)) for k, hz in enumerate(
            rft.Surrogate(self.inputs, 10, 16).frequencies(60000, 44000, 4800)[:9])], search_factor=1.0001)
        self.assertEqual(result.status, rft.AT_BOUND)
        self.assertEqual(result.candidate_presentation, rft.NO_CANDIDATE)
        self.assertIn(result.fit_quality["verdict"], (rft.FIT_WITHIN, rft.HIGH_MISFIT))
        self.assertIn("optimizer status is PARAMETER_AT_BOUND",
                      rft.export_document(result, self.inputs, {})["abaqus_elastic_candidate_withheld"])

    def test_a_low_residual_does_not_hide_a_practical_rank_deficiency(self):
        from dataclasses import replace

        strip = replace(self.inputs, a_mm=1000.0, b_mm=10.0)  # a thin strip: its lowest modes are bending along x only
        spectrum = rft.Surrogate(strip, 10, 16).frequencies(42000, 42000, 6500)
        result = self.fit([(k + 1, float(spectrum[k])) for k in range(5)], inputs=strip, holdout=())
        self.assertEqual(result.status, rft.NOT_IDENTIFIABLE)  # G12 is not determined by these frequencies
        self.assertEqual(result.practical_rank, 1)
        self.assertIsNone(result.candidate)
        self.assertIsNone(result.estimates)
        self.assertEqual(result.fit_quality["verdict"], rft.FIT_WITHIN)  # the residual is tiny all the same
        self.assertEqual(result.fit_quality["holdout_verdict"], rft.NO_HOLDOUT)
        self.assertEqual(result.candidate_presentation, rft.NO_CANDIDATE)

    def test_starts_that_disagree_give_no_candidate(self):
        real, calls = rft.least_squares, []

        def second_start_elsewhere(*args, **kwargs):
            solution = real(*args, **kwargs)
            calls.append(1)
            if len(calls) == 2:  # the second start of the main fit ends at another, worse minimum
                solution.x = solution.x + math.log(1.25)
                solution.cost = solution.cost + 1.0
            return solution

        with mock.patch.object(rft, "least_squares", side_effect=second_start_elsewhere):
            result = self.fit()
        self.assertEqual(result.status, rft.STARTS_DISAGREE)
        self.assertEqual(len(result.minima), 2)
        self.assertIsNone(result.candidate)
        self.assertEqual(result.candidate_presentation, rft.NO_CANDIDATE)
        self.assertTrue(any("further minimum" in reason for reason in result.reasons))

    def test_the_exchanged_axes_keep_their_strict_handling(self):
        records = [(k + 1, float(hz)) for k, hz in enumerate(
            rft.Surrogate(self.inputs, 10, 16).frequencies(60000, 44000, 4800)[:9])]
        result = self.fit(records, parameterization=rft.FREE)
        self.assertEqual(result.status, rft.MIRROR)
        self.assertIsNone(result.candidate)
        self.assertEqual(result.candidate_presentation, rft.NO_CANDIDATE)
        self.assertEqual(result.fit_quality["verdict"], rft.FIT_WITHIN)
        document = rft.export_document(result, self.inputs, {})
        self.assertIsNone(document["abaqus_elastic_candidate"])
        self.assertIn("E1_E2_AXIS_ASSIGNMENT_NOT_IDENTIFIABLE", document["abaqus_elastic_candidate_withheld"])

    def test_a_cancelled_run_assesses_nothing(self):
        cancel = threading.Event()
        cancel.set()
        request = rft.TuningRequest(rft.observations_by_rank(self.records, holdout=(8, 9)), degree=10)
        result = rft.run_tuning(self.inputs, request, cancel=cancel)
        self.assertEqual(result.status, rft.CANCELLED)
        self.assertEqual(result.fit_quality["verdict"], rft.FIT_NOT_ASSESSED)
        self.assertEqual(result.candidate_presentation, rft.NO_CANDIDATE)

    def test_the_same_request_gives_the_same_result(self):
        def text(result):
            return json.dumps(result.to_dict(), default=str, sort_keys=True)

        self.assertEqual(text(self.fit(excluded=(4,), declared={9: 11})), text(self.fit(excluded=(4,), declared={9: 11})))
        self.assertEqual(text(self.fit(self.records[::-1])), text(self.fit(self.records)))  # the input order does not matter

    def test_an_export_is_read_back_as_it_was_written(self):
        result = self.fit(excluded=(1,), declared={k: k - 1 for k in range(2, 10)})
        target = rft.write_export(rft.export_document(result, self.inputs, {"inp": "plate.inp"}),
                                  Path(tempfile.mkdtemp()) / "proposal.json")
        with mock.patch.object(rft, "least_squares", side_effect=AssertionError("refitted")):
            restored = rft.result_from_export(rft.read_export(target))
        self.assertEqual(json.dumps(restored.to_dict(), default=str, sort_keys=True),
                         json.dumps(json.loads(json.dumps(result.to_dict(), default=str)), default=str, sort_keys=True))
        self.assertEqual(restored.fit_quality["verdict"], rft.HIGH_MISFIT)
        self.assertFalse(restored.fit_quality["derived_when_opened"])
        self.assertEqual(restored.correspondence["ranks"], {k: k - 1 for k in range(2, 10)})  # integer record keys again

    def test_a_file_cannot_talk_a_high_misfit_into_a_proposal(self):
        result = self.fit(self.scaled([1.12, 0.88] * 4 + [1.12]))
        document = json.loads(json.dumps(rft.export_document(result, self.inputs, {}), default=str))
        document["candidate_presentation"] = rft.PROPOSAL  # edited by hand
        self.assertEqual(rft.result_from_export(document).candidate_presentation, rft.DIAGNOSTIC_ONLY)
        document["fit_quality"] = dict(document["fit_quality"], verdict=rft.FIT_WITHIN)
        with self.assertRaises(rft.TuningRefused) as caught:
            rft.result_from_export(document)
        self.assertIn("does not follow from its own residuals", str(caught.exception))
        document["fit_quality"] = "fine"
        with self.assertRaises(rft.TuningRefused):
            rft.result_from_export(document)

    def test_an_export_of_the_earlier_version_is_still_read_and_is_qualified(self):
        """A file written by the code at 8ae998d: record 1 EXCLUDED, records 2..9 renumbered to ranks 1..8, converged,
        with a ready *Elastic block at a 20 % RMS. It opens as saved, without a refit, and is qualified as HIGH MISFIT."""
        document = json.loads(LEGACY_EXPORT.read_text(encoding="utf-8"))
        self.assertEqual(document["schema"], rft.SCHEMA)
        self.assertFalse(set(rft.ADDED_FIELDS) & set(document))  # really the earlier representation
        self.assertTrue(document["abaqus_elastic_candidate"].startswith("*Elastic"))
        refuse = AssertionError("recomputed")
        with mock.patch.object(rft, "least_squares", side_effect=refuse), \
                mock.patch.object(rft.Surrogate, "frequencies", side_effect=refuse):
            result = rft.result_from_export(document)
        self.assertEqual((result.status, result.rms_fit_after), (rft.SUPPORTED, document["rms_fit_after"]))
        self.assertEqual(result.candidate, document["candidate"])  # the saved numbers, untouched
        self.assertEqual({r["record"]: r["rank"] for r in result.rows}, {1: None, **{k: k - 1 for k in range(2, 10)}})
        quality = result.fit_quality
        self.assertEqual(quality["verdict"], rft.HIGH_MISFIT)
        self.assertTrue(quality["derived_when_opened"])
        self.assertAlmostEqual(quality["fit_rms_ln"], document["rms_fit_after"], places=12)
        self.assertEqual(result.candidate_presentation, rft.DIAGNOSTIC_ONLY)
        self.assertTrue(result.correspondence["legacy_renumbered_ranks"])
        self.assertIn("Saved by an earlier program version", result.correspondence["notes"][0])
        self.assertEqual(result.correspondence["declared"], {})  # the old renumbering is not passed off as a user's choice
        self.assertEqual(result.validity["physical_validation"], rft.NOT_ESTABLISHED)


class AuditPage(_PageHarness):
    """ABM-AUD-1 C: what the Research Tuning page shows and keeps, on synthetic spectra."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.spectrum = rft.Surrogate(_plate_inputs(), 10, 16).frequencies(45000, 45000, 6000)

    def records(self, factors=None, count=10):
        factors = factors or [1.0] * count
        return [(k + 1, float(self.spectrum[k]) * factors[k]) for k in range(count)]

    def ready(self, records=None):
        window, panel, inputs = self.loaded(records or self.records())
        panel.degree.setText("10")
        return window, panel

    def run_fit(self, panel):
        self.assertTrue(panel.run(), panel.message.text())
        self.wait(panel)
        self.assertIsNotNone(panel.result)
        return panel.result

    def cells(self, panel, key):
        return {row[0]: row[1] for row in panel.table_cells(key)}

    def test_the_rank_column_follows_the_roles_and_the_declared_ranks(self):
        window, panel = self.ready()
        from PySide6.QtWidgets import QLabel, QPushButton

        block = panel._tables["records"]
        texts = [label.text() for label in block.findChildren(QLabel)]
        for header in ("EXP record", "Frequency (Hz)", "Role", "Surrogate rank (hypothesis)"):
            self.assertIn(header, texts)
        # every role is a named button of its own, so assistive technology can read and press it (no cell widgets)
        buttons = {b.objectName(): b for b in block.findChildren(QPushButton)}
        self.assertEqual(sorted(buttons), sorted(f"tuningRole_{k}_{role}" for k in range(1, 11)
                                                 for role in (rft.FIT, rft.HOLDOUT, rft.EXCLUDED)))
        self.assertEqual(buttons["tuningRole_3_EXCLUDED"].accessibleName(), "Record 3: EXCLUDED")
        self.assertEqual([role for role in (rft.FIT, rft.HOLDOUT, rft.EXCLUDED) if buttons[f"tuningRole_9_{role}"].isChecked()],
                         [rft.HOLDOUT])  # exactly one role is on
        buttons["tuningRole_3_HOLDOUT"].click()  # a press is a role change, like set_role
        self.assertEqual(panel.roles()[3], rft.HOLDOUT)
        self.assertFalse(buttons["tuningRole_3_FIT"].isChecked())
        buttons["tuningRole_3_FIT"].click()
        self.assertEqual(block.findChild(QLabel, "tuningRank_7").text(), "7")
        default = {k: str(k) for k in range(1, 11)}
        self.assertEqual(panel.rank_texts(), default)
        self.assertEqual(panel.roles()[1], rft.FIT)  # the lowest record is fitted unless the user says otherwise
        self.assertFalse(panel.correspondence_note.isVisible())
        panel.set_role(1, rft.EXCLUDED)
        shown = panel.rank_texts()
        self.assertTrue(shown[1].startswith("—") and "no other record takes rank 1" in shown[1], shown[1])
        self.assertEqual({k: v for k, v in shown.items() if k != 1}, {k: v for k, v in default.items() if k != 1})
        panel.set_role(5, rft.HOLDOUT)
        panel.set_role(6, rft.EXCLUDED)
        shown = panel.rank_texts()
        self.assertEqual([shown[k] for k in (2, 3, 4, 5, 7, 8, 9, 10)], ["2", "3", "4", "5", "7", "8", "9", "10"])
        self.assertEqual({o.record: o.surrogate_rank for o in panel.build_request().observations},
                         {1: 0, 2: 2, 3: 3, 4: 4, 5: 5, 6: 0, 7: 7, 8: 8, 9: 9, 10: 10})  # what is shown is what is fitted
        panel.set_role(1, rft.FIT)
        panel.set_role(6, rft.FIT)
        panel.set_role(5, rft.FIT)
        self.assertEqual(panel.rank_texts(), default)
        panel.declared.setText("3:12")
        self.assertEqual(panel.rank_texts()[3], "12 (declared; default 3)")
        self.assertEqual({k: v for k, v in panel.rank_texts().items() if k != 3}, {k: v for k, v in default.items() if k != 3})

    def test_an_invalid_correspondence_is_refused_in_words_before_anything_runs(self):
        window, panel = self.ready()
        for text, part in (("3:4", "rank 4 is assigned to records 3, 4"), ("3:0", "a rank starts at 1"),
                           ("44:2", "record(s) 44 that the experimental set does not hold"),
                           ("2:61", "above the highest allowed rank 60"), ("3-4", "not record:rank")):
            with self.subTest(text=text):
                panel.declared.setText(text)
                self.assertTrue(panel.correspondence_note.isVisible())
                self.assertIn(part, panel.correspondence_note.text())
                with mock.patch.object(rft, "run_tuning", side_effect=AssertionError("started")):
                    self.assertFalse(panel.run())
                self.assertIn("Not started", panel.message.text())
                self.assertIn(part, panel.message.text())
                self.assertFalse(panel.busy())
        panel.set_role(2, rft.EXCLUDED)
        panel.declared.setText("2:3")
        self.assertIn("EXCLUDED record(s) 2", panel.correspondence_note.text())
        panel.declared.setText("")
        self.assertFalse(panel.correspondence_note.isVisible())

    def test_a_good_fit_is_shown_as_research_with_three_separate_statements(self):
        window, panel = self.ready()
        result = self.run_fit(panel)
        self.assertEqual((result.status, result.fit_quality["verdict"]), (rft.SUPPORTED, rft.FIT_WITHIN))
        self.assertIn("OPTIMIZER: NUMERICALLY_SUPPORTED", panel.status.text())
        self.assertIn(rft.RESULT_LABEL, panel.status.text())  # NOT_A_MATERIAL_PROPERTY, NOT_VALIDATED_IN_ABAQUS
        self.assertIn("SPECTRAL FIT: FIT RMS 0.00%, within the 2% diagnostic threshold", panel.quality.text())
        self.assertIn("HOLDOUT RMS", panel.quality.text())
        self.assertIn("PHYSICAL VALIDITY: NOT ESTABLISHED", panel.validity.text())
        self.assertEqual([w.property("state") for w in (panel.status, panel.quality, panel.validity)],
                         ["chosen", "chosen", "blocked"])
        self.assertTrue(all(w.isVisible() for w in (panel.status, panel.quality, panel.validity)))
        self.assertFalse(panel.estimate_note.isVisible())
        table = panel._tables["candidate"]
        self.assertEqual(table.horizontalHeaderItem(2).text(), "Candidate (MPa)")
        self.assertIn("not validated in Abaqus and not a material property", panel.candidate_none.text())
        quality = self.cells(panel, "fit_quality")
        self.assertEqual(quality["Spectral fit quality"], rft.FIT_WITHIN)
        self.assertEqual(quality["Diagnostic threshold (unchanged)"], "2%")
        correspondence = self.cells(panel, "correspondence")
        self.assertIn("NOT_A_MODE_IDENTITY", correspondence["Kind"])
        self.assertEqual(correspondence["Record -> surrogate rank"], ", ".join(f"{k} -> {k}" for k in range(1, 11)))
        self.assertEqual(self.cells(panel, "diagnostics")["Physical validity"], rft.NOT_ESTABLISHED)

    def test_a_bad_fit_is_unmistakable_and_its_diagnostics_stay(self):
        window, panel = self.ready(self.records([1.12, 0.88] * 5))
        result = self.run_fit(panel)
        self.assertEqual(result.status, rft.SUPPORTED)  # the optimizer did converge
        self.assertIn("OPTIMIZER: NUMERICALLY_SUPPORTED", panel.status.text())
        self.assertIn("SPECTRAL FIT: HIGH MISFIT", panel.quality.text())
        self.assertIn(f"FIT RMS {result.rms_fit_after:.2%}", panel.quality.text())  # the actual RMS, in the headline
        self.assertGreater(result.rms_fit_after, 0.08)
        self.assertEqual([w.property("state") for w in (panel.status, panel.quality, panel.validity)],
                         ["blocked", "blocked", "blocked"])  # no success colour anywhere
        self.assertTrue(panel.quality.isVisible())
        self.assertIn("HIGH MISFIT", panel.reasons.text())
        self.assertTrue(panel.estimate_note.isVisible())
        self.assertIn("DIAGNOSTIC ONLY", panel.estimate_note.text())
        self.assertEqual(panel._tables["estimates"].horizontalHeaderItem(0).text(), "Optimizer result (diagnostic only)")
        self.assertEqual(panel._tables["candidate"].horizontalHeaderItem(2).text(), "DIAGNOSTIC ONLY, HIGH MISFIT (MPa)")
        self.assertIn("DIAGNOSTIC ONLY — NOT A PROPOSAL", panel.candidate_none.text())
        self.assertTrue(panel.candidate_none.isVisible())
        self.assertEqual(len(panel.table_cells("candidate")), 3)  # the numbers are still there to investigate
        for key, rows in (("frequencies", 10), ("minima", 1), ("sensitivity", 8), ("first_mode", 4)):
            self.assertGreaterEqual(len(panel.table_cells(key)), rows, key)
        diagnostics = self.cells(panel, "diagnostics")
        self.assertEqual(diagnostics["Spectral fit quality"], rft.HIGH_MISFIT)
        self.assertEqual(diagnostics["Candidate presentation"], rft.DIAGNOSTIC_ONLY)
        self.assertIn("Start 1 from", " ".join(diagnostics))
        self.assertTrue(panel.plot_data.startswith(b"\x89PNG"))
        self.assertIn("HIGH_MISFIT", panel.state.text())

    def test_export_and_reopen_keep_the_meaning_of_a_bad_fit(self):
        window, panel = self.ready(self.records([1.12, 0.88] * 5))
        result = self.run_fit(panel)
        saved = SavedResult.shown(self, panel)
        target = Path(tempfile.mkdtemp()) / "proposal.json"
        self.assertTrue(panel.export(str(target)))
        document = json.loads(target.read_text(encoding="utf-8"))
        self.assertIsNone(document["abaqus_elastic_candidate"])
        self.assertNotIn("*Elastic, type", target.read_text(encoding="utf-8"))
        self.assertEqual(document["fit_quality"]["verdict"], rft.HIGH_MISFIT)
        self.assertEqual(document["fit_quality"]["fit_rms_ln"], result.rms_fit_after)
        self.assertEqual(document["candidate"]["G12"], result.candidate["G12"])
        self.assertEqual(document["correspondence"]["identity"], result.correspondence["identity"])
        self.assertTrue(any(w.startswith("HIGH MISFIT") for w in document["warnings"]))
        self.assertIn("NOT_A_MATERIAL_PROPERTY", document["label"])
        other = self.window()[1]
        refuse = mock.Mock(side_effect=AssertionError("recomputed"))
        with mock.patch.object(rft, "run_tuning", refuse), mock.patch.object(rft, "least_squares", refuse):
            self.assertTrue(other.open_result(str(target)))
        self.app.processEvents()
        refuse.assert_not_called()
        self.assertEqual(SavedResult.shown(self, other), saved)  # the same tables, statements and colours
        self.assertIn("SAVED RESULT", other.saved_note.text())
        self.assertTrue(other.saved_note.isVisible())

    def test_an_export_of_the_earlier_version_opens_as_saved_and_qualified(self):
        from new_gui import research_tuning_model as rm
        from new_gui import research_tuning_panel as rtp

        panel = self.window()[1]
        refuse = mock.Mock(side_effect=AssertionError("recomputed or re-read"))
        with mock.patch.object(rm, "read_sources", refuse), mock.patch.object(rft, "run_tuning", refuse), \
                mock.patch.object(rft, "least_squares", refuse), mock.patch.object(rtp.rfs, "run_stability", refuse), \
                mock.patch.object(rft, "read_inp", refuse):
            self.assertTrue(panel.open_result(str(LEGACY_EXPORT)), panel.message.text())
        self.app.processEvents()
        refuse.assert_not_called()
        self.assertFalse(panel.busy())
        self.assertIn("SAVED RESULT", panel.saved_note.text())
        self.assertIn("SPECTRAL FIT: HIGH MISFIT — FIT RMS 20.36%", panel.quality.text())
        self.assertEqual(panel.status.property("state"), "blocked")
        self.assertEqual(panel._tables["candidate"].horizontalHeaderItem(2).text(), "DIAGNOSTIC ONLY, HIGH MISFIT (MPa)")
        quality = self.cells(panel, "fit_quality")
        self.assertIn("Derived from the saved residuals", quality["Origin"])
        self.assertIn("nothing was re-fitted", quality["Origin"])
        notes = " ".join(row[1] for row in panel.table_cells("correspondence"))
        self.assertIn("Saved by an earlier program version", notes)
        self.assertEqual([row[2] for row in panel.table_cells("frequencies")], ["—"] + [str(k) for k in range(1, 9)])
        self.assertFalse(panel.export_button.isEnabled() or panel.stability_button.isEnabled())

    def test_a_result_never_outlives_the_settings_it_was_made_with(self):
        window, panel = self.ready()

        def cleared():
            self.assertIsNone(panel.result)
            self.assertIsNone(panel.request)
            self.assertFalse(panel.results_card.isVisible())
            self.assertEqual(panel.state.text(), rm_stale())
            for key in ("estimates", "candidate", "frequencies", "fit_quality", "correspondence", "diagnostics"):
                self.assertNotIn(key, panel._tables, key)
            self.assertEqual((panel.status.text(), panel.quality.text()), ("", ""))
            self.assertFalse(panel.export_button.isEnabled() or panel.stability_button.isEnabled())

        def rm_stale():
            from new_gui import research_tuning_model as rm

            return rm.STALE_TEXT

        edits = ((lambda: panel.set_role(4, rft.HOLDOUT), lambda: panel.set_role(4, rft.FIT)),
                 (lambda: panel.set_role(1, rft.EXCLUDED), lambda: panel.set_role(1, rft.FIT)),
                 (lambda: panel.declared.setText("10:12"), lambda: panel.declared.setText("")),
                 (lambda: panel.search.setText("8"), lambda: panel.search.setText("10")),
                 (lambda: panel.degree.setText("11"), lambda: panel.degree.setText("10")),
                 (lambda: panel.parameterization.setCurrentIndex(panel.parameterization.findData(rft.FREE)),
                  lambda: panel.parameterization.setCurrentIndex(panel.parameterization.findData(rft.TIED))))
        for edit, back in edits:
            self.run_fit(panel)
            self.assertTrue(panel.results_card.isVisible())
            panel.search.setText("10.0")  # the same setting written differently: the result stays
            panel.declared.setText("  ")
            self.assertIsNotNone(panel.result)
            panel.search.setText("10")
            panel.declared.setText("")
            self.assertIsNotNone(panel.result)
            edit()
            cleared()
            back()  # back to the settings of the cleared result: nothing stale returns
            cleared()
        panel.set_role(1, rft.EXCLUDED)
        result = self.run_fit(panel)  # a new run shows the result of the settings on the page
        self.assertEqual({r["record"]: r["rank"] for r in result.rows}, {1: None, **{k: k for k in range(2, 11)}})
        self.assertIn("The lowest measured record 1", panel.reasons.text())
        self.assertIn("EXCLUDED by the user", panel.reasons.text())
        self.assertIn("1", self.cells(panel, "correspondence")["EXCLUDED records (no rank)"])
        self.assertEqual(panel.rank_texts()[2], "2")
        self.assertIn("record 1 is EXCLUDED by the user", self.cells(panel, "first_mode")["Lowest measured record"])

    def test_a_running_fit_holds_the_roles_and_a_late_worker_is_ignored(self):
        window, panel = self.ready()
        first = self.run_fit(panel)
        panel.set_role(1, rft.EXCLUDED)
        self.assertIsNone(panel.result)
        self.assertTrue(panel.run())
        self.assertFalse(any(combo.isEnabled() for combo in panel.role_combos.values()))  # no role change under a fit
        self.assertFalse(panel.declared.isEnabled())
        panel._bridge.done.emit(panel._token - 1, "fit", first)  # the worker of the earlier request reports late
        self.app.processEvents()
        self.assertIsNot(panel.result, first)
        self.wait(panel)
        self.assertIsNot(panel.result, first)
        self.assertEqual({r["record"]: r["rank"] for r in panel.result.rows}[1], None)  # the result of the new request
        self.assertEqual(panel.result.request["observations"], [o.__dict__ for o in panel.request.observations])
        self.assertTrue(all(combo.isEnabled() for combo in panel.role_combos.values()))
        self.assertTrue(panel.run())
        self.assertTrue(panel.cancel())
        self.wait(panel)
        self.assertTrue(panel.result is None or panel.result.status == rft.CANCELLED or panel.result.rows)
        self.assertTrue(panel.run_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
