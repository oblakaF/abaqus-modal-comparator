"""PRIORITY-5A: the Research Results page of the new interface, with no Qt (RESEARCH_ONLY).

It shows the archived PRIORITY-1–4 results read by ``services.research_results_reader``: the mode matching of the
three ROTATED series (every experimental mode, the published status kept), the research / hypothetical MAC matrices
of an optional local research record chosen by the user, the plate's central FE sensitivities with the rank of the
sensitivity matrix, and the inverse parameter study S0 / H1 / H2 checked by real Abaqus solves. Nothing is computed
or started when the page opens: no Abaqus, solver, LM or Auto-ID. A nearest FE frequency is never a pair, a research
or hypothetical MAC is never a confirmed MAC, and S0 / H1 / H2 are never properties of the carbon.
"""

from __future__ import annotations

from typing import Optional

from services import research_results_reader as rr
from services import sp10_fe_research as sf

TITLE = "Research Results"
SUBTITLE = ("Archived research results of PRIORITY-1–4 and PRIORITY-6 for three specimens: viewing only. Nothing is "
            "computed from shapes, no solver is started.")
LABELS_LINE = "RESEARCH_ONLY / HYPOTHETICAL_PAIRING / NOT_A_MATERIAL_PROPERTY"
SCIENTIFIC_STATUS = ("Scientific status (unchanged): M8 GATE NOT_MET · D-077 NO_GLOBAL_PARAMETER_VALUE · production "
                     "Auto-ID BLOCKED · 261027 PHYSICAL_REGISTRATION_NOT_VERIFIED. No row below is a confirmed mode "
                     "pair and no value is a material property.")
LOAD_RECORD = "Load local research record..."
SPECIMEN_ORDER = ("PLATE", "SP-13", "SP-10")
SCENARIO_ORDER = ("S0", "H1", "H2")
MATCHING_HEADERS = ("EXP", "f_EXP (Hz)", "FE candidates (Δf, within 15 %)", "Nearest FE", "f_FE (Hz)", "Δf (%)",
                    "Research MAC", "Close group", "Status", "Reason")
STATUS_MEANING = (
    "CANDIDATE_ONLY: a likely diagnostic correspondence, not a proven pair · AMBIGUOUS_CLUSTER: close or mixed shapes, "
    "one FE mode cannot be assigned · NO_MATCH: no suitable correspondence · FE_SHAPES_UNAVAILABLE: the FE shapes "
    "needed are missing. The nearest FE frequency is never a confirmed pair; MATCH_CONFIRMED is given nowhere.")
SPECIMEN_NOTES = {
    "PLATE": "MAC basis: " + rr.SPECIMENS["PLATE"].mac_basis + ".",
    "SP-13": "MAC basis: " + rr.SPECIMENS["SP-13"].mac_basis + ".",
    "SP-10": "Historical PRIORITY-1 table, archived and unchanged. At the time of PRIORITY-1 no SP-10 FE package was "
             "extracted: its FE frequencies came from the .dat files of its own models only (FE7–FE15), so every row "
             "is FE_SHAPES_UNAVAILABLE and no MAC exists. These statuses describe the FE shapes available then, not "
             "the current state of SP-10: see B. Updated SP-10 FE Results — PRIORITY-6 below.",
}
SP10_HISTORICAL_HEADING = "A. Historical PRIORITY-1 — prior research (FE7–FE15, archived, unchanged)"
SP10_MAC_NOTE = ("The line above is the PRIORITY-1 state. PRIORITY-6 has since extracted the FE shapes of SP-10, but "
                 "SP-10 261029 has no physical registration (PHYSICAL_REGISTRATION_NOT_VERIFIED): no FE↔EXP MAC is "
                 "computed and no mode pair exists.")
MAC_WARNING = ("NOT A CONFIRMED MAC — research / hypothetical shape agreement under an unverified registration. It "
               "never sets a pair, an orientation or a parameter.")
SP10_MAC = "MAC NOT_AVAILABLE — FE shapes not extracted"
NO_RECORD = ("No local research record is loaded. Choose matching_record.json of PRIORITY-1 with Load local research "
             "record... to see the matrices; nothing is searched for.")
SENSITIVITY_HEADERS = ("FE branch", "f0 (Hz)", "s_E1", "s_E2", "s_G12", "s_E (E1 = E2)", "Cluster / tracking")
SENSITIVITY_HIGHLIGHTS = (
    "FE7: high sensitivity to G12 (the first twist).",
    "FE13: high sensitivity to E1 only; FE14: high sensitivity to E2 only.",
    "FE8 / FE9 (and FE20): identity lost in some ±5 % variations (E1 ≠ E2): no central value.",
    "FE15 / FE16: one confirmed cluster term in PRIORITY-2 (mean ln f).",
)
SENSITIVITY_NOTE = ("Central sensitivities s = d ln f / d ln p from six real Abaqus ±5 % solves (PRIORITY-2). Rank and "
                    "condition describe the FE model, not an established accuracy of material parameters.")
