"""M7 RUN_B HUMAN gate 1: the archived SP-02 CARBON-5A G12 ODB extraction record (manifest 5fd0946a…; no Abaqus here).

Checks the governed record against the RUN_B reuse plan, the governed SP-02 baseline pack and the accepted
CARBON-5A G12 sensitivities.  With the run store configured (``AUTO_ID_FIXTURE_ROOT_M7_RUN_B`` = the RUN_B run
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

from domain.campaign_definition import RUN_B_LABEL, load_archive_reuse, load_campaign_definition
from domain.experiment_fixture import fixture_roots_from_environment
from services.fe_shape_pack import load_shape_pack_record


CAMPAIGNS = ROOT / "docs" / "auto_id" / "campaigns"
RECORD = CAMPAIGNS / "M7_RUN_B.archive-extraction.json"
MANIFEST_HASH = "5fd0946a0c3f4e20562ba97068cdb5b94bf6d10ba789a3b2df20b457882034a1"
RUN_IDENTITY = "fb5234116c6e9413e4b070e901f97b8c6e210d535daefe15f0cdb5b9f8ad87f0"
PACKS = {"SP02_05239a3b56508244": "f7271ea4674966604b696a6807972bcbe974f6a4955d0e3c1d6ea8304a297c3b",
         "SP02_ade5dffa2fde3903": "45660e24a50ec77d5b6e634b50fbcafd3348c4860f144dcdd182e1ce9e7249ce"}
G12 = {"SP02_05239a3b56508244": 4725.0, "SP02_ade5dffa2fde3903": 4275.0}


class ExtractionRecordTests(unittest.TestCase):
    def setUp(self):
        self.record = json.loads(RECORD.read_text(encoding="utf-8"))
        definition = load_campaign_definition(CAMPAIGNS / "M7_RUN_B.campaign.json")
        self.reuse = load_archive_reuse(ROOT / definition.archive_reuse, definition.parameterisation_id)
        self.baseline = load_shape_pack_record(ROOT / "docs/auto_id/fe_shapes/SP02_f3e592281bebce66.shape-pack.json")

    def test_scope_is_exactly_gate_1(self):
        record = self.record
        self.assertEqual((record["run_type"], record["label"]), ("RUN_B", RUN_B_LABEL))
        self.assertEqual((record["authorised_manifest_hash"], record["manifest_hash_after_extraction"]),
                         (MANIFEST_HASH, MANIFEST_HASH))
        self.assertEqual(record["run_identity_hash"], RUN_IDENTITY)
        self.assertEqual((record["abaqus_solves"], record["abaqus_python_extractions"]), (0, 2))
        self.assertEqual(set(record["extractions"]), set(PACKS))
        self.assertTrue(all(record["validation"].values()))
        self.assertEqual(len(record["initial_set_zero_solve"]), 10)

    def test_packs_match_the_reuse_plan_and_the_baseline(self):
        plan = {o.job_name: o for o in self.reuse.odbs}
        for job, content in PACKS.items():
            entry, item = plan[job], self.record["extractions"][job]
            pack = load_shape_pack_record(CAMPAIGNS / "archive_extraction" / f"{job}.shape-pack.json")
            with self.subTest(job=job):
                self.assertEqual(item["point"], {"E_in_plane_mpa": 52000.0, "G12_mpa": G12[job]})
                self.assertEqual(item["archived_odb"]["sha256"], entry.odb_sha256)
                self.assertNotIn("retry", item["archived_odb"]["relative_path"])
                self.assertEqual((pack.content_sha256, item["pack"]["content_sha256"]), (content, content))
                self.assertEqual(pack.pack.sha256, item["pack"]["file_sha256"])
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
        derived = self.record["s_g12_from_extracted_packs"]
        self.assertEqual(set(derived), {"R1", "R2", "R3"})
        for row, value in derived.items():
            with self.subTest(row=row):
                self.assertTrue(math.isclose(value, accepted[row]["S_G12"], rel_tol=1e-9, abs_tol=1e-12))


class RunStoreTests(unittest.TestCase):
    def test_journalled_packs_reverify_and_retrack(self):
        roots = fixture_roots_from_environment()
        missing = sorted({"m7-run-b", "carbon-project-archive"} - set(roots))
        if missing:
            self.skipTest(f"data stores {missing} not configured")
        from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING
        from services.branch_tracker import track_branches
        from services.fe_shape_pack import load_shape_pack, load_shape_pack_file
        from services.identification_campaign_run import journalled_archive_records
        from services.identification_pipeline import fe_state_from_pack

        run_root = Path(roots["m7-run-b"])
        definition = load_campaign_definition(CAMPAIGNS / "M7_RUN_B.campaign.json")
        reuse = load_archive_reuse(ROOT / definition.archive_reuse, definition.parameterisation_id)
        records = journalled_archive_records(reuse, run_root, MANIFEST_HASH)
        self.assertEqual(set(records), set(PACKS))
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
