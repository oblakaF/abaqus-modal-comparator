"""Shell mid-surface diagnostics for physical registration (R7-B; diagnostic only).

A measured surface is selected by ``measured_surface.side`` (``max_z`` / ``min_z``) from the nodes of one FE instance.
For a conventional shell (S3/S4/S4R/S8R/STRI...) every node of the instance lies on the mid-surface, so ``max_z`` and
``min_z`` select the same nodes and ``side`` cannot say which physical face the scanner saw: that face is expressed
only by the Z sign of ``experimental_axes_in_fe`` relative to the element normal.

Equal z coordinates alone are never taken as proof of a shell (a single-layer synthetic solid grid has them too). A
shell is CONFIRMED only from element types read from FE input text (an INP) supplied by the caller with its SHA-256.
The current evidence format has no field for the physical face relative to the shell normal, so a guided
registration of a confirmed shell is refused until that format is decided (see docs/reconciliation/
R7_SHELL_MODAL_SAFETY.md). Nothing here changes the M2 builder, a solid registration or a governed rule.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Iterable, Mapping, Optional

import numpy as np

# Conventional (mid-surface) shell elements; continuum shells (SC6R, SC8R) have through-thickness nodes and are not
# mid-surface elements.
_SHELL_TYPE = re.compile(r"^(S\d+[A-Z0-9]*|STRI\d+)$", re.IGNORECASE)


def is_conventional_shell(element_type: str) -> bool:
    return bool(_SHELL_TYPE.match(element_type.strip())) and not element_type.strip().upper().startswith("SC")


def surface_is_degenerate(fe, instance: str, abaqus_unit: str) -> bool:
    """True when ``max_z`` and ``min_z`` select the same nodes of the instance (one z level)."""
    return sorted(fe.surface_node_ids(instance, "max_z", abaqus_unit)) == \
        sorted(fe.surface_node_ids(instance, "min_z", abaqus_unit))


@dataclass(frozen=True)
class InpElementSummary:
    """Element types and flat-shell normal directions per assembly instance, read from INP text."""
    inp_sha256: str
    instance_element_types: Mapping[str, tuple]  # instance name (upper case) -> sorted element types
    instance_normal_z_counts: Mapping[str, Mapping[str, object]]  # instance -> {"+Z": n, "-Z": n, "in_plane": n}

    def shell_confirmed(self, instance: str) -> Optional[bool]:
        """True / False when the instance's element types are known, None when the INP does not name it."""
        types = self.instance_element_types.get(instance.upper())
        if not types:
            return None
        return all(is_conventional_shell(item) for item in types)


def _blocks(lines: list[str]) -> Iterable[tuple[str, list[str]]]:
    keyword, body = None, []
    for line in lines:
        if line.startswith("**"):
            continue
        if line.startswith("*"):
            if keyword is not None:
                yield keyword, body
            keyword, body = line, []
        elif keyword is not None:
            body.append(line)
    if keyword is not None:
        yield keyword, body


def _option(keyword: str, name: str) -> Optional[str]:
    match = re.search(rf"\b{name}\s*=\s*([^,\s]+)", keyword, re.IGNORECASE)
    return None if match is None else match.group(1).strip()


def inp_element_summary(text: str) -> InpElementSummary:
    """Element types and (for 3/4-node flat shells) the z sign of the connectivity normal, per instance.

    Reads *Part / *Node / *Element / *Instance only. Instance translations do not change normals; for an instance with
    a rotation line the normals are not reported (``{"unknown": "rotated instance"}``), never guessed.
    """
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    lines = text.splitlines()
    parts: dict[str, dict] = {}
    current = None
    instances: dict[str, str] = {}
    for keyword, body in _blocks(lines):
        upper = keyword.upper()
        if upper.startswith("*PART"):
            current = _option(keyword, "name").upper()
            parts[current] = {"nodes": {}, "types": set(), "normals": {"+Z": 0, "-Z": 0, "in_plane": 0}}
        elif upper.startswith("*END PART"):
            current = None
        elif upper.startswith("*NODE") and not upper.startswith("*NODE OUTPUT") and current is not None:
            for row in body:
                values = [item.strip() for item in row.split(",") if item.strip()]
                if len(values) >= 3:
                    xyz = [float(item) for item in values[1:4]] + [0.0] * (4 - len(values))
                    parts[current]["nodes"][int(values[0])] = np.array(xyz[:3], dtype=float)
        elif upper.startswith("*ELEMENT") and not upper.startswith("*ELEMENT OUTPUT") and current is not None:
            element_type = _option(keyword, "type")
            if element_type is None:
                continue
            parts[current]["types"].add(element_type.upper())
            if not is_conventional_shell(element_type):
                continue
            for row in body:
                ids = [int(item) for item in row.split(",") if item.strip()]
                corner = ids[1:5] if len(ids) >= 5 else ids[1:4]
                points = [parts[current]["nodes"].get(item) for item in corner]
                if len(points) < 3 or any(point is None for point in points):
                    continue
                normal = np.cross(points[1] - points[0], points[-1] - points[0])
                if abs(normal[2]) <= 1e-12 * max(np.linalg.norm(normal), 1e-300):
                    parts[current]["normals"]["in_plane"] += 1
                else:
                    parts[current]["normals"]["+Z" if normal[2] > 0 else "-Z"] += 1
        elif upper.startswith("*INSTANCE"):
            rotated = len([row for row in body if row.strip()]) >= 2
            instances[_option(keyword, "name").upper()] = (_option(keyword, "part").upper(), rotated)
    types = {name: tuple(sorted(parts.get(part, {}).get("types", ()))) for name, (part, _) in instances.items()}
    normals = {name: ({"unknown": "rotated instance"} if rotated else dict(parts.get(part, {}).get("normals", {})))
               for name, (part, rotated) in instances.items()}
    return InpElementSummary(sha, types, normals)
