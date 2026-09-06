from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.modal_observation import ObservationUncertainty
from services.identifiability_service import (
    analyze_identifiability,
    collinearity_index,
    combine_independent_uncertainties,
    whiten_sensitivity,
)


class WhiteningTests(unittest.TestCase):
    def test_equal_sigma_preserves_relative_structure(self):
        sensitivity = np.array([[1.0, 2.0], [3.0, 5.0]])
        whitened = whiten_sensitivity(
            sensitivity,
            standard_deviations=(2.0, 2.0),
            parameter_ids=("p1", "p2"),
        )
        np.testing.assert_allclose(whitened.sensitivity, sensitivity / 2.0)
        self.assertEqual(whitened.mode, "diagonal_standard_deviations")

    def test_larger_sigma_reduces_that_observations_fisher_contribution(self):
        sensitivity = np.eye(2)
        whitened = whiten_sensitivity(
            sensitivity,
            standard_deviations=(1.0, 10.0),
            parameter_ids=("p1", "p2"),
        )
        fisher = whitened.sensitivity.T @ whitened.sensitivity
        np.testing.assert_allclose(fisher, np.diag([1.0, 0.01]))

    def test_covariance_input_applies_inverse_square_root(self):
        sensitivity = np.eye(2)
        covariance = np.diag([4.0, 9.0])
        result = whiten_sensitivity(
            sensitivity,
            covariance=covariance,
            parameter_ids=("p1", "p2"),
        )
        np.testing.assert_allclose(result.sensitivity, np.diag([0.5, 1.0 / 3.0]))
        np.testing.assert_allclose(result.covariance, covariance)
        self.assertEqual(result.mode, "diagonal_covariance")

    def test_correlated_covariance_is_supported_without_independence_claim(self):
        covariance = np.array([[2.0, 0.5], [0.5, 1.0]])
        result = whiten_sensitivity(
            np.eye(2),
            covariance=covariance,
            parameter_ids=("p1", "p2"),
        )
        np.testing.assert_allclose(
            result.sensitivity.T @ result.sensitivity,
            np.linalg.inv(covariance),
        )
        self.assertEqual(result.mode, "full_covariance")
        self.assertEqual(result.assumptions, ())

    def test_missing_and_invalid_sigma_are_explicit(self):
        sensitivity = np.eye(2)
        with self.assertRaisesRegex(ValueError, "uncertainty is missing"):
            whiten_sensitivity(sensitivity, parameter_ids=("p1", "p2"))
        unweighted = whiten_sensitivity(
            sensitivity,
            parameter_ids=("p1", "p2"),
            allow_unweighted=True,
        )
        self.assertEqual(unweighted.mode, "unweighted")
        with self.assertRaisesRegex(ValueError, "positive and finite"):
            whiten_sensitivity(
                sensitivity,
                standard_deviations=(1.0, 0.0),
                parameter_ids=("p1", "p2"),
            )

    def test_uncertainty_components_remain_separate_and_assumption_is_recorded(self):
        components = (
            ObservationUncertainty(measurement=1.0, setup=2.0, manufacturing=2.0),
        )
        standard_deviations, preserved = combine_independent_uncertainties(
            components, observation_scales=(10.0,)
        )
        np.testing.assert_allclose(standard_deviations, [0.3])
        self.assertEqual(preserved, components)
        result = whiten_sensitivity(
            np.array([[1.0, 2.0]]),
            uncertainty_components=components,
            observation_scales=(10.0,),
            parameter_ids=("p1", "p2"),
        )
        self.assertEqual(result.uncertainty_components, components)
        self.assertTrue(
            result.metadata["component_variances_combined_as_independent"]
        )
        self.assertIn("independent", result.assumptions[0])


class IdentifiabilityTests(unittest.TestCase):
    def analyze(self, sensitivity, parameter_ids):
        whitened = whiten_sensitivity(
            np.asarray(sensitivity, dtype=float),
            standard_deviations=np.ones(len(sensitivity)),
            parameter_ids=parameter_ids,
        )
        return analyze_identifiability(whitened)

    def test_orthogonal_columns_are_full_rank_and_well_conditioned(self):
        result = self.analyze(np.eye(2), ("p1", "p2"))
        self.assertEqual(result.rank, 2)
        self.assertAlmostEqual(result.condition_number, 1.0)
        self.assertAlmostEqual(result.collinearity.gamma, 1.0)
        self.assertTrue(result.practically_identifiable)
        np.testing.assert_allclose(result.fisher_information, np.eye(2))
        np.testing.assert_allclose(result.covariance_proxy, np.eye(2))

    def test_identical_columns_are_rank_deficient_and_use_pseudoinverse(self):
        result = self.analyze(
            [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]], ("p1", "p2")
        )
        self.assertEqual(result.rank, 1)
        self.assertEqual(result.condition_number, float("inf"))
        self.assertTrue(np.isfinite(result.covariance_proxy).all())
        self.assertTrue(result.deficient_directions[0].numerical_null_direction)
        np.testing.assert_allclose(
            np.abs(result.deficient_directions[0].coefficients),
            [1.0 / np.sqrt(2.0), 1.0 / np.sqrt(2.0)],
        )

    def test_nearly_collinear_columns_raise_advisory_warnings(self):
        result = self.analyze([[1.0, 1.0], [0.0, 1.0e-3]], ("p1", "p2"))
        self.assertGreater(result.condition_number, 100.0)
        self.assertGreater(result.collinearity.gamma, 20.0)
        self.assertFalse(result.practically_identifiable)
        self.assertTrue(any("condition number" in warning for warning in result.warnings))
        self.assertTrue(any("Collinearity" in warning for warning in result.warnings))

    def test_subset_search_recovers_D11_D66_from_deficient_full_model(self):
        sensitivity = np.array(
            [
                [1.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
                [1.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
            ]
        )
        result = self.analyze(sensitivity, ("D11", "D12", "D66"))
        self.assertEqual(result.rank, 2)
        self.assertEqual(
            result.best_identifiable_subset.parameter_ids, ("D11", "D66")
        )
        self.assertTrue(result.best_identifiable_subset.admissible)
        direction = next(
            item for item in result.deficient_directions if item.numerical_null_direction
        )
        self.assertAlmostEqual(abs(direction.parameter_loadings["D11"]), 1.0 / np.sqrt(2.0))
        self.assertAlmostEqual(abs(direction.parameter_loadings["D12"]), 1.0 / np.sqrt(2.0))
        self.assertAlmostEqual(direction.parameter_loadings["D66"], 0.0)

    def test_plain_array_requires_explicit_dimensionless_confirmation(self):
        with self.assertRaisesRegex(ValueError, "dimensionless"):
            analyze_identifiability(np.eye(2), ("p1", "p2"))
        result = analyze_identifiability(
            np.eye(2), ("p1", "p2"), dimensionless=True
        )
        self.assertEqual(result.rank, 2)

    def test_collinearity_definition_uses_normalized_columns(self):
        first = collinearity_index(np.eye(2), ("p1", "p2"))
        second = collinearity_index(
            np.array([[1000.0, 0.0], [0.0, 0.001]]), ("p1", "p2")
        )
        self.assertAlmostEqual(first.gamma, second.gamma)
        self.assertEqual(first.normalization, "unit_l2_sensitivity_columns")


if __name__ == "__main__":
    unittest.main()
