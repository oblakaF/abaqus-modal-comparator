"""WINDOWS PORTABLE RC5: build the portable folder AbaqusModalComparator_RC5 of the new interface and its ZIP.

The program after the single-plate integration (PRIORITY-1-10, PR #122): NEW-GUI.6 with Plate Study A-D (D. FE
Response, C. Physical Readiness) and Research Results. The approach of RC4-F1 (packaging/portable_rc4_f1; RC1-RC4-F1
unchanged). Run it with the Python of a build environment made from requirements-build.txt (not the program's .venv):

    <build venv>\\Scripts\\python.exe packaging\\portable_rc5\\build_portable.py --out <new folder outside the repo>

Steps:
1. The tracked program files (src, docs, packaging) must be committed: the build is the commit it reports.
2. The build folder must be new or empty: nothing that exists there (an earlier RC build, an RC5 build) is deleted or
   replaced.
3. PyInstaller (onedir) freezes the new interface, with no console window.
4. The tracked reference files the program reads are put in ``docs`` beside the program: a frozen module's
   ``__file__`` is ``_internal\\<package>\\<module>.py``, so ``Path(__file__).parents[2]`` (the repository root in the
   source tree) is the portable folder.
5. Checks: the archived research files of PRIORITY-1-4 and 6 and the PRIORITY-2 table of the FE Response Workbench load
   by their recorded SHA-256 from the portable folder; the synthetic single-plate demonstration opens from it and its
   offline study runs (SYNTHETIC); the archive of the physical readiness review verifies; no measurement, FE model, FE
   result, extracted FE package file or solver file is in the build.
6. BUILD_INFO.json (commit, versions, sizes, EXE SHA-256), README_PORTABLE.txt and PACKAGE_SHA256.txt (every file of
   the folder) are written; the folder is zipped and the ZIP is checked against the folder. The ZIP's size and
   SHA-256 are written beside it (``<name>.zip.sha256``, ``build_result.json``).
7. With --desktop, the folder, the ZIP and its ``.zip.sha256`` are copied to the Windows desktop. An existing RC5
   copy there is never replaced (there is no --replace); the RC1-RC4-F1 copies are never touched.

``--verify <folder>`` checks a portable folder (for example one unpacked from the ZIP on another computer) against
its PACKAGE_SHA256.txt.

Nothing scientific is decided or changed here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
NAME = "AbaqusModalComparator_RC5"
EXE = "AbaqusModalComparator.exe"
SPEC = HERE / f"{NAME}.spec"
PACKAGE_LIST = "PACKAGE_SHA256.txt"
EARLIER = ("RC1", "RC2", "RC3", "RC3_F1", "RC3_F2", "RC4", "RC4_F1")
PROTECTED_DESKTOP = tuple(f"AbaqusModalComparator_{name}{suffix}" for name in EARLIER
                          for suffix in ("", ".zip"))  # never written by this build
# The reference files the program reads (JSON records, CSV tables, Markdown, text, SHA-256 lists); figures and Word
# documents are not read by the program and stay out.
DOC_SUFFIXES = {".json", ".csv", ".md", ".txt", ".sha256"}
DOC_MAX_BYTES = 2_000_000
# Never in the build: measurements, FE models and results, solver scratch (they are chosen by the user).
FORBIDDEN_SUFFIXES = {".odb", ".unv", ".uff", ".lms", ".svd", ".inp", ".sta", ".msg", ".prt", ".com", ".sim", ".res",
                      ".fil", ".mdl", ".stt", ".cae", ".jnl", ".rpy", ".lck", ".023", ".abq", ".pac", ".sel"}
SOLVER_DAT_ROOTS = ("docs",)  # an Abaqus .dat is refused where data live; libraries ship their own .dat files
DATA_ROOT_ONLY = {".dat", ".npz"}  # an FE shape pack (.npz) too; matplotlib ships its own sample .npz files
# the files of an extracted FE package (the SP-10 package of PRIORITY-6 is 3.1 GB): chosen by the user, never shipped
PACKAGE_FILE = re.compile(r"^(manifest\.json|geometry\.csv|mode_\d{4}\.csv)$", re.IGNORECASE)
TRACKED_ROOTS = ("src", "docs", "packaging", "requirements-new-gui.txt")
README = """Abaqus-Simcenter Modal Comparator - portable new interface ({name})
WORKING RESEARCH PREVIEW for one single CFRP plate. It identifies no material value.

