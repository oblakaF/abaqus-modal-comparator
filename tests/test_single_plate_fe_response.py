"""PRIORITY-10: the FE Response Workbench (services.single_plate_fe_response) and tab D of the Plate Study page.

A SYNTHETIC_TEST family of another plate (420 × 260 mm, research/plate_fe_response/make_synthetic_family.py) is written
into a temporary folder; the real M11 S4 packages are read where they are on this computer (skipped elsewhere). Nothing
here runs Abaqus, an LM or Auto-ID."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "research" / "plate_fe_response"))

import make_synthetic_family as syn  # noqa: E402
from services import single_plate_fe_response as fr  # noqa: E402

WORK = Path(r"D:\git\abaqus-modal-comparator-work")
S4 = WORK / "runs" / "m11_carbon_plate" / "s4_central"
COPIES = WORK / "research" / "INTEGRATION_RC1_REVIEW" / "moved inputs"
M11_BASE = COPIES / "FE package copy" / "manifest.json"
M11_INP = COPIES / "FE archive copy" / "external_models" / "v3_20261021" / "Plate" / "temp_root" / \
    "CFRP_S4R_0875_FreeFree.inp"
HAVE_M11 = M11_BASE.is_file() and M11_INP.is_file() and (S4 / "M11_S4_G12_PLUS" / "extraction" / "manifest.json").is_file()
EXPONENTS = {mode: dict(zip(("E1", "E2", "G12"), a)) for mode, (_f, a) in syn.MODES.items()}


def central(result, term, parameter):
    return next(t for t in result["central"] if t["term"] == term)["parameters"][parameter]


def branch(result, name):
    return next(b for b in result["branches"] if b["branch"] == name)


class _Synthetic(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)

    def family(self, name="family", **options):
        return fr.family_from_declaration(syn.write_family(self.dir / name, **options))


class SyntheticPlateTests(_Synthetic):
    """Another plate (420 × 260 mm, SYNTHETIC_TEST): the method does not depend on M11."""

    @classmethod
    def setUpClass(cls):
        cls._folder = tempfile.TemporaryDirectory()
        cls.result = fr.analyse(fr.family_from_declaration(syn.write_family(Path(cls._folder.name) / "f")))

    @classmethod
    def tearDownClass(cls):
        cls._folder.cleanup()

    def test_2_independent_of_m11(self):
        result = self.result
        self.assertEqual((result["kind"], result["status"]), (fr.LIVE, fr.LIVE))
        self.assertEqual(result["family_kind"], fr.SYNTHETIC_TEST)
        self.assertEqual(result["rigid_excluded"], [1, 2, 3, 4, 5, 6])  # the code's rigid-body criterion
        text = json.dumps(result)
        for word in ("M11", "261027", "300x300", "Polymax"):
            self.assertNotIn(word, text)
        self.assertEqual(fr.compare_with_archive(result, "another")["state"], "NOT_APPLICABLE")

    def test_9_central_differences_in_ln_p_recover_the_exponents(self):
        for t in self.result["central"]:
            if "+" in t["term"]:
                continue
            mode = int(t["term"][2:])
            for p, item in t["parameters"].items():
                if item.get("s") is not None:
                    self.assertAlmostEqual(item["s"], EXPONENTS[mode][p], places=9, msg=(t["term"], p))
        rank = self.result["rank"]
        self.assertEqual((rank[0]["rank"], rank[0]["of"]), (3, 3))

    def test_3_a_lost_branch_keeps_its_reason_and_has_no_central_value(self):
        lost = branch(self.result, "FE14")["variants"]["E1_PLUS"]
        self.assertEqual(lost["status"], "BRANCH_LOSS")
        self.assertIn("best FE-to-FE MAC", lost["reason"])
        item = central(self.result, "FE14", "E1")
        self.assertIsNone(item["s"])
        self.assertEqual(item["status"], fr.UNAVAILABLE)
        self.assertEqual(item["lost_in"], ["E1_PLUS"])
        self.assertAlmostEqual(central(self.result, "FE14", "E2")["s"], 0.2, places=9)  # other parameters unaffected

    def test_4_an_order_exchange_is_followed_by_shape(self):
        for state in ("E1_PLUS", "E2_MINUS"):
            v10, v11 = branch(self.result, "FE10")["variants"][state], branch(self.result, "FE11")["variants"][state]
            self.assertEqual((v10["candidate"], v11["candidate"]), ("FE11", "FE10"))
            self.assertTrue(v10["permutation"] and v11["permutation"])
        self.assertAlmostEqual(central(self.result, "FE10", "E1")["s"], 0.45, places=9)
        self.assertIn({"rows": ["FE10", "FE11"], "status": "INDEPENDENT", "reasons": mock.ANY}, self.result["clusters"])

    def test_5_a_confirmed_cluster_is_one_term(self):
        terms = [t["term"] for t in self.result["central"]]
        self.assertIn("FE12+FE13", terms)
        self.assertNotIn("FE12", terms)
        self.assertNotIn("FE13", terms)
        self.assertEqual([c["status"] for c in self.result["clusters"] if c["rows"] == ["FE12", "FE13"]], ["CONFIRMED"])
        self.assertAlmostEqual(central(self.result, "FE12+FE13", "E1")["s"], 0.25, places=9)
        self.assertEqual(central(self.result, "FE12+FE13", "E1")["mode"], "TRACKED_CLUSTER")

    def test_10_the_e1_e2_sum_is_conditional(self):
        conditional = self.result["rank"][1]
        self.assertEqual(conditional["parameters"], ["E (E1 = E2)", "G12"])
        self.assertIn(fr.CONDITIONAL, conditional["status"])
        prediction = fr.what_if(self.result, {fr.JOINT_E: 45000.0 * 1.02})
        self.assertTrue(any(fr.CONDITIONAL in label for label in prediction["labels"]))
        self.assertIsNone(prediction["solved_point"])  # no joint state was solved
        row = next(r for r in prediction["rows"] if r["term"] == "FE8")
        self.assertAlmostEqual(row["predicted_hz"], 60.0 * 1.02 ** 0.5, places=9)

    def test_11_no_change_is_the_baseline(self):
        prediction = fr.what_if(self.result, {"G12": 4000.0})
        for row in prediction["rows"]:
            if row["predicted_hz"] is not None:
                self.assertAlmostEqual(row["predicted_hz"], row["f0_hz"], places=12)
                self.assertEqual(row["status"], "BASELINE (no change)")

    def test_12_a_prediction_is_compared_with_the_solved_fe_point(self):
        prediction = fr.what_if(self.result, {"G12": 4200.0})
        self.assertEqual(prediction["solved_point"], "G12_PLUS")
        row = next(r for r in prediction["rows"] if r["term"] == "FE7")
        self.assertAlmostEqual(row["solved_hz"], 25.0 * 1.05 ** 0.48, places=9)
        self.assertAlmostEqual(row["error_percent"], 0.0, places=7)
        self.assertIn(fr.PREDICTION, prediction["labels"][0])
        halfway = fr.what_if(self.result, {"G12": 4100.0})
        self.assertIsNone(halfway["solved_point"])
        self.assertIsNone(next(r for r in halfway["rows"] if r["term"] == "FE7")["solved_hz"])
        lost = next(r for r in fr.what_if(self.result, {"E1": 46000.0})["rows"] if r["term"] == "FE14")
        self.assertIsNone(lost["predicted_hz"])
        self.assertIn(fr.UNAVAILABLE, lost["status"])

    def test_13_no_extrapolation(self):
        for value in (4500.0, 3700.0):
            with self.assertRaises(fr.WhatIfRefused) as caught:
                fr.what_if(self.result, {"G12": value})
            self.assertIn("never extrapolated", str(caught.exception))
        with self.assertRaises(fr.WhatIfRefused):
            fr.what_if(self.result, {"nu12": 0.3})

    def test_14_no_transfer_to_another_fe_model(self):
        with self.assertRaises(fr.WhatIfRefused) as caught:
            fr.what_if(self.result, {"G12": 4200.0}, baseline_manifest_sha256="b" * 64,
                       recorded_baseline_sha256="a" * 64)
        self.assertIn("never carried to another model", str(caught.exception))

    def test_17_experimental_records_stay_unpaired(self):
        rows = fr.experiment_rows([{"number": 1, "hz": 24.0}, {"number": 2, "hz": 61.0}], self.result,
                                  fr.what_if(self.result, {"G12": 3800.0}))
        self.assertEqual({r["status"] for r in rows}, {fr.PROXIMITY_ONLY})
        self.assertTrue(all(r["pair"].startswith("NONE") for r in rows))
        self.assertEqual(rows[0]["nearest_fe"], "FE7")
        self.assertIsNotNone(rows[0]["predicted_hz"])
        self.assertNotIn("pairs", self.result)


class SyntheticFamilyEdgeTests(_Synthetic):
    def test_6_never_followed_by_frequency(self):
        family_path = syn.write_family(self.dir / "f")
        # a state with the baseline's frequencies but other shapes: every branch is lost, none re-paired by frequency
        points = syn.nodes()
        modes = syn.state_modes("BASELINE", points)
        import numpy as np

        xy = np.array([(x, y) for _n, x, y, _z in points])
        x, y = xy[:, 0] / syn.PLAN_MM[0], xy[:, 1] / syn.PLAN_MM[1]
        others = [np.sin((k + 4) * np.pi * x) * np.sin((k + 3) * np.pi * y) for k in range(len(modes) - 6)]
        zero = np.zeros(len(points))
        replaced = modes[:6] + [(n, f, np.column_stack([zero, zero, others[i]])) for i, (n, f, _u) in
                                enumerate(modes[6:])]
        syn.write_package(self.dir / "f" / "G12_PLUS" / "extraction", points, replaced, "G12_PLUS")
        result = fr.analyse(fr.family_from_declaration(family_path))
        for b in result["branches"]:
            self.assertNotIn(b["variants"]["G12_PLUS"]["status"], fr.TRACKED_STATES, b["branch"])
        self.assertTrue(all(t["parameters"]["G12"]["s"] is None for t in result["central"]))

    def test_7_incompatible_geometry_is_excluded(self):
        result = fr.analyse(self.family(other_geometry=["G12_PLUS"]))
        self.assertIn(["G12_PLUS", mock.ANY], [list(x) for x in result["excluded"]])
        self.assertIn("INCOMPATIBLE_FE_GEOMETRY", dict((a, b) for a, b in result["excluded"])["G12_PLUS"])
        self.assertEqual(result["status"], fr.INCOMPLETE)
        self.assertEqual(result["completeness"]["G12"]["missing"], ["+"])

    def test_8_a_missing_state_is_named_never_substituted(self):
        result = fr.analyse(self.family(without=["G12_MINUS"]))
        self.assertEqual(result["status"], fr.INCOMPLETE)
        self.assertEqual(result["completeness"]["G12"]["missing"], ["−"])
        self.assertTrue(all(fr.INCOMPLETE in t["parameters"]["G12"]["status"] for t in result["central"]))
        with self.assertRaises(fr.WhatIfRefused) as caught:
            fr.what_if(result, {"G12": 4100.0})
        self.assertIn(fr.INCOMPLETE, str(caught.exception))
        self.assertIsNotNone(central(result, "FE7", "E1")["s"])  # the complete parameters keep their values

    def test_9_unequal_steps_use_the_actual_values(self):
        result = fr.analyse(self.family(ratios={"G12_PLUS": {"G12": 1.075}}))
        item = central(result, "FE7", "G12")
        self.assertEqual((item["p_minus"], item["p_plus"]), (3800.0, 4300.0))
        self.assertAlmostEqual(item["s"], 0.48, places=9)  # a fixed ±5 % step would give another number

    def test_the_folder_route_reads_the_parameters_from_the_inps(self):
        self.family()
        family = fr.family_from_folder(self.dir / "family", self.dir / "family" / "baseline" / "extraction" /
                                       "manifest.json", "PLATE-Z FE", "PLATE-Z",
                                       baseline_inp=self.dir / "family" / "baseline" / "baseline.inp")
        self.assertEqual(sorted((v.parameter, v.value) for v in family.variants),
                         [("E1", 42750.0), ("E1", 47250.0), ("E2", 28500.0), ("E2", 31500.0), ("G12", 3800.0),
                          ("G12", 4200.0)])
        self.assertEqual(family.problems, ())
        with self.assertRaises(fr.FamilyRefused):  # no baseline values: never guessed
            fr.family_from_folder(self.dir / "family", self.dir / "family" / "baseline" / "extraction" /
                                  "manifest.json", "x", "y")

    def test_15_16_save_reopen_and_invalidation(self):
        family = self.family()
        rows = fr.identities(family)
        result = fr.analyse(family)
        record = fr.session_record(family, rows, result, fr.what_if(result, {"E2": 31500.0}),
                                   fr.experiment_rows([{"number": 1, "hz": 25.1}], result))
        self.assertNotIn("mode_0007", json.dumps(record))  # no FE data inside the session
        path = fr.save_session(record, self.dir / "session.json")
        reopened = fr.open_session(path)
        self.assertEqual(fr.session_state(reopened)["state"], "SOURCES_VERIFIED")
        self.assertEqual(reopened["result"]["central"], json.loads(json.dumps(result))["central"])
        self.assertEqual(reopened["what_if"]["trial"], {"E2": 31500.0})
        written = fr.export_session(reopened, self.dir)
        self.assertEqual(sorted(p.name for p in written), ["FE_RESPONSE_REPORT.md", "branch_tracking.csv",
                                                           "central_sensitivities.csv", "fe_response_session.json",
                                                           "what_if.csv"])
        manifest = Path(family.variants[0].manifest)
        manifest.write_text(manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        state = fr.session_state(fr.open_session(path))
        self.assertEqual(state["state"], "STALE")
        self.assertIn("E1_MINUS: the manifest changed", state["reasons"])

    def test_18_no_physical_lm_auto_id_or_solver(self):
        with mock.patch("subprocess.Popen") as popen, mock.patch("subprocess.run") as run, \
                mock.patch("services.identification_step.run_bounded_lm", side_effect=AssertionError("no LM")):
            result = fr.analyse(self.family())
            fr.what_if(result, {"G12": 4200.0})
            popen.assert_not_called()
            run.assert_not_called()
        self.assertNotIn("material_values", result)


def perturb_shape(manifest: Path, mode: int = 10) -> None:
    """Change one value of one mode-shape file of a package; its manifest stays byte-identical."""
    path = Path(manifest).parent / f"mode_{mode:04d}.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    parts = lines[1].split(",")
    parts[4] = repr(float(parts[4]) * 1.001 + 1e-6)
    lines[1] = ",".join(parts)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def sha(path) -> str:
    return fr.sha256_file(path)


class SourceBindingTests(_Synthetic):
    """PRIORITY-10-F1: the results stay bound to the FE sources they were computed from."""

    def session(self, name="family"):
        family = self.family(name)
        result = fr.analyse(family)
        path = fr.save_session(fr.session_record(family, fr.identities(family), result), self.dir / f"{name}.json")
        self.assertEqual(fr.session_state(fr.open_session(path))["state"], "SOURCES_VERIFIED")
        return family, path

    def test_f1_1_a_changed_shape_file_under_an_unchanged_manifest(self):
        family, path = self.session()
        manifest = Path(next(v for v in family.variants if v.member_id == "E1_MINUS").manifest)
        before = sha(manifest)
        perturb_shape(manifest)
        self.assertEqual(sha(manifest), before)  # the manifest alone would still verify
        state = fr.session_state(fr.open_session(path))
        self.assertEqual(state["state"], "STALE")
        self.assertTrue(any(r.startswith("E1_MINUS: the package files changed") for r in state["reasons"]),
                        state["reasons"])

    def test_f1_2_a_changed_inp(self):
        family, path = self.session()
        for member in (next(v for v in family.variants if v.member_id == "G12_PLUS"), family.baseline):
            inp = Path(member.inp)
            inp.write_text(inp.read_text(encoding="ascii") + "** edited\n", encoding="ascii")
            state = fr.session_state(fr.open_session(path))
            self.assertEqual(state["state"], "STALE")
            self.assertIn(f"{member.member_id}: the INP changed", state["reasons"])

    def test_f1_3_every_used_state_must_be_present(self):
        family, path = self.session()
        record = fr.open_session(path)
        dropped = dict(record, identities=[r for r in record["identities"] if r["id"] != "E2_PLUS"])
        state = fr.session_state(dropped)
        self.assertEqual(state["state"], "STALE")
        self.assertIn("E2_PLUS: used by the results but not among the recorded sources", state["reasons"])
        shutil.rmtree(self.dir / "family" / "G12_MINUS" / "extraction")
        state = fr.session_state(record)
        self.assertEqual(state["state"], "STALE")
        self.assertIn("G12_MINUS: the manifest is missing", state["reasons"])

    def rewrite(self, declaration: Path, name: str, change) -> Path:
        data = json.loads(declaration.read_text(encoding="utf-8"))
        change(data)
        path = declaration.parent / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_f1_4_moduli_in_gpa_are_mpa_and_other_units_are_refused(self):
        declaration = syn.write_family(self.dir / "family")

        def in_gpa(data):
            data["baseline_unit"] = "GPa"
            data["baseline_parameters"] = {k: v / 1000.0 for k, v in data["baseline_parameters"].items()}
            data["baseline_parameters"]["G12"] = {"value": 4.0e9, "unit": "Pa"}
            for v in data["variants"]:
                v["value"], v["unit"] = v["value"] / 1000.0, "GPa"
        mpa = fr.family_from_declaration(declaration)
        gpa = fr.family_from_declaration(self.rewrite(declaration, "gpa.json", in_gpa))
        for p, value in mpa.baseline_parameters.items():
            self.assertAlmostEqual(gpa.baseline_parameters[p], value, delta=1e-9 * value)
        for a, b in zip(mpa.variants, gpa.variants):
            self.assertAlmostEqual(b.value, a.value, delta=1e-9 * a.value)
            self.assertEqual((b.unit, b.declared), ("MPa", f"{a.value / 1000.0:g} GPa"))
        r_mpa, r_gpa = fr.analyse(mpa), fr.analyse(gpa)
        for t_mpa, t_gpa in zip(r_mpa["central"], r_gpa["central"]):
            for p, item in t_mpa["parameters"].items():
                if item["s"] is not None:
                    self.assertAlmostEqual(t_gpa["parameters"][p]["s"], item["s"], places=9)
        self.assertEqual(fr.what_if(r_gpa, {"G12": 4200.0})["solved_point"], "G12_PLUS")
        for unit in ("psi", "ksi", "mPa", "MPA", "kg/cm2"):
            with self.assertRaises(fr.FamilyRefused, msg=unit) as caught:
                fr.family_from_declaration(self.rewrite(declaration, "u.json", lambda d: d["variants"][0].update(
                    unit=unit)))
            self.assertIn("is not supported for a modulus", str(caught.exception))
        with self.assertRaises(fr.FamilyRefused):
            fr.family_from_declaration(self.rewrite(declaration, "u.json", lambda d: d.update(baseline_unit="psi")))
        with self.assertRaises(fr.FamilyRefused) as caught:
            fr.family_from_declaration(self.rewrite(declaration, "u.json", lambda d: d["variants"][0].update(
                parameter="nu12", value=0.31)))
        self.assertIn("not an elastic modulus", str(caught.exception))
        # the INP's own unit: an MPa model read as GPa no longer matches the declaration
        with self.assertRaises(fr.FamilyRefused) as caught:
            fr.family_from_declaration(self.rewrite(declaration, "u.json", lambda d: d.update(inp_modulus_unit="GPa")))
        self.assertIn("but its INP has", str(caught.exception))

    def test_f1_5_declared_values_must_be_the_inp_values(self):
        declaration = syn.write_family(self.dir / "family")

        def variant(data, state):
            return next(v for v in data["variants"] if v["id"] == state)
        with self.assertRaises(fr.FamilyRefused) as caught:
            fr.family_from_declaration(self.rewrite(declaration, "x.json", lambda d: variant(d, "G12_PLUS").update(
                value=4250.0)))
        self.assertIn("G12_PLUS: G12 is declared 4250 MPa but its INP has 4200 MPa", str(caught.exception))
        with self.assertRaises(fr.FamilyRefused) as caught:
            fr.family_from_declaration(self.rewrite(declaration, "x.json", lambda d: d["baseline_parameters"].update(
                G12=4100.0)))
        self.assertIn("the baseline: G12 is declared 4100 MPa but its INP has 4000 MPa", str(caught.exception))
        # an undeclared material change in a state's INP
        inp = self.dir / "family" / "G12_PLUS" / "G12_PLUS.inp"
        original = inp.read_text(encoding="ascii")
        inp.write_text(original.replace(" 8500.,", " 8600.,"), encoding="ascii")
        with self.assertRaises(fr.FamilyRefused) as caught:
            fr.family_from_declaration(declaration)
        self.assertIn("G12_PLUS: its INP also changes E3", str(caught.exception))
        inp.write_text(original, encoding="ascii")
        family = fr.family_from_declaration(declaration)
        self.assertIn("G12_PLUS: G12 equals its INP; no other material constant differs from the baseline INP",
                      family.checks)
        # without a baseline INP: what cannot be checked is named
        family = fr.family_from_declaration(self.rewrite(declaration, "x.json", lambda d: d["baseline"].pop("inp")))
        self.assertTrue(any("baseline: no INP" in c for c in family.checks))
        # the folder route: declared baseline values against the baseline INP
        with self.assertRaises(fr.FamilyRefused):
            fr.family_from_folder(self.dir / "family", self.dir / "family" / "baseline" / "extraction" /
                                  "manifest.json", "x", "y", baseline_parameters={"G12": 4100.0},
                                  baseline_inp=self.dir / "family" / "baseline" / "baseline.inp")


class ArchiveTests(unittest.TestCase):
    """The PRIORITY-2 table as an ARCHIVED_FE_RESULT (always available; never a new FE-to-FE MAC)."""

    def test_1_the_archived_m11_values(self):
        archive = fr.archived_result()
        self.assertEqual(archive["kind"], fr.ARCHIVED)
        terms = {t["term"]: t for t in archive["central"]}
        self.assertAlmostEqual(terms["FE7"]["parameters"]["G12"]["s"], 0.48268, places=5)
        self.assertAlmostEqual(terms["FE13"]["parameters"]["E1"]["s"], 0.49864, places=5)
        self.assertAlmostEqual(terms["FE14"]["parameters"]["E2"]["s"], 0.50037, places=5)
        self.assertIn("FE15+FE16", terms)
        for term in ("FE8", "FE9", "FE20"):
            for p in ("E1", "E2"):
                self.assertIsNone(terms[term]["parameters"][p]["s"], (term, p))
        ranks = {tuple(r["parameters"]): (r["rank"], round(r["condition"], 2)) for r in archive["rank"]}
        self.assertEqual(ranks[("E1", "E2", "G12")], (3, 1.83))
        self.assertEqual(ranks[("E (E1 = E2)", "G12")], (2, 2.35))
        self.assertIn(fr.CONDITIONAL, archive["rank"][1]["status"])

    def test_17_exp1_and_fe7_proximity_only(self):
        rows = fr.experiment_rows([{"number": 1, "hz": 18.6307}], fr.archived_result())
        self.assertEqual((rows[0]["record"], rows[0]["nearest_fe"], rows[0]["status"]), ("EXP1", "FE7",
                                                                                         fr.PROXIMITY_ONLY))
        self.assertAlmostEqual(rows[0]["difference_percent"], 2.37, places=2)


@unittest.skipUnless(HAVE_M11, "the M11 S4 packages and the verified baseline copies are not on this computer")
class RealM11Tests(unittest.TestCase):
    """LIVE_FE_PACKAGE_ANALYSIS of the real M11 S4 packages: the PRIORITY-2 archive reproduced from the shapes."""

    @classmethod
    def setUpClass(cls):
        cls.family = fr.family_from_folder(S4, M11_BASE, "M11 S4R_0875_BASELINE", "PLATE-300x300x1mm",
                                           baseline_inp=M11_INP)
        cls.rows = fr.identities(cls.family)
        cls.result = fr.analyse(cls.family)

    def test_1_live_values_reproduce_the_archive(self):
        self.assertEqual(self.result["kind"], fr.LIVE)
        self.assertEqual(self.rows[0]["manifest_sha256"], fr.M11_MANIFEST_SHA256)
        self.assertAlmostEqual(central(self.result, "FE7", "G12")["s"], 0.48268, places=5)
        self.assertAlmostEqual(central(self.result, "FE13", "E1")["s"], 0.49864, places=5)
        self.assertAlmostEqual(central(self.result, "FE14", "E2")["s"], 0.50037, places=5)
        comparison = fr.compare_with_archive(self.result, self.rows[0]["manifest_sha256"])
        self.assertEqual(comparison["state"], "AGREES")
        self.assertLess(comparison["max_abs_difference"], 1.5e-5)
        self.assertTrue(all(r["odb_state"] == "VERIFIED_SHA256" for r in self.rows[1:]))

    def test_3_4_5_lost_exchanged_and_clustered_branches(self):
        for name in ("FE8", "FE9", "FE20"):
            for state in ("M11_S4_E1_PLUS", "M11_S4_E2_MINUS"):
                self.assertEqual(branch(self.result, name)["variants"][state]["status"], "BRANCH_LOSS", (name, state))
            self.assertEqual(central(self.result, name, "E1")["status"], fr.UNAVAILABLE)
        for a, b in (("FE10", "FE11"), ("FE13", "FE14"), ("FE17", "FE18")):
            self.assertEqual(branch(self.result, a)["variants"]["M11_S4_E1_PLUS"]["candidate"], f"FE{int(b[2:])}")
        self.assertIn("FE15+FE16", [t["term"] for t in self.result["central"]])
        self.assertAlmostEqual(central(self.result, "FE7", "E1")["s"], 0.0081, places=4)  # FE7 stays available

    def test_12_the_g12_plus_prediction_against_the_solved_point(self):
        prediction = fr.what_if(self.result, {"G12": 5250.0})
        fe7 = next(r for r in prediction["rows"] if r["term"] == "FE7")
        self.assertAlmostEqual(fe7["solved_hz"], 19.5264, places=3)
        self.assertLess(abs(fe7["error_percent"]), 0.01)

    def test_f1_6_an_unchanged_m11_session_reopens(self):
        with tempfile.TemporaryDirectory() as folder:
            path = fr.save_session(fr.session_record(self.family, self.rows, self.result), Path(folder) / "m11.json")
            state = fr.session_state(fr.open_session(path))
        self.assertEqual((state["state"], state["reasons"]), ("SOURCES_VERIFIED", []))
        self.assertTrue(all(r["package_sha256"] and r["inp_sha256"] for r in self.rows))
        # the PRIORITY-10 sessions of the archive (identity rows without INP paths) verify the same way
        for name in ("m11_live_g12_plus", "m11_live_g12_minus", "m11_live_e_joint_plus2"):
            archived = ROOT / "docs" / "research" / "plate_fe_response_p10" / name / "fe_response_session.json"
            state = fr.session_state(fr.open_session(archived))
            self.assertEqual((state["state"], state["reasons"]), ("SOURCES_VERIFIED", []), name)


try:
    from PySide6.QtWidgets import QApplication  # noqa: F401
    from new_gui import fe_response_panel as fpanel
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT or os.environ.get("NEW_GUI_REQUIRE_QT") == "1", "PySide6 is not installed")
class PanelTests(unittest.TestCase):
    def setUp(self):
        from new_gui import window as wm

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)
        patch = mock.patch.dict(os.environ, {"LOCALAPPDATA": directory.name})
        patch.start()
        self.addCleanup(patch.stop)
        self.app = QApplication.instance() or wm.create_application([])
        self.window = wm.MainWindow(ask_path=lambda kind, start: "")
        self.window.resize(1366, 768)
        self.window.show()
        self.addCleanup(self.window.close)
        self.panel = self.window.fe_response

    def test_19_tab_d_beside_a_b_c_and_the_synthetic_route(self):
        tabs = self.window.plate_tabs
        self.assertEqual([tabs.tabText(i) for i in range(4)], ["A. Current PLATE Study", "B. New Single Plate",
                                                               "C. Physical Readiness", "D. FE Response"])
        self.assertEqual(tabs.tabToolTip(3), "D. FE Response Workbench")
        # the smoke found the captions of the id fields collapsed to zero width: they never wrap
        from PySide6.QtWidgets import QLabel

        captions = [w for w in self.panel.findChildren(QLabel) if w.text() in ("FE model id", "Specimen id")]
        self.assertEqual(len(captions), 2)
        self.assertTrue(all(not w.wordWrap() and w.minimumSizeHint().width() > 0 for w in captions))
        self.assertFalse(self.panel.run())  # nothing chosen
        declaration = syn.write_family(self.dir / "family")
        self.assertTrue(self.panel.load_declaration(str(declaration)))
        self.assertTrue(self.panel.run())
        self.assertTrue(self.panel.wait_idle())
        self.assertEqual(self.panel.freshness()[0], "CURRENT")
        self.assertIn("tracking", self.panel.tables)
        self.assertTrue(self.panel.predict("G12", 4200.0))
        self.assertTrue(self.panel.wait_idle())  # shown only after the FE sources verify again
        self.assertIn("what_if", self.panel.tables)
        self.assertEqual(self.panel.source_check["state"], "SOURCES_VERIFIED")
        self.assertFalse(self.panel.predict("G12", 9000.0))  # outside the solved range
        self.assertIn("never extrapolated", self.panel.message.text())
        # an experimental modal set changes only the experimental display, never the FE results
        exp = mock.Mock(sets=[mock.Mock(records=[mock.Mock(number=1, frequency_hz=24.5)])])
        self.panel.set_inputs(None, None, exp, {"sha256": "x"}, 0)
        self.assertEqual(self.panel.freshness()[0], "CURRENT")
        self.assertTrue(self.panel.save_session(str(self.dir / "s.json")))
        self.assertTrue(self.panel.export(str(self.dir)))
        self.assertTrue(self.panel.wait_idle())
        self.assertEqual(len(self.panel.last_export), 5)
        # another family chosen: the results are STALE, no prediction from them
        self.assertTrue(self.panel.load_declaration(str(syn.write_family(self.dir / "other",
                                                                         without=["G12_MINUS"]))))
        self.assertEqual(self.panel.freshness()[0], "STALE")
        self.assertFalse(self.panel.predict("G12", 4200.0))
        self.assertTrue(self.panel.open_session(str(self.dir / "s.json")))
        self.assertTrue(self.panel.wait_idle())
        self.assertEqual(self.panel.freshness()[0], "STORED")
        # the smoke found the family line naming the earlier choice: it names the session's baseline
        self.assertTrue(self.panel.family_line.text().startswith("Reopened session: "))
        self.assertIn(str(self.dir / "family" / "baseline"), self.panel.family_line.text())
        self.assertEqual(self.panel.baseline_manifest, str(self.dir / "family" / "baseline" / "extraction" /
                                                           "manifest.json"))
        self.assertTrue(self.panel.predict("E1", 46000.0))
        self.assertTrue(self.panel.wait_idle())
        self.assertIsNotNone(self.panel.prediction)

    def tracked(self, name="family"):
        declaration = syn.write_family(self.dir / name)
        self.assertTrue(self.panel.load_declaration(str(declaration)))
        self.assertTrue(self.panel.run())
        self.assertTrue(self.panel.wait_idle())
        self.assertEqual(self.panel.freshness()[0], "CURRENT")
        return declaration

    def test_f1_another_baseline_or_baseline_inp_invalidates_at_once(self):
        self.tracked()
        other = syn.write_family(self.dir / "other").parent
        self.assertTrue(self.panel.choose_baseline(str(other / "baseline" / "extraction" / "manifest.json")))
        state, reason = self.panel.freshness()  # immediately, before any new tracking
        self.assertEqual(state, "STALE")
        self.assertIn("FE baseline was chosen again", reason)
        self.assertIn("STALE", self.panel.state_line.text())
        self.assertNotIn("tracking", self.panel.tables)  # the previous results are no longer shown
        self.assertIsNone(self.panel.family)
        self.assertFalse(self.panel.predict("G12", 4200.0))
        self.assertFalse(self.panel.export(str(self.dir)))
        self.assertFalse(self.panel.save_session(str(self.dir / "stale.json")))
        self.tracked("again")
        self.assertTrue(self.panel.choose_baseline_inp(str(other / "baseline" / "baseline.inp")))
        self.assertEqual(self.panel.freshness()[0], "STALE")
        self.assertFalse(self.panel.predict("G12", 4200.0))
        # a choice during a running tracking discards that tracking
        self.assertTrue(self.panel.load_declaration(str(self.dir / "again" / "fe_family.json")))
        self.assertTrue(self.panel.run())
        self.assertTrue(self.panel.choose_baseline(str(other / "baseline" / "extraction" / "manifest.json")))
        self.assertTrue(self.panel.wait_idle())
        self.assertEqual(self.panel.freshness()[0], "STALE")

    def test_f1_a_changed_source_stops_the_prediction_and_the_export(self):
        declaration = self.tracked()
        self.assertTrue(self.panel.save_session(str(self.dir / "s.json")))
        perturb_shape(declaration.parent / "E1_MINUS" / "extraction" / "manifest.json")
        self.assertTrue(self.panel.predict("G12", 4200.0))  # accepted, then the sources are verified again
        self.assertTrue(self.panel.wait_idle())
        self.assertIsNone(self.panel.prediction)
        self.assertEqual(self.panel.freshness()[0], "STALE")
        self.assertIn("E1_MINUS: the package files changed", self.panel.message.text())
        self.assertFalse(self.panel.export(str(self.dir)))
        self.assertTrue(self.panel.open_session(str(self.dir / "s.json")))
        self.assertTrue(self.panel.wait_idle())
        self.assertEqual(self.panel.freshness()[0], "STALE")
        self.assertFalse(self.panel.predict("G12", 4200.0))
        # an export started while the results verify is written only after the check
        self.tracked("fresh")
        self.assertTrue(self.panel.export(str(self.dir)))
        self.assertTrue(self.panel.wait_idle())
        written = {p.name: p for p in self.panel.last_export}
        self.assertEqual(json.loads(written["fe_response_session.json"].read_text(encoding="utf-8"))
                         ["source_check"]["state"], "SOURCES_VERIFIED")

    def folder_route(self, name):
        """Another plate by the folder route (baseline + baseline INP + folder of states), its ids not retyped."""
        root = syn.write_family(self.dir / name).parent
        self.assertTrue(self.panel.choose_baseline(str(root / "baseline" / "extraction" / "manifest.json")))
        self.assertTrue(self.panel.choose_baseline_inp(str(root / "baseline" / "baseline.inp")))
        self.assertTrue(self.panel.choose_states_folder(str(root)))
        return root

    def ids(self):
        return self.panel.model_edit.text(), self.panel.specimen_edit.text()

    def test_f1_08_ids_of_a_declaration_are_not_carried_to_another_baseline(self):
        self.tracked()
        synthetic = self.ids()
        self.assertEqual(synthetic, ("SYNTHETIC_TEST-PLATE-420x260-S4", "SYNTHETIC_TEST-PLATE-420x260"))
        earlier = self.panel.family
        self.assertTrue(self.panel.save_session(str(self.dir / "synthetic.json")))
        self.folder_route("plate_z")
        neutral = (fpanel.DEFAULT_MODEL_ID, fpanel.DEFAULT_SPECIMEN_ID)
        self.assertEqual(self.ids(), neutral)
        self.assertEqual((self.panel.family.model_id, self.panel.family.specimen_id), neutral)
        self.assertEqual((earlier.model_id, earlier.specimen_id), synthetic)  # a family made is never changed
        self.assertTrue(self.panel.run())
        self.assertTrue(self.panel.wait_idle())
        self.assertEqual((self.panel.result["model_id"], self.panel.result["specimen_id"]), neutral)
        self.assertTrue(self.panel.save_session(str(self.dir / "plate_z.json")))
        record = fr.open_session(self.dir / "plate_z.json")
        self.assertEqual((record["family"]["model_id"], record["family"]["specimen_id"]), neutral)
        self.assertEqual(record["fe_fingerprint"], fr.fe_fingerprint(record["identities"], self.panel.family))
        self.assertEqual(fr.session_state(record)["state"], "SOURCES_VERIFIED")
        (self.dir / "report").mkdir()
        self.assertTrue(self.panel.export(str(self.dir / "report")))
        self.assertTrue(self.panel.wait_idle())
        exported = json.loads(next(p for p in self.panel.last_export if p.name == "fe_response_session.json")
                              .read_text(encoding="utf-8"))
        self.assertEqual((exported["family"]["model_id"], exported["result"]["model_id"]),
                         (fpanel.DEFAULT_MODEL_ID, fpanel.DEFAULT_MODEL_ID))
        self.assertNotIn("SYNTHETIC", json.dumps(exported["family"]))
        # the identity check is not weakened: another model id under the same sources is not the session's fingerprint
        forged = dict(record, family=dict(record["family"], model_id=synthetic[0]))
        self.assertEqual(fr.session_state(forged)["state"], "STALE")
        # the original session reopens with its own ids
        self.assertTrue(self.panel.open_session(str(self.dir / "synthetic.json")))
        self.assertTrue(self.panel.wait_idle())
        self.assertEqual(self.panel.freshness()[0], "STORED")
        self.assertEqual(self.ids(), synthetic)

    def test_f1_08_ids_of_a_session_are_not_carried_to_another_baseline(self):
        self.tracked()
        self.assertTrue(self.panel.save_session(str(self.dir / "synthetic.json")))
        self.tracked("again")
        self.assertTrue(self.panel.open_session(str(self.dir / "synthetic.json")))
        self.assertTrue(self.panel.wait_idle())
        self.assertEqual(self.ids(), ("SYNTHETIC_TEST-PLATE-420x260-S4", "SYNTHETIC_TEST-PLATE-420x260"))
        # the states folder of the session's own baseline is the same FE model: its ids stay
        root = self.dir / "family"
        self.assertTrue(self.panel.choose_states_folder(str(root)))
        self.assertEqual(self.panel.family.model_id, "SYNTHETIC_TEST-PLATE-420x260-S4")
        self.assertTrue(self.panel.open_session(str(self.dir / "synthetic.json")))
        self.assertTrue(self.panel.wait_idle())
        # the smoke found the family line still naming the session after another baseline was chosen
        other = syn.write_family(self.dir / "plate_y").parent / "baseline" / "extraction" / "manifest.json"
        self.assertTrue(self.panel.choose_baseline(str(other)))
        self.assertEqual(self.panel.family_line.text(), f"Baseline: {other}")
        self.assertEqual(self.ids(), (fpanel.DEFAULT_MODEL_ID, fpanel.DEFAULT_SPECIMEN_ID))
        self.folder_route("plate_z")
        self.assertEqual(self.ids(), (fpanel.DEFAULT_MODEL_ID, fpanel.DEFAULT_SPECIMEN_ID))
        self.assertEqual(self.panel.family.model_id, fpanel.DEFAULT_MODEL_ID)

    def test_f1_08_ids_the_user_entered_stay_and_a_cancelled_choice_changes_nothing(self):
        from PySide6.QtTest import QTest

        self.tracked()
        auto = self.ids()
        self.panel.model_edit.clear()
        QTest.keyClicks(self.panel.model_edit, auto[0])  # typed by the user, even if equal to the filled-in id
        self.panel.specimen_edit.setText("PLATE-Z")  # entered (the text is not the filled-in id)
        self.folder_route("plate_z")
        self.assertEqual(self.ids(), (auto[0], "PLATE-Z"))
        self.assertEqual((self.panel.family.model_id, self.panel.family.specimen_id), (auto[0], "PLATE-Z"))
        self.assertTrue(self.panel.run())
        self.assertTrue(self.panel.wait_idle())
        # a cancelled dialog changes neither the ids nor the chosen set
        self.tracked("again")
        before = (self.ids(), self.panel.baseline_manifest, self.panel.baseline_inp, self.panel.family,
                  self.panel.result, self.panel.freshness(), dict(self.panel._auto_ids))
        self.panel._ask_file, self.panel._ask_folder = (lambda *_a: ""), (lambda *_a: "")
        self.assertFalse(self.panel.choose_baseline())
        self.assertFalse(self.panel.choose_baseline_inp())
        self.assertFalse(self.panel.choose_states_folder())
        self.assertFalse(self.panel.load_declaration())
        self.assertFalse(self.panel.open_session())
        self.assertEqual((self.ids(), self.panel.baseline_manifest, self.panel.baseline_inp, self.panel.family,
                          self.panel.result, self.panel.freshness(), dict(self.panel._auto_ids)), before)
        self.assertEqual(self.panel.freshness()[0], "CURRENT")

    @unittest.skipUnless(HAVE_M11, "the M11 S4 packages and the verified baseline copies are not on this computer")
    def test_f1_08_m11_after_a_synthetic_declaration(self):
        self.tracked()
        self.assertTrue(self.panel.choose_baseline(str(M11_BASE)))
        self.assertTrue(self.panel.choose_baseline_inp(str(M11_INP)))
        self.assertTrue(self.panel.choose_states_folder(str(S4)))
        self.assertTrue(self.panel.run())
        self.assertTrue(self.panel.wait_idle())
        result = self.panel.result
        self.assertEqual((result["model_id"], result["specimen_id"]),
                         (fpanel.DEFAULT_MODEL_ID, fpanel.DEFAULT_SPECIMEN_ID))  # neutral, never guessed
        fe7 = branch(result, "FE7")
        modes = {int(m.number): float(m.frequency_hz) for m in fr._dataset(str(M11_BASE)).sorted_modes()}
        self.assertEqual((fe7["baseline_mode"], fe7["hz"]), (7, modes[7]))  # the baseline FE package itself
        self.assertAlmostEqual(fe7["hz"], 19.07217, places=5)
        before = json.dumps(result, sort_keys=True, default=str)
        rows = []
        for value in (5250.0, 4750.0, 5000.0, 5250.0):
            self.assertTrue(self.panel.predict("G12", value))
            self.assertTrue(self.panel.wait_idle())
            self.assertEqual(self.panel.source_check["state"], "SOURCES_VERIFIED")
            rows.append(next(r for r in self.panel.prediction["rows"] if r["term"] == "FE7"))
        self.assertEqual(json.dumps(self.panel.result, sort_keys=True, default=str), before)  # baseline untouched
        self.assertEqual(rows[0], rows[3])  # nothing accumulates
        self.assertEqual(rows[2]["predicted_hz"], fe7["hz"])
        self.assertAlmostEqual(rows[0]["solved_hz"], 19.5264, places=3)
        self.assertTrue(self.panel.choose_baseline(str(self.dir / "family" / "baseline" / "extraction" /
                                                       "manifest.json")))
        self.assertEqual(self.panel.freshness()[0], "STALE")
        self.assertFalse(self.panel.predict("G12", 5250.0))

    def test_the_tracking_can_be_cancelled(self):
        self.assertTrue(self.panel.load_declaration(str(syn.write_family(self.dir / "family"))))
        self.assertTrue(self.panel.run())
        self.panel.cancel()
        self.assertTrue(self.panel.wait_idle())
        self.assertIsNone(self.panel.result)
        self.assertIn("Cancelled", self.panel.message.text())


if __name__ == "__main__":
    unittest.main()
