"""M4.9 PREPARATION: synthetic digital twin with fake solver / extractor only (no Abaqus, no Abaqus Python).

Covers the twin builder, the observation pipeline (strict freeze → M4.3 families → M4.4 clusters →
objective design) and its integration with the M4.6 pipeline: determinism (A), resume (B),
budget accounting (C), branch-exchange refusal (D) and cluster handling (E).
"""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import statistics
import sys
import tempfile
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.frozen_observations import FreezeStatus
from m4_6_support import P0, TRUTH, FakeSolver
from m4_9_twin_support import MODES, TwinFakeExtractor, build_model, twin_case, twin_definition_dict
from services.branch_tracker import RefusalKind
from services.identification_clusters import ClusterStatus
from services.identification_pipeline import IdentificationPipeline
from services.identification_step import LMResult, LMSettings, LMStatus
from services.synthetic_twin import (
    TWIN_EVIDENCE_SOURCE,
    DesignStatus,
    TwinError,
    assess_recovery,
    deterministic_standard_normal,
    parse_twin_definition,
    prepare_twin,
)


def _below_e(threshold):
    return lambda e, g: e < threshold


class _Tmp(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.tmp = Path(self._directory.name)

    def tearDown(self):
        self._directory.cleanup()

    def prepare(self, name="case", **case):
        definition, registration, fields, truth = twin_case(self.tmp / name, **case)
        return prepare_twin(definition, registration, fields, truth, self.tmp / name / "twin")

    @staticmethod
    def variant(name, **extractor):
        """The same fake-model variant for the archived packs, the truth and the identification solves."""
        return {key: TwinFakeExtractor(variant=name, **extractor)
                for key in ("archive_extractor", "truth_extractor", "extractor")}

    def run_twin(self, name="case", **case):
        preparation = self.prepare(name, **case)
        pipeline = IdentificationPipeline(preparation.pipeline_config)
        return preparation, pipeline, pipeline.run()


# ----------------------------------------------------------------------------- builder

class DefinitionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.model = build_model(Path(directory.name))[0]

    def test_seed_is_required_and_explicit(self):
        for seed in (None, True, -1, 1.5, "7"):
            with self.subTest(seed=seed), self.assertRaises(TwinError):
                parse_twin_definition(twin_definition_dict(self.model, noise_seed=seed))
        data = twin_definition_dict(self.model)
        del data["noise_seed"]
        with self.assertRaises(TwinError):
            parse_twin_definition(data)

    def test_malformed_definitions_are_refused(self):
        for changes in ({"schema": "x"}, {"truth": {"E_in_plane_mpa": 45000.0}}, {"noise_relative_sd": 0.0},
                        {"sigma": float("nan")}, {"mode_numbers": [7, 7]}, {"k_int_enabled": "no"}, {"extra": 1}):
            with self.subTest(changes=changes), self.assertRaises(TwinError):
                parse_twin_definition(twin_definition_dict(self.model, **changes))

    def test_hash_binds_science_not_free_text(self):
        base = parse_twin_definition(twin_definition_dict(self.model))
        self.assertEqual(base.truth, TRUTH)
        self.assertEqual(base.start, P0)
        self.assertEqual(base.mode_numbers, MODES)
        same = parse_twin_definition(twin_definition_dict(self.model, provenance=["other text"]))
        self.assertEqual(base.definition_hash, same.definition_hash)
        for changes in ({"noise_seed": 1}, {"truth": dict(TRUTH, G12_mpa=4100.0)}, {"sigma": 0.004}):
            with self.subTest(changes=changes):
                self.assertNotEqual(parse_twin_definition(twin_definition_dict(self.model, **changes)).definition_hash,
                                    base.definition_hash)


class NoiseTests(unittest.TestCase):
    def test_version_independent_values(self):
        # Pinned: SHA-256 + Box–Muller, no NumPy random state involved.
        self.assertEqual(deterministic_standard_normal(20261005, "fe-mode:7"),
                         deterministic_standard_normal(20261005, "fe-mode:7"))
        self.assertNotEqual(deterministic_standard_normal(1, "fe-mode:7"), deterministic_standard_normal(2, "fe-mode:7"))
        self.assertAlmostEqual(deterministic_standard_normal(0, "x"), PINNED_NOISE, places=15)

    def test_standard_normal_moments(self):
        values = [deterministic_standard_normal(3, f"k{k}") for k in range(4000)]
        self.assertLess(abs(statistics.fmean(values)), 0.06)
        self.assertLess(abs(statistics.pstdev(values) - 1.0), 0.05)


PINNED_NOISE = -1.9874486925152672  # deterministic_standard_normal(0, "x"), pinned once


class ExperimentTests(_Tmp):
    def test_synthetic_experiment_from_the_truth_pack(self):
        preparation = self.prepare()
        definition, experiment = preparation.definition, preparation.experiment
        modes = experiment.modes
        self.assertEqual([m.number for m in modes], list(range(1, 25)))  # numbered by synthetic frequency
        self.assertEqual(sorted(m.source_fe_mode for m in modes), list(MODES))
        self.assertEqual([m.frequency_hz for m in modes], sorted(m.frequency_hz for m in modes))
        for mode in modes:
            epsilon = deterministic_standard_normal(definition.noise_seed, f"fe-mode:{mode.source_fe_mode}")
            self.assertEqual(mode.noise, epsilon)
            self.assertEqual(mode.frequency_hz, mode.truth_fe_hz * (1.0 + 0.003 * epsilon))
            self.assertTrue(np.all(mode.vectors[:, :2] == 0))  # only the measured U3 is present
        truth = preparation.provenance["truth"]
        self.assertFalse(truth["counts_toward_identification_budget"])
        self.assertEqual(experiment.truth_pack_content_sha256, truth["pack_content_sha256"])
        self.assertEqual(preparation.evidence.identity.evidence_source, TWIN_EVIDENCE_SOURCE)
        self.assertEqual(preparation.evidence.identity.measured_dofs, ("U3",))
        self.assertEqual(preparation.evidence.identity.evidence_record_sha256, definition.definition_hash)

    def test_seed_changes_the_experiment_only_through_the_noise(self):
        first = self.prepare("a")
        second = self.prepare("b", definition_changes={"noise_seed": 7})
        self.assertNotEqual(first.experiment.content_sha256, second.experiment.content_sha256)
        self.assertEqual(first.experiment.truth_pack_content_sha256, second.experiment.truth_pack_content_sha256)

    def test_truth_stage_is_journalled_apart_and_resumes_without_a_new_solve(self):
        definition, registration, fields, truth = twin_case(self.tmp)
        first = prepare_twin(definition, registration, fields, truth, self.tmp / "twin")
        kinds = [entry["kind"] for entry in first.truth_journal.entries]
        self.assertEqual(kinds, ["truth_solve", "truth_extraction"])
        crashing = (FakeSolver(crash_after=0), TwinFakeExtractor(fail=True))
        again = prepare_twin(definition, registration, fields, crashing, self.tmp / "twin")
        self.assertEqual(again.experiment.content_sha256, first.experiment.content_sha256)
        self.assertEqual(len(again.truth_journal.entries), 2)

    def test_failed_truth_solve_is_not_retried_without_authorisation(self):
        from services.forward_solver import SolveFailure

        definition, registration, fields, _ = twin_case(self.tmp)
        failing = (FakeSolver(ok_marker=False), TwinFakeExtractor())
        with self.assertRaises(SolveFailure):
            prepare_twin(definition, registration, fields, failing, self.tmp / "twin")
        solver = FakeSolver()
        with self.assertRaises(SolveFailure):
            prepare_twin(definition, registration, fields, (solver, TwinFakeExtractor()), self.tmp / "twin")
        self.assertEqual(solver.commands, [])
        prepared = prepare_twin(definition, registration, fields, (solver, TwinFakeExtractor()), self.tmp / "twin",
                                retry_failed_truth_solve=True)
        self.assertEqual(len(solver.commands), 1)
        self.assertIs(prepared.observation_design.status, DesignStatus.USABLE)


# ----------------------------------------------------------------------------- observation pipeline

class ObservationDesignTests(_Tmp):
    def test_strict_freeze_families_holdouts_and_clusters_by_policy(self):
        preparation = self.prepare()
        observation = preparation.observation_design
        self.assertIs(observation.status, DesignStatus.USABLE)
        frozen = observation.frozen
        self.assertIs(frozen.status, FreezeStatus.FROZEN)
        self.assertEqual(len(frozen.rows), 24)
        family = {row.row_id: observation.families[row.row_id].key for row in frozen.rows}
        holdouts = observation.holdouts
        # Torsion holdout found by the M4.3 policy (lowest odd-odd family), never by FE mode number.
        self.assertEqual(holdouts.torsion_family, "Px:O|Py:O|nx:1|ny:1")
        self.assertTrue(observation.families[holdouts.holdout_row_ids[0]].torsion_dominated)
        self.assertEqual(holdouts.validation_family, family[frozen.rows[-1].row_id])
        design = observation.design
        self.assertEqual(set(design.holdout_rows), set(holdouts.holdout_row_ids))
        self.assertGreaterEqual(design.fit_term_count, 2)
        self.assertEqual(design.observation_hash, frozen.observation_hash)
        self.assertFalse(design.provisional_uncertainty)
        self.assertTrue(all(s.sigma == 0.003 for s in design.sigmas.values()))
        by_family = {family[c.row_ids[0]] + "/" + family[c.row_ids[1]]: c.status for c in observation.clusters}
        self.assertEqual(by_family, {"Px:E|Py:E|nx:2|ny:0/Px:E|Py:E|nx:0|ny:2": ClusterStatus.CONFIRMED,
                                     "Px:E|Py:O|nx:2|ny:1/Px:O|Py:E|nx:1|ny:2": ClusterStatus.INDEPENDENT})

    def test_provenance_record(self):
        preparation = self.prepare()
        written = json.loads((self.tmp / "case" / "twin" / "twin_provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(written["twin_definition_hash"], preparation.definition.definition_hash)
        self.assertEqual(written["observation_design"]["observation_hash"],
                         preparation.observation_design.frozen.observation_hash)
        self.assertEqual(set(written["reused_packs"]),
                         {"p0", "E_in_plane_mpa+", "E_in_plane_mpa-", "G12_mpa+", "G12_mpa-"})
        twin = preparation.pipeline_config.extra_identity["twin"]
        self.assertEqual(twin["noise_seed"], 20261005)
        self.assertEqual(twin["synthetic_experiment_sha256"], preparation.experiment.content_sha256)

    def test_truth_artifact_retention_and_no_duplicate_packs(self):
        # SUPERVISOR decision §8.6.
        preparation = self.prepare()
        retention = preparation.provenance["artifact_retention"]
        self.assertEqual(retention["truth_shape_pack"], "permanent")
        self.assertEqual(retention["truth_provenance_and_run_identities"], "permanent")
        self.assertTrue(retention["truth_odb"].startswith("temporary until M4.9 review"))
        twin_dir = self.tmp / "case" / "twin"
        packs = sorted(path.name for path in twin_dir.rglob("*.npz"))
        self.assertEqual(packs, [f"{preparation.provenance['truth']['job_name']}.npz"])  # archived packs referenced only
        self.assertEqual(preparation.provenance["truth"]["truth_run_hash"], preparation.truth_journal.run_hash)

    # SUPERVISOR decision §8.2: UNSTABLE / UNSUPPORTED groups -> REFUSED (no guess, split, merge or exclusion).
    def assert_refused_without_exclusion(self, preparation, reason):
        observation = preparation.observation_design
        self.assertIs(observation.status, DesignStatus.REFUSED)
        self.assertIsNone(observation.design)
        self.assertIsNone(preparation.pipeline_config)
        self.assertIs(observation.frozen.status, FreezeStatus.FROZEN)
        self.assertEqual(len(observation.frozen.rows), 24)  # nothing excluded to rescue the design
        self.assertIn(reason, " ".join(observation.reasons))
        self.assertEqual(preparation.provenance["observation_design"]["status"], "REFUSED")
        with self.assertRaises(TwinError):
            observation.require_usable()

    def test_unsupported_trigger_group_refuses_the_design(self):
        preparation = self.prepare(**self.variant("triple"))
        self.assert_refused_without_exclusion(preparation, "UNSUPPORTED")
        group = [c for c in preparation.observation_design.clusters if c.status is ClusterStatus.UNSUPPORTED]
        self.assertEqual(len(group[0].row_ids), 3)

    def test_unstable_trigger_group_refuses_the_design(self):
        preparation = self.prepare(**self.variant("leak"))
        self.assert_refused_without_exclusion(preparation, "UNSTABLE")
        unstable = [c for c in preparation.observation_design.clusters if c.status is ClusterStatus.UNSTABLE]
        self.assertEqual(len(unstable), 1)
        bad = {d.direction for d in unstable[0].directions if not d.subspace_stable}
        self.assertEqual(bad, {"E_in_plane_mpa+", "E_in_plane_mpa-"})

    # SUPERVISOR decision §8.3: a CONFIRMED cluster split by the holdout selection -> REFUSED.
    def test_confirmed_cluster_split_by_the_holdout_refuses_the_design(self):
        preparation = self.prepare(**self.variant("top-pair"))
        observation = preparation.observation_design
        confirmed = [c.row_ids for c in observation.clusters if c.status is ClusterStatus.CONFIRMED]
        self.assertEqual(len(confirmed), 1)
        held = set(confirmed[0]) & set(observation.holdouts.holdout_row_ids)
        self.assertEqual(len(held), 1)  # the validation family takes exactly one member
        self.assert_refused_without_exclusion(preparation, "split between fit and holdout")

    def test_modes_without_a_strict_pair_are_excluded_by_the_policy(self):
        # Truth shapes rotated by ~40° in the near-degenerate pair: MAC ≈ 0.59 < 0.8, no strict pair.
        preparation = self.prepare(truth_extractor=TwinFakeExtractor(rotation_deg=40.0))
        observation = preparation.observation_design
        self.assertIs(observation.frozen.status, FreezeStatus.FROZEN)
        self.assertEqual(len(observation.frozen.rows), 22)
        self.assertEqual(len(observation.frozen.excluded), 2)
        self.assertNotIn(ClusterStatus.CONFIRMED, [c.status for c in observation.clusters])

    def test_unfrozen_baseline_refuses_the_design(self):
        from services.synthetic_twin import design_twin_observations

        preparation = self.prepare()
        frozen = replace(preparation.observation_design.frozen, status=FreezeStatus.NOT_FROZEN,
                         reasons=("1 strict pairs < required 2",), rows=())
        observation = design_twin_observations(preparation.definition, frozen, None, {}, 2)
        self.assertIs(observation.status, DesignStatus.REFUSED)
        self.assertIn("not frozen", observation.reasons[0])

    def test_missing_archived_pack_and_foreign_registration_are_refused(self):
        definition, registration, fields, truth = twin_case(self.tmp)
        partial = dict(fields, archived_packs=dict(list(fields["archived_packs"].items())[1:]))
        with self.assertRaises(TwinError):
            prepare_twin(definition, registration, partial, truth, self.tmp / "twin")
        foreign = type(registration)(**dict(vars(registration), registration_hash="f" * 64))
        with self.assertRaises(TwinError):
            prepare_twin(definition, foreign, fields, truth, self.tmp / "twin")
        with self.assertRaises(TwinError):
            prepare_twin(definition, registration, dict(fields, start=dict(TRUTH)), truth, self.tmp / "twin")
        with self.assertRaises(TwinError):
            prepare_twin(definition, registration, dict(fields, frozen=None), truth, self.tmp / "twin")


# ----------------------------------------------------------------------------- M4.6 integration (A–E)

class RecoveryTests(_Tmp):
    def test_recovery_and_assessment(self):
        preparation, pipeline, result = self.run_twin()
        self.assertIs(result.status, LMStatus.CONVERGED)
        assessment = assess_recovery(preparation.definition, result)
        self.assertTrue(assessment["criterion_1_converged"])
        for name, item in assessment["parameters"].items():
            self.assertLessEqual(item["abs_ln_error"], 3 * item["local_sd_ln"], name)

    def test_noise_free_limit_recovers_the_truth_within_one_sigma(self):
        preparation, _, result = self.run_twin(definition_changes={"noise_relative_sd": 1e-9})
        assessment = assess_recovery(preparation.definition, result)
        self.assertTrue(assessment["criterion_1_converged"] and assessment["criterion_2_within_1_sigma"])
        for name in TRUTH:
            self.assertAlmostEqual(result.parameters[name] / TRUTH[name], 1.0, places=3)  # stop: step < 0.2·sd

    def test_assessment_fails_outside_one_sigma_or_when_not_converged(self):
        definition = self.prepare().definition
        result = LMResult(LMStatus.CONVERGED, {"E_in_plane_mpa": 45000.0 * 1.01, "G12_mpa": 4000.0}, (0.0, 0.0),
                          0.0, 6, 1, (0.005, 0.01), (), None)
        assessment = assess_recovery(definition, result)
        self.assertFalse(assessment["criterion_2_within_1_sigma"])
        self.assertFalse(assessment["parameters"]["E_in_plane_mpa"]["within_1_sigma"])
        self.assertTrue(assessment["parameters"]["G12_mpa"]["within_1_sigma"])
        refused = replace(result, status=LMStatus.REFUSED, parameters=dict(TRUTH), local_sd=None, refusal="x")
        assessment = assess_recovery(definition, refused)
        self.assertFalse(assessment["criterion_1_converged"] or assessment["criterion_2_within_1_sigma"])


class DeterminismTests(_Tmp):  # A
    def test_same_twin_same_run_hash_evaluations_and_result(self):
        runs = [self.run_twin(name) for name in ("one", "two")]
        (p1, pipe1, r1), (p2, pipe2, r2) = runs
        self.assertEqual(pipe1.run_hash, pipe2.run_hash)
        self.assertEqual(p1.experiment.content_sha256, p2.experiment.content_sha256)
        self.assertEqual(p1.provenance, p2.provenance)
        hashes = [[e["evaluation_hash"] for e in p.journal.records("evaluation")] for p in (pipe1, pipe2)]
        self.assertEqual(hashes[0], hashes[1])
        self.assertEqual(r1.parameters, r2.parameters)
        self.assertEqual(r1.local_sd, r2.local_sd)
        self.assertEqual((self.tmp / "one" / "twin" / "twin_provenance.json").read_bytes(),
                         (self.tmp / "two" / "twin" / "twin_provenance.json").read_bytes())

    def test_seed_is_part_of_the_run_identity(self):
        _, first, _ = self.run_twin("one")
        _, second, _ = self.run_twin("two", definition_changes={"noise_seed": 7})
        self.assertNotEqual(first.run_hash, second.run_hash)


class ResumeTests(_Tmp):  # B
    def test_interrupted_run_resumes_without_duplicate_evaluations(self):
        _, reference, expected = self.run_twin("reference")
        preparation = self.prepare("resumed", solver=FakeSolver(crash_after=0))
        with self.assertRaises(KeyboardInterrupt):
            IdentificationPipeline(preparation.pipeline_config).run()
        solver = FakeSolver()
        config = replace(preparation.pipeline_config, solve_executor=solver)
        pipeline = IdentificationPipeline(config)
        result = pipeline.run()
        self.assertEqual(result.parameters, expected.parameters)
        evaluations = pipeline.journal.records("evaluation")
        keys = [e["candidate_hash"] for e in evaluations]
        self.assertEqual(len(keys), len(set(keys)))  # each evaluation journalled once
        self.assertEqual([e["evaluation_hash"] for e in evaluations],
                         [e["evaluation_hash"] for e in reference.journal.records("evaluation")])
        self.assertEqual(pipeline.counts()["evaluations_replayed_this_session"], 5)  # p0 and ±5 % before the crash
        self.assertEqual(len(solver.commands), result.solves - 5)
        again = IdentificationPipeline(config)
        self.assertEqual(again.run().parameters, expected.parameters)
        self.assertEqual(len(again.journal.records("evaluation")), len(evaluations))
        self.assertEqual(len(again.journal.records("result")), 1)


class BudgetTests(_Tmp):  # C
    def test_budget_accounting(self):
        preparation, pipeline, result = self.run_twin()
        counts = pipeline.counts()
        evaluations = pipeline.journal.records("evaluation")
        self.assertEqual(evaluations[0]["parameters"], {"E_in_plane_mpa": 52000.0, "G12_mpa": 4500.0})  # p0 counts
        self.assertEqual(evaluations[0]["fe_source"], "archived-validated-pack")
        self.assertEqual(counts["identification_evaluations_journalled"], result.solves)
        self.assertLessEqual(result.solves, 20)
        self.assertEqual(counts["reused_archived_evaluations"], 5)
        self.assertEqual(counts["abaqus_solves_executed_total"], result.solves - 5)
        # The truth solve is journalled apart and never counted by the identification run.
        self.assertEqual(len(preparation.truth_journal.records("truth_solve")), 1)
        self.assertFalse(any(entry["kind"].startswith("truth") for entry in pipeline.journal.entries))
        result_record = pipeline.journal.records("result")[0]
        self.assertEqual(result_record["identification_evaluations"], result.solves)

    def test_budget_includes_reused_evaluations(self):
        settings = LMSettings(mu_initial=1e-3, mu_decrease=10.0, max_step_attempts=3, solve_budget=5)
        _, pipeline, result = self.run_twin(settings=settings)
        self.assertIs(result.status, LMStatus.SOLVE_BUDGET)
        self.assertEqual(result.solves, 5)
        self.assertEqual(pipeline.counts()["abaqus_solves_executed_total"], 0)


class BranchExchangeTests(_Tmp):  # D
    def test_injected_exchange_is_refused_without_re_pairing(self):
        extractor = TwinFakeExtractor(exchange=_below_e(49000.0))
        preparation, pipeline, result = self.run_twin(extractor=extractor)
        self.assertIs(result.status, LMStatus.REFUSED)
        refused = [e for e in pipeline.journal.records("evaluation") if e["refusal"]]
        self.assertEqual(len(refused), 1)
        self.assertIn(refused[0]["refusal"]["kind"], {k.value for k in RefusalKind})
        self.assertEqual(pipeline.identity["observation_hash"], preparation.observation_design.frozen.observation_hash)
        self.assertEqual(pipeline.counts()["abaqus_solves_executed_total"], result.solves - 5)  # nothing after it
        solver = FakeSolver()
        again = IdentificationPipeline(replace(preparation.pipeline_config, solve_executor=solver))
        self.assertIs(again.run().status, LMStatus.REFUSED)
        self.assertEqual(solver.commands, [])


class ClusterTests(_Tmp):  # E
    def test_confirmed_cluster_contributes_one_term(self):
        preparation, pipeline, _ = self.run_twin()
        design = preparation.observation_design.design
        confirmed = [c.row_ids for c in preparation.observation_design.clusters if c.status is ClusterStatus.CONFIRMED]
        independent = [c.row_ids for c in preparation.observation_design.clusters
                       if c.status is ClusterStatus.INDEPENDENT]
        self.assertEqual([tuple(c) for c in design.fit_clusters], [tuple(c) for c in confirmed])
        self.assertTrue(set(independent[0]) <= set(design.fit_rows))
        for evaluation in pipeline.journal.records("evaluation"):
            self.assertEqual(len(evaluation["residuals"]), len(design.fit_rows) + len(design.fit_clusters))
            self.assertFalse(set(confirmed[0]) & set(evaluation["tracking"]))  # followed as a subspace

    def test_cluster_residual_only_when_confirmed(self):
        # Without the rotation the same triggered pair is INDEPENDENT: two individual rows, no cluster term.
        stable = TwinFakeExtractor(rotation_deg=0.0)
        preparation = self.prepare(archive_extractor=stable, truth_extractor=stable, extractor=stable)
        observation = preparation.observation_design
        self.assertEqual({c.status for c in observation.clusters}, {ClusterStatus.INDEPENDENT})
        self.assertEqual(observation.design.fit_clusters, ())
        self.assertEqual(len(observation.clusters), 2)
        result = IdentificationPipeline(preparation.pipeline_config).run()
        self.assertIs(result.status, LMStatus.CONVERGED)


if __name__ == "__main__":
    unittest.main()
