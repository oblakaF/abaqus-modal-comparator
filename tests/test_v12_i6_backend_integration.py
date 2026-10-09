"""Auto-ID V12-I6 — one backend scientific path, LM / Jacobian provenance, readiness (SPEC v1.2; D-078).

Synthetic runs use the accepted ``CampaignRun`` with the M4.6 fake solver (``v12_i6_support``); they prove the
adapter, never a real calibration.  Real-data checks are read-only: the committed M7 RUN_A / RUN_B records (no
stores) and, where configured, the archived journals.  No Abaqus, no new FE solve.
"""

from __future__ import annotations

import ast
import copy
from dataclasses import replace
import inspect
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.campaign_definition import (
    CALIBRATION_NOT_IMPLEMENTED,
    MATERIAL_IDENTIFICATION,
    CalibrationNotImplementedRefusal,
    CampaignDefinitionError,
    load_campaign_definition,
    parse_campaign_definition,
)
from domain.experiment_fixture import fixture_roots_from_environment, load_experiment_fixture_manifest
from domain.frozen_observations import ObservationRow
from domain.identification_run import canonical_hash
from m4_6_support import FakeExtractor, FakeSolver, fake_frequencies
from services import campaign_lm_provenance as lm_module
from services import campaign_scientific_backend as backend_module
from services.campaign_lm_provenance import (
    JACOBIAN_INCONSISTENT,
    LM_HISTORY_UNRELATED,
    LMProvenanceRefusal,
    verify_lm_history,
)
from services.campaign_scientific_backend import (
    CampaignRunEvidence,
    ReadinessRefusal,
    ReadinessStatus,
    judge_campaign_run,
    judge_specimen_calibration,
    released_inp_fragment,
)
from services.candidate_evaluation_evidence import (
    CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE,
    CandidateEvaluationUnverified,
    verify_candidate_evaluation,
)
from services import identification_campaign_run as campaign_module
from services.identification_campaign_run import (
    CampaignRun,
    CampaignRunConfig,
    ObservationSetMismatch,
    build_campaign_report,
    campaign_m5_system,
    check_observation_set,
)
from services.identification_step import local_sd
from services.practical_identifiability import reconstruct_lm_jacobian
from services.specimen_calibration_gate import COMPLETE_COVARIANCE, CONDITIONAL_COVARIANCE
from services.specimen_calibration_output import CalibrationFragmentRefusal
from test_m7_campaign import TRUTH_E, synthetic_specimen
from test_v12_i1_campaign_question import calibration_definition, v12_definition
from v12_i6_support import calibration_run, run_evidence, with_journal


CAMPAIGNS = ROOT / "docs" / "auto_id" / "campaigns"
FIXTURES = ROOT / "docs" / "auto_id" / "fixtures" / "real_experiment_fixtures.json"
RUN_A_SYSTEM = "a5ea2de7f1c736960b0da6dd4ab4c5bb05f6c6d546b8e8674fafde7df69f05f6"
RUN_A_CAMPAIGN_HASH = "0a21ad0567901034b521b822b52f0c29944e96394f3692e1a8ebcd7ccd8d2ccf"
RUN_B_CAMPAIGN_HASH = "7c1f5db24fa9c4f4e90c82ca802c6dae22cbe5c7ec9e2989e63e439f678540e5"


def _load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def rechain(document: dict, edit=None, drop=None, identity=None) -> dict:
    """A self-consistent rewrite of a journal (run hash and hash chain recomputed): forging is not evidence."""
    identity = dict(document["run_identity"] if identity is None else identity)
    run_hash, entries = canonical_hash(identity), []
    previous = run_hash
    for entry in document["entries"]:
        if drop is not None and drop(entry):
            continue
        record = copy.deepcopy(entry["record"])
        if edit is not None:
            record = edit(entry["kind"], record)
        body = {"sequence": len(entries), "kind": entry["kind"], "record": record, "previous_hash": previous}
        entries.append(dict(body, entry_hash=canonical_hash(body)))
        previous = entries[-1]["entry_hash"]
    return dict(document, run_identity=identity, run_hash=run_hash, entries=entries)


def evaluation_hash(record: dict) -> str:
    return canonical_hash({k: v for k, v in record.items() if k != "evaluation_hash"})


def _first_sigma(identity: dict) -> dict:
    return next(iter(identity["objective_design"]["sigmas"].values()))


# One governed pipeline identity field changed at a time (identification_pipeline.run_identity of the campaign's
# specimen_pipeline_config); every evaluation record of the pipeline journal is kept unchanged.
PIPELINE_IDENTITY_MUTATIONS = {
    "forward model": lambda i: i["forward_model"].update(forward_model_id="ANOTHER_FORWARD_MODEL"),
    "forward-model manifest": lambda i: i["forward_model"].update(manifest_hash="f" * 64),
    "specimen passport": lambda i: i["forward_model"].update(passport_manifest_hash="p" * 64),
    "solver profile": lambda i: i.update(solver_profile_hash="s" * 64),
    "frozen observations": lambda i: i.update(observation_hash="o" * 64),
    "pairing policy": lambda i: i.update(pairing_policy_hash="q" * 64),
    "FIT rows": lambda i: i["objective_design"]["fit_rows"].pop(),
    "HOLDOUT rows": lambda i: i["objective_design"]["holdout_rows"].append("R9"),
    "FIT cluster": lambda i: i["objective_design"]["fit_clusters"].append(list(i["objective_design"]["fit_rows"][:2])),
    "HOLDOUT cluster": lambda i: i["objective_design"]["holdout_clusters"].append(["R8", "R9"]),
    "governed sigma": lambda i: _first_sigma(i).update(setup_sd=_first_sigma(i)["setup_sd"] * 2.0),
    "LM settings": lambda i: i["lm_settings"].update(mu_initial=i["lm_settings"]["mu_initial"] * 10.0),
    "bounds": lambda i: i["bounds"]["lower"].__setitem__(0, i["bounds"]["lower"][0] * 0.9),
    "start": lambda i: i["start"].update({name: value * 1.01 for name, value in list(i["start"].items())[:1]}),
    "extraction expectation": lambda i: i["extraction_expectation"].update(surface_tolerance=1.0e-3),
    "archived packs": lambda i: i["archived_packs"].update(FORGED_JOB="a" * 64),
    "campaign run": lambda i: i["extra"].update(campaign_hash="c" * 64),
    "specimen": lambda i: i["extra"].update(specimen="Z"),
    "run type": lambda i: i["extra"].update(run_type="RUN_A" if i["extra"]["run_type"] == "RUN_B" else "RUN_B"),
}


def archived_run(test: unittest.TestCase, run: str):
    """READ-ONLY (store-gated): the archived M7 RUN_A / RUN_B journals as genuine evidence; skips without stores."""
    roots = fixture_roots_from_environment()
    if not {"m7-run-a", "m7-run-b", "snadwich", "carbon-project-archive"} <= set(roots):
        test.skipTest("data stores m7-run-a / m7-run-b / snadwich / carbon-project-archive not configured")
    definition = load_campaign_definition(CAMPAIGNS / f"M7_RUN_{run}.campaign.json")
    specimens = campaign_module.prepare_campaign_specimens(definition, ROOT, load_experiment_fixture_manifest(FIXTURES),
                                                           roots)
    store = Path(roots[f"m7-run-{run.lower()}"])
    campaign = _load(next(store.glob("campaign/*/journal.json")))
    pipelines = {doc["run_identity"]["extra"]["specimen"]: doc for doc in
                 (_load(p) for p in store.glob("specimens/*/*/*/journal.json"))}
    verified = verify_lm_history(definition, specimens, campaign, pipelines)  # the genuine journals verify
    test.assertEqual(verified.run_hash, _load(CAMPAIGNS / f"M7_RUN_{run}.result.json")["run_hash"])
    return definition, specimens, CampaignRunEvidence(campaign, pipelines, {}, {})


