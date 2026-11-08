"""ABM main launcher: RUN_PROGRAM.cmd starts the PySide6 program through RUN_NEW_GUI.cmd by default and the legacy
interface only with the explicit "legacy" option. The routing tests run the real launcher with cmd.exe in a temporary
folder against a stub RUN_NEW_GUI.cmd (and, for legacy, a stand-in .venv with stub scripts), so no package is installed
and no program window or Abaqus is started."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "RUN_PROGRAM.cmd"
LABEL_LINE = "\n:legacy\n"  # the label itself, not "goto :legacy"


def _routes(text: str) -> tuple:
    head, _sep, legacy = text.replace("\r\n", "\n").partition(LABEL_LINE)
    return head, legacy


class LauncherText(unittest.TestCase):
    def test_the_default_route_reuses_the_new_gui_launcher_without_its_own_bootstrap(self):
        head, legacy = _routes(LAUNCHER.read_text(encoding="utf-8"))
        self.assertTrue(legacy)
        self.assertIn('call "%~dp0RUN_NEW_GUI.cmd"', head)
        for duplicated in ("ensure_dependencies", "-m venv", "pip install", "python.exe", "-m new_gui"):
            self.assertNotIn(duplicated, head)
        self.assertIn("exit /b %RESULT%", head)  # the program's exit code is passed on

    def test_the_legacy_interface_needs_the_explicit_option(self):
        head, legacy = _routes(LAUNCHER.read_text(encoding="utf-8"))
        self.assertIn('if /i "%~1"=="legacy" goto :legacy', head)
        self.assertIn('".venv\\Scripts\\python.exe" src\\main.py', legacy)
        self.assertIn('".venv\\Scripts\\python.exe" src\\ensure_dependencies.py', legacy)
        self.assertIn("exit /b 1", legacy)

    def test_the_new_gui_launcher_still_starts_the_program_window(self):
        self.assertIn("-m new_gui", (ROOT / "RUN_NEW_GUI.cmd").read_text(encoding="utf-8"))


@unittest.skipUnless(sys.platform == "win32", "cmd.exe launcher")
class LauncherRouting(unittest.TestCase):
    def run_launcher(self, stub_exit: int, *args: str, legacy_exit=None):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        shutil.copyfile(LAUNCHER, folder / "RUN_PROGRAM.cmd")
        (folder / "RUN_NEW_GUI.cmd").write_bytes(
            f"@echo off\r\necho STUB_NEW_GUI args=[%*]\r\nexit /b {stub_exit}\r\n".encode("ascii"))
        if legacy_exit is not None:  # a stand-in .venv (the running interpreter) and stub legacy scripts
            scripts = folder / ".venv" / "Scripts"
            scripts.mkdir(parents=True)
            shutil.copyfile(sys.executable, scripts / "python.exe")
            config = Path(sys.prefix) / "pyvenv.cfg"
            if config.exists():
                shutil.copyfile(config, folder / ".venv" / "pyvenv.cfg")
            (folder / "src").mkdir()
            (folder / "src" / "ensure_dependencies.py").write_text("print('STUB_ENSURE')\n", encoding="ascii")
            (folder / "src" / "main.py").write_text(f"import sys\nprint('STUB_LEGACY_MAIN')\nsys.exit({legacy_exit})\n",
                                                    encoding="ascii")
        return subprocess.run(["cmd.exe", "/d", "/c", str(folder / "RUN_PROGRAM.cmd"), *args], cwd=str(folder),
                              capture_output=True, text=True, timeout=120, env=dict(os.environ), stdin=subprocess.DEVNULL)

    def test_double_click_starts_the_new_gui_launcher_and_returns_its_exit_code(self):
        done = self.run_launcher(0)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("STUB_NEW_GUI args=[]", done.stdout)
        failed = self.run_launcher(7)
        self.assertEqual(failed.returncode, 7, failed.stdout + failed.stderr)
        self.assertIn("STUB_NEW_GUI", failed.stdout)

    def test_an_unknown_option_is_refused_and_starts_nothing(self):
        done = self.run_launcher(0, "newgui")
        self.assertEqual(done.returncode, 2)
        self.assertIn('Unknown option "newgui"', done.stdout)
        self.assertNotIn("STUB_NEW_GUI", done.stdout)

    def test_the_legacy_option_runs_the_legacy_program_and_reports_its_exit(self):
        done = self.run_launcher(0, "LEGACY", legacy_exit=0)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("STUB_ENSURE", done.stdout)
        self.assertIn("STUB_LEGACY_MAIN", done.stdout)
        self.assertIn("legacy interface", done.stdout)
        self.assertNotIn("STUB_NEW_GUI", done.stdout)
        failed = self.run_launcher(0, "legacy", legacy_exit=3)
        self.assertEqual(failed.returncode, 1, failed.stdout + failed.stderr)
        self.assertIn("could not start or finished with an error", failed.stdout)
        self.assertNotIn("STUB_NEW_GUI", failed.stdout)


if __name__ == "__main__":
    unittest.main()
