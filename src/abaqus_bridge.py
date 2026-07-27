from __future__ import annotations

import csv
import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from modal_core import ModalDataset, ModeShape


class AbaqusExtractionError(RuntimeError):
    pass


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

    try:
        completed = subprocess.run(
            command,
            cwd=str(script_path.parent),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as error:
        raise AbaqusExtractionError(
            "The Abaqus command could not be started. Enter the command used on this "
            "computer, for example 'abaqus', 'abq2024', or the full path to a .bat file."
        ) from error
    except subprocess.TimeoutExpired as error:
        raise AbaqusExtractionError(
            f"Abaqus extraction exceeded {timeout_seconds // 60} minutes."
        ) from error

    log_path = output_directory / "abaqus_extraction.log"
    log_path.write_text(
        "COMMAND\n"
        + " ".join(command)
        + "\n\nSTDOUT\n"
        + completed.stdout
        + "\n\nSTDERR\n"
        + completed.stderr,
        encoding="utf-8",
    )

    manifest_path = output_directory / "manifest.json"
    if completed.returncode != 0 or not manifest_path.exists():
        tail = (completed.stderr or completed.stdout or "No output was produced.")[-4000:]
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
    )
    (cache_directory / "extraction_signature.json").write_text(
        json.dumps(signature, indent=2, sort_keys=True), encoding="utf-8"
    )
    dataset = load_extracted_odb(manifest_path)
    dataset.metadata["extraction_cache_reused"] = False
    return dataset
