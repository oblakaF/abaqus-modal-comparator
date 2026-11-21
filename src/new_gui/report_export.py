"""NEW-GUI.6: the engineering report of the Analysis page, written only on the user's command, with no Qt.

Two reports, both from existing project report writers and the objects the page shows; nothing is computed again:

- **Verified comparison** (a ``ComparisonResult`` of the verified comparison): the program's comparison report,
  ``reporting.export_excel`` / ``reporting.export_pdf`` as ``src/main.py`` composes them, plus a JSON record of the
  sources with fresh SHA-256, the modal set, the registration provenance, the pairs with MAC and signed frequency
  errors, the MAC matrix, the warnings and the result's status and limits. Before writing, the files are identified
  again: an experimental file changed since the comparison is refused.
- **Diagnostic** (no verified registration): ``services.diagnostic_report`` (CORE-E2E-D) with the frequency-only
  diagnostic the page shows: no MAC, no mode pair and no orientation, ever.

The program's comparison report writers are composed by seven existing report layers that ``src/main.py`` installs
in a fixed order. ``ensure_application_reporting`` installs exactly those layers, unchanged, in that order (each is
idempotent) and then checks the final owners the program's runtime contract names; any other owner is refused. No
layer is added. It touches only the report functions of ``reporting`` and ``advanced_metrics``.

NEW-GUI.6-F1: an export states the identities recorded when the files were read (``sources``), after confirming
that the FE manifest and the experimental file on disk still have them. A missing identity (not recorded, or the file
changed during the read) or a changed file refuses the export: a later hash is never attributed to data read earlier,
and no report claims a provenance that cannot be confirmed.

PLATE-ONLY-R2-F1: the FE identity is the whole extracted package (``services.fe_package_identity``: the manifest and
every geometry and mode file the loader read); a changed, missing or added file refuses the export. The ODB is never
read and its hash is never stated as the package's.

PREVIEW-01-COMPARISON-REPORT-FIX: the normal window's Review page exports the same comparison report. With a stated
registration basis (``basis``) the report says in its first Excel sheet, on its first PDF pages and in its JSON record
which registration the pairs rest on (an archived verified registration or a person's confirmation, never both), that
no physical mode identity is established by the report, and the verdict of every experimental record as the analysis
showed it (group-level and ambiguous verdicts included). These are the analysis's own texts and the comparator's own
numbers: nothing is compared, ranked or computed for the report.

Files are written only into the folder the user chose, with time-stamped names (nothing is replaced), each through a
temporary file in that folder that is renamed into place. The read data, the source files and the project's records
are never written.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
from typing import Optional

EXPORT = "Export report..."
SCHEMA = "new-gui/verified-modal-comparison/v1"
VERIFIED_STEM = "verified_modal_comparison"
DIAGNOSTIC_STEM = "modal_diagnostic_report"
# PREVIEW-01-COMPARISON-REPORT-FIX: what a pair of the report rests on, and what it never claims
ARCHIVED_BASIS, CONFIRMED_BASIS = "ARCHIVED_VERIFIED_REGISTRATION", "USER_CONFIRMED_REGISTRATION"
BASIS_TEXT = {
    ARCHIVED_BASIS: "Archived verified registration: an accepted physical registration of the project, bound to these "
                    "files by the FE geometry identity, the experimental file's SHA-256 and the modal set. Only its "
                    "geometric mapping is reused; frequencies and mode shapes are these files' own.",
    CONFIRMED_BASIS: "User-confirmed registration: a person's recorded statement for these two files. It is not an "
                     "archived, governed or independently verified registration.",
}
IDENTITY_NOT_CLAIMED = ("PHYSICAL MODE IDENTITY: NOT ESTABLISHED BY THIS REPORT. A pair is the comparator's numerical "
                        "assignment on the registration named here. A high MAC is not proof that one FE mode is one "
                        "measured mode: read the verdict of every record. Independent physical evidence of mode "
                        "identity is not part of this report and is not claimed.")
STATEMENT_SHEET = "Registration and verdicts"
STATEMENT_TITLE = "FE / experiment modal comparison: registration and verdicts"
PAIR_TITLES = ("FE mode", "FE (Hz)", "EXP record", "EXP mode", "EXP (Hz)", "Signed error (%)", "MAC",
               "Comparator status", "Close modes", "Verdict")
RECORD_TITLES = ("EXP record", "EXP mode", "EXP (Hz)", "Verdict")
GENERATOR = "new_gui.report_export (NEW-GUI.6) from the Analysis page's result; no new computation"

# The report layers of src/main.py, in its order: (module, function). tests check this order against main.py.
REPORT_LAYERS = (("performance_tuning", "install_performance_tuning"),
                 ("reporting_hardening", "install_reporting_hardening"),
                 ("amplitude_correlation", "install_amplitude_correlation"),
                 ("metrics_normalization", "install_metrics_normalization"),
                 ("enhanced_reporting", "install_reporting_enhancements"),
                 ("advanced_reporting", "install_advanced_reporting"),
                 ("final_reporting_review", "install_final_reporting_review"))
# The final owners the program's runtime contract expects (runtime_contracts.verify_runtime_contracts).
FINAL_OWNERS = (("render_pair_images", "amplitude_correlation"), ("render_mac_matrix", "reporting_hardening"),
                ("export_excel", "final_reporting_review"), ("export_pdf", "advanced_reporting"))

_REPORTING = threading.Lock()
_EXPORT = threading.Lock()  # one export at a time


class ReportRuntimeError(RuntimeError):
    """The program's report writers are not composed as src/main.py composes them."""


