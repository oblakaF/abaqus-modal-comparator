"""PLATE-CANDIDATES: the offline calculation of FE-model parameter candidates of the M11 plate (no Qt).

- known parameters are recovered from frequencies made with the same model (one parameter; E1 = E2 with G12);
- the calculation from the archived series' frequencies reproduces the archived S0 / H1 / H2 sets, and the residual
  of every declared row is the model's;
- the answer follows the measured frequencies given (it is not an archive lookup);
- a rank-deficient scenario and an ambiguous or incomplete pairing are refused without a number; every declared
  scenario keeps EXP1 ↔ FE7; nothing is paired by frequency, and MAC is not an input;
- a parameter the rows do not determine is reported with its supported range, never as a unique value;
- the sources are tied by identity, and every mismatch is refused with its reason;
- the export gives the parameters, the fixed inputs and the predicted frequencies as CSV and TXT;
- with the read-only originals present, the calculation runs on the real 261027 UNV and the real M11 FE package;
  otherwise those tests are skipped.
"""

from __future__ import annotations

import csv
import dataclasses
import hashlib
import inspect
import io
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from services import plate_candidate_results as pc  # noqa: E402
from services import plate_study as ps  # noqa: E402
from services import research_results_reader as rr  # noqa: E402

ARCHIVED = {"S0": (56000.0, 56000.0, 4763.4), "H1": (43467.0, 43467.0, 4804.4), "H2": (41952.8, 41952.8, 4810.3)}
DELIVERY = Path(r"D:\Snadwich\New  EXP results")


def archived_frequencies() -> dict:
    return {row.exp_no: row.f_exp_hz for row in rr.load_snapshot().matching["PLATE"]}


def fe_frequencies(sens: dict) -> dict:
    """{FE mode: Hz} of a package whose baseline is the sensitivity table's."""
    out = {8: 59.87416, 9: 62.00917, 20: 327.90103}
    for term, s in sens.items():
        modes = [int(m[2:]) for m in term.split("+")]
        if len(modes) == 1:
            out[modes[0]] = s["f0"]
        else:  # a cluster term: two modes whose geometric mean is the term's value
            out[modes[0]], out[modes[1]] = s["f0"] / 1.02, s["f0"] * 1.02
    return out


class SyntheticRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.sens = pc.load_sensitivities()

    def frequencies(self, truth: dict) -> dict:
        p = pc.full_parameters(truth)
        out = {n: 10.0 * n for n in range(1, 12)}  # the other records: never used, never paired
        out.update({1: pc.predict(self.sens, "FE7", p), 8: pc.predict(self.sens, "FE15+FE16", p),
                    7: pc.predict(self.sens, "FE14", p)})
        return out

    def test_known_e_and_g12_are_recovered_by_h1_and_h2(self):
        result = pc.calculate(self.frequencies({"E": 56000 * 0.9, "G12": 5000 * 1.08}), self.sens)
        for key in ("H1", "H2"):
            c = result.candidate(key)
            self.assertEqual(c.status, pc.CONVERGED)
            self.assertAlmostEqual(c.E1 / 56000, 0.9, places=3)
            self.assertEqual(c.E1, c.E2)  # E1 = E2 is imposed
            self.assertAlmostEqual(c.G12 / 5000, 1.08, places=3)
            for x in c.residuals:  # multiple-frequency residuals: every declared row is fitted
                self.assertAlmostEqual(x.after_percent, 0.0, delta=0.02)
                self.assertAlmostEqual(x.f_predicted_hz, pc.predict(self.sens, x.term, {"E1": c.E1, "E2": c.E2,
                                                                                        "G12": c.G12}))

    def test_known_g12_is_recovered_by_s0_and_e_is_not_changed(self):
        c = pc.calculate(self.frequencies({"G12": 4600.0}), self.sens).candidate("S0")
        self.assertAlmostEqual(c.G12, 4600.0, delta=0.5)
        self.assertEqual((c.E1, c.E2), (56000.0, 56000.0))
        self.assertEqual(c.fitted, ("G12",))

    def test_the_answer_follows_the_measured_frequencies(self):
        base = archived_frequencies()
        moved = {**base, 1: base[1] * 1.01}
        a, b = pc.calculate(base, self.sens).candidate("S0"), pc.calculate(moved, self.sens).candidate("S0")
        self.assertGreater(b.G12, a.G12 * 1.015)  # FE7 moves with G12^0.48: +1 % in f needs about +2 % in G12
        self.assertEqual(pc.calculate(base, self.sens).candidate("H1").G12, pc.calculate(base, self.sens)
                         .candidate("H1").G12)  # deterministic

    def test_the_bounds_are_reported(self):
        c = pc.calculate({**archived_frequencies(), 1: 5.0}, self.sens).candidate("S0")
        self.assertEqual(c.at_bound, ("G12",))
        self.assertAlmostEqual(c.G12, 2500.0)
        self.assertTrue(any(w.startswith("AT A BOUND") for w in c.warnings))


