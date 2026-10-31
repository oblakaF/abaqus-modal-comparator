"""PRIORITY-8: the bounded offline research study of one single plate (no Qt, no Abaqus; RESEARCH_ONLY).

It runs the project's ``services.identification_step.run_bounded_lm`` (no second optimiser) over a LOG-LINEAR
APPROXIMATION built from an imported FE sensitivity table of THIS plate's FE model:

    ln f_t(p) = ln f_t0 + Σ_j s_tj · ln(p_j / p_j0)

Each evaluation is an evaluation of that approximation, never an FE solve; outside the table's solved range the
prediction is marked EXTRAPOLATION and never presented as an Abaqus result. MAC is never a term of the objective.

It starts only when every condition holds (``gate``):

- the FE model of the study is identified (its manifest SHA-256), and the sensitivity table belongs to it and to this
  specimen (a table of another FE model or specimen — for example M11 — is refused);
- the experimental modal fit is usable (curve-fitted records only; an FRF peak is never an admissible mode);
- the physical registration evidence is complete AND the owner's decision that it is admissible for a research
  computation is recorded (this program never makes that decision);
- the observation set is declared before the computation: each row an experimental record and its FE mode (or a
  two-mode cluster), FIT or HOLDOUT, with its basis; parameters, start and bounds fixed; σ stated;
- every FE row used is tracked in the table; the sensitivity matrix of the FIT terms is full rank (SPEC §6 S5).

A result is DIAGNOSTIC_OPTIMIZER_CANDIDATE / NOT_A_RELEASE_VALUE / NOT_A_MATERIAL_PROPERTY: not an identified
property and not a released calibration. ``release_material_values`` always refuses (M8 GATE NOT_MET, D-077
NO_GLOBAL_PARAMETER_VALUE, production Auto-ID BLOCKED).
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from . import generic_plate_evidence as ev
from . import generic_plate_workbench as wb

SENSITIVITY_SCHEMA = "amc/fe-sensitivity-table/v1"
DECLARATION_SCHEMA = "amc/declared-observations/v1"
PARAMETERS = ("E_in_plane", "G12")  # E1 = E2 = E_in_plane (SPEC v1.1 §5.2); G12 separate
ADMISSIBLE = "ADMISSIBLE_FOR_RESEARCH_COMPUTATION"
RESULT_LABELS = ("DIAGNOSTIC_OPTIMIZER_CANDIDATE", "NOT_A_RELEASE_VALUE", "NOT_A_MATERIAL_PROPERTY", "RESEARCH_ONLY",
                 "LOG_LINEAR_APPROXIMATION")
FROZEN_TOLERANCE = 1.0e-4  # relative: the table's baseline against the FE package read
MAX_FILE_BYTES = 5 * 1024 * 1024


class OfflineRefused(ValueError):
    """An input of the offline study is refused; the reason is shown and nothing is computed."""


class ReleaseRefused(RuntimeError):
    """No material value is released by this program."""


def _load_json(source) -> tuple:
    """(data, sha256) of a JSON file or of an already parsed mapping (its canonical text is hashed)."""
    if isinstance(source, Mapping):
        text = json.dumps(source, sort_keys=True, ensure_ascii=False)
        return dict(source), hashlib.sha256(text.encode("utf-8")).hexdigest()
    path = Path(source)
    if not path.is_file():
        raise OfflineRefused(f"{path} does not exist")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise OfflineRefused(f"{path.name} is larger than 5 MB")
    data = path.read_bytes()
    try:
        return json.loads(data.decode("utf-8")), hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OfflineRefused(f"{path.name} is not valid JSON: {error}") from error


def _positive(value, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise OfflineRefused(f"{what}: {value!r} is not a finite positive number")
    return float(value)


def _finite(value, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise OfflineRefused(f"{what}: {value!r} is not a finite number")
    return float(value)


def fe_identity(study: wb.Study) -> Optional[str]:
    record = study.sources.get("fe")
    return record.sha256 if record else None


# ----------------------------------------------------------------------------- the FE sensitivity table

def load_sensitivities(source, study: wb.Study) -> dict:
    """The sensitivity table checked against THIS study's FE model and specimen; refused otherwise."""
    data, digest = _load_json(source)
    if data.get("schema") != SENSITIVITY_SCHEMA:
        raise OfflineRefused(f"not a sensitivity table (schema {SENSITIVITY_SCHEMA})")
    model = data.get("fe_model") or {}
    expected = fe_identity(study)
    if expected is None:
        raise OfflineRefused("the study has no identified FE model (link the FE package read in the Workspace)")
    if model.get("manifest_sha256") != expected:
        raise OfflineRefused(f"the table belongs to the FE model {str(model.get('manifest_sha256'))[:12]}… "
                             f"({model.get('name')}), not to this study's {expected[:12]}…: sensitivities are never "
                             "carried over to another FE model or specimen")
    specimen = (data.get("specimen") or {}).get("physical_specimen_id")
    if specimen != study.passport.physical_specimen_id or not specimen:
        raise OfflineRefused(f"the table is for the specimen {specimen!r}, not {study.passport.physical_specimen_id!r}")
    if (data.get("kind") == "SYNTHETIC") != study.synthetic:
        raise OfflineRefused("a synthetic table belongs to a synthetic study only, and a physical one to a physical study")
    parameters = data.get("parameters") or {}
    if not parameters or set(parameters) - set(PARAMETERS):
        raise OfflineRefused(f"parameters {sorted(parameters)}: only {PARAMETERS} (E1 ≠ E2 needs a traceable warp / "
                             "fill orientation, SPEC v1.1 §5.2)")
    baseline = {p: _positive((v or {}).get("baseline"), f"baseline of {p}") for p, v in parameters.items()}
    solved = data.get("solved_range_relative")
    if not (isinstance(solved, list) and len(solved) == 2 and 0 < _positive(solved[0], "solved range") < 1
            < _positive(solved[1], "solved range")):
        raise OfflineRefused("the solved range (relative to the baseline, for example [0.95, 1.05]) is missing")
    rows = {}
    for row in data.get("rows") or ():
        mode = row.get("fe_mode")
        if not isinstance(mode, int) or mode in rows:
            raise OfflineRefused(f"FE mode {mode!r} is not a unique integer")
        s = row.get("s") or {}
        if set(s) != set(parameters):
            raise OfflineRefused(f"FE{mode}: sensitivities {sorted(s)} are not {sorted(parameters)}")
        rows[mode] = {"f_baseline_hz": _positive(row.get("f_baseline_hz"), f"FE{mode} baseline"),
                      "tracked": row.get("tracked") is True,
                      "s": {p: _finite(v, f"FE{mode} s_{p}") for p, v in s.items()}}
    if not rows:
        raise OfflineRefused("the table has no FE rows")
    fe_modes = {m["number"]: m["hz"] for m in (study.diagnostics or {}).get("fe_elastic", [])}
    if fe_modes:
        for mode, row in rows.items():
            if mode not in fe_modes or abs(row["f_baseline_hz"] / fe_modes[mode] - 1) > FROZEN_TOLERANCE:
                raise OfflineRefused(f"FE{mode}: the table's baseline {row['f_baseline_hz']} Hz is not the FE package "
                                     f"read ({fe_modes.get(mode)} Hz)")
    if not str(data.get("provenance") or "").strip() or not str(data.get("method") or "").strip():
        raise OfflineRefused("the table states no method and provenance")
    return {"sha256": digest, "fe_model": model, "specimen": specimen, "kind": data.get("kind", "PHYSICAL"),
            "parameters": baseline, "units": {p: (v or {}).get("unit", "MPa") for p, v in parameters.items()},
            "solved_range_relative": [float(solved[0]), float(solved[1])], "method": data["method"],
            "provenance": data["provenance"], "rows": {str(k): v for k, v in rows.items()}}


