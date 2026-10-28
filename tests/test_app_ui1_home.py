"""APP-UI.1: the Home screen of the real main window (synthetic data, no process, no Abaqus).

The window opens on Home with four areas:

- source data;
- analysis readiness;
- results;
- material properties.

The Home / Expert mode switch shows the unchanged notebook: 11 tabs, same order, same widgets. Switching keeps every
input, result and the project state. Home uses the window's own handlers and state:

- a file chosen on Home is the file of 1. Files;
- Run on Home is the existing Run;
- a stale or discarded result disappears from Home exactly as from the expert tabs;
- no material property value is ever shown.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import synthetic_plate_support as S  # noqa: E402
import home_dashboard as H  # noqa: E402
from services import modal_data_viewer as viewer  # noqa: E402
from ui_policy import AnalysisState  # noqa: E402
from test_app_p1_stale_results import STALE, _App  # noqa: E402

TAB_ATTRIBUTES = ("input_tab", "table_tab", "shape_tab", "plot_tab", "frf_tab", "cmif_tab", "advanced_tab",
                  "manual_review_tab", "material_identification_tab", "details_tab", "scaling_tab")


class _Home(_App):
    def home(self):
        application = self.application()
        self.root.update()
        return application, application.home

    def texts(self, rows):
        return [(str(mark.cget("text")), str(caption.cget("text")), str(text.cget("text")))
                for mark, caption, text in rows]

    def refreshed(self, application):
        application.home.refresh()
        self.root.update()
        return application.home

    def result_values(self, home):
        labels = home.result_values.winfo_children()
        return [str(label.cget("text")) for label in labels]


class SwitchTests(_Home):
    def test_the_window_opens_on_home_and_expert_mode_is_the_unchanged_notebook(self):
        application, home = self.home()
        self.assertEqual(application.home_view_mode.get(), H.HOME)
        self.assertEqual(home.frame.winfo_manager(), "grid")
        self.assertEqual(application.tabs.winfo_manager(), "")  # hidden, not destroyed
        self.assertEqual(int(home.frame.grid_info()["row"]), 1)
        expected = [str(getattr(application, name)) for name in TAB_ATTRIBUTES]
        self.assertEqual(list(application.tabs.tabs()), expected)  # 11 tabs, same order, no tab added
        application._show_view(H.EXPERT)
        self.assertEqual(application.tabs.winfo_manager(), "grid")
        self.assertEqual(int(application.tabs.grid_info()["row"]), 1)
        self.assertEqual(home.frame.winfo_manager(), "")
        for name in TAB_ATTRIBUTES:  # every tab stays reachable in expert mode
            application.tabs.select(getattr(application, name))
            self.root.update()
            self.assertEqual(application.tabs.select(), str(getattr(application, name)))

    def test_switching_keeps_inputs_result_selected_tab_and_project_state(self):
        application, home = self.home()
        self.established(application)
        application._show_expert(application.cmif_tab)
        before = (application.abaqus_path.get(), application.experimental_path.get(),
                  application.experimental_modal_set_key.get(), application.start_mode.get(), application.result,
                  application.dirty_tracker.dirty, str(application.excel_button.cget("state")))
        for view in (H.HOME, H.EXPERT, H.HOME, H.EXPERT):
            application._show_view(view)
            self.root.update()
        self.assertEqual(application.tabs.select(), str(application.cmif_tab))  # the expert tab shown before
        after = (application.abaqus_path.get(), application.experimental_path.get(),
                 application.experimental_modal_set_key.get(), application.start_mode.get(), application.result,
                 application.dirty_tracker.dirty, str(application.excel_button.cget("state")))
        self.assertEqual(after, before)
        self.assertIs(application.result, before[4])

    def test_the_header_switch_changes_the_view(self):
        application, _home = self.home()
        buttons = [child for child in application.home_view_switch.winfo_children()]
        self.assertEqual([str(button.cget("text")) for button in buttons], ["Home", "Expert mode (all 11 tabs)"])
        buttons[1].invoke()
        self.assertEqual((application.home_view_mode.get(), application.tabs.winfo_manager()), (H.EXPERT, "grid"))
        buttons[0].invoke()
        self.assertEqual((application.home_view_mode.get(), application.tabs.winfo_manager()), (H.HOME, ""))

    def test_no_new_install_layer(self):
        self.assertEqual([name for name in dir(H) if name.startswith("install_")], [])
        main_source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
        self.assertNotIn("home_dashboard", main_source)


class SourceAndReadinessTests(_Home):
    def test_files_chosen_on_home_are_the_files_of_1_files(self):
        application, home = self.home()
        subtitle = [str(w.cget("text")) for w in home.cards["sources"].grid_slaves(row=1, column=0)][0]
        self.assertIn("reads its list of fitted modal sets", subtitle)  # the modal-set discovery reads the file
        self.assertNotIn("Nothing is read", subtitle)
        odb = self.folder / "chosen.odb"
        odb.write_bytes(b"synthetic ODB stand-in; never opened")
        with mock.patch("tkinter.filedialog.askopenfilename", return_value=str(odb)):
            home.source_rows["fe"][2].invoke()
        self.assertEqual(application.abaqus_path.get(), str(odb))
        self.assertEqual(application.abaqus_path_entry.get(), str(odb))  # the same variable as on 1. Files
        unv = S.write_experiment(self.folder / "chosen.unv", S.E0, S.G0)
        with mock.patch("tkinter.filedialog.askopenfilename", return_value=str(unv)):
            home.source_rows["experimental"][2].invoke()
        self.assertEqual(application.experimental_path.get(), str(unv))
        self.settle(application)
        home = self.refreshed(application)
        self.assertIn("chosen.odb", str(home.source_rows["fe"][0].cget("text")))
        self.assertIn("chosen.unv", str(home.source_rows["experimental"][0].cget("text")))
        with mock.patch("tkinter.filedialog.askopenfilename", return_value=""):  # cancelled: nothing changes
            home.source_rows["fe"][2].invoke()
        self.assertEqual(application.abaqus_path.get(), str(odb))

    def test_missing_and_ready_states(self):
        application, home = self.home()
        rows = self.texts(home.check_rows)
        self.assertEqual([row[1] for row in rows],
                         ["Abaqus results", "Experiment", "Modal set", "Abaqus", "Units", "FE modes"])
        self.assertEqual(rows[0][0], H.MARKS[H.OK])
        self.assertTrue(str(home.verdict.cget("text")).startswith(H.MARKS[H.OK] + "  Ready"))
        self.assertEqual(str(home.run_button.cget("state")), "normal")
        application.experimental_path.set("")
        home = self.refreshed(application)
        self.assertEqual(str(home.run_button.cget("state")), "disabled")  # Run on Home only when Home says ready
        rows = self.texts(home.check_rows)
        self.assertEqual(rows[1][:1] + rows[1][2:], (H.MARKS[H.NEEDED], "Missing"))
        self.assertIn("Still needed: Experiment", str(home.verdict.cget("text")))
        application.experimental_path.set(str(self.folder / "absent.unv"))
        home = self.refreshed(application)
        self.assertEqual(self.texts(home.check_rows)[1][2], "Not found: absent.unv")

    def test_a_file_with_several_modal_sets_needs_a_choice_made_on_home(self):
        application, home = self.home()
        unv = S.write_experiment(self.folder / "two_sets.unv", S.E0, S.G0, sets=(("Best", 5), ("Processing", 6)))
        application.experimental_path.set(str(unv))
        self.settle(application)
        home = self.refreshed(application)
        modal_set = self.texts(home.check_rows)[2]
        self.assertEqual(modal_set[0], H.MARKS[H.NEEDED])
        self.assertIn("2 fitted modal sets", modal_set[2])
        self.assertEqual(str(home.run_button.cget("state")), "disabled")
        choices = [value for value in home.modal_set_combo.cget("values") if "Best" in str(value)]
        self.assertEqual(len(choices), 1)
        home.modal_set_combo.set(choices[0])
        home.modal_set_combo.event_generate("<<ComboboxSelected>>")
        self.root.update()
        self.assertTrue(application.experimental_modal_set_key.get())  # the existing handler chose the set
        home = self.refreshed(application)
        self.assertEqual(self.texts(home.check_rows)[2][0], H.MARKS[H.OK])

    def test_odb_without_abaqus_is_a_warning_and_manifest_needs_no_abaqus(self):
        application, home = self.home()
        self.assertEqual(self.texts(home.check_rows)[3][0], H.MARKS[H.WARN])  # synthetic .odb, no Abaqus found
        self.assertIn("see the warning above", str(home.verdict.cget("text")))
        manifest = self.folder / "package" / "manifest.json"
        manifest.parent.mkdir()
        manifest.write_text("{}", encoding="utf-8")
        application.abaqus_path.set(str(manifest))
        home = self.refreshed(application)
        self.assertEqual(self.texts(home.check_rows)[3][0], H.MARKS[H.INFO])
        self.assertIn("no Abaqus run is needed", str(home.source_rows["fe"][1].cget("text")))

    def test_run_on_home_is_the_existing_run_and_locks_the_inputs(self):
        application, home = self.home()
        values = (Path(application.abaqus_path.get()), Path(application.experimental_path.get()),
                  self.folder / "workspace", 1, 9, "abaqus", 1.0, None)
        with mock.patch.object(application, "_validate", return_value=values) as validate, \
                mock.patch.object(application, "_worker", side_effect=lambda *_: None):
            home.run_button.invoke()
        validate.assert_called_once_with()
        self.assertTrue(application.running)
        home = self.refreshed(application)
        self.assertEqual(str(home.run_button.cget("state")), "disabled")
        self.assertEqual(str(home.stop_button.cget("state")), "normal")
        for widget in (home.source_rows["fe"][2], home.source_rows["experimental"][2], home.modal_set_combo):
            self.assertEqual(str(widget.cget("state")), "disabled")
        self.assertTrue(str(home.verdict.cget("text")).startswith(H.MARKS[H.WAIT]))
        self.assertTrue(all(str(b.cget("state")) == "disabled" for b in home.result_buttons.values()))
        application.cache = self.folder / "cache"
        application._complete(self.comparison_result())
        home = self.refreshed(application)
        self.assertEqual(str(home.run_button.cget("state")), "normal")
        self.assertEqual(str(home.source_rows["fe"][2].cget("state")), "normal")
        self.assertEqual(str(home.modal_set_combo.cget("state")), "readonly")


def write_manifest(folder: Path, modes, text=None) -> Path:
    """An extraction manifest.json with only its mode list (no geometry or mode file: Home never reads them)."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "manifest.json"
    if text is None:
        text = json.dumps({"format_version": 2, "geometry_file": "geometry.csv", "start_mode": 6, "end_mode": 15,
                           "modes": [{"mode": m, "file": f"mode_{m:04d}.csv", "frequency_hz": 10.0 * m}
                                     for m in modes]})
    path.write_text(text, encoding="utf-8")
    return path


