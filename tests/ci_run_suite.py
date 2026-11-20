"""ABM-AUD-2: run the whole suite as ``python -m unittest discover -s tests -v`` does, and keep a trace of the reference
counts of ``True`` and ``False`` (this file is not a test module).

    python -X faulthandler tests/ci_run_suite.py --trace refcount-trace.jsonl [--collect]

Why: on CPython 3.11 the Linux run ended with ``Fatal Python error: bool_dealloc: deallocating True or False``. That is
the end of a long loss: some native code gives back more references to a bool than it took, and the process dies in
whichever test happens to release the last one. The place of the crash therefore says little; the trace says which
tests lower the counts. One line is written and flushed after every test, so the trace survives the crash.

Nothing is hidden or retried: the tests run once, in the usual order, in one process, and the exit code is unittest's.
``--collect`` runs the garbage collector before each test, so that a test is not charged with garbage of earlier ones
(slower; for a diagnosis). From Python 3.12 on, the two counts are constant (immortal objects) and the trace is flat.

CI-LINUX-MEMORY-ROOT-CAUSE-1: ``--memory FILE`` also keeps a trace of this process's memory, one flushed line after every
test: resident memory, swapped-out memory, the peak, the change since the previous test, and the machine's own figures
(free, file cache, shared memory), so that memory held by this process can be told from the system's cache and from
other processes. Markers are written when the tests start, when unittest has finished, when its runner has returned and
when the process ends. The order, the count and the verdict of the tests are untouched; without ``--memory`` nothing here
runs. ``--summarise-memory FILE`` reads such a trace (complete or cut short) and prints what it shows as GitHub notices.

GUI-QT-DEFERRED-DELETE-FIX-1: after every test (its cleanups done) the Qt deletions that tests schedule with
``deleteLater()`` are delivered. Without a running event loop Qt never delivers them, and every window of every test
stayed alive to the end of the process. Nothing of Qt is imported here: a suite that has not loaded Qt is run as before.
"""

from __future__ import annotations

import argparse
import atexit
import faulthandler
import gc
import json
import sys
import threading
import time
import unittest


def counts() -> tuple:
    return sys.getrefcount(True), sys.getrefcount(False)


PROCESS_FIELDS = {"VmRSS": "rss_kb", "VmSwap": "swap_kb", "VmHWM": "peak_rss_kb"}
MACHINE_FIELDS = {"MemAvailable": "available_kb", "Cached": "cache_kb", "Shmem": "shared_kb", "SwapFree": "swap_free_kb"}


def _fields(text: str, wanted: dict) -> dict:
    """The named ``Name:   123 kB`` lines of a /proc status file, in kB; a name that is absent is None."""
    found = dict.fromkeys(wanted.values())
    for line in text.splitlines():
        name, _, rest = line.partition(":")
        if name in wanted:
            try:
                found[wanted[name]] = int(rest.split()[0])
            except (IndexError, ValueError):
                pass
    return found


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as stream:
            return stream.read()
    except OSError:
        return ""


def memory_now() -> dict:
    """This process's memory and the machine's, in kB (None where the system does not say, as outside Linux)."""
    return {**_fields(_read("/proc/self/status"), PROCESS_FIELDS), **_fields(_read("/proc/meminfo"), MACHINE_FIELDS)}


def _qt(module: str):
    """A Qt module some test has already imported, or None: this runner imports nothing of Qt itself."""
    return sys.modules.get(f"PySide6.{module}")


def deliver_deferred_deletions() -> bool:
    """Deliver the pending ``deleteLater()`` deletions. Only where a Qt application exists and this is its thread; True
    when they were delivered. An exception a deletion raises is the caller's to report."""
    core = _qt("QtCore")
    if core is None:
        return False
    app = core.QCoreApplication.instance()
    if app is None or app.thread() is not core.QThread.currentThread():
        return False
    core.QCoreApplication.sendPostedEvents(None, core.QEvent.Type.DeferredDelete)
    return True