# ----------------------------------------------------------------------------- the declared observation set

def load_declaration(source, study: wb.Study, sensitivities: Optional[Mapping[str, Any]]) -> dict:
    """The observation set declared before any computation (FIT / HOLDOUT, parameters, bounds, σ, the owner's
    registration decision). It is checked, never completed or chosen here."""
    data, digest = _load_json(source)
    if data.get("schema") != DECLARATION_SCHEMA:
        raise OfflineRefused(f"not a declared observation set (schema {DECLARATION_SCHEMA})")
    if (data.get("specimen") or {}).get("physical_specimen_id") != study.passport.physical_specimen_id:
        raise OfflineRefused("the declaration is for another specimen")
    synthetic = data.get("kind") == "SYNTHETIC"
    if synthetic != study.synthetic:
        raise OfflineRefused("a synthetic declaration belongs to a synthetic study only, and a physical one to a "
                             "physical study")
    decision = dict(data.get("registration_decision") or {})
    parameters = list(data.get("parameters") or ())
    if not parameters or set(parameters) - set(PARAMETERS) or len(set(parameters)) != len(parameters):
        raise OfflineRefused(f"parameters {parameters}: a subset of {PARAMETERS}")
    start = {p: _positive((data.get("start") or {}).get(p), f"start of {p}") for p in parameters}
    bounds = {}
    for p in parameters:
        pair = (data.get("bounds") or {}).get(p)
        if not (isinstance(pair, list) and len(pair) == 2):
            raise OfflineRefused(f"the bounds of {p} are not [lower, upper]")
        low, high = _positive(pair[0], f"lower bound of {p}"), _positive(pair[1], f"upper bound of {p}")
        if not low < start[p] < high:
            raise OfflineRefused(f"the start of {p} is not strictly inside its bounds")
        bounds[p] = (low, high)
    sigma = data.get("sigma_ln") or {}
    sigma_value = _positive(sigma.get("value"), "σ (ln f)")
    if not str(sigma.get("provenance") or "").strip():
        raise OfflineRefused("σ needs its provenance (for example Σ_setup 0.3 % PROVISIONAL)")
    observations = []
    for item in data.get("observations") or ():
        exp, fe, role = item.get("exp"), item.get("fe"), item.get("role")
        if not isinstance(exp, int) or not isinstance(fe, list) or not fe or len(fe) > 2 \
                or not all(isinstance(m, int) for m in fe):
            raise OfflineRefused(f"observation {item!r}: an experimental record number and one FE mode or a two-mode "
                                 "cluster")
        if role not in ("FIT", "HOLDOUT"):
            raise OfflineRefused(f"EXP{exp}: the role {role!r} is not FIT or HOLDOUT (declared before the fit)")
        if not str(item.get("basis") or "").strip():
            raise OfflineRefused(f"EXP{exp}: the declared basis of the pairing is missing")
        observations.append({"exp": exp, "fe": list(fe), "role": role, "basis": item["basis"]})
    if not observations:
        raise OfflineRefused("no observation is declared")
    if len({o["exp"] for o in observations}) != len(observations):
        raise OfflineRefused("an experimental record is declared twice")
    used = [m for o in observations for m in o["fe"]]
    if len(set(used)) != len(used):
        raise OfflineRefused("an FE mode is used in two declared observations")
    if "holdout_declared" not in data or not isinstance(data["holdout_declared"], bool):
        raise OfflineRefused("the declaration must state holdout_declared (true or false): FIT / HOLDOUT is fixed "
                             "before the fit")
    if "experimental_frequencies_hz" in data:
        raise OfflineRefused("the experimental frequencies come from the study's diagnostics (the file read in the "
                             "Workspace, or the synthetic inputs of a synthetic study), never from the declaration")
    experimental = {int(r["number"]): float(r["hz"]) for r in (study.diagnostics or {}).get("experimental", [])}
    return {"sha256": digest, "kind": "SYNTHETIC" if synthetic else "PHYSICAL", "registration_decision": decision,
            "parameters": parameters, "start": start, "bounds": {p: list(v) for p, v in bounds.items()},
            "sigma_ln": {"value": sigma_value, "provenance": sigma["provenance"]}, "observations": observations,
            "holdout_declared": data["holdout_declared"],
            "experimental_frequencies_hz": {str(k): v for k, v in experimental.items()}}


