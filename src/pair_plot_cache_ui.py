from __future__ import annotations

from pathlib import Path

from plot_cache_version import ensure_pair_render_cache


_INSTALLED = False


def install_pair_plot_cache_ui(app_module) -> None:
    """Invalidate stale pair plots before display and show the freshly rendered paths."""
    global _INSTALLED
    if _INSTALLED:
        return

    application_class = app_module.ModalComparatorApp
    original_show_pair = application_class._show_pair

    def versioned_show_pair(self, pair) -> None:
        if self.cache is not None:
            ensure_pair_render_cache(self.cache / "plots" / "mode_pairs")

        original_show_pair(self, pair)

        # figure_export_ui stores the current paths after rendering. Re-display them here
        # so an older inner wrapper can never leave a stale *_overlay.png on screen.
        paths = getattr(self, "current_pair_paths", {})
        if len(getattr(self, "shape_labels", [])) >= 3 and paths:
            for label, key, image_key in zip(
                self.shape_labels,
                ("abaqus", "experimental", "overlay"),
                ("pair_a_current", "pair_e_current", "pair_correlation_current"),
            ):
                path = paths.get(key)
                if path is not None and Path(path).exists():
                    self._image(label, Path(path), image_key)

    application_class._show_pair = versioned_show_pair
    _INSTALLED = True
