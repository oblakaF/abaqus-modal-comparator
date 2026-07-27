from __future__ import annotations

from pathlib import Path

import numpy as np
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

import reporting


_INSTALLED = False


def install_final_reporting_review() -> None:
    """Install the final Excel postprocessor after every other report extension.

    Capturing the current exporter at installation time makes report composition
    independent of Python module import order and test-discovery order.
    """
    global _INSTALLED
    if _INSTALLED:
        return

    previous_export_excel = reporting.export_excel

    def export_excel_final(result, output_path: Path, image_directory: Path) -> Path:
        output_path = previous_export_excel(result, output_path, image_directory)
        workbook = load_workbook(output_path)

        summary = workbook["Summary"]
        errors = [pair.frequency_error_percent for pair in result.pairs]
        if errors:
            summary["A10"] = "Mean absolute frequency error"
            summary["B10"] = float(np.mean(np.abs(errors))) / 100.0
            summary["B10"].number_format = "0.00%"
            summary["A11"] = "Mean signed frequency error"
            summary["B11"] = float(np.mean(errors)) / 100.0
            summary["B11"].number_format = "+0.00%;-0.00%;0.00%"
            summary["A12"] = "Frequency-error sign"
            summary["B12"] = "positive = Abaqus higher; negative = Abaqus lower"

        comparison = workbook["Mode Comparison"]
        comparison.cell(row=1, column=5, value="Signed frequency error, %")
        for column in range(1, comparison.max_column + 1):
            letter = get_column_letter(column)
            comparison.column_dimensions[letter].width = max(
                comparison.column_dimensions[letter].width or 0,
                20,
            )

        workbook.save(output_path)
        return Path(output_path)

    reporting.export_excel = export_excel_final
    _INSTALLED = True
