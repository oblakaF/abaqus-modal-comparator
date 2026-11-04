"""WORKING-DRAFT-R2: saving an analysis as a project and showing it again later, with no Qt.

``save_analysis`` records the shown result as it is: the status, the tables, the comparison only when one was computed,
the identities taken when the files were read (a later hash is never attributed to data read earlier) and one saved
picture of each mode and record. ``open_project`` gives the saved result back without reading an ODB, a UNV or an FE
package, and without starting Abaqus or the comparator.

A snapshot is historical. ``check_sources`` hashes the files now and says what it found, and a new analysis stays blocked
until the ODB and the experimental file are shown to have the saved content. Even then, only a new analysis gives a new
result, through the same services and registration checks as any other; nothing in a project can raise a status.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from new_gui import APP_NAME
from new_gui import analyze_model as am
from new_gui import comparison_model as cm
from new_gui import preview_model as pm
from new_gui import shape_model as sm
from new_gui.workspace_state import EXPERIMENTAL, FE
from services import analysis_project as ap
from services import confirmed_registration as cs
from services import fe_package_identity as fpi
from services import generic_registration as gr
from services import odb_import_service as svc

SHAPE_COMPONENT = "magnitude"  # defined for any geometry, as the page's own default
UNCHANGED, MOVED, CHANGED, MISSING, NOT_CHECKED, UNREADABLE = ("UNCHANGED", "MOVED", "CHANGED", "MISSING", "NOT_CHECKED",
                                                               "UNREADABLE")
NOT_REVALIDATED = "NOT_REVALIDATED"
_USABLE = (UNCHANGED, MOVED)
ROLE_ODB, ROLE_PACKAGE, ROLE_EXPERIMENTAL, ROLE_REGISTRATION = ("FE results (.odb)", "Extracted FE modes",
                                                                "Experiment (.unv, .uff)", "Registration")


@dataclass(frozen=True)
class RegistrationReference:
    """Where a confirmation came from: its file and draft. The content is checked again whenever it is used."""

    document: dict
    confirmation_path: str = ""
    draft_path: str = ""


@dataclass(frozen=True)
class Snapshot:
    """A project as opened: what is displayed comes only from here."""

    path: Path
    document: dict
    images: dict
    analysis: am.Analysis


@dataclass(frozen=True)
class SourceRow:
    role: str
    state: str
    path: str
    detail: str = ""

    @property
    def text(self) -> str:
        return f"{self.role}: {self.state}" + (f" - {self.path}" if self.path else "") + (
            f" ({self.detail})" if self.detail else "")


@dataclass(frozen=True)
class SourceCheck:
    rows: tuple
    can_analyze: bool  # the ODB and the experimental file have the saved content, at the paths in ``paths``
    hashed: bool  # False for the quick look at opening: nothing was hashed, so nothing is confirmed
    paths: dict = field(default_factory=dict)  # FE, EXPERIMENTAL -> the path checked
    manifest: Optional[Path] = None
    extraction_folder: Optional[Path] = None


# ---------------------------------------------------------------------------------------------- saving


def _texts(values) -> list:
    return [str(value) for value in values]


def _rows(rows) -> list:
    return [_texts(row) for row in rows]


def _comparison_document(view) -> Optional[dict]:
    if view is None:
        return None
    pairs = [{"index": int(row.index), "abaqus_mode": int(row.abaqus_mode), "experimental_mode": int(row.experimental_mode),
              "mac": None if row.mac is None else float(row.mac),
              "frequency_error_percent": float(row.frequency_error_percent), "cells": _texts(row.cells)}
             for row in view.pair_rows]
    return {"status": view.status, "statement": view.statement, "set_title": view.set_title, "specimen": view.specimen,
            "fixture_id": view.fixture_id, "registration": view.registration, "registration_file": view.registration_file,
            "pair_rows": pairs, "mac_fe_modes": [int(n) for n in view.mac_fe_modes],
            "mac_experimental_modes": [int(n) for n in view.mac_experimental_modes], "mac_cells": _rows(view.mac_cells),
            "mac_values": [list(row) for row in view.mac_values],
            "assigned_cells": sorted([int(row), int(column)] for row, column in view.assigned_cells),
            "candidate_rows": _rows(view.candidate_rows), "unmatched_fe_rows": _rows(view.unmatched_fe_rows),
            "unmatched_experimental_rows": _rows(view.unmatched_experimental_rows),
            "unpaired_experimental": _texts(view.unpaired_experimental), "rigid_rows": _rows(view.rigid_rows),
            "close_groups": _texts(view.close_groups), "warnings": _texts(view.warnings),
            "provenance": _rows(view.provenance), "gates": _rows(view.gates), "target_counts": view.target_counts,
            "limits": _texts(view.limits), "auto_id_note": view.auto_id_note}


def _registration_document(analysis: am.Analysis, reference: Optional[RegistrationReference]) -> dict:
    empty = {"kind": ap.KIND_NONE, "confirmation_path": "", "draft_path": "", "confirmed_by": "", "confirmed_at": "",
             "evidence_location": "", "confirmation_sha256": "", "draft_sha256": "", "evidence_sha256": "",
             "registration_hash": "", "registration_file": "", "limits": []}
    view = analysis.comparison
    if view is None:
        return empty
    if reference is None:
        return dict(empty, kind=ap.KIND_ARCHIVED, registration_hash=view.registration,
                    registration_file=view.registration_file)
    document = reference.document
    return dict(empty, kind=ap.KIND_CONFIRMED, confirmation_path=reference.confirmation_path,
                draft_path=reference.draft_path, confirmed_by=document["confirmed_by"],
                confirmed_at=document["confirmed_at"], evidence_location=document["evidence_location"],
                confirmation_sha256=document["confirmation_sha256"], draft_sha256=document["draft_sha256"],
                evidence_sha256=document["evidence_sha256"], registration_hash=document["registration_hash"],
                registration_file=view.registration_file, limits=_texts(cs.LIMITS))


def _sources_document(inputs: am.Inputs, odb_path) -> dict:
    fe, experimental = inputs.identities["fe"], inputs.identities["experimental"]
    manifest = Path(inputs.full_fe.manifest_path)
    record = svc.read_source_record(manifest.parent)
    if record is None or not record["odb"].get("sha256"):
        raise ap.ProjectRefused(ap.WRITE_FAILED, "The ODB's identity is not recorded with these extracted modes, so the "
                                                 "project could not name its source.")
    package = fe["package"]
    files = [[item["role"], item["relative"], int(item["size"]), item["sha256"]] for item in package["files"]]
    size = record["odb"].get("size")  # an older record may not state it; a wrong 0 would read as a changed file
    return {"fe_odb": {"path": str(odb_path), "size": int(Path(odb_path).stat().st_size if size is None else size),
                       "sha256": record["odb"]["sha256"], "relocated_from": []},
            "fe_package": {"manifest_path": str(manifest), "manifest_size": int(fe["size"]), "manifest_sha256": fe["sha256"],
                           "package_sha256": package["package_sha256"], "total_bytes": sum(row[2] for row in files),
                           "files": files, "relocated_from": []},
            "experimental": {"path": str(inputs.full_experimental.selected_path),
                             "source_path": str(inputs.full_experimental.source_path), "size": int(experimental["size"]),
                             "sha256": experimental["sha256"], "relocated_from": []}}


def _modal_set_document(inputs: am.Inputs, analysis: am.Analysis) -> dict:
    index = analysis.set_index
    chosen = inputs.full_experimental.sets[index]
    return {"index": index, "key": str(chosen.key), "display_name": str(chosen.display_name),
            "processing_name": str(chosen.processing_name), "title": analysis.set_title,
            "record_count": len(chosen.records), "analyzed_count": len(inputs.experimental.sets[index].records),
            "provisional": any(bool(record.provisional) for record in chosen.records),
            "all_sets": [{"key": str(item.key), "title": str(item.title), "record_count": len(item.records)}
                         for item in inputs.full_experimental.sets]}


def _modes_document(inputs: am.Inputs, analysis: am.Analysis) -> dict:
    kinds = {row[0]: row[2] for row in analysis.fe_rows}
    records = inputs.experimental.sets[analysis.set_index].records
    return {"fe": [{"number": int(mode.number), "frequency_hz": float(mode.frequency_hz),
                    "type": kinds.get(str(mode.number), "")} for mode in inputs.fe.modes],
            "experimental": [{"record": f"EXP{position}", "number": int(record.number),
                              "frequency_hz": float(record.frequency_hz), "classification": str(record.label)}
                             for position, record in enumerate(records, 1)]}


def _result_document(analysis: am.Analysis) -> dict:
    return {"status": analysis.status, "statement": analysis.statement, "set_index": analysis.set_index,
            "set_title": analysis.set_title, "fe_rows": _rows(analysis.fe_rows),
            "experimental_rows": _rows(analysis.experimental_rows), "nearest_rows": _rows(analysis.nearest_rows),
            "first_elastic": analysis.first_elastic, "rigid_modes": [int(n) for n in analysis.rigid_modes],
            "facts": _texts(analysis.facts), "notes": _texts(analysis.notes),
            "registration_reason": str(analysis.registration_reason or ""),
            "registration_outcome": str(analysis.registration_outcome or ""),
            "unavailable_fe": [int(n) for n in analysis.unavailable_fe],
            "experimental_total": int(analysis.experimental_total)}


def _draw(kind: str, source, index: int, cancel_event) -> sm.ShapeOutcome:
    outcome = sm.run_render(kind, source, index, SHAPE_COMPONENT, 0, cancel_event, sm.DEFAULT_VIEW)
    if outcome.cancelled:
        raise am.StepCancelled()
    return outcome


def _entry(outcome: sm.ShapeOutcome, number: str, label: str, name: str, images: dict) -> dict:
    refusal, image = outcome.error, None
    if not refusal and len(outcome.image) > ap.MAX_IMAGE_BYTES:
        refusal = "The picture is too large to keep in a project."
    if not refusal:
        image = name
        images[name] = outcome.image
    return {"number": number, "label": label, "image": image, "lines": _texts(outcome.lines), "refusal": refusal}


def draw_shapes(inputs: am.Inputs, set_index: int, cancel_event, say=None) -> tuple:
    """One picture per mode and record of the scope, drawn by the services from the data already read."""
    fe_modes = inputs.fe.modes
    chosen = inputs.experimental.sets[set_index]
    total = len(fe_modes) + len(chosen.records)
    images, fe_entries, experimental_entries = {}, [], []
    for index, mode in enumerate(fe_modes):
        if say:
            say(f"Drawing saved shape {index + 1} of {total}")
        outcome = _draw(FE, inputs.fe, index, cancel_event)
        fe_entries.append(_entry(outcome, str(mode.number), f"Mode {mode.number} - {mode.frequency_hz:.6g} Hz",
                                 f"images/fe_{int(mode.number)}.png", images))
    for index, record in enumerate(chosen.records):
        if say:
            say(f"Drawing saved shape {len(fe_modes) + index + 1} of {total}")
        outcome = _draw(EXPERIMENTAL, chosen, index, cancel_event)
        experimental_entries.append(_entry(outcome, str(record.number),
                                           f"Record {index + 1}: mode {record.number} - {record.frequency_hz:.6g} Hz",
                                           f"images/exp_{index + 1}.png", images))
    shapes = {"component": SHAPE_COMPONENT, "fe": fe_entries, "experimental": experimental_entries}
    return shapes, images


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def analysis_document(analysis: am.Analysis, inputs: am.Inputs, odb_path, reference: Optional[RegistrationReference],
                      shapes: dict) -> dict:
    now = _now()
    return {"schema": ap.SCHEMA, "saved_at": now, "written_at": now, "program": APP_NAME,
            "scope": {"first_mode": am.FIRST_MODE, "last_mode": am.LAST_MODE, "mode_limit": am.MODE_LIMIT},
            "sources": _sources_document(inputs, odb_path), "modal_set": _modal_set_document(inputs, analysis),
            "modes": _modes_document(inputs, analysis), "result": _result_document(analysis),
            "comparison": _comparison_document(analysis.comparison),
            "registration": _registration_document(analysis, reference), "shapes": shapes}


def _protected(sources: dict, reference: Optional[RegistrationReference] = None) -> tuple:
    manifest = Path(sources["fe_package"]["manifest_path"])
    files = tuple(manifest.parent / row[1] for row in sources["fe_package"]["files"])
    paths = (sources["fe_odb"]["path"], str(manifest), sources["experimental"]["path"], sources["experimental"]["source_path"])
    return paths + files + ((reference.confirmation_path, reference.draft_path) if reference else ())


def save_analysis(analysis: am.Analysis, inputs: am.Inputs, odb_path, reference: Optional[RegistrationReference], path,
                  cancel_event, say=None) -> Path:
    """Draw the saved shapes, then write the project; the shown result is not touched. Raises ``ProjectRefused``."""
    shapes, images = draw_shapes(inputs, analysis.set_index, cancel_event, say)
    document = analysis_document(analysis, inputs, odb_path, reference, shapes)
    if say:
        say("Writing the project")
    return ap.write_project(document, images, path, _protected(document["sources"], reference), cancel_event)


def relocated_document(document: dict, check: Optional[SourceCheck]) -> dict:
    """The document with the paths of files a check found moved, the earlier paths kept; the hashes do not change."""
    updated = dict(document, sources={key: dict(value) for key, value in document["sources"].items()})
    if check is not None and check.hashed:
        states = {row.role: row.state for row in check.rows}
        sources = updated["sources"]
        for role, key, field_name, new in ((ROLE_ODB, "fe_odb", "path", check.paths.get(FE)),
                                           (ROLE_EXPERIMENTAL, "experimental", "path", check.paths.get(EXPERIMENTAL)),
                                           (ROLE_PACKAGE, "fe_package", "manifest_path", check.manifest)):
            if states.get(role) == MOVED and new is not None and str(new) != sources[key][field_name]:
                sources[key]["relocated_from"] = sources[key]["relocated_from"] + [sources[key][field_name]]
                sources[key][field_name] = str(new)
                if key == "experimental":
                    sources[key]["source_path"] = str(new)
    return updated


def save_snapshot(snapshot: Snapshot, check: Optional[SourceCheck], path, cancel_event) -> Path:
    """The same saved results in another file, or with confirmed new paths. ``saved_at`` keeps the results' time."""
    document = relocated_document(snapshot.document, check)
    document["written_at"] = _now()
    return ap.write_project(document, snapshot.images, path, _protected(document["sources"]), cancel_event)


