"""PLATE-ONLY-R1: the research study of the effective bending stiffness of one free-free CFRP plate (no Qt).

Synthetic tests (always run) on an analytic orthotropic plate family and the log-linear SURROGATE twin, through the
project's existing services (branch tracking, cluster confirmation, the M5 system, the bounded LM, the evidence chain
and the verdicts, SYNTHETIC_GATE):

- known parameters are recovered at sufficient rank; insufficient rank is refused;
- a confirmed close pair enters as one term: a relabelling inside it changes nothing, while as two single rows it
  biases the estimate;
- thickness at measured mass is exactly collinear with the common D scale (rank deficient);
- an unverified registration refuses every verdict; one frequency cannot give two parameters;
- the first experimental record and the first elastic FE mode are kept;
- the M11 session never replaces the ROTATED working source, and no M11 measurement is attached to the new plate;
- a research candidate carries its labels and assumptions; the iteration gate always refuses.

With the read-only originals present (the work archive and the 2026-10-29 delivery), the real plate data are checked
too; otherwise those tests are skipped.
"""

from __future__ import annotations

import math
from pathlib import Path
import sys
import tempfile
import threading
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modal_core import ModalDataset, ModeShape  # noqa: E402
from services import plate_study as ps  # noqa: E402

NAMES = ("D11", "D22", "D66")
NU12 = 0.05


def plate_frequency(m: int, n: int, d11: float, d22: float, d66: float, a: float = 0.3, b: float = 0.3) -> float:
    """Kirchhoff orthotropic plate, simply-supported-like trial function (an analytic test model only)."""
    d12 = NU12 * d22
    k = (d11 * (m / a) ** 4 + 2 * (d12 + 2 * d66) * (m / a) ** 2 * (n / b) ** 2 + d22 * (n / b) ** 4)
    return math.pi / 2 * math.sqrt(k / 1.31)


MODES = ((1, 1), (2, 1), (1, 2), (2, 2), (3, 1), (1, 3), (3, 2), (2, 3), (3, 3))


def plate_dataset(D11: float, D22: float, D66: float, name: str = "synthetic plate") -> ModalDataset:  # noqa: N803
    x, y = np.meshgrid(np.linspace(0, 0.3, 21), np.linspace(0, 0.3, 21))
    coordinates = np.column_stack([x.ravel(), y.ravel(), np.zeros(x.size)])
    nodes = np.array([f"PLATE-1:{k + 1}" for k in range(x.size)], dtype=object)
    modes = []
    for number, (m, n) in enumerate(MODES, start=1):
        w = np.sin(m * np.pi * coordinates[:, 0] / 0.3) * np.sin(n * np.pi * coordinates[:, 1] / 0.3)
        vectors = np.zeros((x.size, 3))
        vectors[:, 2] = w
        modes.append(ModeShape(number, plate_frequency(m, n, D11, D22, D66), nodes, coordinates, vectors))
    return ModalDataset(name, Path(name), modes, metadata={"mode_source": "curve-fitted dataset 55"})


BASE = {"D11": 2.9, "D22": 2.9, "D66": 0.26}


def family():
    return {"E1-": (plate_dataset(BASE["D11"] * 0.9, BASE["D22"], BASE["D66"]), "D11", 0.9),
            "E2-": (plate_dataset(BASE["D11"], BASE["D22"] * 0.9, BASE["D66"]), "D22", 0.9),
            "G+": (plate_dataset(BASE["D11"], BASE["D22"], BASE["D66"] * 2.0), "D66", 2.0)}


def surrogate(rows=None) -> ps.SurrogateForward:
    table = ps.sensitivity_table(plate_dataset(**BASE), family())
    rows = rows or [row.row_id for row in table.rows]
    ids, s = table.matrix(NAMES, rows)
    f0 = np.array([row.baseline_hz for row in table.rows if row.row_id in ids])
    return ps.SurrogateForward(ids, f0, NAMES, tuple(BASE[p] for p in NAMES), s)


TRUTH = {"D11": 3.1, "D22": 2.7, "D66": 0.31}
START = {"D11": 2.9, "D22": 2.9, "D66": 0.26}


