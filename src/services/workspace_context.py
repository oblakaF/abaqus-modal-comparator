"""APP-WORKSPACE.1: a headless, immutable model of the workspace state of one specimen (no Tkinter).

It is the state a future GUI shows, built from:

- the **accepted** specimen catalogue (``docs/auto_id/specimen_catalog.json``, status ACCEPTED): specimen ID, type,
  family, the catalogue's Auto-ID statuses, its PolyMAX modal sets and its registrations. Nothing of these is taken
  from anywhere else, and nothing is guessed: a missing value is ``UNKNOWN``;
- the session's selections: the FE and experimental source paths, the modal set, the registration in use and the
  state of the analysis result. Paths are recorded as given; no file is opened, hashed or changed;
- the production Auto-ID status, read on every access from the authoritative blocking code
  (``services.guarded_execution.PRODUCTION_AUTHORITY`` and ``services.campaign_execution_plan.NOT_AUTHORISED``);
  the context never stores, sets or relaxes it.

Registrations are kept apart: PHYSICAL (SPEC section 11 physical registration), LEGACY_REPLAY (replay of an archived
historical registration; not SPEC section 11 evidence), INCOMPLETE (no physical reference), NONE (no registration in
use) and UNKNOWN (a registration whose basis is not stated or cannot be established; a hash alone is UNKNOWN even
when the catalogue records it as physical). A kind is never upgraded, and a catalogue record of the same hash is
reference information only: it is never a verification that the registration applies to the selected files.

The model computes no scientific quantity and changes no scientific rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import PureWindowsPath
from typing import Any, Optional

from domain.specimen_manifest import RegistrationBasisStatus
from ui_policy import AnalysisState

from . import specimen_catalog_view as catalog

UNKNOWN = "UNKNOWN"
ACCEPTED = "ACCEPTED"
FE, EXPERIMENTAL = "FE", "EXPERIMENTAL"


class WorkspaceContextError(ValueError):
    """The supplied state contradicts itself (e.g. MAC shown for a diagnostic result)."""


class RegistrationKind(str, Enum):
    PHYSICAL = RegistrationBasisStatus.PHYSICAL.value
    LEGACY_REPLAY = RegistrationBasisStatus.LEGACY_REPLAY.value
    INCOMPLETE = RegistrationBasisStatus.INCOMPLETE.value
    NONE = "NONE"
    UNKNOWN = UNKNOWN


class ModalSetStatus(str, Enum):
    NOT_SELECTED = "NOT_SELECTED"  # no modal set chosen
    GOVERNED = "GOVERNED"  # the catalogue's governed set of this PolyMAX file
    OTHER = "OTHER"  # listed in this file, not its governed set
    NOT_GOVERNED = "NOT_GOVERNED"  # listed in a file without a governed set
    UNASSIGNED = "UNASSIGNED"  # listed, but the catalogue's governed-set text matches no single listed set
    NOT_IN_CATALOGUE = "NOT_IN_CATALOGUE"  # the catalogue lists no such set for this specimen (or this file)
    NOT_CHECKED = "NOT_CHECKED"  # listed for the specimen, but the experimental file is not one catalogue source
    UNKNOWN = UNKNOWN  # the specimen (or the catalogue) is unknown, so nothing can be checked


_SET_STATUS = {catalog.GOVERNED: ModalSetStatus.GOVERNED, catalog.OTHER: ModalSetStatus.OTHER,
               catalog.NOT_GOVERNED: ModalSetStatus.NOT_GOVERNED, catalog.UNASSIGNED: ModalSetStatus.UNASSIGNED}


def _text(value: Any) -> str:
    """A catalogue value as text; a missing or empty value is UNKNOWN (never a default)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return UNKNOWN
    return str(value)


def _file_name(path: Any) -> str:
    return PureWindowsPath(str(path)).name.casefold() if path else ""


# ------------------------------------------------------------------------------------------------ catalogue facts

@dataclass(frozen=True)
class CatalogueRegistration:
    """One registration recorded in the catalogue; its ``status_text`` is the catalogue's words, not interpreted."""

    kind: RegistrationKind  # PHYSICAL ("physical" record) or LEGACY_REPLAY ("legacy" record)
    path: str
    registration_hash: str
    status_text: str


@dataclass(frozen=True)
class CatalogueModalSet:
    source_name: str  # the PolyMAX file name recorded in the catalogue
    name: str
    mode_count: Optional[int]
    status: ModalSetStatus
    status_text: str


