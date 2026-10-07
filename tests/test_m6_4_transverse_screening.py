"""M6.4a: transverse-constant screening envelope, guarded screening jobs and evaluation (no Abaqus).

SUPERVISOR 2026-10-07 (D-066): the interim envelope LITERATURE_INTERIM_SCREENING_ENVELOPE and the
frozen observation-mode set are accepted; the SPEC §5 0.3 % criterion is uncertainty-budget
bookkeeping only.  Every solve and extraction here is a fake executor; real Abaqus needs a HUMAN gate.
"""

from __future__ import annotations

import ast
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.experiment_fixture import fixture_roots_from_environment, load_experiment_fixture_manifest
from domain.forward_model_manifest import PARAMETERISATIONS, EngineeringConstants, bind_forward_model, carbon_candidate
from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING, IdentificationPairingPolicy
from domain.identification_run import parse_solver_profile
from domain.transverse_screening import (
    INCLUDE,
    NEGLIGIBLE,
    SCREENED_CONSTANTS,
    ScreeningEnvelopeError,
    ScreeningPerturbation,
    classify,
    load_screening_envelope,
    parse_screening_envelope,
    require_material_stability,
)
from m3_support import SYNTHETIC_INP, forward_manifest, synthetic_passport
from m4_6_support import COORDS, FE_IDENTITY, NODE_IDS, SHAPES, TOP_ROWS, fake_frequencies, profile_dict
from services import forward_builder
from services.branch_tracker import FEModalState
from services.fe_shape_pack import parse_shape_pack_record
from services.forward_builder import (
    ForwardBuildError,
    locate_engineering_constants,
    prepare_forward_job,
    prepare_screening_job,
    render_screening_input,
    split_inp_lines,
)
from services.forward_solver import solve_forward_job
from services.shape_extraction import extract_shape_pack
from services.transverse_screening import (
    NOT_CLASSIFIED,
    BoundScreeningSpecimen,
    ScreeningError,
    ScreeningRunConfig,
    evaluate_screening,
    expected_jobs,
    extraction_expectation,
    load_screening_states,
    prepare_screening_plan,
    run_screening,
)


DOCS = ROOT / "docs" / "auto_id"
ENVELOPE = DOCS / "screening" / "M6_4_transverse_envelope.json"
ENVELOPE_HASH = "d29e848566afaadc1a73234d531f83383810e7ec2f7ac0471c0965aa6fd2036d"
MANIFEST_HASH = "6d34179c787c8b0e1619864709290f2824e0435b98fb1ff2689e61d892da3922"
PERTURBATIONS = ("E3-low", "E3-high", "nu13-low", "nu13-high", "nu23-low", "nu23-high", "G13-high", "G23-high")
SUPERVISOR_RANGES = {"E3": (6700.0, 5000.0, 10000.0), "nu13": (0.3, 0.2, 0.4), "nu23": (0.3, 0.2, 0.4),
                     "G13": (2200.0, 2200.0, 5000.0), "G23": (2200.0, 2200.0, 5000.0)}
REAL_JOBS = {
    "SP02": ("SP02_7ecb36decc403fda", "SP02_f3eed68a26571fba", "SP02_4ef95a55171cc3d8", "SP02_fe01394cc4ef1535",
             "SP02_6bf74401677e7e75", "SP02_47b309d68e48a957", "SP02_5732bef18649d4bb", "SP02_c93b3e3cb8ae511e"),
    "SP13": ("SP13_81a5cedfe42b38d3", "SP13_3fc1cad51076cfd2", "SP13_7ac63eb2905930ec", "SP13_9771af6aa8d4373c",
             "SP13_eb9383c49c9e1f2d", "SP13_8f84df93ab40549c", "SP13_b0af3095b6111c09", "SP13_0fcc8454363f3fa4"),
}


def envelope_dict(**changes) -> dict:
    data = json.loads(ENVELOPE.read_text(encoding="utf-8"))
    for path, value in changes.items():
        target = data
        *parents, key = path.split("__")
        for part in parents:
            target = target[int(part)] if isinstance(target, list) else target[part]
        target[key] = value
    return data


# ----------------------------------------------------------------------------- envelope (data, no stores)

