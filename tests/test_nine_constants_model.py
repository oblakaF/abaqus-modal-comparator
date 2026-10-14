"""NINE-EC Phase C: orthotropic elasticity of the nine Engineering Constants and their INP reading / rewriting.

F5 (invalid elastic constants: nothing is rendered or evaluated) and F7 (several materials: explicit choice) live here.
No Abaqus.
"""

from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.forward_model_manifest import EngineeringConstants  # noqa: E402
from domain.orthotropic_elasticity import (  # noqa: E402
    COORDINATES,
    NAMES,
    CoordinateKind,
    ElasticAdmissibilityError,
    admissibility,
    compliance_matrix,
    from_coordinates,
    reciprocal_poisson,
    require_admissible,
    stiffness_matrix,
    to_coordinates,
)
from services.forward_builder import ForwardBuildError, locate_engineering_constants, split_inp_lines  # noqa: E402
from services.nine_constants_inp import (  # noqa: E402
    NineConstantsInputError,
    material_candidates,
    read_nine_constants_model,
    render_constants,
)

CFRP = EngineeringConstants(E1=120000, E2=9000, E3=8500, nu12=0.30, nu13=0.32, nu23=0.45, G12=5000, G13=4800, G23=3200)

TWO_MATERIALS = """*Heading
** two orthotropic materials, one solid and one shell section
*Part, name=PLATE
*Node
1, 0., 0., 0.
*Element, type=C3D8I, elset=FACE
1, 1, 1, 1, 1, 1, 1, 1, 1
*Element, type=S4R, elset=SKIN
2, 1, 1, 1, 1
*Orientation, name=Ori-1
1., 0., 0., 0., 1., 0.
3, 0.
*Solid Section, elset=FACE, orientation=Ori-1, material=Face_A
,
*Shell Section, elset=SKIN, material=Skin_B
0.5, 5
*End Part
*Material, name=Face_A
*Density
1.55e-09,
*Elastic, type=ENGINEERING CONSTANTS
 120000., 9000., 8500., 0.3, 0.32, 0.45, 5000., 4800.,
 3200.
*Material, name=Skin_B
*Elastic, type=ENGINEERING CONSTANTS
 52000., 52000., 6700., 0.05, 0.3, 0.3, 4500., 2200.,
 2200.
*Material, name=Thermal_C
*Elastic, type=ENGINEERING CONSTANTS
 1., 1., 1., 0., 0., 0., 1., 1.,
 1., 20.
 2., 2., 2., 0., 0., 0., 2., 2.,
 2., 80.
*Step
*Frequency
30, , , , ,
*End Step
"""


class ElasticityTests(unittest.TestCase):
    def test_compliance_reciprocity_and_stiffness(self):
        s = compliance_matrix(CFRP)
        self.assertTrue(np.allclose(s, s.T))  # symmetric: ν12/E1 = ν21/E2
        r = reciprocal_poisson(CFRP)
        self.assertAlmostEqual(r["nu21"], 0.30 * 9000 / 120000)
        self.assertAlmostEqual(-s[1, 0] * CFRP.E2, r["nu21"])
        self.assertAlmostEqual(r["nu31"], 0.32 * 8500 / 120000)
        self.assertAlmostEqual(r["nu32"], 0.45 * 8500 / 9000)
        c = stiffness_matrix(CFRP)
        self.assertTrue(np.allclose(c @ s, np.eye(6), atol=1e-9))
        self.assertTrue(np.all(np.linalg.eigvalsh(c) > 0))
        self.assertTrue(admissibility(CFRP).admissible)

    def test_poisson_ratios_are_signed_linear_coordinates(self):
        self.assertEqual({COORDINATES[n] for n in ("nu12", "nu13", "nu23")}, {CoordinateKind.LINEAR})
        auxetic = EngineeringConstants(**dict(CFRP.to_dict(), nu12=-0.2, nu13=0.0))
        self.assertTrue(admissibility(auxetic).admissible)  # zero and negative ν are admissible values
        x = to_coordinates(auxetic)
        self.assertEqual((x[3], x[4]), (-0.2, 0.0))  # never ln ν
        self.assertAlmostEqual(x[0], math.log(120000))
        back = from_coordinates(auxetic, NAMES, x)
        for name in NAMES:
            self.assertAlmostEqual(getattr(back, name), getattr(auxetic, name), places=9)

    def test_invalid_constants_are_refused_with_every_reason(self):  # F5
        cases = {
            "E3": dict(E3=0.0),
            "G13": dict(G13=-10.0),
            "nu12": dict(nu12=4.0),  # |ν12| ≥ sqrt(E1/E2) = 3.65
            "1 - ν12ν21": dict(nu23=0.99, nu13=0.9, nu12=0.6),  # determinant condition
        }
        for label, change in cases.items():
            with self.subTest(label):
                constants = EngineeringConstants(**dict(CFRP.to_dict(), **change))
                report = admissibility(constants)
                self.assertFalse(report.admissible)
                self.assertTrue(any(label in v for v in report.violations), report.violations)
                with self.assertRaises(ElasticAdmissibilityError):
                    require_admissible(constants)
        with self.assertRaises(ValueError):
            EngineeringConstants(**dict(CFRP.to_dict(), E1=float("nan")))  # non-finite input is refused at once


