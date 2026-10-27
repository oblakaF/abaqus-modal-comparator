"""APP-UI.1: the Home screen of the main window (a friendly overview; the 11 expert tabs are unchanged).

The Home screen shows four areas:

- source data;
- analysis readiness;
- results;
- material properties.

It owns no data and starts no computation of its own. Every action calls the existing handlers of the main window:

- file choice: ``_choose_abaqus`` / ``_choose_experiment``;
- modal-set choice: ``_experimental_modal_set_selected``;
- analysis: ``_start`` / ``_request_stop``.

Every value shown is read from the window's existing state:

- the input variables and the modal-set discovery state;
- ``analysis_state``, ``status``, ``result`` and the diagnostic export source;
- the metric cards of 2. Comparison table;
- the material-identification evidence and Auto-ID selection.

So an invalidated or stale result disappears from Home exactly when it disappears from the expert tabs. No material
property value is shown: this version identifies none.
"""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk

from ui_policy import AnalysisState, EM_DASH, LayoutMode, responsive_layout_width, select_layout_mode

HOME, EXPERT = "home", "expert"
OK, NEEDED, WARN, WAIT, INFO = "ok", "needed", "warn", "wait", "info"
MARKS = {OK: "✔", NEEDED: "✖", WARN: "⚠", WAIT: "…", INFO: "ℹ"}
COLOURS = {OK: "#1E7B34", NEEDED: "#B3261E", WARN: "#8A5A00", WAIT: "#8A5A00", INFO: "#2F5D8A"}
# the input variables whose change refreshes Home (the result itself is followed through ``status``)
WATCHED_VARIABLES = (
    "status", "abaqus_path", "experimental_path", "experimental_modal_set_display", "experimental_modal_set_key",
    "experimental_modal_set_summary", "abaqus_installation_label", "abaqus_model_unit",
    "experimental_coordinate_unit", "start_mode", "end_mode",
)
MATERIAL_STATUS = (
    "Not determined. This version does not identify material properties: production Auto-ID is not authorised "
    "({state}). No elastic constant (E1, E2, G12, ...) is shown as identified anywhere in the program; the expert "
    "section shows readiness checks and evidence only."
)
NO_RESULT_TEXT = "No analysis result yet. Choose both files, then run the analysis."
DIAGNOSTIC_TEXT = (
    "Frequency-only diagnostic: the physical orientation of the measurement could not be established, so no mode "
    "pairs and no MAC were computed. The FE and measured frequencies can be compared side by side only."
)


def _get(variable, default: str = "") -> str:
    try:
        return str(variable.get()).strip()
    except (tk.TclError, ValueError, AttributeError):
        return default


def short_path(path: Path, limit: int = 64) -> str:
    """A long folder shown as its start and its last two parts (a path has no spaces to wrap at)."""
    text = str(path)
    parts = path.parts
    if len(text) <= limit or len(parts) <= 3:
        return text
    return str(Path(parts[0], parts[1], "…", *parts[-2:]))


def describe_file(text: str, kind: str) -> tuple[str, str, str]:
    """(state, file name, explanation) of a chosen input path; only the path is checked, nothing is read."""
    if not text:
        hint = ("an Abaqus .odb or an extracted manifest.json" if kind == "fe"
                else "a Simcenter Testlab .unv / .uff file (or an .lms with its exported UNV/UFF beside it)")
        return NEEDED, "Not chosen", f"Choose {hint}."
    path = Path(text)
    if not path.exists():
        return NEEDED, path.name, f"The file is not found: {path}"
    if kind == "fe":
        if path.name.lower() == "manifest.json":
            note = "Extracted Abaqus results (no Abaqus run is needed)."
        elif path.suffix.lower() == ".odb":
            note = "Abaqus ODB: its modes are extracted with Abaqus when the analysis runs."
        else:
            note = "Abaqus results file."
    else:
        note = "Simcenter Testlab measurement file."
    return OK, path.name, f"{note}\nFolder: {short_path(path.parent)}"


