"""Multi-specimen identification campaign — Auto-ID M7 (SPEC §5, §7, §8, §12, §13; D-069).

One shared candidate of the fitted parameters (Run A: ``E_in`` only, G12 fixed) is evaluated on every
campaign specimen:

    shared candidate → per specimen: the accepted M4.6 ``IdentificationPipeline`` of its active physical
    chain (M3 job, validated / journalled FE shapes or a new solve + pinned extraction, M4.5 FE-to-FE
    tracking of *its own* frozen rows, M4.7 whitened log-frequency terms, holdouts kept)
    → the campaign FIT vector = the specimens' FIT terms stacked in definition order.

Modes are never mixed between specimens: each specimen is tracked against its own baseline only, and a
tracking refusal of any specimen refuses the campaign evaluation.  The optimiser is the accepted M4.8
bounded LM (``run_bounded_lm``); no second optimiser exists.  Σ is explicit: Σ_setup (provisional) and
Σ_meas NOT_AVAILABLE (``RowSigma(measurement_sd=None)``; never zero).

Execution needs the HUMAN gate: the authorised manifest hash must equal the planned one, and the hard
Abaqus solve budget stops the run (``SOLVE_BUDGET``) without extension.  RUN_B is refused here unless
its own later SUPERVISOR gate exists (``CampaignDefinition.require_executable``).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import shutil
from typing import Mapping, Optional, Sequence
import uuid

import numpy as np

from domain.campaign_definition import (
    CORRECTIVE_FAMILY_CONSISTENCY_POLICY,
    EFFECTIVE_ESTIMATE,
    IDENTIFIED_MATERIAL_PROPERTY,
    NO_EFFECTIVE_ESTIMATE,
    NO_MATERIAL_CLAIM,
    NOT_AVAILABLE,
    NOT_EXTERNALLY_VALIDATED,
    RUN_B,
    RUN_B_LABEL,
    ArchiveReusePlan,
    ArchivedOdbReuse,
    CampaignDefinition,
    CampaignSpecimen,
)
from domain.experiment_fixture import ExperimentFixtureManifest
from domain.forward_model_manifest import BoundForwardModel
from domain.frozen_observations import FrozenObservationSet
from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING
from domain.identification_run import RunIdentityError, RunJournal, RunLock, SolverProfile, canonical_hash
from domain.identification_run import load_solver_profile
from domain.registration import FrozenRegistration
from services import experimental_qc as qc

from .archived_baseline import load_archived_baseline, reregistered_shape_pack_evidence
from .baseline_freeze import freeze_baseline
from .branch_tracker import BranchTrackingRefusal, RefusalKind
from .campaign_diagnostics import excluded_mode_diagnostics, per_specimen_agreement
from .family_consistency import FamilyConsistencyStatus, family_consistency
from .fe_shape_pack import ShapePackRecord, load_shape_pack, load_shape_pack_record, parse_shape_pack_record
from .forward_builder import load_bound_forward_model
from .forward_solver import SolveExecutor, sha256_file
from .identification_clusters import TriggerRow, cluster_triggers
from .identification_objective import RowSigma, build_objective_design
from .identification_pipeline import IdentificationPipeline, PipelineConfig, forward_candidate, forward_jobs
from .identification_step import LMSettings, LMStatus, parameter_bounds, run_bounded_lm
from .identification_uncertainty import ResidualTerm, residual_terms
from .identification_verdict import (
    EvidenceState,
    GuardEvidence,
    NuisanceConstraint,
    SandwichG12Evidence,
    Verdict,
    VerdictContext,
    VerdictInputs,
    compute_evidence_chain,
    decide_verdicts,
    fitting_pair_mac_evidence,
)
from .modal_family_classifier import ClassifiedRow, classify_shape_pack_modes, select_holdouts
from .practical_identifiability import (
    ObservationCovariance,
    ParameterDefinition,
    ParameterRole,
    assemble_system,
    build_sensitivity_matrix,
    diagonal_component,
    reconstruct_lm_jacobian,
)
from .shape_extraction import ExtractionExecutor, ExtractionExpectation, extract_shape_pack


CAMPAIGN_RUN_SCHEMA = "auto-id/identification-campaign-run/v1"
CAMPAIGN_MANIFEST_SCHEMA = "auto-id/identification-campaign-manifest/v1"
CAMPAIGN_REPORT_SCHEMA = "auto-id/identification-campaign-report/v2"  # v2 (D-076): optimizer candidate vs formal output
DIAGNOSTIC_CANDIDATE = "DIAGNOSTIC_OPTIMIZER_CANDIDATE_NOT_RELEASED"
OPTIMIZER_CANDIDATE_ROLE = "OPTIMIZER_CANDIDATE_DIAGNOSTIC_ONLY_NOT_A_RELEASED_VALUE"
NO_GLOBAL_VALUE = "NO_GLOBAL_PARAMETER_VALUE"
FAMILY_CONSISTENCY_FAIL = "FAMILY_CONSISTENCY_FAIL"
ARCHIVE_EXTRACTION_SCHEMA = "auto-id/campaign-archive-extraction/v1"
SURFACE_TOLERANCE = 1.0e-4  # model units (mm): the extraction gate's measured-surface tolerance
ARCHIVE_RUN_STORE = "auto-id-run"  # store name the extraction records use for their packs
ABAQUS_RELEASE = "Abaqus 2024"


class CampaignError(ValueError):
    """Campaign inputs, plan or evidence are inconsistent; nothing is repaired or guessed."""


class ObservationSetMismatch(Exception):
    """The active chain does not reproduce the accepted observation set: STOP (never adjusted)."""


class CampaignGateRefusal(Exception):
    """The HUMAN execution gate does not authorise this plan; nothing is executed."""


class CampaignSolveBudgetExhausted(Exception):
    """The hard Abaqus solve budget of the campaign is used up; no automatic extension."""


class ArchiveReuseRefusal(Exception):
    """An archived FE result does not match its pinned identity; it is never reused."""


def _repo_file(repo_root: Path, path: str) -> Path:
    return Path(repo_root).joinpath(*PurePosixPath(path).parts)


# ----------------------------------------------------------------------------- specimens (stores needed)

@dataclass(frozen=True)
class CampaignSpecimenInput:
    """One specimen of the campaign on its active physical chain, with its frozen rows and holdouts."""

    spec: CampaignSpecimen
    model: BoundForwardModel
    profile: SolverProfile
    frozen: FrozenObservationSet
    holdout_rows: tuple[str, ...]
    families: Mapping[str, str]  # row id → M4.3 modal family key
    expectation: ExtractionExpectation
    baseline_record: ShapePackRecord
    registration_limited: bool
    registration_evidence_source: str
    excluded_diagnostics: tuple = ()  # D-076: excluded modes with best MAC ≥ 0.80, reporting only (never fitted)

    @property
    def label(self) -> str:
        return self.spec.label

    @property
    def fit_rows(self) -> tuple[str, ...]:
        return tuple(row.row_id for row in self.frozen.rows if row.row_id not in self.holdout_rows)

    def fit_pair_macs(self) -> dict[str, float]:
        return {self.spec.term_id(row.row_id): row.mac for row in self.frozen.rows if row.row_id in self.fit_rows}


def check_observation_set(spec: CampaignSpecimen, frozen: FrozenObservationSet, holdout_rows: Sequence[str],
                          cluster_trigger_count: int) -> None:
    """The active chain must reproduce exactly the accepted rows and roles; otherwise STOP."""

    problems = []
    if not frozen.frozen:
        problems.append(f"not frozen ({list(frozen.reasons)})")
    got = [(r.row_id, r.experimental_mode, r.fe_mode) for r in frozen.rows]
    expected = [(r.row_id, r.experimental_mode, r.fe_mode) for r in spec.rows]
    if got != expected:
        problems.append(f"rows {got} != accepted {expected}")
    if tuple(holdout_rows) != spec.holdout_rows:
        problems.append(f"M4.3 holdouts {list(holdout_rows)} != accepted {list(spec.holdout_rows)}")
    if cluster_trigger_count:
        problems.append(f"{cluster_trigger_count} cluster trigger(s): the accepted design has none")
    if problems:
        raise ObservationSetMismatch(f"{spec.label}: the active chain does not reproduce the accepted observation "
                                     f"set; STOP (no adjustment): {'; '.join(problems)}.")


def prepare_campaign_specimen(definition: CampaignDefinition, spec: CampaignSpecimen, repo_root: Path,
                              fixtures: ExperimentFixtureManifest, roots: Mapping[str, Path]) -> CampaignSpecimenInput:
    """Bind one specimen's active chain and freeze its observations independently (no Abaqus)."""

    model = load_bound_forward_model(_repo_file(repo_root, spec.forward_model), repo_root, fixtures)
    profile = load_solver_profile(_repo_file(repo_root, spec.solver_profile))
    baseline_record = load_shape_pack_record(_repo_file(repo_root, spec.baseline_shape_pack))
    archived = load_archived_baseline(_repo_file(repo_root, spec.archived_baseline))
    fixture = fixtures.fixture(spec.fixture_id)
    registration = FrozenRegistration.from_dict(json.loads(_repo_file(repo_root, fixture.registration.path)
                                                           .read_text(encoding="utf-8")))
    evidence_document = json.loads(_repo_file(repo_root, spec.registration_evidence).read_text(encoding="utf-8"))
    manifest = model.manifest
    checks = {
        "passport_fixture": model.passport.acquisition.fixture_id == spec.fixture_id,
        "parameterisation": manifest.parameterisation.parameterisation_id == definition.parameterisation_id,
        "solver_profile": (profile.forward_model_id, profile.job_prefix) == (manifest.forward_model_id,
                                                                            manifest.job_prefix),
        "baseline_state": baseline_record.state == "BASELINE",
        "baseline_job": archived.job_name == baseline_record.job_name
        and archived.generated_inp_sha256 == baseline_record.generated_inp_sha256,
        "registration": registration.registration_hash == fixture.registration.registration_hash
        == manifest.registration_hash,
        "registration_evidence": evidence_document.get("registration_hash") == registration.registration_hash,
    }
    failed = sorted(name for name, ok in checks.items() if not ok)
    if failed:
        raise CampaignError(f"campaign specimen {spec.label}: {failed}.")
    chain = qc.prepare_auto_id_experimental_input(spec.fixture_id, roots=roots, specimen_passport=model.passport)
    pack = load_shape_pack(baseline_record, roots)
    evidence = reregistered_shape_pack_evidence(archived, pack, registration, chain.dataset.sorted_modes(),
                                                manifest.forward_model_id, chain.eligibility)
    frozen = freeze_baseline(evidence, STRICT_IDENTIFICATION_PAIRING)
    families = classify_shape_pack_modes(pack)
    rows = frozen.rows if frozen.frozen else frozen.provisional_rows
    holdouts = select_holdouts([ClassifiedRow(r.row_id, r.experimental_hz, families[r.fe_mode]) for r in rows], False)
    triggers = cluster_triggers([TriggerRow(r.row_id, r.experimental_hz, r.fe_hz) for r in rows])
    check_observation_set(spec, frozen, holdouts.holdout_row_ids, len(triggers))
    passport = model.passport
    identity = passport.fe_reference.geometry_identity
    surface = passport.geometry_calibration.measured_surface
    expectation = ExtractionExpectation(surface.fe_instance, surface.side, SURFACE_TOLERANCE, identity.sha256,
                                        identity.node_count, baseline_record.node_set_sha256,
                                        baseline_record.node_set_count, baseline_record.mode_numbers)
    excluded = excluded_mode_diagnostics(evidence, frozen, STRICT_IDENTIFICATION_PAIRING.minimum_mac,
                                         {mode: family.key for mode, family in families.items()})
    return CampaignSpecimenInput(spec, model, profile, frozen, tuple(holdouts.holdout_row_ids),
                                 {r.row_id: families[r.fe_mode].key for r in frozen.rows}, expectation,
                                 baseline_record, bool(evidence_document["registration_limited"]),
                                 spec.registration_evidence, excluded)


