"""PRIORITY-2 — SPEC §6 S4 central sensitivities of the M11 S4R plate to E1, E2 and G12 (owner-authorised: at most six
Abaqus Frequency solves of this one model; nothing else).

Steps (each refuses on any identity mismatch; inputs are read-only and never overwritten):

  prepare   six copies of the baseline INP, each with ONE elastic constant changed by ±5 % on the *Elastic line
            (E1, E2: 56 000 → 53 200 / 58 800 MPa; G12: 5 000 → 4 750 / 5 250 MPa); every other byte is checked equal
  solve     ``abaqus job=<job> input=<job>.inp cpus=1 interactive`` in the job's own folder (as R6.6 / R6.7). Each
            attempt is written to SOLVER_RUNS.csv BEFORE it starts; a seventh attempt is refused. A failed job is
            reported, never replaced by an older result
  extract   the pinned ``abaqus_scripts/extract_odb.py`` (SHA-256 checked) on each new ODB: modes 1–20
  analyse   every elastic branch of the baseline followed into each variant by FE-to-FE MAC (``branch_tracker`` via
            ``plate_study.sensitivity_table``; close pairs by ``confirm_cluster``); central s = Δ ln f / Δ ln p from
            the ± pair; one-sided differences for the linearity check; comparison with the PRIORITY-1 secants; rank
            and condition of E1 / E2 / G12 and of E (E1 = E2) / G12; M5 design studies

No LM, no experimental fit, no Auto-ID. RESEARCH_ONLY.
Usage: python research/plate_s4/run_s4.py prepare|solve|extract|analyse|all
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path, PureWindowsPath

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))

from services import plate_study as ps  # noqa: E402

WORK = ps.WORK_ROOT
JOBS_ROOT = WORK / "runs" / "m11_carbon_plate" / "s4_central"
OUT = WORK / "research" / "PLATE_S4_CENTRAL_202610"
ABAQUS = Path(r"C:\SIMULIA\Commands\abaqus.bat")
EXTRACTOR = REPO / "abaqus_scripts" / "extract_odb.py"
EXTRACTOR_SHA256 = "039aa067adeac83e457ccacc9036c767f98c41517fb1ffdd5293fdd01dc6534d"
BASE = ps.PLATE_FE_FAMILY[0]
BASE_INP = WORK.joinpath(*PureWindowsPath(BASE.inp.relative).parts)
BASE_MANIFEST = WORK.joinpath(*PureWindowsPath(BASE.manifest.relative).parts)
BASELINE_LINE = "56000.,56000., 8500.,  0.05,   0.3,   0.3, 5000., 3000."
MAX_SOLVES = 6
FIELD = {"E1": 0, "E2": 1, "G12": 6}
JOBS = (  # (job, parameter, value, field text)
    ("M11_S4_E1_MINUS", "E1", 53200.0, "53200."), ("M11_S4_E1_PLUS", "E1", 58800.0, "58800."),
    ("M11_S4_E2_MINUS", "E2", 53200.0, "53200."), ("M11_S4_E2_PLUS", "E2", 58800.0, "58800."),
    ("M11_S4_G12_MINUS", "G12", 4750.0, " 4750."), ("M11_S4_G12_PLUS", "G12", 5250.0, " 5250."),
)
BASELINE = {"E1": 56000.0, "E2": 56000.0, "G12": 5000.0}
RCOND = 1e-3
PREVIOUS_SECANTS = REPO / "docs" / "research" / "real_modal_matching_202610" / "PLATE_FE_SENSITIVITY.csv"


class Refused(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


# ----------------------------------------------------------------------------- prepare (generic; reused by PRIORITY-4)

def prepare_jobs(jobs_root: Path, jobs, record_name: str, keep_width: bool = True) -> dict:
    """Copies of the baseline INP, each changing only fields of the one *Elastic line.

    ``jobs``: sequence of (job, {parameter: (value, field text)}). Every other line is checked byte-equal; the
    parsed constants must be exactly the requested ones (the others the baseline's); an existing INP of another
    content is never overwritten. ``keep_width`` refuses a field of another width (S4); PRIORITY-4 values such as
    41952.8 need one more character, which free-format Abaqus input accepts."""
    if sha256(BASE_INP) != BASE.inp.sha256:
        raise Refused(f"baseline INP {BASE_INP.name} is not {BASE.inp.sha256[:12]}…")
    if sha256(BASE_MANIFEST) != BASE.manifest.sha256:
        raise Refused("baseline extraction manifest differs from the recorded one")
    raw = BASE_INP.read_bytes()
    lines = raw.split(b"\n")
    hits = [i for i, line in enumerate(lines) if line.rstrip(b"\r").decode("ascii", "replace") == BASELINE_LINE]
    if len(hits) != 1 or not lines[hits[0] - 1].lower().startswith(b"*elastic, type=engineering constants"):
        raise Refused("the *Elastic, type=ENGINEERING CONSTANTS line is not found exactly once")
    index = hits[0]
    record = {"base_inp": str(BASE_INP), "base_inp_sha256": BASE.inp.sha256, "elastic_line_index": index,
              "baseline_line": BASELINE_LINE, "jobs": {}}
    jobs_root.mkdir(parents=True, exist_ok=True)
    names = [job for job, _c in jobs]
    if len(set(names)) != len(names):
        raise Refused("job names are not unique")
    baseline = ps.parse_inp_material(raw.decode("ascii", "replace"))
    for job, changes in jobs:
        fields = BASELINE_LINE.split(",")
        for parameter, (_value, text) in changes.items():
            if keep_width and len(text) != len(fields[FIELD[parameter]]):
                raise Refused(f"{job}: field width changes")
            fields[FIELD[parameter]] = text
        new_line = ",".join(fields)
        eol = lines[index][len(BASELINE_LINE):]
        new_lines = list(lines)
        new_lines[index] = new_line.encode("ascii") + eol
        content = b"\n".join(new_lines)
        changed = [i for i, (a, b) in enumerate(zip(lines, new_lines)) if a != b]
        if changed != [index] or len(new_lines) != len(lines) or (keep_width and len(content) != len(raw)):
            raise Refused(f"{job}: more than the elastic line would change")
        parsed = ps.parse_inp_material(content.decode("ascii", "replace"))
        expected = {**baseline, **{k: v for k, (v, _t) in changes.items()}}
        if set(parsed) != set(expected) or any(abs(parsed[k] - expected[k]) > 1e-9 * max(1.0, abs(expected[k]))
                                               for k in expected):
            raise Refused(f"{job}: parsed constants {parsed} are not {expected}")
        if not abs(parsed["nu12"]) < math.sqrt(parsed["E1"] / parsed["E2"]):
            raise Refused(f"{job}: not positive definite")
        folder = jobs_root / job
        folder.mkdir(exist_ok=True)
        target = folder / f"{job}.inp"
        if target.exists() and target.read_bytes() != content:
            raise Refused(f"{target} exists with another content: not overwritten")
        target.write_bytes(content)
        entry = {"changes": {k: v for k, (v, _t) in changes.items()}, "inp": str(target),
                 "inp_sha256": sha256(target), "changed_line_index": index, "old_line": BASELINE_LINE,
                 "new_line": new_line, "every_other_line_equal": True,
                 "parsed": {k: parsed.get(k) for k in ("E1", "E2", "E3", "nu12", "nu13", "nu23", "G12", "G13", "G23",
                                                       "rho", "h")}}
        if len(changes) == 1:  # the S4 record fields
            (parameter, (value, _t)), = changes.items()
            entry.update(parameter=parameter, value=value, ratio=value / BASELINE[parameter],
                         every_other_byte_equal=True)
        record["jobs"][job] = entry
    (jobs_root / record_name).write_text(json.dumps(record, indent=1), encoding="utf-8")
    return record


def prepare() -> dict:
    return prepare_jobs(JOBS_ROOT, [(job, {parameter: (value, text)}) for job, parameter, value, text in JOBS],
                        "s4_prepare.json")


# ----------------------------------------------------------------------------- solve (generic; never a hidden repeat)

RUNS_CSV = JOBS_ROOT / "SOLVER_RUNS.csv"
RUN_FIELDS = ["attempt", "job", "parameter", "value", "inp_sha256", "started", "finished", "exit_code",
              "sta_completed", "odb_sha256", "seconds", "note"]


def _runs(runs_csv: Path = None) -> list:
    runs_csv = runs_csv or RUNS_CSV
    if not runs_csv.exists():
        return []
    with open(runs_csv, newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _write_runs(rows, runs_csv: Path = None) -> None:
    with open(runs_csv or RUNS_CSV, "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=RUN_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def solve_jobs(jobs_root: Path, record_name: str, max_solves: int, runs_csv: Path) -> list:
    """Each job once: the attempt is logged BEFORE the solver starts; an attempted job (completed or failed) is never
    run again here, an existing ODB is never overwritten, and attempt max_solves + 1 is refused."""
    prep = json.loads((jobs_root / record_name).read_text(encoding="utf-8"))
    if not ABAQUS.is_file():
        raise Refused(f"{ABAQUS} not found")
    rows = _runs(runs_csv)
    attempted = {r["job"] for r in rows}
    for job, entry in prep["jobs"].items():
        if job in attempted:
            continue  # completed, or failed: a failed job needs a new authorisation, never a silent repeat
        if len(rows) >= max_solves:
            raise Refused(f"the authorised {max_solves} solves are used up; {job} is not run")
        folder = jobs_root / job
        inp = folder / f"{job}.inp"
        if sha256(inp) != entry["inp_sha256"]:
            raise Refused(f"{job}: INP changed since prepare")
        if (folder / f"{job}.odb").exists():
            raise Refused(f"{job}: an ODB already exists; it is not overwritten")
        changes = entry.get("changes") or {entry["parameter"]: entry["value"]}
        row = {"attempt": len(rows) + 1, "job": job, "parameter": "; ".join(changes),
               "value": "; ".join(f"{v:g}" for v in changes.values()), "inp_sha256": entry["inp_sha256"],
               "started": now(), "finished": "", "exit_code": "", "sta_completed": "", "odb_sha256": "", "seconds": "",
               "note": "started"}
        rows.append(row)
        _write_runs(rows, runs_csv)  # the attempt is recorded before the solver starts
        (folder / "scratch").mkdir(exist_ok=True)
        t0 = dt.datetime.now()
        with open(folder / "abaqus_console.log", "w", encoding="utf-8", errors="replace") as log:
            code = subprocess.run(["cmd.exe", "/c", str(ABAQUS), f"job={job}", f"input={job}.inp", "cpus=1",
                                   f"scratch={folder / 'scratch'}", "interactive"], cwd=folder, stdout=log,
                                  stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL).returncode
        sta = folder / f"{job}.sta"
        completed = sta.exists() and "THE ANALYSIS HAS COMPLETED SUCCESSFULLY" in sta.read_text(errors="replace")
        odb = folder / f"{job}.odb"
        row.update({"finished": now(), "exit_code": code, "sta_completed": completed,
                    "odb_sha256": sha256(odb) if odb.exists() else "",
                    "seconds": round((dt.datetime.now() - t0).total_seconds(), 1),
                    "note": "completed" if completed and code == 0 else "FAILED: no result is substituted"})
        _write_runs(rows, runs_csv)
    return rows


def solve() -> list:
    return solve_jobs(JOBS_ROOT, "s4_prepare.json", MAX_SOLVES, RUNS_CSV)


# ----------------------------------------------------------------------------- extract (generic)

def extract_jobs(jobs_root: Path, runs_csv: Path, record_name: str) -> dict:
    if sha256(EXTRACTOR) != EXTRACTOR_SHA256:
        raise Refused("the pinned extractor changed")
    out = {}
    for row in _runs(runs_csv):
        job = row["job"]
        if row["sta_completed"] != "True":
            out[job] = "NOT_SOLVED"
            continue
        folder = jobs_root / job
        odb = folder / f"{job}.odb"
        if sha256(odb) != row["odb_sha256"]:
            raise Refused(f"{job}: ODB changed since the solve")
        target = folder / "extraction"
        if (target / "manifest.json").exists():
            out[job] = "EXISTS"
            continue
        with open(folder / "extraction_run.log", "w", encoding="utf-8", errors="replace") as log:
            code = subprocess.run(["cmd.exe", "/c", str(ABAQUS), "python", str(EXTRACTOR), "--odb", odb.name,
                                   "--output", "extraction", "--start-mode", "1", "--end-mode", "20"], cwd=folder,
                                  stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL).returncode
        out[job] = "EXTRACTED" if code == 0 and (target / "manifest.json").exists() else f"FAILED exit {code}"
    (jobs_root / record_name).write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def extract() -> dict:
    return extract_jobs(JOBS_ROOT, RUNS_CSV, "s4_extract.json")


# ----------------------------------------------------------------------------- analyse

def _dataset(manifest: Path):
    from services.importer_runtime import ensure_application_importers
    from services import local_fe_preview

    ensure_application_importers()
    return local_fe_preview.preview_fe_package(manifest).dataset


def _svd(S, names):
    _u, s, vt = np.linalg.svd(S, full_matrices=False)
    norms = np.linalg.norm(S, axis=0)
    return {"parameters": names, "singular_values": s.tolist(), "condition": float(s[0] / s[-1]),
            "rank_at_rcond_1e-3": int(np.sum(s > RCOND * s[0])),
            "weakest_direction": dict(zip(names, vt[-1].round(4).tolist())),
            "column_cosines": ((S.T @ S) / np.outer(norms, norms)).round(4).tolist()}


def analyse() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    prep = json.loads((JOBS_ROOT / "s4_prepare.json").read_text(encoding="utf-8"))
    runs = {r["job"]: r for r in _runs()}
    if sha256(BASE_MANIFEST) != BASE.manifest.sha256:
        raise Refused("baseline manifest changed")
    base = _dataset(BASE_MANIFEST)
    variants = {}
    for job, parameter, value, _t in JOBS:
        manifest = JOBS_ROOT / job / "extraction" / "manifest.json"
        if runs.get(job, {}).get("sta_completed") == "True" and manifest.exists():
            variants[job] = (_dataset(manifest), parameter, value / BASELINE[parameter])
    table = ps.sensitivity_table(base, variants)  # FE-to-FE tracking + confirm_cluster over every ±5 % variant
    # --- branch tracking
    track_rows = []
    for row in table.rows:
        for job, (_ds, parameter, ratio) in variants.items():
            value = row.tracked.get(job)
            status = value[3] if value else "—"
            ok = status in ("TRACKED", "TRACKED_CLUSTER")
            cand = value[0] if ok else ""
            track_rows.append({"branch": row.row_id, "baseline_mode": row.baseline_mode,
                               "f_baseline_hz": round(row.baseline_hz, 5), "variant": job, "parameter": parameter,
                               "ratio": ratio, "status": status[:160],
                               "variant_modes": "+".join(f"FE{m}" for m in cand) if isinstance(cand, (tuple, list))
                               else (f"FE{cand}" if cand != "" else ""),
                               "f_variant_hz": ("/".join(f"{h:.5f}" for h in value[1]) if ok and isinstance(
                                   value[1], (tuple, list)) else (round(value[1], 5) if ok else "")),
                               "mac_or_cos2": ((f"{min(value[2]):.4f}" if isinstance(value[2], (tuple, list)) else
                                                f"{value[2]:.4f}") if ok else ""),
                               "permutation": ("YES" if ok and not isinstance(cand, (tuple, list)) and
                                               cand != row.baseline_mode else "")})
    # --- central sensitivities
    def term_log_f(row, job):
        value = row.tracked.get(job)
        if not value or value[3] not in ("TRACKED", "TRACKED_CLUSTER"):
            return None
        return float(np.mean(np.log(value[1]))) if value[3] == "TRACKED_CLUSTER" else math.log(value[1])

    previous = {}
    if PREVIOUS_SECANTS.exists():
        with open(PREVIOUS_SECANTS, newline="", encoding="utf-8") as stream:
            previous = {r["branch"]: r for r in csv.DictReader(stream)}
    cen_rows, terms = [], {}
    for row in table.rows:
        cluster = row.cluster
        if cluster and row.row_id != cluster[0]:
            continue  # a CONFIRMED cluster is one term (mean ln f), never two rows
        name = "+".join(cluster) if cluster else row.row_id
        base_lf = (float(np.mean([math.log(r.baseline_hz) for r in table.rows if r.row_id in cluster]))
                   if cluster else math.log(row.baseline_hz))
        line = {"term": name, "f_baseline_hz": round(math.exp(base_lf), 5)}
        s = {}
        for parameter in ("E1", "E2", "G12"):
            minus, plus = f"M11_S4_{parameter}_MINUS", f"M11_S4_{parameter}_PLUS"
            lm, lp = term_log_f(row, minus), term_log_f(row, plus)
            line[f"f_{parameter}_minus"] = round(math.exp(lm), 5) if lm is not None else ""
            line[f"f_{parameter}_plus"] = round(math.exp(lp), 5) if lp is not None else ""
            if lm is None or lp is None:
                line[f"s_{parameter}"] = ""
                line[f"lin_{parameter}"] = "NOT_TRACKED"
                s[parameter] = None
                continue
            central = (lp - lm) / (math.log(1.05) - math.log(0.95))
            s_minus = (base_lf - lm) / (0 - math.log(0.95))
            s_plus = (lp - base_lf) / math.log(1.05)
            line[f"s_{parameter}"] = round(central, 5)
            line[f"lin_{parameter}"] = round(s_plus - s_minus, 5)  # one-sided difference (curvature)
            prev = previous.get(row.row_id, {}).get(f"s_{parameter}", "")
            line[f"secant_P1_{parameter}"] = prev
            s[parameter] = central
        line["s_E (E1=E2)"] = round(s["E1"] + s["E2"], 5) if None not in (s["E1"], s["E2"]) else ""
        line["cluster"] = name if cluster else ""
        cen_rows.append(line)
        if None not in s.values():
            terms[name] = s
    ids = list(terms)
    S3 = np.array([[terms[t][p] for p in ("E1", "E2", "G12")] for t in ids])
    S2 = np.column_stack([S3[:, 0] + S3[:, 1], S3[:, 2]])
    full, restricted = _svd(S3, ["E1", "E2", "G12"]), _svd(S2, ["E (E1=E2)", "G12"])
    sens = {t: {"E1": terms[t]["E1"], "E2": terms[t]["E2"], "G12": terms[t]["G12"],
                "E": terms[t]["E1"] + terms[t]["E2"]} for t in ids}
    studies = []
    for label, params in (("E1 / E2 / G12", ("E1", "E2", "G12")), ("E (E1 = E2) / G12", ("E", "G12"))):
        study = ps.design_study(sens, ids, params, label, 0.003)
        studies.append({"case": label, "status": study.status,
                        "conditional_sd_ln": list(study.sd_ln) if study.sd_ln else None,
                        "refusal": list(study.refusal_reasons)})
    lost = sorted({r["branch"] for r in track_rows if r["status"] not in ("TRACKED", "TRACKED_CLUSTER")})
    perms = [f"{r['branch']} -> {r['variant_modes']} in {r['variant']}" for r in track_rows if r["permutation"]]
    record = {"prepare": prep, "runs": list(runs.values()), "clusters": [list(c) for c in table.clusters],
              "central": cen_rows, "rank_full": full, "rank_restricted": restricted, "studies": studies,
              "lost_branches": lost, "permutations": perms}
    for name, rows in (("CENTRAL_SENSITIVITIES.csv", cen_rows), ("BRANCH_TRACKING.csv", track_rows)):
        keys = list(dict.fromkeys(k for r in rows for k in r))
        with open(OUT / name, "w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=keys)
            writer.writeheader()
            writer.writerows(rows)
    with open(OUT / "SOLVER_RUNS.csv", "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=RUN_FIELDS)
        writer.writeheader()
        writer.writerows(_runs())
    (OUT / "s4_record.json").write_text(json.dumps(record, indent=1, default=str), encoding="utf-8")
    return record


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    steps = {"prepare": prepare, "solve": solve, "extract": extract, "analyse": analyse}
    for name in (steps if step == "all" else [step]):
        result = steps[name]()
        print(name, "done")
