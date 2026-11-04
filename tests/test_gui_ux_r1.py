"""GUI-UX-R1: the four pages, the candidate review, MAC / Points and Materials. Synthetic data; Qt ``offscreen``; no Abaqus."""

from __future__ import annotations

import json
from pathlib import Path
import threading
from unittest import mock
import unittest
import zipfile

import numpy as np

import test_universal_reg3_confirmed as reg3
import test_universal_two_file_analysis as base
import test_working_draft_r2_project as r2

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QGridLayout, QPushButton, QScrollArea, QWidget

from modal_core import ModalDataset, ModeShape
from new_gui import analyze_model as am
from new_gui import mac_points_model as mp
from new_gui import materials_workspace_model as mw
from new_gui import production_window as pw
from new_gui import review_model as rv
from new_gui import review_panel as rp
from new_gui import shape_model as sm
from new_gui.shape_panel import ImageView
from new_gui.workspace_state import EXPERIMENTAL, FE
from services import analysis_project as ap
from services import modal_data_viewer as viewer

WANTED_HEADERS = ("Row", "EXP mode", "EXP frequency (Hz)", "Selected FE mode", "Selected FE frequency (Hz)", "Δf (%)",
                  "Nearest FE mode (automatic)")


def cells(table) -> list:
    return [[table.item(r, c).text() for c in range(table.columnCount())] for r in range(table.rowCount())]


def wheel(widget, delta=-120) -> QWheelEvent:
    event = QWheelEvent(QPointF(5, 5), QPointF(widget.mapToGlobal(QPoint(5, 5))), QPoint(0, 0), QPoint(0, delta),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, event)
    return event


class _Stub:
    """The fields of an analysis the review state reads."""

    def __init__(self, nearest, fe, experimental=()):
        self.nearest_rows, self.fe_rows, self.experimental_rows = nearest, fe, experimental


FE_ROWS = (("1", "0.0010", "rigid-body"), ("7", "95.0000", "elastic"), ("8", "105.0000", "elastic"), ("9", "210.0000", "elastic"))
NEAREST = (("EXP1", "1", "100.0000", "7", "95.0000", "-5.00", "8", "105.0000", "+5.00", "—"),
           ("EXP2", "2", "102.0000", "8", "105.0000", "+2.94", "7", "95.0000", "-6.86", "—"),
           ("EXP3", "3", "200.0000", "9", "210.0000", "+5.00", "8", "105.0000", "-47.50", "—"))


class ReviewStateTests(unittest.TestCase):
    def state(self):
        return rv.ReviewState(_Stub(NEAREST, FE_ROWS))

    def test_the_columns_are_in_the_required_order(self):
        self.assertEqual(rv.HEADERS, WANTED_HEADERS)
        self.assertEqual(self.state().row(0).cells(), ("1", "1", "100.0000", "7", "95.0000", "-5.00", "7"))

    def test_the_automatic_cells_are_the_services_own(self):
        state = self.state()
        for source, row in zip(NEAREST, state.rows()):
            self.assertEqual((row.exp_mode, row.selected_mode, row.selected_text, row.difference_text, row.nearest_mode),
                             (source[1], source[3], source[4], source[5], source[3]))
            self.assertFalse(row.manual)

    def test_a_manual_choice_changes_only_the_selection_and_uses_the_convention(self):
        state = self.state()
        state.assign(0, "9", allow_duplicate=True)
        row = state.row(0)
        self.assertEqual((row.selected_mode, row.selected_text, row.difference_text), ("9", "210.0000", "+110.00"))
        self.assertEqual(row.nearest_mode, "7")  # the automatic suggestion stays
        self.assertEqual(row.exp_mode, "1")
        self.assertTrue(row.manual)
        self.assertEqual(row.origin, rv.USER_HYPOTHESIS)
        self.assertIn(rv.USER_HYPOTHESIS, state.hypothesis_text())

    def test_full_precision_frequencies_are_used_when_known(self):
        state = rv.ReviewState(_Stub(NEAREST, FE_ROWS), {"8": 105.5}, {"EXP1": 100.5})
        state.assign(0, "8", allow_duplicate=True)
        self.assertEqual(state.row(0).difference_text, f"{100.0 * (105.5 - 100.5) / 100.5:+.2f}")

    def test_swap_inspects_the_opposite_order_and_reset_restores_the_automatic_one(self):
        state = self.state()
        self.assertTrue(state.swap(0, 1))
        self.assertEqual((state.selected(0), state.selected(1)), ("8", "7"))
        self.assertEqual(state.row(0).difference_text, "+5.00")
        self.assertEqual(state.row(1).difference_text, "-6.86")
        self.assertEqual(state.duplicate_warning(), "")
        state.reset(0)
        self.assertFalse(state.row(0).manual)
        self.assertTrue(state.row(1).manual)
        state.reset()
        self.assertEqual(state.manual, {})
        self.assertEqual(state.rows(), self.state().rows())

    def test_the_same_fe_mode_twice_needs_a_decision_and_gives_a_warning(self):
        state = self.state()
        with self.assertRaises(rv.DuplicateSelection) as caught:
            state.assign(0, "8")
        self.assertEqual(caught.exception.rows, (1,))
        self.assertFalse(state.row(0).manual)
        state.assign(0, "8", allow_duplicate=True)
        self.assertIn("FE mode 8 is selected for rows 1, 2", state.duplicate_warning())

    def test_an_automatic_duplicate_is_also_stated(self):
        nearest = (NEAREST[0], ("EXP2", "2", "96.0000", "7", "95.0000", "-1.04", "8", "105.0000", "+9.38", "—"))
        self.assertIn("FE mode 7 is selected for rows 1, 2", rv.ReviewState(_Stub(nearest, FE_ROWS)).duplicate_warning())

    def test_a_rigid_body_mode_cannot_be_selected(self):
        state = self.state()
        self.assertEqual([number for number, _text in state.options], ["7", "8", "9"])
        with self.assertRaises(ValueError):
            state.assign(0, "1")

    def test_the_plots_draw_stored_frequencies(self):
        state = self.state()
        state.assign(0, "9", allow_duplicate=True)
        for image in (rv.frequency_plot(state, 0), rv.difference_plot(state, 0)):
            self.assertTrue(image.startswith(b"\x89PNG"))


