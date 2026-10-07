"""Transverse-constant screening — Auto-ID M6.4 (SPEC §5, §5.2; D-055, D-061, D-066).

FE-only screening of the fixed carbon-face constants E3, ν13, ν23, G13 and G23 over the
SUPERVISOR-approved envelope (``domain.transverse_screening``):

1. **Plan** (no Abaqus): for every screening specimen, the envelope's reference candidate must
   regenerate the archived baseline job byte-identically (its validated shape pack is reused:
   no baseline solve); then one content-addressed job per one-at-a-time endpoint perturbation
   (``forward_builder.prepare_screening_job``).  The plan is the HUMAN Abaqus manifest; its
   canonical hash is what a HUMAN gate authorises.
2. **Run** (HUMAN gate only): each job is solved with its pinned solver profile and extracted
   with the pinned ``extract_odb.py`` (the M4.6 ``forward_solver`` / ``shape_extraction``
   paths, executors injected).  Hash-chained journal; no automatic retry; no duplicate solve.
3. **Evaluate** (no Abaqus): every frozen observation row is followed from the baseline to each
   perturbed state by FE-to-FE MAC (M4.5 ``track_branches``; never re-paired), and
   Δf/f = (f_perturbed − f_baseline) / f_baseline is recorded per row.  Per constant, over all
   specimens, rows and both endpoints: max |Δf/f| < 0.3 % → ``NEGLIGIBLE_FOR_BUDGET``, otherwise
   ``INCLUDE_IN_UNCERTAINTY_BUDGET``.  A tracking refusal leaves the constant
   ``NOT_CLASSIFIED_TRACKING_REFUSED`` (escalation; nothing is re-paired or guessed).

The criterion is uncertainty-budget bookkeeping only.  It is not a model-fit target, and a
budgeted constant is never a reason to re-tune the model (D-066).  No E_in or G12 refit.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence
import uuid

from domain.experiment_fixture import ExperimentFixtureManifest
from domain.forward_model_manifest import BoundForwardModel, ForwardCandidate
from domain.identification_pairing_policy import IdentificationPairingPolicy
from domain.identification_run import RunIdentityError, RunJournal, RunLock, SolverProfile, canonical_hash
from domain.identification_run import load_solver_profile
from domain.transverse_screening import (
    INCLUDE,
    NEGLIGIBLE,
    ScreeningEnvelope,
    ScreeningPerturbation,
    ScreeningSpecimen,
    classify,
)

from .branch_tracker import BranchTrackingRefusal, FEModalState, track_branches
from .fe_shape_pack import ShapePackRecord, load_shape_pack, load_shape_pack_record
from .forward_builder import (
    PreparedForwardJob,
    load_bound_forward_model,
    prepare_screening_job,
    read_reference_input,
    render_forward_input,
)
from .forward_solver import SolveExecutor, SolveFailure, solve_forward_job, solve_hash, verify_solve
from .identification_pipeline import fe_state_from_pack
from .shape_extraction import (
    PINNED_EXTRACT_SCRIPT,
    PINNED_EXTRACT_SCRIPT_SHA256,
    ExtractionExecutor,
    ExtractionExpectation,
    extract_shape_pack,
    load_run_pack,
)


SCREENING_MANIFEST_SCHEMA = "auto-id/transverse-screening-manifest/v1"
SCREENING_RUN_SCHEMA = "auto-id/transverse-screening-run/v1"
SCREENING_RESULT_SCHEMA = "auto-id/transverse-screening-result/v1"
NOT_CLASSIFIED = "NOT_CLASSIFIED_TRACKING_REFUSED"
SURFACE_TOLERANCE = 1.0e-4  # model units (mm): the extraction gate's measured-surface tolerance


class ScreeningError(ValueError):
    """The screening inputs, plan or evidence are inconsistent; nothing is repaired or guessed."""


def _repo_file(repo_root: Path, path: str) -> Path:
    return Path(repo_root).joinpath(*PurePosixPath(path).parts)


# ----------------------------------------------------------------------------- specimens

@dataclass(frozen=True)
class BoundScreeningSpecimen:
    spec: ScreeningSpecimen
    model: BoundForwardModel
    profile: SolverProfile
    baseline: ShapePackRecord  # the archived, validated baseline pack record (reused; no baseline solve)

    @property
    def label(self) -> str:
        return self.spec.label


def bind_screening_specimens(envelope: ScreeningEnvelope, repo_root: Path,
                             fixtures: ExperimentFixtureManifest | None) -> tuple[BoundScreeningSpecimen, ...]:
    """Load every specimen's forward model, solver profile and baseline pack record, and check them."""

    bound = []
    for spec in envelope.specimens:
        model = load_bound_forward_model(_repo_file(repo_root, spec.forward_model), repo_root, fixtures)
        profile = load_solver_profile(_repo_file(repo_root, spec.solver_profile))
        baseline = load_shape_pack_record(_repo_file(repo_root, spec.baseline_shape_pack))
        manifest = model.manifest
        identity = model.passport.fe_reference.geometry_identity
        checks = {
            "parameterisation": manifest.parameterisation.parameterisation_id == envelope.parameterisation_id,
            "solver_profile": (profile.forward_model_id, profile.job_prefix) == (manifest.forward_model_id,
                                                                                manifest.job_prefix),
            "baseline_state": baseline.state == "BASELINE",
            "baseline_job_prefix": baseline.job_name.startswith(manifest.job_prefix + "_"),
            "baseline_modes": baseline.mode_numbers == envelope.extraction_modes,
            "baseline_fe_geometry": identity is not None and baseline.fe_geometry_sha256 == identity.sha256,
            "eigenvalue_headroom": manifest.frequency_request.requested_eigenvalue_count >= max(envelope.extraction_modes),
        }
        failed = sorted(name for name, ok in checks.items() if not ok)
        if failed:
            raise ScreeningError(f"screening specimen {spec.label}: {failed}.")
        bound.append(BoundScreeningSpecimen(spec, model, profile, baseline))
    return tuple(bound)


