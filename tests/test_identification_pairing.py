"""M4.1 IdentificationPairingPolicy: explicit, strict, gates before assignment (SPEC §12.1; AUDIT V4)."""

from __future__ import annotations

import inspect
from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.identification_pairing_policy import (
    STRICT_IDENTIFICATION_PAIRING as STRICT,
    IdentificationPairingPolicy,
    PairingPolicyError,
)
from services.identification_pairing import (
    BaselinePairingStatus as S,
    ModeFrequency,
    PairingInputError,
    pair_baseline,
)


NAN = float("nan")


def modes(*frequencies, start=1):
    return [ModeFrequency(start + k, float(f)) for k, f in enumerate(frequencies)]


class PolicyTests(unittest.TestCase):
    def test_strict_default_matches_the_spec(self):
        self.assertEqual((STRICT.minimum_mac, STRICT.maximum_relative_frequency_error, STRICT.tracking_minimum_mac),
                         (0.80, 0.15, 0.90))
        self.assertTrue(STRICT.is_strict)
        self.assertIs(STRICT.require_strict(), STRICT)
        self.assertEqual(len(STRICT.policy_hash), 64)

    def test_hash_follows_every_field(self):
        base = STRICT.to_dict()
        for name, value in (("minimum_mac", 0.85), ("maximum_relative_frequency_error", 0.1),
                            ("tracking_minimum_mac", 0.95), ("minimum_observations", 3),
                            ("policy_id", "other"), ("assignment_tie_tolerance", 1e-6)):
            with self.subTest(name=name):
                fields = {key: val for key, val in base.items() if key != "schema"} | {name: value}
                self.assertNotEqual(IdentificationPairingPolicy(**fields).policy_hash, STRICT.policy_hash)

    def test_weaker_policies_are_not_strict(self):
        fields = {key: val for key, val in STRICT.to_dict().items() if key != "schema"}
        for name, value in (("minimum_mac", 0.5), ("maximum_relative_frequency_error", 0.2),
                            ("tracking_minimum_mac", 0.8), ("minimum_observations", 1)):
            with self.subTest(name=name):
                weak = IdentificationPairingPolicy(**(fields | {name: value}))
                self.assertFalse(weak.is_strict)
                with self.assertRaises(PairingPolicyError):
                    weak.require_strict()

    def test_malformed_policies_are_refused(self):
        fields = {key: val for key, val in STRICT.to_dict().items() if key != "schema"}
        for name, value in (("minimum_mac", 0.0), ("minimum_mac", 1.2), ("maximum_relative_frequency_error", -1.0),
                            ("minimum_observations", 0), ("minimum_observations", True), ("policy_id", " "),
                            ("assignment_tie_tolerance", -1.0)):
            with self.subTest(name=name, value=value), self.assertRaises(PairingPolicyError):
                IdentificationPairingPolicy(**(fields | {name: value}))

    def test_policy_is_explicit(self):
        parameters = inspect.signature(pair_baseline).parameters
        self.assertIs(parameters["policy"].default, inspect.Parameter.empty)
        with self.assertRaises(TypeError):
            pair_baseline(None, modes(10.0), modes(10.0), np.array([[1.0]]))


