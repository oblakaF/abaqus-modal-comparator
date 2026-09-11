from __future__ import annotations

import threading
import queue
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Dict, Optional, Sequence

from universal_reader import (
    ExperimentalModalSet,
    discover_experimental_modal_sets,
    resolve_testlab_file,
)


_INSTALLED = False
NO_FITTED_SET_TEXT = "No fitted modal set — FRF/raw fallback"
SELECT_MODAL_SET_TEXT = "Select modal set..."


def modal_set_choice_text(modal_set: ExperimentalModalSet) -> str:
    return f"{modal_set.display_name} — {len(modal_set.modes)} modes"


def modal_set_summary(modal_set: ExperimentalModalSet) -> str:
    return (
        "Source: PolyMAX / dataset 55  |  "
        f"Set: {modal_set.display_name}  |  "
        f"Physical modes: {len(modal_set.modes)}  |  "
        f"Residual records excluded: {modal_set.excluded_residual_count}"
    )


def validate_modal_set_selection(
    modal_sets: Sequence[ExperimentalModalSet],
    selected_key: str,
) -> Optional[str]:
    if not modal_sets:
        return None
    keys = {item.key for item in modal_sets}
    if selected_key in keys:
        return selected_key
    if len(modal_sets) > 1:
        raise ValueError(
            "This experimental file contains multiple fitted modal sets. "
            "Select the experimental modal set to compare."
        )
    return modal_sets[0].key


def experimental_mode_source_label(metadata: Dict[str, Any]) -> str:
    source = str(
        metadata.get("source_label")
        or metadata.get("source")
        or metadata.get("mode_source")
        or "Unknown"
    )
    modal_set = str(metadata.get("modal_set_name") or "").strip()
    if modal_set:
        return f"dataset 55 / {modal_set}"
    return source


