from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.modal_fitting import (
    FittingWorkflow,
    FrfInput,
    ModalFittingOutput,
    ModalFittingProvider,
    ModalFittingProviderIdentity,
    ModalFittingProviderRegistry,
    ModalFittingRefusal,
    ProviderKind,
    canonical_hash,
    run_modal_fitting,
    validate_fitting_output,
)
from domain.modal_input_source import IdentificationInputSourceRefusal, ModalInputSource, require_identification_input
from modal_core import ModalDataset, ModeShape


MOCK = ModalFittingProviderIdentity("mock-provider", "0.1", ProviderKind.INTERNAL, "mock modal fitting provider/0.1")
CONFIGURATION = {"band_hz": [5.0, 60.0], "model_order": 4}


def frf_input(**changes):
    values = dict(
        frequency_hz=np.linspace(1.0, 100.0, 100),
        h=np.ones((2, 1, 100), dtype=complex),
        response_keys=((1, 3), (2, 3)),
        reference_keys=((1, 3),),
        quantity="displacement/force",
        coherence_status="unavailable",
        source_sha256="a" * 64,
    )
    values.update(changes)
    return FrfInput(**values)


class MockProvider:
    """Returns a fixed synthetic result; it performs no fitting."""

    def __init__(self, identity=MOCK, **output_changes):
        self.identity = identity
        self.output_changes = output_changes
        self.calls = 0

    def fit(self, frf, configuration):
        self.calls += 1
        modes = [
            ModeShape(number, frequency, np.array([1, 2], dtype=object), np.zeros((2, 3)),
                      np.array([[0.0, 0.0, 1.0], [0.0, 0.0, -0.5]]), damping_ratio=0.002,
                      metadata={"mode_source": self.identity.mode_source})
            for number, frequency in ((1, 12.0), (2, 31.5))
        ]
        dataset = ModalDataset("mock fit", Path("mock.fit"), modes, metadata={"mode_source": self.identity.mode_source})
        output = ModalFittingOutput(
            dataset=dataset,
            provider=self.identity,
            provenance={
                "frf_source_sha256": frf.source_sha256,
                "frf_content_hash": frf.content_hash,
                "configuration": dict(configuration),
                "configuration_hash": canonical_hash(dict(configuration)),
                "frequency_band_hz": [5.0, 60.0],
                "pole_selection": "rule_based",
            },
            qc_summary={"status": "NOT_EVALUATED"},
            confidence={1: {"frequency_sd_hz": None, "damping_sd": None},
                        2: {"frequency_sd_hz": 0.01, "damping_sd": None}},
        )
        return replace(output, **self.output_changes)


class _ProviderFixture:
    def setUp(self):
        self.registry = ModalFittingProviderRegistry((MOCK,))
        self.frf = frf_input()

    def run_provider(self, provider=None, workflow=FittingWorkflow.PRODUCTION, **kwargs):
        return run_modal_fitting(provider or MockProvider(), self.frf, CONFIGURATION, registry=self.registry,
                                 workflow=workflow, **kwargs)

    def assertRefused(self, field, provider=None, workflow=FittingWorkflow.PRODUCTION):
        with self.assertRaises(ModalFittingRefusal) as caught:
            self.run_provider(provider, workflow)
        self.assertEqual(caught.exception.field, field)


class ProviderContractTests(_ProviderFixture, unittest.TestCase):
    def test_registered_provider_output_is_validated(self):
        provider = MockProvider()
        self.assertIsInstance(provider, ModalFittingProvider)
        validated = self.run_provider(provider)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(validated.output.provider, MOCK)
        self.assertEqual(validated.frf_content_hash, self.frf.content_hash)
        self.assertEqual(validated.configuration_hash, canonical_hash(CONFIGURATION))
        self.assertEqual([mode.frequency_hz for mode in validated.output.dataset.sorted_modes()], [12.0, 31.5])

    def test_validated_output_is_not_yet_production_input(self):
        # D-023: the provider label is not admitted to the M1.1 policy, so it stays unknown.
        validated = self.run_provider()
        self.assertIs(validated.source_classification.source, ModalInputSource.UNKNOWN)
        with self.assertRaises(IdentificationInputSourceRefusal):
            require_identification_input(validated.output.dataset)

    def test_refusal_is_not_a_generic_failure_type(self):
        self.assertFalse(issubclass(ModalFittingRefusal, (ValueError, RuntimeError)))


