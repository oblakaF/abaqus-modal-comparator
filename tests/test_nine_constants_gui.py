"""NINE-EC Phase G: the research nine-constant view inside the main application (Tk with a display; no Abaqus)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import quick_calibration_support as S  # noqa: E402
from test_nine_constants_model import TWO_MATERIALS  # noqa: E402
from test_quick_calibration_ui import _Application  # noqa: E402


def _no_abaqus(*_args, **_kwargs):
    raise AssertionError("the research view must never start Abaqus or any process")


class NineConstantsViewTests(_Application, unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="nine_gui_"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.inp = self.folder / "model.inp"
        self.inp.write_text(S.INP)
        self.unv = self.folder / "exp.unv"
        S.write_experiment(self.unv, 0.9 * S.E0, S.G0, noise=0.001)
        for target in ("services.quick_calibration.AbaqusRunner", "subprocess.Popen"):
            patcher = mock.patch(target, side_effect=_no_abaqus)
            patcher.start()
            self.addCleanup(patcher.stop)

    def window(self):
        import tkinter as tk
        from nine_constants_window import NineConstantsWindow

        try:
            root = tk.Tk()
        except Exception as error:  # noqa: BLE001
            self.skipTest(f"Tk is unavailable: {error}")
        root.withdraw()
        self.addCleanup(lambda: root.destroy() if root.winfo_exists() else None)
        return NineConstantsWindow(tk.Toplevel(root), threaded=False)

    def rows(self, window) -> list[tuple]:
        return [tuple(window.table.item(item, "values")) for item in window.table.get_children()]

    def quick_result(self, inp_sha: str, unv_sha: str) -> Path:
        """A Quick Calibration result.json of the same files (test data with the real record structure)."""
        path = self.folder / "result.json"
        path.write_text(json.dumps({
            "status": "ESTIMATE", "overall_grade": "APPROXIMATE",
            "inputs": {"model_inp_sha256": inp_sha, "experiment_sha256": unv_sha, "modal_set": "polymax"},
            "rows": [{"row_id": "X4", "experimental_hz": 94.4, "baseline_fe_mode": 10, "pair_mac": 0.958},
                     {"row_id": "X7", "experimental_hz": 205.6, "baseline_fe_mode": 13, "pair_mac": 0.947}],
            "estimates": {"E_face": {"multiplier": 1.14, "band_percent": 10.3,
                                     "constants": {"E1": {}, "E2": {}}}}}), encoding="utf-8")
        return path

    def test_the_view_opens_inside_the_main_application(self):
        import tkinter as tk
        import quick_calibration_ui as ui

        application = self.start_application()
        menu = application.workflow_menu
        labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) == "command"]
        self.assertIn(ui.NINE_LABEL + "...", labels)
        window = application._open_nine_constants()
        self.assertIsInstance(window.root, tk.Toplevel)
        self.assertIs(window.root.master, self.root)  # no second Tk root
        self.assertIs(application._open_nine_constants(), window)
        self.assertIn("RESEARCH_DIAGNOSTIC_ONLY", window.root.children[next(iter(window.root.children))]
                      .winfo_children()[0].cget("text"))

    def test_two_files_give_nine_rows_without_abaqus(self):
        window = self.window()
        window.set_inp(str(self.inp))
        self.assertEqual(window.material.get(), "CFRP_Face")  # the only eligible material is used automatically
        window.set_unv(str(self.unv))
        self.assertTrue(window.modal_set.get().startswith("PolyMAX"))  # the only modal set
        window.run_diagnostic()
        rows = self.rows(window)
        self.assertEqual([r[0] for r in rows], ["E1", "E2", "E3", "nu12", "nu13", "nu23", "G12", "G13", "G23"])
        self.assertEqual({r[5] for r in rows}, {"not evaluated"})
        self.assertEqual({r[2] for r in rows}, {"-"})  # no estimated value without evidence
        self.assertEqual(rows[0][1], "52,000")
        units = dict((r[0], r[4]) for r in rows)  # an INP declares no stress unit: never shown as MPa
        self.assertEqual({units[n] for n in ("E1", "E2", "E3", "G12", "G13", "G23")},
                         {"INP stress units (unspecified)"})
        self.assertEqual({units[n] for n in ("nu12", "nu13", "nu23")}, {"dimensionless"})
        self.assertTrue(window.headline.get().startswith("No constant can be determined"), window.headline.get())
        self.assertIn("NOT_A_VALIDATED_MATERIAL_PROPERTY", window.text.get("1.0", "end"))

    def test_frozen_rows_bound_the_rank_and_the_effective_value_stays_separate(self):
        window = self.window()
        window.set_inp(str(self.inp))
        window.set_unv(str(self.unv))
        inp_sha = hashlib.sha256(self.inp.read_bytes()).hexdigest()
        unv_sha = hashlib.sha256(self.unv.read_bytes()).hexdigest()
        window.result_file.set(str(self.quick_result(inp_sha, unv_sha)))
        window.run_diagnostic()
        self.assertEqual({r[5] for r in self.rows(window)}, {"not identifiable"})
        text = window.text.get("1.0", "end")
        self.assertIn("rank <= 2", text)
        self.assertIn("Separate effective FE-model calibration", text)
        self.assertIn("NOT independent per-constant values", text)
        self.quick_result("0" * 64, unv_sha)  # another model's result is refused, never reused
        window.run_diagnostic()
        self.assertTrue(window.headline.get().startswith("FAILED"), window.headline.get())
        self.assertIn("cannot be used", window.headline.get())

    def test_several_materials_need_an_explicit_choice(self):
        two = self.folder / "two.inp"
        two.write_text(TWO_MATERIALS)
        window = self.window()
        window.set_inp(str(two))
        self.assertEqual(list(window.material_box["values"]), ["Face_A", "Skin_B"])
        self.assertEqual(window.material.get(), "Select...")
        window.set_unv(str(self.unv))
        window.run_diagnostic()
        self.assertTrue(window.headline.get().startswith("CHOICE REQUIRED"), window.headline.get())
        window.material.set("Skin_B")  # a shell section: E3, ν13, ν23 cannot act on its spectrum
        window.run_diagnostic()
        statuses = dict((r[0], r[5]) for r in self.rows(window))
        self.assertEqual({statuses[n] for n in ("E3", "nu13", "nu23")}, {"not identifiable"})

    def test_synthetic_demonstration_and_report_files(self):
        window = self.window()
        window.case.set("two_rows")
        window.run_demo()
        self.assertEqual({r[5] for r in self.rows(window)}, {"not identifiable"})
        self.assertIn("SYNTHETIC", window.text.get("1.0", "end"))
        target = self.folder / "report"
        with mock.patch("nine_constants_window.filedialog.askdirectory", return_value=str(target)):
            window.save_button.invoke()
        self.assertEqual(sorted(p.suffix for p in target.iterdir()), [".csv", ".json", ".txt"])
        self.assertFalse(any(p.suffix == ".inp" for p in target.iterdir()))


if __name__ == "__main__":
    unittest.main()
