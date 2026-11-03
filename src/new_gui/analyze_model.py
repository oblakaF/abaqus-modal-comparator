"""UNIVERSAL-UI-1: the steps of the primary workflow (two files, one Analyze button), with no Qt.

Any Abaqus ``.odb`` and any experimental ``.unv`` / ``.uff``. Every step calls an existing service and computes nothing
itself: ``odb_import_service`` (extraction, only after the user's consent), ``preview_model`` (reading),
``diagnostic_model`` (the frequency-only diagnostic and the comparator's shape-based rigid-body criterion),
``registration_check_model`` (whether a verified physical registration applies) and ``comparison_model`` (pairs and MAC,
only with such a registration). Without one, the status is REGISTRATION_REQUIRED: frequencies only, no pair and no MAC.

The extraction package is managed here: it lives in ``<odb folder>/<odb name>_modal_packages`` and is found again by the
ODB's content (SHA-256) and the requested range, so the user never chooses a ``manifest.json``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Optional

from new_gui import comparison_model as cm
from new_gui import diagnostic_model as dm
from new_gui import preview_model as pm
from new_gui import registration_check_model as rm
from new_gui.workspace_state import EXPERIMENTAL, FE
from services import odb_import_service as svc

FIRST_MODE, LAST_MODE = 1, 20  # the first 20 modes; never fewer at the low end, so EXP1 and the first elastic FE stay
MODE_LIMIT = LAST_MODE - FIRST_MODE + 1
FE_SUFFIXES = (".odb",)
EXPERIMENTAL_SUFFIXES = (".unv", ".uff")
SUFFIXES = {FE: FE_SUFFIXES, EXPERIMENTAL: EXPERIMENTAL_SUFFIXES}
FILTERS = {FE: "Abaqus ODB (*.odb);;All files (*)", EXPERIMENTAL: "Experimental modal data (*.unv *.uff);;All files (*)"}
REGISTRATION_REQUIRED = "REGISTRATION_REQUIRED"
REGISTRATION_TEXT = ("No independently verified physical registration applies to these files, so there are no FE-EXP "
                     "mode pairs and no MAC. The frequencies below are a frequency-only diagnostic.")
VERIFIED_TEXT = "A verified physical registration applies to these files. Pairs and MAC are the comparator's result."
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


@dataclass(frozen=True)
class Inputs:
    fe: Any
    experimental: Any
    identities: dict


def read_inputs(manifest, experimental_path, cancel_event) -> Inputs:
    fe, fe_identity = _read(FE, manifest, cancel_event)
    experimental, experimental_identity = _read(EXPERIMENTAL, experimental_path, cancel_event)
    if not experimental.sets:
        raise StepFailed(f"{Path(experimental_path).name} holds no modal data.")
    return Inputs(fe, experimental, {"fe": fe_identity, "experimental": experimental_identity})


def first_modes(experimental, set_index: int):
    """The preview limited to the lowest 20 mode numbers of the chosen set, for the frequency tables. Nothing below
    them is left out, so EXP1 always stays; the registration and the comparator use the whole set they were sealed on."""
    chosen = experimental.sets[set_index]
    if len(chosen.records) <= MODE_LIMIT:
        return experimental
    kept = set(sorted(record.number for record in chosen.records)[:MODE_LIMIT])
    limited = replace(chosen, records=tuple(r for r in chosen.records if r.number in kept),
                      dataset=replace(chosen.dataset, modes=[m for m in chosen.dataset.modes if int(m.number) in kept]))
    return replace(experimental, sets=experimental.sets[:set_index] + (limited,) + experimental.sets[set_index + 1:])


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
    registration_reason: str = ""  # why the status is REGISTRATION_REQUIRED (a tooltip, never a pair or a MAC)


NEAREST_HEADERS = ("EXP record", "EXP mode", "EXP (Hz)", "Nearest FE mode", "FE (Hz)", "Error (%)", "Next FE mode",
                   "Next FE (Hz)", "Next error (%)", "Note")
FE_HEADERS = ("FE mode", "Frequency (Hz)", "Type (by shape)")
EXPERIMENTAL_HEADERS = ("EXP record", "EXP mode", "Frequency (Hz)", "Classification")
PAIR_COLUMNS = (0, 1, 2, 3, 4, 5, 6, 7)  # of comparison_model.PAIR_HEADERS: modes, frequencies, error, MAC, status
PAIR_HEADERS = tuple(cm.PAIR_HEADERS[i] for i in PAIR_COLUMNS)


def _verified(inputs: Inputs, set_index: int, cancel_event) -> tuple:
    """(comparison view or None, why not): a pair or a MAC exists only through both checks of the existing services."""
    if rm.set_is_provisional(inputs.experimental, set_index):
        return None, cm.PROVISIONAL_BLOCK
    check = rm.run_check(inputs.fe, inputs.experimental, set_index, 0, cancel_event)
    if check.cancelled:
        raise StepCancelled()
    if check.view is None:
        return None, check.refusal or check.error
    compared = cm.run_compare(inputs.fe, inputs.experimental, set_index, check.view.registration, 0, cancel_event,
                              inputs.identities)
    if compared.cancelled:
        raise StepCancelled()
    if compared.view is None:
        return None, compared.refusal or compared.error
    return compared.view, ""


def analyse(inputs: Inputs, set_index: int, cancel_event) -> Analysis:
    limited = first_modes(inputs.experimental, set_index)
    outcome = dm.run_diagnostic(inputs.fe, limited, set_index, 0, cancel_event)
    if outcome.cancelled:
        raise StepCancelled()
    if outcome.error:
        raise StepFailed(outcome.error)
    comparison, reason = _verified(inputs, set_index, cancel_event)
    view = outcome.view
    full = inputs.experimental.sets[set_index]
    position = {}
    for index, record in enumerate(full.records):
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
    facts = [f"FE: requested modes {FIRST_MODE}-{LAST_MODE}, loaded "
             + (f"{len(numbers)} ({min(numbers)}-{max(numbers)})" if numbers else "none")
             + f"; rigid-body by shape: {', '.join(str(n) for n in sorted(rigid)) or 'none'}; "
             + f"first elastic: {first_elastic or 'none'}",
             f"EXP: {view.set_title}; {len(limited.sets[set_index].records)} of {len(full.records)} record(s) analysed"]
    notes = tuple(inputs.fe.warnings) + tuple(view.range_warnings) + tuple(view.importer_warnings)
    if comparison is not None:
        status, statement = comparison.status, VERIFIED_TEXT
        notes += tuple(comparison.warnings)
    else:
        status, statement = REGISTRATION_REQUIRED, REGISTRATION_TEXT
    return Analysis(status, statement, set_index, view.set_title, fe_rows, experimental, nearest, first_elastic,
                    tuple(sorted(rigid)), tuple(facts), notes, comparison, reason)


__all__ = ["Analysis", "Inputs", "REGISTRATION_REQUIRED", "StepCancelled", "StepFailed", "analyse", "consent_text",
           "extract", "file_problem", "find_package", "first_modes", "make_plan", "package_folder", "plan_warnings",
           "read_inputs"]
