"""ABM-AUD-5: research estimation of plate bending stiffness from a registered modal set, by the Kirchhoff-Ritz model.

Synthetic data only. The "measured" frequencies and shapes come from an INDEPENDENT free-plate solution written in this
file (a Chebyshev basis with its own quadrature and assembly, checked against Leissa's published values for the free
square isotropic plate), never from the program's Ritz service. The scan is turned 45 degrees, written in metres with
another origin, and covers an interior part of the plate.

Tolerances. The independent solution and the program's Ritz model are two discretizations of the same plate; over the
modes used here their frequencies differ by less than 1e-5 (asserted). A relative frequency error e moves a fitted
modulus by about 2 e times the condition number of the sensitivity matrix (about 2 for these fits), so recovered moduli
and stiffnesses are required within 2e-4, and frequency residuals within 2e-5.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np
from numpy.polynomial import chebyshev
from scipy import linalg

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from modal_core import ModeShape  # noqa: E402
from services import registered_ritz_estimation as rre  # noqa: E402
from services import research_frequency_stability as rfs  # noqa: E402
from services import research_frequency_tuning as rft  # noqa: E402

FREQUENCY_AGREEMENT = 1.0e-5  # the two discretizations, relative, on the modes used
RECOVERY = 2.0e-4  # recovered moduli and stiffnesses, relative (see the module text)
THICKNESS, MASS, NU12 = 0.875, 120.0, 0.05  # mm, g


# ------------------------------------------------------------------------------------------- the independent plate


class IndependentPlate:
    """Free rectangular orthotropic Kirchhoff plate by Rayleigh-Ritz in Chebyshev polynomials T_p(2x/a) T_q(2y/b).

    Strain energy  U = 1/2 int [D11 w,xx^2 + D22 w,yy^2 + 2 D12 w,xx w,yy + 4 D66 w,xy^2] dA, kinetic energy
    T = 1/2 mu omega^2 int w^2 dA, both by a 40-point Gauss-Legendre rule per axis. The three rigid motions are the
    zero eigenvalues and are dropped. Nothing of the program is used."""

    def __init__(self, a_m, b_m, surface_mass, D11, D22, D12, D66, degree=13, count=14):
        self.a, self.b, self.degree = a_m, b_m, degree
        nodes, weights = np.polynomial.legendre.leggauss(40)
        t0, t1, t2 = (self._table(nodes, order) for order in (0, 1, 2))
        sx, sy = 2.0 / a_m, 2.0 / b_m

        def product(left, right):
            return np.einsum("ip,jq->ijpq", left, right).reshape(len(nodes) ** 2, (degree + 1) ** 2)

        weight = np.outer(weights, weights).ravel() * a_m * b_m / 4.0
        w, wxx, wyy, wxy = product(t0, t0), product(t2, t0) * sx * sx, product(t0, t2) * sy * sy, product(t1, t1) * sx * sy
        stiffness = (D11 * (wxx.T * weight) @ wxx + D22 * (wyy.T * weight) @ wyy
                     + D12 * ((wxx.T * weight) @ wyy + (wyy.T * weight) @ wxx) + 4.0 * D66 * (wxy.T * weight) @ wxy)
        mass = surface_mass * (w.T * weight) @ w
        values, vectors = linalg.eigh(stiffness, mass)
        elastic = values > 1.0e-6 * values[10]
        self.hz = np.sqrt(values[elastic][:count]) / (2.0 * math.pi)
        self.vectors = vectors[:, elastic][:, :count]

    def _table(self, points, order):
        out = np.zeros((len(points), self.degree + 1))
        for p in range(order, self.degree + 1):
            coefficients = np.zeros(p + 1)
            coefficients[p] = 1.0
            out[:, p] = chebyshev.chebval(points, chebyshev.chebder(coefficients, order) if order else coefficients)
        return out

    def field(self, x_m, y_m, dx=0, dy=0):
        """Rows: points; columns: modes. The shape or its derivative d^dx/dx^dx d^dy/dy^dy."""
        tx = self._table(2.0 * np.asarray(x_m) / self.a, dx) * (2.0 / self.a) ** dx
        ty = self._table(2.0 * np.asarray(y_m) / self.b, dy) * (2.0 / self.b) ** dy
        return np.einsum("ip,iq->ipq", tx, ty).reshape(len(tx), -1) @ self.vectors


def stiffness(E1, E2, G12, nu12=NU12, thickness_mm=THICKNESS):
    """D11, D22, D12, D66 in N m from the plane-stress relations, written out here (MPa and mm in)."""
    h3 = (thickness_mm * 1.0e-3) ** 3 / 12.0
    q = 1.0 - nu12 * nu12 * E2 / E1
    return E1 * 1.0e6 / q * h3, E2 * 1.0e6 / q * h3, nu12 * E2 * 1.0e6 / q * h3, G12 * 1.0e6 * h3


def truth_plate(length_mm, width_mm, E1, E2, G12, mass_g=MASS, count=14):
    surface = mass_g * 1.0e-3 / (length_mm * width_mm * 1.0e-6)
    return IndependentPlate(length_mm * 1.0e-3, width_mm * 1.0e-3, surface, *stiffness(E1, E2, G12), count=count)


# ------------------------------------------------------------------------------------------- a registered scan


TURN = math.radians(45.0)
ROTATION = np.array([[math.cos(TURN), -math.sin(TURN), 0.0], [math.sin(TURN), math.cos(TURN), 0.0], [0.0, 0.0, 1.0]])
TRANSLATION = np.array([-0.0498, 0.1630, 0.012])  # the scan's own origin, metres
SCALE = np.full(3, 1.0e-3)  # experimental metres per FE millimetre
TRANSFORM = {"rotation": ROTATION.tolist(), "translation": TRANSLATION.tolist(), "coordinate_scales": SCALE.tolist()}
SOURCE = {"experimental_file": "synthetic scan.unv", "experimental_sha256": "ab" * 32, "experimental_size": 1234,
          "modal_set_key": "fitted", "modal_set_title": "Fitted", "fe_manifest_sha256": "cd" * 32,
          "fe_package_sha256": "ef" * 32, "fe_geometry_sha256": "01" * 32}
REGISTRATION = {"kind": "USER_CONFIRMED_REGISTRATION", "status": "USER_CONFIRMED_COMPARISON", "registration_hash": "9f" * 32,
                "confirmed_by": "A. Tester", "confirmed_at": "2026-11-11T00:00:00+00:00",
                "evidence_location": "notebook 7, page 12", "fe_unit": "mm", "experimental_unit": "m", "measured_side": "+Z"}


def scan_places(length_mm, width_mm, across=9, margin=0.08):
    """An interior grid of FE positions (mm): the FE model's corner is its origin, the plate lies in FE X-Y."""
    xs = np.linspace(margin * length_mm, (1.0 - margin) * length_mm, across)
    ys = np.linspace(margin * width_mm, (1.0 - margin) * width_mm, across)
    return np.array([(x, y, 0.0) for y in ys for x in xs])


def to_scan(points_fe):
    """FE positions as the scan file states them: x_exp = (x_fe R) s + t (the comparator's convention)."""
    return (np.asarray(points_fe) @ ROTATION) * SCALE + TRANSLATION


def measured_set(length_mm, width_mm, truth, records=10, component=2, places=None, source=SOURCE, registration=REGISTRATION,
                 frequencies=None, shape_order=None, measured=True):
    """The registered set of a scan of ``truth``: record k is truth mode k (or ``shape_order[k]``) at its own frequency,
    measured along experimental component ``component`` at interior points."""
    places = scan_places(length_mm, width_mm) if places is None else places
    centred = (places - np.array([length_mm / 2.0, width_mm / 2.0, 0.0])) * 1.0e-3
    shapes = truth.field(centred[:, 0], centred[:, 1])
    coordinates = to_scan(places)
    modes = []
    for k in range(records):
        vectors = np.zeros((len(places), 3), dtype=complex)
        vectors[:, component] = shapes[:, k if shape_order is None else shape_order[k]]
        mode = ModeShape(k + 1, float(truth.hz[k] if frequencies is None else frequencies[k]), np.arange(1, len(places) + 1),
                         coordinates, vectors)
        if measured:
            mask = np.zeros((len(places), 3), dtype=bool)
            mask[:, component] = True
            mode.measured_dofs = mask
        modes.append(mode)
    return rre.registered_set(modes=modes, transform=TRANSFORM, fe_low=(0.0, 0.0, 0.0), fe_high=(length_mm, width_mm, 0.0),
                              source=source, registration=registration, pairs=[(k + 1, 7 + k, 0.99) for k in range(records)])


def plate(length_mm, width_mm, reference, **changes):
    values = dict(length_mm=length_mm, width_mm=width_mm, thickness_mm=THICKNESS, mass_g=MASS, nu12=NU12,
                  categories=(rre.MEASURED, rre.MEASURED, rre.MEASURED, rre.MEASURED, rre.DECLARED),
                  inputs_source="measurement sheet 12", length_axis="X", width_axis="Y", linked=True,
                  reference=tuple(float(v) for v in reference))
    values.update(changes)
    return rre.Plate(**values)


def request(rset, parameterization=rft.FREE, holdout=(9, 10), excluded=(), declared=None, **settings):
    observations = rft.observations_by_rank(rset.records, holdout=holdout, excluded=excluded, declared=declared)
    return rft.TuningRequest(observations, parameterization, rft.DECLARED if declared else rft.RANK_ORDER, **settings)


def estimate(rset, declared_plate, parameterization=rft.FREE, reviewed=True, **kw):
    fit = request(rset, parameterization, **kw)
    review = rre.shape_review(rset, declared_plate) if reviewed else None
    return rre.run_estimation(rset, declared_plate, fit, review) + (review,)


