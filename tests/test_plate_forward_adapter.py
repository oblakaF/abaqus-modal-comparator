"""Stage-A read-only adapter: a small SYNTHETIC diagonal package only.

The fixture tests adapter operation. It is not the owner's model, and it is not independent physical
validation. It is built directly here, not from the Ritz solver.
"""

import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_name] = "1"

import numpy as np
from scipy import sparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

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
    ResourceLimits,
    ScientificStatus,
)
from plate_forward_support import SYNTHETIC, TEST_LIMITS, AbaqusForbiddenMixin
from services import plate_forward_adapter as adapter
from services.matrix_model_service import AbaqusDof, StageAAffineBasis, StageAMatrixNodeMap, StageAMatrixParameters
from services.plate_forward_adapter import (
    RitzForwardBackend,
    StageAMatrixForwardBackend,
    inspect_stage_a_package,
    plate_backend_availability,
    write_stage_a_package,
)
from services.plate_ritz_forward import RitzNumericalConfig


RIGID = 3
SPECIMEN = "SYNTHETIC-NO-SPECIMEN"
MODEL = "SYNTHETIC-DIAGONAL-FIXTURE"
REFERENCE = (0.34, 0.03, 0.040)
A = np.array([1.0e5, 0.2e5, 0.5e5, 1.5e5, 2.6e5, 4.0e5])
B = np.array([0.0, 3.0e5, 0.0, 6.0e5, 9.0e5, 2.0e5])
C = np.array([0.4e5, 7.0e5, 9.0e5, 6.0e5, 0.3e5, 1.0e5])
ELASTIC_MASS = np.array([1.0, 1.1, 0.9, 1.2, 0.8, 1.05])
MASS_SLOPE = np.array([0.20, -0.10, 0.15, 0.05, -0.05, 0.10])
DOMAIN = {"D11": (0.2, 0.6), "D12": (-0.1, 0.1), "D66": (0.02, 0.08)}


def diagonal_basis(slope=None, d_scale=1.0, node_map=None):
    """K and M are diagonal, with three zero-stiffness DOFs. ``d_scale`` is D in package units per N*m."""

    def stiffness(values):
        return sparse.diags(np.concatenate([np.zeros(RIGID), values]), format="csr")

    reference = StageAMatrixParameters(*(value * d_scale for value in REFERENCE))
    reference_k = stiffness(A * REFERENCE[0] + B * REFERENCE[1] + C * REFERENCE[2])
    mass = sparse.diags(np.concatenate([np.ones(RIGID), ELASTIC_MASS]), format="csr")
    mass_slope = None
    if slope is not None:
        mass_slope = sparse.diags(np.concatenate([np.zeros(RIGID), slope / d_scale]), format="csr")
    return StageAAffineBasis(
        reference,
        reference_k,
        (stiffness(A / d_scale), stiffness(B / d_scale), stiffness(C / d_scale)),
        mass,
        tuple(AbaqusDof(index + 1, 3) for index in range(A.size + RIGID)),
        mass_derivative_D11=mass_slope,
        node_map=node_map,
    )


def expected_frequencies(d11, d12, d66, slope=None):
    mass = ELASTIC_MASS if slope is None else ELASTIC_MASS + slope * (d11 - REFERENCE[0])
    values = (A * d11 + B * d12 + C * d66) / mass
    return np.sort(np.sqrt(values) / (2.0 * math.pi))


def stage_parameters(d11=0.36, d12=0.02, d66=0.05):
    return PlateBendingParameters(d11, d11, d12, d66)


