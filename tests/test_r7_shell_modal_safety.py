"""R7: zero-frequency safety of extraction packages and the shell mid-surface guard of guided registration.

R7-A: the pinned extractor can record a zero-frequency frame's mode number as its frequency; the loader rejects a
manifest frequency contradicted by the frame description or the EIGFREQ history, records why, and never substitutes a
value. R7-B: a confirmed conventional shell cannot be registered through ``measured_surface.side``; a degenerate
measured surface of unknown element type carries a stated limitation; solid registrations are unchanged.
No Abaqus is needed.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import abaqus_bridge  # noqa: E402
from scientific_state import fe_geometry_identity  # noqa: E402
from services import guided_registration as guided  # noqa: E402
from services import shell_surface  # noqa: E402
from services.physical_registration import FEGeometry  # noqa: E402
from services.shape_extraction import PINNED_EXTRACT_SCRIPT, PINNED_EXTRACT_SCRIPT_SHA256  # noqa: E402
from test_guided_registration import _World  # noqa: E402

sys.modules.setdefault("odbAccess", types.SimpleNamespace(openOdb=lambda *a, **k: None))
_spec = importlib.util.spec_from_file_location("extract_odb_r7", ROOT / "abaqus_scripts" / "extract_odb.py")
extractor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(extractor)

ZERO = "Mode         1: Value = -7.10220E-05 Freq =   0.0000     (cycles/time)"
TINY = "Mode         3: Value =  1.88141E-06 Freq =  2.18304E-04 (cycles/time)"
ELASTIC = "Mode         7: Value =   14360.     Freq =   19.072     (cycles/time)"


class Frame:
    def __init__(self, frequency, frame_value, description, mode=None):
        self.frequency, self.frameValue, self.description, self.mode = frequency, frame_value, description, mode


class PinnedExtractorRootCause(unittest.TestCase):
    def test_pinned_script_is_unchanged(self):
        sha = hashlib.sha256((ROOT / PINNED_EXTRACT_SCRIPT).read_bytes()).hexdigest()
        self.assertEqual(sha, PINNED_EXTRACT_SCRIPT_SHA256)

    def test_zero_frequency_frame_falls_back_to_the_mode_number(self):
        # Root cause, documented: `frequency == 0` is treated as missing and `frameValue` (the mode number in a
        # frequency step) is written as the frequency. The loader below is the guard; the pinned script is unchanged.
        self.assertEqual(extractor.frame_frequency(Frame(0.0, 1.0, ZERO, 1)), 1.0)
        self.assertEqual(extractor.frame_frequency(Frame(19.072, 7.0, ELASTIC, 7)), 19.072)


class DescribedFrequency(unittest.TestCase):
    def test_parses_abaqus_frame_descriptions(self):
        self.assertEqual(abaqus_bridge.described_frequency(ZERO)[0], 0.0)
        self.assertAlmostEqual(abaqus_bridge.described_frequency(ZERO)[1], 5e-5)
        self.assertAlmostEqual(abaqus_bridge.described_frequency(TINY)[0], 2.18304e-4)
        self.assertEqual(abaqus_bridge.described_frequency(ELASTIC)[0], 19.072)
        self.assertIsNone(abaqus_bridge.described_frequency("Increment 0: Base State"))
        self.assertIsNone(abaqus_bridge.described_frequency(None))


class ManifestFrequencyProblem(unittest.TestCase):
    problem = staticmethod(abaqus_bridge.manifest_frequency_problem)

    def test_zero_frequency_recorded_as_mode_number_is_rejected_with_the_independent_value(self):
        item = self.problem(1, 1.0, ZERO, {1: 0.0})
        self.assertIn("mode number", item["reason"])
        self.assertEqual(item["described_frequency_hz"], 0.0)
        self.assertEqual(item["eigfreq_hz"], 0.0)
        self.assertEqual(item["independent_records_agree_on_hz"], 0.0)

    def test_near_zero_and_elastic_values_are_consistent(self):
        self.assertIsNone(self.problem(3, 0.000218304, TINY, {3: 0.000218304}))
        self.assertIsNone(self.problem(7, 19.072, ELASTIC, {7: 19.07217}))

    def test_without_description_the_mode_number_artifact_is_caught_by_eigfreq(self):
        item = self.problem(2, 2.0, None, {2: 0.0})
        self.assertIn("contradicts EIGFREQ", item["reason"])

    def test_unverifiable_legacy_values_are_left_unchanged(self):
        self.assertIsNone(self.problem(7, 7.0, None, None))
        self.assertIsNone(self.problem(7, 7.0, None, {7: 7.0}))

    def test_any_contradicted_value_is_rejected_and_records_disagreement(self):
        item = self.problem(7, 5.5, ELASTIC, {7: 30.0})
        self.assertNotIn("mode number", item["reason"])
        self.assertIsNone(item["independent_records_agree_on_hz"])


def _package(directory: Path, entries, history=True) -> Path:
    nodes = [("PLATE-1", 1, 0.0, 0.0, 0.0), ("PLATE-1", 2, 1.0, 0.0, 0.0)]
    with open(directory / "geometry.csv", "w", newline="") as stream:
        writer = csv.writer(stream); writer.writerow(["instance", "node_label", "x", "y", "z"]); writer.writerows(nodes)
    modes = []
    for mode, frequency, description in entries:
        name = f"mode_{mode:04d}.csv"
        with open(directory / name, "w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["instance", "node_label", "u1_real", "u2_real", "u3_real", "u1_imag", "u2_imag", "u3_imag"])
            for instance, label, *_ in nodes:
                writer.writerow([instance, label, 0, 0, float(label), 0, 0, 0])
        modes.append({"mode": mode, "frequency_hz": frequency, "frame_index": mode, "description": description,
                      "file": name, "node_count": 2})
    eig = {1: 0.0, 2: 0.0, 3: 2.1830420882906765e-4, 7: 19.07217025756836}
    manifest = {"format_version": 2, "geometry_file": "geometry.csv", "geometry_node_count": 2, "odb_path": "p.odb",
                "step_name": "Modal", "start_mode": 1, "end_mode": 7, "modes": modes,
                "history": ([{"region": "Assembly", "name": "EIGFREQ", "data": [[k, v] for k, v in eig.items()]}]
                            if history else [])}
    path = directory / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


class LoaderRejectsFalseFrequencies(unittest.TestCase):
    def test_r6_like_package_loads_without_the_false_rigid_frequencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _package(Path(tmp), [(1, 1.0, ZERO), (2, 2.0, ZERO.replace("1:", "2:")), (3, 0.000218304, TINY),
                                        (7, 19.072, ELASTIC)])
            dataset = abaqus_bridge.load_extracted_odb(path)
        numbers = [mode.number for mode in dataset.sorted_modes()]
        frequencies = [mode.frequency_hz for mode in dataset.sorted_modes()]
        self.assertEqual(numbers, [3, 7])
        self.assertNotIn(1.0, frequencies)
        self.assertNotIn(2.0, frequencies)
        self.assertAlmostEqual(frequencies[1], 19.07217025756836)
        rejected = dataset.metadata["rejected_frequency_modes"]
        self.assertEqual(sorted(rejected), ["1", "2"])
        self.assertEqual(rejected["1"]["independent_records_agree_on_hz"], 0.0)

    def test_a_package_with_only_false_frequencies_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _package(Path(tmp), [(1, 1.0, ZERO)])
            with self.assertRaises(ValueError) as caught:
                abaqus_bridge.load_extracted_odb(path)
        self.assertIn("no usable modes", str(caught.exception))

    def test_a_correct_package_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _package(Path(tmp), [(3, 0.000218304, TINY), (7, 19.072, ELASTIC)], history=False)
            dataset = abaqus_bridge.load_extracted_odb(path)
        self.assertEqual([m.frequency_hz for m in dataset.sorted_modes()], [0.000218304, 19.072])
        self.assertNotIn("rejected_frequency_modes", dataset.metadata)


SHELL_INP = """*Heading
*Part, name=PLATE
*Node
      1,   0.,   0.,   0.
      2,  10.,   0.,   0.
      3,  10.,  10.,   0.
      4,   0.,  10.,   0.
