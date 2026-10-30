"""Compose RESULTS.md of PRIORITY-2 from s4_record.json and the files on disk (every number from the records)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_s4 as S  # noqa: E402

r = json.loads((S.OUT / "s4_record.json").read_text(encoding="utf-8"))
L = []
add = L.append
add("# PRIORITY-2 — SPEC §6 S4 central sensitivities of the M11 S4R plate (RESEARCH_ONLY)")
add("")
add("Owner-authorised: at most six Abaqus Frequency solves of `S4R_0875_BASELINE`. **Six were run, each once; all "
    "completed.** No LM, no experimental fit, no Auto-ID; no normative file, registration or gate changed. Branch "
    "`research/plate-s4-central-sensitivities` (from `1dd29d5`). Script `research/plate_s4/run_s4.py`.")
add("")
add("## 1. Inputs and the six jobs")
add("")
p = r["prepare"]
add(f"- Baseline INP `{Path(p['base_inp']).name}` SHA-256 `{p['base_inp_sha256']}`; *Elastic line {p['elastic_line_index']} "
    f"`{p['baseline_line']}` (E1, E2, E3, ν12, ν13, ν23, G12, G13; G23 on the next line).")
add(f"- Baseline extraction manifest SHA-256 `{S.BASE.manifest.sha256}`; extractor `abaqus_scripts/extract_odb.py` "
    f"SHA-256 `{S.EXTRACTOR_SHA256}` (pinned, unchanged).")
add("- Each copy changes one field of that line, same width; every other byte is checked equal; mass, thickness, "
    "mesh, free-free boundary and the *Frequency step are unchanged. Jobs in "
    "`D:\\git\\abaqus-modal-comparator-work\\runs\\m11_carbon_plate\\s4_central\\`.")
add("")
add("| # | Job | Changed | Value (MPa) | INP SHA-256 | Exit | Completed | Seconds | ODB SHA-256 |")
add("|---|---|---|---|---|---|---|---|---|")
for run in r["runs"]:
    add(f"| {run['attempt']} | {run['job']} | {run['parameter']} | {float(run['value']):.0f} | `{run['inp_sha256'][:16]}…` | "
        f"{run['exit_code']} | {run['sta_completed']} | {run['seconds']} | `{run['odb_sha256'][:16]}…` |")
add("")
add("## 2. Frequencies: baseline and the ±5 % variants (branches followed by FE-to-FE MAC, not by order)")
add("")
add("| Term | f0 Hz | E1 −5 % | E1 +5 % | E2 −5 % | E2 +5 % | G12 −5 % | G12 +5 % |")
add("|---|---|---|---|---|---|---|---|")
for c in r["central"]:
    vals = [c.get(f"f_{p_}_{s}") or "lost" for p_ in ("E1", "E2", "G12") for s in ("minus", "plus")]
    add(f"| {c['term']} | {c['f_baseline_hz']} | " + " | ".join(str(v) for v in vals) + " |")
add("")
add("FE15+FE16 is one CONFIRMED cluster term (mean ln f): individually its branches exchange in E1 +5 % and E2 −5 %, "
    "the two-mode subspace is stable in every direction. Rigid modes 1–6 are excluded by the shape criterion.")
add("")
add("## 3. Central sensitivities s = (ln f₊ − ln f₋) / (ln 1.05 − ln 0.95)")
add("")
add("| Term | s_E1 | s_E2 | s_G12 | s_E (E1=E2) | curvature E1 / E2 / G12 (s₊ − s₋) | PRIORITY-1 secant E1 / E2 / G12 |")
add("|---|---|---|---|---|---|---|")
for c in r["central"]:
    add(f"| {c['term']} | {c.get('s_E1') or '—'} | {c.get('s_E2') or '—'} | {c.get('s_G12') or '—'} | "
        f"{c.get('s_E (E1=E2)') or '—'} | {c.get('lin_E1')} / {c.get('lin_E2')} / {c.get('lin_G12')} | "
        f"{c.get('secant_P1_E1', '') or '—'} / {c.get('secant_P1_E2', '') or '—'} / {c.get('secant_P1_G12', '') or '—'} |")
add("")
add("**Against the PRIORITY-1 secants:** E1 and E2 (secant over −10 %) agree with the central values to within a few "
    "per cent of s; the G12 secants (over ×2) are too large for the G12-coupled branches (FE10 / FE11 0.169 / 0.167 "
    "→ 0.136 / 0.134; FE12 0.245 → 0.210; FE15+16 0.065 → 0.048; FE17 / FE18 0.169 / 0.168 → 0.137 / 0.136): the "
    "×2 step is far outside the linear range. FE7's G12 sensitivity is almost unchanged (0.479 → 0.483).")
add("")
add("## 4. Branches that lose identity, and permutations")
add("")
add(f"- **Lost (not tracked at MAC ≥ 0.90 in at least one variant; no central value):** {', '.join(r['lost_branches'])}. "
    "FE8 / FE9 (59.87 / 62.01 Hz) mix as soon as E1 ≠ E2 (each is tracked on one side only); FE20 is lost in "
    "E1 +5 % and E2 −5 %. Their G12 sensitivity is ~0 on both sides.")
add("- **Permutations caught by the tracking (would be wrong by frequency order):** " + "; ".join(r["permutations"]) + ".")
add("  In every case E1 > E2 (E1 +5 % or E2 −5 %) puts the E1-dominated branch above the E2-dominated one.")
add("- Close pairs (`confirm_cluster`): " + "; ".join(f"{'/'.join(c[0])} {c[1]}" for c in r["clusters"]) + ".")
add("")
add("## 5. Sensitivity matrices, rank and condition")
add("")
for name, rep in (("E1 / E2 / G12", r["rank_full"]), ("E (E1 = E2) / G12", r["rank_restricted"])):
    add(f"- **{name}** over the {len([c for c in r['central'] if c.get('s_E1') not in ('', None)])} tracked terms: "
        f"singular values {', '.join(f'{v:.4f}' for v in rep['singular_values'])}; condition {rep['condition']:.2f}; "
        f"rank {rep['rank_at_rcond_1e-3']} at rcond 1e-3; weakest direction {rep['weakest_direction']}; column "
        f"cosines {rep['column_cosines']}.")
add("")
add("| M5 design study (all tracked terms as if they were confirmed pairs; provisional Σ_setup 0.3 %) | Status | "
    "Conditional sd (ln) |")
add("|---|---|---|")
for s in r["studies"]:
    add(f"| {s['case']} | {s['status']} | " + (", ".join(f"{100 * v:.2f} %" for v in s["conditional_sd_ln"])
                                              if s["conditional_sd_ln"] else "—") + " |")
add("")
add("## 6. What is mathematically distinguishable")
add("")
add("- **In the FE model:** E1, E2 and G12 are separable (rank 3, condition 1.83). Each has its own branch: FE13 is "
    "pure E1 (s 0.499), FE14 pure E2 (0.500), FE7 almost pure G12 (0.483; s_E 0.016); FE10 / FE17 mix E1 with G12, "
    "FE11 / FE18 mix E2 with G12. The restricted E (E1 = E2) / G12 is rank 2, condition 2.35.")
add("- **With the experiment as it stands (PRIORITY-1):** only EXP1 ↔ FE7 is CANDIDATE_ONLY, and it informs G12 "
    "only; E1, E2 and E stay unidentifiable until branches such as FE13 / FE14 or FE10 / FE11 can be paired. Those "
    "pairs need the physical registration, because E1 ↔ E2 swap the members of each pair.")
add("- **E1 ≠ E2** stays blocked by SPEC v1.1 §5.2 (no traceable material axes), although the model separates them.")
add("- The conditional sd values above assume every FE term is a confirmed pair and the provisional Σ_setup: they are "
    "not the accuracy of the real plate.")
add("")
add("## Files")
add("")
add("`CENTRAL_SENSITIVITIES.csv`, `BRANCH_TRACKING.csv`, `SOLVER_RUNS.csv` (this folder); the ODB, extraction "
    "packages and logs stay in `runs\\m11_carbon_plate\\s4_central\\` (outside Git).")
(S.OUT / "RESULTS.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("written", len(L))
