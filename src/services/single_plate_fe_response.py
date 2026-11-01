"""PRIORITY-10: the FE Response Workbench of one single plate — FE-only (no Qt; RESEARCH_ONLY).

One FE model of a plate, its baseline and its already solved perturbation states (one parameter changed per state)
are read from their extracted packages (the existing importer and ``fe_package_identity``). The existing research
method of PRIORITY-2 (``research/plate_s4/run_s4.py``) becomes a reusable function:

- every elastic FE mode of the baseline is followed into each state by FE-to-FE MAC (``plate_study.sensitivity_table``:
  ``branch_tracker.track_branches`` under ``STRICT_IDENTIFICATION_PAIRING``, close pairs by
  ``identification_clusters.confirm_cluster``; the code's rigid-body criterion through ``plate_study.elastic_modes``);
  nothing is matched by frequency, a lost branch keeps its exact reason, a confirmed cluster is one term (mean ln f);
- the central sensitivity of each followed term is ``s = (ln f₊ − ln f₋) / (ln p₊ − ln p₋)`` with the ACTUAL parameter
  values of the two states; when either side is not followed it is ``NOT_TRACKED — CENTRAL_SENSITIVITY_UNAVAILABLE``
  (never replaced by a one-sided difference, which is only shown as a linearity diagnostic);
- the FE-only rank of the sensitivity matrix; E (E1 = E2) only as the CONDITIONAL_SUPERPOSITION s_E1 + s_E2 (no joint
  state was solved);
- the FE-only What-If: ``ln f_trial = ln f0 + Σ s_j ln(p_trial_j / p0_j)`` inside the range the solved states span
  (never extrapolated), compared with the solved FE points where they exist. It is not an Abaqus solve, not a
  linearity proof (the ±2.5 % repeat is missing) and never a material identification.

Kinds of result: LIVE_FE_PACKAGE_ANALYSIS (the shapes read and followed now), ARCHIVED_FE_RESULT (a SHA-checked
historical table, never a new FE-to-FE MAC), FREQUENCY_ONLY (no shapes: following not proven), INCOMPLETE_FE_FAMILY (a
needed state is missing). Experimental records are shown beside the FE frequencies only as FREQUENCY_PROXIMITY_ONLY:
no pair, no MAC objective, no choice of a parameter from a measured frequency.

PRIORITY-10-F1: the results stay bound to their sources. ``verify_sources`` checks every manifest, every package
(``fe_package_identity``: every shape and geometry file), every INP and .dat and the presence of every used state;
any difference makes the results STALE. A declaration's moduli are converted to MPa from supported units only, and its
values are checked against the INPs it names.

Nothing here runs Abaqus, Abaqus Python, an extraction, an LM or Auto-ID, and no disk is searched: only the files and
the folder the user names are read. M8 GATE NOT_MET, D-077 NO_GLOBAL_PARAMETER_VALUE and production Auto-ID BLOCKED are
unchanged.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from services import plate_study as ps
from services import research_results_reader as rrr
from services.practical_identifiability import RCOND

SCHEMA_FAMILY = "amc/fe-family/v1"
SCHEMA_SESSION = "amc/fe-response-session/v1"
LIVE = "LIVE_FE_PACKAGE_ANALYSIS"
ARCHIVED = "ARCHIVED_FE_RESULT"
FREQUENCY_ONLY = "FREQUENCY_ONLY"
INCOMPLETE = "INCOMPLETE_FE_FAMILY"
SYNTHETIC_TEST = "SYNTHETIC_TEST"
UNAVAILABLE = "NOT_TRACKED — CENTRAL_SENSITIVITY_UNAVAILABLE"
CONDITIONAL = "CONDITIONAL_SUPERPOSITION"
PREDICTION = "FE_ONLY_LOCAL_PREDICTION — not an Abaqus solve"
PROXIMITY_ONLY = "FREQUENCY_PROXIMITY_ONLY — NOT A MODE PAIR"
TRACKED_STATES = ("TRACKED", "TRACKED_CLUSTER")
LABELS = ("RESEARCH_ONLY", "FE_ONLY", "NOT_A_MATERIAL_PROPERTY", "NO_EXPERIMENTAL_PAIRING")
LIMITS = (
    "FE-only: sensitivities and predictions describe this FE model, not the physical plate and not a material.",
    "A prediction is the local log-linear formula, not an Abaqus solve; it is never extrapolated beyond the solved "
    "states, and the ±5 % range is not a confirmed linear range without the ±2.5 % repeat.",
    "E1 and E2 are FE model directions: without a traceable warp / fill orientation they are not independent constants "
    "of the physical CFRP.",
    "E (E1 = E2) is a CONDITIONAL_SUPERPOSITION of the separate E1 and E2 states: no joint state was solved.",
    "Experimental records are never paired with FE branches here: frequency proximity only, no MAC objective, no "
    "parameter chosen from a measured frequency.",
)
SCIENTIFIC_STATUS = ("M8 GATE NOT_MET · D-077 NO_GLOBAL_PARAMETER_VALUE · production Auto-ID BLOCKED · no material "
                     "value is released here")


class FamilyRefused(ValueError):
    """The FE family cannot be read or is not one family; the message says why."""


class WhatIfRefused(ValueError):
    """The FE-only prediction is refused (out of range, another FE model, no sensitivity)."""


def sha256_file(path, cancel: Optional[threading.Event] = None) -> Optional[str]:
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                if cancel is not None and cancel.is_set():
                    raise FamilyRefused("cancelled")
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


# ----------------------------------------------------------------------------- the family

@dataclass(frozen=True)
class FEMember:
    member_id: str
    role: str  # "baseline" or "variant"
    manifest: Optional[str]  # extracted package (shapes); None: frequencies only
    parameter: Optional[str] = None
    value: Optional[float] = None
    unit: str = "MPa"
    inp: Optional[str] = None
    dat: Optional[str] = None
    solver_log: Optional[str] = None
    run_record: Optional[Mapping[str, Any]] = None  # the solver run row (exit, completed, ODB SHA-256)
    provenance: str = ""
    declared: str = ""  # the value as declared when its unit was not MPa (``value`` is always MPa)


@dataclass(frozen=True)
class Family:
    model_id: str
    specimen_id: str
    baseline: FEMember
    baseline_parameters: Mapping[str, float]
    variants: tuple
    kind: str = "FE_MODEL"  # or SYNTHETIC_TEST
    geometry_note: str = ""
    provenance: str = ""
    problems: tuple = ()  # members that could not be declared, with the reason
    checks: tuple = ()  # what was checked against the INPs, and what could not be

    def parameters(self) -> tuple:
        return tuple(dict.fromkeys(v.parameter for v in self.variants if v.parameter))


MATERIAL_KEYS = ("E1", "E2", "E3", "nu12", "nu13", "nu23", "G12", "G13", "G23", "rho", "h")
MODULI = ("E1", "E2", "E3", "G12", "G13", "G23")
# the supported units of a modulus as factors to MPa; case-sensitive ("mPa" is not "MPa"), nothing else is guessed
MODULUS_UNITS = {"MPa": 1.0, "N/mm2": 1.0, "N/mm^2": 1.0, "N/mm²": 1.0, "GPa": 1.0e3, "kPa": 1.0e-3, "Pa": 1.0e-6,
                 "N/m2": 1.0e-6, "N/m^2": 1.0e-6, "N/m²": 1.0e-6}
VALUE_TOLERANCE = 1e-6  # relative: a declared value against its INP constant (the INP prints a few decimals)


def to_mpa(value, unit, what: str) -> float:
    """``value`` in ``unit`` as MPa. An unsupported unit, or a value that is not a positive finite number, is
    refused."""
    factor = MODULUS_UNITS.get(str(unit).strip()) if unit is not None else None
    if factor is None:
        raise FamilyRefused(f"{what}: the unit {unit!r} is not supported for a modulus (supported: "
                            f"{', '.join(MODULUS_UNITS)}); nothing is converted by guess")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise FamilyRefused(f"{what}: {value!r} is not a number") from None
    if not math.isfinite(number) or number <= 0.0:
        raise FamilyRefused(f"{what}: {number:g} is not a positive modulus")
    return number * factor


def _differs(a: float, b: float) -> bool:
    return abs(a - b) > VALUE_TOLERANCE * max(abs(a), abs(b))


def _member_from(data: Mapping[str, Any], base: Path, role: str) -> FEMember:
    def path(key):
        value = data.get(key)
        if not value:
            return None
        p = Path(value)
        return str(p if p.is_absolute() else (base / p))
    member_id = str(data.get("id") or data.get("member_id") or role)
    parameter, value, unit = data.get("parameter"), data.get("value"), data.get("unit") or "MPa"
    declared = str(data.get("declared") or "")
    if role == "variant" and parameter is not None and parameter not in MODULI:
        raise FamilyRefused(f"{member_id}: {parameter} is not an elastic modulus ({', '.join(MODULI)}): not supported "
                            "as a parameter of an FE family")
    if value is not None:
        mpa = to_mpa(value, unit, f"{member_id}: {parameter}")
        if MODULUS_UNITS[str(unit).strip()] != 1.0:
            declared = f"{float(value):g} {str(unit).strip()}"
        value = mpa
    return FEMember(member_id, role, path("manifest"), parameter, value, "MPa", path("inp"), path("dat"),
                    path("solver_log"), data.get("run_record"), str(data.get("provenance") or ""), declared)


def _baseline_values(data: Mapping[str, Any]) -> dict:
    """The declared baseline values in MPa: a number (in ``baseline_unit``, MPa by default) or {"value", "unit"}."""
    default = data.get("baseline_unit") or "MPa"
    out = {}
    for name, item in (data.get("baseline_parameters") or {}).items():
        if name not in MODULI:
            raise FamilyRefused(f"the baseline {name} is not an elastic modulus ({', '.join(MODULI)}): not supported "
                                "as a parameter of an FE family")
        value, unit = (item.get("value"), item.get("unit") or default) if isinstance(item, Mapping) else (item, default)
        out[str(name)] = to_mpa(value, unit, f"the baseline {name}")
    return out


def _parse_family(data: Mapping[str, Any], base: Path) -> Family:
    if data.get("schema") != SCHEMA_FAMILY:
        raise FamilyRefused(f"not an FE family declaration ({SCHEMA_FAMILY})")
    params = _baseline_values(data)
    if not params:
        raise FamilyRefused("the baseline parameter values are not declared")
    baseline = _member_from(data.get("baseline") or {}, base, "baseline")
    if not baseline.manifest:
        raise FamilyRefused("the baseline needs an extracted package (manifest.json): its shapes are the reference")
    variants = tuple(_member_from(v, base, "variant") for v in data.get("variants") or ())
    for v in variants:
        if not v.parameter or v.value is None:
            raise FamilyRefused(f"{v.member_id}: the changed parameter and its value are not declared")
        if v.parameter not in params:
            raise FamilyRefused(f"{v.member_id}: {v.parameter} has no baseline value")
    return Family(str(data.get("model_id") or "NOT_AVAILABLE"), str(data.get("specimen_id") or "NOT_AVAILABLE"),
                  baseline, params, variants, str(data.get("kind") or "FE_MODEL"), str(data.get("geometry") or ""),
                  str(data.get("provenance") or ""))


def _inp_values(path, what: str, unit: str) -> dict:
    """The material constants of an INP, the moduli in MPa (``unit``: the model's stress unit)."""
    if not Path(path).is_file():
        raise FamilyRefused(f"{what}: the INP {path} is missing")
    values = _read_inp(path)
    if not any(k in values for k in MODULI):
        raise FamilyRefused(f"{what}: {path} has no *Elastic, type=ENGINEERING CONSTANTS: the declared values cannot "
                            "be checked")
    return {k: (to_mpa(v, unit, f"{what}: {k} of its INP") if k in MODULI else v) for k, v in values.items()}


def _check_inps(family: Family, inp_unit: str) -> tuple:
    """Every declared value against the INP of its member: the baseline values, each state's changed parameter, and no
    other material constant of a state differing from the baseline INP. A mismatch refuses the declaration; what
    cannot be checked (no INP) is named."""
    notes = []
    base_inp = _inp_values(family.baseline.inp, "the baseline", inp_unit) if family.baseline.inp else None
    if base_inp is not None:
        for p, value in family.baseline_parameters.items():
            if p not in base_inp:
                raise FamilyRefused(f"the baseline: {p} is declared but its INP does not define it")
            if _differs(value, base_inp[p]):
                raise FamilyRefused(f"the baseline: {p} is declared {value:g} MPa but its INP has {base_inp[p]:g} MPa")
        notes.append("baseline: the declared values equal its INP")
    else:
        notes.append("baseline: no INP — the declared baseline values are not checked against a model input")
    for v in family.variants:
        if not v.inp:
            notes.append(f"{v.member_id}: no INP — the declared {v.parameter} is not checked and another material "
                         "change cannot be excluded")
            continue
        values = _inp_values(v.inp, v.member_id, inp_unit)
        if v.parameter not in values:
            raise FamilyRefused(f"{v.member_id}: {v.parameter} is declared but its INP does not define it")
        if _differs(v.value, values[v.parameter]):
            raise FamilyRefused(f"{v.member_id}: {v.parameter} is declared {v.value:g} MPa but its INP has "
                                f"{values[v.parameter]:g} MPa")
        if base_inp is not None:
            changed = [k for k in MATERIAL_KEYS if k != v.parameter and (k in base_inp or k in values) and (
                k not in base_inp or k not in values or _differs(base_inp[k], values[k]))]
            if changed:
                raise FamilyRefused(f"{v.member_id}: its INP also changes {', '.join(changed)} against the baseline "
                                    "INP, which the declaration does not state: not a one-parameter state")
            notes.append(f"{v.member_id}: {v.parameter} equals its INP; no other material constant differs from the "
                         "baseline INP")
        else:
            others = [p for p, value in family.baseline_parameters.items() if p != v.parameter and (
                p not in values or _differs(value, values[p]))]
            if others:
                raise FamilyRefused(f"{v.member_id}: its INP also changes {', '.join(others)} against the declared "
                                    "baseline values, which the declaration does not state")
            notes.append(f"{v.member_id}: {v.parameter} equals its INP; without a baseline INP only the declared "
                         "parameters are compared")
    return tuple(notes)


def family_from_declaration(source) -> Family:
    """A family declared in JSON (schema ``amc/fe-family/v1``): model and specimen ids, the baseline and its parameter
    values, and the states, each with its manifest (or .dat for frequencies only), parameter, value and unit. Paths
    may be relative to the declaration file.

    Only elastic moduli are parameters. Each value is converted to MPa from its unit (MPa when none is given; the
    supported units are ``MODULUS_UNITS``); another unit is refused. Where a member names its INP, the declared values
    are checked against it (``inp_modulus_unit``: the model's stress unit, MPa by default): a different value, or a
    state whose INP changes another material constant, refuses the declaration."""
    if isinstance(source, Mapping):
        data, base = dict(source), Path(".")
    else:
        path = Path(source)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise FamilyRefused(f"{path} cannot be read as an FE family ({error})") from error
        base = path.parent
    if not isinstance(data, Mapping):
        raise FamilyRefused(f"not an FE family declaration ({SCHEMA_FAMILY})")
    family = _parse_family(data, base)
    return replace(family, checks=_check_inps(family, data.get("inp_modulus_unit") or "MPa"))


def family_from_record(data: Mapping[str, Any]) -> Family:
    """The family a session recorded (``family_to_dict``: values in MPa, absolute paths). Nothing is read from disk:
    the sources are verified by ``session_state`` / ``verify_sources``."""
    family = _parse_family(data, Path("."))
    return replace(family, problems=tuple(tuple(p) for p in data.get("problems") or ()),
                   checks=tuple(data.get("checks") or ()))


def _read_inp(path) -> dict:
    try:
        return ps.parse_inp_material(Path(path).read_text(encoding="ascii", errors="replace"))
    except OSError:
        return {}


def family_from_folder(folder, baseline_manifest, model_id: str, specimen_id: str,
                       baseline_parameters: Optional[Mapping[str, float]] = None, baseline_inp=None,
                       parameters: Sequence[str] = ("E1", "E2", "G12"), kind: str = "FE_MODEL") -> Family:
    """The family of a folder the user chose: each direct sub-folder holding an extracted package
    (``extraction/manifest.json`` or ``manifest.json``) and one INP is a state. Its changed parameter and value come
    from its INP against the baseline's (``baseline_inp``) or the declared ``baseline_parameters``: exactly one of
    ``parameters`` must differ, every other constant must be equal. A ``SOLVER_RUNS.csv`` in the folder gives the run
    records. Nothing outside the folder is searched; a sub-folder that is not a one-parameter state is listed in
    ``problems``, never guessed."""
    folder = Path(folder)
    if not folder.is_dir():
        raise FamilyRefused(f"{folder} is not a folder")
    base_values = dict(_read_inp(baseline_inp)) if baseline_inp else {}
    if baseline_inp and not base_values:
        raise FamilyRefused(f"the baseline INP {baseline_inp} cannot be read or has no material constants")
    for k, v in (baseline_parameters or {}).items():
        if k in base_values and _differs(float(v), base_values[k]):
            raise FamilyRefused(f"the baseline {k} is declared {float(v):g} MPa but the baseline INP has "
                                f"{base_values[k]:g} MPa")
        base_values[k] = float(v)
    if not all(p in base_values for p in parameters):
        raise FamilyRefused("the baseline values of " + ", ".join(p for p in parameters if p not in base_values)
                            + " are not known: choose the baseline INP or declare them")
    runs = {}
    runs_csv = folder / "SOLVER_RUNS.csv"
    if runs_csv.is_file():
        with open(runs_csv, newline="", encoding="utf-8") as stream:
            runs = {r["job"]: r for r in csv.DictReader(stream)}
    variants, problems = [], []
    for sub in sorted(p for p in folder.iterdir() if p.is_dir()):
        manifest = next((m for m in (sub / "extraction" / "manifest.json", sub / "manifest.json") if m.is_file()), None)
        if manifest is not None and manifest.resolve() == Path(baseline_manifest).resolve():
            continue  # the baseline itself
        inps = sorted(sub.glob("*.inp"))
        dats = sorted(sub.glob("*.dat"))
        if manifest is None and not dats:
            continue
        if len(inps) != 1:
            problems.append((sub.name, f"{len(inps)} INP files: the changed parameter cannot be read"))
            continue
        values = _read_inp(inps[0])
        changed = [p for p in parameters if p in values and abs(values[p] - base_values[p]) >
                   1e-9 * max(1.0, abs(base_values[p]))]
        others = [k for k in MATERIAL_KEYS if k not in parameters and k in values and k in base_values
                  and abs(values[k] - base_values[k]) > 1e-9 * max(1.0, abs(base_values[k]))]
        if len(changed) != 1 or others:
            problems.append((sub.name, f"not a one-parameter state (changed: {changed + others or 'none'})"))
            continue
        logs = [p for p in (sub / f"{sub.name}.sta", sub / "abaqus_console.log") if p.is_file()]
        variants.append(FEMember(sub.name, "variant", str(manifest) if manifest else None, changed[0],
                                 float(values[changed[0]]), "MPa", str(inps[0]), str(dats[0]) if dats else None,
                                 str(logs[0]) if logs else None, runs.get(sub.name),
                                 f"the folder {folder} (INP-declared value)"))
    baseline = FEMember("baseline", "baseline", str(baseline_manifest), None, None, "MPa",
                        str(baseline_inp) if baseline_inp else None, provenance="chosen by the user")
    checks = (("baseline: its values from its INP" if baseline_inp else "baseline: declared values (no INP)"),
              "each state: its parameter and value read from its own INP (MPa: the model's N-mm units); every other "
              "material constant equal to the baseline's")
    return Family(model_id, specimen_id, baseline, {p: float(base_values[p]) for p in parameters}, tuple(variants),
                  kind, provenance=f"folder {folder}", problems=tuple(problems), checks=checks)


def family_to_dict(family: Family) -> dict:
    def member(m: FEMember) -> dict:
        return {"id": m.member_id, "manifest": m.manifest, "parameter": m.parameter, "value": m.value, "unit": m.unit,
                "declared": m.declared or None, "inp": m.inp, "dat": m.dat, "solver_log": m.solver_log,
                "run_record": m.run_record, "provenance": m.provenance}
    return {"schema": SCHEMA_FAMILY, "model_id": family.model_id, "specimen_id": family.specimen_id,
            "kind": family.kind, "geometry": family.geometry_note, "provenance": family.provenance,
            "baseline_parameters": dict(family.baseline_parameters), "baseline": member(family.baseline),
            "variants": [member(v) for v in family.variants], "problems": [list(p) for p in family.problems],
            "checks": list(family.checks)}


# ----------------------------------------------------------------------------- identities

def identities(family: Family, cancel: Optional[threading.Event] = None) -> list:
    """Per member: the manifest SHA-256, the package identity (``fe_package_identity``: every file the loader reads),
    the INP / .dat / solver-log SHA-256, the ODB against its run record, and exactly what cannot be verified."""
    from services import fe_package_identity as fpi

    out = []
    for m in (family.baseline,) + tuple(family.variants):
        row = {"id": m.member_id, "role": m.role, "parameter": m.parameter, "value": m.value, "unit": m.unit,
               "manifest": m.manifest, "manifest_sha256": None, "package_sha256": None, "inp": m.inp,
               "inp_sha256": None, "dat": m.dat, "dat_sha256": None, "solver_log_sha256": None, "odb": None,
               "odb_state": None, "not_verified": []}
        if m.manifest:
            row["manifest_sha256"] = sha256_file(m.manifest, cancel)
            try:
                row["package_sha256"] = fpi.identify(m.manifest, cancel)["package_sha256"]
            except Exception as error:  # noqa: BLE001  (an incomplete package is reported, never assumed)
                row["not_verified"].append(f"the package files ({error})")
        else:
            row["not_verified"].append("no extracted package: no shapes, FE-to-FE tracking impossible")
        for key, path in (("inp_sha256", m.inp), ("dat_sha256", m.dat), ("solver_log_sha256", m.solver_log)):
            if path:
                row[key] = sha256_file(path, cancel)
        if not m.inp:
            row["not_verified"].append("no INP: the parameter value and the model input cannot be checked")
        recorded_odb = (m.run_record or {}).get("odb_sha256")
        folder = Path(m.inp).parent if m.inp else (Path(m.manifest).parent.parent if m.manifest else None)
        odb = folder / f"{m.member_id}.odb" if folder is not None else None
        if recorded_odb and odb is not None and odb.is_file():
            now = sha256_file(odb, cancel)
            row["odb"], row["odb_state"] = str(odb), "VERIFIED_SHA256" if now == recorded_odb else "CHANGED"
        else:
            row["not_verified"].append("the ODB (not present or no recorded SHA-256): the package's origin from its "
                                       "solve is not verified")
        if m.run_record:
            if str(m.run_record.get("inp_sha256") or "") and row["inp_sha256"] and \
                    m.run_record["inp_sha256"] != row["inp_sha256"]:
                row["not_verified"].append("the INP differs from the solver run record")
            row["run"] = {k: m.run_record.get(k) for k in ("exit_code", "sta_completed", "note")}
        out.append(row)
    return out


# ----------------------------------------------------------------------------- reading and tracking

def _dataset(manifest, cancel: Optional[threading.Event] = None):
    from services import local_fe_preview
    from services.importer_runtime import ensure_application_importers

    ensure_application_importers()
    return local_fe_preview.preview_fe_package(manifest, cancel).dataset


def _geometry(dataset) -> str:
    from scientific_state import modal_dataset_geometry_identity

    return modal_dataset_geometry_identity(dataset)["sha256"]


def _completeness(family: Family, readable: Mapping[str, Any]) -> dict:
    """parameter → {"minus": id, "plus": id} of the nearest solved states below / above the baseline, or the missing
    side(s)."""
    out = {}
    for parameter in family.parameters():
        p0 = family.baseline_parameters[parameter]
        below = sorted((v for v in family.variants if v.parameter == parameter and v.value < p0
                        and v.member_id in readable), key=lambda v: p0 - v.value)
        above = sorted((v for v in family.variants if v.parameter == parameter and v.value > p0
                        and v.member_id in readable), key=lambda v: v.value - p0)
        out[parameter] = {"minus": below[0].member_id if below else None, "plus": above[0].member_id if above else None,
                          "missing": [s for s, x in (("−", below), ("+", above)) if not x]}
    return out


def analyse(family: Family, cancel: Optional[threading.Event] = None, progress=None) -> dict:
    """Read the baseline and every state, follow every elastic FE branch and compute the central sensitivities."""
    def say(text):
        if progress is not None:
            progress(text)
    say("reading the baseline package")
    try:
        base = _dataset(family.baseline.manifest, cancel)
    except Exception as error:  # noqa: BLE001
        raise FamilyRefused(f"the baseline package cannot be read ({error})") from error
    base_geometry = _geometry(base)
    datasets, excluded = {}, []
    for v in family.variants:
        if cancel is not None and cancel.is_set():
            raise FamilyRefused("cancelled")
        if not v.manifest:
            excluded.append((v.member_id, f"{FREQUENCY_ONLY}: no extracted package (shapes); following not proven"))
            continue
        say(f"reading {v.member_id}")
        try:
            ds = _dataset(v.manifest, cancel)
        except Exception as error:  # noqa: BLE001
            excluded.append((v.member_id, f"cannot be read ({error})"))
            continue
        if _geometry(ds) != base_geometry:
            excluded.append((v.member_id, "INCOMPATIBLE_FE_GEOMETRY: not the baseline's nodes and coordinates; no "
                                          "FE-to-FE MAC"))
            continue
        datasets[v.member_id] = (ds, v.parameter, v.value / family.baseline_parameters[v.parameter])
    complete = _completeness(family, datasets)
    say("following the FE branches (FE-to-FE MAC)")
    table = ps.sensitivity_table(base, datasets) if datasets else None
    rows = table.rows if table else ()
    hz0 = {row.row_id: row.baseline_hz for row in rows}
    branches = []
    for row in rows:
        per = {}
        for vid, value in row.tracked.items():
            if value is None:
                continue
            ok = value[3] in TRACKED_STATES
            cand = value[0]
            per[vid] = {"status": value[3].split(":")[0] if not ok else value[3], "reason": None if ok else value[3],
                        "candidate": ("+".join(f"FE{m}" for m in cand) if isinstance(cand, (tuple, list)) else
                                      f"FE{cand}") if ok else None,
                        "hz": (list(value[1]) if isinstance(value[1], (tuple, list)) else value[1]) if ok else None,
                        "mac": (min(value[2]) if isinstance(value[2], (tuple, list)) else value[2]) if ok else None,
                        "permutation": bool(ok and not isinstance(cand, (tuple, list)) and cand != row.baseline_mode)}
        branches.append({"branch": row.row_id, "baseline_mode": row.baseline_mode, "hz": row.baseline_hz,
                         "cluster": "+".join(row.cluster) if row.cluster else None, "variants": per})
    clusters = [{"rows": list(ids), "status": status, "reasons": list(reasons)}
                for ids, status, reasons in (table.clusters if table else ())]

    def log_f(row, vid):
        value = row.tracked.get(vid)
        if not value or value[3] not in TRACKED_STATES:
            return None
        return float(np.mean(np.log(value[1]))) if value[3] == "TRACKED_CLUSTER" else math.log(value[1])

    central = []
    for row in rows:
        if row.cluster and row.row_id != row.cluster[0]:
            continue  # a confirmed cluster is ONE term (mean ln f), never two rows
        term = "+".join(row.cluster) if row.cluster else row.row_id
        lf0 = (float(np.mean([math.log(hz0[r]) for r in row.cluster])) if row.cluster else math.log(row.baseline_hz))
        entry = {"term": term, "f0_hz": math.exp(lf0), "cluster": bool(row.cluster), "parameters": {}}
        for parameter, sides in complete.items():
            p0 = family.baseline_parameters[parameter]
            item = {"p0": p0, "minus_state": sides["minus"], "plus_state": sides["plus"]}
            if sides["missing"]:
                item.update(status=f"{INCOMPLETE}: no {' / '.join(sides['missing'])} state", s=None)
                entry["parameters"][parameter] = item
                continue
            vm = next(v for v in family.variants if v.member_id == sides["minus"])
            vp = next(v for v in family.variants if v.member_id == sides["plus"])
            lm, lp = log_f(row, vm.member_id), log_f(row, vp.member_id)
            item.update(p_minus=vm.value, p_plus=vp.value,
                        f_minus=math.exp(lm) if lm is not None else None,
                        f_plus=math.exp(lp) if lp is not None else None,
                        source=f"{vm.member_id} / {vp.member_id}")
            if lm is None or lp is None:
                lost = [vid for vid, l in ((vm.member_id, lm), (vp.member_id, lp)) if l is None]
                item.update(status=UNAVAILABLE, s=None, lost_in=lost,
                            reason="; ".join(str((row.tracked.get(vid) or (None, None, None, "not read"))[3])
                                             for vid in lost))
            else:
                s = (lp - lm) / (math.log(vp.value) - math.log(vm.value))
                item.update(status="CENTRAL", s=s, mode="TRACKED_CLUSTER" if row.cluster else "TRACKED",
                            s_minus=(lf0 - lm) / (math.log(p0) - math.log(vm.value)),
                            s_plus=(lp - lf0) / (math.log(vp.value) - math.log(p0)))
                item["one_sided_difference"] = item["s_plus"] - item["s_minus"]
            entry["parameters"][parameter] = item
        central.append(entry)
    rank = fe_rank(central, list(complete))
    kind = LIVE if datasets else FREQUENCY_ONLY
    status = INCOMPLETE if (any(s["missing"] for s in complete.values()) or not complete) else kind
    return {"kind": kind, "status": status, "model_id": family.model_id, "specimen_id": family.specimen_id,
            "family_kind": family.kind, "baseline_geometry_sha256": base_geometry,
            "baseline_parameters": dict(family.baseline_parameters), "completeness": complete,
            "states_used": sorted(datasets), "excluded": [list(x) for x in excluded],
            "family_problems": [list(p) for p in family.problems],
            "rigid_excluded": [int(m.number) for m in base.sorted_modes()
                               if int(m.number) not in {r.baseline_mode for r in rows}],
            "branches": branches, "clusters": clusters, "central": central, "rank": rank,
            "basis": "central difference in ln p over the actual parameter values of the two solved states"}


def fe_rank(central: Sequence[Mapping[str, Any]], parameters: Sequence[str]) -> list:
    """The FE-only rank of the matrix of central sensitivities (terms with every parameter), and the conditional
    E (E1 = E2) superposition when E1 and E2 are both present."""
    out = []
    full = [t for t in central if all((t["parameters"].get(p) or {}).get("s") is not None for p in parameters)]
    if parameters and full:
        S = np.array([[t["parameters"][p]["s"] for p in parameters] for t in full])
        out.append({**_svd(S, list(parameters)), "terms": [t["term"] for t in full], "status": "FE_ONLY"})
        if "E1" in parameters and "E2" in parameters:
            others = [p for p in parameters if p not in ("E1", "E2")]
            cols = [S[:, parameters.index("E1")] + S[:, parameters.index("E2")]] + [S[:, parameters.index(p)]
                                                                                    for p in others]
            out.append({**_svd(np.column_stack(cols), ["E (E1 = E2)"] + others), "terms": [t["term"] for t in full],
                        "status": f"FE_ONLY — {CONDITIONAL} (s_E = s_E1 + s_E2; no joint E1 = E2 state solved)"})
    return out


def _svd(S: np.ndarray, names: list) -> dict:
    sv = np.linalg.svd(S, compute_uv=False)
    return {"parameters": names, "singular_values": [float(v) for v in sv],
            "rank": int(np.sum(sv > RCOND * sv[0])) if sv.size and sv[0] > 0 else 0,
            "of": len(names), "condition": float(sv[0] / sv[-1]) if sv.size and sv[-1] > 0 else None}


# ----------------------------------------------------------------------------- the PRIORITY-2 archive

M11_MANIFEST_SHA256 = ps.PLATE_FE_FAMILY[0].manifest.sha256


def archived_result(root: Path = rrr.REPO) -> dict:
    """The PRIORITY-2 central sensitivities as an ARCHIVED_FE_RESULT (the SHA-checked CSV; no FE-to-FE MAC is computed
    from it)."""
    snapshot = rrr.load_snapshot(root)
    central = []
    for r in snapshot.sensitivities:
        central.append({"term": r.term, "f0_hz": r.f0_hz, "cluster": "+" in r.term, "parameters": {
            p: ({"s": r.s[p], "status": "CENTRAL (archived)"} if r.s[p] is not None else
                {"s": None, "status": f"{UNAVAILABLE} (archived)"}) for p in ("E1", "E2", "G12")}})
    return {"kind": ARCHIVED, "status": ARCHIVED, "source": rrr.SNAPSHOT_FILES["SENSITIVITIES"][0],
            "source_sha256": rrr.SNAPSHOT_FILES["SENSITIVITIES"][1], "central": central,
            "rank": fe_rank(central, ["E1", "E2", "G12"])}


def compare_with_archive(result: Mapping[str, Any], baseline_manifest_sha256: Optional[str],
                         root: Path = rrr.REPO) -> dict:
    """The live central sensitivities against the archived PRIORITY-2 table: only for the M11 baseline package (another
    FE model is never compared with it). The archive keeps 5 decimals; the difference is reported per value."""
    if baseline_manifest_sha256 != M11_MANIFEST_SHA256:
        return {"state": "NOT_APPLICABLE", "reason": "the archive belongs to M11 S4R_0875_BASELINE; this baseline is "
                                                     "another FE package", "rows": []}
    archive = {t["term"]: t for t in archived_result(root)["central"]}
    rows, worst = [], 0.0
    for term in result.get("central", ()):
        old = archive.get(term["term"])
        for p, item in term["parameters"].items():
            a = (old or {}).get("parameters", {}).get(p, {}).get("s") if old else None
            s = item.get("s")
            diff = None if (a is None or s is None) else s - a
            if diff is not None:
                worst = max(worst, abs(diff))
            agree = (a is None and s is None) or (diff is not None and abs(diff) <= 1e-5 + 5e-6)
            rows.append({"term": term["term"], "parameter": p, "live_s": s, "archived_s": a, "difference": diff,
                         "agree": agree})
    return {"state": "AGREES" if all(r["agree"] for r in rows) else "DIFFERS", "rows": rows,
            "max_abs_difference": worst, "tolerance": "the archive's 5 decimals (|Δs| ≤ 1.5e-5)",
            "archive": rrr.SNAPSHOT_FILES["SENSITIVITIES"][0]}


# ----------------------------------------------------------------------------- the FE-only What-If

JOINT_E = "E (E1 = E2)"


def what_if(result: Mapping[str, Any], trial: Mapping[str, float], baseline_manifest_sha256: Optional[str] = None,
            recorded_baseline_sha256: Optional[str] = None) -> dict:
    """FE-only prediction ``ln f = ln f0 + Σ s_j ln(p_j / p0_j)`` for ``trial`` (parameter → value; ``JOINT_E`` scales E1
    and E2 by the same ratio, the value being E1's: CONDITIONAL_SUPERPOSITION). Refused outside the solved range of a parameter, for another FE model
    than the one the sensitivities belong to, or without a result. Where the trial equals a solved state, the solved FE
    frequency is shown with the prediction error."""
    if not result or not result.get("central"):
        raise WhatIfRefused("no FE sensitivities: run the FE-to-FE tracking first")
    if recorded_baseline_sha256 is not None and baseline_manifest_sha256 != recorded_baseline_sha256:
        raise WhatIfRefused("the sensitivities belong to another FE model (baseline package SHA-256 differs): they are "
                            "never carried to another model")
    p0 = result["baseline_parameters"]
    factors, labels = {}, []
    for name, value in trial.items():
        targets = ("E1", "E2") if name == JOINT_E else (name,)
        if name == JOINT_E:  # E1 and E2 scaled by the same ratio (the value is E1's): s_E1 + s_E2
            if "E1" not in p0 or "E2" not in p0:
                raise WhatIfRefused(f"{JOINT_E} needs both E1 and E2 in the family")
            ratio = float(value) / p0["E1"]
            values = {"E1": float(value), "E2": p0["E2"] * ratio}
        else:
            values = {name: float(value)}
        for p in targets:
            value = values[p]
            if p not in p0:
                raise WhatIfRefused(f"{p} is not a parameter of this family")
            sides = (result.get("completeness") or {}).get(p) or {}
            if sides.get("missing"):
                raise WhatIfRefused(f"{p}: {INCOMPLETE} (no {' / '.join(sides['missing'])} state): no prediction")
            low, high = _range(result, p)
            if not (low - 1e-9 * abs(low) <= float(value) <= high + 1e-9 * abs(high)):
                raise WhatIfRefused(f"{p} = {float(value):g} is outside the solved range {low:g}–{high:g}: never "
                                    "extrapolated")
            factors[p] = math.log(float(value) / p0[p])
        if name == JOINT_E:
            labels.append(f"{JOINT_E}: E1 and E2 scaled by the same ratio — {CONDITIONAL}: no joint state was solved")
    changed = {p: f for p, f in factors.items() if f != 0.0}
    solved = _solved_point(result, changed, trial)
    rows = []
    for term in result["central"]:
        missing = [p for p in changed if (term["parameters"].get(p) or {}).get("s") is None]
        if missing:
            rows.append({"term": term["term"], "f0_hz": term["f0_hz"], "predicted_hz": None,
                         "status": f"{UNAVAILABLE} for {', '.join(missing)}", "solved_hz": None, "error_percent": None,
                         "branch": "not followed in a needed state"})
            continue
        lf = math.log(term["f0_hz"]) + sum(term["parameters"][p]["s"] * f for p, f in changed.items())
        predicted = math.exp(lf)
        actual = None
        if solved is not None:
            item = term["parameters"][solved[0]]
            actual = item["f_minus"] if solved[1] == "minus" else item["f_plus"]
        notes = [f"one-sided s− {term['parameters'][p].get('s_minus'):.5f} / s+ {term['parameters'][p].get('s_plus'):.5f}"
                 for p in changed if term["parameters"][p].get("s_minus") is not None]
        rows.append({"term": term["term"], "f0_hz": term["f0_hz"], "predicted_hz": predicted,
                     "status": PREDICTION if changed else "BASELINE (no change)",
                     "solved_hz": actual, "error_percent": None if actual is None else 100 * (predicted / actual - 1),
                     "branch": "followed in the solved states used", "linearity": "; ".join(notes)})
    return {"trial": dict(trial), "changes_ln": changed, "rows": rows, "labels": [PREDICTION] + labels,
            "solved_point": solved[2] if solved else None,
            "limits": ["no extrapolation beyond the solved states",
                       "linearity not confirmed without the ±2.5 % repeat (one-sided values shown)"]}


def _range(result, parameter) -> tuple:
    for term in result["central"]:
        item = term["parameters"].get(parameter) or {}
        if item.get("p_minus") is not None:
            return item["p_minus"], item["p_plus"]
    raise WhatIfRefused(f"{parameter}: no solved range")


def _solved_point(result, changed, trial) -> Optional[tuple]:
    if len(changed) != 1:
        return None
    (p, _f), = changed.items()
    if JOINT_E in trial:
        return None  # no joint state exists
    low, high = _range(result, p)
    value = float(trial.get(p))
    for side, ref in (("minus", low), ("plus", high)):
        if abs(value - ref) <= 1e-9 * abs(ref):
            state = (result["completeness"][p] or {}).get(side)
            return p, side, state
    return None


# ----------------------------------------------------------------------------- experiment beside the FE (no pairs)

def experiment_rows(records: Sequence[Mapping[str, Any]], result: Mapping[str, Any],
                    prediction: Optional[Mapping[str, Any]] = None) -> list:
    """Each measured record with the nearest FE baseline frequency (and prediction) — FREQUENCY_PROXIMITY_ONLY, never
    a pair; nothing is chosen from it."""
    terms = [(t["term"], t["f0_hz"]) for t in result.get("central", ())]
    predicted = {r["term"]: r["predicted_hz"] for r in (prediction or {}).get("rows", ()) if r.get("predicted_hz")}
    out = []
    for r in records:
        hz = float(r["hz"])
        if not terms:
            out.append({"record": f"EXP{r['number']}", "hz": hz, "nearest_fe": None, "status": PROXIMITY_ONLY})
            continue
        term, f0 = min(terms, key=lambda t: abs(t[1] - hz))
        out.append({"record": f"EXP{r['number']}", "hz": hz, "nearest_fe": term, "fe_hz": f0,
                    "difference_percent": 100 * (f0 / hz - 1), "predicted_hz": predicted.get(term),
                    "status": PROXIMITY_ONLY, "pair": "NONE — no physical registration"})
    return out


# ----------------------------------------------------------------------------- the session

def fe_fingerprint(identity_rows: Sequence[Mapping[str, Any]], family: Family) -> str:
    data = {"members": [[r["id"], r["manifest_sha256"], r["parameter"], r["value"]] for r in identity_rows],
            "baseline_parameters": dict(family.baseline_parameters), "model": family.model_id}
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def session_record(family: Family, identity_rows, result, prediction=None, experiment=None,
                   archive_comparison=None) -> dict:
    """The JSON of one FE-only session (no FE data inside: identities, results and choices only)."""
    return {"schema": SCHEMA_SESSION, "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "labels": list(LABELS) + ([SYNTHETIC_TEST] if family.kind == SYNTHETIC_TEST else []),
            "family": family_to_dict(family), "identities": list(identity_rows),
            "fe_fingerprint": fe_fingerprint(identity_rows, family), "result": result,
            "archive_comparison": archive_comparison, "what_if": prediction, "experiment": experiment,
            "limits": list(LIMITS), "scientific_status": SCIENTIFIC_STATUS}


def save_session(record: Mapping[str, Any], path) -> Path:
    path = Path(path)
    handle, temporary = tempfile.mkstemp(prefix=".~fe_session_", suffix=".json", dir=path.parent)
    os.close(handle)
    try:
        Path(temporary).write_text(json.dumps(record, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    return path


def open_session(path) -> dict:
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FamilyRefused(f"{path} cannot be read as an FE response session ({error})") from error
    if not isinstance(record, dict) or record.get("schema") != SCHEMA_SESSION:
        raise FamilyRefused(f"{path} is not an FE response session ({SCHEMA_SESSION})")
    return record


def used_states(result: Optional[Mapping[str, Any]]) -> list:
    """The FE states a result was computed from: the states read and the − / + states of every central difference."""
    result = result or {}
    used = set(result.get("states_used") or ())
    for sides in (result.get("completeness") or {}).values():
        used.update(s for s in ((sides or {}).get("minus"), (sides or {}).get("plus")) if s)
    return sorted(used)


def verify_sources(identity_rows: Sequence[Mapping[str, Any]], used: Sequence[str] = (),
                   paths: Optional[Mapping[str, Mapping[str, Any]]] = None,
                   cancel: Optional[threading.Event] = None) -> dict:
    """The recorded FE sources against the files now: every manifest (SHA-256), every package (``fe_package_identity``:
    the manifest and every file the loader reads, so a changed shape file under an unchanged manifest is found), every
    INP and .dat, and the presence of every state in ``used``. Any difference, or a source of the baseline or of a
    used state whose identity was not recorded, makes the results STALE. ``paths`` (id → {"inp", "dat"}) supplies the
    paths a session of PRIORITY-10 did not record in its identity rows."""
    from services import fe_package_identity as fpi

    reasons, checked = [], 0
    ids = {row.get("id") for row in identity_rows}
    reasons += [f"{state}: used by the results but not among the recorded sources" for state in used
                if state not in ids]
    if not any(row.get("role") == "baseline" for row in identity_rows):
        reasons.append("the baseline is not among the recorded sources")
    for row in identity_rows:
        name = row.get("id")
        needed = row.get("role") == "baseline" or name in used
        manifest = row.get("manifest")
        if not manifest:
            if needed and name in used:
                reasons.append(f"{name}: no extracted package recorded")
        else:
            if row.get("manifest_sha256"):
                now = sha256_file(manifest, cancel)
                if now != row["manifest_sha256"]:
                    reasons.append(f"{name}: the manifest {'is missing' if now is None else 'changed'}")
                    continue
            elif needed:
                reasons.append(f"{name}: the manifest SHA-256 was not recorded: it cannot be verified")
            if row.get("package_sha256"):
                try:
                    now = fpi.identify(manifest, cancel)["package_sha256"]
                except fpi.PackageIdentityRefused as error:
                    if error.kind == fpi.CANCELLED:
                        raise FamilyRefused("cancelled") from error
                    reasons.append(f"{name}: the package cannot be identified now ({error})")
                    continue
                if now != row["package_sha256"]:
                    reasons.append(f"{name}: the package files changed (a shape or geometry file differs; package "
                                   "SHA-256)")
            elif needed:
                reasons.append(f"{name}: the package SHA-256 was not recorded: its shape files cannot be verified")
        for key, label in (("inp", "INP"), ("dat", ".dat")):
            path = row.get(key) or ((paths or {}).get(name) or {}).get(key)
            recorded = row.get(f"{key}_sha256")
            if recorded and not path:
                reasons.append(f"{name}: the {label} path was not recorded: it cannot be verified")
            elif path:
                now = sha256_file(path, cancel)
                if now != recorded:
                    reasons.append(f"{name}: the {label} " + ("is missing" if now is None else "changed" if recorded
                                                              else "was not readable when recorded"))
        checked += 1
    return {"state": "STALE" if reasons else "SOURCES_VERIFIED", "reasons": reasons, "members": checked,
            "basis": "manifest, package (every file the loader reads), INP and .dat SHA-256; every used state present"}


def session_state(record: Mapping[str, Any], cancel: Optional[threading.Event] = None) -> dict:
    """The FE sources of a session now (``verify_sources``): every manifest, package, INP and .dat hashed again and
    every state the results used present. The recorded identities must also be the ones the session's fingerprint
    names. Any difference makes the FE results STALE; the experimental context never does."""
    family = record.get("family") or {}
    rows = list(record.get("identities") or ())
    reasons = []
    try:
        fingerprint = fe_fingerprint(rows, family_from_record(family))
    except (FamilyRefused, KeyError, TypeError, ValueError) as error:
        fingerprint, reasons = None, [f"the session's FE family cannot be read ({error})"]
    if fingerprint is not None and fingerprint != record.get("fe_fingerprint"):
        reasons.append("the recorded sources are not the ones the session's FE fingerprint names")
    members = [family.get("baseline") or {}] + list(family.get("variants") or ())
    paths = {m.get("id"): m for m in members if isinstance(m, Mapping)}
    declared = {m.get("id") for m in family.get("variants") or () if isinstance(m, Mapping)}
    used = used_states(record.get("result"))
    reasons += [f"{state}: used by the results but not a state of the session's family" for state in used
                if state not in declared]
    checked = verify_sources(rows, used, paths, cancel)
    reasons += checked["reasons"]
    return {"state": "STALE" if reasons else "SOURCES_VERIFIED", "reasons": reasons, "basis": checked["basis"],
            "note": "stored FE results; the FE sources verify by SHA-256 (run again to recompute)" if not reasons
            else "the FE sources changed: the stored FE results are not current"}


def _csv(columns, rows) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return buffer.getvalue()


def export_session(record: Mapping[str, Any], folder) -> tuple:
    """CSV and Markdown of a session into a new folder inside ``folder`` (never overwritten)."""
    folder = Path(folder)
    if not folder.is_dir():
        raise FamilyRefused(f"{folder} is not an existing folder")
    result = record.get("result") or {}
    params = list((result.get("baseline_parameters") or {}))
    central = _csv(["term", "f0_hz"] + [f"{h}_{p}" for p in params for h in ("s", "status", "f_minus", "f_plus")],
                   [[t["term"], f"{t['f0_hz']:.6f}"] + [x for p in params for x in (
                       "" if (t["parameters"].get(p) or {}).get("s") is None else f"{t['parameters'][p]['s']:.6f}",
                       (t["parameters"].get(p) or {}).get("status"), (t["parameters"].get(p) or {}).get("f_minus"),
                       (t["parameters"].get(p) or {}).get("f_plus"))] for t in result.get("central", ())])
    tracking = _csv(["branch", "baseline_mode", "hz", "cluster", "state", "status", "candidate", "state_hz", "mac",
                     "permutation", "reason"],
                    [[b["branch"], b["baseline_mode"], f"{b['hz']:.6f}", b["cluster"] or "", vid, v["status"],
                      v["candidate"] or "", v["hz"] if v["hz"] is not None else "", v["mac"] if v["mac"] is not None
                      else "", "YES" if v["permutation"] else "", v["reason"] or ""]
                     for b in result.get("branches", ()) for vid, v in sorted(b["variants"].items())])
    prediction = record.get("what_if") or {}
    what = _csv(["term", "f0_hz", "predicted_hz", "solved_hz", "error_percent", "status"],
                [[r["term"], r["f0_hz"], r["predicted_hz"], r["solved_hz"], r["error_percent"], r["status"]]
                 for r in prediction.get("rows", ())])
    md = markdown(record)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", str((record.get("family") or {}).get("model_id") or "fe"))
    target = folder / f"fe_response_{name}_{stamp}"
    index = 2
    while target.exists():
        target = folder / f"fe_response_{name}_{stamp}_{index}"
        index += 1
    temporary = Path(tempfile.mkdtemp(prefix=".~fe_response_", dir=folder))
    try:
        for file, text in (("fe_response_session.json", json.dumps(record, indent=2, ensure_ascii=False, default=str)),
                           ("central_sensitivities.csv", central), ("branch_tracking.csv", tracking),
                           ("what_if.csv", what), ("FE_RESPONSE_REPORT.md", md)):
            (temporary / file).write_text(text, encoding="utf-8", newline="\n")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
    return tuple(sorted(target.iterdir()))


def _num(value, digits: int, sign: str = "") -> str:
    return "—" if value is None else format(value, f"{sign}.{digits}f")


def markdown(record: Mapping[str, Any]) -> str:
    family, result = record.get("family") or {}, record.get("result") or {}
    params = list(result.get("baseline_parameters") or {})
    lines = [f"# FE response — {family.get('model_id')} ({family.get('specimen_id')})", "",
             "Labels: " + " / ".join(record.get("labels", ())), "", f"Kind: **{result.get('kind')}** · status "
             f"**{result.get('status')}**", "", "## Sources", "", "| State | Parameter | Value | Manifest SHA-256 | "
             "Not verified |", "|---|---|---|---|---|"]
    lines += [f"| {r['id']} | {r['parameter'] or '—'} | {r['value'] if r['value'] is not None else '—'} | "
              f"{r['manifest_sha256'] or '—'} | {'; '.join(r['not_verified']) or '—'} |"
              for r in record.get("identities", ())]
    lines += ["", "## Central sensitivities", "", "| Term | f0 (Hz) | " + " | ".join(f"s_{p}" for p in params) + " |",
              "|---|---|" + "---|" * len(params)]
    for t in result.get("central", ()):
        lines.append(f"| {t['term']} | {t['f0_hz']:.5f} | " + " | ".join(
            f"{t['parameters'][p]['s']:.5f}" if (t["parameters"].get(p) or {}).get("s") is not None else
            str((t["parameters"].get(p) or {}).get("status")) for p in params) + " |")
    lines += ["", "## FE-only rank", ""] + [
        f"- {' / '.join(r['parameters'])}: rank {r['rank']} of {r['of']}, condition {_num(r['condition'], 2)} — "
        f"{r['status']}" for r in result.get("rank", ())]
    comparison = record.get("archive_comparison") or {}
    if comparison:
        lines += ["", f"## Archive (PRIORITY-2): {comparison.get('state')}", "",
                  f"max |Δs| {comparison.get('max_abs_difference')}; {comparison.get('reason') or ''}"]
    prediction = record.get("what_if") or {}
    if prediction:
        lines += ["", f"## FE-only What-If {prediction.get('trial')}", "", " · ".join(prediction.get("labels", ())), "",
                  "| Term | f0 | predicted | solved FE | error % | status |", "|---|---|---|---|---|---|"]
        lines += [f"| {r['term']} | {r['f0_hz']:.5f} | {_num(r['predicted_hz'], 5)} | {_num(r['solved_hz'], 5)} | "
                  f"{_num(r['error_percent'], 4, '+')} | {r['status']} |" for r in prediction.get("rows", ())]
    lines += ["", "## Limits", ""] + [f"- {x}" for x in record.get("limits", ())] + ["", record.get(
        "scientific_status", "")]
    return "\n".join(lines) + "\n"


__all__ = [name for name in dir() if not name.startswith("_") and name not in (
    "annotations", "csv", "dataclass", "datetime", "field", "hashlib", "io", "json", "math", "np", "os", "re",
    "replace", "shutil", "tempfile", "threading", "timezone", "Any", "Mapping", "Optional", "Path", "Sequence")]