def modal_set_state(app) -> tuple[str, str]:
    """(state, plain text) of the experimental modal set, from the existing modal-set discovery."""
    state = getattr(app, "_modal_set_discovery_state", "idle")
    sets = list(getattr(app, "available_experimental_modal_sets", []) or [])
    key = _get(getattr(app, "experimental_modal_set_key", None))
    if not _get(getattr(app, "experimental_path", None)):
        return NEEDED, "Choose the experimental file first."
    if state == "loading" or state == "idle":
        return WAIT, "Reading the modal sets of the experimental file..."
    if state == "error":
        return NEEDED, "The experimental file could not be inspected: " + _get(app.experimental_modal_set_summary)
    if not sets:
        return INFO, ("No fitted modal set in the file: its other modal records or FRF peaks are used "
                      "(FRF peaks are provisional, not validated modes).")
    if key in {item.key for item in sets}:
        return OK, _get(app.experimental_modal_set_display)
    if len(sets) > 1:
        return NEEDED, f"The file has {len(sets)} fitted modal sets: choose the one to compare."
    return OK, _get(app.experimental_modal_set_display)


def abaqus_state(app) -> tuple[str, str]:
    path = _get(getattr(app, "abaqus_path", None))
    if Path(path).suffix.lower() != ".odb":
        return INFO, "Not needed for extracted results (manifest.json)."
    installations = getattr(app, "_abaqus_installations", {}) or {}
    if installations:
        return OK, f"Found: {_get(app.abaqus_installation_label)}"
    return WARN, ("No Abaqus installation was found. An .odb needs Abaqus unless its modes were already extracted "
                  "into the output workspace; an extracted manifest.json needs none. Abaqus can be set in Expert mode "
                  "> 1. Files and analysis.")


def readiness_rows(app) -> list[tuple[str, str, str]]:
    """(state, caption, text) rows of the readiness checklist."""
    rows = []
    for kind, caption, variable in (("fe", "Abaqus results", app.abaqus_path),
                                    ("experimental", "Experiment", app.experimental_path)):
        state, name, _ = describe_file(_get(variable), kind)
        text = name if state == OK else "Missing" if name == "Not chosen" else f"Not found: {name}"
        rows.append((state, caption, text))
    state, text = modal_set_state(app)
    rows.append((state, "Modal set", text))
    state, text = abaqus_state(app)
    rows.append((state, "Abaqus", text))
    rows.append((INFO, "Units", f"Abaqus model in {_get(app.abaqus_model_unit, '?')}, experiment in "
                                f"{_get(app.experimental_coordinate_unit, '?')}: you confirm them when you press Run."))
    rows.append((INFO, "Abaqus modes", f"{_get(app.start_mode, '?')} to {_get(app.end_mode, '?')}"))
    return rows


def readiness_verdict(app) -> tuple[str, str]:
    state = getattr(app, "analysis_state", AnalysisState.NO_DATA)
    if getattr(app, "running", False) or state in (AnalysisState.RUNNING, AnalysisState.STOPPING):
        return WAIT, f"The analysis is running: {_get(app.status)}"
    rows = readiness_rows(app)
    missing = [caption for row_state, caption, _ in rows if row_state == NEEDED]
    if any(row_state == WAIT for row_state, _, _ in rows):
        return WAIT, "Wait: the experimental file is being read."
    if missing:
        return NEEDED, "Not ready yet. Still needed: " + ", ".join(missing) + "."
    if any(row_state == WARN for row_state, _, _ in rows):
        return OK, "Ready: the analysis can be run (see the warning above)."
    return OK, "Ready: the analysis can be run."