class _Rectangle(unittest.TestCase):
    """An orthotropic 320 x 240 mm plate; material axis 1 along the length."""

    LENGTH, WIDTH = 320.0, 240.0
    TRUTH = (62000.0, 44000.0, 4600.0)
    REFERENCE = (54000.0, 49000.0, 5200.0)

    @classmethod
    def setUpClass(cls):
        cls.truth = truth_plate(cls.LENGTH, cls.WIDTH, *cls.TRUTH)
        cls.rset = measured_set(cls.LENGTH, cls.WIDTH, cls.truth)
        cls.plate = plate(cls.LENGTH, cls.WIDTH, cls.REFERENCE, material_axis=rre.AXIS_LENGTH,
                          material_axis_evidence="layup record L-3: 0 degree plies along the length")
        cls.result, cls.block, cls.review = estimate(cls.rset, cls.plate)

    def assert_close(self, value, expected, tolerance=RECOVERY, msg=None):
        self.assertAlmostEqual(value / expected, 1.0, delta=tolerance, msg=msg)


# ------------------------------------------------------------------------------------------- the reference itself


class IndependentReferenceTests(unittest.TestCase):
    def test_it_reproduces_the_published_free_square_isotropic_plate(self):
        """Leissa, Vibration of Plates (NASA SP-160), completely free square plate, nu = 0.3: omega a^2 sqrt(rho h / D) =
        13.468, 19.596, 24.270 for the first three modes."""
        nu = 0.3
        solution = IndependentPlate(1.0, 1.0, 1.0, 1.0, 1.0, nu, (1.0 - nu) / 2.0)
        for value, published in zip(2.0 * math.pi * solution.hz[:3], (13.468, 19.596, 24.270)):
            self.assertAlmostEqual(value, published, delta=0.002)

    def test_the_two_discretizations_agree_on_the_modes_used(self):
        for length, width, constants in ((320.0, 240.0, (62000.0, 44000.0, 4600.0)), (301.0, 301.0, (52000.0, 52000.0, 4500.0))):
            truth = truth_plate(length, width, *constants)
            inputs = rre.plate_inputs(plate(length, width, constants))
            program = rft.Surrogate(inputs, 14, 12).frequencies(*constants)
            self.assertLess(float(np.max(np.abs(program[:10] / truth.hz[:10] - 1.0))), FREQUENCY_AGREEMENT)


# ------------------------------------------------------------------------------------------- registered data


class RegisteredDataTests(_Rectangle):
    def test_the_turned_metre_scan_is_placed_on_the_plate(self):
        """45 degrees, metres, another origin: every measured DOF comes back to its FE position and is normal."""
        places = scan_places(self.LENGTH, self.WIDTH)
        self.assertLess(float(np.max(np.abs(self.rset.points_fe - places))), 1.0e-9)
        self.assertTrue(np.allclose(self.rset.directions_fe, (0.0, 0.0, 1.0)))
        frame = rre.plate_frame(self.rset, self.plate)
        self.assertLess(float(np.max(np.abs(frame.x_m - (places[:, 0] - self.LENGTH / 2.0) * 1.0e-3))), 1.0e-12)
        self.assertLess(float(np.max(np.abs(frame.y_m - (places[:, 1] - self.WIDTH / 2.0) * 1.0e-3))), 1.0e-12)
        self.assertLess(abs(float(np.max(frame.x_m)) - 0.42 * self.LENGTH * 1.0e-3), 1.0e-9)  # an interior grid
        shown = dict(frame.lines)
        self.assertIn("DECLARED BY THE USER", shown["Link to the registered frame"])
        self.assertIn("320 x 240 x 0 mm", shown["FE extent along x, y, normal"])
        self.assertIn("+0.00 %, +0.00 %", shown["Entered x, y, thickness"])
        self.assertIn("81 normal to the plate", shown["Measured directions"])

    def test_the_source_and_registration_identity_stay_with_the_set(self):
        self.assertEqual(self.rset.records, tuple((k + 1, float(self.truth.hz[k])) for k in range(10)))
        self.assertEqual(self.rset.source["experimental_sha256"], "ab" * 32)
        self.assertEqual(self.rset.pairs[0], (1, 7, 0.99))
        block = self.block
        self.assertEqual(block["source"], SOURCE)
        self.assertEqual(block["registration"]["registration_hash"], "9f" * 32)
        self.assertEqual(block["set_identity"], self.rset.identity)
        self.assertEqual(block["fe_pairs"][2], [3, 9, 0.99])
        other = measured_set(self.LENGTH, self.WIDTH, self.truth, source=dict(SOURCE, experimental_sha256="77" * 32))
        self.assertNotEqual(other.identity, self.rset.identity)

    def test_ritz_shapes_on_the_measured_dofs_match_the_independent_shapes(self):
        """At the truth constants the program's Ritz shapes, placed through the registration, are the independent
        shapes: MAC 1 on the diagonal for every non-close mode."""
        review = rre.shape_review(self.rset, plate(self.LENGTH, self.WIDTH, self.TRUTH))
        for k in range(10):
            self.assertGreater(review["mac"][k][k], 1.0 - 1.0e-6, k)
            self.assertLess(max(v for j, v in enumerate(review["mac"][k]) if j != k), 0.2)  # an interior 9 x 9 grid
        for k, hz in enumerate(review["ritz_hz"][:10]):
            self.assert_close(hz, self.truth.hz[k], FREQUENCY_AGREEMENT)

    def test_an_in_plane_measured_dof_is_projected_by_the_surface_kinematics(self):
        """The scan's own x and y axes lie in the plate plane, turned 45 degrees. On the +Z face a point of a
        Kirchhoff plate moves by (-z w,x ; -z w,y ; w). The data are that motion from the independent derivatives, seen
        in the scan's axes, with only x and y measured. The program must find MAC 1 with the same modes, and it must
        not read those DOFs as the transverse deflection."""
        places = scan_places(self.LENGTH, self.WIDTH)
        centred = (places - np.array([self.LENGTH / 2.0, self.WIDTH / 2.0, 0.0])) * 1.0e-3
        z = 0.5e-3 * THICKNESS
        slope_x = self.truth.field(centred[:, 0], centred[:, 1], dx=1)
        slope_y = self.truth.field(centred[:, 0], centred[:, 1], dy=1)
        transverse = self.truth.field(centred[:, 0], centred[:, 1])
        modes = []
        for k in range(8):
            motion_fe = np.column_stack((-z * slope_x[:, k], -z * slope_y[:, k], transverse[:, k]))
            mode = ModeShape(k + 1, float(self.truth.hz[k]), np.arange(1, len(places) + 1), to_scan(places),
                             (motion_fe @ ROTATION).astype(complex))
            mode.measured_dofs = np.broadcast_to(np.array([True, True, False]), (len(places), 3)).copy()
            modes.append(mode)
        rset = rre.registered_set(modes=modes, transform=TRANSFORM, fe_low=(0, 0, 0), fe_high=(self.LENGTH, self.WIDTH, 0),
                                  source=SOURCE, registration=REGISTRATION)
        self.assertEqual(len(rset.labels), 2 * len(places))
        self.assertTrue(np.allclose(rset.directions_fe[0], (math.cos(TURN), math.sin(TURN), 0.0)))  # the scan's x in FE
        review = rre.shape_review(rset, plate(self.LENGTH, self.WIDTH, self.TRUTH))
        shown = dict(map(tuple, review["frame"]))
        self.assertIn("162 with an in-plane part", shown["Measured directions"])
        self.assertIn("0.4375 mm from the mid-plane", shown["Measured side"])
        for k in range(8):
            self.assertGreater(review["mac"][k][k], 1.0 - 1.0e-6, k)
        # read as transverse deflection, the same data would not be these modes
        as_transverse = np.concatenate((transverse[:, 0], transverse[:, 0]))
        measured = rset.values[0].real
        self.assertLess(float((as_transverse @ measured) ** 2 / ((as_transverse @ as_transverse) * (measured @ measured))), 0.5)

    def test_an_unsupported_measurement_is_refused_not_read_as_transverse(self):
        unknown_side = dict(REGISTRATION, measured_side="")
        rset = measured_set(self.LENGTH, self.WIDTH, self.truth, component=0, registration=unknown_side)
        with self.assertRaises(rre.EstimationRefused) as refused:
            rre.shape_review(rset, self.plate)
        self.assertEqual(refused.exception.code, rre.UNSUPPORTED_MEASUREMENT)
        self.assertIn("No measurement is treated as transverse motion", str(refused.exception))
        with self.assertRaises(rre.EstimationRefused) as refused:
            measured_set(self.LENGTH, self.WIDTH, self.truth, measured=False)
        self.assertEqual(refused.exception.code, rre.UNSUPPORTED_MEASUREMENT)
        self.assertIn("no explicit measured-DOF mask", str(refused.exception))

    def test_without_a_registration_there_is_no_registered_set(self):
        with self.assertRaises(rre.EstimationRefused) as refused:
            measured_set(self.LENGTH, self.WIDTH, self.truth, registration=dict(REGISTRATION, registration_hash=""))
        self.assertEqual(refused.exception.code, rre.REGISTRATION_REQUIRED)


# ------------------------------------------------------------------------------------------- the plate and its link


