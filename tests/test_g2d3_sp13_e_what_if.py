"""G2d-3 — SP-13 E_in what-if on the archived local sensitivities (display only; never a recommended E).

The same f_trial = f_FE * (1 + delta_E) ** S_E as SP-02, with only the recorded SP-13 strict freeze: R1 EXP4 <-> FE10
FIT, R2 EXP7 <-> FE13 HOLDOUT, observation_sufficient = False. One FIT mode: MIXED is never evaluated, the HOLDOUT
stays separate and the scientific limitations are shown with the preview. The arithmetic tests use the real recorded
SP-13 strict pairs and sensitivities from the repository; the store-gated test runs the chain on real archived shapes.
"""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from services import archived_sensitivity_evidence as ev  # noqa: E402
from services import sensitivity_what_if as wi  # noqa: E402
import test_g2d2_e_what_if as g2d2  # noqa: E402

SP13 = next(spec for spec in ev.SPECIMENS if spec.specimen == "SP13")
CHANGES = (0.0, -0.02, 0.02, -0.05, 0.05)
# Rounded reference values (Hz, FE vs exp. after) from the recorded SP-13 S_E; the exact checks use the formula.
EXPECTED = {
    -0.05: {"R1": (84.2608, -0.1074), "R2": (195.0795, -0.0514)},
    -0.02: {"R1": (85.2214, -0.0972), "R2": (198.0336, -0.0370)},
    0.0: {"R1": (85.8515, -0.0905), "R2": (199.9771, -0.0276)},
    0.02: {"R1": (86.4736, -0.0840), "R2": (201.9006, -0.0182)},
    0.05: {"R1": (87.3924, -0.0742), "R2": (204.7497, -0.0044)},
}


def sp13_physical() -> dict:
    return json.loads((ROOT / SP13.reevaluation_path).read_text(encoding="utf-8"))["results"]["PHYSICAL"]


def recorded_sp13_evidence(status: str = ev.VERIFIED, specimen: str = "SP13") -> ev.SensitivityEvidence:
    """A G2c evidence object holding exactly the recorded SP-13 strict pairs, sensitivities and outliers."""
    physical = sp13_physical()
    holdouts = set(physical["holdouts"]["holdout_row_ids"])
    rows = []
    for pair in physical["strict_pairs"]:
        s = physical["sensitivities"][pair["row_id"]]
        rows.append(ev.SensitivityRow(pair["row_id"], "HOLDOUT" if pair["row_id"] in holdouts else "FIT",
                                      pair["experimental_mode"], pair["fe_mode"], pair["experimental_hz"],
                                      pair["fe_hz"], pair["relative_frequency_error"], pair["mac"], pair["mac"],
                                      s["S_E"], s["S_G12"], "RESOLVED", True, "accepted strict pair"))
    for excluded in physical["excluded"]:
        rows.append(ev.SensitivityRow("—", "NO_STRICT_ROW", excluded["experimental_mode"], None, 30.0, None, None,
                                      None, None, None, None, "not applicable", False, excluded["reason"]))
    return ev.SensitivityEvidence(status, specimen, (), tuple(rows),
                                  baseline={"E_in_plane_mpa": 52000.0, "G12_mpa": 4500.0},
                                  perturbations={"E_in_plane_mpa+": 54600.0, "E_in_plane_mpa-": 49400.0,
                                                 "G12_mpa+": 4725.0, "G12_mpa-": 4275.0},
                                  source=f"{SP13.reevaluation_path} (results.PHYSICAL); CARBON-5A ±5 %")


predicted = g2d2.predicted


