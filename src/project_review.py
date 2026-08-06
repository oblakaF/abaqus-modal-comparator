from __future__ import annotations

import json
import traceback
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
import tkinter as tk
from typing import Dict, Optional

import numpy as np

from modal_core import ComparisonResult, ModePairResult, modal_assurance_criterion
from reviewed_core import (
    _phase_align_masked,
    _recalculate_order_changed,
    _status,
    _vectors_on_nodes,
    experimental_measurement_masks,
    frequency_error_percent,
)
from quality_control import _detect_rigid_modes


PROJECT_SCHEMA_VERSION = 1
PROJECT_EXTENSION = ".amcp.json"
CONFIG_DIRECTORY = Path.home() / ".abaqus_simcenter_modal_comparator"
LAST_SESSION_PATH = CONFIG_DIRECTORY / "last_session.json"
ERROR_LOG_PATH = CONFIG_DIRECTORY / "project_review_errors.log"
_INSTALLED = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _log_recoverable_error(context: str, error: BaseException) -> None:
    """Record an error that is deliberately not raised further.

    Session persistence and plot-cache refresh are allowed to fail without
    interrupting the user's session, but staying completely silent about it
    (the previous ``except Exception: pass``) meant a persistent failure
    could go unnoticed indefinitely. Logging here is itself best-effort: if
    the filesystem is unwritable there is nowhere left to report that either.
    """
    try:
        CONFIG_DIRECTORY.mkdir(parents=True, exist_ok=True)
        with ERROR_LOG_PATH.open("a", encoding="utf-8") as stream:
            stream.write(f"{utc_timestamp()} [{context}] {error!r}\n")
            stream.write(traceback.format_exc())
            stream.write("\n")
    except Exception:
        pass


def normalize_manual_reviews(value) -> Dict[str, dict]:
    if not isinstance(value, dict):
        return {}
    output: Dict[str, dict] = {}
    for key, item in value.items():
        if not isinstance(item, dict):
            continue
        try:
            abaqus_mode = str(int(key))
        except (TypeError, ValueError):
            continue
        decision = str(item.get("decision", "automatic")).lower()
        if decision not in {"automatic", "accepted", "rejected", "unresolved"}:
            decision = "automatic"
        experimental_mode = item.get("experimental_mode")
        try:
            experimental_mode = None if experimental_mode in (None, "") else int(experimental_mode)
        except (TypeError, ValueError):
            experimental_mode = None
        output[abaqus_mode] = {
            "decision": decision,
            "experimental_mode": experimental_mode,
            "comment": str(item.get("comment", "")),
            "updated_at": str(item.get("updated_at", "")),
        }
    return output


def project_payload(
    *,
    abaqus_path: str,
    experimental_path: str,
    workspace_path: str,
    abaqus_command: str,
    start_mode: int,
    end_mode: int,
    coordinate_scale: str,
    manual_reviews: Dict[str, dict],
    result: Optional[ComparisonResult] = None,
) -> dict:
    payload = {
        "schema_version": PROJECT_SCHEMA_VERSION,
        "application": "Abaqus–Simcenter Modal Comparator",
        "saved_at": utc_timestamp(),
        "inputs": {
            "abaqus_results": str(abaqus_path),
            "simcenter_results": str(experimental_path),
            "output_workspace": str(workspace_path),
            "abaqus_command": str(abaqus_command or "abaqus"),
            "start_mode": int(start_mode),
            "end_mode": int(end_mode),
            "coordinate_scale": str(coordinate_scale or "auto"),
        },
        "manual_reviews": normalize_manual_reviews(manual_reviews),
    }
    if result is not None:
        payload["last_result"] = {
            "matched_pairs": len(result.pairs),
            "geometry_match_fraction": float(result.geometry.matched_fraction),
            "pairs": [
                {
                    "abaqus_mode": int(pair.abaqus_mode),
                    "experimental_mode": int(pair.experimental_mode),
                    "abaqus_frequency_hz": float(pair.abaqus_frequency_hz),
                    "experimental_frequency_hz": float(pair.experimental_frequency_hz),
                    "signed_frequency_error_percent": float(pair.frequency_error_percent),
                    "mac": None if pair.mac is None else float(pair.mac),
                    "status": str(pair.status),
                    "manual_decision": str(getattr(pair, "manual_decision", "automatic")),
                    "manual_comment": str(getattr(pair, "manual_comment", "")),
                }
                for pair in result.pairs
            ],
        }
    return payload


