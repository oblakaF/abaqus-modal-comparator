"""UNIVERSAL-UI-2: the program's window shows Analyze and Materials only, with no specimen or research text."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import test_universal_two_file_analysis as base

from PySide6.QtWidgets import (QAbstractButton, QApplication, QBoxLayout, QComboBox, QLabel, QPushButton, QScrollArea,
                               QTableWidget, QTabWidget, QWidget)

from new_gui import __main__ as entry
from new_gui import analyze_model as am
from new_gui import comparison_model as cm
from new_gui import materials_status_panel as msp
from new_gui import production_window as pw
from new_gui import registration_check_model as rm
from new_gui import window as window_module
from new_gui.analyze_panel import DONE, HIDE_DETAILS, IDLE, RUNNING, SHOW_DETAILS
from new_gui.workspace_state import EXPERIMENTAL, FE

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = re.compile(r"SP-?\d|\bM\d+\b|PLATE|[Pp]late|[Ss]pecimen|NEW-GUI|\bRC\d|PRIORITY|Auto-ID|[Rr]esearch|[Aa]rchiv|"
                       r"Workspace|[Ff]ixture|(?<!Open )(?<!Save )(?<!Close )\b[Pp]roject\b|[Ss]tage\b|D-0\d\d|PolyMAX")  # the commands stay
REUSED = ("Physical registration reused by FE geometry identity (X): SP-13 fixture-sp13, registration abc (frozen "
          "mapping). archived sensitivities apply only if 11. Scaling verifies this ODB.")
SIZES = ((900, 680), (1366, 768))
ALLOWED = re.compile(r"Physically validated archived evidence|Single-plate model calibration|Load the specimen FE model"  # GUI-UX-R1
                     r"|Research Tuning|" + re.escape(pw.TUNING_SUBTITLE))  # REAL-FIT.R1: the owner-specified research page


def shown_text(window) -> list:
    """All the text the window can show, collapsed details and tooltips included; a file's path is the user's own."""
    texts = [window.windowTitle()]
    for action in window.menuBar().actions():
        texts.append(action.text())
        if action.menu() is not None:
            texts += [item.text() for item in action.menu().actions()]
    study = window.materials_workspace.study  # MAT-3: its owner-specified section names the methods and their scope
    tuning = window.research_tuning  # REAL-FIT.R1: the owner-specified research page states what it is
    for widget in window.findChildren(QWidget):
        if widget is study or study.isAncestorOf(widget) or widget is tuning or tuning.isAncestorOf(widget):
            continue
        texts.append(widget.toolTip())
        if isinstance(widget, (QLabel, QAbstractButton)):
            texts.append(widget.text())
        elif isinstance(widget, QComboBox):
            texts += [widget.itemText(i) for i in range(widget.count())]
        elif isinstance(widget, QTabWidget):
            texts += [widget.tabText(i) for i in range(widget.count())]
        elif isinstance(widget, QTableWidget):
            texts += [widget.horizontalHeaderItem(c).text() for c in range(widget.columnCount())]
            texts += [widget.item(r, c).text() for r in range(widget.rowCount()) for c in range(widget.columnCount())
                      if widget.item(r, c) is not None]
    return texts


class _WindowCase(base._Case):
    def window(self, size=(1180, 800)):
        window = pw.ProductionWindow(analyze_options={"runner": base.Runner(base.plate_nodes()), "discover": base.FOUND,
                                                      "consent": self.consent})
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        window.resize(*size)
        window.show()
        self.app.processEvents()
        return window

    def analysed(self, window):
        window.analyze.choose_file(FE, str(self.odb))
        window.analyze.choose_file(EXPERIMENTAL, str(self.unv(base.plate_nodes())))
        self.run_analysis(window.analyze)
        self.assertEqual(window.analyze.state, DONE, window.analyze.message.text())
        return window.analyze

    def assert_clean(self, window):
        texts = [ALLOWED.sub("", text) for text in shown_text(window)]
        found = [(text, FORBIDDEN.search(text).group()) for text in texts if FORBIDDEN.search(text)]
        self.assertEqual(found, [])


class NavigationTests(_WindowCase):
    def test_public_navigation_is_the_four_workflow_pages_only(self):
        window = self.window()
        self.assertEqual([b.text() for b in window.sidebar.findChildren(QPushButton)],
                         ["Analyze", "Review", "MAC / Points", "Materials", "Research Tuning"])  # REAL-FIT.R1
        self.assertEqual(window.stack.count(), 5)
        self.assertEqual(window.stack.currentIndex(), pw.ANALYZE_PAGE)

    def test_the_menus_hold_no_earlier_page_or_shortcut(self):
        window = self.window()
        self.assertEqual([a.text() for a in window.menuBar().actions()], ["&File", "&Help"])
        self.assertEqual([a.text() for a in window.menuBar().actions()[0].menu().actions() if a.text()],
                         ["Open Project...", "Save Project", "Save Project As...", "Close Project",
                          "Choose FE file...", "Choose experimental file...", "Exit"])

    def test_the_window_is_clean_before_and_after_an_analysis(self):
        for size in SIZES:
            with self.subTest(size=size):
                window = self.window(size)
                self.assert_clean(window)
                self.analysed(window)
                window.analyze.details.toggle.setChecked(True)
                self.assert_clean(window)
                window.show_page(pw.MATERIALS_PAGE)
                self.assert_clean(window)

    def test_earlier_pages_stay_available_only_with_the_explicit_option(self):
        with mock.patch.object(QApplication, "exec", return_value=0), \
                mock.patch.object(pw, "ProductionWindow") as program, \
                mock.patch.object(window_module, "MainWindow") as earlier:
            self.assertEqual(entry.main(["app"]), 0)
            program.assert_called_once_with()
            earlier.assert_not_called()
            self.assertEqual(entry.main(["app", entry.RESEARCH_OPTION]), 0)
            earlier.assert_called_once()
            program.assert_called_once_with()

    def test_the_earlier_window_keeps_its_pages(self):
        window = window_module.MainWindow(analyze_options={"discover": base.FOUND})
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        names = {b.text() for b in window.sidebar.findChildren(QPushButton) if b.isCheckable()}
        self.assertEqual(names, set(window_module.PAGES))
        self.assertEqual(window.archive_button.text(), window_module.OPEN_ARCHIVE)


class SeparationTests(unittest.TestCase):
    def test_no_earlier_page_module_is_loaded_by_the_program_window(self):
        code = ("import sys; sys.path.insert(0, 'src'); import new_gui.production_window; "
                "print(sorted(m for m in sys.modules if m.startswith('new_gui.')))")
        output = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True,
                                env={**base.os.environ, "QT_QPA_PLATFORM": "offscreen"}, timeout=120).stdout
        for name in ("window", "archive_dialog", "known_sources", "known_sources_dialog", "materials_model",
                     "materials_panel", "plate_study_panel", "plate_study_model", "generic_plate_panel",
                     "physical_review_panel", "fe_response_panel", "research_results_panel", "research_results_model"):
            self.assertNotIn(f"'new_gui.{name}'", output)


class LayoutTests(_WindowCase):
    def test_both_sizes_fit_without_a_horizontal_scroll_and_keep_the_shapes_side_by_side(self):
        for size in SIZES:
            with self.subTest(size=size):
                window = self.window(size)
                panel = self.analysed(window)
                self.app.processEvents()
                area = window.stack.currentWidget()
                self.assertIsInstance(area, QScrollArea)
                self.assertEqual(area.horizontalScrollBar().maximum(), 0)
                if size[0] > 1000:  # at 900 the placeholder font of the offscreen platform leaves room to stack them only
                    self.assertEqual(panel.shapes_layout.direction(), QBoxLayout.Direction.LeftToRight)

    def test_a_missing_abaqus_keeps_the_window_within_its_width(self):
        window = self.window((900, 680))
        panel = window.analyze
        panel._discover = lambda *_args, **_kwargs: ()
        panel.choose_file(FE, str(self.odb))
        panel.choose_file(EXPERIMENTAL, str(self.unv(base.plate_nodes())))
        self.run_analysis(panel)
        self.assertEqual(panel.state, base.BLOCKED)
        self.assertFalse(panel.launcher_button.isHidden())
        self.assertFalse(panel.folder_button.isHidden())
        self.assertTrue(panel.advanced_toggle.isChecked())  # ABM-UX2: the needed choice opens by itself
        self.app.processEvents()
        self.assertTrue(panel.launcher_button.isVisible() and panel.folder_button.isVisible())
        self.assertEqual(window.stack.currentWidget().horizontalScrollBar().maximum(), 0)

    def test_two_inputs_and_one_primary_button(self):
        window = self.window((900, 680))
        panel = window.analyze
        self.assertEqual(set(panel.fields), {FE, EXPERIMENTAL})
        primary = [b for b in panel.findChildren(QPushButton) if b.objectName() == "primary" and b.isVisibleTo(panel)]
        self.assertEqual(primary, [panel.analyze_button])
        for hidden in (panel.cancel_button, panel.advanced, panel.progress, panel.log, panel.log_button):
            self.assertTrue(hidden.isHidden())
        self.assertFalse(panel.launcher_button.isVisible() or panel.folder_button.isVisible())  # in the closed Advanced

    def test_the_main_view_is_choose_choose_analyze_with_one_collapsed_advanced(self):
        """ABM-UX2: no project toolbar on the page (the File menu has it); technical choices only in Advanced."""
        window = self.window((900, 680))
        panel = window.analyze
        self.app.processEvents()
        names = [b.text() for b in panel.findChildren(QPushButton) if b.isVisibleTo(panel)]
        self.assertEqual(names, ["Choose file...", "Choose file...", "Analyze", "Advanced"])
        tops = [w.mapTo(panel, w.rect().topLeft()).y() for w in (panel.fields[FE], panel.fields[EXPERIMENTAL],
                                                                  panel.analyze_button, panel.advanced_toggle)]
        self.assertEqual(tops, sorted(tops))
        texts = [l.text() for l in panel.findChildren(QLabel) if l.isVisibleTo(panel) and l.text()]
        self.assertFalse(any("FE modes 1-20" in t for t in texts))  # the scope note sits in Advanced
        panel.advanced_toggle.setChecked(True)
        self.app.processEvents()
        self.assertEqual(panel.advanced_toggle.text(), "Hide advanced")
        self.assertTrue(panel.launcher_button.isVisible() and panel.folder_button.isVisible())
        shown = " ".join(l.text() for l in panel.advanced.findChildren(QLabel))
        self.assertIn("FE modes 1-20", shown)
        self.assertIn("Abaqus launcher: found automatically", shown)
        self.assertIn("Extraction folder: beside the ODB", shown)
        self.assertEqual(window.stack.currentWidget().horizontalScrollBar().maximum(), 0)
        panel.advanced_toggle.setChecked(False)
        self.assertTrue(panel.advanced.isHidden())
        menu = [action.text() for action in window.menuBar().actions()[0].menu().actions()]
        self.assertLessEqual({"Open Project...", "Save Project", "Save Project As..."}, set(menu))

    def test_the_tables_are_tabs_and_a_row_still_shows_its_shapes(self):
        panel = self.analysed(self.window())
        tabs = panel.result_tabs
        self.assertEqual([tabs.tabText(i) for i in range(tabs.count())],
                         ["Nearest frequency", "FE modes", "Experimental modes"])
        self.assertEqual(panel.tables["fe"].rowCount(), 20)
        self.assertTrue(panel.show_candidate(1))
        self.wait(panel)
        self.assertEqual(panel.shape_panels[EXPERIMENTAL].chosen_index(), 1)
        for shape in panel.shape_panels.values():
            self.assertTrue(shape.note.isHidden())
            self.assertTrue(shape.caption.isHidden())
            self.assertTrue(shape.facts.isHidden())
            shape.details_toggle.setChecked(True)
            self.assertFalse(shape.caption.isHidden())
            self.assertFalse(shape.facts.isHidden())


class ProgressTests(_WindowCase):
    def test_progress_is_compact_and_cancel_is_unchanged(self):
        runner = base.Runner(base.plate_nodes(), wait_for_cancel=True)
        window = self.window()
        panel = window.analyze
        panel._runner = runner
        panel.choose_file(FE, str(self.odb))
        panel.choose_file(EXPERIMENTAL, str(self.unv(base.plate_nodes())))
        self.assertTrue(panel.analyze())
        end = base.time.monotonic() + 60
        while not runner.started.is_set() and base.time.monotonic() < end:
            self.app.processEvents()
            base.time.sleep(0.01)
        self.app.processEvents()
        self.assertEqual(panel.state, RUNNING)
        self.assertTrue(panel.progress.isVisible())
        self.assertTrue(panel.cancel_button.isVisible())
        self.assertTrue(panel.log.isHidden())
        self.assertTrue(panel.log_button.isVisible())
        panel.log_button.setChecked(True)
        self.assertFalse(panel.log.isHidden())
        panel.cancel()
        self.wait(panel)
        self.assertEqual(panel.state, IDLE)
        self.assertIn("Cancelled", panel.message.text())
        self.assertTrue(panel.progress.isHidden())
        self.assertTrue(panel.log.isHidden())

    def test_the_progress_goes_after_a_finished_analysis(self):
        panel = self.analysed(self.window())
        self.assertTrue(panel.progress.isHidden())
        self.assertTrue(panel.log_button.isHidden())


class ScientificStatementTests(_WindowCase):
    def analysed_with(self, check=None, compare=None):
        window = self.window()
        patches = [mock.patch.object(rm, "run_check", return_value=check)] if check is not None else []
        patches.append(mock.patch.object(cm, "run_compare", **(
            {"return_value": compare} if compare is not None else {"side_effect": AssertionError("no comparison")})))
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        return window, self.analysed(window)

    def assert_no_verified_claim(self, panel):
        self.assertEqual(panel.status_label.text(), am.REGISTRATION_REQUIRED)
        self.assertNotIn("pairs", panel.tables)
        self.assertNotIn("mac", panel.tables)
        tabs = panel.result_tabs
        self.assertNotIn("MAC", [tabs.tabText(i) for i in range(tabs.count())])
        self.assertIn("no MAC", panel.result_box.findChildren(QLabel)[1].text())

    def test_a_refused_registration_is_stated_without_the_service_wording(self):
        window, panel = self.analysed_with()
        self.assert_no_verified_claim(panel)
        self.assertTrue(panel.analysis.registration_reason)  # kept for the earlier window, not shown here
        self.assertEqual(panel.registration_label.text(), am.REGISTRATION_NOTES[am.REFUSED])
        self.assertTrue(panel.registration_label.isVisible())
        self.assertNotIn(panel.analysis.registration_reason, shown_text(window))
        self.assert_clean(window)

    def test_a_failed_check_is_visible_as_a_failure(self):
        failed = rm.RegistrationOutcome(0, error="The check could not be completed (ValueError: fixture SP-13).")
        window, panel = self.analysed_with(check=failed)
        self.assert_no_verified_claim(panel)
        self.assertIn("FAILED", panel.registration_label.text())
        self.assertTrue(panel.registration_label.isVisible())
        self.assertEqual(panel.registration_label.objectName(), "error")
        self.assertEqual(panel.status_label.property("state"), "blocked")
        self.assert_clean(window)

    def test_a_failed_comparison_after_a_verified_check_is_a_failure_too(self):
        verified = rm.RegistrationOutcome(0, view=SimpleNamespace(registration="hash-1"))
        window, panel = self.analysed_with(check=verified, compare=cm.ComparisonOutcome(0, error="no result"))
        self.assert_no_verified_claim(panel)
        self.assertIn("FAILED", panel.registration_label.text())

    def test_a_verified_comparison_shows_pairs_and_mac_without_naming_the_source(self):
        verified = rm.RegistrationOutcome(0, view=SimpleNamespace(registration="hash-1"))
        cells = ("7", "20.0", "EXP1", "1", "20.5", "-2.44", "0.981", "paired", "12", "100 %", "4")
        view = SimpleNamespace(status=cm.PAIRS_FOUND, pair_rows=(SimpleNamespace(cells=cells),),
                               mac_cells=(("0.981",),), mac_fe_modes=(7,), mac_experimental_modes=(1,),
                               mac_values=((0.981,),), assigned_cells=frozenset({(0, 0)}), provenance=(), gates=(),
                               warnings=(REUSED, "Comparator warning."))
        window, panel = self.analysed_with(check=verified, compare=cm.ComparisonOutcome(0, view=view))
        self.assertEqual(panel.status_label.text(), cm.PAIRS_FOUND)
        self.assertEqual(panel.status_label.property("state"), "read")
        tabs = panel.comparison_tabs
        self.assertEqual([tabs.tabText(i) for i in range(2)], ["Mode pairs", "MAC"])
        self.assertIsNone(panel.registration_label)
        self.assertIn("Comparator warning.", panel.details.body.text())
        self.assertIn(am.VERIFIED_LIMITS, panel.details.body.text())
        self.assert_clean(window)

    def test_warnings_are_brief_and_expand(self):
        runner = base.Runner(base.plate_nodes(), frame_value_fallback=(1, 2))  # the loader refuses these two, and says so
        window = pw.ProductionWindow(analyze_options={"runner": runner, "discover": base.FOUND,
                                                      "consent": self.consent})
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        window.show()
        panel = self.analysed(window)
        self.assertTrue(panel.analysis.notes)
        count = len(panel.analysis.notes)
        self.assertEqual(panel.warning_label.text(), f"{count} warning{'' if count == 1 else 's'}: see details.")
        self.assertTrue(panel.warning_label.isVisible())
        self.assertFalse(panel.details.body.isVisible())
        self.assertEqual(panel.details.toggle.text(), SHOW_DETAILS)
        panel.details.toggle.setChecked(True)
        self.assertTrue(panel.details.body.isVisible())
        self.assertEqual(panel.details.toggle.text(), HIDE_DETAILS)
        for note in panel.analysis.notes:
            self.assertIn(note, panel.details.body.text())
        self.assertIn(am.RIGID_NOTE, panel.details.body.text())


class MaterialsTests(_WindowCase):
    def test_a_generic_state_with_no_value_and_no_record(self):
        window = self.window((900, 680))
        window.show_page(pw.MATERIALS_PAGE)
        self.app.processEvents()
        panel = window.materials
        self.assertEqual(panel.badge.text(), msp.NOT_AVAILABLE)
        rows = [[panel.table.item(r, c).text() for c in range(2)] for r in range(panel.table.rowCount())]
        self.assertEqual(rows, [["E1", msp.NOT_IDENTIFIED], ["E2", msp.NOT_IDENTIFIED], ["G12", msp.NOT_IDENTIFIED]])
        self.assertEqual(window.stack.currentWidget().horizontalScrollBar().maximum(), 0)
        self.assert_clean(window)

    def test_the_page_reads_nothing(self):
        text = (ROOT / "src" / "new_gui" / "materials_status_panel.py").read_text(encoding="utf-8")
        for word in ("materials_model", "open(", "read_text", "json", "services"):
            self.assertNotIn(word, text)

    def test_an_analysis_changes_nothing_on_the_page(self):
        window = self.window()
        self.analysed(window)
        self.assertEqual(window.materials.badge.text(), msp.NOT_AVAILABLE)


if __name__ == "__main__":
    unittest.main()
