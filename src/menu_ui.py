from __future__ import annotations

from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from app import APP_TITLE
from services import local_experimental_preview as experimental_preview
from services import local_fe_preview as fe_preview
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
        self.inspect_button = ttk.Button(buttons, text="Inspect FE modes...", command=self.inspect_selected)
        self.inspect_experimental_button = ttk.Button(buttons, text="Inspect experimental data...",
                                                      command=self.inspect_experimental_selected)
        self.remove_button = ttk.Button(buttons, text="Remove from registry", command=self.remove_selected)
        for column, button in enumerate((self.add_fe_button, self.add_experimental_button, self.use_button,
                                         self.inspect_button, self.inspect_experimental_button, self.remove_button)):
            button.grid(row=0, column=column, padx=(0, 6))
        ttk.Button(buttons, text="Close", command=window.destroy).grid(row=0, column=7, sticky="e")
        buttons.columnconfigure(6, weight=1)
        self.previews: list = []
        self.refresh()

    def _set_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for button in (self.add_fe_button, self.add_experimental_button, self.use_button, self.inspect_button,
                       self.inspect_experimental_button, self.remove_button):
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

    def inspect_selected(self):
        """Open a read-only view of the FE modes of the selected extracted package (APP-DATA.2)."""
        entry = self.selected()
        if entry is None:
            return None
        if entry["kind"] != registry.FE:
            self.message.set("Inspect FE modes works on an FE entry (an extracted manifest.json).")
            return None
        try:
            path = registry.usable_path(entry)
        except registry.RegistryError as error:
            messagebox.showwarning("Inspect FE modes", str(error), parent=self.window)
            self.refresh(select=entry["id"])
            return None
        if path.suffix.lower() == ".odb":
            messagebox.showinfo("Inspect FE modes", fe_preview.ODB_NEEDS_PACKAGE, parent=self.window)
            return None
        preview = FePreviewWindow(self.app.root, entry["label"], path)
        self.previews.append(preview)
        return preview

    def inspect_experimental_selected(self):
        """Open a read-only view of the experimental data of the selected UNV / UFF / LMS entry (APP-DATA.3)."""
        entry = self.selected()
        if entry is None:
            return None
        if entry["kind"] != registry.EXPERIMENTAL:
            self.message.set("Inspect experimental data works on an experimental entry (UNV / UFF / LMS).")
            return None
        try:
            path = registry.usable_path(entry)  # also refuses an LMS project without its companion UNV / UFF
        except registry.RegistryError as error:
            messagebox.showwarning("Inspect experimental data", str(error), parent=self.window)
            self.refresh(select=entry["id"])
            return None
        preview = ExperimentalPreviewWindow(self.app.root, entry["label"], path)
        self.previews.append(preview)
        return preview

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


def _read_fe_package(path, cancel: threading.Event, results: queue.Queue) -> None:
    """Worker of FePreviewWindow: reads the package and posts the outcome. It never touches a Tk object."""
    try:
        results.put(("ok", fe_preview.preview_fe_package(path, cancel_event=cancel)))
    except fe_preview.AnalysisCancelled:
        results.put(("cancelled", None))
    except fe_preview.FePreviewError as error:
        results.put(("error", str(error)))
    except Exception as error:  # noqa: BLE001  (any other failure is stated, the window never waits forever)
        results.put(("error", f"The extracted package cannot be read: {error}"))