SCENARIO_HEADERS = ("Scenario", "E1 (MPa)", "E2 (MPa)", "G12 (MPa)", "Assumed pairs", "Ratios to the baseline",
                    "Beyond the solved ±5 %", "Rank of E1/E2/G12")
BRANCH_HEADERS = ("FE branch", "Baseline FE (Hz)", "LM prediction (Hz)", "Real Abaqus (Hz)", "Approximation error (%)",
                  "FE-to-FE MAC", "Branch status")
DECLARED_HEADERS = ("Assumed pair", "f_EXP (Hz)", "Real Abaqus (Hz)", "Error vs EXP (%)", "LM prediction (Hz)")
DIAGNOSTIC_HEADERS = ("EXP", "f_EXP (Hz)", "Nearest tracked FE", "Real Abaqus (Hz)", "Difference (%)")
INVERSE_NOTE = ("Inverse Parameter Study — Research Only. The three parameter sets come from the bounded LM of "
                "PRIORITY-3 on a log-linear approximation and were each solved once by Abaqus in PRIORITY-4. No "
                "scenario is chosen as the best; none is a property of the carbon.")
CENTROID_NOTE = ("FE15+FE16 is the geometric mean of the two tracked FE branches FE15 and FE16 — a computed subspace "
                 "value, not a separate mode.")
SCENARIO_LIMITS = {
    "S0": "One-mode research problem (EXP1 ↔ FE7, the only CANDIDATE_ONLY row); E1, E2 fixed. G12 lies inside the "
          "solved ±5 %.",
    "H1": "EXP8 ↔ FE15+FE16 is a hypothesis (two-mode subspace 0.92, single MAC 0.43). E1 = E2 imposed (SPEC §5.2); "
          "E far outside the solved ±5 %; two frequencies for two parameters: the small error holds by construction.",
    "H2": "Stress test: EXP7 ↔ FE14 had research MAC 0.79 < 0.80 and |Δf| 15.5 % > 15 %. E1 = E2 imposed; E far "
          "outside the solved ±5 %; two frequencies for two parameters: the small error holds by construction.",
}
PLATE_ONLY = "The FE parameter sensitivities and the inverse parameter study exist only for PLATE."

# ----------------------------------------------------------------------------- PRIORITY-7: SP-10 FE results of PRIORITY-6
SP10_TITLE = "B. Updated SP-10 FE Results — PRIORITY-6"
SP10_STATUS = ("RESEARCH_ONLY / FREQUENCY_ONLY_DIAGNOSTIC / NOT_A_MATERIAL_PROPERTY · SP-10 261029 "
               + sf.REGISTRATION_STATUS)
SP10_RANGE_NOTE = ("FE7–FE15 is the range of PRIORITY-1. PRIORITY-6 added FE16–FE25, ten modes beyond that range "
                   "(226.947–457.613 Hz; FE15 itself is 220.044 Hz). The frequencies are the ODB's EIGFREQ history; "
                   "each equals the job's .dat to its printed five significant digits.")
SP10_FE_HEADERS = ("FE №", "f_FE (Hz)", "Step", "Shape extracted", "Source", "Status")
SP10_DIAGNOSTIC_HEADERS = ("EXP №", "f_EXP (Hz)", "Nearest FE", "f_FE (Hz)", "Δf (%)", "Second candidate", "Δf (%)",
                           "Status")
SP10_DIAGNOSTIC_NOTE = ("Every experimental record of polymax_bravo (12, the f_EXP of the historical table) against the "
                        "19 FE frequencies of PRIORITY-6, nearest by |Δf|, Δf (%) = 100 × (f_FE − f_EXP) / f_EXP. "
                        "A nearest frequency is not a modal correspondence: no MAC, registration, orientation, "
                        "assignment or permutation is made.")
SP10_LIMITS = ("Limits: no physical registration of SP-10 exists, so its FE and experimental shapes can only be viewed "
               "independently (Workspace, Analysis: UNPAIRED SHAPES). No E1 / E2 / G12 or other material value comes "
               "from these frequencies. The extracted package (about 3.1 GB) is not part of the program; this page "
               "never reads it.")


def _thousands(number: int) -> str:
    return f"{number:,}".replace(",", " ")


