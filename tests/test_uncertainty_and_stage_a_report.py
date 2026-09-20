from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest import mock

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.modal_observation import ModalObservation, ObservationUncertainty
from domain.specimen import PhysicalSpecimen, PrimaryMeasurement
from services.inverse_solver import (
    InverseIdentificationResult,
    ModeAssignment,
    PairingResult,
)
from services.stage_a_report_service import (
    APPARENT_FLEXURAL_NOTE,
    StageAReport,
    build_stage_a_report,
)
from services.uncertainty_service import (
    APPARENT_FLEXURAL_LABEL,
    MonteCarloConfiguration,
    MonteCarloResult,
    QuantityStatistics,
    SyntheticTruthCase,
    UncertaintyValidationError,
    apparent_flexural_properties,
    derive_bare_plate_quantities,
    local_linear_covariance,
    perturb_modal_observations,
    run_stage_a_monte_carlo,
    sample_primary_measurements,
    summarize_samples,
    validate_monte_carlo_coverage,
    validate_synthetic_truth_coverage,
)


def _specimen(*, uncertain=True):
    factor = 1.0 if uncertain else 0.0
    return PhysicalSpecimen(
        "SP-01",
        "bare-plate",
        (
            PrimaryMeasurement("m", 0.120, 0.001 * factor, "kg"),
            PrimaryMeasurement("L", 0.30, 0.0005 * factor, "m"),
            PrimaryMeasurement("W", 0.20, 0.0005 * factor, "m"),
            PrimaryMeasurement("h", 0.00045, 0.00001 * factor, "m"),
        ),
    )


def _observations(*, sigma=0.2, missing=False):
    uncertainty = (
        ObservationUncertainty()
        if missing
        else ObservationUncertainty(measurement=sigma, setup=sigma / 2.0)
    )
    return (
        ModalObservation(
            observation_id="obs-2",
            physical_specimen_id="SP-01",
            test_run_id="run-1",
            fe_mode_id=2,
            experimental_mode_id=2,
            fe_frequency_hz=100.0,
            experimental_frequency_hz=100.0,
            mac=0.99,
            uncertainty=uncertainty,
        ),
    )


def _inverse(realisation, *, success=True):
    frequency = realisation.observations[0].experimental_frequency_hz
    d11 = 10.0 * (frequency / 100.0) ** 2
    pairing = PairingResult((ModeAssignment("obs-2", 2),), "synthetic fast matrix")
    return InverseIdentificationResult(
        fitted_parameters={"D11": d11, "D12": 2.0, "D66": 5.0},
        fixed_parameters={},
        transformed_parameters={},
        initial_parameters={"D11": 9.0, "D12": 2.0, "D66": 4.0},
        objective_initial=1.0,
        objective_global=0.1,
        objective_final=(frequency / 100.0 - 1.0) ** 2,
        residuals_initial=np.asarray([0.1]),
        residuals_final=np.asarray([0.0]),
        predicted_frequencies_initial=np.asarray([99.0]),
        predicted_frequencies_final=np.asarray([frequency]),
        experimental_frequencies=np.asarray([frequency]),
        observation_ids=("obs-2",),
        global_evaluations=1,
        global_optimizer_evaluations=1,
        local_iterations=1,
        convergence_history=(),
        pairing_changed_at_optimum=False,
        initial_pairing=pairing,
        global_pairing=pairing,
        final_pairing=pairing,
        excluded_observations=(),
        warnings=(),
        identifiability_metadata_reference="synthetic",
        weighting_mode="diagonal_standard_deviations",
        global_success=success,
        global_stage_acceptable=success,
        global_message="ok" if success else "failed",
        local_success=success,
        local_message="ok" if success else "failed",
        success=success,
    )


class StageAPipelineRunnerTests(unittest.TestCase):
    def test_pipeline_runner_forwards_the_factory_affine_basis_unmodified(self):
        # create_stage_a_pipeline_runner has no mass/K logic of its own; it
        # must hand the caller-supplied StageAAffineBasis (mass-dependent or
        # not) straight through to identify_stage_a, which owns
        # reconstruct_mass(). This proves the Monte Carlo/uncertainty fast
        # path does not bypass the corrected mass reconstruction.
        from services import uncertainty_service as uncertainty_module

        sentinel_basis = object()
        captured = {}

        def fake_identify_stage_a(**kwargs):
            captured.update(kwargs)
            return "identification-result"

        def input_factory(realisation):
            return {
                "affine_model": sentinel_basis,
                "comparison": "comparison-object",
                "initial_parameters": "initial-parameters",
                "parameter_bounds": "bounds",
                "requested_parameter_subset": ("D11",),
                "solver_configuration": "solver-config",
                "design_id": "design",
                "physical_specimen_id": "specimen",
                "test_run_id": "run",
            }

        runner = uncertainty_module.create_stage_a_pipeline_runner(input_factory)
        with mock.patch.object(
            uncertainty_module, "identify_stage_a", side_effect=fake_identify_stage_a
        ):
            result = runner(mock.Mock())

        self.assertEqual(result, "identification-result")
        self.assertIs(captured["affine_model"], sentinel_basis)


