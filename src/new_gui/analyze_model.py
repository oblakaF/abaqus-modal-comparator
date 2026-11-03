"""UNIVERSAL-UI-1: the steps of the primary workflow (two files, one Analyze button), with no Qt.

Any Abaqus ``.odb`` and any experimental ``.unv`` / ``.uff``. Every step calls an existing service and computes nothing
itself: ``odb_import_service`` (extraction, only after the user's consent), ``preview_model`` (reading),
``diagnostic_model`` (the frequency-only diagnostic and the comparator's shape-based rigid-body criterion),
``registration_check_model`` (whether a verified physical registration applies) and ``comparison_model`` (pairs and MAC,
only with such a registration). Without one, the status is REGISTRATION_REQUIRED: frequencies only, no pair and no MAC.

UNIVERSAL-UI-3: one mode scope for every result: FE modes 1-20 and the first 20 records of each experimental set. The
source identities and the registration are verified on the full read data; the diagnostic, the comparator, the tables,
the counts and the shape choices then use read-only subsets, so a mode outside the scope influences nothing shown.

UNIVERSAL-REG-1: ``propose_registration`` checks stated physical evidence on the read files, once they are confirmed
unchanged. Its proposal is diagnostic: it never reaches ``analyse``, so the status, the pairs and the MAC do not change.

The extraction package is managed here: it lives in ``<odb folder>/<odb name>_modal_packages`` and is found again by the
ODB's content (SHA-256) and the requested range, so the user never chooses a ``manifest.json``.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Optional

from new_gui import comparison_model as cm
from new_gui import diagnostic_model as dm
from new_gui import preview_model as pm
from new_gui import registration_check_model as rm
from new_gui.workspace_state import EXPERIMENTAL, FE
from services import generic_registration as gr
from services import odb_import_service as svc

FIRST_MODE, LAST_MODE = 1, 20  # the first 20 modes; never fewer at the low end, so EXP1 and the first elastic FE stay
MODE_LIMIT = LAST_MODE - FIRST_MODE + 1
FE_SUFFIXES = (".odb",)
EXPERIMENTAL_SUFFIXES = (".unv", ".uff")
SUFFIXES = {FE: FE_SUFFIXES, EXPERIMENTAL: EXPERIMENTAL_SUFFIXES}
FILTERS = {FE: "Abaqus ODB (*.odb);;All files (*)", EXPERIMENTAL: "Experimental modal data (*.unv *.uff);;All files (*)"}
REGISTRATION_REQUIRED = "REGISTRATION_REQUIRED"
REGISTRATION_TEXT = "No verified physical registration: no mode pairs and no MAC. Frequency comparison only."
VERIFIED_TEXT = "A verified physical registration applies to these files. Pairs and MAC are the comparator's result."
REFUSED, FAILED, PROVISIONAL = "refused", "failed", "provisional"
REGISTRATION_NOTES = {  # what the program shows; the service's own wording stays in ``registration_reason``
    REFUSED: "Registration check: no accepted registration matches these two files.",
    FAILED: "Registration check FAILED: it could not be completed, so nothing about these files is verified.",
    PROVISIONAL: "Registration not checked: the chosen set holds FRF peak records, not validated fitted modes.",
}
VERIFIED_LIMITS = ("Only the registered geometric mapping is reused: frequencies and mode shapes are these files' own. "
                   "No acceptance gate or threshold is changed.")
_REUSE_WARNING = "Physical registration reused"  # names the archived source; VERIFIED_LIMITS states its limits
STALE_TEXT = "A file changed after it was read, so nothing was analyzed. Click Analyze to read both files again."
RIGID_NOTE = "Rigid-body FE modes are identified by their shape (rigid-body projection), not by their frequency."
CONSENT_TITLE = "Start Abaqus Python?"
_SPACE_WARNING = "These paths contain a space"  # abaqus_bridge passes such paths whole since RC6-F1


class StepFailed(ValueError):
    """A step ended with a message for the user."""


class StepCancelled(RuntimeError):
    """The user cancelled, or the input was replaced."""


def file_problem(kind: str, path) -> str:
    """Why this file is not accepted for ``kind`` (empty when it is); the other side's files stay untouched."""
    candidate = Path(path)
    if candidate.suffix.lower() not in SUFFIXES[kind]:
        wanted = " or ".join(SUFFIXES[kind])
        return f"{candidate.name} is not a {wanted} file."
    if not candidate.is_file():
        return f"The file was not found: {candidate}"
    return ""


def package_folder(odb) -> Path:
    odb = Path(odb)
    return odb.parent / f"{odb.stem}_modal_packages"


