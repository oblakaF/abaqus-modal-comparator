"""Forward-model manifest — Auto-ID M3 (SPEC §4, §5.2, §16; AUDIT V2).

A forward-model manifest binds one accepted Abaqus input to its specimen passport.
It records, as data:

- which pinned INP is the reference model;
- which passport material role carries the rewritten face-sheet constants (the
  material *name* comes from the passport, SPEC §4);
- the accepted source Engineering Constants that the INP must contain;
- the parameterisation (which constants may vary);
- the eigenvalue request of the forward job;
- the FrozenRegistration the job is compared through.

Specimen-specific values live in these manifests, never in code.  Parsing is pure and
strict: unknown fields, absolute paths and inconsistent constants are refused.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping

from .experiment_fixture import ExperimentFixtureManifest, ExternalFileReference, FixtureManifestError
from .experiment_fixture import _file as _external_file
from .specimen_manifest import SpecimenManifest


FORWARD_MODEL_SCHEMA = "auto-id/forward-model/v1"
RIGID_BODY_MODE_COUNT = 6  # free-free specimens: modes 1-6 are rigid-body modes
ENGINEERING_CONSTANTS_TYPE = "ENGINEERING CONSTANTS"

_HASH = re.compile(r"^[0-9a-f]{64}$")
_JOB_PREFIX = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_TOP_KEYS = {"schema", "forward_model_id", "specimen_passport", "model_input", "job_prefix", "material",
             "parameterisation", "frequency_request", "registration", "provenance"}


class ForwardModelManifestError(ValueError):
    """A forward-model manifest is malformed or inconsistent; nothing is guessed."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field


def _fail(field: str, message: str):
    raise ForwardModelManifestError(field, message)


@dataclass(frozen=True)
class EngineeringConstants:
    """The nine Abaqus ``*Elastic, type=ENGINEERING CONSTANTS`` values, in record order."""

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
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError(f"{item.name} must be a finite real number.")
            object.__setattr__(self, item.name, float(value))

    @classmethod
    def names(cls) -> tuple[str, ...]:
        return tuple(item.name for item in fields(cls))

    def as_tuple(self) -> tuple[float, ...]:
        return tuple(getattr(self, name) for name in self.names())

    def to_dict(self) -> dict[str, float]:
        return {name: getattr(self, name) for name in self.names()}


@dataclass(frozen=True)
class Parameterisation:
    """Which Engineering Constants a forward candidate may set; every other constant is fixed."""

    parameterisation_id: str
    material_role: str  # passport materials role whose record is rewritten
    variable_constants: tuple[str, ...]
    fixed_constants: Mapping[str, float]


# CARBON PROPERTY SET v1 (SPEC §5.2): E1 = E2 = E_in_plane and G12 vary; E3, ν12, ν13, ν23,
# G13, G23 are fixed.  E1 ≠ E2 has no parameterisation (it needs traceable warp/fill).
CARBON_PROPERTY_SET_V1 = Parameterisation(
    parameterisation_id="carbon-property-set/v1",
    material_role="face",
    variable_constants=("E1", "E2", "G12"),
    fixed_constants={"E3": 6700.0, "nu12": 0.05, "nu13": 0.30, "nu23": 0.30, "G13": 2200.0, "G23": 2200.0},
)
PARAMETERISATIONS: Mapping[str, Parameterisation] = {
    CARBON_PROPERTY_SET_V1.parameterisation_id: CARBON_PROPERTY_SET_V1,
}


@dataclass(frozen=True)
class PassportReference:
    path: str  # repository-relative POSIX path
    manifest_hash: str


@dataclass(frozen=True)
class FrequencyRequest:
    source_eigenvalue_count: int
    requested_eigenvalue_count: int

    @property
    def elastic_mode_count(self) -> int:
        return self.requested_eigenvalue_count - RIGID_BODY_MODE_COUNT


@dataclass(frozen=True)
class ForwardModelManifest:
    forward_model_id: str
    specimen_passport: PassportReference
    model_input: ExternalFileReference
    job_prefix: str
    material_role: str
    source_engineering_constants: EngineeringConstants
    parameterisation: Parameterisation
    frequency_request: FrequencyRequest
    registration_hash: str
    registration_path: str | None
    source_of_truth: tuple[str, ...]
    canonical: Mapping[str, Any]

    @property
    def manifest_hash(self) -> str:
        return canonical_hash(self.canonical)


