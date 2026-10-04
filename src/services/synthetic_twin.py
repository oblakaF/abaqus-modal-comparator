"""Synthetic digital twin for the M4.9 gate — PREPARATION ONLY (M4_DECISION_RECORD.md §4–§6).

Everything the M4.9 gate needs, with the real Abaqus solves left to a separate HUMAN gate
(solver and extraction executors are injected; the tests use fakes):

1. ``TwinDefinition``: truth and start parameters, the relative frequency-noise sd, an
   **explicit** noise seed (no default), the FE modes of the synthetic experiment, σ and
   k_int; content-hashed.
2. Truth stage (``solve_truth``): the truth candidate's M3 forward job, solved and extracted
   through the M4.6 components, journalled apart from the identification loop (the truth
   solve is not one of the 20 identification evaluations).
3. ``build_synthetic_experiment``: truth FE modes read through the FrozenRegistration onto the
   measured grid (FE shapes rotated by R into the experimental frame, unmeasured DOFs zero),
   frequencies × (1 + sd·ε) with ε from a version-independent deterministic generator
   (SHA-256 + Box–Muller).  Never real PolyMAX data.  Experimental modes are numbered by
   synthetic frequency; FE mode numbers appear only in the definition and in provenance.
4. ``design_twin_observations``: strict baseline freeze at p0 (M4.2), M4.3 family
   classification and holdouts, M4.4 cluster triggers and confirmation with the validated
   ±5 % packs, the M4.7 objective design.  Nothing is hand-selected.  An UNSTABLE or
   UNSUPPORTED trigger group, or a design ``build_objective_design`` refuses, makes the twin
   design REFUSED; rows are never silently dropped (how to resolve such a case is a
   SUPERVISOR decision, not made here).
5. ``prepare_twin``: stages 2–4, then the M4.6 ``PipelineConfig`` (twin hashes and the seed in
   the run identity) and a deterministic provenance record.
6. ``assess_recovery``: M4.9 pass criteria 1–2 as recorded (CONVERGED; |ln(p̂_j/p_true,j)| ≤ sd_j
   with sd_j the local stop-rule sd).  G12 identifiability is reported as observed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
import struct
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from domain.experimental_qc import ExperimentalModeEligibility, ExperimentalQCStatus
from domain.forward_model_manifest import BoundForwardModel, ForwardCandidate
from domain.frozen_observations import BaselineIdentity, FrozenObservationSet
from domain.identification_run import RunJournal, SolverProfile, canonical_hash
from domain.registration import REGISTRATION_DOF_COMPONENTS

from .baseline_freeze import BaselineEvidence, build_baseline_evidence, freeze_baseline
from .fe_shape_pack import FEShapePack, load_shape_pack
from .forward_builder import prepare_forward_job, read_reference_input
from .forward_solver import SolveExecutor, SolveFailure, solve_forward_job, solve_hash, verify_solve
from .identification_clusters import (
    CARBON_V1_DIRECTIONS,
    ClusterConfirmation,
    ClusterStatus,
    TriggerRow,
    cluster_triggers,
    confirm_cluster,
)
from .identification_objective import ObjectiveDesign, ObjectiveInputError, RowSigma, build_objective_design
from .identification_pairing import ModeFrequency
from .identification_pipeline import PipelineConfig
from .identification_step import LMResult, LMStatus
from .modal_family_classifier import ClassifiedRow, HoldoutSelection, ModeFamily, classify_shape_pack_modes, select_holdouts
from .shape_extraction import ExtractionExecutor, ExtractionExpectation, extract_shape_pack, load_run_pack


TWIN_SCHEMA = "auto-id/synthetic-twin/v1"
SYNTHETIC_EXPERIMENT_SCHEMA = "auto-id/synthetic-experiment/v1"
TWIN_TRUTH_SCHEMA = "auto-id/twin-truth/v1"
TWIN_PROVENANCE_SCHEMA = "auto-id/twin-provenance/v1"
TWIN_EVIDENCE_SOURCE = "synthetic-twin"
_DEFINITION_KEYS = {"schema", "twin_id", "forward_model_id", "truth", "start", "noise_relative_sd", "noise_seed",
                    "mode_numbers", "sigma", "k_int_enabled", "provenance"}
_PIPELINE_FIELDS = set(PipelineConfig.__dataclass_fields__) - {"frozen", "design"}
_REQUIRED_PIPELINE_FIELDS = {"run_root", "model", "profile", "policy", "settings", "bounds", "start", "expectation",
                             "roots", "abaqus_command", "solve_executor", "extraction_executor", "archived_packs"}


class TwinError(ValueError):
    """A twin definition, experiment or preparation is malformed or inconsistent."""


# ----------------------------------------------------------------------------- definition

@dataclass(frozen=True)
class TwinDefinition:
    twin_id: str
    forward_model_id: str
    truth: Mapping[str, float]
    start: Mapping[str, float]
    noise_relative_sd: float
    noise_seed: int
    mode_numbers: tuple[int, ...]
    sigma: float
    k_int_enabled: bool
    canonical: Mapping[str, Any]  # every field except free-text provenance

    @property
    def definition_hash(self) -> str:
        return canonical_hash(self.canonical)


def _positive(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise TwinError(f"{field} must be finite and positive.")
    return float(value)


def _parameters(value: object, field: str) -> dict[str, float]:
    if not isinstance(value, Mapping) or not value:
        raise TwinError(f"{field} must be a non-empty mapping of parameters.")
    return {str(name): _positive(number, f"{field}.{name}") for name, number in value.items()}


def parse_twin_definition(data: object) -> TwinDefinition:
    if not isinstance(data, Mapping) or set(data) != _DEFINITION_KEYS:
        found = set(data) if isinstance(data, Mapping) else set()
        raise TwinError(f"twin definition: missing {sorted(_DEFINITION_KEYS - found)}, "
                        f"unknown {sorted(found - _DEFINITION_KEYS)}.")
    if data["schema"] != TWIN_SCHEMA:
        raise TwinError(f"schema must be {TWIN_SCHEMA!r}.")
    truth, start = _parameters(data["truth"], "truth"), _parameters(data["start"], "start")
    if list(truth) != list(start):
        raise TwinError("truth and start must name the same parameters in the same order.")
    seed = data["noise_seed"]
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise TwinError("noise_seed must be an explicit non-negative integer (there is no default seed).")
    modes = data["mode_numbers"]
    if not isinstance(modes, list) or not modes or any(isinstance(m, bool) or not isinstance(m, int) for m in modes) \
            or len(set(modes)) != len(modes):
        raise TwinError("mode_numbers must be a non-empty list of unique integers.")
    if not isinstance(data["k_int_enabled"], bool):
        raise TwinError("k_int_enabled must be a boolean.")
    noise, sigma = _positive(data["noise_relative_sd"], "noise_relative_sd"), _positive(data["sigma"], "sigma")
    canonical = {"schema": TWIN_SCHEMA, "twin_id": str(data["twin_id"]),
                 "forward_model_id": str(data["forward_model_id"]), "truth": truth, "start": start,
                 "noise_relative_sd": noise, "noise_seed": seed, "mode_numbers": sorted(modes), "sigma": sigma,
                 "k_int_enabled": data["k_int_enabled"]}
    return TwinDefinition(canonical["twin_id"], canonical["forward_model_id"], truth, start, noise, seed,
                          tuple(sorted(modes)), sigma, data["k_int_enabled"], canonical)


def load_twin_definition(path: Path) -> TwinDefinition:
    with open(path, encoding="utf-8") as handle:
        return parse_twin_definition(json.load(handle))


# ----------------------------------------------------------------------------- deterministic noise

def deterministic_standard_normal(seed: int, key: str) -> float:
    """N(0, 1) sample from SHA-256(seed, key) by Box–Muller; independent of NumPy and platform."""
    digest = hashlib.sha256(f"auto-id/twin-noise/v1|{int(seed)}|{key}".encode("utf-8")).digest()
    a, b = struct.unpack(">QQ", digest[:16])
    u1 = (a + 1.0) / 2.0 ** 64  # (0, 1]
    u2 = b / 2.0 ** 64  # [0, 1)
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


# ----------------------------------------------------------------------------- synthetic experiment

def measured_dofs(registration) -> tuple[str, ...]:
    contract = np.asarray(registration.measured_dof_contract, dtype=bool)
    if contract.ndim != 2 or contract.shape[1] != len(REGISTRATION_DOF_COMPONENTS) or not contract.any():
        raise TwinError("the registration's measured-DOF contract must be (points, 3) with measured DOFs.")
    return tuple(name for k, name in enumerate(REGISTRATION_DOF_COMPONENTS) if contract[:, k].any())


@dataclass(frozen=True)
class SyntheticMode:
    number: int  # experimental numbering, by synthetic frequency
    frequency_hz: float
    node_ids: tuple
    vectors: np.ndarray  # (points, 3) complex, experimental frame, unmeasured DOFs zero
    source_fe_mode: int  # provenance only
    truth_fe_hz: float  # provenance only
    noise: float  # ε (standard normal)


@dataclass(frozen=True)
class SyntheticExperiment:
    twin_definition_hash: str
    truth_pack_content_sha256: str
    registration_hash: str
    modes: tuple[SyntheticMode, ...]
    content_sha256: str


def _registered_fe_vectors(pack: FEShapePack, registration, mode: int) -> np.ndarray:
    rows = pack.rows(registration.mapped_fe_node_ids)
    rotation = np.asarray(registration.rotation, dtype=float)
    return pack.displacements[pack.mode_index(mode)][rows].astype(np.float64) @ rotation


def build_synthetic_experiment(definition: TwinDefinition, truth_pack: FEShapePack, registration) -> SyntheticExperiment:
    """Truth FE modes on the measured grid, with deterministic frequency noise (no real experimental data)."""

    missing = sorted(set(definition.mode_numbers) - set(truth_pack.mode_numbers))
    if missing:
        raise TwinError(f"the truth pack lacks FE modes {missing} of the twin definition.")
    measured_dofs(registration)
    mask = np.asarray(registration.measured_dof_contract, dtype=bool)
    node_ids = tuple(registration.experimental_node_ids)
    if mask.shape != (len(node_ids), 3) or len(registration.mapped_fe_node_ids) != len(node_ids):
        raise TwinError("registration points, mapped FE nodes and the measured-DOF contract do not match.")
    drafts = []
    for mode in definition.mode_numbers:
        epsilon = deterministic_standard_normal(definition.noise_seed, f"fe-mode:{mode}")
        truth_hz = truth_pack.frequencies_hz[truth_pack.mode_index(mode)]
        vectors = np.where(mask, _registered_fe_vectors(truth_pack, registration, mode), 0.0).astype(complex)
        drafts.append((truth_hz * (1.0 + definition.noise_relative_sd * epsilon), mode, truth_hz, epsilon, vectors))
    drafts.sort(key=lambda item: (item[0], item[1]))
    modes = tuple(SyntheticMode(k, frequency, node_ids, vectors, mode, truth_hz, epsilon)
                  for k, (frequency, mode, truth_hz, epsilon, vectors) in enumerate(drafts, start=1))
    digest = hashlib.sha256()
    digest.update(json.dumps({"schema": SYNTHETIC_EXPERIMENT_SCHEMA, "twin": definition.definition_hash,
                              "truth_pack": truth_pack.record.content_sha256,
                              "registration": registration.registration_hash,
                              "nodes": [str(n) for n in node_ids],
                              "modes": [[m.number, m.source_fe_mode, m.frequency_hz, m.noise] for m in modes]},
                             sort_keys=True).encode("utf-8"))
    for mode in modes:
        digest.update(np.ascontiguousarray(mode.vectors.astype("<c16")).tobytes())
    return SyntheticExperiment(definition.definition_hash, truth_pack.record.content_sha256,
                               registration.registration_hash, modes, digest.hexdigest())


# ----------------------------------------------------------------------------- baseline evidence (complete MAC)

def _mac(left: np.ndarray, right: np.ndarray) -> float:
    """|aᴴb|² / (aᴴa · bᴴb) on the given DOFs (the comparator's MAC formula)."""
    norm_left, norm_right = float(np.vdot(left, left).real), float(np.vdot(right, right).real)
    if norm_left <= 1e-30 or norm_right <= 1e-30:
        raise TwinError("a shape vector is zero on the measured DOFs.")
    return float(np.clip(abs(np.vdot(left, right)) ** 2 / (norm_left * norm_right), 0.0, 1.0))


def measured_mac_matrix(fe_pack: FEShapePack, registration, experiment: SyntheticExperiment) -> np.ndarray:
    """Experimental × FE MAC on the registration's measured-DOF contract (FE shapes rotated by R)."""
    mask = np.asarray(registration.measured_dof_contract, dtype=bool)
    fe = [_registered_fe_vectors(fe_pack, registration, mode)[mask] for mode in fe_pack.mode_numbers]
    return np.array([[_mac(vector, mode.vectors[mask]) for vector in fe] for mode in experiment.modes])


def twin_baseline_evidence(definition: TwinDefinition, model: BoundForwardModel, p0_job, p0_pack: FEShapePack,
                           registration, experiment: SyntheticExperiment) -> BaselineEvidence:
    """Strict-freeze input: all synthetic modes eligible (no suspension threshold applies), complete MAC."""

    record = p0_pack.record
    if (record.job_name, record.generated_inp_sha256) != (p0_job.job_name, p0_job.generated_inp_sha256):
        raise TwinError("the baseline pack does not belong to the start point's M3 job.")
    if experiment.registration_hash != registration.registration_hash:
        raise TwinError("the synthetic experiment was built on another registration.")
    identity = BaselineIdentity(model.manifest.forward_model_id, p0_job.job_name, p0_job.generated_inp_sha256,
                                record.fe_geometry_sha256, registration.registration_hash, experiment.content_sha256,
                                f"synthetic-twin:{definition.twin_id}", measured_dofs(registration),
                                TWIN_EVIDENCE_SOURCE, definition.definition_hash, record.content_sha256)
    numbers = tuple(mode.number for mode in experiment.modes)
    eligibility = ExperimentalModeEligibility(ExperimentalQCStatus.NOT_AVAILABLE, None, numbers, ())
    return build_baseline_evidence(identity, [ModeFrequency(m.number, m.frequency_hz) for m in experiment.modes],
                                   eligibility, [ModeFrequency(m, p0_pack.frequencies_hz[k])
                                                 for k, m in enumerate(p0_pack.mode_numbers)],
                                   measured_mac_matrix(p0_pack, registration, experiment))


# ----------------------------------------------------------------------------- observation design

class DesignStatus(str, Enum):
    USABLE = "USABLE"
    REFUSED = "REFUSED"


@dataclass(frozen=True)
class TwinObservationDesign:
    status: DesignStatus
    reasons: tuple[str, ...]
    frozen: FrozenObservationSet
    families: Mapping[str, ModeFamily]  # row_id → M4.3 family of its baseline FE mode
    holdouts: Optional[HoldoutSelection]
    clusters: tuple[ClusterConfirmation, ...]  # every triggered group, with its M4.4 status
    design: Optional[ObjectiveDesign]

    def require_usable(self) -> ObjectiveDesign:
        if self.status is not DesignStatus.USABLE or self.design is None:
            raise TwinError("twin observation design is REFUSED: " + "; ".join(self.reasons))
        return self.design


def _flat(pack: FEShapePack, modes: Sequence[int]) -> np.ndarray:
    """Surface U1/U2/U3 shapes, one row per mode (the M4.4 primary basis)."""
    data = pack.displacements[[pack.mode_index(m) for m in modes]].astype(np.float64)
    return data.reshape(len(modes), -1)


def design_twin_observations(definition: TwinDefinition, frozen: FrozenObservationSet, p0_pack: FEShapePack,
                             perturbed_packs: Mapping[str, FEShapePack], parameter_count: int) -> TwinObservationDesign:
    """Families, holdouts and clusters through the existing M4.3 / M4.4 policies, then the M4.7 design."""

    if not frozen.frozen:
        return TwinObservationDesign(DesignStatus.REFUSED, ("baseline not frozen: " + "; ".join(frozen.reasons),),
                                     frozen, {}, None, (), None)
    missing = sorted(set(CARBON_V1_DIRECTIONS) - set(perturbed_packs))
    if missing:
        raise TwinError(f"perturbed packs missing for directions {missing}.")
    all_families = classify_shape_pack_modes(p0_pack)
    families = {row.row_id: all_families[row.fe_mode] for row in frozen.rows}
    holdouts = select_holdouts([ClassifiedRow(row.row_id, row.experimental_hz, families[row.row_id])
                                for row in frozen.rows], k_int_enabled=definition.k_int_enabled)
    fe_mode = {row.row_id: row.fe_mode for row in frozen.rows}
    perturbed = {direction: _flat(pack, pack.mode_numbers) for direction, pack in perturbed_packs.items()}
    confirmations, reasons = [], []
    for trigger in cluster_triggers([TriggerRow(r.row_id, r.experimental_hz, r.fe_hz) for r in frozen.rows]):
        confirmation = confirm_cluster(trigger.row_ids, _flat(p0_pack, [fe_mode[row] for row in trigger.row_ids]),
                                       perturbed)
        confirmations.append(confirmation)
        if confirmation.status in (ClusterStatus.UNSTABLE, ClusterStatus.UNSUPPORTED):
            reasons.append(f"trigger group {list(trigger.row_ids)} is {confirmation.status.value}: "
                           + "; ".join(confirmation.reasons))
    if reasons:
        return TwinObservationDesign(DesignStatus.REFUSED, tuple(reasons), frozen, families, holdouts,
                                     tuple(confirmations), None)
    confirmed = [c for c in confirmations if c.status is ClusterStatus.CONFIRMED]
    sigmas = {row.row_id: RowSigma(definition.sigma, 0.0, False) for row in frozen.rows}
    try:
        design = build_objective_design(frozen, holdouts.holdout_row_ids, confirmed, sigmas, parameter_count)
    except ObjectiveInputError as error:
        return TwinObservationDesign(DesignStatus.REFUSED, (f"objective design: {error}",), frozen, families,
                                     holdouts, tuple(confirmations), None)
    return TwinObservationDesign(DesignStatus.USABLE, (), frozen, families, holdouts, tuple(confirmations), design)


# ----------------------------------------------------------------------------- truth stage

def forward_candidate(model: BoundForwardModel, parameters: Mapping[str, float]) -> ForwardCandidate:
    return ForwardCandidate.create(model.manifest.parameterisation.parameterisation_id,
                                   **{name: float(value) for name, value in parameters.items()})


def solve_truth(definition: TwinDefinition, model: BoundForwardModel, profile: SolverProfile,
                expectation: ExtractionExpectation, roots: Mapping[str, Path], directory: Path, abaqus_command: str,
                solve_executor: SolveExecutor, extraction_executor: ExtractionExecutor,
                retry_failed_solve: bool = False) -> tuple[FEShapePack, RunJournal]:
    """The truth forward solve and its validated extraction, in a journal of their own.

    Resumable (a journalled solve or extraction is reused, never repeated); a failed truth
    solve is not retried without ``retry_failed_solve``.
    """

    if definition.forward_model_id != model.manifest.forward_model_id:
        raise TwinError("the twin definition belongs to another forward model.")
    identity = {"schema": TWIN_TRUTH_SCHEMA, "twin_definition_hash": definition.definition_hash,
                "forward_model_hash": model.manifest.manifest_hash, "solver_profile_hash": profile.profile_hash,
                "extraction_expectation": {k: (list(v) if isinstance(v, tuple) else v)
                                           for k, v in asdict(expectation).items()}}
    directory = Path(directory) / canonical_hash(identity)
    directory.mkdir(parents=True, exist_ok=True)
    journal = RunJournal(directory / "journal.json", identity)
    job = prepare_forward_job(model, forward_candidate(model, definition.truth), read_reference_input(model, roots),
                              directory / "jobs")
    key = solve_hash(job.generated_inp_sha256, profile)
    solve_dir = directory / "solves" / job.job_name
    solve = journal.find("truth_solve", solve_hash=key)
    if solve is None:
        failures = [f for f in journal.records("truth_solve_failure") if f["solve_hash"] == key]
        if failures and not retry_failed_solve:
            raise SolveFailure(f"{job.job_name}: the truth solve failed before ({failures[-1]['reason']}); "
                               "retry only with an explicit authorisation.")
        try:
            record = solve_forward_job(job, profile, solve_dir, abaqus_command, solve_executor)
        except SolveFailure as failure:
            journal.append("truth_solve_failure", {"solve_hash": key, "job_name": job.job_name,
                                                   "reason": str(failure)})
            raise
        solve = journal.append("truth_solve", dict(record.to_dict(), executed=True))["record"]
    odb = verify_solve(solve, solve_dir)
    packs = directory / "packs"
    extraction = journal.find("truth_extraction", job_name=job.job_name, odb_sha256=solve["odb_sha256"])
    if extraction is None:
        pack, record = extract_shape_pack(job.job_name, job.generated_inp_sha256, odb, solve["odb_sha256"],
                                          solve["odb_size_bytes"], expectation, packs, extraction_executor,
                                          profile.abaqus_release)
        journal.append("truth_extraction", record.to_dict())
    else:
        pack = load_run_pack(packs, job.job_name, extraction["pack_content_sha256"])
    return pack, journal


# ----------------------------------------------------------------------------- preparation

def perturbed_points(start: Mapping[str, float], step: float) -> dict[str, dict[str, float]]:
    """The ±step points of every parameter, computed exactly as the M4.8 central differences do."""
    points = {}
    for direction in CARBON_V1_DIRECTIONS:
        parameter, sign = direction[:-1], direction[-1]
        if parameter not in start:
            raise TwinError(f"direction {direction} names an unknown parameter.")
        point = {name: float(value) for name, value in start.items()}
        point[parameter] = point[parameter] * (1.0 + step) if sign == "+" else point[parameter] * (1.0 - step)
        points[direction] = point
    return points


@dataclass(frozen=True)
class TwinPreparation:
    definition: TwinDefinition
    experiment: SyntheticExperiment
    evidence: BaselineEvidence
    observation_design: TwinObservationDesign
    pipeline_config: Optional[PipelineConfig]  # only when the design is USABLE
    truth_journal: RunJournal
    provenance: Mapping[str, Any]


def _twin_provenance(definition: TwinDefinition, truth_pack: FEShapePack, truth_journal: RunJournal,
                     experiment: SyntheticExperiment, observation: TwinObservationDesign,
                     packs: Mapping[str, FEShapePack]) -> dict:
    design = observation.design
    return {
        "schema": TWIN_PROVENANCE_SCHEMA,
        "twin_definition": dict(definition.canonical),
        "twin_definition_hash": definition.definition_hash,
        "noise_generator": "SHA-256(seed, 'fe-mode:<n>') with Box-Muller (auto-id/twin-noise/v1)",
        "truth": {"job_name": truth_pack.record.job_name, "generated_inp_sha256": truth_pack.record.generated_inp_sha256,
                  "pack_content_sha256": truth_pack.record.content_sha256,
                  "truth_run_hash": truth_journal.run_hash,
                  "counts_toward_identification_budget": False},
        "synthetic_experiment": {"content_sha256": experiment.content_sha256,
                                 "registration_hash": experiment.registration_hash,
                                 "modes": [{"number": m.number, "frequency_hz": m.frequency_hz,
                                            "source_fe_mode": m.source_fe_mode, "truth_fe_hz": m.truth_fe_hz,
                                            "epsilon": m.noise} for m in experiment.modes]},
        "reused_packs": {key: pack.record.content_sha256 for key, pack in sorted(packs.items())},
        "observation_design": {
            "status": observation.status.value, "reasons": list(observation.reasons),
            "freeze_status": observation.frozen.status.value,
            "observation_hash": observation.frozen.observation_hash,
            "rows": [{"row_id": r.row_id, "experimental_mode": r.experimental_mode, "fe_mode": r.fe_mode,
                      "mac": r.mac, "family": observation.families[r.row_id].key} for r in observation.frozen.rows],
            "holdouts": None if observation.holdouts is None else asdict(observation.holdouts),
            "clusters": [{"row_ids": list(c.row_ids), "status": c.status.value, "reasons": list(c.reasons)}
                         for c in observation.clusters],
            "fit_rows": None if design is None else list(design.fit_rows),
            "fit_clusters": None if design is None else [list(c) for c in design.fit_clusters],
            "holdout_rows": None if design is None else list(design.holdout_rows),
            "holdout_clusters": None if design is None else [list(c) for c in design.holdout_clusters]},
    }


def prepare_twin(definition: TwinDefinition, registration, pipeline_fields: Mapping[str, Any],
                 truth_executors: tuple[SolveExecutor, ExtractionExecutor], work_directory: Path,
                 retry_failed_truth_solve: bool = False) -> TwinPreparation:
    """Truth stage → synthetic experiment → strict freeze → M4.3/M4.4 design → M4.6 pipeline configuration.

    ``pipeline_fields`` are the ``PipelineConfig`` fields except ``frozen`` and ``design`` (forward
    model, solver profile, pairing policy, LM settings, bounds, start, extraction expectation,
    stores, executors and the validated archived packs of p0 and the ±5 % points).  A missing
    archived pack is refused: obtaining one needs its own Abaqus gate.
    """

    unknown = sorted(set(pipeline_fields) - _PIPELINE_FIELDS)
    missing = sorted(_REQUIRED_PIPELINE_FIELDS - set(pipeline_fields))
    if unknown or missing:
        raise TwinError(f"pipeline fields: missing {missing}, unknown {unknown}.")
    fields = dict(pipeline_fields)
    model: BoundForwardModel = fields["model"]
    if {k: float(v) for k, v in fields["start"].items()} != dict(definition.start):
        raise TwinError("the pipeline start differs from the twin definition's start.")
    if set(fields["bounds"].names) != set(definition.truth):
        raise TwinError("the bounded parameters differ from the twin definition's parameters.")
    if registration.registration_hash != model.manifest.registration_hash:
        raise TwinError("the registration is not the forward model's frozen registration.")
    work_directory = Path(work_directory)
    truth_pack, truth_journal = solve_truth(definition, model, fields["profile"], fields["expectation"],
                                            fields["roots"], work_directory / "truth", fields["abaqus_command"],
                                            *truth_executors, retry_failed_solve=retry_failed_truth_solve)
    experiment = build_synthetic_experiment(definition, truth_pack, registration)

    source = read_reference_input(model, fields["roots"])
    points = {"p0": dict(definition.start)}
    points.update(perturbed_points(definition.start, fields["settings"].finite_difference_step))
    packs, jobs = {}, {}
    for key, point in points.items():
        job = prepare_forward_job(model, forward_candidate(model, point), source, work_directory / "jobs")
        record = fields["archived_packs"].get(job.job_name)
        if record is None or record.generated_inp_sha256 != job.generated_inp_sha256:
            raise TwinError(f"no validated pack for {key} ({job.job_name}); obtaining one needs its own Abaqus gate.")
        packs[key], jobs[key] = load_shape_pack(record, fields["roots"]), job

    evidence = twin_baseline_evidence(definition, model, jobs["p0"], packs["p0"], registration, experiment)
    frozen = freeze_baseline(evidence, fields["policy"])
    observation = design_twin_observations(definition, frozen, packs["p0"],
                                           {k: v for k, v in packs.items() if k != "p0"}, len(definition.truth))
    provenance = _twin_provenance(definition, truth_pack, truth_journal, experiment, observation, packs)
    (work_directory / "twin_provenance.json").write_text(
        json.dumps(provenance, indent=1, sort_keys=True, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    config = None
    if observation.status is DesignStatus.USABLE:
        extra = dict(fields.get("extra_identity") or {})
        extra["twin"] = {"twin_definition_hash": definition.definition_hash, "noise_seed": definition.noise_seed,
                         "synthetic_experiment_sha256": experiment.content_sha256,
                         "truth_pack_content_sha256": truth_pack.record.content_sha256,
                         "twin_provenance_sha256": canonical_hash(provenance)}
        fields["extra_identity"] = extra
        config = PipelineConfig(frozen=frozen, design=observation.design, **fields)
    return TwinPreparation(definition, experiment, evidence, observation, config, truth_journal, provenance)


# ----------------------------------------------------------------------------- assessment

def assess_recovery(definition: TwinDefinition, result: LMResult) -> dict:
    """M4.9 pass criteria 1–2 (unchanged): CONVERGED, and |ln(p̂_j / p_true,j)| ≤ sd_j for every parameter.

    Criteria 3–6 (branch-exchange refusal, determinism, provenance, M3 unchanged) are gate-level
    checks, not computed here.
    """

    names = list(result.parameters)
    if set(names) != set(definition.truth):
        raise TwinError("the result's parameters differ from the twin definition's.")
    converged = result.status is LMStatus.CONVERGED
    per_parameter, within = {}, converged and result.local_sd is not None
    for index, name in enumerate(names):
        error = abs(math.log(result.parameters[name] / definition.truth[name]))
        sd = None if result.local_sd is None else float(result.local_sd[index])
        ok = sd is not None and error <= sd
        within = within and ok
        per_parameter[name] = {"estimate": result.parameters[name], "truth": definition.truth[name],
                               "abs_ln_error": error, "local_sd_ln": sd, "within_1_sigma": ok}
    return {"criterion_1_converged": converged, "criterion_2_within_1_sigma": bool(within),
            "lm_status": result.status.value, "identification_evaluations": result.solves,
            "refusal": result.refusal, "parameters": per_parameter}