def mutated_pipelines(evidence, label: str, mutate) -> dict:
    """The pipeline journals with ``label``'s run identity changed (run hash and hash chain recomputed)."""
    pipeline = evidence.pipeline_journals[label]
    identity = copy.deepcopy(pipeline["run_identity"])
    mutate(identity)
    forged = rechain(pipeline, identity=identity)
    assert forged["run_hash"] != pipeline["run_hash"]
    assert [e["record"] for e in forged["entries"]] == [e["record"] for e in pipeline["entries"]]
    return dict(evidence.pipeline_journals, **{label: forged})


def shifted(item, row_id: str, delta: float):
    """The specimen with row ``row_id``'s experimental frequency moved so that its Δ ln f grows by ``delta``."""
    rows = []
    for row in item.frozen.rows:
        if row.row_id == row_id:
            exp = row.experimental_hz * math.exp(-delta)
            row = replace(row, experimental_hz=exp, relative_frequency_error=row.fe_hz / exp - 1.0)
        rows.append(row)
    return replace(item, frozen=replace(item.frozen, rows=tuple(rows)))


class _Runs(unittest.TestCase):
    """Genuine synthetic journalled runs, built once per module (fake solver; nothing real is solved)."""

    _directory = None
    _runs: dict = {}

    @classmethod
    def tmp(cls) -> Path:
        if _Runs._directory is None:
            _Runs._directory = tempfile.TemporaryDirectory()
        return Path(_Runs._directory.name)

    @classmethod
    def run_of(cls, name: str):
        if name not in _Runs._runs:
            _Runs._runs[name] = _SCENARIOS[name](cls.tmp() / name)
        return _Runs._runs[name]

    @property
    def base(self):
        return self.run_of("base")

    def judge(self, evidence=None, definition=None, specimens=None):
        run = self.base
        return judge_campaign_run(definition or run.definition, specimens or [run.item],
                                  run.evidence if evidence is None else evidence)

    def assert_nothing_released(self, readiness, code=None, gate_code=None):
        self.assertNotEqual(readiness.status, ReadinessStatus.RELEASED, readiness.refusal_reasons)
        self.assertFalse(readiness.released)
        record = readiness.to_dict()
        self.assertIsNone(record["released_calibration_parameters"])
        self.assertFalse(record["inp_fragment_available"])
        if readiness.calibration_record is not None:
            self.assertFalse(readiness.calibration_record.released)
            self.assertNotIn("calibration_parameters", readiness.calibration_record.to_dict())
        with self.assertRaises(CalibrationFragmentRefusal):
            released_inp_fragment(readiness, self.base.evidence.source_inps["A"])
        self.assertTrue(readiness.refusal_reasons)
        self.assertTrue(all(r["detail"] for r in readiness.refusal_reasons))
        if code is not None:
            self.assertIn(code.value, readiness.refusal_codes, readiness.refusal_reasons)
        if gate_code is not None:
            self.assertIs(readiness.status, ReadinessStatus.REFUSED)
            self.assertIn(gate_code, {r["code"] for r in readiness.calibration_record.refusal_reasons})
            self.assertIsNotNone(readiness.diagnostic_candidate)  # the judged candidate stays diagnostic only
            self.assertEqual(readiness.diagnostic_candidate["labels"],
                             ["DIAGNOSTIC_OPTIMIZER_CANDIDATE", "NOT_A_RELEASE_VALUE"])
        return readiness


def _scenario(experimental_e=TRUTH_E, data=None, item_change=None, families=None):
    def build(tmp: Path):
        definition = parse_campaign_definition(data() if data else calibration_definition())
        item, _ = synthetic_specimen(definition, "A", tmp / "data", experimental_e)
        if item_change is not None:
            item = item_change(item)
        if families is not None:
            item = replace(item, families=dict(item.families, **families))
        return calibration_run(tmp, definition=definition, item=item)
    return build


def _data(**nested):
    def build():
        data = calibration_definition()
        for path, value in nested.items():
            target = data
            *parents, key = path.split("__")
            for part in parents:
                target = target[int(part)] if isinstance(target, list) else target[part]
            target[key] = value
        return data
    return build


def _rank_data():
    data = calibration_definition()
    data.update(run_type="RUN_B", run_b_gate="synthetic test gate", fitted_parameters=["E_in_plane_mpa", "G12_mpa"],
                fixed_parameters={}, start={"E_in_plane_mpa": 52000.0, "G12_mpa": 4500.0},
                bounds={"E_in_plane_mpa": [26000.0, 104000.0], "G12_mpa": [2250.0, 9000.0]})
    data["specimens"][0]["rows"][1]["fe_mode"] = 14  # modes 8 and 14 have identical (E, G12) log-sensitivities
    return data


def _rank_rows(item):
    exp, base = fake_frequencies(TRUTH_E, 4500.0), fake_frequencies(52000.0, 4500.0)
    rows = tuple(ObservationRow(r.row_id, r.experimental_mode, exp[m - 7], m, base[m - 7], 0.99,
                                base[m - 7] / exp[m - 7] - 1.0) for r, m in zip(item.frozen.rows, (8, 14, 13)))
    return replace(item, frozen=replace(item.frozen, rows=rows))


_SCENARIOS = {
    "base": _scenario(),
    "unrelated": _scenario(experimental_e=47000.0),
    "max_iterations": _scenario(data=_data(lm__max_iterations=1)),
    "imprecise": _scenario(data=_data(sigma__setup__sd_ln=0.2)),
    "holdout_3pct": _scenario(item_change=lambda item: shifted(item, "R3", 0.03)),
    "holdout_9pct": _scenario(item_change=lambda item: shifted(item, "R3", 0.09)),
    "one_family": _scenario(families={"R2": "FAM-A1"}),
    "rank": _scenario(data=_rank_data, item_change=_rank_rows),
}


def tearDownModule():
    if _Runs._directory is not None:
        _Runs._directory.cleanup()
    directory = MaterialPathTests.__dict__.get("_directory")
    if directory is not None:
        directory.cleanup()


# ----------------------------------------------------------------------------- the noncluster integration