def sp10_identity_lines(results: sf.Sp10FeResults) -> tuple:
    instances = ", ".join(f"{name} {_thousands(count)}" for name, count in sorted(results.instances.items()))
    lines = [f"FE model: {results.model} · modal step {results.step} · {len(results.fe_modes)} elastic modes "
             f"FE{results.fe_modes[0].number}–FE{results.fe_modes[-1].number}, "
             f"{results.fe_modes[0].frequency_hz:.3f}–{results.fe_modes[-1].frequency_hz:.3f} Hz",
             f"ODB SHA-256: {results.odb_sha256}",
             f"FE manifest SHA-256: {results.fe_manifest_sha256}",
             f"Geometry: {_thousands(results.nodes)} nodes ({instances})",
             f"Shapes: extracted in PRIORITY-6 for every mode (package {results.package_bytes / 1e9:.2f} GB, outside "
             f"the program) · extractor SHA-256 {results.extractor_sha256[:12]}…",
             f"Experimental series: {sf.SERIES} · modal set {sf.MODAL_SET}, {sf.EXPERIMENTAL_RECORDS} records · "
             f"experimental file SHA-256 {sf.EXPERIMENT_SHA256[:12]}…"]
    lines += [f"Source: {path} · SHA-256 {sha[:12]}… · research commit {commit}"
              for path, sha, commit in results.files.values()]
    return tuple(lines)


def sp10_fe_rows(results: sf.Sp10FeResults) -> tuple:
    return tuple((f"FE{m.number}", f"{m.frequency_hz:.4f}", results.step, f"yes — {m.shape_file}",
                  f"ODB EIGFREQ history (.dat {m.dat_hz:g})",
                  "added in PRIORITY-6 (FE16–FE25)" if m.added else "PRIORITY-1 range (FE7–FE15)")
                 for m in results.fe_modes)


def sp10_added_rows(results: sf.Sp10FeResults) -> tuple:
    return tuple(i for i, m in enumerate(results.fe_modes) if m.added)


def _signed(value: float) -> str:
    return f"{value:+.2f}"


def sp10_diagnostic_rows(rows) -> tuple:
    out = []
    for r in rows:
        notes = [sf.PROXIMITY_ONLY]
        if r.group:
            notes.append(f"close group {r.group}")
        if r.nearest_in_added_range:
            notes.append(f"FE{r.nearest.fe} added in PRIORITY-6")
        out.append((f"EXP{r.exp_no}", f"{r.f_exp_hz:.4f}", f"FE{r.nearest.fe}", f"{r.nearest.frequency_hz:.4f}",
                    _signed(r.nearest.df_percent), f"FE{r.second.fe}" if r.second else "—",
                    _signed(r.second.df_percent) if r.second else "—", " · ".join(notes)))
    return tuple(out)


def sp10_group_rows(rows) -> tuple:
    """Row indices of the close groups (highlighted)."""
    return tuple(i for i, r in enumerate(rows) if r.group)


def sp10_focus_lines(rows) -> tuple:
    """EXP11 and EXP12: FE frequencies that came into the available range with PRIORITY-6."""
    lines = []
    for r in rows:
        if r.exp_no in (11, 12):
            lines.append(f"EXP{r.exp_no} {r.f_exp_hz:.4f} Hz → nearest FE{r.nearest.fe} {r.nearest.frequency_hz:.4f} Hz "
                         f"({_signed(r.nearest.df_percent)} %): FE{r.nearest.fe} is in the range added by PRIORITY-6; "
                         f"PRIORITY-1 had no FE frequency within 15 %. {sf.PROXIMITY_ONLY}.")
    return tuple(lines)


def sp10_group_lines() -> tuple:
    return tuple(f"Close group: {'/'.join(f'EXP{e}' for e in exps)} near the FE spectrum "
                 f"{'/'.join(f'FE{f}' for f in fes)} — no automatic assignment or permutation"
                 for exps, fes in sf.CLOSE_GROUPS)


def _f(value, digits: int = 4) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value) if value not in (None, "") else "—"


def matching_rows(snapshot: rr.Snapshot, specimen: str) -> tuple:
    return tuple((f"EXP{r.exp_no}", f"{r.f_exp_hz:.4f}", r.fe_candidates, r.nearest_fe, r.f_fe_hz or "—",
                  r.df_percent or "—", r.research_mac or "—", r.cluster, r.status, r.reason)
                 for r in snapshot.matching[specimen])


def ambiguous_rows(snapshot: rr.Snapshot, specimen: str) -> tuple:
    """Row indices with a close group or an ambiguous assignment (highlighted on the page)."""
    return tuple(i for i, r in enumerate(snapshot.matching[specimen]) if r.ambiguous)


