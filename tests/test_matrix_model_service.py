import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np
from scipy import sparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from services.abaqus_shell_section import (
    SectionStiffnessBlock,
    StageAShellSectionConfiguration,
    TransverseShearStiffness,
)
from services.matrix_model_service import (
    AbaqusDof,
    AbaqusMatrixFormatError,
    AbaqusMatrixGenerationError,
    AbaqusMatrixJobResult,
    AbaqusMatrixPair,
    DirectAbaqusEvaluation,
    MatrixModelError,
    StageAAbaqusPointEvaluationError,
    StageAAffineBasis,
    StageAMatrixParameters,
    build_stage_a_affine_basis,
    evaluate_stage_a_abaqus_point,
    is_sparse_symmetric,
    read_abaqus_matrix_input,
    read_abaqus_matrix_pair,
    render_stage_a_matrix_deck,
    run_matrix_decomposition_proof_test,
    solve_generalized_eigenproblem,
    stage_a_matrix_configurations,
)


DOFS = (AbaqusDof(1, 1), AbaqusDof(2, 1), AbaqusDof(3, 1))


def diagonal_pair(stiffness_diagonal, mass_diagonal=(1.0, 1.0, 1.0)):
    return AbaqusMatrixPair(
        stiffness=sparse.diags(stiffness_diagonal, format="csr"),
        mass=sparse.diags(mass_diagonal, format="csr"),
        dofs=DOFS,
    )


class AbaqusMatrixParserTests(unittest.TestCase):
    def test_triangular_entries_are_mirrored_once_and_zeros_keep_dof_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "small_STIF1.mtx"
            path.write_text(
                "1,1, 1,1, 2.0\n"
                "2,1, 1,1, 3.0\n"
                "2,1, 2,1, 5.0\n"
                "3,6, 3,6, 0.0\n",
                encoding="ascii",
            )
            loaded = read_abaqus_matrix_input(path)

        self.assertEqual(
            loaded.dofs,
            (AbaqusDof(1, 1), AbaqusDof(2, 1), AbaqusDof(3, 6)),
        )
        np.testing.assert_allclose(
            loaded.matrix.toarray(),
            [[2.0, 3.0, 0.0], [3.0, 5.0, 0.0], [0.0, 0.0, 0.0]],
        )
        self.assertEqual(loaded.matrix.nnz, 4)

    def test_pair_uses_union_of_stiffness_and_mass_dofs(self):
        with tempfile.TemporaryDirectory() as directory:
            stiffness_path = Path(directory) / "K.mtx"
            mass_path = Path(directory) / "M.mtx"
            stiffness_path.write_text(
                "1,1,1,1,4\n2,1,2,1,9\n", encoding="ascii"
            )
            mass_path.write_text(
                "1,1,1,1,1\n3,6,3,6,0\n", encoding="ascii"
            )
            pair = read_abaqus_matrix_pair(stiffness_path, mass_path)

        self.assertEqual(pair.stiffness.shape, (3, 3))
        self.assertEqual(pair.mass.shape, (3, 3))
        self.assertEqual(pair.dofs[-1], AbaqusDof(3, 6))

    def test_duplicate_and_mirrored_duplicate_entries_fail(self):
        for duplicate in (
            "1,1,2,1,3\n1,1,2,1,3\n",
            "1,1,2,1,3\n2,1,1,1,3\n",
        ):
            with self.subTest(duplicate=duplicate), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "duplicate.mtx"
                path.write_text(duplicate, encoding="ascii")
                with self.assertRaisesRegex(AbaqusMatrixFormatError, "duplicate symmetric"):
                    read_abaqus_matrix_input(path)

    def test_malformed_rows_and_nonfinite_values_fail(self):
        for text in ("1,1,1,1\n", "1,1,1,1,nan\n", "node,1,1,1,2\n"):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "bad.mtx"
                path.write_text(text, encoding="ascii")
                with self.assertRaises(AbaqusMatrixFormatError):
                    read_abaqus_matrix_input(path)

    def test_sparse_symmetry_check_does_not_require_dense_conversion(self):
        symmetric = sparse.csr_matrix([[2.0, 3.0], [3.0, 5.0]])
        nonsymmetric = sparse.csr_matrix([[2.0, 3.0], [0.0, 5.0]])
        self.assertTrue(is_sparse_symmetric(symmetric))
        self.assertFalse(is_sparse_symmetric(nonsymmetric))


