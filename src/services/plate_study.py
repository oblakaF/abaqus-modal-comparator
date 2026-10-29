"""PLATE-ONLY-R1 — research study of the effective bending stiffness of one free-free CFRP plate (RESEARCH_ONLY).

Scope (owner, PLATE-ONLY-R1): one physical specimen, ``PLATE-300x300x1mm``, series
``NEXP29/PLATE300-1MM/S261027-ROTATED``. No sandwich result, no SP-02 / SP-10 / SP-13 data and no material record of
another specimen enters this study. Nothing here is governed evidence, no material constant is released, and no
Abaqus, solver, LM campaign or Auto-ID is run: the iterative estimation is prepared behind a gate that refuses
without a separate authorisation (``request_iteration``).

What the module does, each time with the project's existing services and rules (no new threshold):

- **Sources.** The working source is identified by its SHA-256 (``classify_source``). The M11 session 261016 stays
  history only as an experimental source: it never replaces the working source.
- **Specimen (PLATE-ONLY-R2).** The owner confirmed on 2026-10-30 that the plate of the series 261016 (M11) and
  261027 ROTATED is one and the same specimen (``PLATE_IDENTITY`` HUMAN_CONFIRMED, ``IDENTITY_RECORD``; physical
  identity only). The archived M11 measurements of mass, plan and perimeter thickness are therefore attached to this
  specimen with their date, method and uncertainty (``SPECIMEN_RECORD``); they are not measurements of 27.10.
- **Experiment** (``experimental_summary``): every record of the fitted set, record 1 included; phase collinearity
  (``services.experimental_qc``), measured components, the scan geometry and descriptive shape invariants (rigid-plane
  fraction, saddle and dome curvature fractions, invariant under in-plane rotation). Close groups are the existing
  cluster triggers (3 %): a trigger only.
- **FE family** (``PLATE_FE_FAMILY``): the M11 S4R model and its four controlled variants (R6.6 G12, R6.7 E1 / E2),
  with the SHA-256 of INP, ODB and extraction, and three earlier models with frequencies only. All of them model this
  specimen (``INITIAL_FE_MODEL``): the S4R baseline is the initial model, but its applicability to the 261027 test
  (suspension, excitation, registration) is checked separately (``fe_applicability``) and is NOT_VERIFIED.
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
- **Orientation** (``ORIENTATION_CHAIN``): scanner → physical plate (261027, open) and physical plate → FE (shared
  with M11 now that the specimen is the same; candidates A–D, open). No orientation is chosen by MAC, frequency or
  shape. ``grid_saddle_split`` describes a shape relative to its own scan grid only.

The proximity of record 1 (18.6307 Hz) and the first elastic FE mode (19.07 Hz), or their common twist class, never
confirms a mode pair: no registration and no MAC exist.
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
INITIAL_FE_MODEL = "INITIAL_FE_MODEL_OF_THE_SPECIMEN"  # M11 model of this specimen; applicability checked apart
APPLICABILITY_NOT_VERIFIED = "APPLICABILITY_NOT_VERIFIED"
HUMAN_CONFIRMED = "HUMAN_CONFIRMED"
ARCHIVED = "ARCHIVED_RECORD_OF_THE_SAME_SPECIMEN"
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

# PLATE-ONLY-R2: the owner's statement of 2026-10-30 (a HUMAN record in non-normative documentation; not governed
# evidence). It is final: no further confirmation of the identity is requested.
PLATE_IDENTITY = HUMAN_CONFIRMED
IDENTITY_RECORD = {
    "status": HUMAN_CONFIRMED,
    "statement": "The physical plate of the experimental series 261016 (M11) and 261027 ROTATED is one and the same "
                 "specimen.",
    "by": "owner", "date": "2026-10-30", "provenance": "the owner's supplement to PLATE-ONLY-R2 (2026-10-30)",
    "scope": "physical identity of the specimen only; the 2026-10-18 retry FRF file of the delivery is not named "
             "and is not used",
    "does_not_establish": (
        "a mode pair or a mode correspondence between the sessions or with the FE model",
        "the physical registration of either scan",
        "the applicability of the M11 FE model to the 261027 suspension, excitation and registration",
        "that the plate was unchanged between the archived measurements and 27.10.2026"),
    "governed_evidence": False,
}
IDENTITY_EVIDENCE = (
    ("owner statement 2026-10-30 (PLATE-ONLY-R2)", IDENTITY_RECORD["statement"],
     f"{HUMAN_CONFIRMED}: physical identity only"),
    ("file names", "the 261016 and 261027 files carry the same plate description", "consistent; not needed"),
    ("owner note 2026-10-25 (M11 §21)", "with a changed suspension the first resonance appeared near 19 Hz instead "
     "of about 33 Hz", "information on the test conditions"),
    ("frequencies", "several higher fitted frequencies are within about 1 % between the sessions",
     "never evidence of identity or of a mode pair"),
    ("not established by the identity", "; ".join(IDENTITY_RECORD["does_not_establish"]), "OPEN: checked apart"),
)

# The archived measurements of this specimen (M11 §2, §8, §8.1): one owner's sheet, received 2026-10-21.
MEASURED = "by 2026-10-21 (owner's sheet, M11 §8; day not stated); before the 261027 session"
SPECIMEN_MASS_G = 118.37
MASS_RESOLUTION_G = 0.01  # the last digit of the record (not an instrument uncertainty)
SPECIMEN_PLAN_MM = (301.0, 300.0)  # x × y; FE X = the 301 mm edge (HUMAN, M11 §13.1)
PLAN_RESOLUTION_MM = 1.0  # the last digit of the record
THICKNESS_READINGS_MM = {  # rows = edges 1 top, 2 right, 3 bottom, 4 left, seen from the shaker side in 261016
    1: (0.94, 0.92, 0.94, 0.89, 0.71), 2: (0.79, 0.82, 0.84, 0.81, 0.82), 3: (0.74, 0.89, 0.94, 0.92, 0.92),
    4: (0.93, 0.94, 0.93, 0.92, 0.91)}
SHEET_SHA256 = "df5339cd90fe8d114ad8c62c2e76c13bdb14c91c39d96ccac9b2a9b06bf1caaf"  # photograph, work directory only
# PLATE-ONLY-R2-F1: one reading of the sheet is ambiguous (M11 §8). The archived record keeps it as transcribed; the
# other reading is shown beside it and no value is chosen without an independent confirmation (the sheet and the
# transcription are never changed).
THICKNESS_READING_AMBIGUITY = {
    "edge": 2, "reading": 3, "transcribed_mm": 0.84, "alternative_mm": 0.81,
    "source": "M11 §8: the transcription reads 0.84, which could also be read 0.81",
    "owner_reading": "the owner read it as 0.84 (M11 §8.1): a reading of the same sheet, not an independent "
                     "re-measurement",
    "kept": "the transcribed 0.84; the ambiguity is not resolved and no other value is chosen without an independent "
            "confirmation",
}


def thickness_statistics(readings: Mapping[int, Sequence[float]] = THICKNESS_READINGS_MM) -> dict:
    """Mean, spatial sd (n − 1) and cv of the perimeter readings, and the side means (D-052: never divided by √N)."""
    values = np.array([v for row in readings.values() for v in row], dtype=float)
    sd = float(values.std(ddof=1))
    return {"n": int(values.size), "mean": float(values.mean()), "sd": sd, "cv": sd / float(values.mean()),
            "min": float(values.min()), "max": float(values.max()),
            "side_means": {side: float(np.mean(row)) for side, row in readings.items()}}


def thickness_variants() -> dict:
    """The edge statistics with the ambiguous reading as transcribed and as its alternative (both shown; none
    chosen)."""
    item = THICKNESS_READING_AMBIGUITY
    alternative = {edge: tuple(item["alternative_mm"] if (edge, k) == (item["edge"], item["reading"]) else value
                               for k, value in enumerate(row, start=1))
                   for edge, row in THICKNESS_READINGS_MM.items()}
    return {"as transcribed": thickness_statistics(), "alternative reading": thickness_statistics(alternative)}


def areal_mass_kg_m2(mass_g: float = SPECIMEN_MASS_G, plan_mm: Sequence[float] = SPECIMEN_PLAN_MM) -> float:
    return mass_g * 1e-3 / (plan_mm[0] * plan_mm[1] * 1e-6)


@dataclass(frozen=True)
class ArchivedMeasurement:
    quantity: str
    value: str
    recorded: str
    method: str
    uncertainty: str
    source: str
    status: str = ARCHIVED


_T = thickness_statistics()
SPECIMEN_RECORD = (
    ArchivedMeasurement("mass", f"{SPECIMEN_MASS_G:.2f} g", MEASURED, "scale; the instrument is not stated",
                        f"not stated; the record's resolution is {MASS_RESOLUTION_G} g",
                        f"M11 §2, §8 (sheet photograph SHA-256 {SHEET_SHA256[:12]}…)"),
    ArchivedMeasurement("plan", f"{SPECIMEN_PLAN_MM[0]:.0f} × {SPECIMEN_PLAN_MM[1]:.0f} mm (x × y; FE X = 301 mm)",
                        MEASURED, "the instrument is not stated (M11 §13.6)",
                        f"not stated; the record's resolution is {PLAN_RESOLUTION_MM:.0f} mm", "M11 §2, §8, §13.1"),
    ArchivedMeasurement(
        "thickness", f"{_T['n']} perimeter readings, 5 per edge, {_T['min']:.2f}–{_T['max']:.2f} mm; mean "
        f"{_T['mean']:.3f} mm, spatial sd {_T['sd']:.3f} mm (cv {100 * _T['cv']:.1f} %); edge means "
        + ", ".join(f"{side}: {mean:.3f}" for side, mean in _T["side_means"].items()) + " mm; edge 2, reading 3: "
        "0.84 as transcribed, could be read 0.81 (M11 §8; kept, not resolved)",
        MEASURED, "caliper of 0.01 mm resolution and an electronic caliper (owner, M11 §8.1); about 4.5–6.5 mm from "
        "the edge, the low 0.71 / 0.74 about 0.5 mm from it; the interior is NOT measured",
        "gauge uncertainty not stated; observed edge scatter only (D-052: not divided by √N); with the reading 0.81 "
        "the mean is 0.8745 mm",
        "M11 §8, §8.1, §13.1 (transcription plate_measurements_20261021.json)"),
    ArchivedMeasurement("areal mass", f"{areal_mass_kg_m2():.4f} kg/m²", "derived from the mass and plan above",
                        "mass / (x · y)", "from the mass and plan records (instrument uncertainties not stated)",
                        "derived", "DERIVED_FROM_THE_ARCHIVED_RECORD"),
)
SPECIMEN_RECORD_NOTE = (
    "Archived measurements of the same physical specimen (identity HUMAN_CONFIRMED by the owner on 2026-10-30), "
    "recorded for the M11 session by 2026-10-21. They are NOT new measurements of 27.10.2026; the plate is taken as "
    "unchanged since then, which is not verified.")


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
    status: str = INITIAL_FE_MODEL


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
    "Every member models this specimen (the M11 plate; identity HUMAN_CONFIRMED on 2026-10-30): plan 301 × 300, "
    "mass 118.36 g. The S4R baseline is the INITIAL FE model; its applicability to the 261027 test (suspension, "
    "excitation, registration) is NOT_VERIFIED (fe_applicability).",
    "One homogeneous orthotropic material on global axes, no *Orientation: material axis 1 = FE X (301 mm). The "
    "fibre and weave directions of the real plate are not evidenced, so E1 / E2 are model directions.",
    "Free-free without suspension, shaker or attachment; the 261027 test used rubber bands and strings at two upper "
    "points, and its excitation is not stated.",
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
    saddle_on_grid_axes: Optional[float] = None  # uv: nodal lines along the scan-grid axes (grid_saddle_split)
    saddle_on_grid_diagonals: Optional[float] = None  # u² − v²: nodal lines along the scan-grid diagonals


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


def grid_saddle_split(coordinates: np.ndarray, out_of_plane: np.ndarray, grid_angle_deg: float) -> tuple[float, float]:
    """The saddle energy fractions about the shape's OWN scan grid: (uv, u² − v²) in the grid axes (u, v).

    uv has its nodal lines along the grid axes, u² − v² along the grid diagonals; their sum is the saddle fraction of
    ``shape_invariants``. It relates a shape to the measurement grid only: it relates nothing to the plate edges or the
    FE axes, chooses no orientation and pairs nothing (PLATE-ONLY-R2, descriptive).
    """
    xy = np.asarray(coordinates, dtype=float)[:, :2]
    xy = (xy - xy.mean(axis=0)) / max(np.ptp(xy, axis=0).max(), 1e-12)
    angle = math.radians(grid_angle_deg)
    uv = xy @ np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
    u, v = uv[:, 0], uv[:, 1]
    w = _aligned_real(out_of_plane)
    q, _ = np.linalg.qr(np.column_stack([np.ones(len(u)), u, v, u * u - v * v, 2 * u * v, u * u + v * v]))
    energy = float(w @ w) or 1.0
    return float((q[:, 4] @ w) ** 2) / energy, float((q[:, 3] @ w) ** 2) / energy


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
    coordinates = np.asarray(modes[0].coordinates, dtype=float)
    centred = coordinates - coordinates.mean(axis=0)
    normal = np.linalg.svd(centred, full_matrices=False)[2][2]
    spacing, angle = _grid(coordinates)
    records = []
    for position, mode in enumerate(modes, start=1):
        vectors = np.asarray(mode.vectors)
        measured = [k for k in range(3) if np.any(np.abs(vectors[:, k]) > 0)]
        mpc = _phase_collinearity(vectors[:, measured]) if measured else None
        rigid, saddle, dome = shape_invariants(mode.coordinates, vectors[:, 2])
        on_axes, on_diagonals = grid_saddle_split(mode.coordinates, vectors[:, 2], angle)
        records.append(ExperimentalRecord(position, int(mode.number), float(mode.frequency_hz), mpc,
                                          "".join("XYZ"[k] for k in measured), len(vectors), rigid, saddle, dome,
                                          "FITTED (dataset 55)" if fitted else "PROVISIONAL FRF (dataset 58)",
                                          on_axes, on_diagonals))
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
    labels: tuple = (RESEARCH_ONLY, INITIAL_FE_MODEL)

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
                    specimen_record: Optional[Sequence[ArchivedMeasurement]] = SPECIMEN_RECORD,
                    plate_identity: str = PLATE_IDENTITY, material_axes_traceable: bool = False,
                    fe_applicability_verified: bool = False, interior_thickness_measured: bool = False) -> Readiness:
    """Whether an identification of this plate could start, and each parameter's outcome now (no computation)."""
    missing = []
    if not registration_verified:
        missing.append(f"{NOT_VERIFIED}: the face scanned, the plate edge along each scanner axis and the reference of "
                       "the 45° turn are needed (independent evidence, never MAC, frequency or shape)")
    if not confirmed_pairs:
        missing.append("no confirmed experimental / FE mode pair (needs the registration, MAC ≥ 0.80 on measured DOFs, "
                       "branch tracking); the proximity of 18.6307 Hz and 19.07 Hz confirms none")
    if plate_identity not in (HUMAN_CONFIRMED, "ESTABLISHED"):
        missing.append("the identity of the plate with the M11 FE model's plate is not established")
    quantities = {item.quantity for item in specimen_record or ()}
    if not {"mass", "plan", "thickness"} <= quantities:
        missing.append("mass, plan and thickness of this specimen are not recorded")
    if not fe_applicability_verified:
        missing.append(f"{APPLICABILITY_NOT_VERIFIED}: the initial FE model (M11, free-free) is not checked against "
                       "the 261027 suspension (rubber bands and strings at two upper points) and excitation (not "
                       "stated); an FE variant with the suspension is an Abaqus job (separate HUMAN gate)")
    missing.append("Σ_meas NOT_AVAILABLE for PolyMAX (D-069); Σ_setup 0.3 % PROVISIONAL; no repeat of this panel "
                   "under one protocol (261016 and 261027 differ in suspension and grid: not a D-053 repeat)")
    missing.append("family consistency NOT_AVAILABLE for a single plate (D-044 blocks PRODUCTION verdicts)")
    reasons = tuple(missing)
    thickness = (() if interior_thickness_measured else (
        f"E = 12 (1 − ν12 ν21) D / h³ (D-052): the thickness is known only at the edges ({_T['n']} archived "
        f"readings, observed cv {100 * _T['cv']:.1f} %); there is no thickness map of the whole plate, so the real "
        f"uncertainty of E / G is UNKNOWN (3 × CV_edges ≈ {300 * _T['cv']:.0f} % is illustrative only)",))
    outcomes = [parameter_outcome(p, reasons=reasons) for p in ("D11=D22 (balanced D)", "D66")]
    outcomes.append(parameter_outcome("D11, D22 separately", reasons=(
        "E1 ≠ E2 MUST NOT be enabled without traceable warp / fill orientation (SPEC v1.1 §5.2)",) + reasons
        if not material_axes_traceable else reasons))
    outcomes.append(parameter_outcome("D12", reasons=("D12 only when the full system is FULL_RANK at rcond 1e-3 "
                                                      "(D-051); ν12 0.05 fixed otherwise",) + reasons))
    outcomes.append(parameter_outcome("E1_eff, E2_eff, G12_eff", reasons=thickness + reasons))
    status = NOT_READY if missing else "READY_FOR_AUTHORISATION"
    return Readiness(status, tuple(confirmed_pairs), reasons, tuple(outcomes))


