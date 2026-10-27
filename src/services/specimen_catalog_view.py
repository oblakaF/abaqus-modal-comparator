"""APP-CATALOG.1: read-only view of the accepted specimen catalogue (``docs/auto_id/specimen_catalog.json``).

The Home screen shows the passport of one physical specimen from this file. The service only reads the file and
words its values; it computes nothing:

- no missing mass, thickness or dimension is derived;
- an unknown or null value is shown as ``UNKNOWN_TEXT``, never as zero;
- every value keeps the qualifier the catalogue gives it:
  - recorded in the spec or calculated in the spec;
  - nominal or measured;
  - FE template constant (never a material property);
  - raw FRF or governed fitted modes;
  - existing FE file or governed forward model;
  - historical or physical registration.

The catalogue is an optional, read-only input: a missing or damaged file gives a ``CatalogueView`` with a
``problem`` text and no specimen, and nothing else in the program depends on it. Viewing a passport selects no
file, modal set or registration and changes no analysis state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOGUE_PATH = REPO_ROOT / "docs" / "auto_id" / "specimen_catalog.json"
CATALOGUE_SCHEMA = "auto-id/specimen-catalog/v1"
CATALOGUE_READ_LIMIT = 5_000_000  # bytes; the accepted catalogue is about 130 kB
UNKNOWN_TEXT = "Неизвестно (unknown)"
NOT_RECORDED = f"{UNKNOWN_TEXT}: not recorded in the catalogue"
SCOPE_TEXT = (
    "The catalogue is ACCEPTED as the inventory of the specimen records. That does not mean that every specimen is "
    "scientifically validated: the status of each specimen is given below."
)
TEMPLATE_TEXT = (
    "FE input values (ASSUMED/TEMPLATE): FE constants with this status are not measured or identified elastic "
    "constants"
)


@dataclass(frozen=True)
class PassportSection:
    title: str
    rows: tuple[tuple[str, str], ...]  # (caption, text); a caption "" continues the previous row
    note: str = ""


@dataclass(frozen=True)
class CatalogueView:
    path: Path
    specimens: tuple[dict, ...] = ()
    problem: str = ""
    header: dict = field(default_factory=dict)

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(entry["specimen_id"] for entry in self.specimens)

    def entry(self, specimen_id: str) -> Optional[dict]:
        return next((entry for entry in self.specimens if entry["specimen_id"] == specimen_id), None)

    def store_root(self, store: str) -> str:
        for source in self.header.get("sources") or ():
            if isinstance(source, dict) and source.get("store") == store and source.get("root"):
                return str(source["root"])
        return ""


def load_catalogue(path: Optional[Path] = None) -> CatalogueView:
    """The catalogue, or a view with a ``problem`` and no specimen; never raises for a bad file."""
    path = Path(path) if path is not None else CATALOGUE_PATH
    try:
        size = path.stat().st_size
    except OSError:
        return CatalogueView(path, problem="the specimen catalogue file was not found")
    if size > CATALOGUE_READ_LIMIT:
        return CatalogueView(path, problem="the specimen catalogue file is too large to be a catalogue")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return CatalogueView(path, problem="the specimen catalogue file is not readable JSON")
    if not isinstance(data, dict) or data.get("schema") != CATALOGUE_SCHEMA:
        return CatalogueView(path, problem=f"the file is not a specimen catalogue ({CATALOGUE_SCHEMA})")
    entries = data.get("specimens")
    if not isinstance(entries, list) or not entries:
        return CatalogueView(path, problem="the specimen catalogue lists no specimen")
    ids = [entry.get("specimen_id") if isinstance(entry, dict) else None for entry in entries]
    if any(not isinstance(value, str) or not value.strip() for value in ids):
        return CatalogueView(path, problem="a specimen record of the catalogue has no specimen ID")
    if len(set(ids)) != len(ids):
        return CatalogueView(path, problem="the specimen catalogue lists a specimen ID twice")
    header = {key: value for key, value in data.items() if key != "specimens"}
    return CatalogueView(path, tuple(entries), "", header)


# ------------------------------------------------------------------------------------------------ wording


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _unknown(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip().upper() in ("", "UNKNOWN"))


def number(value: Any) -> str:
    """A catalogue number as written (515, 2.9, 0.425, 582.71); never rounded to look like another value."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    return repr(value)


