from __future__ import annotations

from pathlib import Path

from cmif_validation_ui import _source_and_confidence
from plot_cache_version import ensure_pair_render_cache


_INSTALLED = False


def _expected_paths(directory: Path, pair):
    stem = f"abaqus_{pair.abaqus_mode}_experiment_{pair.experimental_mode}"
    return {
        "abaqus": directory / f"{stem}_abaqus.png",
        "experimental": directory / f"{stem}_experimental.png",
        "overlay": directory / f"{stem}_correlation.png",
    }


def _display_paths(application, paths) -> None:
    if len(getattr(application, "shape_labels", [])) < 3:
        return
    for label, key, image_key in zip(
        application.shape_labels,
        ("abaqus", "experimental", "overlay"),
        ("pair_a_current", "pair_e_current", "pair_correlation_current"),
    ):
        path = paths.get(key)
        if path is not None and Path(path).exists():
            application._image(label, Path(path), image_key)


def _set_pair_title(application, pair) -> None:
    mac = "unavailable" if pair.mac is None else f"{pair.mac:.3f}"
    direction = (
        "Abaqus higher"
        if pair.frequency_error_percent > 0
        else "Abaqus lower"
        if pair.frequency_error_percent < 0
        else "equal"
    )
    title = (
        f"Abaqus mode {pair.abaqus_mode} ({pair.abaqus_frequency_hz:.3f} Hz) ↔ "
        f"experimental mode {pair.experimental_mode} ({pair.experimental_frequency_hz:.3f} Hz) | "
        f"signed error {pair.frequency_error_percent:+.2f}% ({direction}) | "
        f"MAC {mac} | {pair.status}"
    )
    if application.result is not None:
        source, confidence = _source_and_confidence(
            application.result, pair.experimental_mode
        )
        title += f" | source: {source} | confidence: {confidence}"
    application.pair_title.configure(text=title)


def install_pair_plot_cache_ui(app_module) -> None:
    """Invalidate stale pair plots and reuse only the current rendering format."""
    global _INSTALLED
    if _INSTALLED:
        return

    application_class = app_module.ModalComparatorApp
    original_show_pair = application_class._show_pair

    def versioned_show_pair(self, pair) -> None:
        if self.cache is None:
            original_show_pair(self, pair)
            return

        pair_directory = self.cache / "plots" / "mode_pairs"
        ensure_pair_render_cache(pair_directory)
        expected = _expected_paths(pair_directory, pair)

        # Reuse a complete current-version set without invoking the older wrappers that
        # looked for *_overlay.png and could leave the obsolete vertical-line image visible.
        if all(path.exists() for path in expected.values()):
            self.current_pair = pair
            self.current_pair_paths = expected
            _display_paths(self, expected)
            _set_pair_title(self, pair)
            return

        original_show_pair(self, pair)
        paths = getattr(self, "current_pair_paths", {}) or expected
        _display_paths(self, paths)
        _set_pair_title(self, pair)

    application_class._show_pair = versioned_show_pair
    _INSTALLED = True
