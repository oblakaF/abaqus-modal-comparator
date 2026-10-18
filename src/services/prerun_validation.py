"""Pre-run Validation of a campaign definition file — Auto-ID M8-D2g (records only; nothing is run or authorised).

Six separate sections, each with the status of the existing service that judges it; nothing is turned into a PASS:

- **Definition** — ``load_campaign_definition`` (the governed parser): formally valid SPEC v1.2 or refused;
- **Sources** — the definition is reproduced from the current governed records (``draft_from_definition``: governed
  binder, bound governed records, accepted observations, declared configuration with its repository checks) and must
  give the same campaign hash; each pinned external file (experimental modal source, FE input, reference ODB, FE
  geometry, forward-model INP) is resolved with its SHA-256 verified (``resolve_external_file``);
- **Observations** — the accepted FIT / HOLDOUT rows and registrations, and the SPEC v1.2 §8 counting conditions
  (counting only);
- **Numerical evidence** — sensitivity, practical rank, leave-one-FIT-family-out, family consistency, Σ_meas, as the
  preparation review reports them (NOT_ASSESSED / NOT_AVAILABLE stay so);
- **Scientific readiness** — the scientific result is not evaluated by this check (NOT_EVALUATED: no run journal is
  looked up or judged here); a calibration question is BLOCKED; the history of the same specimens is shown unchanged;
- **Execution authorisation** — always NOT_AUTHORISED here: a definition carries no authorisation, its decision and
  provenance text is never one, and execution needs its own HUMAN gate.

Nothing here runs Abaqus, FE or LM, and nothing is written.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
from typing import Mapping, Optional

from domain.campaign_definition import (
    CAMPAIGN_SCHEMA_V1_2,
    CalibrationNotImplementedRefusal,
    CampaignDefinitionError,
    RUN_A,
    load_campaign_definition,
    parse_campaign_definition,
)
from domain.experiment_fixture import (
    ExperimentFixtureManifest,
    FixtureSourceMismatchError,
    FixtureSourceUnavailableError,
    resolve_external_file,
)
from domain.forward_model_manifest import load_forward_model_manifest
from domain.specimen_manifest import load_specimen_manifest

from .campaign_configuration import configuration_problems
from .campaign_draft import (
    BOUND,
    CONFIGURATION_GROUPS,
    CampaignDraft,
    CampaignDraftError,
    bind_draft_observations,
    bind_specimen_records,
    draft_declared_from_definition,
    governed_specimen_input,
)
from .campaign_observations import draft_preparation_review

SECTIONS = ("Definition", "Sources", "Observations", "Numerical evidence", "Scientific readiness",
            "Execution authorisation")
NOT_AUTHORISED = "NOT_AUTHORISED"
NOT_EVALUATED = "NOT_EVALUATED"
OVERALL = "NOT_AUTHORISED_FOR_EXECUTION"
DEFINITION_SOURCE = "from the campaign definition file (re-validated)"


@dataclass(frozen=True)
class PrerunValidation:
    path: str
    rows: tuple[tuple[str, str, str, str], ...]
    sections: Mapping[str, str]
    campaign_hash: Optional[str]

    @property
    def overall(self) -> str:
        return OVERALL

    def summary(self) -> str:
        parts = "; ".join(f"{name}: {self.sections.get(name, NOT_EVALUATED)}" for name in SECTIONS)
        return (f"Pre-run Validation of {self.path}: {OVERALL}. {parts}. A complete, valid definition is not "
                "identifiability and not an execution authorisation (HUMAN gate required).")


def draft_from_definition(data, repo_root: Path, fixtures: ExperimentFixtureManifest) -> CampaignDraft:
    """The campaign draft the current governed records give for this definition; refused unless it reproduces the
    definition exactly (same canonical form, hence the same campaign hash)."""

    root = Path(repo_root).resolve()
    try:
        definition = parse_campaign_definition(data)
    except CampaignDefinitionError as error:
        raise CampaignDraftError(f"not a valid campaign definition: {error}") from error
    if definition.schema != CAMPAIGN_SCHEMA_V1_2:
        raise CampaignDraftError(f"schema {definition.schema}: only SPEC v1.2 definitions "
                                 f"({CAMPAIGN_SCHEMA_V1_2}) are prepared by Auto-ID campaign drafts.")
    draft = draft_declared_from_definition(definition)
    for specimen in data["specimens"]:
        draft = draft.with_specimen(governed_specimen_input(root.joinpath(*PurePosixPath(specimen["forward_model"])
                                                                          .parts), root, fixtures))
    draft, records = bind_specimen_records(draft, root, fixtures)
    refused = [o.summary() for o in records if o.status != BOUND]
    if refused:
        raise CampaignDraftError("governed specimen records: " + " | ".join(refused))
    draft, observations = bind_draft_observations(draft, root, fixtures)
    refused = [o.summary() for o in observations if o.status != BOUND]
    if refused:
        raise CampaignDraftError("accepted observations: " + " | ".join(refused))
    for group, keys in CONFIGURATION_GROUPS.items():
        draft = draft.with_configuration(group, {key: data[key] for key in keys}, DEFINITION_SOURCE)
    if definition.run_type == RUN_A and definition.run_b_gate is None:
        draft = draft.with_run_b_gate_none()
    problems = configuration_problems(draft, root)
    if problems:
        raise CampaignDraftError("configuration: " + "; ".join(problems))
    try:
        reproduced = parse_campaign_definition(draft.intended_definition())
    except CampaignDefinitionError as error:
        raise CampaignDraftError(f"the governed records do not reproduce a complete definition: {error}") from error
    if reproduced.canonical != definition.canonical:
        differing = sorted(key for key in definition.canonical
                           if reproduced.canonical.get(key) != definition.canonical.get(key))
        raise CampaignDraftError(f"the definition differs from what the current governed records give in {differing} "
                                 "(never substituted).")
    return draft


def _source_rows(draft: CampaignDraft, root: Path, fixtures: ExperimentFixtureManifest, roots) -> list:
    rows = []
    for item in draft.specimens:
        fixture = fixtures.fixture(item.fixture_id)
        passport = load_specimen_manifest(root.joinpath(*PurePosixPath(item.passport).parts))
        manifest = load_forward_model_manifest(root.joinpath(*PurePosixPath(item.forward_model).parts))
        for label, reference in (("Experimental modal source", fixture.experimental_source),
                                 ("FE model input", fixture.fe.model_input), ("Reference ODB", fixture.fe.odb_reference),
                                 ("FE geometry file", passport.fe_reference.geometry_file),
                                 ("Forward-model INP", manifest.model_input)):
            detail = f"{reference.file_name} (store {reference.location.store}; SHA-256 {reference.sha256[:12]})"
            if roots is None:
                rows.append(("Sources", f"{item.label} {label}", detail + "; data stores not configured",
                             "NOT_CONFIGURED"))
                continue
            try:
                resolve_external_file(reference, roots, verify_sha256=True)
            except FixtureSourceUnavailableError as error:
                status = "NOT_CONFIGURED" if reference.location.store not in roots else "NOT_FOUND"
                rows.append(("Sources", f"{item.label} {label}", f"{detail}; {error}", status))
            except FixtureSourceMismatchError as error:
                rows.append(("Sources", f"{item.label} {label}", f"{detail}; {error}", "MISMATCH"))
            else:
                rows.append(("Sources", f"{item.label} {label}", detail + "; SHA-256 verified now",
                             "SHA256_VERIFIED"))
    return rows


def prerun_validation(path, repo_root: Path, fixtures: ExperimentFixtureManifest, roots) -> PrerunValidation:
    """The six-section pre-run validation of one campaign definition file (read-only)."""

    root, rows, sections = Path(repo_root).resolve(), [], {}
    try:
        definition = load_campaign_definition(path)
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, CampaignDefinitionError) as error:
        rows.append(("Definition", "load_campaign_definition", f"refused: {error}", "INVALID"))
        sections["Definition"] = "INVALID"
        return _finish(path, rows, sections, None)
    v12 = definition.schema == CAMPAIGN_SCHEMA_V1_2
    rows.append(("Definition", "load_campaign_definition",
                 f"{definition.campaign_id}: {definition.schema}; {definition.scientific_question}; {definition.run_type}; "
                 f"campaign hash {definition.campaign_hash}", "FORMALLY_VALID" if v12 else "HISTORICAL_V1_SCHEMA"))
    sections["Definition"] = "FORMALLY_VALID" if v12 else "HISTORICAL_V1_SCHEMA"
    try:
        draft = draft_from_definition(data, root, fixtures)
    except (CampaignDraftError, CampaignDefinitionError, KeyError, ValueError, OSError) as error:
        rows.append(("Sources", "Governed records reproduce the definition", str(error), "MISMATCH"))
        sections["Sources"] = "MISMATCH"
        return _finish(path, rows, sections, definition)
    rows.append(("Sources", "Governed records reproduce the definition",
                 "specimen identities, bound records, accepted rows, configuration and archive plan give the same "
                 "campaign hash", "IDENTITIES_MATCH"))
    files = _source_rows(draft, root, fixtures, roots)
    rows.extend(files)
    statuses = {row[3] for row in files}
    sections["Sources"] = ("MISMATCH" if statuses & {"MISMATCH", "NOT_FOUND"} else
                           "SHA256_VERIFIED" if statuses == {"SHA256_VERIFIED"} else "NOT_VERIFIED")

    review = draft_preparation_review(draft, root, fixtures)
    for item in draft.specimens:
        observations = draft.specimen_observations(item.forward_model)
        rows.append(("Observations", f"{item.label} accepted rows",
                     ", ".join(f"{r.row_id} {r.experimental_mode}↔{r.fe_mode} {r.role} ({r.family}, MAC {r.mac:.3f})"
                               for r in observations.rows)
                     + f"; {observations.registration_label} {observations.registration_hash[:12]}", "ACCEPTED_ROWS"))
    counts = [row for row in review.rows if row[0] == "§8 count"]
    for row in counts:
        rows.append(("Observations", f"§8 count {row[1]}", row[2], row[3]))
    deciding = [row for row in counts if row[1].startswith("pooled")] or counts
    sections["Observations"] = ("COUNT_CONDITIONS_MET" if deciding and all(r[3] == "COUNT_CONDITIONS_MET"
                                                                          for r in deciding)
                                else "COUNT_CONDITIONS_NOT_MET")
    for row in review.rows:
        if row[0] == "§8 count k = 9 (diagnostic)" and row[1] == "Nine-constant identification":
            rows.append(("Numerical evidence", row[1], row[2], row[3]))
        if row[0] == "Numerical identifiability":
            rows.append(("Numerical evidence", row[1], row[2], row[3]))
    sections["Numerical evidence"] = "NOT_ASSESSED"

    try:
        definition.require_question_supported()
    except CalibrationNotImplementedRefusal as refusal:
        rows.append(("Scientific readiness", "Scientific question", str(refusal), "BLOCKED"))
        sections["Scientific readiness"] = "BLOCKED"
    else:
        rows.append(("Scientific readiness", "Scientific verdict",
                     "not evaluated by this check: no run journal is looked up or judged here (the scientific backend "
                     "judges journalled runs); no verdict, nothing identified or released", NOT_EVALUATED))
        sections["Scientific readiness"] = NOT_EVALUATED
    for row in review.rows:
        if row[0] == "History":
            rows.append(("Scientific readiness", row[1], row[2], row[3]))

    # The execution gate itself (CampaignDefinition.require_executable) belongs to the execution path only; it is never
    # called, wrapped or lifted here. The RUN_B gate is shown as the definition records it.
    gate = ("RUN_A: the definition carries no RUN_B gate" if definition.run_type == RUN_A else
            f"RUN_B: run_b_gate {definition.run_b_gate!r} as recorded (the SUPERVISOR's gate; never set by a draft)")
    rows.append(("Execution authorisation", "Run-type gate (as recorded)", gate, "RECORDED"))
    rows.append(("Execution authorisation", "Authorisation",
                 f"none: a campaign definition carries no execution authorisation; its decision "
                 f"{definition.decision!r} and provenance are text, never an authorisation; execution needs its own "
                 "HUMAN gate; production calibration stays BLOCKED / NOT_AUTHORISED", NOT_AUTHORISED))
    sections["Execution authorisation"] = NOT_AUTHORISED
    return _finish(path, rows, sections, definition)


def _finish(path, rows, sections, definition) -> PrerunValidation:
    for name in SECTIONS:
        if name not in sections:
            sections[name] = NOT_EVALUATED
            rows.append((name, "not evaluated", "an earlier section refused the definition", NOT_EVALUATED))
    sections["Execution authorisation"] = NOT_AUTHORISED
    ordered = sorted(rows, key=lambda row: SECTIONS.index(row[0]))
    return PrerunValidation(str(path), tuple(ordered), dict(sections),
                            None if definition is None else definition.campaign_hash)
