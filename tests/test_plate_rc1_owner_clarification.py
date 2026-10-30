"""PLATE-WORKBENCH-RC1 final correction: the owner's clarification of the test conditions (2026-10-30).

- 261016: four rubber bands, the original position, 33.4491 Hz, HISTORY_ONLY (never a fitting target);
- 261027: two rubber bands, turned 45°, the same plate, the same physical points and the same measured face,
  18.6307 Hz, the primary experiment for the free-free M11 model;
- every fact keeps its provenance: the owner (HUMAN_CONFIRMED), the laboratory note (LAB_RECORD), the instrument or a
  derivation; the setup change and the owner's explanation never become a quantified effect, a mode identity, a
  Σ_setup repeat or registration evidence;
- the link of the two scans comes from their instrument geometry only: SAME_PHYSICAL_POINTS_HUMAN_CONFIRMED is kept
  apart from the point-to-point map (DERIVED, never INSTRUMENT_VERIFIED without both sessions' instrument records);
  mirrored or relabelled ids refuse the map;
- no scientific gate, normative document or frozen registration is touched (M8 NOT_MET, D-077, production Auto-ID
  blocked; no plate module writes a registration; no new install_* layer).
"""

from __future__ import annotations

import math
from pathlib import Path
import re
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from services import plate_registration_readiness as rr  # noqa: E402
from services import plate_study as ps  # noqa: E402
from services import plate_workbench as pw  # noqa: E402

F = rr.Fact
SNADWICH = Path(r"D:\Snadwich\New  EXP results\SPname_files_ROTATED_261028")
REFERENCE = ps.WORK_ROOT / "external_models" / "v3_20261021" / "Plate" / "snadwich_Plate"


def grid(angle_deg: float, ids=None, centre=(0.0, 0.0), pitch=0.017, n=17):
    """A regular n × n grid turned by ``angle_deg`` about +Z (ids row by row unless given)."""
    i, j = np.meshgrid(np.arange(n), np.arange(n))
    local = np.column_stack([i.ravel(), j.ravel()]) * pitch
    local -= local.mean(axis=0)
    a = math.radians(angle_deg)
    rotation = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    xy = local @ rotation.T + np.array(centre)
    return (np.arange(1, n * n + 1) if ids is None else np.asarray(ids)), np.column_stack([xy, np.full(n * n, -1.15)])


def read_unv_nodes(path: Path) -> tuple:
    """(ids, coordinates) of the first dataset 2411 of a UNV file (read only)."""
    lines = path.read_text(errors="replace").splitlines()
    for k, line in enumerate(lines):
        if line.strip() == "-1" and k + 1 < len(lines) and lines[k + 1].strip() == "2411":
            ids, xyz, m = [], [], k + 2
            while lines[m].strip() != "-1":
                ids.append(int(lines[m].split()[0]))
                xyz.append([float(v) for v in lines[m + 1].replace("D", "E").split()[:3]])
                m += 2
            return np.array(ids), np.array(xyz)
    raise ValueError(f"no dataset 2411 in {path}")


