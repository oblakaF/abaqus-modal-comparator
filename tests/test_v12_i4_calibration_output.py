"""V12-I4 — specimen-calibration output record and separate calibration INP fragment (SPEC v1.2 §1 B, §6, §9).

The builder evaluates the V12-I3 gate itself on the same evidence bundle; RELEASED values are exactly the judged
p̂, never a material property; a REFUSED record carries only a diagnostic optimiser candidate.  The fragment
renderer is separate from the production-material forward builder, needs a RELEASED record and the complete
governed constants, and writes nothing.  No Abaqus.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import replace
import inspect
import json
import math
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.campaign_definition import CalibrationNotImplementedRefusal, parse_campaign_definition
from domain.frozen_observations import ObservationRow
from domain.identification_run import canonical_hash
from m4_6_support import FakeExtractor, FakeSolver
from services import forward_builder
from services.identification_campaign_run import CampaignRun, CampaignRunConfig, campaign_run_identity
from services.identification_verdict import EvidenceState, GuardEvidence
from services.practical_identifiability import PracticalIdentifiabilityInputError
from services.specimen_calibration_gate import evaluate_calibration_gate
from services.specimen_calibration_output import (
    CANDIDATE_LABELS,
    LABELS,
    CalibrationFragmentRefusal,
    CalibrationOutputStatus,
    ExcludedDiagnosticsEvidence,
    ExcludedModeDiagnostic,
    GovernedConstant,
    build_calibration_output,
    calibration_material_name,
    governed_baseline_rows,
    governed_engineering_constants,
    render_calibration_inp_fragment,
)
from test_m7_campaign import synthetic_definition, synthetic_specimen
from test_v12_i1_campaign_question import calibration_definition
from test_v12_i3_calibration_gate import P_HAT, build
from v12_evidence_support import evaluate_candidate, evaluated_bundle


NONE_EXCLUDED = ExcludedDiagnosticsEvidence((), "synthetic D-076 evaluation: no excluded mode reaches MAC 0.80", True)
SIMPLE_SENSITIVITIES = {"R1": (0.50,), "R2": (0.45,)}  # the synthetic M5 system of specimen A
CLUSTER_ROWS = [("R1", 1, 7, "FIT"), ("R2", 2, 8, "FIT"), ("R3", 3, 9, "FIT"), ("R4", 4, 10, "FIT"),
                ("H1", 5, 11, "HOLDOUT")]
CLUSTER_FAMILIES = {"R1": "F1", "R2": "F1", "R3": "F2", "R4": "F2", "H1": "T"}
BASELINE_RATIO = math.exp(0.03)  # synthetic frozen baseline f_FE / f_EXP


def keys(node) -> set:
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in keys(v)}
    if isinstance(node, list):
        return {k for v in node for k in keys(v)}
    return set()


class _Case(unittest.TestCase):
    """Bundles built from a genuine journalled evaluation of p̂ (``v12_evidence_support``); the evidence of each bundle
    is registered by campaign and p̂ and passed to ``build_calibration_output`` (``self.evidence``)."""

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.tmp = Path(self._directory.name)
        self._evidence, self._last_evidence = {}, None

    def tearDown(self):
        self._directory.cleanup()

    @staticmethod
    def _key(inputs, run_hash=None, system_hash=None) -> tuple:
        return (inputs.definition.campaign_hash,
                canonical_hash({k: float(v) for k, v in sorted(inputs.p_hat.items())}), run_hash, system_hash)

    def register(self, inputs, evidence):
        run_hash = evidence.pipeline_journal["run_identity"]["extra"]["campaign_hash"]
        self._evidence[self._key(inputs)] = evidence
        self._evidence[self._key(inputs, run_hash, evidence.system.system_hash)] = evidence
        self._last_evidence = evidence
        return evidence

    def evidence(self, inputs, item=None):
        """The evaluation evidence of this p̂, calibration run (specimen, frozen set, families) and M5 system; a
        mixed bundle is checked against real evidence: the closest registered one, else the last."""
        if item is not None:
            run_hash = canonical_hash(campaign_run_identity(inputs.definition, [item], "m" * 64, {}))
            system_hash = None if inputs.analysis is None else inputs.analysis.system_hash
            if self._key(inputs, run_hash, system_hash) in self._evidence:
                return self._evidence[self._key(inputs, run_hash, system_hash)]
        return self._evidence.get(self._key(inputs), self._last_evidence)

    def output(self, inputs, item, run, excluded=NONE_EXCLUDED, *rest):
        return build_calibration_output(inputs, item, run, excluded, self.evidence(inputs, item), *rest)

    def simple(self, tau=0.02, p_hat=50000.0):
        """One specimen A (frozen rows R1, R2 FIT; R3 HOLDOUT) and the bundle of its journalled evaluation at p̂."""
        definition = parse_campaign_definition(calibration_definition(tau))
        base = self.tmp / f"s{tau}{p_hat}"
        item, store = synthetic_specimen(definition, "A", base)
        self.source_inp = (store / "models" / "SYA.inp").read_bytes()  # the pinned INP (read by the test only)
        inputs, item, run, evidence = evaluated_bundle(definition, item, store, base / "runs",
                                                       {"E_in_plane_mpa": p_hat}, SIMPLE_SENSITIVITIES)
        self.register(inputs, evidence)
        return inputs, item, run

    def cluster(self, **changes):
        """A specimen with rows R1, R2 (F1), the confirmed cluster C(R3+R4) (F2) and the holdout H1 (T).

        The gate bundle is the I3 synthetic one; the registered evidence is the specimen's genuine (cluster-free) M4
        evaluation, so a cluster bundle reaches the output only to be refused as unverified."""
        data = calibration_definition()
        data["specimens"][0]["rows"] = [{"row_id": r, "experimental_mode": e, "fe_mode": f, "role": role}
                                        for r, e, f, role in CLUSTER_ROWS]
        definition = parse_campaign_definition(data)
        item, store = synthetic_specimen(definition, "A", self.tmp / "cluster")
        rows = tuple(ObservationRow(r, e, 100.0 + 10 * e, f, (100.0 + 10 * e) * BASELINE_RATIO, 0.98, BASELINE_RATIO - 1)
                     for r, e, f, _ in CLUSTER_ROWS)  # frozen baseline Δ ln f = +0.03 on every row
        item = replace(item, frozen=replace(item.frozen, rows=rows), holdout_rows=("H1",),
                       families=dict(CLUSTER_FAMILIES))
        arguments = dict(definition=definition, fit=[0.5, -0.4, 0.3], clusters=(("R3", "R4"),),
                         cluster_offsets={"C(R3+R4)": 0.004})
        arguments.update(changes)
        inputs = replace(build(**arguments), baseline_pair_macs={r: 0.98 for r in ("R1", "R2", "R3", "R4")},
                         baseline_rows=governed_baseline_rows(item))
        evaluation = evaluate_candidate(definition, item, store, self.tmp / "cluster" / "runs", P_HAT,
                                        {r: (0.5,) for r in ("R1", "R2", "R3", "R4")})
        self.register(inputs, evaluation.evidence)
        return inputs, item, evaluation.run_identity


class ReleasedTests(_Case):
    def test_a_passing_bundle_releases_exactly_the_judged_candidate(self):
        inputs, item, run = self.simple()
        record = self.output(inputs, item, run, NONE_EXCLUDED)
        self.assertIs(record.status, CalibrationOutputStatus.RELEASED)
        data = record.to_dict()
        self.assertEqual((data["output_class"], data["labels"]), ("SPECIMEN_ENGINEERING_CALIBRATION", list(LABELS)))
        for name, value in inputs.p_hat.items():  # exactly p̂ of the judged bundle, unrounded
            self.assertIs(type(data["calibration_parameters"][name]["value"]), float)
            self.assertEqual(data["calibration_parameters"][name]["value"], value)
            self.assertEqual(data["calibration_parameters"][name]["role"], "MODEL_CALIBRATION_PARAMETER")
        self.assertEqual(record.gate_record_hash, evaluate_calibration_gate(inputs).record_hash)
        self.assertEqual(data["identity"]["gate_record_hash"], record.gate_record_hash)
        self.assertNotIn("diagnostic_optimizer_candidate", data)
        text = json.dumps(data)
        for label in ('"IDENTIFIED"', '"WIDE"', '"NOT_IDENTIFIABLE"'):
            self.assertNotIn(label, text)
        self.assertFalse({"material_property", "reported_value", "reported_material_value", "verdict"} & keys(data))
        self.assertEqual(data["fixed_parameters"]["G12_mpa"]["value"], 4500.0)

    def test_identity_uncertainty_and_rows(self):
        inputs, item, run = self.simple()
        data = self.output(inputs, item, run, NONE_EXCLUDED).to_dict()
        identity = data["identity"]
        manifest = item.model.manifest
        self.assertEqual((identity["campaign_hash"], identity["run_hash"]),
                         (inputs.definition.campaign_hash, canonical_hash(run)))
        self.assertEqual((identity["inp_sha256"], identity["registration_hash"], identity["tau_mf"]),
                         (manifest.model_input.sha256, manifest.registration_hash, 0.02))
        self.assertEqual(identity["forward_model"]["manifest_hash"], manifest.manifest_hash)
        self.assertEqual((identity["specimen"]["label"], identity["test_run_id"]),
                         ("A", str(item.model.passport.test_run_id)))
        self.assertNotRegex(json.dumps(data), r"[A-Za-z]:\\\\|\b(utc|timestamp)\b")
        # uncertainty: the I3 envelope and the conditional basis, unchanged; τ_mf only as a tolerance
        gate = evaluate_calibration_gate(inputs)
        self.assertEqual(data["precision"], gate.precision)
        self.assertEqual(data["uncertainty_basis"], gate.uncertainty_basis)
        self.assertEqual(data["uncertainty_basis"]["basis"], "UNCERTAINTY_CONDITIONAL_ON_AVAILABLE_COVARIANCE")
        self.assertIn("not a complete experimental uncertainty", data["uncertainty_basis"]["note"])
        self.assertEqual(data["tau_mf"]["role"], "ACCEPTANCE_TOLERANCE")
        for item_ in data["precision"]["parameters"].values():
            self.assertEqual(set(item_), {"birge_adjusted_sd_ln", "model_form_half_range_ln",
                                          "conservative_uncertainty_ln", "pass"})
        self.assertEqual(data["precision"]["ceiling_ln"], 0.08)
        # the full physical-row table and the authoritative I3 non-degradation
        self.assertEqual([(r["row_id"], r["role"]) for r in data["governed_rows"]],
                         [("R1", "FIT"), ("R2", "FIT"), ("R3", "HOLDOUT")])
        for row in data["governed_rows"]:
            self.assertEqual(row["candidate_relative_frequency_error"], math.expm1(row["candidate_delta_ln_f"]))
            self.assertIsNotNone(row["tracking_mac"])
            self.assertEqual(row["baseline_pair_mac"] is None, row["role"] == "HOLDOUT")
        self.assertEqual(data["non_degradation"], gate.non_degradation)
        self.assertEqual(data["excluded_diagnostics"]["records"], [])  # explicit complete empty list
        self.assertTrue(data["excluded_diagnostics"]["complete"])
        self.assertTrue(data["excluded_diagnostics"]["provenance"])

    def test_cluster_members_cannot_be_released_without_member_evidence(self):
        # V12-I5 (F1): M4 tracks a confirmed cluster as a subspace and judges its pairing-independent mean; the
        # per-member candidate frequencies and tracking MACs the gate needs are not part of the evaluation.
        inputs, item, run = self.cluster()
        self.assertTrue(evaluate_calibration_gate(inputs).passed)  # the gate science alone would pass ...
        with self.assertRaisesRegex(PracticalIdentifiabilityInputError, "CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE"):
            self.output(inputs, item, run)  # ... but nothing is released without verified member evidence

    def test_record_is_deterministic(self):
        inputs, item, run = self.simple()
        first = self.output(inputs, item, run, NONE_EXCLUDED)
        second = self.output(inputs, item, run, NONE_EXCLUDED)
        self.assertEqual(first.record_hash, second.record_hash)
        json.dumps(first.to_dict(), allow_nan=False)

    def test_excluded_diagnostics_are_carried_as_diagnostic_only(self):
        inputs, item, run = self.simple()
        diagnostic = ExcludedModeDiagnostic(20, 410.0, 31, 402.0, 0.86, 402.0 / 410.0 - 1.0, "TORSION",
                                            "frequency gate (strict pairing)")
        record = self.output(inputs, item, run, ExcludedDiagnosticsEvidence(
            (diagnostic,), "synthetic D-076 evaluation", True))
        entry = record.to_dict()["excluded_diagnostics"]["records"][0]
        self.assertEqual((entry["role"], entry["experimental_mode"], entry["mac"]), ("DIAGNOSTIC_ONLY", 20, 0.86))
        self.assertIn("never fitted", entry["enters"])
        built = ExcludedDiagnosticsEvidence.from_campaign_rows([{
            "experimental_mode": 20, "experimental_hz": 410.0, "best_fe_mode": 31, "fe_hz": 402.0, "mac": 0.86,
            "signed_frequency_error": -0.0195, "fe_family": "TORSION", "exclusion_reason": "frequency gate"}],
            "campaign_diagnostics.excluded_mode_diagnostics")
        self.assertEqual(built.records[0].best_fe_mode, 31)
        governed = ExcludedModeDiagnostic(1, 100.0, 9, 101.0, 0.9, 0.01, None, "x")  # R1's experimental mode
        with self.assertRaisesRegex(PracticalIdentifiabilityInputError, "never enter the fit"):
            self.output(inputs, item, run, ExcludedDiagnosticsEvidence((governed,), "x", True))


class RefusedTests(_Case):
    def test_a_refused_gate_releases_nothing(self):
        inputs, item, run = self.simple()
        inputs = replace(inputs, registration=GuardEvidence("registration", EvidenceState.FAIL, "x", "limited"))
        record = self.output(inputs, item, run, NONE_EXCLUDED)
        self.assertIs(record.status, CalibrationOutputStatus.REFUSED)
        data = record.to_dict()
        self.assertNotIn("calibration_parameters", data)
        self.assertIsNone(record.calibration_parameters)
        self.assertEqual((data["output_class"], data["labels"]), (None, []))
        candidate = data["diagnostic_optimizer_candidate"]
        self.assertEqual(candidate["labels"], list(CANDIDATE_LABELS))
        self.assertEqual(candidate["parameters"]["E_in_plane_mpa"]["value"], 50000.0)
        self.assertEqual(data["refusal_reasons"], [dict(r) for r in evaluate_calibration_gate(inputs).refusal_reasons])
        self.assertEqual(len(data["governed_rows"]), 3)  # the full row table is reported for a refusal too
        with self.assertRaises(CalibrationFragmentRefusal):
            render_calibration_inp_fragment(record, {}, self.source_inp)
        with self.assertRaises(CalibrationFragmentRefusal):
            governed_engineering_constants(record)

    def test_reporting_claims_must_be_backed(self):
        inputs, item, run = self.simple()
        refused = replace(inputs, registration=GuardEvidence("registration", EvidenceState.FAIL, "x", "limited"))
        with self.assertRaisesRegex(PracticalIdentifiabilityInputError, "claims excluded_high_mac_modes"):
            self.output(refused, item, run, ExcludedDiagnosticsEvidence((), "not evaluated", False))
        with self.assertRaisesRegex(PracticalIdentifiabilityInputError, "excluded_high_mac_modes"):
            self.output(inputs, item, run, ExcludedDiagnosticsEvidence((), "not evaluated", False))
        with self.assertRaises(PracticalIdentifiabilityInputError):
            self.output(inputs, item, run, ExcludedDiagnosticsEvidence((), "   ", True))


class BindingTests(_Case):
    def raises(self, *args, text=""):
        with self.assertRaisesRegex(PracticalIdentifiabilityInputError, text):
            self.output(*args)

    def test_anti_mixing(self):
        names = set(inspect.signature(build_calibration_output).parameters)
        self.assertEqual(names, {"inputs", "specimen", "run_identity", "excluded", "evaluation",
                                 "expected_gate_record_hash"})
        inputs, item, run = self.simple()
        gate_a = evaluate_calibration_gate(inputs).record_hash
        other = replace(inputs, p_hat={"E_in_plane_mpa": 51000.0})  # candidate B with A's evidence
        with self.assertRaisesRegex(PracticalIdentifiabilityInputError, "another p̂"):
            self.output(other, item, run, NONE_EXCLUDED)
        record_a = self.output(inputs, item, run, NONE_EXCLUDED, gate_a)
        self.assertEqual(record_a.gate_record_hash, gate_a)
        # A consistent candidate B has its own evidence: the gate record carries no value by design, so the output
        # binds the judged candidate and evidence by hash and B's record can never carry A's binding.
        b_inputs, b_item, b_run = self.simple(p_hat=51000.0)
        record_b = self.output(b_inputs, b_item, b_run, NONE_EXCLUDED)
        binding_a, binding_b = record_a.identity["evidence_binding"], record_b.identity["evidence_binding"]
        self.assertNotEqual(binding_a["p_hat_hash"], binding_b["p_hat_hash"])
        self.assertNotEqual(binding_a["model_form_robustness_record_hash"],
                            binding_b["model_form_robustness_record_hash"])
        self.assertEqual(record_b.calibration_parameters["E_in_plane_mpa"]["value"], 51000.0)
        self.assertEqual(binding_a["pattern_record_hash"], inputs.pattern.record_hash)
        self.assertEqual(binding_a["p_hat_hash"], inputs.robustness.p_hat_hash)  # the judged candidate

    def test_identity_mismatches(self):
        inputs, item, run = self.simple()
        other_tau, other_item, other_run = self.simple(tau=0.015)
        self.raises(inputs, item, other_run, NONE_EXCLUDED, text="another campaign")  # campaign / τ_mf
        self.raises(other_tau, item, run, NONE_EXCLUDED)  # a τ_mf-0.015 bundle against the τ-0.02 specimen run
        entry = run["specimens"][0]
        for key, value in (("observation_hash", "0" * 64), ("label", "B"), ("fixture_id", "SYN/B"),
                           ("registration_hash", "1" * 64), ("passport_manifest_hash", "2" * 64),
                           ("forward_model", {"forward_model_id": "x", "manifest_hash": "3" * 64})):
            with self.subTest(run_identity=key):
                self.raises(inputs, item, dict(run, specimens=[dict(entry, **{key: value})]), NONE_EXCLUDED,
                            text=key)
        self.raises(inputs, replace(item, spec=replace(item.spec, label="B")), run, NONE_EXCLUDED, text="specimen")
        self.raises(inputs, replace(item, spec=replace(item.spec, fixture_id="SYN/X")), run, NONE_EXCLUDED)
        manifest = item.model.manifest
        wrong_inp = replace(item.model, manifest=replace(manifest, model_input=replace(manifest.model_input,
                                                                                        sha256="f" * 64)))
        self.raises(inputs, replace(item, model=wrong_inp), run, NONE_EXCLUDED, text="INP")
        wrong_registration = replace(item.frozen, identity=replace(item.frozen.identity, registration_hash="4" * 64))
        self.raises(inputs, replace(item, frozen=wrong_registration), run, NONE_EXCLUDED, text="registration")
        self.raises(inputs, item, run, NONE_EXCLUDED, "5" * 64, text="not the gate")

    def test_rows_bind_to_the_specimen(self):
        inputs, item, run = self.simple()
        self.raises(replace(inputs, baseline_pair_macs={k: 0.95 for k in inputs.baseline_pair_macs}), item, run,
                    NONE_EXCLUDED, text="frozen pairing")
        fewer = replace(item, frozen=replace(item.frozen, rows=item.frozen.rows[:2]))  # R3 not a frozen row any more
        self.raises(inputs, fewer, campaign_run_identity(inputs.definition, [fewer], "m" * 64, {}), NONE_EXCLUDED,
                    text="frozen rows")
        cluster_inputs, cluster_item, cluster_run = self.cluster()
        self.raises(cluster_inputs, item, run, NONE_EXCLUDED)  # rows of another specimen
        families = dict(cluster_item.families, R4="F9")  # the cluster family is no longer the members' family
        self.raises(cluster_inputs, replace(cluster_item, families=families), cluster_run, NONE_EXCLUDED)


def material_block(text: str, name: str) -> list[str]:
    """The lines of one *Material block (until the next non-material keyword), trailing comments trimmed."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.lower().replace(" ", "") == f"*material,name={name.lower()}")
    end = start + 1
    options = ("*density", "*elastic", "*expansion", "*damping", "*conductivity", "*specificheat")
    while end < len(lines) and not (lines[end].startswith("*") and not lines[end].startswith("**")
                                    and not lines[end].lower().replace(" ", "").startswith(options)):
        end += 1
    while lines[end - 1].startswith("**") or not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


