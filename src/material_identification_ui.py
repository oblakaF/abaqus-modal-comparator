"""Informational UI for the Effective Material Identification workflow.

This module intentionally contains no scientific execution path. It presents
current project state and the supported task definition without starting
Abaqus or connecting an identification backend.
"""

from __future__ import annotations

from collections.abc import Mapping
import csv
import json
from pathlib import Path
import textwrap
from tkinter import filedialog, messagebox, ttk

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

_EFFECTIVE_PARAMETER_IDS = ("Ex", "Ey", "Gxy")


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


def _existing_evidence(app, kind: str):
    attribute_names = {
        "sensitivity": (
            "material_sensitivity_result",
            "sensitivity_result",
            "sensitivity",
        ),
        "identifiability": (
            "material_identifiability_result",
            "identifiability_result",
            "identifiability",
        ),
    }[kind]
    containers = (
        app,
        getattr(app, "material_identification_result", None),
        getattr(app, "result", None),
    )
    for container in containers:
        if container is None:
            continue
        for name in attribute_names:
            value = _record_value(container, name, default=None)
            if value is not None:
                return value
        metadata = _record_value(container, "metadata", default={}) or {}
        if isinstance(metadata, Mapping):
            for name in attribute_names:
                if metadata.get(name) is not None:
                    return metadata[name]
    return None


def _sequence(value: object) -> tuple:
    if value is None:
        return ()
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, str):
        return (value,)
    try:
        return tuple(value)
    except TypeError:
        return (value,)


def _effective_parameter_indexes(parameter_ids) -> dict[str, int]:
    lookup = {
        str(identifier).strip().lower(): index
        for index, identifier in enumerate(_sequence(parameter_ids))
    }
    return {
        parameter: lookup[parameter.lower()]
        for parameter in _EFFECTIVE_PARAMETER_IDS
        if parameter.lower() in lookup
    }


def _observable_kind(sensitivity, observation_id: str, index: int) -> str:
    kinds = _record_value(
        sensitivity,
        "observable_types",
        "observation_types",
        default=None,
    )
    if isinstance(kinds, Mapping):
        value = kinds.get(observation_id, "")
    else:
        values = _sequence(kinds)
        value = values[index] if index < len(values) else ""
    normalized = str(value or "").strip().lower()
    if normalized in {"family", "cluster", "family_observable"}:
        return "Family observable"
    family_ids = {
        str(value)
        for value in _sequence(
            _record_value(sensitivity, "family_observation_ids", default=())
        )
    }
    return "Family observable" if observation_id in family_ids else "Scalar mode"


def _observability_label(value: object) -> str:
    normalized = _status_value(value).upper().replace(" ", "_")
    if normalized in {"OBSERVABLE", "STRONG", "PASS"}:
        return "strong"
    if normalized in {
        "PARTIALLY_OBSERVABLE",
        "PARTIAL",
        "WEAK",
        "REVIEW",
    }:
        return "weak"
    return "unavailable"


def _weakest_direction_text(identifiability) -> str:
    explicit = _record_value(identifiability, "weakest_direction", default=None)
    if explicit is not None:
        return str(explicit)
    directions = _sequence(
        _record_value(identifiability, "deficient_directions", default=())
    )
    if not directions:
        return "Unavailable"
    direction = directions[-1]
    loadings = _record_value(direction, "parameter_loadings", default={}) or {}
    if isinstance(loadings, Mapping) and loadings:
        return ", ".join(
            f"{parameter} {float(value):+.3f}"
            for parameter, value in loadings.items()
        )
    dominant = _record_value(direction, "dominant_parameter", default=None)
    return str(dominant) if dominant else "Unavailable"


