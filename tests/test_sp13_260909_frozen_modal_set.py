"""SP-13 260909 frozen external PolyMAX modal set (D-026/D-027/D-028; SUPERVISOR 2026-10-07, D-065).

Static checks always run: identity, FREQUENCY_ONLY scope, no registration/FE claim, Sigma_setup still provisional.
Reproduction from the archived Testlab export and the raw 260909 acquisition is store-gated (stores ``sumin`` and
``snadwich``). Nothing is refitted; no Abaqus.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.experiment_fixture import fixture_roots_from_environment, load_experiment_fixture_manifest  # noqa: E402

RECORD = ROOT / "docs/auto_id/fixtures/SP13_260909.frozen-modal-set.json"


def _record() -> dict:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def _blocks(path: Path):
    """UNV datasets as (number, lines), read-only."""
    with open(path, encoding="latin-1") as handle:
        inside, number, lines = False, None, []
        for raw in handle:
            line = raw.rstrip("\r\n")
            if line.strip() == "-1" and len(line) <= 6:
                if inside:
                    yield number, lines
                    inside, number, lines = False, None, []
                else:
                    inside = True
                continue
            if inside and number is None:
                number = int(line.split()[0])
            elif inside:
                lines.append(line)


def _geometry(path: Path):
    for number, lines in _blocks(path):
        if number == 2411:
            ids = [int(lines[i].split()[0]) for i in range(0, len(lines) - 1, 2)]
            xyz = [[float(v.replace("D", "E")) for v in lines[i + 1].split()] for i in range(0, len(lines) - 1, 2)]
            return ids, np.array(xyz)
    raise AssertionError("no dataset 2411")


class FrozenRecordTests(unittest.TestCase):
    def test_identity_and_scope(self):
        record = _record()
        self.assertEqual(record["schema"], "auto-id/frozen-external-modal-set/v1")
        self.assertEqual(record["fixture_id"], "SP13/260909-bravo-1")
        self.assertEqual((record["specimen_id"], record["physical_specimen_id"]), ("SP13", "SP-13"))
        self.assertEqual(record["use_scope"], "FREQUENCY_ONLY")
        self.assertEqual(record["modal_set"]["display_name"], "Bravo (1)")
        self.assertEqual(record["modal_set"]["testlab_project"], "SP13_500by500_Glue420_Auxetic_newSP01_260909")
        self.assertEqual(record["provenance_audit"]["verdict"], "SP13_260909_POLYMAX_PROVENANCE_CONFIRMED")
        modes = record["frozen_modes"]
        self.assertEqual([m["number"] for m in modes], list(range(1, 10)))
        self.assertEqual([round(m["frequency_hz"], 2) for m in modes],
                         [31.64, 74.14, 80.82, 94.43, 96.55, 147.86, 206.15, 212.61, 228.75])

    def test_no_registration_fe_or_cross_grid_claim(self):
        record = _record()
        self.assertEqual(record["registration"]["status"], "NOT_AVAILABLE")
        self.assertEqual(record["fe"]["status"], "NOT_APPLICABLE")
        self.assertTrue(record["relation_to_governed_fixture"]["mode_correspondence"].startswith("NOT_ESTABLISHED"))

    def test_sigma_setup_stays_provisional(self):
        sigma = _record()["sigma_setup"]
        self.assertEqual((sigma["status"], sigma["value_percent"], sigma["flagged"]), ("PROVISIONAL", 0.3, True))

    def test_separate_from_the_mac_fixture_manifest(self):
        """D-028: a separate fixture; the M0.2 manifest (registration + FE required) is unchanged for SP-13."""
        ids = [f.fixture_id for f in load_experiment_fixture_manifest(
            ROOT / "docs/auto_id/fixtures/real_experiment_fixtures.json").fixtures]
        self.assertNotIn(_record()["fixture_id"], ids)
        self.assertIn("SP13/best", ids)


class StoreReproductionTests(unittest.TestCase):
    def setUp(self):
        self.roots = fixture_roots_from_environment()
        missing = sorted({"sumin", "snadwich"} - set(self.roots))
        if missing:
            self.skipTest(f"data stores {missing} not configured")
        self.record = _record()

    def _member(self, directory: Path) -> Path:
        source = self.record["source"]
        archive_path = self.roots["sumin"] / source["archive"]["relative_path"]
        self.assertEqual(archive_path.stat().st_size, source["archive"]["size_bytes"])
        with zipfile.ZipFile(archive_path) as archive:
            data = archive.read(source["member"]["name"])
        self.assertEqual(len(data), source["member"]["size_bytes"])
        self.assertEqual(hashlib.sha256(data).hexdigest(), source["member"]["sha256"])
        path = directory / source["member"]["name"]
        path.write_bytes(data)
        return path

    def test_frozen_modes_are_read_unchanged_by_the_production_reader(self):
        import universal_reader

        with tempfile.TemporaryDirectory() as tmp:
            dataset = universal_reader.load_universal_modal_file(self._member(Path(tmp)), modal_set="bravo-1")
        frequencies = [m.frequency_hz for m in dataset.sorted_modes()]
        self.assertEqual(frequencies, [m["frequency_hz"] for m in self.record["frozen_modes"]])

    def test_geometry_is_the_raw_260909_acquisition(self):
        raw = self.record["raw_acquisition"]["unv"]
        raw_path = self.roots["snadwich"] / raw["relative_path"]
        with open(raw_path, "rb") as handle:
            self.assertEqual(hashlib.sha256(handle.read()).hexdigest(), raw["sha256"])
        with tempfile.TemporaryDirectory() as tmp:
            ids_fit, xyz_fit = _geometry(self._member(Path(tmp)))
        ids_raw, xyz_raw = _geometry(raw_path)
        self.assertEqual(sorted(ids_fit), sorted(ids_raw))
        order = {k: i for i, k in enumerate(ids_raw)}
        difference = np.linalg.norm(xyz_raw[[order[k] for k in ids_fit]] - xyz_fit, axis=1).max()
        self.assertLessEqual(difference, 1e-12)
        node_set = hashlib.sha256("\n".join(sorted(str(v) for v in ids_fit)).encode("utf-8")).hexdigest()
        self.assertEqual(node_set, self.record["geometry"]["node_set_sha256"])


if __name__ == "__main__":
    unittest.main()