class EnvelopeRecordTests(unittest.TestCase):
    def setUp(self):
        self.envelope = load_screening_envelope(ENVELOPE)

    def test_record_is_the_supervisor_envelope(self):
        envelope = self.envelope
        self.assertEqual(envelope.envelope_hash, ENVELOPE_HASH)
        self.assertEqual(envelope.basis, "LITERATURE_INTERIM_SCREENING_ENVELOPE")
        self.assertEqual(envelope.decision, "D-066")
        self.assertEqual(envelope.criterion, 0.003)
        self.assertEqual(dict(envelope.reference_candidate), {"E_in_plane_mpa": 52000.0, "G12_mpa": 4500.0})
        for name, (baseline, low, high) in SUPERVISOR_RANGES.items():
            with self.subTest(name=name):
                item = envelope.ranges[name]
                self.assertEqual((item.baseline, item.low, item.high), (baseline, low, high))
                self.assertEqual(item.baseline, PARAMETERISATIONS["carbon-property-set/v1"].fixed_constants[name])
        self.assertIn("not a material-specific prior", envelope.basis_statement)
        self.assertIn("not claimed as literature-supported", envelope.basis_statement)
        self.assertIn("bookkeeping only", envelope.canonical["criterion"]["purpose"])

    def test_one_at_a_time_endpoints(self):
        self.assertEqual(tuple(p.perturbation_id for p in self.envelope.perturbations()), PERTURBATIONS)
        self.assertEqual(self.envelope.baseline_endpoints(), (("G13", "low"), ("G23", "low")))
        for perturbation in self.envelope.perturbations():
            self.assertEqual(perturbation.envelope_hash, ENVELOPE_HASH)

    def test_frozen_rows_are_the_accepted_physical_strict_freezes(self):
        for spec in self.envelope.specimens:
            evidence = json.loads((DOCS / "registration_evidence" / f"{spec.label}_registration_reevaluation.json")
                                  .read_text(encoding="utf-8"))["results"]["PHYSICAL"]
            pairs = {pair["row_id"]: pair["fe_mode"] for pair in evidence["strict_pairs"]}
            holdouts = set(evidence["holdouts"]["holdout_row_ids"])
            record = json.loads((ROOT / spec.baseline_shape_pack).read_text(encoding="utf-8"))
            with self.subTest(specimen=spec.label):
                self.assertEqual(spec.row_modes, pairs)
                self.assertEqual({r.row_id for r in spec.rows if r.role == "HOLDOUT"}, holdouts)
                self.assertEqual(set(evidence["holdouts"]["fit_row_ids"]),
                                 {r.row_id for r in spec.rows if r.role == "FIT"})
                for pair in evidence["strict_pairs"]:
                    index = record["mode_numbers"].index(pair["fe_mode"])
                    self.assertEqual(record["frequencies_hz"][index], pair["fe_hz"])
        self.assertEqual({s.label: s.row_modes for s in self.envelope.specimens},
                         {"SP02": {"R1": 8, "R2": 10, "R3": 13}, "SP13": {"R1": 10, "R2": 13}})

    def test_every_endpoint_state_is_a_stable_material(self):
        base = PARAMETERISATIONS["carbon-property-set/v1"].engineering_constants(self.envelope.reference_candidate)
        for name in SCREENED_CONSTANTS:
            for value in (self.envelope.ranges[name].low, self.envelope.ranges[name].high):
                require_material_stability(EngineeringConstants(**dict(base.to_dict(), **{name: value})))

    def test_strict_parsing_refusals(self):
        cases = {
            "material-specific basis": {"basis": "MATERIAL_SPECIFIC"},
            "criterion changed": {"criterion__value": 0.005},
            "criterion not strict": {"criterion__comparison": "at_most"},
            "baseline not governed": {"constants__E3__baseline": 7000.0},
            "low above baseline": {"constants__nu13__low": 0.35},
            "low equals high": {"constants__nu23__low": 0.4, "constants__nu23__baseline": 0.4},
            "wrong unit": {"constants__G13__unit": "GPa"},
            "row outside extraction modes": {"specimens__0__rows__0__fe_mode": 31},
            "unknown row role": {"specimens__0__rows__0__role": "PROMOTED"},
            "absolute path": {"specimens__0__forward_model": "D:/x/SP02.forward.json"},
            "unstable endpoint": {"constants__nu23__high": 4.0},
            "reference candidate incomplete": {"reference_candidate": {"E_in_plane_mpa": 52000.0}},
        }
        for label, changes in cases.items():
            with self.subTest(case=label):
                with self.assertRaises(ScreeningEnvelopeError):
                    parse_screening_envelope(envelope_dict(**changes))
        data = envelope_dict()
        data["constants"]["nu12"] = {"unit": "1", "baseline": 0.05, "low": 0.04, "high": 0.06}
        with self.assertRaises(ScreeningEnvelopeError):
            parse_screening_envelope(data)
        data = envelope_dict()
        data["extra"] = 1
        with self.assertRaises(ScreeningEnvelopeError):
            parse_screening_envelope(data)
        data = envelope_dict()
        data["specimens"][0]["rows"].append({"row_id": "R1", "fe_mode": 20, "role": "FIT"})
        with self.assertRaises(ScreeningEnvelopeError):
            parse_screening_envelope(data)

    def test_classification_is_the_spec_rule(self):
        self.assertEqual(classify(0.0), NEGLIGIBLE)
        self.assertEqual(classify(0.0029999), NEGLIGIBLE)
        self.assertEqual(classify(0.003), INCLUDE)  # "< 0.3 %" is strict
        self.assertEqual(classify(0.08), INCLUDE)  # large is still bookkeeping, never a failure
        for bad in (-1e-6, float("nan"), float("inf")):
            with self.assertRaises(ScreeningEnvelopeError):
                classify(bad)

    def test_perturbation_objects_are_restricted(self):
        args = ("id", ENVELOPE_HASH)
        with self.assertRaises(ScreeningEnvelopeError):
            ScreeningPerturbation(*args, "nu12", "high", 0.06, 0.05)
        with self.assertRaises(ScreeningEnvelopeError):
            ScreeningPerturbation(*args, "E3", "middle", 6000.0, 6700.0)
        with self.assertRaises(ScreeningEnvelopeError):
            ScreeningPerturbation(*args, "G13", "low", 2200.0, 2200.0)  # the baseline is no perturbation