class ExportRefused(ValueError):
    """The report is not written; the message says why."""


def ensure_application_reporting() -> None:
    """Install the program's seven report layers in src/main.py's order, then check the final owners."""
    import importlib

    import reporting

    with _REPORTING:
        for module_name, function_name in REPORT_LAYERS:
            getattr(importlib.import_module(module_name), function_name)()
        wrong = [f"reporting.{name}: {getattr(getattr(reporting, name), '__module__', '?')}, expected {owner}"
                 for name, owner in FINAL_OWNERS if getattr(getattr(reporting, name), "__module__", None) != owner]
        if wrong:
            raise ReportRuntimeError("the report writers are not composed as in the program: " + "; ".join(wrong))


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _target(folder: Path, stem: str, stamp: str, suffix: str) -> Path:
    path = folder / f"{stem}_{stamp}{suffix}"
    index = 2
    while path.exists():  # never replace an existing file
        path = folder / f"{stem}_{stamp}_{index}{suffix}"
        index += 1
    return path


def _atomic(destination: Path, write) -> Path:
    """Write to a temporary file in the destination folder, then rename it into place."""
    handle, temporary = tempfile.mkstemp(prefix=".~report_", suffix=destination.suffix, dir=destination.parent)
    os.close(handle)
    try:
        write(Path(temporary))
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    return destination


def _folder(folder) -> Path:
    folder = Path(folder)
    if not folder.is_dir():
        raise ExportRefused(f"{folder} is not an existing folder.")
    return folder


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def confirmed_sources(fe_preview, experimental_preview, sources: Optional[dict], cancel=None) -> tuple:
    """(FE identity, experimental identity) recorded at the read and unchanged on disk now; else ``ExportRefused``."""
    from new_gui import preview_model as pm

    from services import fe_package_identity as fpi

    sources = dict(sources or {})
    confirmed = []
    for key, path in (("fe", fe_preview.manifest_path), ("experimental", experimental_preview.source_path)):
        read = sources.get(key)
        name = "FE manifest" if key == "fe" else "experimental file"
        if read is None:
            raise ExportRefused(f"the {name}'s identity was not recorded when it was read, so the report's provenance "
                                "cannot be confirmed; Inspect the file again.")
        if key == "fe":  # PLATE-ONLY-R2-F1: the whole extracted package, file by file
            try:
                pm.confirm_fe_identity(path, read, cancel)
            except (fpi.PackageChanged, fpi.PackageIdentityRefused) as refusal:
                raise ExportRefused(f"{refusal}; the report is not written for data that no longer match the files. "
                                    "Inspect it again.") from refusal
            confirmed.append({**read, "unchanged_at_export": True})
            continue
        now = pm.file_identity(path, cancel)
        if now is None or now["sha256"] != read["sha256"] or now["size"] != read["size"]:
            raise ExportRefused(f"the {name} {path} changed since it was read (SHA-256 {read['sha256'][:12]}… when "
                                "read); the report is not written for data that no longer match the file. Inspect "
                                "it again.")
        confirmed.append({**read, "unchanged_at_export": True})
    return tuple(confirmed)