# ---------------------------------------------------------------------------------------------- opening


def _tuples(rows) -> tuple:
    return tuple(tuple(row) for row in rows)


def _view_of(document: Optional[dict]):
    if document is None:
        return None
    pairs = tuple(cm.PairRow(item["index"], item["abaqus_mode"], item["experimental_mode"], item["mac"],
                             item["frequency_error_percent"], tuple(item["cells"])) for item in document["pair_rows"])
    return cm.ComparisonView(
        status=document["status"], statement=document["statement"], set_title=document["set_title"],
        specimen=document["specimen"], fixture_id=document["fixture_id"], registration=document["registration"],
        registration_file=document["registration_file"], pair_rows=pairs, mac_fe_modes=tuple(document["mac_fe_modes"]),
        mac_experimental_modes=tuple(document["mac_experimental_modes"]), mac_cells=_tuples(document["mac_cells"]),
        assigned_cells=frozenset(tuple(cell) for cell in document["assigned_cells"]),
        candidate_rows=_tuples(document["candidate_rows"]), unmatched_fe_rows=_tuples(document["unmatched_fe_rows"]),
        unmatched_experimental_rows=_tuples(document["unmatched_experimental_rows"]),
        unpaired_experimental=tuple(document["unpaired_experimental"]), rigid_rows=_tuples(document["rigid_rows"]),
        close_groups=tuple(document["close_groups"]), warnings=tuple(document["warnings"]),
        provenance=_tuples(document["provenance"]), gates=_tuples(document["gates"]),
        target_counts=document["target_counts"], limits=tuple(document["limits"]), auto_id_note=document["auto_id_note"],
        mac_values=tuple(tuple(row) for row in document["mac_values"]))