# ----------------------------------------------------------------------------- the gate

def _terms(declaration: Mapping[str, Any], role: str) -> list:
    return [o for o in declaration["observations"] if o["role"] == role]


def term_sensitivity(sensitivities: Mapping[str, Any], fe: Sequence[int], parameters: Sequence[str]) -> dict:
    """One term's s (a two-mode cluster is one term: the mean of its members, as in the objective's mean ln f)."""
    rows = [sensitivities["rows"][str(m)] for m in fe]
    return {p: float(np.mean([r["s"][p] for r in rows])) for p in parameters}


def rank_check(sensitivities, declaration) -> dict:
    """The M5 rank / condition of the FIT terms (SPEC §6 S5, rcond 1e-3) through the existing service."""
    from .plate_study import design_study

    fit = _terms(declaration, "FIT")
    parameters = declaration["parameters"]
    table = {"+".join(f"FE{m}" for m in o["fe"]): term_sensitivity(sensitivities, o["fe"], parameters) for o in fit}
    result = design_study(table, list(table), parameters, "offline FIT terms", declaration["sigma_ln"]["value"])
    return {"status": result.status, "rank": result.rank, "rcond": result.rcond, "parameters": list(parameters),
            "terms": list(table), "full_rank": result.rank == len(parameters),
            "reasons": list(result.refusal_reasons)}


