"""ABM-UX5: the owner's manual usability findings. Synthetic data; Qt ``offscreen``; no Abaqus, no solver, no identification."""

from __future__ import annotations

import io
import unittest
from unittest import mock

import numpy as np
from PIL import Image
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest

import test_gui_ux_r1 as ux
from new_gui import analyze_model as am
from new_gui import mac_points_model as mp
from new_gui import materials_study_model as msm
from new_gui import production_window as pw
from new_gui import research_tuning_panel as rtp
from new_gui import review_model as rv
from new_gui import review_panel as rp
from new_gui import shape_model as sm
from new_gui.workspace_state import EXPERIMENTAL, FE
from services import research_frequency_tuning as rft


def png_size(data: bytes) -> tuple:
    return Image.open(io.BytesIO(data)).size


def state():
    return rv.ReviewState(ux._Stub(ux.NEAREST, ux.FE_ROWS))


class ChartTests(unittest.TestCase):
    def test_a_chart_is_drawn_at_the_shown_size_and_screen_ratio(self):
        for ratio in (1.0, 1.25, 1.5, 2.0):
            chart = rv.frequency_chart(state(), 0, 420, 300, ratio)
            self.assertEqual(png_size(chart.png), (round(420 * ratio), round(300 * ratio)))
            self.assertEqual(chart.pixel_ratio, ratio)
            self.assertEqual([p[0] for p in chart.points], [0, 1, 2])
        for ratio in (1.25, 2.0):  # at every ratio each hit lies on its own dot
            chart = rv.frequency_chart(state(), None, 420, 300, ratio)
            image = np.asarray(Image.open(io.BytesIO(chart.png)).convert("RGB")).astype(int)
            for row, x, y in chart.points:
                self.assertGreater(image[int(round(y)), int(round(x))][2] - image[int(round(y)), int(round(x))][0], 60, (ratio, row))
        self.assertEqual(png_size(rv.frequency_plot(state(), 0)), (780, 468))  # the unsized form stays as it was

    def test_each_dot_is_where_its_row_is_drawn(self):
        chart = rv.frequency_chart(state(), None, 500, 360, 1.0)
        image = np.asarray(Image.open(io.BytesIO(chart.png)).convert("RGB")).astype(int)
        for row, x, y in chart.points:
            colour = image[int(round(y)), int(round(x))]
            self.assertLess(colour[0], 120, row)  # the blue dot of an automatic candidate, not white paper
            self.assertGreater(colour[2], 150, row)
            self.assertEqual(rv.rows_at(chart, x + 3, y - 3), (row,))
        self.assertEqual(rv.rows_at(chart, 2, 2), ())

    def test_overlapping_dots_are_all_returned_never_one_chosen(self):
        chart = rv.Chart(b"", points=((0, 100.0, 100.0), (2, 101.0, 100.0), (1, 300.0, 50.0)))
        self.assertEqual(rv.rows_at(chart, 100.4, 100.0), (0, 2))
        self.assertEqual(rv.rows_at(chart, 300.0, 50.0), (1,))

    def test_extreme_errors_stay_whole_and_small_ones_get_a_detailed_view(self):
        chart_state = state()
        figure_values = [float(row.difference_text) for row in chart_state.rows()]
        self.assertEqual(figure_values, [-5.0, 2.94, 5.0])  # no detail view: all within the limit
        chart_state.assign(0, "9", allow_duplicate=True)  # +110 %: an extreme row beside small ones
        chart = rv.difference_chart(chart_state, 1, 500, 470, 1.0)
        self.assertEqual(len({span[0] for span in chart.spans}), 3)
        with mock.patch.object(rv, "_png", side_effect=lambda figure, dpi=None: figure):
            figure = rv.difference_chart(chart_state, 1, 500, 470, 1.0).png
        full, detail = figure.axes
        heights = sorted(round(p.get_height(), 6) for p in full.patches if p.get_fill())
        self.assertEqual(heights, sorted([110.0, 2.94, 5.0]))  # every signed value drawn whole, unchanged
        self.assertGreaterEqual(full.get_ylim()[1], 110.0)
        self.assertEqual(detail.get_ylim(), (-12.0, 12.0))
        self.assertIn("+110.0", [t.get_text() for t in detail.texts])  # the cut bar carries its true value
        self.assertIn("cut", detail.get_title(loc="left"))
        self.assertEqual(chart_state.row(0).difference_text, "+110.00")  # the stored percentage is untouched

    def test_frf_records_are_clickable_and_labels_stay_light(self):
        frequency = np.linspace(0.0, 300.0, 1201)
        indicator = 1.0 + np.cos(frequency / 9.0) ** 2
        coherence = np.full_like(frequency, 0.8)
        records = tuple((f"EXP {i + 1}", 20.0 + 13.0 * i) for i in range(20))
        chart = rv.frf_chart((frequency, indicator, coherence), records, 4, False, 900, 470, 1.0)
        self.assertEqual(png_size(chart.png), (900, 470))
        row, x0, x1, top, bottom = chart.spans[7]
        self.assertEqual(rv.rows_at(chart, (x0 + x1) / 2, (top + bottom) / 2), (7,))
        figure = rv.frf_figure((frequency, indicator, coherence), records, 4, False, 900, 470, 1.0)
        texts = [t.get_text() for t in figure.axes[0].texts]
        self.assertEqual(texts[-1], "EXP 5: 72.00 Hz")
        self.assertTrue(all(len(text) <= 2 for text in texts[:-1]))  # the others: their number only
        np.testing.assert_array_equal(figure.axes[1].lines[0].get_ydata(), coherence)  # coherence kept as read


