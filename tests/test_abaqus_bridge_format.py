from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from abaqus_bridge import load_extracted_odb, run_abaqus_extraction  # noqa: E402


def _write_csv(path: Path, header, rows) -> None:
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join(str(item) for item in row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class FormatTwoExtractionTests(unittest.TestCase):
    """format_version 2: static geometry written once, mode files hold only
    dynamic displacement values joined back to geometry by (instance, node)."""

    def test_format_two_round_trip_matches_format_one_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_csv(
                root / "geometry.csv",
                ["instance", "node_label", "x", "y", "z"],
                [
                    ["PART-1", 1, "1.0", "2.0", "3.0"],
                    ["PART-1", 2, "4.0", "5.0", "6.0"],
                ],
            )
            _write_csv(
                root / "mode_0007.csv",
                ["instance", "node_label", "u1_real", "u2_real", "u3_real", "u1_imag", "u2_imag", "u3_imag"],
                [
                    ["PART-1", 1, "0.1", "0.2", "0.3", "0", "0", "0"],
                    ["PART-1", 2, "0.4", "0.5", "0.6", "0", "0", "0"],
                ],
            )
            manifest = {
                "format_version": 2,
                "geometry_file": "geometry.csv",
                "step_name": "Step-1",
                "start_mode": 7,
                "end_mode": 7,
                "modes": [
                    {"mode": 7, "frequency_hz": 24.1, "file": "mode_0007.csv", "frame_index": 0}
                ],
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            dataset = load_extracted_odb(manifest_path)

        self.assertEqual(len(dataset.modes), 1)
        mode = dataset.modes[0]
        self.assertEqual(list(mode.node_ids), ["PART-1:1", "PART-1:2"])
        self.assertEqual(mode.coordinates.tolist(), [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        self.assertAlmostEqual(mode.vectors[0, 0].real, 0.1)
        self.assertAlmostEqual(mode.vectors[1, 2].real, 0.6)

    def test_format_one_legacy_files_still_load(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_csv(
                root / "mode_0007.csv",
                [
                    "instance", "node_label", "x", "y", "z",
                    "u1_real", "u2_real", "u3_real", "u1_imag", "u2_imag", "u3_imag",
                ],
                [["PART-1", 1, "1.0", "2.0", "3.0", "0.1", "0.2", "0.3", "0", "0", "0"]],
            )
            manifest = {
                "format_version": 1,
                "step_name": "Step-1",
                "start_mode": 7,
                "end_mode": 7,
                "modes": [
                    {"mode": 7, "frequency_hz": 24.1, "file": "mode_0007.csv", "frame_index": 0}
                ],
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            dataset = load_extracted_odb(manifest_path)

        mode = dataset.modes[0]
        self.assertEqual(mode.coordinates.tolist(), [[1.0, 2.0, 3.0]])

    def test_missing_manifest_without_format_version_defaults_to_legacy(self):
        # Old caches predate the format_version key entirely; the default of 1
        # must dispatch to the legacy (inline-geometry) reader, never to the
        # format-2 reader, so an old cache is never misread as the new layout.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_csv(
                root / "mode_0007.csv",
                [
                    "instance", "node_label", "x", "y", "z",
                    "u1_real", "u2_real", "u3_real", "u1_imag", "u2_imag", "u3_imag",
                ],
                [["PART-1", 1, "1.0", "2.0", "3.0", "0.1", "0.2", "0.3", "0", "0", "0"]],
            )
            manifest = {
                "step_name": "Step-1",
                "start_mode": 7,
                "end_mode": 7,
                "modes": [
                    {"mode": 7, "frequency_hz": 24.1, "file": "mode_0007.csv", "frame_index": 0}
                ],
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            dataset = load_extracted_odb(manifest_path)
        self.assertEqual(dataset.modes[0].coordinates.tolist(), [[1.0, 2.0, 3.0]])

    def test_format_two_missing_geometry_file_key_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = {"format_version": 2, "modes": []}
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "geometry_file"):
                load_extracted_odb(manifest_path)

    def test_format_two_missing_node_in_geometry_falls_back_to_origin(self):
        # Mirrors format-1's historical fallback for a node absent from the
        # coordinate lookup, so behavior does not silently change.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_csv(
                root / "geometry.csv",
                ["instance", "node_label", "x", "y", "z"],
                [["PART-1", 1, "1.0", "2.0", "3.0"]],
            )
            _write_csv(
                root / "mode_0007.csv",
                ["instance", "node_label", "u1_real", "u2_real", "u3_real", "u1_imag", "u2_imag", "u3_imag"],
                [["PART-1", 99, "0.1", "0.2", "0.3", "0", "0", "0"]],
            )
            manifest = {
                "format_version": 2,
                "geometry_file": "geometry.csv",
                "start_mode": 7,
                "end_mode": 7,
                "modes": [{"mode": 7, "frequency_hz": 24.1, "file": "mode_0007.csv", "frame_index": 0}],
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            dataset = load_extracted_odb(manifest_path)
        self.assertEqual(dataset.modes[0].coordinates.tolist(), [[0.0, 0.0, 0.0]])


class ProgressCallbackTests(unittest.TestCase):
    def test_progress_lines_are_relayed_from_the_log_while_running(self):
        process_holder = {}

        class _Process:
            def __init__(self):
                self.pid = 999
                self.returncode = None
                self._polls = 0

            def poll(self):
                self._polls += 1
                if self._polls == 1:
                    return None
                self.returncode = 0
                return 0

        def fake_popen(command, **kwargs):
            # Simulate the child process appending output to the log file
            # that abaqus_bridge already opened for the real subprocess.
            log_file = kwargs["stdout"]
            log_file.write("PROGRESS: opening ODB\nExtracted mode 7 at 1.0 Hz (1 nodes)\n")
            log_file.flush()
            process = _Process()
            process_holder["process"] = process
            return process

        seen = []
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            output.mkdir()
            (output / "manifest.json").write_text("{}", encoding="utf-8")
            with patch("abaqus_bridge.subprocess.Popen", side_effect=fake_popen):
                run_abaqus_extraction(
                    Path(directory) / "model.odb",
                    output,
                    abaqus_command="abaqus",
                    progress_callback=seen.append,
                )
        self.assertIn("opening ODB", seen)
        # Non-"PROGRESS:" lines (e.g. "Extracted mode ...") must not be
        # forwarded as phase text.
        self.assertFalse(any("Extracted mode" in line for line in seen))


if __name__ == "__main__":
    unittest.main()
