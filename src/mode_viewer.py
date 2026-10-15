"""Individual-mode viewer of the main window (3. Mode shapes > Individual modes). No scientific logic here.

Two separate panes, one per file: the extracted Abaqus modes and the imported experimental records (curve-fitted
modes, or FRF peak-derived response snapshots labelled as such). The panes never share a mapping, an overlay or a MAC;
they work whether or not a physical registration exists. Rendering runs on a worker thread
(services.modal_data_viewer) and every result is posted back to the Tk thread; a newer request supersedes an older
one, so a slow render never shows a stale mode.
"""

from __future__ import annotations

from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from PIL import Image, ImageTk

from services import modal_data_viewer as viewer

STATE_COLOURS = {viewer.ESTABLISHED: ("#174a7c", "#e8f1fb"), viewer.AMBIGUOUS: ("#7a4b00", "#fff4dc"),
                 viewer.NOT_ESTABLISHED: ("#7a4b00", "#fff4dc"), "EMPTY": ("#444444", "#f2f2f2")}
EMPTY_TEXT = "Run an analysis: the extracted FE modes and the imported experimental data appear here separately."


def _follow_width(label) -> None:
    """Wrap a label's text to its current width (not a fixed wraplength the responsive layout would rescale)."""
    label.bind("<Configure>", lambda event: label.configure(wraplength=max(200, event.width - 12)), add="+")


