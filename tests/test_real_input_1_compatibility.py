"""ABM-REAL-INPUT-1: Research Tuning says exactly why an Abaqus INP can or cannot be used. Synthetic INP fixtures only:
shell (supported), solid, continuum shell, mixed, missing definitions, *Include and unsupported material models."""

from __future__ import annotations

import builtins
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from services import research_frequency_tuning as rft  # noqa: E402

MATERIAL = """*Material, name=CFRP_T300_TEST
*Density
 1.498e-09,
*Elastic, type=ENGINEERING CONSTANTS
56700.,41600., 8500.,  0.05,   0.3,   0.3, 4770., 3000.
 3000.,
"""
STEP = """*Step, name=Modal, perturbation
*Frequency, eigensolver=Lanczos
20, , , , ,
*End Step
"""
SHELL_NODES = """*Node
      1,           0.,           0.,           0.
      2,         301.,           0.,           0.
      3,         301.,         300.,           0.
      4,           0.,         300.,           0.
"""
SHELL = ("*Heading\n*Part, name=P\n" + SHELL_NODES + "*Element, type=S4R\n1, 1, 2, 3, 4\n"
         "*Shell Section, elset=Set-1, material=CFRP_T300_TEST\n0.875, 5\n*End Part\n" + MATERIAL + STEP)
SOLID_NODES = "".join(f"{n + 1}, {x:g}, {y:g}, {z:g}\n" for n, (x, y, z) in enumerate(
    [(x, y, z) for z in (0.0, 0.875) for y in (0.0, 300.0) for x in (0.0, 301.0)]))
SOLID = ("*Heading\n*Part, name=P\n*Node\n" + SOLID_NODES + "*Element, type=C3D8I\n1, 1, 2, 4, 3, 5, 6, 8, 7\n"
         "*Orientation, name=Ori-1\n1., 0., 0., 0., 1., 0.\n3, 0.\n"
         "*Solid Section, elset=Set-1, orientation=Ori-1, material=CFRP_T300_TEST\n,\n*End Part\n" + MATERIAL + STEP)


def _write(text: str, name: str = "model.inp", folder: Path = None) -> Path:
    folder = folder or Path(tempfile.mkdtemp())
    path = folder / name
    path.write_text(text, encoding="latin-1")
    return path


