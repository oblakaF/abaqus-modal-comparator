"""ABM-AUD-2: an honest summary of one ``python -m unittest -v`` log for the CI (no test is run here).

    python tests/ci_summary.py LOG --group "Linux full suite" [--min-tests N] [--no-skips] [--exit-code CODE]
                               [--refcounts TRACE]

It reads the log a test command wrote and reports what that log proves, nothing more:

* PASS only when the log ends with unittest's own ``Ran N tests`` and ``OK`` lines;
* a log without them is a run that did NOT finish (a native crash, a kill, a timeout): the tests after the last one
  named are NOT_RUN, and the summary is a failure whatever the command's exit code was said to be;
* skipped tests are counted and named as skipped, never added to the passed ones; ``SKIPPED_WINDOWS_ONLY`` skips (tests
  of the Win32 supervision, run natively by the Windows job) are counted apart;
* ``--no-skips`` makes any skip a failure (the Windows supervision job: every one of its tests has to run there);
* ``--exit-code`` is the exit code of the test command; a non-zero code is a failure even if the log looks complete;
* ``--refcounts`` is the trace ``tests/ci_run_suite.py`` wrote: the tests that lowered the reference counts of ``True``
  and ``False`` the most are named (the evidence for a ``bool_dealloc`` crash; it never changes the verdict).

It prints GitHub annotations (``::notice`` / ``::error``) and appends a table to ``$GITHUB_STEP_SUMMARY`` when that is set.
The exit code is 0 only for a complete, passing run that meets the given requirements.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

WINDOWS_ONLY = "SKIPPED_WINDOWS_ONLY"
PASS, FAIL, DID_NOT_FINISH = "PASS", "FAIL", "DID_NOT_FINISH"
MAX_NAMED = 8  # GitHub shows a limited number of annotations per step
CRASH_LINES = 30  # of the interpreter's own report after "Fatal Python error"
DRAINS_NAMED = 15


def read(log_text: str) -> dict:
    """What a unittest -v log proves: counts from unittest's own closing lines, the failed tests and the crash, if any."""
    lines = log_text.splitlines()
    ran = None
    for line in lines:
        found = re.match(r"^Ran (\d+) tests? in ", line)
        if found:
            ran = int(found.group(1))
    closing = ""
    for line in lines:
        if re.match(r"^(OK|FAILED)( \(.*\))?\s*$", line):
            closing = line.strip()
    parts = dict(re.findall(r"(\w+(?: \w+)?)=(\d+)", closing))
    failed = [re.sub(r"^(FAIL|ERROR): ", "", line).strip() for line in lines if re.match(r"^(FAIL|ERROR): ", line)]
    failed = list(dict.fromkeys(failed))  # unittest prints each once; a tee'd log may repeat a line
    skipped_lines = [line for line in lines if re.search(r"\.\.\. skipped ", line)]
    fatal = [line.strip() for line in lines if "Fatal Python error" in line]
    crash = []
    for number, line in enumerate(lines):
        if "Fatal Python error" in line:
            crash = [text.rstrip() for text in lines[number:number + CRASH_LINES] if text.strip()]
            break
    started = [line for line in lines if re.search(r" \.\.\. ", line) or re.match(r"^test\w* \(", line)]
    finished = ran is not None and bool(closing)
    counts = {key: int(parts.get(key, 0)) for key in ("failures", "errors", "skipped", "expected failures",
                                                      "unexpected successes")}
    passed = None
    if finished:
        passed = ran - counts["failures"] - counts["errors"] - counts["skipped"] - counts["expected failures"] \
            - counts["unexpected successes"]
    return {"finished": finished, "ran": ran, "closing": closing, "passed": passed, **counts, "failed_tests": failed,
            "windows_only_skips": sum(WINDOWS_ONLY in line for line in skipped_lines),
            "skipped_lines": len(skipped_lines), "fatal": fatal, "crash_report": crash,
            "last_test_named": started[-1].strip()[:200] if started else ""}


def verdict(facts: dict, exit_code=None, min_tests: int = 1, no_skips: bool = False) -> tuple:
    """(PASS / FAIL / DID_NOT_FINISH, the reasons). A skip is never a pass; an unfinished run is never a pass."""
    reasons = []
    if not facts["finished"]:
        reasons.append("the log has no closing 'Ran N tests' / 'OK' lines: the run did not finish"
                       + (f" ({facts['fatal'][0]})" if facts["fatal"] else "")
                       + (f"; last test named: {facts['last_test_named']}" if facts["last_test_named"] else "")
                       + "; every test after it is NOT_RUN")
        return DID_NOT_FINISH, reasons
    if not facts["closing"].startswith("OK"):
        reasons.append(f"unittest closed with '{facts['closing']}'")
    if facts["failures"] or facts["errors"] or facts["unexpected successes"] or facts["failed_tests"]:
        reasons.append(f"{facts['failures']} failure(s), {facts['errors']} error(s), "
                       f"{facts['unexpected successes']} unexpected success(es)")
    if facts["ran"] < min_tests:
        reasons.append(f"only {facts['ran']} test(s) ran; at least {min_tests} are required")
    if no_skips and facts["skipped"]:
        reasons.append(f"{facts['skipped']} test(s) were skipped; this group accepts no skip")
    if exit_code not in (None, 0):
        reasons.append(f"the test command exited with code {exit_code}")
    return (FAIL if reasons else PASS), reasons