def text(value: Any) -> str:
    if _unknown(value):
        return UNKNOWN_TEXT
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return number(value)
    if isinstance(value, list):
        return "; ".join(text(item) for item in value) if value else UNKNOWN_TEXT
    return str(value)


def _length(value: Any, qualifier: str) -> str:
    if _unknown(value) or not isinstance(value, (int, float)):
        return UNKNOWN_TEXT if _unknown(value) else str(value)
    return f"{number(value)} mm ({qualifier})"


def _plan(value: Any, qualifier: str) -> str:
    if not isinstance(value, list) or len(value) != 2 or not all(isinstance(v, (int, float)) for v in value):
        return UNKNOWN_TEXT
    return f"{number(value[0])} × {number(value[1])} mm ({qualifier})"


def _hash(value: Any) -> str:
    return f"SHA-256 {value[:12]}…" if isinstance(value, str) and len(value) > 12 else ""


def _size(value: Any) -> str:
    if not isinstance(value, int):
        return ""
    return f"{value / 1e6:.1f} MB" if value >= 1_000_000 else f"{value / 1e3:.1f} kB"


def file_reference(reference: Any, catalogue: Optional[CatalogueView] = None) -> str:
    """A file named by the catalogue (store, relative path, size, hash); the file itself is never opened."""
    reference = _dict(reference)
    if not reference.get("relative_path"):
        return UNKNOWN_TEXT
    store = str(reference.get("store") or "?")
    root = catalogue.store_root(store) if catalogue is not None else ""
    where = f"{store} ({root})" if root else store
    member = f", member {reference['zip_member']}" if reference.get("zip_member") else ""
    extras = ", ".join(item for item in (_size(reference.get("size_bytes")), _hash(reference.get("sha256"))) if item)
    return f"{reference['relative_path']}{member} in store {where}" + (f"; {extras}" if extras else "")


# ------------------------------------------------------------------------------------------------ sections

TYPE_TEXT = {"sandwich": "sandwich panel (two face sheets, core, adhesive)", "bare_plate": "bare plate (no core)"}


def _identity_section(entry: dict, catalogue: Optional[CatalogueView]) -> PassportSection:
    identity, label = _dict(entry.get("identity")), _dict(entry.get("physical_label"))
    confidence = text(identity.get("confidence"))
    verdict = f" ({identity['verdict']})" if identity.get("verdict") else ""
    rows = [
        ("Specimen ID", str(entry.get("specimen_id"))),
        ("Type", TYPE_TEXT.get(entry.get("type"), text(entry.get("type")))),
        ("Family", text(entry.get("family_id"))),
        ("Identity", f"{confidence}{verdict}"),
    ]
    resolution = _dict(_dict(catalogue.header.get("identity_resolutions") if catalogue else None).get(
        entry.get("specimen_id")))
    evidence = identity.get("evidence")
    for item in (evidence if isinstance(evidence, list) else [evidence] if evidence else []):
        if not (resolution and str(item).startswith("see identity_resolutions")):  # the record itself follows
            rows.append(("", f"• {item}"))
    if resolution.get("question_answered"):
        rows.append(("Identity record", f"{resolution['question_answered']} {text(resolution.get('verdict'))} "
                                        f"({text(resolution.get('confidence'))}; SPECIMEN_CATALOG.md)"))
    number_on_label = label.get("specimen_number_on_label")
    on_label = {True: "the specimen number is on the label", False: "no specimen number on the label"}.get(
        number_on_label, "specimen number on the label: " + UNKNOWN_TEXT)
    rows.append(("Label", f"{text(label.get('text'))}; {on_label}"))
    statuses = _list(entry.get("auto_id_status"))
    rows.append(("Identification status", ", ".join(str(item) for item in statuses) if statuses else UNKNOWN_TEXT))
    rows.append(("", "No material property of this specimen is identified (production Auto-ID is not authorised)."))
    if entry.get("m7_role"):
        rows.append(("Role", str(entry["m7_role"])))
    if entry.get("manufacturing_date"):
        rows.append(("Manufactured", str(entry["manufacturing_date"])))
    return PassportSection("Identity and status", tuple(rows))