def verified_record(result, bound, view, fe_preview, experimental_preview, set_index: int, fe_file: dict,
                    experimental_file: dict) -> dict:
    """The JSON record of a verified comparison; every value is the result's, the service's or the files'."""
    from new_gui import comparison_model as cm
    from new_gui import diagnostic_model as dm

    positions = {record.number: position + 1
                 for position, record in enumerate(experimental_preview.sets[set_index].records)}
    pairs = [{
        "fe_mode": int(pair.abaqus_mode), "fe_frequency_hz": float(pair.abaqus_frequency_hz),
        "experimental_record": positions.get(pair.experimental_mode), "experimental_mode": int(pair.experimental_mode),
        "experimental_frequency_hz": float(pair.experimental_frequency_hz),
        "signed_frequency_error_percent": float(pair.frequency_error_percent),
        "mac": _number(pair.mac), "mac_status": "COMPUTED" if pair.mac is not None else cm.MAC_NOT_COMPUTED,
        "comparator_status": str(pair.status), "order_changed": bool(pair.order_changed),
        "measured_dof_count": getattr(pair, "measured_dof_count", None),
        "dof_coverage_fraction": _number(getattr(pair, "dof_coverage_fraction", None)),
        "mapped_points": int(pair.mapped_points), "auto_id_use": cm.AUTO_ID_USE,
    } for pair in result.pairs]
    return {
        "schema": SCHEMA, "created": datetime.now().isoformat(timespec="seconds"),
        "status": view.status, "statement": view.statement,
        "fe_source": {**fe_file, "kind": "extracted FE package (manifest.json); the ODB itself was not read",
                      "identity_basis": "SHA-256 of manifest.json and of every geometry and mode file the loader "
                                        "read, recorded when they were read and unchanged at export; not the ODB's "
                                        "hash"},
        "experimental_source": {**experimental_file, "selected_path": str(experimental_preview.selected_path),
                                "identity_basis": "SHA-256 recorded when it was read, equal to the file the "
                                                  "registration was verified on, unchanged at export"},
        "modal_set": {"index": set_index + 1, "title": dm.set_title(experimental_preview, set_index),
                      "key": (experimental_preview.sets[set_index].dataset.metadata or {}).get("modal_set_key")},
        "registration": bound.provenance(),
        "comparator": "modal_core.compare_modal_datasets (reviewed quality-control facade) with frozen_registration",
        "diagnostic_state": result.diagnostic_state,
        "frequency_error_sign": dm.SIGN_NOTE,
        "pairs": pairs,
        "mac_matrix": {"fe_modes": list(view.mac_fe_modes), "experimental_modes": list(view.mac_experimental_modes),
                       "values": [[_number(v) for v in row] for row in result.mac_matrix]},
        "unmatched_fe_modes": list((result.abaqus.metadata or {}).get("unmatched_abaqus_modes") or []),
        "unmatched_experimental_candidates": list((result.abaqus.metadata or {}).get(
            "unmatched_experimental_candidates") or []),
        "admissibility_gates": dict((result.metadata or {}).get("admissibility_gates") or {}),
        "warnings": list(result.warnings),
        "suitability": {"pairs": "numerical assignment by the comparator's unchanged admissibility gates",
                        "auto_id": cm.AUTO_ID_NOTE, "material_property": "none identified or implied"},
        "engineering_target": cm.ENGINEERING_TARGET,
        "limits": list(view.limits),
        "generated_by": GENERATOR,
    }