# ----------------------------------------------------------------------------- guarded screening jobs (synthetic INP)

class ScreeningJobTests(unittest.TestCase):
    def setUp(self):
        self.envelope = load_screening_envelope(ENVELOPE)
        self.raw = SYNTHETIC_INP.encode("latin-1")
        passport = synthetic_passport()
        self.model = bind_forward_model(forward_manifest(passport, self.raw), passport)
        self._directory = tempfile.TemporaryDirectory()
        self.tmp = Path(self._directory.name)

    def tearDown(self):
        self._directory.cleanup()

    def test_each_job_changes_exactly_its_constant(self):
        reference = carbon_candidate(52000.0, 4500.0).engineering_constants()
        for perturbation in self.envelope.perturbations():
            with self.subTest(perturbation=perturbation.perturbation_id):
                job = prepare_screening_job(self.model, self.envelope, perturbation, self.raw, self.tmp)
                written = locate_engineering_constants(split_inp_lines(job.generated_inp.read_bytes()),
                                                       "CFRP_Face").values
                expected = dict(reference.to_dict(), **{perturbation.constant: perturbation.value})
                self.assertEqual(written.to_dict(), expected)
                self.assertEqual(job.engineering_constants.to_dict(), expected)
                record = locate_engineering_constants(split_inp_lines(self.raw), "CFRP_Face")
                lines = split_inp_lines(self.raw)
                frequency = next(i for i, line in enumerate(lines) if line.startswith("*Frequency")) + 1
                allowed = {i + 1 for i in record.data_lines} | {frequency + 1}
                self.assertLessEqual(set(job.provenance["generated_inp"]["changed_lines"]), allowed)
                self.assertEqual(job.provenance["schema"], "auto-id/screening-forward-job/v1")
                self.assertEqual(job.provenance["candidate"], {"E_in_plane_mpa": 52000.0, "G12_mpa": 4500.0})
                self.assertEqual(job.provenance["screening"]["constant"], perturbation.constant)
                self.assertEqual(job.provenance["screening"]["envelope_hash"], ENVELOPE_HASH)
                self.assertEqual(job.provenance["screening"]["basis"], "LITERATURE_INTERIM_SCREENING_ENVELOPE")
                self.assertTrue(job.job_name.startswith("SYN_"))
                # Constants that are neither candidate nor perturbed keep their exact source text.
                generated = split_inp_lines(job.generated_inp.read_bytes())
                tokens = lambda text: [x.strip() for i in record.data_lines for x in text[i].split(",") if x.strip()]
                keep = [k for k, name in enumerate(EngineeringConstants.names())
                        if name not in ("E1", "E2", "G12", perturbation.constant)]
                self.assertEqual([tokens(generated)[k] for k in keep], [tokens(lines)[k] for k in keep])

    def test_jobs_are_distinct_from_each_other_and_from_the_reference(self):
        names = {prepare_screening_job(self.model, self.envelope, p, self.raw, self.tmp).job_name
                 for p in self.envelope.perturbations()}
        reference = prepare_forward_job(self.model, carbon_candidate(52000.0, 4500.0), self.raw, self.tmp)
        self.assertEqual(len(names), 8)
        self.assertNotIn(reference.job_name, names)

    def test_fitting_path_is_unchanged(self):
        reference = forward_builder.render_forward_input(self.model, carbon_candidate(52000.0, 4500.0), self.raw)
        self.assertEqual(reference.engineering_constants.E3, 6700.0)
        self.assertEqual(reference.engineering_constants.G13, 2200.0)
        self.assertEqual(list(PARAMETERISATIONS), ["carbon-property-set/v1"])  # screening is no parameterisation

    def test_unauthorised_perturbations_are_refused(self):
        forged = ScreeningPerturbation(self.envelope.envelope_id, ENVELOPE_HASH, "E3", "high", 12000.0, 6700.0)
        with self.assertRaises(ForwardBuildError):
            render_screening_input(self.model, self.envelope, forged, self.raw)
        other = parse_screening_envelope(envelope_dict(constants__E3__high=11000.0))
        foreign = other.perturbations()[1]
        with self.assertRaises(ForwardBuildError):  # another envelope's perturbation
            render_screening_input(self.model, self.envelope, foreign, self.raw)
        with self.assertRaises(TypeError):
            render_screening_input(self.model, {"envelope": "dict"}, self.envelope.perturbations()[0], self.raw)

    def test_a_source_other_than_the_pinned_input_is_refused(self):
        raw = SYNTHETIC_INP.replace(" 2200.,\n", " 2300.,\n").encode("latin-1")  # another G23 in the source
        with self.assertRaises(ForwardBuildError):
            render_screening_input(self.model, self.envelope, self.envelope.perturbations()[0], raw)