class AcceptedFreezeTests(unittest.TestCase):
    def test_required_rows_are_the_accepted_strict_freezes(self):
        for specimen in ("SP02", "SP13"):
            with self.subTest(specimen=specimen):
                spec = next(s for s in ev.SPECIMENS if s.specimen == specimen)
                physical = json.loads((ROOT / spec.reevaluation_path).read_text(encoding="utf-8"))["results"]["PHYSICAL"]
                holdouts = set(physical["holdouts"]["holdout_row_ids"])
                self.assertEqual({row["row_id"]: ("HOLDOUT" if row["row_id"] in holdouts else "FIT",
                                                  row["experimental_mode"], row["fe_mode"])
                                  for row in physical["strict_pairs"]}, wi.ACCEPTED_STRICT_ROWS[specimen])
        self.assertEqual(wi.ACCEPTED_STRICT_ROWS["SP13"], {"R1": ("FIT", 4, 10), "R2": ("HOLDOUT", 7, 13)})
        self.assertEqual(set(wi.ACCEPTED_STRICT_ROWS), {"SP02", "SP13"})
        self.assertEqual(wi.REQUIRED_STRICT_ROWS, {"R1": "FIT", "R2": "FIT", "R3": "HOLDOUT"})  # SP-02 unchanged

    def test_recorded_sp13_values(self):
        physical = sp13_physical()
        self.assertIs(physical["observation_sufficient"], False)
        self.assertEqual(physical["holdouts"]["fit_row_ids"], ["R1"])
        self.assertEqual(physical["tracking_refusals"], [])
        pairs = {row["row_id"]: row for row in physical["strict_pairs"]}
        self.assertEqual(pairs["R1"]["fe_hz"], 85.85149383544922)
        self.assertEqual(pairs["R2"]["fe_hz"], 199.9770965576172)
        self.assertAlmostEqual(pairs["R1"]["relative_frequency_error"], -0.0905, places=4)
        self.assertAlmostEqual(physical["sensitivities"]["R1"]["S_G12"], 0.1234, places=4)


class ArithmeticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evidence = recorded_sp13_evidence()
        self.recorded = {row.row_id: row for row in self.evidence.rows if row.role != "NO_STRICT_ROW"}

    def test_zero_change_reproduces_the_recorded_baseline_exactly(self):
        result = wi.e_what_if(self.evidence, 0.0)
        self.assertEqual((result.status, result.specimen, result.e_trial_mpa), (wi.AVAILABLE, "SP13", 52000.0))
        rows = predicted(result)
        self.assertEqual({row_id: row.role for row_id, row in rows.items()}, {"R1": "FIT", "R2": "HOLDOUT"})
        self.assertEqual(rows["R1"].trial_hz, 85.85149383544922)  # exactly, not approximately
        self.assertEqual(rows["R2"].trial_hz, 199.9770965576172)
        self.assertEqual(((rows["R1"].experimental_mode, rows["R1"].fe_mode),
                          (rows["R2"].experimental_mode, rows["R2"].fe_mode)), ((4, 10), (7, 13)))
        for row in rows.values():
            self.assertEqual(row.effect, wi.UNCHANGED)
            self.assertEqual(row.error_after, row.error_before)

    def test_predictions_follow_the_recorded_sp13_sensitivities(self):
        physical = sp13_physical()
        for change in CHANGES:
            with self.subTest(change=change):
                result = wi.e_what_if(self.evidence, change)
                self.assertEqual(result.status, wi.AVAILABLE)
                self.assertEqual(result.e_trial_mpa, 52000.0 * (1.0 + change))
                rows = predicted(result)
                self.assertEqual(set(rows), {"R1", "R2"})
                for row_id, row in rows.items():
                    recorded = self.recorded[row_id]
                    s_e = physical["sensitivities"][row_id]["S_E"]
                    self.assertEqual(row.s_e, s_e)
                    self.assertEqual(row.trial_hz, recorded.fe_hz * (1.0 + change) ** s_e)
                    self.assertAlmostEqual(row.error_after, (row.trial_hz - recorded.experimental_hz)
                                           / recorded.experimental_hz, places=15)
                    hz, after = EXPECTED[change][row_id]
                    self.assertAlmostEqual(row.trial_hz, hz, delta=5e-5)
                    self.assertAlmostEqual(row.error_after, after, delta=5e-5)
                    self.assertEqual(row.effect, wi.UNCHANGED if change == 0 else
                                     wi.IMPROVES if change > 0 else wi.WORSENS)

    def test_no_mixed_and_holdout_separate(self):
        for change in CHANGES:
            with self.subTest(change=change):
                result = wi.e_what_if(self.evidence, change)
                self.assertFalse(result.mixed)
                self.assertNotIn("MIXED:", result.fit_summary)
                self.assertIn("MIXED is not evaluated: only one FIT mode", result.fit_summary)
                self.assertTrue(result.fit_summary.startswith("1 FIT row(s)"))
                self.assertNotIn("R2", result.fit_summary)
                self.assertTrue(result.holdout_summary.startswith("1 HOLDOUT row(s)"))
                if change:
                    self.assertIn("R2", result.holdout_summary)
                self.assertNotIn("MIXED", result.holdout_summary)
                self.assertNotIn("MIXED: FIT modes move", wi.short_status(result))

    def test_r1_difference_is_not_closed_within_the_interval(self):
        for change in CHANGES:
            r1 = predicted(wi.e_what_if(self.evidence, change))["R1"]
            self.assertLess(r1.error_after, -0.074)  # still about -7.4 % at +5 %; nothing extrapolated

    def test_outliers_preserved(self):
        result = wi.e_what_if(self.evidence, 0.05)
        self.assertEqual([(r.row_id, r.experimental_mode, r.fe_mode) for r in result.rows],
                         [(r.row_id, r.experimental_mode, r.fe_mode) for r in self.evidence.rows])
        outliers = [row for row in result.rows if row.role == "NO_STRICT_ROW"]
        self.assertEqual([row.experimental_mode for row in outliers], [1, 2, 3, 5, 6, 8, 9, 10, 11, 12])
        self.assertTrue(all(row.trial_hz is None for row in outliers))

    def test_limitations_are_displayed(self):
        result = wi.e_what_if(self.evidence, 0.05)
        text = "\n".join(result.limitations)
        for needed in ("only one FIT mode", "observation_sufficient = False",
                       "E_in and G12 cannot be independently identified", "G12 is fixed at 4500 MPa",
                       "S_G12 = 0.1234", "-9.05%", "not a material calibration, a validation or an accepted FE result",
                       "no E_in or G12 is recommended", "does not pass that gate", "MIXED is not evaluated",
                       "SP-02 values are never transferred"):
            self.assertIn(needed, text)
        summary = wi.summary_text(result)
        self.assertIn("SP-13", summary)
        self.assertIn("Limitations:", summary)
        self.assertIn(text.splitlines()[0], summary)
        self.assertIn("SP-13", wi.short_status(result))
        self.assertIn("one FIT mode, MIXED not evaluated", wi.short_status(result))
        fields = set(wi.EWhatIf.__dataclass_fields__) | set(wi.WhatIfRow.__dataclass_fields__)
        self.assertFalse(fields & {"recommended_e", "recommended_g12", "best_e", "optimum", "g12_trial",
                                   "calibration", "gate_passed"})

    def test_bounds(self):
        for change in (0.05, -0.05):
            self.assertEqual(wi.e_what_if(self.evidence, change).status, wi.AVAILABLE)
        for change in (0.0501, -0.0501, 0.08, -0.1, float("nan")):
            with self.subTest(change=change):
                result = wi.e_what_if(self.evidence, change)
                self.assertEqual(result.status, wi.BLOCKED)
                self.assertEqual(result.rows, ())