def prepare_campaign_specimens(definition: CampaignDefinition, repo_root: Path, fixtures: ExperimentFixtureManifest,
                               roots: Mapping[str, Path]) -> tuple[CampaignSpecimenInput, ...]:
    return tuple(prepare_campaign_specimen(definition, spec, repo_root, fixtures, roots)
                 for spec in definition.specimens)


# ----------------------------------------------------------------------------- per-specimen M4.6 pipelines

def lm_settings(definition: CampaignDefinition) -> LMSettings:
    lm = definition.lm
    return LMSettings(mu_initial=lm.mu_initial, mu_decrease=lm.mu_decrease, max_step_attempts=lm.max_step_attempts,
                      solve_budget=lm.evaluation_budget, max_iterations=lm.max_iterations,
                      stop_fraction=lm.stop_fraction, mu_increase=lm.mu_increase,
                      finite_difference_step=lm.finite_difference_step)


def campaign_bounds(definition: CampaignDefinition):
    return parameter_bounds([(name, *definition.bounds[name]) for name in definition.fitted_parameters])


def row_sigma(definition: CampaignDefinition) -> RowSigma:
    """Σ per row: Σ_setup as declared; Σ_meas NOT_AVAILABLE is ``None`` (excluded, never zero)."""
    if definition.sigma.measurement_available:
        raise CampaignError("only Σ_meas NOT_AVAILABLE is supported by this campaign definition.")
    return RowSigma(None, definition.sigma.setup_sd_ln, definition.sigma.setup_provisional)


