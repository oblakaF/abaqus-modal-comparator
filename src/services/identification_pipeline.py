"""Resumable identification pipeline — Auto-ID M4.6 (approved design, M4_DECISION_RECORD.md §6).

One identification evaluation (the residual function of the M4.8 bounded LM loop):

    candidate (exact parameters)
      → M3 forward job (``prepare_forward_job``: content-addressed INP; M3 contract unchanged)
      → FE shapes: a validated archived pack (reuse), a journalled solve + pack, or a new solve
        (``forward_solver``) + validated extraction (``shape_extraction``)
      → FE state → FE-to-FE tracking of the frozen rows (M4.5; refusal on identity loss)
      → whitened log-frequency residuals (M4.7)

Run identity (``run_hash``) binds the forward model, solver profile, frozen observation set,
objective design, pairing policy, LM settings, bounds, start point, extraction expectation and
archived packs.  The journal is atomic and hash-chained; every evaluation is journalled once
and replayed on resume (no duplicate evaluations or solves).  Identification evaluations and
actual Abaqus solves are counted separately.  Nothing is identified by path or mtime.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from pathlib import Path
import uuid
from typing import Any, Callable, Mapping, Optional

import numpy as np

from domain.forward_model_manifest import BoundForwardModel, ForwardCandidate
from domain.frozen_observations import FrozenObservationSet
from domain.identification_pairing_policy import IdentificationPairingPolicy
from domain.identification_run import RunIdentityError, RunJournal, RunLock, SolverProfile, canonical_hash

from .branch_tracker import BranchTrackingRefusal, FEModalState, RefusalKind, track_branches
from .fe_shape_pack import FEShapePack, ShapePackRecord, load_shape_pack
from .forward_builder import prepare_forward_job, read_reference_input
from .forward_solver import SolveExecutor, SolveFailure, solve_forward_job, solve_hash, verify_solve
from .identification_objective import ObjectiveDesign, evaluate_objective
from .identification_step import LMResult, LMSettings, ParameterBounds, run_bounded_lm
from .shape_extraction import ExtractionExecutor, ExtractionExpectation, extract_shape_pack, load_run_pack


PIPELINE_SCHEMA = "auto-id/identification-pipeline/v1"


@dataclass(frozen=True)
class PipelineConfig:
    run_root: Path
    model: BoundForwardModel
    profile: SolverProfile
    frozen: FrozenObservationSet
    design: ObjectiveDesign
    policy: IdentificationPairingPolicy
    settings: LMSettings
    bounds: ParameterBounds
    start: Mapping[str, float]
    expectation: ExtractionExpectation
    roots: Mapping[str, Path]  # data stores (reference INP, archived packs, solver scratch)
    abaqus_command: str  # machine-specific; not part of the run identity
    solve_executor: SolveExecutor
    extraction_executor: ExtractionExecutor
    archived_packs: Mapping[str, ShapePackRecord] = field(default_factory=dict)  # job_name → validated record
    extra_identity: Mapping[str, Any] = field(default_factory=dict)  # e.g. the twin's noise seed
    retry_failed_solves: bool = False  # explicit authorisation to re-attempt a journalled failed solve


def run_identity(config: PipelineConfig) -> dict:
    manifest, design = config.model.manifest, config.design
    return {
        "schema": PIPELINE_SCHEMA,
        "forward_model": {"forward_model_id": manifest.forward_model_id, "manifest_hash": manifest.manifest_hash,
                          "passport_manifest_hash": config.model.passport.manifest_hash},
        "solver_profile_hash": config.profile.profile_hash,
        "observation_hash": config.frozen.observation_hash,
        "objective_design": {"fit_rows": list(design.fit_rows), "fit_clusters": [list(c) for c in design.fit_clusters],
                             "holdout_rows": list(design.holdout_rows),
                             "holdout_clusters": [list(c) for c in design.holdout_clusters],
                             "sigmas": {row: asdict(sigma) for row, sigma in sorted(design.sigmas.items())}},
        "pairing_policy_hash": config.policy.policy_hash,
        "lm_settings": asdict(config.settings),
        "bounds": {"names": list(config.bounds.names), "lower": list(config.bounds.lower),
                   "upper": list(config.bounds.upper)},
        "start": {name: float(value) for name, value in sorted(config.start.items())},
        "extraction_expectation": {k: (list(v) if isinstance(v, tuple) else v)
                                   for k, v in asdict(config.expectation).items()},
        "archived_packs": {job: record.content_sha256 for job, record in sorted(config.archived_packs.items())},
        "extra": dict(config.extra_identity),
    }


def forward_candidate(model: BoundForwardModel, parameters: Mapping[str, float]) -> ForwardCandidate:
    return ForwardCandidate.create(model.manifest.parameterisation.parameterisation_id,
                                   **{name: float(value) for name, value in parameters.items()})


def forward_jobs(model: BoundForwardModel, roots: Mapping[str, Path], points: Mapping[str, Mapping[str, float]],
                 directory: Path) -> dict:
    """M3 forward jobs (content-addressed INP, job name and hashes) of named parameter points; nothing is solved.

    The narrow M4.6-owned access to the M3 forward builder for other M4 services (for example the
    M4.9 twin's truth, start and ±5 % jobs): only this pipeline layer imports ``forward_builder``.
    """
    source = read_reference_input(model, roots)
    return {key: prepare_forward_job(model, forward_candidate(model, point), source, Path(directory))
            for key, point in points.items()}


def fe_state_from_pack(pack: FEShapePack) -> FEModalState:
    shapes = np.asarray(pack.displacements, dtype=np.float64).reshape(len(pack.mode_numbers), -1)
    return FEModalState(pack.record.job_name, pack.record.fe_geometry_sha256, pack.record.node_set_sha256,
                        pack.mode_numbers, pack.frequencies_hz, shapes)


class IdentificationPipeline:
    def __init__(self, config: PipelineConfig) -> None:
        manifest = config.model.manifest
        config.frozen.require_frozen()
        problems = []
        if config.frozen.identity.forward_model_id != manifest.forward_model_id:
            problems.append("frozen set belongs to another forward model")
        if (config.profile.forward_model_id, config.profile.job_prefix) != (manifest.forward_model_id,
                                                                           manifest.job_prefix):
            problems.append("solver profile belongs to another forward model")
        if config.design.observation_hash != config.frozen.observation_hash:
            problems.append("objective design belongs to another frozen set")
        if config.policy.policy_hash != config.frozen.policy_hash:
            problems.append("pairing policy differs from the policy of the frozen set")
        if problems:
            raise RunIdentityError("; ".join(problems))
        self.config = config
        self.identity = run_identity(config)
        self.run_hash = canonical_hash(self.identity)
        passport = config.model.passport
        self.run_dir = Path(config.run_root) / str(passport.family_id) / str(passport.design_id) / self.run_hash
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.journal = RunJournal(self.run_dir / "journal.json", self.identity)
        self._source: Optional[bytes] = None
        self._reference: Optional[FEModalState] = None
        self.solves_executed = 0  # actual Abaqus solves in this session
        self.replayed_evaluations = 0

    # ------------------------------------------------------------------ helpers
    def _candidate(self, parameters: Mapping[str, float]) -> ForwardCandidate:
        return forward_candidate(self.config.model, parameters)

    @staticmethod
    def candidate_hash(candidate: ForwardCandidate) -> str:
        return canonical_hash({"parameterisation": candidate.parameterisation_id, "parameters": candidate.to_dict()})

    def _source_bytes(self) -> bytes:
        if self._source is None:
            self._source = read_reference_input(self.config.model, self.config.roots)
        return self._source

    def _check_pack(self, pack: FEShapePack, job) -> None:
        expectation = self.config.expectation
        record = pack.record
        checks = {"job_name": record.job_name == job.job_name,
                  "generated_inp_sha256": record.generated_inp_sha256 == job.generated_inp_sha256,
                  "fe_geometry": record.fe_geometry_sha256 == expectation.fe_geometry_sha256,
                  "node_set": record.node_set_sha256 == expectation.node_set_sha256,
                  "modes": pack.mode_numbers == tuple(expectation.mode_numbers)}
        failed = sorted(name for name, ok in checks.items() if not ok)
        if failed:
            raise RunIdentityError(f"{job.job_name}: FE shapes do not match the job / expectation: {failed}.")

    def _pack_for(self, job) -> tuple[FEShapePack, str]:
        config = self.config
        archived = config.archived_packs.get(job.job_name)
        if archived is not None and archived.generated_inp_sha256 == job.generated_inp_sha256:
            return load_shape_pack(archived, config.roots), "archived-validated-pack"
        key = solve_hash(job.generated_inp_sha256, config.profile)
        solve = self.journal.find("solve", solve_hash=key)
        solve_dir = self.run_dir / "solves" / job.job_name
        if solve is None:
            failures = [f for f in self.journal.records("solve_failure") if f["solve_hash"] == key]
            retried = [r for r in self.journal.records("solve_retry") if r["solve_hash"] == key]
            if len(failures) > len(retried):  # no automatic retry: a failed solve stays failed on resume
                if not config.retry_failed_solves:
                    raise SolveFailure(f"{job.job_name}: a previous solve failed ({failures[-1]['reason']}); "
                                       "retry only with an explicit retry_failed_solves authorisation.")
                self.journal.append("solve_retry", {"solve_hash": key, "job_name": job.job_name,
                                                    "after_failures": len(failures)})
            scratch = None
            if config.profile.scratch_store is not None:
                if config.profile.scratch_store not in config.roots:
                    raise RunIdentityError(f"solver scratch store {config.profile.scratch_store!r} not configured.")
                scratch = Path(config.roots[config.profile.scratch_store])
            try:
                record = solve_forward_job(job, config.profile, solve_dir, config.abaqus_command,
                                           config.solve_executor, scratch)
            except SolveFailure as failure:
                self.solves_executed += 1  # an attempted Abaqus solve is still an executed solve
                self.journal.append("solve_failure", {"solve_hash": key, "job_name": job.job_name,
                                                      "reason": str(failure)})
                raise
            self.solves_executed += 1
            solve = self.journal.append("solve", dict(record.to_dict(), executed=True))["record"]
            source = "new-solve"
        else:
            source = "journalled-solve"
        odb = verify_solve(solve, solve_dir)
        extraction = self.journal.find("extraction", job_name=job.job_name, odb_sha256=solve["odb_sha256"])
        packs = self.run_dir / "packs"
        if extraction is None:
            pack, record = extract_shape_pack(job.job_name, job.generated_inp_sha256, odb, solve["odb_sha256"],
                                              solve["odb_size_bytes"], config.expectation, packs,
                                              config.extraction_executor, config.profile.abaqus_release)
            self.journal.append("extraction", record.to_dict())
        else:
            pack = load_run_pack(packs, job.job_name, extraction["pack_content_sha256"])
        return pack, source

    def _reference_state(self) -> FEModalState:
        if self._reference is None:
            identity = self.config.frozen.identity
            start = self._candidate(self.config.start)
            job = prepare_forward_job(self.config.model, start, self._source_bytes(), self.run_dir / "jobs")
            if (job.job_name, job.generated_inp_sha256) != (identity.job_name, identity.generated_inp_sha256):
                raise RunIdentityError("the start point's M3 job differs from the frozen set's baseline job.")
            pack, _ = self._pack_for(job)
            self._check_pack(pack, job)
            if identity.shape_pack_content_sha256 not in (None, pack.record.content_sha256):
                raise RunIdentityError("baseline FE shapes differ from those the frozen set was built on.")
            self._reference = fe_state_from_pack(pack)
        return self._reference

    # ------------------------------------------------------------------ the residual function
    def evaluate(self, parameters: Mapping[str, float]) -> np.ndarray:
        candidate = self._candidate(parameters)
        key = self.candidate_hash(candidate)
        replay = self.journal.find("evaluation", candidate_hash=key)
        if replay is not None:  # resume: never re-solved, never journalled twice
            self.replayed_evaluations += 1
            if replay["refusal"] is not None:
                raise BranchTrackingRefusal(RefusalKind(replay["refusal"]["kind"]), tuple(replay["refusal"]["details"]))
            return np.asarray(replay["residuals"], dtype=float)
        reference = self._reference_state()
        job = prepare_forward_job(self.config.model, candidate, self._source_bytes(), self.run_dir / "jobs")
        pack, source = self._pack_for(job)
        self._check_pack(pack, job)
        state = fe_state_from_pack(pack)
        rows = {row.row_id: row.fe_mode for row in self.config.frozen.rows}
        clusters = list(self.config.design.fit_clusters) + list(self.config.design.holdout_clusters)
        base = {"candidate_hash": key, "parameters": candidate.to_dict(), "job_name": job.job_name,
                "generated_inp_sha256": job.generated_inp_sha256, "job_hash": job.job_hash,
                "pack_content_sha256": pack.record.content_sha256, "fe_source": source}
        try:
            tracking = track_branches(self.config.policy, reference, state, rows, clusters)
        except BranchTrackingRefusal as refusal:
            self.journal.append("evaluation", dict(base, refusal={"kind": refusal.kind.value,
                                                                  "details": list(refusal.details)},
                                                   residuals=None, objective=None, evaluation_hash=None))
            raise
        result = evaluate_objective(self.config.design, self.config.frozen, tracking)
        residuals = [float(term.residual) for term in result.fit_terms]
        record = dict(base, refusal=None, residuals=residuals, objective=result.objective,
                      tracking={b.row_id: [b.candidate_mode, b.mac] for b in tracking.branches},
                      holdout_residuals={t.term_id: t.residual for t in result.holdout_terms})
        record["evaluation_hash"] = canonical_hash({k: v for k, v in record.items() if k != "evaluation_hash"})
        self.journal.append("evaluation", record)
        return np.asarray(residuals, dtype=float)

    # ------------------------------------------------------------------ the run
    def counts(self) -> dict:
        evaluations = self.journal.records("evaluation")
        return {"identification_evaluations_journalled": len(evaluations),
                "reused_archived_evaluations": sum(e["fe_source"] == "archived-validated-pack" for e in evaluations),
                "abaqus_solves_executed_total": (sum(bool(s.get("executed")) for s in self.journal.records("solve"))
                                                 + len(self.journal.records("solve_failure"))),
                "failed_solves": len(self.journal.records("solve_failure")),
                "abaqus_solves_executed_this_session": self.solves_executed,
                "evaluations_replayed_this_session": self.replayed_evaluations}

    def run(self) -> LMResult:
        with RunLock(self.run_dir, uuid.uuid4().hex):
            result = run_bounded_lm(self.evaluate, self.config.start, self.config.bounds, self.config.settings)
            summary = {"status": result.status.value, "parameters": dict(result.parameters),
                       "objective": None if math.isnan(result.objective) else result.objective,
                       "identification_evaluations": result.solves, "iterations": result.iterations,
                       "local_sd": None if result.local_sd is None else list(result.local_sd),
                       "refusal": result.refusal, **self.counts()}
            if self.journal.find("result", **{k: summary[k] for k in ("status", "parameters",
                                                                       "identification_evaluations")}) is None:
                self.journal.append("result", summary)
            return result