def make_plan(odb, launcher: str = "", folder=None, discover=None) -> svc.ExtractionPlan:
    """The extraction of the first 20 modes, checked without starting anything. Raises ``StepFailed``."""
    try:
        return svc.plan_extraction(odb, folder or package_folder(odb), FIRST_MODE, LAST_MODE, launcher,
                                   discover=discover)
    except (svc.OdbImportRefused, OSError) as error:
        raise StepFailed(str(error)) from error


def plan_warnings(plan: svc.ExtractionPlan) -> tuple:
    return tuple(text for text in plan.warnings if not text.startswith(_SPACE_WARNING))


def consent_text(plan: svc.ExtractionPlan) -> str:
    return (f"Abaqus Python will read {plan.odb.path.name} read-only and extract modes {plan.start_mode}-"
            f"{plan.end_mode} into {plan.results_folder}.\n\nLauncher: {plan.abaqus.command}\n\nNo analysis is solved "
            "and the ODB is not changed. Start it?")


def find_package(plan: svc.ExtractionPlan, cancel_event=None, progress=None) -> Optional[Path]:
    """The manifest of a complete package of this ODB's content and range, or None. Hashes the ODB; starts nothing."""
    try:
        identity = svc.hash_file(plan.odb.path, cancel_event, progress)
        found = svc.existing_packages(plan.results_folder, identity["sha256"], plan.start_mode, plan.end_mode)
    except svc.OdbImportCancelled as error:
        raise StepCancelled() from error
    except (svc.OdbImportRefused, OSError) as error:
        raise StepFailed(f"The ODB could not be read: {error}") from error
    return found[0] / "manifest.json" if found else None


def extract(plan: svc.ExtractionPlan, cancel_event, progress=None, runner: Optional[Callable] = None) -> Path:
    """Run the extraction; call this only after the user's consent. Returns the package's manifest."""
    try:
        return Path(svc.run_extraction(plan, confirmed=True, cancel_event=cancel_event, progress=progress,
                                       runner=runner).manifest_path)
    except svc.OdbImportCancelled as error:
        raise StepCancelled() from error
    except (svc.OdbImportRefused, OSError) as error:
        raise StepFailed(str(error)) from error


def _read(kind: str, path, cancel_event):
    outcome = pm.run_read(kind, path, 0, cancel_event)
    if outcome.cancelled or cancel_event.is_set():
        raise StepCancelled()
    if outcome.error:
        raise StepFailed(outcome.error)
    return outcome.preview, outcome.identity


def _read_only(mode):
    """A copy of one mode whose arrays and metadata cannot be written; the read mode is not touched."""
    frozen = copy.copy(mode)
    for name, value in vars(mode).items():
        if hasattr(value, "flags") and hasattr(value, "view"):  # an array
            view = value.view()
            view.flags.writeable = False
            setattr(frozen, name, view)
    frozen.metadata = MappingProxyType(copy.deepcopy(dict(mode.metadata or {})))
    return frozen


def _read_only_dataset(dataset, modes):
    frozen = copy.copy(dataset)
    frozen.modes = tuple(_read_only(mode) for mode in modes)
    frozen.metadata = copy.deepcopy(dict(dataset.metadata or {}))  # its own dict: a service caches residuals here
    frozen.history = tuple(copy.deepcopy(list(dataset.history or ())))
    return frozen


def scoped_fe(fe):
    """The FE preview limited to the requested mode numbers; a lower or higher mode never replaces a missing one."""
    def inside(number) -> bool:
        return FIRST_MODE <= int(number) <= LAST_MODE

    return replace(fe, modes=tuple(mode for mode in fe.modes if inside(mode.number)),
                   dataset=_read_only_dataset(fe.dataset, [m for m in fe.dataset.modes if inside(m.number)]))


def scoped_experimental(experimental):
    """Each modal set limited to its first 20 records in file order (EXP1 to EXP20)."""
    sets = tuple(replace(item, records=tuple(item.records[:MODE_LIMIT]),
                         dataset=_read_only_dataset(item.dataset, list(item.dataset.modes)[:MODE_LIMIT]))
                 for item in experimental.sets)
    return replace(experimental, sets=sets)


@dataclass(frozen=True)
class Inputs:
    """``fe`` and ``experimental`` are the mode scope, used for every result; ``full_*`` are the data as read, used only
    to verify the source identities and the registration."""

    fe: Any
    experimental: Any
    identities: dict
    full_fe: Any
    full_experimental: Any


def scoped_inputs(fe, experimental, identities: dict) -> Inputs:
    if not any(FIRST_MODE <= int(mode.number) <= LAST_MODE for mode in fe.modes):
        raise StepFailed(f"The FE results hold none of the requested modes {FIRST_MODE}-{LAST_MODE}.")
    return Inputs(scoped_fe(fe), scoped_experimental(experimental), identities, fe, experimental)


