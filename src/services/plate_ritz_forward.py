"""Standalone free-free Kirchhoff-Ritz forward model of a rectangular orthotropic plate.

The transverse deflection is expanded in a hierarchical tensor-product Legendre basis, with
``xi = 2x/a`` and ``eta = 2y/b``. Free edges are the natural conditions of the variational problem:
no term restricts the basis at the boundary. NumPy and SciPy compute frequencies and shapes. No
Abaqus installation, ODB or exported matrix is involved, and this module imports no process tools.

Scope: Kirchhoff-Love bending, constant D, negligible B, D16 and D26, small linear motion. Results
are forward predictions, never a material identification.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
from typing import Any, Mapping, Optional, Sequence, Tuple

import numpy as np
from numpy.polynomial import legendre as np_legendre
from scipy import linalg as dense_linalg

from domain.plate_material_problem import (
    CoordinateObservationSet,
    MixedCoordinateReference,
    ObservationEvaluation,
    PlateBendingParameters,
    PlateForwardRefusal,
    PlateGeometry,
    RefusalCode,
    ResourceLimits,
    identity_hash,
)


RITZ_BACKEND_VERSION = "kirchhoff-ritz-legendre/1"
RITZ_DOF_ORDERING = "(p,q) lexicographic: r = p*(degree_y+1) + q"
RITZ_QUADRATURE = "gauss-legendre n=degree+1 per axis, exact for polynomial degree 2*degree+1"
RITZ_STIFFNESS_NAMES = ("D11", "D22", "D12", "D66")
MIXED_COORDINATE_NAMES = ("ln(D11/D11ref)", "ln(D22/D22ref)", "ln(D66/D66ref)", "u=D12/D22")
ENERGY_FRACTION_NAMES = ("J11", "J22", "J12", "J66")

# Dense float64 n-by-n arrays held at once: K11, K22, K12, K66, M, K, and eigensolver work space.
_DENSE_ARRAY_COUNT = 10
_MIN_DEGREE = 2


def _refuse(code: RefusalCode, reason: str) -> PlateForwardRefusal:
    return PlateForwardRefusal(code, reason)


@dataclass(frozen=True)
class RitzNumericalConfig:
    """A fixed basis order and numerical policy; both are part of the model and run identity.

    ``degeneracy_relative_gap`` is a numerical policy: neighbouring frequencies closer than this
    relative gap are not differentiated as separate branches. It is not a scientific threshold.
    """

    degree_x: int
    degree_y: int
    mode_count: int
    degeneracy_relative_gap: float = 1.0e-7
    check_relative_tolerance: float = 1.0e-9

    def __post_init__(self) -> None:
        for name in ("degree_x", "degree_y", "mode_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
                raise _refuse(RefusalCode.INVALID_INPUT, f"{name} must be an integer.")
            object.__setattr__(self, name, int(value))
        if self.degree_x < _MIN_DEGREE or self.degree_y < _MIN_DEGREE:
            raise _refuse(RefusalCode.INVALID_INPUT, f"The basis degree must be at least {_MIN_DEGREE} per axis.")
        if self.mode_count <= 0:
            raise _refuse(RefusalCode.INVALID_INPUT, "mode_count must be positive.")
        for name in ("degeneracy_relative_gap", "check_relative_tolerance"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise _refuse(RefusalCode.INVALID_INPUT, f"{name} must be positive and finite.")
            object.__setattr__(self, name, value)

    @property
    def dof_count(self) -> int:
        return (self.degree_x + 1) * (self.degree_y + 1)

    def identity(self) -> Mapping[str, Any]:
        return {
            "degree_x": self.degree_x,
            "degree_y": self.degree_y,
            "mode_count": self.mode_count,
            "degeneracy_relative_gap": self.degeneracy_relative_gap,
            "check_relative_tolerance": self.check_relative_tolerance,
            "quadrature": RITZ_QUADRATURE,
            "dof_ordering": RITZ_DOF_ORDERING,
        }


def preflight_ritz(config: RitzNumericalConfig, limits: ResourceLimits) -> Mapping[str, int]:
    """Check the size before any matrix is allocated."""

    dofs = config.dof_count
    estimated = _DENSE_ARRAY_COUNT * dofs * dofs * 8
    if dofs > limits.max_dofs:
        raise _refuse(RefusalCode.RESOURCE_LIMIT, f"{dofs} Ritz coefficients exceed the cap of {limits.max_dofs}.")
    if estimated > limits.max_allocation_bytes:
        raise _refuse(
            RefusalCode.RESOURCE_LIMIT,
            f"Estimated allocation of {estimated} bytes exceeds the cap of {limits.max_allocation_bytes}.",
        )
    if config.mode_count > dofs - 3:
        raise _refuse(
            RefusalCode.INVALID_INPUT,
            f"{config.mode_count} elastic modes requested, but this basis holds only {dofs - 3}.",
        )
    return {"dofs": dofs, "estimated_allocation_bytes": estimated}


def _legendre_values(degree: int, points: np.ndarray, derivative: int) -> np.ndarray:
    """Return d^k P_p / d xi^k at ``points``; rows are points, columns are p = 0..degree."""

    values = np.zeros((points.size, degree + 1), dtype=float)
    for p in range(derivative, degree + 1):
        coefficients = np.zeros(p + 1, dtype=float)
        coefficients[p] = 1.0
        if derivative:
            coefficients = np_legendre.legder(coefficients, m=derivative)
        values[:, p] = np_legendre.legval(points, coefficients)
    return values


@dataclass(frozen=True)
class _AxisIntegrals:
    e00: np.ndarray
    e11: np.ndarray
    e22: np.ndarray
    e02: np.ndarray


@lru_cache(maxsize=16)
def _axis_integrals(degree: int) -> _AxisIntegrals:
    nodes, weights = np_legendre.leggauss(degree + 1)
    p0 = _legendre_values(degree, nodes, 0)
    p1 = _legendre_values(degree, nodes, 1)
    p2 = _legendre_values(degree, nodes, 2)
    integrals = _AxisIntegrals(
        (p0.T * weights) @ p0,
        (p1.T * weights) @ p1,
        (p2.T * weights) @ p2,
        (p0.T * weights) @ p2,
    )
    for array in (integrals.e00, integrals.e11, integrals.e22, integrals.e02):
        array.setflags(write=False)
    return integrals


@dataclass(frozen=True)
class RitzGeometryMatrices:
    """Geometry matrices, assembled once; ``M_area[r,s]`` is the integral of B_r*B_s over the area."""

    a_m: float
    b_m: float
    degree_x: int
    degree_y: int
    K11: np.ndarray
    K22: np.ndarray
    K12: np.ndarray
    K66: np.ndarray
    M_area: np.ndarray
    labels: Tuple[Tuple[int, int], ...]

    def by_name(self) -> Mapping[str, np.ndarray]:
        return {"D11": self.K11, "D22": self.K22, "D12": self.K12, "D66": self.K66}


@lru_cache(maxsize=8)
def _assemble_cached(a_m: float, b_m: float, degree_x: int, degree_y: int) -> RitzGeometryMatrices:
    x_axis = _axis_integrals(degree_x)
    y_axis = _axis_integrals(degree_y)
    jacobian = a_m * b_m / 4.0
    dx2 = (2.0 / a_m) ** 2
    dy2 = (2.0 / b_m) ** 2
    k11 = dx2 * dx2 * jacobian * np.kron(x_axis.e22, y_axis.e00)
    k22 = dy2 * dy2 * jacobian * np.kron(x_axis.e00, y_axis.e22)
    # e02[p,s] = integral P_p * P_s''. The transpose term supplies B_r,xx*B_s,yy in the same order.
    k12 = dx2 * dy2 * jacobian * (np.kron(x_axis.e02.T, y_axis.e02) + np.kron(x_axis.e02, y_axis.e02.T))
    k66 = 4.0 * dx2 * dy2 * jacobian * np.kron(x_axis.e11, y_axis.e11)
    m_area = jacobian * np.kron(x_axis.e00, y_axis.e00)
    labels = tuple((p, q) for p in range(degree_x + 1) for q in range(degree_y + 1))
    for array in (k11, k22, k12, k66, m_area):
        array.setflags(write=False)
    return RitzGeometryMatrices(a_m, b_m, degree_x, degree_y, k11, k22, k12, k66, m_area, labels)


def assemble_ritz_matrices(geometry: PlateGeometry, config: RitzNumericalConfig, limits: ResourceLimits) -> RitzGeometryMatrices:
    """Return the read-only matrices; the cache key holds the exact a, b and basis degrees."""

    preflight_ritz(config, limits)
    return _assemble_cached(geometry.a_m, geometry.b_m, config.degree_x, config.degree_y)


def ritz_model_identity(geometry: PlateGeometry, config: RitzNumericalConfig) -> str:
    return identity_hash(
        {
            "backend_version": RITZ_BACKEND_VERSION,
            "geometry": geometry.identity(),
            "degree_x": config.degree_x,
            "degree_y": config.degree_y,
            "quadrature": RITZ_QUADRATURE,
            "dof_ordering": RITZ_DOF_ORDERING,
        }
    )


def _check_matrix(matrix: np.ndarray, name: str, tolerance: float) -> float:
    if not np.isfinite(matrix).all():
        raise _refuse(RefusalCode.NON_FINITE_MATRIX, f"{name} contains non-finite values.")
    scale = float(np.max(np.abs(matrix)))
    error = float(np.max(np.abs(matrix - matrix.T)))
    if error > tolerance * max(scale, np.finfo(float).tiny):
        raise _refuse(RefusalCode.ASYMMETRIC_MATRIX, f"{name} is not symmetric (max |A-A.T| = {error:.6g}).")
    return error / max(scale, np.finfo(float).tiny)


def rigid_coefficients(matrices: RitzGeometryMatrices) -> np.ndarray:
    """Return the exact coefficients of 1, x and y: x = (a/2)*P1(xi) and y = (b/2)*P1(eta)."""

    index = {label: position for position, label in enumerate(matrices.labels)}
    rigid = np.zeros((len(matrices.labels), 3), dtype=float)
    rigid[index[(0, 0)], 0] = 1.0
    rigid[index[(1, 0)], 1] = matrices.a_m / 2.0
    rigid[index[(0, 1)], 2] = matrices.b_m / 2.0
    return rigid


def basis_at_points(
    matrices: RitzGeometryMatrices,
    x_m: np.ndarray,
    y_m: np.ndarray,
    derivative_x: int = 0,
    derivative_y: int = 0,
) -> np.ndarray:
    """Evaluate d^i/dx^i d^j/dy^j of every basis function; rows are points."""

    xi = 2.0 * np.asarray(x_m, dtype=float) / matrices.a_m
    eta = 2.0 * np.asarray(y_m, dtype=float) / matrices.b_m
    x_values = _legendre_values(matrices.degree_x, xi, derivative_x) * (2.0 / matrices.a_m) ** derivative_x
    y_values = _legendre_values(matrices.degree_y, eta, derivative_y) * (2.0 / matrices.b_m) ** derivative_y
    return np.einsum("ip,iq->ipq", x_values, y_values).reshape(xi.size, -1)


@dataclass(frozen=True)
class RigidSubspaceDiagnostics:
    stiffness_residual: float
    mass_coupling: float
    field_error: float
    rigid_shapes: Tuple[str, str, str] = ("1", "x", "y")
    verified: bool = True


def _separate_rigid_subspace(
    matrices: RitzGeometryMatrices,
    stiffness: np.ndarray,
    mass: np.ndarray,
    tolerance: float,
) -> tuple[np.ndarray, np.ndarray, RigidSubspaceDiagnostics]:
    """Split the coefficient space into span{1,x,y} and its verified M-orthogonal complement."""

    rigid = rigid_coefficients(matrices)
    complement = np.flatnonzero(np.all(rigid == 0.0, axis=1))
    stiffness_scale = float(np.max(np.abs(stiffness)))
    k_residual = float(np.max(np.abs(stiffness @ rigid))) / max(stiffness_scale, np.finfo(float).tiny)
    mass_scale = float(np.max(np.abs(mass)))
    coupling = float(np.max(np.abs(rigid.T @ mass[:, complement]))) / mass_scale
    half_a, half_b = matrices.a_m / 2.0, matrices.b_m / 2.0
    x_check = np.array([-half_a, half_a, 0.3 * half_a, -0.7 * half_a])
    y_check = np.array([half_b, -half_b, -0.4 * half_b, 0.9 * half_b])
    values = basis_at_points(matrices, x_check, y_check) @ rigid
    expected = np.column_stack((np.ones(x_check.size), x_check, y_check))
    field_error = float(np.max(np.abs(values - expected)))
    field_scale = max(half_a, half_b, 1.0)
    if k_residual > tolerance or coupling > tolerance or field_error > tolerance * field_scale:
        raise _refuse(
            RefusalCode.RIGID_SUBSPACE_NOT_VERIFIED,
            "span{1,x,y} failed verification "
            f"(|K R|={k_residual:.3g}, |R^T M Z|={coupling:.3g}, field error={field_error:.3g}).",
        )
    return rigid, complement, RigidSubspaceDiagnostics(k_residual, coupling, field_error)


def _find_clusters(frequencies: np.ndarray, relative_gap: float) -> Tuple[Tuple[int, ...], ...]:
    clusters: list[Tuple[int, ...]] = []
    current = [0]
    for index in range(1, frequencies.size):
        if frequencies[index] - frequencies[index - 1] < relative_gap * frequencies[index - 1]:
            current.append(index)
        else:
            if len(current) > 1:
                clusters.append(tuple(current))
            current = [index]
    if len(current) > 1:
        clusters.append(tuple(current))
    return tuple(clusters)


@dataclass(frozen=True)
class RitzForwardSolution:
    """Elastic eigenpairs in ascending order. Coefficients are mass-orthonormal by columns.

    ``clusters`` lists 0-based mode indexes inside the returned window. A cluster that the window
    boundary cuts is listed, and ``window_cuts_cluster`` is true.
    """

    geometry: PlateGeometry
    parameters: PlateBendingParameters
    config: RitzNumericalConfig
    matrices: RitzGeometryMatrices
    stiffness: np.ndarray
    mass: np.ndarray
    eigenvalues: np.ndarray
    frequencies_hz: np.ndarray
    coefficients: np.ndarray
    rigid_shape_coefficients: np.ndarray
    clusters: Tuple[Tuple[int, ...], ...]
    window_cuts_cluster: bool
    next_elastic_eigenvalue: Optional[float]
    rigid_diagnostics: RigidSubspaceDiagnostics
    max_residual: float
    max_orthonormality_error: float
    symmetry_error: float

    def diagnostics(self) -> Mapping[str, Any]:
        return {
            "elastic_modes_returned": int(self.eigenvalues.size),
            "dof_count": self.config.dof_count,
            "rigid_subspace": "span{1,x,y} separated by mass-orthogonal projection",
            "rigid_stiffness_residual": self.rigid_diagnostics.stiffness_residual,
            "rigid_mass_coupling": self.rigid_diagnostics.mass_coupling,
            "rigid_field_error": self.rigid_diagnostics.field_error,
            "max_eigen_residual": self.max_residual,
            "max_orthonormality_error": self.max_orthonormality_error,
            "stiffness_symmetry_error": self.symmetry_error,
            "clusters": [list(item) for item in self.clusters],
            "window_cuts_cluster": self.window_cuts_cluster,
            "next_elastic_eigenvalue": self.next_elastic_eigenvalue,
            "order_convergence": "NOT_EVALUATED_BY_THIS_SOLVE; see ritz_order_convergence",
        }


def _solve_elastic_block(stiffness: np.ndarray, mass: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return ascending eigenpairs of the elastic block, mass-orthonormal by columns.

    The solve is M v = mu K v with K scaled to a unit diagonal. Its largest mu = 1/lambda is computed
    with error relative to itself, so the low modes used here stay accurate when the stiffness
    entries span many decades. K must be positive definite on this block: nothing is altered to
    continue when it is not.
    """

    diagonal = np.diag(stiffness)
    if np.any(diagonal <= 0.0):
        raise _refuse(
            RefusalCode.NON_POSITIVE_ELASTIC_EIGENVALUE,
            "K has a non-positive diagonal entry on the elastic complement; it is not altered to continue.",
        )
    scale = 1.0 / np.sqrt(diagonal)
    scaled_k = stiffness * scale[:, np.newaxis] * scale[np.newaxis, :]
    scaled_m = mass * scale[:, np.newaxis] * scale[np.newaxis, :]
    try:
        dense_linalg.cholesky(scaled_k, lower=True, check_finite=False)
    except dense_linalg.LinAlgError as exc:
        raise _refuse(
            RefusalCode.NON_POSITIVE_ELASTIC_EIGENVALUE,
            "K is not positive definite on the elastic complement; it is not altered to continue.",
        ) from exc
    try:
        inverse_values, vectors = dense_linalg.eigh(scaled_m, scaled_k, check_finite=False)
    except dense_linalg.LinAlgError as exc:
        raise _refuse(RefusalCode.EIGENSOLVE_FAILED, "The elastic eigenproblem could not be solved.") from exc
    if not np.isfinite(inverse_values).all() or float(np.min(inverse_values)) <= 0.0:
        raise _refuse(RefusalCode.EIGENSOLVE_FAILED, "The elastic spectrum is not finite and positive.")
    values = 1.0 / inverse_values[::-1]
    # eigh gives v^T K v = I and v^T M v = mu; rescale to mass-orthonormal coefficients.
    coefficients = (vectors[:, ::-1] * scale[:, np.newaxis]) * np.sqrt(values)
    return values, coefficients


