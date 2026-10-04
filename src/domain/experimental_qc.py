"""Experimental QC report (Auto-ID M1.4).

QC observes and reports; it never modifies, repairs, reorders or deletes modal data.
Each check returns PASS / WARNING / FAIL / NOT_AVAILABLE with metrics and warnings.

Only *hard* checks can FAIL, and only for broken provenance, invalid fixture identity
or an invalid measurement contract.  Quality concerns are WARNING (diagnostic) and
use only flag rules written in the SPEC; no universal threshold is invented here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
from typing import Any


QC_POLICY_VERSION = "experimental-qc/1"


class ExperimentalQCStatus(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    NOT_AVAILABLE = "NOT_AVAILABLE"


@dataclass(frozen=True)
class ExperimentalQCMetric:
    name: str
    value: float | int | str | None  # None means NOT_AVAILABLE
    unit: str = ""
    mode: int | None = None
    note: str = ""

    @property
    def available(self) -> bool:
        return self.value is not None

    def to_dict(self) -> dict[str, Any]:
        value = self.value
        if isinstance(value, float) and not math.isfinite(value):
            value = None
        return {"name": self.name, "value": value, "unit": self.unit, "mode": self.mode,
                "available": value is not None, "note": self.note}


@dataclass(frozen=True)
class QCWarning:
    code: str
    message: str
    check: str
    modes: tuple[int, ...] = ()
    rule: str = ""  # where the flag rule comes from (e.g. "SPEC §6 S1")

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "check": self.check, "modes": list(self.modes),
                "rule": self.rule}


@dataclass(frozen=True)
class ExperimentalQCCheck:
    name: str
    status: ExperimentalQCStatus
    hard: bool  # True: a FAIL is a refusal condition (provenance / fixture identity / contract)
    summary: str
    metrics: tuple[ExperimentalQCMetric, ...] = ()
    warnings: tuple[QCWarning, ...] = ()
    failures: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status is ExperimentalQCStatus.FAIL and not self.hard:
            raise ValueError(f"QC check {self.name!r} is diagnostic and cannot FAIL; report a WARNING instead.")

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status.value, "hard": self.hard, "summary": self.summary,
                "failures": list(self.failures), "warnings": [item.to_dict() for item in self.warnings],
                "metrics": [item.to_dict() for item in self.metrics]}


def overall_status(checks: tuple[ExperimentalQCCheck, ...]) -> ExperimentalQCStatus:
    """FAIL if a hard check failed; WARNING if any check warned; otherwise PASS.

    NOT_AVAILABLE checks do not degrade the overall status; they are listed in the
    report's ``not_available`` field instead.
    """
    statuses = [check.status for check in checks]
    if ExperimentalQCStatus.FAIL in statuses:
        return ExperimentalQCStatus.FAIL
    if ExperimentalQCStatus.WARNING in statuses:
        return ExperimentalQCStatus.WARNING
    return ExperimentalQCStatus.PASS


@dataclass(frozen=True)
class ExperimentalQCReport:
    fixture_id: str
    modal_source: str
    provider: dict[str, str]
    provenance_reference: dict[str, str]
    checks: tuple[ExperimentalQCCheck, ...]
    policy: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> ExperimentalQCStatus:
        return overall_status(self.checks)

    @property
    def admissible(self) -> bool:
        """False only when a hard check failed; diagnostic warnings never block."""
        return self.status is not ExperimentalQCStatus.FAIL

    @property
    def warnings(self) -> tuple[QCWarning, ...]:
        return tuple(item for check in self.checks for item in check.warnings)

    @property
    def metrics(self) -> tuple[ExperimentalQCMetric, ...]:
        return tuple(item for check in self.checks for item in check.metrics)

    @property
    def not_available(self) -> tuple[str, ...]:
        names = [f"check:{check.name}" for check in self.checks if check.status is ExperimentalQCStatus.NOT_AVAILABLE]
        seen = set()
        for metric in self.metrics:
            if not metric.available and metric.name not in seen:
                seen.add(metric.name)
                names.append(f"metric:{metric.name}")
        return tuple(names)

    def check(self, name: str) -> ExperimentalQCCheck:
        for item in self.checks:
            if item.name == name:
                return item
        raise KeyError(name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": dict(self.policy, version=QC_POLICY_VERSION),
            "fixture_id": self.fixture_id,
            "modal_source": self.modal_source,
            "provider": dict(self.provider),
            "provenance_reference": dict(self.provenance_reference),
            "status": self.status.value,
            "admissible": self.admissible,
            "not_available": list(self.not_available),
            "checks": [check.to_dict() for check in self.checks],
        }

    @property
    def content_hash(self) -> str:
        encoded = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TrustedSuspensionThreshold:
    """A physically documented suspension threshold (SPEC §6 S1, §19 item 5).

    It is a specimen / test-run property from the M2 passport or acquisition record.
    It is never derived from modal frequencies, FE results or existing modal sets, and
    there is no default value.
    """

    suspension_max_hz: float
    source: str  # where the physical value is documented

    def __post_init__(self) -> None:
        value = self.suspension_max_hz
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0.0:
            raise ValueError("suspension_max_hz must be a finite positive frequency in Hz.")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("a trusted suspension threshold must name its documented physical source.")


class ExperimentalModeEligibilityRefusal(Exception):
    """A mode below the trusted suspension threshold was requested for material identification.

    Not a ValueError/RuntimeError, so generic fallback handlers never swallow it.
    """

    def __init__(self, modes: tuple[int, ...], threshold: TrustedSuspensionThreshold) -> None:
        super().__init__(
            f"modes {list(modes)} lie below the trusted suspension threshold "
            f"{threshold.suspension_max_hz:g} Hz ({threshold.source}) and must not enter material "
            "identification (SPEC §6 S1)."
        )
        self.modes = modes
        self.threshold = threshold


@dataclass(frozen=True)
class ExperimentalModeEligibility:
    """Which modes may enter material identification; kept apart from the QC report.

    ``NOT_AVAILABLE`` means no trusted suspension threshold was supplied (pending the
    M2 passport): no mode is excluded and none is guessed.
    """

    status: ExperimentalQCStatus  # PASS (threshold applied) or NOT_AVAILABLE
    threshold: TrustedSuspensionThreshold | None
    eligible_modes: tuple[int, ...]
    excluded_modes: tuple[int, ...]  # strictly below the trusted threshold

    @property
    def suspension_verified(self) -> bool:
        return self.threshold is not None

    def require_eligible(self, modes) -> None:
        requested = tuple(int(mode) for mode in modes)
        blocked = tuple(mode for mode in requested if mode in self.excluded_modes)
        if blocked:
            raise ExperimentalModeEligibilityRefusal(blocked, self.threshold)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "suspension_max_hz": None if self.threshold is None else self.threshold.suspension_max_hz,
            "threshold_source": None if self.threshold is None else self.threshold.source,
            "eligible_modes": list(self.eligible_modes),
            "excluded_modes": list(self.excluded_modes),
        }


class ExperimentalQCRefusal(Exception):
    """A hard QC check failed (broken provenance, fixture identity or measurement contract).

    Not a ValueError/RuntimeError, so generic fallback handlers never swallow it.
    """

    def __init__(self, report: ExperimentalQCReport) -> None:
        failed = [check for check in report.checks if check.status is ExperimentalQCStatus.FAIL]
        details = "; ".join(f"{check.name}: {', '.join(check.failures)}" for check in failed)
        super().__init__(f"Experimental QC refused {report.fixture_id}: {details}")
        self.report = report
