"""SP-13 physical registration gate (M6, SUPERVISOR 2026-10-06): reconstruction, frozen registration, re-evaluation.

Static checks always run. Reproduction from the real stores is store-gated. No Abaqus.

Anti-tuning: the physical transform comes only from the stored PSV frame and the measured panel dimensions; it is
pinned (record SHA-256 in the passport, registration hash below) and the evaluation consumes it unchanged.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
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
from services.archived_baseline import (  # noqa: E402
    ArchivedBaselineError,
    complete_mac_matrix,
    reregistered_mac_matrix,
)
from services.psv_video_registration import CompoundFile, PSVRegistrationError, default_rectangle  # noqa: E402

EVIDENCE = ROOT / "docs/auto_id/registration_evidence"
RECORD = EVIDENCE / "SP13_physical_registration_reconstruction.json"
REEVALUATION = EVIDENCE / "SP13_registration_reevaluation.json"
UNCERTAINTY = EVIDENCE / "SP13_registration_uncertainty.json"
PASSPORT = ROOT / "docs/auto_id/specimens/SP13.physical.specimen.json"
LEGACY_PASSPORT = ROOT / "docs/auto_id/specimens/SP13.specimen.json"
REGISTRATION = ROOT / "docs/registrations/SP13_physical_registration.json"
LEGACY_REGISTRATION = ROOT / "docs/registrations/SP13_frozen_registration.json"
PHYSICAL_REGISTRATION_HASH = "2eeeaa8698851baf33c640a5e741a91a67c6629b436700a920ba9333061cd823"
LEGACY_REGISTRATION_HASH = "a8970e525d10173af3d3b030b1150ca24432b616e1b52f6e8cfeefe2946f58a4"
TRANSFORM_MODULES = ("src/services/psv_video_registration.py", "tools/reconstruct_psv_registration.py",
                     "tools/build_sp13_physical_registration.py", "tools/build_physical_registration.py")
SCALE_REL_READOUT = 0.002  # HUMAN H8: 1 mm ruler graduation over the shorter 510 mm side (0.00196), rounded up
MODAL_MODULES = ("identification_pairing", "archived_baseline", "baseline_freeze", "branch_tracker",
                 "identification_clusters", "modal_family_classifier", "fe_shape_pack", "modal_core",
                 "universal_reader", "experimental_qc", "registration_uncertainty")


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
        elif isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
    return names


def _keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(_keys(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(_keys(v) for v in value)) if value else set()
    return set()


class AntiTuningTests(unittest.TestCase):
    def test_transform_code_never_reads_modal_data_or_mac(self):
        for module in TRANSFORM_MODULES:
            for name in _imports(ROOT / module):
                for forbidden in MODAL_MODULES:
                    with self.subTest(module=module, name=name):
                        self.assertFalse(name == forbidden or name.endswith("." + forbidden),
                                         f"{module} imports {name}: the transform must not see modal data")

    def test_reconstruction_record_carries_no_modal_quantity(self):
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        self.assertIs(record["uses_modal_data"], False)
        words = {w for k in _keys(record) - {"uses_modal_data"} for w in k.lower().replace("-", "_").split("_")}
        for token in ("mac", "frequency", "frequencies", "hz", "mode", "modes", "pair", "pairs", "modal"):
            self.assertNotIn(token, words, f"record has a modal key word {token!r}")

    def test_passport_is_bound_to_the_pinned_reconstruction(self):
        record_sha = hashlib.sha256(RECORD.read_bytes().replace(b"\r\n", b"\n")).hexdigest()  # committed LF blob
        passport = json.loads(PASSPORT.read_text(encoding="utf-8"))
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        gc = passport["geometry_calibration"]
        self.assertIn(record_sha, gc["coordinate_calibration"]["provenance"])
        m2 = record["m2_model"]
        self.assertEqual(gc["coordinate_calibration"]["physical_width"], round(m2["physical_width_mm"], 4))
        self.assertEqual(gc["coordinate_calibration"]["physical_height"], round(m2["physical_height_mm"], 4))
        self.assertEqual(gc["panel_edges"], {"x_mm": round(m2["panel_edges_x_mm"], 4),
                                             "y_mm": round(m2["panel_edges_y_mm"], 4)})
        # H8: readout resolution only (not calibrated accuracy); no calibration or operator term is added
        self.assertEqual(gc["uncertainty"]["scale_rel"], SCALE_REL_READOUT)
        self.assertGreaterEqual(SCALE_REL_READOUT, 1.0 / min(record["panel_dimensions_mm"]))
        self.assertEqual(gc["uncertainty"]["translation_mm"],
                         round(m2["residual_vs_reconstruction_mm"]["max"], 2))
        self.assertEqual(gc["uncertainty"]["rotation_deg"], round(m2["axis_misalignment_deg"], 2))

    def test_h7_orientation_is_recorded_without_changing_the_registration(self):
        source = json.loads(PASSPORT.read_text(encoding="utf-8"))["geometry_calibration"]["orientation"]["source"]
        self.assertIn("HUMAN H7", source)
        self.assertIn("MAC was not used", source)
        registration = FrozenRegistration.from_dict(json.loads(REGISTRATION.read_text(encoding="utf-8")))
        self.assertEqual(registration.registration_hash, PHYSICAL_REGISTRATION_HASH)

    def test_uncertainty_diagnostic_consumed_the_current_passport_and_pinned_registration(self):
        document = json.loads(UNCERTAINTY.read_text(encoding="utf-8"))
        self.assertEqual(document["registration_hash"], PHYSICAL_REGISTRATION_HASH)
        self.assertEqual(document["passport_sha256_lf"],
                         hashlib.sha256(PASSPORT.read_bytes().replace(b"\r\n", b"\n")).hexdigest())
        self.assertEqual(document["accepted_pairs"], [[4, 10], [7, 13]])
        self.assertEqual((document["status"], document["unavailable_components"]), ("EVALUATED", []))
        self.assertIs(document["registration_limited"], False)
        self.assertIs(document["pairing_change_diagnostic"]["pairing_changed"], False)
        self.assertIs(document["registration_limited_both_triggers"], False)
        self.assertEqual((document["abaqus_solves"], document["abaqus_python_extractions"]), (0, 0))

    def test_reevaluation_consumed_the_pinned_registration_unchanged(self):
        document = json.loads(REEVALUATION.read_text(encoding="utf-8"))
        self.assertEqual(document["results"]["PHYSICAL"]["registration_hash"], PHYSICAL_REGISTRATION_HASH)
        self.assertEqual(document["results"]["LEGACY"]["registration_hash"], LEGACY_REGISTRATION_HASH)
        self.assertEqual((document["abaqus_solves"], document["abaqus_python_extractions"]), (0, 0))


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

    def test_physical_passport_is_physical_with_complete_uncertainty(self):
        manifest = load_specimen_manifest(PASSPORT)
        gc = manifest.geometry_calibration
        self.assertIs(gc.registration_basis_status, RegistrationBasisStatus.PHYSICAL)
        self.assertEqual(gc.missing_physical_evidence, ())
        self.assertEqual(gc.missing_uncertainty, ())  # H8 supplies the readout scale contribution
        self.assertEqual(str(manifest.physical_specimen_id), "SP-13")
        self.assertEqual(manifest.acquisition.remount_kind, "re_suspension")


class ReregisteredMacTests(unittest.TestCase):
    def test_other_registration_is_accepted_only_on_the_same_fe_geometry_and_node_set(self):
        from test_baseline_freeze import _synthetic_shape_pack_case

        baseline, pack, registration, experiment = _synthetic_shape_pack_case(
            registration={"registration_hash": "e" * 64})
        with self.assertRaises(ArchivedBaselineError):  # the archived path stays bound to its own registration
            complete_mac_matrix(baseline, pack, registration, experiment)
        matrix = reregistered_mac_matrix(baseline, pack, registration, experiment)
        self.assertEqual(matrix.shape, (len(baseline.experimental_modes), len(baseline.fe_modes)))
        for change in ({"fe_geometry_identity": {"sha256": "9" * 64}},
                       {"registration_metrics": {"fe_mapping_node_subset": {"node_count": 4, "sha256": "8" * 64}}}):
            with self.subTest(change=change):
                case = _synthetic_shape_pack_case(registration={"registration_hash": "e" * 64, **change})
                with self.assertRaises(ArchivedBaselineError):
                    reregistered_mac_matrix(*case)


class ParserUnitTests(unittest.TestCase):
    def test_non_compound_file_is_refused(self):
        with self.assertRaises(PSVRegistrationError):
            CompoundFile(b"not an svd" * 100)

    def test_default_rectangle_must_be_a_rectangle(self):
        import struct

        blob = bytes(12) + struct.pack("<4f", -0.2222, 0.0, 1.5556, 1.0)
        self.assertAlmostEqual(default_rectangle(blob)[2] - default_rectangle(blob)[0], 1.7778, places=4)
        with self.assertRaises(PSVRegistrationError):
            default_rectangle(bytes(12) + struct.pack("<4f", 1.0, 0.0, 0.5, 1.0))


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
        rebuilt = build("snadwich", record["sources"]["svd"]["relative_path"],
                        record["sources"]["unv_geometry"]["relative_path"],
                        record["sources"]["panel_dimensions"]["width_mm"],
                        record["sources"]["panel_dimensions"]["height_mm"],
                        record["sources"]["panel_dimensions"]["source"])
        self.assertEqual(rebuilt["sources"], record["sources"])
        self.assertEqual(rebuilt["stream_sha256"], record["stream_sha256"])
        self.assertTrue(np.allclose(rebuilt["scan_points_panel_mm"], record["scan_points_panel_mm"], atol=1e-6))
        for key in ("physical_width_mm", "physical_height_mm", "panel_edges_x_mm", "panel_edges_y_mm"):
            self.assertAlmostEqual(rebuilt["m2_model"][key], record["m2_model"][key], places=9)

    def test_registration_is_rebuilt_from_the_passport_and_production_ready(self):
        from services.physical_registration import build_physical_registration

        result = build_physical_registration(load_specimen_manifest(PASSPORT))
        self.assertEqual(result.registration.registration_hash, PHYSICAL_REGISTRATION_HASH)
        self.assertEqual(result.production_readiness_issues(), ())

    def test_uncertainty_diagnostic_is_reproduced(self):
        from registration_uncertainty_evaluation import compute

        recorded = json.loads(UNCERTAINTY.read_text(encoding="utf-8"))
        got = compute(Path(recorded["passport"]), Path(recorded["registration_file"]),
                      Path("docs/auto_id/baselines/SP13.carbon4c-baseline.json"), recorded["pack"],
                      Path(recorded["pairs_source"]))
        self.assertEqual(got["pairing_change_diagnostic"], recorded["pairing_change_diagnostic"])
        for a, b in zip(got["pairs"], recorded["pairs"]):
            self.assertAlmostEqual(a["minimum_mac"], b["minimum_mac"], places=12)
            self.assertAlmostEqual(a["maximum_mac"], b["maximum_mac"], places=12)
        self.assertIs(got["registration_limited_both_triggers"], False)

    def test_strict_freeze_under_both_registrations(self):
        document = json.loads(REEVALUATION.read_text(encoding="utf-8"))
        pairs = {k: [(r["experimental_mode"], r["fe_mode"]) for r in document["results"][k]["strict_pairs"]]
                 for k in ("LEGACY", "PHYSICAL")}
        self.assertEqual(pairs, {"LEGACY": [(4, 10), (5, 11)], "PHYSICAL": [(4, 10), (7, 13)]})
        from sp13_registration_reevaluation import compute

        recomputed = compute(include_alternative=False)["results"]
        for name in ("LEGACY", "PHYSICAL"):
            with self.subTest(name=name):
                got, recorded = recomputed[name], document["results"][name]
                self.assertEqual(got["status"], recorded["status"])
                self.assertEqual([(r["experimental_mode"], r["fe_mode"]) for r in got["strict_pairs"]], pairs[name])
                for a, b in zip(got["strict_pairs"], recorded["strict_pairs"]):
                    self.assertAlmostEqual(a["mac"], b["mac"], places=12)
                self.assertEqual(got["holdouts"], recorded["holdouts"])
                self.assertIs(got["observation_sufficient"], False)  # unchanged M4.3 holdout leaves one fit row


if __name__ == "__main__":
    unittest.main()