@dataclass(frozen=True)
class BudgetLine:
    source: str
    ln_sd: Optional[float]  # an established contribution only; None when it is not known
    note: str
    illustrative_ln_sd: Optional[float] = None  # PLATE-ONLY-R2-F1: an illustration, never the real uncertainty


def uncertainty_budget(statistical_sd_ln: Optional[float], thickness_cv: Optional[float],
                       mass_rel_sd: Optional[float] = None, setup_sd_ln: Optional[float] = None,
                       model_form_half_range_ln: Optional[float] = None, thickness_note: str = "",
                       mass_note: str = "") -> tuple:
    """Separate contributions to ln E_eff (or ln G12_eff) from a D estimate: E ∝ D / h³ at fixed ν (D-052).

    A frequency error of x % is not an x % stiffness error: f ∝ √D, so x % in f is about 2x % in D.
    """
    lines = [BudgetLine("statistical (from the M5 system of the confirmed pairs)", statistical_sd_ln,
                        "NOT_AVAILABLE without confirmed pairs" if statistical_sd_ln is None else "σ basis: " +
                        PROVISIONAL_SETUP),
             BudgetLine("thickness (D ∝ h³ ⇒ 3·cv_h; spatial sd, not divided by √N)",
                        None if thickness_cv is None else 3.0 * thickness_cv,
                        thickness_note or ("NOT_AVAILABLE: no thickness record" if thickness_cv is None else "")),
             BudgetLine("mass (areal mass in the frequency: 1·σ_m)", mass_rel_sd,
                        mass_note or ("NOT_AVAILABLE: no mass record" if mass_rel_sd is None else "")),
             BudgetLine("experimental conditions (suspension, attachment)", setup_sd_ln,
                        "NOT_AVAILABLE: no repeat of this panel; Σ_setup 0.3 % is PROVISIONAL" if setup_sd_ln is None
                        else ""),
             BudgetLine("model form (leave-one-family-out half range)", model_form_half_range_ln,
                        "NOT_AVAILABLE without confirmed pairs" if model_form_half_range_ln is None else "")]
    return tuple(lines)


