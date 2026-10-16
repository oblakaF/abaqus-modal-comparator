"""3. Mode shapes > Establish physical registration... (CORE-E2E-C; the logic is services.guided_registration).

One dialog on the last analysis's loaded files: the physical evidence (an accepted scan calibration of this exact
experimental file, or an evidence file), its explicit fields with what is missing, the checks, and the resulting
registration. Apply runs the analysis again with it; the registration can be saved and reopened, and is re-verified
against the files every time it is used. Choosing one of the geometric orientation candidates is never evidence here.
"""

from __future__ import annotations

import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

import numpy as np

from reviewed_core import experimental_measurement_masks
from scientific_state import modal_dataset_geometry_identity
from services import guided_registration as guided
from services.archived_sensitivity_evidence import fresh_content_identity


class GuidedRegistrationDialog:
    def __init__(self, app, loaded) -> None:
        self.app, self.loaded = app, loaded
        self.evidence: Optional[guided.PhysicalEvidence] = None
        self.result: Optional[guided.GuidedRegistration] = None
        self.identity: Optional[dict] = None
        self.reference_path: Optional[Path] = None
        self._calls: queue.Queue = queue.Queue()  # worker threads hand their results to the Tk thread
        self.window = tk.Toplevel(app.root)
        self.window.title("Establish physical registration")
        self.window.transient(app.root)
        self.window.geometry("1180x900")
        self.window.minsize(900, 640)
        body = ttk.Frame(self.window, padding=10)
        body.pack(fill="both", expand=True)
        actions = ttk.Frame(body)  # packed first at the bottom: the actions stay visible at any window height
        actions.pack(side="bottom", fill="x", pady=(8, 0))
        ttk.Label(body, wraplength=1120, justify="left", text=(
            "A physical registration maps each measured point to an FE node from independent physical evidence of the "
            "scan (corner-A marker or measured offsets to the panel edges, physical scan window, measured face). It "
            "never uses MAC, frequencies or a choice among the geometric orientation candidates. The result is a "
            "diagnostic engineering registration of these exact files: not governed evidence and not an Auto-ID "
            "observation.")).pack(anchor="w")
        self.files = self._table(body, "Files of the last analysis", ("item", "value"), 5)
        evidence_box = ttk.LabelFrame(body, text="Physical evidence", padding=6)
        evidence_box.pack(fill="both", expand=True, pady=(6, 0))
        buttons = ttk.Frame(evidence_box)
        buttons.pack(fill="x")
        self.accepted_button = ttk.Button(buttons, text="Use accepted scan calibration of this file",
                                          command=self.use_accepted)
        self.accepted_button.pack(side="left")
        ttk.Button(buttons, text="Load evidence file...", command=self.load_evidence).pack(side="left", padx=6)
        ttk.Button(buttons, text="Write evidence template...", command=self.write_template).pack(side="left")
        self.locate_button = ttk.Button(buttons, text="Locate reference FE geometry file...", command=self.locate,
                                        state="disabled")
        self.locate_button.pack(side="left", padx=6)
        self.fields = self._tree(evidence_box, ("field", "value", "status"), 7, (170, 820, 110))
        result_box = ttk.LabelFrame(body, text="Checks and registration", padding=6)
        result_box.pack(fill="both", expand=True, pady=(6, 0))
        self.status = ttk.Label(result_box, text="No registration yet.", wraplength=1120, justify="left")
        self.status.pack(anchor="w")
        self.checks = self._tree(result_box, ("item", "value"), 7, (200, 900))
        self.build_button = ttk.Button(actions, text="Check and build", command=self.build, state="disabled")
        self.build_button.pack(side="left")
        self.apply_button = ttk.Button(actions, text="Apply and run analysis", command=self.apply, state="disabled")
        self.apply_button.pack(side="left", padx=6)
        self.save_button = ttk.Button(actions, text="Save registration...", command=self.save, state="disabled")
        self.save_button.pack(side="left")
        ttk.Button(actions, text="Open saved registration...", command=self.open_saved).pack(side="left", padx=6)
        ttk.Button(actions, text="Clear guided registration", command=self.clear).pack(side="left")
        ttk.Button(actions, text="Close", command=self.window.destroy).pack(side="right")
        self._show_files()
        self._show_fields()
        active = getattr(app, "_guided_registration", None)
        if active is not None:
            self._show_result(active, "ACTIVE: this guided registration is applied to the analysis.")
        self._hash_experimental_file()
        self.window.after(100, self._drain)

    def _drain(self) -> None:
        while True:
            try:
                callback = self._calls.get_nowait()
            except queue.Empty:
                break
            callback()
        if self.window.winfo_exists():
            self.window.after(100, self._drain)

    # ------------------------------------------------------------------ layout helpers
    def _table(self, parent, title, columns, height):
        frame = ttk.LabelFrame(parent, text=title, padding=6)
        frame.pack(fill="x", pady=(6, 0))
        return self._tree(frame, columns, height, (200, 900))

    @staticmethod
    def _tree(parent, columns, height, widths):
        tree = ttk.Treeview(parent, columns=columns, show="headings", height=height)
        for column, width in zip(columns, widths):
            tree.heading(column, text=column.capitalize())
            tree.column(column, width=width, anchor="w", stretch=column == columns[1])
        tree.pack(fill="both", expand=True)
        return tree

    @staticmethod
    def _fill(tree, rows) -> None:
        tree.delete(*tree.get_children())
        for row in rows:
            tree.insert("", "end", values=tuple(str(value) for value in row))

    # ------------------------------------------------------------------ files and evidence
    def _show_files(self) -> None:
        abaqus, experimental = self.loaded.abaqus, self.loaded.experimental
        fe_nodes = len(abaqus.sorted_modes()[0].node_ids)
        rows = [("ODB", str(self.loaded.abaqus_path or abaqus.source_path)),
                ("FE nodes / modes", f"{fe_nodes} nodes, {len(abaqus.sorted_modes())} modes")]
        try:
            identity = modal_dataset_geometry_identity(abaqus)
            rows.append(("FE geometry identity", f"{identity['sha256']} ({identity['node_count']} nodes)"))
        except ValueError as error:
            rows.append(("FE geometry identity", f"not available: {error}"))
        modes = experimental.sorted_modes()
        masks = np.asarray(experimental_measurement_masks(modes, modes[0].node_ids)[0], dtype=bool)
        dofs = "/".join(name for name, flag in zip(("U1", "U2", "U3"), masks.all(axis=0)) if flag) or "none"
        rows += [("Experimental file", str(self.loaded.experimental_path)),
                 ("Experimental points / modes", f"{len(modes[0].node_ids)} points, {len(modes)} modes, modal set "
                                                 f"{experimental.metadata.get('modal_set_key')!r}, measured {dofs}"),
                 ("Experimental SHA-256", "hashing..." if self.identity is None else
                  f"{self.identity['sha256']} ({self.identity['size']} bytes)")]
        self._fill(self.files, rows)

    def _hash_experimental_file(self) -> None:
        path = self.loaded.experimental_path

        def work():
            try:
                identity = fresh_content_identity(Path(path))
                self._calls.put(lambda: self._hashed(identity))
            except Exception as error:  # noqa: BLE001  (shown, never swallowed)
                self._calls.put(lambda error=error: self._set_status(f"The experimental file cannot be read: {error}"))

        threading.Thread(target=work, daemon=True).start()

    def _hashed(self, identity: dict) -> None:
        self.identity = identity
        if self.window.winfo_exists():
            self._show_files()

    def _show_fields(self) -> None:
        self._fill(self.fields, guided.evidence_rows(self.evidence))
        self.build_button.configure(state="normal" if self.evidence is not None else "disabled")
        needs_reference = (self.evidence is not None and self.evidence.reference_geometry_file is not None)
        self.locate_button.configure(state="normal" if needs_reference else "disabled")

    def _set_status(self, text: str) -> None:
        if self.window.winfo_exists():
            self.status.configure(text=text)

    def use_accepted(self) -> None:
        if self.identity is None:
            self._set_status("The experimental file is still being hashed; try again in a moment.")
            return
        try:
            self.evidence = guided.accepted_scan_evidence(self.identity)
        except guided.GuidedRegistrationRefusal as error:
            self.evidence = None
            self._set_status(f"NO ACCEPTED SCAN CALIBRATION: {error}")
        self._show_fields()

    def load_evidence(self, path: Optional[Path] = None) -> None:
        chosen = path or filedialog.askopenfilename(title="Physical evidence file", parent=self.window,
                                                    filetypes=[("Evidence", "*.json"), ("All files", "*.*")])
        if not chosen:
            return
        try:
            self.evidence = guided.load_evidence_file(Path(chosen))
            self._set_status(f"Evidence loaded from {Path(chosen).name}. Press Check and build.")
        except guided.GuidedRegistrationRefusal as error:
            self.evidence = None
            self._set_status(f"EVIDENCE REFUSED ({error.field}): {error}")
        self._show_fields()

    def write_template(self, path: Optional[Path] = None) -> Optional[Path]:
        if self.identity is None:
            self._set_status("The experimental file is still being hashed; try again in a moment.")
            return None
        chosen = path or filedialog.asksaveasfilename(title="Physical evidence template", parent=self.window,
                                                      defaultextension=".json", filetypes=[("Evidence", "*.json")])
        if not chosen:
            return None
        template = guided.evidence_template(self.loaded.abaqus, self.loaded.experimental, self.identity,
                                            Path(self.loaded.experimental_path).name)
        Path(chosen).write_text(json.dumps(template, indent=1), encoding="utf-8")
        self._set_status(f"Template written to {chosen}: fill in every physical field from the test records, then "
                         "load it with Load evidence file....")
        return Path(chosen)

    def locate(self, path: Optional[Path] = None) -> None:
        chosen = path or filedialog.askopenfilename(title="Reference FE geometry file (instance,node_label,x,y,z)",
                                                    parent=self.window, filetypes=[("CSV", "*.csv")])
        if chosen:
            self.reference_path = Path(chosen)
            self._set_status(f"Reference FE geometry: {chosen} (its SHA-256 is checked when building).")

    # ------------------------------------------------------------------ build / apply / save / open
    def build(self) -> None:
        if self.evidence is None or self.identity is None:
            return
        self.build_button.configure(state="disabled")
        self._discard_result()  # never a stale or partial registration while (or after) building
        self._set_status("Checking the evidence and building the registration...")
        evidence, identity, reference = self.evidence, self.identity, self.reference_path

        def work():
            try:
                result = guided.establish_guided_registration(self.loaded.abaqus, self.loaded.experimental, identity,
                                                              evidence, reference_geometry_path=reference)
            except Exception as error:  # noqa: BLE001  (a refusal or an unexpected error: shown, never swallowed)
                self._calls.put(lambda error=error: self._built(None, error))
                return
            self._calls.put(lambda: self._built(result, None))

        threading.Thread(target=work, daemon=True).start()

    def _built(self, result, error) -> None:
        if not self.window.winfo_exists():
            return
        self.build_button.configure(state="normal")
        if error is not None:
            self._show_failure(error, "REFUSED", "The analysis stays a frequency-only diagnostic.")
            return
        self._show_result(result, "ESTABLISHED: the registration is ready; Apply runs the gated comparison.")

    def _discard_result(self) -> None:
        self.result = None
        self.apply_button.configure(state="disabled")
        self.save_button.configure(state="disabled")

    def _show_failure(self, error: Exception, label: str, consequence: str) -> None:
        """A refusal names its field; any other error is reported as FAILED with its type. Nothing is registered."""
        self._discard_result()
        if isinstance(error, guided.GuidedRegistrationRefusal):
            text = f"{label} ({error.field}): {error}"
        else:
            text = (f"FAILED (unexpected {type(error).__name__}): {error} No registration was made; correct the "
                    "cause and retry.")
        self._fill(self.checks, [("refused" if label == "REFUSED" else label.lower(), text)])
        self._set_status(f"{text} {consequence}")

    def _show_result(self, result, message: str) -> None:
        self.result = result
        rows = guided.summary_rows(result) + [("check", item) for item in result.checks] + \
            [("warning", item) for item in result.warnings]
        self._fill(self.checks, rows)
        self._set_status(message)
        self.apply_button.configure(state="normal")
        self.save_button.configure(state="normal")

    def apply(self) -> None:
        if self.result is None:
            return
        self.app._guided_registration = self.result
        self.app.status.set("Guided physical registration set; the analysis runs again with it.")
        self.window.destroy()
        self.app._start()

    def save(self, path: Optional[Path] = None) -> Optional[Path]:
        if self.result is None:
            return None
        chosen = path or filedialog.asksaveasfilename(title="Save guided registration", parent=self.window,
                                                      defaultextension=".json", filetypes=[("Registration", "*.json")])
        if not chosen:
            return None
        try:
            saved = guided.save_guided_registration(self.result, Path(chosen))
        except OSError as error:
            self._set_status(f"NOT SAVED: {error}")
            return None
        self._set_status(f"Saved to {saved}. It is re-verified against the files whenever it is opened or used.")
        return saved

    def open_saved(self, path: Optional[Path] = None) -> None:
        chosen = path or filedialog.askopenfilename(title="Open guided registration", parent=self.window,
                                                    filetypes=[("Registration", "*.json")])
        if not chosen:
            return
        if self.identity is None:
            self._set_status("The experimental file is still being hashed; try again in a moment.")
            return
        try:
            result = guided.load_guided_registration(Path(chosen))
            guided.verify_for_files(result, self.loaded.abaqus, self.loaded.experimental, self.identity)
        except Exception as error:  # noqa: BLE001  (a refusal or an unreadable file: shown, never applied)
            self._show_failure(error, "SAVED REGISTRATION REFUSED", "")
            return
        self._show_result(result, f"OPENED {Path(chosen).name}: verified against the loaded files.")

    def clear(self) -> None:
        self.app._guided_registration = None
        self.result = None
        self._fill(self.checks, [])
        self.apply_button.configure(state="disabled")
        self.save_button.configure(state="disabled")
        self._set_status("No guided registration is applied; the next analysis uses automatic geometry registration.")


def open_guided_registration_dialog(app) -> Optional[GuidedRegistrationDialog]:
    viewer = getattr(app, "mode_viewer", None)
    loaded = getattr(viewer, "loaded", None)
    if loaded is None or loaded.abaqus is None or loaded.experimental is None or loaded.experimental_path is None:
        messagebox.showinfo("Establish physical registration",
                            "Run the analysis first: the registration is built on the FE and experimental data the "
                            "analysis loaded.")
        return None
    return GuidedRegistrationDialog(app, loaded)
