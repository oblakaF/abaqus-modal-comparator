"""Preliminary E_in what-if on the archived local sensitivity model (G2d-2 SP-02, G2d-3 SP-13; display only).

For the accepted strict pairs of the specimen named by a G2c ``ARCHIVED_SENSITIVITY_EVIDENCE_VERIFIED`` result (the
comparison used the accepted physical registration), a user-chosen E_in change within the archived ±5 % predicts

    f_trial = f_FE * (E_trial / E_baseline) ** S_E

with E_baseline = 52 000 MPa and G12 fixed at 4 500 MPa. S_E is the recorded CARBON-5A central difference of that
exact FE branch of that specimen's model; sensitivities are never transferred between specimens. The FE vs experiment
frequency difference is shown before and after, per mode, with FIT and HOLDOUT kept separate. A change that improves
one FIT mode and worsens another is reported as MIXED; with a single FIT mode (SP-13) MIXED is not evaluated.

This is an interactive local model-response WHAT-IF: no optimisation, no automatic or recommended E, no identified
material property, no specimen calibration, no G12 change and no extrapolation beyond the archived ±5 %. Mode
identities, pairs and excluded outliers are those of the G2c evidence; nothing is re-paired.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional

from services.archived_sensitivity_evidence import VERIFIED, SensitivityEvidence

E_BASELINE_MPA = 52000.0
G12_FIXED_MPA = 4500.0
MAXIMUM_E_CHANGE = 0.05  # the archived CARBON-5A ±5 % interval; never extrapolated
AVAILABLE = "E_WHAT_IF_AVAILABLE"
BLOCKED = "E_WHAT_IF_BLOCKED"
INCOMPLETE = "E_WHAT_IF_INCOMPLETE"  # a required strict row (FIT or HOLDOUT) is unavailable: no partial preview
# The accepted strict freezes (registration_evidence/<specimen>_registration_reevaluation.json, results.PHYSICAL):
# exactly these rows, roles and experimental <-> FE mode pairs, each once. Selected by the verified evidence specimen.
ACCEPTED_STRICT_ROWS = {
    "SP02": {"R1": ("FIT", 2, 8), "R2": ("FIT", 4, 10), "R3": ("HOLDOUT", 7, 13)},
    "SP13": {"R1": ("FIT", 4, 10), "R2": ("HOLDOUT", 7, 13)},
}
SPECIMEN_TEXT = {"SP02": "SP-02", "SP13": "SP-13"}
REQUIRED_STRICT_ROWS = {row_id: role for row_id, (role, _, _) in ACCEPTED_STRICT_ROWS["SP02"].items()}  # SP-02 (G2d-2)
LABELS = ("LOCAL_MODEL_RESPONSE_WHAT_IF", "NOT_A_RECOMMENDED_E", "NOT_AN_IDENTIFIED_MATERIAL_PROPERTY",
          "NOT_A_SPECIMEN_CALIBRATION")
LABEL_TEXT = " · ".join(LABELS)
CAVEAT = ("Interactive what-if on the archived local sensitivities: f_trial = f_FE · (E_trial / 52 000 MPa)^S_E, "
          "G12 fixed at 4 500 MPa, E_in change limited to the archived ±5 %. It is not a recommended E, an identified "
          "material property or a specimen calibration; pairs, MAC thresholds and outliers are unchanged.")
IMPROVES, WORSENS, UNCHANGED = "improves", "worsens", "unchanged"


@dataclass(frozen=True)
class WhatIfRow:
    row_id: str
    role: str  # FIT | HOLDOUT | NO_STRICT_ROW
    experimental_mode: int
    fe_mode: Optional[int]
    fe_hz: Optional[float]
    experimental_hz: Optional[float]
    trial_hz: Optional[float]
    error_before: Optional[float]  # (f_FE - f_exp) / f_exp
    error_after: Optional[float]  # (f_trial - f_exp) / f_exp
    s_e: Optional[float]
    effect: str  # improves | worsens | unchanged | not predicted
    note: str


@dataclass(frozen=True)
class EWhatIf:
    status: str
    reason: str
    e_change: float
    e_trial_mpa: Optional[float]
    rows: tuple[WhatIfRow, ...] = ()
    fit_summary: str = ""
    holdout_summary: str = ""
    labels: tuple[str, ...] = LABELS
    specimen: Optional[str] = None
    limitations: tuple[str, ...] = ()  # specimen-specific scientific limitations shown with the preview

    @property
    def mixed(self) -> bool:
        return self.fit_summary.startswith("MIXED")


def blocked(reason: str, e_change: float = 0.0) -> EWhatIf:
    return EWhatIf(BLOCKED, reason, e_change, None)


def _effect(before: float, after: float) -> str:
    if abs(after) < abs(before):
        return IMPROVES
    if abs(after) > abs(before):
        return WORSENS
    return UNCHANGED


def _summary(rows, role: str) -> str:
    """Per role only: MIXED compares FIT modes with each other, never FIT with HOLDOUT."""
    selected = [row for row in rows if row.role == role and row.trial_hz is not None]
    if not selected:
        return f"{role}: no predicted row."
    improved = [row.row_id for row in selected if row.effect == IMPROVES]
    worsened = [row.row_id for row in selected if row.effect == WORSENS]
    parts = [f"{len(selected)} {role} row(s)"]
    if improved:
        parts.append("improves " + ", ".join(improved))
    if worsened:
        parts.append("worsens " + ", ".join(worsened))
    if not improved and not worsened:
        parts.append("no change")
    text = "; ".join(parts) + "."
    if role == "FIT" and len(selected) == 1:
        text += " MIXED is not evaluated: only one FIT mode."
    if role == "FIT" and improved and worsened:
        return "MIXED: the change improves one FIT mode and worsens another — " + text
    return text


def _strict_identity_problems(strict, required) -> list[str]:
    """Absent, duplicated, re-classified, re-paired or unexpected strict rows against the accepted freeze."""
    problems = []
    for row_id, (role, experimental_mode, fe_mode) in required.items():
        found = [row for row in strict if row.row_id == row_id]
        if not found:
            problems.append(f"{row_id} ({role}) is absent")
        elif len(found) > 1:
            problems.append(f"{row_id} appears {len(found)} times")
        elif found[0].role != role:
            problems.append(f"{row_id} is {found[0].role}, the accepted role is {role}")
        elif (found[0].experimental_mode, found[0].fe_mode) != (experimental_mode, fe_mode):
            problems.append(f"{row_id} pairs EXP{found[0].experimental_mode} with FE{found[0].fe_mode}, the accepted "
                            f"pair is EXP{experimental_mode} <-> FE{fe_mode}")
    problems += [f"unexpected strict row {row.row_id} ({row.role})" for row in strict if row.row_id not in required]
    return problems


def _required_text(required) -> str:
    return ", ".join(f"{row_id} {role} (EXP{em} <-> FE{fe})" for row_id, (role, em, fe) in required.items())


def _specimen_limitations(specimen: str, evidence_rows) -> tuple[str, ...]:
    """The scientific limits that must stay visible next to the preview of this specimen (from its G2c rows)."""
    if specimen != "SP13":
        return ()
    r1 = next(row for row in evidence_rows if row.row_id == "R1")  # present: the identity check passed
    return (
        "SP-13: only one FIT mode (R1); the accepted strict freeze has observation_sufficient = False.",
        "E_in and G12 cannot be independently identified from SP-13: one FIT frequency cannot separate two "
        "parameters.",
        f"G12 is fixed at {G12_FIXED_MPA:.0f} MPa, but SP-13 R1 also responds to G12 (archived S_G12 = "
        f"{_number(r1.s_g12, '.4f')}); the preview is the E_in response at that fixed G12.",
        "The baseline R1 FE vs experiment frequency difference is "
        f"{_number(r1.relative_frequency_error, '+.2%')}; the archived ±5 % does not close it, and the remaining "
        "difference may have a model-form origin (core, adhesive / ties, boundary conditions, mass distribution).",
        "MIXED is not evaluated (one FIT mode); the HOLDOUT row is reported separately and never offsets FIT.",
        "Predicted improvements are not a material calibration, a validation or an accepted FE result; no E_in or "
        "G12 is recommended, and a predicted difference below the SPEC 8 % calibration gate does not pass that gate.",
        "SP-13 uses only its own recorded sensitivities; SP-02 values are never transferred.",
    )


def e_what_if(evidence: Optional[SensitivityEvidence], e_change: float) -> EWhatIf:
    """The what-if for a relative E_in change (``0.01`` = +1 %), or BLOCKED with the reason."""

    if isinstance(e_change, bool) or not isinstance(e_change, (int, float)) or not math.isfinite(e_change):
        return blocked("the E_in change is not a number.")
    e_change = float(e_change)
    if abs(e_change) > MAXIMUM_E_CHANGE + 1e-12:
        return blocked(f"an E_in change of {e_change:+.1%} is outside the archived ±5 % interval; it is not "
                       "extrapolated.", e_change)
    if evidence is None:
        return blocked("no archived sensitivity evidence has been checked for the current comparison.", e_change)
    if evidence.status != VERIFIED:
        return blocked(f"the archived sensitivity evidence is {evidence.status}; the what-if requires "
                       f"{VERIFIED} (comparison on the accepted physical registration).", e_change)
    required = ACCEPTED_STRICT_ROWS.get(evidence.specimen)
    if required is None:
        return blocked(f"the what-if is implemented for SP-02 and SP-13 only (this evidence is {evidence.specimen}).",
                       e_change)
    name = SPECIMEN_TEXT[evidence.specimen]
    baseline = dict(evidence.baseline)
    if baseline.get("E_in_plane_mpa") != E_BASELINE_MPA or baseline.get("G12_mpa") != G12_FIXED_MPA:
        return blocked("the archived baseline is not E_in 52 000 / G12 4 500 MPa.", e_change)

    factor = 1.0 + e_change
    rows = []
    for row in evidence.rows:
        if row.role == "NO_STRICT_ROW":
            rows.append(WhatIfRow(row.row_id, row.role, row.experimental_mode, row.fe_mode, row.fe_hz,
                                  row.experimental_hz, None, row.relative_frequency_error, None, None,
                                  "not predicted", "excluded outlier preserved; no strict pair, no sensitivity"))
            continue
        if not row.applicable or row.s_e is None or not row.fe_hz or not row.experimental_hz:
            rows.append(WhatIfRow(row.row_id, row.role, row.experimental_mode, row.fe_mode, row.fe_hz,
                                  row.experimental_hz, None, row.relative_frequency_error, None, row.s_e,
                                  "not predicted", f"not applicable: {row.reason}"))
            continue
        trial = row.fe_hz * factor ** row.s_e
        before = (row.fe_hz - row.experimental_hz) / row.experimental_hz
        after = (trial - row.experimental_hz) / row.experimental_hz
        rows.append(WhatIfRow(row.row_id, row.role, row.experimental_mode, row.fe_mode, row.fe_hz,
                              row.experimental_hz, trial, before, after, row.s_e, _effect(before, after),
                              "recorded S_E of the resolved FE branch"))
    rows = tuple(rows)
    strict = [row for row in rows if row.role in ("FIT", "HOLDOUT")]
    problems = _strict_identity_problems(strict, required)
    problems += [f"{row.row_id} ({row.role}): {row.note}" for row in strict if row.trial_hz is None]
    if problems:
        return EWhatIf(INCOMPLETE, f"incomplete {name} strict evidence — {'; '.join(problems)}. Exactly the accepted "
                                   f"strict rows {_required_text(required)} are required; a partial FIT/HOLDOUT "
                                   "preview is not shown.", e_change, None, specimen=evidence.specimen)
    return EWhatIf(AVAILABLE, "", e_change, E_BASELINE_MPA * factor, rows, _summary(rows, "FIT"),
                   _summary(rows, "HOLDOUT"), specimen=evidence.specimen,
                   limitations=_specimen_limitations(evidence.specimen, evidence.rows))


# ----------------------------------------------------------------------------- presentation

TABLE_COLUMNS = ("row", "role", "em", "fe", "ef", "ff", "tf", "before", "after", "se", "effect", "note")
TABLE_TITLES = ("Row", "Role", "Exp. mode", "FE mode", "Exp., Hz", "FE baseline, Hz", "Trial FE, Hz",
                "FE vs exp. before", "FE vs exp. after", "S_E (archived)", "Effect", "Note")
TABLE_WIDTHS = (50, 110, 75, 65, 90, 115, 105, 125, 125, 105, 100, 380)


def _number(value: Optional[float], text: str) -> str:
    return "—" if value is None else format(value, text)


def table_rows(what_if: EWhatIf) -> tuple[tuple[str, ...], ...]:
    return tuple((row.row_id, row.role, str(row.experimental_mode), _number(row.fe_mode, "d"),
                  _number(row.experimental_hz, ".4f"), _number(row.fe_hz, ".4f"), _number(row.trial_hz, ".4f"),
                  _number(row.error_before, "+.2%"), _number(row.error_after, "+.2%"), _number(row.s_e, ".4f"),
                  row.effect, row.note) for row in what_if.rows)


def short_status(what_if: EWhatIf) -> str:
    if what_if.status != AVAILABLE:
        return f"{what_if.status} (see below)"
    text = (f"{what_if.status} · {SPECIMEN_TEXT[what_if.specimen]} · E_in {what_if.e_trial_mpa:.0f} MPa "
            f"({what_if.e_change:+.1%}) · G12 {G12_FIXED_MPA:.0f} MPa fixed")
    if what_if.limitations:
        text += " · one FIT mode, MIXED not evaluated; limitations below"
    return text + (" · MIXED: FIT modes move in opposite directions" if what_if.mixed else "")


def summary_text(what_if: EWhatIf) -> str:
    if what_if.status != AVAILABLE:
        return f"{what_if.status}: {what_if.reason}"
    text = (f"{what_if.status} — {SPECIMEN_TEXT[what_if.specimen]}, E_in {E_BASELINE_MPA:.0f} → "
            f"{what_if.e_trial_mpa:.0f} MPa ({what_if.e_change:+.1%}), G12 fixed {G12_FIXED_MPA:.0f} MPa. FIT: "
            f"{what_if.fit_summary} HOLDOUT (separate): {what_if.holdout_summary}")
    if what_if.limitations:
        text += "\nLimitations:\n" + "\n".join(f"- {line}" for line in what_if.limitations)
    return text