def specimen_pipeline_config(definition: CampaignDefinition, item: CampaignSpecimenInput, run_root: Path,
                             roots: Mapping[str, Path], abaqus_command: str, solve_executor: SolveExecutor,
                             extraction_executor: ExtractionExecutor, archived_packs: Mapping[str, ShapePackRecord],
                             campaign_hash: str) -> PipelineConfig:
    sigmas = {row.row_id: row_sigma(definition) for row in item.frozen.rows}
    # Each specimen contributes ≥ 1 FIT term; the campaign-level count (≥ fitted parameters) is the definition's.
    design = build_objective_design(item.frozen, item.holdout_rows, [], sigmas, 1)
    if design.fit_rows != item.spec.fit_rows or design.holdout_rows != item.spec.holdout_rows:
        raise ObservationSetMismatch(f"{item.label}: objective design rows differ from the accepted roles.")
    return PipelineConfig(
        run_root=Path(run_root) / "specimens", model=item.model, profile=item.profile, frozen=item.frozen,
        design=design, policy=STRICT_IDENTIFICATION_PAIRING, settings=lm_settings(definition),
        bounds=campaign_bounds(definition), start=definition.full_parameters(definition.start),
        expectation=item.expectation, roots=roots, abaqus_command=abaqus_command, solve_executor=solve_executor,
        extraction_executor=extraction_executor, archived_packs=dict(archived_packs),
        extra_identity={"campaign_hash": campaign_hash, "specimen": item.label, "run_type": definition.run_type})


class _SolveBudget:
    """Hard cap on new Abaqus solves across all specimens (checked before every solve is started)."""

    def __init__(self, cap: int) -> None:
        self.cap, self.used = cap, 0

    def wrap(self, executor: SolveExecutor) -> SolveExecutor:
        def run(command: str, directory: Path) -> int:
            if self.used >= self.cap:
                raise CampaignSolveBudgetExhausted(f"hard Abaqus solve budget {self.cap} used up; no extension.")
            self.used += 1
            return executor(command, directory)

        return run


# ----------------------------------------------------------------------------- the campaign run

@dataclass(frozen=True)
class CampaignRunConfig:
    run_root: Path
    roots: Mapping[str, Path]  # data stores (reference INPs, archived packs, solver scratch, archive-reuse packs)
    abaqus_command: str  # machine-specific; not part of the run identity
    solve_executor: SolveExecutor
    extraction_executor: ExtractionExecutor
    archived_packs: Mapping[str, Mapping[str, ShapePackRecord]]  # specimen label → job name → validated record
    authorised_manifest_hash: str  # the HUMAN gate authorises exactly this plan


def campaign_run_identity(definition: CampaignDefinition, specimens: Sequence[CampaignSpecimenInput],
                          manifest_hash: str, archived_packs: Mapping[str, Mapping[str, ShapePackRecord]]) -> dict:
    return {
        "schema": CAMPAIGN_RUN_SCHEMA, "run_type": definition.run_type, "campaign_hash": definition.campaign_hash,
        "manifest_hash": manifest_hash,
        "specimens": [{
            "label": item.label, "fixture_id": item.spec.fixture_id,
            "registration_hash": item.frozen.identity.registration_hash,
            "forward_model": {"forward_model_id": item.model.manifest.forward_model_id,
                              "manifest_hash": item.model.manifest.manifest_hash},
            "passport_manifest_hash": item.model.passport.manifest_hash,
            "observation_hash": item.frozen.observation_hash, "fit_rows": list(item.fit_rows),
            "holdout_rows": list(item.holdout_rows), "families": dict(sorted(item.families.items())),
            "solver_profile_hash": item.profile.profile_hash,
            "archived_packs": {job: record.content_sha256
                               for job, record in sorted(archived_packs.get(item.label, {}).items())},
        } for item in specimens],
        "fitted_parameters": list(definition.fitted_parameters), "fixed_parameters": dict(definition.fixed_parameters),
        "sigma": definition.sigma.to_dict(), "bounds": {k: list(v) for k, v in definition.bounds.items()},
        "start": dict(definition.start), "lm": asdict(definition.lm),
        "abaqus_solve_budget": definition.abaqus_solve_budget,
    }


class CampaignRun:
    def __init__(self, definition: CampaignDefinition, specimens: Sequence[CampaignSpecimenInput],
                 manifest_hash: str, config: CampaignRunConfig) -> None:
        definition.require_executable()  # RUN_B needs its own later SUPERVISOR gate
        if config.authorised_manifest_hash != manifest_hash:
            raise CampaignGateRefusal("the HUMAN gate authorised another manifest; nothing is executed.")
        if [item.label for item in specimens] != [s.label for s in definition.specimens]:
            raise CampaignError("give exactly the campaign specimens, in definition order.")
        self.definition, self.specimens, self.config = definition, tuple(specimens), config
        self.identity = campaign_run_identity(definition, specimens, manifest_hash, config.archived_packs)
        self.run_hash = canonical_hash(self.identity)
        self.run_dir = Path(config.run_root) / "campaign" / self.run_hash
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.journal = RunJournal(self.run_dir / "journal.json", self.identity)
        self.budget = _SolveBudget(definition.abaqus_solve_budget)
        self.pipelines = {
            item.label: IdentificationPipeline(specimen_pipeline_config(
                definition, item, config.run_root, config.roots, config.abaqus_command,
                self.budget.wrap(config.solve_executor), config.extraction_executor,
                config.archived_packs.get(item.label, {}), self.run_hash))
            for item in specimens}
        # A resumed run counts the solves its specimens already executed (never re-run).
        self.budget.used = sum(p.counts()["abaqus_solves_executed_total"] for p in self.pipelines.values())
        self.replayed_evaluations = 0

    @staticmethod
    def candidate_hash(fitted: Mapping[str, float]) -> str:
        return canonical_hash({"parameters": {k: float(v) for k, v in sorted(fitted.items())}})

    def evaluate(self, fitted: Mapping[str, float]) -> np.ndarray:
        """One shared candidate → every specimen independently → the stacked campaign FIT vector."""

        key = self.candidate_hash(fitted)
        replay = self.journal.find("evaluation", candidate_hash=key)
        if replay is not None:  # resume: never re-evaluated, never journalled twice
            self.replayed_evaluations += 1
            if replay["refusal"] is not None:
                raise BranchTrackingRefusal(RefusalKind(replay["refusal"]["kind"]), tuple(replay["refusal"]["details"]))
            return np.asarray(replay["residuals"], dtype=float)
        full = self.definition.full_parameters(fitted)
        parts, per_specimen = [], {}
        base = {"candidate_hash": key, "parameters": {k: float(v) for k, v in fitted.items()},
                "full_parameters": full, "fit_term_ids": list(self.definition.fit_term_ids())}
        for item in self.specimens:
            pipeline = self.pipelines[item.label]
            try:
                residuals = pipeline.evaluate(full)
            except BranchTrackingRefusal as refusal:
                self.journal.append("evaluation", dict(base, residuals=None, specimens=per_specimen, refusal={
                    "specimen": item.label, "kind": refusal.kind.value, "details": list(refusal.details)}))
                raise
            record = pipeline.journal.find(
                "evaluation", candidate_hash=pipeline.candidate_hash(forward_candidate(item.model, full)))
            per_specimen[item.label] = {k: record[k] for k in ("evaluation_hash", "job_name", "generated_inp_sha256",
                                                               "fe_source", "tracking", "holdout_residuals",
                                                               "residuals")}
            parts.append(np.asarray(residuals, dtype=float))
        stacked = np.concatenate(parts)
        holdouts = {item.spec.term_id(row): per_specimen[item.label]["holdout_residuals"][row]
                    for item in self.specimens for row in item.holdout_rows}
        self.journal.append("evaluation", dict(base, residuals=[float(v) for v in stacked], specimens=per_specimen,
                                               holdout_residuals=holdouts, refusal=None,
                                               abaqus_solves_used=self.budget.used))
        return stacked

    def counts(self) -> dict:
        return {"campaign_evaluations_journalled": len(self.journal.records("evaluation")),
                "abaqus_solves_used": self.budget.used, "abaqus_solve_budget": self.budget.cap,
                "evaluations_replayed_this_session": self.replayed_evaluations,
                "specimens": {label: p.counts() for label, p in self.pipelines.items()}}

    def run(self) -> dict:
        with RunLock(self.run_dir, uuid.uuid4().hex):
            try:
                result = run_bounded_lm(self.evaluate, self.definition.start, campaign_bounds(self.definition),
                                        lm_settings(self.definition))
                summary = {"status": result.status.value, "parameters": dict(result.parameters),
                           "objective": None if math.isnan(result.objective) else result.objective,
                           "lm_evaluations": result.solves, "iterations": result.iterations,
                           "local_sd": None if result.local_sd is None else list(result.local_sd),
                           "refusal": result.refusal, "history": [asdict(h) for h in result.history],
                           "stop": None}
            except CampaignSolveBudgetExhausted as exhausted:
                summary = {"status": LMStatus.SOLVE_BUDGET.value, "parameters": None, "objective": None,
                           "lm_evaluations": None, "iterations": None, "local_sd": None, "refusal": None,
                           "history": [], "stop": str(exhausted)}
            summary.update(self.counts())
            summary["run_hash"] = self.run_hash
            if self.journal.find("result", status=summary["status"], parameters=summary["parameters"]) is None:
                self.journal.append("result", {k: v for k, v in summary.items() if k != "specimens"})
            return summary