def gate(study: wb.Study, evidence: ev.EvidenceResult, sensitivities: Optional[Mapping[str, Any]],
         declaration: Optional[Mapping[str, Any]], current_sources: Optional[Mapping[str, Any]] = None) -> list:
    """Every reason the offline study cannot start (empty: it may start)."""
    reasons = []
    if fe_identity(study) is None:
        reasons.append("no identified FE model: link the FE package read in the Workspace")
    if not study.synthetic and not (current_sources or {}).get("consistent"):
        reasons.append("the files and the modal set read in the Workspace are not the study's linked sources")
    diagnostics = study.diagnostics or {}
    if not diagnostics.get("experimental"):
        reasons.append("no modal diagnostics (run them on the linked files, or on the synthetic inputs)")
    if evidence.status != ev.COMPLETE:
        reasons.append(f"{evidence.status}: the physical registration evidence is not complete")
    if sensitivities is None:
        reasons.append("no FE sensitivity table of this FE model is loaded")
    if declaration is None:
        reasons.append("no declared observation set (FIT / HOLDOUT, parameters, bounds, σ) is loaded")
    if declaration is not None:
        decision = declaration.get("registration_decision") or {}
        expected = ev.SYNTHETIC if study.synthetic else wb.HUMAN_CONFIRMED
        if decision.get("status") != ADMISSIBLE or decision.get("provenance") != expected \
                or not str(decision.get("reference") or "").strip():
            reasons.append(f"no owner decision {ADMISSIBLE} ({expected}, with its reference) is recorded: this "
                           "program never decides a registration")
        records = {int(r["number"]): r for r in diagnostics.get("experimental", [])}
        for o in declaration["observations"]:
            if str(o["exp"]) not in declaration["experimental_frequencies_hz"]:
                reasons.append(f"EXP{o['exp']} is not an experimental record of the study")
            elif not records.get(o["exp"], {}).get("admissible"):
                reasons.append(f"EXP{o['exp']} is not a curve-fitted mode (an FRF peak or an ambiguous record is "
                               "never admissible)")
        if sensitivities is not None:
            for o in declaration["observations"]:
                for m in o["fe"]:
                    row = sensitivities["rows"].get(str(m))
                    if row is None:
                        reasons.append(f"FE{m} has no sensitivity in the table")
                    elif not row["tracked"]:
                        reasons.append(f"FE{m} is not tracked across the table's variants (branch identity)")
            if set(declaration["parameters"]) - set(sensitivities["parameters"]):
                reasons.append("a declared parameter has no sensitivity in the table")
            fit = _terms(declaration, "FIT")
            if len(fit) < len(declaration["parameters"]):
                reasons.append(f"{len(fit)} FIT terms < {len(declaration['parameters'])} parameters")
            elif not reasons:
                rank = rank_check(sensitivities, declaration)
                if not rank["full_rank"]:
                    reasons.append(f"RANK_DEFICIENT: rank {rank['rank']} < {len(declaration['parameters'])} "
                                   f"(rcond {rank['rcond']:.3g}); no estimate before identifiability (SPEC §6 S5)")
    return reasons