class SensitivityTests(unittest.TestCase):
    def test_branch_sensitivities_follow_the_analytic_plate(self):
        table = ps.sensitivity_table(plate_dataset(**BASE), family())
        self.assertTrue(table.basis.startswith("SECANT"))
        for row in table.rows:
            m, n = MODES[row.baseline_mode - 1]
            for parameter, (key, ratio) in (("D11", ("E1-", 0.9)), ("D22", ("E2-", 0.9)), ("D66", ("G+", 2.0))):
                values = dict(BASE)
                values[parameter] *= ratio
                expected = math.log(plate_frequency(m, n, values["D11"], values["D22"], values["D66"])
                                    / plate_frequency(m, n, BASE["D11"], BASE["D22"], BASE["D66"])) / math.log(ratio)
                with self.subTest(row=row.row_id, parameter=parameter):
                    self.assertAlmostEqual(row.sensitivity[parameter], expected, places=10)
                    self.assertEqual(row.tracked[key][3], "TRACKED")

    def test_the_d_jacobian_is_exact_for_the_homogeneous_plate(self):
        params = {"E1": 56000.0, "E2": 50400.0, "nu12": 0.05}

        def ln_d(e1, e2):
            a = 0.05 ** 2 * e2 / e1
            return np.log([e1 / (1 - a), e2 / (1 - a)])

        h = 1e-6
        numeric = np.column_stack([(ln_d(56000.0 * math.exp(h), 50400.0) - ln_d(56000.0, 50400.0)) / h,
                                   (ln_d(56000.0, 50400.0 * math.exp(h)) - ln_d(56000.0, 50400.0)) / h])
        np.testing.assert_allclose(ps.d_jacobian(params)[:2, :2], numeric, atol=1e-5)  # rows D, columns E
        self.assertEqual(ps.d_jacobian(params)[2, 2], 1.0)


class TwinTests(unittest.TestCase):
    def test_known_parameters_are_recovered_at_sufficient_rank(self):
        forward = surrogate()
        rows = list(forward.rows)
        twin = ps.run_synthetic_twin(forward, TRUTH, rows[:-2], rows[-2:], START)
        self.assertIn(ps.SURROGATE, twin.labels)
        self.assertEqual(twin.lm_status, "CONVERGED")
        self.assertEqual(twin.analysis_status, "FULL_RANK")
        for p in NAMES:
            with self.subTest(parameter=p):
                self.assertLess(abs(twin.recovery_ln[p]), 3 * twin.sd_ln[NAMES.index(p)])
                self.assertIn(twin.verdicts[p], ("IDENTIFIED", "WIDE"))

    def test_insufficient_rank_is_refused(self):
        forward = surrogate(rows=["FE1"])  # one frequency, three parameters
        twin = ps.run_synthetic_twin(forward, TRUTH, ["FE1"], [], START)
        self.assertEqual(twin.analysis_status, "RANK_DEFICIENT")
        self.assertTrue(twin.lm_status.startswith("NOT_RUN"))  # no optimisation on a rank-deficient system
        self.assertEqual(set(twin.verdicts.values()), {"NOT_IDENTIFIABLE"})
        self.assertTrue(all("RANK_DEFICIENT" in " ".join(r) for r in twin.reasons.values()))

    def test_a_relabelled_close_pair_is_one_term(self):
        forward = surrogate()
        rows = list(forward.rows)
        pair = ("FE2", "FE3")  # (2,1) / (1,2): degenerate at D11 = D22, a close group
        fit = [r for r in rows if r not in ("FE8", "FE9")]
        clean = ps.run_synthetic_twin(forward, TRUTH, fit, ["FE8", "FE9"], START, clusters=[pair])
        swapped = ps.run_synthetic_twin(forward, TRUTH, fit, ["FE8", "FE9"], START, clusters=[pair],
                                        relabel=[pair])
        for p in NAMES:  # one cluster term: the relabelling changes nothing
            self.assertAlmostEqual(clean.estimate[p], swapped.estimate[p], places=12)
        singles = ps.run_synthetic_twin(forward, TRUTH, fit, ["FE8", "FE9"], START, relabel=[pair])
        bias = max(abs(singles.recovery_ln[p]) for p in ("D11", "D22"))
        self.assertGreater(bias, 5 * max(abs(clean.recovery_ln[p]) for p in ("D11", "D22")))

    def test_an_unverified_registration_refuses_every_verdict(self):
        forward = surrogate()
        rows = list(forward.rows)
        for state in ("NOT_AVAILABLE", "FAIL"):
            with self.subTest(registration=state):
                twin = ps.run_synthetic_twin(forward, TRUTH, rows[:-2], rows[-2:], START, registration=state)
                self.assertEqual(set(twin.verdicts.values()), {"NOT_IDENTIFIABLE"})
        readiness = ps.plate_readiness(registration_verified=False)
        self.assertEqual(readiness.status, ps.NOT_READY)
        self.assertTrue(any(ps.NOT_VERIFIED in line for line in readiness.missing))


