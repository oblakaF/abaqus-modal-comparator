"""Shared-carbon forward-job preparation for the primary carbon pair (CARBON PROPERTY SET v1).

One shared candidate ``(E_in_plane, G12)`` is written into each accepted
specimen's own Abaqus input as the carbon ``*Elastic, type=ENGINEERING
CONSTANTS`` record, with ``E1 = E2 = E_in_plane`` (the physical warp/fill
orientation of the supplied plates is unknown, so v1 does not separate them).
The other six constants are fixed by the property set; density, core, NSM,
mesh, ties and every other line of the accepted input are copied unchanged.
Only the eigenvalue request may differ, to give the forward job modal headroom.

This is a direct solid Engineering-Constants model, not the Stage-A affine
D-matrix model.  It prepares jobs only: no Abaqus execution, extraction or
pairing happens here.
"""

from __future__ import annotations

from dataclasses import astuple, dataclass, fields
import hashlib
import json
import math
from pathlib import Path
from typing import Optional, Sequence

__all__ = [
    "CARBON_PROPERTY_SET_V1_FIXED",
    "CarbonEngineeringConstants",
    "ForwardJobPreparationError",
    "PreparedSpecimenJob",
    "SharedCarbonCandidate",
    "SharedCarbonPreparedEvaluation",
    "SP02_REGISTRATION_HASH",
    "SP13_REGISTRATION_HASH",
    "SpecimenForwardBaseline",
    "prepare_shared_carbon_jobs",
    "sp02_forward_baseline",
    "sp13_forward_baseline",
    "write_forward_job_inp",
]

FORWARD_JOB_SCHEMA = "shared-carbon-forward-job/1"
FORWARD_EVALUATION_SCHEMA = "shared-carbon-forward-evaluation/1"
RIGID_BODY_MODE_COUNT = 6  # free-free specimens: modes 1-6 are rigid-body modes

# CARBON PROPERTY SET v1: fixed (not fitted) carbon Engineering Constants.
CARBON_PROPERTY_SET_V1_FIXED = {
    "E3": 6700.0,
    "nu12": 0.05,
    "nu13": 0.30,
    "nu23": 0.30,
    "G13": 2200.0,
    "G23": 2200.0,
}

SP02_REGISTRATION_HASH = "9bf736d3650b491f8abf5f1a9abd60f6616639fa5f2f8811a896c5a04fbdc164"
SP13_REGISTRATION_HASH = "a8970e525d10173af3d3b030b1150ca24432b616e1b52f6e8cfeefe2946f58a4"
_SP02_SOURCE_INP = Path(r"D:\Snadwich\SP-02\SP02_Modal_V02.inp")
_SP02_SOURCE_INP_SHA256 = "574ae78a897f5a666989716c54549969f13ca2919ad3af1f3ca658580a4ba8a5"
_SP13_SOURCE_INP = Path(r"D:\Snadwich\SP-13\SP13_mesh_local_v1_modal\SP13_mesh_local_v1_modal.inp")
_SP13_SOURCE_INP_SHA256 = "9d4105840e527354dbd0bb4d0d0012f7708125aa94619b0dcc486fd76dc70571"

# Material options that may appear inside a *Material block of these inputs.
_MATERIAL_OPTIONS = {"density", "elastic", "expansion", "damping", "conductivity", "specific heat"}


class ForwardJobPreparationError(ValueError):
    """The accepted input cannot be rewritten safely; nothing is guessed."""


def _positive(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a real number.")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be finite and positive.")
    return number


@dataclass(frozen=True)
class CarbonEngineeringConstants:
    """The nine Abaqus Engineering Constants, in Abaqus record order."""

    E1: float
    E2: float
    E3: float
    nu12: float
    nu13: float
    nu23: float
    G12: float
    G13: float
    G23: float

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if isinstance(value, bool) or not math.isfinite(float(value)):
                raise ValueError(f"{item.name} must be a finite real number.")
            object.__setattr__(self, item.name, float(value))

    def to_dict(self) -> dict[str, float]:
        return {item.name: getattr(self, item.name) for item in fields(self)}


