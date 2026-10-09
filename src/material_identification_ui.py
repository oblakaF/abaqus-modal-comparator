"""Informational UI for the Effective Material Identification workflow.

This module intentionally contains no scientific execution path. It presents
current project state and the supported task definition without starting
Abaqus or connecting an identification backend.

The pages present one of three contexts (``material_identification_presentation``):
nothing bound, an explicit historical SP13 import (UNBOUND), or a production
session whose BOUND evidence is rendered against the session's authoritative
``IdentificationModelDefinition``.  Parameter ids, order, units, assumptions and
limitations of production results come only from that definition.
"""

from __future__ import annotations

from collections.abc import Mapping
import csv
from dataclasses import dataclass
import json
from pathlib import Path, PureWindowsPath
import textwrap
from tkinter import filedialog, messagebox, ttk

from domain.identification_model import IdentificationModelDefinition
from domain.material_identification_session import MaterialIdentificationSession
from material_identification_evidence_view import (
    EMPTY_EVIDENCE_VIEW_MODEL,
    MaterialIdentificationEvidenceViewModel,
)
from sp13_evidence_adapter import HISTORICAL_STATUS, SP13EvidenceBundle
from ui_policy import MATERIAL_IDENTIFICATION_STEP_LABELS


_INSTALLED = False

_EVIDENCE_ROW_LABELS = (
    ("project", "Specimen / project"),
    ("fe_model", "FE model"),
    ("experimental_data", "Experimental data"),
    ("abaqus", "Abaqus availability"),
    ("provenance", "Provenance / validation"),
)

_STEP_DESCRIPTIONS = {
}

# Wording of the explicit historical SP13 import only (UNBOUND REAL-4 records).
# It describes that frozen study, not any current IdentificationModelDefinition,
# and is never shown for production or unbound-nothing states.
_HISTORICAL_SP13_TEXT = {
    "workflow": "Effective homogeneous face-sheet property identification",
    "unknowns": ("Ex", "Ey", "Gxy"),
    "frozen": ("Core", "Density", "Adhesive", "Geometry"),
    "task_interpretation": (
        "Effective homogeneous face-sheet properties\n\n"
        "Results are not true fibre properties, ply properties, or unique "
        "laminate constants."
    ),
    "identification_interpretation": (
        "Effective homogeneous face-sheet properties\n"
        "Not true fibre properties, ply properties, or unique laminate constants."
    ),
    "identification_limitations": (
        "Laminate architecture unknown",
        "Core frozen",
        "Density frozen",
        "Adhesive frozen",
        "Gxy weighting-sensitive",
    ),
    "validation_limitations": (
        "Effective properties only",
        "Laminate architecture unknown",
        "Core frozen",
        "Density frozen",
        "Adhesive frozen",
    ),
    "report_limitations": (
        "Effective properties only",
        "Not ply or fibre constants",
        "Unknown laminate architecture",
        "Frozen core and interface assumptions",
    ),
    "report_limitations_text": (
        "Effective properties only; not ply/fibre constants; unknown laminate "
        "architecture; frozen core/interface assumptions."
    ),
}

_NO_MODEL_TEXT = "No identification model selected."

_READINESS_EXPERIMENTAL_ROWS = (
    ("modal_data", "Modal data available"),
    ("mode_shapes", "Mode shapes available"),
    ("coordinates", "Coordinates available"),
    ("registration", "Registration status"),
)

_READINESS_FE_ROWS = (
    ("model_files", "CAE / INP / ODB availability"),
    ("geometry_consistency", "Geometry consistency"),
    ("thickness_consistency", "Thickness consistency"),
    ("material_provenance", "Material / provenance status"),
    ("adhesive_representation", "Adhesive representation status"),
)

_READINESS_STATES = {"READY", "WARNING", "BLOCKED"}


def _evidence_view_model(app) -> MaterialIdentificationEvidenceViewModel:
    view_model = getattr(app, "material_identification_evidence_view_model", None)
    if view_model is None:
        return EMPTY_EVIDENCE_VIEW_MODEL
    if not isinstance(view_model, MaterialIdentificationEvidenceViewModel):
        raise TypeError(
            "material_identification_evidence_view_model must be a "
            "MaterialIdentificationEvidenceViewModel."
        )
    return view_model


@dataclass(frozen=True)
class MaterialIdentificationPresentation:
    """The identification context the pages present.

    ``kind`` is ``"none"`` (nothing bound), ``"historical"`` (UNBOUND historical
    SP13 import) or ``"production"`` (BOUND evidence rendered against ``model``).
    The specimen label and the identification model are separate concepts.
    """

    kind: str
    view_model: MaterialIdentificationEvidenceViewModel
    specimen_label: str | None = None
    model: IdentificationModelDefinition | None = None
    registration_hash: str | None = None


def _view_records(view_model: MaterialIdentificationEvidenceViewModel) -> tuple:
    return tuple(
        record
        for record in (
            view_model.sensitivity,
            view_model.identifiability,
            view_model.identification,
            view_model.validation,
        )
        if record is not None
    )


def _historical_specimen(records) -> str | None:
    for record in records:
        details = getattr(record.provenance, "details", None)
        if isinstance(details, Mapping) and str(details.get("specimen") or "").strip():
            return str(details["specimen"]).strip()
    return None


def material_identification_presentation(app) -> MaterialIdentificationPresentation:
    """Classify what is bound; never infer a model from specimen or parameter names."""

    view_model = _evidence_view_model(app)
    session = getattr(app, "material_identification_session", None)
    if session is not None:
        if not isinstance(session, MaterialIdentificationSession):
            raise TypeError(
                "material_identification_session must be a MaterialIdentificationSession."
            )
        model = session.task_definition.model
        if (
            view_model.model is None
            or view_model.model.definition_hash != model.definition_hash
        ):
            raise ValueError(
                "The bound evidence view is not rendered against the session's "
                "identification model."
            )
        registration = session.registration_reference
        return MaterialIdentificationPresentation(
            kind="production",
            view_model=view_model,
            specimen_label=session.source_identities.specimen_label,
            model=model,
            registration_hash=(
                None if registration is None else registration.registration_hash
            ),
        )
    if view_model.model is not None:
        return MaterialIdentificationPresentation(
            kind="production", view_model=view_model, model=view_model.model
        )
    records = _view_records(view_model)
    if records:
        return MaterialIdentificationPresentation(
            kind="historical",
            view_model=view_model,
            specimen_label=_historical_specimen(records),
        )
    return MaterialIdentificationPresentation(kind="none", view_model=view_model)


def session_evidence_view_model(
    session: MaterialIdentificationSession,
    *,
    sensitivity=None,
    identifiability=None,
    identification=None,
    validation=None,
) -> MaterialIdentificationEvidenceViewModel:
    """Build the production view for a session, refusing evidence it does not own.

    The view checks each record's model id and definition hash; this also
    requires the registration and experimental content of every record to be
    the session's own FrozenRegistration, so results are never shown under
    another specimen's registration.
    """

    if not isinstance(session, MaterialIdentificationSession):
        raise TypeError("session must be a MaterialIdentificationSession.")
    view_model = MaterialIdentificationEvidenceViewModel(
        sensitivity=sensitivity,
        identifiability=identifiability,
        identification=identification,
        validation=validation,
        model=session.task_definition.model,
    )
    records = _view_records(view_model)
    registration = session.registration_reference
    if records and registration is None:
        raise ValueError(
            "The session has no FrozenRegistration, so its evidence cannot be presented."
        )
    for record in records:
        binding = record.scientific_binding
        if (
            binding.registration_hash != registration.registration_hash
            or binding.experimental_content_sha256
            != registration.experimental_content_sha256
        ):
            raise ValueError(
                f"{record.RECORD_TYPE} evidence {record.evidence_id!r} belongs to a "
                "different FrozenRegistration or experiment than the session."
            )
    return view_model


def _bullets(items) -> str:
    return "\n".join(f"• {item}" for item in items)


def model_presentation_text(
    presentation: MaterialIdentificationPresentation,
) -> dict[str, str]:
    """Page wording for the bound context; production text comes from the model."""

    if presentation.kind == "production":
        model = presentation.model
        parameters = model.parameter_definitions
        specimen = presentation.specimen_label or "Not stated"
        registration = presentation.registration_hash or "not bound"
        frozen = model.frozen_assumptions
        return {
            "scope": (
                f"Identification model: {model.display_name} ({model.model_id}). "
                "Parameters, units, assumptions and limitations come from the model "
                "definition."
            ),
            "context": (
                f"Specimen / source: {specimen}\n"
                f"Identification model: {model.display_name} ({model.model_id})\n"
                f"FrozenRegistration: {registration}"
            ),
            "workflow": model.display_name,
            "unknowns": "\n".join(
                f"• {item.display_name} [{item.unit}] — {item.meaning}"
                for item in parameters
            ),
            "frozen": _bullets(frozen) or "None stated by the model definition.",
            "frozen_inline": "; ".join(frozen) or "None stated by the model definition.",
            "task_interpretation": "\n".join(model.limitations),
            "identification_interpretation": "\n".join(model.limitations),
            "identification_limitations": _bullets(model.limitations),
            "validation_limitations": _bullets(model.limitations),
            "report_task": "\n".join(
                (
                    model.display_name,
                    f"Specimen / source: {specimen}",
                    "Unknown: "
                    + ", ".join(f"{item.display_name} [{item.unit}]" for item in parameters),
                    "Frozen assumptions: " + ("; ".join(frozen) or "none stated"),
                )
            ),
            "report_limitations": "; ".join(model.limitations),
        }
    if presentation.kind == "historical":
        text = _HISTORICAL_SP13_TEXT
        specimen = presentation.specimen_label or "Not stated"
        return {
            "scope": (
                f"Historical import of specimen {specimen} ({HISTORICAL_STATUS}): "
                "results are labelled effective homogeneous face-sheet properties, not "
                "true fibre properties, ply properties, or unique laminate constants."
            ),
            "context": (
                f"Specimen / source: {specimen} (historical import)\n"
                f"Identification model: not bound — {HISTORICAL_STATUS}\n"
                "FrozenRegistration: none (historical import)"
            ),
            "workflow": text["workflow"],
            "unknowns": _bullets(text["unknowns"]),
            "frozen": _bullets(text["frozen"]),
            "frozen_inline": "    ".join(f"{item} frozen" for item in text["frozen"]),
            "task_interpretation": text["task_interpretation"],
            "identification_interpretation": text["identification_interpretation"],
            "identification_limitations": _bullets(text["identification_limitations"]),
            "validation_limitations": _bullets(text["validation_limitations"]),
            "report_task": "\n".join(
                (
                    text["workflow"],
                    "Unknown: " + ", ".join(text["unknowns"]),
                    "Frozen: " + ", ".join(item.lower() for item in text["frozen"]),
                    f"Historical import: {HISTORICAL_STATUS}",
                )
            ),
            "report_limitations": text["report_limitations_text"],
        }
    return {
        "scope": (
            "No identification model is bound. Results are labelled by the "
            "identification model of the bound session."
        ),
        "context": (
            "Specimen / source: not bound\n"
            "Identification model: none selected\n"
            "FrozenRegistration: not bound"
        ),
        "workflow": "No identification task is bound.",
        "unknowns": _NO_MODEL_TEXT,
        "frozen": _NO_MODEL_TEXT,
        "frozen_inline": _NO_MODEL_TEXT,
        "task_interpretation": _NO_MODEL_TEXT,
        "identification_interpretation": _NO_MODEL_TEXT,
        "identification_limitations": _NO_MODEL_TEXT,
        "validation_limitations": _NO_MODEL_TEXT,
        "report_task": "No identification task is bound.",
        "report_limitations": _NO_MODEL_TEXT,
    }


