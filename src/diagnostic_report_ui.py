"""Export PDF / Excel report buttons for a diagnostic analysis (CORE-E2E-D; the logic is services.diagnostic_report).

With an established comparison the buttons export the comparison report exactly as before. When the analysis ended as
a diagnostic (``FREQUENCY_ONLY_DIAGNOSTIC`` or an unusable experimental file) the same buttons, relabelled, export the
diagnostic report of the loaded data. The report describes the analysis shown when the export starts (a snapshot);
a new analysis never changes a report being written.
"""

from __future__ import annotations

from pathlib import Path
import threading
from tkinter import filedialog, messagebox
from typing import Optional

from services import diagnostic_report as report_service
from services import report_directory

KINDS = {"pdf": (".pdf", "PDF document", "Save diagnostic PDF report", "modal_diagnostic_report.pdf",
                 report_service.write_diagnostic_pdf),
         "xlsx": (".xlsx", "Excel workbook", "Save diagnostic Excel report", "modal_diagnostic_report.xlsx",
                  report_service.write_diagnostic_xlsx)}
NORMAL_TEXT = {"excel_button": "Export Excel report", "pdf_button": "Export PDF report"}
DIAGNOSTIC_TEXT = {"excel_button": "Export diagnostic Excel", "pdf_button": "Export diagnostic PDF"}


def _buttons(app):
    return [(name, getattr(app, name, None)) for name in NORMAL_TEXT if getattr(app, name, None) is not None]


def disable_report_export(app) -> None:
    """A new analysis starts: no report of the previous one is offered."""
    app._diagnostic_export_source = None
    for name, button in _buttons(app):
        button.configure(state="disabled", text=NORMAL_TEXT[name])


def restore_comparison_export(app) -> None:
    app._diagnostic_export_source = None
    for name, button in _buttons(app):
        button.configure(text=NORMAL_TEXT[name])


def enable_diagnostic_export(app, loaded) -> None:
    """The analysis ended as a diagnostic with loaded data: offer the diagnostic report of exactly those data."""
    if loaded is None or getattr(loaded, "abaqus", None) is None:
        return
    app._diagnostic_export_source = loaded
    for name, button in _buttons(app):
        button.configure(state="normal", text=DIAGNOSTIC_TEXT[name])


def _destination(kind: str) -> Optional[Path]:
    suffix, label, title, initial, _ = KINDS[kind]
    chosen = filedialog.asksaveasfilename(title=title, defaultextension=suffix, initialfile=initial,
                                          filetypes=[(label, f"*{suffix}")], **report_directory.save_dialog_options())
    if not chosen:
        return None  # cancelled
    path = Path(chosen)
    if path.suffix.lower() != suffix:
        path = path.with_name(path.name + suffix)  # a typed other extension never yields a mislabelled file
        if path.exists() and not messagebox.askyesno(title, f"{path.name} already exists. Replace it?"):
            return None
    return path


def _images(app, loaded) -> list[tuple[Path, str]]:
    viewer = getattr(app, "mode_viewer", None)
    if viewer is None or getattr(viewer, "loaded", None) is not loaded:
        return []
    images = []
    for pane, role in ((viewer.fe, "FE mode on its own FE nodes"),
                       (viewer.experimental, "experimental record on its own measured points")):
        path = getattr(pane, "image_path", None)
        if path is not None and Path(path).exists():
            images.append((Path(path), f"Separate view ({role}): {pane.choice.get()}. Not overlaid, not paired, no "
                                       "MAC: the physical registration is not established."))
    return images


def export_report(app, kind: str) -> None:
    """Export PDF / Excel report for a diagnostic analysis (the comparison export is handled by the caller)."""
    loaded = getattr(app, "_diagnostic_export_source", None)
    if loaded is None:
        messagebox.showinfo("Not ready yet", "Run the analysis first; then export the report.")
        return
    if getattr(app, "_diagnostic_export_running", False):
        messagebox.showinfo("Export running", "A diagnostic report is being written; wait until it is saved.")
        return
    destination = _destination(kind)
    if destination is None:
        return
    images = _images(app, loaded)
    writer = KINDS[kind][4]
    app._diagnostic_export_running = True
    app.status.set(f"Writing the diagnostic report {destination.name}...")

    def finished(error: Optional[Exception]) -> None:
        app._diagnostic_export_running = False
        if error is not None:
            app.status.set("The diagnostic report was not written.")
            messagebox.showerror("Export failed", str(error))
            return
        note = ""
        if getattr(app, "_diagnostic_export_source", None) is not loaded:
            note = ("\n\nA new analysis was started meanwhile; this report describes the analysis shown when the "
                    "export started (its files and identities are listed in the report).")
        app.status.set(f"Diagnostic report saved: {destination}")
        messagebox.showinfo("Report saved", f"{destination}{note}")

    def work() -> None:
        try:
            report = report_service.build_diagnostic_report(loaded, images=images)
            writer(report, destination)
        except Exception as error:  # noqa: BLE001  (shown to the user; nothing is reported as saved)
            post(lambda error=error: finished(error))
            return
        post(lambda: finished(None))

    def post(callback) -> None:
        poster = getattr(app, "_post_to_ui", None)
        if not (callable(poster) and poster(callback)):
            app.root.after(0, callback)

    threading.Thread(target=work, daemon=True).start()
