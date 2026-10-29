"""PLATE-WORKBENCH-RC1: the single plate's workbench views and the prepared FE campaign (no Qt, RESEARCH_ONLY).

- ``workbench_chain``: the chain Source UNV → Physical specimen → Scan orientation → FE model → Registration → Mode
  pairs → Parameter estimation, with each link's status, source and blocking reason.
- ``target_breakdown``: the ±10 % engineering goal split into its parts (frequency error, shape identity, D, E / G,
  thickness, suspension, FE model choice). A diagnostic frequency difference is never a material accuracy, and the
  illustrative 3 × CV of the edge thickness is never the plate's established uncertainty.
- ``campaign_specification`` / ``campaign_budget`` / ``campaign_template``: the engineering specification of the next
  FE campaign and its job budget, prepared for ONE separate owner decision. Nothing here runs Abaqus, a solver, an
  LM, Auto-ID or an FE computation; the R6.6 / R6.7 secant variants never replace the SPEC §6 S4 central
  sensitivities.
- ``render_spectrum``: measured and FE frequencies on one frequency axis, as two independent rows (no line joins
  them: frequency only, never a mode pair).
"""

from __future__ import annotations

import io
from typing import Any, Optional, Sequence

from services import plate_registration_readiness as rr
from services import plate_study as ps

BLOCKED = "BLOCKED"
READY = "READY"


def workbench_chain(source_confirmed: bool, readiness: rr.RegistrationReadiness, confirmed_pairs: Sequence[str] = (),
                    frozen_registration: Any = None) -> tuple:
    """(link, status, source, blocking reason) of each link, in order; a link is never shown as further than the
    links before it allow."""
    rows = [("Source UNV", "SHA-256 CONFIRMED" if source_confirmed else "NOT_CONFIRMED",
             f"{ps.WORKING_SOURCE} ({ps.WORKING_SOURCE_SHA256[:12]}…), set {ps.WORKING_SET}, fitted dataset 55",
             "—" if source_confirmed else "the file read is not confirmed against the disk; Inspect it again"),
            ("Physical specimen", ps.PLATE_IDENTITY, f"{ps.SPECIMEN}: owner statement 2026-10-30 (261016 = 261027); "
             "archived record of 2026-10-21", "—"),
            ("Scan orientation", readiness.scan_to_plate.status, "lab note (45° clockwise); PSV export (scale, +Z "
             "DOF); no camera frame of the plate session",
             "; ".join(reason for _key, reason in readiness.scan_to_plate.missing) or "—"),
            ("FE model", f"{ps.INITIAL_FE_MODEL} / {ps.APPLICABILITY_NOT_VERIFIED}",
             "M11 S4R_0875_BASELINE (whole extracted package identity at the read)",
             "applicability to the 261027 suspension and excitation not verified; FE ↔ physical edges: "
             + ("; ".join(reason for _key, reason in readiness.plate_to_fe.missing) or "evidence complete"))]
    if readiness.status == rr.COMPLETE and frozen_registration is not None:
        registration = ("FROZEN", "owner-authorised frozen registration", "—")
    elif readiness.status == rr.COMPLETE:
        registration = (rr.COMPLETE, "evidence complete; freezing is a separate owner decision",
                        "no frozen registration (this program never creates one)")
    else:
        registration = (rr.REGISTRATION_NOT_VERIFIED, "plate_registration_readiness",
                        f"{len(readiness.missing)} independent fact(s) missing or refused")
    rows.append(("Registration", *registration))
    mac_ok = rr.mac_permitted(readiness, frozen_registration)
    rows.append(("Mode pairs", (f"{len(confirmed_pairs)} CONFIRMED" if confirmed_pairs else "NONE") if mac_ok
                 else BLOCKED, "the comparator with the frozen registration (MAC ≥ 0.80 on measured DOFs)",
                 "—" if mac_ok else "no MAC without a frozen physical registration; frequency proximity is never "
                 "a pair"))
    rows.append(("Parameter estimation", ps.ITERATION_NOT_AUTHORISED if mac_ok and confirmed_pairs else BLOCKED,
                 "the bounded LM campaign (prepared, not authorised)",
                 "needs confirmed pairs, the S4 sensitivities and a separate owner authorisation; every parameter "
                 "NOT_IDENTIFIABLE"))
    return tuple(rows)


