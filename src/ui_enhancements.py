from __future__ import annotations

import hashlib
import traceback
from pathlib import Path
from tkinter import ttk
from typing import Any

from enhanced_reporting import (
    quality_control_text,
    render_frf_diagnostics,
    render_verified_mac_matrix,
)
from universal_reader import load_universal_modal_file, resolve_testlab_file


_INSTALLED = False


def _compact_value(value: Any) -> str:
    if isinstance(value, list):
        if len(value) > 20:
            return f"<list with {len(value)} items; exported to reports>"
        return str(value)
    if isinstance(value, dict):
        compact = {
            key: (f"<list with {len(item)} items>" if isinstance(item, list) and len(item) > 20 else item)
            for key, item in value.items()
        }
        return str(compact)
    return str(value)


def install_app_enhancements(app_module) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    application_class = app_module.ModalComparatorApp
    original_build = application_class._build
    original_populate = application_class._populate

    def enhanced_build(self) -> None:
        original_build(self)

        self.frf_tab = ttk.Frame(self.tabs, padding=12)
        self.tabs.insert(4, self.frf_tab, text="5. FRF & quality")
        self.tabs.tab(self.details_tab, text="6. Details")

        plots = ttk.Frame(self.frf_tab)
        plots.pack(fill="both", expand=True)
        frf_frame = ttk.LabelFrame(plots, text="FRF peaks and coherence", padding=5)
        verified_frame = ttk.LabelFrame(plots, text="Verified MAC matrix", padding=5)
        frf_frame.grid(row=0, column=0, sticky="nsew", padx=4)
        verified_frame.grid(row=0, column=1, sticky="nsew", padx=4)
        plots.columnconfigure(0, weight=1)
        plots.columnconfigure(1, weight=1)
        plots.rowconfigure(0, weight=1)

        self.frf_diagnostics_label = ttk.Label(
            frf_frame,
            text="Run the analysis to display the combined FRF indicator and coherence.",
            anchor="center",
        )
        self.verified_mac_label = ttk.Label(
            verified_frame,
            text="Run the analysis to display the verified-pair MAC matrix.",
            anchor="center",
        )
        self.frf_diagnostics_label.pack(fill="both", expand=True)
        self.verified_mac_label.pack(fill="both", expand=True)

        summary_frame = ttk.LabelFrame(
            self.frf_tab, text="Automatic quality-control decisions", padding=7
        )
        summary_frame.pack(fill="x", pady=(8, 0))
        self.quality_summary = ttk.Label(
            summary_frame,
            text="No analysis results yet.",
            justify="left",
            anchor="w",
            font=("Consolas", 9),
        )
        self.quality_summary.pack(fill="x")

    def enhanced_worker(
        self,
        abaqus: Path,
        experiment: Path,
        workspace: Path,
        start: int,
        end: int,
        command: str,
    ) -> None:
        try:
            workspace.mkdir(parents=True, exist_ok=True)
            signature = (
                f"{abaqus.resolve()}|{abaqus.stat().st_mtime_ns}|"
                f"{experiment.resolve()}|{experiment.stat().st_mtime_ns}|{start}|{end}"
            )
            key = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:12]
            cache = workspace / f"analysis_{key}"
            cache.mkdir(parents=True, exist_ok=True)

            abaqus_data = app_module.load_or_extract_odb(
                abaqus, cache / "abaqus", command, start, end
            )
            target_frequencies = [
                mode.frequency_hz
                for mode in abaqus_data.sorted_modes()
                if mode.frequency_hz >= 1.0
            ]
            resolved_experiment = resolve_testlab_file(experiment)
            experiment_data = load_universal_modal_file(
                resolved_experiment,
                target_frequencies=target_frequencies,
                target_count=max(len(target_frequencies), 12),
            )
            result = app_module.compare_modal_datasets(abaqus_data, experiment_data)

            plot_dir = cache / "plots"
            app_module.render_mac_matrix(result, plot_dir / "mac_matrix.png")
            app_module.render_frequency_comparison(
                result, plot_dir / "frequency_comparison.png"
            )
            render_frf_diagnostics(result, plot_dir / "frf_diagnostics.png")
            render_verified_mac_matrix(result, plot_dir / "verified_mac_matrix.png")
            self._write_summary(result, cache / "analysis_summary.json")
            self.cache = cache
            self.root.after(0, lambda: self._complete(result))
        except Exception as error:
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "last_error.log").write_text(
                traceback.format_exc(), encoding="utf-8"
            )
            self.root.after(0, lambda err=error: self._failed(err))

    def enhanced_populate(self, result) -> None:
        original_populate(self, result)

        self.table.tag_configure("excellent", background="#E6F4EA")
        self.table.tag_configure("good", background="#F0F7E8")
        self.table.tag_configure("review", background="#FFF4CE")
        self.table.tag_configure("poor", background="#FCE8E6")
        for item_id, pair in self.item_to_pair.items():
            status = pair.status.lower()
            if "excellent" in status:
                tag = "excellent"
            elif "good" in status:
                tag = "good"
            elif "review" in status:
                tag = "review"
            else:
                tag = "poor"
            self.table.item(item_id, tags=(tag,))

        if self.cache:
            self._image(
                self.frf_diagnostics_label,
                self.cache / "plots" / "frf_diagnostics.png",
                "frf_diagnostics",
            )
            self._image(
                self.verified_mac_label,
                self.cache / "plots" / "verified_mac_matrix.png",
                "verified_mac",
            )
        self.quality_summary.configure(text=quality_control_text(result))

    def enhanced_details(self, result) -> None:
        lines = [
            "ANALYSIS SUMMARY",
            "=" * 88,
            f"Abaqus source: {result.abaqus.source_path}",
            f"Experimental source: {result.experimental.source_path}",
            f"Reliable matched pairs: {len(result.pairs)}",
            f"Geometry match: {result.geometry.matched_fraction:.2%}",
            f"Coordinate scale: {result.geometry.coordinate_scale:.8g}",
            f"Geometry RMS / diagonal: {result.geometry.normalized_rms_distance:.3%}",
            f"Mean mapping distance: {result.geometry.distances.mean():.8g}",
            f"Maximum mapping distance: {result.geometry.distances.max():.8g}",
            "",
            quality_control_text(result),
            "",
        ]

        if result.warnings:
            lines.extend(["WARNINGS", "-" * 88])
            lines.extend("• " + warning for warning in result.warnings)
            lines.append("")

        if not result.pairs:
            lines.extend(app_module._no_pair_detail_lines(result))

        lines.extend(["MATCHED MODES", "-" * 88])
        for pair in result.pairs:
            mac = "—" if pair.mac is None else f"{pair.mac:.4f}"
            lines.append(
                f"A{pair.abaqus_mode:>3} {pair.abaqus_frequency_hz:>11.5f} Hz  ↔  "
                f"E{pair.experimental_mode:>3} {pair.experimental_frequency_hz:>11.5f} Hz  |  "
                f"error {pair.frequency_error_percent:>6.2f}%  |  MAC {mac}  |  {pair.status}"
            )

        lines.extend(["", "SIMCENTER PEAK CANDIDATES", "-" * 88])
        for mode in result.experimental.sorted_modes():
            damping = "—" if mode.damping_ratio is None else f"{mode.damping_ratio:.6g}"
            if mode.metadata.get("dataset_type") == 58:
                # Legacy FRF-derived modes (saved before coherence_status existed)
                # are normalized to "unavailable" rather than trusting whatever
                # mean_coherence value they happened to have stored.
                coherence_status = str(mode.metadata.get("coherence_status") or "unavailable")
                coherence_value = mode.metadata.get("mean_coherence")
                if coherence_status == "computed" and isinstance(coherence_value, float):
                    coherence = f"{coherence_value:.4f}"
                else:
                    coherence = f"not measured ({coherence_status})"
            else:
                coherence = "—"
            lines.append(
                f"E{mode.number:>3}: {mode.frequency_hz:>11.5f} Hz | "
                f"damping {damping} | mean coherence {coherence} | points {len(mode.node_ids)}"
            )

        lines.extend(["", "ABAQUS METADATA", "-" * 88])
        for key, value in sorted(result.abaqus.metadata.items()):
            if key in ("modes", "history") or key.startswith("_"):
                continue
            lines.append(f"{key}: {_compact_value(value)}")

        lines.extend(["", "SIMCENTER METADATA", "-" * 88])
        for key, value in sorted(result.experimental.metadata.items()):
            if key.startswith("_"):
                continue
            lines.append(f"{key}: {_compact_value(value)}")

        lines.extend(["", "ABAQUS MODAL HISTORY OUTPUTS", "-" * 88])
        if result.abaqus.history:
            lines.extend(
                f"{item.get('region')} | {item.get('name')} | values={len(item.get('data', []))}"
                for item in result.abaqus.history
            )
        else:
            lines.append("No modal history outputs were found in the selected ODB step.")

        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", "\n".join(lines))
        self.details.configure(state="disabled")

    application_class._build = enhanced_build
    application_class._worker = enhanced_worker
    application_class._populate = enhanced_populate
    application_class._details = enhanced_details
    _INSTALLED = True
