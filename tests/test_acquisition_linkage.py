"""M2.5 acquisition / remount linkage for Σ_setup (SPEC §7)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.acquisition_linkage import SetupRepeatEligibility as E, classify_setup_repeat, validate_acquisition_links
from domain.specimen_manifest import SpecimenManifestError, load_specimen_manifest
from m2_support import parse


def run(run_id="RUN-A", specimen="PANEL-1", remount_of=None, kind="remount", grid=("G-121", 121), protocol="P-1",
        **extra):
    acquisition = {"session": run_id, "grid": {"grid_id": grid[0], "point_count": grid[1]}, "fixture_id": None,
                   "protocol_id": protocol, "remount_of": remount_of}
    if remount_of is not None:
        acquisition.update(remount_kind=kind, remount_evidence=f"rig log: {kind} before {run_id}")
    overrides = {"test_run_id": run_id, "acquisition": acquisition, **extra}
    if specimen is None:
        overrides.update(physical_specimen_id=None, unavailable={"physical_specimen_id": "not recorded"})
    else:
        overrides["physical_specimen_id"] = specimen
    return parse(**overrides)


class SetupRepeatClassificationTests(unittest.TestCase):
    def test_same_panel_remount_same_grid_is_frequency_and_shape_eligible(self):
        original, repeat = run("RUN-A"), run("RUN-B", remount_of="RUN-A")
        result = classify_setup_repeat(original, repeat)
        self.assertIs(result.eligibility, E.FREQUENCY_AND_SHAPE)
        self.assertTrue(result.frequency_eligible and result.shape_eligible)
        self.assertEqual((result.original_run, result.repeat_run), ("RUN-A", "RUN-B"))
        self.assertIs(classify_setup_repeat(repeat, original).eligibility, E.FREQUENCY_AND_SHAPE)  # order-free

    def test_re_suspension_and_excitation_reinstallation_count(self):
        for kind in ("re_suspension", "excitation_reinstallation"):
            with self.subTest(kind=kind):
                result = classify_setup_repeat(run("RUN-A"), run("RUN-B", remount_of="RUN-A", kind=kind))
                self.assertIs(result.eligibility, E.FREQUENCY_AND_SHAPE)

    def test_different_panel_is_not_setup_scatter(self):
        result = classify_setup_repeat(run("RUN-A", "PANEL-1"), run("RUN-B", "PANEL-2", remount_of="RUN-A"))
        self.assertIs(result.eligibility, E.NOT_ELIGIBLE)
        self.assertIn("specimen-to-specimen", result.reasons[0])

    def test_same_run_duplicate_is_not_a_repeat(self):
        self.assertIs(classify_setup_repeat(run("RUN-A"), run("RUN-A")).eligibility, E.NOT_ELIGIBLE)

    def test_undocumented_remount_is_insufficient(self):
        result = classify_setup_repeat(run("RUN-A"), run("RUN-B"))
        self.assertIs(result.eligibility, E.INSUFFICIENTLY_DOCUMENTED)
        unknown_panel = classify_setup_repeat(run("RUN-A", None), run("RUN-B", None))
        self.assertIs(unknown_panel.eligibility, E.INSUFFICIENTLY_DOCUMENTED)

    def test_protocol_compatibility(self):
        self.assertIs(classify_setup_repeat(run("RUN-A", protocol="P-1"),
                                            run("RUN-B", remount_of="RUN-A", protocol="P-2")).eligibility,
                      E.NOT_ELIGIBLE)
        self.assertIs(classify_setup_repeat(run("RUN-A", protocol=None),
                                            run("RUN-B", remount_of="RUN-A")).eligibility,
                      E.INSUFFICIENTLY_DOCUMENTED)

    def test_grid_mismatch_is_frequency_only_at_most(self):
        # SPEC §7: the SP13 121-point / 289-point pair can give at most a frequency-only estimate.
        result = classify_setup_repeat(run("RUN-121", grid=("G-121", 121)),
                                       run("RUN-289", remount_of="RUN-121", grid=("G-289", 289)))
        self.assertIs(result.eligibility, E.FREQUENCY_ONLY)
        self.assertTrue(result.frequency_eligible)
        self.assertFalse(result.shape_eligible)

    def test_121_289_pair_without_confirmed_panel_or_remount_is_unconfirmed(self):
        result = classify_setup_repeat(run("RUN-121", None, grid=("G-121", 121)),
                                       run("RUN-289", None, grid=("G-289", 289)))
        self.assertIs(result.eligibility, E.INSUFFICIENTLY_DOCUMENTED)
        self.assertFalse(result.frequency_eligible)

    def test_historical_sp02_sp13_runs_establish_no_setup_repeat(self):
        sp02, sp13 = (load_specimen_manifest(ROOT / "docs" / "auto_id" / "specimens" / f"{n}.specimen.json")
                      for n in ("SP02", "SP13"))
        self.assertIs(classify_setup_repeat(sp02, sp13).eligibility, E.INSUFFICIENTLY_DOCUMENTED)


class AcquisitionLinkValidationTests(unittest.TestCase):
    def test_valid_chain(self):
        validate_acquisition_links([run("RUN-A"), run("RUN-B", remount_of="RUN-A"), run("RUN-C", remount_of="RUN-B")])

    def test_duplicate_run_identity_is_refused(self):
        with self.assertRaises(SpecimenManifestError) as caught:
            validate_acquisition_links([run("RUN-A"), run("RUN-A", "PANEL-2")])
        self.assertEqual(caught.exception.field, "test_run_id")

    def test_remount_of_a_different_panel_is_impossible(self):
        with self.assertRaises(SpecimenManifestError):
            validate_acquisition_links([run("RUN-A", "PANEL-1"), run("RUN-B", "PANEL-2", remount_of="RUN-A")])

    def test_remount_of_unknown_run_or_unrecorded_panel_is_refused(self):
        with self.assertRaises(SpecimenManifestError):
            validate_acquisition_links([run("RUN-B", remount_of="RUN-Z")])
        with self.assertRaises(SpecimenManifestError):
            validate_acquisition_links([run("RUN-A", None), run("RUN-B", None, remount_of="RUN-A")])

    def test_remount_cycle_is_refused(self):
        with self.assertRaises(SpecimenManifestError):
            validate_acquisition_links([run("RUN-A", remount_of="RUN-B"), run("RUN-B", remount_of="RUN-A")])


if __name__ == "__main__":
    unittest.main()
