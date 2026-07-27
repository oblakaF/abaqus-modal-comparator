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

from odbAccess import openOdb


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


def node_coordinates(odb):
    coordinates = {}
    for instance_name, instance in odb.rootAssembly.instances.items():
        for node in instance.nodes:
            xyz = list(node.coordinates)
            while len(xyz) < 3:
                xyz.append(0.0)
            coordinates[(instance_name, int(node.label))] = xyz[:3]
    return coordinates


def vector_parts(value):
    real_data = list(getattr(value, "data", ()) or ())
    while len(real_data) < 3:
        real_data.append(0.0)
    imaginary_data = [0.0, 0.0, 0.0]
    try:
        conjugate = getattr(value, "conjugateData", None)
        if conjugate:
            imaginary_data = list(conjugate)
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
    args = parser.parse_args()

    odb_path = os.path.abspath(args.odb)
    output_directory = os.path.abspath(args.output)
    if not os.path.isdir(output_directory):
        os.makedirs(output_directory)

    odb = openOdb(path=odb_path, readOnly=True)
    try:
        step_name, frames = select_modal_step(odb, args.start_mode, args.end_mode)
        step = odb.steps[step_name]
        coordinates = node_coordinates(odb)
        mode_entries = []

        for frame_index, frame, mode_number, frequency in frames:
            file_name = "mode_%04d.csv" % mode_number
            file_path = os.path.join(output_directory, file_name)
            field = frame.fieldOutputs["U"]

            with open(file_path, "w") as stream:
                writer = csv.writer(stream, lineterminator="\n")
                writer.writerow(
                    [
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
                    ]
                )
                row_count = 0
                for value in field.values:
                    instance = getattr(value, "instance", None)
                    instance_name = getattr(instance, "name", "ASSEMBLY")
                    node_label = int(getattr(value, "nodeLabel", 0))
                    xyz = coordinates.get((instance_name, node_label), [0.0, 0.0, 0.0])
                    real_data, imaginary_data = vector_parts(value)
                    writer.writerow(
                        [instance_name, node_label]
                        + ["%.16g" % item for item in xyz]
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

        manifest = {
            "format_version": 1,
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
        with open(manifest_path, "w") as stream:
            json.dump(manifest, stream, indent=2, sort_keys=True)
        print("Wrote %s" % manifest_path)
    finally:
        odb.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("ERROR: %s" % error, file=sys.stderr)
        raise