class ShapeComponentTests(unittest.TestCase):
    def test_a_z_only_record_offers_z_and_says_x_and_y_were_not_measured(self):
        allowed = frozenset({"magnitude", "z"})
        self.assertEqual(sm.component_text(EXPERIMENTAL, "x", allowed), "X (not measured)")
        self.assertEqual(sm.component_text(EXPERIMENTAL, "z", allowed), "Z")
        self.assertEqual(sm.component_text(FE, "x", allowed), "U1")
        note = sm.measured_note(allowed)
        self.assertTrue(note.startswith("Measured: Z only. X and Y were not measured and cannot be chosen."), note)
        self.assertIn("Magnitude hides the sign; Z keeps it", note)
        self.assertEqual(sm.measured_note(frozenset({"x", "y", "z", "magnitude"})),
                         "Measured: X, Y, Z. Magnitude hides the sign; the measured components keep it.")


class _Flow(ux._Flow):
    def plots(self, window):
        review = window.review
        review.views.setCurrentIndex(review.views.indexOf(review.plots_area))
        self.app.processEvents()
        review._draw_plots()
        self.settle()
        return review

    def settle(self, seconds=0.4):
        import time
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.01)

    def click_png(self, image, x, y):
        pixmap = image.pixmap()
        ratio = pixmap.devicePixelRatio()
        width, height = pixmap.width() / ratio, pixmap.height() / ratio
        left, top = (image.width() - width) / 2, (image.height() - height) / 2
        QTest.mouseClick(image, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         QPoint(round(left + x / image.source.width() * width), round(top + y / image.source.height() * height)))
        self.app.processEvents()


