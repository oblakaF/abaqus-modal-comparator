"""Universal manifest-driven forward builder — Auto-ID M3 (SPEC §4, §5.2, §16; AUDIT V2).

One code path for every specimen: a forward-model manifest (bound to its passport)
names the pinned reference INP, the material whose Engineering Constants a candidate
sets, the eigenvalue request and the registration.  The builder copies the reference
INP and changes only:

- the variable constants of that one material record (E1, E2, G12 for the carbon
  property set v1); E3, ν12, ν13, ν23, G13, G23 are written back unchanged;
- the eigenvalue count of the single ``*Frequency`` request, when the manifest asks
  for more modal headroom.

Mesh, geometry, core, density, adhesive, ties and every other line are copied
byte-for-byte.  It prepares jobs only: no Abaqus execution, extraction or pairing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from domain.forward_model_manifest import ENGINEERING_CONSTANTS_TYPE, EngineeringConstants


# Material options that may appear inside a *Material block of these inputs.
_MATERIAL_OPTIONS = {"density", "elastic", "expansion", "damping", "conductivity", "specific heat"}


class ForwardBuildError(ValueError):
    """The reference input cannot be rewritten safely; nothing is guessed."""


# ----------------------------------------------------------------------------- INP reading

def _keyword(line: str) -> Optional[str]:
    """Lower-case keyword of a keyword line, or None for data and comment lines."""
    if not line.startswith("*") or line.startswith("**"):
        return None
    return line[1:].split(",", 1)[0].strip().lower()


def _parameters(line: str) -> dict[str, str]:
    output = {}
    for part in line.split(",")[1:]:
        if "=" in part:
            key, value = part.split("=", 1)
            output[" ".join(key.split()).lower()] = " ".join(value.split()).strip('"')
    return output


def _data_lines(lines: list[str], start: int) -> list[int]:
    """Indices of the data lines after keyword line ``start`` (comment lines skipped)."""
    indices = []
    index = start + 1
    while index < len(lines):
        line = lines[index]
        if line.startswith("**"):
            index += 1
            continue
        if line.startswith("*"):
            break
        indices.append(index)
        index += 1
    return indices


def _line_ending(line: str) -> str:
    return line[len(line.rstrip("\r\n")):]


def _tokens(line: str) -> list[str]:
    return [token.strip() for token in line.rstrip("\r\n").split(",")]


def split_inp_lines(raw: bytes) -> list[str]:
    """Split INP bytes into lines that re-join to exactly the same bytes."""
    return raw.decode("latin-1").splitlines(keepends=True)


def join_inp_lines(lines: list[str]) -> bytes:
    return "".join(lines).encode("latin-1")


# ----------------------------------------------------------------------------- M3.1 material location

@dataclass(frozen=True)
class EngineeringConstantsRecord:
    """Where one material's Engineering-Constants record sits in an INP (0-based line indices)."""

    material_name: str
    material_line: int
    elastic_line: int
    data_lines: tuple[int, ...]
    positions: tuple[tuple[int, int], ...]  # (data row, token column) of the nine values, in record order
    values: EngineeringConstants


def locate_engineering_constants(lines: list[str], material_name: str) -> EngineeringConstantsRecord:
    """Locate the unique ``*Elastic, type=ENGINEERING CONSTANTS`` record of the named material.

    Refuses a missing or duplicated material, zero or several ``*Elastic`` options, any
    other elastic type, and anything but one temperature-independent nine-value record.
    """

    target = material_name.lower()
    blocks = [i for i, line in enumerate(lines)
              if _keyword(line) == "material" and _parameters(line).get("name", "").lower() == target]
    if len(blocks) != 1:
        raise ForwardBuildError(f"Expected exactly one *Material named {material_name!r}; found {len(blocks)}.")
    elastic = []
    index = blocks[0] + 1
    while index < len(lines):
        keyword = _keyword(lines[index])
        if keyword is not None:
            if keyword not in _MATERIAL_OPTIONS:
                break
            if keyword == "elastic":
                elastic.append(index)
        index += 1
    if len(elastic) != 1:
        raise ForwardBuildError(
            f"Material {material_name!r} must contain exactly one *Elastic record; found {len(elastic)}.")
    if _parameters(lines[elastic[0]]).get("type", "").upper() != ENGINEERING_CONSTANTS_TYPE:
        raise ForwardBuildError(f"Material {material_name!r} *Elastic is not type={ENGINEERING_CONSTANTS_TYPE}.")
    data = _data_lines(lines, elastic[0])
    rows = [_tokens(lines[i]) for i in data]
    positions = tuple((row, column) for row, tokens in enumerate(rows) for column, token in enumerate(tokens) if token)
    if len(positions) != 9:
        raise ForwardBuildError(
            f"Material {material_name!r} Engineering Constants must be one 9-value record "
            f"(no temperature dependence); found {len(positions)} values.")
    try:
        values = EngineeringConstants(*(float(rows[r][c]) for r, c in positions))
    except ValueError as exc:
        raise ForwardBuildError(f"Material {material_name!r}: unreadable Engineering Constants: {exc}") from exc
    return EngineeringConstantsRecord(material_name, blocks[0], elastic[0], tuple(data), positions, values)
