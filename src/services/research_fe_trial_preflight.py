"""REAL-FIT.R4: prepare and statically verify two Abaqus S4R trial decks from the Ritz research minima.

The two decks are the original M11 INP with only E1, E2 and G12 of its single ``*Elastic, type=ENGINEERING CONSTANTS``
replaced by the two independently optimised mirror minima of a research-frequency-tuning export. Every other byte stays
as it is. The module only reads and writes files: it never starts Abaqus or any other process, and it writes only new
files into an output folder (never over an existing file, never next to the source deck).

The decks are exploratory FE trial inputs (diagnostic optimiser candidates), not material properties, not calibration
values and not FE results. Static agreement says nothing about how Abaqus will solve them.
"""

from __future__ import annotations

from dataclasses import dataclass
import difflib
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from . import research_frequency_tuning as rft

SCHEMA = "research-fe-trial-preflight/1"
LABEL = "EXPLORATORY_FE_TRIAL_INPUT — DIAGNOSTIC_OPTIMIZER_CANDIDATE — NOT_A_RELEASE_VALUE — NOT_RUN_IN_ABAQUS"
VARIANTS = (("A", "M11_RITZ_MINIMUM_A.inp"), ("B", "M11_RITZ_MINIMUM_B.inp"))
MANIFEST = "preflight_manifest.json"
FIELDS = ("E1", "E2", "E3", "nu12", "nu13", "nu23", "G12", "G13", "G23")  # ENGINEERING CONSTANTS order
TARGETS = ("E1", "E2", "G12")
MAX_FIELD_CHARS = 20  # an Abaqus floating-point data item may use at most 20 characters
DISTINCT = 1.0e-3  # the two minima must differ by more than this relative amount in some target (numerical policy)
NORMAL_X_LIMIT_DEG = 0.1  # Abaqus projects global Z instead of X when the normal is within 0.1 degrees of X
ABAQUS_RUN = "NOT_RUN"


class PreflightRefused(ValueError):
    """The inputs are missing, ambiguous or not of the supported structure; nothing is written."""


@dataclass(frozen=True)
class Minimum:
    label: str  # "A" = lowest cost, "B" = the exchanged minimum, as named in the export's axis assignments
    values: Mapping[str, float]
    cost: float


# ------------------------------------------------------------------------------------------------ text structure


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def _lines(data: bytes) -> list:
    return data.decode("latin-1").splitlines(keepends=True)


def _body(line: str) -> str:
    return line.rstrip("\r\n")


def _is_keyword(line: str) -> bool:
    return line.startswith("*") and not line.startswith("**")


def blocks(lines: Sequence[str]) -> list:
    """(keyword line index, keyword text, data line indexes) for every keyword; comment lines are not data."""
    out = []
    for index, line in enumerate(lines):
        if _is_keyword(line):
            out.append((index, _body(line).strip(), []))
        elif out and not line.startswith("**") and _body(line).strip():
            out[-1][2].append(index)
    return out


def _name(keyword: str) -> str:
    return keyword.split(",")[0].strip().lower().replace(" ", "")