class PlateLinkTests(_Rectangle):
    def test_an_unstated_link_refuses_every_shape_comparison(self):
        with self.assertRaises(rre.EstimationRefused) as refused:
            rre.shape_review(self.rset, replace_plate(self.plate, linked=False))
        self.assertEqual(refused.exception.code, rre.LINK_NOT_ESTABLISHED)
        self.assertIn("no Ritz shape is compared with a measured shape", str(refused.exception))

    def test_a_plate_that_cannot_hold_the_registered_points_is_refused(self):
        with self.assertRaises(rre.EstimationRefused) as refused:
            rre.shape_review(self.rset, replace_plate(self.plate, length_mm=250.0))
        self.assertEqual(refused.exception.code, rre.LINK_NOT_ESTABLISHED)
        self.assertIn("lie outside the entered 250 x 240 mm rectangle", str(refused.exception))
        with self.assertRaises(rre.EstimationRefused):  # the axes exchanged: the 320 mm scan does not fit 240 mm
            rre.shape_review(self.rset, replace_plate(self.plate, length_axis="Y", width_axis="X"))

    def test_a_registration_without_a_length_unit_gives_no_link(self):
        rset = measured_set(self.LENGTH, self.WIDTH, self.truth, registration=dict(REGISTRATION, fe_unit=""))
        with self.assertRaises(rre.EstimationRefused) as refused:
            rre.shape_review(rset, self.plate)
        self.assertEqual(refused.exception.code, rre.LINK_NOT_ESTABLISHED)

    def test_a_different_entered_size_is_shown_not_replaced(self):
        """The measured plan is used as entered even when the FE model differs: the difference is displayed."""
        review = rre.shape_review(self.rset, replace_plate(self.plate, length_mm=323.2))
        self.assertIn("+1.00 %, +0.00 %", dict(map(tuple, review["frame"]))["Entered x, y, thickness"])

    def test_invalid_inputs_are_refused_with_every_reason(self):
        cases = ((dict(length_mm=0.0), "Length must be a positive number"), (dict(width_mm=-3.0), "Width must be"),
                 (dict(thickness_mm=float("nan")), "Thickness must be"), (dict(mass_g=0.0), "Mass must be"),
                 (dict(nu12=float("inf")), "nu12 must be a number"), (dict(inputs_source="  "), "State where the dimensions"),
                 (dict(categories=(rre.MEASURED,) * 4), "State for each of"),
                 (dict(categories=(rre.MEASURED,) * 3 + (rre.IMPORTED_FE, rre.DECLARED)), "mass cannot be imported"),
                 (dict(reference=(50000.0, -1.0, 5000.0)), "reference constants"),
                 (dict(material_axis=rre.AXIS_WIDTH, material_axis_evidence=""), "needs its evidence"))
        for changes, words in cases:
            with self.assertRaises(rre.EstimationRefused, msg=changes) as refused:
                rre.plate_inputs(replace_plate(self.plate, **changes))
            self.assertEqual(refused.exception.code, rre.INVALID_INPUT)
            self.assertIn(words, str(refused.exception))

    def test_a_stiffness_that_is_not_positive_definite_is_refused(self):
        with self.assertRaises(rre.EstimationRefused) as refused:
            rre.plate_inputs(replace_plate(self.plate, nu12=1.2, reference=(50000.0, 50000.0, 5000.0)))
        self.assertIn("not positive definite", str(refused.exception))

    def test_nothing_is_taken_from_a_file_and_the_density_is_computed(self):
        inputs = rre.plate_inputs(self.plate)
        self.assertEqual((inputs.inp_path, inputs.inp_sha256), ("", ""))
        self.assert_close(inputs.mass_g, MASS, 1.0e-12)
        self.assertEqual((inputs.a_mm, inputs.b_mm, inputs.thickness_mm, inputs.nu12), (320.0, 240.0, THICKNESS, NU12))
        turned = rre.plate_inputs(replace_plate(self.plate, material_axis=rre.AXIS_WIDTH))
        self.assertEqual((turned.a_mm, turned.b_mm), (240.0, 320.0))  # the fit frame's x is material axis 1


def replace_plate(declared, **changes):
    from dataclasses import replace

    return replace(declared, **changes)


def reviewed_ranks(review) -> dict:
    """{record: Ritz rank} for the records whose most alike Ritz mode is not the mode of their own frequency rank: what a
    person reads off the review table and then declares. The test does the reading; the program assigns nothing."""
    mac = np.array(review["mac"])
    best = {record: int(np.argmax(mac[row])) + 1 for row, (record, _hz) in enumerate(review["records"])}
    return {record: rank for record, rank in best.items() if rank != record}


# ------------------------------------------------------------------------------------------- known answers


class OrthotropicRecoveryTests(_Rectangle):
    def test_the_known_constants_and_stiffnesses_are_recovered(self):
        result, block = self.result, self.block
        self.assertEqual(result.status, rft.SUPPORTED, result.reasons)
        self.assertEqual(len(result.minima), 1)
        for name, expected in zip(("E1", "E2", "G12"), self.TRUTH):
            self.assert_close(result.fitted[name], expected, msg=name)
        d11, d22, d12, d66 = stiffness(*self.TRUTH)
        values = block["stiffness"]["values"]
        for name, expected in (("D11", d11), ("D22", d22), ("D66", d66), ("D12", d12)):
            self.assert_close(values[name], expected, msg=name)
        self.assertEqual(block["stiffness"]["unit"], "N m")
        self.assertEqual(block["stiffness"]["frame"], {"x": "length a", "y": "width b"})
        self.assertIn("held fixed", block["stiffness"]["D12_note"])

    def test_conditional_constants_are_named_only_with_the_axis_evidence(self):
        constants = self.block["constants"]
        self.assertEqual(self.block["presentation"], {"verdict": rre.SUPPORTED_ESTIMATE, "reasons": []})
        self.assertEqual(constants["kind"], "CONDITIONAL_ENGINEERING_CONSTANTS")
        self.assertEqual([name.split(" ")[0] for name, _value in constants["rows"]], ["E1", "E2", "G12"])
        self.assertIn("layup record L-3", constants["axis_evidence"])
        self.assertIn("thickness 0.875 mm", constants["conditions"])
        # the same data and correspondence, without the evidence: the numbers stay, the axis names do not
        result, block, _review = estimate(self.rset, plate(self.LENGTH, self.WIDTH, self.REFERENCE))
        self.assertEqual(block["presentation"]["verdict"], rre.SUPPORTED_ESTIMATE)
        self.assertEqual(block["constants"]["kind"], "AXIS_FREE_VALUES")
        names = [name for name, _value in block["constants"]["rows"]]
        self.assertFalse([name for name in names if name.startswith(("E1", "E2"))])
        self.assertEqual(names[:2], ["E_stiff (no material axis named)", "E_soft (no material axis named)"])
        self.assertIn("not independent evidence of the material axes", block["constants"]["rows"][3][1])
        self.assertIn("material axis 1 is not stated", " ".join(block["constants"]["reasons"]))
        self.assert_close(result.fitted["E1"], self.TRUTH[0])

    def test_the_fit_residuals_and_the_holdout_prediction(self):
        result = self.result
        self.assertEqual(result.fit_quality["verdict"], rft.FIT_WITHIN)
        self.assertEqual(result.fit_quality["holdout_verdict"], rft.HOLDOUT_WITHIN)
        self.assertLess(result.rms_fit_after, 2.0 * FREQUENCY_AGREEMENT)
        self.assertLess(result.rms_holdout_after, 2.0 * FREQUENCY_AGREEMENT)
        rows = {row["record"]: row for row in result.rows}
        self.assertEqual([rows[k]["role"] for k in (8, 9, 10)], [rft.FIT, rft.HOLDOUT, rft.HOLDOUT])
        for record in (9, 10):  # predicted from the eight fitted records, against the independent frequencies
            self.assert_close(rows[record]["ritz_after_hz"], self.truth.hz[record - 1], 2.0 * FREQUENCY_AGREEMENT)

    def test_a_holdout_record_has_no_influence_on_the_fit(self):
        frequencies = np.array(self.truth.hz[:10])
        frequencies[9] *= 1.2
        moved = measured_set(self.LENGTH, self.WIDTH, self.truth, frequencies=frequencies)
        result, block, _review = estimate(moved, self.plate)
        for name in ("E1", "E2", "G12"):
            self.assertAlmostEqual(result.fitted[name] / self.result.fitted[name], 1.0, delta=1.0e-9)
        self.assertEqual(result.fit_quality["holdout_verdict"], rft.HOLDOUT_DISAGREES)  # and the poor prediction is said
        self.assertEqual(block["presentation"]["verdict"], rre.DIAGNOSTIC_ONLY)
        self.assertIn("HOLDOUT record(s) 10 are not predicted", " ".join(block["presentation"]["reasons"]))
        self.assertEqual(block["constants"]["kind"], "DIAGNOSTIC_ONLY_VALUES")

    def test_the_fit_is_the_same_whether_the_other_records_are_predicted_or_left_out(self):
        """HOLDOUT against EXCLUDED for records 9 and 10: the FIT branches are recognised by themselves, so the fitted
        values are the same numbers, and no FIT record changes its Ritz mode."""
        result, block = rre.run_estimation(self.rset, self.plate, request(self.rset, holdout=(), excluded=(9, 10)),
                                           self.review)
        for name in ("E1", "E2", "G12"):
            self.assertAlmostEqual(result.fitted[name] / self.result.fitted[name], 1.0, delta=1.0e-9)
        kept = {row["record"]: row["fitted_rank"] for row in block["branch"]["rows"]}
        self.assertEqual(kept, {k: k for k in range(1, 9)})
        rows = {row["record"]: row for row in result.rows}
        self.assertEqual((rows[9]["role"], rows[9]["rank"], rows[8]["rank"]), (rft.EXCLUDED, None, 8))

    def test_the_first_record_is_fitted_and_identities_are_kept(self):
        fit = request(self.rset)
        self.assertEqual((fit.observations[0].record, fit.observations[0].role, fit.observations[0].surrogate_rank),
                         (1, rft.FIT, 1))
        self.assertTrue(self.result.first_mode_check["done"])
        self.assertEqual(self.result.first_mode_check["left_out_record"], 1)  # checked, and still in the fit
        rows = self.block["correspondence"]["reference"]["rows"]
        self.assertEqual([(row["record"], row["rank"], row["role"]) for row in rows],
                         [(k, k, rft.HOLDOUT if k > 8 else rft.FIT) for k in range(1, 11)])
        self.assertEqual([row["fe_pair"] for row in rows[:2]], [[7, 0.99], [8, 0.99]])
        self.assertEqual([row["verdict"] for row in rows], [rre.AGREES] * 10)
        branch = self.block["branch"]
        self.assertEqual(branch["verdict"], rre.BRANCHES_TRACKED)
        self.assertEqual([(row["record"], row["reference_rank"], row["status"]) for row in branch["rows"]],
                         [(k, k, rre.TRACKED) for k in range(1, 11)])

    def test_the_seven_statements_are_separate(self):
        titles = [row[0] for row in self.block["statements"]]
        self.assertEqual(titles, ["1. Optimizer convergence", "2. Parameter identifiability", "3. FIT spectral residuals",
                                  "4. HOLDOUT predictive residuals", "5. Modal correspondence and branches",
                                  "6. Model assumptions", "7. Physical validity"])
        verdicts = [row[1] for row in self.block["statements"]]
        self.assertEqual(verdicts[0], rft.SUPPORTED)
        self.assertEqual(verdicts[2], rft.FIT_WITHIN)
        self.assertEqual(verdicts[4], f"{rre.SHAPE_REVIEWED}; {rre.BRANCHES_TRACKED}")
        self.assertEqual(verdicts[6], rft.NOT_ESTABLISHED)  # a supported fit establishes no physical validity
        self.assertEqual(self.result.validity["physical_validation"], rft.NOT_ESTABLISHED)
        self.assertEqual(self.result.label, rft.RESULT_LABEL)

    def test_every_quantity_names_its_category_and_source(self):
        table = {row["quantity"].split(" ")[0]: row for row in self.result.quantities}
        self.assertEqual(table["Natural"]["category"], rre.MEASURED)
        self.assertIn("synthetic scan.unv, SHA-256 abababababab", table["Natural"]["source"])
        self.assertIn("USER_CONFIRMED_REGISTRATION", table["Physical"]["category"])
        self.assertIn("confirmed by A. Tester", table["Physical"]["source"])
        self.assertEqual((table["Length"]["category"], table["Mass"]["category"]), (rre.MEASURED, rre.MEASURED))
        self.assertEqual(table["nu12"]["category"], rre.DECLARED + ", FIXED, NOT IDENTIFIED")
        self.assertEqual(table["Surface"]["category"], rre.COMPUTED)
        self.assertEqual(table["Material"]["category"], rre.DECLARED)
        self.assertIn("set neither the start nor the bounds", table["Reference"]["source"])
        self.assertEqual(self.result.quantities[-1]["category"], rre.ESTIMATE)
        self.assertEqual(self.result.assumptions, rre.ASSUMPTIONS)

    def test_the_reference_constants_are_not_a_hidden_target(self):
        """Another declared reference, reviewed again, on the same data: the same estimate. The reference serves the
        shape review only; the start and the bounds of the fit are scaled from the measured frequencies."""
        other = replace_plate(self.plate, reference=(47000.0, 45000.0, 6500.0))
        review = rre.shape_review(self.rset, other)
        declared = reviewed_ranks(review)
        self.assertTrue(declared, "at this reference two modes stand in another order than in the data")
        result, block = rre.run_estimation(self.rset, other, request(self.rset, declared=declared), review)
        self.assertEqual(block["presentation"]["verdict"], rre.SUPPORTED_ESTIMATE, block["presentation"]["reasons"])
        for name, expected in zip(("E1", "E2", "G12"), self.TRUTH):
            self.assert_close(result.fitted[name], expected, msg=name)
            self.assertAlmostEqual(result.fitted[name] / self.result.fitted[name], 1.0, delta=1.0e-6)
        self.assertEqual(result.initialization["inp_values_used"], "no (shown for comparison only)")
        self.assertEqual(result.baseline["E1"], 47000.0)  # the reference is the comparison column, nothing else

    def test_the_stability_check_follows_the_same_branches(self):
        fit = request(self.rset)
        inputs = rre.plate_inputs(self.plate)
        tracked = rre.tracked_request(self.rset, self.plate, fit, self.review)
        stability = rfs.run_stability(inputs, tracked, self.result)
        done = [item for item in stability["leave_one_out"] if item.get("done")]
        self.assertEqual(len(done), 8)
        for item in done:
            self.assertLess(max(abs(v) for v in item["change"].values()), 1.0e-3)


