"""ABM-AUD-2: the CI summary reports what a test log proves. A skip is not a pass, and a run that did not finish (a native
crash, a kill) is a failure with the remaining tests NOT_RUN, whatever exit code a shell pipeline reported."""

from __future__ import annotations

import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ci_summary as cs  # noqa: E402

PASSING = """test_a (m.C.test_a) ... ok
test_b (m.C.test_b) ... skipped 'SKIPPED_WINDOWS_ONLY: Win32 Job Object supervision'
test_c (m.C.test_c) ... skipped 'no display'
test_d (m.C.test_d) ... ok

----------------------------------------------------------------------
Ran 4 tests in 0.010s

OK (skipped=2)
"""
FAILING = """test_a (m.C.test_a) ... ok
test_b (m.C.test_b) ... FAIL
test_c (m.C.test_c) ... ERROR

======================================================================
ERROR: test_c (m.C.test_c)
----------------------------------------------------------------------
Traceback (most recent call last):
ValueError: x
======================================================================
FAIL: test_b (m.C.test_b)
----------------------------------------------------------------------
AssertionError: 1 != 2

----------------------------------------------------------------------
Ran 3 tests in 0.010s

FAILED (failures=1, errors=1)
"""
CRASHED = """test_a (m.C.test_a) ... ok
test_b (m.C.test_b) ... Fatal Python error: bool_dealloc: deallocating True or False: bug likely caused by a refcount error in a C extension
Python runtime state: initialized

Current thread 0x00007f (most recent call first):
  File "x.py", line 1 in f
"""