# ----------------------------------------------------------------------------- archived results (identity + gated extraction)

def verify_archived_odb(entry: ArchivedOdbReuse, roots: Mapping[str, Path]) -> Path:
    """The archived ODB and its status files must equal their pins; the completion / release markers must exist."""

    if entry.odb_store not in roots:
        raise ArchiveReuseRefusal(f"{entry.job_name}: store {entry.odb_store!r} not configured.")
    root = Path(roots[entry.odb_store])
    odb = root.joinpath(*PurePosixPath(entry.odb_relative_path).parts)
    if not odb.is_file() or odb.stat().st_size != entry.odb_size_bytes or sha256_file(odb) != entry.odb_sha256:
        raise ArchiveReuseRefusal(f"{entry.job_name}: the archived ODB differs from its pin; never reused.")
    for relative, digest in entry.status_files.items():
        path = root.joinpath(*PurePosixPath(relative).parts)
        if not path.is_file() or sha256_file(path) != digest:
            raise ArchiveReuseRefusal(f"{entry.job_name}: archived status file {relative} differs from its pin.")
    texts = {p.suffix: p.read_text(encoding="utf-8", errors="replace")
             for p in (root.joinpath(*PurePosixPath(r).parts) for r in entry.status_files)}
    if "THE ANALYSIS HAS COMPLETED SUCCESSFULLY" not in texts.get(".sta", "") or ABAQUS_RELEASE not in texts.get(".dat", ""):
        raise ArchiveReuseRefusal(f"{entry.job_name}: completion or release marker missing in the archived run.")
    for attempt in entry.excluded_attempts:
        if PurePosixPath(attempt["relative_path"]) in PurePosixPath(entry.odb_relative_path).parents:
            raise ArchiveReuseRefusal(f"{entry.job_name}: the pinned ODB lies inside an excluded attempt.")
    return odb


def archive_journal(run_root: Path, manifest_hash: str) -> RunJournal:
    directory = Path(run_root) / "archive_reuse"
    directory.mkdir(parents=True, exist_ok=True)
    return RunJournal(directory / "journal.json", {"schema": ARCHIVE_EXTRACTION_SCHEMA, "manifest_hash": manifest_hash})


def extract_archived_odbs(reuse: ArchiveReusePlan, specimens: Sequence[CampaignSpecimenInput], run_root: Path,
                          roots: Mapping[str, Path], executor: ExtractionExecutor, manifest_hash: str,
                          authorised_manifest_hash: str) -> dict[str, ShapePackRecord]:
    """Extraction-only reuse of the archived accepted ODBs (Abaqus Python; HUMAN gate only).

    Each ODB is verified against its pin, copied to the run store (the archived original is never opened
    by Abaqus), extracted with the pinned script and validated; the pack's mode numbers and frequencies
    must equal the accepted archived frequencies exactly.  Resumable: a journalled extraction is reused.
    """

    if authorised_manifest_hash != manifest_hash:
        raise CampaignGateRefusal("the HUMAN gate authorised another manifest; nothing is extracted.")
    journal = archive_journal(run_root, manifest_hash)
    directory = Path(run_root) / "archive_reuse"
    by_label = {item.label: item for item in specimens}
    records = {}
    for entry in reuse.odbs:
        done = journal.find("archive_extraction", job_name=entry.job_name)
        record_path = directory / "packs" / f"{entry.job_name}.shape-pack.json"
        if done is None:
            source = verify_archived_odb(entry, roots)
            copies = directory / "odb"
            copies.mkdir(parents=True, exist_ok=True)
            copy = copies / f"{entry.job_name}.odb"
            shutil.copyfile(source, copy)
            if sha256_file(copy) != entry.odb_sha256:
                raise ArchiveReuseRefusal(f"{entry.job_name}: the run-store copy differs from the pinned ODB.")
            pack, extraction = extract_shape_pack(entry.job_name, entry.generated_inp_sha256, copy, entry.odb_sha256,
                                                  entry.odb_size_bytes, by_label[entry.specimen].expectation,
                                                  directory / "packs", executor, ABAQUS_RELEASE)
            if pack.mode_numbers != entry.expected_mode_numbers or pack.frequencies_hz != entry.expected_frequencies_hz:
                raise ArchiveReuseRefusal(f"{entry.job_name}: the extracted frequencies differ from the accepted "
                                          "archived frequencies; never reused.")
            copy.unlink()  # retention: the archived original stays the content source
            journal.append("archive_extraction", dict(extraction.to_dict(), specimen=entry.specimen,
                                                      archived_odb=entry.odb_relative_path))
        record = parse_shape_pack_record(json.loads(record_path.read_text(encoding="utf-8")))
        if record.generated_inp_sha256 != entry.generated_inp_sha256 or record.frequencies_hz != entry.expected_frequencies_hz:
            raise ArchiveReuseRefusal(f"{entry.job_name}: the journalled pack does not match its archived identity.")
        records[entry.job_name] = record
    return records


def journalled_archive_records(reuse: ArchiveReusePlan, run_root: Path, manifest_hash: str) -> dict[str, ShapePackRecord]:
    """The already journalled archive extractions only (read-only; refuses when one is missing)."""

    journal = archive_journal(run_root, manifest_hash)
    directory = Path(run_root) / "archive_reuse"
    records = {}
    for entry in reuse.odbs:
        if journal.find("archive_extraction", job_name=entry.job_name) is None:
            raise ArchiveReuseRefusal(f"{entry.job_name}: no journalled archive extraction (gated extract-archive "
                                      "step first).")
        record = parse_shape_pack_record(json.loads((directory / "packs" / f"{entry.job_name}.shape-pack.json")
                                                    .read_text(encoding="utf-8")))
        if record.generated_inp_sha256 != entry.generated_inp_sha256 or record.frequencies_hz != entry.expected_frequencies_hz:
            raise ArchiveReuseRefusal(f"{entry.job_name}: the journalled pack does not match its archived identity.")
        records[entry.job_name] = record
    return records


