"""Universal manifest-driven forward builder — Auto-ID M3 (SPEC §4, §5.2, §16; AUDIT V2).

One code path for every specimen: a forward-model manifest (bound to its passport)
names the pinned reference INP, the material whose Engineering Constants a candidate
sets, the eigenvalue request and the registration.  The builder copies the reference
INP and changes only:

- the variable constants of that one material record (E1, E2, G12 for the carbon
  property set v1); E3, ν12, ν13, ν23, G13, G23 are written back unchanged;
- the eigenvalue count of the single ``*Frequency`` request, when the manifest asks
  for more modal headroom.

Mesh, geometry, core, density, adhesive, ties and every other line are copied
byte-for-byte.  It prepares jobs only: no Abaqus execution, extraction or pairing.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
from typing import Mapping, Optional, Sequence

from domain.experiment_fixture import ExperimentFixtureManifest, resolve_external_file
from domain.forward_model_manifest import (
    ENGINEERING_CONSTANTS_TYPE,
    BoundForwardModel,
    EngineeringConstants,
    ForwardCandidate,
    FrequencyRequest,
    bind_forward_model,
    canonical_hash,
    load_forward_model_manifest,
)
from domain.specimen_manifest import load_specimen_manifest


# Material options that may appear inside a *Material block of these inputs.
_MATERIAL_OPTIONS = {"density", "elastic", "expansion", "damping", "conductivity", "specific heat"}


class ForwardBuildError(ValueError):
    """The reference input cannot be rewritten safely; nothing is guessed."""


# ----------------------------------------------------------------------------- INP reading

def _keyword(line: str) -> Optional[str]:
    """Lower-case keyword of a keyword line, or None for data and comment lines."""
    if not line.startswith("*") or line.startswith("**"):
        return None
    return line[1:].split(",", 1)[0].strip().lower()


def _parameters(line: str) -> dict[str, str]:
    output = {}
    for part in line.split(",")[1:]:
        if "=" in part:
            key, value = part.split("=", 1)
            output[" ".join(key.split()).lower()] = " ".join(value.split()).strip('"')
    return output


def _data_lines(lines: list[str], start: int) -> list[int]:
    """Indices of the data lines after keyword line ``start`` (comment lines skipped)."""
    indices = []
    index = start + 1
    while index < len(lines):
        line = lines[index]
        if line.startswith("**"):
            index += 1
            continue
        if line.startswith("*"):
            break
        indices.append(index)
        index += 1
    return indices


def _strip_ending(line: str) -> str:
    return line.rstrip("\r\n")


def _line_ending(line: str) -> str:
    return line[len(line.rstrip("\r\n")):]


def _tokens(line: str) -> list[str]:
    return [token.strip() for token in line.rstrip("\r\n").split(",")]


def split_inp_lines(raw: bytes) -> list[str]:
    """Split INP bytes into lines that re-join to exactly the same bytes."""
    return raw.decode("latin-1").splitlines(keepends=True)


def join_inp_lines(lines: list[str]) -> bytes:
    return "".join(lines).encode("latin-1")


# ----------------------------------------------------------------------------- M3.1 material location

@dataclass(frozen=True)
class EngineeringConstantsRecord:
    """Where one material's Engineering-Constants record sits in an INP (0-based line indices)."""

    material_name: str
    material_line: int
    elastic_line: int
    data_lines: tuple[int, ...]
    positions: tuple[tuple[int, int], ...]  # (data row, token column) of the nine values, in record order
    values: EngineeringConstants


def locate_engineering_constants(lines: list[str], material_name: str) -> EngineeringConstantsRecord:
    """Locate the unique ``*Elastic, type=ENGINEERING CONSTANTS`` record of the named material.

    Refuses a missing or duplicated material, zero or several ``*Elastic`` options, any
    other elastic type, and anything but one temperature-independent nine-value record.
    """

    target = material_name.lower()
    blocks = [i for i, line in enumerate(lines)
              if _keyword(line) == "material" and _parameters(line).get("name", "").lower() == target]
    if len(blocks) != 1:
        raise ForwardBuildError(f"Expected exactly one *Material named {material_name!r}; found {len(blocks)}.")
    elastic = []
    index = blocks[0] + 1
    while index < len(lines):
        keyword = _keyword(lines[index])
        if keyword is not None:
            if keyword not in _MATERIAL_OPTIONS:
                break
            if keyword == "elastic":
                elastic.append(index)
        index += 1
    if len(elastic) != 1:
        raise ForwardBuildError(
            f"Material {material_name!r} must contain exactly one *Elastic record; found {len(elastic)}.")
    if _parameters(lines[elastic[0]]).get("type", "").upper() != ENGINEERING_CONSTANTS_TYPE:
        raise ForwardBuildError(f"Material {material_name!r} *Elastic is not type={ENGINEERING_CONSTANTS_TYPE}.")
    data = _data_lines(lines, elastic[0])
    rows = [_tokens(lines[i]) for i in data]
    positions = tuple((row, column) for row, tokens in enumerate(rows) for column, token in enumerate(tokens) if token)
    if len(positions) != 9:
        raise ForwardBuildError(
            f"Material {material_name!r} Engineering Constants must be one 9-value record "
            f"(no temperature dependence); found {len(positions)} values.")
    try:
        values = EngineeringConstants(*(float(rows[r][c]) for r, c in positions))
    except ValueError as exc:
        raise ForwardBuildError(f"Material {material_name!r}: unreadable Engineering Constants: {exc}") from exc
    return EngineeringConstantsRecord(material_name, blocks[0], elastic[0], tuple(data), positions, values)


