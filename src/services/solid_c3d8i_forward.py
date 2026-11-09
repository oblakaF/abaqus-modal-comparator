"""ABM-SOLID-2: element-level offline kernel for 8-node orthotropic solid bricks.

Scope
-----
Element level only: a 3-D orthotropic constitutive matrix from engineering
constants, the stiffness of one 8-node brick with Wilson incompatible modes and
the Taylor-Beresford-Wilson centre-Jacobian correction (static condensation),
a plain fully integrated 8-node brick for comparison, and the consistent mass
matrix.  There is no INP reader, no global assembly, no full-model solve and no
material fitting in this module.

Formulation (published element theory)
--------------------------------------
* Constitutive law: linear orthotropic elasticity, compliance S built from
  E1, E2, E3, nu12, nu13, nu23, G12, G13, G23 with nu_ji = nu_ij E_j / E_i
  (strain e_j = -nu_ij s_i / E_i).  C = S^-1.  Admissible only when S is
  symmetric positive definite.
* Voigt order (11, 22, 33, 12, 13, 23) with engineering shear strains
  gamma_ij = 2 e_ij.  This is the order Abaqus documents for its stress and
  strain components.
* Geometry: trilinear isoparametric map, nodes in the Abaqus C3D8 order
  (1-4 on face zeta = -1 anticlockwise seen from +zeta, 5-8 above them).
  Nodal DOF order is [u1x, u1y, u1z, u2x, ..., u8z].
* Incompatible modes (Wilson, Taylor, Doherty, Ghaboussi 1973):
  u_inc = sum_k (1 - xi_k^2) a_k, k = 1..3, three vector amplitudes, nine
  internal DOFs.  Their derivatives use the centre Jacobian J0 and the weight
  det J0 / det J (Taylor, Beresford, Wilson 1976), so that the integral of
  B_inc over the element vanishes and the element passes the constant-strain
  patch test for any non-degenerate geometry.
* Static condensation: K = Kcc - Kci Kii^-1 Kic, solved with a Cholesky
  factorisation of the symmetric positive definite Kii; it is exact for the
  element because the internal amplitudes carry no load and no mass.
* Integration: 2 x 2 x 2 Gauss for stiffness, 3 x 3 x 3 Gauss for the
  consistent mass (exact for any trilinear brick).
* Mass: rho * integral of N^T N over the element with the compatible shape
  functions only.

Not verified against Abaqus (ABAQUS_EQUIVALENCE = NOT_VERIFIED)
---------------------------------------------------------------
Abaqus describes its C3D8I element as an incompatible-mode element but its
exact internal mode set, the enhanced-strain variant, how the centre Jacobian
is used, its mass integration and any element-level stabilisation have not
been compared with this implementation.  Abaqus documents selectively reduced
integration for its fully integrated C3D8, so ``HEX8_FULL_2X2X2`` here is not
Abaqus C3D8 either.  Nothing in this module may be described as
Abaqus-equivalent until element- or model-level evidence exists.

Units: none are converted.  Inputs must be consistent; the owner's models use
mm, t, s, so moduli are in MPa (N/mm^2), density in t/mm^3, stiffness in N/mm,
mass in t and frequencies in Hz.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import numpy as np
from scipy import linalg as dense_linalg

FORMULATION_HEX8_FULL = "HEX8_FULL_2X2X2"
FORMULATION_C3D8I_REFERENCE = "C3D8I_WILSON_TAYLOR_9_INCOMPATIBLE_MODES"
FORMULATIONS = (FORMULATION_HEX8_FULL, FORMULATION_C3D8I_REFERENCE)
ABAQUS_EQUIVALENCE = "NOT_VERIFIED"
INTERNAL_MODE_COUNT = {FORMULATION_HEX8_FULL: 0, FORMULATION_C3D8I_REFERENCE: 9}
VOIGT_ORDER = ("11", "22", "33", "12", "13", "23")
ENGINEERING_SHEAR_STRAIN = True
ABAQUS_ENGINEERING_CONSTANT_ORDER = (
    "E1", "E2", "E3", "nu12", "nu13", "nu23", "G12", "G13", "G23")

# Abaqus C3D8 / C3D8I node order in natural coordinates (xi, eta, zeta).
NODE_NATURAL_COORDINATES = np.array([
    [-1.0, -1.0, -1.0], [1.0, -1.0, -1.0], [1.0, 1.0, -1.0], [-1.0, 1.0, -1.0],
    [-1.0, -1.0, 1.0], [1.0, -1.0, 1.0], [1.0, 1.0, 1.0], [-1.0, 1.0, 1.0],
])
DOF_ORDER = tuple((node, axis) for node in range(1, 9) for axis in ("x", "y", "z"))


class SolidElementError(ValueError):
    """Invalid element geometry, formulation or condensation."""


class InadmissibleMaterialError(SolidElementError):
    """Engineering constants that do not give a positive definite elasticity."""


# --------------------------------------------------------------------------- material


@dataclass(frozen=True)
class OrthotropicEngineeringConstants:
    """Engineering constants on the material axes 1, 2, 3 (consistent units)."""

    e1: float
    e2: float
    e3: float
    nu12: float
    nu13: float
    nu23: float
    g12: float
    g13: float
    g23: float

    def __post_init__(self) -> None:
        values = (self.e1, self.e2, self.e3, self.nu12, self.nu13, self.nu23,
                  self.g12, self.g13, self.g23)
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                   and math.isfinite(v) for v in values):
            raise InadmissibleMaterialError("All nine engineering constants must be finite numbers.")
        for name in ("e1", "e2", "e3", "g12", "g13", "g23"):
            if getattr(self, name) <= 0.0:
                raise InadmissibleMaterialError(f"{name.upper()} must be positive.")
        compliance = self.compliance_matrix()
        eigenvalues = np.linalg.eigvalsh(compliance)
        if eigenvalues[0] <= 1.0e-12 * eigenvalues[-1]:
            raise InadmissibleMaterialError(
                "The engineering constants do not give a positive definite compliance "
                f"(stability determinant {self.stability_determinant():.6g}).")

    @classmethod
    def from_abaqus(cls, values: Sequence[float]) -> "OrthotropicEngineeringConstants":
        """Build from the nine values of ``*Elastic, type=ENGINEERING CONSTANTS``."""
        values = tuple(float(v) for v in values)
        if len(values) != 9:
            raise InadmissibleMaterialError("ENGINEERING CONSTANTS need exactly nine values.")
        return cls(*values)

    @classmethod
    def isotropic(cls, e: float, nu: float) -> "OrthotropicEngineeringConstants":
        g = e / (2.0 * (1.0 + nu))
        return cls(e, e, e, nu, nu, nu, g, g, g)

    def stability_determinant(self) -> float:
        """1 - nu12 nu21 - nu23 nu32 - nu13 nu31 - 2 nu21 nu32 nu13."""
        nu21 = self.nu12 * self.e2 / self.e1
        nu31 = self.nu13 * self.e3 / self.e1
        nu32 = self.nu23 * self.e3 / self.e2
        return (1.0 - self.nu12 * nu21 - self.nu23 * nu32 - self.nu13 * nu31
                - 2.0 * nu21 * nu32 * self.nu13)

    def compliance_matrix(self) -> np.ndarray:
        s = np.zeros((6, 6))
        s[0, 0], s[1, 1], s[2, 2] = 1.0 / self.e1, 1.0 / self.e2, 1.0 / self.e3
        s[0, 1] = s[1, 0] = -self.nu12 / self.e1
        s[0, 2] = s[2, 0] = -self.nu13 / self.e1
        s[1, 2] = s[2, 1] = -self.nu23 / self.e2
        s[3, 3], s[4, 4], s[5, 5] = 1.0 / self.g12, 1.0 / self.g13, 1.0 / self.g23
        return s

    def stiffness_matrix(self) -> np.ndarray:
        c = np.linalg.inv(self.compliance_matrix())
        return 0.5 * (c + c.T)


def material_axes(rotation: Sequence[Sequence[float]]) -> np.ndarray:
    """Validate local material axes: rows are axes 1, 2, 3 in global coordinates."""
    r = np.asarray(rotation, dtype=float)
    if r.shape != (3, 3) or not np.all(np.isfinite(r)):
        raise SolidElementError("Material axes must be a finite 3 x 3 matrix.")
    if not np.allclose(r @ r.T, np.eye(3), atol=1.0e-10):
        raise SolidElementError("Material axes must be orthonormal.")
    if np.linalg.det(r) <= 0.0:
        raise SolidElementError("Material axes must form a right-handed system.")
    return r


def material_axes_from_points(a: Sequence[float], b: Sequence[float]) -> np.ndarray:
    """Axes from an Abaqus rectangular ``*Orientation`` (point a on axis 1, b in the 1-2 plane)."""
    e1 = np.asarray(a, dtype=float)
    norm = np.linalg.norm(e1)
    if norm == 0.0:
        raise SolidElementError("Orientation point a must not be the origin.")
    e1 = e1 / norm
    e3 = np.cross(e1, np.asarray(b, dtype=float))
    if np.linalg.norm(e3) == 0.0:
        raise SolidElementError("Orientation points a and b must not be collinear.")
    e3 = e3 / np.linalg.norm(e3)
    return material_axes(np.vstack([e1, np.cross(e3, e1), e3]))


def strain_transformation(rotation: Sequence[Sequence[float]]) -> np.ndarray:
    """T with eps_local = T eps_global (Voigt order, engineering shear)."""
    r = material_axes(rotation)
    pairs = ((0, 0), (1, 1), (2, 2), (0, 1), (0, 2), (1, 2))
    # Tensor rule e'_ij = R_ik R_jm e_km with e_km = gamma_km / 2 for k != m and
    # gamma'_ij = 2 e'_ij for i != j.
    t = np.zeros((6, 6))
    for row, (i, j) in enumerate(pairs):
        row_factor = 1.0 if i == j else 2.0
        for col, (k, m) in enumerate(pairs):
            if k == m:
                t[row, col] = row_factor * r[i, k] * r[j, k]
            else:
                t[row, col] = row_factor * 0.5 * (r[i, k] * r[j, m] + r[i, m] * r[j, k])
    return t


def global_elasticity(material: OrthotropicEngineeringConstants,
                      rotation: Sequence[Sequence[float]] | None = None) -> np.ndarray:
    """6 x 6 elasticity in global axes: C_g = T^T C_local T."""
    c_local = material.stiffness_matrix()
    if rotation is None:
        return c_local
    t = strain_transformation(rotation)
    c = t.T @ c_local @ t
    return 0.5 * (c + c.T)


# --------------------------------------------------------------------------- element


def _gauss(order: int) -> tuple[np.ndarray, np.ndarray]:
    points, weights = np.polynomial.legendre.leggauss(order)
    grid = np.array([(a, b, c) for a in points for b in points for c in points])
    wts = np.array([wa * wb * wc for wa in weights for wb in weights for wc in weights])
    return grid, wts


def shape_functions(xi: Sequence[float]) -> np.ndarray:
    x = np.asarray(xi, dtype=float)
    return np.prod(1.0 + NODE_NATURAL_COORDINATES * x, axis=1) / 8.0


def shape_derivatives(xi: Sequence[float]) -> np.ndarray:
    """dN/dxi as a 3 x 8 array."""
    x = np.asarray(xi, dtype=float)
    n = NODE_NATURAL_COORDINATES
    f = 1.0 + n * x
    d = np.empty((3, 8))
    d[0] = n[:, 0] * f[:, 1] * f[:, 2] / 8.0
    d[1] = n[:, 1] * f[:, 0] * f[:, 2] / 8.0
    d[2] = n[:, 2] * f[:, 0] * f[:, 1] / 8.0
    return d


def _coordinates(coordinates: Sequence[Sequence[float]]) -> np.ndarray:
    x = np.asarray(coordinates, dtype=float)
    if x.shape != (8, 3) or not np.all(np.isfinite(x)):
        raise SolidElementError("An 8-node brick needs an 8 x 3 array of finite coordinates.")
    return x


def _jacobian(x: np.ndarray, xi: Sequence[float]) -> tuple[np.ndarray, float, np.ndarray]:
    dn = shape_derivatives(xi)
    jac = dn @ x  # jac[i, j] = d x_j / d xi_i
    det = float(np.linalg.det(jac))
    return jac, det, dn


def _require_positive_jacobian(x: np.ndarray, points: np.ndarray) -> None:
    scale = float(np.max(np.ptp(x, axis=0))) ** 3
    # Centre and the integration points actually used.  Vertex Jacobians are not
    # required: standard distorted benchmark bricks may be slightly negative there.
    for xi in np.vstack([np.zeros((1, 3)), points]):
        det = _jacobian(x, xi)[1]
        if not det > 1.0e-12 * scale:
            raise SolidElementError(
                "Non-positive Jacobian: the element is degenerate, inverted or its nodes "
                "are not in the Abaqus C3D8 order.")


def _strain_matrix(dndx: np.ndarray) -> np.ndarray:
    """6 x (3 n) B matrix for derivative rows dndx (3 x n)."""
    count = dndx.shape[1]
    b = np.zeros((6, 3 * count))
    for a in range(count):
        dx, dy, dz = dndx[:, a]
        c = 3 * a
        b[0, c] = dx
        b[1, c + 1] = dy
        b[2, c + 2] = dz
        b[3, c], b[3, c + 1] = dy, dx
        b[4, c], b[4, c + 2] = dz, dx
        b[5, c + 1], b[5, c + 2] = dz, dy
    return b


def _elasticity(elasticity: np.ndarray) -> np.ndarray:
    c = np.asarray(elasticity, dtype=float)
    if c.shape != (6, 6) or not np.all(np.isfinite(c)):
        raise InadmissibleMaterialError("Elasticity must be a finite 6 x 6 matrix.")
    if not np.allclose(c, c.T, rtol=1.0e-10, atol=1.0e-12 * np.max(np.abs(c))):
        raise InadmissibleMaterialError("Elasticity must be symmetric.")
    eigenvalues = np.linalg.eigvalsh(c)
    if eigenvalues[0] <= 1.0e-12 * eigenvalues[-1]:
        raise InadmissibleMaterialError("Elasticity must be positive definite.")
    return c


@dataclass(frozen=True)
class ElementStiffness:
    """Condensed 24 x 24 element stiffness and its condensation data."""

    formulation: str
    stiffness: np.ndarray
    internal_mode_count: int
    internal_stiffness: np.ndarray | None
    internal_coupling: np.ndarray | None
    internal_condition_number: float | None
    abaqus_equivalence: str = ABAQUS_EQUIVALENCE
    dof_order: tuple = DOF_ORDER

    def internal_amplitudes(self, displacements: Sequence[float]) -> np.ndarray:
        """Recover the nine incompatible-mode amplitudes a = -Kii^-1 Kic u."""
        if self.internal_stiffness is None:
            return np.zeros(0)
        u = np.asarray(displacements, dtype=float).reshape(24)
        return -dense_linalg.solve(self.internal_stiffness, self.internal_coupling @ u,
                                   assume_a="pos")


def hex8_full_stiffness(coordinates, elasticity) -> ElementStiffness:
    """Plain fully integrated (2 x 2 x 2) trilinear brick; not Abaqus C3D8."""
    x = _coordinates(coordinates)
    c = _elasticity(elasticity)
    points, weights = _gauss(2)
    _require_positive_jacobian(x, points)
    k = np.zeros((24, 24))
    for xi, w in zip(points, weights):
        jac, det, dn = _jacobian(x, xi)
        b = _strain_matrix(np.linalg.solve(jac, dn))
        k += b.T @ c @ b * det * w
    return ElementStiffness(FORMULATION_HEX8_FULL, 0.5 * (k + k.T), 0, None, None, None)


def c3d8i_reference_stiffness(coordinates, elasticity, *,
                              centre_jacobian_correction: bool = True) -> ElementStiffness:
    """Wilson incompatible-mode brick, condensed to the 24 nodal DOFs.

    ``centre_jacobian_correction=False`` gives the original 1973 Wilson element,
    which fails the patch test on distorted geometry; it exists only so that the
    tests can show why the correction is required.
    """
    x = _coordinates(coordinates)
    c = _elasticity(elasticity)
    points, weights = _gauss(2)
    _require_positive_jacobian(x, points)
    jac0, det0, _ = _jacobian(x, (0.0, 0.0, 0.0))
    kcc = np.zeros((24, 24))
    kci = np.zeros((24, 9))
    kii = np.zeros((9, 9))
    for xi, w in zip(points, weights):
        jac, det, dn = _jacobian(x, xi)
        bc = _strain_matrix(np.linalg.solve(jac, dn))
        dp = np.diag(-2.0 * np.asarray(xi))  # dP_k / dxi_m for P_k = 1 - xi_k^2
        if centre_jacobian_correction:
            bi = _strain_matrix(np.linalg.solve(jac0, dp)) * (det0 / det)
        else:
            bi = _strain_matrix(np.linalg.solve(jac, dp))
        dv = det * w
        kcc += bc.T @ c @ bc * dv
        kci += bc.T @ c @ bi * dv
        kii += bi.T @ c @ bi * dv
    kii = 0.5 * (kii + kii.T)
    try:
        factor = dense_linalg.cho_factor(kii, check_finite=False)
    except dense_linalg.LinAlgError as exc:
        raise SolidElementError("The incompatible-mode block is not positive definite.") from exc
    scale = 1.0 / np.sqrt(np.diag(kii))
    scaled = kii * scale[:, None] * scale[None, :]
    condition = float(np.linalg.cond(scaled))
    if not math.isfinite(condition) or condition > 1.0e12:
        raise SolidElementError(
            f"The incompatible-mode block is ill-conditioned (scaled condition {condition:.3g}).")
    k = kcc - kci @ dense_linalg.cho_solve(factor, kci.T, check_finite=False)
    return ElementStiffness(FORMULATION_C3D8I_REFERENCE, 0.5 * (k + k.T), 9, kii, kci.T, condition)


def consistent_mass(coordinates, density: float) -> np.ndarray:
    """rho * integral N^T N dV with 3 x 3 x 3 Gauss (exact for trilinear geometry)."""
    x = _coordinates(coordinates)
    if isinstance(density, bool) or not math.isfinite(float(density)) or density <= 0.0:
        raise InadmissibleMaterialError("Density must be a positive finite number.")
    points, weights = _gauss(3)
    _require_positive_jacobian(x, points)
    scalar = np.zeros((8, 8))
    for xi, w in zip(points, weights):
        n = shape_functions(xi)
        scalar += np.outer(n, n) * _jacobian(x, xi)[1] * w
    scalar *= float(density)
    m = np.kron(scalar, np.eye(3))
    return 0.5 * (m + m.T)


def element_volume(coordinates) -> float:
    x = _coordinates(coordinates)
    points, weights = _gauss(2)
    return float(sum(_jacobian(x, xi)[1] * w for xi, w in zip(points, weights)))


def rigid_body_modes(coordinates) -> np.ndarray:
    """24 x 6 basis: three translations and three infinitesimal rotations."""
    x = _coordinates(coordinates)
    centre = x.mean(axis=0)
    modes = np.zeros((24, 6))
    for a, p in enumerate(x - centre):
        rows = slice(3 * a, 3 * a + 3)
        modes[rows, 0:3] = np.eye(3)
        modes[rows, 3] = (0.0, -p[2], p[1])
        modes[rows, 4] = (p[2], 0.0, -p[0])
        modes[rows, 5] = (-p[1], p[0], 0.0)
    return modes


def element_stiffness(formulation: str, coordinates, material: OrthotropicEngineeringConstants,
                      rotation=None) -> ElementStiffness:
    """Explicit formulation choice; an unknown name is refused, never substituted."""
    elasticity = global_elasticity(material, rotation)
    if formulation == FORMULATION_C3D8I_REFERENCE:
        return c3d8i_reference_stiffness(coordinates, elasticity)
    if formulation == FORMULATION_HEX8_FULL:
        return hex8_full_stiffness(coordinates, elasticity)
    raise SolidElementError(f"Unknown solid formulation {formulation!r}; expected one of {FORMULATIONS}.")


def formulation_for_abaqus_element(element_type: str) -> tuple[str, str]:
    """Map an Abaqus element label to the formulation here and its equivalence status."""
    label = str(element_type).strip().upper()
    if label == "C3D8I":
        return FORMULATION_C3D8I_REFERENCE, ABAQUS_EQUIVALENCE
    raise SolidElementError(
        f"No offline formulation for Abaqus element {label!r}. Only C3D8I has a reference "
        "formulation here (Abaqus equivalence NOT_VERIFIED); C3D8, C3D8R and others are "
        "not substituted.")


def element_free_vibration(formulation: str, coordinates, material, density: float,
                           rotation=None, mode_count: int = 18):
    """Free-free eigenpairs of one element through the project generalized eigensolver."""
    from .matrix_model_service import solve_generalized_eigenproblem
    from scipy import sparse

    k = element_stiffness(formulation, coordinates, material, rotation).stiffness
    m = consistent_mass(coordinates, density)
    return solve_generalized_eigenproblem(sparse.csr_matrix(k), sparse.csr_matrix(m),
                                          mode_count, expected_rigid_body_modes=6)


__all__ = [
    "ABAQUS_ENGINEERING_CONSTANT_ORDER", "ABAQUS_EQUIVALENCE", "DOF_ORDER", "ElementStiffness",
    "FORMULATIONS", "FORMULATION_C3D8I_REFERENCE", "FORMULATION_HEX8_FULL",
    "INTERNAL_MODE_COUNT", "InadmissibleMaterialError", "NODE_NATURAL_COORDINATES",
    "OrthotropicEngineeringConstants", "SolidElementError", "VOIGT_ORDER",
    "c3d8i_reference_stiffness", "consistent_mass", "element_free_vibration",
    "element_stiffness", "element_volume", "formulation_for_abaqus_element",
    "global_elasticity", "hex8_full_stiffness", "material_axes", "material_axes_from_points",
    "rigid_body_modes", "shape_derivatives", "shape_functions", "strain_transformation",
]
