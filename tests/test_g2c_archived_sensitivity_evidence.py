"""G2c — archived CARBON-5A sensitivity evidence for the two-file comparison (display only).

The recorded S_E / S_G12 of the accepted SP-02 / SP-13 strict pairs are shown only when the comparison is bound to
exactly that evidence: fresh SHA-256 of the compared ODB and experimental file, the pinned PolyMAX modal set, the
frozen physical registration, the pinned records and the accepted strict pairs with MAC-supported comparison pairs.
Everything else is SENSITIVITY_EVIDENCE_NOT_APPLICABLE with the reason. Nothing is estimated.

The synthetic world uses small files and records (no ODB / UNV in CI); the real SP-02 / SP-13 records are checked
without the large files, and the full real chain runs only when the data stores are configured.
"""

from __future__ import annotations

import contextlib
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

from domain.experiment_fixture import fixture_roots_from_environment, load_experiment_fixture_manifest  # noqa: E402
from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING  # noqa: E402
from domain.registration import FrozenRegistration  # noqa: E402
from modal_core import ModalDataset, ModeShape  # noqa: E402
from scientific_state import calibration_fingerprint, fe_geometry_identity  # noqa: E402
from services import archived_sensitivity_evidence as ev  # noqa: E402
from services.archived_baseline import load_archived_baseline, record_hash  # noqa: E402
from services.experiment_fixture_regression import load_fixture_registration  # noqa: E402

DIRECTIONS = tuple(ev.PERTURBATIONS)
FE_HZ = {7: 20.0, 8: 70.0, 9: 75.0, 10: 88.0, 11: 92.0, 12: 140.0, 13: 200.0}
EXP_HZ = {1: 24.0, 2: 71.0, 3: 90.0, 4: 205.0}
STRICT = (("R1", 2, 8), ("R2", 3, 10), ("R3", 4, 13))  # R3 is the holdout
S_VALUES = {"R1": (0.4932, 0.0002), "R2": (0.3620, 0.1269), "R3": (0.4837, 0.0005)}
SPEC_OF = {spec.specimen: spec for spec in ev.SPECIMENS}


