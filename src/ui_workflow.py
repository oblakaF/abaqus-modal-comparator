from __future__ import annotations

import json
import os
import shlex
import subprocess
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from ui_policy import (
    AnalysisState,
    COMPARISON_COLUMNS,
    DirtyTracker,
    EM_DASH,
    LayoutMode,
    REVIEW_COLUMNS,
    STYLE_TOKENS,
    button_grid_columns,
    completion_state,
    coordinate_scale_from_units,
    discover_abaqus_installations,
    experimental_unit_from_metadata,
    logical_window_width,
    metric_grid_columns,
    normalize_recovery_preferences,
    resolve_command,
    responsive_padding,
    select_abaqus_installation,
    select_layout_mode,
    status_text,
    tab_labels_for,
    text_wrap_width,
    validate_custom_scale,
)


_INSTALLED = False
RESIZE_DEBOUNCE_MS = 90
AUTOSAVE_DEBOUNCE_MS = 650
STOP_CLOSE_TIMEOUT_MS = 12_000
RECOVERY_SETTINGS_NAME = "ui_preferences.json"
DIAGNOSTIC_SHAPE_MESSAGE = (
    "No accepted mode pairs.\n"
    "See MAC and frequencies / Manual review for diagnostic candidates."
)
ANALYSIS_CONFIGURATION_CONTROL_NAMES = (
    "abaqus_path",
    "abaqus_path_browse",
    "experimental_path",
    "experimental_path_browse",
    "start_mode",
    "end_mode",
    "abaqus_installation",
    "detect_abaqus",
    "browse_abaqus",
    "test_abaqus",
    "advanced_command_toggle",
    "advanced_command",
    "abaqus_model_unit",
    "experimental_coordinate_unit",
    "automatic_scale",
    "custom_scale",
    "custom_scale_input",
    "workspace_path",
    "workspace_path_browse",
)


def set_configuration_controls_locked(controls, locked: bool) -> None:
    """Freeze or restore every widget that defines an active analysis run."""
    for widget, idle_state in controls.values():
        try:
            widget.configure(state="disabled" if locked else idle_state)
        except tk.TclError:
            continue


def enable_windows_dpi_awareness() -> bool:
    if os.name != "nt":
        return False
    try:
        import ctypes

        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)
        except (AttributeError, OSError, TypeError, ValueError):
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return True
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def _preferences_path() -> Path:
    from project_review import CONFIG_DIRECTORY

    return CONFIG_DIRECTORY / RECOVERY_SETTINGS_NAME


