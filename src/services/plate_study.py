"""PLATE-ONLY-R1 — research study of the effective bending stiffness of one free-free CFRP plate (RESEARCH_ONLY).

Scope (owner, PLATE-ONLY-R1): one physical specimen, ``PLATE-300x300x1mm``, series
``NEXP29/PLATE300-1MM/S261027-ROTATED``. No sandwich result, no SP-02 / SP-10 / SP-13 data and no material record of
another specimen enters this study. Nothing here is governed evidence, no material constant is released, and no
Abaqus, solver, LM campaign or Auto-ID is run: the iterative estimation is prepared behind a gate that refuses
without a separate authorisation (``request_iteration``).

What the module does, each time with the project's existing services and rules (no new threshold):

- **Sources.** The working source is identified by its SHA-256 (``classify_source``). The M11 session 261016 is
  history only; that it is the same physical plate is not established (``PLATE_IDENTITY``), so no M11 measurement
  (mass, plan, thickness) is attached to this plate.
- **Experiment** (``experimental_summary``): every record of the fitted set, record 1 included; phase collinearity
  (``services.experimental_qc``), measured components, the scan geometry and descriptive shape invariants (rigid-plane
  fraction, saddle and dome curvature fractions, invariant under in-plane rotation). Close groups are the existing
  cluster triggers (3 %): a trigger only.
- **FE family** (``PLATE_FE_FAMILY``): the M11 S4R model and its four controlled variants (R6.6 G12, R6.7 E1 / E2),
  with the SHA-256 of INP, ODB and extraction, and three earlier models with frequencies only. All of them are
  ``CANDIDATE_FE_REFERENCE``: a model of the M11 plate, not a confirmed model of this specimen.
- **Comparison.** ``services.new_odb_comparison.frequency_only_diagnostic`` (frequency proximity only, never a mode
  pair) and ``bind_registration_by_fe_geometry`` (the archived registrations; no orientation is chosen by MAC or
  frequency). Without a verified registration the status is ``PHYSICAL_REGISTRATION_NOT_VERIFIED``.
- **FE sensitivities** (``sensitivity_table``): every elastic FE branch is followed into each variant by FE-to-FE MAC
  with ``services.branch_tracker.track_branches`` (policy ``STRICT_IDENTIFICATION_PAIRING``); triggered FE pairs are
  examined with ``services.identification_clusters.confirm_cluster``. s = Δ ln f / Δ ln p is a **secant** over the
  variant step (−10 % for E1 / E2, +100 % / +200 % for G12): research sensitivities, not the SPEC §6 S4 central
  ±5 % differences. The D-parameter columns follow from the exact Jacobian of ln D with respect to ln E of a
  homogeneous orthotropic Kirchhoff plate (``d_jacobian``).
- **Identifiability** (``design_study``): the M5 system of ``services.practical_identifiability`` for a declared set
  of rows that would have to be confirmed pairs. A design study, labelled ``HYPOTHETICAL_PAIRING``: it shows what the
  data could constrain, never what they do.
- **Synthetic twin** (``run_synthetic_twin``): a log-linear ``SURROGATE`` forward model built from the FE secant
  sensitivities, the existing bounded LM (``services.identification_step``), the evidence chain and verdicts
  (``services.identification_verdict``, ``SYNTHETIC_GATE``).
- **Readiness and outcomes** (``plate_readiness``, ``parameter_outcome``): IDENTIFIABLE_UNDER_GOVERNED_RULES only with
  a PRODUCTION verdict IDENTIFIED / WIDE; RESEARCH_CANDIDATE_ONLY for a research estimate with its assumptions;
  NOT_IDENTIFIABLE otherwise, with the reasons.
- **Uncertainty budget** (``uncertainty_budget``): the statistical part, thickness (D ∝ E·h³), mass, setup and
  model form kept separate; a frequency error of x % is not an x % parameter error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
from pathlib import Path, PureWindowsPath
import re
from typing import Any, Mapping, Optional, Sequence

import numpy as np

RESEARCH_ONLY = "RESEARCH_ONLY"
SURROGATE = "SURROGATE"
HYPOTHETICAL_PAIRING = "HYPOTHETICAL_PAIRING"
NOT_A_MATERIAL_PROPERTY = "NOT_A_MATERIAL_PROPERTY"
CANDIDATE_FE_REFERENCE = "CANDIDATE_FE_REFERENCE"
FREQUENCY_ONLY = "FREQUENCY_ONLY"
NOT_VERIFIED = "PHYSICAL_REGISTRATION_NOT_VERIFIED"
NOT_READY = "NOT_READY_FOR_IDENTIFICATION"
ITERATION_NOT_AUTHORISED = "ITERATION_NOT_AUTHORISED"
SECANT = "SECANT_RESEARCH_SENSITIVITY (not SPEC §6 S4 central ±5 %)"

IDENTIFIABLE = "IDENTIFIABLE_UNDER_GOVERNED_RULES"
RESEARCH_CANDIDATE = "RESEARCH_CANDIDATE_ONLY"
NOT_IDENTIFIABLE = "NOT_IDENTIFIABLE"

SPECIMEN = "PLATE-300x300x1mm"
SERIES = "NEXP29/PLATE300-1MM/S261027-ROTATED"
WORKING_SOURCE_SHA256 = "76db80aed1b4ba7062c0bf914cae85b55ea2665d80cb643c8cd54ba6c8bedc4d"
WORKING_SOURCE = r"SPname_files_ROTATED_261028\300by300_plate_only_1mm_ROTATED_Polytec_261027.unv"
WORKING_SET = "Polymax_bravo"
AUXILIARY_FRF_SHA256 = "d3bc99e9d0fd8261fd878b83fc8eec8b27206cec23eeea240d2a3cd7712b9878"
M11_HISTORY_SHA256 = "117c893bafbb"  # prefix of the M11 261016 PolyMAX UNV (history only); full value checked below
WORKING = "WORKING_SOURCE"
AUXILIARY = "AUXILIARY_FRF_CHECK_ONLY"
HISTORY = "M11_HISTORY_ONLY"
UNKNOWN_SOURCE = "NOT_A_PLATE_STUDY_SOURCE"

PLATE_IDENTITY = "NOT_ESTABLISHED"
IDENTITY_EVIDENCE = (
    ("file names", "the 261016 and 261027 files carry the same plate description", "SUGGESTS, does not prove"),
    ("owner note 2026-10-25 (M11 §21)", "with a changed suspension the first resonance appeared near 19 Hz instead "
     "of about 33 Hz", "information on the test conditions; not a statement of identity"),
    ("frequencies", "several higher fitted frequencies are within about 1 % between the sessions",
     "not evidence of physical identity (frequency proximity is never identity)"),
    ("mass, plan, thickness of the tested plate", "not recorded for the 261027 session", "MISSING"),
    ("marks, photographs, serial", "none for the 261027 session", "MISSING"),
)
IDENTITY_NEEDED = (
    "a lab or owner statement that the 261027 plate is the M11 plate (or not)",
    "its mass, plan dimensions and a thickness map (9+ points, SPEC v1.1 §5 / §15) measured for this plate",
    "a photograph of the mounted plate with a corner mark and the face shown to the scanner",
)
M11_MEASUREMENTS_NOT_ATTACHED = ("mass 118.37 g, plan 301 × 300 mm and 20 edge thickness readings (mean 0.876 mm) "
                                 "belong to the M11 plate; they are NOT attached to PLATE-300x300x1mm")


def classify_source(sha256: str) -> str:
    """The role of an experimental file in this study, by its SHA-256 only (never a name or a frequency)."""
    sha256 = str(sha256 or "").lower()
    if sha256 == WORKING_SOURCE_SHA256:
        return WORKING
    if sha256 == AUXILIARY_FRF_SHA256:
        return AUXILIARY
    if sha256.startswith(M11_HISTORY_SHA256):
        return HISTORY
    return UNKNOWN_SOURCE


class PlateStudyRefusal(ValueError):
    """The plate study does not use these data; the message says why."""


def require_working_source(sha256: str) -> None:
    role = classify_source(sha256)
    if role != WORKING:
        raise PlateStudyRefusal(
            f"the experimental file (SHA-256 {str(sha256)[:12]}…) is {role}, not the working source of {SERIES}; "
            "an M11 or auxiliary file never replaces it, and the M11 data are history only.")


# ----------------------------------------------------------------------------- FE family

WORK_ROOT = Path(r"D:\git\abaqus-modal-comparator-work")


@dataclass(frozen=True)
class FEFile:
    relative: str
    sha256: str


@dataclass(frozen=True)
class FEMember:
    member_id: str
    description: str
    elements: str
    parameters: Mapping[str, float]  # E1, E2, E3, nu12, nu13, nu23, G12, G13, G23 (MPa), h (mm), rho (t/mm³)
    inp: FEFile
    manifest: Optional[FEFile] = None  # extracted shapes (comparator extraction format 2)
    odb: Optional[FEFile] = None
    dat: Optional[FEFile] = None
    variant_of: Optional[str] = None  # the baseline member it differs from by one field
    changed: Optional[str] = None  # the changed parameter
    status: str = CANDIDATE_FE_REFERENCE


_S4R = {"E1": 56000.0, "E2": 56000.0, "E3": 8500.0, "nu12": 0.05, "nu13": 0.3, "nu23": 0.3, "G12": 5000.0,
        "G13": 3000.0, "G23": 3000.0, "h": 0.875, "rho": 1.498e-9}
_M11 = "runs/m11_carbon_plate"
_V3 = "external_models/v3_20261021/Plate/temp_root"
PLATE_FE_FAMILY = (
    FEMember("S4R_0875_BASELINE", "CFRP_S4R_0875_FreeFree (M11 R6 extraction)", "S4R, 100 × 100, h 0.875",
             dict(_S4R), FEFile(f"{_V3}/CFRP_S4R_0875_FreeFree.inp",
                                "962f75f2fd5d9e6d97578df828599bc150b9777648392b29e8c856546af81df3"),
             FEFile(f"{_M11}/odb_extraction_r6/output/manifest.json",
                    "354966dae2126d11610b9fdb56804006b56b40aea1cf7a180278ef375893b4c7"),
             FEFile(f"{_M11}/odb_extraction_r6/input/CFRP_S4R_0875_FreeFree.odb",
                    "7daeb7e35adf6bd6fabe8f9f582859935ca3d8927ae32fcf07a35c38e8c023b8"),
             FEFile(f"{_V3}/CFRP_S4R_0875_FreeFree.dat",
                    "f440592598a21bd23dd7fa68f1032ebcd4d0da4d33b48156adc68ec690625de9")),
    FEMember("S4R_0875_G12_10000", "R6.6-A: G12 5 000 → 10 000", "S4R, as baseline", {**_S4R, "G12": 10000.0},
             FEFile(f"{_M11}/r66/CFRP_S4R_0875_FreeFree_R66A_G12_10000/CFRP_S4R_0875_FreeFree_R66A_G12_10000.inp",
                    "36dce25dc5fb5c7cfd20fcd2a4701df897e9870a219d65744e5159fdbad87a6e"),
             FEFile(f"{_M11}/r66/CFRP_S4R_0875_FreeFree_R66A_G12_10000/extraction/manifest.json",
                    "2808101150270dd9030a97ce0f519a196980bd0281b37aa854e1092a7e27f0c7"),
             variant_of="S4R_0875_BASELINE", changed="G12"),
    FEMember("S4R_0875_G12_15000", "R6.6-B: G12 5 000 → 15 000", "S4R, as baseline", {**_S4R, "G12": 15000.0},
             FEFile(f"{_M11}/r66/CFRP_S4R_0875_FreeFree_R66B_G12_15000/CFRP_S4R_0875_FreeFree_R66B_G12_15000.inp",
                    "b5a504771a1cc66b359a2191ed3041d019434dcfc9380aaa4e81f4348089204b"),
             FEFile(f"{_M11}/r66/CFRP_S4R_0875_FreeFree_R66B_G12_15000/extraction/manifest.json",
                    "f2b88494a6262b2ecfa6a83d7694cebb6319497cc1e922d3b670741676673a6a"),
             variant_of="S4R_0875_BASELINE", changed="G12"),
    FEMember("S4R_0875_E1_50400", "R6.7-A: E1 56 000 → 50 400", "S4R, as baseline", {**_S4R, "E1": 50400.0},
             FEFile(f"{_M11}/r67/CFRP_S4R_0875_FreeFree_R67A_E1_50400/CFRP_S4R_0875_FreeFree_R67A_E1_50400.inp",
                    "fd220f14755f2ccaed21c0848c82b67f4b6e2c43b23490aa190294ec32976ad6"),
             FEFile(f"{_M11}/r67/CFRP_S4R_0875_FreeFree_R67A_E1_50400/extraction/manifest.json",
                    "91c523bddb2df0c797c2ed2814e03bfffc8155ed83e558e41078eb476878428d"),
             variant_of="S4R_0875_BASELINE", changed="E1"),
    FEMember("S4R_0875_E2_50400", "R6.7-B: E2 56 000 → 50 400", "S4R, as baseline", {**_S4R, "E2": 50400.0},
             FEFile(f"{_M11}/r67/CFRP_S4R_0875_FreeFree_R67B_E2_50400/CFRP_S4R_0875_FreeFree_R67B_E2_50400.inp",
                    "5c08084b51c8af446be69fd8c49fae7389f86e90b37b4d81f100955eebdba2eb"),
             FEFile(f"{_M11}/r67/CFRP_S4R_0875_FreeFree_R67B_E2_50400/extraction/manifest.json",
                    "688c0b1e78c55435fb0269f799989a5d2b0925204c32b65ceadd430379bc2d58"),
             variant_of="S4R_0875_BASELINE", changed="E2"),
    FEMember("S4R_WEDGE", "CFRP_S4R_WEDGE_FreeFree (nodal thickness 0.93 → 0.81)", "S4R, nodal thickness",
             {**_S4R, "h": float("nan")}, FEFile(f"{_V3}/CFRP_S4R_WEDGE_FreeFree.inp",
                                                 "dcb639f14a008eeb29179d36817993279451b615b9061753a9afec27b628bb4b"),
             dat=FEFile(f"{_V3}/CFRP_S4R_WEDGE_FreeFree.dat",
                        "d545876a72d7ebf5c1f2e0c76a84a6188821ea26e59cd3642a89aaeb0d4394fe")),
    FEMember("C3D8I_0875", "CFRP_C3D8I_0875_FreeFree (E 60 000)", "C3D8I, 3 through the thickness",
             {**_S4R, "E1": 60000.0, "E2": 60000.0}, FEFile(
                 f"{_V3}/CFRP_C3D8I_0875_FreeFree.inp",
                 "b2be6ff5f12b51196601c510f31b7fcc77a1cc5fff8c039bb04efa38f25c7e3e"),
             dat=FEFile(f"{_V3}/CFRP_C3D8I_0875_FreeFree.dat",
                        "8dcc84881bda7a5607a38e42c0e1c255a762bafb268cdbcd4ced0b43e162c6cd")),
    FEMember("E30E26", "E30E26 (owner's manual fit, not a measurement)", "C3D8I, h 1.0",
             {**_S4R, "E1": 30820.0, "E2": 26520.0, "nu12": 0.3, "G12": 10000.0, "h": 1.0, "rho": 1.31522e-9},
             FEFile(f"{_V3}/E30E26.inp", "3ac44ab34931d1dd524fc60893a4f551f9dd089a6996309170ea21d3c8acf9e6"),
             dat=FEFile(f"{_V3}/E30E26.dat", "e24129e25e44969e5c49f0354ee1281813bab883a7b88bfe2d2a6399cb4471f3")),
)
FE_LIMITS = (
    "Every member models the M11 plate (plan 301 × 300, mass 118.36 g): a CANDIDATE_FE_REFERENCE for "
    "PLATE-300x300x1mm, not a confirmed model of it (identity NOT_ESTABLISHED).",
    "One homogeneous orthotropic material on global axes, no *Orientation: material axis 1 = FE X (301 mm). The "
    "fibre and weave directions of the real plate are not evidenced, so E1 / E2 are model directions.",
    "Free-free without suspension, shaker or attachment; the test used rubber bands and strings at two points.",
    "INP → ODB: the records are consistent (job name, heading, timing, element type, eigenvalues), but mesh "
    "identity is not proven (M11 §15.5).",
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:  # read-only
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class FileCheck:
    role: str
    path: str
    expected: str
    state: str  # VERIFIED / MISSING / CHANGED


def verify_member(member: FEMember, root: Path = WORK_ROOT) -> tuple[FileCheck, ...]:
    checks = []
    for role in ("inp", "manifest", "odb", "dat"):
        item = getattr(member, role)
        if item is None:
            continue
        path = Path(root).joinpath(*PureWindowsPath(item.relative).parts)
        if not path.is_file():
            state = "MISSING"
        else:
            state = "VERIFIED" if file_sha256(path) == item.sha256 else "CHANGED"
        checks.append(FileCheck(role, str(path), item.sha256, state))
    return tuple(checks)


def parse_inp_material(text: str) -> dict:
    """*Elastic ENGINEERING CONSTANTS, *Density and the shell thickness of an Abaqus input (one material)."""
    values = {}
    elastic = re.search(r"\*Elastic,\s*type=ENGINEERING CONSTANTS\s*\n([^\n]*)\n([^\n*]*)", text, re.IGNORECASE)
    if elastic:
        numbers = [float(x) for x in re.findall(r"[-+]?\d+\.?\d*(?:[eE][-+]?\d+)?", elastic.group(1) + "," +
                                                                                   elastic.group(2))]
        for name, value in zip(("E1", "E2", "E3", "nu12", "nu13", "nu23", "G12", "G13", "G23"), numbers):
            values[name] = value
    density = re.search(r"\*Density\s*\n\s*([-+\d.eE]+)", text)
    if density:
        values["rho"] = float(density.group(1))
    shell = re.search(r"\*Shell Section[^\n]*\n\s*([-+\d.eE]+)", text)
    if shell:
        values["h"] = float(shell.group(1))
    return values


def parse_dat_frequencies(text: str) -> tuple[tuple[int, float], ...]:
    """(mode, cycles/time) rows of the first EIGENVALUE OUTPUT table of an Abaqus .dat file."""
    start = text.find("E I G E N V A L U E    O U T P U T")
    if start < 0:
        return ()
    rows = []
    for line in text[start:].splitlines()[1:]:
        match = re.match(r"\s*(\d+)\*?\s+([-+\d.Ee]+)\s+([-+\d.Ee]+)\s+([-+\d.Ee]+)", line)
        if match:
            rows.append((int(match.group(1)), float(match.group(4))))
        elif rows and line.strip() and not line.strip().startswith("MODE"):
            if not re.match(r"\s*\d", line):
                break
    return tuple(rows)


# ----------------------------------------------------------------------------- experiment

@dataclass(frozen=True)
class ExperimentalRecord:
    position: int
    mode: int
    frequency_hz: float
    mpc: Optional[float]
    measured_components: str
    points: int
    rigid_plane_fraction: float
    saddle_fraction: float
    dome_fraction: float
    classification: str


@dataclass(frozen=True)
class ExperimentalSummary:
    source_sha256: str
    source_role: str
    modal_set: str
    records: tuple
    point_count: int
    span_m: tuple
    plane_normal: tuple
    scan_distance_m: float
    grid_spacing_m: float
    grid_axis_angle_deg: float
    close_groups: tuple
    damping_note: str
    limits: tuple


def _aligned_real(vector: np.ndarray) -> np.ndarray:
    """The real shape after the best global phase rotation (descriptive only)."""
    v = np.asarray(vector, dtype=complex)
    stack = np.vstack([v.real, v.imag])
    _, _, vt = np.linalg.svd(stack.T, full_matrices=False)
    phase = math.atan2(vt[0, 1], vt[0, 0])
    return (v * np.exp(-1j * phase)).real


def shape_invariants(coordinates: np.ndarray, out_of_plane: np.ndarray) -> tuple[float, float, float]:
    """(rigid-plane, saddle, dome) energy fractions of the shape (orthogonal blocks, each ≤ 1, sum ≤ 1); invariant
    under an in-plane rotation of the grid. Descriptive: they classify no mode and pair nothing."""
    xy = np.asarray(coordinates, dtype=float)[:, :2]
    xy = (xy - xy.mean(axis=0)) / max(np.ptp(xy, axis=0).max(), 1e-12)
    w = _aligned_real(out_of_plane)
    x, y = xy[:, 0], xy[:, 1]
    # orthonormal blocks in this order: rigid plane, saddle (x² − y², 2xy), dome (x² + y²); energy fractions ≤ 1
    q, _ = np.linalg.qr(np.column_stack([np.ones(len(xy)), x, y, x * x - y * y, 2 * x * y, x * x + y * y]))
    energy = float(w @ w) or 1.0
    parts = (q[:, :3], q[:, 3:5], q[:, 5:6])
    rigid, saddle, dome = (float(np.sum((block.T @ w) ** 2)) / energy for block in parts)
    return rigid, saddle, dome


def _grid(coordinates: np.ndarray) -> tuple[float, float]:
    xy = np.asarray(coordinates, dtype=float)[:, :2]
    distances = np.linalg.norm(xy[:, None, :] - xy[None, :, :], axis=2)
    np.fill_diagonal(distances, np.inf)
    nearest = distances.argmin(axis=1)
    vectors = xy[nearest] - xy
    angles = np.degrees(np.arctan2(vectors[:, 1], vectors[:, 0])) % 90.0
    return float(np.median(distances.min(axis=1))), float(np.median(angles))


def experimental_summary(dataset, source_sha256: str) -> ExperimentalSummary:
    """The fitted set as read (every record, record 1 included); descriptive metrics only."""
    from services.experimental_qc import _phase_collinearity
    from services.identification_clusters import TriggerRow, cluster_triggers

    modes = dataset.sorted_modes()
    fitted = "55" in str((dataset.metadata or {}).get("mode_source") or "")
    records = []
    for position, mode in enumerate(modes, start=1):
        vectors = np.asarray(mode.vectors)
        measured = [k for k in range(3) if np.any(np.abs(vectors[:, k]) > 0)]
        mpc = _phase_collinearity(vectors[:, measured]) if measured else None
        rigid, saddle, dome = shape_invariants(mode.coordinates, vectors[:, 2])
        records.append(ExperimentalRecord(position, int(mode.number), float(mode.frequency_hz), mpc,
                                          "".join("XYZ"[k] for k in measured), len(vectors), rigid, saddle, dome,
                                          "FITTED (dataset 55)" if fitted else "PROVISIONAL FRF (dataset 58)"))
    coordinates = np.asarray(modes[0].coordinates, dtype=float)
    centred = coordinates - coordinates.mean(axis=0)
    normal = np.linalg.svd(centred, full_matrices=False)[2][2]
    spacing, angle = _grid(coordinates)
    triggers = cluster_triggers([TriggerRow(f"E{r.mode}", r.frequency_hz, r.frequency_hz) for r in records])
    return ExperimentalSummary(
        source_sha256=source_sha256, source_role=classify_source(source_sha256),
        modal_set=str((dataset.metadata or {}).get("modal_set_name") or ""), records=tuple(records),
        point_count=len(coordinates), span_m=tuple(float(v) for v in np.ptp(coordinates, axis=0)),
        plane_normal=tuple(float(v) for v in normal), scan_distance_m=float(-coordinates[:, 2].mean()),
        grid_spacing_m=spacing, grid_axis_angle_deg=angle,
        close_groups=tuple(trigger.row_ids for trigger in triggers),
        damping_note=("Damping is not in the dataset-55 records; the lab workbook lists damping ratios for records "
                      "1–10 (record 11 not listed). They are shown as the workbook's values, not as fitted data."),
        limits=("The scan grid is rotated about 45° in the camera frame (ROTATED session); which plate edge and face "
                "relate to which scanner axis is UNKNOWN.",
                "The PolyMAX geometry carries z = −1.15 m (the measured Polytec distance); scale and in-plane "
                "orientation relative to the plate edges are not calibrated against the plate.",
                "Shape invariants (rigid-plane, saddle, dome fractions) are descriptive; they classify no mode and "
                "pair nothing."))


# ----------------------------------------------------------------------------- FE states and sensitivities

def elastic_modes(dataset) -> list:
    """FE modes outside the comparator's rigid-body shape criterion (the first elastic mode is kept)."""
    from quality_control import RIGID_SHAPE_RESIDUAL_THRESHOLD
    from quality_control_reviewed import _rigid_body_residual_fraction

    return [mode for mode in dataset.sorted_modes()
            if _rigid_body_residual_fraction(mode) > RIGID_SHAPE_RESIDUAL_THRESHOLD]