def sensitivity_evidence_view(app) -> dict[str, object]:
    """Present stored sensitivity evidence without deriving sensitivities or SVDs."""

    sensitivity = _existing_evidence(app, "sensitivity")
    identifiability = _existing_evidence(app, "identifiability")
    matrix_rows = []
    if sensitivity is not None:
        parameter_indexes = _effective_parameter_indexes(
            _record_value(sensitivity, "parameter_ids", default=())
        )
        observation_ids = _sequence(
            _record_value(
                sensitivity,
                "observation_ids",
                "observable_ids",
                default=(),
            )
        )
        matrix = _sequence(
            _record_value(
                sensitivity,
                "scaled_sensitivity",
                "sensitivity_matrix",
                default=(),
            )
        )
        for index, observation_id in enumerate(observation_ids):
            values = _sequence(matrix[index]) if index < len(matrix) else ()
            parameter_values = tuple(
                (
                    float(values[parameter_indexes[parameter]])
                    if parameter in parameter_indexes
                    and parameter_indexes[parameter] < len(values)
                    else None
                )
                for parameter in _EFFECTIVE_PARAMETER_IDS
            )
            matrix_rows.append(
                (
                    str(observation_id),
                    _observable_kind(sensitivity, str(observation_id), index),
                    *parameter_values,
                )
            )

    observability_source = (
        _record_value(identifiability, "parameter_observability", default={}) or {}
        if identifiability is not None
        else {}
    )
    observability_lookup = (
        {
            str(parameter).strip().lower(): status
            for parameter, status in observability_source.items()
        }
        if isinstance(observability_source, Mapping)
        else {}
    )
    observability = tuple(
        (
            parameter,
            _observability_label(observability_lookup.get(parameter.lower())),
        )
        for parameter in _EFFECTIVE_PARAMETER_IDS
    )

    if identifiability is None:
        summary = (
            ("Rank", "Unavailable"),
            ("Condition number", "Unavailable"),
            ("Singular values", "Unavailable"),
            ("Weakest direction", "Unavailable"),
        )
    else:
        singular_values = _sequence(
            _record_value(identifiability, "singular_values", default=())
        )
        summary = (
            ("Rank", str(_record_value(identifiability, "rank", default="Unavailable"))),
            (
                "Condition number",
                _format_number(
                    _record_value(
                        identifiability, "condition_number", default=None
                    )
                ),
            ),
            (
                "Singular values",
                ", ".join(_format_number(value) for value in singular_values)
                or "Unavailable",
            ),
            ("Weakest direction", _weakest_direction_text(identifiability)),
        )
    return {
        "available": sensitivity is not None or identifiability is not None,
        "matrix": tuple(matrix_rows),
        "observability": observability,
        "identifiability": summary,
    }


def _format_number(value: object) -> str:
    if value is None:
        return "Unavailable"
    try:
        return f"{float(value):.6g}"
    except (TypeError, ValueError):
        return str(value)


def _mapping_value(mapping, key: str, default=None):
    if not isinstance(mapping, Mapping):
        return default
    if key in mapping:
        return mapping[key]
    wanted = key.strip().lower()
    for current_key, value in mapping.items():
        if str(current_key).strip().lower() == wanted:
            return value
    return default


def _existing_identification_record(app):
    attribute_names = (
        "effective_property_identification_result",
        "identified_properties",
        "material_identification_record",
        "material_identification_result",
        "identification_record",
    )
    for name in attribute_names:
        value = getattr(app, name, None)
        if value is not None:
            return value
    result = getattr(app, "result", None)
    metadata = _record_value(result, "metadata", default={}) or {}
    if isinstance(metadata, Mapping):
        for name in attribute_names:
            if metadata.get(name) is not None:
                return metadata[name]
    return None


def _model_record(record, model_name: str):
    models = _record_value(record, "models", default={}) or {}
    if isinstance(models, Mapping):
        model = _mapping_value(models, model_name)
        if model is not None:
            return model
    for name in (
        f"model_{model_name.lower()}",
        f"model_{model_name}",
        f"case_{model_name.lower()}",
        f"case_{model_name}",
    ):
        model = _record_value(record, name, default=None)
        if model is not None:
            return model
    return None


def _property_mapping(model):
    if model is None:
        return {}, "MPa"
    for name, unit in (
        ("properties_MPa", "MPa"),
        ("effective_homogeneous_face_sheet_properties_MPa", "MPa"),
        ("properties", ""),
        ("effective_properties", ""),
        ("fitted_parameters", ""),
    ):
        properties = _record_value(model, name, default=None)
        if isinstance(properties, Mapping):
            declared_unit = _record_value(model, "unit", "units", default=unit)
            if isinstance(declared_unit, Mapping):
                declared_unit = unit
            return properties, str(declared_unit or unit)
    if isinstance(model, Mapping) and any(
        _mapping_value(model, parameter) is not None
        for parameter in _EFFECTIVE_PARAMETER_IDS
    ):
        return model, str(_mapping_value(model, "unit", ""))
    return {}, "MPa"


def _stored_parameter_differences(record) -> Mapping:
    stability = _record_value(record, "stability", default={}) or {}
    if isinstance(stability, Mapping):
        for key in (
            "U_P_symmetric_difference_percent",
            "u_p_symmetric_difference_percent",
            "parameter_differences",
            "differences",
        ):
            values = _mapping_value(stability, key)
            if isinstance(values, Mapping):
                return values
    for key in ("parameter_differences", "differences"):
        values = _record_value(record, key, default=None)
        if isinstance(values, Mapping):
            return values
    return {}


