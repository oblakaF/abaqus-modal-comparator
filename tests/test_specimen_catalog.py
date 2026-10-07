"""Specimen catalog (docs/auto_id/SPECIMEN_CATALOG.md + specimen_catalog.json): documentation-governance checks.

Static checks always run: unique and deterministic specimen IDs and family memberships, controlled vocabularies,
no measured/template confusion, no SP-02/SP-13 core swap, Markdown <-> JSON parity, and agreement with the governed
repository records. Source files are verified (existence, size, SHA-256) only for the data stores configured through
``AUTO_ID_FIXTURE_ROOT_<STORE>``. No Abaqus.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.experiment_fixture import fixture_roots_from_environment  # noqa: E402

CATALOG = ROOT / "docs/auto_id/specimen_catalog.json"
MARKDOWN = ROOT / "docs/auto_id/SPECIMEN_CATALOG.md"
IDENTITY = {"CONFIRMED", "DERIVED", "AMBIGUOUS"}
AUTO_ID_STATUS = {"READY_FOR_M7", "NEEDS_REGISTRATION", "NEEDS_GOVERNANCE", "NEEDS_FORWARD_MODEL",
                  "NEEDS_MODAL_PREPARATION", "OBSERVATION_INSUFFICIENT", "NOT_APPLICABLE"}
CONSTANT_STATUS = {"MEASURED", "ASSUMED/TEMPLATE", "UNKNOWN"}
CONTRADICTION_CLASS = {"STALE_DOC", "EXPECTED_HISTORICAL", "REAL_CONFLICT", "UNKNOWN"}


def _catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def _refs(value):
    """Every external file reference (a dict with store + relative_path) anywhere in the catalog."""
    if isinstance(value, dict):
        if "store" in value and "relative_path" in value:
            yield value
        for v in value.values():
            yield from _refs(v)
    elif isinstance(value, list):
        for v in value:
            yield from _refs(v)


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class CatalogStructureTests(unittest.TestCase):
    def setUp(self):
        self.catalog = _catalog()
        self.specimens = self.catalog["specimens"]
        self.by_id = {s["specimen_id"]: s for s in self.specimens}

    def test_status_and_scope(self):
        self.assertEqual(self.catalog["schema"], "auto-id/specimen-catalog/v1")
        self.assertEqual(self.catalog["status"], "ACCEPTED")  # SUPERVISOR 2026-10-07 (D-065)
        self.assertFalse(self.catalog["runtime_dependency"])
        self.assertEqual((self.catalog["abaqus_solves"], self.catalog["abaqus_python_extractions"]), (0, 0))

    def test_specimen_ids_are_unique_and_sorted(self):
        ids = [s["specimen_id"] for s in self.specimens]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, sorted(ids))
        self.assertTrue(all(re.fullmatch(r"SP-\d\d", i) for i in ids))
        self.assertNotIn("SP-14", ids, "SP-14 has no physical record; it is listed only as an unresolved name")
        self.assertEqual([n["name"] for n in self.catalog["names_without_physical_record"]], ["SP-14"])

    def test_family_membership_is_deterministic(self):
        families = {f["family_id"]: f for f in self.catalog["families"]}
        self.assertEqual(len(families), len(self.catalog["families"]))
        for s in self.specimens:
            self.assertIn(s["family_id"], families, s["specimen_id"])
        for family_id, family in families.items():
            members = sorted(s["specimen_id"] for s in self.specimens if s["family_id"] == family_id)
            self.assertEqual(family["members"], members, family_id)
            self.assertEqual(sorted(family["cores"]), members, family_id)

    def test_controlled_vocabularies(self):
        for s in self.specimens:
            self.assertIn(s["identity"]["confidence"], IDENTITY, s["specimen_id"])
            self.assertTrue(s["auto_id_status"], s["specimen_id"])
            self.assertLessEqual(set(s["auto_id_status"]), AUTO_ID_STATUS, s["specimen_id"])
        for c in self.catalog["contradictions"]:
            self.assertIn(c["class"], CONTRADICTION_CLASS, c["id"])

    def test_no_measured_or_template_confusion(self):
        """No material constant is measured for any specimen; FE template values are never labelled MEASURED."""
        for s in self.specimens:
            blocks = [s["face_material"]["constants"]]
            if s["core"]:
                blocks.append(s["core"]["constants"])
            for block in blocks:
                self.assertIn(block["status"], CONSTANT_STATUS, s["specimen_id"])
                self.assertNotEqual(block["status"], "MEASURED", s["specimen_id"])
                if block["status"] == "UNKNOWN":
                    self.assertIsNone(block["values"], s["specimen_id"])
                else:
                    self.assertTrue(block["values"], s["specimen_id"])

    def test_no_sp02_sp13_core_swap(self):
        self.assertEqual(self.by_id["SP-02"]["core"]["topology"], "honeycomb")
        self.assertEqual(self.by_id["SP-13"]["core"]["topology"], "auxetic")
        self.assertEqual(self.by_id["SP-02"]["family_id"], self.by_id["SP-13"]["family_id"])

    def test_sp02_identity_is_resolved_from_records_not_confirmed(self):
        resolution = self.catalog["identity_resolutions"]["SP-02"]
        self.assertEqual(resolution["verdict"], "SP02_IDENTITY_RESOLVED_FROM_RECORDS")
        self.assertEqual(resolution["confidence"], "DERIVED")
        self.assertEqual(self.by_id["SP-02"]["identity"]["confidence"], "DERIVED")
        self.assertEqual(len(resolution["lms_sp2_old_hz"]), 9)

    def test_governed_fixtures(self):
        governed = sorted((s["specimen_id"], e["governed_set"]) for s in self.specimens for e in s["experiments"]
                          if e["governed"])
        self.assertEqual(governed, [
            ("SP-02", "Bravo (1) (active fixture SP02/bravo-1-physical)"),
            ("SP-13", "Best (fixture SP13/best)"),
            ("SP-13", "Bravo (1) (frozen FREQUENCY_ONLY fixture SP13/260909-bravo-1, D-065)")])
        self.assertFalse(any("READY_FOR_M7" in s["auto_id_status"] for s in self.specimens))


class RepositoryAgreementTests(unittest.TestCase):
    """Hashes quoted by the catalog equal the governed repository records."""

    def setUp(self):
        self.by_id = {s["specimen_id"]: s for s in _catalog()["specimens"]}

    def test_registration_hashes(self):
        for sid in ("SP-02", "SP-13"):
            for kind in ("legacy", "physical"):
                entry = self.by_id[sid]["registration"][kind]
                record = json.loads((ROOT / entry["path"]).read_text(encoding="utf-8"))
                self.assertEqual(record["registration_hash"], entry["registration_hash"], (sid, kind))
            self.assertTrue((ROOT / self.by_id[sid]["registration"]["physical"]["passport"]).is_file())

    def test_forward_models(self):
        for sid in ("SP-02", "SP-13"):
            entry = self.by_id[sid]["fe_assets"]["governed_forward_model"]
            manifest = json.loads((ROOT / entry["path"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["forward_model_id"], entry["forward_model_id"])
            self.assertEqual(manifest["model_input"]["sha256"], entry["inp_sha256"])

    def test_governed_fixture_sources(self):
        fixtures = json.loads((ROOT / "docs/auto_id/fixtures/real_experiment_fixtures.json").read_text(encoding="utf-8"))
        sources = {f["experimental_source"]["location"]["relative_path"]: f["experimental_source"]["sha256"]
                   for f in fixtures["fixtures"]}
        frozen = json.loads((ROOT / "docs/auto_id/fixtures/SP13_260909.frozen-modal-set.json").read_text(encoding="utf-8"))
        for s in self.by_id.values():
            for e in s["experiments"]:
                if not e["governed"]:
                    continue
                if "zip_member" in e["source"]:  # frozen FREQUENCY_ONLY record outside the M0.2 manifest (D-065)
                    self.assertEqual((e["source"]["zip_member"], e["source"]["sha256"]),
                                     (frozen["source"]["member"]["name"], frozen["source"]["member"]["sha256"]))
                else:
                    self.assertEqual(sources[e["source"]["relative_path"]], e["source"]["sha256"], s["specimen_id"])


class MarkdownParityTests(unittest.TestCase):
    def setUp(self):
        self.catalog = _catalog()
        self.ids = {s["specimen_id"] for s in self.catalog["specimens"]}
        self.text = MARKDOWN.read_text(encoding="utf-8")

    def _section(self, number: int) -> str:
        return self.text.split(f"\n## {number}. ")[1].split("\n## ")[0]

    def test_specimen_records(self):
        self.assertEqual(set(re.findall(r"^### (SP-\d\d) ", self._section(6), flags=re.M)), self.ids)

    def test_asset_matrix(self):
        self.assertEqual(set(re.findall(r"^\| (SP-\d\d) \|", self._section(5), flags=re.M)), self.ids)

    def test_one_line_summaries(self):
        self.assertEqual(set(re.findall(r"^- (SP-\d\d) — ", self._section(11), flags=re.M)), self.ids)

    def test_contradictions_and_questions(self):
        ids = {c["id"] for c in self.catalog["contradictions"]}
        self.assertEqual(set(re.findall(r"^\| (C\d+) \|", self._section(9), flags=re.M)), ids)
        for c in self.catalog["contradictions"]:
            self.assertRegex(self._section(9), rf"\| {c['id']} \|.*{re.escape(c['class'])}")
        questions = {q["id"] for q in self.catalog["open_questions"]}
        self.assertEqual(set(re.findall(r"\*\*(Q\d)", self._section(10))), questions)

    def test_family_table(self):
        section = self._section(8)
        for family in self.catalog["families"]:
            self.assertIn(f"**{family['family_id']}**", section)
            for member in family["members"]:
                self.assertIn(member, section)


class StoreSourceTests(unittest.TestCase):
    """Every referenced source file exists with the recorded size and hash (configured stores only)."""

    def test_referenced_files(self):
        roots = fixture_roots_from_environment()
        refs = [r for r in _refs(_catalog()) if r["store"] in roots]
        if not refs:
            self.skipTest("no catalog data store configured")
        for r in refs:
            with self.subTest(store=r["store"], path=r["relative_path"], member=r.get("zip_member")):
                path = roots[r["store"]] / r["relative_path"]
                self.assertTrue(path.is_file())
                if "zip_member" in r:
                    with zipfile.ZipFile(path) as archive:
                        data = archive.read(r["zip_member"])
                    self.assertEqual(len(data), r["size_bytes"])
                    self.assertEqual(hashlib.sha256(data).hexdigest(), r["sha256"])
                    continue
                self.assertEqual(path.stat().st_size, r["size_bytes"])
                if "sha256" in r:
                    self.assertEqual(_sha(path), r["sha256"])

    def test_lms_sheet_assigns_the_governed_sp02_set_to_old_sp2(self):
        roots = fixture_roots_from_environment()
        if "sumin" not in roots:
            self.skipTest("data store 'sumin' not configured")
        import openpyxl

        resolution = _catalog()["identity_resolutions"]["SP-02"]
        sheet = openpyxl.load_workbook(roots["sumin"] / "Updated_260911/Experiment_Freq_damping_LMS.xlsx",
                                       data_only=True, read_only=True)[resolution["lms_sheet"]]
        rows = [list(r) for r in sheet.iter_rows(values_only=True)]
        h = next(i for i, r in enumerate(rows) if "SP2" in r)
        header = rows[h]
        columns = {}
        for i, cell in enumerate(header):
            if cell in ("SP2", "SP10") and i + 1 < len(header):
                columns[f"{cell} {header[i + 1]}"] = i
        self.assertEqual(sorted(columns), ["SP10 (new SP2)", "SP2 (old)"])
        modes = [r for r in rows[h + 1:] if r and r[0] in range(1, 10)][:9]
        self.assertEqual([r[0] for r in modes], list(range(1, 10)))

        def values(col):
            return [float(str(r[col]).replace(" Hz", "")) for r in modes]

        self.assertEqual(values(columns["SP2 (old)"]), resolution["lms_sp2_old_hz"])
        self.assertEqual(values(columns["SP10 (new SP2)"]), resolution["lms_sp10_new_sp2_hz"])
        governed = next(e for s in _catalog()["specimens"] if s["specimen_id"] == "SP-02" for e in s["experiments"]
                        if e["governed"])
        bravo = next(f for f in governed["fitted_sets"] if f["set"] == "Bravo (1)")["frequencies_hz"]
        for lms, fit in zip(resolution["lms_sp2_old_hz"], bravo):
            self.assertAlmostEqual(lms, fit, delta=0.001 + 2e-5 * fit)


if __name__ == "__main__":
    unittest.main()
