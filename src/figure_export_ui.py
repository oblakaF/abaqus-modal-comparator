from __future__ import annotations

import csv
import json
import os
import shutil
from pathlib import Path
from typing import Dict, Iterable, Optional

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageDraw, ImageFont, ImageTk

from advanced_metrics import (
    advanced_metric_summary,
    render_abaqus_automac,
    render_comac_map,
    render_experimental_automac,
)
from enhanced_reporting import quality_control_text


_INSTALLED = False


class FullSizeImageViewer(tk.Toplevel):
    def __init__(self, parent: tk.Misc, image_path: Path, title: str) -> None:
        super().__init__(parent)
        self.image_path = Path(image_path)
        self.title(title)
        self.geometry("1200x820")
        self.minsize(700, 500)

        with Image.open(self.image_path) as source:
            self.original = source.convert("RGBA")
        self.zoom = 1.0
        self.photo: Optional[ImageTk.PhotoImage] = None

        toolbar = ttk.Frame(self, padding=6)
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Fit", command=self.fit).pack(side="left")
        ttk.Button(toolbar, text="100%", command=self.actual_size).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Zoom in", command=lambda: self.change_zoom(1.25)).pack(side="left")
        ttk.Button(toolbar, text="Zoom out", command=lambda: self.change_zoom(0.8)).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Save as PNG…", command=self.save_as).pack(side="left", padx=(14, 4))
        ttk.Button(toolbar, text="Open folder", command=self.open_folder).pack(side="left")
        self.zoom_label = ttk.Label(toolbar, text="100%")
        self.zoom_label.pack(side="right")

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, background="#202020", highlightthickness=0)
        horizontal = ttk.Scrollbar(body, orient="horizontal", command=self.canvas.xview)
        vertical = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=horizontal.set, yscrollcommand=vertical.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        self.canvas.bind("<Control-MouseWheel>", self._mouse_zoom)
        self.after_idle(self.fit)

    def _mouse_zoom(self, event) -> None:
        self.change_zoom(1.15 if event.delta > 0 else 1.0 / 1.15)

    def change_zoom(self, factor: float) -> None:
        self.zoom = min(8.0, max(0.05, self.zoom * factor))
        self.redraw()

    def actual_size(self) -> None:
        self.zoom = 1.0
        self.redraw()

    def fit(self) -> None:
        self.update_idletasks()
        available_width = max(self.canvas.winfo_width() - 30, 200)
        available_height = max(self.canvas.winfo_height() - 30, 200)
        self.zoom = min(
            available_width / self.original.width,
            available_height / self.original.height,
            1.0,
        )
        self.redraw()

    def redraw(self) -> None:
        width = max(1, int(round(self.original.width * self.zoom)))
        height = max(1, int(round(self.original.height * self.zoom)))
        resized = self.original.resize((width, height), Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(resized)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        self.canvas.configure(scrollregion=(0, 0, width, height))
        self.zoom_label.configure(text=f"{self.zoom * 100:.0f}%")

    def save_as(self) -> None:
        destination = filedialog.asksaveasfilename(
            parent=self,
            title="Save image",
            defaultextension=".png",
            initialfile=self.image_path.name,
            filetypes=[("PNG image", "*.png")],
        )
        if destination:
            shutil.copy2(self.image_path, destination)

    def open_folder(self) -> None:
        try:
            os.startfile(str(self.image_path.parent))
        except Exception:
            messagebox.showinfo("Image folder", str(self.image_path.parent), parent=self)


def _safe_copy(source: Path, destination: Path) -> Path:
    source = Path(source)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)
    return destination


def _write_table_csv(application, destination: Path) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    headings = [application.table.heading(column, "text") for column in application.table["columns"]]
    with destination.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(headings)
        for item in application.table.get_children():
            writer.writerow(application.table.item(item, "values"))
    return destination


