"""TRIAL-MAC-EXPORT-1: one ZIP archive of a completed exploratory trial (``services.trial_point_mac``).

Export only. Every number written is read from the given ``TrialRun`` and its ``Trial`` records: no MAC is computed, no
point is mapped, no placement is chosen or put in an order of preference, and no source file is copied. A rejected
placement is recorded with its reason and gets no matrix and no assumed node.

The archive is written to a temporary file beside the destination and takes its name only when it is complete. An
existing file is never replaced, and nothing is left behind when the export fails.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from typing import Callable, Mapping, Optional
import zipfile

import numpy as np

from services import trial_point_mac as tp

SCHEMA = "trial-mac-export/1"
UNCONFIRMED = "UNCONFIRMED"
NOT_VERIFIED = "not verified by this export"
README, MANIFEST, PLACEMENTS, POINTS, FAMILIES, MATRICES = ("README.txt", "manifest.json", "placements.csv",
                                                           "point_mapping.csv", "families.csv", "matrices")
NOT_STATEMENTS = ("a physically confirmed registration", "verified modal pairs", "accepted material properties",
                  "a production Auto-ID result")
PLACEMENT_HEADERS = ("status", "placement", "fe_face", "fe_face_z", "scan_z_along_fe_z", "quarter_turns", "shift_x",
                     "shift_y", "grid_axis_a_in_fe_xy", "grid_axis_b_in_fe_xy", "determinant", "points",
                     "points_inside_and_near_a_node", "different_fe_nodes", "rms_distance", "max_distance",
                     "distance_limit", "edge_margin", "usable", "rejection_reason", "matrix_file")
POINT_HEADERS = ("status", "placement", "placement_state", "point_order", "exp_point_id", "assumed_fe_node_id",
                 "placed_fe_x", "placed_fe_y", "assumed_fe_face_z")
FAMILY_HEADERS = ("status", "family", "placement")
FACE_SIGN = dict(tp.FACES)


class ExportRefused(ValueError):
    """Nothing was exported; the text says why."""


def _number(value) -> str:
    """A float at full precision (shortest text that reads back to the same value); empty when it is not finite."""
    value = float(value)
    return repr(value) if np.isfinite(value) else ""


def _csv(headers, rows) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return out.getvalue().encode("utf-8-sig")  # the label holds a dash outside ASCII; spreadsheet programs need the mark


def matrix_name(trial) -> str:
    return f"{MATRICES}/{trial.name}.csv"


def _letter(index: int) -> str:
    return chr(ord("A") + index) if index < 26 else str(index + 1)


def placement_rows(run) -> list:
    limit = _number(run.half_mesh_diagonal)
    return [(run.label, t.name, t.face, _number(run.faces[t.face]), f"{FACE_SIGN[t.face]:+g}", t.turn, _number(t.shift[0]),
             _number(t.shift[1]), ";".join(_number(v) for v in t.grid_a), ";".join(_number(v) for v in t.grid_b),
             _number(t.determinant), t.points, t.valid_points, t.unique_nodes, _number(t.rms_distance),
             _number(t.max_distance), limit, _number(t.edge_margin), "yes" if t.usable else "no", t.rejected_because,
             matrix_name(t) if t.usable else "") for t in run.trials]


def point_rows(run) -> list:
    rows = []
    for t in run.trials:
        state = "mapped under this assumption" if t.usable else f"rejected: {t.rejected_because}"
        face_z = _number(run.faces[t.face])
        for order, point in enumerate(run.point_ids):
            node = t.node_ids[order] if t.usable else ""  # a rejected placement maps no point
            rows.append((UNCONFIRMED, t.name, state, order + 1, point, node, _number(t.placed[order, 0]),
                         _number(t.placed[order, 1]), face_z))
    return rows


def family_rows(run) -> list:
    return [(run.label, _letter(index), name) for index, names in enumerate(run.families) for name in names]


def matrix_csv(run, trial) -> bytes:
    """Rows are the experimental modes, columns the FE modes, as ``trial.mac`` holds them."""
    corner = f"{run.label} | placement {trial.name} | rows: EXP mode, columns: FE mode"
    headers = (corner, "EXP frequency (Hz)") + tuple(
        f"FE {n} ({_number(f)} Hz)" for n, f in zip(run.fe_numbers, run.fe_frequencies))
    rows = [(f"EXP {n}", _number(f), *(_number(v) for v in row))
            for n, f, row in zip(run.experimental_numbers, run.experimental_frequencies, trial.mac)]
    return _csv(headers, rows)


def _readme(run, provenance: Mapping) -> str:
    usable = len(run.usable)
    grid = run.grid
    sources = provenance.get("sources") or {}
    lines = [
        run.label,
        "=" * len(run.label),
        "",
        "What this archive is",
        "--------------------",
        "The results of the exploratory Trial MAC of Abaqus Modal Comparator, exactly as the program calculated them.",
        "The measured grid was placed on the FE model in a fixed set of assumed ways, and for each of them the measured",
        "mode shapes were compared with the FE mode shapes (MAC: 1 = the same shape, near 0 = unrelated shapes).",
        "",
        "What this archive is NOT",
        "------------------------",
        "Every placement here is an assumption that nobody has confirmed. These results are not:",
        *(f"  - {text};" for text in NOT_STATEMENTS[:-1]),
        f"  - {NOT_STATEMENTS[-1]}.",
        "No placement is selected, preferred or put in an order by its MAC values. A large MAC value does not show",
        "that a placement is the physical one, and nearby frequencies do not show that two modes are the same mode.",
        "Which placement is physical can only be settled by independent physical evidence (which face was measured,",
        "how the grid was turned and where it lay on the specimen).",
        "",
        "This calculation",
        "----------------",
        f"  Measured points: {len(run.point_ids)} (grid {grid['counts'][0]} x {grid['counts'][1]}, pitch "
        f"{grid['pitch']:.4f} FE units, turned {grid['theta_deg']:.2f} deg in the scan plane)",
        f"  Experimental modes: {len(run.experimental_numbers)}; elastic FE modes: {len(run.fe_numbers)}",
        f"  Placements: {len(run.trials)}; mapped every point: {usable}; rejected: {len(run.trials) - usable}",
        f"  Source files: {sources.get('verification', NOT_VERIFIED)}",
        "",
        "Assumptions",
        "-----------",
        f"  - Measured coordinates are multiplied by {run.scale:g} to give FE units (metres to millimetres).",
        "  - Only the measured Z component is used, at every point of every mode.",
        f"  - Placements: {len(tp.FACES)} faces (T: the FE face of largest Z, scan +Z along FE +Z; B: the FE face of",
        f"    smallest Z, scan +Z along FE -Z) x {len(tp.TURNS)} quarter turns x {len(tp.SHIFTS)} positions (C: the grid",
        "    centre on the centre of the FE outline, which is itself an assumption; X+5, X-5, Y+5, Y-5: shifts of 5 FE",
        "    units). A placement name is face, quarter turns, position: for example T1_X+5.",
        "  - Each measured point takes the nearest FE node of the assumed face. A placement is used only when every",
        "    point is inside the FE outline, within half a mesh diagonal of its node and on a node of its own.",
        "  - No point is dropped, no reflection is used and the grid is not stretched.",
        "",
        "Files",
        "-----",
        f"  {MANIFEST}      identities of the source files, the modal set, the assumptions, the modes and frequencies",
        f"  {PLACEMENTS}     every placement: geometric checks, distances (FE units), usable or rejected and why",
        f"  {POINTS}  for every placement: experimental point, ASSUMED FE node, placed FE coordinates.",
        "                     Every row is an unconfirmed mapping. A rejected placement has no assumed node.",
        f"  {FAMILIES}       centred placements whose matrices are numerically equal (within {tp.FAMILY_TOLERANCE:g} in",
        "                     every entry). The letters follow the fixed order of the placements; they are not a preference.",
        f"  {MATRICES}/<placement>.csv  the MAC matrix of each usable placement at full precision: rows are experimental",
        "                     modes, columns are FE modes. An empty cell is a value that is not defined.",
        "                     A rejected placement has no matrix file.",
        "",
        "Limitations",
        "-----------",
        "  - The original ODB / UNV / UFF files are not in this archive.",
        "  - Identities marked as not verified were recorded earlier and were not checked again by this export.",
        "  - Placements that differ only by a symmetry of the mode shapes give equal matrices and cannot be told apart",
        "    by these numbers.",
        "",
        run.label,
        "",
    ]
    return "\n".join(lines)


def _manifest(run, provenance: Mapping, members: Mapping, created: str) -> dict:
    grid = run.grid
    return {
        "schema": SCHEMA,
        "label": run.label,
        "status": "exploratory; every placement is an unconfirmed assumption",
        "these_results_are_not": list(NOT_STATEMENTS),
        "selection": "no placement is selected, preferred or ordered by MAC",
        "created_utc": created,
        "sources": dict(provenance.get("sources") or {"verification": NOT_VERIFIED}),
        "source_files_included": False,
        "modal_set": dict(provenance.get("modal_set") or {}),
        "rigid_body_fe_modes_excluded": list(provenance.get("rigid_body_fe_modes") or ()),
        "assumptions": {
            "experimental_to_fe_scale": run.scale,
            "measured_component": "Z alone, at every point of every mode",
            "node_choice": "nearest FE node of the assumed face",
            "distance_limit_half_mesh_diagonal": run.half_mesh_diagonal,
            "family_tolerance": tp.FAMILY_TOLERANCE,
            "faces": {name: {"fe_z": run.faces[name], "scan_z_along_fe_z": sign} for name, sign in tp.FACES},
            "quarter_turns": list(tp.TURNS),
            "positions": {name: [dx, dy] for name, dx, dy in tp.SHIFTS},
            "centre": "the grid centre on the centre of the FE outline (an assumption)",
            "every_transform_determinant": 1,
        },
        "measured_grid": {"points": len(run.point_ids), "counts": list(grid["counts"]), "pitch": grid["pitch"],
                          "theta_deg": grid["theta_deg"], "extent": list(grid["extent"])},
        "experimental_modes": [{"number": int(n), "frequency_hz": float(f)}
                               for n, f in zip(run.experimental_numbers, run.experimental_frequencies)],
        "fe_modes": [{"number": int(n), "frequency_hz": float(f)} for n, f in zip(run.fe_numbers, run.fe_frequencies)],
        "placements": {"count": len(run.trials), "usable": [t.name for t in run.trials if t.usable],
                       "rejected": {t.name: t.rejected_because for t in run.trials if not t.usable}},
        "families": [list(names) for names in run.families],
        "files": {name: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in members.items()},
    }


def build_files(run, provenance: Optional[Mapping] = None, created: Optional[str] = None) -> dict:
    """{archive name: bytes} for ``run``, in the order they are written. ``provenance`` is recorded as given."""
    if run is None or not getattr(run, "trials", None):
        raise ExportRefused("There is no completed trial to export.")
    provenance = provenance or {}
    members = {PLACEMENTS: _csv(PLACEMENT_HEADERS, placement_rows(run)), POINTS: _csv(POINT_HEADERS, point_rows(run)),
               FAMILIES: _csv(FAMILY_HEADERS, family_rows(run))}
    for trial in run.trials:
        if trial.usable and trial.mac is not None:
            members[matrix_name(trial)] = matrix_csv(run, trial)
    created = created or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = json.dumps(_manifest(run, provenance, members, created), indent=1, ensure_ascii=False).encode("utf-8")
    return {README: _readme(run, provenance).encode("utf-8-sig"), MANIFEST: manifest, **members}


# Where hard links are missing, only a rename that can never replace a file is used instead: that is the Windows rename.
_RENAME_NEVER_REPLACES = os.name == "nt"


def _publish(temporary: str, target: Path) -> None:
    """Give the finished file its name without ever replacing a file that is there, and without ever leaving anything
    under that name when the step fails: each way used is one atomic step that fails when the name is taken."""
    exists = ExportRefused(f"{target} already exists and is not replaced. Choose a new name.")
    try:
        os.link(temporary, target)  # atomic, and fails when the name is taken
        return
    except FileExistsError as error:
        raise exists from error
    except OSError as error:  # a file system without hard links
        no_links = error
    if os.path.lexists(target):
        raise exists from no_links
    if not _RENAME_NEVER_REPLACES:
        raise ExportRefused(f"The archive was not written to {target}: this folder's file system cannot give a new file its "
                            f"name without the risk of replacing another file ({no_links}). Choose a folder on another "
                            "drive.") from no_links
    try:
        os.rename(temporary, target)  # on Windows a rename never replaces
    except FileExistsError as error:
        raise exists from error


def write_archive(path, run, provenance: Optional[Mapping] = None, verify: Optional[Callable[[], None]] = None) -> Path:
    """Write the archive of ``run`` to the new file ``path``. ``verify`` runs once the archive is complete and before it
    takes its name; whatever it raises leaves no file. Raises ``ExportRefused`` with the reason."""
    target = Path(path)
    if target.exists():
        raise ExportRefused(f"{target} already exists and is not replaced. Choose a new name.")
    files = build_files(run, provenance)
    temporary = None
    try:
        handle, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".partial", dir=target.parent)
        with os.fdopen(handle, "wb") as stream, zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.comment = run.label.encode("utf-8")
            for name, data in files.items():
                archive.writestr(name, data)
        if verify is not None:
            verify()
        _publish(temporary, target)
    except ExportRefused:
        raise
    except OSError as error:
        raise ExportRefused(f"The archive could not be written to {target} ({error}).") from error
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass
    return target


__all__ = ["ExportRefused", "SCHEMA", "build_files", "matrix_name", "write_archive"]
