"""V12-I5 — negative / regression closure of the SPEC v1.2 contract (D-078; tests only, no Abaqus).

A finite acceptance matrix over the accepted V12-I1 … V12-I4 implementation.  It reuses the I1–I4 fixtures and
does not repeat their unit tests; every case here is checked end to end (campaign → gate → output → fragment):

- the two predeclared questions, their distinct identities and the absence of any fallback;
- τ_mf boundaries and its exclusion from Σ, the objective, statistical_sd, Birge, LOO, the precision envelope and
  SPEC §13;
- SPEC §13 FAIL / NOT_EVALUABLE blocking every global value although the τ_mf-aware pattern passes;
- every calibration-gate refusal as a REFUSED output record with no released value and no fragment;
- evidence anti-mixing, cluster member rows, the fail-closed calibration material clone;
- historical v1.1 evidence immutability and the still-blocked production calibration execution.
"""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
import hashlib
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


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import numpy as np

from domain.campaign_definition import (
    CALIBRATION_NOT_IMPLEMENTED,
    CAMPAIGN_SCHEMA,
    MATERIAL_IDENTIFICATION,
    NO_MATERIAL_CLAIM,
    SPECIMEN_ENGINEERING_CALIBRATION,
    CalibrationNotImplementedRefusal,
    CampaignDefinitionError,
    load_campaign_definition,
    parse_campaign_definition,
)
from domain.experiment_fixture import fixture_roots_from_environment, load_experiment_fixture_manifest
from domain.forward_model_manifest import PARAMETERISATIONS, bind_forward_model, load_forward_model_manifest
from domain.identification_run import canonical_hash, verify_journal_chain
from domain.specimen_manifest import load_specimen_manifest
from m4_6_support import FakeExtractor, FakeSolver
from services import forward_builder
from services import identification_campaign_run as campaign_module
from services import specimen_calibration_output as output_module
from services import candidate_evaluation_evidence as evidence_module
from services.shape_extraction import load_run_pack
from services.family_consistency import CHI2_CONDITIONS, FamilyConsistencyStatus, family_consistency
from services.identification_campaign_run import (
    NO_GLOBAL_VALUE,
    CampaignRun,
    CampaignRunConfig,
    build_campaign_report,
    campaign_family_consistency,
    campaign_run_identity,
    prepare_run_manifest,
    row_sigma,
)
from services.identification_uncertainty import (
    PatternStatus,
    ResidualTerm,
    birge_adjustment,
    residual_pattern_test,
    residual_terms,
    statistical_sd,
)
from services.model_form_robustness import linearised_model_form_robustness
from services.identification_verdict import EvidenceState, GuardEvidence
from services.practical_identifiability import (
    PracticalIdentifiabilityInputError,
    RankStatus,
    analyse_practical_identifiability,
)
from services.specimen_calibration_gate import CalibrationGateStatus, GovernedRow, evaluate_calibration_gate
from services.specimen_calibration_output import (
    CANDIDATE_LABELS,
    LABELS,
    CalibrationFragmentRefusal,
    CalibrationOutputStatus,
    build_calibration_output,
    governed_baseline_rows,
    governed_engineering_constants,
    render_calibration_inp_fragment,
)
from test_m7_campaign import TRUTH_E, synthetic_definition, synthetic_specimen
from test_v12_i1_campaign_question import calibration_definition, v12_definition
from test_v12_i3_calibration_gate import E_FAMILIES, E_ROWS, P_HAT, SIGMA, SIGMA_C, build
from test_identification_uncertainty import E, system
from test_v12_i4_calibration_output import BASELINE_RATIO, NONE_EXCLUDED, _Case, material_block
from v12_evidence_support import designed_frozen_rows, evaluated_bundle


DOCS = ROOT / "docs" / "auto_id"
CAMPAIGNS = DOCS / "campaigns"
RUN_A_CAMPAIGN_HASH = "0a21ad0567901034b521b822b52f0c29944e96394f3692e1a8ebcd7ccd8d2ccf"
RUN_B_CAMPAIGN_HASH = "7c1f5db24fa9c4f4e90c82ca802c6dae22cbe5c7ec9e2989e63e439f678540e5"
RUN_A_RUN_HASH = "8ed03be3be86aa83877367ab505cf2d66ae711c6c9a2a7a4dc47ab6c499923a2"
RUN_B_RUN_HASH = "fb5234116c6e9413e4b070e901f97b8c6e210d535daefe15f0cdb5b9f8ad87f0"
# Canonical content hashes (parsed JSON, so independent of checkout line endings) of the historical v1.1 evidence.
# Unchanged since main 9bff6c7 (M7b closure, before SPEC v1.2); pinned here at main 90e2378 (V12-I4 merged).
HISTORICAL_RECORDS = {
    "campaigns/M7_CLOSURE.json": "e015a935e34301223a3c0e9f70464d4a72d8952292f779fc9353f9a20e702d24",
    "campaigns/M7_RUN_A.archive-extraction.json": "bcbfb60e7677e878743cef043116bd5ab75c6436f5f4fe03f13d7ea16baf1f22",
    "campaigns/M7_RUN_A.archive-reuse.json": "91c8bc547c738a65ec5bdf4ff1e2d6f3d91e518fd5bdab4ebb547fc7b1a18b92",
    "campaigns/M7_RUN_A.campaign.json": RUN_A_CAMPAIGN_HASH,
    "campaigns/M7_RUN_A.result.json": "82501b35c4effc0fd829d40d6e3aaef105d5a70cc8e8a3b0ba306b9caa66c5c2",
    "campaigns/M7_RUN_B.archive-extraction.json": "c2df90abde073a801a3d09082ce8ec06925550938106777de77d0de65bf27e10",
    "campaigns/M7_RUN_B.archive-reuse.json": "fa19cfbb4f818c66ab0f58479fbce97e9fc767f3dd17909d8f0ffa48e545173e",
    "campaigns/M7_RUN_B.campaign.json": RUN_B_CAMPAIGN_HASH,
    "campaigns/M7_RUN_B.result.json": "8a9264eca72827889042fb5430ed057f9d44ebb9305d0b10db9c28d433a2b2de",
    "campaigns/archive_extraction/SP02_05239a3b56508244.shape-pack.json":
        "6421633e8c103385588f24d5fbdb4218602975794172b4156add472da2226c22",
    "campaigns/archive_extraction/SP02_13363f977809dbff.shape-pack.json":
        "47690ca2e08aca5974a233a707557ad7718ce6ad5fbf0de2908f811b97cd7444",
    "campaigns/archive_extraction/SP02_84753f636064e192.shape-pack.json":
        "0319db02a05d1e0968a3d94df796ddd139972d9105b891a773cbd79cf4d84dac",
    "campaigns/archive_extraction/SP02_ade5dffa2fde3903.shape-pack.json":
        "469988d9667fbff57433169bc0340dd88e0333165713ccc666e22db3e62d9573",
    "audit_corrections/M7_FAMILY_CONSISTENCY_CORRECTION.json":
        "3ea488d5dde7cf73910930514f0bece280aeba73dd06a2a044f11f23fcafb6d1",
    "audit_corrections/M7_PER_SPECIMEN_DIAGNOSTICS.json":
        "54427d2805e3d4b1a7811c7a1eb1bb4a8b5968b57433037f193d113a52ac3890",
    "baselines/SP02.carbon4c-baseline.json": "e2e31535dfce8f929976607e314119d73e3069842778dadd71a9537f617bbfbc",
    "baselines/SP13.carbon4c-baseline.json": "24b40e6855eacd5b8797e912ccfc421c5fb3eacfd3b455515fdcd8edf368c64e",
    "registration_evidence/SP02_physical_registration_reconstruction.json":
        "01d43dae9e882c66d989ef8f89a06a274f39151c6f2bd5612231a871bdb60f15",
    "registration_evidence/SP02_registration_reevaluation.json":
        "a488f1ebe01b15d7fce50f5219554011404a8ea24f6208938387c32a5678d553",
    "registration_evidence/SP02_registration_uncertainty.json":
        "fbea6a008641ddb999834e5db90e89082355100bd622a0656039fdc0a3dfb75c",
    "registration_evidence/SP13_physical_registration_reconstruction.json":
        "ff5c84d1d7d713df6712f56d6e683ca644fcce34499c8b8d04f42cd5807d1101",
    "registration_evidence/SP13_registration_reevaluation.json":
        "5c2e897c813107323c768316d8b38463988b59371cab6968f590420ca437d27b",
    "registration_evidence/SP13_registration_uncertainty.json":
        "508c77b9e0560b0035ed8236c9d885be28b834e25cdc7d098c0fc9718acdd8b6",
    "forward_models/SP02.forward.json": "bc3d9b867ba7099e2ea2829acac9c88949678de587632eba36f6bd2c944e26ba",
    "forward_models/SP02.physical.forward.json": "f53226a05eabb2af1a49153880e67cba4a9a723e72f7fb32ea09f2537f7080af",
    "forward_models/SP13.forward.json": "f54079004c953749feb06bc0cf81c24a8545a74eb9f40d38cb3cd5fc831aa2b9",
    "forward_models/SP13.physical.forward.json": "ec6f5ee2afd2aed60edcc90c5fa8ceb5b9afa75efd94a7020de59ff72da4d8b7",
    "forward_models/accepted_forward_jobs.json": "40914b07a4034eda7eddcbd50662cfc28f1b896394386f644eae3db4fd4e8f71",
    "../registrations/SP02_frozen_registration.json": "b800e6b05aca19c821c1f2481720f7645068aa18c4349ea1e43681065d9e855e",
    "../registrations/SP02_physical_registration.json": "97e2c54b73a66e23d2686f8b1a5b02a13f2e630dd2c6b17a97cfb7ab6995eae5",
    "../registrations/SP13_frozen_registration.json": "7506cd5c58c3f13eb0c28e5a7995c788d2f6218c47cbc2948bb7842fb38af69f",
    "../registrations/SP13_physical_registration.json": "e1634ab96cd0b20fc938f353521c133c0499955cb90dc753f6c6b6b2253579c5",
}
# The archived run stores (store-gated): byte SHA-256 of every journal, manifest, report and journalled pack record.
RUN_STORE_FILES = {
    "m7-run-a": {
        "archive_reuse/journal.json": "e4a626025e5b57a22b22222ff063c80829ac866ec5b92aa32ab0199ca6ed2ea0",
        "archive_reuse/packs/SP02_13363f977809dbff.shape-pack.json":
            "a2931b9bd4b0c0d5ba06ae65fb91c8fc071ebc35c33bd60b4714d0eaba09bfe3",
        "archive_reuse/packs/SP02_84753f636064e192.shape-pack.json":
            "12e2d7db9ba41e20aa41dc9897a2b7af0c20be4e835a1583bc6021c1c46f252f",
        f"campaign/{RUN_A_RUN_HASH}/journal.json": "e97f07741162a159b7aa068a45f97fe3376d062bf4f886df83d17b8c41f7564f",
        "run_a_report.json": "23b0bfe76556ec094fc954ef0cb83fd12db4ee407a9661f2f92f07be6f81c62f",
        "specimens/CFRP-T300-plain-0.45-oldstock/SP-02/223e013f4aae97921e5baeb6cd11f11d5aea6a2d1d4aff6bba058d5fd50b38c3/"
        "journal.json": "2f342997300f7da0340655c700c03258559ce55eadd2b3b3c5c62f6f1b0220e5",
        "specimens/CFRP-T300-plain-0.45-oldstock/SP-02/223e013f4aae97921e5baeb6cd11f11d5aea6a2d1d4aff6bba058d5fd50b38c3/"
        "packs/SP02_34f86ec4cc03237a.shape-pack.json": "a4bb244e9f7627fd65ac23479216163efd74a66d46ff8b335ca52fd91680c074",
        "specimens/CFRP-T300-plain-0.45-oldstock/SP-13/7e992dee8c9bee27f767e99a670d1f9762d7de7a641912c8c132fa4a8c916881/"
        "journal.json": "425558799f6ac2d477df1231605b9c7d732aa8efdfb08c4043c3e3d5aaa30b0d",
        "specimens/CFRP-T300-plain-0.45-oldstock/SP-13/7e992dee8c9bee27f767e99a670d1f9762d7de7a641912c8c132fa4a8c916881/"
        "packs/SP13_0188a303fd3bc39d.shape-pack.json": "879919ecd2827d7512370f04e6dca1e57b51a4b2c5b895dfaf7891a195097845",
    },
    "m7-run-b": {
        "archive_reuse/journal.json": "1657cc6728e3301f9b5ec4d8b64950d8e9597fac57cccc4183b6d84fac50e469",
        "archive_reuse/packs/SP02_05239a3b56508244.shape-pack.json":
            "ac78db2f5d7f32b0f3021e7c73147aff306a38df3102fe2676fab80384a1abbb",
        "archive_reuse/packs/SP02_ade5dffa2fde3903.shape-pack.json":
            "1ef7c3761af3fa987d5b827834d4b7f8409e1cf7f4362e72a52e3ee8d8f3bb63",
        f"campaign/{RUN_B_RUN_HASH}/journal.json": "2efe459ccb9c86ebeb6817526ff14a7e1c68bf1ccd0e070afbc1e9516395c982",
        "run_b_manifest.json": "71c31821a0743d7f37842be9593ffce8a8916dab80fcc121c1221cf24eb856a9",
        "specimens/CFRP-T300-plain-0.45-oldstock/SP-02/a128385da7f0d978e07cf79721df6cbd541fbbd503792b2119b81bde2b74cecb/"
        "journal.json": "b4d184fa47efa534688ff16ac9b0a3a67797bdb0a667364fe210e8c7b176fd6f",
        "specimens/CFRP-T300-plain-0.45-oldstock/SP-02/a128385da7f0d978e07cf79721df6cbd541fbbd503792b2119b81bde2b74cecb/"
        "packs/SP02_5b6eaf2fa8d1c56c.shape-pack.json": "c27ed8411a730a84f3351ba75d587c6c7daa846d9aa391168e96072f5f011c63",
        "specimens/CFRP-T300-plain-0.45-oldstock/SP-02/a128385da7f0d978e07cf79721df6cbd541fbbd503792b2119b81bde2b74cecb/"
        "packs/SP02_9bc6b114e5412d25.shape-pack.json": "ec5d518e6628c7ca4932c6df2b611bba57338993818511ea16c43117329563b5",
        "specimens/CFRP-T300-plain-0.45-oldstock/SP-02/a128385da7f0d978e07cf79721df6cbd541fbbd503792b2119b81bde2b74cecb/"
        "packs/SP02_ac0561f6867ebf53.shape-pack.json": "22054836539669c8247e52323aba0e7c01927b8f4939c257f2589114b5d6adc6",
        "specimens/CFRP-T300-plain-0.45-oldstock/SP-13/a134f7dcd121e18880ff35b484635611b853088c6082cab7c7a9613ad620464b/"
        "journal.json": "a9991b356142d3ac7132639c3ce0c4d06f91b7564adcc8eb6b7a7d37fc94d83b",
        "specimens/CFRP-T300-plain-0.45-oldstock/SP-13/a134f7dcd121e18880ff35b484635611b853088c6082cab7c7a9613ad620464b/"
        "packs/SP13_3f7e327ba640406d.shape-pack.json": "9acf9679562c71480e7c3b3ebb0f25fcd03e6196f5776789a84fda120b5888c1",
        "specimens/CFRP-T300-plain-0.45-oldstock/SP-13/a134f7dcd121e18880ff35b484635611b853088c6082cab7c7a9613ad620464b/"
        "packs/SP13_48875a2cbd480a18.shape-pack.json": "9dbd627d3c6a3f32c88456fb9498005bb0a96546a513e0bde9573cbabddd614c",
        "specimens/CFRP-T300-plain-0.45-oldstock/SP-13/a134f7dcd121e18880ff35b484635611b853088c6082cab7c7a9613ad620464b/"
        "packs/SP13_c7bb74ceebcce108.shape-pack.json": "4f3f918d07f5af5219985e8394ee5314a3fc2cb4d6ab1ede97291e405ea5fefd",
    },
}
OBSERVATION_HASHES = {"SP02": "b5da4f5f8098962fdbf947b7ad22fec70bc8a2dbc759482a4f492141e050f643",
                      "SP13": "945eee3159b88dc1fa2eb963c58dd23406523e3e6c0ae724dfd458e68110963a"}

