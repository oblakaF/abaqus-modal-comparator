"""Shared offline inverse workflow: bounded, explicitly SYNTHETIC cases for both backends.

Recovering known values from synthetic observations tests the software. It is not experimental
material validation. Tolerances here were declared before the first run of these tests.
"""

import dataclasses
import math
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest

for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_name] = "1"

import numpy as np
from scipy import sparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.campaign_definition import SPECIMEN_ENGINEERING_CALIBRATION
from domain.plate_inverse_problem import (
    SYNTHETIC_NO_PHYSICAL_SOURCE,
    FittedParameter,
    FrozenPlateObservation,
    InverseNumericalPolicy,
    InverseRefusalCode,
    InverseResourceBudget,
    InverseScientificStatus,
    MaterialReleaseRefusal,
    NumericalStatus,
    ObservationRole,
    PlateInverseDeclaration,
    ReleaseStatus,
    StudyIntent,
)
from domain.plate_material_problem import (
    CoordinateObservationSet,
    DofObservation,
    DofObservationSet,
    EvidenceKind,
    ExecutionStatus,
    ForwardBackendId,
    ObservationPoint,
    PlateBendingParameters,
    PlateForwardRefusal,
    PlateGeometry,
    RefusalCode,
)
from plate_forward_support import SYNTHETIC, TEST_LIMITS, AbaqusForbiddenMixin
from services import plate_material_workflow
from services.identification_step import (
    CoordinateKind,
    InadmissibleTrial,
    LMSettings,
    LMStatus,
    MixedParameterBounds,
    parameter_bounds,
    run_bounded_lm,
)
from services.matrix_model_service import AbaqusDof, StageAAffineBasis, StageAMatrixParameters
from services.plate_forward_adapter import RitzForwardBackend, StageAMatrixForwardBackend, write_stage_a_package
from services.plate_material_workflow import (
    _StudyRefusal,
    _frozen_set,
    ForwardState,
    RitzInverseModel,
    StageAInverseModel,
    release_material_property,
    run_plate_inverse_study,
)
from services.plate_ritz_forward import RitzNumericalConfig, ritz_model_identity


CURVE_FITTED = "curve-fitted modal dataset"
FRF_PEAK = "FRF peak-derived experimental shape"
SIGMA = 1.0e-3
BUDGET = InverseResourceBudget(max_solves=900, max_elapsed_seconds=60.0, limits=TEST_LIMITS)
GEOMETRY = PlateGeometry.from_units(300.0, 200.0, "mm", mass=120.0, mass_unit="g", thickness=2.0)
RITZ_TRUTH = {"D11": 12.0, "D22": 7.0, "D66": 2.3, "u": 0.15}
RITZ_START = {"D11": 13.0, "D22": 6.5, "D66": 2.5, "u": 0.10}
GRID = tuple((x * 0.14, y * 0.09) for x in (-1.0, -0.6, -0.2, 0.2, 0.6, 1.0) for y in (-1.0, -0.5, 0.0, 0.5, 1.0))
RITZ_SET = CoordinateObservationSet(
    "SYNTHETIC-REGISTRATION", tuple(ObservationPoint(f"p{i}", x, y) for i, (x, y) in enumerate(GRID))
)
RITZ_BOUNDS = {"D11": (6.0, 24.0), "D22": (3.5, 14.0), "D66": (1.2, 4.6), "u": (-0.5, 0.5)}


def ritz_declaration(**changes):
    return dataclasses.replace(RITZ_BASE, **changes)


def ritz_identity(geometry=GEOMETRY, degree=8, count=14):
    return ritz_model_identity(geometry, RitzNumericalConfig(degree, degree, count))


def mac(left, right):
    return float(left @ right) ** 2 / float((left @ left) * (right @ right))


def ritz_state(parameters, geometry=GEOMETRY, degree=8, count=14, observations=RITZ_SET):
    declaration = PlateInverseDeclaration(
        "helper", StudyIntent.SYNTHETIC_SOFTWARE_TEST, EvidenceKind.SYNTHETIC, ForwardBackendId.KIRCHHOFF_RITZ_4D,
        "", "helper", observations, (), (), geometry=geometry, degree_x=degree, degree_y=degree, forward_mode_count=count,
        budget=BUDGET,
    )
    return RitzInverseModel(declaration).solve(parameters)


def row_map(truth, start):
    """Frozen identities, found once from the two shape sets before the study starts."""

    mapping = {}
    for mode in range(truth.observed.shape[1]):
        scores = [mac(truth.observed[:, mode], start.observed[:, other]) for other in range(start.observed.shape[1])]
        mapping[mode + 1] = int(np.argmax(scores)) + 1
    return mapping


def ritz_rows(truth, start, modes, holdout, source=CURVE_FITTED, setup=SIGMA, measurement=None, offsets=None):
    mapping = row_map(truth, start)
    rows = []
    for mode in modes:
        family = f"F{mode}"
        role = ObservationRole.HOLDOUT if mode in holdout else ObservationRole.FIT
        shift = 1.0 if offsets is None else 1.0 + offsets.get(mode, 0.0)
        rows.append(FrozenPlateObservation(
            f"row{mode}", mode, truth.frequencies_hz[mode - 1] * shift, mapping[mode], role, family, source,
            tuple(truth.observed[:, mode - 1]), measurement, setup, False,
        ))
    return tuple(rows)


def parameters(start, bounds):
    return tuple(FittedParameter(name, value, *bounds[name]) for name, value in start.items())


_TRUTH_STATE = ritz_state(RITZ_TRUTH)
_START_STATE = ritz_state(RITZ_START)
RITZ_BASE = PlateInverseDeclaration(
    study_id="SYNTHETIC-RITZ-1",
    intent=StudyIntent.SYNTHETIC_SOFTWARE_TEST,
    evidence_kind=EvidenceKind.SYNTHETIC,
    backend_id=ForwardBackendId.KIRCHHOFF_RITZ_4D,
    model_identity=ritz_identity(),
    specimen_id="SYNTHETIC-NO-SPECIMEN",
    observation_set=RITZ_SET,
    rows=ritz_rows(_TRUTH_STATE, _START_STATE, range(1, 11), {9, 10}),
    parameters=parameters(RITZ_START, RITZ_BOUNDS),
    geometry=GEOMETRY,
    degree_x=8,
    degree_y=8,
    forward_mode_count=14,
    provenance="SYNTHETIC: observations computed by this solver at known values; not a measurement",
    budget=BUDGET,
)

# Stage-A fixture: diagonal K and M, three rigid DOFs, built directly here without the Ritz solver.
RIGID = 3
STAGE_SPECIMEN = "SYNTHETIC-NO-SPECIMEN"
STAGE_MODEL = "SYNTHETIC-DIAGONAL-FIXTURE"
REFERENCE = (0.34, 0.03, 0.040)
A = np.array([1.0e5, 0.2e5, 0.5e5, 1.5e5, 2.6e5, 4.0e5, 3.3e5, 5.5e5, 6.5e5])
B = np.array([0.0, 3.0e5, 0.0, 6.0e5, 9.0e5, 2.0e5, -5.0e5, 7.0e5, 1.0e5])
C = np.array([0.4e5, 7.0e5, 9.0e5, 6.0e5, 0.3e5, 1.0e5, 12.0e5, 5.0e5, 16.0e5])
ELASTIC_MASS = np.array([1.0, 1.1, 0.9, 1.2, 0.8, 1.05, 1.0, 0.95, 1.1])
MASS_SLOPE = np.array([0.20, -0.10, 0.15, 0.05, -0.05, 0.10, 0.02, -0.02, 0.04])
STAGE_DOMAIN = {"D11": (0.2, 0.6), "D12": (-0.1, 0.1), "D66": (0.02, 0.08)}
STAGE_BOUNDS = {"D": (0.2, 0.6), "D66": (0.02, 0.08), "r": (-0.16, 0.16)}
STAGE_TRUTH = {"D": 0.36, "D66": 0.050, "r": 0.09}
STAGE_START = {"D": 0.34, "D66": 0.046, "r": 0.05}
STAGE_DOFS = tuple(index + 1 + RIGID for index in range(A.size))
STAGE_SET = DofObservationSet("SYNTHETIC-REGISTRATION", tuple(DofObservation(f"o{n}", n, 3) for n in STAGE_DOFS))