Start: double-click {exe}. No Python, VS Code or Abaqus installation is needed, and the program starts no Abaqus.
Keep the folder together: {exe}, _internal and docs belong to one another. The folder may be copied or moved
anywhere, including a path with spaces. PACKAGE_SHA256.txt lists the SHA-256 of every file of the folder.

Not included: experimental files (UNV, UFF, LMS), Abaqus models and results (INP, ODB, DAT, SVD), extracted FE
packages (for example the 3.1 GB SP-10 package of PRIORITY-6) and solver files. Choose them in the program:
- Workspace: Choose file... for the FE results (an extracted FE package manifest.json) and the experimental file.
- File > Choose a known new experimental source...: Choose folder... points to the delivery folder wherever it lies.
- Plate Study > A: Choose FE archive folder... points to the folder that holds the plate's FE family.
- Plate Study > D: Choose FE baseline manifest..., Choose baseline INP (optional)... and Choose folder of FE states...
  point to the extracted FE packages of one FE model.
- Research Results: Load local research record... reads a matching_record.json you choose.

Plate Study:
- A. Current PLATE Study: the archived PLATE study; the iterative estimation is NOT AUTHORISED.
- B. New Single Plate - Research Workbench: a research study of any single rectangular CFRP plate. Open study... >
  docs\\examples\\generic_single_plate_demo\\DEMO_STUDY.json opens a SYNTHETIC demonstration (never a physical
  experiment). The physical offline fit is blocked.
- C. Physical Readiness - Review: the dossier of the scientific readiness of one plate (a plan and a request, never a
  run order).
- D. FE Response: the 14 elastic FE branches of an FE family tracked by MAC between extracted FE packages, the
  central sensitivities and the G12 / E What-If. Every value there is FE_ONLY; the What-If is a
  FE_ONLY_LOCAL_PREDICTION, not an Abaqus solve.

Scientific status (unchanged): FREQUENCY_ONLY, MODE_PAIRS_NOT_CONFIRMED, NOT_READY_FOR_IDENTIFICATION. The M11 FE7
19.07217 Hz and the PolyMAX 18.6307 Hz record of 2026-10-27 are not a confirmed mode pair. M8 GATE NOT_MET,
D-077 NO_GLOBAL_PARAMETER_VALUE, production Auto-ID BLOCKED. Reports are written only into a folder you choose.