class ArchiveReproductionTests(unittest.TestCase):
    def setUp(self):
        self.result = pc.compare_with_archive(pc.calculate(archived_frequencies()), pc.load_archive())

    def test_s0_h1_h2_reproduce_the_archived_sets(self):
        for key, (e1, e2, g12) in ARCHIVED.items():
            c = self.result.candidate(key)
            self.assertEqual(c.status, pc.CONVERGED)
            self.assertEqual((round(c.E1, 1), round(c.E2, 1), round(c.G12, 1)), (e1, e2, g12))
            self.assertTrue(c.archive.reproduced)
            self.assertEqual((c.archive.E1, c.archive.E2, c.archive.G12), (e1, e2, g12))

    def test_the_residuals_are_the_archived_approximation_residuals(self):
        with open(ROOT / "docs/research/plate_inverse_r1/PLATE_FREQUENCY_RESIDUALS.csv", encoding="utf-8",
                  newline="") as stream:
            archived = {(r["scenario"], r["exp"]): r for r in csv.DictReader(stream) if r["scenario"] in ARCHIVED}
        self.assertEqual(len(archived), 5)
        seen = 0
        for c in self.result.candidates:
            for x in c.residuals:
                row = archived[(c.key, f"EXP{x.exp}")]
                self.assertEqual(row["fe_term"], x.term)
                self.assertAlmostEqual(x.f_predicted_hz, float(row["f_fe_at_solution_hz"]), delta=2e-4)
                self.assertAlmostEqual(x.after_percent, float(row["error_after_percent"]), delta=1e-4)
                self.assertAlmostEqual(x.before_percent, float(row["error_before_percent"]), delta=6e-4)
                seen += 1
        self.assertEqual(seen, 5)

    def test_rank_status_and_warnings(self):
        s0, h1, h2 = (self.result.candidate(k) for k in ("S0", "H1", "H2"))
        self.assertEqual([(c.rank_fitted, c.rank_full) for c in (s0, h1, h2)], [(1, 1), (2, 2), (2, 2)])
        self.assertEqual(s0.beyond, {})
        self.assertIn("E", h1.beyond)
        self.assertTrue(any(w.startswith("EXTRAPOLATION") for w in h1.warnings))
        self.assertTrue(any(w.startswith("EXTRAPOLATION") for w in h2.warnings))
        self.assertTrue(any("outside the 15 % window" in w for w in h2.warnings))
        self.assertTrue(any(w.startswith("AMBIGUITY") and "FE13" in w for w in h2.warnings))
        for c in (s0, h1, h2):
            self.assertTrue(any("zero by construction" in w for w in c.warnings))

    def test_the_archived_abaqus_solves_are_kept_apart_from_the_calculation(self):
        h1 = self.result.candidate("H1")
        self.assertEqual(h1.archive.abaqus_rows, (("EXP1 ↔ FE7", "18.6307", "18.62655", "-0.0221"),
                                                   ("EXP8 ↔ FE15+FE16", "157.8508", "158.01732", "0.1055")))
        predicted = {x.term: x.f_predicted_hz for x in h1.residuals}
        self.assertAlmostEqual(predicted["FE15+FE16"], 157.86883, places=4)  # the model's value, not Abaqus' 158.017
        self.assertNotAlmostEqual(predicted["FE15+FE16"], 158.01732, places=2)

    def test_another_answer_is_not_called_reproduced(self):
        moved = {**archived_frequencies(), 1: 19.0}
        result = pc.compare_with_archive(pc.calculate(moved), pc.load_archive())
        for c in result.candidates:
            self.assertFalse(c.archive.reproduced)
            self.assertGreater(c.archive.largest_difference_mpa, 1.0)

    def test_a_changed_archive_does_not_change_the_calculation(self):
        result = pc.compare_with_archive(pc.calculate(archived_frequencies()), None, "not compared")
        self.assertEqual(round(result.candidate("H2").E1, 1), 41952.8)
        self.assertIsNone(result.candidate("H2").archive)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(pc.ArchiveRefused):
                pc.load_archive(Path(folder))


