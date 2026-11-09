"""REAL-FIT.R1: research-only frequency tuning of the CFRP input properties of an Abaqus plate model (no Qt, no Abaqus).

The owner asked to refine the ASSUMED orthotropic constants of the M11 plate model (``CFRP_S4R_0875_FreeFree.inp``) against
the measured PolyMAX frequencies. This module is a separate research tool. It does not use, change or bypass the governed
inverse workflow (``plate_material_workflow``), whose refusal of real data stays as it is, and it issues no material
property. Every result carries ``RESULT_LABEL``.

What it does, in order:

1. Reads the model's own inputs from the INP text: the material (``*Elastic, type=ENGINEERING CONSTANTS`` or ``LAMINA``),
   ``*Density``, the ``*Shell Section`` thickness and the plan extents of the part nodes. Nothing is assumed in code.
2. Converts them to homogeneous Kirchhoff bending stiffnesses: one orthotropic layer on the global axes (the INP has no
   ``*Orientation`` and no layup), plane stress, ``Q11 = E1/(1 - nu12 nu21)``, ``Q22 = E2/(1 - nu12 nu21)``,
   ``Q12 = nu12 E2/(1 - nu12 nu21)``, ``Q66 = G12``, ``nu21 = nu12 E2/E1`` and ``Dij = Qij t^3/12``. Transverse shear
   (G13, G23) and E3 are not in this plate theory: they stay as the INP has them.
3. Solves the free plate with the existing Kirchhoff-Ritz forward model (``plate_ritz_forward.solve_ritz``).
4. Compares that surrogate spectrum, by rank, with the elastic FE frequencies, when the caller has them classified
   by shape (the comparator's rigid-body criterion, P-2); without that classification no FE rank comparison is made.
5. Starts from the data alone (REAL-FIT.R1.F1): a common modulus scaled to the measured frequencies and one
   linearized split, with bounds around that start; the INP values are shown for comparison only. Then fits
   the selected experimental frequencies by bounded least squares on signed residuals ln(f_model / f_exp), under ONE
   declared correspondence hypothesis: the k-th fitted experimental frequency against a stated elastic rank of the
   surrogate (by default the same rank). This is a frequency hypothesis, never a mode pair.
6. Keeps HOLDOUT records out of the fit and reports their prediction, and reports the sensitivities d ln f / d ln p, the
   singular values, the condition number, the parameter correlation, active bounds and a check from several starts.

A candidate is issued only when the fit is numerically supported (converged, full practical rank, no active bound, the
starts agree). The candidate values are surrogate (Ritz) results: they are proposals for a new Abaqus solve, not FE results.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
import hashlib
import json
import math
from pathlib import Path
import re
import threading
from typing import Callable, Mapping, Optional, Sequence

import numpy as np
from scipy.optimize import least_squares

from domain.plate_material_problem import PlateBendingParameters, PlateGeometry
from services.plate_ritz_forward import RitzNumericalConfig, solve_ritz

RESULT_LABEL = "EXPLORATORY_FE_INPUT_CANDIDATE — NOT_A_MATERIAL_PROPERTY — NOT_VALIDATED_IN_ABAQUS"
SCHEMA = "research-frequency-tuning/1"
TIED, FREE = "E1=E2, G12", "E1, E2, G12"
PARAMETERIZATIONS = {TIED: ("E", "G12"), FREE: ("E1", "E2", "G12")}
RANK_ORDER, DECLARED = "RANK_ORDER_SPECTRUM", "DECLARED_CORRESPONDENCE"
SUPPORTED, NOT_IDENTIFIABLE, AT_BOUND, NOT_CONVERGED, STARTS_DISAGREE, CANCELLED = (
    "NUMERICALLY_SUPPORTED", "NOT_IDENTIFIABLE", "PARAMETER_AT_BOUND", "NOT_CONVERGED", "STARTS_DISAGREE", "CANCELLED")
MIRROR = "E1_E2_AXIS_ASSIGNMENT_NOT_IDENTIFIABLE"  # two minima with E1 and E2 exchanged: which plate axis is stiff is open
MIRROR_TOLERANCE = 0.05  # relative difference for "exchanged" (numerical policy)
MISFIT_RMS = 0.02  # FIT residual RMS (ln f) above which the parameterization does not reproduce the spectrum (diagnostic)
FIT, HOLDOUT, EXCLUDED = "FIT", "HOLDOUT", "EXCLUDED"
PRACTICAL_RANK_RATIO = 1.0e-3  # a singular value below this share of the largest does not count (numerical policy)
CONDITION_LIMIT = 1.0e3  # above it the parameters are reported as poorly distinguished (numerical policy)
START_AGREEMENT = 1.0e-3  # relative spread of the fitted parameters over the starts (numerical policy)
ASSUMPTIONS = (
    "The Kirchhoff-Ritz plate is a surrogate of the S4R shell model: no transverse shear, no rotary inertia.",
    "One homogeneous orthotropic layer on the global axes, as the INP defines it (no *Orientation, no layup).",
    "Thickness, density and nu12 are held at the INP values; E3, nu13, nu23, G13 and G23 are not part of the fit.",
    "The plate is free-free, as in the model. The test hung the plate on two strings at about 45 degrees with a shaker "
    "behind it; that suspension angle is not a fibre direction, and support stiffness is not in the model.",
    "That the 27 October test plate is the M11 model's specimen is an ASSUMPTION; it is not verified.",
    "Experimental frequencies are matched to the surrogate by a declared rank hypothesis, not by mode identity.",
)


class TuningRefused(ValueError):
    """The inputs cannot support the requested tuning; the message says why."""


# ---------------------------------------------------------------------------------------------- the model's own inputs


@dataclass(frozen=True)
class AbaqusPlateInputs:
    inp_path: str
    inp_sha256: str
    material: str
    elastic_type: str
    E1: float  # MPa (N/mm^2), as written
    E2: float
    E3: Optional[float]
    nu12: float
    nu13: Optional[float]
    nu23: Optional[float]
    G12: float
    G13: Optional[float]
    G23: Optional[float]
    density_t_mm3: float
    thickness_mm: float
    a_mm: float
    b_mm: float
    has_orientation: bool

    @property
    def mass_g(self) -> float:
        return self.density_t_mm3 * self.thickness_mm * self.a_mm * self.b_mm * 1.0e6

    def geometry(self) -> PlateGeometry:
        return PlateGeometry.from_units(self.a_mm, self.b_mm, "mm", surface_mass_kg_m2=self.density_t_mm3 * 1.0e12 * self.thickness_mm * 1.0e-3,
                                        thickness=self.thickness_mm)


def _numbers(lines: Sequence[str]) -> list:
    out = []
    for line in lines:
        out += [float(item) for item in line.replace(" ", "").split(",") if item.strip()]
    return out


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------------------------- model compatibility
# ABM-REAL-INPUT-1: what the INP is, read from its text, and whether this tool can use it. Nothing is converted or assumed:
# a solid model is not turned into a shell, no thickness is taken from the mesh, and *Include files are named, never read.

COMPATIBLE, SOLID_MODEL, MIXED_ELEMENTS, NO_SHELL_ELEMENTS, IN_INCLUDE, MISSING_DEFINITION, UNSUPPORTED_MATERIAL, \
    COMPOSITE_LAYUP, MORE_THAN_ONE = ("COMPATIBLE_SHELL_MODEL", "SOLID_MODEL", "MIXED_ELEMENT_FAMILIES", "NO_SHELL_ELEMENTS",
                                      "DEFINITIONS_IN_INCLUDED_FILE", "MISSING_DEFINITION", "UNSUPPORTED_MATERIAL_MODEL",
                                      "COMPOSITE_LAYUP", "MORE_THAN_ONE_DEFINITION")
_MATERIAL_OPTIONS = ("*elastic", "*density", "*damping", "*expansion", "*plastic", "*hyperelastic", "*hyperfoam",
                     "*viscoelastic", "*conductivity", "*specific heat", "*depvar", "*user material", "*user defined field")
_NOT_MODAL = ("*plastic", "*hyperelastic", "*hyperfoam", "*viscoelastic", "*user material")
SOLID_BACKEND_NOTE = ("Research Tuning of a solid model needs a different forward model, a solid FE solve of every candidate; "
                      "this program has none that runs offline, and an Abaqus solve needs the owner's authorisation.")


@dataclass(frozen=True)
class InpCompatibility:
    inp_path: str
    verdict: str
    reason: str  # one or two sentences, user-readable
    facts: tuple  # (what, as read from the INP)
    includes: tuple  # (file named by *Include, found beside the INP)

    @property
    def supported(self) -> bool:
        return self.verdict == COMPATIBLE


class InpNotSupported(TuningRefused):
    """The INP is not a model this tool reads; ``report`` says what it is and why."""

    def __init__(self, report: InpCompatibility):
        super().__init__(report.reason)
        self.report = report


def element_family(element_type: str) -> str:
    kind = element_type.strip().upper()
    if kind.startswith("SC"):
        return "continuum shell"
    if re.match(r"S\d|STRI", kind):
        return "shell"
    if kind.startswith("C3D"):
        return "solid"
    return "other"


def _option(text: str, name: str) -> str:
    found = re.search(name + r"\s*=\s*(\"[^\"]*\"|[^,]+)", text, re.I)
    return found.group(1).strip().strip('"') if found else ""


def _count(lines: Sequence[str], start: int) -> int:
    count, previous = 0, ""
    for line in lines[start + 1:]:
        if line.startswith("*"):
            break
        if line.strip() and not previous.rstrip().endswith(","):
            count += 1
        previous = line if line.strip() else previous
    return count


def _inspect(path: Path, lines: Sequence[str], keyword: Sequence[tuple], data_after: Callable) -> InpCompatibility:
    def low(k):
        return k.lower()

    elements = {}
    for i, k in keyword:
        if low(k).startswith("*element") and not low(k).startswith("*element output"):
            kind = _option(k, "type").upper() or "?"
            elements[kind] = elements.get(kind, 0) + _count(lines, i)
    families = {element_family(kind) for kind in elements}
    sections = [k for _i, k in keyword if re.match(r"\*\w[\w ]*section\b", low(k)) and "controls" not in low(k)]
    shell_sections = [k for k in sections if low(k).startswith("*shell section")]
    solid_sections = [k for k in sections if low(k).startswith("*solid section")]
    includes = []
    for _i, k in keyword:
        if low(k).startswith("*include"):
            name = _option(k, "input")
            includes.append((name, bool(name) and (path.parent / name).is_file()))
    materials, current = [], None
    for i, k in keyword:
        if low(k).startswith("*material"):
            current = {"name": _option(k, "name"), "options": []}
            materials.append(current)
        elif current is not None and low(k).startswith(_MATERIAL_OPTIONS):
            current["options"].append((k, _numbers(data_after(i))))
        else:
            current = None
    nodes = []
    for i, k in keyword:
        if low(k) == "*node" or low(k).startswith("*node,"):
            for line in data_after(i):
                parts = [p for p in line.split(",") if p.strip()]
                if len(parts) >= 3:
                    nodes.append(tuple(float(p) for p in parts[1:4]) + (0.0,) * (4 - len(parts)))
    facts = [("Elements", "; ".join(f"{kind}: {n} ({element_family(kind)})" for kind, n in elements.items())
              or "no *Element in this file")]
    facts.append(("Sections", "; ".join(
        k.split(",")[0] + "".join(f", {o} {_option(k, o)}" for o in ("material", "orientation") if _option(k, o))
        for k in sections) or "no section in this file"))
    if shell_sections:
        first = _numbers(data_after(next(i for i, k in keyword if k == shell_sections[0]))[:1])
        facts.append(("Shell thickness", f"{first[0]:g}" if first else "not given on the *Shell Section line"))
    for material in materials:
        parts = []
        for option, values in material["options"]:
            head = option.split(",")[0]
            kind = _option(option, "type").upper()
            parts.append(f"{head}{' ' + kind if kind else ''} ({len(values)} values)" if head.lower() != "*density"
                         else f"*Density {values[0]:g}" if values else "*Density (no value)")
        facts.append((f"Material {material['name']}", "; ".join(parts) or "no material data"))
    if not materials:
        facts.append(("Materials", "no *Material in this file"))
    orientations = [_option(k, "name") for _i, k in keyword if low(k).startswith("*orientation")]
    facts.append(("Orientations", ", ".join(orientations) or "none"))
    if nodes:
        extent = [max(n[a] for n in nodes) - min(n[a] for n in nodes) for a in range(3)]
        facts.append(("Node extent x × y × z", " × ".join(f"{e:g}" for e in extent) + f" ({len(nodes)} nodes)"))
    else:
        facts.append(("Nodes", "no *Node data in this file"))
    facts.append(("*Include", "; ".join(f"{n or '(no input= file)'} ({'found' if ok else 'not found'} beside the INP, not read)"
                                         for n, ok in includes) or "none"))

    def report(verdict, reason):
        return InpCompatibility(str(path), verdict, reason, tuple(facts), tuple(includes))

    def missing(what):
        if includes:
            names = ", ".join(f"{n or '(unnamed)'} ({'found' if ok else 'not found'})" for n, ok in includes)
            verb = "are" if " and " in what else "is"
            return report(IN_INCLUDE, f"{what} {verb} not in this file; it may be in the included file(s) {names}. Research "
                                      "Tuning reads one self-contained INP and does not follow *Include.")
        return report(MISSING_DEFINITION, f"The INP has no {what}.")

    kinds = ", ".join(elements)
    if "solid" in families and "shell" not in families or (not elements and solid_sections and not shell_sections):
        return report(SOLID_MODEL, f"Solid model ({kinds or 'no *Element'}, {'*Solid Section' if solid_sections else 'no shell section'}"
                                   "): the Kirchhoff-Ritz surrogate of Research Tuning stands for a shell model and takes its "
                                   "thickness from a *Shell Section. A solid model is not converted to a shell and no thickness "
                                   "is taken from the mesh. " + SOLID_BACKEND_NOTE)
    if "continuum shell" in families and "shell" not in families:
        return report(SOLID_MODEL, f"Continuum-shell model ({kinds}): its thickness comes from the mesh, not from a "
                                   "*Shell Section, and it is not converted here. " + SOLID_BACKEND_NOTE)
    if "shell" in families and families - {"shell"}:
        return report(MIXED_ELEMENTS, f"The INP mixes element families ({kinds}); Research Tuning reads a model of shell "
                                      "elements only.")
    if elements and "shell" not in families:
        return report(NO_SHELL_ELEMENTS, f"The INP has no shell elements ({kinds}); Research Tuning reads a shell model only.")
    if not materials:
        return missing("*Material")
    if len(materials) != 1:
        return report(MORE_THAN_ONE, f"The INP holds {len(materials)} materials; this tool reads exactly one homogeneous "
                                     "material.")
    options = {opt.split(",")[0].strip().lower(): (opt, values) for opt, values in materials[0]["options"]}
    absent = [name for name, key in (("*Elastic", "*elastic"), ("*Density", "*density")) if key not in options]
    if not shell_sections and not sections:
        absent.append("*Shell Section")
    if absent:
        return missing(" and ".join(absent) if len(absent) < 3 else "*Elastic, *Density and *Shell Section")
    if not shell_sections:
        return report(NO_SHELL_ELEMENTS, "The INP has no *Shell Section (" + ", ".join(k.split(",")[0] for k in sections)
                      + "); Research Tuning reads a shell model only.")
    other = [o.split(",")[0] for o, _v in materials[0]["options"] if o.lower().startswith(_NOT_MODAL)]
    if other:
        return report(UNSUPPORTED_MATERIAL, f"The material has {', '.join(other)}; this tool reads a linear elastic "
                                            "orthotropic material only.")
    elastic, values = options["*elastic"]
    kind = (_option(elastic, "type") or "ISOTROPIC").upper()
    wanted = {"ENGINEERING CONSTANTS": 9, "LAMINA": 6}.get(kind)
    if wanted is None or len(values) < wanted:
        return report(UNSUPPORTED_MATERIAL, f"*Elastic type {kind} with {len(values)} values is not an orthotropic "
                                            "definition this tool reads.")
    if len(values) != wanted or _option(elastic, "dependencies"):
        return report(UNSUPPORTED_MATERIAL, f"*Elastic type {kind} holds {len(values)} values; this tool reads one "
                                            f"temperature-independent set of {wanted}.")
    if not options["*density"][1]:
        return missing("*Density value")
    if any("composite" in low(k) for k in shell_sections):
        return report(COMPOSITE_LAYUP, "The shell section is a composite layup; this tool converts one homogeneous layer only.")
    if len(shell_sections) > 1:
        return report(MORE_THAN_ONE, "The INP holds more than one shell section.")
    if not nodes:
        return missing("*Node block")
    note = " The included file(s) were not read." if includes else ""
    return report(COMPATIBLE, f"Shell model ({kinds or 'elements not in this file'}, one *Shell Section, one orthotropic "
                              f"material): Research Tuning can read it.{note}")


def _keywords(path: Path):
    lines = path.read_text(encoding="latin-1").splitlines()
    keyword = [(i, line.strip()) for i, line in enumerate(lines) if line.startswith("*") and not line.startswith("**")]

    def data_after(index: int) -> list:
        out = []
        for line in lines[index + 1:]:
            if line.startswith("*"):
                break
            out.append(line)
        return out

    return lines, keyword, data_after


def inspect_inp(path) -> InpCompatibility:
    """What the INP holds and whether this tool can read it. Read only; *Include files are named, not opened."""
    path = Path(path)
    lines, keyword, data_after = _keywords(path)
    return _inspect(path, lines, keyword, data_after)


def read_inp(path) -> AbaqusPlateInputs:
    """The material, density, shell thickness and plan of a single-part, single-material shell plate INP. Read only.
    Anything else is refused with ``InpNotSupported``, whose report says what the INP is."""
    path = Path(path)
    lines, keyword, data_after = _keywords(path)
    report = _inspect(path, lines, keyword, data_after)
    if not report.supported:
        raise InpNotSupported(report)

    materials = [(i, k) for i, k in keyword if k.lower().startswith("*material")]
    if len(materials) != 1:
        raise TuningRefused(f"The INP holds {len(materials)} materials; this tool reads exactly one homogeneous material.")
    name = re.search(r"name\s*=\s*([^,]+)", materials[0][1], re.I).group(1).strip()
    elastic = density = section = None
    for i, k in keyword:
        low = k.lower()
        if low.startswith("*elastic") and i > materials[0][0]:
            elastic = (k, _numbers(data_after(i)))
        elif low.startswith("*density") and i > materials[0][0]:
            density = _numbers(data_after(i))
        elif low.startswith("*shell section"):
            if section is not None:
                raise TuningRefused("The INP holds more than one shell section.")
            section = (k, _numbers(data_after(i)[:1]))
    if elastic is None or density is None or section is None:
        raise TuningRefused("The INP has no *Elastic, *Density or *Shell Section to read.")
    kind = (re.search(r"type\s*=\s*([^,]+)", elastic[0], re.I) or [None, "ISOTROPIC"])[1].strip().upper()
    values = elastic[1]
    if kind == "ENGINEERING CONSTANTS" and len(values) >= 9:
        E1, E2, E3, nu12, nu13, nu23, G12, G13, G23 = values[:9]
    elif kind == "LAMINA" and len(values) >= 6:
        (E1, E2, nu12, G12, G13, G23), E3, nu13, nu23 = values[:6], None, None, None
    else:
        raise TuningRefused(f"*Elastic type {kind} with {len(values)} values is not an orthotropic definition this tool reads.")
    if "composite" in section[0].lower():
        raise TuningRefused("The shell section is a composite layup; this tool converts one homogeneous layer only.")
    nodes = []
    for i, k in keyword:
        if k.lower() == "*node":
            for line in data_after(i):
                parts = [p for p in line.split(",") if p.strip()]
                if len(parts) >= 3:
                    nodes.append((float(parts[1]), float(parts[2])))
            break
    if not nodes:
        raise TuningRefused("The INP has no *Node block for the plate plan.")
    xs, ys = [n[0] for n in nodes], [n[1] for n in nodes]
    return AbaqusPlateInputs(str(path), _sha(path), name, kind, E1, E2, E3, nu12, nu13, nu23, G12, G13, G23, density[0],
                             section[1][0], max(xs) - min(xs), max(ys) - min(ys),
                             any(k.lower().startswith("*orientation") for _i, k in keyword))


def read_dat_frequencies(path) -> tuple:
    """(mode, Hz) of the eigenvalue output table of an Abaqus .dat, as written. Read only."""
    rows = []
    text = Path(path).read_text(encoding="latin-1")
    start = text.find("E I G E N V A L U E    O U T P U T")
    if start < 0:
        raise TuningRefused("The .dat holds no eigenvalue output.")
    for line in text[start:].splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 4 and parts[0].isdigit():
            try:
                rows.append((int(parts[0]), float(parts[3])))
            except ValueError:
                continue
        elif rows and ("P A R T I C I P A T I O N" in line or "E F F E C T I V E" in line):
            break
    if not rows:
        raise TuningRefused("No eigenvalue rows were found in the .dat.")
    return tuple(rows)


# ---------------------------------------------------------------------------------------------- constitutive conversion


def bending_stiffness(E1: float, E2: float, nu12: float, G12: float, thickness_mm: float) -> PlateBendingParameters:
    """Homogeneous orthotropic Kirchhoff plate, MPa and mm in, N*m out (1 N*mm = 1e-3 N*m)."""
    nu21 = nu12 * E2 / E1
    factor = 1.0 - nu12 * nu21
    if factor <= 0.0:
        raise TuningRefused("1 - nu12*nu21 must be positive.")
    t3 = thickness_mm ** 3 / 12.0 * 1.0e-3
    return PlateBendingParameters(D11=E1 / factor * t3, D22=E2 / factor * t3, D12=nu12 * E2 / factor * t3, D66=G12 * t3)


def _moduli(names: Sequence[str], values: Sequence[float], base: AbaqusPlateInputs) -> dict:
    found = dict(zip(names, values))
    if "E" in found:
        return {"E1": found["E"], "E2": found["E"], "G12": found["G12"]}
    return {"E1": found["E1"], "E2": found["E2"], "G12": found["G12"]}


# ---------------------------------------------------------------------------------------------- the surrogate


@dataclass(frozen=True)
class Surrogate:
    inputs: AbaqusPlateInputs
    degree: int = 14
    mode_count: int = 24

    def frequencies(self, E1: float, E2: float, G12: float) -> np.ndarray:
        config = RitzNumericalConfig(self.degree, self.degree, self.mode_count)
        stiffness = bending_stiffness(E1, E2, self.inputs.nu12, G12, self.inputs.thickness_mm)
        return np.asarray(solve_ritz(self.inputs.geometry(), stiffness, config).frequencies_hz, dtype=float)


def surrogate_discrepancy(surrogate: Surrogate, fe_elastic) -> tuple:
    """(rank, FE mode, FE Hz, Ritz Hz, Ritz/FE - 1) at the INP's own constants, by rank of the elastic spectra."""
    base = surrogate.inputs
    ritz = surrogate.frequencies(base.E1, base.E2, base.G12)
    return tuple((rank + 1, mode, hz, float(ritz[rank]), float(ritz[rank] / hz - 1.0))
                 for rank, (mode, hz) in enumerate(fe_elastic) if rank < ritz.size)