def result_summary(app) -> tuple[str, str, list[tuple[str, str]]]:
    """(state, plain text, [(caption, value)]) of the result shown in the expert tabs."""
    state = getattr(app, "analysis_state", AnalysisState.NO_DATA)
    result = getattr(app, "result", None)
    if getattr(app, "running", False) or state in (AnalysisState.RUNNING, AnalysisState.STOPPING):
        return WAIT, "The analysis is running; the previous result is no longer shown.", []
    if result is not None:
        values = [(caption, _label_text(app, name)) for caption, name in (
            ("Matched mode pairs", "metric_pairs"), ("Mean frequency difference", "metric_error"),
            ("Mean MAC", "metric_mac"))]
        values.append((_label_text(app, "metric_geometry_caption").capitalize() or "State",
                       _label_text(app, "metric_geometry")))
        if result.pairs and state is AnalysisState.SUCCESS:
            return OK, ("Comparison complete: FE and measured modes are paired after the physical registration "
                        "(geometry) was established. Open the frequencies, the mode shapes or the MAC below."), values
        return INFO, ("Analysis complete, but the scientific acceptance checks were not satisfied: there are no "
                      "admissible mode pairs. See the details in Expert mode."), values
    if getattr(app, "_diagnostic_export_source", None) is not None:
        return INFO, DIAGNOSTIC_TEXT, [("Mode pairs", "none"), ("MAC", "not computed")]
    if state is AnalysisState.ERROR:
        return NEEDED, _get(app.status) or "The analysis could not be completed.", []
    if state is AnalysisState.DIAGNOSTIC:
        return INFO, _get(app.status), []
    notice = getattr(app, "_stale_result_notice", None)
    if notice:
        return NEEDED, str(notice), []
    if state is AnalysisState.STOPPED:
        return INFO, "The analysis was stopped. Run it again when ready.", []
    return INFO, NO_RESULT_TEXT, []


def _label_text(app, name: str) -> str:
    label = getattr(app, name, None)
    try:
        return str(label.cget("text")) if label is not None else EM_DASH
    except tk.TclError:
        return EM_DASH


def material_summary(app) -> list[tuple[str, str, str]]:
    """(state, caption, text) rows of the material-property area; no property value is ever shown."""
    from services.campaign_execution_plan import NOT_AUTHORISED

    model = getattr(app, "material_identification_evidence_view_model", None)
    names = ("sensitivity", "identifiability", "identification", "validation")
    present = [name for name in names if getattr(model, name, None) is not None]
    if present:
        bound = getattr(model, "model", None) is not None
        kind = (f"bound to model {getattr(model.model, 'model_id', '?')}" if bound
                else "historical, not bound to a model")
        evidence = f"{len(present)} of 4 evidence records loaded ({', '.join(present)}; {kind})."
    else:
        evidence = "No identification evidence is loaded in this session."
    selection = str(getattr(app, "auto_id_summary", None) or "No specimen or campaign is selected.")
    return [
        (NEEDED, "Material constants", MATERIAL_STATUS.format(state=NOT_AUTHORISED)),
        (INFO, "Existing evidence", evidence),
        (INFO, "Auto-ID selection", selection.splitlines()[0] if selection else selection),
    ]