class PackageCase(AbaqusForbiddenMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name)

    def package(self, name="pkg", basis=None, units="N-m-kg-s", domain=DOMAIN):
        return write_stage_a_package(
            basis if basis is not None else diagonal_basis(),
            self.root / name,
            specimen_id=SPECIMEN,
            model_id=MODEL,
            evidence_kind=EvidenceKind.SYNTHETIC,
            units=units,
            validity_domain=domain,
            expected_rigid_body_modes=RIGID,
            description="SYNTHETIC diagonal Stage-A fixture for adapter tests; no specimen, no physical meaning",
        )

    def open(self, directory, **arguments):
        arguments.setdefault("limits", TEST_LIMITS)
        return StageAMatrixForwardBackend.open(directory, **arguments)

    def assert_refused(self, code, directory, **arguments):
        with self.assertRaises(PlateForwardRefusal) as caught:
            self.open(directory, **arguments)
        self.assertIs(caught.exception.code, code, caught.exception.reason)
        return caught.exception

    def edit_manifest(self, directory, **changes):
        path = directory / adapter.STAGE_A_PACKAGE_MANIFEST
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest.update(changes)
        path.write_text(json.dumps(manifest), encoding="utf-8")

    def replace_arrays(self, directory, **replacements):
        """Change stored arrays and refresh the file hash, so only deeper checks can object."""

        path = directory / "matrices.npz"
        with np.load(path, allow_pickle=False) as data:
            arrays = {name: data[name] for name in data.files}
        arrays.update(replacements)
        with path.open("wb") as stream:
            np.savez(stream, **arrays)
        self.refresh_file_record(directory)

    def refresh_file_record(self, directory):
        path = directory / "matrices.npz"
        self.edit_manifest(
            directory,
            matrix_file={
                "name": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size,
            },
        )


class Capabilities(PackageCase):
    def test_three_parameters_and_constraint(self):
        capabilities = self.open(self.package()).capabilities
        self.assertEqual(capabilities.independent_parameters, ("D11", "D12", "D66"))
        self.assertIn("D22=D11", capabilities.parameter_constraints)
        self.assertTrue(capabilities.requires_matrix_package)
        self.assertFalse(capabilities.requires_abaqus_installation)
        self.assertFalse(capabilities.can_generate_matrices)
        self.assertFalse(capabilities.sum_of_energy_fractions_applies)
        self.assertFalse(capabilities.performs_material_identification)


class Evaluation(PackageCase):
    def test_frequencies_match_the_closed_form_of_the_fixture(self):
        backend = self.open(self.package(), expected_specimen_id=SPECIMEN, expected_model_id=MODEL)
        result = backend.evaluate(stage_parameters(), 6)
        self.assertIs(result.execution_status, ExecutionStatus.COMPLETED)
        self.assertIs(result.backend_id, ForwardBackendId.STAGE_A_MATRIX_3D)
        np.testing.assert_allclose(result.frequencies_hz, expected_frequencies(0.36, 0.02, 0.05), rtol=1.0e-10)
        self.assertLessEqual(result.diagnostics["max_eigen_residual"], 1.0e-9)
        self.assertEqual(result.diagnostics["rigid_spectrum_status"], "PASS")
        self.assertEqual(result.diagnostics["validation_evidence"], "NOT_SUPPLIED")

    def test_statuses_and_synthetic_label(self):
        result = self.open(self.package()).evaluate(stage_parameters(), 3)
        self.assertEqual(result.provenance.evidence_kind.value, "SYNTHETIC")
        self.assertIn("SYNTHETIC", result.provenance.description)
        self.assertIs(result.scientific_status, ScientificStatus.FORWARD_ONLY_NOT_AN_IDENTIFICATION)
        self.assertEqual(dict(result.provenance.source_identities)["specimen_id"], SPECIMEN)

    def test_dof_identities_are_kept_in_the_shape(self):
        result = self.open(self.package()).evaluate(stage_parameters(), 3)
        self.assertEqual(result.shape.row_labels, tuple((index + 1, 3) for index in range(9)))
        self.assertEqual(result.shape.values.shape, (9, 3))

    def test_node_map_survives_the_package(self):
        node_map = StageAMatrixNodeMap.from_mapping({index + 1: f"PLATE:{100 + index}" for index in range(9)})
        backend = self.open(self.package(basis=diagonal_basis(node_map=node_map)))
        self.assertEqual(backend.basis.node_map.content_hash, node_map.content_hash)

    def test_package_units_convert_from_si(self):
        si = self.open(self.package("si")).evaluate(stage_parameters(), 6)
        domain = {name: tuple(1000.0 * value for value in bounds) for name, bounds in DOMAIN.items()}
        mm = self.open(self.package("mm", diagonal_basis(d_scale=1000.0), "N-mm-t-s", domain))
        result = mm.evaluate(stage_parameters(), 6)
        np.testing.assert_allclose(result.frequencies_hz, si.frequencies_hz, rtol=1.0e-10)
        self.assertAlmostEqual(result.diagnostics["parameters_in_package_units"][0], 360.0)

    def test_d22_different_from_d11_is_refused_not_averaged(self):
        result = self.open(self.package()).evaluate(PlateBendingParameters(0.36, 0.30, 0.02, 0.05), 3)
        self.assertIs(result.execution_status, ExecutionStatus.REFUSED)
        self.assertIs(result.refusal_code, RefusalCode.STAGE_A_REQUIRES_D22_EQUAL_D11)
        self.assertEqual(result.frequencies_hz, ())

    def test_outside_the_stored_domain_is_refused(self):
        backend = self.open(self.package())
        for parameters in (stage_parameters(d11=0.7), stage_parameters(d12=0.15), stage_parameters(d66=0.01)):
            result = backend.evaluate(parameters, 3)
            self.assertIs(result.refusal_code, RefusalCode.OUTSIDE_VALIDITY_DOMAIN)

    def test_too_many_modes_is_a_refusal(self):
        result = self.open(self.package()).evaluate(stage_parameters(), 7)
        self.assertIs(result.refusal_code, RefusalCode.MATRIX_MODEL_FAILED)

    def test_run_identity_is_exact_and_depends_on_the_package(self):
        backend = self.open(self.package())
        identity = backend.run_identity(stage_parameters(), 3)
        self.assertEqual(identity, backend.run_identity(stage_parameters(), 3))
        self.assertNotEqual(identity, backend.run_identity(stage_parameters(d66=float(np.nextafter(0.05, 1.0))), 3))
        other = self.open(self.package("other", diagonal_basis(slope=MASS_SLOPE)))
        self.assertNotEqual(backend.model_identity, other.model_identity)

    def test_opening_and_solving_change_no_package_file(self):
        directory = self.package()
        before = {path.name: path.read_bytes() for path in directory.iterdir()}
        self.open(directory).evaluate(stage_parameters(), 3)
        self.assertEqual(before, {path.name: path.read_bytes() for path in directory.iterdir()})