class _Pane:
    def __init__(self, panel: "ModeViewerPanel", parent, role: str, title: str) -> None:
        self.panel, self.role = panel, role
        self.entries: list[viewer.ViewerMode] = []
        self.dataset = None
        self.generation = 0
        self.photo = None
        self.image_path: Optional[Path] = None
        self.frame = ttk.LabelFrame(parent, text=title, padding=6)
        controls = ttk.Frame(self.frame)
        controls.pack(fill="x")
        self.choice = tk.StringVar(master=parent)
        self.combo = ttk.Combobox(controls, textvariable=self.choice, state="disabled", width=34)
        self.combo.pack(side="left")
        self.combo.bind("<<ComboboxSelected>>", lambda _e: self.render(), add="+")
        self.previous_button = ttk.Button(controls, text="◀", width=3, command=lambda: self.step(-1),
                                          state="disabled")
        self.previous_button.pack(side="left", padx=(4, 0))
        self.next_button = ttk.Button(controls, text="▶", width=3, command=lambda: self.step(1), state="disabled")
        self.next_button.pack(side="left", padx=(2, 8))
        self.component = tk.StringVar(master=parent)
        self.component_labels = {viewer.COMPONENT_TEXT[role][key]: key for key in viewer.COMPONENTS}
        self.component_combo = ttk.Combobox(controls, textvariable=self.component, state="disabled", width=30,
                                            values=list(self.component_labels))
        self.component.set(viewer.COMPONENT_TEXT[role]["normal"])
        self.component_combo.pack(side="left")
        self.component_combo.bind("<<ComboboxSelected>>", lambda _e: self.render(), add="+")
        self.info = ttk.Label(self.frame, text="", justify="left")
        self.info.pack(side="bottom", fill="x")
        _follow_width(self.info)
        self.image = ttk.Label(self.frame, text=EMPTY_TEXT, anchor="center", justify="center")
        self.image.pack(fill="both", expand=True, pady=(6, 4))
        self._fit_job = None
        self._fitted_size = None
        self.image.bind("<Configure>", self._schedule_fit, add="+")

    # -------------------------------------------------------------- data
    def set_dataset(self, dataset, empty_reason: str) -> None:
        self.generation += 1
        self.dataset = dataset
        self.entries = viewer.viewer_modes(dataset, self.role)
        labels = [entry.label() for entry in self.entries]
        self.combo.configure(values=labels, state="readonly" if labels else "disabled")
        state = "normal" if len(labels) > 1 else "disabled"
        self.previous_button.configure(state=state)
        self.next_button.configure(state=state)
        self.component_combo.configure(state="readonly" if labels else "disabled")
        if labels:
            self.choice.set(labels[0])
            self.render()
        else:
            self.choice.set("")
            self._show_text(empty_reason)
            self.info.configure(text="")

    def clear(self, message: str) -> None:
        self.generation += 1
        self.dataset, self.entries = None, []
        self.choice.set("")
        for widget in (self.combo, self.component_combo, self.previous_button, self.next_button):
            widget.configure(state="disabled")
        self._show_text(message)
        self.info.configure(text="")

    def selected(self) -> Optional[viewer.ViewerMode]:
        label = self.choice.get()
        return next((entry for entry in self.entries if entry.label() == label), None)

    def step(self, delta: int) -> None:
        current = self.selected()
        if current is None or not self.entries:
            return
        index = (self.entries.index(current) + delta) % len(self.entries)
        self.choice.set(self.entries[index].label())
        self.render()

    def select_number(self, number: int) -> bool:
        entry = next((item for item in self.entries if item.number == int(number)), None)
        if entry is None:
            return False
        self.choice.set(entry.label())
        self.render()
        return True

    # -------------------------------------------------------------- rendering
    def render(self) -> None:
        entry = self.selected()
        if entry is None or self.dataset is None:
            return
        self.generation += 1
        generation = self.generation
        component = self.component_labels.get(self.component.get(), "normal")
        self.info.configure(text=self._info_text(entry))
        # The previous view is forgotten at once: a resize while the new view is drawn must not re-show the old
        # picture under the new selection.
        self.image_path = None
        if self._fit_job is not None:
            self.image.after_cancel(self._fit_job)
            self._fit_job = None
        if not entry.spatial_available:
            self._show_text(f"No spatial view for {entry.label()}:\n{entry.spatial_reason}")
            return
        self._show_text(f"Drawing {entry.label()} ...")
        dataset, directory = self.dataset, self.panel.directory()

        def work():
            try:
                with self.panel.lock:
                    path, _ = viewer.render_viewer_mode(dataset, self.role, entry.number, component, directory)
                outcome = (path, None)
            except Exception as error:  # noqa: BLE001 - shown in the pane, never swallowed
                outcome = (None, error)
            self.panel.post(lambda: self._rendered(generation, *outcome))

        if self.panel.threaded:
            threading.Thread(target=work, daemon=True).start()
        else:
            work()

    def _rendered(self, generation: int, path: Optional[Path], error: Optional[BaseException]) -> None:
        if generation != self.generation:
            return  # superseded by a newer selection or a new analysis
        if error is not None:
            self.image_path = None
            self._show_text(f"The view could not be drawn: {error}")
            return
        self.image_path = path
        self._fit()

    def _schedule_fit(self, _event=None) -> None:
        if self.image_path is None:
            return
        if self._fit_job is not None:
            self.image.after_cancel(self._fit_job)
        self._fit_job = self.image.after(150, self._fit)

    def _fit(self) -> None:
        """Show the rendered view scaled to the space the pane has now (re-fitted when the window is resized)."""
        self._fit_job = None
        if self.image_path is None:
            return
        size = (max(240, self.image.winfo_width() - 8), max(200, self.image.winfo_height() - 8))
        if self.photo is not None and self._fitted_size == size:
            return
        try:
            with Image.open(self.image_path) as source:
                picture = source.copy()
            picture.thumbnail(size, Image.Resampling.LANCZOS)
            self.photo = ImageTk.PhotoImage(picture, master=self.image)
            self._fitted_size = size
            self.image.configure(image=self.photo, text="")
        except Exception as caught:  # noqa: BLE001
            self._show_text(f"Could not display the view: {caught}")

    def _show_text(self, text: str) -> None:
        self.photo = None
        self._fitted_size = None
        self.image.configure(image="", text=text)

    def _info_text(self, entry: viewer.ViewerMode) -> str:
        lines = [f"{entry.label()}  ·  {entry.source_text}",
                 f"{entry.point_count} points; components with data: {', '.join(entry.axes) or 'none'}"]
        quality = entry.quality
        parts = []
        if "mean_coherence" in quality:
            parts.append(f"mean coherence {quality['mean_coherence']:.3f}")
        if "phase_complexity_ratio" in quality:
            parts.append(f"phase complexity {quality['phase_complexity_ratio']:.3f}")
        if "damping_ratio" in quality:
            parts.append(f"damping {quality['damping_ratio']:.4g}")
        if parts:
            lines.append("Quality: " + ", ".join(parts))
        return "\n".join(lines)


