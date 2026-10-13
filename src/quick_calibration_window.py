"""Quick effective-property calibration window (standalone; started by RUN_QUICK_CALIBRATION.cmd).

Choose the Abaqus model (INP), the Polytec / Testlab file (UNV/UFF) and the material, press Run.
The work is done by services.quick_calibration (the same service as tools/quick_calibration.py).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Callable, Optional

from services.forward_builder import _parameters, inp_keyword, split_inp_lines
from services.quick_calibration import (
    DEFAULT_MAX_NEW_FE_SOLVES,
    AbaqusRunner,
    CalibrationCancelled,
    PreflightRefused,
    QuickCalibrationError,
    TerminationUnconfirmed,
    STATUS_ESTIMATE,
    config_from_dict,
    describe_orientation,
    discover_modal_sets,
    locate_elastic,
    preflight,
    run_quick_calibration,
)

TITLE = "Quick material calibration (Abaqus + Polytec)"
DEFAULT_CONSTANTS = {"ENGINEERING CONSTANTS": "E1,E2", "LAMINA": "E1,E2", "ISOTROPIC": "E"}
SELECT_MODAL_SET = "Select the modal set..."
READING_MODAL_SETS = "Reading the modal sets..."
NO_MODAL_SET = "no dataset-55 modal set (dataset 2414 / 58 fallback)"
NOT_CHECKED = "Inputs not checked yet: press Check inputs (no Abaqus run)."


def inp_materials(path: Path) -> list[tuple[str, str]]:
    """(material name, *Elastic type or '') for every *Material of the INP file."""
    lines = split_inp_lines(Path(path).read_bytes())
    names = [_parameters(line).get("name", "") for line in lines if inp_keyword(line) == "material"]
    out = []
    for name in names:
        try:
            out.append((name, locate_elastic(lines, name).elastic_type))
        except Exception:  # noqa: BLE001 - shown as unsupported in the list
            out.append((name, ""))
    return out


def summary_text(result: dict) -> str:
    if result.get("status") != STATUS_ESTIMATE:
        return "NO VALUE: " + "; ".join(result.get("refusal_reasons") or ["see the report"])
    parts = []
    for name, estimate in result["estimates"].items():
        constants = ", ".join(f"{c} = {v['calibrated_value']:,.0f}" for c, v in estimate["constants"].items())
        parts.append(f"{name}: k = {estimate['multiplier']:.4f} (±{estimate['band_percent']:.1f} %) → {constants}")
    return f"{result['overall_grade']}: " + " | ".join(parts)


class QuickCalibrationWindow:
    def __init__(self, root: tk.Misc, solve: Optional[Callable] = None, extract: Optional[Callable] = None,
                 threaded: bool = True, runner_factory: Optional[Callable] = None) -> None:
        self.root, self.solve, self.extract, self.threaded = root, solve, extract, threaded
        # (config, cancel event) -> AbaqusRunner; the real runner unless solve / extract are injected
        self.runner_factory = runner_factory or (lambda config, cancel: AbaqusRunner(
            config.abaqus_command, config.cpus, config.timeout_minutes, cancel))
        self.cancel_event = threading.Event()
        self.closing = False
        self.unconfirmed: Optional[TerminationUnconfirmed] = None  # owned processes whose stop was not confirmed
        self.destroyed = False
        self.messages: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self.result: Optional[dict] = None
        self.paths: dict = {}
        self.orientation_ids: dict[str, str] = {}
        self.worker: Optional[threading.Thread] = None
        root.title(TITLE)
        self.inp = tk.StringVar(master=root)
        self.unv = tk.StringVar(master=root)
        self.out = tk.StringVar(master=root)
        self.abaqus = tk.StringVar(master=root, value="abaqus")
        self.cpus = tk.StringVar(master=root, value=str(max(1, min(4, os.cpu_count() or 1))))
        self.max_new_fe_solves = tk.StringVar(master=root, value=str(DEFAULT_MAX_NEW_FE_SOLVES))
        self.material = tk.StringVar(master=root)
        self.constants = tk.StringVar(master=root, value="E1,E2")
        self.fit_g12 = tk.BooleanVar(master=root, value=False)
        self.lower = tk.StringVar(master=root, value="0.5")
        self.upper = tk.StringVar(master=root, value="2.0")
        self.min_hz = tk.StringVar(master=root)
        self.max_hz = tk.StringVar(master=root)
        self.orientation = tk.StringVar(master=root, value="automatic (geometry)")
        self.modal_set = tk.StringVar(master=root)
        self.modal_set_keys: dict[str, Optional[str]] = {}
        self.modal_set_generation = 0
        self.readiness = tk.StringVar(master=root, value=NOT_CHECKED)
        self.preflight_report = None
        self.summary = tk.StringVar(master=root, value="Choose the files and press Run.")
        self._build()
        self._detect_abaqus()
        self.unv.trace_add("write", lambda *_: self._discover_modal_sets())
        root.protocol("WM_DELETE_WINDOW", self.close)

    # ------------------------------------------------------------------ layout
    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        row = 0

        def file_row(label, variable, command):
            nonlocal row
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(frame, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=4)
            ttk.Button(frame, text="Browse...", command=command).grid(row=row, column=2, sticky="ew")
            row += 1

        file_row("Abaqus model (.inp)", self.inp, self._browse_inp)
        file_row("Polytec / Testlab file (.unv/.uff)", self.unv, self._browse_unv)
        ttk.Label(frame, text="Experimental modal set").grid(row=row, column=0, sticky="w", pady=2)
        self.modal_set_box = ttk.Combobox(frame, textvariable=self.modal_set, state="readonly", values=())
        self.modal_set_box.grid(row=row, column=1, columnspan=2, sticky="ew", padx=4)
        self.modal_set_box.bind("<<ComboboxSelected>>", lambda _event: self._inputs_changed())
        row += 1
        file_row("Output folder", self.out, self._browse_out)

        ttk.Label(frame, text="Abaqus command").grid(row=row, column=0, sticky="w", pady=2)
        self.abaqus_box = ttk.Combobox(frame, textvariable=self.abaqus)
        self.abaqus_box.grid(row=row, column=1, sticky="ew", padx=4)
        cpu_frame = ttk.Frame(frame)
        cpu_frame.grid(row=row, column=2, sticky="ew")
        ttk.Label(cpu_frame, text="CPUs").pack(side="left")
        ttk.Spinbox(cpu_frame, from_=1, to=64, width=4, textvariable=self.cpus).pack(side="left", padx=4)
        ttk.Label(cpu_frame, text="Max new FE solves").pack(side="left", padx=(8, 0))
        self.max_solves_box = ttk.Spinbox(cpu_frame, from_=1, to=500, width=5, textvariable=self.max_new_fe_solves)
        self.max_solves_box.pack(side="left", padx=4)
        row += 1

        ttk.Label(frame, text="Material to calibrate").grid(row=row, column=0, sticky="w", pady=2)
        self.material_box = ttk.Combobox(frame, textvariable=self.material, state="readonly")
        self.material_box.grid(row=row, column=1, sticky="ew", padx=4)
        self.material_box.bind("<<ComboboxSelected>>", lambda _event: self._material_changed())
        row += 1
        ttk.Label(frame, text="Constants scaled together").grid(row=row, column=0, sticky="w", pady=2)
        constants_frame = ttk.Frame(frame)
        constants_frame.grid(row=row, column=1, columnspan=2, sticky="ew", padx=4)
        ttk.Entry(constants_frame, textvariable=self.constants, width=16).pack(side="left")
        ttk.Label(constants_frame, text="  multiplier from").pack(side="left")
        ttk.Entry(constants_frame, textvariable=self.lower, width=5).pack(side="left")
        ttk.Label(constants_frame, text="to").pack(side="left", padx=2)
        ttk.Entry(constants_frame, textvariable=self.upper, width=5).pack(side="left")
        ttk.Checkbutton(constants_frame, text="also fit G12 (second parameter)",
                        variable=self.fit_g12).pack(side="left", padx=12)
        row += 1
        ttk.Label(frame, text="Experimental modes [Hz]").grid(row=row, column=0, sticky="w", pady=2)
        hz_frame = ttk.Frame(frame)
        hz_frame.grid(row=row, column=1, columnspan=2, sticky="ew", padx=4)
        ttk.Label(hz_frame, text="from").pack(side="left")
        ttk.Entry(hz_frame, textvariable=self.min_hz, width=8).pack(side="left", padx=2)
        ttk.Label(hz_frame, text="to").pack(side="left")
        ttk.Entry(hz_frame, textvariable=self.max_hz, width=8).pack(side="left", padx=2)
        ttk.Label(hz_frame, text="(empty = all; set 'from' above the suspension modes)").pack(side="left", padx=6)
        row += 1
        ttk.Label(frame, text="Scan orientation").grid(row=row, column=0, sticky="w", pady=2)
        self.orientation_box = ttk.Combobox(frame, textvariable=self.orientation, state="readonly",
                                            values=["automatic (geometry)"])
        self.orientation_box.grid(row=row, column=1, columnspan=2, sticky="ew", padx=4)
        row += 1

        buttons = ttk.Frame(frame)
        buttons.grid(row=row, column=0, columnspan=3, sticky="ew", pady=8)
        self.check_button = ttk.Button(buttons, text="Check inputs", command=self.check_inputs)
        self.check_button.pack(side="left", padx=(0, 6))
        self.run_button = ttk.Button(buttons, text="Run calibration", command=self.start)
        self.run_button.pack(side="left")
        self.stop_button = ttk.Button(buttons, text="Stop", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=6)
        self.open_button = ttk.Button(buttons, text="Open output folder", command=self._open_output,
                                      state="disabled")
        self.open_button.pack(side="left", padx=6)
        ttk.Button(buttons, text="Save configuration...", command=self._save_config).pack(side="left")
        row += 1
        readiness = ttk.LabelFrame(frame, text="Input readiness (checked before any Abaqus solve)", padding=4)
        readiness.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        readiness.columnconfigure(0, weight=1)
        ttk.Label(readiness, textvariable=self.readiness, wraplength=1000, justify="left").grid(
            row=0, column=0, sticky="w")
        self.readiness_table = ttk.Treeview(readiness, columns=("item", "status", "detail"), show="headings",
                                            height=7, selectmode="none")
        for key, title, width in (("item", "Check", 190), ("status", "Status", 80), ("detail", "Detail", 760)):
            self.readiness_table.heading(key, text=title)
            self.readiness_table.column(key, width=width, anchor="w", stretch=key == "detail")
        self.readiness_table.grid(row=1, column=0, sticky="ew")
        row += 1
        ttk.Label(frame, textvariable=self.summary, wraplength=900, font=("TkDefaultFont", 10, "bold"),
                  justify="left").grid(row=row, column=0, columnspan=3, sticky="w")
        row += 1
        self.log = ScrolledText(frame, height=22, width=110, font=("Consolas", 9))
        self.log.grid(row=row, column=0, columnspan=3, sticky="nsew")
        frame.rowconfigure(row, weight=1)
        self._write("The result is an effective calibration of THIS model on THIS specimen, not a material "
                    "property.\nEach Abaqus solve can take minutes; the run reuses finished jobs when repeated.\n")

    # ------------------------------------------------------------------ inputs
    def _detect_abaqus(self) -> None:
        try:
            from ui_policy import discover_abaqus_installations

            commands = [item.command for item in discover_abaqus_installations()]
        except Exception:  # noqa: BLE001 - detection is a convenience only
            commands = []
        self.abaqus_box["values"] = commands or ["abaqus"]
        if commands:
            self.abaqus.set(commands[0])

    def _browse_inp(self) -> None:
        path = filedialog.askopenfilename(title="Abaqus model", filetypes=[("Abaqus input", "*.inp"), ("All", "*.*")])
        if path:
            self.set_inp(path)

    def set_inp(self, path: str) -> None:
        self.inp.set(path)
        if not self.out.get():
            self.out.set(str(Path(path).with_name(Path(path).stem + "_quick_calibration")))
        try:
            materials = inp_materials(Path(path))
        except OSError as error:
            messagebox.showerror(TITLE, str(error), parent=self.root)
            return
        self._materials = dict(materials)
        labels = [name for name, kind in materials if kind]
        self.material_box["values"] = labels
        preferred = [n for n in labels if any(k in n.lower() for k in ("face", "cfrp", "carbon", "skin"))]
        if preferred or labels:
            self.material.set((preferred or labels)[0])
            self._material_changed()

    def _material_changed(self) -> None:
        kind = getattr(self, "_materials", {}).get(self.material.get(), "")
        self.constants.set(DEFAULT_CONSTANTS.get(kind, "E1,E2"))
        self.fit_g12.set(False)

    def _browse_unv(self) -> None:
        path = filedialog.askopenfilename(title="Polytec / Testlab file",
                                          filetypes=[("Universal file", "*.unv *.uff"), ("All", "*.*")])
        if path:
            self.unv.set(path)

    def _discover_modal_sets(self) -> None:
        """List the dataset-55 modal sets of the chosen file; several sets need an explicit choice."""
        self.modal_set_generation += 1
        generation = self.modal_set_generation
        self.modal_set_keys = {}
        self.modal_set_box["values"] = ()
        self.modal_set.set("")
        self._inputs_changed()
        text = self.unv.get().strip()
        path = Path(text) if text else None
        if path is None or not path.is_file():
            return
        self.modal_set.set(READING_MODAL_SETS)

        def work():
            try:
                outcome = (discover_modal_sets(path), None)
            except Exception as error:  # noqa: BLE001 - shown in the readiness summary
                outcome = ((), error)
            self.messages.put(("modal_sets", (generation, outcome)))

        if self.threaded:
            threading.Thread(target=work, daemon=True).start()
            self.root.after(100, self._poll_idle)
        else:
            work()
            self._poll(reschedule=False)

    def _apply_modal_sets(self, generation: int, outcome) -> None:
        if generation != self.modal_set_generation:
            return  # superseded by another file
        choices, error = outcome
        if error is not None:
            self.modal_set.set("")
            self.readiness.set(f"NOT READY: the experimental file cannot be read ({error}).")
            return
        if not choices:
            self.modal_set_keys = {NO_MODAL_SET: None}
            self.modal_set_box["values"] = (NO_MODAL_SET,)
            self.modal_set.set(NO_MODAL_SET)
            return
        self.modal_set_keys = {f"{choice.label}   [{choice.key}]": choice.key for choice in choices}
        labels = list(self.modal_set_keys)
        if len(choices) == 1:
            self.modal_set_box["values"] = labels
            self.modal_set.set(labels[0])
        else:  # never the first set: the user selects one
            self.modal_set_box["values"] = [SELECT_MODAL_SET] + labels
            self.modal_set.set(SELECT_MODAL_SET)
            self.readiness.set(f"{len(choices)} modal sets in this file: select one in 'Experimental modal set'.")

    def _inputs_changed(self) -> None:
        self.preflight_report = None
        self.readiness.set(NOT_CHECKED)
        if hasattr(self, "readiness_table"):
            self.readiness_table.delete(*self.readiness_table.get_children())

    def _show_preflight(self, report) -> None:
        self.preflight_report = report
        self.readiness.set(report.summary())
        self.readiness_table.delete(*self.readiness_table.get_children())
        for check in report.checks:
            self.readiness_table.insert("", "end", values=(check.item, check.status, check.detail))
        self._write("\n=== input readiness\n" + "\n".join(report.lines()) + "\n")

    def _browse_out(self) -> None:
        path = filedialog.askdirectory(title="Output folder")
        if path:
            self.out.set(path)

    def config_data(self) -> dict:
        def number(variable):
            text = variable.get().strip()
            return float(text) if text else None

        parameters = [{"name": "E_face" if self.constants.get().upper().startswith("E") else "k",
                       "material": self.material.get(), "constants": self.constants.get(),
                       "lower": float(self.lower.get()), "upper": float(self.upper.get())}]
        if self.fit_g12.get():
            parameters.append({"name": "G12", "material": self.material.get(), "constants": ["G12"],
                               "lower": 0.4, "upper": 2.5})
        return {"model_inp": self.inp.get(), "experiment": self.unv.get(), "output_dir": self.out.get(),
                "abaqus_command": self.abaqus.get().strip() or "abaqus", "cpus": int(self.cpus.get()),
                "max_new_fe_solves": self.max_new_fe_solves.get().strip(),
                "parameters": parameters, "min_experimental_hz": number(self.min_hz),
                "max_experimental_hz": number(self.max_hz),
                "modal_set": self.modal_set_keys.get(self.modal_set.get()),
                "orientation_candidate_id": self.orientation_ids.get(self.orientation.get())}

    def _save_config(self) -> None:
        path = filedialog.asksaveasfilename(title="Save configuration", defaultextension=".json",
                                            filetypes=[("JSON", "*.json")])
        if path:
            Path(path).write_text(json.dumps(self.config_data(), indent=2), encoding="utf-8")

    # ------------------------------------------------------------------ run
    def _config(self):
        data = self.config_data()
        if not (data["model_inp"] and data["experiment"] and data["output_dir"] and data["parameters"][0]["material"]):
            raise QuickCalibrationError("choose the INP, the UNV/UFF file, the output folder and the material.")
        return data, config_from_dict(data)

    def check_inputs(self) -> None:
        """The input preflight only: no Abaqus solve, nothing written."""
        if self.worker is not None and self.worker.is_alive():
            return
        try:
            _, config = self._config()
        except (QuickCalibrationError, ValueError) as error:
            self.readiness.set(f"NOT READY: {error}")
            return
        self.readiness.set("Checking the inputs (no Abaqus run)...")

        def work():
            try:
                self.messages.put(("preflight", preflight(config)))
            except Exception as error:  # noqa: BLE001 - shown, never swallowed
                self.messages.put(("failed", error))
            self.messages.put(("idle", None))

        self._launch(work)

    def running(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def _launch(self, work, stoppable: bool = False) -> None:
        self.run_button.configure(state="disabled")
        self.check_button.configure(state="disabled")
        if stoppable:
            self.stop_button.configure(state="normal")
        if self.threaded:
            self.worker = threading.Thread(target=work, daemon=True)
            self.worker.start()
            self.root.after(100, self._poll)
        else:
            work()
            self._poll(reschedule=False)

    def start(self) -> None:
        if self.running() or self.closing:
            return
        if not self._unconfirmed_resolved("NOT STARTED", "start a new run"):
            return
        try:
            data, config = self._config()
        except (QuickCalibrationError, ValueError) as error:
            messagebox.showerror(TITLE, str(error), parent=self.root)
            return
        self.cancel_event = cancel = threading.Event()
        solve, extract = self.solve, self.extract
        if solve is None or extract is None:
            runner = self.runner_factory(config, cancel)
            solve, extract = solve or runner.solve, extract or runner.extract
        self.summary.set("Checking the inputs, then running... (Abaqus solves can take minutes each)")
        self._write(f"\n=== run: {config.output_dir}\n")

        def work():
            try:
                report = preflight(config)
                self.messages.put(("preflight", report))  # shown before any solve
                if not report.ready:
                    raise PreflightRefused(report)  # nothing is written, nothing is solved
                Path(config.output_dir).mkdir(parents=True, exist_ok=True)
                (Path(config.output_dir) / "config.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
                result, paths = run_quick_calibration(config, solve, extract,
                                                      lambda message: self.messages.put(("log", message)),
                                                      cancel=cancel)
                self.messages.put(("done", (result, paths)))
            except CalibrationCancelled as error:
                self.messages.put(("cancelled", error))
            except TerminationUnconfirmed as error:
                self.messages.put(("unconfirmed", error))
            except QuickCalibrationError as error:
                self.messages.put(("stopped", error))
            except Exception as error:  # noqa: BLE001 - shown to the user, never swallowed
                self.messages.put(("failed", error))

        self._launch(work, stoppable=True)

    def stop(self) -> None:
        """Ask the run to stop; STOPPED is shown only after the owned processes are confirmed terminated."""
        if not self.running():
            return
        self.cancel_event.set()
        self.stop_button.configure(state="disabled")
        self.summary.set("STOPPING: waiting until the owned Abaqus processes are confirmed terminated...")
        self._write("\nStop requested: terminating the owned Abaqus processes...\n")

    def close(self) -> None:
        """WM_DELETE_WINDOW: close only when no owned Abaqus process can be left behind."""
        if self.running():
            self.closing = True
            self.stop()
            self.summary.set("CLOSING: stopping the run first; the window closes once the owned Abaqus processes "
                             "are confirmed terminated.")
            return
        if not self._unconfirmed_resolved("NOT CLOSED", "close the window"):
            self.closing = False
            return
        self.destroyed = True
        self.root.destroy()

    def _unconfirmed_resolved(self, refusal: str, action: str) -> bool:
        """True when no owned process of an unconfirmed stop can still run: confirmed gone by the tracker, or
        explicitly confirmed by the user after checking Task Manager. An unknown state is never 'stopped'."""
        if self.unconfirmed is None:
            return True
        remaining = self.unconfirmed.still_running()
        if remaining == []:
            self._write("\nThe owned Abaqus processes of the stopped run are now confirmed gone.\n")
            self.unconfirmed = None
            return True
        detail = ("their state is UNKNOWN (no process tracker could confirm them)" if remaining is None else
                  f"{len(remaining)} may still run: " + ", ".join(f"PID {identity.pid}" for identity in remaining))
        self.summary.set(f"{refusal}: owned Abaqus processes of the stopped run were not confirmed terminated; "
                         f"{detail}. Check Task Manager.")
        if messagebox.askyesno(
                TITLE, f"The termination of this run's Abaqus processes could not be confirmed ({detail}).\n\n"
                       "Open Task Manager and end any remaining Abaqus processes of this run first.\n\n"
                       f"Have you verified that none is still running? Yes lets you {action}.",
                icon="warning", default="no", parent=self.root):
            self._write(f"\nThe user confirmed after checking Task Manager that no process of the stopped run is "
                        f"still running ({detail}).\n")
            self.unconfirmed = None
            return True
        return False

    def _poll(self, reschedule: bool = True) -> None:
        finished = False
        while True:
            try:
                kind, payload = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._write(f"  {payload}\n")
            elif kind == "modal_sets":
                self._apply_modal_sets(*payload)
            elif kind == "preflight":
                self._show_preflight(payload)
            elif kind == "idle":
                finished = True
            elif kind == "done":
                self.result, self.paths = payload
                self.summary.set(summary_text(self.result))
                self._write("\n" + Path(self.paths["report"]).read_text(encoding="utf-8"))
                self.open_button.configure(state="normal")
                finished = True
            elif kind == "stopped":
                finished = True
                self._stopped(payload)
            elif kind == "cancelled":
                finished = True
                self.summary.set(f"STOPPED by the user: {payload}")
                self._write(f"\nSTOPPED: {payload}\n")
            elif kind == "unconfirmed":
                finished = True
                self.unconfirmed = payload
                self.summary.set(f"STOP NOT CONFIRMED: {payload}")
                self._write(f"\nSTOP NOT CONFIRMED: {payload}\n")
            elif kind == "failed":
                finished = True
                self.summary.set(f"FAILED: {payload}")
                self._write(f"\nFAILED: {type(payload).__name__}: {payload}\n")
        if finished:
            self.run_button.configure(state="normal")
            self.check_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            if self.closing:
                self.closing = False
                self.close()  # closes only if nothing owned can be left running
        elif reschedule:
            self.root.after(200, self._poll)

    def _poll_idle(self) -> None:
        """Deliver background modal-set discovery while no run or check is active."""
        if self.worker is not None and self.worker.is_alive():
            return  # the active worker's polling delivers the messages
        self._poll(reschedule=False)
        if self.modal_set.get() == READING_MODAL_SETS:
            self.root.after(100, self._poll_idle)

    def _stopped(self, error: QuickCalibrationError) -> None:
        self.summary.set(f"STOPPED: {error}")
        self._write(f"\nSTOPPED: {error}\n")
        if isinstance(error, PreflightRefused):
            self.summary.set("NOT READY: no Abaqus solve was started; see Input readiness.")
            return
        if error.candidates:
            self.readiness.set(f"Physical orientation AMBIGUOUS ({len(error.candidates)} geometry candidates): the run "
                               "stopped after the baseline solve, before any optimisation step.")
            self.readiness_table.insert("", "end", values=(
                "Physical orientation", "REFUSED",
                f"{len(error.candidates)} equally plausible orientations from geometry alone; choose one in "
                "'Scan orientation' from the photograph / corner marker (never from MAC)"))
            self.orientation_ids = {describe_orientation(c) + f"   [{c['candidate_id']}]": c["candidate_id"]
                                    for c in error.candidates}
            self.orientation_box["values"] = list(self.orientation_ids)
            self.orientation.set("")
            self.summary.set("Orientation is ambiguous: choose it in 'Scan orientation' from the photograph / corner "
                             "marker of the scan (never from MAC), then press Run again.")

    def _write(self, text: str) -> None:
        self.log.insert("end", text)
        self.log.see("end")

    def _open_output(self) -> None:
        folder = self.out.get()
        if not folder:
            return
        if os.name == "nt":
            os.startfile(folder)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", folder])


def main() -> None:
    from application_layers import install_application_layers

    install_application_layers()
    try:
        from ui_workflow import enable_windows_dpi_awareness

        enable_windows_dpi_awareness()
    except Exception:  # noqa: BLE001 - cosmetic
        pass
    root = tk.Tk()
    root.geometry("1100x760")
    QuickCalibrationWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
