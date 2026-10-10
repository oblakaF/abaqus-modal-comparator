"""Auto-ID specimen / family setup wizard — Auto-ID M8.1 (SPEC v1.2 aware).

The preparation layer between the GUI and the governed backend.  It loads what already exists and reports,
factually, what is present and what is missing.

The wizard owns:
- locating the governed inputs: the specimen passport in a specimen folder, or a campaign (family)
  definition, and the records they point to (fixture manifest entry, forward-model manifest);
- factual checks: the governed parsers (passport, campaign, forward model), identity agreement between
  linked records, presence and size of pinned external files and the passport's own declared gaps.  A pinned
  file found with its pinned size is shown as PRESENT_SHA256_NOT_VERIFIED: its SHA-256 is verified only by the
  backend when the file is used, so presence is never shown as scientifically READY;
- the declared SPEC v1.2 scientific question and τ_mf of a campaign definition, exactly as declared (a v1
  definition declares neither: shown as not declared, never inferred), and its FIT / HOLDOUT row declarations;
- a human-readable row view for the GUI.

The backend owns, and the wizard never re-implements: passport and campaign validation rules, registration
basis and production readiness (``services.physical_registration``), the experimental input chain, freezing,
pairing, thresholds, optimisation and verdicts.

The wizard never decides scientific validity, chooses modes or a registration, uses MAC or frequencies,
changes a threshold, fills a missing value, substitutes a local file for a pinned one, or starts Abaqus or an
identification.  It never turns a material-identification campaign into a calibration, judges readiness (the
shared V12-I6 backend does) or writes anything.  Missing means missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path, PurePosixPath
from typing import Mapping, Optional

from domain.campaign_definition import (
    MATERIAL_IDENTIFICATION,
    SPECIMEN_ENGINEERING_CALIBRATION,
    CampaignDefinition,
    CampaignDefinitionError,
    load_campaign_definition,
)
from domain.experiment_fixture import (
    ExperimentFixture,
    ExperimentFixtureManifest,
    ExternalFileReference,
    FixtureManifestError,
    FixtureSourceMismatchError,
    FixtureSourceUnavailableError,
    load_experiment_fixture_manifest,
    resolve_external_file,
)
from domain.forward_model_manifest import ForwardModelManifestError
from domain.specimen_manifest import SpecimenManifest, SpecimenManifestError, load_specimen_manifest

from .forward_builder import load_bound_forward_model


FIXTURE_MANIFEST = PurePosixPath("docs/auto_id/fixtures/real_experiment_fixtures.json")
PASSPORT_NAME = "specimen.json"
PASSPORT_SUFFIX = ".specimen.json"
_PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".heic"}


class ItemStatus(str, Enum):
    PRESENT = "PRESENT"
    PRESENT_SHA256_NOT_VERIFIED = "PRESENT_SHA256_NOT_VERIFIED"  # pinned file found with its pinned size only
    NOT_DECLARED = "NOT_DECLARED"  # the record does not declare it (never inferred)
    MISSING = "MISSING"  # needed by the backend and not recorded
    UNAVAILABLE = "UNAVAILABLE"  # declared unavailable in the record, with its reason
    NOT_CONFIGURED = "NOT_CONFIGURED"  # the store holding a pinned file is not configured on this computer
    NOT_FOUND = "NOT_FOUND"  # the pinned file is not in its configured store
    MISMATCH = "MISMATCH"  # the file or a linked record disagrees with its pin
    INVALID = "INVALID"  # a governed parser refused the record
    INFO = "INFO"


GAPS = (ItemStatus.MISSING, ItemStatus.UNAVAILABLE, ItemStatus.NOT_CONFIGURED, ItemStatus.NOT_FOUND,
        ItemStatus.MISMATCH, ItemStatus.INVALID)


class WizardInputError(ValueError):
    """The selected folder or file cannot be opened as a specimen package or campaign definition."""


@dataclass(frozen=True)
class WizardItem:
    section: str
    label: str
    value: str
    status: ItemStatus
    detail: str = ""  # provenance / reason, for the advanced view


@dataclass(frozen=True)
class FolderFile:
    name: str
    kind: str  # specimen_passport | model_input | universal_file | odb | photo | other
    size_bytes: int


@dataclass(frozen=True)
class SpecimenPreparation:
    source: str
    passport_path: Optional[Path]
    passport: Optional[SpecimenManifest]
    fixture: Optional[ExperimentFixture]
    folder_files: tuple[FolderFile, ...]
    items: tuple[WizardItem, ...]

    @property
    def gaps(self) -> tuple[WizardItem, ...]:
        return tuple(item for item in self.items if item.status in GAPS)

    @property
    def loaded(self) -> bool:
        return self.passport is not None


@dataclass(frozen=True)
class FamilySpecimen:
    label: str
    fixture_id: str
    fit_rows: tuple[str, ...]
    holdout_rows: tuple[str, ...]
    preparation: SpecimenPreparation


@dataclass(frozen=True)
class FamilyPreparation:
    source: str
    campaign_path: Path
    definition: Optional[CampaignDefinition]
    specimens: tuple[FamilySpecimen, ...]
    items: tuple[WizardItem, ...]

    @property
    def gaps(self) -> tuple[WizardItem, ...]:
        own = tuple(item for item in self.items if item.status in GAPS)
        return own + tuple(gap for s in self.specimens for gap in s.preparation.gaps)

    @property
    def loaded(self) -> bool:
        return self.definition is not None


# ----------------------------------------------------------------------------------------------- locating

def locate_passport(folder: Path) -> Path:
    """The specimen passport of a folder: ``specimen.json``, else exactly one ``*.specimen.json``.

    Several candidates are refused (never chosen for the user).
    """

    folder = Path(folder)
    if not folder.is_dir():
        raise WizardInputError(f"{folder} is not a folder.")
    exact = folder / PASSPORT_NAME
    if exact.is_file():
        return exact
    try:
        candidates = sorted(p for p in folder.iterdir() if p.is_file() and p.name.endswith(PASSPORT_SUFFIX))
    except OSError as error:
        raise WizardInputError(f"{folder} cannot be read: {error}.") from error
    if not candidates:
        raise WizardInputError(f"no specimen passport in {folder}: expected {PASSPORT_NAME} or one *{PASSPORT_SUFFIX}.")
    if len(candidates) > 1:
        raise WizardInputError(f"several specimen passports in {folder} ({', '.join(p.name for p in candidates)}); "
                               "select the passport file itself.")
    return candidates[0]


def folder_inventory(folder: Path) -> tuple[FolderFile, ...]:
    """Files directly in the specimen folder, by kind (extension only; contents are not interpreted)."""

    files = []
    try:
        paths = sorted(p for p in Path(folder).iterdir() if p.is_file())
    except OSError:
        return ()
    for path in paths:
        name, suffix = path.name, path.suffix.lower()
        if name == PASSPORT_NAME or name.endswith(PASSPORT_SUFFIX):
            kind = "specimen_passport"
        elif suffix == ".inp":
            kind = "model_input"
        elif suffix in (".unv", ".uff"):
            kind = "universal_file"
        elif suffix == ".odb":
            kind = "odb"
        elif suffix in _PHOTO_SUFFIXES:
            kind = "photo"
        else:
            kind = "other"
        files.append(FolderFile(name, kind, path.stat().st_size))
    return tuple(files)


def load_fixtures(repo_root: Path) -> ExperimentFixtureManifest:
    return load_experiment_fixture_manifest(Path(repo_root).joinpath(*FIXTURE_MANIFEST.parts))


# ----------------------------------------------------------------------------------------------- specimen

def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _physical(passport: SpecimenManifest, name: str, label: str, value: Optional[str]) -> WizardItem:
    if getattr(passport, name) is None:  # the parser admits null only when declared unavailable with a reason
        return WizardItem("Physical measurements", label, "", ItemStatus.UNAVAILABLE, passport.unavailable[name])
    return WizardItem("Physical measurements", label, value or "", ItemStatus.PRESENT)


def _file_item(section: str, label: str, reference: ExternalFileReference,
               roots: Optional[Mapping[str, Path]]) -> WizardItem:
    where = f"store {reference.location.store}: {reference.location.relative_path}"
    detail = f"{where}; {reference.size_bytes} bytes; SHA-256 {reference.sha256}"
    if roots is None:
        return WizardItem(section, label, reference.file_name, ItemStatus.INFO,
                          detail + "; stores not checked; SHA-256 not verified")
    try:
        resolve_external_file(reference, roots, verify_sha256=False)
    except FixtureSourceUnavailableError as error:
        status = ItemStatus.NOT_CONFIGURED if reference.location.store not in roots else ItemStatus.NOT_FOUND
        return WizardItem(section, label, reference.file_name, status, f"{error} ({detail})")
    except FixtureSourceMismatchError as error:
        return WizardItem(section, label, reference.file_name, ItemStatus.MISMATCH, f"{error} ({detail})")
    return WizardItem(section, label, reference.file_name, ItemStatus.PRESENT_SHA256_NOT_VERIFIED,
                      detail + "; present with the pinned size; SHA-256 NOT verified here (the backend verifies it "
                               "when the file is used)")


def _passport_items(passport: SpecimenManifest, path: Path, roots) -> list[WizardItem]:
    items = [
        WizardItem("Identity", "Passport", path.name, ItemStatus.PRESENT,
                   f"{passport.schema}; manifest hash {passport.manifest_hash}"),
        WizardItem("Identity", "Specimen type", passport.specimen_type, ItemStatus.PRESENT),
        WizardItem("Identity", "Family", str(passport.family_id), ItemStatus.PRESENT),
        WizardItem("Identity", "Design", str(passport.design_id), ItemStatus.PRESENT),
    ]
    if passport.physical_specimen_id is None:
        items.append(WizardItem("Identity", "Physical specimen", "", ItemStatus.UNAVAILABLE,
                                passport.unavailable.get("physical_specimen_id", "")))
    else:
        items.append(WizardItem("Identity", "Physical specimen", str(passport.physical_specimen_id),
                                ItemStatus.PRESENT))
    items.append(WizardItem("Identity", "Test run", str(passport.test_run_id), ItemStatus.PRESENT))

    plan = passport.plan_mm
    items.append(_physical(passport, "plan_mm", "Plan dimensions",
                           plan and f"{plan.lx_mm:g} x {plan.ly_mm:g} mm (sd {plan.sd_mm:g} mm)"))
    masses = passport.masses_g
    items.append(_physical(passport, "masses_g", "Masses",
                           masses and ", ".join(f"{k} {v:g} g" for k, v in sorted(masses.items()))))
    faces = passport.face_thickness_mm
    items.append(_physical(passport, "face_thickness_mm", "Face thickness",
                           faces and ", ".join(f"{k}: {len(v)} points" for k, v in sorted(faces.items()))))
    core = passport.core_height_mm
    items.append(_physical(passport, "core_height_mm", "Core height",
                           core and f"{core.value_mm:g} mm (sd {core.sd_mm:g} mm)"))
    materials = passport.materials
    items.append(_physical(passport, "materials", "Materials (face / core / adhesive roles)",
                           materials and ", ".join(f"{k}: {v}" for k, v in sorted(materials.items()))))
    suspension = passport.suspension_max_hz
    items.append(_physical(passport, "suspension_max_hz", "Suspension limit",
                           suspension and f"{suspension.value_hz:g} Hz"))

    calibration = passport.geometry_calibration
    items.append(WizardItem("Physical registration", "Geometry calibration basis", calibration.mode,
                            ItemStatus.PRESENT, json.dumps(dict(calibration.coordinate_calibration))))
    basis = calibration.registration_basis_status.value
    items.append(WizardItem("Physical registration", "Registration basis", basis,
                            ItemStatus.PRESENT if not calibration.missing_physical_evidence else ItemStatus.MISSING,
                            "; ".join(calibration.missing_physical_evidence)))
    items.append(WizardItem("Physical registration", "Orientation reference", calibration.orientation.reference,
                            ItemStatus.PRESENT, calibration.orientation.source))
    surface = calibration.measured_surface
    items.append(WizardItem("Physical registration", "Measured surface", f"{surface.fe_instance} ({surface.side})",
                            ItemStatus.PRESENT, surface.label))
    uncertainty = calibration.uncertainty_availability.value
    items.append(WizardItem("Physical registration", "Calibration uncertainty", uncertainty,
                            ItemStatus.PRESENT if not calibration.missing_uncertainty else ItemStatus.MISSING,
                            "missing: " + ", ".join(calibration.missing_uncertainty)
                            if calibration.missing_uncertainty else ""))

    acquisition = passport.acquisition
    items.append(WizardItem("Acquisition", "Session", acquisition.session, ItemStatus.PRESENT))
    items.append(WizardItem("Acquisition", "Measurement grid",
                            f"{acquisition.grid.grid_id} ({acquisition.grid.point_count} points)", ItemStatus.PRESENT))
    items.append(WizardItem("Acquisition", "Remount linkage",
                            f"{acquisition.remount_kind} of {acquisition.remount_of}" if acquisition.remount_of
                            else "first mounting (no remount recorded)",
                            ItemStatus.PRESENT if acquisition.remount_of else ItemStatus.INFO,
                            acquisition.remount_evidence or ""))
    items.append(WizardItem("Acquisition", "Experiment fixture", acquisition.fixture_id or "",
                            ItemStatus.PRESENT if acquisition.fixture_id else ItemStatus.MISSING,
                            "" if acquisition.fixture_id else
                            "the passport links no experiment fixture: no governed modal data or FE input"))

    reference = passport.fe_reference
    items.append(WizardItem("FE reference", "FE model", reference.model_name, ItemStatus.PRESENT,
                            f"geometry identity {reference.geometry_identity.sha256} "
                            f"({reference.geometry_identity.node_count} nodes)"))
    items.append(_file_item("FE reference", "FE geometry file", reference.geometry_file, roots))
    items.append(WizardItem("Identification request", "Identify", passport.identify, ItemStatus.PRESENT))
    return items


def _fixture_items(passport: SpecimenManifest, fixtures: Optional[ExperimentFixtureManifest],
                   roots) -> tuple[Optional[ExperimentFixture], list[WizardItem]]:
    fixture_id = passport.acquisition.fixture_id
    if fixture_id is None:
        return None, []
    if fixtures is None:
        return None, [WizardItem("Input files", "Fixture manifest", "", ItemStatus.MISSING,
                                 f"the fixture manifest {FIXTURE_MANIFEST} could not be loaded")]
    try:
        fixture = fixtures.fixture(fixture_id)
    except KeyError:
        return None, [WizardItem("Input files", "Experiment fixture", fixture_id, ItemStatus.MISSING,
                                 f"fixture {fixture_id!r} is not in {FIXTURE_MANIFEST}")]
    items = []
    for label, mine, theirs in (("Physical specimen (fixture)", passport.physical_specimen_id,
                                 fixture.physical_specimen_id),
                                ("Test run (fixture)", passport.test_run_id, fixture.test_run_id)):
        if theirs is None:
            continue
        agree = mine is not None and str(mine) == theirs
        items.append(WizardItem("Identity", label, theirs, ItemStatus.PRESENT if agree else ItemStatus.MISMATCH,
                                "" if agree else f"the passport records {mine!r}"))
    modal = fixture.modal_set
    items.append(_file_item("Input files", "Modes (curve-fitted modal set)", fixture.experimental_source, roots))
    items.append(WizardItem("Input files", "Modal set", modal.display_name, ItemStatus.PRESENT,
                            f"{modal.source_type}; {modal.mode_count} modes; {modal.measurement_point_count} points; "
                            f"DOFs {', '.join(modal.measured_dofs)}; face {modal.measured_face}"))
    items.append(_file_item("Input files", "FE model input", fixture.fe.model_input, roots))
    items.append(_file_item("Input files", "Reference ODB", fixture.fe.odb_reference, roots))
    items.append(WizardItem("Input files", "Frozen registration", fixture.registration.path, ItemStatus.PRESENT,
                            f"registration hash {fixture.registration.registration_hash}"))
    for gap in fixture.unresolved:
        items.append(WizardItem("Input files", f"Unresolved: {gap.field}", "", ItemStatus.MISSING, gap.reason))
    return fixture, items


def _folder_items(files: tuple[FolderFile, ...]) -> list[WizardItem]:
    labels = {"model_input": "Model input (local)", "universal_file": "Universal file (local)",
              "odb": "ODB / cache (local)", "photo": "Photo", "other": "Other file"}
    note = "listed only; the backend uses the pinned references above, never an unpinned local file"
    return [WizardItem("Specimen folder", labels[f.kind], f.name, ItemStatus.INFO, f"{f.size_bytes} bytes; {note}")
            for f in files if f.kind != "specimen_passport"]


def prepare_specimen_passport(path: Path, repo_root: Path, roots: Optional[Mapping[str, Path]] = None,
                              fixtures: Optional[ExperimentFixtureManifest] = None,
                              folder_files: tuple[FolderFile, ...] = ()) -> SpecimenPreparation:
    """Load one passport through the governed parser and report its facts and gaps."""

    path = Path(path)
    if fixtures is None:
        try:
            fixtures = load_fixtures(repo_root)
        except (OSError, FixtureManifestError):
            fixtures = None
    try:
        passport = load_specimen_manifest(path)
    except SpecimenManifestError as error:
        items = [WizardItem("Identity", "Passport", path.name, ItemStatus.INVALID, str(error))]
        return SpecimenPreparation(str(path), path, None, None, folder_files, tuple(items + _folder_items(folder_files)))
    except (OSError, json.JSONDecodeError) as error:
        items = [WizardItem("Identity", "Passport", path.name, ItemStatus.INVALID, f"cannot read: {error}")]
        return SpecimenPreparation(str(path), path, None, None, folder_files, tuple(items + _folder_items(folder_files)))
    fixture, fixture_items = _fixture_items(passport, fixtures, roots)
    items = _passport_items(passport, path, roots) + fixture_items + _folder_items(folder_files)
    return SpecimenPreparation(str(path), path, passport, fixture, folder_files, tuple(items))


def prepare_specimen_folder(folder: Path, repo_root: Path, roots: Optional[Mapping[str, Path]] = None,
                            fixtures: Optional[ExperimentFixtureManifest] = None) -> SpecimenPreparation:
    """Option A: a specimen folder holding its passport (and, optionally, local files and photos)."""

    folder = Path(folder)
    files = folder_inventory(folder) if folder.is_dir() else ()
    try:
        passport_path = locate_passport(folder)
    except WizardInputError as error:
        items = (WizardItem("Identity", "Passport", "", ItemStatus.MISSING, str(error)),) + tuple(_folder_items(files))
        return SpecimenPreparation(str(folder), None, None, None, files, items)
    return prepare_specimen_passport(passport_path, repo_root, roots, fixtures, files)


# ----------------------------------------------------------------------------------------------- family

def _repo_path(repo_root: Path, relative: str) -> Path:
    return Path(repo_root).joinpath(*PurePosixPath(relative).parts)


def prepare_family(campaign_path: Path, repo_root: Path, roots: Optional[Mapping[str, Path]] = None,
                   fixtures: Optional[ExperimentFixtureManifest] = None) -> FamilyPreparation:
    """Option B: a governed family / campaign definition and the passports of its specimens (read-only)."""

    campaign_path = Path(campaign_path)
    if fixtures is None:
        try:
            fixtures = load_fixtures(repo_root)
        except (OSError, FixtureManifestError):
            fixtures = None
    try:
        definition = load_campaign_definition(campaign_path)
    except (CampaignDefinitionError, OSError, json.JSONDecodeError) as error:
        items = (WizardItem("Campaign", "Definition", campaign_path.name, ItemStatus.INVALID, str(error)),)
        return FamilyPreparation(str(campaign_path), campaign_path, None, (), items)

    fitted = ", ".join(definition.fitted_parameters)
    fixed = ", ".join(f"{k} {v:g}" for k, v in sorted(definition.fixed_parameters.items())) or "none"
    items = [
        WizardItem("Campaign", "Definition", definition.campaign_id, ItemStatus.PRESENT,
                   f"campaign hash {definition.campaign_hash}; decision {definition.decision}"),
        WizardItem("Campaign", "Run type", definition.run_type, ItemStatus.PRESENT,
                   f"executable gate: {definition.run_b_gate}" if definition.run_b_gate else ""),
        WizardItem("Campaign", "Fitted parameters", fitted, ItemStatus.PRESENT,
                   "; ".join(f"{k}: start {definition.start[k]:g}, bounds {definition.bounds[k][0]:g}-"
                             f"{definition.bounds[k][1]:g}" for k in definition.fitted_parameters)),
        WizardItem("Campaign", "Fixed parameters", fixed, ItemStatus.PRESENT),
        WizardItem("Campaign", "Not fitted", ", ".join(sorted(definition.not_fitted)), ItemStatus.INFO,
                   "; ".join(f"{k}: {v}" for k, v in sorted(definition.not_fitted.items()))),
        WizardItem("Campaign", "Sigma", f"setup {definition.sigma.setup_sd_ln:g} ln "
                   f"({definition.sigma.to_dict()['setup']['status']}); measurement "
                   f"{definition.sigma.to_dict()['measurement']['status']}", ItemStatus.PRESENT),
        WizardItem("Campaign", "Abaqus solve budget", str(definition.abaqus_solve_budget), ItemStatus.PRESENT,
                   "hard ceiling; execution needs a HUMAN gate (not started by the wizard)"),
    ] + _question_items(definition)
    specimens = []
    for spec in definition.specimens:
        try:
            model = load_bound_forward_model(_repo_path(repo_root, spec.forward_model), repo_root, fixtures)
        except (ForwardModelManifestError, SpecimenManifestError, FixtureManifestError, KeyError, OSError) as error:
            failed = SpecimenPreparation(spec.forward_model, None, None, None, (), (
                WizardItem("Identity", "Passport", spec.forward_model, ItemStatus.INVALID, str(error)),))
            specimens.append(FamilySpecimen(spec.label, spec.fixture_id, spec.fit_rows, spec.holdout_rows, failed))
            continue
        passport_path = _repo_path(repo_root, model.manifest.specimen_passport.path)
        preparation = prepare_specimen_passport(passport_path, repo_root, roots, fixtures)
        preparation = _with_forward_model(preparation, spec, model, roots)
        linked = model.passport.acquisition.fixture_id == spec.fixture_id
        items.append(WizardItem("Specimens", spec.label,
                                f"{spec.fixture_id}; FIT {', '.join(spec.fit_rows)}; "
                                f"HOLDOUT {', '.join(spec.holdout_rows)}",
                                ItemStatus.PRESENT if linked else ItemStatus.MISMATCH,
                                f"forward model {spec.forward_model}; passport {passport_path.name}" if linked else
                                f"the passport links fixture {model.passport.acquisition.fixture_id!r}"))
        specimens.append(FamilySpecimen(spec.label, spec.fixture_id, spec.fit_rows, spec.holdout_rows, preparation))
    return FamilyPreparation(str(campaign_path), campaign_path, definition, tuple(specimens), tuple(items))


def _question_items(definition: CampaignDefinition) -> list[WizardItem]:
    """The declared SPEC v1.2 question and τ_mf, exactly as declared (v1 definitions declare neither)."""

    question, tau = definition.scientific_question, definition.tau_mf
    if question is None:
        items = [WizardItem("Scientific question", "Declared question", "", ItemStatus.NOT_DECLARED,
                            f"{definition.schema}: no scientific question is declared (historical v1 definition); "
                            "none is inferred")]
    else:
        note = {MATERIAL_IDENTIFICATION: "material identification; never turned into a specimen calibration",
                SPECIMEN_ENGINEERING_CALIBRATION: "specimen engineering calibration (one physical specimen); "
                                                  "production calibration execution BLOCKED / NOT_AUTHORISED"}
        items = [WizardItem("Scientific question", "Declared question", question, ItemStatus.PRESENT,
                            f"{definition.schema}; {note.get(question, '')}")]
    items.append(WizardItem("Scientific question", "τ_mf", "" if tau is None else f"{tau:g}",
                            ItemStatus.NOT_DECLARED if tau is None else ItemStatus.PRESENT,
                            "not declared; no value is assumed" if tau is None else
                            "declared model-form acceptance tolerance in |Δ ln f| (never an uncertainty)"))
    return items


def _with_forward_model(preparation: SpecimenPreparation, spec, model, roots) -> SpecimenPreparation:
    """The campaign specimen's governed forward model (identity, pinned INP, registration agreement) and rows."""

    manifest = model.manifest
    items = [WizardItem("Forward model", "Forward model", manifest.forward_model_id, ItemStatus.PRESENT,
                        f"{spec.forward_model}; manifest hash {manifest.manifest_hash}; parameterisation "
                        f"{manifest.parameterisation.parameterisation_id}; material role {manifest.material_role}"),
             _file_item("Forward model", "Pinned model input (INP)", manifest.model_input, roots)]
    fixture = preparation.fixture
    if fixture is not None:
        agree = fixture.registration.registration_hash == manifest.registration_hash
        items.append(WizardItem("Forward model", "Registration (forward model vs fixture)", manifest.registration_hash,
                                ItemStatus.PRESENT if agree else ItemStatus.MISMATCH,
                                "" if agree else f"the fixture registration is {fixture.registration.registration_hash}"))
    items.append(WizardItem("Campaign rows", "FIT rows", ", ".join(spec.fit_rows), ItemStatus.PRESENT,
                            "declared by the campaign definition (not chosen by the wizard)"))
    items.append(WizardItem("Campaign rows", "HOLDOUT rows", ", ".join(spec.holdout_rows),
                            ItemStatus.PRESENT if spec.holdout_rows else ItemStatus.NOT_DECLARED,
                            "declared by the campaign definition (not chosen by the wizard)"))
    return SpecimenPreparation(preparation.source, preparation.passport_path, preparation.passport,
                               preparation.fixture, preparation.folder_files, preparation.items + tuple(items))