def analysis_of(document: dict) -> am.Analysis:
    """The saved result as the page shows any result; every value is the saved one, nothing is computed."""
    result = document["result"]
    return am.Analysis(result["status"], result["statement"], result["set_index"], result["set_title"],
                       _tuples(result["fe_rows"]), _tuples(result["experimental_rows"]), _tuples(result["nearest_rows"]),
                       result["first_elastic"], tuple(result["rigid_modes"]), tuple(result["facts"]),
                       tuple(result["notes"]), _view_of(document["comparison"]), result["registration_reason"],
                       result["registration_outcome"], tuple(result["unavailable_fe"]), result["experimental_total"])


def open_project(path) -> Snapshot:
    """The saved results of a project that passes every check. Reads only this file. Raises ``ProjectRefused``."""
    document, images = ap.read_project(path)
    try:
        analysis = analysis_of(document)
    except (KeyError, TypeError, ValueError) as error:
        raise ap.ProjectRefused(ap.INVALID, f"The project's results cannot be shown: {error}.") from error
    return Snapshot(Path(path), document, images, analysis)


# ---------------------------------------------------------------------------------------------- the source files


def _registration_row(document: dict) -> SourceRow:
    registration = document["registration"]
    if registration["kind"] == ap.KIND_NONE:
        return SourceRow(ROLE_REGISTRATION, "NONE", "", "the saved result has no registration")
    if registration["kind"] == ap.KIND_ARCHIVED:
        return SourceRow(ROLE_REGISTRATION, NOT_REVALIDATED, registration["registration_file"],
                         "Analyze checks the archived registration again")
    return SourceRow(ROLE_REGISTRATION, NOT_REVALIDATED, registration["confirmation_path"], _confirmation_detail(registration))


