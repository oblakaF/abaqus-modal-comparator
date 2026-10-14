"""Nine Engineering Constants in an Abaqus INP — research track NINE-EC (Phase C).

Reading and rewriting reuse the accepted M3 forward builder (``locate_engineering_constants`` and
``rewrite_engineering_constants``): one unique material, exactly one temperature-independent nine-value
``*Elastic, type=ENGINEERING CONSTANTS`` record, every other byte unchanged. This module adds what a nine-constant
question needs before any FE job:

- the materials of the INP with their elastic record type and readability (an explicit choice is required when more
  than one material carries Engineering Constants; nothing is guessed);
- the sections that use the material (solid / shell / other), their element types and material orientation as
  written in the INP (axes are reported, never inferred from MAC);
- which of the nine constants the element formulation can use at all: a conventional or continuum shell section works
  in plane stress (E1, E2, ν12, G12 plus G13, G23 for transverse shear), so E3, ν13 and ν23 cannot influence its
  spectrum; a solid section uses all nine. Presence of a value in the record proves nothing about its influence;
- physical admissibility (domain.orthotropic_elasticity) of the read constants and of every rewritten set.

No calibrated-INP writer exists here: ``render_constants`` prepares forward-model inputs only (research jobs).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Mapping, Optional, Sequence

from domain.forward_model_manifest import ENGINEERING_CONSTANTS_TYPE, EngineeringConstants
from domain.orthotropic_elasticity import NAMES, AdmissibilityReport, admissibility, require_admissible

from .forward_builder import (
    ForwardBuildError,
    _parameters,
    inp_keyword,
    join_inp_lines,
    locate_engineering_constants,
    material_block_bounds,
    rewrite_engineering_constants,
    split_inp_lines,
)

SOLID_SECTIONS = {"solid section"}
SHELL_SECTIONS = {"shell section", "shell general section"}  # conventional and continuum shells: plane stress
OTHER_SECTIONS = {"membrane section", "beam section", "beam general section", "cohesive section", "surface section"}
PLANE_STRESS_CONSTANTS = ("E1", "E2", "nu12", "G12", "G13", "G23")  # Abaqus shells: G13, G23 = transverse shear


class NineConstantsInputError(ValueError):
    """The INP cannot support a nine-constant question without guessing (reason in the message)."""


@dataclass(frozen=True)
class SectionUse:
    keyword: str  # e.g. "solid section"
    elset: str
    orientation: Optional[str]  # orientation name on the section line, or None (default axes)
    element_types: tuple[str, ...]  # element types of the elset (or of its *Part, see element_types_source)
    element_types_source: str = "NOT_FOUND"  # ELSET (*Element ..., elset=) | PART (all elements of the part) | NOT_FOUND

    @property
    def kind(self) -> str:
        if self.keyword in SOLID_SECTIONS:
            return "SOLID"
        if self.keyword in SHELL_SECTIONS:
            return "SHELL"
        return "OTHER"

    def to_dict(self) -> dict:
        return {"keyword": self.keyword, "kind": self.kind, "elset": self.elset, "orientation": self.orientation,
                "element_types": list(self.element_types), "element_types_source": self.element_types_source}


@dataclass(frozen=True)
class MaterialCandidate:
    name: str
    elastic_type: Optional[str]  # None when the material has no (or several) *Elastic records
    constants: Optional[EngineeringConstants]
    reason: Optional[str]  # why it is not an eligible nine-constant material
    sections: tuple[SectionUse, ...] = ()

    @property
    def eligible(self) -> bool:
        return self.constants is not None

    def to_dict(self) -> dict:
        return {"name": self.name, "elastic_type": self.elastic_type, "eligible": self.eligible,
                "constants": None if self.constants is None else self.constants.to_dict(), "reason": self.reason,
                "sections": [s.to_dict() for s in self.sections]}


@dataclass(frozen=True)
class OrientationRecord:
    name: str
    system: str
    definition: tuple[str, ...]  # the data lines as written

    def to_dict(self) -> dict:
        return {"name": self.name, "system": self.system, "definition": list(self.definition)}


@dataclass(frozen=True)
class NineConstantsModel:
    """The selected material of one INP, as needed before any nine-constant FE evaluation."""

    source_sha256: str
    material: str
    constants: EngineeringConstants
    admissibility: AdmissibilityReport
    sections: tuple[SectionUse, ...]
    orientations: Mapping[str, OrientationRecord]
    formulation_use: Mapping[str, str]  # constant -> USED / NOT_USED_BY_ELEMENT_FORMULATION / UNKNOWN
    other_materials: tuple[str, ...] = field(default_factory=tuple)

    @property
    def model_kind(self) -> str:
        kinds = {s.kind for s in self.sections}
        if not kinds:
            return "UNKNOWN (no section references the material)"
        if kinds == {"SOLID"}:
            return "3D_SOLID"
        if kinds == {"SHELL"}:
            return "SHELL_PLANE_STRESS"
        return "MIXED_OR_OTHER"

    def to_dict(self) -> dict:
        return {"source_sha256": self.source_sha256, "material": self.material,
                "constants": self.constants.to_dict(), "admissibility": self.admissibility.to_dict(),
                "model_kind": self.model_kind, "sections": [s.to_dict() for s in self.sections],
                "orientations": {k: v.to_dict() for k, v in sorted(self.orientations.items())},
                "formulation_use": dict(self.formulation_use), "other_materials": list(self.other_materials)}


def _scan(lines: Sequence[str]):
    """Keyword-line index: materials, sections, element sets with element types, orientations."""
    materials, sections, orientations = [], [], {}
    element_types: dict[str, set[str]] = {}  # elset (lower) -> types; "part:<name>" -> every type of that part
    part = None
    for index, line in enumerate(lines):
        keyword = inp_keyword(line)
        if keyword is None:
            continue
        parameters = _parameters(line)
        if keyword == "part":
            part = parameters.get("name", "").lower()
        elif keyword == "end part":
            part = None
        elif keyword == "material":
            materials.append(parameters.get("name", ""))
        elif keyword in SOLID_SECTIONS | SHELL_SECTIONS | OTHER_SECTIONS:
            sections.append((keyword, parameters.get("elset", ""), parameters.get("material", ""),
                             parameters.get("orientation"), part))
        elif keyword == "element" and parameters.get("type"):
            if parameters.get("elset"):
                element_types.setdefault(parameters["elset"].lower(), set()).add(parameters["type"].upper())
            if part is not None:
                element_types.setdefault(f"part:{part}", set()).add(parameters["type"].upper())
        elif keyword == "orientation" and parameters.get("name"):
            data = []
            follow = index + 1
            while follow < len(lines) and len(data) < 2 and not (lines[follow].startswith("*")
                                                                  and not lines[follow].startswith("**")):
                if not lines[follow].startswith("**"):
                    data.append(lines[follow].strip())
                follow += 1
            orientations[parameters["name"].lower()] = OrientationRecord(
                parameters["name"], parameters.get("system", "RECTANGULAR").upper(), tuple(data))
    return materials, sections, element_types, orientations


def _candidate(lines: list[str], name: str, sections) -> MaterialCandidate:
    try:
        start, end = material_block_bounds(lines, name)
    except ForwardBuildError as error:
        return MaterialCandidate(name, None, None, str(error), sections)
    elastic = [i for i in range(start + 1, end) if inp_keyword(lines[i]) == "elastic"]
    if len(elastic) != 1:
        return MaterialCandidate(name, None, None, f"{len(elastic)} *Elastic records (exactly one is required)",
                                 sections)
    elastic_type = _parameters(lines[elastic[0]]).get("type", "ISOTROPIC").upper()
    if elastic_type != ENGINEERING_CONSTANTS_TYPE:
        return MaterialCandidate(name, elastic_type, None,
                                 f"*Elastic type={elastic_type} (nine constants need type={ENGINEERING_CONSTANTS_TYPE})",
                                 sections)
    try:
        record = locate_engineering_constants(lines, name)
    except ForwardBuildError as error:
        return MaterialCandidate(name, elastic_type, None, str(error), sections)
    return MaterialCandidate(name, elastic_type, record.values, None, sections)


def material_candidates(source: bytes) -> list[MaterialCandidate]:
    """Every *Material of the INP with its elastic record type, readability and the sections that use it."""
    lines = split_inp_lines(source)
    materials, sections, element_types, _ = _scan(lines)
    out = []
    for name in materials:
        uses = []
        for keyword, elset, material, orientation, part in sections:
            if material.lower() != name.lower():
                continue
            if elset.lower() in element_types:
                types, origin = element_types[elset.lower()], "ELSET"
            elif part is not None and f"part:{part}" in element_types:
                types, origin = element_types[f"part:{part}"], "PART"
            else:
                types, origin = set(), "NOT_FOUND"
            uses.append(SectionUse(keyword, elset, orientation, tuple(sorted(types)), origin))
        out.append(_candidate(lines, name, tuple(uses)))
    return out


def formulation_use(sections: Sequence[SectionUse]) -> dict[str, str]:
    """Which constants the section formulations can use (a value in the record is not proof of influence)."""
    kinds = {s.kind for s in sections}
    if kinds == {"SOLID"}:
        return {name: "USED" for name in NAMES}
    if kinds == {"SHELL"}:
        return {name: ("USED" if name in PLANE_STRESS_CONSTANTS else "NOT_USED_BY_ELEMENT_FORMULATION")
                for name in NAMES}
    return {name: "UNKNOWN" for name in NAMES}


def select_material(candidates: Sequence[MaterialCandidate], requested: Optional[str] = None) -> MaterialCandidate:
    """The material of the question: the requested one, or the only eligible one. Several eligible -> refusal."""
    eligible = [c for c in candidates if c.eligible]
    if requested is not None:
        named = [c for c in candidates if c.name.lower() == requested.strip().lower()]
        if len(named) != 1:
            raise NineConstantsInputError(f"material {requested!r} is not in the INP (exactly once).")
        if not named[0].eligible:
            raise NineConstantsInputError(f"material {named[0].name!r} cannot be used: {named[0].reason}.")
        return named[0]
    if not eligible:
        raise NineConstantsInputError("no material with one nine-value *Elastic, type=ENGINEERING CONSTANTS record: "
                                      + "; ".join(f"{c.name}: {c.reason}" for c in candidates))
    if len(eligible) > 1:
        raise NineConstantsInputError("several materials carry Engineering Constants ("
                                      + ", ".join(c.name for c in eligible) + "): choose one explicitly.")
    return eligible[0]


def read_nine_constants_model(source: bytes, material: Optional[str] = None) -> NineConstantsModel:
    """The selected material with its constants, admissibility, sections, orientations and formulation use."""
    lines = split_inp_lines(source)
    candidates = material_candidates(source)
    chosen = select_material(candidates, material)
    _, _, _, orientations = _scan(lines)
    used = {s.orientation.lower() for s in chosen.sections if s.orientation}
    return NineConstantsModel(
        hashlib.sha256(source).hexdigest(), chosen.name, chosen.constants, admissibility(chosen.constants),
        chosen.sections, {k: v for k, v in orientations.items() if k in used}, formulation_use(chosen.sections),
        tuple(c.name for c in candidates if c.name != chosen.name))


def render_constants(source: bytes, material: str, constants: EngineeringConstants) -> bytes:
    """A forward-model input with the nine constants of ``material`` replaced; every other byte unchanged.

    Inadmissible constants are refused before anything is rendered (no FE job can be prepared from them).
    """
    require_admissible(constants)
    lines = split_inp_lines(source)
    record = locate_engineering_constants(lines, material)
    rewrite_engineering_constants(lines, record, constants, NAMES)
    return join_inp_lines(lines)