class ReviewTableTests(_Flow):
    def test_the_visible_order_ends_with_the_fe_mode_choice_and_widths_follow_the_contents(self):
        window, panel = self.analysed()
        self.wait(panel)
        table = window.review.table
        header = table.horizontalHeader()
        visible = [header.logicalIndex(v) for v in range(header.count()) if not table.isColumnHidden(header.logicalIndex(v))]
        self.assertEqual([rv.HEADERS[c] for c in visible],
                         ["EXP mode", "EXP frequency (Hz)", "Selected FE frequency (Hz)", "Δf (%)", "Selected FE mode"])
        self.assertEqual(table.horizontalHeaderItem(1).text(), "EXP mode")  # the logical columns are unchanged
        for size in ((900, 680), (1366, 768)):
            window.resize(*size)
            self.app.processEvents()
            self.assertLessEqual(table.columnWidth(1), 90, size)  # EXP mode: short record numbers
            self.assertLess(table.columnWidth(1), table.columnWidth(2))
            self.assertGreater(table.columnWidth(3), table.columnWidth(1))  # the FE choice takes the rest
            self.assertEqual(table.horizontalScrollBar().maximum(), 0, size)
            self.assertEqual(window.stack.currentWidget().horizontalScrollBar().maximum(), 0, size)
        review = window.review
        review.columns_toggle.setChecked(True)
        self.assertEqual([header.logicalIndex(v) for v in range(header.count())], list(rp.VISUAL_ORDER))
        self.assertEqual(table.cellWidget(0, 7).text(), "Swap")  # swap, reset and every column stay

    def whole_rows_on_screen(self, window) -> int:
        """Rows of the frequency table that are drawn whole inside the window (not only present in the table)."""
        table = window.review.table
        seen = table.viewport().visibleRegion().boundingRect()  # what the pane, the page and the window leave of it
        return sum(1 for row in range(table.rowCount())
                   if seen.contains(table.visualRect(table.model().index(row, 1))) and not table.isRowHidden(row))

    def test_frequency_rows_are_on_screen_in_a_small_window_before_anything_is_dragged(self):
        """ABM-REAL-UX-1: a 1366 x 768 window at 150 % display scaling is 911 x 512 for the program; the notes of the
        table pane wrap there, and the table was left a strip with no row in it."""
        window, panel = self.analysed()
        self.wait(panel)
        review, table = window.review, window.review.table
        rows = min(table.rowCount(), rp.ROWS_IN_VIEW)
        self.assertGreaterEqual(rows, 3)
        for size in ((911, 512), (900, 680), (1366, 768)):
            window.resize(*size)
            self.settle(0.3)
            self.assertEqual(window.stack.currentWidget().verticalScrollBar().value(), 0, size)  # nothing was scrolled
            self.assertGreaterEqual(self.whole_rows_on_screen(window), rows, size)
            header = table.horizontalHeader()
            self.assertGreaterEqual(header.viewport().visibleRegion().boundingRect().height(), header.height(), size)  # titles whole
            self.assertEqual(table.horizontalScrollBar().maximum(), 0, size)
            self.assertEqual(window.stack.currentWidget().horizontalScrollBar().maximum(), 0, size)
        self.assertFalse(review.selection_label.visibleRegion().isEmpty())  # at 1366 x 768 the chosen row's shapes too
        self.assertTrue(review.selection_label.text().startswith("Shown: EXP "))
        table.selectRow(1)  # choosing a row still works and shows its shapes
        self.settle(0.3)
        self.assertEqual(review.current, 1)
        self.assertGreaterEqual(self.whole_rows_on_screen(window), rows)

    def test_a_duplicate_fe_selection_is_tinted_and_explained(self):
        window, panel = self.analysed()
        self.wait(panel)
        review = window.review
        self.assertFalse(review.colour_legend.isVisible())
        review._ask_duplicate = lambda _text: rp.KEEP
        taken = review.state.selected(1)
        self.assertTrue(review.select_mode(0, taken))
        self.wait(panel)
        self.assertTrue(review.colour_legend.isVisible())
        self.assertIn(rv.CONFLICT_TEXT, review.colour_legend.text())
        self.assertIn("not a frequency-error limit", review.colour_legend.text())
        self.assertIn(rv.MANUAL_TINT_TEXT, review.colour_legend.text())
        self.assertEqual(review.table.item(0, 4).background().color(), QColor("#fde8e8"))
        self.assertEqual(review.table.item(1, 4).background().color(), QColor("#fde8e8"))
        self.assertIn("Not one-to-one", review.duplicate_label.text())
        review.reset_all()
        self.assertFalse(review.colour_legend.isVisible())