def _real(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def _sha(seed: str) -> str:
    import hashlib

    return hashlib.sha256(seed.encode("ascii")).hexdigest()


def _fe_dataset(path: Path, shift: float = 0.0) -> ModalDataset:
    node_ids = np.array([f"PLATE-TOP:{k}" for k in range(1, 13)], dtype=object)
    coordinates = np.array([[x * 10.0 + shift, y * 10.0, 1.0] for y in range(3) for x in range(4)])
    rng = np.random.default_rng(7)
    return ModalDataset("FE", path, [ModeShape(number, hz, node_ids, coordinates, rng.normal(size=(12, 3)))
                                     for number, hz in FE_HZ.items()])


def _experimental_dataset(path: Path, modal_set: str = "set-a") -> ModalDataset:
    node_ids = np.array([100 + k for k in range(6)], dtype=object)
    coordinates = np.array([[x * 0.01, y * 0.01, 0.0] for y in range(2) for x in range(3)])
    rng = np.random.default_rng(3)
    modes = []
    for number, hz in EXP_HZ.items():
        vectors = np.zeros((6, 3), dtype=complex)
        vectors[:, 2] = rng.normal(size=6) + 0.1j
        modes.append(ModeShape(number, hz, node_ids, coordinates, vectors))
    metadata = {"mode_source": "curve-fitted dataset 55", "modal_set_key": modal_set,
                "available_modal_sets": [{"key": "set-a"}, {"key": "set-b"}]}
    return ModalDataset("PolyMAX", path, modes, metadata=metadata)


def comparison_pair(fe_mode, exp_mode, mac=0.95, order_changed=False, coverage="accepted"):
    return SimpleNamespace(abaqus_mode=fe_mode, experimental_mode=exp_mode, abaqus_frequency_hz=FE_HZ[fe_mode],
                           experimental_frequency_hz=EXP_HZ[exp_mode], mac=mac, status="Excellent match",
                           order_changed=order_changed, coverage_status=coverage)


class World:
    """Two synthetic specimens with every accepted record the check reads, written below one repo root."""

    def __init__(self, directory: str) -> None:
        self.root = Path(directory)
        self.files = {}
        self.registrations = {}
        self.baselines = {}
        self.reevaluations = {}
        fixtures = _real(ev.FIXTURE_MANIFEST)
        fixtures["fixtures"] = [item for item in fixtures["fixtures"]
                                if item["fixture_id"] in {spec.fixture_id for spec in ev.SPECIMENS}]
        self.fixtures = fixtures
        self.jobs = {"schema": "auto-id/accepted-forward-jobs/v1", "candidates": []}
        candidates = {ev.BASELINE_CANDIDATE: (52000.0, 4500.0), "CARBON-5A E_MINUS": (49400.0, 4500.0),
                      "CARBON-5A E_PLUS": (54600.0, 4500.0), "CARBON-5A G_MINUS": (52000.0, 4275.0),
                      "CARBON-5A G_PLUS": (52000.0, 4725.0)}
        for name, (e_in, g12) in candidates.items():
            self.jobs["candidates"].append({"name": name, "e_in_plane_mpa": e_in, "g12_mpa": g12, "jobs": {
                specimen: {"generated_inp_sha256": _sha(f"{name}/{specimen}")} for specimen in SPEC_OF}})
        for specimen in SPEC_OF:
            self._specimen(specimen)
        self.write()

    # ------------------------------------------------------------------ construction
    def _specimen(self, specimen: str) -> None:
        spec = SPEC_OF[specimen]
        data = self.root / "data"
        data.mkdir(exist_ok=True)
        odb, unv = data / f"{specimen}.odb", data / f"{specimen}.unv"
        odb.write_bytes(f"{specimen} baseline ODB ".encode("ascii") * 3000)
        unv.write_bytes(f"{specimen} PolyMAX UNV ".encode("ascii") * 500)
        self.files[specimen] = (odb, unv)
        fe = _fe_dataset(odb)
        reference = fe.sorted_modes()[0]
        geometry = fe_geometry_identity(reference.node_ids, reference.coordinates)
        calibration = {"mode": "camera_grid", "specimen": specimen}
        fixture = next(item for item in self.fixtures["fixtures"] if item["fixture_id"] == spec.fixture_id)
        registration = FrozenRegistration.create(
            experimental_source_identity={"path": f"snadwich:{unv.name}", "size": unv.stat().st_size,
                                          "mtime_ns": None, "sha256": self.sha(unv)},
            experimental_modal_set_identity="set-a", fe_geometry_identity=geometry, calibration=calibration,
            calibration_fingerprint=calibration_fingerprint(calibration), orientation_candidate_id="geometry-test",
            rotation=np.eye(3), translation=np.zeros(3), coordinate_scales=np.ones(3),
            experimental_node_ids=[100 + k for k in range(6)],
            mapped_fe_node_ids=[f"PLATE-TOP:{k}" for k in range(1, 7)],
            measured_dof_contract=[[False, False, True]] * 6, registration_metrics={})
        self.registrations[specimen] = registration
        fixture["experimental_source"].update(sha256=self.sha(unv), size_bytes=unv.stat().st_size)
        fixture["modal_set"].update(name="set-a", mode_count=len(EXP_HZ), measurement_point_count=6,
                                    measured_dofs=["U3"])
        fixture["registration"].update(registration_hash=registration.registration_hash,
                                       fe_geometry_sha256=geometry["sha256"])
        fixture["fe"]["geometry_identity"].update(sha256=geometry["sha256"], node_count=geometry["node_count"])
        fixture["fe"]["odb_reference"].update(sha256=self.sha(odb), size_bytes=odb.stat().st_size)
        baseline = _real(spec.baseline_path)
        job = self.candidate(ev.BASELINE_CANDIDATE)["jobs"][specimen]["generated_inp_sha256"]
        baseline["job"] = {"job_name": f"{specimen}_{job[:16]}", "generated_inp_sha256": job}
        baseline["odb"].update(sha256=self.sha(odb), size_bytes=odb.stat().st_size)
        baseline["fe_geometry_sha256"] = geometry["sha256"]
        baseline["experimental"].update(source_sha256=self.sha(unv), modal_set="set-a",
                                        modes=[{"number": k, "frequency_hz": v} for k, v in EXP_HZ.items()])
        baseline["fe_modes"] = [{"number": k, "frequency_hz": v} for k, v in FE_HZ.items()]
        baseline["mac_entries"] = []
        self.baselines[specimen] = baseline
        physical = {
            "status": "FROZEN", "registration_hash": registration.registration_hash,
            "strict_pairs": [{"row_id": row, "experimental_mode": em, "experimental_hz": EXP_HZ[em], "fe_mode": fm,
                              "fe_hz": FE_HZ[fm], "mac": 0.93,
                              "relative_frequency_error": (FE_HZ[fm] - EXP_HZ[em]) / EXP_HZ[em],
                              "family": "test", "torsion_dominated": False} for row, em, fm in STRICT],
            "holdouts": {"fit_row_ids": ["R1", "R2"], "holdout_row_ids": ["R3"]},
            "excluded": [{"experimental_mode": 1, "reason": "no FE mode within the frequency gate"}],
            "best_match_per_experimental_mode": [{"experimental_mode": 1, "experimental_hz": 24.0, "best_fe_mode": 7,
                                                  "best_mac": 0.89, "relative_frequency_error": -4.0 / 24.0}],
            "observation_sufficient": True,
        }
        document = {"policy_id": STRICT_IDENTIFICATION_PAIRING.policy_id,
                    "policy_hash": STRICT_IDENTIFICATION_PAIRING.policy_hash,
                    "physical_registration_file": fixture["registration"]["path"], "results": {"PHYSICAL": physical}}
        if spec.sensitivity_structure == ev.CARBON5A_ARCHIVE_ROWS:
            tracked = {row: fm for row, _, fm in STRICT}
            physical["sensitivities_carbon5a"] = {
                row: {"status": "RESOLVED", "tracked": {d: tracked[row] for d in DIRECTIONS},
                      "min_tracked_mac_u3": 0.9999, "S_E": S_VALUES[row][0], "S_G12": S_VALUES[row][1]}
                for row in S_VALUES}
        else:
            document["packs"] = {d: f"{specimen}_{self.candidate(ev.PERTURBATIONS[d][0])['jobs'][specimen]['generated_inp_sha256'][:16]}"
                                 for d in DIRECTIONS}
            physical["sensitivities"] = {row: {"S_E": s[0], "S_G12": s[1]} for row, s in S_VALUES.items()}
            physical["tracking_refusals"] = []
        self.reevaluations[specimen] = document

    def candidate(self, name: str) -> dict:
        return next(item for item in self.jobs["candidates"] if item["name"] == name)

    @staticmethod
    def sha(path: Path) -> str:
        import hashlib

        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _dump(self, relative: str, value) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=1), encoding="utf-8")

    def write(self, repin: bool = True) -> None:
        """Write every record; ``repin`` re-pins the content hashes (an accepted change), otherwise they stay."""
        self._dump(ev.FIXTURE_MANIFEST, self.fixtures)
        self._dump(ev.ACCEPTED_FORWARD_JOBS, self.jobs)
        for specimen, spec in SPEC_OF.items():
            fixture = next(item for item in self.fixtures["fixtures"] if item["fixture_id"] == spec.fixture_id)
            self._dump(fixture["registration"]["path"], self.registrations[specimen].to_dict())
            self._dump(spec.baseline_path, self.baselines[specimen])
            self.reevaluations[specimen]["baseline_record_sha256"] = load_archived_baseline(
                self.root / spec.baseline_path).record_sha256
            self._dump(spec.reevaluation_path, self.reevaluations[specimen])
        if repin:
            self.specimens = tuple(
                ev.SpecimenEvidence(s.specimen, s.fixture_id, s.baseline_path, s.reevaluation_path,
                                    record_hash(self.reevaluations[s.specimen]), s.sensitivity_structure)
                for s in ev.SPECIMENS)
            self.jobs_hash = record_hash(self.jobs)

    # ------------------------------------------------------------------ the comparison and the check
    def result(self, specimen: str, pairs=None, experimental=None, abaqus=None, unv: Path | None = None):
        odb, source = self.files[specimen]
        source = unv or source
        rows = [comparison_pair(fm, em) for _, em, fm in STRICT] + [comparison_pair(7, 1, mac=0.89)]
        return SimpleNamespace(
            abaqus=abaqus or _fe_dataset(odb), experimental=experimental or _experimental_dataset(source),
            pairs=rows if pairs is None else pairs,
            geometry=SimpleNamespace(experimental_to_abaqus=np.arange(6)),
            metadata={"orientation_source": "geometry_unique",
                      "comparison_inputs": ev.comparison_input_record(odb, source, "set-a")})

    @contextlib.contextmanager
    def pins(self):
        with mock.patch.object(ev, "SPECIMENS", self.specimens), \
                mock.patch.object(ev, "ACCEPTED_FORWARD_JOBS_HASH", self.jobs_hash):
            yield

    def check(self, result, cancel=None):
        with self.pins():
            return ev.check_archived_sensitivity_evidence(result, repo_root=self.root, cancel=cancel)




