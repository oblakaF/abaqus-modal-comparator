"""M1 stage-gate verification: the complete accepted chain on every accepted fixture.

fixture manifest -> M1.1 source policy -> M1.2 production loader -> M1.3 ExternalPolyMAXProvider
-> M1.4 experimental QC -> Auto-ID experimental input.

Real data only; a fixture whose store root is not configured is skipped with the reason.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import universal_reader
from domain.experiment_fixture import (
    fixture_roots_from_environment,
    load_experiment_fixture_manifest,
    resolve_external_file,
)
from domain.experimental_qc import ExperimentalQCStatus
from domain.modal_input_source import IdentificationInputSourceRefusal, ModalInputSource, require_identification_input
from domain.registration import FrozenRegistration
from modal_core import ModalDataset
from services import experimental_qc as qc
from services.external_polymax_provider import EXTERNAL_POLYMAX_PROVIDER, admitted_provider_registry
from services.production_modal_input import load_production_modal_input
from universal_frf_review import modes_from_frf_datasets


MANIFEST_PATH = ROOT / "docs" / "auto_id" / "fixtures" / "real_experiment_fixtures.json"
# D-028: fixture-specific gate references (pinned SP13 repeat-a PolyMAX values).
GATE_REFERENCES_HZ = {"SP13/best": (205.65, 212.66, 228.61)}
GATE_TOLERANCE_HZ = 0.05
KNOWN_FALSE_PEAK_HZ = {"SP13/best": 217.5}


class M1StageGateTests(unittest.TestCase):
    def test_complete_m1_chain_on_accepted_fixtures(self):
        roots = fixture_roots_from_environment()
        for fixture in load_experiment_fixture_manifest(MANIFEST_PATH).fixtures:
            with self.subTest(fixture=fixture.fixture_id):
                store = fixture.experimental_source.location.store
                if store not in roots:
                    self.skipTest(f"{fixture.fixture_id}: store {store!r} not configured")
                result = qc.prepare_auto_id_experimental_input(fixture.fixture_id, roots=roots)
                output, report, dataset = result.provider_output.output, result.qc_report, result.dataset
                provenance = output.provenance
                modes = dataset.sorted_modes()

                # Pinned SHA / source identity and modal set.
                self.assertEqual(provenance["source_file"]["sha256"], fixture.experimental_source.sha256)
                self.assertEqual(provenance["frf_source_sha256"], fixture.experimental_source.sha256)
                resolve_external_file(fixture.experimental_source, roots)  # size + SHA-256 re-verified
                self.assertEqual(dataset.metadata["modal_set_key"], fixture.modal_set.name)
                self.assertEqual(provenance["modal_set"], fixture.modal_set.name)

                # Counts and U3 contract.
                self.assertEqual(len(modes), fixture.modal_set.mode_count)
                self.assertEqual(len(modes[0].node_ids), fixture.modal_set.measurement_point_count)
                self.assertEqual(tuple(provenance["measured_dofs"]), ("U3",))
                self.assertEqual(fixture.modal_set.measured_dofs, ("U3",))

                # FrozenRegistration and FE identity.
                with open(ROOT / fixture.registration.path, encoding="utf-8") as handle:
                    registration = FrozenRegistration.from_dict(json.load(handle))
                self.assertEqual(registration.registration_hash, fixture.registration.registration_hash)
                self.assertEqual(provenance["registration_hash"], fixture.registration.registration_hash)
                self.assertEqual(registration.fe_geometry_identity["sha256"], fixture.fe.geometry_identity.sha256)
                self.assertEqual(provenance["fe_geometry_sha256"], fixture.fe.geometry_identity.sha256)
                self.assertEqual([int(node) for node in modes[0].node_ids], list(registration.experimental_node_ids))

                # Provider provenance and admission.
                self.assertEqual(output.provider, EXTERNAL_POLYMAX_PROVIDER)
                self.assertIs(admitted_provider_registry().require(output.provider), EXTERNAL_POLYMAX_PROVIDER)
                self.assertEqual(provenance["pole_selection"], "external_frozen_selection")
                self.assertIs(result.provider_output.source_classification.source, ModalInputSource.CURVE_FITTED)

                # Damping from the stored PolyMAX poles.
                for mode in modes:
                    real, imag = mode.metadata["polymax_pole"]
                    self.assertAlmostEqual(mode.damping_ratio, -real / math.hypot(real, imag), places=15)
                    self.assertAlmostEqual(mode.frequency_hz, abs(imag) / (2.0 * math.pi), places=9)

                # Hard QC checks pass.
                self.assertTrue(report.admissible)
                for name in (qc.PROVENANCE, qc.MEASUREMENT_CONTRACT, qc.FRF_COMPLETENESS):
                    self.assertIs(report.check(name).status, ExperimentalQCStatus.PASS, name)

                # Dataset unchanged through QC, and equal to the M1.2 production input.
                self.assertIs(dataset, output.dataset)
                production = load_production_modal_input(fixture.fixture_id, roots=roots)
                for mode, reference in zip(modes, production.dataset.sorted_modes(), strict=True):
                    self.assertEqual(mode.frequency_hz, reference.frequency_hz)
                    self.assertEqual(list(mode.node_ids), list(reference.node_ids))
                    np.testing.assert_array_equal(mode.vectors, reference.vectors)

                # D-028 fixture-specific references.
                frequencies = np.array([mode.frequency_hz for mode in modes])
                for reference in GATE_REFERENCES_HZ.get(fixture.fixture_id, ()):
                    self.assertLessEqual(float(np.min(np.abs(frequencies - reference))), GATE_TOLERANCE_HZ)
                if fixture.fixture_id in KNOWN_FALSE_PEAK_HZ:
                    self.assertGreater(float(np.min(np.abs(frequencies - KNOWN_FALSE_PEAK_HZ[fixture.fixture_id]))), 1.0)

                # Peak-derived modes from the same export cannot substitute.
                datasets = universal_reader._read_universal_datasets(resolve_external_file(fixture.experimental_source, roots))
                geometry, _ = universal_reader._read_geometry(datasets)
                peak_modes, peak_metadata = modes_from_frf_datasets(
                    [item for item in datasets if universal_reader._dataset_type(item) == 58], geometry)
                self.assertTrue(peak_modes)
                with self.assertRaises(IdentificationInputSourceRefusal) as caught:
                    require_identification_input(ModalDataset("peak", Path("peak"), peak_modes, metadata=peak_metadata))
                self.assertIs(caught.exception.source, ModalInputSource.PEAK_DERIVED)


if __name__ == "__main__":
    unittest.main()
