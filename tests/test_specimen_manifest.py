"""M2.1 specimen passport and M2.2 identities."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.experimental_qc import TrustedSuspensionThreshold
from domain.specimen_manifest import (
    DesignId,
    FamilyId,
    PhysicalSpecimenId,
    SpecimenManifestError,
    TestRunId,
    parse_specimen_manifest,
)
from m2_support import parse, passport_dict


def bare_plate(**overrides):
    data = passport_dict(specimen_type="bare_plate", materials={"face": "CFRP_Twill"}, core_height_mm=None,
                         face_thickness_mm={"plate": [0.45] * 9}, unavailable={"core_height_mm": "no core"})
    data.update(overrides)
    return data


def core_tile(**overrides):
    data = passport_dict(specimen_type="core_tile", materials={"core": "PLA_Auxetic"}, face_thickness_mm=None,
                         unavailable={"face_thickness_mm": "a core tile has no faces"})
    data.update(overrides)
    return data


class ValidPassportTests(unittest.TestCase):
    def test_valid_sandwich_passport(self):
        manifest = parse()
        self.assertEqual(manifest.specimen_type, "sandwich")
        self.assertEqual((manifest.plan_mm.lx_mm, manifest.plan_mm.ly_mm), (100.0, 80.0))
        self.assertEqual(len(manifest.face_thickness_mm["top"]), 9)
        self.assertTrue(manifest.geometry_calibration.physically_complete)
        self.assertEqual(manifest.geometry_calibration.missing_physical_evidence, ())

    def test_valid_bare_plate_passport(self):
        manifest = parse_specimen_manifest(bare_plate())
        self.assertEqual(manifest.specimen_type, "bare_plate")
        self.assertIsNone(manifest.core_height_mm)
        self.assertEqual(set(manifest.face_thickness_mm), {"plate"})

    def test_valid_core_tile_passport(self):
        manifest = parse_specimen_manifest(core_tile())
        self.assertEqual(manifest.specimen_type, "core_tile")
        self.assertIsNone(manifest.face_thickness_mm)

    def test_unknown_values_stay_explicitly_unavailable(self):
        manifest = parse(suspension_max_hz=None, plan_mm=None,
                         unavailable={"suspension_max_hz": "not measured", "plan_mm": "not measured"})
        self.assertIsNone(manifest.suspension_max_hz)
        self.assertIsNone(manifest.trusted_suspension_threshold())  # never the illustrative 18 Hz
        self.assertEqual(manifest.unavailable["plan_mm"], "not measured")

    def test_trusted_suspension_threshold_comes_from_the_passport(self):
        threshold = parse().trusted_suspension_threshold()
        self.assertIsInstance(threshold, TrustedSuspensionThreshold)
        self.assertEqual(threshold.suspension_max_hz, 20.0)
        self.assertIn("RUN-SYN-A", threshold.source)


class CanonicalHashTests(unittest.TestCase):
    def test_hash_is_deterministic(self):
        self.assertEqual(parse().manifest_hash, parse().manifest_hash)

    def test_key_order_does_not_change_the_hash(self):
        data = passport_dict()
        reordered = json.loads(json.dumps(data, sort_keys=True))
        reversed_keys = {key: reordered[key] for key in reversed(list(reordered))}
        self.assertEqual(parse_specimen_manifest(reversed_keys).manifest_hash, parse_specimen_manifest(data).manifest_hash)

    def test_meaningful_changes_change_the_hash(self):
        base = parse().manifest_hash
        for changes in ({"plan_mm": {"Lx": 100.5, "Ly": 80.0, "sd": 0.5}},
                        {"geometry_calibration__uncertainty": {"translation_mm": 2.0, "scale_rel": 0.005,
                                                               "rotation_deg": 0.5}},
                        {"geometry_calibration__orientation": {"experimental_axes_in_fe": ["-X", "-Y", "+Z"],
                                                               "reference": "corner_A_marker", "source": "photo"}},
                        {"test_run_id": "RUN-SYN-B"},
                        {"suspension_max_hz": {"value_hz": 21.0, "source": "rig log"}}):
            with self.subTest(changes=list(changes)):
                self.assertNotEqual(parse(**changes).manifest_hash, base)

    def test_no_local_absolute_paths(self):
        for path in (r"D:\data\geo.csv", "/data/geo.csv", "../geo.csv"):
            with self.subTest(path=path), self.assertRaises(SpecimenManifestError):
                parse(fe_reference__geometry_file__location={"store": "archive", "relative_path": path})


class IdentityTests(unittest.TestCase):
    def test_identity_types_are_distinct(self):
        self.assertNotEqual(DesignId("SP-13"), PhysicalSpecimenId("SP-13"))
        self.assertNotEqual(PhysicalSpecimenId("X"), TestRunId("X"))
        self.assertEqual(TestRunId("RUN-1"), TestRunId("RUN-1"))
        manifest = parse()
        self.assertIsInstance(manifest.family_id, FamilyId)
        self.assertIsInstance(manifest.design_id, DesignId)
        self.assertIsInstance(manifest.physical_specimen_id, PhysicalSpecimenId)
        self.assertIsInstance(manifest.test_run_id, TestRunId)

    def test_identities_must_not_collapse(self):
        for changes in ({"physical_specimen_id": "DES-SYN"}, {"test_run_id": "PANEL-SYN-1"},
                        {"design_id": "FAM-plain-0.45"}):
            with self.subTest(changes=changes), self.assertRaises(SpecimenManifestError) as caught:
                parse(**changes)
            self.assertEqual(caught.exception.field, "identities")

    def test_missing_or_empty_identities_are_refused(self):
        for key in ("family_id", "design_id", "test_run_id"):
            for value in ("", None, " ", "bad id with spaces"):
                with self.subTest(key=key, value=value), self.assertRaises(SpecimenManifestError):
                    parse(**{key: value})

    def test_unknown_physical_specimen_needs_a_reason(self):
        with self.assertRaises(SpecimenManifestError):
            parse(physical_specimen_id=None)
        self.assertIsNone(parse(physical_specimen_id=None,
                                unavailable={"physical_specimen_id": "not recorded"}).physical_specimen_id)

    def test_remount_must_not_point_to_itself(self):
        with self.assertRaises(SpecimenManifestError):
            parse(acquisition__remount_of="RUN-SYN-A", acquisition__remount_kind="remount",
                  acquisition__remount_evidence="log")

    def test_remount_link_needs_kind_and_evidence(self):
        with self.assertRaises(SpecimenManifestError):
            parse(acquisition__remount_of="RUN-SYN-0")
        with self.assertRaises(SpecimenManifestError):
            parse(acquisition__remount_of="RUN-SYN-0", acquisition__remount_kind="moved it a bit",
                  acquisition__remount_evidence="log")
        manifest = parse(acquisition__remount_of="RUN-SYN-0", acquisition__remount_kind="remount",
                         acquisition__remount_evidence="rig log 2026-10-05")
        self.assertEqual(manifest.acquisition.remount_of, TestRunId("RUN-SYN-0"))


class MalformedPassportTests(unittest.TestCase):
    def assertRefused(self, data, field_fragment=None):
        with self.assertRaises(SpecimenManifestError) as caught:
            parse_specimen_manifest(data)
        if field_fragment:
            self.assertIn(field_fragment, caught.exception.field)

    def test_schema_and_type(self):
        self.assertRefused(passport_dict(schema="auto-id/specimen/v1.0"), "schema")
        missing = passport_dict()
        del missing["schema"]
        self.assertRefused(missing)
        self.assertRefused(passport_dict(specimen_type="beam"), "specimen_type")
        self.assertRefused(passport_dict(extra_field=1))

    def test_invalid_physical_values(self):
        for changes, field in (
            ({"plan_mm": {"Lx": -100.0, "Ly": 80.0, "sd": 0.5}}, "plan_mm.Lx"),
            ({"plan_mm": {"Lx": 100.0, "Ly": math.nan, "sd": 0.5}}, "plan_mm.Ly"),
            ({"plan_mm": {"Lx": 100.0, "Ly": 80.0, "sd": 0.0}}, "plan_mm.sd"),
            ({"masses_g": {"panel": 0.0}}, "masses_g.panel"),
            ({"core_height_mm": {"value": 1.96, "sd": -0.01}}, "core_height_mm.sd"),
            ({"face_thickness_mm": {"top": [0.45] * 8, "bottom": [0.45] * 9}}, "face_thickness_mm.top"),
            ({"suspension_max_hz": {"value_hz": 0.0, "source": "x"}}, "suspension_max_hz.value_hz"),
            ({"suspension_max_hz": {"value_hz": 18.0, "source": " "}}, "suspension_max_hz.source"),
        ):
            with self.subTest(field=field):
                self.assertRefused(passport_dict(**changes), field)

    def test_type_specific_content(self):
        self.assertRefused(bare_plate(core_height_mm={"value": 2.0, "sd": 0.1}, unavailable={}), "core_height_mm")
        self.assertRefused(core_tile(face_thickness_mm={"top": [0.45] * 9, "bottom": [0.45] * 9}, unavailable={}),
                           "face_thickness_mm")
        self.assertRefused(passport_dict(materials={"face": "CFRP"}), "materials")

    def test_null_without_declared_reason(self):
        self.assertRefused(passport_dict(suspension_max_hz=None), "suspension_max_hz")
        self.assertRefused(passport_dict(unavailable={"plan_mm": "x"}), "plan_mm")
        self.assertRefused(passport_dict(unavailable={"test_run_id": "x"}), "unavailable")

    def test_incomplete_or_unknown_calibration(self):
        calibration = passport_dict()["geometry_calibration"]
        no_corner = copy.deepcopy(calibration)
        del no_corner["corner_A"]
        self.assertRefused(passport_dict(geometry_calibration=no_corner), "corner_A")
        self.assertRefused(passport_dict(geometry_calibration__mode="best_fit"), "geometry_calibration.mode")
        self.assertRefused(passport_dict(geometry_calibration__coordinate_calibration={"mode": "legacy_geometric_fit",
                                                                                       "provenance": "x"}))
        self.assertRefused(passport_dict(geometry_calibration__coordinate_calibration={**calibration["coordinate_calibration"],
                                                                                       "provenance": ""}))
        self.assertRefused(passport_dict(geometry_calibration__corner_A={"unv_node": 1, "fe_xy_mm": [0.0, 0.0],
                                                                         "x_axis_towards_unv_node": 1}))
        edges = copy.deepcopy(calibration)
        edges["mode"] = "scan_to_panel_edges"
        self.assertRefused(passport_dict(geometry_calibration=edges), "corner_A")
        del edges["corner_A"]
        self.assertRefused(passport_dict(geometry_calibration=edges), "panel_edges")

    def test_untraceable_orientation(self):
        for orientation in (
            {"experimental_axes_in_fe": ["+X", "+X", "+Z"], "reference": "corner_A_marker", "source": "photo"},
            {"experimental_axes_in_fe": ["+X", "+Y"], "reference": "corner_A_marker", "source": "photo"},
            {"experimental_axes_in_fe": ["+X", "+Y", "+Z"], "reference": "best_mac", "source": "photo"},
            {"experimental_axes_in_fe": ["+X", "+Y", "+Z"], "reference": "corner_A_marker", "source": ""},
            {"experimental_axes_in_fe": ["+X", "+Y", "+Z"], "reference": "documented_convention", "source": "x"},
        ):
            with self.subTest(orientation=orientation):
                self.assertRefused(passport_dict(geometry_calibration__orientation=orientation))

    def test_non_positive_uncertainty_is_refused_but_missing_is_allowed(self):
        self.assertRefused(passport_dict(geometry_calibration__uncertainty={"translation_mm": 0.0, "scale_rel": 0.01,
                                                                            "rotation_deg": 0.5}))
        manifest = parse(geometry_calibration__uncertainty={"translation_mm": None, "scale_rel": 0.01,
                                                            "rotation_deg": None})
        self.assertEqual(manifest.geometry_calibration.uncertainty.missing, ("translation_mm", "rotation_deg"))
        self.assertFalse(manifest.geometry_calibration.physically_complete)


class HistoricalPassportTests(unittest.TestCase):
    """The accepted SP02/SP13 passports parse and record their physical gaps honestly."""

    def test_accepted_passports(self):
        for name in ("SP02", "SP13"):
            with self.subTest(name=name):
                from domain.specimen_manifest import load_specimen_manifest

                manifest = load_specimen_manifest(ROOT / "docs" / "auto_id" / "specimens" / f"{name}.specimen.json")
                self.assertEqual(manifest.geometry_calibration.mode, "documented_centered_alignment")
                self.assertFalse(manifest.geometry_calibration.physically_complete)
                self.assertIsNone(manifest.suspension_max_hz)
                self.assertIsNone(manifest.trusted_suspension_threshold())
                self.assertIsNone(manifest.physical_specimen_id)
                self.assertIn("suspension_max_hz", manifest.unavailable)
                self.assertEqual(manifest.geometry_calibration.uncertainty.missing,
                                 ("translation_mm", "scale_rel", "rotation_deg"))


if __name__ == "__main__":
    unittest.main()
