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
                         ["Abaqus results", "Experiment", "Modal set", "Abaqus", "Units", "Abaqus modes"])
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
        self.assertEqual(self.result_values(home), ["Mode pairs", "none", "MAC", "not computed"])
        self.assertEqual(str(home.result_buttons["mac"].cget("state")), "disabled")
        self.assertEqual(str(home.result_buttons["frequencies"].cget("state")), "normal")

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
            home._canvas_resized(SimpleNamespace(width=width))
            placed = {key: (int(card.grid_info()["row"]), int(card.grid_info()["column"]))
                      for key, card in home.cards.items()}
            if columns == 2:
                self.assertEqual(placed, {"sources": (0, 0), "readiness": (0, 1), "results": (1, 0),
                                          "material": (1, 1)})
            else:
                self.assertEqual(placed, {"sources": (0, 0), "readiness": (1, 0), "results": (2, 0),
                                          "material": (3, 0)})

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