# ---------------------------------------------------------------------------------------------- the tuning


@dataclass(frozen=True)
class Observation:
    record: int  # the experimental record number, as read
    hz: float
    role: str  # FIT, HOLDOUT or EXCLUDED
    surrogate_rank: int  # 1-based elastic rank of the surrogate this frequency is compared with (the declared hypothesis)


@dataclass(frozen=True)
class TuningRequest:
    observations: tuple
    parameterization: str = TIED
    correspondence: str = RANK_ORDER
    search_factor: float = 10.0  # bounds: the data-scaled start divided and multiplied by this factor
    degree: int = 14

    def fit_rows(self) -> tuple:
        return tuple(o for o in self.observations if o.role == FIT)


def observations_by_rank(records: Sequence[tuple], holdout: Sequence[int] = (), excluded: Sequence[int] = (),
                         declared: Optional[Mapping[int, int]] = None) -> tuple:
    """Experimental (record, Hz) as observations. Rank hypothesis: the k-th lowest kept record against surrogate rank k;
    a declared mapping {record: rank} replaces it for the records it names. A mapping that names a record which is not
    there, or not kept, is refused; whether the ranks are valid is checked by ``validate_correspondence``."""
    known = {record for record, _hz in records}
    unknown = sorted(set(declared or {}) - known)
    if unknown:
        raise TuningRefused("The declared ranks name record(s) " + ", ".join(map(str, unknown)) + " that the experimental "
                            "set does not hold.")
    declared_excluded = sorted(set(declared or {}) & set(excluded))
    if declared_excluded:
        raise TuningRefused("The declared ranks name EXCLUDED record(s) " + ", ".join(map(str, declared_excluded)) + "; "
                            "an excluded record has no rank.")
    kept = sorted((r for r in records if r[0] not in set(excluded)), key=lambda item: item[1])
    rows = []
    for rank, (record, hz) in enumerate(kept, start=1):
        target = (declared or {}).get(record, rank)
        rows.append(Observation(record, float(hz), HOLDOUT if record in set(holdout) else FIT, int(target)))
    rows += [Observation(record, float(hz), EXCLUDED, 0) for record, hz in records if record in set(excluded)]
    return tuple(sorted(rows, key=lambda o: o.record))


