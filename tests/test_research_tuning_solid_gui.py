"""ABM-SOLID-5: the solid offline FE mode of the Research Tuning page (synthetic C3D8I models only)."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OMP_NUM_THREADS", "1")
ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "src", ROOT / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import numpy as np  # noqa: E402

from services import solid_c3d8i_model as sm  # noqa: E402
from services import solid_c3d8i_solver as ss  # noqa: E402
from services import solid_forward_runner as sfr  # noqa: E402
from test_real_input_1_compatibility import SHELL  # noqa: E402
from test_solid_c3d8i_model import box_inp  # noqa: E402

DIMENSIONS = dict(nx=6, ny=3, nz=1, lx=60.0, ly=30.0, lz=5.0)


def write_dat(path: Path, elements: int, nodes: int, mass: float, elastic_hz) -> None:
    rows = [f"       {i + 1}*    1.0E-04     1.0E-02     1.0E-03     1.0000         0.0000" for i in range(6)]
    rows += [f"      {i + 7}      1.0E+06     1.0E+03     {hz:.5g}         1.0000         0.0000"
             for i, hz in enumerate(elastic_hz)]
    path.write_text("\n".join([
        "                            P R O B L E M   S I Z E", "",
        f"          NUMBER OF ELEMENTS IS                                 {elements}",
        f"          NUMBER OF NODES DEFINED BY THE USER                   {nodes}", "",
        "                    TOTAL MASS OF MODEL", "", f"                      {mass:.7E}", "",
        "                              E I G E N V A L U E    O U T P U T", "",
        " MODE NO      EIGENVALUE              FREQUENCY         GENERALIZED MASS   COMPOSITE MODAL DAMPING",
        "                             (RAD/TIME)   (CYCLES/TIME)", "", *rows, "",
        " ***NOTE: EIGENVALUES MARKED WITH A * APPEAR TO BE RIGID BODY MODES"]), encoding="latin-1")


class SolidPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])
        folder = Path(tempfile.mkdtemp())
        cls.inp = folder / "BOX.inp"
        cls.inp.write_text(box_inp(**DIMENSIONS), encoding="latin-1")
        cls.direct = ss.SolidForwardModel(sm.load_solid_inp(cls.inp)).solve(14).frequencies_hz
        # a synthetic "Abaqus" .dat, +0.1 %, written with 5 significant digits as Abaqus does
        cls.reference = [float(f"{float(f) * 1.001:.5g}") for f in cls.direct]
        write_dat(cls.inp.with_suffix(".dat"), 18, 56, 2.7e-9 * 60 * 30 * 5, cls.reference)

    def panel(self, confirm=True):
        from new_gui import production_window as pw

        window = pw.ProductionWindow()
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        window.resize(1366, 768)
        window.show()
        window.show_page(pw.TUNING_PAGE)
        self.app.processEvents()
        panel = window.research_tuning
        self.asked = []

        def ask(title, text):
            self.asked.append(text)
            return confirm

        panel._ask_confirm = ask
        self.addCleanup(panel.shutdown)
        return panel

    def wait(self, panel, limit=120.0):
        end = time.monotonic() + limit
        while panel.busy() and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()

    def cells(self, panel, key):
        return dict(map(tuple, panel.table_cells(key)))

    def test_a_solid_inp_opens_the_separate_solid_mode_with_identity_and_unchanged_values(self):
        panel = self.panel()
        panel.choose_file("inp", str(self.inp))
        self.wait(panel)
        self.assertTrue(panel.solid_card.isVisible())
        identity = self.cells(panel, "solid_identity")
        self.assertEqual(identity["Elements"], "18 C3D8I")
        self.assertEqual(identity["Degrees of freedom"], "168")
        self.assertEqual(identity["SHA-256"], sfr.sha256_of(self.inp))
        self.assertEqual(identity["Abaqus element equivalence"], "NOT_VERIFIED")
        material = self.cells(panel, "solid_material")
        self.assertEqual(material["E1 (original, used)"], "70000 MPa")
        self.assertEqual(material["G12 (original, used)"], "9000 MPa")
        self.assertEqual(material["E3 (fixed)"], "15000 MPa")
        reference = self.cells(panel, "solid_reference")
        self.assertIn("[PASS]", reference["Total mass in the .dat (consistency)"])
        self.assertTrue(reference["Provenance (same material and FE model)"].startswith("UNVERIFIED"))
        self.assertTrue(panel.solid_run_button.isEnabled())
        self.assertFalse(panel.run_button.isEnabled())  # the shell tuning stays unavailable for this INP
        self.assertIn("solid offline FE section", panel.message.text())
        self.assertIsNone(panel.solid_outcome)  # nothing is calculated until started and confirmed

    def test_a_declined_confirmation_runs_nothing(self):
        panel = self.panel(confirm=False)
        panel.choose_file("inp", str(self.inp))
        self.wait(panel)
        with mock.patch.object(sfr, "run", side_effect=AssertionError("solve started")):
            self.assertFalse(panel.run_solid())
        self.assertEqual(len(self.asked), 1)
        self.assertIn("Not started", panel.solid_state.text())
        self.assertIsNone(panel.solid_outcome)

    def test_one_confirmed_supervised_solve_shows_frequencies_diagnostics_and_fe_fe_differences(self):
        panel = self.panel()
        panel.choose_file("inp", str(self.inp))
        self.wait(panel)
        self.assertTrue(panel.run_solid())
        self.wait(panel)
        text = self.asked[0]
        for part in ("ONE offline FE calculation", sfr.sha256_of(self.inp), "E1 70000", "G12 9000", "unchanged",
                     "No fitting, no repetition, no Abaqus"):
            self.assertIn(part, text)
        outcome = panel.solid_outcome
        self.assertEqual(outcome.status, sfr.SOLVED, outcome.message)
        self.assertIn(sfr.RESULT_LABEL, panel.solid_status.text())
        rows = panel.table_cells("solid_frequencies")
        self.assertEqual(len(rows), 14)
        self.assertEqual(rows[0][1], f"{self.direct[0]:.4f}")  # the first elastic mode is kept
        self.assertEqual(rows[0][2], f"{self.reference[0]:g}")
        self.assertAlmostEqual(float(rows[0][4]), -0.1, places=2)  # (offline - .dat) / .dat
        self.assertTrue(panel.solid_fe_note.isVisible())
        self.assertIn("PROVISIONAL", panel.solid_fe_note.text())
        table = panel._tables["solid_frequencies"]
        headers = [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]
        self.assertTrue(all("PROVISIONAL" in h for h in headers[2:]), headers)
        diagnostics = self.cells(panel, "solid_diagnostics")
        self.assertIn("verified inside the supervision job", diagnostics["Worker process"])
        self.assertEqual(diagnostics["Worker processes still running after the run"], "0")
        self.assertNotEqual(diagnostics["Peak memory, all worker processes (measured by Windows)"], "—")
        self.assertIn("passed", diagnostics["Rigid-body modes"])
        self.assertIn("NOT_VERIFIED", diagnostics["Element"])
        self.assertEqual(len(self.asked), 1)  # one confirmation, one solve, no repetition

    def test_cancelling_terminates_the_worker(self):
        panel = self.panel()
        panel.choose_file("inp", str(self.inp))
        self.wait(panel)
        self.assertTrue(panel.run_solid())
        self.assertTrue(panel.cancel_solid())
        self.wait(panel)
        outcome = panel.solid_outcome
        self.assertEqual(outcome.status, sfr.CANCELLED)
        self.assertIn(outcome.active_processes_after, (0, None))
        self.assertNotIn("solid_frequencies", panel._tables)

    def test_not_enough_memory_disables_the_calculation(self):
        panel = self.panel()
        with mock.patch.object(sfr, "available_memory_bytes", return_value=0):
            panel.choose_file("inp", str(self.inp))
            self.wait(panel)
        self.assertEqual(panel.solid.preflight["decision"], "REFUSE")
        self.assertIn("NOT ALLOWED", panel.solid_resources.text())
        self.assertFalse(panel.solid_run_button.isEnabled())
        self.assertFalse(panel.run_solid())
        self.assertEqual(self.asked, [])

    def test_a_mismatched_dat_is_not_used_for_differences(self):
        from new_gui import research_tuning_model as rm

        folder = Path(tempfile.mkdtemp())
        inp = folder / "OTHER.inp"
        inp.write_text(box_inp(**DIMENSIONS), encoding="latin-1")
        write_dat(inp.with_suffix(".dat"), 19, 56, 2.7e-9 * 60 * 30 * 5, self.reference)
        summary = rm.check_solid(inp)
        self.assertFalse(summary.reference.consistent)
        self.assertIn("Not used", dict(rm.solid_reference_rows(summary))["Use"])
        rows = rm.solid_frequency_rows({"frequencies_hz": list(self.direct)}, summary)
        self.assertEqual(rows[0][2:], ("—", "—", "—"))

    def test_equal_mesh_and_mass_with_other_material_is_never_verified_and_differences_are_provisional(self):
        """ABM-SOLID-5-F1: a .dat from a model with the same mesh and mass but different material constants passes
        every consistency check, so those checks can never be shown as proof of identity."""
        from new_gui import research_tuning_model as rm
        from test_solid_c3d8i_model import ENGINEERING

        folder = Path(tempfile.mkdtemp())
        stiffer = folder / "STIFFER.inp"  # E1 and G12 changed, same mesh, same density, same mass
        constants = list(ENGINEERING)
        constants[0], constants[6] = 2 * constants[0], 2 * constants[6]
        stiffer.write_text(box_inp(**DIMENSIONS, constants=tuple(constants)), encoding="latin-1")
        other_material_hz = ss.SolidForwardModel(sm.load_solid_inp(stiffer)).solve(14).frequencies_hz
        inp = folder / "ORIGINAL.inp"
        inp.write_text(box_inp(**DIMENSIONS), encoding="latin-1")
        write_dat(inp.with_suffix(".dat"), 18, 56, 2.7e-9 * 60 * 30 * 5, [float(f"{f:.5g}") for f in other_material_hz])
        summary = rm.check_solid(inp)
        reference = summary.reference
        self.assertTrue(all(state == "PASS" for _, _, state in reference.checks))  # consistency passes ...
        self.assertTrue(reference.consistent)
        self.assertEqual(reference.provenance, "UNVERIFIED")  # ... but identity is never claimed
        self.assertFalse(hasattr(reference, "verified"))
        reference_rows = dict(rm.solid_reference_rows(summary))
        self.assertTrue(reference_rows["Provenance (same material and FE model)"].startswith("UNVERIFIED"))
        self.assertIn("PROVISIONAL", reference_rows["Use"])
        self.assertIn("Elements in the .dat (consistency)", reference_rows)
        for row_name, value in reference_rows.items():
            self.assertNotIn("VERIFIED", value.replace("UNVERIFIED", ""), row_name)
        for header in rm.SOLID_FREQUENCY_HEADERS[2:]:
            self.assertIn("PROVISIONAL", header)
        self.assertIn("PROVISIONAL", rm.SOLID_FE_FE_NOTE)
        self.assertIn("UNVERIFIED", rm.SOLID_FE_FE_NOTE)
        rows = rm.solid_frequency_rows({"frequencies_hz": list(self.direct)}, summary)
        self.assertLess(float(rows[0][4]), -20.0)  # the large material difference is visible, labelled PROVISIONAL

    # ------------------------------------------------------------------------------------------ ABM-SOLID-6 What-If

    POINTS = ((60000.0, 25000.0, 7000.0), (90000.0, 15000.0, 11000.0))

    def checked(self, confirm=True):
        panel = self.panel(confirm)
        panel.choose_file("inp", str(self.inp))
        self.wait(panel)
        return panel

    def test_what_if_points_show_the_original_values_and_one_confirmation_lists_every_solve(self):
        panel = self.checked()
        self.assertFalse(panel.whatif_button.isEnabled())  # nothing entered, nothing pre-filled
        self.assertEqual(panel.whatif_fields[0][0].text(), "")
        self.assertEqual(panel.whatif_fields[0][0].placeholderText(), "INP 70000")
        panel.set_whatif(self.POINTS)
        self.assertTrue(panel.whatif_button.isEnabled())
        self.assertIn("2 points ready: 2 FE solves", panel.whatif_check.text())
        table = panel._tables["whatif_parameters"]
        self.assertEqual([table.horizontalHeaderItem(i).text() for i in range(table.columnCount())],
                         ["Parameter", "Original INP", "Point 1", "Point 2"])
        rows = {r[0]: r[1:] for r in panel.table_cells("whatif_parameters")}
        self.assertEqual(rows["E1 (MPa)"], ["70000", "60000 (-14.29 %)", "90000 (+28.57 %)"])
        self.assertEqual(rows["G12 (MPa)"][0], "9000")
        self.assertTrue(rows["Other constants, density"][0].startswith("E3 15000"))
        self.assertEqual(rows["Other constants, density"][1:], ["same as the INP", "same as the INP"])
        self.assertTrue(panel.run_whatif())
        self.wait(panel)
        self.assertEqual(len(self.asked), 1)
        text = self.asked[0]
        for part in ("Run 2 offline FE calculations", sfr.sha256_of(self.inp), "Original INP: E1 70000, E2 20000, G12 9000",
                     "Point 1: E1 60000, E2 25000, G12 7000 MPa", "Point 2: E1 90000, E2 15000, G12 11000 MPa",
                     "Total FE solves: 2", "No search, no fitting"):
            self.assertIn(part, text)
        outcome = panel.whatif_outcome
        self.assertEqual(outcome.status, sfr.SOLVED, outcome.message)
        self.assertIsNone(panel.solid_outcome)  # the single INP-value result is a separate calculation
        self.assertIn(sfr.WHATIF_LABEL, panel.whatif_status.text())
        self.assertIn("2 of 2 points solved", panel.whatif_status.text())
        freq = panel._tables["whatif_frequencies"]
        self.assertEqual([freq.horizontalHeaderItem(i).text() for i in range(freq.columnCount())],
                         ["Elastic mode", "Point 1 (Hz)", "Point 2 (Hz)", "Point 2 vs Point 1 (%)"])
        cells = panel.table_cells("whatif_frequencies")
        self.assertEqual(len(cells), 14)
        model = sm.load_solid_inp(self.inp)
        for column, (e1, e2, g12) in zip((1, 2), self.POINTS):
            expected = ss.SolidForwardModel(model).solve(14, e1=e1, e2=e2, g12=g12).frequencies_hz
            self.assertEqual([row[column] for row in cells], [f"{f:.4f}" for f in expected])
        first, second = float(cells[0][1]), float(cells[0][2])
        self.assertAlmostEqual(float(cells[0][3]), 100 * (second - first) / first, places=2)
        self.assertTrue(panel.whatif_note.isVisible())
        diagnostics = self.cells(panel, "whatif_diagnostics")
        self.assertIn("mass matrix reused for every point: yes", diagnostics["Model reuse"])
        self.assertTrue(diagnostics["Point 1 (E1 60000, E2 25000, G12 7000)"].startswith("SOLVED"))
        self.assertIn("e1 90000", diagnostics["Point 2 material used"])
        self.assertIn("e3 15000", diagnostics["Point 2 material used"])
        self.assertEqual(diagnostics["Worker processes still running after the run"], "0")
        self.assertIn("verified inside the supervision job", diagnostics["Worker process"])

    def test_a_declined_what_if_confirmation_runs_nothing(self):
        panel = self.checked(confirm=False)
        panel.set_whatif(self.POINTS[:1])
        with mock.patch.object(sfr, "run", side_effect=AssertionError("solve started")):
            self.assertFalse(panel.run_whatif())
        self.assertEqual(len(self.asked), 1)
        self.assertIn("Total FE solves: 1", self.asked[0])
        self.assertIn("not confirmed", panel.solid_state.text())
        self.assertIsNone(panel.whatif_outcome)

    def test_invalid_what_if_entries_are_explained_and_never_run(self):
        panel = self.checked()
        for rows, part in (([("60000", "", "7000")], "Row 1: Enter all of E1, E2 and G12"),
                           ([("60000", "-1", "7000")], "Row 1: E2 must be positive"),
                           ([("abc", "1", "1")], "Row 1: E1 is not a number"),
                           ([("1", "1", "nan")], "Row 1: G12 must be a finite"),
                           ([self.POINTS[0], self.POINTS[0]], "Two rows are identical"),
                           ([("", "", ""), ("1", "2", "0")], "Row 2: G12 must be positive")):
            with self.subTest(rows=rows):
                panel.set_whatif(rows)
                self.assertIn(part, panel.whatif_check.text())
                self.assertFalse(panel.whatif_button.isEnabled())
                self.assertNotIn("whatif_parameters", panel._tables)
                with mock.patch.object(sfr, "run", side_effect=AssertionError("solve started")):
                    self.assertFalse(panel.run_whatif())
        self.assertEqual(self.asked, [])  # no confirmation was even asked for

    def test_cancelling_what_if_terminates_the_worker_and_reports_each_point(self):
        panel = self.checked()
        panel.set_whatif(self.POINTS)
        self.assertTrue(panel.run_whatif())
        self.assertTrue(panel.cancel_solid())
        self.wait(panel)
        outcome = panel.whatif_outcome
        self.assertEqual(outcome.status, sfr.CANCELLED)
        self.assertIn(outcome.active_processes_after, (0, None))
        self.assertIn("0 of 2 points solved", panel.whatif_status.text())
        diagnostics = self.cells(panel, "whatif_diagnostics")
        self.assertIn("NOT_RUN", diagnostics["Point 2 (E1 90000, E2 15000, G12 11000)"])

    def test_partial_what_if_results_are_shown_with_the_failed_point(self):
        panel = self.checked()
        panel.set_whatif(self.POINTS)
        direct = [float(f) for f in self.direct]
        outcome = sfr.RunnerOutcome(status=sfr.PARTIAL, message="1 of 2 What-If points solved; point 2 FAILED.",
                                    result={"reuse": {"one_forward_model": True, "mass_matrix_reused_for_every_point": True,
                                                      "points_attempted": 2}}, worker_pid=1, worker_in_job=True,
                                    active_processes_after=0)
        fake = {"frequencies_hz": direct, "guard_frequencies_hz": [1.0], "relative_spacing": [0.1],
                "max_backward_error": 1e-14, "mass_orthogonality_error": 1e-14, "shift": -1.0, "shift_source": "ritz_bound",
                "operator_applications": 10, "factor_nonzeros": 100, "seconds": {"total": 0.1},
                "material": {"e1": 60000.0}, "density": 2.7e-9, "rigid": {"passed": True, "c2e0": "PASS"},
                "formulation": "C3D8I", "abaqus_equivalence": "NOT_VERIFIED"}
        outcome.points = [{"index": 1, "parameters": dict(zip(("e1", "e2", "g12"), self.POINTS[0])), "status": "SOLVED",
                           "result": fake, "error": None, "mass_matrix_reused": True},
                          {"index": 2, "parameters": dict(zip(("e1", "e2", "g12"), self.POINTS[1])), "status": "FAILED",
                           "result": None, "error": {"kind": "RIGID_BODY_CLASSIFICATION_FAILED", "message": "synthetic"}}]
        panel._show_whatif_outcome(outcome)
        cells = panel.table_cells("whatif_frequencies")
        self.assertEqual(cells[0][1:], [f"{direct[0]:.4f}", "FAILED", "—"])
        self.assertIn("PARTIAL: 1 of 2 points solved", panel.whatif_status.text())
        diagnostics = self.cells(panel, "whatif_diagnostics")
        self.assertIn("FAILED: RIGID_BODY_CLASSIFICATION_FAILED: synthetic — not retried",
                      diagnostics["Point 2 (E1 90000, E2 15000, G12 11000)"])

    def test_the_single_inp_value_solve_is_unchanged_next_to_what_if(self):
        panel = self.checked()
        panel.set_whatif(self.POINTS[:1])
        self.assertTrue(panel.run_solid())  # the original one-solve button still runs the INP values only
        self.wait(panel)
        self.assertEqual(panel.solid_outcome.status, sfr.SOLVED)
        self.assertEqual(panel.solid_outcome.result["material"]["e1"], 70000.0)
        self.assertEqual(panel.solid_outcome.points, [])
        self.assertIsNone(panel.whatif_outcome)
        self.assertIn("ONE offline FE calculation", self.asked[0])
        panel.choose_file("inp", str(self.inp))  # a new INP check clears the points of the previous model
        self.wait(panel)
        self.assertEqual(panel.whatif_fields[0][0].text(), "")
        self.assertIsNone(panel.solid_outcome)

    def test_the_shell_workflow_is_unchanged(self):
        panel = self.panel()
        shell = Path(tempfile.mkdtemp()) / "shell.inp"
        shell.write_text(SHELL, encoding="latin-1")
        panel.choose_file("inp", str(shell))
        self.wait(panel)
        self.assertFalse(panel.solid_card.isVisible())
        self.assertIsNone(panel.solid)
        self.assertTrue(panel.compat_verdict.text().startswith("Shell model (S4R"))
        self.assertFalse(panel.message.isVisible())
        panel.choose_file("inp", str(self.inp))  # switching to a solid INP and back clears the solid mode
        self.wait(panel)
        self.assertTrue(panel.solid_card.isVisible())
        panel.choose_file("inp", str(shell))
        self.wait(panel)
        self.assertFalse(panel.solid_card.isVisible())
        self.assertIsNone(panel.solid)


if __name__ == "__main__":
    unittest.main()