class Inspection(unittest.TestCase):
    def test_the_supported_shell_model_still_reads_with_its_own_values(self):
        path = _write(SHELL)
        report = rft.inspect_inp(path)
        self.assertEqual(report.verdict, rft.COMPATIBLE)
        self.assertTrue(report.supported)
        inputs = rft.read_inp(path)
        self.assertEqual((inputs.E1, inputs.E2, inputs.G12, inputs.thickness_mm, inputs.a_mm, inputs.b_mm),
                         (56700.0, 41600.0, 4770.0, 0.875, 301.0, 300.0))

    def test_a_solid_model_is_refused_without_conversion_or_an_invented_thickness(self):
        path = _write(SOLID)
        report = rft.inspect_inp(path)
        self.assertEqual(report.verdict, rft.SOLID_MODEL)
        self.assertFalse(report.supported)
        self.assertIn("C3D8I", report.reason)
        self.assertIn("*Solid Section", report.reason)
        self.assertIn("not converted to a shell", report.reason)
        self.assertIn(rft.SOLID_BACKEND_NOTE, report.reason)
        self.assertNotIn("0.875", report.reason)
        facts = dict(report.facts)
        self.assertEqual(facts["Elements"], "C3D8I: 1 (solid)")
        self.assertEqual(facts["Sections"], "*Solid Section, material CFRP_T300_TEST, orientation Ori-1")
        self.assertEqual(facts["Material CFRP_T300_TEST"], "*Density 1.498e-09; *Elastic ENGINEERING CONSTANTS (9 values)")
        self.assertEqual(facts["Node extent x × y × z"], "301 × 300 × 0.875 (8 nodes)")
        self.assertNotIn("Shell thickness", facts)
        with self.assertRaises(rft.InpNotSupported) as caught:
            rft.read_inp(path)
        self.assertIsInstance(caught.exception, rft.TuningRefused)
        self.assertEqual(caught.exception.report, report)

    def test_continuum_shell_and_mixed_families_are_named(self):
        report = rft.inspect_inp(_write(SOLID.replace("C3D8I", "SC8R")))
        self.assertEqual(report.verdict, rft.SOLID_MODEL)
        self.assertIn("Continuum-shell model (SC8R)", report.reason)
        mixed = SHELL.replace("*Shell Section", "*Element, type=C3D8\n2, 1, 2, 3, 4, 1, 2, 3, 4\n*Shell Section")
        report = rft.inspect_inp(_write(mixed))
        self.assertEqual(report.verdict, rft.MIXED_ELEMENTS)
        self.assertIn("S4R, C3D8", report.reason)

    def test_each_missing_definition_is_named(self):
        report = rft.inspect_inp(_write(SHELL.replace("*Density\n 1.498e-09,\n", "")))
        self.assertEqual((report.verdict, report.reason), (rft.MISSING_DEFINITION, "The INP has no *Density."))
        report = rft.inspect_inp(_write(SHELL.replace(MATERIAL, "")))
        self.assertEqual((report.verdict, report.reason), (rft.MISSING_DEFINITION, "The INP has no *Material."))
        report = rft.inspect_inp(_write(SHELL.replace("*Shell Section, elset=Set-1, material=CFRP_T300_TEST\n0.875, 5\n", "")))
        self.assertEqual((report.verdict, report.reason), (rft.MISSING_DEFINITION, "The INP has no *Shell Section."))

    def test_definitions_in_an_included_file_are_named_and_the_file_is_not_read(self):
        folder = Path(tempfile.mkdtemp())
        _write(MATERIAL, "material.inp", folder)
        path = _write(SHELL.replace(MATERIAL, "*Include, input=material.inp\n*Include, input=absent.inp\n"), folder=folder)
        opened = []
        real_open = builtins.open

        def spy(file, *args, **kwargs):
            opened.append(str(file))
            return real_open(file, *args, **kwargs)

        with mock.patch("builtins.open", spy), mock.patch("io.open", spy):
            report = rft.inspect_inp(path)
        self.assertEqual(report.verdict, rft.IN_INCLUDE)
        self.assertEqual(report.includes, (("material.inp", True), ("absent.inp", False)))
        self.assertIn("*Material is not in this file; it may be in the included file(s) material.inp (found), absent.inp "
                      "(not found)", report.reason)
        self.assertIn("does not follow *Include", report.reason)
        self.assertFalse([name for name in opened if name.endswith("material.inp")])
        self.assertEqual(dict(report.facts)["*Include"], "material.inp (found beside the INP, not read); "
                                                          "absent.inp (not found beside the INP, not read)")

    def test_unsupported_material_models_are_refused_with_the_reason(self):
        isotropic = SHELL.replace("*Elastic, type=ENGINEERING CONSTANTS\n56700.,41600., 8500.,  0.05,   0.3,   0.3, 4770., "
                                  "3000.\n 3000.,\n", "*Elastic\n70000., 0.3\n")
        report = rft.inspect_inp(_write(isotropic))
        self.assertEqual(report.verdict, rft.UNSUPPORTED_MATERIAL)
        self.assertIn("*Elastic type ISOTROPIC with 2 values", report.reason)
        temperature = SHELL.replace(" 3000.,\n", " 3000., 20.\n56000.,41000., 8400.,  0.05,   0.3,   0.3, 4700., 3000.\n"
                                    " 3000., 80.\n")
        report = rft.inspect_inp(_write(temperature))
        self.assertEqual(report.verdict, rft.UNSUPPORTED_MATERIAL)
        self.assertIn("holds 20 values; this tool reads one temperature-independent set of 9", report.reason)
        report = rft.inspect_inp(_write(SHELL.replace("*Density", "*Hyperelastic\n1., 2.\n*Density")))
        self.assertEqual(report.verdict, rft.UNSUPPORTED_MATERIAL)
        self.assertIn("*Hyperelastic", report.reason)


