"""Production orchestration for Stage-A inverse identification.

This module connects the existing reviewed modal comparator to the Stage-A
matrix, sensitivity, identifiability, and inverse-solver services.  Pairing,
MAC, geometry registration, measured-DOF masking, and Hungarian assignment
remain owned by the existing comparator.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import hashlib
import json
import math
from typing import Callable, Mapping, Sequence, Tuple

import numpy as np

from coordinate_calibration import CoordinateCalibration
from domain.modal_input_source import require_identification_input
from domain.modal_observation import InclusionStatus, ModalCluster, ModalObservation
from domain.parameter_model import ParameterPrior
from domain.registration import FrozenRegistration, RegistrationMismatchError
from modal_core import ComparisonResult, ModalDataset, ModeShape, compare_modal_datasets
from reviewed_core import (
    GeometryOrientationAmbiguousError,
    _candidate_summary,
    _explicit_measurement_mask,
    experimental_measurement_masks,
)
from scientific_state import (
    calibration_fingerprint,
    experimental_source_content_identity,
    modal_dataset_geometry_identity,
)

from .identifiability_service import (
    IdentifiabilityResult,
    ParameterPrecisionRequirement,
    analyze_identifiability,
    whiten_sensitivity,
)
from .inverse_solver import (
    ComparisonPairingProvider,
    ExcludedSolverObservation,
    InverseIdentificationResult,
    InverseSolverConfiguration,
    InverseSolverValidationError,
    ModeAssignment,
    ModeTrackingMode,
    PairingResult,
    StageAParameterBounds,
    solve_stage_a_inverse,
)
from .matrix_model_service import (
    AbaqusDof,
    GeneralizedEigenResult,
    MatrixModelError,
    StageAAffineBasis,
    StageAMatrixNodeMap,
    StageAMatrixNodeMapError,
    StageAMatrixParameters,
    solve_generalized_eigenproblem,
)
from .modal_cluster_service import cluster_comparison_result
from .sensitivity_service import ScalarModeSensitivityRefusal, compute_stage_a_sensitivity


class StageAIdentificationError(RuntimeError):
    """Stage-A orchestration cannot safely proceed or produce a result."""


class ComparatorPairingError(ValueError):
    """The reviewed comparator could not provide a complete current pairing."""


class MacEvidencePairingError(ComparatorPairingError):
    """A requested observation could not be re-paired with valid MAC evidence.

    At an optimizer trial point this is an ordinary failed evaluation; at the
    initial production pairing ``identify_stage_a`` refuses instead of falling
    back to fixed pairs.
    """


class StageAProductionPairingRefusal(Exception):
    """Production pairing violates a frozen scientific contract.

    Raised for node-map, experimental-source, FE-geometry, Policy-B,
    calibration, and orientation violations.  Deliberately not a ValueError or
    RuntimeError: the generic pairing-failure, optimizer-evaluation, and
    fixed-pair fallback handlers must never catch it.
    """

    def __init__(self, contract: str, message: str) -> None:
        super().__init__(message)
        self.contract = contract


STAGE_A_MAPPED_DOF_IDENTITY_SCHEMA = "stage-a-dof-mapping/2"
FE_DOF_AVAILABILITY_SOURCE = "stage_a_matrix_active_dofs"
STAGE_A_FE_AVAILABILITY_SCHEMA = "stage-a-fe-availability/1"
_FE_COMPONENT_NAMES = ("U1", "U2", "U3")


class StageAFeAvailabilityError(ValueError):
    """FE DOF availability is malformed or does not satisfy Policy B."""

    def __init__(
        self, message: str, violations: Sequence[Tuple[str, str, str]] = ()
    ) -> None:
        super().__init__(message)
        self.violations = tuple(violations)


def _qualified_fe_node_id(value: object) -> str:
    if not isinstance(value, str):
        raise StageAFeAvailabilityError(
            f"FE node IDs must be 'INSTANCE:label' strings: {value!r}"
        )
    instance, separator, label = value.rpartition(":")
    if not separator or not instance.strip():
        raise StageAFeAvailabilityError(f"FE node ID has no instance name: {value!r}")
    try:
        int(label)
    except ValueError as exc:
        raise StageAFeAvailabilityError(
            f"FE node ID label is not an integer: {value!r}"
        ) from exc
    return str(value)


@dataclass(frozen=True)
class StageAFeAvailability:
    """Which FE U1/U2/U3 components a matrix candidate actually carries.

    ``available`` is True only for translational DOFs that are active in the
    matrix eigenvector DOFs.  Everything else is UNAVAILABLE -- never a known
    zero -- and is never inferred from displacement values, ODB output masks,
    or experimental measurement masks.
    """

    fe_node_ids: Tuple[str, ...]
    available: Tuple[Tuple[bool, bool, bool], ...]
    node_map_hash: str
    source: str = FE_DOF_AVAILABILITY_SOURCE
    schema_version: str = STAGE_A_FE_AVAILABILITY_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != STAGE_A_FE_AVAILABILITY_SCHEMA:
            raise StageAFeAvailabilityError(
                f"Unsupported FE availability schema: {self.schema_version!r}."
            )
        if self.source != FE_DOF_AVAILABILITY_SOURCE:
            raise StageAFeAvailabilityError(
                f"FE availability source must be {FE_DOF_AVAILABILITY_SOURCE!r}."
            )
        node_map_hash = self.node_map_hash
        if (
            not isinstance(node_map_hash, str)
            or len(node_map_hash) != 64
            or any(character not in "0123456789abcdef" for character in node_map_hash)
        ):
            raise StageAFeAvailabilityError("node_map_hash must be a SHA-256 hex digest.")
        node_ids = tuple(
            _qualified_fe_node_id(item) for item in _plain_sequence(self.fe_node_ids)
        )
        if len(set(node_ids)) != len(node_ids):
            raise StageAFeAvailabilityError("FE availability node IDs must be unique.")
        rows = []
        for row in _plain_sequence(self.available):
            items = tuple(_plain_sequence(row))
            if len(items) != len(_FE_COMPONENT_NAMES) or not all(
                isinstance(item, bool) for item in items
            ):
                raise StageAFeAvailabilityError(
                    "FE availability must be an N x 3 boolean mask."
                )
            rows.append(items)
        if len(rows) != len(node_ids):
            raise StageAFeAvailabilityError(
                "FE availability must have one mask row per FE node."
            )
        object.__setattr__(self, "fe_node_ids", node_ids)
        object.__setattr__(self, "available", tuple(rows))
        object.__setattr__(self, "_by_node", dict(zip(node_ids, rows)))

    @property
    def content_hash(self) -> str:
        payload = json.dumps(
            {
                "schema_version": self.schema_version,
                "source": self.source,
                "node_map_hash": self.node_map_hash,
                "nodes": sorted(
                    [node_id, list(row)] for node_id, row in zip(self.fe_node_ids, self.available)
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def has_node(self, fe_node_id: str) -> bool:
        return fe_node_id in self._by_node

    def available_components(self, fe_node_id: str) -> Tuple[bool, bool, bool]:
        try:
            return self._by_node[fe_node_id]
        except KeyError as exc:
            raise StageAFeAvailabilityError(
                f"FE node {fe_node_id} is absent from the FE availability contract."
            ) from exc

    def mask_array(self) -> np.ndarray:
        """Return a new, detached N x 3 boolean array in FE-grid order."""
        return np.array(self.available, dtype=bool).reshape(-1, len(_FE_COMPONENT_NAMES))


def _plain_sequence(value: object) -> list:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, (list, tuple)):
        raise StageAFeAvailabilityError(
            f"Expected a sequence, not {type(value).__name__}."
        )
    return list(value)


def build_stage_a_fe_availability(
    reference_node_ids: Sequence[object],
    node_map: StageAMatrixNodeMap,
    dofs: Sequence[AbaqusDof],
) -> StageAFeAvailability:
    """Build FE availability from the active matrix DOFs through the node map.

    ``dofs`` are the eigenvector DOFs of one solve (``GeneralizedEigenResult.dofs``):
    a translational DOF listed there is AVAILABLE, every other one is not.
    """
    if not isinstance(node_map, StageAMatrixNodeMap):
        raise StageAFeAvailabilityError("An explicit StageAMatrixNodeMap is required.")
    node_ids = [
        _qualified_fe_node_id(item)
        for item in np.asarray(reference_node_ids, dtype=object).reshape(-1)
    ]
    rows: dict[str, int] = {}
    for index, node_id in enumerate(node_ids):
        if node_id in rows:
            raise StageAFeAvailabilityError("Reference FE node IDs must be unique.")
        rows[node_id] = index
    unknown = [target for _, target in node_map.entries if target not in rows]
    if unknown:
        raise StageAFeAvailabilityError(
            f"{len(unknown)} node-map target(s) are not in the reference FE grid "
            f"(first: {unknown[0]!r})."
        )
    available = np.zeros((len(node_ids), len(_FE_COMPONENT_NAMES)), dtype=bool)
    for dof in dofs:
        try:
            fe_node = node_map.fe_node_id(dof.node_label)
        except StageAMatrixNodeMapError as exc:
            raise StageAFeAvailabilityError(str(exc)) from exc
        if 1 <= dof.dof <= 3:
            available[rows[fe_node], dof.dof - 1] = True
    return StageAFeAvailability(
        fe_node_ids=tuple(node_ids),
        available=available,
        node_map_hash=node_map.content_hash,
    )


def required_fe_components(
    registration: FrozenRegistration,
) -> dict[str, Tuple[bool, bool, bool]]:
    """Return the FE U1/U2/U3 components each mapped FE node must provide.

    The comparator rotates FE row vectors as ``experimental = fe @ R``, so a
    measured experimental component ``j`` needs every FE component ``k`` with
    ``R[k][j] != 0``.  The test is exact: a tiny nonzero coefficient is
    conservatively required rather than silently dropped.
    """
    if not isinstance(registration, FrozenRegistration):
        raise StageAFeAvailabilityError("A FrozenRegistration is required.")
    rotation = registration.rotation
    required: dict[str, list[bool]] = {}
    for fe_node, measured in zip(
        registration.mapped_fe_node_ids, registration.measured_dof_contract
    ):
        for component, is_measured in enumerate(measured):
            if not is_measured:
                continue
            need = required.setdefault(fe_node, [False, False, False])
            for fe_component in range(len(_FE_COMPONENT_NAMES)):
                if rotation[fe_component][component] != 0.0:
                    need[fe_component] = True
    return {fe_node: tuple(need) for fe_node, need in sorted(required.items())}


def _refuse_violations(violations: list[Tuple[str, str, str]]) -> None:
    if violations:
        details = "; ".join(
            f"{fe_node} {component} ({reason})"
            for fe_node, component, reason in violations[:5]
        )
        more = f" and {len(violations) - 5} more" if len(violations) > 5 else ""
        raise StageAFeAvailabilityError(
            "Policy B refused: FE components required by the frozen measurement "
            f"contract are UNAVAILABLE: {details}{more}.",
            violations,
        )


def check_required_fe_availability(
    registration: FrozenRegistration,
    availability: StageAFeAvailability,
    *,
    node_map: StageAMatrixNodeMap | None = None,
) -> bool:
    """Policy B: every required FE component must be AVAILABLE (else refuse).

    This is the authoritative per-candidate check.  Unavailable components are
    never treated as zero, and the frozen measurement contract is never reduced.
    """
    if not isinstance(availability, StageAFeAvailability):
        raise StageAFeAvailabilityError("A StageAFeAvailability contract is required.")
    required = required_fe_components(registration)
    if node_map is not None and (
        not isinstance(node_map, StageAMatrixNodeMap)
        or availability.node_map_hash != node_map.content_hash
    ):
        raise StageAFeAvailabilityError(
            "The FE availability contract was not built from the supplied node map."
        )
    violations: list[Tuple[str, str, str]] = []
    for fe_node, need in required.items():
        if not availability.has_node(fe_node):
            names = ",".join(
                name for name, flag in zip(_FE_COMPONENT_NAMES, need) if flag
            )
            violations.append(
                (fe_node, names, "absent from the FE availability contract")
            )
            continue
        have = availability.available_components(fe_node)
        for name, needed, present in zip(_FE_COMPONENT_NAMES, need, have):
            if needed and not present:
                violations.append(
                    (fe_node, name, "not active in the matrix eigenvector DOFs")
                )
    _refuse_violations(violations)
    return True


def precheck_required_fe_export(
    registration: FrozenRegistration,
    node_map: StageAMatrixNodeMap,
    exported_dofs: Sequence[AbaqusDof],
) -> bool:
    """Necessary (not sufficient) basis-level check: required DOFs were exported.

    A DOF absent from the matrix export can never become active, so this can
    refuse early.  Passing it proves nothing about activity in a particular
    eigen-solve; ``check_required_fe_availability`` remains authoritative.
    """
    if not isinstance(node_map, StageAMatrixNodeMap):
        raise StageAFeAvailabilityError("An explicit StageAMatrixNodeMap is required.")
    required = required_fe_components(registration)
    exported: dict[str, set[int]] = {}
    for dof in exported_dofs:
        if not 1 <= dof.dof <= 3:
            continue
        try:
            fe_node = node_map.fe_node_id(dof.node_label)
        except StageAMatrixNodeMapError as exc:
            raise StageAFeAvailabilityError(str(exc)) from exc
        exported.setdefault(fe_node, set()).add(dof.dof - 1)
    violations = [
        (fe_node, _FE_COMPONENT_NAMES[component], "not exported by the matrix basis")
        for fe_node, need in required.items()
        for component in range(len(_FE_COMPONENT_NAMES))
        if need[component] and component not in exported.get(fe_node, set())
    ]
    _refuse_violations(violations)
    return True


class PairingProviderMode(str, Enum):
    COMPARATOR = "production_comparator"
    FIXED_PAIR_FALLBACK = "fixed_pair_synthetic_fallback"


C3B2_MODE_IDENTITY_CAVEAT = {
    "status": "KNOWN_LIMITATION",
    "campaign": "C3B2",
    "reference_branch_assignment_stable": True,
    "minimum_individual_mac": {"NB6": 5.32e-4, "NB8": 0.01495},
    "individual_scalar_mac_alone_is_sufficient": False,
    "future_real_data_requirement": (
        "Do not rely solely on individual scalar MAC near close-mode or "
        "topology transitions; retain reference/branch or future subspace evidence."
    ),
    "cluster_subspace_residual_implemented": False,
    "mac_thresholds_changed": False,
}


@dataclass(frozen=True)
class ModelValidationEvidence:
    specimen_model_identifier: str
    basis_km_hash: str
    dof_mapping_hash: str | None = None
    template_model_hash: str | None = None
    abaqus_version: str | None = None
    validated_parameter_domain: Mapping[str, Tuple[float, float]] = field(
        default_factory=dict
    )
    validation_points: Tuple[Mapping[str, object], ...] = ()
    observed_errors: Mapping[str, float] = field(default_factory=dict)
    thresholds: Mapping[str, float] = field(default_factory=dict)
    validation_timestamp: str | None = None
    campaign_identifier: str | None = None
    status: str = "PASS"

    def __post_init__(self) -> None:
        identifier = str(self.specimen_model_identifier).strip()
        basis_hash = str(self.basis_km_hash).strip().lower()
        if not identifier or not basis_hash:
            raise ValueError(
                "Validation evidence requires specimen/model identifier and basis K/M hash."
            )
        status = str(self.status).strip().upper()
        if status not in {"PASS", "WARNING", "FAIL"}:
            raise ValueError("Validation evidence status must be PASS, WARNING, or FAIL.")
        domain: dict[str, Tuple[float, float]] = {}
        for name, interval in self.validated_parameter_domain.items():
            if len(interval) != 2:
                raise ValueError("Validated parameter-domain intervals require two bounds.")
            lower, upper = (float(value) for value in interval)
            if not math.isfinite(lower) or not math.isfinite(upper) or lower >= upper:
                raise ValueError("Validated parameter-domain bounds are invalid.")
            domain[str(name)] = (lower, upper)
        for label, values in (
            ("observed_errors", self.observed_errors),
            ("thresholds", self.thresholds),
        ):
            if not all(math.isfinite(float(value)) for value in values.values()):
                raise ValueError(f"{label} must contain only finite values.")
        object.__setattr__(self, "specimen_model_identifier", identifier)
        object.__setattr__(self, "basis_km_hash", basis_hash)
        object.__setattr__(self, "dof_mapping_hash", None if self.dof_mapping_hash is None else str(self.dof_mapping_hash).strip().lower())
        object.__setattr__(self, "template_model_hash", None if self.template_model_hash is None else str(self.template_model_hash).strip().lower())
        object.__setattr__(self, "abaqus_version", None if self.abaqus_version is None else str(self.abaqus_version).strip())
        object.__setattr__(self, "validated_parameter_domain", domain)
        object.__setattr__(self, "validation_points", tuple(dict(item) for item in self.validation_points))
        object.__setattr__(self, "observed_errors", {str(k): float(v) for k, v in self.observed_errors.items()})
        object.__setattr__(self, "thresholds", {str(k): float(v) for k, v in self.thresholds.items()})
        object.__setattr__(self, "status", status)


@dataclass(frozen=True)
class StageACampaignPolicy:
    """Explicit campaign decisions applied before identifiability analysis."""

    cluster_relative_frequency_gap: float | None = None
    excluded_experimental_mode_ids: Tuple[int, ...] = (1,)
    excluded_mode_reason: str = "probable suspension influence"
    approve_recommended_subset: bool = False
    allow_fixed_pair_fallback: bool = False
    condition_warning_threshold: float = 100.0
    collinearity_warning_threshold: float = 20.0
    precision_requirements: Mapping[str, ParameterPrecisionRequirement] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if self.cluster_relative_frequency_gap is not None:
            value = float(self.cluster_relative_frequency_gap)
            if not math.isfinite(value) or not 0.0 <= value < 1.0:
                raise ValueError(
                    "cluster_relative_frequency_gap must be finite and in [0, 1)."
                )
            object.__setattr__(self, "cluster_relative_frequency_gap", value)
        mode_ids = tuple(int(item) for item in self.excluded_experimental_mode_ids)
        if any(item <= 0 for item in mode_ids) or len(set(mode_ids)) != len(mode_ids):
            raise ValueError("Campaign-excluded mode IDs must be unique and positive.")
        if mode_ids and not self.excluded_mode_reason.strip():
            raise ValueError("Campaign mode exclusions require an explicit reason.")
        object.__setattr__(self, "excluded_experimental_mode_ids", mode_ids)
        for name in ("condition_warning_threshold", "collinearity_warning_threshold"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be positive and finite.")
            object.__setattr__(self, name, value)
        requirements = dict(self.precision_requirements)
        if not all(
            isinstance(value, ParameterPrecisionRequirement)
            for value in requirements.values()
        ):
            raise TypeError(
                "precision_requirements values must be ParameterPrecisionRequirement."
            )
        object.__setattr__(
            self,
            "precision_requirements",
            {str(key): value for key, value in requirements.items()},
        )


@dataclass(frozen=True)
class StageAIdentificationResult:
    observations: Tuple[ModalObservation, ...]
    clusters: Tuple[ModalCluster, ...]
    effective_observation_count: int
    identifiability: IdentifiabilityResult
    requested_parameter_subset: Tuple[str, ...]
    recommended_parameter_subset: Tuple[str, ...] | None
    fitted_parameter_subset: Tuple[str, ...]
    inverse_result: InverseIdentificationResult
    excluded_observations: Tuple[ExcludedSolverObservation, ...]
    excluded_clusters: Tuple[ModalCluster, ...]
    pairing_provider_mode: PairingProviderMode
    warnings: Tuple[str, ...]
    metadata: Mapping[str, object] = field(default_factory=dict)


ComparatorFunction = Callable[..., ComparisonResult]


def _hash_sparse(hasher: "hashlib._Hash", label: str, matrix: object) -> None:
    from scipy import sparse

    value = sparse.csr_matrix(matrix, dtype="<f8")
    value.sort_indices()
    hasher.update(label.encode("utf-8") + b"\0")
    hasher.update(np.asarray(value.shape, dtype="<i8").tobytes())
    hasher.update(np.asarray(value.indptr, dtype="<i8").tobytes())
    hasher.update(np.asarray(value.indices, dtype="<i8").tobytes())
    hasher.update(np.asarray(value.data, dtype="<f8").tobytes())


def stage_a_basis_identity(affine_model: StageAAffineBasis) -> Mapping[str, str]:
    """Return deterministic K/M/basis and DOF mapping identities."""

    if not isinstance(affine_model, StageAAffineBasis):
        raise TypeError("affine_model must be StageAAffineBasis.")
    basis_hasher = hashlib.sha256()
    basis_hasher.update(np.asarray(affine_model.reference_parameters.values, dtype="<f8").tobytes())
    _hash_sparse(basis_hasher, "reference_K", affine_model.reference_stiffness)
    for name, matrix in zip(("D11", "D12", "D66"), affine_model.basis_matrices):
        _hash_sparse(basis_hasher, f"basis_K_{name}", matrix)
    _hash_sparse(basis_hasher, "reference_M", affine_model.mass)
    if affine_model.mass_derivative_D11 is None:
        basis_hasher.update(b"mass_derivative_D11:none")
    else:
        _hash_sparse(
            basis_hasher, "mass_derivative_D11", affine_model.mass_derivative_D11
        )
    dof_hasher = hashlib.sha256()
    for dof in affine_model.dofs:
        dof_hasher.update(f"{dof.node_label!r}:{dof.dof}\n".encode("utf-8"))
    if affine_model.node_map is None:
        # Legacy label-only DOF identity; values are unchanged for unmapped bases.
        return {
            "basis_km_hash": basis_hasher.hexdigest(),
            "dof_mapping_hash": dof_hasher.hexdigest(),
        }
    # A mapped basis has a different, versioned DOF identity that can never
    # equal the legacy label-only hash.
    node_map_hash = affine_model.node_map.content_hash
    mapped_hasher = hashlib.sha256()
    mapped_hasher.update(f"{STAGE_A_MAPPED_DOF_IDENTITY_SCHEMA}\n".encode("utf-8"))
    mapped_hasher.update(bytes.fromhex(dof_hasher.hexdigest()))
    mapped_hasher.update(bytes.fromhex(node_map_hash))
    return {
        "basis_km_hash": basis_hasher.hexdigest(),
        "dof_mapping_hash": mapped_hasher.hexdigest(),
        "dof_mapping_schema": STAGE_A_MAPPED_DOF_IDENTITY_SCHEMA,
        "node_map_hash": node_map_hash,
    }


def assess_model_validation_evidence(
    evidence: ModelValidationEvidence | None,
    affine_model: StageAAffineBasis,
    *,
    physical_specimen_id: str,
    parameter_bounds: StageAParameterBounds,
    model_template_hash: str | None = None,
    abaqus_version: str | None = None,
) -> Mapping[str, object]:
    identity = stage_a_basis_identity(affine_model)
    base: dict[str, object] = {
        "status": "NOT_VALIDATED_FOR_THIS_MODEL",
        "applicable": False,
        "current_identity": identity,
        "evidence": None,
        "mismatches": (),
    }
    if evidence is None:
        base["reason"] = "No matching model-validation evidence was supplied."
        return base
    mismatches: list[str] = []
    if evidence.specimen_model_identifier != str(physical_specimen_id):
        mismatches.append("specimen_model_identifier")
    if evidence.basis_km_hash != identity["basis_km_hash"]:
        mismatches.append("basis_km_hash")
    if (
        evidence.dof_mapping_hash is not None
        and evidence.dof_mapping_hash != identity["dof_mapping_hash"]
    ):
        mismatches.append("dof_mapping_hash")
    if evidence.template_model_hash is not None:
        if model_template_hash is None or evidence.template_model_hash != str(model_template_hash).lower():
            mismatches.append("template_model_hash")
    if evidence.abaqus_version is not None:
        if abaqus_version is None or evidence.abaqus_version != str(abaqus_version):
            mismatches.append("abaqus_version")
    current_domain = {
        "D11": parameter_bounds.D11,
        "D66": parameter_bounds.D66,
        "coupling_ratio": parameter_bounds.coupling_ratio,
    }
    for name, interval in evidence.validated_parameter_domain.items():
        current = current_domain.get(name)
        if current is None or current[0] < interval[0] or current[1] > interval[1]:
            mismatches.append(f"validated_parameter_domain:{name}")
    evidence_dict = {
        "specimen_model_identifier": evidence.specimen_model_identifier,
        "template_model_hash": evidence.template_model_hash,
        "basis_km_hash": evidence.basis_km_hash,
        "dof_mapping_hash": evidence.dof_mapping_hash,
        "abaqus_version": evidence.abaqus_version,
        "validated_parameter_domain": evidence.validated_parameter_domain,
        "validation_points": evidence.validation_points,
        "observed_errors": evidence.observed_errors,
        "thresholds": evidence.thresholds,
        "validation_timestamp": evidence.validation_timestamp,
        "campaign_identifier": evidence.campaign_identifier,
        "status": evidence.status,
    }
    base["evidence"] = evidence_dict
    base["mismatches"] = tuple(mismatches)
    if mismatches:
        base["reason"] = "Evidence identity/domain mismatch: " + ", ".join(mismatches)
        return base
    base.update(
        status=evidence.status,
        applicable=True,
        reason="Evidence identity and validated domain match this model basis.",
    )
    return base


def _precision_arguments(
    parameters: StageAMatrixParameters,
    sensitivity: object,
    parameter_indexes: Sequence[int],
    parameter_ids: Tuple[str, ...],
    requirements: Mapping[str, ParameterPrecisionRequirement],
) -> Mapping[str, object]:
    selected_coordinates = tuple(
        sensitivity.parameter_coordinates[index] for index in parameter_indexes
    )
    scales = {
        identifier: float(coordinate.scale)
        for identifier, coordinate in zip(parameter_ids, selected_coordinates)
    }
    index_by_id = {identifier: index for index, identifier in enumerate(parameter_ids)}
    jacobian = np.zeros((len(parameter_ids), len(parameter_ids)), dtype=float)
    transformed_ids: list[str] = []
    ratio = parameters.D12 / parameters.D11
    ratio_denominator = 1.0 - ratio * ratio
    for row, identifier in enumerate(parameter_ids):
        if identifier == "D11":
            jacobian[row, index_by_id["D11"]] = 1.0
            transformed_ids.append("x1_log_D11")
        elif identifier == "D66":
            jacobian[row, index_by_id["D66"]] = 1.0
            transformed_ids.append("x2_log_D66")
        elif identifier == "D12":
            jacobian[row, index_by_id["D12"]] = 1.0 / ratio_denominator
            if "D11" in index_by_id:
                jacobian[row, index_by_id["D11"]] = -ratio / ratio_denominator
            transformed_ids.append("x3_atanh_D12_over_D11")
        else:
            jacobian[row, row] = 1.0
            transformed_ids.append(identifier)
    return {
        "precision_requirements": {
            identifier: requirements[identifier]
            for identifier in parameter_ids
            if identifier in requirements
        },
        "physical_parameter_scales": scales,
        "transformed_coordinate_ids": tuple(transformed_ids),
        "transformed_coordinate_jacobian": jacobian,
    }


class MatrixEigenmodeDatasetAdapter:
    """Convert matrix eigenvectors to the comparator's Abaqus dataset contract.

    Translational Abaqus DOFs 1..3 are copied to the existing comparator grid;
    rotational shell DOFs remain matrix-only and are intentionally not exposed
    as displacement components.

    With an explicit ``node_map`` every matrix node is resolved to its exact
    ``INSTANCE:label`` FE node; unmapped nodes or targets outside the reference
    grid are refused.  Without a map, the legacy synthetic path matches matrix
    labels to reference node IDs by exact value, which is not multi-instance
    safe.  Candidate modes record which U1..U3 components the matrix actually
    carries as FE availability, never as experimental measurement.
    """

    def __init__(
        self,
        reference_abaqus: ModalDataset,
        basis_dofs: Sequence[AbaqusDof],
        *,
        node_map: StageAMatrixNodeMap | None = None,
    ) -> None:
        modes = reference_abaqus.sorted_modes()
        if not modes:
            raise ComparatorPairingError(
                "The reference comparison has no Abaqus mode geometry."
            )
        reference = modes[0]
        node_ids = np.asarray(reference.node_ids, dtype=object).reshape(-1)
        self._reference_abaqus = reference_abaqus
        self._node_ids = node_ids.copy()
        self._coordinates = np.asarray(reference.coordinates, dtype=float).copy()
        self._basis_dofs = tuple(basis_dofs)
        self.node_map = node_map
        if node_map is None:
            if len(set(_node_key(item) for item in node_ids)) != len(node_ids):
                raise ComparatorPairingError("Reference Abaqus node IDs must be unique.")
            self._row_by_node = {
                _node_key(item): index for index, item in enumerate(node_ids)
            }
            return
        if not isinstance(node_map, StageAMatrixNodeMap):
            raise TypeError("node_map must be StageAMatrixNodeMap or None.")
        if not all(isinstance(item, str) for item in node_ids):
            raise ComparatorPairingError(
                "A mapped Stage-A candidate requires reference FE node IDs of the "
                "form INSTANCE:label."
            )
        row_by_fe_id: dict[str, int] = {}
        for index, item in enumerate(node_ids):
            if item in row_by_fe_id:
                raise ComparatorPairingError("Reference Abaqus node IDs must be unique.")
            row_by_fe_id[item] = index
        unknown = [target for _, target in node_map.entries if target not in row_by_fe_id]
        if unknown:
            raise ComparatorPairingError(
                f"{len(unknown)} node-map target(s) are not in the reference FE grid "
                f"(first: {unknown[0]!r})."
            )
        self._row_by_fe_id = row_by_fe_id
        self._mapped_locations(self._basis_dofs)

    def _mapped_locations(
        self, dofs: Sequence[AbaqusDof]
    ) -> list[tuple[int, int, int]]:
        locations: list[tuple[int, int, int]] = []
        for vector_row, dof in enumerate(dofs):
            try:
                fe_node = self.node_map.fe_node_id(dof.node_label)
            except StageAMatrixNodeMapError as exc:
                raise ComparatorPairingError(str(exc)) from exc
            if 1 <= dof.dof <= 3:
                locations.append((vector_row, self._row_by_fe_id[fe_node], dof.dof - 1))
        return locations

    def _legacy_locations(
        self, dofs: Sequence[AbaqusDof]
    ) -> list[tuple[int, int, int]]:
        locations: list[tuple[int, int, int]] = []
        for vector_row, dof in enumerate(dofs):
            if not 1 <= dof.dof <= 3:
                continue
            node_row = self._row_by_node.get(_node_key(dof.node_label))
            if node_row is not None:
                locations.append((vector_row, node_row, dof.dof - 1))
        return locations

    def __call__(self, eigenpairs: GeneralizedEigenResult) -> ModalDataset:
        dofs = eigenpairs.dofs if eigenpairs.dofs is not None else self._basis_dofs
        if len(dofs) != eigenpairs.eigenvectors.shape[0]:
            raise ComparatorPairingError(
                "Eigenvector rows do not match the active Abaqus DOF ordering."
            )
        availability: StageAFeAvailability | None = None
        if self.node_map is None:
            locations = self._legacy_locations(dofs)
        else:
            locations = self._mapped_locations(dofs)
            try:
                availability = build_stage_a_fe_availability(
                    self._node_ids, self.node_map, dofs
                )
            except StageAFeAvailabilityError as exc:
                raise ComparatorPairingError(str(exc)) from exc
        if not locations:
            raise ComparatorPairingError(
                "No translational matrix DOFs map to the reference comparator grid."
            )
        available = np.zeros((len(self._node_ids), 3), dtype=bool)
        for _, node_row, component in locations:
            available[node_row, component] = True
        if availability is not None:
            if not np.array_equal(available, availability.mask_array()):
                raise ComparatorPairingError(
                    "Candidate vector placement disagrees with the FE availability contract."
                )
            available = availability.mask_array()

        modes: list[ModeShape] = []
        for mode_index, frequency in enumerate(eigenpairs.frequencies_hz):
            vectors = np.zeros((len(self._node_ids), 3), dtype=float)
            for vector_row, node_row, component in locations:
                vectors[node_row, component] = eigenpairs.eigenvectors[
                    vector_row, mode_index
                ]
            modes.append(
                ModeShape(
                    number=mode_index + 1,
                    frequency_hz=float(frequency),
                    node_ids=self._node_ids.copy(),
                    coordinates=self._coordinates.copy(),
                    vectors=vectors,
                    metadata={
                        "source": "stage_a_affine_matrix_eigensolver",
                        "elastic_mode_index": mode_index + 1,
                        # FE availability of U1..U3 in the active matrix DOFs;
                        # deliberately not ``measured_dofs`` (experimental).
                        "fe_available_dofs": available.copy(),
                        "fe_dof_availability_source": FE_DOF_AVAILABILITY_SOURCE,
                    },
                )
            )
        metadata = {
            "source": "stage_a_affine_matrix_eigensolver",
            "fe_dof_availability_source": FE_DOF_AVAILABILITY_SOURCE,
        }
        if availability is not None:
            metadata["stage_a_node_map_hash"] = self.node_map.content_hash
            metadata["stage_a_fe_availability"] = availability
            metadata["stage_a_fe_availability_hash"] = availability.content_hash
        return ModalDataset(
            source_name="Stage-A affine matrix candidate",
            source_path=self._reference_abaqus.source_path,
            modes=modes,
            metadata=metadata,
            history=list(self._reference_abaqus.history),
        )


class ProductionComparisonPairingProvider:
    """Adapt the current reviewed comparator to ``ComparisonPairingProvider``.

    The provider runs only under an explicit ``FrozenRegistration``: the
    experimental source, FE geometry, calibration, orientation, and required
    FE components are taken from it, never re-selected.  Every candidate is
    built through an explicit matrix node map and checked for FE geometry
    identity and Policy-B availability before the comparator is called.
    Contract violations raise ``StageAProductionPairingRefusal``; only
    ordinary comparator pairing failures raise ``ComparatorPairingError``.
    """

    def __init__(
        self,
        reference_comparison: ComparisonResult,
        candidate_dataset_adapter: MatrixEigenmodeDatasetAdapter,
        *,
        registration: FrozenRegistration | None = None,
        comparator: ComparatorFunction = compare_modal_datasets,
        coordinate_scale_override: float | None = None,
    ) -> None:
        if not isinstance(registration, FrozenRegistration):
            raise StageAProductionPairingRefusal(
                "registration",
                "Production Stage-A pairing requires an explicit FrozenRegistration.",
            )
        if coordinate_scale_override is not None:
            raise StageAProductionPairingRefusal(
                "calibration",
                "A coordinate_scale_override cannot replace the frozen registration "
                "calibration.",
            )
        if (
            not isinstance(candidate_dataset_adapter, MatrixEigenmodeDatasetAdapter)
            or not isinstance(candidate_dataset_adapter.node_map, StageAMatrixNodeMap)
        ):
            raise StageAProductionPairingRefusal(
                "node_map",
                "Production Stage-A pairing requires a MatrixEigenmodeDatasetAdapter "
                "with an explicit StageAMatrixNodeMap.",
            )
        if not reference_comparison.experimental.modes:
            raise ComparatorPairingError(
                "The reference comparison has no experimental mode shapes."
            )
        self.registration = registration
        self.node_map = candidate_dataset_adapter.node_map
        self.node_map_hash = self.node_map.content_hash
        self.geometry_calibration = _frozen_calibration(registration)
        self.orientation_selection = {
            "candidate_id": registration.orientation_candidate_id
        }
        self.experimental_source_identity = _verified_experimental_source(
            registration, reference_comparison
        )
        _require_fe_geometry(
            registration, self.experimental_source_identity, reference_comparison.abaqus
        )
        _require_measurement_contract(registration, reference_comparison.experimental)
        try:
            precheck_required_fe_export(
                registration, self.node_map, candidate_dataset_adapter._basis_dofs
            )
        except StageAFeAvailabilityError as exc:
            raise StageAProductionPairingRefusal("policy_b", str(exc)) from exc
        self.reference_comparison = reference_comparison
        self.candidate_dataset_adapter = candidate_dataset_adapter
        self.comparator = comparator
        self.coordinate_scale_override = None
        self.call_count = 0
        self.failure_count = 0
        self.last_error = ""
        self.last_comparison: ComparisonResult | None = None

    def __call__(
        self,
        observations: Tuple[ModalObservation, ...],
        eigenpairs: GeneralizedEigenResult,
    ) -> PairingResult:
        self.call_count += 1
        experimental_ids = tuple(item.experimental_mode_id for item in observations)
        if len(set(experimental_ids)) != len(experimental_ids):
            raise ComparatorPairingError(
                "Fitting observations must reference unique experimental modes."
            )
        by_number = {
            int(mode.number): mode
            for mode in self.reference_comparison.experimental.modes
        }
        missing = tuple(item for item in experimental_ids if item not in by_number)
        if missing:
            raise ComparatorPairingError(
                "Experimental modes required for re-pairing are unavailable: "
                + ", ".join(map(str, missing))
            )
        experimental = ModalDataset(
            source_name=self.reference_comparison.experimental.source_name,
            source_path=self.reference_comparison.experimental.source_path,
            modes=[by_number[item] for item in experimental_ids],
            metadata=dict(self.reference_comparison.experimental.metadata),
            history=list(self.reference_comparison.experimental.history),
        )
        candidate = self._checked_candidate(eigenpairs)
        try:
            comparison = self.comparator(
                candidate,
                experimental,
                geometry_calibration=self.geometry_calibration,
                orientation_selection=dict(self.orientation_selection),
            )
        except GeometryOrientationAmbiguousError as exc:
            # With a candidate requested, ambiguity means the frozen candidate
            # was not among the comparator's candidates.
            self.failure_count += 1
            self.last_error = str(exc)
            raise StageAProductionPairingRefusal(
                "orientation_candidate_id",
                "The frozen orientation candidate is not available to the "
                f"comparator: {exc}",
            ) from exc
        except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
            self.failure_count += 1
            self.last_error = str(exc)
            if _is_no_geometry_candidates_error(exc):
                raise StageAProductionPairingRefusal(
                    "orientation_candidate_id",
                    "The comparator produced no geometry-alignment candidate for the "
                    f"frozen registration state: {exc}",
                ) from exc
            raise ComparatorPairingError(
                f"Production comparator pairing failed: {exc}"
            ) from exc
        selected = str(_candidate_summary(comparison.geometry)["candidate_id"])
        if selected != self.registration.orientation_candidate_id:
            self.failure_count += 1
            self.last_error = (
                f"The comparator selected geometry candidate {selected}, not the "
                f"frozen candidate {self.registration.orientation_candidate_id}."
            )
            raise StageAProductionPairingRefusal(
                "orientation_candidate_id", self.last_error
            )
        paired_by_experimental = {
            int(pair.experimental_mode): pair for pair in comparison.pairs
        }
        missing_pairs = tuple(
            item for item in experimental_ids if item not in paired_by_experimental
        )
        if missing_pairs:
            self.failure_count += 1
            self.last_error = (
                "No accepted comparator pair for experimental mode(s): "
                + ", ".join(map(str, missing_pairs))
            )
            raise ComparatorPairingError(self.last_error)
        mac_less = tuple(
            item for item in experimental_ids if paired_by_experimental[item].mac is None
        )
        if mac_less:
            self.failure_count += 1
            self.last_error = (
                "Comparator pair(s) for experimental mode(s) "
                + ", ".join(map(str, mac_less))
                + " have no MAC; a frequency-only match does not prove mode identity "
                "for inverse identification."
            )
            raise MacEvidencePairingError(self.last_error)
        self.last_comparison = comparison
        self.last_error = ""
        assignments = tuple(
            ModeAssignment(
                observation_id=observation.observation_id,
                fe_mode_id=int(
                    paired_by_experimental[observation.experimental_mode_id].abaqus_mode
                ),
                mac=paired_by_experimental[observation.experimental_mode_id].mac,
            )
            for observation in observations
        )
        return PairingResult(
            assignments=assignments,
            method="existing reviewed modal comparator",
            warnings=tuple(comparison.warnings),
        )

    def _checked_candidate(self, eigenpairs: GeneralizedEigenResult) -> ModalDataset:
        """Build one candidate and enforce the frozen FE contracts on it."""
        try:
            candidate = self.candidate_dataset_adapter(eigenpairs)
        except ComparatorPairingError as exc:
            raise StageAProductionPairingRefusal("node_map", str(exc)) from exc
        _require_fe_geometry(
            self.registration, self.experimental_source_identity, candidate
        )
        availability = candidate.metadata.get("stage_a_fe_availability")
        if not isinstance(availability, StageAFeAvailability):
            raise StageAProductionPairingRefusal(
                "policy_b", "The candidate carries no typed FE availability contract."
            )
        if (
            candidate.metadata.get("stage_a_node_map_hash") != self.node_map_hash
            or availability.node_map_hash != self.node_map_hash
        ):
            raise StageAProductionPairingRefusal(
                "node_map",
                "The candidate was not built from the provider's frozen node map.",
            )
        try:
            check_required_fe_availability(
                self.registration, availability, node_map=self.node_map
            )
        except StageAFeAvailabilityError as exc:
            raise StageAProductionPairingRefusal("policy_b", str(exc)) from exc
        return candidate


# The reviewed comparator reports an empty candidate set only as this exact
# RuntimeError (reviewed_core); there is no typed exception for it.
_NO_GEOMETRY_CANDIDATES_MESSAGE = "No geometry-alignment candidates were generated."


def _is_no_geometry_candidates_error(exc: BaseException) -> bool:
    return type(exc) is RuntimeError and str(exc) == _NO_GEOMETRY_CANDIDATES_MESSAGE


def _frozen_calibration(registration: FrozenRegistration) -> CoordinateCalibration:
    try:
        calibration = CoordinateCalibration.from_mapping(registration.calibration)
        state = calibration.to_dict()
    except (TypeError, ValueError) as exc:
        raise StageAProductionPairingRefusal(
            "calibration", f"The frozen calibration is not usable: {exc}"
        ) from exc
    if calibration_fingerprint(state) != registration.calibration_fingerprint:
        raise StageAProductionPairingRefusal(
            "calibration",
            "The frozen calibration does not round-trip to its fingerprint.",
        )
    return calibration


def _verified_experimental_source(
    registration: FrozenRegistration, comparison: ComparisonResult
) -> dict[str, object]:
    identity = experimental_source_content_identity(comparison.experimental.source_path)
    if identity is None:
        raise StageAProductionPairingRefusal(
            "experimental_source_identity",
            "The experimental source file is not readable, so its content identity "
            "cannot be verified; the legacy path/size/mtime identity is not used.",
        )
    try:
        registration.check_compatible(identity, registration.fe_geometry_identity)
    except RegistrationMismatchError as exc:
        raise StageAProductionPairingRefusal(exc.field, str(exc)) from exc
    return identity


def _require_fe_geometry(
    registration: FrozenRegistration,
    experimental_identity: Mapping[str, object],
    dataset: ModalDataset,
) -> None:
    try:
        geometry = modal_dataset_geometry_identity(dataset)
        registration.check_compatible(experimental_identity, geometry)
    except RegistrationMismatchError as exc:
        raise StageAProductionPairingRefusal(exc.field, str(exc)) from exc
    except ValueError as exc:
        raise StageAProductionPairingRefusal(
            "fe_geometry_identity", f"FE geometry identity unavailable: {exc}"
        ) from exc


def _require_measurement_contract(
    registration: FrozenRegistration, experimental: ModalDataset
) -> None:
    """The comparator's experimental masks must be the frozen measurement contract."""
    modes = experimental.sorted_modes()
    node_ids = modes[0].node_ids
    current_ids = [
        item.item() if isinstance(item, np.generic) else item
        for item in np.asarray(node_ids, dtype=object).reshape(-1)
    ]
    frozen = np.asarray(registration.measured_dof_contract, dtype=bool)
    if current_ids != list(registration.experimental_node_ids) or any(
        _explicit_measurement_mask(mode) is None for mode in modes
    ):
        raise StageAProductionPairingRefusal(
            "measured_dof_contract",
            "The experimental nodes or explicit measured-DOF masks do not match the "
            "frozen registration.",
        )
    for mask in experimental_measurement_masks(modes, node_ids):
        if not np.array_equal(np.asarray(mask, dtype=bool), frozen):
            raise StageAProductionPairingRefusal(
                "measured_dof_contract",
                "An experimental measured-DOF mask differs from the frozen "
                "measurement contract.",
            )