class GuardTests(unittest.TestCase):
    def assertIncomplete(self, evidence, text: str) -> None:
        result = wi.e_what_if(evidence, 0.02)
        self.assertEqual(result.status, wi.INCOMPLETE)
        self.assertEqual(result.rows, ())  # no partial FIT/HOLDOUT preview
        self.assertIsNone(result.e_trial_mpa)
        self.assertIn(text, result.reason)
        self.assertIn("incomplete SP-13 strict evidence", result.reason)
        self.assertIn("R1 FIT (EXP4 <-> FE10), R2 HOLDOUT (EXP7 <-> FE13)", result.reason)

    def with_rows(self, rows) -> ev.SensitivityEvidence:
        return replace(recorded_sp13_evidence(), rows=tuple(rows))

    def test_missing_duplicate_misclassified_repaired_or_unexpected_rows(self):
        rows = recorded_sp13_evidence().rows
        r1 = next(row for row in rows if row.row_id == "R1")
        for absent, role in (("R1", "FIT"), ("R2", "HOLDOUT")):
            with self.subTest(absent=absent):
                self.assertIncomplete(self.with_rows(r for r in rows if r.row_id != absent), f"{absent} ({role}) is absent")
        self.assertIncomplete(self.with_rows(list(rows) + [r1]), "R1 appears 2 times")
        for row_id, wrong in (("R1", "HOLDOUT"), ("R2", "FIT")):
            with self.subTest(row_id=row_id):
                self.assertIncomplete(self.with_rows(replace(r, role=wrong) if r.row_id == row_id else r for r in rows),
                                      f"{row_id} is {wrong}")
        self.assertIncomplete(self.with_rows(replace(r, fe_mode=11) if r.row_id == "R1" else r for r in rows),
                              "R1 pairs EXP4 with FE11, the accepted pair is EXP4 <-> FE10")
        self.assertIncomplete(self.with_rows(list(rows) + [replace(r1, row_id="R3", role="HOLDOUT")]),
                              "unexpected strict row R3 (HOLDOUT)")
        unsupported = (replace(r, applicable=False, s_e=None, reason="not paired") if r.row_id == "R2" else r
                       for r in rows)
        self.assertIncomplete(self.with_rows(unsupported), "R2 (HOLDOUT): not applicable: not paired")

    def test_reference_only_and_not_applicable_block(self):
        for evidence in (recorded_sp13_evidence(ev.REFERENCE_ONLY), ev.not_applicable("wrong ODB", specimen="SP13"),
                         None, replace(recorded_sp13_evidence(), baseline={"E_in_plane_mpa": 52000.0,
                                                                           "G12_mpa": 4725.0})):
            with self.subTest(evidence=getattr(evidence, "status", None)):
                result = wi.e_what_if(evidence, 0.02)
                self.assertEqual(result.status, wi.BLOCKED)
                self.assertEqual(result.rows, ())
                self.assertIsNone(result.e_trial_mpa)

    def test_a_specimen_label_never_transfers_sensitivities(self):
        sp02_as_sp13 = wi.e_what_if(g2d2.recorded_sp02_evidence(ev.VERIFIED, specimen="SP13"), 0.02)
        self.assertEqual((sp02_as_sp13.status, sp02_as_sp13.rows), (wi.INCOMPLETE, ()))
        for problem in ("R1 pairs EXP2 with FE8", "R2 is FIT, the accepted role is HOLDOUT",
                        "unexpected strict row R3 (HOLDOUT)"):
            self.assertIn(problem, sp02_as_sp13.reason)
        sp13_as_sp02 = wi.e_what_if(recorded_sp13_evidence(specimen="SP02"), 0.02)
        self.assertEqual((sp13_as_sp02.status, sp13_as_sp02.rows), (wi.INCOMPLETE, ()))
        self.assertIn("R3 (HOLDOUT) is absent", sp13_as_sp02.reason)
        # the SP-13 preview uses the S_E carried by the SP-13 evidence rows, never SP-02 values
        sp02_s = {row.s_e for row in g2d2.recorded_sp02_evidence().rows if row.s_e is not None}
        live = predicted(wi.e_what_if(recorded_sp13_evidence(), 0.05))
        self.assertFalse({row.s_e for row in live.values()} & sp02_s)
        self.assertEqual({row_id: row.s_e for row_id, row in live.items()},
                         {row_id: s["S_E"] for row_id, s in sp13_physical()["sensitivities"].items()})