def _confirmation_detail(registration: dict) -> str:
    path = registration["confirmation_path"]
    if not path:
        state = "the file's place was not recorded"
    else:
        try:
            found = gr.read_draft(path)
        except gr.DraftRefused:
            state = "the confirmation file cannot be read there"
        else:
            same = found.get("confirmation_sha256") == registration["confirmation_sha256"]
            state = "the confirmation file is there" if same else "the file there is another confirmation"
    return f"{state}; after Analyze, open it to compare again"


def not_checked(document: dict) -> SourceCheck:
    """What opening a project shows: the saved paths, as text only. No path in the project is looked at or contacted, so
    a project from anywhere opens offline and at once, and a new analysis stays blocked."""
    sources = document["sources"]
    registration = document["registration"]
    detail = "not looked at; use Check source files"
    place = registration["confirmation_path"] or registration["registration_file"]
    rows = (SourceRow(ROLE_ODB, NOT_CHECKED, sources["fe_odb"]["path"], detail),
            SourceRow(ROLE_PACKAGE, NOT_CHECKED, sources["fe_package"]["manifest_path"], detail),
            SourceRow(ROLE_EXPERIMENTAL, NOT_CHECKED, sources["experimental"]["path"], detail),
            SourceRow(ROLE_REGISTRATION, "NONE", "", "the saved result has no registration")
            if registration["kind"] == ap.KIND_NONE else SourceRow(ROLE_REGISTRATION, NOT_CHECKED, place, detail))
    return SourceCheck(rows, False, False, {FE: Path(sources["fe_odb"]["path"]),
                                            EXPERIMENTAL: Path(sources["experimental"]["path"])})


