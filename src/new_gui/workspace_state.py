"""NEW-GUI.1: the state of the new interface's workspace, with no Qt (testable headless).

The workspace is the user's own selection: one FE results file, one experimental file and an optional free-text
specimen label. It starts empty: no file, no specimen, no project, no registration, no preset.

- **A file choice is checked, not imported.** A chosen path is checked with the existing read-only contract
  ``services.local_input_registry.check_file`` (it exists and has a supported type; for an LMS project, a companion
  UNV / UFF lies beside it). Nothing is added to the input file registry, and the file content is not read, so a
  valid choice reads "File chosen; content not checked", never "ready for analysis".
- **A refused choice changes nothing.** A missing or unsupported file leaves the previous choice as it was and gives
  the reason. A cancelled dialog changes nothing.
- **The label is only a label.** It is never looked up in the research archive: typing "SP-02" gives no archive
  record, modal-set status or registration.
- **Nothing is computed.** No analysis is run here: no frequency, MAC or mode pair exists. (NEW-GUI.4: the
  frequency diagnostic is run only by its own command on the Analysis page, by ``new_gui.diagnostic_model``.)
- **The research archive is separate.** It is read only on request, through ``services.specimen_catalog_view``. A
  missing or damaged archive gives a problem text, never an error that stops the program. Reading it changes no
  workspace value.
- **The scientific status is read, never set.** Production Auto-ID comes from the authoritative blocking code
  (``services.workspace_context.production_auto_id_status``). The M8 gate and the D-077 formal output are read from
  ``docs/auto_id/STATUS.json``; an unreadable record shows ``UNKNOWN``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
from typing import Optional

from services import local_input_registry as registry
from services import specimen_catalog_view as catalog

FE, EXPERIMENTAL = registry.FE, registry.EXPERIMENTAL
KINDS = (FE, EXPERIMENTAL)
KIND_TITLE = {FE: "FE results", EXPERIMENTAL: "Experimental data"}
DIALOG_FILTERS = {
    FE: "Abaqus results (*.odb manifest.json);;Abaqus ODB (*.odb);;Extracted manifest (manifest.json);;All files (*)",
    EXPERIMENTAL: ("Universal files (*.unv *.uff);;Simcenter Testlab project (*.lms);;"
                   "All files (*)"),
}
KIND_HELP = {
    FE: "An Abaqus .odb, or a manifest.json extracted from one.",
    EXPERIMENTAL: "A Simcenter Testlab .unv / .uff, or an .lms project with its exported .unv / .uff beside it.",
}

NOT_CHOSEN = "Not chosen"
CHOSEN_NOT_CHECKED = "File chosen; content not checked"
CHOSEN_NOTE = ("Only the file's existence and type were checked. Its content is read only when you click Inspect "
               "file, and choosing it is not a statement that the data are ready for analysis.")
ANALYSIS_NOT_RUN = "Analysis not run"
ANALYSIS_NOTE = ("No frequency, MAC value or mode pair has been computed. A frequency diagnostic runs only when you "
                 "click Run frequency diagnostic, and nothing is assigned automatically.")
EMPTY_TEXT = ("No data selected yet. Choose an FE results file and an experimental file to start. "
              "Nothing is loaded or analysed automatically.")
LABEL_HINT = ("Optional. Your own name for this data. It is not looked up in the research archive, so it links the "
              "files to no archived specimen, registration or status.")
ARCHIVE_NOTE = ("The research archive is a read-only list of the laboratory's specimen records. Viewing it changes "
                "none of your workspace files, transfers no registration and assigns no modal status.")
STATUS_PATH = Path(__file__).resolve().parents[2] / "docs" / "auto_id" / "STATUS.json"
UNKNOWN = "UNKNOWN"


# ------------------------------------------------------------------------------------------------ file choices

@dataclass(frozen=True)
class FileChoice:
    """One side of the workspace. ``path`` is the checked absolute path, or None when nothing is chosen."""

    kind: str
    path: Optional[Path] = None
    file_type: str = ""

    @property
    def chosen(self) -> bool:
        return self.path is not None

    @property
    def status(self) -> str:
        return CHOSEN_NOT_CHECKED if self.chosen else NOT_CHOSEN


def file_type_text(kind: str, path: Path) -> str:
    """The type of a checked file, from its name only."""
    suffix, name = path.suffix.lower(), path.name.lower()
    if kind == FE:
        return "Extracted FE manifest (manifest.json)" if name == "manifest.json" else "Abaqus output database (.odb)"
    if suffix == ".lms":
        from universal_reader import resolve_testlab_file  # the same resolver check_file used; existence only

        return f"Simcenter Testlab project (.lms); companion universal file {resolve_testlab_file(path).name}"
    return f"Universal file ({suffix})"


def check_choice(kind: str, path) -> FileChoice:
    """The file as a choice of this kind; raises ``registry.RegistryError`` with the reason when it is refused."""
    file = registry.check_file(kind, path)  # read-only: nothing is written to the input file registry
    return FileChoice(kind, file, file_type_text(kind, file))


@dataclass(frozen=True)
class Workspace:
    """The whole workspace; immutable. A new workspace is empty."""

    fe: FileChoice = FileChoice(FE)
    experimental: FileChoice = FileChoice(EXPERIMENTAL)
    specimen_label: str = ""

    def choice(self, kind: str) -> FileChoice:
        return self.fe if kind == FE else self.experimental

    @property
    def empty(self) -> bool:
        return not (self.fe.chosen or self.experimental.chosen)

    @property
    def analysis(self) -> str:
        return ANALYSIS_NOT_RUN

    def choose(self, kind: str, path) -> tuple["Workspace", str]:
        """(the workspace, a message). A cancelled dialog (no path) changes nothing and says nothing; a refused file
        keeps the previous choice and says why."""
        if kind not in KINDS:
            raise ValueError(f"Unknown file kind {kind!r}.")
        if path is None or not str(path).strip():
            return self, ""
        try:
            choice = check_choice(kind, path)
        except registry.RegistryError as error:
            kept = "The previous choice is kept." if self.choice(kind).chosen else "Nothing was chosen."
            return self, f"{error} {kept}"
        return replace(self, **{"fe" if kind == FE else "experimental": choice}), ""

    def clear(self, kind: str) -> "Workspace":
        if kind not in KINDS:
            raise ValueError(f"Unknown file kind {kind!r}.")
        return replace(self, **{"fe" if kind == FE else "experimental": FileChoice(kind)})

    def with_label(self, text: str) -> "Workspace":
        return replace(self, specimen_label=str(text or "").strip())

    @property
    def label_text(self) -> str:
        if not self.specimen_label:
            return "Unnamed (a name is optional)"
        return f"{self.specimen_label} (your label; not looked up in the research archive)"


# ------------------------------------------------------------------------------------------------ research archive

@dataclass(frozen=True)
class ArchiveListing:
    """The research archive as read now: its records, or a problem and no record."""

    view: catalog.CatalogueView
    problem: str = ""

    @property
    def records(self) -> tuple[tuple[str, str], ...]:
        """(specimen ID, list text) of each record, in archive order."""
        return tuple((entry["specimen_id"], catalog.choice_text(entry)) for entry in self.view.specimens)

    def passport(self, specimen_id: str) -> list[catalog.PassportSection]:
        """The read-only passport of one record; a record that cannot be worded gives one section saying so."""
        entry = self.view.entry(specimen_id)
        if entry is None:
            return [catalog.PassportSection("Record", (("Record", f"{specimen_id} is not in the archive."),))]
        try:
            return catalog.passport_sections(entry, self.view)
        except Exception as error:  # a malformed record must not stop the program
            return [catalog.PassportSection("Record", (("Record", f"{specimen_id} cannot be shown: {error}"),))]


def load_archive(path: Optional[Path] = None) -> ArchiveListing:
    """The archive, read only; a missing or damaged archive gives a listing with a problem, never an exception."""
    try:
        view = catalog.load_catalogue(path)
    except Exception as error:  # load_catalogue already reports bad files; this guards anything unexpected
        view = catalog.CatalogueView(Path(path) if path is not None else catalog.CATALOGUE_PATH,
                                     problem=f"the research archive could not be read ({error})")
    return ArchiveListing(view, view.problem)


# ------------------------------------------------------------------------------------------------ scientific status

@dataclass(frozen=True)
class StatusRow:
    caption: str
    value: str
    note: str


def _status_record(path: Path) -> tuple[dict, str]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return {}, f"the project status record could not be read ({error.__class__.__name__})"
    if not isinstance(data, dict) or data.get("schema") != "auto-id-project-status/v1":
        return {}, "the project status record has an unexpected format"
    return data, ""


def scientific_status(status_path: Optional[Path] = None) -> tuple[StatusRow, ...]:
    """The scientific status as recorded elsewhere; nothing here sets, relaxes or computes it."""
    from services.workspace_context import production_auto_id_status

    auto_id = production_auto_id_status()
    data, problem = _status_record(status_path if status_path is not None else STATUS_PATH)
    m8 = data.get("m8") if isinstance(data.get("m8"), dict) else {}
    m7 = data.get("m7") if isinstance(data.get("m7"), dict) else {}
    closure = m7.get("closure_d077") if isinstance(m7.get("closure_d077"), dict) else {}
    gate = m8.get("original_gate") if isinstance(m8.get("original_gate"), str) else ""
    d077 = closure.get("formal_output") if closure.get("decision") == "D-077" else None
    source = "Recorded in docs/auto_id/STATUS.json."
    return (
        StatusRow("Production Auto-ID", auto_id.status,
                  f"Blocked by the program's authorisation code: {auto_id.reason}"),
        StatusRow("M8 gate", gate or UNKNOWN, (source if gate else problem or "STATUS.json records no M8 gate.")
                  + " Material identification is not available in this interface."),
        StatusRow("D-077 formal output", d077 if isinstance(d077, str) and d077 else UNKNOWN,
                  (source if d077 else problem or "STATUS.json records no D-077 output.")
                  + " No global material parameter value is reported."),
    )


__all__ = ["ANALYSIS_NOT_RUN", "ArchiveListing", "CHOSEN_NOT_CHECKED", "EXPERIMENTAL", "FE", "FileChoice", "KINDS",
           "NOT_CHOSEN", "StatusRow", "Workspace", "check_choice", "file_type_text", "load_archive",
           "scientific_status"]