def identity_lines(snapshot: rr.Snapshot, specimen: str) -> tuple:
    spec = rr.SPECIMENS[specimen]
    files = [k for k in snapshot.files if k == spec.matching or (specimen == "PLATE" and k not in
                                                                 ("PLATE_MATCHING", "SP13_MATCHING", "SP10_MATCHING"))]
    lines = [f"Specimen: {specimen} · series {spec.series} · {spec.modes} experimental modes",
             f"Experimental source SHA-256 of the research: {spec.experiment_sha256[:16]}…"]
    lines += [f"Source: {snapshot.files[k][0]} · SHA-256 {snapshot.files[k][1][:12]}… · research commit "
              f"{snapshot.files[k][2]}" for k in files]
    lines.append("Status of the research: " + LABELS_LINE)
    return tuple(lines)


def sensitivity_rows(snapshot: rr.Snapshot) -> tuple:
    rows = []
    for x in snapshot.sensitivities:
        cluster = "confirmed cluster term (PRIORITY-2)" if x.cluster else ""
        rows.append((x.term, f"{x.f0_hz:.5f}", *[_f(x.s[p]) if x.s[p] is not None else "lost" for p in
                                                 ("E1", "E2", "G12")],
                     _f(x.s_e) if x.s_e is not None else "lost", "; ".join(v for v in (cluster, x.tracking) if v)))
    return tuple(rows)


def rank_lines(snapshot: rr.Snapshot) -> tuple:
    return tuple(f"{' / '.join(r['parameters'])}: rank {r['rank']}, condition {r['condition']:.2f} over {r['terms']} "
                 f"tracked terms" for r in (snapshot.rank_full, snapshot.rank_restricted))


def scenario_rows(snapshot: rr.Snapshot) -> tuple:
    return tuple((s.key, f"{s.E1:g}", f"{s.E2:g}", f"{s.G12:g}", s.pairs, s.ratios, s.beyond_linear_range, s.rank)
                 for s in snapshot.scenarios)


def scenario_view(snapshot: rr.Snapshot, key: str) -> dict:
    detail = rr.scenario_detail(snapshot, key)
    s = detail["scenario"]
    return {
        "parameters": f"{key}: E1 = {s.E1:g} MPa, E2 = {s.E2:g} MPa, G12 = {s.G12:g} MPa · LM status {s.status} · "
                      f"{s.labels}",
        "pairs": f"Assumed experimental correspondences (hypotheses, never confirmed pairs): {s.pairs}",
        "branches": tuple((b["term"], _f(b["f_baseline_hz"], 5), _f(b["f_lm_hz"], 5), _f(b["f_abaqus_hz"], 5),
                           _f(b["surrogate_error_percent"], 4), b["fe_fe_mac"], b["status"])
                          for b in detail["branches"]),
        "declared": tuple((f"{d['exp']} ↔ {d['fe_branch']}", d["f_exp_hz"], _f(d["f_abaqus_hz"], 5),
                           _f(d["error_percent"], 4), _f(d["f_lm_hz"], 5)) for d in detail["declared"]),
        "diagnostic": tuple((d["exp"], d["f_exp_hz"], d["fe_branch"], _f(d["f_abaqus_hz"], 5),
                             _f(d["error_percent"], 2)) for d in detail["diagnostic"]),
        "limits": SCENARIO_LIMITS[key] + " " + s.note + ".",
        "centroid": any("+" in b["term"] for b in detail["branches"]),
    }


def mac_view(record: Optional[rr.LocalRecord], specimen: str) -> dict:
    """What the MAC section shows for one specimen: a matrix, NOT_AVAILABLE (SP-10) or no record."""
    if specimen == "SP-10":
        return {"state": "not_available", "text": SP10_MAC}
    if record is None:
        return {"state": "no_record", "text": NO_RECORD}
    matrix = record.matrices[specimen]
    return {"state": "matrix", "matrix": matrix, "text": f"{matrix.basis}.",
            "rows": tuple(f"EXP{n} {hz:.2f} Hz" for n, hz in matrix.experimental),
            "cols": tuple(f"FE{m}" for m in matrix.fe_modes)}


def cell_text(record: rr.LocalRecord, specimen: str, row: int, column: int) -> str:
    matrix = record.matrices[specimen]
    number, hz = matrix.experimental[row]
    value = matrix.values[row][column]
    kind = "RESEARCH" if specimen == "PLATE" else "HYPOTHETICAL_SAME_POINTS"
    return (f"EXP{number} ({hz:.4f} Hz) × FE{matrix.fe_modes[column]}: {kind} MAC {value:.4f} — not a confirmed "
            "MAC and not a pair")


def record_lines(record: rr.LocalRecord) -> tuple:
    return (f"Local research record: {record.path}", f"SHA-256 of the record read: {record.sha256}") + record.checks