def solve_ritz(
    geometry: PlateGeometry,
    parameters: PlateBendingParameters,
    config: RitzNumericalConfig,
    limits: Optional[ResourceLimits] = None,
) -> RitzForwardSolution:
    """Solve K q = lambda M q on the elastic complement and verify the result."""

    limits = limits if limits is not None else ResourceLimits()
    matrices = assemble_ritz_matrices(geometry, config, limits)
    tolerance = config.check_relative_tolerance
    stiffness = (
        parameters.D11 * matrices.K11
        + parameters.D22 * matrices.K22
        + parameters.D12 * matrices.K12
        + parameters.D66 * matrices.K66
    )
    mass = geometry.surface_mass_kg_m2 * matrices.M_area
    symmetry_error = _check_matrix(stiffness, "K", tolerance)
    _check_matrix(mass, "M", tolerance)
    stiffness = 0.5 * (stiffness + stiffness.T)
    mass = 0.5 * (mass + mass.T)
    try:
        dense_linalg.cholesky(mass, lower=True, check_finite=False)
    except dense_linalg.LinAlgError as exc:
        raise _refuse(RefusalCode.MASS_NOT_POSITIVE_DEFINITE, "M is not positive definite.") from exc

    rigid, complement, rigid_diagnostics = _separate_rigid_subspace(matrices, stiffness, mass, tolerance)
    values, reduced = _solve_elastic_block(
        stiffness[np.ix_(complement, complement)],
        mass[np.ix_(complement, complement)],
    )

    all_frequencies = np.sqrt(values) / (2.0 * math.pi)
    all_clusters = _find_clusters(all_frequencies, config.degeneracy_relative_gap)
    count = config.mode_count
    window_clusters = []
    cuts = False
    for cluster in all_clusters:
        inside = tuple(index for index in cluster if index < count)
        if len(inside) != len(cluster) and inside:
            cuts = True
        if inside:
            window_clusters.append(inside)

    coefficients = np.zeros((config.dof_count, count), dtype=float)
    coefficients[complement, :] = reduced[:, :count]
    for column in range(count):
        # A fixed sign makes repeated solves identical; the physical sign of a mode is arbitrary.
        pivot = int(np.argmax(np.abs(coefficients[:, column])))
        if coefficients[pivot, column] < 0.0:
            coefficients[:, column] = -coefficients[:, column]

    selected = values[:count]
    residual_vectors = stiffness @ coefficients - (mass @ coefficients) * selected
    denominators = selected * np.linalg.norm(mass @ coefficients, axis=0)
    max_residual = float(np.max(np.linalg.norm(residual_vectors, axis=0) / denominators))
    orthonormality = coefficients.T @ mass @ coefficients - np.eye(count)
    max_orthonormality = float(np.max(np.abs(orthonormality)))
    return RitzForwardSolution(
        geometry=geometry,
        parameters=parameters,
        config=config,
        matrices=matrices,
        stiffness=stiffness,
        mass=mass,
        eigenvalues=selected,
        frequencies_hz=all_frequencies[:count],
        coefficients=coefficients,
        rigid_shape_coefficients=rigid,
        clusters=tuple(window_clusters),
        window_cuts_cluster=cuts,
        next_elastic_eigenvalue=float(values[count]) if values.size > count else None,
        rigid_diagnostics=rigid_diagnostics,
        max_residual=max_residual,
        max_orthonormality_error=max_orthonormality,
        symmetry_error=symmetry_error,
    )


