"""Process trees owned by one quick-calibration session: track, terminate, and confirm termination.

An Abaqus solve is started as a launcher (``cmd.exe`` → ``abaqus`` driver → solver executables). Only processes this
session started are ever terminated: the launcher, plus every process that was observed as its descendant while it
ran. Descendants are recorded from periodic process-table snapshots with their creation time, so a child whose
parent has already exited is still known, and a reused PID is never mistaken for an owned process.

``OwnedProcessTree.terminate`` returns True only after every owned process is confirmed gone; anything it cannot
confirm is reported, never assumed.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import signal
import subprocess
import time
from typing import Callable, Iterable, Mapping, Optional

ProcessTable = Callable[[], Mapping[int, int]]  # pid -> parent pid
CreationTime = Callable[[int], Optional[tuple]]
Killer = Callable[[int], None]


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    created: Optional[tuple]  # creation time (Windows FILETIME or Linux start ticks); None if unavailable


def creation_time(pid: int) -> Optional[tuple]:
    """Creation time of a live process, or None (absent, a zombie, or not determinable)."""
    if os.name == "nt":
        from abaqus_bridge import _process_creation_time  # the application's Windows FILETIME query

        value = _process_creation_time(pid)
        return None if value is None else tuple(value)
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="ascii", errors="replace")
    except OSError:
        return None
    fields = text[text.rfind(")") + 2:].split()
    if not fields or fields[0] in ("Z", "X"):  # a zombie has exited
        return None
    return (int(fields[19]),)  # starttime (field 22 of /proc/<pid>/stat)


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


def kill_process(pid: int) -> None:
    """Forced termination of one owned PID (and, on Windows, its current descendants)."""
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=30, check=False)
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


class OwnedProcessTree:
    """The launcher started by this session and every descendant observed while it ran."""

    def __init__(self, process: subprocess.Popen, *, table: ProcessTable = process_table,
                 created: CreationTime = creation_time, kill: Killer = kill_process) -> None:
        self.process = process
        self._table, self._created, self._kill = table, created, kill
        self.members: dict[int, ProcessIdentity] = {process.pid: ProcessIdentity(process.pid, created(process.pid))}

    def refresh(self) -> None:
        """Record new descendants of any owned process (transitively; a child created before its recorded parent
        is a reused PID and is ignored)."""
        table = self._table()
        changed = True
        while changed:
            changed = False
            for pid, parent in table.items():
                if pid in self.members or parent not in self.members:
                    continue
                owner = self.members[parent]
                created = self._created(pid)
                if created is not None and owner.created is not None and created < owner.created:
                    continue
                self.members[pid] = ProcessIdentity(pid, created)
                changed = True

    def _is_alive(self, identity: ProcessIdentity) -> bool:
        if identity.pid == self.process.pid:
            return self.process.poll() is None
        current = self._created(identity.pid)
        if current is None:
            return False if identity.created is not None else _pid_visible(identity.pid, self._table)
        return identity.created is None or current == identity.created

    def alive(self) -> list[ProcessIdentity]:
        return [identity for identity in self.members.values() if self._is_alive(identity)]

    def terminate(self, timeout_seconds: float = 30.0, poll_seconds: float = 0.2) -> bool:
        """Kill every live owned process and confirm that none remains; True only when confirmed."""
        deadline = time.monotonic() + timeout_seconds
        attempts = 0
        while True:
            self.refresh()
            living = self.alive()
            if not living:
                self._reap()
                return True
            if time.monotonic() >= deadline:
                return False
            if attempts < 3:  # forced termination, retried while processes remain
                for identity in living:
                    self._kill(identity.pid)
                attempts += 1
            time.sleep(poll_seconds)
            self._reap()

    def _reap(self) -> None:
        try:
            self.process.poll()
        except OSError:
            pass

    def describe(self, identities: Optional[Iterable[ProcessIdentity]] = None) -> str:
        identities = list(self.alive() if identities is None else identities)
        return ", ".join(f"PID {identity.pid}" for identity in identities) or "none"


def _pid_visible(pid: int, table: ProcessTable) -> bool:
    return pid in table()
