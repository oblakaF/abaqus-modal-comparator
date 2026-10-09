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
                        evaluated_run_hash: Optional[str] = None) -> ReadinessSelection:
    """Bind a stored backend readiness record to the current selection, by governed identity only.

    A record is presented for a selected family / campaign only when its campaign identity is the governed
    ``CampaignDefinition``'s: the exact campaign hash, the same run type, the same specimen labels in definition order,
    the same declared scientific question and τ_mf (both undeclared for a v1 definition), and the same run hash when a
    run is selected.  Names, folders, labels or file names alone never match.  ``evaluated_run_hash`` is given only for
    the record the GUI itself obtained by evaluating that run (M8.3): a backend refusal that came before the run identity
    could be verified carries no run hash and is then bound to the run that was evaluated; such a record is shown only
    while exactly that run is selected.  A specimen folder declares no governed
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