class ConditionsTests(unittest.TestCase):
    def test_the_owner_clarified_conditions_of_both_series(self):
        old, new = ps.conditions("261016"), ps.conditions("261027")
        self.assertEqual(old["suspension"].value, "four rubber bands")
        self.assertEqual(new["suspension"].value, "two rubber bands")
        self.assertEqual(new["orientation"].value, "turned 45° from the 261016 position")
        self.assertIn("original position", old["orientation"].value)
        self.assertEqual(new["direction of the turn"].value, "clockwise as viewed from the Polytec system")
        for item, status in (("specimen", ""), ("measured points", ps.SAME_POINTS), ("measured face", ps.SAME_FACE),
                             ("setup change", ps.HUMAN_CONFIRMED_SETUP_CHANGE)):
            for series in (old, new):  # common to both series
                self.assertEqual(series[item].series, "both")
                self.assertEqual(series[item].status, status)
        self.assertIn("same physical plate", old["specimen"].value)
        self.assertIn("which face is not stated", new["measured face"].value)
        self.assertEqual((old["role"].status, new["role"].status), (ps.HISTORY_ONLY, ps.PRIMARY_EXPERIMENT))
        self.assertIn("never a fitting target", old["role"].value)
        self.assertTrue(old["first record"].value.startswith("33.4491 Hz"))
        self.assertTrue(new["first record"].value.startswith("18.6307 Hz"))
        self.assertIn("four rubber bands", ps.TEST_261016)
        self.assertIn("two rubber bands", ps.TEST_261027["suspension"])
        self.assertIn("the same suspension in both series) was wrong", ps.CONDITIONS_CORRECTION)

    def test_the_historical_frequency_is_never_a_target(self):
        target = {row[0].split(" (")[0]: row for row in pw.target_breakdown(18.6307, 19.072)}
        self.assertEqual(target["frequency error"][1], "+2.37 %")  # 261027 record 1 against FE 7, not 33.4491 Hz
        self.assertNotIn("33.4491", " ".join(str(v) for row in target.values() for v in row))
        self.assertEqual(ps.classify_source(rr.SERIES_LINK_INPUTS["reference_polymax"][1]), ps.HISTORY)
        variants = {v["variant"]: v for v in pw.APPLICABILITY_VARIANTS}
        self.assertEqual(variants["C"]["role"], "boundary-condition history")
        spec = pw.campaign_specification()
        self.assertEqual(spec["status"], "PREPARED_NOT_AUTHORISED")
        self.assertEqual({o.outcome for o in ps.plate_readiness(False).outcomes}, {ps.NOT_IDENTIFIABLE})

    def test_the_explanation_stays_an_explanation(self):
        explanation = ps.conditions("261027")["why the first frequency is lower"]
        self.assertEqual(explanation.status, ps.OWNER_EXPLANATION)
        self.assertIn("numerical share is not determined", explanation.value)
        not_established = " ".join(ps.NOT_ESTABLISHED_BY_THE_CONDITIONS)
        for text in ("separate numerical contributions of the suspension and of the 45° turn",
                     "are the same elastic mode", "not a quantitative measure of the suspension",
                     "Σ_setup repeat", "261016 experiment was wrong", "relative fact",
                     "never registration evidence"):
            self.assertIn(text, not_established)
        cause = {c.aspect: c for c in ps.fe_applicability(ps.PLATE_FE_FAMILY[0], (301.0, 300.0), 18.6307, 19.072)}
        self.assertEqual(cause["series difference: mode identity"].state, ps.MODE_IDENTITY_NOT_VERIFIED)
        self.assertEqual(cause["mode correspondence"].state, "NOT_ESTABLISHED")


class ProvenanceTests(unittest.TestCase):
    def test_every_condition_keeps_its_own_provenance(self):
        for fact in ps.EXPERIMENT_CONDITIONS:
            self.assertIn(fact.provenance, (ps.HUMAN_CONFIRMED, ps.LAB_RECORD, ps.INSTRUMENT_RECORD, ps.DERIVED),
                          fact.item)
            if fact.provenance == ps.HUMAN_CONFIRMED:
                self.assertIn("owner", fact.source, fact.item)
            if fact.provenance == ps.LAB_RECORD:  # the laboratory note never passes for the owner
                self.assertIn("Read me.txt", fact.source, fact.item)
                self.assertNotIn("owner", fact.source, fact.item)
        new = ps.conditions("261027")
        self.assertEqual(new["suspension"].source, ps.OWNER_2026_10_30)
        self.assertEqual(new["suspension detail"].provenance, ps.LAB_RECORD)
        self.assertEqual(new["turn of the scan grid"].provenance, ps.DERIVED)
        self.assertEqual(ps.READ_ME[1], "4c03624a7591f71bb59189c2bb96a146d6eddcf89904ed5ae58781762047723e")

    def test_a_convention_or_a_relative_fact_never_closes_the_registration(self):
        readiness = rr.evaluate(rr.real_261027_evidence())
        self.assertEqual(readiness.status, rr.REGISTRATION_NOT_VERIFIED)
        convention = [F("fe_origin_corner", (2, 3), rr.CONVENTION_ONLY, "picture D (M11 §16.2)")
                      if f.key == "fe_origin_corner" else f for f in rr.real_261027_evidence()]
        refused = dict(rr.evaluate(convention).missing)
        self.assertIn("convention is not physical evidence", refused["fe_origin_corner"])
        self.assertIn("rests on scanned_face_261016 (CANDIDATE)", dict(readiness.missing)["scanned_face"])
        self.assertFalse(rr.mac_permitted(readiness))
        self.assertFalse(readiness.frozen)