class FeModeRowTests(_Home):
    """APP-UI.1-F1: an extracted manifest.json is compared with every mode it lists; the mode-range field of 1. Files
    applies to an .odb extraction only, so Home never shows that field as the compared FE modes of a manifest."""

    def row(self, application):
        home = self.refreshed(application)
        return self.texts(home.check_rows)[5]

    def application_6_15(self):
        application, _home = self.home()
        application.start_mode.set(6)
        application.end_mode.set(15)
        return application

    def test_a_manifest_7_30_with_the_fields_at_6_15_shows_7_30(self):
        application = self.application_6_15()
        manifest = write_manifest(self.folder / "sp13", range(7, 31))
        with mock.patch("abaqus_bridge.load_extracted_odb", side_effect=AssertionError("no FE data is loaded")):
            application.abaqus_path.set(str(manifest))
            mark, caption, text = self.row(application)
        self.assertEqual((mark, caption), (H.MARKS[H.INFO], "FE modes"))
        self.assertIn("Extracted modes listed in manifest.json: 7–30 (24 modes)", text)
        self.assertIn("The mode range of 1. Files (6 to 15) applies to an .odb extraction only", text)
        self.assertNotIn("6 to 15:", text)  # never presented as the compared modes
        self.assertEqual((application.start_mode.get(), application.end_mode.get()), (6, 15))  # Expert mode unchanged

    def test_an_odb_shows_the_extraction_range(self):
        application = self.application_6_15()
        self.assertTrue(application.abaqus_path.get().endswith(".odb"))
        self.assertEqual(self.row(application)[2], "6 to 15: the modes to extract from the .odb when the analysis runs.")

    def test_a_manifest_6_15(self):
        application = self.application_6_15()
        application.abaqus_path.set(str(write_manifest(self.folder / "sp02", range(6, 16))))
        self.assertIn("listed in manifest.json: 6–15 (10 modes)", self.row(application)[2])

    def test_non_consecutive_mode_numbers_are_not_shown_as_one_range(self):
        application = self.application_6_15()
        application.abaqus_path.set(str(write_manifest(self.folder / "gaps", (13, 6, 7, 8, 10, 12, 7))))
        text = self.row(application)[2]
        self.assertIn("listed in manifest.json: 6–8, 10, 12–13 (6 modes)", text)
        self.assertNotIn("6–13", text)
        self.assertEqual(H.mode_number_text([5]), "5")
        self.assertEqual(H.mode_number_text([7, 9]), "7, 9")

    def test_a_damaged_or_incomplete_manifest_gets_no_invented_range(self):
        application = self.application_6_15()
        cases = (("not json", "{ broken", "the file is not a readable JSON extraction manifest"),
                 ("no mode list", json.dumps({"format_version": 2}), "the file has no valid list of extracted modes"),
                 ("bad entry", json.dumps({"modes": [{"mode": "x"}]}), "the file is not a readable JSON extraction manifest"),
                 ("entry without number", json.dumps({"modes": [{"file": "m.csv"}]}), "the file has no valid list of extracted modes"),
                 ("empty list", json.dumps({"modes": []}), "the file lists no extracted mode"))
        for index, (name, content, reason) in enumerate(cases):
            with self.subTest(name):
                application.abaqus_path.set(str(write_manifest(self.folder / f"bad{index}", (), text=content)))
                mark, _caption, text = self.row(application)
                self.assertEqual(mark, H.MARKS[H.WARN])
                self.assertIn(f"could not be read from manifest.json: {reason}", text)
                self.assertNotRegex(text, r"\d+–\d+")  # no range
                self.assertNotIn("6 to 15", text)
        too_large = write_manifest(self.folder / "large", range(6, 16))
        with mock.patch.object(H, "MANIFEST_READ_LIMIT", 10):
            application.abaqus_path.set(str(too_large))
            self.assertIn("too large to be read here", self.row(application)[2])
        application.abaqus_path.set(str(self.folder / "missing" / "manifest.json"))
        self.assertEqual(self.row(application)[2], "Shown once the extraction manifest.json is found.")

    def test_the_row_follows_a_change_of_the_fe_source(self):
        application = self.application_6_15()
        sp13 = write_manifest(self.folder / "a", range(7, 31))
        sp02 = write_manifest(self.folder / "b", range(6, 16))
        application.abaqus_path.set(str(sp13))
        self.assertIn("7–30", self.row(application)[2])
        application.abaqus_path.set(str(sp02))
        self.assertIn("6–15 (10 modes)", self.row(application)[2])
        write_manifest(self.folder / "b", (6, 7, 9))  # the same file rewritten: read again, not a stale cache
        self.assertIn("6–7, 9 (3 modes)", self.row(application)[2])
        application.abaqus_path.set(str(self.folder / "plate.odb"))
        self.assertIn("6 to 15: the modes to extract from the .odb", self.row(application)[2])
        application.end_mode.set(20)  # the field itself still drives an .odb extraction
        self.assertIn("6 to 20: the modes to extract from the .odb", self.row(application)[2])
        application.abaqus_path.set("")
        self.assertEqual(self.row(application)[2], "Mode range 6 to 20: used when an .odb is extracted.")


