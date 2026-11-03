"""RC6-F1: paths reach the Abaqus launcher unchanged through cmd.exe; unsafe values are refused, never executed.

The Windows tests run the real cmd.exe with a fake launcher: a .bat that forwards %* through a second .bat (as
C:\\SIMULIA\\Commands\\abaqus.bat does) to a stand-in Python script, which records the argv it received. No Abaqus.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import abaqus_bridge  # noqa: E402
from abaqus_bridge import AbaqusExtractionError, AnalysisCancelled, _windows_command  # noqa: E402

_STAND_IN = r'''
import json, os, sys, time
args = sys.argv[1:]
opts = {args[i]: args[i + 1] for i in range(len(args) - 1) if args[i].startswith("--")}
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "received.json"), "w", encoding="utf-8") as s:
    json.dump({"argv": args, "cwd": os.getcwd()}, s)
if opts.get("--registration-file"):
    with open(opts["--registration-file"], "w", encoding="utf-8") as s:
        json.dump({"token": opts["--owner-token"], "pid": os.getpid(), "timestamp": time.time(), "format_version": 2}, s)
print("PROGRESS: stand-in started", flush=True)
if opts.get("--end-mode") == "1000":  # the tests' slow marker: time to cancel
    with open(os.path.join(here, "worker.pid"), "w") as s:
        s.write(str(os.getpid()))
    time.sleep(120)
with open(os.path.join(opts["--output"], "manifest.json"), "w", encoding="utf-8") as s:
    json.dump({"modes": []}, s)
'''


class CommandLineTests(unittest.TestCase):
    """The string itself: on every platform, without starting anything."""

    def test_one_string_with_one_outer_pair_of_quotes(self):
        self.assertEqual(_windows_command(r"C:\a b\abq.bat", ["python", r"D:\c d\x.py", "--odb", r"D:\e f\y.odb"]),
                         r'''cmd.exe /d /s /c ""C:\a b\abq.bat" python "D:\c d\x.py" --odb "D:\e f\y.odb""''')

    def test_plain_words_stay_bare(self):
        self.assertEqual(_windows_command("abaqus", ["python", r"D:\x\y.py", "--start-mode", "6"]),
                         r'cmd.exe /d /s /c "abaqus python D:\x\y.py --start-mode 6"')

    def test_characters_cmd_splits_on_are_quoted(self):
        for value in (r"D:\a,b\x", r"D:\a;b\x", r"D:\a=b\x", r"D:\a(b)\x"):
            self.assertIn(f'"{value}"', _windows_command("abaqus", [value]))

    def test_trailing_backslash_is_doubled_only_when_quoted(self):
        self.assertIn(r'"D:\a b\\"', _windows_command("abaqus", ["D:\\a b\\"]))
        self.assertTrue(_windows_command("abaqus", ["D:\\"]).endswith(r'abaqus D:\"'))

    def test_unsafe_values_are_refused_in_every_position(self):
        for bad in ('a"b', "a%PATH%b", "a!b", "a^b", "a&b", "a|b", "a<b", "a>b", "a\nb", "a\rb", "a\x00b", "a\tb",
                    'x" & calc & "y'):
            with self.subTest(value=bad):
                with self.assertRaises(AbaqusExtractionError):
                    _windows_command(bad, ["python"])
                with self.assertRaises(AbaqusExtractionError):
                    _windows_command("abaqus", ["python", bad])


@unittest.skipUnless(os.name == "nt", "the real cmd.exe")
class RealCmdTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name).resolve()

    def launcher(self, folder_name: str) -> Path:
        folder = self.root / folder_name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "stand_in.py").write_text(_STAND_IN, encoding="utf-8")
        inner = folder / "abq inner.bat"
        inner.write_text(f'@echo off\r\nsetlocal\r\n"{sys.executable}" "{folder / "stand_in.py"}" %*\r\nendlocal\r\n',
                         encoding="utf-8")
        outer = folder / "abaqus launcher.bat"
        outer.write_text(f'@echo off\r\n"{inner}" %*\r\n', encoding="utf-8")
        self.received = folder / "received.json"
        return outer

    def run_bridge(self, launcher: Path, odb: Path, output: Path, program_folder: str = "program folder", **kwargs):
        script = self.root / program_folder / "abaqus_scripts" / "extract_odb.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text("# never run: the fake launcher ignores it\n", encoding="utf-8")
        fake_module = self.root / program_folder / "src" / "abaqus_bridge.py"
        odb.parent.mkdir(parents=True, exist_ok=True)
        odb.write_bytes(b"not an odb")
        with mock.patch.object(abaqus_bridge, "__file__", str(fake_module)):
            manifest = abaqus_bridge.run_abaqus_extraction(odb, output, abaqus_command=str(launcher), **kwargs)
        return manifest, script

    def assert_received(self, odb: Path, output: Path, script: Path):
        argv = json.loads(self.received.read_text(encoding="utf-8"))["argv"]
        self.assertEqual(argv[:2], ["python", str(script)])
        self.assertEqual(argv[argv.index("--odb") + 1], str(odb))
        self.assertEqual(argv[argv.index("--output") + 1], str(output))
        self.assertEqual(argv[argv.index("--registration-file") + 1], str(output / "process_registration.json"))

    def test_spaces_in_the_launcher_odb_script_and_output(self):
        launcher = self.launcher("launcher folder")
        odb, output = self.root / "odb folder" / "my model.odb", self.root / "results folder" / "package 1"
        manifest, script = self.run_bridge(launcher, odb, output)
        self.assertEqual(manifest, output / "manifest.json")
        self.assert_received(odb, output, script)

    def test_other_characters_windows_allows_in_a_path(self):
        for name in ("Program Files (x86)", "a,b;c=d", "it's [v1] {x} #2 +~@$", "Плита образец"):
            with self.subTest(name=name):
                launcher = self.launcher(f"{name} launcher")
                odb, output = self.root / name / "model 1.odb", self.root / f"{name} out" / "pkg"
                manifest, script = self.run_bridge(launcher, odb, output, program_folder=f"{name} program")
                self.assertTrue(manifest.exists())
                self.assert_received(odb, output, script)

    def test_paths_without_spaces_still_work(self):
        launcher = self.launcher("launcher")
        odb, output = self.root / "odb" / "model.odb", self.root / "out"
        manifest, script = self.run_bridge(launcher, odb, output, program_folder="program")
        self.assertTrue(manifest.exists())
        self.assert_received(odb, output, script)

    def test_a_program_found_on_path_still_runs(self):
        launcher = self.launcher("on path")
        odb, output = self.root / "odb folder" / "model.odb", self.root / "out folder"
        with mock.patch.dict(os.environ, {"PATH": f"{launcher.parent};{os.environ['PATH']}"}):
            (launcher.parent / "fakeabq.bat").write_text(f'@echo off\r\n"{launcher}" %*\r\n', encoding="utf-8")
            script = self.root / "program folder" / "abaqus_scripts" / "extract_odb.py"
            script.parent.mkdir(parents=True)
            script.write_text("# never run\n", encoding="utf-8")
            odb.parent.mkdir(parents=True)
            odb.write_bytes(b"x")
            with mock.patch.object(abaqus_bridge, "__file__", str(self.root / "program folder" / "src" / "b.py")):
                abaqus_bridge.run_abaqus_extraction(odb, output, abaqus_command="fakeabq")
        self.assert_received(odb, output, script)

    def test_what_cmd_passes_for_a_trailing_backslash(self):
        launcher = self.launcher("launcher folder")
        # The stand-in then stops on the missing --output; what it received is already recorded.
        subprocess.run(_windows_command(str(launcher), ["D:\\a b\\", "D:\\"]), capture_output=True, check=False)
        self.assertEqual(json.loads(self.received.read_text(encoding="utf-8"))["argv"], ["D:\\a b\\", "D:\\"])

    def test_refused_values_start_nothing_and_create_nothing(self):
        launcher = self.launcher("launcher folder")
        sentinel = self.root / "sentinel.txt"
        inject = f'x" & echo owned>"{sentinel}" & "y'
        ok_odb = self.root / "ok.odb"
        ok_odb.write_bytes(b"x")
        cases = {
            "launcher": (inject, ok_odb, self.root / "out1"),
            "odb, a real file name": (str(launcher), self.root / "a&b%TEMP%.odb", self.root / "out2"),
            "output": (str(launcher), ok_odb, self.root / "a&b" / "out3"),
        }
        for label, (command, odb, output) in cases.items():
            with self.subTest(label), mock.patch("abaqus_bridge.subprocess.Popen") as popen:
                with self.assertRaises(AbaqusExtractionError):
                    abaqus_bridge.run_abaqus_extraction(odb, output, abaqus_command=command)
                popen.assert_not_called()
                self.assertFalse(output.exists())
        self.assertFalse(self.received.exists())
        self.assertFalse(sentinel.exists())

    def test_a_refused_script_folder_starts_nothing(self):
        launcher = self.launcher("launcher folder")
        odb = self.root / "ok.odb"
        odb.write_bytes(b"x")
        fake_module = self.root / "a&b" / "src" / "abaqus_bridge.py"
        with mock.patch.object(abaqus_bridge, "__file__", str(fake_module)), \
                mock.patch("abaqus_bridge.subprocess.Popen") as popen, self.assertRaises(AbaqusExtractionError):
            abaqus_bridge.run_abaqus_extraction(odb, self.root / "out", abaqus_command=str(launcher))
        popen.assert_not_called()

    def test_cancellation_stops_the_owned_worker_with_spaces_in_every_path(self):
        launcher = self.launcher("launcher folder")
        worker_pid_file = launcher.parent / "worker.pid"
        odb, output = self.root / "odb folder" / "model.odb", self.root / "results folder"
        cancel = threading.Event()
        processes = []
        outcome = {}

        def run():
            try:
                self.run_bridge(launcher, odb, output, end_mode=1000, cancel_event=cancel,
                                process_callback=processes.append)
            except BaseException as error:  # noqa: BLE001  (asserted below)
                outcome["error"] = error

        thread = threading.Thread(target=run)
        thread.start()
        deadline = time.monotonic() + 60
        while not worker_pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertTrue(worker_pid_file.exists(), "the worker did not start")
        pid = int(worker_pid_file.read_text())
        self.assertTrue(abaqus_bridge._pid_exists(pid))
        cancel.set()
        thread.join(60)
        self.assertFalse(thread.is_alive())
        self.assertIsInstance(outcome.get("error"), AnalysisCancelled)
        self.assertFalse(abaqus_bridge._pid_exists(pid))
        self.assertIsNotNone(processes[0])  # the launcher process was handed over for ownership
        self.assertIsNone(processes[-1])  # and released at the end
        self.assertFalse((output / "manifest.json").exists())
        self.assertFalse((output / "process_registration.json").exists())

    def test_the_log_shows_the_command_line(self):
        launcher = self.launcher("launcher folder")
        output = self.root / "results folder"
        self.run_bridge(launcher, self.root / "odb folder" / "m.odb", output)
        log = (output / "abaqus_extraction.log").read_text(encoding="utf-8")
        self.assertIn(f'cmd.exe /d /s /c ""{launcher}" python ', log)
        self.assertIn("PROGRESS: stand-in started", log)


if __name__ == "__main__":
    unittest.main()