# ----------------------------------------------------------------------------- synthetic end-to-end (fake executors)

BASELINE_CONSTANTS = {"E3": 6700.0, "nu13": 0.3, "nu23": 0.3, "G13": 2200.0, "G23": 2200.0}
# Fake log-sensitivities (index into modes 7..30) of the screened constants.
EFFECTS = {"E3": {1: 0.001}, "nu13": {}, "nu23": {3: 0.02}, "G13": {1: 0.0036}, "G23": {20: 0.1}}


class ScreeningFakeSolver:
    def __init__(self):
        self.commands = []

    def __call__(self, command: str, directory: Path) -> int:
        import re

        self.commands.append(command)
        job = re.search(r"job=(\S+)", command).group(1)
        inp = Path(re.search(r"input=(\S+)", command).group(1))
        values = locate_engineering_constants(split_inp_lines(inp.read_bytes()), "CFRP_Face").values.to_dict()
        (directory / f"{job}.odb").write_text(json.dumps(values, sort_keys=True), encoding="utf-8")
        (directory / f"{job}.dat").write_text("   Abaqus 2024   Date 07-Oct-2026\n", encoding="utf-8")
        (directory / f"{job}.sta").write_text(" THE ANALYSIS HAS COMPLETED SUCCESSFULLY\n", encoding="utf-8")
        return 0


def screening_frequencies(values: dict) -> list[float]:
    hz = fake_frequencies(values["E1"], values["G12"])
    for name, effects in EFFECTS.items():
        for index, exponent in effects.items():
            hz[index] *= (values[name] / BASELINE_CONSTANTS[name]) ** exponent
    return hz


class ScreeningFakeExtractor:
    def __init__(self):
        self.calls = 0

    def __call__(self, odb: Path, raw: Path, start: int, end: int) -> Path:
        self.calls += 1
        hz = screening_frequencies(json.loads(Path(odb).read_text(encoding="utf-8")))
        raw.mkdir(parents=True, exist_ok=True)
        with open(raw / "geometry.csv", "w", encoding="utf-8") as handle:
            handle.write("instance,node_label,x,y,z\n")
            for node, xyz in zip(NODE_IDS, COORDS):
                instance, label = node.split(":")
                handle.write(f"{instance},{label}," + ",".join("%.16g" % v for v in xyz) + "\n")
        modes = []
        for k, mode in enumerate(range(start, end + 1)):
            values = np.zeros((len(NODE_IDS), 3))
            values[TOP_ROWS, 2] = SHAPES[k]
            name = f"mode_{mode:04d}.csv"
            with open(raw / name, "w", encoding="utf-8") as handle:
                handle.write("instance,node_label,u1_real,u2_real,u3_real,u1_imag,u2_imag,u3_imag\n")
                for node, row in zip(NODE_IDS, values):
                    instance, label = node.split(":")
                    handle.write(f"{instance},{label}," + ",".join("%.16g" % float(np.float32(v)) for v in row)
                                 + ",0,0,0\n")
            modes.append({"mode": mode, "frequency_hz": hz[k], "file": name})
        history = [[m, 0.0 if m < 7 else hz[m - 7]] for m in range(1, 31)]
        (raw / "manifest.json").write_text(json.dumps({"format_version": 2, "modes": modes,
                                                       "history": [{"name": "EIGFREQ", "data": history}]}),
                                           encoding="utf-8")
        return raw / "manifest.json"