class InpTests(unittest.TestCase):
    def test_several_eligible_materials_need_an_explicit_choice(self):  # F7
        source = TWO_MATERIALS.encode()
        candidates = {c.name: c for c in material_candidates(source)}
        self.assertTrue(candidates["Face_A"].eligible and candidates["Skin_B"].eligible)
        self.assertFalse(candidates["Thermal_C"].eligible)  # temperature-dependent: refused, never guessed
        self.assertIn("no temperature dependence", candidates["Thermal_C"].reason)
        with self.assertRaises(NineConstantsInputError) as caught:
            read_nine_constants_model(source)
        self.assertIn("choose one explicitly", str(caught.exception))
        with self.assertRaises(NineConstantsInputError):
            read_nine_constants_model(source, "Thermal_C")

    def test_formulation_orientation_and_constants(self):
        source = TWO_MATERIALS.encode()
        face = read_nine_constants_model(source, "Face_A")
        self.assertEqual(face.constants, CFRP)
        self.assertEqual(face.model_kind, "3D_SOLID")
        self.assertEqual(face.sections[0].element_types, ("C3D8I",))
        self.assertEqual(face.orientations["ori-1"].definition, ("1., 0., 0., 0., 1., 0.", "3, 0."))
        self.assertEqual(set(face.formulation_use.values()), {"USED"})
        skin = read_nine_constants_model(source, "Skin_B")
        self.assertEqual(skin.model_kind, "SHELL_PLANE_STRESS")
        self.assertEqual({n for n, use in skin.formulation_use.items() if use != "USED"}, {"E3", "nu13", "nu23"})

    def test_rewrite_changes_only_the_record_and_refuses_inadmissible_sets(self):  # F5
        source = TWO_MATERIALS.encode()
        new = EngineeringConstants(**dict(CFRP.to_dict(), E3=9100.0, nu23=0.41, G13=4700.0))
        rendered = render_constants(source, "Face_A", new)
        self.assertEqual(read_nine_constants_model(rendered, "Face_A").constants, new)
        before, after = split_inp_lines(source), split_inp_lines(rendered)
        changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
        self.assertEqual(len(before), len(after))
        record = locate_engineering_constants(before, "Face_A")
        self.assertTrue(changed and set(changed) <= set(record.data_lines))  # only the data lines of that record
        self.assertEqual(read_nine_constants_model(rendered, "Skin_B").constants,
                         read_nine_constants_model(source, "Skin_B").constants)  # other material untouched
        with self.assertRaises(ElasticAdmissibilityError):
            render_constants(source, "Face_A", EngineeringConstants(**dict(CFRP.to_dict(), G12=0.0)))
        with self.assertRaises(ForwardBuildError):
            render_constants(source, "Thermal_C", CFRP)


if __name__ == "__main__":
    unittest.main()
