"""Shell mid-surface support for guided physical registration (R7-B; diagnostic only).

A measured surface is selected by ``measured_surface.side`` (``max_z`` / ``min_z``) from the nodes of one FE instance.
For a conventional shell (S3/S4/S4R/S8R/STRI...) all nodes of the instance are the mid-surface: ``max_z`` and ``min_z``
select the same nodes and ``side`` cannot say which physical face the scanner saw.

This module supplies what the guided path needs to stay fail-closed without touching the governed passport contract:

- ``surface_is_degenerate``: the measured surface is a single z level (never, by itself, a claim of a shell);
- ``load_fe_input`` / ``parse_fe_input``: element types, node coordinates (instance translation applied) and the
  connectivity normals of flat 3- / 4-node shells, from the FE input text (INP) with its SHA-256;
- ``bind_fe_input``: the INP describes the loaded FE geometry only if the instance's node labels AND coordinates equal
  the extraction's, node for node (a matching SHA-256 of some INP is not enough). Then the instance is a conventional
  shell, a non-shell, or refused (mixed / rotated / unknown);
- ``ShellFaceStatement``: the guided-only ``shell_measured_face`` block (measured face relative to the element normal).

Nothing here changes the M2 builder, a solid registration, a threshold or a governed rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import re
from typing import Any, Mapping, Optional

import numpy as np

SHELL_FACE_SCHEMA = "auto-id/guided-shell-face/v1"
BINDING_TOLERANCE_MM = 1.0e-3  # INP text precision against float32 ODB coordinates
_SHELL_TYPE = re.compile(r"^(S\d+[A-Z0-9]*|STRI\d+)$", re.IGNORECASE)
NORMAL_DIRECTIONS = ("+Z", "-Z")
MEASURED_FACES = ("positive_normal", "negative_normal")


class ShellSurfaceRefusal(Exception):
    """The FE input or the shell-face statement cannot support the registration (field, reason)."""

    def __init__(self, field_name: str, message: str) -> None:
        super().__init__(message)
        self.field = field_name


def is_conventional_shell(element_type: str) -> bool:
    """S…/STRI… shells; continuum shells (SC6R, SC8R) have through-thickness nodes and are not mid-surfaces."""
    text = element_type.strip()
    return bool(_SHELL_TYPE.match(text)) and not text.upper().startswith("SC")


def surface_is_degenerate(fe, instance: str, abaqus_unit: str) -> bool:
    """True when ``max_z`` and ``min_z`` select the same nodes of the instance (one z level)."""
    return sorted(fe.surface_node_ids(instance, "max_z", abaqus_unit)) == \
        sorted(fe.surface_node_ids(instance, "min_z", abaqus_unit))


# ----------------------------------------------------------------------------- FE input (INP)

@dataclass(frozen=True)
class FEInputInstance:
    name: str
    part: str
    translation: tuple
    rotated: bool
    nodes: Mapping[int, tuple] = field(repr=False)  # label -> (x, y, z), instance translation applied
    element_types: tuple
    normal_counts: Mapping[str, int]  # conventional shell elements only: {"+Z", "-Z", "in_plane"}


@dataclass(frozen=True)
class FEInputModel:
    file_name: str
    sha256: str
    size_bytes: int
    instances: Mapping[str, FEInputInstance]  # upper-case instance name -> instance

    def instance(self, name: str) -> Optional[FEInputInstance]:
        return self.instances.get(name.upper())


def _option(keyword: str, name: str) -> Optional[str]:
    match = re.search(rf"\b{name}\s*=\s*([^,\s]+)", keyword, re.IGNORECASE)
    return None if match is None else match.group(1).strip()


def parse_fe_input(text: str, *, file_name: str = "model.inp", sha256: Optional[str] = None,
                   size_bytes: Optional[int] = None, instance: Optional[str] = None) -> FEInputModel:
    """Instances of an INP with their nodes, element types and shell normals.

    With ``instance`` only that instance's part is read in full (large INPs). Nodes and normals are taken in the part's
    coordinates plus the instance translation; an instance with a rotation line is marked ``rotated`` and its normals
    are not used.
    """
    raw = text.encode("utf-8")
    sha = sha256 or hashlib.sha256(raw).hexdigest()
    lines = text.splitlines()
    instance_rows: dict[str, tuple[str, list[str]]] = {}
    for k, line in enumerate(lines):
        if line[:9].upper() == "*INSTANCE":
            body, j = [], k + 1
            while j < len(lines) and not lines[j].startswith("*"):
                if lines[j].strip():
                    body.append(lines[j])
                j += 1
            instance_rows[_option(line, "name").upper()] = (_option(line, "part").upper(), body)
    wanted_parts = None if instance is None else \
        {instance_rows[instance.upper()][0]} if instance.upper() in instance_rows else set()
    parts: dict[str, dict] = {}
    current, mode, element_type = None, None, None
    for line in lines:
        if line.startswith("**"):
            continue
        if line.startswith("*"):
            upper = line.upper()
            mode = None
            if upper.startswith("*PART"):
                name = _option(line, "name").upper()
                current = name if wanted_parts is None or name in wanted_parts else None
                if current is not None:
                    parts[current] = {"nodes": {}, "types": set(), "normals": {"+Z": 0, "-Z": 0, "in_plane": 0}}
            elif upper.startswith("*END PART"):
                current = None
            elif current is not None and upper.startswith("*NODE") and not upper.startswith("*NODE OUTPUT"):
                mode = "node"
            elif current is not None and upper.startswith("*ELEMENT") and not upper.startswith("*ELEMENT OUTPUT"):
                element_type = _option(line, "type")
                if element_type:
                    parts[current]["types"].add(element_type.upper())
                    mode = "element"
            continue
        if mode == "node":
            values = [item.strip() for item in line.split(",") if item.strip()]
            if len(values) >= 3:
                xyz = [float(item) for item in values[1:4]] + [0.0] * (4 - len(values))
                parts[current]["nodes"][int(values[0])] = tuple(xyz[:3])
        elif mode == "element" and is_conventional_shell(element_type):
            ids = [int(item) for item in line.split(",") if item.strip()]
            corner = ids[1:5] if len(ids) >= 5 else ids[1:4]
            points = [parts[current]["nodes"].get(item) for item in corner]
            if len(points) < 3 or any(point is None for point in points):
                continue
            a, b, c = (np.asarray(point, dtype=float) for point in (points[0], points[1], points[-1]))
            normal = np.cross(b - a, c - a)
            scale = max(float(np.linalg.norm(normal)), 1e-300)
            key = "in_plane" if abs(normal[2]) <= 1e-9 * scale else ("+Z" if normal[2] > 0 else "-Z")
            parts[current]["normals"][key] += 1
    instances = {}
    for name, (part, body) in instance_rows.items():
        if part not in parts:
            continue
        translation = tuple(float(v) for v in body[0].split(",")[:3]) if body else (0.0, 0.0, 0.0)
        shift = np.asarray(translation, dtype=float)
        nodes = {label: tuple((np.asarray(xyz) + shift).tolist()) for label, xyz in parts[part]["nodes"].items()}
        instances[name] = FEInputInstance(name, part, translation, len(body) >= 2, nodes,
                                          tuple(sorted(parts[part]["types"])), dict(parts[part]["normals"]))
    return FEInputModel(file_name, sha, len(raw) if size_bytes is None else size_bytes, instances)


def load_fe_input(path: Path, instance: Optional[str] = None) -> FEInputModel:
    data = Path(path).read_bytes()
    return parse_fe_input(data.decode("latin-1"), file_name=Path(path).name, sha256=hashlib.sha256(data).hexdigest(),
                          size_bytes=len(data), instance=instance)


@dataclass(frozen=True)
class FEInputBinding:
    fe_input_sha256: str
    file_name: str
    instance: str
    element_types: tuple
    kind: str  # "shell" | "non_shell"
    normal_direction: Optional[str]  # "+Z" / "-Z" for a uniformly oriented flat shell, else None
    normal_counts: Mapping[str, int]
    node_count: int
    max_coordinate_difference: float

    def to_dict(self) -> dict:
        return {"fe_input_sha256": self.fe_input_sha256, "file_name": self.file_name, "instance": self.instance,
                "element_types": list(self.element_types), "kind": self.kind,
                "normal_direction": self.normal_direction, "normal_counts": dict(self.normal_counts),
                "node_count": self.node_count, "max_coordinate_difference": self.max_coordinate_difference,
                "bound": True}


def bind_fe_input(model: FEInputModel, fe, instance: str, abaqus_unit: str) -> FEInputBinding:
    """The INP's instance is the loaded FE instance, node for node; else refuse."""
    from coordinate_calibration import millimetres_to_model_units

    item = model.instance(instance)
    if item is None:
        raise ShellSurfaceRefusal("fe_input", f"the FE input {model.file_name} ({model.sha256[:12]}) has no instance "
                                              f"{instance!r}.")
    if item.rotated:
        raise ShellSurfaceRefusal("fe_input", f"instance {item.name} of {model.file_name} is rotated; rotated "
                                              "instances are not bound (normals and coordinates are not transformed).")
    prefix = [str(value).split(":", 1) for value in fe.node_ids]
    selected = np.array([parts[0].upper() == instance.upper() for parts in prefix])
    labels = [int(prefix[k][1]) for k in np.flatnonzero(selected)]
    coordinates = fe.coordinates[selected]
    if sorted(labels) != sorted(item.nodes):
        raise ShellSurfaceRefusal("fe_input", f"instance {item.name} of {model.file_name} has {len(item.nodes)} nodes; "
                                              f"the loaded FE instance has {len(labels)} with other labels: the FE "
                                              "input does not describe the loaded model.")
    expected = np.asarray([item.nodes[label] for label in labels], dtype=float)
    difference = float(np.max(np.abs(expected - coordinates))) if len(labels) else 0.0
    tolerance = millimetres_to_model_units(BINDING_TOLERANCE_MM, abaqus_unit)
    if difference > tolerance:
        raise ShellSurfaceRefusal("fe_input", f"node coordinates of {item.name} in {model.file_name} differ from the "
                                              f"loaded FE geometry by up to {difference:.3g} (tolerance {tolerance:g}):"
                                              " the FE input does not describe the loaded model.")
    shells = [is_conventional_shell(kind) for kind in item.element_types]
    if not item.element_types or (any(shells) and not all(shells)):
        raise ShellSurfaceRefusal("fe_input", f"instance {item.name} has element types "
                                              f"{list(item.element_types)}: neither a conventional shell nor a non-shell.")
    kind = "shell" if all(shells) else "non_shell"
    counts = dict(item.normal_counts)
    direction = None
    if kind == "shell" and counts.get("in_plane", 0) == 0:
        if counts.get("+Z", 0) > 0 and counts.get("-Z", 0) == 0:
            direction = "+Z"
        elif counts.get("-Z", 0) > 0 and counts.get("+Z", 0) == 0:
            direction = "-Z"
    return FEInputBinding(model.sha256, model.file_name, item.name, item.element_types, kind, direction, counts,
                          len(labels), difference)


