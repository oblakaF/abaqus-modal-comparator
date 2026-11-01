"""PRIORITY-10: a SYNTHETIC_TEST FE family of another plate (420 × 260 mm) for the FE Response Workbench.

It writes, into a folder the user names (never the repository), extracted FE packages in the pinned extractor's
format 2 (manifest.json, geometry.csv, mode_NNNN.csv), one minimal INP per state and the family declaration
``fe_family.json``: a baseline and six ±5 % states of E1, E2 and G12 around E1 = 45 000, E2 = 30 000, G12 = 4 000 MPa.

The frequencies follow exact power laws, so the central sensitivities equal the exponents. The family has, on
purpose, what the M11 family has:

- a crossing pair (FE10 / FE11) whose frequency order swaps in E1 +5 % and E2 −5 % (an exchange caught by tracking);
- a degenerate pair (FE12 / FE13) whose shapes rotate inside their subspace in every state (a confirmed cluster);
- a branch (FE14) whose shape mixes with a shape that is no mode in E1 +5 % (a branch loss).

Every package is labelled SYNTHETIC_TEST: never a physical plate or a solved model. ``--without G12_MINUS`` leaves a
state out (an incomplete family); ``--other-geometry STATE`` moves the nodes of a state (an incompatible package).

Usage: python research/plate_fe_response/make_synthetic_family.py <out folder> [--without STATE] [--other-geometry STATE]
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

LABEL = "SYNTHETIC_TEST"
PLAN_MM = (420.0, 260.0)
GRID = (15, 10)
BASELINE = {"E1": 45000.0, "E2": 30000.0, "G12": 4000.0}
# mode: (f0 Hz, exponents E1, E2, G12)
MODES = {7: (25.0, (0.01, 0.01, 0.48)), 8: (60.0, (0.5, 0.0, 0.0)), 9: (75.0, (0.0, 0.5, 0.0)),
         10: (100.0, (0.45, 0.05, 0.10)), 11: (101.0, (0.05, 0.45, 0.10)), 12: (150.0, (0.25, 0.25, 0.05)),
         13: (150.4, (0.25, 0.25, 0.05)), 14: (200.0, (0.30, 0.20, 0.10))}
STATES = {"BASELINE": {}, "E1_MINUS": {"E1": 0.95}, "E1_PLUS": {"E1": 1.05}, "E2_MINUS": {"E2": 0.95},
          "E2_PLUS": {"E2": 1.05}, "G12_MINUS": {"G12": 0.95}, "G12_PLUS": {"G12": 1.05}}
CLUSTER_TURN_DEG = 35.0  # FE12 / FE13 turn inside their subspace in every state
LOSS = ("E1_PLUS", 14, 40.0)  # FE14 mixes with a non-mode shape by 40° in E1 +5 %


def nodes(shift_mm: float = 0.0) -> list:
    nx, ny = GRID
    return [(j * nx + i + 1, PLAN_MM[0] * i / (nx - 1) + shift_mm, PLAN_MM[1] * j / (ny - 1), 0.0)
            for j in range(ny) for i in range(nx)]


def _shapes(points) -> dict:
    xy = np.array([(x, y) for _n, x, y, _z in points])
    x, y = (xy[:, 0] - xy[:, 0].min()) / PLAN_MM[0], (xy[:, 1] - xy[:, 1].min()) / PLAN_MM[1]
    zero, one = np.zeros(len(points)), np.ones(len(points))
    X, Y = (xy[:, 0] - xy[:, 0].mean()) / 1000.0, (xy[:, 1] - xy[:, 1].mean()) / 1000.0  # physical (m): rigid motions
    rigid = [(one, zero, zero), (zero, one, zero), (zero, zero, one), (zero, zero, Y), (zero, zero, -X),
             (-Y, X, zero)]
    w = {7: (x - 0.5) * (y - 0.5) * 4.0, 8: np.cos(2 * np.pi * x), 9: np.cos(2 * np.pi * y),
         10: np.sin(2 * np.pi * x) * np.sin(np.pi * y), 11: np.sin(np.pi * x) * np.sin(2 * np.pi * y),
         12: np.cos(3 * np.pi * x) * np.cos(np.pi * y), 13: np.cos(np.pi * x) * np.cos(3 * np.pi * y),
         14: np.cos(3 * np.pi * x) * np.cos(3 * np.pi * y)}
    other = np.sin(3 * np.pi * x) * np.sin(2 * np.pi * y)  # a shape that is no mode of the family
    return {"rigid": [np.column_stack(u) for u in rigid], "elastic": w, "other": other, "zero": zero}


def state_modes(state: str, points, states=None) -> list:
    """[(number, Hz, U (N × 3))] of one state, the elastic modes numbered by frequency (as an extraction is)."""
    shapes = _shapes(points)
    ratios = {p: (states or STATES)[state].get(p, 1.0) for p in BASELINE}
    elastic = []
    turn = math.radians(CLUSTER_TURN_DEG) if state != "BASELINE" else 0.0
    for mode, (f0, a) in MODES.items():
        f = f0 * math.prod(ratios[p] ** e for p, e in zip(("E1", "E2", "G12"), a))
        w = shapes["elastic"][mode]
        if mode in (12, 13) and turn:
            a12, a13 = shapes["elastic"][12], shapes["elastic"][13]
            w = (math.cos(turn) * a12 + math.sin(turn) * a13) if mode == 12 else (-math.sin(turn) * a12
                                                                                  + math.cos(turn) * a13)
        if (state, mode) == LOSS[:2]:
            angle = math.radians(LOSS[2])
            w = math.cos(angle) * w + math.sin(angle) * shapes["other"] * np.linalg.norm(w) / np.linalg.norm(
                shapes["other"])
        elastic.append((f, np.column_stack([shapes["zero"], shapes["zero"], w])))
    elastic.sort(key=lambda item: item[0])
    rigid = [(n, 0.0011 * n, u) for n, u in enumerate(shapes["rigid"], 1)]
    return rigid + [(7 + k, f, u) for k, (f, u) in enumerate(elastic)]


def _described(frequency: float) -> str:
    return (f"Mode: Value = {(2 * math.pi * frequency) ** 2:.5E} Freq = {frequency:.6f} (cycles/time)")


def write_package(folder: Path, points, modes, state: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    rows = ["instance,node_label,x,y,z"] + [f"PLATE-1,{n},{x!r},{y!r},{z!r}" for n, x, y, z in points]
    (folder / "geometry.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    entries = []
    for number, frequency, vectors in modes:
        name = f"mode_{number:04d}.csv"
        lines = ["instance,node_label,u1_real,u2_real,u3_real,u1_imag,u2_imag,u3_imag"]
        lines += [f"PLATE-1,{n},{float(u[0])!r},{float(u[1])!r},{float(u[2])!r},0,0,0"
                  for (n, *_), u in zip(points, vectors)]
        (folder / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
        entries.append({"mode": number, "frequency_hz": frequency, "file": name, "frame_index": number,
                        "description": _described(frequency)})
    manifest = {"format_version": 2, "geometry_file": "geometry.csv", "step_name": "Frequency",
                "analysis_title": f"{LABEL}: synthetic plate {PLAN_MM[0]:g} x {PLAN_MM[1]:g} mm, state {state}",
                "odb_path": f"{LABEL}/{state}.odb (none: synthetic)", "start_mode": 1, "end_mode": len(modes),
                "modes": entries}
    path = folder / "manifest.json"
    path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return path


def write_inp(path: Path, values: dict) -> None:
    path.write_text(f"** {LABEL}: a minimal input holding the material of the state (never solved)\n"
                    "*Material, name=SYNTHETIC\n*Density\n 1.5e-09,\n*Elastic, type=ENGINEERING CONSTANTS\n"
                    f"{values['E1']:.1f},{values['E2']:.1f}, 8500., 0.3, 0.3, 0.3,{values['G12']:.1f}, 3000.\n"
                    " 3000.,\n", encoding="ascii")


def write_family(out, without=(), other_geometry=(), ratios=None) -> Path:
    """Write the SYNTHETIC_TEST family into ``out``; returns the declaration ``fe_family.json``. ``ratios`` replaces
    the ratio of a state (for example {"G12_PLUS": {"G12": 1.075}}: an unequal step)."""
    states = {**STATES, **(ratios or {})}
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    variants = []
    for state, change in states.items():
        if state in without:
            continue
        points = nodes(shift_mm=5.0 if state in other_geometry else 0.0)
        folder = out / ("baseline" if state == "BASELINE" else state)
        manifest = write_package(folder / "extraction", points, state_modes(state, points, states), state)
        values = {p: BASELINE[p] * change.get(p, 1.0) for p in BASELINE}
        write_inp(folder / f"{folder.name}.inp", values)
        if change:
            (parameter, ratio), = change.items()
            variants.append({"id": state, "manifest": str(manifest.relative_to(out)), "parameter": parameter,
                             "value": BASELINE[parameter] * ratio, "unit": "MPa",
                             "inp": str((folder / f"{folder.name}.inp").relative_to(out)), "provenance": LABEL})
    declaration = {"schema": "amc/fe-family/v1", "model_id": f"{LABEL}-PLATE-420x260-S4", "specimen_id":
                   f"{LABEL}-PLATE-420x260", "kind": LABEL, "geometry": f"{PLAN_MM[0]:g} x {PLAN_MM[1]:g} mm",
                   "provenance": f"{LABEL}: research/plate_fe_response/make_synthetic_family.py (exact power laws)",
                   "baseline_parameters": BASELINE,
                   "baseline": {"id": "baseline", "manifest": "baseline/extraction/manifest.json",
                                "inp": "baseline/baseline.inp", "provenance": LABEL},
                   "variants": variants}
    path = out / "fe_family.json"
    path.write_text(json.dumps(declaration, indent=1), encoding="utf-8")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--without", action="append", default=[])
    parser.add_argument("--other-geometry", action="append", default=[])
    args = parser.parse_args()
    print(write_family(args.out, args.without, args.other_geometry))
