"""Quick effective-property calibration (services/quick_calibration.py) on a synthetic plate with a fake Abaqus."""

from __future__ import annotations

import json
import math
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import quick_calibration_support as S  # noqa: E402
from services.forward_builder import split_inp_lines  # noqa: E402
from services.quick_calibration import (  # noqa: E402
    GRADE_APPROXIMATE,
    GRADE_GOOD,
    GRADE_UNRELIABLE,
    STATUS_ESTIMATE,
    STATUS_REFUSED,
    InpModel,
    ParameterSpec,
    QuickCalibrationError,
    _grade,
    config_from_dict,
    config_template,
    locate_elastic,
    run_quick_calibration,
)

E_FACE = {"name": "E_face", "material": "CFRP_Face", "constants": ["E1", "E2"]}
G_FACE = {"name": "G12_face", "material": "CFRP_Face", "constants": ["G12"], "lower": 0.4, "upper": 2.5}


def _identity_orientation(tmp: Path, fake=None) -> str:
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "model.inp").write_text(S.INP)
    S.write_experiment(tmp / "probe.unv", S.E0, S.G0)
    config = config_from_dict({"model_inp": "model.inp", "experiment": "probe.unv", "output_dir": "probe",
                               "parameters": [E_FACE]}, tmp)
    fake = fake or S.FakeAbaqus()
    try:
        run_quick_calibration(config, fake.solve, fake.extract)
    except QuickCalibrationError as error:
        for candidate in error.candidates:
            if np.allclose(np.asarray(candidate["rotation"]), np.eye(3)):
                return candidate["candidate_id"]
    raise AssertionError("the symmetric synthetic panel should report an orientation ambiguity")


class _Case(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp())
        cls.orientation = _identity_orientation(cls.root)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def run_case(self, name, e, g, parameters=(E_FACE,), scale=None, noise=0.0, fake=None, **extra):
        folder = self.root / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "model.inp").write_text(S.INP)
        S.write_experiment(folder / "exp.unv", e, g, scale, noise)
        data = {"model_inp": "model.inp", "experiment": "exp.unv", "output_dir": "out",
                "orientation_candidate_id": self.orientation, "parameters": list(parameters)}
        data.update(extra)
        config = config_from_dict(data, folder)
        fake = fake or S.FakeAbaqus()
        result, paths = run_quick_calibration(config, fake.solve, fake.extract)
        return result, paths, fake, config


class RecoveryTests(_Case):
    def test_recovers_e_face_with_a_good_grade(self):
        result, paths, fake, _ = self.run_case("recover", 0.9 * S.E0, S.G0, noise=0.001)
        self.assertEqual(result["status"], STATUS_ESTIMATE)
        estimate = result["estimates"]["E_face"]
        self.assertAlmostEqual(estimate["multiplier"], 0.9, delta=0.005)
        self.assertEqual(result["overall_grade"], GRADE_GOOD)
        self.assertLess(estimate["band_percent"], 1.0)
        self.assertEqual(len(result["rows"]), 6)
        self.assertLessEqual(fake.solves, 8)
        # the calibrated INP carries the new E1 = E2 and leaves every other constant unchanged
        calibrated = split_inp_lines(paths["calibrated_inp"].read_bytes())
        face = locate_elastic(calibrated, "CFRP_Face")
        self.assertAlmostEqual(face.value("E1"), S.E0 * estimate["multiplier"], places=6)
        self.assertEqual(face.value("E1"), face.value("E2"))
        self.assertEqual((face.value("E3"), face.value("G12"), face.value("NU12")), (6700.0, 4500.0, 0.05))
        self.assertEqual(locate_elastic(calibrated, "PLA_core").values, (3000.0, 0.35))
        self.assertIn(b"NOT_A_MATERIAL_PROPERTY", paths["calibrated_inp"].read_bytes())
        for key in ("result", "report", "modes"):
            self.assertTrue(paths[key].is_file())
        json.loads(paths["result"].read_text(encoding="utf-8"))

    def test_tracking_uses_the_scanned_surface_only(self):
        orientation = _identity_orientation(self.root / "layers_probe", S.FakeAbaqus(layers=3))
        result, *_ = self.run_case("layers", 0.9 * S.E0, S.G0, fake=S.FakeAbaqus(layers=3),
                                   orientation_candidate_id=orientation)
        self.assertEqual(result["status"], STATUS_ESTIMATE, result.get("refusal_reasons"))
        self.assertEqual(result["registration"]["tracking_node_count"], 26 * 21)  # the top layer of 3 × 546 nodes
        self.assertAlmostEqual(result["estimates"]["E_face"]["multiplier"], 0.9, delta=0.005)

    def test_rerun_reuses_finished_jobs(self):
        _, _, first, config = self.run_case("rerun", 0.95 * S.E0, S.G0)
        second = S.FakeAbaqus()
        result, _ = run_quick_calibration(config, second.solve, second.extract)
        self.assertEqual(second.solves, 0)
        self.assertEqual(result["abaqus_solves"], 0)
        self.assertGreater(first.solves, 0)

    def test_two_parameters(self):
        result, *_ = self.run_case("two", 0.9 * S.E0, 1.3 * S.G0, parameters=(E_FACE, G_FACE), noise=0.0005)
        self.assertEqual(result["status"], STATUS_ESTIMATE, result.get("refusal_reasons"))
        self.assertAlmostEqual(result["estimates"]["E_face"]["multiplier"], 0.9, delta=0.01)
        self.assertAlmostEqual(result["estimates"]["G12_face"]["multiplier"], 1.3, delta=0.03)
        self.assertEqual(len(result["statistics"]["correlation"]), 2)


