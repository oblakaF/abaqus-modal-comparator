"""Acquisition / remount linkage for Σ_setup — Auto-ID M2.5 (SPEC §4.1, §7).

Only a repeat test of the **same physical specimen** estimates setup/retest scatter:
a genuine remount / re-suspension / excitation reinstallation, a comparable protocol,
and — for shapes/MAC — the same measurement grid.  Specimen-to-specimen scatter is
never Σ_setup.  This module classifies run pairs and validates remount links; it does
not compute a covariance (that belongs to the later uncertainty stage).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .specimen_manifest import SpecimenManifest, SpecimenManifestError


class SetupRepeatEligibility(str, Enum):
    FREQUENCY_AND_SHAPE = "eligible_frequency_and_shape"
    FREQUENCY_ONLY = "eligible_frequency_only"
    NOT_ELIGIBLE = "not_eligible"
    INSUFFICIENTLY_DOCUMENTED = "insufficiently_documented"


@dataclass(frozen=True)
class SetupRepeatClassification:
    eligibility: SetupRepeatEligibility
    reasons: tuple[str, ...]
    original_run: str
    repeat_run: str

    @property
    def frequency_eligible(self) -> bool:
        return self.eligibility in (SetupRepeatEligibility.FREQUENCY_AND_SHAPE, SetupRepeatEligibility.FREQUENCY_ONLY)

    @property
    def shape_eligible(self) -> bool:
        return self.eligibility is SetupRepeatEligibility.FREQUENCY_AND_SHAPE


def _ordered(first: SpecimenManifest, second: SpecimenManifest) -> tuple[SpecimenManifest, SpecimenManifest]:
    """(original, repeat): the repeat is the run whose remount_of names the other run."""
    if second.acquisition.remount_of == first.test_run_id:
        return first, second
    if first.acquisition.remount_of == second.test_run_id:
        return second, first
    return first, second


def classify_setup_repeat(first: SpecimenManifest, second: SpecimenManifest) -> SetupRepeatClassification:
    """Whether two runs may contribute to Σ_setup (frequency) and to shape/MAC repeat analysis."""

    original, repeat = _ordered(first, second)
    runs = (str(original.test_run_id), str(repeat.test_run_id))

    def result(eligibility, *reasons):
        return SetupRepeatClassification(eligibility, tuple(reasons), *runs)

    if original.test_run_id == repeat.test_run_id:
        return result(SetupRepeatEligibility.NOT_ELIGIBLE,
                      "same test_run_id: a duplicate or re-export of one run is not a repeat test")
    if original.physical_specimen_id is None or repeat.physical_specimen_id is None:
        return result(SetupRepeatEligibility.INSUFFICIENTLY_DOCUMENTED,
                      "physical_specimen_id is not recorded, so the same physical specimen cannot be established")
    if original.physical_specimen_id != repeat.physical_specimen_id:
        return result(SetupRepeatEligibility.NOT_ELIGIBLE,
                      "different physical specimens: specimen-to-specimen scatter is not Σ_setup (SPEC §7)")
    if original.design_id != repeat.design_id or original.family_id != repeat.family_id:
        return result(SetupRepeatEligibility.NOT_ELIGIBLE,
                      "one physical specimen cannot carry two different design or family identities")
    if repeat.acquisition.remount_of != original.test_run_id:
        return result(SetupRepeatEligibility.INSUFFICIENTLY_DOCUMENTED,
                      "no remount_of link between the runs: a genuine independent remount is not documented")
    if original.acquisition.protocol_id is None or repeat.acquisition.protocol_id is None:
        return result(SetupRepeatEligibility.INSUFFICIENTLY_DOCUMENTED,
                      "acquisition protocol is not recorded for both runs; comparability cannot be established")
    if original.acquisition.protocol_id != repeat.acquisition.protocol_id:
        return result(SetupRepeatEligibility.NOT_ELIGIBLE, "acquisition protocols differ; the runs are not comparable")
    same_grid = (original.acquisition.grid.grid_id == repeat.acquisition.grid.grid_id
                 and original.acquisition.grid.point_count == repeat.acquisition.grid.point_count)
    remount = f"documented {repeat.acquisition.remount_kind}: {repeat.acquisition.remount_evidence}"
    if not same_grid:
        return result(SetupRepeatEligibility.FREQUENCY_ONLY, remount,
                      "different measurement grids: frequency-only setup estimate; shapes/MAC need the same grid")
    return result(SetupRepeatEligibility.FREQUENCY_AND_SHAPE, remount, "same physical specimen, protocol and grid")


def validate_acquisition_links(manifests: Iterable[SpecimenManifest]) -> None:
    """Refuse ambiguous run identities and impossible remount links within a set of passports."""

    by_run: dict = {}
    for manifest in manifests:
        if manifest.test_run_id in by_run:
            raise SpecimenManifestError("test_run_id", f"{manifest.test_run_id} is used by more than one passport.")
        by_run[manifest.test_run_id] = manifest
    for manifest in by_run.values():
        target_id = manifest.acquisition.remount_of
        if target_id is None:
            continue
        target = by_run.get(target_id)
        if target is None:
            raise SpecimenManifestError("acquisition.remount_of",
                                        f"{manifest.test_run_id} names unknown run {target_id} as its original.")
        if (manifest.physical_specimen_id is None or target.physical_specimen_id is None
                or manifest.physical_specimen_id != target.physical_specimen_id):
            raise SpecimenManifestError("acquisition.remount_of",
                                        f"{manifest.test_run_id} cannot be a remount of {target_id}: "
                                        "the runs do not share one recorded physical specimen.")
    # Every link target exists (checked above); now follow each chain back to its original run.
    for manifest in by_run.values():
        seen = {manifest.test_run_id}
        current = manifest
        while current.acquisition.remount_of is not None:
            if current.acquisition.remount_of in seen:
                raise SpecimenManifestError("acquisition.remount_of", "remount links form a cycle.")
            seen.add(current.acquisition.remount_of)
            current = by_run[current.acquisition.remount_of]
