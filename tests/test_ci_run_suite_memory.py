"""CI-LINUX-MEMORY-ROOT-CAUSE-1: the optional memory trace of tests/ci_run_suite.py.

A small synthetic suite is run by the runner in a process of its own, as the CI runs the real one. The trace has one line
per test and the markers; the reference-count trace, the exit code and unittest's closing lines are what they are without
the memory trace. The figures themselves exist only where the system gives them (Linux); elsewhere they are empty.

GUI-QT-DEFERRED-DELETE-FIX-1: the runner delivers the Qt deletions a test schedules with ``deleteLater()`` once the test
and its cleanups are done, so a widget of one test no longer exists in the next; a suite without Qt loads nothing of Qt.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))

import ci_run_suite as runner  # noqa: E402
import ci_summary as cs  # noqa: E402

SAMPLE = ("import unittest\n\nKEPT = []\n\n\nclass T(unittest.TestCase):\n    def test_a_keeps(self):\n"
          "        KEPT.append(b'x' * (64 * 1024 * 1024))\n\n    def test_b_ok(self):\n        pass\n\n"
          "    def test_c_verdict(self):\n        self.assertTrue({verdict})\n")
QT_SAMPLE = """import sys, threading, unittest

from PySide6.QtWidgets import QApplication, QLabel, QWidget
import shiboken6

APP = QApplication.instance() or QApplication([])
KEPT = []  # as a window a test's own objects still refer to: only Qt's deletion ends it


class T(unittest.TestCase):
    def test_a_schedules_the_deletion_of_its_window(self):
        window = QWidget()
        QLabel("a child", window)
        window.show()
        KEPT.append(window)
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        self.assertEqual(len(APP.allWidgets()), 2)

    def test_b_the_window_of_the_test_before_is_gone(self):
        self.assertFalse(shiboken6.isValid(KEPT[0]))
        self.assertEqual(APP.allWidgets(), [])

    def test_c_another_thread_delivers_nothing(self):
        deliver, said = sys.modules["__main__"].deliver_deferred_deletions, []
        thread = threading.Thread(target=lambda: said.append(deliver()))
        thread.start()
        thread.join()
        self.assertEqual(said, [False])
        self.assertIs(deliver(), True)
