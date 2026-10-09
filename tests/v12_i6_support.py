"""Synthetic journalled calibration runs for the V12-I6 backend tests (fake solver; no Abaqus, no real FE).

``calibration_run`` runs the accepted ``CampaignRun`` (bounded LM over the specimen's M4 pipeline, the M4.6 fake
solver / extractor) for a one-specimen SPECIMEN_ENGINEERING_CALIBRATION definition and returns the stored journals,
packs and pinned source INP exactly as a reader of the run directory would find them.

The production calibration execution gate (``CampaignDefinition.require_executable``) is unchanged and refuses this
run; it is lifted only inside ``calibration_run``, only for the in-memory fake solver, so that a genuine LM history
exists to judge.  Synthetic evidence: the solver profile is ``SYA/fake`` and stays visible in every readiness record;
it is never a production calibration.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Optional
from unittest import mock

from domain.campaign_definition import CampaignDefinition, parse_campaign_definition
from m4_6_support import FakeExtractor, FakeSolver
from services.campaign_scientific_backend import CampaignRunEvidence
from services.identification_campaign_run import CampaignRun, CampaignRunConfig
from services.shape_extraction import load_run_pack
from test_m7_campaign import TRUTH_E, synthetic_specimen
from test_v12_i1_campaign_question import calibration_definition


def _load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


@dataclass(frozen=True)
class SyntheticRun:
    definition: CampaignDefinition
    item: object  # CampaignSpecimenInput
    evidence: CampaignRunEvidence
    summary: dict
    campaign: CampaignRun
    solver: FakeSolver


def run_evidence(campaign: CampaignRun, source_inps: dict) -> CampaignRunEvidence:
    """The stored journals and every journalled FE pack of a campaign run directory (read-only)."""
    campaign_journal = _load(campaign.run_dir / "journal.json")
    pipelines, packs = {}, {}
    for label, pipeline in campaign.pipelines.items():
        document = _load(pipeline.run_dir / "journal.json")
        pipelines[label] = document
        for entry in document["entries"]:
            if entry["kind"] == "extraction":
                record = entry["record"]
                packs[record["pack_content_sha256"]] = load_run_pack(pipeline.run_dir / "packs", record["job_name"],
                                                                     record["pack_content_sha256"])
    return CampaignRunEvidence(campaign_journal, pipelines, packs, source_inps)


def calibration_run(tmp: Path, experimental_e: float = TRUTH_E, tau_mf: float = 0.02, definition=None, item=None,
                    extractor=None, manifest_hash: str = "m" * 64, **changes) -> SyntheticRun:
    definition = definition or parse_campaign_definition(calibration_definition(tau_mf, **changes))
    if item is None:
        item, store = synthetic_specimen(definition, "A", tmp / "data", experimental_e)
    else:
        store = tmp / "data" / "store"
    solver = FakeSolver()
    config = CampaignRunConfig(tmp / "runs", {"synthetic": store}, "abq2024.bat", solver, extractor or FakeExtractor(),
                               {}, manifest_hash)
    with mock.patch.object(CampaignDefinition, "require_executable", lambda self: self):  # synthetic only (docstring)
        campaign = CampaignRun(definition, [item], manifest_hash, config)
        summary = campaign.run()
    evidence = run_evidence(campaign, {item.label: (store / "models" / "SYA.inp").read_bytes()})
    return SyntheticRun(definition, item, evidence, summary, campaign, solver)


def with_journal(evidence: CampaignRunEvidence, campaign_journal: Optional[dict] = None,
                 pipeline_journals: Optional[dict] = None, packs: Optional[dict] = None,
                 source_inps: Optional[dict] = None) -> CampaignRunEvidence:
    return CampaignRunEvidence(evidence.campaign_journal if campaign_journal is None else campaign_journal,
                               evidence.pipeline_journals if pipeline_journals is None else pipeline_journals,
                               evidence.packs if packs is None else packs,
                               evidence.source_inps if source_inps is None else source_inps)
