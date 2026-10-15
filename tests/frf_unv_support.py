"""Synthetic Testlab-like UNV/UFF files without fitted modes: geometry (dataset 15) + dataset-58 FRFs (no Abaqus).

The plate and its modes are those of ``quick_calibration_support``; FRFs H(f) = Σ φ_i(rsp) φ_i(ref) / (f_i² − f² +
2jζ f_i f) are written for the U3 direction of every measured point, with coherence channels.  ``points`` limits the
measured points (two points are not enough for a spatial view).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import numpy as np

import quick_calibration_support as S


def write_frf_only(path: Path, points: Optional[int] = None, coherence: bool = True) -> Path:
    import pyuff

    path = Path(path)
    if path.exists():
        path.unlink()
    xs, ys = np.meshgrid(np.linspace(0.0, S.A_MM, 9), np.linspace(0.0, S.B_MM, 7))
    x, y = xs.ravel(), ys.ravel()
    if points is not None:
        x, y = x[:points], y[:points]
    n = len(x)
    nodes = np.arange(1, n + 1)
    uff = pyuff.UFF(str(path))
    uff.write_sets(pyuff.prepare_15(node_nums=nodes, def_cs=np.zeros(n, dtype=int), disp_cs=np.zeros(n, dtype=int),
                                    color=np.ones(n, dtype=int), x=x / 1000.0, y=y / 1000.0, z=np.zeros(n)), "add")
    axis = np.linspace(1.0, 300.0, 1197)
    frequencies = S.frequencies(S.E0, S.G0)
    reference = 0
    for index in range(n):
        response = np.zeros_like(axis, dtype=complex)
        for (m, nn, *_), f in zip(S.MODES, frequencies):
            phi = S.shape(x, y, m, nn)
            response += phi[index] * (phi[reference] + 0.5) / (f ** 2 - axis ** 2 + 2j * 0.004 * f * axis)
        common = dict(id1="Transfer Function H1", id3="x", id4="x", id5="x", rsp_ent_name="pt", ref_ent_name="pt",
                      rsp_node=int(nodes[index]), rsp_dir=3, ref_node=int(nodes[reference]), ref_dir=3,
                      abscissa_spacing=1, abscissa_spec_data_type=18, x=axis)
        uff.write_sets(pyuff.prepare_58(func_type=4, id2="H1 Displacement / Force", ord_data_type=6, data=response,
                                        ordinate_spec_data_type=8, orddenom_spec_data_type=13, **common), "add")
        if coherence:
            uff.write_sets(pyuff.prepare_58(func_type=6, id2="Coherence", ord_data_type=4,
                                            data=np.full_like(axis, 0.97), ordinate_spec_data_type=0,
                                            orddenom_spec_data_type=0, **common), "add")
    return path


def peak_count() -> int:
    return len(S.MODES)


if __name__ == "__main__":  # quick manual check
    import sys
    import tempfile

    sys.path.insert(0, str(S.ROOT / "src"))
    from application_layers import install_application_layers

    install_application_layers()
    from universal_reader import load_universal_modal_file

    with tempfile.TemporaryDirectory() as folder:
        data = load_universal_modal_file(write_frf_only(Path(folder) / "frf.uff"))
        print(data.source_name, data.metadata.get("mode_source"), [round(m.frequency_hz, 2) for m in data.modes],
              math.isfinite(data.modes[0].frequency_hz))