# One calibration specimen with four FIT rows in two families and one holdout: the V12-I3 reference bundle
# (``build()`` defaults) bound to a synthetic specimen, so every case runs through gate, output and fragment.
FOUR_ROWS = (("R1", 1, 7, "FIT"), ("R2", 2, 8, "FIT"), ("R3", 3, 9, "FIT"), ("R4", 4, 10, "FIT"),
             ("H1", 5, 11, "HOLDOUT"))
FOUR_FAMILIES = dict(E_FAMILIES, H1="T")
FIT_ROWS = ("R1", "R2", "R3", "R4")
FOUR_FIT = [0.5, -0.4, 0.3, -0.2]  # whitened FIT residuals of the reference bundle (Δ ln f = r · 0.003)
CLUSTER_ID = "C(R3+R4)"
FAIL = GuardEvidence("guard", EvidenceState.FAIL, "explicit synthetic evidence", "failed")


def _frozen_mac(item, row_id: str, mac: float):
    rows = tuple(replace(r, mac=mac) if r.row_id == row_id else r for r in item.frozen.rows)
    return replace(item, frozen=replace(item.frozen, rows=rows))


def frozen_baseline(inputs, item, values):
    """Frozen baseline FE frequencies with ln(f_FE / f_EXP) = ``values[row]``; the bundle takes the governed rows."""
    rows = tuple(replace(r, fe_hz=r.experimental_hz * math.exp(values[r.row_id]),
                         relative_frequency_error=math.exp(values[r.row_id]) - 1) if r.row_id in values else r
                 for r in item.frozen.rows)
    item = replace(item, frozen=replace(item.frozen, rows=rows))
    return replace(inputs, baseline_rows=governed_baseline_rows(item)), item


def _keys(node) -> set:
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in _keys(v)}
    if isinstance(node, list):
        return {k for v in node for k in _keys(v)}
    return set()


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class _Bundles(_Case):
    """Synthetic calibration evidence bound to a synthetic specimen (``_Case.simple`` / ``_Case.cluster`` from I4)."""

    def bundle(self, families=FOUR_FAMILIES, tau=0.02, fit=FOUR_FIT, holdout=None, p_hat=None, baseline=None,
               macs=None, sensitivities=E_ROWS):
        """A calibration specimen whose frozen set is designed so that the genuine M4 evaluation of p̂ (fake solver)
        has the whitened FIT residuals ``fit`` and HOLDOUT residual ``holdout``; the frozen baseline Δ ln f is
        ``baseline`` (default +0.03 on every row).  The bundle is built from that journalled evaluation."""
        p_hat = dict(p_hat or P_HAT)
        holdout = holdout or (("H1", families["H1"], 0.6),)
        data = calibration_definition(tau)
        data["specimens"][0]["rows"] = [{"row_id": r, "experimental_mode": e, "fe_mode": f, "role": role}
                                        for r, e, f, role in FOUR_ROWS]
        definition = parse_campaign_definition(data)
        base = self.tmp / f"b{len(self._specimens)}"
        item, store = synthetic_specimen(definition, "A", base)
        self.source_inp = (store / "models" / "SYA.inp").read_bytes()
        item = replace(item, holdout_rows=("H1",), families=dict(families))
        deltas = {**{r: v * SIGMA for r, v in zip(FIT_ROWS, fit)}, **{h: v * SIGMA for h, _, v in holdout}}
        frozen = designed_frozen_rows(item.spec.rows, p_hat, deltas, baseline or {r: 0.03 for r in deltas}, macs)
        inputs, item, _, evidence = evaluated_bundle(definition, item, store, base / "runs", p_hat, sensitivities,
                                                     frozen)
        self._specimens[item.frozen.observation_hash] = (definition, store, base, sensitivities)
        self.register(inputs, evidence)
        return inputs, item

    def candidate(self, item, p_hat):
        """Another candidate p̂ evaluated by the same specimen pipeline run (same journal): its own bundle."""
        definition, store, base, sensitivities = self._specimens[item.frozen.observation_hash]
        inputs, _, _, evidence = evaluated_bundle(definition, item, store, base / "runs", p_hat, sensitivities)
        self.register(inputs, evidence)
        return inputs, evidence

    def setUp(self):
        super().setUp()
        self._specimens = {}

    def output(self, inputs, item, evidence=None, **kwargs):
        run = campaign_run_identity(inputs.definition, [item], "m" * 64, {})
        return build_calibration_output(inputs, item, run, NONE_EXCLUDED, evidence or self.evidence(inputs, item),
                                        **kwargs)

    def with_system(self, inputs, item, sensitivities):
        """The same verified evaluation judged on another M5 system: its M5 records recomputed (no robustness when
        the system is rank deficient: M5.7 needs a full system).  Returns (inputs, item, evidence)."""
        evidence = self.evidence(inputs, item)
        record = next(e["record"] for e in evidence.pipeline_journal["entries"]
                      if e["kind"] == "evaluation" and e["record"]["evaluation_hash"] == evidence.evaluation_hash)
        fit = residual_terms(list(FIT_ROWS), [], record["residuals"], item.families, {r: SIGMA for r in FIT_ROWS})
        s = system({r: sensitivities[r] for r in FIT_ROWS}, (E,), sd=SIGMA)
        statistical = statistical_sd(s, inputs.statistical.context)
        try:
            robustness = linearised_model_form_robustness(s, fit, inputs.p_hat)
        except PracticalIdentifiabilityInputError:
            robustness = None
        changed = replace(inputs, analysis=analyse_practical_identifiability(s), statistical=statistical,
                          birge=birge_adjustment(s, statistical, inputs.pattern, fit), robustness=robustness)
        return changed, item, replace(evidence, system=s)

    def assert_refused_output(self, record, code):
        self.assertIs(record.status, CalibrationOutputStatus.REFUSED)
        self.assertIn(code, [r["code"] for r in record.refusal_reasons])
        self.assertIsNone(record.calibration_parameters)
        data = record.to_dict()
        self.assertNotIn("calibration_parameters", data)
        self.assertEqual((data["output_class"], data["labels"]), (None, []))
        self.assertEqual(data["diagnostic_optimizer_candidate"]["labels"], list(CANDIDATE_LABELS))
        with self.assertRaises(CalibrationFragmentRefusal):
            governed_engineering_constants(record)
        with self.assertRaises(CalibrationFragmentRefusal):
            render_calibration_inp_fragment(record, {}, self.source_inp)


# ----------------------------------------------------------------------------- §1 the two questions

