"""MAT-4.UX1: the five tabs of the Materials page, on the same SYNTHETIC cases as MAT-3. Qt ``offscreen``, bounded waits.

The numbers themselves are tested in test_mat3_materials_study; here they must reach the new places unchanged.
"""

from __future__ import annotations

import ast
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import unittest
from unittest import mock

import test_mat3_materials_study as mat3

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractButton, QComboBox, QLabel, QLineEdit, QPushButton, QScrollArea, QStyle,
                               QStyleOptionComboBox, QTabBar, QTableWidget, QWidget)

from new_gui import materials_study_model as sm
from new_gui import materials_study_panel as sp
from new_gui import materials_workspace as mws
from new_gui import production_window as pw
from new_gui.workspace_state import EXPERIMENTAL, FE
from services import analysis_project as ap
from services import materials_project as mp
from services import plate_material_workflow as workflow

CODES = ("KIRCHHOFF_RITZ_4D", "STAGE_A_MATRIX_3D", "SYNTHETIC_SOFTWARE_TEST", "DIAGNOSTIC_OPTIMIZER_CANDIDATE", "NOT_A_RELEASE_VALUE",
         "CONVERGED", "M8 GATE NOT_MET", "D-077 NO_GLOBAL_PARAMETER_VALUE")


def png_size(data: bytes) -> tuple:
    return Image.open(io.BytesIO(data)).size


class _Tabs(mat3._Page):
    def tabs(self, size=(1366, 768)):
        window, panel = self.page()
        window.resize(*size)
        self.app.processEvents()
        return window, window.materials_workspace, panel

    def visible_area(self, workspace) -> QScrollArea:
        page = workspace.pages.currentWidget()
        page = page.currentWidget() if page is workspace.study else page
        self.assertIsInstance(page, QScrollArea)
        return page

    def choose_stage_a(self, panel) -> None:
        panel.method_combo.setCurrentIndex(panel.method_combo.findData(sm.STAGE_A))

    def run_to_end(self, panel) -> dict:
        self.run_it(panel)
        self.app.processEvents()
        return panel.record["materials"]


class Structure(_Tabs):
    def test_five_tabs_and_each_shows_its_own_page(self):
        window, workspace, panel = self.tabs()
        self.assertEqual([workspace.tabs.tabText(i) for i in range(workspace.tabs.count())],
                         ["Calculation", "Results", "Plots", "Diagnostics", "FE / Experiment"])
        self.assertEqual(workspace.tabs.currentIndex(), 0)
        marks = {0: panel.run_button, 1: panel.save_button, 2: panel.plots_empty, 3: panel.diagnostics_empty, 4: workspace.reuse_button}
        for index, mark in marks.items():
            workspace.tabs.setCurrentIndex(index)  # as a click or an arrow key does
            self.app.processEvents()
            self.assertTrue(mark.isVisible(), index)
            for other, widget in marks.items():
                if other != index:
                    self.assertFalse(widget.isVisible(), (index, other))
        self.assertEqual(window.stack.currentIndex(), pw.MATERIALS_PAGE)

    def test_changing_tabs_computes_and_opens_nothing(self):
        window, workspace, panel = self.tabs()
        refuse = AssertionError("nothing starts when a tab is shown")
        with mock.patch.object(sm, "execute_study", side_effect=refuse), mock.patch.object(sm, "run_plate_inverse_study", side_effect=refuse), \
                mock.patch.object(sm, "build_request", side_effect=refuse), mock.patch.object(mws.mw, "read_fe_facts", side_effect=refuse), \
                mock.patch.object(mws.mw, "read_experimental_facts", side_effect=refuse), mock.patch("subprocess.run", side_effect=refuse):
            for _round in range(2):
                for index in range(5):
                    workspace.select_tab(index)
                    self.app.processEvents()
        self.assertFalse(workspace.busy())
        self.assertIsNone(panel.record)
        self.assertEqual(workspace.paths, {FE: None, EXPERIMENTAL: None})
        self.assertEqual(window.analyze.paths, {FE: None, EXPERIMENTAL: None})

    def test_the_fifth_tab_holds_the_real_file_inspection_and_the_status_apart(self):
        window, workspace, panel = self.tabs()
        workspace.select_tab(mws.TAB_FILES)
        self.app.processEvents()
        for widget in (workspace.choose_buttons[FE], workspace.choose_buttons[EXPERIMENTAL], workspace.reuse_button, workspace.property_table,
                       window.materials.table, workspace.status_text, panel.real_state):
            self.assertTrue(widget.isVisible())
        self.assertIn("BLOCKED", panel.real_state.text())
        self.assertEqual(workspace.property_table.horizontalHeaderItem(1).text(), "FE input")
        self.assertEqual(workspace.property_table.horizontalHeaderItem(2).text(), "Independent measurement")
        self.assertEqual(workspace.property_table.horizontalHeaderItem(3).text(), "Identified / calibrated")
        self.assertTrue(workspace.workflow.toggle.isEnabled())

    def test_a_chosen_real_file_stays_on_the_fifth_tab_and_enables_no_fit(self):
        window, workspace, panel = self.tabs()
        self.assertTrue(workspace.choose_file(EXPERIMENTAL, str(self.unv(mat3.base.plate_nodes()))))
        self.assertTrue(window.wait_for_reads())
        self.assertEqual(workspace.tabs.currentIndex(), 0)  # reading a file moves nothing
        self.assertIsNone(panel.record)
        panel.source_combo.setCurrentIndex(panel.source_combo.findData(sm.REAL_SOURCE))
        self.assertFalse(panel.run_button.isEnabled())
        self.assertFalse(panel.prepare_button.isEnabled())
        self.assertFalse(panel.run())
        self.assertIn("NOT_AUTHORIZED", panel.message.text())
        self.assertEqual(dict(panel.table_cells("real"))["Real-data inverse execution"], "BLOCKED")