class IsotropicInPlaneRecoveryTests(unittest.TestCase):
    """A 301 mm square plate with E1 = E2: two unknowns. Its exactly degenerate mode pairs carry no identity of their
    own, so they are predicted (HOLDOUT), not fitted."""

    SIDE, TRUTH = 301.0, (52000.0, 52000.0, 4500.0)

    @classmethod
    def setUpClass(cls):
        cls.truth = truth_plate(cls.SIDE, cls.SIDE, *cls.TRUTH)
        cls.rset = measured_set(cls.SIDE, cls.SIDE, cls.truth)
        cls.plate = plate(cls.SIDE, cls.SIDE, (40000.0, 40000.0, 6000.0))

    def test_the_degenerate_pairs_are_recognised_and_given_a_group_value_only(self):
        review = rre.shape_review(self.rset, self.plate)
        self.assertEqual(review["degenerate_groups"], [[4, 5], [7, 8], [11, 12]])
        table = rre.review_correspondence(review, self.rset, self.plate, request(self.rset, rft.TIED).observations)
        verdicts = {row["record"]: row["verdict"] for row in table["rows"]}
        self.assertEqual([verdicts[k] for k in (4, 5, 7, 8)], [rre.UNCERTAIN] * 4)
        self.assertEqual([verdicts[k] for k in (1, 2, 3, 6, 9, 10)], [rre.AGREES] * 6)
        group = next(g for g in table["groups"] if g["ranks"] == [4, 5])
        self.assertTrue(group["exactly_degenerate"])
        self.assertGreater(group["subspace_mac"], 0.999)  # the pair as a whole spans the same shapes (other constants)
        self.assertLess(min(mac for _record, _rank, mac in group["individual"]), 0.999)  # which no single record shows
        self.assertIn("not an identity of any record", group["subspace_note"])

    def test_fitting_the_uncertain_records_is_diagnostic_only(self):
        result, block, _review = estimate(self.rset, self.plate, rft.TIED)
        self.assertEqual(result.status, rft.SUPPORTED)
        self.assertEqual(block["presentation"]["verdict"], rre.DIAGNOSTIC_ONLY)
        self.assertIn("FIT record(s) 4, 5, 7, 8 lie in a group of close Ritz modes", " ".join(block["presentation"]["reasons"]))

    def test_the_known_values_are_recovered_from_the_identified_records(self):
        result, block, _review = estimate(self.rset, self.plate, rft.TIED, holdout=(4, 5, 7, 8))
        self.assertEqual(result.status, rft.SUPPORTED, result.reasons)
        self.assertEqual(block["presentation"], {"verdict": rre.SUPPORTED_ESTIMATE, "reasons": []})
        self.assertAlmostEqual(result.fitted["E1"] / 52000.0, 1.0, delta=RECOVERY)
        self.assertEqual(result.fitted["E1"], result.fitted["E2"])
        self.assertAlmostEqual(result.fitted["G12"] / 4500.0, 1.0, delta=RECOVERY)
        d11, d22, _d12, d66 = stiffness(*self.TRUTH)
        values = block["stiffness"]["values"]
        self.assertAlmostEqual(values["D11"] / d11, 1.0, delta=RECOVERY)
        self.assertEqual(values["D11"], values["D22"])
        self.assertAlmostEqual(values["D66"] / d66, 1.0, delta=RECOVERY)
        self.assertEqual(block["constants"]["kind"], "AXIS_FREE_VALUES")  # no material axis was stated
        self.assertEqual(block["constants"]["rows"][0][0], "E (one in-plane modulus, tied by the chosen form)")
        self.assertLess(result.rms_holdout_after, 2.0 * FREQUENCY_AGREEMENT)  # the degenerate pairs are predicted

    def test_the_tied_form_needs_equal_reference_moduli(self):
        with self.assertRaises(rre.EstimationRefused) as refused:
            estimate(self.rset, replace_plate(self.plate, reference=(41000.0, 40000.0, 6000.0)), rft.TIED)
        self.assertIn("needs equal reference E1 and E2", str(refused.exception))


# ------------------------------------------------------------------------------------------- correspondence and branches