def extraction_expectation(specimen: BoundScreeningSpecimen, envelope: ScreeningEnvelope) -> ExtractionExpectation:
    """The extraction expectation of a screening job: the baseline pack's surface node set and modes."""

    passport = specimen.model.passport
    if passport.geometry_calibration is None:
        raise ScreeningError(f"{specimen.label}: the passport has no measured surface.")
    surface = passport.geometry_calibration.measured_surface
    identity = passport.fe_reference.geometry_identity
    return ExtractionExpectation(surface.fe_instance, surface.side, SURFACE_TOLERANCE, identity.sha256,
                                 identity.node_count, specimen.baseline.node_set_sha256,
                                 specimen.baseline.node_set_count, envelope.extraction_modes)


# ----------------------------------------------------------------------------- plan (HUMAN Abaqus manifest)

@dataclass(frozen=True)
class ScreeningJob:
    specimen: str
    perturbation: ScreeningPerturbation
    job: PreparedForwardJob


@dataclass(frozen=True)
class ScreeningPlan:
    envelope: ScreeningEnvelope
    specimens: tuple[BoundScreeningSpecimen, ...]
    jobs: tuple[ScreeningJob, ...]
    manifest: dict
    manifest_hash: str

    def specimen(self, label: str) -> BoundScreeningSpecimen:
        for item in self.specimens:
            if item.label == label:
                return item
        raise ScreeningError(f"no screening specimen {label!r} in the plan.")


