"""Campaign configuration of a campaign draft — Auto-ID M8-D2f (explicit declaration of the remaining fields).

The fields a draft does not take from governed records — parameterisation, fitted and fixed parameters, start, search
bounds, engineering plausibility, Σ, practical target, LM settings, Abaqus solve budget, archive reuse, decision,
provenance and (RUN_A) the absent RUN_B gate — are declared explicitly, one group at a time, as text in the GUI form.
``values_from_text`` turns the text into values without filling anything in (an empty field is refused; there is no
default), and ``CampaignDraft.with_configuration`` validates them with the campaign-definition parser's own field
validators.  ``configuration_problems`` adds the repository checks the parser cannot make: the declared
parameterisation is that of every selected forward model, and the archive-reuse plan exists in the repository, loads
with that parameterisation and names only selected specimens.

The archived M7 RUN_A definition is a reference only (``reference_configuration``): its settings are shown with
their origin and can be copied into the form by an explicit user choice; every copied value is validated like a typed
one and the declaration records that it was copied.  Its results are never read: an M7 (v1.1) outcome is not carried
into a v1.2 draft, and a complete definition is neither identifiability nor an execution authorisation.  Nothing here
runs Abaqus, FE or LM.
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Optional

from domain.campaign_definition import (
    NOT_AVAILABLE,
    CampaignDefinitionError,
    load_archive_reuse,
    load_campaign_definition,
)
from domain.forward_model_manifest import load_forward_model_manifest

from .campaign_draft import CONFIGURATION_GROUPS, GROUP_TITLES, CampaignDraft, CampaignDraftError

REFERENCE_CAMPAIGN = "docs/auto_id/campaigns/M7_RUN_A.campaign.json"
REFERENCE_NOTE = ("archived M7 RUN_A definition (schema v1, SPEC v1.1 era): reference only — its settings may be copied "
                  "by an explicit choice and are then validated like typed values; its results are never carried into "
                  "this draft (no v1.2 scientific status)")
COUNTS = {"lm.max_step_attempts", "lm.evaluation_budget", "lm.max_iterations", "abaqus_solve_budget"}
LM_KEYS = ("mu_initial", "mu_decrease", "mu_increase", "max_step_attempts", "evaluation_budget", "max_iterations",
           "stop_fraction", "finite_difference_step")
SIGMA_STATUS_CHOICES = ("PROVISIONAL", "MEASURED")
# The form fields of each group: (field id, label, kind). Kinds: text, number, count, entries, ranges, multiline.
FORM_FIELDS = {
    "material": (("parameterisation", "Parameterisation (governed id)", "text"),
                 ("fitted_parameters", "Fitted parameters (comma-separated)", "text"),
                 ("fixed_parameters", "Fixed parameters (name=value; ... or 'none')", "entries"),
                 ("start", "Start (name=value; ...)", "entries"),
                 ("bounds", "Numerical search bounds (name=low..high; ...)", "ranges"),
                 ("engineering_plausibility", "Engineering plausibility (name=low..high; ... or 'none')", "ranges")),
    "uncertainty": (("sigma.setup.sd_ln", "Σ_setup sd (ln)", "number"),
                    ("sigma.setup.status", "Σ_setup status (PROVISIONAL / MEASURED)", "text"),
                    ("sigma.setup.source", "Σ_setup source", "text"),
                    ("sigma.measurement.source", f"Σ_meas source (status {NOT_AVAILABLE}: the only supported one)",
                     "text"),
                    ("practical_target.preferred_max_abs_relative_error", "Preferred max |rel. error|", "number"),
                    ("practical_target.acceptable_max_abs_relative_error", "Acceptable max |rel. error|", "number"),
                    ("practical_target.note", "Practical target note", "multiline")),
    "algorithm": tuple((f"lm.{key}", f"LM {key}", "count" if f"lm.{key}" in COUNTS else "number") for key in LM_KEYS),
    "budget": (("abaqus_solve_budget", "Abaqus solve budget (hard)", "count"),
               ("archive_reuse", "Archive-reuse plan (repository path)", "text")),
    "provenance": (("decision", "Decision (SUPERVISOR reference)", "text"),
                   ("provenance", "Provenance (one entry per line)", "multiline")),
}


def _number(field: str, text: str, kind: str):
    if kind == "count":
        try:
            return int(text)
        except ValueError:
            raise CampaignDraftError(f"{field}: {text!r} is not a whole number.") from None
    try:
        return float(text)
    except ValueError:
        raise CampaignDraftError(f"{field}: {text!r} is not a number.") from None


def _entries(field: str, text: str, ranges: bool) -> dict:
    if text.strip().lower() == "none":  # explicitly no entry (e.g. RUN_B fixes nothing; no plausibility window)
        return {}
    result = {}
    for part in (p.strip() for p in text.split(";")):
        if not part:
            continue
        name, separator, value = part.partition("=")
        name = name.strip()
        if not separator or not name or name in result:
            raise CampaignDraftError(f"{field}: {part!r} is not 'name={'low..high' if ranges else 'value'}' (or a "
                                     "parameter is repeated).")
        if ranges:
            low, dots, high = value.partition("..")
            if not dots:
                raise CampaignDraftError(f"{field}: {part!r} needs 'low..high'.")
            result[name] = [_number(f"{field}.{name}", low.strip(), "number"),
                            _number(f"{field}.{name}", high.strip(), "number")]
        else:
            result[name] = _number(f"{field}.{name}", value.strip(), "number")
    if not result:
        raise CampaignDraftError(f"{field}: nothing entered (write 'none' for no entry)")
    return result


def values_from_text(group: str, texts) -> dict:
    """The group's values from the form text; nothing is filled in (an empty field is refused)."""

    if group not in FORM_FIELDS:
        raise CampaignDraftError(f"unknown configuration group {group!r}.")
    if not isinstance(texts, dict) or set(texts) != {field for field, _, _ in FORM_FIELDS[group]}:
        raise CampaignDraftError(f"{GROUP_TITLES[group]}: every field of the form must be given.")
    parsed = {}
    for field, _, kind in FORM_FIELDS[group]:
        text = texts[field]
        if not isinstance(text, str) or not text.strip():
            raise CampaignDraftError(f"{field}: not entered (no default is assumed).")
        text = text.strip()
        if kind in ("number", "count"):
            parsed[field] = _number(field, text, kind)
        elif kind in ("entries", "ranges"):
            parsed[field] = _entries(field, text, kind == "ranges")
        elif field == "fitted_parameters":
            parsed[field] = [name.strip() for name in text.split(",") if name.strip()]
        elif field == "provenance":
            parsed[field] = [line.strip() for line in text.splitlines() if line.strip()]
        else:
            parsed[field] = text
    if group == "uncertainty":
        return {"sigma": {"setup": {"sd_ln": parsed["sigma.setup.sd_ln"], "status": parsed["sigma.setup.status"],
                                    "source": parsed["sigma.setup.source"]},
                          "measurement": {"status": NOT_AVAILABLE, "source": parsed["sigma.measurement.source"]}},
                "practical_target": {key.split(".", 1)[1]: parsed[key] for key in parsed
                                     if key.startswith("practical_target.")}}
    if group == "algorithm":
        return {"lm": {key.split(".", 1)[1]: value for key, value in parsed.items()}}
    return parsed