def _write_table_png(application, destination: Path) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    columns = list(application.table["columns"])
    headings = [application.table.heading(column, "text") for column in columns]
    rows = [list(application.table.item(item, "values")) for item in application.table.get_children()]

    font = ImageFont.load_default()
    padding_x = 12
    padding_y = 9
    line_height = 18 + 2 * padding_y
    all_rows = [headings] + rows
    widths = []
    for column_index in range(len(columns)):
        text_width = max(
            ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox(
                (0, 0), str(row[column_index]), font=font
            )[2]
            for row in all_rows
        )
        widths.append(max(90, text_width + 2 * padding_x))

    image = Image.new("RGB", (sum(widths) + 1, line_height * len(all_rows) + 1), "white")
    draw = ImageDraw.Draw(image)
    y = 0
    for row_index, row in enumerate(all_rows):
        x = 0
        fill = "#D9EAF7" if row_index == 0 else ("#F7FBFD" if row_index % 2 == 0 else "white")
        for column_index, value in enumerate(row):
            width = widths[column_index]
            draw.rectangle((x, y, x + width, y + line_height), fill=fill, outline="#808080")
            draw.text((x + padding_x, y + padding_y), str(value), fill="black", font=font)
            x += width
        y += line_height
    image.save(destination, dpi=(180, 180))
    return destination


def _metadata_payload(result) -> Dict[str, object]:
    return {
        "abaqus_source": str(result.abaqus.source_path),
        "experimental_source": str(result.experimental.source_path),
        "abaqus_metadata": result.abaqus.metadata,
        "experimental_metadata": result.experimental.metadata,
        "warnings": result.warnings,
        "matched_pairs": [
            {
                "abaqus_mode": pair.abaqus_mode,
                "experimental_mode": pair.experimental_mode,
                "abaqus_frequency_hz": pair.abaqus_frequency_hz,
                "experimental_frequency_hz": pair.experimental_frequency_hz,
                "frequency_error_percent": pair.frequency_error_percent,
                "mac": pair.mac,
                "status": pair.status,
            }
            for pair in result.pairs
        ],
    }


