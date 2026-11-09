"""ABM-SOLID-3: read-only import of an Abaqus solid C3D8I modal INP.

Supported (everything else is refused with a reason, never ignored):

* ``*Heading``, ``*Preprint`` (output control only);
* one ``*Part`` with ``*Node`` and ``*Element, type=C3D8I``, or the same
  definitions at top level in a flat input file;
* ``*Nset`` / ``*Elset`` (list or ``generate``);
* ``*Orientation`` with ``system=RECTANGULAR`` and ``definition=COORDINATES``
  (points a, b, optional origin c, optional extra rotation about a local axis);
* exactly one ``*Solid Section`` (one material, optional orientation) that
  covers every element;
* ``*Assembly`` with exactly one ``*Instance`` of that part, including the
  optional translation and rotation data lines;
* one ``*Material`` with ``*Density`` (one constant value) and
  ``*Elastic, type=ENGINEERING CONSTANTS`` (nine constant values);
* one perturbation ``*Step`` with ``*Frequency`` plus output requests.

No ``*Boundary`` or any other constraint is accepted: the model is free-free.
The file is opened read-only and never written.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import math
from pathlib import Path
from typing import Iterable

import numpy as np

from .solid_c3d8i_forward import (
    ABAQUS_EQUIVALENCE,
    FORMULATION_C3D8I_REFERENCE,
    OrthotropicEngineeringConstants,
    SolidElementError,
    formulation_for_abaqus_element,
    material_axes,
)

SUPPORTED_ELEMENT_TYPE = "C3D8I"
STEP_OUTPUT_KEYWORDS = {"restart", "output", "node output", "element output", "energy output",
                        "contact output", "monitor", "node print", "el print", "energy print"}


class SolidInpNotSupported(SolidElementError):
    """The INP uses something this importer does not model."""


@dataclass(frozen=True)
class SolidModel:
    """A free-free C3D8I model in global (assembly) coordinates."""

    source_path: str
    source_sha256: str
    part_name: str | None
    instance_name: str | None
    node_labels: np.ndarray        # (n,) int, ascending
    coordinates: np.ndarray        # (n, 3) global coordinates after the instance transform
    element_labels: np.ndarray     # (e,) int
    connectivity: np.ndarray       # (e, 8) indices into node_labels, Abaqus C3D8 order
    material_name: str
    material: OrthotropicEngineeringConstants
    density: float
    material_axes: np.ndarray      # rows: material axes 1, 2, 3 in global coordinates
    orientation_name: str | None
    requested_eigenvalues: int | None
    frequency_parameters: dict
    formulation: str = FORMULATION_C3D8I_REFERENCE
    abaqus_equivalence: str = ABAQUS_EQUIVALENCE

    @property
    def dof_count(self) -> int:
        return 3 * len(self.node_labels)

    @property
    def odb_instance_name(self) -> str | None:
        """Abaqus writes instance names upper-case in the ODB."""
        return self.instance_name.upper() if self.instance_name else None

    def dof_identity(self) -> list[tuple[str | None, int, int]]:
        """(instance, node label, component 1..3) for every global DOF, in order."""
        inst = self.odb_instance_name
        return [(inst, int(label), comp) for label in self.node_labels for comp in (1, 2, 3)]

    def with_in_plane_constants(self, *, e1: float | None = None, e2: float | None = None,
                                g12: float | None = None) -> OrthotropicEngineeringConstants:
        """E1, E2, G12 changed, every other constant held at the INP value; validated."""
        return vary_in_plane(self.material, e1=e1, e2=e2, g12=g12)


def vary_in_plane(material: OrthotropicEngineeringConstants, *, e1=None, e2=None, g12=None
                  ) -> OrthotropicEngineeringConstants:
    changes = {k: float(v) for k, v in (("e1", e1), ("e2", e2), ("g12", g12)) if v is not None}
    return replace(material, **changes)  # __post_init__ re-checks positive definiteness


# --------------------------------------------------------------------------- parsing


def _keyword(line: str) -> tuple[str, dict[str, str]]:
    parts = [p.strip() for p in line[1:].split(",")]
    name = " ".join(parts[0].lower().split())
    params: dict[str, str] = {}
    for item in parts[1:]:
        if not item:
            continue
        key, _, value = item.partition("=")
        params[" ".join(key.lower().split())] = value.strip()
    return name, params


def _blocks(text: str) -> list[tuple[int, str, dict[str, str], list[str]]]:
    blocks = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("**"):
            continue
        if line.startswith("*"):
            name, params = _keyword(line)
            blocks.append((number, name, params, []))
        elif blocks:
            blocks[-1][3].append(line)
        else:
            raise SolidInpNotSupported(f"Line {number}: data before the first keyword.")
    return blocks


def _fields(lines: Iterable[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        items = [f.strip() for f in line.split(",")]
        if items and items[-1] == "":
            items = items[:-1]
        out.extend(items)
    return out


def _floats(values: list[str], where: str) -> list[float]:
    try:
        result = [float(v) for v in values]
    except ValueError as exc:
        raise SolidInpNotSupported(f"{where}: non-numeric value.") from exc
    if not all(math.isfinite(v) for v in result):
        raise SolidInpNotSupported(f"{where}: non-finite value.")
    return result


def _ints(values: list[str], where: str) -> list[int]:
    try:
        return [int(v) for v in values]
    except ValueError as exc:
        raise SolidInpNotSupported(f"{where}: non-integer value.") from exc


def _set_members(params: dict, lines: list[str], where: str, sets: dict) -> list[int]:
    if "generate" in params:
        members: list[int] = []
        for line in lines:
            vals = _ints(_fields([line]), where)
            if len(vals) not in (2, 3):
                raise SolidInpNotSupported(f"{where}: generate needs start, end[, step].")
            start, end, step = vals[0], vals[1], vals[2] if len(vals) == 3 else 1
            if step <= 0 or end < start:
                raise SolidInpNotSupported(f"{where}: invalid generate range.")
            members.extend(range(start, end + 1, step))
        return members
    members = []
    for item in _fields(lines):
        if item.lstrip("-").isdigit():
            members.append(int(item))
        elif item.lower() in sets:
            members.extend(sets[item.lower()])
        else:
            raise SolidInpNotSupported(f"{where}: unknown set member {item!r}.")
    return members


def _rotation_about(axis: np.ndarray, angle_deg: float) -> np.ndarray:
    axis = np.asarray(axis, float)
    norm = np.linalg.norm(axis)
    if norm == 0.0:
        raise SolidInpNotSupported("Rotation axis has zero length.")
    k = axis / norm
    kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    a = math.radians(angle_deg)
    return np.eye(3) + math.sin(a) * kx + (1 - math.cos(a)) * kx @ kx


def _orientation_axes(params: dict, lines: list[str], where: str) -> np.ndarray:
    system = params.get("system", "RECTANGULAR").upper()
    definition = params.get("definition", "COORDINATES").upper()
    if system != "RECTANGULAR" or definition != "COORDINATES":
        raise SolidInpNotSupported(f"{where}: only SYSTEM=RECTANGULAR, DEFINITION=COORDINATES "
                                   f"orientations are supported (got {system}, {definition}).")
    unknown = set(params) - {"name", "system", "definition"}
    if unknown:
        raise SolidInpNotSupported(f"{where}: unsupported orientation parameters {sorted(unknown)}.")
    if not lines or len(lines) > 2:
        raise SolidInpNotSupported(f"{where}: expected one or two data lines.")
    first = _floats(_fields([lines[0]]), where)
    if len(first) not in (6, 9):
        raise SolidInpNotSupported(f"{where}: first line needs a, b[, c] coordinates.")
    a, b = np.array(first[0:3]), np.array(first[3:6])
    c = np.array(first[6:9]) if len(first) == 9 else np.zeros(3)
    e1 = a - c
    if np.linalg.norm(e1) == 0.0:
        raise SolidInpNotSupported(f"{where}: point a coincides with the origin.")
    e1 /= np.linalg.norm(e1)
    e3 = np.cross(e1, b - c)
    if np.linalg.norm(e3) == 0.0:
        raise SolidInpNotSupported(f"{where}: points a and b are collinear with the origin.")
    e3 /= np.linalg.norm(e3)
    axes = np.vstack([e1, np.cross(e3, e1), e3])
    if len(lines) == 2:
        extra = _fields([lines[1]])
        local_axis = int(float(extra[0])) if extra and extra[0] else 1
        angle = float(extra[1]) if len(extra) > 1 and extra[1] else 0.0
        if local_axis not in (1, 2, 3):
            raise SolidInpNotSupported(f"{where}: additional rotation axis must be 1, 2 or 3.")
        if angle != 0.0:
            rot = _rotation_about(axes[local_axis - 1], angle)
            axes = axes @ rot.T
    return material_axes(axes)


def load_solid_inp(path: str | Path) -> SolidModel:
    """Read one free-free C3D8I modal model; refuse anything not modelled."""
    path = Path(path)
    raw = path.read_bytes()
    text = raw.decode("latin-1")
    blocks = _blocks(text)

    scope = "top"            # top | part | assembly | instance | step
    material_open = False
    parts: dict[str, dict] = {}
    flat = {"nodes": {}, "elements": {}, "nsets": {}, "elsets": {}, "orientations": {}, "sections": []}
    current = flat
    current_part: str | None = None
    instances: list[dict] = []
    materials: dict[str, dict] = {}
    current_material: str | None = None
    steps: list[dict] = []
    used_part_keywords = False

    for number, name, params, lines in blocks:
        where = f"Line {number} *{name}"
        if name in ("heading", "preprint"):
            continue
        if name == "include":
            raise SolidInpNotSupported(f"{where}: *Include is not followed; give a self-contained INP.")
        if name == "boundary":
            raise SolidInpNotSupported(f"{where}: boundary conditions are not supported; only free-free "
                                       "models can be solved here.")
        if scope == "step":
            if name == "end step":
                scope = "top"
            elif name == "frequency":
                fields = _fields(lines[:1])
                steps[-1]["frequency"] = {"parameters": dict(params), "data": fields}
            elif name in STEP_OUTPUT_KEYWORDS:
                pass  # output requests do not change K, M or the eigenproblem
            else:
                raise SolidInpNotSupported(f"{where}: not supported inside a step.")
            continue
        if name in ("part",):
            if scope != "top":
                raise SolidInpNotSupported(f"{where}: nested *Part.")
            used_part_keywords = True
            current_part = params.get("name", "")
            if current_part.lower() in (p.lower() for p in parts):
                raise SolidInpNotSupported(f"{where}: duplicate part {current_part!r}.")
            current = {"nodes": {}, "elements": {}, "nsets": {}, "elsets": {}, "orientations": {},
                       "sections": []}
            parts[current_part] = current
            scope = "part"
            material_open = False
            continue
        if name == "end part":
            scope, current = "top", flat
            continue
        if name == "assembly":
            scope = "assembly"
            material_open = False
            continue
        if name == "end assembly":
            scope = "top"
            continue
        if name == "instance":
            if scope != "assembly":
                raise SolidInpNotSupported(f"{where}: *Instance outside *Assembly.")
            unknown = set(params) - {"name", "part"}
            if unknown:
                raise SolidInpNotSupported(f"{where}: unsupported instance parameters {sorted(unknown)}.")
            values = [_floats(_fields([ln]), where) for ln in lines]
            if len(values) > 2 or (values and len(values[0]) != 3) or (len(values) == 2 and len(values[1]) != 7):
                raise SolidInpNotSupported(f"{where}: expected translation (3) and optional rotation (7).")
            instances.append({"name": params.get("name"), "part": params.get("part"),
                              "translation": np.array(values[0]) if values else np.zeros(3),
                              "rotation": values[1] if len(values) == 2 else None})
            scope = "instance"
            continue
        if name == "end instance":
            scope = "assembly"
            continue
        if scope == "instance":
            raise SolidInpNotSupported(f"{where}: definitions inside *Instance are not supported.")
        if name == "step":
            if steps:
                raise SolidInpNotSupported(f"{where}: more than one step.")
            steps.append({"parameters": dict(params)})
            scope = "step"
            material_open = False
            continue
        if name == "material":
            if scope != "top":
                raise SolidInpNotSupported(f"{where}: *Material must be at model level.")
            current_material = params.get("name", "")
            materials[current_material] = {}
            material_open = True
            continue
        if material_open and name in ("density", "elastic"):
            mat = materials[current_material]
            if name in mat:
                raise SolidInpNotSupported(f"{where}: repeated *{name.title()}.")
            if name == "density":
                if set(params):
                    raise SolidInpNotSupported(f"{where}: dependent or distributed density is not supported.")
                if len(lines) != 1:
                    raise SolidInpNotSupported(f"{where}: exactly one constant density is required.")
                values = _floats(_fields(lines), where)
                if len(values) != 1:
                    raise SolidInpNotSupported(f"{where}: temperature-dependent density is not supported.")
                mat["density"] = values[0]
            else:
                kind = params.get("type", "ISOTROPIC").upper()
                if kind != "ENGINEERING CONSTANTS" or set(params) - {"type"}:
                    raise SolidInpNotSupported(f"{where}: only *Elastic, type=ENGINEERING CONSTANTS "
                                               f"(constant) is supported, got {kind}.")
                values = _floats(_fields(lines), where)
                if len(values) != 9:
                    raise SolidInpNotSupported(f"{where}: exactly nine constants are required "
                                               "(no temperature or field dependence).")
                mat["elastic"] = values
            continue
        if material_open:
            raise SolidInpNotSupported(f"{where}: material behaviour *{name} is not supported.")
        if scope == "assembly":
            if name in ("nset", "elset"):
                continue  # inert unless referenced, and nothing may reference them here
            raise SolidInpNotSupported(f"{where}: not supported in the assembly.")
        if scope not in ("top", "part"):
            raise SolidInpNotSupported(f"{where}: unexpected position.")
        if scope == "top" and used_part_keywords and name in ("node", "element", "nset", "elset",
                                                               "orientation", "solid section"):
            raise SolidInpNotSupported(f"{where}: mesh definitions outside the part.")
        if name == "node":
            if set(params) - {"nset"}:
                raise SolidInpNotSupported(f"{where}: unsupported *Node parameters.")
            labels = []
            for ln in lines:
                f = _fields([ln])
                if len(f) < 4:
                    raise SolidInpNotSupported(f"{where}: nodes need label and three coordinates.")
                if len(f) > 4:
                    raise SolidInpNotSupported(f"{where}: nodal local systems / extra fields not supported.")
                label = _ints(f[:1], where)[0]
                if label in current["nodes"]:
                    raise SolidInpNotSupported(f"{where}: duplicate node {label}.")
                current["nodes"][label] = _floats(f[1:4], where)
                labels.append(label)
            if "nset" in params:
                current["nsets"].setdefault(params["nset"].lower(), []).extend(labels)
            continue
        if name == "element":
            etype = params.get("type", "").upper()
            if etype != SUPPORTED_ELEMENT_TYPE:
                formulation_for_abaqus_element(etype)  # raises with the standard refusal
            if set(params) - {"type", "elset"}:
                raise SolidInpNotSupported(f"{where}: unsupported *Element parameters.")
            values = _ints(_fields(lines), where)
            if len(values) % 9:
                raise SolidInpNotSupported(f"{where}: C3D8I needs a label and eight nodes per element.")
            labels = []
            for i in range(0, len(values), 9):
                label = values[i]
                if label in current["elements"]:
                    raise SolidInpNotSupported(f"{where}: duplicate element {label}.")
                current["elements"][label] = values[i + 1:i + 9]
                labels.append(label)
            if "elset" in params:
                current["elsets"].setdefault(params["elset"].lower(), []).extend(labels)
            continue
        if name in ("nset", "elset"):
            key = "nsets" if name == "nset" else "elsets"
            set_name = params.get(name, "").lower()
            if set(params) - {name, "generate", "internal"}:
                raise SolidInpNotSupported(f"{where}: unsupported set parameters.")
            current[key].setdefault(set_name, []).extend(_set_members(params, lines, where, current[key]))
            continue
        if name == "orientation":
            current["orientations"][params.get("name", "").lower()] = (
                params.get("name"), _orientation_axes(params, lines, where))
            continue
        if name == "solid section":
            if set(params) - {"elset", "material", "orientation"}:
                raise SolidInpNotSupported(f"{where}: unsupported section parameters "
                                           f"{sorted(set(params) - {'elset', 'material', 'orientation'})}.")
            if any(v for v in _fields(lines)):
                raise SolidInpNotSupported(f"{where}: non-empty section data line is not supported.")
            current["sections"].append(dict(params))
            continue
        raise SolidInpNotSupported(f"{where}: keyword is not supported by the solid importer.")

    # --------------------------------------------------------------- resolve
    if scope != "top":
        raise SolidInpNotSupported("The INP ends inside a part, assembly, instance or step.")
    if used_part_keywords:
        if len(parts) != 1 or len(instances) != 1:
            raise SolidInpNotSupported(f"Exactly one part and one instance are supported "
                                       f"(found {len(parts)} parts, {len(instances)} instances).")
        part_name = next(iter(parts))
        mesh = parts[part_name]
        inst = instances[0]
        if (inst["part"] or "").lower() != part_name.lower():
            raise SolidInpNotSupported("The instance does not refer to the defined part.")
    else:
        if instances:
            raise SolidInpNotSupported("*Instance without *Part.")
        part_name, mesh, inst = None, flat, None
    if not steps or "frequency" not in steps[0]:
        raise SolidInpNotSupported("A *Frequency step is required.")
    if not mesh["nodes"] or not mesh["elements"]:
        raise SolidInpNotSupported("The model has no C3D8I mesh.")
    if len(mesh["sections"]) != 1:
        raise SolidInpNotSupported(f"Exactly one *Solid Section is supported (found {len(mesh['sections'])}).")
    section = mesh["sections"][0]
    members = mesh["elsets"].get(section.get("elset", "").lower())
    if members is None:
        raise SolidInpNotSupported(f"Section element set {section.get('elset')!r} is not defined.")
    if len(set(members)) != len(members) or set(members) != set(mesh["elements"]):
        raise SolidInpNotSupported("The solid section must cover every element exactly once.")
    mat_name = section.get("material", "")
    matched = [m for m in materials if m.lower() == mat_name.lower()]
    if len(materials) != 1 or not matched:
        raise SolidInpNotSupported(f"Exactly one material, used by the section, is supported "
                                   f"(found {sorted(materials)}).")
    mat = materials[matched[0]]
    if "density" not in mat or "elastic" not in mat:
        raise SolidInpNotSupported("The material needs *Density and *Elastic.")
    material = OrthotropicEngineeringConstants.from_abaqus(mat["elastic"])
    density = float(mat["density"])
    if not density > 0.0:
        raise SolidInpNotSupported("Density must be positive.")
    orientation_name = section.get("orientation")
    if orientation_name:
        found = mesh["orientations"].get(orientation_name.lower())
        if found is None:
            raise SolidInpNotSupported(f"Orientation {orientation_name!r} is not defined.")
        axes = found[1]
    else:
        axes = np.eye(3)

    labels = np.array(sorted(mesh["nodes"]), dtype=np.int64)
    index = {int(label): i for i, label in enumerate(labels)}
    coords = np.array([mesh["nodes"][int(label)] for label in labels], dtype=float)
    element_labels = np.array(sorted(mesh["elements"]), dtype=np.int64)
    try:
        conn = np.array([[index[n] for n in mesh["elements"][int(e)]] for e in element_labels],
                        dtype=np.int64)
    except KeyError as exc:
        raise SolidInpNotSupported(f"An element refers to undefined node {exc.args[0]}.") from exc
    for row in conn:
        if len(set(row.tolist())) != 8:
            raise SolidInpNotSupported("An element repeats a node (collapsed bricks are not supported).")
    used = np.zeros(len(labels), bool)
    used[conn.ravel()] = True
    if not used.all():
        raise SolidInpNotSupported(f"{int((~used).sum())} nodes are not connected to any element.")

    instance_name = None
    if inst is not None:
        instance_name = inst["name"]
        rotation = np.eye(3)
        if inst["rotation"] is not None:
            r = inst["rotation"]
            rotation = _rotation_about(np.array(r[3:6]) - np.array(r[0:3]), r[6])
            origin = np.array(r[0:3])
        else:
            origin = np.zeros(3)
        # Abaqus applies the translation first, then the rotation about the axis a-b.
        coords = coords + inst["translation"]
        coords = (coords - origin) @ rotation.T + origin
        axes = material_axes(axes @ rotation.T)

    frequency = steps[0]["frequency"]
    data = frequency["data"]
    requested = int(data[0]) if data and data[0] else None
    return SolidModel(
        source_path=str(path), source_sha256=hashlib.sha256(raw).hexdigest(),
        part_name=part_name, instance_name=instance_name, node_labels=labels, coordinates=coords,
        element_labels=element_labels, connectivity=conn, material_name=matched[0], material=material,
        density=density, material_axes=axes, orientation_name=orientation_name,
        requested_eigenvalues=requested,
        frequency_parameters={"parameters": frequency["parameters"], "data": data,
                              "step": steps[0]["parameters"]})


__all__ = ["SUPPORTED_ELEMENT_TYPE", "SolidInpNotSupported", "SolidModel", "load_solid_inp", "vary_in_plane"]