class RunTab(_Tabs):
    def test_the_default_screen_is_short_and_run_is_in_view(self):
        for size in ((1366, 768), (900, 700)):
            for backend in (sm.RITZ, sm.STAGE_A):
                with self.subTest(size=size, backend=backend):
                    window, workspace, panel = self.tabs(size)
                    if backend == sm.STAGE_A:
                        self.choose_stage_a(panel)
                    self.app.processEvents()
                    self.assertEqual(panel.backend, backend)
                    self.assertFalse(panel.advanced.body.isVisible())
                    area = self.visible_area(workspace)
                    self.assertEqual(area.verticalScrollBar().value(), 0)
                    bottom = panel.run_button.mapTo(area.viewport(), panel.run_button.rect().bottomLeft()).y()
                    self.assertLessEqual(bottom, area.viewport().height())
                    for hidden in (panel.parameter_fields[backend][next(iter(panel.parameter_fields[backend]))]["start"], panel.solves_field,
                                   panel.numeric_fields["sigma"], panel.note_field, panel.prepare_button):
                        self.assertFalse(hidden.isVisible())
                    window.close()

    def test_the_method_names_are_plain_and_the_codes_stay_the_data(self):
        _window, _workspace, panel = self.tabs()
        self.assertEqual([panel.method_combo.itemText(i) for i in range(2)], ["Ritz plate model", "Stage A matrix model"])
        self.assertEqual([panel.method_combo.itemData(i) for i in range(2)], ["KIRCHHOFF_RITZ_4D", "STAGE_A_MATRIX_3D"])
        self.assertEqual(panel.run_button.text(), "Run calculation")
        self.assertEqual(panel.cancel_button.text(), "Cancel")
        self.assertEqual(panel.source_combo.currentText(), "Built-in synthetic example")

    def test_each_method_shows_only_its_own_inputs(self):
        _window, _workspace, panel = self.tabs()
        self.assertTrue(panel.a_field.isVisible())
        self.assertTrue(panel.mass_field.isVisible())
        self.assertTrue(panel.geometry_note.isVisible())
        panel.advanced.toggle.setChecked(True)
        self.app.processEvents()
        self.assertFalse(panel.package_row.isVisible())
        self.assertTrue(panel.parameter_fields[sm.RITZ]["u"]["start"].isVisible())
        self.choose_stage_a(panel)
        self.app.processEvents()
        for widget in (panel.a_field, panel.b_field, panel.mass_field, panel.mass_unit, panel.length_unit, panel.geometry_note,
                       panel.mass_basis, panel.thickness_field):
            self.assertFalse(widget.isVisible())
        self.assertFalse(panel.a_field.isEnabled())
        self.assertFalse(panel.thickness_field.isEnabled())
        self.assertTrue(panel.package_row.isVisible())
        self.assertTrue(panel.parameter_fields[sm.STAGE_A]["r"]["start"].isVisible())
        self.assertFalse(panel.parameter_fields[sm.RITZ]["u"]["start"].isVisible())

    def test_the_form_is_the_same_as_the_shipped_defaults_for_both_methods(self):
        _window, _workspace, panel = self.tabs()
        self.assertEqual(panel.form(), sm.default_form(sm.RITZ))
        self.choose_stage_a(panel)
        self.assertEqual(panel.form(), sm.default_form(sm.STAGE_A))

    def test_advanced_values_survive_closing_and_tabs_and_reach_the_workflow(self):
        _window, workspace, panel = self.tabs()
        panel.advanced.toggle.setChecked(True)
        self.app.processEvents()
        self.assertTrue(panel.solves_field.isVisible())
        panel.solves_field.setText("12")
        panel.parameter_fields[sm.RITZ]["D11"]["start"].setText("12.5")
        panel.note_field.setText("a note")
        panel.advanced.toggle.setChecked(False)
        for index in (1, 2, 3, 4, 0):
            workspace.select_tab(index)
            self.app.processEvents()
        self.assertEqual(panel.solves_field.text(), "12")
        self.assertEqual(panel.parameter_fields[sm.RITZ]["D11"]["start"].text(), "12.5")
        panel.advanced.toggle.setChecked(True)
        self.app.processEvents()
        self.assertEqual(panel.note_field.text(), "a note")
        with mock.patch.object(sm, "run_plate_inverse_study", wraps=workflow.run_plate_inverse_study) as called:
            section = self.run_to_end(panel)
        called.assert_called_once()
        self.assertEqual(section["result"]["execution_status"], "BUDGET_EXHAUSTED")  # the limit from the hidden section really applied
        self.assertEqual(section["input"]["parameters"]["D11"]["start"], "12.5")
        self.assertEqual(section["input"]["authorization_note"], "a note")

    def test_a_mistake_in_a_hidden_field_is_said_on_the_run_screen(self):
        _window, _workspace, panel = self.tabs()
        panel.solves_field.setText("many")
        self.app.processEvents()
        self.assertFalse(panel.run_button.isEnabled())
        self.assertTrue(panel.message.isVisible())
        self.assertIn("Solve limit", panel.message.text())


