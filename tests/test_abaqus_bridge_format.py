from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

import abaqus_bridge  # noqa: E402
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


NODES = (("PART-1", 1, 0.0, 0.0, 0.0), ("PART-1", 2, 1.0, 0.0, 0.0), ("PART-1", 3, 1.0, 2.0, 0.0),
         ("SKIN-1", 1, 0.0, 2.0, 0.5))
MODE_HEADER = ["instance", "node_label", "u1_real", "u2_real", "u3_real", "u1_imag", "u2_imag", "u3_imag"]


def write_package(root: Path, version: int, modes) -> Path:
    """An extracted package of ``modes`` = [(number, nodes), ...]; each node is (instance, label, x, y, z). The
    displacement of a node depends on the mode and on the node's label, so every mode has vectors of its own."""
    manifest = {"format_version": version, "step_name": "Step-1", "modes": []}
    if version >= 2:
        known = {}
        for _number, nodes in modes:
            for node in nodes:
                known.setdefault(node[:2], node)
        _write_csv(root / "geometry.csv", ["instance", "node_label", "x", "y", "z"], list(known.values()))
        manifest["geometry_file"] = "geometry.csv"
    for number, nodes in modes:
        rows = []
        for instance, label, x, y, z in nodes:
            values = [number + 0.1 * label, number - 0.1 * label, 0.01 * number * label, 0, 0, 0]
            rows.append([instance, label] + ([x, y, z] if version < 2 else []) + values)
        header = MODE_HEADER if version >= 2 else MODE_HEADER[:2] + ["x", "y", "z"] + MODE_HEADER[2:]
        _write_csv(root / f"mode_{number:04d}.csv", header, rows)
        manifest["modes"].append({"mode": number, "frequency_hz": 10.0 * number, "file": f"mode_{number:04d}.csv",
                                  "frame_index": number})
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def parsed_alone(manifest_path: Path):
    """Every mode of the package parsed on its own by ``_load_mode_csv``: what the loader held before any sharing."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    geometry = None
    if int(manifest.get("format_version", 1)) >= 2:
        geometry = abaqus_bridge._load_geometry_csv(manifest_path.parent / manifest["geometry_file"])
    return [abaqus_bridge._load_mode_csv(manifest_path.parent / entry["file"], int(entry["mode"]),
                                         float(entry["frequency_hz"]), {}, geometry) for entry in manifest["modes"]]


class SharedGeometryTests(unittest.TestCase):
    """SP13-SHARED-FE-GEOMETRY-01: modes with exactly the same geometry use one node-id array and one coordinate
    array; every value the loader returns is the value it returned before."""

    def load(self, version, modes):
        with tempfile.TemporaryDirectory() as directory:
            path = write_package(Path(directory), version, modes)
            return load_extracted_odb(path), parsed_alone(path)

    def assert_values_unchanged(self, dataset, alone):
        self.assertEqual([mode.number for mode in dataset.modes], [mode.number for mode in alone])
        for mode, reference in zip(dataset.modes, alone):
            self.assertEqual(mode.frequency_hz, reference.frequency_hz)
            self.assertEqual(mode.node_ids.dtype, object)
            self.assertEqual(mode.node_ids.tolist(), reference.node_ids.tolist())
            self.assertEqual(mode.coordinates.dtype, reference.coordinates.dtype)
            self.assertEqual(mode.coordinates.tobytes(), reference.coordinates.tobytes())
            self.assertEqual(mode.vectors.dtype, reference.vectors.dtype)
            self.assertEqual(mode.vectors.tobytes(), reference.vectors.tobytes())
            self.assertEqual(mode.measured_dofs.tolist(), reference.measured_dofs.tolist())

    def test_the_parser_alone_repeats_the_geometry_in_every_mode(self):
        for version in (1, 2):
            with self.subTest(format_version=version), tempfile.TemporaryDirectory() as directory:
                alone = parsed_alone(write_package(Path(directory), version, [(n, NODES) for n in (1, 2, 3)]))
                self.assertEqual(len({id(mode.node_ids) for mode in alone}), 3)
                self.assertEqual(len({id(mode.coordinates) for mode in alone}), 3)
                self.assertIsNot(alone[0].node_ids[0], alone[1].node_ids[0])  # even the id strings are repeated

    def test_identical_geometry_is_one_pair_of_arrays_in_both_formats(self):
        for version in (1, 2):
            with self.subTest(format_version=version):
                dataset, alone = self.load(version, [(n, NODES) for n in (1, 2, 3)])
                first = dataset.modes[0]
                for mode in dataset.modes[1:]:
                    self.assertIs(mode.node_ids, first.node_ids)
                    self.assertIs(mode.coordinates, first.coordinates)
                self.assertEqual(len(dataset.modes), 3)
                self.assert_values_unchanged(dataset, alone)

    def test_vectors_and_masks_are_never_shared(self):
        dataset, _alone = self.load(2, [(n, NODES) for n in (1, 2, 3)])
        for name in ("vectors", "measured_dofs"):
            arrays = [getattr(mode, name) for mode in dataset.modes]
            self.assertEqual(len({id(array) for array in arrays}), 3)
            self.assertFalse(np.shares_memory(arrays[0], arrays[1]))
            self.assertTrue(all(array.flags.writeable for array in arrays))
        dataset.modes[1].vectors[0, 0] = 99.0
        dataset.modes[1].measured_dofs[0, 0] = False
        self.assertNotEqual(dataset.modes[0].vectors[0, 0], 99.0)
        self.assertTrue(dataset.modes[0].measured_dofs[0, 0])

    def test_shared_arrays_reject_writes(self):
        dataset, _alone = self.load(2, [(n, NODES) for n in (1, 2)])
        for mode in dataset.modes:
            with self.assertRaises(ValueError):
                mode.node_ids[0] = "OTHER:1"
            with self.assertRaises(ValueError):
                mode.coordinates[0, 0] = 5.0
        self.assertEqual(dataset.modes[0].node_ids[0], "PART-1:1")
        self.assertEqual(dataset.modes[0].coordinates[0, 0], 0.0)

    def test_a_different_node_order_is_never_shared(self):
        reordered = (NODES[1], NODES[0]) + NODES[2:]
        for version in (1, 2):
            with self.subTest(format_version=version):
                dataset, alone = self.load(version, [(1, NODES), (2, reordered), (3, NODES)])
                one, two, three = dataset.modes
                self.assertIsNot(two.node_ids, one.node_ids)
                self.assertIsNot(two.coordinates, one.coordinates)
                self.assertFalse(np.shares_memory(two.coordinates, one.coordinates))
                self.assertEqual(two.node_ids.tolist()[:2], ["PART-1:2", "PART-1:1"])
                self.assertTrue(two.node_ids.flags.writeable and two.coordinates.flags.writeable)
                self.assertIs(three.node_ids, one.node_ids)  # a later mode still finds the geometry it equals
                self.assertIs(three.coordinates, one.coordinates)
                self.assert_values_unchanged(dataset, alone)

    def test_different_coordinates_are_never_shared(self):
        moved = NODES[:3] + (("SKIN-1", 1, 0.0, 2.0, 0.5000000000000001),)
        signed_zero = (("PART-1", 1, "-0.0", 0.0, 0.0),) + NODES[1:]
        for label, other in (("one ulp", moved), ("minus zero", signed_zero)):
            with self.subTest(difference=label):
                dataset, alone = self.load(1, [(1, NODES), (2, other)])
                one, two = dataset.modes
                self.assertEqual(one.node_ids.tolist(), two.node_ids.tolist())
                self.assertIsNot(two.node_ids, one.node_ids)
                self.assertIsNot(two.coordinates, one.coordinates)
                self.assertTrue(one.coordinates.flags.writeable and two.coordinates.flags.writeable)
                self.assert_values_unchanged(dataset, alone)

    def test_a_different_node_count_is_never_shared(self):
        dataset, alone = self.load(2, [(1, NODES), (2, NODES[:3])])
        self.assertEqual([len(mode.node_ids) for mode in dataset.modes], [4, 3])
        self.assertIsNot(dataset.modes[1].coordinates, dataset.modes[0].coordinates)
        self.assert_values_unchanged(dataset, alone)

    def test_a_single_mode_keeps_writable_arrays(self):
        dataset, _alone = self.load(2, [(7, NODES)])
        self.assertTrue(dataset.modes[0].node_ids.flags.writeable)
        self.assertTrue(dataset.modes[0].coordinates.flags.writeable)

    def test_sharing_a_loaded_list_again_changes_nothing(self):
        dataset, alone = self.load(2, [(n, NODES) for n in (1, 2, 3)])
        before = [(id(mode.node_ids), id(mode.coordinates)) for mode in dataset.modes]
        self.assertEqual(abaqus_bridge.share_equal_geometry(dataset.modes), 2)
        self.assertEqual([(id(mode.node_ids), id(mode.coordinates)) for mode in dataset.modes], before)
        self.assert_values_unchanged(dataset, alone)

    def test_a_stop_request_still_ends_the_load(self):
        import threading
        stop = threading.Event()
        stop.set()
        with tempfile.TemporaryDirectory() as directory:
            path = write_package(Path(directory), 2, [(n, NODES) for n in (1, 2)])
            with self.assertRaises(abaqus_bridge.AnalysisCancelled):
                load_extracted_odb(path, cancel_event=stop)


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