class DesignTests(unittest.TestCase):
    def setUp(self):
        table = ps.sensitivity_table(plate_dataset(**BASE), family())
        ids, s = table.matrix(NAMES)
        self.sens = {row: dict(zip(NAMES, values)) for row, values in zip(ids, s)}
        self.rows = list(ids)

    def test_thickness_at_measured_mass_is_collinear_with_the_d_scale(self):
        thickness = ps.thickness_column(self.rows, self.sens, NAMES)
        for row in self.rows:
            self.assertAlmostEqual(thickness[row], 3 * sum(self.sens[row].values()), places=12)
            self.assertAlmostEqual(sum(self.sens[row].values()), 0.5, delta=0.03)  # f² ∝ D (secants ≈ 1/2)
        sens = {row: {**self.sens[row], "h": thickness[row]} for row in self.rows}
        study = ps.design_study(sens, self.rows, NAMES + ("h",), "with thickness")
        self.assertEqual(study.status, "RANK_DEFICIENT")
        self.assertIsNone(study.sd_ln)

    def test_one_frequency_cannot_give_two_parameters(self):
        study = ps.design_study(self.sens, ["FE1"], ("D11", "D66"), "one frequency")
        self.assertEqual(study.status, "RANK_DEFICIENT")
        self.assertIn(ps.HYPOTHETICAL_PAIRING, study.labels)
        outcome = ps.parameter_outcome("D66", reasons=study.refusal_reasons)
        self.assertEqual(outcome.outcome, ps.NOT_IDENTIFIABLE)

    def test_several_modes_give_full_rank(self):
        study = ps.design_study(self.sens, self.rows, NAMES, "all")
        self.assertEqual(study.status, "FULL_RANK")
        self.assertEqual(len(study.sd_ln), 3)


class ExperimentAndSourceTests(unittest.TestCase):
    def test_the_first_record_and_the_first_elastic_mode_are_kept(self):
        dataset = plate_dataset(**BASE)
        summary = ps.experimental_summary(dataset, "0" * 64)
        self.assertEqual([r.position for r in summary.records], list(range(1, len(MODES) + 1)))
        self.assertEqual(summary.records[0].mode, 1)
        self.assertEqual(summary.records[0].classification, "FITTED (dataset 55)")
        self.assertEqual([m.number for m in ps.elastic_modes(dataset)][0], 1)
        rigid = ModeShape(0, 0.01, dataset.modes[0].node_ids, dataset.modes[0].coordinates,
                          np.tile([0.0, 0.0, 1.0], (len(dataset.modes[0].node_ids), 1)))
        with_rigid = ModalDataset("with rigid", Path("x"), [rigid] + dataset.modes)
        self.assertEqual([m.number for m in ps.elastic_modes(with_rigid)][0], 1)  # rigid by shape only

    def test_shape_invariants_are_rotation_invariant(self):
        x, y = np.meshgrid(np.linspace(-1, 1, 17), np.linspace(-1, 1, 17))
        xy = np.column_stack([x.ravel(), y.ravel(), np.zeros(x.size)])
        twist = xy[:, 0] * xy[:, 1]
        angle = math.radians(45)
        rotated = xy @ np.array([[math.cos(angle), -math.sin(angle), 0], [math.sin(angle), math.cos(angle), 0],
                                 [0, 0, 1]])
        for coordinates in (xy, rotated):
            rigid, saddle, dome = ps.shape_invariants(coordinates, twist)
            self.assertGreater(saddle, 0.999)
            self.assertLess(rigid + dome, 1e-6)

    def test_m11_never_replaces_the_rotated_working_source(self):
        self.assertEqual(ps.classify_source(ps.WORKING_SOURCE_SHA256), ps.WORKING)
        self.assertEqual(ps.classify_source("117c893bafbb" + "0" * 52), ps.HISTORY)
        self.assertEqual(ps.classify_source(ps.AUXILIARY_FRF_SHA256), ps.AUXILIARY)
        for sha in ("117c893bafbb" + "0" * 52, ps.AUXILIARY_FRF_SHA256, "f" * 64):
            with self.subTest(sha=sha[:12]), self.assertRaises(ps.PlateStudyRefusal):
                ps.require_working_source(sha)
        self.assertEqual(ps.PLATE_IDENTITY, "NOT_ESTABLISHED")
        readiness = ps.plate_readiness(registration_verified=True, confirmed_pairs=("E1",))
        self.assertTrue(any("NOT attached" in line for line in readiness.missing))
        self.assertTrue(all(member.status == ps.CANDIDATE_FE_REFERENCE for member in ps.PLATE_FE_FAMILY))


