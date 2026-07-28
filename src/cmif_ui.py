from __future__ import annotations

import shutil
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from cmif_separation import render_cmif_svd_diagnostics
from figure_export_ui import FullSizeImageViewer


_INSTALLED = False
COMPACT_SUMMARY_LINES = 6
EXPANDED_SUMMARY_LINES = 18


def summary_height(expanded: bool) -> int:
    """Return the fixed text height used by the close-mode summary panel."""
    return EXPANDED_SUMMARY_LINES if expanded else COMPACT_SUMMARY_LINES


def _replace_readonly_text(widget: tk.Text, value: str) -> None:
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", value)
    widget.configure(state="disabled")
    widget.yview_moveto(0.0)


def _summary_text(result) -> str:
    information = result.experimental.metadata.get("close_mode_separation", {})
    method = information.get("method", "not available")
    clusters = information.get("clusters", [])
    lines = [
        f"Method: {method}",
        f"Excitation references: {information.get('reference_count', '—')}",
        f"Additional close-mode candidates: {information.get('added_mode_count', 0)}",
    ]
    for index, cluster in enumerate(clusters, start=1):
        targets = ", ".join(f"{value:.3f}" for value in cluster.get("cluster", []))
        existing = ", ".join(
            f"{value:.3f}" for value in cluster.get("existing_peak_frequencies_hz", [])
        ) or "none"
        added = ", ".join(
            f"{value:.3f}" for value in cluster.get("added_candidate_frequencies_hz", [])
        ) or "none"
        ratios = ", ".join(
            f"{value:.3f}" for value in cluster.get("singular_value_ratios", [])
        ) or "—"
        lines.extend(
            [
                f"Cluster {index}: Abaqus targets {targets} Hz",
                f"  existing experimental peaks: {existing} Hz",
                f"  added SVD candidates: {added} Hz",
                f"  local singular-value ratios: {ratios}",
            ]
        )
    warning = information.get("scientific_warning")
    if warning:
        lines.extend(["", "Interpretation:", str(warning)])

    abaqus_meta = result.abaqus.metadata
    experimental_meta = result.experimental.metadata
    lines.extend(
        [
            "",
            "Performance cache:",
            f"  ODB extraction reused: {abaqus_meta.get('extraction_cache_reused', '—')}",
            f"  Binary ODB dataset reused: {abaqus_meta.get('binary_odb_cache_reused', '—')}",
            f"  ODB dataset load: {float(abaqus_meta.get('odb_dataset_load_seconds', 0.0)):.3f} s",
            f"  UNV cache reused: {experimental_meta.get('unv_cache_reused', '—')}",
            f"  UNV load: {float(experimental_meta.get('unv_load_seconds', 0.0)):.3f} s",
        ]
    )
    return "\n".join(lines)


