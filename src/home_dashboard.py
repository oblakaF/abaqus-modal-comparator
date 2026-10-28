"""APP-UI.1: the Home screen of the main window (a friendly overview; the 11 expert tabs are unchanged).

The Home screen shows four areas:

- source data;
- analysis readiness;
- results;
- material properties.

Below them, APP-CATALOG.1 adds a fifth, read-only area: the passport of one physical specimen from the accepted
specimen catalogue (``services.specimen_catalog_view``). Choosing a specimen there only shows its passport. It
selects no file, modal set or registration and changes no analysis state.

APP-CATALOG.2 adds *Local source selection* to that area: the user picks one FE or experimental source of the
specimen, locates a local copy with the standard file dialog, and the copy is checked against the catalogue
(``services.specimen_catalog_local_files``). Only an explicit **Use as FE input** / **Use as experimental input** sets
one field of 1. Files, exactly as its Browse button does (the variable's existing traces react).

APP-WORKSPACE.2 adds *Current workspace* between the four areas and the passport. It shows the state of the program
through the headless model ``services.workspace_context``:

- the user's own data, with an optional label of the user's (never looked up in any archive);
- the FE and experimental files and the modal set currently set in the program;
- the state of the analysis result;
- the registration that result applied, and the production Auto-ID block.

With no file chosen it shows an empty workspace that asks for the two files. Any supported FE / UNV / UFF file is a
workspace, whether or not the laboratory archive records it, and nothing of the archive (modal-set status,
registration, scientific status) is attributed to it (APP-WORKSPACE.2-F1). The registration kind is never inferred:
a result records the hash of the registration it applied, not its basis, so that is shown as UNKNOWN.

The specimen catalogue (the research archive of SP-01 ... SP-15) is not shown by default: only the explicit
**Open research archive...** shows it, and its data are unchanged.

It owns no data and starts no computation of its own. Every action calls the existing handlers of the main window:

- file choice: ``_choose_abaqus`` / ``_choose_experiment``;
- modal-set choice: ``_experimental_modal_set_selected``;
- analysis: ``_start`` / ``_request_stop``.

Every value shown is read from the window's existing state:

- the input variables and the modal-set discovery state;
- ``analysis_state``, ``status``, ``result`` and the diagnostic export source;
- the metric cards of 2. Comparison table;
- the material-identification evidence and Auto-ID selection.

So an invalidated or stale result disappears from Home exactly when it disappears from the expert tabs. No material
property value is shown: this version identifies none.
"""

from __future__ import annotations

import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from services import specimen_catalog_local_files as local_files
from services import specimen_catalog_view as catalogue_view
from services import workspace_context as workspace
from ui_policy import AnalysisState, EM_DASH, LayoutMode, responsive_layout_width, select_layout_mode

HOME, EXPERT = "home", "expert"
OK, NEEDED, WARN, WAIT, INFO = "ok", "needed", "warn", "wait", "info"
MARKS = {OK: "✔", NEEDED: "✖", WARN: "⚠", WAIT: "…", INFO: "ℹ"}
COLOURS = {OK: "#1E7B34", NEEDED: "#B3261E", WARN: "#8A5A00", WAIT: "#8A5A00", INFO: "#2F5D8A"}
# the input variables whose change refreshes Home (the result itself is followed through ``status``)
WATCHED_VARIABLES = (
    "status", "abaqus_path", "experimental_path", "experimental_modal_set_display", "experimental_modal_set_key",
    "experimental_modal_set_summary", "abaqus_installation_label", "abaqus_model_unit",
    "experimental_coordinate_unit", "start_mode", "end_mode",
)
MATERIAL_STATUS = (
    "Not determined. This version does not identify material properties: production Auto-ID is not authorised "
    "({state}). No elastic constant (E1, E2, G12, ...) is shown as identified anywhere in the program; the expert "
    "section shows readiness checks and evidence only."
)
NO_RESULT_TEXT = "No analysis result yet. Choose both files, then run the analysis."
DIAGNOSTIC_TEXT = (
    "Frequency-only diagnostic: the physical orientation of the measurement could not be established, so no mode "
    "pairs and no MAC were computed. The FE and measured frequencies can be compared side by side only."
)
EXPERIMENT_UNUSABLE_TEXT = (
    "No comparison: the experimental file gave no usable modal or FRF data, so nothing can be compared. Only the FE "
    "frequencies and mode shapes are available (3. Mode shapes). Reason: {reason}"
)
FREQUENCY_ONLY, EXPERIMENT_UNUSABLE = "frequency_only", "experiment_unusable"
CATALOGUE_SUBTITLE = (
    "The recorded facts of a real specimen, from the accepted specimen catalogue. Viewing a passport selects no "
    "file, modal set or registration and changes nothing in the analysis; the catalogue and the input file registry "
    "(File menu) are separate."
)
CATALOGUE_PROMPT = "Choose a specimen to view its passport."
LOCAL_SOURCE_PROMPT = (
    "Choose one recorded source, then Locate local file... to check your own copy against the catalogue. Only Use as "
    "FE input / Use as experimental input changes a field of 1. Files; nothing is loaded or run."
)
CHECK_STATES = {local_files.BYTE_VERIFIED: OK, local_files.NOT_VERIFIED_NO_REFERENCE: WARN}
NO_REFERENCE_WARNING = (
    "The catalogue records no SHA-256 for {name}, so {file} cannot be byte-verified: it may not be the recorded file "
    "at all.\n\nUse it as the {field} file anyway? It will not be called verified, and no modal set, registration or "
    "FE-experiment pairing is chosen."
)
WORKSPACE_SUBTITLE = (
    "The data you are working with: the FE and experimental files, the modal set, the analysis result and its "
    "registration, as currently set in the program. No laboratory archive record is needed."
)
EMPTY_WORKSPACE_TEXT = (
    "No data loaded yet. Choose an FE results file (an Abaqus .odb or an extracted manifest.json) and an "
    "experimental file (a Simcenter Testlab .unv / .uff) to start."
)
SPECIMEN_NAME_HINT = "Optional: your own label for this data. It is not looked up in any archive."
OPEN_ARCHIVE_TEXT, CLOSE_ARCHIVE_TEXT = "Open research archive...", "Close research archive"
# the result records of a frozen registration the analysis applied: (metadata key, how it was applied)
APPLIED_REGISTRATION_RECORDS = (
    ("governed_registration", "the accepted physical registration option"),
    ("geometry_verified_registration", "reuse by FE geometry identity"),
    ("guided_physical_registration", "the guided physical registration"),
)
REGISTRATION_STATES = {
    workspace.RegistrationKind.PHYSICAL: INFO, workspace.RegistrationKind.LEGACY_REPLAY: WARN,
    workspace.RegistrationKind.INCOMPLETE: WARN, workspace.RegistrationKind.NONE: INFO,
    workspace.RegistrationKind.UNKNOWN: WARN,
}


def _get(variable, default: str = "") -> str:
    try:
        return str(variable.get()).strip()
    except (tk.TclError, ValueError, AttributeError):
        return default


def short_path(path: Path, limit: int = 64) -> str:
    """A long folder shown as its start and its last two parts (a path has no spaces to wrap at)."""
    text = str(path)
    parts = path.parts
    if len(text) <= limit or len(parts) <= 3:
        return text
    return str(Path(parts[0], parts[1], "…", *parts[-2:]))


