from __future__ import annotations

import hashlib
import json
import os
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Dict, Optional

from PIL import Image, ImageTk

from abaqus_bridge import AbaqusExtractionError, load_or_extract_odb
from modal_core import ComparisonResult, ModePairResult, compare_modal_datasets
from reporting import (
    export_excel,
    export_pdf,
    render_frequency_comparison,
    render_mac_matrix,
    render_pair_images,
)
from universal_reader import load_universal_modal_file, resolve_testlab_file

APP_TITLE = "Abaqus–Simcenter Modal Comparator"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKSPACE = PROJECT_ROOT / "modal_comparator_output"


class ModalComparatorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title(APP_TITLE)
        root.geometry("1500x900")
        root.minsize(1160, 720)

        self.abaqus_path = tk.StringVar()
        self.experimental_path = tk.StringVar()
        self.workspace_path = tk.StringVar(value=str(DEFAULT_WORKSPACE))
        self.abaqus_command = tk.StringVar(value="abaqus")
        self.start_mode = tk.IntVar(value=6)
        self.end_mode = tk.IntVar(value=14)
        self.status = tk.StringVar(value="Ready. Select Abaqus and Simcenter result files.")

        self.result: Optional[ComparisonResult] = None
        self.cache: Optional[Path] = None
        self.item_to_pair: Dict[str, ModePairResult] = {}
        self.photos: Dict[str, ImageTk.PhotoImage] = {}
        self.running = False

        self._style()
        self._build()

    def _style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"))
        style.configure("Metric.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("Treeview", rowheight=27)
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    def _build(self) -> None:
        header = ttk.Frame(self.root, padding=(18, 14, 18, 8))
        header.pack(fill="x")
        ttk.Label(header, text=APP_TITLE, style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="ODB extraction • Testlab UNV/UFF import • geometry mapping • MAC • reports",
        ).pack(anchor="w")

        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        self.input_tab = ttk.Frame(self.tabs, padding=18)
        self.table_tab = ttk.Frame(self.tabs, padding=12)
        self.shape_tab = ttk.Frame(self.tabs, padding=12)
        self.plot_tab = ttk.Frame(self.tabs, padding=12)
        self.details_tab = ttk.Frame(self.tabs, padding=12)
        for tab, title in (
            (self.input_tab, "1. Files and analysis"),
            (self.table_tab, "2. Comparison table"),
            (self.shape_tab, "3. Mode shapes"),
            (self.plot_tab, "4. MAC and frequencies"),
            (self.details_tab, "5. Details"),
        ):
            self.tabs.add(tab, text=title)

        self._build_input()
        self._build_table()
        self._build_shapes()
        self._build_plots()
        self._build_details()

        footer = ttk.Frame(self.root, padding=(16, 0, 16, 10))
        footer.pack(fill="x")
        ttk.Label(footer, textvariable=self.status).pack(side="left", fill="x", expand=True)
        self.progress = ttk.Progressbar(footer, mode="indeterminate", length=220)
        self.progress.pack(side="right")

    def _build_input(self) -> None:
        files = ttk.LabelFrame(self.input_tab, text="Source files", padding=14)
        files.pack(fill="x")
        files.columnconfigure(1, weight=1)
        self._file_row(files, 0, "Abaqus results", self.abaqus_path, self._choose_abaqus,
                       "Select .odb, or a previously extracted manifest.json.")
        self._file_row(files, 1, "Simcenter Testlab results", self.experimental_path,
                       self._choose_experiment,
                       "Select .unv/.uff. A .lms file is accepted when its companion UNV/UFF is beside it.")
        self._file_row(files, 2, "Output workspace", self.workspace_path, self._choose_workspace,
                       "Extraction cache, plots, Excel, PDF, and logs are written here.")

        settings = ttk.LabelFrame(self.input_tab, text="Analysis settings", padding=14)
        settings.pack(fill="x", pady=(14, 0))
        ttk.Label(settings, text="Abaqus command:").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(settings, textvariable=self.abaqus_command, width=32).grid(row=0, column=1, sticky="w", padx=8)
        ttk.Label(settings, text="Examples: abaqus, abq2024, or full path to an Abaqus .bat command").grid(
            row=0, column=2, sticky="w")
        ttk.Label(settings, text="Abaqus mode range:").grid(row=1, column=0, sticky="w", pady=6)
        mode_box = ttk.Frame(settings)
        mode_box.grid(row=1, column=1, sticky="w", padx=8)
        ttk.Spinbox(mode_box, from_=1, to=999, textvariable=self.start_mode, width=7).pack(side="left")
        ttk.Label(mode_box, text="to").pack(side="left", padx=7)
        ttk.Spinbox(mode_box, from_=1, to=999, textvariable=self.end_mode, width=7).pack(side="left")
        ttk.Label(settings, text="Default 6–14; experimental modes are detected automatically.").grid(
            row=1, column=2, sticky="w")

        buttons = ttk.Frame(self.input_tab)
        buttons.pack(fill="x", pady=18)
        self.run_button = ttk.Button(buttons, text="Extract, compare, and build report data",
                                     command=self._start)
        self.run_button.pack(side="left")
        self.folder_button = ttk.Button(buttons, text="Open output folder",
                                        command=self._open_workspace, state="disabled")
        self.folder_button.pack(side="left", padx=10)

        info = ttk.LabelFrame(self.input_tab, text="Automatic workflow", padding=14)
        info.pack(fill="both", expand=True)
        ttk.Label(
            info,
            justify="left",
            wraplength=1200,
            text=(
                "1. Abaqus Python opens the ODB and extracts natural frequencies, FE coordinates, and U1/U2/U3 mode vectors.\n\n"
                "2. The Testlab importer reads geometry, frequencies, damping, modal mass, and complex mode vectors from UNV/UFF.\n\n"
                "3. Coordinate scale, axis order, and axis signs are detected automatically; experimental points are mapped to FE nodes.\n\n"
                "4. The application builds the full MAC matrix, pairs modes one-to-one, calculates frequency errors, and detects order changes.\n\n"
                "5. Abaqus, experimental, and overlaid mode-shape plots are generated automatically and can be exported to Excel and PDF."
            ),
        ).pack(anchor="nw")

    def _file_row(self, parent, row, label, variable, command, help_text) -> None:
        r = row * 2
        ttk.Label(parent, text=label + ":").grid(row=r, column=0, sticky="w", padx=(0, 10), pady=(8, 2))
        ttk.Entry(parent, textvariable=variable).grid(row=r, column=1, sticky="ew", pady=(8, 2))
        ttk.Button(parent, text="Browse…", command=command).grid(row=r, column=2, padx=(10, 0), pady=(8, 2))
        ttk.Label(parent, text=help_text).grid(row=r + 1, column=1, sticky="w", pady=(0, 5))

    def _build_table(self) -> None:
        metrics = ttk.Frame(self.table_tab)
        metrics.pack(fill="x", pady=(0, 10))
        self.metric_pairs = ttk.Label(metrics, text="Matched pairs: —", style="Metric.TLabel")
        self.metric_error = ttk.Label(metrics, text="Mean frequency error: —", style="Metric.TLabel")
        self.metric_mac = ttk.Label(metrics, text="Mean MAC: —", style="Metric.TLabel")
        self.metric_geometry = ttk.Label(metrics, text="Geometry match: —", style="Metric.TLabel")
        for widget in (self.metric_pairs, self.metric_error, self.metric_mac, self.metric_geometry):
            widget.pack(side="left", padx=(0, 24))

        columns = ("am", "em", "af", "ef", "err", "mac", "order", "points", "status")
        frame = ttk.Frame(self.table_tab)
        frame.pack(fill="both", expand=True)
        self.table = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        titles = ("Abaqus mode", "Experimental mode", "Abaqus, Hz", "Experiment, Hz",
                  "Error, %", "MAC", "Order changed", "Mapped points", "Status")
        widths = (100, 130, 110, 120, 90, 80, 110, 105, 150)
        for key, title, width in zip(columns, titles, widths):
            self.table.heading(key, text=title)
            self.table.column(key, width=width, anchor="center")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.table.bind("<<TreeviewSelect>>", self._selected)

        actions = ttk.Frame(self.table_tab)
        actions.pack(fill="x", pady=(10, 0))
        self.excel_button = ttk.Button(actions, text="Export Excel report", command=self._excel, state="disabled")
        self.pdf_button = ttk.Button(actions, text="Export PDF report", command=self._pdf, state="disabled")
        self.excel_button.pack(side="left")
        self.pdf_button.pack(side="left", padx=10)

    def _build_shapes(self) -> None:
        self.pair_title = ttk.Label(self.shape_tab, text="Run the analysis and select a matched pair.",
                                    style="Metric.TLabel")
        self.pair_title.pack(fill="x", pady=(0, 8))
        frame = ttk.Frame(self.shape_tab)
        frame.pack(fill="both", expand=True)
        self.shape_labels = []
        for column, title in enumerate(("Abaqus mode shape", "Experimental mode shape", "Overlay")):
            cell = ttk.LabelFrame(frame, text=title, padding=5)
            cell.grid(row=0, column=column, sticky="nsew", padx=4)
            label = ttk.Label(cell, text="No image", anchor="center")
            label.pack(fill="both", expand=True)
            self.shape_labels.append(label)
            frame.columnconfigure(column, weight=1)
        frame.rowconfigure(0, weight=1)

    def _build_plots(self) -> None:
        frame = ttk.Frame(self.plot_tab)
        frame.pack(fill="both", expand=True)
        self.mac_label = ttk.Label(ttk.LabelFrame(frame, text="MAC matrix", padding=5), text="No plot")
        self.frequency_label = ttk.Label(ttk.LabelFrame(frame, text="Frequency comparison", padding=5), text="No plot")
        self.mac_label.master.grid(row=0, column=0, sticky="nsew", padx=4)
        self.frequency_label.master.grid(row=0, column=1, sticky="nsew", padx=4)
        self.mac_label.pack(fill="both", expand=True)
        self.frequency_label.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(0, weight=1)

    def _build_details(self) -> None:
        frame = ttk.Frame(self.details_tab)
        frame.pack(fill="both", expand=True)
        self.details = tk.Text(frame, wrap="none", font=("Consolas", 10), state="disabled")
        y_scroll = ttk.Scrollbar(frame, orient="vertical", command=self.details.yview)
        x_scroll = ttk.Scrollbar(frame, orient="horizontal", command=self.details.xview)
        self.details.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.details.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

    def _choose_abaqus(self) -> None:
        path = filedialog.askopenfilename(title="Select Abaqus results",
            filetypes=[("Abaqus ODB", "*.odb"), ("Extracted manifest", "manifest.json"), ("All files", "*.*")])
        if path:
            self.abaqus_path.set(path)

    def _choose_experiment(self) -> None:
        path = filedialog.askopenfilename(title="Select Simcenter Testlab results",
            filetypes=[("Universal modal files", "*.unv *.uff"), ("Testlab project", "*.lms"), ("All files", "*.*")])
        if path:
            self.experimental_path.set(path)

    def _choose_workspace(self) -> None:
        path = filedialog.askdirectory(title="Select output workspace")
        if path:
            self.workspace_path.set(path)

    def _validate(self) -> Optional[tuple[Path, Path, Path, int, int, str]]:
        abaqus = Path(self.abaqus_path.get().strip())
        experiment = Path(self.experimental_path.get().strip())
        workspace = Path(self.workspace_path.get().strip())
        start, end = int(self.start_mode.get()), int(self.end_mode.get())
        if not abaqus.exists():
            messagebox.showwarning("Missing Abaqus file", "Select an existing .odb or manifest.json file.")
            return None
        if not experiment.exists():
            messagebox.showwarning("Missing experimental file", "Select an existing .unv, .uff, or .lms file.")
            return None
        if start < 1 or end < start:
            messagebox.showwarning("Invalid mode range", "The final mode must be greater than or equal to the first mode.")
            return None
        return abaqus, experiment, workspace, start, end, self.abaqus_command.get().strip() or "abaqus"

    def _start(self) -> None:
        if self.running:
            return
        values = self._validate()
        if values is None:
            return
        self.running = True
        self.run_button.configure(state="disabled")
        self.progress.start(12)
        self.status.set("Reading files and calculating modal correlation…")
        threading.Thread(target=self._worker, args=values, daemon=True).start()

    def _worker(self, abaqus: Path, experiment: Path, workspace: Path,
                start: int, end: int, command: str) -> None:
        try:
            workspace.mkdir(parents=True, exist_ok=True)
            key = hashlib.sha1(f"{abaqus.resolve()}|{start}|{end}".encode("utf-8")).hexdigest()[:12]
            cache = workspace / f"analysis_{key}"
            cache.mkdir(parents=True, exist_ok=True)
            abaqus_data = load_or_extract_odb(abaqus, cache / "abaqus", command, start, end)
            resolved_experiment = resolve_testlab_file(experiment)
            experiment_data = load_universal_modal_file(resolved_experiment)
            result = compare_modal_datasets(abaqus_data, experiment_data)
            plot_dir = cache / "plots"
            render_mac_matrix(result, plot_dir / "mac_matrix.png")
            render_frequency_comparison(result, plot_dir / "frequency_comparison.png")
            self._write_summary(result, cache / "analysis_summary.json")
            self.cache = cache
            self.root.after(0, lambda: self._complete(result))
        except Exception as error:
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "last_error.log").write_text(traceback.format_exc(), encoding="utf-8")
            self.root.after(0, lambda err=error: self._failed(err))

    @staticmethod
    def _write_summary(result: ComparisonResult, path: Path) -> None:
        payload = {
            "abaqus_source": str(result.abaqus.source_path),
            "experimental_source": str(result.experimental.source_path),
            "geometry_match_fraction": result.geometry.matched_fraction,
            "geometry_normalized_rms": result.geometry.normalized_rms_distance,
            "warnings": result.warnings,
            "pairs": [
                {
                    "abaqus_mode": p.abaqus_mode,
                    "experimental_mode": p.experimental_mode,
                    "abaqus_frequency_hz": p.abaqus_frequency_hz,
                    "experimental_frequency_hz": p.experimental_frequency_hz,
                    "frequency_error_percent": p.frequency_error_percent,
                    "mac": p.mac,
                    "status": p.status,
                }
                for p in result.pairs
            ],
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _complete(self, result: ComparisonResult) -> None:
        self.running = False
        self.progress.stop()
        self.run_button.configure(state="normal")
        self.folder_button.configure(state="normal")
        self.excel_button.configure(state="normal")
        self.pdf_button.configure(state="normal")
        self.result = result
        self._populate(result)
        self.status.set("Analysis completed. Select a row to inspect the matched mode shapes.")
        self.tabs.select(self.table_tab)

    def _failed(self, error: Exception) -> None:
        self.running = False
        self.progress.stop()
        self.run_button.configure(state="normal")
        self.status.set("Analysis failed. See last_error.log in the output workspace.")
        text = str(error)
        if isinstance(error, AbaqusExtractionError):
            text += "\n\nCheck the Abaqus command and confirm that this ODB opens in your installed Abaqus version."
        messagebox.showerror("Analysis failed", text)

    def _populate(self, result: ComparisonResult) -> None:
        self.table.delete(*self.table.get_children())
        self.item_to_pair.clear()
        for pair in result.pairs:
            item = self.table.insert("", "end", values=(
                pair.abaqus_mode, pair.experimental_mode,
                f"{pair.abaqus_frequency_hz:.4f}", f"{pair.experimental_frequency_hz:.4f}",
                f"{pair.frequency_error_percent:.2f}", "—" if pair.mac is None else f"{pair.mac:.3f}",
                "Yes" if pair.order_changed else "No", pair.mapped_points, pair.status))
            self.item_to_pair[item] = pair

        errors = [p.frequency_error_percent for p in result.pairs]
        macs = [p.mac for p in result.pairs if p.mac is not None]
        self.metric_pairs.configure(text=f"Matched pairs: {len(result.pairs)}")
        self.metric_error.configure(text=f"Mean frequency error: {sum(errors) / len(errors):.2f}%")
        self.metric_mac.configure(text="Mean MAC: —" if not macs else f"Mean MAC: {sum(macs) / len(macs):.3f}")
        self.metric_geometry.configure(text=f"Geometry match: {result.geometry.matched_fraction:.1%}")

        if self.cache:
            self._image(self.mac_label, self.cache / "plots" / "mac_matrix.png", "mac")
            self._image(self.frequency_label, self.cache / "plots" / "frequency_comparison.png", "frequency")
        self._details(result)
        children = self.table.get_children()
        if children:
            self.table.selection_set(children[0])
            self.table.focus(children[0])
            self._show_pair(self.item_to_pair[children[0]])

    def _details(self, result: ComparisonResult) -> None:
        lines = [
            "ANALYSIS SUMMARY", "=" * 80,
            f"Abaqus source: {result.abaqus.source_path}",
            f"Experimental source: {result.experimental.source_path}",
            f"Abaqus modes: {result.abaqus_mode_numbers}",
            f"Experimental modes: {result.experimental_mode_numbers}", "",
            "GEOMETRY ALIGNMENT", "-" * 80,
            f"Coordinate scale: {result.geometry.coordinate_scale:.8g}",
            f"Matched points: {result.geometry.matched_fraction:.2%}",
            f"RMS / diagonal: {result.geometry.normalized_rms_distance:.3%}",
            f"Mean mapping distance: {result.geometry.distances.mean():.8g}",
            f"Maximum mapping distance: {result.geometry.distances.max():.8g}", "",
        ]
        if result.warnings:
            lines.extend(["WARNINGS", "-" * 80] + ["• " + w for w in result.warnings] + [""])
        lines.extend(["SIMCENTER MODES", "-" * 80])
        for mode in result.experimental.sorted_modes():
            damping = "—" if mode.damping_ratio is None else f"{mode.damping_ratio:.6g}"
            mass = "—" if mode.modal_mass is None else f"{mode.modal_mass:.6g}"
            lines.append(f"Mode {mode.number}: {mode.frequency_hz:.5f} Hz | damping {damping} | modal mass {mass} | points {len(mode.node_ids)}")
        lines.extend(["", "ABAQUS METADATA", "-" * 80])
        lines.extend(f"{key}: {value}" for key, value in sorted(result.abaqus.metadata.items()) if key not in ("modes", "history"))
        lines.extend(["", "SIMCENTER METADATA", "-" * 80])
        lines.extend(f"{key}: {value}" for key, value in sorted(result.experimental.metadata.items()))
        lines.extend(["", "ABAQUS MODAL HISTORY OUTPUTS", "-" * 80])
        if result.abaqus.history:
            lines.extend(f"{item.get('region')} | {item.get('name')} | values={len(item.get('data', []))}" for item in result.abaqus.history)
        else:
            lines.append("No modal history outputs were found in the selected ODB step.")
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", "\n".join(lines))
        self.details.configure(state="disabled")

    def _selected(self, _event=None) -> None:
        selected = self.table.selection()
        if selected and selected[0] in self.item_to_pair:
            self._show_pair(self.item_to_pair[selected[0]])

    def _show_pair(self, pair: ModePairResult) -> None:
        if self.cache is None:
            return
        paths = render_pair_images(pair, self.cache / "plots" / "mode_pairs")
        for label, key, image_key in zip(self.shape_labels, ("abaqus", "experimental", "overlay"),
                                         ("pair_a", "pair_e", "pair_o")):
            self._image(label, paths[key], image_key)
        mac = "unavailable" if pair.mac is None else f"{pair.mac:.3f}"
        self.pair_title.configure(text=(
            f"Abaqus mode {pair.abaqus_mode} ({pair.abaqus_frequency_hz:.3f} Hz) ↔ "
            f"experimental mode {pair.experimental_mode} ({pair.experimental_frequency_hz:.3f} Hz) | "
            f"error {pair.frequency_error_percent:.2f}% | MAC {mac} | {pair.status}"))

    def _image(self, label: ttk.Label, path: Path, key: str) -> None:
        try:
            with Image.open(path) as source:
                image = source.copy()
            image.thumbnail((560, 630), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            self.photos[key] = photo
            label.configure(image=photo, text="")
        except Exception as error:
            label.configure(image="", text=f"Could not display image:\n{error}")

    def _excel(self) -> None:
        if self.result is None or self.cache is None:
            return
        destination = filedialog.asksaveasfilename(title="Save Excel report", defaultextension=".xlsx",
            initialfile="modal_comparison_report.xlsx", filetypes=[("Excel workbook", "*.xlsx")])
        if destination:
            try:
                export_excel(self.result, Path(destination), self.cache / "report_images")
                messagebox.showinfo("Report saved", destination)
            except Exception as error:
                messagebox.showerror("Export failed", str(error))

    def _pdf(self) -> None:
        if self.result is None or self.cache is None:
            return
        destination = filedialog.asksaveasfilename(title="Save PDF report", defaultextension=".pdf",
            initialfile="modal_comparison_report.pdf", filetypes=[("PDF document", "*.pdf")])
        if destination:
            try:
                export_pdf(self.result, Path(destination), self.cache / "report_images")
                messagebox.showinfo("Report saved", destination)
            except Exception as error:
                messagebox.showerror("Export failed", str(error))

    def _open_workspace(self) -> None:
        workspace = Path(self.workspace_path.get()).resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(workspace))
        except Exception:
            messagebox.showinfo("Output folder", str(workspace))


def main() -> None:
    DEFAULT_WORKSPACE.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    ModalComparatorApp(root)
    root.mainloop()
