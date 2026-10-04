"""M2.3 FrozenRegistration from physical calibration; path/timestamp-independent compatibility."""

from __future__ import annotations

import copy
import dataclasses
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import modal_core
import reviewed_core
from coordinate_calibration import UNIT_TO_METRES
from domain.registration import FrozenRegistration, RegistrationMismatchError
from domain.specimen_manifest import (
    RegistrationBasisStatus as Basis,
    UncertaintyAvailability as Uncertainty,
    parse_specimen_manifest,
)
from m2_support import (
    CALIBRATION,
    PLATE_Y,
    STEP,
    calibration,
    experiment,
    fixture_for,
    grid_points_mm,
    passport_dict,
    passport_for,
    synthetic_fe,
)
from services.physical_registration import (
    PhysicalRegistrationRefusal,
    ProductionReadinessRefusal,
    build_physical_registration,
    require_production_physical_registration,
)
from services.stage_a_identification_service import _check_registration


SWAP = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])  # exp x = FE +Y, exp y = FE -X
CENTERED = {"mode": "documented_centered_alignment", "coordinate_calibration": dict(CALIBRATION),
            "measured_surface": {"fe_instance": "TOP", "side": "max_z", "label": "TOP exterior face"},
            "orientation": {"experimental_axes_in_fe": ["+X", "+Y", "+Z"], "reference": "documented_convention",
                            "source": "documented convention"},
            "uncertainty": {"translation_mm": None, "scale_rel": None, "rotation_deg": None}}
EDGES = {"mode": "scan_to_panel_edges", "coordinate_calibration": dict(CALIBRATION),
         "measured_surface": {"fe_instance": "TOP", "side": "max_z", "label": "TOP exterior face"},
         "orientation": {"experimental_axes_in_fe": ["+X", "+Y", "+Z"], "reference": "panel_edges",
                         "source": "grid aligned to panel edges (photo)"},
         "uncertainty": {"translation_mm": 1.0, "scale_rel": 0.005, "rotation_deg": 0.5},
         "panel_edges": {"x_mm": 10.0, "y_mm": 10.0}}


def true_top_ids(points=None) -> list[str]:
    points = grid_points_mm() if points is None else points
    per_column = int(round(PLATE_Y / STEP)) + 1
    return [f"TOP:{int(round(x / STEP)) * per_column + int(round(y / STEP)) + 1}" for x, y, _ in points]


class _SyntheticRegistration:
    UNIT = "mm"

    def setUp(self):
        self.fe = synthetic_fe(self.UNIT)
        self.fixture = fixture_for(self.fe)

    def build(self, passport, data=None):
        return build_physical_registration(passport, roots={}, fixture_manifest=None, fe_geometry=self.fe,
                                           experimental=(data or experiment(), self.fixture))

    def assertTruth(self, result):
        self.assertEqual(list(result.registration.mapped_fe_node_ids), true_top_ids())
        self.assertLess(result.registration.registration_metrics["mapping_max_residual_in_abaqus_units"], 1e-9)


class RegistrationModeTests(_SyntheticRegistration, unittest.TestCase):
    def test_corner_coordinates_mode(self):
        result = self.build(passport_for(self.fe))
        self.assertTruth(result)
        self.assertIs(result.registration_basis_status, Basis.PHYSICAL)
        self.assertTrue(result.production_ready)
        np.testing.assert_allclose(result.registration.translation, (0.25, -0.1, -1.002), atol=1e-12)
        self.assertEqual(result.registration.registration_metrics["orientation_source"], "corner_A_marker")
        self.assertAlmostEqual(result.registration.registration_metrics["corner_A_marker_angle_deg"], 0.0)

    def test_corner_mode_with_rotated_scan_axes(self):
        passport = passport_for(self.fe, geometry_calibration__orientation={
            "experimental_axes_in_fe": ["+Y", "-X", "+Z"], "reference": "corner_A_marker", "source": "photo"})
        np.testing.assert_array_equal(passport.geometry_calibration.orientation.rotation, SWAP)
        result = self.build(passport, experiment(rotation=SWAP))
        self.assertTruth(result)
        np.testing.assert_array_equal(result.registration.rotation, SWAP)

    def test_panel_edges_mode(self):
        result = self.build(passport_for(self.fe, geometry_calibration=copy.deepcopy(EDGES)))
        self.assertTruth(result)
        self.assertEqual(result.registration.registration_metrics["orientation_source"], "panel_edges")

    def test_documented_centered_mode_is_never_physical(self):
        result = self.build(passport_for(self.fe, geometry_calibration=copy.deepcopy(CENTERED)))
        self.assertTruth(result)
        self.assertIs(result.registration_basis_status, Basis.INCOMPLETE)
        self.assertIs(result.uncertainty_availability, Uncertainty.NOT_AVAILABLE)
        self.assertEqual(result.missing_physical_evidence, (
            "physical registration reference (corner-A marker or measured scan-to-panel-edge offsets)",))
        self.assertIn("geometry_calibration.uncertainty.translation_mm", result.missing_uncertainty)
        self.assertEqual(result.registration.registration_metrics["orientation_source"], "user_confirmed")
        with self.assertRaises(ProductionReadinessRefusal):
            result.require_production_ready()

    def test_content_source_identity_has_no_machine_path_or_timestamp(self):
        result = self.build(passport_for(self.fe))
        identity = result.registration.experimental_source_identity
        self.assertEqual(result.source_identity_basis, "content")
        self.assertIsNone(identity["mtime_ns"])
        self.assertEqual(identity["path"], "snadwich:" + self.fixture.experimental_source.location.relative_path)
        self.assertEqual(identity["sha256"], self.fixture.experimental_source.sha256)