# ----------------------------------------------------------------------------- PLATE-0875-CURRENT-RESEARCH-VIEW-01
# The current plate research results (corrected scan geometry, plate README §24–§26) beside the historical
# PRIORITY-1–4 tables, which stay as archived and are named historical.
PLATE_CURRENT_TITLE = "A. Current plate research results — corrected scan geometry (plate README §24–§26)"
PLATE_CURRENT_STATUS = " / ".join(rr.PLATE_COMPARISON_LABELS)
PLATE_CURRENT_NOTE = (
    "CURRENT RESEARCH RESULT — four FE models against the 11 experimental records of 261027, with the scan-point "
    "positions taken from the instrument record. A separate, hash-verified research snapshot: display only. It is "
    "not registration evidence, not an identification input and not a pairing record. No row is a confirmed mode "
    "pair, no value is a material property, and no model is chosen as the best.")
PLATE_HISTORICAL_HEADING = ("B. Historical PRIORITY-1–4 plate results — superseded scan geometry (archived, "
                            "unchanged)")
PLATE_HISTORICAL_MATCHING = (
    rr.HISTORICAL_PLATE_GEOMETRY + " The research MAC values, the statuses and the reasons of this table were "
    "published with those positions. The current values are in section A above.")
PLATE_HISTORICAL_MAC = (
    rr.HISTORICAL_PLATE_GEOMETRY + " A local research record of PRIORITY-1 (matching_record.json) holds the plate "
    "matrix computed with those positions: a historical matrix. The current matrices are in section A above.")
PLATE_HISTORICAL_INVERSE = (
    "HISTORICAL — the assumed pairs of S0 / H1 / H2 were taken from the research MAC of the superseded scan geometry "
    "(EXP1 ↔ FE7 at 0.91, EXP8 ↔ FE15+FE16 with subspace 0.92, EXP7 ↔ FE14 at 0.79). The parameter sets and the FE "
    "frequencies of the scenarios do not depend on the point positions and are unchanged. With the corrected positions "
    "a common lower E, as in H1, leaves EXP5 and EXP9 12.0 % and 12.8 % too low at research MAC 0.99 and 0.98 (plate "
    "README §24.6). The scenarios are kept as archived; they are not current results.")
PLATE_SENSITIVITY_UNAFFECTED = ("FE-only quantities: the central sensitivities do not use the scan-point positions "
                                "and are not affected by the superseded geometry.")
PLATE_MODEL_TITLES = {"BASELINE": "Baseline", "THICKNESS_ONLY": "Thickness only", "DIRECTIONAL_ONLY": "Directional "
                      "stiffness only", "COMBINED": "Combined"}
PLATE_MODEL_HEADERS = ("Model", "Thickness", "E1 (MPa)", "E2 (MPa)", "G12 (MPa)", "ν12", "Mass (g)", "FE input SHA-256",
                       "Origin of the FE result")
PLATE_SUMMARY_HEADERS = ("Metric",) + tuple(PLATE_MODEL_TITLES[k] for k in rr.PLATE_MODELS)
PLATE_SHORT_TITLES = {"BASELINE": "Baseline", "THICKNESS_ONLY": "Thickness", "DIRECTIONAL_ONLY": "Directional",
                      "COMBINED": "Combined"}
PLATE_FREQUENCY_HEADERS = ("EXP", "f_EXP (Hz)") + tuple(
    f"{PLATE_SHORT_TITLES[k]}{column}" for k in rr.PLATE_MODELS for column in (": FE, Hz", ": Δf %"))
PLATE_MAC_HEADERS = ("EXP", "f_EXP (Hz)") + tuple(PLATE_MODEL_TITLES[k] for k in rr.PLATE_MODELS) + ("Note",)
PLATE_MAC_TABLE_NOTE = "Each cell: the first-ranked FE mode of the record and its research MAC."
PLATE_RECORD_HEADERS = ("EXP", "f_EXP (Hz)", "Corresp. FE", "f_FE (Hz)", "Δf (%)", "MAC, corresp.", "First FE",
                        "MAC, first", "Range, 59 scenarios", "Note")
PLATE_RECORD_NOTE = ("Corresp. FE: the corresponding FE mode (class order). First FE: the first-ranked FE mode by research "
                     "MAC. Range: the first-ranked research MAC over the 59 declared shift and rotation scenarios, and in "
                     "how many of them the first-ranked mode is unchanged.")
PLATE_TRACKING_HEADERS = ("Directional only: FE", "f (Hz)", "Combined: FE", "f (Hz)", "FE-to-FE MAC", "Status")
PLATE_CORRESPONDENCE_NOTE = ("Corresponding FE: the FE mode of the record's class order (plate README §22.6) — a research "
                             "correspondence fixed without any EXP MAC, never a confirmed pair. Δf (%) = 100 × (f_FE − "
                             "f_EXP) / f_EXP. ± 5 % and 0.80 are the existing descriptive levels, not gates.")