class QuestionContractTests(_Bundles):
    def test_questions_are_explicitly_predeclared_with_distinct_identities(self):
        material = parse_campaign_definition(v12_definition(MATERIAL_IDENTIFICATION))
        calibration_data = calibration_definition()
        calibration = parse_campaign_definition(calibration_data)
        self.assertEqual((material.scientific_question, calibration.scientific_question),
                         (MATERIAL_IDENTIFICATION, SPECIMEN_ENGINEERING_CALIBRATION))
        for key in ("scientific_question", "tau_mf"):  # never inferred
            with self.subTest(missing=key), self.assertRaises(CampaignDefinitionError):
                parse_campaign_definition({k: v for k, v in calibration_data.items() if k != key})
        # the same one-specimen evidence declared under the other question is another campaign (and invalid: §6)
        with self.assertRaises(CampaignDefinitionError):
            parse_campaign_definition(dict(calibration_data, scientific_question=MATERIAL_IDENTIFICATION))
        self.assertNotEqual(material.campaign_hash, parse_campaign_definition(
            v12_definition(SPECIMEN_ENGINEERING_CALIBRATION)
            | {"specimens": v12_definition()["specimens"][:1]}).campaign_hash)
        inputs, item = self.bundle()
        record = self.output(inputs, item)
        self.assertEqual(record.to_dict()["scientific_question"], SPECIMEN_ENGINEERING_CALIBRATION)
        self.assertEqual(record.identity["campaign_hash"], inputs.definition.campaign_hash)
        self.assertEqual(evaluate_calibration_gate(inputs).to_dict()["scientific_question"],
                         SPECIMEN_ENGINEERING_CALIBRATION)

    def test_no_automatic_fallback_in_either_direction(self):
        calibration = parse_campaign_definition(calibration_definition())
        with self.assertRaises(CalibrationNotImplementedRefusal):  # calibration never runs as material ID
            calibration.require_executable()
        material = parse_campaign_definition(v12_definition(MATERIAL_IDENTIFICATION))
        inputs, item = self.bundle()
        as_material = replace(inputs, definition=material)  # material evidence never becomes a calibration
        self.assertEqual(evaluate_calibration_gate(as_material).refusal_codes, ("WRONG_SCHEMA_OR_QUESTION",))
        with self.assertRaisesRegex(PracticalIdentifiabilityInputError, "SPECIMEN_ENGINEERING_CALIBRATION"):
            build_calibration_output(as_material, item, {}, NONE_EXCLUDED, self.evidence(inputs, item))

    def test_a_not_identifiable_material_result_cannot_become_a_released_calibration(self):
        # A material campaign whose formal output releases nothing (SPEC §13 FAIL) ...
        report = FamilyConsistencyTests.reports()[(0.02, 1.12)]
        self.assertEqual(report["formal_output"]["status"], NO_GLOBAL_VALUE)
        material_campaign = FamilyConsistencyTests.campaigns[(0.02, 1.12)]
        # ... cannot be re-labelled: its run identity does not belong to any calibration campaign, and a calibration
        # needs its own separately declared campaign and run identity.
        inputs, item = self.bundle()
        with self.assertRaisesRegex(PracticalIdentifiabilityInputError, "another campaign"):
            build_calibration_output(inputs, item, material_campaign.identity, NONE_EXCLUDED,
                                     self.evidence(inputs, item))
        record = self.output(inputs, item)  # the separately declared calibration run
        self.assertTrue(record.released, record.refusal_reasons)
        self.assertNotEqual(record.identity["campaign_hash"], material_campaign.definition.campaign_hash)

    def test_a_calibration_pass_does_not_change_the_material_verdict(self):
        campaign = FamilyConsistencyTests.campaigns[(0.02, 1.12)]
        before = FamilyConsistencyTests.reports()[(0.02, 1.12)]
        inputs, item = self.bundle()
        self.assertTrue(self.output(inputs, item).released)  # a RELEASED calibration of one specimen
        after = json.loads(json.dumps(build_campaign_report(
            campaign.definition, campaign.specimens, campaign.journal.records("evaluation"),
            FamilyConsistencyTests.results[(0.02, 1.12)]), default=str))
        self.assertEqual(after, before)
        self.assertEqual(after["material_claim"], NO_MATERIAL_CLAIM)
        record = self.output(inputs, item).to_dict()
        self.assertFalse({"verdict", "verdicts", "material_property", "material_claim", "formal_output"} & _keys(record))
        self.assertIn("the material verdict is a separate question and is not changed by this record", record["notes"])


# ----------------------------------------------------------------------------- §4 τ_mf

def _term(term_id, family, r, sigma, rows=None):
    return ResidualTerm(term_id, rows or (term_id,), family, r, sigma)


class TauMfRegressionTests(_Bundles):
    TAU = 0.02

    def family(self, *terms, tau=TAU):
        return residual_pattern_test(list(terms), [], tau)

    def holdout(self, term, tau=TAU):
        return residual_pattern_test([_term("R9", "F9", 0.1, 0.003)], [term], tau)

    def test_boundaries_sigma_and_tau_dominated(self):
        # σ 0.003: τ dominates both rules; σ 0.008: τ for the family (2.5 > 2), 3σ for the holdout; σ 0.0125: 2σ / 3σ
        for sigma, family_limit, holdout_limit in ((0.003, self.TAU / 0.003, self.TAU / 0.003),
                                                   (0.008, self.TAU / 0.008, 3.0), (0.0125, 2.0, 3.0)):
            with self.subTest(sigma=sigma):
                self.assertEqual(family_limit, max(2.0, self.TAU / sigma))
                self.assertEqual(holdout_limit, max(3.0, self.TAU / sigma))
                at = self.family(_term("R1", "F1", family_limit, sigma), _term("R2", "F1", family_limit, sigma))
                self.assertEqual(at.systematic_families, ())  # equality is not systematic
                above = math.nextafter(family_limit, math.inf)
                over = self.family(_term("R1", "F1", above, sigma), _term("R2", "F1", above, sigma))
                self.assertEqual(over.systematic_families, ("F1",))
                negative = self.family(_term("R1", "F1", -above, sigma), _term("R2", "F1", -above, sigma))
                self.assertEqual(negative.systematic_families, ("F1",))  # same sign, either sign
                mixed = self.family(_term("R1", "F1", above, sigma), _term("R2", "F1", -above, sigma))
                self.assertEqual(mixed.systematic_families, ())
                single = self.family(_term("R1", "F1", above, sigma), _term("R2", "F2", above, sigma))
                self.assertEqual(single.systematic_families, ())  # at least two FIT terms per family
                self.assertIs(self.holdout(_term("H1", "T", holdout_limit, sigma)).status, PatternStatus.PASS)
                self.assertIs(self.holdout(_term("H1", "T", -math.nextafter(holdout_limit, math.inf), sigma)).status,
                              PatternStatus.FAIL)

    def test_every_term_with_its_own_sigma(self):
        # the same |Δ ln f| = 0.022 exceeds max(2σ, τ) = 0.02 at σ 0.003 but not 0.025 at σ 0.0125
        loose, tight = _term("R1", "F1", 0.022 / 0.003, 0.003), _term("R2", "F1", 0.022 / 0.0125, 0.0125)
        self.assertEqual(self.family(loose, tight).systematic_families, ())  # every term must exceed
        both = self.family(loose, _term("R2", "F1", 0.026 / 0.0125, 0.0125))
        self.assertEqual(both.systematic_families, ("F1",))
        with self.assertRaisesRegex(PracticalIdentifiabilityInputError, "governed σ"):
            self.family(_term("R1", "F1", 1.0, None), _term("R2", "F1", 1.0, 0.003))

    def test_cluster_term_uses_the_cluster_sigma(self):
        cluster = _term(CLUSTER_ID, "F2", 0.008 / SIGMA_C, SIGMA_C, ("R3", "R4"))  # 0.008 > 3σ_C = 0.00636
        result = self.holdout(cluster, tau=0.005)
        self.assertEqual(result.holdout_failures, (CLUSTER_ID,))
        record = next(t for t in result.to_dict()["terms"] if t["term_id"] == CLUSTER_ID)
        self.assertAlmostEqual(record["sigma_term"], SIGMA_C, places=12)  # the governed cluster σ (recorded)
        self.assertAlmostEqual(record["effective_threshold_ln"], 3 * SIGMA_C, places=12)
        per_row = self.holdout(_term(CLUSTER_ID, "F2", 0.008 / SIGMA, SIGMA, ("R3", "R4")), tau=0.005)
        self.assertIs(per_row.status, PatternStatus.PASS)  # the member-row σ would hide it: it is not used

    def test_invalid_or_missing_tau(self):
        for bad in (0.0, -0.01, 0.0200001, math.nan, math.inf, True, "0.02", None):
            with self.subTest(tau_mf=bad), self.assertRaises(CampaignDefinitionError):
                parse_campaign_definition(calibration_definition(bad))
        for bad in (0.0, -0.01, 0.0200001, math.nan, math.inf, True, "0.02"):
            with self.subTest(pattern_tau=bad), self.assertRaises(PracticalIdentifiabilityInputError):
                residual_pattern_test([_term("R1", "F1", 1.0, 0.003)], [], bad)
        inputs, item = self.bundle()
        for pattern_tau, code in ((None, "PATTERN_EVIDENCE_NOT_V1_2"), (0.01, "TAU_MF_MISMATCH")):
            with self.subTest(pattern_tau=pattern_tau):  # v1.1 pattern evidence / τ_mf of another declaration
                changed = with_pattern(inputs, self.evidence(inputs, item), pattern_tau)
                self.assertIn(code, evaluate_calibration_gate(changed).refusal_codes)  # the I3 gate refuses ...
                with self.assertRaisesRegex(PracticalIdentifiabilityInputError, "residual-pattern record"):
                    self.output(changed, item)  # ... and it is not the pattern of the verified evaluation

    def test_changed_tau_changes_identity_and_nothing_numerical(self):
        records = {}
        for tau in (0.02, 0.01):
            inputs, item = self.bundle(tau=tau)
            record = self.output(inputs, item)
            self.assertTrue(record.released, record.refusal_reasons)
            records[tau] = (inputs, record, evaluate_calibration_gate(inputs))
        (a, ra, ga), (b, rb, gb) = records[0.02], records[0.01]
        for left, right in ((a.definition.campaign_hash, b.definition.campaign_hash), (ra.identity["run_hash"],
                            rb.identity["run_hash"]), (a.pattern.record_hash, b.pattern.record_hash),
                            (ga.record_hash, gb.record_hash), (ra.record_hash, rb.record_hash),
                            (calibration_name(ra), calibration_name(rb))):
            self.assertNotEqual(left, right)
        self.assertEqual(row_sigma(a.definition), row_sigma(b.definition))  # Σ / whitening
        for name in ("analysis", "statistical", "robustness"):  # Φ, statistical_sd, LOO
            self.assertEqual(getattr(a, name).record_hash, getattr(b, name).record_hash, name)
        # Birge: the same χ², dof, s_B and adjusted SD; only its binding to the (τ-aware) pattern record differs
        birge_a, birge_b = a.birge.to_dict(), b.birge.to_dict()
        self.assertNotEqual(birge_a.pop("pattern_record_hash"), birge_b.pop("pattern_record_hash"))
        self.assertEqual(birge_a, birge_b)
        self.assertEqual(ga.precision, gb.precision)  # conservative uncertainty envelope
        self.assertEqual(ra.calibration_parameters, rb.calibration_parameters)
        self.assertEqual((ra.tau_mf, rb.tau_mf), (0.02, 0.01))

    def test_tau_is_absent_from_the_numerical_services(self):
        from services import identification_objective, identification_uncertainty, model_form_robustness
        from services import family_consistency as section_13, practical_identifiability
        for module in (identification_objective, model_form_robustness, section_13, practical_identifiability):
            self.assertNotIn("tau", Path(module.__file__).read_text(encoding="utf-8").lower(), module.__name__)
        for function in (identification_uncertainty.statistical_sd, identification_uncertainty.birge_adjustment,
                         campaign_family_consistency, row_sigma):
            self.assertNotIn("tau", inspect.getsource(function), function.__name__)


def with_pattern(inputs, evidence, tau_mf):
    """The bundle's terms judged by another pattern rule (v1.1 or another τ_mf), Birge consistently re-bound."""
    def terms(role):
        return [ResidualTerm(t.term_id, (t.term_id,), {**inputs.fit_families, **inputs.holdout_families}[t.term_id],
                             t.delta_ln_f / SIGMA, SIGMA) for t in inputs.candidate_terms if t.role == role]
    fit = terms("FIT")
    pattern = residual_pattern_test(fit, terms("HOLDOUT"), tau_mf)
    return replace(inputs, pattern=pattern, birge=birge_adjustment(evidence.system, inputs.statistical, pattern, fit))


def calibration_name(record) -> str:
    return output_module.calibration_material_name(record)


# ----------------------------------------------------------------------------- §5 SPEC §13

