"""PLATE-CANDIDATES: Calculate parameter candidates on the Plate Study page (PySide6, Qt ``offscreen``).

On the synthetic plate family of ``test_plate_study_qt`` (temporary files whose SHA-256 stand for the working source
and the family members), with an FE package whose frequencies are the base point of the sensitivity table and a modal
set of eleven records:

- the command is off, with the reasons, until the working source and the baseline FE package are read;
- it calculates S0, H1 and H2 from the frequencies of the modal set read and shows E1, E2, G12, the measured and
  predicted frequencies, the residuals, the status, the rank and the warnings, each scenario apart;
- other measured frequencies give other values (the page does not show an archive), and the archived Abaqus records
  are shown apart as archived;
- another experimental file, another FE member, another modal set and a file changed on disk are refused;
- the export writes each candidate as CSV and TXT, and is refused when a file changed;
- no process is started, the iterative estimation stays disabled and the page does not grow wider.
"""

from __future__ import annotations

import csv
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

try:
    from PySide6.QtWidgets import QLabel
except ImportError as error:  # pragma: no cover - depends on the environment
    if os.environ.get("NEW_GUI_REQUIRE_QT") == "1":
        raise
    raise unittest.SkipTest(f"PySide6 is not installed ({error})")

from modal_core import ModalDataset, ModeShape  # noqa: E402
from new_gui import plate_study_model as psm  # noqa: E402
from new_gui import preview_model as pm  # noqa: E402
from new_gui import workspace_state as ws  # noqa: E402
from services import plate_candidate_results as pc  # noqa: E402
from services import plate_study as ps  # noqa: E402
from test_new_gui5_registration import experimental_preview, fe_preview  # noqa: E402
from test_plate_candidate_results import ARCHIVED, archived_frequencies, fe_frequencies  # noqa: E402
from test_plate_study_qt import _PlateWindow  # noqa: E402


def dataset(frequencies: dict, name: str, set_key: str = "") -> ModalDataset:
    """A small dataset with the given {number: Hz}; the shapes are not used by the calculation."""
    coordinates = np.array([[0.0, 0.0, 0.0], [0.3, 0.0, 0.0], [0.0, 0.3, 0.0], [0.3, 0.3, 0.0]])
    nodes = np.array([f"PLATE-1:{k + 1}" for k in range(4)], dtype=object)
    modes = []
    for number, hz in sorted(frequencies.items()):
        vectors = np.zeros((4, 3))
        vectors[:, 2] = np.cos(number * np.arange(4))
        modes.append(ModeShape(number, hz, nodes, coordinates, vectors))
    metadata = {"mode_source": "curve-fitted dataset 55"}
    if set_key:
        metadata["modal_set_key"] = set_key
    return ModalDataset(name, Path(name), modes, metadata=metadata)


class _CandidatesWindow(_PlateWindow):
    measured = None  # {record: Hz}; the archived series' frequencies when None
    set_key = ps.WORKING_SET

    def setUp(self):
        super().setUp()
        sens = pc.load_sensitivities()
        self.fe_datasets = {"base": dataset(fe_frequencies(sens), "baseline FE"),
                            "e1": dataset({**fe_frequencies(sens), 13: 160.0}, "E1 variant")}
        self.measured_hz = dict(self.measured or archived_frequencies())
        experiment = dataset(self.measured_hz, "experiment", self.set_key)

        def read(kind, path, cancel_event=None):
            path = Path(path)
            if path.name == "manifest.json":
                return fe_preview(path, self.fe_datasets[path.parent.name])
            return experimental_preview(path, [experiment])

        patcher = mock.patch.object(pm, "read_preview", side_effect=read)
        patcher.start()
        self.addCleanup(patcher.stop)

    def read(self, experiment="plate.unv", fe="base/manifest.json"):
        for kind, name in ((ws.FE, fe), (ws.EXPERIMENTAL, experiment)):
            self.assertEqual(self.window.choose_file(kind, str(self.files[name])), "")
            self.assertTrue(self.window.inspect_file(kind))
        self.assertTrue(self.window.wait_for_reads(120))
        self.window.diagnostic.set_combo.setCurrentIndex(1)
        self.app.processEvents()

    def calculate(self):
        self.assertTrue(self.panel.calculate_button.isEnabled(), self.panel.candidates_why.text())
        self.panel.calculate_button.click()
        self.assertTrue(self.window.wait_for_reads(120))
        self.app.processEvents()

    def cells(self, key):
        table = self.panel.candidate_tables[key]
        return [[table.item(r, c).text() for c in range(table.columnCount())] for r in range(table.rowCount())]

    def texts(self):
        return "\n".join(label.text() for label in self.panel.candidates_card.findChildren(QLabel))