MAX_SURROGATE_RANK = 60  # the highest elastic rank a correspondence may name (the surrogate solves up to it plus a margin)


def validate_correspondence(observations: Sequence[Observation], max_rank: int = MAX_SURROGATE_RANK) -> None:
    """Every included (FIT or HOLDOUT) observation needs a whole, positive, in-range and unique surrogate rank. Raises
    ``TuningRefused`` with every problem found; nothing is optimized on an invalid correspondence."""
    included = [o for o in observations if o.role in (FIT, HOLDOUT)]
    problems = []
    for o in included:
        if isinstance(o.surrogate_rank, bool) or not isinstance(o.surrogate_rank, int):
            problems.append(f"record {o.record}: the rank {o.surrogate_rank!r} is not a whole number")
        elif o.surrogate_rank < 1:
            problems.append(f"record {o.record}: the rank {o.surrogate_rank} is not positive")
        elif o.surrogate_rank > max_rank:
            problems.append(f"record {o.record}: the rank {o.surrogate_rank} is above the highest allowed rank {max_rank}")
    seen = {}
    for o in included:
        seen.setdefault(o.surrogate_rank, []).append(o.record)
    for rank, records in sorted((k, v) for k, v in seen.items() if len(v) > 1 and isinstance(k, int)):
        problems.append(f"rank {rank} is assigned to records {', '.join(map(str, records))}: each surrogate rank may "
                        "match only one experimental record")
    if problems:
        raise TuningRefused("The frequency correspondence is invalid: " + "; ".join(problems) + ".")