# ----------------------------------------------------------------------------------------------- selection ↔ readiness (M8.2)

READINESS_RECORD_SCHEMA = "auto-id/v12-scientific-readiness/v1"  # services.campaign_scientific_backend.SCHEMA


class SelectionState(str, Enum):
    """Presentation states of a stored readiness record against the GUI selection (never a scientific verdict)."""

    NO_SELECTION = "NO_SELECTION"  # nothing selected: a stored record is shown for its own campaign identity only
    NOT_EVALUATED_FOR_SELECTION = "NOT_EVALUATED_FOR_SELECTION"  # no stored record of the selected source
    MATCHED_STORED_RECORD = "MATCHED_STORED_RECORD"  # the stored record's governed identity is the selection's


@dataclass(frozen=True)
class ReadinessSelection:
    state: SelectionState
    detail: str
    show_record: bool  # whether the stored record may be presented under this selection


def readiness_selection(selected: bool, preparation, record, run_hash: Optional[str] = None,
                        evaluated_run_hash: Optional[str] = None,
                        evaluation_current: Optional[bool] = None) -> ReadinessSelection:
    """Bind a stored backend readiness record to the current selection, by governed identity only.

    A record is presented for a selected family / campaign only when its campaign identity is the governed
    ``CampaignDefinition``'s: the exact campaign hash, the same run type, the same specimen labels in definition order,
    the same declared scientific question and τ_mf (both undeclared for a v1 definition), and the same run hash when a
    run is selected.  Names, folders, labels or file names alone never match.  ``evaluated_run_hash`` is given only for
    the record the GUI itself obtained by evaluating that run (M8.3): a backend refusal that came before the run identity
    could be verified carries no run hash and is then bound to the run that was evaluated; such a record is shown only
    while exactly that run is selected.  ``evaluation_current`` is given (True / False) only for such a GUI-evaluated
    record: False — the evaluation is not the current successful evaluation of the exact selected journal (a new run
    selection, a new evaluation attempt or a failed one) — never presents it, with no fallback to a campaign-only match.  A specimen folder declares no governed
    campaign, so no campaign result is attached to it and no question is inferred.  Presentation only: the record is
    neither changed nor re-judged, and a match is not proof that a stored record is authentic.
    """

    is_record = isinstance(record, Mapping) and record.get("schema") == READINESS_RECORD_SCHEMA
    if not selected:
        return ReadinessSelection(SelectionState.NO_SELECTION,
                                  "no source selected: a stored record is shown for its own campaign identity, not "
                                  "for a selection" if is_record else "no source selected", is_record)

    def not_evaluated(reason: str) -> ReadinessSelection:
        return ReadinessSelection(SelectionState.NOT_EVALUATED_FOR_SELECTION, reason, False)

    if evaluation_current is False:
        return not_evaluated("no current evaluation of the selected run: the earlier result is not presented for this "
                             "selection (press Auto-ID — Evaluate Stored Run)")

    if isinstance(preparation, SpecimenPreparation):
        return not_evaluated("a specimen folder declares no governed campaign: no scientific question is inferred and "
                             "no campaign readiness result is attached")
    if not isinstance(preparation, FamilyPreparation) or preparation.definition is None:
        return not_evaluated("the selected source could not be loaded as a governed campaign definition")
    definition = preparation.definition
    if not is_record:
        return not_evaluated(f"no stored backend readiness record for campaign {definition.campaign_id}")
    if evaluated_run_hash is not None and run_hash != evaluated_run_hash:
        return not_evaluated(f"the stored record is the evaluation of run {evaluated_run_hash[:12]}, which is not the "
                             "currently selected run")
    campaign = record.get("campaign") if isinstance(record.get("campaign"), Mapping) else {}
    expected = {"campaign hash": (campaign.get("campaign_hash"), definition.campaign_hash),
                "run type": (campaign.get("run_type"), definition.run_type),
                "specimens": (list(campaign.get("specimens") or ()), [s.label for s in definition.specimens]),
                "scientific question": (record.get("scientific_question"), definition.scientific_question),
                "τ_mf": (record.get("tau_mf"), definition.tau_mf)}
    if run_hash is not None:
        stored_run = campaign.get("run_hash")
        if stored_run is None and evaluated_run_hash is not None:
            stored_run = evaluated_run_hash
        expected["run hash"] = (stored_run, run_hash)
    differing = [name for name, (stored, governed) in expected.items() if stored != governed]
    if differing:
        return not_evaluated(f"the stored record belongs to another campaign or run ({', '.join(differing)} differ: "
                             f"record campaign {campaign.get('campaign_id')!r}); it is not shown for "
                             f"{definition.campaign_id}")
    return ReadinessSelection(SelectionState.MATCHED_STORED_RECORD,
                              f"stored backend record of campaign {definition.campaign_id} (campaign hash "
                              f"{definition.campaign_hash[:12]}) shown as stored; a matching identity is not proof "
                              "that the record is authentic or verified production evidence", True)