class NonClusterIntegrationTests(_Runs):
    def test_complete_synthetic_evidence_releases_through_the_one_backend_path(self):
        run = self.base
        self.assertEqual(run.summary["status"], "CONVERGED")
        readiness = judge_campaign_run(run.definition, [run.item], run.evidence)
        self.assertIs(readiness.status, ReadinessStatus.RELEASED, readiness.refusal_reasons)
        self.assertTrue(readiness.released)
        record = readiness.calibration_record.to_dict()
        p_hat = run.summary["parameters"]
        self.assertEqual({k: v["value"] for k, v in record["calibration_parameters"].items()}, p_hat)
        self.assertEqual(readiness.to_dict()["released_calibration_parameters"], record["calibration_parameters"])
        self.assertEqual(record["identity"]["run_hash"], run.campaign.run_hash)
        lm = readiness.evidence["lm_provenance"]
        self.assertEqual((lm["run_hash"], lm["status"], lm["p_hat"]), (run.campaign.run_hash, "CONVERGED", p_hat))
        # The judged evaluation is the pipeline evaluation the campaign journalled at p̂ (V12-I5 verified)
        final = next(e for e in run.campaign.journal.records("evaluation")
                     if e["candidate_hash"] == CampaignRun.candidate_hash(p_hat))
        binding = record["identity"]["evidence_binding"]
        self.assertEqual(binding["candidate_evaluation"]["evaluation_hash"], final["specimens"]["A"]["evaluation_hash"])
        self.assertEqual(readiness.uncertainty_basis["basis"], CONDITIONAL_COVARIANCE)

    def test_the_m5_system_is_the_reconstructed_lm_jacobian(self):
        run = self.base
        readiness = self.judge()
        journal = run.campaign.journal
        result = journal.records("result")[0]
        jacobian = reconstruct_lm_jacobian([e for e in journal.records("evaluation") if e["residuals"] is not None],
                                           result["history"], run.definition.start, run.definition.fitted_parameters,
                                           run.definition.lm.finite_difference_step)
        system = campaign_m5_system(run.definition, jacobian, run.item.spec.fit_rows)
        binding = readiness.calibration_record.identity["evidence_binding"]
        self.assertEqual(binding["candidate_evaluation"]["system_hash"], system.system_hash)
        np.testing.assert_allclose(readiness.evidence["lm_provenance"]["local_sd"], result["local_sd"], rtol=1e-12)
        # No caller-supplied matrix can enter: the backend takes the journals, packs and INP only
        self.assertEqual(list(inspect.signature(judge_campaign_run).parameters), ["definition", "specimens", "evidence"])
        self.assertEqual(list(CampaignRunEvidence.__dataclass_fields__),
                         ["campaign_journal", "pipeline_journals", "packs", "source_inps"])

    def test_synthetic_evidence_is_never_presented_as_a_production_calibration(self):
        record = self.judge().to_dict()
        self.assertEqual(record["evidence"]["solver_profiles"]["A"]["profile_id"], "SYA/fake")
        self.assertEqual(record["calibration"]["identity"]["evidence_binding"]["candidate_evaluation"]
                         ["solver_profile_id"], "SYA/fake")
        self.assertTrue(record["production_calibration"].startswith("NO_HUMAN_AUTHORISED_PRODUCTION_CALIBRATION_RUN"))
        self.assertTrue(record["production_execution"].startswith("NOT_AUTHORISED"))
        journalled = {r["fe_source"] for r in self.base.campaign.pipelines["A"].journal.records("evaluation")}
        self.assertEqual(record["evidence"]["fe_sources"]["A"], sorted(journalled))  # exactly as journalled

    def test_inp_fragment_is_rendered_only_for_released_readiness(self):
        readiness = self.judge()
        fragment = released_inp_fragment(readiness, self.base.evidence.source_inps["A"])
        self.assertTrue(fragment.material_name.startswith("CAL_A_"))
        refused = judge_campaign_run(self.run_of("imprecise").definition, [self.run_of("imprecise").item],
                                     self.run_of("imprecise").evidence)
        for other in (refused, self.judge(evidence=with_journal(self.base.evidence, campaign_journal={}))):
            with self.assertRaises(CalibrationFragmentRefusal):
                released_inp_fragment(other, self.base.evidence.source_inps["A"])

    def test_judgement_is_deterministic_and_writes_nothing(self):
        before = sorted(p.as_posix() for p in self.tmp().rglob("*"))
        first, second = self.judge(), self.judge()
        self.assertEqual(first.record_hash, second.record_hash)
        self.assertEqual(sorted(p.as_posix() for p in self.tmp().rglob("*")), before)


# ----------------------------------------------------------------------------- LM / Jacobian provenance

class LMProvenanceTests(_Runs):
    def test_history_replays_the_lm_objectives_local_sd_and_stop_step(self):
        run = self.base
        verified = verify_lm_history(run.definition, [run.item], run.evidence.campaign_journal,
                                     run.evidence.pipeline_journals)
        self.assertEqual(verified.status, "CONVERGED")
        self.assertEqual(verified.p_hat, run.summary["parameters"])
        self.assertEqual(len(verified.evaluations), run.summary["lm_evaluations"])  # start, ±5 %, accepted step
        np.testing.assert_allclose(verified.local_sd, local_sd(np.array(verified.jacobian.whitened)), rtol=0)

    def test_committed_run_a_and_run_b_reproduce_their_accepted_m5_systems(self):
        # Real data, no stores: the journalled evaluations and LM history in the accepted M7 records rebuild the
        # accepted M5 systems through the shared construction, and the LM's own local sd and stop step.
        for run in ("A", "B"):
            with self.subTest(run=run):
                record = _load(CAMPAIGNS / f"M7_RUN_{run}.result.json")
                definition = load_campaign_definition(CAMPAIGNS / f"M7_RUN_{run}.campaign.json")
                jacobian = reconstruct_lm_jacobian(record["campaign_evaluations"], record["lm_history"],
                                                   definition.start, definition.fitted_parameters,
                                                   definition.lm.finite_difference_step)
                system = campaign_m5_system(definition, jacobian, definition.fit_term_ids())
                self.assertEqual(system.system_hash, record["m5_verdict"]["evidence_hashes"]["system"])
                np.testing.assert_allclose(local_sd(np.array(jacobian.whitened)), record["lm_result"]["local_sd"],
                                           rtol=1e-12)
        self.assertEqual(_load(CAMPAIGNS / "M7_RUN_A.result.json")["m5_verdict"]["evidence_hashes"]["system"],
                         RUN_A_SYSTEM)

    def test_archived_real_journals_verify_and_a_forged_copy_is_refused(self):
        """READ-ONLY (store-gated): the archived RUN_A / RUN_B campaign and pipeline journals prove their Jacobians."""
        roots = fixture_roots_from_environment()
        if not {"m7-run-a", "m7-run-b", "snadwich", "carbon-project-archive"} <= set(roots):
            self.skipTest("data stores m7-run-a / m7-run-b / snadwich / carbon-project-archive not configured")
        fixtures = load_experiment_fixture_manifest(FIXTURES)
        for run in ("A", "B"):
            with self.subTest(run=run):
                definition = load_campaign_definition(CAMPAIGNS / f"M7_RUN_{run}.campaign.json")
                specimens = campaign_module.prepare_campaign_specimens(definition, ROOT, fixtures, roots)
                store = Path(roots[f"m7-run-{run.lower()}"])
                campaign = _load(next(store.glob("campaign/*/journal.json")))
                pipelines = {doc["run_identity"]["extra"]["specimen"]: doc for doc in
                             (_load(p) for p in store.glob("specimens/*/*/*/journal.json"))}
                verified = verify_lm_history(definition, specimens, campaign, pipelines)
                accepted = _load(CAMPAIGNS / f"M7_RUN_{run}.result.json")
                self.assertEqual(verified.run_hash, accepted["run_hash"])
                system = campaign_m5_system(definition, verified.jacobian, definition.fit_term_ids())
                self.assertEqual(system.system_hash, accepted["m5_verdict"]["evidence_hashes"]["system"])
                forged = rechain(campaign, edit=lambda kind, r: dict(r, local_sd=[v * 1.01 for v in r["local_sd"]])
                                 if kind == "result" else r)
                with self.assertRaises(LMProvenanceRefusal) as refused:
                    verify_lm_history(definition, specimens, forged, pipelines)
                self.assertEqual(refused.exception.code, JACOBIAN_INCONSISTENT)


# ----------------------------------------------------------------------------- pipeline run identity