class CalculationTests(_CandidatesWindow):
    def test_the_command_is_visible_and_off_until_the_plate_files_are_read(self):
        self.assertEqual(self.panel.calculate_button.text(), "Calculate parameter candidates")
        self.assertFalse(self.panel.calculate_button.isHidden())
        self.assertFalse(self.panel.calculate_button.isEnabled())
        self.assertFalse(self.panel.candidates_export_button.isEnabled())
        self.assertIn("working source", self.panel.candidates_why.text())
        self.assertIn("baseline FE package", self.panel.candidates_why.text())
        self.assertFalse(self.panel.candidates_card.isVisible())
        self.assertFalse(self.panel.calculate_candidates())

    def test_the_candidates_are_calculated_and_shown_scenario_by_scenario(self):
        self.read()
        with mock.patch.object(subprocess, "Popen", side_effect=AssertionError("no process")) as popen:
            self.calculate()
        popen.assert_not_called()
        view = self.panel.candidates_view
        self.assertIsNotNone(view, self.panel.candidates_status.text())
        self.assertTrue(self.panel.candidates_card.isVisible())
        summary = self.cells("summary")
        self.assertEqual([row[0] for row in summary], ["S0", "H1", "H2"])  # the declared order, each on its own
        for row in summary:
            e1, e2, g12 = ARCHIVED[row[0]]
            self.assertEqual(row[1:4], [f"{e1:.1f}", f"{e2:.1f}", f"{g12:.1f}"])  # MPa
            self.assertEqual(row[5], "CONVERGED")
        self.assertEqual([row[6:8] for row in summary], [["1 of 1", "1 of 3"], ["2 of 2", "2 of 3"],
                                                         ["2 of 2", "2 of 3"]])
        h1 = self.cells("H1:hypotheses")
        self.assertEqual([row[0] for row in h1], ["EXP1 ↔ FE7", "EXP8 ↔ FE15+FE16"])
        self.assertEqual([row[1] for row in h1], ["18.6307", "157.8508"])  # measured, from the set read
        self.assertEqual(h1[0][2], "19.07217")
        self.assertAlmostEqual(float(h1[1][3]), 157.8688, delta=2e-4)  # predicted by the model
        self.assertLess(abs(float(h1[1][5])), 0.02)
        self.assertEqual({row[6] for row in h1}, {psm.HYPOTHETICAL})
        for key in ("S0", "H1", "H2"):  # EXP1 is kept by every scenario
            self.assertEqual(self.cells(f"{key}:hypotheses")[0][:2], ["EXP1 ↔ FE7", "18.6307"])
            self.assertEqual(len(self.cells(f"{key}:predictions")), 10)
        experiment = self.cells("experiment")
        self.assertEqual(len(experiment), 11)
        self.assertEqual(experiment[0], ["EXP1", "18.6307", "S0, H1, H2"])
        self.assertEqual(experiment[1][2], "not used — not paired")
        self.assertEqual([row[0] for row in self.cells("checks")],
                         ["Experimental file", "Modal set", "FE package", "Sensitivities"])
        texts = self.texts()
        for expected in (psm.CANDIDATES_BADGE, "CALCULATED now", "EXTRAPOLATION: E ×0.7762", "AMBIGUITY",
                         "outside the 15 % window", "NOT determined", "not separable", "None is preferred",
                         "NOT_A_MATERIAL_PROPERTY", "not an uncertainty interval"):
            self.assertIn(expected, texts)
        for forbidden in ("validated material", "best scenario", "recommended", "MATCH_CONFIRMED"):
            self.assertNotIn(forbidden, texts.replace("NOT VALIDATED MATERIAL PROPERTIES", "").lower())
        self.assertFalse(self.panel.gate_button.isEnabled())  # the iterative estimation stays not authorised
        self.assertIsNone(self.panel.view)  # the plate study itself was not run and is not changed

    def test_the_archived_abaqus_records_are_shown_apart_as_archived(self):
        self.read()
        self.calculate()
        archive = self.cells("H2:archive")
        self.assertEqual(archive, [["EXP1 ↔ FE7", "18.6307", "18.62512", "-0.0298"],
                                   ["EXP7 ↔ FE14", "145.9357", "145.95451", "0.0129"]])
        self.assertNotEqual(self.cells("H2:hypotheses")[1][3], archive[1][2])  # the model's value is not Abaqus'
        self.assertIn("ARCHIVED Abaqus verification", self.texts())
        self.assertIn("REPRODUCED to the archive's 0.1 MPa", self.texts())

    def test_the_result_adds_no_width_to_the_page(self):
        self.read()
        before = self.panel.minimumSizeHint().width()
        self.calculate()
        self.assertIsNotNone(self.panel.candidates_view)
        self.assertLessEqual(self.panel.minimumSizeHint().width(), before)

    def test_new_files_remove_the_candidates(self):
        self.read()
        self.calculate()
        self.assertIsNotNone(self.panel.candidates_view)
        self.window.choose_file(ws.EXPERIMENTAL, str(self.files["m11.unv"]))
        self.app.processEvents()
        self.assertIsNone(self.panel.candidates_view)
        self.assertFalse(self.panel.candidates_card.isVisible())
        self.assertFalse(self.panel.candidates_export_button.isEnabled())


