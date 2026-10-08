"""M7 RUN_A HUMAN gate 1: the archived SP-02 CARBON-5A ODB extraction record (manifest e4ba607f…; no Abaqus here).

Checks the governed record against the reuse plan, the governed SP-02 baseline pack and the accepted
CARBON-5A sensitivities.  With the run store configured (``AUTO_ID_FIXTURE_ROOT_M7_RUN_A`` = the RUN_A run
root) the journalled packs are re-verified and re-tracked.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.campaign_definition import load_archive_reuse, load_campaign_definition
from domain.experiment_fixture import fixture_roots_from_environment
from services.fe_shape_pack import load_shape_pack_record


CAMPAIGNS = ROOT / "docs" / "auto_id" / "campaigns"
RECORD = CAMPAIGNS / "M7_RUN_A.archive-extraction.json"
MANIFEST_HASH = "e4ba607f06a69311b4d7adab089b5b8fdbbf98aae9d2da0837849e6c5da5bde6"
PACKS = {"SP02_84753f636064e192": "81a5a8ccdc1c846a4a79ec8ef87721b25ac82f0d0f6270cc791d16e4e2080751",
         "SP02_13363f977809dbff": "7ac24b6b2c5738c5ea8501779eaa34461e718e5628fd5fac6bd861b262cf7792"}


class ExtractionRecordTests(unittest.TestCase):
    def setUp(self):
        self.record = json.loads(RECORD.read_text(encoding="utf-8"))
        definition = load_campaign_definition(CAMPAIGNS / "M7_RUN_A.campaign.json")
        self.reuse = load_archive_reuse(ROOT / definition.archive_reuse, definition.parameterisation_id)
        self.baseline = load_shape_pack_record(ROOT / "docs/auto_id/fe_shapes/SP02_f3e592281bebce66.shape-pack.json")

    def test_scope_is_exactly_gate_1(self):
        record = self.record
        self.assertEqual((record["authorised_manifest_hash"], record["manifest_hash_after_extraction"]),
                         (MANIFEST_HASH, MANIFEST_HASH))
        self.assertEqual((record["abaqus_solves"], record["abaqus_python_extractions"]), (0, 2))
        self.assertEqual(set(record["extractions"]), set(PACKS))
        self.assertTrue(all(record["validation"].values()))

    def test_packs_match_the_reuse_plan_and_the_baseline(self):
        plan = {o.job_name: o for o in self.reuse.odbs}
        for job, content in PACKS.items():
            entry, item = plan[job], self.record["extractions"][job]
            pack = load_shape_pack_record(CAMPAIGNS / "archive_extraction" / f"{job}.shape-pack.json")
            with self.subTest(job=job):
                self.assertEqual(item["archived_odb"]["sha256"], entry.odb_sha256)
                self.assertNotIn("E_MINUS_SP02/", item["archived_odb"]["relative_path"])
                self.assertEqual((pack.content_sha256, item["pack"]["content_sha256"]), (content, content))
                self.assertEqual(pack.generated_inp_sha256, entry.generated_inp_sha256)
                self.assertEqual(pack.frequencies_hz, entry.expected_frequencies_hz)
                self.assertEqual(pack.mode_numbers, tuple(range(7, 31)))
                self.assertEqual((pack.node_set_sha256, pack.node_set_count, pack.fe_geometry_sha256),
                                 (self.baseline.node_set_sha256, self.baseline.node_set_count,
                                  self.baseline.fe_geometry_sha256))
                self.assertEqual({r: t["tracked_fe_mode"] for r, t in item["tracking"].items()},
                                 {"R1": 8, "R2": 10, "R3": 13})
                self.assertTrue(all(t["mac"] >= 0.90 for t in item["tracking"].values()))

    def test_sensitivities_equal_the_accepted_carbon5a_values(self):
        accepted = json.loads((ROOT / "docs/auto_id/registration_evidence/SP02_registration_reevaluation.json")
                              .read_text(encoding="utf-8"))["results"]["PHYSICAL"]["sensitivities_carbon5a"]
        for row, value in self.record["s_e_from_extracted_packs"].items():
            with self.subTest(row=row):
                self.assertTrue(math.isclose(value, accepted[row]["S_E"], rel_tol=1e-9))


class RunStoreTests(unittest.TestCase):
    def test_journalled_packs_reverify_and_retrack(self):
        roots = fixture_roots_from_environment()
        missing = sorted({"m7-run-a", "carbon-project-archive"} - set(roots))
        if missing:
            self.skipTest(f"data stores {missing} not configured")
        from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING
        from services.branch_tracker import track_branches
        from services.fe_shape_pack import load_shape_pack, load_shape_pack_file
        from services.identification_campaign_run import journalled_archive_records
        from services.identification_pipeline import fe_state_from_pack

        run_root = Path(roots["m7-run-a"])
        definition = load_campaign_definition(CAMPAIGNS / "M7_RUN_A.campaign.json")
        reuse = load_archive_reuse(ROOT / definition.archive_reuse, definition.parameterisation_id)
        records = journalled_archive_records(reuse, run_root, MANIFEST_HASH)
        baseline = fe_state_from_pack(load_shape_pack(load_shape_pack_record(
            ROOT / "docs/auto_id/fe_shapes/SP02_f3e592281bebce66.shape-pack.json"), roots))
        for job, record in records.items():
            pack = load_shape_pack_file(run_root / "archive_reuse" / "packs" / record.pack.file_name, record)
            tracking = track_branches(STRICT_IDENTIFICATION_PAIRING, baseline, fe_state_from_pack(pack),
                                      {"R1": 8, "R2": 10, "R3": 13})
            with self.subTest(job=job):
                self.assertEqual(record.content_sha256, PACKS[job])
                self.assertEqual({b.row_id: b.candidate_mode for b in tracking.branches},
                                 {"R1": 8, "R2": 10, "R3": 13})


if __name__ == "__main__":
    unittest.main()