class CorrespondenceTests(_Rectangle):
    """Reference constants at which two modes stand in the other order than in the measured plate."""

    CROSSED = (42000.0, 64000.0, 4600.0)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.crossed = plate(cls.LENGTH, cls.WIDTH, cls.CROSSED)
        cls.crossed_review = rre.shape_review(cls.rset, cls.crossed)
        cls.moved = reviewed_ranks(cls.crossed_review)  # what a reviewer reads off the table and declares

    def test_the_review_shows_a_permutation_against_the_frequency_order(self):
        moved = self.moved
        self.assertGreaterEqual(len(moved), 2, "the crossed reference must reorder at least two modes")
        table = rre.review_correspondence(self.crossed_review, self.rset, self.crossed, request(self.rset).observations)
        verdicts = {row["record"]: row["verdict"] for row in table["rows"]}
        for record in moved:  # the frequency-rank hypothesis is contradicted by shape, record by record
            self.assertIn(verdicts[record], (rre.CONTRADICTS, rre.UNCERTAIN), record)
            row = table["rows"][record - 1]
            self.assertEqual(row["best_rank"], moved[record])
            self.assertGreater(row["best_mac"], row["mac"])
        self.assertTrue(table["contradicting"] or table["uncertain"])
        # nothing was re-paired: every record still stands at its own frequency rank
        self.assertEqual([row["rank"] for row in table["rows"]], list(range(1, 11)))

    def test_the_declared_permutation_agrees_and_the_branches_are_followed_across_the_crossing(self):
        declared = self.moved
        fit = request(self.rset, declared=declared, holdout=(9, 10))
        result, block = rre.run_estimation(self.rset, self.crossed, fit, self.crossed_review)
        self.assertEqual(result.status, rft.SUPPORTED, result.reasons)
        for name, expected in zip(("E1", "E2", "G12"), self.TRUTH):
            self.assert_close(result.fitted[name], expected, msg=name)
        reference = block["correspondence"]["reference"]
        self.assertEqual(reference["contradicting"], [])
        rows = {row["record"]: row for row in block["branch"]["rows"]}
        for record, rank in declared.items():
            self.assertEqual(rows[record]["reference_rank"], rank)  # the original Ritz rank is kept
            self.assertEqual(rows[record]["fitted_rank"], record)  # and its branch now stands at the record's own rank
            self.assertIn("rank changed against the reference; the branch was followed", rows[record]["note"])
        fitted = {row["record"]: row for row in block["correspondence"]["fitted"]["rows"]}
        for record in range(1, 11):
            self.assertEqual(fitted[record]["verdict"], rre.AGREES)
            self.assertGreater(fitted[record]["mac"], 1.0 - 1.0e-4)
        self.assertEqual(block["presentation"], {"verdict": rre.SUPPORTED_ESTIMATE, "reasons": []})

    def test_another_correspondence_gives_another_result_on_the_same_registration(self):
        declared = self.moved
        good, good_block = rre.run_estimation(self.rset, self.crossed, request(self.rset, declared=declared),
                                              self.crossed_review)
        poor, poor_block = rre.run_estimation(self.rset, self.crossed, request(self.rset), self.crossed_review)
        self.assertEqual(good_block["set_identity"], poor_block["set_identity"])
        self.assertEqual(good_block["registration"], poor_block["registration"])
        self.assertEqual(good_block["presentation"]["verdict"], rre.SUPPORTED_ESTIMATE, good_block["presentation"])
        self.assertEqual(poor_block["presentation"]["verdict"], rre.DIAGNOSTIC_ONLY)
        self.assertIn("contradict their fixed Ritz mode by shape", " ".join(poor_block["presentation"]["reasons"]))
        difference = max(abs(poor.fitted[name] / good.fitted[name] - 1.0) for name in ("E1", "E2", "G12"))
        self.assertGreater(difference, 0.01)  # the correspondence, not the registration, moved the values
        self.assertNotIn(poor_block["constants"]["kind"], ("CONDITIONAL_ENGINEERING_CONSTANTS", "AXIS_FREE_VALUES"))

    def test_a_duplicated_correspondence_is_refused_before_anything_is_solved(self):
        fit = request(self.rset, declared={3: 2})
        with self.assertRaises(rft.TuningRefused) as refused:
            rre.run_estimation(self.rset, self.plate, fit, self.review)
        self.assertIn("rank 2 is assigned to records 2, 3", str(refused.exception))

    def test_too_few_fit_records_are_refused(self):
        for kept in ((1,), (1, 2, 3)):
            fit = request(self.rset, holdout=(), excluded=tuple(k for k in range(1, 11) if k not in kept))
            with self.assertRaises(rft.TuningRefused) as refused:
                rre.run_estimation(self.rset, self.plate, fit, self.review)
            self.assertIn(f"{len(kept)} FIT frequencies cannot determine 3 parameters", str(refused.exception))

    def test_a_review_of_other_inputs_is_not_used(self):
        other_set = measured_set(self.LENGTH, self.WIDTH, self.truth, source=dict(SOURCE, modal_set_key="other"))
        for rset, declared in ((other_set, self.plate), (self.rset, replace_plate(self.plate, mass_g=121.0))):
            with self.assertRaises(rre.EstimationRefused) as refused:
                rre.run_estimation(rset, declared, request(rset), self.review)
            self.assertEqual(refused.exception.code, rre.REVIEW_STALE)
        wrong = rft.TuningRequest(rft.observations_by_rank(self.rset.records[:9] + ((77, 500.0),), holdout=(9,)), rft.FREE)
        with self.assertRaises(rre.EstimationRefused) as refused:
            rre.run_estimation(self.rset, self.plate, wrong, self.review)
        self.assertIn("does not name exactly the records of the registered set", str(refused.exception))

    def test_without_a_shape_review_the_fit_is_an_unverified_rank_hypothesis(self):
        result, block, _none = estimate(self.rset, replace_plate(self.plate, linked=False), reviewed=False)
        self.assertEqual(block["correspondence"]["kind"], rre.RANK_HYPOTHESIS)
        self.assertIn("UNVERIFIED CORRESPONDENCE HYPOTHESIS", block["correspondence"]["statement"])
        self.assertEqual(block["branch"]["verdict"], rre.BRANCHES_NOT_FOLLOWED)
        self.assertNotEqual(block["presentation"]["verdict"], rre.SUPPORTED_ESTIMATE)
        self.assertNotEqual(block["constants"]["kind"], "CONDITIONAL_ENGINEERING_CONSTANTS")
        self.assertFalse([name for name, _v in block["constants"]["rows"] if name.startswith(("E1", "E2"))])
        if block["presentation"]["verdict"] == rre.DIAGNOSTIC_ONLY:
            self.assertIn("unverified frequency-rank hypothesis", " ".join(block["presentation"]["reasons"]))


class BranchTests(unittest.TestCase):
    """A square plate: with E1 = E2 the two bending modes of each pair veer, and their character changes hands."""

    SIDE = 301.0

    def tracker(self, reference, top=6):
        return rre.BranchTracker(rre.plate_inputs(plate(self.SIDE, self.SIDE, reference)), reference, top, 14)

    def observations(self, count=6):
        return rft.observations_by_rank([(k + 1, 10.0 * (k + 1)) for k in range(count)])

    def test_a_branch_near_the_reference_is_followed_in_one_step(self):
        tracker = self.tracker((60000.0, 42000.0, 5000.0))
        report, _solution, compared = rre.branch_report(tracker, (62000.0, 41000.0, 5100.0), self.observations())
        self.assertEqual(report["verdict"], rre.BRANCHES_TRACKED)
        self.assertEqual(compared, {k: k for k in range(1, 7)})
        self.assertEqual(report["path_steps"], 1)
        self.assertTrue(all(row["lowest_step_mac"] >= rre.TRACKING_MINIMUM_MAC for row in report["rows"]))

    def test_a_crossing_of_distinct_shapes_is_followed_and_the_rank_change_is_reported(self):
        """From E1 > E2 to E1 < E2 the two bending modes change places in frequency while each keeps its shape: the
        branch is followed, and the report shows the new rank instead of re-pairing by rank."""
        tracker = self.tracker((60000.0, 42000.0, 5000.0))
        report, _solution, compared = rre.branch_report(tracker, (42000.0, 60000.0, 5000.0), self.observations())
        self.assertEqual(report["verdict"], rre.BRANCHES_TRACKED)
        moved = [row for row in report["rows"] if row["fitted_rank"] != row["reference_rank"]]
        self.assertGreaterEqual(len(moved), 2)
        self.assertEqual(sorted(row["fitted_rank"] for row in moved), sorted(row["reference_rank"] for row in moved))
        self.assertTrue(all("rank changed against the reference; the branch was followed" in row["note"] for row in moved))
        self.assertEqual(sorted(compared.values()), list(range(1, 7)))  # one-to-one: no mode is used twice

    def test_a_mode_the_fit_compared_that_the_path_does_not_reach_is_a_lost_branch(self):
        from unittest import mock

        tracker = self.tracker((60000.0, 42000.0, 5000.0))
        followed = tracker.follow((62000.0, 41000.0, 5100.0))
        followed["index"][1], followed["index"][2] = followed["index"][2], followed["index"][1]
        with mock.patch.object(tracker, "follow", return_value=followed):
            report, _solution, _compared = rre.branch_report(tracker, (62000.0, 41000.0, 5100.0), self.observations())
        status = {row["reference_rank"]: row for row in report["rows"]}
        self.assertEqual((status[2]["status"], status[3]["status"]), (rre.LOST, rre.LOST))
        self.assertIn("the followed path arrives at rank 3, the fit compared rank 2", status[2]["note"])
        self.assertEqual(report["verdict"], rre.BRANCH_NOT_IDENTIFIABLE)

    def test_the_gradual_change_of_the_bending_pair_is_followed_step_by_step(self):
        """Towards E1 = E2 the two bending modes turn into their sum and difference. Seen from the reference in one look
        they are half alike; followed in steps, each stays the continuation of its own mode."""
        tracker = self.tracker((60000.0, 42000.0, 5000.0))
        report, _solution, _compared = rre.branch_report(tracker, (51500.0, 51000.0, 5000.0), self.observations())
        rows = {row["reference_rank"]: row for row in report["rows"]}
        for rank in (2, 3):
            self.assertEqual(rows[rank]["status"], rre.TRACKED)
            self.assertLess(rows[rank]["mac_to_reference"], rre.TRACKING_MINIMUM_MAC)  # not recognisable in one look
            self.assertGreaterEqual(rows[rank]["lowest_step_mac"], rre.TRACKING_MINIMUM_MAC)  # yet followed in steps
        self.assertGreater(report["path_steps"], 1)

    def test_a_step_that_stays_unclear_down_to_the_smallest_step_is_an_ambiguous_crossing(self):
        """The tracking level is raised here, only to provoke the case: a branch that is not found again at the level
        even with the smallest step is reported as ambiguous at that place, and support is withheld."""
        from unittest import mock

        tracker = self.tracker((60000.0, 42000.0, 5000.0))
        with mock.patch.object(rre, "TRACKING_MINIMUM_MAC", 1.0 - 1.0e-9):
            report, _solution, _compared = rre.branch_report(tracker, (51500.0, 51000.0, 5000.0), self.observations())
        self.assertEqual(report["verdict"], rre.BRANCH_NOT_IDENTIFIABLE)
        failed = [row for row in report["rows"] if row["status"] != rre.TRACKED]
        unclear = [row for row in failed if "no clear continuation" in row["note"]]
        self.assertTrue({2, 3} <= {row["reference_rank"] for row in unclear})
        self.assertTrue(all(row["status"] == rre.AMBIGUOUS for row in failed))
        self.assertEqual(report["smallest_path_step"], 1.0 / 64.0)
        self.assertIn("could not be followed", report["statement"])
        block = {"correspondence": {"kind": rre.SHAPE_REVIEWED, "reference": {}, "fitted": {}}, "branch": report}
        shown = rre.presentation_of(rft.SUPPORTED, {"verdict": rft.FIT_WITHIN}, block)
        self.assertEqual(shown["verdict"], rre.DIAGNOSTIC_ONLY)
        self.assertIn("diagnostic only", " ".join(shown["reasons"]))

    def test_an_exactly_degenerate_fitted_mode_is_ambiguous(self):
        tracker = self.tracker((52000.0, 52000.0, 4500.0))
        report, _solution, _compared = rre.branch_report(tracker, (53000.0, 53000.0, 4600.0), self.observations())
        status = {row["reference_rank"]: row["status"] for row in report["rows"]}
        self.assertEqual((status[4], status[5]), (rre.AMBIGUOUS, rre.AMBIGUOUS))
        self.assertEqual((status[1], status[2], status[3], status[6]), (rre.TRACKED,) * 4)

    def test_the_tracking_level_is_the_ritz_services_own(self):
        from services import plate_ritz_forward as prf
        import inspect

        self.assertEqual(rre.TRACKING_MINIMUM_MAC,
                         inspect.signature(prf.ritz_central_difference_check).parameters["tracking_minimum_mac"].default)