def _sensitivity_columns(
    presentation: MaterialIdentificationPresentation, view: Mapping[str, object]
) -> tuple[tuple[str, str], ...]:
    """(column key, heading) for the parameter columns actually rendered.

    Production headings are the model parameters present in the sensitivity
    evidence, in model order; every rendered value is checked against the
    stored matrix under that label, so a column can never be mislabelled.
    """

    matrix = tuple(view["matrix"])
    if presentation.kind == "none" or not matrix:
        return ()
    if presentation.kind == "historical":
        names = tuple(name for name, _status in view["observability"])
    else:
        model = presentation.model
        content = presentation.view_model.sensitivity.content
        stored_ids = tuple(str(item) for item in content["parameter_ids"])
        stored_rows = tuple(content["scaled_sensitivity"])
        names = tuple(item for item in model.parameter_ids if item in stored_ids)
        for row, stored in zip(matrix, stored_rows):
            expected = tuple(float(stored[stored_ids.index(name)]) for name in names)
            if tuple(row[2:]) != expected:
                raise ValueError(
                    "Rendered sensitivity values do not match the stored matrix; "
                    "the parameter columns cannot be labelled safely."
                )
        names = tuple(model.parameter(item).display_name for item in names)
    if any(len(row) - 2 != len(names) for row in matrix):
        raise ValueError(
            "Rendered sensitivity rows do not match the parameter columns; the "
            "columns cannot be labelled safely."
        )
    keys = tuple(name.lower() for name in names)
    if len(set(keys)) != len(keys):
        keys = tuple(f"parameter_{index}" for index in range(len(names)))
    return tuple(zip(keys, names))


def _record_value(record, *names, default=None):
    for name in names:
        if isinstance(record, Mapping) and name in record:
            return record[name]
        if hasattr(record, name):
            return getattr(record, name)
    return default


def _status_value(value: object) -> str:
    if hasattr(value, "value"):
        value = value.value
    return str(value or "").strip()


def _mode_rows(dataset, pair_statuses: dict[int, str]) -> tuple[tuple, ...]:
    if dataset is None:
        return ()
    rows = []
    for mode in getattr(dataset, "modes", ()) or ():
        mode_id = int(getattr(mode, "number"))
        metadata = getattr(mode, "metadata", {}) or {}
        source_status = metadata.get("status", "") if hasattr(metadata, "get") else ""
        status = pair_statuses.get(mode_id) or str(source_status).strip() or "Unpaired"
        rows.append((mode_id, float(getattr(mode, "frequency_hz")), status))
    return tuple(rows)


def _existing_family_records(result) -> tuple:
    for attribute in ("modal_clusters", "clusters", "families"):
        records = getattr(result, attribute, None)
        if records:
            return tuple(records)
    metadata = getattr(result, "metadata", {}) or {}
    if isinstance(metadata, Mapping):
        for key in ("modal_clusters", "clusters", "families"):
            records = metadata.get(key)
            if records:
                return tuple(records)
        analysis = metadata.get("cluster_analysis")
        records = getattr(analysis, "clusters", None)
        if records:
            return tuple(records)
    return ()


def _family_row(record) -> tuple[str, str, str, str]:
    fe_ids = tuple(_record_value(record, "fe_mode_ids", default=()) or ())
    exp_ids = tuple(_record_value(record, "experimental_mode_ids", default=()) or ())
    label = _record_value(record, "family_label", "label", default="")
    if not label and (fe_ids or exp_ids):
        fe_label = "/".join(f"A{int(value)}" for value in fe_ids) or "FE —"
        exp_label = "/".join(f"E{int(value)}" for value in exp_ids) or "EXP —"
        label = f"{fe_label} ↔ {exp_label}"
    if not label:
        label = _record_value(record, "cluster_id", "family_id", default="Family")

    identity = _record_value(
        record,
        "family_identity_status",
        "identity_status",
        "gate_status",
        default=None,
    )
    if isinstance(identity, bool):
        identity = "PASS" if identity else "FAIL"
    elif identity is None:
        inclusion = _status_value(
            _record_value(record, "inclusion_status", default="")
        ).lower()
        identity = {
            "included": "PASS",
            "excluded": "FAIL",
            "downweighted": "REVIEW",
        }.get(inclusion, "Not stated")
    else:
        identity = _status_value(identity)

    subspace = _record_value(record, "subspace_mac", default=None)
    evidence = _record_value(
        record,
        "subspace_evidence",
        "family_identity_evidence",
        default=None,
    )
    if subspace is not None:
        subspace_status = f"available (subspace MAC {float(subspace):.3f})"
    elif evidence is not None:
        subspace_status = "available"
    else:
        subspace_status = "not available"
    return str(label), str(identity), "not forced", subspace_status


def modal_correspondence_view(result) -> dict[str, tuple]:
    """Adapt existing correspondence evidence without matching or recomputation."""

    if result is None:
        return {
            "experimental_modes": (),
            "fe_modes": (),
            "correspondences": (),
            "families": (),
        }

    pairs = tuple(getattr(result, "pairs", ()) or ())
    exp_statuses = {
        int(pair.experimental_mode): str(pair.status) for pair in pairs
    }
    fe_statuses = {int(pair.abaqus_mode): str(pair.status) for pair in pairs}
    correspondences = tuple(
        (
            int(pair.experimental_mode),
            int(pair.abaqus_mode),
            float(pair.frequency_error_percent),
            None if pair.mac is None else float(pair.mac),
            str(pair.status),
        )
        for pair in pairs
    )
    return {
        "experimental_modes": _mode_rows(
            getattr(result, "experimental", None), exp_statuses
        ),
        "fe_modes": _mode_rows(getattr(result, "abaqus", None), fe_statuses),
        "correspondences": correspondences,
        "families": tuple(
            _family_row(record) for record in _existing_family_records(result)
        ),
    }


def sensitivity_evidence_view(app) -> dict[str, object]:
    """Render only the typed evidence view model bound to the application.

    With nothing bound there is no parameter list to present, so no
    placeholder parameter rows are shown.
    """

    presentation = material_identification_presentation(app)
    view = presentation.view_model.sensitivity_view()
    if presentation.kind == "none":
        view = {**view, "observability": ()}
    return view


def _format_number(value: object) -> str:
    if value is None:
        return "Unavailable"
    try:
        return f"{float(value):.6g}"
    except (TypeError, ValueError):
        return str(value)


def identification_result_view(app) -> dict[str, object]:
    """Render only the typed identification evidence bound to the application.

    Rows, order and units come from the bound view (the model definition for
    production evidence); with nothing bound no parameter rows are shown.
    """

    presentation = material_identification_presentation(app)
    view = presentation.view_model.identification_view()
    if presentation.kind == "none":
        view = {**view, "model_u": (), "model_p": (), "comparison": ()}
    return view


def validation_evidence_view(app) -> dict[str, object]:
    """Render only the typed validation evidence bound to the application."""

    return _evidence_view_model(app).validation_view()