def describe_file(text: str, kind: str) -> tuple[str, str, str]:
    """(state, file name, explanation) of a chosen input path; only the path is checked, nothing is read."""
    if not text:
        hint = ("an Abaqus .odb or an extracted manifest.json" if kind == "fe"
                else "a Simcenter Testlab .unv / .uff file (or an .lms with its exported UNV/UFF beside it)")
        return NEEDED, "Not chosen", f"Choose {hint}."
    path = Path(text)
    if not path.exists():
        return NEEDED, path.name, f"The file is not found: {path}"
    if kind == "fe":
        if path.name.lower() == "manifest.json":
            note = "Extracted Abaqus results (no Abaqus run is needed)."
        elif path.suffix.lower() == ".odb":
            note = "Abaqus ODB: its modes are extracted with Abaqus when the analysis runs."
        else:
            note = "Abaqus results file."
    else:
        note = "Simcenter Testlab measurement file."
    return OK, path.name, f"{note}\nFolder: {short_path(path.parent)}"


def modal_set_state(app) -> tuple[str, str]:
    """(state, plain text) of the experimental modal set, from the existing modal-set discovery."""
    state = getattr(app, "_modal_set_discovery_state", "idle")
    sets = list(getattr(app, "available_experimental_modal_sets", []) or [])
    key = _get(getattr(app, "experimental_modal_set_key", None))
    if not _get(getattr(app, "experimental_path", None)):
        return NEEDED, "Choose the experimental file first."
    if state == "loading" or state == "idle":
        return WAIT, "Reading the modal sets of the experimental file..."
    if state == "error":
        return NEEDED, "The experimental file could not be inspected: " + _get(app.experimental_modal_set_summary)
    if not sets:
        return INFO, ("No fitted modal set in the file: its other modal records or FRF peaks are used "
                      "(FRF peaks are provisional, not validated modes).")
    if key in {item.key for item in sets}:
        return OK, _get(app.experimental_modal_set_display)
    if len(sets) > 1:
        return NEEDED, f"The file has {len(sets)} fitted modal sets: choose the one to compare."
    return OK, _get(app.experimental_modal_set_display)


def abaqus_state(app) -> tuple[str, str]:
    path = _get(getattr(app, "abaqus_path", None))
    if Path(path).suffix.lower() != ".odb":
        return INFO, "Not needed for extracted results (manifest.json)."
    installations = getattr(app, "_abaqus_installations", {}) or {}
    if installations:
        return OK, f"Found: {_get(app.abaqus_installation_label)}"
    return WARN, ("No Abaqus installation was found. An .odb needs Abaqus unless its modes were already extracted "
                  "into the output workspace; an extracted manifest.json needs none. Abaqus can be set in Expert mode "
                  "> 1. Files and analysis.")


MANIFEST_READ_LIMIT = 2_000_000  # bytes: Home reads the mode list of a small manifest.json only, never a mode file
_manifest_modes_cache: dict = {}


def manifest_mode_numbers(path: Path) -> tuple[Optional[list[int]], str]:
    """(mode numbers listed in an extraction manifest.json, problem). Only the manifest's own mode list is read; no
    geometry or mode file is opened. Cached per file state, so Home does not read it again on every refresh."""
    try:
        stat = path.stat()
    except OSError as error:
        return None, f"the file cannot be read ({error.__class__.__name__})"
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    if key not in _manifest_modes_cache:
        _manifest_modes_cache.clear()
        _manifest_modes_cache[key] = _read_manifest_modes(path, stat.st_size)
    return _manifest_modes_cache[key]


def _read_manifest_modes(path: Path, size: int) -> tuple[Optional[list[int]], str]:
    if size > MANIFEST_READ_LIMIT:
        return None, "the file is too large to be read here"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        entries = manifest["modes"]
        numbers = sorted({int(entry["mode"]) for entry in entries})
    except (OSError, UnicodeDecodeError, ValueError):
        return None, "the file is not a readable JSON extraction manifest"
    except (KeyError, TypeError):
        return None, "the file has no valid list of extracted modes"
    if not numbers:
        return None, "the file lists no extracted mode"
    return numbers, ""


def mode_number_text(numbers: list[int]) -> str:
    """Sorted mode numbers as runs: 6–15; 6–8, 10, 12–13 (a gap is never shown as one continuous range)."""
    runs, first = [], numbers[0]
    for previous, number in zip(numbers, numbers[1:] + [None]):
        if number is None or number != previous + 1:  # the run ends at ``previous``
            runs.append(str(first) if first == previous else f"{first}–{previous}")
            first = number
    return ", ".join(runs)


def fe_mode_row(app) -> tuple[str, str, str]:
    """(state, caption, text) of the FE modes: the extraction range of an .odb, the listed modes of a manifest."""
    path_text = _get(getattr(app, "abaqus_path", None))
    field = f"{_get(app.start_mode, '?')} to {_get(app.end_mode, '?')}"
    path = Path(path_text)
    if path_text and path.name.lower() == "manifest.json":
        if not path.is_file():
            return INFO, "FE modes", "Shown once the extraction manifest.json is found."
        numbers, problem = manifest_mode_numbers(path)
        if numbers is None:
            return WARN, "FE modes", (f"The extracted mode numbers could not be read from manifest.json: {problem}. "
                                      "The analysis reports what it can load.")
        count = f"{len(numbers)} mode{'s' if len(numbers) != 1 else ''}"
        return INFO, "FE modes", (f"Extracted modes listed in manifest.json: {mode_number_text(numbers)} ({count}). "
                                  f"The mode range of 1. Files ({field}) applies to an .odb extraction only.")
    if path_text and path.suffix.lower() == ".odb":
        return INFO, "FE modes", f"{field}: the modes to extract from the .odb when the analysis runs."
    return INFO, "FE modes", f"Mode range {field}: used when an .odb is extracted."


def readiness_rows(app) -> list[tuple[str, str, str]]:
    """(state, caption, text) rows of the readiness checklist."""
    rows = []
    for kind, caption, variable in (("fe", "Abaqus results", app.abaqus_path),
                                    ("experimental", "Experiment", app.experimental_path)):
        state, name, _ = describe_file(_get(variable), kind)
        text = name if state == OK else "Missing" if name == "Not chosen" else f"Not found: {name}"
        rows.append((state, caption, text))
    state, text = modal_set_state(app)
    rows.append((state, "Modal set", text))
    state, text = abaqus_state(app)
    rows.append((state, "Abaqus", text))
    rows.append((INFO, "Units", f"Abaqus model in {_get(app.abaqus_model_unit, '?')}, experiment in "
                                f"{_get(app.experimental_coordinate_unit, '?')}: you confirm them when you press Run."))
    rows.append(fe_mode_row(app))
    return rows


def readiness_verdict(app) -> tuple[str, str]:
    state = getattr(app, "analysis_state", AnalysisState.NO_DATA)
    if getattr(app, "running", False) or state in (AnalysisState.RUNNING, AnalysisState.STOPPING):
        return WAIT, f"The analysis is running: {_get(app.status)}"
    rows = readiness_rows(app)
    missing = [caption for row_state, caption, _ in rows if row_state == NEEDED]
    if any(row_state == WAIT for row_state, _, _ in rows):
        return WAIT, "Wait: the experimental file is being read."
    if missing:
        return NEEDED, "Not ready yet. Still needed: " + ", ".join(missing) + "."
    if any(row_state == WARN for row_state, _, _ in rows):
        return OK, "Ready: the analysis can be run (see the warning above)."
    return OK, "Ready: the analysis can be run."


