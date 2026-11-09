"""ABM-SOLID-3: sparse assembly and free-free modal solve for an imported C3D8I model.

* Assembly uses the ABM-SOLID-2 element kernel unchanged.  Elements whose
  relative nodal coordinates are bit-identical share one element matrix (an
  exact cache, no rounding); everything is scattered into SciPy CSR matrices
  in bounded chunks.  No dense global matrix is ever formed.
* The eigenproblem K phi = lambda M phi is solved by ARPACK shift-invert
  (``scipy.sparse.linalg.eigsh``) with one SuperLU factorisation of the
  symmetric positive definite K - sigma M (sigma < 0).  The default shift is
  half of the seventh Rayleigh-Ritz value of K, M on polynomial displacement
  fields up to degree three; by the min-max principle that value bounds the
  first elastic eigenvalue from above, so sigma stays on the order of the
  wanted spectrum.
* Rigid-body modes: a free-free model has exactly six.  The six lowest
  computed modes are reported as rigid only after the project C2E0 rigid
  spectrum criterion (``matrix_model_service``) and a geometric check of their
  span against the six analytic rigid-body fields are both reported; no
  frequency cut-off is used.
* Close modes: guard modes above the requested window are computed and the
  relative spacing of every neighbouring pair is reported.  Shapes inside a
  near-degenerate cluster are only defined up to a rotation within the
  cluster; comparisons must use subspace MAC (``modal_cluster_service``).

Abaqus equivalence of the element remains NOT_VERIFIED.  Nothing here runs
Abaqus or writes any file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import time
from typing import Callable, Mapping, Sequence

import numpy as np
from scipy import sparse
from scipy.sparse import csgraph
from scipy.sparse import linalg as sparse_linalg

from .solid_c3d8i_forward import (
    ABAQUS_EQUIVALENCE,
    FORMULATION_C3D8I_REFERENCE,
    OrthotropicEngineeringConstants,
    c3d8i_reference_stiffness,
    consistent_mass,
    global_elasticity,
)
from .solid_c3d8i_model import SolidModel

RIGID_BODY_MODES_FREE_FREE = 6
PERMUTATION = "MMD_AT_PLUS_A"
GiB = 1024 ** 3

Progress = Callable[[str, int, int], None]
Cancel = Callable[[], bool]


class SolidSolverError(RuntimeError):
    """The sparse modal solve failed."""


class SolverCancelled(SolidSolverError):
    """The caller cancelled the run."""


class ResourceLimitExceeded(SolidSolverError):
    """A configured size, memory, time or iteration limit was reached."""


@dataclass(frozen=True)
class ResourceLimits:
    max_dofs: int = 300_000
    max_memory_bytes: int = 6 * GiB
    max_seconds: float | None = None
    max_operator_applications: int = 5_000
    assembly_chunk_elements: int = 4_000


@dataclass(frozen=True)
class Preflight:
    node_count: int
    element_count: int
    dof_count: int
    distinct_element_geometries: int
    matrix_nonzeros: int             # structural pattern of K (upper bound for K and M)
    matrices_bytes: int
    factor_nonzeros_estimate: int
    factor_bytes_estimate: int
    eigen_workspace_bytes: int
    peak_bytes_estimate: int
    requested_modes: int
    verdict: str                     # WITHIN_LIMITS | EXCEEDS_LIMITS
    reasons: tuple[str, ...]
    formulation: str = FORMULATION_C3D8I_REFERENCE
    abaqus_equivalence: str = ABAQUS_EQUIVALENCE
    factor_estimate_method: str = (
        "SuperLU symbolic fill of the node graph (same ordering, no pivoting) x 9; estimate only")


@dataclass(frozen=True)
class RigidBodyDiagnostics:
    count: int
    eigenvalues: np.ndarray
    c2e0_status: str
    rigid_to_first_elastic_ratio: float
    span_cosines: np.ndarray          # principal-angle cosines: lowest six modes vs analytic rigid fields
    max_rigid_content_of_elastic_modes: float


@dataclass(frozen=True)
class SolidModalResult:
    frequencies_hz: np.ndarray        # requested elastic modes, ascending
    eigenvalues: np.ndarray
    shapes: np.ndarray                # (dof_count, modes), mass-normalised: phi^T M phi = 1
    guard_frequencies_hz: np.ndarray  # computed elastic modes above the window (boundary safety only)
    relative_spacing: np.ndarray      # (f[i+1]-f[i]) / mean, over window and guard modes
    rigid: RigidBodyDiagnostics
    backward_errors: np.ndarray       # all computed modes: ||K phi - lam M phi|| / ((||K|| + |lam| ||M||) ||phi||), inf-norms
    mass_orthogonality_error: float   # max |Phi^T M Phi - I| over all computed modes
    shift: float
    shift_source: str
    operator_applications: int
    factor_nonzeros: int
    seconds: dict
    material: OrthotropicEngineeringConstants
    density: float
    dof_identity: list = field(repr=False)
    formulation: str = FORMULATION_C3D8I_REFERENCE
    abaqus_equivalence: str = ABAQUS_EQUIVALENCE

    def shape_vectors(self, mode: int) -> np.ndarray:
        """(nodes, 3) displacement of elastic mode ``mode`` (0-based) in node-label order."""
        return self.shapes[:, mode].reshape(-1, 3)


# --------------------------------------------------------------------------- helpers


def _check(cancel: Cancel | None, started: float, limits: ResourceLimits) -> None:
    if cancel is not None and cancel():
        raise SolverCancelled("Cancelled by the caller.")
    if limits.max_seconds is not None and time.perf_counter() - started > limits.max_seconds:
        raise ResourceLimitExceeded(f"Time limit of {limits.max_seconds} s reached.")


def rigid_body_fields(coordinates: np.ndarray) -> np.ndarray:
    """(3n, 6) analytic rigid-body displacement fields about the centroid."""
    x = np.asarray(coordinates, float)
    p = x - x.mean(axis=0)
    n = len(x)
    r = np.zeros((n, 3, 6))
    r[:, 0, 0] = r[:, 1, 1] = r[:, 2, 2] = 1.0
    r[:, 1, 3], r[:, 2, 3] = -p[:, 2], p[:, 1]
    r[:, 0, 4], r[:, 2, 4] = p[:, 2], -p[:, 0]
    r[:, 0, 5], r[:, 1, 5] = -p[:, 1], p[:, 0]
    return r.reshape(3 * n, 6)


def _polynomial_fields(coordinates: np.ndarray, degree: int = 3) -> np.ndarray:
    x = np.asarray(coordinates, float)
    span = np.ptp(x, axis=0)
    span[span == 0.0] = 1.0
    s = 2.0 * (x - x.mean(axis=0)) / span
    powers = [(i, j, k) for i in range(degree + 1) for j in range(degree + 1) for k in range(degree + 1)
              if i + j + k <= degree]
    scalars = np.column_stack([s[:, 0] ** i * s[:, 1] ** j * s[:, 2] ** k for i, j, k in powers])
    n, m = scalars.shape
    v = np.zeros((n, 3, 3 * m))
    for comp in range(3):
        v[:, comp, comp * m:(comp + 1) * m] = scalars
    return v.reshape(3 * n, 3 * m)


def ritz_shift(stiffness: sparse.spmatrix, mass: sparse.spmatrix, coordinates: np.ndarray) -> float:
    """-0.5 x the seventh Rayleigh-Ritz value on polynomial fields (degree <= 3)."""
    v = _polynomial_fields(coordinates)
    b = v.T @ (mass @ v)
    w, q = np.linalg.eigh(0.5 * (b + b.T))
    keep = w > w.max() * 1e-12
    t = q[:, keep] / np.sqrt(w[keep])
    a = t.T @ (v.T @ (stiffness @ v)) @ t
    ritz = np.linalg.eigvalsh(0.5 * (a + a.T))
    value = float(ritz[RIGID_BODY_MODES_FREE_FREE])
    if not value > 0.0:
        raise SolidSolverError("Could not bound the first elastic eigenvalue for the shift.")
    return -0.5 * value


# --------------------------------------------------------------------------- forward model


class SolidForwardModel:
    """Sparse K(E1, E2, G12; other constants fixed) and M for one imported model."""

    def __init__(self, model: SolidModel, limits: ResourceLimits = ResourceLimits()):
        self.model = model
        self.limits = limits
        conn = model.connectivity
        x = model.coordinates[conn]                          # (e, 8, 3)
        relative = (x - x[:, :1, :]).reshape(len(conn), 24)
        self._geometries, self._geometry_of = np.unique(relative, axis=0, return_inverse=True)
        self._geometry_of = np.asarray(self._geometry_of).reshape(-1)
        self._dofs = (3 * conn[:, :, None] + np.arange(3)).reshape(len(conn), 24).astype(np.int64)
        self._mass: sparse.csr_matrix | None = None

    # ---------------------------------------------------------------- preflight
    def preflight(self, elastic_modes: int, guard_modes: int = 4) -> Preflight:
        m = self.model
        n_nodes, n_el = len(m.node_labels), len(m.connectivity)
        graph = self._node_graph()
        nnz = 9 * int(graph.nnz)
        index_bytes = 4 if max(3 * n_nodes, nnz) < 2 ** 31 else 8
        matrices = 2 * (nnz * (8 + index_bytes) + (3 * n_nodes + 1) * index_bytes)
        probe = graph.astype(float)
        probe.data[:] = -1.0
        probe = probe + sparse.diags(np.asarray(-probe.sum(axis=1)).ravel() + 1.0)
        lu = sparse_linalg.splu(probe.tocsc(), permc_spec=PERMUTATION, diag_pivot_thresh=0.0,
                                options={"SymmetricMode": True})
        factor_nnz = 9 * int(lu.L.nnz + lu.U.nnz)
        factor_bytes = factor_nnz * (8 + 4)
        k = elastic_modes + guard_modes + RIGID_BODY_MODES_FREE_FREE
        ncv = min(3 * n_nodes, max(2 * k + 1, 20))
        workspace = 3 * n_nodes * (ncv + k + 8) * 8
        chunk = min(self.limits.assembly_chunk_elements, n_el) * 576 * (8 + 8 + 8) * 2
        peak = matrices + factor_bytes + workspace + chunk + matrices  # K - sigma M copy
        reasons = []
        if 3 * n_nodes > self.limits.max_dofs:
            reasons.append(f"{3 * n_nodes} DOFs exceed the limit of {self.limits.max_dofs}.")
        if peak > self.limits.max_memory_bytes:
            reasons.append(f"Estimated peak {peak / GiB:.2f} GiB exceeds {self.limits.max_memory_bytes / GiB:.2f} GiB.")
        if k >= 3 * n_nodes:
            reasons.append("More modes requested than the model has DOFs.")
        return Preflight(n_nodes, n_el, 3 * n_nodes, len(self._geometries), nnz, matrices, factor_nnz,
                         factor_bytes, workspace, peak, elastic_modes,
                         "EXCEEDS_LIMITS" if reasons else "WITHIN_LIMITS", tuple(reasons))

    def _node_graph(self) -> sparse.csr_matrix:
        conn = self.model.connectivity
        n = len(self.model.node_labels)
        rows = np.repeat(conn, 8, axis=1).ravel()
        cols = np.tile(conn, (1, 8)).ravel()
        g = sparse.csr_matrix((np.ones(rows.size, np.int8), (rows, cols)), shape=(n, n))
        g.data[:] = 1
        return g

    def rcm_bandwidth(self) -> int:
        g = self._node_graph()
        perm = csgraph.reverse_cuthill_mckee(g, symmetric_mode=True)
        inv = np.empty_like(perm)
        inv[perm] = np.arange(len(perm))
        coo = g.tocoo()
        return int(3 * (np.abs(inv[coo.row] - inv[coo.col]).max() + 1))

    # ---------------------------------------------------------------- assembly
    def _scatter(self, element_matrices: np.ndarray, name: str, progress, cancel, started) -> sparse.csr_matrix:
        n = self.model.dof_count
        total = len(self._dofs)
        out = sparse.csr_matrix((n, n))
        step = max(1, int(self.limits.assembly_chunk_elements))
        for start in range(0, total, step):
            _check(cancel, started, self.limits)
            stop = min(total, start + step)
            dofs = self._dofs[start:stop]
            data = element_matrices[self._geometry_of[start:stop]].reshape(-1)
            rows = np.repeat(dofs, 24, axis=1).ravel()
            cols = np.tile(dofs, (1, 24)).ravel()
            out = out + sparse.csr_matrix((data, (rows, cols)), shape=(n, n))
            if progress:
                progress(name, stop, total)
        out.sum_duplicates()
        return out

    def mass_matrix(self, *, progress: Progress | None = None, cancel: Cancel | None = None) -> sparse.csr_matrix:
        if self._mass is None:
            started = time.perf_counter()
            mats = np.array([consistent_mass(g.reshape(8, 3), self.model.density) for g in self._geometries])
            self._mass = self._scatter(mats, "assemble mass", progress, cancel, started)
        return self._mass

    def stiffness_matrix(self, material: OrthotropicEngineeringConstants | None = None, *,
                         progress: Progress | None = None, cancel: Cancel | None = None) -> sparse.csr_matrix:
        material = material or self.model.material
        started = time.perf_counter()
        c = global_elasticity(material, self.model.material_axes)
        mats = []
        for i, g in enumerate(self._geometries):
            if i % 64 == 0:
                _check(cancel, started, self.limits)
            mats.append(c3d8i_reference_stiffness(g.reshape(8, 3), c).stiffness)
        return self._scatter(np.array(mats), "assemble stiffness", progress, cancel, started)

    # ---------------------------------------------------------------- solve
    def solve(self, elastic_modes: int, *, material: OrthotropicEngineeringConstants | None = None,
              e1: float | None = None, e2: float | None = None, g12: float | None = None,
              guard_modes: int = 4, shift: float | None = None, seed: int = 20261109,
              progress: Progress | None = None, cancel: Cancel | None = None) -> SolidModalResult:
        if isinstance(elastic_modes, bool) or int(elastic_modes) != elastic_modes or elastic_modes <= 0:
            raise ValueError("elastic_modes must be a positive integer.")
        if guard_modes < 1:
            raise ValueError("At least one guard mode is required for the window boundary.")
        if material is not None and any(v is not None for v in (e1, e2, g12)):
            raise ValueError("Give either a material or E1/E2/G12 overrides, not both.")
        if material is None:
            material = self.model.with_in_plane_constants(e1=e1, e2=e2, g12=g12)
        pre = self.preflight(elastic_modes, guard_modes)
        if pre.verdict != "WITHIN_LIMITS":
            raise ResourceLimitExceeded("Preflight: " + " ".join(pre.reasons))
        started = time.perf_counter()
        times = {}
        mass = self.mass_matrix(progress=progress, cancel=cancel)
        times["mass"] = time.perf_counter() - started
        stiffness = self.stiffness_matrix(material, progress=progress, cancel=cancel)
        times["stiffness"] = time.perf_counter() - started - times["mass"]
        _check(cancel, started, self.limits)

        shift_source = "caller"
        if shift is None:
            shift, shift_source = ritz_shift(stiffness, mass, self.model.coordinates), "ritz_bound"
        if not (math.isfinite(shift) and shift < 0.0):
            raise ValueError("The shift must be negative so that K - sigma M is positive definite.")
        t0 = time.perf_counter()
        if progress:
            progress("factorise", 0, 1)
        try:
            lu = sparse_linalg.splu((stiffness - shift * mass).tocsc(), permc_spec=PERMUTATION,
                                    diag_pivot_thresh=0.0, options={"SymmetricMode": True})
        except RuntimeError as exc:
            raise SolidSolverError(f"Factorisation of K - sigma M failed: {exc}") from exc
        factor_nnz = int(lu.L.nnz + lu.U.nnz)
        if factor_nnz * 12 > self.limits.max_memory_bytes:
            raise ResourceLimitExceeded(f"Factor needs {factor_nnz * 12 / GiB:.2f} GiB.")
        times["factorise"] = time.perf_counter() - t0
        _check(cancel, started, self.limits)

        n = self.model.dof_count
        k = elastic_modes + guard_modes + RIGID_BODY_MODES_FREE_FREE
        applications = [0]

        def apply(vector):
            applications[0] += 1
            if applications[0] > self.limits.max_operator_applications:
                raise ResourceLimitExceeded(
                    f"Operator application limit {self.limits.max_operator_applications} reached.")
            _check(cancel, started, self.limits)
            if progress and applications[0] % 10 == 0:
                progress("eigensolve", applications[0], self.limits.max_operator_applications)
            return lu.solve(np.asarray(vector, float).reshape(-1))

        op = sparse_linalg.LinearOperator((n, n), matvec=apply, dtype=float)
        v0 = np.random.default_rng(seed).standard_normal(n)
        t0 = time.perf_counter()
        try:
            values, vectors = sparse_linalg.eigsh(stiffness, k=k, M=mass, sigma=shift, which="LM",
                                                  OPinv=op, v0=v0, tol=0.0)
        except sparse_linalg.ArpackNoConvergence as exc:
            raise SolidSolverError(f"ARPACK did not converge ({len(exc.eigenvalues)} of {k} pairs).") from exc
        times["eigensolve"] = time.perf_counter() - t0
        order = np.argsort(values)
        values, vectors = values[order], vectors[:, order]

        # mass normalisation, residuals, orthogonality
        mv = mass @ vectors
        vectors = vectors / np.sqrt(np.einsum("ij,ij->j", vectors, mv))
        mv = mass @ vectors
        kv = stiffness @ vectors
        k_norm = float(abs(stiffness).sum(axis=1).max())
        m_norm = float(abs(mass).sum(axis=1).max())
        residual = np.linalg.norm(kv - mv * values, axis=0) / (
            (k_norm + np.abs(values) * m_norm) * np.linalg.norm(vectors, axis=0))
        ortho = float(np.abs(vectors.T @ mv - np.eye(k)).max())

        rigid = self._rigid_diagnostics(values, vectors, mass)
        elastic = values[RIGID_BODY_MODES_FREE_FREE:]
        freqs = np.sqrt(np.clip(elastic, 0.0, None)) / (2.0 * math.pi)
        spacing = np.diff(freqs) / (0.5 * (freqs[1:] + freqs[:-1]))
        times["total"] = time.perf_counter() - started
        window = slice(RIGID_BODY_MODES_FREE_FREE, RIGID_BODY_MODES_FREE_FREE + elastic_modes)
        return SolidModalResult(
            frequencies_hz=freqs[:elastic_modes], eigenvalues=values[window], shapes=vectors[:, window],
            guard_frequencies_hz=freqs[elastic_modes:], relative_spacing=spacing, rigid=rigid,
            backward_errors=residual, mass_orthogonality_error=ortho, shift=float(shift),
            shift_source=shift_source, operator_applications=applications[0], factor_nonzeros=factor_nnz,
            seconds=times, material=material, density=self.model.density,
            dof_identity=self.model.dof_identity())

    def _rigid_diagnostics(self, values, vectors, mass) -> RigidBodyDiagnostics:
        from .matrix_model_service import _classify_expected_rigid_spectrum

        health = _classify_expected_rigid_spectrum(values, RIGID_BODY_MODES_FREE_FREE)
        r = rigid_body_fields(self.model.coordinates)
        g = r.T @ (mass @ r)
        w, q = np.linalg.eigh(0.5 * (g + g.T))
        r_m = r @ (q / np.sqrt(w))                       # M-orthonormal rigid basis
        projection = r_m.T @ (mass @ vectors)            # (6, k)
        cosines = np.linalg.svd(projection[:, :RIGID_BODY_MODES_FREE_FREE], compute_uv=False)
        content = np.sum(projection[:, RIGID_BODY_MODES_FREE_FREE:] ** 2, axis=0)
        return RigidBodyDiagnostics(
            count=RIGID_BODY_MODES_FREE_FREE, eigenvalues=values[:RIGID_BODY_MODES_FREE_FREE].copy(),
            c2e0_status=health.status, rigid_to_first_elastic_ratio=float(health.rigid_to_first_elastic_ratio),
            span_cosines=cosines, max_rigid_content_of_elastic_modes=float(content.max()) if content.size else 0.0)


# --------------------------------------------------------------------------- FE-FE comparison helpers


def signed_frequency_residuals(offline_hz: Sequence[float], reference_hz: Sequence[float]) -> np.ndarray:
    """(f_offline - f_reference) / f_reference by index; pairing by index is NOT a mode assignment."""
    a, b = np.asarray(offline_hz, float), np.asarray(reference_hz, float)
    n = min(len(a), len(b))
    return (a[:n] - b[:n]) / b[:n]


def shape_mac_matrix(result: SolidModalResult, reference_node_ids: Sequence[str],
                     reference_vectors: Sequence[np.ndarray]) -> np.ndarray:
    """MAC(offline mode i, reference mode j) on identical FE node identities.

    ``reference_node_ids`` are ``"INSTANCE:label"`` (as ``abaqus_bridge.load_extracted_odb``
    gives them); every reference node must exist in the offline model and vice versa.
    Each reference vector is (nodes, 3) in that node order.  No pairing is made here.
    """
    identity = {f"{inst}:{label}": i for i, (inst, label, comp) in enumerate(result.dof_identity) if comp == 1}
    ids = [str(v) for v in reference_node_ids]
    if len(ids) != len(identity) or set(ids) != set(identity):
        raise ValueError("Reference and offline node identities are not the same node set.")
    order = np.array([identity[v] // 3 for v in ids])
    offline = result.shapes.reshape(-1, 3, result.shapes.shape[1])[order].reshape(-1, result.shapes.shape[1])
    ref = np.column_stack([np.real(np.asarray(v)).reshape(-1) for v in reference_vectors])
    num = np.abs(offline.T @ ref) ** 2
    den = np.outer(np.einsum("ij,ij->j", offline, offline), np.einsum("ij,ij->j", ref, ref))
    return num / den


__all__ = [
    "Preflight", "ResourceLimitExceeded", "ResourceLimits", "RigidBodyDiagnostics", "SolidForwardModel",
    "SolidModalResult", "SolidSolverError", "SolverCancelled", "rigid_body_fields", "ritz_shift",
    "shape_mac_matrix", "signed_frequency_residuals",
]