# ----------------------------------------------------------------------------------------------- verdict summary (M8.5)

def _values(parameters, suffix: str = "") -> str:
    items = []
    for name, item in sorted((parameters or {}).items()):
        value = item.get("value") if isinstance(item, Mapping) else item
        unit = item.get("unit") if isinstance(item, Mapping) else None
        items.append(f"{name} = {float(value):.6g}{'' if not unit else ' ' + unit}")
    return ", ".join(items) + (f" ({suffix})" if suffix and items else "")


MATERIAL_NOT_EVALUATED = ("not evaluated in this run: the campaign declares SPECIMEN_ENGINEERING_CALIBRATION and "
                          "the backend records no material-identification verdict for it (the material path refuses "
                          "a calibration definition: no automatic fallback, D-078)")


def material_verdict(record) -> tuple[tuple[str, str], ...]:
    """The material verdict of a stored readiness record, shown first and unchanged (SPEC v1.2 §1; audit V1).

    Presentation only: read from the record (``ScientificReadiness.to_dict``); nothing is judged, recomputed or
    inferred. A calibration record carries no material verdict, so none is shown as computed.
    """

    if not isinstance(record, Mapping) or record.get("schema") != READINESS_RECORD_SCHEMA:
        return ()
    question = record.get("scientific_question")
    status = str(record.get("status", ""))
    reasons = "; ".join(f"{r.get('code')}: {r.get('detail')}" for r in record.get("refusal_reasons") or ()
                        if isinstance(r, Mapping))
    if question == "SPECIMEN_ENGINEERING_CALIBRATION":
        return (("Material verdict — question", f"MATERIAL_IDENTIFICATION {MATERIAL_NOT_EVALUATED}"),
                ("Material verdict — formal output", "NOT_AVAILABLE (no material verdict is recorded for this run)"),
                ("Material verdict — status", "NOT_EVALUATED: no material property; a calibration result never "
                                              "replaces a material verdict"),
                ("Calibration verdict", f"{status} (SPECIMEN_ENGINEERING_CALIBRATION; never a material property)"))
    formal = record.get("material_formal_output") if isinstance(record.get("material_formal_output"), Mapping) else {}
    family = record.get("material_family_consistency")
    asked = ("MATERIAL_IDENTIFICATION" if question == "MATERIAL_IDENTIFICATION" else
             "MATERIAL_IDENTIFICATION (historical v1 definition; question not declared)" if question is None else
             f"{question} (not a recognised question)")
    if status == "MATERIAL_VALUES_RELEASED" and formal.get("released_values"):
        verdict = (f"MATERIAL_VALUES_RELEASED: {_values(formal['released_values'], 'effective model parameters')}; "
                   f"material claim {record.get('material_claim')}")
    elif formal:
        verdict = (f"REFUSED: {formal.get('status')}"
                   + (f"; SPEC §13 family consistency {family}" if family else "")
                   + f"; no global material property; material claim {record.get('material_claim')}"
                   + (f" — {reasons}" if reasons else ""))
    else:
        verdict = f"{status}: no material verdict was judged" + (f" — {reasons}" if reasons else "")
    return (("Material verdict — question", asked),
            ("Material verdict — formal output", str(formal.get("status")) if formal else "NOT_AVAILABLE (not judged)"),
            ("Material verdict — status", verdict),
            ("Calibration verdict", "not applicable: a material-identification campaign never produces a calibration "
                                    "(no automatic fallback)"))


