from __future__ import annotations

import copy
import dataclasses
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from coordinate_calibration import CoordinateCalibration
from domain.registration import FrozenRegistration
from modal_core import ModalDataset, ModeShape
import reviewed_core
from reviewed_core import (
    GeometryOrientationAmbiguousError,
    compare_modal_datasets,
    experimental_measurement_masks,
)
from registration_factory import RegistrationRefusedError, build_frozen_registration
from scientific_state import (
    calibration_fingerprint,
    experimental_source_content_identity,
    experimental_source_identity,
    modal_dataset_geometry_identity,
)


CALIBRATION = CoordinateCalibration(
    mode="calibrated_physical", abaqus_unit="mm", experimental_unit="m"
)
OTHER_CALIBRATION = CoordinateCalibration(mode="manual", manual_scale=0.001)
FREQUENCIES = (21.0, 47.0, 88.0)


def asymmetric_points():
    # No mirror/rotation symmetry: exactly one physical orientation fits.
    return np.array(
        [
            [0.0, 0.0], [120.0, 0.0], [260.0, 10.0], [400.0, 0.0],
            [10.0, 90.0], [150.0, 80.0], [300.0, 120.0], [390.0, 100.0],
            [0.0, 200.0], [90.0, 260.0], [230.0, 210.0], [410.0, 250.0],
            [40.0, 330.0], [200.0, 300.0], [350.0, 340.0],
        ]
    )


def symmetric_points():
    # Rectangular grid: several signed-axis orientations fit equally well.
    xs, ys = np.meshgrid(np.linspace(0.0, 400.0, 5), np.linspace(0.0, 400.0, 5))
    return np.column_stack([xs.ravel(), ys.ravel()])


def fe_dataset(points_2d):
    coordinates = np.column_stack([points_2d, np.zeros(len(points_2d))])
    node_ids = np.asarray(
        [f"PLATE-1:{index + 1}" for index in range(len(coordinates))], dtype=object
    )
    modes = []
    for number, frequency in enumerate(FREQUENCIES, start=1):
        shape = np.sin(number * coordinates[:, 0] / 130.0) * np.cos(
            (number + 1) * coordinates[:, 1] / 170.0
        )
        vectors = np.zeros((len(coordinates), 3), dtype=complex)
        vectors[:, 2] = shape
        mode = ModeShape(
            number=number,
            frequency_hz=frequency,
            node_ids=node_ids,
            coordinates=coordinates,
            vectors=vectors,
            metadata={"step_name": "Frequency"},
        )
        mode.measured_dofs = np.ones((len(coordinates), 3), dtype=bool)
        modes.append(mode)
    return ModalDataset(
        source_name="Abaqus ODB",
        source_path=Path("C:/temp/plate.odb"),
        modes=modes,
        metadata={"D11": 1.0e5, "Ex": 7.0e10, "basis_km_hash": "f" * 64},
    )


def experimental_dataset(fe, source_path, masks=None, drop_mask_mode=None):
    reference = fe.modes[0]
    node_ids = np.asarray([101 + index for index in range(len(reference.node_ids))], dtype=object)
    coordinates = reference.coordinates * 1.0e-3  # FE in mm, experiment in m
    default_mask = np.zeros((len(node_ids), 3), dtype=bool)
    default_mask[:, 2] = True  # only the out-of-plane component is measured
    modes = []
    for index, fe_mode in enumerate(fe.modes):
        mode = ModeShape(
            number=index + 1,
            frequency_hz=fe_mode.frequency_hz * 1.02,
            node_ids=node_ids,
            coordinates=coordinates,
            vectors=fe_mode.vectors.copy(),
        )
        if index != drop_mask_mode:
            mode.measured_dofs = (default_mask if masks is None else masks[index]).copy()
        modes.append(mode)
    return ModalDataset(
        source_name="Test UNV",
        source_path=Path(source_path),
        modes=modes,
        metadata={"modal_set_key": "polymax-set-1", "modal_set_name": "PolyMAX 1"},
    )