def comparison_statement(result, bound, view, experimental_preview, set_index: int, basis: str, status: str = "",
                         statement: str = "", notes=(), verdicts: Optional[dict] = None) -> dict:
    """What the report says about the registration and every record; values of the result, the view and the analysis.

    ``verdicts`` maps an experimental mode number to the verdict the analysis showed for it. Nothing is derived here: a
    record without a stated verdict is reported as having none."""
    from new_gui import comparison_model as cm

    if basis not in BASIS_TEXT:
        raise ExportRefused("the registration the comparison rests on is not stated, so the report cannot name it; "
                            "Analyze again.")
    verdicts = dict(verdicts or {})
    records = list(experimental_preview.sets[set_index].records)
    positions = {record.number: position + 1 for position, record in enumerate(records)}
    shown = {row.index: row.cells for row in view.pair_rows}
    pairs = []
    for index, pair in enumerate(result.pairs):
        cells = shown.get(index)
        pairs.append({
            "fe_mode": int(pair.abaqus_mode), "fe_frequency_hz": float(pair.abaqus_frequency_hz),
            "experimental_record": positions.get(pair.experimental_mode),
            "experimental_mode": int(pair.experimental_mode),
            "experimental_frequency_hz": float(pair.experimental_frequency_hz),
            "signed_frequency_error_percent": float(pair.frequency_error_percent), "mac": _number(pair.mac),
            "comparator_status": str(pair.status), "close_modes": cells[12] if cells else cm.DASH,
            "verdict": verdicts.get(int(pair.experimental_mode)) or (cells[14] if cells else cm.DASH)})
    paired = {int(pair.experimental_mode) for pair in result.pairs}
    without = [{"experimental_record": positions.get(record.number), "experimental_mode": int(record.number),
                "experimental_frequency_hz": float(record.frequency_hz),
                "verdict": verdicts.get(int(record.number)) or cm.DASH}
               for record in records if int(record.number) not in paired]
    return {"registration_basis": basis, "registration_basis_statement": BASIS_TEXT[basis],
            "physical_mode_identity": IDENTITY_NOT_CLAIMED, "status": status or view.status,
            "statement": statement or view.statement, "registration": dict(bound.provenance()), "pairs": pairs,
            "records_without_a_pair": without, "close_mode_groups": [str(line) for line in view.close_groups],
            "verdict_note": cm.VERDICT_NOTE, "warnings": [str(w) for w in result.warnings],
            "notes": [str(note) for note in notes]}


def _text(value) -> str:
    if isinstance(value, (list, tuple)):
        return "; ".join(str(item) for item in value)
    return "" if value is None else str(value)


def statement_rows(section: dict) -> list:
    """The statement as rows (the Excel sheet as it is written; the PDF pages word the same rows)."""
    rows = [(STATEMENT_TITLE,), ("Status", section["status"]), ("Statement", section["statement"]),
            ("Registration basis", section["registration_basis"]), ("", section["registration_basis_statement"]),
            ("Physical mode identity", section["physical_mode_identity"]), (), ("Registration provenance",)]
    rows += [(str(key).replace("_", " "), _text(value)) for key, value in section["registration"].items()]
    rows += [(), ("Mode pairs (the comparator's assignment)",), PAIR_TITLES]
    rows += [(pair["fe_mode"], pair["fe_frequency_hz"], pair["experimental_record"], pair["experimental_mode"],
              pair["experimental_frequency_hz"], pair["signed_frequency_error_percent"], pair["mac"],
              pair["comparator_status"], pair["close_modes"], pair["verdict"]) for pair in section["pairs"]]
    if not section["pairs"]:
        rows.append(("none",))
    rows += [("", section["verdict_note"]), (), ("Experimental records without a pair",), RECORD_TITLES]
    rows += [(record["experimental_record"], record["experimental_mode"], record["experimental_frequency_hz"],
              record["verdict"]) for record in section["records_without_a_pair"]] or [("none",)]
    rows += [(), ("Close mode groups",)] + [("", line) for line in section["close_mode_groups"] or ["none recorded"]]
    rows += [(), ("Warnings of the comparison",)] + [("", line) for line in section["warnings"] or ["none"]]
    rows += [(), ("Notes of the analysis",)] + [("", line) for line in section["notes"] or ["none"]]
    return rows