class HomeDashboard:
    """The Home screen; ``app`` is the main window (ModalComparatorApp)."""

    def __init__(self, app, parent) -> None:
        self.app = app
        self.frame = ttk.Frame(parent)
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(0, weight=1)
        background = ttk.Style(parent).lookup("TFrame", "background") or None
        self.canvas = tk.Canvas(self.frame, highlightthickness=0, borderwidth=0,
                                **({"background": background} if background else {}))
        self.scrollbar = ttk.Scrollbar(self.frame, orient="vertical", command=self.canvas.yview)
        self.content = ttk.Frame(self.canvas, padding=(2, 4))
        self._window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.bind("<Configure>", self._canvas_resized, add="+")
        self.content.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
                          add="+")
        app.root.bind_all("<MouseWheel>", self._wheel, add="+")
        self._wrapped: list[tuple[ttk.Label, ttk.Frame]] = []
        self._columns = None
        self._refresh_job = None
        self._rewrap_job = None
        self.cards = {}
        self._build_sources()
        self._build_readiness()
        self._build_results()
        self._build_material()
        self._layout(2)
        self.frame.bind("<Destroy>", self._cancel_jobs, add="+")
        for name in WATCHED_VARIABLES:
            variable = getattr(app, name, None)
            if variable is not None and hasattr(variable, "trace_add"):
                variable.trace_add("write", lambda *_args: self.schedule_refresh())
        self.refresh()

    # ------------------------------------------------------------------------------------------------ building

    def _card(self, key: str, title: str, subtitle: str) -> ttk.Frame:
        card = ttk.Frame(self.content, style="MetricCard.TFrame", padding=(14, 12))
        card.columnconfigure(1, weight=1)
        ttk.Label(card, text=title, style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        self._wrap(ttk.Label(card, text=subtitle, style="Secondary.TLabel", justify="left"), card).grid(
            row=1, column=0, columnspan=3, sticky="ew", pady=(2, 8))
        card.bind("<Configure>", lambda _event: self._schedule_rewrap(), add="+")
        self.cards[key] = card
        return card

    def _wrap(self, label: ttk.Label, card: ttk.Frame) -> ttk.Label:
        self._wrapped.append((label, card))
        return label

    def _build_sources(self) -> None:
        app = self.app
        card = self._card("sources", "1  Source data", "The two result files to compare. Nothing is read or run "
                                                         "until you press Run analysis.")
        self.source_rows = {}
        for index, (kind, caption, command) in enumerate((("fe", "Abaqus results", app._choose_abaqus),
                                                          ("experimental", "Simcenter experiment",
                                                           app._choose_experiment))):
            top = 2 + 2 * index  # the file row, then its note
            ttk.Label(card, text=caption, style="MetricCaption.TLabel").grid(row=top, column=0, sticky="nw",
                                                                             pady=(6, 0), padx=(0, 10))
            name = ttk.Label(card, text="", style="Status.TLabel", justify="left")
            name.grid(row=top, column=1, sticky="ew", pady=(6, 0))
            button = ttk.Button(card, text="Choose...", command=command)
            button.grid(row=top, column=2, sticky="e", pady=(6, 0), padx=(8, 0))
            note = self._wrap(ttk.Label(card, text="", style="Secondary.TLabel", justify="left"), card)
            note.grid(row=top + 1, column=1, columnspan=2, sticky="ew")
            self.source_rows[kind] = (name, note, button)
        ttk.Label(card, text="Modal set", style="MetricCaption.TLabel").grid(row=6, column=0, sticky="w",
                                                                            pady=(10, 0), padx=(0, 10))
        self.modal_set_combo = ttk.Combobox(card, textvariable=app.experimental_modal_set_display, state="readonly")
        self.modal_set_combo.grid(row=6, column=1, columnspan=2, sticky="ew", pady=(10, 0))
        self.modal_set_combo.bind("<<ComboboxSelected>>", app._experimental_modal_set_selected, add="+")
        buttons = ttk.Frame(card)
        buttons.grid(row=7, column=0, columnspan=3, sticky="w", pady=(12, 0))
        ttk.Button(buttons, text="All settings (mode range, units, Abaqus)...",
                   command=lambda: app._show_expert(app.input_tab)).grid(row=0, column=0, sticky="w")

    def _build_readiness(self) -> None:
        app = self.app
        card = self._card("readiness", "2  Analysis readiness", "What is loaded, what is still missing, and whether "
                                                                "the analysis can be run.")
        self.checklist = ttk.Frame(card)
        self.checklist.grid(row=2, column=0, columnspan=3, sticky="ew")
        self.checklist.columnconfigure(2, weight=1)
        self.check_rows = []
        for row in range(6):
            mark = ttk.Label(self.checklist, text="", width=2)
            caption = ttk.Label(self.checklist, text="", style="MetricCaption.TLabel")
            text = self._wrap(ttk.Label(self.checklist, text="", justify="left"), card)
            mark.grid(row=row, column=0, sticky="nw", pady=2)
            caption.grid(row=row, column=1, sticky="nw", padx=(2, 10), pady=2)
            text.grid(row=row, column=2, sticky="ew", pady=2)
            self.check_rows.append((mark, caption, text))
        self.verdict = self._wrap(ttk.Label(card, text="", style="Section.TLabel", justify="left"), card)
        self.verdict.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(10, 6))
        buttons = ttk.Frame(card)
        buttons.grid(row=4, column=0, columnspan=3, sticky="w")
        self.run_button = ttk.Button(buttons, text="Run analysis", command=app._start)
        self.run_button.grid(row=0, column=0, sticky="w")
        self.stop_button = ttk.Button(buttons, text="Stop", command=app._request_stop)
        self.stop_button.grid(row=0, column=1, sticky="w", padx=(8, 0))

    def _build_results(self) -> None:
        app = self.app
        card = self._card("results", "3  Results", "The state of the last analysis, as shown in the expert tabs.")
        self.result_text = self._wrap(ttk.Label(card, text="", justify="left"), card)
        self.result_text.grid(row=2, column=0, columnspan=3, sticky="ew")
        self.result_values = ttk.Frame(card)
        self.result_values.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        buttons = ttk.Frame(card)
        buttons.grid(row=4, column=0, columnspan=3, sticky="w", pady=(10, 0))
        self.result_buttons = {}
        for column, (key, text, tab) in enumerate((("frequencies", "Frequencies and pairs", "table_tab"),
                                                   ("shapes", "Mode shapes", "shape_tab"),
                                                   ("mac", "MAC matrix", "plot_tab"))):
            button = ttk.Button(buttons, text=text, command=lambda tab=tab: app._show_expert(getattr(app, tab)))
            button.grid(row=column // 2, column=column % 2, sticky="w", padx=(0, 8), pady=(0, 4))
            self.result_buttons[key] = button

    def _build_material(self) -> None:
        card = self._card("material", "4  Material properties", "Identification of material properties from the "
                                                                "modal data (expert section 9).")
        self.material_rows = []
        for row in range(3):
            mark = ttk.Label(card, text="", width=2)
            caption = ttk.Label(card, text="", style="MetricCaption.TLabel")
            text = self._wrap(ttk.Label(card, text="", justify="left"), card)
            mark.grid(row=row + 2, column=0, sticky="nw", pady=2)
            caption.grid(row=row + 2, column=1, sticky="nw", padx=(0, 10), pady=2)
            text.grid(row=row + 2, column=2, sticky="ew", pady=2)
            self.material_rows.append((mark, caption, text))
        card.columnconfigure(1, weight=0)
        card.columnconfigure(2, weight=1)
        ttk.Button(card, text="Open the expert Auto-ID section", command=self.open_auto_id).grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(10, 0))

    # ------------------------------------------------------------------------------------------------ layout

    def _canvas_resized(self, event) -> None:
        self.canvas.itemconfigure(self._window, width=max(1, event.width))
        try:
            width = responsive_layout_width(event.width, float(self.app.root.tk.call("tk", "scaling")),
                                            self.app.ui_scale_percent.get())
        except (tk.TclError, AttributeError):
            width = event.width
        self._layout(1 if select_layout_mode(width) is LayoutMode.COMPACT else 2)

    def _layout(self, columns: int) -> None:
        if columns == self._columns:
            return
        self._columns = columns
        order = ("sources", "readiness", "results", "material")
        for card in self.cards.values():
            card.grid_forget()
        for column in range(2):
            used = column < columns
            self.content.columnconfigure(column, weight=1 if used else 0, uniform="home" if used else "")
        for index, key in enumerate(order):
            row, column = divmod(index, columns)
            self.cards[key].grid(row=row, column=column, sticky="nsew", padx=(0 if column == 0 else 6, 0),
                                 pady=(0, 8))

    def _rewrap(self, card, width: int) -> bool:
        """Each wrapped label wraps at the card's right edge, from where its column starts. False when a label is not
        placed yet (the cards are being laid out again): its place is unknown, so it is wrapped on the next pass."""
        placed = True
        for label, owner in self._wrapped:
            if owner is card:
                try:
                    if not label.winfo_ismapped():
                        placed = False
                        continue
                    offset = max(0, label.winfo_rootx() - card.winfo_rootx())
                    wrap = max(160, width - offset - 30)
                    if str(label.cget("wraplength")) != str(wrap):
                        label.configure(wraplength=wrap)
                except tk.TclError:
                    pass
        return placed

    def _schedule_rewrap(self) -> None:
        """After the layout has settled (a resize, a new text, Home shown again), never during it."""
        if self._rewrap_job is None:
            try:
                self._rewrap_job = self.app.root.after(40, self._rewrap_all)
            except tk.TclError:
                self._rewrap_job = None

    def _rewrap_all(self) -> None:
        self._rewrap_job = None
        try:
            if not self.frame.winfo_ismapped():
                return  # Home is hidden: wrapped when it is shown again (refresh)
            placed = [self._rewrap(card, card.winfo_width()) for card in self.cards.values()]
        except tk.TclError:
            return
        if not all(placed):
            self._schedule_rewrap()

    def _cancel_jobs(self, event=None) -> None:
        if event is not None and event.widget is not self.frame:
            return
        for name in ("_refresh_job", "_rewrap_job"):
            job = getattr(self, name)
            setattr(self, name, None)
            if job is not None:
                try:
                    self.app.root.after_cancel(job)
                except tk.TclError:
                    pass

    def _wheel(self, event) -> None:
        try:
            if not self.frame.winfo_ismapped():
                return
            widget = self.app.root.winfo_containing(event.x_root, event.y_root)
            while widget is not None and widget is not self.canvas:
                widget = getattr(widget, "master", None)
            if widget is not None:
                self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        except (tk.TclError, KeyError):
            pass

    # ------------------------------------------------------------------------------------------------ state

    def schedule_refresh(self) -> None:
        if self._refresh_job is None:
            try:
                self._refresh_job = self.app.root.after_idle(self.refresh)
            except tk.TclError:
                self._refresh_job = None

    def refresh(self) -> None:
        self._refresh_job = None
        app = self.app
        try:
            for kind, variable in (("fe", app.abaqus_path), ("experimental", app.experimental_path)):
                state, name, note = describe_file(_get(variable), kind)
                label, note_label, _button = self.source_rows[kind]
                label.configure(text=f"{MARKS[state]}  {name}", foreground=COLOURS[state])
                note_label.configure(text=note)
            self.modal_set_combo.configure(values=tuple(app.experimental_modal_set_combo.cget("values")))
            for (mark, caption, text), (state, title, value) in zip(self.check_rows, readiness_rows(app)):
                mark.configure(text=MARKS[state], foreground=COLOURS[state])
                caption.configure(text=title)
                text.configure(text=value)
            state, verdict = readiness_verdict(app)
            self.verdict.configure(text=f"{MARKS[state]}  {verdict}", foreground=COLOURS[state])
            # Run on Home only when Home says ready; the existing Run checks every input again when pressed
            ready = state == OK and str(app.run_button.cget("state")) == "normal"
            self.run_button.configure(state="normal" if ready else "disabled")
            self.stop_button.configure(state=str(app.stop_button.cget("state")))
            locked = getattr(app, "analysis_state", None) in (AnalysisState.RUNNING, AnalysisState.STOPPING)
            for widget, idle in ((self.source_rows["fe"][2], "normal"), (self.source_rows["experimental"][2], "normal"),
                                 (self.modal_set_combo, "readonly")):  # as the same controls on 1. Files
                widget.configure(state="disabled" if locked else idle)
            self._refresh_results()
            for (mark, caption, text), (state, title, value) in zip(self.material_rows, material_summary(app)):
                mark.configure(text=MARKS[state], foreground=COLOURS[state])
                caption.configure(text=title)
                text.configure(text=value)
            self._schedule_rewrap()  # the columns may have moved with the new texts
        except tk.TclError:
            pass  # the window is closing

    def _refresh_results(self) -> None:
        app = self.app
        state, text, values = result_summary(app)
        self.result_text.configure(text=f"{MARKS[state]}  {text}", foreground=COLOURS[state])
        for child in self.result_values.winfo_children():
            child.destroy()
        if values:
            self.result_values.grid()
        else:
            self.result_values.grid_remove()  # an emptied frame would keep its former height
        for row, (caption, value) in enumerate(values):
            ttk.Label(self.result_values, text=caption, style="MetricCaption.TLabel").grid(
                row=row, column=0, sticky="nw", padx=(0, 12), pady=1)
            ttk.Label(self.result_values, text=value.replace("\n", "   |   ")).grid(row=row, column=1, sticky="w",
                                                                                 pady=1)
        comparison = getattr(app, "result", None) is not None
        diagnostic = getattr(app, "_diagnostic_export_source", None) is not None
        available = (comparison or diagnostic) and not getattr(app, "running", False)
        for key, button in self.result_buttons.items():
            enabled = available and (key != "mac" or comparison)
            button.configure(state="normal" if enabled else "disabled")

    def open_auto_id(self) -> None:
        app = self.app
        app._show_expert(app.material_identification_tab)
        notebook = getattr(app, "material_identification_notebook", None)
        if notebook is not None and notebook.tabs():
            notebook.select(notebook.tabs()[0])