def synthetic_envelope():
    data = envelope_dict()
    data["specimens"] = [{"label": "SYN", "forward_model": "x/SYN.forward.json", "solver_profile": "x/SYN.json",
                          "baseline_shape_pack": "x/SYN.shape-pack.json", "observation_source": "synthetic",
                          "rows": [{"row_id": "R1", "fe_mode": 8, "role": "FIT"},
                                   {"row_id": "R2", "fe_mode": 10, "role": "HOLDOUT"}]}]
    return parse_screening_envelope(data)


class SyntheticScreeningRunTests(unittest.TestCase):
    """Plan → HUMAN-gated run → evaluation on a synthetic model; every executor is a fake."""

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        tmp = self.tmp = Path(self._directory.name)
        store = tmp / "store"
        (store / "models").mkdir(parents=True)
        self.raw = SYNTHETIC_INP.replace("15, , , , ,", "30, , , , ,").encode("latin-1")
        (store / "models" / "syn.inp").write_bytes(self.raw)
        identity = {"schema_version": FE_IDENTITY["schema_version"], "sha256": FE_IDENTITY["sha256"],
                    "node_count": FE_IDENTITY["node_count"]}
        passport = synthetic_passport(fe_reference__geometry_identity=identity)
        manifest = forward_manifest(passport, self.raw, frequency_request__source_eigenvalue_count=30)
        self.model = bind_forward_model(manifest, passport)
        self.profile = parse_solver_profile(profile_dict())
        self.envelope = synthetic_envelope()
        # The archived baseline: the reference job solved and extracted once (fakes), recorded as BASELINE.
        baseline_root = tmp / "baseline"
        job = prepare_forward_job(self.model, carbon_candidate(52000.0, 4500.0), self.raw, tmp / "p0")
        solve = solve_forward_job(job, self.profile, baseline_root / "solves" / job.job_name, "abq2024.bat",
                                  ScreeningFakeSolver())
        partial = BoundScreeningSpecimen(self.envelope.specimens[0], self.model, self.profile,
                                         parse_shape_pack_record(self._record_stub(job)))
        extract_shape_pack(job.job_name, job.generated_inp_sha256,
                           baseline_root / "solves" / job.job_name / f"{job.job_name}.odb", solve.odb_sha256,
                           solve.odb_size_bytes, extraction_expectation(partial, self.envelope),
                           baseline_root / "packs", ScreeningFakeExtractor(), "Abaqus 2024")
        path = baseline_root / "packs" / f"{job.job_name}.shape-pack.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["state"] = "BASELINE"
        self.baseline = parse_shape_pack_record(record)
        self.specimen = BoundScreeningSpecimen(self.envelope.specimens[0], self.model, self.profile, self.baseline)
        self.roots = {"synthetic": store, "auto-id-run": baseline_root}
        self.plan = prepare_screening_plan(self.envelope, [self.specimen], self.roots, tmp / "run" / "jobs")

    def _record_stub(self, job) -> dict:
        from services.fe_shape_pack import node_set_sha256

        node_set = node_set_sha256([NODE_IDS[i] for i in TOP_ROWS])
        def file(name):
            return {"role": "x", "file_name": name, "sha256": "0" * 64, "size_bytes": 1,
                    "location": {"store": "x", "relative_path": name}}

        return {"schema": "auto-id/fe-shape-pack-record/v1", "job_name": job.job_name, "specimen": "SYN",
                "state": "BASELINE", "generated_inp_sha256": job.generated_inp_sha256,
                "odb": file(f"{job.job_name}.odb"), "pack": file(f"{job.job_name}.npz"),
                "content_sha256": "0" * 64, "node_set": {"definition": "TOP", "node_count": len(TOP_ROWS),
                                                         "sha256": node_set},
                "fe_geometry_sha256": FE_IDENTITY["sha256"], "mode_numbers": list(range(7, 31)),
                "frequencies_hz": [1.0] * 24, "extraction": {}, "validation": {"ok": True}, "provenance_record": {}}

    def tearDown(self):
        self._directory.cleanup()

    def config(self, solver, extractor, authorised=None):
        return ScreeningRunConfig(self.tmp / "run", self.roots, "abq2024.bat", solver, extractor,
                                  self.plan.manifest_hash if authorised is None else authorised)

    def test_plan_is_the_human_manifest(self):
        manifest = self.plan.manifest
        self.assertEqual(manifest["counts"], {"abaqus_solves": 8, "extraction_runs": 8, "baseline_solves": 0,
                                              "baseline_extractions": 0})
        self.assertEqual([job["perturbation_id"] for job in manifest["jobs"]], list(PERTURBATIONS))
        self.assertEqual(manifest["baselines"][0]["job_name"], self.baseline.job_name)
        self.assertEqual(manifest["baseline_endpoints"], [{"constant": "G13", "endpoint": "low"},
                                                          {"constant": "G23", "endpoint": "low"}])
        self.assertNotIn(":\\", json.dumps(manifest))
        again = prepare_screening_plan(self.envelope, [self.specimen], self.roots, self.tmp / "again")
        self.assertEqual(again.manifest_hash, self.plan.manifest_hash)

    def test_a_baseline_that_is_not_regenerated_is_refused(self):
        record = dict(json.loads(json.dumps(self._record_stub(prepare_forward_job(
            self.model, carbon_candidate(52000.0, 4600.0), self.raw, self.tmp / "other")))))
        stale = BoundScreeningSpecimen(self.envelope.specimens[0], self.model, self.profile,
                                       parse_shape_pack_record(record))
        with self.assertRaises(ScreeningError):
            prepare_screening_plan(self.envelope, [stale], self.roots, self.tmp / "stale")

    def test_run_requires_the_authorised_manifest(self):
        solver, extractor = ScreeningFakeSolver(), ScreeningFakeExtractor()
        with self.assertRaises(ScreeningError):
            run_screening(self.plan, self.config(solver, extractor, authorised="f" * 64))
        self.assertEqual((solver.commands, extractor.calls), ([], 0))

    def test_run_evaluate_and_resume(self):
        solver, extractor = ScreeningFakeSolver(), ScreeningFakeExtractor()
        summary = run_screening(self.plan, self.config(solver, extractor))
        self.assertEqual((summary["solves_executed"], summary["extractions_executed"]), (8, 8))
        again = run_screening(self.plan, self.config(ScreeningFakeSolver(), ScreeningFakeExtractor()))
        self.assertEqual((again["solves_executed"], again["extractions_executed"]), (0, 0))  # no duplicate solve

        baselines, candidates = load_screening_states(self.plan, self.tmp / "run", self.roots)
        result = evaluate_screening(self.envelope, STRICT_IDENTIFICATION_PAIRING, baselines, candidates,
                                    expected_jobs(self.plan), self.plan.manifest_hash)
        constants = result["constants"]
        self.assertEqual(constants["E3"]["classification"], NEGLIGIBLE)
        self.assertEqual(constants["nu13"]["classification"], NEGLIGIBLE)
        self.assertEqual(constants["nu13"]["max_abs_relative_change"], 0.0)
        # ν23 moves only the HOLDOUT row R2 (mode 10): holdouts are observations too.  The low endpoint
        # (≈ −0.81 %) moves it more than the high one (≈ +0.58 %): both endpoints are needed.
        self.assertEqual(constants["nu23"]["classification"], INCLUDE)
        self.assertAlmostEqual(constants["nu23"]["max_abs_relative_change"], 1 - (0.2 / 0.3) ** 0.02, places=12)
        # G13 just below the strict criterion: (5000/2200)^0.0036 − 1 ≈ 0.296 %.
        self.assertEqual(constants["G13"]["classification"], NEGLIGIBLE)
        self.assertLess(constants["G13"]["max_abs_relative_change"], 0.003)
        self.assertGreater(constants["G13"]["max_abs_relative_change"], 0.0029)
        self.assertEqual(constants["G13"]["baseline_endpoints"], ["low"])
        # G23 moves only an unobserved mode: the informational all-mode diagnostic sees it, the rule does not.
        self.assertEqual(constants["G23"]["classification"], NEGLIGIBLE)
        g23 = next(s for s in result["states"] if s["perturbation_id"] == "G23-high")
        self.assertFalse(g23["diagnostic_all_modes"]["used_for_classification"])
        self.assertGreater(g23["diagnostic_all_modes"]["max_abs_relative_change"], 0.05)
        self.assertEqual(result["include_in_uncertainty_budget"], ["nu23"])
        self.assertTrue(result["budget_closed"])
        self.assertEqual(result["manifest_hash"], self.plan.manifest_hash)
        nu23 = next(s for s in result["states"] if s["perturbation_id"] == "nu23-high")
        row = next(r for r in nu23["rows"] if r["row_id"] == "R2")
        self.assertAlmostEqual(row["log_sensitivity"], 0.02, places=6)
        self.assertEqual((row["role"], row["candidate_fe_mode"]), ("HOLDOUT", 10))
        repeat = evaluate_screening(self.envelope, STRICT_IDENTIFICATION_PAIRING, baselines, candidates,
                                    expected_jobs(self.plan), self.plan.manifest_hash)
        self.assertEqual(repeat["result_hash"], result["result_hash"])


