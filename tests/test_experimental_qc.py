from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import universal_reader
from domain.experiment_fixture import (
    FixtureSourceUnavailableError,
    fixture_roots_from_environment,
    load_experiment_fixture_manifest,
)
from domain.experimental_qc import (
    ExperimentalQCCheck,
    ExperimentalQCRefusal,
    ExperimentalQCReport,
    ExperimentalQCStatus,
)
from domain.modal_fitting import FrfInput, ModalFittingProviderRegistry, canonical_hash
from fixture_support import MANIFEST_PATH, build_synthetic_fixture_workspace, manifest_from_record
from modal_core import ModalDataset, ModeShape
from services import experimental_qc as qc
from services.external_polymax_provider import prepare_external_polymax_modal_dataset, prepare_frf_input
from services.production_modal_input import load_production_modal_input
from test_external_polymax_provider import synthetic_export


S = ExperimentalQCStatus
HARD = (qc.PROVENANCE, qc.MEASUREMENT_CONTRACT, qc.FRF_COMPLETENESS)


def mode(number, frequency, damping=0.002, shape=(1.0, -0.5, 0.25), z_only=True):
    vectors = np.zeros((3, 3), dtype=complex)
    vectors[:, 2] = shape
    if not z_only:
        vectors[:, 0] = 0.3
    return ModeShape(number, frequency, np.array([101, 102, 103], dtype=object), np.zeros((3, 3)), vectors,
                     damping_ratio=damping)


def frf(df=0.1, coherence=None, low=1.0, high=300.0):
    axis = np.arange(low, high + df / 2, df)
    return FrfInput(frequency_hz=axis, h=np.ones((3, 1, axis.size), dtype=complex),
                    response_keys=((101, 3), (102, 3), (103, 3)), reference_keys=((101, 3),),
                    quantity="velocity/force", coherence_status="computed" if coherence is not None else "unavailable",
                    coherence=None if coherence is None else np.full(axis.size, coherence), source_sha256="a" * 64)


class SyntheticChainTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.workspace = build_synthetic_fixture_workspace(Path(temp.name))
        self.manifest = manifest_from_record(self.workspace.record)
        self.fixture = self.manifest.fixture("SYN/set-a")
        self.datasets = synthetic_export()
        patcher = patch.object(universal_reader, "_read_universal_datasets", side_effect=lambda path: self.datasets)
        patcher.start()
        self.addCleanup(patcher.stop)

    def chain(self):
        return qc.prepare_auto_id_experimental_input("SYN/set-a", roots=self.workspace.roots, manifest=self.manifest,
                                                     repo_root=self.workspace.repo_root)

    def validated_and_frf(self):
        validated = prepare_external_polymax_modal_dataset("SYN/set-a", roots=self.workspace.roots,
                                                           manifest=self.manifest, repo_root=self.workspace.repo_root)
        return validated, prepare_frf_input(self.fixture, self.workspace.roots)

    def evaluate(self, validated, frf_input, fixture=None, **kwargs):
        return qc.evaluate_experimental_qc(validated, frf_input, fixture or self.fixture,
                                           repo_root=self.workspace.repo_root, **kwargs)

    # Core -------------------------------------------------------------------------------
    def test_valid_report(self):
        result = self.chain()
        report = result.qc_report
        self.assertIsInstance(report, ExperimentalQCReport)
        self.assertTrue(report.admissible)
        self.assertEqual(report.fixture_id, "SYN/set-a")
        self.assertEqual(report.provider, {"name": "external-polymax", "version": "1", "kind": "external"})
        self.assertEqual(report.modal_source, "external PolyMAX modal preparation/1")
        for name in HARD:
            self.assertIs(report.check(name).status, S.PASS, name)
        self.assertIs(report.check(qc.COHERENCE_QUALITY).status, S.PASS)
        self.assertEqual([check.name for check in report.checks],
                         [qc.PROVENANCE, qc.MEASUREMENT_CONTRACT, qc.FRF_COMPLETENESS, qc.COHERENCE_QUALITY,
                          qc.FREQUENCY_RESOLUTION, qc.MODAL_CONFIDENCE])
        self.assertIs(result.dataset, result.provider_output.output.dataset)

    def test_report_is_deterministic(self):
        first, second = self.chain().qc_report, self.chain().qc_report
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.content_hash, second.content_hash)

    def test_provenance_is_preserved_and_dataset_untouched(self):
        validated, frf_input = self.validated_and_frf()
        before = copy.deepcopy(validated.output.dataset)
        report = self.evaluate(validated, frf_input)
        after = validated.output.dataset
        self.assertEqual(report.provenance_reference["provenance_hash"],
                         canonical_hash(qc._jsonable(validated.output.provenance)))
        self.assertEqual(report.provenance_reference["frf_content_hash"], frf_input.content_hash)
        self.assertEqual(report.provenance_reference["source_sha256"], self.fixture.experimental_source.sha256)
        self.assertEqual([m.number for m in after.modes], [m.number for m in before.modes])
        for a, b in zip(after.modes, before.modes):
            self.assertEqual((a.frequency_hz, a.damping_ratio, a.metadata), (b.frequency_hz, b.damping_ratio, b.metadata))
            np.testing.assert_array_equal(a.vectors, b.vectors)

    # Hard failures ----------------------------------------------------------------------
    def test_missing_source_is_refused(self):
        self.workspace.source_file.unlink()
        with self.assertRaises(FixtureSourceUnavailableError):
            self.chain()

    def test_invalid_fixture_fails(self):
        validated, frf_input = self.validated_and_frf()
        for changes in ({"fixture_id": "SYN/other"}, {"modal_set__mode_count": 3},
                        {"modal_set__measurement_point_count": 4}):
            with self.subTest(changes=changes):
                record = manifest_from_record(self.workspace.record, **changes).fixtures[0]
                report = self.evaluate(validated, frf_input, record)
                self.assertIs(report.status, S.FAIL)
                self.assertFalse(report.admissible)

    def test_invalid_dof_contract_fails(self):
        validated, frf_input = self.validated_and_frf()
        dataset = copy.deepcopy(validated.output.dataset)
        # An unmeasured DOF now carries data and is declared measured.  The explicit mask matters because,
        # once the app's install_* layers are active, the reader attaches explicit masks that take precedence.
        dataset.modes[0].vectors[:, 0] = 0.3
        mask = np.zeros(dataset.modes[0].vectors.shape, dtype=bool)
        mask[:, [0, 2]] = True
        dataset.modes[0].measured_dofs = mask
        tampered = replace(validated, output=replace(validated.output, dataset=dataset))
        report = self.evaluate(tampered, frf_input)
        self.assertIs(report.check(qc.MEASUREMENT_CONTRACT).status, S.FAIL)
        self.assertFalse(report.admissible)

    def test_broken_provenance_fails(self):
        validated, frf_input = self.validated_and_frf()
        provenance = dict(validated.output.provenance)
        cases = {
            "wrong FRF content hash": {**provenance, "frf_content_hash": "0" * 64},
            "missing source file": {key: value for key, value in provenance.items() if key != "source_file"},
            "wrong configuration hash": {**provenance, "configuration_hash": "1" * 64},
        }
        for name, broken in cases.items():
            with self.subTest(name):
                report = self.evaluate(replace(validated, output=replace(validated.output, provenance=broken)), frf_input)
                self.assertIs(report.check(qc.PROVENANCE).status, S.FAIL)
                self.assertFalse(report.admissible)
        report = self.evaluate(validated, frf_input, registry=ModalFittingProviderRegistry())
        self.assertIs(report.check(qc.PROVENANCE).status, S.FAIL)

    def test_wrong_frf_source_fails(self):
        validated, frf_input = self.validated_and_frf()
        report = self.evaluate(validated, replace(frf_input, source_sha256="f" * 64))
        self.assertIs(report.check(qc.FRF_COMPLETENESS).status, S.FAIL)
        self.assertFalse(report.admissible)

    def test_chain_refuses_on_hard_failure(self):
        validated, frf_input = self.validated_and_frf()
        broken = replace(validated, output=replace(validated.output, provenance={
            **validated.output.provenance, "frf_content_hash": "0" * 64}))
        failing = self.evaluate(broken, frf_input)
        with patch.object(qc, "evaluate_experimental_qc", return_value=failing):
            with self.assertRaises(ExperimentalQCRefusal) as caught:
                self.chain()
        self.assertIs(caught.exception.report, failing)
        self.assertFalse(issubclass(ExperimentalQCRefusal, (ValueError, RuntimeError)))

    # Diagnostics ------------------------------------------------------------------------
    def test_missing_coherence_is_not_available_not_failure(self):
        self.datasets = synthetic_export(with_coherence=False)
        report = self.chain().qc_report
        check = report.check(qc.COHERENCE_QUALITY)
        self.assertIs(check.status, S.NOT_AVAILABLE)
        self.assertEqual([w.code for w in check.warnings], ["COHERENCE_NOT_AVAILABLE"])
        self.assertTrue(report.admissible)
        self.assertIn("check:coherence_quality", report.not_available)

    def test_unavailable_uncertainty_is_recorded_not_fabricated(self):
        report = self.chain().qc_report
        check = report.check(qc.MODAL_CONFIDENCE)
        # The synthetic modes have proportional shapes, so the SPEC AutoMAC flag also fires.
        self.assertIs(check.status, S.WARNING)
        self.assertIn("AUTOMAC_INDISTINGUISHABLE", [w.code for w in check.warnings])
        values = {m.name: m.value for m in check.metrics if m.mode == 1}
        self.assertIsNone(values["frequency_uncertainty"])
        self.assertIsNone(values["damping_uncertainty"])
        self.assertIsNone(values["shape_uncertainty"])
        self.assertIn("UNCERTAINTY_NOT_AVAILABLE", [w.code for w in check.warnings])
        self.assertTrue(report.admissible)


