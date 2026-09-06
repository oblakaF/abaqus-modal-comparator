import math
from pathlib import Path
import sys
import tempfile
import unittest

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
    AbaqusMatrixPair,
    DirectAbaqusEvaluation,
    MatrixModelError,
    StageAMatrixParameters,
    build_stage_a_affine_basis,
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


if __name__ == "__main__":
    unittest.main()