class UnknownProviderTests(_ProviderFixture, unittest.TestCase):
    def test_unregistered_provider_is_refused_before_fitting(self):
        other = ModalFittingProviderIdentity("other", "1.0", ProviderKind.EXTERNAL, "other provider/1.0")
        provider = MockProvider(identity=other)
        self.assertRefused("provider", provider)
        self.assertEqual(provider.calls, 0)

    def test_empty_registry_admits_no_provider(self):
        self.registry = ModalFittingProviderRegistry()
        self.assertRefused("provider")

    def test_registered_name_with_a_different_identity_is_refused(self):
        impostor = ModalFittingProviderIdentity("mock-provider", "0.1", ProviderKind.EXTERNAL, "something else/0.1")
        self.assertRefused("provider", MockProvider(identity=impostor))

    def test_object_without_the_protocol_is_refused(self):
        with self.assertRaises(ModalFittingRefusal):
            run_modal_fitting(object(), self.frf, CONFIGURATION, registry=self.registry,
                              workflow=FittingWorkflow.PRODUCTION)

    def test_provider_cannot_borrow_reader_or_peak_labels(self):
        for label in ("curve-fitted dataset 55", "curve-fitted modal dataset", "FRF peak-derived experimental shape"):
            with self.subTest(label=label), self.assertRaises(ModalFittingRefusal):
                ModalFittingProviderIdentity("spoof", "1", ProviderKind.EXTERNAL, label)

    def test_registry_rejects_duplicate_keys_and_labels(self):
        with self.assertRaises(ModalFittingRefusal):
            self.registry.register(MOCK)
        with self.assertRaises(ModalFittingRefusal):
            self.registry.register(ModalFittingProviderIdentity("x", "1", ProviderKind.INTERNAL, MOCK.mode_source))


class InvalidOutputTests(_ProviderFixture, unittest.TestCase):
    def test_output_from_another_provider_is_refused(self):
        other = ModalFittingProviderIdentity("other", "1.0", ProviderKind.EXTERNAL, "other provider/1.0")
        self.registry.register(other)
        self.assertRefused("output.provider", MockProvider(provider=other))

    def test_non_dataset_or_empty_dataset_is_refused(self):
        self.assertRefused("dataset", MockProvider(dataset="not a dataset"))
        self.assertRefused("dataset", MockProvider(dataset=ModalDataset("x", Path("x"), [],
                                                                        metadata={"mode_source": MOCK.mode_source})))

    def test_unlabelled_or_mislabelled_modes_are_refused(self):
        provider = MockProvider()
        output = provider.fit(self.frf, CONFIGURATION)
        output.dataset.modes[1].metadata["mode_source"] = "curve-fitted dataset 55"
        with self.assertRaises(ModalFittingRefusal) as caught:
            validate_fitting_output(output, frf=self.frf, configuration=CONFIGURATION, registry=self.registry,
                                    workflow=FittingWorkflow.PRODUCTION)
        self.assertEqual(caught.exception.field, "dataset.mode_source")

    def test_non_finite_values_are_refused(self):
        output = MockProvider().fit(self.frf, CONFIGURATION)
        output.dataset.modes[0].vectors[0, 2] = np.nan
        with self.assertRaises(ModalFittingRefusal):
            validate_fitting_output(output, frf=self.frf, configuration=CONFIGURATION, registry=self.registry,
                                    workflow=FittingWorkflow.PRODUCTION)

    def test_missing_damping_is_refused(self):
        output = MockProvider().fit(self.frf, CONFIGURATION)
        output.dataset.modes[0].damping_ratio = None
        with self.assertRaises(ModalFittingRefusal):
            validate_fitting_output(output, frf=self.frf, configuration=CONFIGURATION, registry=self.registry,
                                    workflow=FittingWorkflow.PRODUCTION)

    def test_qc_and_confidence_placeholders_are_required(self):
        self.assertRefused("qc_summary", MockProvider(qc_summary={}))
        self.assertRefused("qc_summary", MockProvider(qc_summary={"status": "OK"}))
        self.assertRefused("confidence", MockProvider(confidence={1: {"frequency_sd_hz": None, "damping_sd": None}}))
        self.assertRefused("confidence", MockProvider(confidence={1: {"frequency_sd_hz": -1.0, "damping_sd": None},
                                                                  2: {"frequency_sd_hz": None, "damping_sd": None}}))


