"""PRIORITY-1 — real modal matching of the three new fitted series and the plate's E1 / E2 / G12 parameter study.

RESEARCH_ONLY. Every input is read-only; nothing is written next to it. No Abaqus, no solver, no LM campaign, no
Auto-ID. The project's own services do the work (no new algorithm):

- import: ``services.local_experimental_preview`` / ``services.local_fe_preview`` (importer chain of ``main.py``);
- frequencies: ``services.new_odb_comparison.frequency_only_diagnostic`` and ``identification_clusters``;
- plate shapes: the M11 R6.5 research complex MAC (``research/m11_r65/cmac_research.py``) on the 261016 diagnostic
  reconstruction, carried to 261027 by the DERIVED point map id k <-> id k
  (``plate_registration_readiness.SERIES_LINK_261016_261027``). This is NOT an admissible registration: the
  ``MAC_admissible`` column is NOT_PERMITTED everywhere and no row is MATCH_CONFIRMED;
- FE branches: ``plate_study.sensitivity_table`` (``branch_tracker.track_branches``, ``confirm_cluster``),
  ``plate_study.design_study`` (M5) and ``identification_step.run_bounded_lm`` on a declared linear surrogate
  (HYPOTHETICAL_PAIRING; never a material value).

Status rules (declared before the results were computed; existing project constants only):
  candidate window |Δf| <= 15 % (STRICT_IDENTIFICATION_PAIRING.maximum_relative_frequency_error);
  close group: 3 % (CLUSTER_TRIGGER_RELATIVE_SPACING);
  shape agreement: MAC >= 0.80 (strict minimum); ambiguity: second MAC >= 0.50 (SPEC §6 S1 AutoMAC flag).
  MATCH_CONFIRMED needs an admissible physical registration: none exists for these series, so it is never given.

Usage: python research/real_modal_matching/run_real_matching.py [--out <dir>]
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
sys.path.insert(0, str(REPO / "research" / "m11_r65"))

import inputs as I  # noqa: E402

from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING  # noqa: E402
from services.experimental_qc import SPEC_AUTOMAC_FLAG  # noqa: E402
from services.identification_clusters import CLUSTER_TRIGGER_RELATIVE_SPACING, TriggerRow, cluster_triggers  # noqa
from services import plate_study as ps  # noqa: E402
from services import plate_registration_readiness as rr  # noqa: E402

WINDOW = STRICT_IDENTIFICATION_PAIRING.maximum_relative_frequency_error  # 0.15
PAIR_MAC = STRICT_IDENTIFICATION_PAIRING.minimum_mac  # 0.80
AMBIGUOUS_MAC = SPEC_AUTOMAC_FLAG  # 0.50
MATCH_CONFIRMED, CANDIDATE, AMBIGUOUS, NO_MATCH, FE_UNAVAILABLE = (
    "MATCH_CONFIRMED", "CANDIDATE_ONLY", "AMBIGUOUS_CLUSTER", "NO_MATCH", "FE_SHAPES_UNAVAILABLE")
NOT_PERMITTED = "NOT_PERMITTED (no admissible physical registration)"
RECONSTRUCTION = I.WORK / "runs" / "m11_carbon_plate" / "plate_reconstruction_W301xH300.json"
REF_261016 = I.WORK / "external_models" / "v3_20261021" / "Plate" / "snadwich_Plate" / "300by300_plate_only_1mm_261016_POLYMAX.unv"
SESSION_UNV = {  # the archived session of the same specimen, for a geometry-only series link (no modes used)
    "SP13": I.DELIVERY / "SPname_files_ROTATED_261028" / "SP13_a_500by500_Glue420_Auxetic_newSP01_260910.unv",
    "SP10": I.DELIVERY / "SPname_files_ROTATED_261028" / "SP10_b_rotated_500by500_Glue420_Honeycomb_PlainFiber_260911.unv",
}


# ----------------------------------------------------------------------------- small helpers

def pct(fe, exp):
    return 100.0 * (fe - exp) / exp


def mpc(v):
    import cmac_research as R

    return float(R.mpc(np.asarray(v, dtype=complex)))


def mac_cc(a, b):
    a, b = np.asarray(a, dtype=complex), np.asarray(b, dtype=complex)
    return float(abs(np.vdot(a, b)) ** 2 / (np.vdot(a, a).real * np.vdot(b, b).real))


def exp_z(mode):
    v = np.asarray(mode.vectors)
    return v[:, 2] if v.ndim == 2 else v


def groups(rows):
    """Close groups (3 % trigger) of (id, hz) rows."""
    return [tuple(t.row_ids) for t in cluster_triggers([TriggerRow(i, f, f) for i, f in rows])]


def read_unv_nodes(path: Path):
    lines = path.read_text(errors="replace").splitlines()
    for k, line in enumerate(lines):
        if line.strip() == "-1" and k + 1 < len(lines) and lines[k + 1].strip() == "2411":
            ids, xyz, m = [], [], k + 2
            while lines[m].strip() != "-1":
                ids.append(int(lines[m].split()[0]))
                xyz.append([float(v) for v in lines[m + 1].replace("D", "E").split()[:3]])
                m += 2
            return np.array(ids), np.array(xyz)
    raise ValueError(f"no dataset 2411 in {path}")


# ----------------------------------------------------------------------------- the plate's research MAC (R6.5 method)

def plate_fe_arrays(fe_dir: Path, inp: Path, modes):
    geo = np.loadtxt(fe_dir / "geometry.csv", delimiter=",", skiprows=1, usecols=(1, 2, 3, 4))
    order = np.argsort(geo[:, 0])
    labels, xyz = geo[order, 0].astype(int), geo[order, 1:4]
    fe_u = {}
    for m in modes:
        d = np.loadtxt(fe_dir / f"mode_{m:04d}.csv", delimiter=",", skiprows=1, usecols=(1, 2, 3, 4, 5, 6, 7))
        d = d[np.argsort(d[:, 0])]
        assert np.array_equal(d[:, 0].astype(int), labels)
        fe_u[m] = d[:, 1:4]
    lines = inp.read_text().splitlines()
    i_node = lines.index("*Node")
    i_el = next(i for i, line in enumerate(lines) if line.startswith("*Element, type=S4R"))
    elems = []
    for line in lines[i_el + 1:]:
        if line.startswith("*"):
            break
        elems.append([int(v) for v in line.split(",")])
    row = {lab: k for k, lab in enumerate(labels)}
    conn = np.array([[row[n] for n in e[1:5]] for e in elems])
    return labels, xyz, fe_u, conn


def plate_research_mac(experimental_modes, fe_modes):
    import cmac_research as R

    rec = json.loads(RECONSTRUCTION.read_text(encoding="utf-8"))
    ref_ids = [int(i) for i in rec["unv_node_ids"]]
    points = np.array(rec["scan_points_panel_mm"])
    base = ps.PLATE_FE_FAMILY[0]
    fe_dir = I.FE_PACKAGES["PLATE"].parent
    inp = ps.WORK_ROOT.joinpath(*PureWindowsPath(base.inp.relative).parts)
    labels, xyz, fe_u, conn = plate_fe_arrays(fe_dir, inp, fe_modes)
    exp = [R.order_by_reference(list(m.node_ids), exp_z(m), ref_ids) for m in experimental_modes]
    transfers = {"bilinear_S4R": R.BilinearQuadMesh(xyz[:, :2], conn), "nearest_node": R.NearestNode(xyz[:, :2])}
    out, fe_vectors = {}, {}
    for cand, axes in R.CANDIDATES.items():
        q = R.candidate_to_fe(points, axes)
        for name, tr in transfers.items():
            loc = tr.locate(q)
            fe = [R.z_sign(axes) * tr.sample(fe_u[m][:, 2], loc) for m in fe_modes]
            out[(cand, name)] = R.cmac_matrix(exp, fe)
            fe_vectors[(cand, name)] = fe
    ref = out[(R.REFERENCE_CONVENTION, "bilinear_S4R")]
    invariance = max(float(np.abs(v - out[(R.REFERENCE_CONVENTION, k[1])]).max()) for k, v in out.items())
    method_diff = float(np.abs(out[(R.REFERENCE_CONVENTION, "nearest_node")] - ref).max())
    return {"mac": ref, "invariance_A_D": invariance, "nearest_vs_bilinear": method_diff, "exp": exp,
            "fe": fe_vectors[(R.REFERENCE_CONVENTION, "bilinear_S4R")], "ref_ids": ref_ids, "points": points,
            "xyz": xyz, "fe_u": fe_u}


SP13_REGISTRATION = REPO / "docs" / "registrations" / "SP13_frozen_registration.json"
SP13_REGISTERED_UNV = I.SP13_REGISTERED_UNV[0]


def sp13_registration_vectors(fe_dataset, fe_modes):
    """The frozen SP-13 registration's own map (experimental id -> FE node, U3): FE vectors on the 289 points."""
    reg = json.loads(SP13_REGISTRATION.read_text(encoding="utf-8"))
    first = fe_dataset.sorted_modes()[0]
    index = {str(n): k for k, n in enumerate(first.node_ids)}
    rows = [index[n] for n in reg["mapped_fe_node_ids"]]
    by_number = {int(m.number): m for m in fe_dataset.sorted_modes()}
    fe = [np.asarray(by_number[n].vectors)[rows, 2].real for n in fe_modes]
    return [int(i) for i in reg["experimental_node_ids"]], fe, reg["registration_hash"]