def fe_state(dataset, state_id: str):
    """The elastic modes of an FE dataset as a ``branch_tracker.FEModalState`` (full U1–U3 on the FE nodes)."""
    from scientific_state import modal_dataset_geometry_identity
    from services.branch_tracker import FEModalState

    modes = elastic_modes(dataset)
    identity = modal_dataset_geometry_identity(dataset)
    shapes = np.vstack([np.asarray(mode.vectors).real.astype(float).reshape(-1) for mode in modes])
    return FEModalState(state_id, identity["sha256"], identity["sha256"], tuple(int(m.number) for m in modes),
                        tuple(float(m.frequency_hz) for m in modes), shapes)


@dataclass(frozen=True)
class BranchRow:
    row_id: str
    baseline_mode: int
    baseline_hz: float
    tracked: Mapping[str, Any]  # variant id → (candidate mode or pair, candidate Hz, MAC / cos², status)
    sensitivity: Mapping[str, Optional[float]]  # parameter → secant s (None when not tracked)
    cluster: Optional[tuple] = None


@dataclass(frozen=True)
class SensitivityTable:
    baseline: str
    variants: tuple  # (variant id, parameter, ratio)
    rows: tuple
    clusters: tuple  # (row ids, status, reasons)
    basis: str = SECANT
    labels: tuple = (RESEARCH_ONLY, CANDIDATE_FE_REFERENCE)

    def matrix(self, parameters: Sequence[str], rows: Optional[Sequence[str]] = None) -> tuple:
        """(row ids, S) for rows with every parameter available."""
        keep = [row for row in self.rows if (rows is None or row.row_id in rows)
                and all(row.sensitivity.get(p) is not None for p in parameters)]
        return tuple(row.row_id for row in keep), np.array([[row.sensitivity[p] for p in parameters] for row in keep])