class ProvenanceTests(_ProviderFixture, unittest.TestCase):
    def provenance(self, **changes):
        provenance = dict(MockProvider().fit(self.frf, CONFIGURATION).provenance)
        provenance.update(changes)
        for key, value in list(provenance.items()):
            if value is ...:
                del provenance[key]
        return MockProvider(provenance=provenance)

    def test_missing_provenance_is_refused(self):
        for key in ("frf_source_sha256", "frf_content_hash", "configuration", "configuration_hash",
                    "frequency_band_hz", "pole_selection"):
            with self.subTest(key=key):
                self.assertRefused("provenance", self.provenance(**{key: ...}))
        self.assertRefused("provenance", MockProvider(provenance=None))

    def test_provenance_must_match_the_actual_inputs(self):
        self.assertRefused("provenance.frf_source_sha256", self.provenance(frf_source_sha256="b" * 64))
        self.assertRefused("provenance.frf_content_hash", self.provenance(frf_content_hash="c" * 64))
        self.assertRefused("provenance.configuration", self.provenance(configuration={"model_order": 8}))
        self.assertRefused("provenance.configuration", self.provenance(configuration_hash="d" * 64))
        self.assertRefused("provenance.frequency_band_hz", self.provenance(frequency_band_hz=[0.5, 60.0]))
        self.assertRefused("provenance.pole_selection", self.provenance(pole_selection="automatic-ish"))

    def test_manual_pole_selection_only_in_research_workflow(self):
        manual = self.provenance(pole_selection="manual_review")
        self.assertRefused("provenance.pole_selection", manual, FittingWorkflow.PRODUCTION)
        validated = self.run_provider(self.provenance(pole_selection="manual_review"), FittingWorkflow.RESEARCH)
        self.assertIs(validated.workflow, FittingWorkflow.RESEARCH)


class FrfInputContractTests(unittest.TestCase):
    def test_valid_input_has_a_deterministic_content_hash(self):
        self.assertEqual(frf_input().content_hash, frf_input().content_hash)
        self.assertNotEqual(frf_input().content_hash, frf_input(h=2 * np.ones((2, 1, 100), dtype=complex)).content_hash)

    def test_invalid_inputs_are_refused(self):
        cases = {
            "non-increasing axis": dict(frequency_hz=np.r_[np.linspace(1.0, 50.0, 50), np.linspace(50.0, 99.0, 50)]),
            "shape mismatch": dict(h=np.ones((3, 1, 100), dtype=complex)),
            "non-finite FRF": dict(h=np.full((2, 1, 100), np.nan, dtype=complex)),
            "duplicate keys": dict(response_keys=((1, 3), (1, 3))),
            "bad coherence status": dict(coherence_status="maybe"),
            "coherence without status": dict(coherence=np.ones(100)),
            "status without coherence": dict(coherence_status="computed"),
            "bad source hash": dict(source_sha256="xyz"),
            "undeclared quantity": dict(quantity=" "),
        }
        for name, changes in cases.items():
            with self.subTest(name), self.assertRaises(ModalFittingRefusal):
                frf_input(**changes)


if __name__ == "__main__":
    unittest.main()