def verdict_summary(record) -> tuple[str, ...]:
    """A concise read-only summary of a stored backend readiness record (``ScientificReadiness.to_dict``).

    Presentation only: every statement is read from the record — no value, threshold, uncertainty or decision is
    computed, inferred or relabelled.  A value is named as released only from the record's released fields (the
    specimen calibration with the record's own labels; material identification only from its formal output when the
    status is MATERIAL_VALUES_RELEASED); a refused record's candidate stays diagnostic only.
    """

    if not isinstance(record, Mapping) or record.get("schema") != READINESS_RECORD_SCHEMA:
        return ()
    status = str(record.get("status"))
    question = record.get("scientific_question")
    tau = record.get("tau_mf")
    campaign = record.get("campaign") if isinstance(record.get("campaign"), Mapping) else {}
    evidence = record.get("evidence") if isinstance(record.get("evidence"), Mapping) else {}
    formal = record.get("material_formal_output") if isinstance(record.get("material_formal_output"), Mapping) else {}
    calibration = record.get("calibration") if isinstance(record.get("calibration"), Mapping) else {}
    reasons = [r for r in record.get("refusal_reasons") or () if isinstance(r, Mapping)]
    lines = [f"Evaluated: {campaign.get('campaign_id')} ({campaign.get('run_type')}); campaign "
             f"{str(campaign.get('campaign_hash'))[:12]}; run {str(campaign.get('run_hash') or 'not verified')[:12]}",
             f"Scientific question: {question or 'not declared (historical v1 definition; none inferred)'}; τ_mf "
             f"{'not declared' if tau is None else f'{tau:g} (acceptance tolerance only)'}"]
    lines += [f"{label}: {value}" for label, value in material_verdict(record)]  # audit V1: material verdict first
    lines.append(f"Backend status: {status}")
    released = record.get("released_calibration_parameters")
    if status == "RELEASED" and released:
        labels = ", ".join(calibration.get("labels") or ())
        lines.append(f"Released: {_values(released)} — {labels}")
        lines.append("Result type: specimen-specific engineering calibration of one physical specimen and one FE "
                     "model; not a material property")
    elif status == "MATERIAL_VALUES_RELEASED" and formal.get("released_values"):
        lines.append(f"Released (formal output {formal.get('status')}): "
                     f"{_values(formal.get('released_values'), 'effective material-model values')}")
        lines.append(f"Result type: material identification; material claim {record.get('material_claim')}")
    else:
        lines.append("Released: no value released")
        if reasons:
            shown = "; ".join(f"{r.get('code')}: {r.get('detail')}" for r in reasons[:4])
            more = f" (+{len(reasons) - 4} more)" if len(reasons) > 4 else ""
            lines.append(f"{'Not ready — missing or invalid evidence' if status == 'NOT_READY' else 'Refused'}: "
                         f"{shown}{more}")
        if formal:
            family = record.get("material_family_consistency")
            lines.append(f"Material formal output: {formal.get('status')}"
                         + (f"; SPEC §13 family consistency {family}" if family else ""))
        if question == "SPECIMEN_ENGINEERING_CALIBRATION":
            lines.append("Result type: specimen engineering calibration (not a material property); none released")
        else:
            lines.append("Result type: material identification; no global material property released")
    candidate = record.get("diagnostic_candidate") if isinstance(record.get("diagnostic_candidate"), Mapping) else {}
    if candidate.get("parameters"):
        lines.append(f"Diagnostic only (not released): {_values(candidate.get('parameters'))} "
                     f"[{', '.join(candidate.get('labels') or ())}]")
    profiles = evidence.get("solver_profiles") if isinstance(evidence.get("solver_profiles"), Mapping) else {}
    if profiles:
        lines.append("Evidence solver profiles: " + "; ".join(f"{label}: {item.get('profile_id')}" for label, item
                                                             in sorted(profiles.items()) if isinstance(item, Mapping)))
    if record.get("production_calibration"):
        lines.append(f"Physical calibration status: {record.get('production_calibration')}")
    lines.append(f"Production execution: {record.get('production_execution')}")
    return tuple(lines)