class NonUniqueTests(unittest.TestCase):
    def setUp(self):
        self.sens = pc.load_sensitivities()
        self.f_exp = archived_frequencies()

    def test_three_parameters_on_two_rows_are_refused_without_a_number(self):
        scenario = pc.Scenario("X", ((1, "FE7"), (7, "FE14")), ("E1", "E2", "G12"), "E1 ≠ E2 on two rows")
        c = pc.calculate(self.f_exp, self.sens, (scenario,)).candidate("X")
        self.assertEqual(c.status, pc.REFUSED_RANK)
        self.assertFalse(c.calculated)
        self.assertEqual((c.E1, c.E2, c.G12), (None, None, None))
        self.assertEqual(c.rank_fitted, 2)
        self.assertIn("do not determine a unique value", c.limitations[0])

    def test_collinear_rows_are_refused(self):
        sens = {**self.sens, "FE99": dict(self.sens["FE7"])}
        scenario = pc.Scenario("X", ((1, "FE7"), (2, "FE99")), ("E", "G12"), "collinear")
        c = pc.calculate(self.f_exp, sens, (scenario,)).candidate("X")
        self.assertEqual(c.status, pc.REFUSED_RANK)
        self.assertFalse(c.calculated)

    def test_s0_reports_the_supported_range_instead_of_a_unique_e(self):
        c = pc.calculate(self.f_exp, self.sens).candidate("S0")
        low, high = c.g12_range_mpa
        self.assertLess(low, c.G12)
        self.assertGreater(high, c.G12)
        s = self.sens["FE7"]
        for factor, g12 in ((2.0, low), (0.5, high)):  # each end fits EXP1 with E at a declared bound
            p = {"E1": 56000 * factor, "E2": 56000 * factor, "G12": g12}
            self.assertAlmostEqual(pc.predict(self.sens, "FE7", p), self.f_exp[1], places=6)
        self.assertGreater(s["G12"], 0)
        self.assertIn("NOT determined", c.limitations[0])
        self.assertIn(f"{low:.1f} to {high:.1f} MPa", c.limitations[0])

    def test_e1_and_e2_are_never_given_apart(self):
        result = pc.calculate(self.f_exp, self.sens)
        for key in ("H1", "H2"):
            c = result.candidate(key)
            self.assertEqual(c.E1, c.E2)
            self.assertEqual(c.rank_full, 2)
            self.assertTrue(any("not separable" in line for line in c.limitations))
        self.assertTrue(any("not an uncertainty interval" in line for line in result.across))
        self.assertTrue(any("No scenario is preferred" in line for line in result.across))