def prepare_screening_plan(envelope: ScreeningEnvelope, specimens: Sequence[BoundScreeningSpecimen],
                           roots: Mapping[str, Path], output_directory: Path) -> ScreeningPlan:
    """Render every screening job (no Abaqus) and build the HUMAN Abaqus manifest."""

    if [item.label for item in specimens] != [item.label for item in envelope.specimens]:
        raise ScreeningError("give exactly the envelope's screening specimens, in envelope order.")
    reference = ForwardCandidate.create(envelope.parameterisation_id, **envelope.reference_candidate)
    jobs, baselines = [], []
    for specimen in specimens:
        source = read_reference_input(specimen.model, roots)
        rendered = render_forward_input(specimen.model, reference, source)
        if rendered.sha256 != specimen.baseline.generated_inp_sha256:
            raise ScreeningError(f"{specimen.label}: the reference candidate does not regenerate the archived "
                                 f"baseline job {specimen.baseline.job_name}; its pack cannot be reused.")
        baselines.append({"specimen": specimen.label, "job_name": specimen.baseline.job_name,
                          "generated_inp_sha256": specimen.baseline.generated_inp_sha256,
                          "shape_pack_content_sha256": specimen.baseline.content_sha256,
                          "node_set_sha256": specimen.baseline.node_set_sha256,
                          "frozen_rows": [{"row_id": r.row_id, "fe_mode": r.fe_mode, "role": r.role,
                                           "baseline_hz": specimen.baseline.frequencies_hz[
                                               specimen.baseline.mode_numbers.index(r.fe_mode)]}
                                          for r in specimen.spec.rows],
                          "observation_source": specimen.spec.observation_source})
        for perturbation in envelope.perturbations():
            job = prepare_screening_job(specimen.model, envelope, perturbation, source, Path(output_directory))
            jobs.append(ScreeningJob(specimen.label, perturbation, job))
    names = [item.job.job_name for item in jobs]
    if len(set(names)) != len(names) or set(names) & {item["job_name"] for item in baselines}:
        raise ScreeningError("screening jobs must be distinct from each other and from the baselines.")

    profiles = {item.label: item.profile for item in specimens}
    manifest = {
        "schema": SCREENING_MANIFEST_SCHEMA,
        "envelope": {"envelope_id": envelope.envelope_id, "envelope_hash": envelope.envelope_hash,
                     "basis": envelope.basis, "decision": envelope.decision},
        "criterion": {"max_abs_relative_frequency_change_strictly_below": envelope.criterion},
        "reference_candidate": dict(envelope.reference_candidate),
        "counts": {"abaqus_solves": len(jobs), "extraction_runs": len(jobs), "baseline_solves": 0,
                   "baseline_extractions": 0},
        "baselines": baselines,
        "baseline_endpoints": [{"constant": c, "endpoint": e} for c, e in envelope.baseline_endpoints()],
        "extraction": {"script": PINNED_EXTRACT_SCRIPT, "script_sha256": PINNED_EXTRACT_SCRIPT_SHA256,
                       "start_mode": min(envelope.extraction_modes), "end_mode": max(envelope.extraction_modes)},
        "jobs": [{
            "specimen": item.specimen, "perturbation_id": item.perturbation.perturbation_id,
            "constant": item.perturbation.constant, "endpoint": item.perturbation.endpoint,
            "value": item.perturbation.value, "baseline": item.perturbation.baseline,
            "forward_model_id": item.job.forward_model_id, "job_name": item.job.job_name,
            "generated_inp_sha256": item.job.generated_inp_sha256,
            "generated_inp_size_bytes": item.job.provenance["generated_inp"]["size_bytes"],
            "changed_lines": item.job.provenance["generated_inp"]["changed_lines"],
            "job_hash": item.job.job_hash,
            "solver_profile_id": profiles[item.specimen].profile_id,
            "solver_profile_hash": profiles[item.specimen].profile_hash,
            "requested_eigenvalue_count": item.job.requested_eigenvalue_count,
        } for item in jobs],
    }
    return ScreeningPlan(envelope, tuple(specimens), tuple(jobs), manifest, canonical_hash(manifest))


# ----------------------------------------------------------------------------- run (HUMAN Abaqus gate only)

@dataclass(frozen=True)
class ScreeningRunConfig:
    run_root: Path
    roots: Mapping[str, Path]  # data stores (archived packs, solver scratch)
    abaqus_command: str  # machine-specific; not part of the run identity
    solve_executor: SolveExecutor
    extraction_executor: ExtractionExecutor
    authorised_manifest_hash: str  # the HUMAN gate authorises exactly this plan


def run_identity(plan: ScreeningPlan) -> dict:
    return {"schema": SCREENING_RUN_SCHEMA, "manifest_hash": plan.manifest_hash}