class HonestyTests(_Case):
    def test_small_model_form_discrepancy_is_approximate(self):
        # ±3.5 % frequency discrepancy between modes: a value, but with a band of several percent
        scale = [1.035, 0.965, 1.0, 1.035, 0.965, 1.0]
        result, *_ = self.run_case("modelform2", 0.9 * S.E0, S.G0, scale=scale)
        self.assertEqual(result["status"], STATUS_ESTIMATE)
        estimate = result["estimates"]["E_face"]
        self.assertEqual(result["overall_grade"], GRADE_APPROXIMATE)
        self.assertGreater(estimate["band_percent"], 5.0)
        self.assertLessEqual(estimate["band_percent"], 10.6)

    def test_model_form_discrepancy_is_unreliable(self):
        # every mode needs a different E (±6 % in frequency, i.e. ±15 % in E): shown, but UNRELIABLE
        scale = [1.06, 0.95, 1.0, 1.05, 0.94, 1.0]
        result, *_ = self.run_case("modelform6", 0.9 * S.E0, S.G0, scale=scale)
        self.assertEqual(result["status"], STATUS_ESTIMATE)
        estimate = result["estimates"]["E_face"]
        self.assertEqual(result["overall_grade"], GRADE_UNRELIABLE)
        self.assertGreater(estimate["band_percent"], 10.0)
        self.assertGreater(estimate["mode_spread_ln"], estimate["scatter_scaled_sd_ln"])
        self.assertTrue(any("model-form" in reason for reason in estimate["grade_reasons"]))
        implied = [row["implied_multiplier"] for row in result["rows"]]
        self.assertGreater(max(implied) / min(implied), 1.2)

    def test_truth_outside_the_bounds_gives_no_value(self):
        bounded = dict(E_FACE, lower=0.8, upper=1.5)
        result, paths, *_ = self.run_case("bound", 0.72 * S.E0, S.G0, parameters=(bounded,))
        self.assertEqual(result["status"], STATUS_REFUSED)
        self.assertEqual(result["estimates"], {})
        self.assertIn("search bound", result["refusal_reasons"][0])
        self.assertNotIn("calibrated_inp", paths)
        self.assertIn("NO VALUE", paths["report"].read_text(encoding="utf-8"))

    def test_branch_loss_gives_no_value(self):
        # the first two FE shapes rotate into each other as E changes (veering): identity is lost
        fake = S.FakeAbaqus(mixing=lambda e: 0.0 if abs(e - S.E0) < 1e-9 else 0.9)
        result, *_ = self.run_case("veering", 0.9 * S.E0, S.G0, fake=fake)
        self.assertEqual(result["status"], STATUS_REFUSED)
        self.assertIn("mode identity", result["refusal_reasons"][0])

    def test_unobservable_parameter_is_refused(self):
        # PLA_core is not in the fake forward model: the frequencies do not depend on it
        core = {"name": "E_core", "material": "PLA_core", "constants": ["E"]}
        result, *_ = self.run_case("unobservable", 0.9 * S.E0, S.G0, parameters=(E_FACE, core))
        self.assertEqual(result["status"], STATUS_REFUSED)
        self.assertEqual(result["estimates"], {})

    def test_baseline_too_far_off(self):
        result, *_ = self.run_case("faroff", 0.4 * S.E0, S.G0)
        self.assertEqual(result["status"], STATUS_REFUSED)
        self.assertIn("closer constants", result["refusal_reasons"][0])

    def test_too_few_modes(self):
        result, *_ = self.run_case("fewmodes", 0.9 * S.E0, S.G0, experimental_modes=[1])
        self.assertEqual(result["status"], STATUS_REFUSED)
        self.assertIn("mode pair", result["refusal_reasons"][0])

    def test_grade_rules(self):
        reasons = []
        self.assertEqual(_grade(0.03, 0.03, 6, 1, False, reasons), GRADE_GOOD)
        self.assertEqual(_grade(0.03, 0.03, 6, 1, True, reasons), GRADE_APPROXIMATE)  # peak-derived input
        self.assertEqual(_grade(0.03, 0.03, 2, 1, False, reasons), GRADE_APPROXIMATE)  # too few rows for GOOD
        self.assertEqual(_grade(0.08, 0.03, 6, 1, False, reasons), GRADE_APPROXIMATE)
        self.assertEqual(_grade(0.12, 0.03, 6, 1, False, reasons), GRADE_UNRELIABLE)
        self.assertEqual(_grade(0.03, 0.12, 6, 1, False, reasons), GRADE_UNRELIABLE)
        self.assertEqual(_grade(float("nan"), 0.01, 2, 2, False, reasons), GRADE_UNRELIABLE)


