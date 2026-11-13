"""ABM-RITZ-EXPORT-1: the candidates of the existing Kirchhoff-Ritz tuning as files for a manual Abaqus run.

The numerical tests use frequencies computed by the surrogate itself at known values. The test on the real plate files
runs only where those files are; elsewhere it is skipped, and a skip is not a pass."""

from __future__ import annotations

import csv
import dataclasses
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
for entry in (ROOT / "src", ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import test_real_fit_r1_tuning as base  # noqa: E402
from new_gui import research_tuning_model as rm  # noqa: E402
from services import research_frequency_tuning as rft  # noqa: E402

REAL_INP = Path(r"I:\sandwich\Abaqus Results\temp\CFRP_S4R_0875_FreeFree.inp")
REAL_UNV = Path(r"I:\sandwich\exp\SPname_files_ROTATED_261103\300by300_plate_only_1mm_ROTATED_Polymax_261027.unv")
# REAL-FIT.R4/R5 (docs/materials/REAL_FIT_R4_PREFLIGHT_REPORT.md): the two archived Ritz minima, MPa, and their costs
ARCHIVED = {"A": {"E1": 59643.140320162354, "E2": 43592.56647783119, "G12": 4824.07010224442, "cost": 0.0008452616410310549},
            "B": {"E1": 44170.77433673189, "E2": 58724.14887983508, "G12": 4817.417308245888, "cost": 0.0008576605619306323}}
ARCHIVED_LINES = {"A": "59643.140320162354, 43592.56647783119, 8500.0, 0.05, 0.3, 0.3, 4824.07010224442, 3000.0",
                  "B": "44170.77433673189, 58724.14887983508, 8500.0, 0.05, 0.3, 0.3, 4817.417308245888, 3000.0"}


def _sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _sources(records):
    """Real files on disk with their own hashes: the INP of the R1 tests and a stand-in for the experimental file."""
    folder = base._files()
    unv = folder / "exp.unv"
    unv.write_bytes(b"stand-in for the experimental file\n")
    inputs = rft.read_inp(folder / "plate.inp")
    return rm.Sources(inputs, None, (), (), "unavailable (test)", str(unv), _sha(unv), "Set", tuple(records)), folder


def _numbers(line: str) -> list:
    return [float(item) for item in line.replace(",", " ").split()]


class _Fitted(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        inputs = rft.read_inp(base._files() / "plate.inp")
        surrogate = rft.Surrogate(inputs, 10, 16)

        def fit(E1, E2, G12, parameterization):
            spectrum = surrogate.frequencies(E1, E2, G12)
            records = [(k + 1, float(spectrum[k])) for k in range(9)]
            sources, folder = _sources(records)
            request = rft.TuningRequest(rft.observations_by_rank(records, holdout=(8, 9)), parameterization, degree=10)
            return rft.run_tuning(sources.inputs, request), sources, folder

        cls.mirror, cls.sources, cls.folder = fit(60000, 44000, 4800, rft.FREE)
        cls.tied, cls.tied_sources, _folder = fit(42000, 42000, 6500, rft.TIED)
        assert cls.mirror.status == rft.MIRROR and cls.tied.status == rft.SUPPORTED


class Candidates(_Fitted):
    def test_both_mirror_minima_are_candidates_and_neither_is_chosen(self):
        found = rm.abaqus_candidates(self.mirror)
        self.assertEqual([c["key"] for c in found], ["A", "B"])
        for candidate, assignment in zip(found, self.mirror.axis_assignments):  # the tuning's own doubles, untouched
            self.assertEqual((candidate["E1"], candidate["E2"], candidate["G12"], candidate["cost"]),
                             (assignment["E1 (FE X)"], assignment["E2 (FE Y)"], assignment["G12"], assignment["cost"]))
        self.assertGreater(found[0]["E1"], found[0]["E2"])  # the two assignments are exchanged
        self.assertLess(found[1]["E1"], found[1]["E2"])
        documents = rm.abaqus_documents(self.mirror, self.sources)
        self.assertEqual([d["stem"] for d in documents], ["ritz_candidate_A_abaqus", "ritz_candidate_B_abaqus"])
        for document in documents:
            self.assertIn(rm.ABAQUS_MIRROR, document["txt"])
            self.assertIn("neither is selected or preferred", document["txt"])
            self.assertIn(rft.RESULT_LABEL, document["txt"])
            self.assertIn("NOT VALIDATED IN ABAQUS", document["txt"])
            self.assertIn("NOT A MATERIAL PROPERTY", document["txt"])
            self.assertIn(rft.NOT_ESTABLISHED, document["txt"])
            for word in ("validated material", "identified material", "recommended", "best candidate"):
                self.assertNotIn(word, document["txt"].lower())

    def test_one_oriented_candidate_of_a_tied_fit(self):
        found = rm.abaqus_candidates(self.tied)
        self.assertEqual([c["key"] for c in found], [""])
        self.assertEqual((found[0]["E1"], found[0]["E2"], found[0]["G12"]),
                         (self.tied.candidate["E1"], self.tied.candidate["E2"], self.tied.candidate["G12"]))
        (document,) = rm.abaqus_documents(self.tied, self.tied_sources)
        self.assertEqual(document["stem"], "ritz_candidate_abaqus")
        self.assertNotIn(rm.ABAQUS_MIRROR, document["txt"])
        self.assertIn("fitted as E1 = E2", document["txt"])

    def test_no_file_for_a_result_without_a_usable_candidate(self):
        high = dataclasses.replace(self.mirror, fit_quality=dict(self.mirror.fit_quality, verdict=rft.HIGH_MISFIT))
        self.assertEqual(rm.abaqus_candidates(high), ())
        self.assertIn("HIGH MISFIT", rm.abaqus_export_unavailable(high, self.sources))
        for status in (rft.NOT_IDENTIFIABLE, rft.AT_BOUND, rft.NOT_CONVERGED, rft.STARTS_DISAGREE):
            other = dataclasses.replace(self.mirror, status=status, axis_assignments=[])
            self.assertEqual(rm.abaqus_candidates(other), ())
            self.assertIn(status, rm.abaqus_export_unavailable(other, self.sources))
        self.assertIn("run the tuning first", rm.abaqus_export_unavailable(None, self.sources))
        self.assertIn("saved result", rm.abaqus_export_unavailable(self.mirror, self.sources, saved=True))
        self.assertIn("registered route", rm.abaqus_export_unavailable(self.mirror, self.sources, registered=True))
        lamina = dataclasses.replace(self.sources, inputs=dataclasses.replace(self.sources.inputs, elastic_type="LAMINA"))
        self.assertIn("type=LAMINA", rm.abaqus_export_unavailable(self.mirror, lamina))
        with self.assertRaises(rft.TuningRefused):
            rm.abaqus_documents(high, self.sources)
        self.assertEqual(rm.abaqus_export_unavailable(self.mirror, self.sources), "")


class Precision(_Fitted):
    def test_every_digit_is_written_and_reads_back_as_the_same_double(self):
        for document, candidate in zip(rm.abaqus_documents(self.mirror, self.sources), rm.abaqus_candidates(self.mirror)):
            first, second = _numbers(document["lines"][1]), _numbers(document["lines"][2])
            self.assertEqual((first[0], first[1], first[6]), (candidate["E1"], candidate["E2"], candidate["G12"]))  # exact
            self.assertEqual(second, [3000.0])
            rows = {(r[0], r[1]): r for r in csv.reader(io.StringIO(document["csv"]))}
            for name in ("E1", "E2", "G12"):
                self.assertEqual(float(rows[("parameter", name)][2]), candidate[name])
                self.assertEqual(rows[("parameter", name)][2], repr(candidate[name]))
                self.assertIn(repr(candidate[name]), document["txt"])
            self.assertNotEqual(float(f"{candidate['E1']:.6g}"), candidate["E1"])  # six digits would not be the value

    def test_the_archived_minima_are_written_exactly(self):
        """The REAL-FIT.R4 doubles through the same writer: the text of the archived decks' numbers, digit for digit."""
        axes = [{"assignment": f"assignment {key}", "E1 (FE X)": v["E1"], "E2 (FE Y)": v["E2"], "G12": v["G12"], "cost": v["cost"]}
                for key, v in ARCHIVED.items()]
        result = dataclasses.replace(self.mirror, axis_assignments=axes)
        for candidate in rm.abaqus_candidates(result):
            lines = rm.abaqus_lines(self.sources.inputs, candidate)
            self.assertEqual(lines[1], ARCHIVED_LINES[candidate["key"]])
            self.assertEqual(lines[2], "3000.0,")
            self.assertLessEqual(max(len(item.strip()) for item in lines[1].split(",")), rm.ABAQUS_FIELD_CHARS)
        self.assertEqual(rm.full(59643.140320162354), "59643.140320162354")

    def test_a_number_too_long_for_an_abaqus_item_is_refused(self):
        with self.assertRaises(rft.TuningRefused):
            rm.abaqus_lines(dataclasses.replace(self.sources.inputs, E3=1.2345678901234567e-105),
                            rm.abaqus_candidates(self.mirror)[0])


class FieldOrder(_Fitted):
    def test_engineering_constants_order_e1_e2_e3_nu12_nu13_nu23_g12_g13_then_g23(self):
        inputs = dataclasses.replace(self.sources.inputs, E3=8501.0, nu12=0.051, nu13=0.31, nu23=0.32, G13=3001.0, G23=3002.0)
        candidate = {"E1": 60001.5, "E2": 44002.5, "G12": 4803.5}
        lines = rm.abaqus_lines(inputs, candidate)
        self.assertEqual(lines[0], "*Elastic, type=ENGINEERING CONSTANTS")
        self.assertEqual(_numbers(lines[1]), [60001.5, 44002.5, 8501.0, 0.051, 0.31, 0.32, 4803.5, 3001.0])
        self.assertEqual(_numbers(lines[2]), [3002.0])
        self.assertEqual(len(lines), 3)  # eight items on the first data line, G23 alone on the second

    def test_the_block_put_into_a_copy_of_the_inp_is_read_back_by_the_program(self):
        original = (self.folder / "plate.inp").read_text(encoding="latin-1")
        for document, candidate in zip(rm.abaqus_documents(self.mirror, self.sources), rm.abaqus_candidates(self.mirror)):
            copy = Path(tempfile.mkdtemp()) / "copy.inp"
            copy.write_text(original.replace("*Elastic, type=ENGINEERING CONSTANTS\n56000.,56000., 8500.,  0.05,   0.3,   0.3, "
                                             "5000., 3000.\n 3000.,", "\n".join(document["lines"])), encoding="latin-1")
            read = rft.read_inp(copy)
            self.assertEqual((read.E1, read.E2, read.G12), (candidate["E1"], candidate["E2"], candidate["G12"]))
            self.assertEqual((read.E3, read.nu12, read.nu13, read.nu23, read.G13, read.G23), (8500.0, 0.05, 0.3, 0.3, 3000.0, 3000.0))
            self.assertEqual((read.density_t_mm3, read.thickness_mm), (1.498e-09, 0.875))

    def test_the_fixed_inputs_are_the_inp_values(self):
        (document, _other) = rm.abaqus_documents(self.mirror, self.sources)
        rows = {(r[0], r[1]): r for r in csv.reader(io.StringIO(document["csv"]))}
        expected = {"E3": 8500.0, "nu12": 0.05, "nu13": 0.3, "nu23": 0.3, "G13": 3000.0, "G23": 3000.0, "Density": 1.498e-09,
                    "Shell thickness": 0.875}
        for name, value in expected.items():
            self.assertEqual(float(rows[("parameter", name)][2]), value)
        self.assertEqual(rows[("parameter", "Density")][3], "t/mm^3")
        self.assertEqual(rows[("parameter", "Shell thickness")][3], "mm")
        self.assertEqual(float(rows[("inp_value", "E1")][2]), 56000.0)
        self.assertEqual(rows[("abaqus_density", "line 2")][2], "1.498e-09,")
        self.assertIn("*Density\n1.498e-09,", document["txt"])


class Frequencies(_Fitted):
    def test_the_best_minimum_has_the_frequencies_the_tuning_reported(self):
        first, second = rm.abaqus_documents(self.mirror, self.sources)
        for mine, theirs in zip(first["rows"], self.mirror.rows):
            self.assertEqual((mine["record"], mine["role"], mine["rank"], mine["exp_hz"]),
                             (theirs["record"], theirs["role"], theirs["rank"], theirs["exp_hz"]))
            self.assertAlmostEqual(mine["ritz_hz"] / theirs["ritz_after_hz"], 1.0, delta=1e-12)
            self.assertAlmostEqual(mine["ln"], theirs["ln_after"], delta=1e-12)
        self.assertNotEqual([r["ritz_hz"] for r in first["rows"]], [r["ritz_hz"] for r in second["rows"]])

    def test_each_candidate_has_its_own_residuals_equal_to_its_cost(self):
        for document, candidate in zip(rm.abaqus_documents(self.mirror, self.sources), rm.abaqus_candidates(self.mirror)):
            fit = [r["ln"] for r in document["rows"] if r["role"] == rft.FIT]
            self.assertEqual(len(fit), 7)
            self.assertAlmostEqual(0.5 * sum(v * v for v in fit), candidate["cost"], delta=1e-12 + 1e-6 * candidate["cost"])
            self.assertIn("half the sum of ln^2 over FIT", document["txt"])
            rows = [r for r in csv.reader(io.StringIO(document["csv"]))]
            self.assertEqual(len([r for r in rows if r[0] == "frequency_exp"]), 9)
            self.assertEqual(len([r for r in rows if r[0] == "frequency_ritz"]), 9)
            self.assertEqual(len([r for r in rows if r[0] == "residual_ln"]), 9)
            self.assertIn("HOLDOUT", document["txt"])
            for item in self.mirror.assumptions:
                self.assertIn(item, document["txt"])

    def test_an_excluded_record_is_listed_without_a_prediction(self):
        records = list(self.sources.records)
        request = rft.TuningRequest(rft.observations_by_rank(records, holdout=(9,), excluded=(8,)), rft.FREE, degree=10)
        result = rft.run_tuning(self.sources.inputs, request)
        self.assertEqual(result.status, rft.MIRROR)
        (document, _other) = rm.abaqus_documents(result, self.sources)
        row = next(r for r in document["rows"] if r["record"] == 8)
        self.assertEqual((row["role"], row["rank"], row["ritz_hz"], row["ln"]), (rft.EXCLUDED, None, None, None))


class Files(_Fitted):
    def test_the_files_are_written_and_the_sources_are_unchanged(self):
        watched = [self.folder / "plate.inp", self.folder / "plate.dat", Path(self.sources.unv_path)]
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in watched}
        target = Path(tempfile.mkdtemp())
        written = rm.export_abaqus(self.mirror, self.sources, target, "20260101_000000")
        self.assertEqual(sorted(p.name for p in written), ["ritz_candidate_A_abaqus_20260101_000000.csv",
                                                           "ritz_candidate_A_abaqus_20260101_000000.txt",
                                                           "ritz_candidate_B_abaqus_20260101_000000.csv",
                                                           "ritz_candidate_B_abaqus_20260101_000000.txt"])
        self.assertEqual(sorted(p.name for p in target.iterdir()), sorted(p.name for p in written))
        self.assertEqual({p: (p.read_bytes(), p.stat().st_mtime_ns) for p in watched}, before)
        text = (target / "ritz_candidate_A_abaqus_20260101_000000.txt").read_text(encoding="utf-8")
        self.assertIn("*Elastic, type=ENGINEERING CONSTANTS", text)
        self.assertIn(self.sources.inputs.inp_sha256, text)
        with self.assertRaises(rft.TuningRefused):  # nothing is ever replaced
            rm.export_abaqus(self.mirror, self.sources, target, "20260101_000000")
        into_the_source_folder = rm.export_abaqus(self.mirror, self.sources, self.folder, "20260101_000001")
        self.assertEqual(len(into_the_source_folder), 4)
        self.assertEqual({p: (p.read_bytes(), p.stat().st_mtime_ns) for p in watched}, before)

    def test_a_changed_source_file_is_refused(self):
        sources, folder = _sources(self.sources.records)
        target = Path(tempfile.mkdtemp())
        (folder / "plate.inp").write_text(base.INP.replace("56000.,56000.", "57000.,56000."), encoding="latin-1")
        with self.assertRaises(rft.TuningRefused) as caught:
            rm.export_abaqus(self.mirror, sources, target, "s")
        self.assertIn("INP changed", str(caught.exception))
        self.assertEqual(list(target.iterdir()), [])
        sources, _folder = _sources(self.sources.records)
        Path(sources.unv_path).unlink()
        with self.assertRaises(rft.TuningRefused) as caught:
            rm.export_abaqus(self.mirror, sources, target, "s")
        self.assertIn("experimental file cannot be read", str(caught.exception))


class Page(base._PageHarness):
    def loaded(self, records):
        sources, folder = _sources(records)
        window, panel = self.window()
        with mock.patch.object(rm, "read_sources", return_value=sources):
            panel.choose_file("inp", str(folder / "plate.inp"))
            panel.choose_file("unv", sources.unv_path)
            self.wait(panel)
        return window, panel, sources

    def spectrum(self, E1, E2, G12):
        values = rft.Surrogate(rft.read_inp(base._files() / "plate.inp"), 14, 16).frequencies(E1, E2, G12)
        return [(k + 1, float(values[k])) for k in range(10)]

    def test_the_button_exports_both_mirror_candidates_from_the_normal_window(self):
        from new_gui import production_window as pw

        window, panel, sources = self.loaded(self.spectrum(60000, 44000, 4800))
        self.assertIsInstance(window, pw.ProductionWindow)
        self.assertEqual(panel.abaqus_button.text(), "Export for Abaqus (TXT/CSV)...")
        self.assertFalse(panel.abaqus_button.isEnabled())
        self.assertIn("run the tuning first", panel.abaqus_note.text())
        self.assertFalse(panel.export_abaqus(tempfile.mkdtemp()))
        panel.parameterization.setCurrentIndex(panel.parameterization.findData(rft.FREE))
        self.assertTrue(panel.run())
        self.assertFalse(panel.abaqus_button.isEnabled())  # not under a running fit
        self.wait(panel)
        self.assertEqual(panel.result.status, rft.MIRROR)
        self.assertTrue(panel.abaqus_button.isEnabled())
        self.assertTrue(panel.abaqus_button.isVisible())
        self.assertIn("neither is selected", panel.abaqus_note.text())
        target = Path(tempfile.mkdtemp())
        panel._ask_folder = lambda start: str(target)
        with mock.patch("subprocess.Popen", side_effect=AssertionError("no process")):
            panel.abaqus_button.click()
        self.app.processEvents()
        names = sorted(p.name for p in target.iterdir())
        self.assertEqual(len(names), 4)
        self.assertEqual([n[:17] for n in names], ["ritz_candidate_A_", "ritz_candidate_A_", "ritz_candidate_B_", "ritz_candidate_B_"])
        self.assertIn("Exported for Abaqus", panel.export_note.text())
        self.assertIn("not a material property", panel.export_note.text())
        for key, assignment in zip("AB", panel.result.axis_assignments):
            text = next(target.glob(f"ritz_candidate_{key}_*.txt")).read_text(encoding="utf-8")
            for name in ("E1 (FE X)", "E2 (FE Y)", "G12"):
                self.assertIn(repr(assignment[name]), text)
        self.assertEqual(panel.result.status, rft.MIRROR)  # the result is as it was: no candidate was chosen
        self.assertIsNone(panel.result.candidate)
        self.assertNotIn("candidate", panel._tables)
        panel._ask_folder = lambda start: ""  # the dialog closed without a folder
        self.assertFalse(panel.export_abaqus())

    def test_a_single_candidate_and_a_changed_source(self):
        window, panel, sources = self.loaded(self.spectrum(45000, 45000, 6000))
        self.assertTrue(panel.run())
        self.wait(panel)
        self.assertEqual(panel.result.status, rft.SUPPORTED)
        self.assertTrue(panel.abaqus_button.isEnabled())
        target = Path(tempfile.mkdtemp())
        self.assertTrue(panel.export_abaqus(str(target)))
        self.assertEqual(len(list(target.glob("ritz_candidate_abaqus_*"))), 2)
        Path(sources.unv_path).write_bytes(b"another file\n")
        other = Path(tempfile.mkdtemp())
        self.assertFalse(panel.export_abaqus(str(other)))
        self.assertIn("Not exported", panel.message.text())
        self.assertEqual(list(other.iterdir()), [])

    def test_a_saved_result_has_no_abaqus_export(self):
        window, panel, sources = self.loaded(self.spectrum(60000, 44000, 4800))
        panel.parameterization.setCurrentIndex(panel.parameterization.findData(rft.FREE))
        self.assertTrue(panel.run())
        self.wait(panel)
        saved = Path(tempfile.mkdtemp()) / "proposal.json"
        self.assertTrue(panel.export(str(saved)))
        self.assertTrue(panel.open_result(str(saved)))
        self.assertFalse(panel.abaqus_button.isEnabled())
        self.assertIn("saved result", panel.abaqus_note.text())
        self.assertFalse(panel.export_abaqus(tempfile.mkdtemp()))


@unittest.skipUnless(REAL_INP.is_file() and REAL_UNV.is_file(), "the real plate INP and UNV are not on this machine")
class RealPlate(base._PageHarness):
    """The real M11 S4R deck and the PolyMAX file of 27 October 2026, read only, through the page itself."""

    def test_the_real_tuning_reproduces_the_archived_minima_and_exports_them(self):
        watched = [REAL_INP, REAL_UNV]
        before = {p: _sha(p) for p in watched}
        window, panel = self.window()
        panel.choose_file("inp", str(REAL_INP))
        panel.choose_file("unv", str(REAL_UNV))
        self.wait(panel, 300.0)
        self.assertIsNotNone(panel.sources, panel.message.text())
        panel.parameterization.setCurrentIndex(panel.parameterization.findData(rft.FREE))
        self.assertTrue(panel.run())
        self.wait(panel, 900.0)
        self.assertEqual(panel.result.status, rft.MIRROR, panel.result.reasons)
        found = {c["key"]: c for c in rm.abaqus_candidates(panel.result)}
        for key, archived in ARCHIVED.items():
            for name in ("E1", "E2", "G12", "cost"):
                self.assertEqual(found[key][name], archived[name], f"{key} {name}")  # bit for bit
        target = Path(tempfile.mkdtemp())
        self.assertTrue(panel.export_abaqus(str(target)))
        for key in "AB":
            text = next(target.glob(f"ritz_candidate_{key}_*.txt")).read_text(encoding="utf-8")
            self.assertIn(ARCHIVED_LINES[key] + "\n3000.0,", text)
            self.assertIn("*Density\n1.498e-09,", text)
            self.assertIn(before[REAL_INP], text)
            self.assertIn(before[REAL_UNV], text)
        self.assertEqual({p: _sha(p) for p in watched}, before)


if __name__ == "__main__":
    unittest.main()
