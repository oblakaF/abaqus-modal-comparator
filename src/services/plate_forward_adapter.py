"""Two interchangeable offline forward backends behind one contract.

``KIRCHHOFF_RITZ_4D`` wraps the standalone solver in :mod:`services.plate_ritz_forward`.
``STAGE_A_MATRIX_3D`` is a read-only adapter to an already prepared Stage-A matrix package. It reuses
``StageAAffineBasis``, ``solve_generalized_eigenproblem`` and ``compute_stage_a_sensitivity``, and
keeps D22 = D11, the stored validity domain, the DOF identities and the stored mass behaviour.

Neither backend can start Abaqus, generate matrices or fall back to another model. A missing or
incompatible package disables only the Stage-A backend. Results are forward predictions only.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Tuple
import zipfile

import numpy as np
from scipy import sparse

from domain.plate_material_problem import (
    BackendAvailability,
    BackendCapabilities,
    CoordinateObservationSet,
    DofObservationSet,
    EvidenceKind,
    ExecutionStatus,
    ForwardBackendId,
    ForwardProvenance,
    ObservationEvaluation,
    PlateBendingParameters,
    PlateForwardRefusal,
    PlateForwardResult,
    PlateGeometry,
    RefusalCode,
    ResourceLimits,
    ShapeKind,
    ShapeRepresentation,
    identity_hash,
)

from .matrix_model_service import (
    STAGE_A_PARAMETER_NAMES,
    AbaqusDof,
    MatrixModelError,
    StageAAffineBasis,
    StageAMatrixNodeMap,
    StageAMatrixNodeMapError,
    StageAMatrixParameters,
    solve_generalized_eigenproblem,
)
from .plate_ritz_forward import (
    RITZ_BACKEND_VERSION,
    RITZ_DOF_ORDERING,
    RITZ_STIFFNESS_NAMES,
    RitzForwardSolution,
    RitzNumericalConfig,
    RitzSensitivities,
    evaluate_ritz_observations,
    ritz_model_identity,
    ritz_sensitivities,
    solve_ritz,
)
from .sensitivity_service import (
    ScalarModeSensitivityRefusal,
    SensitivityResult,
    StageASensitivityCoordinate,
    compute_stage_a_sensitivity,
)
from .stage_a_identification_service import stage_a_basis_identity


STAGE_A_ADAPTER_VERSION = "stage-a-matrix-adapter/1"
STAGE_A_PACKAGE_SCHEMA = "abm/stage-a-matrix-package/v1"
STAGE_A_PACKAGE_MANIFEST = "stage_a_package.json"
STAGE_A_MODEL_KIND = "STAGE_A_AFFINE_BASIS"
STAGE_A_CONSTRAINT = "D22=D11"
MASS_SLOPE_PRESENT = "STORED_DM_DD11"
MASS_SLOPE_ABSENT = "ABSENT_LEGACY_CONSTANT_M"
# Value of 1 N*m in each package unit system. Frequencies are in Hz in both.
_STAGE_A_D_PER_N_M = {"N-m-kg-s": 1.0, "N-mm-t-s": 1000.0}
_MATRIX_MEMBERS = ("K_ref", "K_D11", "K_D12", "K_D66", "M_ref")
_MANIFEST_REQUIRED = (
    "schema",
    "model_kind",
    "model_id",
    "specimen_id",
    "evidence_kind",
    "units",
    "parameter_names",
    "constraint",
    "reference_parameters",
    "validity_domain",
    "expected_rigid_body_modes",
    "mass_slope",
    "matrix_file",
    "basis_km_hash",
    "dof_mapping_hash",
)

RITZ_CAPABILITIES = BackendCapabilities(
    backend_id=ForwardBackendId.KIRCHHOFF_RITZ_4D,
    backend_version=RITZ_BACKEND_VERSION,
    independent_parameters=RITZ_STIFFNESS_NAMES,
    parameter_constraints=("D11,D22,D66 > 0", "D12^2 < D11*D22"),
    shape_kind=ShapeKind.LEGENDRE_TENSOR_COEFFICIENTS,
    observation_kinds=("COORDINATE",),
    mass_depends_on_parameters="NO: M is independent of D",
    sum_of_energy_fractions_applies=True,
    requires_matrix_package=False,
)

STAGE_A_CAPABILITIES = BackendCapabilities(
    backend_id=ForwardBackendId.STAGE_A_MATRIX_3D,
    backend_version=STAGE_A_ADAPTER_VERSION,
    independent_parameters=STAGE_A_PARAMETER_NAMES,
    parameter_constraints=(STAGE_A_CONSTRAINT, "D11,D66 > 0", "|D12| < D11", "stored validity domain"),
    shape_kind=ShapeKind.MATRIX_DOF_VECTOR,
    observation_kinds=("MATRIX_DOF",),
    mass_depends_on_parameters="AS STORED: affine in D11 when the package holds dM/dD11, otherwise constant",
    sum_of_energy_fractions_applies=False,
    requires_matrix_package=True,
)


def _refuse(code: RefusalCode, reason: str) -> PlateForwardRefusal:
    return PlateForwardRefusal(code, reason)


def _refused_result(
    capabilities: BackendCapabilities,
    provenance: ForwardProvenance,
    refusal: PlateForwardRefusal,
    model_identity: str = "",
) -> PlateForwardResult:
    return PlateForwardResult(
        execution_status=ExecutionStatus.REFUSED,
        provenance=provenance,
        backend_id=capabilities.backend_id,
        backend_version=capabilities.backend_version,
        model_identity=model_identity,
        refusal_code=refusal.code,
        refusal_reason=refusal.reason,
    )


class RitzForwardBackend:
    """``KIRCHHOFF_RITZ_4D`` at one fixed geometry and basis order."""

    capabilities = RITZ_CAPABILITIES

    def __init__(
        self,
        geometry: PlateGeometry,
        config: RitzNumericalConfig,
        provenance: ForwardProvenance,
        *,
        limits: Optional[ResourceLimits] = None,
    ) -> None:
        self.geometry = geometry
        self.config = config
        self.provenance = provenance
        self.limits = limits if limits is not None else ResourceLimits()
        self.model_identity = ritz_model_identity(geometry, config)

    def availability(self) -> BackendAvailability:
        return BackendAvailability(ForwardBackendId.KIRCHHOFF_RITZ_4D, True)

    def run_identity(
        self,
        parameters: PlateBendingParameters,
        observations: Optional[CoordinateObservationSet] = None,
    ) -> str:
        return identity_hash(
            {
                "backend_id": self.capabilities.backend_id,
                "model_identity": self.model_identity,
                "parameters": parameters.identity(),
                "numerical_config": self.config.identity(),
                "observations": None if observations is None else observations.identity(),
                "provenance": self.provenance.identity(),
            }
        )

    def solve(self, parameters: PlateBendingParameters) -> RitzForwardSolution:
        """Return the full solution, or raise :class:`PlateForwardRefusal`."""

        return solve_ritz(self.geometry, parameters, self.config, self.limits)

    def sensitivities(self, parameters: PlateBendingParameters) -> RitzSensitivities:
        return ritz_sensitivities(self.solve(parameters))

    def evaluate(
        self,
        parameters: PlateBendingParameters,
        observations: Optional[object] = None,
    ) -> PlateForwardResult:
        try:
            solution = self.solve(parameters)
            evaluation = None
            if observations is not None:
                evaluation = evaluate_ritz_observations(solution, observations, self.limits)
        except PlateForwardRefusal as refusal:
            return _refused_result(self.capabilities, self.provenance, refusal, self.model_identity)
        return PlateForwardResult(
            execution_status=ExecutionStatus.COMPLETED,
            provenance=self.provenance,
            backend_id=self.capabilities.backend_id,
            backend_version=self.capabilities.backend_version,
            model_identity=self.model_identity,
            run_identity=self.run_identity(parameters, observations),
            parameters=parameters,
            frequencies_hz=tuple(float(value) for value in solution.frequencies_hz),
            eigenvalues=tuple(float(value) for value in solution.eigenvalues),
            shape=ShapeRepresentation(
                kind=ShapeKind.LEGENDRE_TENSOR_COEFFICIENTS,
                values=solution.coefficients,
                row_labels=solution.matrices.labels,
                row_meaning=RITZ_DOF_ORDERING,
                coordinate_meaning="plate-centred x,y in m; xi=2x/a, eta=2y/b",
                component_meaning="transverse mid-plane deflection w",
            ),
            observation=evaluation,
            diagnostics=solution.diagnostics(),
        )


@dataclass(frozen=True)
class StageAPackageInspection:
    """Result of a bounded inspection. No matrix values have been loaded."""

    package_directory: Path
    manifest: Mapping[str, Any]
    matrix_path: Path
    matrix_sha256: str
    matrix_bytes: int
    dof_count: int
    nonzero_count: int


def _manifest_path(directory: Path) -> Path:
    if not directory.is_dir():
        raise _refuse(RefusalCode.PACKAGE_MISSING, f"No matrix package folder at {directory}.")
    path = directory / STAGE_A_PACKAGE_MANIFEST
    if not path.is_file():
        raise _refuse(RefusalCode.PACKAGE_MISSING, f"The folder has no {STAGE_A_PACKAGE_MANIFEST}.")
    return path


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON constant {value}.")


def _read_manifest(directory: Path, limits: ResourceLimits) -> Mapping[str, Any]:
    path = _manifest_path(directory)
    try:
        size = path.stat().st_size
        if size > limits.max_manifest_bytes:
            raise _refuse(RefusalCode.RESOURCE_LIMIT, f"The manifest has {size} bytes; the cap is {limits.max_manifest_bytes}.")
        manifest = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_json_constant)
    except (OSError, ValueError) as exc:
        raise _refuse(RefusalCode.PACKAGE_CORRUPT, f"The manifest is not valid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise _refuse(RefusalCode.PACKAGE_CORRUPT, "The manifest is not a JSON object.")
    return manifest


def _check_manifest_identity(
    manifest: Mapping[str, Any],
    expected_specimen_id: Optional[str],
    expected_model_id: Optional[str],
) -> None:
    if manifest.get("schema") != STAGE_A_PACKAGE_SCHEMA:
        raise _refuse(RefusalCode.PACKAGE_UNSUPPORTED, f"Unsupported package schema {manifest.get('schema')!r}.")
    missing = [key for key in _MANIFEST_REQUIRED if key not in manifest]
    if missing:
        raise _refuse(RefusalCode.PACKAGE_CORRUPT, f"The manifest lacks: {', '.join(missing)}.")
    for key in ("model_kind", "model_id", "specimen_id", "evidence_kind", "units", "constraint", "mass_slope"):
        if not isinstance(manifest[key], str):
            raise _refuse(RefusalCode.PACKAGE_CORRUPT, f"Manifest field {key} must be text.")
    if not isinstance(manifest["parameter_names"], list):
        raise _refuse(RefusalCode.PACKAGE_CORRUPT, "Manifest field parameter_names must be a list.")
    if manifest["model_kind"] != STAGE_A_MODEL_KIND:
        raise _refuse(RefusalCode.PACKAGE_WRONG_MODEL, f"Model kind {manifest['model_kind']!r} is not Stage A.")
    if tuple(manifest["parameter_names"]) != STAGE_A_PARAMETER_NAMES or manifest["constraint"] != STAGE_A_CONSTRAINT:
        raise _refuse(RefusalCode.PACKAGE_WRONG_MODEL, "The package does not declare (D11, D12, D66) with D22=D11.")
    if expected_model_id is not None and manifest["model_id"] != expected_model_id:
        raise _refuse(
            RefusalCode.PACKAGE_WRONG_MODEL,
            f"The package holds model {manifest['model_id']!r}, not {expected_model_id!r}.",
        )
    if expected_specimen_id is not None and manifest["specimen_id"] != expected_specimen_id:
        raise _refuse(
            RefusalCode.PACKAGE_WRONG_SPECIMEN,
            f"The package belongs to specimen {manifest['specimen_id']!r}, not {expected_specimen_id!r}.",
        )
    if manifest["units"] not in _STAGE_A_D_PER_N_M:
        raise _refuse(RefusalCode.PACKAGE_UNSUPPORTED, f"Unsupported package units {manifest['units']!r}.")
    if manifest["mass_slope"] not in (MASS_SLOPE_PRESENT, MASS_SLOPE_ABSENT):
        raise _refuse(RefusalCode.PACKAGE_CORRUPT, f"Unknown mass_slope status {manifest['mass_slope']!r}.")
    try:
        EvidenceKind(manifest["evidence_kind"])
    except ValueError as exc:
        raise _refuse(RefusalCode.PACKAGE_CORRUPT, f"Unknown evidence kind {manifest['evidence_kind']!r}.") from exc


def _matrix_file(directory: Path, manifest: Mapping[str, Any], limits: ResourceLimits) -> tuple[Path, str, int]:
    record = manifest["matrix_file"]
    if not isinstance(record, dict) or not isinstance(record.get("name"), str):
        raise _refuse(RefusalCode.PACKAGE_CORRUPT, "matrix_file needs a name, sha256 and bytes.")
    name = record["name"]
    if Path(name).name != name or name in ("", ".", ".."):
        raise _refuse(RefusalCode.PACKAGE_CORRUPT, "matrix_file must be a plain name inside the package folder.")
    path = directory / name
    if not path.is_file():
        raise _refuse(RefusalCode.PACKAGE_MISSING, f"The package has no matrix file {name}.")
    size = path.stat().st_size
    if size > limits.max_package_file_bytes:
        raise _refuse(RefusalCode.RESOURCE_LIMIT, f"The matrix file has {size} bytes; the cap is {limits.max_package_file_bytes}.")
    if record.get("bytes") != size:
        raise _refuse(RefusalCode.PACKAGE_CORRUPT, "The matrix file size differs from the manifest.")
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    if record.get("sha256") != digest:
        raise _refuse(RefusalCode.PACKAGE_CORRUPT, "The matrix file SHA-256 differs from the manifest.")
    return path, digest, size


def _npy_shape(stream: Any, member: str) -> tuple[Tuple[int, ...], np.dtype]:
    try:
        version = np.lib.format.read_magic(stream)
        if version == (1, 0):
            shape, _, dtype = np.lib.format.read_array_header_1_0(stream)
        elif version == (2, 0):
            shape, _, dtype = np.lib.format.read_array_header_2_0(stream)
        else:
            raise ValueError(f"unsupported npy version {version}")
    except ValueError as exc:
        raise _refuse(RefusalCode.PACKAGE_CORRUPT, f"{member}: bad array header: {exc}") from exc
    if dtype.hasobject:
        raise _refuse(RefusalCode.PACKAGE_CORRUPT, f"{member}: object arrays are not accepted.")
    return tuple(shape), dtype


def _preflight_matrix_archive(path: Path, manifest: Mapping[str, Any], limits: ResourceLimits) -> tuple[int, int]:
    """Check sizes from zip and npy headers before any array is allocated."""

    expected = {"dof_nodes", "dof_numbers"}
    matrices = list(_MATRIX_MEMBERS)
    if manifest["mass_slope"] == MASS_SLOPE_PRESENT:
        matrices.append("dM_dD11")
    for matrix in matrices:
        expected.update(f"{matrix}_{part}" for part in ("data", "indices", "indptr"))
    shapes: dict[str, Tuple[int, ...]] = {}
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            total = sum(info.file_size for info in infos)
            if total > limits.max_package_uncompressed_bytes:
                raise _refuse(RefusalCode.RESOURCE_LIMIT, f"The matrix archive expands to {total} bytes.")
            if total > limits.max_allocation_bytes:
                raise _refuse(RefusalCode.RESOURCE_LIMIT, f"Loading needs at least {total} bytes.")
            present = {info.filename[:-4] for info in infos if info.filename.endswith(".npy")}
            if "dM_dD11_data" in present and manifest["mass_slope"] != MASS_SLOPE_PRESENT:
                raise _refuse(RefusalCode.PACKAGE_CORRUPT, "The archive holds dM/dD11 but the manifest declares none.")
            missing = sorted(expected - present)
            if missing:
                raise _refuse(RefusalCode.PACKAGE_CORRUPT, f"The matrix archive lacks: {', '.join(missing)}.")
            for member in sorted(expected):
                with archive.open(f"{member}.npy") as stream:
                    shape, dtype = _npy_shape(stream, member)
                required_kind = "f" if member.endswith("_data") else "iu"
                if dtype.kind not in required_kind:
                    raise _refuse(RefusalCode.PACKAGE_CORRUPT, f"{member}: unexpected array type {dtype}.")
                shapes[member] = shape
    except (zipfile.BadZipFile, OSError, EOFError) as exc:
        raise _refuse(RefusalCode.PACKAGE_CORRUPT, f"The matrix archive cannot be read: {exc}") from exc
    if len(shapes["dof_nodes"]) != 1 or shapes["dof_nodes"] != shapes["dof_numbers"]:
        raise _refuse(RefusalCode.PACKAGE_CORRUPT, "The DOF arrays do not match.")
    dofs = shapes["dof_nodes"][0]
    if dofs > limits.max_matrix_dofs:
        raise _refuse(RefusalCode.RESOURCE_LIMIT, f"{dofs} matrix DOFs exceed the cap of {limits.max_matrix_dofs}.")
    nonzeros = 0
    for matrix in matrices:
        data_shape = shapes[f"{matrix}_data"]
        if len(data_shape) != 1 or data_shape != shapes[f"{matrix}_indices"] or shapes[f"{matrix}_indptr"] != (dofs + 1,):
            raise _refuse(RefusalCode.PACKAGE_CORRUPT, f"{matrix}: inconsistent sparse array shapes.")
        nonzeros += data_shape[0]
    if nonzeros > limits.max_matrix_nonzeros:
        raise _refuse(RefusalCode.RESOURCE_LIMIT, f"{nonzeros} stored values exceed the cap of {limits.max_matrix_nonzeros}.")
    return dofs, nonzeros


def inspect_stage_a_package(
    package_directory: Path | str,
    *,
    expected_specimen_id: Optional[str] = None,
    expected_model_id: Optional[str] = None,
    limits: Optional[ResourceLimits] = None,
) -> StageAPackageInspection:
    """Verify manifest, identities, file hash and declared sizes without loading matrix values."""

    limits = limits if limits is not None else ResourceLimits()
    directory = Path(package_directory)
    manifest = _read_manifest(directory, limits)
    _check_manifest_identity(manifest, expected_specimen_id, expected_model_id)
    _domain_bounds(manifest)
    path, digest, size = _matrix_file(directory, manifest, limits)
    dofs, nonzeros = _preflight_matrix_archive(path, manifest, limits)
    return StageAPackageInspection(directory, manifest, path, digest, size, dofs, nonzeros)


def _sparse_member(data: Any, name: str, size: int) -> sparse.csr_matrix:
    values = np.asarray(data[f"{name}_data"], dtype=float)
    if not np.isfinite(values).all():
        raise _refuse(RefusalCode.PACKAGE_CORRUPT, f"{name} contains non-finite values.")
    try:
        matrix = sparse.csr_matrix((values, data[f"{name}_indices"], data[f"{name}_indptr"]), shape=(size, size))
        matrix.check_format(full_check=True)
    except (ValueError, IndexError) as exc:
        raise _refuse(RefusalCode.PACKAGE_CORRUPT, f"{name} is not a valid sparse matrix: {exc}") from exc
    return matrix


def _domain_bounds(manifest: Mapping[str, Any]) -> Mapping[str, Tuple[float, float]]:
    domain = manifest["validity_domain"]
    if not isinstance(domain, dict):
        raise _refuse(RefusalCode.PACKAGE_CORRUPT, "validity_domain is not an object.")
    bounds = {}
    for name in STAGE_A_PARAMETER_NAMES:
        try:
            lower, upper = (float(value) for value in domain[name])
        except (KeyError, TypeError, ValueError) as exc:
            raise _refuse(RefusalCode.PACKAGE_CORRUPT, f"validity_domain has no valid bounds for {name}.") from exc
        if not (math.isfinite(lower) and math.isfinite(upper)) or lower >= upper:
            raise _refuse(RefusalCode.PACKAGE_CORRUPT, f"validity_domain bounds for {name} are invalid.")
        bounds[name] = (lower, upper)
    return bounds


class StageAMatrixForwardBackend:
    """``STAGE_A_MATRIX_3D`` over one verified package; opening it never writes or generates."""

    capabilities = STAGE_A_CAPABILITIES

    def __init__(
        self,
        basis: StageAAffineBasis,
        inspection: StageAPackageInspection,
        bounds: Mapping[str, Tuple[float, float]],
        identity: Mapping[str, str],
        limits: ResourceLimits,
    ) -> None:
        manifest = inspection.manifest
        self.basis = basis
        self.inspection = inspection
        self.validity_domain = dict(bounds)
        self.basis_identity = dict(identity)
        self.limits = limits
        self.units = str(manifest["units"])
        self.expected_rigid_body_modes = int(manifest["expected_rigid_body_modes"])
        self.provenance = ForwardProvenance(
            EvidenceKind(manifest["evidence_kind"]),
            str(manifest.get("description", "")),
            (
                ("specimen_id", str(manifest["specimen_id"])),
                ("model_id", str(manifest["model_id"])),
                ("matrix_file_sha256", inspection.matrix_sha256),
                ("basis_km_hash", identity["basis_km_hash"]),
                ("dof_mapping_hash", identity["dof_mapping_hash"]),
            ),
        )
        self.model_identity = identity_hash(
            {
                "backend_version": STAGE_A_ADAPTER_VERSION,
                "package_schema": STAGE_A_PACKAGE_SCHEMA,
                "model_id": manifest["model_id"],
                "specimen_id": manifest["specimen_id"],
                "units": self.units,
                "basis_identity": self.basis_identity,
                "validity_domain": {name: list(item) for name, item in bounds.items()},
            }
        )

    @classmethod
    def open(
        cls,
        package_directory: Path | str,
        *,
        expected_specimen_id: Optional[str] = None,
        expected_model_id: Optional[str] = None,
        limits: Optional[ResourceLimits] = None,
    ) -> "StageAMatrixForwardBackend":
        """Load a package, or raise a specific :class:`PlateForwardRefusal`."""

        limits = limits if limits is not None else ResourceLimits()
        inspection = inspect_stage_a_package(
            package_directory,
            expected_specimen_id=expected_specimen_id,
            expected_model_id=expected_model_id,
            limits=limits,
        )
        manifest = inspection.manifest
        bounds = _domain_bounds(manifest)
        rigid = manifest["expected_rigid_body_modes"]
        if isinstance(rigid, bool) or not isinstance(rigid, int) or rigid < 0:
            raise _refuse(RefusalCode.PACKAGE_CORRUPT, "expected_rigid_body_modes must be a non-negative integer.")
        try:
            with np.load(inspection.matrix_path, allow_pickle=False) as data:
                size = inspection.dof_count
                dofs = tuple(
                    AbaqusDof(int(node), int(number))
                    for node, number in zip(data["dof_nodes"].tolist(), data["dof_numbers"].tolist())
                )
                stiffness = _sparse_member(data, "K_ref", size)
                contributions = tuple(_sparse_member(data, f"K_{name}", size) for name in STAGE_A_PARAMETER_NAMES)
                mass = _sparse_member(data, "M_ref", size)
                slope = _sparse_member(data, "dM_dD11", size) if manifest["mass_slope"] == MASS_SLOPE_PRESENT else None
            reference = manifest["reference_parameters"]
            node_map = manifest.get("node_map")
            basis = StageAAffineBasis(
                StageAMatrixParameters(reference["D11"], reference["D12"], reference["D66"]),
                stiffness,
                contributions,
                mass,
                dofs,
                mass_derivative_D11=slope,
                node_map=None if node_map is None else StageAMatrixNodeMap.from_dict(node_map),
            )
        except PlateForwardRefusal:
            raise
        except (KeyError, TypeError, ValueError, OSError, EOFError, zipfile.BadZipFile,
                MatrixModelError, StageAMatrixNodeMapError) as exc:
            raise _refuse(RefusalCode.PACKAGE_CORRUPT, f"The package cannot form a Stage-A basis: {exc}") from exc
        identity = stage_a_basis_identity(basis)
        if identity["basis_km_hash"] != manifest["basis_km_hash"] or identity["dof_mapping_hash"] != manifest["dof_mapping_hash"]:
            raise _refuse(RefusalCode.PACKAGE_CORRUPT, "The stored matrices do not match the identities in the manifest.")
        backend = cls(basis, inspection, bounds, identity, limits)
        try:
            backend._stage_a_parameters_in_package_units(basis.reference_parameters)
        except PlateForwardRefusal as exc:
            raise _refuse(RefusalCode.PACKAGE_CORRUPT, "The reference point lies outside the stored domain.") from exc
        return backend

    def availability(self) -> BackendAvailability:
        return BackendAvailability(ForwardBackendId.STAGE_A_MATRIX_3D, True)

    def _stage_a_parameters_in_package_units(self, parameters: StageAMatrixParameters) -> StageAMatrixParameters:
        for name, value in zip(STAGE_A_PARAMETER_NAMES, parameters.values):
            lower, upper = self.validity_domain[name]
            if not lower <= float(value) <= upper:
                raise _refuse(
                    RefusalCode.OUTSIDE_VALIDITY_DOMAIN,
                    f"{name} = {float(value):.12g} {self.units} lies outside the stored domain [{lower:.12g}, {upper:.12g}].",
                )
        return parameters

    def to_package_parameters(self, parameters: PlateBendingParameters) -> StageAMatrixParameters:
        """Convert SI D to the package units. D22 = D11 is required exactly, never imposed."""

        if parameters.D22 != parameters.D11:
            raise _refuse(
                RefusalCode.STAGE_A_REQUIRES_D22_EQUAL_D11,
                f"Stage A has D22 = D11, but D11 = {parameters.D11:.12g} and D22 = {parameters.D22:.12g} N*m.",
            )
        factor = _STAGE_A_D_PER_N_M[self.units]
        try:
            converted = StageAMatrixParameters(parameters.D11 * factor, parameters.D12 * factor, parameters.D66 * factor)
        except ValueError as exc:
            raise _refuse(RefusalCode.INADMISSIBLE_PARAMETERS, str(exc)) from exc
        return self._stage_a_parameters_in_package_units(converted)

    def _preflight_solve(self, mode_count: int) -> None:
        if isinstance(mode_count, bool) or not isinstance(mode_count, int) or mode_count <= 0:
            raise _refuse(RefusalCode.INVALID_INPUT, "mode_count must be a positive integer.")
        columns = mode_count + self.expected_rigid_body_modes + 4
        estimated = 3 * columns * len(self.basis.dofs) * 8
        if estimated > self.limits.max_allocation_bytes:
            raise _refuse(RefusalCode.RESOURCE_LIMIT, f"The eigensolve needs about {estimated} bytes.")

    def run_identity(
        self,
        parameters: PlateBendingParameters,
        mode_count: int,
        observations: Optional[DofObservationSet] = None,
    ) -> str:
        return identity_hash(
            {
                "backend_id": self.capabilities.backend_id,
                "model_identity": self.model_identity,
                "parameters": parameters.identity(),
                "mode_count": int(mode_count),
                "expected_rigid_body_modes": self.expected_rigid_body_modes,
                "observations": None if observations is None else observations.identity(),
                "provenance": self.provenance.identity(),
            }
        )

    def _observe(self, result: Any, observations: object) -> ObservationEvaluation:
        if not isinstance(observations, DofObservationSet):
            kind = "coordinate" if isinstance(observations, CoordinateObservationSet) else "this"
            raise _refuse(
                RefusalCode.UNSUPPORTED_OBSERVATION_KIND,
                f"The package holds no node coordinates, so {kind} observation kind is not evaluated; "
                "address observations by exact matrix DOF.",
            )
        positions = {(dof.node_label, dof.dof): index for index, dof in enumerate(result.dofs)}
        rows = []
        for item in observations.items:
            position = positions.get((int(item.node_label), int(item.dof)))
            if position is None:
                raise _refuse(
                    RefusalCode.OBSERVATION_OUTSIDE_MODEL,
                    f"{item.observation_id}: DOF {item.node_label}.{item.dof} is not an active package DOF.",
                )
            rows.append(position)
        return ObservationEvaluation(
            observation_ids=tuple(item.observation_id for item in observations.items),
            values=np.asarray(result.eigenvectors)[rows, :],
            component_meanings=tuple(f"matrix DOF {item.node_label}.{item.dof}" for item in observations.items),
            registration_id=observations.registration_id,
        )

    def evaluate(
        self,
        parameters: PlateBendingParameters,
        mode_count: int,
        observations: Optional[object] = None,
    ) -> PlateForwardResult:
        try:
            self._preflight_solve(mode_count)
            package_parameters = self.to_package_parameters(parameters)
            try:
                stiffness = self.basis.reconstruct_stiffness(package_parameters)
                mass = self.basis.reconstruct_mass(package_parameters)
                result = solve_generalized_eigenproblem(
                    stiffness,
                    mass,
                    mode_count,
                    expected_rigid_body_modes=self.expected_rigid_body_modes,
                    dofs=self.basis.dofs,
                )
            except (MatrixModelError, ValueError) as exc:
                raise _refuse(RefusalCode.MATRIX_MODEL_FAILED, str(exc)) from exc
            evaluation = None if observations is None else self._observe(result, observations)
        except PlateForwardRefusal as refusal:
            return _refused_result(self.capabilities, self.provenance, refusal, self.model_identity)
        full_positions = {dof: index for index, dof in enumerate(self.basis.dofs)}
        active = [full_positions[dof] for dof in result.dofs]
        active_k = stiffness[active][:, active]
        active_m = mass[active][:, active]
        vectors = np.asarray(result.eigenvectors)
        residual = active_k @ vectors - (active_m @ vectors) * result.eigenvalues
        denominators = result.eigenvalues * np.linalg.norm(active_m @ vectors, axis=0)
        health = result.rigid_spectrum_health
        return PlateForwardResult(
            execution_status=ExecutionStatus.COMPLETED,
            provenance=self.provenance,
            backend_id=self.capabilities.backend_id,
            backend_version=self.capabilities.backend_version,
            model_identity=self.model_identity,
            run_identity=self.run_identity(parameters, mode_count, observations),
            parameters=parameters,
            frequencies_hz=tuple(float(value) for value in result.frequencies_hz),
            eigenvalues=tuple(float(value) for value in result.eigenvalues),
            shape=ShapeRepresentation(
                kind=ShapeKind.MATRIX_DOF_VECTOR,
                values=vectors,
                row_labels=tuple((dof.node_label, dof.dof) for dof in result.dofs),
                row_meaning="(matrix node label, DOF number), active DOFs only",
                coordinate_meaning="stored matrix DOF identities; the package holds no coordinates",
                component_meaning="stored FE DOF value",
            ),
            observation=evaluation,
            diagnostics={
                "stiffness_model": "STORED_AFFINE_RECONSTRUCTION",
                "mass_model": self.mass_model,
                "parameters_in_package_units": package_parameters.values.tolist(),
                "package_units": self.units,
                "max_eigen_residual": float(np.max(np.linalg.norm(residual, axis=0) / denominators)),
                "rigid_spectrum_status": None if health is None else health.status,
                "rigid_to_first_elastic_ratio": None if health is None else health.rigid_to_first_elastic_ratio,
                "expected_rigid_body_modes": self.expected_rigid_body_modes,
                "next_elastic_eigenvalue": result.next_elastic_eigenvalue,
                "energy_fraction_sum_rule": "NOT_APPLIED: stored K is affine and M may depend on D11",
                "validation_evidence": self.inspection.manifest.get("validation_evidence") or "NOT_SUPPLIED",
            },
        )

    @property
    def mass_model(self) -> str:
        return MASS_SLOPE_ABSENT if self.basis.mass_derivative_D11 is None else MASS_SLOPE_PRESENT

    def sensitivities(
        self,
        parameters: PlateBendingParameters,
        mode_count: int,
        *,
        finite_difference_relative_steps: Sequence[float] = (),
    ) -> SensitivityResult:
        """Reuse the existing Stage-A sensitivities, including the stored mass derivative.

        The existing contract treats the highest solved mode as a guard, so one extra mode is solved
        and modes 1..mode_count are returned. Raises :class:`PlateForwardRefusal` for an unresolved
        mode or a parameter outside the domain.
        """

        self._preflight_solve(mode_count)
        self._preflight_solve(mode_count + 1)
        package_parameters = self.to_package_parameters(parameters)
        try:
            return compute_stage_a_sensitivity(
                self.basis,
                package_parameters,
                mode_count + 1,
                coordinate_system=StageASensitivityCoordinate.AFFINE,
                expected_rigid_body_modes=self.expected_rigid_body_modes,
                finite_difference_relative_steps=tuple(finite_difference_relative_steps),
                observed_mode_ids=tuple(range(1, mode_count + 1)),
            )
        except ScalarModeSensitivityRefusal as exc:
            raise _refuse(RefusalCode.DEGENERATE_BRANCH, str(exc)) from exc
        except MatrixModelError as exc:
            raise _refuse(RefusalCode.MATRIX_MODEL_FAILED, str(exc)) from exc


def stage_a_availability(
    package_directory: Optional[Path | str],
    *,
    expected_specimen_id: Optional[str] = None,
    expected_model_id: Optional[str] = None,
    limits: Optional[ResourceLimits] = None,
) -> BackendAvailability:
    """Report whether a package can be used, by a bounded inspection that loads no matrix values."""

    if package_directory is None:
        return BackendAvailability(
            ForwardBackendId.STAGE_A_MATRIX_3D,
            False,
            RefusalCode.PACKAGE_MISSING,
            "No Stage-A matrix package was selected for this specimen.",
        )
    try:
        inspect_stage_a_package(
            package_directory,
            expected_specimen_id=expected_specimen_id,
            expected_model_id=expected_model_id,
            limits=limits,
        )
    except PlateForwardRefusal as refusal:
        return BackendAvailability(ForwardBackendId.STAGE_A_MATRIX_3D, False, refusal.code, refusal.reason)
    return BackendAvailability(ForwardBackendId.STAGE_A_MATRIX_3D, True)


def plate_backend_availability(
    stage_a_package: Optional[Path | str] = None,
    *,
    expected_specimen_id: Optional[str] = None,
    expected_model_id: Optional[str] = None,
    limits: Optional[ResourceLimits] = None,
) -> Mapping[ForwardBackendId, BackendAvailability]:
    """Report both backends. The Ritz backend depends on no package and stays available."""

    return {
        ForwardBackendId.KIRCHHOFF_RITZ_4D: BackendAvailability(ForwardBackendId.KIRCHHOFF_RITZ_4D, True),
        ForwardBackendId.STAGE_A_MATRIX_3D: stage_a_availability(
            stage_a_package,
            expected_specimen_id=expected_specimen_id,
            expected_model_id=expected_model_id,
            limits=limits,
        ),
    }


def _sparse_arrays(name: str, matrix: sparse.csr_matrix) -> Mapping[str, np.ndarray]:
    ordered = sparse.csr_matrix(matrix, dtype=float, copy=True)
    ordered.sort_indices()
    return {
        f"{name}_data": ordered.data,
        f"{name}_indices": ordered.indices,
        f"{name}_indptr": ordered.indptr,
    }


def write_stage_a_package(
    basis: StageAAffineBasis,
    package_directory: Path | str,
    *,
    specimen_id: str,
    model_id: str,
    evidence_kind: EvidenceKind,
    units: str,
    validity_domain: Mapping[str, Tuple[float, float]],
    expected_rigid_body_modes: int,
    description: str,
    validation_evidence: Optional[str] = None,
) -> Path:
    """Store an existing in-memory basis in a new folder. It computes no matrix and overwrites nothing."""

    directory = Path(package_directory)
    if units not in _STAGE_A_D_PER_N_M:
        raise ValueError(f"Unsupported package units {units!r}.")
    directory.mkdir(parents=True, exist_ok=False)
    arrays: dict[str, np.ndarray] = {
        "dof_nodes": np.asarray([dof.node_label for dof in basis.dofs], dtype=np.int64),
        "dof_numbers": np.asarray([dof.dof for dof in basis.dofs], dtype=np.int64),
    }
    arrays.update(_sparse_arrays("K_ref", basis.reference_stiffness))
    for name, contribution in zip(STAGE_A_PARAMETER_NAMES, basis.basis_matrices):
        arrays.update(_sparse_arrays(f"K_{name}", contribution))
    arrays.update(_sparse_arrays("M_ref", basis.mass))
    if basis.mass_derivative_D11 is not None:
        arrays.update(_sparse_arrays("dM_dD11", basis.mass_derivative_D11))
    matrix_path = directory / "matrices.npz"
    with matrix_path.open("xb") as stream:
        np.savez(stream, **arrays)
    digest = hashlib.sha256(matrix_path.read_bytes()).hexdigest()
    identity = stage_a_basis_identity(basis)
    reference = basis.reference_parameters
    manifest = {
        "schema": STAGE_A_PACKAGE_SCHEMA,
        "model_kind": STAGE_A_MODEL_KIND,
        "model_id": model_id,
        "specimen_id": specimen_id,
        "evidence_kind": EvidenceKind(evidence_kind).value,
        "description": description,
        "units": units,
        "parameter_names": list(STAGE_A_PARAMETER_NAMES),
        "constraint": STAGE_A_CONSTRAINT,
        "reference_parameters": {"D11": reference.D11, "D12": reference.D12, "D66": reference.D66},
        "validity_domain": {name: [float(item[0]), float(item[1])] for name, item in validity_domain.items()},
        "expected_rigid_body_modes": int(expected_rigid_body_modes),
        "mass_slope": MASS_SLOPE_ABSENT if basis.mass_derivative_D11 is None else MASS_SLOPE_PRESENT,
        "matrix_file": {"name": matrix_path.name, "sha256": digest, "bytes": matrix_path.stat().st_size},
        "basis_km_hash": identity["basis_km_hash"],
        "dof_mapping_hash": identity["dof_mapping_hash"],
        "node_map": None if basis.node_map is None else basis.node_map.to_dict(),
        "validation_evidence": validation_evidence,
    }
    with (directory / STAGE_A_PACKAGE_MANIFEST).open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2, sort_keys=True)
    return directory
