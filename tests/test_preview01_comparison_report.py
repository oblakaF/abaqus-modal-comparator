"""PREVIEW-01-COMPARISON-REPORT-FIX: the Review page exports the comparison report of a result with mode pairs.

Synthetic data only. The report is the program's existing comparison report (Excel, PDF, JSON record); what is checked
here is that the normal window reaches it, that the files read back equal the comparison held in memory, that the
registration basis and every verdict are stated, and that nothing is compared again or invented to write them."""

from __future__ import annotations

from dataclasses import replace
import json
import threading
import time
import unittest
from unittest import mock

import test_abm_aud4_modal_comparison as a4
import test_new_gui6_workbench as g6

import modal_core
from new_gui import analyze_model as am
from new_gui import comparison_model as cm
from new_gui import report_export as rx
from new_gui import review_panel as rp

SWAPPED = ((51.0, a4.U1), (112.0, a4.C), (113.0, a4.B), (174.0, a4.D))  # an unmatched record and a permuted close pair
WEAK = ((51.0, a4.A), (82.0, a4.mixed((1.0, a4.B), (0.8, a4.U1))), (123.0, a4.C), (174.0, a4.D), (236.0, a4.E))


def sheets(path) -> dict:
    from openpyxl import load_workbook

    book = load_workbook(path)
    try:
        return {name: {"rows": [list(row) for row in book[name].iter_rows(values_only=True)],
                       "images": len(getattr(book[name], "_images", ()))} for name in book.sheetnames}
    finally:
        book.close()


def table(rows: list, titles: tuple) -> list:
    """The rows under the row that holds ``titles``, up to the first row whose first cell is not a number."""
    start = next(i for i, row in enumerate(rows) if tuple(row[:len(titles)]) == titles)
    found = []
    for row in rows[start + 1:]:
        if not isinstance(row[0], (int, float)):
            break
        found.append(row)
    return found


def pdf_pages(path) -> list:
    from pypdf import PdfReader

    with open(path, "rb") as stream:
        return [" ".join((page.extract_text() or "").split()) for page in PdfReader(stream).pages]


def one(folder, suffix):
    (path,) = [p for p in folder.iterdir() if p.suffix == suffix]
    return path