def target_breakdown(first_record_hz: Optional[float], first_fe_hz: Optional[float]) -> tuple:
    """(part, value, status, note) of the ±10 % goal; nothing is turned into a material accuracy."""
    variants = ps.thickness_variants()
    three = [300 * v["cv"] for v in variants.values()]
    diff = (None if not (first_record_hz and first_fe_hz) else 100 * (first_fe_hz / first_record_hz - 1))
    return (
        ("frequency error (record 1 against the first elastic FE mode)",
         "—" if diff is None else f"{diff:+.2f} %", "DIAGNOSTIC_ONLY",
         "frequency proximity of an unregistered pair candidate: not a mode pair and not a material accuracy"),
        ("shape identity", "not established", "NOT_ESTABLISHED", "no physical registration, so no MAC"),
        ("uncertainty of D (D11 = D22, D66)", "unknown", "UNKNOWN",
         "the conditional 0.30–0.54 % of the design study (provisional Σ_setup) is not the real accuracy"),
        ("uncertainty of E / G", "unknown", "UNKNOWN", "needs D and a thickness map of the whole plate (D-052)"),
        ("thickness", f"{three[0]:.1f}–{three[1]:.1f} % (3 × CV_edges)", "ILLUSTRATIVE",
         "edge readings only; the 0.84 / 0.81 mm reading unresolved; not the plate's established uncertainty"),
        ("suspension", "not quantified", "NOT_QUANTIFIED", "FRF peaks below record 1 (PROVISIONAL); a setup "
         "dependence between the series is suspected, not proven"),
        ("FE model choice", "not available", "NOT_AVAILABLE", "model form needs confirmed pairs (leave-one-family-out "
         "half range)"),
        ("±10 % target", "an engineering goal", "NOT_ACHIEVED", "every material parameter NOT_IDENTIFIABLE"),
    )


# ----------------------------------------------------------------------------- the next FE campaign (prepared only)

def campaign_specification() -> dict:
    base = ps.PLATE_FE_FAMILY[0]
    return {
        "status": "PREPARED_NOT_AUTHORISED",
        "result_kind": ("a specimen calibration parameter: the effective bending stiffness of PLATE-300x300x1mm, never "
                        "a material constant"),
        "result_labels": [ps.RESEARCH_ONLY, ps.NOT_A_MATERIAL_PROPERTY, "NOT_TRANSFERABLE"],
        "base_model": {"member": base.member_id, "inp_sha256": base.inp.sha256,
                       "extraction_manifest_sha256": base.manifest.sha256 if base.manifest else None,
                       "mesh": base.elements, "boundary": "free-free (baseline)"},
        "parameters_varied": [
            {"name": "D (balanced, D11 = D22)", "how": "E1 and E2 scaled together at fixed h, ν12, ρ"},
            {"name": "D66", "how": "G12 at fixed h"},
        ],
        "conditional_parameters": [
            {"name": "D12", "condition": "only if the design study with the S4 sensitivities is FULL_RANK at rcond "
             "1e-3 with it (D-051); ν12 0.05 fixed otherwise"},
            {"name": "D11 ≠ D22 (E1 ≠ E2)", "condition": "not before traceable material axes (SPEC v1.1 §5.2)"},
        ],
        "fixed": ["E3, G13, G23, ν13, ν23 at the baseline", "plan 301 × 300 mm and the 3 mm S4R mesh",
                  "h = 0.875 mm in the FE (thickness is not an FE nuisance column of a bare plate, D-052)"],
        "mass_and_surface": (f"ρ·h kept at the archived areal mass {ps.areal_mass_kg_m2():.4f} kg/m² (the baseline's "
                             "1.3108 kg/m² agrees to the record's resolution); the scanned surface and the S4R "
                             "mid-surface are related by the frozen registration only"),
        "thickness_non_uniformity": ("uniform baseline; a thickness-field variant only from a measured map of the "
                                     "whole plate; the existing wedge model is a model-form sensitivity, never a "
                                     "fitted field; E / G add 3·cv_h of that map (D-052)"),
        "suspension_variants": ["free-free (baseline, exists)",
                                "two-point string suspension at the recorded points: soft and stiff bracket of the "
                                "band stiffness (needs the points, lengths and band data)",
                                "force-sensor / shaker attachment mass at its recorded point (the PSV reference is a "
                                "force channel; needs the point and the mass)"],
        "tracked_modes": ("every elastic FE mode 7–20, followed into each job with branch_tracker.track_branches "
                          "(STRICT_IDENTIFICATION_PAIRING); close pairs examined with confirm_cluster; a confirmed "
                          "cluster (FE 15 + 16) enters as one term (mean ln f); the near-degenerate FE 8 / 9 only as "
                          "one confirmed cluster term, never as two rows"),
        "central_sensitivities": ("SPEC §6 S4: central ±5 % in ln p for each varied parameter (2 jobs each) and the "
                                  "±2.5 % linearity repeat (2 jobs each); the R6.6 / R6.7 secants (−10 % / ×2) do "
                                  "not replace them"),
        "fit_and_holdout": ("declared after the frozen registration and before any fit: FIT = the confirmed terms the "
                            "design study needs for FULL_RANK, HOLDOUT = every other confirmed pair; record 1 is "
                            "kept; frozen in the campaign record"),
        "permutation_and_cluster_control": ("a job whose branch tracking refuses a term (SET_REFUSED, lost branch, "
                                            "exchange inside a cluster) removes that term; no re-pairing by "
                                            "frequency"),
        "stop_and_refusal": ["no frozen physical registration → no campaign",
                             "MAC < 0.80 on measured DOFs → the pair is not confirmed",
                             "RANK_DEFICIENT before optimisation → LM NOT_RUN (SPEC §6 S5)",
                             "branch tracking lost in a sensitivity job → the term is removed",
                             "LM not converged, a bound reached or the solve budget spent → no estimate",
                             "pattern / Birge / robustness failures → the existing verdicts",
                             "family consistency NOT_AVAILABLE for one plate (D-044) → at best RESEARCH_CANDIDATE_ONLY",
                             "M8 GATE NOT_MET and D-077 NO_GLOBAL_PARAMETER_VALUE unchanged"],
        "not_run_here": "no Abaqus, solver, LM, Auto-ID or FE computation",
    }


