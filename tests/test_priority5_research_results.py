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
        self.assertTrue(rr.workspace_link("SP-10", {"sha256": rr.SPECIMENS["SP-10"].experiment_sha256}, None)[0])


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


if __name__ == "__main__":
    unittest.main()
