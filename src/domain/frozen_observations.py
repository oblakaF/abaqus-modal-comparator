"""Frozen baseline observation set — Auto-ID M4.2 (SPEC §6 S3, §12.1; D-008).

The observation rows of an identification are decided once, at the baseline (reference
parameters p0), under an explicit strict ``IdentificationPairingPolicy`` and frozen.
Later candidates never add or drop rows; they are followed by FE-to-FE branch tracking.

A set is ``FROZEN`` only when the baseline pairing is final (complete evidence,
unambiguous, sufficient coverage).  Otherwise it is ``NOT_FROZEN``: its provisional rows
are reported for review but cannot be used for identification.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json


FROZEN_OBSERVATION_SCHEMA = "auto-id/frozen-observations/v1"


class FreezeStatus(str, Enum):
    FROZEN = "FROZEN"
    NOT_FROZEN = "NOT_FROZEN"


class ObservationFreezeRefusal(Exception):
    """The baseline observation set is not frozen; identification must not proceed.

    Not a ValueError/RuntimeError, so generic fallback handlers never swallow it.
    """

    def __init__(self, reasons: tuple[str, ...]) -> None:
        super().__init__("baseline observations are not frozen: " + "; ".join(reasons))
        self.reasons = reasons


@dataclass(frozen=True)
class BaselineIdentity:
    """What the baseline observations were taken from (content identities, no paths)."""

    forward_model_id: str
    job_name: str  # M3 content-addressed job name of the baseline forward job
    generated_inp_sha256: str
    fe_geometry_sha256: str
    registration_hash: str
    experimental_source_sha256: str
    modal_set: str
    measured_dofs: tuple[str, ...]
    evidence_source: str  # for example "archived-carbon4c-replay"
    evidence_record_sha256: str | None
    shape_pack_content_sha256: str | None = None  # FE shapes behind a complete MAC matrix (validated pack)


@dataclass(frozen=True)
class ObservationRow:
    row_id: str
    experimental_mode: int
    experimental_hz: float
    fe_mode: int  # FE mode number at the baseline; later candidates are tracked from it
    fe_hz: float
    mac: float
    relative_frequency_error: float


@dataclass(frozen=True)
class ExcludedObservation:
    experimental_mode: int
    reason: str


@dataclass(frozen=True)
class FrozenObservationSet:
    identity: BaselineIdentity
    policy_id: str
    policy_hash: str
    status: FreezeStatus
    reasons: tuple[str, ...]
    rows: tuple[ObservationRow, ...]  # empty unless FROZEN
    provisional_rows: tuple[ObservationRow, ...]  # what the strict pairing found; for review only
    excluded: tuple[ExcludedObservation, ...]
    unknown_mac_entries: tuple[tuple[int, int], ...]

    def to_dict(self) -> dict:
        document = asdict(self)
        document["schema"] = FROZEN_OBSERVATION_SCHEMA
        document["status"] = self.status.value
        return document

    @property
    def observation_hash(self) -> str:
        encoded = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @property
    def frozen(self) -> bool:
        return self.status is FreezeStatus.FROZEN

    def require_frozen(self) -> "FrozenObservationSet":
        if not self.frozen:
            raise ObservationFreezeRefusal(self.reasons)
        return self

    def row(self, row_id: str) -> ObservationRow:
        for row in self.rows:
            if row.row_id == row_id:
                return row
        raise KeyError(row_id)
