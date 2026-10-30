"""PLATE-WORKBENCH-RC1: the physical registration readiness of the single plate and the workbench services (no Qt).

- a synthetic scan with an independently known physical registration takes the full positive path: the evidence is
  complete and the implied transform maps every scan point onto its true FE position; still nothing is frozen and no
  MAC is permitted without a frozen registration;
- an unknown scanned face, an unknown FE ↔ physical edge relation, a computational convention offered as evidence,
  a non-independent derivation, a mirror-image combination, a window that does not close the plate and an in-plane
  DOF are each refused with the exact missing fact;
- the real 261027 evidence stays PHYSICAL_REGISTRATION_NOT_VERIFIED and invents no fact;
- no orientation comes from the data: the link statuses do not depend on the scan coordinates;
- the workbench chain, the ±10 % breakdown and the prepared FE campaign keep every block (NOT_IDENTIFIABLE, M8 /
  D-077, no campaign without a frozen registration; a specimen calibration parameter, never a material constant).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from services import plate_registration_readiness as rr  # noqa: E402
from services import plate_study as ps  # noqa: E402
from services import plate_workbench as pw  # noqa: E402

F = rr.Fact


def synthetic_scan(angle_deg: float = 45.0):
    """A 17 × 17 grid on the plate, in a scanner frame turned by ``angle_deg``: the truth is known.

    Truth: the unmarked face towards the scanner, +u towards edge 2, +v towards edge 3; FE (0, 0) at the corner of
    edges 2 and 3 (so FE +Z leaves the unmarked face). Physical a ∈ [20, 280], b ∈ [10, 290] mm."""
    a, b = np.meshgrid(np.linspace(20, 280, 17), np.linspace(10, 290, 17))
    a, b = a.ravel(), b.ravel()
    su, sv = a, 300.0 - b
    angle = math.radians(angle_deg)
    u = np.array([math.cos(angle), math.sin(angle)])
    v = np.array([-u[1], u[0]])
    xy = np.array([0.01, 0.17]) + ((su - su.mean())[:, None] * u + (sv - sv.mean())[:, None] * v) / 1000.0
    coordinates = np.column_stack([xy, np.full(len(xy), -1.15)])
    return coordinates, np.column_stack([301.0 - a, b])


def evidence(**changes) -> list:
    facts = {
        "scanned_face": F("scanned_face", "unmarked", rr.HUMAN_CONFIRMED, "owner (synthetic)"),
        "grid_plus_u_edge": F("grid_plus_u_edge", 2, rr.HUMAN_CONFIRMED, "photograph with numerals (synthetic)"),
        "grid_plus_v_edge": F("grid_plus_v_edge", 3, rr.HUMAN_CONFIRMED, "photograph with numerals (synthetic)"),
        "rotation_reference": F("rotation_reference", "45° cw from the 261016 mounting", rr.HUMAN_CONFIRMED, "lab"),
        "scan_window_offsets_mm": F("scan_window_offsets_mm", {"-u": 20.0, "+u": 21.0, "-v": 10.0, "+v": 10.0},
                                    rr.MEASURED, "PSV video frame (synthetic)"),
        "scan_scale": F("scan_scale", {"mm_per_unit": 1000.0}, rr.INSTRUMENT_RECORD, "dataset 164"),
        "scan_metric_geometry": F("scan_metric_geometry", "scanner angles and distance", rr.INSTRUMENT_RECORD,
                                  "PSV scanner angles (synthetic)"),
        "measured_dof": F("measured_dof", "+Z", rr.INSTRUMENT_RECORD, "dataset 58"),
        "fe_x_along_edges": F("fe_x_along_edges", "1/3", rr.HUMAN_CONFIRMED, "M11 §13.1"),
        "fe_origin_corner": F("fe_origin_corner", (2, 3), rr.MEASURED, "FE with measured asymmetry (synthetic)"),
        "fe_normal_face": F("fe_normal_face", "unmarked", rr.MEASURED, "FE with measured asymmetry (synthetic)"),
    }
    for key, fact in changes.items():
        if fact is None:
            facts.pop(key)
        else:
            facts[key] = fact
    return list(facts.values())


class PositivePathTests(unittest.TestCase):
    def test_a_known_physical_registration_takes_the_full_positive_path(self):
        coordinates, truth = synthetic_scan()
        readiness = rr.evaluate(evidence(), coordinates, "Z", (301.0, 300.0))
        self.assertEqual(readiness.status, rr.COMPLETE, readiness.missing)
        self.assertEqual(readiness.missing, ())
        self.assertTrue(all(state == "CONSISTENT" for _c, state, _d in readiness.checks))
        mapped = rr.map_points_to_fe(readiness, coordinates)
        self.assertLess(float(np.abs(mapped - truth).max()), 1e-9)  # every point on its true FE position
        self.assertFalse(readiness.frozen)
        self.assertFalse(readiness.mac_computed)
        self.assertFalse(rr.mac_permitted(readiness))  # complete evidence is not a frozen registration
        self.assertTrue(rr.mac_permitted(readiness, frozen_registration=object()))

    def test_the_link_statuses_never_depend_on_the_data(self):
        for angle in (45.0, 10.0, 80.0):
            with self.subTest(angle=angle):
                coordinates, _truth = synthetic_scan(angle)
                readiness = rr.evaluate(rr.real_261027_evidence(), coordinates)
                self.assertEqual((readiness.scan_to_plate.status, readiness.plate_to_fe.status),
                                 (rr.LINK_OPEN, rr.LINK_OPEN))
                self.assertIsNone(readiness.transform)
        self.assertNotIn("mac", rr.evaluate.__code__.co_varnames)


class RefusalTests(unittest.TestCase):
    def setUp(self):
        self.coordinates, _truth = synthetic_scan()

    def evaluate(self, **changes):
        return rr.evaluate(evidence(**changes), self.coordinates, "Z", (301.0, 300.0))

    def assert_missing(self, readiness, key, text=""):
        self.assertEqual(readiness.status, rr.REGISTRATION_NOT_VERIFIED)
        self.assertIsNone(readiness.transform)
        reasons = dict(readiness.missing)
        self.assertIn(key, reasons)
        self.assertIn(text, reasons[key])

    def test_an_unknown_scanned_face_is_refused(self):
        self.assert_missing(self.evaluate(scanned_face=F("scanned_face", None, rr.NOT_VERIFIED, "none")),
                            "scanned_face", "NOT_VERIFIED")
        self.assert_missing(self.evaluate(scanned_face=None), "scanned_face", "missing")

    def test_an_unknown_relation_of_fe_and_physical_edges_is_refused(self):
        readiness = self.evaluate(fe_origin_corner=F("fe_origin_corner", None, rr.CANDIDATE, "A–D"))
        self.assert_missing(readiness, "fe_origin_corner", "CANDIDATE")
        self.assertEqual(readiness.plate_to_fe.status, rr.LINK_OPEN)
        self.assertEqual(readiness.scan_to_plate.status, rr.LINK_VERIFIED)

    def test_a_convention_never_replaces_physical_evidence(self):
        convention = F("fe_origin_corner", (2, 3), rr.CONVENTION_ONLY, "picture D (M11 §16.2)")
        readiness = self.evaluate(fe_origin_corner=convention)
        self.assert_missing(readiness, "fe_origin_corner", "convention is not physical evidence")
        self.assertEqual(readiness.plate_to_fe.conventions, ("fe_origin_corner",))

    def test_a_derived_fact_counts_only_on_independent_facts(self):
        derived = F("scan_window_offsets_mm", {"-u": 20.0, "+u": 21.0, "-v": 10.0, "+v": 10.0}, rr.DERIVED,
                    "reconstruction", derived_from=("scan_scale",))
        self.assertEqual(self.evaluate(scan_window_offsets_mm=derived).status, rr.COMPLETE)
        weak = F("scan_window_offsets_mm", derived.value, rr.DERIVED, "reconstruction",
                 derived_from=("edge_guess",))
        readiness = self.evaluate(scan_window_offsets_mm=weak, edge_guess=F("edge_guess", 1, rr.CANDIDATE, "image"))
        self.assertEqual([key for key, _reason in readiness.missing], ["scan_window_offsets_mm"])
        self.assert_missing(readiness, "scan_window_offsets_mm", "DERIVED: not independent")

    def test_inconsistent_evidence_is_refused(self):
        mirror = self.evaluate(grid_plus_v_edge=F("grid_plus_v_edge", 1, rr.HUMAN_CONFIRMED, "x"))
        self.assert_missing(mirror, "handedness of the scan link", "mirror image")
        opposite = self.evaluate(grid_plus_v_edge=F("grid_plus_v_edge", 4, rr.HUMAN_CONFIRMED, "x"))
        self.assert_missing(opposite, "grid edges", "adjacent")
        normal = self.evaluate(fe_normal_face=F("fe_normal_face", "marked", rr.MEASURED, "x"))
        self.assert_missing(normal, "FE normal against the origin corner", "right-handed")
        window = self.evaluate(scan_window_offsets_mm=F("scan_window_offsets_mm",
                                                        {"-u": 20.0, "+u": 30.0, "-v": 10.0, "+v": 10.0},
                                                        rr.MEASURED, "x"))
        self.assert_missing(window, "scan window", "the plate")

    def test_an_in_plane_dof_and_another_plan_are_refused(self):
        readiness = rr.evaluate(evidence(), self.coordinates, "XZ", (301.0, 300.0))
        self.assert_missing(readiness, "measured DOF", "in-plane")
        readiness = rr.evaluate(evidence(), self.coordinates, "Z", (0.3, 0.3))
        self.assert_missing(readiness, "FE plan against the specimen")

    def test_a_wrong_scale_a_missing_metric_and_a_window_off_the_plate_are_refused(self):
        for scale in (0.0, -1000.0, float("nan"), None):
            with self.subTest(scale=scale):
                readiness = self.evaluate(scan_scale=F("scan_scale", {"mm_per_unit": scale}, rr.INSTRUMENT_RECORD,
                                                       "x"))
                self.assert_missing(readiness, "scan scale", "positive, finite")
        readiness = self.evaluate(scan_metric_geometry=F("scan_metric_geometry", "UNV grid", rr.CANDIDATE, "UNV"))
        self.assert_missing(readiness, "scan_metric_geometry", "CANDIDATE")
        outside = self.evaluate(scan_window_offsets_mm=F("scan_window_offsets_mm",
                                                         {"-u": 45.0, "+u": -4.0, "-v": 10.0, "+v": 10.0},
                                                         rr.MEASURED, "x"))
        self.assert_missing(outside, "scan window", "outside the plate")

    def test_every_offset_must_be_a_finite_non_negative_number(self):
        # FC1: a NaN offset passed the < 0 check and the closure comparison and gave EVIDENCE_COMPLETE (fail-open)
        good = {"-u": 20.0, "+u": 21.0, "-v": 10.0, "+v": 10.0}
        bad = (("NaN", float("nan"), "not finite"), ("+Infinity", float("inf"), "not finite"),
               ("-Infinity", float("-inf"), "not finite"), ("numpy NaN", np.float64("nan"), "not finite"),
               ("None", None, "missing"), ("string", "10.0", "not a number"), ("bool", True, "not a number"),
               ("list", [10.0], "not a number"), ("negative", -0.5, "negative"))
        for key in ("-u", "+u", "-v", "+v"):
            for label, value, text in bad + (("absent", ..., "missing"),):
                with self.subTest(key=key, value=label):
                    offsets = dict(good)
                    if value is ...:
                        offsets.pop(key)
                    else:
                        offsets[key] = value
                    readiness = self.evaluate(scan_window_offsets_mm=F("scan_window_offsets_mm", offsets,
                                                                       rr.MEASURED, "x"))
                    self.assert_missing(readiness, "scan window", text)
                    self.assertIn(key, dict(readiness.missing)["scan window"])
                    self.assertFalse(rr.mac_permitted(readiness, frozen_registration=object()))
        for value in (None, "20, 21, 10, 10", [20.0, 21.0, 10.0, 10.0]):
            with self.subTest(offsets=value):
                readiness = self.evaluate(scan_window_offsets_mm=F("scan_window_offsets_mm", value, rr.MEASURED, "x"))
                self.assert_missing(readiness, "scan window", "not a mapping")
        # positive controls: finite offsets of any real type keep the full positive path
        for offsets in (good, {"-u": 20, "+u": 21, "-v": 10, "+v": 10},
                        {k: np.float64(v) for k, v in good.items()}):
            with self.subTest(offsets=offsets):
                readiness = self.evaluate(scan_window_offsets_mm=F("scan_window_offsets_mm", offsets, rr.MEASURED,
                                                                   "x"))
                self.assertEqual(readiness.status, rr.COMPLETE, readiness.missing)
                self.assertIsNotNone(readiness.transform)

    def test_a_relative_fact_never_becomes_an_absolute_one(self):
        # the owner's "same face" carries the reference series' face over: a candidate stays a candidate
        same = F("same_face_as_261016", "same", rr.HUMAN_CONFIRMED, "owner")
        for reference, complete in ((F("scanned_face_261016", "unmarked", rr.CANDIDATE, "photograph"), False),
                                    (F("scanned_face_261016", "unmarked", rr.HUMAN_CONFIRMED, "owner"), True)):
            with self.subTest(reference=reference.provenance):
                face = F("scanned_face", "unmarked", rr.DERIVED, "same face",
                         derived_from=("same_face_as_261016", "scanned_face_261016"))
                readiness = self.evaluate(scanned_face=face, same_face_as_261016=same, scanned_face_261016=reference)
                self.assertEqual(readiness.status == rr.COMPLETE, complete, readiness.missing)
                if not complete:
                    self.assert_missing(readiness, "scanned_face", "rests on scanned_face_261016 (CANDIDATE)")
        alone = self.evaluate(scanned_face=F("scanned_face", "the same as before", rr.DERIVED, "owner",
                                             derived_from=("same_face_as_261016",)), same_face_as_261016=same)
        self.assert_missing(alone, "scanned face", "not a physical face")  # "same" names no face

    def test_test_conditions_are_never_registration_evidence(self):
        conditions = [F(f"condition_{i}", c.value, rr.HUMAN_CONFIRMED, c.source)
                      for i, c in enumerate(ps.EXPERIMENT_CONDITIONS)]
        base = rr.evaluate(rr.real_261027_evidence())
        more = rr.evaluate(list(rr.real_261027_evidence()) + conditions)
        self.assertEqual(more.missing, base.missing)
        self.assertEqual(more.status, rr.REGISTRATION_NOT_VERIFIED)

    def test_an_unknown_provenance_is_rejected(self):
        with self.assertRaises(ValueError):
            F("scanned_face", "marked", "PHOTO_GUESS", "x")


class RealSeriesTests(unittest.TestCase):
    def test_the_real_261027_series_stays_not_verified_and_invents_nothing(self):
        readiness = rr.evaluate(rr.real_261027_evidence())
        self.assertEqual(readiness.status, rr.REGISTRATION_NOT_VERIFIED)
        reasons = dict(readiness.missing)
        self.assertEqual(set(reasons), {"scanned_face", "grid_plus_v_edge", "scan_window_offsets_mm",
                                        "scan_metric_geometry", "fe_origin_corner", "fe_normal_face"})
        # every open fact names the candidate it rests on: the 261016 evidence is carried over, never raised
        self.assertIn("rests on scanned_face_261016 (CANDIDATE)", reasons["scanned_face"])
        self.assertIn("rests on scanned_face_261016 (CANDIDATE)", reasons["grid_plus_v_edge"])
        self.assertIn("rests on window_offsets_261016 (CANDIDATE)", reasons["scan_window_offsets_mm"])
        self.assertIn("rests on metric_reconstruction_261016 (CANDIDATE)", reasons["scan_metric_geometry"])
        facts = {fact.key: fact for fact in rr.real_261027_evidence()}
        for key in ("fe_origin_corner", "fe_normal_face"):
            self.assertIsNone(facts[key].value, key)  # no FE corner or face is invented
        self.assertEqual(facts["scanned_face_261016"].provenance, rr.CANDIDATE)  # SCANNER_FACE pending (M11 §15.3)
        self.assertEqual(facts["same_face_as_261016"].provenance, rr.HUMAN_CONFIRMED)
        self.assertEqual(facts["same_points_as_261016"].provenance, rr.HUMAN_CONFIRMED)
        self.assertEqual((facts["grid_plus_u_edge"].value, facts["grid_plus_u_edge"].provenance), (1, rr.DERIVED))
        self.assertNotIn("grid_plus_u_edge", reasons)  # derived from independent facts only
        self.assertNotIn("rotation_reference", reasons)
        self.assertEqual({key for key, *_rest in readiness.supporting} & {"same_face_as_261016",
                                                                         "point_map_261016_261027"},
                         {"same_face_as_261016", "point_map_261016_261027"})
        self.assertEqual(facts["scan_scale"].provenance, rr.INSTRUMENT_RECORD)
        self.assertEqual(facts["measured_dof"].provenance, rr.INSTRUMENT_RECORD)
        self.assertEqual(facts["fe_x_along_edges"].provenance, rr.HUMAN_CONFIRMED)
        self.assertFalse(rr.mac_permitted(readiness))
        notes = {item: provenance for item, _content, provenance in rr.INSTRUMENT_NOTES}
        self.assertEqual(notes["display triad"], rr.CONVENTION_ONLY)


class WorkbenchTests(unittest.TestCase):
    def test_the_chain_blocks_pairs_and_estimation_without_a_frozen_registration(self):
        real = pw.workbench_chain(True, rr.evaluate(rr.real_261027_evidence()))
        self.assertEqual([row[0] for row in real], ["Source UNV", "Physical specimen",
                                                    "Test conditions and scan orientation", "FE model",
                                                    "Registration", "Mode pairs", "Parameter estimation"])
        self.assertTrue(all(len(row) == len(pw.CHAIN_COLUMNS) == 6 for row in real))
        status = {row[0]: row[1] for row in real}
        self.assertEqual(status["Physical specimen"], ps.HUMAN_CONFIRMED)
        self.assertEqual(status["Registration"], rr.REGISTRATION_NOT_VERIFIED)
        self.assertEqual((status["Mode pairs"], status["Parameter estimation"]), (pw.BLOCKED, pw.BLOCKED))
        self.assertTrue(all(row[4] and row[5] for row in real))  # every link: blocking reason (or "—"), diagnostics
        conditions = next(row for row in real if row[0].startswith("Test conditions"))
        self.assertTrue(conditions[1].startswith(ps.HUMAN_CONFIRMED_SETUP_CHANGE))
        self.assertIn(rr.LINK_OPEN, conditions[1])  # the setup change never closes the scan link
        coordinates, _truth = synthetic_scan()
        complete = rr.evaluate(evidence(), coordinates, "Z", (301.0, 300.0))
        status = {row[0]: row[1] for row in pw.workbench_chain(True, complete)}
        self.assertEqual((status["Registration"], status["Mode pairs"]), (rr.COMPLETE, pw.BLOCKED))
        status = {row[0]: row[1] for row in pw.workbench_chain(True, complete, ("E1",), frozen_registration=object())}
        self.assertEqual((status["Registration"], status["Mode pairs"], status["Parameter estimation"]),
                         ("FROZEN", "1 CONFIRMED", ps.ITERATION_NOT_AUTHORISED))
        self.assertEqual(dict((r[0], r[1]) for r in pw.workbench_chain(False, complete))["Source UNV"],
                         "NOT_CONFIRMED")

    def test_the_10_percent_breakdown_turns_nothing_into_a_material_accuracy(self):
        rows = {row[0].split(" (")[0]: row for row in pw.target_breakdown(18.6307, 19.072)}
        self.assertEqual(rows["frequency error"][1:3], ("+2.37 %", "FREQUENCY_ONLY_DIAGNOSTIC"))
        self.assertIn("does not prove", rows["frequency error"][3])
        self.assertEqual(rows["experimental registration"][2], rr.REGISTRATION_NOT_VERIFIED)
        self.assertIn("two rubber bands", rows["suspension"][3])
        self.assertIn("not a material accuracy", rows["frequency error"][3])
        self.assertEqual(rows["shape identity"][2], "NOT_ESTABLISHED")
        self.assertEqual(rows["uncertainty of D"][2], "UNKNOWN")
        self.assertEqual(rows["uncertainty of E / G"][2], "UNKNOWN")
        self.assertEqual(rows["thickness"][1:3], ("24.5–24.9 % (3 × CV_edges)", "ILLUSTRATIVE"))
        self.assertEqual(rows["suspension"][2], "NOT_QUANTIFIED")
        self.assertEqual(rows["FE model choice"][2], "NOT_AVAILABLE")
        self.assertEqual(rows["±10 % target"][2], "NOT_ACHIEVED")

    def test_the_campaign_is_prepared_never_run_and_keeps_every_lock(self):
        spec = pw.campaign_specification()
        self.assertEqual(spec["status"], "PREPARED_NOT_AUTHORISED")
        self.assertIn("never a material constant", spec["result_kind"])  # a specimen calibration parameter
        self.assertIn(ps.NOT_A_MATERIAL_PROPERTY, spec["result_labels"])
        self.assertIn("do not replace them", spec["central_sensitivities"])
        stops = " ".join(spec["stop_and_refusal"])
        for lock in ("no frozen physical registration → no campaign", "D-044", "M8 GATE NOT_MET",
                     "D-077 NO_GLOBAL_PARAMETER_VALUE", "SPEC §6 S5"):
            self.assertIn(lock, stops)
        self.assertEqual([jobs for _p, jobs, _r, _c in pw.campaign_budget()], [4, 2, 4, 4, 12])
        self.assertEqual([jobs for _p, jobs, _r, _c in pw.campaign_budget(include_d12=True)], [4, 2, 6, 6, 12])
        variants = {v["variant"]: v for v in pw.APPLICABILITY_VARIANTS}
        self.assertEqual(list(variants), ["A", "B", "C", "D", "E"])
        self.assertIn("never a material identification from 33.4491 Hz", variants["C"]["purpose"])
        self.assertIn("never from 18.6307 or 33.4491 Hz", " ".join(variants["B"]["values"]["assumptions"]))
        jobs = pw.applicability_jobs()
        self.assertEqual(len(jobs), 6)
        for job in jobs:  # every future job is fully specified and not authorised
            for key in ("source_inp", "changed", "fixed", "expected_outputs", "fe_mode_identity", "stop",
                        "authorisation"):
                self.assertTrue(job[key], (job["job"], key))
            self.assertIn("not given", job["authorisation"])
            self.assertIn("no experimental MAC", job["fe_mode_identity"])
        template = pw.campaign_template()
        self.assertIsNone(template["authorisation"]["owner_decision"])
        self.assertIsNone(template["registration"]["frozen_registration_hash"])
        self.assertIsNone(template["fit_terms"])
        stored = json.loads((ROOT / "docs/research/plate_only/plate_campaign_template_rc1.json").read_text(
            encoding="utf-8"))
        self.assertEqual(stored, json.loads(json.dumps(template)))  # the committed template is the service's
        with self.assertRaises(ps.IterationNotAuthorised):
            ps.request_iteration()
        self.assertEqual({o.outcome for o in ps.plate_readiness(False).outcomes}, {ps.NOT_IDENTIFIABLE})

    def test_the_spectrum_is_a_png_of_two_independent_rows(self):
        image = pw.render_spectrum([18.63, 54.62], [19.07, 59.87], "Measured", "FE")
        self.assertTrue(image.startswith(b"\x89PNG"))


if __name__ == "__main__":
    unittest.main()
