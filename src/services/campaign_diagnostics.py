"""Campaign report diagnostics (D-076; audit iteration 2) — reporting only, never part of any objective.

- ``excluded_mode_diagnostics``: experimental modes that a strict pairing excluded although their best FE match by
  MAC reaches the policy's identity MAC (0.80).  They make model-form disagreement visible (for example the first
  torsional mode); they are never fitted, never re-paired and never lower a threshold.
- ``per_specimen_agreement``: each specimen's baseline and candidate maximum |frequency error|, so a common
  candidate that improves one specimen while worsening another is visible.  No acceptance threshold.
"""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np

from domain.frozen_observations import FrozenObservationSet

from .baseline_freeze import BaselineEvidence


DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY_NOT_FITTED"


def excluded_mode_diagnostics(evidence: BaselineEvidence, frozen: FrozenObservationSet, minimum_mac: float,
                              fe_families: Mapping[int, str] | None = None) -> tuple[dict, ...]:
    """Excluded experimental modes whose best MAC (over all FE modes) is at least ``minimum_mac``."""

    reasons = {item.experimental_mode: item.reason for item in frozen.excluded}
    matrix = evidence.mac_matrix()
    rows = []
    for i, mode in enumerate(evidence.experimental_modes):
        if mode.number not in reasons or not np.any(np.isfinite(matrix[i])):
            continue
        j = int(np.nanargmax(matrix[i]))
        mac = float(matrix[i, j])
        if mac < minimum_mac:
            continue
        fe = evidence.fe_modes[j]
        rows.append({"experimental_mode": mode.number, "experimental_hz": mode.frequency_hz,
                     "best_fe_mode": fe.number, "fe_hz": fe.frequency_hz, "mac": mac,
                     "signed_frequency_error": fe.frequency_hz / mode.frequency_hz - 1.0,
                     "fe_family": None if fe_families is None else fe_families.get(fe.number),
                     "exclusion_reason": reasons[mode.number], "role": DIAGNOSTIC_ONLY,
                     "state": "governed baseline (frozen pairing state)"})
    return tuple(rows)


def per_specimen_agreement(rows: Sequence[Mapping], baseline_rows: Sequence[Mapping]) -> dict:
    """Per-specimen max |relative error| over FIT + HOLDOUT rows at the baseline and at the candidate."""

    result = {}
    for label in sorted({r["specimen"] for r in rows} | {r["specimen"] for r in baseline_rows}):
        candidate = [abs(r["relative_error"]) for r in rows if r["specimen"] == label]
        baseline = [abs(r["relative_error"]) for r in baseline_rows if r["specimen"] == label]
        if not candidate or not baseline:
            result[label] = {"baseline_max_abs_error": max(baseline, default=None),
                             "candidate_max_abs_error": max(candidate, default=None), "delta": None,
                             "change": "NOT_AVAILABLE"}
            continue
        delta = max(candidate) - max(baseline)
        result[label] = {"baseline_max_abs_error": max(baseline), "candidate_max_abs_error": max(candidate),
                         "delta": delta, "change": "IMPROVED" if delta < 0 else ("WORSENED" if delta > 0 else "SAME")}
    return {"specimens": result, "note": "diagnostic only; no acceptance threshold (SPEC v1.2 not decided)"}