class SeriesLinkTests(unittest.TestCase):
    same = F("same_points", "same", rr.HUMAN_CONFIRMED, "owner")

    def test_a_turned_grid_with_kept_ids_is_a_derived_map(self):
        ref_ids, ref = grid(89.6)  # as in 261016: the grid +u nearly along the scan +y
        ids, cur = grid(89.6 - 45.0)  # turned 45° clockwise seen from +Z, ids kept
        link = rr.series_link(ref_ids, ref, ids, cur, self.same)
        self.assertEqual((link.status, link.same_points, link.symmetry, link.proper),
                         (rr.MAPPING_DERIVED, rr.SAME_POINTS_HUMAN, "identity", True))
        self.assertEqual(link.ids_preserved, 289)
        self.assertAlmostEqual(link.turn_deg, -45.0, places=2)
        self.assertTrue(link.sense.startswith("clockwise"))
        ccw = rr.series_link(ref_ids, ref, *grid(89.6 + 45.0), self.same)
        self.assertTrue(ccw.sense.startswith("counter-clockwise"))
        self.assertAlmostEqual(ccw.turn_deg, 45.0, places=2)
        verified = rr.series_link(ref_ids, ref, ids, cur, self.same, instrument_records_of_both=True)
        self.assertEqual(verified.status, rr.MAPPING_INSTRUMENT_VERIFIED)

    def test_the_owner_statement_and_the_map_are_kept_apart(self):
        ref_ids, ref = grid(0.0)
        ids, cur = grid(-45.0)
        link = rr.series_link(ref_ids, ref, ids, cur, None)
        self.assertEqual((link.status, link.same_points), (rr.MAPPING_REFUSED, "NOT_VERIFIED"))
        link = rr.series_link(ref_ids, ref, ids, cur, F("same_points", "same", rr.CANDIDATE, "guess"))
        self.assertEqual(link.status, rr.MAPPING_REFUSED)

    def test_mirrored_or_relabelled_ids_refuse_the_map(self):
        ref_ids, ref = grid(0.0)
        n = 17
        mirrored = np.arange(1, n * n + 1).reshape(n, n)[:, ::-1].ravel()  # the ids of a mirror image
        link = rr.series_link(ref_ids, ref, mirrored, ref, self.same,
                              F("same_face", "same", rr.HUMAN_CONFIRMED, "owner"))
        self.assertEqual((link.status, link.proper), (rr.MAPPING_REFUSED, False))
        self.assertIn("mirror images", " ".join(link.reasons))
        shuffled = np.random.default_rng(1).permutation(ref_ids)
        link = rr.series_link(ref_ids, ref, shuffled, ref, self.same)
        self.assertEqual((link.status, link.symmetry), (rr.MAPPING_REFUSED, None))
        self.assertIn("not a reason to call it another specimen", " ".join(link.reasons))
        fewer = rr.series_link(ref_ids, ref, ref_ids[:-1], ref[:-1], self.same)
        self.assertIn("id sets differ", " ".join(fewer.reasons))

    def test_the_recorded_link_of_the_real_scans(self):
        link = rr.SERIES_LINK_261016_261027
        self.assertEqual((link["status"], link["same_points"], link["symmetry"]),
                         (rr.MAPPING_DERIVED, rr.SAME_POINTS_HUMAN, "identity"))
        self.assertLess(link["turn_deg"], 0)  # clockwise as viewed from the Polytec, as the laboratory note says
        self.assertEqual(rr.SERIES_LINK_INPUTS["series"][1], ps.WORKING_SOURCE_SHA256)
        self.assertIn("not a physical scale", " ".join(rr.SERIES_LINK_NOTES))

    @unittest.skipUnless((SNADWICH / rr.SERIES_LINK_INPUTS["series"][0]).is_file()
                         and (REFERENCE / rr.SERIES_LINK_INPUTS["reference"][0]).is_file(),
                         "the real 261016 / 261027 UNV files are not on this machine")
    def test_the_recorded_link_is_reproduced_from_the_files(self):
        import hashlib

        paths = {"reference": REFERENCE / rr.SERIES_LINK_INPUTS["reference"][0],
                 "series": SNADWICH / rr.SERIES_LINK_INPUTS["series"][0]}
        for key, path in paths.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), rr.SERIES_LINK_INPUTS[key][1])
        ref_ids, ref = read_unv_nodes(paths["reference"])
        ids, cur = read_unv_nodes(paths["series"])
        link = rr.series_link(ref_ids, ref, ids, cur, self.same, F("same_face", "same", rr.HUMAN_CONFIRMED, "owner"))
        recorded = rr.SERIES_LINK_261016_261027
        for key in ("status", "symmetry", "proper", "ids_preserved", "points", "turn_deg", "sense",
                    "representation_scale"):
            self.assertEqual(getattr(link, key), recorded[key], key)


