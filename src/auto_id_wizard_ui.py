"""Auto-ID setup page (M8.1): the specimen / family wizard inside the Effective Material Identification tab.

Rendering only.  Every fact comes from ``services.auto_id_wizard``, which loads the governed records through
the same parsers the CLI and backend use.  This page never starts Abaqus or an identification and never
edits a record.
"""

from __future__ import annotations

from pathlib import Path
from tkinter import BooleanVar, StringVar, filedialog, ttk
import tkinter as tk

from domain.experiment_fixture import fixture_roots_from_environment
from services.auto_id_wizard import (
    FamilyPreparation,
    ItemStatus,
    prepare_family,
    prepare_specimen_folder,
    wizard_rows,
    wizard_summary,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SCOPE_TEXT = (
    "Select a specimen folder (with its specimen.json passport) or a family / campaign definition. "
    "The wizard loads the governed records and shows what is present and exactly what is missing. "
    "It does not decide scientific validity, choose modes or a registration, change thresholds, fill in "
    "missing values or start Abaqus."
)
_STATUS_TAGS = {
    ItemStatus.PRESENT.value: "present",
    ItemStatus.INFO.value: "info",
    ItemStatus.UNAVAILABLE.value: "gap",
    ItemStatus.MISSING.value: "gap",
    ItemStatus.NOT_CONFIGURED.value: "gap",
    ItemStatus.NOT_FOUND.value: "gap",
    ItemStatus.MISMATCH.value: "error",
    ItemStatus.INVALID.value: "error",
}


def load_selection(kind: str, path: str):
    """Prepare the selected source with the configured data stores (no Abaqus, no identification)."""

    roots = fixture_roots_from_environment()
    if kind == "family":
        return prepare_family(Path(path), REPO_ROOT, roots)
    return prepare_specimen_folder(Path(path), REPO_ROOT, roots)


def build_auto_id_setup_page(app, page) -> None:
    app.auto_id_preparation = None
    app.auto_id_source_kind = StringVar(value="specimen")
    app.auto_id_source_path = StringVar(value="")
    app.auto_id_summary = StringVar(value="Nothing selected.")
    app.auto_id_show_details = BooleanVar(value=False)
    app.auto_id_specimen_choice = StringVar(value="")

    ttk.Label(page, text=SCOPE_TEXT, justify="left", wraplength=1100).pack(anchor="w")

    source = ttk.LabelFrame(page, text="Source", padding=10)
    source.pack(fill="x", pady=(10, 6))
    ttk.Radiobutton(source, text="Specimen folder", value="specimen",
                    variable=app.auto_id_source_kind).grid(row=0, column=0, sticky="w")
    ttk.Radiobutton(source, text="Family / campaign definition", value="family",
                    variable=app.auto_id_source_kind).grid(row=0, column=1, sticky="w", padx=(12, 0))
    ttk.Entry(source, textvariable=app.auto_id_source_path, width=90).grid(row=1, column=0, columnspan=2,
                                                                           sticky="we", pady=(6, 0))
    ttk.Button(source, text="Browse…", command=lambda: _browse(app)).grid(row=1, column=2, padx=(6, 0), pady=(6, 0))
    ttk.Button(source, text="Load", command=lambda: _load(app)).grid(row=1, column=3, padx=(6, 0), pady=(6, 0))
    source.columnconfigure(0, weight=1)

    ttk.Label(page, textvariable=app.auto_id_summary, justify="left", wraplength=1100,
              style="Title.TLabel").pack(anchor="w", pady=(4, 4))

    chooser = ttk.Frame(page)
    chooser.pack(fill="x")
    ttk.Label(chooser, text="Specimen:").pack(side="left")
    app.auto_id_specimen_box = ttk.Combobox(chooser, textvariable=app.auto_id_specimen_choice, state="disabled",
                                            width=40)
    app.auto_id_specimen_box.pack(side="left", padx=(6, 0))
    app.auto_id_specimen_box.bind("<<ComboboxSelected>>", lambda _e: _show(app))

    columns = ("section", "item", "value", "status")
    table = ttk.Treeview(page, columns=columns, show="headings", height=18)
    for key, heading, width in (("section", "Section", 170), ("item", "Item", 260), ("value", "Value", 460),
                                ("status", "Status", 130)):
        table.heading(key, text=heading)
        table.column(key, width=width, anchor="w")
    table.tag_configure("gap", foreground="#9a5b00")
    table.tag_configure("error", foreground="#b00020")
    table.tag_configure("info", foreground="#555555")
    table.pack(fill="both", expand=True, pady=(6, 6))
    table.bind("<<TreeviewSelect>>", lambda _e: _show_detail(app))
    app.auto_id_table = table

    ttk.Checkbutton(page, text="Show provenance details", variable=app.auto_id_show_details,
                    command=lambda: _show_detail(app)).pack(anchor="w")
    app.auto_id_detail = tk.Text(page, height=5, wrap="word")
    app.auto_id_items = ()


def _browse(app) -> None:
    if app.auto_id_source_kind.get() == "family":
        path = filedialog.askopenfilename(title="Family / campaign definition",
                                          filetypes=[("Campaign definition", "*.campaign.json"), ("JSON", "*.json")])
    else:
        path = filedialog.askdirectory(title="Specimen folder")
    if path:
        app.auto_id_source_path.set(path)
        _load(app)


def _load(app) -> None:
    path = app.auto_id_source_path.get().strip()
    if not path:
        app.auto_id_summary.set("Nothing selected.")
        return
    app.auto_id_preparation = load_selection(app.auto_id_source_kind.get(), path)
    app.auto_id_summary.set(wizard_summary(app.auto_id_preparation))
    preparation = app.auto_id_preparation
    if isinstance(preparation, FamilyPreparation) and preparation.specimens:
        app.auto_id_specimen_box.configure(values=["(campaign)"] + [s.label for s in preparation.specimens],
                                           state="readonly")
        app.auto_id_specimen_choice.set("(campaign)")
    else:
        app.auto_id_specimen_box.configure(values=[], state="disabled")
        app.auto_id_specimen_choice.set("")
    _show(app)


def _show(app) -> None:
    preparation = app.auto_id_preparation
    items = () if preparation is None else preparation.items
    if isinstance(preparation, FamilyPreparation):
        chosen = app.auto_id_specimen_choice.get()
        for specimen in preparation.specimens:
            if specimen.label == chosen:
                items = specimen.preparation.items
    app.auto_id_items = items
    table = app.auto_id_table
    table.delete(*table.get_children())
    for index, row in enumerate(wizard_rows(items)):
        table.insert("", "end", iid=str(index), values=row, tags=(_STATUS_TAGS.get(row[3], "info"),))
    _show_detail(app)


def _show_detail(app) -> None:
    detail = app.auto_id_detail
    if not app.auto_id_show_details.get():
        detail.pack_forget()
        return
    detail.pack(fill="x")
    selected = app.auto_id_table.selection()
    text = app.auto_id_items[int(selected[0])].detail if selected else "Select a row to see its provenance."
    detail.configure(state="normal")
    detail.delete("1.0", "end")
    detail.insert("1.0", text or "(no further detail)")
    detail.configure(state="disabled")