"""
PLAIN_SAMPLE = ("import sys, unittest\n\n\nclass T(unittest.TestCase):\n    def test_nothing_of_qt_is_loaded(self):\n"
                "        self.assertEqual([n for n in sys.modules if n.startswith(('PySide6', 'shiboken6'))], [])\n"
                "        self.assertIs(sys.modules['__main__'].deliver_deferred_deletions(), False)\n"
                "        self.assertIsNone(sys.modules['__main__'].qt_widgets_alive())\n")
STATUS = "Name:\tpython\nVmHWM:\t  900 kB\nVmRSS:\t  800 kB\nVmSwap:\t   50 kB\nThreads:\t3\n"
MEMINFO = "MemTotal: 16000 kB\nMemAvailable:   12000 kB\nCached:  3000 kB\nSwapCached: 1 kB\nShmem: 40 kB\nSwapFree: 2000 kB\n"


def rows(path: Path) -> list:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class _Sample(unittest.TestCase):
    def suite(self, verdict: str, *more) -> tuple:
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: [p.unlink() for p in folder.rglob("*") if p.is_file()])
        (folder / "test_sample_memory.py").write_text(SAMPLE.format(verdict=verdict), encoding="utf-8")
        done = subprocess.run([sys.executable, str(TESTS / "ci_run_suite.py"), "--start", str(folder), "--trace",
                               str(folder / "refcounts.jsonl"), *more], capture_output=True, text=True,
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"), timeout=300)
        return folder, done


class TraceTests(_Sample):
    def test_every_test_and_every_marker_is_in_the_trace(self):
        folder, done = self.suite("True", "--memory", str(folder_memory := Path(tempfile.mkdtemp()) / "memory.jsonl"))
        self.addCleanup(folder_memory.unlink)
        self.assertEqual(done.returncode, 0, done.stderr)
        trace = rows(folder_memory)
        self.assertEqual([r["test"] for r in trace if "test" in r],
                         [f"test_sample_memory.T.{n}" for n in ("test_a_keeps", "test_b_ok", "test_c_verdict")])
        self.assertEqual([r["event"] for r in trace if "event" in r], ["start", "tests_finished", "runner_returned", "process_exit"])
        self.assertEqual([r["event"] if "event" in r else "test" for r in trace],
                         ["start", "test", "test", "test", "tests_finished", "runner_returned", "process_exit"])
        self.assertEqual((trace[0]["tests_loaded"], trace[4]["tests_run"]), (3, 3))
        times = [r["time"] for r in trace]
        self.assertEqual(times, sorted(times))
        for row in trace:
            for name in ("rss_kb", "swap_kb", "peak_rss_kb", "available_kb", "cache_kb", "shared_kb", "swap_free_kb"):
                self.assertIn(name, row)
        for row in trace[1:4]:
            self.assertIn("rss_change_kb", row)

    @unittest.skipUnless(sys.platform.startswith("linux"), "the system gives these figures on Linux only")
    def test_memory_a_test_keeps_is_seen_as_a_step_that_stays(self):
        memory = Path(tempfile.mkdtemp()) / "memory.jsonl"
        self.addCleanup(memory.unlink)
        _folder, done = self.suite("True", "--memory", str(memory))
        self.assertEqual(done.returncode, 0, done.stderr)
        trace = rows(memory)
        start, kept, after, last = trace[0], trace[1], trace[2], trace[3]
        self.assertGreater(kept["rss_kb"] + kept["swap_kb"] - start["rss_kb"] - start["swap_kb"], 60 * 1024)
        self.assertEqual(after["rss_change_kb"], after["rss_kb"] - kept["rss_kb"])
        self.assertGreater(last["rss_kb"] + last["swap_kb"] - start["rss_kb"] - start["swap_kb"], 60 * 1024)  # it stays
        self.assertGreaterEqual(last["peak_rss_kb"], last["rss_kb"])
        facts = runner.read_memory(memory.read_text(encoding="utf-8"))
        self.assertEqual(facts["grown"][0]["module"], "test_sample_memory")
        self.assertEqual(facts["largest_steps"][0][1], "test_sample_memory.T.test_a_keeps")

    def test_the_verdict_the_closing_lines_and_the_reference_counts_are_as_without_the_trace(self):
        for verdict, code, closing in (("True", 0, "OK"), ("False", 1, "FAILED (failures=1)")):
            with self.subTest(verdict=verdict):
                memory = Path(tempfile.mkdtemp()) / "memory.jsonl"
                self.addCleanup(lambda m=memory: m.exists() and m.unlink())
                plain_folder, plain = self.suite(verdict)
                traced_folder, traced = self.suite(verdict, "--memory", str(memory))
                self.assertEqual((plain.returncode, traced.returncode), (code, code))
                for done in (plain, traced):
                    facts = cs.read(done.stderr)
                    self.assertEqual((facts["finished"], facts["ran"], facts["closing"]), (True, 3, closing))
                self.assertFalse((plain_folder / "memory.jsonl").exists())
                before, after = rows(plain_folder / "refcounts.jsonl"), rows(traced_folder / "refcounts.jsonl")
                self.assertEqual([sorted(r) for r in before], [sorted(r) for r in after])
                self.assertEqual([r.get("test") for r in before], [r.get("test") for r in after])
                self.assertEqual(sorted(before[0]), ["at_start", "collect", "false", "platform", "python", "true"])
                self.assertEqual(sorted(before[1]), ["false", "test", "true"])

    def test_the_trace_is_on_disk_after_each_test_and_survives_a_process_that_is_killed(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: [p.unlink() for p in folder.rglob("*") if p.is_file()])
        (folder / "test_sample_killed.py").write_text(
            "import os, unittest\n\n\nclass T(unittest.TestCase):\n    def test_a(self):\n        pass\n\n"
            "    def test_b_ends_the_process(self):\n        os._exit(9)\n", encoding="utf-8")
        done = subprocess.run([sys.executable, str(TESTS / "ci_run_suite.py"), "--start", str(folder), "--trace",
                               str(folder / "refcounts.jsonl"), "--memory", str(folder / "memory.jsonl")],
                              capture_output=True, text=True, timeout=300)
        self.assertEqual(done.returncode, 9)
        trace = rows(folder / "memory.jsonl")
        self.assertEqual([r.get("event", r.get("test")) for r in trace], ["start", "test_sample_killed.T.test_a"])
        text = "\n".join(text for _title, text in runner.describe_memory(runner.read_memory((folder / "memory.jsonl").read_text())))
        self.assertIn("1 tests traced", text)
        self.assertNotIn("tests_finished", text)  # the trace says how far the process came


class DeferredDeletionTests(unittest.TestCase):
    def folder(self, name: str, text: str) -> Path:
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: [p.unlink() for p in folder.rglob("*") if p.is_file()])
        (folder / name).write_text(text, encoding="utf-8")
        return folder

    def run_in(self, folder: Path, *command) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, *command], capture_output=True, text=True, cwd=folder, timeout=300,
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", QT_QPA_PLATFORM="offscreen"))

    def test_a_widget_scheduled_for_deletion_is_destroyed_before_the_next_test(self):
        folder = self.folder("test_sample_qt.py", QT_SAMPLE)
        done = self.run_in(folder, str(TESTS / "ci_run_suite.py"), "--start", str(folder), "--trace", "refcounts.jsonl",
                           "--memory", "memory.jsonl")
        self.assertEqual(done.returncode, 0, done.stderr)
        facts = cs.read(done.stderr)
        self.assertEqual((facts["finished"], facts["ran"], facts["closing"]), (True, 3, "OK"))
        trace = [r for r in rows(folder / "memory.jsonl") if "test" in r]
        self.assertEqual([r["qt_widgets"] for r in trace], [0, 0, 0])  # none is left after any test
        self.assertIn("Qt widgets alive after a test: 0 at the last such test, 0 at most",
                      dict(runner.describe_memory(runner.read_memory((folder / "memory.jsonl").read_text())))["memory trace: this process"])

    def test_without_the_runner_the_same_widget_outlives_its_test(self):
        """What the runner corrects: unittest alone runs no event loop, and the scheduled deletion never happens."""
        folder = self.folder("test_sample_qt.py", QT_SAMPLE)
        done = self.run_in(folder, "-m", "unittest", "test_sample_qt.T.test_a_schedules_the_deletion_of_its_window",
                           "test_sample_qt.T.test_b_the_window_of_the_test_before_is_gone")
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("FAILED (failures=1)", done.stderr)
        self.assertIn("self.assertFalse(shiboken6.isValid(KEPT[0]))", done.stderr)

    def test_a_suite_without_qt_loads_nothing_of_qt_and_runs_as_before(self):
        folder = self.folder("test_sample_plain.py", PLAIN_SAMPLE)
        done = self.run_in(folder, str(TESTS / "ci_run_suite.py"), "--start", str(folder), "--trace", "refcounts.jsonl",
                           "--memory", "memory.jsonl")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual([r["qt_widgets"] for r in rows(folder / "memory.jsonl") if "test" in r], [None])

    def test_a_deletion_that_fails_is_an_error_of_that_test(self):
        class Sample(unittest.TestCase):
            def test_ok(self):
                pass

        for failing, errors in ((False, 0), (True, 1)):
            with self.subTest(failing=failing), mock.patch.object(
                    runner, "deliver_deferred_deletions", side_effect=RuntimeError("the deletion failed") if failing else None):
                trace = io.StringIO()
                result = unittest.TextTestRunner(stream=io.StringIO(), resultclass=runner.tracing_result(trace, False)).run(
                    unittest.defaultTestLoader.loadTestsFromTestCase(Sample))
                self.assertEqual((result.testsRun, len(result.errors), result.wasSuccessful()), (1, errors, not failing))
                if failing:
                    self.assertIn("the deletion failed", result.errors[0][1])
                self.assertEqual(sorted(json.loads(trace.getvalue())), ["false", "test", "true"])  # the trace is kept


class ReadingTests(unittest.TestCase):
    def test_the_named_lines_are_read_in_kb_and_an_absent_one_is_empty(self):
        self.assertEqual(runner._fields(STATUS, runner.PROCESS_FIELDS), {"rss_kb": 800, "swap_kb": 50, "peak_rss_kb": 900})
        self.assertEqual(runner._fields(MEMINFO, runner.MACHINE_FIELDS),
                         {"available_kb": 12000, "cache_kb": 3000, "shared_kb": 40, "swap_free_kb": 2000})
        self.assertEqual(runner._fields("", runner.PROCESS_FIELDS), {"rss_kb": None, "swap_kb": None, "peak_rss_kb": None})

    def test_a_module_is_charged_with_what_it_leaves_behind_resident_or_swapped(self):
        def row(name, rss, swap, time):
            return json.dumps({"test": name, "time": time, "rss_kb": rss, "swap_kb": swap, "peak_rss_kb": 9000 * 1024,
                               "available_kb": 1, "cache_kb": 2, "shared_kb": 3, "swap_free_kb": 4, "rss_change_kb": 0})

        text = "\n".join([
            json.dumps({"event": "start", "time": 0.0, "rss_kb": 100 * 1024, "swap_kb": 0, "tests_loaded": 5}),
            row("m_a.T.test_1", 900 * 1024, 0, 60.0),          # a peak that is given back inside the module
            row("m_a.T.test_2", 110 * 1024, 0, 120.0),
            row("m_b.T.test_1", 1110 * 1024, 0, 180.0),        # kept
            row("m_c.T.test_1", 610 * 1024, 2500 * 1024, 240.0),  # resident falls only because it was swapped out
            json.dumps({"event": "tests_finished", "time": 250.0, "rss_kb": 1, "swap_kb": 1}),
            '{"test": "m_d.T.test_cut_sho',                    # the process ended while writing
        ])
        facts = runner.read_memory(text)
        self.assertEqual([(m["module"], m["tests"], m["growth_kb"] // 1024) for m in facts["modules"]],
                         [("m_a", 2, 10), ("m_b", 1, 1000), ("m_c", 1, 2000)])
        self.assertEqual([m["module"] for m in facts["grown"]], ["m_c", "m_b", "m_a"])
        self.assertEqual(facts["largest_steps"][0], (2000 * 1024, "m_c.T.test_1"))
        notices = dict(runner.describe_memory(facts))
        self.assertIn("4 tests traced", notices["memory trace: this process"])
        self.assertIn("resident 610 + swapped 2500 MB", notices["memory trace: this process"])
        self.assertIn("tests_finished at +250 s", notices["memory trace: this process"])
        self.assertTrue(notices["memory trace: modules that grew this process most (resident + swapped MB)"]
                        .startswith("m_c +2000 (1 tests, 1110 -> 3110); m_b +1000 (1 tests, 110 -> 1110); m_a +10"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out), tempfile.TemporaryDirectory() as folder:
            Path(folder, "memory.jsonl").write_text(text, encoding="utf-8")
            self.assertEqual(runner.main(["--summarise-memory", str(Path(folder, "memory.jsonl")), "--title", "G: "]), 0)
        self.assertEqual(out.getvalue().count("::notice title=G: memory trace"), 4)
        self.assertEqual(len(out.getvalue().splitlines()), 4)

    def test_an_empty_or_absent_trace_is_said_in_words(self):
        self.assertEqual(runner.describe_memory(runner.read_memory("")), [("memory trace", "no test is in the memory trace")])
        self.assertEqual(runner.describe_memory(runner.read_memory(runner._read("no such file"))),
                         [("memory trace", "no test is in the memory trace")])


if __name__ == "__main__":
    unittest.main()
