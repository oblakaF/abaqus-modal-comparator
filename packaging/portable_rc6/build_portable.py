"""WINDOWS PORTABLE RC6: build the portable folder AbaqusModalComparator_RC6 of the new interface and its ZIP.

The program after the single-plate integration (PRIORITY-1-10, PR #122): NEW-GUI.6 with Plate Study A-D (D. FE
Response, C. Physical Readiness) and Research Results, plus the direct ODB import of PRIORITY-0 (RC6): Extract modal
results... runs the packaged extractor through Abaqus Python on the user's confirmation. The approach of RC5
(packaging/portable_rc5; RC1-RC5
unchanged). Run it with the Python of a build environment made from requirements-build.txt (not the program's .venv):

    <build venv>\\Scripts\\python.exe packaging\\portable_rc6\\build_portable.py --out <new folder outside the repo>

Steps:
1. The tracked program files (src, docs, packaging) must be committed: the build is the commit it reports.
2. The build folder must be new or empty: nothing that exists there (an earlier RC build, an RC6 build) is deleted or
   replaced.
3. PyInstaller (onedir) freezes the new interface, with no console window.
4. The tracked reference files the program reads are put in ``docs`` beside the program: a frozen module's
   ``__file__`` is ``_internal\\<package>\\<module>.py``, so ``Path(__file__).parents[2]`` (the repository root in the
   source tree) is the portable folder.
5. Checks: the archived research files of PRIORITY-1-4 and 6 and the PRIORITY-2 table of the FE Response Workbench load
   by their recorded SHA-256 from the portable folder; the synthetic single-plate demonstration opens from it and its
   offline study runs (SYNTHETIC); the archive of the physical readiness review verifies; no measurement, FE model, FE
   result, extracted FE package file or solver file is in the build.
5a. RC6: the tracked extractor ``abaqus_scripts/extract_odb.py`` is copied beside the program (``<portable>\\
   abaqus_scripts\\``), where the frozen ``abaqus_bridge`` resolves it, and checked (SHA-256 equal to the
   repository's, ``readOnly=True``). The program starts without Abaqus; only the ODB extraction needs it.
6. BUILD_INFO.json (commit, versions, sizes, EXE SHA-256), README_PORTABLE.txt and PACKAGE_SHA256.txt (every file of
   the folder) are written; the folder is zipped and the ZIP is checked against the folder. The ZIP's size and
   SHA-256 are written beside it (``<name>.zip.sha256``, ``build_result.json``).
7. With --desktop, the folder, the ZIP and its ``.zip.sha256`` are copied to the Windows desktop. An existing RC6
   copy there is never replaced (there is no --replace); the RC1-RC5 copies are never touched.

``--verify <folder>`` checks a portable folder (for example one unpacked from the ZIP on another computer) against
its PACKAGE_SHA256.txt.

WINDOWS-PREVIEW-01: what the user receives is named Preview 0.1. PyInstaller still builds from the RC6 specification
(``NAME``, the internal build source); the finished folder is then given the delivered name ``DELIVERED``, and the ZIP,
its ``.zip.sha256``, BUILD_INFO.json and README_PORTABLE.txt carry that name and ``RELEASE``. The README describes the
window the program opens (Analyze, Review, MAC / Points, Materials, Research Tuning). A desktop copy of RC6 is now an
earlier copy and is never written.

WINDOWS-PREVIEW-01-COMPACT: the build leaves out what the program never loads (``LEFT_OUT``: Qt's software OpenGL
renderer, Qt's translations, Qt Network with its TLS plug-ins and the OpenSSL they pull in, Pillow's AVIF codec,
matplotlib's sample data); the specification applies the list, and the finished folder is checked for it and for the
parts every function needs (``REQUIRED``). The ZIP is written with the strongest deflate level (still an ordinary ZIP
that Windows opens).

WINDOWS-PREVIEW-01-REFRESH: the build also checks the current plate comparison snapshot that Help > Research Results
shows (``check_plate_comparison``: present in the portable folder, the SHA-256 the program records, read by the
program's reader with four models, 11 records and 11 x 14 matrices), records it in BUILD_INFO.json, and the README
describes that window.

WINDOWS-PREVIEW-01-SOLID-WORKER-FIX: the packaged program is also the supervised solid worker of Research Tuning
(``launch_new_gui.py`` asks ``frozen_worker_dispatch`` before any interface module is imported). The build starts the
finished program as a worker (``check_solid_worker``: refused invocations, an empty request, a request for a missing
INP; nothing is solved) and stops when one of the starts does not end or answers otherwise; BUILD_INFO.json records it.

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
NAME = "AbaqusModalComparator_RC6"
EXE = "AbaqusModalComparator.exe"
SPEC = HERE / f"{NAME}.spec"
PACKAGE_LIST = "PACKAGE_SHA256.txt"
EARLIER = ("RC1", "RC2", "RC3", "RC3_F1", "RC3_F2", "RC4", "RC4_F1", "RC5")
RELEASE = "Preview 0.1"  # what the user sees: the README, BUILD_INFO.json, the folder and the ZIP
DELIVERED = "AbaqusModalComparator_Preview_0.1"  # the delivered folder and ZIP; NAME stays the internal build source
PROTECTED_DESKTOP = tuple(f"AbaqusModalComparator_{name}{suffix}" for name in EARLIER + ("RC6",)
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
TRACKED_ROOTS = ("src", "docs", "packaging", "abaqus_scripts", "requirements-new-gui.txt")
# RC6: the ODB extractor the program runs through Abaqus Python (PRIORITY-0). abaqus_bridge resolves it as
# Path(__file__).parents[1] / "abaqus_scripts" / "extract_odb.py"; a frozen top-level module's __file__ is
# _internal\abaqus_bridge.pyc, so the script must lie beside the program at <portable>\abaqus_scripts\extract_odb.py.
EXTRACTOR = PurePosixPath("abaqus_scripts/extract_odb.py")
# WINDOWS-PREVIEW-01-COMPACT: never loaded by the program, so not shipped. A path of the portable folder below _internal
# (lower case, forward slashes): a file, or a folder when it ends with "/". The program draws with Qt widgets (no
# OpenGL), installs no translator (English only), opens no network connection, and reads and writes PNG and PDF only.
LEFT_OUT = (
    ("pyside6/opengl32sw.dll", "Qt's software OpenGL renderer: the interface uses Qt widgets, no OpenGL"),
    ("pyside6/translations/", "Qt's own translations: the interface is English and installs no translator"),
    ("pyside6/qt6network.dll", "Qt Network: the program opens no network connection"),
    ("pyside6/qtnetwork.pyd", "Qt Network: the program opens no network connection"),
    ("pyside6/plugins/tls/", "TLS plug-ins of Qt Network"),
    ("pyside6/plugins/networkinformation/", "network state plug-in of Qt Network"),
    ("libcrypto-3-x64.dll", "OpenSSL of the build computer, pulled in only by Qt's TLS plug-in"),
    ("libssl-3-x64.dll", "OpenSSL of the build computer, pulled in only by Qt's TLS plug-in"),
    ("pil/_avif.cp", "Pillow's AVIF codec: the program reads and writes PNG"),
    ("matplotlib/mpl-data/sample_data/", "matplotlib's example data files"),
)
EXCLUDED_MODULES = ("PySide6.QtNetwork", "PIL._avif")  # the modules of the parts above; never imported by the program
# What every function of the program needs, below _internal (a glob each): refused when one is missing.
REQUIRED = ("python3*.dll", "base_library.zip", "PySide6/Qt6Core.dll", "PySide6/Qt6Gui.dll", "PySide6/Qt6Widgets.dll",
            "PySide6/QtCore.pyd", "PySide6/QtGui.pyd", "PySide6/QtWidgets.pyd", "PySide6/plugins/platforms/qwindows.dll",
            "PySide6/plugins/platforms/qoffscreen.dll", "PySide6/plugins/styles/*.dll",
            "PySide6/plugins/imageformats/*.dll", "numpy/_core/_multiarray_umath*.pyd", "numpy.libs/*openblas*.dll",
            "scipy.libs/*openblas*.dll", "scipy/linalg/_flapack*.pyd", "scipy/optimize/*.pyd", "scipy/sparse/*.pyd",
            "scipy/spatial/*.pyd", "scipy/signal/*.pyd", "scipy/interpolate/*.pyd", "scipy/stats/*.pyd",
            "matplotlib/ft2font*.pyd", "matplotlib/backends/_backend_agg*.pyd", "matplotlib/mpl-data/matplotlibrc",
            "matplotlib/mpl-data/fonts/ttf/DejaVuSans.ttf", "PIL/_imaging.cp*.pyd", "libcrypto-3.dll", "_hashlib.pyd")


# WINDOWS-PREVIEW-01-SOLID-WORKER-FIX: the packaged program is also the supervised solid worker of Research Tuning.
# The worker imports these inside functions; the specification names them, and check_solid_worker starts the
# finished program as a worker.
SOLID_WORKER_MODULES = ("services.solid_forward_runner", "services.solid_c3d8i_model", "services.solid_c3d8i_solver",
                        "services.solid_c3d8i_forward", "services.matrix_model_service")
SOLID_WORKER_SECONDS = 180.0  # a start that has not ended by then is refused (the program opened its window)


def check_solid_worker(folder: Path, command=None) -> dict:
    """The finished program, started as the supervised solid worker, behaves as one and never as the interface.
    Four starts, none of which solves anything: the source command (refused), the worker argument without pipes
    (refused), an empty request (refused by the worker after it identified itself) and a well-formed request for an INP
    that does not exist (the worker imports its solver modules, then reports the missing file). A start that does not
    end is the program's window: the build stops. ``command`` replaces the program in the tests of this check."""
    sys.path.insert(0, str(REPO / "src"))
    from services import solid_forward_runner as sfr

    command = [str(folder / EXE)] if command is None else list(command)
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")

    def start(name, arguments, request=None):
        pipes = request is not None
        try:
            done = subprocess.run(command + list(arguments), input=request if pipes else None,
                                  stdin=None if pipes else subprocess.DEVNULL,
                                  stdout=subprocess.PIPE if pipes else subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  cwd=folder, env=env, timeout=SOLID_WORKER_SECONDS,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired:
            raise SystemExit(f"refused: the program started as a solid worker ({name}) did not end in "
                             f"{SOLID_WORKER_SECONDS:g} s: a worker invocation must never open the interface")
        events = []
        for line in (done.stdout or b"").splitlines():
            try:
                events.append(json.loads(line.decode("utf-8")))
            except ValueError:
                raise SystemExit(f"refused: the solid worker ({name}) wrote a line that is not a JSON event")
        return done.returncode, events

    def expect(name, got, wanted):
        if got != wanted:
            raise SystemExit(f"refused: the program started as a solid worker ({name}) gave {got}, not {wanted}")

    code, _ = start("source command", ["-m", "services.solid_forward_runner", "--child"])
    expect("source command", code, sfr.EXIT_MALFORMED_INVOCATION)
    code, _ = start("no pipes", [sfr.WORKER_OPTION])
    expect("no pipes", code, sfr.EXIT_NO_PIPES)
    code, events = start("empty request", [sfr.WORKER_OPTION], b"{}\n")
    expect("empty request", (code, [e.get("event") for e in events], events[-1].get("kind") if events else None),
           (sfr.EXIT_MALFORMED_REQUEST, ["hello", "error"], "MALFORMED_REQUEST"))
    missing = folder / "no such model.inp"
    request = {"inp_path": str(missing), "inp_sha256": "0" * 64, "elastic_modes": 14, "guard_modes": 4,
               "max_memory_bytes": 1 << 30, "max_seconds": 60.0, "points": []}
    code, events = start("missing INP", [sfr.WORKER_OPTION], (json.dumps(request) + "\n").encode("utf-8"))
    expect("missing INP", (code, [e.get("event") for e in events], events[-1].get("kind") if events else None),
           (1, ["hello", "error"], "FileNotFoundError"))
    if not isinstance(events[0].get("pid"), int) or missing.exists():
        raise SystemExit("refused: the solid worker did not identify itself by its process number")
    return {"worker_argument": sfr.WORKER_OPTION, "modules": list(SOLID_WORKER_MODULES),
            "source_command_exit_code": sfr.EXIT_MALFORMED_INVOCATION, "no_pipes_exit_code": sfr.EXIT_NO_PIPES,
            "empty_request": "hello, error MALFORMED_REQUEST, exit code %d" % sfr.EXIT_MALFORMED_REQUEST,
            "missing_inp_request": "hello, error FileNotFoundError after the solver modules were imported, exit code 1",
            "calculations": 0, "interface_opened": False}


def left_out(destination: str) -> str:
    """Why a file of the frozen program (its path below _internal) is not shipped; empty when it is shipped."""
    name = str(destination).replace("\\", "/").lower()
    for pattern, reason in LEFT_OUT:
        if name.startswith(pattern) if pattern.endswith(("/", ".cp")) else name == pattern:
            return reason
    return ""


def check_compact(folder: Path) -> dict:
    """The finished folder holds none of the parts left out and every part the program needs."""
    internal = folder / "_internal"
    present = sorted(p.relative_to(internal).as_posix() for p in internal.rglob("*")
                     if p.is_file() and left_out(p.relative_to(internal).as_posix()))
    if present:
        raise SystemExit("refused: parts that are left out are in the build: " + ", ".join(present[:20]))
    missing = [pattern for pattern in REQUIRED if not any(internal.glob(pattern))]
    if missing:
        raise SystemExit("refused: the build lacks parts the program needs: " + ", ".join(missing))
    return {"left_out": [{"path": pattern, "why": reason} for pattern, reason in LEFT_OUT],
            "excluded_modules": list(EXCLUDED_MODULES), "required_present": len(REQUIRED)}


README = """Abaqus\u2013Simcenter Modal Comparator \u2014 {release}
==================================================

{release} is a WORKING RESEARCH PREVIEW. It compares the modal results of an Abaqus finite-element (FE) model with a
measured modal test. It does NOT identify material properties: real material identification and production Auto-ID
remain BLOCKED (see "What is blocked" below).

START
  Double-click {exe}. No Python, VS Code or Abaqus installation is needed to start it.
  Keep the folder together: {exe}, _internal, docs and abaqus_scripts belong to one
  another. The folder may be copied anywhere, also into a path with spaces. Your own files are not in this folder:
  you choose them in the program.

THE WINDOW
  The list on the left has five pages: Analyze, Review, MAC / Points, Materials, Research Tuning.
  The File menu has Open Project..., Save Project, Save Project As... and Close Project.
  The Help menu has About and Research Results... (part 7).

1. ANALYZE - choose the two files and compare
  - FE results (.odb): click Choose file... and pick the Abaqus output database of a frequency analysis.
  - Experiment (.unv, .uff): click Choose file... and pick the measured modal file.
  - Click Analyze. Cancel stops a running analysis; nothing is kept from a cancelled one.
  The program never opens the .odb itself. If the modes of this .odb were already extracted (a folder
  <odb name>_modal_packages beside it), they are reused and Abaqus is not needed. Otherwise the program asks
  "Start Abaqus Python?" and names the file, the results folder and the launcher. No starts nothing. Yes needs an
  Abaqus installation on this computer; the .odb is read read-only and no analysis is solved. Advanced lets you
  choose the Abaqus launcher and the extraction folder.

2. REVIEW - frequencies and mode shapes
  After Analyze the Review page opens. The table lists each measured (EXP) frequency with the FE frequency nearest to
  it and the difference in percent. These are candidates chosen by frequency, not confirmed mode pairs.
  Below the table: Mode shapes (Show shape, Save PNG), Frequency plots, FRF spectrum and All tables.
  Export report... writes the report of the shown result into a folder you choose. Which report depends on the result:
  - Frequency-only (no registration, status REGISTRATION_REQUIRED): a diagnostic report as PDF and Excel. It holds
    frequencies and frequency differences only: no MAC and no mode pairs.
  - Registered comparison (mode pairs were computed): the comparison report as PDF, Excel and a JSON record. It holds
    the actual FE / EXP mode pairs, their frequencies, signed frequency errors and MAC, the registration the pairs
    rest on (an archived verified registration or a user-confirmed one, named as such) and the verdict of every
    measured record. A verdict such as CORRESPONDENCE_GROUP_LEVEL_ONLY or CORRESPONDENCE_AMBIGUOUS is kept as it is:
    a high MAC alone is not proof that one FE mode is one measured mode, and the report says so on its first page.
  Nothing is calculated again for a report, and existing files are never replaced. When a report cannot be written,
  the page says why beside the button.

3. MAC / POINTS - why verified MAC may be missing
  MAC compares the shape of an FE mode with the shape of a measured mode at the same points. For that the program
  must know which FE node belongs to which measured point: a physical registration. Without a confirmed registration
  the page says MAC NOT AVAILABLE and the status is REGISTRATION_REQUIRED: you have a frequency comparison only, with
  no mode pairs and no MAC. This is the expected result for two files that have no registration yet.
  Set up registration... starts one; it records a person's statement, not an independent proof.
  Run trial MAC is something else: it tries a fixed list of possible placements of the measured points on the FE
  model and shows the matrices under the label EXPLORATORY MAC - UNCONFIRMED GEOMETRIC MAPPING. A trial MAC is a
  look at the data, never a verified MAC and never a confirmed mode pair. The page still says MAC NOT AVAILABLE after
  it. Export all Trial MAC... saves the trial as a ZIP; an existing file is never replaced.

4. SAVE AND REOPEN
  File > Save Project As... (or Save result on the Review page) writes one .mcproj file. The source files are not in
  it. File > Open Project... shows the saved result again, marked SAVED SNAPSHOT; nothing is calculated and no source
  file is opened. Curves and components that need the source files appear again after a new Analyze.
  A SAVED SNAPSHOT cannot be exported as a report: first click Check source files on the Analyze page, then Analyze
  again, and export the fresh result.

5. MATERIALS - two research methods on a built-in synthetic example
  The Materials page tests two model methods on numbers the program makes itself. Tabs: Calculation, Results, Plots,
  Diagnostics, FE / Experiment. Choose the Method, keep Data on "Built-in synthetic example", click Run calculation.
  - Ritz plate model: a thin-plate model computed in the program. It needs the plate length a, width b and mass
    (already filled in for the example); no ODB, Abaqus or matrix file. It fits D11, D22, D66 and u.
  - Stage A matrix model: it needs a prepared matrix package (the built-in synthetic package is used for the
    example); it does not use plate size or mass. It fits D, D66 and r. Without a compatible package it refuses.
  Save result and Open result keep a result as a .mcproj file; Save plot (PNG)... saves a picture.
  Every result of this page is a SYNTHETIC software test marked DIAGNOSTIC_OPTIMIZER_CANDIDATE and
  NOT_A_RELEASE_VALUE: recovering known numbers tests the software and says nothing about a real material.
  "Real file: view only" shows what an .odb or .unv/.uff holds on the FE / Experiment tab and calculates nothing.

6. RESEARCH TUNING
  Research only: it tunes the assumed inputs of a supported Abaqus shell model against measured frequencies with a
  plate surrogate. No Abaqus run; the result is not a material property. The model must be a flat plate in the
  global XY plane (any constant Z); a curved, folded or tilted shell model is refused with the reason.

7. RESEARCH RESULTS - Help > Research Results...
  A separate read-only window of stored research records. It opens only from the Help menu and is not one of the
  five pages. Close returns to the program, which stays on the page it was on.
  For the single CFRP plate it shows four Abaqus models (Baseline, Thickness only, Directional stiffness only,
  Combined) against the 11 measured records: the FE inputs, the frequencies with their differences in percent and
  one 11 x 14 research MAC matrix per model. Four buttons choose the model shown in full.
  The window is independent of the files chosen on Analyze: it reads none of them and gives nothing to an analysis,
  so its link line always says NOT VERIFIED. Nothing is calculated, and Abaqus is never started.
  Tables under a note that begins HISTORICAL were computed with a superseded scan geometry: they are kept as an
  archived record and are not current results.
  Every value there is RESEARCH_ONLY, PHYSICAL_REGISTRATION_NOT_VERIFIED and NOT_A_MATERIAL_PROPERTY: no row is a
  confirmed mode pair and no model is chosen as the best. If the stored file is missing or changed, the window says
  so and shows no table in its place.

MEMORY
  The program holds the extracted FE mode shapes in memory. In testing, one large sandwich-panel example (about
  1.6 million FE nodes, 18 modes) used up to approximately 8.6 GB of memory while it was compared and exported.
  This is one observation: it is not a maximum, and not a minimum system requirement. Smaller models use far less.
  If Windows runs short of memory, close other programs or use a computer with more memory.

WHAT IS BLOCKED
  - Real-data inverse execution: BLOCKED. The program does not identify the material of a real specimen.
  - Production Auto-ID: BLOCKED. M8 GATE NOT_MET, D-077 NO_GLOBAL_PARAMETER_VALUE.
  No number shown by this preview is an accepted material property, a ply constant or a calibration.

NOT INCLUDED
  Experimental files (UNV, UFF, LMS), Abaqus models and results (INP, ODB, DAT) and extracted FE packages.

FILES OF THIS FOLDER
  PACKAGE_SHA256.txt lists the SHA-256 of every file. BUILD_INFO.json names the build.
  Build: {release}, commit {commit} ({branch}), {built}.
  Internal build source: {name}.
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


def copy_extractor(target: Path) -> dict:
    """RC6: the tracked extractor beside the program, byte-identical to the repository's (SHA-256 recorded)."""
    source = REPO.joinpath(*EXTRACTOR.parts)
    tracked = git("ls-files", "--", str(EXTRACTOR))
    if not tracked:
        raise SystemExit(f"refused: {EXTRACTOR} is not a tracked file")
    destination = target.joinpath(*EXTRACTOR.parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return {"path": str(EXTRACTOR), "bytes": destination.stat().st_size, "sha256": sha256(destination)}


def check_extractor(folder: Path) -> dict:
    """The extractor is where the frozen bridge will look for it and equals the repository's file."""
    expected = folder.joinpath(*EXTRACTOR.parts)
    frozen_bridge = folder / "_internal" / "abaqus_bridge.pyc"  # the frozen module's __file__
    resolved = frozen_bridge.resolve().parents[1] / "abaqus_scripts" / "extract_odb.py"
    if resolved != expected.resolve() or not expected.is_file():
        raise SystemExit(f"refused: the extractor is not where abaqus_bridge resolves it ({resolved}); found "
                         f"{'yes' if expected.is_file() else 'no'} at {expected}")
    digest = sha256(expected)
    if digest != sha256(REPO.joinpath(*EXTRACTOR.parts)):
        raise SystemExit("refused: the packaged extractor differs from the repository's")
    text = expected.read_text(encoding="utf-8")
    if "readOnly=True" not in text:
        raise SystemExit("refused: the packaged extractor does not open the ODB read-only")
    return {"path": str(EXTRACTOR), "resolved_by_bridge": str(resolved), "sha256": digest, "read_only": True}


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
            "fe_response": check_fe_response(folder), "plate_comparison": check_plate_comparison(folder),
            "matching_rows": {k: len(v) for k, v in snapshot.matching.items()},
            "sensitivity_terms": len(snapshot.sensitivities),
            "scenarios": [s.key for s in snapshot.scenarios],
            "sp10_priority6": {"fe_modes": [m.number for m in results.fe_modes][0::18],
                               "fe_mode_count": len(results.fe_modes),
                               "fe_manifest_sha256": results.fe_manifest_sha256,
                               "diagnostic_rows": len(rows),
                               "exp11_exp12": [f"EXP{r.exp_no} FE{r.nearest.fe} {r.nearest.df_percent:+.2f} %"
                                               for r in rows[10:]]}}


def check_plate_comparison(folder: Path) -> dict:
    """WINDOWS-PREVIEW-01-REFRESH: the current plate comparison snapshot that Help > Research Results shows is in the
    portable folder, has the SHA-256 the program records for it, and is read there by the program's own reader with its
    four models, 11 records and four 11 x 14 matrices. A missing, changed or inconsistent file stops the build."""
    from services import research_results_reader as rr

    relative, recorded = rr.PLATE_COMPARISON_FILE
    path = folder.joinpath(*PurePosixPath(relative).parts)
    if not path.is_file():
        raise SystemExit(f"refused: the plate comparison snapshot is not in the build: {relative}")
    digest = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()  # the committed (LF) form
    if digest != recorded:
        raise SystemExit(f"refused: the plate comparison snapshot has SHA-256 {digest}, not the recorded {recorded}")
    try:
        comparison = rr.load_plate_comparison(folder)
    except rr.PlateComparisonRefused as error:
        raise SystemExit(f"refused: the plate comparison snapshot is not read from the portable folder: {error}")
    shapes = {key: (len(model.records), len(model.mac), sorted({len(row) for row in model.mac}))
              for key, model in comparison.models.items()}
    if tuple(comparison.models) != tuple(rr.PLATE_MODELS) or any(s != (11, 11, [14]) for s in shapes.values()):
        raise SystemExit(f"refused: the plate comparison snapshot does not hold four models of 11 records and "
                         f"11 x 14 matrices: {shapes}")
    return {"path": relative, "bytes": path.stat().st_size, "sha256": comparison.sha256, "recorded_sha256": recorded,
            "models": list(comparison.models), "records_per_model": 11, "matrix": "11 x 14",
            "labels": list(comparison.labels)}


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


ZIP_LEVEL = 9  # the strongest deflate: an ordinary ZIP, as before, that Windows opens by itself


def make_zip(folder: Path, archive: Path) -> None:
    tmp = archive.with_suffix(".zip.partial")
    # refused before anything is written: os.rename replaces its target on POSIX, so it is not the guard
    for existing in (archive, tmp):
        if existing.exists():
            raise SystemExit(f"refused: {existing} exists (an existing ZIP is never replaced)")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=ZIP_LEVEL) as zf:
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