def create_production_pairing_provider(
    comparison: ComparisonResult,
    affine_model: StageAAffineBasis,
    *,
    registration: FrozenRegistration | None = None,
    comparator: ComparatorFunction = compare_modal_datasets,
    coordinate_scale_override: float | None = None,
) -> ProductionComparisonPairingProvider:
    """Create the frozen production adapter without changing comparator thresholds.

    Requires an explicit ``FrozenRegistration`` and a basis with an explicit
    ``StageAMatrixNodeMap``; anything else is a ``StageAProductionPairingRefusal``.
    """

    if not isinstance(registration, FrozenRegistration):
        raise StageAProductionPairingRefusal(
            "registration",
            "Production Stage-A pairing requires an explicit FrozenRegistration.",
        )
    if affine_model.node_map is None:
        raise StageAProductionPairingRefusal(
            "node_map",
            "Production Stage-A pairing requires an explicit matrix node map; "
            "matrix labels are never matched to FE node IDs implicitly.",
        )
    try:
        adapter = MatrixEigenmodeDatasetAdapter(
            comparison.abaqus, affine_model.dofs, node_map=affine_model.node_map
        )
    except ComparatorPairingError as exc:
        raise StageAProductionPairingRefusal("node_map", str(exc)) from exc
    return ProductionComparisonPairingProvider(
        comparison,
        adapter,
        registration=registration,
        comparator=comparator,
        coordinate_scale_override=coordinate_scale_override,
    )


