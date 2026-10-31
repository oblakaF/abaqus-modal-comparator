"""PRIORITY-8: the research workbench of ANY single rectangular CFRP plate without a core (no Qt; RESEARCH_ONLY).

A study of one physical plate holds:

- a typed passport: separate ``design_id``, ``physical_specimen_id`` and ``test_run_id``, measurements with units,
  method and provenance, thickness readings with their positions, the material orientation, the test set-up, the
  measured DOF, the FE model and the engineering constants with their roles (FIXED or INITIAL);
- the identities (SHA-256) of the experimental file and of the FE manifest read in the Workspace, and the modal set;
- the physical registration evidence (``services.generic_plate_evidence``; never a frozen registration);
- an imported FE sensitivity table of THIS FE model and a declared observation set (``generic_plate_offline_study``);
- the history of the research actions.

Nothing is guessed: an unknown value is NOT_AVAILABLE, a computed one is DERIVED with its basis, a SYNTHETIC one
belongs to a synthetic demonstration study only. The modal diagnostics use the existing importers' data (every
experimental record, EXP1 included; every elastic FE mode by the code's own rigid-body criterion, the first elastic
included); proximity in frequency is never a pair. The readiness lists every reason why an identification cannot
start (NOT_READY_FOR_IDENTIFICATION). Production identification stays BLOCKED (M8 GATE NOT_MET, D-077
NO_GLOBAL_PARAMETER_VALUE): no value here is a material property.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from . import generic_plate_evidence as ev

SCHEMA = "amc/generic-single-plate-study/v1"
PHYSICAL, SYNTHETIC_DEMO = ev.PHYSICAL, ev.SYNTHETIC_DEMO
NOT_AVAILABLE = "NOT_AVAILABLE"
MEASURED, INSTRUMENT_RECORD, HUMAN_CONFIRMED = "MEASURED", "INSTRUMENT_RECORD", "HUMAN_CONFIRMED"
DERIVED, CANDIDATE, NOT_VERIFIED, SYNTHETIC = "DERIVED", "CANDIDATE", "NOT_VERIFIED", ev.SYNTHETIC
PROVENANCES = (MEASURED, INSTRUMENT_RECORD, HUMAN_CONFIRMED, DERIVED, CANDIDATE, "CONVENTION_ONLY", NOT_VERIFIED,
               SYNTHETIC, NOT_AVAILABLE)
MEASURED_CLASSES = (MEASURED, INSTRUMENT_RECORD)
NOT_READY = "NOT_READY_FOR_IDENTIFICATION"
READY_FOR_REVIEW = "READY_FOR_OWNER_REVIEW — production identification remains BLOCKED"
PASS, OPEN, BLOCKED = "PASS", "OPEN", "BLOCKED"
LABELS = ("RESEARCH_ONLY", "NOT_A_MATERIAL_PROPERTY")
SYNTHETIC_LABEL = "SYNTHETIC_DEMONSTRATION — NOT A PHYSICAL EXPERIMENT"
SCIENTIFIC_STATUS = ("M8 GATE NOT_MET · D-077 NO_GLOBAL_PARAMETER_VALUE · production Auto-ID BLOCKED · no material "
                     "value is released here")
MIN_THICKNESS_POINTS = 9  # SPEC v1.1 §5 (t prior from 9+ points)
PROXIMITY_ONLY = "FREQUENCY_PROXIMITY_ONLY — NOT A MODE PAIR"
ROLES = ("FIXED", "INITIAL")

UNITS = {
    "length": {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4},  # → mm
    "mass": {"g": 1.0, "kg": 1000.0},  # → g
    "density": {"kg/m3": 1.0, "g/cm3": 1000.0},  # → kg/m³
    "modulus": {"MPa": 1.0, "GPa": 1000.0, "Pa": 1.0e-6},  # → MPa
    "ratio": {"1": 1.0},
}
BASE_UNIT = {"length": "mm", "mass": "g", "density": "kg/m3", "modulus": "MPa", "ratio": "1"}


class PassportError(ValueError):
    """A passport value is not a valid number with a known unit and provenance."""


class StudyRefused(ValueError):
    """A study file cannot be read, or an action is refused; the reason is shown."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ----------------------------------------------------------------------------- quantities and claims

@dataclass(frozen=True)
class Quantity:
    """A number with its unit, provenance and source; ``value`` None is NOT_AVAILABLE (never a guess)."""

    kind: str
    value: Optional[float] = None
    unit: str = ""
    provenance: str = NOT_AVAILABLE
    source: str = ""
    method: str = ""
    uncertainty: Optional[float] = None  # in ``unit``; None is NOT_AVAILABLE
    uncertainty_basis: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if self.kind not in UNITS:
            raise PassportError(f"unknown quantity kind {self.kind!r}")
        if self.provenance not in PROVENANCES:
            raise PassportError(f"unknown provenance {self.provenance!r}")
        if self.value is None:
            if self.provenance not in (NOT_AVAILABLE,):
                raise PassportError("a value NOT_AVAILABLE has the provenance NOT_AVAILABLE")
            return
        if self.unit not in UNITS[self.kind]:
            raise PassportError(f"{self.unit!r} is not a {self.kind} unit {tuple(UNITS[self.kind])}")
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)) or not math.isfinite(self.value):
            raise PassportError(f"{self.value!r} is not a finite number")
        if self.kind == "ratio":
            if not 0.0 <= self.value < 0.5:
                raise PassportError(f"a Poisson ratio {self.value} is outside [0, 0.5)")
        elif self.value <= 0:
            raise PassportError(f"a {self.kind} must be positive, not {self.value}")
        if self.provenance == NOT_AVAILABLE:
            raise PassportError("a given value needs its provenance")
        if self.uncertainty is not None and (isinstance(self.uncertainty, bool) or not math.isfinite(self.uncertainty)
                                             or self.uncertainty < 0):
            raise PassportError(f"the uncertainty {self.uncertainty!r} is not a finite non-negative number")

    @property
    def available(self) -> bool:
        return self.value is not None

    def base(self) -> Optional[float]:
        """The value in the base unit (mm, g, kg/m³, MPa, 1), or None."""
        return None if self.value is None else float(self.value) * UNITS[self.kind][self.unit]

    def base_uncertainty(self) -> Optional[float]:
        if self.uncertainty is None or self.value is None:
            return None
        return float(self.uncertainty) * UNITS[self.kind][self.unit]

    def text(self) -> str:
        if self.value is None:
            return NOT_AVAILABLE
        unc = f" ± {self.uncertainty:g}" if self.uncertainty is not None else ""
        return f"{self.value:g}{unc} {self.unit} ({self.provenance})"


