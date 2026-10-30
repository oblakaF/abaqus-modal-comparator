"""PRIORITY-4 — real Abaqus verification of the PRIORITY-3 inverse parameter sets S0, H1, H2 of the M11 S4R plate.

RESEARCH_ONLY / HYPOTHETICAL_PAIRING / NOT_A_MATERIAL_PROPERTY / NOT_TRANSFERABLE_WITHOUT_VALIDATION.

Owner-authorised: at most three Abaqus Frequency solves of S4R_0875_BASELINE, one per declared state:

  S0  E1 = E2 = 56 000      G12 = 4 763.4 MPa
  H1  E1 = E2 = 43 467      G12 = 4 804.4 MPa
  H2  E1 = E2 = 41 952.8    G12 = 4 810.3 MPa

The job mechanics are those of ``research/plate_s4/run_s4.py`` (``prepare_jobs`` / ``solve_jobs`` / ``extract_jobs``):
only fields of the *Elastic line change; each attempt is logged before it starts; a job is never run twice; an ODB is
never overwritten; the pinned extractor ``abaqus_scripts/extract_odb.py`` is checked by SHA-256. Branches are followed
from the baseline into each state by FE-to-FE MAC (``plate_study.sensitivity_table`` → ``branch_tracker``, strict
tracking 0.90; close pairs by ``confirm_cluster``), never by frequency order. The PRIORITY-3 predictions are recomputed
with ``research/plate_inverse/run_inverse.predict`` from the pinned PRIORITY-2 central-sensitivity table.

Usage: python research/plate_inverse_fe/run_inverse_fe.py prepare|solve|extract|analyse|figures|all
"""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for sub in ("src", "research/plate_s4", "research/plate_inverse", "research/real_modal_matching"):
    sys.path.insert(0, str(REPO / sub))

import run_s4 as S  # noqa: E402
import run_inverse as V  # noqa: E402
from services import plate_study as ps  # noqa: E402

JOBS_ROOT = S.WORK / "runs" / "m11_carbon_plate" / "inverse_fe_r1"
OUT = S.WORK / "research" / "PLATE_INVERSE_FE_R1_202610"
DOCS = REPO / "docs" / "research" / "plate_inverse_fe_r1"
RUNS_CSV = JOBS_ROOT / "REAL_FE_SOLVER_RUNS.csv"
PREPARE = "inverse_fe_prepare.json"
MAX_SOLVES = 3
LABELS = ["RESEARCH_ONLY", "HYPOTHETICAL_PAIRING", "NOT_A_MATERIAL_PROPERTY", "NOT_TRANSFERABLE_WITHOUT_VALIDATION"]
STATES = {  # declared by the owner; never changed after the results
    "S0": {"G12": (4763.4, "4763.4")},
    "H1": {"E1": (43467.0, "43467."), "E2": (43467.0, "43467."), "G12": (4804.4, "4804.4")},
    "H2": {"E1": (41952.8, "41952.8"), "E2": (41952.8, "41952.8"), "G12": (4810.3, "4810.3")},
}
HYPOTHESES = {  # declared pairings of PRIORITY-3 (hypotheses, never confirmed pairs)
    "S0": [(1, "FE7")], "H1": [(1, "FE7"), (8, "FE15+FE16")], "H2": [(1, "FE7"), (7, "FE14")],
}
LM_PREDICTION_STATED = {  # the PRIORITY-3 values quoted by the owner (for the record; recomputed below)
    ("S0", "FE7"): 18.6311, ("H1", "FE7"): 18.6308, ("H1", "FE15+FE16"): 157.8689, ("H2", "FE7"): 18.6310,
    ("H2", "FE14"): 145.9567,
}


def surrogate_error_percent(f_abaqus: float, f_lm: float) -> float:
    """δ = 100 (f_Abaqus − f_LM) / f_LM."""
    return 100.0 * (f_abaqus - f_lm) / f_lm


def centroid(frequencies) -> float:
    """The cluster term of PRIORITY-2/3: the geometric mean (mean ln f) of its member frequencies."""
    return float(math.exp(np.mean(np.log(np.asarray(frequencies, dtype=float)))))


def prepare() -> dict:
    return S.prepare_jobs(JOBS_ROOT, list(STATES.items()), PREPARE, keep_width=False)


def solve() -> list:
    return S.solve_jobs(JOBS_ROOT, PREPARE, MAX_SOLVES, RUNS_CSV)


def extract() -> dict:
    return S.extract_jobs(JOBS_ROOT, RUNS_CSV, "inverse_fe_extract.json")


def params_of(state: str) -> dict:
    return {**V.P0, **{k: v for k, (v, _t) in STATES[state].items()}}


