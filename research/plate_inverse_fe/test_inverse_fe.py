"""PRIORITY-4: targeted tests of the job mechanics and the comparison formulas (no Abaqus is started).

- the generic ``run_s4.prepare_jobs`` reproduces the six S4 INPs byte for byte (when the M11 baseline is present);
- a multi-field state changes only the *Elastic line, with exactly the requested constants;
- duplicate job names, an existing INP of another content and a seventh / fourth attempt are refused; an attempted
  job is never run again (the solver is never called in these tests);
- δ_surrogate = 100 (f_Abaqus − f_LM) / f_LM and the cluster centroid (mean ln f);
- the research labels are kept.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_inverse_fe as F  # noqa: E402

S = F.S
BASELINE_PRESENT = S.BASE_INP.is_file()


@unittest.skipUnless(BASELINE_PRESENT, "the M11 baseline INP is not on this computer")
class PrepareTests(unittest.TestCase):
    def test_s4_is_reproduced_byte_for_byte(self):
        record = S.JOBS_ROOT / "s4_prepare.json"
        if not record.is_file():
            self.skipTest("the PRIORITY-2 record is not on this computer")
        recorded = json.loads(record.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as folder:
            new = S.prepare_jobs(Path(folder), [(j, {p: (v, t)}) for j, p, v, t in S.JOBS], "x.json")
        for job, entry in recorded["jobs"].items():
            self.assertEqual(new["jobs"][job]["inp_sha256"], entry["inp_sha256"], job)

    def test_a_state_changes_only_the_elastic_line(self):
        with tempfile.TemporaryDirectory() as folder:
            rec = S.prepare_jobs(Path(folder), [("H2", F.STATES["H2"])], "x.json", keep_width=False)
            entry = rec["jobs"]["H2"]
            self.assertEqual(entry["new_line"], "41952.8,41952.8, 8500.,  0.05,   0.3,   0.3,4810.3, 3000.")
            base = S.BASE_INP.read_bytes().split(b"\n")
            new = Path(entry["inp"]).read_bytes().split(b"\n")
            self.assertEqual([i for i, (a, b) in enumerate(zip(base, new)) if a != b], [entry["changed_line_index"]])
            self.assertEqual((entry["parsed"]["E1"], entry["parsed"]["E2"], entry["parsed"]["G12"]),
                             (41952.8, 41952.8, 4810.3))
            for key, value in (("E3", 8500.0), ("nu12", 0.05), ("G13", 3000.0), ("G23", 3000.0), ("h", 0.875),
                               ("rho", 1.498e-09)):
                self.assertEqual(entry["parsed"][key], value, key)
            Path(entry["inp"]).write_bytes(b"other")  # an existing INP of another content is never overwritten
            with self.assertRaises(S.Refused):
                S.prepare_jobs(Path(folder), [("H2", F.STATES["H2"])], "x.json", keep_width=False)
            with self.assertRaises(S.Refused):
                S.prepare_jobs(Path(folder), [("A", F.STATES["S0"]), ("A", F.STATES["S0"])], "y.json",
                               keep_width=False)


class SolveGuardTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.runs = self.root / "runs.csv"
        jobs = {}
        for job in ("S0", "H1", "H2", "X4"):
            (self.root / job).mkdir()
            (self.root / job / f"{job}.inp").write_text(job, encoding="utf-8")
            jobs[job] = {"changes": {"G12": 1.0}, "inp_sha256": S.sha256(self.root / job / f"{job}.inp")}
        (self.root / "prep.json").write_text(json.dumps({"jobs": jobs}), encoding="utf-8")

    def write_attempts(self, jobs):
        with open(self.runs, "w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=S.RUN_FIELDS)
            writer.writeheader()
            for k, job in enumerate(jobs, 1):
                writer.writerow({"attempt": k, "job": job, "sta_completed": "False" if job == "H1" else "True"})

    def test_attempted_jobs_are_never_rerun_and_the_budget_is_enforced(self):
        self.write_attempts(["S0", "H1", "H2"])  # H1 failed: it is NOT run again here
        with mock.patch.object(S, "ABAQUS", self.root / "prep.json"), \
                mock.patch.object(S.subprocess, "run", side_effect=AssertionError("the solver must not start")):
            with self.assertRaises(S.Refused) as refused:
                S.solve_jobs(self.root, "prep.json", 3, self.runs)
        self.assertIn("X4 is not run", str(refused.exception))

    def test_an_existing_odb_is_never_overwritten(self):
        self.write_attempts(["S0", "H1"])
        (self.root / "H2" / "H2.odb").write_bytes(b"old")
        with mock.patch.object(S, "ABAQUS", self.root / "prep.json"), \
                mock.patch.object(S.subprocess, "run", side_effect=AssertionError("the solver must not start")):
            with self.assertRaises(S.Refused) as refused:
                S.solve_jobs(self.root, "prep.json", 3, self.runs)
        self.assertIn("ODB already exists", str(refused.exception))


class FormulaTests(unittest.TestCase):
    def test_errors_centroid_and_labels(self):
        self.assertAlmostEqual(F.surrogate_error_percent(101.0, 100.0), 1.0)
        self.assertAlmostEqual(F.surrogate_error_percent(18.63088, 18.63109), 100 * (18.63088 - 18.63109) / 18.63109)
        self.assertAlmostEqual(F.centroid([174.0, 180.0]), math.sqrt(174.0 * 180.0))
        self.assertEqual(F.LABELS, ["RESEARCH_ONLY", "HYPOTHETICAL_PAIRING", "NOT_A_MATERIAL_PROPERTY",
                                    "NOT_TRANSFERABLE_WITHOUT_VALIDATION"])
        self.assertEqual(F.MAX_SOLVES, 3)
        self.assertEqual(set(F.STATES), {"S0", "H1", "H2"})


if __name__ == "__main__":
    unittest.main()
