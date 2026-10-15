"""Quick calibration P2: an explicitly selected accepted physical registration, and a baseline-only workflow.

Before Abaqus: the fixture and the registration seal (existing APIs), the model INP SHA-256 against the fixture, the
experimental content identity and the modal set / points / U3 contract. After the baseline: the FE geometry identity
recomputed from the FULL extracted dataset must equal the registration's, the registration must be content-compatible
and every mapped node present; otherwise REFUSED before any optimiser step. Pairing uses
compare_modal_datasets(fe, experiment, frozen_registration=registration). BASELINE_ONLY stops before the optimiser.

Synthetic world (FakeAbaqus) in a temporary repository; the real SP-13 reproduction uses archived FE data only.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import quick_calibration_support as S  # noqa: E402
from domain.registration import FrozenRegistration  # noqa: E402
from scientific_state import calibration_fingerprint, fe_geometry_identity  # noqa: E402
from services import quick_calibration as qc  # noqa: E402
from services.quick_calibration import (  # noqa: E402
    REGISTRATION_MISMATCH,
    STATUS_BASELINE_ONLY,
    STATUS_ESTIMATE,
    STATUS_REFUSED,
    PreflightRefused,
    QuickCalibrationError,
    config_from_dict,
    run_quick_calibration,
)
from test_quick_calibration import E_FACE, _identity_orientation  # noqa: E402
from test_quick_calibration_fe_budget import CountingAbaqus  # noqa: E402

FIXTURE = "SYN/plate-physical"


def physical_abaqus() -> CountingAbaqus:
    fake = CountingAbaqus()
    fake.node_id_format = "PLATE-1:{}"  # "INSTANCE:label": the extracted dataset has an FE geometry identity
    return fake


class SyntheticWorld:
    """A temporary repository whose fixture catalogue holds a sealed registration of the synthetic plate."""

    def __init__(self, folder: Path) -> None:
        import universal_reader

        self.folder = folder
        self.repo = folder / "repo"
        (folder / "model.inp").write_text(S.INP)
        S.write_experiment(folder / "exp.unv", 0.9 * S.E0, S.G0, noise=0.001)
        fe = physical_abaqus().extract(self._odb(), folder, 30)
        reference = fe.sorted_modes()[0]
        self.fe_identity = fe_geometry_identity(list(reference.node_ids), reference.coordinates)
        experimental = universal_reader.load_universal_modal_file(folder / "exp.unv", modal_set="polymax")
        points = experimental.sorted_modes()[0]
        fe_xy = np.asarray(reference.coordinates)[:, :2]
        mapped = [str(reference.node_ids[int(np.argmin(np.linalg.norm(fe_xy - xy * 1000.0, axis=1)))])
                  for xy in np.asarray(points.coordinates)[:, :2]]
        unv = folder / "exp.unv"
        calibration = {"mode": "camera_grid", "specimen": "synthetic plate"}
        self.registration = FrozenRegistration.create(
            experimental_source_identity={"path": "synthetic:exp.unv", "size": unv.stat().st_size, "mtime_ns": None,
                                          "sha256": qc._sha256_file(unv)},
            experimental_modal_set_identity="polymax", fe_geometry_identity=self.fe_identity, calibration=calibration,
            calibration_fingerprint=calibration_fingerprint(calibration), orientation_candidate_id="geometry-synthetic",
            rotation=np.eye(3), translation=np.zeros(3), coordinate_scales=np.full(3, 0.001),
            experimental_node_ids=[item.item() if isinstance(item, np.generic) else item for item in points.node_ids],
            mapped_fe_node_ids=mapped, measured_dof_contract=[[False, False, True]] * len(mapped),
            registration_metrics={})
        catalogue = json.loads((ROOT / qc.FIXTURE_MANIFEST).read_text(encoding="utf-8"))
        source = next(f for f in catalogue["fixtures"] if f["fixture_id"] == "SP13/best-physical")
        entry = json.loads(json.dumps(source))
        entry["fixture_id"] = FIXTURE
        entry["experimental_source"].update(sha256=qc._sha256_file(unv), size_bytes=unv.stat().st_size)
        entry["modal_set"].update(name="polymax", display_name="PolyMAX", mode_count=len(experimental.modes),
                                  measurement_point_count=len(mapped))
        entry["registration"].update(path="docs/registrations/SYN_physical_registration.json",
                                     registration_hash=self.registration.registration_hash,
                                     fe_geometry_sha256=self.fe_identity["sha256"])
        entry["fe"]["geometry_identity"].update(sha256=self.fe_identity["sha256"],
                                                node_count=self.fe_identity["node_count"])
        model = folder / "model.inp"
        entry["fe"]["model_input"].update(sha256=qc._sha256_file(model),
                                          size_bytes=model.stat().st_size)
        catalogue["fixtures"].append(entry)
        self.write(catalogue)

    def _odb(self) -> Path:
        odb = self.folder / "fe.odb"
        odb.write_text(json.dumps({"E1": S.E0, "E2": S.E0, "G12": S.G0}))
        return odb

    def write(self, catalogue) -> None:
        manifest = self.repo / qc.FIXTURE_MANIFEST
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(catalogue, indent=1), encoding="utf-8")
        registration = self.repo / "docs/registrations/SYN_physical_registration.json"
        registration.parent.mkdir(parents=True, exist_ok=True)
        registration.write_text(json.dumps(self.registration.to_dict(), indent=1), encoding="utf-8")


class _Case(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp(prefix="qc_p2_"))
        cls.orientation = _identity_orientation(cls.root / "probe")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="case_", dir=self.root))
        self.world = SyntheticWorld(self.folder)

    def config(self, **extra):
        data = {"model_inp": "model.inp", "experiment": "exp.unv", "output_dir": "out", "modal_set": "polymax",
                "parameters": [E_FACE], "physical_registration_fixture": FIXTURE, "baseline_only": True,
                "max_new_fe_solves": 1}
        data.update(extra)
        return config_from_dict(data, self.folder)

    def run_with(self, fake=None, **extra):
        fake = fake or physical_abaqus()
        with mock.patch.object(qc, "run_bounded_lm", side_effect=AssertionError("no optimiser")) as lm:
            result, paths = run_quick_calibration(self.config(**extra), fake.solve, fake.extract,
                                                  repo_root=self.world.repo)
        return result, paths, fake, lm


# ----------------------------------------------------------------------------- the accepted registration

class RegistrationTests(_Case):
    def test_baseline_only_with_the_physical_registration(self):
        result, paths, fake, lm = self.run_with()
        self.assertEqual(result["status"], STATUS_BASELINE_ONLY)
        lm.assert_not_called()  # no optimiser evaluation
        self.assertEqual(fake.calls, 1)
        self.assertEqual(result["estimates"], {})
        self.assertNotIn("calibrated_inp", paths)
        registration = result["registration"]
        self.assertEqual(registration["orientation_source"], "frozen_registration")
        physical = registration["physical_registration"]
        self.assertEqual(physical["fixture_id"], FIXTURE)
        self.assertEqual(physical["registration_hash"], self.world.registration.registration_hash)
        self.assertEqual(physical["fe_geometry_identity"]["sha256"], self.world.fe_identity["sha256"])
        self.assertTrue(any("recomputed from the full extracted dataset" in c for c in physical["checks"]))
        self.assertTrue(any("model INP SHA-256" in c for c in physical["checks"]))
        strong = [p for p in registration["pairs"] if p["fitted_row"]]
        self.assertGreaterEqual(len(strong), 4)
        self.assertTrue(all(p["mac"] > 0.99 for p in strong))  # the frozen mapping reads the measured shapes
        report = Path(paths["report"]).read_text(encoding="utf-8")
        self.assertIn("RESULT: BASELINE_ONLY", report)
        self.assertIn("recomputed from the baseline FE dataset of this run", report)
        self.assertIn(f"Physical registration: {FIXTURE}", report)

    def test_a_reused_baseline_is_verified_again(self):
        self.run_with()
        again, _, fake, lm = self.run_with()
        self.assertEqual((again["status"], fake.calls), (STATUS_BASELINE_ONLY, 0))
        self.assertEqual(again["fe_job_cache"][0]["decision"], qc.VERIFIED_REUSE)
        self.assertTrue(again["registration"]["physical_registration"]["fe_geometry_identity"])

    def test_the_full_workflow_uses_the_registration(self):
        fake = physical_abaqus()
        result, _ = run_quick_calibration(self.config(baseline_only=False, max_new_fe_solves=100), fake.solve,
                                          fake.extract, repo_root=self.world.repo)
        self.assertEqual(result["status"], STATUS_ESTIMATE)
        self.assertEqual(result["registration"]["orientation_source"], "frozen_registration")
        self.assertAlmostEqual(result["estimates"]["E_face"]["multiplier"], 0.9, delta=0.01)


class RefusalTests(_Case):
    def assert_preflight_refused(self, text, **extra):
        fake = physical_abaqus()
        with self.assertRaises(PreflightRefused) as caught:
            run_quick_calibration(self.config(**extra), fake.solve, fake.extract, repo_root=self.world.repo)
        self.assertIn(text, str(caught.exception))
        self.assertEqual(fake.calls, 0)  # nothing was solved

    def test_wrong_fe_geometry_is_refused_before_the_optimiser(self):
        fake = physical_abaqus()
        fake.layers = 2  # another mesh
        result, paths, fake, lm = self.run_with(fake)
        self.assertEqual((result["status"], result["refusal_code"]), (STATUS_REFUSED, REGISTRATION_MISMATCH))
        self.assertIn("not the registration's", result["refusal_reasons"][0])
        lm.assert_not_called()
        self.assertEqual(fake.calls, 1)
        self.assertNotIn("calibrated_inp", paths)
        self.assertNotIn("pairs", result["registration"])  # no pairing on an unverified geometry

    def test_unavailable_fe_identity_is_refused(self):
        fake = CountingAbaqus()  # "PLATE-1.5" ids: no FE geometry identity can be formed
        result, _, _, lm = self.run_with(fake)
        self.assertEqual(result["refusal_code"], REGISTRATION_MISMATCH)
        self.assertIn("identity of the extracted baseline is unavailable", result["refusal_reasons"][0])
        lm.assert_not_called()

    def test_an_incorrect_inp_or_unv_is_refused_before_abaqus(self):
        (self.folder / "edited.inp").write_text(S.INP.replace("** synthetic", "** edited synthetic"))
        self.assert_preflight_refused("not the fixture's accepted model input", model_inp="edited.inp")
        S.write_experiment(self.folder / "other.unv", 0.9 * S.E0, S.G0, noise=0.002, seed=5)
        self.assert_preflight_refused("not the fixture's PolyMAX source", experiment="other.unv")

    def test_a_corrupted_registration_is_refused(self):
        path = self.world.repo / "docs/registrations/SYN_physical_registration.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["mapped_fe_node_ids"][0] = document["mapped_fe_node_ids"][1]
        path.write_text(json.dumps(document), encoding="utf-8")
        self.assert_preflight_refused("the physical registration is not verified")

    def test_a_wrong_modal_set_is_refused(self):
        self.assert_preflight_refused("needs modal set 'polymax'", modal_set="other")
        catalogue = json.loads((self.world.repo / qc.FIXTURE_MANIFEST).read_text(encoding="utf-8"))
        next(f for f in catalogue["fixtures"] if f["fixture_id"] == FIXTURE)["modal_set"]["mode_count"] = 5
        self.world.write(catalogue)  # the pinned set is not the file's set (6 modes)
        self.assert_preflight_refused("the modal set does not replay the registration")

    def test_an_unknown_fixture_is_refused(self):
        self.assert_preflight_refused("is not an accepted fixture", physical_registration_fixture="SYN/none")

    def test_exclusive_and_explicit_options(self):
        for extra, text in (({"orientation_candidate_id": "geometry-x"}, "cannot be combined"),
                            ({"coordinate_scale": 1000.0}, "cannot be combined"),
                            ({"physical_registration_fixture": " SYN/plate-physical"}, "explicit fixture id"),
                            ({"max_new_fe_solves": 2}, "exactly one new FE solve"),
                            ({"baseline_only": "yes"}, "true or false")):
            with self.subTest(extra=extra), self.assertRaisesRegex(QuickCalibrationError, text):
                self.config(**extra)
        self.assertIsNone(qc.config_template()["physical_registration_fixture"])  # never preselected
        self.assertFalse(qc.config_template()["baseline_only"])


# ----------------------------------------------------------------------------- baseline only without a registration

class BaselineOnlyTests(_Case):
    def test_baseline_only_with_a_confirmed_orientation(self):
        result, paths, fake, lm = self.run_with(physical_registration_fixture=None,
                                                orientation_candidate_id=self.orientation)
        self.assertEqual(result["status"], STATUS_BASELINE_ONLY)
        lm.assert_not_called()
        self.assertEqual(fake.calls, 1)
        self.assertNotIn("physical_registration", result["registration"])
        self.assertEqual(result["evaluations"], [])

    def test_the_window_and_the_cli(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import quick_calibration as tool

        common = ["quick", "--inp", str(self.folder / "model.inp"), "--unv", str(self.folder / "exp.unv"),
                  "--modal-set", "polymax", "--material", "CFRP_Face", "--out", str(self.folder / "out"),
                  "--check-only"]
        for flags, code, text in ((["--baseline-only"], 0, "at most 1 new FE solve(s)"),
                                  (["--baseline-only", "--max-new-fe-solves", "2"], 2, "exactly one new FE solve"),
                                  (["--physical-registration-fixture", "SP13/best-physical", "--orientation", "x"], 2,
                                   "cannot be combined"),
                                  (["--physical-registration-fixture", "SP13/best-physical"], 2,
                                   "not the fixture's accepted model input")):
            out, err = io.StringIO(), io.StringIO()
            with self.subTest(flags=flags), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(tool.main(common + flags), code)
            self.assertIn(text, out.getvalue() + err.getvalue())
        try:
            import tkinter as tk

            root = tk.Tk()
        except Exception as error:  # noqa: BLE001
            self.skipTest(f"Tk is unavailable: {error}")
        self.addCleanup(root.destroy)
        root.withdraw()
        import quick_calibration_window as qw

        window = qw.QuickCalibrationWindow(root, threaded=False)
        self.assertEqual(window.registration_fixture.get(), qw.NO_REGISTRATION)  # never preselected
        self.assertIn("SP13/best-physical", list(window.registration_box["values"]))
        self.assertEqual(window.config_data()["physical_registration_fixture"], None)
        window.baseline_only.set(True)
        window._baseline_only_changed()
        self.assertEqual(window.max_new_fe_solves.get(), "1")
        window.registration_fixture.set("SP13/best-physical")
        data = window.config_data()
        self.assertEqual((data["physical_registration_fixture"], data["baseline_only"]), ("SP13/best-physical", True))


# ----------------------------------------------------------------------------- real SP-13 (archived FE data)

class RealSp13ArchivedTests(unittest.TestCase):
    """The baseline-only workflow on the real INP / UNV with the ARCHIVED FE solution (no Abaqus).

    The FE dataset is the archived geometry (all 1,585,637 nodes) with the archived CARBON-4C baseline shapes (top
    surface, modes 7-30), served instead of a solve. The MAC values are recomputed by the current engine from those
    archived shapes: a reproduction of the archived pairing, not an independent FE or experimental validation.
    """

    def test_archived_sp13_pairing_is_reproduced(self):
        from domain.experiment_fixture import fixture_roots_from_environment
        from domain.specimen_manifest import load_specimen_manifest
        from modal_core import ModalDataset, ModeShape
        from services.fe_shape_pack import load_shape_pack, load_shape_pack_record
        from services.physical_registration import load_fe_geometry

        roots = fixture_roots_from_environment()
        if not {"snadwich", "carbon-project-archive"} <= set(roots):
            self.skipTest("data stores snadwich / carbon-project-archive not configured")
        inp = roots["snadwich"] / "SP-13/SP13_mesh_local_v1_modal/SP13_mesh_local_v1_modal.inp"
        unv = roots["snadwich"] / "SP-13/SP13_a_polymax.unv"
        fe = load_fe_geometry(load_specimen_manifest(ROOT / "docs/auto_id/specimens/SP13.physical.specimen.json"),
                              roots)
        record = load_shape_pack_record(ROOT / "docs/auto_id/fe_shapes/SP13_a46d08b52995e078.shape-pack.json")
        pack = load_shape_pack(record, roots)
        ids = np.asarray(fe.node_ids, dtype=object)
        index = {node: i for i, node in enumerate(ids.tolist())}
        rows = np.array([index[str(node)] for node in pack.node_ids])

        def archived_extract(odb, out, last):
            modes = []
            for k, (number, hz) in enumerate(zip(pack.mode_numbers, pack.frequencies_hz)):
                vectors = np.zeros((len(ids), 3), dtype=np.float32)
                vectors[rows] = pack.displacements[k]
                modes.append(ModeShape(number, hz, ids, fe.coordinates, vectors))
            return ModalDataset("archived CARBON-4C shapes", Path(odb), modes)

        def no_solve(inp_path, job_dir, job_name):
            return Path(job_dir) / f"{job_name}.odb"  # the archived solution stands in for the solve

        folder = Path(tempfile.mkdtemp(prefix="qc_p2_sp13_"))
        self.addCleanup(shutil.rmtree, folder, True)
        config = config_from_dict({"model_inp": str(inp), "experiment": str(unv), "output_dir": str(folder),
                                   "modal_set": "best", "physical_registration_fixture": "SP13/best-physical",
                                   "baseline_only": True, "max_new_fe_solves": 1,
                                   "parameters": [{"name": "E_face", "material": "CFRP_Face",
                                                   "constants": ["E1", "E2"]}]})
        identity = {"solver": {"command": "archived", "executable": "archived", "executable_sha256": "archived"},
                    "extraction": {"script": "archived-shape-pack", "script_sha256": record.content_sha256}}
        with mock.patch.object(qc, "run_bounded_lm", side_effect=AssertionError("no optimiser")):
            result, paths = run_quick_calibration(config, no_solve, archived_extract, solver_identity=identity)
        self.assertEqual(result["status"], STATUS_BASELINE_ONLY)
        physical = result["registration"]["physical_registration"]
        self.assertEqual(physical["registration_hash"],
                         "2eeeaa8698851baf33c640a5e741a91a67c6629b436700a920ba9333061cd823")
        self.assertEqual(physical["fe_geometry_identity"],
                         {"sha256": "34d69d7920f5819c49ad5b2ab1aded824055aadbea3cb0244f405ab1a1595826",
                          "node_count": 1585637})
        archived = json.loads((ROOT / "docs/auto_id/registration_evidence/SP13_registration_reevaluation.json")
                              .read_text(encoding="utf-8"))["results"]["PHYSICAL"]["strict_pairs"]
        recomputed = {(p["experimental_mode"], p["fe_mode"]): p["mac"] for p in result["registration"]["pairs"]}
        for row in archived:  # EXP 4 <-> FE 10 (0.958458), EXP 7 <-> FE 13 (0.946904)
            self.assertAlmostEqual(recomputed[(row["experimental_mode"], row["fe_mode"])], row["mac"], places=9)
        strong = sorted((p["experimental_mode"], p["fe_mode"]) for p in result["registration"]["pairs"]
                        if p["fitted_row"])
        self.assertEqual(strong, [(4, 10), (7, 13)])
        self.assertNotIn("calibrated_inp", paths)


if __name__ == "__main__":
    unittest.main()