class PairingTests(unittest.TestCase):
    def setUp(self):
        self.sens = pc.load_sensitivities()
        self.f_exp = archived_frequencies()

    def refused(self, scenario, f_exp=None):
        c = pc.calculate(self.f_exp if f_exp is None else f_exp, self.sens, (scenario,)).candidate(scenario.key)
        self.assertEqual(c.status, pc.REFUSED_PAIRING)
        self.assertFalse(c.calculated)
        return c.reason

    def test_every_declared_scenario_keeps_exp1(self):
        for scenario in pc.SCENARIOS:
            self.assertEqual(scenario.pairs[0], (1, "FE7"))
        result = pc.calculate(self.f_exp, self.sens)
        for c in result.candidates:
            self.assertEqual((c.residuals[0].exp, c.residuals[0].term), (1, "FE7"))
            self.assertEqual(c.residuals[0].f_exp_hz, self.f_exp[1])  # the measured value, unchanged
        self.assertEqual(dict(result.experiment)[1], self.f_exp[1])

    def test_a_scenario_without_exp1_is_refused(self):
        self.assertIn("does not keep EXP1 ↔ FE7",
                      self.refused(pc.Scenario("X", ((8, "FE15+FE16"), (7, "FE14")), ("E", "G12"), "no EXP1")))

    def test_one_record_for_two_fe_terms_is_refused(self):
        self.assertIn("ambiguous pairing",
                      self.refused(pc.Scenario("X", ((1, "FE7"), (1, "FE14")), ("E", "G12"), "twice")))

    def test_overlapping_fe_terms_are_refused(self):
        sens = {**self.sens, "FE15": dict(self.sens["FE14"])}
        c = pc.calculate(self.f_exp, sens, (pc.Scenario("X", ((1, "FE7"), (8, "FE15+FE16"), (9, "FE15")),
                                                        ("E", "G12"), "overlap"),)).candidate("X")
        self.assertEqual(c.status, pc.REFUSED_PAIRING)
        self.assertIn("shares an FE mode", c.reason)

    def test_a_branch_without_identity_is_refused(self):
        self.assertIn("FE8 has no central sensitivity",
                      self.refused(pc.Scenario("X", ((1, "FE7"), (2, "FE8")), ("E", "G12"), "lost branch")))

    def test_a_missing_record_is_refused_and_never_replaced(self):
        short = {n: hz for n, hz in self.f_exp.items() if n != 8}
        result = pc.calculate(short, self.sens)
        self.assertEqual(result.candidate("H1").status, pc.REFUSED_PAIRING)
        self.assertIn("EXP8 is not a record", result.candidate("H1").reason)
        self.assertTrue(result.candidate("S0").calculated)  # the other scenarios are not affected
        self.assertTrue(result.candidate("H2").calculated)

    def test_nothing_is_paired_by_frequency_and_mac_is_not_an_input(self):
        self.assertEqual(list(inspect.signature(pc.fit).parameters), ["scenario", "sens", "f_exp"])
        self.assertEqual(list(inspect.signature(pc.calculate).parameters), ["f_exp", "sens", "scenarios", "checks"])
        source = inspect.getsource(pc).lower()
        for forbidden in ("argmin", "nearest_fe", "modal_assurance", "subprocess", "abaqus job", "os.system"):
            self.assertNotIn(forbidden, source)
        # the other records move freely and change nothing
        other = {**self.f_exp, 2: 60.0, 9: 168.0, 10: 177.0}
        for key in ("S0", "H1", "H2"):
            self.assertEqual(pc.calculate(other, self.sens).candidate(key).G12,
                             pc.calculate(self.f_exp, self.sens).candidate(key).G12)