def reused_pack_records(reuse: ArchiveReusePlan, repo_root: Path, extracted: Mapping[str, ShapePackRecord],
                        specimens: Sequence[CampaignSpecimenInput]) -> dict[str, dict[str, ShapePackRecord]]:
    """specimen → job → validated record: the governed archived packs plus the gated archive extractions."""

    out = {item.label: {} for item in specimens}
    for entry in reuse.packs:
        record = load_shape_pack_record(_repo_file(repo_root, entry.shape_pack_record))
        if (record.job_name, record.generated_inp_sha256) != (entry.job_name, entry.generated_inp_sha256):
            raise ArchiveReuseRefusal(f"{entry.job_name}: the governed pack record does not match the reuse plan.")
        if entry.pack_store is not None:  # same file pins (size, SHA-256, content hash); only the store root differs
            record = replace(record, pack=replace(record.pack, location=replace(record.pack.location,
                                                                                store=entry.pack_store)))
        out[entry.specimen][entry.job_name] = record
    for entry in reuse.odbs:
        if entry.job_name in extracted:
            out[entry.specimen][entry.job_name] = extracted[entry.job_name]
    return out


# ----------------------------------------------------------------------------- the HUMAN run manifest (no Abaqus)

def initial_points(definition: CampaignDefinition) -> dict[str, dict[str, float]]:
    """The LM's first evaluations exactly as M4.8 computes them: p0 and the central differences p·(1 ± h)."""

    h = definition.lm.finite_difference_step
    p0 = {name: float(definition.start[name]) for name in definition.fitted_parameters}
    points = {"p0": definition.full_parameters(p0)}
    for name in definition.fitted_parameters:
        up, down = dict(p0), dict(p0)
        up[name], down[name] = p0[name] * (1.0 + h), p0[name] * (1.0 - h)
        points[f"{name}+"] = definition.full_parameters(up)
        points[f"{name}-"] = definition.full_parameters(down)
    return points


def prepare_run_manifest(definition: CampaignDefinition, reuse: ArchiveReusePlan,
                         specimens: Sequence[CampaignSpecimenInput], roots: Mapping[str, Path], repo_root: Path,
                         jobs_directory: Path, verify_odbs: bool = True) -> tuple[dict, str]:
    """The HUMAN execution manifest: which initial points are reused / extracted, and the hard budgets."""

    definition.require_executable()
    points = initial_points(definition)
    packs = {(e.specimen, e.job_name): e for e in reuse.packs}
    odbs = {(e.specimen, e.job_name): e for e in reuse.odbs}
    planned, extraction_only, new_points = [], [], []
    for item in specimens:
        jobs = forward_jobs(item.model, roots, points, Path(jobs_directory) / item.label)
        for point_id, job in jobs.items():
            key = (item.label, job.job_name)
            if point_id == "p0" and (job.job_name, job.generated_inp_sha256) != (item.baseline_record.job_name,
                                                                                 item.baseline_record.generated_inp_sha256):
                raise CampaignError(f"{item.label}: the start point does not regenerate the archived baseline job.")
            if key in packs and packs[key].generated_inp_sha256 == job.generated_inp_sha256:
                source = "archived-validated-pack"
            elif key in odbs and odbs[key].generated_inp_sha256 == job.generated_inp_sha256:
                source = "archived-odb-extraction"
                entry = odbs[key]
                if verify_odbs:
                    verify_archived_odb(entry, roots)
                extraction_only.append({"specimen": item.label, "point": point_id, "job_name": job.job_name,
                                        "generated_inp_sha256": job.generated_inp_sha256,
                                        "odb": {"store": entry.odb_store, "relative_path": entry.odb_relative_path,
                                                "sha256": entry.odb_sha256, "size_bytes": entry.odb_size_bytes},
                                        "expected_frequencies_sha256": canonical_hash(
                                            list(entry.expected_frequencies_hz)),
                                        "excluded_attempts": [dict(a) for a in entry.excluded_attempts]})
            else:
                source = "NEW_SOLVE"
                new_points.append(f"{item.label}:{point_id}")
            planned.append({"specimen": item.label, "point": point_id, "parameters": points[point_id],
                            "job_name": job.job_name, "generated_inp_sha256": job.generated_inp_sha256,
                            "source": source})
    budget = definition.abaqus_solve_budget
    reused_evaluations = len(points)
    manifest = {
        "schema": CAMPAIGN_MANIFEST_SCHEMA, "campaign_id": definition.campaign_id,
        "campaign_hash": definition.campaign_hash, "run_type": definition.run_type, "decision": definition.decision,
        "archive_reuse_hash": reuse.reuse_hash,
        "specimens": [{
            "label": item.label, "fixture_id": item.spec.fixture_id,
            "registration_hash": item.frozen.identity.registration_hash,
            "forward_model_manifest_hash": item.model.manifest.manifest_hash,
            "passport_manifest_hash": item.model.passport.manifest_hash,
            "observation_hash": item.frozen.observation_hash,
            "rows": [{"row_id": r.row_id, "experimental_mode": r.experimental_mode, "experimental_hz": r.experimental_hz,
                      "fe_mode": r.fe_mode, "fe_hz": r.fe_hz, "mac": r.mac,
                      "role": "HOLDOUT" if r.row_id in item.holdout_rows else "FIT",
                      "family": item.families[r.row_id]} for r in item.frozen.rows],
            "registration_limited": item.registration_limited,
        } for item in specimens],
        "fit_term_ids": list(definition.fit_term_ids()), "holdout_term_ids": list(definition.holdout_term_ids()),
        "fitted_parameters": list(definition.fitted_parameters), "fixed_parameters": dict(definition.fixed_parameters),
        "start": dict(definition.start), "bounds": {k: list(v) for k, v in definition.bounds.items()},
        "engineering_plausibility": {k: list(v) for k, v in definition.engineering_plausibility.items()},
        "sigma": definition.sigma.to_dict(), "lm": asdict(definition.lm), "not_fitted": dict(definition.not_fitted),
        "initial_points": planned, "extraction_only_jobs": extraction_only, "new_solve_initial_points": new_points,
        "budgets": {"max_new_abaqus_solves": budget, "max_new_solve_extractions": budget,
                    "archive_extractions": len(extraction_only),
                    "max_abaqus_python_extractions": budget + len(extraction_only),
                    "lm_evaluation_budget": definition.lm.evaluation_budget,
                    "reused_initial_evaluations": reused_evaluations,
                    "max_new_campaign_evaluations": definition.lm.evaluation_budget - reused_evaluations},
        "executor_gate": ("run only with --authorised-manifest-hash equal to this manifest hash (HUMAN gate); the "
                          "archive extractions and the solves are separate gated commands; no automatic retry, no "
                          "budget extension; RUN_B is not part of this manifest"),
    }
    if new_points:
        raise CampaignError(f"initial points need new solves {new_points}; the approved design reuses all of them.")
    return manifest, canonical_hash(manifest)


