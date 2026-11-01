"""PRIORITY-6 — SP-10 FE shapes from the existing ODB of SP10_NEW_E1=E2_NSM_DENSITY (owner-authorised: ONE run of the
pinned Abaqus Python extractor on this one ODB; no Frequency solve, no model change, no other FE computation).

Steps (each refuses on any identity mismatch; the copies are read-only and never overwritten):

  preflight  the verified V2 copy of the job (ODB, .dat, .inp, .sta, .log, .msg, .com) equals COPY_MANIFEST_V2.json and
             the values pinned here; the job completed; the pinned ``abaqus_scripts/extract_odb.py`` is unchanged
  copy       a working copy (level C) of the ODB and of the extractor in the run folder, checked by SHA-256; the
             original in C:\\temp (level A) is never opened
  extract    ``abaqus python scripts\\extract_odb.py --odb input\\<job>.odb --output output --start-mode 7
             --end-mode 25`` with the working directory and TEMP / TMP in ``logs``: modes 7–25 are every elastic mode the
             ODB holds (modes 1–6 are the rigid-body modes, as in the SP-13 extraction 7–30). The attempt is recorded
             BEFORE it starts and a second attempt is refused: one run, no retry
  postflight the V2 copy and the working copy are unchanged; nothing new in the V2 folder; no solver artefact in the
             run folder (no FE solve took place)
  verify     the extracted package against the job's own .dat (both eigenvalue tables), its identity (SHA-256 of every
             file) and its geometry; writes PACKAGE_IDENTITY.json and the small archived records in docs/research

Nothing scientific is decided here: no MAC, no registration, no pairing. RESEARCH_ONLY.
Usage: python research/sp10_existing_fe_shapes/run_sp10_extraction.py preflight|copy|extract|postflight|verify
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
WORK = Path(r"D:\git\abaqus-modal-comparator-work")
V2_ROOT = WORK / "external_models" / "v2_20261019"
V2_MANIFEST = V2_ROOT / "COPY_MANIFEST_V2.json"
JOB = "SP10_NEW_E1=E2_NSM_DENSITY"
V2_JOB = V2_ROOT / "SP-10" / "temp_root"
ORIGINAL_SOURCE = rf"C:\temp\{JOB}.odb"  # level A: recorded only, never opened
RUN = WORK / "research" / "PRIORITY6_SP10_FE_SHAPES_202610"
ABAQUS = Path(r"C:\SIMULIA\Commands\abaqus.bat")
EXTRACTOR = REPO / "abaqus_scripts" / "extract_odb.py"
EXTRACTOR_SHA256 = "039aa067adeac83e457ccacc9036c767f98c41517fb1ffdd5293fdd01dc6534d"
START_MODE, END_MODE = 7, 25
STEP = "SP_10_MODAL_FREE"  # the second frequency step (25 modes); the first, Modal_FreeFree, has 15
JOB_FILES = {  # suffix: (size, SHA-256) of the V2 copy (COPY_MANIFEST_V2.json, 2026-10-19)
    ".odb": (979511712, "87a9036fb5dc314e14a1fcb0d9ef4e0175d80bc6dfb05ceeea926d1ae767302c"),
    ".dat": (53448, "c2ff381cb61a4f113c87b09527372783f4d46df0354755ba1f1b1801f97dab01"),
    ".inp": (131593293, "851ed627afd2ebc7539304247aefac3248507b5be2fc19ac992be84cb6f7f16f"),
    ".sta": (511, "f53fc3fc79bf29556040875d17c7492ca34f6660fcdbbedb6d9d393acfee5f2b"),
    ".log": (801, "78a010a1c856c83b1fb8db30d9e8db4c7df84f3b1ca26d40f970b27b162becd9"),
    ".msg": (14267, "4f4584798540174c8a5f5a785abdf80fd36bd119d7b6dc43e575b43651c12a1c"),
    ".com": (3538, "ca288149f4f4a0acf1d98557709f566c82c98d125624725729f04ec0f3b5b968"),
}
SOLVER_ARTEFACTS = {".sta", ".msg", ".dat", ".prt", ".com", ".sim", ".res", ".mdl", ".stt", ".023", ".lck", ".ipm",
                    ".odb_f", ".fil"}
DOCS_OUT = REPO / "docs" / "research" / "sp10_existing_fe_shapes_202610"
LABELS = "RESEARCH_ONLY / HYPOTHETICAL_PAIRING / NOT_A_MATERIAL_PROPERTY"


class Refused(RuntimeError):
    """An input is missing or not the expected content; nothing is run or written on it."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 22), b""):
            digest.update(chunk)
    return digest.hexdigest()


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _write_json(path: Path, record) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def _check(path: Path, size: int, digest: str) -> dict:
    if not path.is_file():
        raise Refused(f"{path} is missing")
    actual_size, actual = path.stat().st_size, sha256(path)
    if actual_size != size or actual != digest:
        raise Refused(f"{path.name}: {actual_size} bytes / {actual[:12]}… is not {size} / {digest[:12]}…")
    return {"path": str(path), "bytes": size, "sha256": actual}


