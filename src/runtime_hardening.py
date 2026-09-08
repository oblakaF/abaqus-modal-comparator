from __future__ import annotations

import hashlib
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from abaqus_bridge import AnalysisCancelled
from quality_control import _detect_rigid_modes
from universal_reader import load_universal_modal_file, resolve_testlab_file


_INSTALLED = False
_MATPLOTLIB_LOCK = threading.RLock()


def _parse_coordinate_scale(text: str) -> Optional[float]:
    value = text.strip().lower().replace(",", ".")
    if value in ("", "auto", "automatic"):
        return None
    scale = float(value)
    if scale <= 0.0:
        raise ValueError("Coordinate scale must be positive or 'auto'.")
    return scale


def install_runtime_hardening(app_module) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    application_class = app_module.ModalComparatorApp
    original_build_input = application_class._build_input
    original_populate = application_class._populate
    original_show_pair = application_class._show_pair

    def hardened_build_input(self) -> None:
        self.coordinate_scale_text = tk.StringVar(value="auto")
        original_build_input(self)
        frame = ttk.LabelFrame(
            self.input_tab,
            text="Geometry alignment override",
            padding=10,
        )
        frame.pack(fill="x", pady=(8, 0))
        ttk.Label(frame, text="Abaqus → experimental coordinate scale:").pack(
            side="left"
        )
        ttk.Entry(frame, textvariable=self.coordinate_scale_text, width=14).pack(
            side="left", padx=8
        )
        ttk.Label(
            frame,
            text=(
                "Use 'auto' normally. Enter 0.001 for mm→m or 1000 for m→mm "
                "when the measured grid does not cover the full specimen."
            ),
        ).pack(side="left")

    def hardened_validate(self):
        abaqus = Path(self.abaqus_path.get().strip())
        experiment = Path(self.experimental_path.get().strip())
        workspace_text = self.workspace_path.get().strip()
        workspace = Path(workspace_text) if workspace_text else app_module.DEFAULT_WORKSPACE
        try:
            start = int(self.start_mode.get())
            end = int(self.end_mode.get())
            scale_override = _parse_coordinate_scale(self.coordinate_scale_text.get())
        except (ValueError, tk.TclError) as error:
            messagebox.showwarning("Invalid analysis setting", str(error))
            return None

        if not abaqus.exists():
            messagebox.showwarning(
                "Missing Abaqus file",
                "Select an existing .odb or manifest.json file.",
            )
            return None
        if not experiment.exists():
            messagebox.showwarning(
                "Missing experimental file",
                "Select an existing .unv, .uff, or .lms file.",
            )
            return None
        if start < 1 or end < start:
            messagebox.showwarning(
                "Invalid mode range",
                "The final mode must be greater than or equal to the first mode.",
            )
            return None
        return (
            abaqus,
            experiment,
            workspace,
            start,
            end,
            self.abaqus_command.get().strip() or "abaqus",
            scale_override,
        )

    def hardened_worker(
        self,
        abaqus: Path,
        experiment: Path,
        workspace: Path,
        start: int,
        end: int,
        command: str,
        scale_override: Optional[float],
    ) -> None:
        failure = None
        result = None
        cache = None

        def check_cancelled() -> None:
            cancellation = getattr(self, "_analysis_cancel_event", None)
            if cancellation is not None and cancellation.is_set():
                raise AnalysisCancelled("Analysis stopped by user.")

        def stage(number: int, text: str) -> None:
            check_cancelled()
            callback = getattr(self, "_set_analysis_stage", None)
            if callable(callback):
                self.root.after(0, lambda: callback(number, text))

        def remember_process(process) -> None:
            self._owned_analysis_process = process

        try:
            workspace.mkdir(parents=True, exist_ok=True)
            signature = (
                f"{abaqus.resolve()}|{abaqus.stat().st_size}|{abaqus.stat().st_mtime_ns}|"
                f"{experiment.resolve()}|{experiment.stat().st_size}|{experiment.stat().st_mtime_ns}|"
                f"{start}|{end}|{scale_override}"
            )
            key = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:16]
            cache = workspace / f"analysis_{key}"
            cache.mkdir(parents=True, exist_ok=True)

            stage(1, "Abaqus extraction")
            abaqus_data = app_module.load_or_extract_odb(
                abaqus,
                cache / "abaqus",
                command,
                start,
                end,
                cancel_event=getattr(self, "_analysis_cancel_event", None),
                process_callback=remember_process,
            )
            check_cancelled()
            _, retained_modes, _, _ = _detect_rigid_modes(abaqus_data)
            target_frequencies = [mode.frequency_hz for mode in retained_modes]
            stage(2, "Experimental import")
            resolved_experiment = resolve_testlab_file(experiment)
            experiment_data = load_universal_modal_file(
                resolved_experiment,
                target_frequencies=target_frequencies,
                target_count=max(len(target_frequencies), 1),
            )
            stage(3, "Geometry alignment")
            result = app_module.compare_modal_datasets(
                abaqus_data,
                experiment_data,
                coordinate_scale_override=scale_override,
            )
            stage(4, "Modal comparison")
            check_cancelled()

            plot_dir = cache / "plots"
            stage(5, "Plot generation")
            with _MATPLOTLIB_LOCK:
                app_module.render_mac_matrix(result, plot_dir / "mac_matrix.png")
                check_cancelled()
                app_module.render_frequency_comparison(
                    result, plot_dir / "frequency_comparison.png"
                )
                check_cancelled()
                # Functions installed by ui_enhancements are imported lazily to avoid
                # a circular import during startup.
                from enhanced_reporting import (
                    render_frf_diagnostics,
                    render_verified_mac_matrix,
                )

                render_frf_diagnostics(result, plot_dir / "frf_diagnostics.png")
                check_cancelled()
                render_verified_mac_matrix(result, plot_dir / "verified_mac_matrix.png")
            stage(6, "Report data generation")
            self._write_summary(result, cache / "analysis_summary.json")
            if not result.pairs:
                app_module.write_no_pair_diagnostics(result, cache)
            check_cancelled()
        except AnalysisCancelled as error:
            failure = error
            try:
                workspace.mkdir(parents=True, exist_ok=True)
                (workspace / "last_cancellation.log").write_text(
                    "Analysis stopped by user. Partial files, if any, are diagnostic only.\n",
                    encoding="utf-8",
                )
            except Exception:
                pass
        except Exception as error:
            failure = error
            try:
                workspace.mkdir(parents=True, exist_ok=True)
                (workspace / "last_error.log").write_text(
                    traceback.format_exc(), encoding="utf-8"
                )
            except Exception:
                pass
        finally:
            self._owned_analysis_process = None
            if isinstance(failure, AnalysisCancelled):
                callback = getattr(self, "_cancelled", None)
                if callable(callback):
                    self.root.after(0, callback)
                else:
                    self.root.after(0, lambda: self._failed(failure))
            elif failure is None and result is not None and cache is not None:
                self.cache = cache
                self.root.after(0, lambda value=result: self._complete(value))
            else:
                self.root.after(
                    0,
                    lambda error=failure or RuntimeError("Unknown analysis failure"): self._failed(error),
                )

    def hardened_populate(self, result) -> None:
        original_populate(self, result)
        errors = [pair.frequency_error_percent for pair in result.pairs]
        absolute_errors = [abs(value) for value in errors]
        if not errors:
            self.metric_pairs.configure(text="Matched pairs: 0")
            self.metric_error.configure(text="Mean |frequency error|: —")
            self.metric_mac.configure(text="Mean MAC: —")
            return
        self.metric_error.configure(
            text=f"Mean |frequency error|: {sum(absolute_errors) / len(absolute_errors):.2f}%"
        )

    def hardened_show_pair(self, pair) -> None:
        if self.cache is None:
            return
        pair_directory = self.cache / "plots" / "mode_pairs"
        stem = f"abaqus_{pair.abaqus_mode}_experiment_{pair.experimental_mode}"
        expected = [
            pair_directory / f"{stem}_abaqus.png",
            pair_directory / f"{stem}_experimental.png",
            pair_directory / f"{stem}_overlay.png",
        ]
        if all(path.exists() for path in expected):
            for label, path, image_key in zip(
                self.shape_labels,
                expected,
                ("pair_a", "pair_e", "pair_o"),
            ):
                self._image(label, path, image_key)
            mac = "unavailable" if pair.mac is None else f"{pair.mac:.3f}"
            direction = (
                "Abaqus higher"
                if pair.frequency_error_percent > 0
                else "Abaqus lower"
                if pair.frequency_error_percent < 0
                else "equal"
            )
            self.pair_title.configure(
                text=(
                    f"Abaqus mode {pair.abaqus_mode} ({pair.abaqus_frequency_hz:.3f} Hz) ↔ "
                    f"experimental mode {pair.experimental_mode} ({pair.experimental_frequency_hz:.3f} Hz) | "
                    f"signed error {pair.frequency_error_percent:+.2f}% ({direction}) | "
                    f"MAC {mac} | {pair.status}"
                )
            )
            return
        with _MATPLOTLIB_LOCK:
            original_show_pair(self, pair)
        direction = (
            "Abaqus higher"
            if pair.frequency_error_percent > 0
            else "Abaqus lower"
            if pair.frequency_error_percent < 0
            else "equal"
        )
        mac = "unavailable" if pair.mac is None else f"{pair.mac:.3f}"
        self.pair_title.configure(
            text=(
                f"Abaqus mode {pair.abaqus_mode} ({pair.abaqus_frequency_hz:.3f} Hz) ↔ "
                f"experimental mode {pair.experimental_mode} ({pair.experimental_frequency_hz:.3f} Hz) | "
                f"signed error {pair.frequency_error_percent:+.2f}% ({direction}) | "
                f"MAC {mac} | {pair.status}"
            )
        )

    application_class._build_input = hardened_build_input
    application_class._validate = hardened_validate
    application_class._worker = hardened_worker
    application_class._populate = hardened_populate
    application_class._show_pair = hardened_show_pair
    _INSTALLED = True
