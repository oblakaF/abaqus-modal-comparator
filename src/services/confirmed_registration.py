"""UNIVERSAL-REG-3: a person's confirmation of a revalidated registration draft, and its FrozenRegistration.

A draft (``services.generic_registration``) stays diagnostic. A separate confirmation file records who confirmed which
physical statements about exactly which experimental source, modal set, FE geometry and evidence. Reopening or using it
never trusts the file: its content hash and bindings are checked, the embedded draft is revalidated against the current
data, and the registration is built again and must have the recorded hash.

A confirmation records a statement. It does not prove that the statement is physically correct, is not governed
evidence, adds no Auto-ID observation and does not approve the draft's provisional heuristics. The FrozenRegistration
exists so that the existing comparator can apply this geometry; its orientation comes only from the stated evidence,
and nothing here reads a frequency, an FE mode shape or a MAC.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Mapping, Optional

import numpy as np

from domain.registration import FrozenRegistration, RegistrationMismatchError
from domain.specimen_manifest import canonical_hash
from reviewed_core import _explicit_measurement_mask, experimental_measurement_masks
from scientific_state import calibration_fingerprint, modal_dataset_geometry_identity

from . import generic_registration as gr

CONFIRMATION_SCHEMA = "universal/registration-confirmation/v1"
CONFIRMED_STATUS = "USER_CONFIRMED_PHYSICAL_REGISTRATION"
REGISTRATION_SOURCE = "USER_CONFIRMED_PHYSICAL_EVIDENCE"
LIMITS = ("A confirmation records a person's statement: it is not proof of physical correctness.",
          "Not governed evidence and not production-ready.",
          "The landmark extent, stated-axis and FE-node tie rules stay provisional diagnostic heuristics.")
# what the person states, one by one
STATEMENTS = (("units", "The coordinate units are those of the two files."),
              ("axes", "The experimental axes in the FE frame are physically correct."),
              ("side", "The measured side is the face that was measured."),
              ("dofs", "The measured DOFs are those that were measured."),
              ("landmarks", "The landmarks were identified independently of any modal result."),
              ("mapping", "The point mapping shown is physically correct."))
STATEMENT_KEYS = tuple(key for key, _text in STATEMENTS)
INVALID = "CONFIRMATION_INVALID"
TAMPERED = "CONFIRMATION_TAMPERED"
NOT_BOUND = "CONFIRMATION_NOT_BOUND"
_KEYS = ("schema", "status", "governed", "production_ready", "independent_verification", "limits", "confirmed_by",
         "evidence_location", "confirmed_at", "statements", "draft", "draft_sha256", "evidence_sha256",
         "registration_hash", "confirmation_sha256")


class ConfirmationRefused(ValueError):
    """A confirmation cannot be made or used; ``code`` names the reason."""

    def __init__(self, code: str, text: str) -> None:
        super().__init__(text)
        self.code = code


def _measured_contract(experimental_dataset) -> list:
    """The one measured-DOF contract of all records, as the registration factory requires it: explicit and uniform."""
    modes = list(experimental_dataset.modes)
    for mode in modes:
        if _explicit_measurement_mask(mode) is None:
            raise ConfirmationRefused(NOT_BOUND, f"Experimental record {mode.number} has no explicit measured-DOF mask; "
                                                 "a registration never stores an inferred measurement contract.")
    masks = experimental_measurement_masks(modes, np.asarray(modes[0].node_ids, dtype=object))
    if any(not np.array_equal(mask, masks[0]) for mask in masks[1:]):
        raise ConfirmationRefused(NOT_BOUND, "The measured-DOF mask differs between experimental records; one "
                                             "measurement contract per point is required.")
    return np.asarray(masks[0], dtype=bool).tolist()


def _point_id(label: str):
    return int(label) if label.lstrip("-").isdigit() else label


def build_registration(draft: Mapping, fe_dataset, experimental_dataset) -> FrozenRegistration:
    """The FrozenRegistration of a revalidated draft, from its stored values, so the hash does not vary with noise.

    The draft states x_fe = (s x_exp) R^T + t in row vectors; the comparator's geometry is x_exp = (x_fe R') s' + t':
    R' = R, s' = 1 / s and t' = -(t R) / s.
    """
    result, evidence = draft["result"], draft["evidence"]
    rotation = np.asarray(result["rotation"], dtype=float)
    translation = np.asarray(result["translation"], dtype=float)
    scale = float(result["scale"])
    calibration = {"source": REGISTRATION_SOURCE, "fe_unit": evidence["fe_unit"],
                   "experimental_unit": evidence["experimental_unit"], "scale_experimental_to_fe": scale,
                   "evidence_sha256": draft["evidence_sha256"]}
    determinant = float(np.linalg.det(rotation))
    source = draft["sources"]["experimental"]
    metrics = {"orientation_source": "user_confirmed", "determinant": determinant, "mirrored": determinant < 0.0,
               "matched_fraction": result["metrics"]["matched_fraction"],
               "normalized_rms_distance": result["metrics"]["normalized_rms"],
               "geometry_calibration": calibration}
    return FrozenRegistration.create(
        experimental_source_identity={"path": "experimental file", "size": source["size"], "mtime_ns": None,
                                      "sha256": source["sha256"]},
        experimental_modal_set_identity=draft["modal_set"]["key"],
        fe_geometry_identity=modal_dataset_geometry_identity(fe_dataset),
        calibration=calibration, calibration_fingerprint=calibration_fingerprint(calibration),
        orientation_candidate_id=f"user-confirmed:{draft['evidence_sha256']}",
        rotation=rotation.tolist(), translation=(-(translation @ rotation) / scale).tolist(),
        coordinate_scales=[1.0 / scale] * 3,
        experimental_node_ids=[_point_id(row[0]) for row in result["mapping"]],
        mapped_fe_node_ids=[row[1] for row in result["mapping"]],
        measured_dof_contract=_measured_contract(experimental_dataset), registration_metrics=metrics)


def confirmation_document(draft: Mapping, fe_dataset, experimental_dataset, *, confirmed_by: str,
                          evidence_location: str, statements, now: Optional[datetime] = None) -> dict:
    """The confirmation of a draft already revalidated on these data; every statement and the name are required."""
    missing = [key for key in STATEMENT_KEYS if key not in set(statements)]
    if missing:
        raise ConfirmationRefused(INVALID, f"These statements are not confirmed: {', '.join(missing)}.")
    if not str(confirmed_by).strip():
        raise ConfirmationRefused(INVALID, "The name of the person confirming is required.")
    if not str(evidence_location).strip():
        raise ConfirmationRefused(INVALID, "Where the physical evidence can be found is required.")
    registration = build_registration(draft, fe_dataset, experimental_dataset)
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(timespec="seconds")
    body = {"schema": CONFIRMATION_SCHEMA, "status": CONFIRMED_STATUS, "governed": False, "production_ready": False,
            "independent_verification": False, "limits": list(LIMITS), "confirmed_by": str(confirmed_by).strip(),
            "evidence_location": str(evidence_location).strip(), "confirmed_at": moment,
            "statements": list(STATEMENT_KEYS), "draft": json.loads(json.dumps(draft)),
            "draft_sha256": draft["draft_sha256"], "evidence_sha256": draft["evidence_sha256"],
            "registration_hash": registration.registration_hash}
    return dict(body, confirmation_sha256=canonical_hash(body))


def _check_structure(document: Mapping) -> None:
    if not isinstance(document, dict) or document.get("schema") != CONFIRMATION_SCHEMA:
        raise ConfirmationRefused(INVALID, f"Not a registration confirmation of the version {CONFIRMATION_SCHEMA}.")
    if set(document) != set(_KEYS):
        raise ConfirmationRefused(INVALID, "The confirmation is incomplete or altered.")
    body = {key: value for key, value in document.items() if key != "confirmation_sha256"}
    if canonical_hash(body) != document["confirmation_sha256"]:
        raise ConfirmationRefused(TAMPERED, "The confirmation's content does not match its SHA-256: it was altered.")
    if (document["status"] != CONFIRMED_STATUS or document["governed"] is not False
            or document["production_ready"] is not False or document["independent_verification"] is not False
            or document["limits"] != list(LIMITS)):
        raise ConfirmationRefused(TAMPERED, "The confirmation claims more than a confirmation may.")
    if document["statements"] != list(STATEMENT_KEYS):
        raise ConfirmationRefused(INVALID, "Not every physical statement is confirmed.")
    for key in ("confirmed_by", "evidence_location", "confirmed_at"):
        if not isinstance(document[key], str) or not document[key].strip():
            raise ConfirmationRefused(INVALID, f"The confirmation has no {key.replace('_', ' ')}.")
    draft = document["draft"]
    if not isinstance(draft, dict) or (draft.get("draft_sha256"), draft.get("evidence_sha256")) != (
            document["draft_sha256"], document["evidence_sha256"]):
        raise ConfirmationRefused(TAMPERED, "The confirmation does not name its own draft and evidence.")


@dataclass(frozen=True)
class ConfirmedRegistration:
    """A confirmation that holds now for the current data. It offers what the comparison wording reads."""

    registration: FrozenRegistration
    proposal: gr.Proposal
    evidence: gr.Evidence
    document: Mapping[str, Any]

    def provenance(self) -> dict:
        draft = self.document["draft"]
        return {"source": REGISTRATION_SOURCE, "specimen": "not recorded", "fixture_id": "not recorded",
                "registration_hash": self.registration.registration_hash, "registration_file": "user confirmation",
                "modal_set": draft["modal_set"]["key"], "fe_geometry_sha256": draft["fe_geometry_sha256"],
                "fe_node_count": self.registration.fe_geometry_identity.get("node_count"),
                "experimental_sha256": draft["sources"]["experimental"]["sha256"],
                "confirmed_by": self.document["confirmed_by"], "confirmed_at": self.document["confirmed_at"],
                "evidence_location": self.document["evidence_location"],
                "confirmation_sha256": self.document["confirmation_sha256"],
                "checks": list(self.proposal.checks), "limits": list(LIMITS), "governed": False,
                "production_ready": False, "independent_verification": False}

    def warning(self) -> str:
        return (f"Physical registration confirmed by {self.document['confirmed_by']} on "
                f"{self.document['confirmed_at']}. " + " ".join(LIMITS))


def revalidate(document: Mapping, fe_dataset, experimental_dataset, *, modal_set: Mapping,
               sources: Mapping) -> ConfirmedRegistration:
    """The confirmation checked against the current data, every time, or ``ConfirmationRefused`` with the reason."""
    _check_structure(document)
    outcome = gr.revalidate_draft(document["draft"], fe_dataset, experimental_dataset, modal_set=modal_set,
                                  sources=sources)
    if not outcome.proposal.proposed:
        reasons = " ".join(problem.text for problem in outcome.proposal.problems)
        raise ConfirmationRefused(NOT_BOUND, f"The confirmed draft does not hold for the current data: {reasons}")
    registration = build_registration(document["draft"], fe_dataset, experimental_dataset)
    if registration.registration_hash != document["registration_hash"]:
        raise ConfirmationRefused(NOT_BOUND, "The registration built now is not the confirmed registration.")
    try:
        registration.check_content_compatible({"sha256": sources["experimental"]["sha256"],
                                               "size": sources["experimental"]["size"]},
                                              modal_dataset_geometry_identity(fe_dataset))
    except RegistrationMismatchError as error:
        raise ConfirmationRefused(NOT_BOUND, str(error)) from error
    if float(np.linalg.det(np.asarray(registration.rotation))) <= 0.0:
        raise ConfirmationRefused(NOT_BOUND, "A mirrored orientation is not accepted.")
    return ConfirmedRegistration(registration, outcome.proposal, outcome.evidence, document)


__all__ = ["CONFIRMATION_SCHEMA", "CONFIRMED_STATUS", "ConfirmationRefused", "ConfirmedRegistration", "LIMITS",
           "STATEMENTS", "STATEMENT_KEYS", "build_registration", "confirmation_document", "revalidate"]