class DeterminismAndProhibitionTests(_SyntheticRegistration, unittest.TestCase):
    def test_registration_is_deterministic(self):
        first, second = self.build(passport_for(self.fe)), self.build(passport_for(self.fe))
        self.assertEqual(first.registration.registration_hash, second.registration.registration_hash)
        data = passport_dict(fe_reference__geometry_identity={
            "schema_version": self.fe.identity["schema_version"], "sha256": self.fe.identity["sha256"],
            "node_count": self.fe.identity["node_count"]})
        reordered = parse_specimen_manifest({key: data[key] for key in reversed(list(data))})
        self.assertEqual(self.build(reordered).registration.registration_hash, first.registration.registration_hash)

    def test_no_mac_or_frequency_path(self):
        boom = AssertionError("registration must not consult modal agreement")
        with patch.object(modal_core, "modal_assurance_criterion", side_effect=boom), \
                patch.object(reviewed_core, "modal_assurance_criterion", side_effect=boom), \
                patch.object(reviewed_core, "_mac_matrix_for_geometry", side_effect=boom), \
                patch.object(reviewed_core, "_frequency_error_matrices", side_effect=boom), \
                patch.object(modal_core, "compare_modal_datasets", side_effect=boom):
            for calibration in (None, EDGES, CENTERED):
                passport = passport_for(self.fe) if calibration is None else passport_for(
                    self.fe, geometry_calibration=copy.deepcopy(calibration))
                with self.subTest(mode=passport.geometry_calibration.mode):
                    self.assertTruth(self.build(passport))

    def test_modal_content_does_not_change_the_registration(self):
        base = self.build(passport_for(self.fe)).registration.registration_hash
        other = experiment(frequencies=(55.0, 3.0), shapes=lambda number, p: np.cos(number * p[:, 1] / 7.0) + 2.0)
        self.assertEqual(self.build(passport_for(self.fe), other).registration.registration_hash, base)

    def test_orientation_comes_from_the_passport_not_a_better_fit(self):
        # Documented convention says (-X, -Y): the builder follows it even though (+X, +Y) fits these data.
        flipped = copy.deepcopy(CENTERED)
        flipped["orientation"]["experimental_axes_in_fe"] = ["-X", "-Y", "+Z"]
        result = self.build(passport_for(self.fe, geometry_calibration=flipped))
        self.assertEqual(np.asarray(result.registration.rotation).tolist(), [[-1, 0, 0], [0, -1, 0], [0, 0, 1]])
        self.assertNotEqual(list(result.registration.mapped_fe_node_ids), true_top_ids())
        # A corner-A marker that contradicts the documented axes is refused, not "corrected".
        contradictory = passport_for(self.fe, geometry_calibration__orientation={
            "experimental_axes_in_fe": ["-X", "-Y", "+Z"], "reference": "corner_A_marker", "source": "photo"})
        with self.assertRaises(PhysicalRegistrationRefusal):
            self.build(contradictory)

    def test_scale_comes_from_the_physical_calibration(self):
        metres = self.build(passport_for(self.fe))
        self.assertEqual(list(metres.registration.coordinate_scales), [1e-3, 1e-3, 1e-3])
        wrong_unit = passport_for(self.fe, geometry_calibration__coordinate_calibration={**CALIBRATION,
                                                                                         "experimental_unit": "mm"})
        result = self.build(wrong_unit)
        self.assertEqual(list(result.registration.coordinate_scales), [1.0, 1.0, 1.0])  # passport governs; no refit
        self.assertNotEqual(list(result.registration.mapped_fe_node_ids), true_top_ids())