class FamilyConsistencyTests(unittest.TestCase):
    """Controlled two-specimen v1.2 material evidence: specimen B's experimental E is 12 % above A's, so the shared
    fit leaves A's family FAM-12 (two FIT terms, same sign) at |Δ ln f| ≈ 0.007–0.012 (|r| 2.3–3.9 at σ 0.003):
    systematic under v1.1 and τ_mf = 0.005, inside τ_mf = 0.02.  SPEC §13 compares the two specimens and FAILs."""

    campaigns: dict = {}
    results: dict = {}
    _reports: dict = {}

    @classmethod
    def setUpClass(cls):
        if cls.campaigns:
            return
        cls._directory = tempfile.TemporaryDirectory()
        tmp = Path(cls._directory.name)
        for tau, shift in ((None, 1.12), (0.02, 1.12), (0.005, 1.12), (0.02, 1.0)):
            data = synthetic_definition() if tau is None else v12_definition(MATERIAL_IDENTIFICATION, tau)
            definition = parse_campaign_definition(data)
            tag = tmp / f"{tau}-{shift}"
            items, roots = [], {}
            for label in ("A", "B"):
                item, store = synthetic_specimen(definition, label, tag, TRUTH_E * (shift if label == "B" else 1.0))
                if label == "A":  # R1 and R2 of specimen A form one family: two FIT terms, same sign
                    item = replace(item, families=dict(item.families, R1="FAM-12"))
                items.append(item)
                roots["synthetic"] = store
            campaign = CampaignRun(definition, items, "m" * 64, CampaignRunConfig(
                tag / "runs", roots, "abq2024.bat", FakeSolver(), FakeExtractor(), {}, "m" * 64))
            cls.campaigns[(tau, shift)] = campaign
            cls.results[(tau, shift)] = campaign.run()

    @classmethod
    def reports(cls) -> dict:
        cls.setUpClass()
        if not cls._reports:
            for key, campaign in cls.campaigns.items():
                cls._reports[key] = json.loads(json.dumps(build_campaign_report(
                    campaign.definition, campaign.specimens, campaign.journal.records("evaluation"),
                    cls.results[key]), default=str))
        return cls._reports

    def test_pattern_passes_only_because_of_tau_while_section_13_fails(self):
        reports = self.reports()
        v1, loose, strict = reports[(None, 1.12)], reports[(0.02, 1.12)], reports[(0.005, 1.12)]
        self.assertEqual([v["m5_verdict"]["guards"]["residual_pattern"] for v in (v1, loose, strict)],
                         ["FAIL", "PASS", "FAIL"])
        for report in (v1, loose, strict):
            self.assertEqual(report["family_consistency"]["status"], FamilyConsistencyStatus.FAIL.value)
            self.assertEqual(report["formal_output"]["status"], NO_GLOBAL_VALUE)
            self.assertEqual(report["formal_output"]["released_values"], {})
            self.assertIn("FAMILY_CONSISTENCY_FAIL", report["formal_output"]["blockers"])
            self.assertEqual(report["material_claim"], NO_MATERIAL_CLAIM)
        # With τ_mf = 0.02 SPEC §13 is the only blocker left: no global material parameter value.
        self.assertEqual(loose["m5_verdict"]["verdicts"]["E_in_plane_mpa"]["reasons"], ["FAMILY_CONSISTENCY: failed"])
        self.assertEqual(loose["m5_verdict"]["verdicts"]["E_in_plane_mpa"]["verdict"], "NOT_IDENTIFIABLE")
        self.assertEqual(loose["engineering"]["estimate"], "DIAGNOSTIC_OPTIMIZER_CANDIDATE_NOT_RELEASED")
        self.assertIsNotNone(loose["optimizer_candidate"]["values"])  # visible only as a diagnostic candidate

    def test_section_13_is_decisive(self):
        # Counterfactual control on the same journal: flipping only the §13 status to PASS releases the value, so
        # the FAIL above is what blocks it (the τ_mf-aware pattern PASS never overrides §13).
        campaign, result = self.campaigns[(0.02, 1.12)], self.results[(0.02, 1.12)]
        failing = self.reports()[(0.02, 1.12)]["family_consistency"]
        flipped = dict(failing, status=FamilyConsistencyStatus.PASS.value)
        with mock.patch.object(campaign_module, "campaign_family_consistency", return_value=flipped):
            report = build_campaign_report(campaign.definition, campaign.specimens,
                                           campaign.journal.records("evaluation"), result)
        self.assertIn(report["m5_verdict"]["verdicts"]["E_in_plane_mpa"]["verdict"], ("IDENTIFIED", "WIDE"))
        self.assertEqual(report["formal_output"]["status"], "VALUES_RELEASED")
        self.assertNotIn("FAMILY_CONSISTENCY_FAIL", report["formal_output"]["blockers"])

    def test_tau_never_changes_section_13(self):
        reports = self.reports()
        documents = [reports[(tau, 1.12)]["family_consistency"] for tau in (None, 0.02, 0.005)]
        for document in documents[1:]:
            self.assertEqual(document, documents[0])  # Δχ², dof, p-values, bootstrap, status: identical
        self.assertGreater(documents[0]["delta_chi2"], 50.0)
        self.assertLess(documents[0]["p_chi2"], 1e-10)
        self.assertLess(documents[0]["bootstrap_p"], 1e-3)
        self.assertNotIn("tau", json.dumps(documents[0]))
        control = reports[(0.02, 1.0)]
        self.assertEqual(control["family_consistency"]["status"], "PASS")  # consistent specimens release a value
        self.assertEqual(control["formal_output"]["status"], "VALUES_RELEASED")

    def test_not_evaluable_family_consistency_releases_nothing(self):
        # A genuine NOT_EVALUABLE_RANK_DEFICIENT §13 record (specimen B's separate fit is rank deficient), placed in
        # the otherwise releasing control campaign: no PASS is invented and no global value is released.
        jacobian = np.array([[160.0, 1.0], [120.0, 50.0], [120.0, 50.0]])
        terms = ["A:R1", "A:R2", "B:R1"]
        document = family_consistency(terms, {t: t[0] for t in terms}, [1.0, -2.0, 3.0], jacobian, ["E", "G"],
                                      {"E": 50000.0, "G": 4500.0}, chi2_conditions={c: True for c in CHI2_CONDITIONS},
                                      sigma={"setup": {"sd_ln": 0.003}}, bootstrap_samples=2000,
                                      bootstrap_seed=11).to_dict()
        self.assertEqual(document["status"], FamilyConsistencyStatus.NOT_EVALUABLE_RANK_DEFICIENT.value)
        campaign, result = self.campaigns[(0.02, 1.0)], self.results[(0.02, 1.0)]
        with mock.patch.object(campaign_module, "campaign_family_consistency", return_value=document):
            report = build_campaign_report(campaign.definition, campaign.specimens,
                                           campaign.journal.records("evaluation"), result)
        self.assertEqual(report["m5_verdict"]["guards"]["family_consistency"], "NOT_AVAILABLE")
        self.assertEqual(report["formal_output"]["status"], NO_GLOBAL_VALUE)
        self.assertEqual(report["formal_output"]["released_values"], {})
        self.assertNotEqual(report["m5_verdict"]["verdicts"]["E_in_plane_mpa"]["verdict"], "IDENTIFIED")


# ----------------------------------------------------------------------------- §6 calibration gate negative matrix

class CalibrationNegativeMatrixTests(_Bundles):
    """Every scientific refusal of V12-I3, end to end: gate REFUSED → REFUSED output → no value, no fragment."""

    def cases(self):
        one_family = {r: "F1" for r in FOUR_FAMILIES} | {"H1": "T"}
        overlap = dict(FOUR_FAMILIES, H1="F1")
        cases = {}

        def case(name, code, inputs, item, evidence=None):  # the evidence of the bundle, resolved now
            cases[name] = (code, inputs, item, evidence or self.evidence(inputs, item))

        inputs, item = self.bundle()
        failing = GuardEvidence("guard", EvidenceState.FAIL, "x", "failed")
        case("fewer than k+1 FIT families", "INSUFFICIENT_FIT_FAMILIES", *self.bundle(one_family))
        case("HOLDOUT / FIT family overlap", "HOLDOUT_FAMILY_OVERLAPS_FIT", *self.bundle(overlap))
        case("rank deficiency", "RANK_DEFICIENT",  # a rank-deficient M5 system (no M5.7 robustness exists)
             *self.with_system(inputs, item, {r: (0.0,) for r in FIT_ROWS}))
        case("incomplete LOO", "LOO_INCOMPLETE",  # without F1 the remaining family F2 observes nothing
             *self.bundle(sensitivities={"R1": (0.5,), "R2": (0.45,), "R3": (0.0,), "R4": (0.0,)}))
        case("insufficient baseline MAC", "BASELINE_PAIR_MAC", *self.bundle(macs={"R2": 0.7999}))
        case("branch / pair loss", "BRANCH_OR_PAIRING_LOSS", replace(inputs, branch_pairing=failing), item)
        case("active bound", "ACTIVE_PARAMETER_BOUND", *self.bundle(p_hat={"E_in_plane_mpa": 26000.0}))
        case("limited registration", "REGISTRATION_LIMITED", replace(inputs, registration=failing), item)
        case("peak-derived input", "PEAK_DERIVED_INPUT", replace(inputs, peak_derived_input=failing), item)
        case("systematic family", "SYSTEMATIC_PATTERN", *self.bundle(fit=[8.0, 9.0, 0.3, -0.2]))
        case("holdout failure", "HOLDOUT_FAILURE", *self.bundle(holdout=(("H1", "T", 7.0),)))
        case("missing evidence", "MISSING_EVIDENCE",
             replace(inputs, tracking_macs={k: v for k, v in inputs.tracking_macs.items() if k != "R1"}), item)
        case("missing registration evidence", "MISSING_EVIDENCE",
             replace(inputs, registration=GuardEvidence("registration", EvidenceState.NOT_AVAILABLE, "x")), item)
        case("incorrect row membership", "ROW_SET_MISMATCH",
             replace(inputs, candidate_rows=[r for r in inputs.candidate_rows if r.row_id != "R2"]), item)
        case("max degradation", "MAX_DEGRADED",  # the frozen baseline itself (SPEC v1.1 §6 S3)
             *self.bundle(baseline={r: 0.0017 for r in ("R1", "R2", "R3", "R4", "H1")}))
        case("RMS degradation", "RMS_DEGRADED",
             *self.bundle(baseline={"R1": 0.0, "R2": 0.0, "R3": 0.0, "R4": 0.0, "H1": 0.0018}))
        case("physical row above 8 %", "ROW_RELATIVE_ERROR_ABOVE_CEILING",
             *self.bundle(fit=[math.log1p(0.0800001) / SIGMA, -25.0, 0.3, -0.2],
                          baseline={r: 0.1 for r in ("R1", "R2", "R3", "R4", "H1")}))
        case("Birge unavailable", "BIRGE_UNAVAILABLE",  # blocked by the systematic pattern (SPEC §9)
             *self.bundle(fit=[8.0, 9.0, 0.3, -0.2]))
        case("incomplete robustness", "LOO_INCOMPLETE", replace(inputs, robustness=None), item)
        case("conservative uncertainty > 0.08", "CONSERVATIVE_ABOVE_CEILING",  # weakly observed E
             *self.bundle(sensitivities={r: (0.01,) for r in FIT_ROWS}))
        case("incomplete reporting", "REPORTING_INCOMPLETE",
             replace(inputs, reporting=replace(inputs.reporting, uncertainty_basis=False)), item)
        return cases

    def test_the_reference_bundle_releases(self):
        inputs, item = self.bundle()
        record = self.output(inputs, item)
        self.assertIs(record.status, CalibrationOutputStatus.RELEASED, record.refusal_reasons)
        self.assertEqual(record.calibration_parameters["E_in_plane_mpa"]["value"], inputs.p_hat["E_in_plane_mpa"])

    def test_every_scientific_refusal_stays_refused(self):
        cases = self.cases()
        self.assertEqual(len(cases), 21)  # TRACKING_MAC: see test_tracking_mac_below_090_is_never_journalled
        for name, (code, inputs, item, evidence) in cases.items():
            with self.subTest(case=name):
                gate = evaluate_calibration_gate(inputs)
                self.assertIs(gate.status, CalibrationGateStatus.REFUSED)
                self.assertIn(code, gate.refusal_codes)
                record = self.output(inputs, item, evidence)
                self.assert_refused_output(record, code)
                self.assertEqual(record.gate_record_hash, gate.record_hash)
                self.assertEqual(record.diagnostic_optimizer_candidate["parameters"]["E_in_plane_mpa"]["value"],
                                 inputs.p_hat["E_in_plane_mpa"])  # the judged candidate, diagnostic only

    def test_tracking_mac_below_090_is_never_journalled(self):
        # The I3 gate refuses TRACKING_MAC (test_v12_i3 test_09); a verified evaluation cannot carry it, because the
        # M4 branch tracker itself refuses MAC < 0.90 (no evaluation is journalled), and a forged one is no evidence.
        inputs, item = self.bundle()
        forged = replace(inputs, tracking_macs=dict(inputs.tracking_macs, H1=0.8999))
        self.assertIn("TRACKING_MAC", evaluate_calibration_gate(forged).refusal_codes)
        with self.assertRaisesRegex(PracticalIdentifiabilityInputError, "tracking MAC of H1"):
            self.output(forged, item)

    def test_wrong_question_and_specimen_count_produce_no_record(self):
        inputs, item = self.bundle()
        material = parse_campaign_definition(v12_definition(MATERIAL_IDENTIFICATION))
        two = replace(inputs.definition, specimens=inputs.definition.specimens * 2)
        for name, definition, code in (("question", material, "WRONG_SCHEMA_OR_QUESTION"),
                                       ("specimen count", two, "SPECIMEN_COUNT")):
            with self.subTest(case=name):
                changed = replace(inputs, definition=definition)
                self.assertIn(code, evaluate_calibration_gate(changed).refusal_codes)
                with self.assertRaises(PracticalIdentifiabilityInputError):
                    build_calibration_output(changed, item, campaign_run_identity(inputs.definition, [item],
                                                                                  "m" * 64, {}), NONE_EXCLUDED,
                                             self.evidence(inputs, item))

    def test_no_manual_override(self):
        parameters = list(inspect.signature(build_calibration_output).parameters)
        self.assertEqual(parameters, ["inputs", "specimen", "run_identity", "excluded", "evaluation",
                                      "expected_gate_record_hash"])
        record = self.output(*self.bundle(holdout=(("H1", "T", 7.0),)))
        with self.assertRaises(FrozenInstanceError):
            record.status = CalibrationOutputStatus.RELEASED
        inputs, _ = self.bundle()
        with self.assertRaises(FrozenInstanceError):
            inputs.p_hat = {}
        self.assertEqual(list(inspect.signature(evaluate_calibration_gate).parameters), ["inputs"])
        from dataclasses import fields
        from services.specimen_calibration_gate import CalibrationGateInputs
        names = " ".join(f.name for f in fields(CalibrationGateInputs)) + " " + " ".join(parameters)
        for word in ("override", "force", "manual", "accept", "waive", "status"):
            self.assertNotIn(word, names)


