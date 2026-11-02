# -*- mode: python ; coding: utf-8 -*-
# WINDOWS PORTABLE RC6: PyInstaller (onedir) specification of the portable new interface with the direct ODB import
# (PRIORITY-0): RC5 (NEW-GUI.6 with Plate Study A-D and Research Results) plus Extract modal results... for an .odb.
# The RC5 approach. Build it with packaging/portable_rc6/build_portable.py, which also puts the read-only reference
# files and the ODB extractor (abaqus_scripts/extract_odb.py) beside the program (see docs/gui/WINDOWS_PORTABLE_RC6.md).
# Nothing scientific is decided here.
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

REPO = Path(SPECPATH).resolve().parents[1]
SRC = REPO / "src"

# report_export installs the program's seven report layers by name (importlib): they are invisible to the analysis.
REPORT_LAYERS = ["reporting", "performance_tuning", "reporting_hardening", "amplitude_correlation",
                 "metrics_normalization", "enhanced_reporting", "advanced_reporting", "final_reporting_review",
                 "runtime_contracts"]
# the services of Research Results and of Plate Study B-D (imported directly; named so that a refactor cannot drop
# them silently)
RESEARCH_SERVICES = ["services.research_results_reader", "services.sp10_fe_research",
                     "services.generic_plate_workbench", "services.generic_plate_evidence",
                     "services.generic_plate_offline_study", "services.plate_physical_review",
                     "services.single_plate_fe_response", "services.plate_study",
                     # RC6: the ODB import adapter and the launcher detection it uses (imported inside functions)
                     "services.odb_import_service", "abaqus_bridge", "ui_policy"]

a = Analysis(
    [str(Path(SPECPATH) / "launch_new_gui.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[],
    hiddenimports=REPORT_LAYERS + RESEARCH_SERVICES + collect_submodules("new_gui") + collect_submodules("domain"),
    hookspath=[],
    hooksconfig={"matplotlib": {"backends": ["Agg", "QtAgg"]}},
    runtime_hooks=[str(Path(SPECPATH) / "rthook_open_audit.py")],
    excludes=["tkinter", "_tkinter", "pytest", "IPython", "PyQt5", "PyQt6", "PySide2"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AbaqusModalComparator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="AbaqusModalComparator_RC6",
)