class OtherFrequenciesTests(_CandidatesWindow):
    measured = {**archived_frequencies(), 1: 18.9, 8: 160.0}

    def test_the_values_follow_the_file_read_and_not_the_archive(self):
        self.read()
        self.calculate()
        summary = {row[0]: row for row in self.cells("summary")}
        result = pc.calculate(self.measured)
        for key in ("S0", "H1", "H2"):
            c = result.candidate(key)
            self.assertEqual(summary[key][1:4], [f"{c.E1:.1f}", f"{c.E2:.1f}", f"{c.G12:.1f}"])
            self.assertNotEqual(summary[key][3], f"{ARCHIVED[key][2]:.1f}")
        self.assertEqual(self.cells("H1:hypotheses")[1][1], "160.0000")
        self.assertIn("NOT reproduced", self.texts())
        self.assertNotIn("REPRODUCED to", self.texts())


class RefusalTests(_CandidatesWindow):
    def test_another_experimental_file_is_refused(self):
        self.read("m11.unv")
        self.assertFalse(self.panel.calculate_button.isEnabled())
        self.assertIn(ps.UNKNOWN_SOURCE, self.panel.candidates_why.text())
        self.assertFalse(self.panel.calculate_candidates())
        self.assertIsNone(self.panel.candidates_view)

    def test_another_member_of_the_fe_family_is_refused(self):
        self.read(fe="e1/manifest.json")
        self.assertTrue(self.panel.run_button.isEnabled())  # the plate study accepts a family member
        self.assertFalse(self.panel.calculate_button.isEnabled())  # the calculation needs the baseline model
        self.assertIn("V_E1", self.panel.candidates_why.text())
        self.assertIn("not the baseline model", self.panel.candidates_why.text())

    def test_a_file_changed_after_inspect_is_refused(self):
        self.read()
        self.files["plate.unv"].write_text("changed after the read", encoding="utf-8")
        self.calculate()
        self.assertIsNone(self.panel.candidates_view)
        self.assertFalse(self.panel.candidates_card.isVisible())
        self.assertIn("The candidates were not calculated", self.panel.candidates_status.text())
        self.assertIn("changed since Inspect file read it", self.panel.candidates_status.text())

    def test_fe_frequencies_off_the_base_point_are_refused(self):
        self.fe_datasets["base"] = dataset({**fe_frequencies(pc.load_sensitivities()), 7: 19.5}, "other baseline")
        self.read()
        self.calculate()
        self.assertIsNone(self.panel.candidates_view)
        self.assertIn("not the base point of the sensitivity table", self.panel.candidates_status.text())


class OtherSetTests(_CandidatesWindow):
    set_key = "Polymax_alpha"

    def test_another_modal_set_is_refused(self):
        self.read()
        self.calculate()
        self.assertIsNone(self.panel.candidates_view)
        self.assertIn("not Polymax_bravo", self.panel.candidates_status.text())


class ShortSetTests(_CandidatesWindow):
    measured = {n: hz for n, hz in archived_frequencies().items() if n <= 6}

    def test_a_set_without_the_declared_records_is_refused(self):
        self.read()
        self.calculate()
        self.assertIsNone(self.panel.candidates_view)
        self.assertIn("the scenarios use EXP8", self.panel.candidates_status.text())


class ExportTests(_CandidatesWindow):
    def test_each_candidate_is_exported_as_csv_and_txt(self):
        self.read()
        self.calculate()
        self.assertTrue(self.panel.candidates_export_button.isEnabled())
        self.panel.candidates_export_button.click()
        self.app.processEvents()
        written = sorted(p.name for p in self.reports.iterdir())
        self.assertEqual(len(written), 6)
        self.assertEqual({name.split("_")[2] for name in written}, {"S0", "H1", "H2"})
        self.assertEqual(sorted(Path(name).suffix for name in written), [".csv"] * 3 + [".txt"] * 3)
        for path in self.reports.glob("*.csv"):
            key = path.name.split("_")[2]
            rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))
            values = {r["item"]: float(r["value"]) for r in rows if r["section"] == "parameter"}
            self.assertEqual((values["E1"], values["E2"], values["G12"]), ARCHIVED[key])
            self.assertEqual((values["E3"], values["nu12"], values["h"]), (8500.0, 0.05, 0.875))
        text = next(self.reports.glob("*H1*.txt")).read_text(encoding="utf-8")
        self.assertIn("43467, 43467, 8500, 0.05, 0.3, 0.3, 4804.4, 3000,", text)
        self.assertIn(str(self.files["plate.unv"]), text)
        self.assertIn("Candidates written for a manual Abaqus check", self.panel.candidates_status.text())
        self.assertIsNotNone(self.panel.candidates_view)  # the result stays on the page

    def test_the_export_is_refused_when_a_file_changed(self):
        self.read()
        self.calculate()
        self.files["plate.unv"].write_text("changed after the calculation", encoding="utf-8")
        self.assertTrue(self.panel.export_candidates())
        self.assertEqual(list(self.reports.iterdir()), [])
        self.assertIn("The candidates were not written", self.panel.candidates_status.text())

    def test_nothing_is_exported_without_a_calculation(self):
        self.read()
        self.assertFalse(self.panel.export_candidates())
        self.assertEqual(list(self.reports.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