def _track_rows(policy, reference, candidate, rows: Mapping[str, int], clusters=()) -> dict:
    """Follow each row on its own (a loss affects that row only), then check exchange on the set."""
    from services.branch_tracker import BranchTrackingRefusal, track_branches

    outcome = {}
    clustered = {row for group in clusters for row in group}
    for row, mode in rows.items():
        if row in clustered:
            continue
        try:
            result = track_branches(policy, reference, candidate, {row: mode})
            branch = result.branches[0]
            outcome[row] = (branch.candidate_mode, branch.candidate_hz, branch.mac, "TRACKED")
        except BranchTrackingRefusal as refusal:
            outcome[row] = (None, None, None, f"{refusal.kind.value}: {'; '.join(refusal.details)}")
    tracked = {row: rows[row] for row, value in outcome.items() if value[3] == "TRACKED"}
    if tracked or clusters:
        try:
            result = track_branches(policy, reference, candidate, {**tracked, **{r: rows[r] for r in clustered}},
                                    clusters=[tuple(group) for group in clusters])
            for cluster in result.clusters:
                for row in cluster.row_ids:
                    outcome[row] = (cluster.candidate_modes, cluster.candidate_hz, cluster.cos2, "TRACKED_CLUSTER")
        except BranchTrackingRefusal as refusal:
            for row in list(tracked) + sorted(clustered):
                outcome[row] = (None, None, None, f"SET_REFUSED {refusal.kind.value}: {'; '.join(refusal.details)}")
    return outcome