def readme(commit: str, branch: str, built: str) -> str:
    """README_PORTABLE.txt of the delivered folder: the release, the window the program opens, what is blocked."""
    return README.format(release=RELEASE, name=NAME, exe=EXE, commit=commit, branch=branch, built=built)


def deliver(built: Path, folder: Path) -> None:
    """Give the folder PyInstaller made from the RC6 specification its delivered name. Nothing is replaced."""
    if folder.exists():
        raise SystemExit(f"refused: {folder} exists (nothing is replaced)")
    os.rename(built, folder)


def refuse_existing(out: Path) -> None:
    """The build folder is new or empty: an earlier RC build or an RC6 build there is never deleted or replaced."""
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"refused: the build folder is not empty (nothing there is deleted or replaced): {out}")


def desktop_targets(desktop: Path) -> tuple:
    targets = (desktop / DELIVERED, desktop / f"{DELIVERED}.zip", desktop / f"{DELIVERED}.zip.sha256")
    if any(t.name in PROTECTED_DESKTOP for t in targets):  # a guard: this build never writes the earlier copies
        raise SystemExit("refused: the RC1-RC6 desktop copies are not written by this build")
    existing = [str(t) for t in targets if t.exists()]
    if existing:
        raise SystemExit(f"refused: a {RELEASE} desktop copy exists (it is never replaced): " + ", ".join(existing))
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
    folder, archive = dist / DELIVERED, dist / f"{DELIVERED}.zip"
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN",
                    "--distpath", str(dist), "--workpath", str(work), str(SPEC)], cwd=out, check=True)
    deliver(dist / NAME, folder)  # the RC6 specification built it; the user receives it under the release's name
    documents = copy_documents(folder)  # tracked paths begin with docs/
    extractor = copy_extractor(folder)  # RC6: abaqus_scripts/extract_odb.py beside the program
    check_contents(folder)
    compact = check_compact(folder)
    research = check_research(folder)
    research["odb_extractor"] = check_extractor(folder)
    research["solid_worker"] = check_solid_worker(folder)  # the finished program itself, before anything is listed
    built = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (folder / "README_PORTABLE.txt").write_text(readme(commit, branch, built), encoding="utf-8-sig")  # for Notepad
    count, size = folder_size(folder)
    info = {"name": DELIVERED, "release": RELEASE, "internal_build": NAME, "commit": commit, "branch": branch,
            "dirty": bool(dirty), "built_utc": built,
            "python": sys.version.split()[0], "platform": platform.platform(), "packages": versions(), "exe": EXE,
            "exe_bytes": (folder / EXE).stat().st_size, "exe_sha256": sha256(folder / EXE),
            "files": count + 2, "bytes_before_info": size,  # + BUILD_INFO.json and PACKAGE_SHA256.txt
            "reference_files": len(documents), "reference_bytes": sum(d["bytes"] for d in documents),
            "odb_extractor": extractor, "compact": compact,
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
    (dist / f"{DELIVERED}.zip.sha256").write_text(f"{zip_sha} *{DELIVERED}.zip\n", encoding="utf-8")
    result = {"release": RELEASE, "internal_build": NAME, "folder": str(folder), "zip": str(archive), "files": count,
              "bytes": size,
              "exe_bytes": info["exe_bytes"], "exe_sha256": info["exe_sha256"],
              "zip_bytes": archive.stat().st_size, "zip_sha256": zip_sha, "zip_check": zipped,
              "package_list_sha256": sha256(folder / PACKAGE_LIST), "commit": commit, "branch": branch,
              "dirty": bool(dirty), "python": info["python"], "packages": info["packages"], "research_check": research}
    if desktop:
        shutil.copytree(folder, desktop[0])
        shutil.copy2(archive, desktop[1])
        shutil.copy2(dist / f"{DELIVERED}.zip.sha256", desktop[2])
        if sha256(desktop[1]) != zip_sha or not verify_folder(desktop[0])["verified"]:
            raise SystemExit("refused: the desktop copy does not match the build")
        result["desktop"] = [str(t) for t in desktop]
    (out / "build_result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
