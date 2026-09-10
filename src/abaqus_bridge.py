from __future__ import annotations

import csv
import json
import os
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

    modes: List[ModeShape] = []
    for mode_entry in manifest.get("modes", []):
        if cancel_event is not None and cancel_event.is_set():
            # Cooperative cancellation during Python-side parse/read: no
            # Abaqus worker is alive at this point (extraction already
            # finished), so exiting the parse loop promptly is sufficient --
            # nothing to terminate, just stop doing work and unwind.
            raise AnalysisCancelled("Analysis stopped by user.")
        file_path = manifest_path.parent / mode_entry["file"]
        if not file_path.exists():
            raise FileNotFoundError(f"Extracted mode file is missing: {file_path}")
        modes.append(
            _load_mode_csv(
                file_path=file_path,
                mode_number=int(mode_entry["mode"]),
                frequency_hz=float(mode_entry["frequency_hz"]),
                metadata={
                    "frame_index": mode_entry.get("frame_index"),
                    "frame_description": mode_entry.get("description"),
                    "step_name": manifest.get("step_name"),
                },
                geometry=geometry,
            )
        )

    if not modes:
        raise ValueError("The extracted Abaqus package contains no modes.")
    notice = extraction_range_notice(manifest)
    if notice is not None:
        manifest["extraction_range_notice"] = notice
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
