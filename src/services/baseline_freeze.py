"""Baseline observation freeze — Auto-ID M4.2 (SPEC §6 S1/S3, §12.1; D-008).

Experimental modes enter only if M1 eligibility allows them (modes below a trusted
suspension threshold never do; FE frequencies never select experimental modes).  The
eligible modes are paired with the elastic FE modes of the baseline under the strict
policy, and the rows are frozen only when that pairing is final.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from domain.experimental_qc import ExperimentalModeEligibility
from domain.frozen_observations import (
    BaselineIdentity,
    ExcludedObservation,
    FreezeStatus,
    FrozenObservationSet,
    ObservationRow,
)
from domain.identification_pairing_policy import IdentificationPairingPolicy

from .identification_pairing import BaselinePairingStatus, ModeFrequency, pair_baseline


class BaselineEvidenceError(ValueError):
    """Baseline evidence is malformed or inconsistent."""


@dataclass(frozen=True)
class BaselineEvidence:
    """Everything the baseline freeze needs; ``mac`` uses NaN for entries that are not available."""

    identity: BaselineIdentity
    experimental_modes: tuple[ModeFrequency, ...]
    eligibility: ExperimentalModeEligibility
    fe_modes: tuple[ModeFrequency, ...]  # elastic FE modes only
    mac: tuple[tuple[float, ...], ...]  # rows: experimental_modes, columns: fe_modes

    def mac_matrix(self) -> np.ndarray:
        return np.array(self.mac, dtype=float).reshape(len(self.experimental_modes), len(self.fe_modes))


def build_baseline_evidence(identity: BaselineIdentity, experimental_modes: Sequence[ModeFrequency],
                            eligibility: ExperimentalModeEligibility, fe_modes: Sequence[ModeFrequency],
                            mac: np.ndarray) -> BaselineEvidence:
    experimental_modes, fe_modes = tuple(experimental_modes), tuple(fe_modes)
    numbers = {mode.number for mode in experimental_modes}
    if set(eligibility.eligible_modes) | set(eligibility.excluded_modes) != numbers:
        raise BaselineEvidenceError("M1 eligibility must cover exactly the experimental modes.")
    matrix = np.asarray(mac, dtype=float)
    if matrix.shape != (len(experimental_modes), len(fe_modes)):
        raise BaselineEvidenceError(f"MAC matrix shape {matrix.shape} does not match the modes.")
    return BaselineEvidence(identity, experimental_modes, eligibility, fe_modes,
                            tuple(tuple(float(value) for value in row) for row in matrix))


def freeze_baseline(evidence: BaselineEvidence, policy: IdentificationPairingPolicy) -> FrozenObservationSet:
    """Freeze the baseline observation rows under a strict policy, or report why not."""

    policy.require_strict()
    eligible = set(evidence.eligibility.eligible_modes)
    excluded = [ExcludedObservation(number, "below the trusted suspension threshold (M1 eligibility)")
                for number in sorted(evidence.eligibility.excluded_modes)]
    keep = [i for i, mode in enumerate(evidence.experimental_modes) if mode.number in eligible]
    matrix = evidence.mac_matrix()[keep, :] if keep else np.zeros((0, len(evidence.fe_modes)))
    if not keep:
        return FrozenObservationSet(evidence.identity, policy.policy_id, policy.policy_hash, FreezeStatus.NOT_FROZEN,
                                    ("no eligible experimental mode",), (), (), tuple(excluded), ())
    result = pair_baseline(policy, [evidence.experimental_modes[i] for i in keep], evidence.fe_modes, matrix)

    rows = tuple(ObservationRow(f"R{index}", pair.experimental_mode, pair.experimental_hz, pair.fe_mode, pair.fe_hz,
                                pair.mac, pair.relative_frequency_error)
                 for index, pair in enumerate(result.pairs, start=1))
    excluded += [ExcludedObservation(item.experimental_mode, item.reason) for item in result.unpaired]
    excluded.sort(key=lambda item: item.experimental_mode)
    if result.status is BaselinePairingStatus.COMPLETE:
        return FrozenObservationSet(evidence.identity, policy.policy_id, policy.policy_hash, FreezeStatus.FROZEN, (),
                                    rows, (), tuple(excluded), ())
    reasons = {
        BaselinePairingStatus.INCOMPLETE_EVIDENCE:
            f"MAC not available for {len(result.unknown_entries)} frequency-admissible experimental/FE pairs; "
            "the strict pairing cannot be final",
        BaselinePairingStatus.AMBIGUOUS: f"the strict assignment is not unique: {list(result.ambiguous_pairs)}",
        BaselinePairingStatus.INSUFFICIENT_COVERAGE:
            f"{len(result.pairs)} strict pairs < required {policy.minimum_observations}",
    }
    reason_list = [reasons[result.status]]
    if result.status is not BaselinePairingStatus.INSUFFICIENT_COVERAGE and len(result.pairs) < policy.minimum_observations:
        reason_list.append(reasons[BaselinePairingStatus.INSUFFICIENT_COVERAGE])
    return FrozenObservationSet(evidence.identity, policy.policy_id, policy.policy_hash, FreezeStatus.NOT_FROZEN,
                                tuple(reason_list), (), rows, tuple(excluded), result.unknown_entries)
