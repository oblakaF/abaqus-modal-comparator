"""WINDOWS PORTABLE RC2: build the portable folder AbaqusModalComparator_RC2 of the new interface and its ZIP.

The approach of RC1 (packaging/portable_rc1, unchanged), for the program with the PRIORITY-7 SP-10 integration. Run it
with the Python of a build environment made from requirements-build.txt (not the program's .venv):

    <build venv>\\Scripts\\python.exe packaging\\portable_rc2\\build_portable.py --out <folder outside the repository>

Steps:
1. The tracked program files (src, docs, packaging) must be committed: the build is the commit it reports.
2. PyInstaller (onedir) freezes the new interface, with no console window.
3. The tracked reference files the program reads are put in ``docs`` beside the program: a frozen module's
   ``__file__`` is ``_internal\\<package>\\<module>.py``, so ``Path(__file__).parents[2]`` (the repository root in the
   source tree) is the portable folder. The PRIORITY-6 records of SP-10 are among them.
4. Checks: the archived research files of PRIORITY-1–4 and of PRIORITY-6 load by their recorded SHA-256 from the
   portable folder; no measurement, FE model, FE result, extracted FE package file or solver file is in the build.
5. BUILD_INFO.json (commit, versions, sizes) and README_PORTABLE.txt are written; the folder is zipped.
6. With --desktop, the folder and the ZIP are copied to the Windows desktop (an existing RC2 copy is replaced only
   with --replace; the RC1 copies there are never touched).

Nothing scientific is decided or changed here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
NAME = "AbaqusModalComparator_RC2"
EXE = "AbaqusModalComparator.exe"
SPEC = HERE / f"{NAME}.spec"
PROTECTED_DESKTOP = ("AbaqusModalComparator_RC1", "AbaqusModalComparator_RC1.zip")  # never replaced by this build
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

Start: double-click {exe}. No Python, VS Code or Abaqus installation is needed, and the program starts no Abaqus.
Keep the folder together: {exe}, _internal and docs belong to one another. The folder may be copied or moved
anywhere, including a path with spaces.

Not included: experimental files (UNV, UFF, LMS), Abaqus models and results (INP, ODB, DAT), extracted FE packages
(for example the 3.1 GB SP-10 package of PRIORITY-6) and solver files. Choose them in the program:
- Workspace: Choose file... for the FE results (an extracted FE package manifest.json) and the experimental file.
- File > Choose a known new experimental source...: Choose folder... points to the delivery folder wherever it lies.
- Plate Study: Choose FE archive folder... points to the folder that holds the plate's FE family.
- Research Results: Load local research record... reads a matching_record.json you choose.

Research Results reads the archived tables in docs\\research, including the SP-10 FE results of PRIORITY-6 (FE7-FE25
frequencies and the frequency-only diagnostic of EXP1-EXP12); it never reads an FE package. Every value there is
RESEARCH_ONLY / FREQUENCY_ONLY_DIAGNOSTIC / NOT_A_MATERIAL_PROPERTY; a nearest frequency is not a mode pair and
SP-10 261029 has no physical registration (PHYSICAL_REGISTRATION_NOT_VERIFIED). Reports are written only into a
folder you choose.

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


def check_contents(folder: Path) -> None:
    bad = []
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        top = path.relative_to(folder).parts[0]
        if (suffix in FORBIDDEN_SUFFIXES or (suffix in DATA_ROOT_ONLY and top in SOLVER_DAT_ROOTS)
                or (top in SOLVER_DAT_ROOTS and PACKAGE_FILE.match(path.name))):
            bad.append(str(path.relative_to(folder)))
    if bad:
        raise SystemExit("refused: data or solver files in the build: " + ", ".join(sorted(bad)[:20]))


def check_research(folder: Path) -> dict:
    """The archived research tables and the PRIORITY-6 SP-10 records load from the portable folder exactly as from
    the repository."""
    sys.path.insert(0, str(REPO / "src"))
    from services import research_results_reader as rr
    from services import sp10_fe_research as sf

    snapshot = rr.load_snapshot(folder)
    results = sf.load_results(folder)
    rows = sf.frequency_diagnostic(results, [(r.exp_no, r.f_exp_hz) for r in snapshot.matching["SP-10"]])
    return {"matching_rows": {k: len(v) for k, v in snapshot.matching.items()},
            "sensitivity_terms": len(snapshot.sensitivities),
            "scenarios": [s.key for s in snapshot.scenarios],
            "sp10_priority6": {"fe_modes": [m.number for m in results.fe_modes][0::18],
                               "fe_mode_count": len(results.fe_modes),
                               "fe_manifest_sha256": results.fe_manifest_sha256,
                               "diagnostic_rows": len(rows),
                               "exp11_exp12": [f"EXP{r.exp_no} FE{r.nearest.fe} {r.nearest.df_percent:+.2f} %"
                                               for r in rows[10:]]}}


def folder_size(folder: Path) -> tuple[int, int]:
    files = [p for p in folder.rglob("*") if p.is_file()]
    return len(files), sum(p.stat().st_size for p in files)


def make_zip(folder: Path, archive: Path) -> None:
    tmp = archive.with_suffix(".zip.partial")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(folder.rglob("*")):
            zf.write(path, Path(folder.name) / path.relative_to(folder))
    os.replace(tmp, archive)


def versions() -> dict:
    from importlib import metadata

    names = ("PySide6-Essentials", "shiboken6", "numpy", "scipy", "matplotlib", "pillow", "openpyxl", "pyuff", "pypdf",
             "pyinstaller")
    return {n: metadata.version(n) for n in names}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, type=Path, help="build folder outside the repository")
    parser.add_argument("--allow-dirty", action="store_true", help="trial build of uncommitted program files")
    parser.add_argument("--desktop", action="store_true", help="copy the folder and the ZIP to the desktop")
    parser.add_argument("--replace", action="store_true", help="replace an earlier RC2 desktop copy")
    args = parser.parse_args(argv)
    out = args.out.resolve()
    if out == REPO or REPO in out.parents:
        raise SystemExit("refused: the build folder must be outside the repository")
    # a changed tracked file, or an untracked file where the build takes code from (untracked docs are not shipped)
    dirty = "\n".join(x for x in (git("status", "--porcelain", "--untracked-files=no", "--", *TRACKED_ROOTS),
                                  git("status", "--porcelain", "--untracked-files=all", "--", "src", "packaging"))
                      if x)
    if dirty and not args.allow_dirty:
        raise SystemExit("refused: uncommitted program files (the build must be a commit):\n" + dirty)
    commit, branch = git("rev-parse", "HEAD"), git("rev-parse", "--abbrev-ref", "HEAD")

    dist, work = out / "dist", out / "work"
    out.mkdir(parents=True, exist_ok=True)
    folder, archive = dist / NAME, dist / f"{NAME}.zip"
    for old in (folder, archive):
        if old.is_dir():
            shutil.rmtree(old)
        elif old.exists():
            old.unlink()
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
            "python": sys.version.split()[0], "packages": versions(), "exe": EXE,
            "exe_sha256": sha256(folder / EXE), "files": count + 1, "bytes_before_info": size,
            "reference_files": len(documents), "reference_bytes": sum(d["bytes"] for d in documents),
            "research_check": research}
    (folder / "BUILD_INFO.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    make_zip(folder, archive)
    count, size = folder_size(folder)
    result = {"folder": str(folder), "zip": str(archive), "files": count, "bytes": size,
              "zip_bytes": archive.stat().st_size, "zip_sha256": sha256(archive), "exe_sha256": info["exe_sha256"],
              "commit": commit, "dirty": bool(dirty), "research_check": research}
    if args.desktop:
        desktop = Path(subprocess.run(["powershell", "-NoProfile", "-Command",
                                       "[Environment]::GetFolderPath('Desktop')"],
                                      capture_output=True, text=True, check=True).stdout.strip())
        targets = (desktop / NAME, desktop / f"{NAME}.zip")
        if any(t.name in PROTECTED_DESKTOP for t in targets):  # a guard: this build never writes the RC1 copies
            raise SystemExit("refused: the RC1 desktop copies are not replaced by the RC2 build")
        existing = [str(t) for t in targets if t.exists()]
        if existing and not args.replace:
            raise SystemExit("refused: a desktop copy exists (use --replace): " + ", ".join(existing))
        if targets[0].exists():
            shutil.rmtree(targets[0])
        shutil.copytree(folder, targets[0])
        shutil.copy2(archive, targets[1])
        result["desktop"] = [str(t) for t in targets]
    (out / "build_result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