class FePreviewWindow:
    """A read-only list of the FE modes that ``load_extracted_odb`` loads from one extracted package.

    The package is read on a background thread; the window polls for the outcome, so the main window stays usable.
    Closing the window cancels the reading and an outcome that arrives afterwards is discarded.
    """

    POLL_MS = 100

    def __init__(self, root, label: str, path: Path) -> None:
        self.path = Path(path)
        self.preview = None
        self.error = None
        self.closed = False
        self.cancel = threading.Event()
        self.results: queue.Queue = queue.Queue()
        window = self.window = tk.Toplevel(root)
        window.title(f"FE modes — {label}")
        window.minsize(640, 380)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(3, weight=1)
        window.protocol("WM_DELETE_WINDOW", self.close)
        ttk.Label(window, text=fe_preview.NOTE, wraplength=700, justify="left").grid(
            row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        self.source = tk.StringVar(value=f"Extracted package: {self.path}")
        ttk.Label(window, textvariable=self.source, wraplength=700, justify="left").grid(
            row=1, column=0, sticky="ew", padx=12)
        self.status = tk.StringVar(value="Reading the extracted package... The main window stays usable.")
        ttk.Label(window, textvariable=self.status, wraplength=700, justify="left").grid(
            row=2, column=0, sticky="ew", padx=12, pady=4)
        table = ttk.Frame(window)
        table.grid(row=3, column=0, sticky="nsew", padx=12)
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=("mode", "frequency", "source", "nodes"), show="headings", height=10)
        for column, title, width, stretch in (("mode", "FE mode", 70, False), ("frequency", "Frequency, Hz", 120, False),
                                              ("source", "Frequency source", 300, True), ("nodes", "Nodes", 80, False)):
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, stretch=stretch)
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.warnings = tk.Text(window, height=5, wrap="word")
        self.warnings.grid(row=4, column=0, sticky="ew", padx=12, pady=6)
        self.warnings.configure(state="disabled")
        ttk.Button(window, text="Close", command=self.close).grid(row=5, column=0, sticky="e", padx=12, pady=(0, 12))
        self.thread = threading.Thread(target=_read_fe_package, args=(self.path, self.cancel, self.results),
                                       daemon=True, name="fe-preview")
        self.thread.start()
        self._job = window.after(self.POLL_MS, self._poll)

    def _poll(self) -> None:
        self._job = None
        if self.closed or not self.window.winfo_exists():  # closed, or destroyed with its parent
            self.closed = True
            self.cancel.set()
            return
        try:
            kind, value = self.results.get_nowait()
        except queue.Empty:
            self._job = self.window.after(self.POLL_MS, self._poll)
            return
        self._show(kind, value)

    def _set_warnings(self, lines) -> None:
        self.warnings.configure(state="normal")
        self.warnings.delete("1.0", "end")
        self.warnings.insert("1.0", "\n".join(lines) if lines else "No diagnostic messages from the loader.")
        self.warnings.configure(state="disabled")

    def _show(self, kind: str, value) -> None:
        if kind == "ok":
            self.preview = value
            self.source.set(f"FE source: {value.fe_source}\nExtracted package: {value.manifest_path}"
                            + (f"\nStep: {value.step_name}" if value.step_name else ""))
            for mode in value.modes:
                self.tree.insert("", "end", values=(mode.number, fe_preview.frequency_text(mode),
                                                    fe_preview.source_text(mode), mode.node_count))
            self.status.set(fe_preview.summary(value) + ".")
            self._set_warnings(value.warnings)
        else:
            self.error = value or "The reading was cancelled."
            self.status.set("No FE modes can be shown.")
            self._set_warnings([self.error])

    def close(self) -> None:
        """Cancel the reading (if any) and close; a later outcome is discarded."""
        self.closed = True
        self.cancel.set()
        if self._job is not None:
            try:
                self.window.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        if self.window.winfo_exists():
            self.window.destroy()


def _read_experimental_file(path, cancel: threading.Event, results: queue.Queue) -> None:
    """Worker of ExperimentalPreviewWindow: reads the file and posts the outcome. It never touches a Tk object."""
    try:
        results.put(("ok", experimental_preview.preview_experimental_file(path, cancel_event=cancel)))
    except experimental_preview.PreviewCancelled:
        results.put(("cancelled", None))
    except experimental_preview.ExperimentalPreviewError as error:
        results.put(("error", str(error)))
    except Exception as error:  # noqa: BLE001  (any other failure is stated, the window never waits forever)
        results.put(("error", f"The experimental file cannot be read: {error}"))