class InpTests(unittest.TestCase):
    def test_layouts(self):
        text = S.INP + "*Material, name=Lam\n*Elastic, type=LAMINA\n130000., 9000., 0.3, 5000., 5000., 3000.\n"
        lines = split_inp_lines(text.encode())
        self.assertEqual(locate_elastic(lines, "cfrp_face").elastic_type, "ENGINEERING CONSTANTS")
        self.assertEqual(locate_elastic(lines, "PLA_CORE").names, ("E", "NU"))
        self.assertEqual(locate_elastic(lines, "Lam").value("G12"), 5000.0)

    def test_render_changes_only_the_fitted_values(self):
        model = InpModel(S.INP.encode(), [ParameterSpec("E", "CFRP_Face", ("E1", "E2"))])
        self.assertEqual(model.render({"E": 1.0}), S.INP.encode())
        rendered = model.render({"E": 1.1}).decode().splitlines()
        original = S.INP.splitlines()
        changed = [i for i, (a, b) in enumerate(zip(original, rendered)) if a != b]
        self.assertEqual(len(rendered), len(original))
        self.assertEqual(changed, [original.index("52000., 52000., 6700., 0.05, 0.3, 0.3, 4500., 2200.,")])
        self.assertEqual(model.eigenvalue_count, 30)

    def test_refusals(self):
        cases = {
            "blank field": S.INP.replace("0.05, 0.3, 0.3", "0.05, , 0.3"),
            "temperature column": S.INP.replace("2200.,\n*Material, name=PLA", "2200., 20.\n*Material, name=PLA"),
            "missing material": S.INP.replace("name=CFRP_Face", "name=Other"),
            "two frequency steps": S.INP + "*Frequency\n10\n",
        }
        for label, text in cases.items():
            with self.subTest(label), self.assertRaises(QuickCalibrationError):
                InpModel(text.encode(), [ParameterSpec("E", "CFRP_Face", ("E1", "E2"))])
        with self.assertRaises(QuickCalibrationError):  # constant not in the record type
            InpModel(S.INP.encode(), [ParameterSpec("E", "PLA_core", ("E1",))])

    def test_include_hint(self):
        text = S.INP.replace("*Material, name=CFRP_Face", "*Include, input=face.inp\n*Material, name=Other")
        with self.assertRaises(QuickCalibrationError) as caught:
            InpModel(text.encode(), [ParameterSpec("E", "CFRP_Face", ("E1",))])
        self.assertIn("*Include", str(caught.exception))

    def test_config(self):
        template = config_template()
        config = config_from_dict(template, Path("/data"))
        self.assertEqual(config.model_inp, Path("/data/SP13.inp"))
        self.assertEqual(config.parameters[0].constants, ("E1", "E2"))
        with self.assertRaises(QuickCalibrationError):
            config_from_dict(dict(template, unexpected=1))
        with self.assertRaises(QuickCalibrationError):
            config_from_dict(dict(template, parameters=[dict(E_FACE), dict(E_FACE, name="again")]))
        with self.assertRaises(QuickCalibrationError):
            ParameterSpec("E", "M", ("E1",), lower=1.2, upper=2.0)


if __name__ == "__main__":
    unittest.main()
