"""Identification pairing policy — Auto-ID M4.1 (SPEC §6 S3, §12.1; AUDIT V4; D-008).

Pairing for material identification uses a named policy that is passed explicitly and
is strict by default.  It is separate from the normal comparator: the comparator's
defaults (and the Stage-A pairing provider) are not used and not changed.

Baseline gates (applied to every experimental/FE pair *before* assignment):

- MAC ≥ ``minimum_mac`` (0.80);
- |f_FE − f_EXP| / f_EXP ≤ ``maximum_relative_frequency_error`` (15 %).

Coverage: at least ``minimum_observations`` frozen rows (strict default 2, the number
of free parameters of the carbon property set v1).  After the baseline, rows are frozen
and later candidates are followed by FE-to-FE tracking with MAC ≥
``tracking_minimum_mac`` (0.90) and unique assignment.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math


IDENTIFICATION_PAIRING_POLICY_SCHEMA = "auto-id/identification-pairing-policy/v1"


class PairingPolicyError(ValueError):
    """A pairing policy is malformed."""


@dataclass(frozen=True)
class IdentificationPairingPolicy:
    policy_id: str
    minimum_mac: float
    maximum_relative_frequency_error: float
    tracking_minimum_mac: float
    minimum_observations: int
    assignment_tie_tolerance: float  # two assignments whose total MAC differs by less are a tie → refusal

    def __post_init__(self) -> None:
        if not isinstance(self.policy_id, str) or not self.policy_id.strip():
            raise PairingPolicyError("policy_id must be a non-empty name.")
        for name in ("minimum_mac", "tracking_minimum_mac"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 < value <= 1.0:
                raise PairingPolicyError(f"{name} must be in (0, 1].")
        error = self.maximum_relative_frequency_error
        if isinstance(error, bool) or not isinstance(error, (int, float)) or not math.isfinite(error) or error <= 0:
            raise PairingPolicyError("maximum_relative_frequency_error must be finite and positive.")
        count = self.minimum_observations
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise PairingPolicyError("minimum_observations must be a positive integer.")
        tie = self.assignment_tie_tolerance
        if isinstance(tie, bool) or not isinstance(tie, (int, float)) or not 0.0 <= tie < 1.0:
            raise PairingPolicyError("assignment_tie_tolerance must be in [0, 1).")

    @property
    def is_strict(self) -> bool:
        """At least as strict as SPEC §12.1 on every gate."""
        return (self.minimum_mac >= STRICT_IDENTIFICATION_PAIRING.minimum_mac
                and self.maximum_relative_frequency_error <= STRICT_IDENTIFICATION_PAIRING.maximum_relative_frequency_error
                and self.tracking_minimum_mac >= STRICT_IDENTIFICATION_PAIRING.tracking_minimum_mac
                and self.minimum_observations >= STRICT_IDENTIFICATION_PAIRING.minimum_observations)

    def to_dict(self) -> dict:
        return {"schema": IDENTIFICATION_PAIRING_POLICY_SCHEMA, **asdict(self)}

    @property
    def policy_hash(self) -> str:
        encoded = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def require_strict(self) -> "IdentificationPairingPolicy":
        if not self.is_strict:
            raise PairingPolicyError(f"Policy {self.policy_id!r} is weaker than the strict SPEC §12.1 policy.")
        return self


# SPEC §12.1 strict default.  minimum_observations = 2 = free parameters of carbon-property-set/v1.
STRICT_IDENTIFICATION_PAIRING = IdentificationPairingPolicy(
    policy_id="auto-id/identification-pairing/strict-v1",
    minimum_mac=0.80,
    maximum_relative_frequency_error=0.15,
    tracking_minimum_mac=0.90,
    minimum_observations=2,
    assignment_tie_tolerance=1.0e-9,
)