def read_inputs(manifest, experimental_path, cancel_event) -> Inputs:
    fe, fe_identity = _read(FE, manifest, cancel_event)
    experimental, experimental_identity = _read(EXPERIMENTAL, experimental_path, cancel_event)
    if not experimental.sets:
        raise StepFailed(f"{Path(experimental_path).name} holds no modal data.")
    return scoped_inputs(fe, experimental, {"fe": fe_identity, "experimental": experimental_identity})


def confirm_sources(inputs: Inputs, cancel_event) -> None:
    """Both files are still the files that were read (a modal set may be chosen long after the read)."""
    now = pm.file_identity(inputs.full_experimental.source_path, cancel_event)
    if cancel_event.is_set():
        raise StepCancelled()
    if now is None or inputs.identities.get("experimental") is None:
        raise StepFailed(STALE_TEXT)
    try:
        cm.check_sources(inputs.full_fe, inputs.identities, now, cancel_event)
    except cm.ComparisonCancelled as error:
        raise StepCancelled() from error
    except cm.ComparisonRefused as error:
        raise StepFailed(STALE_TEXT) from error


def registration_geometry(inputs: Inputs, set_index: int) -> tuple:
    return gr.geometry_summary(inputs.full_fe.dataset, inputs.full_experimental.sets[set_index].dataset)


def propose_registration(inputs: Inputs, set_index: int, evidence: gr.Evidence, cancel_event) -> gr.Proposal:
    """The evidence checked on the read data, or REGISTRATION_REQUIRED when a file changed since it was read."""
    try:
        confirm_sources(inputs, cancel_event)
    except StepFailed as error:
        return gr.required([gr.Problem(gr.STALE, str(error))], evidence=evidence)
    proposal = gr.propose(inputs.full_fe.dataset, inputs.full_experimental.sets[set_index].dataset, evidence)
    if cancel_event.is_set():
        raise StepCancelled()
    return proposal


def _ranges(numbers) -> str:
    """1, 2, 13-20"""
    parts, numbers = [], sorted(numbers)
    while numbers:
        first = last = numbers.pop(0)
        while numbers and numbers[0] == last + 1:
            last = numbers.pop(0)
        parts.append(str(first) if first == last else f"{first}-{last}")
    return ", ".join(parts)


@dataclass(frozen=True)
class Analysis:
    status: str
    statement: str
    set_index: int
    set_title: str
    fe_rows: tuple  # (mode, Hz, "rigid-body" | "elastic")
    experimental_rows: tuple  # (EXP record, mode, Hz, classification)
    nearest_rows: tuple  # (EXP record, EXP mode, EXP Hz, FE mode, FE Hz, error %, next FE, next Hz, next error %, note)
    first_elastic: Optional[str]
    rigid_modes: tuple
    facts: tuple
    notes: tuple
    comparison: Any = None  # comparison_model.ComparisonView, only with a verified registration
    registration_reason: str = ""  # the service's own reason for REGISTRATION_REQUIRED (never a pair or a MAC)
    registration_outcome: str = ""  # REFUSED, FAILED or PROVISIONAL; empty with a verified registration
    unavailable_fe: tuple = ()  # requested FE mode numbers the results do not hold
    experimental_total: int = 0  # records of the chosen set as read

    @property
    def registration_note(self) -> str:
        return REGISTRATION_NOTES.get(self.registration_outcome, "")

    @property
    def summary(self) -> str:
        rigid = f"{len(self.rigid_modes)} rigid-body, first elastic {self.first_elastic or 'none'}"
        missing = f" Unavailable: {_ranges(self.unavailable_fe)}." if self.unavailable_fe else ""
        return (f"FE: {len(self.fe_rows)} of {MODE_LIMIT} requested modes ({rigid}).{missing} Experimental: "
                f"{len(self.experimental_rows)} of {self.experimental_total} records analyzed.")


NEAREST_HEADERS = ("EXP record", "EXP mode", "EXP (Hz)", "Nearest FE mode", "FE (Hz)", "Error (%)", "Next FE mode",
                   "Next FE (Hz)", "Next error (%)", "Note")
FE_HEADERS = ("FE mode", "Frequency (Hz)", "Type (by shape)")
EXPERIMENTAL_HEADERS = ("EXP record", "EXP mode", "Frequency (Hz)", "Classification")
PAIR_COLUMNS = (0, 1, 2, 3, 4, 5, 6, 7)  # of comparison_model.PAIR_HEADERS: modes, frequencies, error, MAC, status
PAIR_HEADERS = tuple(cm.PAIR_HEADERS[i] for i in PAIR_COLUMNS)