class _Case(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.world = World(directory.name)

    def assertRefused(self, evidence, text: str) -> None:
        self.assertEqual(evidence.status, ev.NOT_APPLICABLE)
        self.assertFalse(any(row.s_e is not None or row.s_g12 is not None for row in evidence.rows))
        self.assertIn(text, " ".join(evidence.reasons))


class MatchingEvidenceTests(_Case):
    def assert_recorded_rows(self, evidence, specimen: str) -> None:
        self.assertEqual(evidence.status, ev.APPLICABLE, evidence.reasons)
        self.assertEqual(evidence.specimen, specimen)
        strict = [row for row in evidence.rows if row.role != "NO_STRICT_ROW"]
        self.assertEqual([(r.row_id, r.role, r.experimental_mode, r.fe_mode) for r in strict],
                         [("R1", "FIT", 2, 8), ("R2", "FIT", 3, 10), ("R3", "HOLDOUT", 4, 13)])
        for row in strict:  # exactly the recorded values; nothing is estimated
            self.assertTrue(row.applicable)
            self.assertEqual((row.s_e, row.s_g12), S_VALUES[row.row_id])
            self.assertEqual(row.governed_mac, 0.93)
            self.assertEqual(row.comparison_mac, 0.95)
        self.assertEqual(dict(evidence.baseline), {"E_in_plane_mpa": 52000.0, "G12_mpa": 4500.0})
        self.assertEqual(dict(evidence.perturbations), {"E_in_plane_mpa+": 54600.0, "E_in_plane_mpa-": 49400.0,
                                                         "G12_mpa+": 4725.0, "G12_mpa-": 4275.0})
        self.assertIn(SPEC_OF[specimen].reevaluation_path, evidence.source)
        outlier = [row for row in evidence.rows if row.role == "NO_STRICT_ROW"]
        self.assertEqual(len(outlier), 1)  # preserved, never tuned away, and no sensitivity shown for it
        self.assertEqual((outlier[0].experimental_mode, outlier[0].fe_mode, outlier[0].s_e), (1, 7, None))
        self.assertIn("Outlier preserved", outlier[0].reason)
        text = ev.summary_text(evidence)
        for needle in ("52000", "4500", "49400 / 54600", "4275 / 4725", "D-074", "D-077", "SPEC v1.2"):
            self.assertIn(needle, text)

    def test_matching_sp02_evidence(self):
        evidence = self.world.check(self.world.result("SP02"))
        self.assert_recorded_rows(evidence, "SP02")
        self.assertIn("carbon5a/branch_tracking.csv", evidence.rows[0].branch)

    def test_matching_sp13_evidence(self):
        evidence = self.world.check(self.world.result("SP13"))
        self.assert_recorded_rows(evidence, "SP13")
        self.assertIn("strict branch tracker", evidence.rows[0].branch)

    def test_no_material_value_is_produced(self):
        evidence = self.world.check(self.world.result("SP02"))
        self.assertEqual(set(ev.LABELS) & {"NOT_A_MATERIAL_PROPERTY", "NOT_A_SPECIMEN_CALIBRATION"},
                         {"NOT_A_MATERIAL_PROPERTY", "NOT_A_SPECIMEN_CALIBRATION"})
        fields = set(ev.SensitivityRow.__dataclass_fields__) | set(ev.SensitivityEvidence.__dataclass_fields__)
        self.assertFalse(fields & {"e_estimate", "g_estimate", "correction", "recommended", "calibration"})
        self.assertNotIn("55.593", ev.summary_text(evidence))  # historical RUN_A candidate is never shown as a value


class FileIdentityTests(_Case):
    def test_wrong_odb(self):
        result = self.world.result("SP02")
        other_odb = self.world.files["SP13"][0]
        result.metadata["comparison_inputs"] = ev.comparison_input_record(other_odb, self.world.files["SP02"][1], "set-a")
        self.assertRefused(self.world.check(result), "is not the accepted SP13 PolyMAX source")
        unrelated = self.world.root / "data" / "unrelated.odb"
        unrelated.write_bytes(b"another sandwich model" * 100)
        result.metadata["comparison_inputs"] = ev.comparison_input_record(unrelated, self.world.files["SP02"][1], "set-a")
        self.assertRefused(self.world.check(result), "is not an accepted baseline ODB")

    def test_wrong_unv(self):
        result = self.world.result("SP02", unv=self.world.files["SP13"][1])
        self.assertRefused(self.world.check(result), "is not the accepted SP02 PolyMAX source")

    def _same_size_edit(self, path: Path) -> None:
        status = path.stat()
        content = bytearray(path.read_bytes())
        content[len(content) // 2] ^= 0x01
        path.write_bytes(bytes(content))
        os.utime(path, ns=(status.st_atime_ns, status.st_mtime_ns))  # path, size and mtime are unchanged
        self.assertEqual((path.stat().st_size, path.stat().st_mtime_ns), (status.st_size, status.st_mtime_ns))

    def test_same_size_content_modification_of_the_odb(self):
        result = self.world.result("SP02")
        self.assertEqual(self.world.check(result).status, ev.APPLICABLE)
        self._same_size_edit(self.world.files["SP02"][0])
        self.assertRefused(self.world.check(result), "is not an accepted baseline ODB")  # hashed afresh

    def test_same_size_content_modification_of_the_unv(self):
        result = self.world.result("SP13")
        self._same_size_edit(self.world.files["SP13"][1])
        self.assertRefused(self.world.check(result), "is not the accepted SP13 PolyMAX source")

    def test_file_changed_after_the_comparison(self):
        result = self.world.result("SP02")
        odb = self.world.files["SP02"][0]
        odb.write_bytes(odb.read_bytes() + b"x")
        self.assertRefused(self.world.check(result), "changed after the comparison")

    def test_comparison_without_recorded_inputs(self):
        result = self.world.result("SP02")
        del result.metadata["comparison_inputs"]
        self.assertRefused(self.world.check(result), "did not record the files it read")
        self.assertRefused(self.world.check(None), "no comparison result")


class ModalSetAndRegistrationTests(_Case):
    def test_incorrect_polymax_modal_set(self):
        _, unv = self.world.files["SP02"]
        result = self.world.result("SP02", experimental=_experimental_dataset(unv, modal_set="set-b"))
        self.assertRefused(self.world.check(result), "modal_set.name")
        dataset = _experimental_dataset(unv)
        dataset.modes.pop()
        result = self.world.result("SP02", experimental=dataset)
        self.assertRefused(self.world.check(result), "modal_set.mode_count")

    def test_measured_dof_contract_mismatch(self):
        _, unv = self.world.files["SP02"]
        dataset = _experimental_dataset(unv)
        for mode in dataset.modes:
            mode.vectors[:, 0] = 1.0  # U1 now measured: the frozen U3-only contract is not reproduced
        self.assertRefused(self.world.check(self.world.result("SP02", experimental=dataset)), "measured")

    def test_mismatched_physical_registration_hash(self):
        fixture = next(item for item in self.world.fixtures["fixtures"] if item["fixture_id"] == "SP02/bravo-1-physical")
        fixture["registration"]["registration_hash"] = _sha("another registration")
        self.world.write()
        self.assertRefused(self.world.check(self.world.result("SP02")), "registration_hash")

    def test_edited_registration_breaks_its_seal(self):
        path = self.world.root / "docs/registrations/SP13_physical_registration.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["translation"][0] += 1.0
        path.write_text(json.dumps(record), encoding="utf-8")
        self.assertRefused(self.world.check(self.world.result("SP13")), "cannot restore")

    def test_fe_geometry_differs_from_the_registration(self):
        odb, _ = self.world.files["SP02"]
        result = self.world.result("SP02", abaqus=_fe_dataset(odb, shift=0.5))
        self.assertRefused(self.world.check(result), "fe_geometry_identity")

    def test_strict_freeze_on_another_registration(self):
        self.world.reevaluations["SP02"]["results"]["PHYSICAL"]["registration_hash"] = _sha("legacy")
        self.world.write()
        self.assertRefused(self.world.check(self.world.result("SP02")), "not on the accepted physical registration")


class PairAndBranchTests(_Case):
    def test_mismatched_modal_pair(self):
        pairs = [comparison_pair(9, 2), comparison_pair(10, 3), comparison_pair(13, 4)]
        evidence = self.world.check(self.world.result("SP02", pairs=pairs))
        self.assertEqual(evidence.status, ev.APPLICABLE)  # R2 and R3 stay supported
        r1 = next(row for row in evidence.rows if row.row_id == "R1")
        self.assertFalse(r1.applicable)
        self.assertEqual((r1.s_e, r1.s_g12), (None, None))
        self.assertIn("pairs it with FE mode 9", r1.reason)
        evidence = self.world.check(self.world.result("SP02", pairs=[comparison_pair(9, 2)]))
        self.assertRefused(evidence, "no accepted strict pair is supported")
        self.assertIn("it is unpaired", " ".join(evidence.reasons))

    def test_mismatched_mac(self):
        pairs = [comparison_pair(8, 2, mac=0.79), comparison_pair(10, 3, mac=None),
                 comparison_pair(13, 4, order_changed=True)]
        evidence = self.world.check(self.world.result("SP13", pairs=pairs))
        self.assertRefused(evidence, "LOW_MAC")
        text = " ".join(evidence.reasons)
        self.assertIn("FREQUENCY_ONLY", text)
        self.assertIn("QUESTIONABLE", text)

    def test_comparison_mode_is_not_the_recorded_mode(self):
        odb, _ = self.world.files["SP02"]
        abaqus = _fe_dataset(odb)
        next(mode for mode in abaqus.modes if mode.number == 8).frequency_hz = 70.5
        evidence = self.world.check(self.world.result("SP02", abaqus=abaqus))
        r1 = next(row for row in evidence.rows if row.row_id == "R1")
        self.assertIn("not the recorded mode", r1.reason)
        self.assertIsNone(r1.s_e)

    def test_unresolved_sp02_branch(self):
        self.world.reevaluations["SP02"]["results"]["PHYSICAL"]["sensitivities_carbon5a"]["R2"]["status"] = "NOT_RESOLVED"
        self.world.write()
        evidence = self.world.check(self.world.result("SP02"))
        r2 = next(row for row in evidence.rows if row.row_id == "R2")
        self.assertFalse(r2.applicable)
        self.assertIn("not resolved in all four CARBON-5A states", r2.reason)
        self.assertIsNone(r2.s_g12)

    def test_unresolved_sp13_branch(self):
        self.world.reevaluations["SP13"]["results"]["PHYSICAL"]["tracking_refusals"] = ["G12_mpa+: ambiguous"]
        self.world.write()
        self.assertRefused(self.world.check(self.world.result("SP13")), "refused by the strict branch tracker")

    def test_missing_archived_evidence(self):
        del self.world.reevaluations["SP02"]["results"]["PHYSICAL"]["sensitivities_carbon5a"]["R1"]
        self.world.write()
        r1 = next(row for row in self.world.check(self.world.result("SP02")).rows if row.row_id == "R1")
        self.assertIn("no archived CARBON-5A sensitivity", r1.reason)
        (self.world.root / SPEC_OF["SP13"].reevaluation_path).unlink()
        self.assertRefused(self.world.check(self.world.result("SP13")), "is unavailable")

    def test_pinned_records_cannot_change(self):
        self.world.reevaluations["SP02"]["results"]["PHYSICAL"]["sensitivities_carbon5a"]["R1"]["S_E"] = 0.6
        self.world.write(repin=False)
        self.assertRefused(self.world.check(self.world.result("SP02")), "differs from its pinned content")

    def test_perturbations_are_the_archived_five_percent(self):
        self.world.candidate("CARBON-5A G_PLUS")["g12_mpa"] = 4950.0  # +10 %: not the archived perturbation
        self.world.write()
        self.assertRefused(self.world.check(self.world.result("SP02")), "is not the archived ±5 % value")

    def test_sp13_pack_provenance(self):
        self.world.reevaluations["SP13"]["packs"]["E_in_plane_mpa+"] = "SP13_0000000000000000"
        self.world.write()
        self.assertRefused(self.world.check(self.world.result("SP13")), "not the accepted CARBON-5A jobs")


class CancellationTests(_Case):
    def test_cancelled_before_and_during_hashing(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(ev.SensitivityCheckCancelled):
            self.world.check(self.world.result("SP02"), cancel=cancel)

        class AfterFirstChunk:
            calls = 0

            def is_set(self):
                AfterFirstChunk.calls += 1
                return AfterFirstChunk.calls > 2

        with mock.patch.object(ev, "_CHUNK_BYTES", 64), self.assertRaises(ev.SensitivityCheckCancelled):
            self.world.check(self.world.result("SP02"), cancel=AfterFirstChunk())

    def test_hashing_stops_between_chunks(self):
        odb = self.world.files["SP02"][0]
        chunks = []

        class DuringHashing:
            def is_set(self):
                chunks.append(1)
                return len(chunks) > 3  # set while the large file is still being read

        with mock.patch.object(ev, "_CHUNK_BYTES", 64), self.assertRaises(ev.SensitivityCheckCancelled):
            ev.fresh_content_identity(odb, DuringHashing())
        self.assertEqual(len(chunks), 4)
        self.assertGreater(odb.stat().st_size, 64 * 4)


class RuntimeWorkerTests(unittest.TestCase):
    def test_hardened_worker_records_the_compared_files(self):
        import main
        import runtime_hardening

        mode = ModeShape(1, 10.0, np.array([1], dtype=object), np.zeros((1, 3)), np.array([[0.0, 0.0, 1.0]]))
        dataset = ModalDataset("Abaqus", Path("model.odb"), [mode])
        result = SimpleNamespace(metadata={}, warnings=[], pairs=[])

        class Root:
            @staticmethod
            def after(_delay, callback):
                callback()

        application = SimpleNamespace(root=Root(), _analysis_cancel_event=threading.Event(),
                                      _owned_analysis_process=None, _set_analysis_stage=lambda *_: None,
                                      _failed=lambda error: None)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            odb, unv = folder / "model.odb", folder / "scan.unv"
            odb.write_text("odb", encoding="utf-8")
            unv.write_text("unv", encoding="utf-8")
            with mock.patch.object(main.app, "load_or_extract_odb", return_value=dataset), \
                    mock.patch.object(runtime_hardening, "load_universal_modal_file", return_value=dataset), \
                    mock.patch.object(main.app, "compare_modal_datasets", return_value=result), \
                    mock.patch.object(main.app, "render_mac_matrix", side_effect=RuntimeError("stop")):
                main.app.ModalComparatorApp._worker(application, odb, unv, folder / "output", 7, 15, "abaqus",
                                                    None, "set-a")
            record = result.metadata["comparison_inputs"]
            self.assertEqual(record["requested_modal_set"], "set-a")
            self.assertEqual(Path(record["abaqus"]["path"]), odb.resolve())
            self.assertEqual(Path(record["experimental"]["path"]), unv.resolve())
            self.assertEqual(record["abaqus"]["size"], 3)


class RealRecordTests(unittest.TestCase):
    """The accepted SP-02 / SP-13 records satisfy every pin and binding (no ODB / UNV needed)."""

    def test_real_records(self):
        fixtures = load_experiment_fixture_manifest(ROOT / ev.FIXTURE_MANIFEST)
        jobs = json.loads((ROOT / ev.ACCEPTED_FORWARD_JOBS).read_text(encoding="utf-8"))
        expected = {"SP02": {"R1": (8, "FIT"), "R2": (10, "FIT"), "R3": (13, "HOLDOUT")},
                    "SP13": {"R1": (10, "FIT"), "R2": (13, "HOLDOUT")}}
        for spec in ev.SPECIMENS:
            with self.subTest(specimen=spec.specimen):
                fixture = fixtures.fixture(spec.fixture_id)
                registration = load_fixture_registration(fixture, ROOT)
                baseline = load_archived_baseline(ROOT / spec.baseline_path)
                self.assertEqual(baseline.odb.sha256, fixture.fe.odb_reference.sha256)
                perturbations = ev._perturbations(spec, baseline, jobs)
                self.assertEqual({k: v for k, (v, _) in perturbations.items()},
                                 {"E_in_plane_mpa+": 54600.0, "E_in_plane_mpa-": 49400.0, "G12_mpa+": 4725.0,
                                  "G12_mpa-": 4275.0})
                document = json.loads((ROOT / spec.reevaluation_path).read_text(encoding="utf-8"))
                physical = ev._physical_freeze(spec, document, baseline, fixture, registration)
                holdouts = set(physical["holdouts"]["holdout_row_ids"])
                rows = {p["row_id"]: (p["fe_mode"], "HOLDOUT" if p["row_id"] in holdouts else "FIT")
                        for p in physical["strict_pairs"]}
                self.assertEqual(rows, expected[spec.specimen])
                for row_id in rows:
                    s_e, s_g12, _, reason = ev._branch(spec, document, physical, row_id, perturbations)
                    self.assertEqual(reason, "")
                    self.assertTrue(0.3 < s_e < 0.5 and 0.0 <= s_g12 < 0.13)


class RealStoreTests(unittest.TestCase):
    """Full chain on the real SP-02 / SP-13 files (store-gated: never in ordinary CI; no Abaqus).

    FE mode shapes need Abaqus Python, so the FE dataset carries the archived FE geometry (identity-verified) and
    the archived baseline frequencies; the comparison pairs mirror the recorded strict pairs.
    """

    CASES = {"SP02": ("carbon4c/run_sp02/SP02_f3e592281bebce66.odb", "SP-02/SP02_polymax_retry_260803.unv"),
             "SP13": ("carbon4c/run_sp13/SP13_a46d08b52995e078.odb", "SP-13/SP13_a_polymax.unv")}

    def test_real_sp02_and_sp13(self):
        roots = fixture_roots_from_environment()
        missing = [store for store in ("snadwich", "carbon-project-archive") if store not in roots]
        if missing:
            self.skipTest(f"data stores {missing} not configured")
        from domain.specimen_manifest import load_specimen_manifest
        from services.physical_registration import load_fe_geometry
        from universal_reader import load_universal_modal_file

        for specimen, (odb_relative, unv_relative) in self.CASES.items():
            with self.subTest(specimen=specimen):
                spec = SPEC_OF[specimen]
                fixture = load_experiment_fixture_manifest(ROOT / ev.FIXTURE_MANIFEST).fixture(spec.fixture_id)
                odb = roots["carbon-project-archive"] / odb_relative
                unv = roots["snadwich"] / unv_relative
                if not odb.is_file() or not unv.is_file():
                    self.skipTest(f"{specimen} archive files are not available")
                experimental = load_universal_modal_file(unv, modal_set=fixture.modal_set.name)
                fe = load_fe_geometry(load_specimen_manifest(ROOT / f"docs/auto_id/specimens/{specimen}.physical.specimen.json"),
                                      roots)
                baseline = load_archived_baseline(ROOT / spec.baseline_path)
                ids = np.asarray(fe.node_ids, dtype=object)
                zeros = np.zeros((len(ids), 3))
                abaqus = ModalDataset("archived", odb, [ModeShape(m.number, m.frequency_hz, ids, fe.coordinates, zeros)
                                                        for m in baseline.fe_modes])
                physical = json.loads((ROOT / spec.reevaluation_path).read_text(encoding="utf-8"))["results"]["PHYSICAL"]
                pairs = [SimpleNamespace(abaqus_mode=p["fe_mode"], experimental_mode=p["experimental_mode"],
                                         abaqus_frequency_hz=p["fe_hz"], experimental_frequency_hz=p["experimental_hz"],
                                         mac=p["mac"], status="Excellent match", order_changed=False,
                                         coverage_status="accepted") for p in physical["strict_pairs"]]
                result = SimpleNamespace(abaqus=abaqus, experimental=experimental, pairs=pairs,
                                         geometry=SimpleNamespace(experimental_to_abaqus=np.arange(len(experimental.sorted_modes()[0].node_ids))),
                                         metadata={"comparison_inputs": ev.comparison_input_record(
                                             odb, unv, fixture.modal_set.name)})
                evidence = ev.check_archived_sensitivity_evidence(result)
                self.assertEqual(evidence.status, ev.APPLICABLE, evidence.reasons)
                self.assertEqual([r.row_id for r in evidence.rows if r.applicable],
                                 [p["row_id"] for p in physical["strict_pairs"]])


def _pump(root, condition, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        root.update()
        if condition():
            return True
        time.sleep(0.01)
    return False


class TkIntegrationTests(unittest.TestCase):
    def application(self):
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
        return root, application, main

    @staticmethod
    def evidence() -> "ev.SensitivityEvidence":
        directory = tempfile.TemporaryDirectory()
        try:
            world = World(directory.name)
            return world.check(world.result("SP02"))
        finally:
            directory.cleanup()

    def populate(self, application, root):
        import test_core

        result = test_core.ModalCoreTests("test_export_excel_base_writes_the_documented_sheets_and_values").synthetic_result()
        with tempfile.TemporaryDirectory() as directory:
            application.cache = Path(directory)
            application.result = result
            application._populate(result)
            root.update_idletasks()
        return result

    def test_real_tk_check_displays_and_new_comparison_invalidates(self):
        root, application, main = self.application()
        self.assertIn("not checked", application.sensitivity_status.cget("text"))
        self.assertIn(str(application.scaling_tab), str(application.sensitivity_table))  # the existing G1 tab
        result = self.populate(application, root)
        g1_rows = application.scaling_table.get_children()
        self.assertEqual(len(g1_rows), len(result.pairs))  # G1 behaviour unchanged
        evidence = self.evidence()
        seen = []

        def fake_check(checked, cancel=None):
            seen.append((checked, threading.current_thread() is not threading.main_thread()))
            return evidence

        with mock.patch.object(ev, "check_archived_sensitivity_evidence", side_effect=fake_check):
            application.sensitivity_button.invoke()
            self.assertEqual(str(application.sensitivity_button.cget("state")), "disabled")
            self.assertTrue(_pump(root, lambda: application.sensitivity_table.get_children()))
        self.assertEqual(seen, [(result, True)])  # the current comparison, checked off the GUI thread
        shown = [tuple(str(v) for v in application.sensitivity_table.item(k, "values"))
                 for k in application.sensitivity_table.get_children()]
        self.assertEqual(shown, [tuple(str(v) for v in row) for row in ev.table_rows(evidence)])
        self.assertTrue(application.sensitivity_status.cget("text").startswith(ev.APPLICABLE))
        self.assertIn("Verified:", application.sensitivity_details.get("1.0", "end"))
        self.assertEqual(application.scaling_table.get_children(), g1_rows)
        self.populate(application, root)  # a new comparison result: the evidence must be checked again
        self.assertFalse(application.sensitivity_table.get_children())
        self.assertIn("not checked", application.sensitivity_status.cget("text"))
        application._clear_result_presentation("Analysis is running")
        self.assertFalse(application.sensitivity_table.get_children())

    def test_input_or_comparison_change_during_background_check_discards_it(self):
        root, application, main = self.application()
        evidence = self.evidence()
        for change in ("input", "comparison"):
            with self.subTest(change=change):
                result = self.populate(application, root)
                release, started, cancels = threading.Event(), threading.Event(), []

                def slow_check(checked, cancel=None):
                    cancels.append(cancel)
                    started.set()
                    release.wait(5)
                    return evidence

                with mock.patch.object(ev, "check_archived_sensitivity_evidence", side_effect=slow_check):
                    application.sensitivity_button.invoke()
                    self.assertTrue(started.wait(5))
                    if change == "input":
                        application.abaqus_path.set(str(Path(tempfile.gettempdir()) / "other.odb"))
                    else:
                        self.populate(application, root)
                    self.assertTrue(cancels[0].is_set())
                    release.set()
                    _pump(root, lambda: False, timeout=0.5)
                self.assertFalse(application.sensitivity_table.get_children())  # stale evidence is never shown
                self.assertNotIn(ev.APPLICABLE, application.sensitivity_status.cget("text"))
        # the display guard itself: evidence of another comparison, an old generation or a cancelled check
        current = application.result
        generation = application._sensitivity_generation
        for args in ((evidence, result, generation, threading.Event()),
                     (evidence, current, generation - 1, threading.Event())):
            application._show_sensitivity_evidence(*args)
            self.assertFalse(application.sensitivity_table.get_children())
        cancelled = threading.Event()
        cancelled.set()
        application._show_sensitivity_evidence(evidence, current, generation, cancelled)
        self.assertFalse(application.sensitivity_table.get_children())
        application._show_sensitivity_evidence(evidence, current, generation, threading.Event())
        self.assertTrue(application.sensitivity_table.get_children())  # only the current check is displayed

    def test_layout_keeps_both_tables_reachable_at_the_minimum_window_size(self):
        root, application, main = self.application()
        from ui_policy import MINIMUM_WINDOW_SIZE

        evidence = self.evidence()
        application._set_sensitivity_view(ev.APPLICABLE, ev.table_rows(evidence) * 3, ev.summary_text(evidence))
        application.tabs.select(application.scaling_tab)
        table = application.sensitivity_table
        for width, height in ((1160, 720), MINIMUM_WINDOW_SIZE):
            with self.subTest(width=width, height=height):
                root.geometry(f"{width}x{height}+0+0")
                root.deiconify()
                root.update()
                for widget in (application.scaling_table, application.scaling_xscroll, table,
                               application.sensitivity_xscroll, application.sensitivity_yscroll,
                               application.sensitivity_button, application.sensitivity_details):
                    self.assertTrue(widget.winfo_ismapped(), str(widget))
                table.xview_moveto(1.0)
                root.update()
                self.assertTrue(table.bbox(table.get_children()[0], "reason"))  # last column reachable


if __name__ == "__main__":
    unittest.main()