def sensitivity_table(baseline_dataset, variants: Mapping[str, tuple]) -> SensitivityTable:
    """Secant sensitivities of every elastic FE branch.

    ``variants`` maps an id to (dataset, parameter, ratio p_variant / p_baseline). Triggered FE pairs (3 %) are examined
    with ``confirm_cluster`` over every variant; a CONFIRMED pair is one cluster term (mean ln f).
    """
    from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING
    from services.identification_clusters import (ClusterStatus, TriggerRow, cluster_triggers, confirm_cluster)

    reference = fe_state(baseline_dataset, "baseline")
    states = {key: fe_state(dataset, key) for key, (dataset, _p, _r) in variants.items()}
    rows = {f"FE{mode}": mode for mode in reference.mode_numbers}
    hz = dict(zip(reference.mode_numbers, reference.frequencies_hz))
    triggers = cluster_triggers([TriggerRow(row, hz[mode], hz[mode]) for row, mode in rows.items()])
    clusters, cluster_notes = [], []
    for trigger in triggers:
        if len(trigger.row_ids) != 2:
            cluster_notes.append((trigger.row_ids, "NOT_A_2_MODE_GROUP", ("examined row by row",)))
            continue
        baseline_shapes = reference.shapes[[reference.index(rows[r]) for r in trigger.row_ids]]
        confirmation = confirm_cluster(trigger.row_ids, baseline_shapes,
                                       {key: state.shapes for key, state in states.items()},
                                       required_directions=tuple(states))
        cluster_notes.append((trigger.row_ids, confirmation.status.value, tuple(confirmation.reasons)))
        if confirmation.status is ClusterStatus.CONFIRMED:
            clusters.append(trigger.row_ids)
    tracked = {key: _track_rows(STRICT_IDENTIFICATION_PAIRING, reference, state, rows, clusters)
               for key, state in states.items()}
    cluster_of = {row: tuple(group) for group in clusters for row in group}
    table_rows = []
    for row, mode in rows.items():
        per_variant, sensitivity = {}, {}
        for key, (_dataset, parameter, ratio) in variants.items():
            value = tracked[key].get(row)
            per_variant[key] = value
            if value is None or value[3] not in ("TRACKED", "TRACKED_CLUSTER"):
                sensitivity.setdefault(parameter, None)
                continue
            if value[3] == "TRACKED_CLUSTER":
                group = cluster_of[row]
                base = float(np.mean([math.log(hz[rows[r]]) for r in group]))
                new = float(np.mean(np.log(value[1])))
                s = (new - base) / math.log(ratio)
            else:
                s = math.log(value[1] / hz[mode]) / math.log(ratio)
            if parameter in sensitivity and sensitivity[parameter] is not None and ratio > 0:
                # several variants of one parameter (G12 ×2, ×3): the smaller step is kept, the other is reported
                continue
            sensitivity[parameter] = s
        table_rows.append(BranchRow(row, mode, hz[mode], per_variant, sensitivity, cluster_of.get(row)))
    return SensitivityTable("baseline", tuple((key, p, r) for key, (_d, p, r) in variants.items()),
                            tuple(table_rows), tuple(cluster_notes))