# ----------------------------------------------------------------------------- shell-face statement

@dataclass(frozen=True)
class ShellFaceStatement:
    fe_instance: str
    fe_input_sha256: str
    normal_direction: str
    measured_face: str
    face_evidence: str

    def document(self) -> dict:
        return {"schema": SHELL_FACE_SCHEMA, "fe_instance": self.fe_instance, "fe_input_sha256": self.fe_input_sha256,
                "normal_direction": self.normal_direction, "measured_face": self.measured_face,
                "face_evidence": self.face_evidence}

    def experimental_z_in_fe(self) -> str:
        """The FE axis the experimental +z (towards the scanner) must map to."""
        if self.measured_face == "positive_normal":
            return self.normal_direction
        return "-Z" if self.normal_direction == "+Z" else "+Z"


def parse_shell_face(value: Any) -> ShellFaceStatement:
    if not isinstance(value, Mapping) or value.get("schema") != SHELL_FACE_SCHEMA:
        raise ShellSurfaceRefusal("shell_measured_face", f"not a {SHELL_FACE_SCHEMA} block.")
    instance, sha = value.get("fe_instance"), value.get("fe_input_sha256")
    normal, face, source = value.get("normal_direction"), value.get("measured_face"), value.get("face_evidence")
    if not (isinstance(instance, str) and instance.strip()):
        raise ShellSurfaceRefusal("shell_measured_face", "fe_instance is required.")
    if not (isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha)):
        raise ShellSurfaceRefusal("shell_measured_face", "fe_input_sha256 (the bound FE input) is required.")
    if normal not in NORMAL_DIRECTIONS:
        raise ShellSurfaceRefusal("shell_measured_face", f"normal_direction must be one of {NORMAL_DIRECTIONS}.")
    if face not in MEASURED_FACES:
        raise ShellSurfaceRefusal("shell_measured_face", f"measured_face must be one of {MEASURED_FACES}.")
    if not (isinstance(source, str) and source.strip()):
        raise ShellSurfaceRefusal("shell_measured_face", "face_evidence (the physical record of the measured face) is "
                                                         "required.")
    return ShellFaceStatement(instance, sha, normal, face, source)
