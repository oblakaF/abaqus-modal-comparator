"""G2d-1 — the two-file comparator can use the accepted frozen physical registration of SP-02 / SP-13.

Opt-in only, enabled only after the selected ODB and UNV are the accepted files (fresh SHA-256); the analysis verifies
the modal set and the frozen registration on the loaded data again and refuses otherwise (never a silent automatic
registration). The frozen measured-point-to-FE-node mapping and rotation enter the actual MAC computation of the
unchanged comparison engine; G2c then distinguishes VERIFIED from REFERENCE_ONLY.

Synthetic data in ordinary CI. The store-gated test uses the real UNVs, the identity-verified archived FE geometry
and the ARCHIVED CARBON-4C baseline mode shapes (shape packs) — never an Abaqus run.
"""

from __future__ import annotations

import functools
import json
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

from domain.experiment_fixture import fixture_roots_from_environment, load_experiment_fixture_manifest  # noqa: E402
from domain.registration import FrozenRegistration  # noqa: E402
from modal_core import ModalDataset, ModeShape, compare_modal_datasets  # noqa: E402
import reviewed_core  # noqa: E402
from services import archived_sensitivity_evidence as ev  # noqa: E402
from test_g2c_archived_sensitivity_evidence import EXP_HZ, FE_HZ, World, _fe_dataset  # noqa: E402

PAIRS = {1: 7, 2: 8, 3: 10, 4: 13}  # experimental mode -> FE mode whose shape it measures (1 <-> 7 fails the 15 % gate)


def fe_dataset(odb: Path) -> ModalDataset:
    """The World's FE mesh (same geometry identity) with distinct non-rigid U3 shapes; node 12 repeats node 6."""
    base = _fe_dataset(odb)
    coordinates = base.modes[0].coordinates
    modes = []
    for mode in base.sorted_modes():
        m = mode.number
        x, y = coordinates[:, 0] / 10.0, coordinates[:, 1] / 10.0
        vectors = np.zeros((12, 3))
        vectors[:, 2] = np.cos(0.9 * (m - 6) * x + 0.5 * (m % 3 + 1) * y) + 0.4 * np.sin(1.7 * x * y + m)
        vectors[11] = vectors[5]
        modes.append(ModeShape(m, mode.frequency_hz, mode.node_ids, coordinates, vectors))
    return ModalDataset("FE", odb, modes)


def experimental_dataset(unv: Path, fe: ModalDataset) -> ModalDataset:
    """Each experimental mode measures U3 of its FE mode at FE nodes 1-6 (the frozen physical mapping)."""
    shapes = {mode.number: mode.vectors for mode in fe.modes}
    node_ids = np.array([100 + k for k in range(6)], dtype=object)
    coordinates = np.array([[x * 0.01, y * 0.01, 0.0] for y in range(2) for x in range(3)])
    modes = []
    for number, hz in EXP_HZ.items():
        vectors = np.zeros((6, 3), dtype=complex)
        vectors[:, 2] = shapes[PAIRS[number]][:6, 2]
        modes.append(ModeShape(number, hz, node_ids, coordinates, vectors))
    metadata = {"mode_source": "curve-fitted dataset 55", "modal_set_key": "set-a",
                "available_modal_sets": [{"key": "set-a"}]}
    return ModalDataset("PolyMAX", unv, modes, metadata=metadata)


def variant(registration: FrozenRegistration, **changes) -> FrozenRegistration:
    fields = {name: getattr(registration, name) for name in FrozenRegistration.FIELD_NAMES[:-2]}
    fields["measured_dof_contract"] = [list(row) for row in registration.measured_dof_contract]
    fields.update(changes)
    return FrozenRegistration.create(**fields)