def d_jacobian(parameters: Mapping[str, float]) -> np.ndarray:
    """∂ ln (D11, D22, D66) / ∂ ln (E1, E2, G12) of a homogeneous orthotropic Kirchhoff plate (h, ν12 fixed).

    D11 = E1 h³ / (12 (1 − ν12 ν21)), D22 = E2 h³ / (12 (1 − ν12 ν21)), ν21 = ν12 E2 / E1, D66 = G12 h³ / 12.
    """
    a = parameters["nu12"] ** 2 * parameters["E2"] / parameters["E1"]  # ν12 ν21
    c = a / (1.0 - a)
    return np.array([[1.0 - c, c, 0.0], [-c, 1.0 + c, 0.0], [0.0, 0.0, 1.0]])


def d_sensitivities(table: SensitivityTable, parameters: Mapping[str, float]) -> dict:
    """Term → {D11, D22, D66}: s_D = s_E · (∂ ln D / ∂ ln E)⁻¹ (exact for the homogeneous plate).

    A confirmed cluster is ONE term ("FE15+FE16"), never two rows; rows without every sensitivity are left out.
    """
    inverse = np.linalg.inv(d_jacobian(parameters))
    out = {}
    for row in table.rows:
        s = [row.sensitivity.get(p) for p in ("E1", "E2", "G12")]
        if any(v is None for v in s):
            continue
        key = "+".join(row.cluster) if row.cluster else row.row_id
        out.setdefault(key, dict(zip(("D11", "D22", "D66"), (np.array(s) @ inverse).tolist())))
    return out