def _add_statement_sheet(path: Path, section: dict) -> None:
    """Put the statement in front of the comparison workbook the program's writer made; its sheets are not changed."""
    from openpyxl import load_workbook

    workbook = load_workbook(path)
    sheet = workbook.create_sheet(STATEMENT_SHEET, 0)
    for row in statement_rows(section):
        sheet.append(list(row))
    sheet.column_dimensions["A"].width = 30
    sheet.column_dimensions["B"].width = 60
    workbook.active = 0
    workbook.save(path)
    workbook.close()


def _statement_lines(section: dict) -> list:
    import textwrap

    def number(value, form):
        return "not computed" if value is None else format(value, form)

    lines = []
    for row in statement_rows(section):
        if tuple(row) in (PAIR_TITLES, RECORD_TITLES):
            continue
        if len(row) == len(PAIR_TITLES):
            parts = [f"FE mode {row[0]} ({number(row[1], '.4f')} Hz) - EXP record {row[2]}, mode {row[3]} "
                     f"({number(row[4], '.4f')} Hz): error {number(row[5], '+.2f')} %, MAC {number(row[6], '.3f')}, "
                     f"{row[7]}; close modes: {row[8]}", f"    Verdict: {row[9]}"]
        elif len(row) == len(RECORD_TITLES):
            parts = [f"EXP record {row[0]}, mode {row[1]} ({number(row[2], '.4f')} Hz)", f"    Verdict: {row[3]}"]
        else:
            parts = [": ".join(str(cell) for cell in row if str(cell))]
        for part in parts:
            indent = "    " if part.startswith("    ") else ""
            lines += textwrap.wrap(part, 108, subsequent_indent=indent + "  ") or [""]
    return lines


def _add_statement_pages(path: Path, section: dict, per_page: int = 74) -> None:
    """Put the statement on the first pages of the comparison PDF the program's writer made; its pages follow unchanged."""
    import matplotlib
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.figure import Figure
    from pypdf import PdfReader, PdfWriter

    lines = _statement_lines(section)
    handle, front = tempfile.mkstemp(prefix=".~report_front_", suffix=".pdf", dir=path.parent)
    os.close(handle)
    try:
        with matplotlib.rc_context({"pdf.fonttype": 42}), PdfPages(front) as pdf:  # text that can be read back
            for start in range(0, len(lines), per_page):
                figure = Figure(figsize=(8.27, 11.69))
                figure.text(0.06, 0.965, chr(10).join(lines[start:start + per_page]), va="top", ha="left",
                            fontsize=7.5, linespacing=1.25)
                pdf.savefig(figure)
        writer = PdfWriter()
        with open(front, "rb") as first, open(path, "rb") as second:
            for stream in (first, second):
                for page in PdfReader(stream).pages:
                    writer.add_page(page)
            merged = path.with_name(Path(front).name + ".merged")
            try:
                with open(merged, "wb") as out:
                    writer.write(out)
            except BaseException:
                if merged.exists():
                    merged.unlink()
                raise
        os.replace(merged, path)
    finally:
        if os.path.exists(front):
            os.remove(front)