Build: commit {commit} ({branch}), {built}. See BUILD_INFO.json.
"""


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, check=True, capture_output=True, text=True).stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tracked_documents() -> list[str]:
    files = git("ls-files", "-z", "docs").split("\0")
    return sorted(f for f in files if f and PurePosixPath(f).suffix.lower() in DOC_SUFFIXES)


def copy_documents(target: Path) -> list[dict]:
    copied = []
    for relative in tracked_documents():
        source = REPO.joinpath(*PurePosixPath(relative).parts)
        size = source.stat().st_size
        if size > DOC_MAX_BYTES:
            raise SystemExit(f"refused: {relative} is {size} bytes (a reference file is at most {DOC_MAX_BYTES})")
        destination = target.joinpath(*PurePosixPath(relative).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)  # the working-copy bytes the program reads in the source tree
        copied.append({"path": relative, "bytes": size})
    return copied


def forbidden_files(folder: Path) -> list[str]:
    bad = []
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        top = path.relative_to(folder).parts[0]
        if (suffix in FORBIDDEN_SUFFIXES or (suffix in DATA_ROOT_ONLY and top in SOLVER_DAT_ROOTS)
                or (top in SOLVER_DAT_ROOTS and PACKAGE_FILE.match(path.name))):
            bad.append(path.relative_to(folder).as_posix())
    return sorted(bad)


def check_contents(folder: Path) -> None:
    bad = forbidden_files(folder)
    if bad:
        raise SystemExit("refused: data or solver files in the build: " + ", ".join(bad[:20]))


def check_research(folder: Path) -> dict:
    """The archived research tables, the PRIORITY-6 SP-10 records and the PRIORITY-2 table of the FE Response
    Workbench load from the portable folder exactly as from the repository."""
    sys.path.insert(0, str(REPO / "src"))
    from services import research_results_reader as rr
    from services import sp10_fe_research as sf

    snapshot = rr.load_snapshot(folder)
    results = sf.load_results(folder)
    rows = sf.frequency_diagnostic(results, [(r.exp_no, r.f_exp_hz) for r in snapshot.matching["SP-10"]])
    return {"single_plate_demo": check_demo(folder), "physical_review": check_review(folder),
            "fe_response": check_fe_response(folder),
            "matching_rows": {k: len(v) for k, v in snapshot.matching.items()},
            "sensitivity_terms": len(snapshot.sensitivities),
            "scenarios": [s.key for s in snapshot.scenarios],
            "sp10_priority6": {"fe_modes": [m.number for m in results.fe_modes][0::18],
                               "fe_mode_count": len(results.fe_modes),
                               "fe_manifest_sha256": results.fe_manifest_sha256,
                               "diagnostic_rows": len(rows),
                               "exp11_exp12": [f"EXP{r.exp_no} FE{r.nearest.fe} {r.nearest.df_percent:+.2f} %"
                                               for r in rows[10:]]}}


def check_demo(folder: Path) -> dict:
    """The synthetic single-plate demonstration opens from the portable folder and its offline study runs."""
    from services import generic_plate_offline_study as off
    from services import generic_plate_workbench as wb

    demo = folder / "docs" / "examples" / "generic_single_plate_demo"
    study = wb.open_study(demo / "DEMO_STUDY.json")
    study = wb.set_diagnostics(study, wb.load_synthetic_inputs(demo / "DEMO_SYNTHETIC_INPUTS.json", study))
    study = off.with_declaration(off.with_sensitivities(study, demo / "DEMO_SENSITIVITIES.json"),
                                 demo / "DEMO_DECLARATION.json")
    evidence = wb.evidence_result(study)
    states = off.states(study, evidence)
    result = off.run_offline_study(study, evidence, states["sensitivities"], states["declaration"])
    return {"specimen": study.passport.physical_specimen_id, "evidence": evidence.status, "lm": result["status"],
            "candidate": {k: round(v["value"], 1) for k, v in result["candidate"].items()},
            "labels": result["labels"][:3]}


def check_review(folder: Path) -> dict:
    """PRIORITY-9: the archive the physical readiness review cites verifies in the portable folder, and the review of
    the synthetic demonstration (a plate of another geometry) builds there."""
    from services import generic_plate_offline_study as off
    from services import generic_plate_workbench as wb
    from services import plate_physical_review as pr

    archive = [row for row in pr.archive_check(folder) if row[0] in {v[0] for v in pr.ARCHIVE_FILES.values()}]
    bad = [row for row in archive if row[2] != pr.VERIFIED]
    if bad:
        raise SystemExit(f"refused: the review's archive does not verify in the portable folder: {bad}")
    demo = folder / "docs" / "examples" / "generic_single_plate_demo"
    study = wb.open_study(demo / "DEMO_STUDY.json")
    study = off.with_sensitivities(wb.set_diagnostics(study, wb.load_synthetic_inputs(
        demo / "DEMO_SYNTHETIC_INPUTS.json", study)), demo / "DEMO_SENSITIVITIES.json")
    record = pr.build_review(pr.inputs_from_study(study))
    return {"archive_files_verified": len(archive), "demo_review": record["states"],
            "demo_integrity": pr.integrity_state(record),
            "demo_questions": len(record["owner_evidence_request"]["questions"]),
            "documents": sorted(pr.documents(record))}


def check_fe_response(folder: Path) -> dict:
    """PRIORITY-10: the archived central sensitivities the FE Response Workbench compares with (the SHA-checked
    PRIORITY-2 table) load from the portable folder; no FE package is read here."""
    from services import single_plate_fe_response as fr

    archived = fr.archived_result(folder)
    return {"status": archived["status"], "source": archived["source"], "source_sha256": archived["source_sha256"],
            "terms": len(archived["central"]), "fe7_f0_hz": next((t["f0_hz"] for t in archived["central"]
                                                                   if t["term"] == "FE7"), None),
            "rank": archived["rank"]}


def folder_files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.is_file())


def folder_size(folder: Path) -> tuple[int, int]:
    files = folder_files(folder)
    return len(files), sum(p.stat().st_size for p in files)


def write_package_list(folder: Path) -> Path:
    """PACKAGE_SHA256.txt: the SHA-256 of every file of the folder (``<sha256> *<relative path>``), itself excluded."""
    target = folder / PACKAGE_LIST
    lines = [f"{sha256(p)} *{p.relative_to(folder).as_posix()}" for p in folder_files(folder) if p != target]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def verify_folder(folder: Path) -> dict:
    """A portable folder against its PACKAGE_SHA256.txt: every listed file present with its SHA-256, nothing else but
    the list itself."""
    folder = Path(folder)
    listed = {}
    for line in (folder / PACKAGE_LIST).read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, relative = line.split(" *", 1)
            listed[relative] = digest
    present = {p.relative_to(folder).as_posix() for p in folder_files(folder)} - {PACKAGE_LIST}
    changed = sorted(r for r in listed if r in present and sha256(folder / r) != listed[r])
    result = {"files": len(listed), "missing": sorted(set(listed) - present), "extra": sorted(present - set(listed)),
              "changed": changed}
    result["verified"] = not (result["missing"] or result["extra"] or changed)
    return result


def make_zip(folder: Path, archive: Path) -> None:
    tmp = archive.with_suffix(".zip.partial")
    # refused before anything is written: os.rename replaces its target on POSIX, so it is not the guard
    for existing in (archive, tmp):
        if existing.exists():
            raise SystemExit(f"refused: {existing} exists (an existing ZIP is never replaced)")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(folder.rglob("*")):
            zf.write(path, Path(folder.name) / path.relative_to(folder))
    os.rename(tmp, archive)


def check_zip(folder: Path, archive: Path) -> dict:
    """The ZIP holds exactly the files of the folder, each intact (CRC)."""
    with zipfile.ZipFile(archive) as zf:
        bad = zf.testzip()
        names = {n for n in zf.namelist() if not n.endswith("/")}
    expected = {f"{folder.name}/{p.relative_to(folder).as_posix()}" for p in folder_files(folder)}
    if bad or names != expected:
        raise SystemExit(f"refused: the ZIP does not match the folder (bad {bad}, missing "
                         f"{sorted(expected - names)[:5]}, extra {sorted(names - expected)[:5]})")
    return {"zip_files": len(names), "crc": "OK"}


def versions() -> dict:
    from importlib import metadata

    names = ("PySide6-Essentials", "shiboken6", "numpy", "scipy", "matplotlib", "pillow", "openpyxl", "pyuff", "pypdf",
             "pyinstaller", "pyinstaller-hooks-contrib")
    return {n: metadata.version(n) for n in names}


def refuse_existing(out: Path) -> None:
    """The build folder is new or empty: an earlier RC build or an RC5 build there is never deleted or replaced."""
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"refused: the build folder is not empty (nothing there is deleted or replaced): {out}")


def desktop_targets(desktop: Path) -> tuple:
    targets = (desktop / NAME, desktop / f"{NAME}.zip", desktop / f"{NAME}.zip.sha256")
    if any(t.name in PROTECTED_DESKTOP for t in targets):  # a guard: this build never writes the earlier copies
        raise SystemExit("refused: the RC1-RC4-F1 desktop copies are not written by the RC5 build")
    existing = [str(t) for t in targets if t.exists()]
    if existing:
        raise SystemExit("refused: an RC5 desktop copy exists (it is never replaced): " + ", ".join(existing))
    return targets


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, help="new or empty build folder outside the repository")
    parser.add_argument("--allow-dirty", action="store_true", help="trial build of uncommitted program files")
    parser.add_argument("--desktop", action="store_true", help="copy the folder and the ZIP to the desktop")
    parser.add_argument("--verify", type=Path, help="check a portable folder against its PACKAGE_SHA256.txt")
    args = parser.parse_args(argv)
    if args.verify:
        result = verify_folder(args.verify)
        print(json.dumps(result, indent=1))
        return 0 if result["verified"] else 1
    if not args.out:
        parser.error("--out is required")
    out = args.out.resolve()
    if out == REPO or REPO in out.parents:
        raise SystemExit("refused: the build folder must be outside the repository")
    refuse_existing(out)
    # a changed tracked file, or an untracked file where the build takes code from (untracked docs are not shipped)
    dirty = "\n".join(x for x in (git("status", "--porcelain", "--untracked-files=no", "--", *TRACKED_ROOTS),
                                  git("status", "--porcelain", "--untracked-files=all", "--", "src", "packaging"))
                      if x)
    if dirty and not args.allow_dirty:
        raise SystemExit("refused: uncommitted program files (the build must be a commit):\n" + dirty)
    commit, branch = git("rev-parse", "HEAD"), git("rev-parse", "--abbrev-ref", "HEAD")
    desktop = None
    if args.desktop:  # refused before anything is built
        desktop = desktop_targets(Path(subprocess.run(
            ["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
            capture_output=True, text=True, check=True).stdout.strip()))

    dist, work = out / "dist", out / "work"
    out.mkdir(parents=True, exist_ok=True)
    folder, archive = dist / NAME, dist / f"{NAME}.zip"
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN",
                    "--distpath", str(dist), "--workpath", str(work), str(SPEC)], cwd=out, check=True)
    documents = copy_documents(folder)  # tracked paths begin with docs/
    check_contents(folder)
    research = check_research(folder)
    built = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (folder / "README_PORTABLE.txt").write_text(
        README.format(name=NAME, exe=EXE, commit=commit, branch=branch, built=built), encoding="utf-8")
    count, size = folder_size(folder)
    info = {"name": NAME, "commit": commit, "branch": branch, "dirty": bool(dirty), "built_utc": built,
            "python": sys.version.split()[0], "platform": platform.platform(), "packages": versions(), "exe": EXE,
            "exe_bytes": (folder / EXE).stat().st_size, "exe_sha256": sha256(folder / EXE),
            "files": count + 2, "bytes_before_info": size,  # + BUILD_INFO.json and PACKAGE_SHA256.txt
            "reference_files": len(documents), "reference_bytes": sum(d["bytes"] for d in documents),
            "package_list": PACKAGE_LIST, "research_check": research}
    (folder / "BUILD_INFO.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    write_package_list(folder)
    verified = verify_folder(folder)
    if not verified["verified"]:
        raise SystemExit(f"refused: the folder does not match its package list: {verified}")
    make_zip(folder, archive)
    zipped = check_zip(folder, archive)
    count, size = folder_size(folder)
    zip_sha = sha256(archive)
    (dist / f"{NAME}.zip.sha256").write_text(f"{zip_sha} *{NAME}.zip\n", encoding="utf-8")
    result = {"folder": str(folder), "zip": str(archive), "files": count, "bytes": size,
              "exe_bytes": info["exe_bytes"], "exe_sha256": info["exe_sha256"],
              "zip_bytes": archive.stat().st_size, "zip_sha256": zip_sha, "zip_check": zipped,
              "package_list_sha256": sha256(folder / PACKAGE_LIST), "commit": commit, "branch": branch,
              "dirty": bool(dirty), "python": info["python"], "packages": info["packages"], "research_check": research}
    if desktop:
        shutil.copytree(folder, desktop[0])
        shutil.copy2(archive, desktop[1])
        shutil.copy2(dist / f"{NAME}.zip.sha256", desktop[2])
        if sha256(desktop[1]) != zip_sha or not verify_folder(desktop[0])["verified"]:
            raise SystemExit("refused: the desktop copy does not match the build")
        result["desktop"] = [str(t) for t in desktop]
    (out / "build_result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
