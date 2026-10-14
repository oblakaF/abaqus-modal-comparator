"""Synthetic forward model: free vibration of an orthotropic rectangular block — research track NINE-EC (Phase F).

An independent, solver-free test model with nine controllable constants (no Abaqus). It is the classical
Rayleigh–Ritz formulation of resonant ultrasound spectroscopy (Visscher et al., 1991): a free-free rectangular
parallelepiped [−a, a] × [−b, b] × [−c, c] (mm) with material axes 1, 2, 3 along x, y, z, density ρ (t/mm³), moduli in
MPa (N/mm²). Displacements are expanded in products of normalised Legendre polynomials of total degree ≤ N, so the
mass matrix is diagonal and every integral is exact (Gauss–Legendre quadrature). The generalised eigenproblem
K a = ω² M a gives six rigid-body modes and the elastic spectrum.

Why this model: its frequencies depend on all nine constants through the full 3D stiffness tensor, with coupled,
geometry-dependent sensitivities; a thick block can make all nine observable while a thin plate makes the transverse
constants weakly observable. It does not return any desired answer: tests generate "experiments" from one constant
set and must recover them, or refuse, through the general engine.

Outputs per state: elastic frequencies (Hz), mode shapes sampled on the top face (u1, u2, u3 at a grid; the
FE-to-FE tracking input), an exact symmetry class per mode (parities of the shape about the three mid-planes; a
modal-family key for this geometry) and analytic eigenvalue derivatives d ln f / dx for the research coordinates
(finite-difference consistency checks only).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
import hashlib
from typing import Sequence

import numpy as np
from numpy.polynomial import legendre
from scipy.linalg import eigh

from domain.forward_model_manifest import EngineeringConstants
from domain.orthotropic_elasticity import COORDINATES, CoordinateKind, NAMES, compliance_matrix, require_admissible

from .branch_tracker import FEModalState

RIGID_MODES = 6
_VOIGT = {(0, 0): 0, (1, 1): 1, (2, 2): 2, (0, 1): 3, (1, 0): 3, (0, 2): 4, (2, 0): 4, (1, 2): 5, (2, 1): 5}


def _tensor(voigt: np.ndarray) -> np.ndarray:
    """C_ijkl from a 6×6 Voigt matrix (Abaqus order, engineering shear strain)."""
    c = np.zeros((3, 3, 3, 3))
    for i in range(3):
        for j in range(3):
            for k in range(3):
                for m in range(3):
                    c[i, j, k, m] = voigt[_VOIGT[(i, j)], _VOIGT[(k, m)]]
    return c


def _compliance_derivative(c: EngineeringConstants, name: str) -> np.ndarray:
    """dS/dp for one Engineering Constant (S as in domain.orthotropic_elasticity.compliance_matrix)."""
    d = np.zeros((6, 6))
    if name in ("E1", "E2", "E3"):
        i = int(name[1]) - 1
        d[i, i] = -1.0 / getattr(c, name) ** 2
        if name == "E1":
            d[0, 1] = d[1, 0] = c.nu12 / c.E1 ** 2
            d[0, 2] = d[2, 0] = c.nu13 / c.E1 ** 2
        if name == "E2":
            d[1, 2] = d[2, 1] = c.nu23 / c.E2 ** 2
    elif name == "nu12":
        d[0, 1] = d[1, 0] = -1.0 / c.E1
    elif name == "nu13":
        d[0, 2] = d[2, 0] = -1.0 / c.E1
    elif name == "nu23":
        d[1, 2] = d[2, 1] = -1.0 / c.E2
    else:
        index = {"G12": 3, "G13": 4, "G23": 5}[name]
        d[index, index] = -1.0 / getattr(c, name) ** 2
    return d


@dataclass(frozen=True)
class BlockModes:
    constants: EngineeringConstants
    frequencies_hz: tuple[float, ...]  # elastic modes, ascending
    symmetry_classes: tuple[str, ...]  # e.g. "uvw:EOO/..." parity signature per mode
    surface_shapes: np.ndarray  # modes × (3·grid points): u1, u2, u3 on the top face
    eigenvalues: np.ndarray  # ω² of the elastic modes
    vectors: np.ndarray  # Ritz coefficients (columns), mass-normalised

    def state(self, state_id: str, geometry_id: str) -> FEModalState:
        """The FE-to-FE tracking input (mode numbers 1.. in ascending frequency): full-field Ritz vectors, so the MAC
        is mass-weighted over the whole body (M ∝ I in this basis), like an FE-to-FE MAC over all nodes."""
        return FEModalState(state_id, geometry_id, geometry_id + ":ritz", tuple(range(1, len(self.frequencies_hz) + 1)),
                            self.frequencies_hz, self.vectors.T)


class OrthotropicBlock:
    """A free-free orthotropic block (half-dimensions in mm, density in t/mm³, Legendre total degree N)."""

    def __init__(self, half_dimensions_mm: Sequence[float], density_t_mm3: float, order: int = 8,
                 surface_grid: int = 7) -> None:
        self.half = np.asarray(half_dimensions_mm, dtype=float)
        if self.half.shape != (3,) or np.any(self.half <= 0):
            raise ValueError("three positive half-dimensions are required.")
        if not density_t_mm3 > 0:
            raise ValueError("density must be positive.")
        if order < 2:
            raise ValueError("the polynomial order must be at least 2 (rigid-body modes need degree 1).")
        self.density = float(density_t_mm3)
        self.order = int(order)
        self.grid = int(surface_grid)
        self.exponents = np.array([(i, j, k) for i in range(order + 1) for j in range(order + 1 - i)
                                   for k in range(order + 1 - i - j)], dtype=int)

    @property
    def geometry_id(self) -> str:
        text = f"block|{self.half.tolist()}|{self.density}|N{self.order}|grid{self.grid}"
        return hashlib.sha256(text.encode()).hexdigest()

    @cached_property
    def _one_dimensional(self):
        """Normalised Legendre P̂_p on [−1, 1]: A0 = ∫P̂pP̂q (= I), D = ∫P̂p'P̂q, A2 = ∫P̂p'P̂q' (exact quadrature)."""
        n = self.order + 1
        nodes, weights = legendre.leggauss(n + 1)
        values = np.zeros((n, nodes.size))
        derivatives = np.zeros((n, nodes.size))
        for p in range(n):
            coefficients = np.zeros(p + 1)
            coefficients[p] = np.sqrt((2 * p + 1) / 2.0)
            values[p] = legendre.legval(nodes, coefficients)
            derivatives[p] = legendre.legval(nodes, legendre.legder(coefficients))
        a0 = (values * weights) @ values.T
        d = (derivatives * weights) @ values.T
        a2 = (derivatives * weights) @ derivatives.T
        return a0, d, a2

    @cached_property
    def _gradient_integrals(self) -> np.ndarray:
        """G[j, l] = ∫ ∂_jφ_λ ∂_lφ_λ' dV over the block (nb × nb each), exact."""
        a0, d, a2 = self._one_dimensional
        e = self.exponents
        volume_factor = float(np.prod(self.half))
        g = np.zeros((3, 3, len(e), len(e)))
        for j in range(3):
            for l in range(3):
                product = np.ones((len(e), len(e)))
                for t in range(3):
                    p, q = e[:, t][:, None], e[:, t][None, :]
                    if t == j and t == l:
                        factor = a2[p, q]
                    elif t == j:
                        factor = d[p, q]
                    elif t == l:
                        factor = d[q, p]
                    else:
                        factor = a0[p, q]
                    product = product * factor
                g[j, l] = volume_factor * product / (self.half[j] * self.half[l])
        return g

    def _stiffness(self, voigt: np.ndarray) -> np.ndarray:
        c = _tensor(voigt)
        g = self._gradient_integrals
        nb = len(self.exponents)
        k = np.zeros((3 * nb, 3 * nb))
        for i in range(3):
            for m in range(3):
                block = np.einsum("jl,jlab->ab", c[i, :, m, :], g)
                k[i * nb:(i + 1) * nb, m * nb:(m + 1) * nb] = block
        return 0.5 * (k + k.T)

    @cached_property
    def _mass_scale(self) -> float:
        return self.density * float(np.prod(self.half))  # M = ρ·abc·I in the normalised Legendre basis

    @cached_property
    def _surface_basis(self):
        """Basis values on the top face (z = +c) at a grid × grid set of points, and their (x, y) coordinates."""
        axis = np.linspace(-1.0, 1.0, self.grid)
        u, v = np.meshgrid(axis, axis)
        u, v = u.ravel(), v.ravel()
        values = []
        for (p, q, r) in self.exponents:
            values.append(self._legendre(p, u) * self._legendre(q, v) * self._legendre(r, np.ones_like(u)))
        return np.array(values), np.column_stack([u * self.half[0], v * self.half[1]])

    @staticmethod
    def _legendre(p: int, x: np.ndarray) -> np.ndarray:
        coefficients = np.zeros(p + 1)
        coefficients[p] = np.sqrt((2 * p + 1) / 2.0)
        return legendre.legval(x, coefficients)

    def _symmetry_class(self, vector: np.ndarray) -> str:
        """Characters of the mode under the three mid-plane reflections (exact for an axis-aligned orthotropic block).

        Under x → −x a symmetric field keeps u2, u3 and flips u1; so the x-parity of component u_i equals the
        character χ_x for i ≠ 1 and its opposite for i = 1. The label is the character triple, the same whichever
        component dominates (a modal-family key of the synthetic geometry).
        """
        nb = len(self.exponents)
        weights = [vector[component * nb:(component + 1) * nb] ** 2 for component in range(3)]
        dominant = int(np.argmax([w.sum() for w in weights]))
        parity = self.exponents[int(np.argmax(weights[dominant]))] % 2  # 1 = odd
        characters = [int(parity[t]) ^ int(t == dominant) for t in range(3)]
        return "D2h:" + "".join("A" if bit else "S" for bit in characters)  # S symmetric / A antisymmetric

    def modes(self, constants: EngineeringConstants, count: int) -> BlockModes:
        """The ``count`` lowest elastic modes of an admissible constant set."""
        require_admissible(constants)
        stiffness = self._stiffness(np.linalg.inv(compliance_matrix(constants)))
        values, vectors = eigh(stiffness, subset_by_index=[0, RIGID_MODES + count - 1])
        elastic = values[RIGID_MODES:] / self._mass_scale
        if np.any(elastic <= 0.0):
            raise ValueError("non-positive elastic eigenvalue (basis or material problem).")
        vectors = vectors[:, RIGID_MODES:] / np.sqrt(self._mass_scale)  # mass-normalised: aᵀ M a = 1
        basis, _ = self._surface_basis
        nb = len(self.exponents)
        shapes = np.vstack([np.concatenate([vectors[i * nb:(i + 1) * nb, n] @ basis for i in range(3)])
                            for n in range(count)])
        classes = tuple(self._symmetry_class(vectors[:, n]) for n in range(count))
        return BlockModes(constants, tuple(float(np.sqrt(v) / (2 * np.pi)) for v in elastic), classes, shapes,
                          elastic, vectors)

    def family_keys(self, solution: BlockModes) -> tuple[str, ...]:
        """Modal-family key per mode: symmetry class and its order within the class (never the global mode number)."""
        seen: dict[str, int] = {}
        keys = []
        for cls in solution.symmetry_classes:
            seen[cls] = seen.get(cls, 0) + 1
            keys.append(f"{cls}#{seen[cls]}")
        return tuple(keys)

    def analytic_log_sensitivities(self, solution: BlockModes, names: Sequence[str] = NAMES) -> np.ndarray:
        """d ln f_n / d x_j by eigenvalue perturbation (x = ln p for moduli, ν for Poisson ratios); simple modes only."""
        c = solution.constants
        stiffness = np.linalg.inv(compliance_matrix(c))
        out = np.zeros((len(solution.frequencies_hz), len(names)))
        for j, name in enumerate(names):
            d_voigt = -stiffness @ _compliance_derivative(c, name) @ stiffness  # dC/dp
            if COORDINATES[name] is CoordinateKind.LOG:
                d_voigt = d_voigt * getattr(c, name)  # dC/d ln p
            d_k = self._stiffness(d_voigt)
            for n in range(len(solution.frequencies_hz)):
                a = solution.vectors[:, n]
                d_lambda = float(a @ d_k @ a)  # mass-normalised vectors: dλ = aᵀ dK a
                out[n, j] = 0.5 * d_lambda / float(solution.eigenvalues[n])
        return out


class BlockForwardModel:
    """The synthetic block as a nine-constant forward model (``evaluate`` → FEModalState). SYNTHETIC, no Abaqus."""

    def __init__(self, block: OrthotropicBlock, mode_count: int) -> None:
        self.block, self.mode_count = block, int(mode_count)
        self.evaluations = 0

    def solve(self, constants: EngineeringConstants) -> BlockModes:
        return self.block.modes(constants, self.mode_count)

    def evaluate(self, constants: EngineeringConstants) -> FEModalState:
        self.evaluations += 1
        digest = hashlib.sha256(repr(constants.as_tuple()).encode()).hexdigest()[:12]
        return self.solve(constants).state(f"block_{digest}", self.block.geometry_id)

    def identity(self) -> dict:
        return {"solver": "synthetic orthotropic block (Rayleigh-Ritz, Legendre)", "geometry": self.block.geometry_id,
                "mode_count": self.mode_count, "kind": "SYNTHETIC"}