# ----------------------------------------------------------------------------- report (no Abaqus)

def _relative(residual: float, sigma: float) -> float:
    return math.exp(residual * sigma) - 1.0  # f_FE / f_EXP − 1 from a whitened ln-ratio term


def _practical(max_abs: float, definition: CampaignDefinition) -> str:
    if max_abs <= definition.preferred_max_abs_relative_error:
        return "WITHIN_PREFERRED_TARGET"
    if max_abs <= definition.acceptable_max_abs_relative_error:
        return "WITHIN_ACCEPTABLE_TARGET"
    return "OUTSIDE_PRACTICAL_TARGET"


def campaign_rows(definition: CampaignDefinition, specimens: Sequence[CampaignSpecimenInput],
                  evaluation: Mapping) -> list[dict]:
    """Per-row FE/EXP agreement of one journalled campaign evaluation (FIT and HOLDOUT, never mixed)."""

    sigma = definition.sigma.setup_sd_ln
    rows = []
    for item in specimens:
        record = evaluation["specimens"][item.label]
        fit_values = dict(zip(item.fit_rows, record["residuals"]))
        for row in item.frozen.rows:
            holdout = row.row_id in item.holdout_rows
            value = record["holdout_residuals"][row.row_id] if holdout else fit_values[row.row_id]
            mode, mac = record["tracking"][row.row_id]
            rel = _relative(value, sigma)
            rows.append({"term_id": item.spec.term_id(row.row_id), "specimen": item.label, "row_id": row.row_id,
                         "role": "HOLDOUT" if holdout else "FIT", "family": item.families[row.row_id],
                         "experimental_mode": row.experimental_mode, "experimental_hz": row.experimental_hz,
                         "baseline_fe_mode": row.fe_mode, "tracked_fe_mode": mode, "tracking_mac": mac,
                         "fe_hz": row.experimental_hz * (1.0 + rel), "relative_error": rel,
                         "whitened_residual": value, "baseline_pair_mac": row.mac})
    return rows


def campaign_m5_verdict(definition: CampaignDefinition, specimens: Sequence[CampaignSpecimenInput],
                        evaluations: Sequence[Mapping], result: Mapping, final: Mapping) -> dict:
    """M5 evidence chain + verdict on the stacked campaign system at p̂ (PRODUCTION context; rules unchanged)."""

    return _campaign_m5(definition, specimens, evaluations, result, final)[0]


def campaign_family_consistency(definition: CampaignDefinition, whitened_jacobian, final: Mapping, result: Mapping,
                                full_rank: bool) -> dict:
    """SPEC §13 on the campaign's linearised FIT system at p̂ (D-076).

    Pure: the final evaluation's whitened FIT residuals and the reconstructed whitened Jacobian (both journalled
    or recorded), no stores, no Abaqus.
    """

    names = definition.fitted_parameters
    terms = definition.fit_term_ids()
    specimen_of = {s.term_id(row): s.label for s in definition.specimens for row in s.fit_rows}
    policy = definition.family_consistency_policy
    policy_source = "campaign definition (identity-bound)"
    if policy is None:
        policy, policy_source = CORRECTIVE_FAMILY_CONSISTENCY_POLICY, ("D-076 corrective default; not part of this "
                                                                       "campaign's historical identity")
    at_bound = any(math.isclose(float(result["parameters"][n]), bound, rel_tol=1e-12)
                   for n in names for bound in definition.bounds[n])
    sigma = {"setup": {"sd_ln": definition.sigma.setup_sd_ln, "status": definition.sigma.setup_status,
                       "in_whitening": True},
             "measurement": {"status": definition.sigma.measurement_status, "in_whitening": False,
                             "note": "NOT_AVAILABLE: no component; never taken as zero"}}
    outcome = family_consistency(
        terms, specimen_of, final["residuals"], whitened_jacobian, names,
        {n: float(result["parameters"][n]) for n in names},
        chi2_conditions={"sigma_fixed": True, "interior_optimum": not at_bound,
                         "observation_model_comparable": True, "practical_identifiability_adequate": bool(full_rank),
                         "no_influential_priors_or_bounds": not at_bound},
        sigma=sigma, bootstrap_samples=policy.bootstrap_samples, bootstrap_seed=policy.bootstrap_seed)
    document = outcome.to_dict()
    document["policy_source"] = policy_source
    document["linearisation"] = "reconstructed LM Jacobian (the M5 system) at p̂; whitened FIT residuals at p̂"
    return document


def _family_guard(document: Mapping, source: str) -> GuardEvidence:
    state = {FamilyConsistencyStatus.PASS.value: EvidenceState.PASS,
             FamilyConsistencyStatus.FAIL.value: EvidenceState.FAIL}.get(document["status"], EvidenceState.NOT_AVAILABLE)
    detail = (f"SPEC §13 {document['status']}" + (f" ({document['path']}: Δχ² {document['delta_chi2']:.4g}, "
                                                    f"Δdof {document['delta_dof']}, p_χ² {document['p_chi2']:.3g}, "
                                                    f"bootstrap p {document['bootstrap_p']:.3g})"
                                                    if document["delta_chi2"] is not None else
                                                    f": {'; '.join(document['reasons'])}"))
    return GuardEvidence("family_consistency", state, source, detail)