def _verified(inputs: Inputs, set_index: int, cancel_event) -> tuple:
    """(comparison view or None, why not, outcome): a pair or a MAC exists only through both checks of the services."""
    if rm.set_is_provisional(inputs.full_experimental, set_index):
        return None, cm.PROVISIONAL_BLOCK, PROVISIONAL
    check = rm.run_check(inputs.full_fe, inputs.full_experimental, set_index, 0, cancel_event)
    if check.cancelled:
        raise StepCancelled()
    if check.view is None:
        return None, check.refusal or check.error, REFUSED if check.refusal else FAILED
    compared = cm.run_compare(inputs.full_fe, inputs.full_experimental, set_index, check.view.registration, 0,
                              cancel_event, inputs.identities, scope=(inputs.fe, inputs.experimental))
    if compared.cancelled:
        raise StepCancelled()
    if compared.view is None:
        return None, compared.refusal or compared.error, REFUSED if compared.refusal else FAILED
    return compared.view, "", ""


def analyse(inputs: Inputs, set_index: int, cancel_event) -> Analysis:
    confirm_sources(inputs, cancel_event)
    outcome = dm.run_diagnostic(inputs.fe, inputs.experimental, set_index, 0, cancel_event)
    if outcome.cancelled:
        raise StepCancelled()
    if outcome.error:
        raise StepFailed(outcome.error)
    comparison, reason, registration = _verified(inputs, set_index, cancel_event)
    view = outcome.view
    analyzed = inputs.experimental.sets[set_index]
    total = len(inputs.full_experimental.sets[set_index].records)
    position = {}
    for index, record in enumerate(analyzed.records):
        position.setdefault(record.number, index + 1)
    nearest = tuple((f"EXP{position[int(row[1])]}",) + tuple(row[1:9]) + (row[11],) for row in view.nearest_rows)
    experimental = tuple((f"EXP{position[int(row[1])]}",) + tuple(row[1:]) for row in view.experimental_rows)
    diagnostic = outcome.diagnostic
    rigid = {int(mode) for mode, _f, _r in diagnostic.rigid_fe_modes}
    every = sorted([(int(n), f, "elastic") for n, f in diagnostic.fe_modes]
                   + [(int(n), f, "rigid-body") for n, f, _r in diagnostic.rigid_fe_modes])
    fe_rows = tuple((str(n), f"{f:.4f}", kind) for n, f, kind in every)
    numbers = [row[0] for row in every]
    first_elastic = next((str(n) for n, _f, kind in every if kind == "elastic"), None)
    unavailable = tuple(n for n in range(FIRST_MODE, LAST_MODE + 1) if n not in numbers)
    outside = [int(m.number) for m in inputs.full_fe.modes if not FIRST_MODE <= int(m.number) <= LAST_MODE]
    facts = [f"FE: requested modes {FIRST_MODE}-{LAST_MODE}, loaded "
             + (f"{len(numbers)} ({min(numbers)}-{max(numbers)})" if numbers else "none")
             + f"; rigid-body by shape: {', '.join(str(n) for n in sorted(rigid)) or 'none'}; "
             + f"first elastic: {first_elastic or 'none'}",
             f"EXP: {view.set_title}; {len(analyzed.records)} of {total} record(s) analyzed"]
    if outside:
        facts.append(f"FE modes outside the requested range, not analyzed: {_ranges(outside)}.")
    if total > len(analyzed.records):
        facts.append(f"Experimental records after EXP{len(analyzed.records)}, not analyzed: {total - len(analyzed.records)}.")
    notes = tuple(inputs.fe.warnings) + tuple(view.range_warnings) + tuple(view.importer_warnings)
    if unavailable:
        notes += (f"Requested FE modes not available in the results: {_ranges(unavailable)}.",)
    if comparison is not None:
        status, statement = comparison.status, VERIFIED_TEXT
        notes += tuple(w for w in comparison.warnings if not w.startswith(_REUSE_WARNING)) + (VERIFIED_LIMITS,)
    else:
        status, statement = REGISTRATION_REQUIRED, REGISTRATION_TEXT
    return Analysis(status, statement, set_index, view.set_title, fe_rows, experimental, nearest, first_elastic,
                    tuple(sorted(rigid)), tuple(facts), notes, comparison, reason, registration, unavailable, total)


__all__ = ["Analysis", "Inputs", "REGISTRATION_REQUIRED", "StepCancelled", "StepFailed", "analyse", "consent_text",
           "confirm_sources", "extract", "propose_registration", "registration_geometry", "file_problem", "find_package", "make_plan", "package_folder", "plan_warnings",
           "read_inputs", "scoped_experimental", "scoped_fe", "scoped_inputs"]