class ExperimentalPreviewWindow:
    """A read-only view of the experimental data of one UNV / UFF / LMS file, read with the comparator's importer.

    Each fitted dataset-55 modal set is shown on its own (chosen in the list for viewing only: nothing in the main
    window changes); dataset 2414 records with their classification; FRF peak-derived records marked PROVISIONAL.
    The file is read on a background thread; the importer reads a file in one call, so closing the window discards
    the outcome but does not interrupt a read in progress.
    """

    POLL_MS = 100

    def __init__(self, root, label: str, path: Path) -> None:
        self.path = Path(path)
        self.preview = None
        self.error = None
        self.closed = False
        self.cancel = threading.Event()
        self.results: queue.Queue = queue.Queue()
        window = self.window = tk.Toplevel(root)
        window.title(f"Experimental data — {label}")
        window.minsize(720, 460)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(4, weight=1)
        window.protocol("WM_DELETE_WINDOW", self.close)
        ttk.Label(window, text=experimental_preview.NOTE, wraplength=780, justify="left").grid(
            row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        self.status = tk.StringVar(value="Reading the experimental file... The main window stays usable.")
        ttk.Label(window, textvariable=self.status, wraplength=780, justify="left").grid(
            row=1, column=0, sticky="ew", padx=12, pady=4)
        chooser = ttk.Frame(window)
        chooser.grid(row=2, column=0, sticky="ew", padx=12)
        ttk.Label(chooser, text="Modal set (view only):").grid(row=0, column=0, padx=(0, 6))
        self.set_choice = tk.StringVar(value="")
        self.set_box = ttk.Combobox(chooser, textvariable=self.set_choice, state="disabled", width=70)
        self.set_box.grid(row=0, column=1, sticky="ew")
        self.set_box.bind("<<ComboboxSelected>>", lambda _event: self._show_set())
        chooser.columnconfigure(1, weight=1)
        self.set_note = tk.StringVar(value="")
        ttk.Label(window, textvariable=self.set_note, wraplength=780, justify="left").grid(
            row=3, column=0, sticky="ew", padx=12, pady=4)
        table = ttk.Frame(window)
        table.grid(row=4, column=0, sticky="nsew", padx=12)
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=("number", "frequency", "record", "points", "dofs"), show="headings",
                                 height=9)
        for column, title, width, stretch in (("number", "No.", 50, False), ("frequency", "Frequency, Hz", 110, False),
                                              ("record", "Record", 380, True), ("points", "Points", 70, False),
                                              ("dofs", "Measured DOFs", 110, False)):
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, stretch=stretch)
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.details = tk.Text(window, height=8, wrap="word")
        self.details.grid(row=5, column=0, sticky="ew", padx=12, pady=6)
        self.details.configure(state="disabled")
        ttk.Button(window, text="Close", command=self.close).grid(row=6, column=0, sticky="e", padx=12, pady=(0, 12))
        self.thread = threading.Thread(target=_read_experimental_file, args=(self.path, self.cancel, self.results),
                                       daemon=True, name="experimental-preview")
        self.thread.start()
        self._job = window.after(self.POLL_MS, self._poll)

    def _poll(self) -> None:
        self._job = None
        if self.closed or not self.window.winfo_exists():  # closed, or destroyed with its parent
            self.closed = True
            self.cancel.set()
            return
        try:
            kind, value = self.results.get_nowait()
        except queue.Empty:
            self._job = self.window.after(self.POLL_MS, self._poll)
            return
        self._show(kind, value)

    def _set_details(self, lines) -> None:
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", "\n".join(lines))
        self.details.configure(state="disabled")

    def _file_lines(self) -> list:
        preview = self.preview
        lines = [f"Selected file: {preview.selected_path}"]
        if preview.source_path != preview.selected_path:
            lines.append(f"Read from: {preview.source_path} (the companion UNV / UFF of the LMS project)")
        lines.append(f"Data: {experimental_preview.KIND_TEXT[preview.kind]}")
        lines.append(f"Dataset types: {', '.join(str(x) for x in preview.dataset_types) or 'none'}; "
                     f"geometry nodes: {preview.geometry_node_count}")
        lines.extend(preview.details)
        if preview.record_classifications:
            lines.append("Dataset 2414 record classification (importer):")
            lines.extend(f"  record {index}: {classification}, {'included' if included else 'excluded'} — {reason}"
                         for index, classification, included, reason in preview.record_classifications)
        return lines

    def _show_set(self) -> None:
        preview = self.preview
        if preview is None or not preview.sets:
            return
        index = max(0, self.set_box.current())
        chosen = preview.sets[index]
        self.tree.delete(*self.tree.get_children())
        for record in chosen.records:
            self.tree.insert("", "end", values=(record.number, f"{record.frequency_hz:.6g}", record.label,
                                                record.point_count, record.measured_dof_count))
        note = [f"{chosen.title}." + (f" Processing: {chosen.processing_name}." if chosen.processing_name else "")]
        if chosen.excluded_residual:
            note.append(f"Excluded residual records: {'; '.join(chosen.excluded_residual)}.")
        if chosen.excluded_non_modal:
            note.append(f"Excluded non-modal records: {'; '.join(chosen.excluded_non_modal)}.")
        self.set_note.set(" ".join(note))
        warnings = [f"Importer warning: {text}" for text in chosen.warnings]
        self._set_details(self._file_lines() + warnings)

    def _show(self, kind: str, value) -> None:
        if kind != "ok":
            self.error = value or "The reading was cancelled."
            self.status.set("No experimental data can be shown.")
            self._set_details([self.error])
            return
        self.preview = value
        self.status.set(experimental_preview.summary(value) + ".")
        self.set_box.configure(values=[item.title for item in value.sets],
                               state="readonly" if len(value.sets) > 1 else "disabled")
        if value.sets:
            self.set_box.current(0)
        self._show_set()

    def close(self) -> None:
        """Close the view. A read in progress finishes in the background and its outcome is discarded."""
        self.closed = True
        self.cancel.set()
        if self._job is not None:
            try:
                self.window.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        if self.window.winfo_exists():
            self.window.destroy()


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
