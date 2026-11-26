"""PRIORITY-5A: the Research Results page and its reader (headless service / model; the page in Qt ``offscreen``).

- the archived snapshot gives 35 matching rows (11 / 12 / 12), the exact frequencies, S0 / H1 / H2 from the file,
  the published statuses unchanged and the sensitivity rank 3 / 1.83 and 2 / 2.35;
- a changed or damaged CSV refuses the snapshot; a damaged, mis-sized, non-finite, out-of-range or foreign local
  JSON record refuses the matrices; without a record the page still shows every table;
- no research / hypothetical MAC is shown as a confirmed MAC; SP-10 shows MAC NOT_AVAILABLE;
- the Workspace link is made only by SHA-256; otherwise the NOT VERIFIED banner is shown;
- opening the page starts no process (no Abaqus, solver or Auto-ID); the specimens and scenarios switch.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from services import research_results_reader as rr  # noqa: E402
from new_gui import research_results_model as rm  # noqa: E402


def synthetic_record(**changes) -> dict:
    """A structurally valid local research record (synthetic values), with ``changes`` applied."""
    record = {"experimental": {
        "PLATE": {"sha256": rr.SPECIMENS["PLATE"].experiment_sha256, "frequencies_hz": [18.6 + i for i in range(11)]},
        "SP13": {"sha256": rr.SPECIMENS["SP-13"].experiment_sha256, "frequencies_hz": [28.8 + i for i in range(12)]},
        "SP10": {"sha256": rr.SPECIMENS["SP-10"].experiment_sha256, "frequencies_hz": [26.5 + i for i in range(12)]}},
        "plate_research_mac": {"fe_modes": list(range(7, 21)), "matrix": [[0.1] * 14 for _ in range(11)]},
        "sp13_hypothetical_mac": {"fe_modes": list(range(7, 31)), "matrix": [[0.2] * 24 for _ in range(12)]}}
    record["plate_research_mac"]["matrix"][0][0] = 0.905
    for path, value in changes.items():
        target = record
        keys = path.split(".")
        for k in keys[:-1]:
            target = target[int(k)] if isinstance(target, list) else target[k]
        last = keys[-1]
        if isinstance(target, list):
            target[int(last)] = value
        else:
            target[last] = value
    return record


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = rr.load_snapshot()

    def test_every_mode_exact_frequencies_and_the_published_statuses(self):
        self.assertEqual({k: len(v) for k, v in self.snapshot.matching.items()},
                         {"PLATE": 11, "SP-13": 12, "SP-10": 12})
        self.assertEqual(sum(len(v) for v in self.snapshot.matching.values()), 35)
        plate, sp13, sp10 = (self.snapshot.matching[k] for k in ("PLATE", "SP-13", "SP-10"))
        self.assertEqual((plate[0].f_exp_hz, sp13[0].f_exp_hz, sp10[11].f_exp_hz), (18.6307, 28.8015, 266.8519))
        self.assertEqual(plate[0].status, "CANDIDATE_ONLY")
        self.assertEqual([r.status for r in plate].count("AMBIGUOUS_CLUSTER"), 5)
        self.assertEqual({r.status for r in sp10}, {"FE_SHAPES_UNAVAILABLE"})
        self.assertNotIn("MATCH_CONFIRMED", {r.status for rows in self.snapshot.matching.values() for r in rows})
        self.assertTrue(all(r.mac_admissible.startswith("NOT_PERMITTED") for rows in self.snapshot.matching.values()
                            for r in rows))
        self.assertTrue(all(r.research_mac.startswith("HYPOTHETICAL_SAME_POINTS") for r in sp13))
        shown = rm.matching_rows(self.snapshot, "PLATE")
        self.assertEqual([row[8] for row in shown], [r.status for r in plate])  # never renamed

    def test_sensitivities_rank_and_scenarios_from_the_files(self):
        self.assertEqual((self.snapshot.rank_full["rank"], round(self.snapshot.rank_full["condition"], 2)), (3, 1.83))
        self.assertEqual((self.snapshot.rank_restricted["rank"], round(self.snapshot.rank_restricted["condition"], 2)),
                         (2, 2.35))
        terms = {x.term: x for x in self.snapshot.sensitivities}
        self.assertGreater(terms["FE7"].s["G12"], 0.48)
        self.assertGreater(terms["FE13"].s["E1"], 0.49)
        self.assertGreater(terms["FE14"].s["E2"], 0.50)
        self.assertIsNone(terms["FE8"].s["E1"])  # lost identity: no value
        self.assertIn("FE15+FE16", terms)
        self.assertEqual([(s.key, s.E1, s.E2, s.G12) for s in self.snapshot.scenarios],
                         [("S0", 56000.0, 56000.0, 4763.4), ("H1", 43467.0, 43467.0, 4804.4),
                          ("H2", 41952.8, 41952.8, 4810.3)])
        h1 = rm.scenario_view(self.snapshot, "H1")
        self.assertEqual([d[0] for d in h1["declared"]], ["EXP1 ↔ FE7", "EXP8 ↔ FE15+FE16"])
        branch = next(b for b in h1["branches"] if b[0] == "FE15+FE16")
        self.assertEqual(branch[3], "158.01732")
        self.assertIn("geometric mean", branch[6])
        self.assertTrue(h1["centroid"])
        s0 = rm.scenario_view(self.snapshot, "S0")
        self.assertEqual(s0["declared"][0][2], "18.63088")

    def test_the_digest_does_not_depend_on_the_line_ends_of_the_checkout(self):
        with tempfile.TemporaryDirectory() as folder:
            for name, ending in (("lf", b"\n"), ("crlf", b"\r\n")):
                root = Path(folder) / name
                for relative, _sha, _commit in rr.SNAPSHOT_FILES.values():
                    (root / relative).parent.mkdir(parents=True, exist_ok=True)
                    text = (ROOT / relative).read_bytes().replace(b"\r\n", b"\n")
                    (root / relative).write_bytes(text.replace(b"\n", ending))
                self.assertEqual(len(rr.load_snapshot(root).matching["SP-10"]), 12, name)

    def test_a_changed_or_damaged_csv_refuses_the_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for _key, (relative, _sha, _c) in rr.SNAPSHOT_FILES.items():
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, root / relative)
            self.assertEqual(len(rr.load_snapshot(root).matching["PLATE"]), 11)
            target = root / rr.SNAPSHOT_FILES["PLATE_MATCHING"][0]
            target.write_text(target.read_text(encoding="utf-8").replace("CANDIDATE_ONLY", "MATCH_CONFIRMED"),
                              encoding="utf-8")
            with self.assertRaises(rr.SnapshotRefused) as refused:
                rr.load_snapshot(root)
            self.assertIn("SHA-256", str(refused.exception))
            target.unlink()
            with self.assertRaises(rr.SnapshotRefused):
                rr.load_snapshot(root)


class RecordTests(unittest.TestCase):
    def write(self, record) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "matching_record.json"
        path.write_text(record if isinstance(record, str) else json.dumps(record), encoding="utf-8")
        return path

    def test_a_valid_record_gives_the_matrices_with_its_sha(self):
        record = rr.load_local_record(self.write(synthetic_record()))
        self.assertEqual(len(record.sha256), 64)
        self.assertEqual((len(record.matrices["PLATE"].values), len(record.matrices["PLATE"].fe_modes)), (11, 14))
        self.assertNotIn("SP-10", record.matrices)
        view = rm.mac_view(record, "PLATE")
        self.assertEqual(view["state"], "matrix")
        self.assertIn("NOT a physical registration", view["text"])
        self.assertIn("not a confirmed MAC", rm.cell_text(record, "PLATE", 0, 0))
        self.assertIn("HYPOTHETICAL_SAME_POINTS", rm.cell_text(record, "SP-13", 0, 0))
        self.assertEqual(rm.mac_view(record, "SP-10")["text"], "MAC NOT_AVAILABLE — FE shapes not extracted")
        self.assertEqual(rm.mac_view(None, "PLATE")["state"], "no_record")

    def test_a_damaged_or_foreign_record_is_refused(self):
        cases = {"not JSON": "{oops", "no experimental section": {"a": 1},
                 "foreign source": synthetic_record(**{"experimental.PLATE.sha256": "0" * 64}),
                 "too few rows": synthetic_record(**{"plate_research_mac.matrix": [[0.1] * 14] * 10}),
                 "short row": synthetic_record(**{"plate_research_mac.matrix.3": [0.1] * 13}),
                 "out of range": synthetic_record(**{"plate_research_mac.matrix.0.1": 1.5}),
                 "not finite": synthetic_record(**{"plate_research_mac.matrix.0.1": "NaN"}),
                 "bad modes": synthetic_record(**{"sp13_hypothetical_mac.fe_modes": [7] * 24})}
        for name, record in cases.items():
            with self.subTest(case=name), self.assertRaises(rr.RecordRefused):
                text = json.dumps(record).replace('"NaN"', "NaN") if not isinstance(record, str) else record
                rr.load_local_record(self.write(text))


class WorkspaceLinkTests(unittest.TestCase):
    def test_the_link_needs_the_research_sha256(self):
        verified, text = rr.workspace_link("PLATE", None, None)
        self.assertFalse(verified)
        self.assertTrue(text.startswith("ARCHIVED RESEARCH SNAPSHOT — NOT VERIFIED FOR CURRENT WORKSPACE INPUTS"))
        spec = rr.SPECIMENS["PLATE"]
        self.assertFalse(rr.workspace_link("PLATE", {"sha256": spec.experiment_sha256}, {"sha256": "1" * 64})[0])
        self.assertTrue(rr.workspace_link("PLATE", {"sha256": spec.experiment_sha256},
                                          {"sha256": spec.fe_manifest_sha256})[0])

    def test_plate_and_sp13_are_verified_only_by_both_matching_sha256(self):
        for key in ("PLATE", "SP-13"):
            spec = rr.SPECIMENS[key]
            verified, text = rr.workspace_link(key, {"sha256": spec.experiment_sha256},
                                               {"sha256": spec.fe_manifest_sha256})
            self.assertTrue(verified, key)
            self.assertEqual(text, rr.VERIFIED_BANNER)
            for exp, fe in ((spec.experiment_sha256, None), ("3" * 64, spec.fe_manifest_sha256)):
                verified, text = rr.workspace_link(key, {"sha256": exp}, {"sha256": fe} if fe else None)
                self.assertFalse(verified, key)
                self.assertTrue(text.startswith(rr.NOT_VERIFIED_BANNER))

    def test_sp10_matching_experiment_without_fe_is_not_verified(self):
        spec = rr.SPECIMENS["SP-10"]
        verified, text = rr.workspace_link("SP-10", {"sha256": spec.experiment_sha256}, None)
        self.assertFalse(verified)
        self.assertTrue(text.startswith(rr.NOT_VERIFIED_BANNER + ": "))
        self.assertNotIn(rr.VERIFIED_BANNER, text)
        self.assertIn(f"the experimental SHA-256 matches the series' {spec.experiment_sha256[:12]}…", text)
        self.assertIn("the FE identity is not confirmed: SP-10 has no research FE package", text)

    def test_sp10_matching_experiment_with_another_fe_is_not_verified(self):
        spec = rr.SPECIMENS["SP-10"]
        verified, text = rr.workspace_link("SP-10", {"sha256": spec.experiment_sha256}, {"sha256": "4" * 64})
        self.assertFalse(verified)
        self.assertTrue(text.startswith(rr.NOT_VERIFIED_BANNER + ": "))
        self.assertIn("the experimental SHA-256 matches", text)
        self.assertIn("the FE identity is not confirmed", text)
        self.assertIn("the FE manifest read in the Workspace is 444444444444…", text)

    def test_sp10_other_experiment_is_not_verified(self):
        spec = rr.SPECIMENS["SP-10"]
        for fe in (None, {"sha256": "4" * 64}):
            verified, text = rr.workspace_link("SP-10", {"sha256": "5" * 64}, fe)
            self.assertFalse(verified)
            self.assertTrue(text.startswith(rr.NOT_VERIFIED_BANNER + ": "))
            self.assertIn(f"is 555555555555…, not the series' {spec.experiment_sha256[:12]}…", text)
            self.assertNotIn("matches", text)
            self.assertIn("the FE identity is not confirmed", text)


PLATE_JSON = ROOT / rr.PLATE_COMPARISON_FILE[0]
WORK = ROOT.parent / "abaqus-modal-comparator-work"


def plate_document() -> dict:
    return json.loads(PLATE_JSON.read_text(encoding="utf-8"))


def changed(document: dict, path: str, value) -> dict:
    """A copy of the snapshot document with one value replaced ('models.3.records.1.mac_first')."""
    out = json.loads(json.dumps(document))
    target = out
    keys = path.split(".")
    for k in keys[:-1]:
        target = target[int(k)] if isinstance(target, list) else target[k]
    if isinstance(target, list):
        target[int(keys[-1])] = value
    else:
        target[keys[-1]] = value
    return out


class PlateComparisonTests(unittest.TestCase):
    """PLATE-0875-CURRENT-RESEARCH-VIEW-01: the separate snapshot of the current plate research results."""

    def setUp(self):
        self.c = rr.load_plate_comparison()

    # ---- snapshot integrity
    def test_the_snapshot_is_read_only_with_its_recorded_sha256(self):
        self.assertEqual(self.c.sha256, rr.PLATE_COMPARISON_FILE[1])
        with tempfile.TemporaryDirectory() as folder:
            for name, ending in (("lf", b"\n"), ("crlf", b"\r\n")):
                target = Path(folder) / name / rr.PLATE_COMPARISON_FILE[0]
                target.parent.mkdir(parents=True)
                target.write_bytes(PLATE_JSON.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", ending))
                self.assertEqual(rr.load_plate_comparison(Path(folder) / name).sha256, self.c.sha256, name)
            target.write_bytes(PLATE_JSON.read_bytes().replace(b"-5.262375", b"-4.962375"))  # hides the failed ± 5 %
            with self.assertRaises(rr.PlateComparisonRefused) as refused:
                rr.load_plate_comparison(Path(folder) / "crlf")
            self.assertIn("SHA-256", str(refused.exception))
            target.write_bytes(b"{ not json")
            with self.assertRaises(rr.PlateComparisonRefused):
                rr.load_plate_comparison(Path(folder) / "crlf")
            target.unlink()
            with self.assertRaises(rr.PlateComparisonRefused) as refused:
                rr.load_plate_comparison(Path(folder) / "crlf")
            self.assertIn("missing", str(refused.exception))

    def test_the_committed_document_validates_and_is_the_loaded_one(self):
        again = rr.validate_plate_comparison(plate_document())
        self.assertEqual(again.models["COMBINED"].summary, self.c.models["COMBINED"].summary)
        self.assertEqual(again.exp_hz, self.c.exp_hz)

    # ---- source identity, and separation from registration evidence and identification inputs
    def test_source_identity(self):
        self.assertEqual(self.c.specimen["experiment_sha256"], rr.SPECIMENS["PLATE"].experiment_sha256)
        self.assertEqual(self.c.specimen["series"], rr.SPECIMENS["PLATE"].series)
        self.assertEqual([name for name, _p, _s in self.c.sources], list(rr.PLATE_COMPARISON_SOURCES))
        self.assertEqual(self.c.geometry["reconstruction_sha256"], self.c.sources[-1][2])
        self.assertEqual(self.c.models["BASELINE"].identity["fe_manifest_sha256"], rr.SPECIMENS["PLATE"].fe_manifest_sha256)
        self.assertEqual(len({m.identity["inp_sha256"] for m in self.c.models.values()}), 4)
        self.assertEqual(self.c.models["DIRECTIONAL_ONLY"].identity["inp_sha256"][:8], "bab9b7ed")  # README §25.1
        self.assertEqual(self.c.models["COMBINED"].identity["inp_sha256"][:8], "819de855")  # README §26.1
        self.assertEqual(self.c.models["THICKNESS_ONLY"].identity["inp_sha256"][:8], "dcb639f1")  # README §18
        self.assertEqual(self.c.models["BASELINE"].identity["inp_sha256"][:8], "962f75f2")

    def test_source_results_on_this_machine_have_the_recorded_sha256(self):
        import hashlib

        present = [(name, WORK.parent / path, sha) for name, path, sha in self.c.sources if (WORK.parent / path).is_file()]
        if not present:
            self.skipTest("the research work directories of README §24–§27 are not on this machine")
        for name, path, sha in present:
            with self.subTest(source=name):
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), sha)
        self.assertEqual(len(present), len(self.c.sources))

    def test_the_snapshot_is_separate_from_evidence_and_identification_inputs(self):
        import ast

        relative = rr.PLATE_COMPARISON_FILE[0]
        self.assertTrue(relative.startswith("docs/research/plate_only/"))
        self.assertNotIn(relative, [v[0] for v in rr.SNAPSHOT_FILES.values()])  # the historical snapshot is unchanged
        self.assertEqual(len(rr.SNAPSHOT_FILES), 8)
        self.assertIn("not registration evidence", self.c.status["use"])
        self.assertIn("not an identification input", self.c.status["use"])
        self.assertEqual(set(self.c.status["gates"]), {"M8 GATE NOT_MET", "D-077 NO_GLOBAL_PARAMETER_VALUE",
                                                       "production Auto-ID BLOCKED"})
        for label in ("RESEARCH_ONLY", "PHYSICAL_REGISTRATION_NOT_VERIFIED", "NOT_A_MATERIAL_PROPERTY"):
            self.assertIn(label, self.c.labels)
        text = json.dumps(plate_document())
        self.assertNotIn("MATCH_CONFIRMED\"", text.replace("MATCH_CONFIRMED is given nowhere", ""))
        tree = ast.parse((ROOT / "src" / "services" / "research_results_reader.py").read_text(encoding="utf-8"))
        imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module} | {
            a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        for forbidden in ("registration", "identification", "inverse", "auto_id", "pairing", "subprocess"):
            self.assertFalse([m for m in imported if forbidden in m], forbidden)
        users = [p.relative_to(ROOT).as_posix() for folder in ("src", "tools") for p in (ROOT / folder).rglob("*.py")
                 if "plate_comparison_261027" in p.read_text(encoding="utf-8", errors="replace")]
        self.assertEqual(users, ["src/services/research_results_reader.py"])  # no other program code reads it

    # ---- four models, 11 records
    def test_four_models_their_inputs_and_all_eleven_records(self):
        self.assertEqual(tuple(self.c.models), ("BASELINE", "THICKNESS_ONLY", "DIRECTIONAL_ONLY", "COMBINED"))
        inputs = {k: (m.inputs["E1_MPa"], m.inputs["E2_MPa"], m.inputs["G12_MPa"], tuple(m.inputs["thickness_mm_at_x0_x301"]))
                  for k, m in self.c.models.items()}
        self.assertEqual(inputs, {"BASELINE": (56000.0, 56000.0, 5000.0, (0.875, 0.875)),
                                  "THICKNESS_ONLY": (56000.0, 56000.0, 5000.0, (0.81, 0.93)),
                                  "DIRECTIONAL_ONLY": (56000.0, 41000.0, 5000.0, (0.875, 0.875)),
                                  "COMBINED": (56000.0, 41000.0, 5000.0, (0.81, 0.93))})
        self.assertEqual(len(self.c.exp_hz), 11)
        self.assertAlmostEqual(self.c.exp_hz[0], 18.6307, places=4)
        self.assertAlmostEqual(self.c.exp_hz[10], 191.6019, places=4)
        for key, m in self.c.models.items():
            with self.subTest(model=key):
                self.assertEqual([r.exp for r in m.records], list(range(1, 12)))
                self.assertEqual((len(m.mac), {len(row) for row in m.mac}, len(m.fe_hz)), (11, {14}, 14))
        self.assertEqual([round(self.c.models[k].summary["mean_mac_first"], 3) for k in rr.PLATE_MODELS],
                         [0.746, 0.802, 0.878, 0.917])  # README §26.4
        self.assertEqual([round(self.c.models[k].summary["mean_abs_frequency_error_pct"], 2) for k in rr.PLATE_MODELS],
                         [6.22, 5.92, 2.29, 2.73])
        self.assertEqual([self.c.models[k].summary["records_outside_5_pct"] for k in rr.PLATE_MODELS],
                         [[2, 4, 7, 8, 11], [2, 4, 7, 8, 11], [], [2]])
        combined = self.c.models["COMBINED"].records
        self.assertEqual([r.corresponding_fe for r in combined], list(range(7, 18)))
        self.assertEqual([round(r.mac_first, 2) for r in combined], [0.97, 0.99, 0.72, 0.58, 0.99, 0.98, 0.98, 0.96, 0.98,
                                                                     0.97, 0.95])
        self.assertAlmostEqual(combined[1].frequency_error_pct, -5.26, places=2)
        self.assertAlmostEqual(self.c.models["DIRECTIONAL_ONLY"].records[1].frequency_error_pct, -4.38, places=2)
        # what the page shows
        self.assertEqual(len(rm.plate_model_rows(self.c)), 4)
        self.assertEqual([row[3] for row in rm.plate_model_rows(self.c)], ["56000", "56000", "41000", "41000"])
        frequency = rm.plate_frequency_rows(self.c)
        self.assertEqual((len(frequency), {len(r) for r in frequency}), (11, {len(rm.PLATE_FREQUENCY_HEADERS)}))
        self.assertEqual(frequency[1][-2:], ("FE8  51.74", "-5.26"))
        self.assertEqual(len(rm.plate_mac_rows(self.c)), 11)
        self.assertEqual(len(rm.plate_summary_rows(self.c)), 7)
        self.assertEqual(rm.plate_summary_rows(self.c)[-1][1:], ("2, 4, 7, 8, 11", "2, 4, 7, 8, 11", "none", "2"))
        for key in rr.PLATE_MODELS:
            rows = rm.plate_record_rows(self.c, key)
            self.assertEqual((len(rows), {len(r) for r in rows}), (11, {len(rm.PLATE_RECORD_HEADERS)}), key)
            view = rm.plate_mac_view(self.c, key)
            self.assertEqual((len(view["rows"]), len(view["cols"])), (11, 14))
        self.assertIn("RESEARCH MAC 0.9899 — not a confirmed MAC", rm.plate_cell_text(self.c, "COMBINED", 1, 1))

    def test_corrected_scan_window_and_the_conditional_transfer(self):
        g = self.c.geometry
        self.assertEqual([round(v, 1) for v in g["window_mm"]], [287.1, 285.3])
        self.assertEqual([round(v, 1) for v in g["superseded"]["window_mm"]], [215.4, 285.2])
        self.assertEqual(g["pixel_normalisation"], "instrument-metadata")
        lines = " ".join(rm.plate_geometry_lines(self.c))
        self.assertIn("287.1 × 285.3 mm", lines)
        self.assertIn("CONDITIONAL", lines)
        self.assertIn("owner's statement", lines)
        self.assertIn("215.4 × 285.2 mm", lines)
        self.assertIn("CONVENTION_ONLY", lines)

    # ---- what must stay visible
    def test_unresolved_records_lost_branches_and_the_failed_criterion_are_kept(self):
        self.assertEqual(self.c.unresolved_records, (3, 4))
        b = self.c.criteria["combined_model_readme_26"]["B_all_class_frequencies_within_5_pct"]
        self.assertEqual((b["verdict"], b["records_outside"], b["correspondence_not_confirmed_by_tracking"]),
                         ("FAIL", [2], [7, 8]))
        self.assertEqual(self.c.tracking["lost"], [13, 14, 20])
        criteria = " ".join(rm.plate_criteria_lines(self.c))
        self.assertIn("within ± 5 %' (README §26): FAIL — outside: EXP2; largest |Δf| 5.26 %", criteria)
        self.assertIn("EXP3: 0.68 → 0.72 (NOT improved, NOT described)", criteria)
        self.assertIn("EXP4: 0.56 → 0.58 (NOT improved, NOT described)", criteria)
        self.assertIn("EXP7: 0.79 → 0.98 (improved, described)", criteria)
        self.assertIn("does NOT keep the frequency agreement", criteria)
        notes = {row[0]: row[-1] for row in rm.plate_mac_rows(self.c)}
        self.assertIn("UNRESOLVED", notes["EXP3"])
        self.assertIn("UNRESOLVED", notes["EXP4"])
        self.assertIn("outside ± 5 %", notes["EXP2"])
        self.assertIn("LOST in tracking", notes["EXP7"])
        self.assertIn("LOST in tracking", notes["EXP8"])
        combined = {row[0]: row[-1] for row in rm.plate_record_rows(self.c, "COMBINED")}
        self.assertIn("outside ± 5 %", combined["EXP2"])
        self.assertIn("correspondence by frequency position only", combined["EXP7"])
        tracking = rm.plate_tracking_rows(self.c)
        self.assertEqual(len(tracking), 14)
        self.assertEqual([row[0] for row in tracking if row[5].startswith("LOST")], ["FE13", "FE14", "FE20"])
        self.assertEqual(rm.plate_lost_rows(self.c), (6, 7, 13))
        limits = " ".join(rm.plate_limit_lines(self.c))
        for phrase in ("EXP 3 and EXP 4 are not explained", "FAILS - EXP 2 at -5.26 %", "FE 13 and FE 14", "LOST",
                       "PHYSICAL_REGISTRATION_NOT_VERIFIED", "No pairing status"):
            self.assertIn(phrase, limits)
        # EXP2 (row 1) is marked outside ± 5 % for baseline, thickness only and combined, not for directional only
        self.assertEqual(sorted(c for r, c in rm.plate_outside_cells(self.c) if r == 1), [3, 5, 9])
        self.assertEqual(sorted(r + 1 for r, c in rm.plate_low_cells(self.c) if c == 5), [3, 4])  # combined below 0.80

    # ---- refusal of invalid data
    def test_an_inconsistent_or_incomplete_document_is_refused(self):
        document = plate_document()
        nan = float("nan")
        cases = {
            "a model removed": {**document, "models": document["models"][:3]},
            "models reordered": {**document, "models": document["models"][::-1]},
            "ten records": changed(document, "models.3.records", document["models"][3]["records"][:10]),
            "ten experimental frequencies": changed(document, "experiment.hz", document["experiment"]["hz"][:10]),
            "a non-finite MAC": changed(document, "models.0.mac.0.0", nan),
            "a MAC above 1": changed(document, "models.0.mac.0.0", 1.2),
            "a short MAC row": changed(document, "models.1.mac.4", document["models"][1]["mac"][4][:13]),
            "a text frequency": changed(document, "models.2.fe_hz.3", "64.8"),
            "an error that does not follow": changed(document, "models.3.records.1.frequency_error_pct", -4.9),
            "a first-ranked mode that is not the matrix maximum": changed(document, "models.3.records.2.first_fe", 10),
            "a MAC that is not the matrix value": changed(document, "models.3.records.2.mac_corresponding", 0.95),
            "the failed ± 5 % hidden in the summary": changed(document, "models.3.summary.records_outside_5_pct", []),
            "the failed ± 5 % criterion called PASS": changed(
                document, "criteria.combined_model_readme_26.B_all_class_frequencies_within_5_pct.verdict", "PASS"),
            "the unresolved records dropped": changed(document, "unresolved_records", []),
            "a lost branch called tracked": changed(document, "tracking.rows.6.status", "TRACKED"),
            "the lost list shortened": changed(document, "tracking.lost", [20]),
            "the research labels dropped": changed(document, "labels", ["RESEARCH_ONLY"]),
            "another experimental file": changed(document, "specimen.experiment_sha256", "0" * 64),
            "the superseded geometry as basis": changed(document, "geometry.basis", "OLD_NOMINAL"),
            "an unconditional transfer": changed(document, "geometry.transfer_261016_to_261027", "the same points"),
            "a window that does not fit the plate": changed(document, "geometry.window_mm.0", 215.4),
            "used as evidence": changed(document, "status.use", "registration evidence"),
            "the gates dropped": changed(document, "status.gates", ["M8 GATE NOT_MET"]),
            "a source dropped": changed(document, "sources", document["sources"][:5]),
            "E2 above E1 in the directional model": changed(document, "models.2.inputs.E2_MPa", 60000.0),
            "a uniform thickness in the combined model": changed(document, "models.3.inputs.thickness_mm_at_x0_x301", [0.875, 0.875]),
            "no limitations": changed(document, "limitations", []),
            "another schema": changed(document, "schema", "auto-id/frozen-registration/v1"),
            "not an object": [document],
        }
        for name, bad in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(rr.PlateComparisonRefused):
                    rr.validate_plate_comparison(bad)

    # ---- historical results are named historical
    def test_historical_plate_results_are_marked(self):
        for text in (rr.HISTORICAL_PLATE_GEOMETRY, rm.PLATE_HISTORICAL_MATCHING, rm.PLATE_HISTORICAL_MAC,
                     rm.PLATE_HISTORICAL_INVERSE):
            self.assertTrue(text.startswith("HISTORICAL"), text[:40])
            self.assertIn("superseded", text.lower())
        self.assertIn("215.4 mm wide instead of 287.1 mm", rr.HISTORICAL_PLATE_GEOMETRY)
        self.assertIn("not a current result", rr.HISTORICAL_PLATE_GEOMETRY)
        self.assertIn("S0 / H1 / H2", rm.PLATE_HISTORICAL_INVERSE)
        self.assertIn("B. Historical", rm.PLATE_HISTORICAL_HEADING)
        self.assertIn("A. Current", rm.PLATE_CURRENT_TITLE)
        self.assertIn("not affected", rm.PLATE_SENSITIVITY_UNAFFECTED)
        snapshot = rr.load_snapshot()  # the archived tables themselves are unchanged
        self.assertEqual(snapshot.matching["PLATE"][0].status, "CANDIDATE_ONLY")
        self.assertIn("diagnostic reconstruction", rr.SPECIMENS["PLATE"].mac_basis)


try:
    from PySide6.QtWidgets import QApplication  # noqa: F401
    HAVE_QT = True
except ImportError:  # pragma: no cover - depends on the environment
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT or os.environ.get("NEW_GUI_REQUIRE_QT") == "1", "PySide6 is not installed")
class PageTests(unittest.TestCase):
    def setUp(self):
        from new_gui import window as wm

        self.wm = wm
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.record = Path(directory.name) / "matching_record.json"
        self.record.write_text(json.dumps(synthetic_record()), encoding="utf-8")
        patch = mock.patch.dict(os.environ, {"LOCALAPPDATA": directory.name})
        patch.start()
        self.addCleanup(patch.stop)
        self.app = QApplication.instance() or wm.create_application([])
        self.window = wm.MainWindow(ask_path=lambda kind, start: "")
        self.window.resize(1366, 768)
        self.window.show()
        self.addCleanup(self.window.close)
        self.page = self.window.research

    def test_the_page_opens_reads_only_and_starts_nothing(self):
        self.assertEqual(self.wm.PAGES[self.wm.RESEARCH_PAGE], "Research Results")
        self.assertIsNone(self.page.snapshot)  # nothing read at start-up
        with mock.patch("subprocess.Popen") as popen, mock.patch("subprocess.run") as run:
            self.window.nav.button(self.wm.RESEARCH_PAGE).click()
            self.app.processEvents()
            popen.assert_not_called()
            run.assert_not_called()
        self.assertEqual(self.page.specimen(), "PLATE")
        self.assertEqual(self.page.tables["matching"].rowCount(), 11)
        self.assertIn("NOT VERIFIED FOR CURRENT WORKSPACE INPUTS", self.page.banner.text())
        self.assertIn(rm.NO_RECORD, " ".join(w.text() for w in self.page.findChildren(type(self.page.banner))))
        self.assertIsNone(self.page.heatmap)  # without a record: no matrix, every table still shown
        self.assertEqual(self.page.tables["sensitivities"].rowCount(), 13)  # FE7–FE20, FE15+FE16 one term

    def test_specimens_scenarios_and_the_record(self):
        self.window.show_page(self.wm.RESEARCH_PAGE)
        self.assertTrue(self.page.load_record(str(self.record)))
        self.app.processEvents()
        self.assertEqual((self.page.heatmap.rowCount(), self.page.heatmap.columnCount()), (11, 14))
        self.assertTrue(self.page.mac_warning.isVisibleTo(self.window))
        self.page.heatmap.cellClicked.emit(0, 0)
        self.assertIn("RESEARCH MAC 0.9050 — not a confirmed MAC", self.page.cell.text())
        for key, declared in (("S0", 1), ("H1", 2), ("H2", 2)):
            self.page.set_scenario(key)
            self.app.processEvents()
            self.assertEqual(self.page.tables["declared"].rowCount(), declared, key)
            self.assertEqual(self.page.tables["branches"].rowCount(), 10, key)
        self.page.set_specimen("SP-13")
        self.app.processEvents()
        self.assertEqual(self.page.tables["matching"].rowCount(), 12)
        self.assertEqual(self.page.heatmap.columnCount(), 24)
        self.assertFalse(self.page.sens_card.isVisibleTo(self.window))
        self.page.set_specimen("SP-10")
        self.app.processEvents()
        self.assertEqual(self.page.tables["matching"].rowCount(), 12)
        self.assertIsNone(self.page.heatmap)
        self.assertFalse(self.page.load_button.isVisibleTo(self.window))
        texts = " ".join(w.text() for w in self.page.findChildren(type(self.page.banner)))
        self.assertIn("MAC NOT_AVAILABLE — FE shapes not extracted", texts)
        self.page.set_specimen("PLATE")
        self.assertFalse(self.page.load_record(str(self.record.with_name("absent.json"))))
        self.assertIsNone(self.page.heatmap)
        self.assertIn("The record is not used", self.page.record_error)

    def test_the_banner_follows_the_workspace_sha(self):
        self.window.show_page(self.wm.RESEARCH_PAGE)
        spec = rr.SPECIMENS["PLATE"]
        self.page.set_workspace({"sha256": spec.experiment_sha256}, {"sha256": spec.fe_manifest_sha256})
        self.assertTrue(self.page.banner.text().startswith(rr.VERIFIED_BANNER))
        self.page.set_workspace({"sha256": "2" * 64}, None)
        self.assertTrue(self.page.banner.text().startswith(rr.NOT_VERIFIED_BANNER))

    # ---- PLATE-0875-CURRENT-RESEARCH-VIEW-01
    def _labels(self, name):
        return [w for w in self.page.findChildren(type(self.page.banner)) if w.objectName() == name]

    def test_plate_shows_the_current_results_and_marks_the_historical_ones(self):
        with mock.patch("subprocess.Popen") as popen, mock.patch("subprocess.run") as run:
            self.window.show_page(self.wm.RESEARCH_PAGE)
            self.app.processEvents()
            popen.assert_not_called()
            run.assert_not_called()
        page = self.page
        self.assertIsNotNone(page.comparison)
        self.assertTrue(page.plate_card.isVisibleTo(self.window))
        self.assertEqual(page.plate_title.text(), rm.PLATE_CURRENT_TITLE)
        for label in ("RESEARCH_ONLY", "PHYSICAL_REGISTRATION_NOT_VERIFIED", "NOT_A_MATERIAL_PROPERTY"):
            self.assertIn(label, page.plate_status.text())
        self.assertEqual({k: page.tables[k].rowCount() for k in ("plate_models", "plate_summary", "plate_frequencies",
                                                                 "plate_mac", "plate_records", "plate_tracking")},
                         {"plate_models": 4, "plate_summary": 7, "plate_frequencies": 11, "plate_mac": 11,
                          "plate_records": 11, "plate_tracking": 14})
        self.assertEqual((page.plate_heatmap.rowCount(), page.plate_heatmap.columnCount()), (11, 14))
        self.assertIn("287.1 × 285.3 mm", self._labels("plateGeometry")[0].text())
        self.assertIn("CONDITIONAL", self._labels("plateGeometry")[0].text())
        self.assertIn("FAIL — outside: EXP2", self._labels("plateCriteria")[0].text())
        self.assertIn("EXP 3 and EXP 4 are not explained", self._labels("plateLimitations")[0].text())
        self.assertIn("not registration evidence", self._labels("plateCurrentNote")[0].text())
        # the four models, by their buttons; none is preferred at the start
        self.assertEqual(page.plate_model, "BASELINE")
        seen = {}
        for key in rr.PLATE_MODELS:
            page.plate_buttons[key].click()
            self.app.processEvents()
            self.assertEqual([k for k, b in page.plate_buttons.items() if b.isChecked()], [key])
            self.assertEqual(page.tables["plate_records"].rowCount(), 11)
            seen[key] = (self._labels("plateModelLine")[0].text(), page.tables["plate_records"].item(1, 4).text(),
                         page.plate_heatmap.item(1, 1).text())
        self.assertEqual({k: v[1:] for k, v in seen.items()},
                         {"BASELINE": ("+9.62", "0.45"), "THICKNESS_ONLY": ("+8.73", "0.54"),
                          "DIRECTIONAL_ONLY": ("-4.38", "0.97"), "COMBINED": ("-5.26", "0.99")})
        self.assertIn("E2 = 41000 MPa", seen["COMBINED"][0])
        self.assertIn("0.81 mm at X = 0", seen["COMBINED"][0])
        page.plate_heatmap.cellClicked.emit(1, 1)
        self.assertIn("Combined · EXP2", page.plate_cell.text())
        self.assertIn("not a confirmed MAC and not a pair", page.plate_cell.text())
        # the archived plate tables stay, named historical; the local record's matrix too
        self.assertEqual(page.tables["matching"].rowCount(), 11)
        for name in ("plateHistoricalMatching", "plateHistoricalMac", "plateHistoricalInverse"):
            labels = self._labels(name)
            self.assertEqual(len(labels), 1, name)
            self.assertTrue(labels[0].text().startswith("HISTORICAL"), name)
            self.assertTrue(labels[0].isVisibleTo(self.window), name)
        self.assertTrue(page.load_record(str(self.record)))
        self.app.processEvents()
        self.assertIsNotNone(page.heatmap)  # the historical local matrix, still below its HISTORICAL note
        self.assertEqual(len(self._labels("plateHistoricalMac")), 1)
        self.assertIsNotNone(page.plate_heatmap)
        self.assertIsNot(page.heatmap, page.plate_heatmap)
        # other specimens: no plate card, no plate markers
        for other in ("SP-13", "SP-10"):
            page.set_specimen(other)
            self.app.processEvents()
            self.assertFalse(page.plate_card.isVisibleTo(self.window), other)
            self.assertNotIn("plate_records", page.tables)
            self.assertEqual([n for n in ("plateHistoricalMatching", "plateHistoricalMac", "plateHistoricalInverse")
                              if self._labels(n)], [], other)
        page.set_specimen("PLATE")
        self.app.processEvents()
        self.assertEqual(page.tables["plate_frequencies"].rowCount(), 11)

    def test_a_changed_plate_snapshot_is_refused_and_nothing_replaces_it(self):
        from new_gui.research_results_panel import ResearchResultsPanel

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for relative in [v[0] for v in rr.SNAPSHOT_FILES.values()] + [rr.PLATE_COMPARISON_FILE[0]]:
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, root / relative)
            target = root / rr.PLATE_COMPARISON_FILE[0]
            target.write_bytes(target.read_bytes().replace(b'"FAIL"', b'"PASS"'))
            panel = ResearchResultsPanel(root=root)
            self.addCleanup(panel.deleteLater)
            panel.load()
            self.app.processEvents()
            self.assertIsNone(panel.comparison)
            self.assertIn("is not shown", panel.comparison_error)
            self.assertIn("SHA-256", panel.comparison_error)
            refused = [w for w in panel.findChildren(type(panel.banner)) if w.objectName() == "plateCurrentRefused"]
            self.assertEqual(len(refused), 1)
            for key in ("plate_models", "plate_frequencies", "plate_mac", "plate_records", "plate_tracking"):
                self.assertNotIn(key, panel.tables)
            self.assertIsNone(panel.plate_heatmap)
            self.assertEqual(panel.tables["matching"].rowCount(), 11)  # the historical tables are still shown, as such
            self.assertTrue([w for w in panel.findChildren(type(panel.banner)) if w.objectName() == "plateHistoricalMatching"])


if __name__ == "__main__":
    unittest.main()