# ----------------------------------------------------------------------------- identifiability (design study)

PROVISIONAL_SETUP = "Σ_setup 0.3 % PROVISIONAL (D-059, D-065); Σ_meas NOT_AVAILABLE for PolyMAX (D-069)"


def _system(sensitivity: Mapping[str, Mapping[str, float]], rows: Sequence[str], parameters: Sequence[str],
            sigma_ln: float, provenance: str):
    from services.practical_identifiability import (ObservationCovariance, ParameterDefinition, ParameterRole,
                                                    assemble_system, build_sensitivity_matrix, diagonal_component)

    definitions = tuple(ParameterDefinition(p, ParameterRole.GLOBAL) for p in parameters)
    matrix = build_sensitivity_matrix({row: {p: sensitivity[row][p] for p in parameters} for row in rows},
                                      list(rows), (), definitions, {p: provenance for p in parameters})
    covariance = ObservationCovariance(matrix.term_ids, (diagonal_component(
        "Sigma_setup", matrix.term_ids, {t: sigma_ln for t in matrix.term_ids}, True, PROVISIONAL_SETUP),))
    return assemble_system(matrix, covariance, ())


@dataclass(frozen=True)
class DesignResult:
    label: str
    parameters: tuple
    rows: tuple
    status: str
    rank: int
    rcond: float
    sd_ln: Optional[tuple]
    correlation: Optional[tuple]
    refusal_reasons: tuple
    labels: tuple = (RESEARCH_ONLY, HYPOTHETICAL_PAIRING)


def design_study(sensitivity: Mapping[str, Mapping[str, float]], rows: Sequence[str], parameters: Sequence[str],
                 label: str, sigma_ln: float = 0.003) -> DesignResult:
    """The M5 practical identifiability of ``parameters`` if ``rows`` were confirmed pairs (a design study only)."""
    from services.practical_identifiability import analyse_practical_identifiability

    system = _system(sensitivity, rows, parameters, sigma_ln, f"{SECANT}; {HYPOTHETICAL_PAIRING}")
    analysis = analyse_practical_identifiability(system)
    sd = None if analysis.sd_ln is None else tuple(float(analysis.sd_ln[p]) for p in parameters)
    correlation = None if analysis.correlation is None else tuple(
        tuple(float(v) for v in row) for row in np.asarray(analysis.correlation))
    return DesignResult(label, tuple(parameters), tuple(rows), str(getattr(analysis.status, "value", analysis.status)),
                        int(analysis.rank), float(analysis.rcond), sd, correlation,
                        tuple(str(r) for r in analysis.refusal_reasons))


def thickness_column(rows: Sequence[str], sensitivity: Mapping[str, Mapping[str, float]],
                     parameters: Sequence[str]) -> dict:
    """s_h of each row for a plate of measured mass (ρh fixed): D ∝ h³ ⇒ s_h = 3 · Σ_j s_Dj (exactly collinear)."""
    return {row: 3.0 * sum(sensitivity[row][p] for p in parameters) for row in rows}


# ----------------------------------------------------------------------------- synthetic twin (SURROGATE)

@dataclass(frozen=True)
class SurrogateForward:
    """Log-linear SURROGATE / RESEARCH_ONLY: f_i(p) = f0_i · Π_j (p_j / p0_j)^S_ij (FE secants; not an FE solve)."""

    rows: tuple
    f0: np.ndarray
    parameters: tuple
    p0: tuple
    s: np.ndarray
    label: str = f"{SURROGATE} / {RESEARCH_ONLY}"

    def __call__(self, p: Mapping[str, float]) -> np.ndarray:
        x = np.log([p[name] / ref for name, ref in zip(self.parameters, self.p0)])
        return self.f0 * np.exp(self.s @ x)


@dataclass(frozen=True)
class TwinResult:
    truth: Mapping[str, float]
    lm_status: str
    estimate: Mapping[str, float]
    recovery_ln: Mapping[str, float]
    analysis_status: str
    sd_ln: Optional[tuple]
    pattern: str
    verdicts: Mapping[str, str]
    reasons: Mapping[str, tuple]
    labels: tuple = (SURROGATE, RESEARCH_ONLY, "SYNTHETIC_GATE")