# ----------------------------------------------------------------------------------------------- M8.7 breakdown

NOT_AVAILABLE_TEXT = "NOT_AVAILABLE"
_COMPLETE_BASES = ("COVARIANCE_COMPONENTS_COMPLETE_AND_MEASURED", "COMPLETE_MEASURED_COVARIANCE")
_CONDITIONAL_BASES = ("UNCERTAINTY_CONDITIONAL_ON_AVAILABLE_COVARIANCE", "CONDITIONAL_ON_AVAILABLE_COVARIANCE")
_TYPED_ONLY = ("the formal M5 evidence is held only by the current typed evaluation of the selected run; this stored "
               "record does not contain it")


def _mapping(value) -> Mapping:
    return value if isinstance(value, Mapping) else {}


def _number(value) -> Optional[str]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return repr(float(value))  # exactly as recorded, never rounded


def _missing(reason: str) -> str:
    return f"{NOT_AVAILABLE_TEXT} — {reason}"


def _recorded(value, reason: str, suffix: str = "") -> str:
    number = _number(value)
    return _missing(reason) if number is None else number + suffix


def _exact(parameters) -> str:
    items = []
    for name, item in sorted(_mapping(parameters).items()):
        value = item.get("value") if isinstance(item, Mapping) else item
        unit = item.get("unit") if isinstance(item, Mapping) else None
        items.append(f"{name} = {_number(value) or _missing('not recorded')}{'' if not unit else ' ' + unit}")
    return ", ".join(items)


