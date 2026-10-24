"""SETUP_UNDER_REVIEW: a person's diagnostic note on one experimental series (APP-E2E.3).

A series can be marked when the test setup (for example the suspension) may have influenced it and repeat
measurements are planned. The mark is:

- **set by a person only**, never automatically, with a mandatory reason, the source of the information and the
  experiment / test-run identifier;
- **bound to the series identity**: the SHA-256 and size of the experimental file content and the modal set, not to
  the file name. Another file, a re-export with other content, or another modal set is another series: it carries no
  mark and is not thereby declared valid either;
- **a note only**: it changes no frequency, shape, MAC, criterion, accepted registration or scientific status, it is not
  a gate, and nothing reads it to accept, exclude or pair modes;
- **recorded append-only** outside the data (one JSON log per user); setting and withdrawing are both kept. The
  experimental files are only read (hashed), never written.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Optional

from services.archived_sensitivity_evidence import fresh_content_identity

SCHEMA = "comparator/experimental-series-review/v1"
SETUP_UNDER_REVIEW = "SETUP_UNDER_REVIEW"
SET, WITHDRAWN = "SET", "WITHDRAWN"
STORE_NAME = "experimental_series_review.json"
NOTE = ("Diagnostic note set by a person: it changes no frequency, mode shape, MAC, criterion, accepted registration or "
        "scientific status, it is not a gate and no mode is excluded or paired because of it.")
NO_MARK = ("No review mark is recorded for this series. This is not a statement that the series or its test setup is "
           "valid.")


class SeriesReviewError(ValueError):
    """A mark refused (missing reason, source or experiment identifier; unreadable file)."""


def default_store() -> Path:
    """The per-user configuration folder of the comparator (project_review.CONFIG_DIRECTORY), outside every data
    store."""
    return Path.home() / ".abaqus_simcenter_modal_comparator" / STORE_NAME


@dataclass(frozen=True)
class SeriesIdentity:
    sha256: str
    size_bytes: int
    modal_set: str  # "" when the file has no fitted modal set (FRF / dataset 58 records)
    file_name: str = ""  # informational only; never part of the identity

    @property
    def key(self) -> str:
        return f"{self.sha256}:{self.size_bytes}:{self.modal_set}"

    def to_dict(self) -> dict:
        return {"sha256": self.sha256, "size_bytes": self.size_bytes, "modal_set": self.modal_set,
                "file_name_at_marking": self.file_name}


def series_identity(path: Path, modal_set: Optional[str], cancel=None) -> SeriesIdentity:
    """The identity of the series in this file now: its content hash and size, and the modal set."""
    try:
        content = fresh_content_identity(Path(path), cancel=cancel)
    except Exception as error:  # noqa: BLE001  (unreadable or changing file: no identity, no mark)
        raise SeriesReviewError(f"the experimental file cannot be identified: {error}") from error
    return SeriesIdentity(content["sha256"], int(content["size"]), str(modal_set or ""), Path(path).name)


def _read(store: Path) -> dict:
    try:
        data = json.loads(Path(store).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"schema": SCHEMA, "entries": []}
    except (OSError, ValueError) as error:
        raise SeriesReviewError(f"the review log {store} cannot be read: {error}") from error
    if data.get("schema") != SCHEMA or not isinstance(data.get("entries"), list):
        raise SeriesReviewError(f"{store} is not a {SCHEMA} log.")
    return data


def _append(store: Path, entry: dict) -> dict:
    store = Path(store)
    data = _read(store)
    data["entries"].append(entry)
    store.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".series_review_", suffix=".json", dir=str(store.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False)
        os.replace(temporary, store)  # atomic: the log is never half written
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return entry


def _required(value: str, what: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise SeriesReviewError(f"{what} is required.")
    return text


def mark_setup_under_review(store: Path, identity: SeriesIdentity, *, reason: str, source: str, experiment_id: str,
                            marked_by: str = "") -> dict:
    """Record SETUP_UNDER_REVIEW for exactly this series (a person's decision; reason, source and experiment id)."""
    return _append(store, {
        "action": SET, "status": SETUP_UNDER_REVIEW, "series": identity.to_dict(), "series_key": identity.key,
        "experiment_id": _required(experiment_id, "The experiment / test-run identifier"),
        "reason": _required(reason, "The reason"), "information_source": _required(source, "The source of the information"),
        "marked_by": str(marked_by or "").strip(), "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": NOTE})


def withdraw_mark(store: Path, identity: SeriesIdentity, *, reason: str, source: str) -> dict:
    """Withdraw the mark of this series (kept in the log; the series is not thereby declared valid)."""
    if active_mark(store, identity) is None:
        raise SeriesReviewError("This series has no active review mark.")
    return _append(store, {
        "action": WITHDRAWN, "status": SETUP_UNDER_REVIEW, "series": identity.to_dict(), "series_key": identity.key,
        "reason": _required(reason, "The reason"), "information_source": _required(source, "The source of the information"),
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})


def history(store: Path, identity: SeriesIdentity) -> list[dict]:
    return [entry for entry in _read(store)["entries"] if entry.get("series_key") == identity.key]


def active_mark(store: Path, identity: SeriesIdentity) -> Optional[dict]:
    entries = history(store, identity)
    return entries[-1] if entries and entries[-1].get("action") == SET else None


def mark_text(mark: Optional[dict]) -> str:
    """One line for the GUI and the reports."""
    if mark is None:
        return NO_MARK
    return (f"{SETUP_UNDER_REVIEW} — experiment {mark['experiment_id']}: {mark['reason']} (source: "
            f"{mark['information_source']}; recorded {mark['recorded_at']}"
            + (f" by {mark['marked_by']}" if mark.get("marked_by") else "") + "). " + NOTE)