class StageAAffineBasisTests(unittest.TestCase):
    def setUp(self):
        self.reference = StageAMatrixParameters(10.0, 2.0, 3.0)
        self.configurations = stage_a_matrix_configurations(
            self.reference, relative_step=0.05
        )
        self.constant = np.array([7.0, 11.0, 13.0])
        self.contributions = (
            np.array([2.0, 3.0, 5.0]),
            np.array([0.5, -0.25, 0.75]),
            np.array([4.0, 1.0, 2.0]),
        )

    def matrices(self, parameters, mass=(1.0, 2.0, 3.0)):
        diagonal = self.constant.copy()
        for value, contribution in zip(parameters.values, self.contributions):
            diagonal += value * contribution
        return diagonal_pair(diagonal, mass)

    def build_basis(self):
        return build_stage_a_affine_basis(
            self.reference,
            self.matrices(self.reference),
            [
                (parameters, self.matrices(parameters))
                for parameters in self.configurations[1:]
            ],
        )

    def test_configurations_are_reference_plus_three_deterministic_admissible_points(self):
        self.assertEqual(len(self.configurations), 4)
        self.assertEqual(
            self.configurations,
            stage_a_matrix_configurations(self.reference, relative_step=0.05),
        )
        delta = np.vstack(
            [item.values - self.reference.values for item in self.configurations[1:]]
        )
        self.assertEqual(np.linalg.matrix_rank(delta), 3)
        for point in self.configurations:
            self.assertLess(abs(point.D12), point.D11)

    def test_affine_reconstruction_matches_synthetic_matrix(self):
        basis = self.build_basis()
        target = StageAMatrixParameters(12.0, -1.0, 4.5)
        first = basis.reconstruct_stiffness(target)
        second = basis.reconstruct_stiffness(target)
        np.testing.assert_allclose(first.toarray(), self.matrices(target).stiffness.toarray())
        np.testing.assert_array_equal(first.toarray(), second.toarray())

    def test_changed_stage_a_mass_is_rejected(self):
        perturbations = [
            (parameters, self.matrices(parameters))
            for parameters in self.configurations[1:]
        ]
        parameters, _ = perturbations[-1]
        perturbations[-1] = (parameters, self.matrices(parameters, mass=(1.0, 2.1, 3.0)))
        with self.assertRaisesRegex(MatrixModelError, "mass matrix changed"):
            build_stage_a_affine_basis(
                self.reference, self.matrices(self.reference), perturbations
            )


