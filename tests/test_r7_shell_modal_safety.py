"""R7 / R7 R1: frequency-record consistency of extraction packages and the fail-closed shell gate of guided registration.

R7-A: the pinned extractor can record a zero-frequency frame's mode number as its frequency. The loader refuses, per
mode, a manifest frequency that contradicts the frame description, and any frame frequency that contradicts a reliable
EIGFREQ value (EIGVAL-consistent), even when the manifest and the description agree. Nothing is substituted.
R7-B: a single-z-level measured surface needs the model's FE input (INP) bound node for node; a bound conventional
shell needs a measured-face statement consistent with the element normal and the Z sign of the axes; contradictions
and mirrored axes are refused; legacy records of flat surfaces without a binding are not applied.
No Abaqus is needed.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import abaqus_bridge  # noqa: E402
from services import guided_registration as guided  # noqa: E402
from services import shell_surface  # noqa: E402
from services.shape_extraction import PINNED_EXTRACT_SCRIPT, PINNED_EXTRACT_SCRIPT_SHA256  # noqa: E402
from r7_support import synthetic_fe_input, synthetic_inp_text  # noqa: E402
from test_guided_registration import IDENTITY, _World, as_dataset, evidence_document  # noqa: E402

sys.modules.setdefault("odbAccess", types.SimpleNamespace(openOdb=lambda *a, **k: None))
_spec = importlib.util.spec_from_file_location("extract_odb_r7", ROOT / "abaqus_scripts" / "extract_odb.py")
extractor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(extractor)

ZERO = "Mode         1: Value = -7.10220E-05 Freq =   0.0000     (cycles/time)"
TINY = "Mode         3: Value =  1.88141E-06 Freq =  2.18304E-04 (cycles/time)"
ELASTIC = "Mode         7: Value =   14360.     Freq =   19.072     (cycles/time)"
LF_BLOB_SHA256 = "043e89e19d92463ae2223e6ecd766682d2495a5915f210f2641961b8bf6804f5"


class Frame:
    def __init__(self, frequency, frame_value, description, mode=None):
        self.frequency, self.frameValue, self.description, self.mode = frequency, frame_value, description, mode


class PinnedExtractor(unittest.TestCase):
    def _content(self):
        return (ROOT / PINNED_EXTRACT_SCRIPT).read_bytes().replace(b"\r\n", b"\n")

    def test_pinned_script_content_is_unchanged(self):
        # The pin is a CRLF hash (OPEN DECISION OD-R7-1, see R7_SHELL_MODAL_SAFETY.md): the content is compared with
        # CRLF line endings so this test runs on any checkout; the runtime pin itself is not changed.
        crlf = hashlib.sha256(self._content().replace(b"\n", b"\r\n")).hexdigest()
        self.assertEqual(crlf, PINNED_EXTRACT_SCRIPT_SHA256)

    def test_open_decision_the_pin_does_not_match_the_lf_blob(self):
        # Recorded, not hidden: on an LF checkout (Linux CI) pinned_script_executor would refuse the unchanged script.
        self.assertEqual(hashlib.sha256(self._content()).hexdigest(), LF_BLOB_SHA256)
        self.assertNotEqual(LF_BLOB_SHA256, PINNED_EXTRACT_SCRIPT_SHA256)

    def test_root_cause_zero_frequency_falls_back_to_the_mode_number(self):
        self.assertEqual(extractor.frame_frequency(Frame(0.0, 1.0, ZERO, 1)), 1.0)
        self.assertEqual(extractor.frame_frequency(Frame(19.072, 7.0, ELASTIC, 7)), 19.072)


class DescribedFrequency(unittest.TestCase):
    def test_parses_abaqus_frame_descriptions(self):
        self.assertEqual(abaqus_bridge.described_frequency(ZERO)[0], 0.0)
        self.assertAlmostEqual(abaqus_bridge.described_frequency(ZERO)[1], 5e-5)
        self.assertAlmostEqual(abaqus_bridge.described_frequency(TINY)[0], 2.18304e-4)
        self.assertEqual(abaqus_bridge.described_frequency(ELASTIC)[0], 19.072)
        self.assertIsNone(abaqus_bridge.described_frequency("Increment 0: Base State"))


class FrequencyRecordConsistency(unittest.TestCase):
    problem = staticmethod(abaqus_bridge.manifest_frequency_problem)

    def test_all_records_agree(self):
        self.assertIsNone(self.problem(7, 19.072, ELASTIC, {7: 19.07217025756836}))
        self.assertIsNone(self.problem(3, 0.000218304, TINY, {3: 2.1830420882906765e-4}))

    def test_manifest_and_description_agree_but_eigfreq_contradicts_is_refused(self):
        item = self.problem(7, 19.072, ELASTIC, {7: 21.5})
        self.assertIn("contradicts EIGFREQ", item["reason"])
        self.assertIsNone(item["independent_records_agree_on_hz"])

    def test_zero_frequency_recorded_as_mode_number_is_refused(self):
        item = self.problem(1, 1.0, ZERO, {1: 0.0})
        self.assertIn("mode number", item["reason"])
        self.assertEqual(item["independent_records_agree_on_hz"], 0.0)

    def test_without_description_the_manifest_is_checked_against_eigfreq(self):
        self.assertIn("contradicts EIGFREQ", self.problem(2, 2.0, None, {2: 0.0})["reason"])
        self.assertIsNone(self.problem(13, 207.43, None, {13: 207.4272918701172}))  # within the printed precision

    def test_single_records_are_left_unchanged(self):
        self.assertIsNone(self.problem(7, 7.0, None, None))
        self.assertIsNone(self.problem(7, 19.072, ELASTIC, None))

    def test_eigval_inconsistent_eigfreq_is_not_a_reliable_record(self):
        manifest = {"history": [
            {"name": "EIGFREQ", "data": [[7.0, 19.07217025756836], [8.0, 59.8741569519043]]},
            {"name": "EIGVAL", "data": [[7.0, (2 * math.pi * 19.07217025756836) ** 2], [8.0, 1.0]]}]}
        reliable, notes = abaqus_bridge.reliable_eigfreq(manifest)
        self.assertEqual(set(reliable), {7})
        self.assertIn("EIGVAL of mode 8 contradicts", notes[8])

    def test_rigid_mode_negative_eigval_agrees_with_zero_eigfreq(self):
        reliable, notes = abaqus_bridge.reliable_eigfreq({"history": [
            {"name": "EIGFREQ", "data": [[1.0, 0.0]]}, {"name": "EIGVAL", "data": [[1.0, -7.1e-05]]}]})
        self.assertEqual(reliable, {1: 0.0})
        self.assertEqual(notes, {})


def _package(directory: Path, entries, eigfreq=None, eigval=None) -> Path:
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
    history = []
    if eigfreq is not None:
        history.append({"region": "Assembly", "name": "EIGFREQ", "data": [[k, v] for k, v in eigfreq.items()]})
    if eigval is not None:
        history.append({"region": "Assembly", "name": "EIGVAL", "data": [[k, v] for k, v in eigval.items()]})
    path = directory / "manifest.json"
    path.write_text(json.dumps({"format_version": 2, "geometry_file": "geometry.csv", "geometry_node_count": 2,
                                "odb_path": "p.odb", "step_name": "Modal", "start_mode": 1, "end_mode": 7,
                                "modes": modes, "history": history}), encoding="utf-8")
    return path


R6_EIGFREQ = {1: 0.0, 2: 0.0, 3: 2.1830420882906765e-4, 7: 19.07217025756836}
R6_EIGVAL = {1: -7.102198287611827e-05, 2: -3.0856942885293392e-06, 3: 1.8814121176546905e-06, 7: 14360.181640625}


class LoaderConsistency(unittest.TestCase):
    def test_r6_like_package_loads_elastic_modes_without_the_false_rigid_frequencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _package(Path(tmp), [(1, 1.0, ZERO), (2, 2.0, ZERO.replace("1:", "2:")), (3, 0.000218304, TINY),
                                        (7, 19.072, ELASTIC)], R6_EIGFREQ, R6_EIGVAL)
            dataset = abaqus_bridge.load_extracted_odb(path)
        self.assertEqual([m.number for m in dataset.sorted_modes()], [3, 7])
        frequencies = [m.frequency_hz for m in dataset.sorted_modes()]
        self.assertNotIn(1.0, frequencies)
        self.assertNotIn(2.0, frequencies)
        self.assertEqual(frequencies[1], 19.07217025756836)  # the elastic value is kept (EIGFREQ refinement)
        self.assertEqual(sorted(dataset.metadata["rejected_frequency_modes"]), ["1", "2"])

    def test_agreeing_manifest_and_description_against_eigfreq_is_refused_on_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _package(Path(tmp), [(3, 0.000218304, TINY), (7, 19.072, ELASTIC)], {**R6_EIGFREQ, 7: 21.5})
            dataset = abaqus_bridge.load_extracted_odb(path)
        self.assertEqual([m.number for m in dataset.sorted_modes()], [3])
        self.assertIn("contradicts EIGFREQ", dataset.metadata["rejected_frequency_modes"]["7"]["reason"])

    def test_correct_old_packages_are_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _package(Path(tmp), [(3, 0.000218304, TINY), (7, 19.072, ELASTIC)])
            dataset = abaqus_bridge.load_extracted_odb(path)
        self.assertEqual([m.frequency_hz for m in dataset.sorted_modes()], [0.000218304, 19.072])
        self.assertNotIn("rejected_frequency_modes", dataset.metadata)

    def test_a_package_with_only_false_frequencies_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError) as caught:
                abaqus_bridge.load_extracted_odb(_package(Path(tmp), [(1, 1.0, ZERO)], {1: 0.0}))
        self.assertIn("no usable modes", str(caught.exception))


class FEInputParsingAndBinding(_World, unittest.TestCase):
    def test_element_types_and_normals(self):
        model = synthetic_fe_input(self.variant, element_type="S4R")
        item = model.instance("top")
        self.assertEqual(item.element_types, ("S4R",))
        self.assertGreater(item.normal_counts["+Z"], 0)
        self.assertEqual(item.normal_counts["-Z"], 0)
        flipped = synthetic_fe_input(self.variant, element_type="S4R", normal="-Z").instance("TOP")
        self.assertEqual(flipped.normal_counts["+Z"], 0)
        self.assertFalse(shell_surface.is_conventional_shell("SC8R"))
        self.assertTrue(shell_surface.is_conventional_shell("STRI65"))

    def test_binding_is_node_for_node(self):
        fe = guided.fe_geometry_of(as_dataset(self.variant))
        binding = shell_surface.bind_fe_input(synthetic_fe_input(self.variant, element_type="S4R"), fe, "TOP", "mm")
        self.assertEqual((binding.kind, binding.normal_direction), ("shell", "+Z"))
        solid = shell_surface.bind_fe_input(synthetic_fe_input(self.variant), fe, "TOP", "mm")
        self.assertEqual(solid.kind, "non_shell")
        for bad in (synthetic_fe_input(self.variant, shift=0.01), synthetic_fe_input(self.variant, rotated=True),
                    synthetic_fe_input(self.variant, instance="BOT")):
            with self.assertRaises(shell_surface.ShellSurfaceRefusal):
                shell_surface.bind_fe_input(bad, fe, "TOP", "mm")

    def test_flat_geometry_is_not_a_shell_claim(self):
        fe = guided.fe_geometry_of(as_dataset(self.variant))
        self.assertTrue(shell_surface.surface_is_degenerate(fe, "TOP", "mm"))


def _shell_document(test, fe_input, **face):
    document = evidence_document(dict(test.frame))
    document["shell_measured_face"] = {"schema": shell_surface.SHELL_FACE_SCHEMA, "fe_instance": "TOP",
                                       "fe_input_sha256": fe_input.sha256, "normal_direction": "+Z",
                                       "measured_face": "positive_normal",
                                       "face_evidence": "owner statement and photograph of the scanned face", **face}
    return document


class GuidedShellGate(_World, unittest.TestCase):
    def build(self, document=None, fe_input="bound solid"):
        evidence = guided.evidence_from_document(document or evidence_document(dict(self.frame)))
        return self.establish(evidence=evidence, fe_input=fe_input)

    def refused(self, field, **kwargs):
        with self.assertRaises(guided.GuidedRegistrationRefusal) as caught:
            self.build(**kwargs)
        self.assertEqual(caught.exception.field, field, str(caught.exception))
        return str(caught.exception)

    def test_flat_surface_of_unknown_type_is_refused(self):
        self.assertIn("single z level", self.refused("fe_input", fe_input=None))

    def test_bound_non_shell_keeps_the_existing_registration(self):
        result = self.build()
        self.assertTrue(result.metrics["fe_input"]["bound"])
        self.assertEqual(result.metrics["fe_input"]["kind"], "non_shell")
        self.assertFalse(result.provenance()["governed"])
        self.assertFalse(result.provenance()["production_ready"])

    def test_confirmed_shell_without_measured_face_is_refused(self):
        shell = synthetic_fe_input(self.variant, element_type="S4R")
        self.assertIn("conventional shell", self.refused("shell_measured_face", fe_input=shell))

    def test_confirmed_shell_with_consistent_face_passes(self):
        shell = synthetic_fe_input(self.variant, element_type="S4R")
        result = self.build(_shell_document(self, shell), fe_input=shell)
        record = result.metrics["fe_input"]
        self.assertEqual((record["kind"], record["normal_direction"]), ("shell", "+Z"))
        self.assertEqual(record["shell_measured_face"]["measured_face"], "positive_normal")
        self.assertIn("shell_measured_face", result.evidence)
        self.assertFalse(result.provenance()["governed"])

    def test_wrong_normal_direction_is_refused(self):
        shell = synthetic_fe_input(self.variant, element_type="S4R")
        self.refused("shell_measured_face", document=_shell_document(self, shell, normal_direction="-Z"),
                     fe_input=shell)

    def test_face_contradicting_the_axes_z_sign_is_refused(self):
        shell = synthetic_fe_input(self.variant, element_type="S4R")
        text = self.refused("orientation.experimental_axes_in_fe",
                            document=_shell_document(self, shell, measured_face="negative_normal"), fe_input=shell)
        self.assertIn("must map to -Z", text)

    def test_statement_for_another_fe_input_is_refused(self):
        shell = synthetic_fe_input(self.variant, element_type="S4R")
        self.refused("shell_measured_face", document=_shell_document(self, shell, fe_input_sha256="c" * 64),
                     fe_input=shell)

    def test_shell_statement_for_a_non_shell_is_refused(self):
        shell = synthetic_fe_input(self.variant, element_type="S4R")
        self.refused("shell_measured_face", document=_shell_document(self, shell))  # bound solid INP

    def test_non_uniform_normals_are_refused(self):
        shell = synthetic_fe_input(self.variant, element_type="S4R")
        item = shell.instance("TOP")
        mixed = shell_surface.FEInputModel(shell.file_name, shell.sha256, shell.size_bytes, {"TOP": type(item)(
            item.name, item.part, item.translation, item.rotated, item.nodes, item.element_types,
            {"+Z": 3, "-Z": 1, "in_plane": 0})})
        self.refused("shell_measured_face", document=_shell_document(self, shell), fe_input=mixed)

    def test_mirrored_axes_are_refused(self):
        shell = synthetic_fe_input(self.variant, element_type="S4R")
        document = _shell_document(self, shell)
        document["geometry_calibration"]["orientation"] = {"experimental_axes_in_fe": ["+X", "-Y", "+Z"],
                                                           "reference": "corner_A_marker", "source": "photo"}
        self.refused("orientation.experimental_axes_in_fe", document=document, fe_input=shell)

    def test_invalid_shell_block_is_refused_when_loaded(self):
        document = evidence_document(dict(self.frame))
        document["shell_measured_face"] = {"schema": shell_surface.SHELL_FACE_SCHEMA, "fe_instance": "TOP"}
        with self.assertRaises(guided.GuidedRegistrationRefusal) as caught:
            guided.evidence_from_document(document)
        self.assertEqual(caught.exception.field, "shell_measured_face")

    def test_pre_r7_evidence_hash_is_unchanged(self):
        evidence = guided.evidence_from_document(evidence_document(dict(self.frame)))
        self.assertNotIn("shell_measured_face", evidence.document())

    def test_saved_records_of_flat_surfaces_need_the_binding(self):
        result = self.build()
        dataset = as_dataset(self.variant)
        guided.verify_for_files(result, dataset, self.experimental, IDENTITY)  # bound: applied
        legacy = copy.copy(result)
        object.__setattr__(legacy, "metrics", {k: v for k, v in result.metrics.items() if k != "fe_input"})
        with self.assertRaises(guided.GuidedRegistrationRefusal) as caught:
            guided.verify_for_files(legacy, dataset, self.experimental, IDENTITY)
        self.assertEqual(caught.exception.field, "fe_input")


if __name__ == "__main__":
    unittest.main()
