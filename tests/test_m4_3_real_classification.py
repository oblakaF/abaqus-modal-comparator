"""M4.3 real validation: provisional classifier on the validated SP13 baseline shape pack (no Abaqus)."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.experiment_fixture import fixture_roots_from_environment
from services.fe_shape_pack import load_shape_pack, load_shape_pack_record
from services.modal_family_classifier import (
    PROVISIONAL_FAMILY_CLASSIFIER as POLICY,
    ClassifiedRow,
    classify_shape_pack_modes,
    mirror_coverage,
    select_holdouts,
)


JOB = "SP13_a46d08b52995e078"
RECORD = ROOT / "docs" / "auto_id" / "fe_shapes" / f"{JOB}.families.json"
PACK_RECORD = ROOT / "docs" / "auto_id" / "fe_shapes" / f"{JOB}.shape-pack.json"


def grid(lx=510.0, ly=520.0, n=21):
    points = np.array([(x, y) for x in np.linspace(0, lx, n) for y in np.linspace(0, ly, n)])
    return points, (points[:, 0] - lx / 2) / (lx / 2), (points[:, 1] - ly / 2) / (ly / 2)


class HelperTests(unittest.TestCase):
    def test_mirror_coverage(self):
        points, u, v = grid()
        self.assertEqual(mirror_coverage(points), {"x": 1.0, "y": 1.0, "diagonal": 1.0, "antidiagonal": 1.0})
        keep = ~((u > 0.3) & (v > 0.3))
        self.assertLess(mirror_coverage(points[keep])["x"], POLICY.minimum_mirror_coverage)

    def test_classify_shape_pack_modes_uses_out_of_plane_component(self):
        points, u, v = grid()
        displacements = np.zeros((2, len(points), 3))
        displacements[0, :, 2] = u * v
        displacements[1, :, 2] = u ** 2 - 1 / 3
        displacements[:, :, 0] = 5.0  # in-plane components are ignored
        pack = SimpleNamespace(coordinates=np.column_stack([points, np.full(len(points), 2.0)]),
                               displacements=displacements, mode_numbers=(7, 8))
        families = classify_shape_pack_modes(pack)
        self.assertTrue(families[7].torsion_dominated)
        self.assertEqual(families[8].key, "Px:E|Py:E|nx:2|ny:0")


class RecordTests(unittest.TestCase):
    """The pinned classification record (no store needed)."""

    def setUp(self):
        self.record = json.loads(RECORD.read_text(encoding="utf-8"))

    def test_record_binds_to_pack_policy_and_frozen_set(self):
        self.assertEqual(self.record["shape_pack_content_sha256"], load_shape_pack_record(PACK_RECORD).content_sha256)
        self.assertEqual(self.record["classifier_policy"], {"policy_id": POLICY.policy_id,
                                                            "policy_hash": POLICY.policy_hash, "status": "PROVISIONAL"})
        rows = self.record["frozen_observation_set"]["rows"]
        self.assertEqual([(r["row_id"], r["experimental_mode"], r["fe_mode"]) for r in rows],
                         [("R1", 4, 10), ("R2", 5, 11)])
        self.assertEqual(self.record["frozen_observation_set"]["observation_hash"][:16], "922888c7285c8ff0")

    def test_validation_checks(self):
        checks = self.record["checks"]
        self.assertTrue(checks["all_modes_classified"])
        self.assertTrue(checks["mirror_coverage_at_least_policy"])
        self.assertTrue(checks["frozen_rows_classified"])
        self.assertTrue(checks["parity_nodal_consistent_all_modes"])
        self.assertEqual(checks["lowest_torsion_family_identified"], 7)
        first = self.record["modes"][0]
        self.assertEqual((first["fe_mode"], first["family_key"], first["torsion_dominated"]),
                         (7, "Px:O|Py:O|nx:1|ny:1", True))

    def test_holdout_rules_as_defined(self):
        rows = [ClassifiedRow(r["row_id"], r["experimental_hz"], SimpleNamespace(
            key=r["family_key"], torsion_dominated=r["torsion_dominated"])) for r in
            self.record["frozen_observation_set"]["rows"]]
        selection = select_holdouts(rows, k_int_enabled=False)
        recorded = self.record["holdout_selection"]
        self.assertIsNone(selection.torsion_family)  # no odd-odd family among the frozen rows
        self.assertEqual(selection.validation_family, recorded["validation_family"])  # highest accepted family
        self.assertEqual(list(selection.holdout_row_ids), recorded["holdout_row_ids"])
        self.assertEqual(recorded["holdout_row_ids"], ["R2"])
        self.assertEqual(list(selection.fit_row_ids), ["R1"])  # one fit row remains (< 2 parameters)


class StoreTests(unittest.TestCase):
    def test_classification_reproduces_from_the_pack(self):
        roots = fixture_roots_from_environment()
        if "carbon-project-archive" not in roots:
            self.skipTest("data store 'carbon-project-archive' not configured")
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        pack = load_shape_pack(load_shape_pack_record(PACK_RECORD), roots)
        families = classify_shape_pack_modes(pack)
        self.assertEqual(mirror_coverage(pack.coordinates[:, :2]), record["surface"]["mirror_coverage"])
        for entry in record["modes"]:
            with self.subTest(fe_mode=entry["fe_mode"]):
                family = families[entry["fe_mode"]]
                self.assertEqual((family.key, family.parity_x.value, family.parity_y.value, family.torsion_dominated),
                                 (entry["family_key"], entry["parity_x"], entry["parity_y"],
                                  entry["torsion_dominated"]))
                for name in ("p_x", "p_y", "p_diagonal", "p_antidiagonal"):
                    self.assertAlmostEqual(getattr(family, name), entry[name], places=9)


if __name__ == "__main__":
    unittest.main()
