"""PRIORITY-8: the research workbench of ANY single plate (services headless; the panel in Qt ``offscreen``).

Two plates of different sizes and identities (the synthetic demonstration DEMO-SPB-420x260 and a 600 × 300 mm plate)
go through the workflow with no M11 constant: passport, units, thickness, serialisation; sources by SHA-256 and the
modal set; registration evidence (complete is never frozen; wrong axes, DOF, provenance refused); EXP1 and the first
elastic FE mode kept; close groups and no pairs; sensitivities of this FE model only; the gate (registration
decision, rank, FIT / HOLDOUT); the offline research study on declared synthetic data; no material value is released;
save, reopen, export; the panel in the window.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modal_core import ModalDataset, ModeShape  # noqa: E402
from services import generic_plate_evidence as gev  # noqa: E402
from services import generic_plate_offline_study as off  # noqa: E402
from services import generic_plate_workbench as wb  # noqa: E402

DEMO = ROOT / "docs" / "examples" / "generic_single_plate_demo"
TRUTH = {"E_in_plane": 52000.0, "G12": 4300.0}  # declared in research/generic_single_plate_demo/make_demo.py


def demo_study() -> wb.Study:
    study = wb.open_study(DEMO / "DEMO_STUDY.json")
    return wb.set_diagnostics(study, wb.load_synthetic_inputs(DEMO / "DEMO_SYNTHETIC_INPUTS.json", study))


def demo_ready() -> wb.Study:
    study = off.with_sensitivities(demo_study(), DEMO / "DEMO_SENSITIVITIES.json")
    return off.with_declaration(study, DEMO / "DEMO_DECLARATION.json")


def q(kind, value, unit, provenance="MEASURED", uncertainty=None):
    return wb.Quantity(kind, value, unit, provenance, "test record", "test", uncertainty)


def grid(a_mm, b_mm, offset=10.0, nu=11, nv=6):
    """Scan points (m) of a window (a − 2·offset) × (b − 2·offset), centred, on the u / v axes."""
    us = np.linspace(-(a_mm / 2 - offset), a_mm / 2 - offset, nu) / 1000.0
    vs = np.linspace(-(b_mm / 2 - offset), b_mm / 2 - offset, nv) / 1000.0
    return np.array([[u, v, 0.0] for v in vs for u in us])


def facts(provenance="MEASURED", **changes):
    values = {"scanned_face": "marked", "grid_plus_u_edge": 2, "grid_plus_v_edge": 1,
              "scan_window_offsets_mm": {"-u": 10.0, "+u": 10.0, "-v": 10.0, "+v": 10.0},
              "scan_scale": {"mm_per_unit": 1000.0}, "scan_metric_geometry": True, "measured_dof": "Z",
              "fe_x_along_edges": "1/3", "fe_origin_corner": [3, 4], "fe_normal_face": "marked"}
    values.update(changes)
    return tuple(gev.EvidenceFact(k, v, provenance, "test record") for k, v in values.items())


def plate_600() -> wb.Study:
    passport = wb.Passport("DESIGN-X", "PLATE-X-600x300", "RUN-X1", "2026-11-02", "caliper and scale",
                           q("length", 60.0, "cm", uncertainty=0.05), q("length", 0.3, "m", uncertainty=0.0005),
                           q("mass", 0.62, "kg", uncertainty=0.0001), wb.not_available("density"),
                           tuple(wb.ThicknessReading(f"P{i}", q("length", 1.9 + 0.01 * (i % 3), "mm"), "micrometer")
                                 for i in range(9)))
    return replace_study(wb.new_study(), passport=passport, evidence=facts())


def replace_study(study, **changes):
    from dataclasses import replace

    return replace(study, **changes)


# ----------------------------------------------------------------------------- 1–4: passports, units, thickness

class PassportTests(unittest.TestCase):
    def test_two_plates_of_different_size_and_identity(self):
        demo, other = demo_study(), plate_600()
        self.assertEqual(wb.plan_mm(demo.passport), (420.0, 260.0))
        self.assertEqual(wb.plan_mm(other.passport), (600.0, 300.0))
        self.assertNotEqual(demo.passport.physical_specimen_id, other.passport.physical_specimen_id)
        e_demo = wb.evidence_result(demo)
        e_other = wb.evidence_result(other, grid(600, 300), (600.0, 300.0))
        self.assertEqual((e_demo.status, e_other.status), (gev.COMPLETE, gev.COMPLETE))
        self.assertFalse(e_demo.frozen or e_other.frozen or e_demo.mac_computed)
        # the 600 × 300 plate is not checked against the M11 plan (301 × 300) nor the demo's
        wrong = wb.evidence_result(other, grid(600, 300), (301.0, 300.0))
        self.assertEqual(wrong.status, gev.REGISTRATION_NOT_VERIFIED)
        self.assertIn("FE plan against the passport", [m[0] for m in wrong.missing])
        points = gev.map_points_to_fe(e_other, grid(600, 300))
        self.assertAlmostEqual(points[:, 0].min(), 10.0, places=6)
        self.assertAlmostEqual(points[:, 0].max(), 590.0, places=6)

    def test_units_are_converted_and_unknown_values_kept(self):
        self.assertEqual(q("length", 60.0, "cm").base(), 600.0)
        self.assertEqual(q("mass", 0.62, "kg").base(), 620.0)
        self.assertEqual(q("modulus", 52.0, "GPa").base(), 52000.0)
        self.assertEqual(q("density", 1.55, "g/cm3").base(), 1550.0)
        for bad in (lambda: q("length", 10, "yard"), lambda: q("mass", -1, "g"), lambda: q("length", float("nan"), "mm"),
                    lambda: q("ratio", 0.7, "1"), lambda: wb.Quantity("length", 5.0, "mm"),  # a value needs provenance
                    lambda: wb.Quantity("length", None, "", "MEASURED")):
            with self.assertRaises(wb.PassportError):
                bad()
        na = wb.not_available("density")
        self.assertIsNone(na.base())
        self.assertEqual(na.text(), "NOT_AVAILABLE")
        derived = {d.name: d for d in wb.derived_quantities(plate_600().passport)}
        self.assertAlmostEqual(derived["areal_density"].value, 0.62 / 0.18)
        self.assertEqual(derived["areal_density"].provenance, "DERIVED")
        self.assertEqual(derived["areal_density"].basis, ("mass", "length", "width"))

    def test_thickness_points_and_incomplete_measurements(self):
        study = plate_600()
        self.assertEqual(wb.thickness_readiness(study.passport)[0], wb.PASS)
        five = replace_study(study, passport=replace_study(study.passport, thickness=study.passport.thickness[:5]))
        state, detail = wb.thickness_readiness(five.passport)
        self.assertEqual(state, wb.BLOCKED)
        self.assertIn("5 measured thickness points < 9", detail)
        synthetic = tuple(wb.ThicknessReading(r.position, q("length", 2.0, "mm", "SYNTHETIC")) for r in
                          study.passport.thickness)
        physical = replace_study(study, passport=replace_study(study.passport, thickness=synthetic))
        self.assertEqual(wb.thickness_readiness(physical.passport, wb.PHYSICAL)[0], wb.BLOCKED)
        self.assertEqual(wb.thickness_readiness(physical.passport, wb.SYNTHETIC_DEMO)[0], wb.PASS)
        ready = wb.readiness(physical, wb.evidence_result(physical))
        self.assertIn("synthetic values", [c.name for c in ready.checks if c.state == wb.BLOCKED])
        t = wb.thickness_summary(study.passport)
        self.assertGreater(t["sd_mm"], 0)  # an observed scatter; the readings keep uncertainty None
        self.assertTrue(all(r.thickness.uncertainty is None for r in study.passport.thickness))
        missing = replace_study(study, passport=replace_study(study.passport, mass=wb.not_available("mass")))
        geometry = next(c for c in wb.readiness(missing, wb.evidence_result(missing)).checks
                        if c.name == "geometry and mass")
        self.assertEqual(geometry.state, wb.BLOCKED)
        self.assertIn("NOT_AVAILABLE: mass", geometry.detail)

    def test_passport_serialisation_round_trip(self):
        study = plate_600()
        study = replace_study(study, passport=replace_study(study.passport, claims={
            "suspension": wb.Claim("two cords", "HUMAN_CONFIRMED", "owner"), "measured_dofs": wb.Claim("Z", "MEASURED",
                                                                                                      "instrument")},
            constants=(wb.Constant("nu12", q("ratio", 0.05, "1", "HUMAN_CONFIRMED"), "FIXED"),)))
        data = json.loads(json.dumps(wb.study_to_dict(study), default=str))
        back = wb.study_from_dict(data)
        self.assertEqual(back.passport, study.passport)
        self.assertEqual(back.evidence, study.evidence)
        self.assertEqual(data["approved_material_values"]["status"], "NOT_AVAILABLE")
        with self.assertRaises(wb.StudyRefused):
            wb.study_from_dict({"schema": "other"})


# ----------------------------------------------------------------------------- 5–6: sources and the modal set

class SourceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)
        self.unv = self.dir / "plate x.unv"
        self.unv.write_bytes(b"synthetic experimental file")
        self.manifest = self.dir / "manifest.json"
        self.manifest.write_bytes(b"{}")
        self.exp_id = {"path": str(self.unv), "sha256": wb.file_sha256(self.unv), "size": 27}
        self.fe_id = {"path": str(self.manifest), "sha256": wb.file_sha256(self.manifest), "size": 2}
        self.set_a = {"names": ["polymax_a", "a"], "records": 8}

    def test_a_substituted_file_is_shown_and_refused(self):
        study = wb.link_sources(plate_600(), self.exp_id, self.fe_id, self.set_a)
        self.assertTrue(wb.source_status(study, self.exp_id, self.fe_id, self.set_a)["consistent"])
        other = dict(self.exp_id, sha256="9" * 64)
        status = wb.source_status(study, other, self.fe_id, self.set_a)
        self.assertEqual((status["experimental"], status["consistent"]), ("CHANGED", False))
        self.assertEqual(wb.verify_source(study, "experimental")[0], "VERIFIED")
        self.unv.write_bytes(b"synthetic experimental file, changed")
        self.assertEqual(wb.verify_source(study, "experimental")[0], "CHANGED")
        moved = self.dir / "moved.unv"
        moved.write_bytes(b"synthetic experimental file")
        relocated = wb.relocate_source(study, "experimental", str(moved))
        self.assertEqual(relocated.sources["experimental"].path, str(moved))
        with self.assertRaises(wb.StudyRefused):
            wb.relocate_source(study, "experimental", str(self.unv))  # another content: refused
        self.assertEqual(wb.verify_source(study, "experimental", str(self.dir / "absent.unv"))[0], "MISSING")

    def test_a_changed_modal_set_and_relinking_reset_the_results(self):
        study = wb.link_sources(plate_600(), self.exp_id, self.fe_id, self.set_a)
        status = wb.source_status(study, self.exp_id, self.fe_id, {"names": ["polymax_b", "b"], "records": 8})
        self.assertEqual(status["modal_set"], "CHANGED")
        self.assertEqual(wb.source_status(study, self.exp_id, self.fe_id, None)["modal_set"], "NOT_CHOSEN")
        study = replace_study(study, diagnostics={"experimental": []}, declaration={"data": {}},
                              offline_result={"status": "x"})
        relinked = wb.link_sources(study, self.exp_id, self.fe_id, self.set_a)
        self.assertIsNone(relinked.diagnostics)
        self.assertIsNone(relinked.declaration)
        self.assertIsNone(relinked.offline_result)
        with self.assertRaises(wb.StudyRefused):
            wb.link_sources(study, None, None, None)


# ----------------------------------------------------------------------------- 7–8: registration evidence

class EvidenceTests(unittest.TestCase):
    def evaluate(self, items, kind=wb.PHYSICAL):
        return gev.evaluate(items, (600.0, 300.0), 0.5, kind, grid(600, 300), (600.0, 300.0))

    def test_no_registration_without_the_facts(self):
        result = self.evaluate(facts()[:4])
        self.assertEqual(result.status, gev.REGISTRATION_NOT_VERIFIED)
        self.assertIn("fe_origin_corner", [m[0] for m in result.missing])
        study = replace_study(plate_600(), evidence=facts()[:4])
        self.assertEqual(wb.readiness(study, wb.evidence_result(study)).status, wb.NOT_READY)

    def test_wrong_axes_dof_and_provenance_are_refused(self):
        cases = {"opposite edges": facts(grid_plus_v_edge=4), "mirror image": facts(grid_plus_v_edge=3),
                 "in-plane DOF": facts(measured_dof="XYZ"), "FE normal": facts(fe_normal_face="unmarked"),
                 "FE X axis": facts(fe_x_along_edges="1/2")}
        for name, items in cases.items():
            with self.subTest(case=name):
                self.assertEqual(self.evaluate(items).status, gev.REGISTRATION_NOT_VERIFIED)
        for provenance in ("CANDIDATE", "CONVENTION_ONLY", "NOT_VERIFIED", "SYNTHETIC"):
            with self.subTest(provenance=provenance):
                self.assertEqual(self.evaluate(facts(provenance)).status, gev.REGISTRATION_NOT_VERIFIED)
        self.assertEqual(self.evaluate(facts("SYNTHETIC"), gev.SYNTHETIC_DEMO).status, gev.COMPLETE)
        self.assertEqual(self.evaluate(facts()).status, gev.COMPLETE)
        with self.assertRaises(ValueError):
            gev.EvidenceFact("scanned_face", "marked", "GUESSED", "")

    def test_a_scan_window_that_does_not_close_the_plate_is_refused(self):
        result = self.evaluate(facts(scan_window_offsets_mm={"-u": 30.0, "+u": 10.0, "-v": 10.0, "+v": 10.0}))
        self.assertIn("scan window", [m[0] for m in result.missing])
        self.assertEqual(gev.evaluate(facts(), (600.0, 300.0), None, wb.PHYSICAL, grid(600, 300)).status,
                         gev.REGISTRATION_NOT_VERIFIED)  # no plan tolerance: not checkable

    def test_typed_values_from_the_form(self):
        self.assertEqual(gev.parse_fact_value("fe_origin_corner", "3,4"), [3, 4])
        self.assertEqual(gev.parse_fact_value("scan_window_offsets_mm", "-u=1, +u=2, −v=3, +v=4"),
                         {"-u": 1.0, "+u": 2.0, "-v": 3.0, "+v": 4.0})
        self.assertEqual(gev.parse_fact_value("scan_scale", "mm_per_unit=1000"), {"mm_per_unit": 1000.0})
        self.assertIs(gev.parse_fact_value("scan_metric_geometry", "yes"), True)
        self.assertIsNone(gev.parse_fact_value("measured_dof", " "))
        with self.assertRaises(ValueError):
            gev.parse_fact_value("unknown", "x")


# ----------------------------------------------------------------------------- 9–10: modal diagnostics

def _mode(number, hz, coordinates, vectors):
    return ModeShape(number, hz, np.arange(len(coordinates)), coordinates, vectors)


def fe_dataset():
    from services.local_fe_preview import FePreview, PreviewMode

    xy = np.array([[x, y, 0.0] for x in np.linspace(0, 600, 13) for y in np.linspace(0, 300, 7)])
    rigid = np.tile([0.0, 0.0, 1.0], (len(xy), 1))
    twist = np.column_stack([np.zeros(len(xy)), np.zeros(len(xy)), (xy[:, 0] - 300) * (xy[:, 1] - 150) / 45000.0])
    bend = np.column_stack([np.zeros(len(xy)), np.zeros(len(xy)), np.cos(np.pi * xy[:, 0] / 300.0)])
    modes = [_mode(1, 0.01, xy, rigid), _mode(7, 21.0, xy, twist), _mode(8, 40.0, xy, bend), _mode(9, 41.0, xy, bend)]
    dataset = ModalDataset("fe", Path("fe"), modes)
    return FePreview(Path("manifest.json"), "fe", "step", tuple(PreviewMode(m.number, m.frequency_hz, "test", len(xy))
                                                              for m in modes), (), dataset)


def exp_preview():
    records = tuple(SimpleNamespace(number=n, frequency_hz=hz, label=f"record {n}", provisional=(n == 4),
                                    ambiguous=False) for n, hz in ((1, 20.5), (2, 39.6), (3, 40.6), (4, 55.0)))
    coordinates = grid(600, 300)
    dataset = ModalDataset("exp", Path("exp"), [_mode(1, 20.5, coordinates, np.zeros_like(coordinates))])
    return SimpleNamespace(sets=(SimpleNamespace(display_name="polymax_a", key="a", records=records,
                                                 dataset=dataset),))


class DiagnosticsTests(unittest.TestCase):
    def test_exp1_and_the_first_elastic_fe_mode_are_kept(self):
        diag = wb.diagnostics_from_previews(exp_preview(), 0, fe_dataset())
        self.assertEqual([r["exp"] for r in diag["proximity"]], [1, 2, 3, 4])  # EXP1 included
        self.assertEqual([m["number"] for m in diag["fe_elastic"]], [7, 8, 9])  # FE7, the first elastic, included
        self.assertEqual(diag["fe_rigid_excluded"], [1])  # by the code's shape criterion, not a frequency
        self.assertEqual(diag["proximity"][0]["nearest"][0], 7)
        self.assertEqual(diag["pairs"], [])
        self.assertEqual(diag["mac"], "NOT_AVAILABLE")
        self.assertFalse(diag["proximity"][3]["admissible_record"])  # an FRF peak is never an admissible mode
        self.assertEqual(diag["fe_extent_mm"], (600.0, 300.0))
        self.assertEqual(len(diag["scan_points_m"]), 66)
        with self.assertRaises(wb.StudyRefused):
            wb.diagnostics_from_previews(exp_preview(), None, fe_dataset())

    def test_close_and_permuted_modes_are_flagged_never_assigned(self):
        diag = wb.diagnostics_from_previews(exp_preview(), 0, fe_dataset())
        self.assertIn(["EXP2", "EXP3"], diag["experimental_close_groups"])
        self.assertIn(["FE8", "FE9"], diag["fe_close_groups"])
        # EXP2 and EXP3 are nearest to different FE modes by |Δf|, each with the other as second candidate
        self.assertEqual((diag["proximity"][1]["nearest"][0], diag["proximity"][1]["second"][0]), (8, 9))
        self.assertEqual((diag["proximity"][2]["nearest"][0], diag["proximity"][2]["second"][0]), (9, 8))
        self.assertTrue(all(r["status"] == wb.PROXIMITY_ONLY for r in diag["proximity"]))
        ready = wb.readiness(replace_study(plate_600(), diagnostics=diag), gev.evaluate((), None, None))
        self.assertEqual(next(c for c in ready.checks if c.name == "modal families and close groups").state, wb.OPEN)


# ----------------------------------------------------------------------------- 11–17: offline study

class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.study = demo_ready()
        self.evidence = wb.evidence_result(self.study)
        self.states = off.states(self.study, self.evidence)

    def test_an_admissible_offline_run_on_declared_synthetic_data(self):
        self.assertEqual(self.states["gate"], [])
        result = off.run_offline_study(self.study, self.evidence, self.states["sensitivities"],
                                       self.states["declaration"])
        self.assertEqual(result["status"], "CONVERGED")
        for name, truth in TRUTH.items():
            self.assertLess(abs(result["candidate"][name]["value"] / truth - 1), 0.01, name)
        for label in ("DIAGNOSTIC_OPTIMIZER_CANDIDATE", "NOT_A_RELEASE_VALUE", "NOT_A_MATERIAL_PROPERTY",
                      wb.SYNTHETIC_LABEL):
            self.assertIn(label, result["labels"])
        self.assertEqual(result["extrapolation"], {})
        self.assertEqual(result["approved_material_values"]["status"], "NOT_AVAILABLE")
        def keys(value):
            if isinstance(value, dict):
                return [k for k in value] + [x for v in value.values() for x in keys(v)]
            return [x for v in value for x in keys(v)] if isinstance(value, list) else []
        self.assertFalse([k for k in keys(result) if "mac" in str(k).lower()])  # MAC is no input and no output
        self.assertIsInstance(result["derived"]["D11_Nmm"], float)  # ν12 FIXED and thickness given: DERIVED

    def test_fit_and_holdout_are_kept_as_declared(self):
        result = off.run_offline_study(self.study, self.evidence, self.states["sensitivities"],
                                       self.states["declaration"])
        roles = {t["term"].split(" ")[0]: t["role"] for t in result["terms"]}
        self.assertEqual(roles, {"EXP1": "FIT", "EXP2": "FIT", "EXP3": "FIT", "EXP5": "FIT", "EXP6": "FIT",
                                 "EXP4": "HOLDOUT", "EXP7": "HOLDOUT", "EXP8": "HOLDOUT"})
        fit = [t["residual"] for t in result["terms"] if t["role"] == "FIT"]
        self.assertAlmostEqual(result["objective"], 0.5 * sum(r * r for r in fit), places=9)  # HOLDOUT is not in Φ
        raw = json.loads((DEMO / "DEMO_DECLARATION.json").read_text(encoding="utf-8"))
        for change in ({"holdout_declared": None}, {"observations": [dict(raw["observations"][0], role="MAYBE")]}):
            bad = dict(raw, **change)
            if change.get("holdout_declared", 1) is None:
                bad.pop("holdout_declared")
            with self.subTest(change=str(change)[:40]), self.assertRaises(off.OfflineRefused):
                off.load_declaration(bad, self.study, self.states["sensitivities"])

    def test_insufficient_rank_is_refused_before_any_estimate(self):
        study = off.with_declaration(self.study, DEMO / "DEMO_DECLARATION_TWO_ROWS.json")
        states = off.states(study, self.evidence)
        self.assertEqual(states["rank"]["rank"], 1)
        self.assertTrue(any(r.startswith("RANK_DEFICIENT") for r in states["gate"]))
        with self.assertRaises(off.OfflineRefused):
            off.run_offline_study(study, self.evidence, states["sensitivities"], states["declaration"])

    def test_no_sensitivities_shows_the_plan(self):
        study = demo_study()
        states = off.states(study, wb.evidence_result(study))
        self.assertIn("no FE sensitivity table of this FE model is loaded", states["gate"])
        ready = wb.readiness(study, wb.evidence_result(study), None, states["sensitivity_state"],
                             states["declaration_state"], states["rank_state"])
        self.assertEqual(ready.status, wb.NOT_READY)
        self.assertTrue(any("2 × 2 = 4 Abaqus Frequency solves" in line for line in ready.sensitivity_plan))
        self.assertTrue(any("No Abaqus run is started" in line for line in ready.sensitivity_plan))

    def test_sensitivities_of_another_fe_model_or_specimen_are_refused(self):
        raw = json.loads((DEMO / "DEMO_SENSITIVITIES.json").read_text(encoding="utf-8"))
        m11 = copy.deepcopy(raw)
        m11["fe_model"] = {"name": "M11 S4R", "manifest_sha256":
                           "354966dae2126d11610b9fdb56804006b56b40aea1cf7a180278ef375893b4c7"}
        other = copy.deepcopy(raw)
        other["specimen"]["physical_specimen_id"] = "PLATE-300x300x1mm"
        e1e2 = copy.deepcopy(raw)
        e1e2["parameters"] = {"E1": {"baseline": 50000.0}, "E2": {"baseline": 50000.0}}
        baseline = copy.deepcopy(raw)
        baseline["rows"][0]["f_baseline_hz"] = 40.0
        for name, table in (("another FE model (M11)", m11), ("another specimen", other), ("E1 ≠ E2", e1e2),
                            ("another baseline", baseline)):
            with self.subTest(case=name), self.assertRaises(off.OfflineRefused):
                off.load_sensitivities(table, self.study)

    def test_an_unconfirmed_fit_is_refused(self):
        raw = json.loads((DEMO / "DEMO_DECLARATION.json").read_text(encoding="utf-8"))
        no_decision = dict(raw, registration_decision={})
        decl = off.load_declaration(no_decision, self.study, self.states["sensitivities"])
        reasons = off.gate(self.study, self.evidence, self.states["sensitivities"], decl)
        self.assertTrue(any("never decides a registration" in r for r in reasons))
        open_evidence = replace_study(self.study, evidence=self.study.evidence[:3])
        reasons = off.gate(open_evidence, wb.evidence_result(open_evidence), self.states["sensitivities"],
                           self.states["declaration"])
        self.assertTrue(any("not complete" in r for r in reasons))
        physical = replace_study(self.study, kind=wb.PHYSICAL)
        with self.assertRaises(off.OfflineRefused):  # a synthetic declaration in a physical study
            off.load_declaration(raw, physical, None)
        with self.assertRaises(off.OfflineRefused):
            off.load_declaration(dict(raw, experimental_frequencies_hz={"1": 30.0}), self.study, None)

    def test_no_material_value_is_released(self):
        result = off.run_offline_study(self.study, self.evidence, self.states["sensitivities"],
                                       self.states["declaration"])
        with self.assertRaises(off.ReleaseRefused):
            off.release_material_values(result)
        with self.assertRaises(off.ReleaseRefused):
            off.release_material_values(None)
        data = wb.study_to_dict(replace_study(self.study, offline_result=result))
        self.assertEqual(data["approved_material_values"]["status"], "NOT_AVAILABLE")


# ----------------------------------------------------------------------------- 18–19: save, reopen, export

class PersistenceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)
        self.study = demo_ready()
        evidence = wb.evidence_result(self.study)
        states = off.states(self.study, evidence)
        self.study = replace_study(self.study, offline_result=off.run_offline_study(
            self.study, evidence, states["sensitivities"], states["declaration"]))

    def test_save_and_reopen(self):
        path = wb.save_study(self.study, self.dir / "study.json")
        back = wb.open_study(path)
        self.assertEqual(back.passport, self.study.passport)
        self.assertEqual(back.evidence, self.study.evidence)
        self.assertEqual(back.sensitivities, self.study.sensitivities)
        self.assertEqual(back.declaration, self.study.declaration)
        self.assertEqual(back.history[-1][1], "opened")
        self.assertEqual(off.states(back, wb.evidence_result(back))["gate"], [])  # the files are checked again
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIs(data["registration"]["frozen"], False)
        self.assertEqual(data["registration"]["status_when_saved"], gev.COMPLETE)  # complete, never frozen
        self.assertNotIn("manifest.json", json.dumps(data))  # no heavy FE file inside the study

    def test_a_stored_registration_status_is_never_trusted(self):
        data = wb.study_to_dict(replace_study(self.study, evidence=self.study.evidence[:2]))
        data["registration"]["status_when_saved"] = "FROZEN_ACCEPTED"
        data["registration"]["frozen"] = True
        back = wb.study_from_dict(data)
        self.assertEqual(wb.evidence_result(back).status, gev.REGISTRATION_NOT_VERIFIED)
        broken = self.dir / "broken.json"
        broken.write_text("{ not json", encoding="utf-8")
        with self.assertRaises(wb.StudyRefused):
            wb.open_study(broken)

    def test_export(self):
        evidence = wb.evidence_result(self.study)
        written = wb.export_report(self.study, self.dir / "report", evidence, wb.readiness(self.study, evidence))
        names = sorted(p.suffix for p in written)
        self.assertEqual(names, [".csv", ".csv", ".csv", ".csv", ".json", ".md"])
        md = next(p for p in written if p.suffix == ".md").read_text(encoding="utf-8")
        self.assertIn(wb.SYNTHETIC_LABEL, md)
        self.assertIn("## Approved material values", md)
        self.assertIn("NOT_AVAILABLE", md)
        data = json.loads(next(p for p in written if p.suffix == ".json").read_text(encoding="utf-8"))
        self.assertEqual(data["approved_material_values"]["status"], "NOT_AVAILABLE")
        self.assertEqual(data["readiness"]["status"], wb.NOT_READY)
        frequencies = next(p for p in written if p.name.endswith("_frequencies.csv")).read_text(encoding="utf-8")
        self.assertEqual(len(frequencies.strip().splitlines()), 13)  # header + EXP1–EXP12


# ----------------------------------------------------------------------------- the panel in the window

try:
    from PySide6.QtWidgets import QApplication, QLabel  # noqa: F401
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT or os.environ.get("NEW_GUI_REQUIRE_QT") == "1", "PySide6 is not installed")
class PanelTests(unittest.TestCase):
    def setUp(self):
        from new_gui import window as wm

        self.wm = wm
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
        self.panel = self.window.workbench

    def test_the_page_keeps_study_a_and_shows_nothing_before_use(self):
        self.assertIs(self.window.plate_tabs.widget(0), self.window.plate)
        self.assertEqual(self.window.plate_tabs.tabText(1), "B. New Single Plate")
        self.assertEqual(self.window.plate_tabs.tabToolTip(1), "B. New Single Plate — Research Workbench")
        texts = " ".join(w.text() for w in self.panel.findChildren(QLabel))
        for word in ("PHYSICAL_REGISTRATION", "NOT_READY", "SYNTHETIC_DEMONSTRATION"):
            self.assertNotIn(word, texts)
        self.assertFalse(self.panel.run_button.isEnabled())
        self.window.show_page(self.wm.PLATE_PAGE)
        self.window.plate_tabs.setCurrentIndex(1)
        self.app.processEvents()
        self.assertTrue(self.panel.active)
        self.assertIn("6. Parameter Observability: not ready", self.panel.step_line.text())

    def test_the_synthetic_demo_through_the_panel(self):
        with mock.patch("subprocess.Popen") as popen, mock.patch("subprocess.run") as run:
            self.assertTrue(self.panel.open_study(str(DEMO / "DEMO_STUDY.json")))
            self.assertFalse(self.panel.run_button.isEnabled())
            self.assertTrue(self.panel.load_synthetic_inputs(str(DEMO / "DEMO_SYNTHETIC_INPUTS.json")))
            self.assertEqual(self.panel.tables["proximity"].rowCount(), 12)
            self.assertFalse(self.panel.run_button.isEnabled())  # no sensitivities, no declaration
            self.assertIn("no FE sensitivity table of this FE model is loaded", self.panel.gate_label.text())
            self.assertTrue(self.panel.load_sensitivities(str(DEMO / "DEMO_SENSITIVITIES.json")))
            self.assertTrue(self.panel.load_declaration(str(DEMO / "DEMO_DECLARATION.json")))
            self.assertTrue(self.panel.run_button.isEnabled())
            self.assertTrue(self.panel.run_offline())
            popen.assert_not_called()
            run.assert_not_called()
        self.assertEqual(self.panel.tables["offline"].rowCount(), 8)
        self.assertIn("DIAGNOSTIC_OPTIMIZER_CANDIDATE", " ".join(w.text() for w in self.panel.findChildren(QLabel)))
        self.assertTrue(self.panel.export(str(self.dir / "report")))
        self.assertTrue(self.panel.save_study(str(self.dir / "saved.json")))
        self.assertTrue(self.panel.open_study(str(self.dir / "saved.json")))
        self.assertIsNotNone(self.panel.study.offline_result)
        self.assertIn("evidence complete — not frozen", self.panel.step_line.text())

    def test_a_physical_study_without_inputs_or_registration(self):
        self.panel.new_study()
        self.panel.id_edits["physical_specimen_id"].setText("PLATE-Y-500x250")
        self.panel.id_edits["test_run_id"].setText("RUN-Y1")
        self.assertTrue(self.panel.apply_setup())
        self.assertFalse(self.panel.link_inputs())  # nothing read in the Workspace
        self.assertFalse(self.panel.run_diagnostics())
        self.assertFalse(self.panel.load_synthetic_inputs(str(DEMO / "DEMO_SYNTHETIC_INPUTS.json")))
        self.assertFalse(self.panel.load_sensitivities(str(DEMO / "DEMO_SENSITIVITIES.json")))
        self.assertFalse(self.panel.run_button.isEnabled())
        self.assertTrue(self.panel.evaluate_evidence())
        self.assertIn("NOT_VERIFIED", self.panel.evidence_label.text())
        self.panel.quantity_edits["length"][0].setText("500")
        self.panel.quantity_edits["length"][3].setCurrentIndex(1)  # MEASURED
        self.assertTrue(self.panel.apply_measurements())
        self.assertEqual(self.panel.study.passport.length.base(), 500.0)
        self.panel.quantity_edits["mass"][0].setText("-3")
        self.panel.quantity_edits["mass"][3].setCurrentIndex(1)
        self.assertFalse(self.panel.apply_measurements())  # refused with the reason, the study unchanged
        self.assertIn("positive", self.panel.message.text())

    def test_no_step_widens_the_plate_page(self):
        self.window.resize(900, 680)
        self.window.show_page(self.wm.PLATE_PAGE)
        self.window.plate_tabs.setCurrentIndex(1)
        self.assertTrue(self.panel.open_study(str(DEMO / "DEMO_STUDY.json")))
        self.app.processEvents()
        limit = self.window.plate.minimumSizeHint().width()  # the page's width before PRIORITY-8 (study A)
        self.assertLessEqual(self.panel.minimumSizeHint().width(), limit)
        for index in range(self.panel.tabs.count()):
            self.assertLessEqual(self.panel.tabs.widget(index).minimumSizeHint().width(), limit, index)

    def test_the_link_follows_the_workspace(self):
        from new_gui.shape_panel import ShapePanel

        patcher = mock.patch.object(ShapePanel, "set_preview")  # the shape views are tested on their own
        patcher.start()
        self.addCleanup(patcher.stop)
        unv = self.dir / "x.unv"
        unv.write_bytes(b"x")
        exp_id = {"path": str(unv), "sha256": wb.file_sha256(unv), "size": 1}
        fe_id = {"path": "m.json", "sha256": "1" * 64, "size": 2}
        self.panel.set_inputs(fe_dataset(), fe_id, exp_preview(), exp_id, 0)
        self.assertTrue(self.panel.link_inputs())
        self.assertTrue(self.panel.run_diagnostics())
        self.assertEqual(self.panel.tables["proximity"].item(0, 0).text(), "EXP1")
        self.panel.set_inputs(fe_dataset(), fe_id, exp_preview(), dict(exp_id, sha256="2" * 64), 0)
        self.assertIn("experimental CHANGED", self.panel.sources_label.text())
        self.assertFalse(self.panel.run_diagnostics())


if __name__ == "__main__":
    unittest.main()