class PipelineIdentityTests(_Runs):
    """Each specimen's pipeline run is the governed pipeline of its campaign run: the ``run_identity`` of the
    campaign's ``specimen_pipeline_config``.  One changed identity field, with the pipeline run hash and hash chain
    recomputed and every evaluation record kept, is another pipeline run (LM_HISTORY_UNRELATED)."""

    def test_the_genuine_pipeline_run_is_the_governed_pipeline(self):
        run = self.base
        entry = run.evidence.campaign_journal["run_identity"]["specimens"][0]
        governed = lm_module.governed_pipeline_identity(run.definition, run.item, run.campaign.run_hash,
                                                        entry["archived_packs"])
        self.assertEqual(canonical_hash(governed), run.evidence.pipeline_journals["A"]["run_hash"])
        self.assertEqual(governed, run.evidence.pipeline_journals["A"]["run_identity"])

    def test_a_changed_pipeline_identity_releases_no_calibration(self):
        run = self.base
        for name, mutate in PIPELINE_IDENTITY_MUTATIONS.items():
            with self.subTest(field=name):
                journals = mutated_pipelines(run.evidence, "A", mutate)
                with self.assertRaises(LMProvenanceRefusal) as refused:
                    verify_lm_history(run.definition, [run.item], run.evidence.campaign_journal, journals)
                self.assertEqual(refused.exception.code, LM_HISTORY_UNRELATED)
                readiness = self.assert_nothing_released(
                    self.judge(evidence=with_journal(run.evidence, pipeline_journals=journals)),
                    ReadinessRefusal.LM_HISTORY_UNRELATED)
                self.assertIs(readiness.status, ReadinessStatus.NOT_READY)
                self.assertIsNone(readiness.calibration_record)
                self.assertIsNone(readiness.diagnostic_candidate)

    def test_a_changed_pipeline_identity_releases_no_material_value(self):
        material = MaterialPathTests.material_run(self, (0.02, 1.0))
        genuine = judge_campaign_run(material.definition, material.specimens, material.evidence)
        self.assertIs(genuine.status, ReadinessStatus.MATERIAL_VALUES_RELEASED)  # the genuine journals release
        for label in ("A", "B"):
            for name, mutate in PIPELINE_IDENTITY_MUTATIONS.items():
                with self.subTest(specimen=label, field=name):
                    journals = mutated_pipelines(material.evidence, label, mutate)
                    readiness = judge_campaign_run(material.definition, material.specimens,
                                                   with_journal(material.evidence, pipeline_journals=journals))
                    self.assertIs(readiness.status, ReadinessStatus.NOT_READY)
                    self.assertEqual(readiness.refusal_codes, (ReadinessRefusal.LM_HISTORY_UNRELATED.value,))
                    record = readiness.to_dict()
                    for key in ("material_formal_output", "material_family_consistency", "material_claim",
                                "released_calibration_parameters", "diagnostic_candidate", "calibration"):
                        self.assertIsNone(record[key], key)

    def test_archived_real_journals_refuse_a_changed_pipeline_identity(self):
        """READ-ONLY (store-gated): the archived RUN_A / RUN_B pipeline journals with one identity field changed."""
        for run in ("A", "B"):
            definition, specimens, evidence = archived_run(self, run)
            for item in specimens:
                for name, mutate in PIPELINE_IDENTITY_MUTATIONS.items():
                    with self.subTest(run=run, specimen=item.label, field=name):
                        journals = mutated_pipelines(evidence, item.label, mutate)
                        with self.assertRaises(LMProvenanceRefusal) as refused:
                            verify_lm_history(definition, specimens, evidence.campaign_journal, journals)
                        self.assertEqual(refused.exception.code, LM_HISTORY_UNRELATED)
                        readiness = judge_campaign_run(definition, specimens,
                                                       with_journal(evidence, pipeline_journals=journals))
                        self.assertIs(readiness.status, ReadinessStatus.NOT_READY)
                        self.assertEqual(readiness.refusal_codes, (ReadinessRefusal.LM_HISTORY_UNRELATED.value,))
                        self.assertIsNone(readiness.to_dict()["material_formal_output"])


# ----------------------------------------------------------------------------- the end-to-end negative matrix

