"""P11 — observation readiness: data governance, observation count and numerical identifiability kept apart.

The record is built from committed governed records only (no data store, no Abaqus, no FE). Observations are counted
only when every input they rest on is GOVERNED; the SPEC v1.2 §8 counting rule is the calibration gate's own
``count_observations``; rank, precision and leave-one-FIT-family-out stay NOT_ASSESSED.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from unittest import mock

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.identification_run import canonical_hash  # noqa: E402
from domain.modal_input_source import ModalInputSource, classify_mode_source  # noqa: E402
from services.archived_sensitivity_evidence import AcceptedReferenceRefusal, accepted_physical_freeze  # noqa: E402
from services.observation_readiness import (  # noqa: E402
    NOT_ASSESSED,
    PREREQUISITES,
    DataStatus,
    GovernanceItem,
    ReadinessEvidence,
    StrictRow,
    build_observation_readiness,
    modal_input_item,
    pooled_observation_count,
    specimen_observation_readiness,
)
from services.practical_identifiability import PracticalIdentifiabilityInputError  # noqa: E402
from services.observation_count import count_observations  # noqa: E402
from services.specimen_calibration_gate import CalibrationRefusal  # noqa: E402

SP02 = "docs/auto_id/forward_models/SP02.physical.forward.json"
SP13 = "docs/auto_id/forward_models/SP13.physical.forward.json"
SP02_LEGACY = "docs/auto_id/forward_models/SP02.forward.json"
F02, F12, F03 = "Px:E|Py:E|nx:0|ny:2", "Px:O|Py:E|nx:1|ny:2", "Px:E|Py:O|nx:0|ny:3"


def _no_external_work():
    """Every route to a data store, a solver or a subprocess fails the test."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("AUTO_ID_FIXTURE_ROOT_")}
    refuse = mock.Mock(side_effect=AssertionError("no process may be started"))
    return (mock.patch.dict(os.environ, env, clear=True), mock.patch.object(subprocess, "Popen", refuse),
            mock.patch.object(subprocess, "run", refuse))


def _governed(**overrides):
    items = {name: GovernanceItem(DataStatus.GOVERNED, "synthetic") for name in PREREQUISITES}
    items.update(overrides)
    return items


def _row(row_id, role, family, fe_mode=1):
    return StrictRow(row_id, role, fe_mode, fe_mode, family, 0.95, 0.01)


def _evidence(rows, items=None, groups=(), limited=False):
    return ReadinessEvidence({"label": "SYN"}, {}, items or _governed(), limited, tuple(rows), tuple(groups))


