"""Read-only progress of an explicitly selected, already journalled campaign run — Auto-ID M8.4.

"Resume" here means resuming the *inspection* of an existing run: nothing is executed, replayed, solved or written.
Computational resume (``CampaignRun.run`` replaying its journal) stays behind its HUMAN execution gate and is not
offered here.

Every value comes from the accepted journals, after verification:

- the campaign journal: ``stored_run_evidence.select_stored_run`` (accepted journal format, directory = run hash) and
  ``campaign_lm_provenance.journal_document`` (run hash = hash of its run identity, hash chain); its run identity must
  name the selected governed campaign and, when the governed specimen inputs are available, be that campaign's run
  identity field by field (``verify_campaign_run_identity``);
- each specimen's pipeline journal, at the path of its governed pipeline identity
  (``stored_run_evidence.governed_pipeline_directory``), verified the same way;
- counts are the journals' own records (campaign ``evaluation`` / ``result``; pipeline ``evaluation`` / ``solve`` /
  ``solve_failure`` / ``extraction``, as ``IdentificationPipeline.counts``), the budgets are the run identity's.

The freshness identity (``RunProgress.fingerprint`` / ``run_evidence_fingerprint``) covers the verified campaign
journal (run hash, entry chain) and, in definition order, every specimen's governed pipeline journal (label, governed
pipeline run hash, entry chain).  It is ``None`` — equal to nothing — whenever any part is missing or unverified or the
governed specimen inputs are unavailable, so an earlier scientific evaluation is never kept current on incomplete
evidence.

Nothing is inferred: no percentage, remaining time, live solver activity or completion.  A journal without a result
record has no verified LM result — it is not shown as running.  A journalled CONVERGED result is not a scientific
release; the scientific verdict is the shared backend's (Evaluate Stored Run).  Invalid evidence yields no counts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
from typing import Mapping, Optional, Sequence

from domain.campaign_definition import CampaignDefinition
from domain.identification_run import canonical_hash

from .campaign_lm_provenance import LMProvenanceRefusal, journal_document, verify_campaign_run_identity
from .identification_campaign_run import CampaignSpecimenInput
from .stored_run_evidence import StoredRunRefusal, governed_pipeline_directory, select_stored_run


class ProgressState(str, Enum):
    """Presentation states of a stored run's journals (never a scientific verdict, never a live process state)."""

    NOT_SELECTED = "NOT_SELECTED"
    JOURNAL_NOT_VERIFIED = "JOURNAL_NOT_VERIFIED"  # unreadable, wrong schema / layout / identity, broken hash chain
    NO_RESULT_RECORDED = "NO_RESULT_RECORDED"  # no LM result journalled (not evidence of a running process)
    RESULT_RECORDED = "RESULT_RECORDED"
    MULTIPLE_RESULTS_RECORDED = "MULTIPLE_RESULTS_RECORDED"


EXECUTION = ("NOT_AUTHORISED in the GUI: no computation is resumed or started here; running a campaign requires its "
             "HUMAN execution gate; production calibration execution BLOCKED / NOT_AUTHORISED")


def _chain(entries: Sequence) -> list:
    return [e.get("entry_hash") for e in entries if isinstance(e, Mapping)]


@dataclass(frozen=True)
class RunProgress:
    state: ProgressState
    journal_path: Optional[str]
    run_hash: Optional[str]
    fingerprint: Optional[str]  # campaign + every governed pipeline journal; None when any part is not verified
    rows: tuple[tuple[str, str], ...]
    problems: tuple[str, ...] = field(default_factory=tuple)

    @property
    def verified(self) -> bool:
        return self.state not in (ProgressState.NOT_SELECTED, ProgressState.JOURNAL_NOT_VERIFIED)


def _records(entries: Sequence, kind: str) -> list[dict]:
    return [dict(e["record"]) for e in entries if isinstance(e, Mapping) and e.get("kind") == kind
            and isinstance(e.get("record"), Mapping)]


def _not_verified(path, reason: str, run_hash: Optional[str] = None) -> RunProgress:
    return RunProgress(ProgressState.JOURNAL_NOT_VERIFIED, None if path is None else str(path), run_hash, None,
                       (("Journal verification", f"NOT VERIFIED: {reason}"),
                        ("Progress", "not shown: unverified evidence is never presented as progress")), (reason,))


def _pipeline_rows(definition, specimens, run) -> tuple[list[tuple[str, str]], list[str], list]:
    rows, problems, parts = [], [], []
    for item in specimens:
        label = f"Specimen {item.label}"
        try:
            directory = governed_pipeline_directory(definition, item, run)
            document = json.loads((directory / "journal.json").read_text(encoding="utf-8"))
            identity, pipeline_hash, entries = journal_document(document, f"{item.label} pipeline")
        except (ValueError, OSError, UnicodeDecodeError, LMProvenanceRefusal) as error:
            rows.append((label, f"pipeline journal NOT VERIFIED ({error})"))
            problems.append(f"{item.label}: pipeline journal not verified")
            continue
        if pipeline_hash != directory.name:
            rows.append((label, "pipeline journal NOT VERIFIED (it is not the governed pipeline run)"))
            problems.append(f"{item.label}: pipeline journal not the governed run")
            continue
        parts.append([item.label, pipeline_hash, _chain(entries)])
        evaluations = _records(entries, "evaluation")
        solves = sum(bool(s.get("executed")) for s in _records(entries, "solve"))
        failures = len(_records(entries, "solve_failure"))
        rows.append((label, f"pipeline {pipeline_hash[:12]}: {len(evaluations)} evaluation(s) journalled "
                            f"({sum(e.get('refusal') is not None for e in evaluations)} refused, "
                            f"{sum(e.get('fe_source') == 'archived-validated-pack' for e in evaluations)} from "
                            f"archived packs); Abaqus solves recorded {solves + failures} ({failures} failed); "
                            f"{len(_records(entries, 'extraction'))} extraction(s)"))
    return rows, problems, parts


