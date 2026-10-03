"""Real experiment fixture manifest (Auto-ID M0.2).

A fixture record pins, by identity only, everything an Auto-ID run needs to know
about one real experiment: the experimental source file, the modal set, the
FrozenRegistration, the FE geometry/model and where the large files live.

Large files (UNV, INP, ODB) stay outside git.  A record never stores a local
absolute path: each external file is referenced by a named *store* plus a path
relative to that store's root.  The machine-specific root of each store is
supplied at run time (see ``fixture_roots_from_environment``), and every
resolved file is verified by size and SHA-256 before use.

This module only describes and verifies identities.  It does not read modal
data and does not change pairing, registration or any scientific algorithm.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping


EXPERIMENT_FIXTURE_MANIFEST_SCHEMA = "experiment-fixture-manifest/1"
FIXTURE_ROOT_ENV_PREFIX = "AUTO_ID_FIXTURE_ROOT_"
MEASUREMENT_DOF_COMPONENTS = ("U1", "U2", "U3")

_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_STORE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NULLABLE_IDENTIFIERS = ("physical_specimen_id", "experiment_id", "test_run_id")

_MANIFEST_KEYS = {"schema_version", "fixtures"}
_FIXTURE_KEYS = {
    "fixture_id", "specimen_id", "physical_specimen_id", "experiment_id", "test_run_id",
    "experimental_source", "modal_set", "registration", "fe", "provenance", "unresolved",
}
_FILE_KEYS = {"role", "file_name", "sha256", "size_bytes", "location"}
_LOCATION_KEYS = {"store", "relative_path"}
_MODAL_SET_KEYS = {
    "name", "display_name", "source_type", "mode_count", "measurement_point_count",
    "measured_dofs", "measured_face",
}
_REGISTRATION_KEYS = {"path", "schema_version", "registration_hash", "fe_geometry_sha256"}
_FE_KEYS = {"model_name", "geometry_identity", "model_input", "odb_reference"}
_GEOMETRY_KEYS = {"schema_version", "sha256", "node_count"}
_PROVENANCE_KEYS = {"created", "source_of_truth"}
_UNRESOLVED_KEYS = {"field", "reason"}


class FixtureManifestError(ValueError):
    """A fixture manifest or record violates the schema."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field


class FixtureSourceUnavailableError(FileNotFoundError):
    """An external fixture file cannot be located; nothing is substituted."""


class FixtureSourceMismatchError(ValueError):
    """An external file exists but is not the file the record pins."""


@dataclass(frozen=True)
class LocationReference:
    store: str
    relative_path: str


@dataclass(frozen=True)
class ExternalFileReference:
    role: str
    file_name: str
    sha256: str
    size_bytes: int
    location: LocationReference


@dataclass(frozen=True)
class ModalSetIdentity:
    name: str
    display_name: str
    source_type: str
    mode_count: int
    measurement_point_count: int
    measured_dofs: tuple[str, ...]
    measured_face: str


@dataclass(frozen=True)
class RegistrationIdentity:
    path: str
    schema_version: str
    registration_hash: str
    fe_geometry_sha256: str


@dataclass(frozen=True)
class FEGeometryIdentity:
    schema_version: str
    sha256: str
    node_count: int


@dataclass(frozen=True)
class FEIdentity:
    model_name: str
    geometry_identity: FEGeometryIdentity
    model_input: ExternalFileReference
    odb_reference: ExternalFileReference


@dataclass(frozen=True)
class FixtureProvenance:
    created: str
    source_of_truth: tuple[str, ...]


@dataclass(frozen=True)
class UnresolvedField:
    field: str
    reason: str


@dataclass(frozen=True)
class ExperimentFixture:
    fixture_id: str
    specimen_id: str
    physical_specimen_id: str | None
    experiment_id: str | None
    test_run_id: str | None
    experimental_source: ExternalFileReference
    modal_set: ModalSetIdentity
    registration: RegistrationIdentity
    fe: FEIdentity
    provenance: FixtureProvenance
    unresolved: tuple[UnresolvedField, ...]

    def external_files(self) -> tuple[ExternalFileReference, ...]:
        return (self.experimental_source, self.fe.model_input, self.fe.odb_reference)


@dataclass(frozen=True)
class ExperimentFixtureManifest:
    schema_version: str
    fixtures: tuple[ExperimentFixture, ...]

    def fixture(self, fixture_id: str) -> ExperimentFixture:
        for item in self.fixtures:
            if item.fixture_id == fixture_id:
                return item
        raise KeyError(fixture_id)