def _format(value) -> str:
    return repr(float(value)) if isinstance(value, float) else str(value)


def texts_from_values(group: str, values: dict) -> dict:
    """Form text for declared or reference values (for display and for an explicit copy)."""

    if group == "material":
        def entries(mapping, ranges):
            if ranges and not mapping:
                return "none"
            return "; ".join(f"{k}={_format(v[0])}..{_format(v[1])}" if ranges else f"{k}={_format(v)}"
                             for k, v in mapping.items())
        return {"parameterisation": values["parameterisation"],
                "fitted_parameters": ", ".join(values["fitted_parameters"]),
                "fixed_parameters": entries(values["fixed_parameters"], False),
                "start": entries(values["start"], False), "bounds": entries(values["bounds"], True),
                "engineering_plausibility": entries(values["engineering_plausibility"], True)}
    if group == "uncertainty":
        sigma, target = values["sigma"], values["practical_target"]
        return {"sigma.setup.sd_ln": _format(sigma["setup"]["sd_ln"]), "sigma.setup.status": sigma["setup"]["status"],
                "sigma.setup.source": sigma["setup"]["source"], "sigma.measurement.source": sigma["measurement"]["source"],
                "practical_target.preferred_max_abs_relative_error": _format(target["preferred_max_abs_relative_error"]),
                "practical_target.acceptable_max_abs_relative_error":
                    _format(target["acceptable_max_abs_relative_error"]),
                "practical_target.note": target["note"]}
    if group == "algorithm":
        return {f"lm.{key}": _format(values["lm"][key]) for key in LM_KEYS}
    if group == "budget":
        return {"abaqus_solve_budget": str(values["abaqus_solve_budget"]), "archive_reuse": values["archive_reuse"]}
    return {"decision": values["decision"], "provenance": "\n".join(values["provenance"])}


def reference_configuration(repo_root: Path) -> dict:
    """The archived M7 RUN_A settings per group (definition only; its results are never read)."""

    path = Path(repo_root).joinpath(*PurePosixPath(REFERENCE_CAMPAIGN).parts)
    try:
        definition = load_campaign_definition(path)
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, CampaignDefinitionError) as error:
        raise CampaignDraftError(f"the reference {REFERENCE_CAMPAIGN} cannot be read: {error}") from error
    groups = {group: {key: data[key] for key in keys} for group, keys in CONFIGURATION_GROUPS.items()}
    return {"path": REFERENCE_CAMPAIGN, "campaign_id": definition.campaign_id, "schema": data["schema"],
            "run_type": definition.run_type, "campaign_hash": definition.campaign_hash, "values": groups,
            "texts": {group: texts_from_values(group, values) for group, values in groups.items()},
            "note": REFERENCE_NOTE}


