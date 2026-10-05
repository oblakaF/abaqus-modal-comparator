"""Fake Abaqus solver / extractor and synthetic pipeline configurations for the M4.6 tests (no Abaqus)."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np

from domain.forward_model_manifest import bind_forward_model, carbon_candidate
from domain.frozen_observations import BaselineIdentity, FreezeStatus, FrozenObservationSet, ObservationRow
from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING
from domain.identification_run import parse_solver_profile
from m3_support import SYNTHETIC_INP, forward_manifest, synthetic_passport
from scientific_state import fe_geometry_identity
from services.fe_shape_pack import node_set_sha256
from services.forward_builder import locate_engineering_constants, prepare_forward_job, split_inp_lines
from services.identification_objective import RowSigma, build_objective_design
from services.identification_pipeline import PipelineConfig
from services.identification_step import LMSettings, parameter_bounds
from services.shape_extraction import ExtractionExpectation


P0 = {"E_in_plane_mpa": 52000.0, "G12_mpa": 4500.0}
TRUTH = {"E_in_plane_mpa": 45000.0, "G12_mpa": 4000.0}
MODES = tuple(range(7, 31))
GRID = 8  # TOP surface nodes per side (64 >= 24 modes)
# Log-sensitivities (E, G12) and baseline frequencies of the fake elastic modes (well separated).
EXPONENTS = [(0.013, 0.469), (0.492, 0.001), (0.364, 0.123), (0.291, 0.191), (0.48, 0.003), (0.44, 0.044)] * 4
BASE_HZ = [22.5 * (1.12 ** k) for k in range(24)]
APPROVED_LM = LMSettings(mu_initial=1e-3, mu_decrease=10.0, max_step_attempts=3, solve_budget=20)


def _nodes():
    xs = np.arange(GRID) * 62.5  # exactly representable (real ODB coordinates are single precision)
    ids, coords = [], []
    for instance, z in (("BOT", 0.0), ("CORE", 1.0), ("TOP", 2.0)):
        for i, (x, y) in enumerate([(x, y) for x in xs for y in xs], start=1):
            ids.append(f"{instance}:{i}")
            coords.append((x, y, z))
    return ids, np.array(coords)


NODE_IDS, COORDS = _nodes()
TOP_ROWS = [i for i, node in enumerate(NODE_IDS) if node.startswith("TOP:")]
SHAPES = np.linalg.qr(np.random.default_rng(13).normal(size=(len(TOP_ROWS), 24)))[0].T  # orthonormal U3 shapes
FE_IDENTITY = fe_geometry_identity(NODE_IDS, COORDS)
NODE_SET = node_set_sha256([NODE_IDS[i] for i in TOP_ROWS])


def fake_frequencies(e: float, g: float) -> list[float]:
    return [f0 * (e / P0["E_in_plane_mpa"]) ** a * (g / P0["G12_mpa"]) ** b
            for f0, (a, b) in zip(BASE_HZ, EXPONENTS)]


class FakeSolver:
    """Executor for ``forward_solver``: reads E/G12 from the generated INP; writes fake ODB/.sta/.dat."""

    def __init__(self, material="CFRP_Face", fail_jobs=(), crash_after=None, ok_marker=True):
        self.material, self.fail_jobs, self.crash_after, self.ok_marker = material, set(fail_jobs), crash_after, ok_marker
        self.commands = []

    def __call__(self, command: str, directory: Path) -> int:
        if self.crash_after is not None and len(self.commands) >= self.crash_after:
            raise KeyboardInterrupt("simulated interruption")
        self.commands.append(command)
        job = re.search(r"job=(\S+)", command).group(1)
        inp = Path(re.search(r"input=(\S+)", command).group(1))
        record = locate_engineering_constants(split_inp_lines(inp.read_bytes()), self.material).values
        odb = {"inp_sha256": hashlib.sha256(inp.read_bytes()).hexdigest(), "E": record.E1, "G12": record.G12}
        (directory / f"{job}.odb").write_text(json.dumps(odb, sort_keys=True), encoding="utf-8")
        (directory / f"{job}.dat").write_text("   Abaqus 2024   Date 04-Oct-2026\n", encoding="utf-8")
        completed = self.ok_marker and job not in self.fail_jobs
        (directory / f"{job}.sta").write_text(" THE ANALYSIS HAS COMPLETED SUCCESSFULLY\n" if completed else
                                              " ***ERROR: analysis aborted\n", encoding="utf-8")
        return 0


class FakeExtractor:
    """Executor for ``shape_extraction``: writes a format-2 raw extraction for the fake ODB."""

    def __init__(self, exchange_below_e=None, fail=False):
        self.exchange_below_e, self.fail = exchange_below_e, fail
        self.calls = 0

    def __call__(self, odb: Path, raw: Path, start: int, end: int) -> Path:
        if self.fail:
            raise KeyboardInterrupt("simulated extraction interruption")
        self.calls += 1
        data = json.loads(Path(odb).read_text(encoding="utf-8"))
        hz = fake_frequencies(data["E"], data["G12"])
        shapes = SHAPES.copy()
        if self.exchange_below_e is not None and data["E"] < self.exchange_below_e:
            a, b = shapes[2].copy(), shapes[3].copy()  # modes 9 and 10 exchange character
            shapes[2], shapes[3] = (a + b) / math.sqrt(2), (a - b) / math.sqrt(2)
        raw.mkdir(parents=True, exist_ok=True)
        with open(raw / "geometry.csv", "w", encoding="utf-8") as handle:
            handle.write("instance,node_label,x,y,z\n")
            for node, xyz in zip(NODE_IDS, COORDS):
                instance, label = node.split(":")
                handle.write(f"{instance},{label}," + ",".join("%.16g" % v for v in xyz) + "\n")
        modes = []
        for k, mode in enumerate(range(start, end + 1)):
            values = np.zeros((len(NODE_IDS), 3))
            values[TOP_ROWS, 2] = shapes[k]
            name = f"mode_{mode:04d}.csv"
            with open(raw / name, "w", encoding="utf-8") as handle:
                handle.write("instance,node_label,u1_real,u2_real,u3_real,u1_imag,u2_imag,u3_imag\n")
                for node, row in zip(NODE_IDS, values):
                    instance, label = node.split(":")
                    handle.write(f"{instance},{label}," + ",".join("%.16g" % float(np.float32(v)) for v in row)
                                 + ",0,0,0\n")
            modes.append({"mode": mode, "frequency_hz": float("%.5g" % hz[k]), "file": name})
        history = [[m, 0.0 if m < 7 else hz[m - 7]] for m in range(1, 31)]
        manifest = {"format_version": 2, "modes": modes, "history": [{"name": "EIGFREQ", "data": history}]}
        (raw / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return raw / "manifest.json"


def profile_dict(**changes):
    data = {"schema": "auto-id/solver-profile/v1", "profile_id": "SYN/fake", "forward_model_id":
            "SYN_MODEL/carbon-property-set-v1", "job_prefix": "SYN", "abaqus_release": "Abaqus 2024",
            "command_template": "{abaqus} job={job} input={inp} cpus={cpus}{scratch} interactive ask_delete=OFF",
            "cpus": 1, "scratch": None, "completion_marker": "THE ANALYSIS HAS COMPLETED SUCCESSFULLY",
            "version_marker": "Abaqus 2024", "provenance": ["synthetic test profile"]}
    data.update(changes)
    return data


def build_config(tmp: Path, **changes) -> PipelineConfig:
    """A complete synthetic pipeline configuration (store 'synthetic' holds the reference INP)."""
    store = tmp / "store"
    (store / "models").mkdir(parents=True, exist_ok=True)
    raw = SYNTHETIC_INP.replace("15, , , , ,", "30, , , , ,").encode("latin-1")
    (store / "models" / "syn.inp").write_bytes(raw)
    passport = synthetic_passport()
    manifest = forward_manifest(passport, raw, frequency_request__source_eigenvalue_count=30)
    model = bind_forward_model(manifest, passport)
    p0_job = prepare_forward_job(model, carbon_candidate(**{"e_in_plane_mpa": P0["E_in_plane_mpa"],
                                                            "g12_mpa": P0["G12_mpa"]}), raw, tmp / "p0")
    identity = BaselineIdentity(manifest.forward_model_id, p0_job.job_name, p0_job.generated_inp_sha256,
                                FE_IDENTITY["sha256"], manifest.registration_hash, "3" * 64, "set", ("U3",),
                                "synthetic-twin", None)
    exp = fake_frequencies(TRUTH["E_in_plane_mpa"], TRUTH["G12_mpa"])
    base = fake_frequencies(P0["E_in_plane_mpa"], P0["G12_mpa"])
    rows = tuple(ObservationRow(f"R{k + 1}", k + 1, exp[k], MODES[k], base[k], 0.99, base[k] / exp[k] - 1)
                 for k in range(6))
    frozen = FrozenObservationSet(identity, STRICT_IDENTIFICATION_PAIRING.policy_id,
                                  STRICT_IDENTIFICATION_PAIRING.policy_hash, FreezeStatus.FROZEN, (), rows, (), (), ())
    design = build_objective_design(frozen, [], [], {row.row_id: RowSigma(0.003, 0.0, False) for row in rows}, 2)
    values = dict(
        run_root=tmp / "runs", model=model, profile=parse_solver_profile(profile_dict()), frozen=frozen,
        design=design, policy=STRICT_IDENTIFICATION_PAIRING, settings=APPROVED_LM,
        bounds=parameter_bounds([("E_in_plane_mpa", 20000.0, 120000.0), ("G12_mpa", 1000.0, 12000.0)]),
        start=dict(P0),
        expectation=ExtractionExpectation("TOP", "max_z", 1e-4, FE_IDENTITY["sha256"], FE_IDENTITY["node_count"],
                                          NODE_SET, len(TOP_ROWS), MODES),
        roots={"synthetic": store}, abaqus_command="abq2024.bat", solve_executor=FakeSolver(),
        extraction_executor=FakeExtractor())
    values.update(changes)
    return PipelineConfig(**values)