class NegativeMatrixTests(_Runs):
    def final_hashes(self):
        run = self.base
        final = next(e for e in run.campaign.journal.records("evaluation")
                     if e["candidate_hash"] == CampaignRun.candidate_hash(run.summary["parameters"]))
        return final, final["specimens"]["A"]["evaluation_hash"]

    def test_01_wrong_scientific_question(self):
        run = self.base
        material = parse_campaign_definition(v12_definition(MATERIAL_IDENTIFICATION, 0.02))
        for readiness in (judge_specimen_calibration(material, [run.item], run.evidence),
                          judge_campaign_run(replace(run.definition, scientific_question="SOMETHING_ELSE"), [run.item],
                                             run.evidence),
                          judge_specimen_calibration(replace(run.definition, scientific_question=None), [run.item],
                                                     run.evidence)):
            self.assert_nothing_released(readiness, ReadinessRefusal.WRONG_SCIENTIFIC_QUESTION)
            self.assertIs(readiness.status, ReadinessStatus.NOT_READY)
            self.assertIsNone(readiness.calibration_record)

    def test_02_wrong_specimen_count(self):
        run = self.base
        spec = run.definition.specimens[0]
        for readiness in (self.judge(specimens=[run.item, run.item]),
                          self.judge(definition=replace(run.definition, specimens=(spec, spec)))):
            self.assert_nothing_released(readiness, ReadinessRefusal.SPECIMEN_COUNT)

    def test_03_missing_or_invalid_tau_mf(self):
        for tau in (None, 0.0, -0.01, 0.021, float("nan"), float("inf"), True, "0.02"):
            with self.subTest(tau=tau):
                self.assert_nothing_released(self.judge(definition=replace(self.base.definition, tau_mf=tau)),
                                             ReadinessRefusal.TAU_MF_NOT_DECLARED)
        with self.assertRaises(CampaignDefinitionError):
            parse_campaign_definition(calibration_definition(tau_mf=0.05))

    def test_04_wrong_campaign_or_run_identity(self):
        run, other = self.base, self.run_of("unrelated")
        another_campaign = parse_campaign_definition(calibration_definition(tau_mf=0.01))
        self.assertNotEqual(another_campaign.campaign_hash, run.definition.campaign_hash)
        identity = dict(run.evidence.campaign_journal["run_identity"], manifest_hash="n" * 64)
        cases = {
            "another campaign definition": self.judge(definition=another_campaign),
            "another run's pipeline journal": self.judge(evidence=with_journal(
                run.evidence, pipeline_journals=other.evidence.pipeline_journals)),
            "another manifest (run identity)": self.judge(evidence=with_journal(
                run.evidence, campaign_journal=rechain(run.evidence.campaign_journal, identity=identity))),
        }
        for name, readiness in cases.items():
            with self.subTest(case=name):
                self.assert_nothing_released(readiness, ReadinessRefusal.LM_HISTORY_UNRELATED)

    def test_05_unrelated_candidate_evaluation(self):
        run = self.base
        final, _ = self.final_hashes()
        start = next(e for e in run.campaign.journal.records("evaluation")
                     if e["parameters"] == dict(run.definition.start))

        def point_at_start(kind, record):
            if kind == "evaluation" and record["candidate_hash"] == final["candidate_hash"]:
                record["specimens"]["A"] = copy.deepcopy(start["specimens"]["A"])  # a genuine record, another candidate
            return record

        forged = rechain(run.evidence.campaign_journal, edit=point_at_start)
        self.assert_nothing_released(self.judge(evidence=with_journal(run.evidence, campaign_journal=forged)),
                                     ReadinessRefusal.LM_EVALUATION_UNVERIFIED)

    def test_06_manipulated_residuals(self):
        run = self.base
        final, final_hash = self.final_hashes()
        # (a) the campaign journal alone
        alone = rechain(run.evidence.campaign_journal, edit=lambda kind, r: dict(
            r, residuals=[v * 1.5 for v in r["residuals"]]) if kind == "evaluation"
            and r["candidate_hash"] == final["candidate_hash"] else r)
        self.assert_nothing_released(self.judge(evidence=with_journal(run.evidence, campaign_journal=alone)),
                                     ReadinessRefusal.LM_EVALUATION_UNVERIFIED)

        # (b) pipeline and campaign journals rewritten consistently: the LM history no longer follows them
        def forged_pair(change):
            holder = {}

            def pipeline_edit(kind, record):
                if kind == "evaluation" and record["evaluation_hash"] == final_hash:
                    record = change(record)
                    record["evaluation_hash"] = evaluation_hash(record)
                    holder.update(record=record)
                return record

            pipeline = rechain(run.evidence.pipeline_journals["A"], edit=pipeline_edit)
            new = holder["record"]

            def campaign_edit(kind, record):
                if kind == "evaluation" and record["candidate_hash"] == final["candidate_hash"]:
                    record["specimens"]["A"].update({k: new[k] for k in record["specimens"]["A"]})
                    record["residuals"] = list(new["residuals"])
                    record["holdout_residuals"] = {f"A:{k}": v for k, v in new["holdout_residuals"].items()}
                return record

            return with_journal(run.evidence, campaign_journal=rechain(run.evidence.campaign_journal, campaign_edit),
                                pipeline_journals={"A": pipeline})

        self.assert_nothing_released(self.judge(evidence=forged_pair(lambda r: dict(
            r, residuals=[v + 0.5 for v in r["residuals"]]))), ReadinessRefusal.JACOBIAN_INCONSISTENT)
        # (c) holdouts are not in the LM: the FE pack re-derivation refuses them
        self.assert_nothing_released(self.judge(evidence=forged_pair(lambda r: dict(
            r, holdout_residuals={k: v - 3.0 for k, v in r["holdout_residuals"].items()}))),
            ReadinessRefusal.FE_EVIDENCE_UNVERIFIED)

    def test_06b_a_fully_self_consistent_forged_lm_journal_is_refused_by_the_fe_packs(self):
        # Every FIT residual moved by the same whitened offset in both journals, with the LM history, result objective
        # and stop step recomputed by the forger: residual differences (hence the Jacobian and local sd) are
        # unchanged, so only the re-derivation from the content-addressed FE packs can refuse it.
        run, offset = self.base, 0.01
        moved = {}

        def pipeline_edit(kind, record):
            if kind == "evaluation":
                old = record["evaluation_hash"]
                record["residuals"] = [v + offset for v in record["residuals"]]
                record["evaluation_hash"] = evaluation_hash(record)
                moved[old] = record
            return record

        pipeline = rechain(run.evidence.pipeline_journals["A"], edit=pipeline_edit)
        evaluations = {}

        def campaign_edit(kind, record):
            if kind == "evaluation":
                new = moved[record["specimens"]["A"]["evaluation_hash"]]
                record["specimens"]["A"].update({k: new[k] for k in record["specimens"]["A"]})
                record["residuals"] = list(new["residuals"])
                evaluations[record["candidate_hash"]] = record
            elif kind == "result":
                names = run.definition.fitted_parameters

                def residuals(x):
                    point = {n: float(math.exp(v)) for n, v in zip(names, x)}
                    found = [e for e in evaluations.values()
                             if all(math.isclose(e["parameters"][n], point[n], rel_tol=1e-12) for n in names)]
                    return np.asarray(found[0]["residuals"])

                for entry in record["history"]:
                    entry["objective_before"] = 0.5 * float(residuals(entry["x"]) @ residuals(entry["x"]))
                    if entry["trial_objective"] is not None:
                        entry["trial_objective"] = 0.5 * float(residuals(entry["trial_x"]) @ residuals(entry["trial_x"]))
                final = residuals(record["history"][-1]["x"])
                record["objective"] = 0.5 * float(final @ final)
                verified = verify_lm_history(run.definition, [run.item], run.evidence.campaign_journal,
                                             run.evidence.pipeline_journals)
                from services.identification_step import lm_step
                last = record["history"][-1]
                step = lm_step(final, np.array(verified.jacobian.whitened), last["mu"])
                last["trial_x"] = [float(v) for v in np.asarray(last["x"]) + step]
            return record

        campaign = rechain(run.evidence.campaign_journal, edit=campaign_edit)
        forged = with_journal(run.evidence, campaign_journal=campaign, pipeline_journals={"A": pipeline})
        verify_lm_history(run.definition, [run.item], forged.campaign_journal, forged.pipeline_journals)  # LM passes
        self.assert_nothing_released(self.judge(evidence=forged), ReadinessRefusal.FE_EVIDENCE_UNVERIFIED)

    def test_06c_the_campaign_copy_of_a_specimen_evaluation_is_bound_to_the_pipeline_record(self):
        # The FE source shown as provenance cannot be relabelled in the campaign journal (e.g. as an archived pack).
        run = self.base
        for field, value in (("fe_source", "archived-validated-pack"), ("tracking", {"R1": [8, 1.0]})):
            with self.subTest(field=field):
                forged = rechain(run.evidence.campaign_journal, edit=lambda kind, r: dict(
                    r, specimens={"A": dict(r["specimens"]["A"], **{field: value})}) if kind == "evaluation" else r)
                self.assert_nothing_released(self.judge(evidence=with_journal(run.evidence, campaign_journal=forged)),
                                             ReadinessRefusal.LM_EVALUATION_UNVERIFIED)

    def test_07_wrong_baseline(self):
        run = self.base
        final, final_hash = self.final_hashes()
        pipeline = run.campaign.pipelines["A"].journal
        record = next(r for r in pipeline.records("evaluation") if r["evaluation_hash"] == final_hash)
        baseline_content = next(r["pack_content_sha256"] for r in pipeline.records("extraction")
                                if r["job_name"] == run.item.frozen.identity.job_name)
        packs = dict(run.evidence.packs)
        packs[baseline_content] = run.evidence.packs[record["pack_content_sha256"]]  # the candidate as "baseline"
        self.assert_nothing_released(self.judge(evidence=with_journal(run.evidence, packs=packs)),
                                     ReadinessRefusal.FE_EVIDENCE_UNVERIFIED)
        # A frozen set with another baseline FE state is another observation set: never this run's baseline
        rows = tuple(replace(r, fe_hz=r.fe_hz * 1.01) for r in run.item.frozen.rows)
        moved = replace(run.item, frozen=replace(run.item.frozen, rows=rows))
        self.assertNotEqual(moved.frozen.observation_hash, run.item.frozen.observation_hash)
        self.assert_nothing_released(self.judge(specimens=[moved]), ReadinessRefusal.LM_HISTORY_UNRELATED)

    def test_08_inconsistent_fe_pack(self):
        run = self.base
        journal = run.campaign.pipelines["A"].journal
        derivative = [r for r in journal.records("evaluation") if r["parameters"]["E_in_plane_mpa"] == 54600.0][0]
        content = derivative["pack_content_sha256"]
        pack = run.evidence.packs[content]
        other = next(p for c, p in run.evidence.packs.items() if c != content)
        tampered = replace(pack, frequencies_hz=tuple(np.asarray(pack.frequencies_hz) * 1.001))
        for name, packs in (("missing derivative pack", {c: p for c, p in run.evidence.packs.items() if c != content}),
                            ("another pack under its content hash", dict(run.evidence.packs, **{content: other})),
                            ("tampered frequencies", dict(run.evidence.packs, **{content: tampered}))):
            with self.subTest(case=name):
                self.assert_nothing_released(self.judge(evidence=with_journal(run.evidence, packs=packs)),
                                             ReadinessRefusal.FE_EVIDENCE_UNVERIFIED)
        self.assert_nothing_released(self.judge(evidence=with_journal(run.evidence, source_inps={"A": b"*Heading\n"})),
                                     ReadinessRefusal.FE_EVIDENCE_UNVERIFIED)

    def test_09_missing_lm_history(self):
        run = self.base
        cases = {
            "no result entry": with_journal(run.evidence, campaign_journal=rechain(
                run.evidence.campaign_journal, drop=lambda e: e["kind"] == "result")),
            "empty history": with_journal(run.evidence, campaign_journal=rechain(
                run.evidence.campaign_journal, edit=lambda kind, r: dict(r, history=[]) if kind == "result" else r)),
            "no campaign journal": with_journal(run.evidence, campaign_journal={}),
            "no pipeline journal": with_journal(run.evidence, pipeline_journals={}),
        }
        for name, evidence in cases.items():
            with self.subTest(case=name):
                self.assert_nothing_released(self.judge(evidence=evidence), ReadinessRefusal.LM_HISTORY_MISSING)
        self.assert_nothing_released(self.judge(evidence=object()), ReadinessRefusal.LM_HISTORY_MISSING)

    def test_10_unrelated_lm_history(self):
        run, other = self.base, self.run_of("unrelated")
        self.assert_nothing_released(self.judge(evidence=with_journal(
            run.evidence, campaign_journal=other.evidence.campaign_journal)), ReadinessRefusal.LM_HISTORY_UNRELATED)
        # Another run's history (same start and ±5 % points, other residuals) transplanted into this journal
        history = other.campaign.journal.records("result")[0]["history"]
        transplanted = rechain(run.evidence.campaign_journal, edit=lambda kind, r: dict(r, history=history)
                               if kind == "result" else r)
        self.assert_nothing_released(self.judge(evidence=with_journal(run.evidence, campaign_journal=transplanted)),
                                     ReadinessRefusal.JACOBIAN_INCONSISTENT)

    def test_11_inconsistent_reconstructed_jacobian(self):
        run = self.base

        def result_edit(change):
            return with_journal(run.evidence, campaign_journal=rechain(
                run.evidence.campaign_journal, edit=lambda kind, r: change(copy.deepcopy(r)) if kind == "result"
                else r))

        def last(change):
            def apply(record):
                record["history"][-1] = change(record["history"][-1])
                return record
            return apply

        cases = {
            "journalled local sd": lambda r: dict(r, local_sd=[v * 1.01 for v in r["local_sd"]]),
            "stop step damping": last(lambda h: dict(h, mu=h["mu"] * 10.0)),
            "stop step": last(lambda h: dict(h, trial_x=[v + 1e-6 for v in h["trial_x"]])),
            "recorded objective": last(lambda h: dict(h, objective_before=h["objective_before"] * 1.01)),
            "result objective": lambda r: dict(r, objective=r["objective"] * 1.01),
        }
        for name, change in cases.items():
            with self.subTest(case=name):
                self.assert_nothing_released(self.judge(evidence=result_edit(change)),
                                             ReadinessRefusal.JACOBIAN_INCONSISTENT)

    def test_12_non_converged_optimisation(self):
        genuine = self.run_of("max_iterations")
        self.assertEqual(genuine.summary["status"], "MAX_ITERATIONS")
        self.assert_nothing_released(judge_campaign_run(genuine.definition, [genuine.item], genuine.evidence),
                                     ReadinessRefusal.LM_NOT_CONVERGED)
        run = self.base
        for name, change in (("status", lambda r: dict(r, status="STEP_REJECTED")),
                             ("no stop step", lambda r: dict(r, history=r["history"][:-1]))):
            with self.subTest(case=name):
                forged = rechain(run.evidence.campaign_journal, edit=lambda kind, r: change(r) if kind == "result"
                                 else r)
                self.assert_nothing_released(self.judge(evidence=with_journal(run.evidence, campaign_journal=forged)),
                                             ReadinessRefusal.LM_NOT_CONVERGED)

    def judged(self, name):
        run = self.run_of(name)
        return judge_campaign_run(run.definition, [run.item], run.evidence)

    def test_13_inadequate_practical_rank(self):
        readiness = self.assert_nothing_released(self.judged("rank"), gate_code="RANK_DEFICIENT")
        self.assertEqual(readiness.evidence["lm_provenance"]["status"], "CONVERGED")  # a genuine LM result

    def test_14_incomplete_leave_one_family_out(self):
        self.assert_nothing_released(self.judged("one_family"), gate_code="LOO_INCOMPLETE")

    def test_15_failed_holdout_or_pattern(self):
        readiness = self.assert_nothing_released(self.judged("holdout_3pct"), gate_code="HOLDOUT_FAILURE")
        codes = {r["code"] for r in readiness.calibration_record.refusal_reasons}
        self.assertNotIn("ROW_RELATIVE_ERROR_ABOVE_CEILING", codes)  # 3 %: the holdout alone refuses

    def test_16_row_relative_error_above_eight_percent(self):
        readiness = self.assert_nothing_released(self.judged("holdout_9pct"),
                                                 gate_code="ROW_RELATIVE_ERROR_ABOVE_CEILING")
        rows = readiness.calibration_record.non_degradation["rows_above_ceiling"]
        self.assertTrue(rows)

    def test_17_precision_above_008(self):
        self.assert_nothing_released(self.judged("imprecise"), gate_code="CONSERVATIVE_ABOVE_CEILING")

    def test_18_missing_covariance_is_never_reported_as_complete(self):
        released = self.judge()
        for basis in (released.uncertainty_basis, released.calibration_record.uncertainty_basis):
            self.assertEqual(basis["basis"], CONDITIONAL_COVARIANCE)
            self.assertTrue(basis["conditional_on_available_covariance"])
            self.assertEqual(basis["covariance_components"]["sigma_meas"], "NOT_AVAILABLE")
        self.assertNotIn(COMPLETE_COVARIANCE, json.dumps(released.to_dict()))
        data = calibration_definition()
        data["sigma"]["measurement"]["status"] = "MEASURED"
        with self.assertRaises(CampaignDefinitionError):  # no measured Σ_meas exists: never claimed
            parse_campaign_definition(data)
        claimed = replace(self.base.definition, sigma=replace(self.base.definition.sigma, measurement_status="MEASURED"))
        self.assert_nothing_released(self.judge(definition=claimed))

    def test_19_confirmed_cluster_without_member_evidence(self):
        readiness = ClusterReadinessTests.journal_declared_cluster(self)
        self.assert_nothing_released(readiness, ReadinessRefusal.CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE)

    def test_20_invalid_optional_inp_fragment(self):
        readiness = self.judge()
        source = self.base.evidence.source_inps["A"]
        for name, data in (("another INP", source.replace(b"3.32e-05", b"3.31e-05")), ("empty", b""),
                           ("no material block", b"*Heading\n")):
            with self.subTest(case=name):
                with self.assertRaises(CalibrationFragmentRefusal):
                    released_inp_fragment(readiness, data)
        for other in (self.judged("imprecise"), self.judge(definition=replace(self.base.definition, tau_mf=None))):
            with self.assertRaises(CalibrationFragmentRefusal):
                released_inp_fragment(other, source)
        with self.assertRaises(CalibrationFragmentRefusal):
            released_inp_fragment(readiness.calibration_record, source)  # only a judged readiness record

    def test_21_no_material_to_calibration_fallback(self):
        material = MaterialPathTests.material_run(self, (0.02, 1.12))
        readiness = judge_campaign_run(material.definition, material.specimens, material.evidence)
        self.assertIs(readiness.status, ReadinessStatus.REFUSED)
        self.assertIsNone(readiness.calibration_record)
        self.assertIsNone(readiness.to_dict()["released_calibration_parameters"])
        self.assertIsNone(readiness.to_dict()["production_calibration"])
        converted = judge_specimen_calibration(material.definition, material.specimens, material.evidence)
        self.assert_nothing_released(converted, ReadinessRefusal.WRONG_SCIENTIFIC_QUESTION)
        # The calibration question with the material run's journals: never that run's evidence
        self.assert_nothing_released(self.judge(evidence=material.evidence))

    def test_22_real_execution_without_approval_is_refused(self):
        ExecutionSafetyTests.calibration_execution_refused(self)
        ExecutionSafetyTests.judgement_executes_nothing(self)


