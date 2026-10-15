"""Nine elastic constants — research diagnostic view (research track NINE-EC, Phase G). No Abaqus.

Opened from the main application (Workflow menu, quick_calibration_ui) as a Toplevel of its root. The view only calls
services.nine_constants_offline (no scientific logic here): INP + UNV/UFF → material / modal set (asked only when not
unique) → Run diagnostic → nine rows. It never starts Abaqus or any FE solve; a synthetic demonstration runs the full
research engine on the synthetic block model. Every result is RESEARCH_DIAGNOSTIC_ONLY /
NOT_A_VALIDATED_MATERIAL_PROPERTY.
"""

from __future__ import annotations

from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Callable, Optional

TITLE = "Nine elastic constants - research diagnostic (no Abaqus)"
BANNER = ("RESEARCH_DIAGNOSTIC_ONLY  ·  NOT_A_VALIDATED_MATERIAL_PROPERTY  ·  this view never starts Abaqus; "
          "a value appears only where the evidence supports it")
SELECT = "Select..."
COLUMNS = (("constant", "Constant", 90), ("input", "Input value", 120), ("estimate", "Estimated value", 130),
           ("uncertainty", "Uncertainty", 120), ("units", "Units", 190), ("status", "Status", 330))
STATUS_COLOURS = {"SUPPORTED_RESEARCH_ESTIMATE": "#174a7c", "NOT_IDENTIFIABLE": "#a11d1d", "NOT_EVALUATED": "#555555",
                  "FIXED_INPUT_NOT_IDENTIFIED": "#6b4e00", "POLICY_OR_EVIDENCE_BLOCKER": "#9a5300",
                  "INVALID_OR_UNSUPPORTED_MODEL": "#a11d1d"}


def _format(value) -> str:
    if value is None:
        return "-"
    return f"{value:,.6g}" if abs(value) >= 1 else f"{value:.4g}"


def _uncertainty(u) -> str:
    if not u:
        return "-"
    return f"±{u['relative_percent']:.2f} %" if u.get("units") == "ln p" else f"±{u['sd']:.3g}"