def specimen_budget() -> tuple:
    """The budget with the archived record of this specimen. PLATE-ONLY-R2-F1: the edge scatter gives only an
    illustrative 3 × CV_edges; the real thickness contribution to E / G is UNKNOWN (no map of the whole plate)."""
    variants = thickness_variants()
    cvs = [v["cv"] for v in variants.values()]
    lines = list(uncertainty_budget(None, None, thickness_note=(
        f"UNKNOWN: no thickness map of the whole plate. Observed edge scatter ({_T['n']} archived readings, "
        f"2026-10-21): cv {100 * cvs[0]:.1f} % as transcribed, {100 * cvs[1]:.1f} % with the reading 0.81. "
        f"3 × CV_edges = {300 * cvs[0]:.1f} % ({300 * cvs[1]:.1f} %) is ILLUSTRATIVE, not the real uncertainty of "
        "E / G; gauge uncertainty not stated"), mass_note=(
        f"archived mass {SPECIMEN_MASS_G} g (2026-10-21); the scale uncertainty is not stated (the record's "
        f"resolution {MASS_RESOLUTION_G} g is {100 * MASS_RESOLUTION_G / SPECIMEN_MASS_G:.3f} %); a D estimate "
        "uses the areal mass and needs no thickness")))
    lines[1] = BudgetLine(lines[1].source, None, lines[1].note, illustrative_ln_sd=3.0 * cvs[0])
    return tuple(lines)