REFERENCE_MPA = 1000.0  # the arbitrary common modulus the data-scaled start begins from; not an INP value


class _Cancelled(Exception):
    pass


class _Problem:
    """One surrogate, one parameterization, one set of FIT rows: the spectrum, the residuals and their Jacobian."""

    def __init__(self, inputs, names, rows, degree, cancel, progress):
        top = max(o.surrogate_rank for o in rows)
        self.surrogate = Surrogate(inputs, degree, max(top + 4, 12))
        self.inputs, self.names, self.rows, self.cancel, self.progress = inputs, names, rows, cancel, progress
        self.count = 0

    def spectrum(self, x: np.ndarray) -> np.ndarray:
        if self.cancel is not None and self.cancel.is_set():
            raise _Cancelled()
        self.count += 1
        if self.progress is not None:
            self.progress(self.count)
        moduli = _moduli(self.names, np.exp(x), self.inputs)
        return self.surrogate.frequencies(moduli["E1"], moduli["E2"], moduli["G12"])

    def residual(self, x, rows=None):
        return _residuals(self.spectrum(x), rows or self.rows)

    def jacobian(self, x, rows=None, step=1.0e-5):
        columns = []
        for j in range(x.size):
            up, down = x.copy(), x.copy()
            up[j] += step
            down[j] -= step
            columns.append((self.residual(up, rows) - self.residual(down, rows)) / (2 * step))
        return np.column_stack(columns)

    def data_scaled_start(self) -> tuple:
        """A start from the data alone: every modulus at REFERENCE_MPA, then (1) the common factor that the geometric mean
        of the FIT frequencies asks for (f ~ sqrt(modulus) at fixed geometry and surface mass), and (2) one linearized
        least-squares step that splits it between the parameters. Returns (x0, common factor, note)."""
        reference = np.full(len(self.names), math.log(REFERENCE_MPA))
        mismatch = -self.residual(reference)  # ln(f_exp / f_ref)
        common = 2.0 * float(np.mean(mismatch))
        scaled = reference + common
        sensitivity = self.jacobian(scaled)
        step, *_ = np.linalg.lstsq(sensitivity, -self.residual(scaled), rcond=None)
        step = np.clip(step, -math.log(5.0), math.log(5.0))
        return scaled + step, math.exp(common), ("reference modulus 1000 MPa, common factor from the mean log frequency "
                                                 "ratio, one linearized split step")