def subspace(e, basis):
    import cmac_research as R

    return R.subspace_projection(e, np.column_stack(basis))


# ----------------------------------------------------------------------------- matching rows

def classify_shapes(dataset, sha):
    """Descriptive invariants of each record on its own grid (plate_study.experimental_summary)."""
    def f(v):
        return "—" if v is None else f"{v:.2f}"

    try:
        summary = ps.experimental_summary(dataset, sha)
        return {r.mode: f"rigid {f(r.rigid_plane_fraction)}, saddle {f(r.saddle_fraction)} (axes "
                        f"{f(r.saddle_on_grid_axes)}), dome {f(r.dome_fraction)}" for r in summary.records}
    except Exception as error:  # noqa: BLE001 (a descriptive column only)
        return {"error": str(error)}


def match_rows(specimen, series, exp_modes, fe_list, shapes, mac=None, fe_cluster_groups=(), fe_note="",
               no_shapes=False, coverage_hz=None, pair_subspace=None):
    """One row per experimental mode; fe_list = [(FE number, hz)], mac = matrix exp × fe_list or None."""
    exp_groups = groups([(f"EXP{m.number}", m.frequency_hz) for m in exp_modes])
    exp_group_of = {r: g for g in exp_groups for r in g}
    fe_group_of = {r: g for g in fe_cluster_groups for r in g}
    rows = []
    for i, m in enumerate(exp_modes):
        f = m.frequency_hz
        cands = [(n, hz) for n, hz in fe_list if abs(hz - f) / f <= WINDOW]
        nearest = min(fe_list, key=lambda x: abs(x[1] - f)) if fe_list else (None, None)
        reason, status, mac_text, mac_best = [], NO_MATCH, NOT_PERMITTED, ""
        cluster = []
        if f"EXP{m.number}" in exp_group_of:
            cluster.append("EXP " + "/".join(exp_group_of[f"EXP{m.number}"]))
        cand_groups = {fe_group_of[f"FE{n}"] for n, _hz in cands if f"FE{n}" in fe_group_of}
        if cand_groups:
            cluster += ["FE " + "/".join(g) for g in sorted(cand_groups)]
        if no_shapes:
            status = FE_UNAVAILABLE
            reason.append(fe_note)
            if not cands:
                reason.append("no FE frequency within 15 %" + (f" (FE computed only up to {coverage_hz:.1f} Hz)"
                                                               if coverage_hz and f > coverage_hz else ""))
        elif mac is not None:
            col = {n: j for j, (n, _hz) in enumerate(fe_list)}
            ranked = sorted(((float(mac[i, col[n]]), n) for n, _hz in fe_list), reverse=True)
            (best, bn), (second, sn) = ranked[0], ranked[1]
            mac_best = f"FE{bn} {best:.3f}; next FE{sn} {second:.3f}"
            in_window = bn in {n for n, _ in cands}
            grouped = f"FE{bn}" in fe_group_of
            two = pair_subspace(i, bn, sn) if (second >= AMBIGUOUS_MAC and pair_subspace) else None
            if two is not None:
                cluster.append(f"two best FE{bn}/FE{sn} subspace {two:.2f}")
            cand_numbers = {n for n, _ in cands}
            strong = []
            for g in fe_cluster_groups:  # S2MAC-like: the record inside a 2-mode FE group's span (Brincker 2014)
                if len(g) == 2 and pair_subspace and {int(r[2:]) for r in g} & cand_numbers:
                    s = pair_subspace(i, int(g[0][2:]), int(g[1][2:]))
                    if s >= PAIR_MAC:
                        strong.append(("/".join(g), s))
            if best >= PAIR_MAC and second < AMBIGUOUS_MAC and in_window and not grouped:
                status = CANDIDATE
                reason.append(f"research MAC {best:.2f} >= 0.80 with FE{bn} only (next {second:.2f} < 0.50), "
                              "|Δf| within 15 %; no admissible registration, so not a confirmed pair")
            elif best >= AMBIGUOUS_MAC and (grouped or second >= AMBIGUOUS_MAC):
                status = AMBIGUOUS
                reason.append(("best FE" + str(bn) + f" (MAC {best:.2f}) lies in the close FE group "
                               f"{'/'.join(fe_group_of[f'FE{bn}'])}") if grouped else
                              f"two FE shapes agree (MAC {best:.2f} and {second:.2f} >= 0.50)")
                reason.append("the record lies in a multi-mode FE subspace; one FE mode cannot be assigned")
                if not in_window:
                    reason.append(f"|Δf| to FE{bn} {pct(dict(fe_list)[bn], f):+.1f} % lies outside 15 %")
            elif strong:
                status = AMBIGUOUS
                reason.append("the record lies in the span of the close FE group " + "; ".join(
                    f"{g} (two-mode subspace {s:.2f} >= 0.80)" for g, s in strong) + f", while no single FE mode "
                    f"agrees (best {best:.2f}): a cluster term, not a one-to-one pair")
            elif best >= PAIR_MAC and not in_window:
                status = NO_MATCH
                reason.append(f"shape agrees with FE{bn} (MAC {best:.2f}) but |Δf| > 15 %")
            elif best >= AMBIGUOUS_MAC:
                status = NO_MATCH
                reason.append(f"partial shape agreement only: best research MAC {best:.2f} (FE{bn}) < 0.80")
            else:
                status = NO_MATCH
                reason.append(f"no FE shape agrees: best research MAC {best:.2f} < 0.50")
        else:
            if not cands:
                status = NO_MATCH
                reason.append("no FE frequency within 15 %")
            elif len(cands) > 1 or cand_groups or f"EXP{m.number}" in exp_group_of:
                status = AMBIGUOUS
                reason.append(f"{len(cands)} FE frequencies within 15 %" + ("; close group" if cluster else "")
                              + "; frequency only (no admissible registration: no MAC)")
            else:
                status = CANDIDATE
                reason.append("one FE frequency within 15 %; frequency only, never a pair (no MAC)")
        rows.append({
            "specimen": specimen, "series": series, "exp_no": m.number, "f_exp_hz": round(f, 4),
            "fe_candidates": "; ".join(f"FE{n} {hz:.3f} ({pct(hz, f):+.2f} %)" for n, hz in cands) or "—",
            "nearest_fe": f"FE{nearest[0]}" if nearest[0] is not None else "—",
            "f_fe_hz": round(nearest[1], 4) if nearest[1] is not None else "",
            "df_percent": round(pct(nearest[1], f), 2) if nearest[1] is not None else "",
            "mac_admissible": NOT_PERMITTED, "research_mac": mac_best or ("—" if mac is None else ""),
            "shape": shapes.get(m.number, ""), "cluster_or_permutation": "; ".join(cluster) or "—",
            "status": status, "reason": " | ".join(reason)})
        del mac_text
    return rows