def _weighting_status(record, parameter: str) -> str:
    stability = _record_value(record, "stability", default={}) or {}
    value = _mapping_value(stability, parameter)
    if value is None:
        statuses = _record_value(record, "weighting_sensitivity", default={}) or {}
        value = _mapping_value(statuses, parameter)
    normalized = _status_value(value).upper().replace("-", "_").replace(" ", "_")
    if normalized == "WEIGHTING_SENSITIVE":
        return "weighting-sensitive"
    if normalized in {"RELATIVELY_STABLE", "STABLE"}:
        return "relatively stable"
    return _status_value(value) or "Unavailable"


def identification_result_view(app) -> dict[str, object]:
    """Adapt a stored U/P effective-property record without numerical work."""

    record = _existing_identification_record(app)
    model_u = _model_record(record, "U") if record is not None else None
    model_p = _model_record(record, "P") if record is not None else None
    properties_u, unit_u = _property_mapping(model_u)
    properties_p, unit_p = _property_mapping(model_p)
    differences = _stored_parameter_differences(record) if record is not None else {}

    def property_rows(properties, unit):
        return tuple(
            (
                parameter,
                _mapping_value(properties, parameter),
                unit or "Not stated",
            )
            for parameter in _EFFECTIVE_PARAMETER_IDS
        )

    status = "NO_IDENTIFICATION_RESULT"
    if record is not None:
        status = _status_value(
            _record_value(
                record,
                "validation_state",
                "recommendation",
                "status",
                "record_status",
                default=status,
            )
        ) or status
    available = any(
        _mapping_value(properties, parameter) is not None
        for properties in (properties_u, properties_p)
        for parameter in _EFFECTIVE_PARAMETER_IDS
    )
    comparison = tuple(
        (
            parameter,
            _mapping_value(differences, parameter),
            _weighting_status(record, parameter) if record is not None else "Unavailable",
        )
        for parameter in _EFFECTIVE_PARAMETER_IDS
    )
    return {
        "available": available,
        "model_u": property_rows(properties_u, unit_u),
        "model_p": property_rows(properties_p, unit_p),
        "comparison": comparison,
        "status": status,
    }


def _existing_validation_record(app):
    attribute_names = (
        "effective_property_validation",
        "material_validation_result",
        "validation_evidence",
        "validation_result",
        "validation_record",
    )
    for name in attribute_names:
        value = getattr(app, name, None)
        if value is not None:
            return value
    result = getattr(app, "result", None)
    metadata = _record_value(result, "metadata", default={}) or {}
    if isinstance(metadata, Mapping):
        for name in attribute_names:
            if metadata.get(name) is not None:
                return metadata[name]
    return None


def _validation_rows(record, category: str) -> tuple:
    if record is None:
        return ()
    direct_names = {
        "primary": ("primary_observables", "primary_validation", "primary"),
        "holdout": ("holdout_validation", "holdouts", "holdout"),
    }[category]
    for name in direct_names:
        rows = _record_value(record, name, default=None)
        if rows is not None:
            return _sequence(rows)
    rows = _record_value(
        record,
        "validation_rows",
        "rows",
        "observations",
        default=(),
    )
    selected = []
    for row in _sequence(rows):
        row_category = _status_value(
            _record_value(row, "category", "role", default="")
        ).upper()
        if category == "primary" and row_category == "PRIMARY":
            selected.append(row)
        elif category == "holdout" and row_category in {
            "HOLDOUT",
            "HOLDOUT_DIAGNOSTIC",
            "VALIDATION",
        }:
            selected.append(row)
    return tuple(selected)


def _validation_row(record) -> tuple:
    model = _record_value(record, "model", "case", default="—")
    observable = _record_value(
        record,
        "observable",
        "name",
        "label",
        "observable_id",
        default="Unlabelled observable",
    )
    experimental = _record_value(
        record,
        "experimental_frequency_hz",
        "experimental_frequency",
        "experimental_value",
        default=None,
    )
    fe_value = _record_value(
        record,
        "fe_frequency_hz",
        "FE_frequency_hz",
        "fe_frequency",
        "FE_value",
        "calculated_frequency_hz",
        default=None,
    )
    residual = _record_value(
        record,
        "equivalent_error_percent",
        "frequency_error_percent",
        "residual",
        "error",
        "FE_minus_EXP_residual",
        default=None,
    )
    status = _record_value(
        record,
        "validation_status",
        "status",
        "identity_status",
        "result",
        "assessment",
        "comparison_to_baseline",
        default="Not stated",
    )
    return model, observable, experimental, fe_value, residual, status