class SourceIdentityTests(unittest.TestCase):
    def setUp(self):
        self.sens = pc.load_sensitivities()
        self.fe = fe_frequencies(self.sens)
        self.fe_sha = ps.PLATE_FE_FAMILY[0].manifest.sha256

    def verify(self, **changes):
        arguments = {"experimental_sha256": ps.WORKING_SOURCE_SHA256, "set_names": ("55-2", ps.WORKING_SET, ""),
                     "record_numbers": range(1, 12), "fe_manifest_sha256": self.fe_sha,
                     "fe_frequencies_hz": self.fe, **changes}
        return pc.verify_sources(self.sens, **arguments)

    def test_the_real_identities_are_accepted(self):
        checks = dict(self.verify())
        self.assertEqual(set(checks), {"Experimental file", "Modal set", "FE package", "Sensitivities"})
        self.assertIn(ps.WORKING_SOURCE_SHA256, checks["Experimental file"])

    def test_another_experimental_file_is_refused(self):
        for sha in ("0" * 64, ps.AUXILIARY_FRF_SHA256, "", None):
            with self.assertRaises(pc.SourceMismatch) as refusal:
                self.verify(experimental_sha256=sha)
            self.assertIn("experimental file", refusal.exception.reasons[0])
        with self.assertRaises(pc.SourceMismatch) as refusal:
            self.verify(experimental_sha256=ps.M11_HISTORY_SHA256 + "0" * 52)
        self.assertIn(ps.HISTORY, refusal.exception.reasons[0])  # the 261016 session is history only

    def test_another_modal_set_is_refused(self):
        with self.assertRaises(pc.SourceMismatch) as refusal:
            self.verify(set_names=("55-1", "Polymax_alpha", ""))
        self.assertIn("not Polymax_bravo", str(refusal.exception))
        with self.assertRaises(pc.SourceMismatch) as refusal:
            self.verify(record_numbers=range(1, 7))
        self.assertIn("the scenarios use EXP8", str(refusal.exception))
        with self.assertRaises(pc.SourceMismatch):
            self.verify(record_numbers=[1, 2, 4, 5, 6, 7, 8, 9])

    def test_another_fe_package_is_refused(self):
        with self.assertRaises(pc.SourceMismatch) as refusal:
            self.verify(fe_manifest_sha256=ps.PLATE_FE_FAMILY[1].manifest.sha256)
        self.assertIn("S4R_0875_G12_10000", str(refusal.exception))
        with self.assertRaises(pc.SourceMismatch) as refusal:
            self.verify(fe_manifest_sha256="1" * 64)
        self.assertIn("not a member", str(refusal.exception))

    def test_fe_frequencies_that_are_not_the_base_point_are_refused(self):
        with self.assertRaises(pc.SourceMismatch) as refusal:
            self.verify(fe_frequencies_hz={**self.fe, 7: 19.5})
        self.assertIn("FE7 19.50000 Hz", str(refusal.exception))
        with self.assertRaises(pc.SourceMismatch) as refusal:
            self.verify(fe_frequencies_hz={k: v for k, v in self.fe.items() if k != 16})
        self.assertIn("FE15+FE16 missing", str(refusal.exception))

    def test_every_mismatch_is_listed(self):
        with self.assertRaises(pc.SourceMismatch) as refusal:
            self.verify(experimental_sha256="0" * 64, set_names=("x",), fe_manifest_sha256="1" * 64)
        self.assertEqual(len(refusal.exception.reasons), 3)

    def test_a_changed_sensitivity_table_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            relative = rr.SNAPSHOT_FILES["SENSITIVITIES"][0]
            target = Path(folder) / relative
            target.parent.mkdir(parents=True)
            with self.assertRaises(pc.Refused):
                pc.load_sensitivities(Path(folder))
            target.write_bytes((ROOT / relative).read_bytes().replace(b"0.48268", b"0.48269"))
            with self.assertRaises(pc.Refused):
                pc.load_sensitivities(Path(folder))
            target.write_bytes((ROOT / relative).read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
            self.assertEqual(pc.load_sensitivities(Path(folder)), self.sens)  # CRLF and LF checkouts agree

    def test_the_base_point_must_be_the_fe_models(self):
        member = ps.PLATE_FE_FAMILY[0]
        other = dataclasses.replace(member, parameters={**member.parameters, "G12": 5100.0})
        with mock.patch.object(ps, "PLATE_FE_FAMILY", (other,)):
            with self.assertRaises(pc.Refused):
                pc.calculate(archived_frequencies(), self.sens)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.result = pc.calculate(archived_frequencies(), checks=(("Experimental file", "SHA-256 test"),))
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name)

    def test_each_candidate_is_written_as_csv_and_txt(self):
        written = pc.export(self.result, self.folder, "20261113-120000")
        self.assertEqual(sorted(p.name for p in written),
                         sorted(f"plate_candidate_{k}_20261113-120000{s}" for k in ARCHIVED for s in (".csv", ".txt")))
        for key, (e1, e2, g12) in ARCHIVED.items():
            rows = list(csv.DictReader(io.StringIO((self.folder / f"plate_candidate_{key}_20261113-120000.csv")
                                                   .read_text(encoding="utf-8"))))
            parameters = {r["item"]: r for r in rows if r["section"] == "parameter"}
            self.assertEqual([float(parameters[n]["value"]) for n in ("E1", "E2", "G12")], [e1, e2, g12])
            self.assertEqual({n: float(parameters[n]["value"]) for n in ("E3", "nu12", "nu13", "nu23", "G13", "G23",
                                                                           "h", "rho")},
                             {"E3": 8500.0, "nu12": 0.05, "nu13": 0.3, "nu23": 0.3, "G13": 3000.0, "G23": 3000.0,
                              "h": 0.875, "rho": 1.498e-9})  # the fixed inputs of the FE model
            self.assertIn("fixed input", parameters["E3"]["note"])
            self.assertIn("CALCULATED", parameters["G12"]["note"])
            self.assertEqual(sum(1 for r in rows if r["section"] == "predicted frequency"), 10)
            self.assertEqual(sum(1 for r in rows if r["section"] == "measured frequency"), 11)
            self.assertTrue(any(r["section"] == "assumption" for r in rows))
            self.assertTrue(any(r["section"] == "limitation" for r in rows))
            text = (self.folder / f"plate_candidate_{key}_20261113-120000.txt").read_text(encoding="utf-8")
            self.assertIn("NOT verified by Abaqus and NOT a material property", text)
            self.assertIn(f"{e1:g}, {e2:g}, 8500, 0.05, 0.3, 0.3, {g12:g}, 3000,\n  3000", text)
            self.assertIn("NOT Abaqus results", text)
            self.assertIn("SHA-256 test", text)

    def test_an_existing_file_is_never_replaced_and_a_refusal_has_no_file(self):
        first = pc.export(self.result, self.folder, "s")
        before = {p: p.read_bytes() for p in first}
        second = pc.export(self.result, self.folder, "s")
        self.assertFalse(set(first) & set(second))
        self.assertEqual({p: p.read_bytes() for p in first}, before)
        short = pc.calculate({1: 18.6307})
        written = pc.export(short, self.folder, "short")
        self.assertEqual([p.name for p in written], ["plate_candidate_S0_short.csv", "plate_candidate_S0_short.txt"])
        with self.assertRaises(ValueError):
            pc.export(self.result, self.folder / "missing", "s")