def run_evidence_fingerprint(definition: Optional[CampaignDefinition], journal_path,
                             specimens: Optional[Sequence[CampaignSpecimenInput]]) -> Optional[str]:
    """The freshness identity of the selected run's journals (``None`` unless every part is verified)."""
    return inspect_run_progress(definition, journal_path, specimens).fingerprint


def inspect_run_progress(definition: Optional[CampaignDefinition], journal_path,
                         specimens: Optional[Sequence[CampaignSpecimenInput]] = None,
                         specimens_problem: Optional[str] = None) -> RunProgress:
    """Verified, read-only progress of the selected run of the selected governed campaign (fresh from disk)."""

    if not isinstance(definition, CampaignDefinition):
        return RunProgress(ProgressState.NOT_SELECTED, None, None, None,
                           (("Progress", "no governed campaign selected (a specimen folder declares none)"),))
    if journal_path is None:
        return RunProgress(ProgressState.NOT_SELECTED, None, None, None, (("Progress", "no stored run selected"),))
    try:
        run = select_stored_run(journal_path)
        identity, run_hash, entries = journal_document(run.campaign_journal, "campaign")
    except (StoredRunRefusal, LMProvenanceRefusal) as error:
        return _not_verified(journal_path, str(error))
    if identity.get("campaign_hash") != definition.campaign_hash:
        return _not_verified(journal_path, f"the run belongs to campaign hash {str(identity.get('campaign_hash'))[:12]}, "
                                           f"not to {definition.campaign_id}", run_hash)
    identity_note = "campaign hash verified"
    if specimens is not None:
        try:
            verify_campaign_run_identity(definition, specimens, identity)
        except LMProvenanceRefusal as error:
            return _not_verified(journal_path, str(error), run_hash)
        identity_note = "governed run identity verified field by field"
    elif specimens_problem:
        identity_note = f"campaign hash verified; specimen identities NOT verified ({specimens_problem})"

    evaluations = _records(entries, "evaluation")
    results = _records(entries, "result")
    rows = [
        ("Campaign", f"{definition.campaign_id} ({definition.run_type}); campaign hash {definition.campaign_hash[:12]}"),
        ("Run hash", run_hash),
        ("Journal", str(run.journal_path)),
        ("Journal verification", f"VERIFIED (accepted format, hash chain of {len(entries)} entries; {identity_note})"),
        ("Campaign evaluations journalled", f"{len(evaluations)} ({sum(e.get('refusal') is not None for e in evaluations)}"
                                            " refused)"),
        ("Authorised budgets", f"Abaqus solves {identity.get('abaqus_solve_budget')}; LM evaluations "
                               f"{(identity.get('lm') or {}).get('evaluation_budget')} (run identity)"),
    ]
    problems = []
    if not results:
        state = ProgressState.NO_RESULT_RECORDED
        rows.append(("LM result", "none journalled: no verified LM result (this does not mean a process is running)"))
    else:
        state = ProgressState.RESULT_RECORDED if len(results) == 1 else ProgressState.MULTIPLE_RESULTS_RECORDED
        if len(results) > 1:
            problems.append(f"{len(results)} journalled LM results (a scientific evaluation refuses an ambiguous result)")
        last = results[-1]
        rows.append(("LM result" if len(results) == 1 else f"LM results ({len(results)}; last shown)",
                     f"{last.get('status')}; iterations {last.get('iterations')}; LM evaluations "
                     f"{last.get('lm_evaluations')}; Abaqus solves used {last.get('abaqus_solves_used')}"))
        if last.get("refusal") or last.get("stop"):
            rows.append(("Recorded refusal / stop", str(last.get("refusal") or last.get("stop"))))
    fingerprint = None
    if specimens is not None:
        pipeline_rows, pipeline_problems, parts = _pipeline_rows(definition, specimens, run)
        rows += pipeline_rows
        problems += pipeline_problems
        if not pipeline_problems and len(parts) == len(tuple(specimens)):
            fingerprint = canonical_hash([run_hash, _chain(entries), parts])
    else:
        rows.append(("Specimen pipelines", f"not inspected: governed specimen inputs unavailable ({specimens_problem})"))
        problems.append("specimen pipelines not inspected")
    converged = len(results) == 1 and results[0].get("status") == "CONVERGED"
    rows.append(("Scientific evaluation", "prerequisite recorded (one CONVERGED LM result): request it with Auto-ID — "
                                          "Evaluate Stored Run; a converged LM result is not a release"
                 if converged else "the shared backend would refuse it: no single CONVERGED LM result is journalled"))
    rows.append(("Incomplete or missing evidence", "; ".join(problems) if problems else "none found by this inspection"))
    rows.append(("Execution", EXECUTION))
    return RunProgress(state, str(run.journal_path), run_hash, fingerprint, tuple(rows), tuple(problems))
