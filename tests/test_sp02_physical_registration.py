"""SP-02 physical registration gate (M6, SUPERVISOR 2026-10-06): reconstruction, frozen registration, re-evaluation.

Same method as SP-13 (D-062). Static checks always run. Reproduction from the real stores is store-gated. No Abaqus.

Anti-tuning: the physical transform comes only from the stored PSV frame and the panel dimensions; it is pinned
(record SHA-256 in the passport, registration hash below) and the evaluation consumes it unchanged.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))

from domain.experiment_fixture import fixture_roots_from_environment  # noqa: E402
from domain.registration import FrozenRegistration  # noqa: E402
from domain.specimen_manifest import RegistrationBasisStatus, load_specimen_manifest  # noqa: E402
from services.psv_video_registration import PSVRegistrationError, alignment_points  # noqa: E402

EVIDENCE = ROOT / "docs/auto_id/registration_evidence"
RECORD = EVIDENCE / "SP02_physical_registration_reconstruction.json"
REEVALUATION = EVIDENCE / "SP02_registration_reevaluation.json"
UNCERTAINTY = EVIDENCE / "SP02_registration_uncertainty.json"
PASSPORT = ROOT / "docs/auto_id/specimens/SP02.physical.specimen.json"
LEGACY_PASSPORT = ROOT / "docs/auto_id/specimens/SP02.specimen.json"
REGISTRATION = ROOT / "docs/registrations/SP02_physical_registration.json"
LEGACY_REGISTRATION = ROOT / "docs/registrations/SP02_frozen_registration.json"
PHYSICAL_REGISTRATION_HASH = "9b63f6c891331ba55a6ee2797f142bf0b75117d9bffbf3ab312ee08a418e882c"
LEGACY_REGISTRATION_HASH = "9bf736d3650b491f8abf5f1a9abd60f6616639fa5f2f8811a896c5a04fbdc164"
SCALE_REL_READOUT = 0.002  # HUMAN H8: 1 mm ruler graduation over the shorter 510 mm side (0.00196), rounded up
MODAL_WORDS = ("mac", "frequency", "frequencies", "hz", "mode", "modes", "pair", "pairs", "modal")


def _keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(_keys(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(_keys(v) for v in value)) if value else set()
    return set()


def _lf_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


class AntiTuningTests(unittest.TestCase):
    def test_reconstruction_record_carries_no_modal_quantity(self):
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        self.assertIs(record["uses_modal_data"], False)
        words = {w for k in _keys(record) - {"uses_modal_data"} for w in k.lower().replace("-", "_").split("_")}
        for token in MODAL_WORDS:
            self.assertNotIn(token, words, f"record has a modal key word {token!r}")

    def test_passport_is_bound_to_the_pinned_reconstruction(self):
        passport = json.loads(PASSPORT.read_text(encoding="utf-8"))
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        gc = passport["geometry_calibration"]
        self.assertIn(_lf_sha(RECORD), gc["coordinate_calibration"]["provenance"])
        m2 = record["m2_model"]
        self.assertEqual(gc["coordinate_calibration"]["physical_width"], round(m2["physical_width_mm"], 4))
        self.assertEqual(gc["coordinate_calibration"]["physical_height"], round(m2["physical_height_mm"], 4))
        self.assertEqual(gc["panel_edges"], {"x_mm": round(m2["panel_edges_x_mm"], 4),
                                             "y_mm": round(m2["panel_edges_y_mm"], 4)})
        # same uncertainty rule as SP-13 (D-062) plus the H8 readout scale contribution
        self.assertEqual(gc["uncertainty"], {"translation_mm": round(m2["residual_vs_reconstruction_mm"]["max"], 2),
                                             "scale_rel": SCALE_REL_READOUT,
                                             "rotation_deg": round(m2["axis_misalignment_deg"], 2)})
        self.assertGreaterEqual(SCALE_REL_READOUT, 1.0 / min(record["panel_dimensions_mm"]))

    def test_dimension_assignment_is_geometric(self):
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        self.assertEqual(record["panel_dimensions_mm"], [510.0, 515.0])  # horizontal = FE X = 510
        self.assertLess(abs(record["dimension_consistency_px_per_mm_x_over_y"] - 1.0), 0.005)

    def test_same_polytec_anisotropy_as_sp13(self):
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        sx, sy = record["unv_vs_physical"]["scale_unv_over_physical"]
        self.assertGreater(sx, 1.05)
        self.assertLess(sy, 0.85)
        self.assertGreater(record["legacy_centred_error_mm"]["median"], 20.0)

    def test_reevaluation_consumed_the_pinned_registrations_unchanged(self):
        document = json.loads(REEVALUATION.read_text(encoding="utf-8"))
        self.assertEqual(document["results"]["PHYSICAL"]["registration_hash"], PHYSICAL_REGISTRATION_HASH)
        self.assertEqual(document["results"]["LEGACY"]["registration_hash"], LEGACY_REGISTRATION_HASH)
        self.assertEqual((document["abaqus_solves"], document["abaqus_python_extractions"]), (0, 0))

    def test_uncertainty_diagnostic_consumed_the_current_passport_and_pinned_registration(self):
        document = json.loads(UNCERTAINTY.read_text(encoding="utf-8"))
        self.assertEqual(document["registration_hash"], PHYSICAL_REGISTRATION_HASH)
        self.assertEqual(document["passport_sha256_lf"], _lf_sha(PASSPORT))
        self.assertEqual(document["accepted_pairs"], [[2, 8], [4, 10], [7, 13]])
        self.assertEqual((document["status"], document["unavailable_components"]), ("EVALUATED", []))
        self.assertIs(document["registration_limited_both_triggers"], False)


class GovernedFileTests(unittest.TestCase):
    def test_physical_registration_file_is_pinned(self):
        registration = FrozenRegistration.from_dict(json.loads(REGISTRATION.read_text(encoding="utf-8")))
        self.assertEqual(registration.registration_hash, PHYSICAL_REGISTRATION_HASH)
        metrics = dict(registration.registration_metrics)
        self.assertEqual(metrics["calibration_mode"], "scan_to_panel_edges")
        self.assertEqual(metrics["orientation_source"], "panel_edges")

    def test_legacy_registration_is_kept_as_historical_provenance(self):
        legacy = FrozenRegistration.from_dict(json.loads(LEGACY_REGISTRATION.read_text(encoding="utf-8")))
        self.assertEqual(legacy.registration_hash, LEGACY_REGISTRATION_HASH)
        status = load_specimen_manifest(LEGACY_PASSPORT).geometry_calibration.registration_basis_status
        self.assertIs(status, RegistrationBasisStatus.LEGACY_REPLAY)

    def test_physical_passport_is_physical_but_identity_is_not_invented(self):
        manifest = load_specimen_manifest(PASSPORT)
        gc = manifest.geometry_calibration
        self.assertIs(gc.registration_basis_status, RegistrationBasisStatus.PHYSICAL)
        self.assertEqual(gc.missing_physical_evidence, ())
        self.assertEqual(gc.missing_uncertainty, ())
        self.assertIsNone(manifest.physical_specimen_id)  # NEEDS_ONE_HUMAN_CONFIRMATION
        raw = json.loads(PASSPORT.read_text(encoding="utf-8"))
        self.assertIn("NEEDS_ONE_HUMAN_CONFIRMATION", raw["unavailable"]["physical_specimen_id"])


class AlignmentParserTests(unittest.TestCase):
    """Behaviour change: the alignment table is read from its stored count (SP-02 has 27 points, SP-13 19)."""

    @staticmethod
    def _blob(count: int) -> bytes:
        head = bytearray(44)
        struct.pack_into("<I", head, 40, count)
        rows = b"".join(struct.pack("<Iddff", 1, 0.1 * k, -0.2 * k, 0.01 * k, 0.02 * k) for k in range(count))
        return bytes(head) + rows

    def test_any_stored_count_is_read(self):
        for count in (19, 27):
            with self.subTest(count=count):
                rows = alignment_points(self._blob(count))
                self.assertEqual(rows.shape, (count, 4))
                self.assertAlmostEqual(rows[-1, 0], 0.1 * (count - 1))
                self.assertAlmostEqual(rows[-1, 3], np.float32(0.02 * (count - 1)), places=6)

    def test_invalid_table_is_refused(self):
        with self.assertRaises(PSVRegistrationError):
            alignment_points(bytes(20))
        with self.assertRaises(PSVRegistrationError):
            alignment_points(self._blob(27)[:-28])  # truncated
        with self.assertRaises(PSVRegistrationError):
            alignment_points(self._blob(2))


class StoreReproductionTests(unittest.TestCase):
    """Real-data reproduction (needs both data stores)."""

    def setUp(self):
        roots = fixture_roots_from_environment()
        missing = sorted({"snadwich", "carbon-project-archive"} - set(roots))
        if missing:
            self.skipTest(f"data stores {missing} not configured")

    def test_reconstruction_is_reproduced_from_the_pinned_sources(self):
        from reconstruct_psv_registration import build

        record = json.loads(RECORD.read_text(encoding="utf-8"))
        dims = record["sources"]["panel_dimensions"]
        rebuilt = build("snadwich", record["sources"]["svd"]["relative_path"],
                        record["sources"]["unv_geometry"]["relative_path"], dims["width_mm"], dims["height_mm"],
                        dims["source"], dims["uncertainty"])
        self.assertEqual(rebuilt["sources"], record["sources"])
        self.assertEqual(rebuilt["stream_sha256"], record["stream_sha256"])
        self.assertTrue(np.allclose(rebuilt["scan_points_panel_mm"], record["scan_points_panel_mm"], atol=1e-6))
        for key in ("physical_width_mm", "physical_height_mm", "panel_edges_x_mm", "panel_edges_y_mm"):
            self.assertAlmostEqual(rebuilt["m2_model"][key], record["m2_model"][key], places=9)

    def test_registration_is_rebuilt_and_blocked_only_by_identity(self):
        from services.physical_registration import build_physical_registration

        result = build_physical_registration(load_specimen_manifest(PASSPORT))
        self.assertEqual(result.registration.registration_hash, PHYSICAL_REGISTRATION_HASH)
        self.assertEqual(result.production_readiness_issues(), ("physical_specimen_id is not recorded",))

    def test_strict_freeze_under_both_registrations(self):
        document = json.loads(REEVALUATION.read_text(encoding="utf-8"))
        pairs = {k: [(r["experimental_mode"], r["fe_mode"]) for r in document["results"][k]["strict_pairs"]]
                 for k in ("LEGACY", "PHYSICAL")}
        self.assertEqual(pairs, {"LEGACY": [(2, 8)], "PHYSICAL": [(2, 8), (4, 10), (7, 13)]})
        from sp02_registration_reevaluation import compute

        recomputed = compute(include_alternative=False)
        for name in ("LEGACY", "PHYSICAL"):
            with self.subTest(name=name):
                got, recorded = recomputed["results"][name], document["results"][name]
                self.assertEqual(got["status"], recorded["status"])
                self.assertEqual([(r["experimental_mode"], r["fe_mode"]) for r in got["strict_pairs"]], pairs[name])
                for a, b in zip(got["strict_pairs"], recorded["strict_pairs"]):
                    self.assertAlmostEqual(a["mac"], b["mac"], places=12)
                self.assertEqual(got.get("holdouts"), recorded.get("holdouts"))
                self.assertEqual(got["observation_sufficient"], recorded["observation_sufficient"])
        self.assertEqual(recomputed["results"]["PHYSICAL"]["holdouts"]["fit_row_ids"], ["R1", "R2"])
        self.assertEqual(recomputed["legacy_vs_physical_geometry"], document["legacy_vs_physical_geometry"])
        self.assertEqual(recomputed["combined_sp02_sp13"], document["combined_sp02_sp13"])

    def test_carbon5a_sensitivities_match_the_archived_carbon5a_table(self):
        import csv

        from services.archived_baseline import load_archived_baseline
        from sp02_registration_reevaluation import BASELINE, carbon5a_sensitivities

        roots = fixture_roots_from_environment()
        mine = carbon5a_sensitivities(roots, load_archived_baseline(BASELINE))
        with open(roots["carbon-project-archive"] / "carbon5a/sensitivity.csv", newline="", encoding="utf-8") as h:
            archived = {int(r["baseline_fe_branch"]): r for r in csv.DictReader(h) if r["specimen"] == "SP02"}
        self.assertTrue(archived)
        for fe_mode, row in archived.items():
            with self.subTest(fe_mode=fe_mode):
                self.assertEqual(mine[fe_mode]["status"], "RESOLVED")
                self.assertAlmostEqual(mine[fe_mode]["S_E"], float(row["S_E"]), places=9)
                self.assertAlmostEqual(mine[fe_mode]["S_G12"], float(row["S_G"]), places=9)

    def test_uncertainty_diagnostic_is_reproduced(self):
        from registration_uncertainty_evaluation import compute

        recorded = json.loads(UNCERTAINTY.read_text(encoding="utf-8"))
        got = compute(Path(recorded["passport"]), Path(recorded["registration_file"]),
                      Path("docs/auto_id/baselines/SP02.carbon4c-baseline.json"), recorded["pack"],
                      Path(recorded["pairs_source"]))
        self.assertEqual(got["pairing_change_diagnostic"], recorded["pairing_change_diagnostic"])
        for a, b in zip(got["pairs"], recorded["pairs"]):
            self.assertAlmostEqual(a["minimum_mac"], b["minimum_mac"], places=12)
            self.assertAlmostEqual(a["maximum_mac"], b["maximum_mac"], places=12)
        self.assertIs(got["registration_limited_both_triggers"], False)


if __name__ == "__main__":
    unittest.main()