class StageAAffineBasisMassModelTests(unittest.TestCase):
    """Covers the validated M = M_ref + (D11-D11_ref) * dM/dD11 architecture."""

    def setUp(self):
        self.reference = StageAMatrixParameters(10.0, 2.0, 3.0)
        self.configurations = stage_a_matrix_configurations(
            self.reference, relative_step=0.05
        )
        self.stiffness_constant = np.array([7.0, 11.0, 13.0])
        self.stiffness_contributions = (
            np.array([2.0, 3.0, 5.0]),
            np.array([0.5, -0.25, 0.75]),
            np.array([4.0, 1.0, 2.0]),
        )
        self.mass_constant = np.array([1.0, 2.0, 3.0])
        self.mass_slope = np.array([0.02, -0.01, 0.03])

    def stiffness(self, parameters):
        diagonal = self.stiffness_constant.copy()
        for value, contribution in zip(parameters.values, self.stiffness_contributions):
            diagonal += value * contribution
        return diagonal

    def mass(self, parameters):
        delta_d11 = parameters.D11 - self.reference.D11
        return self.mass_constant + delta_d11 * self.mass_slope

    def matrices(self, parameters):
        return AbaqusMatrixPair(
            stiffness=sparse.diags(self.stiffness(parameters), format="csr"),
            mass=sparse.diags(self.mass(parameters), format="csr"),
            dofs=DOFS,
        )

    def build_basis(self):
        return build_stage_a_affine_basis(
            self.reference,
            self.matrices(self.reference),
            [(p, self.matrices(p)) for p in self.configurations[1:]],
        )

    def test_build_accepts_D11_dependent_mass_and_recovers_the_slope(self):
        basis = self.build_basis()
        self.assertIsNotNone(basis.mass_derivative_D11)
        np.testing.assert_allclose(
            basis.mass_derivative_D11.toarray(), np.diag(self.mass_slope)
        )

    def test_reconstruct_mass_at_reference_returns_reference_mass(self):
        basis = self.build_basis()
        np.testing.assert_array_equal(
            basis.reconstruct_mass(self.reference).toarray(),
            self.matrices(self.reference).mass.toarray(),
        )

    def test_reconstruct_mass_at_D11_perturbation_reproduces_its_mass(self):
        basis = self.build_basis()
        d11_perturbation = self.configurations[1]
        np.testing.assert_allclose(
            basis.reconstruct_mass(d11_perturbation).toarray(),
            self.matrices(d11_perturbation).mass.toarray(),
        )

    def test_changing_D_changes_mass_according_to_the_stored_slope(self):
        basis = self.build_basis()
        target = StageAMatrixParameters(13.5, self.reference.D12, self.reference.D66)
        expected = self.mass_constant + (13.5 - self.reference.D11) * self.mass_slope
        np.testing.assert_allclose(
            basis.reconstruct_mass(target).toarray(), np.diag(expected)
        )

    def test_changing_only_D12_leaves_mass_unchanged(self):
        basis = self.build_basis()
        target = StageAMatrixParameters(self.reference.D11, -1.0, self.reference.D66)
        np.testing.assert_array_equal(
            basis.reconstruct_mass(target).toarray(),
            self.matrices(self.reference).mass.toarray(),
        )

    def test_changing_only_D66_leaves_mass_unchanged(self):
        basis = self.build_basis()
        target = StageAMatrixParameters(self.reference.D11, self.reference.D12, 7.25)
        np.testing.assert_array_equal(
            basis.reconstruct_mass(target).toarray(),
            self.matrices(self.reference).mass.toarray(),
        )

    def test_mass_reconstruction_preserves_symmetry_and_dimensions(self):
        off_diagonal_slope = sparse.csr_matrix(
            np.array([[0.0, 0.01, 0.0], [0.01, 0.0, -0.02], [0.0, -0.02, 0.0]])
        )
        basis = StageAAffineBasis(
            reference_parameters=self.reference,
            reference_stiffness=sparse.diags(self.stiffness(self.reference), format="csr"),
            basis_matrices=tuple(
                sparse.diags(item, format="csr") for item in self.stiffness_contributions
            ),
            mass=sparse.diags(self.mass_constant, format="csr"),
            dofs=DOFS,
            mass_derivative_D11=off_diagonal_slope,
        )
        target = StageAMatrixParameters(11.0, self.reference.D12, self.reference.D66)
        reconstructed = basis.reconstruct_mass(target)
        self.assertEqual(reconstructed.shape, (3, 3))
        np.testing.assert_allclose(reconstructed.toarray(), reconstructed.toarray().T)

    def test_build_rejects_D12_mass_mismatch(self):
        perturbations = [
            (parameters, self.matrices(parameters))
            for parameters in self.configurations[1:]
        ]
        d12_parameters, _ = perturbations[1]
        perturbations[1] = (
            d12_parameters,
            AbaqusMatrixPair(
                stiffness=self.matrices(d12_parameters).stiffness,
                mass=sparse.diags(self.mass_constant + np.array([0.0, 0.05, 0.0]), format="csr"),
                dofs=DOFS,
            ),
        )
        with self.assertRaisesRegex(MatrixModelError, "D12"):
            build_stage_a_affine_basis(
                self.reference, self.matrices(self.reference), perturbations
            )

    def test_build_rejects_D66_mass_mismatch(self):
        perturbations = [
            (parameters, self.matrices(parameters))
            for parameters in self.configurations[1:]
        ]
        d66_parameters, _ = perturbations[2]
        perturbations[2] = (
            d66_parameters,
            AbaqusMatrixPair(
                stiffness=self.matrices(d66_parameters).stiffness,
                mass=sparse.diags(self.mass_constant + np.array([0.0, 0.0, 0.07]), format="csr"),
                dofs=DOFS,
            ),
        )
        with self.assertRaisesRegex(MatrixModelError, "D66"):
            build_stage_a_affine_basis(
                self.reference, self.matrices(self.reference), perturbations
            )

    def test_legacy_basis_without_mass_slope_keeps_constant_mass(self):
        legacy = StageAAffineBasis(
            reference_parameters=self.reference,
            reference_stiffness=sparse.diags(self.stiffness(self.reference), format="csr"),
            basis_matrices=tuple(
                sparse.diags(item, format="csr") for item in self.stiffness_contributions
            ),
            mass=sparse.diags(self.mass_constant, format="csr"),
            dofs=DOFS,
        )
        self.assertIsNone(legacy.mass_derivative_D11)
        for d11 in (5.0, 10.0, 22.0):
            target = StageAMatrixParameters(d11, self.reference.D12, self.reference.D66)
            np.testing.assert_array_equal(
                legacy.reconstruct_mass(target).toarray(), np.diag(self.mass_constant)
            )


