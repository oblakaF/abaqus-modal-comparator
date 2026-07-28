from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from help_content import HELP_TOPICS, filter_help_topics


_INSTALLED = False
WINDOW_TITLE = "Help"


def _build_help_window(app, initial_query: str = "") -> tk.Toplevel:
    window = tk.Toplevel(app.root)
    window.title(WINDOW_TITLE)
    window.geometry("980x620")
    window.minsize(720, 420)

    search_row = ttk.Frame(window, padding=(10, 10, 10, 4))
    search_row.pack(fill="x")
    ttk.Label(search_row, text="Search:").pack(side="left")
    query = tk.StringVar(value=initial_query)
    entry = ttk.Entry(search_row, textvariable=query)
    entry.pack(side="left", fill="x", expand=True, padx=(6, 0))

    body = ttk.Frame(window, padding=(10, 0, 10, 10))
    body.pack(fill="both", expand=True)

    list_frame = ttk.Frame(body)
    list_frame.pack(side="left", fill="y", padx=(0, 10))
    listbox = tk.Listbox(list_frame, width=34, activestyle="dotbox", exportselection=False)
    list_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
    listbox.configure(yscrollcommand=list_scroll.set)
    listbox.pack(side="left", fill="y")
    list_scroll.pack(side="left", fill="y")

    text_frame = ttk.Frame(body)
    text_frame.pack(side="left", fill="both", expand=True)
    text = tk.Text(text_frame, wrap="word", font=("Segoe UI", 10), state="disabled")
    text_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=text_scroll.set)
    text.pack(side="left", fill="both", expand=True)
    text_scroll.pack(side="left", fill="y")

    state = {"topics": list(HELP_TOPICS)}

    def show_topic(index: int) -> None:
        if not (0 <= index < len(state["topics"])):
            return
        title, text_body = state["topics"][index]
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert("1.0", f"{title}\n\n{text_body}")
        text.configure(state="disabled")

    def refresh(*_args) -> None:
        matches = filter_help_topics(HELP_TOPICS, query.get())
        state["topics"] = matches
        listbox.delete(0, "end")
        for title, _body in matches:
            listbox.insert("end", title)
        if matches:
            listbox.selection_set(0)
            show_topic(0)
        else:
            text.configure(state="normal")
            text.delete("1.0", "end")
            text.insert("1.0", "No help topic matches that search.")
            text.configure(state="disabled")

    def on_select(_event=None) -> None:
        selection = listbox.curselection()
        if selection:
            show_topic(selection[0])

    query.trace_add("write", refresh)
    listbox.bind("<<ListboxSelect>>", on_select)
    refresh()
    entry.focus_set()
    window.help_query = query
    return window


def open_help(self, initial_query: str = "") -> None:
    window = getattr(self, "_help_window", None)
    if window is not None:
        try:
            if window.winfo_exists():
                if initial_query:
                    window.help_query.set(initial_query)
                window.deiconify()
                window.lift()
                window.focus_force()
                return
        except tk.TclError:
            pass
    window = _build_help_window(self, initial_query)
    self._help_window = window


def install_help_ui(app_module) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    application_class = app_module.ModalComparatorApp
    original_init = application_class.__init__

    def help_init(self, root) -> None:
        self._help_window = None
        original_init(self, root)
        root.bind("<F1>", lambda _event: self._open_help())

    application_class.__init__ = help_init
    application_class._open_help = open_help
    _INSTALLED = True