class StoredMassBehaviour(PackageCase):
    def test_stored_slope_is_used(self):
        backend = self.open(self.package(basis=diagonal_basis(slope=MASS_SLOPE)))
        result = backend.evaluate(stage_parameters(), 6)
        self.assertEqual(result.diagnostics["mass_model"], adapter.MASS_SLOPE_PRESENT)
        np.testing.assert_allclose(result.frequencies_hz, expected_frequencies(0.36, 0.02, 0.05, MASS_SLOPE), rtol=1.0e-10)

    def test_absent_slope_stays_constant_mass(self):
        backend = self.open(self.package())
        self.assertIsNone(backend.basis.mass_derivative_D11)
        result = backend.evaluate(stage_parameters(), 6)
        self.assertEqual(result.diagnostics["mass_model"], adapter.MASS_SLOPE_ABSENT)
        np.testing.assert_allclose(result.frequencies_hz, expected_frequencies(0.36, 0.02, 0.05), rtol=1.0e-10)

    def test_manifest_claiming_a_missing_slope_is_refused(self):
        directory = self.package()
        self.edit_manifest(directory, mass_slope=adapter.MASS_SLOPE_PRESENT)
        self.assert_refused(RefusalCode.PACKAGE_CORRUPT, directory)

    def test_archive_slope_undeclared_by_the_manifest_is_refused(self):
        directory = self.package(basis=diagonal_basis(slope=MASS_SLOPE))
        self.edit_manifest(directory, mass_slope=adapter.MASS_SLOPE_ABSENT)
        self.assert_refused(RefusalCode.PACKAGE_CORRUPT, directory)

    def test_sensitivity_includes_the_stored_mass_term(self):
        backend = self.open(self.package(basis=diagonal_basis(slope=MASS_SLOPE)))
        d11, d12, d66 = 0.36, 0.02, 0.05
        result = backend.sensitivities(stage_parameters(d11, d12, d66), 5, finite_difference_relative_steps=(0.005, 0.01))
        self.assertTrue(result.derivative_validation.consistent)
        lam = (A * d11 + B * d12 + C * d66) / (ELASTIC_MASS + MASS_SLOPE * (d11 - REFERENCE[0]))
        mass = ELASTIC_MASS + MASS_SLOPE * (d11 - REFERENCE[0])
        d_ln_lambda = (A - lam * MASS_SLOPE) / (lam * mass)
        order = np.argsort(lam)[:5]
        np.testing.assert_allclose(result.scaled_sensitivity[:, 0], 0.5 * d11 * d_ln_lambda[order], rtol=1.0e-8)

    def test_energy_fraction_sum_rule_is_not_imposed(self):
        backend = self.open(self.package(basis=diagonal_basis(slope=MASS_SLOPE)))
        evaluated = backend.evaluate(stage_parameters(), 3)
        self.assertIn("NOT_APPLIED", evaluated.diagnostics["energy_fraction_sum_rule"])
        result = backend.sensitivities(stage_parameters(), 5)
        fractions = 2.0 * result.scaled_sensitivity.copy()
        fractions[:, 1] *= 0.02 / 0.36  # D12 is scaled by D11 in the existing coordinate contract.
        self.assertGreater(float(np.max(np.abs(fractions.sum(axis=1) - 1.0))), 1.0e-3)

    def test_outside_domain_sensitivity_is_refused(self):
        with self.assertRaises(PlateForwardRefusal) as caught:
            self.open(self.package()).sensitivities(stage_parameters(d11=0.7), 3)
        self.assertIs(caught.exception.code, RefusalCode.OUTSIDE_VALIDITY_DOMAIN)