class GeneralizedEigenproblemTests(unittest.TestCase):
    def test_known_diagonal_problem_and_frequency_conversion(self):
        result = solve_generalized_eigenproblem(
            sparse.diags([4.0, 9.0]),
            sparse.eye(2, format="csr"),
            2,
            expected_rigid_body_modes=0,
            dofs=DOFS[:2],
        )
        np.testing.assert_allclose(result.eigenvalues, [4.0, 9.0])
        np.testing.assert_allclose(result.frequencies_hz, [1.0 / math.pi, 1.5 / math.pi])
        self.assertEqual(result.eigenvectors.shape, (2, 2))
        self.assertEqual(result.dofs, DOFS[:2])

    def test_rigid_body_mode_is_not_returned_as_elastic(self):
        result = solve_generalized_eigenproblem(
            sparse.diags([0.0, 4.0, 9.0]),
            sparse.eye(3, format="csr"),
            2,
            expected_rigid_body_modes=1,
        )
        np.testing.assert_allclose(result.rigid_body_eigenvalues, [0.0])
        np.testing.assert_allclose(result.eigenvalues, [4.0, 9.0])

    def test_significant_negative_eigenvalue_is_rejected(self):
        with self.assertRaisesRegex(MatrixModelError, "negative"):
            solve_generalized_eigenproblem(
                sparse.diags([-1.0, 4.0]),
                sparse.eye(2, format="csr"),
                1,
                expected_rigid_body_modes=0,
            )

    def test_expected_rigid_count_does_not_hide_pathological_negative_modes(self):
        diagonal = [-100.0, -90.0, -80.0, -70.0, -60.0, -50.0, 1.0, 4.0, 9.0, 16.0]
        with self.assertRaisesRegex(MatrixModelError, "Rigid-spectrum safety FAIL"):
            solve_generalized_eigenproblem(
                sparse.diags(diagonal),
                sparse.eye(len(diagonal), format="csr"),
                4,
                expected_rigid_body_modes=6,
            )

    def test_healthy_scale_aware_rigid_spectrum_passes(self):
        diagonal = [1.0e-10, 2.0e-10, 3.0e-10, 4.0e-10, 5.0e-10, 6.0e-10,
                    1.0, 4.0, 9.0, 16.0]
        result = solve_generalized_eigenproblem(
            sparse.diags(diagonal),
            sparse.eye(len(diagonal), format="csr"),
            4,
            expected_rigid_body_modes=6,
        )
        self.assertEqual(result.rigid_spectrum_health.status, "PASS")
        self.assertEqual(result.rigid_spectrum_health.detected_rigid_mode_count, 6)
        self.assertLess(result.rigid_spectrum_health.rigid_to_first_elastic_ratio, 1.0e-2)


