"""NEW-GUI.1: the PySide6 main window of the new interface, driven headless (Qt ``offscreen`` platform).

First launch is an empty workspace with the archive closed; FE and experimental files of any plate are chosen
through the file dialog (replaced by a stub), replaced, cancelled, cleared and refused with a visible reason; the
label "SP-02" links nothing to the archive; the archive opens only on its command, read-only, and a missing or
damaged archive does not block the window; the analysis page states that no analysis was run and offers only two
actions, Run frequency diagnostic (NEW-GUI.4) and Check reference registration (NEW-GUI.5), both disabled at an empty
start; no user file is changed.

PySide6 comes from ``requirements-new-gui.txt``. Without it these tests are skipped with that reason, except when
``NEW_GUI_REQUIRE_QT=1`` (set in CI), where a missing PySide6 is an error, so the tests really run there.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    from PySide6.QtWidgets import QApplication, QDialog, QLabel, QLineEdit, QPushButton
except ImportError as error:  # pragma: no cover - depends on the environment
    if os.environ.get("NEW_GUI_REQUIRE_QT") == "1":
        raise
    raise unittest.SkipTest(f"PySide6 is not installed ({error}); install requirements-new-gui.txt to run the "
                            "new interface tests (CI sets NEW_GUI_REQUIRE_QT=1 and runs them)")

from PySide6.QtWidgets import QBoxLayout, QFileDialog  # noqa: E402

from new_gui import archive_dialog, window as window_module  # noqa: E402
from new_gui import workspace_state as ws  # noqa: E402
from services import local_input_registry as registry  # noqa: E402
from services import specimen_catalog_view as catalog  # noqa: E402

CATALOGUE = ROOT / "docs" / "auto_id" / "specimen_catalog.json"
ARCHIVE_WORDS = ("GOVERNED", "PHYSICAL", "LEGACY", "NOT_GOVERNED", "catalogue record")
CYRILLIC = re.compile("[Ѐ-ӿ]")


def _app() -> QApplication:
    return QApplication.instance() or window_module.create_application([])


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _texts(widget) -> list[str]:
    found = [label.text() for label in widget.findChildren(QLabel)]
    found += [button.text() for button in widget.findChildren(QPushButton)]
    found += [edit.text() for edit in widget.findChildren(QLineEdit)]
    return found


class _Window(unittest.TestCase):
    def setUp(self):
        self.app = _app()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)
        self.odb = self._file("plate_alu_250x250.odb", b"synthetic odb")
        self.odb2 = self._file("plate_alu_250x250_v2.odb", b"synthetic odb 2")
        self.unv = self._file("plate_alu_roving_hammer.unv", b"synthetic unv")
        self.store = self.folder / "profile" / registry.STORE_NAME
        patcher = mock.patch.object(registry, "default_store", return_value=self.store)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.answers: list[str] = []
        self.asked: list[tuple[str, str]] = []
        self.window = self.make_window()

    def _file(self, name: str, data: bytes) -> Path:
        path = self.folder / name
        path.write_bytes(data)
        return path

    def _ask(self, kind: str, start: str) -> str:
        self.asked.append((kind, start))
        return self.answers.pop(0)

    def make_window(self, **kwargs) -> window_module.MainWindow:
        window = window_module.MainWindow(ask_path=self._ask, **kwargs)
        window.show()
        self.app.processEvents()
        self.addCleanup(self._close, window)
        return window

    def _close(self, window) -> None:
        if window.archive_dialog is not None:
            window.archive_dialog.close()
        window.close()
        window.deleteLater()
        self.app.processEvents()

    def click_choose(self, kind: str, answer: str) -> None:
        self.answers.append(answer)
        self.window.cards[kind].choose_button.click()
        self.app.processEvents()


class FirstLaunchTests(_Window):
    def test_the_workspace_is_empty(self):
        w = self.window
        self.assertTrue(w.windowTitle().startswith("Abaqus"))
        self.assertTrue(w.workspace.empty)
        self.assertTrue(w.empty_state.isVisible())
        self.assertIn("No data selected yet", w.empty_text.text())
        for kind, card in w.cards.items():
            with self.subTest(kind=kind):
                self.assertEqual(card.badge.text(), "Not chosen")
                self.assertEqual(card.path.text(), "")
                self.assertEqual(card.choose_button.text(), "Choose file...")
                self.assertFalse(card.clear_button.isEnabled())
                self.assertFalse(card.error.isVisible())
        self.assertEqual(w.label_edit.text(), "")
        self.assertEqual(w.stack.currentIndex(), 0)

    def test_no_archive_specimen_or_analysis_at_start(self):
        w = self.window
        self.assertIsNone(w.archive_dialog)
        self.assertEqual([d for d in self.app.topLevelWidgets() if isinstance(d, QDialog) and d.isVisible()], [])
        shown = " ".join(_texts(w))
        self.assertNotRegex(shown, r"SP-\d\d")
        for word in ARCHIVE_WORDS:
            self.assertNotIn(word, shown)
        self.assertEqual(w.analysis_badge.text(), "Analysis not run")
        self.assertIn("Analysis not run", w.status_text.text())
        self.assertIn("NOT_AUTHORISED", w.status_text.text())
        self.assertEqual(self.asked, [])

    def test_the_interface_is_english_only(self):
        self.window.open_research_archive().records.setCurrentRow(0)
        self.app.processEvents()
        for text in _texts(self.window):
            self.assertIsNone(CYRILLIC.search(text), text)
        self.assertIn(archive_dialog.UNKNOWN_SHOWN, archive_dialog._shown(catalog.UNKNOWN_TEXT))
        self.assertIsNone(CYRILLIC.search(archive_dialog._shown(catalog.UNKNOWN_TEXT)))


class ChooseFilesTests(_Window):
    def test_fe_and_unv_of_an_arbitrary_plate_without_the_archive(self):
        with mock.patch.object(catalog, "load_catalogue", side_effect=AssertionError("archive read")):
            self.click_choose(ws.FE, str(self.odb))
            self.click_choose(ws.EXPERIMENTAL, str(self.unv))
        w = self.window
        self.assertEqual(self.asked, [(ws.FE, ""), (ws.EXPERIMENTAL, "")])
        self.assertFalse(w.empty_state.isVisible())
        for kind, path, kind_text in ((ws.FE, self.odb, "Abaqus output database (.odb)"),
                                      (ws.EXPERIMENTAL, self.unv, "Universal file (.unv)")):
            card = w.cards[kind]
            with self.subTest(kind=kind):
                self.assertEqual(card.badge.text(), "File chosen; content not checked")
                self.assertEqual(card.path.text(), str(path.resolve()))
                self.assertEqual(card.file_name.text(), path.name)  # readable even when the path is cut off
                self.assertEqual(card.file_type.text(), kind_text)
                self.assertTrue(card.note.isVisible())
                self.assertIn("not a statement that the data are ready for analysis", card.note.text())
                self.assertEqual(card.choose_button.text(), "Replace file...")
                self.assertTrue(card.clear_button.isEnabled())
        self.assertEqual(w.analysis_badge.text(), "Analysis not run")
        self.assertFalse(self.store.exists())

    def test_replace_cancel_and_clear(self):
        w = self.window
        self.click_choose(ws.FE, str(self.odb))
        self.click_choose(ws.FE, str(self.odb2))
        self.assertEqual(self.asked[-1], (ws.FE, str(self.folder.resolve())))  # the dialog starts where the file is
        self.assertEqual(w.cards[ws.FE].path.text(), str(self.odb2.resolve()))
        self.assertEqual(w.cards[ws.FE].file_name.text(), self.odb2.name)
        self.assertEqual(w.cards[ws.FE].path.cursorPosition(), len(str(self.odb2.resolve())))  # the end is shown
        before = w.workspace
        self.click_choose(ws.FE, "")  # the dialog was cancelled
        self.assertIs(w.workspace, before)
        self.assertEqual(w.cards[ws.FE].path.text(), str(self.odb2.resolve()))
        self.assertFalse(w.cards[ws.FE].error.isVisible())
        w.cards[ws.FE].clear_button.click()
        self.app.processEvents()
        self.assertEqual(w.cards[ws.FE].badge.text(), "Not chosen")
        self.assertEqual(w.cards[ws.FE].file_name.text(), "—")
        self.assertTrue(w.empty_state.isVisible())

    def test_a_wrong_path_is_refused_visibly_and_the_previous_choice_is_kept(self):
        w = self.window
        self.click_choose(ws.FE, str(self.folder / "missing.odb"))
        card = w.cards[ws.FE]
        self.assertTrue(card.error.isVisible())
        self.assertIn("does not exist", card.error.text())
        self.assertIn("Nothing was chosen.", card.error.text())
        self.assertEqual(card.badge.text(), "Not chosen")
        self.click_choose(ws.FE, str(self.odb))
        self.assertFalse(card.error.isVisible())
        self.click_choose(ws.FE, str(self.unv))  # an experimental file is not an FE result
        self.assertIn("is not an FE result", card.error.text())
        self.assertIn("The previous choice is kept.", card.error.text())
        self.assertEqual(card.path.text(), str(self.odb.resolve()))
        self.assertEqual(w.statusBar().currentMessage(), "File not accepted.")

    def test_the_real_file_dialog_cancelled_changes_nothing(self):
        w = window_module.MainWindow()
        self.addCleanup(self._close, w)
        with mock.patch.object(QFileDialog, "getOpenFileName", return_value=("", "")) as dialog:
            self.assertEqual(w.choose_file(ws.FE), "")
        dialog.assert_called_once()
        self.assertEqual(dialog.call_args.args[1], "Choose the FE results file")
        self.assertEqual(dialog.call_args.args[3], ws.DIALOG_FILTERS[ws.FE])
        self.assertTrue(w.workspace.empty)

    def test_menu_actions_choose_files(self):
        actions = {action.text(): action for action in self.window.menuBar().actions()[0].menu().actions()}
        self.answers.append(str(self.unv))
        actions["Choose experimental file..."].trigger()
        self.app.processEvents()
        self.assertEqual(self.window.workspace.experimental.path, self.unv.resolve())


class SpecimenLabelTests(_Window):
    def test_sp02_does_not_link_the_archive(self):
        with mock.patch.object(catalog, "load_catalogue", side_effect=AssertionError("archive read")):
            self.window.label_edit.setText("SP-02")
            self.click_choose(ws.EXPERIMENTAL, str(self.unv))
        self.assertEqual(self.window.workspace.specimen_label, "SP-02")
        self.assertIsNone(self.window.archive_dialog)
        shown = " ".join(_texts(self.window))
        for word in ARCHIVE_WORDS:
            self.assertNotIn(word, shown)
        self.assertEqual(self.window.cards[ws.EXPERIMENTAL].badge.text(), "File chosen; content not checked")


class ArchiveTests(_Window):
    def test_the_archive_opens_only_on_its_command_and_changes_nothing(self):
        w = self.window
        self.click_choose(ws.FE, str(self.odb))
        w.label_edit.setText("SP-02")
        before, catalogue = w.workspace, _sha(CATALOGUE)
        w.archive_button.click()
        self.app.processEvents()
        dialog = w.archive_dialog
        self.assertIsNotNone(dialog)
        self.assertTrue(dialog.isVisible())
        self.assertEqual(dialog.windowTitle(), "Research archive (read-only)")
        self.assertEqual(dialog.records.count(), 14)
        self.assertIsNone(dialog.selected_id)  # no record is picked for the user
        self.assertEqual(dialog.passport.toPlainText(), archive_dialog.PICK_TEXT)
        dialog.records.setCurrentRow(1)
        self.app.processEvents()
        self.assertEqual(dialog.selected_id, "SP-02")
        self.assertIn("Identity and status", dialog.passport.toPlainText())
        self.assertEqual([b.text() for b in dialog.findChildren(QPushButton)], ["Close"])  # no "use" action
        self.assertEqual(w.workspace, before)
        self.assertEqual(w.cards[ws.EXPERIMENTAL].badge.text(), "Not chosen")
        self.assertIs(w.open_research_archive(), dialog)  # a second command raises the open dialog
        dialog.close()
        self.app.processEvents()
        self.assertEqual(w.workspace, before)
        self.assertEqual(_sha(CATALOGUE), catalogue)

    def test_the_menu_command_opens_the_archive(self):
        actions = {action.text(): action for action in self.window.menuBar().actions()[0].menu().actions()}
        actions["Open research archive..."].trigger()
        self.app.processEvents()
        self.assertTrue(self.window.archive_dialog.isVisible())

    def test_a_missing_or_damaged_archive_does_not_block_the_window(self):
        bad = self._file("damaged_catalog.json", b"{not json")
        for path in (bad, self.folder / "missing_catalog.json"):
            with self.subTest(archive=path.name):
                self.window = w = self.make_window(archive_path=path)
                dialog = w.open_research_archive()
                self.app.processEvents()
                self.assertTrue(dialog.problem_label.isVisible())
                self.assertIn("The research archive is not available", dialog.problem_label.text())
                self.assertIn("The rest of the program works without it.", dialog.problem_label.text())
                self.assertEqual(dialog.records.count(), 0)
                dialog.close()
                self.click_choose(ws.FE, str(self.odb))
                self.assertEqual(w.cards[ws.FE].badge.text(), "File chosen; content not checked")


class NothingComputedTests(_Window):
    def test_the_analysis_page_offers_only_its_two_commands_and_the_status_page_none(self):
        # NEW-GUI.4 / NEW-GUI.5 (authorised changes of this NEW-GUI.1 test): the Analysis page has exactly two
        # commands, Run frequency diagnostic and Check reference registration, disabled until both files are read and
        # a modal set is chosen; nothing is computed before a click. tests/test_new_gui4_qt.py and
        # tests/test_new_gui5_qt.py check when they become available and what a click gives.
        # NEW-GUI.6 (authorised): the workbench adds Run verified modal comparison and Export report..., and the two
        # unpaired independent shape views their Show shape; all are disabled at start (tests/test_new_gui6_qt.py).
        w = self.window
        analysis, status = w.stack.widget(1).widget(), w.stack.widget(2).widget()
        buttons = analysis.findChildren(QPushButton)
        self.assertEqual([button.text() for button in buttons],
                         ["Run frequency diagnostic", "Check reference registration", "Run verified modal comparison",
                          "Export report...", "Show shape", "Show shape"])
        self.assertFalse(any(button.isEnabled() for button in buttons))
        self.assertEqual(status.findChildren(QPushButton), [])
        texts = " ".join(_texts(analysis))
        self.assertIn("Analysis not run", texts)
        self.assertIn("No frequency, MAC value or mode pair has been computed", texts)
        self.click_choose(ws.FE, str(self.odb))  # choosing files computes nothing and enables nothing
        self.click_choose(ws.EXPERIMENTAL, str(self.unv))
        self.assertFalse(any(button.isEnabled() for button in buttons))
        self.assertFalse(w.busy())
        self.assertEqual(w.analysis_badge.text(), "Analysis not run")
        self.assertIn("No frequency, MAC value or mode pair has been computed", " ".join(_texts(analysis)))
        self.assertEqual({k: b.text() for k, b in w.status_badges.items()},
                         {"Production Auto-ID": "NOT_AUTHORISED", "M8 gate": "NOT_MET",
                          "D-077 formal output": "NO_GLOBAL_PARAMETER_VALUE"})
        w.nav.button(1).click()
        self.assertEqual(w.stack.currentIndex(), 1)
        w.nav.button(2).click()
        self.assertEqual(w.stack.currentIndex(), 2)

    def test_after_choosing_both_files_still_nothing_is_computed(self):
        self.click_choose(ws.FE, str(self.odb))
        self.click_choose(ws.EXPERIMENTAL, str(self.unv))
        self.assertEqual(self.window.analysis_badge.text(), "Analysis not run")
        self.assertEqual(self.window.workspace.analysis, ws.ANALYSIS_NOT_RUN)

    def test_no_user_file_is_changed(self):
        files = {p: (_sha(p), p.stat().st_mtime_ns) for p in (self.odb, self.odb2, self.unv)}
        names = sorted(p.name for p in self.folder.iterdir())
        catalogue = _sha(CATALOGUE)
        self.click_choose(ws.FE, str(self.odb))
        self.click_choose(ws.FE, str(self.odb2))
        self.click_choose(ws.EXPERIMENTAL, str(self.unv))
        self.window.label_edit.setText("SP-02")
        self.window.open_research_archive().records.setCurrentRow(1)
        self.window.clear_file(ws.FE)
        self.app.processEvents()
        self.assertEqual({p: (_sha(p), p.stat().st_mtime_ns) for p in files}, files)
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), names)
        self.assertEqual(_sha(CATALOGUE), catalogue)
        self.assertFalse(self.store.exists())


class LayoutTests(_Window):
    def test_small_and_wide_windows(self):
        w = self.window
        self.assertLessEqual(w.minimumWidth(), 560)
        self.assertLessEqual(w.minimumHeight(), 420)
        w.resize(600, 480)
        self.app.processEvents()
        self.assertEqual(w.sources.direction(), QBoxLayout.Direction.TopToBottom)
        w.resize(1300, 800)
        self.app.processEvents()
        self.assertEqual(w.sources.direction(), QBoxLayout.Direction.LeftToRight)

    def test_the_window_fits_the_available_screen(self):
        free = self.window.screen().availableGeometry()
        self.assertLessEqual(self.window.width(), max(free.width(), self.window.minimumWidth()))
        self.assertLessEqual(self.window.height(), max(free.height(), self.window.minimumHeight()))

    def test_the_window_closes(self):
        self.assertTrue(self.window.close())


if __name__ == "__main__":
    unittest.main()