def thickness_rows() -> tuple:
    """(item, value, status) of the thickness record for the page and the report (PLATE-ONLY-R2-F1)."""
    v = thickness_variants()
    t, a = v["as transcribed"], v["alternative reading"]
    item = THICKNESS_READING_AMBIGUITY
    return (
        ("edge readings (archived)", f"{t['n']} at the edges, {t['min']:.2f}–{t['max']:.2f} mm; {MEASURED}", ARCHIVED),
        ("ambiguous reading", f"edge {item['edge']}, reading {item['reading']}: {item['transcribed_mm']} as "
         f"transcribed, could be read {item['alternative_mm']} ({item['source']}); {item['owner_reading']}",
         "AMBIGUOUS: kept as transcribed, not resolved"),
        ("observed edge scatter", f"mean {t['mean']:.4f} / {a['mean']:.4f} mm, sd {t['sd']:.4f} / {a['sd']:.4f} mm, "
         f"CV_edges {100 * t['cv']:.1f} % / {100 * a['cv']:.1f} % (as transcribed / with 0.81)",
         "OBSERVED (edges only)"),
        ("3 × CV_edges", f"{300 * t['cv']:.1f} % / {300 * a['cv']:.1f} % in ln E / ln G12",
         "ILLUSTRATIVE: not the real uncertainty"),
        ("thickness map of the whole plate", "not measured (the interior is unknown)", "NOT_MEASURED"),
        ("real uncertainty of E / G", "unknown", "UNKNOWN"),
        ("±10 % target", "an engineering goal", "NOT_ACHIEVED"),
    )