class _Case(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.world = World(directory.name)
        self.odb, self.unv = self.world.files["SP02"]
        self.fe = fe_dataset(self.odb)
        self.experimental = experimental_dataset(self.unv, self.fe)
        self.registration = self.world.registrations["SP02"]

    def compare(self, registration=None, **kwargs):
        result = compare_modal_datasets(self.fe, self.experimental, frozen_registration=registration, **kwargs)
        result.metadata["comparison_inputs"] = ev.comparison_input_record(self.odb, self.unv, "set-a")
        return result


class EngineTests(_Case):
    def test_frozen_mapping_and_rotation_drive_the_mac(self):
        result = self.compare(self.registration)
        reference = result.abaqus.sorted_modes()[0]
        mapped = [str(n) for n in np.asarray(reference.node_ids, dtype=object)[result.geometry.experimental_to_abaqus]]
        self.assertEqual(mapped, list(self.registration.mapped_fe_node_ids))
        np.testing.assert_array_equal(result.geometry.rotation, np.asarray(self.registration.rotation))
        self.assertEqual(result.metadata["orientation_source"], reviewed_core.FROZEN_REGISTRATION_ORIENTATION_SOURCE)
        self.assertEqual(result.geometry.calibration_details["frozen_registration_hash"],
                         self.registration.registration_hash)
        pairs = {(p.experimental_mode, p.abaqus_mode): p.mac for p in result.pairs}
        for em, fm in ((2, 8), (3, 10), (4, 13)):
            self.assertAlmostEqual(pairs[(em, fm)], 1.0, places=12)  # the measured shapes of the frozen nodes
        self.assertNotIn((1, 7), pairs)  # the frequency gate is unchanged (24 vs 20 Hz)

        shifted = variant(self.registration, mapped_fe_node_ids=[f"PLATE-TOP:{k}" for k in range(7, 13)])
        shifted_pairs = {(p.experimental_mode, p.abaqus_mode): p.mac for p in self.compare(shifted).pairs}
        self.assertNotEqual(shifted_pairs, pairs)  # another mapping: another MAC
        self.assertLess(max((v for v in shifted_pairs.values() if v is not None), default=0.0), 0.999)

        turned = variant(self.registration, rotation=[[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]])
        turned_macs = [p.mac for p in self.compare(turned).pairs]
        self.assertFalse(any(mac is not None and mac > 0.999 for mac in turned_macs))  # U3 now reads FE U1 (zero)

    def test_frozen_registration_excludes_every_other_geometry_option(self):
        for option in ({"coordinate_scale_override": 1.0}, {"orientation_selection": {"candidate_id": "x"}},
                       {"fe_mapping_node_ids": ["PLATE-TOP:1"]}):
            with self.subTest(option=option), self.assertRaisesRegex(ValueError, "fixes the geometry"):
                reviewed_core.compare_modal_datasets(self.fe, self.experimental,
                                                     frozen_registration=self.registration, **option)

    def test_points_or_nodes_of_another_model_are_refused(self):
        other_points = variant(self.registration, experimental_node_ids=[200 + k for k in range(6)])
        with self.assertRaisesRegex(ValueError, "not the frozen registration's points"):
            self.compare(other_points)
        missing = variant(self.registration, mapped_fe_node_ids=[f"PLATE-TOP:{k}" for k in range(1, 6)] + ["X:99"])
        with self.assertRaisesRegex(ValueError, "absent from the Abaqus dataset"):
            self.compare(missing)

    def test_default_automatic_registration_is_unchanged(self):
        with mock.patch.object(reviewed_core, "geometry_from_frozen_registration") as frozen:
            try:
                compare_modal_datasets(self.fe, self.experimental, coordinate_scale_override=1.0)
            except Exception:  # noqa: BLE001 - the synthetic geometry may be ambiguous; only the path matters
                pass
        frozen.assert_not_called()


class G2cDistinctionTests(_Case):
    def check(self, result):
        return self.world.check(result)

    def test_governed_comparison_is_verified(self):
        evidence = self.check(self.compare(self.registration))
        self.assertEqual(evidence.status, ev.VERIFIED, evidence.reasons)
        self.assertEqual([r.row_id for r in evidence.rows if r.applicable], ["R1", "R2", "R3"])

    def test_another_registration_with_the_same_pairs_is_reference_only(self):
        # node 12 carries the same shapes as node 6: identical pairs and MAC, but not the governed mapping
        twin = variant(self.registration, mapped_fe_node_ids=[f"PLATE-TOP:{k}" for k in (1, 2, 3, 4, 5, 12)])
        result = self.compare(twin)
        self.assertEqual({(p.experimental_mode, p.abaqus_mode) for p in result.pairs},
                         {(p.experimental_mode, p.abaqus_mode) for p in self.compare(self.registration).pairs})
        evidence = self.check(result)
        self.assertEqual(evidence.status, ev.REFERENCE_ONLY, evidence.reasons)
        self.assertIn("maps 5 of 6 measurement points", evidence.reasons[1])


class WorkerTests(_Case):
    def run_worker(self, requested: bool, unv: Path | None = None, calibration=None, workspace: Path | None = None):
        import main
        import runtime_hardening

        captured, failures = [], []
        real = main.app.compare_modal_datasets

        def spy(*args, **kwargs):
            captured.append((args, kwargs))
            result = real(*args, **kwargs)
            captured.append(result)
            return result

        class Root:
            @staticmethod
            def after(_delay, callback):
                callback()

        application = SimpleNamespace(root=Root(), _analysis_cancel_event=threading.Event(),
                                      _owned_analysis_process=None, _set_analysis_stage=lambda *_: None,
                                      _failed=failures.append, _governed_registration_requested=requested)
        bind = functools.partial(ev.bind_accepted_reference, repo_root=self.world.root)
        with tempfile.TemporaryDirectory() as directory, self.world.pins(), \
                mock.patch.object(runtime_hardening, "bind_accepted_reference", bind), \
                mock.patch.object(main.app, "load_or_extract_odb", return_value=self.fe), \
                mock.patch.object(runtime_hardening, "load_universal_modal_file", return_value=self.experimental), \
                mock.patch.object(main.app, "compare_modal_datasets", side_effect=spy), \
                mock.patch.object(main.app, "render_mac_matrix", side_effect=RuntimeError("stop after comparison")):
            main.app.ModalComparatorApp._worker(application, self.odb, unv or self.unv, workspace or Path(directory),
                                                7, 13, "abaqus", calibration, "set-a")
        return captured, failures

    def test_requested_and_verified_applies_the_frozen_registration(self):
        captured, failures = self.run_worker(True)
        (_, kwargs), result = captured
        self.assertEqual(set(kwargs), {"frozen_registration"})  # no calibration, scale or orientation mixed in
        self.assertEqual(kwargs["frozen_registration"].registration_hash, self.registration.registration_hash)
        self.assertEqual(result.metadata["governed_registration"]["registration_hash"],
                         self.registration.registration_hash)
        self.assertTrue(result.warnings[0].startswith("Accepted physical registration applied: SP02"))
        self.assertEqual(str(failures[0]), "stop after comparison")
        self.assertEqual(self.world.check(result).status, ev.VERIFIED)

    def test_requested_but_mismatched_refuses_without_substitution(self):
        import runtime_hardening

        captured, failures = self.run_worker(True, unv=self.world.files["SP13"][1])
        self.assertEqual(captured, [])  # the comparison never ran with another registration
        self.assertIsInstance(failures[0], runtime_hardening.GovernedRegistrationRefused)
        self.assertIn("is not the accepted SP02 PolyMAX source", str(failures[0]))
        self.assertIn("not run with any other registration", str(failures[0]))

    def test_governed_and_automatic_runs_never_share_a_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            self.run_worker(True, workspace=workspace)
            governed = {path.name for path in workspace.glob("analysis_*")}
            self.run_worker(False, workspace=workspace)
            both = {path.name for path in workspace.glob("analysis_*")}
        self.assertEqual(len(governed), 1)
        self.assertEqual(len(both), 2)

    def test_default_keeps_automatic_registration(self):
        captured, _ = self.run_worker(False, calibration=1.0)
        (_, kwargs) = captured[0]
        self.assertNotIn("frozen_registration", kwargs)
        self.assertEqual(kwargs, {"coordinate_scale_override": 1.0})


def _pump(root, condition, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        root.update()
        if condition():
            return True
        time.sleep(0.01)
    return False


class TkTests(_Case):
    def test_option_is_enabled_only_for_accepted_files(self):
        try:
            import tkinter as tk

            root = tk.Tk()
        except Exception as error:  # noqa: BLE001
            self.skipTest(f"Tk is unavailable: {error}")
        self.addCleanup(root.destroy)
        self.addCleanup(lambda: [root.after_cancel(job) for job in root.tk.splitlist(root.tk.call("after", "info"))])
        root.withdraw()
        import main
        import ui_workflow

        disabled = {"autosave_enabled": False, "restore_on_startup": False, "show_recovery_notice": False}
        with mock.patch.object(ui_workflow, "load_recovery_preferences", return_value=disabled), \
                mock.patch.object(ui_workflow, "discover_abaqus_installations", return_value=()):
            application = main.app.ModalComparatorApp(root)
        check = application.governed_registration_check
        self.assertEqual(str(check.cget("state")), "disabled")  # automatic registration is the default
        self.assertFalse(application.use_governed_registration.get())
        match = functools.partial(ev.match_accepted_files, repo_root=self.world.root)
        with self.world.pins(), mock.patch.object(ev, "match_accepted_files", match):
            application.abaqus_path.set(str(self.odb))
            application.experimental_path.set(str(self.unv))
            self.assertTrue(_pump(root, lambda: str(check.cget("state")) == "normal"))
            self.assertIn("Available: SP02", application.governed_registration_status.cget("text"))
            check.invoke()
            self.assertTrue(application._governed_registration_requested)
            application.experimental_path.set(str(self.world.files["SP13"][1]))  # another file: withdrawn at once
            self.assertEqual(str(check.cget("state")), "disabled")
            self.assertFalse(application.use_governed_registration.get())
            self.assertFalse(application._governed_registration_requested)
            self.assertTrue(_pump(root, lambda: "Not available:" in application.governed_registration_status.cget("text")
                                  and "PolyMAX source" in application.governed_registration_status.cget("text")))
            self.assertEqual(str(check.cget("state")), "disabled")


class RealArchivedShapeTests(unittest.TestCase):
    """Real UNV + identity-verified archived FE geometry + ARCHIVED CARBON-4C baseline mode shapes (store-gated).

    Exercised: the real engine with the frozen physical registration on real archived mode shapes; the governed MACs
    of the accepted strict pairs are reproduced, and G2c is VERIFIED; the legacy centred registration gives
    REFERENCE_ONLY. Not exercised: Abaqus extraction from the ODB (the shapes come from the archived shape pack, TOP
    surface only, modes 7-17) and the GUI worker.
    """

    CASES = {"SP02": ("carbon4c/run_sp02/SP02_f3e592281bebce66.odb", "SP-02/SP02_polymax_retry_260803.unv",
                      "SP02_f3e592281bebce66"),
             "SP13": ("carbon4c/run_sp13/SP13_a46d08b52995e078.odb", "SP-13/SP13_a_polymax.unv",
                      "SP13_a46d08b52995e078")}

    def test_real_archived_shapes(self):
        roots = fixture_roots_from_environment()
        missing = [store for store in ("snadwich", "carbon-project-archive") if store not in roots]
        if missing:
            self.skipTest(f"data stores {missing} not configured")
        from domain.specimen_manifest import load_specimen_manifest
        from services.fe_shape_pack import load_shape_pack, load_shape_pack_record
        from services.physical_registration import load_fe_geometry
        from universal_reader import load_universal_modal_file

        for specimen, (odb_relative, unv_relative, pack_name) in self.CASES.items():
            with self.subTest(specimen=specimen):
                spec = next(s for s in ev.SPECIMENS if s.specimen == specimen)
                fixture = load_experiment_fixture_manifest(ROOT / ev.FIXTURE_MANIFEST).fixture(spec.fixture_id)
                odb, unv = roots["carbon-project-archive"] / odb_relative, roots["snadwich"] / unv_relative
                if not odb.is_file() or not unv.is_file():
                    self.skipTest(f"{specimen} archive files are not available")
                experimental = load_universal_modal_file(unv, modal_set=fixture.modal_set.name)
                fe = load_fe_geometry(load_specimen_manifest(
                    ROOT / f"docs/auto_id/specimens/{specimen}.physical.specimen.json"), roots)
                pack = load_shape_pack(load_shape_pack_record(ROOT / f"docs/auto_id/fe_shapes/{pack_name}.shape-pack.json"),
                                       roots)
                ids = np.asarray(fe.node_ids, dtype=object)
                index = {node: i for i, node in enumerate(ids.tolist())}
                rows = np.array([index[str(node)] for node in pack.node_ids])
                modes = []
                for k, (number, hz) in enumerate(zip(pack.mode_numbers, pack.frequencies_hz)):
                    if number > 17:
                        continue
                    vectors = np.zeros((len(ids), 3), dtype=np.float32)
                    vectors[rows] = pack.displacements[k]
                    modes.append(ModeShape(number, hz, ids, fe.coordinates, vectors))
                abaqus = ModalDataset("archived shape pack", odb, modes)
                governed = ev.bind_accepted_reference(odb, unv, abaqus, experimental)
                record = json.loads((ROOT / spec.reevaluation_path).read_text(encoding="utf-8"))["results"]["PHYSICAL"]
                legacy = FrozenRegistration.from_dict(json.loads(
                    (ROOT / f"docs/registrations/{specimen}_frozen_registration.json").read_text(encoding="utf-8")))
                for registration, expected in ((governed.registration, ev.VERIFIED), (legacy, ev.REFERENCE_ONLY)):
                    result = compare_modal_datasets(abaqus, experimental, frozen_registration=registration)
                    result.metadata["comparison_inputs"] = ev.comparison_input_record(odb, unv, fixture.modal_set.name)
                    if expected == ev.VERIFIED:
                        macs = {(p.experimental_mode, p.abaqus_mode): p.mac for p in result.pairs}
                        for row in record["strict_pairs"]:
                            self.assertAlmostEqual(macs[(row["experimental_mode"], row["fe_mode"])], row["mac"],
                                                   places=9)
                    self.assertEqual(ev.check_archived_sensitivity_evidence(result).status, expected)


if __name__ == "__main__":
    unittest.main()