class Summary(unittest.TestCase):
    def run_main(self, text, *options):
        folder = Path(tempfile.mkdtemp())
        log = folder / "log.txt"
        if text is not None:
            log.write_text(text, encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out), mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(folder / "summary.md")}):
            code = cs.main([str(log), "--group", "G", *options])
        page = (folder / "summary.md").read_text(encoding="utf-8") if (folder / "summary.md").is_file() else ""
        return code, out.getvalue(), page

    def test_a_skip_is_counted_as_a_skip_and_never_as_a_pass(self):
        facts = cs.read(PASSING)
        self.assertEqual((facts["ran"], facts["passed"], facts["skipped"], facts["windows_only_skips"]), (4, 2, 2, 1))
        code, out, page = self.run_main(PASSING)
        self.assertEqual(code, 0)
        self.assertIn("::notice title=G: PASS::", out)
        for part in ("Ran 4: passed 2", "skipped 2 (1 SKIPPED_WINDOWS_ONLY, 1 other)", "Skipped tests are not passes"):
            self.assertIn(part, out)
            self.assertIn(part, page)

    def test_a_group_that_accepts_no_skip_fails_on_one(self):
        code, out, _page = self.run_main(PASSING, "--no-skips")
        self.assertEqual(code, 1)
        self.assertIn("::error title=G: FAIL::", out)
        self.assertIn("2 test(s) were skipped; this group accepts no skip", out)

    def test_failures_are_named_and_fail_the_group(self):
        code, out, page = self.run_main(FAILING)
        self.assertEqual(code, 1)
        self.assertIn("failed 1, errors 1", out)
        self.assertIn("::error title=G: failed test::test_b (m.C.test_b)", out)
        self.assertIn("::error title=G: failed test::test_c (m.C.test_c)", out)
        self.assertIn("- `test_b (m.C.test_b)`", page)

    def test_a_native_crash_is_not_a_pass_even_with_exit_code_zero(self):
        code, out, _page = self.run_main(CRASHED, "--exit-code", "0")  # what a pipeline without pipefail would report
        self.assertEqual(code, 1)
        self.assertIn("::error title=G: DID_NOT_FINISH::", out)
        self.assertIn("the run did not finish", out)
        self.assertIn("bool_dealloc", out)
        self.assertIn("test_b (m.C.test_b)", out)  # where it stopped
        self.assertIn("NOT_RUN", out)
        self.assertNotIn("PASS", out)

    def test_a_missing_log_or_too_few_tests_or_a_failed_command_is_a_failure(self):
        code, out, _page = self.run_main(None)
        self.assertEqual(code, 1)
        self.assertIn("did not run (NOT_RUN)", out)
        code, out, _page = self.run_main(PASSING, "--min-tests", "18")
        self.assertEqual(code, 1)
        self.assertIn("only 4 test(s) ran; at least 18 are required", out)
        code, out, _page = self.run_main(PASSING, "--exit-code", "134")
        self.assertEqual(code, 1)
        self.assertIn("exited with code 134", out)
        self.assertEqual(self.run_main("")[0], 1)  # an empty log proves nothing

    def test_the_crash_report_and_the_reference_count_trace_are_shown_and_change_no_verdict(self):
        folder = Path(tempfile.mkdtemp())
        trace = folder / "trace.jsonl"
        trace.write_text('{"python": "3.11.9", "platform": "linux", "true": 1000, "false": 900}\n'
                         '{"test": "m.C.test_a", "true": 1010, "false": 905}\n'
                         '{"test": "m.C.test_b", "true": 400, "false": 905}\n'
                         '{"test": "n.D.test_c", "before": [400, 905], "true": 390, "false": 5}\n'
                         '{"test": "n.D.test_d", "tr', encoding="utf-8")  # the last line was cut short by the crash
        facts = cs.read_refcounts(trace.read_text(encoding="utf-8"))
        self.assertEqual((facts["tests"], facts["falling_tests"], facts["lowest"]), (3, 2, (390, 5)))
        self.assertEqual([name for _total, name, _change in facts["falls"]], ["n.D.test_c", "m.C.test_b"])
        self.assertEqual(facts["modules"], [("n", -910), ("m", -610)])
        code, out, page = self.run_main(CRASHED, "--refcounts", str(trace))
        self.assertEqual(code, 1)
        self.assertIn("::error title=G: crash report::", out)
        self.assertIn("bool_dealloc: deallocating True or False: bug likely caused by a refcount error in a C extension || "
                      "Python runtime state: initialized || Current thread", out)
        self.assertIn("::notice title=G: True/False reference counts::Python 3.11.9 on linux", out)
        for part in ("lowest 390/5", "n.D.test_c (-10, -900)", "m.C.test_b (-610, +0)", "By module: n -910; m -610"):
            self.assertIn(part, out)
            self.assertIn(part, page)
        code, out, _page = self.run_main(PASSING, "--refcounts", str(trace))
        self.assertEqual(code, 0)  # the trace is evidence; it decides nothing
        code, out, _page = self.run_main(PASSING, "--refcounts", str(folder / "absent.jsonl"))
        self.assertEqual(code, 0)
        self.assertIn("no reference-count trace was written", out)

    def test_the_suite_runner_traces_every_test_and_returns_unittests_verdict(self):
        import ci_run_suite as runner
        folder = Path(tempfile.mkdtemp())
        (folder / "test_sample.py").write_text(
            "import unittest\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        pass\n\n"
            "    def test_bad(self):\n        self.fail('x')\n", encoding="utf-8")
        trace = folder / "trace.jsonl"
        self.addCleanup(sys.modules.pop, "test_sample", None)  # discovery imports the sample and adds its folder
        self.addCleanup(lambda: str(folder) in sys.path and sys.path.remove(str(folder)))
        stream = io.StringIO()
        with mock.patch.object(sys, "stderr", stream), mock.patch.object(runner.faulthandler, "enable"):
            code = runner.main(["--start", str(folder), "--trace", str(trace), "--collect"])
        self.assertEqual(code, 1)
        facts = cs.read(stream.getvalue())
        self.assertEqual((facts["ran"], facts["failures"], facts["failed_tests"]),
                         (2, 1, ["test_bad (test_sample.T.test_bad)"]))
        rows = cs.read_refcounts(trace.read_text(encoding="utf-8"))
        self.assertEqual((rows["tests"], rows["head"]["platform"]), (2, sys.platform))

    def test_many_failures_are_listed_up_to_the_annotation_limit(self):
        names = [f"test_{i} (m.C.test_{i})" for i in range(12)]
        text = "".join(f"FAIL: {n}\n" for n in names) + "\nRan 12 tests in 0.1s\n\nFAILED (failures=12)\n"
        code, out, page = self.run_main(text)
        self.assertEqual(code, 1)
        self.assertEqual(out.count("failed test::"), cs.MAX_NAMED)
        self.assertIn("and 4 more", out)
        self.assertEqual(page.count("- `test_"), 12)  # the summary page names every one


if __name__ == "__main__":
    unittest.main()
