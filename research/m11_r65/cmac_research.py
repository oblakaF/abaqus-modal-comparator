"""M11 R6.5 — research-only experimental–FE complex MAC (isolated research code).

Status of every result produced with this module:
RESEARCH_DIAGNOSTIC_ONLY / COMPUTATIONAL_CONVENTION_ONLY / NO_ACCEPTED_PHYSICAL_REGISTRATION.

This is not the production comparator and not a physical registration: it creates no FrozenRegistration, no
corner_A_marker and no panel_edges evidence, and it applies no pairing criterion. It never selects an orientation,
a geometry scenario, a phase or a frequency by agreement. Pure functions only; the real data are read by
``run_m11_r65.py`` from paths supplied outside Git and refused on any identity mismatch.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
from scipy.spatial import cKDTree

SCHEMA = "m11-r65-research-cmac/v1"
STATUS = ("RESEARCH_DIAGNOSTIC_ONLY", "COMPUTATIONAL_CONVENTION_ONLY", "NO_ACCEPTED_PHYSICAL_REGISTRATION")
PLATE_MM = (301.0, 300.0)

# Experimental axes (scanner view: x right, y up, z towards the scanner) expressed in FE axes (R6.2 / R6.3).
CANDIDATES = {"A": ("-X", "+Y", "-Z"), "B": ("+X", "-Y", "-Z"), "C": ("-X", "-Y", "+Z"), "D": ("+X", "+Y", "+Z")}
REFERENCE_CONVENTION = "D"  # COMPUTATIONAL_CONVENTION_ONLY; never a physical statement


def _scenarios() -> dict:
    out = {}
    for dx in (-3, -2, -1, 0, 1, 2, 3):
        for dy in (-3, -2, -1, 0, 1, 2, 3):
            out[f"dx{dx:+d}_dy{dy:+d}"] = (float(dx), float(dy), 0.0)
    for r in (-0.874, 0.874):
        for dx, dy in ((0, 0), (3, 3), (-3, -3), (3, -3), (-3, 3)):
            out[f"rot{r:+.3f}_dx{dx:+d}_dy{dy:+d}"] = (float(dx), float(dy), r)
    return out


# Fixed before the first experimental-FE MAC was computed (R6.5 §7); its SHA-256 and time are recorded in the local
# execution log only, so it is NOT an independently verified preregistration. Never re-tuned after seeing results.
PROTOCOL = {
    "schema": SCHEMA,
    "status": list(STATUS),
    "primary_metric": "complex MAC |e^H f|^2 / ((e^H e)(f^H f)), complex experimental shape, real FE shape",
    "experimental_set": {"key": "polymax-bravo", "modes": 10, "points": 289, "dof_mask": ["U3"],
                         "unmeasured_dofs": ["U1", "U2"], "representation": "complex, as stored"},
    "fe_modes": list(range(7, 21)),
    "fe_component": "U3 (Assembly frame, shell normal +Z); sign follows the candidate's experimental z axis",
    "mapping_methods": ["nearest_node", "bilinear_S4R"],
    "candidates": {k: list(v) for k, v in CANDIDATES.items()},
    "reference_convention": REFERENCE_CONVENTION + " (COMPUTATIONAL_CONVENTION_ONLY)",
    "scenarios": {k: list(v) for k, v in _scenarios().items()},
    "scenario_rotation_centre": "centroid of the 289 points (scanner view)",
    "separate_hypothesis": "ALT_BOTTOM_EDGE: reconstruction with the competing bottom-edge feature (R6.3); "
                           "reported separately, never merged with the +-3 mm range",
    "subspace_pairs": [[10, 11], [13, 14], [17, 18]],
    "watched_pairs": [[8, 9], [15, 16]],
    "secondary_diagnostics": ["real_normalised_experimental (global phase maximising ||Re||, experimental data "
                              "only)", "beam_projection: FE U3 x cos(beam angle), plate assumed normal to the "
                                       "scan-head axis"],
    "reporting": "full 10 x 14 matrices; nominal value and min/max over the declared scenarios; no scenario, "
                 "orientation, phase, frequency or material is selected by MAC; no pairing status",
}


def protocol_sha256() -> str:
    return hashlib.sha256(json.dumps(PROTOCOL, sort_keys=True).encode("utf-8")).hexdigest()


class ResearchRefusal(ValueError):
    """The research computation refuses (identity, data or geometry); nothing is computed."""


# ----------------------------------------------------------------------------------------------- location guard
# Original stores of the M11 data: never read, never hashed, never written (R6.5a §1). Further roots can be added.
DEFAULT_FORBIDDEN_ROOTS = ((r"C:\temp", r"D:\Snadwich", r"I:\Sumin") if os.name == "nt" else ()) + (
    os.path.join(os.path.expanduser("~"), "Desktop"),)


def _norm(path) -> str:
    """Absolute, lexically normalised, case-folded where the platform is case-insensitive (no filesystem access)."""
    return os.path.normcase(os.path.normpath(os.path.abspath(os.fspath(path))))


def _within(path_n: str, root_n: str) -> bool:
    return path_n == root_n or path_n.startswith(root_n.rstrip("\\/") + os.sep)


def _redirected_component(path_n: str, stop_n: str) -> str | None:
    """The first existing component between ``stop_n`` and ``path_n`` that is a symbolic link or junction."""
    current = path_n
    while True:
        if os.path.lexists(current) and (os.path.islink(current) or
                                         (hasattr(os.path, "isjunction") and os.path.isjunction(current))):
            return current
        if current == stop_n or _within(stop_n, current):
            return None
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


class PathPolicy:
    """Fail-closed location policy, applied BEFORE any input is read or hashed and before any output is written.

    - ``forbidden_roots``: original stores; never read, hashed or written. The check is lexical, so a forbidden
      location is refused without touching it.
    - ``input_roots``: the verified copy and derived work roots that inputs (and the config) may come from.
    - ``protected_roots``: never written (verified copies, the repository).
    - ``output_root``: the only place results may be written; it must not hold any input.

    Relative paths and ``..`` are normalised before the check. A symbolic link or junction in any component, a hard
    link (more than one link to the file) or a real path that differs from the checked path is refused.
    """

    def __init__(self, input_roots: Sequence, output_root, protected_roots: Sequence = (),
                 forbidden_roots: Sequence = DEFAULT_FORBIDDEN_ROOTS) -> None:
        self.forbidden = [_norm(r) for r in forbidden_roots]
        self.inputs = [_norm(r) for r in input_roots]
        self.protected = [_norm(r) for r in protected_roots]
        self.output = _norm(output_root)
        if not self.inputs:
            raise ResearchRefusal("no input root declared")
        for root in self.inputs + [self.output]:
            for bad in self.forbidden:
                if _within(root, bad) or _within(bad, root):
                    raise ResearchRefusal(f"root {root} overlaps the forbidden original store {bad}")
        for bad in self.protected:
            if _within(self.output, bad) or _within(bad, self.output):
                raise ResearchRefusal(f"output root {self.output} overlaps the protected root {bad}")
        for root in self.inputs:
            if _within(root, self.output):
                raise ResearchRefusal(f"input root {root} lies inside the output root")
        for root in self.inputs + [self.output]:
            if os.path.lexists(root):
                hit = _redirected_component(root, os.path.splitdrive(root)[0] + os.sep)
                if hit is not None:
                    raise ResearchRefusal(f"root {root} passes through a link or junction ({hit})")

    def check_input(self, path) -> Path:
        p = _norm(path)
        for bad in self.forbidden:
            if _within(p, bad):
                raise ResearchRefusal(f"{p} lies in a forbidden original store: refused before any access")
        root = next((r for r in self.inputs if _within(p, r)), None)
        if root is None:
            raise ResearchRefusal(f"{p} is outside every declared input root")
        if _within(p, self.output):
            raise ResearchRefusal(f"{p} lies in the output root; inputs never come from there")
        hit = _redirected_component(p, root)
        if hit is not None:
            raise ResearchRefusal(f"{p} passes through a link or junction ({hit})")
        if not os.path.isfile(p):
            raise ResearchRefusal(f"{p} is not a regular file")
        if os.stat(p).st_nlink != 1:
            raise ResearchRefusal(f"{p} is a hard link ({os.stat(p).st_nlink} names): origin cannot be established")
        if _norm(os.path.realpath(p)) != p:
            raise ResearchRefusal(f"{p} resolves elsewhere ({os.path.realpath(p)})")
        return Path(p)

    def check_output_dir(self, path) -> Path:
        p = _norm(path)
        for bad in self.forbidden + self.protected:
            if _within(p, bad):
                raise ResearchRefusal(f"output {p} lies in a forbidden or protected root ({bad})")
        if not _within(p, self.output):
            raise ResearchRefusal(f"output {p} is outside the declared output root {self.output}")
        hit = _redirected_component(p, self.output)
        if hit is not None:
            raise ResearchRefusal(f"output {p} passes through a link or junction ({hit})")
        return Path(p)


# ----------------------------------------------------------------------------------------------- identity
def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_identity(paths: Mapping[str, Path], expected: Mapping[str, str], policy: PathPolicy) -> dict:
    """Every expected input must be supplied, lie in an allowed location (checked first, before any read) and match
    its SHA-256; extra inputs are refused too."""
    missing = sorted(set(expected) - set(paths))
    extra = sorted(set(paths) - set(expected))
    if missing or extra:
        raise ResearchRefusal(f"input set mismatch: missing {missing}, unexpected {extra}")
    located = {name: policy.check_input(paths[name]) for name in expected}  # all locations before any hashing
    found = {}
    for name, sha in expected.items():
        p = located[name]
        h = sha256_file(p)
        if h != sha:
            raise ResearchRefusal(f"input {name!r}: SHA-256 {h} differs from the verified {sha}")
        found[name] = h
    return found


# ----------------------------------------------------------------------------------------------- vectors
def _check(v: np.ndarray, what: str) -> np.ndarray:
    v = np.asarray(v)
    if v.ndim != 1 or v.size == 0:
        raise ResearchRefusal(f"{what}: not a non-empty vector")
    if not np.all(np.isfinite(v)):
        raise ResearchRefusal(f"{what}: non-finite values")
    if float(np.vdot(v, v).real) <= 0.0:
        raise ResearchRefusal(f"{what}: zero vector")
    return v


def cmac(e: np.ndarray, f: np.ndarray) -> float:
    """Complex MAC; invariant to a global complex factor of either vector."""
    e, f = _check(e, "experimental shape"), _check(f, "FE shape")
    if e.shape != f.shape:
        raise ResearchRefusal("shape length mismatch")
    num = abs(np.vdot(e, f)) ** 2
    return float(num / (np.vdot(e, e).real * np.vdot(f, f).real))


def cmac_matrix(experimental: Sequence[np.ndarray], fe: Sequence[np.ndarray]) -> np.ndarray:
    return np.array([[cmac(e, f) for f in fe] for e in experimental])


def real_normalised(e: np.ndarray) -> np.ndarray:
    """Real part after the global phase that maximises ||Re(e exp(-i phi))|| (experimental data only)."""
    e = _check(np.asarray(e, dtype=complex), "experimental shape")
    phi = 0.5 * np.angle(np.sum(e * e))
    return (e * np.exp(-1j * phi)).real


def mpc(e: np.ndarray) -> float:
    re, im = np.real(e), np.imag(e)
    sxx, syy, sxy = re @ re, im @ im, re @ im
    return float(((sxx - syy) ** 2 + 4 * sxy ** 2) / (sxx + syy) ** 2)


def subspace_projection(e: np.ndarray, basis: np.ndarray) -> float:
    """Share of ||e||^2 in span(basis columns); invariant to any change of basis of that span."""
    e = _check(np.asarray(e, dtype=complex), "experimental shape")
    b = np.asarray(basis, dtype=float)
    if b.ndim != 2 or b.shape[0] != e.size:
        raise ResearchRefusal("basis shape mismatch")
    q, r = np.linalg.qr(b)
    if np.min(np.abs(np.diag(r))) <= 1e-12 * np.max(np.abs(np.diag(r))):
        raise ResearchRefusal("basis is rank deficient")
    c = q.T @ e
    return float(np.vdot(c, c).real / np.vdot(e, e).real)


# ----------------------------------------------------------------------------------------------- points
def order_by_reference(node_ids: Sequence, values: np.ndarray, reference_ids: Sequence) -> np.ndarray:
    """Values re-ordered to the reference point order; any missing, duplicate or extra point is refused."""
    ids, ref = [int(i) for i in node_ids], [int(i) for i in reference_ids]
    if len(set(ids)) != len(ids) or len(set(ref)) != len(ref):
        raise ResearchRefusal("duplicate point ids")
    if set(ids) != set(ref):
        raise ResearchRefusal(f"point sets differ: missing {sorted(set(ref) - set(ids))[:5]}, "
                              f"extra {sorted(set(ids) - set(ref))[:5]}")
    pos = {i: k for k, i in enumerate(ids)}
    return np.asarray(values)[[pos[i] for i in ref]]


def candidate_to_fe(points_xy: np.ndarray, axes: Sequence[str], plate=PLATE_MM) -> np.ndarray:
    p = np.asarray(points_xy, dtype=float)
    if tuple(axes[:2]) not in {("+X", "+Y"), ("-X", "+Y"), ("+X", "-Y"), ("-X", "-Y")}:
        raise ResearchRefusal(f"unsupported candidate axes {axes}")
    x = p[:, 0] if axes[0] == "+X" else plate[0] - p[:, 0]
    y = p[:, 1] if axes[1] == "+Y" else plate[1] - p[:, 1]
    return np.column_stack([x, y])


def z_sign(axes: Sequence[str]) -> float:
    if axes[2] not in ("+Z", "-Z"):
        raise ResearchRefusal(f"unsupported z axis {axes[2]}")
    return 1.0 if axes[2] == "+Z" else -1.0


def scenario_points(points_xy: np.ndarray, dx: float, dy: float, rot_deg: float) -> np.ndarray:
    p = np.asarray(points_xy, dtype=float)
    c = p.mean(axis=0)
    t = math.radians(rot_deg)
    rot = np.array([[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]])
    return (p - c) @ rot.T + c + np.array([dx, dy])


# ----------------------------------------------------------------------------------------------- FE transfer
class NearestNode:
    def __init__(self, node_xy: np.ndarray) -> None:
        self.tree = cKDTree(np.asarray(node_xy, dtype=float))

    def locate(self, points: np.ndarray):
        dist, idx = self.tree.query(np.asarray(points, dtype=float))
        return np.asarray(idx, dtype=int), np.asarray(dist)

    @staticmethod
    def sample(field: np.ndarray, located) -> np.ndarray:
        return np.asarray(field)[located[0]]


class BilinearQuadMesh:
    """Four-node isoparametric (S4R) interpolation of a nodal field; points outside every element are refused."""

    def __init__(self, node_xy: np.ndarray, elements: np.ndarray, tol: float = 1e-9) -> None:
        self.xy = np.asarray(node_xy, dtype=float)
        self.el = np.asarray(elements, dtype=int)
        if self.el.ndim != 2 or self.el.shape[1] != 4 or self.el.min() < 0 or self.el.max() >= len(self.xy):
            raise ResearchRefusal("invalid quadrilateral connectivity")
        c = self.xy[self.el]
        self.lo, self.hi = c.min(axis=1), c.max(axis=1)
        self.tol = tol

    @staticmethod
    def shape(xi, eta):
        return 0.25 * np.array([(1 - xi) * (1 - eta), (1 + xi) * (1 - eta), (1 + xi) * (1 + eta), (1 - xi) * (1 + eta)])

    def _inverse(self, e: int, p: np.ndarray):
        c = self.xy[self.el[e]]
        xi = eta = 0.0
        for _ in range(30):
            n = self.shape(xi, eta)
            r = n @ c - p
            dxi = 0.25 * np.array([-(1 - eta), (1 - eta), (1 + eta), -(1 + eta)])
            deta = 0.25 * np.array([-(1 - xi), -(1 + xi), (1 + xi), (1 - xi)])
            jac = np.column_stack([dxi @ c, deta @ c])
            step = np.linalg.solve(jac, r)
            xi, eta = xi - step[0], eta - step[1]
            if np.linalg.norm(step) < 1e-14:
                break
        return xi, eta

    def locate(self, points: np.ndarray):
        pts = np.asarray(points, dtype=float)
        elems, coords = [], []
        span = float(np.max(self.hi - self.lo))
        for p in pts:
            cand = np.where(np.all(self.lo - self.tol * span <= p, axis=1) & np.all(p <= self.hi + self.tol * span,
                                                                                     axis=1))[0]
            hit = None
            for e in cand:
                xi, eta = self._inverse(int(e), p)
                if abs(xi) <= 1 + 1e-9 and abs(eta) <= 1 + 1e-9:
                    hit = (int(e), xi, eta)
                    break
            if hit is None:
                raise ResearchRefusal(f"point {p.tolist()} lies in no element: bilinear transfer refused "
                                      "(no extrapolation)")
            elems.append(hit[0])
            coords.append(hit[1:])
        return np.array(elems), np.array(coords)

    def sample(self, field: np.ndarray, located) -> np.ndarray:
        elems, coords = located
        f = np.asarray(field)
        out = np.empty(len(elems), dtype=f.dtype)
        for k, (e, (xi, eta)) in enumerate(zip(elems, coords)):
            out[k] = self.shape(xi, eta) @ f[self.el[e]]
        return out