def _check_extraction(job: str, row: dict) -> dict:
    """The extraction must come from this job's own ODB, and its frequencies from this solve."""
    manifest = JOBS_ROOT / job / "extraction" / "manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8-sig"))
    own = Path(data["odb_path"]).resolve() == (JOBS_ROOT / job / f"{job}.odb").resolve()
    if not own:
        raise S.Refused(f"{job}: the extraction names {data['odb_path']}, not its own ODB")
    if S.sha256(JOBS_ROOT / job / f"{job}.odb") != row["odb_sha256"]:
        raise S.Refused(f"{job}: the ODB changed after the solve")
    return {"manifest_sha256": S.sha256(manifest), "odb_path_matches": own, "modes": len(data["modes"])}


def analyse() -> dict:
    import inputs as I  # fail-closed experimental input (SHA-256 of the provenance map)
    from services.branch_tracker import _mac_matrix

    OUT.mkdir(parents=True, exist_ok=True)
    prep = json.loads((JOBS_ROOT / PREPARE).read_text(encoding="utf-8"))
    runs = {r["job"]: r for r in S._runs(RUNS_CSV)}
    base = S._dataset(S.BASE_MANIFEST)
    states, checks = {}, {}
    for job in STATES:
        row = runs.get(job)
        if row is None or row["sta_completed"] != "True":
            continue
        checks[job] = _check_extraction(job, row)
        states[job] = S._dataset(JOBS_ROOT / job / "extraction" / "manifest.json")
    variants = {job: (ds, "G12" if job == "S0" else "E1", params_of(job)["G12"] / 5000.0 if job == "S0" else
                      params_of(job)["E1"] / 56000.0) for job, ds in states.items()}
    table = ps.sensitivity_table(base, variants)  # the tracking (its secant column is not used here)
    sens = V.load_sensitivities()  # pinned PRIORITY-2 table (refused on another content)
    plate = I.read_experimental("PLATE")
    f_exp = {int(m.number): float(m.frequency_hz) for m in plate.modes}
    # --- all extracted frequencies
    freq_rows = []
    for name, ds in [("BASE", base)] + list(states.items()):
        for m in ds.sorted_modes():
            freq_rows.append({"state": name, "mode": int(m.number), "frequency_hz": round(float(m.frequency_hz), 6),
                              "elastic": int(m.number) in {int(e.number) for e in ps.elastic_modes(ds)}})
    # --- tracking table and the real value of every term (a confirmed cluster is one term, mean ln f)
    track_rows, real = [], {}
    cluster_of = {r.row_id: r.cluster for r in table.rows if r.cluster}
    for row in table.rows:
        for job in states:
            value = row.tracked.get(job)
            status = value[3] if value else "—"
            ok = status in ("TRACKED", "TRACKED_CLUSTER")
            cand = value[0] if ok else None
            modes = (list(cand) if isinstance(cand, (tuple, list)) else [cand]) if ok else []
            track_rows.append({"state": job, "branch": row.row_id, "baseline_mode": row.baseline_mode,
                               "f_baseline_hz": round(row.baseline_hz, 6),
                               "state_modes": "+".join(f"FE{m}" for m in modes),
                               "f_state_hz": ("/".join(f"{h:.6f}" for h in value[1]) if ok and isinstance(
                                   value[1], (tuple, list)) else (round(value[1], 6) if ok else "")),
                               "fe_fe_mac_or_cos2": ((f"{min(value[2]):.4f}" if isinstance(value[2], (tuple, list))
                                                      else f"{value[2]:.4f}") if ok else ""),
                               "status": status if ok else ("BRANCH_LOSS" if "LOSS" in status else
                                                            "AMBIGUOUS_CLUSTER" if "CLUSTER" in status or
                                                            "EXCHANGE" in status else status)[:60],
                               "detail": "" if ok else status[:200],
                               "permutation": "YES" if ok and len(modes) == 1 and modes[0] != row.baseline_mode
                               else ""})
            if ok:
                term = "+".join(cluster_of[row.row_id]) if row.row_id in cluster_of else row.row_id
                hz = value[1]
                real[(job, term)] = centroid(hz) if isinstance(hz, (tuple, list)) else float(hz)
    # PRIORITY-2 treated FE15 / FE16 as one confirmed cluster term (mean ln f). Here both may be tracked one by one
    # (confirm_cluster INDEPENDENT); the same term is then their geometric mean, computed from the tracked branches.
    for job in states:
        if (job, "FE15+FE16") not in real and (job, "FE15") in real and (job, "FE16") in real:
            real[(job, "FE15+FE16")] = centroid([real[(job, "FE15")], real[(job, "FE16")]])
    # --- real Abaqus against the PRIORITY-3 approximation
    lm_rows = []
    for job in states:
        p = params_of(job)
        for term in sens:
            f_lm = V.predict(sens, term, p)
            f_real = real.get((job, term))
            lm_rows.append({"state": job, "fe_branch": term, "f_baseline_hz": round(sens[term]["f0"], 5),
                            "f_lm_hz": round(f_lm, 5), "f_abaqus_hz": "" if f_real is None else round(f_real, 5),
                            "surrogate_error_percent": "" if f_real is None else round(
                                surrogate_error_percent(f_real, f_lm), 4),
                            "lm_stated_by_owner_hz": LM_PREDICTION_STATED.get((job, term), ""),
                            "branch_status": "TRACKED" if f_real is not None else "NOT_TRACKED (no value assigned)"})
    # --- real Abaqus against the declared experimental hypotheses, and diagnostic residuals of the other records
    exp_rows = []
    for job in states:
        for e, term in HYPOTHESES[job]:
            f_real = real.get((job, term))
            exp_rows.append({"state": job, "kind": "DECLARED_HYPOTHESIS", "exp": f"EXP{e}", "f_exp_hz": round(f_exp[e], 4),
                             "fe_branch": term, "f_abaqus_hz": "" if f_real is None else round(f_real, 5),
                             "error_percent": "" if f_real is None else round(100 * (f_real / f_exp[e] - 1), 4),
                             "f_lm_hz": round(V.predict(sens, term, params_of(job)), 5), "labels": " / ".join(LABELS)})
        tracked_terms = {t: f for (j, t), f in real.items() if j == job}
        declared = {e for e, _t in HYPOTHESES[job]}
        for e, f in f_exp.items():
            if e in declared:
                continue
            t, hz = min(tracked_terms.items(), key=lambda kv: abs(kv[1] - f))
            exp_rows.append({"state": job, "kind": "DIAGNOSTIC_NEAREST_FREQUENCY_ONLY (not a pair)", "exp": f"EXP{e}",
                             "f_exp_hz": round(f, 4), "fe_branch": t, "f_abaqus_hz": round(hz, 5),
                             "error_percent": round(100 * (hz / f - 1), 4), "f_lm_hz": "", "labels": " / ".join(LABELS)})
    # --- FE-to-FE MAC matrices (elastic modes), for the figures and the record
    ref = ps.fe_state(base, "BASE")
    macs = {job: {"rows": list(ref.mode_numbers), "cols": list(ps.fe_state(ds, job).mode_numbers),
                  "mac": _mac_matrix(ref.shapes, ps.fe_state(ds, job).shapes).round(4).tolist()}
            for job, ds in states.items()}
    runs_rows = S._runs(RUNS_CSV)
    record = {"labels": LABELS, "prepare": prep, "runs": runs_rows, "extraction_checks": checks,
              "states": {j: params_of(j) for j in STATES}, "clusters": [list(c) for c in table.clusters],
              "frequencies": freq_rows, "tracking": track_rows, "vs_lm": lm_rows, "vs_experiment": exp_rows,
              "fe_fe_mac": macs, "experiment_sha256": plate.sha256, "sensitivity_table_sha256": V.SENSITIVITIES_SHA256}
    DOCS.mkdir(parents=True, exist_ok=True)
    for name, rows in (("REAL_FE_SOLVER_RUNS.csv", runs_rows), ("REAL_FE_FREQUENCIES.csv", freq_rows),
                       ("REAL_FE_BRANCH_TRACKING.csv", track_rows), ("REAL_FE_VS_LM.csv", lm_rows),
                       ("REAL_FE_VS_EXPERIMENT.csv", exp_rows)):
        keys = list(dict.fromkeys(k for r in rows for k in r))
        for folder in (OUT, DOCS):
            with open(folder / name, "w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=keys)
                writer.writeheader()
                writer.writerows(rows)
    (OUT / "inverse_fe_record.json").write_text(json.dumps(record, indent=1, default=str), encoding="utf-8")
    return record


def figures() -> None:
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    rec = json.loads((OUT / "inverse_fe_record.json").read_text(encoding="utf-8"))
    figs = OUT / "figures"
    figs.mkdir(exist_ok=True)
    # 1. spectra
    fig = Figure(figsize=(11, 4.2), dpi=120)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(1, 1, 1)
    rows = ["BASE", "S0", "H1", "H2"]
    for k, name in enumerate(rows):
        hz = [r["frequency_hz"] for r in rec["frequencies"] if r["state"] == name and r["elastic"]]
        ax.vlines(hz, k - 0.35, k + 0.35, colors="#c0392b" if name == "BASE" else "#8e44ad", lw=1.4)
    import inputs as I

    exp = [float(m.frequency_hz) for m in I.read_experimental("PLATE").modes]
    ax.vlines(exp, len(rows) - 0.35, len(rows) + 0.35, colors="#1f5fbf", lw=1.6)
    ax.set_yticks(range(len(rows) + 1), ["FE baseline", "FE S0", "FE H1", "FE H2", "EXP 261027"])
    ax.set_xlabel("Frequency (Hz)")
    ax.set_title("Elastic FE frequencies of the real Abaqus solves and the 261027 records — frequencies only, NOT "
                 "mode pairs", fontsize=9)
    ax.set_xlim(0, 340)
    fig.tight_layout()
    fig.savefig(figs / "spectra_base_S0_H1_H2_exp.png")
    # 2. FE-to-FE MAC matrices
    for job, m in rec["fe_fe_mac"].items():
        mac = np.array(m["mac"])
        fig = Figure(figsize=(7.5, 6.3), dpi=120)
        FigureCanvasAgg(fig)
        ax = fig.add_subplot(1, 1, 1)
        im = ax.imshow(mac, vmin=0, vmax=1, cmap="viridis")
        for i in range(mac.shape[0]):
            for j in range(mac.shape[1]):
                ax.text(j, i, f"{mac[i, j]:.2f}", ha="center", va="center", fontsize=5,
                        color="white" if mac[i, j] < 0.6 else "black")
        ax.set_xticks(range(len(m["cols"])), [f"{job} FE{c}" for c in m["cols"]], rotation=90, fontsize=6)
        ax.set_yticks(range(len(m["rows"])), [f"base FE{r}" for r in m["rows"]], fontsize=6)
        fig.colorbar(im, ax=ax, fraction=0.04, label="FE-to-FE MAC (–)")
        ax.set_title(f"FE-to-FE MAC, baseline × {job} (elastic modes; tracking needs ≥ 0.90)", fontsize=8)
        fig.tight_layout()
        fig.savefig(figs / f"fe_fe_mac_base_vs_{job}.png")
    # 3. permutations: each tracked branch's rank by frequency in each state
    fig = Figure(figsize=(9, 6), dpi=120)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(1, 1, 1)
    branches = sorted({r["branch"] for r in rec["tracking"]}, key=lambda b: int(b[2:]))
    for b in branches:
        ys, xs = [], []
        base_hz = next(r["f_baseline_hz"] for r in rec["tracking"] if r["branch"] == b)
        xs.append(0), ys.append(base_hz)
        for k, job in enumerate(("S0", "H1", "H2"), start=1):
            r = next((r for r in rec["tracking"] if r["branch"] == b and r["state"] == job), None)
            if r and r["f_state_hz"] != "" and "/" not in str(r["f_state_hz"]):
                xs.append(k), ys.append(float(r["f_state_hz"]))
        ax.plot(xs, ys, marker="o", lw=1)
        ax.annotate(b, (0, base_hz), xytext=(-34, 0), textcoords="offset points", fontsize=6, va="center")
    ax.set_xticks([0, 1, 2, 3], ["baseline", "S0", "H1", "H2"])
    ax.set_ylabel("Frequency of the tracked branch (Hz)")
    ax.set_title("Elastic branches followed by FE-to-FE MAC; crossing lines are order exchanges; a missing point is a "
                 "lost branch or a cluster", fontsize=8)
    fig.tight_layout()
    fig.savefig(figs / "branch_permutations.png")
    # 4. FE shapes of each state (U3, elastic modes)
    for job in ("S0", "H1", "H2"):
        ds = S._dataset(JOBS_ROOT / job / "extraction" / "manifest.json")
        modes = ps.elastic_modes(ds)[:14]
        fig = Figure(figsize=(14, 7.5), dpi=100)
        FigureCanvasAgg(fig)
        for k, m in enumerate(modes):
            ax = fig.add_subplot(3, 5, k + 1)
            xyz = np.asarray(m.coordinates)
            v = np.asarray(m.vectors)[:, 2].real
            ax.scatter(xyz[:, 0], xyz[:, 1], c=v / (np.max(np.abs(v)) or 1), cmap="coolwarm", vmin=-1, vmax=1, s=0.6)
            ax.set_title(f"{job} FE{m.number} {m.frequency_hz:.2f} Hz", fontsize=7)
            ax.set_aspect("equal"), ax.set_xticks([]), ax.set_yticks([])
        fig.suptitle(f"{job}: FE shapes U3 (normalised, –) on the FE plane, x / y in mm — independent views", fontsize=9)
        fig.tight_layout()
        fig.savefig(figs / f"fe_shapes_{job}.png")


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    steps = {"prepare": prepare, "solve": solve, "extract": extract, "analyse": analyse, "figures": figures}
    for name in (steps if step == "all" else [step]):
        steps[name]()
        print(name, "done")