def write_project(path: Path, payload: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def read_project(path: Path) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Project file must contain a JSON object.")
    version = int(payload.get("schema_version", 0))
    if version != PROJECT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported project schema version {version}; expected {PROJECT_SCHEMA_VERSION}."
        )
    if not isinstance(payload.get("inputs"), dict):
        raise ValueError("Project file does not contain an inputs section.")
    payload["manual_reviews"] = normalize_manual_reviews(payload.get("manual_reviews", {}))
    return payload


def build_manual_pair(
    result: ComparisonResult,
    abaqus_mode_number: int,
    experimental_mode_number: int,
) -> ModePairResult:
    """Build one reviewed pair on the already selected geometry and measured DOFs."""
    abaqus_lookup = {mode.number: mode for mode in result.abaqus.sorted_modes()}
    experimental_modes = result.experimental.sorted_modes()
    experimental_lookup = {mode.number: mode for mode in experimental_modes}
    abaqus_mode = abaqus_lookup.get(int(abaqus_mode_number))
    experimental_mode = experimental_lookup.get(int(experimental_mode_number))
    if abaqus_mode is None:
        raise ValueError(f"Abaqus mode {abaqus_mode_number} is not available.")
    if experimental_mode is None:
        raise ValueError(f"Experimental mode {experimental_mode_number} is not available.")

    abaqus_reference = result.abaqus.sorted_modes()[0]
    experimental_reference = experimental_modes[0]
    reference_node_ids = experimental_reference.node_ids
    mapped_abaqus_ids = abaqus_reference.node_ids[result.geometry.experimental_to_abaqus]

    abaqus_values = _vectors_on_nodes(abaqus_mode, mapped_abaqus_ids)
    abaqus_rotated = abaqus_values @ result.geometry.rotation
    experimental_values = _vectors_on_nodes(experimental_mode, reference_node_ids)
    # This pair's own experimental mode only -- never the whole dataset's
    # modes unioned together (ROADMAP Stage 2 #3).
    measurement_mask = experimental_measurement_masks(
        [experimental_mode], reference_node_ids
    )[0]
    finite = (
        np.isfinite(abaqus_rotated.real)
        & np.isfinite(abaqus_rotated.imag)
        & np.isfinite(experimental_values.real)
        & np.isfinite(experimental_values.imag)
    )
    dof_mask = measurement_mask & finite
    valid_rows = np.any(dof_mask, axis=1)
    if not np.any(valid_rows):
        raise ValueError("The selected pair has no common measured degrees of freedom.")

    a = np.asarray(abaqus_rotated[valid_rows])
    e = np.asarray(experimental_values[valid_rows])
    local_mask = np.asarray(dof_mask[valid_rows], dtype=bool)
    coordinates = np.asarray(experimental_reference.coordinates[valid_rows])
    mac_value = modal_assurance_criterion(a[local_mask], e[local_mask])
    signed_error = frequency_error_percent(
        abaqus_mode.frequency_hz, experimental_mode.frequency_hz
    )
    aligned_a = _phase_align_masked(e, a, local_mask)
    pair = ModePairResult(
        abaqus_mode=abaqus_mode.number,
        experimental_mode=experimental_mode.number,
        abaqus_frequency_hz=abaqus_mode.frequency_hz,
        experimental_frequency_hz=experimental_mode.frequency_hz,
        frequency_error_percent=float(signed_error),
        mac=mac_value,
        status=_status(mac_value, signed_error),
        order_changed=False,
        mapped_points=int(np.count_nonzero(np.any(local_mask, axis=1))),
        abaqus_vector=aligned_a,
        experimental_vector=e,
        coordinates=coordinates,
    )
    setattr(pair, "measured_dof_mask", local_mask)
    setattr(pair, "measured_dof_count", int(np.count_nonzero(local_mask)))
    return pair