# ----------------------------------------------------------------------------- evaluation on synthetic FE states

def state(state_id, frequencies, shapes=None):
    shapes = SHAPES if shapes is None else shapes
    return FEModalState(state_id, "g" * 64, "n" * 64, tuple(range(7, 31)), tuple(frequencies), shapes)


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.envelope = synthetic_envelope()
        self.base_hz = [20.0 * (1.1 ** k) for k in range(24)]
        self.baselines = {"SYN": state("BASE", self.base_hz)}
        self.jobs = {("SYN", "baseline"): "BASE"}
        self.jobs.update({("SYN", p): p for p in PERTURBATIONS})

    def candidates(self, overrides=None):
        overrides = overrides or {}
        return {("SYN", p): overrides.get(p, state(p, self.base_hz)) for p in PERTURBATIONS}

    def evaluate(self, candidates, policy=STRICT_IDENTIFICATION_PAIRING):
        return evaluate_screening(self.envelope, policy, self.baselines, candidates, self.jobs, "m" * 64)

    def test_tracking_refusal_leaves_the_constant_unclassified(self):
        shapes = SHAPES.copy()
        shapes[1] = (SHAPES[1] + SHAPES[2]) / math.sqrt(2)  # row R1 (mode 8) loses its identity
        result = self.evaluate(self.candidates({"E3-high": state("E3-high", self.base_hz, shapes)}))
        self.assertEqual(result["constants"]["E3"]["classification"], NOT_CLASSIFIED)
        self.assertIsNone(result["constants"]["E3"]["max_abs_relative_change"])
        self.assertEqual(result["constants"]["E3"]["tracking_refusals"], ["E3-high@SYN"])
        self.assertEqual(result["not_classified"], ["E3"])
        self.assertFalse(result["budget_closed"])
        self.assertEqual(result["constants"]["nu13"]["classification"], NEGLIGIBLE)

    def test_frequency_order_change_is_followed_by_shape(self):
        hz, shapes = list(self.base_hz), SHAPES.copy()
        hz[1], hz[2] = self.base_hz[2] * 1.0, self.base_hz[1] * 1.0  # modes 8 and 9 swap order …
        shapes[1], shapes[2] = SHAPES[2], SHAPES[1]  # … with their shapes: identity is kept
        result = self.evaluate(self.candidates({"nu13-low": state("nu13-low", hz, shapes)}))
        entry = next(s for s in result["states"] if s["perturbation_id"] == "nu13-low")
        row = next(r for r in entry["rows"] if r["row_id"] == "R1")
        self.assertEqual((row["baseline_fe_mode"], row["candidate_fe_mode"]), (8, 9))
        self.assertEqual(row["relative_change"], 0.0)
        self.assertEqual(result["constants"]["nu13"]["classification"], NEGLIGIBLE)

    def test_incomplete_or_foreign_evidence_is_refused(self):
        candidates = self.candidates()
        del candidates[("SYN", "G23-high")]
        with self.assertRaises(ScreeningError):
            self.evaluate(candidates)
        candidates = self.candidates({"G23-high": state("SOMETHING_ELSE", self.base_hz)})
        with self.assertRaises(ScreeningError):
            self.evaluate(candidates)
        weak = IdentificationPairingPolicy("weak", 0.5, 0.15, 0.5, 2, 1e-9)
        with self.assertRaises(Exception):
            self.evaluate(self.candidates(), weak)


