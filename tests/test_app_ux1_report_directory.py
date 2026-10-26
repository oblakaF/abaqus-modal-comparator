"""APP-UX.1: the PDF / Excel report save dialogs open in one predictable folder of the user.

Without an initial folder the Windows save dialog opens in the folder Python last used (the user's dialog history),
which can be a folder of source measurements. Both report paths — the comparison report (``ModalComparatorApp._excel``
/ ``_pdf``) and the diagnostic report (``diagnostic_report_ui``) — now pass ``Documents\\Abaqus Modal Comparator
Reports`` as the initial folder, never a folder of the analysed files. The user still chooses any other place, and a
cancelled dialog writes nothing. The dialog is intercepted (no native Windows dialog is opened) and the home folder is
a temporary folder, so no test touches the real user profile.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import synthetic_plate_support as S  # noqa: E402
from services import diagnostic_report as dr  # noqa: E402
from services import report_directory  # noqa: E402
from test_diagnostic_report import _Case, pdf_text, sheet_names  # noqa: E402

FOLDER = report_directory.REPORT_FOLDER_NAME


class _Home(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.home = Path(folder.name) / "user"
        (self.home / "Documents").mkdir(parents=True)
        patcher = mock.patch.object(Path, "home", return_value=self.home)
        patcher.start()
        self.addCleanup(patcher.stop)


class ReportDirectoryTests(_Home):
    def test_the_report_folder_in_documents_is_created_and_reused(self):
        expected = self.home / "Documents" / FOLDER
        self.assertEqual(report_directory.default_report_directory(), expected)
        self.assertTrue(expected.is_dir())
        (expected / "earlier.pdf").write_bytes(b"user report")
        self.assertEqual(report_directory.save_dialog_options(), {"initialdir": str(expected)})
        self.assertEqual((expected / "earlier.pdf").read_bytes(), b"user report")  # an existing folder is kept

    def test_without_documents_the_home_folder_is_used_and_no_documents_folder_is_made(self):
        (self.home / "Documents").rmdir()
        self.assertEqual(report_directory.default_report_directory(), self.home / FOLDER)
        self.assertFalse((self.home / "Documents").exists())

    def test_a_folder_that_cannot_be_created_falls_back_to_documents(self):
        with mock.patch.object(Path, "mkdir", side_effect=PermissionError("denied")):
            self.assertEqual(report_directory.default_report_directory(), self.home / "Documents")

    def test_a_missing_home_is_never_created(self):
        missing = self.home.parent / "absent"
        self.assertEqual(report_directory.default_report_directory(missing), missing)
        self.assertFalse(missing.exists())


class ComparisonReportDialogTests(_Home):
    """The established comparison report, through the final owner of ``_excel`` / ``_pdf`` (ui_workflow)."""

    def setUp(self) -> None:
        super().setUp()
        import main

        self.app_module = main.app
        self.data = self.home.parent / "measurements"  # stands for the folder of the analysed ODB / UNV files
        self.data.mkdir()
        self.application = SimpleNamespace(result=object(), cache=self.home.parent / "cache",
                                           _diagnostic_export_source=None)

    def export(self, method: str, writer: str, answer: str):
        calls, written, shown = [], [], []
        with mock.patch.object(self.app_module.filedialog, "asksaveasfilename",
                               side_effect=lambda **options: calls.append(options) or answer), \
                mock.patch.object(self.app_module, writer, side_effect=lambda *args: written.append(args)), \
                mock.patch.object(self.app_module.messagebox, "showinfo", side_effect=lambda *a: shown.append(a)), \
                mock.patch.object(self.app_module.messagebox, "showerror", side_effect=AssertionError("no error")):
            getattr(self.app_module.ModalComparatorApp, method)(self.application)
        return calls, written, shown

    def test_excel_and_pdf_dialogs_open_in_the_report_folder(self):
        expected = str(self.home / "Documents" / FOLDER)
        for method, writer, suffix in (("_excel", "export_excel", ".xlsx"), ("_pdf", "export_pdf", ".pdf")):
            with self.subTest(method):
                calls, _, _ = self.export(method, writer, "")
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0]["initialdir"], expected)
                self.assertNotIn(str(self.data), calls[0]["initialdir"])
                self.assertEqual(calls[0]["initialfile"], f"modal_comparison_report{suffix}")
                self.assertEqual(calls[0]["defaultextension"], suffix)

    def test_cancel_writes_and_shows_nothing(self):
        for method, writer in (("_excel", "export_excel"), ("_pdf", "export_pdf")):
            with self.subTest(method):
                _, written, shown = self.export(method, writer, "")
                self.assertEqual((written, shown), ([], []))
        self.assertEqual(list((self.home / "Documents" / FOLDER).iterdir()), [])

    def test_the_user_can_still_choose_another_place(self):
        for method, writer, name in (("_excel", "export_excel", "chosen.xlsx"), ("_pdf", "export_pdf", "chosen.pdf")):
            with self.subTest(method):
                chosen = self.home.parent / "elsewhere" / name
                _, written, shown = self.export(method, writer, str(chosen))
                self.assertEqual(len(written), 1)
                self.assertIs(written[0][0], self.application.result)  # the same result, the same writer call
                self.assertEqual(written[0][1:], (chosen, self.application.cache / "report_images"))
                self.assertEqual(shown, [("Report saved", str(chosen))])


class DiagnosticReportDialogTests(_Case):
    """The diagnostic report of a FREQUENCY_ONLY_DIAGNOSTIC, through the same final owner (no comparison result)."""

    def setUp(self) -> None:
        super().setUp()
        import main
        import diagnostic_report_ui as ui

        self.ui, self.app_module = ui, main.app
        self.home = self.folder / "user"
        (self.home / "Documents").mkdir(parents=True)
        patcher = mock.patch.object(Path, "home", return_value=self.home)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.data = self.folder / "measurements"
        self.data.mkdir()
        loaded = self.loaded(S.write_experiment(self.data / "f.unv", S.E0, S.G0))
        self.application = SimpleNamespace(result=None, cache=None, excel_button=None, pdf_button=None, root=None,
                                           mode_viewer=None, status=SimpleNamespace(set=lambda text: None),
                                           _post_to_ui=lambda callback: callback() or True)
        ui.enable_diagnostic_export(self.application, loaded)

    def export(self, method: str, answer: str):
        calls, shown = [], []
        with mock.patch.object(self.ui.filedialog, "asksaveasfilename",
                               side_effect=lambda **options: calls.append(options) or answer), \
                mock.patch.object(self.ui.messagebox, "showinfo", side_effect=lambda *a: shown.append(a)), \
                mock.patch.object(self.ui.messagebox, "showerror", side_effect=AssertionError("no error")), \
                mock.patch.object(self.ui.threading, "Thread",
                                  side_effect=lambda target, daemon: SimpleNamespace(start=target)):
            getattr(self.app_module.ModalComparatorApp, method)(self.application)
        return calls, shown

    def test_pdf_and_excel_dialogs_open_in_the_report_folder_and_cancel_writes_nothing(self):
        folder = self.home / "Documents" / FOLDER
        for method, suffix in (("_pdf", ".pdf"), ("_excel", ".xlsx")):
            with self.subTest(method):
                calls, shown = self.export(method, "")
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0]["initialdir"], str(folder))
                self.assertNotIn(str(self.data), calls[0]["initialdir"])
                self.assertEqual(calls[0]["initialfile"], f"modal_diagnostic_report{suffix}")
                self.assertEqual(shown, [])
        self.assertEqual(list(folder.iterdir()), [])
        self.assertEqual(sorted(p.name for p in self.data.iterdir()), ["f.unv"])  # nothing next to the data

    def test_the_user_can_still_choose_another_place(self):
        elsewhere = self.folder / "elsewhere"
        elsewhere.mkdir()
        calls, shown = self.export("_pdf", str(elsewhere / "diag.pdf"))
        self.assertEqual(calls[0]["initialdir"], str(self.home / "Documents" / FOLDER))
        self.assertIn(dr.BANNER, pdf_text(elsewhere / "diag.pdf"))
        self.assertEqual(shown[-1][0], "Report saved")
        self.export("_excel", str(elsewhere / "diag.xlsx"))
        self.assertIn("Provenance", sheet_names(elsewhere / "diag.xlsx"))
        self.assertEqual(list((self.home / "Documents" / FOLDER).iterdir()), [])


from test_app_p1_stale_results import _App  # noqa: E402


class MainWindowExportTests(_App):
    """The real main window: the export buttons of an established comparison and of a frequency-only diagnostic."""

    def export(self, button, answer: str):
        calls, shown = [], []
        with mock.patch.object(Path, "home", return_value=self.folder / "user"), \
                mock.patch("tkinter.filedialog.asksaveasfilename",
                           side_effect=lambda **options: calls.append(options) or answer), \
                mock.patch("tkinter.messagebox.showinfo", side_effect=lambda *a, **k: shown.append(a)), \
                mock.patch("tkinter.messagebox.showerror", side_effect=AssertionError("no error")),                 mock.patch("diagnostic_report_ui.threading.Thread",  # the diagnostic writer runs in the test thread
                           side_effect=lambda target, daemon: SimpleNamespace(start=target)):
            button.invoke()
            deadline = time.monotonic() + 120  # the answer is posted to the Tk loop
            while answer and not shown and time.monotonic() < deadline:
                self.root.update()
                time.sleep(0.05)
        return calls, shown

    def check(self, application, prefix: str) -> None:
        (self.folder / "user" / "Documents").mkdir(parents=True, exist_ok=True)
        folder = self.folder / "user" / "Documents" / FOLDER
        chosen = self.folder / "chosen"
        chosen.mkdir(exist_ok=True)
        for button, suffix in ((application.excel_button, ".xlsx"), (application.pdf_button, ".pdf")):
            with self.subTest(prefix=prefix, suffix=suffix):
                calls, shown = self.export(button, "")
                self.assertEqual([(c["initialdir"], c["initialfile"]) for c in calls],
                                 [(str(folder), f"{prefix}{suffix}")])
                self.assertEqual(shown, [])  # cancelled: nothing written, nothing shown
                self.assertEqual(list(folder.iterdir()), [])
                target = chosen / f"{prefix}{suffix}"
                calls, shown = self.export(button, str(target))
                self.assertEqual(calls[0]["initialdir"], str(folder))
                self.assertTrue(target.is_file() and target.stat().st_size > 0)
                self.assertEqual(shown[-1][0], "Report saved")

    def test_comparison_report_dialogs(self):
        application = self.established(self.application())
        self.check(application, "modal_comparison_report")

    def test_diagnostic_report_dialogs(self):
        application = self.diagnostic(self.application())
        self.check(application, "modal_diagnostic_report")


if __name__ == "__main__":
    unittest.main()