def evaluate_ritz_field(
    solution: RitzForwardSolution,
    x_m: Sequence[float],
    y_m: Sequence[float],
    derivative_x: int = 0,
    derivative_y: int = 0,
) -> np.ndarray:
    """Evaluate a shape or spatial derivative on the plate; rows are points, columns are modes."""

    x_values, y_values = _inside_plate(solution.geometry, x_m, y_m)
    basis = basis_at_points(solution.matrices, x_values, y_values, derivative_x, derivative_y)
    return basis @ solution.coefficients


def _inside_plate(geometry: PlateGeometry, x_m: Sequence[float], y_m: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
    x_values = np.asarray(x_m, dtype=float).ravel()
    y_values = np.asarray(y_m, dtype=float).ravel()
    if x_values.size != y_values.size or not x_values.size:
        raise _refuse(RefusalCode.INVALID_INPUT, "x and y must be matching non-empty lists.")
    if not (np.isfinite(x_values).all() and np.isfinite(y_values).all()):
        raise _refuse(RefusalCode.INVALID_INPUT, "Coordinates must be finite.")
    if np.any(np.abs(x_values) > geometry.a_m / 2.0) or np.any(np.abs(y_values) > geometry.b_m / 2.0):
        raise _refuse(RefusalCode.OBSERVATION_OUTSIDE_MODEL, "A coordinate lies outside the plate rectangle.")
    return x_values, y_values


@lru_cache(maxsize=8)
def _observation_basis_cached(
    a_m: float,
    b_m: float,
    degree_x: int,
    degree_y: int,
    x_key: Tuple[float, ...],
    y_key: Tuple[float, ...],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    matrices = _assemble_cached(a_m, b_m, degree_x, degree_y)
    x_values = np.asarray(x_key, dtype=float)
    y_values = np.asarray(y_key, dtype=float)
    arrays = (
        basis_at_points(matrices, x_values, y_values),
        basis_at_points(matrices, x_values, y_values, 1, 0),
        basis_at_points(matrices, x_values, y_values, 0, 1),
    )
    for array in arrays:
        array.setflags(write=False)
    return arrays


def evaluate_ritz_observations(
    solution: RitzForwardSolution,
    observations: CoordinateObservationSet,
    limits: Optional[ResourceLimits] = None,
) -> ObservationEvaluation:
    """Project shapes on declared measured directions with Kirchhoff surface kinematics.

    At height z the displacement is (-z*w_x, -z*w_y, w), so the measured value along the unit
    direction d is ``d_z*w - z*(d_x*w_x + d_y*w_y)``. A direction with an in-plane part and no
    declared z is unsupported: it is refused rather than treated as U3.
    """

    limits = limits if limits is not None else ResourceLimits()
    if not isinstance(observations, CoordinateObservationSet):
        raise _refuse(RefusalCode.UNSUPPORTED_OBSERVATION_KIND, "The Ritz backend evaluates coordinate observations only.")
    points = observations.points
    estimated = 3 * len(points) * solution.config.dof_count * 8
    if estimated > limits.max_allocation_bytes:
        raise _refuse(RefusalCode.RESOURCE_LIMIT, f"Observation evaluation needs about {estimated} bytes.")
    for point in points:
        if (point.direction[0] != 0.0 or point.direction[1] != 0.0) and point.surface_offset_m is None:
            raise _refuse(
                RefusalCode.UNSUPPORTED_KINEMATICS,
                f"{point.observation_id}: an off-normal direction needs a declared surface offset.",
            )
    x_values, y_values = _inside_plate(
        solution.geometry, [point.x_m for point in points], [point.y_m for point in points]
    )
    basis_w, basis_wx, basis_wy = _observation_basis_cached(
        solution.geometry.a_m,
        solution.geometry.b_m,
        solution.config.degree_x,
        solution.config.degree_y,
        tuple(x_values.tolist()),
        tuple(y_values.tolist()),
    )
    w = basis_w @ solution.coefficients
    w_x = basis_wx @ solution.coefficients
    w_y = basis_wy @ solution.coefficients
    direction = np.asarray([point.direction for point in points], dtype=float)
    offset = np.asarray([0.0 if point.surface_offset_m is None else point.surface_offset_m for point in points])
    values = (
        direction[:, 2, np.newaxis] * w
        - offset[:, np.newaxis] * (direction[:, 0, np.newaxis] * w_x + direction[:, 1, np.newaxis] * w_y)
    )
    return ObservationEvaluation(
        observation_ids=tuple(point.observation_id for point in points),
        values=values,
        component_meanings=tuple(point.component_meaning for point in points),
        registration_id=observations.registration_id,
        w=w,
        w_x=w_x,
        w_y=w_y,
    )


def log_frequency_derivative(
    vector: np.ndarray,
    eigenvalue: float,
    stiffness_derivative: np.ndarray,
    mass: np.ndarray,
    mass_derivative: Optional[np.ndarray] = None,
) -> float:
    """Return d ln(f)/dt = q^H (K_t - lambda*M_t) q / (2*lambda*q^H*M*q) for one simple branch."""

    numerator = np.vdot(vector, stiffness_derivative @ vector)
    if mass_derivative is not None:
        numerator = numerator - eigenvalue * np.vdot(vector, mass_derivative @ vector)
    denominator = 2.0 * eigenvalue * np.vdot(vector, mass @ vector)
    return float(np.real(numerator / denominator))


@dataclass(frozen=True)
class ClusterSensitivity:
    """Basis-invariant derivative of ln(sqrt(mean lambda)) over one unresolved mode cluster."""

    mode_indexes: Tuple[int, ...]
    d_ln_rms_frequency_d_D: np.ndarray


@dataclass(frozen=True)
class RitzSensitivities:
    """Derivatives for the returned modes. Rows of clustered modes are NaN and listed as refused.

    ``d_ln_f_d_D`` columns follow ``RITZ_STIFFNESS_NAMES`` (per N*m). ``mixed`` holds S1..S4 in
    ``MIXED_COORDINATE_NAMES`` order. ``energy_fractions`` holds J in ``ENERGY_FRACTION_NAMES`` order.
    """

    d_ln_f_d_D: np.ndarray
    mixed: np.ndarray
    energy_fractions: np.ndarray
    refused_mode_indexes: Tuple[int, ...]
    clusters: Tuple[ClusterSensitivity, ...]
    max_energy_fraction_sum_error: Optional[float]

    def simple_mode_row(self, mode_index: int) -> np.ndarray:
        if mode_index in self.refused_mode_indexes:
            raise _refuse(
                RefusalCode.DEGENERATE_BRANCH,
                f"Mode index {mode_index} is in an unresolved cluster; use the cluster derivative.",
            )
        return self.mixed[mode_index]


def ritz_sensitivities(solution: RitzForwardSolution) -> RitzSensitivities:
    """Compute analytic sensitivities. M does not depend on D, and K is homogeneous of degree one in D."""

    matrices = solution.matrices
    derivative_matrices = (matrices.K11, matrices.K22, matrices.K12, matrices.K66)
    count = solution.eigenvalues.size
    refused = sorted({index for cluster in solution.clusters for index in cluster})
    if solution.window_cuts_cluster:
        refused = sorted(set(refused) | {count - 1})
    derivatives = np.full((count, 4), np.nan)
    for mode in range(count):
        if mode in refused:
            continue
        for column, matrix in enumerate(derivative_matrices):
            derivatives[mode, column] = log_frequency_derivative(
                solution.coefficients[:, mode], float(solution.eigenvalues[mode]), matrix, solution.mass
            )
    parameters = solution.parameters
    u = parameters.u
    mixed = np.column_stack(
        (
            parameters.D11 * derivatives[:, 0],
            parameters.D22 * (derivatives[:, 1] + u * derivatives[:, 2]),
            parameters.D66 * derivatives[:, 3],
            parameters.D22 * derivatives[:, 2],
        )
    )
    fractions = np.column_stack(
        (
            2.0 * parameters.D11 * derivatives[:, 0],
            2.0 * parameters.D22 * derivatives[:, 1],
            2.0 * parameters.D12 * derivatives[:, 2],
            2.0 * parameters.D66 * derivatives[:, 3],
        )
    )
    simple = [mode for mode in range(count) if mode not in refused]
    sum_error = float(np.max(np.abs(fractions[simple].sum(axis=1) - 1.0))) if simple else None

    cluster_results = []
    for cluster in solution.clusters:
        if solution.window_cuts_cluster and cluster[-1] == count - 1:
            continue
        subspace = solution.coefficients[:, list(cluster)]
        trace_lambda = float(np.sum(solution.eigenvalues[list(cluster)]))
        row = np.array(
            [float(np.trace(subspace.T @ matrix @ subspace)) / (2.0 * trace_lambda) for matrix in derivative_matrices]
        )
        cluster_results.append(ClusterSensitivity(tuple(cluster), row))
    return RitzSensitivities(derivatives, mixed, fractions, tuple(refused), tuple(cluster_results), sum_error)


def _track_branches(reference: RitzForwardSolution, trial: RitzForwardSolution, minimum_mac: float) -> np.ndarray:
    """Match modes of two solves on the same basis by the M-weighted MAC."""

    cross = reference.coefficients.T @ reference.mass @ trial.coefficients
    mac = cross * cross
    matched = np.argmax(mac, axis=1)
    if len(set(matched.tolist())) != matched.size or np.any(mac[np.arange(matched.size), matched] < minimum_mac):
        raise _refuse(RefusalCode.BRANCH_NOT_TRACKED, "A mode could not be tracked to a unique branch.")
    return matched


def _embed(source: RitzForwardSolution, target: RitzForwardSolution) -> np.ndarray:
    """Express source coefficients in the target's labels; the hierarchical basis is nested."""

    if source.matrices.labels == target.matrices.labels:
        return source.coefficients
    index = {label: position for position, label in enumerate(target.matrices.labels)}
    embedded = np.zeros((len(target.matrices.labels), source.coefficients.shape[1]), dtype=float)
    for position, label in enumerate(source.matrices.labels):
        embedded[index[label], :] = source.coefficients[position, :]
    return embedded


@dataclass(frozen=True)
class CentralDifferenceCheck:
    """Mixed-coordinate derivatives from tracked central differences at each step size."""

    step_sizes: Tuple[float, ...]
    central_differences: np.ndarray
    analytic: np.ndarray
    worst_relative_error_by_step: Tuple[float, ...]


def ritz_central_difference_check(
    solution: RitzForwardSolution,
    *,
    step_sizes: Sequence[float] = (1.0e-3, 2.0e-3),
    tracking_minimum_mac: float = 0.9,
    limits: Optional[ResourceLimits] = None,
) -> CentralDifferenceCheck:
    """Compare S1..S4 with central differences on simple tracked branches only."""

    analytic = ritz_sensitivities(solution)
    if analytic.refused_mode_indexes:
        raise _refuse(RefusalCode.DEGENERATE_BRANCH, "Central differences need simple tracked branches only.")
    reference = MixedCoordinateReference(solution.parameters.D11, solution.parameters.D22, solution.parameters.D66)
    centre = np.asarray(solution.parameters.mixed_coordinates(reference))
    steps = tuple(float(step) for step in step_sizes)
    results = np.empty((len(steps),) + analytic.mixed.shape, dtype=float)
    errors = []
    for step_index, step in enumerate(steps):
        for coordinate in range(4):
            shift = np.zeros(4)
            shift[coordinate] = step
            sides = []
            for sign in (1.0, -1.0):
                trial_parameters = PlateBendingParameters.from_mixed_coordinates(centre + sign * shift, reference)
                trial = solve_ritz(solution.geometry, trial_parameters, solution.config, limits)
                matched = _track_branches(solution, trial, tracking_minimum_mac)
                sides.append(np.log(trial.frequencies_hz[matched]))
            results[step_index, :, coordinate] = (sides[0] - sides[1]) / (2.0 * step)
        denominator = np.maximum(np.abs(analytic.mixed), 1.0e-8)
        errors.append(float(np.max(np.abs(results[step_index] - analytic.mixed) / denominator)))
    return CentralDifferenceCheck(steps, results, analytic.mixed, tuple(errors))


@dataclass(frozen=True)
class OrderConvergenceStep:
    """Change between two successive orders, on modes tracked by the M-weighted MAC.

    ``subspace_cosine_squared`` holds, per coarse mode, its MAC with the matched fine mode. For a
    cluster it holds the smallest squared principal-angle cosine of the cluster subspace.
    """

    coarse_degrees: Tuple[int, int]
    fine_degrees: Tuple[int, int]
    relative_frequency_change: np.ndarray
    subspace_cosine_squared: np.ndarray
    max_mixed_sensitivity_change: float
    index_permutation: bool
    frequencies_not_increased: bool


@dataclass(frozen=True)
class OrderConvergenceReport:
    """Observed changes only. No convergence rate is assumed, and no verdict is issued here."""

    schedule: Tuple[Tuple[int, int], ...]
    frequencies_by_order: Tuple[np.ndarray, ...]
    steps: Tuple[OrderConvergenceStep, ...]


def ritz_order_convergence(
    geometry: PlateGeometry,
    parameters: PlateBendingParameters,
    schedule: Sequence[Tuple[int, int]],
    mode_count: int,
    *,
    guard_modes: int = 4,
    tracking_minimum_mac: float = 0.5,
    limits: Optional[ResourceLimits] = None,
) -> OrderConvergenceReport:
    """Run a fixed, predeclared order schedule, and refuse it as a whole if any order exceeds a cap."""

    limits = limits if limits is not None else ResourceLimits()
    schedule = tuple((int(item[0]), int(item[1])) for item in schedule)
    if len(schedule) < 2 or len(set(schedule)) != len(schedule):
        raise _refuse(RefusalCode.INVALID_INPUT, "A convergence schedule needs at least two distinct orders.")
    for coarse, fine in zip(schedule, schedule[1:]):
        if fine[0] < coarse[0] or fine[1] < coarse[1]:
            raise _refuse(RefusalCode.INVALID_INPUT, "A convergence schedule must refine a nested basis.")
    configs = []
    for degree_x, degree_y in schedule:
        config = RitzNumericalConfig(degree_x, degree_y, mode_count + guard_modes)
        preflight_ritz(config, limits)
        configs.append(config)

    solutions = [solve_ritz(geometry, parameters, config, limits) for config in configs]
    sensitivities = [ritz_sensitivities(solution) for solution in solutions]
    steps = []
    for index in range(len(solutions) - 1):
        coarse = solutions[index]
        fine = solutions[index + 1]
        embedded = _embed(coarse, fine)[:, :mode_count]
        cross = embedded.T @ fine.mass @ fine.coefficients
        mac = cross * cross
        matched = np.argmax(mac, axis=1)
        if np.any(mac[np.arange(mode_count), matched] < tracking_minimum_mac):
            raise _refuse(RefusalCode.BRANCH_NOT_TRACKED, "A mode has no clear match at the next order.")
        cosine = mac[np.arange(mode_count), matched].copy()
        for cluster in coarse.clusters:
            members = [mode for mode in cluster if mode < mode_count]
            if not members:
                continue
            fine_members = sorted({int(matched[mode]) for mode in members})
            singular = np.linalg.svd(cross[np.ix_(members, fine_members)], compute_uv=False)
            cosine[members] = float(np.min(singular)) ** 2 if len(fine_members) == len(members) else 0.0
        change = coarse.frequencies_hz[:mode_count] - fine.frequencies_hz[matched]
        relative = change / fine.frequencies_hz[matched]
        difference = np.abs(sensitivities[index].mixed[:mode_count] - sensitivities[index + 1].mixed[matched])
        finite = difference[np.isfinite(difference)]
        steps.append(
            OrderConvergenceStep(
                schedule[index],
                schedule[index + 1],
                relative,
                cosine,
                float(np.max(finite)) if finite.size else math.nan,
                bool(np.any(matched != np.arange(mode_count))),
                # Nested Rayleigh-Ritz spaces cannot raise the k-th eigenvalue (min-max theorem).
                bool(np.all(fine.frequencies_hz[:mode_count] <= coarse.frequencies_hz[:mode_count] * (1.0 + 1.0e-10))),
            )
        )
    return OrderConvergenceReport(
        schedule,
        tuple(solution.frequencies_hz[:mode_count].copy() for solution in solutions),
        tuple(steps),
    )
