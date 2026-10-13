"""Synthetic plate, fake Abaqus and a PolyMAX-like UNV writer for the quick-calibration tests (no Abaqus)."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modal_core import ModalDataset, ModeShape  # noqa: E402
from services.forward_builder import split_inp_lines  # noqa: E402
from services.quick_calibration import locate_elastic  # noqa: E402

A_MM, B_MM = 500.0, 400.0
E0, G0 = 52000.0, 4500.0
# (m, n, c_Hz, exponent of E1, exponent of G12): f = c · (E/E0)^a · (G/G0)^b.  Mode 3 is G12-sensitive.
MODES = [(2, 0, 70.0, 0.48, 0.02), (0, 2, 95.0, 0.47, 0.03), (1, 1, 60.0, 0.20, 0.30),
         (2, 1, 140.0, 0.40, 0.10), (1, 2, 165.0, 0.38, 0.12), (2, 2, 230.0, 0.42, 0.08)]

INP = """*Heading
** synthetic sandwich stand-in
*Node
1, 0., 0., 0.
*Material, name=CFRP_Face
*Density
1.5e-09,
*Elastic, type=ENGINEERING CONSTANTS
52000., 52000., 6700., 0.05, 0.3, 0.3, 4500., 2200.,
2200.,
*Material, name=PLA_core
*Density
1.24e-09,
*Elastic
3000., 0.35
*Step, name=modal
*Frequency, eigensolver=Lanczos, normalization=displacement
30, , , , ,
*End Step
"""


def shape(x, y, m, n):
    return np.cos(m * math.pi * x / A_MM) * np.cos(n * math.pi * y / B_MM)


def frequencies(e: float, g: float, scale=None) -> list[float]:
    scale = scale or [1.0] * len(MODES)
    return [c * (e / E0) ** a * (g / G0) ** b * s for (_, _, c, a, b), s in zip(MODES, scale)]


def fe_grid():
    xs, ys = np.meshgrid(np.linspace(0.0, A_MM, 26), np.linspace(0.0, B_MM, 21))
    return xs.ravel(), ys.ravel()


class FakeAbaqus:
    """``solve`` reads the constants from the written INP; ``extract`` returns Abaqus-like sorted modes."""

    def __init__(self, mixing=None, layers: int = 1) -> None:
        self.solves = 0
        self.mixing = mixing  # optional callable e -> angle mixing modes 1 and 2 (branch-loss test)
        self.layers = layers  # >1: extra node layers below the scanned surface (a solid sandwich stand-in)

    def solve(self, inp_path: Path, job_dir: Path, job_name: str) -> Path:
        self.solves += 1
        lines = split_inp_lines(Path(inp_path).read_bytes())
        face = locate_elastic(lines, "CFRP_Face")
        odb = Path(job_dir) / f"{job_name}.odb"
        odb.write_text(json.dumps({"E1": face.value("E1"), "E2": face.value("E2"), "G12": face.value("G12")}))
        return odb

    def extract(self, odb_path: Path, output_dir: Path, last_mode: int) -> ModalDataset:
        state = json.loads(Path(odb_path).read_text())
        e, g = state["E1"], state["G12"]
        x, y = fe_grid()
        ids = np.array([f"PLATE-1.{i + 1}" for i in range(len(x))], dtype=object)
        coordinates = np.column_stack([x, y, np.zeros_like(x)])
        shapes = [shape(x, y, m, n) for m, n, *_ in MODES]
        if self.mixing is not None:
            angle = self.mixing(e)
            s0, s1 = shapes[0], shapes[1]
            shapes[0], shapes[1] = math.cos(angle) * s0 + math.sin(angle) * s1, -math.sin(angle) * s0 + math.cos(angle) * s1
        rigid = [(0.001, np.ones_like(x)), (0.002, x - x.mean()), (0.003, y - y.mean())]
        elastic = list(zip(frequencies(e, g), shapes))
        modes = []
        count = len(x)
        if self.layers > 1:  # deeper layers at z = -5 mm, -10 mm ... with the same U3 (bending)
            ids = np.array([f"PLATE-1.{i + 1}" for i in range(count * self.layers)], dtype=object)
            coordinates = np.vstack([np.column_stack([x, y, np.full(count, -5.0 * layer)])
                                     for layer in range(self.layers)])
        for number, (frequency, values) in enumerate(sorted(rigid + elastic, key=lambda item: item[0]), start=1):
            vectors = np.zeros((count * self.layers, 3))
            vectors[:, 2] = np.tile(values, self.layers)
            modes.append(ModeShape(number, frequency, ids, coordinates, vectors))
        return ModalDataset("fake ODB", Path(odb_path), modes[:last_mode])


def write_experiment(path: Path, e: float, g: float, scale=None, noise=0.0, seed=0, sets=None) -> Path:
    """PolyMAX-like dataset 15 + 55 (complex shapes, small damping), coordinates in metres, U3 only.

    ``sets``: optional ((processing name, number of modes), ...) to write several dataset-55 modal sets (the lowest
    modes of each); by default one set named "PolyMAX" with every mode.
    """
    import pyuff

    rng = np.random.default_rng(seed)
    path = Path(path)
    if path.exists():
        path.unlink()
    xs, ys = np.meshgrid(np.linspace(0.0, A_MM, 9), np.linspace(0.0, B_MM, 7))
    x, y = xs.ravel(), ys.ravel()
    n = len(x)
    nodes = np.arange(1, n + 1)
    uff = pyuff.UFF(str(path))
    uff.write_sets(pyuff.prepare_15(node_nums=nodes, def_cs=np.zeros(n, dtype=int), disp_cs=np.zeros(n, dtype=int),
                                    color=np.ones(n, dtype=int), x=x / 1000.0, y=y / 1000.0, z=np.zeros(n)), "add")
    order = np.argsort(frequencies(e, g, scale))
    freqs = frequencies(e, g, scale)
    for name, count in sets or (("PolyMAX", len(MODES)),):
        for k, index in enumerate(order[:count]):
            m, nn = MODES[index][:2]
            f = freqs[index] * math.exp(noise * rng.standard_normal())
            zeta = 0.003
            w = 2 * math.pi * f / math.sqrt(1 - zeta ** 2)
            lam = -zeta * w + 1j * w * math.sqrt(1 - zeta ** 2)
            values = shape(x, y, m, nn) * np.exp(1j * 0.3)
            data = pyuff.prepare_55(id1=name, id2="synthetic", id3="x", id4="x", id5="x", model_type=1,
                                    analysis_type=3, data_ch=2, spec_data_type=11, data_type=5, n_data_per_node=3,
                                    load_case=1, mode_n=k + 1, eig=lam, modal_a=1 + 0j, modal_b=1 + 0j,
                                    node_nums=nodes, r1=np.zeros(n, complex), r2=np.zeros(n, complex), r3=values,
                                    return_full_dict=True)
            uff.write_sets(data, "add")
    text = path.read_text()
    path.write_text(text.replace("        11         5         6", "        11         5         3"))
    return path
