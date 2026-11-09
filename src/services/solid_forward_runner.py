"""ABM-SOLID-5: one supervised offline C3D8I forward solve in a child Python process (Windows).

Supervision (fixes the ABM-SOLID-4 monitoring failure, where only the venv launcher was watched):

* The child is created SUSPENDED, assigned to a Windows Job Object, then resumed.  Every process it starts
  (the venv launcher starts the real interpreter) belongs to the same job before it can run.
* The job enforces a kernel memory limit for all its processes together, reports the measured peak
  (``PeakJobMemoryUsed``) and is closed with KILL_ON_JOB_CLOSE, so no worker can outlive the supervisor.
* The worker reports its own PID first.  The run is refused unless that process is verified to be in the job.
* Wall-clock, silence (no progress line) and system free-memory floors terminate the whole job.
* Cancellation terminates the whole job; afterwards the job is checked to hold no active process.

The child verifies the INP SHA-256 the owner confirmed, imports the model with ``solid_c3d8i_model`` and solves
ONCE with ``solid_c3d8i_solver`` at the INP material.  No Abaqus, no parameter change, no file written.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from typing import Callable, Optional

GiB = 1024 ** 3
SOLVED, REFUSED, CANCELLED, FAILED, KILLED = "SOLVED", "REFUSED", "CANCELLED", "FAILED", "KILLED"
RESULT_LABEL = ("RESEARCH NUMERICAL FORWARD RESULT: offline C3D8I reference element (Abaqus equivalence NOT_VERIFIED) "
                "at the INP's own material values; not identified material properties, not a physical validation.")


@dataclass(frozen=True)
class RunnerLimits:
    max_job_memory_bytes: int = 6 * GiB      # kernel limit for all worker processes together
    reserve_free_memory_bytes: int = 2 * GiB # the system must keep this much physical memory available
    max_seconds: float = 3600.0
    max_silence_seconds: float = 1200.0      # SuperLU factorisation reports no progress while it runs
    handshake_seconds: float = 120.0


@dataclass(frozen=True)
class ForwardRequest:
    inp_path: str
    inp_sha256: str
    elastic_modes: int = 14
    guard_modes: int = 4


@dataclass
class RunnerOutcome:
    status: str
    message: str
    result: Optional[dict] = None
    preflight: Optional[dict] = None
    launcher_pid: Optional[int] = None
    worker_pid: Optional[int] = None
    worker_in_job: Optional[bool] = None
    # Kernel-measured, all job processes together.  Windows also counts a commit request the limit REFUSED, so a peak
    # above the limit means the limit was reached (memory_limit_reached), not that this much was in use.
    peak_job_memory_bytes: Optional[int] = None
    memory_limit_reached: Optional[bool] = None
    peak_worker_commit_bytes: Optional[int] = None       # reported by the worker for itself
    available_memory_before_bytes: Optional[int] = None
    min_available_memory_bytes: Optional[int] = None
    active_processes_after: Optional[int] = None
    runtime_seconds: float = 0.0
    stages: list = field(default_factory=list)
    label: str = RESULT_LABEL


class RunnerRefused(RuntimeError):
    pass


# ------------------------------------------------------------------------------------------------ Win32


class _MEMSTAT(ctypes.Structure):
    _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


class _BASIC_LIMIT(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in ("ReadOperationCount", "WriteOperationCount",
                                                        "OtherOperationCount", "ReadTransferCount",
                                                        "WriteTransferCount", "OtherTransferCount")]


class _EXTENDED_LIMIT(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BASIC_LIMIT), ("IoInfo", _IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


class _ACCOUNTING(ctypes.Structure):
    _fields_ = [("TotalUserTime", ctypes.c_int64), ("TotalKernelTime", ctypes.c_int64),
                ("ThisPeriodTotalUserTime", ctypes.c_int64), ("ThisPeriodTotalKernelTime", ctypes.c_int64),
                ("TotalPageFaultCount", wintypes.DWORD), ("TotalProcesses", wintypes.DWORD),
                ("ActiveProcesses", wintypes.DWORD), ("TotalTerminatedProcesses", wintypes.DWORD)]


class _PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t)]


JOB_EXTENDED_LIMIT_INFORMATION = 9
JOB_BASIC_ACCOUNTING_INFORMATION = 1
LIMIT_JOB_MEMORY = 0x200
LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x400
LIMIT_KILL_ON_JOB_CLOSE = 0x2000
CREATE_SUSPENDED = 0x4
CREATE_NO_WINDOW = 0x08000000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259


def _kernel32():
    if os.name != "nt":
        raise RunnerRefused("Supervised solid solves need Windows job objects; this platform is not supported.")
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateJobObjectW.restype = wintypes.HANDLE
    k.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    k.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
    k.QueryInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                            ctypes.c_void_p)
    k.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    k.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    k.IsProcessInJob.argtypes = (wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL))
    k.OpenProcess.restype = wintypes.HANDLE
    k.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    k.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    k.CloseHandle.argtypes = (wintypes.HANDLE,)
    k.GetCurrentProcess.restype = wintypes.HANDLE
    k.K32GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD)
    k.GlobalMemoryStatusEx.argtypes = (ctypes.c_void_p,)
    return k


def available_memory_bytes() -> int:
    k = _kernel32()
    s = _MEMSTAT()
    s.dwLength = ctypes.sizeof(s)
    if not k.GlobalMemoryStatusEx(ctypes.byref(s)):
        raise RunnerRefused("System memory status is unavailable.")
    return int(s.ullAvailPhys)


def own_peak_commit_bytes() -> int:
    """Peak private commit of the calling process (Win32 PeakPagefileUsage)."""
    k = _kernel32()
    c = _PMC()
    c.cb = ctypes.sizeof(c)
    if not k.K32GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(c), c.cb):
        return -1
    return int(c.PeakPagefileUsage)


def process_alive(pid: int) -> bool:
    k = _kernel32()
    handle = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        return bool(k.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == STILL_ACTIVE
    finally:
        k.CloseHandle(handle)


class _Job:
    def __init__(self, memory_limit: int):
        self.k = _kernel32()
        self.handle = self.k.CreateJobObjectW(None, None)
        if not self.handle:
            raise RunnerRefused(f"No job object could be created (error {ctypes.get_last_error()}).")
        info = _EXTENDED_LIMIT()
        info.BasicLimitInformation.LimitFlags = LIMIT_JOB_MEMORY | LIMIT_KILL_ON_JOB_CLOSE | LIMIT_DIE_ON_UNHANDLED_EXCEPTION
        info.JobMemoryLimit = int(memory_limit)
        if not self.k.SetInformationJobObject(self.handle, JOB_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info),
                                              ctypes.sizeof(info)):
            self.close()
            raise RunnerRefused(f"The job memory limit could not be set (error {ctypes.get_last_error()}).")

    def assign(self, process_handle) -> None:
        if not self.k.AssignProcessToJobObject(self.handle, wintypes.HANDLE(int(process_handle))):
            raise RunnerRefused(f"The worker could not be placed under supervision (error {ctypes.get_last_error()}).")

    def contains(self, pid: int) -> bool:
        handle = self.k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return False
        try:
            result = wintypes.BOOL()
            return bool(self.k.IsProcessInJob(handle, self.handle, ctypes.byref(result))) and bool(result.value)
        finally:
            self.k.CloseHandle(handle)

    def peak_memory(self) -> int:
        info = _EXTENDED_LIMIT()
        self.k.QueryInformationJobObject(self.handle, JOB_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info),
                                         ctypes.sizeof(info), None)
        return int(info.PeakJobMemoryUsed)

    def active_processes(self) -> int:
        info = _ACCOUNTING()
        self.k.QueryInformationJobObject(self.handle, JOB_BASIC_ACCOUNTING_INFORMATION, ctypes.byref(info),
                                         ctypes.sizeof(info), None)
        return int(info.ActiveProcesses)

    def terminate(self) -> None:
        if self.handle:
            self.k.TerminateJobObject(self.handle, 1)

    def close(self) -> None:
        if self.handle:
            self.k.CloseHandle(self.handle)  # KILL_ON_JOB_CLOSE: nothing in the job survives
            self.handle = None


def _resume(process) -> None:
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtResumeProcess.argtypes = (wintypes.HANDLE,)
    status = ntdll.NtResumeProcess(wintypes.HANDLE(int(process._handle)))
    if status != 0:
        raise RunnerRefused(f"The supervised worker could not be resumed (status {status}).")


# ------------------------------------------------------------------------------------------------ parent side


def sha256_of(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def preflight(request: ForwardRequest, limits: RunnerLimits = RunnerLimits()) -> dict:
    """Identity, solver preflight and the memory decision, in this process. Raises RunnerRefused."""
    from services import solid_c3d8i_model as sm
    from services import solid_c3d8i_solver as ss

    if sha256_of(request.inp_path) != request.inp_sha256:
        raise RunnerRefused("The INP changed since it was checked; check and confirm it again.")
    model = sm.load_solid_inp(request.inp_path)
    pre = ss.SolidForwardModel(model, ss.ResourceLimits(max_memory_bytes=limits.max_job_memory_bytes)).preflight(
        request.elastic_modes, request.guard_modes)
    available = available_memory_bytes()
    reasons = list(pre.reasons)
    if pre.peak_bytes_estimate > available - limits.reserve_free_memory_bytes:
        reasons.append(f"Estimated peak {pre.peak_bytes_estimate / GiB:.2f} GiB does not fit in the available "
                       f"{available / GiB:.2f} GiB while keeping {limits.reserve_free_memory_bytes / GiB:.2f} GiB free.")
    info = {k: (list(v) if isinstance(v, tuple) else v) for k, v in pre.__dict__.items()}
    info.update(available_memory_bytes=available, job_memory_limit_bytes=limits.max_job_memory_bytes,
                reserve_free_memory_bytes=limits.reserve_free_memory_bytes, decision_reasons=reasons,
                decision="REFUSE" if reasons else "ALLOW")
    return info


def _child_argv() -> list:
    # -m from src: sys.path[0] is src, never the services folder itself
    return [sys.executable, "-m", "services.solid_forward_runner", "--child"]


def run(request: ForwardRequest, limits: RunnerLimits = RunnerLimits(), *,
        progress: Optional[Callable[[dict], None]] = None, cancel: Optional[threading.Event] = None,
        child_argv: Optional[list] = None, skip_preflight: bool = False) -> RunnerOutcome:
    """Run ONE supervised solve.  ``child_argv`` and ``skip_preflight`` exist only for supervision tests."""
    started = time.perf_counter()
    outcome = RunnerOutcome(status=FAILED, message="")
    cancel = cancel or threading.Event()

    def note(event: dict) -> None:
        outcome.stages.append([round(time.perf_counter() - started, 3), event.get("stage") or event.get("event")])
        if progress:
            progress(event)

    try:
        outcome.available_memory_before_bytes = available_memory_bytes()
        if not skip_preflight:
            note({"event": "progress", "stage": "preflight"})
            outcome.preflight = preflight(request, limits)
            if outcome.preflight["decision"] != "ALLOW":
                outcome.status, outcome.message = REFUSED, " ".join(outcome.preflight["decision_reasons"])
                return outcome
        if cancel.is_set():
            outcome.status, outcome.message = CANCELLED, "Cancelled before the worker started."
            return outcome
        job = _Job(limits.max_job_memory_bytes)
    except RunnerRefused as error:
        outcome.status, outcome.message = REFUSED, str(error)
        return outcome
    except Exception as error:  # noqa: BLE001  (import or preflight failure is a refusal, not a crash)
        outcome.status, outcome.message = REFUSED, f"{type(error).__name__}: {error}"
        return outcome

    env = dict(os.environ)
    env.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", PYTHONUNBUFFERED="1")
    src = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    events: "queue.Queue" = queue.Queue()
    process = None
    try:
        process = subprocess.Popen(child_argv or _child_argv(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, env=env, cwd=src,
                                   creationflags=CREATE_SUSPENDED | CREATE_NO_WINDOW)
        outcome.launcher_pid = process.pid
        try:
            job.assign(process._handle)
        except RunnerRefused:
            process.kill()
            raise
        _resume(process)
        spawned = time.perf_counter()
        spec = {"inp_path": request.inp_path, "inp_sha256": request.inp_sha256, "elastic_modes": request.elastic_modes,
                "guard_modes": request.guard_modes, "max_memory_bytes": limits.max_job_memory_bytes,
                "max_seconds": limits.max_seconds}
        process.stdin.write((json.dumps(spec) + "\n").encode("utf-8"))
        process.stdin.close()

        def reader() -> None:
            for raw in process.stdout:
                try:
                    events.put(json.loads(raw.decode("utf-8")))
                except (ValueError, UnicodeDecodeError):
                    events.put({"event": "noise"})
            events.put({"event": "eof"})

        reader_thread = threading.Thread(target=reader, name="solid-runner-reader", daemon=True)
        reader_thread.start()
        last_event = time.perf_counter()
        outcome.min_available_memory_bytes = outcome.available_memory_before_bytes
        final = None
        while True:
            try:
                event = events.get(timeout=0.25)
            except queue.Empty:
                event = None
            now = time.perf_counter()
            available = available_memory_bytes()
            outcome.min_available_memory_bytes = min(outcome.min_available_memory_bytes, available)
            stop = None
            if cancel.is_set():
                stop = (CANCELLED, "Cancelled: the worker and its processes were terminated.")
            elif outcome.worker_pid is None and now - spawned > limits.handshake_seconds:
                stop = (REFUSED, "The worker process identity could not be established; nothing was solved.")
            elif now - started > limits.max_seconds:
                stop = (KILLED, f"Wall-clock limit {limits.max_seconds:g} s reached.")
            elif now - last_event > limits.max_silence_seconds:
                stop = (KILLED, f"No progress for {limits.max_silence_seconds:g} s.")
            elif available < limits.reserve_free_memory_bytes:
                stop = (KILLED, f"System available memory fell to {available / GiB:.2f} GiB.")
            if stop is None and event is not None:
                last_event = now
                kind = event.get("event")
                if kind == "hello":
                    pid = int(event.get("pid", -1))
                    if outcome.worker_pid is not None:
                        stop = (REFUSED, "The worker identified itself twice.")
                    elif not job.contains(pid):
                        outcome.worker_pid, outcome.worker_in_job = pid, False
                        stop = (REFUSED, f"Reported worker PID {pid} is not under supervision; the run was stopped.")
                    else:
                        outcome.worker_pid, outcome.worker_in_job = pid, True
                        note({"event": "progress", "stage": "worker verified", "pid": pid})
                elif outcome.worker_pid is None and kind != "eof":
                    stop = (REFUSED, "The worker sent output before identifying itself; the run was stopped.")
                elif kind == "progress":
                    event["peak_job_memory_bytes"] = job.peak_memory()
                    event["available_memory_bytes"] = available
                    note(event)
                elif kind in ("result", "error"):
                    final = event
                elif kind == "eof":
                    break
            if stop is not None:
                job.terminate()
                outcome.status, outcome.message = stop
                break
        if process.poll() is None:
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                job.terminate()
                process.wait(timeout=30)
        outcome.peak_job_memory_bytes = job.peak_memory()
        outcome.memory_limit_reached = outcome.peak_job_memory_bytes > limits.max_job_memory_bytes
        if outcome.status == FAILED and final is not None:  # the loop ended at EOF
            if final.get("event") == "result" and outcome.worker_in_job:
                outcome.status, outcome.result = SOLVED, final["result"]
                outcome.peak_worker_commit_bytes = final.get("peak_worker_commit_bytes")
                outcome.message = "One offline FE solve completed."
            elif final.get("event") == "result":
                outcome.status, outcome.message = REFUSED, "A result arrived from an unverified worker; it is discarded."
            else:
                outcome.message = f"{final.get('kind', 'error')}: {final.get('message', '')}"
                outcome.peak_worker_commit_bytes = final.get("peak_worker_commit_bytes")
                outcome.result = final.get("diagnostics")
        elif outcome.status == FAILED and not outcome.message:
            outcome.message = (f"The worker ended without a result (exit code {process.returncode}); "
                               f"the job memory limit is {limits.max_job_memory_bytes / GiB:.2f} GiB.")
    except RunnerRefused as error:
        outcome.status, outcome.message = REFUSED, str(error)
    finally:
        if outcome.status != SOLVED:
            job.terminate()
        try:
            deadline = time.perf_counter() + 10.0
            while job.active_processes() and time.perf_counter() < deadline:
                time.sleep(0.05)
            outcome.active_processes_after = job.active_processes()
        except Exception:  # noqa: BLE001
            outcome.active_processes_after = None
        job.close()
        if process is not None:
            if process.poll() is None:
                process.kill()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                pass
            if process.stdout is not None:
                if "reader_thread" in locals():
                    reader_thread.join(timeout=10)
                process.stdout.close()
        outcome.runtime_seconds = time.perf_counter() - started
    return outcome


# ------------------------------------------------------------------------------------------------ child side


def _emit(event: dict) -> None:
    sys.stdout.write(json.dumps(event, default=float) + "\n")
    sys.stdout.flush()


def _child_main() -> int:
    _emit({"event": "hello", "pid": os.getpid()})
    spec = json.loads(sys.stdin.readline())
    try:
        import numpy as np
        from services import solid_c3d8i_model as sm
        from services import solid_c3d8i_solver as ss

        if sha256_of(spec["inp_path"]) != spec["inp_sha256"]:
            raise RunnerRefused("The INP changed after confirmation; nothing was solved.")
        _emit({"event": "progress", "stage": "import"})
        model = sm.load_solid_inp(spec["inp_path"])
        limits = ss.ResourceLimits(max_memory_bytes=int(spec["max_memory_bytes"]), max_seconds=float(spec["max_seconds"]))
        forward = ss.SolidForwardModel(model, limits)

        def progress(stage, done, total):
            _emit({"event": "progress", "stage": stage, "done": done, "total": total})

        try:
            result = forward.solve(int(spec["elastic_modes"]), guard_modes=int(spec["guard_modes"]), progress=progress)
        except ss.RigidBodyClassificationError as exc:
            d = exc.diagnostics
            _emit({"event": "error", "kind": "RIGID_BODY_CLASSIFICATION_FAILED", "message": str(exc),
                   "peak_worker_commit_bytes": own_peak_commit_bytes(),
                   "diagnostics": {"rigid_passed": False, "c2e0": d.c2e0_status, "reasons": list(d.failure_reasons),
                                   "rigid_content": d.rigid_content.tolist(),
                                   "all_eigenvalues": exc.all_eigenvalues.tolist()}})
            return 3
        r = result.rigid
        m = result.material
        _emit({"event": "result", "peak_worker_commit_bytes": own_peak_commit_bytes(), "result": {
            "frequencies_hz": result.frequencies_hz.tolist(), "guard_frequencies_hz": result.guard_frequencies_hz.tolist(),
            "relative_spacing": result.relative_spacing.tolist(),
            "max_backward_error": float(np.max(result.backward_errors)),
            "mass_orthogonality_error": result.mass_orthogonality_error, "shift": result.shift,
            "shift_source": result.shift_source, "operator_applications": result.operator_applications,
            "factor_nonzeros": result.factor_nonzeros, "seconds": result.seconds,
            "material": {k: getattr(m, k) for k in ("e1", "e2", "e3", "nu12", "nu13", "nu23", "g12", "g13", "g23")},
            "density": result.density, "dof_count": model.dof_count, "element_count": len(model.element_labels),
            "rigid": {"passed": r.passed, "c2e0": r.c2e0_status, "ratio": r.rigid_to_first_elastic_ratio,
                      "eigenvalues": r.eigenvalues.tolist(), "min_span_cosine": float(np.min(r.span_cosines)),
                      "max_rigid_content_of_elastic": r.max_rigid_content_of_elastic_modes},
            "formulation": result.formulation, "abaqus_equivalence": result.abaqus_equivalence}})
        return 0
    except MemoryError:
        _emit({"event": "error", "kind": "MEMORY_LIMIT", "message": "The job memory limit stopped an allocation.",
               "peak_worker_commit_bytes": own_peak_commit_bytes()})
        return 2
    except Exception as error:  # noqa: BLE001
        _emit({"event": "error", "kind": type(error).__name__, "message": str(error),
               "peak_worker_commit_bytes": own_peak_commit_bytes()})
        return 1


if __name__ == "__main__" and "--child" in sys.argv:
    sys.exit(_child_main())


__all__ = ["CANCELLED", "FAILED", "ForwardRequest", "KILLED", "REFUSED", "RESULT_LABEL", "RunnerLimits", "RunnerOutcome",
           "RunnerRefused", "SOLVED", "available_memory_bytes", "preflight", "process_alive", "run", "sha256_of"]