def export_verified(result, bound, view, fe_preview, experimental_preview, set_index: int, folder,
                    cancel=None, sources: Optional[dict] = None, basis: str = "", status: str = "",
                    statement: str = "", notes=(), verdicts: Optional[dict] = None) -> tuple:
    """Write the comparison report (xlsx, pdf) and its JSON record into ``folder``; returns the written paths.

    With ``basis`` (``ARCHIVED_BASIS`` or ``CONFIRMED_BASIS``) the registration and verdict statement of
    ``comparison_statement`` stands first in each of the three files."""
    folder = _folder(folder)
    with _EXPORT:
        fe_file, experimental_file = confirmed_sources(fe_preview, experimental_preview, sources, cancel)
        section = (comparison_statement(result, bound, view, experimental_preview, set_index, basis, status, statement,
                                        notes, verdicts) if basis else None)
        if experimental_file["sha256"] != bound.provenance()["experimental_sha256"]:
            raise ExportRefused("the experimental file is not the one the comparison verified (SHA-256 "
                                f"{str(experimental_file['sha256'])[:12]}… when read); run the comparison again.")
        ensure_application_reporting()
        import reporting

        stamp, written = _stamp(), []
        images = Path(tempfile.mkdtemp(prefix="new_gui_report_images_"))
        try:
            for suffix, writer, front in ((".xlsx", reporting.export_excel, _add_statement_sheet),
                                          (".pdf", reporting.export_pdf, _add_statement_pages)):
                target = _target(folder, VERIFIED_STEM, stamp, suffix)

                def write(path, w=writer, f=front):
                    w(result, path, images)
                    if section is not None:
                        f(path, section)

                written.append(_atomic(target, write))
        finally:
            shutil.rmtree(images, ignore_errors=True)
        record = verified_record(result, bound, view, fe_preview, experimental_preview, set_index, fe_file,
                                 experimental_file)
        if section is not None:  # the statement the other two files open with, and the verdict beside every pair
            record.update({"status": section["status"], "statement": section["statement"],
                           "registration_basis": section["registration_basis"],
                           "registration_basis_statement": section["registration_basis_statement"],
                           "physical_mode_identity": section["physical_mode_identity"],
                           "records_without_a_pair": section["records_without_a_pair"],
                           "close_mode_groups": section["close_mode_groups"], "verdict_note": section["verdict_note"],
                           "notes": section["notes"]})
            for pair, stated in zip(record["pairs"], section["pairs"]):
                pair.update({"close_modes": stated["close_modes"], "verdict": stated["verdict"]})
        record["files"] = [path.name for path in written]
        target = _target(folder, VERIFIED_STEM, stamp, ".json")
        written.append(_atomic(target, lambda path: path.write_text(json.dumps(record, indent=2, ensure_ascii=False,
                                                                               default=str), encoding="utf-8")))
        return tuple(written)


def export_diagnostic(fe_preview, experimental_preview, set_index: int, diagnostic, registration_reason: str,
                      folder, cancel=None, sources: Optional[dict] = None, statement: str = "") -> tuple:
    """Write the CORE-E2E-D diagnostic report (pdf, xlsx) of the frequency diagnostic shown; no MAC, no pair.

    ``statement`` (ABM-PLATE-EXPORT-1) is put in front of the report's own reason, so the caller's status words stand
    first under "Why the analysis is diagnostic"; nothing else of the report is changed."""
    from services import diagnostic_report as dr
    from services.modal_data_viewer import NOT_ESTABLISHED, LoadedModalData

    folder = _folder(folder)
    if diagnostic is None:
        raise ExportRefused("run the frequency diagnostic first: the diagnostic report states its result.")
    with _EXPORT:
        confirmed_sources(fe_preview, experimental_preview, sources, cancel)  # the report hashes the files again
        loaded = LoadedModalData(abaqus=fe_preview.dataset, experimental=experimental_preview.sets[set_index].dataset,
                                 registration=NOT_ESTABLISHED, reason=registration_reason,
                                 frequency_diagnostic=diagnostic, abaqus_path=Path(fe_preview.manifest_path),
                                 experimental_path=Path(experimental_preview.source_path))
        report = dr.build_diagnostic_report(loaded, cancel=cancel)
        if statement:
            report = replace(report, reason=f"{statement} {report.reason}")
        stamp = _stamp()
        written = []
        for suffix, writer in ((".pdf", dr.write_diagnostic_pdf), (".xlsx", dr.write_diagnostic_xlsx)):
            written.append(writer(report, _target(folder, DIAGNOSTIC_STEM, stamp, suffix)))  # their own atomic write
        return tuple(Path(path) for path in written)


__all__ = ["ARCHIVED_BASIS", "BASIS_TEXT", "CONFIRMED_BASIS", "IDENTITY_NOT_CLAIMED", "STATEMENT_SHEET",
           "comparison_statement", "statement_rows", "EXPORT", "ExportRefused", "confirmed_sources", "FINAL_OWNERS", "REPORT_LAYERS", "ReportRuntimeError",
           "ensure_application_reporting", "export_diagnostic", "export_verified", "verified_record"]