class ModelLayer(unittest.TestCase):
    def test_a_solid_model_is_a_read_failure_with_its_report_and_the_exp_file_is_not_read(self):
        from new_gui import research_tuning_model as rm

        path = _write(SOLID)
        with mock.patch.object(rm.pm, "run_read", side_effect=AssertionError("EXP read")):
            with self.assertRaises(rm.ReadFailed) as caught:
                rm.read_sources(path, "exp.unv", mock.Mock())
        self.assertEqual(caught.exception.compatibility.verdict, rft.SOLID_MODEL)
        self.assertTrue(str(caught.exception).startswith("The INP could not be used: Solid model (C3D8I"))
        with self.assertRaises(rm.ReadFailed):
            rm.check_model(path)
        self.assertEqual(rm.check_model(_write(SHELL)).verdict, rft.COMPATIBLE)

    def test_the_notes_name_what_stays_available_and_enable_nothing(self):
        from new_gui import research_tuning_model as rm

        folder = Path(tempfile.mkdtemp())
        path = _write(SOLID, "NEW.inp", folder)
        report = rft.inspect_inp(path)
        self.assertEqual(rm.compatibility_notes(report), rm.ANALYZE_NOTE)
        (folder / "NEW.odb").write_bytes(b"x")
        self.assertIn("NEW.odb is beside the INP. This does not enable Research Tuning.", rm.compatibility_notes(report))
        (folder / "NEW_modal_packages").mkdir()
        self.assertIn("NEW.odb is beside the INP, with extracted modes in NEW_modal_packages; Analyze uses them without "
                      "Abaqus when they match that ODB. This does not enable Research Tuning.", rm.compatibility_notes(report))
        self.assertEqual(rm.compatibility_notes(rft.inspect_inp(_write(SHELL))), "")


class PageDisplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def panel(self):
        from new_gui import production_window as pw

        window = pw.ProductionWindow()
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        window.resize(1366, 768)
        window.show()
        window.show_page(pw.TUNING_PAGE)
        self.app.processEvents()
        return window.research_tuning

    def wait(self, panel, limit=30.0):
        end = time.monotonic() + limit
        while panel.busy() and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()

    def test_a_solid_model_shows_the_reason_what_was_read_and_what_stays_available(self):
        panel = self.panel()
        self.assertFalse(panel.compat_verdict.isVisible())
        panel.choose_file("inp", str(_write(SOLID)))
        self.wait(panel)
        self.assertTrue(panel.compat_title.isVisible() and panel.compat_verdict.isVisible())
        self.assertTrue(panel.compat_verdict.text().startswith("Solid model (C3D8I, *Solid Section)"))
        self.assertEqual(panel.compat_verdict.objectName(), "warnings")
        cells = dict(map(tuple, panel.table_cells("compatibility")))
        self.assertEqual(cells["Elements"], "C3D8I: 1 (solid)")
        self.assertIn("Still available: the Analyze page", panel.compat_notes.text())
        self.assertEqual(panel.message.text(), "Research Tuning cannot use this INP; the model check above says why.")
        self.assertFalse(panel.run_button.isEnabled())
        self.assertIsNone(panel.sources)

    def test_a_shell_model_shows_one_compatible_sentence_and_the_file_choice_stays_free(self):
        from new_gui import research_tuning_model as rm

        panel = self.panel()
        panel.choose_file("inp", str(_write(SOLID)))
        self.wait(panel)
        shell = _write(SHELL)
        panel.choose_file("inp", str(shell))
        self.wait(panel)
        self.assertTrue(panel.compat_verdict.text().startswith("Shell model (S4R"))
        self.assertEqual(panel.compat_verdict.objectName(), "hint")
        self.assertNotIn("compatibility", panel._tables)
        self.assertFalse(panel.compat_notes.isVisible())
        self.assertFalse(panel.message.isVisible())
        sources = rm.Sources(rft.read_inp(shell), None, (), (), "unavailable (test)", "exp.unv", "0" * 64, "Set",
                             ((1, 20.0), (2, 40.0), (3, 60.0)), rft.inspect_inp(shell))
        with mock.patch.object(rm, "read_sources", return_value=sources):
            panel.choose_file("unv", "exp.unv")
            self.wait(panel)
        self.assertIs(panel.sources, sources)
        self.assertTrue(panel.run_button.isEnabled())
        self.assertTrue(panel.compat_verdict.text().startswith("Shell model (S4R"))


if __name__ == "__main__":
    unittest.main()