def _node_key(value: object) -> tuple[str, object]:
    if isinstance(value, np.generic):
        value = value.item()
    return type(value).__name__, value


def _apply_campaign_policy(
    observations: Sequence[ModalObservation],
    policy: StageACampaignPolicy,
) -> Tuple[ModalObservation, ...]:
    excluded_ids = set(policy.excluded_experimental_mode_ids)
    result: list[ModalObservation] = []
    for observation in observations:
        if observation.experimental_mode_id not in excluded_ids:
            result.append(observation)
            continue
        metadata = dict(observation.metadata)
        metadata["pre_campaign_inclusion_status"] = observation.inclusion_status.value
        metadata["pre_campaign_inclusion_reason"] = observation.reason
        result.append(
            replace(
                observation,
                inclusion_status=InclusionStatus.EXCLUDED,
                reason=policy.excluded_mode_reason,
                metadata=metadata,
            )
        )
    return tuple(result)


MAC_UNAVAILABLE_REASON = (
    "MAC unavailable: a frequency-only match does not prove mode identity, so the "
    "pair is excluded from inverse identification"
)


def _apply_mac_evidence_policy(
    observations: Sequence[ModalObservation],
) -> Tuple[ModalObservation, ...]:
    """Exclude observations without MAC evidence from the inverse fit (D-FREQONLY).

    The comparator result is not changed, so frequency-only matches remain in
    diagnostics and reports.  Only ``mac is None`` is excluded: a numeric MAC,
    including 0.0, is left to the existing upstream gates, and no MAC is ever
    inferred from frequency.
    """
    result: list[ModalObservation] = []
    for observation in observations:
        if (
            observation.mac is not None
            or observation.inclusion_status == InclusionStatus.EXCLUDED
        ):
            result.append(observation)
            continue
        metadata = dict(observation.metadata)
        metadata["pre_mac_policy_inclusion_status"] = observation.inclusion_status.value
        metadata["pre_mac_policy_inclusion_reason"] = observation.reason
        result.append(
            replace(
                observation,
                inclusion_status=InclusionStatus.EXCLUDED,
                reason=f"{MAC_UNAVAILABLE_REASON} (comparator: {observation.reason})",
                metadata=metadata,
            )
        )
    return tuple(result)


