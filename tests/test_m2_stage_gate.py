"""M2 stage gate on real data: passports reproduce the accepted FrozenRegistrations (SPEC §6 S2, §11).

Needs the data stores AUTO_ID_FIXTURE_ROOT_SNADWICH (experimental exports) and
AUTO_ID_FIXTURE_ROOT_CARBON_PROJECT_ARCHIVE (pinned FE geometry); skips with the reason otherwise.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import modal_core
import reviewed_core
from domain.experiment_fixture import fixture_roots_from_environment, load_experiment_fixture_manifest, resolve_external_file
from domain.experimental_qc import ExperimentalQCStatus as S
from domain.registration import FrozenRegistration
from domain.specimen_manifest import RegistrationBasisStatus, UncertaintyAvailability, load_specimen_manifest
from services import experimental_qc as qc
from services.physical_registration import (
    ProductionReadinessRefusal,
    build_physical_registration,
    load_experimental_geometry,
    load_fe_geometry,
)
from services.registration_uncertainty import UncertaintyStatus, evaluate_registration_uncertainty


SPECIMENS = ROOT / "docs" / "auto_id" / "specimens"
FIXTURES = ROOT / "docs" / "auto_id" / "fixtures" / "real_experiment_fixtures.json"


class M2StageGateTests(unittest.TestCase):
    def test_passports_reproduce_accepted_registrations(self):
        roots = fixture_roots_from_environment()
        fixtures = load_experiment_fixture_manifest(FIXTURES)
        for name in ("SP02", "SP13"):
            with self.subTest(specimen=name):
                passport = load_specimen_manifest(SPECIMENS / f"{name}.specimen.json")
                fixture = fixtures.fixture(passport.acquisition.fixture_id)
                stores = {passport.fe_reference.geometry_file.location.store,
                          fixture.experimental_source.location.store}
                missing = sorted(stores - set(roots))
                if missing:
                    self.skipTest(f"{name}: data stores {missing} not configured")
                fe = load_fe_geometry(passport, roots)
                experimental = load_experimental_geometry(passport, roots, fixtures)

                boom = AssertionError("registration must not consult modal agreement")
                with patch.object(modal_core, "modal_assurance_criterion", side_effect=boom), \
                        patch.object(reviewed_core, "modal_assurance_criterion", side_effect=boom), \
                        patch.object(reviewed_core, "_mac_matrix_for_geometry", side_effect=boom), \
                        patch.object(reviewed_core, "_frequency_error_matrices", side_effect=boom):
                    result = build_physical_registration(passport, roots=roots, fixture_manifest=fixtures,
                                                         fe_geometry=fe, experimental=experimental)
                again = build_physical_registration(passport, roots=roots, fixture_manifest=fixtures,
                                                    fe_geometry=fe, experimental=experimental)

                with open(ROOT / fixture.registration.path, encoding="utf-8") as handle:
                    accepted = FrozenRegistration.from_dict(json.load(handle))
                # Historical accepted-registration replay / regression compatibility: full content equality.
                self.assertEqual(result.registration.registration_hash, fixture.registration.registration_hash)
                self.assertEqual(result.registration.to_dict(), accepted.to_dict())
                self.assertEqual(again.registration.registration_hash, result.registration.registration_hash)
                self.assertEqual(result.registration.fe_geometry_identity["sha256"], fixture.fe.geometry_identity.sha256)
                self.assertEqual(result.source_identity_basis, "legacy_accepted_registration")

                # Two separate facts: the basis is a legacy replay (not SPEC §11 evidence), and no
                # calibration uncertainty is measured.
                self.assertIs(result.registration_basis_status, RegistrationBasisStatus.LEGACY_REPLAY)
                self.assertIs(result.uncertainty_availability, UncertaintyAvailability.NOT_AVAILABLE)
                self.assertEqual(result.missing_physical_evidence, (
                    "physical registration reference (corner-A marker or measured scan-to-panel-edge offsets)",))
                self.assertEqual(result.missing_uncertainty, (
                    "geometry_calibration.uncertainty.translation_mm",
                    "geometry_calibration.uncertainty.scale_rel",
                    "geometry_calibration.uncertainty.rotation_deg"))

                # Current production physical readiness: NOT_READY, with the missing evidence explicit.
                self.assertFalse(result.production_ready)
                with self.assertRaises(ProductionReadinessRefusal) as caught:
                    result.require_production_ready()
                reasons = caught.exception.reasons
                self.assertTrue(any("LEGACY_REPLAY" in reason for reason in reasons))
                self.assertIn("missing physical registration reference (corner-A marker or measured "
                              "scan-to-panel-edge offsets)", reasons)
                self.assertIn("physical_specimen_id is not recorded", reasons)
                self.assertIs(result.registration_basis_status, RegistrationBasisStatus.LEGACY_REPLAY)

                # Content-based compatibility on this machine's copy (path/mtime not part of the check).
                path = resolve_external_file(fixture.experimental_source, roots)
                content = {"sha256": fixture.experimental_source.sha256, "size": path.stat().st_size,
                           "path": str(path), "mtime_ns": path.stat().st_mtime_ns}
                self.assertTrue(result.registration.check_content_compatible(content, fe.identity))

                # M2.4: no measured uncertainty -> NOT_AVAILABLE, registration-limited not evaluable.
                report = evaluate_registration_uncertainty(
                    result.registration, passport.geometry_calibration.uncertainty, fe, result.surface_node_ids,
                    experimental[0], {}, [], fixture.modal_set.measured_dofs)
                self.assertIs(report.status, UncertaintyStatus.NOT_AVAILABLE)
                self.assertIsNone(report.registration_limited)

                # M1 integration: no passport threshold -> suspension NOT_AVAILABLE; hard QC checks pass.
                chain = qc.prepare_auto_id_experimental_input(passport.acquisition.fixture_id, roots=roots,
                                                              specimen_passport=passport)
                self.assertIs(chain.qc_report.check(qc.SUSPENSION_THRESHOLD).status, S.NOT_AVAILABLE)
                self.assertTrue(chain.qc_report.admissible)
                self.assertEqual(chain.eligibility.excluded_modes, ())
                self.assertEqual(len(chain.dataset.modes), fixture.modal_set.mode_count)


if __name__ == "__main__":
    unittest.main()
