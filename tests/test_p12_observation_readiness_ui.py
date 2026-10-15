"""P12 — Observation Readiness section of the Data Readiness page.

The section shows the P11 observation-readiness record of one explicitly selected governed forward model: data
governance, the SPEC v1.2 §8 count for k = 1 (and a k = 9 observation-deficit diagnostic), numerical identifiability
NOT_ASSESSED and scientific readiness NOT_DECLARED. It is kept apart from the READY / WARNING / BLOCKED data-readiness
gate, never selects a model by itself, never turns a failure into a count, and runs no calibration, FE or process.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import material_identification_ui as ui  # noqa: E402
from services.observation_readiness import (  # noqa: E402
    PREREQUISITES,
    DataStatus,
    GovernanceItem,
    ReadinessEvidence,
    StrictRow,
    build_observation_readiness,
    modal_input_item,
)
from domain.modal_input_source import ModalInputSource  # noqa: E402
from test_material_identification_ui import _ApplicationHarness  # noqa: E402

MODELS = ROOT / "docs" / "auto_id" / "forward_models"
SP02, SP13, SP02_LEGACY = (MODELS / name for name in ("SP02.physical.forward.json", "SP13.physical.forward.json",
                                                      "SP02.forward.json"))
DATA_STATES = {"READY", "WARNING", "BLOCKED"}


def _rows(application) -> dict:
    rows = {}
    for item, value in application.material_observation_readiness_table.items.values():
        rows.setdefault(item, []).append(value)
    return rows


def _status(application) -> str:
    return application.material_observation_readiness_status_label.kwargs["text"]


def _summary(application) -> str:
    return application.material_observation_readiness_summary_label.kwargs["text"]


class _Harness(_ApplicationHarness):
    def setUp(self):
        env = {key: value for key, value in os.environ.items() if not key.startswith("AUTO_ID_FIXTURE_ROOT_")}
        refuse = mock.Mock(side_effect=AssertionError("no calibration, FE or process may run"))
        patches = [mock.patch.dict(os.environ, env, clear=True),
                   mock.patch.object(subprocess, "Popen", refuse), mock.patch.object(subprocess, "run", refuse),
                   mock.patch("services.specimen_calibration_gate.evaluate_calibration_gate", refuse),
                   mock.patch("services.specimen_calibration_output.build_calibration_output", refuse),
                   mock.patch("services.campaign_scientific_backend.judge_campaign_run", refuse),
                   mock.patch("services.forward_builder.read_reference_input", refuse),
                   mock.patch("services.forward_builder.prepare_forward_jobs", refuse)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.refuse = refuse
        self.application = self._application()


class GovernedSpecimenTests(_Harness, unittest.TestCase):
    def test_sp02_shows_two_fit_one_holdout_and_a_met_count_without_readiness(self):
        ui.select_observation_readiness_model(self.application, SP02)
        rows = _rows(self.application)
        self.assertEqual(_status(self.application), "§8 COUNT MET (k = 1)")
        self.assertEqual(rows["Selected model"], ["docs/auto_id/forward_models/SP02.physical.forward.json"])
        self.assertEqual(rows["Strict rows FIT / HOLDOUT"], ["2 / 1"])
        self.assertEqual(rows["Terms FIT / HOLDOUT"], ["2 / 1"])
        self.assertTrue(rows["Unique families FIT / HOLDOUT"][0].startswith("2 / 1"))
        self.assertTrue(rows["SPEC v1.2 §8 count (k = 1)"][0].startswith("MET: 2 unique FIT families (≥ 2 required)"))
        self.assertEqual(rows["Insufficiency reasons"], ["none recorded"])
        self.assertEqual(rows["Scientific readiness"], ["NOT_DECLARED"])
        for part in ("rank", "precision", "leave one fit family out", "sensitivity"):
            self.assertIn(f"{part} NOT_ASSESSED", rows["Numerical identifiability"][0])
            self.assertIn(f"{part} NOT_ASSESSED", _summary(self.application))
        self.assertIn("Scientific readiness: NOT_DECLARED", _summary(self.application))
        self.assertTrue(rows["Data: strict_freeze"][0].startswith("GOVERNED"))
        self.assertTrue(rows["Data: suspension_threshold"][0].startswith("NOT_AVAILABLE"))
        nine = rows["Diagnostic k = 9"][0]
        self.assertTrue(nine.startswith("NOT MET: 2 unique FIT families (≥ 10 required)"))
        self.assertIn("not permitted by SPEC v1.2", nine)
        self.assertEqual(len(rows["Record hash (k = 1)"][0]), 64)
        self.refuse.assert_not_called()

    def test_sp13_shows_one_fit_one_holdout_and_an_unmet_count(self):
        ui.select_observation_readiness_model(self.application, SP13)
        rows = _rows(self.application)
        self.assertEqual(_status(self.application), "§8 COUNT NOT MET (k = 1)")
        self.assertEqual(rows["Strict rows FIT / HOLDOUT"], ["1 / 1"])
        self.assertTrue(rows["Unique families FIT / HOLDOUT"][0].startswith("1 / 1"))
        self.assertTrue(rows["SPEC v1.2 §8 count (k = 1)"][0].startswith("NOT MET"))
        self.assertTrue(rows["Insufficiency reason"][0].startswith("INSUFFICIENT_FIT_FAMILIES"))
        self.refuse.assert_not_called()

    def test_the_record_hash_is_stable_across_selections(self):
        ui.select_observation_readiness_model(self.application, SP02)
        first = _rows(self.application)["Record hash (k = 1)"]
        ui.select_observation_readiness_model(self.application, SP13)
        ui.select_observation_readiness_model(self.application, SP02)
        self.assertEqual(_rows(self.application)["Record hash (k = 1)"], first)


class SelectionAndFailureTests(_Harness, unittest.TestCase):
    def test_nothing_is_selected_until_the_user_chooses_a_model(self):
        self.assertEqual(_status(self.application), "NO MODEL SELECTED")
        self.assertEqual(self.application.material_observation_readiness_table.items, {})
        self.assertEqual(ui.observation_readiness_view(self.application)["summary"], ui.OBSERVATION_NOTHING_SELECTED)
        self.application._refresh_material_identification_pages()
        self.assertEqual(_status(self.application), "NO MODEL SELECTED")

    def test_cancel_keeps_and_clear_removes_the_selection(self):
        with mock.patch.object(ui, "_ask_governed_forward_model", return_value=str(SP02)):
            ui._choose_observation_readiness_model(self.application)
        self.assertEqual(_status(self.application), "§8 COUNT MET (k = 1)")
        with mock.patch.object(ui, "_ask_governed_forward_model", return_value=""):
            ui._choose_observation_readiness_model(self.application)
        self.assertEqual(_status(self.application), "§8 COUNT MET (k = 1)")
        ui.select_observation_readiness_model(self.application, None)
        self.assertEqual(_status(self.application), "NO MODEL SELECTED")
        self.assertEqual(self.application.material_observation_readiness_table.items, {})

    def test_historical_model_shows_diagnostic_data_and_no_governed_observation(self):
        ui.select_observation_readiness_model(self.application, SP02_LEGACY)
        rows = _rows(self.application)
        self.assertEqual(_status(self.application), "DIAGNOSTIC DATA ONLY: NO GOVERNED OBSERVATIONS")
        self.assertEqual(rows["Strict rows FIT / HOLDOUT"], ["0 / 0"])
        self.assertTrue(rows["Data: physical_registration"][0].startswith("DIAGNOSTIC_ONLY"))
        self.assertIn("PREREQUISITE_NOT_GOVERNED", " ".join(rows["Insufficiency reason"]))
        self.assertNotIn("COUNT MET", _status(self.application))

    def test_peak_derived_data_never_look_counted(self):
        items = {name: GovernanceItem(DataStatus.GOVERNED, "synthetic") for name in PREREQUISITES}
        items["modal_input_source"] = modal_input_item(ModalInputSource.PEAK_DERIVED, False, "dataset 58")
        items["experimental_modal_set"] = GovernanceItem(DataStatus.DIAGNOSTIC_ONLY, "19 FRF peaks")
        rows = (StrictRow("P1", "FIT", 1, 1, "A", 0.9, 0.0), StrictRow("P2", "FIT", 2, 2, "B", 0.9, 0.0),
                StrictRow("P3", "HOLDOUT", 3, 3, "C", 0.9, 0.0))
        evidence = ReadinessEvidence({"label": "SP04-like"}, {}, items, False, rows)
        fake = lambda _path, k, **_kwargs: build_observation_readiness(evidence, k)  # noqa: E731
        with mock.patch("services.observation_readiness.specimen_observation_readiness", fake):
            ui.select_observation_readiness_model(self.application, SP02)
        self.assertEqual(_status(self.application), "DIAGNOSTIC DATA ONLY: NO GOVERNED OBSERVATIONS")
        self.assertEqual(_rows(self.application)["Strict rows FIT / HOLDOUT"], ["0 / 0"])

    def test_a_model_outside_the_repository_is_not_available(self):
        ui.select_observation_readiness_model(self.application, Path(os.sep) / "elsewhere" / "x.forward.json")
        self.assertEqual(_status(self.application), "RECORD NOT AVAILABLE")
        self.assertIn("Nothing is counted", _summary(self.application))
        self.assertNotIn("Strict rows FIT / HOLDOUT", _rows(self.application))

    def test_a_refused_or_failing_record_is_not_available(self):
        ui.select_observation_readiness_model(self.application, ROOT / "docs" / "auto_id" / "STATUS.json")
        self.assertEqual(_status(self.application), "RECORD NOT AVAILABLE")  # not a forward-model manifest
        with mock.patch("services.observation_readiness.specimen_observation_readiness",
                        side_effect=RuntimeError("source unavailable")):
            ui.select_observation_readiness_model(self.application, SP02)
        self.assertEqual(_status(self.application), "RECORD NOT AVAILABLE")
        self.assertIn("source unavailable", _summary(self.application))

    def test_a_record_failing_its_hash_check_is_not_verified(self):
        ui.select_observation_readiness_model(self.application, SP02)
        record = self.application.observation_readiness_state["records"][ui.OBSERVATION_READINESS_K]
        record["observation_count"]["section_8_count"]["met"] = True
        record["observation_count"]["families"]["FIT"] = 10
        ui._refresh_data_readiness_page(self.application)
        self.assertEqual(_status(self.application), "RECORD NOT VERIFIED")
        self.assertNotIn("Unique families FIT / HOLDOUT", _rows(self.application))


class SeparationTests(_Harness, unittest.TestCase):
    def test_data_readiness_gate_is_unchanged_by_observation_readiness(self):
        before = ui.data_readiness_view(self.application)
        gate = self.application.material_readiness_status_label.kwargs["text"]
        for model in (SP02, SP13, SP02_LEGACY):
            ui.select_observation_readiness_model(self.application, model)
            self.assertEqual(ui.data_readiness_view(self.application), before)
            self.assertEqual(self.application.material_readiness_status_label.kwargs["text"], gate)
            view = ui.observation_readiness_view(self.application)
            self.assertNotIn(view["status"], DATA_STATES)
            for word in DATA_STATES:
                self.assertNotIn(word, view["status"].split())

    def test_the_section_is_part_of_the_data_readiness_page(self):
        text = self._page_text(self.application, "2. Data Readiness Check")
        for expected in ("Observation Readiness (governed records; SPEC v1.2 §8 count only)",
                         ui.OBSERVATION_SELECT_LABEL, ui.OBSERVATION_CLEAR_LABEL, "Data readiness gate",
                         "Scientific readiness (SPEC v1.2, read-only)"):
            self.assertIn(expected, text)

    def test_the_data_readiness_page_scrolls_in_a_real_window(self):
        import tkinter as tk
        from tkinter import ttk

        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"no display: {error}")
        self.addCleanup(root.destroy)
        root.withdraw()
        page = ttk.Frame(root)
        content = ui._scrollable_page(page)
        self.assertIsNot(content, page)
        self.assertEqual(content.master.winfo_class(), "Canvas")
        self.assertEqual({child.winfo_class() for child in page.winfo_children()}, {"Canvas", "TScrollbar"})
        stand_in = object()
        self.assertIs(ui._scrollable_page(stand_in), stand_in)  # presentation harness: no container

    def test_the_campaign_draft_still_uses_the_shared_forward_model_dialog(self):
        with mock.patch.object(ui, "_ask_governed_forward_model", return_value=str(SP02)), \
                mock.patch.object(ui, "add_draft_specimen") as add:
            ui._choose_draft_specimen(self.application)
        add.assert_called_once_with(self.application, str(SP02))


if __name__ == "__main__":
    unittest.main()