class PairingTests(unittest.TestCase):
    def test_complete_strict_pairing(self):
        result = pair_baseline(STRICT, modes(10.0, 20.0, 30.0), modes(10.5, 19.0, 31.0, 50.0, start=7),
                               np.array([[0.95, 0.10, 0.0, 0.0], [0.20, 0.90, 0.1, 0.0], [0.0, 0.1, 0.85, 0.3]]))
        self.assertIs(result.status, S.COMPLETE)
        self.assertTrue(result.final)
        self.assertEqual([(p.experimental_mode, p.fe_mode) for p in result.pairs], [(1, 7), (2, 8), (3, 9)])
        self.assertAlmostEqual(result.pairs[0].relative_frequency_error, 0.05)
        self.assertEqual(result.policy_hash, STRICT.policy_hash)

    def test_gates_apply_before_assignment(self):
        # Mode 1's best MAC partner is outside the 15 % frequency gate: it is never assigned there.
        result = pair_baseline(STRICT, modes(10.0, 20.0), modes(12.0, 20.5, start=7),
                               np.array([[0.99, 0.0], [0.0, 0.95]]))
        self.assertEqual([(p.experimental_mode, p.fe_mode) for p in result.pairs], [(2, 8)])
        self.assertEqual(result.unpaired[0].reason, "no FE mode within the frequency gate")
        self.assertIs(result.status, S.INSUFFICIENT_COVERAGE)
        # MAC 0.79 is not admissible under the strict policy, whatever the assignment would prefer.
        result = pair_baseline(STRICT, modes(10.0, 20.0), modes(10.1, 20.1, start=7),
                               np.array([[0.79, 0.0], [0.0, 0.95]]))
        self.assertEqual(len(result.pairs), 1)

    def test_frequency_gate_is_relative_to_the_experiment(self):
        result = pair_baseline(STRICT, modes(100.0, 200.0), modes(115.0, 230.0001, start=7),
                               np.array([[0.9, 0.0], [0.0, 0.9]]))
        self.assertEqual([(p.experimental_mode, p.fe_mode) for p in result.pairs], [(1, 7)])
        self.assertEqual(result.unpaired[0].reason, "no FE mode within the frequency gate")

    def test_unknown_mac_makes_the_evidence_incomplete(self):
        result = pair_baseline(STRICT, modes(10.0, 20.0, 30.0), modes(10.0, 20.0, 30.0, start=7),
                               np.array([[0.95, NAN, NAN], [NAN, 0.9, NAN], [NAN, NAN, NAN]]))
        self.assertIs(result.status, S.INCOMPLETE_EVIDENCE)
        self.assertFalse(result.final)
        self.assertIn((3, 9), result.unknown_entries)
        self.assertEqual(result.unpaired[0].reason,
                         "MAC not available for frequency-admissible FE modes; admissibility unknown")
        # An unknown MAC outside the frequency gate cannot matter.
        result = pair_baseline(STRICT, modes(10.0, 20.0), modes(10.0, 20.0, 99.0, start=7),
                               np.array([[0.95, 0.0, NAN], [0.0, 0.9, NAN]]))
        self.assertIs(result.status, S.COMPLETE)

    def test_tied_assignment_is_ambiguous(self):
        result = pair_baseline(STRICT, modes(10.0, 10.2), modes(10.1, 10.15, start=7),
                               np.array([[0.9, 0.9], [0.9, 0.9]]))
        self.assertIs(result.status, S.AMBIGUOUS)
        self.assertTrue(result.ambiguous_pairs)

    def test_competition_reason(self):
        result = pair_baseline(STRICT, modes(10.0, 10.1, 20.0), modes(10.05, 20.0, start=7),
                               np.array([[0.95, 0.0], [0.85, 0.0], [0.0, 0.9]]))
        self.assertEqual([(p.experimental_mode, p.fe_mode) for p in result.pairs], [(1, 7), (3, 8)])
        self.assertEqual(result.unpaired[0].reason, "its admissible FE modes are assigned to other experimental modes")

    def test_more_pairs_beat_a_higher_single_mac(self):
        # Assigning 1-7 (0.99) would leave mode 2 unpaired; two pairs win.
        result = pair_baseline(STRICT, modes(10.0, 10.2), modes(10.1, 10.3, start=7),
                               np.array([[0.99, 0.85], [0.86, 0.0]]))
        self.assertEqual([(p.experimental_mode, p.fe_mode) for p in result.pairs], [(1, 8), (2, 7)])

    def test_input_validation(self):
        for args in ((modes(10.0), modes(10.0), np.array([[1.0, 0.0]])),
                     (modes(10.0), modes(10.0), np.array([[1.5]])),
                     (modes(-1.0), modes(10.0), np.array([[1.0]])),
                     ([ModeFrequency(1, 10.0), ModeFrequency(1, 11.0)], modes(10.0), np.array([[1.0], [1.0]])),
                     ([], modes(10.0), np.zeros((0, 1)))):
            with self.subTest(args=len(args[0])), self.assertRaises(PairingInputError):
                pair_baseline(STRICT, *args)


if __name__ == "__main__":
    unittest.main()
