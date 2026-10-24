"""1. Files > Experimental series review: show and set a person's SETUP_UNDER_REVIEW note (APP-E2E.3).

The selected experimental file is identified (content SHA-256 and size, and the selected modal set) off the GUI
thread; the note of exactly that series is shown. The dialog records or withdraws the note with a mandatory reason,
source and experiment identifier. The note never changes data, analysis inputs, results or exports other than the
note itself (services.experimental_series_review).
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Optional

from services import experimental_series_review as review

MARKED_COLOUR = "#9a4d00"


def store_of(app) -> Path:
    return Path(getattr(app, "_series_review_store", None) or review.default_store())


def build_series_review_row(app, parent, row: int) -> None:
    app.series_review_text = tk.StringVar(master=app.root, value="Experimental series review: no file selected.")
    app._series_identity = None
    app._series_mark = None
    app._series_generation = 0
    ttk.Label(parent, text="Series review:").grid(row=row, column=0, sticky="nw", pady=(4, 2))
    app.series_review_label = ttk.Label(parent, textvariable=app.series_review_text, justify="left", wraplength=700)
    app.series_review_label.grid(row=row, column=1, sticky="ew", padx=(10, 0), pady=(4, 2))
    # wrapped to the width of its own column (never under the button next to it)
    app.series_review_label._wraps_to_pane = True
    app.series_review_label.bind(
        "<Configure>", lambda event: app.series_review_label.configure(wraplength=max(200, event.width - 4)), add="+")
    app.series_review_button = ttk.Button(parent, text="Review series...",
                                          command=lambda: open_series_review_dialog(app))
    app.series_review_button.grid(row=row, column=2, sticky="ne", padx=(10, 0), pady=(4, 2))
    for variable in (app.experimental_path, app.experimental_modal_set_key):
        variable.trace_add("write", lambda *_: schedule_identification(app))
    schedule_identification(app)


def _show(app, identity, mark, note: str = "") -> None:
    app._series_identity, app._series_mark = identity, mark
    text = note or review.mark_text(mark)
    app.series_review_text.set(text)
    try:
        app.series_review_label.configure(foreground=MARKED_COLOUR if mark is not None else "")
    except tk.TclError:
        pass


def schedule_identification(app) -> None:
    """Identify the selected series off the GUI thread; a newer selection discards an older answer."""
    app._series_generation += 1
    generation = app._series_generation
    path_text = app.experimental_path.get().strip()
    modal_set = app.experimental_modal_set_key.get()
    if not path_text or not Path(path_text).is_file():
        _show(app, None, None, "Experimental series review: no experimental file selected.")
        return
    _show(app, None, None, "Experimental series review: identifying the series (content SHA-256)...")
    store = store_of(app)
    results = queue.Queue(maxsize=1)

    def work() -> None:
        try:
            identity = review.series_identity(Path(path_text), modal_set)
            results.put((identity, review.active_mark(store, identity), ""))
        except review.SeriesReviewError as error:
            results.put((None, None, f"Experimental series review: not available ({error})."))

    def poll() -> None:  # the same pattern as the modal-set discovery: the GUI thread collects the answer
        if generation != app._series_generation or getattr(app, "_ui_closing", False):
            return
        try:
            identity, mark, note = results.get_nowait()
        except queue.Empty:
            try:
                app.root.after(40, poll)
            except (tk.TclError, RuntimeError):
                pass
            return
        _show(app, identity, mark, note)

    threading.Thread(target=work, daemon=True).start()
    app.root.after(40, poll)


def open_series_review_dialog(app) -> Optional[tk.Toplevel]:
    identity = getattr(app, "_series_identity", None)
    if identity is None:
        messagebox.showinfo("Experimental series review", "Select an experimental file and wait until the series is "
                            "identified (content SHA-256).")
        return None
    window = tk.Toplevel(app.root)
    window.title("Experimental series review")
    window.transient(app.root)
    body = ttk.Frame(window, padding=14)
    body.pack(fill="both", expand=True)
    body.columnconfigure(1, weight=1)
    rows = (("File (informational)", identity.file_name), ("Content SHA-256", identity.sha256),
            ("Size", f"{identity.size_bytes} bytes"), ("Modal set", identity.modal_set or "none (no fitted set)"))
    for index, (name, value) in enumerate(rows):
        ttk.Label(body, text=name + ":").grid(row=index, column=0, sticky="w")
        ttk.Label(body, text=value).grid(row=index, column=1, sticky="w", padx=(8, 0))
    current = tk.StringVar(master=window, value=review.mark_text(app._series_mark))
    ttk.Label(body, textvariable=current, wraplength=640, justify="left").grid(
        row=4, column=0, columnspan=2, sticky="w", pady=(10, 8))
    fields = {}
    for index, (key, label) in enumerate((("experiment_id", "Experiment / test-run identifier"),
                                          ("reason", "Reason"), ("source", "Source of the information"),
                                          ("marked_by", "Recorded by (optional)")), start=5):
        ttk.Label(body, text=label + ":").grid(row=index, column=0, sticky="w", pady=2)
        fields[key] = tk.StringVar(master=window)
        ttk.Entry(body, textvariable=fields[key], width=70).grid(row=index, column=1, sticky="ew", padx=(8, 0), pady=2)
    ttk.Label(body, text=review.NOTE, wraplength=640, justify="left", style="Secondary.TLabel").grid(
        row=9, column=0, columnspan=2, sticky="w", pady=(8, 8))
    buttons = ttk.Frame(body)
    buttons.grid(row=10, column=0, columnspan=2, sticky="e")

    def refresh_current() -> None:
        current.set(review.mark_text(app._series_mark))

    def mark() -> None:
        try:
            review.mark_setup_under_review(store_of(app), identity, reason=fields["reason"].get(),
                                           source=fields["source"].get(), experiment_id=fields["experiment_id"].get(),
                                           marked_by=fields["marked_by"].get())
            _show(app, identity, review.active_mark(store_of(app), identity))
        except review.SeriesReviewError as error:
            messagebox.showwarning("Experimental series review", str(error), parent=window)
            return
        refresh_current()

    def withdraw() -> None:
        try:
            review.withdraw_mark(store_of(app), identity, reason=fields["reason"].get(), source=fields["source"].get())
            _show(app, identity, review.active_mark(store_of(app), identity))
        except review.SeriesReviewError as error:
            messagebox.showwarning("Experimental series review", str(error), parent=window)
            return
        refresh_current()

    window.mark_button = ttk.Button(buttons, text=f"Mark {review.SETUP_UNDER_REVIEW}", command=mark)
    window.mark_button.pack(side="left")
    window.withdraw_button = ttk.Button(buttons, text="Withdraw mark", command=withdraw)
    window.withdraw_button.pack(side="left", padx=8)
    ttk.Button(buttons, text="Close", command=window.destroy).pack(side="left")
    window.fields = fields
    return window