def _excluded_clusters(
    clusters: Sequence[ModalCluster],
) -> Tuple[ModalCluster, ...]:
    result: list[ModalCluster] = []
    for cluster in clusters:
        metadata = dict(cluster.metadata)
        metadata["pre_solver_inclusion_status"] = cluster.inclusion_status.value
        metadata["pre_solver_reason"] = cluster.reason
        result.append(
            replace(
                cluster,
                inclusion_status=InclusionStatus.EXCLUDED,
                reason="cluster_requires_subspace_solver",
                metadata=metadata,
            )
        )
    return tuple(result)


def _usable_scalar_observations(
    observations: Sequence[ModalObservation],
    clusters: Sequence[ModalCluster],
    configuration: InverseSolverConfiguration,
) -> tuple[
    Tuple[ModalObservation, ...],
    np.ndarray,
    Tuple[ExcludedSolverObservation, ...],
]:
    cluster_members = {
        observation_id: cluster.cluster_id
        for cluster in clusters
        for observation_id in cluster.observation_ids
    }
    usable: list[ModalObservation] = []
    weights: list[float] = []
    excluded: list[ExcludedSolverObservation] = []
    for observation in observations:
        if observation.observation_id in cluster_members:
            excluded.append(
                ExcludedSolverObservation(
                    observation.observation_id,
                    "cluster_member_excluded",
                    f"Member of {cluster_members[observation.observation_id]}; not an independent equation.",
                )
            )
        elif observation.inclusion_status == InclusionStatus.EXCLUDED:
            excluded.append(
                ExcludedSolverObservation(
                    observation.observation_id, "excluded", observation.reason
                )
            )
        elif observation.inclusion_status == InclusionStatus.DOWNWEIGHTED:
            weight = configuration.downweighted_observation_weights.get(
                observation.observation_id
            )
            if weight is None:
                excluded.append(
                    ExcludedSolverObservation(
                        observation.observation_id,
                        "downweighted_without_numerical_weight",
                        "DOWNWEIGHTED observations require an explicit numerical weight.",
                    )
                )
            else:
                usable.append(observation)
                weights.append(float(weight))
        else:
            usable.append(observation)
            weights.append(1.0)
    if not usable:
        raise StageAIdentificationError(
            "No usable scalar modal observations remain after campaign, MAC-evidence, "
            "and cluster policy; frequency-only (MAC-less) pairs are never fitted."
        )
    return tuple(usable), np.asarray(weights, dtype=float), tuple(excluded)