# ----------------------------------------------------------------------------- confirmed clusters

class ClusterReadinessTests(_Runs):
    def journal_declared_cluster(self, governed: bool = True):
        """The genuine run whose pipeline objective design declares a confirmed cluster C(R1+R2).

        The campaign governance has no cluster terms (the production path stops at a cluster trigger), so such a
        pipeline run is not the governed pipeline (LM_HISTORY_UNRELATED).  ``governed=True`` judges it under a
        governance whose specimen pipeline declares the same cluster, which reaches the backend's cluster refusal.
        """
        run = self.base
        pipeline = run.evidence.pipeline_journals["A"]
        identity = copy.deepcopy(pipeline["run_identity"])
        identity["objective_design"]["fit_clusters"] = [["R1", "R2"]]
        declared = rechain(pipeline, identity=identity)
        evidence = with_journal(run.evidence, pipeline_journals={"A": declared})
        if not governed:
            return judge_campaign_run(run.definition, [run.item], evidence)
        governance = lm_module.governed_pipeline_identity

        def declaring(*args):
            expected = governance(*args)
            expected["objective_design"]["fit_clusters"] = [["R1", "R2"]]
            return expected

        with mock.patch.object(lm_module, "governed_pipeline_identity", declaring):
            return judge_campaign_run(run.definition, [run.item], evidence)

    def test_an_ungoverned_cluster_declaration_is_an_unrelated_pipeline_run(self):
        readiness = self.journal_declared_cluster(governed=False)
        self.assertIs(readiness.status, ReadinessStatus.NOT_READY)
        self.assertEqual(readiness.refusal_codes, (ReadinessRefusal.LM_HISTORY_UNRELATED.value,))
        self.assertIsNone(readiness.calibration_record)
        self.assertIsNone(readiness.to_dict()["released_calibration_parameters"])

    def test_a_confirmed_cluster_is_a_readiness_refusal_without_member_matching(self):
        readiness = self.journal_declared_cluster()
        self.assertIs(readiness.status, ReadinessStatus.NOT_READY)
        self.assertEqual(readiness.refusal_codes, (CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE,))
        self.assertIsNone(readiness.calibration_record)
        detail = readiness.refusal_reasons[0]["detail"]
        self.assertIn("no member pairing, ordering, averaging or dropping", detail)
        record = readiness.to_dict()
        self.assertIsNone(record["released_calibration_parameters"])
        self.assertFalse(record["inp_fragment_available"])
        self.assertIsNotNone(record["evidence"]["lm_provenance"])  # the LM history itself verified first
        with self.assertRaises(CalibrationFragmentRefusal):
            released_inp_fragment(readiness, run_source(self.base))

    def test_the_i5_verifier_refuses_a_cluster_bundle(self):
        from test_v12_i4_calibration_output import _Case  # the I4 / I5 confirmed-cluster fixture (genuine M4 run)

        case = _Case()
        case.setUp()
        try:
            inputs, item, run = case.cluster()
            with self.assertRaises(CandidateEvaluationUnverified) as refused:
                verify_candidate_evaluation(case.evidence(inputs, item), inputs, item, run)
            self.assertIn(CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE, str(refused.exception))
        finally:
            case.tearDown()

    def test_the_production_campaign_path_stops_at_a_cluster_trigger(self):
        run = self.base
        with self.assertRaises(ObservationSetMismatch) as stopped:
            check_observation_set(run.item.spec, run.item.frozen, run.item.holdout_rows, 1)
        self.assertIn("cluster trigger", str(stopped.exception))


