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
    QuickCalibrationError,
    STATUS_ESTIMATE,
    config_from_dict,
    describe_orientation,
    locate_elastic,
    run_quick_calibration,
)

TITLE = "Quick material calibration (Abaqus + Polytec)"
DEFAULT_CONSTANTS = {"ENGINEERING CONSTANTS": "E1,E2", "LAMINA": "E1,E2", "ISOTROPIC": "E"}


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
                 threaded: bool = True) -> None:
        self.root, self.solve, self.extract, self.threaded = root, solve, extract, threaded
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
        self.material = tk.StringVar(master=root)
        self.constants = tk.StringVar(master=root, value="E1,E2")
        self.fit_g12 = tk.BooleanVar(master=root, value=False)
        self.lower = tk.StringVar(master=root, value="0.5")
        self.upper = tk.StringVar(master=root, value="2.0")
        self.min_hz = tk.StringVar(master=root)
        self.max_hz = tk.StringVar(master=root)
        self.orientation = tk.StringVar(master=root, value="automatic (geometry)")
        self.summary = tk.StringVar(master=root, value="Choose the files and press Run.")
        self._build()
        self._detect_abaqus()

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
        file_row("Output folder", self.out, self._browse_out)

        ttk.Label(frame, text="Abaqus command").grid(row=row, column=0, sticky="w", pady=2)
        self.abaqus_box = ttk.Combobox(frame, textvariable=self.abaqus)
        self.abaqus_box.grid(row=row, column=1, sticky="ew", padx=4)
        cpu_frame = ttk.Frame(frame)
        cpu_frame.grid(row=row, column=2, sticky="ew")
        ttk.Label(cpu_frame, text="CPUs").pack(side="left")
        ttk.Spinbox(cpu_frame, from_=1, to=64, width=4, textvariable=self.cpus).pack(side="left", padx=4)
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
        self.run_button = ttk.Button(buttons, text="Run calibration", command=self.start)
        self.run_button.pack(side="left")
        self.open_button = ttk.Button(buttons, text="Open output folder", command=self._open_output,
                                      state="disabled")
        self.open_button.pack(side="left", padx=6)
        ttk.Button(buttons, text="Save configuration...", command=self._save_config).pack(side="left")
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
                "parameters": parameters, "min_experimental_hz": number(self.min_hz),
                "max_experimental_hz": number(self.max_hz),
                "orientation_candidate_id": self.orientation_ids.get(self.orientation.get())}

    def _save_config(self) -> None:
        path = filedialog.asksaveasfilename(title="Save configuration", defaultextension=".json",
                                            filetypes=[("JSON", "*.json")])
        if path:
            Path(path).write_text(json.dumps(self.config_data(), indent=2), encoding="utf-8")

    # ------------------------------------------------------------------ run
    def start(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            return
        try:
            data = self.config_data()
            if not (data["model_inp"] and data["experiment"] and data["output_dir"] and data["parameters"][0]["material"]):
                raise QuickCalibrationError("choose the INP, the UNV/UFF file, the output folder and the material.")
            config = config_from_dict(data)
        except (QuickCalibrationError, ValueError) as error:
            messagebox.showerror(TITLE, str(error), parent=self.root)
            return
        Path(config.output_dir).mkdir(parents=True, exist_ok=True)
        (Path(config.output_dir) / "config.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.run_button.configure(state="disabled")
        self.summary.set("Running... (Abaqus solves can take minutes each)")
        self._write(f"\n=== run: {config.output_dir}\n")

        def work():
            try:
                result, paths = run_quick_calibration(config, self.solve, self.extract,
                                                      lambda message: self.messages.put(("log", message)))
                self.messages.put(("done", (result, paths)))
            except QuickCalibrationError as error:
                self.messages.put(("stopped", error))
            except Exception as error:  # noqa: BLE001 - shown to the user, never swallowed
                self.messages.put(("failed", error))

        if self.threaded:
            self.worker = threading.Thread(target=work, daemon=True)
            self.worker.start()
            self.root.after(100, self._poll)
        else:
            work()
            self._poll(reschedule=False)

    def _poll(self, reschedule: bool = True) -> None:
        finished = False
        while True:
            try:
                kind, payload = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._write(f"  {payload}\n")
            elif kind == "done":
                self.result, self.paths = payload
                self.summary.set(summary_text(self.result))
                self._write("\n" + Path(self.paths["report"]).read_text(encoding="utf-8"))
                self.open_button.configure(state="normal")
                finished = True
            elif kind == "stopped":
                finished = True
                self._stopped(payload)
            elif kind == "failed":
                finished = True
                self.summary.set(f"FAILED: {payload}")
                self._write(f"\nFAILED: {type(payload).__name__}: {payload}\n")
        if finished:
            self.run_button.configure(state="normal")
        elif reschedule:
            self.root.after(200, self._poll)

    def _stopped(self, error: QuickCalibrationError) -> None:
        self.summary.set(f"STOPPED: {error}")
        self._write(f"\nSTOPPED: {error}\n")
        if error.candidates:
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