class FragmentTests(_Case):
    def released(self, p_hat=50000.0):
        inputs, item, run = self.simple(p_hat=p_hat)
        record = self.output(inputs, item, run, NONE_EXCLUDED)
        self.assertTrue(record.released, record.refusal_reasons)
        return record

    def render(self, record, source=None, constants=None):
        return render_calibration_inp_fragment(record, constants or governed_engineering_constants(record),
                                               self.source_inp if source is None else source)

    def repointed(self, record, text):
        """The same record pointing at another (test-built) pinned source INP."""
        raw = text.encode("latin-1")
        return replace(record, identity=dict(record.identity, inp_sha256=hashlib.sha256(raw).hexdigest())), raw

    def test_the_complete_governed_material_block_is_cloned(self):
        record = self.released()
        constants = governed_engineering_constants(record)
        self.assertEqual({k: v.value for k, v in constants.items()},
                         {"E1": 50000.0, "E2": 50000.0, "E3": 6700.0, "nu12": 0.05, "nu13": 0.30, "nu23": 0.30,
                          "G12": 4500.0, "G13": 2200.0, "G23": 2200.0})
        self.assertIn("released calibration parameter E_in_plane_mpa", constants["E1"].provenance)
        self.assertIn("campaign definition fixed parameter G12_mpa", constants["G12"].provenance)
        self.assertIn("carbon-property-set/v1 fixed constant", constants["nu23"].provenance)
        with mock.patch.object(forward_builder, "prepare_forward_job", side_effect=AssertionError), \
                mock.patch.object(forward_builder, "render_forward_input", side_effect=AssertionError):
            fragment = self.render(record)
        source = material_block(self.source_inp.decode("latin-1"), "CFRP_Face")
        clone = material_block(fragment.content, fragment.material_name)
        # the source block has *Density; the clone is not merely *Material + *Elastic
        self.assertIn("*Density", source)
        self.assertEqual(len(clone), len(source))
        self.assertIn("*Density", clone)
        self.assertEqual(clone[clone.index("*Density") + 1], source[source.index("*Density") + 1])  # " 1.57e-09,"
        changed = [i for i, (a, b) in enumerate(zip(source, clone)) if a != b]
        elastic = source.index("*Elastic, type=ENGINEERING CONSTANTS")
        # only the *Material line and the Engineering Constants data lines (the forward builder re-emits a record's
        # data lines as ", "-joined values); every other line of the block is byte-identical
        self.assertEqual(changed, [0, elastic + 1, elastic + 2])
        self.assertEqual(clone[0], f"*Material, name={fragment.material_name}")
        self.assertEqual(clone[elastic + 1], "50000.0, 50000.0, 6700., 0.05, 0.3, 0.3, 4500.0, 2200.")
        self.assertEqual(source[elastic + 1], "52000.,52000., 6700.,  0.05,   0.3,   0.3, 4500., 2200.")
        self.assertEqual((source[elastic + 2], clone[elastic + 2]), (" 2200.,", "2200.,"))  # G23 value unchanged
        self.assertEqual(fragment.content.count("*Material,"), 1)  # one separate material; the source name unused
        self.assertNotIn("*Material, name=CFRP_Face", fragment.content)
        # provenance and warnings
        lines = fragment.content.splitlines()
        self.assertEqual(lines[1:4], ["** SPECIMEN_ENGINEERING_CALIBRATION", "** NOT_A_MATERIAL_PROPERTY",
                                      "** NOT_TRANSFERABLE_WITHOUT_VALIDATION"])
        self.assertEqual((fragment.source_inp_sha256, fragment.source_material_name, fragment.gate_record_hash,
                          fragment.source_calibration_record_hash),
                         (hashlib.sha256(self.source_inp).hexdigest(), "CFRP_Face", record.gate_record_hash,
                          record.record_hash))
        identity = record.identity
        for value in (identity["campaign_hash"], identity["run_hash"], record.gate_record_hash, record.record_hash,
                      identity["inp_sha256"], identity["forward_model"]["manifest_hash"], identity["test_run_id"],
                      fragment.source_material_block_sha256, fragment.material_name):
            self.assertIn(str(value), fragment.content)
        self.assertIn("Complete governed source material block", fragment.content)
        self.assertIn("Only the material name and the governed Engineering Constants were changed", fragment.content)
        self.assertNotIn("not provided here", fragment.content)
        self.assertRegex(fragment.material_name, r"^CAL_A_[0-9a-f]{12}$")
        self.assertNotRegex(fragment.content, r"[A-Za-z]:[\\/]|\\\\|(^|\s)/\w")  # no filesystem path

    def test_other_governed_material_options_are_preserved(self):
        record = self.released()
        text = self.source_inp.decode("latin-1").replace(
            "*Material, name=CFRP_Face\n*Density\n 1.57e-09,\n",
            "*Material, name=CFRP_Face\n*Density\n 1.57e-09,\n*Damping, alpha=0.5, beta=1.2e-06\n"
            "** structural damping of the governed face\n*Expansion\n 2.1e-06,\n")
        pointed, raw = self.repointed(record, text)
        fragment = self.render(pointed, raw)
        clone = material_block(fragment.content, fragment.material_name)
        for line in ("*Damping, alpha=0.5, beta=1.2e-06", "** structural damping of the governed face", "*Expansion",
                     " 2.1e-06,", "*Density", " 1.57e-09,"):
            self.assertIn(line, clone)
        self.assertEqual(len(clone), len(material_block(text, "CFRP_Face")))

    def test_source_binding_and_refusals(self):
        record = self.released()
        self.render(record)  # the exact pinned bytes
        tampered = bytearray(self.source_inp)
        tampered[tampered.index(b"1.57e-09")] = ord("2")
        with self.assertRaisesRegex(CalibrationFragmentRefusal, "SHA-256"):
            self.render(record, bytes(tampered))  # one byte changed
        with self.assertRaises(CalibrationFragmentRefusal):
            self.render(record, self.source_inp.decode("latin-1"))  # not bytes
        missing = replace(record, identity=dict(record.identity, forward_model=dict(
            record.identity["forward_model"], production_material_name="CFRP_Missing")))
        with self.assertRaisesRegex(CalibrationFragmentRefusal, "cannot be cloned"):
            self.render(missing)
        text = self.source_inp.decode("latin-1")
        duplicate = text.replace("*Material, name=Core_PLA", "*Material, name=CFRP_Face", 1)
        with self.assertRaisesRegex(CalibrationFragmentRefusal, "cannot be cloned"):
            self.render(*self.repointed(record, duplicate))
        plastic = text.replace("*Material, name=Core_PLA", "*Plastic\n 100., 0.\n*Material, name=Core_PLA", 1)
        with self.assertRaisesRegex(CalibrationFragmentRefusal, "unsupported option"):
            self.render(*self.repointed(record, plastic))
        other_nu = text.replace("4500., 2200.\n 2200.,", "4500., 2300.\n 2200.,", 1)  # G13 not the governed value
        with self.assertRaisesRegex(CalibrationFragmentRefusal, "not the governed set"):
            self.render(*self.repointed(record, other_nu))

    def test_fragment_is_deterministic_and_value_sensitive(self):
        first, again = self.render(self.released()), self.render(self.released())
        self.assertEqual((first.content, first.content_sha256), (again.content, again.content_sha256))
        changed = self.render(self.released(51000.0))
        self.assertNotEqual(changed.content_sha256, first.content_sha256)
        self.assertNotEqual(changed.material_name, first.material_name)

    def test_incomplete_or_ungoverned_constants_refuse(self):
        record = self.released()
        constants = governed_engineering_constants(record)
        for name in ("E3", "nu23", "G23"):
            with self.subTest(missing=name), self.assertRaisesRegex(CalibrationFragmentRefusal, "missing"):
                self.render(record, constants={k: v for k, v in constants.items() if k != name})
        with self.assertRaisesRegex(CalibrationFragmentRefusal, "not the governed value"):
            self.render(record, constants=dict(constants, nu12=GovernedConstant(0.3, "guess")))
        with self.assertRaisesRegex(CalibrationFragmentRefusal, "unexpected"):
            self.render(record, constants=dict(constants, density=GovernedConstant(1.5e-9, "x")))
        with self.assertRaisesRegex(CalibrationFragmentRefusal, "provenance"):
            self.render(record, constants=dict(constants, E3=GovernedConstant(6700.0, " ")))
        unsupported = replace(record, calibration_parameters={"k_core": {"value": 1.0, "unit": None,
                                                                         "role": "MODEL_CALIBRATION_PARAMETER"}})
        with self.assertRaisesRegex(CalibrationFragmentRefusal, "do not match"):
            governed_engineering_constants(unsupported)
        with self.assertRaises(CalibrationFragmentRefusal):
            self.render(unsupported, constants=constants)
        same_name = replace(record, identity=dict(record.identity, forward_model=dict(
            record.identity["forward_model"], production_material_name="cal_a_000000000000")))
        with mock.patch.object(type(record), "record_hash", new_callable=mock.PropertyMock, return_value="0" * 64), \
                self.assertRaisesRegex(CalibrationFragmentRefusal, "production material name"):
            calibration_material_name(same_name)  # CAL_A_000000000000 == the production name (case-insensitive)

    def test_module_never_builds_forward_jobs_or_touches_files(self):
        source = (ROOT / "src" / "services" / "specimen_calibration_output.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        imported |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        self.assertFalse({m for m in imported if m and re.search(r"subprocess|shutil|^os$", m)})
        from_builder = {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                        and node.module == "forward_builder" for alias in node.names}
        self.assertEqual(from_builder, {"ForwardBuildError", "inp_keyword", "locate_engineering_constants",
                                        "material_block_bounds", "rewrite_engineering_constants", "split_inp_lines"})
        calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func,
                                                                                                    ast.Name)}
        self.assertFalse({"open", "prepare_forward_job", "render_forward_input"} & calls)
        self.assertNotRegex(source, r"\.write_(text|bytes)\(|\.read_(text|bytes)\(|\.mkdir\(")


class ProductionStillBlockedTests(_Case):
    def test_calibration_campaign_execution_is_still_refused(self):
        calibration = parse_campaign_definition(calibration_definition())
        item, store = synthetic_specimen(calibration, "A", self.tmp)
        solver = FakeSolver()
        config = CampaignRunConfig(self.tmp / "runs", {"synthetic": store}, "abq2024.bat", solver, FakeExtractor(),
                                   {}, "m" * 64)
        with self.assertRaises(CalibrationNotImplementedRefusal) as refused:
            CampaignRun(calibration, [item], "m" * 64, config)
        self.assertIn("output service (V12-I4)", str(refused.exception))
        self.assertIn("blocked pending V12-I5 / V12-I6", str(refused.exception))
        self.assertEqual(solver.commands, [])
        self.assertFalse((self.tmp / "runs").exists())
        self.assertIsNotNone(synthetic_definition)


if __name__ == "__main__":
    unittest.main()
