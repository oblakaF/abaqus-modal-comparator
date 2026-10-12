"""Governed specimen records of a campaign draft specimen — Auto-ID M8-D2d (read-only; nothing is chosen).

For one governed specimen input (a forward-model manifest bound through the governed binder), find the four governed
records a campaign specimen references — ``solver_profile``, ``archived_baseline``, ``baseline_shape_pack`` and
``registration_evidence`` — among the repository's governed record folders, using the production loaders and the
production identity checks:

- solver profile (``docs/auto_id/solver_profiles``): ``load_solver_profile``; forward_model_id and job_prefix equal to
  the forward model's (the campaign preparation check);
- archived baseline (``docs/auto_id/baselines``): ``load_archived_baseline``; its own forward-model manifest unchanged
  (manifest hash) and the same forward model (forward_model_id, job_prefix); bound to the specimen's experiment fixture
  (FE ODB, FE geometry, experimental source, modal set — the G2c binding rule); its generated INP is the accepted
  CARBON-4C BASELINE job of this specimen in the pinned ``accepted_forward_jobs.json`` (same parameter values);
- baseline shape pack (``docs/auto_id/fe_shapes``): ``load_shape_pack_record``; specimen, state BASELINE and the
  production pack-to-baseline rule ``archived_baseline._bind_pack`` against the fixture's physical registration (job,
  generated INP, ODB, FE geometry, node set, FE modes and exact frequencies) — on the record, whose validated modes
  and frequencies equal the pack's; the pack file in its data store is not read here;
- registration evidence (``docs/auto_id/registration_evidence``): an ``auto-id/registration-uncertainty-evaluation/v1``
  record (the M2.4 record carrying ``registration_limited``) of the fixture's registration (registration hash = the
  fixture's = the forward model's; the same registration file) and of the bound baseline pack.

A specimen is bound only when **every** one of the four fields has exactly one compatible candidate (atomic). Zero or
several candidates, or an incompatible specimen, refuse the binding with the reasons and the candidates; nothing is
ever selected by order or name, and no alternative is substituted. Each bound record is fingerprinted with its
canonical content SHA-256 (``record_hash``: independent of key order and line endings).

Bound records are governed references only. They are not FIT / HOLDOUT rows, parameters, covariance, tolerances or
solver settings, and binding them is not a scientific readiness verdict. Nothing here runs Abaqus, FE, LM or a solve.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Optional

from domain.experiment_fixture import ExperimentFixtureManifest
from domain.identification_run import load_solver_profile
from domain.registration import FrozenRegistration

from .archived_baseline import _bind_pack, load_archived_baseline, record_hash
from .archived_sensitivity_evidence import ACCEPTED_FORWARD_JOBS, ACCEPTED_FORWARD_JOBS_HASH, BASELINE_CANDIDATE
from .fe_shape_pack import load_shape_pack_record
from .forward_builder import load_bound_forward_model

FIELDS = ("solver_profile", "archived_baseline", "baseline_shape_pack", "registration_evidence")
DIRECTORIES = {
    "solver_profile": (PurePosixPath("docs/auto_id/solver_profiles"), "*.json"),
    "archived_baseline": (PurePosixPath("docs/auto_id/baselines"), "*.json"),
    "baseline_shape_pack": (PurePosixPath("docs/auto_id/fe_shapes"), "*.shape-pack.json"),
    "registration_evidence": (PurePosixPath("docs/auto_id/registration_evidence"), "*.json"),
}
REGISTRATION_EVIDENCE_SCHEMA = "auto-id/registration-uncertainty-evaluation/v1"  # the M2.4 registration_limited record
BOUND, REFUSED = "BOUND", "REFUSED"
BINDING_NOTE = ("governed references only (not FIT / HOLDOUT rows, parameters, covariance, tolerances or solver "
                "settings); binding them is not a scientific readiness verdict")


@dataclass(frozen=True)
class BoundRecord:
    path: str  # repository-relative POSIX path
    canonical_sha256: str  # record_hash of the record's JSON content

    def to_dict(self) -> dict:
        return {"path": self.path, "canonical_sha256": self.canonical_sha256}


@dataclass(frozen=True)
class SpecimenRecords:
    """The four governed records of one campaign specimen (bound together or not at all)."""

    solver_profile: BoundRecord
    archived_baseline: BoundRecord
    baseline_shape_pack: BoundRecord
    registration_evidence: BoundRecord

    def to_dict(self) -> dict:
        return {name: getattr(self, name).to_dict() for name in FIELDS}

    def paths(self) -> dict:
        return {name: getattr(self, name).path for name in FIELDS}


@dataclass(frozen=True)
class RecordBinding:
    """The outcome for one specimen: BOUND with its records, or REFUSED with the reasons (nothing bound)."""

    forward_model: str
    status: str
    records: Optional[SpecimenRecords]
    candidates: tuple[tuple[str, tuple[str, ...]], ...]  # field -> compatible candidate paths
    reasons: tuple[str, ...]

    def summary(self) -> str:
        if self.status == BOUND:
            return f"{self.forward_model}: BOUND " + ", ".join(f"{k} {v}" for k, v in self.records.paths().items())
        return f"{self.forward_model}: REFUSED — " + "; ".join(self.reasons)


def _relative(path: Path, root: Path) -> str:
    return PurePosixPath(path.resolve().relative_to(root).as_posix()).as_posix()


def _files(root: Path, field: str) -> list[Path]:
    folder, pattern = DIRECTORIES[field]
    directory = root.joinpath(*folder.parts)
    return sorted(path for path in directory.glob(pattern) if path.is_file()) if directory.is_dir() else []


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _check(checks: dict) -> list[str]:
    return sorted(name for name, ok in checks.items() if not ok)


def bind_governed_specimen_records(forward_model: str, repo_root: Path,
                                   fixtures: ExperimentFixtureManifest) -> RecordBinding:
    """The four governed records of the specimen whose forward-model manifest is ``forward_model`` (read-only)."""

    root = Path(repo_root).resolve()
    reasons: list[str] = []

    def refused(*extra: str, candidates=()) -> RecordBinding:
        return RecordBinding(forward_model, REFUSED, None, tuple(candidates), tuple(reasons) + extra)

    if not isinstance(fixtures, ExperimentFixtureManifest):
        return refused("the governed experiment-fixture catalogue is not loaded and validated")
    try:
        model = load_bound_forward_model(root.joinpath(*PurePosixPath(forward_model).parts), root, fixtures)
        manifest, passport = model.manifest, model.passport
        fixture = fixtures.fixture(passport.acquisition.fixture_id)
        registration_file = root.joinpath(*PurePosixPath(fixture.registration.path).parts)
        registration = FrozenRegistration.from_dict(_json(registration_file))
    except Exception as error:  # noqa: BLE001 - any unreadable input refuses (fail-closed)
        return refused(f"the specimen input or its fixture / registration cannot be loaded ({error})")
    if not registration.registration_hash == fixture.registration.registration_hash == manifest.registration_hash:
        return refused("the fixture's registration, its file and the forward model's registration hash differ")
    label = manifest.job_prefix
    rejected: dict[str, list[str]] = {name: [] for name in FIELDS}

    # solver profile ------------------------------------------------------------------------------------------------
    profiles = []
    for path in _files(root, "solver_profile"):
        name = _relative(path, root)
        try:
            profile = load_solver_profile(path)
        except Exception as error:  # noqa: BLE001
            rejected["solver_profile"].append(f"{name}: not a solver profile ({error})")
            continue
        failed = _check({"forward_model_id": profile.forward_model_id == manifest.forward_model_id,
                         "job_prefix": profile.job_prefix == manifest.job_prefix})
        if failed:
            rejected["solver_profile"].append(f"{name}: {failed} differ")
        else:
            profiles.append(name)

    # archived baseline ---------------------------------------------------------------------------------------------
    jobs = None
    try:
        jobs_document = _json(root.joinpath(*PurePosixPath(ACCEPTED_FORWARD_JOBS).parts))
        if record_hash(jobs_document) == ACCEPTED_FORWARD_JOBS_HASH:
            jobs = jobs_document
        else:
            reasons.append(f"{ACCEPTED_FORWARD_JOBS} differs from its pinned content: no generated INP is accepted")
    except Exception as error:  # noqa: BLE001
        reasons.append(f"{ACCEPTED_FORWARD_JOBS} cannot be read ({error}): no generated INP is accepted")
    accepted_job = None
    if jobs is not None:
        candidates = [c for c in jobs.get("candidates", ()) if c.get("name") == BASELINE_CANDIDATE]
        if len(candidates) == 1:
            accepted_job = candidates[0]
    baselines = {}
    for path in _files(root, "archived_baseline"):
        name = _relative(path, root)
        try:
            baseline = load_archived_baseline(path)
            source = load_bound_forward_model(root.joinpath(*PurePosixPath(baseline.forward_model_path).parts), root,
                                              fixtures).manifest
        except Exception as error:  # noqa: BLE001
            rejected["archived_baseline"].append(f"{name}: not an archived baseline of a governed forward model "
                                                 f"({error})")
            continue
        job = (accepted_job or {}).get("jobs", {}).get(label, {})
        failed = _check({
            "forward_model_hash": source.manifest_hash == baseline.forward_model_hash,
            "forward_model_id": source.forward_model_id == manifest.forward_model_id,
            "job_prefix": source.job_prefix == manifest.job_prefix,
            "fixture_odb": baseline.odb.sha256 == fixture.fe.odb_reference.sha256,
            "fixture_fe_geometry": baseline.fe_geometry_sha256 == fixture.fe.geometry_identity.sha256,
            "fixture_experimental_source": baseline.experimental_source_sha256 == fixture.experimental_source.sha256,
            "fixture_modal_set": baseline.modal_set == fixture.modal_set.name,
            "accepted_generated_inp": accepted_job is not None
            and job.get("generated_inp_sha256") == baseline.generated_inp_sha256,
            "accepted_parameters": accepted_job is not None
            and dict(baseline.candidate) == {"E_in_plane_mpa": accepted_job.get("e_in_plane_mpa"),
                                             "G12_mpa": accepted_job.get("g12_mpa")},
        })
        if failed:
            rejected["archived_baseline"].append(f"{name}: {failed} differ")
        else:
            baselines[name] = baseline

    # baseline shape pack -------------------------------------------------------------------------------------------
    packs = {}
    for path in _files(root, "baseline_shape_pack"):
        name = _relative(path, root)
        try:
            record = load_shape_pack_record(path)
        except Exception as error:  # noqa: BLE001
            rejected["baseline_shape_pack"].append(f"{name}: not a shape-pack record ({error})")
            continue
        if record.specimen != label or record.state != "BASELINE":
            rejected["baseline_shape_pack"].append(f"{name}: specimen {record.specimen} / state {record.state}")
            continue
        view = SimpleNamespace(record=record, mode_numbers=record.mode_numbers, frequencies_hz=record.frequencies_hz)
        matches = []
        for baseline_name, baseline in baselines.items():
            try:
                _bind_pack(baseline, view, registration, same_registration=False)  # the production pack rule
            except Exception:  # noqa: BLE001
                continue
            matches.append(baseline_name)
        if matches and record.odb.sha256 == fixture.fe.odb_reference.sha256:
            packs[name] = record
        else:
            rejected["baseline_shape_pack"].append(f"{name}: does not belong to a compatible archived baseline "
                                                   "(job, generated INP, ODB, FE geometry, node set, modes)")

    # registration evidence -----------------------------------------------------------------------------------------
    pack_jobs = {record.job_name for record in packs.values()}
    evidence = []
    for path in _files(root, "registration_evidence"):
        name = _relative(path, root)
        try:
            document = _json(path)
        except Exception as error:  # noqa: BLE001
            rejected["registration_evidence"].append(f"{name}: unreadable ({error})")
            continue
        if not isinstance(document, dict) or document.get("schema") != REGISTRATION_EVIDENCE_SCHEMA:
            continue  # another kind of registration record (reconstruction, re-evaluation), never a candidate
        failed = _check({
            "registration_hash": document.get("registration_hash") == fixture.registration.registration_hash,
            "registration_file": document.get("registration_file") == fixture.registration.path,
            "registration_limited": isinstance(document.get("registration_limited"), bool),
            "baseline_pack": document.get("pack") in pack_jobs,
        })
        if failed:
            rejected["registration_evidence"].append(f"{name}: {failed} differ")
        else:
            evidence.append(name)

    found = {"solver_profile": profiles, "archived_baseline": sorted(baselines),
             "baseline_shape_pack": sorted(packs), "registration_evidence": evidence}
    candidates = tuple((name, tuple(found[name])) for name in FIELDS)
    for name in FIELDS:
        if not found[name]:
            detail = "; ".join(rejected[name]) or "no record in the governed folder"
            reasons.append(f"{name}: no compatible record ({detail})")
        elif len(found[name]) > 1:
            reasons.append(f"{name}: {len(found[name])} compatible records {found[name]} — ambiguous, none is chosen")
    if reasons:
        return refused(candidates=candidates)
    records = SpecimenRecords(**{name: BoundRecord(found[name][0], record_hash(_json(root.joinpath(
        *PurePosixPath(found[name][0]).parts)))) for name in FIELDS})
    return RecordBinding(forward_model, BOUND, records, candidates, ())
