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

TITLE = "Research Results"
SUBTITLE = ("Archived research results of PRIORITY-1–4 for three specimens: viewing only. Nothing is computed, no "
            "solver is started.")
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
    "SP-10": "No extracted SP-10 FE package: FE frequencies come from the .dat files of its own models only, so every "
             "row is FE_SHAPES_UNAVAILABLE and no MAC exists.",
}
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


__all__ = ["LOAD_RECORD", "MAC_WARNING", "TITLE", "ambiguous_rows", "cell_text", "identity_lines", "mac_view",
           "matching_rows", "rank_lines", "record_lines", "scenario_rows", "scenario_view", "sensitivity_rows"]