def _geometry_section(entry: dict) -> PassportSection:
    geometry, bare = _dict(entry.get("geometry")), entry.get("type") == "bare_plate"
    rows = [("Panel plan", _plan(geometry.get("plan_mm"), "recorded"))]
    if bare:
        rows.append(("Plate thickness", _length(geometry.get("total_thickness_mm"), "recorded")))
        rows.append(("Face sheets", "not applicable: bare plate without core"))
    else:
        rows.append(("Total thickness", _length(geometry.get("total_thickness_mm"),
                                                "recorded total sandwich thickness, not a face-sheet thickness")))
        rows.append(("Top face sheet", _length(geometry.get("face_top_mm"), "recorded")))
        rows.append(("Bottom face sheet", _length(geometry.get("face_bottom_mm"), "recorded")))
        rows.append(("Core thickness", _length(geometry.get("core_thickness_mm"), "recorded")))
    if geometry.get("total_thickness_before_glue_mm") is not None:
        rows.append(("Before bonding", _length(geometry["total_thickness_before_glue_mm"],
                                               "recorded total thickness before bonding")))
    if geometry.get("face_asymmetry"):
        rows.append(("Face asymmetry", str(geometry["face_asymmetry"])))
    for key, source in (("core_plan_mm", "core_plan_source"), ("core_cad_plan_mm", "core_cad_source")):
        if geometry.get(key) is not None:
            rows.append(("Core plan", _plan(geometry[key], f"from {geometry.get(source) or 'a CAD record'}; "
                                                           "not a measurement of the specimen")))
    if geometry.get("flag"):
        rows.append(("Flag", str(geometry["flag"])))
    rows.append(("Local variation", text(geometry.get("local_face_thickness_variation"))))
    rows.append(("Source", text(geometry.get("source"))))
    if geometry.get("fe_orientation"):
        rows.append(("FE orientation", str(geometry["fe_orientation"])))
    default = "" if bare else "Total sandwich thickness is not face-sheet thickness."
    return PassportSection("Dimensions", tuple(rows), str(geometry.get("distinction") or default))


def _constants(constants: Any) -> str:
    constants = _dict(constants)
    status = str(constants.get("status") or "UNKNOWN")
    if status == "ASSUMED/TEMPLATE":
        source = f"; recorded in {constants['source']}" if constants.get("source") else ""
        return f"{TEMPLATE_TEXT}{source}"
    if status == "UNKNOWN":
        return f"{UNKNOWN_TEXT}: no constants are recorded"
    return f"{status} (as recorded in the catalogue)"


def _material_section(entry: dict) -> PassportSection:
    face, core = _dict(entry.get("face_material")), entry.get("core")
    rows = [
        ("Face material", text(face.get("designation"))),
        ("Face stock", text(face.get("stock"))),
        ("Weave", text(face.get("weave"))),
        ("Nominal face", _length(face.get("nominal_thickness_mm"), "nominal stock thickness, not a measurement")),
        ("Face FE constants", _constants(face.get("constants"))),
    ]
    if isinstance(core, dict):
        rows += [
            ("Core material", text(core.get("material"))),
            ("Core topology", text(core.get("topology"))),
            ("Core grade", text(core.get("grade"))),
            ("Core process", text(core.get("process"))),
            ("Adhesive", text(core.get("adhesive"))),
        ]
        if core.get("core_mass_per_panel_area_g_m2") is not None:
            note = core.get("core_mass_per_area_note") or "DERIVED in the catalogue"
            rows.append(("Core mass per area", f"{number(core['core_mass_per_panel_area_g_m2'])} g/m² ({note})"))
        rows.append(("Core FE constants", _constants(core.get("constants"))))
        if core.get("note"):
            rows.append(("Core note", str(core["note"])))
    elif entry.get("type") == "bare_plate":
        rows.append(("Core and adhesive", "none: bare plate"))
    else:
        rows.append(("Core and adhesive", UNKNOWN_TEXT))
    return PassportSection("Materials", tuple(rows))