def not_available(kind: str) -> Quantity:
    return Quantity(kind)


@dataclass(frozen=True)
class Claim:
    """A stated fact that is not a number (orientation, set-up, face, axes); None is NOT_AVAILABLE."""

    value: Optional[str] = None
    provenance: str = NOT_AVAILABLE
    source: str = ""

    def __post_init__(self) -> None:
        if self.provenance not in PROVENANCES:
            raise PassportError(f"unknown provenance {self.provenance!r}")
        if self.value in (None, "") and self.provenance != NOT_AVAILABLE:
            raise PassportError("an empty claim has the provenance NOT_AVAILABLE")
        if self.value not in (None, "") and self.provenance == NOT_AVAILABLE:
            raise PassportError("a stated claim needs its provenance")

    @property
    def available(self) -> bool:
        return self.value not in (None, "")

    def text(self) -> str:
        return f"{self.value} ({self.provenance})" if self.available else NOT_AVAILABLE


@dataclass(frozen=True)
class ThicknessReading:
    position: str
    thickness: Quantity  # kind "length"
    method: str = ""

    def __post_init__(self) -> None:
        if self.thickness.kind != "length" or not self.thickness.available:
            raise PassportError("a thickness reading needs a length value")
        if not str(self.position).strip():
            raise PassportError("a thickness reading needs its position")


@dataclass(frozen=True)
class Constant:
    """An engineering constant of the FE model: FIXED (not fitted) or INITIAL (a start value)."""

    name: str
    quantity: Quantity
    role: str

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise PassportError(f"role {self.role!r} is not one of {ROLES}")


CLAIMS = ("material_orientation", "layup", "suspension", "measured_face", "instrument_axes", "measured_dofs",
          "fe_model_version", "excitation")


@dataclass(frozen=True)
class Passport:
    design_id: str = ""
    physical_specimen_id: str = ""
    test_run_id: str = ""
    measurement_date: str = ""
    measurement_method: str = ""
    length: Quantity = field(default_factory=lambda: not_available("length"))
    width: Quantity = field(default_factory=lambda: not_available("length"))
    mass: Quantity = field(default_factory=lambda: not_available("mass"))
    density: Quantity = field(default_factory=lambda: not_available("density"))
    thickness: tuple = ()  # ThicknessReading
    claims: Mapping[str, Claim] = field(default_factory=dict)  # CLAIMS → Claim
    constants: tuple = ()  # Constant

    def claim(self, name: str) -> Claim:
        return self.claims.get(name) or Claim()

    def constant(self, name: str) -> Optional[Constant]:
        return next((c for c in self.constants if c.name == name), None)


# ----------------------------------------------------------------------------- derived quantities

@dataclass(frozen=True)
class Derived:
    name: str
    value: Optional[float]
    unit: str
    basis: tuple  # the inputs it is computed from
    provenance: str = DERIVED
    note: str = ""


def thickness_summary(passport: Passport, kind: str = PHYSICAL) -> dict:
    """Mean, observed scatter and count of the thickness readings (mm). The scatter is an observed spread, never
    declared an instrument uncertainty. SYNTHETIC readings count as measured in a synthetic study only."""
    values = [r.thickness.base() for r in passport.thickness]
    accepted = MEASURED_CLASSES + ((SYNTHETIC,) if kind == SYNTHETIC_DEMO else ())
    measured = [r for r in passport.thickness if r.thickness.provenance in accepted]
    n = len(values)
    if not n:
        return {"n": 0, "n_measured": 0, "mean_mm": None, "sd_mm": None, "cv": None, "min_mm": None, "max_mm": None}
    mean = sum(values) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1)) if n > 1 else None
    return {"n": n, "n_measured": len(measured), "mean_mm": mean, "sd_mm": sd,
            "cv": (sd / mean) if sd is not None else None, "min_mm": min(values), "max_mm": max(values)}


def derived_quantities(passport: Passport) -> tuple:
    out = []
    length, width, mass = passport.length.base(), passport.width.base(), passport.mass.base()
    t = thickness_summary(passport)
    if None not in (length, width, mass):
        out.append(Derived("areal_density", mass / 1000.0 / (length * width / 1.0e6), "kg/m2",
                           ("mass", "length", "width"), note="m / (L·W)"))
    else:
        out.append(Derived("areal_density", None, "kg/m2", ("mass", "length", "width"), NOT_AVAILABLE,
                           "needs mass, length and width"))
    if t["mean_mm"] is not None:
        out.append(Derived("mean_thickness", t["mean_mm"], "mm", tuple(r.position for r in passport.thickness),
                           note=f"mean of {t['n']} readings"))
    if None not in (length, width, mass) and t["mean_mm"] is not None:
        out.append(Derived("density_from_mass", mass / 1000.0 / (length * width * t["mean_mm"] / 1.0e9), "kg/m3",
                           ("mass", "length", "width", "mean_thickness"), note="m / (L·W·t_mean)"))
    return tuple(out)