# ------------------------------------------------------------------------------------------- quality and status


class QualityTests(_Rectangle):
    def test_a_converged_high_misfit_stays_diagnostic(self):
        frequencies = np.array(self.truth.hz[:10])
        frequencies[3] *= 1.12
        result, block, _review = estimate(measured_set(self.LENGTH, self.WIDTH, self.truth, frequencies=frequencies), self.plate)
        self.assertIn(result.status, (rft.SUPPORTED, rft.MIRROR, rft.STARTS_DISAGREE))
        self.assertEqual(result.fit_quality["verdict"], rft.HIGH_MISFIT)
        self.assertNotEqual(block["presentation"]["verdict"], rre.SUPPORTED_ESTIMATE)
        if result.status == rft.SUPPORTED:
            self.assertEqual(block["presentation"]["verdict"], rre.DIAGNOSTIC_ONLY)
            self.assertIn("HIGH_MISFIT", " ".join(block["presentation"]["reasons"]))
            self.assertEqual(block["constants"]["kind"], "DIAGNOSTIC_ONLY_VALUES")
            self.assertFalse([name for name, _v in block["constants"]["rows"] if name.startswith(("E1", "E2"))])

    def test_unseparable_parameters_give_no_estimate(self):
        """Four records that barely feel one modulus: the practical rank or the condition number says so."""
        sensitivity = {row["record"]: row for row in self.result.sensitivity}
        weakest = sorted(sensitivity, key=lambda record: abs(sensitivity[record]["E2"]))[:4]
        fit = request(self.rset, holdout=(), excluded=tuple(k for k in range(1, 11) if k not in weakest))
        result, block = rre.run_estimation(self.rset, self.plate, fit, self.review)
        if result.status in (rft.NOT_IDENTIFIABLE, rft.AT_BOUND, rft.STARTS_DISAGREE, rft.NOT_CONVERGED):
            self.assertEqual(block["presentation"]["verdict"], rre.NO_ESTIMATE)
            self.assertEqual(block["constants"], dict(block["constants"], kind="WITHHELD", rows=[]))
            self.assertEqual(block["stiffness"]["alternatives"], [])
        else:  # separable after all: then the statement of identifiability carries the large condition number
            self.assertGreater(result.condition_number, self.result.condition_number)
        self.assertEqual(block["statements"][1][0], "2. Parameter identifiability")

    def test_a_square_plate_fitted_by_rank_alone_names_no_axis(self):
        """Exchanged E1 and E2 give the same frequencies on a square: without shapes neither is chosen."""
        truth = truth_plate(301.0, 301.0, 62000.0, 44000.0, 4600.0)
        rset = measured_set(301.0, 301.0, truth)
        declared = plate(301.0, 301.0, (50000.0, 50000.0, 5000.0), linked=False)
        result, block, _none = estimate(rset, declared, reviewed=False)
        self.assertNotEqual(block["presentation"]["verdict"], rre.SUPPORTED_ESTIMATE)
        self.assertFalse([name for name, _v in block["constants"]["rows"] if name.startswith(("E1", "E2"))])
        if result.status == rft.MIRROR:
            self.assertEqual(len(block["stiffness"]["alternatives"]), 2)
            self.assertIn("not identifiable", " ".join(block["constants"]["reasons"]))


# ------------------------------------------------------------------------------------------- saving


class SavedResultTests(_Rectangle):
    def saved(self, block=None, result=None):
        folder = Path(tempfile.mkdtemp())
        path = folder / "estimate.json"
        rft.write_export(rre.export_document(result or self.result, block or self.block), path)
        return path

    def test_an_export_holds_the_provenance_and_no_abaqus_block(self):
        document = json.loads(self.saved().read_text(encoding="utf-8"))
        self.assertIsNone(document["abaqus_elastic_candidate"])
        self.assertIn("No INP", document["abaqus_elastic_candidate_withheld"])
        self.assertEqual(document["sources"]["unv_sha256"], "ab" * 32)
        self.assertEqual(document["inputs"]["inp_path"], "")
        block = document["registered_estimation"]
        self.assertEqual((block["schema"], block["label"]), (rre.SCHEMA, rre.LABEL))
        self.assertEqual(block["plate"]["mass_g"], MASS)
        self.assertEqual(block["plate"]["categories"][4], rre.DECLARED)
        self.assertIn("NOT_PRODUCTION_AUTO_ID", document["statement"])

    def test_a_reopened_result_is_the_saved_result_without_a_fit(self):
        from unittest import mock

        path = self.saved()
        with mock.patch.object(rft, "run_tuning", side_effect=AssertionError("refitted")), \
                mock.patch.object(rft, "solve_ritz", side_effect=AssertionError("solved")):
            document = rft.read_export(path)
            result = rft.result_from_export(document)
            block = rre.block_from_export(document, result)
        self.assertEqual(result.fitted, self.result.fitted)
        self.assertEqual(block, self.block)
        self.assertEqual(json.loads(json.dumps(block)), json.loads(json.dumps(self.block)))

    def test_a_file_cannot_raise_its_own_status(self):
        """A diagnostic result whose file is edited to claim support and named constants opens as diagnostic."""
        frequencies = np.array(self.truth.hz[:10])
        frequencies[9] *= 1.2
        result, block, _review = estimate(measured_set(self.LENGTH, self.WIDTH, self.truth, frequencies=frequencies), self.plate)
        self.assertEqual(block["presentation"]["verdict"], rre.DIAGNOSTIC_ONLY)
        path = self.saved(block, result)
        document = json.loads(path.read_text(encoding="utf-8"))
        document["registered_estimation"]["presentation"] = {"verdict": rre.SUPPORTED_ESTIMATE, "reasons": []}
        document["registered_estimation"]["constants"] = dict(self.block["constants"])
        document["registered_estimation"]["stiffness"]["values"]["D11"] = 999.0
        path.write_text(json.dumps(document), encoding="utf-8")
        opened = rre.block_from_export(rft.read_export(path), rft.result_from_export(rft.read_export(path)))
        self.assertEqual(opened["presentation"]["verdict"], rre.DIAGNOSTIC_ONLY)
        self.assertEqual(opened["constants"]["kind"], "DIAGNOSTIC_ONLY_VALUES")
        self.assertEqual(opened["stiffness"]["values"], block["stiffness"]["values"])

    def test_a_damaged_or_foreign_part_is_refused(self):
        path = self.saved()
        document = json.loads(path.read_text(encoding="utf-8"))
        result = rft.result_from_export(document)
        for change, words in ((lambda b: b.update(schema="other/1"), "another version"),
                              (lambda b: b.pop("branch"), "incomplete: branch missing"),
                              (lambda b: b["correspondence"].update(kind="CERTIFIED"), "unknown kind"),
                              (lambda b: b.update(plate={"length_mm": 1.0}), "damaged")):
            damaged = json.loads(json.dumps(document))
            change(damaged["registered_estimation"])
            with self.assertRaises(rft.TuningRefused) as refused:
                rre.block_from_export(damaged, result)
            self.assertIn(words, str(refused.exception))
        self.assertIsNone(rre.block_from_export({k: v for k, v in document.items() if k != "registered_estimation"}, result))


# ------------------------------------------------------------------------------------------- the page, end to end

import test_abm_aud4_modal_comparison as a4  # noqa: E402  (the Analyze fixture: a 301 mm FE model, a scan turned 45 degrees)

from new_gui import analyze_model as am  # noqa: E402
from new_gui import production_window as pw  # noqa: E402
from new_gui import research_tuning_model as rm  # noqa: E402

FILE_RECOVERY = 5.0e-4  # through the UNV file: frequencies and coordinates carry six significant digits
SQUARE = 301.0
SQUARE_TRUTH = (52000.0, 52000.0, 4500.0)
FE_FACTOR = 0.976  # the FE model of the fixture stands a little low, as an FE model with other constants would


def mode_function(truth, k):
    """Truth mode k as a function of FE positions (mm, the corner at the origin), for the Analyze fixture."""
    def value(points):
        points = np.asarray(points, dtype=float)
        return truth.field((points[:, 0] - SQUARE / 2.0) * 1.0e-3, (points[:, 1] - SQUARE / 2.0) * 1.0e-3)[:, k]
    return value


class _Page(a4._Compared):
    """Analyze with a confirmed registration and a comparison, then the Research Tuning page of the same window."""

    RECORDS = 10

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.truth = truth_plate(SQUARE, SQUARE, *SQUARE_TRUTH)

    def modal_lists(self, frequencies=None):
        hz = self.truth.hz[:self.RECORDS] if frequencies is None else frequencies
        fe = [(FE_FACTOR * float(self.truth.hz[k]), mode_function(self.truth, k)) for k in range(self.RECORDS)]
        experimental = [(float(hz[k]), mode_function(self.truth, k)) for k in range(self.RECORDS)]
        return fe, experimental

    def tuning(self, frequencies=None):
        analyze, analysis = self.compared(*self.modal_lists(frequencies))
        window = analyze.window()
        panel = window.research_tuning
        self.confirmations = []
        panel._ask_confirm = lambda title, text: (self.confirmations.append((title, text)), True)[1]
        window.show_page(pw.TUNING_PAGE)
        self.app.processEvents()
        return window, analyze, panel

    def wait_tuning(self, panel, limit=120.0):
        import time

        end = time.monotonic() + limit
        while panel.busy() and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()
        self.assertFalse(panel.busy())

    def declare(self, panel, **changes):
        values = dict(length=SQUARE, width=SQUARE, thickness=THICKNESS, mass=MASS, nu12=NU12, source="measurement sheet 12",
                      categories={"length": rre.MEASURED, "width": rre.MEASURED, "thickness": rre.MEASURED,
                                  "mass": rre.MEASURED, "nu12": rre.DECLARED},
                      length_axis="X", width_axis="Y", linked=True, E1=40000.0, E2=40000.0, G12=6000.0)
        values.update(changes)
        panel.set_plate(**values)
        self.app.processEvents()

    def reviewed(self, panel):
        self.assertTrue(panel.review_shapes(), panel.message.text())
        self.wait_tuning(panel)
        self.assertIsNotNone(panel.review, panel.message.text())

    def roles(self, panel, holdout=(4, 5, 7, 8)):
        for record in range(1, self.RECORDS + 1):
            panel.set_role(record, rft.HOLDOUT if record in holdout else rft.FIT)
        self.app.processEvents()

    def fitted(self, panel):
        panel.reg_fixed.setChecked(True)
        self.assertTrue(panel.run(), panel.message.text())
        self.wait_tuning(panel)
        self.assertIsNotNone(panel.result, panel.message.text())
        return panel.result, panel.block

    def cells(self, panel, key) -> list:
        return panel.table_cells(f"{key}")