def _mapping(value: object, field: str, keys: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FixtureManifestError(field, "must be an object.")
    missing = sorted(keys - set(value))
    if missing:
        raise FixtureManifestError(field, f"missing required field(s) {', '.join(missing)}.")
    unknown = sorted(set(value) - keys)
    if unknown:
        raise FixtureManifestError(field, f"unknown field(s) {', '.join(unknown)}.")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FixtureManifestError(field, "must be a non-empty string.")
    return value


def _count(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FixtureManifestError(field, "must be a positive integer.")
    return value


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _HASH_PATTERN.match(value):
        raise FixtureManifestError(field, "must be a 64-character lowercase hex SHA-256.")
    return value


def _relative_path(value: object, field: str) -> str:
    text = _text(value, field)
    if "\\" in text or re.match(r"^[A-Za-z]:", text) or text.startswith("/"):
        raise FixtureManifestError(field, "must be a relative POSIX path, never a local absolute path.")
    if ".." in PurePosixPath(text).parts:
        raise FixtureManifestError(field, "must not leave its root ('..').")
    return text


def _location(value: object, field: str) -> LocationReference:
    data = _mapping(value, field, _LOCATION_KEYS)
    store = _text(data["store"], f"{field}.store")
    if not _STORE_PATTERN.match(store):
        raise FixtureManifestError(f"{field}.store", "must be a lowercase identifier (a-z, 0-9, '-').")
    return LocationReference(store, _relative_path(data["relative_path"], f"{field}.relative_path"))


def _file(value: object, field: str) -> ExternalFileReference:
    data = _mapping(value, field, _FILE_KEYS)
    reference = ExternalFileReference(
        role=_text(data["role"], f"{field}.role"),
        file_name=_text(data["file_name"], f"{field}.file_name"),
        sha256=_sha256(data["sha256"], f"{field}.sha256"),
        size_bytes=_count(data["size_bytes"], f"{field}.size_bytes"),
        location=_location(data["location"], f"{field}.location"),
    )
    if PurePosixPath(reference.location.relative_path).name != reference.file_name:
        raise FixtureManifestError(f"{field}.location", "relative_path must end with file_name.")
    return reference


def _modal_set(value: object, field: str) -> ModalSetIdentity:
    data = _mapping(value, field, _MODAL_SET_KEYS)
    dofs = data["measured_dofs"]
    if (
        not isinstance(dofs, list)
        or not dofs
        or len(set(dofs)) != len(dofs)
        or any(item not in MEASUREMENT_DOF_COMPONENTS for item in dofs)
    ):
        raise FixtureManifestError(
            f"{field}.measured_dofs", f"must be a non-empty unique subset of {MEASUREMENT_DOF_COMPONENTS}."
        )
    return ModalSetIdentity(
        name=_text(data["name"], f"{field}.name"),
        display_name=_text(data["display_name"], f"{field}.display_name"),
        source_type=_text(data["source_type"], f"{field}.source_type"),
        mode_count=_count(data["mode_count"], f"{field}.mode_count"),
        measurement_point_count=_count(data["measurement_point_count"], f"{field}.measurement_point_count"),
        measured_dofs=tuple(dofs),
        measured_face=_text(data["measured_face"], f"{field}.measured_face"),
    )


def _fixture(value: object, field: str) -> ExperimentFixture:
    data = _mapping(value, field, _FIXTURE_KEYS)

    unresolved_data = data["unresolved"]
    if not isinstance(unresolved_data, list):
        raise FixtureManifestError(f"{field}.unresolved", "must be a list.")
    unresolved = []
    for index, item in enumerate(unresolved_data):
        entry = _mapping(item, f"{field}.unresolved[{index}]", _UNRESOLVED_KEYS)
        unresolved.append(
            UnresolvedField(
                _text(entry["field"], f"{field}.unresolved[{index}].field"),
                _text(entry["reason"], f"{field}.unresolved[{index}].reason"),
            )
        )
    declared = {item.field for item in unresolved}

    identifiers = {}
    for name in _NULLABLE_IDENTIFIERS:
        if data[name] is None:
            # A missing identity must be declared with a reason, never left silently empty.
            if name not in declared:
                raise FixtureManifestError(f"{field}.{name}", "is null but not declared in unresolved.")
            identifiers[name] = None
        else:
            identifiers[name] = _text(data[name], f"{field}.{name}")
            if name in declared:
                raise FixtureManifestError(f"{field}.{name}", "has a value but is also declared unresolved.")

    registration_data = _mapping(data["registration"], f"{field}.registration", _REGISTRATION_KEYS)
    registration = RegistrationIdentity(
        path=_relative_path(registration_data["path"], f"{field}.registration.path"),
        schema_version=_text(registration_data["schema_version"], f"{field}.registration.schema_version"),
        registration_hash=_sha256(registration_data["registration_hash"], f"{field}.registration.registration_hash"),
        fe_geometry_sha256=_sha256(
            registration_data["fe_geometry_sha256"], f"{field}.registration.fe_geometry_sha256"
        ),
    )

    fe_data = _mapping(data["fe"], f"{field}.fe", _FE_KEYS)
    geometry_data = _mapping(fe_data["geometry_identity"], f"{field}.fe.geometry_identity", _GEOMETRY_KEYS)
    fe = FEIdentity(
        model_name=_text(fe_data["model_name"], f"{field}.fe.model_name"),
        geometry_identity=FEGeometryIdentity(
            schema_version=_text(geometry_data["schema_version"], f"{field}.fe.geometry_identity.schema_version"),
            sha256=_sha256(geometry_data["sha256"], f"{field}.fe.geometry_identity.sha256"),
            node_count=_count(geometry_data["node_count"], f"{field}.fe.geometry_identity.node_count"),
        ),
        model_input=_file(fe_data["model_input"], f"{field}.fe.model_input"),
        odb_reference=_file(fe_data["odb_reference"], f"{field}.fe.odb_reference"),
    )
    if registration.fe_geometry_sha256 != fe.geometry_identity.sha256:
        raise FixtureManifestError(
            f"{field}.registration.fe_geometry_sha256", "does not match fe.geometry_identity.sha256."
        )

    provenance_data = _mapping(data["provenance"], f"{field}.provenance", _PROVENANCE_KEYS)
    created = _text(provenance_data["created"], f"{field}.provenance.created")
    if not _DATE_PATTERN.match(created):
        raise FixtureManifestError(f"{field}.provenance.created", "must be an ISO date YYYY-MM-DD.")
    sources = provenance_data["source_of_truth"]
    if not isinstance(sources, list) or not sources:
        raise FixtureManifestError(f"{field}.provenance.source_of_truth", "must be a non-empty list.")

    return ExperimentFixture(
        fixture_id=_text(data["fixture_id"], f"{field}.fixture_id"),
        specimen_id=_text(data["specimen_id"], f"{field}.specimen_id"),
        experimental_source=_file(data["experimental_source"], f"{field}.experimental_source"),
        modal_set=_modal_set(data["modal_set"], f"{field}.modal_set"),
        registration=registration,
        fe=fe,
        provenance=FixtureProvenance(
            created,
            tuple(_text(item, f"{field}.provenance.source_of_truth[{index}]") for index, item in enumerate(sources)),
        ),
        unresolved=tuple(unresolved),
        **identifiers,
    )


def parse_experiment_fixture_manifest(data: object) -> ExperimentFixtureManifest:
    """Validate a decoded manifest and return immutable fixture records."""

    manifest = _mapping(data, "manifest", _MANIFEST_KEYS)
    if manifest["schema_version"] != EXPERIMENT_FIXTURE_MANIFEST_SCHEMA:
        raise FixtureManifestError(
            "manifest.schema_version", f"must be {EXPERIMENT_FIXTURE_MANIFEST_SCHEMA!r}."
        )
    items = manifest["fixtures"]
    if not isinstance(items, list) or not items:
        raise FixtureManifestError("manifest.fixtures", "must be a non-empty list.")
    fixtures = tuple(_fixture(item, f"fixtures[{index}]") for index, item in enumerate(items))
    identifiers = [item.fixture_id for item in fixtures]
    duplicates = sorted({name for name in identifiers if identifiers.count(name) > 1})
    if duplicates:
        raise FixtureManifestError("manifest.fixtures", f"duplicate fixture_id {', '.join(duplicates)}.")
    return ExperimentFixtureManifest(EXPERIMENT_FIXTURE_MANIFEST_SCHEMA, fixtures)


def load_experiment_fixture_manifest(path: Path) -> ExperimentFixtureManifest:
    with open(path, encoding="utf-8") as handle:
        return parse_experiment_fixture_manifest(json.load(handle))


def fixture_roots_from_environment(environ: Mapping[str, str] | None = None) -> dict[str, Path]:
    """Map store names to local roots from ``AUTO_ID_FIXTURE_ROOT_<STORE>`` variables.

    The store name is upper-cased with '-' replaced by '_', for example the store
    ``carbon-project-archive`` is configured by ``AUTO_ID_FIXTURE_ROOT_CARBON_PROJECT_ARCHIVE``.
    """

    environ = os.environ if environ is None else environ
    roots = {}
    for key, value in environ.items():
        if key.startswith(FIXTURE_ROOT_ENV_PREFIX) and value.strip():
            store = key[len(FIXTURE_ROOT_ENV_PREFIX):].lower().replace("_", "-")
            roots[store] = Path(value)
    return roots


def resolve_external_file(
    reference: ExternalFileReference,
    roots: Mapping[str, Path],
    *,
    verify_sha256: bool = True,
) -> Path:
    """Return the local path of a pinned external file, or refuse.

    Refuses (never substitutes) when the store is not configured, the file is
    missing, or its size or SHA-256 differs from the record.
    """

    store = reference.location.store
    if store not in roots:
        raise FixtureSourceUnavailableError(
            f"Fixture store {store!r} is not configured; set "
            f"{FIXTURE_ROOT_ENV_PREFIX}{store.upper().replace('-', '_')} to its local root."
        )
    path = Path(roots[store]).joinpath(*PurePosixPath(reference.location.relative_path).parts)
    if not path.is_file():
        raise FixtureSourceUnavailableError(
            f"{reference.role} {reference.file_name!r} not found in store {store!r} at {path}."
        )
    size = path.stat().st_size
    if size != reference.size_bytes:
        raise FixtureSourceMismatchError(
            f"{reference.file_name!r} has {size} bytes; the record pins {reference.size_bytes}."
        )
    if verify_sha256:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 22), b""):
                digest.update(chunk)
        if digest.hexdigest() != reference.sha256:
            raise FixtureSourceMismatchError(
                f"{reference.file_name!r} SHA-256 {digest.hexdigest()} does not match the record {reference.sha256}."
            )
    return path
