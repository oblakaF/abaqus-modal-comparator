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

Files are written only into the folder the user chose, with time-stamped names (nothing is replaced), each through a
temporary file in that folder that is renamed into place. The read data, the source files and the project's records
are never written.
"""

from __future__ import annotations

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


def export_verified(result, bound, view, fe_preview, experimental_preview, set_index: int, folder,
                    cancel=None, sources: Optional[dict] = None) -> tuple:
    """Write the comparison report (xlsx, pdf) and its JSON record into ``folder``; returns the written paths."""
    folder = _folder(folder)
    with _EXPORT:
        fe_file, experimental_file = confirmed_sources(fe_preview, experimental_preview, sources, cancel)
        if experimental_file["sha256"] != bound.experimental["sha256"]:
            raise ExportRefused("the experimental file is not the one the comparison verified (SHA-256 "
                                f"{str(experimental_file['sha256'])[:12]}… when read); run the comparison again.")
        ensure_application_reporting()
        import reporting

        stamp, written = _stamp(), []
        images = Path(tempfile.mkdtemp(prefix="new_gui_report_images_"))
        try:
            for suffix, writer in ((".xlsx", reporting.export_excel), (".pdf", reporting.export_pdf)):
                target = _target(folder, VERIFIED_STEM, stamp, suffix)
                written.append(_atomic(target, lambda path, w=writer: w(result, path, images)))
        finally:
            shutil.rmtree(images, ignore_errors=True)
        record = verified_record(result, bound, view, fe_preview, experimental_preview, set_index, fe_file,
                                 experimental_file)
        record["files"] = [path.name for path in written]
        target = _target(folder, VERIFIED_STEM, stamp, ".json")
        written.append(_atomic(target, lambda path: path.write_text(json.dumps(record, indent=2, ensure_ascii=False,
                                                                               default=str), encoding="utf-8")))
        return tuple(written)


def export_diagnostic(fe_preview, experimental_preview, set_index: int, diagnostic, registration_reason: str,
                      folder, cancel=None, sources: Optional[dict] = None) -> tuple:
    """Write the CORE-E2E-D diagnostic report (pdf, xlsx) of the frequency diagnostic shown; no MAC, no pair."""
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
        stamp = _stamp()
        written = []
        for suffix, writer in ((".pdf", dr.write_diagnostic_pdf), (".xlsx", dr.write_diagnostic_xlsx)):
            written.append(writer(report, _target(folder, DIAGNOSTIC_STEM, stamp, suffix)))  # their own atomic write
        return tuple(Path(path) for path in written)


__all__ = ["EXPORT", "ExportRefused", "confirmed_sources", "FINAL_OWNERS", "REPORT_LAYERS", "ReportRuntimeError",
           "ensure_application_reporting", "export_diagnostic", "export_verified", "verified_record"]
