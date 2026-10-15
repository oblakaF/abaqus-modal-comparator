"""SPEC v1.2 §8 counting conditions — the one shared rule (P11).

The specimen-calibration gate judges its observability with this function, and the records-only observation-readiness
record reports it; neither keeps a copy of the rule. It counts only: full practical rank at the M5 RCOND and
complete leave-one-FIT-family-out validity are separate §8 conditions, judged by the gate from FE evidence.

Refusal codes are the gate's refusal-code values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .practical_identifiability import PracticalIdentifiabilityInputError

INSUFFICIENT_FIT_FAMILIES = "INSUFFICIENT_FIT_FAMILIES"
NO_HOLDOUT_FAMILY = "NO_HOLDOUT_FAMILY"
HOLDOUT_FAMILY_OVERLAPS_FIT = "HOLDOUT_FAMILY_OVERLAPS_FIT"


@dataclass(frozen=True)
class ObservationCount:
    """The counting conditions of SPEC v1.2 §8 for k parameters (rank and leave-one-family-out are not judged here)."""

    k: int
    fit_family_keys: tuple[str, ...]
    holdout_family_keys: tuple[str, ...]
    holdout_fit_overlap: tuple[str, ...]
    refusals: tuple[tuple[str, str], ...]  # (refusal code, detail)

    @property
    def met(self) -> bool:
        return not self.refusals

    def to_dict(self) -> dict:
        return {"k": self.k, "required_fit_families": self.k + 1, "fit_family_keys": list(self.fit_family_keys),
                "holdout_family_keys": list(self.holdout_family_keys),
                "holdout_fit_overlap": list(self.holdout_fit_overlap), "met": self.met,
                "refusal_reasons": [{"code": code, "detail": detail} for code, detail in self.refusals]}


def count_observations(fit_families: Mapping[str, str], holdout_families: Mapping[str, str],
                       k: int) -> ObservationCount:
    """≥ k + 1 distinct FIT families, ≥ 1 HOLDOUT family, no family both FIT and HOLDOUT.

    The mappings take a governed term id to its M4.3 family key; a confirmed cluster is one term. Families are counted
    by key, so terms that share a family count once. A term that is both FIT and HOLDOUT is an input error.
    """
    if isinstance(k, bool) or not isinstance(k, int) or k < 0:
        raise PracticalIdentifiabilityInputError("k must be a non-negative number of parameters.")
    for name, families in (("fit_families", fit_families), ("holdout_families", holdout_families)):
        if any(not isinstance(t, str) or not t or not isinstance(f, str) or not f for t, f in families.items()):
            raise PracticalIdentifiabilityInputError(f"{name} must map term ids to non-empty family keys.")
    shared_terms = sorted(set(fit_families) & set(holdout_families))
    if shared_terms:
        raise PracticalIdentifiabilityInputError(f"terms {shared_terms} are both FIT and HOLDOUT.")
    fit_keys = sorted(set(fit_families.values()))
    holdout_keys = sorted(set(holdout_families.values()))
    overlap = sorted(set(fit_keys) & set(holdout_keys))
    refusals = []
    if len(fit_keys) < k + 1:
        refusals.append((INSUFFICIENT_FIT_FAMILIES, f"{len(fit_keys)} distinct FIT families {fit_keys} < k + 1 = {k + 1}"))
    if not holdout_keys:
        refusals.append((NO_HOLDOUT_FAMILY, "no HOLDOUT family"))
    if overlap:
        refusals.append((HOLDOUT_FAMILY_OVERLAPS_FIT, f"HOLDOUT families shared with FIT: {overlap}"))
    return ObservationCount(k, tuple(fit_keys), tuple(holdout_keys), tuple(overlap), tuple(refusals))
