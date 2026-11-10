"""ABM-AUD-2: where do references to ``True`` go? A diagnosis for the CI, not a test module.

    python tests/ci_bool_refcount_probe.py

The traced Linux run (Python 3.11) showed tests of pages that run a calculation on a Python thread losing thousands of
references to ``True`` each, until ``Fatal Python error: bool_dealloc``. This script repeats small operations of that
kind many times and prints the change of ``sys.getrefcount(True)`` / ``(False)`` for each as a GitHub notice: an operation
that takes or gives back the wrong number of references shows a change proportional to the repeat count.
"""

from __future__ import annotations

import gc
import os
import sys
import threading
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "src"), str(HERE)]
N = 500


def counts():
    return sys.getrefcount(True), sys.getrefcount(False)


def measure(action) -> tuple:
    gc.collect()
    before = counts()
    action()
    gc.collect()
    after = counts()
    return after[0] - before[0], after[1] - before[1]


def main() -> int:
    import PySide6
    import shiboken6
    from PySide6.QtCore import QObject, Qt, Signal
    from PySide6.QtWidgets import QApplication, QLabel

    import matplotlib
    import numpy
    import scipy

    app = QApplication.instance() or QApplication([])
    print(f"::notice title=bool probe 00::Python {sys.version.split()[0]} on {sys.platform}; PySide6 {PySide6.__version__}, "
          f"shiboken6 {shiboken6.__version__}, numpy {numpy.__version__}, scipy {scipy.__version__}, matplotlib "
          f"{matplotlib.__version__}; counts at start {counts()}", flush=True)

    class Bridge(QObject):
        two = Signal(int, int)
        three = Signal(int, str, object)
        flag = Signal(bool)

    class Receiver(QObject):
        def __init__(self):
            super().__init__()
            self.seen = 0

        def take(self, *_args):
            self.seen += 1

    def drain(receiver, expected):
        end = time.monotonic() + 30
        while receiver.seen < expected and time.monotonic() < end:
            app.processEvents()
            time.sleep(0.001)
        app.processEvents()

    def in_thread(work):
        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        while thread.is_alive():
            app.processEvents()
            time.sleep(0.001)
        thread.join()

    results = []

    def case(name, action):
        print(f"starting: {name}; counts now {counts()}", flush=True)
        try:
            results.append((name, measure(action)))
        except Exception as error:  # noqa: BLE001  (a diagnosis reports everything it can)
            results.append((name, f"{type(error).__name__}: {error}"))
        # said at once: a case that ends the process must not take the earlier answers with it
        print(f"::notice title=bool probe {len(results):02d}::{name}: {results[-1][1]} (True, False) over {N} repeats; "
              f"counts now {counts()}", flush=True)

    def emit_case(signal_name, args, threaded, connected=True, keep_result=False, connection=None):
        def action():
            bridge, receiver = Bridge(), Receiver()
            if connected:
                signal = getattr(bridge, signal_name)
                if connection is None:
                    signal.connect(receiver.take)
                else:
                    signal.connect(receiver.take, connection)

            def work():
                kept = []
                for _ in range(N):
                    value = getattr(bridge, signal_name).emit(*args)
                    if keep_result:
                        kept.append(value)
                del kept

            if threaded:
                in_thread(work)
            else:
                work()
            drain(receiver, N if connected else 0)
        return action

    label = QLabel()
    case("nothing (the measurement itself)", lambda: None)
    case("processEvents + sleep loop", lambda: [app.processEvents() or time.sleep(0) for _ in range(N)])
    case("QLabel.setText", lambda: [label.setText(str(i)) for i in range(N)])
    case("thread.is_alive polled", lambda: in_thread(lambda: time.sleep(0.2)))
    case("emit(int, int), main thread, connected", emit_case("two", (1, 2), False))
    if os.environ.get("PROBE_QUICK") == "1":  # the version matrix: one clear answer per combination
        change = results[-1][1]
        print(f"::notice title=bool probe matrix::Python {sys.version.split()[0]}, PySide6 {PySide6.__version__} on "
              f"{sys.platform}: {N} x Signal.emit() changed the reference counts of (True, False) by {change}", flush=True)
        return 0
    case("emit(int, int), main thread, not connected", emit_case("two", (1, 2), False, connected=False))
    case("emit(int, int), main thread, result kept", emit_case("two", (1, 2), False, keep_result=True))
    case("emit(int, int), main thread, queued", emit_case("two", (1, 2), False, connection=Qt.ConnectionType.QueuedConnection))
    case("emit(int, int), Python thread, connected", emit_case("two", (1, 2), True))
    case("emit(int, int), Python thread, not connected", emit_case("two", (1, 2), True, connected=False))
    case("emit(int, str, object), main thread", emit_case("three", (1, "fit", {"a": 1}), False))
    case("emit(int, str, object), Python thread", emit_case("three", (1, "fit", {"a": 1}), True))
    case("emit(bool True), main thread", emit_case("flag", (True,), False))
    case("emit(bool True), Python thread", emit_case("flag", (True,), True))
    case("emit(bool False), Python thread", emit_case("flag", (False,), True))
    probe = Bridge()
    value = probe.two.emit(1, 2)
    emit_returns = f"{value!r} ({type(value).__name__})"

    import test_real_fit_r1_tuning as fixtures
    from services import research_frequency_tuning as rft

    inputs = rft.read_inp(fixtures._files() / "plate.inp")
    surrogate = rft.Surrogate(inputs, 14, 16)
    spectrum = surrogate.frequencies(60000, 44000, 4800)
    request = rft.TuningRequest(rft.observations_by_rank([(k + 1, float(spectrum[k])) for k in range(10)]), rft.FREE)
    solves = []

    def fit(progress=None):
        outcome = rft.run_tuning(inputs, request, (), threading.Event(), progress)
        solves.append(outcome.status)

    def fit_emitting():
        bridge, receiver = Bridge(), Receiver()
        bridge.two.connect(receiver.take)
        emitted = []

        def progress(count):
            emitted.append(count)
            bridge.two.emit(1, count)

        in_thread(lambda: fit(progress))
        drain(receiver, len(emitted))
        solves.append(f"{len(emitted)} progress calls")

    case("300 surrogate solves, main thread", lambda: [surrogate.frequencies(60000 + i, 44000, 4800) for i in range(300)])
    case("300 surrogate solves, Python thread",
         lambda: in_thread(lambda: [surrogate.frequencies(60000 + i, 44000, 4800) for i in range(300)]))
    case("run_tuning, main thread, no progress", fit)
    case("run_tuning, main thread, progress = list.append", lambda: fit([].append))
    case("run_tuning, Python thread, no progress", lambda: in_thread(fit))
    case("run_tuning, Python thread, progress = list.append", lambda: in_thread(lambda: fit([].append)))
    case("run_tuning, Python thread, progress emits a signal", fit_emitting)
    results.append(("fit outcomes", ", ".join(map(str, solves))))

    def run_tests(*names):
        def action():
            suite = unittest.TestSuite(unittest.TestLoader().loadTestsFromName(name) for name in names)
            outcome = unittest.TextTestRunner(verbosity=0, stream=open(os.devnull, "w")).run(suite)
            if not outcome.wasSuccessful() or not outcome.testsRun:
                raise RuntimeError(f"ran {outcome.testsRun}, failures {len(outcome.failures)}, errors {len(outcome.errors)}")
        return action

    case("test_real_fit_r1_tuning.Page.test_roles_and_cancel", run_tests("test_real_fit_r1_tuning.Page.test_roles_and_cancel"))
    case("the same test again", run_tests("test_real_fit_r1_tuning.Page.test_roles_and_cancel"))
    case("test_real_fit_r2_stability.Page (export of the stability check)",
         run_tests("test_real_fit_r2_stability.Page.test_the_page_shows_and_exports_the_stability_check"))
    versions = (f"Python {sys.version.split()[0]} on {sys.platform}; PySide6 {PySide6.__version__}, shiboken6 "
                f"{shiboken6.__version__}, numpy {numpy.__version__}, scipy {scipy.__version__}, matplotlib "
                f"{matplotlib.__version__}; emit() returns {emit_returns}; {N} repeats per case")
    text = versions + ". Change of the reference counts (True, False): " + "; ".join(
        f"{name}: {change}" for name, change in results)
    print(f"::notice title=bool reference-count probe::{text}")
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write("### bool reference-count probe\n\n" + versions + "\n\n"
                         + "".join(f"- {name}: `{change}`\n" for name, change in results) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