class ReportExportTests(_Flow):
    """ABM-PLATE-EXPORT-1: the existing diagnostic report, exported from the Review page."""

    def exported(self, review, folder):
        self.assertTrue(review.export_report(str(folder)))
        self.assertFalse(review.export_button.isEnabled())  # one export at a time
        deadline = __import__("time").monotonic() + 120
        while review._exporting and __import__("time").monotonic() < deadline:
            self.settle(0.05)
        self.assertFalse(review._exporting)
        return review.export_feedback.text()

    def test_the_review_page_exports_the_diagnostic_report_as_pdf_and_excel(self):
        import openpyxl
        window, panel = self.analysed()
        self.wait(panel)
        review = window.review
        self.assertEqual(review.export_button.text(), "Export report...")
        self.assertTrue(review.export_button.isEnabled(), review.export_problem())
        kept = panel.analysis.diagnostic
        self.assertIsNotNone(kept)  # the frequency diagnostic of the analysis itself: nothing is run again to export
        folder = self.root / "report of the result"
        folder.mkdir()
        with mock.patch("new_gui.diagnostic_model.run_diagnostic", side_effect=AssertionError("diagnostic run again")), \
                mock.patch("abaqus_bridge.subprocess.Popen", side_effect=AssertionError("a process was started")):
            message = self.exported(review, folder)
        self.assertTrue(message.startswith("Report exported: "), message)
        self.assertIs(panel.analysis.diagnostic, kept)
        written = sorted(p.suffix for p in folder.iterdir())
        self.assertEqual(written, [".pdf", ".xlsx"])
        self.assertTrue(next(folder.glob("*.pdf")).read_bytes().startswith(b"%PDF"))
        book = openpyxl.load_workbook(next(folder.glob("*.xlsx")), read_only=True)
        cells = {name: [[str(c) if c is not None else "" for c in row] for row in book[name].iter_rows(values_only=True)]
                 for name in book.sheetnames}
        book.close()
        everything = "\n".join(" | ".join(row) for rows in cells.values() for row in rows)
        self.assertIn("REGISTRATION_REQUIRED. MAC NOT COMPUTED. NO VERIFIED MODAL PAIRS.", everything)
        self.assertIn("NOT_COMPUTED", everything)
        self.assertIn("NONE (physical mode pairing not established)", everything)
        self.assertNotIn("MAC 0.", everything)
        def numbers(header):  # the rows under the table whose first title is ``header``, as numbers where they are
            for rows in cells.values():
                titles = next((i for i, row in enumerate(rows) if row and row[0] == header), None)
                if titles is not None:
                    return [[float(c) if c.replace(".", "", 1).replace("-", "", 1).isdigit() else c for c in row]
                            for row in rows[titles + 1:] if row and row[0]]
            self.fail(f"no table {header!r}")

        records = numbers("Record")
        shown = panel.analysis.experimental_rows
        self.assertEqual(len(records), len(shown))  # every experimental record, the first one included
        self.assertEqual(records[0][0], 1.0)
        for row, record in zip(shown, records):
            self.assertAlmostEqual(record[1], float(row[2]), delta=6e-5, msg=row)
        nearest = numbers("Experimental record")
        self.assertEqual(len(nearest), len(panel.analysis.nearest_rows))
        for row, line in zip(panel.analysis.nearest_rows, nearest):  # FE candidate, its frequency, the signed difference
            self.assertEqual(int(line[2]), int(row[3]), row)
            self.assertAlmostEqual(line[3], float(row[4]), delta=6e-5, msg=row)
            self.assertAlmostEqual(line[4], float(row[5]), delta=6e-3, msg=row)
            self.assertEqual(line[-2:], ["NOT_COMPUTED", "NONE (not a mode pair)"])
        self.assertIn("RIGID-BODY (diagnostic record, not an elastic mode)", everything)
        self.assertTrue(review.export_button.isEnabled())

    def test_a_changed_file_refuses_the_export_and_writes_nothing(self):
        window, panel = self.analysed()
        self.wait(panel)
        folder = self.root / "refused"
        folder.mkdir()
        source = panel.inputs.full_experimental.source_path
        with open(source, "ab") as stream:
            stream.write(b"\n")
        message = self.exported(window.review, folder)
        self.assertTrue(message.startswith("Report not exported: "), message)
        self.assertIn("changed since it was read", message)
        self.assertEqual(list(folder.iterdir()), [])

    def test_a_saved_snapshot_is_not_exported_as_live_data(self):
        window, panel = self.analysed()
        self.wait(panel)
        review = window.review
        self.assertEqual(am.report_problem(panel.inputs, panel.analysis, True), am.REPORT_SNAPSHOT)
        self.assertEqual(am.report_problem(None, panel.analysis, False), am.REPORT_NOT_READY)
        with mock.patch.object(panel, "snapshot", object()):
            review._save_state()
            self.assertFalse(review.export_button.isEnabled())
            self.assertIn("Not available for a saved result", review.export_button.toolTip())
            self.assertFalse(review.export_report(str(self.root)))
        review._save_state()
        self.assertTrue(review.export_button.isEnabled())


