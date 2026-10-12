"""Two-file frequency-scaling diagnostics (G1) for the ODB + PolyMAX comparison.

For every matched pair of the existing comparison result (``ComparisonResult.pairs``; pairing is not redone) this
module reports the frequency ratio ``f_exp / f_FE``, its square and ``ln(f_exp / f_FE)``, with the pair's MAC, its
comparator status and quality warnings.  Pairs are classified, never re-paired or re-gated:

- ``INVALID_FREQUENCY`` — a frequency is missing, non-finite or not positive: no ratio is computed;
- ``FREQUENCY_ONLY`` — the pair has no MAC (frequency-only match);
- ``LOW_MAC`` — MAC below the accepted strict identification-pairing minimum (``STRICT_IDENTIFICATION_PAIRING``);
- ``QUESTIONABLE`` — MAC-supported but outside the strict relative frequency window, with an order change or with
  insufficient measurement coverage;
- ``MAC_SUPPORTED`` — none of the above.

Only ``MAC_SUPPORTED`` pairs enter the descriptive summary (median and range).  The range is a descriptive spread,
never a statistical uncertainty.  Every value is labelled FREQUENCY_SCALING_DIAGNOSTIC_ONLY, NOT_A_MATERIAL_PROPERTY
and NOT_A_SCIENTIFIC_IDENTIFICATION_VERDICT: a frequency ratio is not a unique stiffness or material correction (it
mixes stiffness, mass, geometry, boundary conditions and model form; a sandwich panel is not a homogeneous isotropic
material), and no E, G or ν is derived here.  The diagnostic is independent of Auto-ID verdicts.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import statistics
from typing import Optional, Sequence

from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING

LABELS = ("FREQUENCY_SCALING_DIAGNOSTIC_ONLY", "NOT_A_MATERIAL_PROPERTY", "NOT_A_SCIENTIFIC_IDENTIFICATION_VERDICT")
LABEL_TEXT = " · ".join(LABELS)
CAVEAT = ("A frequency ratio is not a unique stiffness or material correction: it combines stiffness, mass, geometry, "
          "boundary conditions and model form. No E, G or ν is derived. The range is a descriptive spread of the "
          "MAC-supported pairs, not a statistical uncertainty.")
MAC_SUPPORTED = "MAC_SUPPORTED"
QUESTIONABLE = "QUESTIONABLE"
LOW_MAC = "LOW_MAC"
FREQUENCY_ONLY = "FREQUENCY_ONLY"
INVALID_FREQUENCY = "INVALID_FREQUENCY"
ACCEPTED_COVERAGE = "accepted"  # reviewed_core coverage status of a fully covered pair
MINIMUM_MAC = STRICT_IDENTIFICATION_PAIRING.minimum_mac  # accepted strict pairing minimum (0.80)
MAXIMUM_RELATIVE_ERROR = STRICT_IDENTIFICATION_PAIRING.maximum_relative_frequency_error  # |f_FE - f_EXP| / f_EXP


@dataclass(frozen=True)
class ScalingRow:
    fe_mode: object
    experimental_mode: object
    fe_frequency_hz: Optional[float]
    experimental_frequency_hz: Optional[float]
    mac: Optional[float]
    comparator_status: str
    frequency_ratio: Optional[float]  # f_exp / f_FE
    squared_frequency_ratio: Optional[float]  # (f_exp / f_FE) ** 2
    log_frequency_difference: Optional[float]  # ln(f_exp / f_FE)
    direction: str
    category: str
    warnings: tuple[str, ...]

    @property
    def in_summary(self) -> bool:
        return self.category == MAC_SUPPORTED


@dataclass(frozen=True)
class ScalingSummary:
    """Descriptive median and range of the MAC-supported pairs (never a statistical uncertainty)."""

    count: int
    median_ratio: float
    median_squared_ratio: float
    median_log_difference: float
    min_log_difference: float
    max_log_difference: float

    @property
    def log_range(self) -> float:
        return self.max_log_difference - self.min_log_difference


@dataclass(frozen=True)
class FrequencyScalingDiagnostic:
    rows: tuple[ScalingRow, ...]
    summary: Optional[ScalingSummary]
    status: str  # AVAILABLE | UNAVAILABLE
    message: str
    labels: tuple[str, ...] = LABELS


def _frequency(value) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value > 0.0 else None


def _mac(value) -> Optional[float]:
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def scaling_row(pair) -> ScalingRow:
    """One matched pair of the existing comparison result, classified (the pair itself is never changed)."""

    fe = _frequency(getattr(pair, "abaqus_frequency_hz", None))
    exp = _frequency(getattr(pair, "experimental_frequency_hz", None))
    mac = _mac(getattr(pair, "mac", None))
    status = str(getattr(pair, "status", ""))
    warnings = []
    if fe is None or exp is None:
        warnings.append("missing, non-finite or non-positive frequency: no ratio computed")
        return ScalingRow(getattr(pair, "abaqus_mode", None), getattr(pair, "experimental_mode", None), fe, exp, mac,
                          status, None, None, None, "not available", INVALID_FREQUENCY, tuple(warnings))
    ratio = exp / fe
    log_difference = math.log(ratio)
    direction = ("experiment higher than FE" if ratio > 1.0 else "experiment lower than FE" if ratio < 1.0
                 else "equal")
    if mac is None:
        category = FREQUENCY_ONLY
        warnings.append("frequency-only match: no MAC, mode identity not shape-verified")
    elif mac < MINIMUM_MAC:
        category = LOW_MAC
        warnings.append(f"MAC {mac:.3f} below the strict identification-pairing minimum {MINIMUM_MAC:.2f}")
    else:
        category = MAC_SUPPORTED
    if abs(fe - exp) / exp > MAXIMUM_RELATIVE_ERROR:
        warnings.append(f"|f_FE - f_exp| / f_exp above the strict pairing window {MAXIMUM_RELATIVE_ERROR:.0%}")
    if getattr(pair, "order_changed", False):
        warnings.append("mode order changed between FE and experiment")
    coverage = getattr(pair, "coverage_status", None)
    if coverage is not None and coverage != ACCEPTED_COVERAGE:
        warnings.append(f"measurement coverage: {coverage}")
    if category == MAC_SUPPORTED and warnings:
        category = QUESTIONABLE
    return ScalingRow(getattr(pair, "abaqus_mode", None), getattr(pair, "experimental_mode", None), fe, exp, mac,
                      status, ratio, ratio * ratio, log_difference, direction, category, tuple(warnings))


def frequency_scaling_diagnostic(pairs: Optional[Sequence]) -> FrequencyScalingDiagnostic:
    """The diagnostic for the matched pairs of an existing comparison result (pairing is not redone)."""

    rows = tuple(scaling_row(pair) for pair in (pairs or ()))
    usable = [row for row in rows if row.in_summary]
    if not rows:
        return FrequencyScalingDiagnostic((), None, "UNAVAILABLE",
                                          "Frequency-scaling diagnostic unavailable: the comparison has no matched "
                                          "pairs.")
    if not usable:
        return FrequencyScalingDiagnostic(rows, None, "UNAVAILABLE",
                                          "Frequency-scaling diagnostic unavailable: no MAC-supported pair without "
                                          "quality warnings; the listed pairs are not evidence for material "
                                          "identification.")
    logs = [row.log_frequency_difference for row in usable]
    summary = ScalingSummary(len(usable), statistics.median(row.frequency_ratio for row in usable),
                             statistics.median(row.squared_frequency_ratio for row in usable),
                             statistics.median(logs), min(logs), max(logs))
    return FrequencyScalingDiagnostic(rows, summary, "AVAILABLE", summary_text(summary))


def summary_text(summary: ScalingSummary) -> str:
    if summary.count == 1:
        return (f"1 MAC-supported pair: f_exp/f_FE {summary.median_ratio:.4f}, (f_exp/f_FE)^2 "
                f"{summary.median_squared_ratio:.4f}, ln(f_exp/f_FE) {summary.median_log_difference:+.4f} "
                "(a single pair: no spread).")
    return (f"{summary.count} MAC-supported pairs: median f_exp/f_FE {summary.median_ratio:.4f}, median "
            f"(f_exp/f_FE)^2 {summary.median_squared_ratio:.4f}, median ln(f_exp/f_FE) "
            f"{summary.median_log_difference:+.4f}; ln range {summary.min_log_difference:+.4f} to "
            f"{summary.max_log_difference:+.4f} (descriptive spread, not a statistical uncertainty).")


def _number(value: Optional[float], digits: int, signed: bool = False) -> str:
    if value is None:
        return "—"
    return f"{value:+.{digits}f}" if signed else f"{value:.{digits}f}"


def table_rows(diagnostic: FrequencyScalingDiagnostic) -> tuple[tuple[str, ...], ...]:
    """GUI rows: FE mode, experimental mode, frequencies, MAC, ratios, direction, category, status, warnings."""

    return tuple((str(row.fe_mode), str(row.experimental_mode), _number(row.fe_frequency_hz, 4),
                  _number(row.experimental_frequency_hz, 4), _number(row.mac, 3), _number(row.frequency_ratio, 5),
                  _number(row.squared_frequency_ratio, 5), _number(row.log_frequency_difference, 5, signed=True),
                  row.direction, row.category, row.comparator_status, "; ".join(row.warnings) or "none")
                 for row in diagnostic.rows)


EXCEL_HEADERS = ("FE mode", "Experimental mode", "FE frequency, Hz", "Experimental frequency, Hz", "MAC",
                 "f_exp / f_FE", "(f_exp / f_FE)^2", "ln(f_exp / f_FE)", "Direction", "Category",
                 "Comparator status", "In descriptive summary", "Quality warnings")


def write_excel_sheet(workbook, diagnostic: FrequencyScalingDiagnostic, title: str = "Frequency Scaling"):
    """A separate workbook sheet with the labels, the caveat, the summary and one row per matched pair."""

    sheet = workbook.create_sheet(title)
    sheet.append(["Labels", LABEL_TEXT])
    sheet.append(["Caveat", CAVEAT])
    sheet.append(["Status", diagnostic.status])
    sheet.append(["Summary", diagnostic.message])
    if diagnostic.summary is not None:
        summary = diagnostic.summary
        sheet.append(["MAC-supported pairs", summary.count])
        sheet.append(["Median f_exp / f_FE", summary.median_ratio])
        sheet.append(["Median (f_exp / f_FE)^2", summary.median_squared_ratio])
        sheet.append(["Median ln(f_exp / f_FE)", summary.median_log_difference])
        sheet.append(["ln range (descriptive, not uncertainty)", summary.min_log_difference,
                      summary.max_log_difference])
    sheet.append([])
    sheet.append(list(EXCEL_HEADERS))
    for row in diagnostic.rows:
        sheet.append([row.fe_mode, row.experimental_mode, row.fe_frequency_hz, row.experimental_frequency_hz, row.mac,
                      row.frequency_ratio, row.squared_frequency_ratio, row.log_frequency_difference, row.direction,
                      row.category, row.comparator_status, "yes" if row.in_summary else "no",
                      "; ".join(row.warnings) or "none"])
    sheet.column_dimensions["A"].width = 34
    sheet.column_dimensions["B"].width = 22
    return sheet