def diagnostic_kind(app) -> Optional[str]:
    """The kind of the diagnostic shown, read from the loaded data of that analysis with the rule of the diagnostic
    report (no new classification): no experimental dataset = the experimental file was not usable
    (ExperimentalDataUnavailable); otherwise FREQUENCY_ONLY_DIAGNOSTIC (physical orientation not established)."""
    loaded = getattr(app, "_diagnostic_export_source", None)
    if loaded is None:
        return None
    return EXPERIMENT_UNUSABLE if getattr(loaded, "experimental", None) is None else FREQUENCY_ONLY


def result_links(app) -> set[str]:
    """The result views that show something for the result on display ("frequencies", "shapes", "mac")."""
    if getattr(app, "running", False):
        return set()
    if getattr(app, "result", None) is not None:
        return {"frequencies", "shapes", "mac"}
    kind = diagnostic_kind(app)
    if kind == FREQUENCY_ONLY:
        return {"frequencies", "shapes"}  # the frequencies side by side; each file's modes separately; no MAC
    if kind == EXPERIMENT_UNUSABLE:
        return {"shapes"}  # the FE modes only: no frequency comparison, no MAC
    return set()


def result_summary(app) -> tuple[str, str, list[tuple[str, str]]]:
    """(state, plain text, [(caption, value)]) of the result shown in the expert tabs."""
    state = getattr(app, "analysis_state", AnalysisState.NO_DATA)
    result = getattr(app, "result", None)
    if getattr(app, "running", False) or state in (AnalysisState.RUNNING, AnalysisState.STOPPING):
        return WAIT, "The analysis is running; the previous result is no longer shown.", []
    if result is not None:
        values = [(caption, _label_text(app, name)) for caption, name in (
            ("Matched mode pairs", "metric_pairs"), ("Mean frequency difference", "metric_error"),
            ("Mean MAC", "metric_mac"))]
        values.append((_label_text(app, "metric_geometry_caption").capitalize() or "State",
                       _label_text(app, "metric_geometry")))
        if result.pairs and state is AnalysisState.SUCCESS:
            return OK, ("Comparison complete: FE and measured modes are paired after the physical registration "
                        "(geometry) was established. Open the frequencies, the mode shapes or the MAC below."), values
        return INFO, ("Analysis complete, but the scientific acceptance checks were not satisfied: there are no "
                      "admissible mode pairs. See the details in Expert mode."), values
    kind = diagnostic_kind(app)
    if kind == EXPERIMENT_UNUSABLE:
        reason = str(getattr(app._diagnostic_export_source, "experimental_error", None) or "not stated")
        return INFO, EXPERIMENT_UNUSABLE_TEXT.format(reason=reason), [
            ("Experimental data", "not usable"), ("Mode pairs", "none"), ("MAC", "not computed")]
    if kind == FREQUENCY_ONLY:
        return INFO, DIAGNOSTIC_TEXT, [("Mode pairs", "none"), ("MAC", "not computed")]
    if state is AnalysisState.ERROR:
        return NEEDED, _get(app.status) or "The analysis could not be completed.", []
    if state is AnalysisState.DIAGNOSTIC:
        return INFO, _get(app.status), []
    notice = getattr(app, "_stale_result_notice", None)
    if notice:
        return NEEDED, str(notice), []
    if state is AnalysisState.STOPPED:
        return INFO, "The analysis was stopped. Run it again when ready.", []
    return INFO, NO_RESULT_TEXT, []


def _label_text(app, name: str) -> str:
    label = getattr(app, name, None)
    try:
        return str(label.cget("text")) if label is not None else EM_DASH
    except tk.TclError:
        return EM_DASH


def material_summary(app) -> list[tuple[str, str, str]]:
    """(state, caption, text) rows of the material-property area; no property value is ever shown."""
    from services.campaign_execution_plan import NOT_AUTHORISED

    model = getattr(app, "material_identification_evidence_view_model", None)
    names = ("sensitivity", "identifiability", "identification", "validation")
    present = [name for name in names if getattr(model, name, None) is not None]
    if present:
        bound = getattr(model, "model", None) is not None
        kind = (f"bound to model {getattr(model.model, 'model_id', '?')}" if bound
                else "historical, not bound to a model")
        evidence = f"{len(present)} of 4 evidence records loaded ({', '.join(present)}; {kind})."
    else:
        evidence = "No identification evidence is loaded in this session."
    selection = str(getattr(app, "auto_id_summary", None) or "No specimen or campaign is selected.")
    return [
        (NEEDED, "Material constants", MATERIAL_STATUS.format(state=NOT_AUTHORISED)),
        (INFO, "Existing evidence", evidence),
        (INFO, "Auto-ID selection", selection.splitlines()[0] if selection else selection),
    ]


def selected_modal_set_name(app) -> tuple[Optional[str], str]:
    """(the PolyMAX name of the selected modal set, or None; why it is not known).

    The name is the ``display_name`` of the one discovered set whose key is the selected key; the formatted text of
    the choice list is never parsed. No selection gives (None, ""); anything ambiguous gives (None, reason)."""
    key = _get(getattr(app, "experimental_modal_set_key", None))
    if not key:
        return None, ""
    sets = list(getattr(app, "available_experimental_modal_sets", []) or [])
    matches = [item for item in sets if getattr(item, "key", None) == key]
    if len(matches) != 1:
        return None, "the selected modal set could not be identified unambiguously in the discovered sets"
    name = getattr(matches[0], "display_name", None)
    if not isinstance(name, str) or not name.strip():
        return None, "the selected modal set has no recorded name"
    if sum(1 for item in sets if getattr(item, "display_name", None) == name) != 1:
        return None, f"the file holds more than one set named \"{name}\""
    return name, ""


def workspace_result(app) -> tuple[workspace.ResultState, str]:
    """(the result state for the workspace, a note). Pairs and MAC only for a successful result on display."""
    state = getattr(app, "analysis_state", AnalysisState.NO_DATA)
    if not isinstance(state, AnalysisState):
        state = AnalysisState.NO_DATA
    result = getattr(app, "result", None)
    notice = str(getattr(app, "_stale_result_notice", None) or "")
    if getattr(app, "running", False) or state in (AnalysisState.RUNNING, AnalysisState.STOPPING):
        return workspace.ResultState(AnalysisState.RUNNING if state is not AnalysisState.STOPPING else state), ""
    if state is AnalysisState.SUCCESS and result is not None:
        pairs = list(getattr(result, "pairs", None) or [])
        return workspace.ResultState(AnalysisState.SUCCESS, len(pairs),
                                     any(getattr(pair, "mac", None) is not None for pair in pairs)), ""
    if state is AnalysisState.SUCCESS:  # no result on display: nothing of a former one is carried over
        state = AnalysisState.NO_DATA
    return workspace.ResultState(state), notice


def applied_registration(app) -> tuple[Optional[str], str, bool]:
    """(the hash of the frozen registration the result on display applied, how it was applied, conflicting).

    Read from the result's own records; the basis of the registration is not recorded there."""
    result = getattr(app, "result", None)
    if result is None or getattr(app, "analysis_state", None) is not AnalysisState.SUCCESS:
        return None, "no analysis result is on display", False
    metadata = getattr(result, "metadata", None) or {}
    found = [(label, record.get("registration_hash")) for key, label in APPLIED_REGISTRATION_RECORDS
             if isinstance(record := metadata.get(key), dict)]
    hashes = {digest for _label, digest in found if isinstance(digest, str) and digest.strip()}
    if not found:
        return None, ("the result applied no frozen registration (automatic geometry alignment or registration "
                      "only)"), False
    labels = ", ".join(label for label, _digest in found)
    if len(hashes) != 1 or len(found) != 1:
        return None, f"the result records conflicting or incomplete registrations ({labels})", True
    return hashes.pop(), labels, False