# ----------------------------------------------------------------------------- M3.2 generic candidate rewrite

def _format(value: float) -> str:
    return repr(float(value))


def rewrite_engineering_constants(lines: list[str], record: EngineeringConstantsRecord,
                                  constants: EngineeringConstants, variable: tuple[str, ...]) -> None:
    """Write the ``variable`` constants of ``constants`` into the located record, in place.

    Every other value keeps its source text.  A record line is re-emitted as its values
    joined by ``", "``, keeping a trailing comma and the line ending.  A constant outside
    ``variable`` must equal the source value: a candidate never changes a fixed constant.
    """

    names = EngineeringConstants.names()
    unknown = set(variable) - set(names)
    if unknown:
        raise ForwardBuildError(f"Unknown Engineering Constants {sorted(unknown)}.")
    for name in names:
        if name not in variable and getattr(constants, name) != getattr(record.values, name):
            raise ForwardBuildError(
                f"Material {record.material_name!r}: fixed constant {name} would change from "
                f"{getattr(record.values, name)} to {getattr(constants, name)}.")
    rows = [_tokens(lines[index]) for index in record.data_lines]
    for position, (row, column) in enumerate(record.positions):
        if names[position] in variable:
            rows[row][column] = _format(getattr(constants, names[position]))
    for row, index in enumerate(record.data_lines):
        line = lines[index]
        values = [token for token in rows[row] if token]
        trailing_comma = "," if line.rstrip().endswith(",") else ""
        lines[index] = ", ".join(values) + trailing_comma + _line_ending(line)


def locate_eigenvalue_request(lines: list[str]) -> tuple[int, int]:
    """(data-line index, eigenvalue count) of the single ``*Frequency`` request."""
    frequency = [i for i, line in enumerate(lines) if _keyword(line) == "frequency"]
    if len(frequency) != 1:
        raise ForwardBuildError(f"Expected exactly one *Frequency step request; found {len(frequency)}.")
    data = _data_lines(lines, frequency[0])
    if not data:
        raise ForwardBuildError("The *Frequency request has no data line.")
    try:
        count = int(_tokens(lines[data[0]])[0])
    except ValueError as exc:
        raise ForwardBuildError("The *Frequency eigenvalue count is not an integer.") from exc
    return data[0], count


def rewrite_eigenvalue_request(lines: list[str], request: FrequencyRequest) -> Optional[int]:
    """Set the eigenvalue count; returns the changed line index, or None when unchanged."""
    index, current = locate_eigenvalue_request(lines)
    if current != request.source_eigenvalue_count:
        raise ForwardBuildError(
            f"The source requests {current} eigenvalues; the manifest records {request.source_eigenvalue_count}.")
    if request.requested_eigenvalue_count == current:
        return None
    line = lines[index]
    first, separator, rest = _strip_ending(line).partition(",")
    lines[index] = str(request.requested_eigenvalue_count) + separator + rest + _line_ending(line)
    return index


@dataclass(frozen=True)
class RenderedForwardInput:
    """Generated INP bytes plus what changed; nothing is written to disk."""

    content: bytes
    sha256: str
    source_sha256: str
    engineering_constants: EngineeringConstants
    changed_lines: tuple[int, ...]  # 0-based indices into the source lines


