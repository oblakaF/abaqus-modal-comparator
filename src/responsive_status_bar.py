from __future__ import annotations


_INSTALLED = False
_MIN_PROGRESS_LENGTH = 170
_MAX_PROGRESS_LENGTH = 360
_PROGRESS_WIDTH_FRACTION = 0.22


def progress_length_for_width(width: int) -> int:
    """Return a readable progress-bar length for the current window width."""
    try:
        available = max(1, int(width))
    except (TypeError, ValueError):
        available = 1
    return max(
        _MIN_PROGRESS_LENGTH,
        min(_MAX_PROGRESS_LENGTH, int(available * _PROGRESS_WIDTH_FRACTION)),
    )


def ensure_status_bar_visible(application) -> bool:
    """Reserve bottom space for the status bar before the expanding notebook.

    The base UI historically packed the expanding notebook before the footer.
    When a tab requested more vertical space than the current window provided,
    Tk could clip the footer until the user enlarged the window. Reordering the
    existing packed children makes the footer claim its bottom strip first.
    """
    root = getattr(application, "root", None)
    tabs = getattr(application, "tabs", None)
    progress = getattr(application, "progress", None)
    if root is None or tabs is None or progress is None:
        return False

    footer = getattr(progress, "master", None)
    if footer is None or footer is root:
        return False

    try:
        footer.pack_forget()
        footer.pack(side="bottom", fill="x", before=tabs)
        footer.lift()
    except Exception:
        return False

    def resize_progress(event=None) -> None:
        if event is not None and getattr(event, "widget", root) is not root:
            return
        try:
            width = int(root.winfo_width())
            progress.configure(length=progress_length_for_width(width))
            footer.lift()
        except Exception:
            return

    application._resize_status_progress = resize_progress
    root.bind("<Configure>", resize_progress, add="+")
    root.after_idle(resize_progress)
    return True


def install_responsive_status_bar(app_module) -> None:
    """Keep the status text and progress indicator visible at every window size."""
    global _INSTALLED
    if _INSTALLED:
        return

    application_class = app_module.ModalComparatorApp
    original_init = application_class.__init__

    def responsive_status_init(self, root) -> None:
        original_init(self, root)
        ensure_status_bar_visible(self)

    responsive_status_init.__name__ = getattr(original_init, "__name__", "__init__")
    responsive_status_init.__doc__ = getattr(original_init, "__doc__", None)
    application_class.__init__ = responsive_status_init
    _INSTALLED = True