def _file_row(source: "workspace.SourceSelection", context: "workspace.WorkspaceContext",
              caption: str) -> tuple[str, str, str]:
    if not source.selected:
        return NEEDED, caption, "Not chosen."
    text = source.path
    if context.specimen_known:
        text += (f"\nThe file name is one recorded for {context.specimen_id} in the catalogue (name only: the file "
                 "is not verified by this)." if source.catalogue_name_match
                 else f"\nThe file name is not one recorded for {context.specimen_id} in the catalogue.")
    return INFO, caption, text


def _registration_row(context: "workspace.WorkspaceContext", how: str, conflicting: bool) -> tuple[str, str, str]:
    registration = context.registration
    kind = workspace.RegistrationKind.UNKNOWN if conflicting else registration.kind
    digest = registration.registration_hash
    short = f"{digest[:12]}…" if digest else ""
    if kind is workspace.RegistrationKind.NONE:
        text = f"NONE: no registration is applied ({how})."
    elif conflicting:
        text = f"UNKNOWN: {how}."
    elif kind is workspace.RegistrationKind.UNKNOWN:
        text = (f"UNKNOWN: registration {short} was applied by {how}, but its basis is not recorded, so no binding "
                "to this working set is confirmed.")
    else:
        text = f"{kind.value} (as stated): registration {short or 'without a hash'}."
        if registration.stated_physical_hash_recorded_in_catalogue:
            text += (" The catalogue records this hash as the physical registration of the working specimen "
                     "(cross-reference only, not a verification of the data).")
    reference = registration.catalogue_reference
    if reference is not None:
        text += (f"\nCatalogue (reference only): {context.specimen_id} records this hash as {reference.kind.value} "
                 f"({reference.status_text}).")
    for issue in registration.issues:
        if issue.startswith("no registration basis is stated"):  # said above in plain words
            continue
        if context.requested_specimen_id is None and "catalogue" in issue:
            continue  # the user's data is not compared with the archive at all
        text += f"\n{issue[:1].upper()}{issue[1:]}."
    return REGISTRATION_STATES[kind], "Registration", text


def workspace_rows(context: "workspace.WorkspaceContext", modal_set_note: str = "", result_note: str = "",
                   registration_how: str = "", registration_conflict: bool = False,
                   specimen_name: str = "") -> list[tuple[str, str, str]]:
    """(state, caption, text) rows of the Current workspace panel; every value comes from ``context``.

    Home builds the context of the user's data without an archive specimen (``specimen_id`` None): the user's
    optional ``specimen_name`` is a label only, so nothing of the archive is attributed to the data."""
    if context.requested_specimen_id is None:
        specimen = (INFO, "Specimen", f"{specimen_name.strip()} (your label; not looked up in any archive)."
                    if specimen_name.strip() else "Unnamed (a name is optional).")
    elif context.catalogue_problem:
        specimen = (WARN, "Working specimen", f"UNKNOWN: the specimen catalogue cannot be used "
                                              f"({context.catalogue_problem}).")
    elif not context.specimen_known:
        specimen = (WARN, "Working specimen", f"UNKNOWN: {context.requested_specimen_id} is not in the catalogue.")
    else:
        specimen = (INFO, "Working specimen", f"{context.specimen_id}: type {context.specimen_type}, family "
                                              f"{context.family_id} (accepted catalogue).")
    modal = context.modal_set
    if modal_set_note:
        modal_row = (WARN, "Modal set", f"{workspace.ModalSetStatus.NOT_CHECKED.value}: {modal_set_note}.")
    elif modal.status is workspace.ModalSetStatus.NOT_SELECTED:
        modal_row = (INFO, "Modal set", "NOT_SELECTED: no modal set is selected.")
    elif context.requested_specimen_id is None:  # the user's data: no archive status is looked up or given
        modal_row = (INFO, "Modal set", f"{modal.name}: selected in the experimental file. It is not compared with "
                                        "the research archive, so no archive status is given to it.")
    elif modal.catalogue_set is not None:  # found by the set name in a file of the same name: names only
        modal_row = (INFO, "Modal set", f"{modal.name}: catalogue status {modal.status.value} ({modal.reason}). "
                                        f"Matched by the set name and the file name "
                                        f"({modal.catalogue_set.source_name}) only; the file content is not verified "
                                        "by this.")
    else:
        modal_row = (WARN, "Modal set", f"{modal.name}: {modal.status.value} ({modal.reason}).")
    result = context.result
    if result.state is AnalysisState.SUCCESS:
        pairs = "number of pairs unknown" if result.pair_count is None else f"{result.pair_count} admissible mode pairs"
        analysis = f"SUCCESS: {pairs}; MAC {'shown' if result.mac_shown else 'not shown'}."
    else:
        analysis = f"{result.state.value.upper()}: no mode pairs and no MAC on display."
    if result_note:
        analysis += f"\n{result_note}"
    auto_id = context.production_auto_id
    return [
        specimen,
        _file_row(context.fe_source, context, "FE file"),
        _file_row(context.experimental_source, context, "Experimental file"),
        modal_row,
        (OK if result.state is AnalysisState.SUCCESS else INFO, "Analysis", analysis),
        _registration_row(context, registration_how or "no analysis result is on display", registration_conflict),
        (NEEDED, "Production Auto-ID", f"{auto_id.status}: blocked. {auto_id.reason}"),
    ]