def render_forward_input(model: BoundForwardModel, candidate: ForwardCandidate, source: bytes) -> RenderedForwardInput:
    """Rewrite the reference INP for one candidate; only the authorised lines may change."""

    manifest = model.manifest
    if not isinstance(candidate, ForwardCandidate):
        raise TypeError("candidate must be a ForwardCandidate.")
    if candidate.parameterisation_id != manifest.parameterisation.parameterisation_id:
        raise ForwardBuildError(f"Candidate parameterisation {candidate.parameterisation_id!r} differs from the "
                                f"forward model's {manifest.parameterisation.parameterisation_id!r}.")
    source_sha = hashlib.sha256(source).hexdigest()
    if source_sha != manifest.model_input.sha256 or len(source) != manifest.model_input.size_bytes:
        raise ForwardBuildError(f"{manifest.forward_model_id}: reference INP SHA-256/size differ from the manifest.")

    source_lines = split_inp_lines(source)
    lines = list(source_lines)
    record = locate_engineering_constants(lines, model.material_name)
    if record.values != manifest.source_engineering_constants:
        raise ForwardBuildError(f"{manifest.forward_model_id}: source Engineering Constants "
                                f"{record.values.to_dict()} differ from the manifest.")
    constants = candidate.engineering_constants()
    variable = manifest.parameterisation.variable_constants
    rewrite_engineering_constants(lines, record, constants, variable)
    frequency_line = rewrite_eigenvalue_request(lines, manifest.frequency_request)

    # Independent post-check: only the record and the eigenvalue request may differ.
    if len(lines) != len(source_lines):
        raise ForwardBuildError("The rewrite changed the number of INP lines.")
    changed = tuple(i for i, (old, new) in enumerate(zip(source_lines, lines)) if old != new)
    allowed = set(record.data_lines) | ({frequency_line} if frequency_line is not None else set())
    if not set(changed) <= allowed:
        raise ForwardBuildError(f"Unauthorised INP lines changed: {sorted(set(changed) - allowed)[:5]}.")
    written = locate_engineering_constants(lines, model.material_name).values
    if written != constants:
        raise ForwardBuildError("The written Engineering Constants differ from the candidate.")

    content = join_inp_lines(lines)
    return RenderedForwardInput(content, hashlib.sha256(content).hexdigest(), source_sha, constants, changed)


# ----------------------------------------------------------------------------- M3.3 provenance / job hash

FORWARD_JOB_SCHEMA = "auto-id/forward-job/v1"
FORWARD_EVALUATION_SCHEMA = "auto-id/forward-evaluation/v1"
FORWARD_BUILDER_ID = "auto-id/forward-builder/v1"


def forward_job_name(job_prefix: str, generated_sha256: str) -> str:
    """Content-addressed job name, ``<prefix>_<first 16 hex of the generated INP SHA-256>``."""
    return f"{job_prefix}_{generated_sha256[:16]}"


@dataclass(frozen=True)
class PreparedForwardJob:
    forward_model_id: str
    candidate: ForwardCandidate
    engineering_constants: EngineeringConstants
    source_inp_sha256: str
    generated_inp: Path
    generated_inp_sha256: str
    job_name: str
    registration_hash: str
    requested_eigenvalue_count: int
    elastic_mode_count: int
    provenance: dict
    job_hash: str  # canonical SHA-256 of ``provenance``


@dataclass(frozen=True)
class PreparedForwardEvaluation:
    candidate: ForwardCandidate
    jobs: tuple[PreparedForwardJob, ...]
    evaluation_hash: str


def forward_job_provenance(model: BoundForwardModel, candidate: ForwardCandidate,
                           rendered: RenderedForwardInput) -> dict:
    """Everything that determines the job, by content: no machine path, no timestamp."""

    manifest, passport = model.manifest, model.passport
    request = manifest.frequency_request
    return {
        "schema": FORWARD_JOB_SCHEMA,
        "builder": FORWARD_BUILDER_ID,
        "forward_model": {"forward_model_id": manifest.forward_model_id, "manifest_hash": manifest.manifest_hash},
        "specimen": {
            "passport_manifest_hash": passport.manifest_hash,
            "design_id": str(passport.design_id),
            "physical_specimen_id": None if passport.physical_specimen_id is None else str(passport.physical_specimen_id),
            "test_run_id": str(passport.test_run_id),
        },
        "source_inp": {"file_name": manifest.model_input.file_name, "sha256": rendered.source_sha256,
                       "size_bytes": manifest.model_input.size_bytes},
        "material": {"role": manifest.material_role, "name": model.material_name,
                     "elastic_type": ENGINEERING_CONSTANTS_TYPE},
        "parameterisation": manifest.parameterisation.parameterisation_id,
        "candidate": candidate.to_dict(),
        "engineering_constants": rendered.engineering_constants.to_dict(),
        "registration_hash": manifest.registration_hash,
        "frequency_request": {"source_eigenvalue_count": request.source_eigenvalue_count,
                              "requested_eigenvalue_count": request.requested_eigenvalue_count,
                              "elastic_mode_count": request.elastic_mode_count},
        "generated_inp": {"sha256": rendered.sha256, "size_bytes": len(rendered.content),
                          "job_name": forward_job_name(manifest.job_prefix, rendered.sha256),
                          "changed_lines": [index + 1 for index in rendered.changed_lines]},
    }