def _json_safe(value):
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "tolist"):
        return _json_safe(value.tolist())
    if hasattr(value, "value"):
        return _json_safe(value.value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def report_evidence_snapshot(app) -> dict[str, object]:
    """Build a deterministic report snapshot from existing presentation records."""

    project = project_evidence_status(app)
    presentation = material_identification_presentation(app)
    identification = identification_result_view(app)
    validation = validation_evidence_view(app)

    def properties(rows):
        return {
            parameter: {"value": value, "unit": unit}
            for parameter, value, unit in rows
        }

    text = model_presentation_text(presentation)
    task_definition: dict[str, object] = {
        "context": presentation.kind,
        "specimen": presentation.specimen_label,
        "description_lines": text["report_task"].splitlines(),
    }
    if presentation.kind == "production":
        model = presentation.model
        task_definition.update(
            {
                "identification_model_id": model.model_id,
                "identification_model_name": model.display_name,
                "identification_model_hash": model.definition_hash,
                "registration_hash": presentation.registration_hash,
                "unknown_parameters": [
                    {
                        "parameter_id": item.parameter_id,
                        "display_name": item.display_name,
                        "unit": item.unit,
                    }
                    for item in model.parameter_definitions
                ],
                "frozen_assumptions": list(model.frozen_assumptions),
            }
        )
        limitations = list(model.limitations)
    elif presentation.kind == "historical":
        task_definition.update(
            {
                "historical_status": HISTORICAL_STATUS,
                "workflow": _HISTORICAL_SP13_TEXT["workflow"],
                "unknown_parameters": list(_HISTORICAL_SP13_TEXT["unknowns"]),
                "frozen": [item.lower() for item in _HISTORICAL_SP13_TEXT["frozen"]],
            }
        )
        limitations = list(_HISTORICAL_SP13_TEXT["report_limitations"])
    else:
        task_definition["unknown_parameters"] = []
        limitations = []

    snapshot = {
        "schema_version": "material-identification-gui-7",
        "project_summary": {
            "specimen_or_project": project["project"],
            "fe_model": project["fe_model"],
            "experimental_dataset": project["experimental_data"],
            "provenance_status": project["provenance"],
        },
        "task_definition": task_definition,
        "identification_result": {
            "available": identification["available"],
            "status": identification["status"],
            "model_u": properties(identification["model_u"]),
            "model_p": properties(identification["model_p"]),
            "comparison": [
                {
                    "parameter": parameter,
                    "stored_u_p_difference_percent": difference,
                    "weighting_sensitivity_status": weighting,
                }
                for parameter, difference, weighting in identification["comparison"]
            ],
        },
        "validation": {
            "available": validation["available"],
            "status": validation["status"],
            "primary_observables": [
                {
                    "model": model,
                    "observable": observable,
                    "experimental_frequency": experimental,
                    "fe_frequency": fe_value,
                    "stored_residual_or_error": residual,
                    "status": status,
                }
                for model, observable, experimental, fe_value, residual, status in validation[
                    "primary"
                ]
            ],
            "holdouts": [
                {
                    "model": model,
                    "observable": observable,
                    "experimental_frequency": experimental,
                    "fe_frequency": fe_value,
                    "stored_residual_or_error": residual,
                    "status": status,
                    "usage": "NOT USED FOR IDENTIFICATION",
                }
                for model, observable, experimental, fe_value, residual, status in validation[
                    "holdout"
                ]
            ],
        },
        "limitations": limitations,
    }
    snapshot["report_available"] = bool(
        identification["available"] or validation["available"]
    )
    return _json_safe(snapshot)


def export_material_identification_json(snapshot, destination: Path) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(_json_safe(snapshot), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def export_material_identification_csv(snapshot, destination: Path) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for key, value in snapshot["project_summary"].items():
        rows.append(("project_summary", "", "", key, "", "", value, "", "", ""))
    for model_key in ("model_u", "model_p"):
        for parameter, item in snapshot["identification_result"][model_key].items():
            rows.append(
                (
                    "identification",
                    model_key[-1].upper(),
                    "",
                    parameter,
                    "",
                    "",
                    item.get("value"),
                    snapshot["identification_result"]["status"],
                    item.get("unit"),
                    "",
                )
            )
    for item in snapshot["identification_result"]["comparison"]:
        rows.append(
            (
                "identification_comparison",
                "U/P",
                "",
                item["parameter"],
                "",
                "",
                item["stored_u_p_difference_percent"],
                item["weighting_sensitivity_status"],
                "%",
                "",
            )
        )
    for scope, key in (("primary", "primary_observables"), ("holdout", "holdouts")):
        for item in snapshot["validation"][key]:
            rows.append(
                (
                    "validation",
                    item["model"],
                    scope,
                    item["observable"],
                    item["experimental_frequency"],
                    item["fe_frequency"],
                    item["stored_residual_or_error"],
                    item["status"],
                    "",
                    item.get("usage", ""),
                )
            )
    with destination.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            (
                "section",
                "model",
                "scope",
                "item",
                "experimental_frequency",
                "fe_frequency",
                "value_or_error",
                "status",
                "unit",
                "usage",
            )
        )
        writer.writerows(rows)
    return destination


def _report_lines(snapshot) -> list[str]:
    project = snapshot["project_summary"]
    identification = snapshot["identification_result"]
    validation = snapshot["validation"]
    lines = [
        "PROJECT SUMMARY",
        f"Specimen/project: {project['specimen_or_project']}",
        f"FE model: {project['fe_model']}",
        f"Experimental dataset: {project['experimental_dataset']}",
        f"Provenance: {project['provenance_status']}",
        "",
        "TASK DEFINITION",
        *snapshot["task_definition"]["description_lines"],
        "",
        "IDENTIFICATION RESULT",
        f"Status: {identification['status']}",
    ]
    for model_key, model_label in (("model_u", "Model U"), ("model_p", "Model P")):
        values = identification[model_key]
        summary = ", ".join(
            f"{parameter}={item['value']} {item['unit']}"
            for parameter, item in values.items()
        )
        lines.append(f"{model_label}: {summary}")
    for item in identification["comparison"]:
        lines.append(
            f"U/P {item['parameter']}: difference="
            f"{item['stored_u_p_difference_percent']}%; "
            f"weighting={item['weighting_sensitivity_status']}"
        )
    lines.extend(("", "VALIDATION", f"Status: {validation['status']}", "Primary:"))
    for item in validation["primary_observables"]:
        lines.append(
            f"{item['model']} {item['observable']}: EXP={item['experimental_frequency']}, "
            f"FE={item['fe_frequency']}, error={item['stored_residual_or_error']}, "
            f"status={item['status']}"
        )
    lines.append("Holdouts - NOT USED FOR IDENTIFICATION:")
    for item in validation["holdouts"]:
        lines.append(
            f"{item['model']} {item['observable']}: EXP={item['experimental_frequency']}, "
            f"FE={item['fe_frequency']}, error={item['stored_residual_or_error']}, "
            f"status={item['status']}"
        )
    lines.extend(("", "LIMITATIONS", *(f"- {item}" for item in snapshot["limitations"])))
    return lines


def export_material_identification_pdf(snapshot, destination: Path) -> Path:
    """Write a deterministic text report from the supplied stored-evidence snapshot."""

    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.figure import Figure

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    expanded_lines = []
    for line in _report_lines(snapshot):
        safe_line = (
            str(line)
            .replace("\u2014", "-")
            .replace("\u2194", "<->")
            .replace("\u2022", "-")
        )
        expanded_lines.extend(textwrap.wrap(safe_line, width=100) or [""])
    lines_per_page = 46
    pages = [
        expanded_lines[index : index + lines_per_page]
        for index in range(0, max(len(expanded_lines), 1), lines_per_page)
    ]
    with PdfPages(destination) as pdf:
        for page_number, lines in enumerate(pages, start=1):
            figure = Figure(figsize=(8.27, 11.69))
            figure.text(
                0.08,
                0.95,
                "Effective Material Identification Report",
                fontsize=17,
                weight="bold",
            )
            y = 0.91
            for line in lines:
                is_heading = bool(line) and line == line.upper() and not line.startswith("-")
                figure.text(
                    0.08,
                    y,
                    line,
                    fontsize=10.5 if is_heading else 9,
                    weight="bold" if is_heading else "normal",
                    family="sans-serif",
                )
                y -= 0.018
            figure.text(
                0.5,
                0.035,
                f"Page {page_number} of {len(pages)}",
                fontsize=8,
                ha="center",
                color="#59636E",
            )
            pdf.savefig(figure)
    return destination


def _selected_source_status(path_value: object) -> str:
    text = str(path_value or "").strip()
    if not text:
        return "Not selected"
    # PureWindowsPath splits on both "\" and "/", so the displayed file name does not
    # depend on the host OS (a Windows path shown on Linux keeps only its file name).
    return f"Selected — {PureWindowsPath(text).name}"


def project_evidence_status(app) -> dict[str, str]:
    """Derive the evidence summary without reading files or running tools."""

    project_path = getattr(app, "project_path", None)
    project_name = Path(project_path).name if project_path else "Unsaved project"

    abaqus_path = getattr(app, "abaqus_path", None)
    experimental_path = getattr(app, "experimental_path", None)
    installations = getattr(app, "_abaqus_installations", {}) or {}
    selected_launcher = getattr(app, "abaqus_installation_label", None)
    selected_launcher = selected_launcher.get() if selected_launcher is not None else ""
    if selected_launcher in installations:
        abaqus_status = f"Available — {selected_launcher}"
    elif installations:
        count = len(installations)
        suffix = "launcher" if count == 1 else "launchers"
        abaqus_status = f"Available — {count} detected {suffix}"
    else:
        abaqus_status = "Unavailable — no launcher detected"

    result = getattr(app, "result", None)
    if result is None:
        provenance_status = "Not validated — no modal comparison result"
    else:
        geometry = getattr(result, "geometry", None)
        calibration = getattr(geometry, "calibration_details", {}) or {}
        provenance = calibration.get("provenance") if hasattr(calibration, "get") else None
        if str(provenance or "").strip():
            provenance_status = (
                "Available — comparison result and calibration provenance loaded"
            )
        else:
            provenance_status = (
                "Partial — comparison result loaded; calibration provenance not declared"
            )

    return {
        "project": project_name,
        "fe_model": _selected_source_status(
            abaqus_path.get() if abaqus_path is not None else ""
        ),
        "experimental_data": _selected_source_status(
            experimental_path.get() if experimental_path is not None else ""
        ),
        "abaqus": abaqus_status,
        "provenance": provenance_status,
    }


def _readiness_record(app):
    for attribute in (
        "data_readiness_evidence",
        "material_data_readiness",
        "readiness_evidence",
    ):
        record = getattr(app, attribute, None)
        if isinstance(record, Mapping):
            return record
    return None


def _readiness_rows(section, definitions) -> tuple[tuple[str, str, str, str], ...]:
    source = section if isinstance(section, Mapping) else {}
    rows = []
    for key, label in definitions:
        item = source.get(key)
        if isinstance(item, Mapping):
            status = _status_value(
                _record_value(item, "status", "state", default="")
            ).upper()
            detail = _status_value(
                _record_value(item, "detail", "evidence", "message", default="")
            )
        else:
            status = _status_value(item).upper()
            detail = ""
        if status not in _READINESS_STATES:
            status = "BLOCKED"
            if not detail:
                detail = "No stored readiness evidence"
        rows.append((key, label, status, detail or "Stored evidence available"))
    return tuple(rows)


def data_readiness_view(app) -> dict[str, object]:
    """Present an existing readiness record without inspecting or fixing data."""

    record = _readiness_record(app)
    experimental = _readiness_rows(
        _record_value(record, "experimental", default={}) if record else {},
        _READINESS_EXPERIMENTAL_ROWS,
    )
    fe = _readiness_rows(
        _record_value(record, "fe", "finite_element", default={}) if record else {},
        _READINESS_FE_ROWS,
    )
    stored_overall = _status_value(
        _record_value(record, "overall_status", "status", default="")
        if record
        else ""
    ).upper()
    states = tuple(row[2] for row in (*experimental, *fe))
    if stored_overall in _READINESS_STATES:
        overall = stored_overall
    elif "BLOCKED" in states:
        overall = "BLOCKED"
    elif "WARNING" in states:
        overall = "WARNING"
    else:
        overall = "READY"
    return {
        "available": record is not None,
        "overall_status": overall,
        "experimental": experimental,
        "fe": fe,
    }


def scientific_readiness_view(app) -> dict[str, object]:
    """Present a stored SPEC v1.2 scientific readiness record (V12-I6) without judging anything.

    The record is produced by the shared backend (``services.campaign_scientific_backend``); its display rows come
    from the same backend, so the GUI never evaluates, converts or fills in a scientific state.

    M8.2: the stored record is presented only under its own governed selection (``readiness_selection``); another
    source never inherits it.  The record itself is never changed.
    """

    from services.auto_id_wizard import SelectionState, readiness_selection
    from services.campaign_scientific_backend import readiness_presentation

    record = getattr(app, "scientific_readiness_record", None)
    evaluated, current = None, None
    if record is not None and getattr(app, "auto_id_evaluated_record", None) is record:
        # M8.3: a record this GUI evaluated is current only for the exact journal and run of its successful evaluation
        active = getattr(app, "auto_id_active_evaluation", None)
        current = active is not None and active[2] is record \
            and active[0] == getattr(app, "auto_id_selected_run_path", None) \
            and active[1] == getattr(app, "auto_id_selected_run_hash", None)
        evaluated = active[1] if current else None
    selection = readiness_selection(getattr(app, "auto_id_source", None) is not None,
                                    getattr(app, "auto_id_preparation", None), record,
                                    getattr(app, "auto_id_selected_run_hash", None), evaluated, current)
    rows = readiness_presentation(record) if selection.show_record and isinstance(record, Mapping) else ()
    if rows:
        status = dict(rows).get("Readiness") or "NOT AVAILABLE"
    elif selection.state is SelectionState.NOT_EVALUATED_FOR_SELECTION:
        status = selection.state.value
    else:
        status = "NOT AVAILABLE"
    return {
        "available": bool(rows),
        "status": status,
        "rows": rows,
        "selection_state": selection.state.value,
        "selection": selection.detail,
    }


AUTO_ID_REPO_ROOT = Path(__file__).resolve().parents[1]
AUTO_ID_SETUP_SCOPE = (
    "Select one specimen folder (with its specimen passport) or a family / campaign definition. The governed "
    "records are loaded read-only and shown with exactly what is present, missing or not verified. Nothing is "
    "chosen, judged or computed here: no experimental or FE modes, modal families or registration are selected, "
    "no material property or calibration is produced, nothing is written and Abaqus is never started. A file "
    "found locally is not a governed or scientifically accepted file."
)
AUTO_ID_NOTHING_SELECTED = "Nothing selected."


def load_auto_id_source(app, kind: str, path: str) -> None:
    """Load a specimen folder or a family / campaign definition through the M8.1 wizard service (read-only)."""

    from domain.experiment_fixture import fixture_roots_from_environment
    from services.auto_id_wizard import prepare_family, prepare_specimen_folder, wizard_summary

    app.auto_id_source = (kind, str(path))
    _clear_auto_id_run(app)  # M8.3: a run belongs to one campaign selection; a new selection resets it
    app.auto_id_specimens = None  # M8.4: governed specimen inputs belong to one campaign selection
    try:
        roots = fixture_roots_from_environment()
        if kind == "family":
            preparation = prepare_family(Path(path), AUTO_ID_REPO_ROOT, roots)
        else:
            preparation = prepare_specimen_folder(Path(path), AUTO_ID_REPO_ROOT, roots)
        summary = wizard_summary(preparation)
    except Exception as error:  # an unexpected record problem is reported, never a GUI crash
        preparation, summary = None, f"The selection could not be loaded: {error}"
    app.auto_id_preparation = preparation
    app.auto_id_summary = summary
    _refresh_auto_id_setup_page(app)
    _refresh_data_readiness_page(app)  # M8.2: the readiness shown follows the new selection at once


AUTO_ID_EVALUATE_LABEL = "Auto-ID — Evaluate Stored Run"
AUTO_ID_NO_RUN = "No stored run selected."


def _clear_auto_id_run(app) -> None:
    app.auto_id_active_evaluation = None  # no earlier evaluation is current for a new selection
    app.auto_id_selected_run_path = None
    app.auto_id_selected_run_hash = None
    app.auto_id_run_message = AUTO_ID_NO_RUN
    app.auto_id_progress = None  # M8.4: no progress of another selection stays visible


def _auto_id_specimens(app, definition):
    """The selected campaign's governed specimen inputs (read-only preparation), cached for this campaign selection."""

    from domain.experiment_fixture import fixture_roots_from_environment
    from services.stored_run_evidence import campaign_specimens

    cached = getattr(app, "auto_id_specimens", None)
    if cached is not None and cached[0] == definition.campaign_hash:
        return cached[1], cached[2]
    try:
        specimens, problem = campaign_specimens(definition, AUTO_ID_REPO_ROOT, fixture_roots_from_environment()), None
    except Exception as error:  # stores unavailable or the chain refused: shown, never a crash
        specimens, problem = None, str(error)
    app.auto_id_specimens = (definition.campaign_hash, specimens, problem)
    return specimens, problem


def _inspect_auto_id_progress(app, journal_path):
    """M8.4: verified, read-only progress of the selected stored run (fresh from disk; nothing is executed)."""

    from services.auto_id_wizard import FamilyPreparation
    from services.run_progress import inspect_run_progress

    preparation = getattr(app, "auto_id_preparation", None)
    definition = preparation.definition if isinstance(preparation, FamilyPreparation) else None
    specimens, problem = (None, None) if definition is None or journal_path is None \
        else _auto_id_specimens(app, definition)
    try:
        app.auto_id_progress = inspect_run_progress(definition, journal_path, specimens, problem)
    except Exception as error:  # never a GUI crash; never presented as progress
        from services.run_progress import _not_verified

        app.auto_id_progress = _not_verified(journal_path, f"inspection failed ({error})")


def refresh_auto_id_progress(app) -> None:
    """"Refresh run progress": re-read and re-verify the selected run's journals; no evaluation is started. An active
    scientific evaluation stops being current when the journal content changed since it was evaluated."""

    path = getattr(app, "auto_id_selected_run_path", None)
    _inspect_auto_id_progress(app, path)
    progress = app.auto_id_progress
    if getattr(app, "auto_id_active_evaluation", None) is not None \
            and (not progress.verified or progress.fingerprint != getattr(app, "auto_id_evaluated_fingerprint", None)):
        app.auto_id_active_evaluation = None
        app.auto_id_run_message = ("The selected run's journal changed or is no longer verified since its evaluation: "
                                   "the earlier result is not current (evaluate it again).")
    _refresh_auto_id_setup_page(app)
    _refresh_data_readiness_page(app)


def reopen_auto_id_run(app) -> None:
    """"Reopen selected run": select the same journal again (identity re-verified, earlier evaluation not current)."""

    path = getattr(app, "auto_id_selected_run_path", None)
    if path is None:
        app.auto_id_run_message = "Nothing to reopen: select the journal of an existing run of this campaign."
        _refresh_auto_id_setup_page(app)
        return
    select_auto_id_run(app, path)


def select_auto_id_run(app, journal_path) -> None:
    """Select an existing journalled campaign run explicitly (read-only; nothing is evaluated yet)."""

    from services.stored_run_evidence import StoredRunRefusal, select_stored_run

    _clear_auto_id_run(app)
    try:
        run = select_stored_run(journal_path)
    except StoredRunRefusal as refusal:
        app.auto_id_run_message = f"Run not selected: {refusal}"
    except Exception as error:  # never a GUI crash
        app.auto_id_run_message = f"Run not selected: {error}"
    else:
        app.auto_id_selected_run_path = str(run.journal_path)
        app.auto_id_selected_run_hash = run.run_hash
        app.auto_id_run_message = f"Selected run {run.run_hash[:12]} ({run.journal_path}); not evaluated yet."
    _inspect_auto_id_progress(app, journal_path)  # M8.4: the new selection is verified before anything is shown
    _refresh_auto_id_setup_page(app)
    _refresh_data_readiness_page(app)


def evaluate_auto_id_run(app) -> None:
    """"Auto-ID — Evaluate Stored Run": judge the selected journalled run of the selected governed campaign with the
    shared backend (read-only). The backend's readiness record is stored unchanged and shown, selection-bound, on the
    Data Readiness Check page; nothing is solved, executed or written."""

    from domain.experiment_fixture import fixture_roots_from_environment
    from services.auto_id_wizard import FamilyPreparation
    from services.stored_run_evidence import StoredRunRefusal, evaluate_stored_run

    app.auto_id_active_evaluation = None  # invalidated before any attempt; only a returned result becomes current
    preparation = getattr(app, "auto_id_preparation", None)
    definition = preparation.definition if isinstance(preparation, FamilyPreparation) else None
    run_path = getattr(app, "auto_id_selected_run_path", None)
    if definition is None:
        app.auto_id_run_message = ("No evaluation: select a governed family / campaign definition (a specimen folder "
                                   "declares no campaign).")
    elif run_path is None:
        app.auto_id_run_message = "No evaluation: select the journal of an existing run of this campaign."
    else:
        try:
            evaluation = evaluate_stored_run(definition, run_path, AUTO_ID_REPO_ROOT,
                                             fixture_roots_from_environment())
        except StoredRunRefusal as refusal:
            app.auto_id_run_message = f"No evaluation: {refusal}"
        except Exception as error:  # an unexpected evidence problem is reported, never a GUI crash
            app.auto_id_run_message = f"No evaluation: the stored run could not be evaluated ({error})"
        else:
            record = evaluation.readiness.to_dict()
            app.scientific_readiness_record = record
            app.auto_id_evaluated_record = record
            app.auto_id_evaluated_run_hash = evaluation.run.run_hash
            app.auto_id_active_evaluation = (run_path, evaluation.run.run_hash, record)
            from services.run_progress import journal_fingerprint

            app.auto_id_evaluated_fingerprint = journal_fingerprint(evaluation.run.run_hash,
                                                                    evaluation.run.campaign_journal.get("entries") or ())
            notes = f" Loading notes: {'; '.join(evaluation.notes)}." if evaluation.notes else ""
            app.auto_id_run_message = (f"Evaluated stored run {evaluation.run.run_hash[:12]} with the shared backend: "
                                       f"{record['status']} (see Data Readiness Check).{notes}")
    _refresh_auto_id_setup_page(app)
    _refresh_data_readiness_page(app)


def _choose_auto_id_run(app) -> None:
    path = filedialog.askopenfilename(
        title="Stored campaign run journal (campaign/<run hash>/journal.json)",
        filetypes=(("Run journal", "journal.json"), ("JSON", "*.json")),
    )
    if path:
        select_auto_id_run(app, path)


def _choose_auto_id_source(app, kind: str) -> None:
    if kind == "family":
        path = filedialog.askopenfilename(
            title="Family / campaign definition",
            filetypes=(("Campaign definition", "*.campaign.json"), ("JSON", "*.json")),
        )
    else:
        path = filedialog.askdirectory(title="Specimen folder")
    if path:
        load_auto_id_source(app, kind, path)


def auto_id_setup_view(app) -> dict[str, object]:
    """Rows of the loaded selection (presentation only)."""

    from services.auto_id_wizard import preparation_rows

    preparation = getattr(app, "auto_id_preparation", None)
    source = getattr(app, "auto_id_source", None)
    return {
        "source": "" if source is None else f"{source[0]}: {source[1]}",
        "summary": getattr(app, "auto_id_summary", None) or AUTO_ID_NOTHING_SELECTED,
        "rows": preparation_rows(preparation),
    }


def _build_auto_id_setup_page(app, page) -> None:
    ttk.Label(page, text=AUTO_ID_SETUP_SCOPE, justify="left", wraplength=1100).pack(
        anchor="nw", fill="x", pady=(0, 8)
    )
    buttons = ttk.Frame(page)
    buttons.pack(anchor="w", pady=(0, 8))
    ttk.Button(
        buttons,
        text="Select specimen folder...",
        command=lambda: _choose_auto_id_source(app, "specimen"),
    ).pack(side="left")
    ttk.Button(
        buttons,
        text="Select family / campaign definition...",
        command=lambda: _choose_auto_id_source(app, "family"),
    ).pack(side="left", padx=(8, 0))
    run_buttons = ttk.Frame(page)
    run_buttons.pack(anchor="w", pady=(0, 8))
    ttk.Button(
        run_buttons,
        text="Select stored run journal...",
        command=lambda: _choose_auto_id_run(app),
    ).pack(side="left")
    ttk.Button(
        run_buttons,
        text=AUTO_ID_EVALUATE_LABEL,
        command=lambda: evaluate_auto_id_run(app),
    ).pack(side="left", padx=(8, 0))
    app.material_auto_id_run_label = ttk.Label(page, text=AUTO_ID_NO_RUN, justify="left", wraplength=1100)
    app.material_auto_id_run_label.pack(anchor="nw", fill="x", pady=(0, 4))
    progress = ttk.LabelFrame(page, text="Selected run progress (read-only; nothing is resumed or executed)", padding=8)
    progress.pack(fill="x", pady=(0, 8))
    progress_buttons = ttk.Frame(progress)
    progress_buttons.pack(anchor="w", pady=(0, 4))
    ttk.Button(
        progress_buttons,
        text="Refresh run progress",
        command=lambda: refresh_auto_id_progress(app),
    ).pack(side="left")
    ttk.Button(
        progress_buttons,
        text="Reopen selected run",
        command=lambda: reopen_auto_id_run(app),
    ).pack(side="left", padx=(8, 0))
    app.material_auto_id_progress_label = ttk.Label(progress, text="NOT_SELECTED", style="MetricValue.TLabel")
    app.material_auto_id_progress_label.pack(anchor="w", pady=(0, 4))
    app.material_auto_id_progress_table = _build_read_only_table(
        progress, ("item", "value"), ("Item", "Recorded in the verified journals"), (240, 900), height=8
    )
    app.material_auto_id_source_label = ttk.Label(page, text="", justify="left", wraplength=1100)
    app.material_auto_id_source_label.pack(anchor="nw", fill="x")
    app.material_auto_id_summary_label = ttk.Label(
        page, text=AUTO_ID_NOTHING_SELECTED, justify="left", wraplength=1100
    )
    app.material_auto_id_summary_label.pack(anchor="nw", fill="x", pady=(4, 8))
    app.material_auto_id_table = _build_read_only_table(
        page,
        ("section", "item", "value", "status", "provenance"),
        ("Section", "Item", "Value", "Status", "Provenance"),
        (190, 230, 300, 210, 420),
        height=18,
    )
    ttk.Label(
        page,
        text=(
            "PRESENT_SHA256_NOT_VERIFIED: a pinned file was found with its pinned size only; its SHA-256 is "
            "verified by the backend when the file is used. Scientific readiness is judged on the Data "
            "Readiness Check page by the shared backend, never here."
        ),
        style="Secondary.TLabel",
        justify="left",
        wraplength=1100,
    ).pack(anchor="nw", fill="x", pady=(8, 0))


def _refresh_auto_id_setup_page(app) -> None:
    if not hasattr(app, "material_auto_id_table"):
        return
    view = auto_id_setup_view(app)
    _replace_table_rows(app.material_auto_id_table, view["rows"])
    app.material_auto_id_summary_label.configure(text=view["summary"])
    app.material_auto_id_source_label.configure(text=view["source"])
    if hasattr(app, "material_auto_id_run_label"):
        app.material_auto_id_run_label.configure(text=getattr(app, "auto_id_run_message", None) or AUTO_ID_NO_RUN)
    if hasattr(app, "material_auto_id_progress_table"):
        progress = getattr(app, "auto_id_progress", None)
        _replace_table_rows(app.material_auto_id_progress_table, () if progress is None else progress.rows)
        app.material_auto_id_progress_label.configure(text="NOT_SELECTED" if progress is None
                                                      else progress.state.value)


def _build_project_evidence_page(app, page) -> None:
    section = ttk.LabelFrame(page, text="1. Project Evidence", padding=16)
    section.pack(fill="both", expand=True)
    ttk.Label(
        section,
        text=(
            "Read-only evidence from the current modal-comparator project. "
            "This page does not open Abaqus or run an analysis."
        ),
        justify="left",
        wraplength=1050,
    ).pack(anchor="nw", fill="x", pady=(0, 12))

    app.material_identification_evidence_labels = {}
    for key, caption in _EVIDENCE_ROW_LABELS:
        row = ttk.Frame(section)
        row.pack(fill="x", pady=4)
        ttk.Label(
            row,
            text=f"{caption}:",
            style="MetricCaption.TLabel",
            width=24,
        ).pack(side="left", anchor="nw")
        value = ttk.Label(row, text="", justify="left", wraplength=820)
        value.pack(side="left", anchor="nw", fill="x", expand=True)
        app.material_identification_evidence_labels[key] = value

    ttk.Separator(section).pack(fill="x", pady=12)
    ttk.Label(
        section,
        text=(
            "Informational status only. Project evidence is not an instruction to "
            "start identification."
        ),
        style="Secondary.TLabel",
        justify="left",
        wraplength=1050,
    ).pack(anchor="nw", fill="x")


def _build_task_definition_page(app, page) -> None:
    section = ttk.LabelFrame(page, text="3. Task Definition", padding=16)
    section.pack(fill="both", expand=True)
    app.material_task_context_label = ttk.Label(
        section, text="", justify="left", wraplength=1000
    )
    app.material_task_context_label.pack(anchor="nw", fill="x", pady=(0, 10))
    ttk.Label(
        section,
        text="Identification task",
        style="Section.TLabel",
    ).pack(anchor="nw")
    app.material_task_workflow_label = ttk.Label(section, text="", justify="left")
    app.material_task_workflow_label.pack(anchor="nw", pady=(4, 14))

    columns = ttk.Frame(section)
    columns.pack(fill="x")
    unknown = ttk.LabelFrame(columns, text="Unknown", padding=12)
    unknown.pack(side="left", anchor="n", fill="both", expand=True, padx=(0, 6))
    frozen = ttk.LabelFrame(columns, text="Frozen", padding=12)
    frozen.pack(side="left", anchor="n", fill="both", expand=True, padx=(6, 0))
    app.material_task_unknowns_label = ttk.Label(
        unknown, text="", justify="left", wraplength=480
    )
    app.material_task_unknowns_label.pack(anchor="w", pady=2)
    app.material_task_frozen_label = ttk.Label(
        frozen, text="", justify="left", wraplength=480
    )
    app.material_task_frozen_label.pack(anchor="w", pady=2)

    interpretation = ttk.LabelFrame(
        section,
        text="Material interpretation",
        padding=12,
    )
    interpretation.pack(fill="x", pady=(14, 0))
    app.material_task_interpretation_label = ttk.Label(
        interpretation,
        text="",
        justify="left",
        wraplength=1000,
    )
    app.material_task_interpretation_label.pack(anchor="nw", fill="x")


def _refresh_model_texts(app) -> None:
    """Apply the bound context's wording to every page that describes the model."""

    text = model_presentation_text(material_identification_presentation(app))
    for attribute, key in (
        ("material_identification_scope_label", "scope"),
        ("material_task_context_label", "context"),
        ("material_task_workflow_label", "workflow"),
        ("material_task_unknowns_label", "unknowns"),
        ("material_task_frozen_label", "frozen"),
        ("material_task_interpretation_label", "task_interpretation"),
        ("material_sensitivity_frozen_label", "frozen_inline"),
        ("material_identification_interpretation_label", "identification_interpretation"),
        ("material_identification_limitations_label", "identification_limitations"),
        ("material_validation_limitations_label", "validation_limitations"),
        ("material_report_task_label", "report_task"),
        ("material_report_limitations_label", "report_limitations"),
    ):
        label = getattr(app, attribute, None)
        if label is not None:
            label.configure(text=text[key])


def _build_read_only_table(parent, columns, headings, widths, *, height):
    frame = ttk.Frame(parent)
    frame.pack(fill="both", expand=True)
    table = ttk.Treeview(
        frame,
        columns=columns,
        show="headings",
        selectmode="browse",
        height=height,
    )
    for key, heading, width in zip(columns, headings, widths):
        table.heading(key, text=heading)
        table.column(
            key,
            width=width,
            minwidth=min(width, 80),
            anchor="w" if key in {"status", "family", "subspace"} else "center",
        )
    scroll = ttk.Scrollbar(frame, orient="vertical", command=table.yview)
    table.configure(yscrollcommand=scroll.set)
    table.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    return table


def _build_data_readiness_page(app, page) -> None:
    ttk.Label(
        page,
        text=(
            "Read-only preflight gate from stored project evidence. The check "
            "reports readiness and does not calculate corrections or resolve conflicts."
        ),
        justify="left",
        wraplength=1100,
    ).pack(anchor="nw", fill="x", pady=(0, 8))

    status_card = ttk.Frame(page, style="MetricCard.TFrame", padding=(12, 9))
    status_card.pack(fill="x", pady=(0, 8))
    ttk.Label(
        status_card,
        text="Data readiness gate",
        style="MetricCaption.TLabel",
    ).pack(anchor="w")
    app.material_readiness_status_label = ttk.Label(
        status_card,
        text="BLOCKED",
        style="MetricValue.TLabel",
    )
    app.material_readiness_status_label.pack(anchor="w", pady=(2, 0))

    app.material_readiness_empty_label = ttk.Label(
        page,
        text="No data-readiness evidence available.",
        justify="left",
    )
    app.material_readiness_empty_label.pack(anchor="nw", fill="x", pady=(0, 8))

    tables = ttk.Frame(page)
    tables.pack(fill="both", expand=True)
    experimental = ttk.LabelFrame(tables, text="Experimental", padding=8)
    experimental.pack(
        side="left", fill="both", expand=True, anchor="n", padx=(0, 5)
    )
    fe = ttk.LabelFrame(tables, text="FE", padding=8)
    fe.pack(side="left", fill="both", expand=True, anchor="n", padx=(5, 0))
    app.material_readiness_experimental_table = _build_read_only_table(
        experimental,
        ("check", "state", "evidence"),
        ("Check", "State", "Existing evidence"),
        (210, 100, 360),
        height=4,
    )
    app.material_readiness_fe_table = _build_read_only_table(
        fe,
        ("check", "state", "evidence"),
        ("Check", "State", "Existing evidence"),
        (220, 100, 350),
        height=5,
    )
    scientific = ttk.LabelFrame(
        page, text="Scientific readiness (SPEC v1.2, read-only)", padding=8
    )
    scientific.pack(fill="both", expand=True, pady=(8, 0))
    app.material_scientific_readiness_status_label = ttk.Label(
        scientific,
        text="NOT AVAILABLE",
        style="MetricValue.TLabel",
    )
    app.material_scientific_readiness_status_label.pack(anchor="w", pady=(0, 4))
    app.material_scientific_readiness_selection_label = ttk.Label(
        scientific, text="", style="Secondary.TLabel", justify="left", wraplength=1040
    )
    app.material_scientific_readiness_selection_label.pack(anchor="w", pady=(0, 4))
    app.material_scientific_readiness_table = _build_read_only_table(
        scientific,
        ("item", "state"),
        ("Item", "Stored backend record"),
        (220, 820),
        height=13,
    )
    ttk.Label(
        page,
        text=(
            "READY permits documented progression; WARNING requires engineering "
            "review; BLOCKED prevents progression. No state changes project data."
        ),
        style="Secondary.TLabel",
        justify="left",
        wraplength=1100,
    ).pack(anchor="nw", fill="x", pady=(10, 0))


def _refresh_data_readiness_page(app) -> None:
    if not hasattr(app, "material_readiness_experimental_table"):
        return
    view = data_readiness_view(app)
    _replace_table_rows(
        app.material_readiness_experimental_table,
        ((label, status, detail) for _, label, status, detail in view["experimental"]),
    )
    _replace_table_rows(
        app.material_readiness_fe_table,
        ((label, status, detail) for _, label, status, detail in view["fe"]),
    )
    app.material_readiness_status_label.configure(text=view["overall_status"])
    app.material_readiness_empty_label.configure(
        text="" if view["available"] else "No data-readiness evidence available."
    )
    if hasattr(app, "material_scientific_readiness_table"):
        scientific = scientific_readiness_view(app)
        _replace_table_rows(app.material_scientific_readiness_table, scientific["rows"])
        app.material_scientific_readiness_status_label.configure(
            text=scientific["status"]
        )
        if hasattr(app, "material_scientific_readiness_selection_label"):
            app.material_scientific_readiness_selection_label.configure(
                text=f"Selection: {scientific['selection']}"
            )


def _build_modal_correspondence_page(app, page) -> None:
    ttk.Label(
        page,
        text=(
            "Read-only evidence from the current comparison result. Existing mode "
            "lists and accepted correspondence records are displayed without new matching."
        ),
        justify="left",
        wraplength=1100,
    ).pack(anchor="nw", fill="x", pady=(0, 6))
    ttk.Label(
        page,
        text=(
            "MAC/subspace are identity validation only. They are not "
            "optimization objectives."
        ),
        style="Secondary.TLabel",
        justify="left",
        wraplength=1100,
    ).pack(anchor="nw", fill="x", pady=(0, 10))

    app.material_correspondence_empty_label = ttk.Label(
        page,
        text="No comparison result available.",
        justify="left",
    )
    app.material_correspondence_empty_label.pack(anchor="nw", fill="x", pady=(0, 8))

    mode_lists = ttk.Frame(page)
    mode_lists.pack(fill="both", expand=True)
    experimental = ttk.LabelFrame(mode_lists, text="Experimental modes", padding=8)
    experimental.pack(
        side="left", fill="both", expand=True, anchor="n", padx=(0, 5)
    )
    fe = ttk.LabelFrame(mode_lists, text="FE modes", padding=8)
    fe.pack(side="left", fill="both", expand=True, anchor="n", padx=(5, 0))
    app.material_experimental_modes_table = _build_read_only_table(
        experimental,
        ("mode", "frequency", "status"),
        ("Mode ID", "Frequency, Hz", "Status"),
        (90, 130, 220),
        height=5,
    )
    app.material_fe_modes_table = _build_read_only_table(
        fe,
        ("mode", "frequency", "status"),
        ("Mode ID", "Frequency, Hz", "Status"),
        (90, 130, 220),
        height=5,
    )

    correspondence = ttk.LabelFrame(
        page, text="Existing correspondence", padding=8
    )
    correspondence.pack(fill="both", expand=True, pady=(10, 0))
    app.material_correspondence_table = _build_read_only_table(
        correspondence,
        ("experimental", "fe", "difference", "mac", "status"),
        (
            "EXP mode",
            "FE mode",
            "Signed frequency difference, %",
            "MAC",
            "Status",
        ),
        (100, 100, 210, 100, 260),
        height=5,
    )

    families = ttk.LabelFrame(page, text="Grouped modes / families", padding=8)
    families.pack(fill="both", expand=True, pady=(10, 0))
    app.material_family_empty_label = ttk.Label(
        families,
        text="No family/subspace evidence available in the current result.",
        justify="left",
    )
    app.material_family_empty_label.pack(anchor="nw", fill="x", pady=(0, 5))
    app.material_family_table = _build_read_only_table(
        families,
        ("family", "identity", "scalar", "subspace"),
        ("Family", "Family identity", "Scalar labels", "Subspace evidence"),
        (260, 130, 140, 260),
        height=3,
    )


def _replace_table_rows(table, rows) -> None:
    table.delete(*table.get_children())
    for row in rows:
        table.insert("", "end", values=row)


def _refresh_modal_correspondence_page(app) -> None:
    if not hasattr(app, "material_correspondence_table"):
        return
    result = getattr(app, "result", None)
    view = modal_correspondence_view(result)
    _replace_table_rows(
        app.material_experimental_modes_table,
        (
            (mode, f"{frequency:.6g}", status)
            for mode, frequency, status in view["experimental_modes"]
        ),
    )
    _replace_table_rows(
        app.material_fe_modes_table,
        (
            (mode, f"{frequency:.6g}", status)
            for mode, frequency, status in view["fe_modes"]
        ),
    )
    _replace_table_rows(
        app.material_correspondence_table,
        (
            (
                exp_mode,
                fe_mode,
                f"{difference:+.3f}",
                "—" if mac is None else f"{mac:.3f}",
                status,
            )
            for exp_mode, fe_mode, difference, mac, status in view[
                "correspondences"
            ]
        ),
    )
    _replace_table_rows(app.material_family_table, view["families"])
    app.material_correspondence_empty_label.configure(
        text=(
            "No comparison result available."
            if result is None
            else (
                "Comparison result loaded; no accepted correspondence records are available."
                if not view["correspondences"]
                else ""
            )
        )
    )
    app.material_family_empty_label.configure(
        text=(
            ""
            if view["families"]
            else "No family/subspace evidence available in the current result."
        )
    )


def _build_sensitivity_page(app, page) -> None:
    ttk.Label(
        page,
        text=(
            "Read-only sensitivity and identifiability evidence. Existing result "
            "objects are displayed without numerical analysis or optimization."
        ),
        justify="left",
        wraplength=1100,
    ).pack(anchor="nw", fill="x", pady=(0, 6))
    ttk.Label(
        page,
        text=(
            "Sensitivity indicates influence. It does not automatically mean "
            "identifiable material truth."
        ),
        style="Secondary.TLabel",
        justify="left",
        wraplength=1100,
    ).pack(anchor="nw", fill="x", pady=(0, 8))
    app.material_sensitivity_empty_label = ttk.Label(
        page,
        text="No sensitivity or identifiability evidence available.",
        justify="left",
    )
    app.material_sensitivity_empty_label.pack(anchor="nw", fill="x", pady=(0, 8))

    matrix = ttk.LabelFrame(page, text="Sensitivity matrix", padding=8)
    matrix.pack(fill="both", expand=True)
    # Parameter columns are added on refresh from what the evidence renders.
    app.material_sensitivity_table = _build_read_only_table(
        matrix,
        ("observable", "type"),
        ("Observable", "Observable type"),
        (220, 160),
        height=6,
    )

    summaries = ttk.Frame(page)
    summaries.pack(fill="both", expand=True, pady=(10, 0))
    observability = ttk.LabelFrame(
        summaries, text="Observability summary", padding=8
    )
    observability.pack(
        side="left", fill="both", expand=True, anchor="n", padx=(0, 5)
    )
    identifiability = ttk.LabelFrame(
        summaries, text="Identifiability summary", padding=8
    )
    identifiability.pack(
        side="left", fill="both", expand=True, anchor="n", padx=(5, 0)
    )
    app.material_observability_table = _build_read_only_table(
        observability,
        ("parameter", "status"),
        ("Parameter", "Status"),
        (140, 180),
        height=4,
    )
    app.material_identifiability_table = _build_read_only_table(
        identifiability,
        ("metric", "value"),
        ("Metric", "Value"),
        (180, 410),
        height=4,
    )

    frozen = ttk.LabelFrame(page, text="Frozen parameters", padding=8)
    frozen.pack(fill="x", pady=(10, 0))
    app.material_sensitivity_frozen_label = ttk.Label(
        frozen, text="", justify="left", wraplength=1050
    )
    app.material_sensitivity_frozen_label.pack(side="left", padx=(0, 28))


def _configure_sensitivity_columns(table, parameter_columns) -> None:
    columns = ("observable", "type", *(key for key, _heading in parameter_columns))
    table.configure(columns=columns)
    for key, heading, width in (
        ("observable", "Observable", 220),
        ("type", "Observable type", 160),
        *((key, heading, 120) for key, heading in parameter_columns),
    ):
        table.heading(key, text=heading)
        table.column(key, width=width, minwidth=min(width, 80), anchor="center")


def _refresh_sensitivity_page(app) -> None:
    if not hasattr(app, "material_sensitivity_table"):
        return
    view = sensitivity_evidence_view(app)
    _configure_sensitivity_columns(
        app.material_sensitivity_table,
        _sensitivity_columns(material_identification_presentation(app), view),
    )
    _replace_table_rows(
        app.material_sensitivity_table,
        (
            (
                observable,
                observable_type,
                *(
                    "—" if value is None else _format_number(value)
                    for value in values
                ),
            )
            for observable, observable_type, *values in view["matrix"]
        ),
    )
    _replace_table_rows(app.material_observability_table, view["observability"])
    _replace_table_rows(app.material_identifiability_table, view["identifiability"])
    app.material_sensitivity_empty_label.configure(
        text=(
            ""
            if view["available"]
            else "No sensitivity or identifiability evidence available."
        )
    )


def _build_identification_page(app, page) -> None:
    ttk.Label(
        page,
        text=(
            "Read-only identification results. Stored U/P cases "
            "are displayed without running an inverse or optimizer."
        ),
        justify="left",
        wraplength=1100,
    ).pack(anchor="nw", fill="x", pady=(0, 8))
    app.material_identification_empty_label = ttk.Label(
        page,
        text="No effective-property identification result available.",
        justify="left",
    )
    app.material_identification_empty_label.pack(anchor="nw", fill="x", pady=(0, 8))

    status_card = ttk.Frame(page, style="MetricCard.TFrame", padding=(12, 9))
    status_card.pack(fill="x", pady=(0, 10))
    ttk.Label(
        status_card,
        text="Stored identification status",
        style="MetricCaption.TLabel",
    ).pack(anchor="w")
    app.material_identification_status_label = ttk.Label(
        status_card,
        text="NO_IDENTIFICATION_RESULT",
        style="MetricValue.TLabel",
        wraplength=1000,
    )
    app.material_identification_status_label.pack(anchor="w", pady=(3, 0))
    ttk.Label(
        status_card,
        text=(
            "The identification status reports the stored result only. A completed "
            "or converged identification is not a validation of material properties; "
            "see 7. Validation."
        ),
        style="Secondary.TLabel",
        justify="left",
        wraplength=1000,
    ).pack(anchor="w", pady=(3, 0))

    models = ttk.Frame(page)
    models.pack(fill="both", expand=True)
    model_u = ttk.LabelFrame(models, text="Model U", padding=8)
    model_u.pack(side="left", fill="both", expand=True, padx=(0, 5))
    model_p = ttk.LabelFrame(models, text="Model P", padding=8)
    model_p.pack(side="left", fill="both", expand=True, padx=(5, 0))
    app.material_model_u_table = _build_read_only_table(
        model_u,
        ("parameter", "value", "unit"),
        ("Parameter", "Value", "Unit"),
        (160, 190, 100),
        height=3,
    )
    app.material_model_p_table = _build_read_only_table(
        model_p,
        ("parameter", "value", "unit"),
        ("Parameter", "Value", "Unit"),
        (160, 190, 100),
        height=3,
    )

    comparison = ttk.LabelFrame(page, text="U/P comparison", padding=8)
    comparison.pack(fill="both", expand=True, pady=(10, 0))
    app.material_identification_comparison_table = _build_read_only_table(
        comparison,
        ("parameter", "difference", "weighting"),
        ("Parameter", "Stored U/P difference, %", "Weighting sensitivity status"),
        (150, 230, 300),
        height=3,
    )

    interpretation = ttk.LabelFrame(
        page, text="Scientific interpretation", padding=8
    )
    interpretation.pack(fill="x", pady=(10, 0))
    app.material_identification_interpretation_label = ttk.Label(
        interpretation,
        text="",
        justify="left",
        wraplength=1050,
    )
    app.material_identification_interpretation_label.pack(anchor="nw", fill="x")

    limitations = ttk.LabelFrame(page, text="Limitations", padding=8)
    limitations.pack(fill="x", pady=(10, 0))
    app.material_identification_limitations_label = ttk.Label(
        limitations, text="", justify="left", wraplength=1050
    )
    app.material_identification_limitations_label.pack(anchor="nw", fill="x")


def _refresh_identification_page(app) -> None:
    if not hasattr(app, "material_model_u_table"):
        return
    view = identification_result_view(app)

    def displayed_properties(rows):
        return (
            (
                parameter,
                "—" if value is None else _format_number(value),
                unit if value is not None else "—",
            )
            for parameter, value, unit in rows
        )

    _replace_table_rows(
        app.material_model_u_table, displayed_properties(view["model_u"])
    )
    _replace_table_rows(
        app.material_model_p_table, displayed_properties(view["model_p"])
    )
    _replace_table_rows(
        app.material_identification_comparison_table,
        (
            (
                parameter,
                "—" if difference is None else _format_number(difference),
                weighting,
            )
            for parameter, difference, weighting in view["comparison"]
        ),
    )
    app.material_identification_status_label.configure(text=view["status"])
    app.material_identification_empty_label.configure(
        text=(
            ""
            if view["available"]
            else "No effective-property identification result available."
        )
    )


def _build_validation_page(app, page) -> None:
    ttk.Label(
        page,
        text=(
            "Read-only validation evidence. Stored primary and holdout records are "
            "displayed without running Abaqus, inverse identification, or calculations."
        ),
        justify="left",
        wraplength=1100,
    ).pack(anchor="nw", fill="x", pady=(0, 8))
    app.material_validation_empty_label = ttk.Label(
        page,
        text="No validation evidence available.",
        justify="left",
    )
    app.material_validation_empty_label.pack(anchor="nw", fill="x", pady=(0, 8))

    status_card = ttk.Frame(page, style="MetricCard.TFrame", padding=(12, 9))
    status_card.pack(fill="x", pady=(0, 10))
    ttk.Label(
        status_card,
        text="Overall validation status",
        style="MetricCaption.TLabel",
    ).pack(anchor="w")
    app.material_validation_status_label = ttk.Label(
        status_card,
        text="NO_VALIDATION_EVIDENCE",
        style="MetricValue.TLabel",
        wraplength=1000,
    )
    app.material_validation_status_label.pack(anchor="w", pady=(3, 0))

    columns = ("model", "observable", "experimental", "fe", "residual", "status")
    headings = (
        "Model",
        "Observable",
        "Experimental frequency",
        "FE frequency",
        "Stored residual / error",
        "Status",
    )
    widths = (85, 190, 170, 140, 175, 300)
    primary = ttk.LabelFrame(page, text="Primary observable validation", padding=8)
    primary.pack(fill="both", expand=True)
    app.material_primary_validation_table = _build_read_only_table(
        primary, columns, headings, widths, height=5
    )

    holdout = ttk.LabelFrame(page, text="Holdout validation", padding=8)
    holdout.pack(fill="both", expand=True, pady=(10, 0))
    app.material_holdout_validation_badge = ttk.Label(
        holdout,
        text="NOT USED FOR IDENTIFICATION",
        style="MetricCaption.TLabel",
    )
    app.material_holdout_validation_badge.pack(anchor="w", pady=(0, 5))
    app.material_holdout_validation_table = _build_read_only_table(
        holdout, columns, headings, widths, height=5
    )

    limitations = ttk.LabelFrame(page, text="Model limitations", padding=8)
    limitations.pack(fill="x", pady=(10, 0))
    app.material_validation_limitations_label = ttk.Label(
        limitations, text="", justify="left", wraplength=1050
    )
    app.material_validation_limitations_label.pack(anchor="nw", fill="x")


def _refresh_validation_page(app) -> None:
    if not hasattr(app, "material_primary_validation_table"):
        return
    view = validation_evidence_view(app)

    def displayed_rows(rows):
        return (
            (
                model,
                observable,
                "—" if experimental is None else _format_number(experimental),
                "—" if fe_value is None else _format_number(fe_value),
                "—" if residual is None else _format_number(residual),
                status,
            )
            for model, observable, experimental, fe_value, residual, status in rows
        )

    _replace_table_rows(
        app.material_primary_validation_table, displayed_rows(view["primary"])
    )
    _replace_table_rows(
        app.material_holdout_validation_table, displayed_rows(view["holdout"])
    )
    app.material_validation_status_label.configure(text=view["status"])
    app.material_validation_empty_label.configure(
        text="" if view["available"] else "No validation evidence available."
    )


def _build_report_page(app, page) -> None:
    ttk.Label(
        page,
        text=(
            "Final report preview from existing stored identification and validation "
            "evidence. Export does not run or recalculate scientific results."
        ),
        justify="left",
        wraplength=1100,
    ).pack(anchor="nw", fill="x", pady=(0, 8))
    app.material_report_empty_label = ttk.Label(
        page,
        text="No stored identification or validation evidence available for report.",
        justify="left",
    )
    app.material_report_empty_label.pack(anchor="nw", fill="x", pady=(0, 8))

    overview = ttk.Frame(page)
    overview.pack(fill="both", expand=True)
    project = ttk.LabelFrame(overview, text="Project summary", padding=8)
    project.pack(side="left", fill="both", expand=True, padx=(0, 5))
    task = ttk.LabelFrame(overview, text="Task definition", padding=8)
    task.pack(side="left", fill="both", expand=True, padx=(5, 0))
    app.material_report_project_table = _build_read_only_table(
        project,
        ("item", "value"),
        ("Item", "Stored value"),
        (180, 410),
        height=4,
    )
    app.material_report_task_label = ttk.Label(
        task,
        text="",
        justify="left",
        wraplength=480,
    )
    app.material_report_task_label.pack(anchor="nw", fill="x")

    identification = ttk.LabelFrame(
        page, text="Identification result", padding=8
    )
    identification.pack(fill="both", expand=True, pady=(10, 0))
    app.material_report_identification_table = _build_read_only_table(
        identification,
        ("parameter", "u", "p", "difference", "weighting"),
        ("Parameter", "Model U", "Model P", "U/P difference, %", "Weighting status"),
        (120, 170, 170, 180, 230),
        height=3,
    )

    validation = ttk.LabelFrame(page, text="Validation evidence", padding=8)
    validation.pack(fill="both", expand=True, pady=(10, 0))
    app.material_report_validation_status_label = ttk.Label(
        validation,
        text="Validation status: NO_VALIDATION_EVIDENCE",
        style="MetricCaption.TLabel",
    )
    app.material_report_validation_status_label.pack(anchor="w", pady=(0, 5))
    app.material_report_validation_table = _build_read_only_table(
        validation,
        ("scope", "model", "observable", "experimental", "fe", "error", "status"),
        ("Scope", "Model", "Observable", "EXP", "FE", "Error", "Status"),
        (190, 75, 180, 110, 110, 110, 240),
        height=6,
    )

    limitations = ttk.LabelFrame(page, text="Limitations", padding=8)
    limitations.pack(fill="x", pady=(10, 0))
    app.material_report_limitations_label = ttk.Label(
        limitations,
        text="",
        justify="left",
        wraplength=1050,
    )
    app.material_report_limitations_label.pack(anchor="nw", fill="x")

    exports = ttk.LabelFrame(page, text="Export options", padding=8)
    exports.pack(fill="x", pady=(10, 0))
    app.material_report_pdf_button = ttk.Button(
        exports,
        text="Export PDF report…",
        command=app._export_material_report_pdf,
        state="disabled",
    )
    app.material_report_json_button = ttk.Button(
        exports,
        text="Export JSON evidence…",
        command=app._export_material_report_json,
        state="disabled",
    )
    app.material_report_csv_button = ttk.Button(
        exports,
        text="Export CSV tables…",
        command=app._export_material_report_csv,
        state="disabled",
    )
    app.material_report_pdf_button.pack(side="left")
    app.material_report_json_button.pack(side="left", padx=8)
    app.material_report_csv_button.pack(side="left")


def _refresh_report_page(app) -> None:
    if not hasattr(app, "material_report_project_table"):
        return
    snapshot = report_evidence_snapshot(app)
    project = snapshot["project_summary"]
    _replace_table_rows(
        app.material_report_project_table,
        (
            ("Specimen / project", project["specimen_or_project"]),
            ("FE model", project["fe_model"]),
            ("Experimental dataset", project["experimental_dataset"]),
            ("Provenance status", project["provenance_status"]),
        ),
    )
    identification = snapshot["identification_result"]
    comparison = {
        item["parameter"]: item for item in identification["comparison"]
    }
    _replace_table_rows(
        app.material_report_identification_table,
        (
            (
                parameter,
                _report_property_text(identification["model_u"].get(parameter, {})),
                _report_property_text(identification["model_p"].get(parameter, {})),
                _format_report_value(
                    comparison.get(parameter, {}).get(
                        "stored_u_p_difference_percent"
                    )
                ),
                comparison.get(parameter, {}).get(
                    "weighting_sensitivity_status", "Unavailable"
                ),
            )
            # Parameter order is the rendered order (the model's, for production).
            for parameter in identification["model_u"]
        ),
    )
    validation = snapshot["validation"]
    validation_rows = []
    for scope, key in (("PRIMARY", "primary_observables"), ("NOT USED FOR IDENTIFICATION", "holdouts")):
        for item in validation[key]:
            validation_rows.append(
                (
                    scope,
                    item["model"],
                    item["observable"],
                    _format_report_value(item["experimental_frequency"]),
                    _format_report_value(item["fe_frequency"]),
                    _format_report_value(item["stored_residual_or_error"]),
                    item["status"],
                )
            )
    _replace_table_rows(app.material_report_validation_table, validation_rows)
    app.material_report_validation_status_label.configure(
        text=f"Validation status: {validation['status']}"
    )
    ready = bool(snapshot["report_available"])
    app.material_report_empty_label.configure(
        text=(
            ""
            if ready
            else "No stored identification or validation evidence available for report."
        )
    )
    for button in (
        app.material_report_pdf_button,
        app.material_report_json_button,
        app.material_report_csv_button,
    ):
        button.configure(state="normal" if ready else "disabled")


def _format_report_value(value) -> str:
    return "—" if value is None else _format_number(value)


def _report_property_text(item: Mapping) -> str:
    value = item.get("value")
    if value is None:
        return "—"
    unit = str(item.get("unit") or "").strip()
    return f"{_format_number(value)} {unit}".strip()


def _build_unavailable_page(page, step_label: str) -> None:
    section = ttk.LabelFrame(page, text=step_label, padding=16)
    section.pack(fill="both", expand=True)
    ttk.Label(
        section,
        text=_STEP_DESCRIPTIONS[step_label],
        justify="left",
        wraplength=1050,
    ).pack(anchor="nw", fill="x")
    ttk.Separator(section).pack(fill="x", pady=14)
    ttk.Label(
        section,
        text="Not available in GUI-6 — informational pages only.",
        justify="left",
    ).pack(anchor="nw")


def install_material_identification_ui(app_module) -> None:
    """Add the GUI-only material-identification workspace to the main notebook."""

    global _INSTALLED
    if _INSTALLED:
        return

    application_class = app_module.ModalComparatorApp
    original_init = application_class.__init__

    def material_identification_init(self, root) -> None:
        original_init(self, root)
        self.material_identification_evidence_view_model = EMPTY_EVIDENCE_VIEW_MODEL
        self.material_identification_session = None
        self._install_material_identification_tab()

    def bind_material_identification_evidence(
        self, bundle: SP13EvidenceBundle
    ) -> None:
        """Bind a frozen historical (UNBOUND) bundle; no session or model applies."""

        view_model = MaterialIdentificationEvidenceViewModel.from_bundle(bundle)
        self.material_identification_session = None
        self.material_identification_evidence_view_model = view_model
        self._refresh_material_identification_pages()

    def bind_material_identification_session(
        self,
        session: MaterialIdentificationSession,
        *,
        sensitivity=None,
        identifiability=None,
        identification=None,
        validation=None,
    ) -> None:
        """Bind a production session and its BOUND evidence (possibly none yet).

        The session's own model definition drives every parameter row; evidence
        bound to another model, definition, registration or experiment is
        refused before anything is bound.
        """

        view_model = session_evidence_view_model(
            session,
            sensitivity=sensitivity,
            identifiability=identifiability,
            identification=identification,
            validation=validation,
        )
        self.material_identification_session = session
        self.material_identification_evidence_view_model = view_model
        self._refresh_material_identification_pages()

    def refresh_material_identification_pages(self, _event=None) -> None:
        labels = getattr(self, "material_identification_evidence_labels", {})
        for key, value in project_evidence_status(self).items():
            label = labels.get(key)
            if label is not None:
                label.configure(text=value)
        _refresh_model_texts(self)
        _refresh_auto_id_setup_page(self)
        _refresh_data_readiness_page(self)
        _refresh_modal_correspondence_page(self)
        _refresh_sensitivity_page(self)
        _refresh_identification_page(self)
        _refresh_validation_page(self)
        _refresh_report_page(self)

    def export_material_report(self, kind: str) -> None:
        snapshot = report_evidence_snapshot(self)
        if not snapshot["report_available"]:
            messagebox.showwarning(
                "No report evidence",
                "Load stored identification or validation evidence before exporting.",
            )
            return
        options = {
            "pdf": (
                "Export PDF report",
                ".pdf",
                "effective_material_identification_report.pdf",
                [("PDF report", "*.pdf")],
                export_material_identification_pdf,
            ),
            "json": (
                "Export JSON evidence",
                ".json",
                "effective_material_identification_evidence.json",
                [("JSON evidence", "*.json")],
                export_material_identification_json,
            ),
            "csv": (
                "Export CSV tables",
                ".csv",
                "effective_material_identification_tables.csv",
                [("CSV tables", "*.csv")],
                export_material_identification_csv,
            ),
        }
        title, extension, initialfile, filetypes, exporter = options[kind]
        destination = filedialog.asksaveasfilename(
            title=title,
            defaultextension=extension,
            initialfile=initialfile,
            filetypes=filetypes,
        )
        if not destination:
            return
        try:
            exporter(snapshot, Path(destination))
            messagebox.showinfo("Report saved", destination)
        except Exception as error:
            messagebox.showerror("Export failed", str(error))

    def export_material_report_pdf(self) -> None:
        self._export_material_report("pdf")

    def export_material_report_json(self) -> None:
        self._export_material_report("json")

    def export_material_report_csv(self) -> None:
        self._export_material_report("csv")

    def install_material_identification_tab(self) -> None:
        self.material_identification_tab = ttk.Frame(self.tabs, padding=10)
        details_index = self.tabs.index(self.details_tab)
        self.tabs.insert(
            details_index,
            self.material_identification_tab,
            text="9. Effective Material Identification",
        )
        self.tabs.tab(self.details_tab, text="10. Details")

        heading = ttk.Frame(self.material_identification_tab)
        heading.pack(fill="x", pady=(0, 10))
        ttk.Label(
            heading,
            text="Effective Material Identification",
            style="Title.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            heading,
            text=(
                "GUI-6 informational workflow. No identification solver is connected "
                "and no Abaqus analysis can be started from this page."
            ),
            justify="left",
            wraplength=1200,
        ).pack(anchor="w", pady=(4, 0))
        self.material_identification_scope_label = ttk.Label(
            heading,
            text="",
            justify="left",
            wraplength=1200,
        )
        self.material_identification_scope_label.pack(anchor="w", pady=(4, 0))

        self.material_identification_notebook = ttk.Notebook(
            self.material_identification_tab
        )
        self.material_identification_notebook.pack(fill="both", expand=True)
        self.material_identification_pages = {}

        for step_label in MATERIAL_IDENTIFICATION_STEP_LABELS:
            page = ttk.Frame(self.material_identification_notebook, padding=16)
            self.material_identification_notebook.add(page, text=step_label)
            self.material_identification_pages[step_label] = page
            if step_label == "0. Auto-ID Setup":
                _build_auto_id_setup_page(self, page)
            elif step_label == "1. Project Evidence":
                _build_project_evidence_page(self, page)
            elif step_label == "2. Data Readiness Check":
                _build_data_readiness_page(self, page)
            elif step_label == "3. Task Definition":
                _build_task_definition_page(self, page)
            elif step_label == "4. Modal Correspondence":
                _build_modal_correspondence_page(self, page)
            elif step_label == "5. Sensitivity":
                _build_sensitivity_page(self, page)
            elif step_label == "6. Identification":
                _build_identification_page(self, page)
            elif step_label == "7. Validation":
                _build_validation_page(self, page)
            elif step_label == "8. Report":
                _build_report_page(self, page)
            else:
                _build_unavailable_page(page, step_label)

        self._refresh_material_identification_pages()
        self.material_identification_notebook.bind(
            "<<NotebookTabChanged>>",
            self._refresh_material_identification_pages,
            add="+",
        )
        self.tabs.bind(
            "<<NotebookTabChanged>>",
            self._refresh_material_identification_pages,
            add="+",
        )

        def refresh_material_identification_pages_from_trace(
            _variable_name, _index, _operation
        ) -> None:
            self._refresh_material_identification_pages()

        for variable_name in (
            "abaqus_path",
            "experimental_path",
            "abaqus_installation_label",
        ):
            variable = getattr(self, variable_name, None)
            if variable is not None and hasattr(variable, "trace_add"):
                variable.trace_add(
                    "write", refresh_material_identification_pages_from_trace
                )

    application_class.__init__ = material_identification_init
    application_class._install_material_identification_tab = (
        install_material_identification_tab
    )
    application_class._refresh_material_identification_pages = (
        refresh_material_identification_pages
    )
    application_class.bind_material_identification_evidence = (
        bind_material_identification_evidence
    )
    application_class.bind_material_identification_session = (
        bind_material_identification_session
    )
    application_class._export_material_report = export_material_report
    application_class._export_material_report_pdf = export_material_report_pdf
    application_class._export_material_report_json = export_material_report_json
    application_class._export_material_report_csv = export_material_report_csv
    _INSTALLED = True


__all__ = [
    "install_material_identification_ui",
    "export_material_identification_csv",
    "export_material_identification_json",
    "export_material_identification_pdf",
    "data_readiness_view",
    "identification_result_view",
    "material_identification_presentation",
    "MaterialIdentificationPresentation",
    "modal_correspondence_view",
    "model_presentation_text",
    "project_evidence_status",
    "report_evidence_snapshot",
    "sensitivity_evidence_view",
    "session_evidence_view_model",
    "validation_evidence_view",
]