PLATE_MAC_NOTE = ("RESEARCH MAC — NOT A CONFIRMED MAC. Complex MAC of each record with the FE shape sampled at the "
                  "corrected scan positions (placement D, CONVENTION_ONLY). It never sets a pair, an orientation or a "
                  "parameter.")
PLATE_REFUSED = "The current plate research snapshot is not shown: "


def plate_identity_lines(comparison: rr.PlateComparison) -> tuple:
    specimen = comparison.specimen
    lines = [f"Research snapshot: {comparison.path} · SHA-256 {comparison.sha256} (verified when this page was read)",
             f"Specimen: {specimen['key']} · series {specimen['series']} · modal set {specimen.get('modal_set', '—')} · "
             f"{specimen['records']} experimental records · experimental source SHA-256 "
             f"{specimen['experiment_sha256'][:16]}…",
             f"Documented in: {comparison.documented_in}",
             "Use: " + comparison.status["use"],
             "Scientific status (unchanged): " + " · ".join(comparison.status["gates"])]
    lines += [f"Source result: {path} · SHA-256 {sha[:12]}…" for _name, path, sha in comparison.sources]
    return tuple(lines)


def plate_geometry_lines(comparison: rr.PlateComparison) -> tuple:
    g = comparison.geometry
    left, right, bottom, top = g["gaps_mm_left_right_bottom_top"]
    old = g["superseded"]
    return (f"Corrected scan window (session {g['session_of_the_instrument_record']}, {g['pixel_normalisation']} "
            f"reading): {g['window_mm'][0]:.1f} × {g['window_mm'][1]:.1f} mm on the {g['plate_plan_mm'][0]:g} × "
            f"{g['plate_plan_mm'][1]:g} mm plate; gaps to the edges left {left:.1f}, right {right:.1f}, bottom "
            f"{bottom:.1f}, top {top:.1f} mm · placement {g['placement']}",
            f"Transfer 261016 → 261027 — {g['transfer_261016_to_261027']}.",
            f"Superseded geometry (historical results below): {old['window_mm'][0]:.1f} × {old['window_mm'][1]:.1f} mm; "
            f"points displaced by up to {old['max_point_shift_mm']:.1f} mm — {old['reason']}.",
            f"Corrected reconstruction: {g['reconstruction_file']} · SHA-256 {g['reconstruction_sha256'][:12]}…")


def plate_model_rows(comparison: rr.PlateComparison) -> tuple:
    rows = []
    for key in rr.PLATE_MODELS:
        m = comparison.models[key]
        i = m.inputs
        rows.append((PLATE_MODEL_TITLES[key], i["thickness"], f"{i['E1_MPa']:g}", f"{i['E2_MPa']:g}", f"{i['G12_MPa']:g}",
                     f"{i['nu12']:g}", f"{i['mass_g']:.3f}", m.identity["inp_sha256"][:12] + "…",
                     f"{m.origin} (README §{m.readme})"))
    return tuple(rows)


def _list(values) -> str:
    return ", ".join(f"EXP{v}" for v in values) if values else "none"


def _numbers(values) -> str:
    return ", ".join(str(v) for v in values) if values else "none"


def plate_summary_rows(comparison: rr.PlateComparison) -> tuple:
    s = [comparison.models[k].summary for k in rr.PLATE_MODELS]
    return (("Mean research MAC, first-ranked FE mode",) + tuple(f"{x['mean_mac_first']:.3f}" for x in s),
            ("Records at research MAC ≥ 0.80",) + tuple(str(len(x["records_mac_ge_0_80"])) for x in s),
            ("Records below 0.80 (EXP №)",) + tuple(_numbers(x["records_mac_below_0_80"]) for x in s),
            ("First-ranked FE mode = corresponding FE mode",) + tuple(f"{x['first_ranked_is_corresponding']} of 11"
                                                                        for x in s),
            ("Mean |Δf| of the corresponding FE modes (%)",) + tuple(f"{x['mean_abs_frequency_error_pct']:.2f}"
                                                                      for x in s),
            ("Largest |Δf| (%)",) + tuple(f"{x['max_abs_frequency_error_pct']:.2f}" for x in s),
            ("Records outside ± 5 % (EXP №)",) + tuple(_numbers(x["records_outside_5_pct"]) for x in s))