MASS_ROWS = (  # key, caption, qualifier (every value is one written in the spec; the program computes none)
    ("face_top_g", "Top face sheet", "recorded"),
    ("face_bottom_g", "Bottom face sheet", "recorded"),
    ("core_g", "Core", "recorded"),
    ("without_adhesive_g", "Without adhesive", "recorded"),
    ("adhesive_top_g", "Adhesive, top", "recorded"),
    ("adhesive_bottom_g", "Adhesive, bottom", "recorded"),
    ("adhesive_calculated_g", "Adhesive, calculated", "recorded in the spec as a calculated value"),
    ("adhesive_real_g", "Adhesive, real", "recorded in the spec as the real value"),
    ("finished_g", "Finished panel", "recorded in the spec"),
    ("finished_real_g", "Finished, real", "recorded in the spec as the real value"),
    ("finished_calculated_g", "Finished, calculated", "recorded in the spec as a calculated value"),
    ("total_calculated_g", "Total, calculated", "recorded in the spec as a calculated value"),
)
ALWAYS_SHOWN = ("face_top_g", "face_bottom_g", "core_g", "adhesive_real_g")  # shown even when not recorded
FINISHED_KEYS = ("finished_g", "finished_real_g", "finished_calculated_g", "total_calculated_g")


def _mass(value: Any, qualifier: str) -> str:
    if _unknown(value):
        return NOT_RECORDED
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return str(value)
    return f"{number(value)} g ({qualifier})"


def _mass_section(entry: dict) -> PassportSection:
    mass = _dict(entry.get("mass"))
    rows = []
    if entry.get("type") == "bare_plate":
        rows.append(("Plate", _mass(mass.get("plate_g"), "recorded")))
    else:
        for key, caption, qualifier in MASS_ROWS:
            if key in FINISHED_KEYS:
                continue
            if key in mass or key in ALWAYS_SHOWN:
                rows.append((caption, _mass(mass.get(key), qualifier)))
        finished = [(caption, _mass(mass[key], qualifier)) for key, caption, qualifier in MASS_ROWS
                    if key in FINISHED_KEYS and key in mass]
        rows += finished or [("Finished panel", NOT_RECORDED)]
    for note in _list(mass.get("arithmetic_notes")):
        rows.append(("Catalogue note", str(note)))
    return PassportSection("Masses", tuple(rows), "Masses as recorded in the catalogue (spec file). A calculated "
                                                  "value is one the spec records as calculated; the program "
                                                  "calculates no mass, and a missing value stays unknown.")


GOVERNED, OTHER, NOT_GOVERNED, UNASSIGNED = "governed", "other", "not_governed", "unassigned"


def _strip_qualifier(name: str) -> str:
    """``governed_set`` without one trailing "( ... )" qualifier: "Bravo (1) (active fixture X)" -> "Bravo (1)"."""
    name = name.rstrip()
    if not name.endswith(")"):
        return name
    depth = 0
    for index in range(len(name) - 1, -1, -1):
        depth += {")": 1, "(": -1}.get(name[index], 0)
        if depth == 0:
            return name[:index].rstrip()
    return name


def governed_set_match(experiment: dict) -> tuple[Optional[str], str]:
    """(the listed set the catalogue names as governed, or None; why none).

    The ``governed_set`` text is matched by exact name, with or without its trailing qualifier. Similar names are
    never merged ("Bravo" is not "Bravo (1)"). When both readings name a listed set, the match is ambiguous and no
    set is marked."""
    if not experiment.get("governed"):
        return None, "not governed"
    recorded = experiment.get("governed_set")
    names = [str(_dict(item).get("set")) for item in _list(experiment.get("fitted_sets"))]
    if not isinstance(recorded, str) or not recorded.strip():
        return None, "the catalogue names no governed set"
    readings = {recorded.strip(), _strip_qualifier(recorded)}
    matches = sorted({name for name in names if name in readings})
    if len(matches) == 1 and names.count(matches[0]) == 1:
        return matches[0], ""
    if matches:
        return None, f"the governed set \"{recorded}\" matches more than one listed set ({', '.join(matches)})"
    return None, f"the governed set \"{recorded}\" matches no listed set"


def _frequency_only(experiment: dict) -> bool:
    return "FREQUENCY_ONLY" in " ".join([str(experiment.get("governed_set") or "")]
                                        + [str(item) for item in _list(experiment.get("usable_now"))])