# ----------------------------------------------------------------------------- §7 evidence anti-mixing

class AntiMixingTests(_Bundles):
    def setUp(self):
        super().setUp()
        self.a, self.item = self.bundle()  # candidate A: p̂ = 50000 MPa, evaluated by the specimen pipeline
        self.b, self.evidence_b = self.candidate(self.item, {"E_in_plane_mpa": 51000.0})  # candidate B, same run

    def never_passes(self, inputs, item=None, **kwargs):
        try:
            record = self.output(inputs, item or self.item, **kwargs)
        except PracticalIdentifiabilityInputError:
            return
        self.assertIs(record.status, CalibrationOutputStatus.REFUSED, "an inconsistent bundle became RELEASED")

    def test_candidates_cannot_be_mixed(self):
        self.assertTrue(self.output(self.a, self.item).released)
        self.assertTrue(self.output(self.b, self.item, self.evidence_b).released)
        mixes = {
            "A p̂ with B robustness": replace(self.a, robustness=self.b.robustness),
            "A pattern with B residuals": replace(self.a, candidate_terms=self.b.candidate_terms,
                                                  candidate_rows=self.b.candidate_rows),
            "B pattern with A residuals": replace(self.a, pattern=self.b.pattern),
            "A Birge with B pattern": replace(self.a, pattern=self.b.pattern, statistical=self.b.statistical),
            "B p̂ + robustness with A residuals (F1)": replace(self.a, p_hat=self.b.p_hat, robustness=self.b.robustness),
        }
        for name, inputs in mixes.items():
            for evidence in (self.evidence(self.a, self.item), self.evidence_b):
                with self.subTest(mix=name, evidence=evidence.evaluation_hash[:8]), \
                        self.assertRaises(PracticalIdentifiabilityInputError):
                    self.output(inputs, self.item, evidence)

    def test_baseline_of_another_row_set(self):
        other, _, _ = self.simple()  # rows R1, R2, R3 of another evidence bundle
        mixed = replace(self.a, baseline_rows=other.baseline_rows)
        self.assertIn("ROW_SET_MISMATCH", evaluate_calibration_gate(mixed).refusal_codes)
        self.never_passes(mixed)
        with self.assertRaisesRegex(PracticalIdentifiabilityInputError, "baseline pair MAC"):
            self.output(replace(self.a, baseline_pair_macs=dict(self.a.baseline_pair_macs, R1=0.95)), self.item)

    def test_gate_and_values_of_different_candidates(self):
        gate_a = evaluate_calibration_gate(self.a).record_hash
        with self.assertRaisesRegex(PracticalIdentifiabilityInputError, "not the gate"):
            self.output(self.b, self.item, self.evidence_b, expected_gate_record_hash=gate_a)
        record = self.output(self.a, self.item, expected_gate_record_hash=gate_a)
        self.assertEqual(record.calibration_parameters["E_in_plane_mpa"]["value"], 50000.0)  # A's judged p̂ only
        self.assertEqual(record.identity["evidence_binding"]["p_hat_hash"],
                         canonical_hash({"E_in_plane_mpa": 50000.0}))
        self.assertEqual(record.identity["evidence_binding"]["candidate_evaluation"]["candidate_parameters"],
                         {"E_in_plane_mpa": 50000.0})

    def test_run_campaign_specimen_registration_and_inp(self):
        other = parse_campaign_definition(calibration_definition(0.01))  # another campaign (τ_mf identity)
        run_other = campaign_run_identity(other, [self.item], "m" * 64, {})
        with self.assertRaisesRegex(PracticalIdentifiabilityInputError, "another campaign"):
            build_calibration_output(self.a, self.item, run_other, NONE_EXCLUDED, self.evidence(self.a, self.item))
        material = parse_campaign_definition(v12_definition(MATERIAL_IDENTIFICATION))
        item_b, store_b = synthetic_specimen(material, "B", self.tmp / "other-specimen")
        with self.assertRaises(PracticalIdentifiabilityInputError):  # A's rows with B's forward manifest
            self.output(self.a, replace(self.item, model=item_b.model))
        identity = replace(self.item.frozen.identity, registration_hash="9" * 64)
        with self.assertRaisesRegex(PracticalIdentifiabilityInputError, "registration"):
            self.output(self.a, replace(self.item, frozen=replace(self.item.frozen, identity=identity)))
        record = self.output(self.a, self.item)
        with self.assertRaisesRegex(CalibrationFragmentRefusal, "SHA-256"):  # B's pinned INP for A's record
            render_calibration_inp_fragment(record, governed_engineering_constants(record),
                                            (store_b / "models" / "SYB.inp").read_bytes())
        render_calibration_inp_fragment(record, governed_engineering_constants(record), self.source_inp)


class CandidateEvaluationBindingTests(_Bundles):
    """F1 closed: p̂, the governed residual evidence, the M5 records and the FE identity must be the verified evaluation
    of ONE candidate in the specimen's pipeline journal (``candidate_evaluation_evidence``)."""

    def setUp(self):
        super().setUp()
        self.a, self.item = self.bundle()
        self.evidence_a = self.evidence(self.a, self.item)
        self.b, self.evidence_b = self.candidate(self.item, {"E_in_plane_mpa": 51000.0})

    def unverified(self, inputs, evidence=None, text=""):
        with self.assertRaisesRegex(PracticalIdentifiabilityInputError, text):
            self.output(inputs, self.item, evidence or self.evidence_a)

    def test_finding_1_p_hat_and_robustness_are_bound_to_the_judged_residuals(self):
        mixed = replace(self.a, p_hat=self.b.p_hat, robustness=self.b.robustness)  # was RELEASED at 51000 MPa
        self.assertIs(evaluate_calibration_gate(mixed).status, CalibrationGateStatus.PASS)  # the pure gate cannot see it
        self.unverified(mixed, self.evidence_a, "not p̂")
        self.unverified(mixed, self.evidence_b, "candidate terms")

    def test_p_hat_and_residuals_varied_independently(self):
        # only p̂ (with a consistently recomputed robustness at that p̂ from A's residuals)
        fit = [ResidualTerm(t.term_id, (t.term_id,), self.a.fit_families[t.term_id], t.delta_ln_f / SIGMA, SIGMA)
               for t in self.a.candidate_terms if t.role == "FIT"]
        robustness = linearised_model_form_robustness(self.evidence_a.system, fit, self.b.p_hat)
        self.unverified(replace(self.a, p_hat=self.b.p_hat, robustness=robustness), text="not p̂")
        # only the residuals (B's terms, rows, pattern, Birge and tracking) with A's p̂ and robustness
        residuals = replace(self.a, candidate_terms=self.b.candidate_terms, candidate_rows=self.b.candidate_rows,
                            pattern=self.b.pattern, birge=self.b.birge, tracking_macs=self.b.tracking_macs)
        self.unverified(residuals, text="candidate terms")
        # only robustness: computed at A's p̂ but from B's residuals (the exact F1 gap: same p_hat_hash)
        fit_b = [ResidualTerm(t.term_id, (t.term_id,), self.a.fit_families[t.term_id], t.delta_ln_f / SIGMA, SIGMA)
                 for t in self.b.candidate_terms if t.role == "FIT"]
        foreign = linearised_model_form_robustness(self.evidence_a.system, fit_b, self.a.p_hat)
        self.assertEqual(foreign.p_hat_hash, self.a.robustness.p_hat_hash)
        self.assertIs(evaluate_calibration_gate(replace(self.a, robustness=foreign)).status, CalibrationGateStatus.PASS)
        self.unverified(replace(self.a, robustness=foreign), text="model_form_robustness")

    def test_holdout_rows_are_bound(self):
        # a HOLDOUT term and row of another evaluation (FIT terms, p̂ and robustness unchanged)
        held_b = {t.term_id: t for t in self.b.candidate_terms if t.role == "HOLDOUT"}
        terms = [held_b.get(t.term_id, t) if t.role == "HOLDOUT" else t for t in self.a.candidate_terms]
        rows = [next(r for r in self.b.candidate_rows if r.row_id == "H1") if r.row_id == "H1" else r
                for r in self.a.candidate_rows]
        changed = with_pattern(replace(self.a, candidate_terms=terms, candidate_rows=rows), self.evidence_a,
                               self.a.definition.tau_mf)
        self.unverified(changed, text="candidate terms")
        row_only = [GovernedRow(r.row_id, r.role, r.delta_ln_f * 1.01) if r.row_id == "H1" else r
                    for r in self.a.candidate_rows]
        self.unverified(replace(self.a, candidate_rows=row_only), text="H1")
        self.unverified(replace(self.a, tracking_macs=dict(self.a.tracking_macs, H1=0.95)), text="tracking MAC of H1")

    def test_forged_m5_records_are_not_evidence(self):
        forged = {
            "analysis": replace(self.a, analysis=replace(self.a.analysis, status=RankStatus.RANK_DEFICIENT)),
            "birge (smaller sd)": replace(self.a, birge=replace(self.a.birge, birge_adjusted_sd_ln={
                "E_in_plane_mpa": 0.001})),
            "robustness": replace(self.a, robustness=replace(self.a.robustness, supports_green=False)),
        }
        for name, inputs in forged.items():
            with self.subTest(record=name):
                self.unverified(inputs, text="not computed from the verified")

    def test_evidence_components_are_verified(self):
        evidence = self.evidence_a
        record = self.output(self.a, self.item)
        verified = record.identity["evidence_binding"]["candidate_evaluation"]
        self.assertEqual(verified["verification"], "VERIFIED_AGAINST_SPECIMEN_PIPELINE_JOURNAL")
        self.assertEqual((verified["solver_profile_id"], verified["fe_source"]),  # synthetic evidence stays visible
                         (self.item.profile.profile_id, "new-solve"))
        self.assertTrue(verified["solver_profile_id"].endswith("/fake"))
        journal = evidence.pipeline_journal
        entries = [dict(e) for e in journal["entries"]]
        tampered = dict(entries[-1], record=dict(entries[-1]["record"], objective=0.0))
        cases = {
            "journal entry tampered": (replace(evidence, pipeline_journal=dict(
                journal, entries=entries[:-1] + [tampered])), "hash chain"),
            "evaluation of another candidate": (replace(evidence, pipeline_journal=self.evidence_b.pipeline_journal,
                                                        evaluation_hash=self.evidence_b.evaluation_hash), "not p̂"),
            "unknown evaluation": (replace(evidence, evaluation_hash="0" * 64), "0 journalled evaluations"),
            "candidate pack of another evaluation": (replace(evidence, candidate_pack=self.evidence_b.candidate_pack),
                                                     "candidate FE pack"),
            "baseline pack swapped": (replace(evidence, baseline_pack=evidence.candidate_pack), "baseline FE pack"),
            "another source INP": (replace(evidence, source_inp=evidence.source_inp + b"\n"), "re-rendered"),
            "another M5 system": (replace(evidence, system=system({r: (0.3,) for r in FIT_ROWS}, (E,), sd=SIGMA)),
                                  "another M5 system"),
            "no evidence": (None, "required"),
        }
        for name, (changed, text) in cases.items():
            with self.subTest(evidence=name), self.assertRaisesRegex(PracticalIdentifiabilityInputError, text):
                run = campaign_run_identity(self.a.definition, [self.item], "m" * 64, {})
                build_calibration_output(self.a, self.item, run, NONE_EXCLUDED, changed)

    def test_a_self_consistent_fabricated_journal_is_not_evidence(self):
        # Re-hashing an edited evaluation (evaluation hash and hash chain recomputed) is not proof: the job is
        # re-rendered from the pinned INP and the residuals re-derived from the content-addressed FE packs.
        def fabricated(change):
            document = self.evidence_a.pipeline_journal
            entries, previous, target = [], document["run_hash"], None
            for entry in document["entries"]:
                record = dict(entry["record"])
                if entry["kind"] == "evaluation" and record["evaluation_hash"] == self.evidence_a.evaluation_hash:
                    record = change(record)
                    record["evaluation_hash"] = target = canonical_hash({k: v for k, v in record.items()
                                                                         if k != "evaluation_hash"})
                body = {"sequence": entry["sequence"], "kind": entry["kind"], "record": record,
                        "previous_hash": previous}
                entries.append(dict(body, entry_hash=canonical_hash(body)))
                previous = entries[-1]["entry_hash"]
            return replace(self.evidence_a, pipeline_journal=dict(document, entries=entries), evaluation_hash=target)

        cases = {
            "job hash": (lambda r: dict(r, job_hash="0" * 64), "not the forward job"),
            "residuals": (lambda r: dict(r, residuals=[v * 1.5 for v in r["residuals"]]), "not those of the FE packs"),
            "holdout residuals": (lambda r: dict(r, holdout_residuals={k: -v for k, v in r["holdout_residuals"].items()}),
                                  "not those of the FE packs"),
            "evaluated parameters": (lambda r: dict(r, parameters=dict(r["parameters"], E_in_plane_mpa=51000.0)),
                                     "not p̂"),
        }
        for name, (change, text) in cases.items():
            with self.subTest(fabricated=name):
                self.unverified(self.a, fabricated(change), text)
        self.assertTrue(self.output(self.a, self.item, fabricated(lambda r: r)).released)  # control: unchanged

    def test_evidence_of_another_run_or_specimen(self):
        other_inputs, other_item = self.bundle(fit=[0.45, -0.35, 0.25, -0.15])  # another specimen's frozen set
        self.unverified(self.a, self.evidence(other_inputs, other_item), "another frozen observation set")
        regrouped_inputs, regrouped_item = self.bundle(families=dict(FOUR_FAMILIES, R2="F2", R3="F1"))
        self.assertEqual(regrouped_item.frozen.observation_hash, self.item.frozen.observation_hash)  # same frozen set
        self.unverified(self.a, self.evidence(regrouped_inputs, regrouped_item), "another calibration run")

    def test_real_pipeline_journals_and_packs_fit_the_evidence_contract(self):
        """READ-ONLY (store-gated): the archived M7 specimen journals verify and every journalled FE pack's content
        hash is reproduced by the contract's recomputation (no calibration, nothing written)."""
        roots = fixture_roots_from_environment()
        checked = 0
        for store in ("m7-run-a", "m7-run-b"):
            if store not in roots:
                continue
            for path in sorted(Path(roots[store]).glob("specimens/*/*/*/journal.json")):
                document = _load(path)
                verify_journal_chain(document["run_hash"], document["entries"])
                self.assertEqual(canonical_hash(document["run_identity"]), document["run_hash"])
                for entry in document["entries"]:
                    if entry["kind"] == "extraction":
                        record = entry["record"]
                        pack = load_run_pack(path.parent / "packs", record["job_name"], record["pack_content_sha256"])
                        self.assertEqual(evidence_module._pack_content_sha256(pack), record["pack_content_sha256"])
                        checked += 1
        if not checked:
            self.skipTest("data stores m7-run-a / m7-run-b not configured")
        self.assertEqual(checked, 8)

    def test_clusters_are_refused_as_unverified(self):
        inputs, item, run = self.cluster()
        self.assertTrue(evaluate_calibration_gate(inputs).passed)
        with self.assertRaisesRegex(PracticalIdentifiabilityInputError, "CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE"):
            build_calibration_output(inputs, item, run, NONE_EXCLUDED, self.evidence(inputs, item))