class ResultsTab(_Tabs):
    def test_both_examples_go_to_results_and_show_the_real_numbers(self):
        for backend, expected in ((sm.RITZ, {"D11": "12.0001", "D22": "7.00009", "D66": "2.30006", "u": "0.149767"}),
                                  (sm.STAGE_A, {"D": "0.36", "D66": "0.05", "r": "0.09"})):
            with self.subTest(backend=backend):
                _window, workspace, panel = self.tabs()
                if backend == sm.STAGE_A:
                    self.choose_stage_a(panel)
                section = self.run_to_end(panel)
                self.assertEqual(workspace.tabs.currentIndex(), sp.TAB_RESULTS)
                self.assertTrue(panel.save_button.isVisible())
                self.assertTrue(panel.open_button.isVisible())
                rows = panel.table_cells("summary_parameters")
                shown = {row[0].split(",")[0]: row[2] for row in rows}
                for name, value in expected.items():
                    self.assertEqual(shown[name], value, name)
                known = {row[0].split(",")[0]: row[3] for row in rows}
                for name in expected:
                    self.assertEqual(known[name], f"{float(section['known_values'][name]):.6g}", name)
                self.assertTrue(any("N·m" in row[0] for row in rows))
                self.assertEqual(section["result"]["numerical_status"], "CONVERGED")
                if backend == sm.STAGE_A:
                    self.assertEqual(section["result"]["solves"], 86)  # the owner's run

    def test_the_summary_answers_the_five_questions_with_the_codes(self):
        _window, _workspace, panel = self.tabs()
        section = self.run_to_end(panel)
        summary = dict(panel.summary_cells)
        self.assertEqual(list(summary), ["Run", "Method", "Convergence", "Scientific checks", "Meaning of the numbers"])
        self.assertIn("Completed (COMPLETED)", summary["Run"])
        self.assertEqual(summary["Method"], "Ritz plate model (KIRCHHOFF_RITZ_4D)")
        self.assertEqual(summary["Convergence"], "Reached (CONVERGED)")
        self.assertIn("DIAGNOSTIC_OPTIMIZER_CANDIDATE", summary["Scientific checks"])
        self.assertIn("SYNTHETIC_SOFTWARE_TEST", summary["Meaning of the numbers"])
        self.assertIn("NOT_A_RELEASE_VALUE", summary["Meaning of the numbers"])
        self.assertIn("not accepted material properties", panel.statement.text())
        self.assertEqual(panel.badge.text(), "DIAGNOSTIC_OPTIMIZER_CANDIDATE | NOT_A_RELEASE_VALUE")
        self.assertEqual(section["result"]["release_status"], "NOT_A_RELEASE_VALUE")
        area = self.visible_area(self.window_workspace(panel))
        bottom = panel.statement.mapTo(area.viewport(), panel.statement.rect().bottomLeft()).y()
        self.assertLessEqual(bottom, area.viewport().height())  # the answer is on the first screen

    def window_workspace(self, panel):
        return panel.workspace

    def test_a_refusal_is_said_at_the_top_and_nothing_looks_like_a_result(self):
        _window, workspace, panel = self.tabs()
        self.choose_stage_a(panel)
        panel.package_source.setCurrentIndex(panel.package_source.findData(sm.SELECTED))
        self.run_to_end(panel)
        self.assertEqual(workspace.tabs.currentIndex(), sp.TAB_RESULTS)
        summary = dict(panel.summary_cells)
        self.assertIn("PACKAGE_REFUSED", summary["Scientific checks"])
        self.assertNotIn("Reached", summary["Convergence"])
        self.assertEqual(panel.table_cells("summary_parameters")[0][2], sm.DASH)
        self.assertEqual(panel.badge.property("state"), "blocked")

    def test_frequencies_and_holdout_are_in_the_first_tables(self):
        _window, _workspace, panel = self.tabs()
        section = self.run_to_end(panel)
        rows = panel.table_cells("summary_frequencies")
        self.assertEqual(len(rows), 10)
        self.assertEqual([row[1] for row in rows].count("HOLDOUT"), 2)
        self.assertEqual(rows, [[row[1], row[2], row[3], row[4], row[5], row[6], row[7]] for row in sm.frequency_rows(section)])
        errors = [row for row in sm.error_rows(section) if row[1] == "HOLDOUT"]
        for mode, _role, _before, after in errors:
            self.assertIn(f"mode {mode}:", panel.holdout_line.text())
            self.assertIn(f"{after:+.4f} %", panel.holdout_line.text())

    def test_a_tiny_error_keeps_its_size_and_sign(self):
        self.assertEqual(sm._signed_percent(-3.0e-7), "-3.00e-07 %")
        self.assertEqual(sm._signed_percent(1.5e-5), "+1.50e-05 %")
        self.assertEqual(sm._signed_percent(0.00123), "+0.0012 %")
        self.assertEqual(sm._signed_percent(0.0), "+0.0000 %")

    def test_cancel_stays_on_the_run_tab_says_so_and_results_says_it_too(self):
        _window, workspace, panel = self.tabs()
        gate = mat3._Gate()
        patcher = mock.patch.object(sm, "run_plate_inverse_study", gate)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(gate.go.set)
        panel.run_button.click()
        self.assertTrue(gate.reached.wait(20.0))
        self.app.processEvents()
        self.assertTrue(panel.progress.isVisible())
        self.assertFalse(panel.run_button.isEnabled())
        self.assertTrue(panel.cancel_button.isEnabled())
        self.assertFalse(panel.save_button.isEnabled())
        self.assertFalse(panel.open_button.isEnabled())
        for index in (1, 2, 3, 4, 0):  # the other tabs can be looked at during a run, and it goes on alone
            workspace.select_tab(index)
            self.app.processEvents()
        self.assertTrue(panel.busy())
        self.assertFalse(panel.run())
        panel.cancel_button.click()
        gate.go.set()
        self.wait(panel)
        self.assertEqual(workspace.tabs.currentIndex(), sp.TAB_RUN)
        self.assertEqual(panel.run_state.text(), sp.CANCELLED_TEXT)
        self.assertIsNone(panel.record)
        self.assertEqual(dict(panel.summary_cells)["Meaning of the numbers"], "No numbers")
        self.assertIn("CANCELLED", dict(panel.summary_cells)["Run"])
        self.assertNotIn("summary_parameters", panel._tables)
        self.assertTrue(panel.run_button.isEnabled())

    def test_a_form_that_does_not_build_stays_on_the_run_tab(self):
        _window, workspace, panel = self.tabs()
        with mock.patch.object(sm, "execute_study", side_effect=sm.FormProblem(("a reason",))):
            self.run_it(panel)
        self.assertEqual(workspace.tabs.currentIndex(), sp.TAB_RUN)
        self.assertIn("a reason", panel.message.text())
        self.assertTrue(panel.message.isVisible())


