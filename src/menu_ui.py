from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from app import APP_TITLE


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


def _build_menu(self) -> None:
    menu_bar = tk.Menu(self.root)

    file_menu = tk.Menu(menu_bar, tearoff=False)
    file_menu.add_command(label="New project", command=self._new_project)
    file_menu.add_command(label="Open project...", accelerator="Ctrl+O", command=self._open_project)
    file_menu.add_command(label="Save project", accelerator="Ctrl+S", command=self._save_project)
    file_menu.add_command(label="Save project as...", command=self._save_project_as)
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