def effective_moduli_from_d(d11: float, d22: float, d66: float, h: float, nu12: float) -> dict:
    """E1, E2, G12 of the equivalent homogeneous plate from D11, D22, D66 (N·mm) and h (mm): the exact inverse of
    D11 = E1 h³ / (12 (1 − ν12 ν21)), D22 = E2 h³ / (12 (1 − ν12 ν21)), D66 = G12 h³ / 12 with ν21 = ν12 E2 / E1.
    Prepared for a later, authorised estimate; it is applied to no value here (D-052: h³ stays explicit)."""
    a = nu12 * nu12 * d22 / d11  # ν12 ν21 (E2 / E1 = D22 / D11)
    return {"E1": 12.0 * (1.0 - a) * d11 / h ** 3, "E2": 12.0 * (1.0 - a) * d22 / h ** 3,
            "G12": 12.0 * d66 / h ** 3}


def plate_d(parameters: Mapping[str, float]) -> Optional[dict]:
    """D11, D22, D66 (N·mm) of an FE member's assumed constants (model inputs, not measurements or estimates); None
    for a member without one uniform thickness."""
    if not math.isfinite(parameters.get("h", float("nan"))):
        return None
    a = parameters["nu12"] ** 2 * parameters["E2"] / parameters["E1"]
    h3 = parameters["h"] ** 3
    return {"D11": parameters["E1"] * h3 / (12 * (1 - a)), "D22": parameters["E2"] * h3 / (12 * (1 - a)),
            "D66": parameters["G12"] * h3 / 12}


