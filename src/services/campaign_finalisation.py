"""Finalise & Export Campaign Definition — Auto-ID M8-D2g (a complete draft becomes a SPEC v1.2 definition file).

``finalise_campaign`` re-verifies the draft before anything is finalised, with the existing validators only: the draft
is rebuilt from its own document by ``draft_from_document`` (the reopening path: governed specimen identities, bound
governed records, accepted FIT / HOLDOUT observations on their strict freeze and physical registration, the declared
configuration with its repository checks, the archive-reuse plan) and must equal the current draft; then
``CampaignDraft.finalise`` — the governed ``parse_campaign_definition`` — accepts it, or it is refused with the reasons.

``export_campaign_definition`` writes exactly the definition the parser accepted (no extra field) to a ``.json`` file
the user chose outside the repository and every data store, atomically: the temporary file is loaded by the existing
``load_campaign_definition`` and published only when its campaign hash equals the hash that was checked and shown;
the published file is loaded again.  If the data changed between the check and the save, nothing is written.  An
existing file is replaced only after an explicit confirmation and only when it is itself a campaign definition.  A
separate export protocol (``*.export-protocol.json``) records the checks for diagnosis; it is not governed evidence.

A finalised, exported definition authorises nothing: execution needs its own HUMAN gate, and its decision and
provenance text is never an authorisation.  Nothing here runs Abaqus, FE or LM.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Iterable, Optional

from domain.campaign_definition import (
    CampaignDefinition,
    CampaignDefinitionError,
    load_campaign_definition,
)
from domain.experiment_fixture import ExperimentFixtureManifest

from .campaign_draft import CampaignDraft, CampaignDraftError, DraftIncomplete, draft_from_document

EXPORT_PROTOCOL_SCHEMA = "auto-id/campaign-definition-export-protocol/v1"
PROTOCOL_LABELS = ("DIAGNOSTIC_EXPORT_PROTOCOL", "NOT_GOVERNED_EVIDENCE", "AUTHORISES_NOTHING")
NOT_AN_AUTHORISATION = ("a complete campaign definition is not identifiability and not an execution authorisation; "
                        "execution needs its own HUMAN gate; production calibration stays BLOCKED / NOT_AUTHORISED")
RECHECKS = ("explicit declarations and configuration (campaign-definition field validators)",
            "governed specimen identities (forward model, passport, fixture, registration)",
            "bound governed specimen records (solver profile, archived baseline, shape pack, registration evidence)",
            "accepted FIT / HOLDOUT observations on the strict freeze and the physical registration",
            "archive-reuse plan and forward-model parameterisation (repository checks)",
            "no missing required input; parse_campaign_definition")


@dataclass(frozen=True)
class FinalisedCampaign:
    definition: CampaignDefinition
    data: dict  # the exact definition the parser accepted (what is written)
    draft_fingerprint: str

    @property
    def campaign_hash(self) -> str:
        return self.definition.campaign_hash


@dataclass(frozen=True)
class ExportResult:
    path: Path
    campaign_id: str
    campaign_hash: str
    reloaded_hash: str
    protocol_path: Optional[Path]
    protocol_error: Optional[str]

    def summary(self) -> str:
        text = (f"Exported campaign definition {self.campaign_id} to {self.path}; campaign hash {self.campaign_hash} "
                f"(re-read by load_campaign_definition: {self.reloaded_hash}). {NOT_AN_AUTHORISATION}.")
        if self.protocol_path is not None:
            text += f" Export protocol (diagnostic, not governed): {self.protocol_path}."
        if self.protocol_error:
            text += f" The export protocol could not be written: {self.protocol_error}."
        return text


def _fingerprint(draft: CampaignDraft) -> str:
    return hashlib.sha256(draft.document_bytes()).hexdigest()


def reverify_draft(draft: CampaignDraft, repo_root: Path, fixtures: ExperimentFixtureManifest) -> CampaignDraft:
    """The draft rebuilt from its own document against the current governed records; refused if anything differs."""

    if not isinstance(draft, CampaignDraft):
        raise CampaignDraftError("no campaign draft to finalise.")
    rebuilt = draft_from_document(draft.document(), repo_root, fixtures)  # refuses with the reason on any change
    if rebuilt != draft:
        raise CampaignDraftError("the draft no longer equals its re-verified form (the governed records changed); "
                                 "nothing is finalised.")
    return rebuilt


def finalise_campaign(draft: CampaignDraft, repo_root: Path, fixtures: ExperimentFixtureManifest) -> FinalisedCampaign:
    """Re-verify the draft, then finalise it with the governed parser (``CampaignDraft.finalise``)."""

    draft = reverify_draft(draft, repo_root, fixtures)
    definition = draft.finalise()  # DraftIncomplete or CampaignDefinitionError on any refusal
    data = json.loads(json.dumps(draft.intended_definition(), allow_nan=False))
    return FinalisedCampaign(definition, data, _fingerprint(draft))


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _is_definition(path: Path) -> bool:
    """Only a file the governed ``load_campaign_definition`` accepts is a campaign definition (a matching ``schema``
    alone is not enough)."""
    try:
        load_campaign_definition(path)
    except (OSError, ValueError, TypeError, KeyError, CampaignDefinitionError):
        return False
    return True


def _is_protocol(path: Path) -> bool:
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("schema") == EXPORT_PROTOCOL_SCHEMA
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        return False


def check_definition_destination(destination, protected_roots: Iterable, overwrite: bool = False) -> Path:
    """A permitted destination: ``.json``, outside every protected root; an existing file only with confirmation and
    only when it is itself a campaign definition."""

    if destination is None or not str(destination).strip():
        raise CampaignDraftError("no destination selected.")
    target = Path(destination).resolve()
    if target.suffix.lower() != ".json":
        raise CampaignDraftError(f"{target.name}: a campaign definition is a .json document.")
    if not target.parent.is_dir():
        raise CampaignDraftError(f"the folder {target.parent} does not exist.")
    for root in protected_roots:
        if root is None:
            raise CampaignDraftError("a protected root could not be determined; nothing is written.")
        if _inside(target, Path(root).resolve()):
            raise CampaignDraftError(f"{target} is inside the protected {Path(root)} (repository or data store); "
                                     "campaign definitions are exported elsewhere.")
    if target.exists():
        if not target.is_file() or not _is_definition(target):
            raise CampaignDraftError(f"{target} exists and is not a campaign definition; it is never overwritten.")
        if not overwrite:
            raise CampaignDraftError(f"{target} exists; it is replaced only after an explicit confirmation.")
    return target


def _atomic_write(target: Path, data: bytes, verify=None) -> None:
    temporary = None
    try:
        handle, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".partial", dir=target.parent)
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if verify is not None:
            verify(Path(temporary))
        os.replace(temporary, target)
        temporary = None
    except BaseException as error:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass
        if isinstance(error, CampaignDraftError):
            raise
        if isinstance(error, Exception):
            raise CampaignDraftError(f"{target}: {error}") from error
        raise


def export_campaign_definition(draft: CampaignDraft, destination, repo_root: Path,
                               fixtures: ExperimentFixtureManifest, protected_roots: Iterable,
                               expected_hash: str, overwrite: bool = False) -> ExportResult:
    """Re-check, then write the accepted definition atomically and re-read it with ``load_campaign_definition``.

    ``expected_hash`` is the campaign hash of the check shown to the user: if the re-check now gives another
    definition, the data changed between the check and the save and nothing is written.
    """

    target = check_definition_destination(destination, protected_roots, overwrite)
    finalised = finalise_campaign(draft, repo_root, fixtures)
    if finalised.campaign_hash != expected_hash:
        raise CampaignDraftError(f"the campaign definition changed since it was checked (hash {expected_hash[:12]} → "
                                 f"{finalised.campaign_hash[:12]}); nothing is written — check and finalise again.")
    payload = (json.dumps(finalised.data, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")

    def verify(temporary: Path) -> None:
        try:
            loaded = load_campaign_definition(temporary)
        except (OSError, ValueError, CampaignDefinitionError) as error:
            raise CampaignDraftError(f"the written definition is not accepted by load_campaign_definition: {error}; "
                                     "nothing is published.") from error
        if loaded.campaign_hash != finalised.campaign_hash:
            raise CampaignDraftError("the written definition re-reads with another campaign hash; nothing is "
                                     "published.")

    _atomic_write(target, payload, verify)
    reloaded = load_campaign_definition(target)
    if reloaded.campaign_hash != finalised.campaign_hash:  # never expected after the verified rename
        raise CampaignDraftError(f"{target}: the published definition re-reads with another campaign hash.")
    protocol_path, protocol_error = target.with_name(target.name[:-len(target.suffix)] + ".export-protocol.json"), None
    protocol = {"schema": EXPORT_PROTOCOL_SCHEMA, "labels": list(PROTOCOL_LABELS),
                "definition": {"path": str(target), "campaign_id": finalised.definition.campaign_id,
                               "campaign_hash": finalised.campaign_hash, "schema": finalised.definition.schema,
                               "file_sha256": hashlib.sha256(payload).hexdigest()},
                "reloaded_campaign_hash": reloaded.campaign_hash, "draft_fingerprint": finalised.draft_fingerprint,
                "rechecked": list(RECHECKS), "statement": NOT_AN_AUTHORISATION}
    try:
        if protocol_path.exists() and not _is_protocol(protocol_path):
            raise CampaignDraftError(f"{protocol_path} exists and is not an export protocol; it is never overwritten")
        _atomic_write(protocol_path, (json.dumps(protocol, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    except CampaignDraftError as error:
        protocol_path, protocol_error = None, str(error)
    return ExportResult(target, finalised.definition.campaign_id, finalised.campaign_hash, reloaded.campaign_hash,
                        protocol_path, protocol_error)


__all__ = ["FinalisedCampaign", "ExportResult", "finalise_campaign", "export_campaign_definition",
           "check_definition_destination", "reverify_draft", "DraftIncomplete", "NOT_AN_AUTHORISATION"]