class DiagnosticRuleTests(unittest.TestCase):
    def test_close_mode_warning(self):
        dataset = ModalDataset("x", Path("x"), [mode(1, 100.0), mode(2, 102.0), mode(3, 150.0)])
        check = qc._resolution_check(frf(df=0.01), dataset)
        close = [w for w in check.warnings if w.code == "CLOSE_MODES"]
        self.assertEqual(len(close), 1)
        self.assertEqual(close[0].modes, (1, 2))
        self.assertEqual(close[0].rule, "SPEC §12.4")
        self.assertIs(check.status, S.WARNING)

    def test_insufficient_frequency_resolution(self):
        dataset = ModalDataset("x", Path("x"), [mode(1, 50.0, damping=0.002)])  # 2*zeta*f = 0.2 Hz
        coarse = qc._resolution_check(frf(df=0.25), dataset)
        fine = qc._resolution_check(frf(df=0.05), dataset)
        self.assertEqual([w.code for w in coarse.warnings], ["UNRESOLVED_RESONANCE"])
        self.assertIs(fine.status, S.PASS)
        bandwidth = {m.name: m.value for m in fine.metrics if m.mode == 1}
        self.assertAlmostEqual(bandwidth["half_power_bandwidth"], 0.2)
        self.assertAlmostEqual(bandwidth["bandwidth_in_lines"], 4.0)

    def test_missing_damping_is_reported_not_guessed(self):
        dataset = ModalDataset("x", Path("x"), [mode(1, 50.0, damping=None)])
        check = qc._resolution_check(frf(df=0.05), dataset)
        self.assertEqual([w.code for w in check.warnings], ["DAMPING_NOT_AVAILABLE"])
        self.assertIsNone(next(m.value for m in check.metrics if m.name == "half_power_bandwidth"))

    def test_low_coherence_flag(self):
        dataset = ModalDataset("x", Path("x"), [mode(1, 50.0)])
        self.assertEqual([w.code for w in qc._coherence_check(frf(coherence=0.5), dataset).warnings],
                         ["LOW_COHERENCE_AT_RESONANCE"])
        self.assertIs(qc._coherence_check(frf(coherence=0.95), dataset).status, S.PASS)

    def test_automac_and_phase_collinearity(self):
        self.assertAlmostEqual(qc._phase_collinearity(np.array([1.0, -0.5, 0.25])), 1.0)
        self.assertAlmostEqual(qc._phase_collinearity(np.array([1.0, -0.5, 0.25]) * np.exp(0.7j)), 1.0)
        self.assertLess(qc._phase_collinearity(np.array([1.0, 1.0j, -1.0, -1.0j])), 0.5)

    def test_diagnostic_checks_cannot_fail(self):
        with self.assertRaises(ValueError):
            ExperimentalQCCheck("coherence_quality", S.FAIL, hard=False, summary="x")


class RealFixtureQCTests(unittest.TestCase):
    """QC on every accepted manifest fixture (store permitting); hard checks must pass."""

    def test_accepted_fixtures_pass_hard_checks(self):
        roots = fixture_roots_from_environment()
        for fixture in load_experiment_fixture_manifest(MANIFEST_PATH).fixtures:
            with self.subTest(fixture=fixture.fixture_id):
                store = fixture.experimental_source.location.store
                if store not in roots:
                    self.skipTest(f"{fixture.fixture_id}: store {store!r} not configured")
                result = qc.prepare_auto_id_experimental_input(fixture.fixture_id, roots=roots)
                report = result.qc_report
                self.assertTrue(report.admissible)
                for name in HARD:
                    self.assertIs(report.check(name).status, S.PASS, name)
                self.assertEqual(report.provenance_reference["registration_hash"],
                                 fixture.registration.registration_hash)
                self.assertEqual(report.provenance_reference["source_sha256"], fixture.experimental_source.sha256)

                # M1.3 / M1.2 compatibility: QC hands on the provider dataset unchanged.
                production = load_production_modal_input(fixture.fixture_id, roots=roots)
                for produced, expected in zip(result.dataset.sorted_modes(), production.dataset.sorted_modes(),
                                              strict=True):
                    self.assertEqual(produced.frequency_hz, expected.frequency_hz)
                    np.testing.assert_array_equal(produced.vectors, expected.vectors)

                # Coherence availability follows the FRF data; uncertainty is never fabricated.
                coherence_status = prepare_frf_input(fixture, roots).coherence_status
                expected = S.NOT_AVAILABLE if coherence_status != "computed" else None
                if expected is not None:
                    self.assertIs(report.check(qc.COHERENCE_QUALITY).status, expected)
                self.assertIs(report.check(qc.MODAL_CONFIDENCE).status, S.NOT_AVAILABLE)

                # Deterministic.
                again = qc.prepare_auto_id_experimental_input(fixture.fixture_id, roots=roots).qc_report
                self.assertEqual(again.content_hash, report.content_hash)


if __name__ == "__main__":
    unittest.main()
