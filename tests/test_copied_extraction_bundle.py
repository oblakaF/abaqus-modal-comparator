"""Copy-first rule: a copied extraction bundle (manifest + the files it references) loads on its own.

The application must work from a verified copy of an extraction bundle. Selecting the copied manifest.json never
opens the ODB recorded in the manifest's provenance (that ODB may be absent, or busy in the user's Abaqus) and never
starts Abaqus or any other process. Synthetic files only; no Abaqus.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import abaqus_bridge  # noqa: E402


def _write_bundle(folder: Path, odb_path: str) -> Path:
    folder.mkdir(parents=True)
    (folder / "geometry.csv").write_text(
        "instance,node_label,x,y,z\nPART-1,1,0,0,0\nPART-1,2,10,0,0\nPART-1,3,0,10,0\n", encoding="utf-8")
    modes = []
    for number, hz in ((7, 58.1), (8, 144.7)):
        name = f"mode_{number:04d}.csv"
        (folder / name).write_text(
            "instance,node_label,u1_real,u2_real,u3_real,u1_imag,u2_imag,u3_imag\n"
            f"PART-1,1,0,0,{number * 0.1},0,0,0\nPART-1,2,0,0,-0.2,0,0,0\nPART-1,3,0,0,0.3,0,0,0\n",
            encoding="utf-8")
        modes.append({"mode": number, "frequency_hz": hz, "file": name, "frame_index": number - 7})
    manifest = folder / "manifest.json"
    manifest.write_text(json.dumps({"format_version": 2, "geometry_file": "geometry.csv", "step_name": "Modal",
                                    "start_mode": 7, "end_mode": 8, "odb_path": odb_path, "odb_name": odb_path,
                                    "modes": modes}), encoding="utf-8")
    return manifest


def _no_process(*_args, **_kwargs):
    raise AssertionError("loading a copied extraction bundle must not start Abaqus or any process")


class CopiedBundleTests(unittest.TestCase):
    def test_a_relocated_bundle_loads_without_its_recorded_odb_or_any_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = _write_bundle(root / "original" / "abaqus", str(root / "absent" / "Specimen.odb"))
            copy = root / "acceptance" / "run_1" / "inputs" / "abaqus_bundle"
            shutil.copytree(original.parent, copy)
            shutil.rmtree(original.parent)  # the copy must not depend on the source folder either
            cache = root / "acceptance" / "run_1" / "output" / "abaqus"
            with mock.patch("subprocess.Popen", side_effect=_no_process), \
                    mock.patch.object(abaqus_bridge, "run_abaqus_extraction", side_effect=_no_process):
                dataset = abaqus_bridge.load_or_extract_odb(copy / "manifest.json", cache, "abaqus", 7, 8)
            self.assertEqual([m.number for m in dataset.sorted_modes()], [7, 8])
            self.assertEqual([m.frequency_hz for m in dataset.sorted_modes()], [58.1, 144.7])
            self.assertFalse((root / "absent").exists())  # the recorded ODB path was never created or opened
            self.assertFalse(cache.exists())  # nothing is written next to, or on behalf of, the source bundle


if __name__ == "__main__":
    unittest.main()