def _all_elastic_abaqus_modes(result: ComparisonResult):
    """Return the Abaqus modes retained after rigid-body filtering.

    Mirrors quality_control.compare_modal_datasets_with_quality_control, which
    already ran this same filter on this dataset to build *result*: a failure
    here indicates a real bug, not an expected input shape, so it is left to
    propagate rather than silently substituting unfiltered (possibly rigid)
    modes into the manual-review candidate list.
    """
    _, retained, _, _ = _detect_rigid_modes(result.abaqus)
    return retained


def install_project_review(app_module) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    application_class = app_module.ModalComparatorApp
    original_init = application_class.__init__
    original_complete = application_class._complete
    original_populate = application_class._populate
    original_details = application_class._details

    def reviewed_init(self, root) -> None:
        self.project_path: Optional[Path] = None
        self.manual_reviews: Dict[str, dict] = {}
        self._automatic_pairs_by_mode: Dict[int, ModePairResult] = {}
        self._manual_candidate_pairs: Dict[int, ModePairResult] = {}
        self._review_item_to_mode: Dict[str, int] = {}
        original_init(self, root)
        self._install_project_controls()
        self._install_manual_review_tab()
        self._install_manual_columns()
        self._restore_last_session()
        self.root.protocol("WM_DELETE_WINDOW", self._close_with_session_save)

    def install_project_controls(self) -> None:
        # New/Open/Save/Save as live in the File menu (menu_ui.install_menu_ui) so
        # they are reachable from every tab; this only keeps the current-project
        # indicator visible in the header, next to the window title.
        self.project_name_label = ttk.Label(self.header, text="Project: Unsaved project")
        self.project_name_label.pack(side="right", anchor="e", padx=(0, 4))

    def install_manual_columns(self) -> None:
        columns = list(self.table["columns"])
        for key in ("manual", "comment"):
            if key not in columns:
                columns.append(key)
        self.table.configure(columns=columns)
        self.table.heading("manual", text="Manual decision")
        self.table.heading("comment", text="Comment")
        self.table.column("manual", width=125, anchor="center")
        self.table.column("comment", width=190, anchor="w")

    def install_manual_review_tab(self) -> None:
        self.manual_review_tab = ttk.Frame(self.tabs, padding=10)
        details_index = self.tabs.index(self.details_tab)
        self.tabs.insert(details_index, self.manual_review_tab, text="8. Manual review")
        self.tabs.tab(self.details_tab, text="9. Details")

        explanation = ttk.Label(
            self.manual_review_tab,
            text=(
                "Automatic pairing remains preserved. Manual decisions create the effective pair set used "
                "by tables, plots and reports. Rejected or unresolved modes remain visible here."
            ),
            wraplength=1300,
            justify="left",
        )
        explanation.pack(fill="x", pady=(0, 8))

        frame = ttk.Frame(self.manual_review_tab)
        frame.pack(fill="both", expand=True)
        columns = ("am", "af", "auto_em", "current_em", "ef", "err", "mac", "auto_status", "decision", "comment")
        self.review_table = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        specs = (
            ("am", "Abaqus mode", 90),
            ("af", "Abaqus, Hz", 105),
            ("auto_em", "Automatic E", 95),
            ("current_em", "Reviewed E", 95),
            ("ef", "Experiment, Hz", 110),
            ("err", "Signed error, %", 105),
            ("mac", "MAC", 75),
            ("auto_status", "Automatic status", 130),
            ("decision", "Decision", 115),
            ("comment", "Comment", 260),
        )
        for key, title, width in specs:
            self.review_table.heading(key, text=title)
            self.review_table.column(key, width=width, anchor="center" if key != "comment" else "w")
        y_scroll = ttk.Scrollbar(frame, orient="vertical", command=self.review_table.yview)
        self.review_table.configure(yscrollcommand=y_scroll.set)
        self.review_table.pack(side="left", fill="both", expand=True)
        y_scroll.pack(side="right", fill="y")

        buttons = ttk.Frame(self.manual_review_tab)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Accept selected", command=self._manual_accept).pack(side="left")
        ttk.Button(buttons, text="Reject selected", command=self._manual_reject).pack(side="left", padx=5)
        ttk.Button(buttons, text="Mark unresolved", command=self._manual_unresolved).pack(side="left")
        ttk.Button(buttons, text="Change experimental mode…", command=self._manual_change_mode).pack(side="left", padx=5)
        ttk.Button(buttons, text="Add comment…", command=self._manual_comment).pack(side="left")
        ttk.Button(buttons, text="Reset automatic", command=self._manual_reset).pack(side="left", padx=5)

    def project_payload_for_self(self) -> dict:
        coordinate_scale = getattr(self, "coordinate_scale_text", None)
        coordinate_scale_value = coordinate_scale.get() if coordinate_scale is not None else "auto"
        try:
            start_mode = int(self.start_mode.get())
            end_mode = int(self.end_mode.get())
        except (TypeError, ValueError, tk.TclError):
            start_mode, end_mode = 6, 15
        return project_payload(
            abaqus_path=self.abaqus_path.get(),
            experimental_path=self.experimental_path.get(),
            workspace_path=self.workspace_path.get(),
            abaqus_command=self.abaqus_command.get(),
            start_mode=start_mode,
            end_mode=end_mode,
            coordinate_scale=coordinate_scale_value,
            manual_reviews=self.manual_reviews,
            result=self.result,
        )

    def apply_project_payload(self, payload: dict, project_path: Optional[Path] = None) -> None:
        inputs = payload.get("inputs", {})
        self.abaqus_path.set(str(inputs.get("abaqus_results", "")))
        self.experimental_path.set(str(inputs.get("simcenter_results", "")))
        self.workspace_path.set(str(inputs.get("output_workspace", app_module.DEFAULT_WORKSPACE)))
        self.abaqus_command.set(str(inputs.get("abaqus_command", "abaqus")))
        self.start_mode.set(int(inputs.get("start_mode", 6)))
        self.end_mode.set(int(inputs.get("end_mode", 15)))
        if hasattr(self, "coordinate_scale_text"):
            self.coordinate_scale_text.set(str(inputs.get("coordinate_scale", "auto")))
        self.manual_reviews = normalize_manual_reviews(payload.get("manual_reviews", {}))
        self.project_path = None if project_path is None else Path(project_path)
        self.project_name_label.configure(
            text="Project: "
            + ("Recovered last session" if self.project_path is None else self.project_path.name)
        )
        self._refresh_review_table()

    def save_last_session(self) -> None:
        try:
            CONFIG_DIRECTORY.mkdir(parents=True, exist_ok=True)
            write_project(LAST_SESSION_PATH, self._project_payload_for_self())
        except Exception as error:
            _log_recoverable_error("save_last_session", error)

    def restore_last_session(self) -> None:
        if not LAST_SESSION_PATH.exists():
            return
        try:
            self._apply_project_payload(read_project(LAST_SESSION_PATH), None)
            self.status.set("Last project settings restored. Run the analysis to restore results.")
        except Exception as error:
            _log_recoverable_error("restore_last_session", error)
            self.status.set(
                "Could not restore the last session; starting from defaults. "
                f"See {ERROR_LOG_PATH}."
            )

    def new_project(self) -> None:
        if not messagebox.askyesno("New project", "Clear the current project settings and manual decisions?"):
            return
        self.project_path = None
        self.manual_reviews = {}
        self._automatic_pairs_by_mode = {}
        self._manual_candidate_pairs = {}
        self.result = None
        self.cache = None
        self.abaqus_path.set("")
        self.experimental_path.set("")
        self.workspace_path.set(str(app_module.DEFAULT_WORKSPACE))
        self.abaqus_command.set("abaqus")
        self.start_mode.set(6)
        self.end_mode.set(15)
        if hasattr(self, "coordinate_scale_text"):
            self.coordinate_scale_text.set("auto")
        self.project_name_label.configure(text="Project: Unsaved project")
        self.table.delete(*self.table.get_children())
        self._refresh_review_table()
        self.status.set("New project created.")

    def open_project(self) -> None:
        filename = filedialog.askopenfilename(
            title="Open modal-comparator project",
            filetypes=[("Modal Comparator project", "*.amcp.json"), ("JSON", "*.json"), ("All files", "*.*")],
        )
        if not filename:
            return
        try:
            payload = read_project(Path(filename))
            self._apply_project_payload(payload, Path(filename))
            self._save_last_session()
            self.status.set("Project opened. Run the analysis to load or calculate modal results.")
        except Exception as error:
            messagebox.showerror("Could not open project", str(error))

    def save_project(self) -> None:
        if self.project_path is None:
            self._save_project_as()
            return
        try:
            write_project(self.project_path, self._project_payload_for_self())
            self._save_last_session()
            self.project_name_label.configure(text=f"Project: {self.project_path.name}")
            self.status.set(f"Project saved: {self.project_path}")
        except Exception as error:
            messagebox.showerror("Could not save project", str(error))

    def save_project_as(self) -> None:
        filename = filedialog.asksaveasfilename(
            title="Save modal-comparator project",
            defaultextension=PROJECT_EXTENSION,
            initialfile="modal_comparison_project.amcp.json",
            filetypes=[("Modal Comparator project", "*.amcp.json"), ("JSON", "*.json")],
        )
        if not filename:
            return
        self.project_path = Path(filename)
        self._save_project()

    def close_with_session_save(self) -> None:
        self._save_last_session()
        self.root.destroy()

    def reviewed_complete(self, result) -> None:
        self._automatic_pairs_by_mode = {int(pair.abaqus_mode): pair for pair in result.pairs}
        self._manual_candidate_pairs = {}
        setattr(result, "automatic_pairs", list(result.pairs))
        original_complete(self, result)
        self._apply_manual_reviews(refresh=True)
        self._save_last_session()

    def reviewed_populate(self, result) -> None:
        original_populate(self, result)
        columns = list(self.table["columns"])
        for item, pair in self.item_to_pair.items():
            values = list(self.table.item(item, "values"))
            while len(values) < len(columns):
                values.append("")
            decision = str(getattr(pair, "manual_decision", "automatic")).title()
            comment = str(getattr(pair, "manual_comment", ""))
            values[columns.index("manual")] = decision
            values[columns.index("comment")] = comment
            self.table.item(item, values=values)
        self._refresh_review_table()

    def reviewed_details(self, result) -> None:
        original_details(self, result)
        lines = ["", "", "MANUAL REVIEW", "-" * 88]
        if not self.manual_reviews:
            lines.append("No manual decisions have been recorded.")
        else:
            for key in sorted(self.manual_reviews, key=lambda value: int(value)):
                item = self.manual_reviews[key]
                experimental = item.get("experimental_mode")
                experimental_text = "—" if experimental is None else f"E{experimental}"
                lines.append(
                    f"A{key}: {item.get('decision', 'automatic')} | reviewed pair {experimental_text} | "
                    f"comment: {item.get('comment', '') or '—'}"
                )
        self.details.configure(state="normal")
        self.details.insert("end", "\n".join(lines))
        self.details.configure(state="disabled")

    def selected_review_mode(self) -> Optional[int]:
        selection = self.review_table.selection()
        if not selection:
            messagebox.showinfo("Manual review", "Select an Abaqus mode in the manual-review table.")
            return None
        return self._review_item_to_mode.get(selection[0])

    def set_manual_review(self, abaqus_mode: int, decision: str, experimental_mode=None, comment=None) -> None:
        key = str(int(abaqus_mode))
        current = dict(self.manual_reviews.get(key, {}))
        current["decision"] = decision
        if experimental_mode is not None or "experimental_mode" not in current:
            current["experimental_mode"] = experimental_mode
        if comment is not None:
            current["comment"] = comment
        current.setdefault("comment", "")
        current["updated_at"] = utc_timestamp()
        self.manual_reviews[key] = current
        self._apply_manual_reviews(refresh=True)
        self._save_last_session()

    def manual_accept(self) -> None:
        abaqus_mode = self._selected_review_mode()
        if abaqus_mode is None:
            return
        current = self.manual_reviews.get(str(abaqus_mode), {})
        experimental_mode = current.get("experimental_mode")
        if experimental_mode is None:
            automatic = self._automatic_pairs_by_mode.get(abaqus_mode)
            if automatic is None:
                messagebox.showinfo(
                    "Manual review",
                    "This Abaqus mode has no selected experimental mode. Use Change experimental mode first.",
                )
                return
            experimental_mode = automatic.experimental_mode
        self._set_manual_review(abaqus_mode, "accepted", experimental_mode=experimental_mode)

    def manual_reject(self) -> None:
        abaqus_mode = self._selected_review_mode()
        if abaqus_mode is not None:
            self._set_manual_review(abaqus_mode, "rejected")

    def manual_unresolved(self) -> None:
        abaqus_mode = self._selected_review_mode()
        if abaqus_mode is not None:
            self._set_manual_review(abaqus_mode, "unresolved")

    def manual_comment(self) -> None:
        abaqus_mode = self._selected_review_mode()
        if abaqus_mode is None:
            return
        current = self.manual_reviews.get(str(abaqus_mode), {})
        comment = simpledialog.askstring(
            "Manual-review comment",
            f"Comment for Abaqus mode {abaqus_mode}:",
            initialvalue=str(current.get("comment", "")),
            parent=self.root,
        )
        if comment is not None:
            self._set_manual_review(
                abaqus_mode,
                str(current.get("decision", "automatic")),
                experimental_mode=current.get("experimental_mode"),
                comment=comment,
            )

    def manual_reset(self) -> None:
        abaqus_mode = self._selected_review_mode()
        if abaqus_mode is None:
            return
        self.manual_reviews.pop(str(abaqus_mode), None)
        self._manual_candidate_pairs.pop(abaqus_mode, None)
        self._apply_manual_reviews(refresh=True)
        self._save_last_session()

    def manual_change_mode(self) -> None:
        abaqus_mode = self._selected_review_mode()
        if abaqus_mode is None or self.result is None:
            return
        window = tk.Toplevel(self.root)
        window.title(f"Select experimental mode for Abaqus mode {abaqus_mode}")
        window.geometry("720x520")
        window.transient(self.root)
        window.grab_set()
        columns = ("em", "freq", "error", "mac", "source")
        table = ttk.Treeview(window, columns=columns, show="headings", selectmode="browse")
        for key, title, width in (
            ("em", "Experimental mode", 125),
            ("freq", "Frequency, Hz", 120),
            ("error", "Signed error, %", 115),
            ("mac", "MAC", 90),
            ("source", "Source", 190),
        ):
            table.heading(key, text=title)
            table.column(key, width=width, anchor="center")
        table.pack(fill="both", expand=True, padx=10, pady=10)
        candidates: Dict[str, ModePairResult] = {}
        used_modes = {
            int(pair.experimental_mode): int(pair.abaqus_mode)
            for pair in self.result.pairs
            if int(pair.abaqus_mode) != int(abaqus_mode)
        }
        for experimental_mode in self.result.experimental.sorted_modes():
            try:
                pair = build_manual_pair(self.result, abaqus_mode, experimental_mode.number)
            except ValueError:
                # build_manual_pair raises ValueError for a candidate with no
                # common measured DOF, or a mode number that no longer exists;
                # that mode is simply not a viable candidate for this list.
                # Anything else is a real bug and must not be hidden here.
                continue
            metadata = experimental_mode.metadata
            source = metadata.get("source_label") or metadata.get("mode_source") or "Unknown"
            item = table.insert(
                "",
                "end",
                values=(
                    experimental_mode.number,
                    f"{experimental_mode.frequency_hz:.5f}",
                    f"{pair.frequency_error_percent:+.2f}",
                    "—" if pair.mac is None else f"{pair.mac:.3f}",
                    source,
                ),
            )
            candidates[item] = pair
            if experimental_mode.number in used_modes:
                table.item(item, tags=("used",))
        table.tag_configure("used", background="#FCE8E6")

        footer = ttk.Frame(window)
        footer.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Label(footer, text="Red rows are already used by another effective pair.").pack(side="left")

        def choose() -> None:
            selection = table.selection()
            if not selection:
                return
            pair = candidates[selection[0]]
            owner = used_modes.get(int(pair.experimental_mode))
            if owner is not None:
                messagebox.showwarning(
                    "Experimental mode already used",
                    f"Experimental mode E{pair.experimental_mode} is already paired with A{owner}. "
                    "Reject or mark that pair unresolved first.",
                    parent=window,
                )
                return
            self._manual_candidate_pairs[int(abaqus_mode)] = pair
            self._set_manual_review(
                int(abaqus_mode),
                "accepted",
                experimental_mode=int(pair.experimental_mode),
            )
            window.destroy()

        ttk.Button(footer, text="Use selected mode", command=choose).pack(side="right")
        ttk.Button(footer, text="Cancel", command=window.destroy).pack(side="right", padx=6)
        table.bind("<Double-1>", lambda _event: choose())

    def apply_manual_reviews(self, refresh: bool = True) -> None:
        if self.result is None:
            self._refresh_review_table()
            return
        base_pairs = dict(self._automatic_pairs_by_mode)
        effective = []
        for abaqus_mode in [mode.number for mode in _all_elastic_abaqus_modes(self.result)]:
            automatic = base_pairs.get(int(abaqus_mode))
            review = self.manual_reviews.get(str(int(abaqus_mode)), {})
            decision = str(review.get("decision", "automatic"))
            selected_experimental = review.get("experimental_mode")
            pair = automatic
            if selected_experimental is not None and (
                automatic is None or int(automatic.experimental_mode) != int(selected_experimental)
            ):
                pair = self._manual_candidate_pairs.get(int(abaqus_mode))
                if pair is None or int(pair.experimental_mode) != int(selected_experimental):
                    try:
                        pair = build_manual_pair(self.result, int(abaqus_mode), int(selected_experimental))
                        self._manual_candidate_pairs[int(abaqus_mode)] = pair
                    except ValueError as error:
                        # A manually requested pair with no common measured DOF
                        # (or a stale mode number) is dropped from the effective
                        # set below rather than crashing the review. Any other
                        # exception is a real bug in the reviewed pair and must
                        # propagate instead of silently vanishing from the report.
                        _log_recoverable_error(
                            f"apply_manual_reviews: A{abaqus_mode}/E{selected_experimental}",
                            error,
                        )
                        pair = None
            if decision in {"rejected", "unresolved"}:
                continue
            if pair is None:
                continue
            setattr(pair, "manual_decision", decision)
            setattr(pair, "manual_comment", str(review.get("comment", "")))
            effective.append(pair)

        effective.sort(key=lambda pair: pair.abaqus_frequency_hz)
        _recalculate_order_changed(effective)
        self.result.pairs = effective
        base_warnings = getattr(self.result, "_warnings_before_manual_review", None)
        if base_warnings is None:
            base_warnings = list(self.result.warnings)
            setattr(self.result, "_warnings_before_manual_review", base_warnings)
        self.result.warnings = list(base_warnings)
        if self.manual_reviews:
            accepted = sum(1 for item in self.manual_reviews.values() if item.get("decision") == "accepted")
            rejected = sum(1 for item in self.manual_reviews.values() if item.get("decision") == "rejected")
            unresolved = sum(1 for item in self.manual_reviews.values() if item.get("decision") == "unresolved")
            self.result.warnings.append(
                f"Manual review applied: {accepted} accepted, {rejected} rejected, {unresolved} unresolved."
            )
        if refresh:
            self._invalidate_review_plots()
            self._populate(self.result)
            self.status.set("Manual review applied. Effective plots and reports were refreshed.")

    def invalidate_review_plots(self) -> None:
        if self.cache is None:
            return
        plot_directory = self.cache / "plots"
        for name in (
            "frequency_comparison.png",
            "verified_mac_matrix.png",
            "abaqus_automac.png",
            "experimental_automac.png",
            "comac_map.png",
            "automac_comac.png",
        ):
            try:
                (plot_directory / name).unlink(missing_ok=True)
            except OSError as error:
                _log_recoverable_error(f"invalidate_review_plots: unlink {name}", error)
        try:
            app_module.render_frequency_comparison(
                self.result, plot_directory / "frequency_comparison.png"
            )
            from enhanced_reporting import render_verified_mac_matrix
            render_verified_mac_matrix(self.result, plot_directory / "verified_mac_matrix.png")
        except Exception as error:
            # The stale plots were already removed above, so a failed
            # re-render leaves the images missing rather than silently wrong;
            # still surface it, since a plot that should reflect the current
            # manual-review pair set failing to regenerate is worth knowing.
            _log_recoverable_error("invalidate_review_plots: re-render", error)
            self.result.warnings.append(
                "Frequency/verified-MAC plots could not be refreshed after the "
                f"manual review change; see {ERROR_LOG_PATH}."
            )

    def refresh_review_table(self) -> None:
        if not hasattr(self, "review_table"):
            return
        self.review_table.delete(*self.review_table.get_children())
        self._review_item_to_mode.clear()
        if self.result is None:
            return
        automatic = self._automatic_pairs_by_mode
        experimental_lookup = {mode.number: mode for mode in self.result.experimental.modes}
        for mode in _all_elastic_abaqus_modes(self.result):
            auto_pair = automatic.get(int(mode.number))
            review = self.manual_reviews.get(str(int(mode.number)), {})
            decision = str(review.get("decision", "automatic"))
            current_pair = auto_pair
            selected_experimental = review.get("experimental_mode")
            if selected_experimental is not None and (
                auto_pair is None or int(auto_pair.experimental_mode) != int(selected_experimental)
            ):
                current_pair = self._manual_candidate_pairs.get(int(mode.number))
                if current_pair is None:
                    try:
                        current_pair = build_manual_pair(self.result, mode.number, selected_experimental)
                        self._manual_candidate_pairs[int(mode.number)] = current_pair
                    except Exception:
                        current_pair = None
            auto_em = "—" if auto_pair is None else f"E{auto_pair.experimental_mode}"
            current_em = "—" if current_pair is None else f"E{current_pair.experimental_mode}"
            ef = "—" if current_pair is None else f"{current_pair.experimental_frequency_hz:.5f}"
            error = "—" if current_pair is None else f"{current_pair.frequency_error_percent:+.2f}"
            mac = "—" if current_pair is None or current_pair.mac is None else f"{current_pair.mac:.3f}"
            auto_status = "Unmatched" if auto_pair is None else auto_pair.status
            display_decision = decision.title()
            if auto_pair is None and decision == "automatic":
                display_decision = "Unresolved (auto)"
            item = self.review_table.insert(
                "",
                "end",
                values=(
                    mode.number,
                    f"{mode.frequency_hz:.5f}",
                    auto_em,
                    current_em,
                    ef,
                    error,
                    mac,
                    auto_status,
                    display_decision,
                    str(review.get("comment", "")),
                ),
            )
            self._review_item_to_mode[item] = int(mode.number)

    application_class.__init__ = reviewed_init
    application_class._install_project_controls = install_project_controls
    application_class._install_manual_columns = install_manual_columns
    application_class._install_manual_review_tab = install_manual_review_tab
    application_class._project_payload_for_self = project_payload_for_self
    application_class._apply_project_payload = apply_project_payload
    application_class._save_last_session = save_last_session
    application_class._restore_last_session = restore_last_session
    application_class._new_project = new_project
    application_class._open_project = open_project
    application_class._save_project = save_project
    application_class._save_project_as = save_project_as
    application_class._close_with_session_save = close_with_session_save
    application_class._complete = reviewed_complete
    application_class._populate = reviewed_populate
    application_class._details = reviewed_details
    application_class._selected_review_mode = selected_review_mode
    application_class._set_manual_review = set_manual_review
    application_class._manual_accept = manual_accept
    application_class._manual_reject = manual_reject
    application_class._manual_unresolved = manual_unresolved
    application_class._manual_comment = manual_comment
    application_class._manual_reset = manual_reset
    application_class._manual_change_mode = manual_change_mode
    application_class._apply_manual_reviews = apply_manual_reviews
    application_class._invalidate_review_plots = invalidate_review_plots
    application_class._refresh_review_table = refresh_review_table
    _INSTALLED = True
