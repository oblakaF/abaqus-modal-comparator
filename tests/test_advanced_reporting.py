from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from openpyxl import Workbook, load_workbook
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import advanced_reporting
from metrics_normalization import install_metrics_normalization
from test_core import ModalCoreTests


def _fake_export_excel(_result, output_path, _image_directory):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    workbook.active.title = "Summary"
    workbook.save(output_path)
    return output_path


def _fake_export_pdf(_result, output_path, _image_directory):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(output_path) as pdf:
        figure = Figure(figsize=(4.0, 3.0))
        figure.add_subplot(111).set_title("base report page")
        pdf.savefig(figure)
    return output_path


class AdvancedReportingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_metrics_normalization()

    def make_result(self):
        return ModalCoreTests().synthetic_result()

    def test_export_excel_advanced_adds_automac_comac_sheet(self):
        result = self.make_result()
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            with patch.object(
                advanced_reporting, "_ORIGINAL_EXPORT_EXCEL", _fake_export_excel
            ):
                output = advanced_reporting.export_excel_advanced(
                    result, directory / "report.xlsx", directory / "images"
                )
            workbook = load_workbook(output)
            try:
                self.assertIn("Summary", workbook.sheetnames)
                self.assertIn("AutoMAC COMAC", workbook.sheetnames)
                sheet = workbook["AutoMAC COMAC"]
                self.assertEqual(sheet["A1"].value, "AutoMAC and COMAC diagnostics")
                keys = {sheet.cell(row=row, column=1).value for row in range(3, 8)}
                self.assertTrue(keys & {"mean_comac", "abaqus_automac_max_off_diagonal"})
            finally:
                workbook.close()

    def test_export_excel_advanced_replaces_rather_than_duplicates_sheet(self):
        result = self.make_result()
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            with patch.object(
                advanced_reporting, "_ORIGINAL_EXPORT_EXCEL", _fake_export_excel
            ):
                output_path = directory / "report.xlsx"
                advanced_reporting.export_excel_advanced(
                    result, output_path, directory / "images"
                )
                # A second call reuses the same base workbook (as if export_excel_advanced
                # were re-run against an existing report) and must not leave two sheets
                # with the same name.
                _fake_export_excel(result, output_path, directory / "images")
                advanced_reporting.export_excel_advanced(
                    result, output_path, directory / "images"
                )
            workbook = load_workbook(output_path)
            try:
                self.assertEqual(workbook.sheetnames.count("AutoMAC COMAC"), 1)
            finally:
                workbook.close()

    def test_export_pdf_advanced_merges_base_and_extension_pages(self):
        result = self.make_result()
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            with patch.object(
                advanced_reporting, "_ORIGINAL_EXPORT_PDF", _fake_export_pdf
            ):
                output = advanced_reporting.export_pdf_advanced(
                    result, directory / "report.pdf", directory / "images"
                )
            reader = PdfReader(str(output))
            # 1 base page + 1 AutoMAC/COMAC image page + 1 text summary page.
            self.assertEqual(len(reader.pages), 3)


if __name__ == "__main__":
    unittest.main()