class _Exported:
    def folder(self, name):
        folder = self.root / name
        folder.mkdir()
        return folder

    def check_statement(self, written_folder, analysis, basis):
        """Excel, PDF and JSON of one export against the comparison in memory; returns the first sheet's rows."""
        result, verdicts = analysis.comparison_result, {int(row[1]): row[-1] for row in analysis.nearest_rows}
        self.assertEqual(sorted(p.suffix for p in written_folder.iterdir()), [".json", ".pdf", ".xlsx"])
        self.assertTrue(all(p.name.startswith(rx.VERIFIED_STEM) for p in written_folder.iterdir()))
        book = sheets(one(written_folder, ".xlsx"))
        self.assertEqual(list(book)[0], rx.STATEMENT_SHEET)
        self.assertIn("Mode Comparison", book)  # the program's own comparison sheets follow
        rows = book[rx.STATEMENT_SHEET]["rows"]
        said = {row[0]: row[1] for row in rows if row[0] and row[1] is not None}
        self.assertEqual((said["Status"], said["Statement"]), (analysis.status, analysis.statement))
        self.assertEqual(said["Registration basis"], basis)
        self.assertEqual(said["Physical mode identity"], rx.IDENTITY_NOT_CLAIMED)
        self.assertEqual(said["registration hash"], analysis.comparison.registration)
        pairs = table(rows, rx.PAIR_TITLES)
        self.assertEqual(len(pairs), len(result.pairs))
        self.assertTrue(result.pairs)
        for row, pair in zip(pairs, result.pairs):  # the comparator's own numbers, not rounded and not re-ranked
            self.assertEqual((row[0], row[3], row[7]), (int(pair.abaqus_mode), int(pair.experimental_mode),
                                                        str(pair.status)))
            for cell, value in ((row[1], pair.abaqus_frequency_hz), (row[4], pair.experimental_frequency_hz),
                                (row[5], pair.frequency_error_percent), (row[6], pair.mac)):
                self.assertAlmostEqual(cell, float(value), delta=1e-12 * max(1.0, abs(float(value))))  # a workbook's digits
            self.assertEqual(row[9], verdicts[int(pair.experimental_mode)])
            self.assertAlmostEqual(row[5], 100.0 * (row[1] - row[4]) / row[4], places=9)  # signed: (FE - EXP) / EXP
        paired = {int(pair.experimental_mode) for pair in result.pairs}
        without = table(rows, rx.RECORD_TITLES)
        self.assertEqual([row[1] for row in without], [n for n in sorted(verdicts) if n not in paired])
        for row in without:
            self.assertEqual(row[3], verdicts[row[1]])
        every = "\n".join(str(cell) for row in rows for cell in row if cell is not None)
        for warning in result.warnings:
            self.assertIn(str(warning), every)
        # the PDF opens with the same statement; the program's own pages follow
        pages = pdf_pages(one(written_folder, ".pdf"))
        front = " ".join(pages[:3])
        self.assertIn(basis, pages[0])
        self.assertIn("PHYSICAL MODE IDENTITY: NOT ESTABLISHED BY THIS REPORT", pages[0])
        for pair in result.pairs:
            self.assertIn(f"FE mode {pair.abaqus_mode} ({pair.abaqus_frequency_hz:.4f} Hz) - EXP record", front)
            self.assertIn(f"error {pair.frequency_error_percent:+.2f} %, MAC {pair.mac:.3f}, {pair.status}", front)
        for text in verdicts.values():
            self.assertIn(text.split(":")[0], front)
        # the JSON record
        record = json.loads(one(written_folder, ".json").read_text(encoding="utf-8"))
        self.assertEqual((record["status"], record["registration_basis"]), (analysis.status, basis))
        self.assertEqual(record["physical_mode_identity"], rx.IDENTITY_NOT_CLAIMED)
        self.assertEqual([(p["fe_mode"], p["experimental_mode"], p["mac"], p["signed_frequency_error_percent"],
                           p["verdict"]) for p in record["pairs"]],
                         [(int(p.abaqus_mode), int(p.experimental_mode), float(p.mac), float(p.frequency_error_percent),
                           verdicts[int(p.experimental_mode)]) for p in result.pairs])
        self.assertEqual([r["experimental_mode"] for r in record["records_without_a_pair"]],
                         [row[1] for row in without])
        return rows, pages, record