class ModeViewerPanel:
    """The separate FE / experimental views; ``post`` runs a callback on the Tk thread."""

    def __init__(self, parent, *, post: Callable[[Callable[[], None]], bool], lock,
                 confirm_orientation: Callable[[object], None], threaded: bool = True) -> None:
        self.post, self.lock, self.threaded = post, lock, threaded
        self.confirm_orientation = confirm_orientation
        self.loaded: Optional[viewer.LoadedModalData] = None
        self.ambiguity = None
        self.frame = ttk.Frame(parent)
        self.banner = tk.Label(self.frame, text=EMPTY_TEXT, justify="left", anchor="w", padx=8, pady=6)
        self.banner.pack(fill="x")
        _follow_width(self.banner)
        actions = ttk.Frame(self.frame)
        actions.pack(fill="x", pady=(6, 6))
        self.confirm_button = ttk.Button(actions, text="Confirm physical orientation (independent evidence)...",
                                         command=self._confirm, state="disabled")
        self.confirm_button.pack(side="left")
        self.save_button = ttk.Button(actions, text="Save diagnostic output...", command=self.save,
                                      state="disabled")
        self.save_button.pack(side="left", padx=8)
        panes = ttk.Frame(self.frame)
        panes.pack(fill="both", expand=True)
        self.fe = _Pane(self, panes, viewer.FE, "FE mode (Abaqus ODB)")
        self.experimental = _Pane(self, panes, viewer.EXPERIMENTAL, "Experimental data (UNV/UFF)")
        self.fe.frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self.experimental.frame.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        panes.columnconfigure(0, weight=1, uniform="pane")
        panes.columnconfigure(1, weight=1, uniform="pane")
        panes.rowconfigure(0, weight=1)
        self._set_banner(EMPTY_TEXT, "EMPTY")

    def directory(self) -> Path:
        if self.loaded is not None and self.loaded.directory is not None:
            return Path(self.loaded.directory)
        from app import DEFAULT_WORKSPACE

        return Path(DEFAULT_WORKSPACE) / "viewer"

    def set_data(self, loaded: viewer.LoadedModalData, message: str, ambiguity=None) -> None:
        self.loaded, self.ambiguity = loaded, ambiguity
        self._set_banner(message, loaded.registration)
        self.confirm_button.configure(state="normal" if ambiguity is not None else "disabled")
        self.save_button.configure(state="normal")
        self.fe.set_dataset(loaded.abaqus, "No FE modes were extracted.")
        if loaded.experimental is None:
            reason = loaded.experimental_error or "no experimental data were loaded"
            self.experimental.clear(f"No experimental view: {reason}")
        else:
            self.experimental.set_dataset(loaded.experimental, "The experimental file holds no modal or FRF record.")

    def set_message(self, message: str, state: str, ambiguity=None) -> None:
        """A state without loaded datasets (the orientation can still be confirmed when ``ambiguity`` is given)."""
        self.clear("No loaded modal data are available for this run.")
        self.ambiguity = ambiguity
        self._set_banner(message, state)
        self.confirm_button.configure(state="normal" if ambiguity is not None else "disabled")

    def clear(self, message: str) -> None:
        self.loaded, self.ambiguity = None, None
        self._set_banner(message, "EMPTY")
        self.confirm_button.configure(state="disabled")
        self.save_button.configure(state="disabled")
        self.fe.clear(message)
        self.experimental.clear(message)

    def _set_banner(self, text: str, state: str) -> None:
        foreground, background = STATE_COLOURS.get(state, STATE_COLOURS["EMPTY"])
        self.banner.configure(text=text, fg=foreground, bg=background)

    def _confirm(self) -> None:
        if self.ambiguity is not None:
            self.confirm_orientation(self.ambiguity)

    def save(self, folder: Optional[Path] = None) -> Optional[dict]:
        if self.loaded is None:
            return None
        if folder is None:
            chosen = filedialog.askdirectory(title="Folder for the diagnostic output")
            if not chosen:
                return None
            folder = Path(chosen)
        images = [pane.image_path for pane in (self.fe, self.experimental) if pane.image_path is not None]
        try:
            paths = viewer.write_diagnostic_package(folder, self.loaded.inventory(), self.loaded.frequency_diagnostic,
                                                    images)
        except OSError as error:
            messagebox.showerror("Save diagnostic output", str(error))
            return None
        return paths
