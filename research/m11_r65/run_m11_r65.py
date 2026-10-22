"""M11 R6.5 runner — research-only experimental–FE complex MAC on the verified M11 copies.

RESEARCH_DIAGNOSTIC_ONLY / COMPUTATIONAL_CONVENTION_ONLY / NO_ACCEPTED_PHYSICAL_REGISTRATION.

Usage (paths are supplied outside Git; every input is refused unless its SHA-256 equals expected_inputs.json):
    python research/m11_r65/run_m11_r65.py --config <inputs.json> --out <work directory>

Reads only verified copies and derived files; never opens an ODB, never runs Abaqus; production code is imported
read-only (UNV reader, PSV record parser) and is not modified. Writes results and figures to --out only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tools"))
import cmac_research as R  # noqa: E402

INP_COORD_TOL_MM = 1.0e-3  # float32 ODB coordinates vs INP (technical identity check, not a scientific criterion)
MEASPOINT_RESIDUAL_MAX = 2.0e-3  # the accepted M2.3 parser-validation refusal level (unchanged)


def load_inputs(paths):
    from universal_reader import discover_experimental_modal_sets
    import services.psv_video_registration as P
    from reconstruct_psv_registration import unv_scan_geometry

    # FE (R6 extraction, Assembly frame)
    geo = np.loadtxt(paths["fe_geometry"], delimiter=",", skiprows=1, usecols=(1, 2, 3, 4))
    order = np.argsort(geo[:, 0])
    labels, xyz = geo[order, 0].astype(int), geo[order, 1:4]
    if len(labels) != 10201 or np.any(np.abs(xyz[:, 2]) > 0):
        raise R.ResearchRefusal("FE geometry is not the 10 201-node flat R6 geometry")
    fe_manifest = json.loads(Path(paths["fe_manifest"]).read_text(encoding="utf-8-sig"))
    fe_hz = {m["mode"]: float(m["frequency_hz"]) for m in fe_manifest["modes"]}
    fe_u = {}
    for m in R.PROTOCOL["fe_modes"]:
        d = np.loadtxt(paths[f"fe_mode_{m:04d}"], delimiter=",", skiprows=1, usecols=(1, 2, 3, 4, 5, 6, 7))
        d = d[np.argsort(d[:, 0])]
        if not np.array_equal(d[:, 0].astype(int), labels) or np.any(d[:, 4:7] != 0):
            raise R.ResearchRefusal(f"FE mode {m}: labels or real-mode representation differ")
        fe_u[m] = d[:, 1:4]

    # INP connectivity (research hypothesis: the verified INP mesh is the R6 mesh; identity NODES_AND_INP_CONTENT)
    lines = Path(paths["inp"]).read_text().splitlines()
    i_node = lines.index("*Node")
    i_el = next(i for i, l in enumerate(lines) if l.startswith("*Element, type=S4R"))
    nodes = np.array([[float(v) for v in l.split(",")] for l in lines[i_node + 1:i_el]])
    elems = []
    for l in lines[i_el + 1:]:
        if l.startswith("*"):
            break
        elems.append([int(v) for v in l.split(",")])
    elems = np.array(elems)
    i_inst = next(i for i, l in enumerate(lines) if l.startswith("*Instance"))
    trans = np.array([float(v) for v in lines[i_inst + 1].split(",")])
    if not lines[i_inst + 2].startswith("*End Instance"):
        raise R.ResearchRefusal("INP instance has a rotation: not supported")
    inp_xyz = nodes[np.argsort(nodes[:, 0]), 1:4] + trans
    if not np.array_equal(np.sort(nodes[:, 0]).astype(int), labels) or np.abs(inp_xyz - xyz).max() > INP_COORD_TOL_MM:
        raise R.ResearchRefusal("INP nodes do not reproduce the R6 geometry: bilinear transfer refused")
    row = {lab: k for k, lab in enumerate(labels)}
    conn = np.array([[row[n] for n in e[1:5]] for e in elems])
    c = xyz[conn, :2]
    a, b = c[:, 1] - c[:, 0], c[:, 3] - c[:, 0]
    normal_z = a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]
    if not np.all(normal_z > 0):
        raise R.ResearchRefusal("S4R node order does not give normal +Z for every element")

    # Experimental (PolyMAX polymax-bravo, complex, U3 only)
    sets = [s for s in discover_experimental_modal_sets(Path(paths["unv_polymax"])) if s.key == "polymax-bravo"]
    if len(sets) != 1 or len(sets[0].modes) != 10:
        raise R.ResearchRefusal("polymax-bravo: not exactly one set of 10 modes")
    rec = json.loads(Path(paths["scan_geometry_nominal"]).read_text(encoding="utf-8"))
    alt = json.loads(Path(paths["scan_geometry_alt_bottom"]).read_text(encoding="utf-8"))
    ref_ids = [int(i) for i in rec["unv_node_ids"]]
    if [int(i) for i in alt["unv_node_ids"]] != ref_ids or len(ref_ids) != 289:
        raise R.ResearchRefusal("scan geometries do not share the 289-point order")
    exp_vec, exp_hz, exp_mpc = [], [], []
    for m in sets[0].modes:
        v = np.asarray(m.vectors)
        if v.shape != (289, 3) or np.any(v[:, :2] != 0):
            raise R.ResearchRefusal("experimental mode is not 289 points with U3 only")
        e = R.order_by_reference(m.node_ids, v[:, 2], ref_ids)
        R._check(e, "experimental mode")
        exp_vec.append(e)
        exp_hz.append(float(m.frequency_hz))
        exp_mpc.append(R.mpc(e))

    # MeasPoints <-> UNV <-> diagnostic geometry
    ids_unv, xy_unv = unv_scan_geometry(Path(paths["unv_polymax"]))
    if [int(i) for i in ids_unv] != ref_ids:
        raise R.ResearchRefusal("UNV geometry order differs from the reconstruction order")
    cf = P.CompoundFile(Path(paths["svd"]).read_bytes())
    uv = P.measpoints_uv(cf.read("Info/Geometry/MeasPoints"), 289)
    h = P.homography(np.asarray(xy_unv) * 1000.0, uv)
    res = float(np.max(np.linalg.norm(P.apply_homography(h, np.asarray(xy_unv) * 1000.0) - uv, axis=1)))
    if res > MEASPOINT_RESIDUAL_MAX:
        raise R.ResearchRefusal(f"MeasPoints do not validate against the UNV ({res:.2e})")
    al = P.alignment_points(cf.read("Info/VideoSettings"))
    t = np.tan(np.radians(al[:, :2]))
    X = np.column_stack([np.ones(len(al)), t])
    cu, *_ = np.linalg.lstsq(X, al[:, 2], rcond=None)
    cv, *_ = np.linalg.lstsq(X, al[:, 3], rcond=None)
    tan_pts = np.linalg.solve(np.array([[cu[1], cu[2]], [cv[1], cv[2]]]), (uv - np.array([cu[0], cv[0]])).T).T
    beam = np.arctan(np.hypot(tan_pts[:, 0], tan_pts[:, 1]))

    return {"labels": labels, "xyz": xyz, "fe_u": fe_u, "fe_hz": fe_hz, "conn": conn, "exp": exp_vec,
            "exp_hz": exp_hz, "exp_mpc": exp_mpc, "points": np.array(rec["scan_points_panel_mm"]),
            "points_alt": np.array(alt["scan_points_panel_mm"]), "measpoint_residual": res, "beam_rad": beam,
            "inp_max_coord_diff_mm": float(np.abs(inp_xyz - xyz).max())}


def matrices(data, points, axes, transfers, weights=None, experimental=None):
    q = R.candidate_to_fe(points, axes)
    out, located = {}, {}
    for name, tr in transfers.items():
        loc = tr.locate(q)
        located[name] = loc
        fe = []
        for m in R.PROTOCOL["fe_modes"]:
            f = R.z_sign(axes) * tr.sample(data["fe_u"][m][:, 2], loc)
            fe.append(f * weights if weights is not None else f)
        exp = experimental if experimental is not None else data["exp"]
        out[name] = {"mac": R.cmac_matrix(exp, fe), "fe": fe}
    return out, located


def subspaces(data, fe_vectors):
    modes = R.PROTOCOL["fe_modes"]
    res = {}
    for a, b in R.PROTOCOL["subspace_pairs"] + R.PROTOCOL["watched_pairs"]:
        basis = np.column_stack([fe_vectors[modes.index(a)], fe_vectors[modes.index(b)]])
        res[f"{a}-{b}"] = [R.subspace_projection(e, basis) for e in data["exp"]]
    return res


def run(config: Path, out: Path) -> dict:
    expected = json.loads((HERE / "expected_inputs.json").read_text(encoding="utf-8"))
    paths = {k: Path(v) for k, v in json.loads(Path(config).read_text(encoding="utf-8")).items()}
    identity = R.verify_identity(paths, expected)
    data = load_inputs(paths)
    nodes_xy = data["xyz"][:, :2]
    transfers = {"nearest_node": R.NearestNode(nodes_xy), "bilinear_S4R": R.BilinearQuadMesh(nodes_xy, data["conn"])}
    scen = R.PROTOCOL["scenarios"]

    full = {}  # candidate -> scenario -> method -> 10x14
    subs = {}  # candidate -> scenario -> method -> pair -> [10]
    dist = {}
    for k, axes in R.CANDIDATES.items():
        full[k], subs[k] = {}, {}
        for s, spec in list(scen.items()) + [("ALT_BOTTOM_EDGE", None)]:
            pts = data["points_alt"] if spec is None else R.scenario_points(data["points"], *spec)
            res, loc = matrices(data, pts, axes, transfers)
            full[k][s] = {m: v["mac"] for m, v in res.items()}
            subs[k][s] = {m: subspaces(data, v["fe"]) for m, v in res.items()}
            if k == R.REFERENCE_CONVENTION:
                dist[s] = {"nearest_node_rms_mm": float(np.sqrt(np.mean(loc["nearest_node"][1] ** 2))),
                           "nearest_node_max_mm": float(np.max(loc["nearest_node"][1]))}

    ref = R.REFERENCE_CONVENTION
    eq = {"max_abs_mac_difference_vs_reference": 0.0, "max_abs_subspace_difference_vs_reference": 0.0}
    for k in R.CANDIDATES:
        for s in full[k]:
            for m in full[k][s]:
                eq["max_abs_mac_difference_vs_reference"] = max(eq["max_abs_mac_difference_vs_reference"], float(
                    np.abs(full[k][s][m] - full[ref][s][m]).max()))
                for p in subs[k][s][m]:
                    eq["max_abs_subspace_difference_vs_reference"] = max(
                        eq["max_abs_subspace_difference_vs_reference"],
                        float(np.abs(np.array(subs[k][s][m][p]) - np.array(subs[ref][s][m][p])).max()))
    if eq["max_abs_mac_difference_vs_reference"] > 1e-6 or eq["max_abs_subspace_difference_vs_reference"] > 1e-6:
        raise R.ResearchRefusal(f"A-D results differ beyond numerical precision: {eq}")

    F = full[ref]
    names = [s for s in scen]
    summary = {}
    for m in ("nearest_node", "bilinear_S4R"):
        stack = np.array([F[s][m] for s in names])
        summary[m] = {"nominal": F["dx+0_dy+0"][m].tolist(), "min": stack.min(0).tolist(), "max": stack.max(0).tolist(),
                      "range": (stack.max(0) - stack.min(0)).tolist(), "alt_bottom": F["ALT_BOTTOM_EDGE"][m].tolist(),
                      "argmax_fe_per_exp_nominal": [int(R.PROTOCOL["fe_modes"][i]) for i in
                                                    F["dx+0_dy+0"][m].argmax(1)],
                      "argmax_same_as_nominal_scenarios": [int(sum(stack[j].argmax(1)[i] == F["dx+0_dy+0"][m].argmax(1)[i]
                                                               for j in range(len(names)))) for i in range(10)],
                      "argmax_alt_bottom": [int(R.PROTOCOL["fe_modes"][i]) for i in F["ALT_BOTTOM_EDGE"][m].argmax(1)]}
    S = subs[ref]
    sub_summary = {}
    for m in ("nearest_node", "bilinear_S4R"):
        sub_summary[m] = {}
        for p in S["dx+0_dy+0"][m]:
            stack = np.array([S[s][m][p] for s in names])
            sub_summary[m][p] = {"nominal": S["dx+0_dy+0"][m][p], "min": stack.min(0).tolist(),
                                 "max": stack.max(0).tolist(), "alt_bottom": S["ALT_BOTTOM_EDGE"][m][p]}

    # secondary, declared: real-normalised experimental shapes; beam projection cos(theta)
    real_exp = [R.real_normalised(e) for e in data["exp"]]
    sec_real, _ = matrices(data, data["points"], R.CANDIDATES[ref], transfers, experimental=real_exp)
    sec_beam, _ = matrices(data, data["points"], R.CANDIDATES[ref], transfers, weights=np.cos(data["beam_rad"]))
    secondary = {"real_normalised": {m: v["mac"].tolist() for m, v in sec_real.items()},
                 "beam_projection": {m: v["mac"].tolist() for m, v in sec_beam.items()},
                 "beam_angle_deg": {"min": float(np.degrees(data["beam_rad"].min())),
                                    "max": float(np.degrees(data["beam_rad"].max())),
                                    "cos_min": float(np.cos(data["beam_rad"].max()))}}

    result = {
        "schema": R.SCHEMA, "status": list(R.STATUS), "protocol_sha256": R.protocol_sha256(),
        "inputs_sha256": identity, "reference_convention": f"{ref} (COMPUTATIONAL_CONVENTION_ONLY)",
        "checks": {"experimental": {"set": "polymax-bravo", "modes": 10, "points": 289, "dof_mask": ["U3"],
                                    "unmeasured_U1_U2_identically_zero": True, "representation": "complex",
                                    "measpoints_unv_residual_max": data["measpoint_residual"],
                                    "point_order": "reconstruction unv_node_ids == UNV geometry order"},
                   "fe": {"nodes": 10201, "modes": R.PROTOCOL["fe_modes"], "frame": "Assembly",
                          "normals": "+Z for all S4R elements (INP node order)",
                          "inp_vs_r6_max_coord_diff_mm": data["inp_max_coord_diff_mm"],
                          "inp_odb_identity": "NODES_AND_INP_CONTENT (connectivity use is a research hypothesis)"},
                   "a_to_d_equivalence": eq},
        "metadata_frequencies_hz": {"experimental": data["exp_hz"],
                                    "fe": [data["fe_hz"][m] for m in R.PROTOCOL["fe_modes"]],
                                    "use": "reference metadata only; not used for MAC, pairing or tuning"},
        "experimental_mpc": data["exp_mpc"],
        "mapping_distance_reference": dist,
        "cmac": summary, "subspace_projection": sub_summary, "secondary": secondary,
        "scenario_names": names,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "r65_results.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    np.savez_compressed(out / "r65_all_matrices.npz", **{f"{k}|{s}|{m}": full[k][s][m] for k in full
                                                         for s in full[k] for m in full[k][s]})
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    try:
        r = run(a.config, a.out)
    except R.ResearchRefusal as exc:
        print(f"REFUSED: {exc}")
        sys.exit(2)
    print(json.dumps({"status": r["status"], "a_to_d": r["checks"]["a_to_d_equivalence"],
                      "protocol_sha256": r["protocol_sha256"]}, indent=1))


if __name__ == "__main__":
    main()