def plate_frequency_rows(comparison: rr.PlateComparison) -> tuple:
    rows = []
    for i, hz in enumerate(comparison.exp_hz):
        row = [f"EXP{i + 1}", f"{hz:.4f}"]
        for key in rr.PLATE_MODELS:
            r = comparison.models[key].records[i]
            row += [f"FE{r.corresponding_fe}  {r.corresponding_hz:.2f}", _signed(r.frequency_error_pct)]
        rows.append(tuple(row))
    return tuple(rows)


def plate_outside_cells(comparison: rr.PlateComparison) -> tuple:
    """(row, column) of every Δf cell of the frequency table that is outside ± 5 % (highlighted)."""
    return tuple((i, 3 + 2 * n) for n, key in enumerate(rr.PLATE_MODELS)
                 for i, r in enumerate(comparison.models[key].records)
                 if abs(r.frequency_error_pct) > rr.PLATE_FREQUENCY_LEVEL)


def _record_notes(comparison: rr.PlateComparison, exp: int) -> list:
    notes = []
    if exp in comparison.unresolved_records:
        notes.append("UNRESOLVED: explained by none of the four models")
    b = comparison.criteria["combined_model_readme_26"]["B_all_class_frequencies_within_5_pct"]
    if exp in b["records_outside"]:
        notes.append("combined model outside ± 5 %")
    if exp in b["correspondence_not_confirmed_by_tracking"]:
        notes.append("combined model: FE branch LOST in tracking — correspondence by frequency position only")
    return notes


def plate_mac_rows(comparison: rr.PlateComparison) -> tuple:
    rows = []
    for i, hz in enumerate(comparison.exp_hz):
        row = [f"EXP{i + 1}", f"{hz:.4f}"]
        for key in rr.PLATE_MODELS:
            r = comparison.models[key].records[i]
            row.append(f"FE{r.first_fe}: {r.mac_first:.2f}")
        row.append(" · ".join(_record_notes(comparison, i + 1)) or "—")
        rows.append(tuple(row))
    return tuple(rows)


def plate_low_cells(comparison: rr.PlateComparison) -> tuple:
    """(row, column) of every first-ranked MAC of the comparison table that is below 0.80 (highlighted)."""
    return tuple((i, 2 + n) for n, key in enumerate(rr.PLATE_MODELS)
                 for i, r in enumerate(comparison.models[key].records) if r.mac_first < rr.PLATE_MAC_LEVEL)


def plate_record_rows(comparison: rr.PlateComparison, key: str) -> tuple:
    rows = []
    for r in comparison.models[key].records:
        notes = []
        if r.mac_first < rr.PLATE_MAC_LEVEL:
            notes.append("research MAC below 0.80")
        if abs(r.frequency_error_pct) > rr.PLATE_FREQUENCY_LEVEL:
            notes.append("outside ± 5 %")
        if r.first_fe != r.corresponding_fe:
            notes.append("first-ranked FE mode is not the corresponding one")
        if r.exp in comparison.unresolved_records:
            notes.append("UNRESOLVED in all four models")
        if key == "COMBINED" and r.exp in comparison.criteria["combined_model_readme_26"][
                "B_all_class_frequencies_within_5_pct"]["correspondence_not_confirmed_by_tracking"]:
            notes.append("FE branch LOST in tracking — correspondence by frequency position only")
        rows.append((f"EXP{r.exp}", f"{r.f_exp_hz:.4f}", f"FE{r.corresponding_fe}", f"{r.corresponding_hz:.3f}",
                     _signed(r.frequency_error_pct), f"{r.mac_corresponding:.2f}", f"FE{r.first_fe}",
                     f"{r.mac_first:.2f}", f"{r.mac_range[0]:.2f}–{r.mac_range[1]:.2f} ({r.first_unchanged})",
                     " · ".join(notes) or "—"))
    return tuple(rows)


def plate_model_line(comparison: rr.PlateComparison, key: str) -> str:
    m = comparison.models[key]
    i = m.inputs
    return (f"{m.title}: thickness {i['thickness']} · E1 = {i['E1_MPa']:g} MPa, E2 = {i['E2_MPa']:g} MPa, G12 = "
            f"{i['G12_MPa']:g} MPa, ν12 = {i['nu12']:g} · mass {i['mass_g']:.3f} g · {i['mesh']} · {i['boundary']} · "
            f"FE7–FE20: {m.fe_hz[0]:.3f}–{m.fe_hz[-1]:.3f} Hz · {m.origin}")


def plate_mac_view(comparison: rr.PlateComparison, key: str) -> dict:
    """The research MAC matrix of one model in the form MacHeatmap shows."""
    m = comparison.models[key]
    matrix = rr.MacMatrix("PLATE", PLATE_MAC_NOTE, tuple((k + 1, hz) for k, hz in enumerate(comparison.exp_hz)),
                          comparison.fe_modes, m.mac)
    return {"state": "matrix", "matrix": matrix, "text": PLATE_MAC_NOTE,
            "rows": tuple(f"EXP{n} {hz:.2f} Hz" for n, hz in matrix.experimental),
            "cols": tuple(f"FE{mode}\n{hz:.1f}" for mode, hz in zip(comparison.fe_modes, m.fe_hz))}