def qt_widgets_alive():
    """How many Qt widgets exist now; None where no Qt widget application exists."""
    widgets = _qt("QtWidgets")
    if widgets is None:
        return None
    app = widgets.QApplication.instance()
    return len(app.allWidgets()) if isinstance(app, widgets.QApplication) else None


class MemoryTrace:
    """One flushed JSON line per finished test and per marker."""

    def __init__(self, stream):
        self.stream, self.previous = stream, None

    def _write(self, row: dict) -> None:
        self.stream.write(json.dumps(row) + "\n")
        self.stream.flush()

    def test(self, test_id: str) -> None:
        now = memory_now()
        rss = now["rss_kb"]
        change = None if rss is None or self.previous is None else rss - self.previous
        self.previous = rss if rss is not None else self.previous
        self._write({"test": test_id, "time": round(time.time(), 3), **now, "rss_change_kb": change,
                     "qt_widgets": qt_widgets_alive()})

    def marker(self, event: str, **more) -> None:
        try:
            self._write({"event": event, "time": round(time.time(), 3), **memory_now(), **more})
        except ValueError:  # the trace file is already closed
            pass


def tracing_result(trace, collect: bool, memory=None):
    class TracingResult(unittest.TextTestResult):
        def stopTestRun(self):
            super().stopTestRun()
            if memory is not None:
                memory.marker("tests_finished", tests_run=self.testsRun)

        def startTest(self, test):
            if collect:
                gc.collect()
                self._before = counts()
            super().startTest(test)

        def stopTest(self, test):
            super().stopTest(test)
            try:  # the test's cleanups are done; what they scheduled for deletion is deleted now, not at the process's end
                deliver_deferred_deletions()
            except Exception:  # a deletion that fails is this test's error, in the verdict and in the closing lines
                self.addError(test, sys.exc_info())
            row = {"test": test.id()}
            if collect:
                gc.collect()
                row["before"] = list(self._before)
            row["true"], row["false"] = counts()
            trace.write(json.dumps(row) + "\n")
            trace.flush()
            if memory is not None:
                memory.test(test.id())

    return TracingResult


def _mb(kb) -> str:
    return "?" if kb is None else f"{kb / 1024:.0f}"


def read_memory(trace_text: str) -> dict:
    """What a memory trace shows. The memory this process holds is resident plus swapped-out; a module's growth is that
    sum after its last test less the sum before its first, so memory that is given back within the module does not count."""
    tests, markers = [], []
    for line in trace_text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue  # a line cut short by the end of the process
        (tests if "test" in row else markers).append(row)

    def held(row):
        return None if not row or row.get("rss_kb") is None else row["rss_kb"] + (row.get("swap_kb") or 0)

    start = next((m for m in markers if m.get("event") == "start"), None)
    modules, steps, before = [], [], held(start)
    for row in tests:
        name, now = row["test"].split(".")[0], held(row)
        if not modules or modules[-1]["module"] != name:
            modules.append({"module": name, "tests": 0, "before_kb": before, "first": row["time"]})
        modules[-1].update(after_kb=now, last=row["time"])
        modules[-1]["tests"] += 1
        if now is not None and before is not None:
            steps.append((now - before, row["test"]))
        before = now if now is not None else before
    for module in modules:
        known = module["before_kb"] is not None and module["after_kb"] is not None
        module["growth_kb"] = module["after_kb"] - module["before_kb"] if known else None
    return {"tests": tests, "markers": markers, "modules": modules, "start": start, "last": tests[-1] if tests else None,
            "largest_steps": sorted(steps, reverse=True)[:10],
            "grown": sorted((m for m in modules if m["growth_kb"]), key=lambda m: -m["growth_kb"])}