class Refusals(PackageCase):
    def test_missing_folder_manifest_and_matrices(self):
        self.assert_refused(RefusalCode.PACKAGE_MISSING, self.root / "absent")
        directory = self.package()
        (directory / "matrices.npz").unlink()
        self.assert_refused(RefusalCode.PACKAGE_MISSING, directory)
        empty = self.root / "empty"
        empty.mkdir()
        self.assert_refused(RefusalCode.PACKAGE_MISSING, empty)

    def test_bad_manifest(self):
        directory = self.package()
        (directory / adapter.STAGE_A_PACKAGE_MANIFEST).write_text("{not json", encoding="utf-8")
        self.assert_refused(RefusalCode.PACKAGE_CORRUPT, directory)
        (directory / adapter.STAGE_A_PACKAGE_MANIFEST).write_text("[1]", encoding="utf-8")
        self.assert_refused(RefusalCode.PACKAGE_CORRUPT, directory)

    def test_wrong_field_types_are_refused(self):
        for index, change in enumerate(({"units": ["N-m-kg-s"]}, {"parameter_names": 3}, {"model_id": 7})):
            directory = self.package(f"t{index}")
            self.edit_manifest(directory, **change)
            self.assert_refused(RefusalCode.PACKAGE_CORRUPT, directory)

    def test_non_integer_dof_labels_are_refused_not_truncated(self):
        directory = self.package()
        self.replace_arrays(directory, dof_nodes=np.arange(1.5, 10.5))
        self.assert_refused(RefusalCode.PACKAGE_CORRUPT, directory)

    def test_unknown_schema_and_missing_fields(self):
        directory = self.package("a")
        self.edit_manifest(directory, schema="abm/stage-a-matrix-package/v99")
        self.assert_refused(RefusalCode.PACKAGE_UNSUPPORTED, directory)
        directory = self.package("b")
        path = directory / adapter.STAGE_A_PACKAGE_MANIFEST
        manifest = json.loads(path.read_text(encoding="utf-8"))
        del manifest["validity_domain"]
        path.write_text(json.dumps(manifest), encoding="utf-8")
        self.assert_refused(RefusalCode.PACKAGE_CORRUPT, directory)

    def test_wrong_model(self):
        directory = self.package("a")
        self.assert_refused(RefusalCode.PACKAGE_WRONG_MODEL, directory, expected_model_id="OTHER")
        self.edit_manifest(directory, model_kind="GENERIC_SENSITIVITY_TABLE")
        self.assert_refused(RefusalCode.PACKAGE_WRONG_MODEL, directory)
        directory = self.package("b")
        self.edit_manifest(directory, parameter_names=["D11", "D22", "D12", "D66"])
        self.assert_refused(RefusalCode.PACKAGE_WRONG_MODEL, directory)
        directory = self.package("c")
        self.edit_manifest(directory, constraint="NONE")
        self.assert_refused(RefusalCode.PACKAGE_WRONG_MODEL, directory)

    def test_wrong_specimen(self):
        self.assert_refused(RefusalCode.PACKAGE_WRONG_SPECIMEN, self.package(), expected_specimen_id="SP-11")

    def test_changed_bytes_are_refused(self):
        directory = self.package()
        path = directory / "matrices.npz"
        data = bytearray(path.read_bytes())
        data[len(data) // 2] ^= 0xFF
        path.write_bytes(bytes(data))
        self.assert_refused(RefusalCode.PACKAGE_CORRUPT, directory)

    def test_truncated_archive_with_matching_hash_is_refused(self):
        directory = self.package()
        path = directory / "matrices.npz"
        path.write_bytes(path.read_bytes()[:200])
        self.refresh_file_record(directory)
        self.assert_refused(RefusalCode.PACKAGE_CORRUPT, directory)

    def test_changed_matrix_with_matching_file_hash_is_refused_by_identity(self):
        directory = self.package()
        with np.load(directory / "matrices.npz", allow_pickle=False) as data:
            changed = data["K_ref_data"] * 1.01
        self.replace_arrays(directory, K_ref_data=changed)
        self.assert_refused(RefusalCode.PACKAGE_CORRUPT, directory)

    def test_non_finite_values_are_refused(self):
        directory = self.package()
        with np.load(directory / "matrices.npz", allow_pickle=False) as data:
            changed = data["M_ref_data"].copy()
        changed[0] = math.nan
        self.replace_arrays(directory, M_ref_data=changed)
        self.assert_refused(RefusalCode.PACKAGE_CORRUPT, directory)

    def test_object_arrays_are_refused_before_loading(self):
        directory = self.package()
        self.replace_arrays(directory, K_ref_data=np.array([{"a": 1}, None], dtype=object))
        with mock.patch.object(adapter.np, "load", side_effect=AssertionError("loaded")):
            self.assert_refused(RefusalCode.PACKAGE_CORRUPT, directory)

    def test_matrix_file_must_stay_in_the_folder(self):
        directory = self.package()
        self.edit_manifest(directory, matrix_file={"name": "../matrices.npz", "sha256": "0", "bytes": 1})
        self.assert_refused(RefusalCode.PACKAGE_CORRUPT, directory)

    def test_reference_outside_the_stored_domain_is_refused(self):
        directory = self.package()
        self.edit_manifest(directory, validity_domain={"D11": [0.5, 0.6], "D12": [-0.1, 0.1], "D66": [0.02, 0.08]})
        self.assert_refused(RefusalCode.PACKAGE_CORRUPT, directory)

    def test_bad_domain_is_refused(self):
        directory = self.package()
        self.edit_manifest(directory, validity_domain={"D11": [0.6, 0.2], "D12": [-0.1, 0.1], "D66": [0.02, 0.08]})
        self.assert_refused(RefusalCode.PACKAGE_CORRUPT, directory)

    def test_size_caps_refuse_before_any_load(self):
        directory = self.package()
        size = (directory / "matrices.npz").stat().st_size
        caps = (
            ResourceLimits(max_package_file_bytes=size - 1),
            ResourceLimits(max_package_uncompressed_bytes=16),
            ResourceLimits(max_allocation_bytes=16),
            ResourceLimits(max_matrix_dofs=4),
            ResourceLimits(max_matrix_nonzeros=4),
            ResourceLimits(max_manifest_bytes=8),
        )
        for limits in caps:
            with self.subTest(limits=limits), mock.patch.object(adapter.np, "load", side_effect=AssertionError("loaded")):
                self.assert_refused(RefusalCode.RESOURCE_LIMIT, directory, limits=limits)

    def test_inspection_loads_no_matrix_values(self):
        directory = self.package()
        with mock.patch.object(adapter.np, "load", side_effect=AssertionError("loaded")):
            inspection = inspect_stage_a_package(directory, limits=TEST_LIMITS)
        self.assertEqual(inspection.dof_count, 9)
        self.assertGreater(inspection.nonzero_count, 0)

    def test_writer_never_overwrites(self):
        directory = self.package()
        with self.assertRaises(FileExistsError):
            self.package(directory.name)


class BackendIndependence(PackageCase):
    def ritz(self):
        geometry = PlateGeometry.from_units(300.0, 200.0, "mm", mass=120.0, mass_unit="g")
        return RitzForwardBackend(geometry, RitzNumericalConfig(6, 6, 3), SYNTHETIC, limits=TEST_LIMITS)

    def test_missing_package_disables_only_stage_a(self):
        for package in (None, self.root / "absent"):
            availability = plate_backend_availability(package, limits=TEST_LIMITS)
            self.assertTrue(availability[ForwardBackendId.KIRCHHOFF_RITZ_4D].available)
            stage_a = availability[ForwardBackendId.STAGE_A_MATRIX_3D]
            self.assertFalse(stage_a.available)
            self.assertIs(stage_a.refusal_code, RefusalCode.PACKAGE_MISSING)
            self.assertTrue(stage_a.reason)
        result = self.ritz().evaluate(PlateBendingParameters(12.0, 7.0, 1.1, 2.3))
        self.assertIs(result.execution_status, ExecutionStatus.COMPLETED)

    def test_compatible_package_enables_stage_a(self):
        availability = plate_backend_availability(
            self.package(), expected_specimen_id=SPECIMEN, expected_model_id=MODEL, limits=TEST_LIMITS
        )
        self.assertTrue(availability[ForwardBackendId.STAGE_A_MATRIX_3D].available)

    def test_wrong_package_reports_the_reason(self):
        availability = plate_backend_availability(self.package(), expected_specimen_id="SP-11", limits=TEST_LIMITS)
        stage_a = availability[ForwardBackendId.STAGE_A_MATRIX_3D]
        self.assertIs(stage_a.refusal_code, RefusalCode.PACKAGE_WRONG_SPECIMEN)
        self.assertTrue(availability[ForwardBackendId.KIRCHHOFF_RITZ_4D].available)

    def test_both_backends_return_the_same_contract(self):
        ritz = self.ritz().evaluate(stage_parameters())
        stage_a = self.open(self.package()).evaluate(stage_parameters(), 3)
        self.assertIs(type(ritz), type(stage_a))
        self.assertIs(ritz.scientific_status, stage_a.scientific_status)
        self.assertNotEqual(ritz.shape.kind, stage_a.shape.kind)


class ObservationKinds(PackageCase):
    def test_dof_observation_returns_stored_rows(self):
        result = self.open(self.package()).evaluate(
            stage_parameters(), 3, DofObservationSet("SYNTHETIC-REG", (DofObservation("o1", 4, 3), DofObservation("o2", 6, 3)))
        )
        positions = [3, 5]
        np.testing.assert_array_equal(result.observation.values, result.shape.values[positions, :])
        self.assertEqual(result.observation.observation_ids, ("o1", "o2"))

    def test_unknown_dof_is_refused_not_guessed(self):
        result = self.open(self.package()).evaluate(
            stage_parameters(), 3, DofObservationSet("r", (DofObservation("o", 4, 2),))
        )
        self.assertIs(result.refusal_code, RefusalCode.OBSERVATION_OUTSIDE_MODEL)

    def test_coordinate_observation_is_refused(self):
        result = self.open(self.package()).evaluate(
            stage_parameters(), 3, CoordinateObservationSet("r", (ObservationPoint("p", 0.0, 0.0),))
        )
        self.assertIs(result.refusal_code, RefusalCode.UNSUPPORTED_OBSERVATION_KIND)


class NoExtraction(PackageCase):
    def test_adapter_module_holds_no_generation_call(self):
        tree = (ROOT / "src/services/plate_forward_adapter.py").read_text(encoding="utf-8")
        for name in ("run_abaqus_matrix_job", "evaluate_stage_a_abaqus_point", "build_stage_a_affine_basis",
                     "render_stage_a_matrix_deck", "forward_solver", "subprocess", "generic_plate_offline_study"):
            self.assertNotIn(name, tree)


if __name__ == "__main__":
    unittest.main()