def _campaign_m5(definition: CampaignDefinition, specimens: Sequence[CampaignSpecimenInput],
                 evaluations: Sequence[Mapping], result: Mapping, final: Mapping) -> tuple[dict, Optional[dict], dict]:
    """The M5 verdict record, the M5 model_form_robustness record (None when M5 computed none) and the SPEC §13
    family-consistency record."""

    names = definition.fitted_parameters
    sigma = definition.sigma.setup_sd_ln
    usable = [e for e in evaluations if e.get("residuals") is not None]
    jacobian = reconstruct_lm_jacobian(usable, result["history"], definition.start, names,
                                       definition.lm.finite_difference_step)
    whitened = np.array(jacobian.whitened)
    terms = definition.fit_term_ids()
    data = {term: {n: float(whitened[i, j]) * sigma for j, n in enumerate(names)} for i, term in enumerate(terms)}
    parameters = tuple(ParameterDefinition(n, ParameterRole.GLOBAL) for n in names)
    matrix = build_sensitivity_matrix(data, terms, [], parameters, {n: jacobian.provenance for n in names})
    covariance = ObservationCovariance(matrix.term_ids, (diagonal_component(
        "sigma_setup", matrix.term_ids, {t: sigma for t in matrix.term_ids}, definition.sigma.setup_provisional,
        f"{definition.sigma.setup_source}; Σ_meas {NOT_AVAILABLE}: no component (never zero)"),))
    system = assemble_system(matrix, covariance, ())
    families = {item.spec.term_id(row): family for item in specimens for row, family in item.families.items()}
    fit = residual_terms(list(terms), [], final["residuals"], families)
    held = [ResidualTerm(term, (term,), families[term], value) for term, value in final["holdout_residuals"].items()]
    p_hat = {n: float(result["parameters"][n]) for n in names}
    label = f"{definition.campaign_id} ({definition.run_type}): real-data campaign"
    chain = compute_evidence_chain(system, fit, held, p_hat, label)
    consistency = campaign_family_consistency(definition, whitened, final, result, chain.analysis.full_rank)
    macs = {}
    for item in specimens:
        macs.update(item.fit_pair_macs())
    refusals = [e for e in evaluations if e.get("refusal") is not None]
    source = f"campaign journal {definition.campaign_id}"
    inputs = VerdictInputs(
        VerdictContext.PRODUCTION, label, chain.analysis, chain.statistical, chain.pattern, chain.birge,
        chain.robustness,
        fitting_pair_mac_evidence(macs, "frozen physical strict pairs (baseline MAC); identity at p̂ by FE-to-FE "
                                        "tracking MAC ≥ 0.90"),
        GuardEvidence("registration", EvidenceState.FAIL if any(i.registration_limited for i in specimens)
                      else EvidenceState.PASS, "; ".join(i.registration_evidence_source for i in specimens),
                      "M2.4 registration_limited per specimen"),
        GuardEvidence("peak_derived_input", EvidenceState.PASS, "fixtures: PolyMAX curve-fitted dataset-55 modal sets",
                      "no peak-derived modes"),
        GuardEvidence("tracking", EvidenceState.FAIL if refusals else EvidenceState.PASS, source,
                      f"{len(refusals)} refused campaign evaluation(s)"),
        _family_guard(consistency, source),
        SandwichG12Evidence("G12_mpa" in names, EvidenceState.NOT_AVAILABLE, ("k_core",), {"k_core": NuisanceConstraint(
            "k_core", False, True, False, "no independent k_core prior (M6.3 NOT_AVAILABLE, D-059)")},
            "SPEC §5.1; D-046"),
        p_hat, {n: ParameterRole.GLOBAL for n in names})
    report = decide_verdicts(inputs)
    return report.to_dict(), None if chain.robustness is None else chain.robustness.to_dict(), consistency


# How the campaign report reads M5 model_form_robustness (D-075).  M5 is unchanged: its numeric range is taken
# over the VALID leave-one-family-out cases only, so an incomplete set can show 0.0.  The campaign report never
# presents that number as model-form evidence and never substitutes another value.
LOO_COMPLETE = "AVAILABLE_COMPLETE_LOO"
LOO_INCOMPLETE = "UNAVAILABLE_INCOMPLETE_LOO"
LOO_NOT_EVALUATED = "NOT_EVALUATED"
MODEL_DEPENDENCE_DIAGNOSTIC = "MODEL_DEPENDENCE_DIAGNOSTIC"


def model_form_robustness_reporting(robustness: Optional[Mapping]) -> dict:
    """The campaign status of an M5 model_form_robustness record (its ``to_dict`` form).

    The range is reported only when every family's leave-one-family-out case is VALID and there are at least
    two of them; it is then a MODEL_DEPENDENCE_DIAGNOSTIC (not a confidence interval, not a material-property
    uncertainty).  Otherwise the status is UNAVAILABLE_INCOMPLETE_LOO with no number at all.
    """

    if robustness is None:
        return {"status": LOO_NOT_EVALUATED, "label": None, "parameters": None, "cases": [], "reasons": [
            "no M5 model_form_robustness record (no converged campaign verdict)"]}
    cases = [{"family": c["family"], "removed_term_ids": list(c["removed_term_ids"]), "status": c["status"],
              "estimate": c["estimate"]} for c in robustness["cases"]]
    valid = [c for c in cases if c["status"] == "VALID"]
    reasons = []
    if robustness["refused_families"] or len(valid) != len(cases):
        reasons.append(f"leave-one-family-out refused for {list(robustness['refused_families'])}")
    if len(valid) < 2:
        reasons.append(f"{len(valid)} valid leave-one-family-out case(s): a range needs at least two")
    if reasons or not robustness["supports_green"]:
        return {"status": LOO_INCOMPLETE, "label": None, "parameters": None, "cases": cases, "reasons": reasons + [
            "the M5 numeric model_form_robustness covers the valid cases only; it is not a model-form uncertainty "
            "and not evidence of robustness (no replacement value)"]}
    parameters = {name: {"p_hat": item["p_hat"], "min_estimate": item["min_estimate"],
                         "max_estimate": item["max_estimate"],
                         "half_range_ln": 0.5 * (item["max_shift_ln"] - item["min_shift_ln"])}
                  for name, item in sorted(robustness["parameters"].items())}
    return {"status": LOO_COMPLETE, "label": MODEL_DEPENDENCE_DIAGNOSTIC, "parameters": parameters, "cases": cases,
            "reasons": ["range of the linearised leave-one-family-out estimates: a model-dependence diagnostic; "
                        "not a confidence interval and not a formal material-property uncertainty"]}


DESCRIPTIVE_LN_BANDS = (0.05, 0.08)  # D-045 bands, used only to describe stability (never an identification rule)


def _describe_shift(delta_ln: float) -> str:
    size = abs(delta_ln)
    if size <= DESCRIPTIVE_LN_BANDS[0]:
        return "WITHIN_0.05_LN"
    if size <= DESCRIPTIVE_LN_BANDS[1]:
        return "WITHIN_0.08_LN"
    return "BEYOND_0.08_LN"


def compare_to_reference(parameters: Mapping[str, float], reference: Mapping[str, float], label: str) -> dict:
    """Δ ln p against a reference run (for RUN_B: RUN_A), described with the D-045 ln bands (descriptive only)."""
    shifts = {}
    for name, value in reference.items():
        if name in parameters:
            delta = math.log(float(parameters[name])) - math.log(float(value))
            shifts[name] = {"reference": float(value), "value": float(parameters[name]), "delta_ln": delta,
                            "delta_percent": (math.exp(delta) - 1.0) * 100.0, "description": _describe_shift(delta)}
    return {"reference": label, "shifts": shifts,
            "note": "descriptive stability only (D-045 ln bands); not a material-identification criterion"}


def uncertainty_basis(definition: CampaignDefinition) -> dict:
    """What the reported statistical_sd / birge_adjusted_sd are conditional on (D-076; audit J5).

    Reporting only: M5 mathematics and values are unchanged, nothing is enlarged and Σ_meas is never invented.
    """

    sigma = definition.sigma
    complete = sigma.measurement_available and not sigma.setup_provisional
    statement = ("statistical_sd and birge_adjusted_sd are complete measured uncertainties" if complete else
                 "statistical_sd and birge_adjusted_sd are conditional on the available covariance components "
                 f"(Σ_setup {sigma.setup_status}; Σ_meas {sigma.measurement_status}); they are not a complete "
                 "measured uncertainty")
    return {"statistical_sd_status": "COMPLETE_MEASURED_COVARIANCE" if complete else
            "CONDITIONAL_ON_AVAILABLE_COVARIANCE",
            "covariance_components": {"sigma_setup": sigma.setup_status, "sigma_meas": sigma.measurement_status},
            "statement": statement}