def run_source(run) -> bytes:
    return run.evidence.source_inps["A"]


# ----------------------------------------------------------------------------- MATERIAL_IDENTIFICATION unchanged

class _MaterialRun:
    def __init__(self, definition, specimens, evidence, campaign, summary):
        self.definition, self.specimens, self.evidence, self.campaign, self.summary = (definition, specimens, evidence,
                                                                                       campaign, summary)


class MaterialPathTests(unittest.TestCase):
    _directory = None
    _runs: dict = {}

    def material_run(self, key):
        cls = MaterialPathTests
        if key not in cls._runs:
            if cls._directory is None:
                cls._directory = tempfile.TemporaryDirectory()
            tau, shift = key
            tag = Path(cls._directory.name) / f"{tau}-{shift}"
            definition = parse_campaign_definition(v12_definition(MATERIAL_IDENTIFICATION, tau))
            items, roots = [], {}
            for label in ("A", "B"):
                item, store = synthetic_specimen(definition, label, tag, TRUTH_E * (shift if label == "B" else 1.0))
                if label == "A":  # as test_v12_i5_contract_closure.FamilyConsistencyTests
                    item = replace(item, families=dict(item.families, R1="FAM-12"))
                items.append(item)
                roots["synthetic"] = store
            campaign = CampaignRun(definition, items, "m" * 64, CampaignRunConfig(
                tag / "runs", roots, "abq2024.bat", FakeSolver(), FakeExtractor(), {}, "m" * 64))
            summary = campaign.run()
            cls._runs[key] = _MaterialRun(definition, tuple(items), run_evidence(campaign, {}), campaign, summary)
        return cls._runs[key]

    def test_section_13_fail_releases_no_global_material_value(self):
        run = self.material_run((0.02, 1.12))
        readiness = judge_campaign_run(run.definition, run.specimens, run.evidence)
        self.assertIs(readiness.status, ReadinessStatus.REFUSED)
        record = readiness.to_dict()
        self.assertEqual(record["material_family_consistency"], "FAIL")
        self.assertEqual(record["material_formal_output"]["status"], "NO_GLOBAL_PARAMETER_VALUE")
        self.assertEqual(record["material_formal_output"]["released_values"], {})
        self.assertIn("FAMILY_CONSISTENCY_FAIL", [r["detail"] for r in readiness.refusal_reasons])
        self.assertEqual(record["material_claim"], "NO_MATERIAL_PROPERTY_CLAIM")
        self.assertEqual(readiness.diagnostic_candidate["parameters"], run.summary["parameters"])

    def test_material_behaviour_is_the_accepted_report_unchanged(self):
        for key, expected in (((0.02, 1.12), ReadinessStatus.REFUSED),
                              ((0.02, 1.0), ReadinessStatus.MATERIAL_VALUES_RELEASED)):
            with self.subTest(case=key):
                run = self.material_run(key)
                readiness = judge_campaign_run(run.definition, run.specimens, run.evidence)
                self.assertIs(readiness.status, expected)
                report = build_campaign_report(run.definition, run.specimens,
                                               run.campaign.journal.records("evaluation"),
                                               run.campaign.journal.records("result")[0])
                self.assertEqual(json.dumps(readiness.material_report, sort_keys=True, default=str),
                                 json.dumps(report, sort_keys=True, default=str))

    def test_real_run_a_section_13_fail_prevents_a_global_value(self):
        """READ-ONLY (store-gated): the archived RUN_A journals judged by the shared backend."""
        roots = fixture_roots_from_environment()
        if not {"m7-run-a", "snadwich", "carbon-project-archive"} <= set(roots):
            self.skipTest("data stores m7-run-a / snadwich / carbon-project-archive not configured")
        definition = load_campaign_definition(CAMPAIGNS / "M7_RUN_A.campaign.json")
        self.assertEqual(definition.campaign_hash, RUN_A_CAMPAIGN_HASH)
        specimens = campaign_module.prepare_campaign_specimens(definition, ROOT,
                                                               load_experiment_fixture_manifest(FIXTURES), roots)
        store = Path(roots["m7-run-a"])
        evidence = CampaignRunEvidence(_load(next(store.glob("campaign/*/journal.json"))),
                                       {doc["run_identity"]["extra"]["specimen"]: doc for doc in
                                        (_load(p) for p in store.glob("specimens/*/*/*/journal.json"))}, {}, {})
        readiness = judge_campaign_run(definition, specimens, evidence)
        record = readiness.to_dict()
        self.assertIs(readiness.status, ReadinessStatus.REFUSED)
        self.assertEqual(record["material_family_consistency"], "FAIL")
        self.assertEqual(record["material_formal_output"]["status"], "NO_GLOBAL_PARAMETER_VALUE")
        self.assertIn("FAMILY_CONSISTENCY_FAIL", record["material_formal_output"]["blockers"])
        self.assertEqual(record["evidence"]["lm_provenance"]["run_hash"],
                         _load(CAMPAIGNS / "M7_RUN_A.result.json")["run_hash"])
        self.assertIsNone(record["calibration"])
        self.assertIsNone(record["production_calibration"])


# ----------------------------------------------------------------------------- production execution safety