def validation_evidence_view(app) -> dict[str, object]:
    """Adapt stored validation rows without calculating validation metrics."""

    record = _existing_validation_record(app)
    identification_record = _existing_identification_record(app)
    status_source = record if record is not None else identification_record
    status = "NO_VALIDATION_EVIDENCE"
    if status_source is not None:
        status = _status_value(
            _record_value(
                status_source,
                "overall_status",
                "validation_status",
                "recommendation",
                "status",
                default=status,
            )
        ) or status
    return {
        "available": record is not None,
        "status": status,
        "primary": tuple(
            _validation_row(row) for row in _validation_rows(record, "primary")
        ),
        "holdout": tuple(
            _validation_row(row) for row in _validation_rows(record, "holdout")
        ),
    }


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
    identification = identification_result_view(app)
    validation = validation_evidence_view(app)

    def properties(rows):
        return {
            parameter: {"value": value, "unit": unit}
            for parameter, value, unit in rows
        }

    snapshot = {
        "schema_version": "effective-material-identification-gui-6",
        "project_summary": {
            "specimen_or_project": project["project"],
            "fe_model": project["fe_model"],
            "experimental_dataset": project["experimental_data"],
            "provenance_status": project["provenance"],
        },
        "task_definition": {
            "workflow": "Effective homogeneous face-sheet property identification",
            "unknown_parameters": list(_EFFECTIVE_PARAMETER_IDS),
            "frozen": ["core", "density", "adhesive", "geometry"],
        },
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
        "limitations": [
            "Effective properties only",
            "Not ply or fibre constants",
            "Unknown laminate architecture",
            "Frozen core and interface assumptions",
        ],
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
        "Effective homogeneous face-sheet property identification",
        "Unknown: Ex, Ey, Gxy",
        "Frozen: core, density, adhesive, geometry",
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
    return f"Selected — {Path(text).name}"


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


def _build_task_definition_page(page) -> None:
    section = ttk.LabelFrame(page, text="2. Task Definition", padding=16)
    section.pack(fill="both", expand=True)
    ttk.Label(
        section,
        text="Supported first workflow",
        style="Section.TLabel",
    ).pack(anchor="nw")
    ttk.Label(
        section,
        text="Effective homogeneous face-sheet property identification",
        justify="left",
    ).pack(anchor="nw", pady=(4, 14))

    columns = ttk.Frame(section)
    columns.pack(fill="x")
    unknown = ttk.LabelFrame(columns, text="Unknown", padding=12)
    unknown.pack(side="left", anchor="n", fill="both", expand=True, padx=(0, 6))
    frozen = ttk.LabelFrame(columns, text="Frozen", padding=12)
    frozen.pack(side="left", anchor="n", fill="both", expand=True, padx=(6, 0))
    for parameter in ("Ex", "Ey", "Gxy"):
        ttk.Label(unknown, text=f"• {parameter}").pack(anchor="w", pady=2)
    for group in ("Core", "Density", "Adhesive", "Geometry"):
        ttk.Label(frozen, text=f"• {group}").pack(anchor="w", pady=2)

    interpretation = ttk.LabelFrame(
        section,
        text="Material interpretation",
        padding=12,
    )
    interpretation.pack(fill="x", pady=(14, 0))
    ttk.Label(
        interpretation,
        text=(
            "Effective homogeneous face-sheet properties\n\n"
            "Results are not true fibre properties, ply properties, or unique "
            "laminate constants."
        ),
        justify="left",
        wraplength=1000,
    ).pack(anchor="nw", fill="x")


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
    app.material_sensitivity_table = _build_read_only_table(
        matrix,
        ("observable", "type", "ex", "ey", "gxy"),
        ("Observable", "Observable type", "Ex", "Ey", "Gxy"),
        (220, 160, 120, 120, 120),
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
    for label in (
        "Core frozen",
        "Density frozen",
        "Adhesive frozen",
        "Geometry frozen",
    ):
        ttk.Label(frozen, text=label).pack(side="left", padx=(0, 28))


def _refresh_sensitivity_page(app) -> None:
    if not hasattr(app, "material_sensitivity_table"):
        return
    view = sensitivity_evidence_view(app)
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
            "Read-only effective-property identification results. Stored U/P cases "
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
        text="Stored validation state",
        style="MetricCaption.TLabel",
    ).pack(anchor="w")
    app.material_identification_status_label = ttk.Label(
        status_card,
        text="NO_IDENTIFICATION_RESULT",
        style="MetricValue.TLabel",
        wraplength=1000,
    )
    app.material_identification_status_label.pack(anchor="w", pady=(3, 0))

    models = ttk.Frame(page)
    models.pack(fill="both", expand=True)
    model_u = ttk.LabelFrame(models, text="Model U", padding=8)
    model_u.pack(side="left", fill="both", expand=True, padx=(0, 5))
    model_p = ttk.LabelFrame(models, text="Model P", padding=8)
    model_p.pack(side="left", fill="both", expand=True, padx=(5, 0))
    app.material_model_u_table = _build_read_only_table(
        model_u,
        ("parameter", "value", "unit"),
        ("Effective property", "Value", "Unit"),
        (160, 190, 100),
        height=3,
    )
    app.material_model_p_table = _build_read_only_table(
        model_p,
        ("parameter", "value", "unit"),
        ("Effective property", "Value", "Unit"),
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
    ttk.Label(
        interpretation,
        text=(
            "Effective homogeneous face-sheet properties\n"
            "Not true fibre properties, ply properties, or unique laminate constants."
        ),
        justify="left",
        wraplength=1050,
    ).pack(anchor="nw", fill="x")

    limitations = ttk.LabelFrame(page, text="Limitations", padding=8)
    limitations.pack(fill="x", pady=(10, 0))
    for text in (
        "Laminate architecture unknown",
        "Core frozen",
        "Density frozen",
        "Adhesive frozen",
        "Gxy weighting-sensitive",
    ):
        ttk.Label(limitations, text=f"• {text}").pack(
            side="left", anchor="w", padx=(0, 20)
        )


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
    for text in (
        "Effective properties only",
        "Laminate architecture unknown",
        "Core frozen",
        "Density frozen",
        "Adhesive frozen",
    ):
        ttk.Label(limitations, text=f"• {text}").pack(
            side="left", anchor="w", padx=(0, 24)
        )


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
    ttk.Label(
        task,
        text=(
            "Effective homogeneous face-sheet property identification\n"
            "Unknown: Ex, Ey, Gxy\n"
            "Frozen: core, density, adhesive, geometry"
        ),
        justify="left",
        wraplength=480,
    ).pack(anchor="nw", fill="x")

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
    ttk.Label(
        limitations,
        text=(
            "Effective properties only; not ply/fibre constants; unknown laminate "
            "architecture; frozen core/interface assumptions."
        ),
        justify="left",
        wraplength=1050,
    ).pack(anchor="nw", fill="x")

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
            for parameter in _EFFECTIVE_PARAMETER_IDS
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
        self._install_material_identification_tab()

    def refresh_material_identification_pages(self, _event=None) -> None:
        labels = getattr(self, "material_identification_evidence_labels", {})
        for key, value in project_evidence_status(self).items():
            label = labels.get(key)
            if label is not None:
                label.configure(text=value)
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
        ttk.Label(
            heading,
            text=(
                "Results are labelled effective homogeneous face-sheet properties, "
                "not true fibre properties, ply properties, or unique laminate constants."
            ),
            justify="left",
            wraplength=1200,
        ).pack(anchor="w", pady=(4, 0))

        self.material_identification_notebook = ttk.Notebook(
            self.material_identification_tab
        )
        self.material_identification_notebook.pack(fill="both", expand=True)
        self.material_identification_pages = {}

        for step_label in MATERIAL_IDENTIFICATION_STEP_LABELS:
            page = ttk.Frame(self.material_identification_notebook, padding=16)
            self.material_identification_notebook.add(page, text=step_label)
            self.material_identification_pages[step_label] = page
            if step_label == "1. Project Evidence":
                _build_project_evidence_page(self, page)
            elif step_label == "2. Task Definition":
                _build_task_definition_page(page)
            elif step_label == "3. Modal Correspondence":
                _build_modal_correspondence_page(self, page)
            elif step_label == "4. Sensitivity":
                _build_sensitivity_page(self, page)
            elif step_label == "5. Identification":
                _build_identification_page(self, page)
            elif step_label == "6. Validation":
                _build_validation_page(self, page)
            elif step_label == "7. Report":
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
        for variable_name in (
            "abaqus_path",
            "experimental_path",
            "abaqus_installation_label",
        ):
            variable = getattr(self, variable_name, None)
            if variable is not None and hasattr(variable, "trace_add"):
                variable.trace_add("write", self._refresh_material_identification_pages)

    application_class.__init__ = material_identification_init
    application_class._install_material_identification_tab = (
        install_material_identification_tab
    )
    application_class._refresh_material_identification_pages = (
        refresh_material_identification_pages
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
    "identification_result_view",
    "modal_correspondence_view",
    "project_evidence_status",
    "report_evidence_snapshot",
    "sensitivity_evidence_view",
    "validation_evidence_view",
]
