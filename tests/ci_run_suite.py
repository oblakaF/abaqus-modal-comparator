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
"""

from __future__ import annotations

import argparse
import faulthandler
import gc
import json
import sys
import unittest


def counts() -> tuple:
    return sys.getrefcount(True), sys.getrefcount(False)


def tracing_result(trace, collect: bool):
    class TracingResult(unittest.TextTestResult):
        def startTest(self, test):
            if collect:
                gc.collect()
                self._before = counts()
            super().startTest(test)

        def stopTest(self, test):
            super().stopTest(test)
            row = {"test": test.id()}
            if collect:
                gc.collect()
                row["before"] = list(self._before)
            row["true"], row["false"] = counts()
            trace.write(json.dumps(row) + "\n")
            trace.flush()

    return TracingResult


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start", default="tests")
    parser.add_argument("--trace", required=True)
    parser.add_argument("--collect", action="store_true")
    args = parser.parse_args(argv)
    faulthandler.enable()
    with open(args.trace, "w", encoding="utf-8") as trace:
        first = counts()
        suite = unittest.TestLoader().discover(args.start)
        loaded = counts()
        trace.write(json.dumps({"python": sys.version.split()[0], "platform": sys.platform, "collect": args.collect,
                                "at_start": list(first), "true": loaded[0], "false": loaded[1]}) + "\n")
        trace.flush()
        result = unittest.TextTestRunner(verbosity=2, resultclass=tracing_result(trace, args.collect)).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