class MatrixDeckAndProofTests(unittest.TestCase):
    def test_deck_renderer_emits_matrix_output_and_verified_shell_orders(self):
        template = (
            "*HEADING\n"
            "** <STAGE_A_SHELL_GENERAL_SECTION>\n"
            "** <STAGE_A_ANALYSIS_STEPS>\n"
        )
        config = StageAShellSectionConfiguration(
            "PLATE",
            SectionStiffnessBlock(100.0, 20.0, 100.0, 0.0, 0.0, 40.0),
            TransverseShearStiffness(70.0, 7.0, 80.0),
        )
        rendered = render_stage_a_matrix_deck(
            template,
            StageAMatrixParameters(10.0, 2.0, 3.0),
            config,
            direct_frequency_modes=8,
        )
        self.assertIn("*MATRIX GENERATE, STIFFNESS, MASS", rendered)
        self.assertIn("*MATRIX OUTPUT, STIFFNESS, MASS, FORMAT=MATRIX INPUT", rendered)
        self.assertIn("*FREQUENCY, EIGENSOLVER=LANCZOS\n8,", rendered)
        self.assertIn("*TRANSVERSE SHEAR STIFFNESS\n70, 80, 7", rendered)
        section_lines = rendered.split("*TRANSVERSE SHEAR STIFFNESS", 1)[0].splitlines()
        numeric_lines = [line for line in section_lines if line and line[0].isdigit()]
        self.assertEqual([len(line.split(",")) for line in numeric_lines], [8, 8, 5])

    def test_structured_proof_result_reports_pass_and_failure_offender(self):
        reference = StageAMatrixParameters(10.0, 2.0, 3.0)
        configurations = stage_a_matrix_configurations(reference)

        def matrices(parameters):
            diagonal = 1.0 + np.array([parameters.D11, parameters.D66, 20.0])
            return diagonal_pair(diagonal)

        basis = build_stage_a_affine_basis(
            reference,
            matrices(reference),
            [(point, matrices(point)) for point in configurations[1:]],
        )
        samples = [StageAMatrixParameters(11.0, 1.0, 4.0)]

        def exact_evaluator(parameters):
            pair = matrices(parameters)
            frequencies = solve_generalized_eigenproblem(
                pair.stiffness, pair.mass, 2, expected_rigid_body_modes=0
            ).frequencies_hz
            return DirectAbaqusEvaluation(pair, frequencies)

        passed = run_matrix_decomposition_proof_test(
            basis,
            samples,
            exact_evaluator,
            mode_count=2,
            expected_rigid_body_modes=0,
        )
        self.assertTrue(passed.passed)
        self.assertEqual(passed.sample_count, 1)
        self.assertIsNone(passed.offending_parameters)

        def failing_evaluator(parameters):
            exact = exact_evaluator(parameters)
            return DirectAbaqusEvaluation(
                exact.matrices, exact.elastic_frequencies_hz * 1.01
            )

        failed = run_matrix_decomposition_proof_test(
            basis,
            samples,
            failing_evaluator,
            mode_count=2,
            expected_rigid_body_modes=0,
        )
        self.assertFalse(failed.passed)
        self.assertEqual(failed.offending_parameters, samples[0])


class StageAAbaqusPointEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.template = (
            "*HEADING\n"
            "** deterministic Stage-A fixture\n"
            "** <STAGE_A_SHELL_GENERAL_SECTION>\n"
            "** <STAGE_A_ANALYSIS_STEPS>\n"
        )
        self.parameters = StageAMatrixParameters(10.0, 2.0, 3.0)
        self.configuration = StageAShellSectionConfiguration(
            "PLATE",
            SectionStiffnessBlock(100.0, 20.0, 100.0, 0.0, 0.0, 40.0),
            TransverseShearStiffness(70.0, 7.0, 80.0),
            density=2.5,
        )
        self.matrix_pair = diagonal_pair([4.0, 9.0, 16.0])

    @staticmethod
    def _successful_job(input_path, output_directory, *, job_name, **_kwargs):
        output_directory = Path(output_directory)
        paths = {
            "launch": output_directory / f"{job_name}.launch.log",
            "dat": output_directory / f"{job_name}.dat",
            "odb": output_directory / f"{job_name}.odb",
            "stiffness": output_directory / f"{job_name}_STIF1.mtx",
            "mass": output_directory / f"{job_name}_MASS1.mtx",
        }
        for label, path in paths.items():
            path.write_text(f"{label} for {job_name}\n", encoding="ascii")
        return AbaqusMatrixJobResult(
            job_name=job_name,
            stiffness_path=paths["stiffness"],
            mass_path=paths["mass"],
            odb_path=paths["odb"],
            dat_path=paths["dat"],
            launch_log_path=paths["launch"],
        )

    @staticmethod
    def _successful_frequency_extract(_odb_path, output_path, **_kwargs):
        Path(output_path).write_text('{"format_version": 1}\n', encoding="ascii")
        return np.array([0.0, 1.25, 2.5])

    def _evaluate(self, work_root, **changes):
        values = {
            "template_text": self.template,
            "parameters": self.parameters,
            "section_configuration": self.configuration,
            "work_root": work_root,
            "direct_frequency_modes": 3,
            "abaqus_version": "Abaqus 2024 test",
        }
        values.update(changes)
        with (
            mock.patch(
                "services.matrix_model_service.run_abaqus_matrix_job",
                side_effect=self._successful_job,
            ) as runner,
            mock.patch(
                "services.matrix_model_service.read_abaqus_matrix_pair",
                return_value=self.matrix_pair,
            ) as reader,
            mock.patch(
                "services.matrix_model_service.extract_abaqus_frequencies",
                side_effect=self._successful_frequency_extract,
            ) as extractor,
            mock.patch(
                "services.matrix_model_service.subprocess.run",
                side_effect=AssertionError("unit test attempted to launch Abaqus"),
            ) as subprocess_run,
        ):
            result = evaluate_stage_a_abaqus_point(**values)
        subprocess_run.assert_not_called()
        return result, runner, reader, extractor

    def test_same_complete_input_has_same_key_but_fresh_isolated_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            first, *_ = self._evaluate(directory)
            second, *_ = self._evaluate(directory)
        self.assertEqual(first.evaluation_key, second.evaluation_key)
        self.assertEqual(first.job_name, second.job_name)
        self.assertNotEqual(first.work_directory, second.work_directory)

    def test_each_bending_parameter_changes_the_key(self):
        changed_points = (
            StageAMatrixParameters(11.0, 2.0, 3.0),
            StageAMatrixParameters(10.0, 2.5, 3.0),
            StageAMatrixParameters(10.0, 2.0, 3.5),
        )
        with tempfile.TemporaryDirectory() as directory:
            baseline, *_ = self._evaluate(directory)
            keys = [
                self._evaluate(directory, parameters=point)[0].evaluation_key
                for point in changed_points
            ]
        self.assertTrue(all(key != baseline.evaluation_key for key in keys))
        self.assertEqual(len(set(keys)), len(changed_points))

    def test_template_and_eigensolver_changes_each_change_the_key(self):
        changed_template = self.template.replace(
            "** deterministic", "** scientifically different"
        )
        with tempfile.TemporaryDirectory() as directory:
            baseline, *_ = self._evaluate(directory)
            template_result, *_ = self._evaluate(
                directory, template_text=changed_template
            )
            solver_result, *_ = self._evaluate(
                directory, frequency_eigensolver="SUBSPACE"
            )
            solver_input = solver_result.input_path.read_text(encoding="utf-8")
        self.assertNotEqual(baseline.evaluation_key, template_result.evaluation_key)
        self.assertNotEqual(baseline.evaluation_key, solver_result.evaluation_key)
        self.assertIn("*FREQUENCY, EIGENSOLVER=SUBSPACE", solver_input)

    def test_success_composes_existing_services_and_preserves_exact_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            result, runner, reader, extractor = self._evaluate(directory)
            rendered = result.input_path.read_text(encoding="utf-8")
        self.assertTrue(result.success)
        self.assertEqual(result.parameters, self.parameters)
        self.assertEqual(
            result.unconstrained_parameters,
            self.parameters.as_parameterization().unconstrained,
        )
        self.assertEqual(result.modal_request.mode_count, 3)
        self.assertEqual(result.modal_request.eigensolver, "LANCZOS")
        self.assertEqual(result.abaqus_version, "Abaqus 2024 test")
        self.assertIs(result.matrices, self.matrix_pair)
        np.testing.assert_array_equal(result.direct_frequencies_hz, [0.0, 1.25, 2.5])
        self.assertIn("0, 10, 0, 0, 0, 2, 10, 0", rendered)
        self.assertIn("*FREQUENCY, EIGENSOLVER=LANCZOS\n3,", rendered)
        self.assertEqual(result.stiffness_metadata.shape, (3, 3))
        self.assertEqual(result.mass_metadata.dof_count, 3)
        self.assertEqual(len(result.template_sha256), 64)
        self.assertEqual(len(result.rendered_input_sha256), 64)
        self.assertEqual(len(result.evaluation_key), 64)
        runner.assert_called_once()
        reader.assert_called_once_with(
            result.matrix_job.stiffness_path, result.matrix_job.mass_path
        )
        extractor.assert_called_once()

    def test_failed_process_raises_structured_failure_with_no_success_result(self):
        process_error = AbaqusMatrixGenerationError(
            "solver returned an error", returncode=17
        )
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "services.matrix_model_service.run_abaqus_matrix_job",
            side_effect=process_error,
        ), mock.patch(
            "services.matrix_model_service.subprocess.run",
            side_effect=AssertionError("unit test attempted to launch Abaqus"),
        ) as subprocess_run:
            with self.assertRaises(StageAAbaqusPointEvaluationError) as captured:
                evaluate_stage_a_abaqus_point(
                    self.template,
                    self.parameters,
                    self.configuration,
                    directory,
                    direct_frequency_modes=3,
                    abaqus_version="Abaqus 2024 test",
                )
        subprocess_run.assert_not_called()
        failure = captured.exception
        self.assertFalse(failure.success)
        self.assertEqual(failure.stage, "abaqus_job")
        self.assertEqual(failure.process_return_code, 17)
        self.assertEqual(failure.parameters, self.parameters)
        self.assertEqual(len(failure.evaluation_key), 64)
        self.assertTrue(failure.work_directory.name.startswith(failure.job_name))

    def test_incomplete_current_outputs_are_rejected_before_read_or_extract(self):
        def incomplete_job(input_path, output_directory, *, job_name, **_kwargs):
            job = self._successful_job(
                input_path, output_directory, job_name=job_name
            )
            job.mass_path.unlink()
            return job

        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch(
                "services.matrix_model_service.run_abaqus_matrix_job",
                side_effect=incomplete_job,
            ),
            mock.patch(
                "services.matrix_model_service.read_abaqus_matrix_pair"
            ) as reader,
            mock.patch(
                "services.matrix_model_service.extract_abaqus_frequencies"
            ) as extractor,
        ):
            with self.assertRaises(StageAAbaqusPointEvaluationError) as captured:
                evaluate_stage_a_abaqus_point(
                    self.template,
                    self.parameters,
                    self.configuration,
                    directory,
                    direct_frequency_modes=3,
                    abaqus_version="Abaqus 2024 test",
                )
        self.assertEqual(captured.exception.stage, "job_output_validation")
        reader.assert_not_called()
        extractor.assert_not_called()

    def test_missing_frequency_artifact_is_not_accepted_as_success(self):
        def incomplete_extract(_odb_path, _output_path, **_kwargs):
            return np.array([0.0, 1.25, 2.5])

        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch(
                "services.matrix_model_service.run_abaqus_matrix_job",
                side_effect=self._successful_job,
            ),
            mock.patch(
                "services.matrix_model_service.read_abaqus_matrix_pair",
                return_value=self.matrix_pair,
            ),
            mock.patch(
                "services.matrix_model_service.extract_abaqus_frequencies",
                side_effect=incomplete_extract,
            ),
        ):
            with self.assertRaises(StageAAbaqusPointEvaluationError) as captured:
                evaluate_stage_a_abaqus_point(
                    self.template,
                    self.parameters,
                    self.configuration,
                    directory,
                    direct_frequency_modes=3,
                    abaqus_version="Abaqus 2024 test",
                )
        self.assertEqual(captured.exception.stage, "frequency_extraction")

    def test_stale_outputs_from_another_directory_cannot_satisfy_current_job(self):
        with tempfile.TemporaryDirectory() as directory:
            stale_directory = Path(directory) / "stale"
            stale_directory.mkdir()

            def stale_job(input_path, output_directory, *, job_name, **_kwargs):
                return self._successful_job(
                    input_path, stale_directory, job_name=job_name
                )

            with (
                mock.patch(
                    "services.matrix_model_service.run_abaqus_matrix_job",
                    side_effect=stale_job,
                ),
                mock.patch(
                    "services.matrix_model_service.read_abaqus_matrix_pair"
                ) as reader,
                mock.patch(
                    "services.matrix_model_service.extract_abaqus_frequencies"
                ) as extractor,
            ):
                with self.assertRaises(StageAAbaqusPointEvaluationError) as captured:
                    evaluate_stage_a_abaqus_point(
                        self.template,
                        self.parameters,
                        self.configuration,
                        directory,
                        direct_frequency_modes=3,
                        abaqus_version="Abaqus 2024 test",
                    )
        self.assertEqual(captured.exception.stage, "job_output_validation")
        reader.assert_not_called()
        extractor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