def thickness_readiness(passport: Passport, kind: str = PHYSICAL) -> tuple:
    """(state, detail): the normative t prior needs 9+ measured points (SPEC v1.1 §5); fewer only blocks it."""
    t = thickness_summary(passport, kind)
    if t["n_measured"] >= MIN_THICKNESS_POINTS:
        return PASS, f"{t['n_measured']} measured thickness points (≥ {MIN_THICKNESS_POINTS}): a t prior is possible"
    return BLOCKED, (f"{t['n_measured']} measured thickness points < {MIN_THICKNESS_POINTS} (SPEC v1.1 §5): viewing is "
                     "possible, the normative thickness prior is not")


def synthetic_values(passport: Passport) -> list:
    """The passport entries marked SYNTHETIC (allowed in a synthetic demonstration study only)."""
    out = [n for n in ("length", "width", "mass", "density") if getattr(passport, n).provenance == SYNTHETIC]
    out += [f"thickness {r.position}" for r in passport.thickness if r.thickness.provenance == SYNTHETIC]
    out += [n for n, c in passport.claims.items() if c.provenance == SYNTHETIC]
    out += [f"constant {c.name}" for c in passport.constants if c.quantity.provenance == SYNTHETIC]
    return out


# ----------------------------------------------------------------------------- the study

@dataclass(frozen=True)
class SourceRecord:
    role: str  # "experimental" or "fe"
    path: str
    sha256: str
    size: Optional[int] = None


@dataclass(frozen=True)
class Study:
    kind: str = PHYSICAL
    passport: Passport = field(default_factory=Passport)
    sources: Mapping[str, SourceRecord] = field(default_factory=dict)
    modal_set: Optional[Mapping[str, Any]] = None  # {"names": (display, key), "records": n}
    evidence: tuple = ()  # ev.EvidenceFact
    sensitivities: Optional[Mapping[str, Any]] = None  # the imported table (small JSON), with its SHA-256
    declaration: Optional[Mapping[str, Any]] = None  # the declared observation set, with its SHA-256
    diagnostics: Optional[Mapping[str, Any]] = None  # the last diagnostics (plain data)
    offline_result: Optional[Mapping[str, Any]] = None
    history: tuple = ()  # (utc, action, detail)
    created: str = ""

    def __post_init__(self) -> None:
        if self.kind not in (PHYSICAL, SYNTHETIC_DEMO):
            raise StudyRefused(f"unknown study kind {self.kind!r}")

    @property
    def synthetic(self) -> bool:
        return self.kind == SYNTHETIC_DEMO

    def logged(self, action: str, detail: str = "") -> "Study":
        return replace(self, history=self.history + ((_now(), action, detail),))


def new_study(kind: str = PHYSICAL) -> Study:
    return Study(kind=kind, created=_now(), history=((_now(), "created", kind),))


def plan_mm(passport: Passport) -> Optional[tuple]:
    a, b = passport.length.base(), passport.width.base()
    return None if a is None or b is None else (a, b)


def plan_tolerance_mm(passport: Passport) -> Optional[float]:
    values = [passport.length.base_uncertainty(), passport.width.base_uncertainty()]
    return None if None in values else max(values)


def evidence_result(study: Study, scan_coordinates_m=None, fe_plan_mm=None) -> ev.EvidenceResult:
    """The evidence evaluated anew from the facts (a stored status is never trusted). The scan points and the FE
    extent default to those of the study's diagnostics (the files read, or the synthetic inputs)."""
    diagnostics = study.diagnostics or {}
    if scan_coordinates_m is None and diagnostics.get("scan_points_m"):
        import numpy as np

        scan_coordinates_m = np.asarray(diagnostics["scan_points_m"], dtype=float)
    if fe_plan_mm is None and diagnostics.get("fe_extent_mm"):
        fe_plan_mm = tuple(diagnostics["fe_extent_mm"])
    return ev.evaluate(study.evidence, plan_mm(study.passport), plan_tolerance_mm(study.passport), study.kind,
                       scan_coordinates_m, fe_plan_mm)


# ----------------------------------------------------------------------------- Workspace sources (by SHA-256)

def modal_set_of(experimental_preview, set_index) -> Optional[dict]:
    sets = experimental_preview.sets if experimental_preview is not None else ()
    if set_index is None or not 0 <= set_index < len(sets):
        return None
    chosen = sets[set_index]
    return {"names": [chosen.display_name, chosen.key], "records": len(chosen.records)}


def link_sources(study: Study, experimental_identity, fe_identity, modal_set) -> Study:
    """Record the files read in the Workspace (their SHA-256) and the chosen modal set in the study."""
    sources = {}
    for role, identity in (("experimental", experimental_identity), ("fe", fe_identity)):
        if identity and identity.get("sha256"):
            sources[role] = SourceRecord(role, str(identity.get("path", "")), identity["sha256"], identity.get("size"))
    if not sources:
        raise StudyRefused("no file is read in the Workspace: read the FE results and the experimental file first")
    out = replace(study, sources=sources, modal_set=modal_set, diagnostics=None, declaration=None, offline_result=None)
    return out.logged("sources linked", "; ".join(f"{r} {s.sha256[:12]}…" for r, s in sources.items())
                      + (f"; set {modal_set['names'][0]}" if modal_set else "; no modal set"))


def set_diagnostics(study: Study, diagnostics: Mapping[str, Any]) -> Study:
    """New diagnostics replace the old ones; the declaration (it takes its frequencies from them) and an earlier
    offline result are removed and must be loaded / run again."""
    out = replace(study, diagnostics=dict(diagnostics), declaration=None, offline_result=None)
    return out.logged("modal diagnostics", f"{diagnostics.get('source')}: {len(diagnostics.get('experimental', []))} "
                      f"EXP, {len(diagnostics.get('fe_elastic', []))} elastic FE")