class FrozenBaselineBindingTests(_Bundles):
    """F2 closed: the SPEC v1.2 §7 baseline is the frozen FE reference state at p0 (SPEC v1.1 §6 S3), per governed
    physical row Δ ln f = ln(f_FE / f_EXP) of the frozen observation set; anything else is an input inconsistency."""

    def raises(self, inputs, item, text="baseline"):
        with self.assertRaisesRegex(PracticalIdentifiabilityInputError, text):
            self.output(inputs, item)

    def test_valid_frozen_baseline_passes_and_is_reported(self):
        inputs, item = self.bundle()
        record = self.output(inputs, item)
        self.assertTrue(record.released, record.refusal_reasons)
        for row in record.governed_rows:  # the table shows exactly what the frozen frequencies imply
            frozen = item.frozen.row(row["row_id"])
            self.assertEqual(row["baseline_delta_ln_f"], math.log(frozen.fe_hz / frozen.experimental_hz))
            self.assertEqual(row["baseline_delta_ln_f"],
                             math.log(row["baseline_fe_hz"] / row["experimental_hz"]))
        self.assertAlmostEqual(record.non_degradation["baseline_max_abs_delta_ln_f"], math.log(BASELINE_RATIO),
                               places=12)  # §7 is judged against the frozen baseline

    def test_finding_2_baseline_delta_ln_f_is_bound_to_the_frozen_baseline_pairing(self):
        inputs, item = self.bundle()
        rows = list(inputs.baseline_rows)
        for name, changed in (("incorrect Δ ln f", 1e-6), ("sign flipped", None)):
            with self.subTest(case=name):
                altered = [GovernedRow(r.row_id, r.role, (-r.delta_ln_f if changed is None else r.delta_ln_f + changed)
                                       if r.row_id == "R2" else r.delta_ln_f) for r in rows]
                self.raises(replace(inputs, baseline_rows=altered), item)
        holdout = [GovernedRow(r.row_id, r.role, r.delta_ln_f * 0.5 if r.role == "HOLDOUT" else r.delta_ln_f)
                   for r in rows]
        self.raises(replace(inputs, baseline_rows=holdout), item)  # a HOLDOUT row too
        role = [GovernedRow(r.row_id, "FIT", r.delta_ln_f) for r in rows]
        self.raises(replace(inputs, baseline_rows=role), item)  # exact FIT / HOLDOUT role
        self.raises(replace(inputs, baseline_rows=rows[:-1]), item)
        self.raises(replace(inputs, baseline_rows=rows + [rows[0]]), item, "twice")
        with self.assertRaisesRegex(PracticalIdentifiabilityInputError, "finite"):
            GovernedRow("R1", "FIT", math.nan)  # a non-finite baseline cannot even be stated

    def test_wrong_frozen_frequencies_are_inconsistent(self):
        inputs, item = self.bundle()
        for field in ("fe_hz", "experimental_hz"):
            with self.subTest(frequency=field):  # the supplied baseline no longer matches the frozen pairing
                frozen_rows = tuple(replace(r, **{field: getattr(r, field) * 1.001}) if r.row_id == "R1" else r
                                    for r in item.frozen.rows)
                self.raises(inputs, replace(item, frozen=replace(item.frozen, rows=frozen_rows)))
        for bad in (0.0, -1.0):  # non-finite values cannot enter an observation identity at all
            with self.subTest(fe_hz=bad):
                frozen_rows = tuple(replace(r, fe_hz=bad) if r.row_id == "R1" else r for r in item.frozen.rows)
                self.raises(inputs, replace(item, frozen=replace(item.frozen, rows=frozen_rows)), "finite and positive")

    def test_baseline_of_another_specimen_or_frozen_set(self):
        inputs, item = self.bundle()
        other_inputs, other_item, _ = self.simple()  # another specimen's frozen set (rows R1, R2, R3)
        self.raises(replace(inputs, baseline_rows=governed_baseline_rows(other_item)), item)
        shifted_inputs, shifted_item = frozen_baseline(inputs, item, {"R1": 0.031})  # another frozen observation set
        self.assertNotEqual(shifted_item.frozen.observation_hash, item.frozen.observation_hash)
        self.raises(replace(inputs, baseline_rows=shifted_inputs.baseline_rows), item)  # its baseline, our frozen set
        with self.assertRaisesRegex(PracticalIdentifiabilityInputError, "observation_hash"):  # its frozen set, our run
            build_calibration_output(shifted_inputs, shifted_item,
                                     campaign_run_identity(inputs.definition, [item], "m" * 64, {}), NONE_EXCLUDED,
                                     self.evidence(inputs, item))
        own_inputs, own_item = self.bundle(baseline={"R1": 0.031, "R2": 0.03, "R3": 0.03, "R4": 0.03, "H1": 0.03})
        self.assertTrue(self.output(own_inputs, own_item).released)  # a genuine bundle on that frozen baseline

    def test_cluster_member_rows_are_bound_separately(self):
        inputs, item, _ = self.cluster()
        with self.assertRaisesRegex(PracticalIdentifiabilityInputError, "CLUSTER_MEMBER"):  # the baseline binds,
            self.output(inputs, item)  # then the cluster is refused as unverified (F1)
        members = [GovernedRow(r.row_id, r.role, r.delta_ln_f + (0.001 if r.row_id == "R3" else
                                                                  -0.001 if r.row_id == "R4" else 0.0))
                   for r in inputs.baseline_rows]  # same cluster mean, different member rows
        self.raises(replace(inputs, baseline_rows=members), item)


# ----------------------------------------------------------------------------- §8 RELEASED / REFUSED output

class OutputContractTests(_Bundles):
    def test_released_values_are_exactly_the_judged_candidate(self):
        for value in (50000.0, 50000.000000001, 61234.5678):
            with self.subTest(p_hat=value):
                inputs, item = self.bundle(p_hat={"E_in_plane_mpa": value})
                record = self.output(inputs, item)
                self.assertTrue(record.released, record.refusal_reasons)
                data = record.to_dict()
                self.assertEqual((data["output_class"], data["labels"]),
                                 (SPECIMEN_ENGINEERING_CALIBRATION, list(LABELS)))
                self.assertEqual(LABELS, ("SPECIMEN_ENGINEERING_CALIBRATION", "NOT_A_MATERIAL_PROPERTY",
                                          "NOT_TRANSFERABLE_WITHOUT_VALIDATION"))
                item_value = data["calibration_parameters"]["E_in_plane_mpa"]
                self.assertEqual((item_value["value"], item_value["role"]), (value, "MODEL_CALIBRATION_PARAMETER"))
                self.assertNotIn("diagnostic_optimizer_candidate", data)

    def test_refused_records_release_nothing_and_render_nothing(self):
        inputs, item = self.bundle(holdout=(("H1", "T", 7.0),))
        record = self.output(inputs, item)
        self.assert_refused_output(record, "HOLDOUT_FAILURE")
        self.assertEqual(CANDIDATE_LABELS, ("DIAGNOSTIC_OPTIMIZER_CANDIDATE", "NOT_A_RELEASE_VALUE"))
        text = json.dumps(record.to_dict())
        for label in ("SPECIMEN_ENGINEERING_CALIBRATION\", \"NOT_A_MATERIAL", "MODEL_CALIBRATION_PARAMETER"):
            self.assertNotIn(label, text)

    def test_no_ordinary_material_writer(self):
        tree = ast.parse(Path(output_module.__file__).read_text(encoding="utf-8"))
        imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                    and node.module == "forward_builder" for alias in node.names}
        self.assertEqual(imported, {"ForwardBuildError", "inp_keyword", "locate_engineering_constants",
                                    "material_block_bounds", "rewrite_engineering_constants", "split_inp_lines"})
        source = Path(output_module.__file__).read_text(encoding="utf-8")
        for name in ("prepare_forward_job", "render_forward_input", "join_inp_lines", "write_text", "write_bytes",
                     "open(", "mkdir", "os.replace"):
            self.assertNotIn(name, source)
        # the F1 verifier re-renders the candidate job in memory only (pure render, never a job or a file)
        from services import candidate_evaluation_evidence as evidence_module
        tree = ast.parse(Path(evidence_module.__file__).read_text(encoding="utf-8"))
        imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                    and node.module == "forward_builder" for alias in node.names}
        self.assertEqual(imported, {"ForwardBuildError", "forward_job_provenance", "render_forward_input"})
        source = Path(evidence_module.__file__).read_text(encoding="utf-8")
        for name in ("prepare_forward_job", "write_text", "write_bytes", "open(", "mkdir", "os.replace", "subprocess",
                     "run_bounded_lm", "IdentificationPipeline"):
            self.assertNotIn(name, source)