def load_recovery_preferences(path: Optional[Path] = None) -> dict[str, bool]:
    path = path or _preferences_path()
    try:
        return normalize_recovery_preferences(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return normalize_recovery_preferences({})


def save_recovery_preferences(value: object, path: Optional[Path] = None) -> None:
    path = path or _preferences_path()
    preferences = normalize_recovery_preferences(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(preferences, indent=2), encoding="utf-8")


def verify_abaqus_command(command: str, timeout_seconds: int = 15) -> tuple[bool, str]:
    resolved = resolve_command(command)
    if resolved is None:
        return False, (
            "No valid Abaqus installation was found. Choose Detect again, "
            "Browse, or Advanced command."
        )
    arguments = ["information=release"]
    if os.name == "nt":
        command_line = subprocess.list2cmdline([resolved, *arguments])
        invocation = ["cmd.exe", "/d", "/s", "/c", command_line]
    else:
        invocation = shlex.split(resolved) + arguments
    try:
        completed = subprocess.run(
            invocation,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return False, f"The Abaqus launcher could not be tested: {error}"
    output = (completed.stdout or completed.stderr or "").strip()
    if completed.returncode != 0:
        return False, output[-1000:] or "The Abaqus launcher returned an error."
    return True, output[-1000:] or f"Abaqus launcher is available: {resolved}"


def dispatch_clipboard_action(widget, action: str) -> bool:
    """Apply Windows-style text editing without replacing Tk's normal typing."""
    action = str(action).lower()
    is_text = widget.winfo_class() == "Text"
    try:
        state = str(widget.cget("state"))
    except Exception:
        state = "normal"
    editable = state == "normal"

    try:
        if is_text:
            selected = bool(widget.tag_ranges("sel"))
            selected_text = widget.get("sel.first", "sel.last") if selected else ""
        else:
            selected = bool(widget.selection_present())
            selected_text = widget.get()[widget.index("sel.first"):widget.index("sel.last")] if selected else ""

        if action == "copy":
            if not selected:
                return False
            widget.clipboard_clear()
            widget.clipboard_append(selected_text)
            return True
        if action == "select_all":
            if is_text:
                widget.tag_add("sel", "1.0", "end-1c")
                widget.mark_set("insert", "1.0")
            else:
                widget.selection_range(0, "end")
                widget.icursor("end")
            return True
        if not editable:
            return False
        if action == "cut":
            if not selected:
                return False
            widget.clipboard_clear()
            widget.clipboard_append(selected_text)
            if is_text:
                widget.delete("sel.first", "sel.last")
            else:
                widget.delete("sel.first", "sel.last")
            return True
        if action == "paste":
            value = widget.clipboard_get()
            if selected:
                widget.delete("sel.first", "sel.last")
            widget.insert("insert", value)
            return True
    except (tk.TclError, AttributeError, IndexError):
        return False
    return False


class Tooltip:
    def __init__(self, widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.window = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _event=None) -> None:
        if self.window is not None:
            return
        window = tk.Toplevel(self.widget)
        window.wm_overrideredirect(True)
        try:
            x = self.widget.winfo_rootx() + 16
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            window.wm_geometry(f"+{x}+{y}")
        except tk.TclError:
            pass
        ttk.Label(
            window,
            text=self.text,
            style="Tooltip.TLabel",
            justify="left",
            wraplength=420,
            padding=(8, 6),
        ).pack()
        self.window = window

    def _hide(self, _event=None) -> None:
        if self.window is not None:
            self.window.destroy()
            self.window = None


def _walk(widget):
    for child in widget.winfo_children():
        yield child
        yield from _walk(child)


def _configure_styles(root) -> None:
    style = ttk.Style(root)
    family = STYLE_TOKENS["font_family"]
    root.option_add("*Font", (family, STYLE_TOKENS["body_size"]))
    style.configure("Title.TLabel", font=(family, STYLE_TOKENS["application_title_size"], "bold"))
    style.configure("Section.TLabel", font=(family, STYLE_TOKENS["section_title_size"], "bold"))
    style.configure("MetricCaption.TLabel", font=(family, STYLE_TOKENS["metric_caption_size"], "bold"), foreground="#505A64")
    style.configure("MetricValue.TLabel", font=(family, STYLE_TOKENS["metric_value_size"], "bold"), foreground="#17212B")
    style.configure("Secondary.TLabel", font=(family, STYLE_TOKENS["secondary_size"]), foreground="#59636E")
    style.configure("Status.TLabel", font=(family, STYLE_TOKENS["status_size"]))
    style.configure("Tooltip.TLabel", font=(family, STYLE_TOKENS["secondary_size"]), background="#FFFBEA", relief="solid", borderwidth=1)
    style.configure("Treeview", font=(family, STYLE_TOKENS["table_size"]), rowheight=STYLE_TOKENS["table_row_height"])
    style.configure("Treeview.Heading", font=(family, STYLE_TOKENS["table_size"], "bold"))
    style.configure("MetricCard.TFrame", relief="solid", borderwidth=1)


def _configure_tree(table, specifications) -> None:
    active = [str(item) for item in table["columns"]]
    known = {item.key: item for item in specifications}
    for column in active:
        item = known.get(column)
        if item is None:
            current = str(table.heading(column, "text") or "").strip()
            table.heading(column, text=current or column.replace("_", " ").title())
            table.column(column, minwidth=70)
            continue
        table.heading(column, text=item.heading)
        table.column(
            column,
            width=item.width,
            minwidth=item.minimum,
            anchor=item.anchor,
            stretch=item.stretch,
        )


def _ensure_horizontal_scrollbar(table) -> bool:
    if getattr(table, "_horizontal_scrollbar", None) is not None:
        return True
    parent = table.master
    bar = ttk.Scrollbar(parent, orient="horizontal", command=table.xview)
    table.configure(xscrollcommand=bar.set)
    try:
        if table.winfo_manager() == "pack":
            bar.pack(side="bottom", fill="x", before=table)
        elif table.winfo_manager() == "grid":
            info = table.grid_info()
            row = int(info.get("row", 0)) + 1
            column = int(info.get("column", 0))
            bar.grid(row=row, column=column, sticky="ew")
        else:
            return False
    except tk.TclError:
        return False
    table._horizontal_scrollbar = bar
    return True


def _choice_dialog(parent, title: str, message: str, choices: tuple[tuple[str, str], ...]) -> Optional[str]:
    result = {"value": None}
    window = tk.Toplevel(parent)
    window.title(title)
    window.transient(parent)
    window.resizable(False, False)
    ttk.Label(window, text=message, justify="left", wraplength=440, padding=(18, 18, 18, 10)).pack(fill="x")
    buttons = ttk.Frame(window, padding=(18, 0, 18, 16))
    buttons.pack(fill="x")

    def select(value: str) -> None:
        result["value"] = value
        window.destroy()

    for value, label in choices:
        ttk.Button(buttons, text=label, command=lambda current=value: select(current)).pack(side="left", padx=(0, 8))
    window.protocol("WM_DELETE_WINDOW", window.destroy)
    window.grab_set()
    parent.wait_window(window)
    return result["value"]


def install_responsive_workflow(app_module) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from project_review import LAST_SESSION_PATH, write_project

    application_class = app_module.ModalComparatorApp
    original_init = application_class.__init__
    original_complete = application_class._complete
    original_failed = application_class._failed
    original_populate = application_class._populate
    original_apply_project = application_class._apply_project_payload
    original_new_project = application_class._new_project
    original_set_manual_review = application_class._set_manual_review
    original_manual_reset = application_class._manual_reset
    original_refresh_review = application_class._refresh_review_table

    def workflow_init(self, root) -> None:
        self._recovery_preferences = load_recovery_preferences()
        self._session_recovered = False
        self._analysis_cancel_event = threading.Event()
        self._owned_analysis_process = None
        self._analysis_thread = None
        self._close_after_cancel = False
        self._ui_closing = False
        self._automatic_admissible_pair_count = None
        self._autosave_job = None
        self._responsive_job = None
        self._layout_mode = None
        self._metric_cards = []
        self._button_frames = []
        self._responsive_wrap_labels = []
        self._tooltips = []
        self._abaqus_installations = {}
        self._analysis_configuration_controls = {}
        self.analysis_state = AnalysisState.NO_DATA
        self.dirty_tracker = DirtyTracker()

        self.abaqus_model_unit = tk.StringVar(master=root, value="mm")
        self.experimental_coordinate_unit = tk.StringVar(master=root, value="m")
        self.experimental_unit_source = tk.StringVar(master=root, value="inferred; verify for this test setup")
        self.coordinate_mapping_mode = tk.StringVar(master=root, value="automatic")
        self.custom_coordinate_scale = tk.StringVar(master=root, value="1.0")
        self.computed_coordinate_scale = tk.StringVar(master=root, value="0.001")
        # Kept as a compatibility bridge for the existing project payload and
        # runtime worker; normal users never edit or see the word "auto".
        self.coordinate_scale_text = tk.StringVar(master=root, value="auto")
        self.abaqus_installation_label = tk.StringVar(master=root, value="Detecting installed launchers...")
        self.abaqus_detection_status = tk.StringVar(master=root, value="")
        self.show_abaqus_advanced = tk.BooleanVar(master=root, value=False)

        original_init(self, root)
        root.geometry("1400x860")
        root.minsize(900, 650)
        _configure_styles(root)
        self._rebuild_metric_cards()
        self._finalize_tables()
        self._install_text_editing()
        self._install_settings_menu()
        self._collect_responsive_widgets()
        self._install_dirty_tracking()
        self._detect_abaqus_installations()
        self._sync_coordinate_mapping()
        self._set_empty_states()
        self._refresh_readiness()
        root.bind("<Configure>", self._schedule_responsive_layout, add="+")
        root.after_idle(self._apply_responsive_layout)
        root.protocol("WM_DELETE_WINDOW", self._close_requested)
        if self._session_recovered:
            self.dirty_tracker.reset({})
            self._on_persistent_change()
            self.status.set("Previous session recovered.")
            if self._recovery_preferences["show_recovery_notice"]:
                root.after_idle(self._show_recovery_notice)
        else:
            self._reset_dirty()

    def build_input(self) -> None:
        self.end_mode.set(15)
        canvas = tk.Canvas(self.input_tab, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(self.input_tab, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas, padding=4)
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width), add="+")
        content.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")), add="+")
        self.root.bind_all("<MouseWheel>", self._scroll_input_tab, add="+")
        self._input_canvas = canvas
        self._input_content = content

        def section(title: str):
            frame = ttk.LabelFrame(content, text=title, padding=STYLE_TOKENS["section_padding"])
            frame.pack(fill="x", pady=(0, STYLE_TOKENS["section_spacing"]))
            frame.columnconfigure(1, weight=1)
            return frame

        source = section("SOURCE FILES")
        self.abaqus_path_entry, abaqus_path_browse = self._responsive_file_row(
            source, 0, "Abaqus results", self.abaqus_path, self._choose_abaqus,
            "Select an .odb file or an extracted manifest.json."
        )
        self.experimental_path_entry, experimental_path_browse = self._responsive_file_row(
            source, 2, "Experimental results", self.experimental_path, self._choose_experiment,
            "Select UNV/UFF data; an LMS file is accepted when its exported UNV/UFF is beside it."
        )

        analysis = section("ANALYSIS")
        ttk.Label(analysis, text="Abaqus mode range:").grid(row=0, column=0, sticky="w", pady=4)
        mode_box = ttk.Frame(analysis)
        mode_box.grid(row=0, column=1, sticky="w", padx=(10, 0), pady=4)
        self.start_mode_spinbox = ttk.Spinbox(
            mode_box, from_=1, to=999, textvariable=self.start_mode, width=7
        )
        self.start_mode_spinbox.pack(side="left")
        ttk.Label(mode_box, text="to").pack(side="left", padx=7)
        self.end_mode_spinbox = ttk.Spinbox(
            mode_box, from_=1, to=999, textvariable=self.end_mode, width=7
        )
        self.end_mode_spinbox.pack(side="left")
        mode_help = ttk.Label(
            analysis,
            text="Rigid and near-zero modes are excluded automatically; experimental modes are detected from the measurement file.",
            style="Secondary.TLabel",
            justify="left",
        )
        mode_help.grid(row=1, column=1, sticky="w", padx=(10, 0), pady=(0, 4))
        self._responsive_wrap_labels.append(mode_help)
        self._tooltips.append(Tooltip(mode_box, "Select the inclusive Abaqus eigenmode range to extract from the ODB."))

        abaqus = section("ABAQUS")
        ttk.Label(abaqus, text="Abaqus installation:").grid(row=0, column=0, sticky="w", pady=4)
        self.abaqus_installation_combo = ttk.Combobox(
            abaqus, textvariable=self.abaqus_installation_label, state="readonly"
        )
        self.abaqus_installation_combo.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=4)
        self.abaqus_installation_combo.bind("<<ComboboxSelected>>", self._select_abaqus_installation, add="+")
        detect_buttons = ttk.Frame(abaqus)
        detect_buttons.grid(row=0, column=2, sticky="e", padx=(10, 0))
        self.detect_abaqus_button = ttk.Button(
            detect_buttons, text="Detect again", command=self._detect_abaqus_installations
        )
        self.detect_abaqus_button.pack(side="left")
        self.browse_abaqus_button = ttk.Button(
            detect_buttons, text="Browse...", command=self._browse_abaqus_command
        )
        self.browse_abaqus_button.pack(side="left", padx=5)
        self.test_abaqus_button = ttk.Button(
            detect_buttons, text="Test Abaqus", command=self._test_abaqus
        )
        self.test_abaqus_button.pack(side="left")
        self.abaqus_warning_label = ttk.Label(abaqus, textvariable=self.abaqus_detection_status, style="Secondary.TLabel")
        self.abaqus_warning_label.grid(row=1, column=1, columnspan=2, sticky="w", padx=(10, 0))
        self.abaqus_advanced_checkbutton = ttk.Checkbutton(
            abaqus,
            text="Advanced command",
            variable=self.show_abaqus_advanced,
            command=self._toggle_abaqus_advanced,
        )
        self.abaqus_advanced_checkbutton.grid(row=2, column=0, sticky="w", pady=(7, 2))
        self.abaqus_advanced_frame = ttk.Frame(abaqus)
        self.abaqus_advanced_frame.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(10, 0), pady=(7, 2))
        self.abaqus_advanced_frame.columnconfigure(0, weight=1)
        self.abaqus_command_entry = ttk.Entry(self.abaqus_advanced_frame, textvariable=self.abaqus_command)
        self.abaqus_command_entry.grid(row=0, column=0, sticky="ew")
        self.abaqus_advanced_frame.grid_remove()

        geometry = section("GEOMETRY / UNITS")
        ttk.Label(geometry, text="Abaqus model length unit:").grid(row=0, column=0, sticky="w", pady=4)
        self.abaqus_unit_combo = ttk.Combobox(
            geometry, textvariable=self.abaqus_model_unit, values=("mm", "m", "cm", "\u00b5m", "custom"), state="readonly", width=15
        )
        self.abaqus_unit_combo.grid(row=0, column=1, sticky="w", padx=(10, 0), pady=4)
        ttk.Label(geometry, text="Abaqus is unitless; choose the length unit used to build the model.", style="Secondary.TLabel").grid(row=0, column=2, sticky="w", padx=(10, 0))
        ttk.Label(geometry, text="Experimental coordinate unit:").grid(row=1, column=0, sticky="w", pady=4)
        self.experimental_unit_combo = ttk.Combobox(
            geometry, textvariable=self.experimental_coordinate_unit, values=("mm", "m", "cm", "\u00b5m"), state="readonly", width=15
        )
        self.experimental_unit_combo.grid(row=1, column=1, sticky="w", padx=(10, 0), pady=4)
        self.experimental_unit_combo.bind(
            "<<ComboboxSelected>>", self._experimental_unit_selected, add="+"
        )
        ttk.Label(geometry, textvariable=self.experimental_unit_source, style="Secondary.TLabel").grid(row=1, column=2, sticky="w", padx=(10, 0))
        ttk.Label(geometry, text="Coordinate mapping:").grid(row=2, column=0, sticky="nw", pady=4)
        mapping = ttk.Frame(geometry)
        mapping.grid(row=2, column=1, columnspan=2, sticky="w", padx=(10, 0), pady=4)
        self.automatic_scale_radio = ttk.Radiobutton(
            mapping,
            text="Automatic from units / alignment",
            variable=self.coordinate_mapping_mode,
            value="automatic",
            command=self._sync_coordinate_mapping,
        )
        self.automatic_scale_radio.pack(anchor="w")
        self.custom_scale_radio = ttk.Radiobutton(
            mapping,
            text="Custom scale factor",
            variable=self.coordinate_mapping_mode,
            value="custom",
            command=self._sync_coordinate_mapping,
        )
        self.custom_scale_radio.pack(anchor="w")
        self.custom_scale_frame = ttk.Frame(geometry)
        self.custom_scale_frame.grid(row=3, column=1, columnspan=2, sticky="w", padx=(10, 0), pady=4)
        ttk.Label(self.custom_scale_frame, text="Custom scale:").pack(side="left")
        self.custom_scale_entry = ttk.Entry(self.custom_scale_frame, textvariable=self.custom_coordinate_scale, width=16)
        self.custom_scale_entry.pack(side="left", padx=(8, 0))
        ttk.Label(geometry, text="Computed scale:").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Entry(geometry, textvariable=self.computed_coordinate_scale, state="readonly", width=18).grid(row=4, column=1, sticky="w", padx=(10, 0), pady=4)
        mapping_help = ttk.Label(
            geometry,
            text="The scale converts Abaqus model coordinates into the experimental coordinate unit before alignment. Automatic mapping remains subject to the existing scientific geometry checks.",
            style="Secondary.TLabel", justify="left"
        )
        mapping_help.grid(row=5, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self._responsive_wrap_labels.append(mapping_help)
        self._tooltips.extend((
            Tooltip(self.abaqus_unit_combo, "Abaqus ODB files do not contain an intrinsic physical length unit. Choose the unit used when the model geometry was created."),
            Tooltip(self.experimental_unit_combo, "The unit is detected from UNV metadata when available, otherwise inferred and left editable."),
            Tooltip(mapping, "Automatic mapping derives the scale from the selected units; Custom exposes a positive numeric override."),
        ))

        output = section("OUTPUT")
        self.workspace_path_entry, workspace_path_browse = self._responsive_file_row(
            output, 0, "Output workspace", self.workspace_path, self._choose_workspace,
            "Extraction cache, diagnostic logs, plots and report data are written here."
        )

        self._analysis_configuration_controls = {
            "abaqus_path": (self.abaqus_path_entry, "normal"),
            "abaqus_path_browse": (abaqus_path_browse, "normal"),
            "experimental_path": (self.experimental_path_entry, "normal"),
            "experimental_path_browse": (experimental_path_browse, "normal"),
            "start_mode": (self.start_mode_spinbox, "normal"),
            "end_mode": (self.end_mode_spinbox, "normal"),
            "abaqus_installation": (self.abaqus_installation_combo, "readonly"),
            "detect_abaqus": (self.detect_abaqus_button, "normal"),
            "browse_abaqus": (self.browse_abaqus_button, "normal"),
            "test_abaqus": (self.test_abaqus_button, "normal"),
            "advanced_command_toggle": (self.abaqus_advanced_checkbutton, "normal"),
            "advanced_command": (self.abaqus_command_entry, "normal"),
            "abaqus_model_unit": (self.abaqus_unit_combo, "readonly"),
            "experimental_coordinate_unit": (self.experimental_unit_combo, "readonly"),
            "automatic_scale": (self.automatic_scale_radio, "normal"),
            "custom_scale": (self.custom_scale_radio, "normal"),
            "custom_scale_input": (self.custom_scale_entry, "normal"),
            "workspace_path": (self.workspace_path_entry, "normal"),
            "workspace_path_browse": (workspace_path_browse, "normal"),
        }

        actions = ttk.Frame(content)
        actions.pack(fill="x", pady=(2, 10))
        self.run_button = ttk.Button(actions, text="Run analysis", command=self._start)
        self.stop_button = ttk.Button(actions, text="Stop", command=self._request_stop, state="disabled")
        self.folder_button = ttk.Button(actions, text="Open output folder", command=self._open_workspace)
        for button in (self.run_button, self.stop_button, self.folder_button):
            button.pack(side="left", padx=(0, 8))

        help_text = ttk.Label(
            content,
            text=(
                "Workflow: extract Abaqus modes; import experimental data; align geometry; compare modes; "
                "generate plots; prepare report data. Scientific acceptance gates are unchanged."
            ),
            style="Secondary.TLabel",
            justify="left",
        )
        help_text.pack(fill="x", pady=(0, 6))
        self._responsive_wrap_labels.append(help_text)

    def responsive_file_row(self, parent, row, label, variable, command, help_text):
        ttk.Label(parent, text=label + ":").grid(row=row, column=0, sticky="w", pady=(5, 2))
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", padx=(10, 0), pady=(5, 2))
        button = ttk.Button(parent, text="Browse...", command=command)
        button.grid(row=row, column=2, sticky="e", padx=(10, 0), pady=(5, 2))
        help_label = ttk.Label(parent, text=help_text, style="Secondary.TLabel", justify="left")
        help_label.grid(row=row + 1, column=1, columnspan=2, sticky="w", padx=(10, 0), pady=(0, 4))
        self._responsive_wrap_labels.append(help_label)
        return entry, button

    def sync_coordinate_mapping(self, *_args) -> Optional[float]:
        custom = self.coordinate_mapping_mode.get() == "custom"
        if custom:
            self.custom_scale_frame.grid()
            try:
                value = validate_custom_scale(self.custom_coordinate_scale.get())
            except ValueError:
                self.computed_coordinate_scale.set(EM_DASH)
                self.coordinate_scale_text.set(self.custom_coordinate_scale.get())
                return None
            self.computed_coordinate_scale.set(f"{value:.9g}")
            self.coordinate_scale_text.set(f"{value:.17g}")
            return value
        self.custom_scale_frame.grid_remove()
        try:
            value = coordinate_scale_from_units(
                self.abaqus_model_unit.get(), self.experimental_coordinate_unit.get()
            )
        except ValueError:
            self.computed_coordinate_scale.set(EM_DASH)
            self.coordinate_scale_text.set("auto")
            return None
        self.computed_coordinate_scale.set(f"{value:.9g}")
        self.coordinate_scale_text.set("auto")
        return value

    def scroll_input_tab(self, event) -> None:
        try:
            widget = self.root.winfo_containing(event.x_root, event.y_root)
            while widget is not None and widget not in (self._input_canvas, self._input_content):
                widget = getattr(widget, "master", None)
            if widget is None:
                return
            self._input_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        except tk.TclError:
            pass

    def experimental_unit_selected(self, _event=None) -> None:
        self.experimental_unit_source.set("manually selected")
        self._on_persistent_change()

    def workflow_validate(self):
        abaqus = Path(self.abaqus_path.get().strip())
        experiment = Path(self.experimental_path.get().strip())
        workspace_text = self.workspace_path.get().strip()
        workspace = Path(workspace_text) if workspace_text else app_module.DEFAULT_WORKSPACE
        if not abaqus.exists():
            messagebox.showwarning("Abaqus results", "Select an existing Abaqus .odb file or extracted manifest.json.")
            return None
        if not experiment.exists():
            messagebox.showwarning("Experimental results", "Select an existing experimental .unv, .uff, or .lms file.")
            return None
        try:
            start, end = int(self.start_mode.get()), int(self.end_mode.get())
        except (ValueError, tk.TclError):
            messagebox.showwarning("Abaqus mode range", "Enter whole-number first and final Abaqus modes.")
            return None
        if start < 1 or end < start:
            messagebox.showwarning("Abaqus mode range", "The final mode must be greater than or equal to the first mode.")
            return None
        if self.coordinate_mapping_mode.get() == "custom":
            try:
                scale = validate_custom_scale(self.custom_coordinate_scale.get())
            except ValueError as error:
                messagebox.showwarning("Custom coordinate scale", str(error))
                return None
        else:
            try:
                scale = coordinate_scale_from_units(
                    self.abaqus_model_unit.get(), self.experimental_coordinate_unit.get()
                )
            except ValueError:
                messagebox.showwarning(
                    "Coordinate mapping",
                    "Choose Automatic mapping with named units, or enter a positive Custom scale factor.",
                )
                return None
        command = self.abaqus_command.get().strip()
        if abaqus.suffix.lower() == ".odb" and resolve_command(command) is None:
            messagebox.showwarning(
                "Abaqus installation",
                "No valid Abaqus installation was found. Choose Detect again, Browse, or Advanced command.",
            )
            return None
        return abaqus, experiment, workspace, start, end, command or "abaqus", scale

    def detect_abaqus(self) -> None:
        installations = discover_abaqus_installations()
        self._abaqus_installations = {item.label: item.command for item in installations}
        labels = tuple(self._abaqus_installations)
        self.abaqus_installation_combo.configure(values=labels)
        selected = select_abaqus_installation(installations, self.abaqus_command.get())
        if selected is not None:
            self.abaqus_installation_label.set(selected.label)
            self.abaqus_command.set(selected.command)
            self.abaqus_detection_status.set(f"Detected launcher: {selected.command}")
        elif installations:
            self.abaqus_installation_label.set("Choose an installed Abaqus version")
            self.abaqus_detection_status.set(f"{len(installations)} launchers detected; choose one.")
        else:
            self.abaqus_installation_label.set("No installation detected")
            self.abaqus_detection_status.set(
                "No valid Abaqus installation was found. Use Detect again, Browse, or Advanced command."
            )

    def select_abaqus(self, _event=None) -> None:
        command = self._abaqus_installations.get(self.abaqus_installation_label.get())
        if command:
            self.abaqus_command.set(command)
            self.abaqus_detection_status.set(f"Selected launcher: {command}")

    def browse_abaqus(self) -> None:
        filename = filedialog.askopenfilename(
            title="Choose an Abaqus launcher",
            filetypes=[("Abaqus launchers", "*.bat *.cmd *.exe"), ("All files", "*.*")],
        )
        if filename:
            resolved = resolve_command(filename)
            if resolved is None:
                messagebox.showwarning(
                    "Abaqus launcher",
                    "Choose an executable Abaqus launcher (.bat, .cmd, or .exe).",
                )
                return
            label = f"Abaqus \u2014 selected \u2713"
            self._abaqus_installations[label] = resolved
            self.abaqus_installation_combo.configure(values=tuple(self._abaqus_installations))
            self.abaqus_installation_label.set(label)
            self.abaqus_command.set(resolved)
            self.abaqus_detection_status.set(f"Selected launcher: {resolved}")

    def toggle_abaqus_advanced(self) -> None:
        if self.show_abaqus_advanced.get():
            self.abaqus_advanced_frame.grid()
            self.abaqus_command_entry.focus_set()
        else:
            self.abaqus_advanced_frame.grid_remove()

    def test_abaqus(self) -> None:
        command = self.abaqus_command.get().strip()
        self.abaqus_detection_status.set("Testing the Abaqus launcher (no FE analysis is started)...")

        def worker() -> None:
            ok, detail = verify_abaqus_command(command)
            def finished() -> None:
                self.abaqus_detection_status.set("Abaqus launcher is available." if ok else detail)
                if ok:
                    messagebox.showinfo("Test Abaqus", detail or "Abaqus launcher is available.")
                else:
                    messagebox.showwarning("Test Abaqus", detail)
            self._post_to_ui(finished)

        threading.Thread(target=worker, daemon=True).start()

    def set_analysis_state(self, state: AnalysisState, message: Optional[str] = None) -> None:
        self.analysis_state = AnalysisState(state)
        if message is None:
            message = status_text(self.analysis_state)
        self.status.set(message)
        configuration_locked = self.analysis_state in {
            AnalysisState.RUNNING,
            AnalysisState.STOPPING,
        }
        set_configuration_controls_locked(
            self._analysis_configuration_controls,
            configuration_locked,
        )
        if self.analysis_state in {AnalysisState.RUNNING}:
            self.run_button.configure(state="disabled")
            self.stop_button.configure(state="normal")
        elif self.analysis_state is AnalysisState.STOPPING:
            self.run_button.configure(state="disabled")
            self.stop_button.configure(state="disabled")
        else:
            self.run_button.configure(state="normal")
            self.stop_button.configure(state="disabled")

    def set_analysis_stage(self, number: int, text: str) -> None:
        if self.analysis_state is AnalysisState.RUNNING:
            self.status.set(f"{int(number)}/6 {text}...")

    def start_analysis(self) -> None:
        if self.running:
            return
        values = self._validate()
        if values is None:
            return
        self._analysis_cancel_event = threading.Event()
        self._owned_analysis_process = None
        self._automatic_admissible_pair_count = None
        self.result = None
        self.cache = None
        self._clear_result_presentation("Analysis is running; previous results are no longer active.")
        self.running = True
        self.progress.start(12)
        self._set_analysis_state(AnalysisState.RUNNING, "1/6 Abaqus extraction...")
        self._analysis_thread = threading.Thread(target=self._worker, args=values, daemon=True)
        self._analysis_thread.start()

    def request_stop(self) -> None:
        if not self.running or self.analysis_state is AnalysisState.STOPPING:
            return
        self._analysis_cancel_event.set()
        self._set_analysis_state(AnalysisState.STOPPING)

    def cancelled(self) -> None:
        self.running = False
        self.progress.stop()
        self.result = None
        self.cache = None
        self._clear_result_presentation("Analysis stopped by user.")
        self._set_empty_states(stopped=True)
        for button_name in ("excel_button", "pdf_button", "export_all_button"):
            button = getattr(self, button_name, None)
            if button is not None:
                button.configure(state="disabled")
        self._set_analysis_state(AnalysisState.STOPPED)
        if self._close_after_cancel:
            self._close_after_cancel = False
            self._finish_close()

    def complete(self, result) -> None:
        if self._analysis_cancel_event.is_set():
            self._cancelled()
            return
        automatic_pair_count = len(result.pairs)
        self._automatic_admissible_pair_count = automatic_pair_count
        original_complete(self, result)
        if not result.pairs:
            self._set_mode_shape_placeholder(DIAGNOSTIC_SHAPE_MESSAGE)
        range_notice = result.metadata.get("extraction_range_notice")
        if range_notice:
            self.abaqus_detection_status.set(str(range_notice))
        state = completion_state(automatic_pair_count)
        self._set_analysis_state(state, status_text(state, pair_count=automatic_pair_count))

    def failed(self, error: Exception) -> None:
        original_failed(self, error)
        self._clear_result_presentation("Analysis could not be completed.")
        self._set_empty_states()
        self.metric_geometry_caption.configure(text="STATE")
        self.metric_geometry.configure(text="Error")
        self._set_analysis_state(
            AnalysisState.ERROR,
            "Analysis could not be completed. See last_error.log in the output workspace.",
        )
        if self._close_after_cancel:
            self._close_after_cancel = False
            process = self._owned_analysis_process
            if process is not None and process.poll() is None:
                messagebox.showwarning(
                    "Close blocked",
                    "The application is still tracking an Abaqus process that did not stop. "
                    "The window will remain open so the process is not orphaned.",
                )
            else:
                self._finish_close()

    def populate(self, result) -> None:
        original_populate(self, result)
        pairs = list(result.pairs)
        automatic_pair_count = self._automatic_admissible_pair_count
        automatic_diagnostic = automatic_pair_count == 0
        errors = [abs(float(pair.frequency_error_percent)) for pair in pairs]
        macs = [float(pair.mac) for pair in pairs if pair.mac is not None]
        pair_text = f"{len(pairs)} manual" if automatic_diagnostic and pairs else str(len(pairs))
        self.metric_pairs.configure(text=pair_text)
        self.metric_error.configure(text=EM_DASH if not errors else f"{sum(errors) / len(errors):.2f}%")
        self.metric_mac.configure(text=EM_DASH if not macs else f"{sum(macs) / len(macs):.3f}")
        if automatic_diagnostic:
            self.metric_geometry_caption.configure(text="STATE")
            detail = "manual review only" if pairs else "gates not satisfied"
            self.metric_geometry.configure(text=f"Diagnostic \u2014 {detail}")
        elif pairs:
            self.metric_geometry_caption.configure(text="GEOMETRY MATCH")
            self.metric_geometry.configure(text=f"{result.geometry.matched_fraction:.1%}")
        else:
            self.metric_geometry_caption.configure(text="STATE")
            self.metric_geometry.configure(text="Diagnostic \u2014 gates not satisfied")
        if not pairs and not self.table.get_children():
            values = [""] * len(self.table["columns"])
            columns = list(self.table["columns"])
            if "status" in columns:
                values[columns.index("status")] = "Diagnostic \u2014 no admissible pairs"
            if "comment" in columns:
                values[columns.index("comment")] = "Scientific acceptance gates were not satisfied."
            self.table.insert("", "end", values=values, tags=("diagnostic",))
        if self.experimental_unit_source.get() != "manually selected":
            try:
                unit, source = experimental_unit_from_metadata(result.experimental.metadata)
                self.experimental_coordinate_unit.set(unit)
                self.experimental_unit_source.set(source)
                self._sync_coordinate_mapping()
            except Exception:
                pass

    def rebuild_metric_cards(self) -> None:
        frame = self.metric_pairs.master
        for child in frame.winfo_children():
            child.destroy()
        specifications = (
            ("MATCHED PAIRS", "metric_pairs"),
            ("MEAN |FREQ. ERROR|", "metric_error"),
            ("MEAN MAC", "metric_mac"),
            ("GEOMETRY MATCH", "metric_geometry"),
        )
        self._metric_cards = []
        for caption, attribute in specifications:
            card = ttk.Frame(frame, style="MetricCard.TFrame", padding=(12, 9))
            caption_label = ttk.Label(card, text=caption, style="MetricCaption.TLabel")
            value_label = ttk.Label(card, text=EM_DASH, style="MetricValue.TLabel")
            caption_label.pack(anchor="w")
            value_label.pack(anchor="w", pady=(2, 0))
            setattr(self, attribute, value_label)
            if attribute == "metric_geometry":
                self.metric_geometry_caption = caption_label
            self._metric_cards.append(card)
        frame.columnconfigure(tuple(range(4)), weight=1)
        self._metrics_frame = frame
        self._tooltips.extend((
            Tooltip(self.metric_mac, "MAC is the modal assurance criterion for an admissible paired mode."),
            Tooltip(self.metric_geometry, "Geometry match is the fraction of experimental points mapped within the existing scientific tolerance."),
        ))

    def finalize_tables(self) -> None:
        _configure_tree(self.table, COMPARISON_COLUMNS)
        _ensure_horizontal_scrollbar(self.table)
        self.table.tag_configure("diagnostic", foreground="#7A4D00")
        if hasattr(self, "review_table"):
            _configure_tree(self.review_table, REVIEW_COLUMNS)
            _ensure_horizontal_scrollbar(self.review_table)
        self._tooltips.append(
            Tooltip(
                self.table,
                "Frequency error is signed; Experimental source and Confidence describe the measurement candidate. Diagnostic rows are not accepted pairs.",
            )
        )
        for widget in _walk(self.root):
            if isinstance(widget, ttk.Treeview):
                active = list(widget["columns"])
                for column in active:
                    if not str(widget.heading(column, "text") or "").strip():
                        widget.heading(column, text=str(column).replace("_", " ").title())

    def install_text_editing(self) -> None:
        def handler(action: str):
            def callback(event):
                dispatch_clipboard_action(event.widget, action)
                return "break"
            return callback

        for class_name in ("Entry", "TEntry", "TCombobox", "Text", "Spinbox", "TSpinbox"):
            self.root.bind_class(class_name, "<Control-a>", handler("select_all"))
            self.root.bind_class(class_name, "<Control-A>", handler("select_all"))
            self.root.bind_class(class_name, "<Control-c>", handler("copy"))
            self.root.bind_class(class_name, "<Control-C>", handler("copy"))
            self.root.bind_class(class_name, "<Control-x>", handler("cut"))
            self.root.bind_class(class_name, "<Control-X>", handler("cut"))
            self.root.bind_class(class_name, "<Control-v>", handler("paste"))
            self.root.bind_class(class_name, "<Control-V>", handler("paste"))
            self.root.bind_class(class_name, "<Button-3>", self._show_text_context_menu, add="+")

    def show_text_context_menu(self, event) -> str:
        widget = event.widget
        try:
            state = str(widget.cget("state"))
        except Exception:
            state = "normal"
        menu = tk.Menu(self.root, tearoff=False)
        if state == "normal":
            menu.add_command(label="Cut", command=lambda: dispatch_clipboard_action(widget, "cut"))
        menu.add_command(label="Copy", command=lambda: dispatch_clipboard_action(widget, "copy"))
        if state == "normal":
            menu.add_command(label="Paste", command=lambda: dispatch_clipboard_action(widget, "paste"))
        menu.add_separator()
        menu.add_command(label="Select All", command=lambda: dispatch_clipboard_action(widget, "select_all"))
        try:
            widget.focus_set()
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def persistent_snapshot(self) -> dict:
        return {
            "abaqus_path": self.abaqus_path.get(),
            "experimental_path": self.experimental_path.get(),
            "workspace_path": self.workspace_path.get(),
            "abaqus_command": self.abaqus_command.get(),
            "start_mode": self.start_mode.get(),
            "end_mode": self.end_mode.get(),
            "abaqus_model_unit": self.abaqus_model_unit.get(),
            "experimental_coordinate_unit": self.experimental_coordinate_unit.get(),
            "experimental_unit_source": self.experimental_unit_source.get(),
            "coordinate_mapping_mode": self.coordinate_mapping_mode.get(),
            "custom_coordinate_scale": self.custom_coordinate_scale.get(),
            "manual_reviews": self.manual_reviews,
        }

    def reset_dirty(self) -> None:
        self.dirty_tracker.reset(self._persistent_snapshot())
        self._update_project_indicator()

    def on_persistent_change(self, *_args) -> None:
        self._sync_coordinate_mapping()
        self.dirty_tracker.update(self._persistent_snapshot())
        self._update_project_indicator()
        self._refresh_readiness()
        self._save_last_session()

    def update_project_indicator(self) -> None:
        if not hasattr(self, "project_name_label"):
            return
        if self.project_path is not None:
            name = self.project_path.name
        elif self._session_recovered:
            name = "Recovered session (not explicitly saved)"
        else:
            name = "Unsaved project"
        self.project_name_label.configure(text=f"Project: {name}{' *' if self.dirty_tracker.dirty else ''}")

    def install_dirty_tracking(self) -> None:
        variables = (
            self.abaqus_path,
            self.experimental_path,
            self.workspace_path,
            self.abaqus_command,
            self.start_mode,
            self.end_mode,
            self.abaqus_model_unit,
            self.experimental_coordinate_unit,
            self.coordinate_mapping_mode,
            self.custom_coordinate_scale,
        )
        self._persistent_traces = [variable.trace_add("write", self._on_persistent_change) for variable in variables]
        self.root.bind_all("<Control-s>", lambda _event: (self._save_project(), "break")[1])
        self.root.bind_all("<Control-Shift-s>", lambda _event: (self._save_project_as(), "break")[1])
        self.root.bind_all("<Control-S>", lambda _event: (self._save_project_as(), "break")[1])

    def project_payload_for_self(self) -> dict:
        from project_review import project_payload

        payload = project_payload(
            abaqus_path=self.abaqus_path.get(),
            experimental_path=self.experimental_path.get(),
            workspace_path=self.workspace_path.get(),
            abaqus_command=self.abaqus_command.get(),
            start_mode=int(self.start_mode.get()),
            end_mode=int(self.end_mode.get()),
            coordinate_scale="auto" if self.coordinate_mapping_mode.get() == "automatic" else self.custom_coordinate_scale.get(),
            manual_reviews=self.manual_reviews,
            result=self.result,
        )
        payload["inputs"].update(
            {
                "abaqus_model_length_unit": self.abaqus_model_unit.get(),
                "experimental_coordinate_unit": self.experimental_coordinate_unit.get(),
                "experimental_unit_source": self.experimental_unit_source.get(),
                "coordinate_mapping_mode": self.coordinate_mapping_mode.get(),
                "custom_coordinate_scale": self.custom_coordinate_scale.get(),
            }
        )
        return payload

    def apply_project(self, payload: dict, project_path: Optional[Path] = None) -> None:
        original_apply_project(self, payload, project_path)
        inputs = payload.get("inputs", {})
        legacy_scale = str(inputs.get("coordinate_scale", "auto"))
        self.abaqus_model_unit.set(str(inputs.get("abaqus_model_length_unit", "mm")))
        self.experimental_coordinate_unit.set(str(inputs.get("experimental_coordinate_unit", "m")))
        self.experimental_unit_source.set(str(inputs.get("experimental_unit_source", "inferred; verify for this test setup")))
        mode = str(inputs.get("coordinate_mapping_mode", "automatic" if legacy_scale.lower() in {"", "auto", "automatic"} else "custom"))
        self.coordinate_mapping_mode.set(mode)
        self.custom_coordinate_scale.set(str(inputs.get("custom_coordinate_scale", "1.0" if mode == "automatic" else legacy_scale)))
        self._sync_coordinate_mapping()
        if project_path is None:
            self._session_recovered = True
        if hasattr(self, "dirty_tracker") and project_path is not None:
            self._reset_dirty()

    def new_project(self) -> None:
        before = (self.project_path, self.abaqus_path.get(), self.experimental_path.get())
        original_new_project(self)
        after = (self.project_path, self.abaqus_path.get(), self.experimental_path.get())
        if before != after:
            self._session_recovered = False
            self.abaqus_model_unit.set("mm")
            self.experimental_coordinate_unit.set("m")
            self.experimental_unit_source.set("inferred; verify for this test setup")
            self.coordinate_mapping_mode.set("automatic")
            self.custom_coordinate_scale.set("1.0")
            self._reset_dirty()
            self._set_empty_states()
            self._refresh_readiness()

    def save_project(self) -> bool:
        if self.project_path is None:
            return self._save_project_as()
        try:
            write_project(self.project_path, self._project_payload_for_self())
            self._session_recovered = False
            self._reset_dirty()
            self._save_recovery_now()
            self.status.set(f"Project saved: {self.project_path}")
            return True
        except Exception as error:
            messagebox.showerror("Could not save project", str(error))
            return False

    def save_project_as(self) -> bool:
        filename = filedialog.asksaveasfilename(
            title="Save modal-comparator project",
            defaultextension=".amcp.json",
            initialfile="modal_comparison_project.amcp.json",
            filetypes=[("Modal Comparator project", "*.amcp.json"), ("JSON", "*.json")],
        )
        if not filename:
            return False
        previous = self.project_path
        self.project_path = Path(filename)
        if self._save_project():
            return True
        self.project_path = previous
        return False

    def schedule_recovery_save(self) -> None:
        if not self._recovery_preferences["autosave_enabled"] or not hasattr(self, "root"):
            return
        if self._autosave_job is not None:
            try:
                self.root.after_cancel(self._autosave_job)
            except tk.TclError:
                pass
        self._autosave_job = self.root.after(AUTOSAVE_DEBOUNCE_MS, self._save_recovery_now)

    def save_recovery_now(self) -> bool:
        self._autosave_job = None
        if not self._recovery_preferences["autosave_enabled"]:
            return False
        try:
            write_project(LAST_SESSION_PATH, self._project_payload_for_self())
            return True
        except Exception:
            return False

    def restore_last_session(self) -> None:
        if not self._recovery_preferences["restore_on_startup"] or not LAST_SESSION_PATH.exists():
            return
        try:
            from project_review import read_project

            self._apply_project_payload(read_project(LAST_SESSION_PATH), None)
            self._session_recovered = True
            self.status.set("Previous session recovered.")
        except Exception:
            self.status.set("Recovery information could not be restored; starting from defaults.")

    def show_recovery_notice(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Previous session recovered")
        window.transient(self.root)
        ttk.Label(window, text="Previous session recovered.\nThis recovery copy is not an explicitly saved project.", justify="left", padding=(18, 18, 18, 8)).pack(fill="x")
        dont_show = tk.BooleanVar(master=window, value=False)
        ttk.Checkbutton(window, text="Don't show this again", variable=dont_show).pack(anchor="w", padx=18, pady=(0, 10))
        buttons = ttk.Frame(window, padding=(18, 0, 18, 16))
        buttons.pack(fill="x")

        def finish(disable: bool) -> None:
            if disable:
                self._recovery_preferences["autosave_enabled"] = False
                self._recovery_preferences["restore_on_startup"] = False
            if dont_show.get():
                self._recovery_preferences["show_recovery_notice"] = False
            try:
                save_recovery_preferences(self._recovery_preferences)
            except OSError:
                pass
            window.destroy()

        ttk.Button(buttons, text="Keep automatic recovery", command=lambda: finish(False)).pack(side="left")
        ttk.Button(buttons, text="Disable automatic recovery", command=lambda: finish(True)).pack(side="left", padx=(8, 0))
        window.protocol("WM_DELETE_WINDOW", lambda: finish(False))
        window.grab_set()

    def install_settings_menu(self) -> None:
        if not hasattr(self, "menu_bar"):
            return
        settings = tk.Menu(self.menu_bar, tearoff=False)
        settings.add_command(label="Session recovery...", command=self._show_recovery_settings)
        self.menu_bar.add_cascade(label="Settings", menu=settings)
        self.settings_menu = settings
        try:
            for index in range(int(self.menu_bar.index("end")) + 1):
                if self.menu_bar.entrycget(index, "label") == "File":
                    file_menu = self.root.nametowidget(self.menu_bar.entrycget(index, "menu"))
                    end = file_menu.index("end")
                    for item in range(int(end) + 1):
                        if file_menu.type(item) == "command" and str(file_menu.entrycget(item, "label")).startswith("Save project as"):
                            file_menu.entryconfigure(item, accelerator="Ctrl+Shift+S")
        except (tk.TclError, TypeError):
            pass

    def show_recovery_settings(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Session recovery")
        window.transient(self.root)
        autosave = tk.BooleanVar(master=window, value=self._recovery_preferences["autosave_enabled"])
        restore = tk.BooleanVar(master=window, value=self._recovery_preferences["restore_on_startup"])
        ttk.Label(window, text="Session recovery", style="Section.TLabel", padding=(16, 16, 16, 8)).pack(anchor="w")
        ttk.Checkbutton(window, text="Automatically save recovery information", variable=autosave).pack(anchor="w", padx=16, pady=4)
        ttk.Checkbutton(window, text="Restore previous session on startup", variable=restore).pack(anchor="w", padx=16, pady=4)
        ttk.Label(window, text="Recovery information is separate from an explicitly saved project file.", style="Secondary.TLabel", padding=(16, 6)).pack(anchor="w")

        def apply() -> None:
            self._recovery_preferences["autosave_enabled"] = autosave.get()
            self._recovery_preferences["restore_on_startup"] = restore.get()
            try:
                save_recovery_preferences(self._recovery_preferences)
            except OSError as error:
                messagebox.showerror("Session recovery", str(error), parent=window)
                return
            window.destroy()

        ttk.Button(window, text="Save settings", command=apply).pack(anchor="e", padx=16, pady=(8, 16))

    def refresh_readiness(self) -> None:
        if self.running:
            return
        ready = bool(self.abaqus_path.get().strip() and self.experimental_path.get().strip())
        self._set_analysis_state(AnalysisState.READY if ready else AnalysisState.NO_DATA)

    def set_empty_states(self, stopped: bool = False) -> None:
        if not self.table.get_children():
            values = [""] * len(self.table["columns"])
            columns = list(self.table["columns"])
            target = "Analysis stopped; run again when ready." if stopped else "Run an analysis to view matched modes."
            if "status" in columns:
                values[columns.index("status")] = target
            self.table.insert("", "end", values=values, tags=("empty",))
        if hasattr(self, "review_table") and not self.review_table.get_children():
            values = [""] * len(self.review_table["columns"])
            columns = list(self.review_table["columns"])
            if "comment" in columns:
                values[columns.index("comment")] = "No candidates are available for manual review."
            self.review_table.insert("", "end", values=values, tags=("empty",))
        self.metric_pairs.configure(text="0" if stopped else EM_DASH)
        self.metric_error.configure(text=EM_DASH)
        self.metric_mac.configure(text=EM_DASH)
        self.metric_geometry_caption.configure(text="STATE" if stopped else "GEOMETRY MATCH")
        self.metric_geometry.configure(text="Stopped" if stopped else EM_DASH)

    def clear_result_presentation(self, message: str) -> None:
        self.item_to_pair.clear()
        self.table.delete(*self.table.get_children())
        if hasattr(self, "review_table"):
            self.review_table.delete(*self.review_table.get_children())
        self._automatic_pairs_by_mode = {}
        self._manual_candidate_pairs = {}
        self.photos.clear()
        labels = [
            getattr(self, name, None)
            for name in (
                "mac_label", "frequency_label", "frf_diagnostics_label",
                "verified_mac_label", "abaqus_automac_label",
                "experimental_automac_label", "comac_label", "cmif_label",
            )
        ] + list(getattr(self, "shape_labels", ()))
        for label in labels:
            if label is not None:
                self._set_visual_placeholder(label, message)
        if hasattr(self, "pair_title"):
            self.pair_title.configure(text=message)
        if hasattr(self, "details"):
            self.details.configure(state="normal")
            self.details.delete("1.0", "end")
            self.details.insert("1.0", message)
            self.details.configure(state="disabled")
        if hasattr(self, "cmif_summary"):
            self.cmif_summary.configure(state="normal")
            self.cmif_summary.delete("1.0", "end")
            self.cmif_summary.insert("1.0", message)
            self.cmif_summary.configure(state="disabled")

    def set_visual_placeholder(self, label, message: str) -> None:
        jobs = getattr(self, "_responsive_resize_jobs", {})
        job = jobs.pop(label, None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
        key = getattr(self, "_responsive_label_keys", {}).pop(label, None)
        if key is not None:
            getattr(self, "_responsive_sources", {}).pop(key, None)
            self.photos.pop(key, None)
        getattr(self, "_responsive_last_render", {}).pop(label, None)
        try:
            label.configure(image="", text=message, anchor="center")
        except tk.TclError:
            pass

    def set_mode_shape_placeholder(self, message: str) -> None:
        for label in getattr(self, "shape_labels", ()):
            self._set_visual_placeholder(label, message)
        if hasattr(self, "pair_title"):
            self.pair_title.configure(text=message)

    def collect_responsive_widgets(self) -> None:
        for widget in _walk(self.root):
            try:
                wrap = int(widget.cget("wraplength"))
            except (tk.TclError, ValueError):
                wrap = 0
            if wrap > 0 and widget not in self._responsive_wrap_labels:
                self._responsive_wrap_labels.append(widget)
        frames = []
        for widget in _walk(self.root):
            if not isinstance(widget, ttk.Frame):
                continue
            children = widget.winfo_children()
            buttons = [child for child in children if isinstance(child, ttk.Button)]
            if len(buttons) >= 2 and len(buttons) == len(children):
                frames.append((widget, buttons))
        self._button_frames = frames

    def schedule_responsive_layout(self, event=None) -> None:
        if event is not None and event.widget is not self.root:
            return
        if self._responsive_job is not None:
            try:
                self.root.after_cancel(self._responsive_job)
            except tk.TclError:
                pass
        self._responsive_job = self.root.after(RESIZE_DEBOUNCE_MS, self._apply_responsive_layout)

    def apply_responsive_layout(self) -> None:
        self._responsive_job = None
        try:
            pixel_width = int(self.root.winfo_width())
            tk_scaling = float(self.root.tk.call("tk", "scaling"))
            width = logical_window_width(pixel_width, tk_scaling)
        except tk.TclError:
            return
        mode = select_layout_mode(width)
        self._layout_mode = mode
        labels = tab_labels_for(mode)
        ordered_tabs = (
            self.input_tab, self.table_tab, self.shape_tab, self.plot_tab,
            self.frf_tab, self.cmif_tab, self.advanced_tab, self.manual_review_tab, self.details_tab,
        )
        for tab, label in zip(ordered_tabs, labels):
            self.tabs.tab(tab, text=label)
        columns = metric_grid_columns(mode, width)
        for card in self._metric_cards:
            card.grid_forget()
        xpad, ypad = responsive_padding(mode)
        for index, card in enumerate(self._metric_cards):
            card.grid(row=index // columns, column=index % columns, sticky="nsew", padx=(0 if index % columns == 0 else xpad, 0), pady=(0, ypad))
        for column in range(4):
            self._metrics_frame.columnconfigure(column, weight=1 if column < columns else 0)
        wrap = text_wrap_width(width, mode)
        for label in self._responsive_wrap_labels:
            try:
                label.configure(wraplength=wrap)
            except tk.TclError:
                pass
        for frame, buttons in self._button_frames:
            count = button_grid_columns(mode, len(buttons))
            for button in buttons:
                button.pack_forget()
                button.grid_forget()
            for index, button in enumerate(buttons):
                button.grid(row=index // count, column=index % count, sticky="w", padx=(0, 7), pady=(0, 5))
        padding = responsive_padding(mode)[0]
        for tab in ordered_tabs:
            try:
                tab.configure(padding=padding)
            except tk.TclError:
                pass
        refresh = getattr(self, "_refresh_responsive_images", None)
        if callable(refresh):
            self.root.after_idle(refresh)

    def close_requested(self) -> None:
        if self.running:
            choice = _choice_dialog(
                self.root,
                "Analysis is running",
                "An analysis is currently running.\nStop the analysis and close the application?",
                (("stop", "Stop and close"), ("keep", "Keep running")),
            )
            if choice != "stop":
                return
            self._close_after_cancel = True
            self._request_stop()
            self.root.after(STOP_CLOSE_TIMEOUT_MS, self._close_stop_timeout)
            return
        self._finish_close()

    def close_stop_timeout(self) -> None:
        if self.running and self._close_after_cancel:
            self._close_after_cancel = False
            messagebox.showwarning(
                "Still stopping",
                "The current processing stage did not stop within the close timeout. "
                "The application will remain open so no analysis process is orphaned.",
            )

    def post_to_ui(self, callback) -> bool:
        if self._ui_closing:
            return False
        try:
            self.root.after(0, lambda: callback() if not self._ui_closing else None)
            return True
        except (tk.TclError, RuntimeError):
            return False

    def finish_close(self) -> None:
        process = self._owned_analysis_process
        if process is not None and process.poll() is None:
            messagebox.showwarning(
                "Close blocked",
                "An Abaqus process launched by this application is still active. "
                "Close is blocked until that owned process exits.",
            )
            return
        if self.dirty_tracker.dirty:
            project_name = self.project_path.name if self.project_path is not None else "this unsaved project"
            choice = _choice_dialog(
                self.root,
                "Save project changes",
                f"Save changes to {project_name}?",
                (("save", "Save"), ("discard", "Don't save"), ("cancel", "Cancel")),
            )
            if choice == "cancel" or choice is None:
                return
            if choice == "save" and not self._save_project():
                return
        if self._recovery_preferences["autosave_enabled"]:
            self._save_recovery_now()
        self._ui_closing = True
        self.root.destroy()

    def set_manual_review(self, *args, **kwargs) -> None:
        original_set_manual_review(self, *args, **kwargs)
        self._on_persistent_change()

    def manual_reset(self) -> None:
        before = dict(self.manual_reviews)
        original_manual_reset(self)
        if before != self.manual_reviews:
            self._on_persistent_change()

    def refresh_review_table(self) -> None:
        original_refresh_review(self)
        if not hasattr(self, "review_table"):
            return
        self.review_table.tag_configure("automatic", background="#F4F6F8")
        self.review_table.tag_configure("manual", background="#E8F1FB")
        self.review_table.tag_configure("rejected", background="#FCE8E6")
        columns = list(self.review_table["columns"])
        if "decision" not in columns:
            return
        index = columns.index("decision")
        for item in self.review_table.get_children():
            values = list(self.review_table.item(item, "values"))
            decision = str(values[index] if index < len(values) else "").lower()
            tag = "automatic" if "auto" in decision else "rejected" if "reject" in decision else "manual"
            self.review_table.item(item, tags=(tag,))

    application_class.__init__ = workflow_init
    application_class._build_input = build_input
    application_class._responsive_file_row = responsive_file_row
    application_class._sync_coordinate_mapping = sync_coordinate_mapping
    application_class._scroll_input_tab = scroll_input_tab
    application_class._experimental_unit_selected = experimental_unit_selected
    application_class._validate = workflow_validate
    application_class._detect_abaqus_installations = detect_abaqus
    application_class._select_abaqus_installation = select_abaqus
    application_class._browse_abaqus_command = browse_abaqus
    application_class._toggle_abaqus_advanced = toggle_abaqus_advanced
    application_class._test_abaqus = test_abaqus
    application_class._set_analysis_state = set_analysis_state
    application_class._set_analysis_stage = set_analysis_stage
    application_class._start = start_analysis
    application_class._request_stop = request_stop
    application_class._cancelled = cancelled
    application_class._complete = complete
    application_class._failed = failed
    application_class._populate = populate
    application_class._rebuild_metric_cards = rebuild_metric_cards
    application_class._finalize_tables = finalize_tables
    application_class._install_text_editing = install_text_editing
    application_class._show_text_context_menu = show_text_context_menu
    application_class._persistent_snapshot = persistent_snapshot
    application_class._reset_dirty = reset_dirty
    application_class._on_persistent_change = on_persistent_change
    application_class._update_project_indicator = update_project_indicator
    application_class._install_dirty_tracking = install_dirty_tracking
    application_class._project_payload_for_self = project_payload_for_self
    application_class._apply_project_payload = apply_project
    application_class._new_project = new_project
    application_class._save_project = save_project
    application_class._save_project_as = save_project_as
    application_class._save_last_session = schedule_recovery_save
    application_class._save_recovery_now = save_recovery_now
    application_class._restore_last_session = restore_last_session
    application_class._show_recovery_notice = show_recovery_notice
    application_class._install_settings_menu = install_settings_menu
    application_class._show_recovery_settings = show_recovery_settings
    application_class._refresh_readiness = refresh_readiness
    application_class._set_empty_states = set_empty_states
    application_class._set_visual_placeholder = set_visual_placeholder
    application_class._set_mode_shape_placeholder = set_mode_shape_placeholder
    application_class._clear_result_presentation = clear_result_presentation
    application_class._collect_responsive_widgets = collect_responsive_widgets
    application_class._schedule_responsive_layout = schedule_responsive_layout
    application_class._apply_responsive_layout = apply_responsive_layout
    application_class._close_requested = close_requested
    application_class._close_stop_timeout = close_stop_timeout
    application_class._post_to_ui = post_to_ui
    application_class._finish_close = finish_close
    application_class._set_manual_review = set_manual_review
    application_class._manual_reset = manual_reset
    application_class._refresh_review_table = refresh_review_table
    _INSTALLED = True