# ----------------------------------------------------------------------------- the .dat eigenvalue tables

_ROW = re.compile(r"^\s+(\d+)\*?\s+([-+.\dEe]+)\s+([-+.\dEe]+)\s+([-+.\dEe]+)\s+([-+.\dEe]+)")


def dat_tables(text: str) -> list:
    """Every EIGENVALUE OUTPUT table of an Abaqus .dat, in step order: [(step, [(mode, eigenvalue, hz), ...]), ...]."""
    tables, step = [], None
    lines = text.splitlines()
    for index, line in enumerate(lines):
        found = re.search(r"S T E P\s+(\d+)\s+C A L C U L A T I O N   O F   E I G E N V A L U E S", line)
        if found:
            step = int(found.group(1))
        if "E I G E N V A L U E    O U T P U T" not in line:
            continue
        rows = []
        for row in lines[index + 1:]:
            match = _ROW.match(row)
            if match:
                rows.append((int(match.group(1)), float(match.group(2)), float(match.group(4))))
            elif rows and "EIGENVALUES MARKED" in row or (rows and row.strip().startswith("P A R T")):
                break
        tables.append((step, rows))
    return tables


def same_printed_value(odb_hz: float, dat_hz: float) -> bool:
    """The .dat prints five significant digits: the ODB frequency, printed the same way, must give the same number."""
    if dat_hz == 0.0:
        return odb_hz == 0.0
    digits = 5 - 1 - int(math.floor(math.log10(abs(dat_hz))))
    return round(odb_hz, digits) == round(dat_hz, digits)


# ----------------------------------------------------------------------------- steps

def preflight() -> dict:
    manifest = json.loads(V2_MANIFEST.read_text(encoding="utf-8"))
    listed = {Path(f["copy"]).name: f for f in manifest["files"] if f.get("specimen") == "SP10"}
    record = {"checked": now(), "job": JOB, "v2_manifest": str(V2_MANIFEST), "files": {}}
    for suffix, (size, digest) in JOB_FILES.items():
        entry = listed.get(JOB + suffix)
        if entry is None or entry["size"] != size or entry["sha256"] != digest or entry["result"] != "COPIED_VERIFIED":
            raise Refused(f"{JOB}{suffix}: COPY_MANIFEST_V2.json does not hold the pinned copy")
        record["files"][suffix] = _check(V2_JOB / (JOB + suffix), size, digest) | {"source": entry["source"]}
    log = (V2_JOB / f"{JOB}.log").read_text(errors="replace")
    sta = (V2_JOB / f"{JOB}.sta").read_text(errors="replace")
    if f"Abaqus JOB {JOB} COMPLETED" not in log or "THE ANALYSIS HAS COMPLETED SUCCESSFULLY" not in sta:
        raise Refused("the job did not complete")
    if sha256(EXTRACTOR) != EXTRACTOR_SHA256:
        raise Refused("the pinned extractor changed")
    record["job_completed"] = True
    record["abaqus_release"] = re.search(r"Abaqus (\d{4})", log).group(1)
    record["extractor"] = {"path": str(EXTRACTOR), "sha256": EXTRACTOR_SHA256}
    _write_json(RUN / "preflight.json", record)
    return record