# ----------------------------------------------------------------------------- the run

def _predict(sensitivities, fe: Sequence[int], parameters: Mapping[str, float]) -> list:
    out = []
    for m in fe:
        row = sensitivities["rows"][str(m)]
        x = sum(row["s"][p] * math.log(parameters[p] / sensitivities["parameters"][p]) for p in parameters)
        out.append(row["f_baseline_hz"] * math.exp(x))
    return out


def run_offline_study(study: wb.Study, evidence: ev.EvidenceResult, sensitivities: Mapping[str, Any],
                      declaration: Mapping[str, Any], current_sources: Optional[Mapping[str, Any]] = None) -> dict:
    """The bounded LM over the log-linear approximation; refused (OfflineRefused) unless ``gate`` is empty."""
    from .identification_step import LMSettings, StepError, parameter_bounds, run_bounded_lm

    reasons = gate(study, evidence, sensitivities, declaration, current_sources)
    if reasons:
        raise OfflineRefused("; ".join(reasons))
    names = declaration["parameters"]
    sigma = declaration["sigma_ln"]["value"]
    f_exp = {int(k): v for k, v in declaration["experimental_frequencies_hz"].items()}
    fixed = {p: sensitivities["parameters"][p] for p in sensitivities["parameters"] if p not in names}
    fit, holdout = _terms(declaration, "FIT"), _terms(declaration, "HOLDOUT")

    def full(q):
        return {**fixed, **{p: float(q[p]) for p in names}}

    def residual(o, p):
        model = _predict(sensitivities, o["fe"], p)
        return (float(np.mean(np.log(model))) - math.log(f_exp[o["exp"]])) / sigma

    def residuals(q):
        p = full(q)
        return np.array([residual(o, p) for o in fit])

    bounds = parameter_bounds([(p, *declaration["bounds"][p]) for p in names])
    settings = LMSettings(mu_initial=1e-3, mu_decrease=10.0, max_step_attempts=8, solve_budget=200, max_iterations=50)
    try:
        lm = run_bounded_lm(residuals, declaration["start"], bounds, settings)
    except StepError as error:
        raise OfflineRefused(f"the step is not defined: {error}") from error
    p = full(lm.parameters)
    low, high = sensitivities["solved_range_relative"]
    ratios = {n: p[n] / sensitivities["parameters"][n] for n in names}
    extrapolation = {n: r for n, r in ratios.items() if not low <= r <= high}
    terms = []
    for role, group in (("FIT", fit), ("HOLDOUT", holdout)):
        for o in group:
            model = _predict(sensitivities, o["fe"], p)
            terms.append({"term": f"EXP{o['exp']} ↔ " + "+".join(f"FE{m}" for m in o["fe"]), "role": role,
                          "f_exp_hz": f_exp[o["exp"]], "f_model_hz": float(math.exp(np.mean(np.log(model)))),
                          "residual": residual(o, p), "basis": o["basis"]})
    candidate = {n: {"value": p[n], "unit": sensitivities["units"].get(n, "MPa"), "ratio_to_baseline": ratios[n],
                     "local_sd_ln": (lm.local_sd[i] if lm.local_sd else None)} for i, n in enumerate(names)}
    derived = derived_bending(study, p)
    limits = [f"EXTRAPOLATION beyond the solved range {low:g}–{high:g} × baseline: "
              + ", ".join(f"{k} ×{v:.3f}" for k, v in extrapolation.items())] if extrapolation else []
    limits += ["The forward model is a log-linear approximation of the imported FE sensitivities, not an Abaqus "
               "solve.", f"σ = {sigma:g} ({declaration['sigma_ln']['provenance']}).",
               "The pairs are the declared ones (" + declaration["registration_decision"].get("reference", "") +
               "); MAC is not a term of the objective."]
    labels = list(RESULT_LABELS) + ([wb.SYNTHETIC_LABEL] if study.synthetic else [])
    return {"status": lm.status.value, "labels": labels, "refusal": lm.refusal, "evaluations": lm.solves,
            "iterations": lm.iterations, "objective": lm.objective, "parameters": names, "candidate": candidate,
            "fixed": fixed, "extrapolation": extrapolation, "terms": terms, "derived": derived, "limits": limits,
            "sensitivities_sha256": sensitivities["sha256"], "declaration_sha256": declaration["sha256"],
            "approved_material_values": {"status": wb.NOT_AVAILABLE, "reason": wb.SCIENTIFIC_STATUS}}