# ----------------------------------------------------------------------------- applicability and orientation (R2)

CONSISTENT = "CONSISTENT_WITH_THE_RECORD"
TEST_261027 = {
    "rotation": "45° clockwise as viewed from the Polytec system (lab note); not an FE rotation",
    "suspension": "rubber bands and strings at two upper points along the nodal line of the first mode (lab note); "
                  "stiffness, lengths and exact points are not recorded",
    "excitation": "not stated in the lab note (shaker attachment or non-contact excitation unknown)",
    "low_frf_peaks_hz": (3.44, 10.31, 12.5),  # auxiliary FRF (PROVISIONAL), probably the suspension
}
TEST_261016 = "four corner straps and a shaker stinger near the bottom edge (HUMAN, M11 §13.3)"
# PLATE-ONLY-R2 research (grid_saddle_split of record 1 in each session; review folder PLATE_ONLY_R2_REVIEW)
SESSION_TWIST = {"261027": (18.6307, 0.988), "261016": (33.4491, 0.947)}  # (measured Hz, uv fraction) of record 1
# PLATE-ONLY-R2-F1: the difference of the two series is a suspicion, never an established effect of the setup
SETUP_DEPENDENCE_SUSPECTED = "SETUP_DEPENDENCE_SUSPECTED"
MODE_IDENTITY_NOT_VERIFIED = "MODE_IDENTITY_NOT_VERIFIED"
SESSION_DIFFERENCE = f"{SETUP_DEPENDENCE_SUSPECTED} / {MODE_IDENTITY_NOT_VERIFIED}"


@dataclass(frozen=True)
class ApplicabilityCheck:
    aspect: str
    fe: str
    test: str
    state: str
    note: str


def fe_plan(dataset) -> tuple:
    """The in-plane extent (x, y) of an FE dataset's geometry, in its own units."""
    xy = np.asarray(dataset.sorted_modes()[0].coordinates, dtype=float)[:, :2]
    return tuple(float(v) for v in np.ptp(xy, axis=0))