def describe_memory(facts: dict) -> list:
    """(title, text) notices: the totals and the markers, the modules that grew the process most, the largest single
    steps, and the course of the run."""
    if not facts["tests"]:
        return [("memory trace", "no test is in the memory trace")]
    start, last = facts["start"] or {}, facts["last"]
    first_time = start.get("time", facts["tests"][0]["time"])

    def at(row):
        return (f"resident {_mb(row.get('rss_kb'))} + swapped {_mb(row.get('swap_kb'))} MB (peak resident "
                f"{_mb(row.get('peak_rss_kb'))}); machine: available {_mb(row.get('available_kb'))}, file cache "
                f"{_mb(row.get('cache_kb'))}, shared {_mb(row.get('shared_kb'))}, swap free {_mb(row.get('swap_free_kb'))} MB")

    marks = "; ".join(f"{m['event']} at +{m['time'] - first_time:.0f} s" + (f" [{m['threads']}]" if m.get("threads") else "")
                      for m in facts["markers"])
    held = [t["rss_kb"] + (t.get("swap_kb") or 0) for t in facts["tests"] if t.get("rss_kb") is not None]
    widgets = [t["qt_widgets"] for t in facts["tests"] if t.get("qt_widgets") is not None]
    more = (f" Largest resident + swapped after a test: {_mb(max(held))} MB." if held else "") + (
        f" Qt widgets alive after a test: {widgets[-1]} at the last such test, {max(widgets)} at most." if widgets else "")
    notices = [("memory trace: this process", f"{len(facts['tests'])} tests traced. At the start: {at(start)}. After the last "
                f"traced test ({last['test']}, +{last['time'] - first_time:.0f} s): {at(last)}. Markers: {marks}.{more}")]
    notices.append(("memory trace: modules that grew this process most (resident + swapped MB)", "; ".join(
        f"{m['module']} +{_mb(m['growth_kb'])} ({m['tests']} tests, {_mb(m['before_kb'])} -> {_mb(m['after_kb'])})"
        for m in facts["grown"][:14])))
    notices.append(("memory trace: largest single steps (MB)", "; ".join(f"{name} +{_mb(step)}" for step, name in
                                                                         facts["largest_steps"])))
    step = max(1, len(facts["modules"]) // 30)
    notices.append(("memory trace: course by module (minute - module = resident + swapped MB)", "; ".join(
        f"{(m['last'] - first_time) / 60:.0f} - {m['module']} = {_mb(m['after_kb'])}"
        for m in facts["modules"][::step] + facts["modules"][-1:])))
    return notices


def summarise_memory(path: str, title: str = "") -> int:
    for name, text in describe_memory(read_memory(_read(path))):
        print(f"::notice title={title}{name}::{text}", flush=True)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start", default="tests")
    parser.add_argument("--trace")
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--memory", help="also write a per-test trace of this process's memory to this file")
    parser.add_argument("--summarise-memory", help="read a memory trace and print what it shows; runs no test")
    parser.add_argument("--title", default="", help="a prefix for the titles of the memory notices")
    args = parser.parse_args(argv)
    if args.summarise_memory:
        return summarise_memory(args.summarise_memory, args.title)
    if not args.trace:
        parser.error("--trace is required")
    faulthandler.enable()
    memory = MemoryTrace(open(args.memory, "w", encoding="utf-8")) if args.memory else None
    with open(args.trace, "w", encoding="utf-8") as trace:
        first = counts()
        suite = unittest.TestLoader().discover(args.start)
        loaded = counts()
        trace.write(json.dumps({"python": sys.version.split()[0], "platform": sys.platform, "collect": args.collect,
                                "at_start": list(first), "true": loaded[0], "false": loaded[1]}) + "\n")
        trace.flush()
        if memory is not None:
            memory.marker("start", tests_loaded=suite.countTestCases())
            atexit.register(memory.marker, "process_exit")  # the last thing this process can say; the file stays open
        result = unittest.TextTestRunner(verbosity=2, resultclass=tracing_result(trace, args.collect, memory)).run(suite)
        if memory is not None:
            memory.marker("runner_returned", threads=", ".join(sorted(
                f"{t.name}{'' if t.daemon else ' (not daemon)'}" for t in threading.enumerate() if t is not threading.main_thread())))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