class ExecutionSafetyTests(_Runs):
    def calibration_execution_refused(self):
        run = self.base
        with tempfile.TemporaryDirectory() as tmp:
            config = CampaignRunConfig(Path(tmp) / "runs", {}, "abq2024.bat", FakeSolver(), FakeExtractor(), {},
                                       "m" * 64)
            with self.assertRaises(CalibrationNotImplementedRefusal) as refused:
                CampaignRun(run.definition, [run.item], "m" * 64, config)
            self.assertEqual(refused.exception.state, CALIBRATION_NOT_IMPLEMENTED)
            self.assertFalse((Path(tmp) / "runs").exists())
        with self.assertRaises(CalibrationNotImplementedRefusal):
            run.definition.require_executable()

    def judgement_executes_nothing(self):
        run = self.base
        forbidden = mock.Mock(side_effect=AssertionError("forbidden call"))
        before = sorted(p.as_posix() for p in self.tmp().rglob("*"))
        commands = list(run.solver.commands)
        with mock.patch.object(subprocess, "Popen", forbidden), mock.patch.object(subprocess, "run", forbidden), \
                mock.patch.object(os, "system", forbidden), \
                mock.patch.object(campaign_module, "run_bounded_lm", forbidden), \
                mock.patch.object(CampaignRun, "run", forbidden), mock.patch.object(CampaignRun, "evaluate", forbidden):
            readiness = self.judge()
        self.assertTrue(readiness.released)
        forbidden.assert_not_called()
        self.assertEqual(run.solver.commands, commands)
        self.assertEqual(sorted(p.as_posix() for p in self.tmp().rglob("*")), before)

    def test_calibration_execution_stays_refused(self):
        self.calibration_execution_refused()

    def test_the_backend_judges_without_executing_or_writing(self):
        self.judgement_executes_nothing()

    def test_backend_modules_import_no_executor(self):
        forbidden = {"subprocess", "os", "shutil", "services.forward_solver", "forward_solver",
                     "services.shape_extraction", "shape_extraction", "identification_step.run_bounded_lm"}
        for name in ("campaign_scientific_backend", "campaign_lm_provenance"):
            tree = ast.parse((ROOT / "src" / "services" / f"{name}.py").read_text(encoding="utf-8"))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported |= {alias.name for alias in node.names}
                elif isinstance(node, ast.ImportFrom):
                    module = (node.module or "").lstrip(".")
                    imported.add(module)
                    imported |= {f"{module}.{alias.name}" for alias in node.names}
                elif isinstance(node, ast.Call) and getattr(node.func, "id", None) in ("open", "CampaignRun"):
                    self.fail(f"{name} calls {node.func.id}")
                elif isinstance(node, ast.Attribute) and node.attr in ("write_text", "write_bytes", "mkdir", "run",
                                                                      "evaluate"):
                    self.fail(f"{name} uses .{node.attr}")
            self.assertEqual(imported & forbidden, set(), name)
            self.assertNotIn("run_bounded_lm", {i.rsplit(".", 1)[-1] for i in imported}, name)

    def test_only_the_synthetic_fixture_lifts_the_execution_gate(self):
        lift = "patch.object(CampaignDefinition, " + '"require_executable"'
        lifting = sorted(p.name for p in (ROOT / "tests").glob("*.py") if lift in p.read_text(encoding="utf-8"))
        self.assertEqual(lifting, ["v12_i6_support.py"])
        users = sorted(p.relative_to(ROOT).as_posix() for folder in ("src", "tools") for p in (ROOT / folder).rglob("*.py")
                       if any(isinstance(node, ast.Attribute) and node.attr == "require_executable"
                              for node in ast.walk(ast.parse(p.read_text(encoding="utf-8")))))
        self.assertEqual(users, ["src/services/identification_campaign_run.py", "tools/m7_campaign.py"])  # unchanged
        # callers (CampaignRun, the run manifest, the M7 CLI); no I6 module calls, wraps or bypasses the gate


# ----------------------------------------------------------------------------- GUI readiness (existing page; not M8)

class GuiReadinessTests(_Runs):
    """The existing Material Identification "Data Readiness Check" page shows the stored backend record only."""

    def application(self, record=None):
        from test_material_identification_ui import _ApplicationHarness

        application = _ApplicationHarness()._application()
        if record is not None:
            application.scientific_readiness_record = record
        application._refresh_material_identification_pages()
        return application

    def rows(self, application) -> dict:
        return dict(application.material_scientific_readiness_table.items.values())

    def test_empty_state_is_explicit(self):
        application = self.application()
        self.assertEqual(application.material_scientific_readiness_status_label.kwargs["text"], "NOT AVAILABLE")
        self.assertEqual(application.material_scientific_readiness_table.items, {})

    def test_released_calibration_is_shown_with_its_identity_and_synthetic_provenance(self):
        readiness = self.judge()
        rows = self.rows(self.application(readiness.to_dict()))
        self.assertEqual(rows["Scientific question"], "SPECIMEN_ENGINEERING_CALIBRATION")
        self.assertEqual(rows["Readiness"], "RELEASED")
        self.assertIn("acceptance tolerance only", rows["τ_mf"])
        self.assertIn(self.base.campaign.run_hash[:12], rows["Campaign identity"])
        self.assertIn("E_in_plane_mpa = ", rows["Released calibration"])
        self.assertIn("not a material property", rows["Released calibration"])
        self.assertIn(CONDITIONAL_COVARIANCE, rows["Uncertainty"])
        self.assertEqual(rows["Diagnostic-only candidate"], "none")
        self.assertIn("SYA/fake", rows["Evidence"])
        self.assertTrue(rows["Production calibration"].startswith("NO_HUMAN_AUTHORISED_PRODUCTION_CALIBRATION_RUN"))
        self.assertTrue(rows["Production execution"].startswith("NOT_AUTHORISED"))

    def test_refusals_show_reasons_and_only_a_diagnostic_candidate(self):
        imprecise = self.run_of("imprecise")
        cases = {
            "gate refusal": judge_campaign_run(imprecise.definition, [imprecise.item], imprecise.evidence),
            "evidence refusal": self.judge(evidence=with_journal(self.base.evidence, campaign_journal={})),
            "cluster": ClusterReadinessTests.journal_declared_cluster(self),
        }
        for name, readiness in cases.items():
            with self.subTest(case=name):
                application = self.application(readiness.to_dict())
                rows = self.rows(application)
                self.assertEqual(application.material_scientific_readiness_status_label.kwargs["text"],
                                 readiness.status.value)
                self.assertEqual(rows["Released calibration"], "none released")
                self.assertNotEqual(rows["Refusal reasons"], "none")
                for code in readiness.refusal_codes:
                    self.assertIn(code, rows["Refusal reasons"])
        rows = self.rows(self.application(cases["gate refusal"].to_dict()))
        self.assertIn("DIAGNOSTIC_OPTIMIZER_CANDIDATE, NOT_A_RELEASE_VALUE", rows["Diagnostic-only candidate"])
        rows = self.rows(self.application(cases["cluster"].to_dict()))
        self.assertEqual(rows["Cluster member evidence"], "NOT AVAILABLE: a confirmed cluster cannot be released")

    def test_section_13_fail_shows_no_global_material_value(self):
        material = MaterialPathTests.material_run(self, (0.02, 1.12))
        readiness = judge_campaign_run(material.definition, material.specimens, material.evidence)
        rows = self.rows(self.application(readiness.to_dict()))
        self.assertEqual(rows["Scientific question"], MATERIAL_IDENTIFICATION)
        self.assertIn("NO_GLOBAL_PARAMETER_VALUE", rows["Global material value"])
        self.assertIn("SPEC §13 family consistency FAIL", rows["Global material value"])
        self.assertEqual(rows["Released calibration"], "none released")
        self.assertEqual(rows["Production calibration"], "not applicable")

    def test_the_gui_judges_nothing(self):
        source = (ROOT / "src" / "material_identification_ui.py").read_text(encoding="utf-8")
        for name in ("judge_campaign_run", "verify_lm_history", "evaluate_calibration_gate",
                     "build_calibration_output", "CampaignRun", "tau_mf", "SPECIMEN_ENGINEERING_CALIBRATION"):
            self.assertNotIn(name, source)
        self.assertIn("readiness_presentation", source)
        forged = dict(self.judge().to_dict(), schema="another/schema")  # an unknown record is not presented
        self.assertEqual(self.rows(self.application(forged)), {})


if __name__ == "__main__":
    unittest.main()
