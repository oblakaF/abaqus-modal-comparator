"""PLATE-WORKBENCH-RC1: the single plate's workbench views and the prepared FE campaign (no Qt, RESEARCH_ONLY).

- ``workbench_chain``: the chain Source UNV → Physical specimen → Scan orientation → FE model → Registration → Mode
  pairs → Parameter estimation, with each link's status, source and blocking reason.
- ``target_breakdown``: the ±10 % engineering goal split into its parts (frequency error, shape identity, D, E / G,
  thickness, suspension, FE model choice). A diagnostic frequency difference is never a material accuracy, and the
  illustrative 3 × CV of the edge thickness is never the plate's established uncertainty.
- ``campaign_specification`` / ``campaign_budget`` / ``campaign_template``: the engineering specification of the next
  FE campaign and its job budget, prepared for ONE separate owner decision. RC1 final correction (owner, 2026-10-30:
  two rubber bands in 261027, four in 261016): ``APPLICABILITY_VARIANTS`` A free-free, B two-band, C four-band
  (history of the boundary conditions only), D force sensor, E thickness model form, and ``applicability_jobs`` with
  each future job's INP, changed and fixed values, outputs, FE-mode identity, stop rules and authorisation. Nothing
  here runs Abaqus, a solver, an LM, Auto-ID or an FE computation; the R6.6 / R6.7 secant variants never replace the
  SPEC §6 S4 central sensitivities.
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


CHAIN_COLUMNS = ("link", "status", "confirmation", "source", "missing and blocking", "diagnostics available")


def workbench_chain(source_confirmed: bool, readiness: rr.RegistrationReadiness, confirmed_pairs: Sequence[str] = (),
                    frozen_registration: Any = None) -> tuple:
    """(link, status, confirmation, source, missing facts and blocking reason, diagnostics available) of each link, in
    order (``CHAIN_COLUMNS``); a link is never shown as further than the links before it allow. The test conditions
    (two rubber bands, the 45° turn) are shown with the scan link but never close it: they are not registration
    evidence."""
    def missing(link):
        return "; ".join(f"{key}: {reason}" for key, reason in link.missing) or "—"

    rows = [("Source UNV", "SHA-256 CONFIRMED" if source_confirmed else "NOT_CONFIRMED",
             "the file on disk = the file read (SHA-256 and size)" if source_confirmed else "not confirmed",
             f"{ps.WORKING_SOURCE} ({ps.WORKING_SOURCE_SHA256[:12]}…), set {ps.WORKING_SET}, fitted dataset 55",
             "—" if source_confirmed else "the file read is not confirmed against the disk; Inspect it again",
             "every record (record 1 included); experimental shapes"),
            ("Physical specimen", ps.PLATE_IDENTITY, "owner, 2026-10-30 (physical identity only)",
             f"{ps.SPECIMEN}: 261016 = 261027; archived record of 2026-10-21", "—",
             "archived mass, plan and edge thickness"),
            ("Test conditions and scan orientation",
             f"{ps.HUMAN_CONFIRMED_SETUP_CHANGE}; scan → plate {readiness.scan_to_plate.status}",
             "two rubber bands, 45° turn, same points and face: HUMAN_CONFIRMED (owner); clockwise: laboratory note; "
             "id-preserving grid turn: DERIVED; 261016 four rubber bands: history",
             "owner 2026-10-30; Read me.txt; the 261016 and 261027 UNV geometries; PSV export (scale, +Z DOF)",
             missing(readiness.scan_to_plate), "conditions table; link of the two series (ids, turn)"),
            ("FE model", f"{ps.INITIAL_FE_MODEL} / {ps.APPLICABILITY_NOT_VERIFIED}",
             "the idealised free-free FE base of this study; its applicability to the 261027 test is not verified",
             "M11 S4R_0875_BASELINE (whole extracted package identity at the read)",
             "suspension (two bands) and force sensor not modelled; FE ↔ physical edges: " + missing(
                 readiness.plate_to_fe),
             "FE shapes; frequency table; spectra; FE-to-FE secant sensitivities")]
    if readiness.status == rr.COMPLETE and frozen_registration is not None:
        registration = ("FROZEN", "owner-authorised", "owner-authorised frozen registration", "—")
    elif readiness.status == rr.COMPLETE:
        registration = (rr.COMPLETE, "evidence complete, not frozen",
                        "evidence complete; freezing is a separate owner decision",
                        "no frozen registration (this program never creates one)")
    else:
        registration = (rr.REGISTRATION_NOT_VERIFIED, "independent evidence incomplete",
                        "plate_registration_readiness",
                        f"{len(readiness.missing)} independent fact(s) missing or refused")
    rows.append(("Registration", *registration, "the readiness table: every fact with its provenance"))
    mac_ok = rr.mac_permitted(readiness, frozen_registration)
    rows.append(("Mode pairs", (f"{len(confirmed_pairs)} CONFIRMED" if confirmed_pairs else "NONE") if mac_ok
                 else BLOCKED, "MAC on a frozen registration" if mac_ok else "none (no MAC computed)",
                 "the comparator with the frozen registration (MAC ≥ 0.80 on measured DOFs)",
                 "—" if mac_ok else "no MAC without a frozen physical registration; frequency proximity is never "
                 "a pair", "frequency-only diagnostic (never a pair)"))
    rows.append(("Parameter estimation", ps.ITERATION_NOT_AUTHORISED if mac_ok and confirmed_pairs else BLOCKED,
                 ps.NOT_IDENTIFIABLE, "the bounded LM campaign (prepared, not authorised)",
                 "needs confirmed pairs, the S4 sensitivities and a separate owner authorisation; every parameter "
                 "NOT_IDENTIFIABLE", "hypothetical design studies (conditional); the prepared campaign"))
    return tuple(rows)


def target_breakdown(first_record_hz: Optional[float], first_fe_hz: Optional[float],
                     registration_status: str = rr.REGISTRATION_NOT_VERIFIED) -> tuple:
    """(part, value, status, note) of the ±10 % goal; nothing is turned into a material accuracy."""
    variants = ps.thickness_variants()
    three = [300 * v["cv"] for v in variants.values()]
    diff = (None if not (first_record_hz and first_fe_hz) else 100 * (first_fe_hz / first_record_hz - 1))
    return (
        ("frequency error (record 1 against the first elastic FE mode)",
         "—" if diff is None else f"{diff:+.2f} %", "FREQUENCY_ONLY_DIAGNOSTIC",
         "frequency proximity of an unregistered pair candidate: not a mode pair and not a material accuracy; "
         "consistent with a freer suspension, which it does not prove"),
        ("shape identity", "not established", "NOT_ESTABLISHED", "no physical registration, so no MAC"),
        ("uncertainty of D (D11 = D22, D66)", "unknown", "UNKNOWN",
         "the conditional 0.30–0.54 % of the design study (provisional Σ_setup) is not the real accuracy"),
        ("uncertainty of E / G", "unknown", "UNKNOWN", "needs D and a thickness map of the whole plate (D-052)"),
        ("thickness", f"{three[0]:.1f}–{three[1]:.1f} % (3 × CV_edges)", "ILLUSTRATIVE",
         "edge readings only; the 0.84 / 0.81 mm reading unresolved; not the plate's established uncertainty"),
        ("suspension", "not quantified", "NOT_QUANTIFIED", "two rubber bands in 261027, four in 261016 (owner); "
         "freer by the owner's explanation; FRF peaks below record 1 (PROVISIONAL); no FE variant with the bands "
         "exists yet"),
        ("FE model choice", "not available", "NOT_AVAILABLE", "model form needs confirmed pairs (leave-one-family-out "
         "half range)"),
        ("experimental registration", "not verified", registration_status,
         "without it no MAC, no mode pair and no fit; see the readiness table"),
        ("±10 % target", "an engineering goal", "NOT_ACHIEVED", "every material parameter NOT_IDENTIFIABLE"),
    )


# ----------------------------------------------------------------------------- the next FE campaign (prepared only)

# RC1 final correction: the suspension variants of the FE-applicability stage (owner, 2026-10-30: two rubber bands
# in 261027, four in 261016). Confirmed values, assumptions and future sensitivity parameters are kept apart; no band
# stiffness is ever set by fitting a measured frequency.
_UNKNOWN_BANDS = ("band stiffness, length and the exact attachment points are NOT recorded: they come from the owner "
                  "or the laboratory, or from a research range declared before the run and labelled RESEARCH_RANGE "
                  "(never from 18.6307 or 33.4491 Hz)")
APPLICABILITY_VARIANTS = (
    {"variant": "A", "name": "free-free reference", "role": "reference",
     "purpose": "the existing M11 S4R_0875_BASELINE (no new job)",
     "values": {"confirmed": ["the M11 model as extracted (package identity)"], "assumptions": ["no support"],
                "future_sensitivity": []},
     "jobs": ()},
    {"variant": "B", "name": "two-band suspension (261027)", "role": "applicability",
     "purpose": "the primary experiment's suspension: does it move the elastic FE modes?",
     "values": {"confirmed": ["two rubber bands (owner, 2026-10-30)",
                              "strings at two upper points along the nodal line of the first mode (laboratory note)"],
                "assumptions": [_UNKNOWN_BANDS],
                "future_sensitivity": ["band axial stiffness: a soft and a stiff end of the declared range"]},
     "jobs": (("PLATE_RC1_P1_B_TWO_BAND_SOFT", "two axial springs at the declared points, soft end"),
              ("PLATE_RC1_P1_B_TWO_BAND_STIFF", "two axial springs at the declared points, stiff end"))},
    {"variant": "C", "name": "four-band historical suspension (261016)", "role": "boundary-condition history",
     "purpose": "only the difference of the boundary conditions between the series; never a material "
                "identification from 33.4491 Hz, and no claim that the bands turn one mode into another before the "
                "shapes are identified",
     "values": {"confirmed": ["four rubber bands (owner, 2026-10-30)", "four corner straps in the 261016 PSV frame "
                              "(M11 §13.3)"],
                "assumptions": [_UNKNOWN_BANDS], "future_sensitivity": ["band axial stiffness: soft and stiff end"]},
     "jobs": (("PLATE_RC1_P1_C_FOUR_BAND_SOFT", "four axial springs at the corner straps, soft end"),
              ("PLATE_RC1_P1_C_FOUR_BAND_STIFF", "four axial springs at the corner straps, stiff end"))},
    {"variant": "D", "name": "force sensor / attachment", "role": "applicability",
     "purpose": "the mass (and rotary inertia, if recorded) of the force sensor at its point",
     "values": {"confirmed": ["a force reference channel (dataset 58 'Force * Velocity')"],
                "assumptions": ["the sensor's point and mass are NOT recorded: needed from the owner or the "
                                "laboratory before this job"],
                "future_sensitivity": ["attachment mass"]},
     "jobs": (("PLATE_RC1_P1_D_SENSOR_MASS", "a point mass at the recorded sensor point"),)},
    {"variant": "E", "name": "thickness / model form", "role": "applicability", "source": "S4R_WEDGE",
     "purpose": "the effect of the measured edge-thickness pattern on the elastic modes (model form, not a field)",
     "values": {"confirmed": [f"{ps._T['n']} archived edge readings (2026-10-21)"],
                "assumptions": ["the interior thickness is not measured: the existing wedge model is a model-form "
                                "alternative, never a fitted or invented thickness map"],
                "future_sensitivity": ["thickness model form"]},
     "jobs": (("PLATE_RC1_P1_E_WEDGE", "the existing S4R_WEDGE model (INP and .dat exist) re-solved with the "
                                       "baseline's output requests so that its shapes can be extracted and tracked"),)},
)
APPLICABILITY_FIXED = ["plan 301 × 300 mm and the 3 mm S4R mesh of the baseline", "the material constants of the "
                       "baseline (E1 = E2, G12, ν12, ρ)", "h = 0.875 mm (except variant E)",
                       "the frequency step and the number of modes of the baseline"]
APPLICABILITY_IDENTITY = ("FE-to-FE: each elastic mode 7–20 of the baseline followed into the job with "
                          "branch_tracker.track_branches on all FE nodes; close pairs by confirm_cluster; the "
                          "suspension's rigid-body modes must separate from the elastic ones; no experimental MAC")
APPLICABILITY_STOP = ["the job does not finish, or the solver reports an error or a negative eigenvalue",
                      "a tracked elastic branch is lost or exchanged → that branch is reported, not re-paired by "
                      "frequency", "the rigid-body (suspension) modes do not separate from the elastic ones",
                      "an input value is not declared before the run (no value is tuned afterwards)"]


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
        "suspension_variants": [f"{v['variant']}. {v['name']}: {v['purpose']}" for v in APPLICABILITY_VARIANTS],
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


def applicability_jobs() -> tuple:
    """The future FE-applicability jobs, one dict each (none is run here; 0 Abaqus solves in this program)."""
    members = {member.member_id: member for member in ps.PLATE_FE_FAMILY}
    jobs = []
    for variant in APPLICABILITY_VARIANTS:
        member_id = variant.get("source", ps.PLATE_FE_FAMILY[0].member_id)
        base = members.get(member_id)
        source = ({"member": member_id, "file": base.inp.relative, "sha256": base.inp.sha256} if base is not None
                  else {"member": member_id, "file": None, "sha256": None})  # not in this family: named only
        for name, setting in variant["jobs"]:
            jobs.append({
                "job": name, "variant": f"{variant['variant']}. {variant['name']}", "source_inp": source,
                "changed": setting, "fixed": APPLICABILITY_FIXED,
                "values": variant["values"],
                "expected_outputs": [f"{name}.odb", f"{name}.dat", f"{name}.msg", f"{name}.sta",
                                     f"extraction package of {name} (manifest.json, geometry.csv, mode_NNNN.csv) by "
                                     "the pinned extractor — Abaqus Python on the new ODB is its own gate"],
                "fe_mode_identity": APPLICABILITY_IDENTITY,
                "stop": APPLICABILITY_STOP,
                "authorisation": "a separate, explicit owner authorisation naming this job (Abaqus solver and "
                                 "extraction); not given",
                "role": variant["role"]})
    return tuple(jobs)


def campaign_budget(include_d12: bool = False) -> tuple:
    """(phase, jobs, prerequisite, content); the counts follow from the specification (no runtime is invented)."""
    n = 3 if include_d12 else 2
    required = [v for v in APPLICABILITY_VARIANTS if v["role"] == "applicability"]
    optional = [v for v in APPLICABILITY_VARIANTS if v["role"] == "boundary-condition history"]
    return (
        ("1a. FE applicability (no registration needed)", sum(len(v["jobs"]) for v in required),
         "the two-band data (or a declared research range), the force-sensor point and mass",
         " + ".join(f"{len(v['jobs'])} {v['variant']} ({v['name']})" for v in required) + "; A exists"),
        ("1b. optional: boundary-condition history", sum(len(v["jobs"]) for v in optional),
         "phase 1a; never a material identification from 33.4491 Hz",
         " + ".join(f"{len(v['jobs'])} {v['variant']} ({v['name']})" for v in optional)),
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
            "applicability_jobs": [{"job": job["job"], "variant": job["variant"], "declared_values": None,
                                    "inp_sha256": None, "odb_sha256": None, "extraction_package_sha256": None,
                                    "authorised": None} for job in applicability_jobs()],
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


__all__ = ["APPLICABILITY_VARIANTS", "BLOCKED", "CHAIN_COLUMNS", "READY", "applicability_jobs", "campaign_budget",
           "campaign_specification", "campaign_template", "render_spectrum", "target_breakdown", "workbench_chain"]