def copy() -> dict:
    preflight()
    size, digest = JOB_FILES[".odb"]
    target = RUN / "input" / f"{JOB}.odb"
    script = RUN / "scripts" / "extract_odb.py"
    for source, destination, expected in ((V2_JOB / f"{JOB}.odb", target, digest), (EXTRACTOR, script,
                                                                                     EXTRACTOR_SHA256)):
        if destination.exists():
            if sha256(destination) != expected:
                raise Refused(f"{destination} exists with another content")
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if sha256(destination) != expected:
            raise Refused(f"{destination}: the copy differs")
        os.chmod(destination, 0o444)  # read-only working copy
    record = {"copied": now(), "odb": str(target), "odb_sha256": digest, "odb_bytes": size,
              "extractor": str(script), "extractor_sha256": EXTRACTOR_SHA256, "level_a_original": ORIGINAL_SOURCE,
              "level_a_accessed": False}
    _write_json(RUN / "copy.json", record)
    return record


def extract() -> dict:
    attempts = RUN / "logs" / "attempt.json"
    if attempts.exists():
        raise Refused("an extraction attempt is already recorded: one run, no retry")
    odb = RUN / "input" / f"{JOB}.odb"
    script = RUN / "scripts" / "extract_odb.py"
    if sha256(odb) != JOB_FILES[".odb"][1] or sha256(script) != EXTRACTOR_SHA256:
        raise Refused("the working copy or the extractor copy changed")
    if (RUN / "output").exists():
        raise Refused("the output folder exists")
    logs = RUN / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    command = ["cmd.exe", "/c", str(ABAQUS), "python", str(script), "--odb", str(odb), "--output",
               str(RUN / "output"), "--start-mode", str(START_MODE), "--end-mode", str(END_MODE)]
    record = {"started": now(), "command": command, "cwd": str(logs), "temp": str(logs)}
    _write_json(attempts, record)  # written BEFORE the run
    env = dict(os.environ, TEMP=str(logs), TMP=str(logs))
    with open(logs / "abaqus_python_run.log", "w", encoding="utf-8", errors="replace") as log:
        code = subprocess.run(command, cwd=logs, env=env, stdout=log, stderr=subprocess.STDOUT,
                              stdin=subprocess.DEVNULL).returncode
    record.update(ended=now(), exit_code=code, manifest_written=(RUN / "output" / "manifest.json").is_file())
    _write_json(attempts, record)
    return record


def postflight() -> dict:
    record = {"checked": now(), "v2_copy": {}, "working_copy": None, "unlisted_in_v2_folder": [],
              "solver_artefacts_in_run": []}
    for suffix, (size, digest) in JOB_FILES.items():
        record["v2_copy"][suffix] = _check(V2_JOB / (JOB + suffix), size, digest)["sha256"]
    record["working_copy"] = _check(RUN / "input" / f"{JOB}.odb", *JOB_FILES[".odb"])["sha256"]
    manifest = json.loads(V2_MANIFEST.read_text(encoding="utf-8"))
    listed = {Path(f["copy"]).resolve() for f in manifest["files"] if f.get("specimen") == "SP10"}
    record["unlisted_in_v2_folder"] = sorted(str(p) for p in (V2_ROOT / "SP-10").rglob("*")
                                             if p.is_file() and p.resolve() not in listed)
    record["solver_artefacts_in_run"] = sorted(str(p) for p in RUN.rglob("*") if p.is_file()
                                               and p.suffix.lower() in SOLVER_ARTEFACTS)
    record["extractor_unchanged"] = sha256(EXTRACTOR) == EXTRACTOR_SHA256
    if record["unlisted_in_v2_folder"] or record["solver_artefacts_in_run"] or not record["extractor_unchanged"]:
        _write_json(RUN / "postflight.json", record | {"result": "REFUSED"})
        raise Refused("postflight: " + json.dumps(record, ensure_ascii=False)[:400])
    _write_json(RUN / "postflight.json", record | {"result": "UNCHANGED"})
    return record


