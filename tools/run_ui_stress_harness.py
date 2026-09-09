from __future__ import annotations

import sys
import tempfile
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import main
import ui_workflow


def main_harness() -> None:
    root = tk.Tk()
    preferences = {
        "autosave_enabled": False,
        "restore_on_startup": False,
        "show_recovery_notice": False,
        "ui_scale_percent": 100,
    }
    with patch.object(ui_workflow, "load_recovery_preferences", return_value=preferences), patch.object(
        ui_workflow, "discover_abaqus_installations", return_value=()
    ):
        application = main.app.ModalComparatorApp(root)
    root.title("Modal Comparator UI Stress Harness")
    root.geometry("1600x900")

    with tempfile.TemporaryDirectory(prefix="hud_stress_") as directory:
        path = Path(directory) / "stress_plot.png"
        image = Image.new("RGB", (2200, 1400), "#e9eef3")
        draw = ImageDraw.Draw(image)
        for x in range(0, 2200, 100):
            draw.line((x, 0, x, 1400), fill="#8ca4b8", width=2)
        for y in range(0, 1400, 100):
            draw.line((0, y, 2200, y), fill="#8ca4b8", width=2)
        draw.text((70, 60), "RESIZE STRESS IMAGE - GRID MUST REMAIN STABLE", fill="#17212b")
        image.save(path)

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
            application._image(label, path, f"stress_{index}")

        application.status.set(
            "UI stress harness: presentation-only synthetic plots; no analysis is running."
        )
        application.tabs.select(application.input_tab)
        root.mainloop()


if __name__ == "__main__":
    main_harness()
