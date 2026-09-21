from pathlib import Path
import sys
import unittest

import numpy as np
from scipy import sparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from services.identifiability_service import (
    ParameterPrecisionRequirement,
    analyze_identifiability,
)
from services.inverse_solver import StageAParameterBounds
from services.matrix_model_service import AbaqusDof, StageAAffineBasis, StageAMatrixParameters
from services.stage_a_identification_service import (
    ModelValidationEvidence,
    assess_model_validation_evidence,
    stage_a_basis_identity,
)
from services.uncertainty_service import local_linear_covariance


class PracticalPrecisionGateTests(unittest.TestCase):
    def test_equal_condition_numbers_can_have_opposite_precision_outcomes(self):
        requirements = {
            name: ParameterPrecisionRequirement(10.0, coordinate="scaled")
            for name in ("p1", "p2")
        }
        well_scaled = analyze_identifiability(
            np.eye(2), ("p1", "p2"), dimensionless=True,
            precision_requirements=requirements,
        )
        tiny = analyze_identifiability(
            1.0e-8 * np.eye(2), ("p1", "p2"), dimensionless=True,
            precision_requirements=requirements,
        )
        self.assertEqual(well_scaled.condition_number, tiny.condition_number)
        self.assertTrue(well_scaled.overall_practical_identifiability)
        self.assertFalse(tiny.overall_practical_identifiability)
        self.assertTrue(tiny.structurally_identifiable)
        self.assertTrue(tiny.directionally_separable)
        self.assertFalse(tiny.practically_precise_enough)

    def test_zero_D12_uses_declared_absolute_scale_not_relative_to_estimate(self):
        result = analyze_identifiability(
            np.asarray([[2.0]]), ("D12",), dimensionless=True,
            precision_requirements={
                "D12": ParameterPrecisionRequirement(
                    1.0, coordinate="physical", reference_scale=10.0
                )
            },
            physical_parameter_scales={"D12": 1.0},
        )
        assessment = result.precision_assessments[0]
        self.assertEqual(assessment.status, "PASS")
        self.assertAlmostEqual(assessment.physical_standard_deviation, 0.5)
        self.assertAlmostEqual(assessment.achieved_fraction_of_reference, 0.05)


class NullspaceUncertaintyTests(unittest.TestCase):
    def test_unobservable_parameter_never_gets_zero_uncertainty(self):
        result = local_linear_covariance(np.diag([1.0, 0.0]), ("observed", "missing"))
        self.assertEqual(result.parameter_statuses["observed"], "OBSERVABLE")
        self.assertEqual(result.parameter_statuses["missing"], "UNOBSERVABLE")
        self.assertTrue(np.isinf(result.standard_deviations[1]))
        self.assertIsNone(result.intervals_95["missing"])
        np.testing.assert_allclose(result.nullspace_basis[:, 0], [0.0, 1.0])

    def test_mixed_null_direction_is_explicitly_partial(self):
        result = local_linear_covariance(np.asarray([[1.0, 1.0]]), ("a", "b"))
        self.assertEqual(result.parameter_statuses["a"], "PARTIALLY_OBSERVABLE")
        self.assertEqual(result.parameter_statuses["b"], "PARTIALLY_OBSERVABLE")
        self.assertIsNone(result.intervals_95["a"])
        self.assertIsNone(result.intervals_95["b"])


class ValidationEvidenceIdentityTests(unittest.TestCase):
    def basis(self, first_entry=2.0):
        parameters = StageAMatrixParameters(10.0, 2.0, 4.0)
        return StageAAffineBasis(
            reference_parameters=parameters,
            reference_stiffness=sparse.diags([first_entry, 3.0], format="csr"),
            basis_matrices=(
                sparse.diags([0.1, 0.0], format="csr"),
                sparse.diags([0.0, 0.1], format="csr"),
                sparse.diags([0.05, 0.05], format="csr"),
            ),
            mass=sparse.eye(2, format="csr"),
            dofs=(AbaqusDof(1, 1), AbaqusDof(2, 1)),
        )

    def test_evidence_is_accepted_only_for_matching_basis_identity(self):
        basis = self.basis()
        identity = stage_a_basis_identity(basis)
        evidence = ModelValidationEvidence(
            specimen_model_identifier="SP15",
            basis_km_hash=identity["basis_km_hash"],
            dof_mapping_hash=identity["dof_mapping_hash"],
            validated_parameter_domain={
                "D11": (8.0, 16.0),
                "D66": (2.0, 8.0),
                "coupling_ratio": (-0.2, 0.4),
            },
            validation_points=({"name": "reference"},),
            observed_errors={"relative_frequency": 1.0e-5},
            thresholds={"relative_frequency": 1.0e-4},
            campaign_identifier="fixture",
        )
        bounds = StageAParameterBounds(
            D11=(8.0, 16.0), D66=(2.0, 8.0), coupling_ratio=(-0.2, 0.4)
        )
        matched = assess_model_validation_evidence(
            evidence, basis, physical_specimen_id="SP15", parameter_bounds=bounds
        )
        mismatched = assess_model_validation_evidence(
            evidence, self.basis(first_entry=2.1),
            physical_specimen_id="SP15", parameter_bounds=bounds,
        )
        self.assertEqual(matched["status"], "PASS")
        self.assertTrue(matched["applicable"])
        self.assertEqual(mismatched["status"], "NOT_VALIDATED_FOR_THIS_MODEL")
        self.assertIn("basis_km_hash", mismatched["mismatches"])

        outside_domain = assess_model_validation_evidence(
            evidence,
            basis,
            physical_specimen_id="SP15",
            parameter_bounds=StageAParameterBounds(
                D11=(7.0, 16.0),
                D66=(2.0, 8.0),
                coupling_ratio=(-0.2, 0.4),
            ),
        )
        self.assertEqual(outside_domain["status"], "NOT_VALIDATED_FOR_THIS_MODEL")
        self.assertIn("validated_parameter_domain:D11", outside_domain["mismatches"])


if __name__ == "__main__":
    unittest.main()
