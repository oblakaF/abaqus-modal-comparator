"""Compose RESULTS.md from the computed records (matching_record.json, parameter_record.json). Every number in the
tables comes from those records; the text states what they do and do not establish. RESEARCH_ONLY."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import inputs as I  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else I.WORK / "research" / "REAL_MODAL_MATCHING_202610"
m = json.loads((OUT / "matching_record.json").read_text(encoding="utf-8"))
p = json.loads((OUT / "parameter_record.json").read_text(encoding="utf-8"))
L = []
add = L.append


def table(rows, cols, heads):
    add("| " + " | ".join(heads) + " |")
    add("|" + "---|" * len(heads))
    for r in rows:
        add("| " + " | ".join(str(r[c]).replace("|", "/") for c in cols) + " |")


add("# PRIORITY-1 — real modal matching and the plate's E1 / E2 / G12 parameter study (RESEARCH_ONLY)")
add("")
add("Branch `research/real-modal-matching-202610` from `main` `4abfbca`. Inputs read-only; no Abaqus, solver, LM "
    "campaign or Auto-ID; no SPEC / DECISIONS / STATUS / EVIDENCE / registration / gate changed. Scripts: "
    "`research/real_modal_matching/` (`inputs.py`, `run_real_matching.py`, `plate_parameters.py`, this file).")
add("")
add("**Statuses never claimed here:** no row is MATCH_CONFIRMED (no admissible physical registration exists for these "
    "three ROTATED series), and no number is a property of the carbon material.")
add("")
add("## 1. What was read")
add("")
add("| Specimen | Series | File (SHA-256 vs SOURCE_PROVENANCE.csv) | Set | Records | Points |")
add("|---|---|---|---|---|---|")
for k, e in m["experimental"].items():
    add(f"| {k} | {e['series']} | `{Path(e['path']).name}` {e['sha256'][:12]}… "
        f"{'MATCH' if e['provenance_ok'] else 'MISMATCH'} | {e['set']} | {len(e['frequencies_hz'])} | {e['points']} |")
add("")
add("| FE source | Content |")
add("|---|---|")
add(f"| PLATE: M11 `S4R_0875_BASELINE` extracted package (R6) | elastic FE {m['fe']['PLATE']['elastic'][0][0]}–"
    f"{m['fe']['PLATE']['elastic'][-1][0]} ({len(m['fe']['PLATE']['elastic'])} modes), shapes on 10 201 nodes |")
add(f"| SP-13: `SP13_mesh_local_v1_modal` extracted package (M4, verified copy) | elastic FE "
    f"{m['fe']['SP13']['elastic'][0][0]}–{m['fe']['SP13']['elastic'][-1][0]} ({len(m['fe']['SP13']['elastic'])} "
    "modes), shapes on 1 585 637 nodes |")
add("| SP-10: four own models (`SP10_NEW_E1=E2_NSM_DENSITY` primary, `SP10nemash63000`, `SP10newmash`, "
    "`SP10_new_E_NSM_DENS`), `.dat` eigenvalue tables | elastic FE 7–15 only (≤ 220 Hz); **no extracted package: "
    "no FE shapes** |")
add("")
add("Literature actually applied (repository `References/`, summaries in `docs/literature/`): Allemang 2002 (MAC, "
    "close-mode caution) → MAC / AutoMAC thresholds; Brincker et al. 2014 (local correspondence, S2MAC) → two-mode "
    "subspace projections for close FE groups; Peeters et al. 2004 (PolyMAX) → fitted dataset-55 records, MPC; "
    "Mottershead, Link & Friswell 2011 and Mottershead & Friswell 1993 → secant sensitivity matrix, rank / "
    "conditioning, bounded LM with pairing kept by shape; Greś et al. 2021 → MAC values near the thresholds read as "
    "uncertain. No other source is used; nothing is attributed to a paper that is not in the folder.")
add("")
add("## 2. All frequencies and the FE candidates of each mode (frequency window 15 %, close groups 3 %)")
for key, name in (("PLATE", "PLATE-300x300x1mm, 261027 vs M11"), ("SP13", "SP-13, 261028 vs SP13_mesh_local_v1_modal"),
                  ("SP10", "SP-10, 261029 vs SP10_NEW_E1=E2_NSM_DENSITY (.dat)")):
    add("")
    add(f"### {name}")
    add("")
    table(m["matching"][key], ["exp_no", "f_exp_hz", "fe_candidates", "nearest_fe", "df_percent", "research_mac",
                               "cluster_or_permutation", "status"],
          ["EXP", "f_EXP Hz", "FE candidates (Δf)", "nearest FE", "Δf %", "shape MAC (research / hypothetical)",
           "cluster / permutation", "status"])
add("")
add("Full rows with the shape descriptors and the reasons: `PLATE_MODAL_MATCHING.csv`, `SP13_MODAL_MATCHING.csv`, "
    "`SP10_MODAL_MATCHING.csv`.")
add("")
add("## 3. Close groups and permutations")
add("")
cg = m["close_groups"]
for k in ("PLATE", "SP13", "SP10"):
    add(f"- **{k}:** experimental {cg['experimental'][k] or 'none'}; FE {cg['fe'][k]}.")
add("- **FE permutations found by FE-to-FE tracking (plate variants, `PLATE_FE_SENSITIVITY.csv`):** E2 ×0.9 swaps "
    "FE10↔FE11, FE13↔FE14 and FE17↔FE18; E1 ×0.9 moves FE14 to FE15; G12 ×2 and ×3 move FE20 to FE19. Matching by "
    "mode number would have mixed these branches.")
add("- **Near-degenerate FE8 / FE9 (59.87 / 62.01 Hz):** insensitive to G12 and lost (BRANCH_LOSS) under E1 ×0.9 and "
    "E2 ×0.9: the two shapes mix when E1 ≠ E2. Plate EXP2 (54.62 Hz) lies in their span (two-mode subspace 0.97).")
add("")
add("## 4. Where a MAC exists and where it may not be computed")
add("")
pm = m["plate_research_mac"]
add(f"- **Admissible MAC: none.** No accepted physical registration applies to any of the three ROTATED series; the "
    "`mac_admissible` column is NOT_PERMITTED in every row.")
add(f"- **PLATE — research MAC (M11 R6.5 method):** the 261016 diagnostic reconstruction (DIAGNOSTIC_ONLY; SCANNER_FACE "
    f"pending) carried to 261027 by the DERIVED point map id k ↔ id k (owner: same points; geometry: 289/289 ids kept "
    f"under a −44.17° turn). Invariant to the FE candidates A–D (max difference {pm['invariance_A_D_max_abs']:.1e}); "
    f"nearest-node vs bilinear transfer differ by ≤ {pm['nearest_vs_bilinear_max_abs']:.3f}. Not a registration.")
sc = m["sp13_hypothetical_mac"]
ctrl = np.array(sc["control_registered_session"]["matrix"])
add("- **SP-13 — HYPOTHETICAL_SAME_POINTS MAC:** the accepted SP-13 frozen registration (session 260910 a) applied to "
    "261028 by point id. Geometry supports it (registered UNV ↔ 260910 re-export: same ids, scale 1.143; 260910 ↔ "
    "261028: 289/289 ids kept under a −45.34° clockwise turn), but the owner has not confirmed the same points for "
    "SP-13. Control on the registered session itself: " + ", ".join(
        f"A{i + 1}→FE{sc['fe_modes'][int(np.argmax(r))]} {r.max():.2f}" for i, r in enumerate(ctrl[:6])) + " …")
add("- **SP-10 — no MAC:** no extracted FE package (shapes would need Abaqus Python on its ODB: a separate gate); the "
    "260911 b session has 323 points against 289, so no id map either.")
add("")
add("### Plate research MAC (rows EXP 261027, columns FE M11)")
add("")
fe_modes = pm["fe_modes"]
mat = np.array(pm["matrix"])
add("| EXP | " + " | ".join(f"FE{n}" for n in fe_modes) + " |")
add("|" + "---|" * (len(fe_modes) + 1))
for i, row in enumerate(mat):
    add(f"| {i + 1} | " + " | ".join(f"**{v:.2f}**" if v >= 0.5 else f"{v:.2f}" for v in row) + " |")
add("")
s16 = np.array(m["plate_261016_vs_261027_mac"]["matrix"])
add("**261016 × 261027 by point id (same physical points, DERIVED map; research):** the diagonal-like maxima are "
    + ", ".join(f"16:E{i + 1}→27:E{int(np.argmax(r)) + 1} {r.max():.2f}" for i, r in enumerate(s16)) + ". Record 1 "
    "of both series has the same shape (0.90) while the frequency moved 33.45 → 18.63 Hz: consistent with the owner's "
    "freer-suspension explanation (research, not a proof).")
add("")
add("## 5. Plate FE frequencies against E1, E2 and G12 (existing variants; no new solve)")
add("")
rows = p["sensitivity_rows"]
cols = list(rows[0])
fcols = [c for c in cols if c.startswith("f ")]
add("| Branch | f0 Hz | " + " | ".join(c[2:].split(" (")[1].rstrip(")") for c in fcols) + " | s_E1 | s_E2 | s_G12 | s_E (E1=E2) |")
add("|" + "---|" * (len(fcols) + 6))
for r in rows:
    add(f"| {r['branch']} | {r['f_baseline_hz']} | " + " | ".join(str(r[c]) or "lost" for c in fcols)
        + f" | {r['s_E1']} | {r['s_E2']} | {r['s_G12']} | {r['s_E (E1=E2)']} |")
add("")
add("Secant sensitivities s = Δ ln f / Δ ln p (E1, E2: −10 %; G12: ×2, the smaller step kept). FE15+FE16 is one "
    "confirmed cluster term. Empty cells: the branch was not tracked in that variant (no value is guessed).")
add("")
add("## 6. Rank and what can be determined separately")
add("")
for name, rep in (("E1, E2, G12", p["rank_full"]), ("E (E1 = E2), G12", p["rank_restricted"])):
    add(f"- **{name}:** singular values {', '.join(f'{v:.3f}' for v in rep['singular_values'])}; condition "
        f"{rep['condition']:.1f}; rank {rep['rank_at_rcond_1e-3']} at rcond 1e-3; weakest direction "
        f"{rep['weakest_direction']}.")
add("")
table([dict(zip(("a", "b", "c", "d"), s)) for s in p["studies"]], ["a", "b", "c", "d"],
      ["M5 design study (provisional Σ_setup 0.3 %)", "status", "conditional sd (ln)", "refusal"])
add("")
add("**Reading:**")
add("- With the FE terms the model offers (FE7, FE10, FE11, FE12, FE13, FE14, FE15+16, FE17, FE18), E1, E2 and G12 "
    "are separable in the model (full rank, condition 1.8): FE7 carries G12 (s 0.48, s_E 0.02), FE13 only E1 (0.50), "
    "FE14 only E2 (0.50), FE10 / FE17 mostly E1 and FE11 / FE18 mostly E2 with G12.")
add("- With the observations that are usable now (one CANDIDATE_ONLY row, EXP1 ↔ FE7), the problem has rank 1: only "
    "G12 (as D66) is informed; E1, E2 and E (E1 = E2) are not. The design study refuses (SPEC §10 hard block).")
add("- E1 ≠ E2 stays blocked by SPEC v1.1 §5.2 (no traceable material axes) even though the model separates them: "
    "FE13 / FE14 and FE10 / FE11 swap under E1 / E2, so the assignment needs the physical registration.")
add("")
add("### Bounded LM on a linear surrogate — HYPOTHETICAL_PAIRING (method demonstration only)")
add("")
for k, v in p["lm_surrogate"].items():
    if "ratio_to_baseline" in v:
        add(f"- **{k}:** {v['status']}, ratio to baseline " + ", ".join(f"{n} ×{r:.4f}" for n, r in
                                                                        v["ratio_to_baseline"].items())
            + f", objective {v['objective']:.3g}, {v['evaluations']} surrogate evaluations, local sd(ln) "
            f"{', '.join(f'{s:.4f}' for s in v['local_sd_ln'] or [])}.")
    else:
        add(f"- **{k}:** {v['status']} — {v.get('reason', '')}.")
add("")
add("G12 alone from EXP1 ↔ FE7 moves G12 by ×0.952 in the linear surrogate; E alone runs to its lower bound (the "
    "twist mode does not inform E); E + G12 together is singular. These numbers demonstrate the method and its "
    "limits; they are not carbon properties (one unconfirmed pair, secant extrapolation, no admissible registration).")
add("")
add("## 7. The FE computations needed for the next iterative step, and why")
add("")
add("1. **SPEC §6 S4 central sensitivities of the M11 baseline** (4 jobs: E (E1 = E2) and G12 at ±5 %, plus the ±2.5 % "
    "repeat, 4 jobs): the secants above use −10 % / ×2 steps; the LM needs central derivatives at the working point "
    "and their linearity check.")
add("2. **FE applicability of the two-band suspension and the force sensor** (prepared jobs B ×2, D ×1): EXP2–EXP5 "
    "and EXP8–EXP11 sit in FE groups whose ordering depends on small asymmetries; a suspension or attachment that "
    "splits them changes which records can become pairs.")
add("3. **An FE model carrying the measured edge-thickness asymmetry** (or the owner's FE corner): it fixes the FE ↔ "
    "physical corner (A–D) and splits FE8 / FE9, FE10 / FE11, FE13 / FE14 physically, which E1 / E2 need.")
add("4. **Extraction of the SP-10 ODB** (`SP10_NEW_E1=E2_NSM_DENSITY`, Abaqus Python, separate gate) and modes above "
    "220 Hz: without them SP-10 has no FE shapes and EXP11–12 no FE frequency.")
add("5. **Owner input that unlocks admissible MAC (no computation):** SCANNER_FACE of 261016 and the 261016 scan "
    "calibration (plate); the same-points confirmation for SP-13 261028 (then its frozen registration can be carried "
    "by point id).")
add("")
add("## 8. Rule refinements made after the first run (disclosed)")
add("")
add("The status rules were declared in `run_real_matching.py` before the first run. Two refinements were made after "
    "it, both making the result more conservative or more consistent, none adding a confirmed pair:")
add("1. A record whose best single MAC is below 0.50 is no longer called AMBIGUOUS only because its nearest FE mode "
    "belongs to a close group (first run: plate EXP9 / EXP10 with MAC 0.26 / 0.15). AMBIGUOUS now needs shape "
    "agreement >= 0.50 with a group member, or two FE modes >= 0.50.")
add("2. A record inside the span of a close two-mode FE group (two-mode subspace projection >= 0.80, S2MAC idea of "
    "Brincker et al. 2014) is AMBIGUOUS_CLUSTER even when no single FE mode reaches 0.50 (plate EXP8: FE15 / FE16 "
    "subspace 0.92).")
add("")
add("## Figures (`figures/`, independent views unless stated)")
add("")
for f in sorted((OUT / "figures").glob("*.png")):
    add(f"- `{f.name}`")
add("")
add("`plate_side_by_side_research.png` and `plate_research_mac.png` use the 261016 diagnostic reconstruction: research "
    "only, never a registered pair.")
(OUT / "RESULTS.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("RESULTS.md written", len(L), "lines")