def _inp_instances(path: Path) -> list:
    names = []
    with open(path, encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if line[:10].lower() == "*instance,":
                found = re.search(r"name=([^,\s]+)", line, re.I)
                names.append(found.group(1).upper())
    return names


def verify() -> dict:
    out = RUN / "output"
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    problems = []
    tables = dat_tables((V2_JOB / f"{JOB}.dat").read_text(errors="replace"))
    by_step = {step: {mode: (eig, hz) for mode, eig, hz in rows} for step, rows in tables}
    if sorted(by_step) != [1, 2] or len(by_step[1]) != 15 or len(by_step[2]) != 25:
        problems.append(f"unexpected .dat tables: {[(s, len(r)) for s, r in tables]}")
    if manifest.get("format_version") != 2:
        problems.append("not extraction format 2")
    if manifest.get("step_name") != STEP:
        problems.append(f"step {manifest.get('step_name')!r} is not {STEP!r}")
    modes = manifest["modes"]
    numbers = [m["mode"] for m in modes]
    if numbers != list(range(START_MODE, END_MODE + 1)):
        problems.append(f"modes {numbers} are not {START_MODE}–{END_MODE}")
    # the step's own history output (EIGFREQ, EIGVAL) holds every mode of the step at full precision: an independent
    # check of the ODB against the .dat, beside the frame frequency the package carries
    history = {h["name"]: {int(round(x)): v for x, v in h["data"]} for h in manifest.get("history", [])
               if h["name"] in ("EIGFREQ", "EIGVAL")}
    eigfreq, eigval = history.get("EIGFREQ", {}), history.get("EIGVAL", {})
    if sorted(eigfreq) != list(range(1, 26)) or sorted(eigval) != list(range(1, 26)):
        problems.append("the ODB history does not hold EIGFREQ / EIGVAL of modes 1–25")
    history_rows = []
    for mode, (eig, hz) in sorted(by_step.get(2, {}).items()):
        f, v = eigfreq.get(mode), eigval.get(mode)
        equal = (f is not None and v is not None and same_printed_value(f, hz)
                 and abs(v - eig) <= 1e-5 * max(abs(eig), 1.0))
        if not equal:
            problems.append(f"mode {mode}: ODB history EIGFREQ {f} / EIGVAL {v} differs from the .dat {hz} / {eig}")
        history_rows.append({"mode": mode, "odb_eigfreq_hz": f, "odb_eigval": v, "dat_hz": hz, "dat_eigval": eig,
                             "equal_to_dat": equal})
    rows = []
    for entry in modes:
        mode, odb_hz = entry["mode"], float(entry["frequency_hz"])
        dat2 = by_step.get(2, {}).get(mode)
        dat1 = by_step.get(1, {}).get(mode)
        equal2 = dat2 is not None and same_printed_value(odb_hz, dat2[1])
        equal1 = None if dat1 is None else same_printed_value(odb_hz, dat1[1])
        if not equal2 or equal1 is False:
            problems.append(f"mode {mode}: ODB {odb_hz} Hz differs from the .dat")
        rows.append({"mode": mode, "odb_hz": odb_hz, "odb_eigfreq_hz": eigfreq.get(mode),
                     "dat_step2_hz": dat2[1] if dat2 else None, "dat_step1_hz": dat1[1] if dat1 else None,
                     "abs_diff_hz": round(abs(eigfreq[mode] - dat2[1]), 6) if dat2 and mode in eigfreq else None,
                     "equal_to_dat": equal2 and equal1 is not False, "above_220_hz": odb_hz > 220.04 + 1e-9,
                     "node_count": entry["node_count"], "file": entry["file"]})
    geometry = out / manifest["geometry_file"]
    instances, count = {}, 0
    with open(geometry, newline="", encoding="utf-8") as stream:
        reader = csv.reader(stream)
        next(reader)
        for row in reader:
            instances[row[0]] = instances.get(row[0], 0) + 1
            count += 1
    if count != manifest["geometry_node_count"]:
        problems.append("geometry.csv row count differs from the manifest")
    if any(m["node_count"] != count for m in modes):
        problems.append("a mode file does not hold every geometry node")
    inp_instances = _inp_instances(V2_JOB / f"{JOB}.inp")
    if sorted(i.upper() for i in instances) != sorted(inp_instances):
        problems.append(f"ODB instances {sorted(instances)} are not the INP instances {sorted(inp_instances)}")
    files = sorted(p for p in out.iterdir() if p.is_file())
    identity = {"package": str(out), "manifest_sha256": sha256(manifest_path),
                "files": {p.name: {"bytes": p.stat().st_size, "sha256": sha256(p)} for p in files},
                "total_bytes": sum(p.stat().st_size for p in files)}
    record = {
        "verified": now(), "result": "PASS" if not problems else "REFUSED", "problems": problems,
        "labels": LABELS,
        "source": {"job": JOB, "odb_v2_copy": str(V2_JOB / f"{JOB}.odb"), "odb_sha256": JOB_FILES[".odb"][1],
                   "odb_bytes": JOB_FILES[".odb"][0], "dat_sha256": JOB_FILES[".dat"][1],
                   "inp_sha256": JOB_FILES[".inp"][1], "level_a_original": ORIGINAL_SOURCE,
                   "odb_name_in_manifest": manifest.get("odb_name"),
                   "analysis_title": manifest.get("analysis_title")},
        "extraction": {"extractor_sha256": EXTRACTOR_SHA256, "step": manifest.get("step_name"),
                       "requested": [START_MODE, END_MODE], "modes": len(modes),
                       "frequency_range_hz": [min(r["odb_hz"] for r in rows), max(r["odb_hz"] for r in rows)],
                       "modes_above_220_hz": [r["mode"] for r in rows if r["above_220_hz"]]},
        "geometry": {"nodes": count, "instances": instances, "inp_instances": inp_instances},
        "frequencies": rows,
        "odb_history_vs_dat": history_rows,
        "identity": identity,
    }
    _write_json(RUN / "PACKAGE_IDENTITY.json", record)
    if problems:
        raise Refused("verify: " + "; ".join(problems))
    archived = {k: v for k, v in record.items() if k != "identity"} | {
        "identity": {"manifest_sha256": identity["manifest_sha256"], "files": identity["files"],
                     "total_bytes": identity["total_bytes"],
                     "location": "outside Git: " + str(out)}}
    _write_json(DOCS_OUT / "SP10_FE_PACKAGE.json", archived)
    with open(DOCS_OUT / "SP10_FE_VS_DAT.csv", "w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["mode", "odb_hz", "odb_eigfreq_hz", "dat_step2_hz", "dat_step1_hz", "abs_diff_hz",
                         "equal_to_dat", "above_220_hz", "node_count"])
        for r in rows:
            writer.writerow([r["mode"], f"{r['odb_hz']:.8g}", f"{r['odb_eigfreq_hz']:.8g}", r["dat_step2_hz"],
                             "" if r["dat_step1_hz"] is None else r["dat_step1_hz"], r["abs_diff_hz"],
                             r["equal_to_dat"], r["above_220_hz"], r["node_count"]])
    return record


STEPS = {"preflight": preflight, "copy": copy, "extract": extract, "postflight": postflight, "verify": verify}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in STEPS:
        raise SystemExit(__doc__)
    result = STEPS[sys.argv[1]]()
    print(json.dumps(result, indent=1, ensure_ascii=False)[:6000])
