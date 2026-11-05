"""MAT-3: the results of the Materials page as a ``.mcproj`` v2 project. No Qt, no solve and no source file is read.

A v2 project holds one SYNTHETIC software test of the shared inverse workflow: the form as entered, the frozen declaration,
the whole result, units, provenance and, as plain text, the paths the page had chosen. It holds no ODB, UNV, UFF or matrix
package. See ``docs/gui/PROJECT_FORMAT.md``.

The container and its atomic writing are ``services.analysis_project``. The check here is strict in every field and also
checks that the statuses belong together, so a file cannot state a stronger result than the workflow can produce: the release
status has one value, only SYNTHETIC studies are accepted, a refusal holds no candidate, and a candidate needs what the
workflow requires of one. The hashes find damage and careless edits. They are not a signature, so a project proves nothing.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import math
from pathlib import Path
import re
from typing import Any, Mapping

from domain.plate_inverse_problem import (
    PLATE_INVERSE_DECLARATION_SCHEMA,
    RESTRICTIONS_UNCHANGED,
    IdentifiabilityDiagnostics,
    InverseRefusalCode,
    InverseScientificStatus,
    LeaveOneFamilyOutRow,
    ModalFrequencyRow,
    ModeIdentityRow,
    NumericalStatus,
    ObservationRole,
    PlateInverseDeclaration,
    PlateInverseResult,
    ReleaseStatus,
    ResidualTableRow,
    StudyIntent,
    UncertaintyReport,
)
from domain.plate_material_problem import EvidenceKind, ExecutionStatus, ForwardBackendId, identity_hash

from . import analysis_project as ap
from .identification_step import IterationRecord

STUDY_KIND = StudyIntent.SYNTHETIC_SOFTWARE_TEST.value
NOT_OPENED = "NOT_OPENED"
_TOP_KEYS = ("schema", "saved_at", "written_at", "program", "materials")
_SECTION_KEYS = ("study_kind", "backend_id", "input", "known_values", "declaration", "declaration_hash", "result",
                 "result_hash", "units", "provenance", "references", "statement")
_DECLARATION_KEYS = ("schema", "study_id", "intent", "evidence_kind", "backend_id", "model_identity", "specimen_id",
                     "observation_set", "rows", "parameters", "confirmed_clusters", "geometry", "degree_x", "degree_y",
                     "forward_mode_count", "stage_a_model_id", "execution_authorization", "provenance", "policy", "budget")
_DECLARED_ROW_KEYS = ("row_id", "experimental_mode", "experimental_hz", "model_mode", "role", "family", "mode_source",
                      "dataset_type", "measurement_sd_ln", "setup_sd_ln", "setup_provisional", "shape")
_RESULT_HASH_ROWS = ("frequencies", "fit_residuals", "holdout_residuals", "mode_identity", "iterations", "leave_one_family_out")
_NON_FINITE = "non_finite"
FORM_KEYS = {"geometry": ("a", "b", "length_unit", "mass_basis", "mass", "mass_unit", "thickness"),
             "numerics": ("degree", "mode_count", "observed_modes", "holdout_modes", "sigma"),
             "budget": ("max_solves", "max_seconds"),
             "package": ("source", "path")}

# s text, S text or null, n number, N number or null, i whole number, I whole number or null, b true or false,
# t text list, a a nested value of numbers and texts
_ROW_SPECS = {
    ModalFrequencyRow: {"row_id": "s", "role": "r", "experimental_hz": "n", "initial_model_hz": "n", "final_model_hz": "n"},
    ResidualTableRow: {"term_id": "s", "row_ids": "t", "role": "r", "family": "s", "sigma_ln": "n", "initial_log_ratio": "n",
                       "final_log_ratio": "n", "initial_whitened": "n", "final_whitened": "n"},
    ModeIdentityRow: {"row_id": "s", "experimental_mode": "i", "initial_model_mode": "i", "final_model_mode": "i",
                      "initial_experimental_mac": "n", "final_experimental_mac": "n", "minimum_model_to_model_mac": "n"},
    LeaveOneFamilyOutRow: {"family": "s", "removed_term_ids": "t", "status": "s", "estimate": "A", "reasons": "t"},
    IterationRecord: {"iteration": "i", "mu": "n", "x": "a", "trial_x": "a", "objective_before": "n", "trial_objective": "N",
                      "accepted": "b", "note": "s"},
    IdentifiabilityDiagnostics: {"status": "s", "rank": "i", "parameter_ids": "t", "singular_values": "a",
                                 "condition_number": "n", "correlation": "A", "pairwise_cosines": "a", "projection_q": "a",
                                 "sensitivity": "a", "term_ids": "t"},
    UncertaintyReport: {"statistical_sd": "A", "birge_status": "s", "birge_adjusted_sd": "A", "robustness_range": "a",
                        "robustness_note": "s", "pattern_status": "s", "pattern_reasons": "t", "available_components": "t",
                        "missing_components": "t"},
}
_RESULT_SPEC = {"declaration_hash": "s", "refusal_reason": "s", "forward_refusal_code": "S", "scientific_reasons": "t",
                "initial_parameters": "A", "final_parameters": "A", "initial_stiffness": "A", "final_stiffness": "A",
                "conditional_effective_constants": "A", "order_changes": "a", "initial_objective": "N", "final_objective": "N",
                "solves": "i", "max_analytic_sensitivity_difference": "N", "max_eigen_residual_seen": "N",
                "max_orthonormality_error_seen": "N", "package_validation_text": "S", "package_validation_status": "s"}


def _invalid(text: str) -> ap.ProjectRefused:
    return ap.ProjectRefused(ap.INVALID, f"The Materials results are not valid: {text}.")


# ---------------------------------------------------------------------------------------------- to and from JSON


def to_json(value: Any) -> Any:
    """Exact JSON form: floats keep every bit, and a non-finite one is a tagged text, since strict JSON has none."""
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        number = float(value)
        return number if math.isfinite(number) else {_NON_FINITE: repr(number)}
    if is_dataclass(value):
        return {item.name: to_json(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): to_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    item = getattr(value, "item", None)
    if callable(item):
        return to_json(item())
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return to_json(tolist())
    raise TypeError(f"{type(value).__name__} has no project form.")


def from_json(value: Any) -> Any:
    """Undo the tag of a non-finite float; the rest is already in its exact form."""
    if isinstance(value, dict):
        if set(value) == {_NON_FINITE}:
            return float(value[_NON_FINITE])
        return {key: from_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [from_json(item) for item in value]
    return value


def number(value: Any) -> Any:
    """A saved number for display and arithmetic, its tag undone."""
    return from_json(value)


def declaration_document(declaration: PlateInverseDeclaration) -> dict:
    return to_json(declaration.identity())


def result_document(result: PlateInverseResult) -> dict:
    return to_json(result)


def result_hash_of(result: Mapping) -> str:
    """``PlateInverseResult.result_hash`` from the saved form: the same fields and the same float bits."""
    names = ("declaration_hash", "execution_status", "numerical_status", "scientific_status", "refusal_code",
             "initial_parameters", "final_parameters", "solves", "identifiability", "uncertainty") + _RESULT_HASH_ROWS
    return identity_hash(from_json({name: result[name] for name in names}))


def materials_section(form: Mapping, known_values: Mapping, declaration: PlateInverseDeclaration, result: PlateInverseResult,
                      units: Mapping, provenance: Mapping, references, statement: str) -> dict:
    return {"study_kind": STUDY_KIND, "backend_id": declaration.backend_id.value, "input": to_json(form),
            "known_values": to_json(known_values), "declaration": declaration_document(declaration),
            "declaration_hash": declaration.declaration_hash, "result": result_document(result),
            "result_hash": result.result_hash, "units": to_json(units), "provenance": to_json(provenance),
            "references": [{"role": role, "path": str(where), "state": NOT_OPENED} for role, where in references],
            "statement": statement}


# ---------------------------------------------------------------------------------------------- the checks


def _keys(value: Any, keys, name: str) -> None:
    if not isinstance(value, dict) or set(value) != set(keys):
        raise _invalid(f"{name} is incomplete or holds unknown fields")


def _is_number(value: Any) -> bool:
    if isinstance(value, dict):
        return set(value) == {_NON_FINITE} and value[_NON_FINITE] in ("inf", "-inf", "nan")
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _is_whole(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _nested(value: Any) -> bool:
    if value is None or isinstance(value, str) or _is_number(value):
        return True
    if isinstance(value, list):
        return all(_nested(item) for item in value)
    return isinstance(value, dict) and all(_nested(item) for item in value.values())


def _check_field(value: Any, code: str, name: str) -> None:
    good = {"s": lambda: isinstance(value, str),
            "S": lambda: value is None or isinstance(value, str),
            "n": lambda: _is_number(value),
            "N": lambda: value is None or _is_number(value),
            "i": lambda: _is_whole(value),
            "b": lambda: isinstance(value, bool),
            "t": lambda: isinstance(value, list) and all(isinstance(item, str) for item in value),
            "r": lambda: value in {item.value for item in ObservationRole},
            "a": lambda: value is not None and _nested(value),
            "A": lambda: _nested(value)}[code]()
    if not good:
        raise _invalid(f"{name} does not hold what it should")


def _check_spec(value: Any, spec: Mapping, name: str) -> None:
    _keys(value, spec, name)
    for key, code in spec.items():
        _check_field(value[key], code, f"{name}.{key}")


def _check_rows(rows: Any, kind: type, name: str) -> None:
    if not isinstance(rows, list):
        raise _invalid(f"{name} is not a list")
    for row in rows:
        _check_spec(row, _ROW_SPECS[kind], f"a row of {name}")


def _member(value: Any, kinds: type, name: str) -> Any:
    try:
        return kinds(value)
    except ValueError as error:
        raise _invalid(f"{name} {value!r} is not known") from error


def _check_form(form: Any, backend: str) -> None:
    _keys(form, ("backend", "parameters", "authorization_note") + tuple(FORM_KEYS), "the saved input")
    if form["backend"] != backend or not isinstance(form["authorization_note"], str):
        raise _invalid("the saved input does not belong to this study")
    for key, names in FORM_KEYS.items():
        _keys(form[key], names, f"the saved input's {key}")
        if not all(isinstance(item, str) for item in form[key].values()):
            raise _invalid(f"the saved input's {key} is not text")
    if not isinstance(form["parameters"], dict):
        raise _invalid("the saved parameters are not valid")
    for name, entry in form["parameters"].items():
        _keys(entry, ("truth", "start", "lower", "upper"), f"the saved parameter {name}")
        if not all(isinstance(item, str) for item in entry.values()):
            raise _invalid(f"the saved parameter {name} is not text")


def _check_declaration(declaration: Any, backend: str) -> None:
    _keys(declaration, _DECLARATION_KEYS, "the declaration")
    if declaration["schema"] != PLATE_INVERSE_DECLARATION_SCHEMA:
        raise _invalid("the declaration has another format")
    if declaration["intent"] != STUDY_KIND or declaration["evidence_kind"] != EvidenceKind.SYNTHETIC.value:
        raise _invalid("a project holds only a SYNTHETIC software test")
    if declaration["backend_id"] != backend:
        raise _invalid("the declaration names another method")
    if not str(declaration["study_id"]).startswith("SYNTHETIC-") or not str(declaration["provenance"]).startswith("SYNTHETIC"):
        raise _invalid("the declaration's identity is not marked SYNTHETIC")
    if not isinstance(declaration["rows"], list) or not isinstance(declaration["parameters"], list):
        raise _invalid("the declaration's rows or parameters are not lists")
    for row in declaration["rows"]:
        _keys(row, _DECLARED_ROW_KEYS, "a declared row")
        _check_field(row["experimental_hz"], "n", "a declared frequency")
        _check_field(row["role"], "r", "a declared role")
        if not _is_whole(row["experimental_mode"]) or not _is_whole(row["model_mode"]):
            raise _invalid("a declared row's mode is not a whole number")
        for pair in row["shape"] if isinstance(row["shape"], list) else [None]:
            if not (isinstance(pair, list) and len(pair) == 2 and all(_is_number(item) for item in pair)):
                raise _invalid("a declared shape is not valid")
    for entry in declaration["parameters"]:
        _keys(entry, ("name", "start", "lower", "upper"), "a declared parameter")
        if not all(_is_number(entry[key]) for key in ("start", "lower", "upper")):
            raise _invalid("a declared parameter is not numeric")


def _check_statuses(result: Mapping, backend: str) -> None:
    _member(result["execution_status"], ExecutionStatus, "the execution status")
    numerical = _member(result["numerical_status"], NumericalStatus, "the numerical status")
    scientific = _member(result["scientific_status"], InverseScientificStatus, "the scientific status")
    if result["release_status"] != ReleaseStatus.NOT_A_RELEASE_VALUE.value:
        raise _invalid("the release status can only be NOT_A_RELEASE_VALUE")
    if result["evidence_kind"] != EvidenceKind.SYNTHETIC.value or result["backend_id"] != backend:
        raise _invalid("the result is not this SYNTHETIC study's")
    if list(result["restrictions_unchanged"]) != list(RESTRICTIONS_UNCHANGED):
        raise _invalid("the unchanged restrictions were altered")
    if result["refusal_code"] is not None:
        _member(result["refusal_code"], InverseRefusalCode, "the refusal code")
        if scientific is not InverseScientificStatus.NO_RESULT or result["final_parameters"] is not None:
            raise _invalid("a refusal cannot hold a result")
    if scientific is InverseScientificStatus.DIAGNOSTIC_OPTIMIZER_CANDIDATE:
        block, cases = result["identifiability"], result["leave_one_family_out"]
        if result["refusal_code"] is not None or numerical is not NumericalStatus.CONVERGED \
                or result["execution_status"] != ExecutionStatus.COMPLETED.value or result["final_parameters"] is None \
                or result["uncertainty"] is None or result["uncertainty"]["pattern_status"] != "PASS" or block is None \
                or block["rank"] != len(block["parameter_ids"]) or not cases \
                or any(case["status"] != "VALID" for case in cases):
            raise _invalid("the candidate status does not fit what the file holds")


def _check_result(result: Any, backend: str) -> None:
    names = {item.name for item in fields(PlateInverseResult)}
    plain = set(_RESULT_SPEC) | set(_RESULT_HASH_ROWS) | {"execution_status", "numerical_status", "scientific_status",
                                                         "evidence_kind", "backend_id", "release_status",
                                                         "restrictions_unchanged", "refusal_code", "identifiability",
                                                         "uncertainty"}
    if plain != names:  # a changed result contract must be seen here, not skipped
        raise _invalid("this program's result contract and its check differ")
    _keys(result, names, "the result")
    for key, code in _RESULT_SPEC.items():
        _check_field(result[key], code, f"result.{key}")
    _check_rows(result["frequencies"], ModalFrequencyRow, "frequencies")
    _check_rows(result["fit_residuals"], ResidualTableRow, "fit_residuals")
    _check_rows(result["holdout_residuals"], ResidualTableRow, "holdout_residuals")
    _check_rows(result["mode_identity"], ModeIdentityRow, "mode_identity")
    _check_rows(result["iterations"], IterationRecord, "iterations")
    _check_rows(result["leave_one_family_out"], LeaveOneFamilyOutRow, "leave_one_family_out")
    if result["identifiability"] is not None:
        _check_spec(result["identifiability"], _ROW_SPECS[IdentifiabilityDiagnostics], "identifiability")
    if result["uncertainty"] is not None:
        _check_spec(result["uncertainty"], _ROW_SPECS[UncertaintyReport], "uncertainty")
    _check_statuses(result, backend)


def validate_materials_document(document: Any, images: Mapping[str, bytes]) -> None:
    """Every field has the documented form, and the statuses fit what the file holds."""
    _keys(document, _TOP_KEYS, "the project")
    if document["schema"] != ap.SCHEMA_V2:
        raise ap.ProjectRefused(ap.OTHER_VERSION, f"This project has the format {document['schema']!r}; this command reads "
                                                  f"{ap.SCHEMA_V2!r}.")
    if images:
        raise _invalid("a Materials project holds no pictures")
    for key in ("saved_at", "written_at", "program"):
        if not isinstance(document[key], str):
            raise _invalid(f"{key} is not a text")
    section = document["materials"]
    _keys(section, _SECTION_KEYS, "the Materials section")
    if section["study_kind"] != STUDY_KIND:
        raise _invalid("a project holds only a SYNTHETIC software test")
    backend = _member(section["backend_id"], ForwardBackendId, "the method").value
    _check_form(section["input"], backend)
    _check_field(section["known_values"], "a", "the known values")
    _check_declaration(section["declaration"], backend)
    _check_result(section["result"], backend)
    if not (isinstance(section["declaration_hash"], str) and re.fullmatch(r"[0-9a-f]{64}", section["declaration_hash"])):
        raise _invalid("the declaration hash is not a SHA-256")
    try:
        declared, computed = identity_hash(from_json(section["declaration"])), result_hash_of(section["result"])
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise _invalid(f"the identities cannot be computed ({error})") from error
    if declared != section["declaration_hash"] or section["result"]["declaration_hash"] != declared:
        raise _invalid("the declaration does not match its hash")
    if computed != section["result_hash"]:
        raise _invalid("the result does not match its hash")
    for key in ("units", "provenance"):
        if not isinstance(section[key], dict) or not all(isinstance(item, str) for item in section[key].values()):
            raise _invalid(f"{key} is not a table of texts")
    if not isinstance(section["statement"], str) or not isinstance(section["references"], list):
        raise _invalid("the statement or the saved references are not valid")
    for entry in section["references"]:
        _keys(entry, ("role", "path", "state"), "a saved reference")
        if entry["state"] != NOT_OPENED or not isinstance(entry["role"], str) or not isinstance(entry["path"], str):
            raise _invalid("a saved reference is not plain unopened text")


# ---------------------------------------------------------------------------------------------- writing and reading


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def materials_document(section: Mapping, program: str, saved_at: str = "") -> dict:
    now = _now()
    return {"schema": ap.SCHEMA_V2, "saved_at": saved_at or now, "written_at": now, "program": program, "materials": section}


def write_materials_project(document: Mapping, path, cancel_event=None) -> Path:
    """All or nothing; a path the page holds is never overwritten. Raises ``ProjectRefused``."""
    protected = tuple(entry["path"] for entry in document["materials"]["references"])
    return ap.write_project(document, {}, path, protected, cancel_event, schema=ap.SCHEMA_V2,
                            validate=validate_materials_document)


def read_materials_project(path) -> dict:
    """The document of a v2 project that passes every check. Reads only this file. Raises ``ProjectRefused``."""
    document, _images = ap.read_project(path, ap.SCHEMA_V2, validate_materials_document)
    return document


__all__ = ["FORM_KEYS", "NOT_OPENED", "STUDY_KIND", "declaration_document", "from_json", "materials_document",
           "materials_section", "number", "read_materials_project", "result_document", "result_hash_of", "to_json",
           "validate_materials_document", "write_materials_project"]