class PageWorkflowTests(_Page):
    def test_from_the_confirmed_comparison_to_the_stiffness_estimate(self):
        _window, analyze, panel = self.tuning()
        self.assertTrue(panel.use_registered(), panel.registered_state.text())
        identity = dict(self.cells(panel, "registered_identity"))
        self.assertIn("turned scan.unv", identity["Experimental file"])
        self.assertEqual(identity["SHA-256"], analyze.inputs.identities["experimental"]["sha256"])
        self.assertIn("USER_CONFIRMED_REGISTRATION", identity["Registration"])
        self.assertIn("confirmed by A. Tester", identity["Registration"])
        self.assertIn("FE mm, experimental m, measured side +Z", identity["Units and measured side"])
        self.assertIn("record 1 - FE 7", identity["FE / EXP pairs of the comparison (kept, not used by the fit)"])
        self.assertEqual(sorted(panel.role_combos), list(range(1, 11)))  # the records as read, the first one among them
        self.assertEqual(panel.roles()[1], rft.FIT)
        self.assertIn("Not ready", panel.registered_check.text())  # nothing is prefilled
        self.assertEqual(panel.reg_fields["length"].text(), "")
        self.assertEqual(panel.reg_categories["mass"].value(), "")
        self.assertEqual(panel.run_button.text(), "Run research fit...")

        self.declare(panel)
        self.assertEqual(panel.registered_check.text(), "")
        self.reviewed(panel)
        frame = dict(self.cells(panel, "reg_frame"))
        self.assertIn("301 x 301 x 0 mm", frame["FE extent along x, y, normal"])
        self.assertIn("289 DOFs at 289 points", frame["Registered measurement"])
        mac = self.cells(panel, "reg_mac")
        self.assertEqual(len(mac), 10)
        for row in (0, 1, 2, 5):  # the modes with a shape of their own stand on the diagonal
            self.assertGreater(float(mac[row][2 + row]), 0.99)
        self.roles(panel)
        verdicts = {row[0]: row[7] for row in self.cells(panel, "reg_correspondence")}
        self.assertEqual([verdicts[str(k)] for k in (1, 2, 3, 6, 9, 10)], ["agrees"] * 6)
        self.assertEqual([verdicts[str(k)] for k in (4, 5, 7, 8)], ["UNCERTAIN: close Ritz modes"] * 4)
        self.assertRegex(self.cells(panel, "reg_correspondence")[0][8], r"^FE 7 \(MAC (0\.99\d|1\.000)\)$")  # the comparator's pair
        self.assertIn("Every FIT record agrees by shape", panel.review_summary.text())
        self.assertIn("HOLDOUT record(s) 4, 5, 7, 8 do not agree by shape", panel.review_summary.text())
        groups = self.cells(panel, "reg_groups")
        self.assertTrue(any("exactly degenerate" in row[0] and "not an identity of any record" in row[2] for row in groups))

        result, block = self.fitted(panel)
        title, text = self.confirmations[-1]
        self.assertEqual(title, "Run one research fit")
        for words in ("record 1 (", "FIT, Ritz rank 1, shape agrees", "record 4", "HOLDOUT, Ritz rank 4",
                      "length 301 mm (MEASURED)", "mass 120 g (MEASURED)", "nu12 0.05 (DECLARED ASSUMPTION)",
                      "Fitted: E1=E2, G12", "divided and multiplied by 10", "Model assumptions:", "free on all edges",
                      "Material axis 1: not stated", "not a scientific approval of any value"):
            self.assertIn(words, text)
        self.assertEqual(result.status, rft.SUPPORTED, result.reasons)
        self.assertEqual(block["presentation"]["verdict"], rre.SUPPORTED_ESTIMATE, block["presentation"]["reasons"])
        self.assertAlmostEqual(result.fitted["E1"] / SQUARE_TRUTH[0], 1.0, delta=FILE_RECOVERY)
        self.assertAlmostEqual(result.fitted["G12"] / SQUARE_TRUTH[2], 1.0, delta=FILE_RECOVERY)
        d11, _d22, d12, d66 = stiffness(*SQUARE_TRUTH)
        shown = {row[0].split(" ")[0]: row for row in self.cells(panel, "reg_stiffness")}
        self.assertAlmostEqual(float(shown["D11"][1]) / d11, 1.0, delta=FILE_RECOVERY)
        self.assertAlmostEqual(float(shown["D66"][1]) / d66, 1.0, delta=FILE_RECOVERY)
        self.assertAlmostEqual(float(shown["D12"][1]) / d12, 1.0, delta=2.0e-3)  # four printed decimals of a small number
        self.assertEqual(shown["D11"][2], rre.ESTIMATE)
        self.assertIn("FIXED RELATION", shown["D12"][2])
        constants = self.cells(panel, "reg_constants")
        self.assertEqual(constants[0][0], "E (one in-plane modulus, tied by the chosen form)")
        self.assertEqual(constants[0][2], "RESEARCH ESTIMATE WITHOUT A MATERIAL AXIS")
        self.assertIn("E1 and E2 are not named", panel.constants_note.text())
        self.assertIn("NUMERICALLY SUPPORTED RESEARCH ESTIMATE", panel.presentation.text())
        self.assertIn("NOT_PRODUCTION_AUTO_ID", panel.presentation.text())
        self.assertEqual(panel.presentation.property("state"), "chosen")
        self.assertEqual(panel.validity.property("state"), "blocked")
        self.assertIn("PHYSICAL VALIDITY: NOT ESTABLISHED", panel.validity.text())
        statements = self.cells(panel, "reg_statements")
        self.assertEqual(len(statements), 7)
        self.assertEqual(statements[6][1], rft.NOT_ESTABLISHED)
        branch = self.cells(panel, "reg_branch")
        self.assertEqual({row[7] for row in branch if row[1] == rft.FIT}, {rre.TRACKED})
        self.assertIn("Every fixed FIT branch was followed", panel.branch_statement.text())
        frequencies = self.cells(panel, "frequencies")
        self.assertEqual([row[1] for row in frequencies if row[0] in ("4", "5", "7", "8")], [rft.HOLDOUT] * 4)
        self.assertFalse(panel.candidate_title.isVisible())  # no Abaqus candidate in this route
        self.assertNotIn("candidate", panel._tables)
        self.assertNotIn("estimates", panel._tables)
        quantities = {row[0].split(" ")[0]: row for row in self.cells(panel, "quantities")}
        self.assertEqual(quantities["Mass"][1], rre.MEASURED)
        self.assertEqual(quantities["Record"][1], "FIXED BY THE USER BEFORE THE FIT")

    def test_export_and_reopen_show_the_same_result_without_a_fit(self):
        from unittest import mock

        _window, _analyze, panel = self.tuning()
        panel.use_registered()
        self.declare(panel, material_axis=rre.AXIS_LENGTH, axis_evidence="layup record L-3")
        self.reviewed(panel)
        self.roles(panel)
        result, block = self.fitted(panel)
        self.assertEqual(block["constants"]["kind"], "CONDITIONAL_ENGINEERING_CONSTANTS")
        self.assertEqual(self.cells(panel, "reg_constants")[0][0], "E1 = E2 (tied by the chosen form)")
        keys = ("reg_statements", "reg_stiffness", "reg_constants", "reg_branch", "reg_fitted", "reg_reference",
                "reg_result_frame", "frequencies", "quantities", "fit_quality", "diagnostics")
        before = {key: self.cells(panel, key) for key in keys}
        texts = (panel.presentation.text(), panel.constants_note.text(), panel.status.text(), panel.quality.text())
        path = self.root / "estimate.json"
        self.assertTrue(panel.export(str(path)), panel.message.text())
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(document["registered_estimation"]["registration"]["kind"], "USER_CONFIRMED_REGISTRATION")
        self.assertIsNone(document["abaqus_elastic_candidate"])
        with mock.patch.object(rft, "run_tuning", side_effect=AssertionError("refitted")), \
                mock.patch.object(rre, "shape_review", side_effect=AssertionError("reviewed")), \
                mock.patch.object(am, "confirm_sources", side_effect=AssertionError("a saved result reads no source")):
            self.assertTrue(panel.open_result(str(path)), panel.message.text())
        self.assertEqual({key: self.cells(panel, key) for key in keys}, before)
        self.assertEqual((panel.presentation.text(), panel.constants_note.text(), panel.status.text(), panel.quality.text()),
                         texts)
        self.assertIn("SAVED RESULT", panel.saved_note.text())
        self.assertIn("were not revalidated", panel.saved_note.text())
        self.assertIsNone(panel.registered)  # nothing of the saved result is carried into a new calculation
        self.assertFalse(panel.registered_form.isVisible())
        self.assertFalse(panel.export_button.isEnabled())
        self.assertFalse(panel.stability_button.isEnabled())
        self.assertFalse(panel.run_button.isEnabled())

    def test_an_edited_input_clears_the_result_the_review_and_the_fixing(self):
        _window, _analyze, panel = self.tuning()
        panel.use_registered()
        self.declare(panel)
        self.reviewed(panel)
        self.roles(panel)
        self.fitted(panel)
        self.assertTrue(panel.results_card.isVisible())
        panel.reg_fields["mass"].setText("121")
        self.app.processEvents()
        self.assertIsNone(panel.result)
        self.assertIsNone(panel.block)
        self.assertFalse(panel.results_card.isVisible())
        self.assertIsNone(panel.review)  # the review was made for another mass
        self.assertFalse(panel.reg_fixed.isChecked())
        self.assertNotIn("reg_mac", panel._tables)
        self.assertEqual(panel.state.text(), rm.STALE_TEXT)
        # and a role changed after the fixing withdraws the fixing: the fit cannot start on it
        self.reviewed(panel)
        panel.reg_fixed.setChecked(True)
        panel.set_role(9, rft.EXCLUDED)
        self.app.processEvents()
        self.assertFalse(panel.reg_fixed.isChecked())
        self.assertFalse(panel.run())
        self.assertIn("correspondence is not fixed", panel.message.text())

    def test_nothing_starts_without_the_fixing_or_the_confirmation(self):
        from unittest import mock

        _window, _analyze, panel = self.tuning()
        panel.use_registered()
        self.declare(panel)
        self.reviewed(panel)
        self.roles(panel)
        with mock.patch.object(rre, "run_estimation", side_effect=AssertionError("started")):
            self.assertFalse(panel.run())
            self.assertIn("is not fixed", panel.message.text())
            panel.reg_fixed.setChecked(True)
            panel._ask_confirm = lambda title, text: False
            self.assertFalse(panel.run())
            self.assertEqual(panel.state.text(), "Not started: the calculation was not confirmed.")
            panel.declared.setText("3:2")  # two records on one Ritz rank
            self.app.processEvents()
            panel.reg_fixed.setChecked(True)
            self.assertFalse(panel.run())
            self.assertIn("rank 2 is assigned to records 2, 3", panel.message.text())
        self.assertIsNone(panel.result)

    def test_an_explicit_import_of_the_fe_dimensions_is_marked_as_such(self):
        _window, _analyze, panel = self.tuning()
        panel.use_registered()
        self.assertFalse(panel.take_fe_dimensions())  # the axes are not chosen yet
        self.assertEqual(panel.reg_fields["length"].text(), "")
        panel.set_plate(length_axis="X", width_axis="Y")
        self.assertTrue(panel.take_fe_dimensions())
        self.assertEqual((panel.reg_fields["length"].text(), panel.reg_fields["width"].text()), ("301", "301"))
        self.assertEqual(panel.reg_categories["length"].value(), rre.IMPORTED_FE)
        self.assertEqual(panel.reg_categories["thickness"].value(), "")  # a mid-surface model has no thickness to take
        self.assertEqual(panel.reg_fields["mass"].text(), "")


