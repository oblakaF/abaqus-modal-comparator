from __future__ import annotations

import csv
from decimal import Decimal
import json
import math
import os
import re
import shlex
import signal
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

import numpy as np

from modal_core import ModalDataset, ModeShape


class AbaqusExtractionError(RuntimeError):
    pass


class AnalysisCancelled(RuntimeError):
    """Raised when the user cancels work owned by this application."""


def new_owner_token() -> str:
    """A per-run ownership token the extractor echoes back in its registration."""
    return uuid.uuid4().hex


def _process_creation_time(pid: int) -> Optional[List[int]]:
    """Best-effort Windows FILETIME creation-time query for PID-reuse safety.

    Returns None off Windows, if the PID does not exist, or the query fails
    for any other reason -- callers must treat that as "cannot confirm", not
    as "process is absent".
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None
        try:
            creation = wintypes.FILETIME()
            exit_t = wintypes.FILETIME()
            kernel_t = wintypes.FILETIME()
            user_t = wintypes.FILETIME()
            ok = kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_t),
                ctypes.byref(kernel_t),
                ctypes.byref(user_t),
            )
            if not ok:
                return None
            return [int(creation.dwLowDateTime), int(creation.dwHighDateTime)]
        finally:
            kernel32.CloseHandle(handle)
    except OSError:
        return None


def read_process_registration(registration_path: Path) -> Optional[Dict[str, Any]]:
    """Read and structurally validate a worker self-registration record."""
    try:
        with Path(registration_path).open("r", encoding="utf-8") as stream:
            record = json.load(stream)
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict):
        return None
    if "token" not in record or "pid" not in record:
        return None
    try:
        record["pid"] = int(record["pid"])
    except (TypeError, ValueError):
        return None
    return record


def _registered_worker_is_confirmable(pid: int, recorded_creation_time) -> Optional[bool]:
    """Cross-check a registered PID against its live creation time.

    Returns True if the live process's creation time matches the one the
    worker reported about itself (strong confirmation), False if a live
    process exists at that PID but with a *different* creation time (i.e.
    the PID was reused by an unrelated process -- never kill it), or None if
    no creation-time evidence is available on either side (existence alone,
    checked by the caller, is the fallback).
    """
    live_creation_time = _process_creation_time(pid)
    if live_creation_time is None or recorded_creation_time is None:
        return None
    return list(live_creation_time) == list(recorded_creation_time)


def _pid_exists(pid: int) -> bool:
    if os.name == "nt":
        return _process_creation_time(pid) is not None or _windows_pid_in_tasklist(pid)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _windows_pid_in_tasklist(pid: int) -> bool:
    try:
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            check=False,
            timeout=5,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return str(pid) in (completed.stdout or "")


def _validate_registered_owner(
    registration_path: Path, expected_token: str
) -> Optional[Dict[str, Any]]:
    """Return the registration record only if token, PID, and (if available)
    creation time all check out as still belonging to our launched run."""
    record = read_process_registration(registration_path)
    if record is None or record.get("token") != expected_token:
        return None
    pid = record["pid"]
    recorded_creation_time = record.get("creation_time")
    confirmable = _registered_worker_is_confirmable(pid, recorded_creation_time)
    if confirmable is False:
        # A live process exists at this PID but it is provably NOT the
        # process that wrote this registration record (PID reused). Never
        # treat it as ours.
        return None
    if confirmable is None and not _pid_exists(pid):
        return None
    return record


def _terminate_pid_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
            timeout=10,
        )
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def stop_owned_extraction(
    process: Optional[subprocess.Popen],
    registration_path: Optional[Path],
    owner_token: Optional[str],
    first_timeout_seconds: float = 12.0,
    retry_timeout_seconds: float = 8.0,
) -> bool:
    """Terminate exactly the processes this run owns: the registered worker
    (validated by token + PID + creation-time cross-check, which survives it
    being reparented/detached away from the launcher) and the originally
    spawned launcher tree. Returns True only once every owned process that
    was confirmed alive is confirmed dead; never touches anything it cannot
    positively identify as ours.
    """
    worker_ok = True
    if registration_path is not None and owner_token is not None:
        record = _validate_registered_owner(Path(registration_path), owner_token)
        if record is not None:
            worker_pid = record["pid"]
            recorded_creation_time = record.get("creation_time")
            deadline = time.monotonic() + first_timeout_seconds
            _terminate_pid_tree(worker_pid)
            worker_ok = False
            while time.monotonic() < deadline:
                still_matches = _registered_worker_is_confirmable(
                    worker_pid, recorded_creation_time
                )
                if still_matches is False or (
                    still_matches is None and not _pid_exists(worker_pid)
                ):
                    worker_ok = True
                    break
                time.sleep(0.2)
            if not worker_ok:
                # One escalation retry against the same confirmed-owned PID.
                _terminate_pid_tree(worker_pid)
                deadline = time.monotonic() + retry_timeout_seconds
                while time.monotonic() < deadline:
                    still_matches = _registered_worker_is_confirmable(
                        worker_pid, recorded_creation_time
                    )
                    if still_matches is False or (
                        still_matches is None and not _pid_exists(worker_pid)
                    ):
                        worker_ok = True
                        break
                    time.sleep(0.2)

    launcher_ok = stop_owned_process_and_wait(
        process, first_timeout_seconds=first_timeout_seconds, retry_timeout_seconds=retry_timeout_seconds
    )
    return worker_ok and launcher_ok


def extraction_range_notice(manifest: Mapping[str, Any]) -> Optional[str]:
    """Describe a requested modal range clipped by available extraction frames."""
    try:
        requested_start = int(manifest["start_mode"])
        requested_end = int(manifest["end_mode"])
        extracted = sorted({int(item["mode"]) for item in manifest.get("modes", ())})
    except (KeyError, TypeError, ValueError):
        return None
    if not extracted:
        return None
    effective_start, effective_end = extracted[0], extracted[-1]
    contiguous = extracted == list(range(effective_start, effective_end + 1))
    if (
        contiguous
        and effective_start == requested_start
        and effective_end == requested_end
    ):
        return None
    effective = (
        f"{effective_start}-{effective_end}"
        if contiguous
        else ", ".join(str(mode) for mode in extracted)
    )
    return (
        f"Requested Abaqus modes {requested_start}-{requested_end}; available extraction "
        f"frames yielded modes {effective}. Using modes {effective}."
    )


def cancel_owned_process(process: Optional[subprocess.Popen]) -> bool:
    """Terminate exactly the process tree started by this application.

    Abaqus launchers commonly create a ``cmd.exe`` and one or more Python/solver
    children.  On Windows, terminating only the launcher can orphan those
    children, so taskkill is scoped to the recorded PID and its descendants.
    """
    if process is None or process.poll() is not None:
        return False
    try:
        if os.name == "nt":
            completed = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                check=False,
                timeout=10,
            )
            if completed.returncode != 0 and process.poll() is None:
                process.terminate()
        else:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            except (AttributeError, ProcessLookupError):
                process.terminate()
        return True
    except (OSError, subprocess.SubprocessError):
        try:
            process.terminate()
            return True
        except OSError:
            return False


def stop_owned_process_and_wait(
    process: Optional[subprocess.Popen],
    first_timeout_seconds: float = 10.0,
    retry_timeout_seconds: float = 5.0,
) -> bool:
    """Request scoped termination and confirm that the owned process exited."""
    if process is None or process.poll() is not None:
        return True
    cancel_owned_process(process)
    try:
        process.wait(timeout=first_timeout_seconds)
    except subprocess.TimeoutExpired:
        cancel_owned_process(process)
        try:
            process.wait(timeout=retry_timeout_seconds)
        except subprocess.TimeoutExpired:
            return False
    return process.poll() is not None


def _windows_command(executable: str, arguments: List[str]) -> List[str]:
    command_line = subprocess.list2cmdline([executable] + arguments)
    return ["cmd.exe", "/d", "/s", "/c", command_line]


def run_abaqus_extraction(
    odb_path: Path,
    output_directory: Path,
    abaqus_command: str = "abaqus",
    start_mode: int = 6,
    end_mode: int = 14,
    timeout_seconds: int = 3600,
    cancel_event=None,
    process_callback: Optional[Callable[[Optional[subprocess.Popen]], None]] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Path:
    odb_path = Path(odb_path).resolve()
    output_directory = Path(output_directory).resolve()
    output_directory.mkdir(parents=True, exist_ok=True)

    script_path = Path(__file__).resolve().parents[1] / "abaqus_scripts" / "extract_odb.py"
    if not script_path.exists():
        raise FileNotFoundError(f"Abaqus extraction script was not found: {script_path}")

    owner_token = new_owner_token()
    # Run-specific, not a shared/global path: lives inside this run's own
    # output directory, so concurrent runs in different directories never
    # collide and a stale record from a previous run in the same directory
    # is never misread as belonging to this run (token differs; overwritten
    # atomically by the new worker as soon as it starts).
    registration_path = output_directory / "process_registration.json"
    try:
        registration_path.unlink()
    except OSError:
        pass

    arguments = [
        "python",
        str(script_path),
        "--odb",
        str(odb_path),
        "--output",
        str(output_directory),
        "--start-mode",
        str(start_mode),
        "--end-mode",
        str(end_mode),
        "--owner-token",
        owner_token,
        "--registration-file",
        str(registration_path),
    ]
    executable = abaqus_command.strip() or "abaqus"
    command = (
        _windows_command(executable, arguments)
        if os.name == "nt"
        else shlex.split(executable) + arguments
    )

    log_path = output_directory / "abaqus_extraction.log"
    process: Optional[subprocess.Popen] = None
    started = time.monotonic()
    try:
        with log_path.open("w", encoding="utf-8") as log:
            log.write("COMMAND\n" + " ".join(command) + "\n\nOUTPUT\n")
            log.flush()
            popen_options = {
                "cwd": str(script_path.parent),
                "stdout": log,
                "stderr": subprocess.STDOUT,
                "text": True,
            }
            if os.name == "nt":
                popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_options["start_new_session"] = True
            if cancel_event is not None and cancel_event.is_set():
                raise AnalysisCancelled("Analysis stopped by user.")
            process = subprocess.Popen(command, **popen_options)
            if process_callback is not None:
                process_callback(process)
            log_tail_position = 0
            log_tail_partial = ""

            def _drain_progress() -> None:
                # Best-effort: the extraction script's stdout is captured to
                # log_path, so new "PROGRESS: ..." lines are surfaced to the
                # GUI as they appear instead of only after the whole process
                # exits. Any read failure (e.g. transient sharing violation
                # while the child is flushing) is silently skipped and
                # retried on the next poll tick.
                nonlocal log_tail_position, log_tail_partial
                if progress_callback is None:
                    return
                try:
                    with log_path.open("r", encoding="utf-8", errors="replace") as tail:
                        tail.seek(log_tail_position)
                        chunk = tail.read()
                        log_tail_position = tail.tell()
                except OSError:
                    return
                if not chunk:
                    return
                text = log_tail_partial + chunk
                lines = text.split("\n")
                log_tail_partial = lines.pop()
                for line in lines:
                    line = line.strip()
                    if line.startswith("PROGRESS:"):
                        progress_callback(line[len("PROGRESS:"):].strip())

            while process.poll() is None:
                if cancel_event is not None and cancel_event.is_set():
                    if not stop_owned_extraction(process, registration_path, owner_token):
                        raise AbaqusExtractionError(
                            "Cancellation could not be confirmed: the owned Abaqus worker "
                            "or launcher process did not stop within the timeout. Treat "
                            "the extraction as still running and check Task Manager before retrying."
                        )
                    raise AnalysisCancelled("Analysis stopped by user.")
                if time.monotonic() - started > timeout_seconds:
                    if not stop_owned_extraction(process, registration_path, owner_token):
                        raise AbaqusExtractionError(
                            "Abaqus extraction timed out, but the owned process did not stop."
                        )
                    raise AbaqusExtractionError(
                        f"Abaqus extraction exceeded {timeout_seconds // 60} minutes."
                    )
                _drain_progress()
                time.sleep(0.1)
            _drain_progress()
            return_code = int(process.returncode or 0)
    except FileNotFoundError as error:
        raise AbaqusExtractionError(
            "No valid Abaqus installation was found. Choose Detect again, "
            "Browse, or Advanced command."
        ) from error
    finally:
        if process_callback is not None and (
            process is None or process.poll() is not None
        ):
            process_callback(None)
        try:
            registration_path.unlink()
        except OSError:
            pass

    manifest_path = output_directory / "manifest.json"
    if return_code != 0 or not manifest_path.exists():
        try:
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
        except OSError:
            tail = "No output was produced."
        raise AbaqusExtractionError(
            "Abaqus could not extract the ODB results.\n\n"
            + tail
            + f"\n\nFull log: {log_path}"
        )
    return manifest_path


def _load_geometry_csv(file_path: Path) -> Dict[tuple, List[float]]:
    """Load the format-2 shared node-geometry file (written once per extraction)."""
    coordinates: Dict[tuple, List[float]] = {}
    with file_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"instance", "node_label", "x", "y", "z"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"Invalid Abaqus geometry file: {file_path.name}")
        for row in reader:
            key = (row["instance"], int(row["node_label"]))
            coordinates[key] = [float(row["x"]), float(row["y"]), float(row["z"])]
    return coordinates


def _load_mode_csv(
    file_path: Path,
    mode_number: int,
    frequency_hz: float,
    metadata: Dict[str, Any],
    geometry: Optional[Dict[tuple, List[float]]] = None,
) -> ModeShape:
    """Parse one per-mode CSV.

    ``geometry`` is None for format-1 files (legacy layout, each row also
    carries its own x/y/z) and a shared coordinate lookup for format-2 files
    (coordinates were written once to geometry.csv). Missing keys fall back to
    [0, 0, 0], mirroring the format-1 script's historical fallback so parsing
    behavior does not silently change if a node is ever absent from a frame.
    """
    node_ids: List[str] = []
    coordinates: List[List[float]] = []
    vectors: List[List[complex]] = []

    legacy = geometry is None
    required = {
        "instance",
        "node_label",
        "u1_real",
        "u2_real",
        "u3_real",
        "u1_imag",
        "u2_imag",
        "u3_imag",
    }
    if legacy:
        required = required | {"x", "y", "z"}

    with file_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"Invalid Abaqus mode file: {file_path.name}")

        for row in reader:
            instance_name = row["instance"]
            node_label = int(row["node_label"])
            node_ids.append(f"{instance_name}:{node_label}")
            if legacy:
                xyz = [float(row["x"]), float(row["y"]), float(row["z"])]
            else:
                xyz = geometry.get((instance_name, node_label), [0.0, 0.0, 0.0])
            coordinates.append(xyz)
            vectors.append(
                [
                    complex(float(row["u1_real"]), float(row["u1_imag"])),
                    complex(float(row["u2_real"]), float(row["u2_imag"])),
                    complex(float(row["u3_real"]), float(row["u3_imag"])),
                ]
            )

    if not node_ids:
        raise ValueError(f"No displacement values were found in {file_path.name}.")

    mode = ModeShape(
        number=mode_number,
        frequency_hz=frequency_hz,
        node_ids=np.asarray(node_ids, dtype=object),
        coordinates=np.asarray(coordinates, dtype=float),
        vectors=np.asarray(vectors, dtype=complex),
        metadata=metadata,
    )
    mode.measured_dofs = np.ones(mode.vectors.shape, dtype=bool)
    return mode


# The frame frequency of an Abaqus frequency step is reported with only 5-6 significant digits, while the EIGFREQ
# history output carries the solver's single-precision value. The history value replaces the frame value only when its
# mode identity is unambiguous and consistent; otherwise the frame value stays (fail-closed).
FREQUENCY_SOURCE_HISTORY = "EIGFREQ history"
FREQUENCY_SOURCE_FRAME = "frame frequency"
_FLOAT32_RESOLUTION = 2.0 ** -23  # one single-precision ulp, relative (ODB results are stored in single precision)
_EIGVAL_RELATIVE_TOLERANCE = 4 * 2.0 ** -24  # sqrt(EIGVAL)/2pi vs EIGFREQ: a few single-precision ulps


def _reported_precision(value: float) -> float:
    """Half a unit in the last reported decimal place of a frame frequency, never below float32 resolution."""
    exponent = Decimal(repr(float(value))).as_tuple().exponent
    half_unit = 0.5 * 10.0 ** exponent if isinstance(exponent, int) else 0.0
    return max(half_unit, abs(value) * _FLOAT32_RESOLUTION)


def _single_history(manifest: Mapping[str, Any], name: str):
    """(mode number -> value, None); (None, None) when absent; (None, reason) when unusable."""
    entries = [item for item in manifest.get("history") or () if isinstance(item, Mapping) and item.get("name") == name]
    if not entries:
        return None, None
    if len(entries) > 1:
        return None, f"{len(entries)} {name} histories (ambiguous)"
    values: Dict[int, float] = {}
    for pair in entries[0].get("data") or ():
        try:
            x, y = float(pair[0]), float(pair[1])
        except (TypeError, ValueError, IndexError):
            return None, f"{name} history has a malformed point"
        if not (math.isfinite(x) and math.isfinite(y) and x.is_integer() and x >= 1):
            return None, f"{name} history point {pair!r} is not (mode number, finite value)"
        if int(x) in values:
            return None, f"{name} history repeats mode {int(x)}"
        values[int(x)] = y
    if not values:
        return None, f"{name} history is empty"
    return values, None


def history_frequencies(manifest: Mapping[str, Any], frame_frequencies: Mapping[int, float]):
    """(mode -> full-precision EIGFREQ frequency, mode -> reason the frame frequency is kept).

    A mode takes its EIGFREQ value only if: exactly one EIGFREQ history exists with unique integer mode numbers; it
    contains the mode; the value agrees with the frame frequency within the frame's reported precision; no other
    mode's EIGFREQ value is equally consistent with that frame frequency; and, when an EIGVAL history exists, it is
    single, lists the same modes and sqrt(EIGVAL)/2pi agrees with EIGFREQ. Array order and nearest-value search are
    never used.
    """
    eigfreq, eigfreq_problem = _single_history(manifest, "EIGFREQ")
    eigval, eigval_problem = _single_history(manifest, "EIGVAL")
    problem = eigfreq_problem or eigval_problem
    if problem is None and eigfreq is None:
        problem = "no EIGFREQ history"
    if problem is None and eigval is not None and set(eigval) != set(eigfreq):
        problem = "the EIGVAL and EIGFREQ histories list different modes"
    if problem is not None:
        return {}, {mode: problem for mode in frame_frequencies}
    accepted: Dict[int, float] = {}
    rejected: Dict[int, str] = {}
    for mode, frame in frame_frequencies.items():
        value = eigfreq.get(mode)
        tolerance = _reported_precision(frame)
        if value is None:
            rejected[mode] = f"mode {mode} is not in the EIGFREQ history"
        elif not (frame > 0.0 and abs(value - frame) <= tolerance):
            rejected[mode] = f"EIGFREQ {value!r} contradicts the frame frequency {frame!r} of mode {mode}"
        elif any(other != mode and abs(candidate - frame) <= tolerance for other, candidate in eigfreq.items()):
            rejected[mode] = f"the frame frequency {frame!r} of mode {mode} also matches another EIGFREQ mode"
        elif eigval is not None and not (
                eigval[mode] > 0.0
                and abs(math.sqrt(eigval[mode]) / (2.0 * math.pi) - value) <= _EIGVAL_RELATIVE_TOLERANCE * value):
            rejected[mode] = f"the EIGVAL of mode {mode} contradicts its EIGFREQ"
        else:
            accepted[mode] = value
    return accepted, rejected


# R7: the pinned extractor writes `frame.frameValue` as the frequency when `frame.frequency` is exactly 0. In a
# frequency step `frameValue` holds the mode number, so a zero-frequency (rigid-body) frame is recorded as "1 Hz",
# "2 Hz", ... The frame description ("Mode 1: Value = ... Freq = 0.0000 (cycles/time)") and the EIGFREQ history are
# independent records of the same frame. A manifest frequency that contradicts them never enters a comparison; the
# mode is not loaded and the reason is recorded. Nothing is replaced by an inferred value.
_DESCRIPTION_FREQUENCY = re.compile(r"\bfreq(?:uency)?\s*[:=]\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[Ee][-+]?\d+)?)",
                                    re.IGNORECASE)


def described_frequency(description: Any) -> Optional[tuple]:
    """(frequency, half a unit in its last printed digit) from an Abaqus frame description, or None."""
    match = _DESCRIPTION_FREQUENCY.search(str(description or ""))
    if match is None:
        return None
    text = match.group(1)
    value = float(text)
    if not math.isfinite(value):
        return None
    exponent = Decimal(text).as_tuple().exponent
    half_unit = 0.5 * 10.0 ** exponent if isinstance(exponent, int) else 0.0
    return value, max(half_unit, abs(value) * _FLOAT32_RESOLUTION)


def reliable_eigfreq(manifest: Mapping[str, Any]) -> tuple:
    """(mode -> EIGFREQ value usable as an independent record, mode -> why it is not).

    EIGFREQ counts only when its history is single and well formed and, when an EIGVAL history exists, EIGVAL agrees
    for that mode (sqrt(max(EIGVAL, 0))/2pi within a few single-precision ulps; a rigid mode's non-positive EIGVAL
    agrees with EIGFREQ = 0). This is the existing EIGFREQ/EIGVAL policy applied to consistency checking only.
    """
    eigfreq, problem = _single_history(manifest, "EIGFREQ")
    if eigfreq is None:
        return {}, {}
    eigval, eigval_problem = _single_history(manifest, "EIGVAL")
    if eigval_problem is not None:
        return {}, {mode: f"EIGVAL history unusable ({eigval_problem})" for mode in eigfreq}
    reliable: Dict[int, float] = {}
    notes: Dict[int, str] = {}
    for mode, value in eigfreq.items():
        if eigval is not None:
            if mode not in eigval:
                notes[mode] = f"mode {mode} has EIGFREQ but no EIGVAL"
                continue
            expected = math.sqrt(max(eigval[mode], 0.0)) / (2.0 * math.pi)
            if abs(expected - value) > _EIGVAL_RELATIVE_TOLERANCE * max(abs(value), expected) + 1e-12:
                notes[mode] = f"the EIGVAL of mode {mode} contradicts its EIGFREQ"
                continue
        reliable[mode] = value
    return reliable, notes


def manifest_frequency_problem(mode: int, manifest_frequency: float, description: Any,
                               eigfreq: Optional[Mapping[int, float]]) -> Optional[dict]:
    """Why a manifest frequency cannot be used (with the independent records), or None when every record agrees.

    Records of the same mode: the manifest value, the frame description ("Freq = ...") and a reliable EIGFREQ value
    (``reliable_eigfreq``). The manifest must agree with the description; the frame frequency (the description, or the
    manifest when there is none) must agree with EIGFREQ, within the printed precision plus float32 resolution. Any
    contradiction refuses the mode: nothing is chosen between the records and nothing is substituted. A value with no
    second record is left unchanged (legacy packages).
    """
    history = None if eigfreq is None else eigfreq.get(mode)
    described = described_frequency(description)
    reasons = []
    if described is not None:
        frame_value, frame_tolerance = described
        if abs(manifest_frequency - frame_value) > max(frame_tolerance, _reported_precision(manifest_frequency)):
            reasons.append(f"manifest frequency {manifest_frequency!r} Hz of mode {mode} contradicts its frame "
                           f"description ({frame_value!r} Hz)")
    else:
        frame_value, frame_tolerance = manifest_frequency, _reported_precision(manifest_frequency)
    if history is not None and abs(frame_value - history) > frame_tolerance + abs(history) * _FLOAT32_RESOLUTION:
        source = "frame description" if described is not None else "manifest frequency"
        reasons.append(f"the {source} {frame_value!r} Hz of mode {mode} contradicts EIGFREQ ({history!r} Hz)")
    if not reasons:
        return None
    reason = "; ".join(reasons)
    if manifest_frequency == float(mode):
        reason += "; the manifest value equals the mode number (frameValue fallback of a zero-frequency frame)"
    agreed = None
    if described is not None and history is not None and \
            abs(described[0] - history) <= described[1] + abs(history) * _FLOAT32_RESOLUTION:
        agreed = history
    elif described is not None and history is None:
        agreed = None  # one independent record only: recorded, never used
    return {"reason": reason, "manifest_frequency_hz": manifest_frequency,
            "described_frequency_hz": None if described is None else described[0], "eigfreq_hz": history,
            "independent_records_agree_on_hz": agreed}


def load_extracted_odb(manifest_path: Path, cancel_event=None) -> ModalDataset:
    manifest_path = Path(manifest_path)
    with manifest_path.open("r", encoding="utf-8") as stream:
        manifest = json.load(stream)

    format_version = int(manifest.get("format_version", 1))
    geometry: Optional[Dict[tuple, List[float]]] = None
    if format_version >= 2:
        geometry_file = manifest.get("geometry_file")
        if not geometry_file:
            raise ValueError(
                "Extraction manifest declares format_version "
                f"{format_version} but has no geometry_file entry."
            )
        geometry_path = manifest_path.parent / geometry_file
        if not geometry_path.exists():
            raise FileNotFoundError(f"Extracted geometry file is missing: {geometry_path}")
        geometry = _load_geometry_csv(geometry_path)

    eigfreq, eigfreq_notes = reliable_eigfreq(manifest)
    rejected: Dict[int, dict] = {}
    for entry in manifest.get("modes", []):
        problem = manifest_frequency_problem(int(entry["mode"]), float(entry["frequency_hz"]),
                                             entry.get("description"), eigfreq)
        if problem is not None:
            rejected[int(entry["mode"])] = problem
    mode_entries = [entry for entry in manifest.get("modes", []) if int(entry["mode"]) not in rejected]
    frame_frequencies = {int(entry["mode"]): float(entry["frequency_hz"]) for entry in mode_entries}
    precise, kept = history_frequencies(manifest, frame_frequencies)
    modes: List[ModeShape] = []
    for mode_entry in mode_entries:
        if cancel_event is not None and cancel_event.is_set():
            # Cooperative cancellation during Python-side parse/read: no
            # Abaqus worker is alive at this point (extraction already
            # finished), so exiting the parse loop promptly is sufficient --
            # nothing to terminate, just stop doing work and unwind.
            raise AnalysisCancelled("Analysis stopped by user.")
        file_path = manifest_path.parent / mode_entry["file"]
        if not file_path.exists():
            raise FileNotFoundError(f"Extracted mode file is missing: {file_path}")
        mode_number = int(mode_entry["mode"])
        frame_frequency = float(mode_entry["frequency_hz"])
        metadata = {
            "frame_index": mode_entry.get("frame_index"),
            "frame_description": mode_entry.get("description"),
            "step_name": manifest.get("step_name"),
            "frame_frequency_hz": frame_frequency,
            "frequency_source": FREQUENCY_SOURCE_HISTORY if mode_number in precise else FREQUENCY_SOURCE_FRAME,
        }
        if mode_number in kept:
            metadata["frequency_history_note"] = kept[mode_number]
        modes.append(
            _load_mode_csv(
                file_path=file_path,
                mode_number=mode_number,
                frequency_hz=precise.get(mode_number, frame_frequency),
                metadata=metadata,
                geometry=geometry,
            )
        )

    if not modes:
        if rejected:
            raise ValueError("The extracted Abaqus package contains no usable modes: "
                             + "; ".join(item["reason"] for item in rejected.values()))
        raise ValueError("The extracted Abaqus package contains no modes.")
    if rejected:
        manifest["rejected_frequency_modes"] = {str(mode): item for mode, item in sorted(rejected.items())}
    if eigfreq_notes:
        manifest["eigfreq_not_used_for_consistency"] = {str(mode): note for mode, note in sorted(eigfreq_notes.items())}
    notice = extraction_range_notice(manifest)
    if notice is not None:
        manifest["extraction_range_notice"] = notice
    manifest["frequency_sources"] = {
        "history_modes": sorted(precise),
        "frame_modes": {str(mode): reason for mode, reason in sorted(kept.items())},
    }
    return ModalDataset(
        source_name="Abaqus ODB",
        source_path=Path(manifest.get("odb_path", manifest_path)),
        modes=modes,
        metadata=manifest,
        history=list(manifest.get("history", [])),
    )


def _source_signature(
    odb_path: Path,
    abaqus_command: str,
    start_mode: int,
    end_mode: int,
) -> Dict[str, Any]:
    stat = odb_path.stat()
    return {
        "odb_path": str(odb_path.resolve()),
        "odb_size": int(stat.st_size),
        "odb_mtime_ns": int(stat.st_mtime_ns),
        "abaqus_command": abaqus_command.strip() or "abaqus",
        "start_mode": int(start_mode),
        "end_mode": int(end_mode),
    }


def _cache_is_valid(
    cache_directory: Path,
    signature: Dict[str, Any],
) -> bool:
    manifest_path = cache_directory / "manifest.json"
    signature_path = cache_directory / "extraction_signature.json"
    if not manifest_path.exists() or not signature_path.exists():
        return False
    try:
        cached_signature = json.loads(signature_path.read_text(encoding="utf-8"))
        if cached_signature != signature:
            return False
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return bool(manifest.get("modes")) and all(
            (cache_directory / item["file"]).exists()
            for item in manifest.get("modes", [])
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def load_or_extract_odb(
    odb_or_manifest_path: Path,
    cache_directory: Path,
    abaqus_command: str,
    start_mode: int,
    end_mode: int,
    cancel_event=None,
    process_callback: Optional[Callable[[Optional[subprocess.Popen]], None]] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> ModalDataset:
    selected = Path(odb_or_manifest_path)
    if selected.name.lower() == "manifest.json":
        return load_extracted_odb(selected, cancel_event=cancel_event)
    if selected.suffix.lower() != ".odb":
        raise ValueError(
            "Select an Abaqus .odb file or a previously extracted manifest.json file."
        )

    cache_directory = Path(cache_directory)
    cache_directory.mkdir(parents=True, exist_ok=True)
    signature = _source_signature(
        selected, abaqus_command, start_mode, end_mode
    )
    manifest_path = cache_directory / "manifest.json"
    if _cache_is_valid(cache_directory, signature):
        dataset = load_extracted_odb(manifest_path, cancel_event=cancel_event)
        dataset.metadata["extraction_cache_reused"] = True
        return dataset

    manifest_path = run_abaqus_extraction(
        odb_path=selected,
        output_directory=cache_directory,
        abaqus_command=abaqus_command,
        start_mode=start_mode,
        end_mode=end_mode,
        cancel_event=cancel_event,
        process_callback=process_callback,
        progress_callback=progress_callback,
    )
    (cache_directory / "extraction_signature.json").write_text(
        json.dumps(signature, indent=2, sort_keys=True), encoding="utf-8"
    )
    dataset = load_extracted_odb(manifest_path, cancel_event=cancel_event)
    dataset.metadata["extraction_cache_reused"] = False
    return dataset