def install_cmif_ui(app_module) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    application_class = app_module.ModalComparatorApp
    original_build = application_class._build
    original_populate = application_class._populate

    def cmif_build(self) -> None:
        original_build(self)
        self.cmif_tab = ttk.Frame(self.tabs, padding=10)
        insert_index = self.tabs.index(self.advanced_tab)
        self.tabs.insert(insert_index, self.cmif_tab, text="6. Close modes — SVD")
        self.tabs.tab(self.advanced_tab, text="7. AutoMAC & COMAC")
        self.tabs.tab(self.details_tab, text="8. Details")

        plot_frame = ttk.LabelFrame(
            self.cmif_tab,
            text="Local close-mode separation diagnostics",
            padding=6,
        )
        plot_frame.pack(fill="both", expand=True)
        self.cmif_label = ttk.Label(
            plot_frame,
            text="Run the analysis to inspect overlapping resonance bands.",
            anchor="center",
        )
        self.cmif_label.pack(fill="both", expand=True)

        controls = ttk.Frame(self.cmif_tab)
        controls.pack(fill="x", pady=(8, 0))

        def current_path():
            if self.cache is None:
                return None
            path = self.cache / "plots" / "cmif_svd_diagnostics.png"
            return path if path.exists() else None

        def open_full_size() -> None:
            path = current_path()
            if path is None:
                messagebox.showwarning("Image unavailable", "Run the analysis first.")
                return
            FullSizeImageViewer(self.root, path, "Close-mode SVD diagnostics")

        def save_png() -> None:
            path = current_path()
            if path is None:
                messagebox.showwarning("Image unavailable", "Run the analysis first.")
                return
            destination = filedialog.asksaveasfilename(
                title="Save close-mode diagnostics",
                defaultextension=".png",
                initialfile="cmif_svd_diagnostics.png",
                filetypes=[("PNG image", "*.png")],
            )
            if destination:
                shutil.copy2(path, destination)

        def save_summary() -> None:
            if self.result is None:
                messagebox.showwarning("No analysis", "Run the analysis first.")
                return
            destination = filedialog.asksaveasfilename(
                title="Save close-mode summary",
                defaultextension=".txt",
                initialfile="close_mode_svd_summary.txt",
                filetypes=[("Text file", "*.txt")],
            )
            if destination:
                Path(destination).write_text(
                    _summary_text(self.result), encoding="utf-8"
                )

        ttk.Button(controls, text="Open full size", command=open_full_size).pack(side="left")
        ttk.Button(controls, text="Save PNG…", command=save_png).pack(side="left", padx=6)
        ttk.Button(controls, text="Save summary…", command=save_summary).pack(side="left")

        summary_frame = ttk.LabelFrame(
            self.cmif_tab,
            text="Close-mode decision and performance",
            padding=6,
        )
        summary_frame.pack(fill="x", pady=(8, 0))
        summary_frame.columnconfigure(0, weight=1)

        summary_toolbar = ttk.Frame(summary_frame)
        summary_toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        ttk.Label(
            summary_toolbar,
            text="Detailed diagnostics are scrollable; keep this panel compact to enlarge the plot.",
        ).pack(side="left", fill="x", expand=True)

        self.cmif_summary_expanded = False

        def toggle_summary() -> None:
            self.cmif_summary_expanded = not self.cmif_summary_expanded
            self.cmif_summary.configure(
                height=summary_height(self.cmif_summary_expanded)
            )
            self.cmif_summary_toggle.configure(
                text="Collapse details" if self.cmif_summary_expanded else "Expand details"
            )
            refresh = getattr(self, "_refresh_responsive_images", None)
            if callable(refresh):
                self.root.after_idle(refresh)

        self.cmif_summary_toggle = ttk.Button(
            summary_toolbar,
            text="Expand details",
            command=toggle_summary,
        )
        self.cmif_summary_toggle.pack(side="right", padx=(8, 0))

        self.cmif_summary = tk.Text(
            summary_frame,
            height=summary_height(False),
            wrap="word",
            font=("Consolas", 9),
            state="disabled",
            relief="flat",
            borderwidth=0,
            padx=3,
            pady=2,
        )
        summary_scroll = ttk.Scrollbar(
            summary_frame,
            orient="vertical",
            command=self.cmif_summary.yview,
        )
        self.cmif_summary.configure(yscrollcommand=summary_scroll.set)
        self.cmif_summary.grid(row=1, column=0, sticky="ew")
        summary_scroll.grid(row=1, column=1, sticky="ns", padx=(4, 0))
        _replace_readonly_text(self.cmif_summary, "No analysis results yet.")

    def cmif_populate(self, result) -> None:
        original_populate(self, result)
        if self.cache is None:
            return
        plot_path = self.cache / "plots" / "cmif_svd_diagnostics.png"
        if not plot_path.exists():
            render_cmif_svd_diagnostics(result.experimental, plot_path)
        self._image(self.cmif_label, plot_path, "cmif_svd_diagnostics")
        _replace_readonly_text(self.cmif_summary, _summary_text(result))

    application_class._build = cmif_build
    application_class._populate = cmif_populate
    _INSTALLED = True