def fe_applicability(member: FEMember, fe_plan_mm: Optional[Sequence[float]] = None,
                     first_record_hz: Optional[float] = None, first_fe_hz: Optional[float] = None) -> tuple:
    """The initial FE model against the archived record of this specimen and the 261027 test (no computation).

    Only the record's resolution is used to call a value consistent; nothing here is a new criterion. The model is not
    applicable to the 261027 test until the suspension, excitation and registration are checked.
    """
    p = member.parameters
    h = p.get("h", float("nan"))
    checks = []
    if fe_plan_mm is None:
        checks.append(ApplicabilityCheck("plan", "—", "301 × 300 mm", "UNKNOWN", "the FE geometry was not read"))
    else:
        plan = tuple(float(v) for v in fe_plan_mm[:2])
        ok = all(abs(a - b) <= PLAN_RESOLUTION_MM for a, b in zip(plan, SPECIMEN_PLAN_MM))
        checks.append(ApplicabilityCheck("plan", " × ".join(f"{v:g}" for v in plan) + " (FE units)",
                                         "301 × 300 mm (archived)", CONSISTENT if ok else "DIFFERS",
                                         f"within the record's resolution {PLAN_RESOLUTION_MM:.0f} mm" if ok else
                                         "the FE plan is not the specimen's"))
        if math.isfinite(h):
            mass = p["rho"] * h * plan[0] * plan[1] * 1e6  # t/mm³ · mm · mm² → g
            ok = abs(mass - SPECIMEN_MASS_G) <= MASS_RESOLUTION_G
            checks.append(ApplicabilityCheck(
                "mass", f"{mass:.2f} g (ρ·h·A)", f"{SPECIMEN_MASS_G} g (archived)", CONSISTENT if ok else "DIFFERS",
                "the model's ρ was set from this mass at h 0.875 mm (M11 §2)" if ok else
                f"{100 * (mass / SPECIMEN_MASS_G - 1):+.2f} % against the record"))
    checks.append(ApplicabilityCheck(
        "thickness", f"uniform {h:.3f} mm" if math.isfinite(h) else "nodal thickness",
        f"perimeter mean {_T['mean']:.3f} mm, cv {100 * _T['cv']:.1f} %, edge means "
        f"{min(_T['side_means'].values()):.3f}–{max(_T['side_means'].values()):.3f} mm", "NOT_VERIFIED",
        "the interior is not measured; uniform thickness is an assumption (the wedge member is one alternative)"))
    checks.append(ApplicabilityCheck("material axes", "one orthotropic material on the global axes",
                                     "fibre and weave directions not evidenced", "NOT_VERIFIED",
                                     "E1 ≠ E2 is blocked without traceable axes (SPEC v1.1 §5.2)"))
    ratio = (f"; the highest is {max(TEST_261027['low_frf_peaks_hz']) / first_record_hz:.2f} of record 1"
             if first_record_hz else "")
    checks.append(ApplicabilityCheck(
        "suspension", "free-free (no springs, masses or strings)", TEST_261027["suspension"], "NOT_VERIFIED",
        "SPEC §15 asks for a soft suspension; the auxiliary FRF has peaks at "
        + ", ".join(f"{v:g}" for v in TEST_261027["low_frf_peaks_hz"]) + " Hz (PROVISIONAL, probably the "
        f"suspension){ratio}: softness is not demonstrated and the effect is not quantified"))
    checks.append(ApplicabilityCheck("excitation", "none", TEST_261027["excitation"], "UNKNOWN",
                                     "SPEC §15: the shaker attachment mass in the model, or non-contact excitation"))
    (f27, uv27), (f16, uv16) = SESSION_TWIST["261027"], SESSION_TWIST["261016"]
    checks.append(ApplicabilityCheck(
        "series difference: mode identity", "—", f"record 1 measured at {f27} Hz (261027) and {f16} Hz (261016)",
        MODE_IDENTITY_NOT_VERIFIED,
        f"measured: record 1 at {f27} Hz in 261027 and at {f16} Hz in 261016; descriptively both are twists about "
        f"their own scan grid (uv fraction {uv27} and {uv16}). Whether they are the same mode is NOT verified (no "
        "registration, no MAC between the series). No cross-series mode pair"))
    checks.append(ApplicabilityCheck(
        "series difference: cause", "—", f"261016: {TEST_261016}; 261027: the two-point suspension",
        SETUP_DEPENDENCE_SUSPECTED,
        "the cause of the difference is NOT established: a dependence on the test setup (suspension, shaker "
        "attachment) is suspected, not proven. Not a Σ_setup repeat (D-053)"))
    checks.append(ApplicabilityCheck(
        "registration", "FE X = 301 mm edge, +Z shell normal", "scan rotated 45°; face and edges unknown",
        NOT_VERIFIED, "scanner → plate (261027) open; plate → FE: candidates A–D, the owner's choice pending "
        "(M11 §14.5); see the orientation chain"))
    if first_record_hz and first_fe_hz:
        checks.append(ApplicabilityCheck(
            "mode correspondence", f"{first_fe_hz:.2f} Hz (first elastic FE mode)", f"{first_record_hz:.4f} Hz "
            "(record 1)", "NOT_ESTABLISHED", f"{100 * (first_fe_hz / first_record_hz - 1):+.1f} %: frequency "
            "proximity and a common shape class are NOT a mode pair (no registration, no MAC)"))
    return tuple(checks)


@dataclass(frozen=True)
class OrientationLink:
    link: str
    known: str
    open: str
    state: str