def _resolved_uncertainty(
    observations: Tuple[ModalObservation, ...],
    all_observations: Tuple[ModalObservation, ...],
    standard_deviations: float | Sequence[float] | Mapping[str, float] | None,
    covariance: np.ndarray | None,
    covariance_observation_ids: Sequence[str] | None,
) -> tuple[np.ndarray | None, np.ndarray | None]:
    if standard_deviations is not None and covariance is not None:
        raise StageAIdentificationError(
            "Supply standard deviations or covariance, not both."
        )
    if standard_deviations is None:
        selected_covariance = None
    elif isinstance(standard_deviations, Mapping):
        missing = tuple(
            item.observation_id
            for item in observations
            if item.observation_id not in standard_deviations
        )
        if missing:
            raise StageAIdentificationError(
                "Missing standard deviations for usable observations: "
                + ", ".join(missing)
            )
        return (
            np.asarray(
                [standard_deviations[item.observation_id] for item in observations],
                dtype=float,
            ),
            None,
        )
    elif np.isscalar(standard_deviations):
        return np.full(len(observations), float(standard_deviations)), None
    else:
        values = np.asarray(standard_deviations, dtype=float)
        if values.shape == (len(observations),):
            return values, None
        if values.shape == (len(all_observations),):
            by_id = {
                item.observation_id: value
                for item, value in zip(all_observations, values)
            }
            return np.asarray(
                [by_id[item.observation_id] for item in observations], dtype=float
            ), None
        raise StageAIdentificationError(
            "Standard deviations must align with all or usable observations."
        )

    if covariance is None:
        return None, None
    matrix = np.asarray(covariance, dtype=float)
    if covariance_observation_ids is None:
        if matrix.shape != (len(observations), len(observations)):
            raise StageAIdentificationError(
                "Covariance without observation IDs must align with usable observations."
            )
        return None, matrix
    identifiers = tuple(str(item) for item in covariance_observation_ids)
    if len(set(identifiers)) != len(identifiers):
        raise StageAIdentificationError("Covariance observation IDs must be unique.")
    if matrix.shape != (len(identifiers), len(identifiers)):
        raise StageAIdentificationError(
            "Covariance shape must match covariance_observation_ids."
        )
    index_by_id = {item: index for index, item in enumerate(identifiers)}
    try:
        indexes = [index_by_id[item.observation_id] for item in observations]
    except KeyError as exc:
        raise StageAIdentificationError(
            f"Covariance is missing usable observation {exc.args[0]}."
        ) from exc
    return None, matrix[np.ix_(indexes, indexes)]


