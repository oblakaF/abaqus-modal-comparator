"""M4.2 baseline observation freeze (SPEC §6 S1/S3, §12.1; D-008) and the archived CARBON-4C replay."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.experiment_fixture import (
    fixture_roots_from_environment,
    load_experiment_fixture_manifest,
    resolve_external_file,
)
from domain.experimental_qc import ExperimentalModeEligibility, ExperimentalQCStatus, TrustedSuspensionThreshold
from domain.forward_model_manifest import load_forward_model_manifest
from domain.frozen_observations import BaselineIdentity, FreezeStatus, ObservationFreezeRefusal
from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING as STRICT
from domain.identification_pairing_policy import IdentificationPairingPolicy, PairingPolicyError
from domain.specimen_manifest import load_specimen_manifest
from services.archived_baseline import ArchivedBaselineError, load_archived_baseline, parse_archived_baseline
from services.baseline_freeze import BaselineEvidenceError, build_baseline_evidence, freeze_baseline
from services.identification_pairing import ModeFrequency


BASELINES = ROOT / "docs" / "auto_id" / "baselines"
FIXTURES = ROOT / "docs" / "auto_id" / "fixtures" / "real_experiment_fixtures.json"
ANCHORS = ROOT / "docs" / "auto_id" / "forward_models" / "accepted_forward_jobs.json"
IDENTITY = BaselineIdentity("SYN/carbon-property-set-v1", "SYN_0123456789abcdef", "0123456789abcdef" + "0" * 48,
                            "1" * 64, "2" * 64, "3" * 64, "set-a", ("U3",), "synthetic", None)
NAN = float("nan")


def eligibility(numbers, excluded=(), threshold=None):
    status = ExperimentalQCStatus.PASS if threshold else ExperimentalQCStatus.NOT_AVAILABLE
    eligible = tuple(n for n in numbers if n not in excluded)
    return ExperimentalModeEligibility(status, threshold, eligible, tuple(excluded))


def modes(*frequencies, start=1):
    return [ModeFrequency(start + k, float(f)) for k, f in enumerate(frequencies)]


def evidence(mac, exp=(18.0, 74.0, 78.0, 90.0), fe=(23.0, 75.0, 78.5, 89.0), excluded=(), threshold=None):
    experimental = modes(*exp)
    return build_baseline_evidence(IDENTITY, experimental,
                                   eligibility([m.number for m in experimental], excluded, threshold),
                                   modes(*fe, start=7), np.array(mac, dtype=float))


COMPLETE_MAC = [[0.97, 0.0, 0.0, 0.0], [0.0, 0.96, 0.1, 0.0], [0.0, 0.1, 0.85, 0.0], [0.0, 0.0, 0.0, 0.9]]


class FreezeTests(unittest.TestCase):
    def test_complete_evidence_freezes_rows(self):
        frozen = freeze_baseline(evidence(COMPLETE_MAC, exp=(22.0, 74.0, 78.0, 90.0)), STRICT)
        self.assertIs(frozen.status, FreezeStatus.FROZEN)
        self.assertEqual([(r.row_id, r.experimental_mode, r.fe_mode) for r in frozen.rows],
                         [("R1", 1, 7), ("R2", 2, 8), ("R3", 3, 9), ("R4", 4, 10)])
        self.assertIs(frozen.require_frozen(), frozen)
        self.assertEqual(frozen.policy_hash, STRICT.policy_hash)
        self.assertEqual(frozen.row("R2").fe_hz, 75.0)

    def test_ineligible_modes_never_enter_even_with_a_perfect_match(self):
        threshold = TrustedSuspensionThreshold(20.0, "rig log")
        frozen = freeze_baseline(evidence(COMPLETE_MAC, excluded=(1,), threshold=threshold), STRICT)
        self.assertEqual([r.experimental_mode for r in frozen.rows], [2, 3, 4])
        self.assertEqual(frozen.excluded[0].experimental_mode, 1)
        self.assertIn("suspension", frozen.excluded[0].reason)

    def test_incomplete_evidence_is_not_frozen(self):
        mac = [row[:] for row in COMPLETE_MAC]
        mac[2][2] = NAN
        frozen = freeze_baseline(evidence(mac, exp=(22.0, 74.0, 78.0, 90.0)), STRICT)
        self.assertIs(frozen.status, FreezeStatus.NOT_FROZEN)
        self.assertEqual(frozen.rows, ())
        self.assertTrue(frozen.provisional_rows)
        self.assertIn((3, 9), frozen.unknown_mac_entries)
        with self.assertRaises(ObservationFreezeRefusal) as caught:
            frozen.require_frozen()
        self.assertIn("MAC not available", caught.exception.reasons[0])
        self.assertFalse(issubclass(ObservationFreezeRefusal, (ValueError, RuntimeError)))

    def test_insufficient_coverage_is_not_frozen(self):
        mac = [[0.97, 0, 0, 0], [0, 0.5, 0, 0], [0, 0, 0.5, 0], [0, 0, 0, 0.5]]
        frozen = freeze_baseline(evidence(mac, exp=(22.0, 74.0, 78.0, 90.0)), STRICT)
        self.assertIs(frozen.status, FreezeStatus.NOT_FROZEN)
        self.assertIn("< required 2", frozen.reasons[0])

    def test_only_strict_policies_freeze(self):
        fields = {k: v for k, v in STRICT.to_dict().items() if k != "schema"}
        weak = IdentificationPairingPolicy(**(fields | {"minimum_mac": 0.5}))
        with self.assertRaises(PairingPolicyError):
            freeze_baseline(evidence(COMPLETE_MAC), weak)

    def test_observation_hash(self):
        first = freeze_baseline(evidence(COMPLETE_MAC, exp=(22.0, 74.0, 78.0, 90.0)), STRICT)
        again = freeze_baseline(evidence(COMPLETE_MAC, exp=(22.0, 74.0, 78.0, 90.0)), STRICT)
        self.assertEqual(first.observation_hash, again.observation_hash)
        changed = [row[:] for row in COMPLETE_MAC]
        changed[1][1] = 0.95
        self.assertNotEqual(freeze_baseline(evidence(changed, exp=(22.0, 74.0, 78.0, 90.0)), STRICT).observation_hash,
                            first.observation_hash)

    def test_evidence_validation(self):
        with self.assertRaises(BaselineEvidenceError):  # eligibility must cover exactly the modes
            build_baseline_evidence(IDENTITY, modes(10.0, 20.0), eligibility([1]), modes(10.0), np.ones((2, 1)))
        with self.assertRaises(BaselineEvidenceError):
            build_baseline_evidence(IDENTITY, modes(10.0), eligibility([1]), modes(10.0, 20.0), np.ones((1, 3)))


class ArchivedBaselineTests(unittest.TestCase):
    """The approved M4.2 source: archived CARBON-4C baselines, bound to M0–M3 identities (no store needed)."""

    def setUp(self):
        self.fixtures = load_experiment_fixture_manifest(FIXTURES)
        self.anchors = json.loads(ANCHORS.read_text(encoding="utf-8"))["candidates"][0]

    def load(self, name):
        return load_archived_baseline(BASELINES / f"{name}.carbon4c-baseline.json")

    def test_records_bind_to_accepted_identities(self):
        for name in ("SP02", "SP13"):
            with self.subTest(name=name):
                baseline = self.load(name)
                forward = load_forward_model_manifest(ROOT / baseline.forward_model_path)
                passport = load_specimen_manifest(ROOT / forward.specimen_passport.path)
                fixture = self.fixtures.fixture(baseline.fixture_id)
                self.assertEqual(baseline.forward_model_hash, forward.manifest_hash)
                self.assertEqual(baseline.generated_inp_sha256, self.anchors["jobs"][name]["generated_inp_sha256"])
                self.assertEqual(baseline.job_name, f"{forward.job_prefix}_{baseline.generated_inp_sha256[:16]}")
                self.assertEqual(baseline.candidate, {"E_in_plane_mpa": 52000.0, "G12_mpa": 4500.0})
                self.assertEqual(baseline.odb.sha256, fixture.fe.odb_reference.sha256)
                self.assertEqual(baseline.fe_geometry_sha256, passport.fe_reference.geometry_identity.sha256)
                self.assertEqual(baseline.registration_hash, fixture.registration.registration_hash)
                self.assertEqual(baseline.experimental_source_sha256, fixture.experimental_source.sha256)
                self.assertEqual(len(baseline.experimental_modes), fixture.modal_set.mode_count)
                self.assertEqual([m.number for m in baseline.fe_modes], list(range(7, 31)))

    def test_strict_freeze_of_the_archived_baselines_is_not_final(self):
        """FE shapes are not archived: the recorded MACs cannot decide the strict pairing (no guessing)."""
        expected = {"SP02": [(2, 8)], "SP13": [(4, 10), (5, 11)]}
        for name in ("SP02", "SP13"):
            with self.subTest(name=name):
                baseline = self.load(name)
                numbers = [m.number for m in baseline.experimental_modes]
                frozen = freeze_baseline(baseline.evidence(f"{name}/fm", eligibility(numbers)), STRICT)
                self.assertIs(frozen.status, FreezeStatus.NOT_FROZEN)
                self.assertIn("MAC not available", frozen.reasons[0])
                self.assertEqual([(r.experimental_mode, r.fe_mode) for r in frozen.provisional_rows], expected[name])
                self.assertEqual(frozen.identity.evidence_source, "archived-carbon4c-replay")
                with self.assertRaises(ObservationFreezeRefusal):
                    frozen.require_frozen()

    def test_record_hash_ignores_layout(self):
        data = json.loads((BASELINES / "SP02.carbon4c-baseline.json").read_text(encoding="utf-8"))
        from services.archived_baseline import record_hash

        reordered = {key: data[key] for key in reversed(list(data))}
        self.assertEqual(record_hash(reordered), self.load("SP02").record_sha256)

    def test_malformed_records_are_refused(self):
        data = json.loads((BASELINES / "SP02.carbon4c-baseline.json").read_text(encoding="utf-8"))
        changes = (("job", {"job_name": "SP02_ffffffffffffffff", "generated_inp_sha256": data["job"]["generated_inp_sha256"]}),
                   ("mac_entries", data["mac_entries"] + [data["mac_entries"][0]]),
                   ("mac_entries", [dict(data["mac_entries"][0], mac=1.5)]),
                   ("mac_entries", [dict(data["mac_entries"][0], fe_mode=99)]),
                   ("schema", "auto-id/archived-baseline/v0"))
        for key, value in changes:
            with self.subTest(key=key), self.assertRaises(ArchivedBaselineError):
                parse_archived_baseline(dict(copy.deepcopy(data), **{key: value}), "0" * 64)
        with self.assertRaises(ArchivedBaselineError):
            parse_archived_baseline(dict(copy.deepcopy(data), extra=1), "0" * 64)


class ArchivedBaselineStoreTests(unittest.TestCase):
    """Store-gated: the records agree with the archive and with the M1 production modal input."""

    def test_records_match_archive_and_m1(self):
        roots = fixture_roots_from_environment()
        missing = sorted({"snadwich", "carbon-project-archive"} - set(roots))
        if missing:
            self.skipTest(f"data stores {missing} not configured")
        from services import experimental_qc as qc

        for name in ("SP02", "SP13"):
            with self.subTest(name=name):
                baseline = load_archived_baseline(BASELINES / f"{name}.carbon4c-baseline.json")
                resolve_external_file(baseline.source_record, roots)  # size + SHA-256 of the archived record
                resolve_external_file(baseline.odb, roots, verify_sha256=False)  # ODB present with the pinned size
                forward = load_forward_model_manifest(ROOT / baseline.forward_model_path)
                passport = load_specimen_manifest(ROOT / forward.specimen_passport.path)
                chain = qc.prepare_auto_id_experimental_input(baseline.fixture_id, roots=roots,
                                                              specimen_passport=passport)
                self.assertEqual([(m.number, m.frequency_hz) for m in baseline.experimental_modes],
                                 [(m.number, float(m.frequency_hz)) for m in chain.dataset.sorted_modes()])
                frozen = freeze_baseline(baseline.evidence(forward.forward_model_id, chain.eligibility), STRICT)
                self.assertIs(frozen.status, FreezeStatus.NOT_FROZEN)


if __name__ == "__main__":
    unittest.main()
