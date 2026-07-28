from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple
import tkinter as tk

from PIL import Image, ImageTk


MIN_RENDER_DIMENSION = 48
RESIZE_DEBOUNCE_MS = 90
IMAGE_PADDING = 12
_INSTALLED = False


def fit_image_size(
    source_size: Tuple[int, int],
    box_size: Tuple[int, int],
) -> Tuple[int, int]:
    """Return the largest aspect-preserving size that fits inside *box_size*."""
    source_width, source_height = (int(source_size[0]), int(source_size[1]))
    box_width, box_height = (int(box_size[0]), int(box_size[1]))
    if source_width <= 0 or source_height <= 0:
        raise ValueError("Source image dimensions must be positive.")
    if box_width <= 0 or box_height <= 0:
        raise ValueError("Target image dimensions must be positive.")

    scale = min(box_width / source_width, box_height / source_height)
    return (
        max(1, int(round(source_width * scale))),
        max(1, int(round(source_height * scale))),
    )


def install_responsive_images(app_module) -> None:
    """Scale every embedded plot to the current label size and rescale on resize."""
    global _INSTALLED
    if _INSTALLED:
        return

    application_class = app_module.ModalComparatorApp
    original_init = application_class.__init__

    def responsive_init(self, *args, **kwargs) -> None:
        self._responsive_sources: Dict[str, Image.Image] = {}
        self._responsive_label_keys = {}
        self._responsive_resize_jobs = {}
        self._responsive_last_render = {}
        self._responsive_bound_labels = set()
        original_init(self, *args, **kwargs)
        self.tabs.bind(
            "<<NotebookTabChanged>>",
            lambda _event: self.root.after_idle(self._refresh_responsive_images),
            add="+",
        )

    def _render_responsive_image(self, label) -> None:
        self._responsive_resize_jobs.pop(label, None)
        key = self._responsive_label_keys.get(label)
        source = self._responsive_sources.get(key)
        if key is None or source is None:
            return
        try:
            if not label.winfo_exists():
                return
            available_width = int(label.winfo_width()) - IMAGE_PADDING
            available_height = int(label.winfo_height()) - IMAGE_PADDING
        except tk.TclError:
            return

        # Hidden notebook pages commonly report 1x1. Defer rendering until the page
        # becomes visible instead of installing an oversized fixed thumbnail.
        if (
            available_width < MIN_RENDER_DIMENSION
            or available_height < MIN_RENDER_DIMENSION
        ):
            return

        target_size = fit_image_size(
            source.size,
            (available_width, available_height),
        )
        signature = (key, target_size)
        if self._responsive_last_render.get(label) == signature:
            return

        try:
            resized = source.resize(target_size, Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(resized, master=self.root)
            self.photos[key] = photo
            label.configure(image=photo, text="", anchor="center")
            self._responsive_last_render[label] = signature
        except (OSError, ValueError, tk.TclError) as error:
            try:
                label.configure(image="", text=f"Could not display image:\n{error}")
            except tk.TclError:
                pass

    def _schedule_responsive_image(self, label, *, immediate: bool = False) -> None:
        previous = self._responsive_resize_jobs.pop(label, None)
        if previous is not None:
            try:
                self.root.after_cancel(previous)
            except tk.TclError:
                pass
        delay = 0 if immediate else RESIZE_DEBOUNCE_MS
        try:
            job = self.root.after(delay, lambda: self._render_responsive_image(label))
        except tk.TclError:
            return
        self._responsive_resize_jobs[label] = job

    def _refresh_responsive_images(self) -> None:
        for label in tuple(self._responsive_label_keys):
            self._schedule_responsive_image(label, immediate=True)

    def responsive_image(self, label, path: Path, key: str) -> None:
        try:
            with Image.open(path) as opened:
                source = opened.copy()
        except Exception as error:
            try:
                label.configure(image="", text=f"Could not display image:\n{error}")
            except tk.TclError:
                pass
            return

        self._responsive_sources[key] = source
        self._responsive_label_keys[label] = key
        self._responsive_last_render.pop(label, None)

        if label not in self._responsive_bound_labels:
            label.bind(
                "<Configure>",
                lambda _event, current_label=label: self._schedule_responsive_image(
                    current_label
                ),
                add="+",
            )
            self._responsive_bound_labels.add(label)

        # Rendering after idle lets Tk finish allocating the current tab before the
        # target dimensions are calculated.
        self._schedule_responsive_image(label, immediate=True)

    application_class.__init__ = responsive_init
    application_class._render_responsive_image = _render_responsive_image
    application_class._schedule_responsive_image = _schedule_responsive_image
    application_class._refresh_responsive_images = _refresh_responsive_images
    application_class._image = responsive_image
    _INSTALLED = True