class GovernanceTests(unittest.TestCase):
    def test_no_scientific_gate_or_normative_decision_is_touched(self):
        status = (ROOT / "docs/auto_id/STATUS.json").read_text(encoding="utf-8")
        decisions = (ROOT / "docs/auto_id/DECISIONS.md").read_text(encoding="utf-8")
        self.assertRegex(status, r"NOT_MET")
        self.assertIn("NO_GLOBAL_PARAMETER_VALUE", decisions)
        self.assertIn("D-077", decisions)
        self.assertEqual(ps.ITERATION_GATE.status, ps.ITERATION_NOT_AUTHORISED)
        with self.assertRaises(ps.IterationNotAuthorised):
            ps.request_iteration()
        spec = pw.campaign_specification()
        self.assertIn(ps.NOT_A_MATERIAL_PROPERTY, spec["result_labels"])  # a specimen calibration, not a material
        self.assertIn("never a material constant", spec["result_kind"])
        stops = " ".join(spec["stop_and_refusal"])
        for lock in ("M8 GATE NOT_MET", "D-077 NO_GLOBAL_PARAMETER_VALUE", "D-044"):
            self.assertIn(lock, stops)

    def test_the_plate_modules_never_write_a_registration_or_install_a_layer(self):
        for module in ("services/plate_study.py", "services/plate_registration_readiness.py",
                       "services/plate_workbench.py", "new_gui/plate_study_model.py", "new_gui/plate_study_panel.py"):
            text = (ROOT / "src" / module).read_text(encoding="utf-8")
            self.assertNotIn("docs/registrations", text.replace("\\", "/"), module)
            self.assertIsNone(re.search(r"\bFrozenRegistration\s*\(", text), module)
            self.assertIsNone(re.search(r"^def install_", text, re.MULTILINE), module)
        main = (ROOT / "src/main.py").read_text(encoding="utf-8")
        self.assertNotIn("plate_", " ".join(re.findall(r"install_\w+", main)))


if __name__ == "__main__":
    unittest.main()