class FactoryFixture(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.source = self.directory / "SP13.unv"
        self.source.write_bytes(b"experimental modal file content")
        self.other_source = self.directory / "SP05.unv"
        self.other_source.write_bytes(b"another experiment")

    def unique_result(self, **experimental_kwargs):
        fe = fe_dataset(asymmetric_points())
        experiment = experimental_dataset(fe, self.source, **experimental_kwargs)
        return compare_modal_datasets(fe, experiment, geometry_calibration=CALIBRATION)

    def ambiguous_candidates(self):
        fe = fe_dataset(symmetric_points())
        experiment = experimental_dataset(fe, self.source)
        with self.assertRaises(GeometryOrientationAmbiguousError) as context:
            compare_modal_datasets(fe, experiment, geometry_calibration=CALIBRATION)
        return fe, experiment, context.exception.ambiguous_candidates

    def binding(self, candidate, source=None, calibration=CALIBRATION):
        # Same structure the GUI stores in confirm_orientation_candidate.
        return {
            "orientation_source": "user_confirmed",
            "candidate_identity": candidate["candidate_id"],
            "candidate": dict(candidate),
            "experimental_source_identity": experimental_source_identity(source or self.source),
            "calibration_state": calibration.to_dict(),
            "calibration_fingerprint": calibration_fingerprint(calibration.to_dict()),
        }

    def confirmed_result(self, choice=1):
        fe, experiment, candidates = self.ambiguous_candidates()
        candidate = candidates[choice]
        result = compare_modal_datasets(
            fe, experiment, geometry_calibration=CALIBRATION, orientation_selection=candidate
        )
        return result, candidate


class UnambiguousGeometryTests(FactoryFixture):
    # A
    def test_unique_geometry_builds_registration(self):
        result = self.unique_result()
        self.assertEqual(result.metadata["orientation_source"], "geometry_unique")
        registration = build_frozen_registration(result, calibration=CALIBRATION)
        self.assertIsInstance(registration, FrozenRegistration)
        self.assertEqual(
            registration.orientation_candidate_id,
            reviewed_core._candidate_summary(result.geometry)["candidate_id"],
        )
        self.assertEqual(registration.experimental_modal_set_identity, "polymax-set-1")
        self.assertEqual(dict(registration.calibration), CALIBRATION.to_dict())
        self.assertEqual(
            registration.calibration_fingerprint, calibration_fingerprint(CALIBRATION.to_dict())
        )
        self.assertEqual(FrozenRegistration.from_dict(registration.to_dict()), registration)

    # E
    def test_fe_geometry_identity_comes_from_the_fe_dataset(self):
        result = self.unique_result()
        registration = build_frozen_registration(result, calibration=CALIBRATION)
        self.assertEqual(
            registration.to_dict()["fe_geometry_identity"],
            modal_dataset_geometry_identity(result.abaqus),
        )
        self.assertEqual(
            registration.fe_geometry_identity["schema_version"], "fe-geometry-identity/2"
        )
        self.assertNotIn("dof_count", registration.fe_geometry_identity)

    # F
    def test_mapping_matches_the_finished_comparison(self):
        result = self.unique_result()
        registration = build_frozen_registration(result, calibration=CALIBRATION)
        experimental_reference = result.experimental.sorted_modes()[0]
        fe_reference = result.abaqus.sorted_modes()[0]
        self.assertEqual(
            registration.experimental_node_ids, tuple(experimental_reference.node_ids.tolist())
        )
        self.assertEqual(
            registration.mapped_fe_node_ids,
            tuple(fe_reference.node_ids[result.geometry.experimental_to_abaqus].tolist()),
        )
        self.assertTrue(all(node.startswith("PLATE-1:") for node in registration.mapped_fe_node_ids))
        masks = experimental_measurement_masks(
            result.experimental.sorted_modes(), experimental_reference.node_ids
        )
        self.assertEqual(registration.measured_dof_contract, tuple(map(tuple, masks[0].tolist())))
        self.assertTrue(all(row == (False, False, True) for row in registration.measured_dof_contract))

    # H
    def test_transform_is_copied_not_recomputed(self):
        result = self.unique_result()
        registration = build_frozen_registration(result, calibration=CALIBRATION)
        self.assertEqual(registration.rotation, tuple(map(tuple, result.geometry.rotation.tolist())))
        self.assertEqual(registration.translation, tuple(result.geometry.translation.tolist()))
        self.assertEqual(
            registration.coordinate_scales, tuple(result.geometry.coordinate_scales.tolist())
        )
        metrics = registration.registration_metrics
        self.assertEqual(metrics["matched_fraction"], result.geometry.matched_fraction)
        self.assertEqual(metrics["mapping_rms"], result.metadata["mapping_rms"])
        self.assertEqual(metrics["mapping_max_residual"], result.metadata["mapping_max_residual"])
        self.assertEqual(metrics["orientation_source"], "geometry_unique")

    # I
    def test_source_identity_is_the_content_identity(self):
        result = self.unique_result()
        registration = build_frozen_registration(result, calibration=CALIBRATION)
        self.assertEqual(
            dict(registration.experimental_source_identity),
            experimental_source_content_identity(self.source),
        )
        self.assertIn("sha256", registration.experimental_source_identity)

    def test_injected_identity_must_be_a_content_identity(self):
        result = self.unique_result()
        injected = {"path": "synthetic", "size": 1, "mtime_ns": 1, "sha256": "a" * 64}
        registration = build_frozen_registration(
            result, calibration=CALIBRATION, experimental_source_identity=injected
        )
        self.assertEqual(dict(registration.experimental_source_identity), injected)
        legacy = experimental_source_identity(self.source)
        with self.assertRaisesRegex(RegistrationRefusedError, "content identity"):
            build_frozen_registration(
                result, calibration=CALIBRATION, experimental_source_identity=legacy
            )

    def test_missing_source_file_does_not_fall_back_to_legacy_identity(self):
        result = self.unique_result()
        self.source.unlink()
        with self.assertRaisesRegex(RegistrationRefusedError, "content identity"):
            build_frozen_registration(result, calibration=CALIBRATION)

    # J
    def test_mutating_result_after_build_does_not_change_registration(self):
        result = self.unique_result()
        registration = build_frozen_registration(result, calibration=CALIBRATION)
        snapshot = registration.to_dict()
        result.geometry.rotation[0, 0] = 99.0
        result.geometry.translation[:] = 5.0
        result.geometry.coordinate_scales[:] = 2.0
        result.geometry.experimental_to_abaqus[:] = 0
        result.metadata["mapping_rms"] = -1.0
        result.metadata["geometry_calibration"]["mode"] = "tampered"
        for mode in result.experimental.modes:
            mode.node_ids[0] = 999
            mode.measured_dofs[:] = True
        for mode in result.abaqus.modes:
            mode.node_ids[0] = "OTHER:1"
        self.assertEqual(registration.to_dict(), snapshot)

    # K
    def test_no_full_model_contamination(self):
        result = self.unique_result()
        registration = build_frozen_registration(result, calibration=CALIBRATION)
        encoded = json.dumps(registration.to_dict()).lower()
        for token in ("d11", "\"ex\"", "basis_km_hash", "stiffness", "material", "mac", "frequency"):
            with self.subTest(token):
                self.assertNotIn(token, encoded)
        names = {field.name for field in dataclasses.fields(registration)}
        self.assertFalse({"stiffness", "basis_km_hash", "material_parameters", "model_template"} & names)


class ConfirmationPolicyTests(FactoryFixture):
    # B
    def test_confirmed_result_without_binding_is_refused(self):
        result, _ = self.confirmed_result()
        self.assertEqual(result.metadata["orientation_source"], "user_confirmed")
        with self.assertRaisesRegex(RegistrationRefusedError, "confirmation"):
            build_frozen_registration(result, calibration=CALIBRATION)

    def test_result_without_recorded_orientation_source_is_refused(self):
        result = self.unique_result()
        del result.metadata["orientation_source"]
        with self.assertRaisesRegex(RegistrationRefusedError, "orientation_source"):
            build_frozen_registration(result, calibration=CALIBRATION)

    # C
    def test_confirmed_result_with_valid_binding_builds(self):
        result, candidate = self.confirmed_result(choice=1)
        registration = build_frozen_registration(
            result, calibration=CALIBRATION, orientation_binding=self.binding(candidate)
        )
        self.assertEqual(registration.orientation_candidate_id, candidate["candidate_id"])
        self.assertEqual(registration.registration_metrics["orientation_source"], "user_confirmed")
        self.assertEqual(registration.rotation, tuple(map(tuple, result.geometry.rotation.tolist())))

    # D
    def test_stale_binding_for_another_source_is_refused(self):
        result, candidate = self.confirmed_result()
        with self.assertRaisesRegex(RegistrationRefusedError, "not valid"):
            build_frozen_registration(
                result,
                calibration=CALIBRATION,
                orientation_binding=self.binding(candidate, source=self.other_source),
            )

    def test_stale_binding_for_another_calibration_is_refused(self):
        result, candidate = self.confirmed_result()
        with self.assertRaisesRegex(RegistrationRefusedError, "not valid"):
            build_frozen_registration(
                result,
                calibration=CALIBRATION,
                orientation_binding=self.binding(candidate, calibration=OTHER_CALIBRATION),
            )

    def test_binding_for_another_candidate_is_refused(self):
        _, _, candidates = self.ambiguous_candidates()
        result, _ = self.confirmed_result(choice=1)
        with self.assertRaisesRegex(RegistrationRefusedError, "candidate"):
            build_frozen_registration(
                result, calibration=CALIBRATION, orientation_binding=self.binding(candidates[0])
            )

    def test_stale_binding_is_refused_even_for_unique_geometry(self):
        result = self.unique_result()
        candidate = reviewed_core._candidate_summary(result.geometry)
        with self.assertRaisesRegex(RegistrationRefusedError, "not valid"):
            build_frozen_registration(
                result,
                calibration=CALIBRATION,
                orientation_binding=self.binding(candidate, source=self.other_source),
            )

    def test_comparison_run_with_another_calibration_is_refused(self):
        result = self.unique_result()
        with self.assertRaisesRegex(RegistrationRefusedError, "calibration"):
            build_frozen_registration(result, calibration=OTHER_CALIBRATION)

    # G
    def test_factory_never_reselects_orientation_or_reads_modal_evidence(self):
        result, candidate = self.confirmed_result()
        expected = build_frozen_registration(
            result, calibration=CALIBRATION, orientation_binding=self.binding(candidate)
        )
        forbidden = AssertionError("orientation must not be re-selected")
        with patch.object(reviewed_core, "geometry_alignment_candidates", side_effect=forbidden), \
            patch.object(reviewed_core, "_select_unambiguous_geometry", side_effect=forbidden), \
            patch.object(reviewed_core, "_select_user_confirmed_geometry", side_effect=forbidden), \
            patch.object(reviewed_core, "compare_modal_datasets", side_effect=forbidden), \
            patch.object(reviewed_core, "modal_assurance_criterion", side_effect=forbidden):
            stripped = copy.copy(result)
            stripped.mac_matrix = None
            stripped.frequency_error_matrix = None
            stripped.pairs = []
            stripped.candidate_diagnostics = []
            stripped.diagnostic_summaries = {}
            rebuilt = build_frozen_registration(
                stripped, calibration=CALIBRATION, orientation_binding=self.binding(candidate)
            )
        self.assertEqual(rebuilt.registration_hash, expected.registration_hash)


class MeasurementContractTests(FactoryFixture):
    def test_mode_without_explicit_mask_is_refused_not_inferred(self):
        result = self.unique_result(drop_mask_mode=1)
        with self.assertRaisesRegex(RegistrationRefusedError, "explicit measured-DOF mask"):
            build_frozen_registration(result, calibration=CALIBRATION)

    def test_modes_with_different_masks_are_refused(self):
        count = len(asymmetric_points())
        first = np.zeros((count, 3), dtype=bool)
        first[:, 2] = True
        second = first.copy()
        second[0, 0] = True
        result = self.unique_result(masks=[first, second, first])
        with self.assertRaisesRegex(RegistrationRefusedError, "differs between experimental modes"):
            build_frozen_registration(result, calibration=CALIBRATION)

    def test_missing_modal_set_key_is_stored_as_none(self):
        result = self.unique_result()
        result.experimental.metadata.pop("modal_set_key")
        registration = build_frozen_registration(result, calibration=CALIBRATION)
        self.assertIsNone(registration.experimental_modal_set_identity)


if __name__ == "__main__":
    unittest.main()
