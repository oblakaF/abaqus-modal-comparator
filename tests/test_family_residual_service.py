from pathlib import Path
import inspect
import math
import sys
import unittest
import warnings

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from services.family_residual_service import (
    FamilyIdentityError,
    FamilyIdentityEvidence,
    FamilyIdentityGate,
    FamilyResidualValidationError,
    SP13_FITTED_PARAMETER_IDS,
    SP13_PRIMARY_OBSERVABLE_IDS,
    evaluate_sp13_primary_residual,
    scalar_log_frequency_residual,
    two_mode_subspace_evidence,
)
from services.family_residual_service import _two_mode_basis
from services.modal_cluster_service import _orthonormal_basis


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



IDS = dict(baseline_member_ids=(8, 9), candidate_member_ids=(8, 9))


def _evidence(baseline, candidate):
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # a ComplexWarning would mean truncation
        return two_mode_subspace_evidence(baseline, candidate, **IDS)


def _family_with_singular_values(second, size=6, seed=3):
    """A real 2 x size family whose singular values are exactly (1, second)."""
    rng = np.random.default_rng(seed)
    left, _ = np.linalg.qr(rng.standard_normal((size, 2)))
    right, _ = np.linalg.qr(rng.standard_normal((2, 2)))
    return (left @ np.diag([1.0, second]) @ right.T).T


class ComplexRankAwareFamilySubspaceTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(11)
        self.complex_family = rng.standard_normal((2, 5)) + 1j * rng.standard_normal((2, 5))
        self.real_family = rng.standard_normal((2, 5))

    # A
    def test_real_family_matches_previous_real_qr_result(self):
        candidate = self.real_family + 0.3 * np.random.default_rng(5).standard_normal((2, 5))
        evidence = _evidence(self.real_family, candidate)
        qb = np.linalg.qr(self.real_family.T)[0][:, :2]
        qc = np.linalg.qr(candidate.T)[0][:, :2]
        previous = np.linalg.svd(qb.T @ qc, compute_uv=False)
        np.testing.assert_allclose(
            evidence.squared_canonical_correlations, np.clip(previous**2, 0.0, 1.0), atol=1e-12
        )
        np.testing.assert_allclose(
            evidence.principal_angles_degrees,
            np.degrees(np.arccos(np.clip(previous, -1.0, 1.0))),
            atol=1e-6,
        )
        integers = _evidence(np.asarray([[1, 0, 1, 0], [0, 1, 0, 1]]), np.asarray([[1, 0, 1, 0], [0, 1, 0, 1]]))
        np.testing.assert_allclose(integers.squared_canonical_correlations, (1.0, 1.0), atol=1e-12)

    # B / J
    def test_imaginary_components_are_preserved(self):
        baseline = np.asarray([[1, 0, 0], [0, 1, 0]], dtype=complex)
        candidate = np.asarray([[1, 0, 0], [0, 1, 1j]], dtype=complex)
        # Real parts are identical: a float cast would report two zero angles.
        evidence = _evidence(baseline, candidate)
        self.assertAlmostEqual(evidence.principal_angles_degrees[0], 0.0, places=6)
        self.assertAlmostEqual(evidence.principal_angles_degrees[1], 45.0, places=9)
        self.assertAlmostEqual(min(evidence.squared_canonical_correlations), 0.5, places=12)

    # C
    def test_global_and_per_mode_complex_phase_do_not_change_the_subspace(self):
        phases = np.exp(1j * np.asarray([[0.4], [-2.1]]))
        for candidate in (np.exp(0.9j) * self.complex_family, phases * self.complex_family):
            evidence = _evidence(self.complex_family, candidate)
            np.testing.assert_allclose(evidence.squared_canonical_correlations, (1.0, 1.0), atol=1e-12)
            self.assertLess(evidence.maximum_principal_angle_degrees, 1e-5)

    # D
    def test_complex_basis_is_orthonormal_under_hermitian_product(self):
        basis = _two_mode_basis(self.complex_family, "Test")
        self.assertEqual(basis.shape, (5, 2))
        np.testing.assert_allclose(basis.conj().T @ basis, np.eye(2), atol=1e-12)
        self.assertFalse(np.allclose(basis.T @ basis, np.eye(2), atol=1e-6))

    # E / F / H
    def test_rank_deficient_families_are_refused(self):
        v = self.complex_family[0]
        cases = {
            "duplicate real": np.vstack([self.real_family[0], self.real_family[0]]),
            "complex multiple": np.vstack([v, (1 + 2j) * v]),
            "one zero vector": np.vstack([v, np.zeros_like(v)]),
        }
        for name, family in cases.items():
            with self.subTest(name):
                with self.assertRaisesRegex(FamilyResidualValidationError, "numerical rank 1, not 2"):
                    _evidence(family, self.complex_family)
                with self.assertRaisesRegex(FamilyResidualValidationError, "Candidate.*rank 1"):
                    _evidence(self.complex_family, family)
        with self.assertRaisesRegex(FamilyResidualValidationError, "at least one non-zero vector"):
            _evidence(np.zeros((2, 5)), self.complex_family)

    # G
    def test_independent_family_has_full_rank(self):
        for family in (self.real_family, self.complex_family):
            self.assertEqual(_two_mode_basis(family, "Test").shape[1], 2)
            evidence = _evidence(family, family)
            np.testing.assert_allclose(evidence.squared_canonical_correlations, (1.0, 1.0), atol=1e-12)

    # I
    def test_near_dependence_follows_the_modal_cluster_rank_rule(self):
        tolerance = 6 * np.finfo(float).eps  # max(shape) * eps * sigma_max, sigma_max = 1
        for factor, expected_rank in ((10.0, 2), (0.1, 1)):
            with self.subTest(factor=factor):
                family = _family_with_singular_values(factor * tolerance)
                self.assertEqual(_orthonormal_basis(family.T, None).shape[1], expected_rank)
                if expected_rank == 2:
                    self.assertEqual(_two_mode_basis(family, "Test").shape[1], 2)
                else:
                    with self.assertRaises(FamilyResidualValidationError):
                        _two_mode_basis(family, "Test")

    # K
    def test_canonical_correlations_match_an_independent_hermitian_projection(self):
        baseline = np.asarray([[1.0, 1j, 0.0], [0.0, 0.0, 1.0]]) / np.asarray([[math.sqrt(2)], [1.0]])
        candidate = np.asarray([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=complex)
        columns = baseline.T
        projector = columns @ np.linalg.inv(columns.conj().T @ columns) @ columns.conj().T
        coupling = candidate.conj() @ projector @ candidate.T  # C^H P C for orthonormal C
        expected = np.sort(np.linalg.eigvalsh(coupling))[::-1]
        np.testing.assert_allclose(expected, (1.0, 0.0), atol=1e-12)
        evidence = _evidence(baseline, candidate)
        np.testing.assert_allclose(evidence.squared_canonical_correlations, expected, atol=1e-12)
        np.testing.assert_allclose(evidence.principal_angles_degrees, (0.0, 90.0), atol=1e-6)
        for value in evidence.squared_canonical_correlations + evidence.principal_angles_degrees:
            self.assertIsInstance(value, float)

    # L
    def test_public_api_and_input_validation_are_unchanged(self):
        signature = inspect.signature(two_mode_subspace_evidence)
        self.assertEqual(
            list(signature.parameters),
            ["baseline_mode_vectors", "candidate_mode_vectors", "baseline_member_ids", "candidate_member_ids"],
        )
        evidence = _evidence(self.complex_family, self.complex_family)
        self.assertIsInstance(evidence, FamilyIdentityEvidence)
        self.assertEqual(evidence.baseline_member_ids, (8, 9))
        with self.assertRaisesRegex(FamilyResidualValidationError, "finite"):
            _evidence(np.asarray([[1.0, np.nan, 0.0], [0.0, 1.0, 1j]]), self.complex_family[:, :3])
        with self.assertRaisesRegex(FamilyResidualValidationError, "same 2 x N shape"):
            _evidence(self.complex_family, self.complex_family[:, :4])
        with self.assertRaisesRegex(FamilyResidualValidationError, "numeric"):
            _evidence(np.asarray([["a", "b"], ["c", "d"]]), self.real_family[:, :2])


if __name__ == "__main__":
    unittest.main()