class HomeDashboard:
    """The Home screen; ``app`` is the main window (ModalComparatorApp)."""

    def __init__(self, app, parent) -> None:
        self.app = app
        self.frame = ttk.Frame(parent)
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(0, weight=1)
        background = ttk.Style(parent).lookup("TFrame", "background") or None
        self.canvas = tk.Canvas(self.frame, highlightthickness=0, borderwidth=0,
                                **({"background": background} if background else {}))
        self.scrollbar = ttk.Scrollbar(self.frame, orient="vertical", command=self.canvas.yview)
        self.content = ttk.Frame(self.canvas, padding=(2, 4))
        self._window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.bind("<Configure>", self._canvas_resized, add="+")
        self.content.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
                          add="+")
        app.root.bind_all("<MouseWheel>", self._wheel, add="+")
        self._wrapped: list[tuple[ttk.Label, ttk.Frame]] = []
        self._columns = None
        self._refresh_job = None
        self._rewrap_job = None
        self.cards = {}
        self._build_sources()
        self._build_readiness()
        self._build_results()
        self._build_material()
        self._build_catalogue()
        self._build_workspace()  # placed above the passport; built after it to share the loaded catalogue
        self._layout(2)
        self.frame.bind("<Destroy>", self._cancel_jobs, add="+")
        for name in WATCHED_VARIABLES:
            variable = getattr(app, name, None)
            if variable is not None and hasattr(variable, "trace_add"):
                variable.trace_add("write", lambda *_args: self.schedule_refresh())
        self.refresh()

    # ------------------------------------------------------------------------------------------------ building

    def _card(self, key: str, title: str, subtitle: str) -> ttk.Frame:
        card = ttk.Frame(self.content, style="MetricCard.TFrame", padding=(14, 12))
        card.columnconfigure(1, weight=1)
        ttk.Label(card, text=title, style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        self._wrap(ttk.Label(card, text=subtitle, style="Secondary.TLabel", justify="left"), card).grid(
            row=1, column=0, columnspan=3, sticky="ew", pady=(2, 8))
        card.bind("<Configure>", lambda _event: self._schedule_rewrap(), add="+")
        self.cards[key] = card
        return card

    def _wrap(self, label: ttk.Label, card: ttk.Frame) -> ttk.Label:
        self._wrapped.append((label, card))
        return label

    def _build_sources(self) -> None:
        app = self.app
        card = self._card("sources", "1  Source data", "The two result files to compare. Choosing an experimental "
                                                         "file reads its list of fitted modal sets; the analysis "
                                                         "runs only when you press Run analysis.")
        self.source_rows = {}
        for index, (kind, caption, command) in enumerate((("fe", "Abaqus results", app._choose_abaqus),
                                                          ("experimental", "Simcenter experiment",
                                                           app._choose_experiment))):
            top = 2 + 2 * index  # the file row, then its note
            ttk.Label(card, text=caption, style="MetricCaption.TLabel").grid(row=top, column=0, sticky="nw",
                                                                             pady=(6, 0), padx=(0, 10))
            name = ttk.Label(card, text="", style="Status.TLabel", justify="left")
            name.grid(row=top, column=1, sticky="ew", pady=(6, 0))
            button = ttk.Button(card, text="Choose...", command=command)
            button.grid(row=top, column=2, sticky="e", pady=(6, 0), padx=(8, 0))
            note = self._wrap(ttk.Label(card, text="", style="Secondary.TLabel", justify="left"), card)
            note.grid(row=top + 1, column=1, columnspan=2, sticky="ew")
            self.source_rows[kind] = (name, note, button)
        ttk.Label(card, text="Modal set", style="MetricCaption.TLabel").grid(row=6, column=0, sticky="w",
                                                                            pady=(10, 0), padx=(0, 10))
        self.modal_set_combo = ttk.Combobox(card, textvariable=app.experimental_modal_set_display, state="readonly")
        self.modal_set_combo.grid(row=6, column=1, columnspan=2, sticky="ew", pady=(10, 0))
        self.modal_set_combo.bind("<<ComboboxSelected>>", app._experimental_modal_set_selected, add="+")
        buttons = ttk.Frame(card)
        buttons.grid(row=7, column=0, columnspan=3, sticky="w", pady=(12, 0))
        ttk.Button(buttons, text="All settings (mode range, units, Abaqus)...",
                   command=lambda: app._show_expert(app.input_tab)).grid(row=0, column=0, sticky="w")

    def _build_readiness(self) -> None:
        app = self.app
        card = self._card("readiness", "2  Analysis readiness", "What is loaded, what is still missing, and whether "
                                                                "the analysis can be run.")
        self.checklist = ttk.Frame(card)
        self.checklist.grid(row=2, column=0, columnspan=3, sticky="ew")
        self.checklist.columnconfigure(2, weight=1)
        self.check_rows = []
        for row in range(6):
            mark = ttk.Label(self.checklist, text="", width=2)
            caption = ttk.Label(self.checklist, text="", style="MetricCaption.TLabel")
            text = self._wrap(ttk.Label(self.checklist, text="", justify="left"), card)
            mark.grid(row=row, column=0, sticky="nw", pady=2)
            caption.grid(row=row, column=1, sticky="nw", padx=(2, 10), pady=2)
            text.grid(row=row, column=2, sticky="ew", pady=2)
            self.check_rows.append((mark, caption, text))
        self.verdict = self._wrap(ttk.Label(card, text="", style="Section.TLabel", justify="left"), card)
        self.verdict.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(10, 6))
        buttons = ttk.Frame(card)
        buttons.grid(row=4, column=0, columnspan=3, sticky="w")
        self.run_button = ttk.Button(buttons, text="Run analysis", command=app._start)
        self.run_button.grid(row=0, column=0, sticky="w")
        self.stop_button = ttk.Button(buttons, text="Stop", command=app._request_stop)
        self.stop_button.grid(row=0, column=1, sticky="w", padx=(8, 0))

    def _build_results(self) -> None:
        app = self.app
        card = self._card("results", "3  Results", "The state of the last analysis, as shown in the expert tabs.")
        self.result_text = self._wrap(ttk.Label(card, text="", justify="left"), card)
        self.result_text.grid(row=2, column=0, columnspan=3, sticky="ew")
        self.result_values = ttk.Frame(card)
        self.result_values.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        buttons = ttk.Frame(card)
        buttons.grid(row=4, column=0, columnspan=3, sticky="w", pady=(10, 0))
        self.result_buttons = {}
        for column, (key, text, tab) in enumerate((("frequencies", "Frequencies and pairs", "table_tab"),
                                                   ("shapes", "Mode shapes", "shape_tab"),
                                                   ("mac", "MAC matrix", "plot_tab"))):
            button = ttk.Button(buttons, text=text, command=lambda tab=tab: app._show_expert(getattr(app, tab)))
            button.grid(row=column // 2, column=column % 2, sticky="w", padx=(0, 8), pady=(0, 4))
            self.result_buttons[key] = button

    def _build_material(self) -> None:
        card = self._card("material", "4  Material properties", "Identification of material properties from the "
                                                                "modal data (expert section 9).")
        self.material_rows = []
        for row in range(3):
            mark = ttk.Label(card, text="", width=2)
            caption = ttk.Label(card, text="", style="MetricCaption.TLabel")
            text = self._wrap(ttk.Label(card, text="", justify="left"), card)
            mark.grid(row=row + 2, column=0, sticky="nw", pady=2)
            caption.grid(row=row + 2, column=1, sticky="nw", padx=(0, 10), pady=2)
            text.grid(row=row + 2, column=2, sticky="ew", pady=2)
            self.material_rows.append((mark, caption, text))
        card.columnconfigure(1, weight=0)
        card.columnconfigure(2, weight=1)
        ttk.Button(card, text="Open the expert Auto-ID section", command=self.open_auto_id).grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(10, 0))

    def _build_catalogue(self) -> None:
        card = self._card("catalogue", "5  Specimen catalogue / Паспорт образца", CATALOGUE_SUBTITLE)
        card.columnconfigure(1, weight=1)
        self.catalogue = catalogue_view.load_catalogue()
        self.catalogue_choices = {catalogue_view.choice_text(entry): entry["specimen_id"]
                                  for entry in self.catalogue.specimens}
        ttk.Label(card, text="Specimen", style="MetricCaption.TLabel").grid(row=2, column=0, sticky="w",
                                                                           padx=(0, 10))
        self.specimen_choice = tk.StringVar(master=self.app.root, value="")  # Home's own: no window state
        self.specimen_combo = ttk.Combobox(card, textvariable=self.specimen_choice, state="readonly", width=44,
                                           values=tuple(self.catalogue_choices))
        self.specimen_combo.grid(row=2, column=1, sticky="w")
        self.specimen_combo.bind("<<ComboboxSelected>>", lambda _event: self.show_passport(), add="+")
        self.specimen_combo.bind("<MouseWheel>", self._combo_wheel)  # the wheel scrolls Home, never the choice
        self.catalogue_message = self._wrap(ttk.Label(card, text="", justify="left"), card)
        self.catalogue_message.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self._build_local_sources(card)
        self.passport = ttk.Frame(card)
        self.passport.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self.passport.columnconfigure(1, weight=1)
        if self.catalogue.problem:
            self.specimen_combo.configure(state="disabled")
            self.catalogue_message.configure(
                text=f"{MARKS[WARN]}  The specimen catalogue cannot be shown: {self.catalogue.problem} "
                     f"({short_path(self.catalogue.path)}). The rest of the program is not affected.",
                foreground=COLOURS[WARN])
        else:
            self._catalogue_message(CATALOGUE_PROMPT)

    def _build_workspace(self) -> None:
        """APP-WORKSPACE.2 / F1: the user's own data, independent of the laboratory archive; read only."""
        app = self.app
        card = self._card("workspace", "Current workspace", WORKSPACE_SUBTITLE)
        card.columnconfigure(0, weight=1)
        self.workspace_empty = ttk.Frame(card)  # shown while no file is chosen
        self.workspace_empty.grid(row=2, column=0, columnspan=3, sticky="ew")
        self.workspace_empty.columnconfigure(0, weight=1)
        self.workspace_empty_text = self._wrap(ttk.Label(self.workspace_empty, text=f"{MARKS[INFO]}  "
                                                         f"{EMPTY_WORKSPACE_TEXT}", foreground=COLOURS[INFO],
                                                         justify="left"), card)
        self.workspace_empty_text.grid(row=0, column=0, sticky="ew")
        choose = ttk.Frame(self.workspace_empty)
        choose.grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.workspace_choose_fe = ttk.Button(choose, text="Choose FE file...", command=app._choose_abaqus)
        self.workspace_choose_experiment = ttk.Button(choose, text="Choose experimental file...",
                                                      command=app._choose_experiment)
        self.workspace_choose_fe.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.workspace_choose_experiment.grid(row=0, column=1, sticky="w")
        self.workspace_details = ttk.Frame(card)  # shown once a file is chosen, whatever the archive records
        self.workspace_details.grid(row=3, column=0, columnspan=3, sticky="ew")
        self.workspace_details.columnconfigure(2, weight=1)
        ttk.Label(self.workspace_details, text="Specimen name", style="MetricCaption.TLabel").grid(
            row=0, column=1, sticky="w", padx=(0, 10), pady=2)
        self.specimen_name = tk.StringVar(master=app.root, value="")  # Home's own label: no window state
        name = ttk.Frame(self.workspace_details)
        name.grid(row=0, column=2, sticky="ew", pady=2)
        self.specimen_name_entry = ttk.Entry(name, textvariable=self.specimen_name, width=32)
        self.specimen_name_entry.grid(row=0, column=0, sticky="w")
        ttk.Label(name, text=SPECIMEN_NAME_HINT, style="Secondary.TLabel").grid(row=0, column=1, sticky="w",
                                                                               padx=(8, 0))
        self.workspace_rows = []
        for row in range(6):  # FE file, experimental file, modal set, analysis, registration, production Auto-ID
            mark = ttk.Label(self.workspace_details, text="", width=2)
            caption = ttk.Label(self.workspace_details, text="", style="MetricCaption.TLabel")
            text = self._wrap(ttk.Label(self.workspace_details, text="", justify="left"), card)
            mark.grid(row=row + 1, column=0, sticky="nw", pady=2)
            caption.grid(row=row + 1, column=1, sticky="nw", padx=(0, 10), pady=2)
            text.grid(row=row + 1, column=2, sticky="ew", pady=2)
            self.workspace_rows.append((mark, caption, text))
        self.research_archive_open = False
        self.archive_button = ttk.Button(card, text=OPEN_ARCHIVE_TEXT, command=self.toggle_research_archive)
        self.archive_button.grid(row=4, column=0, columnspan=3, sticky="w", pady=(10, 0))
        self.workspace_context = None
        self.specimen_name.trace_add("write", lambda *_args: self._refresh_workspace())

    def toggle_research_archive(self, show: Optional[bool] = None) -> None:
        """Show or hide the research archive (the laboratory specimen catalogue); it is never shown by default."""
        self.research_archive_open = (not self.research_archive_open) if show is None else bool(show)
        self.archive_button.configure(text=CLOSE_ARCHIVE_TEXT if self.research_archive_open else OPEN_ARCHIVE_TEXT)
        columns, self._columns = self._columns, None
        self._layout(columns or 2)
        self._schedule_rewrap()

    def open_research_archive(self) -> None:
        self.toggle_research_archive(True)

    def _refresh_workspace(self) -> None:
        app = self.app
        loaded = bool(_get(app.abaqus_path) or _get(app.experimental_path))
        if loaded:
            self.workspace_empty.grid_remove()
            self.workspace_details.grid()
        else:
            self.workspace_details.grid_remove()
            self.workspace_empty.grid()
        modal_set, modal_set_note = selected_modal_set_name(app)
        result, result_note = workspace_result(app)
        digest, how, conflicting = applied_registration(app)
        self.workspace_context = workspace.build_workspace_context(  # the user's data: no archive specimen
            None, fe_path=_get(app.abaqus_path) or None, experimental_path=_get(app.experimental_path) or None,
            modal_set=modal_set, registration_hash=digest, result=result, catalogue_view=self.catalogue)
        rows = workspace_rows(self.workspace_context, modal_set_note, result_note, how, conflicting,
                              specimen_name=self.specimen_name.get())[1:]  # the name has its own entry
        for (mark, caption, text), (state, title, value) in zip(self.workspace_rows, rows):
            mark.configure(text=MARKS[state], foreground=COLOURS[state])
            caption.configure(text=title)
            text.configure(text=value)
        self._schedule_rewrap()

    def _catalogue_message(self, text: str) -> None:
        self.catalogue_message.configure(
            text=f"{MARKS[INFO]}  {len(self.catalogue.specimens)} specimens in the catalogue "
                 f"({self.catalogue.header.get('status') or 'status unknown'}). {text}", foreground=COLOURS[INFO])

    def show_passport(self, specimen_id: Optional[str] = None) -> None:
        """Show one passport (from the list, or ``specimen_id``); reads the loaded catalogue only."""
        if specimen_id is None:
            specimen_id = self.catalogue_choices.get(self.specimen_choice.get())
        entry = self.catalogue.entry(specimen_id) if specimen_id else None
        card = self.cards["catalogue"]
        for child in self.passport.winfo_children():
            child.destroy()
        self._wrapped = [(label, owner) for label, owner in self._wrapped if label.winfo_exists()]
        self._set_local_sources(entry)
        if entry is None:
            return
        choice = catalogue_view.choice_text(entry)
        if self.specimen_choice.get() != choice:
            self.specimen_choice.set(choice)
        self._catalogue_message(f"Passport of {entry['specimen_id']}, as recorded in {self.catalogue.path.name} "
                                "(read only).")
        row = 0
        for section in catalogue_view.passport_sections(entry, self.catalogue):
            ttk.Label(self.passport, text=section.title, style="Section.TLabel").grid(
                row=row, column=0, columnspan=2, sticky="w", pady=(10, 2))
            row += 1
            if section.note:
                self._wrap(ttk.Label(self.passport, text=section.note, style="Secondary.TLabel", justify="left"),
                           card).grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 2))
                row += 1
            for caption, value in section.rows:
                ttk.Label(self.passport, text=caption, style="MetricCaption.TLabel").grid(
                    row=row, column=0, sticky="nw", padx=(0, 10), pady=1)
                self._wrap(ttk.Label(self.passport, text=value, justify="left"), card).grid(
                    row=row, column=1, sticky="ew", pady=1)
                row += 1
        self._schedule_rewrap()

    def _combo_wheel(self, event) -> str:
        self._wheel(event)
        return "break"

    # ------------------------------------------------------------------------------------------------ local sources

    def _build_local_sources(self, card) -> None:
        """APP-CATALOG.2: one recorded source, a located local copy, its check, and the explicit Use buttons."""
        self.local_frame = ttk.Frame(card)
        self.local_frame.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        self.local_frame.columnconfigure(1, weight=1)
        ttk.Label(self.local_frame, text="Local source selection", style="Section.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w")
        self.local_prompt = self._wrap(ttk.Label(self.local_frame, text="", style="Secondary.TLabel",
                                                 justify="left"), card)
        self.local_prompt.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        ttk.Label(self.local_frame, text="Source", style="MetricCaption.TLabel").grid(row=2, column=0, sticky="w",
                                                                                      padx=(0, 10))
        self.source_choice = tk.StringVar(master=self.app.root, value="")  # Home's own: no window state
        self.source_combo = ttk.Combobox(self.local_frame, textvariable=self.source_choice, state="disabled",
                                         width=90)
        self.source_combo.grid(row=2, column=1, sticky="w")
        self.source_combo.bind("<<ComboboxSelected>>", lambda _event: self.select_source(), add="+")
        self.source_combo.bind("<MouseWheel>", self._combo_wheel)
        self.source_info = ttk.Frame(self.local_frame)
        self.source_info.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.source_info.columnconfigure(1, weight=1)
        buttons = ttk.Frame(self.local_frame)
        buttons.grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))  # a fixed place, above the details
        self.locate_button = ttk.Button(buttons, text="Locate local file...", command=self.locate_local_file)
        self.use_fe_button = ttk.Button(buttons, text="Use as FE input",
                                        command=lambda: self.use_local_file(catalogue_view.FE_SIDE))
        self.use_experiment_button = ttk.Button(buttons, text="Use as experimental input",
                                                command=lambda: self.use_local_file(catalogue_view.EXPERIMENTAL_SIDE))
        for column, button in enumerate((self.locate_button, self.use_fe_button, self.use_experiment_button)):
            button.grid(row=0, column=column, sticky="w", padx=(0, 8))
        self.local_status = self._wrap(ttk.Label(self.local_frame, text="", justify="left"), card)
        self.local_status.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.local_sources: tuple = ()
        self.local_source = None
        self.local_check = None
        self._set_local_sources(None)

    def _set_local_sources(self, entry: Optional[dict]) -> None:
        self.local_sources = catalogue_view.local_sources(entry) if entry is not None else ()
        self.local_choices = {catalogue_view.source_choice_text(source): source for source in self.local_sources}
        self.source_choice.set("")
        self.source_combo.configure(values=tuple(self.local_choices),
                                    state="readonly" if self.local_sources else "disabled")
        if entry is None:
            prompt = "Choose a specimen first."
        elif not self.local_sources:
            prompt = f"No FE or experimental source is recorded for {entry['specimen_id']} in the catalogue."
        else:
            prompt = LOCAL_SOURCE_PROMPT
        self.local_prompt.configure(text=prompt)
        self._show_source(None)

    def select_source(self, source=None) -> None:
        """Show one source (from the list, or ``source``); a new source drops the previous file check."""
        if source is None:
            source = self.local_choices.get(self.source_choice.get())
        elif self.source_choice.get() != catalogue_view.source_choice_text(source):
            self.source_choice.set(catalogue_view.source_choice_text(source))
        self._show_source(source)

    def _show_source(self, source) -> None:
        self.local_source, self.local_check = source, None
        card = self.cards["catalogue"]
        for child in self.source_info.winfo_children():
            child.destroy()
        self._wrapped = [(label, owner) for label, owner in self._wrapped if label.winfo_exists()]
        if source is not None:
            for row, (caption, value) in enumerate(catalogue_view.source_lines(source, self.catalogue)):
                ttk.Label(self.source_info, text=caption, style="MetricCaption.TLabel").grid(
                    row=row, column=0, sticky="nw", padx=(0, 10), pady=1)
                self._wrap(ttk.Label(self.source_info, text=value, justify="left"), card).grid(
                    row=row, column=1, sticky="ew", pady=1)
        self._show_check("" if source is None or source.loadable else "This file cannot be used as an input.")
        self._schedule_rewrap()

    def _show_check(self, text: str = "", state: Optional[str] = None) -> None:
        check = self.local_check
        if check is not None and not text:
            state = CHECK_STATES.get(check.status, NEEDED)
            text = f"{check.status}: {check.message}"
        state = state or INFO
        self.local_status.configure(text=f"{MARKS[state]}  {text}" if text else "", foreground=COLOURS[state])
        self._refresh_local_buttons()

    def _analysis_locked(self) -> bool:
        return getattr(self.app, "analysis_state", None) in (AnalysisState.RUNNING, AnalysisState.STOPPING)

    def _refresh_local_buttons(self) -> None:
        source, check, locked = self.local_source, self.local_check, self._analysis_locked()
        usable = check is not None and check.usable and not locked
        self.locate_button.configure(state="normal" if source is not None and source.loadable and not locked
                                     else "disabled")
        self.use_fe_button.configure(state="normal" if usable and source.side == catalogue_view.FE_SIDE
                                     else "disabled")
        self.use_experiment_button.configure(
            state="normal" if usable and source.side == catalogue_view.EXPERIMENTAL_SIDE else "disabled")

    def locate_local_file(self) -> None:
        """The user names the file in the standard dialog; only that file is checked (read-only)."""
        source = self.local_source
        if source is None or not source.loadable or self._analysis_locked():
            return
        patterns = " ".join(f"*{suffix}" for suffix in local_files.allowed_suffixes(source))
        path = filedialog.askopenfilename(parent=self.app.root, title=f"Locate your local copy of {source.file_name}",
                                          filetypes=[(f"{source.file_name} ({patterns})", patterns),
                                                     ("All files", "*.*")])
        if not path:
            return  # cancelled: the previous check (if any) stays
        self.local_check = self._busy(lambda: local_files.check_local_file(source, path))
        self._show_check()

    def _busy(self, work):
        """``work()`` with the wait cursor (hashing a file runs on the window's thread)."""
        root = self.app.root
        try:
            root.configure(cursor="watch")
            root.update_idletasks()
        except tk.TclError:
            pass
        try:
            return work()
        finally:
            try:
                root.configure(cursor="")
            except tk.TclError:
                pass

    def use_local_file(self, side: str) -> None:
        """Set one field of 1. Files to the checked file, as its Browse button does; nothing else."""
        source, check = self.local_source, self.local_check
        if source is None or check is None or not check.usable or side != source.side:
            return
        field = "Abaqus results" if side == catalogue_view.FE_SIDE else "Experimental results"
        if self._analysis_locked():
            self._show_check("An analysis is running: the inputs cannot change now.", WARN)
            return
        if check.status == local_files.BYTE_VERIFIED:  # F1: the full SHA-256 again, size and time are not trusted
            fresh = self._busy(lambda: local_files.recheck_before_use(source, check))
            if fresh.status != local_files.BYTE_VERIFIED:
                self.local_check = fresh  # the earlier BYTE_VERIFIED no longer stands: Use is disabled
                self._show_check(f"Not used: {fresh.status}: {fresh.message}", NEEDED)
                return
            check = self.local_check = fresh
        elif not local_files.unchanged_since(check):  # no reference: only its size and time can be compared
            self.local_check = None
            self._show_check(f"{check.path.name} changed or disappeared since it was checked: locate it again. The "
                             "fields of the program are unchanged.", NEEDED)
            return
        if check.needs_confirmation and not messagebox.askyesno(
                "Use a file that cannot be byte-verified",
                NO_REFERENCE_WARNING.format(name=source.file_name, file=check.path.name, field=field),
                icon="warning", default="no", parent=self.app.root):
            self._show_check(f"Not used: {check.path.name} was not confirmed. The fields of the program are "
                             "unchanged.", INFO)
            return
        variable = self.app.abaqus_path if side == catalogue_view.FE_SIDE else self.app.experimental_path
        variable.set(str(check.path))  # what the Browse button of that field does; the existing traces react to it
        kind = "byte-verified" if check.status == local_files.BYTE_VERIFIED else "NOT byte-verified (confirmed by you)"
        self._show_check(f"{check.path.name} ({kind}) is now the {field} file on 1. Files. Nothing was loaded or run; "
                         "no modal set, registration or FE-experiment pairing was chosen. "
                         f"{local_files.IDENTITY_NOTE}", CHECK_STATES[check.status])

    # ------------------------------------------------------------------------------------------------ layout

    def _canvas_resized(self, event) -> None:
        self.canvas.itemconfigure(self._window, width=max(1, event.width))
        try:
            width = responsive_layout_width(event.width, float(self.app.root.tk.call("tk", "scaling")),
                                            self.app.ui_scale_percent.get())
        except (tk.TclError, AttributeError):
            width = event.width
        self._layout(1 if select_layout_mode(width) is LayoutMode.COMPACT else 2)

    def _layout(self, columns: int) -> None:
        if columns == self._columns:
            return
        self._columns = columns
        order = ("sources", "readiness", "results", "material")
        for card in self.cards.values():
            card.grid_forget()
        for column in range(2):
            used = column < columns
            self.content.columnconfigure(column, weight=1 if used else 0, uniform="home" if used else "")
        for index, key in enumerate(order):
            row, column = divmod(index, columns)
            self.cards[key].grid(row=row, column=column, sticky="nsew", padx=(0 if column == 0 else 6, 0),
                                 pady=(0, 8))
        below = len(order) // columns
        self.cards["workspace"].grid(row=below, column=0, columnspan=columns, sticky="nsew",
                                     pady=(0, 8))  # the current workspace: the full width, below the four areas
        if getattr(self, "research_archive_open", False):  # F1: only after Open research archive...
            self.cards["catalogue"].grid(row=below + 1, column=0, columnspan=columns, sticky="nsew",
                                         pady=(0, 8))  # the specimen passport: the full width, below the workspace

    def _rewrap(self, card, width: int) -> bool:
        """Each wrapped label wraps at the card's right edge, from where its column starts. False when a label is not
        placed yet (the cards are being laid out again): its place is unknown, so it is wrapped on the next pass."""
        placed = True
        for label, owner in self._wrapped:
            if owner is card:
                try:
                    if not label.winfo_ismapped():
                        placed = placed and not self._shown(label, card)  # a hidden part is not waited for
                        continue
                    offset = max(0, label.winfo_rootx() - card.winfo_rootx())
                    wrap = max(160, width - offset - 30)
                    if str(label.cget("wraplength")) != str(wrap):
                        label.configure(wraplength=wrap)
                except tk.TclError:
                    pass
        return placed

    @staticmethod
    def _shown(label, card) -> bool:
        """True when ``label`` and every container up to ``card`` are placed (so it is only waiting for layout)."""
        widget = label
        while widget is not None and widget is not card:
            if not widget.winfo_manager():
                return False
            widget = widget.master
        return True

    def _schedule_rewrap(self) -> None:
        """After the layout has settled (a resize, a new text, Home shown again), never during it."""
        if self._rewrap_job is None:
            try:
                self._rewrap_job = self.app.root.after(40, self._rewrap_all)
            except tk.TclError:
                self._rewrap_job = None

    def _rewrap_all(self) -> None:
        self._rewrap_job = None
        try:
            if not self.frame.winfo_ismapped():
                return  # Home is hidden: wrapped when it is shown again (refresh)
            placed = [self._rewrap(card, card.winfo_width()) for card in self.cards.values()
                      if card.winfo_manager()]  # a closed research archive is not laid out
        except tk.TclError:
            return
        if not all(placed):
            self._schedule_rewrap()

    def _cancel_jobs(self, event=None) -> None:
        if event is not None and event.widget is not self.frame:
            return
        for name in ("_refresh_job", "_rewrap_job"):
            job = getattr(self, name)
            setattr(self, name, None)
            if job is not None:
                try:
                    self.app.root.after_cancel(job)
                except tk.TclError:
                    pass

    def _wheel(self, event) -> None:
        try:
            if not self.frame.winfo_ismapped():
                return
            widget = self.app.root.winfo_containing(event.x_root, event.y_root)
            while widget is not None and widget is not self.canvas:
                widget = getattr(widget, "master", None)
            if widget is not None:
                self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        except (tk.TclError, KeyError):
            pass

    # ------------------------------------------------------------------------------------------------ state

    def schedule_refresh(self) -> None:
        if self._refresh_job is None:
            try:
                self._refresh_job = self.app.root.after_idle(self.refresh)
            except tk.TclError:
                self._refresh_job = None

    def refresh(self) -> None:
        self._refresh_job = None
        app = self.app
        try:
            for kind, variable in (("fe", app.abaqus_path), ("experimental", app.experimental_path)):
                state, name, note = describe_file(_get(variable), kind)
                label, note_label, _button = self.source_rows[kind]
                label.configure(text=f"{MARKS[state]}  {name}", foreground=COLOURS[state])
                note_label.configure(text=note)
            self.modal_set_combo.configure(values=tuple(app.experimental_modal_set_combo.cget("values")))
            for (mark, caption, text), (state, title, value) in zip(self.check_rows, readiness_rows(app)):
                mark.configure(text=MARKS[state], foreground=COLOURS[state])
                caption.configure(text=title)
                text.configure(text=value)
            state, verdict = readiness_verdict(app)
            self.verdict.configure(text=f"{MARKS[state]}  {verdict}", foreground=COLOURS[state])
            # Run on Home only when Home says ready; the existing Run checks every input again when pressed
            ready = state == OK and str(app.run_button.cget("state")) == "normal"
            self.run_button.configure(state="normal" if ready else "disabled")
            self.stop_button.configure(state=str(app.stop_button.cget("state")))
            locked = getattr(app, "analysis_state", None) in (AnalysisState.RUNNING, AnalysisState.STOPPING)
            for widget, idle in ((self.source_rows["fe"][2], "normal"), (self.source_rows["experimental"][2], "normal"),
                                 (self.modal_set_combo, "readonly")):  # as the same controls on 1. Files
                widget.configure(state="disabled" if locked else idle)
            self._refresh_results()
            self._refresh_workspace()
            self._refresh_local_buttons()  # locked while an analysis runs, like the other input controls
            for (mark, caption, text), (state, title, value) in zip(self.material_rows, material_summary(app)):
                mark.configure(text=MARKS[state], foreground=COLOURS[state])
                caption.configure(text=title)
                text.configure(text=value)
            self._schedule_rewrap()  # the columns may have moved with the new texts
        except tk.TclError:
            pass  # the window is closing

    def _refresh_results(self) -> None:
        app = self.app
        state, text, values = result_summary(app)
        self.result_text.configure(text=f"{MARKS[state]}  {text}", foreground=COLOURS[state])
        for child in self.result_values.winfo_children():
            child.destroy()
        if values:
            self.result_values.grid()
        else:
            self.result_values.grid_remove()  # an emptied frame would keep its former height
        for row, (caption, value) in enumerate(values):
            ttk.Label(self.result_values, text=caption, style="MetricCaption.TLabel").grid(
                row=row, column=0, sticky="nw", padx=(0, 12), pady=1)
            ttk.Label(self.result_values, text=value.replace("\n", "   |   ")).grid(row=row, column=1, sticky="w",
                                                                                 pady=1)
        links = result_links(app)
        for key, button in self.result_buttons.items():
            button.configure(state="normal" if key in links else "disabled")

    def open_auto_id(self) -> None:
        app = self.app
        app._show_expert(app.material_identification_tab)
        notebook = getattr(app, "material_identification_notebook", None)
        if notebook is not None and notebook.tabs():
            notebook.select(notebook.tabs()[0])