# ----------------------------------------------------------------------------- architecture guards

def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    found |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    return found


class GuardTests(unittest.TestCase):
    MODULES = (ROOT / "src" / "domain" / "transverse_screening.py", ROOT / "src" / "services" / "transverse_screening.py")

    def test_generic_modules_name_no_specimen_or_machine_path(self):
        for module in self.MODULES:
            text = module.read_text(encoding="utf-8")
            for token in ("SP02", "SP13", "SP-02", "SP-13", "Snadwich", "snadwich", "carbon_project_archive", "D:\\",
                          "CFRP_T300_PlainWeave", "CFRP_Face"):
                with self.subTest(module=module.name, token=token):
                    self.assertNotIn(token, text)

    def test_controlled_imports(self):
        forbidden = ("subprocess", "abaqus_bridge", "shared_carbon_forward", "matrix_model_service", "modal_core",
                     "sp13_evidence_adapter")
        for module in self.MODULES:
            for imported in _imports(module):
                with self.subTest(module=module.name, imported=imported):
                    self.assertFalse(any(imported == n or imported.endswith("." + n) for n in forbidden))

    def test_no_fitting_or_verdict_module_uses_screening(self):
        allowed = {ROOT / "src" / "services" / "forward_builder.py", ROOT / "src" / "services" / "transverse_screening.py"}
        for path in sorted((ROOT / "src").rglob("*.py")):
            if path in allowed or path == self.MODULES[0]:
                continue
            with self.subTest(module=str(path.relative_to(ROOT))):
                self.assertFalse(any(name.endswith("transverse_screening") for name in _imports(path)))

    def test_screening_functions_have_no_defaults(self):
        import inspect

        for function in (forward_builder.render_screening_input, forward_builder.prepare_screening_job,
                         prepare_screening_plan, evaluate_screening, run_screening):
            with self.subTest(function=function.__name__):
                parameters = inspect.signature(function).parameters.values()
                self.assertTrue(all(p.default is inspect.Parameter.empty for p in parameters))

    def test_tool_run_refuses_an_unauthorised_hash_before_any_executor(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import m6_4_transverse_screening as tool

        plan = mock.Mock(manifest_hash="a" * 64)
        with mock.patch.object(tool, "build_plan", return_value=plan), \
                mock.patch.object(tool, "run_screening", side_effect=AssertionError("must not run")), \
                mock.patch("services.forward_solver.subprocess_executor",
                           side_effect=AssertionError("no executor")):
            with self.assertRaises(ScreeningError):
                tool.main(["run", "--run-root", str(Path(tempfile.gettempdir()) / "m64-guard"), "--abaqus", "abq",
                           "--authorised-manifest-hash", "b" * 64])


# ----------------------------------------------------------------------------- real stores (skipped without them)

class RealPlanTests(unittest.TestCase):
    """The HUMAN Abaqus manifest of the real SP-02 / SP-13 screening (renders 16 INPs; no Abaqus)."""

    @classmethod
    def setUpClass(cls):
        roots = fixture_roots_from_environment()
        if "snadwich" not in roots:
            raise unittest.SkipTest("data store 'snadwich' not configured")
        from services.transverse_screening import bind_screening_specimens

        cls._directory = tempfile.TemporaryDirectory()
        envelope = load_screening_envelope(ENVELOPE)
        fixtures = load_experiment_fixture_manifest(DOCS / "fixtures" / "real_experiment_fixtures.json")
        cls.specimens = bind_screening_specimens(envelope, ROOT, fixtures)
        cls.plan = prepare_screening_plan(envelope, cls.specimens, roots, Path(cls._directory.name))

    @classmethod
    def tearDownClass(cls):
        cls._directory.cleanup()

    def test_manifest_is_pinned(self):
        self.assertEqual(self.plan.manifest_hash, MANIFEST_HASH)
        self.assertEqual(self.plan.manifest["counts"], {"abaqus_solves": 16, "extraction_runs": 16,
                                                        "baseline_solves": 0, "baseline_extractions": 0})
        for label, names in REAL_JOBS.items():
            jobs = [j for j in self.plan.manifest["jobs"] if j["specimen"] == label]
            with self.subTest(specimen=label):
                self.assertEqual(tuple(j["job_name"] for j in jobs), names)
                self.assertEqual(tuple(j["perturbation_id"] for j in jobs), PERTURBATIONS)

    def test_baselines_are_the_archived_carbon4c_jobs(self):
        self.assertEqual([b["job_name"] for b in self.plan.manifest["baselines"]],
                         ["SP02_f3e592281bebce66", "SP13_a46d08b52995e078"])

    def test_only_the_material_record_and_the_accepted_eigenvalue_line_change(self):
        expected = {"SP02": [2077230, 2077231, 2077244], "SP13": [1957765, 1957766]}  # = the M3.5 anchors
        for job in self.plan.manifest["jobs"]:
            with self.subTest(job=job["job_name"]):
                self.assertEqual(job["changed_lines"], expected[job["specimen"]])
                self.assertEqual(job["requested_eigenvalue_count"], 30)

    def test_extraction_expectation_is_the_baseline_node_set(self):
        envelope = self.plan.envelope
        for specimen in self.specimens:
            expectation = extraction_expectation(specimen, envelope)
            with self.subTest(specimen=specimen.label):
                self.assertEqual((expectation.node_set_sha256, expectation.node_count),
                                 (specimen.baseline.node_set_sha256, specimen.baseline.node_set_count))
                self.assertEqual(expectation.mode_numbers, tuple(range(7, 31)))


if __name__ == "__main__":
    unittest.main()
