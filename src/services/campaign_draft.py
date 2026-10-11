"""Campaign draft preparation — Auto-ID M8-D1 (GUI preparation of a new campaign; nothing is validated as a campaign).

A *campaign draft* is a working document, separate from the governed campaign schema: it collects what the user
declares explicitly and what the selected governed records state, shows every required campaign input that is still
missing, and previews the intended ``auto-id/identification-campaign/v1.2`` definition.  It is never a campaign
definition, never executable and authorises nothing.

The draft holds:
- the explicitly declared scientific question (MATERIAL_IDENTIFICATION or SPECIMEN_ENGINEERING_CALIBRATION) and τ_mf,
  each validated by the campaign-definition domain rules (``declared_scientific_question`` / ``declared_tau_mf``);
  neither has a default;
- governed specimen inputs: forward-model manifests inside the repository, loaded through the governed binder
  (manifest, specimen passport, experiment fixture); their identities are shown as recorded.

The draft never chooses or invents mode pairings, FIT / HOLDOUT rows, a registration or registration evidence, a
solver profile, FE baselines, uncertainties, fitted or fixed parameters, bounds, LM or solver settings, a budget, a
decision or an authorisation: every such field is listed as missing.  Completeness is judged by the domain rules
(``CAMPAIGN_KEYS``, ``CAMPAIGN_SPECIMEN_KEYS``, ``require_specimen_count``), and finalisation is exactly
``parse_campaign_definition`` — refused while anything is missing.  Nothing here runs Abaqus, FE or LM.

M8-D2c adds the explicitly declared ``campaign_id`` and ``run_type`` (RUN_A or RUN_B; domain validation, no default;
RUN_B grants no execution authorisation: its ``run_b_gate`` stays a missing, SUPERVISOR-gated input).  Drafts are
saved as ``auto-id/campaign-draft/v2``; a ``v1`` draft (which declares neither field) is still opened as written.

Reopening (``load_draft``, M8-D2a) accepts only a campaign-draft document (v1 or v2).  It rebuilds the draft from
its explicit declarations through the domain validators and from its specimen selections through the governed binder
(location, manifest, passport, fixture catalogue), and refuses any stored identity or pinned hash that differs from the
current governed records, any missing or invalid reference and any conflicting preview; it never substitutes another
specimen.  The stored status, missing inputs and preview are never trusted: they are recomputed.

Checking the draft's inputs (``check_draft_inputs``, M8-D2b) re-verifies every selected specimen against the current
governed records and runs the existing M8.1 wizard preparation on its passport and fixture: experimental modal data,
FE inputs and other pinned external files are reported with their factual availability (PRESENT_SHA256_NOT_VERIFIED,
NOT_CONFIGURED, NOT_FOUND, MISMATCH, ...) and the passport's recorded physical-data gaps are shown.  It is never a
scientific readiness verdict (the shared backend judges readiness) and never substitutes an input.

Writing (``write_draft``) happens only on an explicit Save As, to a ``.json`` destination outside the repository, the
data stores and the selected source; never to a ``*.campaign.json`` name, never over a file that is not an earlier
campaign draft; atomically (temporary file in the destination folder, then ``os.replace``).
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
from typing import Iterable, Optional

from domain.campaign_definition import (
    CAMPAIGN_KEYS,
    SCIENTIFIC_QUESTIONS,
    CAMPAIGN_SCHEMA_V1_2,
    CAMPAIGN_SPECIMEN_KEYS,
    CampaignDefinition,
    CampaignDefinitionError,
    RUN_B,
    RUN_B_LABEL,
    RUN_TYPES,
    declared_campaign_id,
    declared_run_type,
    declared_scientific_question,
    declared_tau_mf,
    parse_campaign_definition,
    require_specimen_count,
    require_unique_specimens,
)
from domain.experiment_fixture import ExperimentFixtureManifest, FixtureManifestError
from domain.forward_model_manifest import ForwardModelManifestError
from domain.specimen_manifest import SpecimenManifestError

from .forward_builder import load_bound_forward_model

DRAFT_SCHEMA_V1 = "auto-id/campaign-draft/v1"  # M8-D1 / D2a: declares scientific_question and tau_mf
DRAFT_SCHEMA = "auto-id/campaign-draft/v2"  # M8-D2c: also campaign_id and run_type
DRAFT_SCHEMAS = (DRAFT_SCHEMA_V1, DRAFT_SCHEMA)
_DECLARED_KEYS = {DRAFT_SCHEMA_V1: ("scientific_question", "tau_mf"),
                  DRAFT_SCHEMA: ("scientific_question", "tau_mf", "campaign_id", "run_type")}
DRAFT_KIND = "CAMPAIGN_DRAFT"
DRAFT_LABELS = ("DRAFT_NOT_A_CAMPAIGN_DEFINITION", "NOT_VALIDATED", "NOT_EXECUTABLE", "AUTHORISES_NOTHING")
DRAFT_NOTE = ("Campaign draft (Auto-ID M8-D1): a working document, not a campaign definition. It is never loaded as "
              "a campaign, never executed and authorises nothing. Every required input it does not declare is listed "
              "under missing_required_inputs; finalisation is the governed campaign-definition parser.")
NOT_CHOSEN = ("not declared by the draft: M8-D1 never chooses mode pairings, FIT / HOLDOUT rows, registration evidence, "
              "solver profiles, FE baselines, uncertainties, parameters, settings, budgets, decisions or authorisation")
PRODUCTION = "BLOCKED / NOT_AUTHORISED"
AUTHORISATION = "none: a draft authorises no run; execution needs a HUMAN gate"
FORWARD_MODEL_DIRECTORY = PurePosixPath("docs/auto_id/forward_models")  # the only governed specimen-input location
QUESTION_CHOICES = SCIENTIFIC_QUESTIONS  # offered for an explicit choice; none is preselected
RUN_TYPE_CHOICES = RUN_TYPES  # offered for an explicit choice; none is preselected
RUN_B_NOT_AUTHORISED = (f"{RUN_B} ({RUN_B_LABEL}) is diagnostic only: selecting it authorises nothing; its own "
                        "SUPERVISOR gate (run_b_gate) stays required and is never set by a draft")


class CampaignDraftError(ValueError):
    """A declaration or a selected input is refused; the draft is unchanged."""


class DraftIncomplete(CampaignDraftError):
    """Finalisation refused: required campaign inputs are missing."""

    def __init__(self, gaps) -> None:
        super().__init__(f"{len(gaps)} required campaign input(s) missing: "
                         + "; ".join(f"{g.field}: {g.reason}" for g in gaps))
        self.gaps = tuple(gaps)


@dataclass(frozen=True)
class DraftGap:
    field: str
    reason: str


@dataclass(frozen=True)
class DraftSpecimen:
    """A governed specimen input as its records state it (nothing is chosen)."""

    label: str  # the governed forward model's job prefix
    forward_model: str  # repository-relative POSIX path of the forward-model manifest
    forward_model_id: str
    forward_manifest_hash: str
    fixture_id: Optional[str]  # the passport's linked experiment fixture
    passport: str
    passport_manifest_hash: str
    physical_specimen_id: Optional[str]
    test_run_id: str
    registration_hash: str
    registration_basis: str

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def governed_specimen_input(manifest_path, repo_root: Path, fixtures: ExperimentFixtureManifest) -> DraftSpecimen:
    """A forward-model manifest in ``docs/auto_id/forward_models/``, loaded through the governed binder (read-only).

    The governed fixture catalogue is required (fail-closed): without it the binder could not check the manifest
    against its linked experiment fixture, so the selection is refused.
    """

    if not isinstance(fixtures, ExperimentFixtureManifest):
        raise CampaignDraftError("the governed experiment-fixture catalogue is not loaded and validated; the specimen "
                                 "input cannot be checked against its fixture and is refused.")

    path, root = Path(manifest_path).resolve(), Path(repo_root).resolve()
    try:
        relative = PurePosixPath(path.relative_to(root).as_posix())
    except ValueError:
        raise CampaignDraftError(f"{path} is not inside the repository: only governed forward-model manifests "
                                 f"(docs/auto_id/forward_models/*.forward.json) are campaign specimen inputs.") from None
    if relative.parent != FORWARD_MODEL_DIRECTORY:
        raise CampaignDraftError(f"{relative}: governed specimen inputs are the forward-model manifests in "
                                 f"{FORWARD_MODEL_DIRECTORY}/ only.")
    if not path.name.endswith(".forward.json"):
        raise CampaignDraftError(f"{relative}: a governed specimen input is a forward-model manifest "
                                 "(*.forward.json).")
    try:
        model = load_bound_forward_model(path, root, fixtures)
    except (ForwardModelManifestError, SpecimenManifestError, FixtureManifestError, KeyError, OSError,
            ValueError) as error:
        raise CampaignDraftError(f"{relative} is refused by the governed forward-model binder: {error}") from error
    manifest, passport = model.manifest, model.passport
    return DraftSpecimen(
        label=manifest.job_prefix, forward_model=str(relative), forward_model_id=manifest.forward_model_id,
        forward_manifest_hash=manifest.manifest_hash, fixture_id=passport.acquisition.fixture_id,
        passport=manifest.specimen_passport.path, passport_manifest_hash=passport.manifest_hash,
        physical_specimen_id=None if passport.physical_specimen_id is None else str(passport.physical_specimen_id),
        test_run_id=str(passport.test_run_id), registration_hash=manifest.registration_hash,
        registration_basis=passport.geometry_calibration.registration_basis_status.value)


@dataclass(frozen=True)
class CampaignDraft:
    scientific_question: Optional[str] = None
    tau_mf: Optional[float] = None
    specimens: tuple[DraftSpecimen, ...] = ()
    campaign_id: Optional[str] = None  # M8-D2c
    run_type: Optional[str] = None  # M8-D2c

    # ------------------------------------------------------------------ explicit declarations
    def with_question(self, question) -> "CampaignDraft":
        try:
            return replace(self, scientific_question=declared_scientific_question(question))
        except CampaignDefinitionError as error:
            raise CampaignDraftError(str(error)) from error

    def with_tau_mf(self, value) -> "CampaignDraft":
        if isinstance(value, str):
            try:
                value = float(value.strip())
            except ValueError:
                raise CampaignDraftError(f"tau_mf: {value!r} is not a number; declare it explicitly.") from None
        try:
            return replace(self, tau_mf=declared_tau_mf(value))
        except CampaignDefinitionError as error:
            raise CampaignDraftError(str(error)) from error

    def with_campaign_id(self, value) -> "CampaignDraft":
        try:
            return replace(self, campaign_id=declared_campaign_id(value))
        except CampaignDefinitionError as error:
            raise CampaignDraftError(str(error)) from error

    def with_run_type(self, value) -> "CampaignDraft":
        try:
            return replace(self, run_type=declared_run_type(value))
        except CampaignDefinitionError as error:
            raise CampaignDraftError(str(error)) from error

    def with_specimen(self, specimen: DraftSpecimen) -> "CampaignDraft":
        if any(s.forward_model == specimen.forward_model for s in self.specimens):
            raise CampaignDraftError(f"{specimen.forward_model} is already in the draft.")
        return replace(self, specimens=self.specimens + (specimen,))

    def without_specimens(self) -> "CampaignDraft":
        return replace(self, specimens=())

    # ------------------------------------------------------------------ preview and completeness
    def intended_definition(self) -> dict:
        """The intended v1.2 campaign definition: only what is declared or recorded; nothing is filled in."""

        intended = {"schema": CAMPAIGN_SCHEMA_V1_2,
                    "specimens": [{"label": s.label, "fixture_id": s.fixture_id, "forward_model": s.forward_model}
                                  for s in self.specimens]}
        if self.scientific_question is not None:
            intended["scientific_question"] = self.scientific_question
        if self.tau_mf is not None:
            intended["tau_mf"] = self.tau_mf
        if self.campaign_id is not None:
            intended["campaign_id"] = self.campaign_id
        if self.run_type is not None:
            intended["run_type"] = self.run_type
        return intended

    def gaps(self) -> tuple[DraftGap, ...]:
        intended = self.intended_definition()
        gaps = []
        if self.scientific_question is None:
            gaps.append(DraftGap("scientific_question", "not declared: choose MATERIAL_IDENTIFICATION or "
                                                        "SPECIMEN_ENGINEERING_CALIBRATION explicitly"))
        if self.tau_mf is None:
            gaps.append(DraftGap("tau_mf", "not declared: no value is assumed"))
        if self.scientific_question is None:
            gaps.append(DraftGap("specimens", "the required number of specimens follows the declared question"))
        else:
            try:
                require_specimen_count(self.scientific_question, len(self.specimens))
            except CampaignDefinitionError as error:
                gaps.append(DraftGap("specimens", str(error)))
        try:
            require_unique_specimens((s.label for s in self.specimens), (s.fixture_id for s in self.specimens))
        except CampaignDefinitionError as error:
            gaps.append(DraftGap("specimens", f"{error} ({', '.join(s.label for s in self.specimens)})"))
        for index, item in enumerate(intended["specimens"]):
            if item["fixture_id"] is None:
                gaps.append(DraftGap(f"specimens[{index}].fixture_id", "the governed passport links no experiment "
                                                                       "fixture"))
            for key in sorted(CAMPAIGN_SPECIMEN_KEYS - set(item)):
                gaps.append(DraftGap(f"specimens[{index}].{key}", NOT_CHOSEN))
        for key in sorted(CAMPAIGN_KEYS - set(intended)):
            gaps.append(DraftGap(key, RUN_B_NOT_AUTHORISED if key == "run_b_gate" and self.run_type == RUN_B
                                 else NOT_CHOSEN))
        return tuple(gaps)

    def finalise(self) -> CampaignDefinition:
        """The governed parser on the intended definition; refused while any required input is missing."""

        gaps = self.gaps()
        if gaps:
            raise DraftIncomplete(gaps)
        return parse_campaign_definition(self.intended_definition())

    def document(self) -> dict:
        """The deterministic draft document (no timestamps, no random identifiers)."""

        gaps = self.gaps()
        return {
            "schema": DRAFT_SCHEMA, "kind": DRAFT_KIND, "labels": list(DRAFT_LABELS), "note": DRAFT_NOTE,
            "status": "INCOMPLETE" if gaps else "COMPLETE_NOT_FINALISED",
            "declared": {"scientific_question": self.scientific_question, "tau_mf": self.tau_mf,
                         "campaign_id": self.campaign_id, "run_type": self.run_type},
            "specimen_identities": [s.to_dict() for s in self.specimens],
            "intended_campaign_definition": self.intended_definition(),
            "missing_required_inputs": [{"field": g.field, "reason": g.reason} for g in gaps],
            "authorisation": AUTHORISATION,
            "production_calibration_execution": PRODUCTION,
        }

    def document_bytes(self) -> bytes:
        return (json.dumps(self.document(), indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
                + "\n").encode("utf-8")


def declare_tolerance(draft: CampaignDraft, value) -> CampaignDraft:
    """The draft with τ_mf declared explicitly (GUI entry text or a number)."""
    return draft.with_tau_mf(value)


def draft_rows(draft: CampaignDraft) -> tuple[tuple[str, str, str, str], ...]:
    """Table rows (section, item, value, status) for the GUI: declarations, specimen identities, missing inputs."""

    run_type = draft.run_type or ""
    if draft.run_type == RUN_B:
        run_type = f"{RUN_B} — {RUN_B_NOT_AUTHORISED}"
    rows = [("Declared", "Campaign id", draft.campaign_id or "", "PRESENT" if draft.campaign_id else "NOT_DECLARED"),
            ("Declared", "Run type", run_type, "PRESENT" if draft.run_type else "NOT_DECLARED"),
            ("Declared", "Scientific question", draft.scientific_question or "",
             "PRESENT" if draft.scientific_question else "NOT_DECLARED"),
            ("Declared", "τ_mf", "" if draft.tau_mf is None else f"{draft.tau_mf:g}",
             "NOT_DECLARED" if draft.tau_mf is None else "PRESENT")]
    for item in draft.specimens:
        rows.append(("Specimens", item.label,
                     f"fixture {item.fixture_id}; forward model {item.forward_model_id} ({item.forward_model}); "
                     f"physical specimen {item.physical_specimen_id}; test run {item.test_run_id}; registration "
                     f"{item.registration_basis} {item.registration_hash[:12]}", "PRESENT"))
    rows.extend(("Missing required inputs", gap.field, gap.reason, "MISSING") for gap in draft.gaps())
    return tuple(rows)


def finalisation_state(draft: CampaignDraft) -> str:
    """Whether the governed parser would accept the draft; it stays a draft either way (nothing is written)."""

    try:
        draft.finalise()
    except DraftIncomplete as refusal:
        return (f"Finalisation refused: {len(refusal.gaps)} required campaign input(s) missing. The draft stays a "
                "draft (not a validated campaign definition).")
    except CampaignDefinitionError as error:
        return f"Finalisation refused by the campaign-definition parser: {error}"
    return "All required inputs present: accepted by the campaign-definition parser (no definition is written here)."


# ----------------------------------------------------------------------------- reopening (M8-D2a)

_DOCUMENT_KEYS = {"schema", "kind", "labels", "note", "status", "declared", "specimen_identities",
                  "intended_campaign_definition", "missing_required_inputs", "authorisation",
                  "production_calibration_execution"}
_SPECIMEN_FIELDS = tuple(f.name for f in fields(DraftSpecimen))


def _refuse(message: str):
    raise CampaignDraftError(message)


def draft_from_document(document, repo_root: Path, fixtures: ExperimentFixtureManifest) -> CampaignDraft:
    """Rebuild a saved draft against the current governed records (refused on any mismatch; nothing substituted)."""

    if not isinstance(document, dict) or document.get("schema") not in DRAFT_SCHEMAS:
        _refuse(f"not a campaign draft: only {' / '.join(DRAFT_SCHEMAS)} documents can be opened.")
    keys = _DECLARED_KEYS[document["schema"]]  # a v1 draft declares no campaign_id / run_type (never inferred)
    if set(document) != _DOCUMENT_KEYS:
        _refuse(f"malformed draft: missing {sorted(_DOCUMENT_KEYS - set(document))}, unknown "
                f"{sorted(set(document) - _DOCUMENT_KEYS)}.")
    if document["kind"] != DRAFT_KIND or document["labels"] != list(DRAFT_LABELS)             or document["authorisation"] != AUTHORISATION or document["production_calibration_execution"] != PRODUCTION:
        _refuse("malformed draft: its kind, labels, authorisation or production statement differ from a campaign "
                "draft's (a draft authorises nothing).")
    declared = document["declared"]
    if not isinstance(declared, dict) or set(declared) != set(keys):
        _refuse(f"malformed draft: 'declared' must state exactly {', '.join(keys)} for {document['schema']} (null "
                "when not declared).")
    draft = CampaignDraft()
    if declared.get("campaign_id") is not None:
        draft = draft.with_campaign_id(declared["campaign_id"])  # domain validation
    if declared.get("run_type") is not None:
        draft = draft.with_run_type(declared["run_type"])  # domain validation
    if declared["scientific_question"] is not None:
        draft = draft.with_question(declared["scientific_question"])  # domain validation
    if declared["tau_mf"] is not None:
        if isinstance(declared["tau_mf"], str):
            _refuse("malformed draft: the declared tau_mf must be a number.")
        draft = draft.with_tau_mf(declared["tau_mf"])  # domain validation
    identities = document["specimen_identities"]
    if not isinstance(identities, list):
        _refuse("malformed draft: 'specimen_identities' must be a list.")
    for index, stored in enumerate(identities):
        if not isinstance(stored, dict) or set(stored) != set(_SPECIMEN_FIELDS):
            _refuse(f"specimen_identities[{index}]: malformed specimen identity.")
        reference = stored["forward_model"]
        if not isinstance(reference, str) or not reference or "\\" in reference                 or PurePosixPath(reference).is_absolute():
            _refuse(f"specimen_identities[{index}]: the forward model must be a repository-relative POSIX path.")
        try:
            current = governed_specimen_input(Path(repo_root).joinpath(*PurePosixPath(reference).parts), repo_root,
                                              fixtures)
        except CampaignDraftError as error:
            _refuse(f"specimen_identities[{index}] ({reference}): {error}")
        changed = [name for name in _SPECIMEN_FIELDS if stored[name] != getattr(current, name)]
        if changed:
            _refuse(f"specimen_identities[{index}] ({reference}): the stored {', '.join(changed)} differ(s) from the "
                    "current governed records; the selection is refused (never substituted).")
        draft = draft.with_specimen(current)
    if document["intended_campaign_definition"] != draft.intended_definition():
        _refuse("conflicting draft: the stored preview does not match its declarations and specimen identities.")
    return draft


def load_draft(path, repo_root: Path, fixtures: ExperimentFixtureManifest) -> CampaignDraft:
    """Open a saved campaign draft file and rebuild it (``draft_from_document``)."""

    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CampaignDraftError(f"{path} cannot be read as a JSON document: {error}") from error
    return draft_from_document(document, repo_root, fixtures)


# ----------------------------------------------------------------------------- input availability (M8-D2b)

CHECK_NOTE = ("factual input availability only, not a scientific readiness verdict: PRESENT_SHA256_NOT_VERIFIED means "
              "found with its pinned size, SHA-256 not verified here; readiness is judged by the shared backend on the "
              "Data Readiness Check page")


@dataclass(frozen=True)
class DraftInputCheck:
    """Rows (specimen, section, item, status, explanation) and refusals of one explicit check of one draft."""

    rows: tuple[tuple[str, str, str, str, str], ...]
    refusals: tuple[str, ...]

    def summary(self) -> str:
        if self.refusals:
            return "Input check refused: " + "; ".join(self.refusals)
        counts: dict[str, int] = {}
        for row in self.rows:
            counts[row[3]] = counts.get(row[3], 0) + 1
        specimens = len({row[0] for row in self.rows})
        return (f"Checked {specimens} specimen(s): " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
                + f" — {CHECK_NOTE}.")


def check_draft_inputs(draft: CampaignDraft, repo_root: Path, fixtures: ExperimentFixtureManifest,
                       roots) -> DraftInputCheck:
    """Re-verify each selected specimen and report its inputs through the M8.1 wizard checks (read-only)."""

    from .auto_id_wizard import prepare_specimen_passport  # the M8.1 factual checks, unchanged

    if not isinstance(fixtures, ExperimentFixtureManifest):
        return DraftInputCheck((), ("the governed experiment-fixture catalogue is not loaded and validated; no input "
                                    "is checked",))
    if roots is None:
        return DraftInputCheck((), ("the configured data-store roots could not be determined; no input is checked",))
    if not draft.specimens:
        return DraftInputCheck((), ("the draft selects no specimen",))
    rows = []
    for stored in draft.specimens:
        name = stored.label
        try:
            current = governed_specimen_input(Path(repo_root).joinpath(*PurePosixPath(stored.forward_model).parts),
                                              repo_root, fixtures)
        except CampaignDraftError as error:
            rows.append((name, "Identity", f"Governed specimen input {stored.forward_model}", "INVALID",
                         f"{error}; not checked further (never substituted)"))
            continue
        changed = [field for field in _SPECIMEN_FIELDS if getattr(stored, field) != getattr(current, field)]
        if changed:
            rows.append((name, "Identity", f"Governed specimen input {stored.forward_model}", "MISMATCH",
                         f"the selected {', '.join(changed)} differ(s) from the current governed records; refused, "
                         "not checked further (never substituted)"))
            continue
        rows.append((name, "Identity", f"Governed specimen input {stored.forward_model}", "PRESENT",
                     f"re-verified against the current governed records (forward model {current.forward_model_id}, "
                     f"manifest {current.forward_manifest_hash[:12]}; fixture {current.fixture_id})"))
        preparation = prepare_specimen_passport(Path(repo_root).joinpath(*PurePosixPath(current.passport).parts),
                                                repo_root, roots, fixtures)
        for item in preparation.items:
            rows.append((name, item.section, f"{item.label}: {item.value}" if item.value else item.label,
                         item.status.value, item.detail))
    return DraftInputCheck(tuple(rows), ())


# ----------------------------------------------------------------------------- writing

def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _is_draft(path: Path) -> bool:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(document, dict) and document.get("schema") in DRAFT_SCHEMAS


def check_draft_destination(destination, protected_roots: Iterable) -> Path:
    """A permitted draft destination: ``.json`` (never ``*.campaign.json``), outside every protected root."""

    if destination is None or not str(destination).strip():
        raise CampaignDraftError("no destination selected.")
    target = Path(destination).resolve()
    if target.suffix.lower() != ".json":
        raise CampaignDraftError(f"{target.name}: a campaign draft is a .json document.")
    if target.name.lower().endswith(".campaign.json"):
        raise CampaignDraftError(f"{target.name}: a draft is never saved under a campaign-definition name "
                                 "(*.campaign.json).")
    if not target.parent.is_dir():
        raise CampaignDraftError(f"the folder {target.parent} does not exist.")
    for root in protected_roots:
        if root is None:  # an undetermined protected root is never ignored
            raise CampaignDraftError("a protected root could not be determined; nothing is written.")
        if _inside(target, Path(root).resolve()):
            raise CampaignDraftError(f"{target} is inside the protected {Path(root)} (repository, data store or "
                                     "selected source); drafts are written elsewhere.")
    if target.exists() and (not target.is_file() or not _is_draft(target)):
        raise CampaignDraftError(f"{target} exists and is not an earlier campaign draft; it is never overwritten.")
    return target


def write_draft(draft: CampaignDraft, destination, protected_roots: Iterable) -> Path:
    """Write the draft document atomically (temporary file in the same folder, then ``os.replace``)."""

    target = check_draft_destination(destination, protected_roots)
    data = draft.document_bytes()
    temporary = None
    try:
        handle, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".partial", dir=target.parent)
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except BaseException as error:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass
        if isinstance(error, Exception):
            raise CampaignDraftError(f"{target}: {error}") from error
        raise
    return target