class FrfTests(unittest.TestCase):
    def test_no_frf_data_gives_no_curve(self):
        dataset = ModalDataset("EXP", Path("x.unv"), [], metadata={"mode_source": "dataset 55"})
        self.assertIsNone(rv.frf_series(dataset))
        self.assertIsNone(rv.frf_series(None))
        self.assertIsNone(rv.frf_series(ModalDataset("EXP", Path("x.unv"), [], metadata={
            "_frf_frequency_hz": [1.0, 2.0], "_frf_indicator": [1.0]})))

    def test_read_frf_data_is_drawn_as_read(self):
        dataset = ModalDataset("EXP", Path("x.unv"), [], metadata={
            "_frf_frequency_hz": [1.0, 2.0, 3.0], "_frf_indicator": [0.5, 2.0, 0.1], "_frf_mean_coherence": [0.9, 0.95, 0.8]})
        frequency, indicator, coherence = rv.frf_series(dataset)
        self.assertEqual(frequency.tolist(), [1.0, 2.0, 3.0])
        self.assertEqual(indicator.tolist(), [0.5, 2.0, 0.1])
        self.assertTrue(rv.frf_plot((frequency, indicator, coherence), (2.0,), 2.0).startswith(b"\x89PNG"))
        self.assertTrue(rv.frf_plot((frequency, indicator, None)).startswith(b"\x89PNG"))