def diagonal_basis(slope=None):
    def stiffness(values):
        return sparse.diags(np.concatenate([np.zeros(RIGID), values]), format="csr")

    mass_slope = None if slope is None else sparse.diags(np.concatenate([np.zeros(RIGID), slope]), format="csr")
    return StageAAffineBasis(
        StageAMatrixParameters(*REFERENCE),
        stiffness(A * REFERENCE[0] + B * REFERENCE[1] + C * REFERENCE[2]),
        (stiffness(A), stiffness(B), stiffness(C)),
        sparse.diags(np.concatenate([np.ones(RIGID), ELASTIC_MASS]), format="csr"),
        tuple(AbaqusDof(index + 1, 3) for index in range(A.size + RIGID)),
        mass_derivative_D11=mass_slope,
    )


def stage_lambda(point, slope=None):
    d, d66, r = point["D"], point["D66"], point["r"]
    mass = ELASTIC_MASS if slope is None else ELASTIC_MASS + slope * (d - REFERENCE[0])
    return (A * d + B * r * d + C * d66) / mass


def stage_rows(truth, start, fit, holdout, slope=None):
    truth_values = stage_lambda(truth, slope)
    start_order = list(np.argsort(stage_lambda(start, slope)))
    truth_order = list(np.argsort(truth_values))
    rows = []
    for rank, dof in enumerate(truth_order, start=1):
        if int(dof) not in set(fit) | set(holdout):
            continue
        shape = np.zeros(A.size)
        shape[dof] = 1.0 / math.sqrt(ELASTIC_MASS[dof])
        rows.append(FrozenPlateObservation(
            f"dof{dof}", rank, math.sqrt(truth_values[dof]) / (2.0 * math.pi), start_order.index(dof) + 1,
            ObservationRole.HOLDOUT if int(dof) in holdout else ObservationRole.FIT, f"F{dof}", CURVE_FITTED,
            tuple(shape), None, SIGMA, False,
        ))
    return tuple(rows)


class StageCase(AbaqusForbiddenMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name)

    def package(self, name="pkg", basis=None, validation_evidence=None, evidence=EvidenceKind.SYNTHETIC):
        return write_stage_a_package(
            basis if basis is not None else diagonal_basis(), self.root / name,
            specimen_id=STAGE_SPECIMEN, model_id=MODEL_ID, evidence_kind=evidence, units="N-m-kg-s",
            validity_domain=STAGE_DOMAIN, expected_rigid_body_modes=RIGID,
            description="SYNTHETIC diagonal fixture", validation_evidence=validation_evidence,
        )

    def declaration(self, directory, *, slope=None, **changes):
        backend = StageAMatrixForwardBackend.open(
            directory, expected_specimen_id=STAGE_SPECIMEN, expected_model_id=MODEL_ID, limits=TEST_LIMITS
        )
        base = PlateInverseDeclaration(
            study_id="SYNTHETIC-STAGE-A-1",
            intent=StudyIntent.SYNTHETIC_SOFTWARE_TEST,
            evidence_kind=EvidenceKind.SYNTHETIC,
            backend_id=ForwardBackendId.STAGE_A_MATRIX_3D,
            model_identity=backend.model_identity,
            specimen_id=STAGE_SPECIMEN,
            observation_set=STAGE_SET,
            rows=stage_rows(STAGE_TRUTH, STAGE_START, (0, 1, 2, 3, 4, 5, 6), (7,), slope),
            parameters=parameters(STAGE_START, STAGE_BOUNDS),
            forward_mode_count=9,
            stage_a_model_id=MODEL_ID,
            provenance="SYNTHETIC diagonal fixture",
            budget=BUDGET,
        )
        return dataclasses.replace(base, **changes)


MODEL_ID = STAGE_MODEL