def modal_set_status(experiment: dict, name: str) -> tuple[str, str]:
    """(status key, words) of one listed set of a PolyMAX export."""
    governed, reason = governed_set_match(experiment)
    if not experiment.get("governed"):
        return NOT_GOVERNED, "PolyMAX modal fit, not governed (the catalogue records no governed set for this file)"
    if governed is None:
        return UNASSIGNED, f"status not assigned: {reason}"
    if name != governed:
        return OTHER, f"PolyMAX modal fit, not the governed set of this file (that is {governed})"
    words = f"GOVERNED SET: {experiment['governed_set']}"
    if _frequency_only(experiment):
        words += "; FREQUENCY_ONLY: frequencies only, no confirmed mode-shape (MAC) comparison"
    return GOVERNED, words


def _experiment_rows(experiment: dict, catalogue: Optional[CatalogueView]) -> list[tuple[str, str]]:
    dataset = str(experiment.get("dataset") or UNKNOWN_TEXT)
    fitted = "dataset 55" in dataset or "PolyMAX" in dataset
    if not fitted:
        kind = "measured response functions, not fitted modes"
    elif not experiment.get("governed"):
        kind = "PolyMAX modal fit; not governed (no governed fixture in the catalogue)"
    else:
        governed, reason = governed_set_match(experiment)
        kind = (f"PolyMAX modal fit; governed set {governed}" if governed is not None
                else f"PolyMAX modal fit; governed, but {reason}: no set is marked as governed")
        if governed is not None and _frequency_only(experiment):
            kind += " (FREQUENCY_ONLY: no confirmed MAC comparison)"
    rows = [("Data", f"{dataset}: {kind}")]
    for item in _list(experiment.get("fitted_sets")):
        item = _dict(item)
        frequencies = _list(item.get("frequencies_hz"))
        span = f", {number(frequencies[0])} … {number(frequencies[-1])} Hz" if frequencies else ""
        _status, words = modal_set_status(experiment, str(item.get("set")))
        rows.append(("Modal set", f"{text(item.get('set'))}: {text(item.get('mode_count'))} modes{span}"
                                  f" (Testlab project {text(item.get('testlab_project'))}) — {words}"))
    if experiment.get("points") is not None:
        rows.append(("Points", number(experiment["points"])))
    band = experiment.get("frequency_range_hz")
    if isinstance(band, list) and len(band) == 2:
        resolution = experiment.get("frequency_resolution_hz")
        step = f", Δf {number(resolution)} Hz" if resolution is not None else ""
        rows.append(("Band", f"{number(band[0])} … {number(band[1])} Hz{step}"))
    if experiment.get("functions"):
        rows.append(("Functions", text(experiment["functions"])))
    if experiment.get("acquired"):
        rows.append(("Acquired", str(experiment["acquired"])))
    if experiment.get("remount_relation"):
        rows.append(("Mounting", str(experiment["remount_relation"])))
    if experiment.get("orientation"):
        rows.append(("Orientation", str(experiment["orientation"])))
    rows.append(("Usable now", text(experiment.get("usable_now"))))
    if experiment.get("usable_after_governance"):
        rows.append(("After governance", text(experiment["usable_after_governance"])))
    rows.append(("Source", file_reference(experiment.get("source"), catalogue)))
    if experiment.get("video_frame_source"):
        rows.append(("Camera frame", file_reference(experiment["video_frame_source"], catalogue)))
    if experiment.get("note"):
        rows.append(("Note", str(experiment["note"])))
    return rows


def experiment_sections(entry: dict, catalogue: Optional[CatalogueView] = None) -> list[PassportSection]:
    """One section per recorded data set; sessions are listed separately and never merged."""
    experiments = [item for item in _list(entry.get("experiments")) if isinstance(item, dict)]
    sections = []
    for index, experiment in enumerate(experiments, start=1):
        title = f"Experimental data {index}/{len(experiments)}: session {text(experiment.get('session'))}"
        sections.append(PassportSection(title, tuple(_experiment_rows(experiment, catalogue))))
    extra = [(caption, str(entry[key])) for key, caption in (("experiment_note", "Note"),
                                                              ("earlier_session_records", "Earlier records"))
             if entry.get(key)]
    if not experiments:
        sections.append(PassportSection("Experimental data", tuple(
            [("Measurements", "No experiment is recorded for this specimen in the catalogue.")] + extra)))
    elif extra:
        sections.append(PassportSection("Experimental data: notes", tuple(extra)))
    return sections