class ConfirmedComparisonReportTests(_Exported, a4._Compared):
    @staticmethod
    def settle(seconds):
        from PySide6.QtWidgets import QApplication

        end = time.monotonic() + seconds
        while time.monotonic() < end:
            QApplication.processEvents()
            time.sleep(0.005)

    def exported(self, review, folder):
        self.assertTrue(review.export_report(str(folder)))
        self.assertFalse(review.export_button.isEnabled())  # one export at a time
        deadline = time.monotonic() + 180
        while review._exporting and time.monotonic() < deadline:
            self.settle(0.05)
        self.assertFalse(review._exporting)
        return review.export_feedback.text()

    def test_the_review_page_exports_the_pairs_mac_registration_and_verdicts_it_shows(self):
        panel, analysis = self.compared(a4.CLOSE_FE, SWAPPED)
        review = panel.window().review
        self.assertEqual(analysis.registration_basis, rx.CONFIRMED_BASIS)
        self.assertEqual(am.report_kind(analysis), am.COMPARISON_REPORT)
        self.assertTrue(review.export_button.isEnabled(), review.export_problem())  # it was disabled for such a result
        self.assertEqual(review.export_button.toolTip(), rp.EXPORT_HINTS[am.COMPARISON_REPORT])
        self.assertFalse(review.export_reason.isVisible())
        kept, bound = analysis.comparison_result, analysis.comparison_bound
        folder = self.folder("comparison report")
        refuse = AssertionError("computed again for the report")
        with g6.reporting_restored(), \
                mock.patch.object(modal_core, "compare_modal_datasets", side_effect=refuse), \
                mock.patch.object(cm, "mode_verdicts", side_effect=refuse), \
                mock.patch.object(cm, "comparison_view", side_effect=refuse), \
                mock.patch.object(am, "analyse", side_effect=refuse), \
                mock.patch("new_gui.diagnostic_model.run_diagnostic", side_effect=refuse), \
                mock.patch("abaqus_bridge.subprocess.Popen", side_effect=AssertionError("a process was started")):
            message = self.exported(review, folder)
            # the program's own report alone, for comparison: the statement is added in front, nothing is taken away
            plain = self.folder("the program's report alone")
            rx.export_verified(kept, bound, analysis.comparison, panel.inputs.fe, panel.inputs.experimental,
                               analysis.set_index, plain, sources=panel.inputs.identities)
        self.assertTrue(message.startswith("Report exported: "), message)
        self.assertIs(panel.analysis.comparison_result, kept)
        self.assertTrue(review.export_button.isEnabled())
        rows, pages, record = self.check_statement(folder, analysis, rx.CONFIRMED_BASIS)
        every = "\n".join(str(cell) for row in rows for cell in row if cell is not None)
        # a person's confirmation, named as that and as nothing more
        self.assertIn(rx.BASIS_TEXT[rx.CONFIRMED_BASIS], every)
        self.assertNotIn(rx.ARCHIVED_BASIS, every)
        self.assertNotIn(rx.BASIS_TEXT[rx.ARCHIVED_BASIS], every)
        said = {row[0]: row[1] for row in rows if row[0] and row[1] is not None}
        self.assertEqual((said["confirmed by"], said["evidence location"]),
                         ("A. Tester", "laboratory notebook 7, page 12"))
        self.assertEqual((said["independent verification"], said["governed"]), ("False", "False"))
        self.assertEqual(record["registration"]["confirmed_by"], "A. Tester")
        # the close pair keeps its group-level verdict beside a MAC of 1.000; the unmatched record is not paired
        pairs = table(rows, rx.PAIR_TITLES)
        self.assertEqual([(row[0], row[3]) for row in pairs], [(8, 3), (9, 2), (10, 4)])
        for row in pairs[:2]:
            self.assertGreater(row[6], 0.99)
            self.assertTrue(row[9].startswith(cm.GROUP_VERDICT), row[9])
            self.assertIn(cm.GROUP_UNRESOLVED, row[9])
            self.assertFalse(row[9].startswith(cm.CONFIRMED_VERDICT))
        (alone,) = table(rows, rx.RECORD_TITLES)
        self.assertEqual(alone[1], 1)
        self.assertTrue(alone[3].startswith(cm.REJECTED_VERDICT), alone[3])
        self.assertIn(cm.GROUP_VERDICT, " ".join(pages[:3]))
        self.assertTrue(any(line.startswith(cm.CLOSE_PREFIX) for line in record["close_mode_groups"]))
        # the program's own sheets and pages are the ones it writes alone
        own, alone_book = sheets(one(folder, ".xlsx")), sheets(one(plain, ".xlsx"))
        self.assertEqual(list(own)[1:], list(alone_book))
        for name, sheet in alone_book.items():
            self.assertEqual(own[name]["images"], sheet["images"], name)
            self.assertEqual(len(own[name]["rows"]), len(sheet["rows"]), name)
        self.assertEqual(own["Mode Comparison"]["rows"], alone_book["Mode Comparison"]["rows"])
        alone_pages = pdf_pages(one(plain, ".pdf"))
        self.assertGreater(len(pages), len(alone_pages))
        self.assertEqual(pages[len(pages) - len(alone_pages):], alone_pages)

    def test_what_cannot_be_exported_says_why_and_writes_nothing(self):
        panel, analysis = self.compared(a4.CLOSE_FE, SWAPPED)
        review, inputs = panel.window().review, panel.inputs
        folder = self.folder("refused")
        with g6.reporting_restored():
            # a cancelled folder dialog starts nothing
            with mock.patch.object(rp.QFileDialog, "getExistingDirectory", return_value="") as asked:
                self.assertFalse(review.export_report())
            self.assertEqual(asked.call_args[0][1], rp.EXPORT_FOLDER[am.COMPARISON_REPORT])
            self.assertFalse(review._exporting)
            self.assertFalse(review.export_feedback.isVisible())
            # a folder that does not exist
            message = self.exported(review, self.root / "no such folder")
            self.assertTrue(message.startswith("Report not exported: ") and "is not an existing folder" in message, message)
            self.assertEqual(review.export_feedback.objectName(), "error")
            # identities that were not recorded at the read: no provenance is claimed
            for missing in ({"fe": None, "experimental": inputs.identities["experimental"]},
                            {"fe": inputs.identities["fe"], "experimental": None}):
                with self.assertRaisesRegex(am.StepFailed, "not recorded when it was read"):
                    am.export_report(replace(inputs, identities=missing), analysis, folder)
            # a comparison whose own result or registration is not held: never the frequency-only report instead
            for lost in (replace(analysis, comparison_result=None), replace(analysis, comparison_bound=None),
                         replace(analysis, registration_basis="")):
                self.assertEqual(am.report_problem(inputs, lost, False), am.REPORT_NOT_KEPT)
                with self.assertRaisesRegex(am.StepFailed, "pairs and MAC cannot be stated"):
                    am.export_report(inputs, lost, folder)
            with self.assertRaisesRegex(rx.ExportRefused, "is not stated"):
                rx.comparison_statement(analysis.comparison_result, analysis.comparison_bound, analysis.comparison,
                                        inputs.experimental, analysis.set_index, "PHYSICALLY_VERIFIED")
            # a source file changed since the read
            with open(inputs.full_experimental.source_path, "ab") as stream:
                stream.write(b"\n")
            message = self.exported(review, folder)
        self.assertTrue(message.startswith("Report not exported: ") and "changed since it was read" in message, message)
        self.assertEqual(list(folder.iterdir()), [])

    def test_a_reopened_comparison_is_not_exported_and_the_page_says_why(self):
        panel, analysis = self.compared(a4.CLOSE_FE, SWAPPED)
        self.saved(panel)
        _second, again = self.reopened()
        review = again.window().review
        self.settle(0.2)
        self.assertIsNotNone(again.snapshot)
        self.assertEqual(again.analysis.comparison, analysis.comparison)  # the saved pairs, none added
        self.assertIsNone(again.analysis.comparison_result)
        self.assertIsNone(again.analysis.comparison_bound)
        self.assertEqual(again.analysis.registration_basis, "")
        self.assertFalse(review.export_button.isEnabled())
        self.assertTrue(review.export_reason.isVisible())
        self.assertEqual(review.export_reason.text(), rp.EXPORT_UNAVAILABLE + am.REPORT_SNAPSHOT)
        self.assertIn(am.REPORT_SNAPSHOT, review.export_button.toolTip())
        folder = self.folder("snapshot")
        self.assertFalse(review.export_report(str(folder)))
        with self.assertRaisesRegex(am.StepFailed, "No result of files read in this session"):
            am.export_report(None, again.analysis, folder)
        self.assertEqual(list(folder.iterdir()), [])

    def test_an_ambiguous_pair_keeps_its_verdict_and_a_high_mac_is_not_called_an_identity(self):
        panel, analysis = self.compared(a4.CLEAR_FE, WEAK)
        folder = self.folder("ambiguous")
        with g6.reporting_restored():
            written = am.export_report(panel.inputs, analysis, folder)
        self.assertEqual(sorted(p.suffix for p in written), [".json", ".pdf", ".xlsx"])
        rows, pages, _record = self.check_statement(folder, analysis, rx.CONFIRMED_BASIS)
        verdict = {row[3]: (row[6], row[7], row[9]) for row in table(rows, rx.PAIR_TITLES)}
        mac, status, text = verdict[2]
        self.assertAlmostEqual(mac, 1.0 / 1.64, delta=0.02)
        self.assertNotIn(status, cm.SOUND_STATUSES)
        self.assertTrue(text.startswith(cm.AMBIGUOUS_VERDICT), text)
        self.assertGreater(verdict[1][0], 0.99)
        self.assertIn(cm.AMBIGUOUS_VERDICT, " ".join(pages[:3]))
        self.assertIn("A high MAC is not proof that one FE mode is one measured mode", pages[0])