def run_screening(plan: ScreeningPlan, config: ScreeningRunConfig) -> dict:
    """Solve and extract every screening job of an authorised plan; resumable, no automatic retry."""

    if config.authorised_manifest_hash != plan.manifest_hash:
        raise ScreeningError("the HUMAN gate authorised another manifest; nothing is solved.")
    run_root = Path(config.run_root)
    run_root.mkdir(parents=True, exist_ok=True)
    journal = RunJournal(run_root / "journal.json", run_identity(plan))
    solves = extractions = 0
    with RunLock(run_root, uuid.uuid4().hex):
        for item in plan.jobs:
            specimen = plan.specimen(item.specimen)
            profile, job = specimen.profile, item.job
            key = solve_hash(job.generated_inp_sha256, profile)
            solve_dir = run_root / "solves" / job.job_name
            solve = journal.find("solve", solve_hash=key)
            if solve is None:
                failure = journal.find("solve_failure", solve_hash=key)
                if failure is not None:
                    raise SolveFailure(f"{job.job_name}: a previous solve failed ({failure['reason']}); no automatic retry.")
                scratch = None
                if profile.scratch_store is not None:
                    if profile.scratch_store not in config.roots:
                        raise RunIdentityError(f"solver scratch store {profile.scratch_store!r} not configured.")
                    scratch = Path(config.roots[profile.scratch_store])
                try:
                    record = solve_forward_job(job, profile, solve_dir, config.abaqus_command, config.solve_executor,
                                               scratch)
                except SolveFailure as exc:
                    solves += 1
                    journal.append("solve_failure", {"solve_hash": key, "job_name": job.job_name, "reason": str(exc)})
                    raise
                solves += 1
                solve = journal.append("solve", dict(record.to_dict(), perturbation_id=item.perturbation.perturbation_id,
                                                     specimen=item.specimen))["record"]
            odb = verify_solve(solve, solve_dir)
            extraction = journal.find("extraction", job_name=job.job_name, odb_sha256=solve["odb_sha256"])
            if extraction is None:
                _, record = extract_shape_pack(job.job_name, job.generated_inp_sha256, odb, solve["odb_sha256"],
                                               solve["odb_size_bytes"], extraction_expectation(specimen, plan.envelope),
                                               run_root / "packs", config.extraction_executor, profile.abaqus_release)
                journal.append("extraction", dict(record.to_dict(), specimen=item.specimen,
                                                  perturbation_id=item.perturbation.perturbation_id))
                extractions += 1
    return {"manifest_hash": plan.manifest_hash, "jobs": len(plan.jobs), "solves_executed": solves,
            "extractions_executed": extractions}


def load_screening_states(plan: ScreeningPlan, run_root: Path,
                          roots: Mapping[str, Path]) -> tuple[dict[str, FEModalState], dict[tuple[str, str], FEModalState]]:
    """Baseline states from the archived packs; perturbed states from the journalled, re-verified run packs."""

    journal = RunJournal(Path(run_root) / "journal.json", run_identity(plan))
    baselines = {item.label: fe_state_from_pack(load_shape_pack(item.baseline, roots)) for item in plan.specimens}
    candidates = {}
    for item in plan.jobs:
        extraction = journal.find("extraction", job_name=item.job.job_name)
        if extraction is None:
            raise ScreeningError(f"{item.job.job_name}: no journalled extraction; the screening is incomplete.")
        pack = load_run_pack(Path(run_root) / "packs", item.job.job_name, extraction["pack_content_sha256"])
        if pack.record.generated_inp_sha256 != item.job.generated_inp_sha256:
            raise ScreeningError(f"{item.job.job_name}: the pack belongs to another INP.")
        candidates[(item.specimen, item.perturbation.perturbation_id)] = fe_state_from_pack(pack)
    return baselines, candidates


# ----------------------------------------------------------------------------- evaluation (no Abaqus)

def _diagnostic_all_modes(policy, reference: FEModalState, candidate: FEModalState) -> dict:
    """Informational only (never classifies): each baseline mode followed on its own."""
    tracked, untracked = {}, []
    for mode, frequency in zip(reference.mode_numbers, reference.frequencies_hz):
        try:
            branch = track_branches(policy, reference, candidate, {f"M{mode}": mode}).branches[0]
        except BranchTrackingRefusal:
            untracked.append(mode)
            continue
        tracked[str(mode)] = (branch.candidate_hz - frequency) / frequency
    worst = max((abs(value) for value in tracked.values()), default=None)
    return {"relative_change_by_mode": tracked, "untracked_modes": untracked, "max_abs_relative_change": worst,
            "used_for_classification": False}