@dataclass(frozen=True)
class SpecimenRecord:
    """What the accepted catalogue says about one specimen (identity, family, statuses, sets, registrations)."""

    specimen_id: str
    specimen_type: str
    family_id: str
    catalogue_auto_id_status: tuple[str, ...]
    modal_sets: tuple[CatalogueModalSet, ...]
    registrations: tuple[CatalogueRegistration, ...]
    fe_source_names: tuple[str, ...]


def _modal_sets(entry: dict) -> tuple[CatalogueModalSet, ...]:
    sets = []
    for experiment in entry.get("experiments") or ():
        if not isinstance(experiment, dict) or not isinstance(experiment.get("fitted_sets"), list):
            continue
        source = experiment.get("source") if isinstance(experiment.get("source"), dict) else {}
        source_name = PureWindowsPath(str(source.get("relative_path") or "")).name
        for item in experiment["fitted_sets"]:
            if not isinstance(item, dict) or not isinstance(item.get("set"), str):
                continue
            key, words = catalog.modal_set_status(experiment, item["set"])
            count = item.get("mode_count")
            sets.append(CatalogueModalSet(source_name or UNKNOWN, item["set"],
                                          count if isinstance(count, int) and not isinstance(count, bool) else None,
                                          _SET_STATUS[key], words))
    return tuple(sets)


def _registrations(entry: dict) -> tuple[CatalogueRegistration, ...]:
    record = entry.get("registration") if isinstance(entry.get("registration"), dict) else {}
    found = []
    for key, kind in (("physical", RegistrationKind.PHYSICAL), ("legacy", RegistrationKind.LEGACY_REPLAY)):
        item = record.get(key)
        if isinstance(item, dict) and isinstance(item.get("registration_hash"), str):
            found.append(CatalogueRegistration(kind, _text(item.get("path")), item["registration_hash"],
                                               _text(item.get("status"))))
    return tuple(found)


def _fe_source_names(entry: dict) -> tuple[str, ...]:
    assets = entry.get("fe_assets") if isinstance(entry.get("fe_assets"), dict) else {}
    return tuple(PureWindowsPath(str(item["relative_path"])).name for item in assets.get("store") or ()
                 if isinstance(item, dict) and item.get("relative_path"))


def specimen_record(entry: dict) -> SpecimenRecord:
    statuses = entry.get("auto_id_status")
    return SpecimenRecord(
        specimen_id=str(entry["specimen_id"]),
        specimen_type=_text(entry.get("type")),
        family_id=_text(entry.get("family_id")),
        catalogue_auto_id_status=tuple(str(item) for item in statuses) if isinstance(statuses, list) else (),
        modal_sets=_modal_sets(entry),
        registrations=_registrations(entry),
        fe_source_names=_fe_source_names(entry),
    )


def accepted_catalogue_problem(view: catalog.CatalogueView) -> str:
    """Why the catalogue cannot be used ("" when it is the accepted catalogue)."""
    if view.problem:
        return view.problem
    status = view.header.get("status")
    if status != ACCEPTED:
        return f"the specimen catalogue is not accepted (status {_text(status)})"
    return ""


# ------------------------------------------------------------------------------------------------ session state

@dataclass(frozen=True)
class SourceSelection:
    """A selected FE or experimental source: the path as given, never opened."""

    role: str
    path: Optional[str] = None
    catalogue_name_match: bool = False  # the file name equals a source file name of this specimen in the catalogue

    @property
    def selected(self) -> bool:
        return bool(self.path)

    @property
    def file_name(self) -> str:
        return PureWindowsPath(self.path).name if self.path else UNKNOWN


@dataclass(frozen=True)
class ModalSetState:
    name: Optional[str]
    status: ModalSetStatus
    reason: str
    catalogue_set: Optional[CatalogueModalSet] = None


@dataclass(frozen=True)
class RegistrationState:
    """The registration the session states it uses, with the catalogue record of the same hash for reference.

    ``kind`` is the stated basis only: a hash without a stated basis is UNKNOWN, whatever the catalogue records for
    it. ``catalogue_reference`` is reference information: it says what the catalogue records under that hash for
    this specimen, never that the registration is in use, applies to the selected FE / experimental files or was
    verified against them (that is done only by the comparison's own registration binding)."""

    kind: RegistrationKind
    registration_hash: Optional[str] = None
    catalogue_reference: Optional[CatalogueRegistration] = None
    issues: tuple[str, ...] = ()

    @property
    def stated_physical_hash_recorded_in_catalogue(self) -> bool:
        """A cross-reference only: the stated basis is PHYSICAL and its hash is the catalogue's physical registration
        record of this specimen, with no issue. Not a physical verification of the data and not a statement that the
        registration applies to the selected FE / experimental files."""
        return (self.kind is RegistrationKind.PHYSICAL and self.catalogue_reference is not None
                and self.catalogue_reference.kind is RegistrationKind.PHYSICAL and not self.issues)