class AcceptedSpecimenTests(unittest.TestCase):
    def setUp(self):
        patches = _no_external_work()
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_sp02_has_two_fit_and_one_holdout_observation(self):
        record = specimen_observation_readiness(SP02, 1, repo_root=ROOT).record
        count = record["observation_count"]
        self.assertTrue(count["governed_observations_counted"])
        self.assertEqual((count["strict_rows"]["FIT"], count["strict_rows"]["HOLDOUT"]), (2, 1))
        self.assertEqual(count["families"], {"FIT": 2, "HOLDOUT": 1})
        self.assertEqual({(r["row_id"], r["role"], r["fe_mode"]) for r in count["strict_rows"]["rows"]},
                         {("R1", "FIT", 8), ("R2", "FIT", 10), ("R3", "HOLDOUT", 13)})
        self.assertEqual(count["section_8_count"]["fit_family_keys"], sorted([F02, F12]))
        self.assertEqual(count["section_8_count"]["holdout_family_keys"], [F03])
        self.assertEqual(count["status"], "COUNT_CONDITIONS_MET")
        self.assertEqual(record["insufficiency_reasons"], [])
        self.assertEqual(record["specimen"]["physical_specimen_id"], "SP-02")
        for name in PREREQUISITES:
            self.assertEqual(record["data_governance"][name]["status"], "GOVERNED", name)
        self.assertEqual(record["data_governance"]["suspension_threshold"]["status"], "NOT_AVAILABLE")
        self.assertIs(record["registration_limited"], False)

    def test_sp13_has_one_fit_and_one_holdout_observation(self):
        record = specimen_observation_readiness(SP13, 1, repo_root=ROOT).record
        count = record["observation_count"]
        self.assertEqual((count["strict_rows"]["FIT"], count["strict_rows"]["HOLDOUT"]), (1, 1))
        self.assertEqual(count["families"], {"FIT": 1, "HOLDOUT": 1})
        self.assertEqual(count["status"], "COUNT_CONDITIONS_NOT_MET")
        self.assertEqual([r["code"] for r in record["insufficiency_reasons"]], ["INSUFFICIENT_FIT_FAMILIES"])

    def test_nine_constants_are_refused_by_count_without_any_fe(self):
        sp02 = specimen_observation_readiness(SP02, 9, repo_root=ROOT)
        sp13 = specimen_observation_readiness(SP13, 9, repo_root=ROOT)
        for item in (sp02, sp13):
            section = item.record["observation_count"]["section_8_count"]
            self.assertFalse(section["met"])
            self.assertEqual(section["required_fit_families"], 10)
            self.assertIn("INSUFFICIENT_FIT_FAMILIES", [r["code"] for r in section["refusal_reasons"]])
        pooled = pooled_observation_count([sp02, sp13], 9)
        self.assertEqual(pooled["terms"], {"FIT": ["SP02:R1", "SP02:R2", "SP13:R1"], "HOLDOUT": ["SP02:R3", "SP13:R2"]})
        self.assertEqual(pooled["section_8_count"]["fit_family_keys"], sorted([F02, F12]))  # (1,2) shared, once
        self.assertEqual(pooled["status"], "COUNT_CONDITIONS_NOT_MET")
        self.assertEqual(pooled["numerical_identifiability"]["rank_status"], NOT_ASSESSED)

    def test_a_met_count_never_sets_a_rank_or_readiness_result(self):
        record = specimen_observation_readiness(SP02, 1, repo_root=ROOT).record
        self.assertEqual(record["observation_count"]["status"], "COUNT_CONDITIONS_MET")
        numerical = record["numerical_identifiability"]
        for key in ("rank_status", "precision_status", "leave_one_fit_family_out_status", "sensitivity_status"):
            self.assertEqual(numerical[key], NOT_ASSESSED)
        self.assertEqual(record["scientific_readiness"], "NOT_DECLARED")
        self.assertNotIn("PASS", repr(record).replace("PASSPORT", ""))

    def test_historical_legacy_specimen_is_never_counted(self):
        record = specimen_observation_readiness(SP02_LEGACY, 1, repo_root=ROOT).record
        self.assertFalse(record["observation_count"]["governed_observations_counted"])
        self.assertEqual(record["observation_count"]["strict_rows"]["rows"], [])
        self.assertEqual(record["data_governance"]["physical_registration"]["status"], "DIAGNOSTIC_ONLY")
        self.assertEqual(record["data_governance"]["strict_freeze"]["status"], "NOT_AVAILABLE")
        self.assertIn("PREREQUISITE_NOT_GOVERNED", [r["code"] for r in record["insufficiency_reasons"]])

    def test_m6_4_screening_is_attached_as_diagnostic_only(self):
        record = specimen_observation_readiness(SP02, 1, repo_root=ROOT).record
        screening = record["diagnostics"]["m6_4_transverse_screening"]
        self.assertEqual(screening["status"], "DIAGNOSTIC_ONLY")
        self.assertEqual({item["classification"] for item in screening["constants"].values()},
                         {"NEGLIGIBLE_FOR_BUDGET"})
        self.assertLess(max(item["max_abs_relative_change_this_specimen"] for item in screening["constants"].values()),
                        0.003)
        self.assertEqual(record["numerical_identifiability"]["sensitivity_status"], NOT_ASSESSED)

    def test_the_record_is_deterministic_and_sealed(self):
        first = specimen_observation_readiness(SP02, 1, repo_root=ROOT).record
        second = specimen_observation_readiness(SP02, 1, repo_root=ROOT).record
        self.assertEqual(first, second)
        unsealed = {key: value for key, value in first.items() if key != "record_hash"}
        self.assertEqual(first["record_hash"], canonical_hash(unsealed))
        self.assertNotEqual(specimen_observation_readiness(SP02, 2, repo_root=ROOT).record_hash, first["record_hash"])
        text = json.dumps(first, ensure_ascii=False).lower()
        for local in (str(ROOT), ROOT.as_posix(), json.dumps(str(ROOT))[1:-1]):  # repository-relative provenance only
            self.assertNotIn(local.lower(), text)

    def test_accepted_freeze_access_is_read_only_and_refuses_unknown_fixtures(self):
        freeze = accepted_physical_freeze("SP02/bravo-1-physical", repo_root=ROOT)
        self.assertEqual(freeze.freeze["status"], "FROZEN")
        freeze.freeze["strict_pairs"].clear()
        self.assertEqual(len(accepted_physical_freeze("SP02/bravo-1-physical", repo_root=ROOT).freeze["strict_pairs"]), 3)
        with self.assertRaises(AcceptedReferenceRefusal):
            accepted_physical_freeze("SP02/bravo-1", repo_root=ROOT)  # historical legacy record: no accepted freeze


