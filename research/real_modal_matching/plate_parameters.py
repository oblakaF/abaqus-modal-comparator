"""PRIORITY-1, part 4 — the plate's FE frequency dependence on E1, E2 and G12 from the EXISTING FE variants.

RESEARCH_ONLY. No Abaqus is run. The variants are the verified M11 family members (R6.6: G12 5 000 → 10 000 / 15 000;
R6.7: E1 56 000 → 50 400, E2 56 000 → 50 400). The project's services do the work:

- ``plate_study.sensitivity_table``: every elastic branch followed into each variant by FE-to-FE MAC
  (``branch_tracker.track_branches``, strict policy, tracking MAC >= 0.90), close FE pairs examined with
  ``confirm_cluster``; secant sensitivities s = Δ ln f / Δ ln p (SECANT, not the SPEC §6 S4 central ±5 %);
- ``plate_study.design_study``: the M5 practical identifiability for a declared set of terms;
- ``identification_step.run_bounded_lm``: the bounded LM on a declared LINEAR SURROGATE built from the secants, with
  HYPOTHETICAL_PAIRING (the CANDIDATE_ONLY rows of the plate's research matching). It demonstrates the method; its
  numbers are not properties of the carbon plate.

Usage: python research/real_modal_matching/plate_parameters.py [--out <dir>]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path, PureWindowsPath

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "src"))

import inputs as I  # noqa: E402
from services import plate_study as ps  # noqa: E402
from services import identification_step as st  # noqa: E402

RCOND = 1e-3  # D-051 practical-rank level
SIGMA_LN = 0.003  # the provisional Σ_setup used by the design studies (not a measured uncertainty)


def datasets():
    from services.importer_runtime import ensure_application_importers
    from services import local_fe_preview

    ensure_application_importers()
    members = {m.member_id: m for m in ps.PLATE_FE_FAMILY}
    base = members["S4R_0875_BASELINE"]
    out, checks = {}, {}
    for member in ps.PLATE_FE_FAMILY:
        if member.manifest is None:
            continue
        checks[member.member_id] = [(c.role, c.state) for c in ps.verify_member(member)]
        if not all(state == "VERIFIED" for _r, state in checks[member.member_id]):
            continue
        path = ps.WORK_ROOT.joinpath(*PureWindowsPath(member.manifest.relative).parts)
        ds = local_fe_preview.preview_fe_package(path).dataset
        ratio = member.parameters[member.changed] / base.parameters[member.changed] if member.changed else 1.0
        out[member.member_id] = (ds, member.changed, ratio)
    return base, out, checks


def svd_report(S, names):
    u, s, vt = np.linalg.svd(S, full_matrices=False)
    rank = int(np.sum(s > RCOND * s[0]))
    norms = np.linalg.norm(S, axis=0)
    cos = (S.T @ S) / np.outer(norms, norms)
    return {"parameters": names, "singular_values": s.tolist(), "condition": float(s[0] / s[-1]),
            "rank_at_rcond_1e-3": rank, "weakest_direction": dict(zip(names, vt[-1].round(4).tolist())),
            "column_cosines": cos.round(4).tolist()}


def main(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    base, family, checks = datasets()
    base_ds = family.pop("S4R_0875_BASELINE")[0]
    variants = {k: v for k, v in family.items() if v[1] in ("E1", "E2", "G12")}
    table = ps.sensitivity_table(base_ds, variants)
    # --- CSV: every elastic branch, its frequency in every variant (tracked by shape) and the secants
    rows = []
    for row in table.rows:
        line = {"branch": row.row_id, "fe_mode": row.baseline_mode, "f_baseline_hz": round(row.baseline_hz, 4)}
        for key, (_ds, parameter, ratio) in variants.items():
            value = row.tracked.get(key)
            label = f"{key} ({parameter} ×{ratio:.3g})"
            if value is None or value[3] not in ("TRACKED", "TRACKED_CLUSTER"):
                line[f"f {label}"] = ""
                line[f"track {label}"] = (value[3] if value else "—")[:80]
            else:
                hz = value[1] if not isinstance(value[1], (tuple, list)) else "/".join(f"{h:.4f}" for h in value[1])
                line[f"f {label}"] = round(hz, 4) if isinstance(hz, float) else hz
                mac = value[2] if not isinstance(value[2], (tuple, list)) else min(value[2])
                line[f"track {label}"] = f"{value[3]} MAC {mac:.3f}" + (
                    f" -> FE{value[0]}" if not isinstance(value[0], (tuple, list)) else f" -> FE{value[0]}")
        for p in ("E1", "E2", "G12"):
            s = row.sensitivity.get(p)
            line[f"s_{p}"] = "" if s is None else round(s, 4)
        sE = row.sensitivity.get("E1"), row.sensitivity.get("E2")
        line["s_E (E1=E2)"] = "" if None in sE else round(sE[0] + sE[1], 4)
        line["cluster"] = "+".join(row.cluster) if row.cluster else ""
        rows.append(line)
    with open(out / "PLATE_FE_SENSITIVITY.csv", "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    # --- rank: all tracked terms, and the restricted E1 = E2
    ids3, S3 = table.matrix(("E1", "E2", "G12"))
    # a CONFIRMED cluster is ONE term (mean ln f), never two rows (plate_study.d_sensitivities)
    keep, names = [], []
    for k, rid in enumerate(ids3):
        row = next(rw for rw in table.rows if rw.row_id == rid)
        if row.cluster and rid != row.cluster[0]:
            continue
        keep.append(k)
        names.append("+".join(row.cluster) if row.cluster else rid)
    ids3, S3 = tuple(names), S3[keep]
    full = svd_report(S3, ["E1", "E2", "G12"])
    S2 = np.column_stack([S3[:, 0] + S3[:, 1], S3[:, 2]])
    restricted = svd_report(S2, ["E (E1=E2)", "G12"])
    matching = json.loads((out / "matching_record.json").read_text(encoding="utf-8"))
    candidates = [r for r in matching["matching"]["PLATE"] if r["status"] == "CANDIDATE_ONLY"]
    hyp_rows = []
    for r in candidates:
        fe_no = int(r["research_mac"].split()[0][2:])
        if f"FE{fe_no}" in ids3:
            hyp_rows.append((r["exp_no"], r["f_exp_hz"], f"FE{fe_no}"))
    sens = {rid: {"E1": S3[k, 0], "E2": S3[k, 1], "G12": S3[k, 2], "E": S3[k, 0] + S3[k, 1]}
            for k, rid in enumerate(ids3)}
    studies = []
    for label, params, terms in (("all tracked FE terms, E1 / E2 / G12", ("E1", "E2", "G12"), list(ids3)),
                                 ("all tracked FE terms, E (E1 = E2) / G12", ("E", "G12"), list(ids3)),
                                 ("CANDIDATE_ONLY rows only (hypothetical pairing), E1 / E2 / G12",
                                  ("E1", "E2", "G12"), [t for _e, _f, t in hyp_rows]),
                                 ("CANDIDATE_ONLY rows only (hypothetical pairing), E (E1 = E2) / G12", ("E", "G12"),
                                  [t for _e, _f, t in hyp_rows])):
        if not terms:
            studies.append((label, "NO_TERMS", "—", "—"))
            continue
        study = ps.design_study(sens, terms, params, label, SIGMA_LN)
        studies.append((label, study.status, ", ".join(f"{100 * v:.2f} %" for v in study.sd_ln) if study.sd_ln
                        else "—", "; ".join(study.refusal_reasons) or "—"))
    # --- LM on a declared linear surrogate (HYPOTHETICAL_PAIRING; the method, not a material value)
    lm = {}
    p0 = {"E": base.parameters["E1"], "G12": base.parameters["G12"]}
    if hyp_rows:
        f0 = {t: {rw.row_id: rw.baseline_hz for rw in table.rows}[t] for _e, _f, t in hyp_rows}

        def surrogate(p):
            return np.array([(math.log(f0[t]) + sens[t]["E"] * math.log(p["E"] / p0["E"]) + sens[t]["G12"] *
                              math.log(p["G12"] / p0["G12"]) - math.log(f)) / SIGMA_LN for _e, f, t in hyp_rows])

        for params in (("G12",), ("E",), ("E", "G12")):
            names = list(params)
            bounds = st.parameter_bounds([(n, p0[n] * 0.5, p0[n] * 2.0) for n in names])
            settings = st.LMSettings(mu_initial=1e-3, mu_decrease=10.0, max_step_attempts=5, solve_budget=60)
            fixed = {n: p0[n] for n in p0 if n not in names}
            try:
                res = st.run_bounded_lm(lambda q: surrogate({**fixed, **q}), {n: p0[n] for n in names}, bounds,
                                        settings)
                lm["+".join(names)] = {"status": res.status.value, "parameters": res.parameters,
                                       "ratio_to_baseline": {n: res.parameters[n] / p0[n] for n in names},
                                       "objective": res.objective, "evaluations": res.solves,
                                       "local_sd_ln": res.local_sd, "refusal": res.refusal}
            except st.StepError as error:
                lm["+".join(names)] = {"status": "STEP_ERROR", "reason": str(error)}
    # --- the report
    lines = ["# PLATE_PARAMETER_RANK — E1, E2, G12 of the M11 plate model (RESEARCH_ONLY)", "",
             "Secant sensitivities s = Δ ln f / Δ ln p from the existing FE variants (no new Abaqus solve); branches "
             "followed by FE-to-FE MAC (strict tracking 0.90), close pairs by `confirm_cluster`. Basis: "
             f"`{table.basis}`.", "",
             "## FE family used (SHA-256 verified)", "", "| Member | Changed | Ratio | Files |", "|---|---|---|---|"]
    lines += [f"| {k} | {v[1] or '—'} | {v[2]:.3g} | {', '.join(f'{r} {s}' for r, s in checks[k])} |"
              for k, v in {**{"S4R_0875_BASELINE": (None, None, 1.0)}, **variants}.items()]
    lines += ["", "## Sensitivity matrix (all tracked terms)", "", "| Term | f0 (Hz) | s_E1 | s_E2 | s_G12 | s_E (E1=E2) |",
              "|---|---|---|---|---|---|"]
    f_by = {rw.row_id: rw.baseline_hz for rw in table.rows}
    for rw in table.rows:
        if rw.cluster:
            f_by["+".join(rw.cluster)] = float(np.exp(np.mean([np.log(r.baseline_hz) for r in table.rows
                                                               if r.row_id in rw.cluster])))
    lines += [f"| {t} | {f_by[t]:.3f} | {S3[k, 0]:+.4f} | {S3[k, 1]:+.4f} | {S3[k, 2]:+.4f} | "
              f"{S3[k, 0] + S3[k, 1]:+.4f} |" for k, t in enumerate(ids3)]
    missing = [rw.row_id for rw in table.rows if rw.row_id not in ids3 and not rw.cluster]
    lines += ["", f"Terms without every sensitivity (tracking refused in a variant): {', '.join(missing) or 'none'}.",
              "", "Close FE pairs (`confirm_cluster`): " + "; ".join(f"{'/'.join(ids)} {status}" for ids, status, _r
                                                                    in table.clusters), "",
              "## Rank", "",
              "| Problem | Singular values | Condition | Rank (rcond 1e-3) | Weakest direction |", "|---|---|---|---|---|"]
    for name, rep in (("E1, E2, G12", full), ("E (E1 = E2), G12", restricted)):
        lines.append(f"| {name} | {', '.join(f'{v:.4f}' for v in rep['singular_values'])} | {rep['condition']:.1f} | "
                     f"{rep['rank_at_rcond_1e-3']} | {rep['weakest_direction']} |")
    lines += ["", "Column cosines (E1, E2, G12): " + json.dumps(full["column_cosines"]), "",
              "## M5 practical identifiability (design study; provisional Σ_setup 0.3 %)", "",
              "| Case | Status | Conditional sd (ln) | Refusal |", "|---|---|---|---|"]
    lines += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in studies]
    lines += ["", "## Bounded LM on a linear surrogate — HYPOTHETICAL_PAIRING / RESEARCH_ONLY", "",
              "Pairs used (CANDIDATE_ONLY rows of the research matching; not confirmed pairs): "
              + (", ".join(f"EXP{e} {f} Hz ↔ {t}" for e, f, t in hyp_rows) or "none") + ".", "",
              "Surrogate: ln f_t(p) = ln f_t0 + Σ s_tj ln(p_j / p_j0) with the secants above; residual / 0.003. Each "
              "evaluation is a surrogate evaluation, not an Abaqus solve. The result shows the method; it is NOT a "
              "property of the carbon plate (one term, a linear extrapolation of secants, no admissible "
              "registration).", "", "```json", json.dumps(lm, indent=1), "```"]
    (out / "PLATE_PARAMETER_RANK.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    record = {"sensitivity_rows": rows, "rank_full": full, "rank_restricted": restricted, "studies": studies,
              "hypothetical_pairs": hyp_rows, "lm_surrogate": lm, "clusters": [list(c) for c in table.clusters]}
    (out / "parameter_record.json").write_text(json.dumps(record, indent=1, default=str), encoding="utf-8")
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(I.WORK / "research" / "REAL_MODAL_MATCHING_202610"))
    rec = main(Path(parser.parse_args().out))
    print(json.dumps({k: rec[k] for k in ("rank_full", "rank_restricted", "studies", "hypothetical_pairs",
                                          "lm_surrogate")}, indent=1, default=str)[:6000])