# ----------------------------------------------------------------------------- §9 clusters

class ClusterSafetyTests(_Bundles):
    """A confirmed cluster is ONE governed term; its member rows are checked one by one (averaging hides nothing)."""

    def cluster_case(self, baseline=None, **changes):
        inputs, item, _ = self.cluster(**changes)
        self.source_inp = (self.tmp / "cluster" / "store" / "models" / "SYA.inp").read_bytes()
        return frozen_baseline(inputs, item, baseline) if baseline else (inputs, item)

    def test_one_term_two_rows(self):
        inputs, item = self.cluster_case(cluster_offsets={CLUSTER_ID: 0.004})
        gate = evaluate_calibration_gate(inputs)
        self.assertTrue(gate.passed, gate.refusal_reasons)
        self.assertEqual(sum(1 for t in inputs.pattern.terms if t["term_id"] == CLUSTER_ID), 1)
        self.assertEqual(gate.observability["fit_family_keys"], ["F1", "F2"])
        self.assertEqual(gate.non_degradation["rows"], 5)  # R3 and R4 judged as two physical rows
        rows = {r.row_id: r.delta_ln_f for r in inputs.candidate_rows}
        term = next(t.delta_ln_f for t in inputs.candidate_terms if t.term_id == CLUSTER_ID)
        self.assertNotAlmostEqual(rows["R3"], rows["R4"], places=6)
        self.assertAlmostEqual((rows["R3"] + rows["R4"]) / 2, term, places=15)
        # V12-I5 (F1): the M4 evaluation has no per-member evidence for a cluster, so nothing is released
        with self.assertRaisesRegex(PracticalIdentifiabilityInputError, "CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE"):
            self.output(inputs, item)

    def test_a_bad_member_row_is_never_averaged_away(self):
        base, item = self.cluster_case()
        bad_mac = (replace(base, baseline_pair_macs=dict(base.baseline_pair_macs, R4=0.79)),
                   _frozen_mac(item, "R4", 0.79))  # member mean (0.98 + 0.79) / 2 = 0.885 ≥ 0.80
        self.assertGreaterEqual((0.98 + 0.79) / 2, 0.80)
        bad_tracking = (replace(base, tracking_macs=dict(base.tracking_macs, R3=0.89)), item)  # mean 0.93 ≥ 0.90
        cases = {
            "member baseline MAC": (*bad_mac, "BASELINE_PAIR_MAC"),
            "member tracking MAC": (*bad_tracking, "TRACKING_MAC"),
            "member max degradation": (*self.cluster_case(cluster_offsets={CLUSTER_ID: 0.05},
                                                          baseline={r: 0.03 for r in ("R1", "R2", "R3", "R4", "H1")}),
                                       "MAX_DEGRADED"),
            "member RMS degradation": (*self.cluster_case(cluster_offsets={CLUSTER_ID: 0.045},
                                                          baseline={"R1": 0.06, "R2": 0.0, "R3": 0.0, "R4": 0.0,
                                                                    "H1": 0.0}), "RMS_DEGRADED"),
            "member above 8 %": (*self.cluster_case(cluster_offsets={CLUSTER_ID: 0.0775},
                                                    baseline={r: 0.1 for r in ("R1", "R2", "R3", "R4", "H1")}),
                                 "ROW_RELATIVE_ERROR_ABOVE_CEILING"),
        }
        for name, (inputs, case_item, code) in cases.items():
            with self.subTest(case=name):
                term = next(t for t in inputs.candidate_terms if t.term_id == CLUSTER_ID)
                self.assertLess(abs(math.expm1(term.delta_ln_f)), 0.08)  # the cluster term itself is fine
                gate = evaluate_calibration_gate(inputs)
                self.assertIs(gate.status, CalibrationGateStatus.REFUSED)
                self.assertIn(code, gate.refusal_codes)
                with self.assertRaises(PracticalIdentifiabilityInputError):  # and never a released record
                    self.output(inputs, case_item)


# ----------------------------------------------------------------------------- §10–11 calibration material fragment

class MaterialFragmentSafetyTests(_Bundles):
    def setUp(self):
        super().setUp()
        self.bundle()  # the pinned synthetic source INP

    def released(self):
        inputs, item = self.bundle()
        record = self.output(inputs, item)
        self.assertTrue(record.released, record.refusal_reasons)
        return record

    def render(self, record, text):
        raw = text.encode("latin-1")
        pointed = replace(record, identity=dict(record.identity, inp_sha256=hashlib.sha256(raw).hexdigest()))
        return render_calibration_inp_fragment(pointed, governed_engineering_constants(pointed), raw)

    def text(self):
        return self.source_inp.decode("latin-1")

    def test_unknown_material_options_fail_closed(self):
        record = self.released()
        source = self.text()
        after_elastic = "*Material, name=Core_PLA"
        cases = {  # genuine Abaqus material options / sub-options outside the supported and the old refusal sets
            "*Mohr Coulomb after *Elastic": source.replace(
                after_elastic, "*Mohr Coulomb\n 30., 0.\n*Mohr Coulomb Hardening\n 10., 0.\n" + after_elastic, 1),
            "*Fail Stress sub-option of *Elastic": source.replace(
                after_elastic, "*Fail Stress\n 600., -500., 600., -500., 80., 0., 0.\n" + after_elastic, 1),
            "*Plastic (old refusal list)": source.replace(after_elastic, "*Plastic\n 100., 0.\n" + after_elastic, 1),
            "unexpected structural keyword": source.replace(
                after_elastic, "*Initial Conditions, type=TEMPERATURE\nSet-1, 20.\n" + after_elastic, 1),
            "lower-case unknown option": source.replace(after_elastic, "*mohr coulomb\n 30., 0.\n" + after_elastic, 1),
        }
        for name, text in cases.items():
            with self.subTest(case=name):
                self.assertNotEqual(text, source)
                with self.assertRaisesRegex(CalibrationFragmentRefusal, "not a recognised material-block boundary"):
                    self.render(record, text)
        before = source.replace("*Elastic, type=ENGINEERING CONSTANTS\n52000.",
                                "*Mohr Coulomb\n 30., 0.\n*Elastic, type=ENGINEERING CONSTANTS\n52000.", 1)
        self.assertNotEqual(before, source)
        with self.assertRaisesRegex(CalibrationFragmentRefusal, "cannot be cloned"):  # *Elastic outside the block
            self.render(record, before)

    def test_forward_builder_parsing_is_unchanged(self):
        text = self.text().replace("*Material, name=Core_PLA",
                                   "*Mohr Coulomb\n 30., 0.\n*Material, name=Core_PLA", 1)
        lines = forward_builder.split_inp_lines(text.encode("latin-1"))
        start, end = forward_builder.material_block_bounds(lines, "CFRP_Face")
        self.assertEqual(lines[end], "*Mohr Coulomb\n")  # the historical block end; the clone refuses it
        self.assertEqual(forward_builder.locate_engineering_constants(lines, "CFRP_Face").values.E1, 52000.0)
        self.assertEqual(forward_builder._MATERIAL_OPTIONS,
                         {"density", "elastic", "expansion", "damping", "conductivity", "specific heat"})

    def test_recognised_boundaries_clone_completely(self):
        record = self.released()
        source = self.text()
        core = source.index("*Material, name=Core_PLA")
        step = source.index("*Step, name=")
        self.assertLess(core, step)
        cases = {"next *Material": source,
                 "*Step after a comment (the pinned SP02 / SP13 layout)":
                     source[:core] + "** ----------------\n**\n** STEP: Modal\n**\n" + source[step:],
                 "end of the input": source[:core]}
        for name, text in cases.items():
            with self.subTest(case=name):
                fragment = self.render(record, text)
                clone = material_block(fragment.content, fragment.material_name)
                original = material_block(text, "CFRP_Face")
                self.assertEqual(len(clone), len(original))
                self.assertEqual(clone[1:3], ["*Density", " 1.57e-09,"])
                self.assertNotIn("** ------", fragment.content.split("*Material,", 1)[1])  # trailing comment

    def test_pinned_source_regression(self):
        record = self.released()
        constants = governed_engineering_constants(record)
        source = self.text()
        fragment = render_calibration_inp_fragment(record, constants, self.source_inp)
        self.assertEqual(fragment.source_inp_sha256, hashlib.sha256(self.source_inp).hexdigest())
        mutated = bytearray(self.source_inp)
        mutated[-2] ^= 0x01  # one byte, outside the material block
        with self.assertRaisesRegex(CalibrationFragmentRefusal, "SHA-256"):
            render_calibration_inp_fragment(record, constants, bytes(mutated))
        with self.assertRaisesRegex(CalibrationFragmentRefusal, "cannot be cloned"):
            self.render(record, source.replace("*Material, name=Core_PLA", "*Material, name=CFRP_Face", 1))
        damped = source.replace("*Material, name=CFRP_Face\n*Density\n 1.57e-09,\n",
                                "*Material, name=CFRP_Face\n*Density\n 1.57e-09,\n*Damping, alpha=0.5\n"
                                "*Expansion\n 2.1e-06,\n*Conductivity\n 0.6,\n*Specific Heat\n 1.1e+09,\n", 1)
        damped_fragment = self.render(record, damped)
        clone = material_block(damped_fragment.content, damped_fragment.material_name)
        for line in ("*Density", " 1.57e-09,", "*Damping, alpha=0.5", "*Expansion", " 2.1e-06,", "*Conductivity",
                     " 0.6,", "*Specific Heat", " 1.1e+09,"):
            self.assertIn(line, clone)
        elastic = clone.index("*Elastic, type=ENGINEERING CONSTANTS")
        self.assertEqual(clone[elastic + 1:elastic + 3], ["50000.0, 50000.0, 6700., 0.05, 0.3, 0.3, 4500.0, 2200.",
                                                          "2200.,"])
        self.assertRegex(fragment.material_name, r"^CAL_A_[0-9a-f]{12}$")
        self.assertNotIn("*Material, name=CFRP_Face", fragment.content)  # production material untouched
        self.assertEqual(fragment.content.count("*Material,"), 1)
        again = render_calibration_inp_fragment(record, constants, self.source_inp)
        self.assertEqual((again.content, again.content_sha256), (fragment.content, fragment.content_sha256))

    def test_rendering_touches_no_file_and_no_process(self):
        record = self.released()
        constants = governed_engineering_constants(record)
        forbidden = mock.Mock(side_effect=AssertionError("filesystem or process access"))
        with mock.patch("builtins.open", forbidden), mock.patch.object(Path, "write_text", forbidden), \
                mock.patch.object(Path, "write_bytes", forbidden), mock.patch.object(Path, "mkdir", forbidden), \
                mock.patch.object(Path, "read_bytes", forbidden), mock.patch.object(os, "replace", forbidden), \
                mock.patch.object(subprocess, "Popen", forbidden), mock.patch.object(subprocess, "run", forbidden):
            fragment = render_calibration_inp_fragment(record, constants, self.source_inp)
        forbidden.assert_not_called()
        self.assertTrue(fragment.content.startswith("** ---"))

    def test_real_pinned_inputs_have_a_clonable_layout(self):
        """READ-ONLY layout check of the pinned SP02 / SP13 production inputs (no fragment, no calibration)."""
        roots = fixture_roots_from_environment()
        if "snadwich" not in roots:
            self.skipTest("data store snadwich not configured")
        fixtures = load_experiment_fixture_manifest(DOCS / "fixtures" / "real_experiment_fixtures.json")
        boundaries = output_module._MATERIAL_BLOCK_BOUNDARIES
        fixed = PARAMETERISATIONS["carbon-property-set/v1"].fixed_constants
        for label in ("SP02", "SP13"):
            with self.subTest(specimen=label):
                manifest = load_forward_model_manifest(DOCS / "forward_models" / f"{label}.physical.forward.json")
                passport = load_specimen_manifest(DOCS / "specimens" / f"{label}.physical.specimen.json")
                material = bind_forward_model(manifest, passport, fixtures).material_name
                raw = (Path(roots["snadwich"]) / manifest.model_input.location.relative_path).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), manifest.model_input.sha256)
                lines = forward_builder.split_inp_lines(raw)
                start, end = forward_builder.material_block_bounds(lines, material)
                self.assertIn(forward_builder.inp_keyword(lines[end]), boundaries)
                options = [forward_builder.inp_keyword(x) for x in lines[start + 1:end]
                           if forward_builder.inp_keyword(x) is not None]
                self.assertEqual(options, ["density", "elastic"])
                values = forward_builder.locate_engineering_constants(lines, material).values
                for name, value in fixed.items():
                    self.assertEqual(getattr(values, name), value, name)


