"""NINE-EC Phases D–H: sensitivities, identifiability, research estimation, FE cost plan and report (no Abaqus).

The synthetic forward model is an independent Rayleigh–Ritz orthotropic block (services.orthotropic_block_model);
synthetic experiments are generated from declared true constants and must be recovered, or refused, through the
general engine. SYNTHETIC / TEST EVIDENCE: nothing here says anything about real SP-13 identifiability except the
factual two-row reference (F2), which needs no FE evaluation at all.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.forward_model_manifest import EngineeringConstants  # noqa: E402
from domain.orthotropic_elasticity import NAMES, ElasticAdmissibilityError, admissibility  # noqa: E402
from services.branch_tracker import FEModalState  # noqa: E402
from services.nine_constants_engine import (  # noqa: E402
    ConstantStatus,
    EvaluationCounter,
    ObservationRow,
    Role,
    SensitivityDesign,
    assess_identifiability,
    central_sensitivities,
    estimate_constants,
    plan_fe_evaluations,
    SP13_MEASURED_PROFILE,
)
from services.nine_constants_offline import START, TRUTH, synthetic_demo  # noqa: E402
from services.nine_constants_report import build_report, report_csv, report_text, write_report  # noqa: E402
from services.nine_constants_synthetic import separated_modes, synthetic_experiment  # noqa: E402
from services.orthotropic_block_model import BlockForwardModel, OrthotropicBlock  # noqa: E402

THICK = (13.0, 6.3, 4.4)


def thick(mode_count: int = 48) -> BlockForwardModel:
    return BlockForwardModel(OrthotropicBlock(THICK, 1.55e-9, order=10), mode_count)


def error(name: str, estimate: float, truth: float) -> float:
    return math.log(estimate / truth) if name[0] in "EG" else estimate - truth


class SyntheticModelTests(unittest.TestCase):
    def test_physics_checks_of_the_independent_model(self):
        block = OrthotropicBlock(THICK, 1.55e-9, order=10)
        solution = block.modes(TRUTH, 12)
        finer = OrthotropicBlock(THICK, 1.55e-9, order=12).modes(TRUTH, 12)
        self.assertLess(np.max(np.abs(np.array(finer.frequencies_hz) / solution.frequencies_hz - 1)), 2e-3)  # converged
        analytic = block.analytic_log_sensitivities(solution)
        moduli = [NAMES.index(n) for n in ("E1", "E2", "E3", "G12", "G13", "G23")]
        # homogeneity: scaling every modulus by λ scales every frequency by √λ
        self.assertTrue(np.allclose(analytic[:, moduli].sum(axis=1), 0.5, atol=1e-9))
        forward = BlockForwardModel(block, 12)
        rows = [ObservationRow(f"X{m}", 1.0, m, f"F{m}", Role.FIT, 0.001) for m in range(1, 9)]
        fine = SensitivityDesign(ln_step=0.01, poisson_step=0.005, noise_check=False)
        numeric = central_sensitivities(EvaluationCounter(forward, 100), TRUTH, rows, NAMES, fine)
        fd = np.array([[numeric.values[f"X{m}"][n] for n in NAMES] for m in range(1, 9)])
        self.assertLess(np.max(np.abs(fd - analytic[:8])), 1e-3)  # tracked central differences match eigen-derivatives
        coarse = central_sensitivities(EvaluationCounter(forward, 100), TRUTH, rows, NAMES, SensitivityDesign())
        self.assertEqual(set(coarse.column_status.values()), {"EVALUATED"})  # SPEC half-step noise check passes


class FullObservabilityTests(unittest.TestCase):
    """F1: a deliberately well-conditioned synthetic dataset (thick block, 27 FIT families, sd 0.03 %)."""

    @classmethod
    def setUpClass(cls):
        cls.forward = thick()
        modes = separated_modes(cls.forward, [TRUTH, START], 30)
        cls.experiment = synthetic_experiment(cls.forward, TRUTH, START, modes, 3, sd_ln=0.0003,
                                              noise_sd_ln=0.00015, seed=7)
        cls.result = estimate_constants(cls.forward, START, cls.experiment.rows, NAMES, (), evaluation_limit=200,
                                        poisson_sd_limit=0.05)

    def test_all_nine_recovered_with_status_and_uncertainty(self):
        result = self.result
        self.assertEqual(result.status, "ESTIMATED_RESEARCH", result.reasons)
        gate = result.gate
        self.assertEqual((gate.rank_status, gate.rank, gate.parameters_in_system), ("FULL_RANK", 9, NAMES))
        self.assertEqual((gate.fit_terms, gate.fit_families), (27, 27))
        self.assertTrue(gate.minimum_observability_met)
        for name in NAMES:
            item = result.final_assessment.constants[name]
            self.assertIs(item.status, ConstantStatus.SUPPORTED_RESEARCH_ESTIMATE)
            self.assertLessEqual(abs(error(name, item.estimate, getattr(TRUTH, name))), 3.0 * item.sd, name)
        units = {n: result.final_assessment.constants[n].coordinate for n in NAMES}
        self.assertEqual(units["nu13"], "ν (dimensionless, absolute)")
        self.assertEqual(units["G23"], "ln p")
        holdouts = [r for r in result.residuals if r["role"] == "HOLDOUT"]
        self.assertEqual(len(holdouts), 3)
        self.assertTrue(all(abs(r["residual_ln"]) <= 3 * 0.0003 for r in holdouts))
        self.assertLessEqual(result.evaluations, 200)

    def test_report_shows_nine_research_estimates_with_labels(self):
        report = build_report(question="test", inputs={}, model={"constants": START.to_dict()}, experiment=None,
                              registration=None, observations=self.experiment.rows, assessment=None,
                              estimation=self.result, fe_plan=None, fe_provenance=None,
                              effective_model_reference=None, refusals=[])
        self.assertEqual([r["constant"] for r in report["constants"]], list(NAMES))
        self.assertTrue(all(r["estimated_value_class"] == "EVIDENCE_SUPPORTED_RESEARCH_ESTIMATE"
                            for r in report["constants"]))
        self.assertEqual(report["claim"], ["RESEARCH_DIAGNOSTIC_ONLY", "NOT_A_VALIDATED_MATERIAL_PROPERTY"])
        self.assertIn("NOT_EVALUATED", report["constants"][0]["governed_material_property"])
        self.assertTrue(all(r["input_value"] == getattr(START, r["constant"]) for r in report["constants"]))


class RefusalTests(unittest.TestCase):
    def test_partially_identifiable_question_is_refused_before_optimisation(self):
        forward = thick()
        modes = separated_modes(forward, [TRUTH, START], 30)
        experiment = synthetic_experiment(forward, TRUTH, START, modes, 3, sd_ln=0.001, seed=7)
        result = estimate_constants(forward, START, experiment.rows, NAMES, (), 200, poisson_sd_limit=0.05)
        self.assertEqual(result.status, "REFUSED_BEFORE_OPTIMISATION")
        self.assertEqual(result.evaluations, 1 + 18 + 18)  # the gate only: no optimiser evaluation
        blocked = [n for n, a in result.gate.constants.items() if a.status is not ConstantStatus.SUPPORTED_RESEARCH_ESTIMATE]
        self.assertIn("nu13", blocked)
        report = build_report(question="t", inputs={}, model={"constants": START.to_dict()}, experiment=None,
                              registration=None, observations=experiment.rows, assessment=None, estimation=result,
                              fe_plan=None, fe_provenance=None, effective_model_reference=None, refusals=[])
        self.assertTrue(all(r["estimated_value"] is None for r in report["constants"]))  # no partial optimisation
        self.assertNotIn("SUPPORTED_RESEARCH_ESTIMATE", {r["status"] for r in report["constants"]})

    def test_two_observations_cannot_determine_nine_constants(self):  # F2
        report = synthetic_demo("two_rows")
        self.assertEqual(report["identifiability"]["rank_status"], "RANK_DEFICIENT")
        self.assertLessEqual(report["identifiability"]["rank"], 2)
        self.assertEqual({r["status"] for r in report["constants"]}, {"NOT_IDENTIFIABLE"})
        self.assertTrue(all(r["estimated_value"] is None for r in report["constants"]))
        self.assertEqual(len(report["identifiability"]["supported_combinations"]), 2)  # diagnostic directions only
        self.assertTrue(report["headline"].startswith("No constant can be determined"))

    def test_accepted_sp13_two_rows_are_a_factual_rank_bound(self):  # F2, factual reference, no FE evaluation
        rows = [ObservationRow("X4", 94.3990939312666, 10, "Px:O|Py:E|nx:1|ny:2"),
                ObservationRow("X7", 205.64887661733076, 13, "Px:E|Py:O|nx:0|ny:3")]
        sp13 = EngineeringConstants(52000, 52000, 6700, 0.05, 0.3, 0.3, 4500, 2200, 2200)
        assessment = assess_identifiability(sp13, rows, None, NAMES)
        self.assertEqual({a.status for a in assessment.constants.values()}, {ConstantStatus.NOT_IDENTIFIABLE})
        self.assertIn("rank ≤ 2", assessment.refusal_reasons[0])
        self.assertFalse(assessment.minimum_observability_met)

    def test_nearly_dependent_columns_are_confounded(self):  # F3
        rng = np.random.default_rng(3)
        base = rng.normal(0.0, 0.2, size=(14, 9))
        families = [ObservationRow(f"R{i}", 100.0 + i, i + 1, f"F{i}", Role.FIT, 0.003) for i in range(13)]
        rows = families + [ObservationRow("H", 300.0, 14, "FH", Role.HOLDOUT, 0.003)]
        e3, g13 = NAMES.index("E3"), NAMES.index("G13")
        exact = base.copy()
        exact[:, g13] = exact[:, e3] * 1.0000001  # dependent: rank deficiency
        a = assess_identifiability(START, rows, {r.row_id: dict(zip(NAMES, exact[i])) for i, r in enumerate(families)},
                                   NAMES)
        self.assertEqual(a.rank_status, "RANK_DEFICIENT")
        self.assertGreater(a.constants["E3"].null_space_weight, 0.5)
        self.assertGreater(a.constants["G13"].null_space_weight, 0.5)
        self.assertLess(a.constants["E1"].null_space_weight, 1e-6)
        near = base.copy()
        near[:, g13] = near[:, e3] + rng.normal(0.0, 5e-3, size=14)  # cosine ≈ 0.999: full rank but confounded
        b = assess_identifiability(START, rows, {r.row_id: dict(zip(NAMES, near[i])) for i, r in enumerate(families)},
                                   NAMES, poisson_sd_limit=0.05)
        self.assertEqual(b.rank_status, "FULL_RANK")
        for name in ("E3", "G13"):
            self.assertIs(b.constants[name].status, ConstantStatus.NOT_IDENTIFIABLE)
            self.assertLess(b.constants[name].q, 0.05)  # information absorbed by the other column
        correlation = np.array(b.analysis["correlation"]).reshape(9, 9)  # the M5 record stores it flattened
        self.assertLess(correlation[e3, g13], -0.99)
        self.assertIs(b.constants["E1"].status, ConstantStatus.SUPPORTED_RESEARCH_ESTIMATE)

    def test_zero_and_weak_sensitivity(self):  # F4
        rng = np.random.default_rng(5)
        matrix = rng.normal(0.0, 0.2, size=(13, 9))
        matrix[:, NAMES.index("nu23")] = 0.0
        rows = [ObservationRow(f"R{i}", 100.0 + i, i + 1, f"F{i}", Role.FIT, 0.003) for i in range(13)]
        a = assess_identifiability(START, rows, {r.row_id: dict(zip(NAMES, matrix[i])) for i, r in enumerate(rows)},
                                   NAMES)
        self.assertEqual(a.rank_status, "RANK_DEFICIENT")
        self.assertAlmostEqual(a.constants["nu23"].null_space_weight, 1.0, places=6)
        report = synthetic_demo("thin_plate")  # model level: a thin plate barely feels E3, ν13, ν23
        weights = {r["constant"]: r["null_space_weight"] for r in report["constants"]}
        self.assertEqual(report["identifiability"]["rank_status"], "RANK_DEFICIENT")
        self.assertGreater(weights["E3"], 0.9)
        self.assertGreater(weights["nu13"], 0.9)
        self.assertLess(weights["E1"], 0.01)

    def test_declared_fixed_constants_are_never_estimated(self):
        report = synthetic_demo("thin_plate_reduced")
        rows = {r["constant"]: r for r in report["constants"]}
        for name in ("E3", "nu13", "nu23"):
            self.assertEqual(rows[name]["status"], "FIXED_INPUT_NOT_IDENTIFIED")
            self.assertEqual(rows[name]["input_value_class"], "ASSUMED_FIXED")
            self.assertIsNone(rows[name]["estimated_value"])
        self.assertEqual(rows["G23"]["status"], "NOT_IDENTIFIABLE")  # sd > 8 % in ln p (SPEC §10)
        self.assertEqual(rows["E1"]["status"], "NOT_EVALUATED")  # identifiable alone, but the question was refused
        self.assertIn("narrower question", rows["E1"]["reasons"][-1])

    def test_inadmissible_states_never_reach_the_forward_model(self):  # F5
        forward = thick(12)
        counter = EvaluationCounter(forward, 10)
        with self.assertRaises(ElasticAdmissibilityError):
            counter.evaluate(EngineeringConstants(**dict(START.to_dict(), nu12=5.0)))
        self.assertEqual((forward.evaluations, counter.count), (0, 0))
        low, high = START.nu12, 5.0  # bisect the admissibility boundary in ν12 (other constants fixed)
        for _ in range(60):
            middle = 0.5 * (low + high)
            if admissibility(EngineeringConstants(**dict(START.to_dict(), nu12=middle))).admissible:
                low = middle
            else:
                high = middle
        edge = EngineeringConstants(**dict(START.to_dict(), nu12=low - 0.01))  # admissible; +0.02 is not
        rows = [ObservationRow(f"X{m}", 1.0, m, f"F{m}", Role.FIT, 0.001) for m in range(1, 6)]
        result = central_sensitivities(EvaluationCounter(forward, 50), edge, rows, ("E1", "nu12"))
        self.assertEqual(result.column_status["nu12"], "NOT_EVALUATED")  # ν12 + step is not admissible
        self.assertIn("not admissible", result.column_reasons["nu12"])
        with self.assertRaises(ElasticAdmissibilityError):
            estimate_constants(forward, EngineeringConstants(**dict(START.to_dict(), G12=-1.0)), rows, NAMES, (), 10)

    def test_branch_loss_is_a_refusal_never_a_re_pairing(self):  # F6
        class Mixing:
            """Rotates modes 1 and 2 by 45° in every state except the start state (identity loss)."""

            def __init__(self, inner):
                self.inner = inner

            def identity(self):
                return {"kind": "mixing test double"}

            def evaluate(self, constants):
                state = self.inner.evaluate(constants)
                if constants == START:
                    return state
                shapes = np.array(state.shapes)
                a, b = shapes[0].copy(), shapes[1].copy()
                shapes[0], shapes[1] = (a + b) / math.sqrt(2), (a - b) / math.sqrt(2)
                return FEModalState(state.state_id, state.fe_geometry_sha256, state.node_set_sha256,
                                    state.mode_numbers, state.frequencies_hz, shapes)

        forward = Mixing(thick(20))
        rows = [ObservationRow(f"X{m}", 1.0, m, f"F{m}", Role.FIT, 0.001) for m in range(1, 13)]
        result = central_sensitivities(EvaluationCounter(forward, 100), START, rows, ("E1", "G12"))
        for name in ("E1", "G12"):
            self.assertEqual(result.column_status[name], "NOT_EVALUATED")
            self.assertIn("BRANCH_LOSS", result.column_reasons[name])
        a = assess_identifiability(START, rows, result.values, ("E1", "G12"),
                                   tuple(n for n in NAMES if n not in ("E1", "G12")), result.column_status,
                                   result.column_reasons)
        self.assertEqual({a.constants[n].status for n in ("E1", "G12")}, {ConstantStatus.NOT_EVALUATED})

    def test_element_formulation_blocks_unused_constants(self):
        rows = [ObservationRow(f"R{i}", 100.0 + i, i + 1, f"F{i}", Role.FIT, 0.003) for i in range(3)]
        use = {n: ("NOT_USED_BY_ELEMENT_FORMULATION" if n in ("E3", "nu13", "nu23") else "USED") for n in NAMES}
        a = assess_identifiability(START, rows, None, NAMES, formulation_use=use)
        self.assertIn("element formulation", a.constants["E3"].reasons[0])
        self.assertIs(a.constants["E3"].status, ConstantStatus.NOT_IDENTIFIABLE)


class RepeatabilityAndPlanTests(unittest.TestCase):
    def test_identical_evidence_gives_identical_records(self):  # F8
        first, second = synthetic_demo("two_rows"), synthetic_demo("two_rows")
        self.assertEqual(first["report_hash"], second["report_hash"])
        self.assertEqual(first["identifiability"]["analysis"]["system_hash"],
                         second["identifiability"]["analysis"]["system_hash"])
        self.assertNotEqual(EvaluationCounter.key(START), EvaluationCounter.key(TRUTH))

    def test_fe_cost_plan_counts_and_never_promises_unverified_reuse(self):
        plan = plan_fe_evaluations(9, potentially_reusable=12, authorised_limit=8, profile=SP13_MEASURED_PROFILE)
        self.assertEqual(plan.required_new_minimum, 1 + 18 + 18)  # baseline + central differences + noise repeat
        self.assertEqual(plan.required_new_typical, (37 + 2 + 36, 37 + 15 + 36))
        self.assertFalse(plan.within_authorised_limit)  # the GUI default of 8 cannot hold a nine-constant campaign
        self.assertEqual(plan.potentially_reusable, 12)  # recorded, never subtracted
        self.assertIn("ESTIMATE", plan.resources["statement"])
        self.assertIn("MEASURED", plan.resources["basis"])
        cached = plan_fe_evaluations(9, verified_cached=("baseline",))
        self.assertEqual(cached.required_new_minimum, 36)
        self.assertEqual(plan_fe_evaluations(2, noise_check=False).required_new_minimum, 1 + 4)


class ReportContractTests(unittest.TestCase):
    def test_a_completed_narrow_question_never_reports_fixed_inputs_as_estimates(self):
        from services.nine_constants_synthetic import perturbed_states

        forward = BlockForwardModel(OrthotropicBlock((40.0, 27.0, 0.8), 1.55e-9, order=10), 40)
        modes = separated_modes(forward, perturbed_states(START), 20)
        experiment = synthetic_experiment(forward, START, START, modes, 2, sd_ln=0.003, seed=1)
        estimated = ("E1", "E2", "G12")
        fixed = tuple(n for n in NAMES if n not in estimated)
        result = estimate_constants(forward, START, experiment.rows, estimated, fixed, 100)
        self.assertEqual(result.status, "ESTIMATED_RESEARCH", result.reasons)
        report = build_report(question="t", inputs={}, model={"constants": START.to_dict()}, experiment=None,
                              registration=None, observations=experiment.rows, assessment=None, estimation=result,
                              fe_plan=None, fe_provenance=None, effective_model_reference=None, refusals=[])
        rows = {r["constant"]: r for r in report["constants"]}
        for name in estimated:
            self.assertEqual(rows[name]["estimated_value_class"], "EVIDENCE_SUPPORTED_RESEARCH_ESTIMATE")
        for name in fixed:
            self.assertEqual(rows[name]["status"], "FIXED_INPUT_NOT_IDENTIFIED")
            self.assertIsNone(rows[name]["estimated_value"])  # the input value never fills the estimate field
            self.assertIsNone(rows[name]["uncertainty"])
            self.assertEqual(rows[name]["input_value"], getattr(START, name))
        self.assertIn("E1, E2, G12 only", report["headline"])

    def test_refusal_report_files_and_contents(self):
        report = synthetic_demo("two_rows")
        folder = Path(tempfile.mkdtemp(prefix="nine_report_"))
        self.addCleanup(shutil.rmtree, folder, True)
        paths = write_report(report, folder)
        self.assertEqual(sorted(p.name for p in folder.iterdir()),
                         ["nine_constants_report.csv", "nine_constants_report.json", "nine_constants_report.txt"])
        record = json.loads(paths["json"].read_text(encoding="utf-8"))
        self.assertEqual(record["schema"], "research/nine-constants-report/v1")
        self.assertEqual(len(record["constants"]), 9)
        self.assertTrue(record["calibrated_inp"].startswith("NOT_PRODUCED"))
        self.assertEqual(len(report_csv(report).strip().splitlines()), 10)
        text = report_text(report)
        self.assertIn("RESEARCH_DIAGNOSTIC_ONLY", text)
        self.assertIn("NOT_A_VALIDATED_MATERIAL_PROPERTY", text)
        self.assertIn("SYNTHETIC", text)
        for name in ("synthetic", "uncertainty_basis", "nuisance_assumptions", "fe_cost_plan", "registration",
                     "observations", "identifiability", "claim_classification"):
            self.assertIn(name, record)


if __name__ == "__main__":
    unittest.main()