def _require_full_rank_subset(
    identifiability: IdentifiabilityResult, subset: Sequence[str]
) -> None:
    """Hard block: the fitted subset must have full numerical rank."""
    subset_set = set(subset)
    if subset_set == set(identifiability.parameter_ids):
        rank = identifiability.rank
    else:
        diagnostic = next(
            (
                item
                for item in identifiability.subset_ranking
                if set(item.parameter_ids) == subset_set
            ),
            None,
        )
        rank = None if diagnostic is None else diagnostic.rank
    if rank is None or rank < len(subset_set):
        raise StageAIdentificationError(
            f"The selected Stage-A subset {tuple(subset)} is rank deficient "
            f"(numerical rank {rank}); this is a hard block that no override can bypass."
        )


def _conditioning_override_provenance(
    identifiability: IdentifiabilityResult,
    policy: StageACampaignPolicy,
    subset: Sequence[str],
) -> Mapping[str, object]:
    """Record which full-rank conditioning criteria an explicit override bypassed."""
    criteria = []
    if identifiability.condition_number > policy.condition_warning_threshold:
        criteria.append(
            {
                "criterion": "condition_number",
                "value": float(identifiability.condition_number),
                "threshold": policy.condition_warning_threshold,
            }
        )
    if identifiability.collinearity.warning:
        criteria.append(
            {
                "criterion": "collinearity_gamma",
                "value": float(identifiability.collinearity.gamma),
                "threshold": policy.collinearity_warning_threshold,
            }
        )
    return {
        "override": "full_rank_conditioning",
        "overridden_criteria": tuple(criteria),
        "numerical_rank": identifiability.rank,
        "fitted_parameter_subset": tuple(subset),
    }


def _fixed_pairing(
    observations: Tuple[ModalObservation, ...], mode_count: int
) -> PairingResult:
    if any(item.fe_mode_id > mode_count for item in observations):
        raise StageAIdentificationError(
            "Fixed-pair fallback cannot map source FE mode IDs into the computed spectrum."
        )
    return PairingResult(
        assignments=tuple(
            ModeAssignment(item.observation_id, item.fe_mode_id)
            for item in observations
        ),
        method="explicit fixed-pair fallback without experimental-vector tracking",
        warnings=(
            "Production comparator re-pairing was unavailable; fixed-pair fallback is active.",
        ),
    )