def _swap(names, x: np.ndarray) -> np.ndarray:
    swapped = x.copy()
    if "E1" in names:
        i, j = names.index("E1"), names.index("E2")
        swapped[i], swapped[j] = x[j], x[i]
    return swapped


def _solve(problem: _Problem, x0: np.ndarray, factor: float, bounds: Optional[tuple] = None) -> dict:
    """``bounds`` (lower, upper) in ln p replaces the range x0 ÷/× factor (REAL-FIT.R2: a refit keeps the full fit's range)."""
    lower, upper = (x0 - math.log(factor), x0 + math.log(factor)) if bounds is None else (np.asarray(bounds[0]),
                                                                                          np.asarray(bounds[1]))
    starts_x = [x0, x0 + np.array([math.log(0.6) if n != "G12" else math.log(1.6) for n in problem.names]),
                x0 + np.array([math.log(1.6) if n != "G12" else math.log(0.6) for n in problem.names])]
    if "E1" in problem.names:  # asymmetric starts and the exchanged start, so that a mirror minimum shows itself
        starts_x += [x0 + np.array([math.log(1.3), math.log(0.77), 0.0]), x0 + np.array([math.log(0.77), math.log(1.3), 0.0]),
                     _swap(problem.names, x0)]
    starts = []
    for start in starts_x:
        x_start = np.clip(start, lower + 1e-9, upper - 1e-9)
        solution = least_squares(problem.residual, x_start, jac=problem.jacobian, bounds=(lower, upper), method="trf",
                                 x_scale=1.0, ftol=1e-14, xtol=1e-12, gtol=1e-12, max_nfev=200)
        starts.append({"start": dict(zip(problem.names, np.exp(x_start).tolist())),
                       "values": dict(zip(problem.names, np.exp(solution.x).tolist())), "cost": float(solution.cost),
                       "status": int(solution.status), "message": solution.message, "success": bool(solution.success),
                       "x": solution.x})
    best = min(starts, key=lambda s: s["cost"])
    minima = []
    for item in sorted(starts, key=lambda s: s["cost"]):
        if not any(float(np.max(np.abs(np.exp(item["x"] - m["x"]) - 1.0))) <= START_AGREEMENT for m in minima):
            minima.append(item)
    return {"x": best["x"], "starts": starts, "minima": minima, "lower": lower, "upper": upper}


def _percent(sd_log: float) -> float:
    return math.exp(sd_log) - 1.0


@dataclass
class TuningResult:
    status: str
    reasons: list
    label: str
    warnings: list
    request: dict
    inputs: dict
    parameter_names: tuple
    baseline: dict  # the INP's values, for comparison only; they set neither the start nor the bounds
    fitted: Optional[dict]  # the best minimum, always reported for diagnosis
    candidate: Optional[dict]  # an oriented candidate: only when numerically supported AND the axes are resolved
    estimates: Optional[dict]  # numerical research estimates; for an unresolved E1/E2 axis: E_stiff, E_soft, G12
    axis_assignments: list  # both assignments when the axis is unresolved; never one chosen
    rows: list
    sensitivity: list
    singular_values: list
    condition_number: Optional[float]
    practical_rank: int
    correlation: Optional[list]
    log_sd: Optional[dict]
    active_bounds: list
    starts: list
    rms_fit_before: float
    rms_fit_after: Optional[float]
    rms_holdout_before: Optional[float]
    rms_holdout_after: Optional[float]
    surrogate: list
    initialization: dict = field(default_factory=dict)
    first_mode_check: dict = field(default_factory=dict)
    assumption_sensitivity: list = field(default_factory=list)
    quantities: list = field(default_factory=list)
    accuracy_statement: str = ""
    fe_classification: str = ""
    minima: list = field(default_factory=list)
    assumptions: tuple = ASSUMPTIONS
    evaluations: int = 0

    def to_dict(self) -> dict:
        return {"schema": SCHEMA, **asdict(self)}


def _residuals(frequencies: np.ndarray, rows: Sequence[Observation]) -> np.ndarray:
    return np.array([math.log(frequencies[o.surrogate_rank - 1] / o.hz) for o in rows])


ACCURACY_STATEMENT = ("Frequency errors are not parameter errors. The statistical SD is conditional on the model, the rank "
                      "hypothesis and the fixed inputs; it leaves out the thickness and density assumptions, the support "
                      "stiffness and any missed mode. A 10 % engineering accuracy of the parameters is a target, not a "
                      "demonstrated or certified property of these estimates.")


def _estimates(names, values: Mapping[str, float]) -> dict:
    if "E" in names:
        return {"E (E1 = E2)": values["E"], "G12": values["G12"]}
    return {"E_stiff": max(values["E1"], values["E2"]), "E_soft": min(values["E1"], values["E2"]), "G12": values["G12"]}