COPYABLE_GROUPS = ("material", "uncertainty", "algorithm", "budget")  # settings only: never a decision or provenance


def copy_reference_texts(group: str, reference: dict) -> dict:
    """The reference settings of one group as form text, for an explicit copy (validated only when applied).

    The decision and provenance are never copied: the archived decision authorised the archived campaign only.
    """
    if group not in COPYABLE_GROUPS:
        raise CampaignDraftError(f"{GROUP_TITLES.get(group, group)} is never copied from the reference: the archived "
                                 "decision authorised the archived campaign only; declare it yourself.")
    return dict(reference["texts"][group])


def reference_source(reference: dict, edited: bool) -> str:
    origin = (f"{reference['path']} ({reference['campaign_id']}, campaign hash {reference['campaign_hash'][:12]}, "
              f"schema {reference['schema']})")
    if edited:
        return f"declared by the user (edited after an explicit copy from {origin}); every value validated"
    return f"copied by an explicit user choice from {origin}; every value validated; no M7 result carried over"


def declare_configuration(draft: CampaignDraft, group: str, texts, repo_root: Path, source: str) -> CampaignDraft:
    """The draft with one group declared from form text, refused on any rule or repository problem."""

    changed = draft.with_configuration(group, values_from_text(group, texts), source)
    problems = configuration_problems(changed, repo_root, groups=(group,))
    if problems:
        raise CampaignDraftError("; ".join(problems))
    return changed


def configuration_problems(draft: CampaignDraft, repo_root: Path, groups=None) -> list[str]:
    """Repository checks of the declared configuration the parser cannot make (empty: no problem found)."""

    root, configured, problems = Path(repo_root).resolve(), draft.configured(), []
    groups = tuple(CONFIGURATION_GROUPS) if groups is None else groups
    parameterisation = configured.get("parameterisation")
    if "material" in groups and parameterisation is not None:
        for item in draft.specimens:
            try:
                manifest = load_forward_model_manifest(root.joinpath(*PurePosixPath(item.forward_model).parts))
            except (OSError, ValueError) as error:
                problems.append(f"{item.label}: forward model unreadable ({error})")
                continue
            if manifest.parameterisation.parameterisation_id != parameterisation:
                problems.append(f"parameterisation {parameterisation} is not the parameterisation "
                                f"{manifest.parameterisation.parameterisation_id} of {item.forward_model}")
    reuse = configured.get("archive_reuse")
    if ("budget" in groups or "material" in groups) and reuse is not None:
        path = root.joinpath(*PurePosixPath(reuse).parts)
        if not path.is_file():
            problems.append(f"archive_reuse {reuse}: no such file in the repository")
        elif parameterisation is None:
            problems.append(f"archive_reuse {reuse}: declare the material parameters (parameterisation) to check it")
        else:
            try:
                plan = load_archive_reuse(path, parameterisation)
            except (OSError, ValueError, KeyError) as error:
                problems.append(f"archive_reuse {reuse}: not a valid archive-reuse plan ({error})")
            else:
                labels = {s.label for s in draft.specimens}
                foreign = sorted({entry.specimen for entry in (*plan.packs, *plan.odbs)} - labels)
                if foreign:
                    problems.append(f"archive_reuse {reuse}: names specimens {foreign} that the draft does not select")
    return problems


def configuration_rows(draft: CampaignDraft, repo_root: Path) -> list[tuple[str, str, str, str]]:
    """Review rows: each group's state and source, and the repository checks."""

    configured, rows = draft.configured(), []
    for group, keys in CONFIGURATION_GROUPS.items():
        declared = all(key in configured for key in keys)
        rows.append(("Configuration", GROUP_TITLES[group], draft.configuration_source(group) or
                     "not declared (no default)", "DECLARED" if declared else "NOT_DECLARED"))
    rows.append(("Configuration", "run_b_gate", "none (RUN_A)" if "run_b_gate" in configured else
                 ("never set by a draft: the SUPERVISOR gate of RUN_B" if draft.run_type == "RUN_B" else
                  "not declared"), "DECLARED" if "run_b_gate" in configured else "NOT_DECLARED"))
    for problem in configuration_problems(draft, repo_root):
        rows.append(("Configuration", "Repository check", problem, "REFUSED"))
    return rows


def reference_rows(repo_root: Path) -> list[tuple[str, str, str, str]]:
    """Read-only rows of the archived M7 RUN_A settings (reference)."""

    reference = reference_configuration(repo_root)
    rows = [("Reference", "Archived definition", f"{reference['path']} — {reference['campaign_id']} "
             f"({reference['run_type']}, campaign hash {reference['campaign_hash'][:12]})", "REFERENCE_ONLY"),
            ("Reference", "Note", reference["note"], "REFERENCE_ONLY")]
    for group, texts in reference["texts"].items():
        for field, text in texts.items():
            rows.append(("Reference", f"{GROUP_TITLES[group]}: {field}", text.replace("\n", " | "), "REFERENCE_ONLY"))
    return rows