class ChartSelectionTests(_Flow):
    def test_a_click_on_a_dot_selects_its_row_and_both_shapes_follow(self):
        window, panel = self.analysed()
        self.wait(panel)
        review = self.plots(window)
        image = review.frequency_image
        chart = review.charts["frequency"]
        self.assertEqual(png_size(chart.png), (image.source.width(), image.source.height()))
        self.assertEqual(image.source.width(), round(image.width() * image.devicePixelRatioF()))  # not stretched
        target = 2
        row, x, y = next(p for p in chart.points if p[0] == target)
        self.click_png(image, x, y)
        self.wait(panel)
        self.assertEqual(review.current, target)
        self.assertEqual(review.table.selectionModel().selectedRows()[0].row(), target)
        self.assertIs(review.views.currentWidget(), review.plots_area)  # the plots stay; the table follows
        shown = review.state.row(target)
        experimental, fe = panel.shape_panels[EXPERIMENTAL], panel.shape_panels[FE]
        records = panel.inputs.experimental.sets[panel.analysis.set_index].records
        self.assertEqual(str(records[experimental.chosen_index()].number), shown.exp_mode)
        self.assertEqual(str(panel.inputs.fe.modes[fe.chosen_index()].number), shown.selected_mode)
        self.assertIn(f"EXP {shown.exp_mode}", review.selection_label.text())
        self.assertEqual(rv.selected_point(review.state, review.current)[0].row, target)  # the chart rings the same row

    def test_a_click_on_a_bar_selects_its_row(self):
        window, panel = self.analysed()
        self.wait(panel)
        review = self.plots(window)
        chart = review.charts["difference"]
        row, x0, x1, top, bottom = next(span for span in chart.spans if span[0] == 1)
        self.click_png(review.difference_image, (x0 + x1) / 2, (top + bottom) / 2)
        self.wait(panel)
        self.assertEqual(review.current, 1)

    def test_overlapping_dots_ask_the_person_and_choose_nothing_alone(self):
        window, panel = self.analysed()
        self.wait(panel)
        review = self.plots(window)
        review.select_row(0)
        self.wait(panel)
        review.charts["frequency"] = rv.Chart(b"", points=((1, 50.0, 50.0), (3, 50.5, 50.0)))
        asked = []
        review._ask_row = lambda rows: (asked.append(rows), None)[1]
        self.assertIsNone(review._chart_clicked("frequency", 50.2, 50.0))
        self.assertEqual(asked, [(1, 3)])
        self.assertEqual(review.current, 0)  # nothing chosen without the person
        review._ask_row = lambda rows: rows[1]
        self.assertEqual(review._chart_clicked("frequency", 50.2, 50.0), 3)
        self.wait(panel)
        self.assertEqual(review.current, 3)
        self.assertIn("Row 4: EXP", review.row_text(3))

    def test_the_charts_follow_the_window_size(self):
        window, panel = self.analysed()
        self.wait(panel)
        for size in ((900, 680), (1366, 768)):
            window.resize(*size)
            self.settle()
            review = self.plots(window)
            image = review.frequency_image
            self.assertEqual(image.source.width(), round(image.width() * image.devicePixelRatioF()), size)
            self.assertEqual(window.stack.currentWidget().horizontalScrollBar().maximum(), 0, size)
            self.assertEqual(review._side_by_side, review.plots_area.viewport().width() >= rp.SIDE_BY_SIDE_WIDTH)


class ShapePanelTests(_Flow):
    def test_unmeasured_experimental_components_cannot_be_chosen_and_are_named(self):
        window, panel = self.analysed()
        self.wait(panel)
        experimental = panel.shape_panels[EXPERIMENTAL]
        allowed = sm.record_components(experimental.chosen_set(), experimental.chosen_index())
        model = experimental.component_combo.model()
        for row, component in enumerate(sm.COMPONENTS):
            item = model.item(row)
            self.assertEqual(item.isEnabled(), component in allowed, component)
            self.assertEqual("(not measured)" in item.text(), component in "xyz" and component not in allowed, component)
        self.assertTrue(experimental.component_note.isVisible())
        self.assertEqual(experimental.component_note.text(), sm.measured_note(allowed))
        fe = panel.shape_panels[FE]
        self.assertEqual(fe.component_note.text(), sm.FE_COMPONENT_NOTE)
        self.assertEqual([fe.component_combo.itemText(i) for i in range(5)], ["Normal", "Magnitude", "U1", "U2", "U3"])


