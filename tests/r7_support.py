"""R7 test support: FE input (INP) text generated from a synthetic FE geometry (not a test module)."""

from __future__ import annotations

import numpy as np

from services import shell_surface


def synthetic_inp_text(fe, instance: str = "TOP", element_type: str = "C3D8", normal: str = "+Z",
                       shift: float = 0.0, rotated: bool = False) -> str:
    """One part holding ``instance``'s nodes (labels and coordinates of the FE geometry) and its elements.

    Conventional shells get one quadrilateral per grid cell, ordered so that the connectivity normal is ``normal``;
    other element types get a single element (only the type is read). ``shift`` moves every node (a model mismatch).
    """
    selected = [k for k, value in enumerate(fe.node_ids) if str(value).split(":")[0] == instance]
    labels = [int(str(fe.node_ids[k]).split(":")[1]) for k in selected]
    points = fe.coordinates[selected] + np.array([shift, 0.0, 0.0])
    lines = ["*Heading", f"*Part, name={instance}_PART", "*Node"]
    lines += [f"{label}, {float(x)!r}, {float(y)!r}, {float(z)!r}" for label, (x, y, z) in zip(labels, points)]
    lines.append(f"*Element, type={element_type}")
    if shell_surface.is_conventional_shell(element_type):
        xs, ys = np.unique(points[:, 0]), np.unique(points[:, 1])
        index = {(round(x, 9), round(y, 9)): label for label, (x, y, _) in zip(labels, points)}
        element = 1
        for i in range(len(xs) - 1):
            for j in range(len(ys) - 1):
                corners = [(xs[i], ys[j]), (xs[i + 1], ys[j]), (xs[i + 1], ys[j + 1]), (xs[i], ys[j + 1])]
                if normal == "-Z":
                    corners = corners[::-1]
                ids = [index[(round(x, 9), round(y, 9))] for x, y in corners]
                lines.append(f"{element}, " + ", ".join(str(item) for item in ids))
                element += 1
    else:
        lines.append("1, " + ", ".join(str(item) for item in labels[:8]))
    lines += ["*End Part", "*Assembly, name=Assembly", f"*Instance, name={instance}, part={instance}_PART"]
    if rotated:
        lines += ["0., 0., 0.", "0., 0., 0., 0., 0., 1., 90."]
    lines += ["*End Instance", "*End Assembly"]
    return "\n".join(lines) + "\n"


def synthetic_fe_input(fe, instance: str = "TOP", **options) -> shell_surface.FEInputModel:
    return shell_surface.parse_fe_input(synthetic_inp_text(fe, instance, **options), file_name="synthetic.inp")