def _check_odb(saved: dict, path, cancel_event, say) -> tuple:
    if not Path(path).is_file():
        return SourceRow(ROLE_ODB, MISSING, str(path)), False
    try:
        found = svc.hash_file(path, cancel_event, say)
    except svc.OdbImportCancelled as error:
        raise am.StepCancelled() from error
    except (svc.OdbImportRefused, OSError) as error:
        return SourceRow(ROLE_ODB, UNREADABLE, str(path), str(error)), False
    if found["sha256"] != saved["sha256"]:
        return SourceRow(ROLE_ODB, CHANGED, str(path), "its SHA-256 is not the saved one"), False
    state = UNCHANGED if _same_path(path, saved["path"]) else MOVED
    return SourceRow(ROLE_ODB, state, str(path)), True


def _check_experimental(saved: dict, path, cancel_event) -> tuple:
    if not Path(path).is_file():
        return SourceRow(ROLE_EXPERIMENTAL, MISSING, str(path)), False
    found = pm.file_identity(path, cancel_event)
    if cancel_event.is_set():
        raise am.StepCancelled()
    if found is None:
        return SourceRow(ROLE_EXPERIMENTAL, UNREADABLE, str(path), "it could not be read"), False
    if found["sha256"] != saved["sha256"]:
        return SourceRow(ROLE_EXPERIMENTAL, CHANGED, str(path), "its SHA-256 is not the saved one"), False
    state = UNCHANGED if _same_path(path, saved["path"]) else MOVED
    return SourceRow(ROLE_EXPERIMENTAL, state, str(path)), True


