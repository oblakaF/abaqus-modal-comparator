"""CI-LINUX-PERF-ROOT-CAUSE-1: on one Linux runner, time real numerical test modules with the default native threading
and with one native thread (this file is not a test module).

    python tests/ci_blas_threading_probe.py --out blas-threading-probe.json [--rounds 2] [--limit 1500]
    python tests/ci_blas_threading_probe.py --out machine.json --rounds 0 --title "machine before the suite"

Every measurement is one ``python -m unittest <module>`` in a process of its own, with the module's own assertions; the
only thing that differs between the two modes is the three variables OPENBLAS_NUM_THREADS, OMP_NUM_THREADS and
MKL_NUM_THREADS. The modes alternate (default, one, default, one, ...), so a slow machine and a slow mode can be told
apart. For each process: wall time, user and system CPU time, context switches, the largest number of threads seen, the
CPU time the hypervisor gave to others meanwhile (steal) and the load average. Nothing is asserted about the times:
the result is a record, printed, saved as JSON and shown as GitHub notices.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import tempfile
import time

TESTS = Path(__file__).resolve().parent
MODULES = ("test_abm_aud5_ritz_estimation", "test_abm_aud6_uncertainty_report")
VARIABLES = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
DESCRIBE = r"""
import json, os, sys
import numpy as np, scipy
from scipy import linalg
a = np.random.default_rng(0).standard_normal((400, 400)); a = a @ a.T
linalg.eigh(a); np.linalg.solve(a + 400 * np.eye(400), a)
threads = [line.split()[1] for line in open("/proc/self/status") if line.startswith("Threads:")]
blas = {}
for name, module in (("numpy", np), ("scipy", scipy)):
    try:
        config = module.show_config(mode="dicts")
        blas[name] = {k: {f: v.get(f) for f in ("name", "version", "openblas configuration") if isinstance(v, dict)}
                      for k, v in config.get("Build Dependencies", {}).items()}
    except Exception as error:
        blas[name] = repr(error)
print(json.dumps({"numpy": np.__version__, "scipy": scipy.__version__, "threads_after_blas_calls": int(threads[0]),
                  "blas": blas}))
"""


def read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except OSError as error:
        return f"unreadable ({error.__class__.__name__})"


def steal_ticks() -> int:
    try:
        return int(read("/proc/stat").splitlines()[0].split()[8])
    except (IndexError, ValueError):
        return -1


def cpu_seconds() -> dict:
    """The machine's CPU time since it started, by kind (all processors together)."""
    try:
        cells = [int(v) / os.sysconf("SC_CLK_TCK") for v in read("/proc/stat").splitlines()[0].split()[1:9]]
    except (IndexError, ValueError, AttributeError):
        return {}
    return dict(zip(("user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal"), (round(v, 1) for v in cells)))


def watched(path: str) -> dict:
    """What the once-a-minute samples taken beside the full suite say: ``epoch load1 MemAvailable_kB SwapFree_kB`` and
    the first line of /proc/stat."""
    rows = []
    for line in read(path).splitlines():
        cells = line.split()
        try:
            rows.append((int(cells[0]), float(cells[1]), int(cells[2]), int(cells[3]), [int(v) for v in cells[5:13]]))
        except (IndexError, ValueError):
            continue
    if len(rows) < 2:
        return {"samples": len(rows)}
    ticks, start = os.sysconf("SC_CLK_TCK"), rows[0][0]
    names = ("user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal")
    spent = {n: round((b - a) / ticks) for n, a, b in zip(names, rows[0][4], rows[-1][4]) if b - a}
    step = max(1, len(rows) // 12)
    return {"samples": len(rows), "seconds": rows[-1][0] - start, "cpu_s": spent, "max_load1": max(r[1] for r in rows),
            "min_mem_available_MB": min(r[2] for r in rows) // 1024, "min_swap_free_MB": min(r[3] for r in rows) // 1024,
            "first_swap_free_MB": rows[0][3] // 1024,
            "minute:load1:available_MB": [f"{(r[0] - start) // 60}:{r[1]}:{r[2] // 1024}" for r in rows[::step]]}


def environment(one_thread: bool) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in VARIABLES}
    if one_thread:
        env.update({name: "1" for name in VARIABLES})
    return env


def machine() -> dict:
    cpus = [line.split(":", 1)[1].strip() for line in read("/proc/cpuinfo").splitlines() if line.startswith("model name")]
    return {
        "python": sys.version.split()[0], "platform": platform.platform(), "cpu_models": sorted(set(cpus)),
        "cpu_count": os.cpu_count(), "affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
        "cgroup_cpu_max": read("/sys/fs/cgroup/cpu.max"), "cgroup_v1_quota": read("/sys/fs/cgroup/cpu/cpu.cfs_quota_us"),
        "memory": [line for line in read("/proc/meminfo").splitlines() if line.startswith(("MemTotal", "MemAvailable"))],
        "loadavg": read("/proc/loadavg"), "uptime_s": read("/proc/uptime").split()[0],
        "cpu_seconds_since_boot": cpu_seconds(),
        "runner": {name: os.environ.get(name) for name in ("RUNNER_NAME", "RUNNER_OS", "RUNNER_ARCH", "ImageOS", "ImageVersion",
                                                           "RUNNER_ENVIRONMENT", "GITHUB_RUN_ID", "GITHUB_SHA")},
        "variables_in_the_job": {name: os.environ.get(name) for name in VARIABLES},
    }