class MacReadinessTests(_Flow):
    def test_without_a_registration_the_missing_prerequisite_is_named(self):
        window, panel = self.analysed()
        self.wait(panel)
        answers = window.mac_points.readiness_answers()
        self.assertEqual(list(answers), list(mp.READY_QUESTIONS))
        self.assertTrue(answers["Fitted EXP modes"].startswith("Yes"))
        self.assertTrue(answers["FE-to-EXP registration"].startswith("No"))
        self.assertIn("unknown until a registration exists", answers["Measured directions and points"])
        self.assertTrue(answers["MAC"].startswith("No: a registration is missing"))
        self.assertIn("Set up registration...", answers["MAC"])
        self.assertIsNone(panel.analysis.comparison)  # nothing was set up or computed
        self.assertFalse(window.mac_points.badge.isHidden())

    def test_a_confirmed_registration_is_not_called_proof(self):
        window, panel = self.analysed()
        self.confirmed(panel)
        self.compare(panel)
        answers = window.mac_points.readiness_answers()
        self.assertTrue(answers["MAC"].startswith("Yes: computed for"))
        self.assertIn("not independent proof", answers["FE-to-EXP registration"])

    def test_frf_peak_records_are_not_fitted_modes(self):
        stub = mock.Mock(comparison=None, registration_outcome=ux.am.PROVISIONAL, experimental_rows=(),
                         set_title="Peaks", experimental_total=3)
        answers = dict(mp.readiness_rows(stub, False, None, "none"))
        self.assertTrue(answers["Fitted EXP modes"].startswith("No: the chosen set holds FRF peak records"))
        self.assertTrue(answers["MAC"].startswith("No: MAC needs fitted mode shapes"))


class MaterialsTests(_Flow):
    def test_the_synthetic_source_and_the_meaning_of_its_numbers_are_stated(self):
        window = self.window()
        study = window.materials_workspace.study
        self.assertEqual(study.source_banner.text(), msm.EXAMPLE_BANNER[msm.RITZ])
        self.assertIn("does not identify your material", study.source_banner.text())
        self.assertIn("D11, D22: bending stiffness", study.parameter_help.text())
        self.assertIn("You do not need to calculate", study.parameter_help.text())
        study.method_combo.setCurrentIndex(study.method_combo.findData(msm.STAGE_A))
        self.assertEqual(study.source_banner.text(), msm.EXAMPLE_BANNER[msm.STAGE_A])
        self.assertIn("not on a plate size and mass", study.source_banner.text())
        self.assertIn("not your specimen", study.geometry_title.text())
        study.method_combo.setCurrentIndex(study.method_combo.findData(msm.RITZ))
        study.source_combo.setCurrentIndex(study.source_combo.findData(msm.REAL_SOURCE))
        self.assertEqual(study.source_banner.text(), msm.REAL_BANNER)
        self.assertFalse(study.real_next.isHidden())
        self.assertIn("Research Tuning", study.real_next.text())
        self.assertFalse(study.run_button.isEnabled())  # real data stays blocked
        self.assertIn(msm.RUN_BLOCKED, study.blocked.text())

    def test_the_status_codes_are_explained_and_kept_exactly(self):
        section = {"result": {"scientific_status": "DIAGNOSTIC_OPTIMIZER_CANDIDATE", "release_status": "NOT_A_RELEASE_VALUE"}}
        text = msm.status_meaning(section)
        self.assertIn("does not make them a verified material property", text)
        self.assertIn("DIAGNOSTIC_OPTIMIZER_CANDIDATE: numbers the optimizer found", text)
        self.assertIn("NOT_A_RELEASE_VALUE: must not be used as a material property", text)
        self.assertEqual(section["result"]["scientific_status"], "DIAGNOSTIC_OPTIMIZER_CANDIDATE")


class TuningTextTests(_Flow):
    def test_the_workflow_roles_forms_and_the_mirror_are_explained(self):
        window = self.window()
        tuning = window.research_tuning
        self.assertTrue(rtp.INTRO.startswith("The current exploratory workflow for real data"))
        self.assertIn("UNV / UFF: the measured, curve-fitted PolyMAX frequencies", tuning.roles_note.text())
        self.assertIn("does not automatically apply to a solid or sandwich FE model", tuning.roles_note.text())
        self.assertIn("E1, E2, G12: separate moduli", tuning.parameterization.toolTip())
        self.assertTrue(tuning.mirror_note.isHidden())
        self.assertIn("frequency agreement alone cannot tell", rtp.MIRROR_TEXT)
        self.assertEqual([tuning.parameterization.itemData(i) for i in range(2)], [rft.TIED, rft.FREE])


if __name__ == "__main__":
    unittest.main()