def _same_path(one, other) -> bool:
    try:
        return Path(one).resolve() == Path(other).resolve()
    except OSError:
        return str(one) == str(other)


def _package_matches(manifest: Path, saved: dict, cancel_event) -> bool:
    try:
        found = fpi.identify(manifest, cancel_event)
    except fpi.PackageIdentityRefused as refusal:
        if refusal.kind == fpi.CANCELLED or cancel_event.is_set():
            raise am.StepCancelled() from refusal
        return False
    return found["package_sha256"] == saved["package_sha256"]


def _check_package(saved: dict, odb_sha256: str, odb_path, folder, cancel_event) -> tuple:
    """(row, manifest, its folder): the extracted modes at their saved place or in the usual folders, by content."""
    recorded = Path(saved["manifest_path"])
    present = recorded.is_file()
    if present and _package_matches(recorded, saved, cancel_event):
        return SourceRow(ROLE_PACKAGE, UNCHANGED, str(recorded)), recorded, recorded.parent.parent
    places = [place for place in (folder, am.package_folder(odb_path), recorded.parent.parent) if place is not None]
    for place in places:
        for covering in (False, True):
            for package in svc.existing_packages(place, odb_sha256, am.FIRST_MODE, am.LAST_MODE, covering=covering):
                manifest = package / "manifest.json"
                if manifest != recorded and _package_matches(manifest, saved, cancel_event):
                    return SourceRow(ROLE_PACKAGE, MOVED, str(manifest)), manifest, Path(place)
    state = CHANGED if present else MISSING
    return (SourceRow(ROLE_PACKAGE, state, str(recorded),
                      "without the saved package, Analyze asks before extracting with Abaqus Python"), None, None)


def check_sources(document: dict, odb_path, experimental_path, folder, cancel_event, say=None) -> SourceCheck:
    """Hash the files now and say what was found. Raises ``StepCancelled``. Changes nothing and starts no process."""
    sources = document["sources"]
    if say:
        say("Checking the ODB")
    odb_row, odb_same = _check_odb(sources["fe_odb"], odb_path, cancel_event, say)
    if say:
        say("Checking the experimental file")
    experimental_row, experimental_same = _check_experimental(sources["experimental"], experimental_path, cancel_event)
    if say:
        say("Checking the extracted FE modes")
    package_row, manifest, extraction = _check_package(sources["fe_package"], sources["fe_odb"]["sha256"], odb_path, folder,
                                                       cancel_event)
    return SourceCheck((odb_row, package_row, experimental_row, _registration_row(document)),
                       odb_same and experimental_same, True,
                       {FE: Path(odb_path), EXPERIMENTAL: Path(experimental_path)}, manifest, extraction)


__all__ = ["CHANGED", "MISSING", "MOVED", "NOT_CHECKED", "NOT_REVALIDATED", "RegistrationReference", "SourceCheck",
           "SourceRow", "Snapshot", "UNCHANGED", "UNREADABLE", "analysis_document", "analysis_of", "check_sources",
           "not_checked", "open_project", "relocated_document", "save_analysis", "save_snapshot"]