def build_campaign_report(definition: CampaignDefinition, specimens: Sequence[CampaignSpecimenInput],
                          evaluations: Sequence[Mapping], result: Mapping,
                          reference: Optional[Mapping[str, float]] = None, reference_label: str = "") -> dict:
    """The campaign report: engineering estimate and the formal M5 verdict, kept separate (D-069).

    RUN_B is the diagnostic ``EFFECTIVE_MODEL_COMPENSATION_TEST``: its label replaces the engineering
    estimate label, its G12 is a compensation diagnostic (never a material property), and its shifts
    against RUN_A are reported in ln p with the descriptive D-045 bands.
    """

    status = result["status"]
    parameters = result.get("parameters")
    final = start = None
    if parameters is not None:
        final = next((e for e in evaluations if e.get("refusal") is None and e["parameters"] == dict(parameters)), None)
    start = next((e for e in evaluations if e.get("refusal") is None and e["parameters"] == dict(definition.start)),
                 None)
    refusals = [e["refusal"] for e in evaluations if e.get("refusal") is not None]
    reasons = []
    if status != LMStatus.CONVERGED.value:
        reasons.append(f"LM status {status}")
    if refusals:
        reasons.append("branch tracking refusal")
    rows = campaign_rows(definition, specimens, final) if final is not None else []
    baseline_rows = campaign_rows(definition, specimens, start) if start is not None else []
    max_final = max((abs(r["relative_error"]) for r in rows), default=None)
    max_baseline = max((abs(r["relative_error"]) for r in baseline_rows), default=None)
    at_bound = {}
    plausibility = {}
    if parameters is not None:
        for name in definition.fitted_parameters:
            low, high = definition.bounds[name]
            at_bound[name] = math.isclose(parameters[name], low, rel_tol=1e-12) or math.isclose(parameters[name], high,
                                                                                               rel_tol=1e-12)
            if name in definition.engineering_plausibility:
                lo, hi = definition.engineering_plausibility[name]
                plausibility[name] = "INSIDE" if lo <= parameters[name] <= hi else "OUTSIDE_REPORTED_NOT_REJECTED"
    if any(at_bound.values()):
        reasons.append("estimate at a numerical search bound")
    identity_ok = bool(rows) and all(r["tracking_mac"] >= STRICT_IDENTIFICATION_PAIRING.tracking_minimum_mac
                                     and r["baseline_pair_mac"] >= STRICT_IDENTIFICATION_PAIRING.minimum_mac
                                     for r in rows)
    if rows and not identity_ok:
        reasons.append("mode identity not established for every row")
    practical = None if max_final is None else _practical(max_final, definition)
    if practical == "OUTSIDE_PRACTICAL_TARGET":
        reasons.append("frequency agreement outside the practical ~10 % target")
    improved = None if max_final is None or max_baseline is None else max_final <= max_baseline
    if improved is False:
        reasons.append("frequency agreement worse than at the start")
    if final is None:
        reasons.append("no accepted final evaluation")
    verdict = robustness = consistency = None
    if final is not None and status == LMStatus.CONVERGED.value and not refusals:
        verdict, robustness, consistency = _campaign_m5(definition, specimens, evaluations, result, final)
    identified = bool(verdict) and all(v["verdict"] == Verdict.IDENTIFIED.value for v in verdict["verdicts"].values())
    # D-076 (SPEC §1 upper rule): a value is released only where M5 gives IDENTIFIED or WIDE.  Otherwise the
    # optimiser output stays visible as a diagnostic candidate and nothing is presented as a released parameter.
    released = {name: v["reported_value"] for name, v in (verdict or {}).get("verdicts", {}).items()
                if v["verdict"] in (Verdict.IDENTIFIED.value, Verdict.WIDE.value) and v["reported_value"] is not None}
    all_released = bool(verdict) and set(released) == set(definition.fitted_parameters)
    if reasons:
        estimate = NO_EFFECTIVE_ESTIMATE
    elif all_released:
        estimate = EFFECTIVE_ESTIMATE
    else:
        estimate = DIAGNOSTIC_CANDIDATE
    if definition.run_type == RUN_B:
        estimate = RUN_B_LABEL if not reasons else f"{RUN_B_LABEL}_INCOMPLETE"
    blockers = []
    if consistency is not None and consistency["status"] == FamilyConsistencyStatus.FAIL.value:
        blockers.append(FAMILY_CONSISTENCY_FAIL)
    for name, v in (verdict or {}).get("verdicts", {}).items():
        if name not in released:
            blockers.extend(f"{name}: {reason}" for reason in v["reasons"])
    if verdict is None:
        blockers.append("no formal M5 verdict (no converged, refusal-free campaign result)")
    formal_output = {
        "status": "VALUES_RELEASED" if all_released else (
            "PARTIAL_VALUES_RELEASED" if released else NO_GLOBAL_VALUE),
        "released_values": released,
        "blockers": blockers,
        "rule": "SPEC v1.1 §1 upper rule and §13: only M5 IDENTIFIED / WIDE values are output; a family-consistency "
                "FAIL blocks every shared value (D-076)",
    }
    return {
        "schema": CAMPAIGN_REPORT_SCHEMA, "campaign_id": definition.campaign_id, "run_type": definition.run_type,
        "campaign_hash": definition.campaign_hash, "lm_status": status,
        "optimizer_candidate": {"values": parameters, "role": OPTIMIZER_CANDIDATE_ROLE},
        "formal_output": formal_output,
        "family_consistency": consistency,
        "per_specimen_agreement": per_specimen_agreement(rows, baseline_rows) if rows and baseline_rows else None,
        "excluded_mode_diagnostics": {item.label: list(item.excluded_diagnostics) for item in specimens},
        "engineering": {"estimate": estimate, "reasons": reasons, "rows": rows, "baseline_rows": baseline_rows,
                        "max_abs_relative_error": max_final, "baseline_max_abs_relative_error": max_baseline,
                        "practical_target": practical, "improved_or_consistent": improved,
                        "engineering_plausibility": plausibility, "at_search_bound": at_bound,
                        "practical_target_note": "engineering criterion, separate from the formal M5 verdict"},
        "m5_verdict": verdict,
        "uncertainty_basis": uncertainty_basis(definition),
        "model_form_robustness": model_form_robustness_reporting(robustness),
        "material_claim": IDENTIFIED_MATERIAL_PROPERTY if identified else NO_MATERIAL_CLAIM,
        "validation": NOT_EXTERNALLY_VALIDATED,
        "reporting": ("released values are model-calibrated effective constants within this FE model (SPEC §5.2); "
                      f"{NOT_EXTERNALLY_VALIDATED} (D-060); an optimizer candidate is diagnostic evidence only "
                      "(D-076)"),
        "sigma": definition.sigma.to_dict(), "not_fitted": dict(definition.not_fitted),
        "fixed_parameters": dict(definition.fixed_parameters),
        "abaqus_solves_used": result.get("abaqus_solves_used"),
        "parameter_roles": {name: ("COMPENSATION_DIAGNOSTIC_NOT_MATERIAL_PROPERTY"
                                   if definition.run_type == RUN_B and name == "G12_mpa" else "EFFECTIVE_MODEL_PARAMETER")
                            for name in definition.fitted_parameters},
        "comparison": (compare_to_reference(parameters, reference, reference_label)
                       if reference is not None and parameters is not None else None),
    }
