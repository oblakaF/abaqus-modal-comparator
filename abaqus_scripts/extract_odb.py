# -*- coding: utf-8 -*-
"""Extract modal frequencies, coordinates, and displacement vectors from an Abaqus ODB.

Run through the Abaqus Python interpreter:
    abaqus python extract_odb.py --odb Job-1.odb --output out --start-mode 6 --end-mode 14

The script intentionally uses Python-2-compatible syntax because older Abaqus releases
ship Python 2.7, while newer releases ship Python 3.
"""

from __future__ import print_function

import argparse
import csv
import json
import os
import re
import sys
import time

from odbAccess import openOdb


# Bumped whenever the on-disk extraction layout changes in a way that a
# consumer must branch on. Format 1 wrote node coordinates redundantly into
# every per-mode CSV. Format 2 writes static node geometry once (geometry.csv)
# and per-mode CSV files carry only the dynamic displacement values, joined
# back to geometry by (instance, node_label). abaqus_bridge.load_extracted_odb
# dispatches on manifest["format_version"] and still reads format 1 read-only.
FORMAT_VERSION = 2


def _log(message):
    """Emit a single-line, timestamped progress marker to stdout.

    Abaqus's subprocess stdout is captured to a log file by abaqus_bridge and
    tailed for new lines, so each call here becomes one GUI-visible progress
    update. Keep messages short and free of embedded newlines.
    """
    print("PROGRESS: %s" % message)
    sys.stdout.flush()


