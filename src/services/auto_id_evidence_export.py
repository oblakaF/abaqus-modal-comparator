"""Governed Auto-ID evidence export — Auto-ID M8.8 (read-only report of an already judged stored run).

An *export snapshot*: a deterministic, report-only JSON wrapper around the shared backend's readiness record of the
current typed evaluation.  It is not a scientific verdict, not a new normative evidence schema and never an accepted
scientific evidence record; the scientific content is the backend's own output, unchanged:

- ``scientific_evidence.backend_record`` is exactly ``ScientificReadiness.to_dict`` of the current typed evaluation,
  with its ``record_hash``; for material identification the backend's formal campaign report (``material_report``)
  with its canonical hash; for a RELEASED specimen calibration the governed Engineering Constants and the calibration
  material fragment of the accepted M8.6 preview, labelled a non-production preview (never an INP file);
- ``verified_identities``: the campaign and run identity, every specimen's recorded governed identity and governed
  pipeline run hash, and the evidence fingerprint — all re-verified from disk immediately before the snapshot is built;
- ``presentation``: the accepted M8.5 verdict summary and M8.7 uncertainty / source breakdown of the same record.

Freshness (fail-closed): the export requires an explicitly selected governed campaign and existing run, the current
typed evaluation bound to the displayed record, governed specimen inputs, and a journal fingerprint recomputed *now*
(``run_progress.inspect_run_progress``: campaign journal + every governed pipeline journal) that is not ``None`` and
equals the fingerprint stored when the run was evaluated.  Anything else refuses; the run is never evaluated again
here.  Nothing is computed scientifically: no constant, uncertainty, verdict or hash of the evidence is derived except
the accepted canonical hashes of the records themselves.

Writing (``write_export``) happens only on an explicit user action, to a ``.json`` destination outside the repository,
the data stores and the selected run, never over a file that is not an earlier Auto-ID export; the document is created
atomically (temporary file in the destination folder, then ``os.replace``), and nothing is left behind on failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import os
from pathlib import Path
import tempfile
from typing import Iterable, Mapping, Optional, Sequence

from domain.campaign_definition import CampaignDefinition
from domain.identification_run import canonical_hash

from .auto_id_wizard import uncertainty_breakdown, verdict_summary
from .calibration_material_preview import PreviewState, calibration_material_preview
from .campaign_scientific_backend import ReadinessStatus, ScientificReadiness
from .identification_campaign_run import CampaignSpecimenInput
from .run_progress import inspect_run_progress
from .stored_run_evidence import StoredRunEvaluation, governed_pipeline_directory

EXPORT_SCHEMA = "auto-id/evidence-export-snapshot/v1"
EXPORT_KIND = "EXPORT_SNAPSHOT"
EXPORT_NOTE = ("Report-only export snapshot of an already judged stored run: not a scientific verdict, not a new "
               "normative evidence schema and not an accepted scientific evidence record. The scientific content is "
               "the shared backend's own output (scientific_evidence), unchanged; presentation and export metadata "
               "are kept separate.")
VERIFICATION = "VERIFIED_FRESH_AT_EXPORT"
FRAGMENT_LABELS = ("GOVERNED_NON_PRODUCTION_PREVIEW", "NOT_AN_INP_FILE", "NEVER_ATTACHED_TO_A_PRODUCTION_MODEL")


class ExportRefusalCode(str, Enum):
    NO_CAMPAIGN = "NO_GOVERNED_CAMPAIGN_SELECTED"
    NO_RUN = "NO_STORED_RUN_SELECTED"
    NOT_EVALUATED = "NO_CURRENT_TYPED_EVALUATION"
    RECORD_BINDING = "DISPLAYED_RECORD_NOT_THE_EVALUATED_RECORD"
    RUN_MISMATCH = "RUN_OR_CAMPAIGN_MISMATCH"
    SPECIMENS_UNAVAILABLE = "GOVERNED_SPECIMEN_INPUTS_UNAVAILABLE"
    NOT_VERIFIED = "EVIDENCE_NOT_VERIFIED_AT_EXPORT"
    STALE = "EVIDENCE_CHANGED_SINCE_EVALUATION"
    DESTINATION = "DESTINATION_REFUSED"
    WRITE_FAILED = "WRITE_FAILED"


class ExportRefusal(ValueError):
    """No verified export; nothing is written."""

    def __init__(self, code: ExportRefusalCode, message: str) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code


@dataclass(frozen=True)
class EvidenceExport:
    snapshot: Mapping
    content_hash: str

    def document(self) -> bytes:
        """The deterministic JSON document (sorted keys, no timestamps, no random identifiers)."""
        return (json.dumps(self.snapshot, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
                + "\n").encode("utf-8")


def _refuse(code: ExportRefusalCode, message: str):
    raise ExportRefusal(code, message)


def _calibration(readiness: ScientificReadiness, evaluation: StoredRunEvaluation) -> Optional[dict]:
    if readiness.status is not ReadinessStatus.RELEASED:
        return None
    preview = calibration_material_preview(readiness, evaluation.source_inps)
    if preview.state is not PreviewState.AVAILABLE:
        return {"status": preview.state.value, "reason": preview.reason}
    fragment = preview.fragment
    return {
        "status": preview.state.value,
        "labels": list(preview.labels),
        "evidence": list(preview.evidence),
        "engineering_constants": [{"name": r.name, "value": r.value, "unit": r.unit, "origin": r.origin.value,
                                   "provenance": r.provenance} for r in preview.constants],
        "material_fragment": {
            "labels": list(FRAGMENT_LABELS),
            "material_name": fragment.material_name,
            "production_material_name": preview.production_material_name,
            "source_inp_sha256": fragment.source_inp_sha256,
            "source_material_block_sha256": fragment.source_material_block_sha256,
            "source_calibration_record_hash": fragment.source_calibration_record_hash,
            "gate_record_hash": fragment.gate_record_hash,
            "content_sha256": fragment.content_sha256,
            "content_lines": fragment.content.splitlines(),
        },
    }


def build_evidence_export(definition, journal_path, specimens: Optional[Sequence[CampaignSpecimenInput]],
                          evaluation, displayed_record, evaluated_fingerprint) -> EvidenceExport:
    """The verified export snapshot of the current typed evaluation, built in memory (nothing is written).

    The campaign journal and every governed pipeline journal are re-verified from disk *now*; the export refuses when
    the evidence is incomplete, unverified or changed since the evaluation.  Never evaluates the run again.
    """

    if not isinstance(definition, CampaignDefinition):
        _refuse(ExportRefusalCode.NO_CAMPAIGN, "select a governed family / campaign definition (a specimen folder "
                                               "declares no campaign).")
    if journal_path is None or not str(journal_path).strip():
        _refuse(ExportRefusalCode.NO_RUN, "select the journal of an existing run of this campaign.")
    if not isinstance(evaluation, StoredRunEvaluation) or not isinstance(evaluation.readiness, ScientificReadiness):
        _refuse(ExportRefusalCode.NOT_EVALUATED, "evaluate the selected stored run first (Auto-ID — Evaluate Stored "
                                                 "Run); a stored or display-only record is never exported as verified.")
    readiness = evaluation.readiness
    record = readiness.to_dict()
    if not isinstance(displayed_record, Mapping) or dict(displayed_record) != record:
        _refuse(ExportRefusalCode.RECORD_BINDING, "the record shown is not the current typed evaluation's record.")
    if Path(str(evaluation.run.journal_path)) != Path(str(journal_path)) \
            or evaluation.run.campaign_hash != definition.campaign_hash \
            or (record.get("campaign") or {}).get("campaign_hash") != definition.campaign_hash:
        _refuse(ExportRefusalCode.RUN_MISMATCH, "the evaluated run is not the selected run of the selected campaign.")
    if specimens is None:
        _refuse(ExportRefusalCode.SPECIMENS_UNAVAILABLE, "the campaign's governed specimen inputs are unavailable, so "
                                                         "the pipeline journals cannot be verified.")
    specimens = tuple(specimens)
    progress = inspect_run_progress(definition, journal_path, specimens)  # fresh from disk, immediately before export
    if progress.fingerprint != evaluated_fingerprint or progress.run_hash != evaluation.run.run_hash:
        _refuse(ExportRefusalCode.STALE, "the campaign or a governed pipeline journal changed (or is no longer "
                                         "verified) since the evaluation; evaluate the selected stored run again "
                                         "before exporting.")
    if progress.fingerprint is None:  # unverifiable then and now: the evaluation itself stays as judged
        reasons = "; ".join(progress.problems) or "the journals are not fully verified"
        _refuse(ExportRefusalCode.NOT_VERIFIED, f"freshness cannot be established ({reasons}); a verified export "
                                                "needs the campaign journal and every governed pipeline journal.")

    run = evaluation.run
    recorded = {entry.get("label"): entry for entry in run.campaign_journal["run_identity"]["specimens"]
                if isinstance(entry, Mapping)}
    governed = []
    for item in specimens:
        directory = governed_pipeline_directory(definition, item, run)
        governed.append({"label": item.label, "recorded_run_identity": recorded.get(item.label),
                         "governed_pipeline_run_hash": directory.name,
                         "governed_pipeline_journal": directory.relative_to(run.run_root).as_posix() + "/journal.json"})
    report = readiness.material_report
    scientific = {
        "backend_record": record,
        "backend_record_hash": readiness.record_hash,
        "backend_material_report": report,
        "backend_material_report_hash": None if report is None else canonical_hash(report),
        "released_specimen_calibration": _calibration(readiness, evaluation),
    }
    snapshot = {
        "export": {"schema": EXPORT_SCHEMA, "kind": EXPORT_KIND, "note": EXPORT_NOTE, "verification": VERIFICATION,
                   "freshness": "campaign journal and every governed pipeline journal re-verified from disk at export; "
                                "fingerprint equal to the one stored for the evaluation"},
        "verified_identities": {
            "campaign_id": definition.campaign_id, "campaign_hash": definition.campaign_hash,
            "run_type": definition.run_type, "run_hash": run.run_hash, "evidence_fingerprint": progress.fingerprint,
            "specimens": governed,
        },
        "scientific_evidence": scientific,
        "presentation": {"verdict_summary": list(verdict_summary(record)),
                         "uncertainty_breakdown": [list(row) for row in uncertainty_breakdown(record, report)],
                         "loading_notes": list(evaluation.notes)},
        "production": {"execution": record.get("production_execution"),
                       "calibration": record.get("production_calibration")},
    }
    snapshot = json.loads(json.dumps(snapshot, sort_keys=True, ensure_ascii=False, allow_nan=False))
    content_hash = canonical_hash(snapshot)
    return EvidenceExport(dict(snapshot, content_hash=content_hash), content_hash)


# ----------------------------------------------------------------------------- writing

def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _is_export(path: Path) -> bool:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(document, Mapping) and isinstance(document.get("export"), Mapping) \
        and document["export"].get("schema") == EXPORT_SCHEMA


def check_destination(destination, protected_roots: Iterable) -> Path:
    """A permitted export destination: a ``.json`` file outside every protected root, never over another file."""

    if destination is None or not str(destination).strip():
        _refuse(ExportRefusalCode.DESTINATION, "no destination selected.")
    target = Path(destination).resolve()
    if target.suffix.lower() != ".json":
        _refuse(ExportRefusalCode.DESTINATION, f"{target.name}: an Auto-ID evidence export is a .json document.")
    if not target.parent.is_dir():
        _refuse(ExportRefusalCode.DESTINATION, f"the folder {target.parent} does not exist.")
    for root in protected_roots:
        if root is not None and _inside(target, Path(root).resolve()):
            _refuse(ExportRefusalCode.DESTINATION, f"{target} is inside the protected {Path(root)} (repository, data "
                                                   "store or selected run); exports are written elsewhere.")
    if target.exists() and (not target.is_file() or not _is_export(target)):
        _refuse(ExportRefusalCode.DESTINATION, f"{target} exists and is not an earlier Auto-ID evidence export; it is "
                                               "never overwritten.")
    return target


def write_export(export: EvidenceExport, destination, protected_roots: Iterable) -> Path:
    """Write the document atomically (temporary file in the same folder, then ``os.replace``); nothing on failure."""

    target = check_destination(destination, protected_roots)
    data = export.document()
    handle, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".partial", dir=target.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except BaseException as error:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        if isinstance(error, Exception):
            raise ExportRefusal(ExportRefusalCode.WRITE_FAILED, f"{target}: {error}") from error
        raise
    return target