def install_polymax_ui(app_module) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    application_class = app_module.ModalComparatorApp
    original_init = application_class.__init__
    original_build_input = application_class._build_input
    original_validate = application_class._validate
    original_persistent_snapshot = application_class._persistent_snapshot
    original_project_payload = application_class._project_payload_for_self
    original_apply_project = application_class._apply_project_payload
    original_new_project = application_class._new_project
    original_details = application_class._details

    def polymax_init(self, root) -> None:
        self.experimental_modal_set_key = tk.StringVar(master=root, value="")
        self.experimental_modal_set_display = tk.StringVar(
            master=root, value=NO_FITTED_SET_TEXT
        )
        self.experimental_modal_set_summary = tk.StringVar(
            master=root, value="Choose an experimental file to discover fitted modal sets."
        )
        self.available_experimental_modal_sets = []
        self._modal_set_choices = {}
        self._modal_set_discovery_generation = 0
        self._modal_set_discovery_path = None
        self._modal_set_discovery_state = "idle"
        self._pending_project_modal_set = None
        self._modal_set_restore_baseline = False
        self._suppress_modal_set_dirty = False
        original_init(self, root)
        self._modal_set_path_trace = self.experimental_path.trace_add(
            "write", self._schedule_modal_set_discovery
        )
        self._modal_set_key_trace = self.experimental_modal_set_key.trace_add(
            "write", self._modal_set_key_changed
        )
        self._schedule_modal_set_discovery()

    def polymax_build_input(self) -> None:
        original_build_input(self)
        source = self.experimental_path_entry.master
        ttk.Label(source, text="Experimental modal set:").grid(
            row=4, column=0, sticky="w", pady=(7, 2)
        )
        self.experimental_modal_set_combo = ttk.Combobox(
            source,
            textvariable=self.experimental_modal_set_display,
            state="readonly",
            width=42,
        )
        self.experimental_modal_set_combo.grid(
            row=4, column=1, sticky="ew", padx=(10, 0), pady=(7, 2)
        )
        self.experimental_modal_set_combo.bind(
            "<<ComboboxSelected>>", self._experimental_modal_set_selected, add="+"
        )
        self.experimental_modal_set_summary_label = ttk.Label(
            source,
            textvariable=self.experimental_modal_set_summary,
            style="Secondary.TLabel",
            justify="left",
        )
        self.experimental_modal_set_summary_label.grid(
            row=5, column=1, columnspan=2, sticky="w", padx=(10, 0), pady=(0, 5)
        )
        self._responsive_wrap_labels.append(self.experimental_modal_set_summary_label)
        self._analysis_configuration_controls["experimental_modal_set"] = (
            self.experimental_modal_set_combo,
            "readonly",
        )

    def set_modal_set_key(self, key: str) -> None:
        self._suppress_modal_set_dirty = True
        try:
            self.experimental_modal_set_key.set(key)
        finally:
            self._suppress_modal_set_dirty = False

    def show_modal_set(self, key: str) -> None:
        lookup = {item.key: item for item in self.available_experimental_modal_sets}
        selected = lookup.get(key)
        self._set_modal_set_key(key if selected is not None else "")
        if selected is None:
            if self.available_experimental_modal_sets:
                self.experimental_modal_set_display.set(SELECT_MODAL_SET_TEXT)
                self.experimental_modal_set_summary.set(
                    "Multiple fitted dataset-55 sets found. Select one before Run."
                )
            else:
                self.experimental_modal_set_display.set(NO_FITTED_SET_TEXT)
                self.experimental_modal_set_summary.set(
                    "No fitted dataset-55 modal set — dataset 2414 / dataset 58 fallback remains available."
                )
            return
        self.experimental_modal_set_display.set(modal_set_choice_text(selected))
        self.experimental_modal_set_summary.set(modal_set_summary(selected))

    def apply_discovered_modal_sets(
        self,
        generation: int,
        resolved_path: Path,
        modal_sets: Sequence[ExperimentalModalSet],
        error: Optional[BaseException],
    ) -> None:
        if generation != self._modal_set_discovery_generation:
            return
        if self._modal_set_discovery_path != resolved_path:
            return
        self.available_experimental_modal_sets = list(modal_sets)
        self._modal_set_discovery_state = "error" if error is not None else "ready"
        self._modal_set_choices = {
            modal_set_choice_text(item): item.key for item in modal_sets
        }

        if error is not None:
            self.experimental_modal_set_combo.configure(values=())
            self._set_modal_set_key("")
            self.experimental_modal_set_display.set("Modal-set discovery failed")
            self.experimental_modal_set_summary.set(str(error))
        elif not modal_sets:
            self.experimental_modal_set_combo.configure(values=(NO_FITTED_SET_TEXT,))
            self._show_experimental_modal_set("")
        else:
            values = tuple(self._modal_set_choices)
            if len(modal_sets) > 1:
                values = (SELECT_MODAL_SET_TEXT,) + values
            self.experimental_modal_set_combo.configure(values=values)
            requested = self._pending_project_modal_set
            if requested:
                match = next((item for item in modal_sets if item.key == requested), None)
                if match is None:
                    self._show_experimental_modal_set("")
                    messagebox.showwarning(
                        "Experimental modal set",
                        f"The saved modal set {requested!r} no longer exists in this file. "
                        "Select the experimental modal set again.",
                    )
                else:
                    self._show_experimental_modal_set(match.key)
            elif len(modal_sets) == 1:
                self._show_experimental_modal_set(modal_sets[0].key)
            else:
                self._show_experimental_modal_set("")

        self._pending_project_modal_set = None
        if self._modal_set_restore_baseline:
            self._modal_set_restore_baseline = False
            self._reset_dirty()
        self._refresh_readiness()

    def schedule_modal_set_discovery(self, *_args) -> None:
        self._modal_set_discovery_generation += 1
        generation = self._modal_set_discovery_generation
        self.available_experimental_modal_sets = []
        self._modal_set_choices = {}
        self._set_modal_set_key("")
        selected_path = self.experimental_path.get().strip()
        if not selected_path:
            self._pending_project_modal_set = None
            self._modal_set_restore_baseline = False
            self._modal_set_discovery_path = None
            self._modal_set_discovery_state = "idle"
            self.experimental_modal_set_combo.configure(values=())
            self.experimental_modal_set_display.set(NO_FITTED_SET_TEXT)
            self.experimental_modal_set_summary.set(
                "Choose an experimental file to discover fitted modal sets."
            )
            return
        try:
            resolved_path = resolve_testlab_file(Path(selected_path)).resolve()
        except Exception as error:
            self._modal_set_discovery_path = Path(selected_path)
            self._apply_discovered_modal_sets(
                generation, self._modal_set_discovery_path, [], error
            )
            return
        self._modal_set_discovery_path = resolved_path
        self._modal_set_discovery_state = "loading"
        self.experimental_modal_set_combo.configure(values=())
        self.experimental_modal_set_display.set("Discovering modal sets...")
        self.experimental_modal_set_summary.set(
            "Reading dataset-55 result-set metadata from the selected file."
        )

        def worker() -> None:
            try:
                modal_sets = discover_experimental_modal_sets(resolved_path)
                error = None
            except Exception as caught:
                modal_sets = []
                error = caught

            results.put((modal_sets, error))

        results = queue.Queue(maxsize=1)

        def poll() -> None:
            if generation != self._modal_set_discovery_generation:
                return
            try:
                modal_sets, error = results.get_nowait()
            except queue.Empty:
                try:
                    self.root.after(25, poll)
                except (tk.TclError, RuntimeError):
                    pass
                return
            self._apply_discovered_modal_sets(
                generation, resolved_path, modal_sets, error
            )

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(25, poll)

    def modal_set_selected(self, _event=None) -> None:
        display = self.experimental_modal_set_display.get()
        key = self._modal_set_choices.get(display, "")
        self.experimental_modal_set_key.set(key)
        selected = next(
            (item for item in self.available_experimental_modal_sets if item.key == key),
            None,
        )
        if selected is None:
            self.experimental_modal_set_summary.set(
                "Multiple fitted dataset-55 sets found. Select one before Run."
            )
        else:
            self.experimental_modal_set_summary.set(modal_set_summary(selected))

    def modal_set_key_changed(self, *_args) -> None:
        if not self._suppress_modal_set_dirty and hasattr(self, "dirty_tracker"):
            self._on_persistent_change()

    def polymax_validate(self):
        if self._modal_set_discovery_state == "loading":
            messagebox.showwarning(
                "Experimental modal set",
                "Modal-set discovery is still running. Wait for it to finish before Run.",
            )
            return None
        if self._modal_set_discovery_state == "error":
            messagebox.showwarning(
                "Experimental modal set",
                "The selected experimental file could not be inspected. "
                "Choose the file again before Run.",
            )
            return None
        try:
            modal_set = validate_modal_set_selection(
                self.available_experimental_modal_sets,
                self.experimental_modal_set_key.get(),
            )
        except ValueError as error:
            messagebox.showwarning("Experimental modal set", str(error))
            return None
        values = original_validate(self)
        if values is None:
            return None
        return (*values, modal_set)

    def polymax_persistent_snapshot(self) -> dict:
        snapshot = original_persistent_snapshot(self)
        snapshot["experimental_modal_set"] = self.experimental_modal_set_key.get()
        return snapshot

    def polymax_project_payload(self) -> dict:
        payload = original_project_payload(self)
        payload.setdefault("inputs", {})["experimental_modal_set"] = (
            self.experimental_modal_set_key.get() or None
        )
        selected = next(
            (
                item
                for item in self.available_experimental_modal_sets
                if item.key == self.experimental_modal_set_key.get()
            ),
            None,
        )
        payload["inputs"]["experimental_modal_set_name"] = (
            None if selected is None else selected.display_name
        )
        return payload

    def polymax_apply_project(self, payload: dict, project_path=None) -> None:
        inputs = payload.get("inputs", {})
        self._pending_project_modal_set = inputs.get("experimental_modal_set")
        self._modal_set_restore_baseline = project_path is not None
        original_apply_project(self, payload, project_path)

    def polymax_new_project(self) -> None:
        original_new_project(self)
        if self.project_path is None and not self.experimental_path.get().strip():
            self._pending_project_modal_set = None
            self._modal_set_restore_baseline = False
            self._show_experimental_modal_set("")

    def polymax_details(self, result) -> None:
        original_details(self, result)
        metadata = result.experimental.metadata
        lines = [
            "",
            "",
            "EXPERIMENTAL MODAL SOURCE",
            "-" * 88,
            f"Source dataset: {metadata.get('mode_source', 'unknown')}",
            f"Modal set: {metadata.get('modal_set_name', 'not applicable')}",
            f"Modal-set key: {metadata.get('modal_set_key', 'not applicable')}",
            f"Dataset-55 residual records excluded: {metadata.get('excluded_residual_count', 0)}",
            f"Dataset-58 role: {metadata.get('dataset_58_role', 'primary fallback or unavailable')}",
            f"Dataset-58 FRF channels: {metadata.get('frf_channel_count', 0)}",
            f"Coherence: {metadata.get('coherence_status', 'unavailable')}",
        ]
        self.details.configure(state="normal")
        self.details.insert("end", "\n".join(lines))
        self.details.configure(state="disabled")

    application_class.__init__ = polymax_init
    application_class._build_input = polymax_build_input
    application_class._set_modal_set_key = set_modal_set_key
    application_class._show_experimental_modal_set = show_modal_set
    application_class._apply_discovered_modal_sets = apply_discovered_modal_sets
    application_class._schedule_modal_set_discovery = schedule_modal_set_discovery
    application_class._experimental_modal_set_selected = modal_set_selected
    application_class._modal_set_key_changed = modal_set_key_changed
    application_class._validate = polymax_validate
    application_class._persistent_snapshot = polymax_persistent_snapshot
    application_class._project_payload_for_self = polymax_project_payload
    application_class._apply_project_payload = polymax_apply_project
    application_class._new_project = polymax_new_project
    application_class._details = polymax_details
    _INSTALLED = True