class PageRefusalTests(_Page):
    def test_without_a_confirmed_registration_there_is_no_registered_set(self):
        """Frequency comparison only, then a saved draft: the page says what is missing and takes nothing."""
        self.fe, self.experimental = (tuple(item) for item in self.modal_lists())
        window, analyze = self.analysed()
        panel = window.research_tuning
        self.assertFalse(panel.use_registered())
        self.assertIn("REGISTRATION_REQUIRED", panel.registered_state.text())
        self.assertIn("a registration draft is not a confirmed registration", panel.registered_state.text())
        self.assertIsNone(panel.registered)
        self.assertFalse(panel.registered_form.isVisible())
        self.assertFalse(panel.run_button.isEnabled())
        self.confirmed(analyze)  # a confirmation that was not applied in a comparison is no registered comparison either
        self.assertFalse(panel.use_registered())
        self.assertIn("REGISTRATION_REQUIRED", panel.registered_state.text())
        self.assertTrue(analyze.tables["nearest"].rowCount())  # the spectrum stays on Analyze

    def test_an_unstated_link_gives_no_shape_and_only_a_diagnostic_rank_fit(self):
        _window, _analyze, panel = self.tuning()
        panel.use_registered()
        self.declare(panel, linked=False)
        self.assertTrue(panel.review_shapes())  # it is tried, and the service refuses it
        self.wait_tuning(panel)
        self.assertIsNone(panel.review)
        self.assertIn("It is not stated that the plate entered here is the registered FE body", panel.message.text())
        self.assertIn("UNVERIFIED CORRESPONDENCE HYPOTHESIS", panel.review_note.text())
        self.roles(panel)
        result, block = self.fitted(panel)
        self.assertIn("UNVERIFIED frequency-rank hypothesis", self.confirmations[-1][1])
        self.assertEqual(block["correspondence"]["kind"], rre.RANK_HYPOTHESIS)
        self.assertNotEqual(block["presentation"]["verdict"], rre.SUPPORTED_ESTIMATE)
        self.assertEqual(panel.presentation.property("state"), "blocked")
        self.assertEqual(panel.status.property("state"), "blocked")
        self.assertFalse([row for row in self.cells(panel, "reg_constants") if row[0].startswith(("E1", "E2"))]
                         if "reg_constants" in panel._tables else [])
        self.assertNotIn("reg_branch", panel._tables)

    def test_a_plate_that_does_not_hold_the_scan_is_refused(self):
        _window, _analyze, panel = self.tuning()
        panel.use_registered()
        self.declare(panel, length=250.0)
        panel.review_shapes()
        self.wait_tuning(panel)
        self.assertIsNone(panel.review)
        self.assertIn("lie outside the entered 250 x 301 mm rectangle", panel.message.text())

    def test_invalid_inputs_are_named_and_nothing_starts(self):
        _window, _analyze, panel = self.tuning()
        panel.use_registered()
        self.declare(panel, mass="-5", nu12="abc", thickness="")
        text = panel.registered_check.text()
        for words in ("Thickness (mm) is not entered.", "nu12 (held fixed): 'abc' is not a number."):
            self.assertIn(words, text)
        self.assertFalse(panel.review_shapes())
        self.declare(panel, mass="-5")
        self.assertIn("Mass must be a positive number (g).", panel.registered_check.text())
        self.declare(panel, nu12="1.3")
        self.assertIn("not positive definite", panel.registered_check.text())
        self.declare(panel, material_axis=rre.AXIS_WIDTH)
        self.assertIn("needs its evidence", panel.registered_check.text())
        panel.reg_fixed.setChecked(True)
        self.assertFalse(panel.run())
        self.assertIsNone(panel.result)

    def test_a_source_file_changed_after_the_comparison_stops_the_fit(self):
        _window, analyze, panel = self.tuning()
        panel.use_registered()
        self.declare(panel)
        self.reviewed(panel)
        self.roles(panel)
        path = Path(analyze.inputs.full_experimental.source_path)
        path.write_text(path.read_text() + "\n", encoding="utf-8")
        panel.reg_fixed.setChecked(True)
        self.assertTrue(panel.run())
        self.wait_tuning(panel)
        self.assertIsNone(panel.result)
        self.assertIn("a source file changed after the comparison", panel.message.text())

    def test_a_source_file_changed_after_the_calculation_releases_the_result(self):
        _window, analyze, panel = self.tuning()
        panel.use_registered()
        self.declare(panel)
        self.reviewed(panel)
        self.roles(panel)
        self.fitted(panel)
        path = Path(analyze.inputs.full_experimental.source_path)
        path.write_text(path.read_text() + "\n", encoding="utf-8")
        self.assertFalse(panel.export(str(self.root / "late.json")))
        self.assertFalse((self.root / "late.json").exists())
        self.assertIsNone(panel.result)
        self.assertIsNone(panel.registered)
        self.assertIn("a source file changed after the calculation", panel.message.text())

    def test_a_new_analysis_or_a_saved_snapshot_releases_the_registered_set(self):
        window, analyze, panel = self.tuning()
        panel.use_registered()
        self.declare(panel)
        self.reviewed(panel)
        self.roles(panel)
        self.fitted(panel)
        project = self.saved(analyze)
        self.assertIsNotNone(panel.registered)  # saving changes nothing of the comparison
        self.assertTrue(analyze.open_project(str(project)))
        self.wait(analyze)
        self.assertIsNotNone(analyze.snapshot)
        self.assertIsNone(panel.registered)
        self.assertIsNone(panel.result)
        self.assertIn("Released", panel.registered_state.text())
        self.assertFalse(panel.use_registered())  # a snapshot's comparison is not carried into a calculation
        self.assertIn("a saved result is a snapshot", panel.registered_state.text())

    def test_frf_peak_records_and_missing_analyses_are_refused_by_the_source(self):
        with self.assertRaises(am.StepFailed) as refused:
            am.registered_source(None, None, "NONE")
        self.assertIn("no analysis of files read in this session", str(refused.exception))
        peaks = SimpleNamespace(registration_outcome=am.PROVISIONAL, comparison=None, comparison_result=None,
                                registration_reason="")
        with self.assertRaises(am.StepFailed) as refused:
            am.registered_source(object(), peaks, "NONE")
        self.assertIn("FRF peak records without validated modal fitting", str(refused.exception))

    def test_the_inp_route_and_the_registered_route_do_not_mix(self):
        _window, _analyze, panel = self.tuning()
        panel.use_registered()
        self.assertIsNotNone(panel.registered)
        panel.choose_file("unv", str(self.root / "other.unv"))
        self.assertIsNone(panel.registered)
        self.assertIn("the INP route's files were chosen", panel.registered_state.text())
        self.assertEqual(panel.run_button.text(), "Run tuning")


class BoundaryTests(unittest.TestCase):
    def test_the_service_starts_no_solver_process_and_touches_no_governed_workflow(self):
        import ast

        source = (ROOT / "src" / "services" / "registered_ritz_estimation.py").read_text(encoding="utf-8")
        imported = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        for name in ("subprocess", "os", "PySide6", "services.plate_material_workflow", "services.inverse_solver",
                     "services.identification_pipeline", "abaqus_bridge", "services.solid_forward_runner"):
            self.assertFalse([item for item in imported if item == name or item.startswith(name + ".")], name)
        for word in ("58000", "43000", "4720", "58.0", "4.72"):  # no expected material value is written into the service
            self.assertNotIn(word, source)


if __name__ == "__main__":
    unittest.main()