@dataclass(frozen=True)
class ResultState:
    """The state of the analysis result; only a successful comparison can carry pairs and MAC."""

    state: AnalysisState = AnalysisState.NO_DATA
    pair_count: Optional[int] = None  # None: not known
    mac_shown: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.state, AnalysisState):
            raise WorkspaceContextError(f"result state must be an AnalysisState, not {self.state!r}")
        if self.pair_count is not None and (isinstance(self.pair_count, bool) or not isinstance(self.pair_count, int)
                                            or self.pair_count < 0):
            raise WorkspaceContextError(f"pair count must be a non-negative integer or None, not {self.pair_count!r}")
        if self.state is not AnalysisState.SUCCESS and (self.mac_shown or (self.pair_count or 0) > 0):
            raise WorkspaceContextError(f"a {self.state.value} result has no mode pairs and no MAC")


@dataclass(frozen=True)
class ProductionAutoIdStatus:
    status: str
    blocked: bool
    reason: str


def production_auto_id_status() -> ProductionAutoIdStatus:
    """The production Auto-ID status, read from the authoritative blocking code; never set by this module."""
    from services.campaign_execution_plan import NOT_AUTHORISED, STATEMENT
    from services.guarded_execution import PRODUCTION_AUTHORITY

    reason = STATEMENT if PRODUCTION_AUTHORITY.available else PRODUCTION_AUTHORITY.unavailable_reason
    return ProductionAutoIdStatus(NOT_AUTHORISED, True, str(reason))


# ------------------------------------------------------------------------------------------------ the context

@dataclass(frozen=True)
class WorkspaceContext:
    requested_specimen_id: Optional[str]
    catalogue_problem: str  # "" when the accepted catalogue was read
    specimen: Optional[SpecimenRecord]  # None: unknown specimen (or no accepted catalogue)
    fe_source: SourceSelection
    experimental_source: SourceSelection
    modal_set: ModalSetState
    registration: RegistrationState
    result: ResultState

    @property
    def specimen_known(self) -> bool:
        return self.specimen is not None

    @property
    def specimen_id(self) -> str:
        return self.specimen.specimen_id if self.specimen else UNKNOWN

    @property
    def specimen_type(self) -> str:
        return self.specimen.specimen_type if self.specimen else UNKNOWN

    @property
    def family_id(self) -> str:
        return self.specimen.family_id if self.specimen else UNKNOWN

    @property
    def catalogue_auto_id_status(self) -> tuple[str, ...]:
        return self.specimen.catalogue_auto_id_status if self.specimen else ()

    @property
    def production_auto_id(self) -> ProductionAutoIdStatus:
        return production_auto_id_status()

    @property
    def missing(self) -> tuple[str, ...]:
        """What is still missing for a complete workspace, in a fixed order."""
        items = []
        if not self.specimen_known:
            items.append("specimen")
        if not self.fe_source.selected:
            items.append("FE source")
        if not self.experimental_source.selected:
            items.append("experimental source")
        if self.modal_set.status is ModalSetStatus.NOT_SELECTED:
            items.append("modal set")
        if self.registration.kind is RegistrationKind.NONE:
            items.append("registration")
        return tuple(items)


def _registration_state(record: Optional[SpecimenRecord], basis: Optional[RegistrationBasisStatus],
                        registration_hash: Optional[str]) -> RegistrationState:
    if basis is not None and not isinstance(basis, RegistrationBasisStatus):
        raise WorkspaceContextError(f"registration basis must be a RegistrationBasisStatus, not {basis!r}")
    if registration_hash is not None and (not isinstance(registration_hash, str) or not registration_hash.strip()):
        raise WorkspaceContextError("registration hash must be a non-empty string or None")
    reference = None
    if record is not None and registration_hash:
        reference = next((item for item in record.registrations if item.registration_hash == registration_hash), None)
    if basis is None and not registration_hash:
        return RegistrationState(RegistrationKind.NONE)
    issues = []
    if registration_hash and reference is None:
        issues.append("the registration is not recorded in the catalogue for this specimen")
    if basis is None:  # a hash alone never establishes the registration in use, not even a catalogue PHYSICAL one
        issues.insert(0, "no registration basis is stated: the registration in use is UNKNOWN"
                         + (f" (the catalogue records this hash as {reference.kind.value}; reference only)"
                            if reference is not None else ""))
        return RegistrationState(RegistrationKind.UNKNOWN, registration_hash, reference, tuple(issues))
    kind = RegistrationKind(basis.value)
    if reference is not None and reference.kind is not kind:
        issues.append(f"the catalogue records this registration as {reference.kind.value}, not {kind.value}")
    if kind is RegistrationKind.PHYSICAL and not registration_hash:
        issues.append("a PHYSICAL registration without a registration hash cannot be matched to the catalogue")
    return RegistrationState(kind, registration_hash, reference, tuple(issues))


