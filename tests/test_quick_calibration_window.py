"""The stand-alone quick-calibration window, driven headlessly with the fake Abaqus (needs Tk and a display)."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import quick_calibration_support as S  # noqa: E402

try:
    import tkinter as tk

    _ROOT = tk.Tk()
    _ROOT.withdraw()
    _ROOT.destroy()
    TK_AVAILABLE = True
except Exception:  # noqa: BLE001 - no Tk or no display
    TK_AVAILABLE = False


@unittest.skipUnless(TK_AVAILABLE, "Tk with a display is required")
class QuickCalibrationWindowTests(unittest.TestCase):
    def setUp(self):
        from quick_calibration_window import QuickCalibrationWindow

        self.folder = Path(tempfile.mkdtemp())
        (self.folder / "model.inp").write_text(S.INP)
        S.write_experiment(self.folder / "exp.unv", 0.9 * S.E0, S.G0, noise=0.001)
        self.root = tk.Tk()
        self.root.withdraw()
        self.fake = S.FakeAbaqus()
        self.window = QuickCalibrationWindow(self.root, self.fake.solve, self.fake.extract, threaded=False)

    def tearDown(self):
        self.root.destroy()
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_inp_selection_fills_materials_and_defaults(self):
        self.window.set_inp(str(self.folder / "model.inp"))
        self.assertEqual(list(self.window.material_box["values"]), ["CFRP_Face", "PLA_core"])
        self.assertEqual(self.window.material.get(), "CFRP_Face")
        self.assertEqual(self.window.constants.get(), "E1,E2")
        self.assertTrue(self.window.out.get().endswith("model_quick_calibration"))
        self.window.material.set("PLA_core")
        self.window._material_changed()
        self.assertEqual(self.window.constants.get(), "E")

    def test_orientation_choice_then_result(self):
        window = self.window
        window.set_inp(str(self.folder / "model.inp"))
        window.unv.set(str(self.folder / "exp.unv"))
        window.start()
        self.assertIn("Orientation is ambiguous", window.summary.get())
        choices = list(window.orientation_box["values"])
        self.assertGreaterEqual(len(choices), 2)
        identity = next(c for c in choices if c.startswith("exp X = +FE X, exp Y = +FE Y, exp Z = +FE Z"))
        window.orientation.set(identity)
        window.start()
        self.assertTrue(window.summary.get().startswith("GOOD"), window.summary.get())
        self.assertAlmostEqual(window.result["estimates"]["E_face"]["multiplier"], 0.9, delta=0.005)
        self.assertTrue((Path(window.out.get()) / "config.json").is_file())
        self.assertEqual(str(window.open_button["state"]), "normal")
        self.assertIn("QUICK EFFECTIVE-PROPERTY CALIBRATION", window.log.get("1.0", "end"))


if __name__ == "__main__":
    unittest.main()