def quantity_table(inputs: AbaqusPlateInputs, names, fe_classification: str) -> list:
    fitted = ", ".join("E1 = E2" if n == "E" else n for n in names)
    return [
        {"quantity": "Natural frequencies", "category": "MEASURED", "source": "PolyMAX curve-fitted records (the experimental file)"},
        {"quantity": fitted, "category": "FITTED", "source": "this tuning (Kirchhoff-Ritz surrogate)"},
        {"quantity": f"Thickness {inputs.thickness_mm:g} mm", "category": "ASSUMED (INP), FIXED", "source": "*Shell Section of the INP"},
        {"quantity": f"Density {inputs.density_t_mm3:g} t/mm³", "category": "ASSUMED (INP), FIXED", "source": "*Density of the INP"},
        {"quantity": f"Surface mass {inputs.density_t_mm3 * inputs.thickness_mm * 1e9:.4g} kg/m²", "category": "DERIVED",
         "source": "density × thickness (INP)"},
        {"quantity": f"Plan {inputs.a_mm:g} × {inputs.b_mm:g} mm", "category": "MODEL GEOMETRY (INP)", "source": "*Node extents"},
        {"quantity": f"nu12 = {inputs.nu12:g}", "category": "FIXED, NOT IDENTIFIED", "source": "*Elastic of the INP"},
        {"quantity": "E3, nu13, nu23, G13, G23", "category": "NOT IN THE SURROGATE, KEPT", "source": "*Elastic of the INP"},
        {"quantity": "FE rigid-body / elastic classification", "category": "SHAPE-BASED" if fe_classification.startswith("shape")
         else "UNAVAILABLE", "source": fe_classification},
    ]


def run_tuning(inputs: AbaqusPlateInputs, request: TuningRequest, fe_elastic=(), cancel: Optional[threading.Event] = None,
               progress: Optional[Callable[[int], None]] = None, fe_classification: str = "") -> TuningResult:
    """``fe_elastic``: (mode, Hz) of the elastic FE modes as classified by shape (P-2), or () when no classification exists."""
    names = PARAMETERIZATIONS[request.parameterization]
    validate_correspondence(request.observations)
    fit_rows = request.fit_rows()
    holdout_rows = tuple(o for o in request.observations if o.role == HOLDOUT)
    if len(fit_rows) <= len(names):
        raise TuningRefused(f"{len(fit_rows)} FIT frequencies cannot determine {len(names)} parameters; keep more than "
                            f"{len(names)} in the fit.")
    if request.parameterization == TIED and inputs.E1 != inputs.E2:
        raise TuningRefused("E1 = E2 tying needs equal E1 and E2 in the INP; choose the three-parameter form.")
    if not request.search_factor > 1.0:
        raise TuningRefused("The search range factor must exceed 1.")
    kept = tuple(o for o in request.observations if o.role != EXCLUDED)
    problem = _Problem(inputs, names, fit_rows, request.degree, cancel, progress)
    all_rows = _Problem(inputs, names, kept, request.degree, cancel, None)
    base_values = {"E": inputs.E1, "E1": inputs.E1, "E2": inputs.E2, "G12": inputs.G12}
    base = np.array([math.log(base_values[n]) for n in names])
    try:
        x0, common, note = problem.data_scaled_start()
        fit = _solve(problem, x0, request.search_factor)
        x = fit["x"]
        baseline_spectrum = all_rows.spectrum(base)
        fitted_spectrum = all_rows.spectrum(x)
        J = problem.jacobian(x)
        if "E1" in names and len(fit["minima"]) == 1:  # look for the exchanged minimum explicitly; never assume it absent
            mirror = _solve(problem, _swap(names, x), request.search_factor)
            for item in mirror["minima"]:
                if not any(float(np.max(np.abs(np.exp(item["x"] - m["x"]) - 1.0))) <= START_AGREEMENT for m in fit["minima"]):
                    fit["minima"].append(item)
            fit["starts"] += mirror["starts"]
        first_mode = _first_mode_check(inputs, request, names, x, cancel)
    except _Cancelled:
        return _cancelled(inputs, request, names)
    singular = np.linalg.svd(J, compute_uv=False)
    rank = int(np.sum(singular > PRACTICAL_RANK_RATIO * singular[0])) if singular.size else 0
    condition = float(singular[0] / singular[-1]) if singular.size and singular[-1] > 0 else math.inf
    r_after = _residuals(fitted_spectrum[:], fit_rows)
    dof = len(fit_rows) - len(names)
    correlation = log_sd = None
    if rank == len(names):
        covariance = np.linalg.inv(J.T @ J) * float(r_after @ r_after) / dof
        sd = np.sqrt(np.diag(covariance))
        correlation = (covariance / np.outer(sd, sd)).round(6).tolist()
        log_sd = dict(zip(names, sd.tolist()))
    active = [n for n, v, lo, hi in zip(names, x, fit["lower"], fit["upper"]) if v - lo < 1e-6 or hi - v < 1e-6]
    minima = sorted(fit["minima"], key=lambda m: m["cost"])
    mirror = (len(minima) >= 2 and "E1" in names and all(
        abs(minima[0]["values"][a] / minima[1]["values"][b] - 1.0) <= MIRROR_TOLERANCE
        for a, b in (("E1", "E2"), ("E2", "E1"), ("G12", "G12"))))
    others = [m for m in minima[1:] if not mirror or m is not minima[1]]
    reasons = []
    if not all(s["success"] for s in fit["starts"]):
        reasons.append("A start did not converge: " + "; ".join(s["message"] for s in fit["starts"] if not s["success"]))
    if rank < len(names):
        reasons.append(f"Practical rank {rank} of {len(names)}: the FIT frequencies cannot separate the parameters.")
    if condition > CONDITION_LIMIT:
        reasons.append(f"Condition number {condition:.3g} exceeds {CONDITION_LIMIT:g}: the parameters are poorly distinguished.")
    if active:
        reasons.append("At a bound: " + ", ".join(active) + ". The minimum lies outside the search range.")
    if others:
        reasons.append(f"{len(others)} further minimum/minima besides the best: the minimum is not unique within the range.")
    if mirror:
        reasons.append("Two minima with E1 and E2 exchanged fit almost equally (costs " + ", ".join(
            f"{m['cost']:.6g}" for m in minima[:2]) + "): the frequencies support a stiff and a soft in-plane direction but "
            "not which plate axis (FE X or Y) is which. That needs the physical orientation of the test plate.")
    if reasons and reasons[0].startswith("A start"):
        status = NOT_CONVERGED
    elif rank < len(names) or condition > CONDITION_LIMIT:
        status = NOT_IDENTIFIABLE
    elif active:
        status = AT_BOUND
    elif others:
        status = STARTS_DISAGREE
    else:
        status = MIRROR if mirror else SUPPORTED
    fitted = {k: float(v) for k, v in _moduli(names, np.exp(x), inputs).items()}
    values = dict(zip(names, np.exp(x).tolist()))
    estimates = _estimates(names, values) if status in (SUPPORTED, MIRROR) else None
    axes = []
    if mirror:
        for label, m in zip(("assignment A", "assignment B"), minima[:2]):
            axes.append({"assignment": label, "E1 (FE X)": m["values"]["E1"], "E2 (FE Y)": m["values"]["E2"],
                         "G12": m["values"]["G12"], "cost": m["cost"]})
    rows = []
    for o in request.observations:
        if o.role == EXCLUDED:
            rows.append({"record": o.record, "role": o.role, "rank": None, "exp_hz": o.hz, "ritz_before_hz": None,
                         "ritz_after_hz": None, "ln_before": None, "ln_after": None})
            continue
        before, after = float(baseline_spectrum[o.surrogate_rank - 1]), float(fitted_spectrum[o.surrogate_rank - 1])
        rows.append({"record": o.record, "role": o.role, "rank": o.surrogate_rank, "exp_hz": o.hz, "ritz_before_hz": before,
                     "ritz_after_hz": after, "ln_before": math.log(before / o.hz), "ln_after": math.log(after / o.hz)})

    def rms(role, key):
        found = [r[key] for r in rows if r["role"] == role]
        return float(np.sqrt(np.mean(np.square(found)))) if found else None

    warnings = []
    fit_rms = float(np.sqrt(np.mean(np.square(r_after))))
    if fit_rms > MISFIT_RMS:
        warnings.append(f"FIT residual RMS {fit_rms:.2%} in ln f exceeds {MISFIT_RMS:.0%}: this parameterization does not "
                        "reproduce the measured spectrum, and its values absorb model-form error.")
    if any(abs(r["ln_after"]) > 0.05 for r in rows if r["role"] == HOLDOUT):
        warnings.append("A HOLDOUT frequency is predicted more than 5 % off after the fit.")
    if first_mode.get("largest_change", 0.0) > 0.05:
        warnings.append(f"Leaving out the lowest experimental record changes a parameter by {first_mode['largest_change']:.1%}: "
                        "the estimate depends on that record.")
    if not fe_elastic:
        warnings.append("FE classification unavailable: no extracted FE mode shapes, so the surrogate is not compared with "
                        "the Abaqus spectrum by rank.")
    statistical = {n: _percent(v) for n, v in (log_sd or {}).items()}
    return TuningResult(
        status=status, reasons=reasons, label=RESULT_LABEL, warnings=warnings,
        request={"parameterization": request.parameterization, "correspondence": request.correspondence,
                 "search_factor": request.search_factor, "ritz_degree": request.degree,
                 "observations": [asdict(o) for o in request.observations]},
        inputs=asdict(inputs), parameter_names=names,
        baseline={"E1": inputs.E1, "E2": inputs.E2, "G12": inputs.G12, "nu12": inputs.nu12},
        fitted={**fitted, "nu12": inputs.nu12},
        candidate=({**fitted, "nu12": inputs.nu12} if status == SUPPORTED else None),
        estimates=estimates, axis_assignments=axes,
        rows=rows, sensitivity=[dict(zip(names, row)) | {"record": o.record} for o, row in zip(fit_rows, J.tolist())],
        singular_values=singular.tolist(), condition_number=condition, practical_rank=rank, correlation=correlation,
        log_sd=log_sd, active_bounds=active,
        starts=[{k: v for k, v in s.items() if k != "x"} for s in fit["starts"]],
        rms_fit_before=rms(FIT, "ln_before"), rms_fit_after=rms(FIT, "ln_after"),
        rms_holdout_before=rms(HOLDOUT, "ln_before"), rms_holdout_after=rms(HOLDOUT, "ln_after"),
        surrogate=[{"rank": r[0], "fe_mode": r[1], "fe_hz": r[2], "ritz_hz": r[3], "ritz_over_fe_minus_1": r[4]}
                   for r in surrogate_discrepancy(Surrogate(inputs, request.degree, max(len(fe_elastic) + 2, 12)),
                                                  fe_elastic)] if fe_elastic else [],
        initialization={"method": note, "reference_mpa": REFERENCE_MPA, "common_factor": common,
                        "start": dict(zip(names, np.exp(x0).tolist())),
                        "bounds": {n: [float(np.exp(lo)), float(np.exp(hi))] for n, lo, hi in zip(names, fit["lower"], fit["upper"])},
                        "inp_values_used": "no (shown for comparison only)"},
        first_mode_check=first_mode,
        assumption_sensitivity=assumption_sensitivity(),
        quantities=quantity_table(inputs, names, fe_classification or "unavailable"),
        accuracy_statement=ACCURACY_STATEMENT + (" Statistical SD: " + ", ".join(f"{n} ±{v:.1%}" for n, v in statistical.items())
                                                 if statistical else ""),
        fe_classification=fe_classification or "unavailable",
        minima=[{"values": dict(m["values"]), "cost": m["cost"]} for m in minima], evaluations=problem.count + all_rows.count)