class CountingRuleTests(unittest.TestCase):
    def test_unconfirmed_frf_peaks_give_no_governed_observation(self):
        source = classify_mode_source({"mode_source": "dataset 58 FRF peak extraction", "dataset_type": 58})
        self.assertIs(source, ModalInputSource.PEAK_DERIVED)
        items = _governed(experimental_modal_set=GovernanceItem(DataStatus.DIAGNOSTIC_ONLY, "19 FRF peaks"),
                          modal_input_source=modal_input_item(source, False, "dataset 58"))
        rows = [_row(f"P{i}", "FIT" if i < 18 else "HOLDOUT", f"F{i}", i + 1) for i in range(19)]
        record = build_observation_readiness(_evidence(rows, items), 1).record
        count = record["observation_count"]
        self.assertFalse(count["governed_observations_counted"])
        self.assertEqual((count["strict_rows"]["FIT"], count["strict_rows"]["HOLDOUT"]), (0, 0))
        self.assertEqual(record["data_governance"]["modal_input_source"]["status"], "DIAGNOSTIC_ONLY")
        self.assertIn("PREREQUISITE_NOT_GOVERNED", [r["code"] for r in record["insufficiency_reasons"]])

    def test_ungoverned_data_are_never_governed(self):
        curve_fitted = classify_mode_source({"mode_source": "curve-fitted dataset 55"})
        self.assertIs(modal_input_item(curve_fitted, False, "zip export").status, DataStatus.AVAILABLE)
        self.assertIs(modal_input_item(ModalInputSource.UNKNOWN, False, "?").status, DataStatus.NOT_VERIFIED)
        items = _governed(experimental_modal_set=GovernanceItem(DataStatus.AVAILABLE, "ungoverned PolyMAX set"))
        rows = [_row("R1", "FIT", "A"), _row("R2", "FIT", "B"), _row("R3", "HOLDOUT", "C")]
        record = build_observation_readiness(_evidence(rows, items), 1).record
        self.assertFalse(record["observation_count"]["governed_observations_counted"])
        self.assertEqual(record["data_governance"]["experimental_modal_set"]["status"], "AVAILABLE")
        limited = build_observation_readiness(_evidence(rows, limited=True), 1).record
        self.assertFalse(limited["observation_count"]["governed_observations_counted"])
        self.assertIn("REGISTRATION_LIMITED", [r["code"] for r in limited["insufficiency_reasons"]])

    def test_a_cluster_counts_once(self):
        rows = [_row("R1", "FIT", "A"), _row("R2", "FIT", "A"), _row("R3", "FIT", "B"), _row("R4", "HOLDOUT", "C")]
        record = build_observation_readiness(_evidence(rows, groups=[("R1", "R2")]), 2).record
        count = record["observation_count"]
        self.assertEqual(count["strict_rows"]["FIT"], 3)
        self.assertEqual(count["terms"]["FIT"], 2)
        self.assertEqual(count["terms"]["members"]["R1+R2"], ["R1", "R2"])
        self.assertEqual(count["families"]["FIT"], 2)
        self.assertEqual(count["section_8_count"]["refusal_reasons"][0]["code"], "INSUFFICIENT_FIT_FAMILIES")
        self.assertIn("CLUSTER_COUNTED_ONCE", [r["code"] for r in record["insufficiency_reasons"]])
        mixed = build_observation_readiness(_evidence(rows, groups=[("R1", "R3")]), 1).record
        self.assertEqual(mixed["observation_count"]["terms"]["FIT"], 1)  # R2 only; the R1+R3 group is not counted
        self.assertIn("CLUSTER_GROUP_NOT_COUNTED", [r["code"] for r in mixed["insufficiency_reasons"]])
        # Terms that share a family are one family (no double counting).
        self.assertEqual(count_observations({"T1": "A", "T2": "A", "T3": "B"}, {"H": "C"}, 1).fit_family_keys,
                         ("A", "B"))

    def test_a_family_shared_by_fit_and_holdout_is_refused(self):
        rows = [_row("R1", "FIT", "A"), _row("R2", "FIT", "B"), _row("R3", "HOLDOUT", "A")]
        record = build_observation_readiness(_evidence(rows), 1).record
        self.assertEqual(record["observation_count"]["section_8_count"]["holdout_fit_overlap"], ["A"])
        self.assertIn("HOLDOUT_FAMILY_OVERLAPS_FIT", [r["code"] for r in record["insufficiency_reasons"]])
        count = count_observations({"T1": "A", "T2": "B"}, {"H": "A"}, 1)
        self.assertFalse(count.met)
        self.assertEqual(count.refusals, ((CalibrationRefusal.HOLDOUT_FAMILY_OVERLAPS_FIT.value,
                                           "HOLDOUT families shared with FIT: ['A']"),))
        with self.assertRaises(PracticalIdentifiabilityInputError):
            count_observations({"T1": "A"}, {"T1": "A"}, 1)  # one term cannot be FIT and HOLDOUT

    def test_count_refusal_wording_is_the_gate_wording(self):
        count = count_observations({}, {}, 1)
        self.assertEqual(count.refusals, ((CalibrationRefusal.INSUFFICIENT_FIT_FAMILIES.value,
                                           "0 distinct FIT families [] < k + 1 = 2"),
                                          (CalibrationRefusal.NO_HOLDOUT_FAMILY.value, "no HOLDOUT family")))
        every = count_observations({"T": "A"}, {"H": "A"}, 3).refusals + count.refusals
        self.assertEqual({CalibrationRefusal(code) for code, _ in every},  # the gate maps every code to its enum
                         {CalibrationRefusal.INSUFFICIENT_FIT_FAMILIES, CalibrationRefusal.NO_HOLDOUT_FAMILY,
                          CalibrationRefusal.HOLDOUT_FAMILY_OVERLAPS_FIT})
        for bad in (-1, True, 1.0):
            with self.assertRaises(PracticalIdentifiabilityInputError):
                count_observations({}, {}, bad)

    def test_missing_governance_items_are_an_input_error(self):
        with self.assertRaises(ValueError):
            build_observation_readiness(ReadinessEvidence({"label": "X"}, {}, {}, False), 1)


if __name__ == "__main__":
    unittest.main()