# ----------------------------------------------------------------------------- the study's imported files

def import_file(path) -> dict:
    """An imported file kept in the study as it was read (with its SHA-256); it is checked again at every use."""
    data, digest = _load_json(path)
    return {"file": str(path), "file_sha256": digest, "data": data}


def with_sensitivities(study: wb.Study, path) -> wb.Study:
    from dataclasses import replace

    imported = import_file(path)
    load_sensitivities(imported["data"], study)  # refused here when it is not this model's table
    out = replace(study, sensitivities=imported, offline_result=None)
    return out.logged("sensitivity table imported", f"{Path(path).name} {imported['file_sha256'][:12]}…")


def with_declaration(study: wb.Study, path) -> wb.Study:
    from dataclasses import replace

    imported = import_file(path)
    load_declaration(imported["data"], study, active_sensitivities(study))
    out = replace(study, declaration=imported, offline_result=None)
    return out.logged("observation set declared", f"{Path(path).name} {imported['file_sha256'][:12]}…")


def active_sensitivities(study: wb.Study) -> Optional[dict]:
    if not study.sensitivities:
        return None
    out = load_sensitivities(study.sensitivities["data"], study)
    out["sha256"] = study.sensitivities["file_sha256"]
    return out


def active_declaration(study: wb.Study, sensitivities: Optional[Mapping[str, Any]]) -> Optional[dict]:
    if not study.declaration:
        return None
    out = load_declaration(study.declaration["data"], study, sensitivities)
    out["sha256"] = study.declaration["file_sha256"]
    return out