@dataclass(frozen=True)
class SharedCarbonCandidate:
    """One shared v1 candidate; nu12 is fixed, never a candidate field."""

    e_in_plane_mpa: float
    g12_mpa: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "e_in_plane_mpa", _positive(self.e_in_plane_mpa, "e_in_plane_mpa"))
        object.__setattr__(self, "g12_mpa", _positive(self.g12_mpa, "g12_mpa"))

    def engineering_constants(self) -> CarbonEngineeringConstants:
        fixed = CARBON_PROPERTY_SET_V1_FIXED
        return CarbonEngineeringConstants(
            E1=self.e_in_plane_mpa,
            E2=self.e_in_plane_mpa,
            E3=fixed["E3"],
            nu12=fixed["nu12"],
            nu13=fixed["nu13"],
            nu23=fixed["nu23"],
            G12=self.g12_mpa,
            G13=fixed["G13"],
            G23=fixed["G23"],
        )

    def to_dict(self) -> dict[str, float]:
        return {"E_in_plane_mpa": self.e_in_plane_mpa, "G12_mpa": self.g12_mpa}


@dataclass(frozen=True)
class SpecimenForwardBaseline:
    """What is needed to derive one specimen's forward job from its accepted input."""

    specimen_id: str
    job_prefix: str
    source_inp: Path
    source_inp_sha256: Optional[str]
    carbon_material_name: str
    source_engineering_constants: CarbonEngineeringConstants
    source_eigenvalue_count: int
    requested_eigenvalue_count: int
    registration_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_inp", Path(self.source_inp))
        if not self.job_prefix.replace("_", "").isalnum() or not self.job_prefix[0].isalpha():
            raise ValueError("job_prefix must start with a letter and contain only letters, digits or _.")
        for name in ("source_eigenvalue_count", "requested_eigenvalue_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= RIGID_BODY_MODE_COUNT:
                raise ValueError(f"{name} must be an integer above {RIGID_BODY_MODE_COUNT}.")
        source = self.source_engineering_constants
        for name, value in CARBON_PROPERTY_SET_V1_FIXED.items():
            if getattr(source, name) != value:
                raise ValueError(
                    f"Baseline {self.specimen_id}: source {name}={getattr(source, name)} differs from "
                    f"the CARBON PROPERTY SET v1 fixed value {value}."
                )

    @property
    def elastic_mode_count(self) -> int:
        return self.requested_eigenvalue_count - RIGID_BODY_MODE_COUNT


_ACCEPTED_SOURCE_CONSTANTS = CarbonEngineeringConstants(
    E1=52000.0, E2=52000.0, E3=6700.0, nu12=0.05, nu13=0.3, nu23=0.3,
    G12=4500.0, G13=2200.0, G23=2200.0,
)


def sp02_forward_baseline(source_inp: Path = _SP02_SOURCE_INP) -> SpecimenForwardBaseline:
    """SP-02 honeycomb, accepted model SP02_Modal_V02; forward jobs request 24 elastic modes."""

    return SpecimenForwardBaseline(
        specimen_id="SP-02",
        job_prefix="SP02",
        source_inp=source_inp,
        source_inp_sha256=_SP02_SOURCE_INP_SHA256,
        carbon_material_name="CFRP_T300_PlainWeave",
        source_engineering_constants=_ACCEPTED_SOURCE_CONSTANTS,
        source_eigenvalue_count=15,
        requested_eigenvalue_count=RIGID_BODY_MODE_COUNT + 24,
        registration_hash=SP02_REGISTRATION_HASH,
    )


def sp13_forward_baseline(source_inp: Path = _SP13_SOURCE_INP) -> SpecimenForwardBaseline:
    """SP-13 auxetic, accepted model SP13_mesh_local_v1_modal; keeps its 30-eigenvalue request."""

    return SpecimenForwardBaseline(
        specimen_id="SP-13",
        job_prefix="SP13",
        source_inp=source_inp,
        source_inp_sha256=_SP13_SOURCE_INP_SHA256,
        carbon_material_name="CFRP_Face",
        source_engineering_constants=_ACCEPTED_SOURCE_CONSTANTS,
        source_eigenvalue_count=30,
        requested_eigenvalue_count=30,
        registration_hash=SP13_REGISTRATION_HASH,
    )


@dataclass(frozen=True)
class PreparedSpecimenJob:
    specimen_id: str
    candidate: SharedCarbonCandidate
    engineering_constants: CarbonEngineeringConstants
    source_inp: Path
    source_inp_sha256: str
    generated_inp: Path
    generated_inp_sha256: str
    registration_hash: str
    requested_eigenvalue_count: int
    elastic_mode_count: int
    provenance: dict
    provenance_hash: str


@dataclass(frozen=True)
class SharedCarbonPreparedEvaluation:
    candidate: SharedCarbonCandidate
    jobs: tuple[PreparedSpecimenJob, ...]
    evaluation_hash: str


def _canonical_hash(document: dict) -> str:
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _keyword(line: str) -> Optional[str]:
    """Return the lower-case keyword of a keyword line, or None for data/comment lines."""
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
    """Indices of the data lines that follow keyword line ``start`` (comments skipped)."""
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


def _line_ending(line: str) -> str:
    return line[len(line.rstrip("\r\n")):]


def _tokens(line: str) -> list[str]:
    return [token.strip() for token in line.rstrip("\r\n").split(",")]


def _format(value: float) -> str:
    return repr(float(value))


def _carbon_elastic_record(lines: list[str], material_name: str) -> tuple[int, list[int]]:
    """Locate the unique Engineering-Constants record of the named material."""
    target = material_name.lower()
    blocks = [i for i, line in enumerate(lines)
              if _keyword(line) == "material" and _parameters(line).get("name", "").lower() == target]
    if len(blocks) != 1:
        raise ForwardJobPreparationError(
            f"Expected exactly one *Material named {material_name!r}; found {len(blocks)}."
        )
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
        raise ForwardJobPreparationError(
            f"Material {material_name!r} must contain exactly one *Elastic record; found {len(elastic)}."
        )
    if _parameters(lines[elastic[0]]).get("type", "").upper() != "ENGINEERING CONSTANTS":
        raise ForwardJobPreparationError(
            f"Material {material_name!r} *Elastic is not type=ENGINEERING CONSTANTS."
        )
    data = _data_lines(lines, elastic[0])
    return elastic[0], data


def _rewrite_carbon(lines: list[str], baseline: SpecimenForwardBaseline,
                    constants: CarbonEngineeringConstants) -> None:
    _, data = _carbon_elastic_record(lines, baseline.carbon_material_name)
    rows = [[token for token in _tokens(lines[i])] for i in data]
    positions = [(row, column) for row, tokens in enumerate(rows) for column, token in enumerate(tokens) if token]
    if len(positions) != 9:
        raise ForwardJobPreparationError(
            f"Material {baseline.carbon_material_name!r} Engineering Constants must be one 9-value "
            f"record (no temperature dependence); found {len(positions)} values."
        )
    try:
        source = CarbonEngineeringConstants(*(float(rows[r][c]) for r, c in positions))
    except ValueError as exc:
        raise ForwardJobPreparationError(f"Unreadable Engineering Constants: {exc}") from exc
    if source != baseline.source_engineering_constants:
        raise ForwardJobPreparationError(
            f"Specimen {baseline.specimen_id}: source Engineering Constants {source.to_dict()} differ "
            f"from the accepted baseline {baseline.source_engineering_constants.to_dict()}."
        )
    new_values = astuple(constants)
    for index, (row, column) in enumerate(positions):
        if index in (0, 1, 6):  # E1, E2, G12 only
            rows[row][column] = _format(new_values[index])
    for row, line_index in enumerate(data):
        line = lines[line_index]
        values = [token for token in rows[row] if token]
        trailing_comma = "," if line.rstrip().endswith(",") else ""
        lines[line_index] = ", ".join(values) + trailing_comma + _line_ending(line)


def _rewrite_frequency(lines: list[str], baseline: SpecimenForwardBaseline) -> None:
    frequency = [i for i, line in enumerate(lines) if _keyword(line) == "frequency"]
    if len(frequency) != 1:
        raise ForwardJobPreparationError(
            f"Expected exactly one *Frequency step request; found {len(frequency)}."
        )
    data = _data_lines(lines, frequency[0])
    if not data:
        raise ForwardJobPreparationError("The *Frequency request has no data line.")
    tokens = _tokens(lines[data[0]])
    try:
        current = int(tokens[0])
    except ValueError as exc:
        raise ForwardJobPreparationError("The *Frequency eigenvalue count is not an integer.") from exc
    if current != baseline.source_eigenvalue_count:
        raise ForwardJobPreparationError(
            f"Specimen {baseline.specimen_id}: source requests {current} eigenvalues, expected "
            f"{baseline.source_eigenvalue_count}."
        )
    if baseline.requested_eigenvalue_count != current:
        line = lines[data[0]]
        body = line.rstrip("\r\n")
        first, separator, rest = body.partition(",")
        lines[data[0]] = str(baseline.requested_eigenvalue_count) + separator + rest + _line_ending(line)


def write_forward_job_inp(baseline: SpecimenForwardBaseline, candidate: SharedCarbonCandidate,
                          output_directory: Path) -> PreparedSpecimenJob:
    """Write one specimen's forward job INP; only the approved fields can differ from the source."""

    if not isinstance(candidate, SharedCarbonCandidate):
        raise TypeError("candidate must be a SharedCarbonCandidate.")
    raw = baseline.source_inp.read_bytes()
    source_sha = hashlib.sha256(raw).hexdigest()
    if baseline.source_inp_sha256 is not None and source_sha != baseline.source_inp_sha256:
        raise ForwardJobPreparationError(
            f"Specimen {baseline.specimen_id}: source INP SHA-256 {source_sha} differs from the "
            f"accepted {baseline.source_inp_sha256}."
        )
    lines = raw.decode("latin-1").splitlines(keepends=True)
    constants = candidate.engineering_constants()
    _rewrite_carbon(lines, baseline, constants)
    _rewrite_frequency(lines, baseline)
    generated = "".join(lines).encode("latin-1")
    generated_sha = hashlib.sha256(generated).hexdigest()

    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    target = output_directory / f"{baseline.job_prefix}_{generated_sha[:16]}.inp"
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != generated_sha:
            raise ForwardJobPreparationError(f"{target} exists with different content.")
    else:
        target.write_bytes(generated)

    provenance = {
        "schema": FORWARD_JOB_SCHEMA,
        "specimen_id": baseline.specimen_id,
        "source_inp_sha256": source_sha,
        "carbon_material_name": baseline.carbon_material_name,
        "candidate": candidate.to_dict(),
        "engineering_constants": constants.to_dict(),
        "registration_hash": baseline.registration_hash,
        "requested_eigenvalue_count": baseline.requested_eigenvalue_count,
        "elastic_mode_count": baseline.elastic_mode_count,
        "generated_inp_sha256": generated_sha,
    }
    return PreparedSpecimenJob(
        specimen_id=baseline.specimen_id,
        candidate=candidate,
        engineering_constants=constants,
        source_inp=baseline.source_inp,
        source_inp_sha256=source_sha,
        generated_inp=target,
        generated_inp_sha256=generated_sha,
        registration_hash=baseline.registration_hash,
        requested_eigenvalue_count=baseline.requested_eigenvalue_count,
        elastic_mode_count=baseline.elastic_mode_count,
        provenance=provenance,
        provenance_hash=_canonical_hash(provenance),
    )


def prepare_shared_carbon_jobs(candidate: SharedCarbonCandidate, output_directory: Path,
                               baselines: Optional[Sequence[SpecimenForwardBaseline]] = None,
                               ) -> SharedCarbonPreparedEvaluation:
    """Prepare one forward job per specimen for a single shared candidate (no Abaqus)."""

    if baselines is None:
        baselines = (sp02_forward_baseline(), sp13_forward_baseline())
    jobs = tuple(write_forward_job_inp(baseline, candidate, output_directory) for baseline in baselines)
    identifiers = [job.specimen_id for job in jobs]
    if len(set(identifiers)) != len(identifiers):
        raise ForwardJobPreparationError("Each specimen may appear only once in an evaluation.")
    document = {
        "schema": FORWARD_EVALUATION_SCHEMA,
        "candidate": candidate.to_dict(),
        "jobs": [job.provenance_hash for job in jobs],
    }
    return SharedCarbonPreparedEvaluation(candidate=candidate, jobs=jobs,
                                          evaluation_hash=_canonical_hash(document))