@dataclass(frozen=True)
class BoundForwardModel:
    """A forward-model manifest checked against its passport (and fixture, when linked)."""

    manifest: ForwardModelManifest
    passport: SpecimenManifest
    material_name: str  # resolved from the passport's materials by role


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _mapping(value: object, field: str, required: set[str], optional: set[str] = frozenset()) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(field, "must be an object.")
    missing = sorted(required - set(value))
    if missing:
        _fail(field, f"missing required field(s) {', '.join(missing)}.")
    unknown = sorted(set(value) - required - set(optional))
    if unknown:
        _fail(field, f"unknown field(s) {', '.join(unknown)}.")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        _fail(field, "must be a non-empty string without surrounding whitespace.")
    return value


def _hash(value: object, field: str) -> str:
    if not isinstance(value, str) or not _HASH.match(value):
        _fail(field, "must be a 64-character lowercase hex SHA-256.")
    return value


def _repo_path(value: object, field: str) -> str:
    text = _text(value, field)
    if "\\" in text or re.match(r"^[A-Za-z]:", text) or text.startswith("/") or ".." in text.split("/"):
        _fail(field, "must be a repository-relative POSIX path.")
    return text


def _count(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= RIGID_BODY_MODE_COUNT:
        _fail(field, f"must be an integer above {RIGID_BODY_MODE_COUNT} (rigid-body modes).")
    return value


def _constants(value: object, field: str) -> EngineeringConstants:
    names = set(EngineeringConstants.names())
    data = _mapping(value, field, names)
    try:
        return EngineeringConstants(**{name: data[name] for name in EngineeringConstants.names()})
    except ValueError as exc:
        _fail(field, str(exc))


def parse_forward_model_manifest(data: object) -> ForwardModelManifest:
    data = _mapping(data, "manifest", _TOP_KEYS)
    if data["schema"] != FORWARD_MODEL_SCHEMA:
        _fail("schema", f"must be {FORWARD_MODEL_SCHEMA!r}.")
    model_id = _text(data["forward_model_id"], "forward_model_id")
    if not _IDENTIFIER.match(model_id):
        _fail("forward_model_id", "must use letters, digits, '.', '_', '-' or '/'.")

    passport_data = _mapping(data["specimen_passport"], "specimen_passport", {"path", "manifest_hash"})
    passport = PassportReference(_repo_path(passport_data["path"], "specimen_passport.path"),
                                 _hash(passport_data["manifest_hash"], "specimen_passport.manifest_hash"))
    try:
        model_input = _external_file(data["model_input"], "model_input")
    except FixtureManifestError as exc:
        _fail(exc.field, str(exc))

    prefix = data["job_prefix"]
    if not isinstance(prefix, str) or not _JOB_PREFIX.match(prefix):
        _fail("job_prefix", "must start with a letter and contain only letters, digits or '_'.")

    parameterisation_id = data["parameterisation"]
    if parameterisation_id not in PARAMETERISATIONS:
        _fail("parameterisation", f"unknown parameterisation {parameterisation_id!r}; known: "
                                  f"{', '.join(sorted(PARAMETERISATIONS))}.")
    parameterisation = PARAMETERISATIONS[parameterisation_id]

    material = _mapping(data["material"], "material", {"role", "elastic_type", "source_engineering_constants"})
    role = _text(material["role"], "material.role")
    if role != parameterisation.material_role:
        _fail("material.role", f"{parameterisation_id} rewrites the {parameterisation.material_role!r} material.")
    if material["elastic_type"] != ENGINEERING_CONSTANTS_TYPE:
        _fail("material.elastic_type", f"must be {ENGINEERING_CONSTANTS_TYPE!r}.")
    source = _constants(material["source_engineering_constants"], "material.source_engineering_constants")
    for name, value in parameterisation.fixed_constants.items():
        if getattr(source, name) != value:
            _fail("material.source_engineering_constants",
                  f"{name}={getattr(source, name)} differs from the {parameterisation_id} fixed value {value}.")

    frequency = _mapping(data["frequency_request"], "frequency_request",
                         {"source_eigenvalue_count", "requested_eigenvalue_count"})
    request = FrequencyRequest(_count(frequency["source_eigenvalue_count"], "frequency_request.source_eigenvalue_count"),
                               _count(frequency["requested_eigenvalue_count"],
                                      "frequency_request.requested_eigenvalue_count"))

    registration = _mapping(data["registration"], "registration", {"registration_hash"}, {"path"})
    registration_hash = _hash(registration["registration_hash"], "registration.registration_hash")
    registration_path = None
    if registration.get("path") is not None:
        registration_path = _repo_path(registration["path"], "registration.path")

    provenance = _mapping(data["provenance"], "provenance", {"source_of_truth"})
    sources = provenance["source_of_truth"]
    if not isinstance(sources, list) or not sources:
        _fail("provenance.source_of_truth", "must be a non-empty list.")
    sources = tuple(_text(item, "provenance.source_of_truth[]") for item in sources)

    canonical = {
        "schema": FORWARD_MODEL_SCHEMA,
        "forward_model_id": model_id,
        "specimen_passport": {"path": passport.path, "manifest_hash": passport.manifest_hash},
        "model_input": {"role": model_input.role, "file_name": model_input.file_name, "sha256": model_input.sha256,
                        "size_bytes": model_input.size_bytes,
                        "location": {"store": model_input.location.store,
                                     "relative_path": model_input.location.relative_path}},
        "job_prefix": prefix,
        "material": {"role": role, "elastic_type": ENGINEERING_CONSTANTS_TYPE,
                     "source_engineering_constants": source.to_dict()},
        "parameterisation": parameterisation_id,
        "frequency_request": {"source_eigenvalue_count": request.source_eigenvalue_count,
                              "requested_eigenvalue_count": request.requested_eigenvalue_count},
        "registration": {"registration_hash": registration_hash, "path": registration_path},
        "provenance": {"source_of_truth": list(sources)},
    }
    return ForwardModelManifest(model_id, passport, model_input, prefix, role, source, parameterisation, request,
                                registration_hash, registration_path, sources, canonical)


def load_forward_model_manifest(path: Path) -> ForwardModelManifest:
    with open(path, encoding="utf-8") as handle:
        return parse_forward_model_manifest(json.load(handle))


def bind_forward_model(manifest: ForwardModelManifest, passport: SpecimenManifest,
                       fixtures: ExperimentFixtureManifest | None = None) -> BoundForwardModel:
    """Check a manifest against its passport (and linked fixture) and resolve the material name.

    The passport is pinned by its canonical hash; the material name is taken from the
    passport's ``materials`` by role (SPEC §4), never from code.  When the passport links
    an experiment fixture, the fixture's pinned model input and registration must agree.
    """

    if passport.manifest_hash != manifest.specimen_passport.manifest_hash:
        _fail("specimen_passport.manifest_hash",
              f"the passport hash {passport.manifest_hash} differs from the pinned "
              f"{manifest.specimen_passport.manifest_hash}.")
    materials = passport.materials or {}
    if manifest.material_role not in materials:
        _fail("material.role", f"the passport records no {manifest.material_role!r} material.")
    material_name = materials[manifest.material_role]

    fixture_id = passport.acquisition.fixture_id
    if fixture_id is not None and fixtures is not None:
        fixture = fixtures.fixture(fixture_id)
        if fixture.fe.model_input != manifest.model_input:
            _fail("model_input", f"differs from the model input pinned by fixture {fixture_id}.")
        if fixture.registration.registration_hash != manifest.registration_hash:
            _fail("registration.registration_hash", f"differs from the registration of fixture {fixture_id}.")
        if (manifest.registration_path is not None
                and fixture.registration.path != manifest.registration_path):
            _fail("registration.path", f"differs from the registration path of fixture {fixture_id}.")
        if fixture.fe.model_name != passport.fe_reference.model_name:
            _fail("specimen_passport", f"passport FE model differs from fixture {fixture_id}.")
    return BoundForwardModel(manifest, passport, material_name)