def _parameter(keyword: str, key: str) -> Optional[str]:
    for part in keyword.split(",")[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            if k.strip().lower() == key:
                return v.strip()
    return None


def _numbers(text: str) -> list:
    return [float(item) for item in text.split(",") if item.strip()]


@dataclass(frozen=True)
class ElasticBlock:
    keyword_index: int
    data_indexes: tuple
    values: Mapping[str, float]


def elastic_block(lines: Sequence[str]) -> ElasticBlock:
    """The single material's single ENGINEERING CONSTANTS *Elastic, nine constants on 8 + 1 data items. Else refused."""
    found = blocks(lines)
    materials = [b for b in found if _name(b[1]) == "*material"]
    elastic = [b for b in found if _name(b[1]) == "*elastic"]
    if len(materials) != 1:
        raise PreflightRefused(f"The deck holds {len(materials)} *Material definitions; exactly one is supported.")
    if len(elastic) != 1:
        raise PreflightRefused(f"The deck holds {len(elastic)} *Elastic definitions; exactly one is supported.")
    index, keyword, data = elastic[0]
    if index < materials[0][0]:
        raise PreflightRefused("The *Elastic block precedes the *Material it should belong to.")
    kind = (_parameter(keyword, "type") or "ISOTROPIC").upper()
    if kind != "ENGINEERING CONSTANTS":
        raise PreflightRefused(f"*Elastic type {kind} is not supported; only ENGINEERING CONSTANTS is.")
    extra = [p.split("=")[0].strip().lower() for p in keyword.split(",")[1:] if p.split("=")[0].strip().lower() != "type"]
    if extra:
        raise PreflightRefused(f"*Elastic parameters {extra} (dependencies, moduli, ...) are not supported.")
    if len(data) != 2:
        raise PreflightRefused(f"The *Elastic block has {len(data)} data lines; the supported form has 2 (8 + 1 items).")
    first, second = (_numbers(_body(lines[i])) for i in data)
    if len(first) != 8 or len(second) != 1:
        raise PreflightRefused("The *Elastic data are not 8 + 1 constants (temperature or field columns are not supported).")
    values = dict(zip(FIELDS, first + second))
    if not all(math.isfinite(v) for v in values.values()) or min(values[k] for k in ("E1", "E2", "E3", "G12", "G13", "G23")) <= 0:
        raise PreflightRefused("The *Elastic moduli must be finite and positive.")
    return ElasticBlock(index, tuple(data), values)


def format_value(value: float) -> str:
    """Shortest repr that reads back to exactly the same double, within the Abaqus 20-character limit."""
    value = float(value)
    if not math.isfinite(value) or value <= 0.0:
        raise PreflightRefused(f"A target modulus {value!r} is not finite and positive.")
    text = repr(value)
    if float(text) != value or len(text) > MAX_FIELD_CHARS:
        raise PreflightRefused(f"The value {text} cannot be written exactly in {MAX_FIELD_CHARS} characters.")
    return text


def build_variant(original: bytes, values: Mapping[str, float]) -> bytes:
    """The original bytes with only the E1, E2 and G12 items of the first *Elastic data line replaced."""
    lines = _lines(original)
    block = elastic_block(lines)
    index = block.data_indexes[0]
    line = lines[index]
    body = _body(line)
    ending = line[len(body):]
    items = body.split(",")
    for name in TARGETS:
        position = FIELDS.index(name)
        token = items[position]
        lead = token[: len(token) - len(token.lstrip())]
        items[position] = lead + format_value(values[name])
    lines[index] = ",".join(items) + ending
    return "".join(lines).encode("latin-1")


# --------------------------------------------------------------------------------------------- model structure


def _table(lines, data) -> list:
    return [[p.strip() for p in _body(lines[i]).split(",") if p.strip()] for i in data]


def structure(data: bytes) -> dict:
    """Identities of every model part except the *Elastic data: counts and SHA-256 of normalised content."""
    lines = _lines(data)
    found = blocks(lines)
    summary: dict = {"keywords": [b[1] for b in found]}
    groups: dict = {}
    for index, keyword, rows in found:
        name = _name(keyword)
        content = [keyword] + [_body(lines[i]).strip() for i in rows]
        if name == "*elastic":
            content = [keyword]  # its data are the authorised change; checked field by field elsewhere
        groups.setdefault(name, []).append(content)
    for name, items in groups.items():
        summary[name] = sha256_bytes(json.dumps(items).encode("utf-8"))
    nodes = [b for b in found if _name(b[1]) == "*node"]
    elements = [b for b in found if _name(b[1]) == "*element"]
    summary["node_count"] = sum(len(b[2]) for b in nodes)
    summary["element_count"] = sum(len(b[2]) for b in elements)
    summary["element_types"] = sorted({(_parameter(b[1], "type") or "").upper() for b in elements})
    summary["node_coordinates_sha256"] = sha256_bytes(json.dumps(
        [[float(v) for v in row[1:]] for b in nodes for row in _table(lines, b[2])]).encode("utf-8"))
    summary["connectivity_sha256"] = sha256_bytes(json.dumps(
        [[int(v) for v in row] for b in elements for row in _table(lines, b[2])]).encode("utf-8"))
    sections = [b for b in found if _name(b[1]) == "*shellsection"]
    summary["shell_sections"] = [[b[1]] + [_body(lines[i]).strip() for i in b[2]] for b in sections]
    densities = [b for b in found if _name(b[1]) == "*density"]
    summary["density"] = [_numbers(_body(lines[i])) for b in densities for i in b[2]]
    steps = [i for i, b in enumerate(found) if _name(b[1]) == "*step"]
    summary["steps"] = [[b[1]] + [_body(lines[i]).strip() for i in b[2]] for b in found[steps[0]:]] if steps else []
    return summary


def _vector(row) -> np.ndarray:
    return np.array([float(v) for v in row[1:4]] + [0.0] * (3 - len(row[1:4])))


def material_axes(data: bytes) -> dict:
    """How Abaqus would orient material 1/2 in each S4R element, from the deck alone (no solver run)."""
    lines = _lines(data)
    found = blocks(lines)
    names = [_name(b[1]) for b in found]
    explicit = sorted({b[1] for b in found if _name(b[1]) in ("*orientation", "*transform", "*distribution", "*rebarlayer")})
    section_orientation = [b[1] for b in found if _name(b[1]) == "*shellsection" and _parameter(b[1], "orientation")]
    composite = [b[1] for b in found if _name(b[1]) == "*shellsection" and "composite" in b[1].lower()]
    instances = [b for b in found if _name(b[1]) == "*instance"]
    instance_lines = [[_body(lines[i]).strip() for i in b[2]] for b in instances]
    nodes = {}
    for b in found:
        if _name(b[1]) == "*node":
            for row in _table(lines, b[2]):
                nodes[int(row[0])] = _vector(row)
    normals = []
    for b in found:
        if _name(b[1]) == "*element" and (_parameter(b[1], "type") or "").upper() in ("S4R", "S4", "S4R5"):
            for row in _table(lines, b[2]):
                p = [nodes[int(n)] for n in row[1:5]]
                n = np.cross(p[2] - p[0], p[3] - p[1])
                normals.append(n / np.linalg.norm(n))
    normals = np.array(normals) if normals else np.zeros((0, 3))
    z = np.array([v[2] for v in nodes.values()]) if nodes else np.zeros(0)
    angle_to_x = float(np.degrees(np.min(np.arccos(np.clip(np.abs(normals[:, 0]), 0.0, 1.0))))) if len(normals) else None
    plus_z = int(np.sum(normals[:, 2] > 1.0 - 1e-12)) if len(normals) else 0
    minus_z = int(np.sum(normals[:, 2] < -1.0 + 1e-12)) if len(normals) else 0
    translation_only = all(len(rows) <= 1 for rows in instance_lines)
    planar = bool(len(z)) and float(np.ptp(z)) == 0.0
    established = (not explicit and not section_orientation and not composite and translation_only and planar
                   and len(normals) > 0 and plus_z + minus_z == len(normals) and angle_to_x is not None
                   and angle_to_x > NORMAL_X_LIMIT_DEG)
    result = {
        "explicit_orientation_keywords": explicit,
        "section_orientation_parameter": section_orientation,
        "composite_section": composite,
        "instances": instance_lines,
        "instance_translation_only": translation_only,
        "nodes_in_one_plane_z": float(z[0]) if planar else None,
        "shell_elements": int(len(normals)),
        "normals_plus_z": plus_z,
        "normals_minus_z": minus_z,
        "smallest_angle_normal_to_global_x_deg": angle_to_x,
        "status": "ESTABLISHED_FROM_DECK_AND_ABAQUS_CONVENTION" if established else "NOT_ESTABLISHED",
    }
    if established:
        result["interpretation"] = (
            "No *Orientation: Abaqus uses its default local shell directions, material 1 = projection of global X onto the "
            "shell surface (global Z is used only for normals within 0.1 degrees of X), material 2 = normal x direction 1. "
            "Every element lies in one plane z = const with a normal along global Z, and the instance is only translated, "
            "so material 1 = FE global X and material 2 = FE global Y (sign is irrelevant for an orthotropic material) "
            "in every element. This rests on the documented Abaqus convention; no solver output of the local directions "
            "has been inspected.")
    else:
        result["interpretation"] = "The material 1/2 axes cannot be established from the deck alone; no transformation is assumed."
    return result


# ------------------------------------------------------------------------------------------------ the minima


def minima_from_export(document: Mapping[str, Any], inp_sha256: str) -> tuple:
    """The two mirror minima of a FREE (E1, E2, G12) tuning export of this exact INP, A = lowest cost. Else refused."""
    if document.get("schema") != rft.SCHEMA:
        raise PreflightRefused(f"The export schema {document.get('schema')!r} is not {rft.SCHEMA}.")
    if (document.get("request") or {}).get("parameterization") != rft.FREE:
        raise PreflightRefused("The export is not an orthotropic (E1, E2, G12) tuning.")
    if (document.get("inputs") or {}).get("inp_sha256") != inp_sha256:
        raise PreflightRefused("The export was made from a different INP (SHA-256 differs).")
    if document.get("status") != rft.MIRROR:
        raise PreflightRefused(f"The export status is {document.get('status')!r}, not the two-minimum {rft.MIRROR}.")
    minima = document.get("minima")
    if not isinstance(minima, list) or len(minima) != 2:
        raise PreflightRefused(f"The export holds {len(minima) if isinstance(minima, list) else 'no'} minima; exactly two are needed.")
    out = []
    for label, item in zip(("A", "B"), minima):
        values = (item or {}).get("values") or {}
        cost = (item or {}).get("cost")
        try:
            values = {name: float(values[name]) for name in TARGETS}
            cost = float(cost)
        except (KeyError, TypeError, ValueError) as exc:
            raise PreflightRefused(f"Minimum {label} lacks E1, E2, G12 or its cost.") from exc
        if not all(math.isfinite(v) and v > 0 for v in values.values()) or not math.isfinite(cost):
            raise PreflightRefused(f"Minimum {label} is not finite and positive.")
        out.append(Minimum(label, values, cost))
    if not out[0].cost <= out[1].cost:
        raise PreflightRefused("The minima are not in ascending cost order; A is not identifiable.")
    if max(abs(out[0].values[k] / out[1].values[k] - 1.0) for k in TARGETS) <= DISTINCT:
        raise PreflightRefused("The two minima are the same point; there is no second minimum.")
    axes = document.get("axis_assignments") or []
    if len(axes) != 2:
        raise PreflightRefused("The export has no two axis assignments to confirm the minima.")
    for minimum, axis in zip(out, axes):
        shown = (axis.get("E1 (FE X)"), axis.get("E2 (FE Y)"), axis.get("G12"))
        if axis.get("assignment") != f"assignment {minimum.label}" or shown != tuple(minimum.values[k] for k in TARGETS) \
                or axis.get("cost") != minimum.cost:
            raise PreflightRefused(f"Axis assignment {minimum.label} does not match minimum {minimum.label}.")
    fitted = document.get("fitted") or {}
    if any(fitted.get(k) != out[0].values[k] for k in TARGETS):
        raise PreflightRefused("The export's fitted values are not minimum A.")
    return tuple(out)


# ------------------------------------------------------------------------------------------------ verification


def verify_variant(original: bytes, variant: bytes, values: Mapping[str, float]) -> list:
    """Static checks of one variant against the original: (name, passed, detail) per check."""
    checks = []

    def check(name, passed, detail=""):
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    a, b = _lines(original), _lines(variant)
    check("line count unchanged", len(a) == len(b), f"{len(a)} / {len(b)}")
    try:
        block_a, block_b = elastic_block(a), elastic_block(b)
    except PreflightRefused as exc:
        check("one supported *Elastic in both decks", False, str(exc))
        return checks
    check("one supported *Elastic in both decks", True)
    changed = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    check("only the first *Elastic data line differs", changed == [block_a.data_indexes[0]] and len(a) == len(b),
          f"changed lines {[i + 1 for i in changed][:10]}")
    check("line endings unchanged", all(x[len(_body(x)):] == y[len(_body(y)):] for x, y in zip(a, b)))
    for name in TARGETS:
        check(f"{name} written exactly", block_b.values[name] == float(values[name]),
              f"{block_b.values[name]!r} (expected {float(values[name])!r})")
    for name in FIELDS:
        if name not in TARGETS:
            check(f"{name} unchanged", block_b.values[name] == block_a.values[name], repr(block_b.values[name]))
    items_a, items_b = _body(a[block_a.data_indexes[0]]).split(","), _body(b[block_b.data_indexes[0]]).split(",")
    check("non-target items unchanged as text", len(items_a) == len(items_b) and all(
        items_a[i] == items_b[i] for i in range(len(items_a)) if i >= 8 or FIELDS[i] not in TARGETS))
    check("second *Elastic data line unchanged as text", a[block_a.data_indexes[1]] == b[block_b.data_indexes[1]])
    sa, sb = structure(original), structure(variant)
    for key in sorted(set(sa) | set(sb)):
        check(f"structure: {key}", sa.get(key) == sb.get(key))
    return checks


def unified_diff(original: bytes, variant: bytes, original_name: str, variant_name: str) -> str:
    return "".join(difflib.unified_diff([_body(x) + "\n" for x in _lines(original)], [_body(x) + "\n" for x in _lines(variant)],
                                        original_name, variant_name, n=1))


def _parsed(path: Path, base: rft.AbaqusPlateInputs, values: Mapping[str, float]) -> list:
    """The deck read back through the tuning service's own INP reader."""
    read = rft.read_inp(path)
    checks = []
    for name in TARGETS:
        checks.append({"check": f"read_inp {name}", "passed": getattr(read, name) == values[name], "detail": repr(getattr(read, name))})
    for name in ("E3", "nu12", "nu13", "nu23", "G13", "G23", "density_t_mm3", "thickness_mm", "a_mm", "b_mm", "material",
                 "elastic_type", "has_orientation"):
        checks.append({"check": f"read_inp {name} unchanged", "passed": getattr(read, name) == getattr(base, name),
                       "detail": repr(getattr(read, name))})
    return checks


def _failed(checks) -> list:
    return [c for c in checks if not c["passed"]]


# ------------------------------------------------------------------------------------------------ preparation


def prepare(export_path, inp_path, out_dir, other_sources: Sequence = (), reproduction: Optional[Mapping] = None) -> dict:
    """Write the two trial decks and their manifest into ``out_dir``. Refuses on any failed check; writes no source file."""
    export_path, inp_path, out_dir = Path(export_path), Path(inp_path), Path(out_dir)
    sources = [inp_path, export_path] + [Path(p) for p in other_sources]
    before = {str(p): sha256_file(p) for p in sources}
    targets = [out_dir / name for _label, name in VARIANTS] + [out_dir / MANIFEST]
    resolved_sources = {p.resolve() for p in sources}
    if out_dir.resolve() == inp_path.resolve().parent or any(t.resolve() in resolved_sources for t in targets):
        raise PreflightRefused("The output folder must not be the source deck's folder or hold a source file.")
    existing = [str(t) for t in targets if t.exists()]
    if existing:
        raise PreflightRefused(f"Output files already exist and are never overwritten: {existing}")
    original = inp_path.read_bytes()
    if sha256_bytes(original) != before[str(inp_path)]:
        raise PreflightRefused("The INP changed while it was read.")
    document = json.loads(export_path.read_text(encoding="utf-8"))
    minima = minima_from_export(document, before[str(inp_path)])
    elastic_block(_lines(original))
    try:
        base = rft.read_inp(inp_path)
    except rft.TuningRefused as exc:
        raise PreflightRefused(f"The tuning service cannot read the INP: {exc}") from exc
    axes = material_axes(original)
    built = []
    for minimum, (_label, name) in zip(minima, VARIANTS):
        variant = build_variant(original, minimum.values)
        checks = verify_variant(original, variant, minimum.values)
        if _failed(checks):
            raise PreflightRefused(f"Variant {minimum.label} fails the static preflight: {_failed(checks)}")
        built.append((minimum, name, variant, checks))
    if built[0][2] == built[1][2]:
        raise PreflightRefused("The two variants are identical.")
    out_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for minimum, name, variant, checks in built:
        path = out_dir / name
        with open(path, "xb") as handle:  # exclusive create: never overwrite
            handle.write(variant)
        written = path.read_bytes()
        checks = checks + [{"check": "written bytes equal the verified bytes", "passed": written == variant, "detail": ""}]
        checks += verify_variant(original, written, minimum.values) + _parsed(path, base, minimum.values)
        records.append({
            "label": minimum.label, "file": str(path), "sha256": sha256_bytes(written), "bytes": len(written),
            "source_minimum": {"values": dict(minimum.values), "cost": minimum.cost,
                               "assignment": f"assignment {minimum.label}: E1 along FE X, E2 along FE Y"},
            "elastic_line_written": _body(_lines(written)[elastic_block(_lines(written)).data_indexes[0]]),
            "checks": checks, "failed": _failed(checks),
            "diff_against_original": unified_diff(original, written, inp_path.name, name),
        })
    after = {str(p): sha256_file(p) for p in sources}
    original_elastic = elastic_block(_lines(original)).values
    manifest = {
        "schema": SCHEMA, "label": LABEL, "abaqus": ABAQUS_RUN,
        "status": "PREFLIGHT_PASSED" if not any(r["failed"] for r in records) and before == after else "PREFLIGHT_FAILED",
        "statement": ("Static preparation only. The decks are the original INP with E1, E2 and G12 replaced by the two "
                      "Kirchhoff-Ritz research minima. They are not FE results, not material properties and not calibration "
                      "values; no Abaqus job has run, so nothing is known yet about their FE frequencies."),
        "sources": [{"path": k, "sha256": v} for k, v in before.items()],
        "sources_unchanged": before == after,
        "export": {"path": str(export_path), "schema": document.get("schema"), "label": document.get("label"),
                   "status": document.get("status"), "request": document.get("request"), "sources": document.get("sources")},
        "original": {"elastic": dict(original_elastic), "structure": structure(original)},
        "material_axes": axes,
        "variants": records,
        "reproduction": dict(reproduction) if reproduction else None,
    }
    with open(out_dir / MANIFEST, "x", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=1, ensure_ascii=False)
    if manifest["status"] != "PREFLIGHT_PASSED":
        raise PreflightRefused("The written decks failed the preflight; see the manifest.")
    return manifest