class Plots(_Tabs):
    def shown_plots(self, size=(1366, 768), backend=sm.RITZ):
        _window, workspace, panel = self.tabs(size)
        if backend != sm.RITZ:
            self.choose_stage_a(panel)
        section = self.run_to_end(panel)
        workspace.select_tab(sp.TAB_PLOTS)
        self.app.processEvents()
        for view in panel.plot_views.values():
            view.render_now()
        self.app.processEvents()
        return workspace, panel, section

    def test_plots_are_drawn_at_the_size_shown_and_take_the_width(self):
        workspace, panel, _section = self.shown_plots()
        area = self.visible_area(workspace)
        for view in panel.plot_views.values():
            self.assertTrue(view.isVisible())
            self.assertGreater(view.width(), 0.85 * area.viewport().width())
            self.assertGreater(view.width(), sp.sm.BASE_DPI * 6)  # well beyond the old fixed 480 pixels
            self.assertEqual(png_size(view.data), (view.width(), view.height()))
            self.assertEqual((view.pixmap().width(), view.pixmap().height()), (view.width(), view.height()))

    def test_a_resized_window_draws_anew_from_the_numbers(self):
        _workspace, panel, section = self.shown_plots((1366, 768))
        view = panel.error_view
        first = png_size(view.data)
        with mock.patch.object(view, "draw", wraps=view.draw) as drawn:
            panel.window().resize(1000, 768)
            self.app.processEvents()
            view.render_now()
        drawn.assert_called_once()
        self.assertEqual(drawn.call_args.args[0], section)
        self.assertLess(png_size(view.data)[0], first[0])
        self.assertEqual(png_size(view.data)[0], view.width())
        with mock.patch.object(view, "draw", side_effect=AssertionError("the same picture is not drawn twice")):
            view.render_now()

    def test_each_screen_scale_gets_its_own_pixels_never_an_enlarged_picture(self):
        _workspace, panel, _section = self.shown_plots()
        view = panel.error_view
        width, height = view.width(), view.height()
        for ratio in (1.0, 1.5, 2.0):
            with self.subTest(ratio=ratio), mock.patch.object(view, "scale", return_value=ratio):
                view._drawn = None
                self.assertTrue(view.render_now())
                self.assertEqual(png_size(view.data), (math.floor(width * ratio), math.floor(height * ratio)))

    def test_a_real_200_percent_screen_gets_twice_the_pixels_at_the_same_logical_size(self):
        code = """
import json, sys
from PySide6.QtWidgets import QApplication
from new_gui import materials_study_model as sm, materials_study_panel as sp
app = QApplication([])
section = json.loads(open(sys.argv[1], encoding="utf-8").read())
view = sp.PlotView("objective", sm.objective_plot, "plot")
view.resize(700, 400)
view.show()
view.set_section(section)
view.render_now()
print(json.dumps({"ratio": view.devicePixelRatioF(), "logical": [view.width(), view.height()],
                  "pixmap": [view.pixmap().width(), view.pixmap().height()], "pixmap_ratio": view.pixmap().devicePixelRatio()}))
"""
        path = self.root / "section.json"
        path.write_text(json.dumps(mat3.study(sm.STAGE_A)), encoding="utf-8")
        environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR="2", OMP_NUM_THREADS="1", PYTHONIOENCODING="utf-8",
                           PYTHONPATH=str(mat3.ROOT / "src"))
        with mock.patch("subprocess.Popen", mat3.REAL_POPEN):
            done = subprocess.run([sys.executable, "-c", code, str(path)], env=environment, capture_output=True, text=True, timeout=120, check=False)
        self.assertEqual(done.returncode, 0, done.stderr)
        found = json.loads(done.stdout.strip().splitlines()[-1])
        self.assertEqual(found["ratio"], 2.0)
        self.assertEqual(found["pixmap_ratio"], 2.0)
        self.assertEqual(found["pixmap"], [2 * found["logical"][0], 2 * found["logical"][1]])

    def test_text_keeps_its_size_when_the_scale_changes(self):
        section = mat3.study(sm.RITZ)
        for draw in (sm.error_plot, sm.objective_plot):
            self.assertEqual(png_size(draw(section, 800, 450, 2.0)), (1600, 900))
            self.assertEqual(png_size(draw(section, 800, 450, 1.0)), (800, 450))

    def test_the_saved_plot_has_a_fixed_high_resolution(self):
        _workspace, panel, _section = self.shown_plots()
        for kind, view in panel.plot_views.items():
            path = self.root / f"{kind}_saved"
            with mock.patch.object(sp.QFileDialog, "getSaveFileName", return_value=(str(path), "")):
                panel.plot_buttons[kind].click()
            saved = path.with_name(path.name + ".png")
            self.assertTrue(saved.is_file())
            self.assertEqual(png_size(saved.read_bytes()), (3200, 1800))
            self.assertGreater(3200, png_size(view.data)[0])
        self.assertFalse(panel.save_plot("error", str(self.root / "no such folder" / "x.png")))
        self.assertIn("not saved", panel.plot_message.text())

    def test_the_errors_are_signed_model_against_observation_and_holdout_is_marked(self):
        section = mat3.study(sm.RITZ)
        rows = sm.error_rows(section)
        self.assertEqual(len(rows), 10)
        by_mode = {row["experimental_mode"]: row["row_id"] for row in section["declaration"]["rows"]}
        found = {row["row_id"]: row for row in section["result"]["frequencies"]}
        signs = set()
        for mode, role, before, after in rows:
            row = found[by_mode[mode]]
            self.assertEqual(role, row["role"])
            self.assertEqual(before, 100.0 * (row["initial_model_hz"] / row["experimental_hz"] - 1.0))
            self.assertEqual(after, 100.0 * (row["final_model_hz"] / row["experimental_hz"] - 1.0))
            signs.add(before > 0.0)
        self.assertEqual(signs, {True, False})  # both signs occur, and neither is folded
        self.assertEqual([row[1] for row in rows].count("HOLDOUT"), 2)

    def test_small_residuals_are_drawn_on_their_own_scale_not_hidden(self):
        section = mat3.study(sm.RITZ)
        captured = {}
        original = sm._error_axis

        def spy(axis, rows, column, title, labels):
            original(axis, rows, column, title, labels)
            captured[column] = axis.get_ylim()

        with mock.patch.object(sm, "_error_axis", spy):
            self.assertIsNotNone(sm.error_plot(section))
        rows = sm.error_rows(section)
        for column in (2, 3):
            reach = max(abs(row[column]) for row in rows)
            self.assertLess(reach, captured[column][1])
            self.assertLess(captured[column][0], -reach)  # every bar is inside, with zero in the middle
            self.assertLess(captured[column][1], 2.0 * reach)  # and it fills its own panel
        self.assertLess(captured[3][1], captured[2][1] / 100.0)

    def test_the_objective_plot_uses_the_saved_points_only(self):
        section = mat3.study(sm.RITZ)
        points = sm.objective_points(section)
        accepted = [row["objective_before"] for row in section["result"]["iterations"] if row["accepted"]]
        self.assertEqual(list(points), [mp.number(value) for value in accepted] + [mp.number(section["result"]["final_objective"])])

    def test_no_data_is_said_and_no_plot_is_drawn(self):
        _window, workspace, panel = self.tabs()
        workspace.select_tab(sp.TAB_PLOTS)
        self.app.processEvents()
        self.assertTrue(panel.plots_empty.isVisible())
        self.assertFalse(panel.error_card.isVisible())
        self.assertFalse(panel.save_plot("error", str(self.root / "x.png")))
        refused = sm.execute_study(mat3.stage_form(""), threading.Event())
        self.assertIsNone(sm.objective_plot(refused))
        self.assertIsNone(sm.error_plot(refused))


class Diagnostics(_Tabs):
    def test_everything_technical_is_kept_in_short_named_groups(self):
        _window, workspace, panel = self.tabs()
        section = self.run_to_end(panel)
        workspace.select_tab(sp.TAB_DIAGNOSTICS)
        self.app.processEvents()
        self.assertEqual(list(panel.sections), ["status", "parameters", "conditional", "modes", "fit", "convergence", "rank", "families"])
        for key, group in panel.sections.items():
            self.assertTrue(group.toggle.text())
            self.assertEqual(group.body.isVisible(), key == "status")  # one open: not ten tables in a row
        for key, rows in (("parameters", sm.parameter_rows), ("frequencies", sm.frequency_rows), ("iterations", sm.iteration_rows),
                          ("identifiability", sm.identifiability_rows), ("holdout", sm.holdout_rows), ("families", sm.family_rows),
                          ("convergence", sm.convergence_rows), ("uncertainty", sm.uncertainty_rows), ("conditional", sm.conditional_rows),
                          ("status", sm.status_rows)):
            self.assertEqual(panel.table_cells(key), [list(row) for row in rows(section)], key)
        self.assertEqual(len(panel.table_cells("observations")), 10)
        self.assertIn(section["statement"], panel.original_statement.text())

    def test_the_exact_codes_stay_available(self):
        _window, _workspace, panel = self.tabs()
        self.run_to_end(panel)
        seen = json.dumps(panel.table_cells("status"), ensure_ascii=False) + panel.method_combo.currentData()
        for code in CODES:
            if code != "STAGE_A_MATRIX_3D":
                self.assertIn(code, seen)
        self.assertIn("STAGE_A_MATRIX_3D", [panel.method_combo.itemData(i) for i in range(2)])

    def test_the_terms_are_explained(self):
        _window, _workspace, panel = self.tabs()
        for key, word in (("modes", "MAC"), ("fit", "HOLDOUT"), ("rank", "Rank"), ("parameters", "Uncertainty")):
            self.assertIn(word, panel.sections[key].toggle.toolTip())
        self.assertIn("Sigma", panel.numeric_fields["sigma"].toolTip())
        self.assertIn("HOLDOUT", panel.numeric_fields["holdout_modes"].toolTip())

    def test_prepare_shows_the_rows_on_diagnostics_without_a_fit(self):
        _window, workspace, panel = self.tabs()
        with mock.patch.object(sm, "run_plate_inverse_study", side_effect=AssertionError("prepare does not fit")):
            self.assertTrue(panel.prepare())
            self.wait(panel)
        self.assertEqual(workspace.tabs.currentIndex(), sp.TAB_RUN)
        self.assertEqual(len(panel.table_cells("observations")), 10)
        workspace.select_tab(sp.TAB_DIAGNOSTICS)
        self.app.processEvents()
        self.assertTrue(panel.diagnostics_card.isVisible())
        self.assertIsNone(panel.record)