def source_status(study: Study, experimental_identity, fe_identity, modal_set) -> dict:
    """role → MATCH / CHANGED / NOT_READ / NOT_LINKED, and the modal set; a change invalidates the results."""
    out = {}
    for role, identity in (("experimental", experimental_identity), ("fe", fe_identity)):
        recorded = study.sources.get(role)
        current = (identity or {}).get("sha256")
        if recorded is None:
            out[role] = "NOT_LINKED"
        elif current is None:
            out[role] = "NOT_READ"
        else:
            out[role] = "MATCH" if current == recorded.sha256 else "CHANGED"
    if study.modal_set is None:
        out["modal_set"] = "NOT_LINKED"
    elif modal_set is None:
        out["modal_set"] = "NOT_CHOSEN"
    else:
        out["modal_set"] = "MATCH" if list(modal_set["names"]) == list(study.modal_set["names"]) and \
            modal_set["records"] == study.modal_set["records"] else "CHANGED"
    out["consistent"] = all(out[k] == "MATCH" for k in ("experimental", "fe", "modal_set"))
    return out


def file_sha256(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_source(study: Study, role: str, path: Optional[str] = None) -> tuple:
    """(state, detail): the file at its recorded path (or a new path the user chose) has the recorded SHA-256."""
    recorded = study.sources.get(role)
    if recorded is None:
        return "NOT_LINKED", f"no {role} source is recorded"
    target = Path(path or recorded.path)
    if not target.is_file():
        return "MISSING", f"{target} does not exist: choose the file's new location"
    digest = file_sha256(target)
    if digest != recorded.sha256:
        return "CHANGED", f"{target.name}: SHA-256 {digest[:12]}… is not the recorded {recorded.sha256[:12]}…"
    return "VERIFIED", f"{target} has the recorded SHA-256 {digest[:12]}…"


def relocate_source(study: Study, role: str, path: str) -> Study:
    state, detail = verify_source(study, role, path)
    if state != "VERIFIED":
        raise StudyRefused(detail)
    record = replace(study.sources[role], path=str(path))
    return replace(study, sources={**study.sources, role: record}).logged("source relocated", f"{role}: {path}")


# ----------------------------------------------------------------------------- modal diagnostics

def _cluster_groups(rows: Sequence[tuple]) -> list:
    """Groups of adjacent rows within the SPEC §12.4 trigger (3 % relative spacing); a trigger, never a pair."""
    from .identification_clusters import TriggerRow, cluster_triggers

    if len(rows) < 2:
        return []
    return [list(t.row_ids) for t in cluster_triggers([TriggerRow(r, hz, hz) for r, hz in rows])]


def fe_extent_mm(fe_preview) -> Optional[tuple]:
    """The in-plane extent (X, Y) of the FE geometry in mm (the model's units are taken as mm, as in the project)."""
    dataset = getattr(fe_preview, "dataset", None)
    if dataset is None or not dataset.modes:
        return None
    import numpy as np

    xyz = np.asarray(dataset.sorted_modes()[0].coordinates, dtype=float)
    span = xyz.max(axis=0) - xyz.min(axis=0)
    return float(span[0]), float(span[1])


def modal_diagnostics(experimental: Sequence[Mapping[str, Any]], fe_modes: Sequence[Mapping[str, Any]],
                      rigid_fe: Sequence[int] = (), source: str = "Workspace") -> dict:
    """Frequency diagnostics of every experimental record and every elastic FE mode: nearest and second FE by |Δf|,
    Δf = 100 (f_FE − f_EXP) / f_EXP, close groups. Never a pair, a MAC or an exclusion."""
    exp = [dict(r) for r in experimental]
    fe = [dict(m) for m in fe_modes]
    rows = []
    for r in exp:
        ranked = sorted(fe, key=lambda m: (abs(m["hz"] - r["hz"]), m["number"]))
        cand = [(m["number"], m["hz"], 100.0 * (m["hz"] - r["hz"]) / r["hz"]) for m in ranked[:2]]
        rows.append({"exp": r["number"], "f_exp_hz": r["hz"], "nearest": cand[0] if cand else None,
                     "second": cand[1] if len(cand) > 1 else None, "status": PROXIMITY_ONLY,
                     "admissible_record": r.get("admissible", False), "record": r.get("label", "")})
    exp_groups = _cluster_groups([(f"EXP{r['number']}", r["hz"]) for r in exp])
    fe_groups = _cluster_groups([(f"FE{m['number']}", m["hz"]) for m in fe])
    return {"source": source, "experimental": exp, "fe_elastic": fe, "fe_rigid_excluded": list(rigid_fe),
            "proximity": rows, "experimental_close_groups": exp_groups, "fe_close_groups": fe_groups,
            "pairs": [], "mac": NOT_AVAILABLE,
            "note": "Frequency proximity only: no pair, MAC, orientation or exclusion is made."}


def diagnostics_from_previews(experimental_preview, set_index, fe_preview) -> dict:
    """The diagnostics of the files read in the Workspace (the existing importers' data)."""
    from . import plate_study as ps

    if experimental_preview is None or fe_preview is None:
        raise StudyRefused("read the FE results and the experimental file on the Workspace page first")
    sets = experimental_preview.sets
    if set_index is None or not 0 <= set_index < len(sets):
        raise StudyRefused("choose the experimental modal set on the Analysis page")
    chosen = sets[set_index]
    experimental = [{"number": r.number, "hz": float(r.frequency_hz), "label": r.label,
                     "admissible": not r.provisional and not r.ambiguous} for r in chosen.records]
    elastic = ps.elastic_modes(fe_preview.dataset)
    numbers = {int(m.number) for m in elastic}
    fe_modes = [{"number": int(m.number), "hz": float(m.frequency_hz)} for m in elastic]
    rigid = [int(m.number) for m in fe_preview.dataset.sorted_modes() if int(m.number) not in numbers]
    out = modal_diagnostics(experimental, fe_modes, rigid, "Workspace")
    out["modal_set"] = {"names": [chosen.display_name, chosen.key], "records": len(chosen.records)}
    out["fe_extent_mm"] = fe_extent_mm(fe_preview)
    modes = chosen.dataset.sorted_modes() if chosen.dataset is not None else []
    out["scan_points_m"] = [list(map(float, xyz)) for xyz in modes[0].coordinates] if modes else []
    return out


SYNTHETIC_INPUTS_SCHEMA = "amc/synthetic-plate-inputs/v1"


def load_synthetic_inputs(source, study: Study) -> dict:
    """The diagnostics of a SYNTHETIC demonstration study from its declared synthetic inputs (records, FE modes,
    scan grid, FE extent); refused in a physical study. Never a physical experiment."""
    if not study.synthetic:
        raise StudyRefused("synthetic inputs belong to a synthetic demonstration study only")
    if isinstance(source, Mapping):
        data = dict(source)
    else:
        try:
            data = json.loads(Path(source).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise StudyRefused(f"the synthetic inputs cannot be read: {error}") from error
    if data.get("schema") != SYNTHETIC_INPUTS_SCHEMA or data.get("kind") != "SYNTHETIC":
        raise StudyRefused(f"not synthetic plate inputs (schema {SYNTHETIC_INPUTS_SCHEMA}, kind SYNTHETIC)")
    if (data.get("specimen") or {}).get("physical_specimen_id") != study.passport.physical_specimen_id:
        raise StudyRefused("the synthetic inputs are for another specimen")
    try:
        experimental = [{"number": int(r["number"]), "hz": float(r["hz"]), "label": "SYNTHETIC curve-fitted record",
                         "admissible": True} for r in data["experimental"]]
        fe_modes = [{"number": int(m["number"]), "hz": float(m["hz"])} for m in data["fe_elastic"]]
        points = [[float(v) for v in xyz] for xyz in data["scan_points_m"]]
        extent = [float(v) for v in data["fe_extent_mm"]]
    except (KeyError, TypeError, ValueError) as error:
        raise StudyRefused(f"the synthetic inputs are incomplete: {error}") from error
    out = modal_diagnostics(experimental, fe_modes, [int(m) for m in data.get("fe_rigid", [])], "SYNTHETIC")
    out.update(modal_set={"names": ["SYNTHETIC", "synthetic"], "records": len(experimental)}, fe_extent_mm=extent,
               scan_points_m=points, labels=[SYNTHETIC_LABEL])
    return out


# ----------------------------------------------------------------------------- readiness (observability)

@dataclass(frozen=True)
class Check:
    name: str
    state: str  # PASS / OPEN / BLOCKED
    detail: str


@dataclass(frozen=True)
class Readiness:
    status: str
    checks: tuple
    reasons: tuple
    sensitivity_plan: tuple
    scientific_status: str = SCIENTIFIC_STATUS


def sensitivity_plan(parameters: Sequence[str] = ("E_in_plane", "G12")) -> tuple:
    """What a sensitivity table of THIS FE model needs (nothing is run here)."""
    n = len(parameters)
    return (f"Parameters: {', '.join(parameters)} (E1 = E2 = E_in_plane: E1 ≠ E2 needs a traceable warp / fill "
            "orientation, SPEC v1.1 §5.2).",
            f"Central ±5 % finite differences (SPEC §6 S4): 2 × {n} = {2 * n} Abaqus Frequency solves of this plate's "
            "own FE model, plus the baseline already extracted — each a separate HUMAN-authorised Abaqus gate.",
            "Inputs: the FE model (INP) of this plate with its SHA-256, the baseline engineering constants (INITIAL / "
            "FIXED with provenance), the extraction of every variant with the pinned extractor, FE-to-FE branch "
            "tracking of every elastic mode (MAC ≥ 0.90; close pairs as clusters).",
            "Output: a table in the schema amc/fe-sensitivity-table/v1, tied to the FE manifest SHA-256 of this study; "
            "a table of another FE model or specimen is refused.",
            "No Abaqus run is started by this program.")


def readiness(study: Study, evidence: ev.EvidenceResult, current_sources: Optional[dict] = None,
              sensitivity_state: tuple = (BLOCKED, "no sensitivity table of this FE model is loaded"),
              declaration_state: tuple = (BLOCKED, "no declared observation set (FIT / HOLDOUT) is loaded"),
              rank_state: tuple = (BLOCKED, "no rank without a sensitivity table and declared observations")) -> Readiness:
    """Every condition of an identification, kept apart; NOT_READY_FOR_IDENTIFICATION while any is not PASS."""
    p = study.passport
    checks = []
    sources = current_sources or {}
    if study.synthetic:
        checks.append(Check("sources (identity)", OPEN, SYNTHETIC_LABEL + ": no physical file"))
    elif not study.sources:
        checks.append(Check("sources (identity)", BLOCKED, "no experimental file and FE package are linked"))
    else:
        state = PASS if sources.get("consistent") else BLOCKED
        checks.append(Check("sources (identity)", state, "; ".join(f"{k}: {v}" for k, v in sources.items()
                                                                     if k != "consistent") or "not checked"))
    diagnostics = study.diagnostics or {}
    exp = diagnostics.get("experimental", [])
    if not exp:
        checks.append(Check("modal fit quality", BLOCKED, "no diagnostics: run the modal diagnostics"))
    else:
        bad = [f"EXP{r['number']}" for r in exp if not r.get("admissible")]
        checks.append(Check("modal fit quality", PASS if not bad else OPEN,
                            f"{len(exp) - len(bad)} of {len(exp)} records are curve-fitted modes" +
                            (f"; not admissible (FRF peak or ambiguous): {', '.join(bad)}" if bad else "")))
    missing = [n for n, q in (("length", p.length), ("width", p.width), ("mass", p.mass)) if not q.available]
    t_state, t_detail = thickness_readiness(p, study.kind)
    geometry_state = BLOCKED if missing or t_state != PASS else PASS
    checks.append(Check("geometry and mass", geometry_state,
                        (f"NOT_AVAILABLE: {', '.join(missing)}; " if missing else "") + t_detail
                        + ("" if plan_tolerance_mm(p) is not None else "; length / width uncertainty NOT_AVAILABLE")))
    if not study.synthetic and synthetic_values(p):
        checks.append(Check("synthetic values", BLOCKED, "SYNTHETIC values in a physical study: "
                            + ", ".join(synthetic_values(p))))
    orientation = p.claim("material_orientation")
    checks.append(Check("material axes (warp / fill)", PASS if orientation.available and orientation.provenance in
                        (MEASURED, INSTRUMENT_RECORD, HUMAN_CONFIRMED, SYNTHETIC) else OPEN,
                        orientation.text() + " — without it only E1 = E2 = E_in_plane"))
    checks.append(Check("physical registration evidence", PASS if evidence.status == ev.COMPLETE else BLOCKED,
                        evidence.status + ("" if evidence.status == ev.COMPLETE else
                                           f": {len(evidence.missing)} open item(s)")))
    decision = ((study.declaration or {}).get("data") or {}).get("registration_decision") or {}
    decided = (decision.get("status") == "ADMISSIBLE_FOR_RESEARCH_COMPUTATION" and str(decision.get("reference") or "")
               and decision.get("provenance") == (SYNTHETIC if study.synthetic else HUMAN_CONFIRMED))
    checks.append(Check("registration decision (owner)", PASS if decided else BLOCKED,
                        (f"{decision.get('reference')} ({decision.get('provenance')}; recorded, not made here)"
                         if decided else "no owner decision is recorded; this program never makes one")))
    checks.append(Check("admissible mode pairs", PASS if declaration_state[0] == PASS else BLOCKED,
                        "only declared pairs on an admissible registration; no pair from frequency proximity"))
    groups = diagnostics.get("experimental_close_groups", []) + diagnostics.get("fe_close_groups", [])
    checks.append(Check("modal families and close groups", OPEN if groups else (PASS if exp else BLOCKED),
                        ("close groups (3 % trigger): " + "; ".join("/".join(g) for g in groups)) if groups else
                        ("no close group" if exp else "no diagnostics")))
    checks.append(Check("FE sensitivities of this model", *sensitivity_state))
    checks.append(Check("rank and condition", *rank_state))
    checks.append(Check("FIT / HOLDOUT", *declaration_state))
    checks.append(Check("uncertainties", OPEN, "Σ_meas NOT_AVAILABLE for PolyMAX-type fits unless measured (D-069); "
                        "Σ_setup 0.3 % PROVISIONAL until a repeat protocol"))
    suspension = p.claim("suspension")
    checks.append(Check("FE model applicability", OPEN, f"test set-up {suspension.text()} against the FE model's "
                        f"boundary conditions {p.claim('fe_model_version').text()}: an owner judgement, not checked "
                        "here"))
    reasons = tuple(f"{c.name}: {c.detail}" for c in checks if c.state != PASS)
    status = READY_FOR_REVIEW if not reasons else NOT_READY
    return Readiness(status, tuple(checks), reasons, sensitivity_plan())


# ----------------------------------------------------------------------------- persistence

def _quantity_dict(q: Quantity) -> dict:
    return asdict(q)


def _quantity(data: Mapping[str, Any], kind: str) -> Quantity:
    if not isinstance(data, Mapping):
        raise StudyRefused(f"a {kind} quantity is not an object")
    if data.get("kind", kind) != kind:
        raise StudyRefused(f"a {kind} quantity is recorded as {data.get('kind')!r}")
    try:
        return Quantity(kind, data.get("value"), data.get("unit", ""), data.get("provenance", NOT_AVAILABLE),
                        data.get("source", ""), data.get("method", ""), data.get("uncertainty"),
                        data.get("uncertainty_basis", ""), data.get("note", ""))
    except PassportError as error:
        raise StudyRefused(f"{kind}: {error}") from error


def passport_to_dict(p: Passport) -> dict:
    return {"design_id": p.design_id, "physical_specimen_id": p.physical_specimen_id, "test_run_id": p.test_run_id,
            "measurement_date": p.measurement_date, "measurement_method": p.measurement_method,
            "length": _quantity_dict(p.length), "width": _quantity_dict(p.width), "mass": _quantity_dict(p.mass),
            "density": _quantity_dict(p.density),
            "thickness": [{"position": r.position, "method": r.method, "thickness": _quantity_dict(r.thickness)}
                          for r in p.thickness],
            "claims": {k: asdict(v) for k, v in p.claims.items()},
            "constants": [{"name": c.name, "role": c.role, "quantity": _quantity_dict(c.quantity)}
                          for c in p.constants]}


def passport_from_dict(data: Mapping[str, Any]) -> Passport:
    try:
        claims = {k: Claim(v.get("value"), v.get("provenance", NOT_AVAILABLE), v.get("source", ""))
                  for k, v in (data.get("claims") or {}).items() if k in CLAIMS}
        thickness = tuple(ThicknessReading(str(r["position"]), _quantity(r["thickness"], "length"), r.get("method", ""))
                          for r in data.get("thickness") or ())
        constants = tuple(Constant(str(c["name"]), _quantity(c["quantity"], c["quantity"].get("kind", "modulus")),
                                   c["role"]) for c in data.get("constants") or ())
        return Passport(str(data.get("design_id", "")), str(data.get("physical_specimen_id", "")),
                        str(data.get("test_run_id", "")), str(data.get("measurement_date", "")),
                        str(data.get("measurement_method", "")), _quantity(data.get("length", {}), "length"),
                        _quantity(data.get("width", {}), "length"), _quantity(data.get("mass", {}), "mass"),
                        _quantity(data.get("density", {}), "density"), thickness, claims, constants)
    except (KeyError, TypeError, AttributeError, PassportError) as error:
        raise StudyRefused(f"the passport cannot be read: {error}") from error


def study_to_dict(study: Study, evidence: Optional[ev.EvidenceResult] = None) -> dict:
    """The study file. The registration status is written as computed (never 'accepted' or 'frozen') and is not
    trusted when the file is read again; heavy FE files are never written into it."""
    evidence = evidence or evidence_result(study)
    return {
        "schema": SCHEMA, "kind": study.kind, "created": study.created, "saved": _now(),
        "labels": list(LABELS) + ([SYNTHETIC_LABEL] if study.synthetic else []),
        "scientific_status": SCIENTIFIC_STATUS,
        "passport": passport_to_dict(study.passport),
        "derived": [asdict(d) for d in derived_quantities(study.passport)],
        "sources": {k: asdict(v) for k, v in study.sources.items()},
        "modal_set": study.modal_set,
        "evidence": [{"key": f.key, "value": f.value, "provenance": f.provenance, "source": f.source,
                      "derived_from": list(f.derived_from)} for f in study.evidence],
        "registration": {"status_when_saved": evidence.status, "frozen": False, "mac_computed": False,
                         "missing": [list(m) for m in evidence.missing],
                         "note": "recomputed from the evidence when the study is opened; never a frozen registration"},
        "sensitivities": study.sensitivities, "declaration": study.declaration,
        "diagnostics": study.diagnostics, "offline_result": study.offline_result,
        "approved_material_values": {"status": NOT_AVAILABLE,
                                     "reason": "no value passes the scientific criteria of a release (" +
                                               SCIENTIFIC_STATUS + ")"},
        "history": [list(h) for h in study.history],
    }


def study_from_dict(data: Mapping[str, Any]) -> Study:
    if not isinstance(data, Mapping) or data.get("schema") != SCHEMA:
        raise StudyRefused(f"not a single-plate study file (schema {SCHEMA})")
    try:
        evidence = tuple(ev.EvidenceFact(f["key"], f.get("value"), f["provenance"], f.get("source", ""),
                                         tuple(f.get("derived_from") or ())) for f in data.get("evidence") or ())
        sources = {k: SourceRecord(v["role"], v["path"], v["sha256"], v.get("size"))
                   for k, v in (data.get("sources") or {}).items()}
    except (KeyError, TypeError, ValueError) as error:
        raise StudyRefused(f"the study file cannot be read: {error}") from error
    if any(not isinstance(s.sha256, str) or len(s.sha256) != 64 for s in sources.values()):
        raise StudyRefused("a recorded source has no SHA-256")
    study = Study(kind=data.get("kind", PHYSICAL), passport=passport_from_dict(data.get("passport") or {}),
                  sources=sources, modal_set=data.get("modal_set"), evidence=evidence,
                  sensitivities=data.get("sensitivities"), declaration=data.get("declaration"),
                  diagnostics=data.get("diagnostics"), offline_result=data.get("offline_result"),
                  history=tuple(tuple(h) for h in data.get("history") or ()), created=data.get("created", ""))
    return study.logged("opened", "registration recomputed from the evidence")


def save_study(study: Study, path, evidence: Optional[ev.EvidenceResult] = None) -> Path:
    path = Path(path)
    data = study_to_dict(study.logged("saved", path.name), evidence)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def open_study(path) -> Study:
    path = Path(path)
    if not path.is_file():
        raise StudyRefused(f"{path} does not exist")
    if path.stat().st_size > 20 * 1024 * 1024:
        raise StudyRefused(f"{path.name} is larger than 20 MB: not a study file")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StudyRefused(f"{path.name} is not valid JSON: {error}") from error
    return study_from_dict(data)


# ----------------------------------------------------------------------------- export

def _csv(rows: Sequence[Sequence[Any]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    for row in rows:
        writer.writerow(row)
    return out.getvalue()


def export_report(study: Study, folder, evidence: ev.EvidenceResult, ready: Readiness) -> list:
    """Markdown, JSON and CSV tables into ``folder``; returns the files written. No approved material value."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = f"single_plate_{(study.passport.physical_specimen_id or 'study').replace(' ', '_')}_{stamp}"
    data = study_to_dict(study, evidence)
    data["readiness"] = {"status": ready.status, "checks": [asdict(c) for c in ready.checks],
                         "reasons": list(ready.reasons), "sensitivity_plan": list(ready.sensitivity_plan)}
    written = []
    path = folder / f"{base}.json"
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    written.append(path)
    diag = study.diagnostics or {}
    tables = {
        "frequencies": [("EXP", "f_EXP (Hz)", "nearest FE", "f_FE (Hz)", "Δf (%)", "second FE", "Δf (%)", "status")] +
                       [(f"EXP{r['exp']}", f"{r['f_exp_hz']:.4f}",
                         *(("FE%d" % r["nearest"][0], f"{r['nearest'][1]:.4f}", f"{r['nearest'][2]:+.2f}")
                           if r.get("nearest") else ("—", "—", "—")),
                         *(("FE%d" % r["second"][0], f"{r['second'][2]:+.2f}") if r.get("second") else ("—", "—")),
                         r["status"]) for r in diag.get("proximity", [])],
        "readiness": [("check", "state", "detail")] + [(c.name, c.state, c.detail) for c in ready.checks],
        "thickness": [("position", "value", "unit", "provenance", "method", "source")] +
                     [(r.position, r.thickness.value, r.thickness.unit, r.thickness.provenance, r.method,
                       r.thickness.source) for r in study.passport.thickness],
    }
    if study.offline_result:
        tables["offline_terms"] = [("term", "role", "f_EXP (Hz)", "f_model (Hz)", "residual (σ)")] + [
            (t["term"], t["role"], t["f_exp_hz"], t["f_model_hz"], t["residual"])
            for t in study.offline_result.get("terms", [])]
    for name, rows in tables.items():
        path = folder / f"{base}_{name}.csv"
        path.write_text(_csv(rows), encoding="utf-8")
        written.append(path)
    path = folder / f"{base}.md"
    path.write_text(markdown_report(study, evidence, ready), encoding="utf-8")
    written.append(path)
    return written


def markdown_report(study: Study, evidence: ev.EvidenceResult, ready: Readiness) -> str:
    p = study.passport
    lines = [f"# Single-plate research study — {p.physical_specimen_id or 'unnamed specimen'}", ""]
    if study.synthetic:
        lines += [f"**{SYNTHETIC_LABEL}**", ""]
    lines += [f"Labels: {' / '.join(LABELS)}. {SCIENTIFIC_STATUS}.", "",
              "## Identity", "",
              f"- design_id: {p.design_id or NOT_AVAILABLE}",
              f"- physical_specimen_id: {p.physical_specimen_id or NOT_AVAILABLE}",
              f"- test_run_id: {p.test_run_id or NOT_AVAILABLE}",
              f"- measured: {p.measurement_date or NOT_AVAILABLE} ({p.measurement_method or NOT_AVAILABLE})", "",
              "## Measurements", "",
              f"- length: {p.length.text()}", f"- width: {p.width.text()}", f"- mass: {p.mass.text()}",
              f"- density: {p.density.text()}"]
    t = thickness_summary(p, study.kind)
    lines.append(f"- thickness: {t['n']} readings" + (f", mean {t['mean_mm']:.4f} mm, observed scatter "
                                                       f"{t['sd_mm']:.4f} mm (not an instrument uncertainty)"
                                                       if t["sd_mm"] is not None else ""))
    lines += [f"- {name}: {p.claim(name).text()}" for name in CLAIMS]
    lines += [f"- constant {c.name} ({c.role}): {c.quantity.text()}" for c in p.constants]
    lines += ["", "Derived:", ""] + [f"- {d.name}: " + (f"{d.value:.6g} {d.unit}" if d.value is not None else
                                                        NOT_AVAILABLE) + f" ({d.provenance}; from {', '.join(d.basis)})"
                                     for d in derived_quantities(p)]
    lines += ["", "## Sources", ""] + ([f"- {r}: {s.path} — SHA-256 {s.sha256}" for r, s in study.sources.items()]
                                       or ["- none linked"])
    if study.modal_set:
        lines.append(f"- modal set: {study.modal_set['names'][0]} ({study.modal_set['records']} records)")
    lines += ["", "## Physical registration evidence", "", f"Status: **{evidence.status}** (never frozen here; no MAC).",
              ""] + [f"- missing / refused: {k} — {why}" for k, why in evidence.missing] + \
             [f"- check: {c[0]} — {c[1]} — {c[2]}" for c in evidence.checks]
    diag = study.diagnostics
    lines += ["", "## Modal diagnostics (frequency proximity only, never pairs)", ""]
    if diag:
        lines += ["| EXP | f_EXP (Hz) | nearest FE | Δf (%) | second | Δf (%) |", "|---|---|---|---|---|---|"]
        for r in diag.get("proximity", []):
            n, s = r.get("nearest"), r.get("second")
            lines.append(f"| EXP{r['exp']} | {r['f_exp_hz']:.4f} | " + (f"FE{n[0]} {n[1]:.4f} | {n[2]:+.2f}" if n else
                                                                         "— | —") + " | " +
                         (f"FE{s[0]} | {s[2]:+.2f}" if s else "— | —") + " |")
        lines.append(f"\nFE rigid-body modes excluded by the code's shape criterion: {diag.get('fe_rigid_excluded')}")
    else:
        lines.append("Not run.")
    lines += ["", f"## Readiness: {ready.status}", ""] + [f"- {c.name}: {c.state} — {c.detail}" for c in ready.checks]
    lines += ["", "Sensitivity plan (nothing is run here):", ""] + [f"- {x}" for x in ready.sensitivity_plan]
    lines += ["", "## Offline research study", ""]
    result = study.offline_result
    if result:
        lines += [f"Status: {result.get('status')} — {' / '.join(result.get('labels', []))}", ""]
        lines += [f"- {k}: {v}" for k, v in (result.get("candidate") or {}).items()]
        lines += [f"- limit: {x}" for x in result.get("limits", [])]
    else:
        lines.append("Not run.")
    lines += ["", "## Approved material values", "", f"{NOT_AVAILABLE}: {SCIENTIFIC_STATUS}.", "",
              "## History", ""] + [f"- {h[0]} {h[1]} {h[2] if len(h) > 2 else ''}" for h in study.history]
    return "\n".join(lines) + "\n"


__all__ = ["BLOCKED", "CLAIMS", "Check", "Claim", "Constant", "NOT_AVAILABLE", "NOT_READY", "OPEN", "PASS",
           "PHYSICAL", "Passport", "PassportError", "Quantity", "Readiness", "SCHEMA", "SYNTHETIC_DEMO",
           "SYNTHETIC_LABEL", "SourceRecord", "Study", "StudyRefused", "ThicknessReading", "derived_quantities",
           "diagnostics_from_previews", "evidence_result", "export_report", "link_sources", "modal_diagnostics",
           "modal_set_of", "new_study", "open_study", "readiness", "relocate_source", "save_study",
           "sensitivity_plan", "source_status", "study_from_dict", "study_to_dict", "set_diagnostics",
           "load_synthetic_inputs", "thickness_readiness",
           "thickness_summary", "verify_source"]
