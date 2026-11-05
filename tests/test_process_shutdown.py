"""MAT-4: a process that builds and closes the program's windows ends normally.

Each scenario is one small process, offscreen, with faulthandler on. The test keeps its exit code and stderr and shows
them when it fails. It does not name a cause for the ``bool_dealloc`` crash seen at the end of the full CI run: that
cause is unknown. A crash in one of these small cases would show which part is needed to reach it.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]

try:
    import PySide6  # noqa: F401
    HAS_QT = True
except ImportError:
    HAS_QT = False
if not HAS_QT and os.environ.get("NEW_GUI_REQUIRE_QT") == "1":
    raise RuntimeError("NEW_GUI_REQUIRE_QT=1, but PySide6 is missing")


def _code(*parts: str) -> str:
    return chr(10).join(textwrap.dedent(part) for part in parts)


_START = """
    import sys
    sys.path.insert(0, sys.argv[1])
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
"""
_OLDER = """
    from new_gui import window as wm
    window = wm.MainWindow(ask_path=lambda *args: "")
"""
_PROGRAM = """
    from new_gui import production_window as pw
    window = pw.ProductionWindow()
"""
_SHOW = """
    window.show()
    app.processEvents()
"""
_CLOSE = """
    window.close()
    window.deleteLater()
    app.processEvents()
"""
_MATERIALS_RUN_WAITING = """
    import threading
    from new_gui import materials_study_model as sm, materials_study_panel as mp
    panel = next(p for p in vars(window.materials_workspace).values() if isinstance(p, mp.MaterialsStudyPanel))
    release = threading.Event()
    real = sm.execute_study
    def held(*args, **kwargs):
        release.wait(30)
        return real(*args, **kwargs)
    sm.execute_study = held
    panel.run_button.click()
    app.processEvents()
    assert panel._thread.is_alive()
"""
_CANCEL_AND_FINISH = """
    panel.cancel_button.click()
    release.set()
"""
_WORKER_LEFT_BEHIND = """
    panel.shutdown(0.05)
    assert panel._thread.is_alive()
"""
SCENARIOS = {
    "application only": (),
    "older window closed": (_OLDER, _SHOW, _CLOSE),
    "program window closed": (_PROGRAM, _SHOW, _CLOSE),
    "program window left open": (_PROGRAM, _SHOW),
    "Materials run cancelled, then closed": (_PROGRAM, _SHOW, _MATERIALS_RUN_WAITING, _CANCEL_AND_FINISH, _CLOSE),
    "a worker still waiting when the process leaves": (_PROGRAM, _SHOW, _MATERIALS_RUN_WAITING, _WORKER_LEFT_BEHIND),
}


@unittest.skipUnless(HAS_QT, "PySide6 is not installed")
class ProcessShutdownTests(unittest.TestCase):
    def run_scenario(self, parts: tuple) -> subprocess.CompletedProcess:
        code = _code(_START, *parts)
        environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
                           MKL_NUM_THREADS="1", PYTHONIOENCODING="utf-8")
        return subprocess.run([sys.executable, "-X", "faulthandler", "-c", code, str(ROOT / "src")],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
                              env=environment, check=False)

    def test_each_scenario_ends_normally(self):
        for name, parts in SCENARIOS.items():
            with self.subTest(scenario=name):
                result = self.run_scenario(parts)
                self.assertEqual(result.returncode, 0, result.stderr[-4000:])
                self.assertNotIn("Fatal Python error", result.stderr)
                self.assertNotIn("Traceback", result.stderr, result.stderr[-4000:])


if __name__ == "__main__":
    unittest.main()