class Layout(_Tabs):
    SIZES = ((1366, 768), (900, 700), (1920, 1080))

    def test_no_tab_scrolls_sideways_at_any_size_and_tables_scroll_inside(self):
        for size in self.SIZES:
            with self.subTest(size=size):
                window, workspace, panel = self.tabs(size)
                self.run_to_end(panel)
                for group in panel.sections.values():
                    group.toggle.setChecked(True)
                panel.advanced.toggle.setChecked(True)
                for index in range(5):
                    workspace.select_tab(index)
                    self.app.processEvents()
                    self.app.processEvents()
                    outer = window.stack.currentWidget()
                    self.assertEqual(outer.horizontalScrollBar().maximum(), 0, index)
                    self.assertEqual(outer.verticalScrollBar().maximum(), 0, index)
                    self.assertEqual(self.visible_area(workspace).horizontalScrollBar().maximum(), 0, index)
                for table in panel.findChildren(QTableWidget):
                    self.assertLessEqual(table.height(), sp.TABLE_HEIGHT)
                window.close()

    def test_a_long_table_stays_inside_its_own_scroll_area(self):
        _window, _workspace, panel = self.tabs((900, 700))
        rows = tuple((f"row {index}", "a very long text " * 30) for index in range(200))
        panel._table("status", panel._boxes["status"], ("Status", "Value"), rows, 1)
        self.app.processEvents()
        table = panel._tables["status"]
        self.assertEqual(table.height(), sp.TABLE_HEIGHT)
        self.assertLess(panel.minimumSizeHint().width(), 900)

    def test_the_buttons_are_not_cut_at_the_small_size(self):
        window, workspace, panel = self.tabs((900, 700))
        self.run_to_end(panel)
        for index in range(5):
            workspace.select_tab(index)
            self.app.processEvents()
            for button in window.stack.currentWidget().findChildren(QPushButton):
                if button.isVisible():
                    self.assertGreaterEqual(button.width(), button.minimumSizeHint().width(), button.text())

    def test_every_command_can_take_the_keyboard_focus(self):
        _window, workspace, panel = self.tabs()
        for widget in (workspace.tabs, panel.run_button, panel.cancel_button, panel.method_combo, panel.advanced.toggle, panel.save_button,
                       panel.open_button, panel.plot_buttons["error"], panel.sections["fit"].toggle):
            self.assertNotEqual(widget.focusPolicy().value & sp.Qt.FocusPolicy.TabFocus.value, 0, widget.objectName())


class SaveAndOpen(_Tabs):
    def saved(self, backend):
        _window, _workspace, panel = self.tabs()
        if backend != sm.RITZ:
            self.choose_stage_a(panel)
        self.run_to_end(panel)
        path = self.root / f"{backend}.mcproj"
        self.assertTrue(panel.save_results(str(path)))
        self.wait(panel)
        return panel, path

    def test_open_shows_the_same_summary_and_plots_without_a_calculation_and_says_it_is_saved(self):
        for backend in (sm.RITZ, sm.STAGE_A):
            with self.subTest(backend=backend):
                first, path = self.saved(backend)
                summary = first.summary_cells
                parameters, frequencies = first.table_cells("summary_parameters"), first.table_cells("summary_frequencies")
                plot = sm.error_plot(first.record["materials"])
                _window, workspace, panel = self.tabs()
                self.assertEqual(ap.project_schema(path), ap.SCHEMA_V2)
                refuse = AssertionError("no calculation")
                with mock.patch.object(sm, "run_plate_inverse_study", side_effect=refuse), mock.patch.object(sm, "execute_study", side_effect=refuse), \
                        mock.patch.object(sm, "build_request", side_effect=refuse), mock.patch.object(sm, "inspect_stage_a_package", side_effect=refuse):
                    self.assertTrue(panel.open_results(str(path)))
                    self.wait(panel)
                    self.app.processEvents()
                    self.assertEqual(workspace.tabs.currentIndex(), sp.TAB_RESULTS)
                    self.assertEqual(panel.summary_cells, summary)
                    self.assertEqual(panel.table_cells("summary_parameters"), parameters)
                    self.assertEqual(panel.table_cells("summary_frequencies"), frequencies)
                    self.assertIn(sp.SNAPSHOT_TEXT.format(name=path.name), panel.origin_note.text())
                    self.assertFalse(panel.changed_note.isVisible())
                    workspace.select_tab(sp.TAB_PLOTS)
                    self.app.processEvents()
                    self.assertTrue(panel.error_view.render_now() or panel.error_view.data)
                    self.assertEqual(sm.error_plot(panel.record["materials"]), plot)  # from the saved numbers alone
                self.assertFalse(panel.busy())
                path.unlink()

    def test_a_changed_setting_marks_the_shown_result_as_older(self):
        panel, _path = self.saved(sm.RITZ)
        self.assertFalse(panel.changed_note.isVisible())
        panel.solves_field.setText("500")
        self.assertTrue(panel.changed_note.isVisible())
        self.assertIn("previous settings", panel.changed_note.text())
        panel.solves_field.setText("900")
        self.assertFalse(panel.changed_note.isVisible())

    def test_a_refused_file_is_said_on_the_results_tab(self):
        _window, workspace, panel = self.tabs()
        bad = self.root / "bad.mcproj"
        bad.write_bytes(b"not a project")
        workspace.select_tab(sp.TAB_RESULTS)
        self.assertTrue(panel.open_results(str(bad)))
        self.wait(panel)
        self.app.processEvents()
        self.assertTrue(panel.results_message.isVisible())
        self.assertIn("Not opened", panel.results_message.text())
        self.assertTrue(panel.results_empty.isVisible())

    def test_the_format_and_the_saved_codes_are_unchanged(self):
        panel, path = self.saved(sm.STAGE_A)
        document = mp.read_materials_project(path)
        self.assertEqual(document["schema"], "universal/analysis-project/v2")
        self.assertEqual(ap.SCHEMA, "universal/analysis-project/v1")
        section = document["materials"]
        result = section["result"]
        self.assertEqual((result["backend_id"], result["numerical_status"], result["scientific_status"], result["release_status"]),
                         ("STAGE_A_MATRIX_3D", "CONVERGED", "DIAGNOSTIC_OPTIMIZER_CANDIDATE", "NOT_A_RELEASE_VALUE"))
        self.assertEqual(section["declaration"]["intent"], "SYNTHETIC_SOFTWARE_TEST")
        self.assertEqual(result["restrictions_unchanged"], ["M8 GATE NOT_MET", "D-077 NO_GLOBAL_PARAMETER_VALUE", "production Auto-ID BLOCKED"])
        self.assertEqual(section["statement"], sm.STATEMENT)  # the saved English statement and provenance are not retranslated
        self.assertIn("SYNTHETIC", section["declaration"]["provenance"])
        self.assertEqual(section["result_hash"], panel.record["materials"]["result_hash"])


