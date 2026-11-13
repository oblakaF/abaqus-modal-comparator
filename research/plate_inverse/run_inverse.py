"""PRIORITY-3 — the first bounded inverse fit of the M11 plate parameters (RESEARCH_ONLY / HYPOTHETICAL_PAIRING /
NOT_A_MATERIAL_PROPERTY).

The optimiser is the project's ``services.identification_step.run_bounded_lm`` (no second optimiser). The forward model
is a LINEAR APPROXIMATION in logarithms built from the PRIORITY-2 central sensitivities (real Abaqus ±5 % solves):

    ln f_t(p) = ln f_t0 + Σ_j s_tj · ln(p_j / p_j0),   p0 = (E1, E2, G12) = (56 000, 56 000, 5 000) MPa

Each evaluation is an evaluation of that approximation, never an Abaqus solve; no new solve is run. Real FE results are
used only where they exist (the baseline and the six ±5 % variants). Residuals r_t = (ln f_t(p) − ln f_EXP) / σ with the
provisional σ = 0.003 of the design studies (a scale, not a measured uncertainty). MAC is never a term of the objective.

Scenarios (declared before any fit; pairings are HYPOTHESES, none is a confirmed pair):
  S0  EXP1 ↔ FE7, G12 only (E1, E2 fixed)
  H1  EXP1 ↔ FE7 and EXP8 ↔ the FE15/FE16 cluster centroid (geometric mean), E1 = E2 = E and G12
  H2  EXP1 ↔ FE7 and EXP7 ↔ FE14, E1 = E2 = E and G12 — a stress test: research MAC 0.79 < 0.80 and |Δf| 15.5 % > 15 %
Bounds (declared): every parameter in [0.5, 2] × its baseline value.

Usage: python research/plate_inverse/run_inverse.py [--out <dir>]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research" / "real_modal_matching"))

from services import identification_step as st  # noqa: E402

SENSITIVITIES = REPO / "docs" / "research" / "plate_s4_central" / "CENTRAL_SENSITIVITIES.csv"
SENSITIVITIES_SHA256 = "50136be13b38021251feb9c8f4fb74cfb052801bbeeba99e9b7f3efd90864ee8"
# PLATE-CANDIDATES: the fit itself lives in services.plate_candidate_results (moved there unchanged), so the
# interface and this script run one implementation
from services.plate_candidate_results import (BOUND_FACTOR, LABELS, LINEAR_RANGE, P0, RCOND, SCENARIOS,  # noqa: E402,F401
                                              SETTINGS, SIGMA_LN, Scenario, fit, full_parameters, jacobian_rows,
                                              predict, rank_report)


class Refused(RuntimeError):
    pass


def load_sensitivities(path: Path = SENSITIVITIES, expected: str = SENSITIVITIES_SHA256) -> dict:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected:
        raise Refused(f"{path.name}: SHA-256 {digest[:12]}… is not the PRIORITY-2 table {expected[:12]}…")
    out = {}
    with open(path, newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["s_E1"] in ("", None) or row["s_G12"] in ("", None):
                continue  # a branch that lost identity has no central value; nothing is guessed
            out[row["term"]] = {"f0": float(row["f_baseline_hz"]), "E1": float(row["s_E1"]),
                                "E2": float(row["s_E2"]), "G12": float(row["s_G12"]),
                                "real": {("G12", 4750.0): row["f_G12_minus"], ("G12", 5250.0): row["f_G12_plus"],
                                         ("E1", 53200.0): row["f_E1_minus"], ("E1", 58800.0): row["f_E1_plus"],
                                         ("E2", 53200.0): row["f_E2_minus"], ("E2", 58800.0): row["f_E2_plus"]}}
    return out


def main(out: Path) -> dict:
    import inputs as I  # fail-closed: refuses a UNV whose SHA-256 is not the provenance map's

    out.mkdir(parents=True, exist_ok=True)
    sens = load_sensitivities()
    plate = I.read_experimental("PLATE")
    f_exp = {int(m.number): float(m.frequency_hz) for m in plate.modes}
    results = [fit(s, sens, f_exp) for s in SCENARIOS]
    # real FE check where a real solve exists: G12 = 4750 MPa (PRIORITY-2 job M11_S4_G12_MINUS)
    s0 = sens["FE7"]
    real_4750 = float(s0["real"][("G12", 4750.0)])
    check = {"G12_MPa": 4750.0, "FE7_real_abaqus_hz": real_4750,
             "FE7_linear_approximation_hz": predict(sens, "FE7", {**P0, "G12": 4750.0}),
             "EXP1_hz": f_exp[1], "real_error_vs_EXP1_percent": 100 * (real_4750 / f_exp[1] - 1)}
    # E1 / E2 / G12 rank of the observations that are actually available
    available = {"CANDIDATE_ONLY rows (EXP1 ↔ FE7)": ["FE7"], "H1 rows": ["FE7", "FE15+FE16"],
                 "H2 rows": ["FE7", "FE14"], "H1 ∪ H2 rows (not a scenario)": ["FE7", "FE15+FE16", "FE14"],
                 "every tracked FE term (model capacity, not observations)": list(sens)}
    ranks = {k: {**rank_report(jacobian_rows(sens, v, ("E1", "E2", "G12"))), "terms": v}
             for k, v in available.items()}
    # every tracked FE term at each solution (FE predictions only: never a pair with a record)
    predictions = []
    for r in results:
        if "parameters" in r:
            for term in sens:
                predictions.append({"scenario": r["scenario"], "term": term, "f0": sens[term]["f0"],
                                    "f_at_solution": predict(sens, term, r["parameters"])})
    record = {"labels": LABELS, "sensitivities_sha256": SENSITIVITIES_SHA256, "experiment_sha256": plate.sha256,
              "experimental_hz": f_exp, "scenarios": results, "real_fe_check": check, "ranks": ranks,
              "fe_predictions": predictions,
              "settings": {"sigma_ln": SIGMA_LN, "bounds": BOUND_FACTOR, "lm": SETTINGS.__dict__}}
    (out / "inverse_record.json").write_text(json.dumps(record, indent=1, ensure_ascii=False, default=str),
                                              encoding="utf-8")
    write_outputs(out, record)
    write_report(out, record)
    return record


def write_outputs(out: Path, record: dict) -> None:
    rows = []
    for r in record["scenarios"]:
        p = r.get("parameters", {})
        rows.append({"scenario": r["scenario"], "pairs": "; ".join(r["pairs"]),
                     "fitted": "+".join(r["fitted_parameters"]), "status": r["status"],
                     "E1_MPa": round(p["E1"], 1) if p else "", "E2_MPa": round(p["E2"], 1) if p else "",
                     "G12_MPa": round(p["G12"], 1) if p else "",
                     "ratios": "; ".join(f"{k} ×{v:.4f}" for k, v in r.get("ratios", {}).items()),
                     "at_bound": ", ".join(r.get("at_bound", [])) or "none",
                     "beyond_linear_range": "; ".join(f"{k} ×{v:.3f}" for k, v in
                                                      r.get("extrapolation_beyond_5_percent", {}).items()) or "none",
                     "rank_fitted": r["rank_fitted"]["rank"], "condition_fitted": round(r["rank_fitted"]["condition"],
                                                                                        3),
                     "rank_E1_E2_G12": r["rank_E1_E2_G12"]["rank"], "objective": r.get("objective", ""),
                     "evaluations": r.get("evaluations", ""), "labels": " / ".join(LABELS),
                     "note": r.get("reason") or r["note"]})
    with open(out / "PLATE_INVERSE_SCENARIOS.csv", "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    res = []
    for r in record["scenarios"]:
        for x in r.get("residuals", []):
            res.append({"scenario": r["scenario"], "exp": f"EXP{x['exp']}", "fe_term": x["term"],
                        "f_exp_hz": round(x["f_exp"], 4), "f_fe_baseline_hz": round(x["f0"], 4),
                        "f_fe_at_solution_hz": round(x["f_fit"], 4),
                        "error_before_percent": round(x["error_before_percent"], 3),
                        "error_after_percent": round(x["error_after_percent"], 4),
                        "source": "LINEAR_APPROXIMATION (not an Abaqus solve)"})
    c = record["real_fe_check"]
    res.append({"scenario": "real FE check", "exp": "EXP1", "fe_term": "FE7", "f_exp_hz": round(c["EXP1_hz"], 4),
                "f_fe_baseline_hz": 19.0722, "f_fe_at_solution_hz": round(c["FE7_real_abaqus_hz"], 5),
                "error_before_percent": round(100 * (19.07217 / c["EXP1_hz"] - 1), 3),
                "error_after_percent": round(c["real_error_vs_EXP1_percent"], 4),
                "source": "REAL ABAQUS SOLVE M11_S4_G12_MINUS (G12 = 4750 MPa)"})
    with open(out / "PLATE_FREQUENCY_RESIDUALS.csv", "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(res[0]))
        writer.writeheader()
        writer.writerows(res)


def write_report(out: Path, record: dict) -> None:
    L = []
    add = L.append
    add("# PLATE_INVERSE_RESULTS — first bounded inverse fit of the M11 plate (RESEARCH_ONLY / HYPOTHETICAL_PAIRING / "
        "NOT_A_MATERIAL_PROPERTY)")
    add("")
    add("| Сценарий | Использованные моды | E1 (МПа) | E2 (МПа) | G12 (МПа) | Ошибка частот | Ранг | Ограничения |")
    add("|---|---|---|---|---|---|---|---|")
    for r in record["scenarios"]:
        p = r.get("parameters")
        if not p:
            add(f"| {r['scenario']} | {'; '.join(r['pairs'])} | — | — | — | — | {r['rank_fitted']['rank']} | "
                f"{r.get('reason', r['status'])} |")
            continue
        errors = "; ".join(f"EXP{x['exp']} {x['error_before_percent']:+.2f} % → {x['error_after_percent']:+.4f} %"
                           for x in r["residuals"])
        fixed_e = "E" not in r["fitted_parameters"]
        limits = ["linear approximation (not an Abaqus solve)", "hypothetical pairing"]
        if fixed_e:
            limits.append("E1, E2 fixed (not fitted)")
        else:
            limits.append("E1 = E2 imposed (SPEC v1.1 §5.2); E1 / E2 not separable: rank "
                          f"{r['rank_E1_E2_G12']['rank']} of 3 on these modes")
        if r["extrapolation_beyond_5_percent"]:
            limits.append("EXTRAPOLATION beyond ±5 %: " + ", ".join(f"{k} ×{v:.3f}" for k, v in
                                                                    r["extrapolation_beyond_5_percent"].items()))
        if r["at_bound"]:
            limits.append("at bound: " + ", ".join(r["at_bound"]))
        if len(r["pairs"]) == len(r["fitted_parameters"]):
            limits.append("square system: zero residual by construction, no test of fit")
        add(f"| {r['scenario']} | {'; '.join(r['pairs'])} | {p['E1']:.0f}{' (fixed)' if fixed_e else ''} | "
            f"{p['E2']:.0f}{' (fixed)' if fixed_e else ''} | {p['G12']:.0f} | {errors} | "
            f"{r['rank_fitted']['rank']} of {len(r['fitted_parameters'])} (cond {r['rank_fitted']['condition']:.2f}) | "
            f"{'; '.join(limits)} |")
    add("")
    add("Every number above is RESEARCH_ONLY / HYPOTHETICAL_PAIRING / NOT_A_MATERIAL_PROPERTY: the pairings are "
        "hypotheses (no admissible physical registration exists for 261027), and the forward model is the "
        "log-linear approximation of the PRIORITY-2 central sensitivities, not a new Abaqus solve.")
    add("")
    c = record["real_fe_check"]
    add("## Real FE result against the approximation")
    add("")
    add(f"- **Real Abaqus solve** `M11_S4_G12_MINUS` (G12 = 4 750 MPa, PRIORITY-2): FE7 = {c['FE7_real_abaqus_hz']:.5f} Hz.")
    add(f"- **Linear approximation** at the same point: {c['FE7_linear_approximation_hz']:.5f} Hz (difference "
        f"{100 * (c['FE7_linear_approximation_hz'] / c['FE7_real_abaqus_hz'] - 1):+.4f} %).")
    add(f"- EXP1 = {c['EXP1_hz']:.4f} Hz: the real FE7 at 4 750 MPa is {c['real_error_vs_EXP1_percent']:+.3f} % from it "
        f"(baseline {100 * (19.07217 / c['EXP1_hz'] - 1):+.2f} %).")
    s0 = next(r for r in record["scenarios"] if r["scenario"] == "S0")
    add(f"- S0 lies inside the solved ±5 % range (G12 ×{s0['ratios']['G12']:.4f}): an interpolation between real "
        "solves. H1 / H2 need E far outside it: an extrapolation that only a real solve at that point can check.")
    add("")
    add("## Scenarios in detail")
    for r in record["scenarios"]:
        add("")
        add(f"### {r['scenario']} — {'; '.join(r['pairs'])}")
        add("")
        add(f"- Note: {r['note']}.")
        add(f"- Status of `run_bounded_lm`: **{r['status']}**; evaluations of the approximation "
            f"{r.get('evaluations', '—')}; objective Φ = {r.get('objective', float('nan')):.3g}; at bound: "
            f"{', '.join(r.get('at_bound', [])) or 'none'}.")
        if "ratios" in r:
            add("- Solution: " + ", ".join(f"{k} ×{v:.4f}" for k, v in r["ratios"].items()) + "; direct solve of "
                "the same equations: " + ", ".join(f"{k} ×{v:.4f}" for k, v in r["direct_solution_ratios"].items())
                + ".")
            if r.get("local_sd_ln"):
                add("- Local sd(ln p) with the provisional σ 0.3 % (a scale, not the real accuracy): "
                    + ", ".join(f"{100 * v:.2f} %" for v in r["local_sd_ln"]) + ".")
        add(f"- Rank of the fitted parameters: {r['rank_fitted']['rank']}, singular values "
            f"{', '.join(f'{v:.4f}' for v in r['rank_fitted']['singular_values'])}; rank for E1 / E2 / G12 on the same "
            f"modes: {r['rank_E1_E2_G12']['rank']}.")
    add("")
    add("## H1 against H2 (no scenario is chosen)")
    add("")
    h1 = next(r for r in record["scenarios"] if r["scenario"] == "H1")
    h2 = next(r for r in record["scenarios"] if r["scenario"] == "H2")
    if "ratios" in h1 and "ratios" in h2:
        add(f"- E: H1 ×{h1['ratios']['E']:.4f}, H2 ×{h2['ratios']['E']:.4f} (difference "
            f"{100 * (h2['ratios']['E'] / h1['ratios']['E'] - 1):+.1f} %); G12: H1 ×{h1['ratios']['G12']:.4f}, H2 "
            f"×{h2['ratios']['G12']:.4f}.")
    add("- G12 is set by FE7 in both (s_G12 0.483, s_E 0.016), so it barely depends on the second assignment; E is "
        "set entirely by the second, hypothetical assignment. Both ask for E about 22–25 % below the baseline, far "
        "outside the ±5 % that was solved.")
    add("- Both are square systems (two modes, two parameters): their zero residual says nothing about which "
        "assignment is right. No scenario is selected by frequency error or MAC.")
    if "parameters" in h1 and "parameters" in h2:
        sens = load_sensitivities()
        f7, f8 = record["experimental_hz"][7], record["experimental_hz"][8]
        a = predict(sens, "FE14", h1["parameters"])
        b = predict(sens, "FE15+FE16", h2["parameters"])
        add(f"- Cross-check of the two hypotheses (not used to choose): at the H1 solution FE14 = {a:.2f} Hz against "
            f"EXP7 {f7:.2f} Hz ({100 * (a / f7 - 1):+.1f} %); at the H2 solution FE15+FE16 = {b:.2f} Hz against EXP8 "
            f"{f8:.2f} Hz ({100 * (b / f8 - 1):+.1f} %). The two hypotheses ask for nearly the same E shift; this is "
            "their mutual consistency inside the approximation, not evidence for either assignment.")
    add("")
    add("## E1, E2, G12: rank of the observations actually available")
    add("")
    add("| Observation set | Terms | Rank (of 3) | Condition |")
    add("|---|---|---|---|")
    for k, v in record["ranks"].items():
        add(f"| {k} | {', '.join(v['terms'])} | {v['rank']} | {v['condition']:.2f} |")
    add("")
    add("- With EXP1 ↔ FE7 alone (the only CANDIDATE_ONLY row) only G12 is determined.")
    add("- H1 and H2 each give rank 2: E1 and E2 move together on FE7 and FE15+16, and FE14 informs E2 only. No "
        "independent E1 / E2 is given.")
    add("- The union of H1 and H2 would reach rank 3 only by joining two unconfirmed hypotheses; it is not fitted.")
    add("")
    add("## FE predictions at each solution (FE values only; never paired with a record)")
    add("")
    add("| Term | f0 Hz | " + " | ".join(r["scenario"] for r in record["scenarios"] if "parameters" in r) + " |")
    add("|---|---|" + "---|" * sum(1 for r in record["scenarios"] if "parameters" in r))
    terms = list(dict.fromkeys(x["term"] for x in record["fe_predictions"]))
    by = {(x["scenario"], x["term"]): x for x in record["fe_predictions"]}
    for t in terms:
        add(f"| {t} | {by[(record['scenarios'][0]['scenario'], t)]['f0']:.3f} | " + " | ".join(
            f"{by[(r['scenario'], t)]['f_at_solution']:.3f}" for r in record["scenarios"] if "parameters" in r) + " |")
    add("")
    add("Experimental 261027 records for reference: " + ", ".join(f"EXP{k} {v:.4f}" for k, v in
                                                                  record["experimental_hz"].items()) + " Hz.")
    add("")
    add("## Settings")
    add("")
    add(f"`identification_step.run_bounded_lm`, ln p, bounds [0.5, 2] × baseline, σ = {SIGMA_LN} (scale), "
        f"settings {json.dumps(record['settings']['lm'])}. Sensitivity table SHA-256 `{SENSITIVITIES_SHA256}`; "
        f"experiment SHA-256 `{record['experiment_sha256']}` (refused on any other content). No Abaqus solve, no "
        "production Auto-ID, no change to SPEC, DECISIONS, STATUS or registrations.")
    (out / "PLATE_INVERSE_RESULTS.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=r"D:\git\abaqus-modal-comparator-work\research\PLATE_INVERSE_R1_202610")
    rec = main(Path(parser.parse_args().out))
    for r in rec["scenarios"]:
        print(r["scenario"], r["status"], {k: round(v, 1) for k, v in r.get("parameters", {}).items()},
              r.get("ratios"), r.get("at_bound"), r["rank_fitted"], r.get("objective"))
    print(json.dumps(rec["real_fe_check"], indent=1))
    print(json.dumps({k: (v["rank"], round(v["condition"], 2)) for k, v in rec["ranks"].items()}, ensure_ascii=False))