def run_synthetic_twin(forward: SurrogateForward, truth: Mapping[str, float], fit_rows: Sequence[str],
                       holdout_rows: Sequence[str], start: Mapping[str, float], noise_sd_ln: float = 0.003,
                       seed: int = 20261030, registration: str = "PASS", clusters: Sequence[Sequence[str]] = (),
                       families: Optional[Mapping[str, str]] = None,
                       relabel: Sequence[tuple[str, str]] = ()) -> TwinResult:
    """Recover ``truth`` from synthetic frequencies with the existing LM and evidence chain (SYNTHETIC_GATE).

    The synthetic experiment is the surrogate at ``truth`` with deterministic noise (``synthetic_twin``'s governed
    generator). ``registration`` is the registration guard state ("PASS", "FAIL", "NOT_AVAILABLE"). A confirmed
    cluster in ``clusters`` enters as one term, mean ln f, independent of how its members are labelled.
    ``relabel`` swaps the synthetic measured values of row pairs (an experimental relabelling inside a close group).
    """
    from services.identification_step import LMSettings, parameter_bounds, run_bounded_lm
    from services.identification_uncertainty import ResidualTerm, residual_terms
    from services.identification_verdict import (EvidenceState, GuardEvidence, SandwichG12Evidence, VerdictContext,
                                                 VerdictInputs, compute_evidence_chain, decide_verdicts,
                                                 fitting_pair_mac_evidence)
    from services.practical_identifiability import ParameterRole
    from services.synthetic_twin import deterministic_standard_normal

    index = {row: i for i, row in enumerate(forward.rows)}
    measured = forward(truth) * np.exp([noise_sd_ln * deterministic_standard_normal(seed, row)
                                        for row in forward.rows])
    for left, right in relabel:
        measured[[index[left], index[right]]] = measured[[index[right], index[left]]]
    clustered = {row for group in clusters for row in group}
    terms = [tuple(group) for group in clusters] + [(row,) for row in fit_rows if row not in clustered]

    def residuals(p):
        model = forward(p)
        values = [np.mean(np.log(model[[index[r] for r in term]])) - np.mean(np.log(measured[[index[r] for r in term]]))
                  for term in terms]
        return np.asarray(values) / noise_sd_ln

    term_ids = ["+".join(term) for term in terms]
    sensitivity = {"+".join(term): {p: float(np.mean(forward.s[[index[r] for r in term], j]))
                                    for j, p in enumerate(forward.parameters)} for term in terms}
    system = _system(sensitivity, term_ids, forward.parameters, noise_sd_ln, f"{SURROGATE} Jacobian")
    from services.practical_identifiability import analyse_practical_identifiability

    if analyse_practical_identifiability(system).full_rank:  # SPEC §6 S5: identifiability before optimisation
        bounds = parameter_bounds([(name, ref / 10.0, ref * 10.0)
                                   for name, ref in zip(forward.parameters, forward.p0)])
        lm = run_bounded_lm(residuals, start, bounds, LMSettings(mu_initial=1e-3, mu_decrease=10,
                                                                 max_step_attempts=3, solve_budget=60))
        lm_status, estimate = lm.status.value, dict(lm.parameters)
    else:
        lm_status, estimate = "NOT_RUN (RANK_DEFICIENT before optimisation, SPEC §6 S5)", dict(start)
    families = dict(families or {})
    family = {term_id: families.get(term_id, term_id) for term_id in term_ids}
    fit = residual_terms(term_ids, (), list(residuals(estimate)), family)  # whitened, as the chain expects
    held = []
    for row in holdout_rows:
        value = (math.log(forward(estimate)[index[row]]) - math.log(measured[index[row]])) / noise_sd_ln
        held.append(ResidualTerm(row, (row,), families.get(row, row), float(value)))
    chain = compute_evidence_chain(system, fit, held, estimate, "plate synthetic twin (SURROGATE)")
    provenance = "plate synthetic twin, SURROGATE / RESEARCH_ONLY"
    state = {"PASS": EvidenceState.PASS, "FAIL": EvidenceState.FAIL}.get(registration, EvidenceState.NOT_AVAILABLE)
    inputs = VerdictInputs(
        VerdictContext.SYNTHETIC_GATE, "plate twin", chain.analysis, chain.statistical, chain.pattern, chain.birge,
        chain.robustness, fitting_pair_mac_evidence({t: 0.99 for t in term_ids}, provenance),
        GuardEvidence("registration", state, provenance), GuardEvidence("peak_derived_input", EvidenceState.PASS,
                                                                        provenance),
        GuardEvidence("tracking", EvidenceState.PASS, provenance),
        GuardEvidence("family_consistency", EvidenceState.NOT_AVAILABLE, provenance),
        SandwichG12Evidence(False, EvidenceState.NOT_AVAILABLE, (), {}, provenance), dict(estimate),
        {p: ParameterRole.GLOBAL for p in forward.parameters})
    report = decide_verdicts(inputs)
    sd = None if chain.analysis.sd_ln is None else tuple(float(chain.analysis.sd_ln[p]) for p in forward.parameters)
    return TwinResult(dict(truth), lm_status, dict(estimate),
                      {p: math.log(estimate[p] / truth[p]) for p in forward.parameters},
                      chain.analysis.status.value, sd, chain.pattern.status.value,
                      {p: v.verdict.value for p, v in report.verdicts.items()},
                      {p: tuple(str(r) for r in v.reasons) for p, v in report.verdicts.items()})


# ----------------------------------------------------------------------------- readiness, outcomes, budget, gate

@dataclass(frozen=True)
class ParameterOutcome:
    parameter: str
    outcome: str
    reasons: tuple
    labels: tuple = ()
    value: Optional[float] = None
    assumptions: tuple = ()


def parameter_outcome(parameter: str, production_verdict: Optional[str] = None,
                      research_estimate: Optional[float] = None, assumptions: Sequence[str] = (),
                      reasons: Sequence[str] = ()) -> ParameterOutcome:
    """IDENTIFIABLE_UNDER_GOVERNED_RULES only for a PRODUCTION verdict IDENTIFIED / WIDE; a research estimate is a
    RESEARCH_CANDIDATE_ONLY with its assumptions (never a material constant); otherwise NOT_IDENTIFIABLE."""
    if production_verdict in ("IDENTIFIED", "WIDE"):
        return ParameterOutcome(parameter, IDENTIFIABLE, (f"PRODUCTION verdict {production_verdict}",))
    if research_estimate is not None:
        if not assumptions:
            raise PlateStudyRefusal("a research candidate needs its assumptions listed.")
        return ParameterOutcome(parameter, RESEARCH_CANDIDATE, tuple(reasons),
                                (RESEARCH_ONLY, NOT_A_MATERIAL_PROPERTY, "NOT_TRANSFERABLE"), research_estimate,
                                tuple(assumptions))
    return ParameterOutcome(parameter, NOT_IDENTIFIABLE, tuple(reasons) or ("no confirmed evidence",))


@dataclass(frozen=True)
class Readiness:
    status: str
    confirmed_pairs: tuple
    missing: tuple
    outcomes: tuple