def write_csv(path: Path, rows):
    with open(path, "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


# ----------------------------------------------------------------------------- figures (independent views)

def figure_ladder(path, title, exp_hz, fe_sets):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    fig = Figure(figsize=(10, 1.2 + 0.6 * (1 + len(fe_sets))), dpi=120)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(1, 1, 1)
    rows = [("EXP", exp_hz, "#1f5fbf")] + [(name, hz, c) for (name, hz), c in
                                           zip(fe_sets, ("#c0392b", "#e67e22", "#8e44ad", "#16a085"))]
    top = max(max(h for _n, hs, _c in rows for h in hs), 1) * 1.04
    for k, (name, hz, colour) in enumerate(reversed(rows)):
        ax.vlines([h for h in hz if h <= top], k - 0.3, k + 0.3, colors=colour, lw=1.5)
        for h in hz:
            if h <= top:
                ax.annotate(f"{h:.1f}", (h, k + 0.32), rotation=90, fontsize=5.5, ha="center", va="bottom",
                            color=colour)
    ax.set_yticks(range(len(rows)), [n for n, _h, _c in reversed(rows)], fontsize=7)
    ax.set_ylim(-0.6, len(rows) + 0.2)
    ax.set_xlim(0, top)
    ax.set_xlabel("Frequency (Hz)", fontsize=8)
    ax.set_title(title + " — frequencies only, NOT mode pairs", fontsize=9)
    fig.tight_layout()
    fig.savefig(path)


def figure_shapes(path, title, items, cols=4):
    """items: (label, x, y, values) — each an independent view on its own coordinates."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    rows = math.ceil(len(items) / cols)
    fig = Figure(figsize=(3.0 * cols, 2.8 * rows + 0.4), dpi=110)
    FigureCanvasAgg(fig)
    for k, (label, x, y, v) in enumerate(items):
        ax = fig.add_subplot(rows, cols, k + 1)
        v = np.asarray(v, dtype=float)
        scale = np.max(np.abs(v)) or 1.0
        ax.scatter(x, y, c=v / scale, cmap="coolwarm", vmin=-1, vmax=1, s=8 if len(x) < 2000 else 1.0,
                   linewidths=0)
        ax.set_title(label, fontsize=7)
        ax.set_aspect("equal")
        ax.set_xticks([]), ax.set_yticks([])
    fig.suptitle(title, fontsize=9)
    fig.tight_layout()
    fig.savefig(path)


def figure_mac(path, mac, exp_labels, fe_labels, title):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    fig = Figure(figsize=(9, 6), dpi=120)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(1, 1, 1)
    im = ax.imshow(mac, vmin=0, vmax=1, cmap="viridis")
    for i in range(mac.shape[0]):
        for j in range(mac.shape[1]):
            ax.text(j, i, f"{mac[i, j]:.2f}", ha="center", va="center", fontsize=5.5,
                    color="white" if mac[i, j] < 0.6 else "black")
    ax.set_xticks(range(len(fe_labels)), fe_labels, rotation=90, fontsize=6)
    ax.set_yticks(range(len(exp_labels)), exp_labels, fontsize=6)
    fig.colorbar(im, ax=ax, fraction=0.03)
    ax.set_title(title, fontsize=8)
    fig.tight_layout()
    fig.savefig(path)


# ----------------------------------------------------------------------------- main

def main(out: Path) -> dict:
    from services import local_experimental_preview as lep

    out.mkdir(parents=True, exist_ok=True)
    figs = out / "figures"
    figs.mkdir(exist_ok=True)
    record = {"status": ["RESEARCH_ONLY", "NO_ADMISSIBLE_REGISTRATION", "NOT_A_MATERIAL_PROPERTY"],
              "rules": {"window": WINDOW, "cluster": CLUSTER_TRIGGER_RELATIVE_SPACING, "pair_mac": PAIR_MAC,
                        "ambiguous_mac": AMBIGUOUS_MAC}}
    exps = {k: I.read_experimental(k) for k in ("PLATE", "SP13", "SP10")}
    record["experimental"] = {k: {"series": e.series, "path": str(e.path), "sha256": e.sha256,
                                  "provenance_ok": e.provenance_ok, "set": e.set_name,
                                  "frequencies_hz": [m.frequency_hz for m in e.modes],
                                  "mpc": [mpc(exp_z(m)) for m in e.modes],
                                  "points": len(e.modes[0].node_ids)} for k, e in exps.items()}
    fe = {k: I.read_fe(k) for k in ("PLATE", "SP13")}
    fe_elastic = {k: [(int(m.number), float(m.frequency_hz)) for m in ps.elastic_modes(p.dataset)]
                  for k, p in fe.items()}
    sp10 = {name: I.dat_frequencies(I.SP10_DAT / f"{name}.dat") for name in I.SP10_MODELS}
    record["fe"] = {"PLATE": {"source": fe["PLATE"].fe_source, "elastic": fe_elastic["PLATE"]},
                    "SP13": {"source": fe["SP13"].fe_source, "elastic": fe_elastic["SP13"]},
                    "SP10": {name: rows for name, rows in sp10.items()}}
    from services.new_odb_comparison import frequency_only_diagnostic

    record["frequency_only_service"] = {}
    for k in ("PLATE", "SP13"):
        d = frequency_only_diagnostic(fe[k].dataset, exps[k].dataset, "PRIORITY-1: no admissible registration")
        record["frequency_only_service"][k] = [(r.experimental_mode, r.experimental_hz, r.nearest_fe_mode,
                                                r.nearest_fe_hz, r.nearest_difference_percent) for r in d.rows]
    fe_groups = {k: groups([(f"FE{n}", hz) for n, hz in fe_elastic[k]]) for k in fe_elastic}
    fe_groups["SP10"] = groups([(f"FE{n}", hz) for n, hz in sp10[I.SP10_MODELS[0]]])
    exp_groups = {k: groups([(f"EXP{m.number}", m.frequency_hz) for m in e.modes]) for k, e in exps.items()}
    record["close_groups"] = {"fe": fe_groups, "experimental": exp_groups}

    # --- plate: research MAC on the DERIVED point map and the 261016 diagnostic reconstruction
    plate_modes = [n for n, _hz in fe_elastic["PLATE"]]
    pm_ = plate_research_mac(exps["PLATE"].modes, plate_modes)
    mac = pm_["mac"]
    record["plate_research_mac"] = {"matrix": mac.round(4).tolist(), "fe_modes": plate_modes,
                                    "invariance_A_D_max_abs": pm_["invariance_A_D"],
                                    "nearest_vs_bilinear_max_abs": pm_["nearest_vs_bilinear"],
                                    "basis": "M11 R6.5 complex MAC; 261016 diagnostic reconstruction W301xH300; "
                                             "point map id k <-> id k (DERIVED); candidate D convention (A–D equal)"}
    pairs_fe = [g for g in fe_groups["PLATE"] if len(g) == 2]
    sub = {}
    for g in pairs_fe:
        idx = [plate_modes.index(int(r[2:])) for r in g]
        sub["/".join(g)] = [subspace(e, [pm_["fe"][j] for j in idx]) for e in pm_["exp"]]
    record["plate_subspace_projection"] = sub
    # 261016 against 261027 by point id (same physical points, DERIVED map) and 261016 against FE (R6.5 cross-check)
    prev16 = lep.preview_experimental_file(REF_261016)
    set16 = [s for s in prev16.sets if "bravo" in (s.key + s.display_name).lower()][0]
    m16 = list(set16.dataset.sorted_modes())
    import cmac_research as R

    e16 = [R.order_by_reference(list(m.node_ids), exp_z(m), pm_["ref_ids"]) for m in m16]
    series_mac = np.array([[mac_cc(a, b) for b in pm_["exp"]] for a in e16])
    fe_vec = pm_["fe"]
    mac16 = R.cmac_matrix(e16, fe_vec)
    record["plate_261016_vs_261027_mac"] = {"rows_261016_hz": [m.frequency_hz for m in m16],
                                            "matrix": series_mac.round(4).tolist()}
    record["plate_261016_research_mac_vs_fe"] = mac16.round(4).tolist()

    shapes = {k: classify_shapes(e.dataset, e.sha256) for k, e in exps.items()}
    def pair_subspace(i, a, b):
        return subspace(pm_["exp"][i], [pm_["fe"][plate_modes.index(a)], pm_["fe"][plate_modes.index(b)]])

    plate_rows = match_rows("PLATE-300x300x1mm", exps["PLATE"].series, exps["PLATE"].modes, fe_elastic["PLATE"],
                            shapes["PLATE"], mac=mac, fe_cluster_groups=[g for g in fe_groups["PLATE"]],
                            pair_subspace=pair_subspace)
    for row, i in zip(plate_rows, range(len(plate_rows))):
        extra = [f"{name}: {vals[i]:.2f}" for name, vals in sub.items() if vals[i] >= 0.5]
        if extra:
            row["cluster_or_permutation"] += " | subspace " + "; ".join(extra)
        j = int(np.argmax(series_mac[:, i]))
        row["reason"] += (f" | 261016 record {m16[j].number} ({m16[j].frequency_hz:.4f} Hz) has research MAC "
                          f"{series_mac[j, i]:.2f} with this record (same points, DERIVED map)")
    # SP-13: the accepted frozen registration of session 260910 a, carried to 261028 ONLY under the hypothesis that the
    # same physical points were measured (ids kept by one proper grid turn: geometry; NOT confirmed by the owner)
    import cmac_research as R

    sp13_modes = [n for n, _hz in fe_elastic["SP13"]]
    reg_ids, sp13_fe, reg_hash = sp13_registration_vectors(fe["SP13"].dataset, sp13_modes)
    sp13_exp = [R.order_by_reference(list(m.node_ids), exp_z(m), reg_ids) for m in exps["SP13"].modes]
    sp13_mac = R.cmac_matrix(sp13_exp, sp13_fe)
    prev_a = lep.preview_experimental_file(I.verified(*I.SP13_REGISTERED_UNV))
    set_a = [s for s in prev_a.sets if s.key.lower() == "best" or s.display_name.lower() == "best"][0]
    ma = list(set_a.dataset.sorted_modes())
    control = R.cmac_matrix([R.order_by_reference(list(m.node_ids), exp_z(m), reg_ids) for m in ma], sp13_fe)
    record["sp13_hypothetical_mac"] = {
        "basis": "HYPOTHETICAL_SAME_POINTS: SP-13 frozen registration " + reg_hash[:12] + "… (session 260910 a) "
                 "applied to 261028 by point id; the same points are NOT confirmed for SP-13",
        "matrix": sp13_mac.round(4).tolist(), "fe_modes": sp13_modes,
        "control_registered_session": {"rows_hz": [m.frequency_hz for m in ma], "matrix": control.round(4).tolist()}}

    def sp13_pair(i, a, b):
        return subspace(sp13_exp[i], [sp13_fe[sp13_modes.index(a)], sp13_fe[sp13_modes.index(b)]])

    sp13_rows = match_rows("SP-13", exps["SP13"].series, exps["SP13"].modes, fe_elastic["SP13"], shapes["SP13"],
                           mac=sp13_mac, fe_cluster_groups=fe_groups["SP13"], pair_subspace=sp13_pair)
    for row in sp13_rows:
        row["research_mac"] = ("HYPOTHETICAL_SAME_POINTS: " + row["research_mac"]) if row["research_mac"] else ""
        row["reason"] += " | basis: the SP-13 frozen registration of 260910 a carried by point id under the "
        row["reason"] += "UNCONFIRMED same-points hypothesis"
    primary = sp10[I.SP10_MODELS[0]]
    sp10_rows = match_rows("SP-10", exps["SP10"].series, exps["SP10"].modes, primary, shapes["SP10"],
                           fe_cluster_groups=fe_groups["SP10"], no_shapes=True,
                           fe_note=f"no extracted FE package of SP-10: frequencies of {I.SP10_MODELS[0]}.dat only",
                           coverage_hz=max(hz for _n, hz in primary))
    for row in sp10_rows:  # the other own models (same mesh) as frequency alternatives
        f = row["f_exp_hz"]
        alts = []
        for name in I.SP10_MODELS[1:]:
            n, hz = min(sp10[name], key=lambda x: abs(x[1] - f))
            alts.append(f"{name}: FE{n} {hz:.2f} ({pct(hz, f):+.1f} %)")
        row["reason"] += " | alternatives " + "; ".join(alts)
    write_csv(out / "PLATE_MODAL_MATCHING.csv", plate_rows)
    write_csv(out / "SP13_MODAL_MATCHING.csv", sp13_rows)
    write_csv(out / "SP10_MODAL_MATCHING.csv", sp10_rows)
    record["matching"] = {"PLATE": plate_rows, "SP13": sp13_rows, "SP10": sp10_rows}

    # --- series links of the sandwiches (geometry only; the same points are NOT confirmed for them)
    record["series_links"] = {}
    for k, path in SESSION_UNV.items():
        try:
            ids0, xyz0 = read_unv_nodes(path)
            e = exps[k]
            link = rr.series_link(ids0, xyz0, list(e.modes[0].node_ids), np.asarray(e.modes[0].coordinates), None)
            record["series_links"][k] = {"reference": path.name, "symmetry": link.symmetry, "proper": link.proper,
                                         "ids_preserved": link.ids_preserved, "points": link.points,
                                         "turn_deg": link.turn_deg, "sense": link.sense, "status": link.status,
                                         "reasons": list(link.reasons)}
        except Exception as error:  # noqa: BLE001
            record["series_links"][k] = {"error": str(error)}

    # --- figures
    figure_ladder(figs / "plate_frequencies.png", "PLATE 261027 vs M11 S4R",
                  [m.frequency_hz for m in exps["PLATE"].modes], [("FE M11", [h for _n, h in fe_elastic["PLATE"]])])
    figure_ladder(figs / "sp13_frequencies.png", "SP-13 261028 vs SP13_mesh_local_v1_modal",
                  [m.frequency_hz for m in exps["SP13"].modes], [("FE SP-13", [h for _n, h in fe_elastic["SP13"]])])
    figure_ladder(figs / "sp10_frequencies.png", "SP-10 261029 vs its own models (.dat)",
                  [m.frequency_hz for m in exps["SP10"].modes],
                  [(n.replace("SP10_", "").replace("SP10", "")[:18], [h for _m, h in sp10[n]]) for n in I.SP10_MODELS])
    labels_exp = [f"E{m.number} {m.frequency_hz:.1f}" for m in exps["PLATE"].modes]
    figure_mac(figs / "plate_research_mac.png", mac, labels_exp, [f"FE{n} {h:.1f}" for n, h in fe_elastic["PLATE"]],
               "PLATE 261027 × M11 FE — RESEARCH complex MAC (261016 diagnostic reconstruction, DERIVED point map; "
               "NOT an admissible registration)")
    figure_mac(figs / "plate_261016_vs_261027_mac.png", series_mac, [f"16:E{m.number} {m.frequency_hz:.1f}"
                                                                       for m in m16], labels_exp,
               "261016 × 261027 by point id (same physical points, DERIVED map) — research MAC")
    for k, e in exps.items():
        xy = np.asarray(e.modes[0].coordinates)
        items = []
        for m in e.modes:
            z = np.asarray(exp_z(m))
            phase = np.angle(z[np.argmax(np.abs(z))])
            items.append((f"EXP{m.number} {m.frequency_hz:.2f} Hz", xy[:, 0], xy[:, 1], (z * np.exp(-1j * phase)).real))
        figure_shapes(figs / f"{k.lower()}_experimental_shapes.png",
                      f"{k} {e.series}: experimental shapes on their own scan coordinates (independent views)", items)
    for k in ("PLATE", "SP13"):
        ds = fe[k].dataset
        items = []
        for m in ps.elastic_modes(ds)[:16]:
            xyz = np.asarray(m.coordinates)
            v = np.asarray(m.vectors)[:, 2].real
            keep = slice(None) if len(xyz) < 20000 else slice(None, None, max(1, len(xyz) // 15000))
            items.append((f"FE{m.number} {m.frequency_hz:.2f} Hz", xyz[keep, 0], xyz[keep, 1], v[keep]))
        figure_shapes(figs / f"{k.lower()}_fe_shapes.png", f"{k} FE shapes (U3) on the FE coordinates "
                      "(independent views)", items)
    # side by side, plate (independent; the experimental view is drawn on the 261016 reconstruction positions)
    items = []
    for i, m in enumerate(exps["PLATE"].modes):
        j = int(np.argmax(mac[i]))
        e = pm_["exp"][i]
        e = (e * np.exp(-1j * np.angle(e[np.argmax(np.abs(e))]))).real
        items.append((f"EXP{m.number} {m.frequency_hz:.2f}", pm_["points"][:, 0], pm_["points"][:, 1], e))
        f = pm_["fe"][j]
        items.append((f"FE{plate_modes[j]} {dict(fe_elastic['PLATE'])[plate_modes[j]]:.2f} (sampled; "
                      f"research MAC {mac[i, j]:.2f})", pm_["points"][:, 0], pm_["points"][:, 1], f))
    figure_shapes(figs / "plate_side_by_side_research.png", "PLATE 261027: experimental record and the FE shape "
                  "with the highest RESEARCH MAC, both on the 261016 diagnostic positions — not a registered pair",
                  items, cols=6)
    (out / "matching_record.json").write_text(json.dumps(record, indent=1, default=str), encoding="utf-8")
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(I.WORK / "research" / "REAL_MODAL_MATCHING_202610"))
    main(Path(parser.parse_args().out))
    print("done")