class OutcomeAndGateTests(unittest.TestCase):
    def test_a_research_candidate_is_labelled_and_never_a_material_constant(self):
        candidate = ps.parameter_outcome("D66", research_estimate=0.3, assumptions=("hypothetical pairing",))
        self.assertEqual(candidate.outcome, ps.RESEARCH_CANDIDATE)
        self.assertIn(ps.NOT_A_MATERIAL_PROPERTY, candidate.labels)
        self.assertIn(ps.RESEARCH_ONLY, candidate.labels)
        with self.assertRaises(ps.PlateStudyRefusal):
            ps.parameter_outcome("D66", research_estimate=0.3)  # assumptions are mandatory
        self.assertEqual(ps.parameter_outcome("D66", production_verdict="IDENTIFIED").outcome, ps.IDENTIFIABLE)
        self.assertEqual(ps.parameter_outcome("D66", production_verdict="NOT_IDENTIFIABLE").outcome,
                         ps.NOT_IDENTIFIABLE)

    def test_the_readiness_of_the_plate_now(self):
        readiness = ps.plate_readiness(registration_verified=False)
        self.assertEqual(readiness.status, ps.NOT_READY)
        self.assertEqual({o.outcome for o in readiness.outcomes}, {ps.NOT_IDENTIFIABLE})
        separate = next(o for o in readiness.outcomes if o.parameter.startswith("D11, D22"))
        self.assertIn("SPEC v1.1 §5.2", separate.reasons[0])

    def test_the_iteration_gate_always_refuses(self):
        for authorisation in (None, object()):
            with self.subTest(authorisation=authorisation), self.assertRaises(ps.IterationNotAuthorised):
                ps.request_iteration(authorisation)
        self.assertEqual(ps.ITERATION_GATE.status, ps.ITERATION_NOT_AUTHORISED)

    def test_the_uncertainty_budget_keeps_the_sources_apart(self):
        lines = ps.uncertainty_budget(0.005, 0.03)
        thickness = next(line for line in lines if line.source.startswith("thickness"))
        self.assertAlmostEqual(thickness.ln_sd, 0.09)  # D ∝ h³: a 3 % thickness cv is 9 % in E
        self.assertIsNone(next(line for line in lines if line.source.startswith("mass")).ln_sd)


class FileTests(unittest.TestCase):
    def test_inp_and_dat_parsing(self):
        inp = ("*Shell Section, elset=Set-1, material=M\n0.875, 5\n*Material, name=M\n*Density\n 1.498e-09,\n"
               "*Elastic, type=ENGINEERING CONSTANTS\n56000.,56000., 8500.,  0.05,   0.3,   0.3, 5000., 3000.\n"
               " 3000.,\n")
        parsed = ps.parse_inp_material(inp)
        self.assertEqual((parsed["E1"], parsed["G12"], parsed["G23"], parsed["h"], parsed["rho"]),
                         (56000.0, 5000.0, 3000.0, 0.875, 1.498e-09))
        dat = ("   E I G E N V A L U E    O U T P U T\n\n MODE NO      EIGENVALUE   FREQUENCY  GEN\n"
               "  (RAD/TIME)   (CYCLES/TIME)\n\n       1*    -9.4E-05     0.0000         0.0000         1.0000\n"
               "       7     14360.       119.83         19.072         1.0000\n\n")
        self.assertEqual(ps.parse_dat_frequencies(dat), ((1, 0.0), (7, 19.072)))

    def test_member_files_are_verified_by_sha256(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            member = ps.PLATE_FE_FAMILY[0]
            states = {check.role: check.state for check in ps.verify_member(member, root)}
            self.assertEqual(set(states.values()), {"MISSING"})
            path = root.joinpath(*Path(member.inp.relative).parts)
            path.parent.mkdir(parents=True)
            path.write_text("not the input", encoding="utf-8")
            states = {check.role: check.state for check in ps.verify_member(member, root)}
            self.assertEqual(states["inp"], "CHANGED")


DELIVERY = Path(r"D:\Snadwich\New  EXP results")


@unittest.skipUnless(ps.WORK_ROOT.is_dir() and DELIVERY.is_dir(), "the read-only plate originals are not here")
class RealPlateTests(unittest.TestCase):
    def test_the_real_plate_study(self):
        from new_gui import preview_model as pm
        from new_gui import workspace_state as ws

        source = DELIVERY.joinpath(*Path(ps.WORKING_SOURCE.replace("\\", "/")).parts)
        read = pm.run_read(ws.EXPERIMENTAL, source, 1, threading.Event())
        ps.require_working_source(read.identity["sha256"])
        summary = ps.experimental_summary(read.preview.sets[0].dataset, read.identity["sha256"])
        self.assertEqual(len(summary.records), 11)
        self.assertAlmostEqual(summary.records[0].frequency_hz, 18.6307, places=3)
        self.assertEqual(summary.point_count, 289)
        self.assertAlmostEqual(summary.grid_axis_angle_deg, 45.0, delta=1.0)
        for member in ps.PLATE_FE_FAMILY:
            with self.subTest(member=member.member_id):
                self.assertEqual({c.state for c in ps.verify_member(member)}, {"VERIFIED"})


if __name__ == "__main__":
    unittest.main()