def _registration_rows(registration: dict) -> list[tuple[str, str]]:
    rows = []
    physical, legacy = registration.get("physical"), registration.get("legacy")
    if isinstance(physical, dict):
        rows.append(("Physical registration", f"{text(physical.get('status'))}; {text(physical.get('path'))}"))
        if physical.get("passport"):
            rows.append(("", f"physical passport {physical['passport']}"))
    else:
        status = registration.get("status")
        rows.append(("Physical registration", f"none ({status})" if status else "none"))
    if isinstance(legacy, dict):
        rows.append(("Legacy registration", f"{text(legacy.get('status'))}; {text(legacy.get('path'))}"))
    for key, caption in (("physical_basis", "Basis"), ("distortion", "UNV distortion"),
                         ("unresolved", "Open items"), ("note", "Note")):
        if registration.get(key):
            rows.append((caption, str(registration[key])))
    return rows


def _fe_section(entry: dict, catalogue: Optional[CatalogueView]) -> PassportSection:
    assets, registration = _dict(entry.get("fe_assets")), _dict(entry.get("registration"))
    rows = [("FE status", text(assets.get("status")))]
    model = assets.get("governed_forward_model")
    if isinstance(model, dict):
        rows.append(("Governed FE model", f"{text(model.get('forward_model_id'))}; {text(model.get('path'))}"
                     + (f"; INP {_hash(model.get('inp_sha256'))}" if model.get("inp_sha256") else "")))
    else:
        rows.append(("Governed FE model", "none recorded"))
    for key, where in (("store", "FE file"), ("elsewhere", "Outside the store")):
        for item in _list(assets.get(key)):
            rows.append((where, f"{text(_dict(item).get('role'))}: {file_reference(item, catalogue)}"))
    for key, caption in (("note", "Note"), ("other", "Other")):
        if assets.get(key):
            rows.append((caption, str(assets[key])))
    rows += _registration_rows(registration)
    pairs = _dict(entry.get("strict_pairs"))
    for key, value in pairs.items():
        rows.append((f"Strict pairs, {key}", str(value)))
    return PassportSection("FE data", tuple(rows), "An existing INP or ODB file is not a governed FE model; only "
                                                   "the governed model is reproducible input for identification.")


def _origin_section(entry: dict, catalogue: Optional[CatalogueView]) -> PassportSection:
    rows = []
    for key, caption in (("spec", "Spec file"), ("vault_note", "Specimen note")):
        if entry.get(key):
            rows.append((caption, f"{file_reference(entry[key], catalogue)} ({text(_dict(entry[key]).get('role'))})"))
        else:
            rows.append((caption, f"{UNKNOWN_TEXT}: none in the catalogue"))
    rows.append(("Store folder", str(entry["folder"]) if entry.get("folder") else "none in the curated store"))
    if catalogue is not None:
        header = catalogue.header
        rows.append(("Catalogue", f"{text(header.get('status'))}, {text(header.get('date'))}; "
                                  f"{text(header.get('acceptance'))}"))
        rows.append(("", f"Read only from {catalogue.path.name}; the files it names are not opened."))
    return PassportSection("Origin of the data", tuple(rows), SCOPE_TEXT)


def passport_sections(entry: dict, catalogue: Optional[CatalogueView] = None) -> list[PassportSection]:
    """The whole passport of one specimen record, in reading order."""
    return [_identity_section(entry, catalogue), _geometry_section(entry), _material_section(entry),
            _mass_section(entry),
            *experiment_sections(entry, catalogue), _fe_section(entry, catalogue), _origin_section(entry, catalogue)]


def choice_text(entry: dict) -> str:
    """The text of one specimen in the selection list."""
    kind = {"sandwich": "sandwich", "bare_plate": "bare plate"}.get(entry.get("type"), text(entry.get("type")))
    return f"{entry['specimen_id']}  ({kind}, {text(entry.get('family_id'))})"
