"""Shared synthetic INP / forward-model builders for the M3 tests (not a test module)."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path

from domain.forward_model_manifest import parse_forward_model_manifest
from m2_support import parse as parse_passport


ROOT = Path(__file__).resolve().parents[1]
FORWARD_MODELS = ROOT / "docs" / "auto_id" / "forward_models"
SPECIMENS = ROOT / "docs" / "auto_id" / "specimens"
FIXTURES = ROOT / "docs" / "auto_id" / "fixtures" / "real_experiment_fixtures.json"

SOURCE_CONSTANTS = {"E1": 52000.0, "E2": 52000.0, "E3": 6700.0, "nu12": 0.05, "nu13": 0.3, "nu23": 0.3,
                    "G12": 4500.0, "G13": 2200.0, "G23": 2200.0}

# A small sandwich-like input in the same layout as the accepted SP02/SP13 inputs.
SYNTHETIC_INP = """*Heading
** Job name: SYN Model name: Model-1
*Part, name=Face
*Node
      1,           0.,           0.,           0.
      2,           3.,           0.,           0.
      3,           3.,           3.,           0.
      4,           0.,           3.,           0.
      5,           0.,           0.,        0.45
      6,           3.,           0.,        0.45
      7,           3.,           3.,        0.45
      8,           0.,           3.,        0.45
*Element, type=C3D8I
1, 1, 2, 3, 4, 5, 6, 7, 8
*Elset, elset=Set-1, generate
 1, 1, 1
*Orientation, name=Ori-1
          1.,           0.,           0.,           0.,           1.,           0.
3, 0.
*Solid Section, elset=Set-1, orientation=Ori-1, material=CFRP_Face
,
*Nonstructural Mass, elset=Set-1, units=TOTAL MASS, distribution=VOLUME PROPORTIONAL
3.32e-05,
*End Part
*Assembly, name=Assembly
*Instance, name=Face-1, part=Face
*End Instance
*Tie, name=T, adjust=yes, type=SURFACE TO SURFACE
s_Surf-3, m_Surf-3
*End Assembly
**
** MATERIALS
**
*Material, name=Adhesive_DP420
*Density
 1.2e-09,
*Elastic
 1800., 0.38
*Material, name=CFRP_Face
*Density
 1.57e-09,
*Elastic, type=ENGINEERING CONSTANTS
52000.,52000., 6700.,  0.05,   0.3,   0.3, 4500., 2200.
 2200.,
*Material, name=Core_PLA
*Density
 1.0475e-09,
*Elastic, type=ENGINEERING CONSTANTS
2580.,2580.,2060., 0.33, 0.33, 0.33, 970., 850.
 850.,
** ----------------------------------------------------------------
*Step, name=Modal, nlgeom=NO, perturbation
*Frequency, eigensolver=Lanczos, sim, acoustic coupling=on, normalization=mass
15, , , , ,
*End Step
"""
CARBON_DATA = ("52000.,52000., 6700.,  0.05,   0.3,   0.3, 4500., 2200.\n", " 2200.,\n")
FREQUENCY_DATA = "15, , , , ,\n"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def synthetic_passport(**overrides):
    return parse_passport(**overrides)


def forward_dict(passport=None, inp: bytes | None = None, **overrides) -> dict:
    """A valid synthetic forward-model manifest for SYNTHETIC_INP in a store 'synthetic'."""
    inp = SYNTHETIC_INP.encode("latin-1") if inp is None else inp
    passport = synthetic_passport() if passport is None else passport
    data = {
        "schema": "auto-id/forward-model/v1",
        "forward_model_id": "SYN_MODEL/carbon-property-set-v1",
        "specimen_passport": {"path": "docs/auto_id/specimens/SYN.specimen.json",
                              "manifest_hash": passport.manifest_hash},
        "model_input": {"role": "accepted source Abaqus input", "file_name": "syn.inp", "sha256": sha256(inp),
                        "size_bytes": len(inp), "location": {"store": "synthetic", "relative_path": "models/syn.inp"}},
        "job_prefix": "SYN",
        "material": {"role": "face", "elastic_type": "ENGINEERING CONSTANTS",
                     "source_engineering_constants": dict(SOURCE_CONSTANTS)},
        "parameterisation": "carbon-property-set/v1",
        "frequency_request": {"source_eigenvalue_count": 15, "requested_eigenvalue_count": 30},
        "registration": {"registration_hash": "a" * 64},
        "provenance": {"source_of_truth": ["synthetic test model"]},
    }
    data = copy.deepcopy(data)
    for path, value in overrides.items():
        target = data
        *parents, key = path.split("__")
        for part in parents:
            target = target[part]
        target[key] = value
    return data


def forward_manifest(passport=None, inp: bytes | None = None, **overrides):
    return parse_forward_model_manifest(forward_dict(passport, inp, **overrides))


def synthetic_model(text: str = SYNTHETIC_INP, **overrides):
    """(bound forward model, source bytes) for a synthetic INP."""
    from domain.forward_model_manifest import bind_forward_model

    raw = text.encode("latin-1")
    passport = synthetic_passport()
    return bind_forward_model(forward_manifest(passport, raw, **overrides), passport), raw
