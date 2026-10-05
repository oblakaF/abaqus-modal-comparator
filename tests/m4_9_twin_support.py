"""Plate-like fake Abaqus extractor and synthetic-twin configurations for the M4.9 preparation tests (no Abaqus).

The fake FE model has 24 elastic modes (7–30) on a symmetric 12 × 12 outer-surface grid.  Each
mode is a product of plate-like cosines cos(m·π·(s+1)/2) in x and y, so the M4.3 classifier
sees real parities and nodal lines.  Frequencies follow f0·(E/E0)^a·(G/G0)^b; mode numbers are
assigned by ascending frequency in every state, as Abaqus does.  Two deliberate close pairs:

- ``rotating``: (2,0)/(0,2), 1.5 % apart; the pair's shapes rotate within their own subspace with
  E by 20°·tanh(36.6·(E/E0 − 1)) — about 19° at ±5 % (individual MAC ≈ 0.894 < 0.9, subspace
  exact), about 20° at the truth (MAC ≈ 0.883 ≥ 0.8): a cluster M4.4 must CONFIRM;
- ``stable``: (2,1)/(1,2), 2 % apart, fixed shapes: triggered, but INDEPENDENT.

Variants: ``triple`` (a third mode within 3 % of ``stable``: UNSUPPORTED group), ``leak`` (the
rotating pair's first mode rotates towards a distant mode instead, so the pair's subspace is not
stable: UNSTABLE), ``top-pair`` (the rotating pair is the highest slot, so the validation holdout
takes one member of the CONFIRMED cluster: split).
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from domain.forward_model_manifest import bind_forward_model
from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING
from domain.identification_run import parse_solver_profile
from m3_support import SYNTHETIC_INP, forward_manifest, synthetic_passport
from m4_6_support import APPROVED_LM, P0, TRUTH, FakeSolver, profile_dict
from scientific_state import fe_geometry_identity
from services.fe_shape_pack import node_set_sha256, parse_shape_pack_record
from services.forward_builder import prepare_forward_job
from services.forward_solver import solve_forward_job
from services.identification_pipeline import forward_candidate
from services.identification_step import parameter_bounds
from services.shape_extraction import ExtractionExpectation, extract_shape_pack
from services.synthetic_twin import TWIN_SCHEMA, parse_twin_definition, perturbed_points


MODES = tuple(range(7, 31))
GRID = 12
SPAN = 45.0 * (GRID - 1)


def _nodes():
    xs = np.arange(GRID) * 45.0  # exactly representable
    ids, coords = [], []
    for instance, z in (("BOT", 0.0), ("CORE", 1.0), ("TOP", 2.0)):
        for i, (x, y) in enumerate([(x, y) for x in xs for y in xs], start=1):
            ids.append(f"{instance}:{i}")
            coords.append((x, y, z))
    return ids, np.array(coords)


NODE_IDS, COORDS = _nodes()
TOP_ROWS = [i for i, node in enumerate(NODE_IDS) if node.startswith("TOP:")]
TOP_IDS = [NODE_IDS[i] for i in TOP_ROWS]
FE_IDENTITY = fe_geometry_identity(NODE_IDS, COORDS)
NODE_SET = node_set_sha256(TOP_IDS)
_U = COORDS[TOP_ROWS, 0] / SPAN * 2.0 - 1.0
_V = COORDS[TOP_ROWS, 1] / SPAN * 2.0 - 1.0


def plate_shape(mx: int, my: int) -> np.ndarray:
    shape = np.cos(mx * math.pi * (_U + 1.0) / 2.0) * np.cos(my * math.pi * (_V + 1.0) / 2.0)
    return shape / np.linalg.norm(shape)


@dataclass(frozen=True)
class FakeMode:
    name: str
    waves: tuple[int, int]
    f0: float  # Hz at P0
    a: float  # d ln f / d ln E
    b: float  # d ln f / d ln G12


_SINGLE_WAVES = [(2, 2), (3, 0), (0, 3), (3, 1), (1, 3), (3, 2), (2, 3), (3, 3), (4, 0), (0, 4), (4, 1), (1, 4),
                 (4, 2), (2, 4), (4, 3), (3, 4), (4, 4), (5, 0), (0, 5)]
_EXPONENTS = [(0.48, 0.02), (0.32, 0.18), (0.42, 0.08), (0.36, 0.14), (0.5, 0.0), (0.3, 0.2)]
ROTATING_SLOT, STABLE_SLOT, TOP_SLOT = 5, 9, 21
VARIANTS = (None, "triple", "leak", "top-pair")


def fake_modes(variant: str | None = None) -> list[FakeMode]:
    """22 frequency slots 12 % apart; each pair shares a slot."""
    if variant not in VARIANTS:
        raise ValueError(variant)
    rotating_slot = TOP_SLOT if variant == "top-pair" else ROTATING_SLOT
    singles = iter(_SINGLE_WAVES)
    modes = [FakeMode("torsion", (1, 1), 20.0, 0.02, 0.49)]
    for slot in range(1, 22):
        f0 = 20.0 * 1.12 ** slot
        a, b = _EXPONENTS[slot % len(_EXPONENTS)]
        if slot == rotating_slot:
            modes += [FakeMode("rotating-1", (2, 0), f0, a, b), FakeMode("rotating-2", (0, 2), f0 * 1.015, a, b)]
        elif slot == STABLE_SLOT:
            modes += [FakeMode("stable-1", (2, 1), f0, a, b), FakeMode("stable-2", (1, 2), f0 * 1.02, a, b)]
        else:
            waves = next(singles)
            if variant == "triple" and slot == STABLE_SLOT + 1:
                f0 = 20.0 * 1.12 ** STABLE_SLOT * 1.04
                a, b = _EXPONENTS[STABLE_SLOT % len(_EXPONENTS)]
            modes.append(FakeMode(f"single-{waves[0]}{waves[1]}", waves, f0, a, b))
    assert len(modes) == len(MODES)
    return modes


def rotation_angle(e: float, amplitude_deg: float) -> float:
    return math.radians(amplitude_deg) * math.tanh(36.6 * (e / P0["E_in_plane_mpa"] - 1.0))


def fake_state(e: float, g: float, rotation_deg: float = 20.0, variant: str | None = None, exchange=None):
    """(mode numbers 7–30 by ascending frequency) → (frequency, U3 shape on TOP, name)."""
    modes = fake_modes(variant)
    shapes = {m.name: plate_shape(*m.waves) for m in modes}
    theta = rotation_angle(e, rotation_deg)
    partner = "single-22" if variant == "leak" else "rotating-2"  # leak: rotation out of the pair's subspace
    a, b = shapes["rotating-1"], shapes[partner]
    shapes["rotating-1"] = math.cos(theta) * a + math.sin(theta) * b
    shapes[partner] = -math.sin(theta) * a + math.cos(theta) * b
    if exchange is not None and exchange(e, g):  # injected loss of character between two fit modes
        left, right = shapes["single-22"].copy(), shapes["single-30"].copy()
        shapes["single-22"], shapes["single-30"] = (left + right) / math.sqrt(2), (left - right) / math.sqrt(2)
    hz = {m.name: m.f0 * (e / P0["E_in_plane_mpa"]) ** m.a * (g / P0["G12_mpa"]) ** m.b for m in modes}
    order = sorted(hz, key=lambda name: hz[name])
    return [(hz[name], shapes[name], name) for name in order]


class TwinFakeExtractor:
    """Executor for ``shape_extraction``: a format-2 raw extraction of the plate-like fake ODB."""

    def __init__(self, rotation_deg: float = 20.0, variant: str | None = None, exchange=None, fail: bool = False):
        self.rotation_deg, self.variant, self.exchange, self.fail = rotation_deg, variant, exchange, fail
        self.calls = 0

    def __call__(self, odb: Path, raw: Path, start: int, end: int) -> Path:
        if self.fail:
            raise KeyboardInterrupt("simulated extraction interruption")
        self.calls += 1
        data = json.loads(Path(odb).read_text(encoding="utf-8"))
        state = fake_state(data["E"], data["G12"], self.rotation_deg, self.variant, self.exchange)
        raw.mkdir(parents=True, exist_ok=True)
        with open(raw / "geometry.csv", "w", encoding="utf-8") as handle:
            handle.write("instance,node_label,x,y,z\n")
            for node, xyz in zip(NODE_IDS, COORDS):
                instance, label = node.split(":")
                handle.write(f"{instance},{label}," + ",".join("%.16g" % v for v in xyz) + "\n")
        modes = []
        for k, mode in enumerate(range(start, end + 1)):
            values = np.zeros((len(NODE_IDS), 3))
            values[TOP_ROWS, 2] = state[k][1]
            name = f"mode_{mode:04d}.csv"
            with open(raw / name, "w", encoding="utf-8") as handle:
                handle.write("instance,node_label,u1_real,u2_real,u3_real,u1_imag,u2_imag,u3_imag\n")
                for node, row in zip(NODE_IDS, values):
                    instance, label = node.split(":")
                    handle.write(f"{instance},{label}," + ",".join("%.16g" % float(np.float32(v)) for v in row)
                                 + ",0,0,0\n")
            modes.append({"mode": mode, "frequency_hz": float("%.5g" % state[k][0]), "file": name})
        history = [[m, 0.0 if m < 7 else state[m - 7][0]] for m in range(1, 31)]
        manifest = {"format_version": 2, "modes": modes, "history": [{"name": "EIGFREQ", "data": history}]}
        (raw / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return raw / "manifest.json"


def twin_definition_dict(model, **changes) -> dict:
    data = {"schema": TWIN_SCHEMA, "twin_id": "SYN/twin-test", "forward_model_id": model.manifest.forward_model_id,
            "truth": dict(TRUTH), "start": dict(P0), "noise_relative_sd": 0.003, "noise_seed": 20261005,
            "mode_numbers": list(MODES), "sigma": 0.003, "k_int_enabled": False,
            "provenance": ["synthetic test twin (fake solver)"]}
    data.update(changes)
    return data


def registration_for(model):
    """A FrozenRegistration stand-in: every TOP node measured in U3, experimental frame rotated 90° about z."""
    rotation = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    return SimpleNamespace(registration_hash=model.manifest.registration_hash, rotation=rotation,
                           experimental_node_ids=tuple(f"P{k}" for k in range(1, len(TOP_IDS) + 1)),
                           mapped_fe_node_ids=tuple(TOP_IDS), measured_dof_contract=[[False, False, True]] * len(TOP_IDS))


def build_model(tmp: Path):
    store = tmp / "store"
    (store / "models").mkdir(parents=True, exist_ok=True)
    raw = SYNTHETIC_INP.replace("15, , , , ,", "30, , , , ,").encode("latin-1")
    (store / "models" / "syn.inp").write_bytes(raw)
    passport = synthetic_passport()
    manifest = forward_manifest(passport, raw, frequency_request__source_eigenvalue_count=30)
    return bind_forward_model(manifest, passport), raw, store


EXPECTATION = ExtractionExpectation("TOP", "max_z", 1e-4, FE_IDENTITY["sha256"], FE_IDENTITY["node_count"],
                                    NODE_SET, len(TOP_IDS), MODES)


def archive_packs(tmp: Path, model, raw: bytes, profile, extractor: TwinFakeExtractor) -> dict:
    """Validated packs of p0 and the ±5 % points (stand-ins for the archived SP13 packs), via the M4.6 path."""
    archive = tmp / "archive"
    points = {"p0": dict(P0), **perturbed_points(P0, APPROVED_LM.finite_difference_step)}
    records = {}
    for point in points.values():
        job = prepare_forward_job(model, forward_candidate(model, point), raw, archive / "jobs")
        solve = solve_forward_job(job, profile, archive / "solves" / job.job_name, "abq2024.bat", FakeSolver())
        extract_shape_pack(job.job_name, job.generated_inp_sha256, archive / "solves" / job.job_name / f"{job.job_name}.odb",
                           solve.odb_sha256, solve.odb_size_bytes, EXPECTATION, archive / "packs", extractor,
                           profile.abaqus_release)
        path = archive / "packs" / f"{job.job_name}.shape-pack.json"
        records[job.job_name] = parse_shape_pack_record(json.loads(path.read_text(encoding="utf-8")))
    return records, archive


def twin_case(tmp: Path, definition_changes=None, extractor=None, archive_extractor=None, truth_extractor=None,
              solver=None, truth_solver=None, settings=APPROVED_LM):
    """(definition, registration, pipeline_fields, truth executors) for one synthetic twin."""
    tmp = Path(tmp)
    model, raw, store = build_model(tmp)
    profile = parse_solver_profile(profile_dict())
    records, archive = archive_packs(tmp, model, raw, profile, archive_extractor or TwinFakeExtractor())
    definition = parse_twin_definition(twin_definition_dict(model, **(definition_changes or {})))
    fields = dict(run_root=tmp / "runs", model=model, profile=profile, policy=STRICT_IDENTIFICATION_PAIRING,
                  settings=settings,
                  bounds=parameter_bounds([("E_in_plane_mpa", 20000.0, 120000.0), ("G12_mpa", 1000.0, 12000.0)]),
                  start=dict(P0), expectation=EXPECTATION, roots={"synthetic": store, "auto-id-run": archive},
                  abaqus_command="abq2024.bat", solve_executor=solver or FakeSolver(),
                  extraction_executor=extractor or TwinFakeExtractor(), archived_packs=records)
    truth = (truth_solver or FakeSolver(), truth_extractor or TwinFakeExtractor())
    return definition, registration_for(model), fields, truth
