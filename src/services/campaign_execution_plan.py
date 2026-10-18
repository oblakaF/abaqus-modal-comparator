"""Auto-ID Execution Plan of a saved campaign definition — Auto-ID M8-D2h (a plan only; nothing is executed or authorised).

``prepare_execution_plan`` connects a SPEC v1.2 campaign definition saved by M8-D2g to the existing Auto-ID executor
without running it:

1. **Re-check** — the M8-D2g Pre-run Validation of the file: Definition must be ``FORMALLY_VALID`` (SPEC v1.2; the
   archived M7 v1 campaigns are never planned here) and Sources ``SHA256_VERIFIED`` (the current governed records
   reproduce the definition and every pinned file is verified now); otherwise the plan is refused.
2. **Governed loader** — ``load_campaign_definition``; its campaign hash must be the one Pre-run validated.
3. **Existing planning sequence** — ``identification_campaign_run.prepare_campaign_plan``, the one the M7 CLI uses:
   the run-type / question gate (RUN_B without its own gate, calibration BLOCKED), the definition's governed
   archive-reuse plan, ``prepare_campaign_specimens`` (each specimen frozen on its active chain: exactly the accepted
   rows or STOP) and ``prepare_run_manifest`` (initial points, archived reuse verified, budgets, manifest hash).
4. **Cross-checks** — the prepared FIT / HOLDOUT rows equal the definition's (which Pre-run proved equal to the accepted
   strict freezes) and the budgets are consistent; the definition file must be unchanged from step 1 to publication.
5. **Writing** — only into the chosen working directory (the future run root), never the repository, a data store or a
   folder that holds other files: ``run_manifest.json`` (the manifest exactly as the CLI writes it), ``plan_jobs/``
   (the rendered initial-point INPs) and ``execution_plan.json`` (labelled ``NOT_GOVERNED_EVIDENCE`` /
   ``AUTHORISES_NOTHING``). A refusal publishes nothing.

The plan distinguishes ready archived shape packs, archived ODBs that need a gated extraction and new Abaqus solves,
and names the separate HUMAN gates they need.  ``authorisation_scope`` is what a later authorisation must bind exactly
(campaign hash, definition file, manifest hash, operations and budgets); an M7 authorisation never carries over.

``request_execution`` is the entry point a later, separately authorised stage will pass through.  In M8-D2h no
authorisation exists: every request — with nothing, a typed manifest hash, a decision or provenance text, a matching
archived hash or anything else — is refused there, before any executor, extraction, run journal or LM is touched.

A successful plan is not scientific readiness and not a right to run: numerical identifiability of the campaign stays
NOT_ASSESSED until a real journalled result exists.  Nothing here runs Abaqus, Abaqus Python, FE or LM.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Iterable, Mapping, Optional
import uuid

from domain.campaign_definition import (
    CalibrationNotImplementedRefusal,
    CampaignDefinitionError,
    RunGateRefusal,
    load_campaign_definition,
)
from domain.experiment_fixture import ExperimentFixtureManifest
from domain.identification_run import canonical_hash

from .identification_campaign_run import ArchiveReuseRefusal, CampaignError, ObservationSetMismatch, prepare_campaign_plan
from .prerun_validation import PrerunValidation, prerun_validation

PLAN_SCHEMA = "auto-id/execution-plan/v1"
SCOPE_SCHEMA = "auto-id/execution-authorisation-scope/v1"
PLAN_LABELS = ("EXECUTION_PLAN", "NOT_GOVERNED_EVIDENCE", "AUTHORISES_NOTHING")
NOT_AUTHORISED = "NOT_AUTHORISED"
MANIFEST_FILE, PLAN_FILE, JOBS_FOLDER = "run_manifest.json", "execution_plan.json", "plan_jobs"
SOURCE_STATUS = {"archived-validated-pack": "ARCHIVED_SHAPE_PACK_READY",
                 "archived-odb-extraction": "ARCHIVED_ODB_NEEDS_EXTRACTION", "NEW_SOLVE": "NEW_ABAQUS_SOLVE"}
GATE_ARCHIVE_EXTRACTION = "ARCHIVE_EXTRACTION"
GATE_CAMPAIGN_RUN = "CAMPAIGN_RUN"
STATEMENT = ("An execution plan is not scientific readiness and not an execution authorisation: execution status "
             "NOT_AUTHORISED; every Abaqus Python extraction, Abaqus solve and LM evaluation needs its own HUMAN gate "
             "bound to this exact scope; numerical identifiability NOT_ASSESSED until a real journalled result; "
             "production calibration BLOCKED / NOT_AUTHORISED; M7 authorisations never carry over")


class ExecutionPlanError(ValueError):
    """The definition cannot be planned (or the plan cannot be written); nothing is published."""


class ExecutionNotAuthorised(Exception):
    """Execution is not authorised; nothing is executed, extracted, journalled or optimised.

    Not a ValueError, so generic fallback handlers never swallow it.
    """


@dataclass(frozen=True)
class ExecutionPlan:
    definition_path: Path
    definition_sha256: str
    campaign_id: str
    campaign_hash: str
    scientific_question: str
    run_type: str
    prerun: PrerunValidation
    manifest: Mapping
    manifest_hash: str
    work_directory: Path
    operations: Mapping
    gates: tuple
    authorisation_scope: Mapping
    rows: tuple  # (section, item, detail, status) for the GUI table

    @property
    def authorisation_scope_hash(self) -> str:
        return canonical_hash(self.authorisation_scope)

    @property
    def execution_status(self) -> str:
        return NOT_AUTHORISED

    @property
    def manifest_path(self) -> Path:
        return self.work_directory / MANIFEST_FILE

    @property
    def plan_path(self) -> Path:
        return self.work_directory / PLAN_FILE

    def summary(self) -> str:
        budgets = self.manifest["budgets"]
        return (f"Execution plan of {self.campaign_id} (campaign hash {self.campaign_hash}): manifest hash "
                f"{self.manifest_hash}; {self.operations['archived_packs_ready']} archived shape pack(s) ready, "
                f"{self.operations['archive_extractions']} archived ODB extraction(s), "
                f"{self.operations['new_initial_point_solves']} new solve(s) for the initial points, at most "
                f"{budgets['max_new_abaqus_solves']} new Abaqus solves and {budgets['lm_evaluation_budget']} LM "
                f"evaluations. Written to {self.work_directory}. Execution status: {NOT_AUTHORISED}.")

    def record(self) -> dict:
        """The plan sidecar ``execution_plan.json`` (diagnostic, never governed evidence, authorises nothing)."""
        return {"schema": PLAN_SCHEMA, "labels": list(PLAN_LABELS), "execution_status": NOT_AUTHORISED,
                "definition": {"path": str(self.definition_path), "file_sha256": self.definition_sha256,
                               "campaign_id": self.campaign_id, "campaign_hash": self.campaign_hash,
                               "scientific_question": self.scientific_question, "run_type": self.run_type},
                "prerun_validation": dict(self.prerun.sections),
                "manifest": {"file": MANIFEST_FILE, "manifest_hash": self.manifest_hash},
                "operations": dict(self.operations), "gates": [dict(g) for g in self.gates],
                "authorisation_scope": dict(self.authorisation_scope),
                "authorisation_scope_hash": self.authorisation_scope_hash,
                "numerical_identifiability": "NOT_ASSESSED", "statement": STATEMENT}


# ----------------------------------------------------------------------------- the working directory

def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_work_directory(directory, protected_roots: Iterable, campaign_hash: str) -> Path:
    """A permitted working directory: an existing folder outside (and not above) the repository, every data store and
    every other protected root, which is empty or holds an earlier plan of the same campaign."""

    if directory is None or not str(directory).strip():
        raise ExecutionPlanError("no working directory selected.")
    target = Path(directory).resolve()
    if not target.is_dir():
        raise ExecutionPlanError(f"the working directory {target} does not exist.")
    for root in protected_roots:
        if root is None:
            raise ExecutionPlanError("a protected root could not be determined; nothing is written.")
        root = Path(root).resolve()
        if _inside(target, root) or _inside(root, target):
            raise ExecutionPlanError(f"{target} is inside or above the protected {root} (repository, data store or "
                                     "source folder); an execution plan is written elsewhere.")
    entries = [p for p in target.iterdir() if not p.name.startswith(".plan-staging-")]
    if entries:
        plan = target / PLAN_FILE
        try:
            earlier = json.loads(plan.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            earlier = None
        if not isinstance(earlier, dict) or earlier.get("schema") != PLAN_SCHEMA:
            raise ExecutionPlanError(f"{target} is not empty and holds no execution plan; choose an empty working "
                                     "directory (other files are never mixed with a plan).")
        if (earlier.get("definition") or {}).get("campaign_hash") != campaign_hash:
            raise ExecutionPlanError(f"{target} holds the execution plan of another campaign; choose a new working "
                                     "directory.")
    return target


def _atomic_write(target: Path, data: bytes, verify=None) -> None:
    temporary = None
    try:
        handle, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".partial", dir=target.parent)
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if verify is not None:
            verify(Path(temporary))
        os.replace(temporary, target)
        temporary = None
    except OSError as error:
        raise ExecutionPlanError(f"{target}: {error}") from error
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _tree(folder: Path) -> dict:
    return {p.relative_to(folder).as_posix(): _sha256(p) for p in sorted(folder.rglob("*")) if p.is_file()}


# ----------------------------------------------------------------------------- the plan

def _row_roles(rows) -> list:
    return [(r["row_id"], r["experimental_mode"], r["fe_mode"], r["role"]) for r in rows]


def _cross_check(definition, manifest: Mapping) -> list:
    problems = []
    prepared = {item["label"]: _row_roles(item["rows"]) for item in manifest["specimens"]}
    for spec in definition.specimens:
        declared = [(r.row_id, r.experimental_mode, r.fe_mode, r.role) for r in spec.rows]
        if prepared.get(spec.label) != declared:
            problems.append(f"{spec.label}: prepared rows {prepared.get(spec.label)} != definition rows {declared}")
    if list(prepared) != [s.label for s in definition.specimens]:
        problems.append("the prepared specimens are not the definition's, in definition order")
    budgets = manifest["budgets"]
    if budgets["max_new_campaign_evaluations"] < 0:
        problems.append(f"the LM evaluation budget {budgets['lm_evaluation_budget']} is smaller than the "
                        f"{budgets['reused_initial_evaluations']} initial evaluations")
    if len(manifest["new_solve_initial_points"]) > budgets["max_new_abaqus_solves"]:
        problems.append("the initial points need more new solves than the hard solve budget")
    return problems


def _operations(manifest: Mapping) -> dict:
    budgets, initial = manifest["budgets"], manifest["initial_points"]
    specimens = len(manifest["specimens"])
    later = budgets["max_new_campaign_evaluations"] * specimens  # every later LM evaluation solves each specimen anew
    rows = [r for item in manifest["specimens"] for r in item["rows"]]
    return {
        "specimens": specimens,
        "fit_rows": sum(r["role"] == "FIT" for r in rows), "holdout_rows": sum(r["role"] == "HOLDOUT" for r in rows),
        "initial_points": len(initial),
        "archived_packs_ready": sum(p["source"] == "archived-validated-pack" for p in initial),
        "archive_extractions": len(manifest["extraction_only_jobs"]),
        "archive_extraction_jobs": [job["job_name"] for job in manifest["extraction_only_jobs"]],
        "new_initial_point_solves": len(manifest["new_solve_initial_points"]),
        "max_new_abaqus_solves": budgets["max_new_abaqus_solves"],
        "solves_the_lm_budget_could_need": later,
        "solve_budget_may_stop_the_lm": later > budgets["max_new_abaqus_solves"],
        "lm_evaluation_budget": budgets["lm_evaluation_budget"],
        "reused_initial_evaluations": budgets["reused_initial_evaluations"],
        "max_new_campaign_evaluations": budgets["max_new_campaign_evaluations"],
        "max_abaqus_python_extractions": budgets["max_abaqus_python_extractions"],
    }


def _gates(operations: Mapping) -> tuple:
    gates = []
    if operations["archive_extractions"]:
        gates.append({"gate": GATE_ARCHIVE_EXTRACTION, "status": NOT_AUTHORISED,
                      "scope": f"Abaqus Python, extraction only, of {operations['archive_extractions']} archived ODB(s) "
                               f"{operations['archive_extraction_jobs']} on run-store copies (0 solves); the "
                               "extracted frequencies must equal the accepted archived ones"})
    gates.append({"gate": GATE_CAMPAIGN_RUN, "status": NOT_AUTHORISED,
                  "scope": f"bounded M4.8 LM of at most {operations['lm_evaluation_budget']} campaign evaluations "
                           f"({operations['reused_initial_evaluations']} initial ones reused) with at most "
                           f"{operations['max_new_abaqus_solves']} new Abaqus solves (hard cap, no extension, no "
                           "automatic retry); resumable"})
    return tuple(gates)


def authorisation_scope(definition, definition_sha256: str, manifest: Mapping, manifest_hash: str,
                        operations: Mapping, gates) -> dict:
    """What a later authorisation must bind exactly; anything else is another plan."""
    return {"schema": SCOPE_SCHEMA, "campaign_id": definition.campaign_id, "campaign_hash": definition.campaign_hash,
            "definition_file_sha256": definition_sha256, "scientific_question": definition.scientific_question,
            "run_type": definition.run_type, "manifest_hash": manifest_hash,
            "archive_reuse_hash": manifest["archive_reuse_hash"],
            "operations": {"archive_extraction_jobs": list(operations["archive_extraction_jobs"]),
                           "new_initial_point_solves": list(manifest["new_solve_initial_points"]),
                           "max_new_abaqus_solves": operations["max_new_abaqus_solves"],
                           "max_abaqus_python_extractions": operations["max_abaqus_python_extractions"],
                           "lm_evaluation_budget": operations["lm_evaluation_budget"],
                           "max_new_campaign_evaluations": operations["max_new_campaign_evaluations"]},
            "gates": [g["gate"] for g in gates]}


def _plan_rows(definition, path: Path, sha: str, prerun: PrerunValidation, manifest: Mapping, manifest_hash: str,
               operations: Mapping, gates, scope_hash: str, work: Path) -> tuple:
    rows = [("Campaign", "Definition", f"{path}; {definition.campaign_id}; {definition.schema}; "
                                       f"{definition.scientific_question}; {definition.run_type}; file SHA-256 {sha}",
             "SELECTED"),
            ("Campaign", "Campaign hash", definition.campaign_hash, "FORMALLY_VALID")]
    rows += [("Pre-run Validation", name, "M8-D2g Pre-run Validation, run again now", status)
             for name, status in prerun.sections.items()]
    rows += [("Manifest", "Manifest hash", f"{manifest_hash} (prepare_run_manifest)", "PREPARED"),
             ("Manifest", "Run manifest", str(work / MANIFEST_FILE), "WRITTEN"),
             ("Manifest", "Archive-reuse plan", f"{definition.archive_reuse}; reuse hash "
                                                f"{manifest['archive_reuse_hash']}", "VERIFIED")]
    for item in manifest["specimens"]:
        fit = [r["row_id"] for r in item["rows"] if r["role"] == "FIT"]
        holdout = [r["row_id"] for r in item["rows"] if r["role"] == "HOLDOUT"]
        rows.append(("Observations", f"{item['label']} FIT / HOLDOUT",
                     f"FIT {', '.join(fit)}; HOLDOUT {', '.join(holdout) or '-'}; observation hash "
                     f"{item['observation_hash'][:12]}; registration {item['registration_hash'][:12]} (prepared on "
                     "the active chain = definition rows = accepted strict freeze)", "MATCHES_FROZEN_RECORDS"))
    extraction = {(j["specimen"], j["job_name"]): j for j in manifest["extraction_only_jobs"]}
    for point in manifest["initial_points"]:
        values = ", ".join(f"{k} {v:g}" for k, v in point["parameters"].items())
        detail = f"{point['job_name']} ({values})"
        odb = extraction.get((point["specimen"], point["job_name"]))
        if odb is not None:
            detail += (f"; archived ODB {odb['odb']['store']}/{odb['odb']['relative_path']} SHA-256 "
                       f"{odb['odb']['sha256'][:12]} verified now")
        elif point["source"] == "archived-validated-pack":
            detail += "; validated governed shape pack (no solve, no extraction)"
        rows.append(("Initial state", f"{point['specimen']} {point['point']}", detail,
                     SOURCE_STATUS.get(point["source"], point["source"])))
    budgets = manifest["budgets"]
    rows += [("Budget", "LM evaluation budget", f"{budgets['lm_evaluation_budget']} campaign evaluations "
                                                f"({budgets['reused_initial_evaluations']} initial ones reused; at most "
                                                f"{budgets['max_new_campaign_evaluations']} new)", "DECLARED"),
             ("Budget", "Hard Abaqus solve budget", f"{budgets['max_new_abaqus_solves']} new solves (no extension)",
              "DECLARED"),
             ("Budget", "Abaqus Python extractions", f"at most {budgets['max_abaqus_python_extractions']} "
                                                     f"({budgets['archive_extractions']} archived + one per new solve)",
              "DECLARED")]
    later = (f"at most {operations['solves_the_lm_budget_could_need']} later "
             f"({operations['max_new_campaign_evaluations']} LM evaluations x {operations['specimens']} specimens; "
             f"hard cap {operations['max_new_abaqus_solves']}"
             + ("; the solve budget may stop the LM first (SOLVE_BUDGET)" if operations["solve_budget_may_stop_the_lm"]
                else "") + ")")
    rows += [("Operations", "Archived shape packs reused", f"{operations['archived_packs_ready']} of "
                                                           f"{operations['initial_points']} initial points",
              "NO_OPERATION_NEEDED"),
             ("Operations", "Archived ODB extractions", f"{operations['archive_extractions']} "
                                                        f"{operations['archive_extraction_jobs']}",
              "REQUIRES_HUMAN_GATE" if operations["archive_extractions"] else "NONE"),
             ("Operations", "New Abaqus solves", f"{operations['new_initial_point_solves']} for the initial points; "
                                                 + later, "REQUIRES_HUMAN_GATE"),
             ("Operations", "LM", f"bounded M4.8 LM, at most {operations['lm_evaluation_budget']} evaluations",
              "REQUIRES_HUMAN_GATE")]
    rows += [("Execution", f"Gate {g['gate']}", g["scope"], g["status"]) for g in gates]
    rows += [("Execution", "Authorisation scope", f"{scope_hash}: campaign hash, definition file, manifest hash, "
                                                  "operations and budgets; an M7 authorisation never carries over",
              NOT_AUTHORISED),
             ("Execution", "Execution status", "no authorisation exists in M8-D2h; Start is refused before any "
                                               "executor, extraction, run journal or LM", NOT_AUTHORISED),
             ("Scientific readiness", "Numerical identifiability", "not assessed until a real journalled result; a "
                                                                   "plan is not scientific readiness", "NOT_ASSESSED")]
    return tuple(rows)


def prepare_execution_plan(definition_path, work_directory, repo_root: Path, fixtures: ExperimentFixtureManifest,
                           roots: Optional[Mapping[str, Path]], protected_roots: Iterable) -> ExecutionPlan:
    """Re-check a saved definition, prepare it with the existing planning sequence and write the plan (no execution)."""

    path = Path(definition_path).resolve()
    try:
        sha = _sha256(path)
    except OSError as error:
        raise ExecutionPlanError(f"the campaign definition cannot be read: {error}") from error
    prerun = prerun_validation(path, repo_root, fixtures, roots)
    sections = prerun.sections
    if sections["Definition"] != "FORMALLY_VALID":
        raise ExecutionPlanError(f"Pre-run Validation: Definition {sections['Definition']} (only a valid SPEC v1.2 "
                                 "campaign definition is planned; archived M7 campaigns are never substituted); "
                                 "nothing written.")
    if sections["Sources"] != "SHA256_VERIFIED":
        reasons = "; ".join(f"{r[1]}: {r[2]}" for r in prerun.rows if r[0] == "Sources" and r[3] not in
                            ("SHA256_VERIFIED", "IDENTITIES_MATCH"))
        raise ExecutionPlanError(f"Pre-run Validation: Sources {sections['Sources']} ({reasons}); nothing written.")
    try:
        definition = load_campaign_definition(path)
    except (OSError, ValueError, CampaignDefinitionError) as error:
        raise ExecutionPlanError(f"load_campaign_definition refused the definition: {error}") from error
    if definition.campaign_hash != prerun.campaign_hash:
        raise ExecutionPlanError("the definition changed during Pre-run Validation; nothing written.")
    work = check_work_directory(work_directory, protected_roots, definition.campaign_hash)
    staging = work / f".plan-staging-{uuid.uuid4().hex}"
    try:
        staging.mkdir()
        try:
            _, _, manifest, manifest_hash = prepare_campaign_plan(definition, Path(repo_root), fixtures, dict(roots),
                                                                  staging / JOBS_FOLDER)
        except CalibrationNotImplementedRefusal as refusal:
            raise ExecutionPlanError(f"BLOCKED: {refusal}") from refusal
        except RunGateRefusal as refusal:
            raise ExecutionPlanError(f"refused by the run-type gate: {refusal}") from refusal
        except (CampaignError, ObservationSetMismatch, ArchiveReuseRefusal, CampaignDefinitionError, KeyError,
                OSError, ValueError) as error:
            raise ExecutionPlanError(f"the existing planning sequence refused the campaign: {error}") from error
        problems = _cross_check(definition, manifest)
        if problems:
            raise ExecutionPlanError("the prepared plan does not match the definition: " + "; ".join(problems))
        operations = _operations(manifest)
        gates = _gates(operations)
        scope = authorisation_scope(definition, sha, manifest, manifest_hash, operations, gates)
        plan = ExecutionPlan(path, sha, definition.campaign_id, definition.campaign_hash,
                             definition.scientific_question, definition.run_type, prerun, manifest, manifest_hash,
                             work, operations, gates, scope,
                             _plan_rows(definition, path, sha, prerun, manifest, manifest_hash, operations, gates,
                                        canonical_hash(scope), work))
        if _sha256(path) != sha:
            raise ExecutionPlanError("the campaign definition file changed while the plan was prepared; nothing "
                                     "written.")
        _publish(plan, staging)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return plan


def _publish(plan: ExecutionPlan, staging: Path) -> None:
    jobs, staged = plan.work_directory / JOBS_FOLDER, staging / JOBS_FOLDER
    if jobs.exists():
        if _tree(jobs) != _tree(staged):
            raise ExecutionPlanError(f"{jobs} holds other initial-point jobs; nothing replaced or written.")
    else:
        os.replace(staged, jobs)

    def verify(temporary: Path) -> None:
        if canonical_hash(json.loads(temporary.read_text(encoding="utf-8"))) != plan.manifest_hash:
            raise ExecutionPlanError("the written run manifest re-reads with another manifest hash; nothing "
                                     "published.")

    _atomic_write(plan.manifest_path, json.dumps(plan.manifest, indent=1).encode("utf-8"), verify)
    _atomic_write(plan.plan_path, (json.dumps(plan.record(), indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


# ----------------------------------------------------------------------------- staleness and the execution entry point

def plan_problems(plan: Optional[ExecutionPlan]) -> list:
    """Why a prepared plan is no longer current (the definition, its manifest or its record changed); [] if current."""

    if plan is None:
        return ["no execution plan prepared"]
    problems = []
    try:
        if _sha256(plan.definition_path) != plan.definition_sha256:
            problems.append("the campaign definition file changed after the plan was prepared")
        elif load_campaign_definition(plan.definition_path).campaign_hash != plan.campaign_hash:
            problems.append("the campaign hash changed after the plan was prepared")
    except (OSError, ValueError, CampaignDefinitionError) as error:
        problems.append(f"the campaign definition cannot be re-read: {error}")
    try:
        if canonical_hash(json.loads(plan.manifest_path.read_text(encoding="utf-8"))) != plan.manifest_hash:
            problems.append("the run manifest in the working directory changed")
        if json.loads(plan.plan_path.read_text(encoding="utf-8")) != json.loads(json.dumps(plan.record())):
            problems.append("the execution plan record in the working directory changed")
    except (OSError, ValueError) as error:
        problems.append(f"the plan files cannot be re-read: {error}")
    return problems


def request_execution(plan: Optional[ExecutionPlan], authorisation: object = None):
    """The entry point a later, separately authorised stage will use to start an execution plan.

    M8-D2h has no authorisation: this always raises ``ExecutionNotAuthorised`` before any executor, archive extraction,
    run journal or LM is touched.  A typed manifest or campaign hash, a decision or provenance text, a matching archived
    (M7) hash or any other value is never an authorisation.
    """

    reasons = ["no execution authorisation exists in M8-D2h"]
    if authorisation is not None:
        reasons.append(f"the given {type(authorisation).__name__} is not an authorisation (a manifest hash, campaign "
                       "hash, decision or provenance text or an archived M7 authorisation never is one)")
    if plan is None:
        reasons.append("no execution plan prepared")
    else:
        reasons += plan_problems(plan)
        reasons.append(f"a later authorisation must bind exactly scope {plan.authorisation_scope_hash} (campaign hash "
                       f"{plan.campaign_hash[:12]}, manifest hash {plan.manifest_hash[:12]}, operations and budgets)")
    raise ExecutionNotAuthorised(f"Execution status {NOT_AUTHORISED}: " + "; ".join(reasons) + ". Nothing executed.")


__all__ = ["ExecutionPlan", "ExecutionPlanError", "ExecutionNotAuthorised", "prepare_execution_plan",
           "check_work_directory", "plan_problems", "request_execution", "authorisation_scope", "NOT_AUTHORISED"]