class DisplayGridTests(unittest.TestCase):
    """The artifact: a fixed 220-cell grid finer than the mesh left most cells empty, drawn as a dotted field."""

    @staticmethod
    def regular(count=101, pitch=3.0):
        x, y = np.meshgrid(np.arange(count) * pitch, np.arange(count) * pitch)
        return x.ravel(), y.ravel()

    def test_the_fixed_grid_reproduces_the_holes(self):
        x, y = self.regular()
        count, _, _ = np.histogram2d(x, y, bins=(viewer.DISPLAY_GRID_CELLS, viewer.DISPLAY_GRID_CELLS))
        self.assertGreater(viewer.display_hole_fraction(count), 0.5)

    def test_the_grid_follows_the_node_spacing(self):
        x, y = self.regular()
        cells = viewer.display_cells(x, y)
        self.assertLess(cells, 101)
        count, _, _ = np.histogram2d(x, y, bins=(cells, cells))
        self.assertEqual(viewer.display_hole_fraction(count), 0.0)

    def test_every_cell_value_is_a_mean_of_real_nodes_and_a_cut_out_stays_blank(self):
        x, y = self.regular()
        keep = ~((x > 100) & (x < 200) & (y > 100) & (y < 200))
        x, y = x[keep], y[keep]
        values = np.sin(x / 40.0) + y / 300.0
        cells = viewer.display_cells(x, y)
        image, _extent = viewer._binned(x, y, values, cells)
        self.assertTrue(np.isnan(image[cells // 2, cells // 2]))  # no value invented inside the cut-out
        finite = image[np.isfinite(image)]
        self.assertGreaterEqual(finite.min(), values.min())
        self.assertLessEqual(finite.max(), values.max())

    def test_a_large_regular_mode_is_drawn_and_states_the_grid(self):
        x, y = self.regular()
        points = np.column_stack([x, y, np.zeros_like(x)])
        vectors = np.zeros_like(points)
        vectors[:, 2] = np.sin(x / 40.0)
        with mock.patch("matplotlib.figure.Figure.savefig", autospec=True) as save:
            with mock.patch.object(viewer.Path, "mkdir"):
                viewer.render_mode(ModeShape(7, 58.1, np.arange(len(x)), points, vectors), viewer.FE, "normal", Path("x.png"), "t")
        figure = save.call_args.args[0]
        self.assertIn("mean per display cell", figure.axes[0].get_xlabel())
        self.assertIn("empty cells blank", figure.axes[0].get_xlabel())
        self.assertNotIn("through the depth", figure.axes[0].get_xlabel())


class ImageViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def picture(self):
        return rv.frequency_plot(rv.ReviewState(_Stub(NEAREST, FE_ROWS)))

    def test_a_scroll_bars_width_does_not_change_the_height(self):
        view = ImageView()
        self.addCleanup(view.close)
        view.resize(400, 10)
        view.show()
        self.app.processEvents()
        view.set_image(self.picture())
        height = view.height()
        view.resize(400 - 17, height)
        self.app.processEvents()
        self.assertEqual(view.height(), height)
        view.resize(700, height)
        self.app.processEvents()
        self.assertGreater(view.height(), height)

    def test_pictures_in_a_scroll_area_settle_at_every_height(self):
        # the loop: the picture's height shows the scroll bar, the bar narrows the picture, the lower picture hides the bar
        area = QScrollArea()
        area.setWidgetResizable(True)
        content = QWidget()
        grid = QGridLayout(content)
        views = (ImageView(), ImageView())
        for column, view in enumerate(views):
            grid.addWidget(view, 0, column)
        area.setWidget(content)
        area.resize(900, 400)
        area.show()
        self.addCleanup(area.close)
        self.app.processEvents()
        for view in views:
            view.set_image(self.picture())
        for height in range(150, 420, 3):
            area.resize(900, height)
            self.app.processEvents()
        self.assertTrue(all(view.source is not None for view in views))


class _Flow(r2._Project):
    def setUp(self):
        super().setUp()
        self.addCleanup(self.app.processEvents)


class NavigationTests(_Flow):
    def test_four_pages_and_review_after_an_analysis(self):
        window = self.window()
        self.assertEqual([b.text() for b in window.sidebar.findChildren(QPushButton)],
                         ["Analyze", "Review", "MAC / Points", "Materials"])
        self.assertEqual(window.stack.currentIndex(), pw.ANALYZE_PAGE)
        _window, panel = self.analysed()
        self.assertEqual(_window.stack.currentIndex(), pw.REVIEW_PAGE)
        self.assertEqual(_window.nav.checkedId(), pw.REVIEW_PAGE)
        self.assertIs(panel.result_box.window(), _window)

    def test_the_analyze_page_holds_only_the_inputs(self):
        window, panel = self.analysed()
        page = window.stack.widget(pw.ANALYZE_PAGE).widget()
        for widget in (panel.fields[FE], panel.fields[EXPERIMENTAL], panel.analyze_button, panel.open_project_button,
                       panel.save_project_button, panel.save_as_button):
            self.assertTrue(page.isAncestorOf(widget))
        for widget in (panel.result_box, panel.shapes, panel.tables_box, panel.comparison_box):
            self.assertFalse(page.isAncestorOf(widget))
        self.assertIn("FE modes 1-20", " ".join(l.text() for l in panel.findChildren(type(panel.message))))

    def test_a_comparison_started_on_mac_points_stays_there(self):
        window, panel = self.analysed()
        self.confirmed(panel)
        window.show_page(pw.MAC_PAGE)
        self.compare(panel)
        self.assertEqual(window.stack.currentIndex(), pw.MAC_PAGE)

    def test_a_failure_returns_to_analyze_with_its_message(self):
        window, panel = self.analysed()
        panel._block("something failed")
        self.assertEqual(window.stack.currentIndex(), pw.ANALYZE_PAGE)
        self.assertEqual(window.statusBar().currentMessage(), "something failed")

    def test_no_page_scrolls_sideways_at_the_usual_sizes(self):
        window, _panel = self.analysed()
        for size in ((900, 680), (1366, 768)):
            window.resize(*size)
            for page in range(window.stack.count()):
                window.show_page(page)
                self.app.processEvents()
                area = window.stack.currentWidget()
                self.assertIsInstance(area, QScrollArea)
                self.assertEqual(area.horizontalScrollBar().maximum(), 0, (size, page))

    def test_save_from_the_menu_stays_on_the_page(self):
        window, panel = self.analysed()
        panel.save_project_as(str(self.project))
        self.wait(panel)
        window.project_actions["save"].trigger()
        self.wait(panel)
        self.assertEqual(window.stack.currentIndex(), pw.REVIEW_PAGE)
        self.assertIn("Project saved", window.statusBar().currentMessage())


class ReviewPageTests(_Flow):
    def test_the_table_has_the_required_columns_and_every_record(self):
        window, panel = self.analysed()
        table = window.review.table
        self.assertEqual(tuple(table.horizontalHeaderItem(c).text() for c in range(table.columnCount())), WANTED_HEADERS)
        self.assertEqual(table.rowCount(), len(panel.analysis.nearest_rows))
        self.assertEqual(table.item(0, 1).text(), panel.analysis.nearest_rows[0][1])  # EXP mode 1 is kept
        self.assertEqual(table.item(0, 6).text(), panel.analysis.nearest_rows[0][3])
        self.assertEqual(window.review.combos[0].currentData(), panel.analysis.nearest_rows[0][3])

    def test_selecting_a_row_shows_its_shapes(self):
        window, panel = self.analysed()
        self.wait(panel)
        window.review.select_row(2)
        self.wait(panel)
        row = panel.analysis.nearest_rows[2]
        fe = panel.shape_panels[FE]
        self.assertEqual(fe.preview.modes[fe.chosen_index()].number, int(row[3]))
        self.assertEqual(panel.shape_panels[EXPERIMENTAL].chosen_index(), 2)
        self.assertEqual(fe.slot.state, sm.SHOWN)
        self.assertIn(f"FE {row[3]}", window.review.selection_label.text())
        self.assertIn("not a validated pair", window.review.selection_label.text())

    def test_a_manual_choice_follows_into_the_table_shapes_and_marks(self):
        window, panel = self.analysed()
        self.wait(panel)
        review = window.review
        other = next(n for n, _t in review.state.options if n not in {review.state.selected(i) for i in range(len(review.state))})
        self.assertTrue(review.select_mode(1, other))
        self.wait(panel)
        row = review.state.row(1)
        self.assertEqual(review.table.item(1, 4).text(), row.selected_text)
        self.assertEqual(review.table.item(1, 5).text(), row.difference_text)
        self.assertEqual(review.table.item(1, 6).text(), panel.analysis.nearest_rows[1][3])
        self.assertIn(rv.USER_HYPOTHESIS, review.hypothesis_label.text())
        self.assertFalse(review.session_label.isHidden())
        fe = panel.shape_panels[FE]
        self.assertEqual(str(fe.preview.modes[fe.chosen_index()].number), other)
        review.reset_all()
        self.wait(panel)
        self.assertEqual(review.state.manual, {})
        self.assertTrue(review.hypothesis_label.isHidden())
        self.assertEqual(review.table.item(1, 3).text(), panel.analysis.nearest_rows[1][3])

    def test_a_duplicate_asks_and_cancel_keeps_the_selection(self):
        window, panel = self.analysed()
        self.wait(panel)
        review = window.review
        taken = review.state.selected(0)
        before = review.state.selected(1)
        review._ask_duplicate = lambda _text: rp.CANCEL
        self.assertFalse(review.select_mode(1, taken))
        self.assertEqual(review.state.selected(1), before)
        self.assertEqual(review.combos[1].currentData(), before)
        review._ask_duplicate = lambda _text: rp.KEEP
        self.assertTrue(review.select_mode(1, taken))
        self.wait(panel)
        self.assertIn("not one-to-one", review.duplicate_label.text())
        review.reset_all()
        self.wait(panel)
        review._ask_duplicate = lambda _text: rp.SWAP
        self.assertTrue(review.select_mode(1, taken))
        self.wait(panel)
        self.assertEqual((review.state.selected(0), review.state.selected(1)), (before, taken))
        self.assertTrue(review.duplicate_label.isHidden())

    def test_a_manual_choice_changes_no_result_no_saved_file_and_no_pair(self):
        window, panel = self.analysed()
        self.confirmed(panel)
        window.show_page(pw.REVIEW_PAGE)
        analysis = self.compare(panel)
        self.wait(panel)
        pairs, mac = analysis.comparison.pair_rows, analysis.comparison.mac_values
        before = r2.displayed(panel)
        self.saved(panel)
        with zipfile.ZipFile(self.project) as archive:
            clean = json.loads(archive.read(ap.PROJECT))
        window.review.swap_with_next(0)
        self.wait(panel)
        self.assertTrue(window.review.state.manual)
        self.assertIs(panel.analysis, analysis)
        self.assertEqual(analysis.comparison.pair_rows, pairs)
        self.assertEqual(analysis.comparison.mac_values, mac)
        self.assertEqual(r2.displayed(panel), before)
        self.assertEqual(panel.status_label.text(), am.CONFIRMED_COMPARISON)
        second = self.root / "with manual.mcproj"
        self.saved(panel, second)
        with zipfile.ZipFile(second) as archive:
            names = set(archive.namelist())
            again = json.loads(archive.read(ap.PROJECT))
        for key in ("saved_at", "written_at"):
            clean.pop(key), again.pop(key)
        self.assertEqual(again, clean)
        self.assertFalse(any(rv.USER_HYPOTHESIS in name for name in names))
        self.assertNotIn(rv.USER_HYPOTHESIS, json.dumps(again))

    def test_a_new_result_starts_again_from_the_automatic_selection(self):
        window, panel = self.analysed()
        self.wait(panel)
        window.review.swap_with_next(0)
        self.wait(panel)
        self.run_analysis(panel)
        self.assertEqual(window.review.state.manual, {})

    def test_the_wheel_over_a_closed_choice_changes_nothing_and_goes_on(self):
        window, panel = self.analysed()
        self.wait(panel)
        combo = window.review.combos[0]
        chosen = combo.currentIndex()
        event = wheel(combo)
        self.assertEqual(combo.currentIndex(), chosen)
        self.assertEqual(window.review.state.manual, {})
        self.assertFalse(event.isAccepted())
        shape = panel.shape_panels[FE].item_combo
        chosen = shape.currentIndex()
        wheel(shape)
        self.assertEqual(shape.currentIndex(), chosen)
        self.assertEqual(panel.shape_panels[FE].slot.state, sm.SHOWN)

    def test_the_views_are_read_only_and_the_frf_tab_never_makes_a_curve(self):
        window, panel = self.analysed()
        self.wait(panel)
        review = window.review
        review.views.setCurrentIndex(1)
        self.app.processEvents()
        self.assertIsNotNone(review.frequency_image.source)
        self.assertIsNotNone(review.difference_image.source)
        review.views.setCurrentIndex(2)
        self.app.processEvents()
        self.assertIsNone(review.frf_image.source)
        self.assertEqual(review.frf_note.text(), rv.FRF_NOT_IN_FILE)

    def test_frf_curves_are_shown_when_the_importer_read_them(self):
        window, panel = self.analysed()
        self.wait(panel)
        panel.chosen_dataset().metadata.update({"_frf_frequency_hz": [10.0, 20.0, 30.0], "_frf_indicator": [1.0, 3.0, 2.0]})
        window.review.views.setCurrentIndex(2)
        self.app.processEvents()
        self.assertIsNotNone(window.review.frf_image.source)
        self.assertEqual(window.review.frf_note.text(), "")

    def test_frf_peak_records_get_a_short_label_one_explanation_and_full_details(self):
        window, panel = self.analysed()
        rows = tuple(row[:3] + (sm.PROVISIONAL_TEXT,) for row in panel.analysis.experimental_rows)
        from dataclasses import replace

        panel.analysis = replace(panel.analysis, experimental_rows=rows)
        panel._show_result()
        table = panel.tables["experimental"]
        self.assertEqual(table.item(0, 3).text(), sm.FRF_PEAK_SHORT)
        self.assertEqual(table.item(0, 3).toolTip(), sm.PROVISIONAL_TEXT)
        self.assertFalse(window.review.provisional_note.isHidden())
        self.assertTrue(window.review.state.provisional)
        self.assertEqual(panel.analysis.experimental_rows[0][3], sm.PROVISIONAL_TEXT)  # the data keep the full wording


class SavedResultTests(_Flow):
    def test_opening_shows_review_with_no_computation_and_says_what_needs_the_sources(self):
        _window, panel = self.analysed()
        self.wait(panel)
        self.saved(panel)
        with mock.patch("services.odb_import_service.hash_file", side_effect=AssertionError("no hash")):
            window, again = self.reopened()
        self.assertEqual(window.stack.currentIndex(), pw.REVIEW_PAGE)
        review = window.review
        self.assertEqual(cells(review.table)[0][1], again.analysis.nearest_rows[0][1])
        self.assertFalse(review.saved_note.isHidden())
        self.assertIsNotNone(again.saved_shapes[FE].image.source)
        review.views.setCurrentIndex(1)
        self.assertIsNotNone(review.frequency_image.source)
        review.views.setCurrentIndex(2)
        self.assertIsNone(review.frf_image.source)
        self.assertEqual(review.frf_note.text(), rv.FRF_NEEDS_SOURCE)
        self.assertIsNotNone(again.check_button)
        self.assertTrue(window.stack.widget(pw.ANALYZE_PAGE).widget().isAncestorOf(again.check_button))

    def test_a_row_and_a_manual_choice_use_the_saved_pictures_and_full_frequencies(self):
        _window, panel = self.analysed()
        self.wait(panel)
        self.saved(panel)
        window, again = self.reopened()
        review = window.review
        document = again.snapshot.document
        review.show_row(1)
        self.assertEqual(again.saved_shapes[FE].shown_number, again.analysis.nearest_rows[1][3])
        other = next(n for n, _t in review.state.options if n not in {review.state.selected(i) for i in range(len(review.state))})
        self.assertTrue(review.select_mode(1, other))
        self.assertEqual(again.saved_shapes[FE].shown_number, other)
        fe = next(m["frequency_hz"] for m in document["modes"]["fe"] if str(m["number"]) == other)
        experimental = next(m["frequency_hz"] for m in document["modes"]["experimental"] if m["record"] == "EXP2")
        self.assertEqual(review.state.row(1).difference_text, f"{100.0 * (fe - experimental) / experimental:+.2f}")

    def test_the_marked_row_is_the_row_of_the_pair_on_show(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        self.compare(panel)
        self.wait(panel)
        self.saved(panel)
        window, again = self.reopened()
        pair = again.analysis.comparison.pair_rows[0].cells
        current = window.review.current
        self.assertEqual(window.review.state.row(current).exp_mode, pair[3])
        self.assertEqual([i.row() for i in window.review.table.selectionModel().selectedRows()], [current])
        self.assertIn(f"EXP {pair[3]} and FE {pair[0]}", window.review.selection_label.text())

    def test_old_project_files_still_open_and_the_format_is_unchanged(self):
        self.assertEqual(ap.SCHEMA, "universal/analysis-project/v1")

    def test_mac_points_of_a_saved_comparison_shows_what_is_stored(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        self.compare(panel)
        self.wait(panel)
        self.saved(panel)
        window, again = self.reopened()
        mac = window.mac_points
        self.assertEqual(again.tables["pairs"].rowCount(), reg3.RECORDS)
        self.assertTrue(mac.badge.isHidden())
        self.assertIsNone(mac.point_table)
        self.assertEqual(mac.coverage_table.rowCount(), reg3.RECORDS)
        self.assertEqual(mac.pair_status.text(), mp.NEEDS_SOURCE)
        self.assertFalse(mac.show_pair_images(0))


class MacPointsTests(_Flow):
    def test_without_a_registration_the_reason_is_shown_and_nothing_is_made_up(self):
        window, panel = self.analysed()
        mac = window.mac_points
        self.assertFalse(mac.badge.isHidden())
        self.assertEqual(mac.reason.text(), mp.REASONS[am.REFUSED])
        self.assertIsNone(panel.comparison_tabs)
        self.assertNotIn("mac", panel.tables)
        self.assertIsNone(mac.point_table)
        self.assertTrue(window.stack.widget(pw.MAC_PAGE).widget().isAncestorOf(panel.registration_button))

    def test_the_provisional_reason_and_every_outcome_have_their_own_text(self):
        for outcome in (am.PROVISIONAL, am.REFUSED, am.FAILED, am.NOT_CONFIRMED):
            stub = mock.Mock(comparison=None, registration_outcome=outcome)
            self.assertEqual(mp.unavailable_reason(stub, False), mp.REASONS[outcome])
        self.assertIn("FRF peak", mp.REASONS[am.PROVISIONAL])

    def test_the_evidence_levels_stay_separate(self):
        window, panel = self.analysed()
        self.wait(panel)
        table = window.mac_points.evidence_table
        rows = cells(table)
        self.assertEqual([row[0] for row in rows],
                         ["Frequency-based candidate selection", "MAC-based modal identity diagnostics",
                          "User-confirmed registration", "Physically validated archived evidence"])
        self.assertEqual(rows[1][1], "Not available")
        self.assertEqual(rows[2][1], "None applied")
        self.assertEqual(rows[3][1], "None applied")
        window.review.swap_with_next(0)
        self.wait(panel)
        window.show_page(pw.MAC_PAGE)
        rows = cells(window.mac_points.evidence_table)
        self.assertIn(rv.USER_HYPOTHESIS, rows[0][1])
        self.assertEqual(rows[1][1], "Not available")  # a manual choice opens no gate
        self.assertEqual(rows[2][1], "None applied")
        self.assertIsNone(panel.analysis.comparison)

    def compared(self):
        window, panel = self.analysed()
        self.confirmed(panel)
        self.compare(panel)
        self.wait(panel)
        self.assertEqual(panel.analysis.status, am.CONFIRMED_COMPARISON)
        return window, panel

    def test_a_comparison_shows_pairs_mac_points_and_coverage(self):
        window, panel = self.compared()
        mac = window.mac_points
        self.assertEqual([panel.comparison_tabs.tabText(i) for i in range(panel.comparison_tabs.count())],
                         ["Mode pairs", "MAC", "Points", "Mapping diagnostics", "Line profile"])
        result = panel.analysis.comparison_result
        self.assertEqual(mac.point_table.rowCount(), len(result.experimental.modes[0].node_ids))
        self.assertEqual(mac.coverage_table.rowCount(), reg3.RECORDS)
        rows = cells(mac.point_table)
        mapped = np.asarray(result.abaqus.modes[0].node_ids)[np.asarray(result.geometry.experimental_to_abaqus)]
        self.assertEqual([row[4] for row in rows], [str(node) for node in mapped])
        self.assertEqual(rows[0][0], str(result.experimental.modes[0].node_ids[0]))
        self.assertNotIn("MAC", " ".join(mp.POINT_HEADERS))  # no value per point
        evidence = cells(mac.evidence_table)
        self.assertEqual(evidence[2][1], "Applied to this result")
        self.assertEqual(evidence[3][1], "None applied")

    def test_the_comparator_result_is_never_saved(self):
        _window, panel = self.compared()
        self.saved(panel)
        with zipfile.ZipFile(self.project) as archive:
            self.assertNotIn("comparison_result", json.dumps(json.loads(archive.read(ap.PROJECT))))

    def test_clicking_a_pair_draws_its_pictures(self):
        window, panel = self.compared()
        mac = window.mac_points
        panel._pair_clicked(1)
        self.assertTrue(window.wait_for_reads())
        self.assertTrue(all(image.source is not None for image in mac.pair_images))

    def test_a_profile_is_drawn_only_for_a_measured_component(self):
        window, panel = self.compared()
        mac = window.mac_points
        self.assertTrue(mac.lines)
        self.assertTrue(all(len(line.indices) >= 3 for line in mac.lines))
        mac.axis_combo.setCurrentIndex(2)  # the fixture measures Z
        self.assertIsNotNone(mac.profile_image.source)
        pair = panel.analysis.comparison_result.pairs[0]
        points = np.asarray(pair.coordinates)
        for line in mac.lines:
            others = [a for a in range(3) if a != line.axis]
            spread = np.ptp(points[list(line.indices)][:, others], axis=0)
            self.assertTrue((spread < 1e-2).all())
        masked = mock.Mock(wraps=pair)
        masked.measured_dof_mask = np.zeros_like(np.asarray(pair.abaqus_vector), dtype=bool)
        masked.abaqus_vector, masked.experimental_vector = pair.abaqus_vector, pair.experimental_vector
        self.assertIsNone(mp.profile_plot(masked, mac.lines[0], 0))


class MaterialsTests(_Flow):
    def test_the_page_states_what_is_missing_and_issues_no_value(self):
        window = self.window()
        workspace = window.materials_workspace
        rows = cells(workspace.property_table)
        self.assertEqual([row[0] for row in rows], list(mw.INPUT_PROPERTIES))
        for row in rows:
            self.assertEqual(row[1:], [mw.NOT_STORED, mw.NOT_PROVIDED, mw.NOT_ISSUED])
        self.assertIn("INP or CAE", workspace.material_statement.text())
        text = " ".join(mw.WORKFLOW)
        self.assertIn("explicitly authorized", text)
        self.assertIn("scientific refusal", text)
        self.assertEqual(window.materials.table.item(0, 1).text(), "Not identified")

    def test_its_files_are_its_own_and_start_nothing(self):
        window = self.window()
        workspace = window.materials_workspace
        self.assertTrue(workspace.choose_file(FE, str(self.odb)))
        self.assertTrue(workspace.choose_file(EXPERIMENTAL, str(self.unv(base.plate_nodes()))))
        self.assertTrue(window.wait_for_reads())
        self.assertEqual(window.analyze.paths, {FE: None, EXPERIMENTAL: None})
        self.assertIsNone(window.analyze.analysis)
        self.assertIn(mw.NO_PACKAGE, workspace.fact_notes[FE].text())
        self.assertEqual(workspace.fact_tables[EXPERIMENTAL].item(0, 1).text(), "exp data.unv")
        self.assertEqual(self.consents, [])

    def test_a_wrong_file_is_refused(self):
        workspace = self.window().materials_workspace
        self.assertFalse(workspace.choose_file(FE, str(self.root / "x.unv")))
        self.assertFalse(workspace.message.isHidden())

    def test_a_package_of_this_odb_gives_the_geometry_without_the_mode_files(self):
        window, panel = self.analysed()
        self.wait(panel)
        manifest = Path(panel.inputs.full_fe.manifest_path)
        self.assertEqual(dict(mw.read_fe_facts(self.odb, threading.Event()).rows)["Nodes"], str(len(self.nodes())))
        for mode_file in manifest.parent.glob("mode_*.csv"):
            mode_file.rename(mode_file.with_suffix(".hidden"))  # the geometry facts do not need them
        table = dict(mw.geometry_facts(manifest))
        self.assertEqual(table["Nodes"], str(len(self.nodes())))
        self.assertIn("X extent", table)
        self.assertEqual(table["Units"], "Not stated by the extracted data")
        self.assertNotIn("E1", table)

    def test_reusing_the_files_of_analyze(self):
        window, panel = self.analysed()
        self.wait(panel)
        workspace = window.materials_workspace
        self.assertTrue(workspace.use_analyze_files())
        self.assertTrue(window.wait_for_reads())
        self.assertEqual(workspace.paths, panel.paths)
        self.assertIsNotNone(workspace.facts[FE])
        self.assertIsNotNone(workspace.facts[EXPERIMENTAL])

    def test_reusing_a_saved_result_looks_at_no_path(self):
        _window, panel = self.analysed()
        self.wait(panel)
        self.saved(panel)
        window, again = self.reopened()
        with mock.patch("pathlib.Path.is_file", side_effect=AssertionError("no path is looked at")), \
                mock.patch("services.odb_import_service.hash_file", side_effect=AssertionError("no hash")):
            self.assertTrue(window.materials_workspace.use_analyze_files())
        self.assertFalse(window.materials_workspace.busy())
        self.assertIn("not looked at", window.materials_workspace.fact_notes[FE].text())

    def test_nothing_to_reuse_is_said(self):
        workspace = self.window().materials_workspace
        self.assertFalse(workspace.use_analyze_files())
        self.assertFalse(workspace.message.isHidden())


class SourceGuards(unittest.TestCase):
    def test_the_new_pages_install_nothing_and_run_no_solver(self):
        root = Path(__file__).resolve().parents[1] / "src" / "new_gui"
        for name in ("review_model.py", "review_panel.py", "mac_points_model.py", "mac_points_panel.py",
                     "materials_workspace_model.py", "materials_workspace.py"):
            text = (root / name).read_text(encoding="utf-8")
            for forbidden in ("install_", "subprocess", "run_extraction", "compare_modal_datasets", "modal_assurance_criterion"):
                self.assertNotIn(forbidden, text, name)


if __name__ == "__main__":
    unittest.main()
