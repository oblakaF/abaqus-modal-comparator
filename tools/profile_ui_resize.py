from __future__ import annotations

import json
import sys
import tempfile
import time
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from matplotlib.backend_bases import FigureCanvasBase
from matplotlib.figure import Figure


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import main
import ui_workflow


def profile_resize(
    *, cycles: int = 1, step_delay: float = 0.11, cycle_tabs: bool = False
) -> dict:
    metrics = {
        "raw_configure_callbacks": 0,
        "layout_schedules": 0,
        "layout_cancellations": 0,
        "responsive_policy_executions": 0,
        "responsive_policy_seconds": 0.0,
        "mode_transitions": 0,
        "image_schedules": 0,
        "image_cancellations": 0,
        "image_renders": 0,
        "image_render_seconds": 0.0,
        "notebook_tab_updates": 0,
        "treeview_inserts": 0,
        "treeview_deletes": 0,
        "scientific_callbacks": 0,
        "figure_recreations": 0,
        "matplotlib_draws": 0,
        "event_loop_update_seconds": 0.0,
        "event_loop_update_max_seconds": 0.0,
    }
    root = tk.Tk()
    disabled = {
        "autosave_enabled": False,
        "restore_on_startup": False,
        "show_recovery_notice": False,
        "ui_scale_percent": 100,
    }
    with patch.object(ui_workflow, "load_recovery_preferences", return_value=disabled), patch.object(
        ui_workflow, "discover_abaqus_installations", return_value=()
    ):
        application = main.app.ModalComparatorApp(root)

    original_figure_init = Figure.__init__
    original_canvas_draw = FigureCanvasBase.draw
    original_compare = main.app.compare_modal_datasets

    def figure_init(figure, *args, **kwargs):
        metrics["figure_recreations"] += 1
        return original_figure_init(figure, *args, **kwargs)

    def canvas_draw(canvas, *args, **kwargs):
        metrics["matplotlib_draws"] += 1
        return original_canvas_draw(canvas, *args, **kwargs)

    def compare(*args, **kwargs):
        metrics["scientific_callbacks"] += 1
        return original_compare(*args, **kwargs)

    Figure.__init__ = figure_init
    FigureCanvasBase.draw = canvas_draw
    main.app.compare_modal_datasets = compare

    root.bind(
        "<Configure>",
        lambda event: metrics.__setitem__(
            "raw_configure_callbacks",
            metrics["raw_configure_callbacks"] + int(event.widget is root),
        ),
        add="+",
    )

    original_schedule = application._schedule_responsive_layout
    original_apply = application._apply_responsive_layout
    original_image_schedule = application._schedule_responsive_image
    original_image_render = application._render_responsive_image

    def schedule(event=None):
        metrics["layout_schedules"] += 1
        metrics["layout_cancellations"] += int(application._responsive_job is not None)
        return original_schedule(event)

    def apply():
        before_mode = application._layout_mode
        started = time.perf_counter()
        try:
            return original_apply()
        finally:
            metrics["responsive_policy_executions"] += 1
            metrics["responsive_policy_seconds"] += time.perf_counter() - started
            metrics["mode_transitions"] += int(before_mode != application._layout_mode)

    def image_schedule(label, *, immediate=False):
        metrics["image_schedules"] += 1
        metrics["image_cancellations"] += int(
            application._responsive_resize_job is not None
        )
        return original_image_schedule(label, immediate=immediate)

    def image_render(label):
        started = time.perf_counter()
        try:
            return original_image_render(label)
        finally:
            metrics["image_renders"] += 1
            metrics["image_render_seconds"] += time.perf_counter() - started

    application._schedule_responsive_layout = schedule
    application._apply_responsive_layout = apply
    application._schedule_responsive_image = image_schedule
    application._render_responsive_image = image_render
    if application._resize_settler is not None:
        application._resize_settler.callback = apply

    original_tab = application.tabs.tab

    def tab(*args, **kwargs):
        if "text" in kwargs:
            metrics["notebook_tab_updates"] += 1
        return original_tab(*args, **kwargs)

    application.tabs.tab = tab

    treeviews = [widget for widget in ui_workflow._walk(root) if isinstance(widget, ttk.Treeview)]
    for tree in treeviews:
        original_insert = tree.insert
        original_delete = tree.delete

        def insert(*args, _original=original_insert, **kwargs):
            metrics["treeview_inserts"] += 1
            return _original(*args, **kwargs)

        def delete(*args, _original=original_delete, **kwargs):
            metrics["treeview_deletes"] += len(args)
            return _original(*args, **kwargs)

        tree.insert = insert
        tree.delete = delete

    with tempfile.TemporaryDirectory(prefix="hud_resize_profile_") as directory:
        image_path = Path(directory) / "synthetic_plot.png"
        Image.new("RGB", (2200, 1400), "#46627f").save(image_path)
        labels = [
            getattr(application, name, None)
            for name in (
                "mac_label",
                "frequency_label",
                "frf_diagnostics_label",
                "verified_mac_label",
                "abaqus_automac_label",
                "experimental_automac_label",
                "comac_label",
                "cmif_label",
            )
        ] + list(getattr(application, "shape_labels", ()))
        for index, label in enumerate(item for item in labels if item is not None):
            application._image(label, image_path, f"profile_{index}")

        size_results = {}
        application.coordinate_mapping_mode.set("camera_grid")
        application._sync_coordinate_mapping()
        for target_width, target_height in (
            (1920, 1080),
            (1600, 900),
            (1366, 768),
            (1280, 720),
            (1024, 700),
        ):
            root.geometry(f"{target_width}x{target_height}")
            root.update()
            application._apply_responsive_layout()
            root.update_idletasks()
            application.tabs.select(application.input_tab)
            root.update_idletasks()
            canvas_width = application._input_canvas.winfo_width()
            content_requested_width = application._input_content.winfo_reqwidth()
            tabs_usable = True
            try:
                for tab_id in application.tabs.tabs():
                    application.tabs.select(tab_id)
                    root.update_idletasks()
            except tk.TclError:
                tabs_usable = False
            size_results[f"{target_width}x{target_height}"] = {
                "layout_mode": application._layout_mode.value,
                "input_canvas_width": canvas_width,
                "input_content_requested_width": content_requested_width,
                "horizontal_fit": content_requested_width <= canvas_width,
                "all_required_controls_managed": all(
                    bool(widget.winfo_manager())
                    for widget, _state in application._analysis_configuration_controls.values()
                ),
                "run_managed": bool(application.run_button.winfo_manager()),
                "stop_managed": bool(application.stop_button.winfo_manager()),
                "notebook_tabs": len(application.tabs.tabs()),
                "tabs_usable": tabs_usable,
            }
        metrics["target_sizes"] = size_results
        application.tabs.select(application.plot_tab)
        root.geometry("1600x900")
        root.update()
        time.sleep(0.25)
        root.update()
        retained_targets = metrics["target_sizes"]
        metrics.update({key: 0 if isinstance(value, int) else 0.0 for key, value in metrics.items() if key != "target_sizes"})
        metrics["target_sizes"] = retained_targets
        settled_scheduled_before = application._resize_settler.scheduled_count
        settled_cancelled_before = application._resize_settler.cancelled_count

        widths = list(range(1600, 1023, -24)) + list(range(1024, 1601, 24))
        started = time.perf_counter()
        stress_tabs = (
            application.input_tab,
            application.plot_tab,
            application.frf_tab,
            application.cmif_tab,
            application.shape_tab,
            application.manual_review_tab,
        )
        update_count = 0
        for cycle in range(cycles):
            if cycle_tabs:
                application.tabs.select(stress_tabs[cycle % len(stress_tabs)])
                root.update()
                time.sleep(0.25)
                root.update()
            for width in widths:
                height = round(700 + (width - 1024) * 200 / 576)
                root.geometry(f"{width}x{height}")
                update_started = time.perf_counter()
                root.update()
                update_seconds = time.perf_counter() - update_started
                metrics["event_loop_update_seconds"] += update_seconds
                metrics["event_loop_update_max_seconds"] = max(
                    metrics["event_loop_update_max_seconds"], update_seconds
                )
                update_count += 1
                time.sleep(step_delay)
                update_started = time.perf_counter()
                root.update()
                update_seconds = time.perf_counter() - update_started
                metrics["event_loop_update_seconds"] += update_seconds
                metrics["event_loop_update_max_seconds"] = max(
                    metrics["event_loop_update_max_seconds"], update_seconds
                )
                update_count += 1
        if cycle_tabs:
            for _ in range(2):
                root.state("zoomed")
                root.update()
                time.sleep(0.25)
                root.state("normal")
                root.update()
                time.sleep(0.25)
        time.sleep(0.3)
        root.update()
        metrics["scenario_wall_seconds"] = time.perf_counter() - started
        metrics["event_loop_update_mean_seconds"] = (
            metrics["event_loop_update_seconds"] / max(1, update_count)
        )

    metrics["layout_schedules"] = application._resize_settler.scheduled_count - settled_scheduled_before
    metrics["layout_cancellations"] = application._resize_settler.cancelled_count - settled_cancelled_before

    metrics["pending_layout_jobs"] = int(application._responsive_job is not None)
    metrics["pending_image_jobs"] = int(application._responsive_resize_job is not None)
    Figure.__init__ = original_figure_init
    FigureCanvasBase.draw = original_canvas_draw
    main.app.compare_modal_datasets = original_compare
    root.destroy()
    return metrics


if __name__ == "__main__":
    stress = "--stress" in sys.argv[1:]
    cycles = 6 if stress else int(sys.argv[1]) if len(sys.argv) > 1 else 1
    print(
        json.dumps(
            profile_resize(
                cycles=cycles,
                step_delay=0.02 if stress else 0.11,
                cycle_tabs=stress,
            ),
            indent=2,
        )
    )
