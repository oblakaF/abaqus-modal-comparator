from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from app import APP_TITLE
from services import local_input_registry as registry


_INSTALLED = False
ABOUT_TEXT = (
    f"{APP_TITLE}\n\n"
    "Compares Abaqus modal results with Siemens LMS / Simcenter Testlab "
    "measurements: mode matching, MAC/AutoMAC/COMAC, FRF and quality-control "
    "diagnostics, and Excel/PDF reports.\n\n"
    "Press F1 or use Help > Help topics for a searchable description of every "
    "tab in this window."
)


def _guarded(self, ready_message: str, action) -> None:
    if self.result is None and getattr(self, "_diagnostic_export_source", None) is not None:
        action()  # CORE-E2E-D: the diagnostic report of a frequency-only / FE-only analysis
        return
    if self.result is None or self.cache is None:
        messagebox.showinfo("Not ready yet", ready_message)
        return
    action()


def _export_excel_from_menu(self) -> None:
    _guarded(
        self,
        "Run the analysis on the \"Files and analysis\" tab first, then export the report.",
        self._excel,
    )


def _export_pdf_from_menu(self) -> None:
    _guarded(
        self,
        "Run the analysis on the \"Files and analysis\" tab first, then export the report.",
        self._pdf,
    )


def _show_about(self) -> None:
    messagebox.showinfo(APP_TITLE, ABOUT_TEXT)


def _exit_app(self) -> None:
    # Route through the same handler as the window's close ("X") button so
    # File > Exit also saves the last-session file, instead of silently
    # skipping it by destroying the root window directly.
    close_handler = getattr(self, "_close_with_session_save", None)
    if callable(close_handler):
        close_handler()
    else:
        self.root.destroy()


class InputRegistryDialog:
    """File > Input file registry...: the user's own FE / experimental file references (APP-DATA.1).

    Use fills the matching field of 1. Files exactly as choosing the file there does (the variable the Browse button
    sets), so the existing reactions apply: a changed input clears the shown result, the modal sets of an experimental
    file are discovered. Nothing is loaded, compared or run, and FE and experimental entries are never paired.
    """

    def __init__(self, application, store=None) -> None:
        self.app = application
        self.store = Path(store or getattr(application, "local_input_registry_store", None) or registry.default_store())
        self.entries: dict[str, dict] = {}
        window = self.window = tk.Toplevel(application.root)
        window.title("Input file registry")
        window.transient(application.root)
        window.minsize(720, 360)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)
        ttk.Label(window, text=registry.NOTE, wraplength=760, justify="left").grid(
            row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        table = ttk.Frame(window)
        table.grid(row=1, column=0, sticky="nsew", padx=12)
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=("kind", "label", "state", "path"), show="headings",
                                 selectmode="browse", height=8)
        for column, title, width, stretch in (("kind", "Kind", 130, False), ("label", "Name", 200, False),
                                              ("state", "File", 70, False), ("path", "Path", 380, True)):
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, stretch=stretch)
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<Double-1>", lambda _event: self.use_selected())
        self.message = tk.StringVar(value="")
        ttk.Label(window, textvariable=self.message, wraplength=760, justify="left").grid(
            row=2, column=0, sticky="ew", padx=12, pady=6)
        buttons = ttk.Frame(window)
        buttons.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 12))
        self.add_fe_button = ttk.Button(buttons, text="Add FE file...", command=lambda: self.add(registry.FE))
        self.add_experimental_button = ttk.Button(buttons, text="Add experimental file...",
                                                  command=lambda: self.add(registry.EXPERIMENTAL))
        self.use_button = ttk.Button(buttons, text="Use in 1. Files", command=self.use_selected)
        self.remove_button = ttk.Button(buttons, text="Remove from registry", command=self.remove_selected)
        for column, button in enumerate((self.add_fe_button, self.add_experimental_button, self.use_button,
                                         self.remove_button)):
            button.grid(row=0, column=column, padx=(0, 6))
        ttk.Button(buttons, text="Close", command=window.destroy).grid(row=0, column=5, sticky="e")
        buttons.columnconfigure(4, weight=1)
        self.refresh()

    def _set_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for button in (self.add_fe_button, self.add_experimental_button, self.use_button, self.remove_button):
            button.configure(state=state)

    def refresh(self, select: str = "") -> bool:
        self.tree.delete(*self.tree.get_children())
        self.entries = {}
        try:
            entries = registry.list_entries(self.store)
        except registry.RegistryError as error:
            self._set_enabled(False)
            self.message.set(str(error))
            return False
        self._set_enabled(True)
        for entry in entries:
            self.entries[entry["id"]] = entry
            self.tree.insert("", "end", iid=entry["id"], values=(
                registry.KIND_TEXT[entry["kind"]], entry["label"], registry.entry_state(entry), entry["path"]))
        if select in self.entries:
            self.tree.selection_set(select)
            self.tree.see(select)
        if not entries:
            self.message.set("No entries yet. Add an FE or experimental file you use.")
        return True

    def selected(self):
        selection = self.tree.selection()
        entry = self.entries.get(selection[0]) if selection else None
        if entry is None:
            self.message.set("Select an entry first.")
        return entry

    def add(self, kind: str) -> None:
        what = "FE result (Abaqus ODB or extracted manifest.json)" if kind == registry.FE else \
            "experimental result (UNV / UFF, or LMS with its UNV / UFF beside it)"
        path = filedialog.askopenfilename(parent=self.window, title=f"Add {what}", filetypes=registry.FILETYPES[kind])
        if not path:
            return
        label = simpledialog.askstring("Name of the entry", "A name you will recognise (the file is not renamed):",
                                       initialvalue=Path(path).name, parent=self.window)
        if label is None:
            return
        try:
            entry, added = registry.add_entry(self.store, kind, path, label)
        except registry.RegistryError as error:
            messagebox.showerror("Input file registry", f"{error}\n\nNothing was added.", parent=self.window)
            self.refresh()
            return
        self.refresh(select=entry["id"])
        self.message.set(f"Added '{entry['label']}'." if added else
                         f"This file is already in the registry as '{entry['label']}'; nothing was changed.")

    def use_selected(self) -> None:
        entry = self.selected()
        if entry is None:
            return
        try:
            path = registry.usable_path(entry)
        except registry.RegistryError as error:
            messagebox.showwarning("Input file registry", f"{error}\n\nThe field on 1. Files is left unchanged.",
                                   parent=self.window)
            self.refresh(select=entry["id"])
            return
        if entry["kind"] == registry.FE:
            variable, field = self.app.abaqus_path, "Abaqus results"
        else:
            variable, field = self.app.experimental_path, "Experimental results"
        variable.set(str(path))  # what the Browse button of that field does; the existing traces react to it
        self.app.tabs.select(self.app.input_tab)
        self.message.set(f"'{entry['label']}' is now the {field} file on 1. Files. Nothing was loaded or run; "
                         "check the other inputs and press Run when ready.")

    def remove_selected(self) -> None:
        entry = self.selected()
        if entry is None:
            return
        if not messagebox.askyesno("Input file registry", f"Remove '{entry['label']}' from the registry?\n\nOnly the "
                                   "reference is removed; the file itself is not touched.", parent=self.window):
            return
        try:
            registry.remove_entry(self.store, entry["id"])
        except registry.RegistryError as error:
            messagebox.showerror("Input file registry", str(error), parent=self.window)
            self.refresh()
            return
        self.refresh()
        self.message.set(f"Removed '{entry['label']}' from the registry; the file was not touched.")


