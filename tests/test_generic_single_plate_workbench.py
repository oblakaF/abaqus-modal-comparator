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


class _PanelWindow(unittest.TestCase):
    """The window with the workbench (shared set-up of the panel tests)."""

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


@unittest.skipUnless(HAVE_QT or os.environ.get("NEW_GUI_REQUIRE_QT") == "1", "PySide6 is not installed")
class PanelTests(_PanelWindow):
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

    def test_the_layout_choices_that_keep_the_page_narrow(self):
        """Font-independent: the step buttons stand in two columns over one page at a time, and no row of buttons
        is laid out side by side (the page width itself is checked by the Windows GUI smoke at 900 × 680)."""
        from PySide6.QtWidgets import QHBoxLayout, QPushButton, QStackedWidget

        self.assertIsInstance(self.panel.tabs, QStackedWidget)
        self.assertEqual(self.panel.tabs.count(), 8)
        grid = self.panel.step_buttons.button(0).parentWidget().layout().itemAt(1).layout()
        self.assertEqual(grid.columnCount(), 2)
        for index in range(8):
            row, column, _rows, _columns = grid.getItemPosition(grid.indexOf(self.panel.step_buttons.button(index)))
            self.assertEqual((row, column), (index // 2, index % 2))
        for layout in self.panel.findChildren(QHBoxLayout):
            buttons = [layout.itemAt(i).widget() for i in range(layout.count())
                       if isinstance(layout.itemAt(i).widget(), QPushButton)]
            self.assertLessEqual(len(buttons), 1, [b.text() for b in buttons])

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


# ----------------------------------------------------------------------------- PRIORITY-8-F1 regressions

class F1FreshnessTests(unittest.TestCase):
    """F1.1: results of other or unverified inputs are never current; the history and earlier results are kept."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)
        self.unv = self.dir / "plate.unv"
        self.unv.write_bytes(b"synthetic experimental file")
        self.manifest = self.dir / "manifest.json"
        self.manifest.write_bytes(b"{}")
        (self.dir / "mode_0007.csv").write_bytes(b"large mode file, never hashed by the disk check")
        self.exp_id = {"path": str(self.unv), "sha256": wb.file_sha256(self.unv), "size": 27}
        self.fe_id = {"path": str(self.manifest), "sha256": wb.file_sha256(self.manifest), "size": 2}
        self.set_a = {"names": ["polymax_a", "a"], "records": 4}
        study = wb.link_sources(plate_600(), self.exp_id, self.fe_id, self.set_a)
        self.study = wb.set_diagnostics(study, wb.diagnostics_from_previews(exp_preview(), 0, fe_dataset()))

    def status(self, exp=None, fe=None, modal_set="same"):
        return wb.source_status(self.study, exp if exp is not None else self.exp_id, fe if fe is not None else
                                self.fe_id, self.set_a if modal_set == "same" else modal_set)

    def test_current_only_for_the_same_files_and_set(self):
        self.assertEqual(wb.results_state(self.study, self.status())["state"], wb.CURRENT)
        for case, status in (("experimental", self.status(exp=dict(self.exp_id, sha256="9" * 64))),
                             ("fe", self.status(fe=dict(self.fe_id, sha256="8" * 64))),
                             ("modal set", self.status(modal_set={"names": ["polymax_b", "b"], "records": 4}))):
            with self.subTest(changed=case):
                state = wb.results_state(self.study, status)
                self.assertEqual(state["state"], wb.CHANGED)
                self.assertFalse(state["current"])
        self.assertEqual(wb.results_state(self.study)["state"], wb.NOT_CHECKED)  # nothing read, nothing verified

    def test_results_of_other_inputs_are_stale_and_kept_as_a_record(self):
        from dataclasses import replace

        other = replace(self.study, diagnostics=dict(self.study.diagnostics,
                                                     inputs=dict(self.study.diagnostics["inputs"], fe="7" * 64)))
        self.assertEqual(wb.results_state(other, self.status())["state"], wb.STALE)
        legacy = replace(self.study, diagnostics={k: v for k, v in self.study.diagnostics.items() if k != "inputs"})
        self.assertEqual(wb.results_state(legacy, self.status())["state"], wb.STALE)  # an earlier study file
        history = len(self.study.history)
        relinked = wb.link_sources(self.study, dict(self.exp_id, sha256="6" * 64), self.fe_id, self.set_a)
        self.assertIsNone(relinked.diagnostics)
        self.assertEqual(len(relinked.superseded), 1)
        self.assertEqual(relinked.superseded[0]["inputs"]["experimental"], self.exp_id["sha256"])
        self.assertGreater(len(relinked.history), history)  # the history is kept

    def test_reopening_checks_the_recorded_files_on_disk(self):
        path = wb.save_study(self.study, self.dir / "study.json")
        study = wb.open_study(path)
        with mock.patch.object(wb, "file_sha256", wraps=wb.file_sha256) as hashed:
            disk = wb.disk_status(study)
        self.assertEqual(sorted(Path(c.args[0]).name for c in hashed.call_args_list), ["manifest.json", "plate.unv"])
        self.assertEqual({r: s for r, (s, _d) in disk.items()}, {"experimental": "VERIFIED", "fe": "VERIFIED"})
        self.assertEqual(wb.results_state(study, None, disk)["state"], wb.CURRENT)
        self.unv.write_bytes(b"synthetic experimental file, changed")
        self.assertEqual(wb.results_state(study, None, wb.disk_status(study))["state"], wb.CHANGED)
        moved = self.dir / "moved" / "plate.unv"
        moved.parent.mkdir()
        moved.write_bytes(b"synthetic experimental file")
        self.unv.unlink()
        self.assertEqual(wb.results_state(study, None, wb.disk_status(study))["state"], wb.MISSING)
        relocated = wb.relocate_source(study, "experimental", str(moved))  # a moved file with the same SHA-256
        self.assertEqual(wb.results_state(relocated, None, wb.disk_status(relocated))["state"], wb.CURRENT)

    def test_an_offline_candidate_of_other_inputs_is_not_current(self):
        from dataclasses import replace

        demo = demo_ready()
        evidence = wb.evidence_result(demo)
        states = off.states(demo, evidence)
        demo = replace(demo, offline_result=off.run_offline_study(demo, evidence, states["sensitivities"],
                                                                  states["declaration"]))
        self.assertTrue(wb.results_state(demo)["offline_current"])
        other = replace(demo, offline_result=dict(demo.offline_result, inputs=dict(demo.offline_result["inputs"],
                                                                                   declaration="5" * 64)))
        state = wb.results_state(other)
        self.assertEqual(state["offline"], wb.STALE)
        self.assertFalse(state["offline_current"])

    def test_the_export_never_reports_stale_results_as_current(self):
        from dataclasses import replace

        stale = replace(self.study, offline_result={"status": "CONVERGED", "candidate": {"G12": {"value": 1.0}},
                                                    "terms": [{"term": "EXP1 ↔ FE7", "role": "FIT", "f_exp_hz": 1,
                                                               "f_model_hz": 1, "residual": 0}],
                                                    "inputs": {"diagnostics": None}})
        freshness = wb.results_state(stale, self.status(exp=dict(self.exp_id, sha256="9" * 64)))
        evidence = wb.evidence_result(stale)
        written = wb.export_report(stale, self.dir / "report", evidence, wb.readiness(stale, evidence), freshness)
        data = json.loads(next(p for p in written if p.suffix == ".json").read_text(encoding="utf-8"))
        self.assertIsNone(data["diagnostics"])
        self.assertIsNone(data["offline_result"])
        self.assertEqual(data["not_current_results"]["state"], wb.CHANGED)
        self.assertIsNotNone(data["not_current_results"]["offline_result"])  # kept apart, as a record
        self.assertFalse(any(p.name.endswith("_offline_terms.csv") for p in written))
        frequencies = next(p for p in written if p.name.endswith("_frequencies.csv")).read_text(encoding="utf-8")
        self.assertEqual(len(frequencies.strip().splitlines()), 1)  # the header only
        md = next(p for p in written if p.suffix == ".md").read_text(encoding="utf-8")
        self.assertIn("NOT CURRENT", md)
        self.assertNotIn("Status: CONVERGED", md)


class F1PhysicalGateTests(unittest.TestCase):
    """F1.2: an imported HUMAN_CONFIRMED string never opens the physical offline fit; the demo still runs."""

    def physical(self):
        from dataclasses import replace

        demo = demo_ready()
        study = replace(demo, kind=wb.PHYSICAL, declaration=None, offline_result=None)
        raw = json.loads((DEMO / "DEMO_DECLARATION.json").read_text(encoding="utf-8"))
        raw.update(kind="PHYSICAL", registration_decision={
            "status": off.ADMISSIBLE, "provenance": "HUMAN_CONFIRMED", "reference": "OWNER-DECISION-001",
            "decided_by": "owner", "date": "2026-11-01"})
        return study, raw

    def test_a_declared_human_decision_does_not_open_the_physical_fit(self):
        study, raw = self.physical()
        sensitivities = json.loads((DEMO / "DEMO_SENSITIVITIES.json").read_text(encoding="utf-8"))
        sensitivities["kind"] = "PHYSICAL"
        sens = off.load_sensitivities(sensitivities, study)
        decl = off.load_declaration(raw, study, sens)
        reasons = off.gate(study, wb.evidence_result(study), sens, decl, {"consistent": True})
        self.assertIn(wb.PHYSICAL_DECISION_NOT_VERIFIABLE, reasons)
        with self.assertRaises(off.OfflineRefused):
            off.run_offline_study(study, wb.evidence_result(study), sens, decl, {"consistent": True})
        ready = wb.readiness(study, wb.evidence_result(study))
        owner = next(c for c in ready.checks if c.name == "registration decision (owner)")
        self.assertEqual(owner.state, wb.BLOCKED)
        self.assertIn("PHYSICAL_OFFLINE_FIT_BLOCKED", owner.detail)

    def test_the_synthetic_demonstration_still_runs(self):
        demo = demo_ready()
        evidence = wb.evidence_result(demo)
        states = off.states(demo, evidence)
        self.assertEqual(states["gate"], [])
        self.assertEqual(off.run_offline_study(demo, evidence, states["sensitivities"], states["declaration"])
                         ["status"], "CONVERGED")


class F1UnitTests(unittest.TestCase):
    """F1.3: modulus units are converted to MPa or refused; D11, D66, D12 against hand-computed values."""

    def setUp(self):
        self.study = demo_study()
        self.sens = json.loads((DEMO / "DEMO_SENSITIVITIES.json").read_text(encoding="utf-8"))
        self.decl = json.loads((DEMO / "DEMO_DECLARATION.json").read_text(encoding="utf-8"))

    def test_gpa_and_pa_are_converted_and_other_units_refused(self):
        gpa = copy.deepcopy(self.sens)
        gpa["parameters"] = {"E_in_plane": {"baseline": 50.0, "unit": "GPa"}, "G12": {"baseline": 4.5e9, "unit": "Pa"}}
        loaded = off.load_sensitivities(gpa, self.study)
        self.assertAlmostEqual(loaded["parameters"]["E_in_plane"], 50000.0)
        self.assertAlmostEqual(loaded["parameters"]["G12"], 4500.0)
        self.assertEqual(loaded["units"], {"E_in_plane": "MPa", "G12": "MPa"})
        for unit in ("ksi", None, "mpa"):
            bad = copy.deepcopy(self.sens)
            bad["parameters"]["G12"]["unit"] = unit
            if unit is None:
                bad["parameters"]["G12"].pop("unit")
            with self.subTest(unit=unit), self.assertRaises(off.OfflineRefused):
                off.load_sensitivities(bad, self.study)
        sens = off.load_sensitivities(self.sens, self.study)
        decl = dict(self.decl, unit="GPa", start={"E_in_plane": 50.0, "G12": 4.5},
                    bounds={"E_in_plane": [25.0, 100.0], "G12": [2.25, 9.0]})
        loaded = off.load_declaration(decl, self.study, sens)
        self.assertAlmostEqual(loaded["start"]["E_in_plane"], 50000.0)
        self.assertEqual(loaded["bounds"]["G12"], [2250.0, 9000.0])
        missing = dict(self.decl)
        missing.pop("unit")
        with self.assertRaises(off.OfflineRefused):
            off.load_declaration(missing, self.study, sens)

    def test_bending_stiffness_against_control_values(self):
        from dataclasses import replace

        thickness = tuple(wb.ThicknessReading(f"P{i}", q("length", 2.0, "mm", "SYNTHETIC")) for i in range(9))
        nu = wb.Constant("nu12", q("ratio", 0.2, "1", "SYNTHETIC"), "FIXED")
        study = replace(self.study, passport=replace(self.study.passport, thickness=thickness, constants=(nu,)))
        d = off.derived_bending(study, {"E_in_plane": 60000.0, "G12": 5000.0})
        # D11 = E h³ / (12 (1 − ν²)) = 60000 · 8 / (12 · 0.96); D12 = ν D11; D66 = G h³ / 12 = 5000 · 8 / 12  (N·mm)
        self.assertAlmostEqual(d["D11_Nmm"], 41666.6666667, places=6)
        self.assertAlmostEqual(d["D12_Nmm"], 8333.3333333, places=6)
        self.assertAlmostEqual(d["D66_Nmm"], 3333.3333333, places=6)
        no_nu = replace(study, passport=replace(study.passport, constants=()))
        d = off.derived_bending(no_nu, {"E_in_plane": 60000.0, "G12": 5000.0})
        self.assertEqual((d["D11_Nmm"], d["D12_Nmm"]), ("NOT_AVAILABLE", "NOT_AVAILABLE"))
        self.assertAlmostEqual(d["D66_Nmm"], 3333.3333333, places=6)


@unittest.skipUnless(HAVE_QT or os.environ.get("NEW_GUI_REQUIRE_QT") == "1", "PySide6 is not installed")
class F1PanelTests(_PanelWindow):
    """F1.1 / F1.2 in the panel: a reopened study's sources are checked at once; stale results are not shown."""

    def test_the_buttons_never_pass_their_checked_state_as_an_argument(self):
        from PySide6.QtWidgets import QPushButton

        asked = []
        self.panel._ask_file = lambda title: asked.append(title) or ""
        self.panel.study = wb.new_study(wb.SYNTHETIC_DEMO)
        self.panel.findChild(QPushButton, "wbNew").click()  # clicked(bool) must not become the study kind
        self.app.processEvents()
        self.assertEqual(self.panel.study.kind, wb.PHYSICAL)
        self.panel.findChild(QPushButton, "wbRelocate").click()  # nor the path of a moved source
        self.app.processEvents()
        self.assertEqual(asked, ["Choose the moved experimental source"])

    def test_reopening_shows_missing_sources_and_hides_the_results(self):
        from new_gui.shape_panel import ShapePanel

        patcher = mock.patch.object(ShapePanel, "set_preview")
        patcher.start()
        self.addCleanup(patcher.stop)
        unv = self.dir / "x.unv"
        unv.write_bytes(b"x")
        manifest = self.dir / "manifest.json"
        manifest.write_bytes(b"{}")
        exp_id = {"path": str(unv), "sha256": wb.file_sha256(unv), "size": 1}
        fe_id = {"path": str(manifest), "sha256": wb.file_sha256(manifest), "size": 2}
        self.panel.set_inputs(fe_dataset(), fe_id, exp_preview(), exp_id, 0)
        self.assertTrue(self.panel.link_inputs())
        self.assertTrue(self.panel.run_diagnostics())
        self.assertIn("proximity", self.panel.tables)
        self.assertTrue(self.panel.save_study(str(self.dir / "s.json")))
        self.panel.set_inputs(None, None, None, None, None)  # nothing read: only the disk check remains
        self.assertTrue(self.panel.open_study(str(self.dir / "s.json")))
        self.assertIn("results CURRENT", self.panel.message.text())
        self.assertIn("proximity", self.panel.tables)
        unv.unlink()
        self.assertTrue(self.panel.open_study(str(self.dir / "s.json")))
        self.assertIn("results MISSING", self.panel.message.text())
        self.assertNotIn("proximity", self.panel.tables)
        self.assertIn("NOT CURRENT", self.panel.results_label.text())
        self.assertIn("5. Diagnostics: missing", self.panel.step_line.text().replace("5. Modal Diagnostics",
                                                                                     "5. Diagnostics"))
        self.assertFalse(self.panel.run_button.isEnabled())
        self.assertIn("PHYSICAL_OFFLINE_FIT_BLOCKED", self.panel.gate_label.text())


# ----------------------------------------------------------------------------- PRIORITY-8-F2 regressions

def demo_converged() -> wb.Study:
    from dataclasses import replace

    study = demo_ready()
    evidence = wb.evidence_result(study)
    states = off.states(study, evidence)
    return replace(study, offline_result=off.run_offline_study(study, evidence, states["sensitivities"],
                                                               states["declaration"]))


def with_passport(study: wb.Study, **changes) -> wb.Study:
    from dataclasses import replace

    return replace(study, passport=replace(study.passport, **changes))


class F2OfflineFreshnessTests(unittest.TestCase):
    """F2: the offline candidate belongs to the passport and evidence it was computed with."""

    def setUp(self):
        self.study = demo_converged()
        self.assertEqual(self.study.offline_result["status"], "CONVERGED")
        self.assertTrue(wb.results_state(self.study)["offline_current"])

    def assert_stale(self, study, what):
        state = wb.results_state(study)
        self.assertEqual(state["offline"], wb.STALE)
        self.assertFalse(state["offline_current"])
        self.assertTrue(any(what in r for r in state["reasons"]), state["reasons"])
        return state

    def test_a_thickness_change_makes_the_candidate_stale_but_not_the_diagnostics(self):
        thicker = tuple(wb.ThicknessReading(r.position, q("length", r.thickness.value + 0.1, "mm", "SYNTHETIC"),
                                            r.method) for r in self.study.passport.thickness)
        state = self.assert_stale(with_passport(self.study, thickness=thicker), "the passport")
        self.assertEqual(state["state"], wb.CURRENT)  # the frequency diagnostics keep their sources: still current
        self.assertTrue(state["current"])

    def test_a_changed_fixed_nu12_never_leaves_d11_d12_current(self):
        nu = wb.Constant("nu12", q("ratio", 0.3, "1", "SYNTHETIC"), "FIXED")
        constants = tuple(nu if c.name == "nu12" else c for c in self.study.passport.constants)
        changed = with_passport(self.study, constants=constants)
        self.assert_stale(changed, "the passport")
        with tempfile.TemporaryDirectory() as folder:
            evidence = wb.evidence_result(changed)
            written = wb.export_report(changed, folder, evidence, wb.readiness(changed, evidence))
            data = json.loads(next(p for p in written if p.suffix == ".json").read_text(encoding="utf-8"))
            md = next(p for p in written if p.suffix == ".md").read_text(encoding="utf-8")
            names = [p.name for p in written]
        self.assertIsNone(data["offline_result"])
        self.assertEqual(data["not_current_results"]["offline_state"], wb.STALE)
        self.assertNotIn("D11_Nmm", json.dumps({k: v for k, v in data.items() if k != "not_current_results"}))
        self.assertNotIn("D11", md.split("## Earlier results")[0])
        self.assertFalse(any(n.endswith("_offline_terms.csv") for n in names))

    def test_a_changed_physical_specimen_id_makes_the_candidate_stale(self):
        self.assert_stale(with_passport(self.study, physical_specimen_id="ANOTHER-PLATE"), "the passport")

    def test_changed_evidence_or_conditions_make_the_candidate_stale(self):
        from dataclasses import replace

        evidence = tuple(gev.EvidenceFact(f.key, "unmarked" if f.key == "scanned_face" else f.value, f.provenance,
                                          f.source) for f in self.study.evidence)
        self.assert_stale(replace(self.study, evidence=evidence), "the registration evidence")
        claims = dict(self.study.passport.claims, suspension=wb.Claim("hung on one wire", "SYNTHETIC", "x"))
        self.assert_stale(with_passport(self.study, claims=claims), "the passport")
        same = with_passport(self.study, claims=dict(self.study.passport.claims))
        self.assertTrue(wb.results_state(same)["offline_current"])  # an equal passport stays current

    def test_replacing_the_inputs_keeps_the_candidate_in_superseded(self):
        for replace_input in (lambda s: off.with_sensitivities(s, DEMO / "DEMO_SENSITIVITIES.json"),
                              lambda s: off.with_declaration(s, DEMO / "DEMO_DECLARATION.json")):
            with self.subTest(replace_input=replace_input):
                replaced = replace_input(self.study)
                self.assertIsNone(replaced.offline_result)
                self.assertEqual(len(replaced.superseded), len(self.study.superseded) + 1)
                self.assertEqual(replaced.superseded[-1]["offline_result"]["status"], "CONVERGED")
        retired = wb.retire_offline(self.study, "the registration evidence was changed")
        self.assertEqual(retired.superseded[-1]["reason"], "the registration evidence was changed")
        self.assertIsNone(retired.offline_result)

    def test_reopening_and_export_keep_the_scientific_statuses(self):
        with tempfile.TemporaryDirectory() as folder:
            current = wb.open_study(wb.save_study(self.study, Path(folder) / "current.json"))
            self.assertTrue(wb.results_state(current)["offline_current"])
            stale = with_passport(self.study, physical_specimen_id="ANOTHER-PLATE")
            reopened = wb.open_study(wb.save_study(stale, Path(folder) / "stale.json"))
            self.assertEqual(wb.results_state(reopened)["offline"], wb.STALE)
            evidence = wb.evidence_result(reopened)
            written = wb.export_report(reopened, Path(folder) / "report", evidence, wb.readiness(reopened, evidence))
            data = json.loads(next(p for p in written if p.suffix == ".json").read_text(encoding="utf-8"))
        self.assertEqual(data["results_state"]["offline"], wb.STALE)
        self.assertEqual(data["approved_material_values"]["status"], "NOT_AVAILABLE")
        self.assertIn("DIAGNOSTIC_OPTIMIZER_CANDIDATE", json.dumps(data["not_current_results"]["offline_result"]))

    def test_a_candidate_without_a_passport_fingerprint_is_stale(self):
        from dataclasses import replace

        legacy = replace(self.study, offline_result=dict(self.study.offline_result, inputs={
            k: v for k, v in self.study.offline_result["inputs"].items() if k not in ("passport", "evidence")}))
        self.assert_stale(legacy, "the passport")

    def test_the_physical_offline_fit_stays_blocked(self):
        from dataclasses import replace

        physical = replace(demo_ready(), kind=wb.PHYSICAL)
        reasons = off.gate(physical, wb.evidence_result(physical), None, None, {"consistent": True})
        self.assertIn(wb.PHYSICAL_DECISION_NOT_VERIFIABLE, reasons)


@unittest.skipUnless(HAVE_QT or os.environ.get("NEW_GUI_REQUIRE_QT") == "1", "PySide6 is not installed")
class F2PanelTests(_PanelWindow):
    def test_a_thickness_change_hides_the_old_candidate_and_its_d_values(self):
        self.assertTrue(self.panel.open_study(str(DEMO / "DEMO_STUDY.json")))
        self.assertTrue(self.panel.load_synthetic_inputs(str(DEMO / "DEMO_SYNTHETIC_INPUTS.json")))
        self.assertTrue(self.panel.load_sensitivities(str(DEMO / "DEMO_SENSITIVITIES.json")))
        self.assertTrue(self.panel.load_declaration(str(DEMO / "DEMO_DECLARATION.json")))
        self.assertTrue(self.panel.run_offline())
        shown = " ".join(w.text() for w in self.panel.findChildren(QLabel))
        self.assertIn("D11_Nmm", shown)
        first = self.panel.thickness_table.widgets[0][1]
        first.setText("2.40")
        self.assertTrue(self.panel.apply_measurements())
        shown = " ".join(w.text() for w in self.panel.findChildren(QLabel))
        self.assertIn("Offline candidate STALE — NOT CURRENT", shown)
        self.assertNotIn("D11_Nmm", shown)
        self.assertNotIn("offline", self.panel.tables)
        self.assertIn("proximity", self.panel.tables)  # the diagnostics stay current
        self.assertIn("7. Offline Research Study: stale", self.panel.step_line.text())
        self.assertTrue(self.panel.evaluate_evidence())  # changed evidence: the candidate goes to superseded
        self.assertIsNone(self.panel.study.offline_result)
        self.assertEqual(self.panel.study.superseded[-1]["reason"], "the registration evidence was changed")


if __name__ == "__main__":
    unittest.main()