class ResultTests(_Home):
    def test_an_established_comparison_is_summarised_from_the_metric_cards(self):
        application, home = self.home()
        self.assertIn(H.NO_RESULT_TEXT, str(home.result_text.cget("text")))
        self.assertTrue(all(str(b.cget("state")) == "disabled" for b in home.result_buttons.values()))
        self.established(application)
        home = self.refreshed(application)
        self.assertIn("Comparison complete", str(home.result_text.cget("text")))
        values = self.result_values(home)
        self.assertEqual(values[0:2], ["Matched mode pairs", str(application.metric_pairs.cget("text"))])
        self.assertIn(str(application.metric_error.cget("text")), values)
        self.assertTrue(all(str(b.cget("state")) == "normal" for b in home.result_buttons.values()))
        for key, tab in (("frequencies", "table_tab"), ("shapes", "shape_tab"), ("mac", "plot_tab")):
            application._show_view(H.HOME)
            home.result_buttons[key].invoke()
            self.assertEqual(application.home_view_mode.get(), H.EXPERT)
            self.assertEqual(application.tabs.select(), str(getattr(application, tab)))

    def test_a_changed_input_removes_the_result_from_home(self):
        application, home = self.home()
        self.established(application)
        application.start_mode.set(2)  # an input of the result
        home = self.refreshed(application)
        self.assertIn(STALE, str(home.result_text.cget("text")))
        self.assertEqual(self.result_values(home), [])
        self.assertEqual(home.result_values.winfo_manager(), "")
        self.assertTrue(all(str(b.cget("state")) == "disabled" for b in home.result_buttons.values()))
        self.assertNotIn(str(application.metric_pairs.cget("text")) + " ", " ".join(self.result_values(home)))

    def test_a_frequency_only_diagnostic_shows_no_pairs_and_no_mac(self):
        application, home = self.home()
        self.diagnostic(application)
        home = self.refreshed(application)
        self.assertIn(H.DIAGNOSTIC_TEXT, str(home.result_text.cget("text")))
        self.assertNotIn("experimental file gave no usable", str(home.result_text.cget("text")))
        self.assertEqual(H.diagnostic_kind(application), H.FREQUENCY_ONLY)
        self.assertEqual(self.result_values(home), ["Mode pairs", "none", "MAC", "not computed"])
        self.assertEqual(str(home.result_buttons["mac"].cget("state")), "disabled")
        self.assertEqual(str(home.result_buttons["frequencies"].cget("state")), "normal")
        self.assertEqual(str(home.result_buttons["shapes"].cget("state")), "normal")

    def test_an_unusable_experimental_file_is_explained_as_such(self):
        """ExperimentalDataUnavailable: no orientation question arises; only the FE data are available."""
        application, home = self.home()
        self.start(application)
        error = viewer.ExperimentalDataUnavailable("The experimental file could not be used")
        error.loaded_modal_data = viewer.LoadedModalData(self.fe, None, experimental_error="no modal vectors or FRFs",
                                                         directory=self.folder / "views")
        application._failed(error)
        self.assertEqual(application.analysis_state, AnalysisState.DIAGNOSTIC)
        home = self.refreshed(application)
        text = str(home.result_text.cget("text"))
        self.assertNotIn("orientation", text)  # not the frequency-only explanation
        self.assertNotIn(H.DIAGNOSTIC_TEXT, text)
        self.assertIn("no modal vectors or FRFs", text)  # the reason the window has for this file
        self.assertIn(H.EXPERIMENT_UNUSABLE_TEXT.format(reason="no modal vectors or FRFs"), text)
        self.assertEqual(H.diagnostic_kind(application), H.EXPERIMENT_UNUSABLE)
        self.assertEqual(self.result_values(home),
                         ["Experimental data", "not usable", "Mode pairs", "none", "MAC", "not computed"])
        states = {key: str(button.cget("state")) for key, button in home.result_buttons.items()}
        self.assertEqual(states, {"frequencies": "disabled", "shapes": "normal", "mac": "disabled"})
        home.result_buttons["shapes"].invoke()  # the FE modes, in 3. Mode shapes
        self.assertEqual(application.tabs.select(), str(application.shape_tab))
        application.experimental_path.set(str(self.other_unv))  # an input changes: the diagnostic leaves Home
        home = self.refreshed(application)
        self.assertIn(STALE, str(home.result_text.cget("text")))
        self.assertEqual(self.result_values(home), [])

    def test_a_new_project_clears_the_result_on_home(self):
        application, home = self.home()
        self.established(application)
        with mock.patch("tkinter.messagebox.askyesnocancel", return_value=False), \
                mock.patch("tkinter.messagebox.askyesno", return_value=True):
            application._new_project()
        home = self.refreshed(application)
        self.assertIsNone(application.result)
        self.assertNotIn("Comparison complete", str(home.result_text.cget("text")))
        self.assertEqual(self.result_values(home), [])