def plate_cell_text(comparison: rr.PlateComparison, key: str, row: int, column: int) -> str:
    m = comparison.models[key]
    return (f"{PLATE_MODEL_TITLES[key]} · EXP{row + 1} ({comparison.exp_hz[row]:.4f} Hz) × FE{comparison.fe_modes[column]} "
            f"({m.fe_hz[column]:.3f} Hz): RESEARCH MAC {m.mac[row][column]:.4f} — not a confirmed MAC and not a pair")


def plate_tracking_rows(comparison: rr.PlateComparison) -> tuple:
    return tuple((f"FE{r['reference_fe']}", f"{r['reference_hz']:.3f}", f"FE{r['target_fe']}", f"{r['target_hz']:.3f}",
                  f"{r['mac']:.3f}", "tracked" if r["status"] == "TRACKED" else
                  "LOST — reported as lost, not replaced by another mode") for r in comparison.tracking["rows"])


def plate_lost_rows(comparison: rr.PlateComparison) -> tuple:
    return tuple(i for i, r in enumerate(comparison.tracking["rows"]) if r["status"] == "LOST")


def plate_tracking_line(comparison: rr.PlateComparison) -> str:
    t = comparison.tracking
    return (f"Branch tracking, combined against directional only (FE-to-FE MAC of the whole field, tracked at "
            f"{t['minimum_mac_for_tracked']:.2f} or more): {t['tracked']} of {len(t['rows'])} tracked; LOST: "
            + ", ".join(f"FE{m}" for m in t["lost"]) + ".")


def plate_criteria_lines(comparison: rr.PlateComparison) -> tuple:
    d = comparison.criteria["directional_test_readme_25"]
    c = comparison.criteria["combined_model_readme_26"]
    b = c["B_all_class_frequencies_within_5_pct"]
    a = c["A_shapes_of_records_3_4_7"]
    shapes = "; ".join(f"EXP{k}: {v['directional_only']:.2f} → {v['combined']:.2f} "
                       f"({'improved' if v['improved'] else 'NOT improved'}, "
                       f"{'described' if v['described'] else 'NOT described'})" for k, v in sorted(a.items(), key=lambda x: int(x[0])))
    return ("Directional stiffness only — the three criteria written before the solve (README §25): "
            + ", ".join(f"{k.split('_', 1)[1].replace('_', ' ')} {v}" for k, v in d.items()) + ".",
            f"Combined model — criterion 'all class frequencies within ± 5 %' (README §26): {b['verdict']} — "
            f"outside: {_list(b['records_outside'])}; largest |Δf| {b['max_abs_error_pct']:.2f} %.",
            f"Combined model — shapes of EXP3, EXP4, EXP7 against directional only: {shapes}.",
            f"Combined model — deterioration of the well-matched records: {c['C_no_deterioration']['verdict']}; the two "
            f"effects are not additive (frequency: {_list(c['D_interaction']['non_additive_frequency_records'])}; MAC: "
            f"{_list(c['D_interaction']['non_additive_mac_records'])}).",
            "Combined model overall: improves the shapes "
            + ("" if c["overall"]["improves_the_model"] else "(NOT met) ")
            + ("and keeps" if c["overall"]["keeps_frequency_agreement_of_25"] else "but does NOT keep")
            + " the frequency agreement of the directional-only model.")


def plate_limit_lines(comparison: rr.PlateComparison) -> tuple:
    return tuple(comparison.limitations)


__all__ = ["LOAD_RECORD", "MAC_WARNING", "PLATE_CURRENT_TITLE", "PLATE_HISTORICAL_HEADING", "SP10_TITLE", "TITLE",
           "plate_cell_text", "plate_criteria_lines", "plate_frequency_rows", "plate_geometry_lines",
           "plate_identity_lines", "plate_limit_lines", "plate_mac_rows", "plate_mac_view", "plate_model_rows",
           "plate_record_rows", "plate_summary_rows", "plate_tracking_rows",
           "ambiguous_rows", "cell_text", "identity_lines",
           "mac_view", "matching_rows", "rank_lines", "record_lines", "scenario_rows", "scenario_view",
           "sensitivity_rows", "sp10_diagnostic_rows", "sp10_fe_rows", "sp10_focus_lines", "sp10_group_lines",
           "sp10_group_rows", "sp10_identity_lines"]
