"""Guarded Auto-ID execution of a prepared Execution Plan — Auto-ID M8-D2i (one controller for the GUI and the CLI).

**Campaign definition → Execution Plan → guarded executor → journals → progress → scientific backend → result.**

``open_execution_context`` opens an existing Execution Plan folder (M8-D2h).  It accepts the folder only when:

- the folder is one complete, consistent plan (``plan_set_problems``);
- the definition file is byte-for-byte the planned one;
- Pre-run Validation passes again (Definition ``FORMALLY_VALID``, Sources ``SHA256_VERIFIED``);
- the existing planning sequence (``prepare_campaign_plan``, run into a temporary folder) gives the recorded manifest
  hash and authorisation scope again.

The context carries the governed definition, the archive-reuse plan and the prepared specimen inputs.

``GuardedExecutionController`` runs the two separately gated operations with the existing executor only:

- ``ARCHIVE_EXTRACTION`` — ``extract_archived_odbs`` (Abaqus Python on run-store copies of the archived ODBs);
- ``CAMPAIGN_RUN`` — ``journalled_archive_records`` + ``reused_pack_records`` + ``CampaignRun.run`` (the accepted
  bounded LM with the hard solve budget; resumable from its hash-chained journals).

Nothing here optimises, judges or plans anything itself.  The result is read back with the existing services:
``run_progress.inspect_run_progress`` for progress and ``stored_run_evidence.evaluate_stored_run`` →
``campaign_scientific_backend.judge_campaign_run`` for the scientific verdict.

**Authorisation contract.** An operation runs only with an ``ExecutionAuthorisation`` that passes all of these:

- it binds the operation, the plan's authorisation scope hash, campaign hash and manifest hash, and exactly that
  operation's budget;
- it is attested by a trusted ``AuthorisationAuthority``;
- the plan is re-checked as still current immediately before execution, and the binding is checked again against
  that fresh context, so a change of campaign, manifest or scope after authorisation is refused.

The two operations are authorised independently: an extraction authorisation never authorises solves or LM.  Plain
JSON, GUI text, a typed hash, decision / provenance text or an M7 authorisation is never an ``ExecutionAuthorisation``.

**No trusted HUMAN authorisation source exists in this installation.**  The production authority is
``NoTrustedAuthority``: it attests nothing, so the executor stays blocked.  No trusted record is fabricated.  Tests use
an isolated authority of their own that the production GUI cannot reach.

A long operation runs in a worker thread.  Stop takes effect before the next Abaqus solve or extraction starts: a
running process is not killed.  Journals are append-only and hash-chained: a stop, an executor error or an interruption
leaves the written records intact, and a later authorised run resumes from them without repeating a journalled solve.

Every attempt is logged in ``guarded_execution.json`` in the plan folder (``NOT_GOVERNED_EVIDENCE``).  A run attested by
a simulated authority is labelled ``SIMULATED`` and is never a material result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Callable, Mapping, Optional

from domain.campaign_definition import CampaignDefinitionError, load_campaign_definition
from domain.experiment_fixture import ExperimentFixtureManifest
from domain.identification_run import canonical_hash

from . import identification_campaign_run as executor_module
from .campaign_execution_plan import (
    GATE_ARCHIVE_EXTRACTION,
    GATE_CAMPAIGN_RUN,
    MANIFEST_FILE,
    NOT_AUTHORISED,
    PLAN_FILE,
    ExecutionNotAuthorised,
    authorisation_scope,
    plan_gates,
    plan_operations,
    plan_set_problems,
)
from .campaign_lm_provenance import LMProvenanceRefusal, journal_document
from .prerun_validation import prerun_validation

ARCHIVE_EXTRACTION, CAMPAIGN_RUN = GATE_ARCHIVE_EXTRACTION, GATE_CAMPAIGN_RUN
OPERATIONS = (ARCHIVE_EXTRACTION, CAMPAIGN_RUN)
AUTHORISATION_SCHEMA = "auto-id/execution-authorisation/v1"
EXECUTION_LOG_SCHEMA = "auto-id/guarded-execution-log/v1"
EXECUTION_LOG = "guarded_execution.json"
# what the executor adds to a plan folder, which is the run root (CampaignRun / IdentificationPipeline layout)
RUN_ENTRIES = ("archive_reuse", "campaign", "specimens", EXECUTION_LOG)
LOG_LABELS = ("EXECUTION_LOG", "NOT_GOVERNED_EVIDENCE")
SIMULATED = "SIMULATED_TEST_EXECUTION_NEVER_A_MATERIAL_RESULT"
NO_TRUSTED_SOURCE = ("NO_TRUSTED_AUTHORISATION_SOURCE: no trusted HUMAN authorisation source exists in this "
                     "installation; the executor stays blocked (no authorisation record is accepted or fabricated)")


class ExecutionContextError(ValueError):
    """The Execution Plan cannot be opened for execution (missing, damaged or no longer current); nothing runs."""


class ExecutionStopped(BaseException):
    """Stop requested: raised before the next solve or extraction starts (never caught as an ordinary error)."""


class ExecutionState(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
    REFUSED = "REFUSED"


# ----------------------------------------------------------------------------- the authorisation contract

@dataclass(frozen=True)
class ExecutionAuthorisation:
    """One HUMAN authorisation of one operation of one exact plan (valid only when a trusted authority attests it)."""

    operation: str
    authorisation_scope_hash: str
    campaign_hash: str
    manifest_hash: str
    budget: Mapping
    authorised_by: str
    attestation: str  # opaque; only the issuing trusted authority can check it
    schema: str = AUTHORISATION_SCHEMA

    def binding(self) -> dict:
        """Everything the attestation covers (all fields but the attestation itself)."""
        return {"schema": self.schema, "operation": self.operation,
                "authorisation_scope_hash": self.authorisation_scope_hash, "campaign_hash": self.campaign_hash,
                "manifest_hash": self.manifest_hash, "budget": json.loads(json.dumps(dict(self.budget))),
                "authorised_by": self.authorised_by}


class NoTrustedAuthority:
    """The production authority: no trusted HUMAN authorisation source exists, so nothing is ever attested."""

    name = "none"
    simulated = False
    available = False
    unavailable_reason = NO_TRUSTED_SOURCE

    def attests(self, authorisation: ExecutionAuthorisation) -> bool:
        return False

    def authorisation_for(self, context: "ExecutionContext", operation: str) -> Optional[ExecutionAuthorisation]:
        return None


PRODUCTION_AUTHORITY = NoTrustedAuthority()


def operation_budget(scope: Mapping, operation: str) -> dict:
    """Exactly the budget an authorisation of ``operation`` binds (from the plan's authorisation scope)."""
    operations = scope["operations"]
    if operation == ARCHIVE_EXTRACTION:
        return {"archive_extraction_jobs": list(operations["archive_extraction_jobs"]), "abaqus_solves": 0,
                "lm_evaluations": 0}
    if operation == CAMPAIGN_RUN:
        return {"max_new_abaqus_solves": operations["max_new_abaqus_solves"],
                "max_abaqus_python_extractions": operations["max_abaqus_python_extractions"],
                "lm_evaluation_budget": operations["lm_evaluation_budget"],
                "max_new_campaign_evaluations": operations["max_new_campaign_evaluations"],
                "new_initial_point_solves": list(operations["new_initial_point_solves"])}
    raise ValueError(f"unknown operation {operation!r}; the operations are {OPERATIONS}.")


# ----------------------------------------------------------------------------- the execution context

def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExecutionContextError(f"{path} cannot be read ({error}).") from error


@dataclass(frozen=True)
class ExecutionContext:
    work_directory: Path
    definition_path: Path
    definition_sha256: str
    definition: object
    reuse: object
    specimens: tuple
    manifest: Mapping
    manifest_hash: str
    operations: Mapping
    gates: tuple
    scope: Mapping
    repo_root: Path
    roots: Mapping  # the data stores plus the run store of the archive extractions (inside the plan folder)

    @property
    def campaign_hash(self) -> str:
        return self.definition.campaign_hash

    @property
    def scope_hash(self) -> str:
        return canonical_hash(self.scope)

    def rows(self) -> tuple:
        budgets = self.manifest["budgets"]
        rows = [("Plan", "Folder", str(self.work_directory), "OPENED"),
                ("Plan", "Campaign", f"{self.definition.campaign_id}; campaign hash {self.campaign_hash}; "
                                     f"definition {self.definition_path}", "CURRENT"),
                ("Plan", "Manifest hash", f"{self.manifest_hash} (re-planned now: identical)", "CURRENT"),
                ("Plan", "Authorisation scope", self.scope_hash, "CURRENT"),
                ("Sources", "Pre-run Validation", "Definition FORMALLY_VALID; Sources SHA256_VERIFIED (re-checked now)",
                 "CURRENT")]
        rows += [("Budget", "LM evaluations", f"{budgets['lm_evaluation_budget']} ({budgets['reused_initial_evaluations']} "
                                              f"initial reused; at most {budgets['max_new_campaign_evaluations']} new)",
                  "DECLARED"),
                 ("Budget", "Hard Abaqus solve budget", str(budgets["max_new_abaqus_solves"]), "DECLARED"),
                 ("Budget", "Archive extractions", str(budgets["archive_extractions"]), "DECLARED")]
        return tuple(rows)


def open_execution_context(work_directory, repo_root: Path, fixtures: ExperimentFixtureManifest,
                           roots: Optional[Mapping[str, Path]]) -> ExecutionContext:
    """Open an existing Execution Plan folder and re-check that it is still current (writes nothing)."""

    work = Path(work_directory).resolve()
    record = _read_json(work / PLAN_FILE)
    try:
        campaign_hash = record["definition"]["campaign_hash"]
        path, recorded_sha = Path(record["definition"]["path"]), record["definition"]["file_sha256"]
        recorded_manifest_hash, recorded_scope_hash = (record["manifest"]["manifest_hash"],
                                                       record["authorisation_scope_hash"])
    except (KeyError, TypeError) as error:
        raise ExecutionContextError(f"{work}: not an execution plan record ({error!r}).") from error
    problems = plan_set_problems(work, campaign_hash, ignore=RUN_ENTRIES)
    if problems:
        raise ExecutionContextError(f"{work} is not one complete, consistent execution plan: {'; '.join(problems)}.")
    try:
        sha = _sha256(path)
    except OSError as error:
        raise ExecutionContextError(f"the planned campaign definition {path} cannot be read ({error}).") from error
    if sha != recorded_sha:
        raise ExecutionContextError("STALE: the campaign definition file changed after the plan was prepared.")
    if roots is None:
        raise ExecutionContextError("the data stores are not configured; the sources cannot be re-checked.")
    validation = prerun_validation(path, repo_root, fixtures, roots)
    if (validation.sections["Definition"], validation.sections["Sources"]) != ("FORMALLY_VALID", "SHA256_VERIFIED"):
        raise ExecutionContextError(f"STALE: Pre-run Validation now gives Definition {validation.sections['Definition']}, "
                                    f"Sources {validation.sections['Sources']}.")
    try:
        definition = load_campaign_definition(path)
    except (OSError, ValueError, CampaignDefinitionError) as error:
        raise ExecutionContextError(f"load_campaign_definition refused the definition ({error}).") from error
    if definition.campaign_hash != campaign_hash:
        raise ExecutionContextError("STALE: the campaign hash differs from the plan's.")
    with tempfile.TemporaryDirectory(prefix="auto-id-recheck-") as scratch:
        try:
            reuse, specimens, manifest, manifest_hash = executor_module.prepare_campaign_plan(
                definition, Path(repo_root), fixtures, dict(roots), Path(scratch) / "jobs")
        except Exception as error:  # the existing planning sequence refuses: the plan is not executable as it stands
            raise ExecutionContextError(f"STALE: the existing planning sequence now refuses the campaign ({error}).") \
                from error
    if canonical_hash(_read_json(work / MANIFEST_FILE)) != recorded_manifest_hash or \
            manifest_hash != recorded_manifest_hash:
        raise ExecutionContextError(f"STALE: the sources or records now give manifest {manifest_hash[:12]}, the plan "
                                    f"records {str(recorded_manifest_hash)[:12]}; prepare a new plan.")
    operations = plan_operations(manifest)
    gates = plan_gates(operations)
    scope = authorisation_scope(definition, sha, manifest, manifest_hash, operations, gates)
    if canonical_hash(scope) != recorded_scope_hash:
        raise ExecutionContextError("STALE: the authorisation scope differs from the plan's.")
    run_roots = dict(roots)
    run_roots[executor_module.ARCHIVE_RUN_STORE] = work / "archive_reuse"
    return ExecutionContext(work, path, sha, definition, reuse, tuple(specimens), manifest, manifest_hash, operations,
                            gates, scope, Path(repo_root), run_roots)


def campaign_journals(context: ExecutionContext) -> list:
    """The campaign journals in the plan folder that belong to this campaign and manifest (read-only)."""

    found = []
    for path in sorted((context.work_directory / "campaign").glob("*/journal.json")):
        try:
            identity, _, _ = journal_document(json.loads(path.read_text(encoding="utf-8")), "campaign")
        except (OSError, ValueError, LMProvenanceRefusal):
            continue
        if identity.get("campaign_hash") == context.campaign_hash and \
                identity.get("manifest_hash") == context.manifest_hash:
            found.append(path)
    return found


# ----------------------------------------------------------------------------- the controller

@dataclass
class ExecutionOutcome:
    operation: str
    state: ExecutionState
    detail: str
    summary: Optional[Mapping] = None
    simulated: bool = False
    started: str = ""
    finished: str = ""
    labels: tuple = field(default_factory=tuple)


def _stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class GuardedExecutionController:
    """The one execution controller of the GUI and the CLI (see the module docstring)."""

    def __init__(self, context: ExecutionContext, authority=PRODUCTION_AUTHORITY, *, abaqus_command: str = "",
                 solve_executor_factory: Optional[Callable] = None,
                 extraction_executor_factory: Optional[Callable] = None,
                 recheck: Optional[Callable[[], ExecutionContext]] = None) -> None:
        self.context, self.authority, self.abaqus_command = context, authority, abaqus_command
        self._solve_factory, self._extraction_factory = solve_executor_factory, extraction_executor_factory
        self._recheck = recheck
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self.state, self.outcome, self.operation = ExecutionState.IDLE, None, None

    # -- authorisation -------------------------------------------------------------------------------------------

    def start_available(self) -> tuple:
        if not getattr(self.authority, "available", False):
            return False, getattr(self.authority, "unavailable_reason", NO_TRUSTED_SOURCE)
        return True, f"authority {self.authority.name}"

    def authorisation_problems(self, operation: str, authorisation, context: Optional[ExecutionContext] = None) -> list:
        context = context or self.context
        if operation not in OPERATIONS:
            return [f"unknown operation {operation!r}"]
        if not getattr(self.authority, "available", False):
            return [getattr(self.authority, "unavailable_reason", NO_TRUSTED_SOURCE)]
        if not isinstance(authorisation, ExecutionAuthorisation):
            return [f"a {type(authorisation).__name__} is not an execution authorisation (plain JSON, GUI text, a typed "
                    "hash, decision / provenance text or an M7 authorisation never is one)"]
        expected = {"schema": AUTHORISATION_SCHEMA, "operation": operation,
                    "authorisation_scope_hash": context.scope_hash, "campaign_hash": context.campaign_hash,
                    "manifest_hash": context.manifest_hash,
                    "budget": json.loads(json.dumps(operation_budget(context.scope, operation)))}
        binding = authorisation.binding()
        problems = [f"{key}: the authorisation names {str(binding.get(key))[:80]!r}, this plan needs "
                    f"{str(value)[:80]!r}" for key, value in expected.items() if binding.get(key) != value]
        if not problems and not self.authority.attests(authorisation):
            problems.append(f"the authority {self.authority.name} does not attest this authorisation")
        return problems

    # -- execution -----------------------------------------------------------------------------------------------

    def _guarded(self, executor: Callable) -> Callable:
        def run(*args, **kwargs):
            if self._stop.is_set():
                raise ExecutionStopped("stop requested: the next solve or extraction was not started.")
            return executor(*args, **kwargs)
        return run

    def _log(self, entry: Mapping) -> None:
        path = self.context.work_directory / EXECUTION_LOG
        try:
            document = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        except (OSError, ValueError):
            document = None
        if not isinstance(document, dict) or document.get("schema") != EXECUTION_LOG_SCHEMA:
            document = {"schema": EXECUTION_LOG_SCHEMA, "labels": list(LOG_LABELS), "attempts": []}
        document["attempts"].append(json.loads(json.dumps(entry, default=str)))
        temporary = path.with_name(f".{path.name}.partial")
        temporary.write_text(json.dumps(document, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)

    def execute(self, operation: str, authorisation) -> ExecutionOutcome:
        """Run one authorised operation synchronously (refused with ``ExecutionNotAuthorised`` before anything runs)."""

        problems = self.authorisation_problems(operation, authorisation)
        if problems:
            raise ExecutionNotAuthorised(f"{operation} {NOT_AUTHORISED}: " + "; ".join(problems) + ". Nothing executed.")
        if self._recheck is not None:  # the plan must still be current now, and the authorisation bound to it
            try:
                fresh = self._recheck()
            except ExecutionContextError as error:
                raise ExecutionNotAuthorised(f"{operation} refused: {error} Nothing executed.") from error
            problems = self.authorisation_problems(operation, authorisation, fresh)
            if problems:
                raise ExecutionNotAuthorised(f"{operation} refused: the plan changed after authorisation ("
                                             + "; ".join(problems) + "). Nothing executed.")
            self.context = fresh
        simulated = bool(getattr(self.authority, "simulated", False))
        outcome = ExecutionOutcome(operation, ExecutionState.RUNNING, "running", simulated=simulated, started=_stamp(),
                                   labels=(SIMULATED,) if simulated else ())
        entry = {"operation": operation, "authorisation": authorisation.binding(), "authority": self.authority.name,
                 "simulated": simulated, "started": outcome.started}
        try:
            outcome.summary = self._run(operation)
            outcome.state, outcome.detail = ExecutionState.COMPLETED, "completed"
        except ExecutionStopped as stopped:
            outcome.state, outcome.detail = ExecutionState.STOPPED, str(stopped)
        except KeyboardInterrupt as interrupted:  # an interrupted executor; the journals keep what was written
            outcome.state, outcome.detail = ExecutionState.FAILED, f"interrupted ({interrupted})"
        except Exception as error:  # an executor or evidence error; never repaired, the journals stay as written
            outcome.state, outcome.detail = ExecutionState.FAILED, f"{type(error).__name__}: {error}"
        outcome.finished = _stamp()
        self._log(dict(entry, state=outcome.state.value, detail=outcome.detail, finished=outcome.finished,
                       summary=outcome.summary, labels=list(outcome.labels)))
        return outcome

    def _run(self, operation: str) -> dict:
        context = self.context
        if operation == ARCHIVE_EXTRACTION:
            if self._extraction_factory is None:
                raise RuntimeError("no extraction executor configured.")
            records = executor_module.extract_archived_odbs(
                context.reuse, context.specimens, context.work_directory, context.roots,
                self._guarded(self._extraction_factory()), context.manifest_hash, context.manifest_hash)
            return {"archive_extractions": {job: record.content_sha256 for job, record in sorted(records.items())}}
        if self._solve_factory is None or self._extraction_factory is None:
            raise RuntimeError("no solve / extraction executor configured.")
        extracted = executor_module.journalled_archive_records(context.reuse, context.work_directory,
                                                               context.manifest_hash)
        config = executor_module.CampaignRunConfig(
            context.work_directory, context.roots, self.abaqus_command, self._guarded(self._solve_factory()),
            self._guarded(self._extraction_factory()),
            executor_module.reused_pack_records(context.reuse, context.repo_root, extracted, context.specimens),
            context.manifest_hash)
        campaign = executor_module.CampaignRun(context.definition, context.specimens, context.manifest_hash, config)
        summary = campaign.run()
        return dict(summary, journal=str(campaign.run_dir / "journal.json"))

    # -- background ----------------------------------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, operation: str, authorisation, on_done: Optional[Callable[[ExecutionOutcome], None]] = None):
        """Check the authorisation now, then run the operation in a worker thread (the GUI stays responsive)."""

        with self._lock:
            if self.running:
                raise RuntimeError("an operation is already running.")
            problems = self.authorisation_problems(operation, authorisation)
            if problems:
                self.state = ExecutionState.REFUSED
                self.outcome = ExecutionOutcome(operation, ExecutionState.REFUSED, "; ".join(problems))
                raise ExecutionNotAuthorised(f"{operation} {NOT_AUTHORISED}: " + "; ".join(problems)
                                             + ". Nothing executed.")
            self._stop.clear()
            self.state, self.operation = ExecutionState.RUNNING, operation

            def work():
                try:
                    outcome = self.execute(operation, authorisation)
                except ExecutionNotAuthorised as refusal:
                    outcome = ExecutionOutcome(operation, ExecutionState.REFUSED, str(refusal))
                self.outcome, self.state = outcome, outcome.state
                if on_done is not None:
                    on_done(outcome)

            self._thread = threading.Thread(target=work, name=f"auto-id-{operation}", daemon=True)
            self._thread.start()
            return self._thread

    def stop(self) -> None:
        """Request a stop before the next solve or extraction (a running process is not killed)."""
        self._stop.set()

    def wait(self, timeout: Optional[float] = None) -> Optional[ExecutionOutcome]:
        if self._thread is not None:
            self._thread.join(timeout)
        return self.outcome

    def gate_rows(self) -> tuple:
        available, reason = self.start_available()
        return tuple((gate["gate"], gate["scope"], json.dumps(operation_budget(self.context.scope, gate["gate"])),
                      "START_ENABLED" if available else f"{NOT_AUTHORISED}: {reason}") for gate in self.context.gates)


def execution_provenance(journal_path) -> Optional[str]:
    """``SIMULATED_...`` when the run root of this campaign journal holds any attempt attested by a simulated authority
    (such a folder is test material, never a material result); ``None`` otherwise (read-only)."""

    try:
        root = Path(journal_path).resolve().parents[2]  # <run root>/campaign/<run hash>/journal.json
        document = json.loads((root / EXECUTION_LOG).read_text(encoding="utf-8"))
        attempts = document.get("attempts") if document.get("schema") == EXECUTION_LOG_SCHEMA else None
    except (OSError, IndexError, ValueError, AttributeError):
        return None
    return SIMULATED if any(isinstance(a, Mapping) and a.get("simulated") for a in attempts or ()) else None


def outcome_text(outcome: Optional[ExecutionOutcome]) -> str:
    if outcome is None:
        return "No execution attempted."
    text = f"{outcome.operation}: {outcome.state.value} — {outcome.detail}"
    if outcome.simulated:
        text += f" [{SIMULATED}]"
    if outcome.summary and "status" in outcome.summary:
        text += f"; LM status {outcome.summary['status']}, {outcome.summary.get('abaqus_solves_used')} solves used"
    return text


__all__ = ["ARCHIVE_EXTRACTION", "CAMPAIGN_RUN", "ExecutionAuthorisation", "NoTrustedAuthority", "PRODUCTION_AUTHORITY",
           "ExecutionContext", "ExecutionContextError", "ExecutionOutcome", "ExecutionState", "ExecutionStopped",
           "GuardedExecutionController", "campaign_journals", "execution_provenance", "open_execution_context",
           "operation_budget", "outcome_text"]
