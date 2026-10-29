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
- the M11 session never replaces the ROTATED working source as an experimental file;
- PLATE-ONLY-R2: the specimen identity is HUMAN_CONFIRMED (owner, 2026-10-30) with its provenance and limits; the
  archived M11 measurements are attached with their date, method and uncertainty (never as measurements of 27.10);
  the initial FE model's applicability to the 261027 test is checked apart and NOT_VERIFIED; frequency proximity
  (18.6307 / 19.07 Hz) never makes a pair; the orientation candidates stay open;
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
        # PLATE-ONLY-R2: the specimen is the same, but the M11 session stays history as an experimental file
        self.assertEqual(ps.PLATE_IDENTITY, ps.HUMAN_CONFIRMED)
        self.assertEqual(ps.classify_source("117c893bafbb" + "0" * 52), ps.HISTORY)


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


class SpecimenR2Tests(unittest.TestCase):
    """PLATE-ONLY-R2: the owner's confirmation of the specimen identity (2026-10-30) and what follows from it."""

    def test_the_identity_is_human_confirmed_with_its_provenance_and_limits(self):
        record = ps.IDENTITY_RECORD
        self.assertEqual((ps.PLATE_IDENTITY, record["status"], record["by"], record["date"]),
                         (ps.HUMAN_CONFIRMED, ps.HUMAN_CONFIRMED, "owner", "2026-10-30"))
        self.assertIn("261016", record["statement"])
        self.assertIn("261027", record["statement"])
        self.assertFalse(record["governed_evidence"])
        limits = " ".join(record["does_not_establish"])
        for item in ("mode pair", "registration", "applicability", "unchanged"):
            self.assertIn(item, limits)
        self.assertTrue(ps.IDENTITY_EVIDENCE[0][2].startswith(ps.HUMAN_CONFIRMED))
        # the identity is final: nothing asks for it again
        self.assertFalse(hasattr(ps, "IDENTITY_NEEDED"))
        readiness = ps.plate_readiness(registration_verified=False)
        self.assertFalse(any("identity" in line for line in readiness.missing))
        self.assertFalse(any("identity with the M11" in line or "statement" in line for line in ps.ITERATION_PLAN))
        self.assertTrue(any("identity of the plate" in line for line in ps.plate_readiness(
            False, plate_identity="NOT_ESTABLISHED").missing))

    def test_the_archived_measurements_keep_their_date_method_and_uncertainty(self):
        by = {m.quantity: m for m in ps.SPECIMEN_RECORD}
        self.assertEqual(set(by), {"mass", "plan", "thickness", "areal mass"})
        for quantity in ("mass", "plan", "thickness"):
            with self.subTest(quantity=quantity):
                self.assertIn("2026-10-21", by[quantity].recorded)
                self.assertIn("before the 261027 session", by[quantity].recorded)
                self.assertEqual(by[quantity].status, ps.ARCHIVED)
                self.assertIn("not stated", by[quantity].uncertainty)
        for item in ps.SPECIMEN_RECORD:
            self.assertNotIn("27.10", item.recorded)  # never a measurement of the 27.10 session
        self.assertIn("NOT new measurements of 27.10.2026", ps.SPECIMEN_RECORD_NOTE)
        self.assertEqual(by["mass"].value, "118.37 g")
        self.assertIn("0.01 mm", by["thickness"].method)
        self.assertIn("interior is NOT measured", by["thickness"].method)
        stats = ps.thickness_statistics()
        self.assertEqual(stats["n"], 20)
        self.assertAlmostEqual(stats["mean"], 0.876, places=6)
        self.assertAlmostEqual(stats["cv"], 0.0815, delta=5e-4)
        self.assertAlmostEqual(stats["side_means"][2], 0.816, places=6)
        self.assertAlmostEqual(stats["side_means"][4], 0.926, places=6)
        self.assertAlmostEqual(ps.areal_mass_kg_m2(), 1.31085, delta=5e-5)

    def test_the_initial_fe_model_is_checked_apart_for_the_new_test(self):
        self.assertTrue(all(member.status == ps.INITIAL_FE_MODEL for member in ps.PLATE_FE_FAMILY))
        base = ps.PLATE_FE_FAMILY[0]
        checks = {c.aspect: c for c in ps.fe_applicability(base, (301.0, 300.0), 18.6307, 19.072)}
        self.assertEqual(checks["plan"].state, ps.CONSISTENT)
        self.assertEqual(checks["mass"].state, ps.CONSISTENT)  # 118.36 g against 118.37 g (the record's last digit)
        for aspect in ("thickness", "material axes", "suspension"):
            self.assertEqual(checks[aspect].state, "NOT_VERIFIED", aspect)
        self.assertEqual(checks["excitation"].state, "UNKNOWN")
        self.assertEqual(checks["registration"].state, ps.NOT_VERIFIED)
        self.assertIn("0.67 of record 1", checks["suspension"].note)
        self.assertEqual(checks["series difference: mode identity"].state, "MODE_IDENTITY_NOT_VERIFIED")
        self.assertEqual(checks["series difference: cause"].state, "SETUP_DEPENDENCE_SUSPECTED")
        self.assertIn("Not a Σ_setup repeat", checks["series difference: cause"].note)
        e30 = next(m for m in ps.PLATE_FE_FAMILY if m.member_id == "E30E26")
        self.assertEqual({c.aspect: c.state for c in ps.fe_applicability(e30, (301.0, 300.0))}["mass"], "DIFFERS")
        other = {c.aspect: c.state for c in ps.fe_applicability(base, (0.3, 0.3))}
        self.assertEqual((other["plan"], other["mass"]), ("DIFFERS", "DIFFERS"))
        self.assertEqual({c.aspect: c.state for c in ps.fe_applicability(base)}["plan"], "UNKNOWN")
        readiness = ps.plate_readiness(registration_verified=False)
        self.assertTrue(any(line.startswith(ps.APPLICABILITY_NOT_VERIFIED) for line in readiness.missing))
        verified = ps.plate_readiness(registration_verified=False, fe_applicability_verified=True)
        self.assertFalse(any(line.startswith(ps.APPLICABILITY_NOT_VERIFIED) for line in verified.missing))

    def test_the_proximity_of_18_63_and_19_07_hz_never_makes_a_mode_pair(self):
        checks = {c.aspect: c for c in ps.fe_applicability(ps.PLATE_FE_FAMILY[0], (301.0, 300.0), 18.6307, 19.072)}
        correspondence = checks["mode correspondence"]
        self.assertEqual(correspondence.state, "NOT_ESTABLISHED")
        self.assertIn("NOT a mode pair", correspondence.note)
        self.assertIn("+2.4 %", correspondence.note)
        readiness = ps.plate_readiness(registration_verified=False)
        self.assertEqual(readiness.confirmed_pairs, ())
        self.assertTrue(any("18.6307 Hz and 19.07 Hz confirms none" in line for line in readiness.missing))
        self.assertEqual({o.outcome for o in readiness.outcomes}, {ps.NOT_IDENTIFIABLE})

    def test_e_and_g_need_the_interior_thickness_while_d_needs_the_areal_mass_only(self):
        outcomes = {o.parameter: o for o in ps.plate_readiness(registration_verified=False).outcomes}
        moduli = outcomes["E1_eff, E2_eff, G12_eff"].reasons[0]
        self.assertIn("known only at the edges", moduli)
        self.assertIn("24 % is illustrative only", moduli)
        self.assertIn("real uncertainty of E / G is UNKNOWN", moduli)
        self.assertNotIn("known only at the edges", " ".join(outcomes["D66"].reasons))
        measured = {o.parameter: o for o in ps.plate_readiness(False, interior_thickness_measured=True).outcomes}
        self.assertNotIn("known only at the edges", measured["E1_eff, E2_eff, G12_eff"].reasons[0])
        budget = {line.source.split(" ")[0]: line for line in ps.specimen_budget()}
        self.assertIsNone(budget["thickness"].ln_sd)  # R2-F1: never an established contribution
        self.assertAlmostEqual(budget["thickness"].illustrative_ln_sd, 3 * ps.thickness_statistics()["cv"], places=12)
        self.assertIsNone(budget["mass"].ln_sd)  # the scale uncertainty is not stated: never invented (D-052)
        self.assertIn("needs no thickness", budget["mass"].note)
        self.assertIsNone(ps.plate_d(ps.PLATE_FE_FAMILY[5].parameters))  # the wedge: no uniform thickness
        for member in ps.PLATE_FE_FAMILY[:5]:
            with self.subTest(member=member.member_id):
                d = ps.plate_d(member.parameters)
                e = ps.effective_moduli_from_d(d["D11"], d["D22"], d["D66"], member.parameters["h"],
                                               member.parameters["nu12"])
                for name in ("E1", "E2", "G12"):
                    self.assertAlmostEqual(e[name] / member.parameters[name], 1.0, places=12)

    def test_the_grid_saddle_split_relates_a_shape_to_its_own_grid_only(self):
        u, v = np.meshgrid(np.linspace(-1, 1, 17), np.linspace(-1, 1, 17))
        twist = (u * v).ravel()
        angle = math.radians(45)
        grid = np.column_stack([u.ravel(), v.ravel()]) @ np.array([[math.cos(angle), math.sin(angle)],
                                                                   [-math.sin(angle), math.cos(angle)]])
        coordinates = np.column_stack([grid, np.zeros(len(grid))])
        on_axes, on_diagonals = ps.grid_saddle_split(coordinates, twist, 45.0)
        self.assertGreater(on_axes, 0.999)
        self.assertLess(on_diagonals, 1e-6)
        swapped = ps.grid_saddle_split(coordinates, twist, 0.0)  # the same shape in the camera axes
        self.assertGreater(swapped[1], 0.999)
        self.assertAlmostEqual(sum(swapped), ps.shape_invariants(coordinates, twist)[1], places=9)
        record = ps.experimental_summary(plate_dataset(**BASE), "0" * 64).records[0]
        self.assertIsNotNone(record.saddle_on_grid_axes)
        self.assertAlmostEqual(record.saddle_on_grid_axes + record.saddle_on_grid_diagonals, record.saddle_fraction,
                               places=9)

    def test_the_orientation_chain_keeps_every_candidate_open(self):
        states = [link.state for link in ps.ORIENTATION_CHAIN]
        self.assertEqual(states[0], ps.NOT_VERIFIED)
        self.assertTrue(states[1].startswith("PENDING"))
        self.assertEqual(states[2], "HISTORY_ONLY")
        notes = " ".join(ps.ORIENTATION_NOTES)
        self.assertIn("No orientation is chosen by MAC, frequency or shape", notes)
        self.assertIn("none is chosen", notes)
        self.assertIn("edge 2", notes)
        self.assertIn("NOT a mode pair", ps.fe_applicability(ps.PLATE_FE_FAMILY[0], None, 18.6307, 19.072)[-1].note)

    def test_the_ambiguous_thickness_reading_is_shown_and_never_resolved(self):
        # PLATE-ONLY-R2-F1: M11 §8 reads 0.84 or 0.81; the record keeps the transcription and shows both
        self.assertEqual(ps.THICKNESS_READINGS_MM[2], (0.79, 0.82, 0.84, 0.81, 0.82))  # the 20 readings, unchanged
        self.assertEqual(sum(len(row) for row in ps.THICKNESS_READINGS_MM.values()), 20)
        item = ps.THICKNESS_READING_AMBIGUITY
        self.assertEqual((item["edge"], item["reading"], item["transcribed_mm"], item["alternative_mm"]),
                         (2, 3, 0.84, 0.81))
        self.assertIn("not an independent re-measurement", item["owner_reading"])
        self.assertIn("not resolved", item["kept"])
        variants = ps.thickness_variants()
        self.assertAlmostEqual(variants["as transcribed"]["mean"], 0.876, places=6)
        self.assertAlmostEqual(variants["alternative reading"]["mean"], 0.8745, places=6)
        self.assertEqual(variants["as transcribed"], ps.thickness_statistics())
        thickness = next(m for m in ps.SPECIMEN_RECORD if m.quantity == "thickness")
        self.assertIn("0.84 as transcribed, could be read 0.81", thickness.value)
        rows = {r[0]: r for r in ps.thickness_rows()}
        self.assertTrue(rows["ambiguous reading"][2].startswith("AMBIGUOUS"))

    def test_the_illustrative_thickness_figure_is_never_the_real_uncertainty(self):
        rows = {r[0]: r for r in ps.thickness_rows()}
        self.assertIn("8.2 % / 8.3 %", rows["observed edge scatter"][1])
        self.assertIn("24.5 % / 24.9 %", rows["3 × CV_edges"][1])
        self.assertTrue(rows["3 × CV_edges"][2].startswith("ILLUSTRATIVE"))
        self.assertEqual(rows["thickness map of the whole plate"][2], "NOT_MEASURED")
        self.assertEqual(rows["real uncertainty of E / G"][1:], ("unknown", "UNKNOWN"))
        self.assertEqual(rows["±10 % target"][2], "NOT_ACHIEVED")
        thickness = next(line for line in ps.specimen_budget() if line.source.startswith("thickness"))
        self.assertIsNone(thickness.ln_sd)
        self.assertTrue(thickness.note.startswith("UNKNOWN: no thickness map of the whole plate"))
        self.assertIn("ILLUSTRATIVE, not the real uncertainty", thickness.note)

    def test_the_difference_of_the_two_series_is_a_suspicion_not_a_result(self):
        # PLATE-ONLY-R2-F1: the measured values stay; no established setup effect, no cross-series pair, no Σ_setup
        checks = {c.aspect: c for c in ps.fe_applicability(ps.PLATE_FE_FAMILY[0], (301.0, 300.0), 18.6307, 19.072)}
        identity, cause = checks["series difference: mode identity"], checks["series difference: cause"]
        self.assertEqual((identity.state, cause.state), (ps.MODE_IDENTITY_NOT_VERIFIED, ps.SETUP_DEPENDENCE_SUSPECTED))
        self.assertEqual(ps.SESSION_DIFFERENCE, "SETUP_DEPENDENCE_SUSPECTED / MODE_IDENTITY_NOT_VERIFIED")
        for text in ("18.6307 Hz in 261027", "33.4491 Hz in 261016", "uv fraction 0.988 and 0.947",
                     "same mode is NOT verified", "No cross-series mode pair"):
            self.assertIn(text, identity.note)
        for text in ("cause of the difference is NOT established", "suspected, not proven",
                     "Not a Σ_setup repeat (D-053)"):
            self.assertIn(text, cause.note)
        everything = " ".join(f"{c.aspect} {c.state} {c.note}" for c in checks.values())
        for forbidden in ("SETUP_SENSITIVE", "the setup changed", "setup-sensitive"):
            self.assertNotIn(forbidden, everything)
        self.assertEqual(ps.SESSION_TWIST, {"261027": (18.6307, 0.988), "261016": (33.4491, 0.947)})  # kept
        self.assertEqual(ps.plate_readiness(registration_verified=False).confirmed_pairs, ())


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

    def test_record_1_of_both_sessions_of_the_same_specimen(self):
        # PLATE-ONLY-R2 research, reproduced: the twist class about each scan grid (descriptive; not a pair)
        from new_gui import preview_model as pm
        from new_gui import workspace_state as ws

        m11 = (ps.WORK_ROOT / "external_models/v3_20261021/Plate/snadwich_Plate"
               / "300by300_plate_only_1mm_261016_POLYMAX.unv")
        if not m11.is_file():
            self.skipTest("the verified M11 copy is not here")
        for key, path in (("261027", DELIVERY.joinpath(*Path(ps.WORKING_SOURCE.replace("\\", "/")).parts)),
                          ("261016", m11)):
            with self.subTest(session=key):
                read = pm.run_read(ws.EXPERIMENTAL, path, 1, threading.Event())
                first = ps.experimental_summary(read.preview.sets[0].dataset, read.identity["sha256"]).records[0]
                hz, uv = ps.SESSION_TWIST[key]
                self.assertAlmostEqual(first.frequency_hz, hz, places=3)
                self.assertAlmostEqual(first.saddle_on_grid_axes, uv, delta=1e-3)
        manifest = ps.WORK_ROOT.joinpath(*Path(ps.PLATE_FE_FAMILY[0].manifest.relative).parts)
        fe = pm.read_preview(ws.FE, manifest, threading.Event()).dataset
        checks = {c.aspect: c.state for c in ps.fe_applicability(ps.PLATE_FE_FAMILY[0], ps.fe_plan(fe))}
        self.assertEqual((checks["plan"], checks["mass"]), (ps.CONSISTENT, ps.CONSISTENT))


if __name__ == "__main__":
    unittest.main()
