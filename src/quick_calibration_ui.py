"""The workflows of the main application (and the research nine-constant view, Workflow menu item 3, no Abaqus).

1. Compare modes (ODB + UNV/UFF): the main window itself ("1. Files and analysis").
2. Calibrate effective material properties (INP + UNV/UFF): the existing QuickCalibrationWindow, opened in a
   Toplevel of the main Tk root (never a second Tk root) from the Workflow menu or the header buttons.

Closing the application (window "X" or File > Exit) never bypasses the quick calibration's own stop safeguards:
while a calibration runs, or the termination of its Abaqus processes is unconfirmed, the close is handed to
QuickCalibrationWindow.close() and the application stays open until that window has closed.

The two workflows never run at the same time: the ODB comparison does not start (_start) while a calibration runs,
stops or has unconfirmed owned processes, and a calibration does not start while the comparison runs, stops or
still owns an Abaqus process. Nothing running is interrupted; the user is told why.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

COMPARE_LABEL = "1. Compare modes (ODB + UNV/UFF)"
CALIBRATE_LABEL = "2. Calibrate effective material properties (INP + UNV/UFF)"
NINE_LABEL = "3. Nine elastic constants - research diagnostic (no Abaqus)"  # research track NINE-EC
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
    window.other_workflow_busy = self._comparison_busy_reason  # no calibration while the comparison is busy
    self._quick_calibration = window
    return window


def comparison_busy_reason(self) -> Optional[str]:
    """Why a calibration must not start: the ODB comparison runs, stops or still owns an Abaqus process."""
    if getattr(self, "running", False):
        stopping = getattr(getattr(self, "analysis_state", None), "name", "") == "STOPPING"
        return "the ODB comparison (workflow 1) is stopping" if stopping else "the ODB comparison (workflow 1) is running"
    process = getattr(self, "_owned_analysis_process", None)
    if process is not None and process.poll() is None:
        return "an Abaqus process of the ODB comparison (workflow 1) is still active"
    return None


def quick_calibration_busy_reason(self) -> Optional[str]:
    """Why the ODB comparison must not start: a calibration runs, stops or has unconfirmed owned processes."""
    window = getattr(self, "_quick_calibration", None)
    return window.busy_reason() if _window_open(window) else None


def open_nine_constants(self, factory: Optional[Callable] = None):
    """Research view (no Abaqus): the nine-constant identifiability diagnostic, one window per application."""
    from nine_constants_window import NineConstantsWindow

    window = getattr(self, "_nine_constants", None)
    if window is not None and not window.destroyed:
        try:
            if window.root.winfo_exists():
                window.root.deiconify()
                window.root.lift()
                return window
        except tk.TclError:
            pass
    top = tk.Toplevel(self.root)
    width = min(1300, max(900, top.winfo_screenwidth() - 120))
    height = min(900, max(650, top.winfo_screenheight() - 140))
    top.geometry(f"{width}x{height}+50+30")
    window = (factory or NineConstantsWindow)(top)
    self._nine_constants = window
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
    menu.add_separator()
    menu.add_command(label=NINE_LABEL + "...", command=self._open_nine_constants)
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
    original_start = application_class._start

    def start_comparison(self) -> None:
        reason = self._quick_calibration_busy_reason()
        if reason:
            self.status.set(f"ODB comparison not started: {reason}.")
            messagebox.showwarning(COMPARE_LABEL, f"The ODB comparison was not started: {reason}.\n\nWait until the "
                                                  "calibration has finished or stopped (see its window), then press "
                                                  "Run analysis again.", parent=self.root)
            return
        original_start(self)

    def workflow_init(self, root) -> None:
        self._quick_calibration = None
        self._nine_constants = None
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
    application_class._open_nine_constants = open_nine_constants
    application_class._show_compare_workflow = show_compare_workflow
    application_class._quick_calibration_released = quick_calibration_released
    application_class._comparison_busy_reason = comparison_busy_reason
    application_class._quick_calibration_busy_reason = quick_calibration_busy_reason
    application_class._start = start_comparison
    application_class._finish_close = finish_close
    application_class._close_with_session_save = close_with_session_save
    _INSTALLED = True