def _open_input_registry(self) -> None:
    InputRegistryDialog(self)


def _build_menu(self) -> None:
    menu_bar = tk.Menu(self.root)

    file_menu = tk.Menu(menu_bar, tearoff=False)
    file_menu.add_command(label="New project", command=self._new_project)
    file_menu.add_command(label="Open project...", accelerator="Ctrl+O", command=self._open_project)
    file_menu.add_command(label="Save project", accelerator="Ctrl+S", command=self._save_project)
    file_menu.add_command(label="Save project as...", command=self._save_project_as)
    file_menu.add_separator()
    file_menu.add_command(label="Input file registry...", command=lambda: _open_input_registry(self))
    file_menu.add_separator()
    file_menu.add_command(label="Open output folder", command=self._open_workspace)
    file_menu.add_separator()
    file_menu.add_command(label="Exit", command=lambda: _exit_app(self))
    menu_bar.add_cascade(label="File", menu=file_menu)

    reports_menu = tk.Menu(menu_bar, tearoff=False)
    reports_menu.add_command(
        label="Export Excel report...",
        command=lambda: _export_excel_from_menu(self),
    )
    reports_menu.add_command(
        label="Export PDF report...",
        command=lambda: _export_pdf_from_menu(self),
    )
    menu_bar.add_cascade(label="Reports", menu=reports_menu)

    help_menu = tk.Menu(menu_bar, tearoff=False)
    help_menu.add_command(label="Help topics", accelerator="F1", command=lambda: self._open_help())
    help_menu.add_separator()
    help_menu.add_command(label="About", command=lambda: _show_about(self))
    menu_bar.add_cascade(label="Help", menu=help_menu)

    self.root.configure(menu=menu_bar)
    self.menu_bar = menu_bar

    self.root.bind_all("<Control-o>", lambda _event: self._open_project())
    self.root.bind_all("<Control-s>", lambda _event: self._save_project())


def install_menu_ui(app_module) -> None:
    """Add a top File/Reports/Help menu bar over the project-file and export
    actions that already exist as in-tab buttons, so they stay reachable from
    any tab instead of only from "Files and analysis"."""
    global _INSTALLED
    if _INSTALLED:
        return

    application_class = app_module.ModalComparatorApp
    original_init = application_class.__init__

    def menu_init(self, root) -> None:
        original_init(self, root)
        _build_menu(self)

    application_class.__init__ = menu_init
    _INSTALLED = True