def _process_creation_time(pid):
    """Best-effort Windows process creation timestamp (FILETIME halves).

    Used only as an additional PID-reuse safety check by the controller; the
    process that actually runs this script reports its own creation time so
    the controller never has to guess or race a query after the fact. Returns
    None off Windows or if the query fails for any reason (never fatal).
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
    except Exception:
        return None


def _atomic_replace(tmp_path, final_path):
    """Publish tmp_path as final_path so a reader never observes a partial file.

    Plain os.rename fails on Windows if final_path already exists (and
    os.replace is Python-3-only, while this script also runs under Abaqus's
    Python 2.7). MoveFileExW with MOVEFILE_REPLACE_EXISTING is atomic on a
    single volume on Windows; elsewhere fall back to remove-then-rename.
    """
    if os.name == "nt":
        try:
            import ctypes

            MOVEFILE_REPLACE_EXISTING = 0x1
            MOVEFILE_WRITE_THROUGH = 0x8
            ok = ctypes.windll.kernel32.MoveFileExW(
                unicode(tmp_path) if str is bytes else tmp_path,  # noqa: F821
                unicode(final_path) if str is bytes else final_path,  # noqa: F821
                MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
            )
            if ok:
                return
        except Exception:
            pass
    try:
        if os.path.exists(final_path):
            os.remove(final_path)
    except OSError:
        pass
    os.rename(tmp_path, final_path)


def _write_registration(registration_file, owner_token):
    """Self-register this process as the owner of the current extraction run.

    Written as early as possible (before openOdb) and atomically, so the
    controller can positively identify the real worker PID for cancellation
    even if Abaqus's launcher chain later reparents/detaches it away from the
    originally-spawned launcher process.
    """
    if not registration_file or not owner_token:
        return
    pid = os.getpid()
    record = {
        "token": owner_token,
        "pid": pid,
        "timestamp": time.time(),
        "format_version": FORMAT_VERSION,
    }
    creation_time = _process_creation_time(pid)
    if creation_time is not None:
        record["creation_time"] = creation_time
    tmp_path = "%s.tmp-%d" % (registration_file, pid)
    try:
        with open(tmp_path, "w") as stream:
            json.dump(record, stream)
            stream.flush()
            try:
                os.fsync(stream.fileno())
            except Exception:
                pass
        _atomic_replace(tmp_path, registration_file)
        _log("registered worker pid %d" % pid)
    except Exception as error:
        # Registration is best-effort from the extractor's point of view: if
        # it fails, the controller simply has no positive worker identity and
        # falls back to launcher-tree-only cancellation (documented gap), but
        # extraction itself must not be blocked by a registration failure.
        _log("worker registration failed: %s" % error)


def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return float(default)


def frame_mode_number(frame, fallback):
    value = getattr(frame, "mode", None)
    if value not in (None, 0):
        try:
            return int(value)
        except Exception:
            pass
    description = getattr(frame, "description", "") or ""
    match = re.search(r"mode\s*[:=]?\s*(\d+)", description, re.I)
    if match:
        return int(match.group(1))
    return int(fallback)


def frame_frequency(frame):
    value = getattr(frame, "frequency", None)
    if value not in (None, 0):
        return safe_float(value)
    frame_value = getattr(frame, "frameValue", None)
    if frame_value not in (None, 0):
        return safe_float(frame_value)
    description = getattr(frame, "description", "") or ""
    match = re.search(r"frequency\s*[:=]?\s*([0-9.+\-Ee]+)", description, re.I)
    if match:
        return safe_float(match.group(1))
    return 0.0


def select_modal_step(odb, start_mode, end_mode):
    best = None
    for step_name, step in odb.steps.items():
        candidates = []
        for frame_index, frame in enumerate(step.frames):
            if "U" not in frame.fieldOutputs:
                continue
            mode_number = frame_mode_number(frame, frame_index)
            frequency = frame_frequency(frame)
            if frequency <= 0:
                continue
            if mode_number < start_mode or mode_number > end_mode:
                continue
            candidates.append((frame_index, frame, mode_number, frequency))
        if best is None or len(candidates) > len(best[1]):
            best = (step_name, candidates)
    if best is None or not best[1]:
        raise RuntimeError(
            "No frequency-extraction frames with displacement output U were found "
            "for modes %d-%d." % (start_mode, end_mode)
        )
    return best


def describe_available_modes(odb, start_mode, end_mode):
    """Scan every step's frames once to report the full modal range present.

    This is a diagnostic pass only (no field data is read) so it stays cheap
    even for a large ODB, and lets the caller surface an accurate range-clip
    message such as "requested 7-30; ODB contains modes through 16".
    """
    all_modes = []
    for step in odb.steps.values():
        for frame_index, frame in enumerate(step.frames):
            if "U" not in frame.fieldOutputs:
                continue
            frequency = frame_frequency(frame)
            if frequency <= 0:
                continue
            all_modes.append(frame_mode_number(frame, frame_index))
    if not all_modes:
        return None
    return min(all_modes), max(all_modes)


def node_coordinates(odb):
    coordinates = {}
    for instance_name, instance in odb.rootAssembly.instances.items():
        for node in instance.nodes:
            xyz = list(node.coordinates)
            while len(xyz) < 3:
                xyz.append(0.0)
            coordinates[(instance_name, int(node.label))] = xyz[:3]
    return coordinates


def sequence_values(raw_value):
    """Convert Abaqus scalar/list/tuple/numpy-like data to a normal list.

    Abaqus may expose FieldValue.data and conjugateData as numpy arrays. Their
    truth value is ambiguous, so they must never be used in expressions such as
    ``raw_value or ()`` or ``if raw_value``.
    """
    if raw_value is None:
        return []
    try:
        return list(raw_value)
    except TypeError:
        return [raw_value]


def vector_parts(value):
    real_data = sequence_values(getattr(value, "data", None))
    while len(real_data) < 3:
        real_data.append(0.0)

    imaginary_data = [0.0, 0.0, 0.0]
    try:
        conjugate = getattr(value, "conjugateData", None)
        conjugate_values = sequence_values(conjugate)
        if len(conjugate_values) > 0:
            imaginary_data = conjugate_values
            while len(imaginary_data) < 3:
                imaginary_data.append(0.0)
    except Exception:
        pass

    return real_data[:3], imaginary_data[:3]


def extract_history(step):
    keywords = ("FREQ", "EIG", "MASS", "MODAL", "PART", "PF", "EM")
    output = []
    for region_name, region in step.historyRegions.items():
        for output_name, history_output in region.historyOutputs.items():
            upper_name = output_name.upper()
            if not any(keyword in upper_name for keyword in keywords):
                continue
            values = []
            for pair in list(history_output.data)[:1000]:
                try:
                    values.append([safe_float(pair[0]), safe_float(pair[1])])
                except Exception:
                    continue
            output.append(
                {
                    "region": region_name,
                    "name": output_name,
                    "description": getattr(history_output, "description", ""),
                    "data": values,
                }
            )
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--odb", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--start-mode", type=int, default=6)
    parser.add_argument("--end-mode", type=int, default=14)
    parser.add_argument("--owner-token", default=None)
    parser.add_argument("--registration-file", default=None)
    args = parser.parse_args()

    odb_path = os.path.abspath(args.odb)
    output_directory = os.path.abspath(args.output)
    if not os.path.isdir(output_directory):
        os.makedirs(output_directory)

    _write_registration(args.registration_file, args.owner_token)

    _log("opening ODB %s" % os.path.basename(odb_path))
    open_started = time.time()
    odb = openOdb(path=odb_path, readOnly=True)
    _log("ODB opened in %.1fs" % (time.time() - open_started))
    try:
        available = describe_available_modes(odb, args.start_mode, args.end_mode)
        if available is not None:
            _log(
                "modes available %d-%d; requested %d-%d"
                % (available[0], available[1], args.start_mode, args.end_mode)
            )
        step_name, frames = select_modal_step(odb, args.start_mode, args.end_mode)
        step = odb.steps[step_name]
        effective_modes = sorted(item[2] for item in frames)
        if effective_modes:
            _log(
                "using modes %d-%d (%d frames)"
                % (effective_modes[0], effective_modes[-1], len(effective_modes))
            )

        geometry_started = time.time()
        _log("exporting geometry...")
        coordinates = node_coordinates(odb)
        geometry_file_name = "geometry.csv"
        geometry_path = os.path.join(output_directory, geometry_file_name)
        with open(geometry_path, "w") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(["instance", "node_label", "x", "y", "z"])
            for (instance_name, node_label), xyz in coordinates.items():
                writer.writerow(
                    [instance_name, node_label] + ["%.16g" % item for item in xyz]
                )
        _log(
            "geometry exported: %d nodes in %.1fs"
            % (len(coordinates), time.time() - geometry_started)
        )

        mode_entries = []
        total_modes = len(frames)
        for mode_index, (frame_index, frame, mode_number, frequency) in enumerate(frames, start=1):
            mode_started = time.time()
            _log("exporting mode %d/%d (mode %d)..." % (mode_index, total_modes, mode_number))
            file_name = "mode_%04d.csv" % mode_number
            file_path = os.path.join(output_directory, file_name)
            field = frame.fieldOutputs["U"]

            with open(file_path, "w") as stream:
                writer = csv.writer(stream, lineterminator="\n")
                writer.writerow(
                    [
                        "instance",
                        "node_label",
                        "u1_real",
                        "u2_real",
                        "u3_real",
                        "u1_imag",
                        "u2_imag",
                        "u3_imag",
                    ]
                )
                row_count = 0
                for value in field.values:
                    instance = getattr(value, "instance", None)
                    instance_name = getattr(instance, "name", "ASSEMBLY")
                    node_label = int(getattr(value, "nodeLabel", 0))
                    real_data, imaginary_data = vector_parts(value)
                    writer.writerow(
                        [instance_name, node_label]
                        + ["%.16g" % item for item in real_data]
                        + ["%.16g" % item for item in imaginary_data]
                    )
                    row_count += 1

            mode_entries.append(
                {
                    "mode": mode_number,
                    "frequency_hz": frequency,
                    "frame_index": frame_index,
                    "description": getattr(frame, "description", ""),
                    "file": file_name,
                    "node_count": row_count,
                }
            )
            print("Extracted mode %d at %.8g Hz (%d nodes)" % (mode_number, frequency, row_count))
            _log(
                "mode %d/%d done in %.1fs"
                % (mode_index, total_modes, time.time() - mode_started)
            )

        manifest = {
            "format_version": FORMAT_VERSION,
            "geometry_file": geometry_file_name,
            "geometry_node_count": len(coordinates),
            "odb_path": odb_path,
            "odb_name": getattr(odb, "name", os.path.basename(odb_path)),
            "analysis_title": getattr(odb, "analysisTitle", ""),
            "description": getattr(odb, "description", ""),
            "step_name": step_name,
            "start_mode": args.start_mode,
            "end_mode": args.end_mode,
            "modes": mode_entries,
            "history": extract_history(step),
        }

        manifest_path = os.path.join(output_directory, "manifest.json")
        manifest_tmp_path = "%s.tmp-%d" % (manifest_path, os.getpid())
        with open(manifest_tmp_path, "w") as stream:
            json.dump(manifest, stream, indent=2, sort_keys=True)
            stream.flush()
            try:
                os.fsync(stream.fileno())
            except Exception:
                pass
        _atomic_replace(manifest_tmp_path, manifest_path)
        _log("wrote manifest %s" % manifest_path)
        print("Wrote %s" % manifest_path)
    finally:
        odb.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("ERROR: %s" % error, file=sys.stderr)
        raise
