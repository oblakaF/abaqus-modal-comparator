import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from dataclasses import asdict
import json

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from services.abaqus_shell_section import (
    SectionStiffnessBlock,
    StageAShellSectionConfiguration,
    TransverseShearStiffness,
)
from services.matrix_model_service import (
    DirectAbaqusEvaluation,
    StageAMatrixParameters,
    build_stage_a_affine_basis,
    extract_abaqus_frequencies,
    read_abaqus_matrix_pair,
    render_stage_a_matrix_deck,
    run_abaqus_matrix_job,
    run_matrix_decomposition_proof_test,
    solve_generalized_eigenproblem,
    stage_a_matrix_configurations,
)


ABAQUS_COMMAND = os.environ.get("ABAQUS_COMMAND", "abaqus")
ABAQUS_AVAILABLE = Path(ABAQUS_COMMAND).is_file() or shutil.which(ABAQUS_COMMAND) is not None
RUN_INTEGRATION = os.environ.get("ABAQUS_MATRIX_INTEGRATION") == "1"
RUN_PROOF = os.environ.get("ABAQUS_MATRIX_PROOF") == "1"


@unittest.skipUnless(
    RUN_INTEGRATION and ABAQUS_AVAILABLE,
    "set ABAQUS_MATRIX_INTEGRATION=1 and provide an Abaqus executable",
)
class AbaqusStageAMatrixIntegrationTests(unittest.TestCase):
    def test_real_s4_renderer_matrix_export_import_and_eigensolve(self):
        template = (ROOT / "abaqus_scripts" / "stage_a_bare_plate_template.inp").read_text(
            encoding="ascii"
        )
        configuration = StageAShellSectionConfiguration(
            "PLATE",
            SectionStiffnessBlock(1.0e6, 2.5e5, 1.0e6, 0.0, 0.0, 3.75e5),
            TransverseShearStiffness(5.0e5, 0.0, 5.0e5),
        )
        deck = render_stage_a_matrix_deck(
            template,
            StageAMatrixParameters(100.0, 25.0, 37.5),
            configuration,
            direct_frequency_modes=12,
        )

        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            input_path = directory_path / "stage_a_real_smoke.inp"
            input_path.write_text(deck, encoding="ascii")
            datacheck = run_abaqus_matrix_job(
                input_path,
                directory_path,
                job_name="stage_a_real_datacheck",
                abaqus_command=ABAQUS_COMMAND,
                datacheck=True,
            )
            self.assertTrue(datacheck.dat_path.is_file())

            job = run_abaqus_matrix_job(
                input_path,
                directory_path,
                job_name="stage_a_real_smoke",
                abaqus_command=ABAQUS_COMMAND,
            )
            matrices = read_abaqus_matrix_pair(job.stiffness_path, job.mass_path)
            direct = extract_abaqus_frequencies(
                job.odb_path,
                directory_path / "frequencies.json",
                abaqus_command=ABAQUS_COMMAND,
            )
            fast = solve_generalized_eigenproblem(
                matrices.stiffness,
                matrices.mass,
                6,
                expected_rigid_body_modes=6,
                dofs=matrices.dofs,
            )

        self.assertEqual(matrices.stiffness.shape, matrices.mass.shape)
        self.assertGreater(matrices.stiffness.nnz, matrices.stiffness.shape[0])
        self.assertEqual(fast.eigenvectors.shape[0], len(matrices.dofs))
        self.assertEqual(len(direct), 12)
        direct_elastic = direct[6:12]
        relative_error = np.max(
            np.abs(fast.frequencies_hz - direct_elastic) / direct_elastic
        )
        self.assertLess(relative_error, 1.0e-4)

    @unittest.skipUnless(
        RUN_PROOF,
        "set ABAQUS_MATRIX_PROOF=1 to run the 20-sample Abaqus proof test",
    )
    def test_real_twenty_sample_matrix_decomposition_proof(self):
        template = (ROOT / "abaqus_scripts" / "stage_a_bare_plate_template.inp").read_text(
            encoding="ascii"
        )
        configuration = StageAShellSectionConfiguration(
            "PLATE",
            SectionStiffnessBlock(1.0e6, 2.5e5, 1.0e6, 0.0, 0.0, 3.75e5),
            TransverseShearStiffness(5.0e5, 0.0, 5.0e5),
        )
        reference = StageAMatrixParameters(100.0, 25.0, 37.5)
        configurations = stage_a_matrix_configurations(reference, relative_step=0.01)

        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)

            def evaluate_job(parameters, name, frequency_modes=0):
                input_path = directory_path / f"{name}.inp"
                input_path.write_text(
                    render_stage_a_matrix_deck(
                        template,
                        parameters,
                        configuration,
                        direct_frequency_modes=frequency_modes,
                    ),
                    encoding="ascii",
                )
                job = run_abaqus_matrix_job(
                    input_path,
                    directory_path,
                    job_name=name,
                    abaqus_command=ABAQUS_COMMAND,
                )
                matrices = read_abaqus_matrix_pair(job.stiffness_path, job.mass_path)
                frequencies = None
                if frequency_modes:
                    frequencies = extract_abaqus_frequencies(
                        job.odb_path,
                        directory_path / f"{name}_frequencies.json",
                        abaqus_command=ABAQUS_COMMAND,
                    )
                return matrices, frequencies

            basis_jobs = [
                evaluate_job(parameters, f"stage_a_basis_{index}")[0]
                for index, parameters in enumerate(configurations)
            ]
            basis = build_stage_a_affine_basis(
                reference,
                basis_jobs[0],
                list(zip(configurations[1:], basis_jobs[1:])),
            )

            rng = np.random.default_rng(20260906)
            samples = [
                StageAMatrixParameters(
                    D11=float(rng.uniform(70.0, 130.0)),
                    D12=0.0,
                    D66=float(rng.uniform(25.0, 55.0)),
                )
                for _ in range(20)
            ]
            samples = [
                StageAMatrixParameters(
                    D11=sample.D11,
                    D12=float(rng.uniform(-0.55, 0.55) * sample.D11),
                    D66=sample.D66,
                )
                for sample in samples
            ]
            evaluation_index = 0

            def direct_evaluator(parameters):
                nonlocal evaluation_index
                matrices, frequencies = evaluate_job(
                    parameters,
                    f"stage_a_proof_{evaluation_index:02d}",
                    frequency_modes=26,
                )
                evaluation_index += 1
                return DirectAbaqusEvaluation(matrices, frequencies[6:])

            result = run_matrix_decomposition_proof_test(
                basis,
                samples,
                direct_evaluator,
                mode_count=20,
                expected_rigid_body_modes=6,
            )

        print("STAGE_A_PROOF_RESULT=" + json.dumps(asdict(result), default=str, sort_keys=True))
        self.assertTrue(result.passed)
        self.assertEqual(result.sample_count, 20)
        self.assertLess(result.worst_frequency_relative_error, 1.0e-4)


if __name__ == "__main__":
    unittest.main()