def install_figure_export_ui(app_module) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    application_class = app_module.ModalComparatorApp
    original_build = application_class._build
    original_populate = application_class._populate
    original_show_pair = application_class._show_pair
    original_image = application_class._image

    def plot_path(self, filename: str) -> Optional[Path]:
        if self.cache is None:
            return None
        path = self.cache / "plots" / filename
        return path if path.exists() else None

    def require_result(self) -> bool:
        if self.result is None or self.cache is None:
            messagebox.showwarning("No analysis", "Run the analysis first.")
            return False
        return True

    def open_image(self, path: Optional[Path], title: str) -> None:
        if path is None or not Path(path).exists():
            messagebox.showwarning("Image unavailable", "The requested image has not been generated yet.")
            return
        FullSizeImageViewer(self.root, Path(path), title)

    def save_image(self, path: Optional[Path], initial_name: str) -> None:
        if path is None or not Path(path).exists():
            messagebox.showwarning("Image unavailable", "The requested image has not been generated yet.")
            return
        destination = filedialog.asksaveasfilename(
            title="Save image",
            defaultextension=".png",
            initialfile=initial_name,
            filetypes=[("PNG image", "*.png")],
        )
        if destination:
            _safe_copy(Path(path), Path(destination))

    def save_paths_to_folder(self, paths: Dict[str, Path], title: str) -> None:
        folder = filedialog.askdirectory(title=title)
        if not folder:
            return
        destination = Path(folder)
        saved = 0
        for name, path in paths.items():
            if path and Path(path).exists():
                _safe_copy(Path(path), destination / name)
                saved += 1
        messagebox.showinfo("Images saved", f"Saved {saved} file(s) to:\n{destination}")

    def selected_pair_paths(self) -> Dict[str, Path]:
        return dict(getattr(self, "current_pair_paths", {}))

    def save_selected_pair(self) -> None:
        if not require_result(self):
            return
        paths = selected_pair_paths(self)
        if not paths:
            messagebox.showwarning("No selected pair", "Select a matched mode pair first.")
            return
        pair = getattr(self, "current_pair", None)
        prefix = "selected_pair" if pair is None else f"A{pair.abaqus_mode}_E{pair.experimental_mode}"
        save_paths_to_folder(
            self,
            {
                f"{prefix}_abaqus.png": paths["abaqus"],
                f"{prefix}_experimental.png": paths["experimental"],
                f"{prefix}_amplitude_correlation.png": paths["overlay"],
            },
            "Save selected mode-pair images",
        )

    def save_all_pairs(self, destination: Optional[Path] = None) -> None:
        if not require_result(self):
            return
        if destination is None:
            folder = filedialog.askdirectory(title="Save all matched mode-pair images")
            if not folder:
                return
            destination = Path(folder)
        mode_directory = destination / "mode_pairs"
        mode_directory.mkdir(parents=True, exist_ok=True)
        for pair in self.result.pairs:
            pair_directory = mode_directory / f"A{pair.abaqus_mode}_E{pair.experimental_mode}"
            paths = app_module.render_pair_images(pair, pair_directory)
            for key, path in paths.items():
                suffix = "amplitude_correlation" if key == "overlay" else key
                _safe_copy(path, pair_directory / f"A{pair.abaqus_mode}_E{pair.experimental_mode}_{suffix}.png")

    def save_table_csv(self) -> None:
        if not require_result(self):
            return
        destination = filedialog.asksaveasfilename(
            title="Save comparison table as CSV",
            defaultextension=".csv",
            initialfile="modal_comparison_table.csv",
            filetypes=[("CSV file", "*.csv")],
        )
        if destination:
            _write_table_csv(self, Path(destination))

    def save_table_png(self) -> None:
        if not require_result(self):
            return
        destination = filedialog.asksaveasfilename(
            title="Save comparison table as PNG",
            defaultextension=".png",
            initialfile="modal_comparison_table.png",
            filetypes=[("PNG image", "*.png")],
        )
        if destination:
            _write_table_png(self, Path(destination))

    def advanced_current(self) -> tuple[Optional[Path], str, str]:
        index = self.advanced_notebook.index(self.advanced_notebook.select())
        options = (
            (plot_path(self, "abaqus_automac.png"), "Abaqus AutoMAC", "abaqus_automac.png"),
            (plot_path(self, "experimental_automac.png"), "Experimental AutoMAC", "experimental_automac.png"),
            (plot_path(self, "comac_map.png"), "COMAC map", "comac_map.png"),
        )
        return options[index]

    def save_advanced_bundle(self) -> None:
        if not require_result(self):
            return
        folder = filedialog.askdirectory(title="Save AutoMAC and COMAC figures")
        if not folder:
            return
        destination = Path(folder)
        paths = {
            "abaqus_automac.png": plot_path(self, "abaqus_automac.png"),
            "experimental_automac.png": plot_path(self, "experimental_automac.png"),
            "comac_map.png": plot_path(self, "comac_map.png"),
        }
        for name, path in paths.items():
            if path:
                _safe_copy(path, destination / name)
        values = advanced_metric_summary(self.result)
        (destination / "automac_comac_summary.txt").write_text(
            "\n".join(f"{key}: {value:.6g}" for key, value in values.items()),
            encoding="utf-8",
        )
        messagebox.showinfo("Figures saved", str(destination))

    def save_frf_bundle(self) -> None:
        if not require_result(self):
            return
        folder = filedialog.askdirectory(title="Save FRF and quality figures")
        if not folder:
            return
        destination = Path(folder)
        for filename in ("frf_diagnostics.png", "verified_mac_matrix.png"):
            path = plot_path(self, filename)
            if path:
                _safe_copy(path, destination / filename)
        (destination / "quality_control_summary.txt").write_text(
            quality_control_text(self.result), encoding="utf-8"
        )
        messagebox.showinfo("FRF bundle saved", str(destination))

    def save_plot_bundle(self) -> None:
        if not require_result(self):
            return
        paths = {
            "mac_matrix.png": plot_path(self, "mac_matrix.png"),
            "frequency_regression.png": plot_path(self, "frequency_comparison.png"),
        }
        save_paths_to_folder(self, paths, "Save MAC and frequency figures")

    def save_details_txt(self) -> None:
        if not require_result(self):
            return
        destination = filedialog.asksaveasfilename(
            title="Save details",
            defaultextension=".txt",
            initialfile="modal_analysis_details.txt",
            filetypes=[("Text file", "*.txt")],
        )
        if destination:
            Path(destination).write_text(self.details.get("1.0", "end-1c"), encoding="utf-8")

    def save_metadata_json(self) -> None:
        if not require_result(self):
            return
        destination = filedialog.asksaveasfilename(
            title="Save metadata",
            defaultextension=".json",
            initialfile="modal_analysis_metadata.json",
            filetypes=[("JSON file", "*.json")],
        )
        if destination:
            Path(destination).write_text(
                json.dumps(_metadata_payload(self.result), indent=2, default=str),
                encoding="utf-8",
            )

    def export_all_figures(self) -> None:
        if not require_result(self):
            return
        folder = filedialog.askdirectory(title="Export all figures and analysis data")
        if not folder:
            return
        destination = Path(folder)
        destination.mkdir(parents=True, exist_ok=True)

        fixed_files = {
            "mac_matrix.png": "mac_matrix.png",
            "frequency_comparison.png": "frequency_regression.png",
            "frf_diagnostics.png": "frf_diagnostics.png",
            "verified_mac_matrix.png": "verified_mac_matrix.png",
            "abaqus_automac.png": "abaqus_automac.png",
            "experimental_automac.png": "experimental_automac.png",
            "comac_map.png": "comac_map.png",
        }
        for source_name, destination_name in fixed_files.items():
            path = plot_path(self, source_name)
            if path:
                _safe_copy(path, destination / destination_name)

        _write_table_csv(self, destination / "modal_comparison_table.csv")
        _write_table_png(self, destination / "modal_comparison_table.png")
        (destination / "quality_control_summary.txt").write_text(
            quality_control_text(self.result), encoding="utf-8"
        )
        (destination / "details.txt").write_text(
            self.details.get("1.0", "end-1c"), encoding="utf-8"
        )
        (destination / "metadata.json").write_text(
            json.dumps(_metadata_payload(self.result), indent=2, default=str),
            encoding="utf-8",
        )
        save_all_pairs(self, destination)
        messagebox.showinfo("Export complete", f"All figures were saved to:\n{destination}")

    def build_action_bar(parent, buttons: Iterable[tuple[str, object]]) -> ttk.Frame:
        frame = ttk.Frame(parent)
        frame.pack(side="bottom", fill="x", pady=(8, 0))
        for text, command in buttons:
            ttk.Button(frame, text=text, command=command).pack(side="left", padx=(0, 7))
        return frame

    def enhanced_build(self) -> None:
        original_build(self)
        self.displayed_image_paths: Dict[str, Path] = {}
        self.current_pair_paths: Dict[str, Path] = {}
        self.current_pair = None

        build_action_bar(
            self.table_tab,
            (
                ("Save table CSV", self.save_table_csv),
                ("Save table PNG", self.save_table_png),
                ("Export all figures", self.export_all_figures),
            ),
        )
        build_action_bar(
            self.shape_tab,
            (
                ("Open Abaqus full size", lambda: self.open_image(self.current_pair_paths.get("abaqus"), "Abaqus mode shape")),
                ("Open experiment full size", lambda: self.open_image(self.current_pair_paths.get("experimental"), "Experimental mode shape")),
                ("Open correlation full size", lambda: self.open_image(self.current_pair_paths.get("overlay"), "Amplitude correlation")),
                ("Save selected pair", self.save_selected_pair),
                ("Save all pairs", self.save_all_pairs),
            ),
        )
        build_action_bar(
            self.plot_tab,
            (
                ("Open MAC full size", lambda: self.open_image(self.plot_path("mac_matrix.png"), "MAC matrix")),
                ("Open regression full size", lambda: self.open_image(self.plot_path("frequency_comparison.png"), "Frequency regression")),
                ("Save tab figures", self.save_plot_bundle),
            ),
        )
        if hasattr(self, "frf_tab"):
            build_action_bar(
                self.frf_tab,
                (
                    ("Open FRF full size", lambda: self.open_image(self.plot_path("frf_diagnostics.png"), "FRF diagnostics")),
                    ("Open verified MAC full size", lambda: self.open_image(self.plot_path("verified_mac_matrix.png"), "Verified MAC matrix")),
                    ("Save tab bundle", self.save_frf_bundle),
                ),
            )
        if hasattr(self, "advanced_tab"):
            build_action_bar(
                self.advanced_tab,
                (
                    ("Open current full size", lambda: self.open_image(*self.advanced_current()[:2])),
                    ("Save current PNG", lambda: self.save_image(self.advanced_current()[0], self.advanced_current()[2])),
                    ("Save all three", self.save_advanced_bundle),
                ),
            )
        build_action_bar(
            self.details_tab,
            (
                ("Save details TXT", self.save_details_txt),
                ("Save metadata JSON", self.save_metadata_json),
            ),
        )

    def enhanced_populate(self, result) -> None:
        original_populate(self, result)
        if hasattr(self, "export_all_button"):
            self.export_all_button.configure(state="normal")

    def enhanced_show_pair(self, pair) -> None:
        original_show_pair(self, pair)
        if self.cache is None:
            return
        self.current_pair = pair
        self.current_pair_paths = app_module.render_pair_images(
            pair,
            self.cache / "plots" / "mode_pairs",
        )

    def dynamic_image(self, label: ttk.Label, path: Path, key: str) -> None:
        try:
            path = Path(path)
            self.root.update_idletasks()
            available_width = label.winfo_width()
            available_height = label.winfo_height()
            if available_width < 100:
                available_width = min(1150, max(700, self.root.winfo_width() - 120))
            if available_height < 100:
                available_height = min(720, max(420, self.root.winfo_height() - 280))
            with Image.open(path) as source:
                image = source.convert("RGBA")
            image.thumbnail(
                (max(240, available_width - 12), max(220, available_height - 12)),
                Image.Resampling.LANCZOS,
            )
            photo = ImageTk.PhotoImage(image)
            self.photos[key] = photo
            self.displayed_image_paths[key] = path
            label.configure(image=photo, text="")
        except Exception:
            original_image(self, label, path, key)

    application_class.plot_path = plot_path
    application_class.open_image = open_image
    application_class.save_image = save_image
    application_class.save_selected_pair = save_selected_pair
    application_class.save_all_pairs = save_all_pairs
    application_class.save_table_csv = save_table_csv
    application_class.save_table_png = save_table_png
    application_class.advanced_current = advanced_current
    application_class.save_advanced_bundle = save_advanced_bundle
    application_class.save_frf_bundle = save_frf_bundle
    application_class.save_plot_bundle = save_plot_bundle
    application_class.save_details_txt = save_details_txt
    application_class.save_metadata_json = save_metadata_json
    application_class.export_all_figures = export_all_figures
    application_class._build = enhanced_build
    application_class._populate = enhanced_populate
    application_class._show_pair = enhanced_show_pair
    application_class._image = dynamic_image
    _INSTALLED = True