# ----------------------------------------------------------------------------- §12 historical immutability

class HistoricalImmutabilityTests(unittest.TestCase):
    def test_historical_records_are_byte_for_byte_the_accepted_ones(self):
        for relative, expected in HISTORICAL_RECORDS.items():
            with self.subTest(record=relative):
                self.assertEqual(canonical_hash(_load(DOCS / relative)), expected)

    def test_campaign_and_run_identities(self):
        for name, campaign_hash, run_hash in (("M7_RUN_A", RUN_A_CAMPAIGN_HASH, RUN_A_RUN_HASH),
                                              ("M7_RUN_B", RUN_B_CAMPAIGN_HASH, RUN_B_RUN_HASH)):
            with self.subTest(run=name):
                definition = load_campaign_definition(CAMPAIGNS / f"{name}.campaign.json")
                result = _load(CAMPAIGNS / f"{name}.result.json")
                self.assertEqual((definition.schema, definition.campaign_hash), (CAMPAIGN_SCHEMA, campaign_hash))
                self.assertEqual((definition.scientific_question, definition.tau_mf), (None, None))
                self.assertEqual((result["campaign_hash"], result["run_hash"]), (campaign_hash, run_hash))
                self.assertEqual(result["journals"]["campaign"]["run_hash"], run_hash)
        correction = _load(DOCS / "audit_corrections" / "M7_FAMILY_CONSISTENCY_CORRECTION.json")
        self.assertEqual((correction["run_a"]["campaign_hash"], correction["run_a"]["run_hash"]),
                         (RUN_A_CAMPAIGN_HASH, RUN_A_RUN_HASH))
        self.assertEqual((correction["run_b"]["campaign_hash"], correction["run_b"]["run_hash"]),
                         (RUN_B_CAMPAIGN_HASH, RUN_B_RUN_HASH))

    def test_v1_1_pattern_records_recompute_unchanged(self):
        for name in ("M7_RUN_A", "M7_RUN_B"):
            with self.subTest(run=name):
                result = _load(CAMPAIGNS / f"{name}.result.json")
                record = result["m5_diagnostics"]["pattern"]
                fit = [ResidualTerm(t, (t,), f["family"], v) for f in record["families"]
                       for t, v in zip(f["term_ids"], f["values"])]
                held = [ResidualTerm(t, (t,), "HOLDOUT", v) for t, v in record["holdouts"].items()]
                pattern = residual_pattern_test(fit, held)  # v1.1: no τ_mf
                self.assertEqual(pattern.to_dict(), record)
                self.assertEqual(pattern.record_hash, result["m5_verdict"]["evidence_hashes"]["pattern"])
                self.assertEqual(record["schema"], "auto-id/identification-uncertainty/v1")

    def test_verdicts_and_classification_are_not_reinterpreted(self):
        run_a, run_b = _load(CAMPAIGNS / "M7_RUN_A.result.json"), _load(CAMPAIGNS / "M7_RUN_B.result.json")
        self.assertEqual({k: v["verdict"] for k, v in run_a["m5_verdict"]["verdicts"].items()},
                         {"E_in_plane_mpa": "NOT_IDENTIFIABLE"})
        self.assertEqual({k: v["verdict"] for k, v in run_b["m5_verdict"]["verdicts"].items()},
                         {"E_in_plane_mpa": "NOT_IDENTIFIABLE", "G12_mpa": "NOT_IDENTIFIABLE"})
        self.assertEqual((run_a["material_claim"], run_b["material_claim"]), (NO_MATERIAL_CLAIM, NO_MATERIAL_CLAIM))
        correction = _load(DOCS / "audit_corrections" / "M7_FAMILY_CONSISTENCY_CORRECTION.json")
        interpretation = correction["corrected_interpretation"]
        self.assertTrue(interpretation["formal_output"].startswith("NO GLOBAL PARAMETER VALUE"))
        self.assertEqual(interpretation["reasons"], ["FAMILY_CONSISTENCY_FAIL (SPEC §13)",
                                                     "M5 NOT_IDENTIFIABLE (SPEC §1 upper rule)"])
        self.assertEqual((correction["run_a"]["verdict"], correction["run_b"]["verdict"]),
                         ("FAIL", "NOT_EVALUABLE_RANK_DEFICIENT"))
        closure = _load(CAMPAIGNS / "M7_CLOSURE.json")
        self.assertEqual(closure["run_b"]["status"], "ACCEPTED_DIAGNOSTIC_ONLY")
        self.assertEqual(set(closure["run_b"]["m5_verdict"].values()), {"NOT_IDENTIFIABLE"})
        self.assertEqual(closure["run_a"]["m5_verdict"], {"E_in_plane_mpa": "NOT_IDENTIFIABLE"})
        # §13 recomputed from the frozen records under the current code: unchanged
        for name, status in (("M7_RUN_A", "FAIL"), ("M7_RUN_B", "NOT_EVALUABLE_RANK_DEFICIENT")):
            record = _load(CAMPAIGNS / f"{name}.result.json")
            document = campaign_family_consistency(
                load_campaign_definition(CAMPAIGNS / f"{name}.campaign.json"),
                record["m5_diagnostics"]["jacobian"]["whitened"], record["campaign_evaluations"][-1],
                {"parameters": record["parameters"]}, True)
            self.assertEqual(document["status"], status, name)

    def test_historical_campaigns_cannot_enter_the_v1_2_paths(self):
        historical = load_campaign_definition(CAMPAIGNS / "M7_RUN_A.campaign.json")
        historical.require_question_supported()  # material ID as before; no calibration question
        self.assertEqual(evaluate_calibration_gate(replace(build(), definition=historical)).refusal_codes,
                         ("WRONG_SCHEMA_OR_QUESTION",))

    def test_archived_journals_and_manifests(self):
        roots = fixture_roots_from_environment()
        for store, (name, run_hash) in (("m7-run-a", ("M7_RUN_A", RUN_A_RUN_HASH)),
                                         ("m7-run-b", ("M7_RUN_B", RUN_B_RUN_HASH))):
            with self.subTest(store=store):
                if store not in roots:
                    self.skipTest(f"data store {store} not configured")
                root = Path(roots[store])
                for relative, expected in RUN_STORE_FILES[store].items():
                    self.assertEqual(hashlib.sha256((root / relative).read_bytes()).hexdigest(), expected, relative)
                result = _load(CAMPAIGNS / f"{name}.result.json")
                journal = _load(root / "campaign" / run_hash / "journal.json")
                self.assertEqual(canonical_hash(journal["run_identity"]), run_hash)
                previous = run_hash
                for index, entry in enumerate(journal["entries"]):  # the hash chain, read only
                    body = {k: entry[k] for k in ("sequence", "kind", "record", "previous_hash")}
                    self.assertEqual((entry["sequence"], entry["previous_hash"], entry["entry_hash"]),
                                     (index, previous, canonical_hash(body)))
                    previous = entry["entry_hash"]
                self.assertEqual((len(journal["entries"]), previous),
                                 (result["journals"]["campaign"]["entries"],
                                  result["journals"]["campaign"]["last_entry_hash"]))
                self.assertEqual({s["label"]: s["observation_hash"] for s in journal["run_identity"]["specimens"]},
                                 OBSERVATION_HASHES)
                for label, summary in result["journals"]["specimens"].items():
                    path = next(root.glob(f"specimens/*/*/{summary['run_hash']}/journal.json"))
                    entries = _load(path)["entries"]
                    self.assertEqual(entries[-1]["entry_hash"], summary["last_entry_hash"], label)


# ----------------------------------------------------------------------------- §13 production safety

class ProductionRefusalTests(unittest.TestCase):
    def test_calibration_execution_is_refused_with_zero_side_effects(self):
        calibration = parse_campaign_definition(calibration_definition())
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            item, store = synthetic_specimen(calibration, "A", tmp / "data")
            before = sorted(p.relative_to(tmp).as_posix() for p in tmp.rglob("*"))
            solver, extractor = FakeSolver(), FakeExtractor()
            config = CampaignRunConfig(tmp / "runs", {"synthetic": store}, "abq2024.bat", solver, extractor, {},
                                       "m" * 64)
            forbidden = mock.Mock(side_effect=AssertionError("forbidden call"))
            with mock.patch.object(campaign_module, "run_bounded_lm", forbidden), \
                    mock.patch.object(campaign_module, "prepare_forward_job", forbidden, create=True), \
                    mock.patch.object(subprocess, "Popen", forbidden), mock.patch.object(subprocess, "run", forbidden), \
                    mock.patch("os.system", forbidden):
                for attempt in (lambda: CampaignRun(calibration, [item], "m" * 64, config),
                                lambda: prepare_run_manifest(calibration, None, [item], {"synthetic": store}, ROOT,
                                                             tmp / "jobs"),
                                lambda: build_campaign_report(calibration, [item], [], {"status": "CONVERGED",
                                                                                        "parameters": None}),
                                calibration.require_executable, calibration.require_question_supported):
                    with self.assertRaises(CalibrationNotImplementedRefusal) as refused:
                        attempt()
                    self.assertEqual(refused.exception.state, CALIBRATION_NOT_IMPLEMENTED)
            forbidden.assert_not_called()  # zero optimisation, zero solver / Abaqus processes
            self.assertEqual(solver.commands, [])
            self.assertEqual(sorted(p.relative_to(tmp).as_posix() for p in tmp.rglob("*")), before)  # nothing written
            self.assertFalse((tmp / "runs").exists())
            self.assertFalse((tmp / "jobs").exists())

    def test_no_execution_path_reaches_the_calibration_services(self):
        for module in ("specimen_calibration_gate", "specimen_calibration_output"):
            users = sorted(p.relative_to(ROOT).as_posix() for folder in ("src", "tools") for p in
                           (ROOT / folder).rglob("*.py") if module in p.read_text(encoding="utf-8")
                           and p.stem not in ("specimen_calibration_gate", "specimen_calibration_output"))
            # only the pure I3 / I4 services and the read-only V12-I6 backend (it judges journalled runs and executes
            # nothing: test_v12_i6_backend_integration.ExecutionSafetyTests); no run wiring
            self.assertEqual(users, ["src/services/campaign_scientific_backend.py"], module)


def tearDownModule():
    directory = FamilyConsistencyTests.__dict__.get("_directory")  # shared with QuestionContractTests
    if directory is not None:
        directory.cleanup()


if __name__ == "__main__":
    unittest.main()