ORIENTATION_CHAIN = (
    OrientationLink(
        "scanner (261027 ROTATED) → physical plate",
        "scan grid 17 × 17 at about 45° in the camera frame; the lab turned the plate 45° clockwise as viewed from the "
        "Polytec; distance 1.15 m; the Polytec node numbering changes with the rotation (lab note)",
        "the reference orientation of the 45° turn; the face towards the Polytec (marked or unmarked); which numbered "
        "edge lies along each grid side; the scan-to-edge offsets (no camera frame of this plate in the delivery)",
        NOT_VERIFIED),
    OrientationLink(
        "physical plate → FE model (M11, same specimen)",
        "FE X = 301 mm edge, Y = 300 mm edge; edges 1–4 with their thickness rows and the marked face (HUMAN, "
        "M11 §13.1); four candidates A–D of the FE axes (M11 §14.2)",
        "which of A–D (one picture chosen by the owner, M11 §14.5), hence FE +Z against a physical face; this link "
        "is shared with M11 because the specimen is the same",
        "PENDING (owner's choice A–D)"),
    OrientationLink(
        "scanner (261016, M11) → physical plate",
        "diagnostic reconstruction W301xH300 with three deviations not accepted (M11 §13.4, §14.3)",
        "not transferable to 261027: another session, grid and node numbering", "HISTORY_ONLY"),
)
_EDGES = _T["side_means"]
ORIENTATION_NOTES = (
    "No orientation is chosen by MAC, frequency or shape; every candidate stays open until independent evidence "
    "closes it.",
    "Together the two open links leave 8 maps of the 261027 scan axes into the FE axes (the proper symmetries of a "
    "square: 4 in-plane turns × 2 faces); none is chosen.",
    f"Why it matters even for a balanced D: the edge means {min(_EDGES.values()):.3f} (edge "
    f"{min(_EDGES, key=_EDGES.get)}) and {max(_EDGES.values()):.3f} mm (edge {max(_EDGES, key=_EDGES.get)}) differ by "
    f"about {100 * (max(_EDGES.values()) / min(_EDGES.values()) - 1):.0f} %; with D ∝ h³ the plate is not physically "
    "symmetric, so the near-degenerate bending pair and a later E1 ≠ E2 depend on the registration.",
)


ITERATION_PLAN = (
    "1. Specimen record: identity HUMAN_CONFIRMED (owner, 2026-10-30); the archived mass, plan and 20 perimeter "
    "thickness readings (2026-10-21) are attached. Still open, for E / G only: an interior thickness map.",
    "2. Close the physical registration with independent evidence: for 261027 the face towards the Polytec, the "
    "numbered edge along each grid side (or the reference of the 45° turn) and the scan scale; for the FE side the "
    "owner's picture A–D (M11 §14.5); then the existing guided-registration service records it.",
    "3. Check the initial FE model against the 261027 test: the excitation, and an FE variant with the two-point "
    "suspension (and a shaker attachment if one was used) — an Abaqus job: separate HUMAN authorisation.",
    "4. Run the existing comparator with the registration: confirmed pairs MAC ≥ 0.80 on measured DOFs, families, "
    "clusters; freeze the FIT / HOLDOUT rows before any fit.",
    "5. SPEC §6 S4 sensitivities: central ±5 % in ln p for D (balanced E1 = E2) and G12 (2·n_p = 4 jobs) and the "
    "±2.5 % repeat (4 jobs); E1 ≠ E2 only after traceable fibre axes (SPEC v1.1 §5.2) — Abaqus: separate HUMAN gate.",
    "6. Optional: the Stage-A affine basis (*MATRIX GENERATE, 4 jobs) for a balanced plate (D11 = D22) — Abaqus: "
    "separate HUMAN gate.",
    "7. Only then a declared campaign (question, τ_mf, Σ, bounds) and the bounded LM with branch tracking — LM / "
    "campaign: separate HUMAN authorisation. The D route needs the areal mass only; E / G add the thickness "
    "contribution (D-052), which needs a thickness map of the whole plate.",
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
    """Always refuses in PLATE-ONLY-R1 / R2: no real optimisation, FE solve or campaign is run (owner, PLATE-ONLY-R1
    §7; PLATE-ONLY-R2 item 6)."""
    raise IterationNotAuthorised(
        f"{ITERATION_NOT_AUTHORISED}: the iterative estimation needs {ITERATION_GATE.required}; PLATE-ONLY-R1 / R2 do "
        "not run it" + ("" if authorisation is None else " (an authorisation object is not accepted in this stage)")
        + ".")


__all__ = [name for name in dir() if not name.startswith("_")]