CYRILLIC = re.compile("[Ѐ-ӿ]")


def shown_texts(window) -> list:
    """Every text a user can see or hover in the window: labels, buttons, fields, lists, tabs, tables, tooltips and menus."""
    found = [window.windowTitle()]
    for widget in window.findChildren(QWidget):
        found += [widget.toolTip(), widget.accessibleName(), widget.windowTitle()]
        if isinstance(widget, (QLabel, QAbstractButton)):
            found.append(widget.text())
        if isinstance(widget, QLineEdit):
            found += [widget.text(), widget.placeholderText()]
        if isinstance(widget, QComboBox):
            for index in range(widget.count()):
                found += [widget.itemText(index), str(widget.itemData(index, Qt.ItemDataRole.ToolTipRole) or "")]
        if isinstance(widget, QTabBar):
            found += [widget.tabText(index) for index in range(widget.count())]
        if isinstance(widget, QTableWidget):
            found += [widget.horizontalHeaderItem(column).text() for column in range(widget.columnCount())
                      if widget.horizontalHeaderItem(column) is not None]
            found += [widget.item(row, column).text() for row in range(widget.rowCount()) for column in range(widget.columnCount())
                      if widget.item(row, column) is not None]
    actions = list(window.menuBar().actions())
    while actions:
        action = actions.pop()
        found += [action.text(), action.toolTip()]
        if action.menu() is not None:
            actions += list(action.menu().actions())
    return [text for text in found if text]


def edit_width(combo) -> int:
    option = QStyleOptionComboBox()
    combo.initStyleOption(option)
    return combo.style().subControlRect(QStyle.ComplexControl.CC_ComboBox, option, QStyle.SubControl.SC_ComboBoxEditField, combo).width()


