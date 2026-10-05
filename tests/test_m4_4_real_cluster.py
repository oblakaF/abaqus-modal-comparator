"""M4.4 real cluster confirmation of SP13 R1/R2 from validated shape packs (no Abaqus)."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.experiment_fixture import fixture_roots_from_environment
from services.fe_shape_pack import load_shape_pack, load_shape_pack_record
from services.identification_clusters import (
    BRANCH_MINIMUM_MAC,
    CARBON_V1_DIRECTIONS,
    CLUSTER_TRIGGER_RELATIVE_SPACING,
    SUBSPACE_MINIMUM_COS2,
    confirm_cluster,
)


SHAPES = ROOT / "docs" / "auto_id" / "fe_shapes"
RECORD = SHAPES / "SP13.R1-R2.cluster.json"
JOBS = {"BASELINE": "SP13_a46d08b52995e078", "E_in_plane_mpa-": "SP13_a9df66283a168786",
        "E_in_plane_mpa+": "SP13_0e861d03c333bb0b", "G12_mpa-": "SP13_0328066b74b6fd78",
        "G12_mpa+": "SP13_4c0f189b9727feaf"}


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.record = json.loads(RECORD.read_text(encoding="utf-8"))

    def test_criteria_are_the_approved_constants(self):
        self.assertEqual(self.record["criteria"]["trigger_relative_spacing"], CLUSTER_TRIGGER_RELATIVE_SPACING)
        self.assertEqual(self.record["criteria"]["branch_minimum_mac"], BRANCH_MINIMUM_MAC)
        self.assertEqual(self.record["criteria"]["subspace_minimum_cos2"], SUBSPACE_MINIMUM_COS2)
        self.assertEqual(self.record["criteria"]["directions"], list(CARBON_V1_DIRECTIONS))

    def test_inputs_bind_to_m4_2_and_m4_3(self):
        families = json.loads((SHAPES / "SP13_a46d08b52995e078.families.json").read_text(encoding="utf-8"))
        family_of = {m["fe_mode"]: m["family_key"] for m in families["modes"]}
        rows = self.record["rows"]
        self.assertEqual([(r["row_id"], r["experimental_mode"], r["fe_mode"]) for r in rows],
                         [("R1", 4, 10), ("R2", 5, 11)])
        self.assertEqual([r["family_key"] for r in rows], [family_of[10], family_of[11]])
        self.assertEqual(self.record["frozen_observation_hash"],
                         families["frozen_observation_set"]["observation_hash"])
        for key, job in JOBS.items():
            content = load_shape_pack_record(SHAPES / f"{job}.shape-pack.json").content_sha256
            if key == "BASELINE":
                self.assertEqual(self.record["baseline_pack_content_sha256"], content)
            else:
                direction = next(d for d in self.record["results"]["surface_U1_U2_U3"]["directions"]
                                 if d["direction"] == key)
                self.assertEqual(direction["pack_content_sha256"], content)

    def test_trigger_fires_but_identity_is_stable(self):
        self.assertTrue(self.record["trigger"]["fired"])  # frequency proximity is a trigger only
        self.assertLess(self.record["trigger"]["experimental_spacing"], CLUSTER_TRIGGER_RELATIVE_SPACING)
        self.assertEqual(self.record["decision"], "INDEPENDENT")
        for basis, result in self.record["results"].items():
            with self.subTest(basis=basis):
                self.assertEqual(result["status"], "INDEPENDENT")
                for direction in result["directions"]:
                    self.assertEqual(direction["best_counterparts"], [10, 11])
                    self.assertEqual(direction["counterparts_above_0_9"], [1, 1])
                    self.assertTrue(direction["individual_stable"])
                    self.assertGreater(min(direction["best_individual_mac"]), BRANCH_MINIMUM_MAC)
                    self.assertLess(max(direction["cross_mac_R1_to_perturbed_11"],
                                        direction["cross_mac_R2_to_perturbed_10"]), 1e-3)


class StoreTests(unittest.TestCase):
    def test_confirmation_reproduces_from_the_packs(self):
        roots = fixture_roots_from_environment()
        if "carbon-project-archive" not in roots:
            self.skipTest("data store 'carbon-project-archive' not configured")
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        packs = {key: load_shape_pack(load_shape_pack_record(SHAPES / f"{job}.shape-pack.json"), roots)
                 for key, job in JOBS.items()}
        base = packs["BASELINE"]
        for basis in ("surface_U1_U2_U3", "surface_U3"):
            def vectors(pack, modes):
                data = pack.displacements[[pack.mode_index(m) for m in modes]].astype(np.float64)
                return data.reshape(len(modes), -1) if basis == "surface_U1_U2_U3" else data[:, :, 2]

            result = confirm_cluster(("R1", "R2"), vectors(base, (10, 11)),
                                     {d: vectors(packs[d], packs[d].mode_numbers) for d in CARBON_V1_DIRECTIONS})
            with self.subTest(basis=basis):
                self.assertEqual(result.status.value, record["results"][basis]["status"])
                for item, recorded in zip(result.directions, record["results"][basis]["directions"]):
                    self.assertEqual(item.direction, recorded["direction"])
                    for value, expected in zip(item.individual_macs + item.cos2,
                                               recorded["best_individual_mac"] + recorded["subspace_cos2"]):
                        self.assertAlmostEqual(value, expected, places=9)


if __name__ == "__main__":
    unittest.main()