class RitzRecovery(AbaqusForbiddenMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_plate_inverse_study(RITZ_BASE)

    def test_recovers_known_values(self):
        result = self.result
        self.assertIs(result.execution_status, ExecutionStatus.COMPLETED, result.refusal_reason)
        self.assertIs(result.numerical_status, NumericalStatus.CONVERGED)
        sd = result.uncertainty.statistical_sd
        fitted = result.final_parameters
        for name in ("D11", "D22", "D66"):
            self.assertLessEqual(abs(math.log(fitted[name] / RITZ_TRUTH[name])), 0.25 * sd[name] + 1.0e-12)
        self.assertLessEqual(abs(fitted["u"] - RITZ_TRUTH["u"]), 0.25 * sd["u"] + 1.0e-12)

    def test_status_is_a_diagnostic_candidate_only(self):
        result = self.result
        self.assertIs(result.scientific_status, InverseScientificStatus.DIAGNOSTIC_OPTIMIZER_CANDIDATE)
        self.assertIs(result.release_status, ReleaseStatus.NOT_A_RELEASE_VALUE)
        self.assertIs(result.evidence_kind, EvidenceKind.SYNTHETIC)
        self.assertIn("M8 GATE NOT_MET", result.restrictions_unchanged)
        self.assertIn("D-077 NO_GLOBAL_PARAMETER_VALUE", result.restrictions_unchanged)
        self.assertTrue(any("not material validation" in reason for reason in result.scientific_reasons))

    def test_required_outputs_are_present(self):
        result = self.result
        self.assertEqual(result.initial_stiffness["D11"], RITZ_START["D11"])
        self.assertAlmostEqual(result.final_stiffness["D12"], result.final_parameters["u"] * result.final_stiffness["D22"])
        self.assertEqual(len(result.frequencies), 10)
        self.assertEqual(len(result.fit_residuals), 8)
        self.assertEqual(len(result.holdout_residuals), 2)
        self.assertEqual(len(result.mode_identity), 10)
        self.assertGreater(len(result.iterations), 1)
        self.assertEqual(result.identifiability.status, "FULL_RANK")
        self.assertIsNotNone(result.identifiability.correlation)
        self.assertEqual(set(result.identifiability.projection_q), set(RITZ_TRUTH))
        self.assertEqual(result.uncertainty.pattern_status, "PASS")
        self.assertEqual(result.uncertainty.birge_status, "AVAILABLE")
        self.assertEqual(len(result.leave_one_family_out), 8)
        self.assertTrue(all(case.status == "VALID" for case in result.leave_one_family_out))
        self.assertLess(result.final_objective, result.initial_objective)

    def test_frequencies_and_holdout_at_the_final_point(self):
        for row in self.result.frequencies:
            self.assertAlmostEqual(row.final_model_hz / row.experimental_hz, 1.0, delta=5.0 * SIGMA)
        for row in self.result.holdout_residuals:
            self.assertLess(abs(row.final_whitened), 3.0)

    def test_final_analytic_sensitivities_agree(self):
        self.assertIsNotNone(self.result.max_analytic_sensitivity_difference)
        self.assertLessEqual(self.result.max_analytic_sensitivity_difference, 1.0e-4)

    def test_missing_parts_stay_named(self):
        missing = " ".join(self.result.uncertainty.missing_components)
        self.assertIn("Sigma_meas NOT_AVAILABLE", missing)
        self.assertIn("mass uncertainty: NOT_AVAILABLE", missing)
        self.assertIn("signed-coordinate precision policy", missing)

    def test_same_declaration_gives_the_same_result(self):
        again = run_plate_inverse_study(RITZ_BASE)
        self.assertEqual(self.result.result_hash, again.result_hash)
        self.assertEqual(self.result.final_parameters, again.final_parameters)

    def test_changed_declaration_changes_identity(self):
        changed = ritz_declaration(policy=InverseNumericalPolicy(stop_fraction=0.1))
        self.assertNotEqual(RITZ_BASE.declaration_hash, changed.declaration_hash)

    def test_zero_and_negative_u_are_recovered(self):
        for u in (0.0, -0.2):
            with self.subTest(u=u):
                truth = dict(RITZ_TRUTH, u=u)
                rows = ritz_rows(ritz_state(truth), _START_STATE, range(1, 11), {9, 10})
                # The start is far in u, so this study declares more than the SPEC 8 default of five iterations.
                result = run_plate_inverse_study(ritz_declaration(rows=rows, policy=InverseNumericalPolicy(max_iterations=12)))
                self.assertIs(result.numerical_status, NumericalStatus.CONVERGED, result.refusal_reason)
                self.assertLessEqual(abs(result.final_parameters["u"] - u), 0.25 * result.uncertainty.statistical_sd["u"] + 1e-12)

    def test_iteration_limit_gives_no_candidate(self):
        rows = ritz_rows(ritz_state(dict(RITZ_TRUTH, u=-0.2)), _START_STATE, range(1, 11), {9, 10})
        result = run_plate_inverse_study(ritz_declaration(rows=rows))
        self.assertIs(result.numerical_status, NumericalStatus.MAX_ITERATIONS)
        self.assertIs(result.scientific_status, InverseScientificStatus.NOT_CONVERGED_NO_CANDIDATE)
        self.assertFalse(result.leave_one_family_out)

    def test_mac_is_not_in_the_objective(self):
        rotated = []
        for index, row in enumerate(RITZ_BASE.rows):
            # A different shape with the same admissible identity leaves every parameter unchanged.
            shape = np.asarray(row.shape, dtype=complex) * np.exp(0.7j)
            shape = shape + 0.02 * np.max(np.abs(shape)) * np.cos(np.arange(shape.size) + index)
            rotated.append(dataclasses.replace(row, shape=tuple(shape)))
        result = run_plate_inverse_study(ritz_declaration(rows=tuple(rotated)))
        self.assertIs(result.numerical_status, NumericalStatus.CONVERGED, result.refusal_reason)
        self.assertEqual(result.final_parameters, self.result.final_parameters)
        changed = [a.final_experimental_mac != b.final_experimental_mac
                   for a, b in zip(result.mode_identity, self.result.mode_identity)]
        self.assertTrue(any(changed))

    def test_holdout_data_do_not_change_the_fit(self):
        rows = tuple(
            dataclasses.replace(row, experimental_hz=row.experimental_hz * 1.02) if row.role is ObservationRole.HOLDOUT else row
            for row in RITZ_BASE.rows
        )
        result = run_plate_inverse_study(ritz_declaration(rows=rows))
        self.assertEqual(result.final_parameters, self.result.final_parameters)
        self.assertIs(result.scientific_status, InverseScientificStatus.MODEL_FORM_CHECK_FAILED)
        self.assertEqual(result.uncertainty.birge_status, "BLOCKED_PATTERN")
        self.assertIs(result.release_status, ReleaseStatus.NOT_A_RELEASE_VALUE)

    def test_leave_one_family_out_moves_estimates_on_perturbed_data(self):
        offsets = {1: 0.002, 2: -0.0015, 3: 0.001, 4: -0.002, 5: 0.0012, 6: -0.001, 7: 0.0018, 8: -0.0012}
        rows = ritz_rows(_TRUTH_STATE, _START_STATE, range(1, 11), {9, 10}, offsets=offsets)
        result = run_plate_inverse_study(ritz_declaration(rows=rows))
        self.assertIs(result.numerical_status, NumericalStatus.CONVERGED, result.refusal_reason)
        ranges = result.uncertainty.robustness_range
        self.assertTrue(all(high > low for low, high in ranges.values()))
        self.assertIn("not a standard deviation", result.uncertainty.robustness_note)
        self.assertGreater(result.final_objective, 0.0)


class OrderChange(AbaqusForbiddenMixin, unittest.TestCase):
    def test_ritz_identity_follows_shape_when_order_changes(self):
        # Between these points twisting modes rise past bending modes.
        truth = {"D11": 12.0, "D22": 7.0, "D66": 2.7, "u": 0.1}
        start = {"D11": 13.0, "D22": 6.5, "D66": 2.2, "u": 0.1}
        truth_state, start_state = ritz_state(truth), ritz_state(start)
        rows = ritz_rows(truth_state, start_state, range(1, 11), {9, 10})
        self.assertNotEqual([row.experimental_mode for row in rows], [row.model_mode for row in rows])
        result = run_plate_inverse_study(ritz_declaration(rows=rows, parameters=parameters(start, RITZ_BOUNDS)))
        self.assertIs(result.numerical_status, NumericalStatus.CONVERGED, result.refusal_reason)
        self.assertTrue(result.order_changes)
        self.assertAlmostEqual(result.final_parameters["D66"], 2.7, delta=0.01)
        for row in result.mode_identity:
            self.assertEqual(row.final_model_mode, row.experimental_mode)
            self.assertGreater(row.final_experimental_mac, 0.999)


class StageAStudies(StageCase):
    def test_recovers_known_values_with_constant_mass(self):
        result = run_plate_inverse_study(self.declaration(self.package()), stage_a_package=self.root / "pkg")
        self.assertIs(result.numerical_status, NumericalStatus.CONVERGED, result.refusal_reason)
        self.assertIs(result.scientific_status, InverseScientificStatus.DIAGNOSTIC_OPTIMIZER_CANDIDATE)
        sd = result.uncertainty.statistical_sd
        for name in ("D", "D66"):
            self.assertLessEqual(abs(math.log(result.final_parameters[name] / STAGE_TRUTH[name])), 0.25 * sd[name] + 1e-12)
        self.assertLessEqual(abs(result.final_parameters["r"] - STAGE_TRUTH["r"]), 0.25 * sd["r"] + 1e-12)
        self.assertEqual(result.final_stiffness["D22"], result.final_stiffness["D11"])
        self.assertLessEqual(result.max_analytic_sensitivity_difference, 1.0e-4)

    def test_recovers_known_values_with_the_stored_mass_slope(self):
        directory = self.package(basis=diagonal_basis(MASS_SLOPE))
        declaration = self.declaration(directory, slope=MASS_SLOPE)
        result = run_plate_inverse_study(declaration, stage_a_package=directory)
        self.assertIs(result.numerical_status, NumericalStatus.CONVERGED, result.refusal_reason)
        self.assertAlmostEqual(math.log(result.final_parameters["D"] / STAGE_TRUTH["D"]), 0.0, delta=0.25 * result.uncertainty.statistical_sd["D"])
        self.assertLessEqual(result.max_analytic_sensitivity_difference, 1.0e-4)

    def test_mass_slope_is_not_ignored(self):
        directory = self.package(basis=diagonal_basis(MASS_SLOPE))
        rows = stage_rows(STAGE_TRUTH, STAGE_START, (0, 1, 2, 3, 4, 5, 6), (7,), None)  # truth without the slope
        result = run_plate_inverse_study(self.declaration(directory, rows=rows), stage_a_package=directory)
        self.assertGreater(result.final_objective, 1.0e-3)

    def test_identity_follows_shape_when_order_changes(self):
        start = {"D": 0.30, "D66": 0.058, "r": 0.05}
        truth = STAGE_TRUTH
        rows = stage_rows(truth, start, (0, 1, 2, 3, 4, 5, 6), (7,))
        self.assertNotEqual([row.experimental_mode for row in rows], [row.model_mode for row in rows])
        directory = self.package()
        declaration = self.declaration(
            directory, rows=rows, parameters=parameters(start, STAGE_BOUNDS),
            policy=InverseNumericalPolicy(max_iterations=20),
        )
        result = run_plate_inverse_study(declaration, stage_a_package=directory)
        self.assertIs(result.numerical_status, NumericalStatus.CONVERGED, result.refusal_reason)
        self.assertTrue(result.order_changes)
        self.assertAlmostEqual(result.final_parameters["D"], truth["D"], delta=1.0e-3)
        for row in result.mode_identity:
            self.assertEqual(row.final_model_mode, row.experimental_mode)

    def test_same_declaration_gives_the_same_result(self):
        directory = self.package()
        declaration = self.declaration(directory)
        first = run_plate_inverse_study(declaration, stage_a_package=directory)
        second = run_plate_inverse_study(declaration, stage_a_package=directory)
        self.assertEqual(first.result_hash, second.result_hash)


class StageARefusals(StageCase):
    def assert_refused(self, result, code):
        self.assertIs(result.refusal_code, code, result.refusal_reason)
        self.assertIsNone(result.final_parameters)
        self.assertIs(result.scientific_status, InverseScientificStatus.NO_RESULT)

    def test_wrong_model(self):
        directory = self.package()
        declaration = self.declaration(directory, stage_a_model_id="OTHER-MODEL")
        result = run_plate_inverse_study(declaration, stage_a_package=directory)
        self.assert_refused(result, InverseRefusalCode.PACKAGE_REFUSED)
        self.assertEqual(result.forward_refusal_code, "PACKAGE_WRONG_MODEL")

    def test_wrong_specimen(self):
        directory = self.package()
        result = run_plate_inverse_study(self.declaration(directory, specimen_id="SP-OTHER"), stage_a_package=directory)
        self.assert_refused(result, InverseRefusalCode.PACKAGE_REFUSED)
        self.assertEqual(result.forward_refusal_code, "PACKAGE_WRONG_SPECIMEN")

    def test_changed_model_identity(self):
        directory = self.package()
        result = run_plate_inverse_study(self.declaration(directory, model_identity="0" * 64), stage_a_package=directory)
        self.assert_refused(result, InverseRefusalCode.MODEL_IDENTITY_MISMATCH)

    def test_missing_package(self):
        directory = self.package()
        declaration = self.declaration(directory)
        result = run_plate_inverse_study(declaration)
        self.assert_refused(result, InverseRefusalCode.PACKAGE_REFUSED)
        self.assertEqual(result.forward_refusal_code, "PACKAGE_MISSING")

    def test_validation_text_is_not_physical_proof(self):
        directory = self.package(validation_evidence="Validated against a physical test by the author.")
        result = run_plate_inverse_study(self.declaration(directory), stage_a_package=directory)
        self.assertEqual(result.package_validation_status, "NOT_ASSESSED_NOT_PHYSICAL_PROOF")
        self.assertIn("Validated", result.package_validation_text)
        self.assertIs(result.release_status, ReleaseStatus.NOT_A_RELEASE_VALUE)
        self.assertTrue(any("not physical proof" in reason for reason in result.scientific_reasons))
        self.assertIs(result.evidence_kind, EvidenceKind.SYNTHETIC)

    def test_package_evidence_kind_must_match_the_declaration(self):
        directory = self.package(evidence=EvidenceKind.PHYSICAL)
        declaration = self.declaration(directory)
        result = run_plate_inverse_study(declaration, stage_a_package=directory)
        self.assert_refused(result, InverseRefusalCode.EVIDENCE_KIND_MISMATCH)

    def test_bounds_beyond_the_stored_range(self):
        directory = self.package()
        wide = dict(STAGE_BOUNDS, D=(0.1, 0.6))
        result = run_plate_inverse_study(
            self.declaration(directory, parameters=parameters(STAGE_START, wide)), stage_a_package=directory
        )
        self.assert_refused(result, InverseRefusalCode.OUTSIDE_VALIDATED_RANGE)
        wide = dict(STAGE_BOUNDS, r=(-0.5, 0.5))
        result = run_plate_inverse_study(
            self.declaration(directory, parameters=parameters(STAGE_START, wide)), stage_a_package=directory
        )
        self.assert_refused(result, InverseRefusalCode.OUTSIDE_VALIDATED_RANGE)

    def test_start_outside_bounds(self):
        directory = self.package()
        start = dict(STAGE_START, D=0.7)
        result = run_plate_inverse_study(
            self.declaration(directory, parameters=parameters(start, STAGE_BOUNDS)), stage_a_package=directory
        )
        self.assert_refused(result, InverseRefusalCode.OUTSIDE_VALIDATED_RANGE)

    def test_rank_deficient_stage_a(self):
        directory = self.package(basis=_collinear_basis())
        rows = _collinear_rows()
        result = run_plate_inverse_study(self.declaration(directory, rows=rows), stage_a_package=directory)
        self.assert_refused(result, InverseRefusalCode.RANK_DEFICIENT)
        self.assertEqual(result.solves > 0, True)


def _collinear_basis():
    """No mode senses D12, so r has no observable direction."""

    def stiffness(values):
        return sparse.diags(np.concatenate([np.zeros(RIGID), values]), format="csr")

    no_coupling = np.zeros_like(B)
    return StageAAffineBasis(
        StageAMatrixParameters(*REFERENCE),
        stiffness(A * REFERENCE[0] + C * REFERENCE[2]),
        (stiffness(A), stiffness(no_coupling), stiffness(C)),
        sparse.diags(np.concatenate([np.ones(RIGID), ELASTIC_MASS]), format="csr"),
        tuple(AbaqusDof(index + 1, 3) for index in range(A.size + RIGID)),
    )


def _collinear_rows():
    def values(point):
        return (A * point["D"] + C * point["D66"]) / ELASTIC_MASS

    truth = values(STAGE_TRUTH)
    start_order = list(np.argsort(values(STAGE_START)))
    rows = []
    for rank, dof in enumerate(np.argsort(truth), start=1):
        if int(dof) == 8:
            continue
        shape = np.zeros(A.size)
        shape[dof] = 1.0
        rows.append(FrozenPlateObservation(
            f"dof{dof}", rank, math.sqrt(truth[dof]) / (2.0 * math.pi), start_order.index(dof) + 1,
            ObservationRole.HOLDOUT if int(dof) == 7 else ObservationRole.FIT, f"F{dof}", CURVE_FITTED,
            tuple(shape), None, SIGMA, False,
        ))
    return tuple(rows)


class RitzRefusals(AbaqusForbiddenMixin, unittest.TestCase):
    def assert_refused(self, result, code):
        self.assertIs(result.refusal_code, code, result.refusal_reason)
        self.assertIs(result.execution_status, ExecutionStatus.REFUSED)
        self.assertIsNone(result.final_parameters)
        self.assertIs(result.scientific_status, InverseScientificStatus.NO_RESULT)
        self.assertIs(result.release_status, ReleaseStatus.NOT_A_RELEASE_VALUE)

    def test_too_few_fit_terms_are_rank_deficient(self):
        rows = ritz_rows(_TRUTH_STATE, _START_STATE, (1, 2, 3, 9), {9})
        self.assert_refused(run_plate_inverse_study(ritz_declaration(rows=rows)), InverseRefusalCode.RANK_DEFICIENT)

    def test_collinear_sensitivities_are_rank_deficient(self):
        # A model whose two columns are identical cannot separate D11 from D22, however many rows it has.
        class Collinear(RitzInverseModel):
            def solve(self, parameters):
                merged = dict(parameters, D22=parameters["D11"] * RITZ_START["D22"] / RITZ_START["D11"])
                return super().solve(merged)

        result = run_plate_inverse_study(RITZ_BASE, model=Collinear(RITZ_BASE))
        self.assert_refused(result, InverseRefusalCode.RANK_DEFICIENT)
        self.assertEqual(result.solves > 0, True)

    def test_missing_holdout(self):
        rows = tuple(dataclasses.replace(row, role=ObservationRole.FIT) for row in RITZ_BASE.rows)
        result = run_plate_inverse_study(ritz_declaration(rows=rows))
        self.assert_refused(result, InverseRefusalCode.MISSING_HOLDOUT)
        self.assertEqual(result.solves, 0)

    def test_holdout_sharing_a_fit_family_is_not_independent(self):
        rows = tuple(dataclasses.replace(row, family="F1") if row.row_id in ("row1", "row9") else row for row in RITZ_BASE.rows)
        self.assert_refused(run_plate_inverse_study(ritz_declaration(rows=rows)), InverseRefusalCode.HOLDOUT_NOT_INDEPENDENT)

    def test_incomplete_covariance(self):
        rows = list(RITZ_BASE.rows)
        rows[2] = dataclasses.replace(rows[2], setup_sd_ln=None)
        result = run_plate_inverse_study(ritz_declaration(rows=tuple(rows)))
        self.assert_refused(result, InverseRefusalCode.INCOMPLETE_COVARIANCE)
        self.assertEqual(result.solves, 0)
        rows[2] = dataclasses.replace(rows[2], setup_sd_ln=0.0)
        self.assert_refused(run_plate_inverse_study(ritz_declaration(rows=tuple(rows))), InverseRefusalCode.INCOMPLETE_COVARIANCE)

    def test_frf_peaks_cannot_be_fitted_modes(self):
        for source in (FRF_PEAK, "something else", None):
            with self.subTest(source=source):
                rows = ritz_rows(_TRUTH_STATE, _START_STATE, range(1, 11), {9, 10}, source=source)
                result = run_plate_inverse_study(ritz_declaration(rows=rows))
                self.assert_refused(result, InverseRefusalCode.INPUT_SOURCE_REFUSED)
                self.assertEqual(result.solves, 0)

    def test_calibration_request_fails_closed_with_no_path(self):
        self.assertEqual({item.value for item in StudyIntent}, {"SYNTHETIC_SOFTWARE_TEST", "MATERIAL_IDENTIFICATION_RESEARCH"})
        for intent in (SPECIMEN_ENGINEERING_CALIBRATION, "ANYTHING_ELSE", None):
            with self.subTest(intent=intent):
                result = run_plate_inverse_study(ritz_declaration(intent=intent), model=_NeverSolved())
                self.assert_refused(result, InverseRefusalCode.UNSUPPORTED_STUDY_INTENT)
                self.assertEqual(result.solves, 0)

    def test_non_synthetic_study_is_refused_whatever_the_authorization_text_says(self):
        for kind in (EvidenceKind.RESEARCH, EvidenceKind.PHYSICAL):
            for intent in StudyIntent:
                for text in (None, "", "Approved by the owner", "HUMAN GATE PASSED"):
                    with self.subTest(kind=kind, intent=intent, text=text):
                        declaration = ritz_declaration(evidence_kind=kind, intent=intent, execution_authorization=text)
                        result = run_plate_inverse_study(declaration, model=_NeverSolved())
                        self.assert_refused(result, InverseRefusalCode.NOT_AUTHORIZED)
                        self.assertEqual(result.solves, 0)

    def test_non_synthetic_study_is_refused_before_a_package_is_opened(self):
        declaration = ritz_declaration(evidence_kind=EvidenceKind.PHYSICAL, execution_authorization="Approved")
        result = run_plate_inverse_study(declaration, stage_a_package=Path("does-not-exist"))
        self.assert_refused(result, InverseRefusalCode.NOT_AUTHORIZED)

    def test_research_intent_on_synthetic_data_is_not_authorized_either(self):
        declaration = ritz_declaration(intent=StudyIntent.MATERIAL_IDENTIFICATION_RESEARCH, execution_authorization="Approved")
        result = run_plate_inverse_study(declaration, model=_NeverSolved())
        self.assert_refused(result, InverseRefusalCode.NOT_AUTHORIZED)

    def _frozen(self, declaration):
        return _frozen_set(declaration, _START_STATE, {row.row_id: 1.0 for row in declaration.rows})

    def test_synthetic_provenance_claims_no_physical_source_file(self):
        frozen = self._frozen(RITZ_BASE)
        identity = frozen.identity
        for name in ("job_name", "generated_inp_sha256", "fe_geometry_sha256", "registration_hash", "experimental_source_sha256"):
            self.assertEqual(getattr(identity, name), SYNTHETIC_NO_PHYSICAL_SOURCE, name)
        self.assertEqual(identity.evidence_source, "SYNTHETIC")
        self.assertIsNone(identity.evidence_record_sha256)
        self.assertEqual(identity.measured_dofs, tuple(point.observation_id for point in RITZ_SET.points))
        self.assertNotIn(RITZ_BASE.model_identity, str(identity))
        self.assertNotIn(RITZ_BASE.declaration_hash, str(identity))
        self.assertNotIn(RITZ_SET.registration_id, str(identity))
        self.assertEqual(frozen.observation_hash, self._frozen(RITZ_BASE).observation_hash)

    def test_physical_identities_cannot_be_presented_as_verified(self):
        with self.assertRaises(_StudyRefusal) as caught:
            self._frozen(ritz_declaration(evidence_kind=EvidenceKind.PHYSICAL))
        self.assertIs(caught.exception.code, InverseRefusalCode.NOT_AUTHORIZED)

    def test_model_identity_must_match(self):
        result = run_plate_inverse_study(ritz_declaration(model_identity="f" * 64))
        self.assert_refused(result, InverseRefusalCode.MODEL_IDENTITY_MISMATCH)

    def test_start_in_the_inadmissible_region(self):
        bad = {"D11": 7.0, "D22": 14.0, "D66": 2.5, "u": 0.9}
        bounds = dict(RITZ_BOUNDS, u=(-0.95, 0.95))
        result = run_plate_inverse_study(ritz_declaration(parameters=parameters(bad, bounds)))
        self.assert_refused(result, InverseRefusalCode.INADMISSIBLE_POINT)

    def test_start_outside_bounds(self):
        start = dict(RITZ_START, D11=30.0)
        result = run_plate_inverse_study(ritz_declaration(parameters=parameters(start, RITZ_BOUNDS)))
        self.assert_refused(result, InverseRefusalCode.OUTSIDE_VALIDATED_RANGE)

    def test_wrong_frozen_mapping_is_refused_not_repaired(self):
        rows = list(RITZ_BASE.rows)
        rows[0], rows[1] = (
            dataclasses.replace(rows[0], model_mode=rows[1].model_mode),
            dataclasses.replace(rows[1], model_mode=rows[0].model_mode),
        )
        result = run_plate_inverse_study(ritz_declaration(rows=tuple(rows)))
        self.assert_refused(result, InverseRefusalCode.BASELINE_PAIRING_REFUSED)
        self.assertIn("frozen as model mode", result.refusal_reason)
        self.assertIn("not changed", result.refusal_reason)
        self.assertEqual(result.iterations, ())  # refused before the fit: nothing was re-paired or fitted

    def test_start_outside_the_strict_frequency_gate(self):
        far = {"D11": 24.0, "D22": 14.0, "D66": 4.6, "u": 0.1}
        rows = ritz_rows(_TRUTH_STATE, ritz_state(far), range(1, 11), {9, 10})
        result = run_plate_inverse_study(ritz_declaration(rows=rows, parameters=parameters(far, RITZ_BOUNDS)))
        self.assert_refused(result, InverseRefusalCode.BASELINE_PAIRING_REFUSED)

    def test_weakly_observed_parameter_is_not_fitted(self):
        # SPEC 10: sd above 8 % in ln p. Full rank alone does not allow the fit.
        rows = ritz_rows(_TRUTH_STATE, _START_STATE, range(1, 11), {9, 10}, setup=0.2)
        result = run_plate_inverse_study(ritz_declaration(rows=rows))
        self.assert_refused(result, InverseRefusalCode.PARAMETER_NOT_OBSERVABLE)

    def test_inadmissible_difference_point_during_the_fit_is_coded_as_such(self):
        class EdgeOfDomain(RitzInverseModel):
            calls = 0

            def solve(self, parameters):
                type(self).calls += 1
                if type(self).calls == 23:  # after the preflight solves, inside the first LM difference stencil
                    raise PlateForwardRefusal(RefusalCode.INADMISSIBLE_PARAMETERS, "D12^2 must be less than D11*D22.")
                return super().solve(parameters)

        result = run_plate_inverse_study(RITZ_BASE, model=EdgeOfDomain(RITZ_BASE))
        self.assert_refused(result, InverseRefusalCode.INADMISSIBLE_POINT)
        self.assertIs(result.numerical_status, NumericalStatus.REFUSED)

    def test_duplicate_experimental_modes_are_refused_cleanly(self):
        rows = list(RITZ_BASE.rows)
        rows[1] = dataclasses.replace(rows[1], experimental_mode=rows[0].experimental_mode)
        result = run_plate_inverse_study(ritz_declaration(rows=tuple(rows)))
        self.assert_refused(result, InverseRefusalCode.DECLARATION_INVALID)

    def test_failed_eigen_residual_is_refused(self):
        class Unhealthy(RitzInverseModel):
            def solve(self, parameters):
                return dataclasses.replace(super().solve(parameters), max_eigen_residual=1.0e-3)

        result = run_plate_inverse_study(RITZ_BASE, model=Unhealthy(RITZ_BASE))
        self.assert_refused(result, InverseRefusalCode.NUMERICAL_HEALTH_FAILED)

    def test_failed_orthogonality_is_refused(self):
        class Unhealthy(RitzInverseModel):
            def solve(self, parameters):
                return dataclasses.replace(super().solve(parameters), max_orthonormality_error=1.0e-3)

        result = run_plate_inverse_study(RITZ_BASE, model=Unhealthy(RITZ_BASE))
        self.assert_refused(result, InverseRefusalCode.NUMERICAL_HEALTH_FAILED)

    def test_health_failure_during_a_trial_keeps_no_candidate(self):
        class FailsLater(RitzInverseModel):
            calls = 0

            def solve(self, parameters):
                type(self).calls += 1
                state = super().solve(parameters)
                if type(self).calls > 30:
                    return dataclasses.replace(state, max_eigen_residual=1.0e-3)
                return state

        result = run_plate_inverse_study(RITZ_BASE, model=FailsLater(RITZ_BASE))
        self.assert_refused(result, InverseRefusalCode.NUMERICAL_HEALTH_FAILED)
        self.assertIs(result.numerical_status, NumericalStatus.REFUSED)

    def test_loss_of_branch_identity_is_refused_not_repaired(self):
        class Scrambled(RitzInverseModel):
            calls = 0

            def solve(self, parameters):
                type(self).calls += 1
                state = super().solve(parameters)
                if type(self).calls < 30:
                    return state
                shapes = np.array(state.shapes)
                shapes[0], shapes[1] = shapes[0] + shapes[1], shapes[0] - shapes[1]
                return dataclasses.replace(state, shapes=shapes)

        result = run_plate_inverse_study(RITZ_BASE, model=Scrambled(RITZ_BASE))
        self.assert_refused(result, InverseRefusalCode.BRANCH_IDENTITY_LOST)
        self.assertIs(result.numerical_status, NumericalStatus.REFUSED)
        self.assertTrue(result.iterations or result.solves)

    def test_budget_stop_is_not_a_candidate(self):
        small = InverseResourceBudget(max_solves=25, max_elapsed_seconds=60.0, limits=TEST_LIMITS)
        result = run_plate_inverse_study(ritz_declaration(budget=small))
        self.assertIn(result.execution_status, (ExecutionStatus.BUDGET_EXHAUSTED,))
        self.assertIsNot(result.scientific_status, InverseScientificStatus.DIAGNOSTIC_OPTIMIZER_CANDIDATE)

    def test_elapsed_budget_stops_at_a_solve_boundary(self):
        ticks = iter(range(0, 100000, 100))
        result = run_plate_inverse_study(RITZ_BASE, clock=lambda: float(next(ticks)))
        self.assertIs(result.execution_status, ExecutionStatus.BUDGET_EXHAUSTED)
        self.assertIsNone(result.final_parameters)

    def test_cancel_stops_at_a_solve_boundary(self):
        calls = []

        def cancel():
            calls.append(1)
            return len(calls) > 3

        result = run_plate_inverse_study(RITZ_BASE, cancel=cancel)
        self.assertIs(result.execution_status, ExecutionStatus.CANCELLED)
        self.assertIs(result.refusal_code, InverseRefusalCode.CANCELLED)
        self.assertIsNone(result.final_parameters)


class _AnyEigenbasis(RitzInverseModel):
    """Returns exactly repeated pairs in a chosen basis, as a different eigensolver or platform may do.

    The pair is first aligned with the reference shapes, then turned by ``angle``.
    """

    def __init__(self, declaration, reference, angle):
        super().__init__(declaration)
        self.reference, self.angle = reference, angle

    def solve(self, parameters):
        state = super().solve(parameters)
        shapes, observed = state.shapes.copy(), state.observed.copy()
        root = np.sqrt(self.weights)
        frequencies = state.frequencies_hz
        for i in range(len(frequencies) - 1):
            if abs(frequencies[i] / frequencies[i + 1] - 1.0) > 1.0e-10:
                continue
            modes = [i, i + 1]
            left, _, right = np.linalg.svd((shapes[modes] * root) @ (self.reference.shapes[modes] * root).T)
            c, s = math.cos(self.angle), math.sin(self.angle)
            turn = np.array([[c, s], [-s, c]]) @ (left @ right).T
            shapes[modes] = turn @ shapes[modes]
            observed[:, modes] = observed[:, modes] @ turn.T
        return dataclasses.replace(state, shapes=shapes, observed=observed)


class _NeverSolved:
    """Stands where a backend would be, for refusals that must come before any solve."""

    def __getattr__(self, name):
        raise AssertionError(f"A refused declaration reached the model: {name}.")


class SymmetricSquarePlate(AbaqusForbiddenMixin, unittest.TestCase):
    """A square plate at D11 = D22, whose elastic spectrum holds exactly repeated pairs."""

    GEOMETRY = PlateGeometry.from_units(300.0, 300.0, "mm", mass=100.0, mass_unit="g", thickness=2.0)
    TRUTH = {"D11": 5.1, "D22": 5.0, "D66": 1.75, "u": 0.3}
    START = {"D11": 5.0, "D22": 5.0, "D66": 1.9, "u": 0.3}
    BOUNDS = {"D11": (3.0, 8.0), "D22": (3.0, 8.0), "D66": (1.0, 3.0), "u": (-0.5, 0.6)}
    ANGLES = tuple(math.radians(value) for value in (0.0, 10.0, 25.0, 45.0, 90.0))
    SEPARATED = (1, 2, 3, 8, 9, 10)  # modes 4 to 7 are two repeated pairs

    def setUp(self):
        super().setUp()
        self.points = CoordinateObservationSet("SYNTHETIC-REGISTRATION", tuple(
            ObservationPoint(f"p{i}", x * 0.14, y * 0.13)
            for i, (x, y) in enumerate((a, b) for a in (-1.0, -0.6, -0.2, 0.3, 0.7, 1.0) for b in (-1.0, -0.4, 0.2, 0.6, 1.0))
        ))
        self.truth = ritz_state(self.TRUTH, self.GEOMETRY, 8, 14, self.points)

    def declaration(self, modes, declared=()):
        rows = tuple(
            FrozenPlateObservation(
                f"row{mode}", mode, self.truth.frequencies_hz[mode - 1], mode,
                ObservationRole.HOLDOUT if mode == 3 else ObservationRole.FIT, f"F{mode}", CURVE_FITTED,
                tuple(self.truth.observed[:, mode - 1]), None, SIGMA, False,
            )
            for mode in modes
        )
        return PlateInverseDeclaration(
            "SYNTHETIC-SQUARE", StudyIntent.SYNTHETIC_SOFTWARE_TEST, EvidenceKind.SYNTHETIC,
            ForwardBackendId.KIRCHHOFF_RITZ_4D, ritz_identity(self.GEOMETRY), "SYNTHETIC-NO-SPECIMEN", self.points,
            rows, parameters(self.START, self.BOUNDS), confirmed_clusters=declared,
            geometry=self.GEOMETRY, degree_x=8, degree_y=8, forward_mode_count=14, budget=BUDGET,
            provenance="SYNTHETIC",
        )

    def test_frozen_rows_on_a_repeated_eigenvalue_are_refused_in_every_basis(self):
        # Before this check the same declaration gave a candidate, a pairing refusal or a cluster refusal,
        # depending only on the basis that the eigensolver happened to return.
        for declared in ((), (("row1", "row2"),), (("row4", "row5"),)):
            declaration = self.declaration((1, 2, 3, 4, 5, 8, 9, 10), declared)
            for angle in self.ANGLES:
                with self.subTest(declared=declared, angle=angle):
                    result = run_plate_inverse_study(declaration, model=_AnyEigenbasis(declaration, self.truth, angle))
                    self.assertIs(result.refusal_code, InverseRefusalCode.UNRESOLVED_MODAL_CLUSTER, result.refusal_reason)
                    self.assertIn("arbitrary basis", result.refusal_reason)
                    self.assertIsNone(result.final_parameters)
                    self.assertEqual(result.solves, 1)

    def test_one_frozen_member_of_a_repeated_pair_is_refused_in_every_basis(self):
        # The partner is not an observation, yet the individual eigenvector of the frozen member is still arbitrary.
        for member in (4, 5):
            modes = tuple(sorted((1, 2, 3, member, 8, 9, 10)))
            for declared in ((), (("row1", "row2"),)):
                declaration = self.declaration(modes, declared)
                outcomes = set()
                for angle in self.ANGLES:
                    with self.subTest(member=member, declared=declared, angle=angle):
                        result = run_plate_inverse_study(declaration, model=_AnyEigenbasis(declaration, self.truth, angle))
                        self.assertIs(result.refusal_code, InverseRefusalCode.UNRESOLVED_MODAL_CLUSTER, result.refusal_reason)
                        self.assertIn("arbitrary basis", result.refusal_reason)
                        self.assertIn("not frozen", result.refusal_reason)
                        self.assertIsNone(result.final_parameters)
                        self.assertEqual(result.iterations, ())
                        self.assertEqual(result.solves, 1)  # no review, MAC check or fit was reached
                        outcomes.add((result.refusal_code, result.refusal_reason))
                self.assertEqual(len(outcomes), 1, outcomes)

    def test_four_parameters_are_rank_deficient_at_the_symmetric_point(self):
        declaration = self.declaration(self.SEPARATED)
        # Swapping x and y leaves each separated mode unchanged, so d/dlnD11 equals d/dlnD22 at fixed D12.
        # With D12 = u*D22, the D22 column therefore equals the D11 column plus u times the u column.
        reference = RitzInverseModel(declaration)
        analytic = reference.analytic_sensitivities(self.START, max(self.SEPARATED))[[mode - 1 for mode in self.SEPARATED]]
        gap = analytic[:, 1] - analytic[:, 0] - self.START["u"] * analytic[:, 3]
        self.assertLess(float(np.abs(gap).max()), 1.0e-9)
        for angle in self.ANGLES:  # the unobserved repeated pairs must not influence the outcome
            with self.subTest(angle=angle):
                result = run_plate_inverse_study(declaration, model=_AnyEigenbasis(declaration, self.truth, angle))
                self.assertIs(result.refusal_code, InverseRefusalCode.RANK_DEFICIENT, result.refusal_reason)
                self.assertIn("rank 3 < 4", result.refusal_reason)
                self.assertIsNone(result.final_parameters)


class RepeatedNeighbourGuard(unittest.TestCase):
    """The guard reads only the solved spectrum: the stand-ins below hold no shape from which to compute a MAC."""

    LIMIT = InverseNumericalPolicy().repeated_frequency_relative_spacing

    @staticmethod
    def check(modes, spectrum):
        rows = tuple(types.SimpleNamespace(row_id=f"row{mode}", model_mode=mode) for mode in modes)
        declaration = types.SimpleNamespace(rows=rows, policy=InverseNumericalPolicy())
        plate_material_workflow._refuse_repeated_rows(declaration, types.SimpleNamespace(frequencies_hz=tuple(spectrum)))

    def assert_refused(self, modes, spectrum):
        with self.assertRaises(plate_material_workflow._StudyRefusal) as caught:
            self.check(modes, spectrum)
        self.assertIs(caught.exception.code, InverseRefusalCode.UNRESOLVED_MODAL_CLUSTER)

    def test_the_lower_and_the_upper_unfrozen_neighbour_are_both_checked(self):
        self.assert_refused([2], [10.0, 20.0, 20.0, 30.0])  # upper
        self.assert_refused([3], [10.0, 20.0, 20.0, 30.0])  # lower

    def test_the_two_ends_of_the_solved_spectrum_have_one_neighbour(self):
        self.assert_refused([1], [10.0, 10.0, 30.0])
        self.assert_refused([3], [10.0, 30.0, 30.0])
        self.check([1], [10.0, 20.0, 30.0])
        self.check([3], [10.0, 20.0, 30.0])

    def test_the_existing_tolerance_is_the_limit(self):
        self.assert_refused([1], [100.0, 100.0 * (1.0 + 0.5 * self.LIMIT), 200.0])
        self.check([1], [100.0, 100.0 * (1.0 + 2.0 * self.LIMIT), 200.0])

    def test_a_repeated_pair_away_from_the_frozen_modes_is_ignored(self):
        self.check([1, 2], [10.0, 20.0, 30.0, 30.0, 40.0])
        self.check([1, 5], [10.0, 20.0, 30.0, 30.0, 40.0])

    def test_two_frozen_members_are_still_refused(self):
        self.assert_refused([2, 3], [10.0, 20.0, 20.0, 30.0])


class ConfirmedCluster(StageCase):
    """A SYNTHETIC rotating pair: D12 turns its shapes while its two-dimensional subspace stays fixed."""

    A_PAIR = (2.0e5, 1.94e5)
    C_PAIR = 2.0e5
    B_PAIR = 6.0e4
    ELASTIC = 6
    START = {"D": 0.34, "D66": 0.046, "r": 0.05}
    TRUTH = {"D": 0.36, "D66": 0.050, "r": 0.06}

    def pair_basis(self):
        count = RIGID + self.ELASTIC + 2
        first, second = count - 2, count - 1

        def matrix(diagonal_values, pair_values, off_diagonal=0.0):
            dense = np.diag(np.concatenate([np.zeros(RIGID), diagonal_values, pair_values]))
            dense[first, second] = dense[second, first] = off_diagonal
            return sparse.csr_matrix(dense)

        a = A[: self.ELASTIC]
        b = B[: self.ELASTIC]
        c = C[: self.ELASTIC]
        k_d11 = matrix(a, self.A_PAIR)
        k_d12 = matrix(b, (0.0, 0.0), self.B_PAIR)
        k_d66 = matrix(c, (self.C_PAIR, self.C_PAIR))
        reference = k_d11 * REFERENCE[0] + k_d12 * REFERENCE[1] + k_d66 * REFERENCE[2]
        return StageAAffineBasis(
            StageAMatrixParameters(*REFERENCE), sparse.csr_matrix(reference), (k_d11, k_d12, k_d66),
            sparse.identity(count, format="csr"), tuple(AbaqusDof(index + 1, 3) for index in range(count)),
        )

    def study(self):
        directory = self.package(basis=self.pair_basis())
        count = self.ELASTIC + 2
        observations = DofObservationSet("SYNTHETIC-REGISTRATION", tuple(
            DofObservation(f"o{n}", n, 3) for n in range(RIGID + 1, RIGID + count + 1)
        ))
        backend = StageAMatrixForwardBackend.open(directory, limits=TEST_LIMITS)

        def solved(point):
            d = point["D"]
            return backend.evaluate(PlateBendingParameters(d, d, point["r"] * d, point["D66"]), count, observations)

        truth, start = solved(self.TRUTH), solved(self.START)
        truth_shapes, start_shapes = truth.observation.values, start.observation.values
        pair_modes = [mode for mode in range(count) if abs(start_shapes[-2:, mode]).max() > 0.1]
        self.assertEqual(len(pair_modes), 2)
        rows = []
        for mode in range(count):
            shape = truth_shapes[:, mode]
            in_pair = abs(shape[-2:]).max() > 0.1
            if in_pair:
                start_mode = pair_modes[0] if mode == min(m for m in range(count) if abs(truth_shapes[-2:, m]).max() > 0.1) else pair_modes[1]
            else:
                start_mode = int(np.argmax([mac(shape, start_shapes[:, other]) for other in range(count)]))
            if start_mode == count - 1:  # the highest mode stays above the frozen rows as the window guard
                continue
            holdout = start_mode == count - 2 and not in_pair
            rows.append(FrozenPlateObservation(
                f"m{mode + 1}", mode + 1, truth.frequencies_hz[mode], start_mode + 1,
                ObservationRole.HOLDOUT if holdout else ObservationRole.FIT,
                "pair" if in_pair else f"F{mode + 1}", CURVE_FITTED, tuple(shape), None, SIGMA, False,
            ))
        pair_rows = [row.row_id for row in rows if row.family == "pair"]
        self.assertEqual(len(pair_rows), 2)
        declaration = self.declaration(
            directory, rows=tuple(rows), observation_set=observations, forward_mode_count=count,
            parameters=parameters(self.START, STAGE_BOUNDS), confirmed_clusters=(tuple(pair_rows),),
        )
        return directory, declaration, rows, pair_rows

    def test_confirmed_pair_is_one_observation_and_the_fit_recovers(self):
        directory, declaration, rows, pair_rows = self.study()
        result = run_plate_inverse_study(declaration, stage_a_package=directory)
        self.assertIs(result.numerical_status, NumericalStatus.CONVERGED, result.refusal_reason)
        ids = [row.term_id for row in result.fit_residuals]
        self.assertIn(f"C({pair_rows[0]}+{pair_rows[1]})", ids)
        self.assertEqual(len(ids), len([r for r in rows if r.role is ObservationRole.FIT]) - 1)
        self.assertLessEqual(abs(result.final_parameters["r"] - self.TRUTH["r"]), 0.25 * result.uncertainty.statistical_sd["r"] + 1e-12)

    def test_undeclared_cluster_is_refused(self):
        directory, declaration, _, pair_rows = self.study()
        undeclared = dataclasses.replace(declaration, confirmed_clusters=())
        result = run_plate_inverse_study(undeclared, stage_a_package=directory)
        self.assertIs(result.refusal_code, InverseRefusalCode.UNRESOLVED_MODAL_CLUSTER, result.refusal_reason)
        self.assertIn("separate observations", result.refusal_reason)
        for row in pair_rows:
            self.assertIn(row, result.refusal_reason)
        self.assertIsNone(result.final_parameters)

    def test_declared_pair_that_is_not_a_cluster_is_refused(self):
        directory, declaration, rows, pair_rows = self.study()
        separate = tuple(row.row_id for row in rows if row.family != "pair" and row.role is ObservationRole.FIT)[:2]
        declared = dataclasses.replace(declaration, confirmed_clusters=(tuple(pair_rows), separate))
        result = run_plate_inverse_study(declared, stage_a_package=directory)
        self.assertIs(result.refusal_code, InverseRefusalCode.UNRESOLVED_MODAL_CLUSTER, result.refusal_reason)
        self.assertIn("not confirmed", result.refusal_reason)
        self.assertIsNone(result.final_parameters)


class PublishedBenchmark(AbaqusForbiddenMixin, unittest.TestCase):
    """Liu and Banerjee, Computers & Structures 164 (2016) 108-126, Table 1, FFFF row M = N = 20.

    Square isotropic plate, nu = 0.3. The parameter is omega*a^2*sqrt(rho*h/D). Modes 4 to 11 in the
    paper's numbering are the first eight elastic modes, since modes 1 to 3 are rigid. Accepted
    manuscript: https://openaccess.city.ac.uk/id/eprint/14353/. Tolerance declared before the first
    run: 1e-4 in the parameter, one unit in the last published digit.
    """

    TABLE = (13.4682, 19.5961, 24.2702, 34.8009, 34.8009, 61.0932, 61.0932, 63.6861)
    TOLERANCE = 1.0e-4

    def test_free_free_isotropic_values(self):
        a = 0.3
        mu = 2.0
        d = 5.0
        nu = 0.3
        geometry = PlateGeometry.from_units(a, a, "m", surface_mass_kg_m2=mu)
        backend = RitzForwardBackend(geometry, RitzNumericalConfig(14, 14, 8), SYNTHETIC, limits=TEST_LIMITS)
        result = backend.evaluate(PlateBendingParameters(d, d, nu * d, (1.0 - nu) / 2.0 * d))
        omega = 2.0 * math.pi * np.array(result.frequencies_hz)
        parameter = omega * a * a * math.sqrt(mu / d)
        np.testing.assert_allclose(parameter, self.TABLE, atol=self.TOLERANCE, rtol=0.0)
        self.assertLessEqual(result.diagnostics["max_eigen_residual"], 1.0e-8)


class Release(AbaqusForbiddenMixin, unittest.TestCase):
    def test_candidate_cannot_be_released(self):
        result = run_plate_inverse_study(RITZ_BASE)
        self.assertIs(result.scientific_status, InverseScientificStatus.DIAGNOSTIC_OPTIMIZER_CANDIDATE)
        with self.assertRaises(MaterialReleaseRefusal):
            release_material_property(result)

    def test_result_cannot_hold_another_release_status(self):
        result = run_plate_inverse_study(RITZ_BASE)
        with self.assertRaises(ValueError):
            dataclasses.replace(result, release_status="ACCEPTED_MATERIAL")

    def test_no_calibration_field_exists(self):
        names = {field.name for field in dataclasses.fields(run_plate_inverse_study(RITZ_BASE))}
        self.assertFalse([name for name in names if "calibration" in name])


class SharedLoopMixedPath(unittest.TestCase):
    """The opt-in path of the one LM loop, with analytic residuals and no solver."""

    SETTINGS = LMSettings(mu_initial=1e-3, mu_decrease=10.0, max_step_attempts=4, solve_budget=200, max_iterations=30,
                          finite_difference_step=0.01)
    BOUNDS = MixedParameterBounds(("p", "u"), (0.1, -1.0), (10.0, 1.0), (CoordinateKind.LOG, CoordinateKind.LINEAR), (None, 0.01))

    @staticmethod
    def residuals(point):
        return np.array([math.log(point["p"] / 2.0) / 1e-3, (point["u"] + 0.3) / 1e-3, (math.log(point["p"] / 2.0) + point["u"] + 0.3) / 1e-3])

    def test_signed_coordinate_is_not_logged(self):
        result = run_bounded_lm(self.residuals, {"p": 1.5, "u": 0.0}, self.BOUNDS, self.SETTINGS)
        self.assertIs(result.status, LMStatus.CONVERGED)
        self.assertAlmostEqual(result.parameters["u"], -0.3, places=4)
        self.assertAlmostEqual(result.x[1], result.parameters["u"])
        self.assertAlmostEqual(result.x[0], math.log(result.parameters["p"]))

    def test_rejected_small_step_is_not_convergence(self):
        def always_worse(point):
            base = self.residuals(point)
            # Difference points move one coordinate only; every real trial moves both and is worse.
            return base if point["p"] == 1.5 or point["u"] == 0.0 else base + 1.0e4

        settings = dataclasses.replace(self.SETTINGS, max_step_attempts=14)
        result = run_bounded_lm(always_worse, {"p": 1.5, "u": 0.0}, self.BOUNDS, settings)
        self.assertIs(result.status, LMStatus.STEP_REJECTED)
        self.assertEqual(result.parameters, {"p": 1.5, "u": 0.0})
        self.assertFalse(any(item.accepted for item in result.history))

    def test_default_path_keeps_its_historical_stop_after_rejections(self):
        # Recorded behaviour of the default path, kept so that historical results do not change: damping
        # after rejections shrinks the step until the stop rule reports convergence. The mixed path does not.
        bounds = parameter_bounds([("a", 0.1, 10.0), ("b", 0.1, 10.0)])

        def always_worse(point):
            base = np.array([math.log(point["a"] / 2.0) / 1e-3, math.log(point["b"] / 3.0) / 1e-3,
                             math.log(point["a"] * point["b"] / 6.0) / 1e-3])
            return base if point["a"] == 1.5 or point["b"] == 2.5 else base + 1.0e4

        settings = LMSettings(mu_initial=1e-3, mu_decrease=10.0, max_step_attempts=14, solve_budget=200,
                              finite_difference_step=0.01)
        result = run_bounded_lm(always_worse, {"a": 1.5, "b": 2.5}, bounds, settings)
        self.assertIs(result.status, LMStatus.CONVERGED)
        self.assertEqual(result.parameters, {"a": 1.5, "b": 2.5})

    def test_legacy_positive_path_is_unchanged_by_the_opt_in(self):
        bounds = parameter_bounds([("a", 0.1, 10.0), ("b", 0.1, 10.0)])

        def linear(point):
            return np.array([math.log(point["a"] / 2.0) / 1e-3, math.log(point["b"] / 3.0) / 1e-3, math.log(point["a"] * point["b"] / 6.0) / 1e-3])

        settings = LMSettings(mu_initial=1e-3, mu_decrease=10.0, max_step_attempts=3, solve_budget=60)
        result = run_bounded_lm(linear, {"a": 1.8, "b": 3.2}, bounds, settings)
        self.assertIs(result.status, LMStatus.CONVERGED)
        self.assertAlmostEqual(result.parameters["a"], 2.0, places=2)
        self.assertEqual(result.history[-1].note, "step below stop_fraction·sd")

    def test_inadmissible_trial_is_rejected_and_the_state_is_kept(self):
        accepted = []

        def guarded(point):
            if point["u"] < -0.1 and point["u"] != 0.0:
                raise InadmissibleTrial("u below the admissible limit")
            return self.residuals(point)

        settings = dataclasses.replace(self.SETTINGS, max_step_attempts=2, finite_difference_step=0.01)
        result = run_bounded_lm(guarded, {"p": 1.5, "u": 0.0}, self.BOUNDS, settings, accepted.append)
        rejected = [item for item in result.history if item.note.startswith("rejected: u below")]
        self.assertTrue(rejected)
        for item in rejected:
            self.assertIsNone(item.trial_objective)
            self.assertFalse(item.accepted)
        self.assertGreaterEqual(result.parameters["u"], -0.1)
        if accepted:
            self.assertEqual(accepted[-1], dict(result.parameters))

    def test_inadmissible_difference_point_refuses(self):
        def guarded(point):
            if point["u"] > 0.005:
                raise InadmissibleTrial("u above the admissible limit")
            return self.residuals(point)

        result = run_bounded_lm(guarded, {"p": 1.5, "u": 0.0}, self.BOUNDS, self.SETTINGS)
        self.assertIs(result.status, LMStatus.REFUSED)
        self.assertEqual(result.parameters, {"p": 1.5, "u": 0.0})

    def test_difference_points_stay_inside_the_bounds(self):
        seen = []

        def record(point):
            seen.append(dict(point))
            return self.residuals(point)

        run_bounded_lm(record, {"p": 0.1, "u": -1.0}, self.BOUNDS, dataclasses.replace(self.SETTINGS, solve_budget=6))
        self.assertTrue(all(0.1 <= item["p"] <= 10.0 and -1.0 <= item["u"] <= 1.0 for item in seen))

    def test_log_coordinate_needs_a_positive_bound(self):
        with self.assertRaises(Exception):
            MixedParameterBounds(("p",), (-1.0,), (1.0,), (CoordinateKind.LOG,), (None,))
        with self.assertRaises(Exception):
            MixedParameterBounds(("u",), (-1.0,), (1.0,), (CoordinateKind.LINEAR,), (None,))


if __name__ == "__main__":
    unittest.main()
