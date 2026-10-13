"""Quick calibration P0: explicit PolyMAX modal-set selection and the input preflight before any Abaqus solve.

Synthetic plate, synthetic multi-modal-set UNV and a fake Abaqus (no Abaqus). The real SP-13 UNV is used when the
snadwich data store is configured (store-gated; still no Abaqus).
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import quick_calibration_support as S  # noqa: E402
from services.quick_calibration import (  # noqa: E402
    CHECK_INFO,
    CHECK_OK,
    CHECK_REFUSED,
    ModalSetChoice,
    PreflightRefused,
    QuickCalibrationError,
    config_from_dict,
    check_inp_references,
    load_experiment,
    preflight,
    resolve_modal_set,
    run_quick_calibration,
)

E_FACE = {"name": "E_face", "material": "CFRP_Face", "constants": ["E1", "E2"]}
SETS = (("Best", 6), ("Processing", 4))


def checks(report, item: str) -> list:
    return [check for check in report.checks if check.item == item]


class _Case(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="qc_p0_"))
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        (self.folder / "model.inp").write_text(S.INP)
        S.write_experiment(self.folder / "multi.unv", 0.9 * S.E0, S.G0, sets=SETS)
        S.write_experiment(self.folder / "single.unv", 0.9 * S.E0, S.G0)

    def config(self, experiment="multi.unv", **extra):
        data = {"model_inp": "model.inp", "experiment": experiment, "output_dir": "out", "parameters": [E_FACE]}
        data.update(extra)
        return config_from_dict(data, self.folder)


# ----------------------------------------------------------------------------- modal-set resolution

class ModalSetTests(_Case):
    CHOICES = (ModalSetChoice("best", "Best", "Best", 12), ModalSetChoice("processing", "Processing", "Processing", 21))

    def test_several_sets_need_an_explicit_choice(self):
        for requested in (None, "", "  "):
            with self.subTest(requested=requested), self.assertRaises(QuickCalibrationError) as caught:
                resolve_modal_set(self.CHOICES, requested)
            message = str(caught.exception)
            self.assertIn("select one explicitly", message)
            self.assertIn("Best — 12 modes", message)
            self.assertIn("Processing — 21 modes", message)

    def test_explicit_choice_by_key_or_unique_name(self):
        self.assertEqual(resolve_modal_set(self.CHOICES, "best").key, "best")
        self.assertEqual(resolve_modal_set(self.CHOICES, "Processing").key, "processing")
        self.assertEqual(resolve_modal_set(self.CHOICES[:1], None).key, "best")  # the only set
        with self.assertRaisesRegex(QuickCalibrationError, "was not found"):
            resolve_modal_set(self.CHOICES, "Bets")
        twins = (ModalSetChoice("best", "Best", "Best", 12), ModalSetChoice("best-1a2b3c4d", "Best", "Best", 9))
        self.assertEqual(resolve_modal_set(twins, "best-1a2b3c4d").mode_count, 9)  # the key is exact
        with self.assertRaisesRegex(QuickCalibrationError, "matches several sets"):
            resolve_modal_set(twins[1:] + (ModalSetChoice("other", "Best", "Best", 5),), "Best")
        self.assertIsNone(resolve_modal_set((), None))
        with self.assertRaisesRegex(QuickCalibrationError, "no dataset-55 modal set"):
            resolve_modal_set((), "best")

    def test_the_selected_set_is_loaded(self):
        self.assertEqual(len(load_experiment(self.config(modal_set="Best")).modes), 6)
        processing = load_experiment(self.config(modal_set="processing"))
        self.assertEqual((len(processing.modes), processing.metadata["modal_set_key"]), (4, "processing"))
        with self.assertRaisesRegex(QuickCalibrationError, "select one explicitly"):
            load_experiment(self.config())


# ----------------------------------------------------------------------------- the preflight

class PreflightTests(_Case):
    def test_ready_summary(self):
        report = preflight(self.config(modal_set="Best"))
        self.assertTrue(report.ready, report.lines())
        self.assertEqual((report.modal_set.key, report.experimental_mode_count), ("best", 6))
        self.assertEqual([c.status for c in checks(report, "Experimental modal set")], [CHECK_OK])
        self.assertIn("Best — 6 modes (key 'best', selected explicitly)",
                      checks(report, "Experimental modal set")[0].detail)
        self.assertIn("6 mode(s) used", checks(report, "Experimental modes")[0].detail)
        self.assertIn("E1 = 52000, E2 = 52000", checks(report, "Material and elastic constants")[0].detail)
        self.assertEqual(checks(report, "INP file references")[0].status, CHECK_OK)
        orientation = checks(report, "Physical orientation")[0]
        self.assertEqual(orientation.status, CHECK_INFO)
        self.assertIn("before any optimisation step", orientation.detail)
        self.assertTrue(report.summary().startswith("READY"))
        self.assertFalse((self.folder / "out").exists())  # nothing is written

    def test_missing_modal_set_choice_is_not_ready(self):
        report = preflight(self.config())
        self.assertFalse(report.ready)
        self.assertEqual(checks(report, "Experimental modal set")[0].status, CHECK_REFUSED)
        self.assertIn("Best — 6 modes", report.summary())
        self.assertIsNone(report.experimental_mode_count)
        single = preflight(self.config("single.unv"))
        self.assertTrue(single.ready)
        self.assertIn("the only set in the file", checks(single, "Experimental modal set")[0].detail)

    def test_mode_count_and_frequency_window(self):
        report = preflight(self.config(modal_set="Best", min_experimental_hz=90.0))
        self.assertEqual(report.experimental_mode_count, 4)
        empty = preflight(self.config(modal_set="Best", min_experimental_hz=10000.0))
        self.assertEqual(checks(empty, "Experimental modes")[0].status, CHECK_REFUSED)

    def test_inp_and_material_refusals(self):
        missing = preflight(self.config(modal_set="Best", model_inp="absent.inp"))
        self.assertEqual(checks(missing, "Model INP")[0].status, CHECK_REFUSED)
        for parameter, text in (({"name": "k", "material": "Steel", "constants": ["E"]}, "Steel"),
                                ({"name": "k", "material": "CFRP_Face", "constants": ["E"]}, "has no constant")):
            with self.subTest(text=text):
                report = preflight(self.config(modal_set="Best", parameters=[parameter]))
                self.assertIn(text, checks(report, "Material and elastic constants")[0].detail)
                self.assertFalse(report.ready)
        (self.folder / "zero.inp").write_text(S.INP.replace("52000., 52000.,", "0., 52000.,"))
        zero = preflight(self.config(modal_set="Best", model_inp="zero.inp"))
        self.assertIn("is not positive", checks(zero, "Material and elastic constants")[0].detail)

    def test_unreadable_experiment(self):
        (self.folder / "broken.unv").write_text("not a universal file")
        report = preflight(self.config("broken.unv"))
        self.assertFalse(report.ready)
        absent = preflight(self.config("absent.unv"))
        self.assertIn("does not exist", checks(absent, "Experimental file")[0].detail)


class IncludeTests(_Case):
    def write_inp(self, name: str, extra: str) -> str:
        (self.folder / name).write_text(S.INP.replace("*Material, name=CFRP_Face", extra + "*Material, name=CFRP_Face"))
        return name

    def test_references_are_resolved_from_the_generated_job_directory(self):
        (self.folder / "mesh.inp").write_text("*Node\n2, 1., 0., 0.\n")
        relative_inp = self.write_inp("rel.inp", "*Include, input=mesh.inp\n")
        relative = preflight(self.config(modal_set="Best", model_inp=relative_inp))
        problem = checks(relative, "INP file references")[0]
        self.assertEqual(problem.status, CHECK_REFUSED)
        self.assertIn("relative path", problem.detail)
        self.assertIn(str(relative.baseline_job_dir), problem.detail)  # where Abaqus would look
        absolute = self.write_inp("abs.inp", f"*INCLUDE, INPUT={self.folder / 'mesh.inp'}\n")
        report = preflight(self.config(modal_set="Best", model_inp=absolute))
        self.assertTrue(report.ready, report.lines())
        self.assertIn("mesh.inp", checks(report, "INP file references")[0].detail)
        gone = self.write_inp("gone.inp", f"*Include, input={self.folder / 'absent.inp'}\n")
        self.assertIn("does not exist", checks(preflight(self.config(modal_set="Best", model_inp=gone)),
                                               "INP file references")[0].detail)

    def test_nested_and_other_input_references(self):
        (self.folder / "inner.inp").write_text("*Node, input=nodes.inp\n")
        (self.folder / "outer.inp").write_text(f"*Include, input={self.folder / 'inner.inp'}\n")
        nested = self.write_inp("nested.inp", f"*Include, input={self.folder / 'outer.inp'}\n")
        report = preflight(self.config(modal_set="Best", model_inp=nested))
        details = [c.detail for c in checks(report, "INP file references")]
        self.assertTrue(any("inner.inp line 1 (*node, input=nodes.inp): relative path" in d for d in details), details)
        resolved, problems = check_inp_references(b"*Heading\n** *Include, input=commented.inp\n", self.folder)
        self.assertEqual((resolved, problems), ([], []))  # comments are not references

    def test_a_refused_preflight_never_solves(self):
        fake = S.FakeAbaqus()
        bad = self.write_inp("rel2.inp", "*Include, input=mesh.inp\n")
        for config in (self.config(), self.config(modal_set="Best", model_inp=bad)):
            with self.subTest(config=config.model_inp.name), self.assertRaises(PreflightRefused) as caught:
                run_quick_calibration(config, fake.solve, fake.extract)
            self.assertIn("no Abaqus solve was started", str(caught.exception))
            self.assertFalse(caught.exception.report.ready)
        self.assertEqual(fake.solves, 0)
        self.assertFalse((self.folder / "out").exists())


class OrientationTests(_Case):
    def test_ambiguous_orientation_stops_before_the_optimisation(self):
        fake = S.FakeAbaqus()
        with self.assertRaises(QuickCalibrationError) as caught:
            run_quick_calibration(self.config(modal_set="Best"), fake.solve, fake.extract)
        self.assertNotIsInstance(caught.exception, PreflightRefused)
        self.assertGreaterEqual(len(caught.exception.candidates), 2)
        self.assertEqual(fake.solves, 1)  # the baseline only: no optimiser evaluation was solved


# ----------------------------------------------------------------------------- CLI

class CliTests(_Case):
    def cli(self, *argv):
        import quick_calibration as tool  # tools/quick_calibration.py

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = tool.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "tools"))

    def test_sets_check_and_check_only(self):
        code, out, _ = self.cli("sets", str(self.folder / "multi.unv"))
        self.assertEqual(code, 0)
        self.assertIn("best: Best — 6 modes", out)
        self.assertIn("processing: Processing — 4 modes", out)
        config = self.folder / "case.json"
        config.write_text(json.dumps({"model_inp": "model.inp", "experiment": "multi.unv", "output_dir": "out",
                                      "parameters": [E_FACE]}))
        code, out, err = self.cli("check", str(config))
        self.assertEqual(code, 2)
        self.assertIn("NOT_READY", out)
        self.assertIn("no Abaqus solve was started", err)
        common = ["quick", "--inp", str(self.folder / "model.inp"), "--unv", str(self.folder / "multi.unv"),
                  "--material", "CFRP_Face", "--out", str(self.folder / "out"), "--check-only"]
        code, out, _ = self.cli(*common)
        self.assertEqual(code, 2)  # several sets, none selected
        code, out, _ = self.cli(*common, "--modal-set", "best")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("READY"))
        self.assertFalse((self.folder / "out").exists())


# ----------------------------------------------------------------------------- window (real Tk)

class WindowTests(_Case):
    def setUp(self) -> None:
        super().setUp()
        try:
            import tkinter as tk

            self.root = tk.Tk()
        except Exception as error:  # noqa: BLE001
            self.skipTest(f"Tk is unavailable: {error}")
        self.addCleanup(self.root.destroy)
        self.root.withdraw()
        from quick_calibration_window import QuickCalibrationWindow

        self.fake = S.FakeAbaqus()
        self.window = QuickCalibrationWindow(self.root, self.fake.solve, self.fake.extract, threaded=False)
        self.window.set_inp(str(self.folder / "model.inp"))
        self.window.out.set(str(self.folder / "out"))

    def rows(self):
        table = self.window.readiness_table
        return [tuple(str(v) for v in table.item(k, "values")) for k in table.get_children()]

    def test_modal_set_must_be_selected_before_running(self):
        import quick_calibration_window as qw

        window = self.window
        window.unv.set(str(self.folder / "multi.unv"))
        self.assertEqual(window.modal_set.get(), qw.SELECT_MODAL_SET)  # never the first set
        values = list(window.modal_set_box["values"])
        self.assertEqual(values[0], qw.SELECT_MODAL_SET)
        self.assertEqual(values[1:], ["Best — 6 modes   [best]", "Processing — 4 modes   [processing]"])
        window.check_inputs()
        self.assertTrue(window.readiness.get().startswith("NOT_READY"))
        self.assertIn(("Experimental modal set", "REFUSED"), [row[:2] for row in self.rows()])
        window.start()
        self.assertIn("NOT READY", window.summary.get())
        self.assertEqual(self.fake.solves, 0)
        self.assertFalse((self.folder / "out").exists())  # a refused run writes nothing
        window.modal_set.set(values[1])
        window._inputs_changed()
        self.assertEqual(self.rows(), [])  # a changed input invalidates the summary
        window.check_inputs()
        self.assertTrue(window.readiness.get().startswith("READY"), window.readiness.get())
        self.assertIn(("Experimental modes", "OK"), [row[:2] for row in self.rows()])
        self.assertEqual(self.fake.solves, 0)
        self.assertEqual(json.loads(json.dumps(window.config_data()))["modal_set"], "best")

    def test_single_set_and_orientation_report(self):
        window = self.window
        window.unv.set(str(self.folder / "single.unv"))
        self.assertEqual(window.modal_set.get(), "PolyMAX — 6 modes   [polymax]")
        window.start()  # the symmetric synthetic panel: ambiguous after the baseline solve
        self.assertEqual(self.fake.solves, 1)
        self.assertIn("Physical orientation AMBIGUOUS", window.readiness.get())
        self.assertIn(("Physical orientation", "REFUSED"), [row[:2] for row in self.rows()])
        self.assertIn("Orientation is ambiguous", window.summary.get())


# ----------------------------------------------------------------------------- real SP-13 UNV (store-gated, no Abaqus)

class RealSp13Tests(_Case):
    def test_real_sp13_unv(self):
        from domain.experiment_fixture import fixture_roots_from_environment

        store = fixture_roots_from_environment().get("snadwich")
        unv = None if store is None else Path(store) / "SP-13" / "SP13_a_polymax.unv"
        if unv is None or not unv.is_file():
            self.skipTest("the snadwich data store (real SP-13 UNV) is not configured")
        report = preflight(self.config(str(unv)))
        self.assertFalse(report.ready)
        self.assertEqual([(c.key, c.mode_count) for c in report.available_modal_sets],
                         [("best", 12), ("processing", 21)])
        self.assertIn("Best — 12 modes", report.summary())
        best = preflight(self.config(str(unv), modal_set="Best"))
        self.assertTrue(best.ready, best.lines())
        self.assertEqual((best.modal_set.key, best.experimental_mode_count), ("best", 12))


if __name__ == "__main__":
    unittest.main()