def _gate_details(calibration: Mapping, code: str) -> list[str]:
    return [str(r.get("detail")) for r in calibration.get("refusal_reasons") or ()
            if isinstance(r, Mapping) and r.get("code") == code]


def uncertainty_breakdown(record, material_report=None) -> tuple[tuple[str, str, str], ...]:
    """Read-only uncertainty and evidence-source breakdown of a stored backend readiness record (M8.7).

    Rows (section, item, recorded value).  Every value is read from the record (``ScientificReadiness.to_dict``) or,
    for material identification only, from the backend's formal campaign report of the *current typed evaluation*
    (``material_report``; never rebuilt from a dictionary of another origin).  Nothing is computed: no covariance,
    statistical_sd, Birge adjustment, model-form range, precision envelope or decision.  A missing quantity is
    NOT_AVAILABLE with its recorded reason, never zero or a replacement; a conditional covariance basis is never called
    a complete measured uncertainty; τ_mf is shown only as an acceptance tolerance on |Δ ln f|.
    """

    if not isinstance(record, Mapping) or record.get("schema") != READINESS_RECORD_SCHEMA:
        return ()
    rows: list[tuple[str, str, str]] = []

    def add(section: str, item: str, value) -> None:
        rows.append((section, item, str(value)))

    status = str(record.get("status"))
    question = record.get("scientific_question")
    calibration_question = question == "SPECIMEN_ENGINEERING_CALIBRATION"
    calibration = _mapping(record.get("calibration"))
    report = material_report if isinstance(material_report, Mapping) and not calibration_question else None
    reasons = [r for r in record.get("refusal_reasons") or () if isinstance(r, Mapping)]
    precision = _mapping(calibration.get("precision"))
    parameters = _mapping(precision.get("parameters"))
    verdicts = _mapping(_mapping(report.get("m5_verdict")).get("verdicts")) if report else {}
    not_ready = status == "NOT_READY"

    # ------------------------------------------------------------------ status and evidence role
    section = "Status"
    add(section, "Backend status", status)
    add(section, "Evidence role", {
        "RELEASED": "released specimen calibration record — readiness evidence only, NOT AUTHORISED FOR PRODUCTION",
        "MATERIAL_VALUES_RELEASED": "formal M5 evidence behind the formally released material values",
        "REFUSED": "REFUSED — every quantity below is supporting / diagnostic evidence only, never a release",
        "NOT_READY": "NOT_READY — no scientific judgement was made; quantities that need the missing evidence are "
                     "NOT_AVAILABLE",
    }.get(status, f"{status} (as recorded)"))
    for r in reasons:
        add(section, "Missing / invalid evidence" if not_ready else "Refusal", f"{r.get('code')}: {r.get('detail')}")

    # ------------------------------------------------------------------ A covariance basis
    section = "A · Covariance basis"
    basis = _mapping(record.get("uncertainty_basis"))
    components = _mapping(basis.get("covariance_components"))
    if not basis:
        add(section, "Covariance basis", _missing("no uncertainty basis in this record"
                                                  + (" (NOT_READY: not evaluated)" if not_ready else "")))
    else:
        add(section, "Σ_setup status", components.get("sigma_setup") or _missing("not recorded"))
        add(section, "Σ_meas status", components.get("sigma_meas") or _missing("not recorded"))
        kind = basis.get("basis") or basis.get("statistical_sd_status")
        add(section, "Recorded basis", kind or _missing("not recorded"))
        if basis.get("conditional_on_available_covariance") is True or kind in _CONDITIONAL_BASES:
            extent = "CONDITIONAL on the available covariance components — not a complete measured uncertainty"
        elif kind in _COMPLETE_BASES and basis.get("conditional_on_available_covariance") is not True:
            extent = "COMPLETE (as recorded: all covariance components measured)"
        else:
            extent = _missing("the record states no recognised basis; never presented as complete")
        add(section, "Complete / conditional", extent)
        provisional = sorted(k for k, v in components.items() if v == "PROVISIONAL")
        missing = sorted(k for k, v in components.items() if v == NOT_AVAILABLE_TEXT)
        add(section, "Provisional components", ", ".join(provisional) or "none recorded")
        add(section, "Missing components", ", ".join(f"{k} (NOT_AVAILABLE, never zero)" for k in missing)
            or "none recorded")
        if basis.get("note") or basis.get("statement"):
            add(section, "Recorded statement", basis.get("note") or basis.get("statement"))
    if report:
        sigma = _mapping(report.get("sigma"))
        setup, measurement = _mapping(sigma.get("setup")), _mapping(sigma.get("measurement"))
        if setup:
            add(section, "Σ_setup (campaign report)", f"sd_ln {_recorded(setup.get('sd_ln'), 'not recorded')} "
                                                      f"{setup.get('status')}; source: {setup.get('source')}")
        if measurement:
            add(section, "Σ_meas (campaign report)", f"{measurement.get('status')}; source: {measurement.get('source')}")

    # ------------------------------------------------------------------ B statistical uncertainty
    section = "B · Statistical uncertainty"
    qualifier = " ln p (conditional on the available covariance)" if components.get("sigma_meas") == NOT_AVAILABLE_TEXT \
        or components.get("sigma_setup") == "PROVISIONAL" else " ln p"
    if status == "REFUSED":
        qualifier += "; supporting / diagnostic evidence only (REFUSED)"
    if calibration_question:
        names = sorted(parameters) or ["fitted parameters"]
        recorded = _mapping(calibration.get("statistical_sd"))
        why = f"{recorded.get('status')}: " + ("; ".join(recorded.get("reasons") or ()) or "no value recorded")
        for name in names:
            if not calibration:
                add(section, f"statistical_sd · {name}", _missing("no calibration output record (not evaluated)"))
            elif not recorded:
                add(section, f"statistical_sd · {name}", _missing(
                    "not recorded in this calibration output record (schema before audit V2)"))
            else:
                add(section, f"statistical_sd · {name}", _recorded(
                    _mapping(recorded.get("statistical_sd_ln")).get(name), why, qualifier))
    elif verdicts:
        for name, verdict in sorted(verdicts.items()):
            verdict = _mapping(verdict)
            add(section, f"statistical_sd · {name}", _recorded(verdict.get("statistical_sd_ln"), "; ".join(
                verdict.get("reasons") or ()) or "not recorded", qualifier))
    else:
        add(section, "statistical_sd", _missing("not evaluated (NOT_READY)" if not_ready else _TYPED_ONLY))

    # ------------------------------------------------------------------ C Birge adjustment
    section = "C · Birge adjustment"
    if calibration_question:
        unavailable = "; ".join(_gate_details(calibration, "BIRGE_UNAVAILABLE"))
        if not parameters:
            add(section, "birge_adjusted_sd", _missing("no calibration output record (not evaluated)"))
        for name, item in sorted(parameters.items()):
            value = _mapping(item).get("birge_adjusted_sd_ln")
            add(section, f"birge_adjusted_sd · {name}", _recorded(value, unavailable or "reason not recorded",
                                                                   qualifier + "; AVAILABLE"))
    elif verdicts:
        for name, verdict in sorted(verdicts.items()):
            verdict = _mapping(verdict)
            why = "; ".join(r for r in verdict.get("reasons") or () if "BIRGE" in str(r)) or "reason not recorded"
            add(section, f"birge_adjusted_sd · {name}", _recorded(verdict.get("birge_adjusted_sd_ln"), why,
                                                                   qualifier + "; AVAILABLE"))
    else:
        add(section, "birge_adjusted_sd", _missing("not evaluated (NOT_READY)" if not_ready else _TYPED_ONLY))

    # ------------------------------------------------------------------ D model-form robustness
    section = "D · Model-form robustness"
    if calibration_question:
        incomplete = "; ".join(_gate_details(calibration, "LOO_INCOMPLETE"))
        robustness = _mapping(calibration.get("model_form_robustness"))
        if robustness:
            incomplete = incomplete or ("" if robustness.get("status") == "AVAILABLE_COMPLETE_LOO" else
                                        "; ".join(robustness.get("reasons") or ()) or str(robustness.get("status")))
            add(section, "Leave-one-FIT-family-out status", str(robustness.get("status"))
                + (f" — {'; '.join(robustness.get('reasons'))}" if robustness.get("reasons") else ""))
            for case in robustness.get("cases") or ():
                case = _mapping(case)
                add(section, f"Case {case.get('family')}", case.get("status"))
        add(section, "Leave-one-FIT-family-out", ("INCOMPLETE (recorded refusal LOO_INCOMPLETE): " + incomplete)
            if incomplete else ("COMPLETE (recorded AVAILABLE_COMPLETE_LOO)" if robustness else
                                "no LOO_INCOMPLETE refusal recorded (schema before audit V2: no LOO status field)"
                                if calibration else _missing("no calibration output record (not evaluated)")))
        for name, item in sorted(parameters.items()):
            add(section, f"model_form_half_range · {name}", _recorded(
                _mapping(item).get("model_form_half_range_ln"),
                "incomplete leave-one-FIT-family-out: no model-form interval" if incomplete else "not recorded",
                " ln p (half-range of the leave-one-FIT-family-out shifts; model-dependence diagnostic, not a "
                "confidence interval)"))
    elif report:
        robustness = _mapping(report.get("model_form_robustness"))
        add(section, "Leave-one-family-out status", robustness.get("status") or _missing("not recorded"))
        add(section, "Label", robustness.get("label") or _missing("not recorded"))
        for case in robustness.get("cases") or ():
            case = _mapping(case)
            add(section, f"Case {case.get('family')}", case.get("status"))
        complete = robustness.get("status") == "AVAILABLE_COMPLETE_LOO"
        for name in sorted(verdicts) or sorted(_mapping(robustness.get("parameters"))):
            item = _mapping(_mapping(robustness.get("parameters")).get(name))
            add(section, f"half_range · {name} (campaign report)", _recorded(
                item.get("half_range_ln") if complete else None,
                "incomplete leave-one-family-out: no model-form interval" if not complete else "not recorded",
                " ln p (MODEL_DEPENDENCE_DIAGNOSTIC)"))
            model = _mapping(_mapping(verdicts.get(name)).get("model_form_robustness"))
            # with an incomplete set the M5 number covers the valid cases only (recorded interpretation): never shown
            add(section, f"half_range · {name} (M5 verdict)", _recorded(
                model.get("half_range_ln") if complete else None,
                "incomplete leave-one-family-out: the M5 number covers the valid cases only; not a model-form "
                "interval" if not complete else "not recorded", " ln p"))
        for reason in robustness.get("reasons") or ():
            add(section, "Interpretation (recorded)", reason)
    else:
        add(section, "Leave-one-family-out", _missing("not evaluated (NOT_READY)" if not_ready else _TYPED_ONLY))

    # ------------------------------------------------------------------ E conservative calibration uncertainty
    section = "E · Conservative calibration uncertainty"
    if calibration_question and precision:
        add(section, "Recorded envelope", f"{precision.get('envelope')} in {precision.get('space')}")
        add(section, "SPEC v1.2 precision ceiling (recorded)", f"{_recorded(precision.get('ceiling_ln'), 'not recorded')}"
                                                               " in ln p")
        missing = "; ".join(_gate_details(calibration, "MISSING_EVIDENCE")) or "not recorded"
        for name, item in sorted(parameters.items()):
            item = _mapping(item)
            value = _recorded(item.get("conservative_uncertainty_ln"), missing, " ln p")
            decision = "PASS" if item.get("pass") is True else "REFUSED"
            add(section, f"conservative_uncertainty · {name}", f"{value}; recorded decision {decision}")
        add(section, "τ_mf in the envelope (recorded)", precision.get("tau_mf_in_envelope"))
    elif calibration_question:
        add(section, "conservative_uncertainty", _missing("no calibration output record (not evaluated)"))
    else:
        add(section, "Calibration precision gate", "not applicable: the SPEC v1.2 precision gate belongs to a specimen "
                                                   "engineering calibration, not to material identification")
        for name, verdict in sorted(verdicts.items()):
            why = "; ".join(r for r in _mapping(verdict).get("reasons") or ()
                            if "BIRGE" in str(r) or "MODEL_FORM" in str(r)) or "not recorded"
            add(section, f"M5 verdict envelope · {name}", _recorded(
                _mapping(verdict).get("conservative_ln"), why,
                " ln p (SPEC §9 verdict envelope; not a calibration precision)"))

    # ------------------------------------------------------------------ F τ_mf
    section = "F · τ_mf"
    tau = record.get("tau_mf")
    declared = _mapping(calibration.get("tau_mf"))
    if tau is None:
        add(section, "τ_mf", "not declared (none inferred)")
    else:
        add(section, "τ_mf", f"{_recorded(tau, 'not recorded')} — acceptance tolerance on |Δ ln f| only")
        if declared:
            add(section, "Recorded role", f"{declared.get('role')}: {declared.get('note')}")
        add(section, "Separation", "never a statistical uncertainty, never part of Σ (Σ_setup + Σ_meas only) and never "
                                   "converted into a parameter uncertainty")

    # ------------------------------------------------------------------ question-specific evidence
    if calibration_question:
        section = "Calibration parameters"
        released = record.get("released_calibration_parameters")
        if status == "RELEASED" and released:
            add(section, "Fitted (released)", f"{_exact(released)} (MODEL_CALIBRATION_PARAMETER)")
        candidate = _mapping(record.get("diagnostic_candidate"))
        if candidate.get("parameters"):
            add(section, "Fitted (diagnostic only, not released)",
                f"{_exact(candidate.get('parameters'))} [{', '.join(candidate.get('labels') or ())}]")
        for name, item in sorted(_mapping(calibration.get("fixed_parameters")).items()):
            item = _mapping(item)
            add(section, f"Fixed · {name}", f"{_recorded(item.get('value'), 'not recorded')} {item.get('unit') or ''}"
                                             f" ({item.get('role')}; {item.get('provenance')}); fixed: no fitted "
                                             "uncertainty")
    else:
        section = "Material identification"
        formal = _mapping(record.get("material_formal_output"))
        add(section, "Formal output", formal.get("status") or _missing("not judged"))
        if status == "MATERIAL_VALUES_RELEASED" and formal.get("released_values"):
            add(section, "Formally released", f"{_exact(formal.get('released_values'))} (effective material-model "
                                              "values)")
        family = record.get("material_family_consistency")
        add(section, "SPEC §13 family consistency", (f"{family} — decisive: no global material property" if family ==
                                                     "FAIL" else family) or _missing("not recorded"))
        if record.get("material_claim"):
            add(section, "Material claim", record.get("material_claim"))
        for name, verdict in sorted(verdicts.items()):
            verdict = _mapping(verdict)
            add(section, f"M5 verdict · {name}", f"{verdict.get('verdict')}"
                + (f" ({'; '.join(verdict.get('reasons'))})" if verdict.get("reasons") else ""))
        candidate = _mapping(record.get("diagnostic_candidate"))
        if candidate.get("parameters"):
            add(section, "Optimizer candidate (diagnostic only, not released)",
                f"{_exact(candidate.get('parameters'))} [{', '.join(candidate.get('labels') or ())}]")

    # ------------------------------------------------------------------ sources / provenance
    section = "Sources / provenance"
    campaign = _mapping(record.get("campaign"))
    evidence = _mapping(record.get("evidence"))
    add(section, "Campaign", f"{campaign.get('campaign_id')} ({campaign.get('run_type')}); campaign hash "
                             f"{campaign.get('campaign_hash')}")
    add(section, "Run hash", campaign.get("run_hash") or _missing("not verified"))
    add(section, "Specimens", ", ".join(str(s) for s in campaign.get("specimens") or ()) or _missing("not recorded"))
    for label, item in sorted(_mapping(evidence.get("solver_profiles")).items()):
        item = _mapping(item)
        add(section, f"Solver profile · {label}", f"{item.get('profile_id')} (hash {item.get('profile_hash')}; declared "
                                                  f"{item.get('abaqus_release')}) — as journalled; not a claim of a "
                                                  "physical Abaqus solve")
    sources = _mapping(evidence.get("fe_sources"))
    for label, values in sorted(sources.items()):
        add(section, f"FE sources · {label}", ", ".join(str(v) for v in values)
            + " (as journalled; an archived-validated-pack is a reused archived pack, never a new solve)")
    if not sources:
        add(section, "FE sources", _missing("not verified (no verified LM history)" if not_ready else "not recorded"))
    lm = _mapping(evidence.get("lm_provenance"))
    if lm:
        add(section, "LM provenance", f"{lm.get('verification')}; LM {lm.get('status')}; final candidate "
                                      f"{lm.get('final_candidate_hash')}")
        for label, value in sorted(_mapping(lm.get("pipeline_run_hashes")).items()):
            add(section, f"Pipeline run · {label}", value)
        jacobian = _mapping(lm.get("jacobian"))
        if jacobian:
            add(section, "Jacobian", f"{jacobian.get('provenance')}; whitened hash {jacobian.get('whitened_hash')}")
    else:
        add(section, "LM provenance", _missing("not verified"))
    identity = _mapping(calibration.get("identity"))
    if calibration.get("gate_record_hash"):
        add(section, "Calibration gate record hash", calibration.get("gate_record_hash"))
    if identity.get("inp_sha256"):
        add(section, "Pinned source INP SHA-256", identity.get("inp_sha256"))
    for name, value in sorted(_mapping(_mapping(report.get("m5_verdict")).get("evidence_hashes")).items()
                              if report else ()):
        add(section, f"M5 evidence hash · {name}", value or _missing("not recorded"))
    add(section, "Production execution", record.get("production_execution"))
    if record.get("production_calibration"):
        add(section, "Physical calibration status", record.get("production_calibration"))
    return tuple(rows)