def _first_mode_check(inputs, request, names, x, cancel) -> dict:
    """The same fit with the lowest kept experimental record left out (not removed from the result): how much the estimates
    lean on it. Only that record leaves: every other observation keeps its declared surrogate rank and its role, so the
    correspondence is neither renumbered nor rematched (REAL-FIT.R1.F2)."""
    kept = sorted((o for o in request.observations if o.role != EXCLUDED), key=lambda o: o.hz)
    if not kept or kept[0].role != FIT:
        return {"done": False, "reason": "the lowest kept record is not a FIT record"}
    lowest = kept[0]
    observations = tuple(o if o.record != lowest.record else Observation(o.record, o.hz, EXCLUDED, 0)
                         for o in request.observations)
    fit_rows = tuple(o for o in observations if o.role == FIT)
    if len(fit_rows) <= len(names):
        return {"done": False, "reason": "too few FIT records without it"}
    problem = _Problem(inputs, names, fit_rows, request.degree, cancel, None)
    fit = _solve(problem, x, request.search_factor)
    candidates = [m for m in fit["minima"]]
    nearest = min(candidates, key=lambda m: float(np.max(np.abs(m["x"] - x))))
    singular = np.linalg.svd(problem.jacobian(nearest["x"]), compute_uv=False)
    changes = {n: float(math.exp(a - b) - 1.0) for n, a, b in zip(names, nearest["x"], x)}
    return {"done": True, "left_out_record": lowest.record, "left_out_hz": lowest.hz, "left_out_rank": lowest.surrogate_rank,
            "ranks_kept": {o.record: o.surrogate_rank for o in fit_rows},
            "values": dict(zip(names, np.exp(nearest["x"]).tolist())), "change": changes,
            "largest_change": max(abs(v) for v in changes.values()),
            "condition_number": float(singular[0] / singular[-1]) if singular[-1] > 0 else math.inf}


def assumption_sensitivity() -> list:
    """How the estimates move with the fixed inputs, from the plate scaling f ~ sqrt(D / (rho h)), D ~ E t^3 (exact for the
    surrogate). Not a fit; a statement of what the fixed inputs carry."""
    rows = []
    for change in (-0.05, 0.05):
        rows.append({"assumption": f"thickness {change:+.0%}, surface mass held (measured mass)",
                     "moduli_factor": (1.0 + change) ** -3})
        rows.append({"assumption": f"thickness {change:+.0%}, density held (surface mass changes)",
                     "moduli_factor": (1.0 + change) ** -2})
        rows.append({"assumption": f"density {change:+.0%}", "moduli_factor": 1.0 + change})
    return rows


