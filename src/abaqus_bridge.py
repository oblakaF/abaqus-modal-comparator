from __future__ import annotations

import csv
import json
import os
import shlex
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

import numpy as np

from modal_core import ModalDataset, ModeShape


class AbaqusExtractionError(RuntimeError):
    pass


class AnalysisCancelled(RuntimeError):
    """Raised when the user cancels work owned by this application."""


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
) -> Path:
    odb_path = Path(odb_path).resolve()
    output_directory = Path(output_directory).resolve()
    output_directory.mkdir(parents=True, exist_ok=True)

    script_path = Path(__file__).resolve().parents[1] / "abaqus_scripts" / "extract_odb.py"
    if not script_path.exists():
        raise FileNotFoundError(f"Abaqus extraction script was not found: {script_path}")

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
            while process.poll() is None:
                if cancel_event is not None and cancel_event.is_set():
                    if not stop_owned_process_and_wait(process):
                        raise AbaqusExtractionError(
                            "The owned Abaqus process did not stop within the cancellation timeout."
                        )
                    raise AnalysisCancelled("Analysis stopped by user.")
                if time.monotonic() - started > timeout_seconds:
                    if not stop_owned_process_and_wait(process):
                        raise AbaqusExtractionError(
                            "Abaqus extraction timed out, but the owned process did not stop."
                        )
                    raise AbaqusExtractionError(
                        f"Abaqus extraction exceeded {timeout_seconds // 60} minutes."
                    )
                time.sleep(0.1)
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


def _load_mode_csv(
    file_path: Path,
    mode_number: int,
    frequency_hz: float,
    metadata: Dict[str, Any],
) -> ModeShape:
    node_ids: List[str] = []
    coordinates: List[List[float]] = []
    vectors: List[List[complex]] = []

    with file_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {
            "instance",
            "node_label",
            "x",
            "y",
            "z",
            "u1_real",
            "u2_real",
            "u3_real",
            "u1_imag",
            "u2_imag",
            "u3_imag",
        }
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"Invalid Abaqus mode file: {file_path.name}")

        for row in reader:
            node_ids.append(f"{row['instance']}:{row['node_label']}")
            coordinates.append([float(row["x"]), float(row["y"]), float(row["z"])])
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


def load_extracted_odb(manifest_path: Path) -> ModalDataset:
    manifest_path = Path(manifest_path)
    with manifest_path.open("r", encoding="utf-8") as stream:
        manifest = json.load(stream)

    modes: List[ModeShape] = []
    for mode_entry in manifest.get("modes", []):
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
) -> ModalDataset:
    selected = Path(odb_or_manifest_path)
    if selected.name.lower() == "manifest.json":
        return load_extracted_odb(selected)
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
        dataset = load_extracted_odb(manifest_path)
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
    )
    (cache_directory / "extraction_signature.json").write_text(
        json.dumps(signature, indent=2, sort_keys=True), encoding="utf-8"
    )
    dataset = load_extracted_odb(manifest_path)
    dataset.metadata["extraction_cache_reused"] = False
    return dataset