class EnglishOnly(_Tabs):
    """MAT-4.UX1.F1: the interface is English only, wherever a text can appear."""

    def open_everything(self, workspace, panel) -> None:
        for group in panel.sections.values():
            group.toggle.setChecked(True)
        panel.advanced.toggle.setChecked(True)
        workspace.workflow.toggle.setChecked(True)
        for index in range(5):
            workspace.select_tab(index)
            self.app.processEvents()

    def test_no_russian_text_in_the_window_for_either_method_and_every_state(self):
        for backend in (sm.RITZ, sm.STAGE_A):
            with self.subTest(backend=backend):
                window, workspace, panel = self.tabs((900, 700))
                if backend == sm.STAGE_A:
                    self.choose_stage_a(panel)
                self.run_to_end(panel)
                self.open_everything(workspace, panel)
                texts = shown_texts(window)
                panel.solves_field.setText("many")  # a form problem
                panel.package_source.setCurrentIndex(panel.package_source.findData(sm.SELECTED))  # no package chosen
                self.app.processEvents()
                texts += shown_texts(window)
                panel.source_combo.setCurrentIndex(panel.source_combo.findData(sm.REAL_SOURCE))  # the refusal of real data
                self.app.processEvents()
                panel.run()
                texts += shown_texts(window)
                self.assertGreater(len(texts), 300)
                self.assertEqual([text for text in texts if CYRILLIC.search(text)], [])
                window.close()

    def test_no_russian_string_in_the_new_gui_sources(self):
        """Covers what no single screen shows: dialog titles, messages of failures and every other literal."""
        root = Path(__file__).resolve().parents[1] / "src" / "new_gui"
        found = []
        for path in sorted(root.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            found += [(path.name, node.lineno) for node in ast.walk(tree)
                      if isinstance(node, ast.Constant) and isinstance(node.value, str) and CYRILLIC.search(node.value)]
        self.assertEqual(found, [])

    def test_the_saved_plot_files_have_english_names(self):
        self.assertEqual(sp.PLOT_FILES, {"error": "frequency_error.png", "objective": "objective_convergence.png"})


class NarrowWindow(_Tabs):
    """MAT-4.UX1.F1: the three defects of the Windows smoke test at 900 x 700 (D1, D2, D3), and the usual size."""

    SIZES = ((900, 700), (1366, 768))

    def test_d1_every_plot_text_lies_inside_the_picture(self):
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.text import Text

        for backend in (sm.RITZ, sm.STAGE_A):
            section = mat3.study(backend)
            # the smallest heights the page gives (PLOT_RATIOS) near a 900-pixel window, at 100 % and 150 %, and the saved size
            for build, size in ((sm.objective_figure, (560, 320, 1.0)), (sm.objective_figure, (690, 320, 1.5)),
                                (sm.error_figure, (560, 520, 1.0)), (sm.error_figure, (690, 520, 1.5)),
                                (sm.objective_figure, sm.EXPORT_SIZE), (sm.error_figure, sm.EXPORT_SIZE)):
                with self.subTest(backend=backend, plot=build.__name__, size=size):
                    figure = build(section, *size)
                    renderer = FigureCanvasAgg(figure).get_renderer()
                    figure.draw(renderer)
                    width, height = figure.get_size_inches()
                    drawn = figure.get_tightbbox(renderer)  # everything drawn: titles, axis labels, ticks, legend, annotations
                    self.assertGreaterEqual(drawn.x0, -0.01)
                    self.assertGreaterEqual(drawn.y0, -0.01)
                    self.assertLessEqual(drawn.x1, width + 0.01)
                    self.assertLessEqual(drawn.y1, height + 0.01)
                    frame = figure.bbox
                    for axis in figure.axes:  # each axis label lies inside the picture, both ends
                        for label in (axis.yaxis.label, axis.xaxis.label, axis.title):
                            if label.get_text():
                                box = label.get_window_extent(renderer)
                                self.assertTrue(frame.x0 - 0.5 <= box.x0 and box.x1 <= frame.x1 + 0.5, label.get_text())
                                self.assertTrue(frame.y0 - 0.5 <= box.y0 and box.y1 <= frame.y1 + 0.5, label.get_text())
                    texts = [text.get_text() for text in figure.findobj(Text) if text.get_text().strip()]
                    self.assertTrue(set(texts) & {"Objective", "Error, %"})
                    self.assertEqual([text for text in texts if CYRILLIC.search(text)], [])

    def test_d1_the_objective_label_is_shorter_than_its_axis_on_screen(self):
        from matplotlib.backends.backend_agg import FigureCanvasAgg

        for backend in (sm.RITZ, sm.STAGE_A):
            with self.subTest(backend=backend):
                _workspace, panel, _section = Plots.shown_plots(self, (900, 700), backend)
                view = panel.objective_view
                figure = sm.objective_figure(view.section, view.width(), view.height(), view.scale())
                renderer = FigureCanvasAgg(figure).get_renderer()
                figure.draw(renderer)
                axis = figure.axes[0]
                self.assertLess(axis.yaxis.label.get_window_extent(renderer).height, axis.get_window_extent(renderer).height)
                panel.window().close()

    def test_d2_the_frequency_table_shows_every_role_and_column_without_scrolling(self):
        for size in self.SIZES:
            for backend in (sm.RITZ, sm.STAGE_A):
                with self.subTest(size=size, backend=backend):
                    window, workspace, panel = self.tabs(size)
                    if backend == sm.STAGE_A:
                        self.choose_stage_a(panel)
                    section = self.run_to_end(panel)
                    workspace.select_tab(sp.TAB_RESULTS)
                    self.app.processEvents()
                    table = panel._tables["summary_frequencies"]
                    header = table.horizontalHeader()
                    for column in range(table.columnCount()):  # no cell and no header is cut: "HOLDOUT" stays whole
                        self.assertGreaterEqual(header.sectionSize(column), table.sizeHintForColumn(column), column)
                        self.assertGreaterEqual(header.sectionSize(column), header.sectionSizeHint(column), column)
                    natural = sum(table.natural)
                    # The offscreen test font is about 1.6 times as wide as Segoe UI, so at 900 the columns fit on Windows (measured
                    # there: 482 of 634 pixels) but not always here. Whenever they fit, the whole table is in view and the free
                    # width is shared, not given to one column.
                    if natural <= table.viewport().width():
                        self.assertEqual(table.horizontalScrollBar().maximum(), 0)  # "Error after" is in view
                        self.assertEqual(header.length(), table.viewport().width())
                        spare = [header.sectionSize(column) - table.natural[column] for column in range(table.columnCount())]
                        self.assertLessEqual(max(spare) - min(spare), 1)
                    elif size == (1366, 768):
                        self.fail(f"the frequency table does not fit at 1366: {natural} > {table.viewport().width()}")
                    self.assertIn("HOLDOUT", [row[1] for row in panel.table_cells("summary_frequencies")])
                    self.assertEqual(panel.table_cells("summary_frequencies"),
                                     [list(row) for row in sm.summary_frequency_rows(section)])
                    self.assertEqual(self.visible_area(workspace).horizontalScrollBar().maximum(), 0)
                    window.close()

    def test_d3_no_choice_list_cuts_its_entries(self):
        for size in self.SIZES:
            for backend in (sm.RITZ, sm.STAGE_A):
                with self.subTest(size=size, backend=backend):
                    window, workspace, panel = self.tabs(size)
                    if backend == sm.STAGE_A:
                        self.choose_stage_a(panel)
                    panel.advanced.toggle.setChecked(True)
                    workspace.select_tab(sp.TAB_RUN)
                    self.app.processEvents()
                    combos = [combo for combo in panel.findChildren(QComboBox) if combo.isVisible()]
                    self.assertEqual(panel.package_source in combos, backend == sm.STAGE_A)
                    for combo in combos:
                        for index in range(combo.count()):
                            text = combo.itemText(index)
                            self.assertGreaterEqual(edit_width(combo), combo.fontMetrics().horizontalAdvance(text), text)
                    self.assertEqual(self.visible_area(workspace).horizontalScrollBar().maximum(), 0)
                    window.close()


class RealSourceView(_Tabs):
    """REAL-PLATE.R1.F1: a real source shows no synthetic specimen input; the synthetic example comes back unchanged."""

    def real(self, panel, on=True):
        panel.source_combo.setCurrentIndex(panel.source_combo.findData(sm.REAL_SOURCE if on else sm.SYNTHETIC_SOURCE))
        self.app.processEvents()

    def shown_texts(self, panel) -> list:
        page = panel.widget(sp.TAB_RUN).widget()
        found = []
        for widget in page.findChildren(QWidget):
            if not widget.isVisible():
                continue
            if isinstance(widget, (QLabel, QAbstractButton)):
                found.append(widget.text())
            if isinstance(widget, QLineEdit):
                found.append(widget.text())
            if isinstance(widget, QComboBox):
                found.append(widget.currentText())
        return [text for text in found if text]

    def test_the_real_view_shows_no_synthetic_input_and_one_message(self):
        for backend in (sm.RITZ, sm.STAGE_A):
            with self.subTest(backend=backend):
                window, workspace, panel = self.tabs((900, 700))
                if backend == sm.STAGE_A:
                    self.choose_stage_a(panel)
                panel.advanced.toggle.setChecked(True)
                self.real(panel)
                for widget in (panel.geometry_card, panel.advanced_card, panel.method_combo, panel.method_text, panel.run_button,
                               panel.cancel_button, panel.a_field, panel.mass_field, panel.thickness_field, panel.solves_field,
                               panel.package_source):
                    self.assertFalse(widget.isVisible(), widget.objectName())
                self.assertTrue(panel.source_combo.isVisible() and panel.source_combo.isEnabled())
                self.assertTrue(panel.blocked.isVisible())
                self.assertEqual(panel.blocked.text(), sp.REAL_VIEW_TEXT)
                self.assertIn("FE / Experiment", panel.blocked.text())
                self.assertIn("Real-data inverse execution: BLOCKED", panel.blocked.text())
                shown = " | ".join(self.shown_texts(panel))
                defaults = sm.default_form(backend)
                for text in (sm.METHOD_TEXT[backend], sm.METHOD_NAMES[backend], sm.geometry_text(defaults), "Length a", "Mass",
                             "Run calculation", "Advanced settings"):
                    self.assertNotIn(text, shown)
                self.assertFalse(panel.run())
                self.assertIn("NOT_AUTHORIZED", panel.message.text())
                self.assertIsNone(panel.record)
                self.assertEqual(self.visible_area(workspace).horizontalScrollBar().maximum(), 0)
                window.close()

    def test_choosing_synthetic_again_restores_the_entered_inputs_of_both_methods(self):
        window, workspace, panel = self.tabs()
        panel.a_field.setText("310")
        panel.mass_field.setText("118.37")
        panel.solves_field.setText("700")
        panel.parameter_fields[sm.RITZ]["D11"]["start"].setText("12.5")
        before = panel.form()
        self.real(panel)
        self.real(panel, False)
        self.assertEqual(panel.form(), before)
        for widget in (panel.geometry_card, panel.advanced_card, panel.method_combo, panel.method_text, panel.run_button):
            self.assertTrue(widget.isVisible(), widget.objectName())
        self.assertFalse(panel.blocked.isVisible())
        self.choose_stage_a(panel)
        stage = panel.form()
        self.real(panel)
        self.real(panel, False)
        self.assertEqual(panel.form(), stage)
        self.assertFalse(panel.geometry_card.isVisible())  # Stage A's own view: the package holds its geometry
        self.assertTrue(panel.run_button.isVisible() and panel.run_button.isEnabled())
        window.close()

    def test_both_methods_still_run_after_a_visit_to_the_real_view(self):
        window, workspace, panel = self.tabs()
        self.real(panel)
        self.real(panel, False)
        ritz = self.run_to_end(panel)
        self.assertEqual(ritz["result"]["numerical_status"], "CONVERGED")
        workspace.select_tab(sp.TAB_RUN)
        self.choose_stage_a(panel)
        self.real(panel)
        self.real(panel, False)
        section = self.run_to_end(panel)
        result = section["result"]
        self.assertEqual((result["solves"], result["numerical_status"]), (86, "CONVERGED"))
        rows = {row[0].split(",")[0]: row for row in sm.summary_parameter_rows(section)}
        self.assertEqual((rows["D"][2], rows["D66"][2], rows["r"][2]), ("0.36", "0.05", "0.09"))
        window.close()


class SourceSwitchGuards(_Tabs):
    """REAL-PLATE.R1.F1 (final): the source cannot change under a running job, and a real source hides stale form errors."""

    def test_a_running_calculation_keeps_its_cancel_whatever_the_source(self):
        window, workspace, panel = self.tabs((900, 700))
        gate = mat3._Gate()

        def held_or_real(declaration, **options):  # the real-data gate's own call (no cancel) goes to the workflow
            return gate(declaration, **options) if "cancel" in options else gate.real(declaration, **options)

        patcher = mock.patch.object(sm, "run_plate_inverse_study", held_or_real)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(gate.go.set)
        self.assertTrue(panel.source_combo.isEnabled())
        panel.run_button.click()
        self.assertTrue(gate.reached.wait(20.0))
        self.app.processEvents()
        self.assertEqual(panel._active, sp.RUNNING)
        self.assertFalse(panel.source_combo.isEnabled())  # the user cannot switch it now
        panel.source_combo.setCurrentIndex(panel.source_combo.findData(sm.REAL_SOURCE))  # nor can a programmatic change hide Cancel
        self.app.processEvents()
        self.assertTrue(panel.cancel_button.isVisible() and panel.cancel_button.isEnabled())
        self.assertTrue(panel.run_state.isVisible())
        self.assertTrue(panel.cancel())
        gate.go.set()
        self.wait(panel)
        self.app.processEvents()
        self.assertIsNone(panel.record)
        self.assertEqual(panel.badge.text(), "CANCELLED")
        self.assertTrue(panel.source_combo.isEnabled())  # free again once the job has ended
        self.assertFalse(panel.cancel_button.isVisible())  # the real view, now that nothing runs
        panel.source_combo.setCurrentIndex(panel.source_combo.findData(sm.SYNTHETIC_SOURCE))
        self.app.processEvents()
        self.assertTrue(panel.run_button.isVisible() and panel.run_button.isEnabled())
        window.close()

    def test_the_source_is_locked_during_every_background_job(self):
        window, workspace, panel = self.tabs()
        for kind in (sp.PREPARING, "package", "open", "save"):
            with self.subTest(job=kind):
                panel._active = kind
                panel._refresh()
                self.assertFalse(panel.source_combo.isEnabled())
                panel._active = None
                panel._refresh()
                self.assertTrue(panel.source_combo.isEnabled())
        window.close()

    def test_a_real_source_hides_stale_form_errors_and_synthetic_restores_them(self):
        window, workspace, panel = self.tabs((900, 700))
        panel.solves_field.setText("many")
        self.app.processEvents()
        self.assertTrue(panel.message.isVisible())
        self.assertIn("Solve limit", panel.message.text())
        panel.source_combo.setCurrentIndex(panel.source_combo.findData(sm.REAL_SOURCE))
        self.app.processEvents()
        self.assertFalse(panel.message.isVisible())
        self.assertNotIn("Solve limit", panel.message.text())
        self.assertTrue(panel.blocked.isVisible())
        self.assertEqual(panel.blocked.text(), sp.REAL_VIEW_TEXT)
        panel.note_field.setText("changed while hidden")  # a hidden field changing does not bring the error back
        self.app.processEvents()
        self.assertFalse(panel.message.isVisible())
        self.assertFalse(panel.run())
        self.assertIn("NOT_AUTHORIZED", panel.message.text())  # the workflow's refusal of a direct call is still said
        panel.source_combo.setCurrentIndex(panel.source_combo.findData(sm.SYNTHETIC_SOURCE))
        self.app.processEvents()
        self.assertEqual(panel.solves_field.text(), "many")  # nothing was cleared
        self.assertTrue(panel.message.isVisible())
        self.assertIn("Solve limit", panel.message.text())
        self.assertFalse(panel.run_button.isEnabled())
        panel.solves_field.setText("900")
        self.app.processEvents()
        self.assertFalse(panel.message.isVisible())
        self.assertTrue(panel.run_button.isEnabled())
        window.close()


class Boundaries(unittest.TestCase):
    def test_no_mathematical_logic_entered_the_widgets(self):
        root = Path(__file__).resolve().parents[1] / "src" / "new_gui"
        for name in ("materials_study_panel.py", "materials_workspace.py"):
            tree = ast.parse((root / name).read_text(encoding="utf-8"))
            imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
            imported |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
            for forbidden in ("numpy", "scipy", "matplotlib", "services.plate_material_workflow", "services.plate_ritz_forward",
                              "services.identification_step", "subprocess"):
                self.assertNotIn(forbidden, imported, name)

    def test_the_saved_statement_and_provenance_text_did_not_change(self):
        """They are part of saved results and of the declaration hash, so translating them would change results."""
        self.assertTrue(sm.STATEMENT.startswith("SYNTHETIC software test."))
        self.assertTrue(sm.RITZ_PROVENANCE.startswith("SYNTHETIC: observations computed by the Ritz solver"))
        self.assertTrue(sm.STAGE_PROVENANCE.startswith("SYNTHETIC: observations computed from a diagonal matrix fixture"))

    def test_the_owner_stage_a_numbers_are_unchanged(self):
        section = mat3.study(sm.STAGE_A)
        result = section["result"]
        self.assertEqual(result["solves"], 86)
        self.assertEqual(result["numerical_status"], "CONVERGED")
        rows = {row[0].split(",")[0]: row for row in sm.summary_parameter_rows(section)}
        self.assertEqual((rows["D"][2], rows["D66"][2], rows["r"][2]), ("0.36", "0.05", "0.09"))
        self.assertEqual((rows["D"][1], rows["D66"][1], rows["r"][1]), ("0.34", "0.046", "0.05"))


if __name__ == "__main__":
    unittest.main()