def _cancelled(inputs, request, names) -> TuningResult:
    return TuningResult(CANCELLED, ["Cancelled before the fit finished."], RESULT_LABEL, [], {}, asdict(inputs), names,
                        {"E1": inputs.E1, "E2": inputs.E2, "G12": inputs.G12, "nu12": inputs.nu12}, None, None, None, [], [],
                        [], [], None, 0, None, None, [], [], 0.0, None, None, None, [])


def abaqus_elastic_line(inputs: AbaqusPlateInputs, candidate: Mapping[str, float]) -> str:
    """The *Elastic data a new Abaqus solve would use: the candidate E1, E2, G12; every other constant as in the INP."""
    if inputs.elastic_type == "ENGINEERING CONSTANTS":
        return (f"*Elastic, type=ENGINEERING CONSTANTS\n{candidate['E1']:.6g}, {candidate['E2']:.6g}, {inputs.E3:.6g}, "
                f"{inputs.nu12:.6g}, {inputs.nu13:.6g}, {inputs.nu23:.6g}, {candidate['G12']:.6g}, {inputs.G13:.6g}\n"
                f"{inputs.G23:.6g},")
    return (f"*Elastic, type=LAMINA\n{candidate['E1']:.6g}, {candidate['E2']:.6g}, {inputs.nu12:.6g}, {candidate['G12']:.6g}, "
            f"{inputs.G13:.6g}, {inputs.G23:.6g}")


def export_document(result: TuningResult, inputs: AbaqusPlateInputs, sources: Mapping[str, str],
                    stability: Optional[Mapping] = None) -> dict:
    """Everything needed to reproduce and review the proposal. An Abaqus *Elastic block only for an oriented candidate:
    never when the E1/E2 axis is unresolved. ``stability``: the REAL-FIT.R2 check of this same result, when it was run."""
    document = result.to_dict()
    document["sources"] = dict(sources)
    document["stability"] = dict(stability) if stability else None
    document["abaqus_elastic_candidate"] = abaqus_elastic_line(inputs, result.candidate) if result.candidate else None
    document["statement"] = ("Surrogate (Kirchhoff-Ritz) research estimates. Not an FE result, not a material property and "
                             "not a calibration; an oriented Abaqus block is given only when the axes are resolved. "
                             + RESULT_LABEL)
    return document


def write_export(document: dict, path) -> Path:
    path = Path(path)
    path.write_text(json.dumps(document, indent=1, default=str, ensure_ascii=False), encoding="utf-8")
    return path


EXPORT_MAX_BYTES = 20 * 2 ** 20  # an export is a few hundred kB; anything far larger is not one


def read_export(path, max_bytes: int = EXPORT_MAX_BYTES) -> dict:
    """An exported proposal as JSON, size-limited. Only this file is read: no path named in it is looked at."""
    path = Path(path)
    try:
        size = path.stat().st_size
    except OSError as error:
        raise TuningRefused(f"The file cannot be read ({error}).") from None
    if size > max_bytes:
        raise TuningRefused(f"The file is {size / 2 ** 20:.1f} MB; a Research Tuning export is at most "
                            f"{max_bytes / 2 ** 20:.0f} MB.")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise TuningRefused(f"Not a Research Tuning export: the file is not valid JSON ({type(error).__name__}).") from None
    if not isinstance(document, dict):
        raise TuningRefused("Not a Research Tuning export: the file holds no JSON object.")
    return document


def restore_record_keys(value):
    """JSON writes integer dictionary keys (record numbers) as text; give them back as integers, recursively."""
    if isinstance(value, dict):
        return {(int(k) if isinstance(k, str) and k.isdigit() else k): restore_record_keys(v) for k, v in value.items()}
    if isinstance(value, list):
        return [restore_record_keys(v) for v in value]
    return value


def result_from_export(document: Mapping) -> TuningResult:
    """The saved result of an export, exactly as it was written; nothing is recomputed. Refused unless it is this schema,
    carries the research label, holds every result field with the expected kind and is not a cancelled run."""
    if document.get("schema") != SCHEMA:
        raise TuningRefused(f"Not a Research Tuning export: schema {document.get('schema')!r}, expected {SCHEMA!r}.")
    if document.get("label") != RESULT_LABEL:
        raise TuningRefused("The file does not carry the Research Tuning label; it is not opened.")
    names = [item.name for item in fields(TuningResult)]
    missing = [name for name in names if name not in document]
    if missing:
        raise TuningRefused(f"The export is incomplete: {', '.join(missing)} missing.")
    values = {name: restore_record_keys(document[name]) for name in names}
    kinds = {"status": str, "label": str, "reasons": list, "warnings": list, "request": dict, "inputs": dict,
             "parameter_names": list, "baseline": dict, "axis_assignments": list, "rows": list, "sensitivity": list,
             "singular_values": list, "practical_rank": int, "active_bounds": list, "starts": list, "surrogate": list,
             "minima": list, "assumptions": list, "evaluations": int}
    wrong = [name for name, kind in kinds.items() if not isinstance(values[name], kind)]
    if wrong:
        raise TuningRefused(f"The export is damaged: unexpected content in {', '.join(wrong)}.")
    if tuple(values["parameter_names"]) not in PARAMETERIZATIONS.values():
        raise TuningRefused("The export names unknown fitted inputs.")
    if values["status"] == CANCELLED:
        raise TuningRefused("The export holds a cancelled run; there is no result to show.")
    values["parameter_names"] = tuple(values["parameter_names"])
    values["assumptions"] = tuple(values["assumptions"])
    return TuningResult(**values)


__all__ = ["MAX_SURROGATE_RANK", "validate_correspondence", "ACCURACY_STATEMENT", "ASSUMPTIONS", "AbaqusPlateInputs", "DECLARED", "FIT", "FREE", "HOLDOUT", "EXCLUDED",
           "MIRROR", "Observation", "PARAMETERIZATIONS", "RANK_ORDER", "RESULT_LABEL", "SUPPORTED", "Surrogate", "TIED",
           "TuningRefused", "TuningRequest", "TuningResult", "abaqus_elastic_line", "assumption_sensitivity",
           "bending_stiffness", "export_document", "observations_by_rank", "quantity_table", "read_dat_frequencies",
           "read_export", "read_inp", "restore_record_keys", "result_from_export", "run_tuning", "surrogate_discrepancy", "write_export",
           "COMPATIBLE", "SOLID_MODEL", "MIXED_ELEMENTS", "NO_SHELL_ELEMENTS", "IN_INCLUDE", "MISSING_DEFINITION",
           "UNSUPPORTED_MATERIAL", "COMPOSITE_LAYUP", "MORE_THAN_ONE", "SOLID_BACKEND_NOTE", "InpCompatibility",
           "InpNotSupported", "element_family", "inspect_inp"]