class PrimarySamplingTests(unittest.TestCase):
    def test_deterministic_seed_and_derived_correlation_are_preserved(self):
        specimen = _specimen()
        first_rng = np.random.default_rng(123)
        second_rng = np.random.default_rng(123)
        first = sample_primary_measurements(specimen, first_rng)
        second = sample_primary_measurements(specimen, second_rng)
        self.assertEqual(first, second)
        derived = derive_bare_plate_quantities(specimen, first)
        self.assertAlmostEqual(
            derived["areal_mass"], first["m"] / (first["L"] * first["W"])
        )
        self.assertNotIn("areal_mass", first)

    def test_derived_primary_measurement_cannot_be_sampled_independently(self):
        with self.assertRaisesRegex(ValueError, "derived"):
            PrimaryMeasurement("mu", 2.0, 0.1)

    def test_fixed_measurement_uses_zero_uncertainty(self):
        measurement = PrimaryMeasurement(
            "h", 0.45, 0.0, "mm", metadata={"distribution": "fixed"}
        )
        specimen = PhysicalSpecimen("SP", "D", (measurement,))
        sample = sample_primary_measurements(specimen, np.random.default_rng(1))
        self.assertEqual(sample["h"], 0.45)

    def test_missing_frequency_sigma_has_no_silent_default(self):
        with self.assertRaisesRegex(UncertaintyValidationError, "explicitly enable"):
            perturb_modal_observations(
                _observations(missing=True), np.random.default_rng(1)
            )
        unweighted = perturb_modal_observations(
            _observations(missing=True), np.random.default_rng(1), allow_unweighted=True
        )
        self.assertEqual(unweighted[0].experimental_frequency_hz, 100.0)
        with self.assertRaisesRegex(UncertaintyValidationError, "explicitly enable"):
            run_stage_a_monte_carlo(
                _specimen(),
                _observations(missing=True),
                _inverse,
                MonteCarloConfiguration(sample_count=2),
            )


class MonteCarloTests(unittest.TestCase):
    def test_seed_reproducibility(self):
        configuration = MonteCarloConfiguration(sample_count=12, random_seed=44)
        first = run_stage_a_monte_carlo(_specimen(), _observations(), _inverse, configuration)
        second = run_stage_a_monte_carlo(_specimen(), _observations(), _inverse, configuration)
        self.assertEqual(
            [item.primary_measurements for item in first.samples],
            [item.primary_measurements for item in second.samples],
        )
        self.assertEqual(
            [item.fitted_parameters for item in first.samples],
            [item.fitted_parameters for item in second.samples],
        )

    def test_thickness_uncertainty_propagates_with_inverse_cube_direction(self):
        thinner = apparent_flexural_properties(10.0, 2.0, 5.0, 0.4e-3)
        thicker = apparent_flexural_properties(10.0, 2.0, 5.0, 0.5e-3)
        self.assertGreater(thinner.E_flex, thicker.E_flex)
        self.assertAlmostEqual(thinner.E_flex / thicker.E_flex, (0.5 / 0.4) ** 3)
        result = run_stage_a_monte_carlo(
            _specimen(), _observations(sigma=0.0), _inverse,
            MonteCarloConfiguration(sample_count=100, random_seed=8),
        )
        self.assertGreater(
            result.derived_statistics["E_flex"].standard_deviation, 0.0
        )
        self.assertGreater(
            result.thickness_diagnostics["E_flex"].thickness_variance_fraction, 0.0
        )

    def test_zero_uncertainty_collapses_distribution(self):
        result = run_stage_a_monte_carlo(
            _specimen(uncertain=False), _observations(sigma=0.0), _inverse,
            MonteCarloConfiguration(sample_count=8, random_seed=1),
        )
        for statistics in tuple(result.identified_statistics.values()) + tuple(
            result.derived_statistics.values()
        ):
            self.assertEqual(statistics.standard_deviation, 0.0)
            self.assertEqual(statistics.interval_95[0], statistics.interval_95[1])

    def test_failed_solver_samples_are_counted_and_warned(self):
        def runner(realisation):
            if realisation.sample_index == 1:
                raise RuntimeError("synthetic solver failure")
            return _inverse(realisation)

        result = run_stage_a_monte_carlo(
            _specimen(uncertain=False), _observations(sigma=0.0), runner,
            MonteCarloConfiguration(
                sample_count=4, random_seed=1, failure_rate_warning_threshold=0.20
            ),
        )
        self.assertEqual(result.failed_sample_count, 1)
        self.assertEqual(result.successful_sample_count, 3)
        self.assertIn("synthetic solver failure", result.samples[1].failure)
        self.assertTrue(any("failure rate" in item for item in result.warnings))

    def test_percentile_calculation_is_numpy_linear_percentile(self):
        statistics = summarize_samples(range(1, 101), successful=100, failed=2)
        self.assertAlmostEqual(statistics.percentile_2_5, 3.475)
        self.assertAlmostEqual(statistics.percentile_97_5, 97.525)
        self.assertEqual(statistics.failed_sample_count, 2)

    def test_local_covariance_uses_pseudoinverse_for_singular_information(self):
        jacobian = np.asarray([[1.0, 1.0], [2.0, 2.0]])
        result = local_linear_covariance(jacobian, ("a", "b"))
        np.testing.assert_allclose(
            result.covariance, np.linalg.pinv(jacobian.T @ jacobian)
        )
        self.assertIn("pseudoinverse", result.method)