def identify_stage_a(
    comparison: ComparisonResult,
    affine_model: StageAAffineBasis,
    initial_parameters: StageAMatrixParameters,
    parameter_bounds: StageAParameterBounds,
    requested_parameter_subset: Sequence[str],
    solver_configuration: InverseSolverConfiguration,
    *,
    design_id: str,
    physical_specimen_id: str,
    test_run_id: str,
    campaign_policy: StageACampaignPolicy | None = None,
    observation_standard_deviations: (
        float | Sequence[float] | Mapping[str, float] | None
    ) = None,
    observation_covariance: np.ndarray | None = None,
    covariance_observation_ids: Sequence[str] | None = None,
    priors: Mapping[str, ParameterPrior] | None = None,
    pairing_provider: ComparisonPairingProvider | None = None,
    registration: FrozenRegistration | None = None,
    validation_evidence: ModelValidationEvidence | None = None,
    model_template_hash: str | None = None,
    abaqus_version: str | None = None,
) -> StageAIdentificationResult:
    """Run the complete production Stage-A pipeline through the existing services.

    Without an injected ``pairing_provider`` the production comparator pairing
    runs under ``registration`` (a FrozenRegistration), which is then required.
    ``StageAProductionPairingRefusal`` always propagates: a frozen-contract
    violation never becomes a fixed-pair fallback.

    Only curve-fitted experimental modes are identification input (SPEC §4,
    D-002): peak-derived or unclassifiable modes raise
    ``IdentificationInputSourceRefusal`` before any computation.

    A rank-deficient fitted subset is a hard block.
    ``solver_configuration.allow_non_identifiable_subset`` only overrides the
    condition-number and collinearity (gamma) limits of a full-rank subset, and
    the overridden criteria are recorded in ``metadata["identifiability_override"]``.
    """

    if not isinstance(comparison, ComparisonResult):
        raise TypeError("comparison must be ComparisonResult.")
    if not isinstance(affine_model, StageAAffineBasis):
        raise TypeError("affine_model must be StageAAffineBasis.")
    if not isinstance(initial_parameters, StageAMatrixParameters):
        raise TypeError("initial_parameters must be StageAMatrixParameters.")
    if not isinstance(parameter_bounds, StageAParameterBounds):
        raise TypeError("parameter_bounds must be StageAParameterBounds.")
    if not isinstance(solver_configuration, InverseSolverConfiguration):
        raise TypeError("solver_configuration must be InverseSolverConfiguration.")
    require_identification_input(comparison.experimental)
    policy = campaign_policy or StageACampaignPolicy()
    requested = tuple(str(item).strip() for item in requested_parameter_subset)
    if not requested or len(set(requested)) != len(requested):
        raise StageAIdentificationError(
            "requested_parameter_subset must contain unique Stage-A parameter IDs."
        )

    cluster_analysis = cluster_comparison_result(
        comparison,
        design_id,
        physical_specimen_id,
        test_run_id,
        relative_frequency_gap=policy.cluster_relative_frequency_gap,
    )
    observations = _apply_mac_evidence_policy(
        _apply_campaign_policy(cluster_analysis.observations, policy)
    )
    clusters = _excluded_clusters(cluster_analysis.clusters)
    usable, numerical_weights, preliminary_exclusions = _usable_scalar_observations(
        observations, clusters, solver_configuration
    )
    standard_deviations, covariance = _resolved_uncertainty(
        usable,
        observations,
        observation_standard_deviations,
        observation_covariance,
        covariance_observation_ids,
    )

    initial_eigenpairs = solve_generalized_eigenproblem(
        affine_model.reconstruct_stiffness(initial_parameters),
        affine_model.reconstruct_mass(initial_parameters),
        solver_configuration.mode_count,
        expected_rigid_body_modes=solver_configuration.expected_rigid_body_modes,
        dofs=affine_model.dofs,
    )
    if registration is not None and pairing_provider is not None:
        if not (
            isinstance(pairing_provider, ProductionComparisonPairingProvider)
            and pairing_provider.registration == registration
        ):
            raise StageAIdentificationError(
                "registration applies to the production pairing provider; it does "
                "not match the injected pairing_provider."
            )
    active_provider = pairing_provider
    fallback_reason = ""
    if active_provider is None:
        try:
            active_provider = create_production_pairing_provider(
                comparison, affine_model, registration=registration
            )
        except StageAProductionPairingRefusal:
            raise
        except ComparatorPairingError as exc:
            fallback_reason = str(exc)
    pairing_mode = PairingProviderMode.COMPARATOR
    if active_provider is not None:
        try:
            initial_pairing = active_provider(usable, initial_eigenpairs)
        except StageAProductionPairingRefusal:
            raise
        except MacEvidencePairingError as exc:
            # Fixed pairs must not stand in for missing MAC evidence.
            raise StageAIdentificationError(
                "Initial production pairing has no MAC evidence; Stage-A "
                f"identification is refused without fixed-pair fallback: {exc}"
            ) from exc
        except (ValueError, RuntimeError, MatrixModelError) as exc:
            fallback_reason = str(exc)
            initial_pairing = None
    else:
        initial_pairing = None
    if initial_pairing is None:
        if not policy.allow_fixed_pair_fallback:
            raise StageAIdentificationError(
                "Production comparison-backed pairing is unavailable: " + fallback_reason
            )
        initial_pairing = _fixed_pairing(usable, solver_configuration.mode_count)
        active_provider = None
        pairing_mode = PairingProviderMode.FIXED_PAIR_FALLBACK

    assignment_by_id = {
        item.observation_id: item.fe_mode_id for item in initial_pairing.assignments
    }
    normalized_observations = tuple(
        replace(
            item,
            fe_mode_id=assignment_by_id.get(item.observation_id, item.fe_mode_id),
        )
        for item in observations
    )

    try:
        # Rows come back in ``usable`` order: exactly the initially paired modes.
        sensitivity = compute_stage_a_sensitivity(
            affine_model,
            initial_parameters,
            solver_configuration.mode_count,
            expected_rigid_body_modes=solver_configuration.expected_rigid_body_modes,
            finite_difference_relative_steps=(),
            observed_mode_ids=tuple(
                assignment_by_id[item.observation_id] for item in usable
            ),
        )
    except ScalarModeSensitivityRefusal as exc:
        raise StageAIdentificationError(
            f"Stage-A initial sensitivity refused: {exc}"
        ) from exc
    try:
        parameter_indexes = [sensitivity.parameter_ids.index(item) for item in requested]
    except ValueError as exc:
        raise StageAIdentificationError(
            f"Unsupported requested Stage-A parameter: {exc.args[0]}."
        ) from exc
    requested_sensitivity = sensitivity.scaled_sensitivity[:, parameter_indexes]
    weighted_sensitivity = numerical_weights[:, np.newaxis] ** 0.5 * requested_sensitivity
    whitening = whiten_sensitivity(
        weighted_sensitivity,
        standard_deviations=standard_deviations,
        covariance=covariance,
        observation_ids=tuple(item.observation_id for item in usable),
        parameter_ids=requested,
        allow_unweighted=solver_configuration.allow_unweighted,
    )
    identifiability = analyze_identifiability(
        whitening,
        condition_warning_threshold=policy.condition_warning_threshold,
        collinearity_warning_threshold=policy.collinearity_warning_threshold,
        **_precision_arguments(
            initial_parameters,
            sensitivity,
            parameter_indexes,
            requested,
            policy.precision_requirements,
        ),
    )
    initial_identifiability = identifiability
    recommended = (
        None
        if identifiability.best_identifiable_subset is None
        else identifiability.best_identifiable_subset.parameter_ids
    )
    override_used = False
    identifiability_override = None
    subset_selection = "requested_subset_identifiable"
    if (
        identifiability.structurally_identifiable
        and identifiability.directionally_separable
    ):
        fitted_subset = requested
    elif (
        identifiability.structurally_identifiable
        and solver_configuration.allow_non_identifiable_subset
    ):
        # The override covers full-rank conditioning/collinearity limits only;
        # a rank-deficient subset can never be fitted through it.
        fitted_subset = requested
        override_used = True
        subset_selection = "explicit_non_identifiable_override"
        identifiability_override = _conditioning_override_provenance(
            identifiability, policy, requested
        )
    elif policy.approve_recommended_subset and recommended is not None:
        fitted_subset = recommended
        subset_selection = "explicitly_approved_recommended_subset"
    elif not identifiability.structurally_identifiable:
        raise StageAIdentificationError(
            "The requested Stage-A subset is not structurally identifiable: it is "
            "rank deficient (numerical rank "
            f"{identifiability.rank} < {len(requested)} fitted parameters, tolerance "
            f"{identifiability.numerical_rank_tolerance:.6g}); this is a hard block that "
            "no override can bypass. "
            f"Recommended full-rank subset: {recommended}."
        )
    else:
        raise StageAIdentificationError(
            "The requested Stage-A subset is not structurally identifiable or "
            "directionally separable; "
            f"recommended subset: {recommended}. Explicitly approve the recommendation "
            "or enable the non-identifiable override."
        )
    _require_full_rank_subset(identifiability, fitted_subset)

    tracking_mode = (
        ModeTrackingMode.COMPARISON_BACKED
        if active_provider is not None
        else ModeTrackingMode.FIXED_PAIR_SYNTHETIC
    )
    configured_solver = replace(
        solver_configuration,
        tracking_mode=tracking_mode,
        allow_non_identifiable_subset=override_used,
    )
    reference = f"stage-a/{design_id}/{physical_specimen_id}/{test_run_id}/initial-svd"
    try:
        inverse_result = solve_stage_a_inverse(
            affine_model,
            normalized_observations + clusters,
            fitted_subset,
            initial_parameters,
            parameter_bounds,
            configured_solver,
            observation_standard_deviations=standard_deviations,
            observation_covariance=covariance,
            priors=priors,
            identifiability=identifiability,
            identifiability_metadata_reference=reference,
            comparison_pairing_provider=active_provider,
        )
    except StageAProductionPairingRefusal:
        raise
    except (InverseSolverValidationError, MatrixModelError, ValueError) as exc:
        raise StageAIdentificationError(f"Stage-A inverse solve failed: {exc}") from exc

    final_values = dict(inverse_result.fixed_parameters)
    final_values.update(inverse_result.fitted_parameters)
    final_parameters = StageAMatrixParameters(
        final_values["D11"], final_values["D12"], final_values["D66"]
    )
    final_assignment_by_id = {
        item.observation_id: item.fe_mode_id
        for item in inverse_result.final_pairing.assignments
    }
    try:
        # Rows come back in ``usable`` order: exactly the finally paired modes.
        optimum_sensitivity = compute_stage_a_sensitivity(
            affine_model,
            final_parameters,
            solver_configuration.mode_count,
            expected_rigid_body_modes=solver_configuration.expected_rigid_body_modes,
            finite_difference_relative_steps=(),
            observed_mode_ids=tuple(
                final_assignment_by_id[item.observation_id] for item in usable
            ),
        )
    except ScalarModeSensitivityRefusal as exc:
        raise StageAIdentificationError(
            f"Stage-A optimum sensitivity refused: {exc}"
        ) from exc
    optimum_parameter_indexes = [
        optimum_sensitivity.parameter_ids.index(item) for item in fitted_subset
    ]
    optimum_requested_sensitivity = optimum_sensitivity.scaled_sensitivity[
        :, optimum_parameter_indexes
    ]
    optimum_weighted_sensitivity = (
        numerical_weights[:, np.newaxis] ** 0.5 * optimum_requested_sensitivity
    )
    optimum_whitening = whiten_sensitivity(
        optimum_weighted_sensitivity,
        standard_deviations=standard_deviations,
        covariance=covariance,
        observation_ids=tuple(item.observation_id for item in usable),
        parameter_ids=fitted_subset,
        allow_unweighted=solver_configuration.allow_unweighted,
    )
    identifiability = analyze_identifiability(
        optimum_whitening,
        condition_warning_threshold=policy.condition_warning_threshold,
        collinearity_warning_threshold=policy.collinearity_warning_threshold,
        **_precision_arguments(
            final_parameters,
            optimum_sensitivity,
            optimum_parameter_indexes,
            tuple(fitted_subset),
            policy.precision_requirements,
        ),
    )

    cluster_ids = {item.cluster_id for item in clusters}
    inverse_excluded_observations = tuple(
        item
        for item in inverse_result.excluded_observations
        if item.observation_id not in cluster_ids
    )
    exclusions_by_key = {
        (item.observation_id, item.status): item
        for item in preliminary_exclusions + inverse_excluded_observations
    }
    warnings = list(comparison.warnings)
    warnings.extend(identifiability.warnings)
    warnings.extend(inverse_result.warnings)
    if fallback_reason and pairing_mode == PairingProviderMode.FIXED_PAIR_FALLBACK:
        warnings.append(
            "Production pairing unavailable; explicit fixed-pair fallback used: "
            + fallback_reason
        )
    if subset_selection != "requested_subset_identifiable":
        warnings.append(
            f"Stage-A subset selection: {subset_selection}; fitted {fitted_subset}."
        )
    model_validation = assess_model_validation_evidence(
        validation_evidence,
        affine_model,
        physical_specimen_id=physical_specimen_id,
        parameter_bounds=parameter_bounds,
        model_template_hash=model_template_hash,
        abaqus_version=abaqus_version,
    )
    ratio = final_parameters.D12 / final_parameters.D11
    bound_values = {
        "D11": (final_parameters.D11, parameter_bounds.D11),
        "D66": (final_parameters.D66, parameter_bounds.D66),
        "coupling_ratio": (ratio, parameter_bounds.coupling_ratio),
    }
    bound_hits = tuple(
        name
        for name, (value, interval) in bound_values.items()
        if any(
            math.isclose(
                value,
                endpoint,
                rel_tol=100.0 * np.finfo(float).eps,
                abs_tol=100.0 * np.finfo(float).eps * max(abs(endpoint), 1.0),
            )
            for endpoint in interval
        )
    )
    if not identifiability.structurally_identifiable:
        identifiability_status = "STRUCTURALLY_NON_IDENTIFIABLE"
    elif not identifiability.directionally_separable:
        identifiability_status = "DIRECTIONALLY_INSEPARABLE"
    elif identifiability.practically_precise_enough is True:
        identifiability_status = "PASS"
    elif identifiability.practically_precise_enough is False:
        identifiability_status = "FAIL_IMPRECISE"
    else:
        identifiability_status = "NOT_ASSESSED_MISSING_PRECISION_REQUIREMENTS"
    scientific_statuses = {
        "optimizer_solver": {
            "status": "PASS" if inverse_result.success else "FAIL",
            "legacy_inverse_success": inverse_result.success,
        },
        "fit_quality": {
            "status": "NOT_ASSESSED_NO_DECLARED_ACCEPTANCE_THRESHOLD",
            "objective_final": inverse_result.objective_final,
        },
        "identifiability_at_optimum": {
            "status": identifiability_status,
            "structurally_identifiable": identifiability.structurally_identifiable,
            "directionally_separable": identifiability.directionally_separable,
            "practically_precise_enough": identifiability.practically_precise_enough,
            "overall_practical_identifiability": (
                identifiability.overall_practical_identifiability
            ),
            "reason": identifiability.precision_status,
        },
        "bounds": {
            "status": "AT_BOUND_REVIEW_REQUIRED" if bound_hits else "WITHIN_BOUNDS",
            "bound_hits": bound_hits,
        },
        "direct_fe_validation": {
            "status": "NOT_RUN",
            "required": True,
        },
        "hold_out_validation": {
            "status": "NOT_RUN",
            "required": True,
        },
        "model_validation_evidence": {
            "status": model_validation["status"],
            "applicable": model_validation["applicable"],
        },
        "material_identification_validation": {
            "status": "NOT_VALIDATED",
            "reason": (
                "Solver convergence is independent of fit, precision, direct-FE, "
                "hold-out, and model-evidence validation."
            ),
        },
    }
    metadata = {
        "identifiability_reference": reference,
        "non_identifiable_override": override_used,
        "identifiability_override": identifiability_override,
        "recommended_subset_approved": bool(
            subset_selection == "explicitly_approved_recommended_subset"
        ),
        "subset_selection": subset_selection,
        "campaign_excluded_experimental_mode_ids": policy.excluded_experimental_mode_ids,
        "campaign_exclusion_reason": policy.excluded_mode_reason,
        "cluster_scalar_equations_implemented": False,
        "mac_used_in_objective": False,
        "initial_pairing_signature": initial_pairing.signature,
        "pairing_provider_calls": getattr(active_provider, "call_count", None),
        "pairing_provider_failures": getattr(active_provider, "failure_count", None),
        "pairing_fallback_reason": fallback_reason or None,
        "frozen_registration_hash": (
            active_provider.registration.registration_hash
            if isinstance(active_provider, ProductionComparisonPairingProvider)
            else None
        ),
        "identifiability_evaluated_at": "fitted_optimum",
        "initial_identifiability": {
            "rank": initial_identifiability.rank,
            "condition_number": initial_identifiability.condition_number,
            "structurally_identifiable": initial_identifiability.structurally_identifiable,
            "directionally_separable": initial_identifiability.directionally_separable,
            "precision_status": initial_identifiability.precision_status,
        },
        "model_validation_evidence": model_validation,
        "scientific_statuses": scientific_statuses,
        "mode_identity_caveat": C3B2_MODE_IDENTITY_CAVEAT,
        "stiffness_model": (
            "documented affine approximation in (D11, D12, D66); model-specific "
            f"validation evidence status: {model_validation['status']}"
        ),
        "mass_model": (
            "constant reference mass"
            if affine_model.mass_derivative_D11 is None
            else (
                "affine in D11 (M = M_ref + (D11-D11_ref) * dM/dD11); invariant "
                "to D12 and D66; model-specific validation evidence required"
            )
        ),
        "final_direct_abaqus_verification_required": True,
    }
    return StageAIdentificationResult(
        observations=observations,
        clusters=clusters,
        effective_observation_count=len(inverse_result.observation_ids),
        identifiability=identifiability,
        requested_parameter_subset=requested,
        recommended_parameter_subset=recommended,
        fitted_parameter_subset=tuple(fitted_subset),
        inverse_result=inverse_result,
        excluded_observations=tuple(exclusions_by_key.values()),
        excluded_clusters=clusters,
        pairing_provider_mode=pairing_mode,
        warnings=tuple(dict.fromkeys(item for item in warnings if item)),
        metadata=metadata,
    )


__all__ = [
    "C3B2_MODE_IDENTITY_CAVEAT",
    "ComparatorPairingError",
    "MacEvidencePairingError",
    "MatrixEigenmodeDatasetAdapter",
    "ModelValidationEvidence",
    "PairingProviderMode",
    "ProductionComparisonPairingProvider",
    "StageACampaignPolicy",
    "StageAIdentificationError",
    "StageAIdentificationResult",
    "StageAProductionPairingRefusal",
    "assess_model_validation_evidence",
    "create_production_pairing_provider",
    "identify_stage_a",
    "stage_a_basis_identity",
]