*Element, type=S4R
1, 1, 2, 3, 4
*End Part
*Part, name=BLOCK
*Node
1, 0., 0., 0.
*Element, type=C3D8I
1, 1, 1, 1, 1, 1, 1, 1, 1
*End Part
*Assembly, name=Assembly
*Instance, name=PLATE-1, part=PLATE
*End Instance
*Instance, name=TILTED-1, part=PLATE
 1., 0., 0.
 0., 0., 0., 1., 0., 0., 30.
*End Instance
*Instance, name=TOP, part=BLOCK
*End Instance
*End Assembly
"""


class InpElementSummaryTests(unittest.TestCase):
    def test_element_types_and_normals_per_instance(self):
        summary = shell_surface.inp_element_summary(SHELL_INP)
        self.assertEqual(summary.instance_element_types["PLATE-1"], ("S4R",))
        self.assertEqual(summary.instance_normal_z_counts["PLATE-1"], {"+Z": 1, "-Z": 0, "in_plane": 0})
        self.assertEqual(summary.instance_normal_z_counts["TILTED-1"], {"unknown": "rotated instance"})
        self.assertTrue(summary.shell_confirmed("plate-1"))
        self.assertFalse(summary.shell_confirmed("TOP"))
        self.assertIsNone(summary.shell_confirmed("ABSENT"))

    def test_continuum_shells_are_not_mid_surface_shells(self):
        self.assertTrue(shell_surface.is_conventional_shell("S4R"))
        self.assertTrue(shell_surface.is_conventional_shell("STRI65"))
        self.assertFalse(shell_surface.is_conventional_shell("SC8R"))
        self.assertFalse(shell_surface.is_conventional_shell("C3D8I"))

    def test_equal_z_is_detected_but_is_not_a_shell_claim(self):
        flat = FEGeometry(np.array(["P:1", "P:2"]), np.array([[0.0, 0, 0], [1.0, 0, 0]]),
                          fe_geometry_identity(["P:1", "P:2"], np.array([[0.0, 0, 0], [1.0, 0, 0]])))
        thick = FEGeometry(np.array(["P:1", "P:2"]), np.array([[0.0, 0, 0], [0.0, 0, 0.4]]),
                           fe_geometry_identity(["P:1", "P:2"], np.array([[0.0, 0, 0], [0.0, 0, 0.4]])))
        self.assertTrue(shell_surface.surface_is_degenerate(flat, "P", "mm"))
        self.assertFalse(shell_surface.surface_is_degenerate(thick, "P", "mm"))


def _summary_for(instance: str, element_type: str) -> shell_surface.InpElementSummary:
    return shell_surface.InpElementSummary("b" * 64, {instance: (element_type,)}, {instance: {"+Z": 1}})


class GuidedShellGuard(_World, unittest.TestCase):
    def test_confirmed_shell_is_refused(self):
        with self.assertRaises(guided.GuidedRegistrationRefusal) as caught:
            guided.establish_guided_registration(*self._args(), fe_element_summary=_summary_for("TOP", "S4R"))
        self.assertEqual(caught.exception.field, "measured_surface")
        self.assertIn("conventional shell", str(caught.exception))

    def test_degenerate_surface_of_unknown_type_states_the_limitation(self):
        result = guided.establish_guided_registration(*self._args())
        self.assertTrue(any("max_z and min_z select the same nodes" in w and "a shell is not excluded" in w
                            for w in result.warnings))
        self.assertFalse(result.provenance()["governed"])
        self.assertFalse(result.provenance()["production_ready"])

    def test_solid_element_types_keep_the_registration(self):
        plain = guided.establish_guided_registration(*self._args())
        solid = guided.establish_guided_registration(*self._args(), fe_element_summary=_summary_for("TOP", "C3D8I"))
        self.assertEqual(solid.registration.registration_hash, plain.registration.registration_hash)
        self.assertTrue(any("not a conventional shell" in w for w in solid.warnings))

    def test_mirrored_axes_are_still_refused(self):
        evidence = self.evidence(orientation={"experimental_axes_in_fe": ["+X", "-Y", "+Z"],
                                              "reference": "corner_A_marker", "source": "photo"})
        args = list(self._args()); args[3] = evidence
        with self.assertRaises(guided.GuidedRegistrationRefusal) as caught:
            guided.establish_guided_registration(*args)
        self.assertEqual(caught.exception.field, "orientation.experimental_axes_in_fe")

    def _args(self):
        from test_guided_registration import IDENTITY, as_dataset
        return as_dataset(self.variant), self.experimental, IDENTITY, self.evidence()


if __name__ == "__main__":
    unittest.main()
