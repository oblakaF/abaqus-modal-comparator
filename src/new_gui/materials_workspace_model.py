"""GUI-UX-R1: the facts the Materials page can state about two chosen files, with no Qt.

Read-only. The FE facts come from an already extracted package (its manifest and geometry file; the mode files are not read
and Abaqus is never started). The extraction stores no material, section, layup, density, thickness or length unit, so none
of them is shown or guessed. The page computes no material value, runs no iteration and starts no solver.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path

from new_gui import analyze_model as am
from new_gui import preview_model as pm
from new_gui.workspace_state import EXPERIMENTAL
from services import odb_import_service as svc

NOT_STORED = "Not in the extracted data"
NO_PACKAGE = ("No extracted modes were found for this ODB, so its geometry is not shown. Run Analyze for this ODB first. "
              "This page never starts Abaqus.")
MATERIAL_STATEMENT = ("The extracted FE data hold no material names, sections, layups, E1, E2, G12, density, thickness or "
                      "units, and this program does not guess them. To show them, a separate INP or CAE source would be "
                      "required, or an extended ODB extraction with Abaqus Python, separately authorized.")
PROPERTY_HEADERS = ("Property", "FE input", "Independent measurement", "Identified / calibrated")
INPUT_PROPERTIES = ("Material names", "Sections and layups", "E1, E2, G12", "Density", "Thickness", "Length unit")
NOT_PROVIDED, NOT_ISSUED = "None provided", "Not issued"
WORKFLOW = ("1. Load the specimen FE model and experimental modal dataset.",
            "2. Inspect actual input properties and geometry.",
            "3. Select a scientifically approved calibration parameter set.",
            "4. Establish physical registration and modal identity.",
            "5. Run explicitly authorized FE iterations.",
            "6. Evaluate frequency residuals, holdout results, uncertainty and model-form sensitivity.",
            "7. Report either a supported result or a scientific refusal.")
WORKFLOW_TITLE = "Single-plate model calibration: future workflow, not available now"
STATUS_TEXT = ("Current scientific status: this page runs no optimizer, FE iteration or solver, and it issues no number. "
               "Frequency agreement does not establish a material value. A model-specific calibration is not an identified "
               "material property.")


def property_rows() -> tuple:
    return tuple((name, NOT_STORED, NOT_PROVIDED, NOT_ISSUED) for name in INPUT_PROPERTIES)


@dataclass(frozen=True)
class Facts:
    rows: tuple  # (caption, value)
    note: str = ""


def _fmt(value: float) -> str:
    return f"{value:.6g}"


def geometry_facts(manifest: Path, cancel_event=None) -> tuple:
    """Node count, instances and extents from the package's geometry file, streamed; the mode files are not opened."""
    document = json.loads(Path(manifest).read_text(encoding="utf-8"))
    path = Path(manifest).parent / document["geometry_file"]
    low, high = [math.inf] * 3, [-math.inf] * 3
    instances, count = set(), 0
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            count += 1
            if cancel_event is not None and count % 65536 == 0 and cancel_event.is_set():
                raise am.StepCancelled()
            instances.add(row.get("instance") or "")
            for axis, key in enumerate("xyz"):
                value = float(row[key])
                low[axis], high[axis] = min(low[axis], value), max(high[axis], value)
    rows = [("Extracted modes", f"{document.get('start_mode', '?')} to {document.get('end_mode', '?')}"),
            ("Step", str(document.get("step_name") or "not recorded")),
            ("Analysis title", str(document.get("analysis_title") or "not recorded")),
            ("Nodes", str(count)), ("Instances", ", ".join(sorted(i for i in instances if i)) or "not recorded")]
    if count:
        rows += [(f"{key} extent", f"{_fmt(low[axis])} to {_fmt(high[axis])} (size {_fmt(high[axis] - low[axis])})")
                 for axis, key in enumerate("XYZ")]
    rows.append(("Units", "Not stated by the extracted data"))
    return tuple(rows)


def beside_odb(odb: Path) -> tuple:
    """Files with the ODB's name beside it, named only; they are not opened."""
    return tuple(candidate.name for candidate in (odb.with_suffix(".inp"), odb.with_suffix(".cae")) if candidate.is_file())


def read_fe_facts(odb, cancel_event, say=None) -> Facts:
    """Find the package of this ODB's content (hashing it, as Analyze does) and state its geometry. Starts no process."""
    odb = Path(odb)
    try:
        identity = svc.hash_file(odb, cancel_event, say)
        folder = am.package_folder(odb)
        found = (svc.existing_packages(folder, identity["sha256"], am.FIRST_MODE, am.LAST_MODE)
                 or svc.existing_packages(folder, identity["sha256"], am.FIRST_MODE, am.LAST_MODE, covering=True))
    except svc.OdbImportCancelled as error:
        raise am.StepCancelled() from error
    except (svc.OdbImportRefused, OSError) as error:
        raise am.StepFailed(f"The ODB could not be read: {error}") from error
    files = beside_odb(odb)
    note = f"Beside the ODB, not read: {', '.join(files)}." if files else "No INP or CAE file with this name is beside the ODB."
    if not found:
        return Facts((("Extracted modes", "None found"),), f"{NO_PACKAGE} {note}")
    return Facts(geometry_facts(found[0] / "manifest.json", cancel_event), note)


def experimental_facts(preview) -> Facts:
    rows = [("File", Path(preview.selected_path).name), ("Dataset types", ", ".join(str(x) for x in preview.dataset_types) or "none"),
            ("Geometry nodes", str(preview.geometry_node_count)), ("Modal sets", str(len(preview.sets)))]
    for item in preview.sets:
        points = max((record.point_count for record in item.records), default=0)
        dofs = max((record.measured_dof_count for record in item.records), default=0)
        peak = any(record.provisional for record in item.records)
        rows.append((item.title, f"{points} points, {dofs} measured DOFs" + ("; FRF peak — not fitted" if peak else "")))
    rows.append(("Units", "Not stated by the data read"))
    return Facts(tuple(rows))


def read_experimental_facts(path, cancel_event) -> Facts:
    outcome = pm.run_read(EXPERIMENTAL, path, 0, cancel_event)
    if outcome.cancelled or cancel_event.is_set():
        raise am.StepCancelled()
    if outcome.error:
        raise am.StepFailed(outcome.error)
    return experimental_facts(outcome.preview)


def saved_facts(document: dict) -> tuple:
    """From a saved result's own file: no path named in it is looked at."""
    fe_modes, modes = document["modes"]["fe"], document["modes"]["experimental"]
    fe = Facts((("Extracted modes when saved", f"{len(fe_modes)}"), ("Units", "Not stated by the extracted data")),
               "From the saved file. The source files were not looked at.")
    experimental = Facts((("Modal set when saved", document["modal_set"]["title"]), ("Records when saved", str(len(modes)))),
                         "From the saved file. The source files were not looked at.")
    return fe, experimental


__all__ = ["Facts", "MATERIAL_STATEMENT", "PROPERTY_HEADERS", "STATUS_TEXT", "WORKFLOW", "WORKFLOW_TITLE", "experimental_facts",
           "geometry_facts", "property_rows", "read_experimental_facts", "read_fe_facts", "saved_facts"]
