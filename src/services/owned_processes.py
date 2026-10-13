"""Process trees owned by one quick-calibration session: track, terminate, and confirm termination.

An Abaqus solve is started as a launcher (``cmd.exe`` → ``abaqus`` driver → solver executables). Only processes this
session started are ever terminated: the launcher, and every process observed as a child of an owned process while
that parent was still the recorded process (same PID and creation time) and created after it. Every kill re-checks
the identity on the process itself (Windows: the same handle; Linux: a pidfd), so a reused PID is never killed.

Termination is confirmed only when every owned process is known to be gone. A process whose state or identity cannot
be determined is never killed and never counted as gone: ``terminate`` then returns False and ``unconfirmed`` reports
it (``None`` when the tracker cannot establish identities at all).
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import signal
import subprocess
import time
from typing import Callable, Mapping, Optional

ALIVE = "ALIVE"
GONE = "GONE"
UNKNOWN = "UNKNOWN"  # the process may exist, but its state or identity cannot be read

ProcessTable = Callable[[], Mapping[int, int]]  # pid -> parent pid
StateFunction = Callable[[int], tuple]  # pid -> (ALIVE | GONE | UNKNOWN, creation identity or None)
Killer = Callable[["ProcessIdentity"], None]


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    created: Optional[tuple]  # creation time (Windows FILETIME or Linux start ticks); None if unknown


# ----------------------------------------------------------------------------- platform queries

def process_state(pid: int) -> tuple[str, Optional[tuple]]:
    """(ALIVE, creation identity), (GONE, None) or (UNKNOWN, None) for one PID."""
    return _windows_state(pid) if os.name == "nt" else _posix_state(pid)


def creation_time(pid: int) -> Optional[tuple]:
    """Creation identity of a live process, or None (gone or unknown)."""
    status, created = process_state(pid)
    return created if status == ALIVE else None


def _posix_state(pid: int) -> tuple[str, Optional[tuple]]:
    if not Path("/proc/self/stat").exists():
        return UNKNOWN, None  # no /proc: identities cannot be established
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="ascii", errors="replace")
    except (FileNotFoundError, ProcessLookupError):
        return GONE, None
    except OSError:
        return UNKNOWN, None
    fields = text[text.rfind(")") + 2:].split()
    if not fields:
        return UNKNOWN, None
    if fields[0] in ("Z", "X"):  # exited, not yet reaped
        return GONE, None
    return ALIVE, (int(fields[19]),)  # starttime (field 22 of /proc/<pid>/stat)


def _kernel32():
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    return kernel32


def _windows_handle_state(kernel32, handle) -> tuple[str, Optional[tuple]]:
    import ctypes
    from ctypes import wintypes

    code = wintypes.DWORD()
    if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
        return UNKNOWN, None
    if code.value != 259:  # not STILL_ACTIVE: exited (a handle may keep the object)
        return GONE, None
    times = [wintypes.FILETIME() for _ in range(4)]
    if not kernel32.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
        return UNKNOWN, None
    return ALIVE, (int(times[0].dwLowDateTime), int(times[0].dwHighDateTime))


def _windows_state(pid: int) -> tuple[str, Optional[tuple]]:
    import ctypes

    try:
        kernel32 = _kernel32()
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return (GONE if ctypes.get_last_error() == 87 else UNKNOWN), None  # 87: no such process
        try:
            return _windows_handle_state(kernel32, handle)
        finally:
            kernel32.CloseHandle(handle)
    except (OSError, AttributeError):
        return UNKNOWN, None


def kill_verified(identity: ProcessIdentity) -> None:
    """Kill exactly this process: its identity is re-checked on the process object that receives the kill."""
    if identity.created is None:
        return  # ownership cannot be established: never killed
    if os.name == "nt":
        try:
            kernel32 = _kernel32()
            handle = kernel32.OpenProcess(0x0001 | 0x1000, False, identity.pid)  # TERMINATE | QUERY_LIMITED
            if not handle:
                return
            try:
                status, created = _windows_handle_state(kernel32, handle)
                if status == ALIVE and created == identity.created:
                    kernel32.TerminateProcess(handle, 1)
            finally:
                kernel32.CloseHandle(handle)
        except (OSError, AttributeError):
            pass
        return
    pidfd_open = getattr(os, "pidfd_open", None)
    if pidfd_open is not None:
        try:
            descriptor = pidfd_open(identity.pid)
        except OSError:
            return
        try:  # the pidfd pins the process: a PID reused after this point cannot receive the signal
            status, created = _posix_state(identity.pid)
            if status == ALIVE and created == identity.created:
                signal.pidfd_send_signal(descriptor, signal.SIGKILL)
        except OSError:
            pass
        finally:
            os.close(descriptor)
        return
    status, created = _posix_state(identity.pid)
    if status == ALIVE and created == identity.created:
        try:
            os.kill(identity.pid, signal.SIGKILL)
        except OSError:
            pass


def process_table() -> dict[int, int]:
    """pid -> parent pid of every visible process (empty when it cannot be read)."""
    if os.name == "nt":
        return _windows_process_table()
    try:
        output = subprocess.run(["ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True, timeout=10,
                                check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    table = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            table[int(parts[0])] = int(parts[1])
    return table


def _windows_process_table() -> dict[int, int]:
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                        ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
                        ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                        ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                        ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
        if snapshot in (None, wintypes.HANDLE(-1).value):
            return {}
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            table = {}
            ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
            while ok:
                table[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
                ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
            return table
        finally:
            kernel32.CloseHandle(snapshot)
    except (OSError, AttributeError, ValueError):
        return {}


# ----------------------------------------------------------------------------- the owned tree

class OwnedProcessTree:
    """The launcher started by this session and every descendant whose ownership was established while it ran."""

    def __init__(self, process: subprocess.Popen, *, table: ProcessTable = process_table,
                 state: StateFunction = process_state, kill: Killer = kill_verified) -> None:
        self.process = process
        self._table, self._state, self._kill = table, state, kill
        status, created = state(process.pid)
        self.root = ProcessIdentity(process.pid, created if status == ALIVE else None)
        self.members: dict[int, ProcessIdentity] = {process.pid: self.root}
        self.unverified: dict[int, int] = {}  # pid -> owned parent pid: a child whose identity cannot be read

    @property
    def identity_available(self) -> bool:
        """Descendants can only be attributed when the launcher's own identity is known."""
        return self.root.created is not None

    def _is_recorded_process(self, pid: int) -> bool:
        """The owned process at ``pid`` is still the one recorded (same PID and creation identity)."""
        identity = self.members.get(pid)
        if identity is None or identity.created is None:
            return False
        if pid == self.process.pid and self.process.poll() is not None:
            return False
        status, created = self._state(pid)
        return status == ALIVE and created == identity.created

    def refresh(self) -> None:
        """Record children of owned processes whose ownership is established; never guess."""
        table = self._table()
        changed = True
        while changed:
            changed = False
            for pid, parent in table.items():
                if pid in self.members or parent not in self.members or not self._is_recorded_process(parent):
                    continue
                status, created = self._state(pid)
                owner = self.members[parent]
                if status == ALIVE and created is not None:
                    if created < owner.created:
                        continue  # older than the recorded parent: a stale parent link, not ours
                    self.members[pid] = ProcessIdentity(pid, created)
                    self.unverified.pop(pid, None)
                    changed = True
                elif status == UNKNOWN or status == ALIVE:
                    self.unverified[pid] = parent  # possibly ours, identity unreadable: never killed or confirmed
        for pid, parent in list(self.unverified.items()):
            if table.get(pid) != parent or self._state(pid)[0] == GONE:
                del self.unverified[pid]

    def _member_status(self, identity: ProcessIdentity) -> str:
        if identity.pid == self.process.pid:
            return ALIVE if self.process.poll() is None else GONE
        status, created = self._state(identity.pid)
        if status == ALIVE and created != identity.created:
            return GONE  # the PID now belongs to another process; the owned one has exited
        return status

    def remaining(self) -> list[ProcessIdentity]:
        """Owned processes not known to be gone, plus children whose identity could not be established."""
        left = [identity for identity in self.members.values() if self._member_status(identity) != GONE]
        return left + [ProcessIdentity(pid, None) for pid in self.unverified]

    def unconfirmed(self) -> Optional[list[ProcessIdentity]]:
        """What may still run; ``None`` when the tracker cannot establish identities (never 'all stopped')."""
        if not self.identity_available:
            return None
        self.refresh()
        return self.remaining()

    def terminate(self, timeout_seconds: float = 30.0, poll_seconds: float = 0.2) -> bool:
        """Kill every owned process and confirm that none remains; True only when confirmed."""
        deadline = time.monotonic() + timeout_seconds
        attempts = 0
        while True:
            self.refresh()
            left = self.remaining()
            if self.identity_available and not left:
                self._reap()
                return True
            if not self.identity_available and self.process.poll() is not None:
                return False  # the launcher is gone, but its descendants cannot be confirmed
            if time.monotonic() >= deadline:
                return False
            if attempts < 3:
                for identity in left:
                    if identity.pid == self.process.pid:
                        self._kill_root()
                    elif identity.created is not None:
                        self._kill(identity)
                attempts += 1
            time.sleep(poll_seconds)
            self._reap()

    def _kill_root(self) -> None:
        try:
            self.process.kill()  # our own process object: it cannot refer to a reused PID
        except OSError:
            pass

    def _reap(self) -> None:
        try:
            self.process.poll()
        except OSError:
            pass

    def describe(self, identities=None) -> str:
        if identities is None:
            if not self.identity_available:
                return "unknown (the launcher's identity could not be read; descendants cannot be attributed)"
            identities = self.remaining()
        return ", ".join(f"PID {i.pid}" + ("" if i.created is not None or i.pid == self.process.pid
                                             else " (identity unreadable)") for i in identities) or "none"