class _UnitRegistration(_SyntheticRegistration):
    """The same physical plate and scan in an FE model of another length unit; passport values stay in mm."""

    def passport(self, mode):
        if mode == "corner":
            return passport_for(self.fe, geometry_calibration__coordinate_calibration=calibration(self.UNIT))
        edges = copy.deepcopy(EDGES)
        edges["coordinate_calibration"] = calibration(self.UNIT)
        return passport_for(self.fe, geometry_calibration=edges)

    def test_corner_and_edge_registration_are_unit_safe(self):
        reference = synthetic_fe("mm")
        for mode in ("corner", "edges"):
            with self.subTest(unit=self.UNIT, mode=mode):
                result = self.build(self.passport(mode))
                self.assertTruth(result)  # identical FE nodes as in the mm model
                factor = UNIT_TO_METRES[self.UNIT]
                np.testing.assert_allclose(result.registration.coordinate_scales, (factor,) * 3, rtol=1e-12)
                np.testing.assert_allclose(result.registration.translation, (0.25, -0.1, -1.002), atol=1e-12)
                self.assertEqual(len(result.surface_node_ids), int(sum(n.startswith("TOP:") for n in reference.node_ids)))
                self.assertIs(result.registration_basis_status, Basis.PHYSICAL)


class MillimetreUnitTests(_UnitRegistration, unittest.TestCase):
    UNIT = "mm"


class CentimetreUnitTests(_UnitRegistration, unittest.TestCase):
    UNIT = "cm"


class MetreUnitTests(_UnitRegistration, unittest.TestCase):
    UNIT = "m"

    def test_same_physical_geometry_gives_equivalent_mapping(self):
        mm = synthetic_fe("mm")
        mm_result = build_physical_registration(
            passport_for(mm), roots={}, fe_geometry=mm, experimental=(experiment(), fixture_for(mm)))
        for mode in ("corner", "edges"):
            with self.subTest(mode=mode):
                result = self.build(self.passport(mode))
                self.assertEqual(result.registration.mapped_fe_node_ids, mm_result.registration.mapped_fe_node_ids)
                np.testing.assert_allclose(result.registration.translation, mm_result.registration.translation,
                                           atol=1e-12)
                np.testing.assert_array_equal(result.registration.rotation, mm_result.registration.rotation)


class ProductionReadinessTests(_SyntheticRegistration, unittest.TestCase):
    REFERENCE = "physical registration reference (corner-A marker or measured scan-to-panel-edge offsets)"

    def test_physical_registration_without_uncertainty_is_production_ready(self):
        result = self.build(passport_for(self.fe, geometry_calibration__uncertainty={
            "translation_mm": None, "scale_rel": None, "rotation_deg": None}))
        self.assertIs(result.registration_basis_status, Basis.PHYSICAL)
        self.assertIs(result.uncertainty_availability, Uncertainty.NOT_AVAILABLE)
        self.assertEqual(len(result.missing_uncertainty), 3)
        self.assertEqual(result.production_readiness_issues(), ())
        self.assertIs(result.require_production_ready(), result.registration)
        self.assertIs(require_production_physical_registration(result), result.registration)

    def test_legacy_replay_is_refused_and_never_upgraded(self):
        physical = self.build(passport_for(self.fe))
        legacy = dataclasses.replace(physical, registration_basis_status=Basis.LEGACY_REPLAY,
                                     missing_physical_evidence=(self.REFERENCE,),
                                     orientation_reference="documented_convention", physical_specimen_id=None,
                                     source_identity_basis="legacy_accepted_registration")
        with self.assertRaises(ProductionReadinessRefusal) as caught:
            require_production_physical_registration(legacy)
        reasons = caught.exception.reasons
        self.assertTrue(any("LEGACY_REPLAY" in reason for reason in reasons))
        self.assertIn(f"missing {self.REFERENCE}", reasons)
        self.assertTrue(any("orientation is not physically traceable" in reason for reason in reasons))
        self.assertTrue(any("legacy path/mtime" in reason for reason in reasons))
        self.assertIn("physical_specimen_id is not recorded", reasons)
        self.assertIs(legacy.registration_basis_status, Basis.LEGACY_REPLAY)  # unchanged by the refusal
        self.assertFalse(issubclass(ProductionReadinessRefusal, (ValueError, RuntimeError)))

    def test_each_contract_failure_refuses_on_its_own(self):
        physical = self.build(passport_for(self.fe))
        for changes in ({"registration_basis_status": Basis.INCOMPLETE},
                        {"missing_physical_evidence": (self.REFERENCE,)},
                        {"orientation_reference": "documented_convention"},
                        {"source_identity_basis": "legacy_accepted_registration"},
                        {"physical_specimen_id": None}):
            with self.subTest(changes=changes):
                broken = dataclasses.replace(physical, **changes)
                self.assertEqual(len(broken.production_readiness_issues()), 1)
                with self.assertRaises(ProductionReadinessRefusal):
                    broken.require_production_ready()
        # Uncertainty availability alone is never a refusal.
        self.assertTrue(dataclasses.replace(physical, uncertainty_availability=Uncertainty.NOT_AVAILABLE,
                                            missing_uncertainty=("x",)).production_ready)


