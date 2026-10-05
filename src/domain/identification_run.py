"""Identification run identity, solver profiles and the atomic run journal — Auto-ID M4.6.

Approved M4.6 design (M4_DECISION_RECORD.md §6):

- **Solver profiles** are separate data (Abaqus release, cpus, command template, scratch
  policy); the M3 forward-model manifests are not touched.
- **Content identities only**: nothing is identified by path, size or modification time.
- **Atomic, append-only journal**: every entry is chained to the previous one by SHA-256,
  the whole journal is rewritten via ``.partial`` + ``os.replace``; a broken chain is refused.
- Identification evaluations (reused and new) and actual Abaqus solves are counted
  separately.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping


SOLVER_PROFILE_SCHEMA = "auto-id/solver-profile/v1"
RUN_SCHEMA = "auto-id/identification-run/v1"
JOURNAL_SCHEMA = "auto-id/identification-journal/v1"
_TEMPLATE_FIELDS = {"abaqus", "job", "inp", "cpus", "scratch"}
_PROFILE_KEYS = {"schema", "profile_id", "forward_model_id", "job_prefix", "abaqus_release", "command_template",
                 "cpus", "scratch", "completion_marker", "version_marker", "provenance"}


class RunIdentityError(ValueError):
    """A run, profile or journal does not match its identity; nothing is repaired."""


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SolverProfile:
    """How one forward model is solved; machine paths are supplied at run time, never stored."""

    profile_id: str
    forward_model_id: str
    job_prefix: str
    abaqus_release: str  # e.g. "Abaqus 2024"; must appear in the job's .dat (version_marker)
    command_template: str  # placeholders {abaqus} {job} {inp} {cpus} {scratch}
    cpus: int
    scratch_store: str | None  # store name whose root is the solver scratch directory, or None
    completion_marker: str  # text that the .sta file must contain
    version_marker: str
    canonical: Mapping[str, Any]

    @property
    def profile_hash(self) -> str:
        return canonical_hash(self.canonical)

    def render_command(self, abaqus: str, job: str, inp: str, scratch: str | None) -> str:
        if (self.scratch_store is None) != (scratch is None):
            raise RunIdentityError(f"{self.profile_id}: scratch directory required = {self.scratch_store is not None}.")
        return self.command_template.format(abaqus=abaqus, job=job, inp=inp, cpus=self.cpus,
                                            scratch="" if scratch is None else f" scratch={scratch}")


def parse_solver_profile(data: object) -> SolverProfile:
    if not isinstance(data, Mapping) or set(data) != _PROFILE_KEYS:
        found = set(data) if isinstance(data, Mapping) else set()
        raise RunIdentityError(f"solver profile: missing {sorted(_PROFILE_KEYS - found)}, "
                               f"unknown {sorted(found - _PROFILE_KEYS)}.")
    if data["schema"] != SOLVER_PROFILE_SCHEMA:
        raise RunIdentityError(f"solver profile schema must be {SOLVER_PROFILE_SCHEMA!r}.")
    template = data["command_template"]
    fields = set(re.findall(r"{(\w+)}", template)) if isinstance(template, str) else set()
    if fields != _TEMPLATE_FIELDS:
        raise RunIdentityError(f"command_template must use exactly {sorted(_TEMPLATE_FIELDS)}; found {sorted(fields)}.")
    if re.search(r"[A-Za-z]:\\|^/", template):
        raise RunIdentityError("command_template must not contain machine paths.")
    cpus = data["cpus"]
    if isinstance(cpus, bool) or not isinstance(cpus, int) or cpus < 1:
        raise RunIdentityError("cpus must be a positive integer.")
    scratch = data["scratch"]
    if scratch is not None and (not isinstance(scratch, Mapping) or set(scratch) != {"store"}):
        raise RunIdentityError("scratch must be null or {\"store\": <store name>}.")
    for key in ("profile_id", "forward_model_id", "job_prefix", "abaqus_release", "completion_marker",
                "version_marker"):
        if not isinstance(data[key], str) or not data[key].strip():
            raise RunIdentityError(f"{key} must be a non-empty string.")
    canonical = {key: data[key] for key in sorted(_PROFILE_KEYS - {"provenance"})}
    return SolverProfile(data["profile_id"], data["forward_model_id"], data["job_prefix"], data["abaqus_release"],
                         template, cpus, None if scratch is None else str(scratch["store"]),
                         data["completion_marker"], data["version_marker"], canonical)


def load_solver_profile(path: Path) -> SolverProfile:
    with open(path, encoding="utf-8") as handle:
        return parse_solver_profile(json.load(handle))


class RunJournal:
    """Append-only, hash-chained journal of one identification run (single JSON file, atomic writes)."""

    def __init__(self, path: Path, run_identity: Mapping[str, Any]) -> None:
        self.path = Path(path)
        self.run_identity = dict(run_identity)
        self.run_hash = canonical_hash(self.run_identity)
        if self.path.exists():
            document = json.loads(self.path.read_text(encoding="utf-8"))
            if document.get("schema") != JOURNAL_SCHEMA:
                raise RunIdentityError("journal schema differs.")
            if document.get("run_hash") != self.run_hash or document.get("run_identity") != self.run_identity:
                raise RunIdentityError("the journal belongs to another run (run identity differs); not resumed.")
            self.entries = list(document["entries"])
            self._verify_chain()
        else:
            self.entries = []
            self._write()

    def _verify_chain(self) -> None:
        previous = self.run_hash
        for index, entry in enumerate(self.entries):
            body = {k: entry[k] for k in ("sequence", "kind", "record", "previous_hash")}
            if entry["sequence"] != index or entry["previous_hash"] != previous or entry["entry_hash"] != canonical_hash(body):
                raise RunIdentityError(f"journal entry {index} breaks the hash chain; the journal is refused.")
            previous = entry["entry_hash"]

    def _write(self) -> None:
        document = {"schema": JOURNAL_SCHEMA, "run_hash": self.run_hash, "run_identity": self.run_identity,
                    "entries": self.entries}
        partial = self.path.with_name(self.path.name + ".partial")
        partial.write_text(json.dumps(document, indent=1, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        os.replace(partial, self.path)

    def append(self, kind: str, record: Mapping[str, Any]) -> dict:
        previous = self.entries[-1]["entry_hash"] if self.entries else self.run_hash
        body = {"sequence": len(self.entries), "kind": kind, "record": dict(record), "previous_hash": previous}
        entry = dict(body, entry_hash=canonical_hash(body))
        self.entries.append(entry)
        self._write()
        return entry

    def records(self, kind: str) -> list[dict]:
        return [entry["record"] for entry in self.entries if entry["kind"] == kind]

    def find(self, kind: str, **match: Any) -> dict | None:
        for record in self.records(kind):
            if all(record.get(key) == value for key, value in match.items()):
                return record
        return None


class RunLock:
    """One writer per run directory: an exclusive lock file holding an owner token."""

    def __init__(self, directory: Path, owner: str) -> None:
        self.path = Path(directory) / ".run.lock"
        self.owner = owner
        self.held = False

    def __enter__(self) -> "RunLock":
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise RunIdentityError(f"run directory is locked by another writer ({self.path}).") from None
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(self.owner)
        self.held = True
        return self

    def __exit__(self, *_exc) -> None:
        if self.held and self.path.exists() and self.path.read_text(encoding="utf-8") == self.owner:
            self.path.unlink()
        self.held = False