class ArchivedComparisonReportTests(_Exported, g6._Comparison):
    """The archived registration of the synthetic fixture world, through the analysis of the normal window's model."""

    def setUp(self):
        super().setUp()
        self.root = self.own
        self.inputs = am.scoped_inputs(self.fe_preview, self.exp_preview, self.sources)

    def test_an_archived_registration_is_named_as_archived_and_never_as_a_persons_confirmation(self):
        analysis = am.analyse(self.inputs, 0, threading.Event())
        self.assertEqual(analysis.status, cm.PAIRS_FOUND, analysis.registration_reason)
        self.assertEqual(analysis.registration_basis, rx.ARCHIVED_BASIS)
        self.assertEqual(am.report_problem(self.inputs, analysis, False), "")
        folder = self.folder("archived")
        before = g6.fingerprint(self.world.root)
        with g6.reporting_restored(), \
                mock.patch.object(modal_core, "compare_modal_datasets", side_effect=AssertionError("compared again")):
            am.export_report(self.inputs, analysis, folder)
        self.assertEqual(g6.fingerprint(self.world.root), before)  # the sources and the registrations are not written
        rows, _pages, record = self.check_statement(folder, analysis, rx.ARCHIVED_BASIS)
        every = "\n".join(str(cell) for row in rows for cell in row if cell is not None)
        self.assertIn(rx.BASIS_TEXT[rx.ARCHIVED_BASIS], every)
        self.assertNotIn(rx.CONFIRMED_BASIS, every)
        self.assertNotIn("confirmed by", every)
        self.assertEqual(record["registration"]["registration_hash"], self.registration)
        self.assertEqual(record["registration"]["fixture_id"], analysis.comparison.fixture_id)
        self.assertEqual(record["statement"], am.VERIFIED_TEXT)
        self.assertIn(am.VERIFIED_LIMITS, record["notes"])

    def test_without_a_registration_the_frequency_only_report_is_still_the_one_written(self):
        analysis = am.analyse(self.inputs, 1, threading.Event())  # the other set of the file: the registration is pinned
        self.assertEqual(analysis.status, am.REGISTRATION_REQUIRED)
        self.assertEqual((analysis.registration_basis, analysis.comparison_bound), ("", None))
        self.assertEqual(am.report_kind(analysis), am.DIAGNOSTIC_REPORT)
        folder = self.folder("frequency only")
        written = am.export_report(self.inputs, analysis, folder)
        self.assertEqual(sorted(p.suffix for p in written), [".pdf", ".xlsx"])
        self.assertTrue(all(p.name.startswith(rx.DIAGNOSTIC_STEM) for p in written))
        book = sheets(one(folder, ".xlsx"))
        self.assertNotIn(rx.STATEMENT_SHEET, book)
        every = "\n".join(str(cell) for sheet in book.values() for row in sheet["rows"] for cell in row if cell is not None)
        self.assertIn(am.REPORT_STATEMENT, every)
        self.assertIn("NOT_COMPUTED", every)
        self.assertNotIn("Excellent match", every)
        self.assertNotIn(rx.ARCHIVED_BASIS, every)


if __name__ == "__main__":
    unittest.main()