class ResearchScriptTests(unittest.TestCase):
    def test_the_research_script_runs_the_same_implementation(self):
        sys.path.insert(0, str(ROOT / "research" / "plate_inverse"))
        try:
            import run_inverse
        finally:
            sys.path.remove(str(ROOT / "research" / "plate_inverse"))
        self.assertIs(run_inverse.fit, pc.fit)
        self.assertIs(run_inverse.predict, pc.predict)
        self.assertIs(run_inverse.SCENARIOS, pc.SCENARIOS)
        self.assertIs(run_inverse.SETTINGS, pc.SETTINGS)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


REAL_UNV = DELIVERY.joinpath(*Path(ps.WORKING_SOURCE.replace("\\", "/")).parts)
REAL_FE = ps.WORK_ROOT.joinpath(*Path(ps.PLATE_FE_FAMILY[0].manifest.relative).parts)


@unittest.skipUnless(REAL_UNV.is_file() and REAL_FE.is_file(), "the read-only plate originals are not here")
class RealPlateTests(unittest.TestCase):
    """The real 261027 UNV and the real M11 FE package, read with the application's own readers (read-only)."""

    @classmethod
    def setUpClass(cls):
        from new_gui import preview_model as pm
        from new_gui import workspace_state as ws

        cls.before = {REAL_UNV: _sha(REAL_UNV), REAL_FE: _sha(REAL_FE)}
        cls.experiment = pm.read_preview(ws.EXPERIMENTAL, REAL_UNV)
        cls.fe = pm.read_preview(ws.FE, REAL_FE)
        cls.identities = {"experimental": pm.file_identity(REAL_UNV), "fe": pm.fe_package_identity(REAL_FE)}

    def chosen(self):
        sets = [i for i, s in enumerate(self.experiment.sets)
                if ps.WORKING_SET in (s.key, s.display_name, s.processing_name)]
        self.assertEqual(len(sets), 1, [(s.key, s.display_name, s.processing_name) for s in self.experiment.sets])
        return sets[0]

    def test_the_candidates_are_calculated_from_the_real_files(self):
        from new_gui import plate_study_model as psm

        self.assertEqual(self.before[REAL_UNV], ps.WORKING_SOURCE_SHA256)
        view = psm.compute_candidates(self.fe, self.identities["fe"], self.experiment,
                                      self.identities["experimental"], self.chosen())
        result = view.result
        self.assertEqual(len(result.experiment), 11)
        records = self.experiment.sets[self.chosen()].records
        self.assertEqual([hz for _n, hz in result.experiment], [r.frequency_hz for r in records])  # read from the file
        for key, (e1, e2, g12) in ARCHIVED.items():
            c = result.candidate(key)
            self.assertEqual(c.status, pc.CONVERGED)
            self.assertEqual((round(c.E1, 1), round(c.E2, 1), round(c.G12, 1)), (e1, e2, g12))
            self.assertTrue(c.archive.reproduced)
            for x in c.residuals:
                self.assertLess(abs(x.after_percent), 0.02)
        self.assertEqual({name for name, _detail in view.check_rows},
                         {"Experimental file", "Modal set", "FE package", "Sensitivities"})
        self.assertEqual({REAL_UNV: _sha(REAL_UNV), REAL_FE: _sha(REAL_FE)}, self.before)  # the originals are untouched

    def test_another_set_of_the_same_file_is_refused(self):
        from new_gui import plate_study_model as psm

        others = [i for i in range(len(self.experiment.sets)) if i != self.chosen()]
        if not others:
            self.skipTest("the file holds one modal set")
        with self.assertRaises(pc.SourceMismatch):
            psm.compute_candidates(self.fe, self.identities["fe"], self.experiment, self.identities["experimental"],
                                   others[0])


if __name__ == "__main__":
    unittest.main()