class CoverageAndReportTests(unittest.TestCase):
    def test_concrete_noisy_synthetic_truth_case_has_expected_coverage(self):
        truth = {"D11": 10.0, "D12": 2.0, "D66": 5.0}
        case = SyntheticTruthCase(
            truth=truth,
            nominal_observations=np.asarray([10.0, 2.0, 5.0]),
            observation_standard_deviations=np.asarray([0.2, 0.04, 0.1]),
            estimator=lambda frequencies: dict(zip(truth, frequencies)),
        )
        result = validate_synthetic_truth_coverage(
            case,
            repetitions=100,
            monte_carlo_samples=300,
            tolerance=0.08,
            random_seed=77,
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.successful_experiments, 100)
        self.assertTrue(
            all(0.87 <= value <= 1.0 for value in result.empirical_coverage.values())
        )

    def test_synthetic_coverage_validation(self):
        def experiment(rng, index):
            del rng
            covered = index % 20 != 0
            interval = (-1.0, 1.0) if covered else (1.0, 2.0)
            statistics = QuantityStatistics(
                mean=0.0,
                median=0.0,
                standard_deviation=1.0,
                percentile_2_5=interval[0],
                percentile_97_5=interval[1],
                interval_95=interval,
                successful_sample_count=100,
                failed_sample_count=0,
                convergence_fraction=1.0,
            )
            result = SimpleNamespace(
                identified_statistics={name: statistics for name in ("D11", "D12", "D66")}
            )
            return {"D11": 0.0, "D12": 0.0, "D66": 0.0}, result

        result = validate_monte_carlo_coverage(
            experiment, repetitions=100, tolerance=0.01, random_seed=4
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.empirical_coverage["D11"], 0.95)
        self.assertEqual(result.metadata["validation_level"], 1)

    def test_json_round_trip_text_determinism_and_apparent_label(self):
        monte_carlo = run_stage_a_monte_carlo(
            _specimen(uncertain=False), _observations(sigma=0.0), _inverse,
            MonteCarloConfiguration(sample_count=4, random_seed=1),
        )
        inverse = _inverse(
            SimpleNamespace(observations=_observations(sigma=0.0))
        )
        identification = SimpleNamespace(
            inverse_result=inverse,
            fitted_parameter_subset=("D11", "D12", "D66"),
            recommended_parameter_subset=("D11", "D12", "D66"),
            effective_observation_count=1,
            observations=_observations(sigma=0.0),
            clusters=(),
            excluded_observations=(),
            warnings=(),
            metadata={},
            identifiability=SimpleNamespace(
                parameter_ids=("D11", "D12", "D66"),
                rank=3,
                condition_number=2.0,
                collinearity=SimpleNamespace(gamma=1.2),
                practically_identifiable=True,
                correlation_matrix=np.eye(3),
                deficient_directions=(),
                weighting_mode="diagonal_standard_deviations",
            ),
        )
        report = build_stage_a_report(identification, _specimen(uncertain=False), monte_carlo)
        payload = report.to_json()
        restored = StageAReport.from_json(payload)
        self.assertEqual(restored.to_dict(), report.to_dict())
        self.assertIn("global_success", report.inverse_fit_summary)
        self.assertIn("global_stage_acceptable", report.inverse_fit_summary)
        self.assertEqual(report.to_markdown(), report.to_markdown())
        self.assertIn(APPARENT_FLEXURAL_LABEL, report.to_markdown())
        self.assertIn(APPARENT_FLEXURAL_NOTE, report.to_markdown())


if __name__ == "__main__":
    unittest.main()
