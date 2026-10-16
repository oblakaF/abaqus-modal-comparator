"""CORE-E2E-C: guided physical registration of a new FE mesh (synthetic control T4; no Abaqus, no data store).

- the guided path is the accepted M2.3 builder: on the reference mesh it gives the builder's registration hash;
- a new mesh in the same FE frame (other node identity) gets its own registration with the known true mapping;
- refusals: wrong orientation (corner-A marker), mirrored axes, another FE frame, another experimental file or modal
  set, measured-DOF mismatch, a non-physical calibration, missing FE frame evidence;
- a saved registration reopens only for the exact files; the worker applies it or refuses, never substitutes;
- the MEAN MAC card states what it averages.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from m2_support import experiment, fixture_for, passport_dict, passport_for, synthetic_fe  # noqa: E402
from modal_core import ModalDataset, ModeShape  # noqa: E402
from scientific_state import fe_geometry_identity  # noqa: E402
from services import guided_registration as guided  # noqa: E402
from services.physical_registration import FEGeometry, build_physical_registration  # noqa: E402
from test_physical_registration import true_top_ids  # noqa: E402

IDENTITY = {"sha256": "a" * 64, "size": 4096}


def mesh_variant(fe: FEGeometry) -> FEGeometry:
    """The same skins and frame, a refined core (more nodes inside the same core bounding box)."""
    core = np.array([value.startswith("CORE:") for value in fe.node_ids])
    extra = fe.coordinates[core][:-1] + np.diff(fe.coordinates[core], axis=0) / 2.0  # mid-points, same bbox
    labels = [f"CORE:{100000 + k}" for k in range(len(extra))]
    ids = np.concatenate([fe.node_ids, np.array(labels)])
    coordinates = np.vstack([fe.coordinates, extra])
    return FEGeometry(ids, coordinates, fe_geometry_identity(ids.tolist(), coordinates))


def guided_boxes(fe: FEGeometry) -> dict:
    instances = np.array([value.split(":")[0] for value in fe.node_ids])
    boxes = {}
    for name in sorted(set(instances.tolist())):
        points = fe.coordinates[instances == name]
        boxes[name] = (tuple(points.min(axis=0)), tuple(points.max(axis=0)))
    return boxes


def as_dataset(fe: FEGeometry) -> ModalDataset:
    rng = np.random.default_rng(1)
    modes = [ModeShape(n, 10.0 * n, fe.node_ids.astype(object), fe.coordinates, rng.normal(size=(len(fe.node_ids), 3)))
             for n in (7, 8)]
    return ModalDataset("FE", Path("plate.odb"), modes)


def evidence_document(fe_frame: dict, **calibration_overrides) -> dict:
    calibration = copy.deepcopy(passport_dict()["geometry_calibration"])
    for key, value in calibration_overrides.items():
        calibration[key] = value
    return {"schema": guided.EVIDENCE_SCHEMA, "label": "synthetic corner-A photograph", "physical_specimen_id": "P-1",
            "experimental_source": {"name": "synthetic.unv", **IDENTITY}, "modal_set": "set-a",
            "measured_dofs": ["U3"], "point_count": 20, "fe_frame": fe_frame, "geometry_calibration": calibration}


class _World:
    def setUp(self) -> None:
        self.reference = synthetic_fe("mm")
        self.variant = mesh_variant(self.reference)
        self.experimental = experiment()
        self.surface = guided.measured_surface_identity(self.reference.node_ids, self.reference.coordinates, "TOP",
                                                        "max_z", "mm")
        self.frame = {"measured_surface_identity": {"sha256": self.surface["sha256"],
                                                    "node_count": self.surface["node_count"]}}

    def evidence(self, **overrides) -> guided.PhysicalEvidence:
        return guided.evidence_from_document(evidence_document(dict(self.frame), **overrides))

    def establish(self, fe=None, evidence=None, identity=None, experimental=None):
        return guided.establish_guided_registration(as_dataset(fe or self.variant), experimental or self.experimental,
                                                    identity or IDENTITY, evidence or self.evidence())


class GuidedRegistrationTests(_World, unittest.TestCase):
    def test_the_guided_path_is_the_accepted_m2_builder(self):
        fixture = fixture_for(self.reference)
        built = build_physical_registration(passport_for(self.reference), roots={}, fe_geometry=self.reference,
                                            experimental=(self.experimental, fixture))
        source = fixture.experimental_source
        document = evidence_document({"fe_geometry_identity": dict(self.reference.identity)})
        document["experimental_source"] = {"name": source.file_name, "sha256": source.sha256, "size": source.size_bytes}
        evidence = guided.evidence_from_document(document)
        evidence = guided.PhysicalEvidence(**{**evidence.__dict__, "registration_source_identity": {
            "path": f"{source.location.store}:{source.location.relative_path}", "size": source.size_bytes,
            "mtime_ns": None, "sha256": source.sha256}})
        result = self.establish(self.reference, evidence, {"sha256": source.sha256, "size": source.size_bytes})
        self.assertEqual(result.registration.registration_hash, built.registration.registration_hash)

    def test_a_new_mesh_in_the_same_frame_gets_its_own_registration(self):
        result = self.establish()
        self.assertNotEqual(self.variant.identity["sha256"], self.reference.identity["sha256"])
        variant = guided.modal_dataset_geometry_identity(as_dataset(self.variant))
        self.assertEqual(result.registration.to_dict()["fe_geometry_identity"], dict(variant))
        self.assertEqual(variant["sha256"], self.variant.identity["sha256"])
        self.assertEqual(list(result.registration.mapped_fe_node_ids), true_top_ids())
        self.assertLess(result.metrics["mapping_max_residual_in_abaqus_units"], 1e-9)
        self.assertTrue(any(check.startswith("FE frame: the measured surface TOP max_z") for check in result.checks))
        self.assertFalse(result.provenance()["production_ready"])
        self.assertFalse(result.provenance()["governed"])

    def test_wrong_orientation_is_refused_by_the_corner_marker(self):
        evidence = self.evidence(orientation={"experimental_axes_in_fe": ["-X", "-Y", "+Z"],
                                              "reference": "corner_A_marker", "source": "wrong photograph reading"})
        with self.assertRaises(guided.GuidedRegistrationRefusal) as caught:
            self.establish(evidence=evidence)
        self.assertIn("contradicts the documented axes", str(caught.exception))

    def test_mirrored_axes_are_refused(self):
        evidence = self.evidence(orientation={"experimental_axes_in_fe": ["+X", "-Y", "+Z"],
                                              "reference": "corner_A_marker", "source": "photo"})
        with self.assertRaises(guided.GuidedRegistrationRefusal) as caught:
            self.establish(evidence=evidence)
        self.assertEqual(caught.exception.field, "orientation.experimental_axes_in_fe")

    def test_same_bounding_boxes_but_another_internal_orientation_is_refused(self):
        """R1: a mirrored, rotated or relabelled mesh of the symmetric plate keeps every bounding box; not the frame."""
        def variant(coordinates=None, node_ids=None):
            ids = self.variant.node_ids if node_ids is None else node_ids
            xyz = self.variant.coordinates if coordinates is None else coordinates
            return FEGeometry(ids, xyz, fe_geometry_identity(ids.tolist(), xyz))

        xyz = self.variant.coordinates
        span = xyz.max(axis=0) + xyz.min(axis=0)
        mirrored = xyz.copy()
        mirrored[:, 0] = span[0] - xyz[:, 0]  # mirror about the plate centre: same boxes
        rotated = xyz.copy()
        rotated[:, :2] = span[:2] - xyz[:, :2]  # 180 degrees in plane: same boxes
        top = np.flatnonzero([value.startswith("TOP:") for value in self.variant.node_ids])
        relabelled = self.variant.node_ids.copy()
        relabelled[top] = relabelled[top[::-1]]  # the same TOP points under other node labels
        swapped = xyz[:, [1, 0, 2]]  # axes swapped: other boxes as well
        for label, fe in (("mirrored", variant(mirrored)), ("rotated 180", variant(rotated)),
                          ("relabelled surface", variant(node_ids=relabelled)), ("axes swapped", variant(swapped))):
            with self.subTest(label):
                if label != "axes swapped":
                    self.assertEqual(guided_boxes(fe), guided_boxes(self.variant))  # bounding boxes are no evidence
                with self.assertRaises(guided.GuidedRegistrationRefusal) as caught:
                    self.establish(fe)
                self.assertEqual(caught.exception.field, "fe_frame")
                self.assertIn(guided.FE_FRAME_NOT_VERIFIED, str(caught.exception))

    def test_changed_files_and_dof_mismatch_are_refused(self):
        cases = {
            "experimental_source": dict(identity={"sha256": "b" * 64, "size": 4096}),
            "modal_set": dict(experimental=ModalDataset("x", Path("x.unv"), experiment().modes,
                                                        metadata={"modal_set_key": "set-b"})),
        }
        for field_name, kwargs in cases.items():
            with self.subTest(field_name), self.assertRaises(guided.GuidedRegistrationRefusal) as caught:
                self.establish(**kwargs)
            self.assertEqual(caught.exception.field, field_name)
        document = evidence_document(dict(self.frame))
        document["measured_dofs"] = ["U1", "U2", "U3"]
        with self.assertRaises(guided.GuidedRegistrationRefusal) as caught:
            self.establish(evidence=guided.evidence_from_document(document))
        self.assertEqual(caught.exception.field, "measured_dof_contract")

    def test_missing_or_non_physical_evidence_is_refused(self):
        document = evidence_document({})
        with self.assertRaises(guided.GuidedRegistrationRefusal) as caught:
            guided.evidence_from_document(document)
        self.assertEqual(caught.exception.field, "fe_frame")
        centered = evidence_document(dict(self.frame), mode="documented_centered_alignment",
                                     orientation={"experimental_axes_in_fe": ["+X", "+Y", "+Z"],
                                                  "reference": "documented_convention", "source": "convention"})
        del centered["geometry_calibration"]["corner_A"]
        with self.assertRaises(guided.GuidedRegistrationRefusal) as caught:
            self.establish(evidence=guided.evidence_from_document(centered))
        self.assertEqual(caught.exception.field, "geometry_calibration.mode")
        template = guided.evidence_template(as_dataset(self.variant), self.experimental, IDENTITY, "synthetic.unv")
        with self.assertRaises(guided.GuidedRegistrationRefusal):  # the unfilled template is never evidence
            guided.evidence_from_document(template)
        self.assertEqual([row[2] for row in guided.evidence_rows(None)], ["MISSING"] * len(guided.REQUIRED_EVIDENCE))

    def test_saved_registration_reopens_only_for_the_exact_files(self):
        result = self.establish()
        with tempfile.TemporaryDirectory() as directory:
            path = guided.save_guided_registration(result, Path(directory) / "guided.json")
            again = guided.load_guided_registration(path)
            self.assertEqual(again.registration.registration_hash, result.registration.registration_hash)
            guided.verify_for_files(again, as_dataset(self.variant), self.experimental, IDENTITY)
            for label, args in (("other experimental content", (as_dataset(self.variant), self.experimental,
                                                                {"sha256": "c" * 64, "size": 4096})),
                                ("other FE mesh", (as_dataset(self.reference), self.experimental, IDENTITY))):
                with self.subTest(label), self.assertRaises(guided.GuidedRegistrationRefusal):
                    guided.verify_for_files(again, *args)
            record = json.loads(path.read_text(encoding="utf-8"))
            record["checks"].append("edited by hand")
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaises(guided.GuidedRegistrationRefusal) as caught:
                guided.load_guided_registration(path)
            self.assertEqual(caught.exception.field, "record_hash")

    def test_accepted_scan_evidence_is_found_by_content_only(self):
        from domain.experiment_fixture import load_experiment_fixture_manifest
        from services.production_modal_input import FIXTURE_MANIFEST_PATH

        fixtures = load_experiment_fixture_manifest(FIXTURE_MANIFEST_PATH)
        source = fixtures.fixture("SP13/best-physical").experimental_source
        evidence = guided.accepted_scan_evidence({"sha256": source.sha256, "size": source.size_bytes})
        self.assertEqual((evidence.kind, evidence.modal_set, evidence.measured_dofs),
                         (guided.ACCEPTED_SCAN, "best", ("U3",)))
        self.assertEqual(evidence.geometry_calibration.mode, "scan_to_panel_edges")
        self.assertEqual(evidence.reference_geometry_file.sha256,
                         "78d197376f7a5cce644d7c0eeb218df3151d3c349284caffa48c333f3ff11d39")
        self.assertEqual(dict(evidence.fe_frame["accepted_surface_label_set"]), {
            "node_count": 29754, "sha256": "bdfec8bf94605fdbe967353e56fbe36e379f73928fcdc3ca3bbaaa1c316b02db",
            "registration_hash": "2eeeaa8698851baf33c640a5e741a91a67c6629b436700a920ba9333061cd823"})
        with self.assertRaises(guided.GuidedRegistrationRefusal):
            guided.accepted_scan_evidence({"sha256": "d" * 64, "size": source.size_bytes})


class WorkerTests(_World, unittest.TestCase):
    def run_worker(self, active):
        import main
        import runtime_hardening

        captured, failures = [], []

        class Root:
            @staticmethod
            def after(_delay, callback):
                callback()

        application = SimpleNamespace(root=Root(), _analysis_cancel_event=threading.Event(),
                                      _owned_analysis_process=None, _set_analysis_stage=lambda *_: None,
                                      _failed=failures.append, _governed_registration_requested=False,
                                      _guided_registration=active)
        with tempfile.TemporaryDirectory() as directory:
            odb, unv = Path(directory) / "plate.odb", Path(directory) / "test.unv"
            odb.write_bytes(b"stand-in")
            unv.write_bytes(b"x" * IDENTITY["size"])
            with mock.patch.object(main.app, "load_or_extract_odb", return_value=as_dataset(self.variant)), \
                    mock.patch.object(runtime_hardening, "load_universal_modal_file", return_value=self.experimental), \
                    mock.patch.object(runtime_hardening, "fresh_content_identity", return_value=dict(IDENTITY)), \
                    mock.patch.object(main.app, "compare_modal_datasets",
                                      side_effect=lambda *a, **k: captured.append(k) or (_ for _ in ()).throw(
                                          RuntimeError("stop after comparison"))):
                main.app.ModalComparatorApp._worker(application, odb, unv, Path(directory), 7, 8, "abaqus", 1.0,
                                                    "set-a")
        return captured, failures

    def test_an_active_guided_registration_is_applied_to_its_files(self):
        result = self.establish()
        captured, failures = self.run_worker(result)
        self.assertEqual(set(captured[0]), {"frozen_registration"})
        self.assertEqual(captured[0]["frozen_registration"].registration_hash, result.registration.registration_hash)
        self.assertEqual(str(failures[0]), "stop after comparison")

    def test_a_guided_registration_of_other_files_refuses_the_run(self):
        import runtime_hardening

        result = self.establish(fe=self.reference, evidence=guided.evidence_from_document(
            evidence_document({"fe_geometry_identity": dict(self.reference.identity)})))
        captured, failures = self.run_worker(result)  # the loaded ODB is the variant mesh
        self.assertEqual(captured, [])  # never compared with another registration
        self.assertIsInstance(failures[0], runtime_hardening.GuidedRegistrationRefused)
        self.assertIn("not run with any other registration", str(failures[0]))


class MeanMacCardTests(unittest.TestCase):
    def test_the_card_states_what_it_averages(self):
        from ui_workflow import mean_mac_card_text

        pair = lambda mac, status: SimpleNamespace(mac=mac, status=status)  # noqa: E731
        # CORE-E2E T1 (SP-02): three Excellent pairs and three Review / Poor candidates
        pairs = [pair(0.9176, "Excellent match"), pair(0.622, "Review"), pair(0.9508, "Excellent match"),
                 pair(0.570, "Poor match"), pair(0.614, "Review"), pair(0.9754, "Excellent match")]
        self.assertEqual(mean_mac_card_text(pairs), "0.948 Excellent/Good (3)\n0.775 all admissible (6)")
        self.assertEqual(mean_mac_card_text([pair(0.65, "Review")]), "— Excellent/Good (0)\n0.650 all admissible (1)")
        self.assertEqual(mean_mac_card_text([]), "—")


class DialogTests(_World, unittest.TestCase):
    def test_dialog_builds_applies_saves_and_reopens(self):
        import tkinter as tk

        from guided_registration_ui import GuidedRegistrationDialog
        from services.modal_data_viewer import LoadedModalData

        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"no display: {error}")
        root.withdraw()
        self.addCleanup(root.destroy)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            unv = folder / "synthetic.unv"
            unv.write_bytes(b"synthetic experimental content")
            from services.archived_sensitivity_evidence import fresh_content_identity

            identity = fresh_content_identity(unv)
            document = evidence_document(dict(self.frame))
            document["experimental_source"] = {"name": unv.name, "sha256": identity["sha256"], "size": identity["size"]}
            (folder / "evidence.json").write_text(json.dumps(document), encoding="utf-8")
            loaded = LoadedModalData(as_dataset(self.variant), self.experimental, abaqus_path=folder / "plate.odb",
                                     experimental_path=unv)
            started = []
            app = SimpleNamespace(root=root, status=tk.StringVar(master=root), _start=lambda: started.append(True),
                                  _guided_registration=None)
            dialog = GuidedRegistrationDialog(app, loaded)

            def pump(condition, timeout=30.0):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline and not condition():
                    root.update()
                    time.sleep(0.01)
                return condition()

            self.assertTrue(pump(lambda: dialog.identity is not None))
            self.assertEqual({row[2] for row in guided.evidence_rows(None)}, {"MISSING"})
            wrong = copy.deepcopy(document)  # an FE frame that is not this model's: refused, the reason shown
            wrong["fe_frame"] = {"measured_surface_identity": {"sha256": "e" * 64,
                                                               "node_count": self.surface["node_count"]}}
            (folder / "wrong.json").write_text(json.dumps(wrong), encoding="utf-8")
            dialog.load_evidence(folder / "wrong.json")
            dialog.build()
            self.assertTrue(pump(lambda: dialog.status.cget("text").startswith("REFUSED")))
            self.assertIn("fe_frame", dialog.status.cget("text"))
            self.assertEqual(str(dialog.build_button.cget("state")), "normal")
            self.assertEqual(str(dialog.apply_button.cget("state")), "disabled")
            dialog.load_evidence(folder / "evidence.json")
            # R2: an unexpected error in the background build (unreadable file, broken CSV, ...) never leaves the
            # dialog blocked, never leaves a registration, and the operation can be retried
            with mock.patch.object(guided, "establish_guided_registration",
                                   side_effect=OSError("reference FE geometry: read error")):
                dialog.build()
                self.assertTrue(pump(lambda: str(dialog.build_button.cget("state")) == "normal"))
            self.assertTrue(dialog.status.cget("text").startswith("FAILED (unexpected OSError)"),
                            dialog.status.cget("text"))
            self.assertIsNone(dialog.result)
            self.assertEqual((str(dialog.apply_button.cget("state")), str(dialog.save_button.cget("state"))),
                             ("disabled", "disabled"))
            with mock.patch.object(guided, "establish_guided_registration", side_effect=ValueError("bad CSV row")):
                dialog.build()
                self.assertTrue(pump(lambda: str(dialog.build_button.cget("state")) == "normal"))
            self.assertIn("unexpected ValueError", dialog.status.cget("text"))
            dialog.build()
            self.assertTrue(pump(lambda: dialog.result is not None))
            self.assertTrue(dialog.status.cget("text").startswith("ESTABLISHED"))
            saved = dialog.save(folder / "guided.json")
            dialog.apply()
            self.assertIs(app._guided_registration, dialog.result)
            self.assertEqual(started, [True])
            again = GuidedRegistrationDialog(app, loaded)
            self.assertTrue(pump(lambda: again.identity is not None))
            again.open_saved(saved)
            self.assertTrue(again.status.cget("text").startswith("OPENED"))
            unv.write_bytes(b"changed experimental content")  # the measurement file changed
            changed = GuidedRegistrationDialog(app, loaded)
            self.assertTrue(pump(lambda: changed.identity is not None))
            changed.open_saved(saved)
            self.assertTrue(changed.status.cget("text").startswith("SAVED REGISTRATION REFUSED"))
            changed.clear()
            self.assertIsNone(app._guided_registration)
            for window in (dialog, again, changed):
                if window.window.winfo_exists():
                    window.window.destroy()



class StaleResultTests(_World, unittest.TestCase):
    """R3: a registration shown in the dialog always belongs to the inputs shown; a stale one is never applicable."""

    def setUp(self) -> None:
        super().setUp()
        import tkinter as tk

        from guided_registration_ui import GuidedRegistrationDialog
        from services.archived_sensitivity_evidence import fresh_content_identity
        from services.modal_data_viewer import LoadedModalData

        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"no display: {error}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name)
        unv = self.folder / "synthetic.unv"
        unv.write_bytes(b"synthetic experimental content")
        identity = fresh_content_identity(unv)
        self.document = evidence_document(dict(self.frame))
        self.document["experimental_source"] = {"name": unv.name, "sha256": identity["sha256"],
                                                "size": identity["size"]}
        self.write("evidence.json", self.document)
        other = copy.deepcopy(self.document)
        other["label"] = "another physical record of the same scan"
        self.write("other.json", other)
        (self.folder / "broken.json").write_text("{ not json", encoding="utf-8")
        self.loaded = LoadedModalData(as_dataset(self.variant), self.experimental,
                                      abaqus_path=self.folder / "plate.odb", experimental_path=unv)
        self.started = []
        self.app = SimpleNamespace(root=self.root, status=tk.StringVar(master=self.root),
                                   _start=lambda: self.started.append(True), _guided_registration=None)
        self.dialog = GuidedRegistrationDialog(self.app, self.loaded)
        self.addCleanup(lambda: self.dialog.window.winfo_exists() and self.dialog.window.destroy())
        self.assertTrue(self.pump(lambda: self.dialog.identity is not None))

    def write(self, name, document):
        (self.folder / name).write_text(json.dumps(document), encoding="utf-8")

    def pump(self, condition, timeout=30.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not condition():
            self.root.update()
            time.sleep(0.01)
        return condition()

    def built(self):
        self.dialog.load_evidence(self.folder / "evidence.json")
        self.dialog.build()
        self.assertTrue(self.pump(lambda: self.dialog.result is not None))
        self.assertEqual(self.applicable(), (True, True))
        return self.dialog.result

    def applicable(self):
        return (str(self.dialog.apply_button.cget("state")) == "normal",
                str(self.dialog.save_button.cget("state")) == "normal")

    def assertStale(self):
        self.assertIsNone(self.dialog.result)
        self.assertEqual(self.applicable(), (False, False))
        self.dialog.apply()  # nothing is applied
        self.assertIsNone(self.app._guided_registration)
        self.assertEqual(self.started, [])

    def test_new_evidence_invalidates_the_result(self):
        self.built()
        self.dialog.load_evidence(self.folder / "other.json")
        self.assertStale()
        self.assertEqual(str(self.dialog.build_button.cget("state")), "normal")  # a new Check and build is required

    def test_accepted_scan_choice_invalidates_the_result(self):
        self.built()
        self.dialog.use_accepted()  # this synthetic file has no accepted passport: refused, nothing stale kept
        self.assertTrue(self.dialog.status.cget("text").startswith("NO ACCEPTED SCAN CALIBRATION"))
        self.assertStale()

    def test_unreadable_new_evidence_leaves_no_applicable_result(self):
        self.built()
        self.dialog.load_evidence(self.folder / "broken.json")
        self.assertTrue(self.dialog.status.cget("text").startswith("EVIDENCE REFUSED"))
        self.assertIsNone(self.dialog.evidence)
        self.assertStale()

    def test_another_reference_geometry_requires_a_new_check(self):
        self.built()
        self.dialog.locate(self.folder / "reference_geometry.csv")
        self.assertEqual(self.dialog.reference_path, self.folder / "reference_geometry.csv")
        self.assertIn("Press Check and build again", self.dialog.status.cget("text"))
        self.assertStale()

    def test_cancelled_file_choice_changes_nothing(self):
        result = self.built()
        status = self.dialog.status.cget("text")
        with mock.patch("tkinter.filedialog.askopenfilename", return_value=""):
            self.dialog.load_evidence()
            self.dialog.locate()
            self.dialog.open_saved()
        self.assertIs(self.dialog.result, result)
        self.assertEqual(self.applicable(), (True, True))
        self.assertEqual(self.dialog.status.cget("text"), status)
        self.assertIsNone(self.dialog.reference_path)

    def _held_build(self):
        """A build whose background work waits until released (a real registration is returned afterwards)."""
        release, real = threading.Event(), guided.establish_guided_registration

        def held(*args, **kwargs):
            release.wait(30)
            return real(*args, **kwargs)

        patcher = mock.patch.object(guided, "establish_guided_registration", side_effect=held)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.dialog.load_evidence(self.folder / "evidence.json")
        self.dialog.build()
        self.assertEqual(str(self.dialog.build_button.cget("state")), "disabled")
        return release, held

    def test_a_build_overtaken_by_new_evidence_is_ignored(self):
        release, held = self._held_build()
        self.dialog.load_evidence(self.folder / "other.json")
        release.set()
        self.assertFalse(self.pump(lambda: self.dialog.result is not None, timeout=3.0))
        self.assertStale()

    def test_a_build_overtaken_by_clear_is_ignored(self):
        release, held = self._held_build()
        self.dialog.clear()
        release.set()
        self.assertFalse(self.pump(lambda: self.dialog.result is not None, timeout=3.0))
        self.assertStale()

    def test_reopened_registration_is_verified_and_replaces_the_shown_result(self):
        first = self.built()
        saved = self.dialog.save(self.folder / "saved.json")
        self.dialog.load_evidence(self.folder / "other.json")
        self.dialog.build()
        self.assertTrue(self.pump(lambda: self.dialog.result is not None))
        self.assertNotEqual(self.dialog.result.evidence_hash, first.evidence_hash)
        self.dialog.open_saved(saved)
        self.assertTrue(self.dialog.status.cget("text").startswith("OPENED"))
        self.assertEqual(self.dialog.result.evidence_hash, first.evidence_hash)
        self.dialog.apply()
        self.assertEqual(self.app._guided_registration.evidence_hash, first.evidence_hash)
        self.assertEqual(self.started, [True])

    def test_an_applied_registration_is_not_changed_by_new_inputs(self):
        applied = self.built()
        self.dialog.apply()
        from guided_registration_ui import GuidedRegistrationDialog

        again = GuidedRegistrationDialog(self.app, self.loaded)
        self.addCleanup(lambda: again.window.winfo_exists() and again.window.destroy())
        self.assertTrue(self.pump(lambda: again.identity is not None))
        again.load_evidence(self.folder / "other.json")
        again.locate(self.folder / "reference_geometry.csv")
        self.assertIsNone(again.result)
        self.assertIs(self.app._guided_registration, applied)  # only Clear removes it
        again.clear()
        self.assertIsNone(self.app._guided_registration)

REAL_T3_GEOMETRY = os.environ.get("AUTO_ID_CORE_E2E_SP13_MODAL_GEOMETRY")  # geometry.csv of the new SP13_modal.odb


@unittest.skipUnless(REAL_T3_GEOMETRY and os.environ.get("AUTO_ID_FIXTURE_ROOT_CARBON_PROJECT_ARCHIVE"),
                     "needs AUTO_ID_CORE_E2E_SP13_MODAL_GEOMETRY (new SP13_modal.odb geometry.csv) and the "
                     "carbon-project-archive store (pinned SP13_fe_geometry.csv)")
class RealSp13FrameTests(unittest.TestCase):
    """R1 on the real case: the new SP13_modal.odb measured surface is the accepted model's, label and coordinate."""

    def test_new_sp13_mesh_shares_the_accepted_measured_surface(self):
        from domain.experiment_fixture import fixture_roots_from_environment, resolve_external_file
        from domain.specimen_manifest import load_specimen_manifest

        manifest = load_specimen_manifest(ROOT / "docs/auto_id/specimens/SP13.physical.specimen.json")
        reference = resolve_external_file(manifest.fe_reference.geometry_file, fixture_roots_from_environment())
        accepted = guided.geometry_file_surface_identity(reference, "CFRP_PLATE_TOP", "max_z", "mm")
        new = guided.geometry_file_surface_identity(Path(REAL_T3_GEOMETRY), "CFRP_PLATE_TOP", "max_z", "mm")
        self.assertEqual((new["sha256"], new["node_count"]), (accepted["sha256"], accepted["node_count"]))
        self.assertEqual((accepted["label_set_sha256"], accepted["node_count"]),
                         ("bdfec8bf94605fdbe967353e56fbe36e379f73928fcdc3ca3bbaaa1c316b02db", 29754))


if __name__ == "__main__":
    unittest.main()