class MaterialTests(_Home):
    def test_no_material_value_is_shown_and_the_status_is_stated(self):
        application, home = self.home()
        rows = self.texts(home.material_rows)
        self.assertEqual([row[1] for row in rows], ["Material constants", "Existing evidence", "Auto-ID selection"])
        self.assertTrue(rows[0][2].startswith("Not determined."))
        self.assertIn("NOT_AUTHORISED", rows[0][2])
        self.assertEqual(rows[1][2], "No identification evidence is loaded in this session.")
        for _mark, _caption, text in rows:  # no number is presented as a property value
            self.assertNotRegex(text, r"\d+(\.\d+)?\s*(GPa|MPa|Pa)\b")

    def test_loaded_historical_evidence_is_named_as_evidence_only(self):
        application, home = self.home()
        application.material_identification_evidence_view_model = SimpleNamespace(
            sensitivity=object(), identifiability=None, identification=object(), validation=None, model=None)
        home = self.refreshed(application)
        rows = self.texts(home.material_rows)
        self.assertEqual(rows[1][2], "2 of 4 evidence records loaded (sensitivity, identification; historical, not "
                                     "bound to a model).")
        self.assertTrue(rows[0][2].startswith("Not determined."))  # evidence never makes a constant determined

    def test_open_auto_id_goes_to_the_expert_section(self):
        application, home = self.home()
        home.open_auto_id()
        self.assertEqual(application.home_view_mode.get(), H.EXPERT)
        self.assertEqual(application.tabs.select(), str(application.material_identification_tab))
        notebook = application.material_identification_notebook
        self.assertEqual(notebook.select(), notebook.tabs()[0])


