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
        self.assertIn("[PASS]", reference["Total mass in the .dat"])
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
        self.assertFalse(summary.reference.verified)
        self.assertIn("Not used", dict(rm.solid_reference_rows(summary))["Use"])
        rows = rm.solid_frequency_rows({"frequencies_hz": list(self.direct)}, summary)
        self.assertEqual(rows[0][2:], ("—", "—", "—"))

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
