"""Stage-A Abaqus matrix generation, import, affine reconstruction, and solve.

The module is intentionally independent of the modal-comparator workflow.  It
implements only the Stage-A matrix path described in the inverse-identification
roadmap; modal pairing, sensitivities, and optimisation belong to later work.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import shlex
import subprocess
from typing import Callable, Iterable, Sequence, Tuple

import numpy as np
from scipy import linalg as dense_linalg
from scipy import sparse
from scipy.sparse import linalg as sparse_linalg

from .abaqus_shell_section import (
    StageAShellSectionConfiguration,
    generate_stage_a_shell_general_section,
)
from .stage_a_parameterization import (
    StageAParameterization,
    validate_balanced_d_matrix,
)


STAGE_A_SECTION_MARKER = "** <STAGE_A_SHELL_GENERAL_SECTION>"
STAGE_A_STEPS_MARKER = "** <STAGE_A_ANALYSIS_STEPS>"
STAGE_A_PARAMETER_NAMES = ("D11", "D12", "D66")


class AbaqusMatrixFormatError(ValueError):
    """An Abaqus MATRIX INPUT file is malformed or ambiguous."""


class MatrixModelError(RuntimeError):
    """The Stage-A matrix model cannot be constructed or solved."""


class AbaqusMatrixGenerationError(MatrixModelError):
    """A real Abaqus matrix-generation or extraction process failed."""


def _finite(value: float, name: str) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite real number.") from exc
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite.")
    return normalized


@dataclass(frozen=True, order=True)
class AbaqusDof:
    """One Abaqus matrix coordinate, preserving node and DOF numbering."""

    node_label: int
    dof: int

    def __post_init__(self) -> None:
        if isinstance(self.node_label, bool) or int(self.node_label) != self.node_label:
            raise ValueError("node_label must be an integer.")
        if isinstance(self.dof, bool) or int(self.dof) != self.dof:
            raise ValueError("dof must be an integer.")
        if int(self.node_label) <= 0:
            raise ValueError("node_label must be positive.")
        if int(self.dof) <= 0:
            raise ValueError("dof must be positive.")
        object.__setattr__(self, "node_label", int(self.node_label))
        object.__setattr__(self, "dof", int(self.dof))


@dataclass(frozen=True)
class AbaqusSparseMatrix:
    matrix: sparse.csr_matrix
    dofs: Tuple[AbaqusDof, ...]

    def __post_init__(self) -> None:
        normalized = sparse.csr_matrix(self.matrix, dtype=float)
        if normalized.shape != (len(self.dofs), len(self.dofs)):
            raise ValueError("Matrix shape does not match its Abaqus DOF ordering.")
        if len(set(self.dofs)) != len(self.dofs):
            raise ValueError("Abaqus DOF ordering contains duplicates.")
        if normalized.data.size and not np.isfinite(normalized.data).all():
            raise ValueError("Sparse matrix contains non-finite values.")
        normalized.sum_duplicates()
        normalized.eliminate_zeros()
        object.__setattr__(self, "matrix", normalized)
        object.__setattr__(self, "dofs", tuple(self.dofs))


@dataclass(frozen=True)
class AbaqusMatrixPair:
    stiffness: sparse.csr_matrix
    mass: sparse.csr_matrix
    dofs: Tuple[AbaqusDof, ...]

    def __post_init__(self) -> None:
        stiffness = sparse.csr_matrix(self.stiffness, dtype=float)
        mass = sparse.csr_matrix(self.mass, dtype=float)
        expected_shape = (len(self.dofs), len(self.dofs))
        if stiffness.shape != expected_shape or mass.shape != expected_shape:
            raise ValueError("K and M must share the supplied Abaqus DOF ordering.")
        if len(set(self.dofs)) != len(self.dofs):
            raise ValueError("Abaqus DOF ordering contains duplicates.")
        for name, matrix in (("K", stiffness), ("M", mass)):
            if matrix.data.size and not np.isfinite(matrix.data).all():
                raise ValueError(f"{name} contains non-finite values.")
            matrix.sum_duplicates()
            matrix.eliminate_zeros()
            require_sparse_symmetric(matrix, name=name)
        object.__setattr__(self, "stiffness", stiffness)
        object.__setattr__(self, "mass", mass)
        object.__setattr__(self, "dofs", tuple(self.dofs))


@dataclass(frozen=True)
class _CoordinateEntries:
    values: dict[tuple[AbaqusDof, AbaqusDof], float]
    dofs: frozenset[AbaqusDof]


def _parse_positive_integer(raw: str, name: str, path: Path, line_number: int) -> int:
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise AbaqusMatrixFormatError(
            f"{path.name}:{line_number}: {name} must be an integer."
        ) from exc
    if value <= 0:
        raise AbaqusMatrixFormatError(
            f"{path.name}:{line_number}: {name} must be positive."
        )
    return value


def _read_abaqus_coordinate_entries(path: Path) -> _CoordinateEntries:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Abaqus matrix file was not found: {path}")

    values: dict[tuple[AbaqusDof, AbaqusDof], float] = {}
    dofs: set[AbaqusDof] = set()
    with path.open("r", encoding="ascii", errors="strict", newline="") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("**"):
                continue
            fields = next(csv.reader([raw_line], skipinitialspace=True))
            if len(fields) != 5:
                raise AbaqusMatrixFormatError(
                    f"{path.name}:{line_number}: expected five comma-separated fields, "
                    f"found {len(fields)}."
                )
            left = AbaqusDof(
                _parse_positive_integer(fields[0], "row node label", path, line_number),
                _parse_positive_integer(fields[1], "row DOF", path, line_number),
            )
            right = AbaqusDof(
                _parse_positive_integer(fields[2], "column node label", path, line_number),
                _parse_positive_integer(fields[3], "column DOF", path, line_number),
            )
            try:
                value = float(fields[4].strip().replace("D", "E").replace("d", "e"))
            except ValueError as exc:
                raise AbaqusMatrixFormatError(
                    f"{path.name}:{line_number}: matrix value is not numeric."
                ) from exc
            if not math.isfinite(value):
                raise AbaqusMatrixFormatError(
                    f"{path.name}:{line_number}: matrix value must be finite."
                )

            canonical = (left, right) if left <= right else (right, left)
            if canonical in values:
                raise AbaqusMatrixFormatError(
                    f"{path.name}:{line_number}: duplicate symmetric matrix entry for "
                    f"({left.node_label},{left.dof}) and "
                    f"({right.node_label},{right.dof})."
                )
            values[canonical] = value
            dofs.update((left, right))

    if not values:
        raise AbaqusMatrixFormatError(f"{path.name}: no matrix entries were found.")
    return _CoordinateEntries(values=values, dofs=frozenset(dofs))


def _entries_to_sparse(
    entries: _CoordinateEntries,
    dofs: Tuple[AbaqusDof, ...],
) -> sparse.csr_matrix:
    indexes = {dof: index for index, dof in enumerate(dofs)}
    rows: list[int] = []
    columns: list[int] = []
    data: list[float] = []
    for (left, right), value in entries.values.items():
        if value == 0.0:
            continue
        left_index = indexes[left]
        right_index = indexes[right]
        rows.append(left_index)
        columns.append(right_index)
        data.append(value)
        if left_index != right_index:
            rows.append(right_index)
            columns.append(left_index)
            data.append(value)
    matrix = sparse.coo_matrix(
        (data, (rows, columns)), shape=(len(dofs), len(dofs)), dtype=float
    ).tocsr()
    matrix.sum_duplicates()
    matrix.eliminate_zeros()
    return matrix


def read_abaqus_matrix_input(path: Path) -> AbaqusSparseMatrix:
    """Read one symmetric Abaqus ``FORMAT=MATRIX INPUT`` coordinate file.

    Abaqus writes a single triangular half.  Each off-diagonal value is copied
    once to the opposite half; mirrored or repeated input entries are rejected
    rather than silently summed.  Explicit zero entries participate in the DOF
    map but are removed from sparse storage.
    """

    entries = _read_abaqus_coordinate_entries(path)
    dofs = tuple(sorted(entries.dofs))
    matrix = _entries_to_sparse(entries, dofs)
    require_sparse_symmetric(matrix, name=Path(path).name)
    return AbaqusSparseMatrix(matrix=matrix, dofs=dofs)


def read_abaqus_matrix_pair(
    stiffness_path: Path,
    mass_path: Path,
) -> AbaqusMatrixPair:
    """Read K and M on the sorted union of their exact Abaqus DOF labels."""

    stiffness_entries = _read_abaqus_coordinate_entries(stiffness_path)
    mass_entries = _read_abaqus_coordinate_entries(mass_path)
    dofs = tuple(sorted(stiffness_entries.dofs | mass_entries.dofs))
    stiffness = _entries_to_sparse(stiffness_entries, dofs)
    mass = _entries_to_sparse(mass_entries, dofs)
    return AbaqusMatrixPair(stiffness=stiffness, mass=mass, dofs=dofs)


def sparse_symmetry_error(matrix: sparse.spmatrix) -> float:
    """Return max absolute sparse ``A - A.T`` without densifying."""

    matrix = sparse.csr_matrix(matrix, dtype=float)
    difference = matrix - matrix.T
    difference.eliminate_zeros()
    if difference.nnz == 0:
        return 0.0
    return float(np.max(np.abs(difference.data)))


def is_sparse_symmetric(
    matrix: sparse.spmatrix,
    *,
    rtol: float = 1.0e-10,
    atol: float = 1.0e-12,
) -> bool:
    matrix = sparse.csr_matrix(matrix, dtype=float)
    if matrix.shape[0] != matrix.shape[1]:
        return False
    scale = float(np.max(np.abs(matrix.data))) if matrix.nnz else 0.0
    return sparse_symmetry_error(matrix) <= atol + rtol * scale


def require_sparse_symmetric(
    matrix: sparse.spmatrix,
    *,
    name: str = "matrix",
    rtol: float = 1.0e-10,
    atol: float = 1.0e-12,
) -> None:
    if not is_sparse_symmetric(matrix, rtol=rtol, atol=atol):
        raise MatrixModelError(
            f"{name} is not symmetric within tolerance "
            f"(max |A-A.T|={sparse_symmetry_error(matrix):.6g})."
        )


def _sparse_allclose(
    left: sparse.spmatrix,
    right: sparse.spmatrix,
    *,
    rtol: float,
    atol: float,
) -> bool:
    left = sparse.csr_matrix(left, dtype=float)
    right = sparse.csr_matrix(right, dtype=float)
    if left.shape != right.shape:
        return False
    difference = left - right
    difference.eliminate_zeros()
    error = float(np.max(np.abs(difference.data))) if difference.nnz else 0.0
    left_scale = float(np.max(np.abs(left.data))) if left.nnz else 0.0
    right_scale = float(np.max(np.abs(right.data))) if right.nnz else 0.0
    return error <= atol + rtol * max(left_scale, right_scale)


def relative_sparse_frobenius_error(
    actual: sparse.spmatrix,
    expected: sparse.spmatrix,
) -> float:
    actual = sparse.csr_matrix(actual, dtype=float)
    expected = sparse.csr_matrix(expected, dtype=float)
    if actual.shape != expected.shape:
        raise ValueError("Matrices must have the same shape.")
    denominator = float(sparse_linalg.norm(actual, ord="fro"))
    numerator = float(sparse_linalg.norm(actual - expected, ord="fro"))
    if denominator == 0.0:
        return 0.0 if numerator == 0.0 else math.inf
    return numerator / denominator


@dataclass(frozen=True)
class StageAMatrixParameters:
    """The three affine Stage-A bending parameters."""

    D11: float
    D12: float
    D66: float

    def __post_init__(self) -> None:
        d11 = _finite(self.D11, "D11")
        d12 = _finite(self.D12, "D12")
        d66 = _finite(self.D66, "D66")
        validate_balanced_d_matrix(d11, d11, d12, d66)
        object.__setattr__(self, "D11", d11)
        object.__setattr__(self, "D12", d12)
        object.__setattr__(self, "D66", d66)

    @classmethod
    def from_parameterization(
        cls, parameters: StageAParameterization
    ) -> "StageAMatrixParameters":
        return cls(parameters.D11, parameters.D12, parameters.D66)

    @property
    def values(self) -> np.ndarray:
        return np.asarray((self.D11, self.D12, self.D66), dtype=float)

    def as_parameterization(self) -> StageAParameterization:
        return StageAParameterization(
            D=self.D11,
            D66=self.D66,
            r=self.D12 / self.D11,
        )


def stage_a_matrix_configurations(
    reference: StageAMatrixParameters,
    *,
    relative_step: float = 1.0e-2,
) -> Tuple[StageAMatrixParameters, ...]:
    """Return reference + one admissible perturbation per affine parameter."""

    relative_step = _finite(relative_step, "relative_step")
    if not 0.0 < relative_step < 1.0:
        raise ValueError("relative_step must satisfy 0 < relative_step < 1.")

    d11_step = reference.D11 * relative_step
    d66_step = reference.D66 * relative_step
    d12_step = reference.D11 * relative_step
    d12_candidate = reference.D12 + d12_step
    if abs(d12_candidate) >= reference.D11:
        d12_candidate = reference.D12 - d12_step

    return (
        reference,
        StageAMatrixParameters(
            reference.D11 + d11_step, reference.D12, reference.D66
        ),
        StageAMatrixParameters(
            reference.D11, d12_candidate, reference.D66
        ),
        StageAMatrixParameters(
            reference.D11, reference.D12, reference.D66 + d66_step
        ),
    )


@dataclass(frozen=True)
class StageAAffineBasis:
    reference_parameters: StageAMatrixParameters
    reference_stiffness: sparse.csr_matrix
    basis_matrices: Tuple[sparse.csr_matrix, ...]
    mass: sparse.csr_matrix
    dofs: Tuple[AbaqusDof, ...]

    def __post_init__(self) -> None:
        size = len(self.dofs)
        reference = sparse.csr_matrix(self.reference_stiffness, dtype=float)
        mass = sparse.csr_matrix(self.mass, dtype=float)
        basis = tuple(sparse.csr_matrix(item, dtype=float) for item in self.basis_matrices)
        if len(basis) != len(STAGE_A_PARAMETER_NAMES):
            raise ValueError("Stage A requires exactly three stiffness basis matrices.")
        if reference.shape != (size, size) or mass.shape != (size, size):
            raise ValueError("Reference K and M do not match the Abaqus DOF ordering.")
        if any(item.shape != (size, size) for item in basis):
            raise ValueError("Every basis matrix must have the reference K shape.")
        require_sparse_symmetric(reference, name="reference K")
        require_sparse_symmetric(mass, name="reference M")
        for name, item in zip(STAGE_A_PARAMETER_NAMES, basis):
            require_sparse_symmetric(item, name=f"K_{name}")
        object.__setattr__(self, "reference_stiffness", reference)
        object.__setattr__(self, "basis_matrices", basis)
        object.__setattr__(self, "mass", mass)
        object.__setattr__(self, "dofs", tuple(self.dofs))

    def reconstruct_stiffness(
        self, parameters: StageAMatrixParameters
    ) -> sparse.csr_matrix:
        delta = parameters.values - self.reference_parameters.values
        reconstructed = self.reference_stiffness.copy()
        for coefficient, contribution in zip(delta, self.basis_matrices):
            if coefficient != 0.0:
                reconstructed = reconstructed + coefficient * contribution
        reconstructed = sparse.csr_matrix(reconstructed)
        reconstructed.eliminate_zeros()
        require_sparse_symmetric(reconstructed, name="reconstructed K")
        return reconstructed


def build_stage_a_affine_basis(
    reference_parameters: StageAMatrixParameters,
    reference_matrices: AbaqusMatrixPair,
    perturbations: Sequence[tuple[StageAMatrixParameters, AbaqusMatrixPair]],
    *,
    mass_rtol: float = 1.0e-12,
    mass_atol: float = 1.0e-14,
) -> StageAAffineBasis:
    """Recover three affine K contributions from four admissible Abaqus jobs."""

    if len(perturbations) != len(STAGE_A_PARAMETER_NAMES):
        raise ValueError("Stage A basis recovery requires exactly three perturbations.")

    delta_rows: list[np.ndarray] = []
    stiffness_differences: list[sparse.csr_matrix] = []
    for parameters, matrices in perturbations:
        if matrices.dofs != reference_matrices.dofs:
            raise MatrixModelError("All basis jobs must have identical Abaqus DOF ordering.")
        if not _sparse_allclose(
            matrices.mass,
            reference_matrices.mass,
            rtol=mass_rtol,
            atol=mass_atol,
        ):
            mass_error = relative_sparse_frobenius_error(
                reference_matrices.mass, matrices.mass
            )
            raise MatrixModelError(
                "Stage-A mass matrix changed with D11/D12/D66; a single verified M "
                f"cannot be used (relative Frobenius change {mass_error:.6g})."
            )
        delta_rows.append(parameters.values - reference_parameters.values)
        stiffness_differences.append(
            sparse.csr_matrix(matrices.stiffness - reference_matrices.stiffness)
        )

    delta_matrix = np.vstack(delta_rows)
    if np.linalg.matrix_rank(delta_matrix) != len(STAGE_A_PARAMETER_NAMES):
        raise MatrixModelError("Stage-A perturbation vectors are linearly dependent.")
    inverse_delta = np.linalg.inv(delta_matrix)

    contributions: list[sparse.csr_matrix] = []
    for basis_index in range(len(STAGE_A_PARAMETER_NAMES)):
        contribution = sparse.csr_matrix(reference_matrices.stiffness.shape, dtype=float)
        for sample_index, difference in enumerate(stiffness_differences):
            coefficient = inverse_delta[basis_index, sample_index]
            if coefficient != 0.0:
                contribution = contribution + coefficient * difference
        contribution = sparse.csr_matrix(contribution)
        contribution.eliminate_zeros()
        contributions.append(contribution)

    return StageAAffineBasis(
        reference_parameters=reference_parameters,
        reference_stiffness=reference_matrices.stiffness,
        basis_matrices=tuple(contributions),
        mass=reference_matrices.mass,
        dofs=reference_matrices.dofs,
    )


@dataclass(frozen=True)
class GeneralizedEigenResult:
    eigenvalues: np.ndarray
    frequencies_hz: np.ndarray
    eigenvectors: np.ndarray
    dofs: Tuple[AbaqusDof, ...] | None
    rigid_body_eigenvalues: np.ndarray


def _remove_fully_inactive_dofs(
    stiffness: sparse.csr_matrix,
    mass: sparse.csr_matrix,
    dofs: Tuple[AbaqusDof, ...] | None,
) -> tuple[sparse.csr_matrix, sparse.csr_matrix, Tuple[AbaqusDof, ...] | None]:
    activity = np.asarray(
        (stiffness.getnnz(axis=1) + mass.getnnz(axis=1)) > 0
    ).ravel()
    if activity.all():
        return stiffness, mass, dofs
    active = np.flatnonzero(activity)
    if active.size == 0:
        raise MatrixModelError("K and M contain no active degrees of freedom.")
    reduced_dofs = tuple(dofs[index] for index in active) if dofs is not None else None
    return (
        stiffness[active][:, active].tocsr(),
        mass[active][:, active].tocsr(),
        reduced_dofs,
    )


def solve_generalized_eigenproblem(
    stiffness: sparse.spmatrix,
    mass: sparse.spmatrix,
    mode_count: int,
    *,
    expected_rigid_body_modes: int | None = None,
    dofs: Iterable[AbaqusDof] | None = None,
) -> GeneralizedEigenResult:
    """Solve ``K phi = lambda M phi`` and return the first elastic modes.

    Large systems use sparse shift-invert Lanczos.  A small negative shift lets
    SciPy accept Abaqus' positive-semidefinite mass matrix (for example, S4
    drilling rotations have zero mass) while keeping rigid-body eigenvalues
    closest to the target.  Numerical zero tolerance is derived from machine
    precision and the returned spectrum; it is not an application frequency
    threshold.
    """

    if isinstance(mode_count, bool) or int(mode_count) != mode_count or mode_count <= 0:
        raise ValueError("mode_count must be a positive integer.")
    mode_count = int(mode_count)
    if expected_rigid_body_modes is not None:
        if (
            isinstance(expected_rigid_body_modes, bool)
            or int(expected_rigid_body_modes) != expected_rigid_body_modes
            or expected_rigid_body_modes < 0
        ):
            raise ValueError("expected_rigid_body_modes must be a non-negative integer.")
        expected_rigid_body_modes = int(expected_rigid_body_modes)

    stiffness = sparse.csr_matrix(stiffness, dtype=float)
    mass = sparse.csr_matrix(mass, dtype=float)
    if stiffness.shape != mass.shape or stiffness.shape[0] != stiffness.shape[1]:
        raise ValueError("K and M must be square matrices with identical shape.")
    normalized_dofs = tuple(dofs) if dofs is not None else None
    if normalized_dofs is not None and len(normalized_dofs) != stiffness.shape[0]:
        raise ValueError("DOF ordering length does not match K and M.")
    require_sparse_symmetric(stiffness, name="K")
    require_sparse_symmetric(mass, name="M")
    stiffness, mass, normalized_dofs = _remove_fully_inactive_dofs(
        stiffness, mass, normalized_dofs
    )

    size = stiffness.shape[0]
    rigid_allowance = expected_rigid_body_modes if expected_rigid_body_modes is not None else 6
    requested = mode_count + rigid_allowance + 4
    if size <= 64 and np.all(mass.diagonal() > 0.0):
        try:
            eigenvalues, eigenvectors = dense_linalg.eigh(
                stiffness.toarray(), mass.toarray(), check_finite=False
            )
        except dense_linalg.LinAlgError as exc:
            raise MatrixModelError("The generalized eigenproblem could not be solved.") from exc
    else:
        if requested >= size:
            requested = size - 1
        if requested <= 0:
            raise MatrixModelError("The matrix is too small for a sparse eigen-solve.")
        positive_mass_diagonal = np.abs(mass.diagonal())
        positive_mass_diagonal = positive_mass_diagonal[positive_mass_diagonal > 0.0]
        mass_scale = (
            float(np.max(positive_mass_diagonal))
            if positive_mass_diagonal.size
            else 1.0
        )
        stiffness_scale = (
            float(np.max(np.abs(stiffness.data))) if stiffness.nnz else 1.0
        )
        spectral_scale = max(stiffness_scale / mass_scale, 1.0)
        shift = -math.sqrt(np.finfo(float).eps) * spectral_scale
        try:
            eigenvalues, eigenvectors = sparse_linalg.eigsh(
                stiffness,
                k=requested,
                M=mass,
                sigma=shift,
                which="LM",
                v0=np.ones(size, dtype=float),
            )
        except (RuntimeError, ValueError, sparse_linalg.ArpackError) as exc:
            raise MatrixModelError("The sparse generalized eigenproblem failed.") from exc

    order = np.argsort(eigenvalues)
    eigenvalues = np.asarray(eigenvalues[order], dtype=float)
    eigenvectors = np.asarray(eigenvectors[:, order], dtype=float)
    spectrum_scale = max(float(np.max(np.abs(eigenvalues))), 1.0)
    zero_tolerance = (
        100.0 * np.finfo(float).eps * spectrum_scale * max(stiffness.shape[0], 1)
    )
    eigenvalues[np.abs(eigenvalues) <= zero_tolerance] = 0.0

    if expected_rigid_body_modes is None:
        if np.any(eigenvalues < -zero_tolerance):
            most_negative = float(np.min(eigenvalues))
            raise MatrixModelError(
                f"K has a significant negative generalized eigenvalue ({most_negative:.6g})."
            )
        rigid_count = int(np.count_nonzero(eigenvalues == 0.0))
    else:
        rigid_count = expected_rigid_body_modes
        if eigenvalues.size < rigid_count:
            raise MatrixModelError(
                f"Expected {rigid_count} rigid-body modes, but only "
                f"{eigenvalues.size} eigenvalues were computed."
            )

    elastic_values = eigenvalues[rigid_count : rigid_count + mode_count]
    elastic_vectors = eigenvectors[:, rigid_count : rigid_count + mode_count]
    if elastic_values.size != mode_count:
        raise MatrixModelError(
            f"Only {elastic_values.size} elastic eigenpairs are available; "
            f"{mode_count} were requested."
        )
    if np.any(elastic_values < -zero_tolerance):
        most_negative = float(np.min(elastic_values))
        raise MatrixModelError(
            f"K has a significant negative elastic eigenvalue ({most_negative:.6g})."
        )
    if np.any(elastic_values <= 0.0):
        raise MatrixModelError("Rigid-body modes remain in the requested elastic spectrum.")
    frequencies = np.sqrt(elastic_values) / (2.0 * math.pi)
    return GeneralizedEigenResult(
        eigenvalues=elastic_values,
        frequencies_hz=frequencies,
        eigenvectors=elastic_vectors,
        dofs=normalized_dofs,
        rigid_body_eigenvalues=eigenvalues[:rigid_count],
    )


def render_stage_a_matrix_deck(
    template_text: str,
    parameters: StageAMatrixParameters,
    section_configuration: StageAShellSectionConfiguration,
    *,
    direct_frequency_modes: int = 0,
) -> str:
    """Fill the two explicit Stage-A markers in an Abaqus input template."""

    if template_text.count(STAGE_A_SECTION_MARKER) != 1:
        raise ValueError(f"Template must contain exactly one {STAGE_A_SECTION_MARKER!r}.")
    if template_text.count(STAGE_A_STEPS_MARKER) != 1:
        raise ValueError(f"Template must contain exactly one {STAGE_A_STEPS_MARKER!r}.")
    if (
        isinstance(direct_frequency_modes, bool)
        or int(direct_frequency_modes) != direct_frequency_modes
        or direct_frequency_modes < 0
    ):
        raise ValueError("direct_frequency_modes must be a non-negative integer.")

    section_text = generate_stage_a_shell_general_section(
        parameters.as_parameterization(), section_configuration
    ).rstrip("\n")
    steps = [
        "*STEP, NAME=GENERATE_MATRICES",
        "*MATRIX GENERATE, STIFFNESS, MASS",
        "*MATRIX OUTPUT, STIFFNESS, MASS, FORMAT=MATRIX INPUT",
        "*END STEP",
    ]
    if direct_frequency_modes:
        steps.extend(
            (
                "*STEP, NAME=DIRECT_FREQUENCY",
                "*FREQUENCY, EIGENSOLVER=LANCZOS",
                f"{int(direct_frequency_modes)},",
                "*END STEP",
            )
        )
    rendered = template_text.replace(STAGE_A_SECTION_MARKER, section_text)
    rendered = rendered.replace(STAGE_A_STEPS_MARKER, "\n".join(steps))
    return rendered.rstrip("\n") + "\n"


@dataclass(frozen=True)
class AbaqusMatrixJobResult:
    job_name: str
    stiffness_path: Path | None
    mass_path: Path | None
    odb_path: Path
    dat_path: Path
    launch_log_path: Path


def _abaqus_command(executable: str, arguments: Sequence[str]) -> list[str]:
    executable = executable.strip() or "abaqus"
    if os.name == "nt":
        command_line = subprocess.list2cmdline([executable, *arguments])
        return ["cmd.exe", "/d", "/s", "/c", command_line]
    return shlex.split(executable) + list(arguments)


def run_abaqus_matrix_job(
    input_path: Path,
    output_directory: Path,
    *,
    job_name: str | None = None,
    abaqus_command: str = "abaqus",
    datacheck: bool = False,
    timeout_seconds: int = 3600,
) -> AbaqusMatrixJobResult:
    """Run one real Abaqus matrix job and locate its exported K/M files."""

    input_path = Path(input_path).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"Abaqus input deck was not found: {input_path}")
    output_directory = Path(output_directory).resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    normalized_job_name = job_name or input_path.stem
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_\-]*", normalized_job_name):
        raise ValueError("job_name must start with a letter and contain only A-Z, 0-9, _ or -.")

    arguments = [
        f"job={normalized_job_name}",
        f"input={input_path}",
    ]
    if datacheck:
        arguments.append("datacheck")
    arguments.extend(("interactive", "ask_delete=OFF"))
    command = _abaqus_command(abaqus_command, arguments)
    try:
        completed = subprocess.run(
            command,
            cwd=str(output_directory),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise AbaqusMatrixGenerationError(
            "The Abaqus command could not be started."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AbaqusMatrixGenerationError(
            f"Abaqus matrix job exceeded {timeout_seconds} seconds."
        ) from exc

    launch_log_path = output_directory / f"{normalized_job_name}.launch.log"
    launch_log_path.write_text(
        "COMMAND\n"
        + " ".join(command)
        + "\n\nSTDOUT\n"
        + completed.stdout
        + "\n\nSTDERR\n"
        + completed.stderr,
        encoding="utf-8",
    )
    dat_path = output_directory / f"{normalized_job_name}.dat"
    odb_path = output_directory / f"{normalized_job_name}.odb"
    stiffness_path = output_directory / f"{normalized_job_name}_STIF1.mtx"
    mass_path = output_directory / f"{normalized_job_name}_MASS1.mtx"
    required_outputs = (dat_path, odb_path)
    if not datacheck:
        required_outputs += (stiffness_path, mass_path)
    if completed.returncode != 0 or not all(path.exists() for path in required_outputs):
        process_tail = (completed.stderr or completed.stdout or "No output was produced.")[-4000:]
        dat_tail = ""
        if dat_path.is_file():
            dat_tail = dat_path.read_text(encoding="utf-8", errors="replace")[-8000:]
        message = (
            f"Abaqus matrix job {normalized_job_name!r} failed.\n"
            f"PROCESS OUTPUT\n{process_tail}\n"
        )
        if dat_tail:
            message += f"ABAQUS DAT TAIL\n{dat_tail}\n"
        message += f"Full launch log: {launch_log_path}"
        raise AbaqusMatrixGenerationError(message)
    return AbaqusMatrixJobResult(
        job_name=normalized_job_name,
        stiffness_path=None if datacheck else stiffness_path,
        mass_path=None if datacheck else mass_path,
        odb_path=odb_path,
        dat_path=dat_path,
        launch_log_path=launch_log_path,
    )


def extract_abaqus_frequencies(
    odb_path: Path,
    output_path: Path,
    *,
    abaqus_command: str = "abaqus",
    timeout_seconds: int = 300,
) -> np.ndarray:
    """Extract the direct Abaqus eigenfrequencies from an ODB via Abaqus Python."""

    odb_path = Path(odb_path).resolve()
    output_path = Path(output_path).resolve()
    script_path = Path(__file__).resolve().parents[2] / "abaqus_scripts" / "extract_frequencies.py"
    if not odb_path.is_file():
        raise FileNotFoundError(f"Abaqus ODB was not found: {odb_path}")
    if not script_path.is_file():
        raise FileNotFoundError(f"Frequency extraction script was not found: {script_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = _abaqus_command(
        abaqus_command,
        ("python", str(script_path), "--odb", str(odb_path), "--output", str(output_path)),
    )
    try:
        completed = subprocess.run(
            command,
            cwd=str(output_path.parent),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise AbaqusMatrixGenerationError(
            "Abaqus frequency extraction could not be completed."
        ) from exc
    if completed.returncode != 0 or not output_path.is_file():
        tail = (completed.stderr or completed.stdout or "No output was produced.")[-4000:]
        raise AbaqusMatrixGenerationError(
            f"Abaqus frequency extraction failed.\n{tail}"
        )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    frequencies = np.asarray(
        [float(item["frequency_hz"]) for item in payload.get("modes", [])],
        dtype=float,
    )
    if frequencies.size == 0 or not np.isfinite(frequencies).all():
        raise AbaqusMatrixGenerationError(
            "Abaqus frequency extraction produced no finite modal frequencies."
        )
    return frequencies


@dataclass(frozen=True)
class DirectAbaqusEvaluation:
    matrices: AbaqusMatrixPair
    elastic_frequencies_hz: np.ndarray

    def __post_init__(self) -> None:
        frequencies = np.asarray(self.elastic_frequencies_hz, dtype=float)
        if frequencies.ndim != 1 or frequencies.size == 0:
            raise ValueError("Direct Abaqus frequencies must be a non-empty vector.")
        if not np.isfinite(frequencies).all() or np.any(frequencies <= 0.0):
            raise ValueError("Direct Abaqus elastic frequencies must be finite and positive.")
        object.__setattr__(self, "elastic_frequencies_hz", frequencies)


@dataclass(frozen=True)
class MatrixDecompositionProofResult:
    passed: bool
    sample_count: int
    worst_matrix_relative_error: float
    worst_frequency_relative_error: float
    offending_parameters: StageAMatrixParameters | None


def run_matrix_decomposition_proof_test(
    basis: StageAAffineBasis,
    samples: Sequence[StageAMatrixParameters],
    direct_evaluator: Callable[[StageAMatrixParameters], DirectAbaqusEvaluation],
    *,
    mode_count: int = 20,
    expected_rigid_body_modes: int | None = None,
    frequency_relative_tolerance: float = 1.0e-4,
) -> MatrixDecompositionProofResult:
    """Compare reconstructed K/SciPy modes with direct Abaqus at every sample."""

    if not samples:
        raise ValueError("The proof test requires at least one parameter sample.")
    frequency_relative_tolerance = _finite(
        frequency_relative_tolerance, "frequency_relative_tolerance"
    )
    if frequency_relative_tolerance <= 0.0:
        raise ValueError("frequency_relative_tolerance must be positive.")

    worst_matrix_error = -math.inf
    worst_frequency_error = -math.inf
    frequency_offender: StageAMatrixParameters | None = None
    for parameters in samples:
        direct = direct_evaluator(parameters)
        if direct.matrices.dofs != basis.dofs:
            raise MatrixModelError(
                "Proof-test Abaqus matrix has a different DOF ordering from the basis."
            )
        if not _sparse_allclose(
            direct.matrices.mass,
            basis.mass,
            rtol=1.0e-12,
            atol=1.0e-14,
        ):
            raise MatrixModelError(
                "Proof-test Abaqus mass matrix differs from the verified Stage-A M."
            )
        reconstructed = basis.reconstruct_stiffness(parameters)
        matrix_error = relative_sparse_frobenius_error(
            direct.matrices.stiffness, reconstructed
        )
        worst_matrix_error = max(worst_matrix_error, matrix_error)

        fast = solve_generalized_eigenproblem(
            reconstructed,
            basis.mass,
            mode_count,
            expected_rigid_body_modes=expected_rigid_body_modes,
            dofs=basis.dofs,
        )
        if direct.elastic_frequencies_hz.size < mode_count:
            raise MatrixModelError(
                f"Direct Abaqus returned only {direct.elastic_frequencies_hz.size} elastic "
                f"frequencies; {mode_count} are required."
            )
        direct_frequencies = direct.elastic_frequencies_hz[:mode_count]
        relative_errors = np.abs(fast.frequencies_hz - direct_frequencies) / direct_frequencies
        sample_frequency_error = float(np.max(relative_errors))
        if sample_frequency_error > worst_frequency_error:
            worst_frequency_error = sample_frequency_error
            frequency_offender = parameters

    passed = worst_frequency_error < frequency_relative_tolerance
    return MatrixDecompositionProofResult(
        passed=passed,
        sample_count=len(samples),
        worst_matrix_relative_error=worst_matrix_error,
        worst_frequency_relative_error=worst_frequency_error,
        offending_parameters=None if passed else frequency_offender,
    )
