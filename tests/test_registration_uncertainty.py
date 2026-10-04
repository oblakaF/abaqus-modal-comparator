"""M2.4 registration uncertainty diagnostic (SPEC §11): physical perturbations only; never a best MAC."""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from coordinate_calibration import millimetres_to_model_units
from domain.specimen_manifest import GeometryUncertainty
from m2_support import PLATE_X, PLATE_Y, calibration, experiment, fixture_for, passport_for, synthetic_fe
from modal_core import modal_assurance_criterion
from services import registration_uncertainty
from services.physical_registration import build_physical_registration
from services.registration_uncertainty import (
    RegistrationUncertaintyReport,
    UncertaintyStatus,
    evaluate_registration_uncertainty,
    perturbation_set,
)


def wavy(number: int, points: np.ndarray, waves: float) -> np.ndarray:
    return np.sin(waves * number * np.pi * points[:, 0] / PLATE_X) * np.sin(np.pi * points[:, 1] / PLATE_Y)


class _Setup:
    WAVES = 1.0
    UNIT = "mm"

    def setUp(self):
        self.fe = synthetic_fe(self.UNIT)
        self.experiment = experiment(shapes=lambda n, p: wavy(n, p, self.WAVES))
        self.passport = passport_for(self.fe, geometry_calibration__coordinate_calibration=calibration(self.UNIT))
        result = build_physical_registration(self.passport, roots={}, fe_geometry=self.fe,
                                             experimental=(self.experiment, fixture_for(self.fe)))
        self.registration, self.surface = result.registration, result.surface_node_ids
        top = [i for i, node in enumerate(self.fe.node_ids) if node.startswith("TOP:")]
        self.fe_modes = {}
        for number in (1, 2):
            values = {}
            for index in top:
                vector = np.zeros(3)
                point_mm = self.fe.coordinates[index:index + 1] / millimetres_to_model_units(1.0, self.UNIT)
                vector[2] = wavy(number, point_mm, self.WAVES)[0]
                values[self.fe.node_ids[index]] = vector
            self.fe_modes[number] = values

    def evaluate(self, uncertainty):
        return evaluate_registration_uncertainty(self.registration, uncertainty, self.fe, self.surface,
                                                 self.experiment, self.fe_modes, [(1, 1), (2, 2)], ["U3"])


class PerturbationSetTests(unittest.TestCase):
    def test_deterministic_physical_set(self):
        complete = GeometryUncertainty(1.0, 0.005, 0.5)
        first, missing = perturbation_set(complete)
        self.assertEqual([p.name for p in first], ["+translation_x", "-translation_x", "+translation_y",
                                                   "-translation_y", "+scale", "-scale", "+rotation", "-rotation"])
        self.assertEqual(first, perturbation_set(complete)[0])
        self.assertEqual(missing, ())
        self.assertEqual(first[0].translation_mm, (1.0, 0.0))
        self.assertEqual(first[5].scale_rel, -0.005)

    def test_missing_uncertainty_stays_unavailable(self):
        perturbations, missing = perturbation_set(GeometryUncertainty(None, 0.01, None))
        self.assertEqual([p.name for p in perturbations], ["+scale", "-scale"])
        self.assertEqual(missing, ("translation_mm", "rotation_deg"))
        self.assertEqual(perturbation_set(GeometryUncertainty(None, None, None)), ((), ("translation_mm", "scale_rel",
                                                                                         "rotation_deg")))


class DiagnosticTests(_Setup, unittest.TestCase):
    def test_mac_range_is_reported(self):
        report = self.evaluate(GeometryUncertainty(1.0, 0.005, 0.5))
        self.assertIs(report.status, UncertaintyStatus.EVALUATED)
        self.assertEqual(len(report.perturbations), 8)
        for pair in report.pairs:
            self.assertAlmostEqual(pair.nominal_mac, 1.0, places=9)
            self.assertLessEqual(pair.minimum_mac, pair.nominal_mac)
            self.assertGreaterEqual(pair.maximum_mac, pair.minimum_mac)
            self.assertEqual(len(pair.per_perturbation), 8)
        self.assertIs(report.registration_limited, False)
        self.assertEqual(report.pairing_change_evaluation, "DEFERRED_M4")

    def test_nominal_registration_stays_nominal(self):
        before = self.registration.to_dict()
        report = self.evaluate(GeometryUncertainty(5.0, 0.02, 2.0))
        self.assertEqual(self.registration.to_dict(), before)
        self.assertEqual(report.nominal_registration_hash, self.registration.registration_hash)

    def test_no_best_perturbation_is_ever_selected(self):
        names = {field.name for field in fields(RegistrationUncertaintyReport)}
        self.assertFalse({name for name in names if "best" in name or "selected" in name or "optim" in name})
        report = self.evaluate(GeometryUncertainty(5.0, 0.02, 2.0))
        self.assertFalse(any(hasattr(outcome, "registration") for outcome in report.perturbations))

    def test_missing_uncertainty_is_not_available(self):
        report = self.evaluate(GeometryUncertainty(None, None, None))
        self.assertIs(report.status, UncertaintyStatus.NOT_AVAILABLE)
        self.assertIsNone(report.registration_limited)
        self.assertEqual(report.perturbations, ())
        self.assertFalse(report.mac_threshold_crossing_evaluated)
        self.assertEqual([pair.minimum_mac for pair in report.pairs], [pair.nominal_mac for pair in report.pairs])

    def test_partial_uncertainty_cannot_prove_not_limited(self):
        report = self.evaluate(GeometryUncertainty(None, 0.001, None))
        self.assertIs(report.status, UncertaintyStatus.PARTIAL)
        self.assertIsNone(report.registration_limited)