class LayoutTests(_Home):
    def test_two_columns_when_wide_one_column_when_narrow(self):
        application, home = self.home()
        scaling = float(self.root.tk.call("tk", "scaling"))
        for width, columns in ((int(2000 * scaling / (96 / 72)), 2), (int(600 * scaling / (96 / 72)), 1),
                               (int(2000 * scaling / (96 / 72)), 2)):
            for archive_open in (False, True, False):  # APP-WORKSPACE.2-F1: the archive only when opened
                home.toggle_research_archive(archive_open)
                home._canvas_resized(SimpleNamespace(width=width))
                placed = {key: (int(card.grid_info()["row"]), int(card.grid_info()["column"]))
                          for key, card in home.cards.items() if card.winfo_manager()}
                if columns == 2:  # APP-WORKSPACE.2 / APP-CATALOG.1: the workspace, then the passport, full width
                    expected = {"sources": (0, 0), "readiness": (0, 1), "results": (1, 0), "material": (1, 1),
                                "workspace": (2, 0), "catalogue": (3, 0)}
                else:
                    expected = {"sources": (0, 0), "readiness": (1, 0), "results": (2, 0), "material": (3, 0),
                                "workspace": (4, 0), "catalogue": (5, 0)}
                if not archive_open:
                    del expected["catalogue"]
                self.assertEqual(placed, expected)
                self.assertEqual(int(home.cards["workspace"].grid_info()["columnspan"]), columns)
                if archive_open:
                    self.assertEqual(int(home.cards["catalogue"].grid_info()["columnspan"]), columns)

    def test_interface_scale_and_window_sizes_keep_home_usable(self):
        application, home = self.home()
        self.root.deiconify()
        try:
            for size, scale in (("1920x1080", 100), ("1120x700", 125), ("1366x768", 110), ("1120x700", 100)):
                application._apply_ui_scale(scale, persist=False)
                self.root.geometry(size)
                deadline = time.monotonic() + 2.0  # the wrap follows once the layout has settled
                while time.monotonic() < deadline:
                    self.root.update()
                    time.sleep(0.02)
                for label, card in home._wrapped:
                    if label.winfo_ismapped():
                        right = label.winfo_rootx() + label.winfo_reqwidth()
                        self.assertLessEqual(right, card.winfo_rootx() + card.winfo_width() + 2,
                                             (size, scale, str(label.cget("text"))[:40]))
        finally:
            application._apply_ui_scale(100, persist=False)
            self.root.withdraw()

    def test_long_folders_are_shortened(self):
        long = Path("C:/Users/someone/AppData/Local/Temp/a/very/deep/folder/structure/with/data/run_20261016")
        text = H.short_path(long)
        self.assertLessEqual(len(text), len(str(long)))
        self.assertTrue(text.endswith(str(Path("data", "run_20261016"))))
        self.assertIn("\u2026", text)
        self.assertEqual(H.short_path(Path("C:/data")), str(Path("C:/data")))


if __name__ == "__main__":
    unittest.main()
