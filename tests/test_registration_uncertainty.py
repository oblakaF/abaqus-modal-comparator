"""M2.4 registration uncertainty diagnostic (SPEC §11): physical perturbations only; never a best MAC."""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.specimen_manifest import GeometryUncertainty
from m2_support import PLATE_X, PLATE_Y, experiment, fixture_for, passport_for, synthetic_fe
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

    def setUp(self):
        self.fe = synthetic_fe()
        self.experiment = experiment(shapes=lambda n, p: wavy(n, p, self.WAVES))
        self.passport = passport_for(self.fe)
        result = build_physical_registration(self.passport, roots={}, fe_geometry=self.fe,
                                             experimental=(self.experiment, fixture_for(self.fe)))
        self.registration, self.surface = result.registration, result.surface_node_ids
        top = [i for i, node in enumerate(self.fe.node_ids) if node.startswith("TOP:")]
        self.fe_modes = {}
        for number in (1, 2):
            values = {}
            for index in top:
                vector = np.zeros(3)
                vector[2] = wavy(number, self.fe.coordinates[index:index + 1], self.WAVES)[0]
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


if __name__ == "__main__":
    unittest.main()
