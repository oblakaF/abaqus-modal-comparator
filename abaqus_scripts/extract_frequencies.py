# -*- coding: utf-8 -*-
"""Extract direct eigenfrequencies from an Abaqus ODB to a small JSON file.

Run with the Abaqus Python interpreter.  The implementation remains compatible
with Abaqus releases that embed Python 2.7.
"""

from __future__ import print_function

import argparse
import json
import os
import re
import sys

from odbAccess import openOdb


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
    if value is not None:
        try:
            return float(value)
        except Exception:
            pass
    description = getattr(frame, "description", "") or ""
    match = re.search(r"frequency\s*[:=]?\s*([0-9.+\-Ee]+)", description, re.I)
    if match:
        return float(match.group(1))
    return None


def select_frequency_step(odb):
    best = None
    for step_name, step in odb.steps.items():
        modes = []
        for frame_index, frame in enumerate(step.frames):
            mode = frame_mode_number(frame, frame_index)
            frequency = frame_frequency(frame)
            if mode <= 0 or frequency is None:
                continue
            modes.append(
                {
                    "mode": mode,
                    "frequency_hz": frequency,
                    "frame_index": frame_index,
                    "description": getattr(frame, "description", ""),
                }
            )
        if best is None or len(modes) > len(best[1]):
            best = (step_name, modes)
    if best is None or not best[1]:
        raise RuntimeError("No frequency-extraction modes were found in the ODB.")
    best[1].sort(key=lambda item: item["mode"])
    return best


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--odb", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    odb_path = os.path.abspath(args.odb)
    output_path = os.path.abspath(args.output)
    odb = openOdb(path=odb_path, readOnly=True)
    try:
        step_name, modes = select_frequency_step(odb)
        payload = {
            "format_version": 1,
            "odb_path": odb_path,
            "step_name": step_name,
            "modes": modes,
        }
        with open(output_path, "w") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
        print("Wrote %s" % output_path)
    finally:
        odb.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("ERROR: %s" % error, file=sys.stderr)
        raise