class ThresholdCrossingTests(_Setup, unittest.TestCase):
    WAVES = 9.0  # short wavelength: a few millimetres of misplacement change the shape correlation strongly

    def test_crossing_sets_registration_limited(self):
        report = self.evaluate(GeometryUncertainty(6.0, 0.005, 0.5))
        self.assertTrue(any(pair.crosses_threshold for pair in report.pairs))
        self.assertIs(report.registration_limited, True)
        self.assertEqual(report.nominal_registration_hash, self.registration.registration_hash)

    def test_small_uncertainty_does_not(self):
        report = self.evaluate(GeometryUncertainty(0.2, 0.0005, 0.05))
        self.assertIs(report.registration_limited, False)


def _comparable(report):
    return ([(o.perturbation, o.mapped_ids_sha256, o.remapped_points) for o in report.perturbations],
            [(p.per_perturbation, p.crosses_threshold) for p in report.pairs], report.registration_limited)


class NonMillimetreModelTests(_Setup, unittest.TestCase):
    """Translation uncertainty is physical (mm): a metre FE model perturbs the same physical distance."""

    UNIT = "m"
    WAVES = 9.0

    def test_translation_uncertainty_is_converted_to_model_units(self):
        mm = ThresholdCrossingTests(methodName="test_small_uncertainty_does_not")
        mm.setUp()
        for uncertainty in (GeometryUncertainty(0.2, 0.0005, 0.05), GeometryUncertainty(6.0, 0.005, 0.5)):
            with self.subTest(uncertainty=uncertainty):
                metres, millimetres = self.evaluate(uncertainty), mm.evaluate(uncertainty)
                expected, actual = _comparable(millimetres), _comparable(metres)
                self.assertEqual([item[1:] for item in actual[0]], [item[1:] for item in expected[0]])
                self.assertEqual(actual[2], expected[2])
                for got, want in zip(actual[1], expected[1]):
                    self.assertEqual(got[1], want[1])
                    for (name, value), (other, reference) in zip(got[0], want[0]):
                        self.assertEqual(name, other)
                        self.assertAlmostEqual(value, reference, places=9)
        # 0.2 mm stays within one 2 mm mesh cell in a metre model (read as 0.2 m it would leave the panel).
        report = self.evaluate(GeometryUncertainty(0.2, None, None))
        self.assertEqual([o.remapped_points for o in report.perturbations], [0, 0, 0, 0])


class _InvalidMac:
    """Make selected MAC evaluations non-finite (call order per pair: nominal, then each perturbation)."""

    def __init__(self, positions, calls_per_pair, value=float("nan")):
        self.positions, self.calls_per_pair, self.value, self.calls = set(positions), calls_per_pair, value, 0

    def __call__(self, *args, **kwargs):
        position = self.calls % self.calls_per_pair
        self.calls += 1
        return self.value if position in self.positions else modal_assurance_criterion(*args, **kwargs)


class NonFiniteMacTests(_Setup, unittest.TestCase):
    def evaluate_with(self, uncertainty, positions, value=float("nan")):
        calls = 1 + len(perturbation_set(uncertainty)[0])
        with patch.object(registration_uncertainty, "modal_assurance_criterion",
                          side_effect=_InvalidMac(positions, calls, value)):
            return self.evaluate(uncertainty)

    def test_invalid_perturbation_is_recorded_and_excluded(self):
        for value in (float("nan"), float("inf"), None):
            with self.subTest(value=value):
                report = self.evaluate_with(GeometryUncertainty(1.0, 0.005, 0.5), {1}, value)
                for pair in report.pairs:
                    self.assertEqual(pair.invalid_perturbations, ("+translation_x",))
                    self.assertEqual(dict(pair.per_perturbation)["+translation_x"], None)
                    self.assertFalse(pair.complete)
                    for bound in (pair.minimum_mac, pair.maximum_mac):
                        self.assertTrue(np.isfinite(bound))
                # Incomplete evidence: not "not limited".
                self.assertIs(report.status, UncertaintyStatus.PARTIAL)
                self.assertIsNone(report.registration_limited)

    def test_invalid_nominal_mac_cannot_cross_or_clear(self):
        report = self.evaluate_with(GeometryUncertainty(1.0, 0.005, 0.5), {0})
        for pair in report.pairs:
            self.assertIsNone(pair.nominal_mac)
            self.assertFalse(pair.crosses_threshold)
        self.assertIsNone(report.registration_limited)

    def test_all_perturbations_invalid(self):
        report = self.evaluate_with(GeometryUncertainty(1.0, 0.005, 0.5), set(range(1, 9)))
        for pair in report.pairs:
            self.assertEqual(len(pair.invalid_perturbations), 8)
            self.assertEqual(pair.minimum_mac, pair.nominal_mac)
            self.assertFalse(pair.crosses_threshold)
        self.assertIsNone(report.registration_limited)


class NonFiniteMacCrossingTests(_Setup, unittest.TestCase):
    WAVES = 9.0

    def test_real_crossing_is_still_conclusive(self):
        uncertainty = GeometryUncertainty(6.0, 0.005, 0.5)
        calls = 1 + len(perturbation_set(uncertainty)[0])
        with patch.object(registration_uncertainty, "modal_assurance_criterion",
                          side_effect=_InvalidMac({8}, calls)):  # "-rotation" invalid
            report = self.evaluate(uncertainty)
        self.assertIs(report.status, UncertaintyStatus.PARTIAL)
        self.assertTrue(any(pair.crosses_threshold for pair in report.pairs))
        self.assertIs(report.registration_limited, True)


if __name__ == "__main__":
    unittest.main()
