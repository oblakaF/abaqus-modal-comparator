"""The two workflows of the main application.

1. Compare modes (ODB + UNV/UFF): the main window itself ("1. Files and analysis").
2. Calibrate effective material properties (INP + UNV/UFF): the existing QuickCalibrationWindow, opened in a
   Toplevel of the main Tk root (never a second Tk root) from the Workflow menu or the header buttons.

Closing the application (window "X" or File > Exit) never bypasses the quick calibration's own stop safeguards:
while a calibration runs, or the termination of its Abaqus processes is unconfirmed, the close is handed to
QuickCalibrationWindow.close() and the application stays open until that window has closed.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

COMPARE_LABEL = "1. Compare modes (ODB + UNV/UFF)"
CALIBRATE_LABEL = "2. Calibrate effective material properties (INP + UNV/UFF)"
STILL_STOPPING = ("The quick calibration is stopping its Abaqus run. The application stays open until the owned "
                  "Abaqus processes are confirmed terminated and the calibration window has closed; then close the "
                  "application again.")

_INSTALLED = False


def _window_open(window) -> bool:
    if window is None or window.destroyed:
        return False
    try:
        return bool(window.root.winfo_exists())
    except tk.TclError:
        return False


def open_quick_calibration(self, factory: Optional[Callable] = None):
    """Workflow 2: show the calibration window (one per application; an open one is raised, not duplicated)."""
    from quick_calibration_window import QuickCalibrationWindow

    window = getattr(self, "_quick_calibration", None)
    if _window_open(window):
        window.root.deiconify()
        window.root.lift()
        window.root.focus_set()
        return window
    top = tk.Toplevel(self.root)
    width = min(1400, max(900, top.winfo_screenwidth() - 80))
    height = min(950, max(650, top.winfo_screenheight() - 120))
    top.geometry(f"{width}x{height}+30+20")
    window = (factory or QuickCalibrationWindow)(top)
    self._quick_calibration = window
    return window


def show_compare_workflow(self) -> None:
    """Workflow 1: the comparison inputs of the main window."""
    self.root.deiconify()
    self.root.lift()
    self.tabs.select(self.input_tab)


def quick_calibration_released(self) -> bool:
    """True when closing the application cannot leave a calibration's Abaqus process behind."""
    window = getattr(self, "_quick_calibration", None)
    if not _window_open(window):
        return True
    if not (window.running() or window.closing or window.unconfirmed is not None):
        return True  # idle: nothing owned can run; the window closes with the application
    window.root.deiconify()
    window.root.lift()
    window.close()  # stops a run; asks about an unconfirmed stop; closes only when nothing owned can be left
    if window.destroyed:
        return True
    if window.running():
        messagebox.showinfo(CALIBRATE_LABEL, STILL_STOPPING, parent=self.root)
    return False


def _build_workflow_controls(self) -> None:
    menu = tk.Menu(self.menu_bar, tearoff=False)
    menu.add_command(label=COMPARE_LABEL, command=self._show_compare_workflow)
    menu.add_command(label=CALIBRATE_LABEL + "...", command=self._open_quick_calibration)
    self.menu_bar.insert_cascade(self.menu_bar.index("File") + 1, label="Workflow", menu=menu)  # after File
    self.workflow_menu = menu
    bar = ttk.Frame(self.header)
    bar.pack(anchor="w", pady=(6, 0))
    ttk.Label(bar, text="Workflow:").pack(side="left", padx=(0, 6))
    self.compare_workflow_button = ttk.Button(bar, text=COMPARE_LABEL, command=self._show_compare_workflow)
    self.compare_workflow_button.pack(side="left", padx=(0, 6))
    self.calibrate_workflow_button = ttk.Button(bar, text=CALIBRATE_LABEL, command=self._open_quick_calibration)
    self.calibrate_workflow_button.pack(side="left")


def install_quick_calibration_ui(app_module) -> None:
    """Last UI layer: it wraps the final close owners (window "X" and File > Exit), so it must stay after
    install_project_review and install_responsive_workflow (checked by runtime_contracts)."""
    global _INSTALLED
    if _INSTALLED:
        return
    application_class = app_module.ModalComparatorApp
    original_init = application_class.__init__
    original_finish_close = application_class._finish_close
    original_close_with_session_save = application_class._close_with_session_save

    def workflow_init(self, root) -> None:
        self._quick_calibration = None
        original_init(self, root)
        _build_workflow_controls(self)

    def finish_close(self) -> None:
        if not self._quick_calibration_released():
            return
        original_finish_close(self)

    def close_with_session_save(self) -> None:
        if not self._quick_calibration_released():
            return
        original_close_with_session_save(self)

    application_class.__init__ = workflow_init
    application_class._open_quick_calibration = open_quick_calibration
    application_class._show_compare_workflow = show_compare_workflow
    application_class._quick_calibration_released = quick_calibration_released
    application_class._finish_close = finish_close
    application_class._close_with_session_save = close_with_session_save
    _INSTALLED = True
