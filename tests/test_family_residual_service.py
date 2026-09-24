from pathlib import Path
import inspect
import math
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from services.family_residual_service import (
    FamilyIdentityError,
    FamilyIdentityEvidence,
    FamilyIdentityGate,
    SP13_FITTED_PARAMETER_IDS,
    SP13_PRIMARY_OBSERVABLE_IDS,
    evaluate_sp13_primary_residual,
    scalar_log_frequency_residual,
    two_mode_subspace_evidence,
)


class FamilyResidualServiceTests(unittest.TestCase):
    def setUp(self):
        self.baseline = np.asarray([[1.0, 0.0, 1.0, 0.0], [0.0, 1.0, 0.0, 1.0]])
        self.evidence = two_mode_subspace_evidence(
            self.baseline, self.baseline,
            baseline_member_ids=(8, 9), candidate_member_ids=(8, 9),
        )
        self.gate = FamilyIdentityGate(0.8, math.degrees(math.acos(math.sqrt(0.8))))
        self.kwargs = dict(
            fe_A7_hz=31.0, fe_A12_hz=148.0, fe_A8_A9_hz=(74.0, 81.0),
            experimental_A7_hz=31.4, experimental_A12_hz=147.5,
            experimental_A8_A9_hz=(74.2, 80.9),
            standard_deviations=(0.0023, 0.0023, 0.0016, 0.00014),
            family_identity_evidence=self.evidence, family_identity_gate=self.gate,
        )

    def test_fe_family_swap_leaves_objective_identical(self):
        first = evaluate_sp13_primary_residual(**self.kwargs)
        swapped = dict(self.kwargs, fe_A8_A9_hz=self.kwargs["fe_A8_A9_hz"][::-1])
        second = evaluate_sp13_primary_residual(**swapped)
        np.testing.assert_array_equal(first.residuals, second.residuals)
        self.assertEqual(first.objective, second.objective)

    def test_experimental_family_swap_leaves_objective_identical(self):
        first = evaluate_sp13_primary_residual(**self.kwargs)
        swapped = dict(
            self.kwargs,
            experimental_A8_A9_hz=self.kwargs["experimental_A8_A9_hz"][::-1],
        )
        second = evaluate_sp13_primary_residual(**swapped)
        np.testing.assert_array_equal(first.residuals, second.residuals)
        self.assertEqual(first.objective, second.objective)

    def test_basis_rotation_preserves_subspace_gate(self):
        angle = 0.731
        rotation = np.asarray(
            [[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]]
        )
        evidence = two_mode_subspace_evidence(
            self.baseline, rotation @ self.baseline,
            baseline_member_ids=(8, 9), candidate_member_ids=(11, 12),
        )
        self.assertTrue(self.gate.accepts(evidence))
        self.assertGreater(min(evidence.squared_canonical_correlations), 1.0 - 1e-12)

    def test_family_identity_loss_invalidates_evaluation(self):
        failed = FamilyIdentityEvidence((0.79, 0.78), (27.0, 28.0), (8, 9), (18, 19))
        with self.assertRaises(FamilyIdentityError):
            evaluate_sp13_primary_residual(
                **dict(self.kwargs, family_identity_evidence=failed)
            )

    def test_scalar_residual_is_backward_compatible_log_ratio(self):
        self.assertEqual(scalar_log_frequency_residual(31.0, 30.0), math.log(31.0/30.0))

    def test_subspace_metrics_are_not_objective_inputs(self):
        signature = inspect.signature(evaluate_sp13_primary_residual)
        self.assertNotIn("mac", signature.parameters)
        result = evaluate_sp13_primary_residual(**self.kwargs)
        self.assertFalse(result.log_record()["subspace_metrics_used_in_objective"])

    def test_a15_is_absent_from_primary_observable_set(self):
        self.assertEqual(
            SP13_PRIMARY_OBSERVABLE_IDS,
            ("A7", "A12", "A8_A9_CENTER", "A8_A9_SPLITTING"),
        )
        self.assertFalse(any("A15" in item for item in SP13_PRIMARY_OBSERVABLE_IDS))

    def test_only_face_parameters_are_fitted(self):
        self.assertEqual(
            SP13_FITTED_PARAMETER_IDS,
            ("effective_face_Ex", "effective_face_Ey", "effective_face_Gxy"),
        )
        self.assertFalse(any("core" in item.lower() for item in SP13_FITTED_PARAMETER_IDS))

    def test_log_record_contains_members_features_and_gate_evidence(self):
        record = evaluate_sp13_primary_residual(**self.kwargs).log_record()
        for key in (
            "fe_family_member_frequencies_hz", "fe_family_center",
            "fe_family_squared_splitting", "minimum_squared_canonical_correlation",
            "maximum_principal_angle_degrees", "candidate_family_member_ids",
        ):
            self.assertIn(key, record)


if __name__ == "__main__":
    unittest.main()
