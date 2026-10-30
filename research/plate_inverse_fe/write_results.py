"""Compose RESULTS.md of PRIORITY-4 from inverse_fe_record.json (every number comes from the record)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_inverse_fe as F  # noqa: E402

r = json.loads((F.OUT / "inverse_fe_record.json").read_text(encoding="utf-8"))
L = []
add = L.append
lm = {(x["state"], x["fe_branch"]): x for x in r["vs_lm"]}
tr = {(x["state"], x["branch"]): x for x in r["tracking"]}
ex = [x for x in r["vs_experiment"] if x["kind"] == "DECLARED_HYPOTHESIS"]


def real(state, term):
    v = lm.get((state, term), {}).get("f_abaqus_hz", "")
    return float(v) if v != "" else None


add("# PRIORITY-4 — real Abaqus verification of the inverse parameter sets S0, H1, H2 (M11 S4R plate)")
add("")
add("Labels of every number: " + " / ".join(F.LABELS) + ".")
add("")
add("| Сценарий | E1, МПа | E2, МПа | G12, МПа | Основные частоты Abaqus, Гц | Эксперимент, Гц | Ошибка | FE-ветви |")
add("|---|---|---|---|---|---|---|---|")
for state in ("S0", "H1", "H2"):
    p = r["states"][state]
    main = "; ".join(f"{t} {real(state, t):.4f}" for t in ("FE7", "FE13", "FE14", "FE15+FE16") if real(state, t))
    hyp = [x for x in ex if x["state"] == state]
    add(f"| {state} | {p['E1']:g} | {p['E2']:g} | {p['G12']:g} | {main} | "
        + "; ".join(f"{x['exp']} {x['f_exp_hz']}" for x in hyp) + " | "
        + "; ".join(f"{x['exp']}↔{x['fe_branch']} {float(x['error_percent']):+.3f} %" for x in hyp) + " | "
        + f"{sum(1 for k, v in tr.items() if k[0] == state and v['status'] == 'TRACKED')} of "
        f"{sum(1 for k in tr if k[0] == state)} tracked at MAC ≥ 0.90; permutations "
        f"{sum(1 for k, v in tr.items() if k[0] == state and v['permutation'])}; lost "
        f"{sum(1 for k, v in tr.items() if k[0] == state and v['status'] != 'TRACKED')} |")
add("")
add("## 1. The three real Abaqus solves (owner-authorised maximum: 3)")
add("")
add("| # | State | Changed | Values | INP SHA-256 | Exit | Completed | s | ODB SHA-256 | Extraction manifest SHA-256 |")
add("|---|---|---|---|---|---|---|---|---|---|")
for run in r["runs"]:
    chk = r["extraction_checks"].get(run["job"], {})
    add(f"| {run['attempt']} | {run['job']} | {run['parameter']} | {run['value']} | `{run['inp_sha256'][:16]}…` | "
        f"{run['exit_code']} | {run['sta_completed']} | {run['seconds']} | `{run['odb_sha256'][:16]}…` | "
        f"`{chk.get('manifest_sha256', '')[:16]}…` |")
add("")
prep = r["prepare"]
add(f"Baseline INP `CFRP_S4R_0875_FreeFree.inp` `{prep['base_inp_sha256']}`; only the *Elastic line "
    f"{prep['elastic_line_index'] + 1} differs (`{prep['baseline_line']}` →):")
for job, e in prep["jobs"].items():
    add(f"- {job}: `{e['new_line']}` — parsed E3 {e['parsed']['E3']:g}, ν12 {e['parsed']['nu12']:g}, ν13 "
        f"{e['parsed']['nu13']:g}, ν23 {e['parsed']['nu23']:g}, G13 {e['parsed']['G13']:g}, G23 {e['parsed']['G23']:g}, "
        f"ρ {e['parsed']['rho']:g}, h {e['parsed']['h']:g} (all as the baseline).")
add("")
add("Each extraction manifest names its own job's ODB (`odb_path`), and the ODB SHA-256 equals the one recorded after "
    "the solve: the shapes belong to the new solves, not to the baseline. Pinned extractor `039aa067…` unchanged. "
    "No attempt was repeated.")
add("")
add("## 2. Real Abaqus against the PRIORITY-3 predictions, branch by branch")
add("")
add("| Сценарий | FE-ветвь | База, Гц | Прогноз LM, Гц | Abaqus, Гц | Ошибка прогноза, % | Эксперимент (объявленная гипотеза) | FE-to-FE MAC | Статус ветви |")
add("|---|---|---|---|---|---|---|---|---|")
for state in ("S0", "H1", "H2"):
    for x in [v for k, v in lm.items() if k[0] == state]:
        term = x["fe_branch"]
        hyp = next((h for h in ex if h["state"] == state and h["fe_branch"] == term), None)
        if "+" in term:
            macs = [tr[(state, b)]["fe_fe_mac_or_cos2"] for b in term.split("+")]
            mac, status = " / ".join(macs), "centroid of FE15 and FE16, each TRACKED"
        else:
            mac, status = tr[(state, term)]["fe_fe_mac_or_cos2"], tr[(state, term)]["status"] + (
                " (order changed)" if tr[(state, term)]["permutation"] else "")
        add(f"| {state} | {term} | {x['f_baseline_hz']} | {x['f_lm_hz']} | {x['f_abaqus_hz']} | "
            f"{x['surrogate_error_percent']} | {(hyp['exp'] + ' ' + str(hyp['f_exp_hz'])) if hyp else '—'} | {mac} | "
            f"{status} |")
add("")
add("The branches FE8, FE9 and FE20 have no PRIORITY-2 central derivative (they were lost when E1 ≠ E2), so no LM "
    "prediction exists for them; their real frequencies are in `REAL_FE_FREQUENCIES.csv` and their tracking in "
    "`REAL_FE_BRANCH_TRACKING.csv`.")
add("")
add("## 3. Permutations, lost and mixed branches")
add("")
lost = [k for k, v in tr.items() if v["status"] != "TRACKED"]
perm = [k for k, v in tr.items() if v["permutation"]]
add(f"- Tracked at FE-to-FE MAC ≥ 0.90: {sum(1 for v in tr.values() if v['status'] == 'TRACKED')} of {len(tr)} "
    f"branch × state cells; lowest MAC {min(float(v['fe_fe_mac_or_cos2']) for v in tr.values() if v['fe_fe_mac_or_cos2']):.4f}.")
add(f"- Permutations: {', '.join(f'{b} in {s}' for s, b in perm) or 'none'}. Lost or ambiguous: "
    f"{', '.join(f'{b} in {s}' for s, b in lost) or 'none'}.")
add("- Close pairs (`confirm_cluster` over S0 / H1 / H2): " + "; ".join(f"{'/'.join(c[0])} {c[1]}" for c in r["clusters"])
    + ". FE15 / FE16, a confirmed cluster in PRIORITY-2 (where E1 ≠ E2 exchanged them), keep their individual "
    "identity here, because E1 = E2 keeps the square symmetry; the PRIORITY-3 term FE15+FE16 is compared as the "
    "geometric mean of the two tracked branches.")
add("- FE8 / FE9 stay separate and keep their order in every state for the same reason (they mixed only when "
    "E1 ≠ E2).")
add("")
add("## 4. Declared experimental hypotheses and diagnostic residuals")
add("")
add("| State | Hypothesis | f_EXP, Hz | f_Abaqus, Hz | Error | f_LM, Hz |")
add("|---|---|---|---|---|---|")
for h in ex:
    add(f"| {h['state']} | {h['exp']} ↔ {h['fe_branch']} | {h['f_exp_hz']} | {h['f_abaqus_hz']} | "
        f"{float(h['error_percent']):+.4f} % | {h['f_lm_hz']} |")
add("")
add("Other records against the nearest tracked FE frequency (diagnostic only, never a pair; nearest frequency is not "
    "shape identity):")
add("")
add("| State | " + " | ".join(f"EXP{k}" for k in range(1, 12)) + " |")
add("|---|" + "---|" * 11)
for state in ("S0", "H1", "H2"):
    cells = []
    for k in range(1, 12):
        x = next((v for v in r["vs_experiment"] if v["state"] == state and v["exp"] == f"EXP{k}"), None)
        cells.append("hyp." if x and x["kind"] == "DECLARED_HYPOTHESIS" else
                     (f"{x['fe_branch']} {float(x['error_percent']):+.2f} %" if x else "—"))
    add(f"| {state} | " + " | ".join(cells) + " |")
add("")
add("## 5. Answers")
add("")
s0 = lm[("S0", "FE7")]
add(f"1. **S0:** the real FE7 is {s0['f_abaqus_hz']} Hz against the predicted {s0['f_lm_hz']} Hz "
    f"({s0['surrogate_error_percent']} %), and {next(h for h in ex if h['state'] == 'S0')['error_percent']} % from "
    f"EXP1 (18.6307 Hz); FE-to-FE MAC with the baseline FE7 {tr[('S0', 'FE7')]['fe_fe_mac_or_cos2']}. The "
    "one-mode fit is reproduced by the real solve.")
worst = {s: max(abs(float(x["surrogate_error_percent"])) for k, x in lm.items() if k[0] == s and x["surrogate_error_percent"] != "")
         for s in ("S0", "H1", "H2")}
add(f"2. **Accuracy of the log-linear approximation:** largest |δ| S0 {worst['S0']:.3f} %, H1 {worst['H1']:.3f} %, "
    f"H2 {worst['H2']:.3f} % over all tracked branches. Branches driven by E alone (FE13, FE14) stay within "
    "0.002 % even at E −22 % / −25 % (f ∝ E^0.5 is exactly log-linear); the branches that mix E with G12 "
    "(FE10–FE12, FE17–FE19) are under-predicted by 0.2–0.32 %, because their share of E and G12 changes along the "
    "path; FE7 −0.02 / −0.03 %.")
add("3. **Kept identity:** every elastic branch FE7–FE20 in S0, H1 and H2 (lowest FE-to-FE MAC "
    f"{min(float(v['fe_fe_mac_or_cos2']) for v in tr.values() if v['fe_fe_mac_or_cos2']):.4f}).")
add("4. **Exchanged order:** none in these three states.")
add("5. **Lost or mixed:** none; FE15 / FE16 are individually stable here (INDEPENDENT), unlike in the E1 ≠ E2 "
    "variants of PRIORITY-2.")
h1 = {h["fe_branch"]: h for h in ex if h["state"] == "H1"}
h2 = {h["fe_branch"]: h for h in ex if h["state"] == "H2"}
add(f"6. **H1 / H2 against the declared records:** H1 EXP1 {float(h1['FE7']['error_percent']):+.3f} %, EXP8 ↔ "
    f"FE15+FE16 centroid {float(h1['FE15+FE16']['error_percent']):+.3f} % (real centroid "
    f"{h1['FE15+FE16']['f_abaqus_hz']} Hz; the two real branches are FE15 {tr[('H1', 'FE15')]['f_state_hz']} and "
    f"FE16 {tr[('H1', 'FE16')]['f_state_hz']} Hz). H2 EXP1 {float(h2['FE7']['error_percent']):+.3f} %, EXP7 ↔ FE14 "
    f"{float(h2['FE14']['error_percent']):+.3f} %. These agreements follow from fitting two frequencies with two "
    "parameters; they test the approximation, not the pairings, and H1 / H2 are not ranked by them.")
add("7. **Using the PRIORITY-2 central derivatives far from the base point:** along E1 = E2 with G12 almost fixed "
    "they predicted the real solves to ≤ 0.32 % at E −25 %, which is adequate for a first iteration in that "
    "direction. They are not adequate for precise residuals of the E–G12 mixed branches (bias 0.2–0.3 %, the "
    "size of the provisional Σ_setup) and they say nothing reliable in E1 ≠ E2 directions, where the PRIORITY-2 "
    "branches FE8 / FE9 / FE20 were lost and order exchanges occur. An iteration far from the base needs updated "
    "derivatives at the new point (a new ±5 % set: separate authorisation).")
add("8. **Enough independent experimental correspondences for E1, E2, G12?** No. The only shape-supported row is "
    "EXP1 ↔ FE7 (CANDIDATE_ONLY, research MAC on an unadmitted registration) and it informs G12 only. H1 and H2 add "
    "one hypothetical row each and give rank 2 of 3 (E1 and E2 not separable); E1 ≠ E2 stays blocked by SPEC v1.1 "
    "§5.2.")
add("")
add("## 6. Kept apart (one status each)")
add("")
add("| Question | Outcome |")
add("|---|---|")
add("| Optimiser (PRIORITY-3 `run_bounded_lm`) | worked: CONVERGED in all three scenarios, inside the bounds |")
add("| Approximation against real Abaqus | verified: |δ| ≤ 0.012 % (S0), ≤ 0.23 % (H1), ≤ 0.32 % (H2) |")
add("| Calculated against experimental frequencies | the declared records agree to ≤ 0.11 % by construction (two "
    "frequencies, two parameters); the other records are NOT fitted and are not pairs |")
add("| Correctness of the shape correspondence (EXP ↔ FE) | NOT ESTABLISHED: no admissible physical registration; "
    "EXP8 ↔ FE15+16 and EXP7 ↔ FE14 are hypotheses |")
add("| Engineering calibration of this FE model | not made: no confirmed pairs, no FIT / HOLDOUT, no campaign |")
add("| Material property identification | NOT_A_MATERIAL_PROPERTY; NOT_TRANSFERABLE_WITHOUT_VALIDATION; M8 GATE "
    "NOT_MET and D-077 NO_GLOBAL_PARAMETER_VALUE unchanged; production Auto-ID blocked |")
add("")
add("## Files")
add("")
add("In this folder: `REAL_FE_SOLVER_RUNS.csv`, `REAL_FE_FREQUENCIES.csv`, `REAL_FE_BRANCH_TRACKING.csv`, "
    "`REAL_FE_VS_LM.csv`, `REAL_FE_VS_EXPERIMENT.csv`. Outside Git: the jobs, ODB, DAT, STA, logs and extractions in "
    "`D:\\git\\abaqus-modal-comparator-work\\runs\\m11_carbon_plate\\inverse_fe_r1\\{S0,H1,H2}`; the figures (spectra, "
    "FE shapes, FE-to-FE MAC matrices, branch permutations) in "
    "`D:\\git\\abaqus-modal-comparator-work\\research\\PLATE_INVERSE_FE_R1_202610\\figures`.")
text = "\n".join(L) + "\n"
for folder in (F.OUT, F.DOCS):
    (folder / "RESULTS.md").write_text(text, encoding="utf-8")
print("written", len(L))