def _write_content_addressed(target: Path, content: bytes, sha256: str) -> None:
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != sha256:
            raise ForwardBuildError(f"{target} exists with different content.")
        return
    partial = target.with_name(target.name + ".partial")
    partial.write_bytes(content)
    os.replace(partial, target)


def prepare_forward_job(model: BoundForwardModel, candidate: ForwardCandidate, source: bytes,
                        output_directory: Path) -> PreparedForwardJob:
    """Render and write one forward job INP (content-addressed name) with its provenance."""

    rendered = render_forward_input(model, candidate, source)
    provenance = forward_job_provenance(model, candidate, rendered)
    name = provenance["generated_inp"]["job_name"]
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    target = output_directory / f"{name}.inp"
    _write_content_addressed(target, rendered.content, rendered.sha256)
    request = model.manifest.frequency_request
    return PreparedForwardJob(
        forward_model_id=model.manifest.forward_model_id,
        candidate=candidate,
        engineering_constants=rendered.engineering_constants,
        source_inp_sha256=rendered.source_sha256,
        generated_inp=target,
        generated_inp_sha256=rendered.sha256,
        job_name=name,
        registration_hash=model.manifest.registration_hash,
        requested_eigenvalue_count=request.requested_eigenvalue_count,
        elastic_mode_count=request.elastic_mode_count,
        provenance=provenance,
        job_hash=canonical_hash(provenance),
    )


def forward_evaluation_hash(candidate: ForwardCandidate, jobs: Sequence[PreparedForwardJob]) -> str:
    return canonical_hash({
        "schema": FORWARD_EVALUATION_SCHEMA,
        "parameterisation": candidate.parameterisation_id,
        "candidate": candidate.to_dict(),
        "jobs": [{"forward_model_id": job.forward_model_id, "job_hash": job.job_hash} for job in jobs],
    })


def _check_distinct(models: Sequence[BoundForwardModel]) -> None:
    for attribute in ("forward_model_id", "job_prefix"):
        values = [getattr(model.manifest, attribute) for model in models]
        if len(set(values)) != len(values):
            raise ForwardBuildError(f"Each forward model may appear only once in an evaluation ({attribute}).")



def prepare_forward_evaluation(models: Sequence[BoundForwardModel], sources: Sequence[bytes],
                               candidate: ForwardCandidate, output_directory: Path) -> PreparedForwardEvaluation:
    """One forward job per forward model for a single shared candidate (no Abaqus)."""

    if len(models) != len(sources) or not models:
        raise ForwardBuildError("Give one reference INP per forward model.")
    _check_distinct(models)
    jobs = tuple(prepare_forward_job(model, candidate, source, output_directory)
                 for model, source in zip(models, sources))
    return PreparedForwardEvaluation(candidate, jobs, forward_evaluation_hash(candidate, jobs))


# ----------------------------------------------------------------------------- M3.4 manifest-driven inputs

def load_bound_forward_model(manifest_path: Path, repo_root: Path,
                             fixtures: Optional[ExperimentFixtureManifest] = None) -> BoundForwardModel:
    """Load a forward-model manifest and its pinned passport (repository-relative), then bind them."""

    manifest = load_forward_model_manifest(manifest_path)
    passport_path = Path(repo_root).joinpath(*PurePosixPath(manifest.specimen_passport.path).parts)
    return bind_forward_model(manifest, load_specimen_manifest(passport_path), fixtures)


def read_reference_input(model: BoundForwardModel, roots: Mapping[str, Path]) -> bytes:
    """Read the pinned reference INP from its configured store (``AUTO_ID_FIXTURE_ROOT_<STORE>``).

    Refuses an unconfigured store, a missing file or a size mismatch; the SHA-256 is
    verified on the bytes actually used, when the job is rendered.
    """

    return resolve_external_file(model.manifest.model_input, roots, verify_sha256=False).read_bytes()


def prepare_forward_jobs(models: Sequence[BoundForwardModel], candidate: ForwardCandidate,
                         roots: Mapping[str, Path], output_directory: Path) -> PreparedForwardEvaluation:
    """Prepare one job per explicitly given forward model; there are no default specimens."""

    if not models:
        raise ForwardBuildError("Give at least one forward model; there are no default specimens.")
    _check_distinct(models)
    return prepare_forward_evaluation(models, [read_reference_input(model, roots) for model in models],
                                      candidate, output_directory)
