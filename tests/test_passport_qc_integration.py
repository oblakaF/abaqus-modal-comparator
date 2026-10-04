"""M2 passport -> M1.4 QC: the suspension threshold flows from the physical passport, never guessed."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.experimental_qc import ExperimentalQCStatus as S, TrustedSuspensionThreshold
from domain.specimen_manifest import SpecimenManifestError
from m2_support import parse
from services import experimental_qc as qc
from test_experimental_qc import _SyntheticChainFixture


class PassportSuspensionTests(_SyntheticChainFixture, unittest.TestCase):
    def run_chain(self, **kwargs):
        return qc.prepare_auto_id_experimental_input("SYN/set-a", roots=self.workspace.roots, manifest=self.manifest,
                                                     repo_root=self.workspace.repo_root, **kwargs)

    def test_threshold_flows_from_the_passport(self):
        passport = parse()  # suspension_max_hz 20 Hz, fixture SYN/set-a; synthetic modes at 12 Hz and 31.5 Hz
        result = self.run_chain(specimen_passport=passport)
        check = result.qc_report.check(qc.SUSPENSION_THRESHOLD)
        self.assertIs(check.status, S.WARNING)
        self.assertEqual(check.warnings[0].modes, (1,))
        self.assertIn(passport.manifest_hash[:16], result.eligibility.threshold.source)
        self.assertEqual(result.eligibility.excluded_modes, (1,))
        self.assertEqual([mode.number for mode in result.identification_dataset().modes], [2])
        self.assertEqual([mode.number for mode in result.dataset.modes], [1, 2])  # dataset unchanged

    def test_absent_passport_value_stays_not_available(self):
        passport = parse(suspension_max_hz=None, unavailable={"suspension_max_hz": "not measured"})
        result = self.run_chain(specimen_passport=passport)
        self.assertIs(result.qc_report.check(qc.SUSPENSION_THRESHOLD).status, S.NOT_AVAILABLE)
        self.assertEqual(result.eligibility.excluded_modes, ())
        self.assertEqual(result.qc_report.content_hash, self.run_chain().qc_report.content_hash)

    def test_passport_for_another_fixture_is_refused(self):
        with self.assertRaises(SpecimenManifestError):
            self.run_chain(specimen_passport=parse(acquisition__fixture_id="SP02/bravo-1"))

    def test_passport_and_explicit_threshold_are_exclusive(self):
        with self.assertRaises(TypeError):
            self.run_chain(specimen_passport=parse(),
                           suspension_threshold=TrustedSuspensionThreshold(20.0, "rig log"))


if __name__ == "__main__":
    unittest.main()