class NineConstantsWindow:
    def __init__(self, root: tk.Misc, threaded: bool = True, preview: Optional[Callable] = None,
                 demo: Optional[Callable] = None, discover: Optional[Callable] = None) -> None:
        from services.nine_constants_offline import SYNTHETIC_CASES, offline_preview, synthetic_demo

        self.root, self.threaded = root, threaded
        self.preview, self.demo = preview or offline_preview, demo or synthetic_demo
        self.discover = discover
        self.cases = SYNTHETIC_CASES
        self.messages: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self.worker: Optional[threading.Thread] = None
        self.report: Optional[dict] = None
        self.destroyed = False
        root.title(TITLE)
        self.inp = tk.StringVar(master=root)
        self.unv = tk.StringVar(master=root)
        self.result_file = tk.StringVar(master=root)
        self.material = tk.StringVar(master=root)
        self.modal_set = tk.StringVar(master=root)
        self.case = tk.StringVar(master=root, value=next(iter(SYNTHETIC_CASES)))
        self.headline = tk.StringVar(master=root, value="Choose the INP and the UNV/UFF file, then press Run diagnostic.")
        self._build()
        root.protocol("WM_DELETE_WINDOW", self.close)

    # ------------------------------------------------------------------ layout
    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        tk.Label(frame, text=BANNER, fg="white", bg="#a11d1d", font=("TkDefaultFont", 9, "bold"), anchor="w",
                 padx=6, pady=3).grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        row = 1

        def file_row(label, variable, command):
            nonlocal row
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(frame, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=4)
            ttk.Button(frame, text="Browse...", command=command).grid(row=row, column=2, sticky="ew")
            row += 1

        file_row("Abaqus model (.inp)", self.inp, self._browse_inp)
        file_row("Polytec / Testlab file (.unv/.uff)", self.unv, self._browse_unv)
        ttk.Label(frame, text="Material").grid(row=row, column=0, sticky="w", pady=2)
        self.material_box = ttk.Combobox(frame, textvariable=self.material, state="readonly", values=())
        self.material_box.grid(row=row, column=1, columnspan=2, sticky="ew", padx=4)
        row += 1
        ttk.Label(frame, text="Experimental modal set").grid(row=row, column=0, sticky="w", pady=2)
        self.modal_set_box = ttk.Combobox(frame, textvariable=self.modal_set, state="readonly", values=())
        self.modal_set_box.grid(row=row, column=1, columnspan=2, sticky="ew", padx=4)
        row += 1
        file_row("Frozen observations (optional:\nQuick Calibration result.json)", self.result_file,
                 self._browse_result)
        buttons = ttk.Frame(frame)
        buttons.grid(row=row, column=0, columnspan=3, sticky="ew", pady=8)
        self.run_button = ttk.Button(buttons, text="Run diagnostic (no Abaqus)", command=self.run_diagnostic)
        self.run_button.pack(side="left")
        ttk.Label(buttons, text="   Synthetic demonstration:").pack(side="left")
        self.case_box = ttk.Combobox(buttons, textvariable=self.case, state="readonly", values=list(self.cases),
                                     width=20)
        self.case_box.pack(side="left", padx=4)
        self.demo_button = ttk.Button(buttons, text="Run synthetic demonstration", command=self.run_demo)
        self.demo_button.pack(side="left")
        self.save_button = ttk.Button(buttons, text="Save report...", command=self._save, state="disabled")
        self.save_button.pack(side="left", padx=6)
        row += 1
        self.headline_label = ttk.Label(frame, textvariable=self.headline, wraplength=1000, justify="left",
                                        font=("TkDefaultFont", 10, "bold"))
        self.headline_label.grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 6))
        row += 1
        self.table = ttk.Treeview(frame, columns=[c[0] for c in COLUMNS], show="headings", height=9,
                                  selectmode="browse")
        for key, title, width in COLUMNS:
            self.table.heading(key, text=title)
            self.table.column(key, width=width, anchor="w", stretch=key == "status")
        for status, colour in STATUS_COLOURS.items():
            self.table.tag_configure(status, foreground=colour)
        self.table.grid(row=row, column=0, columnspan=3, sticky="ew")
        row += 1
        self.text = ScrolledText(frame, height=16, width=110, font=("Consolas", 9))
        self.text.grid(row=row, column=0, columnspan=3, sticky="nsew", pady=(6, 0))
        frame.rowconfigure(row, weight=1)
        self._write("Two files are enough: the INP of the specimen model and its measured UNV/UFF. The diagnostic "
                    "states for each of the nine constants whether this evidence can determine it. It never starts "
                    "Abaqus; the nine-constant sensitivities need approved FE evaluations.\n")

    # ------------------------------------------------------------------ inputs
    def _browse_inp(self) -> None:
        path = filedialog.askopenfilename(title="Abaqus model", filetypes=[("Abaqus input", "*.inp"), ("All", "*.*")])
        if path:
            self.set_inp(path)

    def _browse_unv(self) -> None:
        path = filedialog.askopenfilename(title="Polytec / Testlab file",
                                          filetypes=[("Universal file", "*.unv *.uff"), ("All", "*.*")])
        if path:
            self.set_unv(path)

    def _browse_result(self) -> None:
        path = filedialog.askopenfilename(title="Quick Calibration result", filetypes=[("JSON", "*.json")])
        if path:
            self.result_file.set(path)

    def set_inp(self, path: str) -> None:
        from services.nine_constants_inp import material_candidates

        self.inp.set(path)
        try:
            candidates = material_candidates(Path(path).read_bytes())
        except OSError as error:
            messagebox.showerror(TITLE, str(error), parent=self.root)
            return
        eligible = [c.name for c in candidates if c.eligible]
        self.material_box["values"] = eligible
        self.material.set(eligible[0] if len(eligible) == 1 else (SELECT if eligible else ""))
        if len(eligible) > 1:
            self._write(f"\nThe INP has {len(eligible)} materials with Engineering Constants ({', '.join(eligible)}): "
                        "select the one to analyse.\n")
        elif not eligible:
            self._write("\nNo material with one nine-value *Elastic, type=ENGINEERING CONSTANTS record: "
                        + "; ".join(f"{c.name}: {c.reason}" for c in candidates) + "\n")

    def set_unv(self, path: str) -> None:
        self.unv.set(path)
        self.modal_set_box["values"] = ()
        self.modal_set.set("")
        discover = self.discover
        if discover is None:
            from services.quick_calibration import discover_modal_sets as discover

        def work():
            try:
                self.messages.put(("sets", list(discover(Path(path)))))
            except Exception as error:  # noqa: BLE001 - shown, never swallowed
                self.messages.put(("failed", error))

        self._launch(work, busy=False)

    # ------------------------------------------------------------------ actions
    def _selected(self, variable: tk.StringVar) -> Optional[str]:
        value = variable.get().strip()
        return None if value in ("", SELECT) else value.split("   [")[-1].rstrip("]") if "   [" in value else value

    def run_diagnostic(self) -> None:
        if self.running():
            return
        inp, unv = self.inp.get().strip(), self.unv.get().strip()
        if not inp or not unv:
            messagebox.showerror(TITLE, "Choose the INP and the UNV/UFF file.", parent=self.root)
            return
        material, modal_set = self._selected(self.material), self._selected(self.modal_set)
        result = self.result_file.get().strip() or None
        self.headline.set("Running the offline diagnostic (no Abaqus)...")

        def work():
            from services.nine_constants_offline import OfflinePreviewChoiceRequired

            try:
                report = self.preview(Path(inp), Path(unv), material, modal_set,
                                      None if result is None else Path(result))
                self.messages.put(("report", report))
            except OfflinePreviewChoiceRequired as choice:
                self.messages.put(("choice", choice))
            except Exception as error:  # noqa: BLE001 - shown, never swallowed
                self.messages.put(("failed", error))

        self._launch(work)

    def run_demo(self) -> None:
        if self.running():
            return
        case = self.case.get()
        self.headline.set(f"Running the synthetic demonstration '{case}' (synthetic model, no Abaqus)...")

        def work():
            try:
                self.messages.put(("report", self.demo(case)))
            except Exception as error:  # noqa: BLE001
                self.messages.put(("failed", error))

        self._launch(work)

    def running(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def _launch(self, work, busy: bool = True) -> None:
        if busy:
            self.run_button.configure(state="disabled")
            self.demo_button.configure(state="disabled")
        if self.threaded:
            self.worker = threading.Thread(target=work, daemon=True)
            self.worker.start()
            self.root.after(100, self._poll)
        else:
            work()
            self._poll(reschedule=False)

    def _poll(self, reschedule: bool = True) -> None:
        if self.destroyed:
            return
        while True:
            try:
                kind, payload = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == "sets":
                labels = [f"{s.label}   [{s.key}]" for s in payload]
                self.modal_set_box["values"] = labels
                self.modal_set.set(labels[0] if len(labels) == 1 else (SELECT if labels else ""))
                if len(labels) > 1:
                    self._write(f"\n{len(labels)} modal sets in the file: select one.\n")
            elif kind == "report":
                self.show(payload)
            elif kind == "choice":
                self.headline.set(f"CHOICE REQUIRED: {payload}")
                self._write(f"\nCHOICE REQUIRED ({payload.field}): {payload}  Options: {', '.join(payload.options)}\n")
            elif kind == "failed":
                self.headline.set(f"FAILED: {payload}")
                self._write(f"\nFAILED: {type(payload).__name__}: {payload}\n")
        if self.running() and reschedule:
            self.root.after(150, self._poll)
            return
        self.run_button.configure(state="normal")
        self.demo_button.configure(state="normal")

    def show(self, report: dict) -> None:
        from services.nine_constants_report import report_text

        self.report = report
        self.headline.set(report["headline"])
        self.table.delete(*self.table.get_children())
        for row in report["constants"]:
            self.table.insert("", "end", values=(row["constant"], _format(row["input_value"]),
                                                 _format(row["estimated_value"]), _uncertainty(row["uncertainty"]),
                                                 row["units"], row["status_text"]), tags=(row["status"],))
        self.text.delete("1.0", "end")
        self._write(report_text(report))
        self.save_button.configure(state="normal")

    def _save(self) -> None:
        from services.nine_constants_report import write_report

        folder = filedialog.askdirectory(title="Folder for the nine-constant report")
        if folder and self.report is not None:
            paths = write_report(self.report, Path(folder))
            self._write("\nSaved: " + ", ".join(str(p) for p in paths.values()) + "\n")

    def _write(self, text: str) -> None:
        self.text.insert("end", text)
        self.text.see("end")

    def close(self) -> None:
        self.destroyed = True  # an offline worker owns no external process; nothing to stop
        self.root.destroy()