def campaign_budget(include_d12: bool = False) -> tuple:
    """(phase, jobs, prerequisite, content); the counts follow from the specification (no runtime is invented)."""
    n = 3 if include_d12 else 2
    return (
        ("1. FE applicability (no registration needed)", 4,
         "suspension points / bands, force-sensor point and mass",
         "2 suspension brackets + 1 attachment mass + 1 thickness model-form (wedge) job, each with extraction"),
        ("2. SPEC §6 S4 central sensitivities", 2 * n, "a frozen physical registration and confirmed pairs",
         f"±5 % in ln p for {n} parameters"),
        ("3. linearity repeat", 2 * n, "phase 2", f"±2.5 % in ln p for {n} parameters"),
        ("4. bounded LM", 12, "phases 2–3, FIT / HOLDOUT frozen, owner authorisation",
         "at most 12 FE solves (the solve budget the owner authorises)"),
    )


def campaign_template() -> dict:
    """A reproducible campaign record to fill in, not a campaign: every decision field is empty."""
    return {"schema": "plate-campaign-template/v1", "specimen": ps.SPECIMEN, "series": ps.SERIES,
            "authorisation": {"owner_decision": None, "date": None, "solve_budget": None},
            "registration": {"frozen_registration_hash": None, "evidence_status": rr.REGISTRATION_NOT_VERIFIED},
            "base_model": campaign_specification()["base_model"],
            "jobs": [{"phase": phase, "count": jobs, "inp_sha256": None, "odb_sha256": None,
                      "extraction_package_sha256": None} for phase, jobs, _pre, _c in campaign_budget()],
            "fit_terms": None, "holdout_terms": None, "result": None}


# ----------------------------------------------------------------------------- frequency spectra (no pairs)

def render_spectrum(measured_hz: Sequence[float], fe_hz: Sequence[float], title_measured: str,
                    title_fe: str) -> bytes:
    """PNG of the measured and FE frequencies on one axis, as two independent rows (matplotlib, no pyplot)."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    figure = Figure(figsize=(9.0, 3.0), dpi=110)
    FigureCanvasAgg(figure)
    axes = figure.add_subplot(1, 1, 1)
    top = max([*measured_hz, *fe_hz, 1.0]) * 1.05
    for row, values, colour in ((1.0, measured_hz, "#1f5fbf"), (0.0, fe_hz, "#c0392b")):
        axes.vlines(values, row - 0.3, row + 0.3, colors=colour, linewidth=1.6)
        for value in values:  # vertical labels: close frequencies stay readable
            axes.annotate(f"{value:.1f}", (value, row + 0.33), ha="center", va="bottom", rotation=90, fontsize=6,
                          color=colour)
    axes.set_yticks([0.0, 1.0], [title_fe, title_measured], fontsize=8)
    axes.set_ylim(-0.5, 1.95)
    axes.set_xlim(0.0, top)
    axes.set_xlabel("Frequency (Hz)", fontsize=8)
    axes.tick_params(axis="x", labelsize=7)
    axes.set_title("Frequency only — NOT mode pairs (no registration, no MAC)", fontsize=9)
    figure.tight_layout()
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png")
    return buffer.getvalue()


__all__ = ["BLOCKED", "READY", "campaign_budget", "campaign_specification", "campaign_template", "render_spectrum",
           "target_breakdown", "workbench_chain"]