def describe(one_thread: bool) -> dict:
    done = subprocess.run([sys.executable, "-c", DESCRIBE], env=environment(one_thread), capture_output=True, text=True)
    try:
        return json.loads(done.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        return {"error": (done.stderr or done.stdout)[-400:]}


def measure(module: str, one_thread: bool, limit: float) -> dict:
    before, steal, started = resource.getrusage(resource.RUSAGE_CHILDREN), steal_ticks(), time.monotonic()
    output = tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace")
    child = subprocess.Popen([sys.executable, "-X", "faulthandler", "-m", "unittest", module], cwd=TESTS,
                             env=environment(one_thread), stdout=output, stderr=subprocess.STDOUT)
    threads, finished = 0, True
    while child.poll() is None:
        for line in read(f"/proc/{child.pid}/status").splitlines():
            if line.startswith("Threads:"):
                threads = max(threads, int(line.split()[1]))
        if time.monotonic() - started > limit:
            child.kill()
            finished = False
        time.sleep(0.5)
    wall = time.monotonic() - started
    output.seek(0)
    tail = output.read().strip().splitlines()[-4:]
    output.close()
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    ticks = os.sysconf("SC_CLK_TCK")
    return {"module": module, "mode": "one thread" if one_thread else "default", "finished": finished, "exit_code": child.returncode,
            "closing_lines": tail, "wall_s": round(wall, 1), "user_s": round(after.ru_utime - before.ru_utime, 1),
            "system_s": round(after.ru_stime - before.ru_stime, 1), "peak_threads": threads,
            "voluntary_switches": after.ru_nvcsw - before.ru_nvcsw, "involuntary_switches": after.ru_nivcsw - before.ru_nivcsw,
            "steal_s": round((steal_ticks() - steal) / ticks, 1) if steal >= 0 else None, "loadavg_after": read("/proc/loadavg")}


def notice(title: str, text: str) -> None:
    print(f"::notice title={title}::{text}", flush=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True)
    parser.add_argument("--rounds", type=int, default=2, help="0 records the machine only")
    parser.add_argument("--title", default="probe machine")
    parser.add_argument("--watched", help="a file of once-a-minute samples taken beside the suite, to be summarised")
    parser.add_argument("--limit", type=float, default=1500.0, help="seconds after which one measurement is ended and recorded")
    args = parser.parse_args(argv)
    record = {"machine": machine(), "default": describe(False), "one_thread": describe(True), "runs": []}
    print(json.dumps({k: record[k] for k in ("machine", "default", "one_thread")}, indent=1), flush=True)
    shown = record["machine"]
    notice(args.title, json.dumps({"py": shown["python"], "cpu": shown["cpu_models"], "n": shown["cpu_count"],
                                        "affinity": shown["affinity"], "cpu.max": shown["cgroup_cpu_max"],
                                        "image": shown["runner"]["ImageVersion"], "kernel": shown["platform"],
                                        "uptime": shown["uptime_s"], "load": shown["loadavg"],
                                        "cpu_s": shown["cpu_seconds_since_boot"],
                                        "numpy": record["default"].get("numpy"), "scipy": record["default"].get("scipy"),
                                        "blas": record["default"].get("blas"),
                                        "threads default": record["default"].get("threads_after_blas_calls"),
                                        "threads one": record["one_thread"].get("threads_after_blas_calls")}))
    Path(args.out).write_text(json.dumps(record, indent=1), encoding="utf-8")
    if args.watched:
        record["watched"] = watched(args.watched)
        notice(args.title + " (samples)", json.dumps(record["watched"]))
        Path(args.out).write_text(json.dumps(record, indent=1), encoding="utf-8")
    for round_number in range(1, args.rounds + 1):
        for one_thread in (False, True):
            for module in MODULES:
                run = dict(measure(module, one_thread, args.limit), round=round_number)
                record["runs"].append(run)
                print(json.dumps(run), flush=True)
                Path(args.out).write_text(json.dumps(record, indent=1), encoding="utf-8")
            rows = [r for r in record["runs"] if r["round"] == round_number and r["mode"] == ("one thread" if one_thread else "default")]
            notice(f"probe round {round_number} {rows[0]['mode']}", " || ".join(
                f"{r['module'][9:13]}: wall {r['wall_s']} user {r['user_s']} sys {r['system_s']} threads {r['peak_threads']} "
                f"vcsw {r['voluntary_switches']} ivcsw {r['involuntary_switches']} steal {r['steal_s']} load {r['loadavg_after'][:14]} "
                f"{'ok' if r['finished'] and r['exit_code'] == 0 else 'NOT FINISHED/FAILED ' + str(r['closing_lines'][-1:])}" for r in rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
