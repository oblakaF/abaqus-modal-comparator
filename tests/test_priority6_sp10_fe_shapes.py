"""PRIORITY-6: the SP-10 FE package extracted from the existing ODB of SP10_NEW_E1=E2_NSM_DENSITY.

- every eigenvalue table of an Abaqus .dat is read, in step order (the SP-10 jobs have two frequency steps);
- an ODB frequency equals the .dat only when it prints to the same five significant digits;
- a second extraction attempt is refused (one run, no retry);
- the archived package record: modes 7–25 of step SP_10_MODAL_FREE, every frequency equal to the .dat, the modes
  above 220 Hz present, no MAC, pair or registration in it;
- the archived Research Results of SP-10 stay NOT VERIFIED when the Workspace reads this package.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from services import research_results_reader as rr  # noqa: E402

RECORD = ROOT / "docs" / "research" / "sp10_existing_fe_shapes_202610" / "SP10_FE_PACKAGE.json"


def _module():
    spec = importlib.util.spec_from_file_location(
        "run_sp10_extraction", ROOT / "research" / "sp10_existing_fe_shapes" / "run_sp10_extraction.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DAT = """
                        S T E P       1     C A L C U L A T I O N   O F   E I G E N V A L U E S

                              E I G E N V A L U E    O U T P U T

 MODE NO      EIGENVALUE              FREQUENCY         GENERALIZED MASS   COMPOSITE MODAL DAMPING
                             (RAD/TIME)   (CYCLES/TIME)


       1*    -1.53000E-03     0.0000         0.0000         1.0000         0.0000
       2       22524.         150.08         23.886         1.0000         0.0000

 ***NOTE: EIGENVALUES MARKED WITH A * APPEAR TO BE RIGID BODY MODES

          P A R T I C I P A T I O N   F A C T O R S

 MODE NO    X-COMPONENT    Y-COMPONENT    Z-COMPONENT    X-ROTATION     Y-ROTATION     Z-ROTATION

       1      2.32182E-02   -2.21614E-04   -3.05544E-06    1.46276E-02    2.61494E-02    -5.2464

                        S T E P       2     C A L C U L A T I O N   O F   E I G E N V A L U E S

                              E I G E N V A L U E    O U T P U T

 MODE NO      EIGENVALUE              FREQUENCY         GENERALIZED MASS   COMPOSITE MODAL DAMPING
                             (RAD/TIME)   (CYCLES/TIME)


       1*    -1.53000E-03     0.0000         0.0000         1.0000         0.0000
       2       22524.         150.08         23.886         1.0000         0.0000
       3      8.26716E+06     2875.3         457.61         1.0000         0.0000

 ***NOTE: EIGENVALUES MARKED WITH A * APPEAR TO BE RIGID BODY MODES
"""


class DatTablesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _module()

    def test_every_eigenvalue_table_is_read_in_step_order(self):
        tables = self.m.dat_tables(DAT)
        self.assertEqual([step for step, _rows in tables], [1, 2])
        self.assertEqual([(mode, hz) for mode, _eig, hz in tables[0][1]], [(1, 0.0), (2, 23.886)])
        self.assertEqual([(mode, hz) for mode, _eig, hz in tables[1][1]], [(1, 0.0), (2, 23.886), (3, 457.61)])

    def test_the_participation_factors_are_not_read_as_modes(self):
        self.assertEqual(len(self.m.dat_tables(DAT)[0][1]), 2)

    def test_equal_only_to_the_printed_digits(self):
        same = self.m.same_printed_value
        self.assertTrue(same(23.88612, 23.886))
        self.assertTrue(same(457.6149, 457.61))
        self.assertFalse(same(23.8866, 23.886))
        self.assertFalse(same(457.62, 457.61))
        self.assertTrue(same(0.0, 0.0))

    def test_a_second_extraction_attempt_is_refused(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(self.m, "RUN", Path(folder)):
            (Path(folder) / "logs").mkdir()
            (Path(folder) / "logs" / "attempt.json").write_text("{}", encoding="utf-8")
            with mock.patch.object(self.m.subprocess, "run") as run, self.assertRaises(self.m.Refused):
                self.m.extract()
            run.assert_not_called()


class ArchivedPackageRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(RECORD.read_text(encoding="utf-8"))

    def test_the_package_is_step_two_modes_7_to_25_equal_to_the_dat(self):
        r = self.record
        self.assertEqual(r["result"], "PASS")
        self.assertEqual(r["problems"], [])
        self.assertEqual(r["extraction"]["step"], "SP_10_MODAL_FREE")
        self.assertEqual([f["mode"] for f in r["frequencies"]], list(range(7, 26)))
        self.assertTrue(all(f["equal_to_dat"] for f in r["frequencies"]))
        self.assertEqual(r["extraction"]["modes_above_220_hz"], list(range(16, 26)))
        self.assertEqual(r["source"]["odb_sha256"], "87a9036fb5dc314e14a1fcb0d9ef4e0175d80bc6dfb05ceeea926d1ae767302c")
        self.assertEqual(r["extraction"]["extractor_sha256"],
                         "039aa067adeac83e457ccacc9036c767f98c41517fb1ffdd5293fdd01dc6534d")

    def test_the_frequencies_agree_with_the_archived_dat_values(self):
        by_mode = {f["mode"]: f["dat_step2_hz"] for f in self.record["frequencies"]}
        # PRIORITY-1 (.dat, step 1: FE7–FE15) and the M10 erratum (step 2: FE16–FE18)
        self.assertEqual([by_mode[m] for m in range(7, 16)],
                         [23.886, 76.529, 79.572, 90.785, 91.986, 146.12, 210.88, 214.23, 220.04])
        self.assertEqual([by_mode[m] for m in (16, 17, 18)], [226.95, 265.04, 267.14])

    def test_the_record_holds_no_pairing_mac_or_registration(self):
        text = json.dumps(self.record).lower()
        for word in ("\"mac", "pair\"", "registration", "orientation"):
            self.assertNotIn(word, text)
        self.assertEqual(self.record["labels"], "RESEARCH_ONLY / HYPOTHETICAL_PAIRING / NOT_A_MATERIAL_PROPERTY")


class ResearchResultsLinkTests(unittest.TestCase):
    def test_sp10_research_tables_stay_not_verified_with_the_extracted_package(self):
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        spec = rr.SPECIMENS["SP-10"]
        verified, text = rr.workspace_link("SP-10", {"sha256": spec.experiment_sha256},
                                           {"sha256": record["identity"]["manifest_sha256"]})
        self.assertFalse(verified)
        self.assertTrue(text.startswith(rr.NOT_VERIFIED_BANNER + ": "))
        self.assertIn("the FE identity is not confirmed: SP-10 has no research FE package", text)
        self.assertIn(record["identity"]["manifest_sha256"][:12], text)


if __name__ == "__main__":
    unittest.main()
