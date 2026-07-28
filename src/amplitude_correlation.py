from __future__ import annotations

from pathlib import Path
from typing import Dict

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

import reporting
import reporting_hardening
from modal_core import ModePairResult
from modal_scaling import correlation_plot_values


_INSTALLED = False
_UI_INSTALLED = False


def _new_figure(figsize) -> Figure:
    figure = Figure(figsize=figsize, constrained_layout=True)
    FigureCanvasAgg(figure)
    return figure


def render_amplitude_correlation(pair: ModePairResult, output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    abaqus, experiment, coefficient = correlation_plot_values(pair)

    figure = _new_figure((6.0, 4.6))
    axis = figure.add_subplot(111)
    axis.scatter(experiment, abaqus, s=25, alpha=0.75)
    limits = (-1.05, 1.05)
    axis.plot(limits, limits, linestyle="--", linewidth=1.1, label="45° agreement")
    axis.set_xlim(limits)
    axis.set_ylim(limits)
    axis.set_aspect("equal", adjustable="box")
    axis.set_xlabel("Experimental normalized modal amplitude")
    axis.set_ylabel("Abaqus fitted normalized modal amplitude")
    mac_text = "unavailable" if pair.mac is None else f"{pair.mac:.3f}"
    axis.set_title(
        f"Mode A{pair.abaqus_mode} / E{pair.experimental_mode} amplitude correlation\n"
        f"MAC={mac_text}; complex fit |c|={abs(coefficient):.3g}"
    )
    axis.grid(True, alpha=0.25)
    axis.legend(loc="best")
    figure.savefig(output_path, dpi=170)
    return output_path


def render_pair_images(pair: ModePairResult, output_directory: Path) -> Dict[str, Path]:
    output_directory = Path(output_directory)
    stem = f"abaqus_{pair.abaqus_mode}_experiment_{pair.experimental_mode}"
    return {
        "abaqus": reporting_hardening.render_mode_shape(
            pair.coordinates,
            pair.abaqus_vector,
            f"Abaqus mode {pair.abaqus_mode} — {pair.abaqus_frequency_hz:.3f} Hz",
            output_directory / f"{stem}_abaqus.png",
        ),
        "experimental": reporting_hardening.render_mode_shape(
            pair.coordinates,
            pair.experimental_vector,
            f"Experimental mode {pair.experimental_mode} — {pair.experimental_frequency_hz:.3f} Hz",
            output_directory / f"{stem}_experimental.png",
        ),
        "overlay": render_amplitude_correlation(
            pair,
            output_directory / f"{stem}_correlation.png",
        ),
    }


def install_amplitude_correlation() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    reporting.render_overlay = render_amplitude_correlation
    reporting.render_pair_images = render_pair_images
    _INSTALLED = True


def install_correlation_ui(app_module) -> None:
    global _UI_INSTALLED
    if _UI_INSTALLED:
        return
    application_class = app_module.ModalComparatorApp
    original_build_shapes = application_class._build_shapes

    def reviewed_build_shapes(self) -> None:
        original_build_shapes(self)
        if len(getattr(self, "shape_labels", [])) >= 3:
            self.shape_labels[2].master.configure(text="Amplitude correlation")

    application_class._build_shapes = reviewed_build_shapes
    _UI_INSTALLED = True