def evaluate_screening(envelope: ScreeningEnvelope, policy: IdentificationPairingPolicy,
                       baseline_states: Mapping[str, FEModalState],
                       candidate_states: Mapping[tuple[str, str], FEModalState],
                       expected_jobs: Mapping[tuple[str, str], str], manifest_hash: str) -> dict:
    """Classify every screened constant; ``expected_jobs`` maps (specimen, "baseline" | perturbation id) → job."""

    policy.require_strict()
    perturbations = envelope.perturbations()
    states = []
    for spec in envelope.specimens:
        reference = baseline_states.get(spec.label)
        if reference is None or reference.state_id != expected_jobs.get((spec.label, "baseline")):
            raise ScreeningError(f"{spec.label}: the baseline state is missing or is not the planned baseline job.")
        for perturbation in perturbations:
            key = (spec.label, perturbation.perturbation_id)
            candidate = candidate_states.get(key)
            if candidate is None or candidate.state_id != expected_jobs.get(key):
                raise ScreeningError(f"{key}: the perturbed state is missing or is not the planned job.")
            entry = {"specimen": spec.label, "perturbation_id": perturbation.perturbation_id,
                     "constant": perturbation.constant, "endpoint": perturbation.endpoint,
                     "value": perturbation.value, "baseline": perturbation.baseline, "job_name": candidate.state_id,
                     "refusal": None, "rows": []}
            try:
                tracking = track_branches(policy, reference, candidate, spec.row_modes)
            except BranchTrackingRefusal as refusal:
                entry["refusal"] = {"kind": refusal.kind.value, "details": list(refusal.details)}
            else:
                step = math.log(perturbation.value / perturbation.baseline)
                for row in spec.rows:
                    branch = next(b for b in tracking.branches if b.row_id == row.row_id)
                    f0 = reference.frequencies_hz[reference.index(row.fe_mode)]
                    entry["rows"].append({
                        "row_id": row.row_id, "role": row.role, "baseline_fe_mode": row.fe_mode,
                        "candidate_fe_mode": branch.candidate_mode, "tracking_mac": branch.mac,
                        "baseline_hz": f0, "perturbed_hz": branch.candidate_hz,
                        "relative_change": (branch.candidate_hz - f0) / f0,
                        "log_sensitivity": math.log(branch.candidate_hz / f0) / step})
                entry["order_changes"] = [list(pair) for pair in tracking.order_changes]
            entry["diagnostic_all_modes"] = _diagnostic_all_modes(policy, reference, candidate)
            states.append(entry)

    constants = {}
    for name in envelope.ranges:
        entries = [entry for entry in states if entry["constant"] == name]
        refused = [entry["perturbation_id"] + "@" + entry["specimen"] for entry in entries if entry["refusal"]]
        changes = [abs(row["relative_change"]) for entry in entries for row in entry["rows"]]
        worst = max(changes, default=0.0)  # a baseline endpoint contributes Δf ≡ 0
        constants[name] = {
            "range": {"baseline": envelope.ranges[name].baseline, "low": envelope.ranges[name].low,
                      "high": envelope.ranges[name].high, "unit": envelope.ranges[name].unit},
            "baseline_endpoints": [e for c, e in envelope.baseline_endpoints() if c == name],
            "max_abs_relative_change": None if refused else worst,
            "classification": NOT_CLASSIFIED if refused else classify(worst),
            "tracking_refusals": refused,
        }
    classified = all(item["classification"] != NOT_CLASSIFIED for item in constants.values())
    result = {
        "schema": SCREENING_RESULT_SCHEMA,
        "manifest_hash": manifest_hash,
        "envelope": {"envelope_id": envelope.envelope_id, "envelope_hash": envelope.envelope_hash,
                     "basis": envelope.basis, "decision": envelope.decision},
        "criterion": {"max_abs_relative_frequency_change_strictly_below": envelope.criterion,
                      "purpose": envelope.canonical["criterion"]["purpose"]},
        "pairing_policy_hash": policy.policy_hash,
        "states": states,
        "constants": constants,
        "negligible": sorted(n for n, item in constants.items() if item["classification"] == NEGLIGIBLE),
        "include_in_uncertainty_budget": sorted(n for n, item in constants.items() if item["classification"] == INCLUDE),
        "not_classified": sorted(n for n, item in constants.items() if item["classification"] == NOT_CLASSIFIED),
        "budget_closed": classified,
    }
    result["result_hash"] = canonical_hash(result)
    return result


def expected_jobs(plan: ScreeningPlan) -> dict[tuple[str, str], str]:
    jobs = {(item.label, "baseline"): item.baseline.job_name for item in plan.specimens}
    jobs.update({(item.specimen, item.perturbation.perturbation_id): item.job.job_name for item in plan.jobs})
    return jobs
