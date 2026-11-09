"""ABM-SOLID-3: read-only Abaqus solid INP import (synthetic box fixtures only)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault("OMP_NUM_THREADS", "1")
ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "src", ROOT / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import numpy as np  # noqa: E402

from services import solid_c3d8i_forward as sf  # noqa: E402
from services import solid_c3d8i_model as sm  # noqa: E402


# ---- synthetic Abaqus-style INP fixture (box meshes only); also used by test_solid_c3d8i_solver
ENGINEERING = (70000.0, 20000.0, 15000.0, 0.0, 0.0, 0.0, 9000.0, 7000.0, 6000.0)


def node_label(i, j, k, nx, ny):
    return 1 + i + (nx + 1) * (j + (ny + 1) * k)


def box_inp(nx=4, ny=2, nz=1, lx=40.0, ly=10.0, lz=5.0, *, constants=ENGINEERING, density=2.7e-9,
            orientation="1., 0., 0., 0., 1., 0.\n3, 0.", translation=None, rotation=None,
            element_type="C3D8I", model_extra="", part_extra="", step_extra="", material_extra="",
            part=True, modes=10):
    nodes = []
    for k in range(nz + 1):
        for j in range(ny + 1):
            for i in range(nx + 1):
                nodes.append(f"{node_label(i, j, k, nx, ny)}, {i * lx / nx!r}, {j * ly / ny!r}, {k * lz / nz!r}")
    elements = []
    label = 1
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                n = [node_label(i, j, k, nx, ny), node_label(i + 1, j, k, nx, ny),
                     node_label(i + 1, j + 1, k, nx, ny), node_label(i, j + 1, k, nx, ny),
                     node_label(i, j, k + 1, nx, ny), node_label(i + 1, j, k + 1, nx, ny),
                     node_label(i + 1, j + 1, k + 1, nx, ny), node_label(i, j + 1, k + 1, nx, ny)]
                elements.append(f"{label}, " + ", ".join(map(str, n)))
                label += 1
    n_nodes, n_el = len(nodes), len(elements)
    c = ", ".join(repr(v) for v in constants[:8]) + "\n" + repr(constants[8]) + ","
    section_orientation = ", orientation=Ori-1" if orientation else ""
    mesh = (f"*Node\n" + "\n".join(nodes) + f"\n*Element, type={element_type}\n" + "\n".join(elements)
            + f"\n*Nset, nset=Set-1, generate\n 1, {n_nodes}, 1\n*Elset, elset=Set-1, generate\n 1, {n_el}, 1\n"
            + (f"*Orientation, name=Ori-1\n{orientation}\n" if orientation else "")
            + f"** Section: S\n*Solid Section, elset=Set-1{section_orientation}, material=MAT\n,\n" + part_extra)
    inst_lines = ""
    if translation is not None or rotation is not None:
        inst_lines = ", ".join(repr(v) for v in (translation or (0.0, 0.0, 0.0))) + "\n"
        if rotation is not None:
            inst_lines += ", ".join(repr(v) for v in rotation) + "\n"
    if part:
        body = (f"*Part, name=Part-1\n{mesh}*End Part\n**\n*Assembly, name=Assembly\n"
                f"*Instance, name=Part-1-1, part=Part-1\n{inst_lines}*End Instance\n*End Assembly\n")
    else:
        body = mesh
    return (f"*Heading\n** Job name: FIXTURE Model name: SYNTHETIC\n*Preprint, echo=NO, model=NO, history=NO\n"
            f"{body}{model_extra}*Material, name=MAT\n*Density\n {density!r},\n"
            f"*Elastic, type=ENGINEERING CONSTANTS\n{c}\n{material_extra}"
            f"*Step, name=Modal, nlgeom=NO, perturbation\n"
            f"*Frequency, eigensolver=Lanczos, sim, acoustic coupling=on, normalization=mass\n{modes}, , , , ,\n"
            f"{step_extra}*Restart, write, frequency=0\n*Output, field\n*Node Output\nU,\n"
            f"*Output, history\n*Energy Output\nALLKE, ALLSE\n*End Step\n")


class InpCase(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)

    def write(self, text, name="model.inp"):
        path = Path(self._dir.name) / name
        path.write_text(text, encoding="latin-1")
        return path

    def load(self, **kwargs):
        return sm.load_solid_inp(self.write(box_inp(**kwargs)))


class ImportTests(InpCase):
    def test_part_instance_model_is_read_with_labels_and_c3d8_order(self):
        path = self.write(box_inp(nx=4, ny=2, nz=1, translation=(251.0, 270.0, 0.0)))
        before = path.read_bytes()
        m = sm.load_solid_inp(path)
        self.assertEqual(path.read_bytes(), before)  # read-only
        self.assertEqual(m.source_sha256, hashlib.sha256(before).hexdigest())
        self.assertEqual((m.part_name, m.instance_name, m.odb_instance_name), ("Part-1", "Part-1-1", "PART-1-1"))
        self.assertEqual(len(m.node_labels), 5 * 3 * 2)
        self.assertEqual(len(m.element_labels), 8)
        self.assertEqual(m.material_name, "MAT")
        self.assertEqual(m.density, 2.7e-9)
        self.assertEqual(m.material, sf.OrthotropicEngineeringConstants.from_abaqus(
            (70000.0, 20000.0, 15000.0, 0.0, 0.0, 0.0, 9000.0, 7000.0, 6000.0)))
        self.assertEqual(m.requested_eigenvalues, 10)
        np.testing.assert_allclose(m.material_axes, np.eye(3))
        first = m.node_labels[m.connectivity[0]]
        self.assertEqual(first.tolist(), [1, 2, 7, 6, 16, 17, 22, 21])
        # instance translation applied: node 1 at part origin -> (251, 270, 0)
        np.testing.assert_allclose(m.coordinates[0], (251.0, 270.0, 0.0))
        np.testing.assert_allclose(m.coordinates[-1], (291.0, 280.0, 5.0))

    def test_dof_identity_is_node_major_with_odb_instance_names(self):
        m = self.load(nx=1, ny=1, nz=1)
        ids = m.dof_identity()
        self.assertEqual(m.dof_count, 24)
        self.assertEqual(ids[:4], [("PART-1-1", 1, 1), ("PART-1-1", 1, 2), ("PART-1-1", 1, 3), ("PART-1-1", 2, 1)])

    def test_flat_input_without_parts(self):
        m = self.load(part=False)
        self.assertIsNone(m.instance_name)
        self.assertEqual(len(m.element_labels), 8)

    def test_orientation_points_origin_and_additional_rotation(self):
        quarter = np.array([[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
        for text in ("0., 1., 0., -1., 0., 0.\n3, 0.", "1., 0., 0., 0., 1., 0.\n3, 90.",
                     "5., 6., 2., 4., 5., 2., 5., 5., 2.\n3, 0."):
            with self.subTest(text=text):
                np.testing.assert_allclose(self.load(orientation=text).material_axes, quarter, atol=1e-12)
        self.assertIsNone(self.load(orientation=None).orientation_name)
        np.testing.assert_allclose(self.load(orientation=None).material_axes, np.eye(3))

    def test_instance_rotation_moves_nodes_and_material_axes(self):
        m0 = self.load()
        m1 = self.load(translation=(10.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 90.0))
        r = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
        np.testing.assert_allclose(m1.coordinates, (m0.coordinates + (10.0, 0.0, 0.0)) @ r.T, atol=1e-12)
        np.testing.assert_allclose(m1.material_axes, r.T, atol=1e-12)  # axis 1 now along global y

    def test_in_plane_variation_holds_other_constants(self):
        m = self.load()
        varied = m.with_in_plane_constants(e1=80000.0, g12=4000.0)
        self.assertEqual((varied.e1, varied.e2, varied.g12), (80000.0, 20000.0, 4000.0))
        self.assertEqual((varied.e3, varied.nu12, varied.nu13, varied.nu23, varied.g13, varied.g23),
                         (m.material.e3, 0.0, 0.0, 0.0, 7000.0, 6000.0))
        with self.assertRaises(sf.InadmissibleMaterialError):
            m.with_in_plane_constants(g12=0.0)
        poisson = self.load(constants=(1000.0, 1000.0, 1000.0, 0.45, 0.45, 0.45, 300.0, 300.0, 300.0))
        with self.assertRaises(sf.InadmissibleMaterialError):
            poisson.with_in_plane_constants(e2=200.0)  # nu23 = 0.45 > sqrt(E2/E3): not positive definite
        self.assertEqual(poisson.with_in_plane_constants(e1=1200.0).e1, 1200.0)


class RefusalTests(InpCase):
    def refuse(self, pattern, **kwargs):
        with self.assertRaisesRegex(sf.SolidElementError, pattern):
            self.load(**kwargs)

    def test_boundary_conditions_are_refused(self):
        self.refuse("boundary", model_extra="*Boundary\nPart-1-1.Set-1, 1, 3\n")
        self.refuse("boundary", step_extra="*Boundary\nPart-1-1.Set-1, ENCASTRE\n")

    def test_unsupported_keywords_are_named(self):
        cases = {
            "Include": dict(model_extra="*Include, input=other.inp\n"),
            "inside a step": dict(step_extra="*Cload\n1, 3, 1.\n"),
            "not supported": dict(model_extra="*Tie, name=T\nA, B\n"),
            "material behaviour": dict(material_extra="*Damping, alpha=0.1\n"),
        }
        for pattern, kwargs in cases.items():
            with self.subTest(pattern=pattern):
                self.refuse(pattern, **kwargs)
        text = box_inp().replace("*End Assembly", "*Surface, name=S\nPart-1-1.Set-1\n*End Assembly")
        with self.assertRaisesRegex(sf.SolidElementError, "assembly"):
            sm.load_solid_inp(self.write(text))

    def test_other_element_types_are_not_substituted(self):
        for etype in ("C3D8", "C3D8R", "C3D20R"):
            with self.subTest(etype=etype):
                self.refuse("not substituted", element_type=etype)

    def test_material_and_section_restrictions(self):
        text = box_inp().replace("type=ENGINEERING CONSTANTS", "type=ISOTROPIC")
        with self.assertRaisesRegex(sf.SolidElementError, "ENGINEERING CONSTANTS"):
            sm.load_solid_inp(self.write(text))
        text = box_inp().replace(" 2.7e-09,", " 2.7e-09, 20.\n 2.8e-09, 80.")
        with self.assertRaisesRegex(sf.SolidElementError, "density"):
            sm.load_solid_inp(self.write(text))
        self.refuse("Exactly one material", model_extra="*Material, name=OTHER\n*Density\n1e-9,\n")

    def test_section_coverage_and_mesh_consistency(self):
        text = box_inp().replace("*Elset, elset=Set-1, generate\n 1, 8, 1", "*Elset, elset=Set-1, generate\n 1, 7, 1")
        with self.assertRaisesRegex(sf.SolidElementError, "every element"):
            sm.load_solid_inp(self.write(text))
        text = box_inp().replace("\n1, 1, 2, 7, 6,", "\n1, 1, 2, 7, 999,")
        with self.assertRaisesRegex(sf.SolidElementError, "undefined node"):
            sm.load_solid_inp(self.write(text))
        text = box_inp().replace("*Element, type=C3D8I", "99, 0., 0., 9.\n*Element, type=C3D8I")
        with self.assertRaisesRegex(sf.SolidElementError, "not connected"):
            sm.load_solid_inp(self.write(text))
        text = box_inp().replace("*Solid Section, elset=Set-1, orientation=Ori-1, material=MAT\n,",
                                 "*Solid Section, elset=Set-1, orientation=Ori-1, material=MAT\n2.0,")
        with self.assertRaisesRegex(sf.SolidElementError, "section data"):
            sm.load_solid_inp(self.write(text))
        text = box_inp().replace("*Orientation, name=Ori-1", "*Orientation, name=Ori-1, system=CYLINDRICAL")
        with self.assertRaisesRegex(sf.SolidElementError, "RECTANGULAR"):
            sm.load_solid_inp(self.write(text))

    def test_structure_restrictions(self):
        text = box_inp().replace("*End Assembly", "*Instance, name=Part-1-2, part=Part-1\n*End Instance\n*End Assembly")
        with self.assertRaisesRegex(sf.SolidElementError, "one part and one instance"):
            sm.load_solid_inp(self.write(text))
        text = box_inp().replace("*Frequency, eigensolver=Lanczos, sim, acoustic coupling=on, normalization=mass\n10, , , , ,\n",
                                 "*Static\n")
        with self.assertRaisesRegex(sf.SolidElementError, "inside a step"):
            sm.load_solid_inp(self.write(text))
        text = box_inp().split("*Step")[0]
        with self.assertRaisesRegex(sf.SolidElementError, "Frequency"):
            sm.load_solid_inp(self.write(text))
        text = box_inp().replace("*End Step\n", "*End Step\n*Step, name=Two\n*Frequency\n5,\n*End Step\n")
        with self.assertRaisesRegex(sf.SolidElementError, "more than one step"):
            sm.load_solid_inp(self.write(text))


if __name__ == "__main__":
    unittest.main()