def describe(group: str, facts: dict, outcome: str, reasons) -> str:
    if not facts["finished"]:
        return f"{group}: {outcome}. " + " ".join(reasons)
    other = facts["skipped"] - facts["windows_only_skips"]
    text = (f"{group}: {outcome}. Ran {facts['ran']}: passed {facts['passed']}, failed {facts['failures']}, errors "
            f"{facts['errors']}, skipped {facts['skipped']} ({facts['windows_only_skips']} {WINDOWS_ONLY}, {other} other)."
            " Skipped tests are not passes.")
    return text + (" " + " ".join(reasons) if reasons else "")


def read_refcounts(trace_text: str) -> dict:
    """The trace of ``ci_run_suite``: where the counts of True / False started, their lowest and last values, and the tests
    over which they fell the most. A fall is evidence, not proof: a test may only release what earlier tests kept."""
    rows = []
    for line in trace_text.splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue  # a line cut short by the crash
    if not rows:
        return {}
    head, tests = rows[0], rows[1:]
    falls, previous = [], (head["true"], head["false"])
    for row in tests:
        before = tuple(row.get("before", previous))
        change = (row["true"] - before[0], row["false"] - before[1])
        if min(change) < 0:
            falls.append((change[0] + change[1], row["test"], change))
        previous = (row["true"], row["false"])
    modules = {}
    for total, name, _change in falls:
        modules[name.split(".")[0]] = modules.get(name.split(".")[0], 0) + total
    last = tests[-1] if tests else head
    return {"head": head, "tests": len(tests), "last": last, "falls": sorted(falls)[:DRAINS_NAMED],
            "falling_tests": len(falls), "modules": sorted(modules.items(), key=lambda item: item[1])[:DRAINS_NAMED],
            "lowest": (min(row["true"] for row in rows), min(row["false"] for row in rows))}


def describe_refcounts(facts: dict) -> str:
    if not facts:
        return "no reference-count trace was written"
    head, last = facts["head"], facts["last"]
    text = (f"Python {head.get('python')} on {head.get('platform')}; True/False reference counts: {head['true']}/"
            f"{head['false']} after loading, lowest {facts['lowest'][0]}/{facts['lowest'][1]}, {last['true']}/{last['false']} "
            f"after the last of {facts['tests']} traced test(s) ({last.get('test', 'none')}). {facts['falling_tests']} test(s) "
            "lowered a count.")
    if facts["falls"]:
        text += " Largest falls (True, False): " + "; ".join(
            f"{name} ({change[0]:+d}, {change[1]:+d})" for _total, name, change in facts["falls"])
        text += ". By module: " + "; ".join(f"{name} {total:+d}" for name, total in facts["modules"])
    return text


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("log")
    parser.add_argument("--group", required=True)
    parser.add_argument("--min-tests", type=int, default=1)
    parser.add_argument("--no-skips", action="store_true")
    parser.add_argument("--exit-code", type=int, default=None)
    parser.add_argument("--refcounts", default=None)
    args = parser.parse_args(argv)
    path = Path(args.log)
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    facts = read(text)
    outcome, reasons = verdict(facts, args.exit_code, args.min_tests, args.no_skips)
    if not path.is_file():
        outcome, reasons = DID_NOT_FINISH, [f"the log {path} was not written: the group did not run (NOT_RUN)"]
    summary = describe(args.group, facts, outcome, reasons)
    print(f"::{'notice' if outcome == PASS else 'error'} title={args.group}: {outcome}::{summary}")
    for name in facts["failed_tests"][:MAX_NAMED]:
        print(f"::error title={args.group}: failed test::{name}")
    if len(facts["failed_tests"]) > MAX_NAMED:
        print(f"::error title={args.group}: failed tests::and {len(facts['failed_tests']) - MAX_NAMED} more; see the log")
    if facts["crash_report"]:  # the interpreter's own words; "%0A" is a line break inside an annotation
        print(f"::error title={args.group}: crash report::" + "%0A".join(facts["crash_report"]))
    counts = ""
    if args.refcounts:
        trace = Path(args.refcounts)
        counts = describe_refcounts(read_refcounts(trace.read_text(encoding="utf-8", errors="replace")
                                                   if trace.is_file() else ""))
        print(f"::notice title={args.group}: True/False reference counts::{counts}")
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(f"### {args.group}: {outcome}\n\n{summary}\n\n")
            if facts["failed_tests"]:
                handle.write("".join(f"- `{name}`\n" for name in facts["failed_tests"]) + "\n")
            if facts["crash_report"]:
                handle.write("```\n" + "\n".join(facts["crash_report"]) + "\n```\n\n")
            if counts:
                handle.write(counts + "\n\n")
    return 0 if outcome == PASS else 1


if __name__ == "__main__":
    sys.exit(main())