class MeasuredScaleTests(_SyntheticRegistration, unittest.TestCase):
    def test_camera_grid_scale_from_measured_scan_window(self):
        # The 5 x 4 grid spans 80 mm x 60 mm on the panel; scale = raw span / measured window size.
        camera = {"mode": "camera_grid", "scan_coverage": "partial", "physical_width": 80.0, "physical_height": 60.0,
                  "dimension_unit": "mm", "abaqus_unit": "mm", "experimental_unit": "m",
                  "provenance": "scan window measured with a steel rule"}
        result = self.build(passport_for(self.fe, geometry_calibration__coordinate_calibration=camera),
                            experiment(scale=2.0e-3, translation=(0.0, 0.0, -1.004)))
        np.testing.assert_allclose(result.registration.coordinate_scales, (2.0e-3, 2.0e-3, 2.0e-3), rtol=1e-12)
        self.assertTruth(result)


class RefusalTests(_SyntheticRegistration, unittest.TestCase):
    def test_fe_identity_mismatch(self):
        other = passport_for(self.fe, fe_reference__geometry_identity={
            "schema_version": "fe-geometry-identity/2", "sha256": "f" * 64, "node_count": 3})
        with self.assertRaises(PhysicalRegistrationRefusal):
            self.build(other)

    def test_missing_corner_node_or_surface(self):
        with self.assertRaises(PhysicalRegistrationRefusal):
            self.build(passport_for(self.fe, geometry_calibration__corner_A={
                "unv_node": 999, "fe_xy_mm": [10.0, 10.0], "x_axis_towards_unv_node": 2}))
        with self.assertRaises(PhysicalRegistrationRefusal):
            self.build(passport_for(self.fe, geometry_calibration__measured_surface={
                "fe_instance": "MISSING", "side": "max_z", "label": "x"}))

    def test_implausible_documented_orientation(self):
        tilted = copy.deepcopy(CENTERED)
        tilted["orientation"]["experimental_axes_in_fe"] = ["+Z", "+X", "+Y"]
        with self.assertRaises(PhysicalRegistrationRefusal):
            self.build(passport_for(self.fe, geometry_calibration=tilted))


class ContentCompatibilityTests(unittest.TestCase):
    """Path/timestamp debt: registrations bind to content, not to one workstation's path or mtime."""

    def setUp(self):
        with open(ROOT / "docs" / "registrations" / "SP02_frozen_registration.json", encoding="utf-8") as handle:
            self.registration = FrozenRegistration.from_dict(json.load(handle))
        self.source = dict(self.registration.experimental_source_identity)
        self.geometry = dict(self.registration.fe_geometry_identity)

    def test_same_content_elsewhere_is_compatible(self):
        moved = {**self.source, "path": "e:\\other\\machine\\copy.unv", "mtime_ns": 1}
        self.assertTrue(self.registration.check_content_compatible(moved, self.geometry))
        _check_registration(self.registration, moved, self.geometry)
        with self.assertRaises(RegistrationMismatchError):  # the legacy exact check still refuses it
            self.registration.check_compatible(moved, self.geometry)

    def test_different_content_or_geometry_is_refused(self):
        for source in ({**self.source, "sha256": "0" * 64}, {**self.source, "size": 1}, {}, None):
            with self.subTest(source=source), self.assertRaises(RegistrationMismatchError):
                self.registration.check_content_compatible(source, self.geometry)
        with self.assertRaises(RegistrationMismatchError):
            self.registration.check_content_compatible(self.source, {**self.geometry, "sha256": "0" * 64})

    def test_registration_without_content_hash_uses_the_legacy_check(self):
        payload = self.registration.to_dict()
        payload["experimental_source_identity"] = {k: v for k, v in self.source.items() if k != "sha256"}
        del payload["registration_hash"]
        legacy = FrozenRegistration.create(**{k: v for k, v in payload.items() if k != "registration_schema_version"})
        with self.assertRaises(RegistrationMismatchError):
            legacy.check_content_compatible(self.source, self.geometry)
        _check_registration(legacy, dict(legacy.experimental_source_identity), self.geometry)
        with self.assertRaises(RegistrationMismatchError):
            _check_registration(legacy, {**legacy.experimental_source_identity, "path": "x"}, self.geometry)


if __name__ == "__main__":
    unittest.main()