class SP02UnchangedTests(unittest.TestCase):
    def test_sp02_predictions_and_presentation(self):
        evidence = g2d2.recorded_sp02_evidence()
        for change, r3 in ((0.0, 207.4273), (-0.02, 205.4101), (0.02, 209.4237)):
            result = wi.e_what_if(evidence, change)
            self.assertEqual((result.status, result.specimen, result.limitations), (wi.AVAILABLE, "SP02", ()))
            self.assertAlmostEqual(predicted(result)["R3"].trial_hz, r3, delta=5e-5)
            self.assertEqual(result.mixed, change != 0.0)
            self.assertNotIn("only one FIT mode", result.fit_summary)
            self.assertNotIn("Limitations:", wi.summary_text(result))


class TkTests(unittest.TestCase):
    application = g2d2.TkTests.application
    show = g2d2.TkTests.show
    table = g2d2.TkTests.table

    def test_sp13_preview_title_and_limitations(self):
        root, application = self.application()
        frame = application.what_if_spinbox.master.master
        self.assertTrue(str(frame.cget("text")).startswith("E_in what-if, SP-02 / SP-13"))
        evidence = recorded_sp13_evidence()
        self.show(application, evidence)
        self.assertEqual(str(application.what_if_spinbox.cget("state")), "normal")
        application.what_if_change.set("5")
        self.assertEqual(self.table(application), [tuple(r) for r in wi.table_rows(wi.e_what_if(evidence, 0.05))])
        status = application.what_if_status.cget("text")
        self.assertIn("SP-13", status)
        self.assertNotIn("MIXED: FIT modes move", status)
        details = application.what_if_details.get("1.0", "end")
        for line in wi.e_what_if(evidence, 0.05).limitations:
            self.assertIn(line, details)
        self.assertIn(wi.CAVEAT, details)
        application.what_if_change.set("6")  # outside the archived interval: refused
        self.assertEqual(self.table(application), [])
        self.show(application, recorded_sp13_evidence(ev.REFERENCE_ONLY))
        self.assertEqual(str(application.what_if_spinbox.cget("state")), "disabled")
        self.assertEqual(self.table(application), [])


