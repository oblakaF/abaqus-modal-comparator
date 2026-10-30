# -*- mode: python ; coding: utf-8 -*-
# WINDOWS PORTABLE RC1: PyInstaller (onedir) specification of the portable new interface.
# Build it with packaging/portable_rc1/build_portable.py, which also puts the read-only reference files beside the
# program (see docs/gui/WINDOWS_PORTABLE_RC1.md). Nothing scientific is decided here.
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

REPO = Path(SPECPATH).resolve().parents[1]
SRC = REPO / "src"

# report_export installs the program's seven report layers by name (importlib): they are invisible to the analysis.
REPORT_LAYERS = ["reporting", "performance_tuning", "reporting_hardening", "amplitude_correlation",
                 "metrics_normalization", "enhanced_reporting", "advanced_reporting", "final_reporting_review",
                 "runtime_contracts"]

a = Analysis(
    [str(Path(SPECPATH) / "launch_new_gui.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[],
    hiddenimports=REPORT_LAYERS + collect_submodules("new_gui") + collect_submodules("domain"),
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
    name="AbaqusModalComparator_RC1",
)