def states(study: wb.Study, evidence: ev.EvidenceResult, current_sources: Optional[Mapping[str, Any]] = None) -> dict:
    """The readiness states of the sensitivities, the declaration and the rank, and the gate's reasons (recomputed
    from the imported files at every call)."""
    out = {"sensitivities": None, "declaration": None, "errors": [], "rank": None}
    try:
        out["sensitivities"] = active_sensitivities(study)
    except OfflineRefused as error:
        out["errors"].append(f"sensitivity table refused: {error}")
    try:
        out["declaration"] = active_declaration(study, out["sensitivities"])
    except OfflineRefused as error:
        out["errors"].append(f"declaration refused: {error}")
    sens, decl = out["sensitivities"], out["declaration"]
    out["sensitivity_state"] = ((wb.PASS, f"{len(sens['rows'])} FE rows of {sens['fe_model'].get('name')} "
                                          f"(SHA-256 {sens['sha256'][:12]}…), {sens['method']}") if sens else
                                (wb.BLOCKED, (out["errors"][0] if out["errors"] else
                                              "no sensitivity table of this FE model is loaded")))
    if decl:
        fit = len(_terms(decl, "FIT"))
        out["declaration_state"] = (wb.PASS, f"{fit} FIT and {len(decl['observations']) - fit} HOLDOUT terms "
                                             f"declared; parameters {', '.join(decl['parameters'])}")
    else:
        out["declaration_state"] = (wb.BLOCKED, "no declared observation set (FIT / HOLDOUT) is loaded")
    if sens and decl and len(_terms(decl, "FIT")) >= 1:
        try:
            rank = rank_check(sens, decl)
            out["rank"] = rank
            out["rank_state"] = ((wb.PASS if rank["full_rank"] else wb.BLOCKED),
                                 f"{rank['status']}: rank {rank['rank']} of {len(rank['parameters'])} "
                                 f"(rcond {rank['rcond']:.3g}) over {len(rank['terms'])} FIT terms")
        except (KeyError, ValueError) as error:
            out["rank_state"] = (wb.BLOCKED, f"the rank cannot be computed: {error}")
    else:
        out["rank_state"] = (wb.BLOCKED, "no rank without a sensitivity table and declared FIT terms")
    out["gate"] = gate(study, evidence, sens, decl, current_sources) + out["errors"]
    return out


def derived_bending(study: wb.Study, p: Mapping[str, float]) -> dict:
    """D11 (= D22 with E1 = E2), D66 and, with a FIXED ν12, D12, from the candidate and the mean thickness: DERIVED,
    with the assumptions; NOT_AVAILABLE without the thickness (and ν12 for D11 / D12)."""
    t = wb.thickness_summary(study.passport, study.kind)["mean_mm"]
    nu = study.passport.constant("nu12")
    nu12 = nu.quantity.base() if nu is not None and nu.role == "FIXED" and nu.quantity.available else None
    out = {"basis": "homogeneous Kirchhoff plate, E1 = E2 = E_in_plane, mean thickness; DERIVED from a diagnostic "
                    "candidate, never a material property"}
    if t is None:
        return {**out, "D11_Nmm": wb.NOT_AVAILABLE, "D66_Nmm": wb.NOT_AVAILABLE, "D12_Nmm": wb.NOT_AVAILABLE,
                "reason": "no thickness reading"}
    h3 = t ** 3
    out["D66_Nmm"] = p["G12"] * h3 / 12.0 if "G12" in p else wb.NOT_AVAILABLE
    if nu12 is None or "E_in_plane" not in p:
        out["D11_Nmm"] = out["D12_Nmm"] = wb.NOT_AVAILABLE
        out["reason"] = "ν12 is not a FIXED constant of the passport"
    else:
        d11 = p["E_in_plane"] * h3 / (12.0 * (1.0 - nu12 ** 2))
        out["D11_Nmm"], out["D12_Nmm"] = d11, nu12 * d11
    return out


def release_material_values(result: Optional[Mapping[str, Any]]) -> None:
    """Always refused: no value of the workbench is a released material property."""
    raise ReleaseRefused("no material value is released: the result is DIAGNOSTIC_OPTIMIZER_CANDIDATE / "
                         "NOT_A_RELEASE_VALUE / NOT_A_MATERIAL_PROPERTY; " + wb.SCIENTIFIC_STATUS)


__all__ = ["ADMISSIBLE", "DECLARATION_SCHEMA", "OfflineRefused", "PARAMETERS", "RESULT_LABELS", "ReleaseRefused",
           "SENSITIVITY_SCHEMA", "active_declaration", "active_sensitivities", "derived_bending", "gate",
           "import_file", "load_declaration", "load_sensitivities", "rank_check", "release_material_values",
           "run_offline_study", "states", "with_declaration", "with_sensitivities"]