# ----------------------------------------------------------------------------------------------- view model

def wizard_rows(items: tuple[WizardItem, ...]) -> tuple[tuple[str, str, str, str], ...]:
    """Table rows (section, item, value, status) for the GUI."""
    return tuple((i.section, i.label, i.value, i.status.value) for i in items)


def wizard_summary(preparation) -> str:
    """One human-readable line: what was loaded and how many factual gaps remain."""

    gaps = len(preparation.gaps)
    if isinstance(preparation, FamilyPreparation):
        if preparation.definition is None:
            return f"Campaign definition not loaded: {preparation.items[0].detail}"
        labels = ", ".join(s.label for s in preparation.specimens)
        what = f"Campaign {preparation.definition.campaign_id} ({preparation.definition.run_type}): {labels}"
    else:
        if preparation.passport is None:
            return f"Specimen passport not loaded: {preparation.items[0].detail}"
        p = preparation.passport
        what = f"Specimen {p.design_id} / {p.physical_specimen_id or 'physical id unavailable'} / run {p.test_run_id}"
    unverified = sum(1 for item in _all_items(preparation) if item.status is ItemStatus.PRESENT_SHA256_NOT_VERIFIED)
    text = f"{what}. {gaps} item(s) missing or not available." if gaps else f"{what}. No missing items."
    if unverified:
        text += f" {unverified} pinned file(s) present by size only (SHA-256 not verified)."
    return text + " Factual loading only: not a scientific readiness judgement."


def _all_items(preparation) -> tuple[WizardItem, ...]:
    if isinstance(preparation, FamilyPreparation):
        return preparation.items + tuple(i for s in preparation.specimens for i in s.preparation.items)
    return preparation.items


def preparation_rows(preparation) -> tuple[tuple[str, str, str, str, str], ...]:
    """All rows (section, item, value, status, provenance) of a preparation; every specimen of a family is listed,
    its rows carrying the specimen label in their section."""

    if preparation is None:
        return ()
    rows = [(i.section, i.label, i.value, i.status.value, i.detail) for i in preparation.items]
    if isinstance(preparation, FamilyPreparation):
        for specimen in preparation.specimens:
            rows += [(f"{specimen.label} · {i.section}", i.label, i.value, i.status.value, i.detail)
                     for i in specimen.preparation.items]
    return tuple(rows)
