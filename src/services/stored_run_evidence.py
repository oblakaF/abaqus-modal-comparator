"""Read-only evidence of an already journalled campaign run — Auto-ID M8.3.

The smallest adapter between a GUI selection and the accepted shared backend: it reads an existing run in the accepted
journal layout and hands genuine ``CampaignRunEvidence`` to ``campaign_scientific_backend.judge_campaign_run``.  It is
not a scientific engine and defines no evidence schema:

- the run is the campaign journal file the user selects explicitly (``<run root>/campaign/<run hash>/journal.json``,
  the ``CampaignRun`` layout); no newest run, first directory or matching file name is ever chosen;
- the journal must be the accepted journal format, its directory must be its run hash and its run identity must name
  exactly the selected governed campaign (campaign hash), otherwise there is no evaluation;
- each specimen's pipeline journal is located deterministically by the hash of its governed pipeline identity
  (``campaign_lm_provenance.governed_pipeline_identity``, the ``IdentificationPipeline`` layout
  ``<run root>/specimens/<family>/<design>/<pipeline run hash>/journal.json``); a missing one is passed as missing;
- content-addressed FE packs are loaded with the accepted verifying loader (``load_run_pack``: file SHA-256 and content
  hash) from the journalled extractions; a missing or failing pack is left out and reported;
- each specimen's pinned source INP is read with its SHA-256 verified (the backend needs it to re-render the jobs of a
  specimen calibration); a missing one is left out.

Everything else (journal hash chains, run identity, LM / Jacobian provenance, FE re-derivation, the gates) is judged by
the backend, which refuses incomplete or inconsistent evidence.  Nothing here solves, extracts, plans, runs LM, starts
a process or writes a file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path, PurePosixPath
from typing import Mapping, Optional, Sequence

from domain.campaign_definition import CampaignDefinition
from domain.experiment_fixture import (
    FixtureManifestError,
    FixtureSourceMismatchError,
    FixtureSourceUnavailableError,
    load_experiment_fixture_manifest,
    resolve_external_file,
)
from domain.identification_run import JOURNAL_SCHEMA, canonical_hash

from .campaign_lm_provenance import governed_pipeline_identity
from .campaign_scientific_backend import CampaignRunEvidence, ScientificReadiness, judge_campaign_run
from .identification_campaign_run import CampaignSpecimenInput, ObservationSetMismatch, prepare_campaign_specimens
from .shape_extraction import load_run_pack


FIXTURE_MANIFEST = PurePosixPath("docs/auto_id/fixtures/real_experiment_fixtures.json")


class StoredRunRefusalCode(str, Enum):
    NO_CAMPAIGN = "NO_CAMPAIGN_SELECTED"
    NO_RUN = "NO_RUN_SELECTED"
    UNREADABLE_JOURNAL = "UNREADABLE_JOURNAL"
    NOT_A_CAMPAIGN_RUN = "NOT_A_CAMPAIGN_RUN_JOURNAL"
    RUN_CAMPAIGN_MISMATCH = "RUN_BELONGS_TO_ANOTHER_CAMPAIGN"
    SPECIMENS_UNAVAILABLE = "GOVERNED_SPECIMENS_UNAVAILABLE"


class StoredRunRefusal(ValueError):
    """The selection cannot be evaluated; nothing is passed to the backend."""

    def __init__(self, code: StoredRunRefusalCode, message: str) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code


@dataclass(frozen=True)
class StoredRun:
    journal_path: Path
    run_root: Path
    run_hash: str
    campaign_hash: str
    campaign_journal: Mapping


@dataclass(frozen=True)
class StoredRunEvaluation:
    run: StoredRun
    readiness: ScientificReadiness  # exactly as returned by the backend
    notes: tuple[str, ...]  # loading facts (missing pipeline journals, packs or INP), never a verdict
    # M8.6: the SHA-256-verified pinned source INP bytes of this same evaluation (exactly the evidence the backend
    # judged); used only for the read-only calibration material preview, never written or re-read
    source_inps: Mapping[str, bytes] = field(default_factory=dict)


def _refuse(code: StoredRunRefusalCode, message: str):
    raise StoredRunRefusal(code, message)


def select_stored_run(journal_path) -> StoredRun:
    """Open an explicitly selected campaign journal file (the accepted ``CampaignRun`` layout); read-only."""

    if journal_path is None or not str(journal_path).strip():
        _refuse(StoredRunRefusalCode.NO_RUN, "select the journal.json of an existing campaign run.")
    path = Path(journal_path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        _refuse(StoredRunRefusalCode.UNREADABLE_JOURNAL, f"{path} cannot be read as a journal ({error}).")
    identity = document.get("run_identity") if isinstance(document, Mapping) else None
    if not isinstance(document, Mapping) or document.get("schema") != JOURNAL_SCHEMA \
            or not isinstance(identity, Mapping) or not isinstance(document.get("run_hash"), str):
        _refuse(StoredRunRefusalCode.NOT_A_CAMPAIGN_RUN, f"{path.name} is not an identification journal.")
    run_hash = document["run_hash"]
    if path.name != "journal.json" or path.parent.name != run_hash or path.parent.parent.name != "campaign":
        _refuse(StoredRunRefusalCode.NOT_A_CAMPAIGN_RUN,
                f"{path} is not <run root>/campaign/<run hash>/journal.json of a campaign run.")
    if not isinstance(identity.get("campaign_hash"), str) or not isinstance(identity.get("specimens"), list):
        _refuse(StoredRunRefusalCode.NOT_A_CAMPAIGN_RUN, f"{path.name} is not a campaign run journal.")
    return StoredRun(path, path.parent.parent.parent, run_hash, identity["campaign_hash"], dict(document))


def campaign_specimens(definition: CampaignDefinition, repo_root: Path,
                       roots: Mapping[str, Path]) -> tuple[CampaignSpecimenInput, ...]:
    """The campaign's governed specimen inputs, prepared read-only by the accepted backend (no Abaqus)."""
    fixtures = load_experiment_fixture_manifest(Path(repo_root).joinpath(*FIXTURE_MANIFEST.parts))
    return prepare_campaign_specimens(definition, Path(repo_root), fixtures, roots)


