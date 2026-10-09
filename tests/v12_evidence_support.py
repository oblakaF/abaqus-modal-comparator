"""Genuine candidate evaluations for the V12 calibration tests (V12-I5, finding F1; no Abaqus).

The calibration bundle is not asserted by the test: the real M4 identification pipeline (``IdentificationPipeline``
with the synthetic fake solver / extractor of the M4.6 tests) evaluates the candidate p̂ for the calibration
specimen, journals it, and the I3 evidence bundle is built from that journalled evaluation:

- FIT / HOLDOUT residuals, tracking MACs and physical candidate rows from the evaluation and its FE pack;
- the M5 records (analysis, statistical_sd, pattern, Birge, model_form_robustness) from the synthetic M5 system and
  those residuals at p̂ (``test_v12_i3_calibration_gate.build``);
- the baseline from the specimen's frozen set (``governed_baseline_rows``).

Desired candidate Δ ln f per row are obtained by choosing the synthetic experimental frequencies of the frozen set
(``exp = f_FE(p̂) · exp(-Δ)``); the frozen baseline FE frequency is ``exp · exp(Δ_baseline)``.  The fake FE model is the
M4.6 one: well-separated modes 7–30 with fixed orthonormal shapes (tracking MAC ≈ 1).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import math
from pathlib import Path
from typing import Mapping, Optional

from domain.frozen_observations import ObservationRow
from domain.identification_run import canonical_hash
from m4_6_support import FakeExtractor, FakeSolver, fake_frequencies
from services.candidate_evaluation_evidence import CandidateEvaluationEvidence
from services.identification_campaign_run import campaign_run_identity, specimen_pipeline_config
from services.identification_pipeline import IdentificationPipeline
from services.shape_extraction import load_run_pack
from services.specimen_calibration_gate import GovernedRow
from services.specimen_calibration_output import governed_baseline_rows
from test_identification_uncertainty import E, G, system
from test_v12_i3_calibration_gate import SIGMA, build


G12_FIXED = 4500.0


def designed_frozen_rows(spec_rows, p_hat: Mapping[str, float], candidate_delta: Mapping[str, float],
                         baseline_delta: Mapping[str, float],
                         macs: Optional[Mapping[str, float]] = None) -> tuple[ObservationRow, ...]:
    """Frozen rows whose candidate Δ ln f at p̂ and frozen baseline Δ ln f are the given values."""
    hz = fake_frequencies(p_hat["E_in_plane_mpa"], p_hat.get("G12_mpa", G12_FIXED))
    macs = macs or {}
    rows = []
    for spec in spec_rows:
        experimental = hz[spec.fe_mode - 7] * math.exp(-candidate_delta[spec.row_id])
        fe = experimental * math.exp(baseline_delta[spec.row_id])
        rows.append(ObservationRow(spec.row_id, spec.experimental_mode, experimental, spec.fe_mode, fe,
                                   macs.get(spec.row_id, 0.98),
                                   fe / experimental - 1.0))
    return tuple(rows)


@dataclass(frozen=True)
class Evaluation:
    run_identity: dict
    evidence: CandidateEvaluationEvidence
    record: dict  # the journalled evaluation


def evaluate_candidate(definition, item, store: Path, run_root: Path, p_hat: Mapping[str, float],
                       sensitivities: Mapping[str, tuple]) -> Evaluation:
    """Run the real M4 pipeline for the calibration specimen at p̂ (fake solver) and collect its evidence."""
    run = campaign_run_identity(definition, [item], "m" * 64, {})
    config = specimen_pipeline_config(definition, item, run_root, {"synthetic": store}, "abq2024.bat", FakeSolver(),
                                      FakeExtractor(), {}, canonical_hash(run))
    pipeline = IdentificationPipeline(config)
    pipeline.evaluate(definition.full_parameters(p_hat))
    document = json.loads((pipeline.run_dir / "journal.json").read_text(encoding="utf-8"))
    record = [e["record"] for e in document["entries"] if e["kind"] == "evaluation"][-1]
    packs = pipeline.run_dir / "packs"
    baseline_job = item.frozen.identity.job_name
    baseline = next(e["record"] for e in document["entries"]
                    if e["kind"] == "extraction" and e["record"]["job_name"] == baseline_job)
    parameters = (E, G) if len(definition.fitted_parameters) == 2 else (E,)
    evidence = CandidateEvaluationEvidence(
        document, record["evaluation_hash"], load_run_pack(packs, record["job_name"], record["pack_content_sha256"]),
        load_run_pack(packs, baseline_job, baseline["pack_content_sha256"]), (store / "models" / "SYA.inp").read_bytes(),
        system({row: sensitivities[row] for row in item.spec.fit_rows}, parameters, sd=SIGMA))
    return Evaluation(run, evidence, record)


def verified_bundle(definition, item, evaluation: Evaluation, sensitivities: Mapping[str, tuple],
                    p_hat: Mapping[str, float]):
    """The I3 evidence bundle of the journalled evaluation (no value chosen by the test)."""
    record = evaluation.record
    fit_rows, holdout_rows = list(item.spec.fit_rows), list(item.spec.holdout_rows)
    parameters = (E, G) if len(definition.fitted_parameters) == 2 else (E,)
    inputs = build(definition=definition, rows={row: sensitivities[row] for row in fit_rows},
                   families={row: item.families[row] for row in fit_rows}, fit=list(record["residuals"]),
                   holdout=tuple((row, item.families[row], record["holdout_residuals"][row]) for row in holdout_rows),
                   parameters=parameters, p_hat=dict(p_hat))
    tracking = {row: mac for row, (_, mac) in record["tracking"].items()}
    pack = evaluation.evidence.candidate_pack
    rows = []
    for row in item.frozen.rows:
        role = "HOLDOUT" if row.row_id in holdout_rows else "FIT"
        hz = pack.frequencies_hz[pack.mode_index(record["tracking"][row.row_id][0])]
        rows.append(GovernedRow(row.row_id, role, math.log(hz) - math.log(row.experimental_hz)))
    return replace(inputs, baseline_pair_macs={r.row_id: r.mac for r in item.frozen.rows if r.row_id in fit_rows},
                   tracking_macs=tracking, candidate_rows=rows, baseline_rows=governed_baseline_rows(item))


def evaluated_bundle(definition, item, store: Path, run_root: Path, p_hat: Mapping[str, float],
                     sensitivities: Mapping[str, tuple], frozen_rows: Optional[tuple] = None):
    """(inputs, item, run identity, evidence) for the item (optionally with designed frozen rows)."""
    if frozen_rows is not None:
        item = replace(item, frozen=replace(item.frozen, rows=frozen_rows))
    evaluation = evaluate_candidate(definition, item, store, run_root, p_hat, sensitivities)
    return verified_bundle(definition, item, evaluation, sensitivities, p_hat), item, evaluation.run_identity, \
        evaluation.evidence