class RealArchivedShapeTests(unittest.TestCase):
    """SP-13 on real archived data (store-gated; no Abaqus): the real PolyMAX UNV, the identity-verified archived FE
    geometry and the ARCHIVED CARBON-4C baseline shape pack, compared on the accepted physical registration; the
    governed MACs are reproduced, G2c is VERIFIED with the recorded R1 / R2 sensitivities and the what-if equals the
    recorded-value predictions. Not exercised: Abaqus extraction from the ODB and the GUI worker."""

    def test_real_sp13_chain(self):
        from domain.experiment_fixture import fixture_roots_from_environment, load_experiment_fixture_manifest

        roots = fixture_roots_from_environment()
        missing = [store for store in ("snadwich", "carbon-project-archive") if store not in roots]
        if missing:
            self.skipTest(f"data stores {missing} not configured")
        import numpy as np

        from domain.specimen_manifest import load_specimen_manifest
        from modal_core import ModalDataset, ModeShape, compare_modal_datasets
        from services.fe_shape_pack import load_shape_pack, load_shape_pack_record
        from services.physical_registration import load_fe_geometry
        from universal_reader import load_universal_modal_file

        fixture = load_experiment_fixture_manifest(ROOT / ev.FIXTURE_MANIFEST).fixture(SP13.fixture_id)
        odb = roots["carbon-project-archive"] / "carbon4c/run_sp13/SP13_a46d08b52995e078.odb"
        unv = roots["snadwich"] / "SP-13/SP13_a_polymax.unv"
        if not odb.is_file() or not unv.is_file():
            self.skipTest("SP13 archive files are not available")
        experimental = load_universal_modal_file(unv, modal_set=fixture.modal_set.name)
        fe = load_fe_geometry(load_specimen_manifest(ROOT / "docs/auto_id/specimens/SP13.physical.specimen.json"), roots)
        pack = load_shape_pack(load_shape_pack_record(ROOT / "docs/auto_id/fe_shapes/SP13_a46d08b52995e078.shape-pack.json"),
                               roots)
        ids = np.asarray(fe.node_ids, dtype=object)
        index = {node: i for i, node in enumerate(ids.tolist())}
        rows = np.array([index[str(node)] for node in pack.node_ids])
        modes = []
        for k, (number, hz) in enumerate(zip(pack.mode_numbers, pack.frequencies_hz)):
            if number > 17:
                continue
            vectors = np.zeros((len(ids), 3), dtype=np.float32)
            vectors[rows] = pack.displacements[k]
            modes.append(ModeShape(number, hz, ids, fe.coordinates, vectors))
        abaqus = ModalDataset("archived shape pack", odb, modes)
        governed = ev.bind_accepted_reference(odb, unv, abaqus, experimental)
        result = compare_modal_datasets(abaqus, experimental, frozen_registration=governed.registration)
        result.metadata["comparison_inputs"] = ev.comparison_input_record(odb, unv, fixture.modal_set.name)
        macs = {(p.experimental_mode, p.abaqus_mode): p.mac for p in result.pairs}
        for row in sp13_physical()["strict_pairs"]:
            self.assertAlmostEqual(macs[(row["experimental_mode"], row["fe_mode"])], row["mac"], places=9)

        evidence = ev.check_archived_sensitivity_evidence(result)
        self.assertEqual((evidence.status, evidence.specimen), (ev.VERIFIED, "SP13"), evidence.reasons)
        recorded = recorded_sp13_evidence()
        strict = {row.row_id: row for row in evidence.rows if row.role != "NO_STRICT_ROW"}
        self.assertEqual({row_id: (row.role, row.s_e, row.s_g12) for row_id, row in strict.items()},
                         {row.row_id: (row.role, row.s_e, row.s_g12) for row in recorded.rows
                          if row.role != "NO_STRICT_ROW"})
        for change in CHANGES:
            live, expected = wi.e_what_if(evidence, change), wi.e_what_if(recorded, change)
            self.assertEqual(live.status, wi.AVAILABLE)
            self.assertEqual(live.limitations, expected.limitations)
            self.assertEqual(set(predicted(live)), {"R1", "R2"})
            for row_id, row in predicted(live).items():
                self.assertAlmostEqual(row.trial_hz, predicted(expected)[row_id].trial_hz, places=9)
                self.assertEqual(row.effect, predicted(expected)[row_id].effect)


if __name__ == "__main__":
    unittest.main()