def governed_pipeline_directory(definition: CampaignDefinition, item: CampaignSpecimenInput, run: StoredRun) -> Path:
    """The run directory of the specimen's governed pipeline in this campaign run (``IdentificationPipeline`` layout).

    ``ValueError`` when the run identity lists no archived packs for the specimen or no governed identity can be formed.
    """
    entries = {e.get("label"): e for e in run.campaign_journal["run_identity"]["specimens"] if isinstance(e, Mapping)}
    archived = (entries.get(item.label) or {}).get("archived_packs")
    if not isinstance(archived, Mapping):
        raise ValueError("the run identity lists no archived packs for this specimen")
    try:
        pipeline_hash = canonical_hash(governed_pipeline_identity(definition, item, run.run_hash, archived))
    except Exception as error:  # the governed pipeline cannot be formed: never located otherwise
        raise ValueError(f"no governed pipeline identity ({error})") from error
    passport = item.model.passport
    return run.run_root / "specimens" / str(passport.family_id) / str(passport.design_id) / pipeline_hash


def load_run_evidence(definition: CampaignDefinition, specimens: Sequence[CampaignSpecimenInput], run: StoredRun,
                      roots: Mapping[str, Path]) -> tuple[CampaignRunEvidence, tuple[str, ...]]:
    """Genuine ``CampaignRunEvidence`` of the selected run (missing parts are left missing and noted)."""

    notes, pipelines, packs, sources = [], {}, {}, {}
    for item in specimens:
        try:
            directory = governed_pipeline_directory(definition, item, run)
        except ValueError as error:  # the backend refuses a run without its governed pipelines
            notes.append(f"{item.label}: {error}")
            continue
        try:
            document = json.loads((directory / "journal.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            notes.append(f"{item.label}: governed pipeline journal not available ({error})")
            continue
        pipelines[item.label] = document
        for entry in document.get("entries") or ():
            record = entry.get("record") if isinstance(entry, Mapping) else None
            if not isinstance(record, Mapping) or entry.get("kind") != "extraction":
                continue
            content = record.get("pack_content_sha256")
            try:
                packs[content] = load_run_pack(directory / "packs", record["job_name"], content)
            except Exception as error:  # an unverifiable pack is left out; the backend refuses where it is needed
                notes.append(f"{item.label}: FE pack {str(content)[:12]} not available ({error})")
        try:  # used by the backend for a specimen calibration (job re-rendering); unused for material identification
            sources[item.label] = resolve_external_file(item.model.manifest.model_input, roots,
                                                        verify_sha256=True).read_bytes()
        except (FixtureSourceUnavailableError, FixtureSourceMismatchError, OSError) as error:
            notes.append(f"{item.label}: pinned source INP not available ({error})")
    return CampaignRunEvidence(run.campaign_journal, pipelines, packs, sources), tuple(notes)


def evaluate_stored_run(definition: Optional[CampaignDefinition], journal_path, repo_root: Path,
                        roots: Mapping[str, Path],
                        specimens: Optional[Sequence[CampaignSpecimenInput]] = None) -> StoredRunEvaluation:
    """Judge an explicitly selected, already journalled run of the selected governed campaign (read-only).

    The scientific judgement is ``judge_campaign_run``'s alone; its readiness record is returned unchanged.
    """

    if not isinstance(definition, CampaignDefinition):
        _refuse(StoredRunRefusalCode.NO_CAMPAIGN, "select a governed family / campaign definition first.")
    run = select_stored_run(journal_path)
    if run.campaign_hash != definition.campaign_hash:
        _refuse(StoredRunRefusalCode.RUN_CAMPAIGN_MISMATCH,
                f"the run {run.run_hash[:12]} belongs to campaign hash {run.campaign_hash[:12]}, not to "
                f"{definition.campaign_id} ({definition.campaign_hash[:12]}).")
    if specimens is None:
        try:
            specimens = campaign_specimens(definition, repo_root, roots)
        except (FixtureManifestError, FixtureSourceUnavailableError, FixtureSourceMismatchError, OSError,
                ObservationSetMismatch, ValueError, KeyError) as error:
            _refuse(StoredRunRefusalCode.SPECIMENS_UNAVAILABLE,
                    f"the campaign's governed specimen inputs cannot be prepared ({error}).")
    evidence, notes = load_run_evidence(definition, specimens, run, roots)
    return StoredRunEvaluation(run, judge_campaign_run(definition, specimens, evidence), notes,
                               dict(evidence.source_inps))