def _modal_set_state(record: Optional[SpecimenRecord], name: Optional[str],
                     experimental: SourceSelection) -> ModalSetState:
    if name is not None and (not isinstance(name, str) or not name.strip()):
        name = None
    if name is None:
        return ModalSetState(None, ModalSetStatus.NOT_SELECTED, "no modal set is selected")
    if record is None:
        return ModalSetState(name, ModalSetStatus.UNKNOWN, "the specimen is unknown, so the modal set is not checked")
    file_name = _file_name(experimental.path)
    in_file = [item for item in record.modal_sets if file_name and item.source_name.casefold() == file_name]
    if in_file:
        found = [item for item in in_file if item.name == name]
        if len(found) == 1:
            return ModalSetState(name, found[0].status, found[0].status_text, found[0])
        if not found:
            return ModalSetState(name, ModalSetStatus.NOT_IN_CATALOGUE,
                                 f"the catalogue lists no set \"{name}\" in {in_file[0].source_name}")
        return ModalSetState(name, ModalSetStatus.NOT_CHECKED,
                             f"the catalogue lists \"{name}\" more than once in {in_file[0].source_name}")
    if not any(item.name == name for item in record.modal_sets):
        return ModalSetState(name, ModalSetStatus.NOT_IN_CATALOGUE,
                             f"the catalogue lists no set \"{name}\" for {record.specimen_id}")
    return ModalSetState(name, ModalSetStatus.NOT_CHECKED,
                         "the set is listed for this specimen, but the experimental file is not one of its catalogue "
                         "PolyMAX files, so its status is not assigned")


def build_workspace_context(
    specimen_id: Optional[str],
    *,
    fe_path: Optional[str] = None,
    experimental_path: Optional[str] = None,
    modal_set: Optional[str] = None,
    registration_basis: Optional[RegistrationBasisStatus] = None,
    registration_hash: Optional[str] = None,
    result: Optional[ResultState] = None,
    catalogue_view: Optional[catalog.CatalogueView] = None,
) -> WorkspaceContext:
    """The workspace context of one specimen; missing or unknown values are represented, never invented."""
    view = catalogue_view if catalogue_view is not None else catalog.load_catalogue()
    problem = accepted_catalogue_problem(view)
    requested = specimen_id.strip() if isinstance(specimen_id, str) and specimen_id.strip() else None
    entry = view.entry(requested) if requested and not problem else None
    record = specimen_record(entry) if entry is not None else None
    experimental_names = {item.source_name.casefold() for item in record.modal_sets} if record else set()
    fe_names = {name.casefold() for name in record.fe_source_names} if record else set()
    fe = SourceSelection(FE, str(fe_path) if fe_path else None, bool(fe_path) and _file_name(fe_path) in fe_names)
    experimental = SourceSelection(EXPERIMENTAL, str(experimental_path) if experimental_path else None,
                                   bool(experimental_path) and _file_name(experimental_path) in experimental_names)
    if result is not None and not isinstance(result, ResultState):
        raise WorkspaceContextError(f"result must be a ResultState, not {result!r}")
    return WorkspaceContext(
        requested_specimen_id=requested,
        catalogue_problem=problem,
        specimen=record,
        fe_source=fe,
        experimental_source=experimental,
        modal_set=_modal_set_state(record, modal_set, experimental),
        registration=_registration_state(record, registration_basis, registration_hash),
        result=result if result is not None else ResultState(),
    )


__all__ = ["ACCEPTED", "CatalogueModalSet", "CatalogueRegistration", "ModalSetState", "ModalSetStatus",
           "ProductionAutoIdStatus", "RegistrationKind", "RegistrationState", "ResultState", "SourceSelection",
           "SpecimenRecord", "UNKNOWN", "WorkspaceContext", "WorkspaceContextError", "accepted_catalogue_problem",
           "build_workspace_context", "production_auto_id_status", "specimen_record"]