def plate_readiness(registration_verified: bool, confirmed_pairs: Sequence[str] = (),
                    specimen_measurements: bool = False, plate_identity: str = PLATE_IDENTITY,
                    material_axes_traceable: bool = False) -> Readiness:
    """Whether an identification of this plate could start, and each parameter's outcome now (no computation)."""
    missing = []
    if not registration_verified:
        missing.append(f"{NOT_VERIFIED}: the face scanned, the plate edge along each scanner axis and the reference of "
                       "the 45° turn are needed (independent evidence, never MAC or frequency)")
    if not confirmed_pairs:
        missing.append("no confirmed experimental / FE mode pair (needs the registration, MAC ≥ 0.80 on measured DOFs, "
                       "branch tracking)")
    if not specimen_measurements:
        missing.append("mass, plan and a thickness map (9+ points) of THIS plate; " + M11_MEASUREMENTS_NOT_ATTACHED)
    if plate_identity != "ESTABLISHED":
        missing.append("plate identity with the M11 FE model's plate NOT_ESTABLISHED: the FE family is a "
                       "CANDIDATE_FE_REFERENCE")
    missing.append("an FE model of this plate's own suspension (two strings at upper points) is not available; "
                   "free-free is assumed in every FE member")
    missing.append("Σ_meas NOT_AVAILABLE for PolyMAX (D-069); Σ_setup 0.3 % PROVISIONAL; no repeat of this panel")
    missing.append("family consistency NOT_AVAILABLE for a single plate (D-044 blocks PRODUCTION verdicts)")
    reasons = tuple(missing)
    outcomes = [parameter_outcome(p, reasons=reasons) for p in ("D11=D22 (balanced D)", "D66")]
    outcomes.append(parameter_outcome("D11, D22 separately", reasons=(
        "E1 ≠ E2 MUST NOT be enabled without traceable warp / fill orientation (SPEC v1.1 §5.2)",) + reasons
        if not material_axes_traceable else reasons))
    outcomes.append(parameter_outcome("D12", reasons=("D12 only when the full system is FULL_RANK at rcond 1e-3 "
                                                      "(D-051); ν12 0.05 fixed otherwise",) + reasons))
    outcomes.append(parameter_outcome("E1_eff, E2_eff, G12_eff", reasons=(
        "E = 12 (1 − ν12 ν21) D / h³ needs the thickness of this plate (D-052)",) + reasons))
    status = NOT_READY if missing else "READY_FOR_AUTHORISATION"
    return Readiness(status, tuple(confirmed_pairs), reasons, tuple(outcomes))


@dataclass(frozen=True)
class BudgetLine:
    source: str
    ln_sd: Optional[float]
    note: str


def uncertainty_budget(statistical_sd_ln: Optional[float], thickness_cv: Optional[float],
                       mass_rel_sd: Optional[float] = None, setup_sd_ln: Optional[float] = None,
                       model_form_half_range_ln: Optional[float] = None) -> tuple:
    """Separate contributions to ln E_eff (or ln G12_eff) from a D estimate: E ∝ D / h³ at fixed ν (D-052).

    A frequency error of x % is not an x % stiffness error: f ∝ √D, so x % in f is about 2x % in D.
    """
    lines = [BudgetLine("statistical (from the M5 system of the confirmed pairs)", statistical_sd_ln,
                        "NOT_AVAILABLE without confirmed pairs" if statistical_sd_ln is None else "σ basis: " +
                        PROVISIONAL_SETUP),
             BudgetLine("thickness (D ∝ h³ ⇒ 3·cv_h; spatial sd, not divided by √N)",
                        None if thickness_cv is None else 3.0 * thickness_cv,
                        "NOT_AVAILABLE: no thickness record of this plate" if thickness_cv is None else ""),
             BudgetLine("mass (areal mass in the frequency: 1·σ_m)", mass_rel_sd,
                        "NOT_AVAILABLE: no mass record of this plate" if mass_rel_sd is None else ""),
             BudgetLine("experimental conditions (suspension, attachment)", setup_sd_ln,
                        "NOT_AVAILABLE: no repeat of this panel; Σ_setup 0.3 % is PROVISIONAL" if setup_sd_ln is None
                        else ""),
             BudgetLine("model form (leave-one-family-out half range)", model_form_half_range_ln,
                        "NOT_AVAILABLE without confirmed pairs" if model_form_half_range_ln is None else "")]
    return tuple(lines)


ITERATION_PLAN = (
    "1. Close the specimen record: mass, plan, thickness map (9+ points), photographs with a corner mark, and the "
    "owner / lab statement of identity with the M11 plate (or a separate FE model of this plate).",
    "2. Close the physical registration with independent evidence: face scanned, plate edge along each scanner axis, "
    "reference of the 45° turn, scan scale; then the existing guided-registration service records it.",
    "3. Build an FE model of THIS plate (measured plan, thickness and mass; free-free and, as a separate variant, the "
    "two-string suspension) — an Abaqus job: separate HUMAN authorisation.",
    "4. Run the existing comparator with the registration: confirmed pairs MAC ≥ 0.80 on measured DOFs, families, "
    "clusters; freeze the FIT / HOLDOUT rows before any fit.",
    "5. SPEC §6 S4 sensitivities: central ±5 % in ln p for D (balanced E1 = E2) and G12 (2·n_p = 4 jobs) and the "
    "±2.5 % repeat (4 jobs); E1 ≠ E2 only after traceable fibre axes (SPEC v1.1 §5.2) — Abaqus: separate HUMAN gate.",
    "6. Optional: the Stage-A affine basis (*MATRIX GENERATE, 4 jobs) for a balanced plate (D11 = D22) — Abaqus: "
    "separate HUMAN gate.",
    "7. Only then a declared campaign (question, τ_mf, Σ, bounds) and the bounded LM with branch tracking — LM / "
    "campaign: separate HUMAN authorisation.",
)


class IterationNotAuthorised(RuntimeError):
    """The iterative estimation is prepared but not authorised."""


@dataclass(frozen=True)
class IterationGate:
    status: str = ITERATION_NOT_AUTHORISED
    required: str = ("a separate, explicit owner authorisation naming the FE model, the parameters, the solve budget "
                     "and the campaign definition")
    plan: tuple = ITERATION_PLAN


ITERATION_GATE = IterationGate()


def request_iteration(authorisation: Optional[object] = None) -> None:
    """Always refuses in PLATE-ONLY-R1: no real optimisation, FE solve or campaign is run (owner, PLATE-ONLY-R1 §7)."""
    raise IterationNotAuthorised(
        f"{ITERATION_NOT_AUTHORISED}: the iterative estimation needs {ITERATION_GATE.required}; PLATE-ONLY-R1 does not "
        "run it" + ("" if authorisation is None else " (an authorisation object is not accepted in this stage)") + ".")


__all__ = [name for name in dir() if not name.startswith("_")]
