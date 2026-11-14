"""ABM-SANDWICH-SP13-1: the SP-13 sandwich trial (face-sheet E1 = E2 and G12 from the archived +/-5 % FE response).

The calculation is tested on synthetic frequencies only: no test fits the measured SP-13 data. The tests on the real
SP-13 files and on the archived shape packs only read them (identity, baseline frequencies, sensitivities); they run
where those files are and are skipped elsewhere, and a skip is not a pass."""

from __future__ import annotations

import csv
import hashlib
import io
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import threading
import unittest
from unittest import mock

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
for entry in (ROOT / "src", ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import test_real_fit_r1_tuning as base  # noqa: E402
from new_gui import research_tuning_model as rm  # noqa: E402
from services import sandwich_trial_candidates as stc  # noqa: E402
from services.branch_tracker import FEModalState  # noqa: E402

REAL_INP = Path(r"D:\Snadwich\SP-13\SP13_mesh_local_v1_modal\SP13_mesh_local_v1_modal.inp")
REAL_UNV = Path(r"D:\Snadwich\New  EXP results\SPname_files_ROTATED_261028"
                r"\SP13_500by500_Glue420_Auxetic_ROTATED_Polytec_261028.unv")
REAL_ARCHIVE = Path(r"D:\carbon_project_archive")
TARGET_SHA = "8abf951dba4b8a942922cb4af96074fc1ce8fce2a3f0de8ce082bc5820eeda10"
SEPTEMBER_SHA = "f268023583972f0a9c1660bc60631587e8f3330e4fb7495e52d8310906af39fe"
SP10_SHA = "432adf963085b012b07a6b235e1dde3c4df83ea87b85326497df0a89a9eeef1f"
E0, G0 = 52000.0, 4500.0
BOUNDS = {"E_in_plane_mpa": (49400.0, 54600.0), "G12_mpa": (4275.0, 4725.0)}
# (FE mode, baseline Hz, S_E, S_G12): rounded values of the kind the SP-13 FE model has (twist, bending pairs, ...)
MODES = ((7, 22.5, 0.013, 0.468), (8, 72.7, 0.492, 0.001), (9, 76.0, 0.491, 0.001), (10, 85.9, 0.365, 0.123),
         (11, 87.8, 0.366, 0.121), (12, 138.0, 0.291, 0.191), (13, 200.0, 0.483, 0.002), (14, 204.9, 0.481, 0.003))
MATERIAL = stc.FaceMaterial("CFRP_Face", {"E1": 52000.0, "E2": 52000.0, "E3": 6700.0, "nu12": 0.05, "nu13": 0.3,
                                          "nu23": 0.3, "G12": 4500.0, "G13": 2200.0, "G23": 2200.0},
                            ("52000.", "52000.", "6700.", "0.05", "0.3", "0.3", "4500.", "2200.", "2200."), (8, 1), 11, 14,
                            (15, 16))


def _sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evidence(unresolved=(), modes=MODES) -> stc.FaceSensitivityEvidence:
    items = []
    for mode, hz, s_e, s_g in modes:
        if mode in unresolved:
            items.append(stc.ModeSensitivity(mode, hz, False, reason="branch not resolved in all four states (test)"))
        else:
            items.append(stc.ModeSensitivity(mode, hz, True, s_e, s_g, {
                "E_in_plane_mpa+": s_e, "E_in_plane_mpa-": s_e, "G12_mpa+": s_g, "G12_mpa-": s_g},
                {key: (mode, 1.0, hz) for key in ("E_in_plane_mpa+", "E_in_plane_mpa-", "G12_mpa+", "G12_mpa-")}))
    return stc.FaceSensitivityEvidence(stc.VERIFIED, (), ("synthetic evidence (test)",),
                                       {"E_in_plane_mpa": E0, "G12_mpa": G0}, dict(BOUNDS),
                                       tuple((m, hz) for m, hz, _e, _g in modes), tuple(items), "synthetic")


def measured(E, G, modes=MODES, order=None) -> tuple:
    """(record, Hz): the response model itself at a known E and G12; record k is FE mode ``order[k-1]`` (default: rank)."""
    table = {mode: hz * (E / E0) ** s_e * (G / G0) ** s_g for mode, hz, s_e, s_g in modes}
    order = order or [mode for mode, *_rest in modes]
    return tuple((index + 1, table[mode]) for index, mode in enumerate(order))


def rank(records, ev) -> stc.Hypothesis:
    return stc.frequency_order_hypothesis(records, ev.baseline_modes)


def solve(records, ev=None, roles=None, declared=None, selected=stc.FREQUENCY_ORDER) -> stc.TrialResult:
    ev = ev or evidence()
    stated = [rank(records, ev)]
    if declared is not None:
        stated.append(stc.declared_hypothesis(records, declared))
    return stc.calculate(ev, records, roles or {}, stated, selected)


class SyntheticRecovery(unittest.TestCase):
    def test_a_known_face_e_and_g12_inside_the_interval_are_recovered(self):
        records = measured(53500.0, 4400.0)
        result = solve(records)
        outcome = result.selected
        self.assertEqual(outcome.status, stc.CANDIDATE)
        self.assertEqual(outcome.at_limit, ())
        self.assertAlmostEqual(outcome.values["E1"], 53500.0, delta=1e-6)
        self.assertAlmostEqual(outcome.values["G12"], 4400.0, delta=1e-6)
        self.assertEqual(outcome.values["E1"], outcome.values["E2"])  # one face modulus for both directions
        self.assertEqual(set(outcome.values), {"E1", "E2", "G12"})  # no core, tie or density value
        self.assertEqual((outcome.rank, outcome.fit_count), (2, 8))
        for row in outcome.rows:
            self.assertAlmostEqual(row.predicted_hz, row.experimental_hz, delta=1e-9)
            self.assertAlmostEqual(row.after, 0.0, delta=1e-12)
        self.assertLess(outcome.cost, 1e-24)
        self.assertEqual(result.label, stc.LABEL)
        self.assertIn("UNVERIFIED MODE CORRESPONDENCE", outcome.warnings[0])

    def test_the_baseline_itself_gives_no_change(self):
        outcome = solve(measured(E0, G0)).selected
        self.assertEqual(outcome.status, stc.CANDIDATE)
        self.assertAlmostEqual(outcome.values["E1"], E0, delta=1e-6)
        self.assertAlmostEqual(outcome.values["G12"], G0, delta=1e-6)

    def test_a_holdout_is_predicted_and_not_fitted_and_an_excluded_record_stays_listed(self):
        records = list(measured(53000.0, 4600.0))
        records[5] = (6, records[5][1] * 1.02)  # the HOLDOUT record is off by 2 %: it must not move the fit
        records[7] = (8, records[7][1] * 0.50)  # the EXCLUDED record is far off
        stated = {record: 6 + record for record, _hz in records}  # declared: the far-off record keeps its FE mode
        outcome = solve(tuple(records), roles={6: stc.HOLDOUT, 8: stc.EXCLUDED}, declared=stated,
                        selected=stc.DECLARED).selected
        self.assertAlmostEqual(outcome.values["E1"], 53000.0, delta=1e-6)
        self.assertAlmostEqual(outcome.values["G12"], 4600.0, delta=1e-6)
        rows = {row.record: row for row in outcome.rows}
        self.assertEqual([row.record for row in outcome.rows], list(range(1, 9)))
        self.assertEqual((rows[6].role, rows[8].role), (stc.HOLDOUT, stc.EXCLUDED))
        self.assertAlmostEqual(rows[6].after, 1 / 1.02 - 1, delta=1e-9)
        self.assertAlmostEqual(outcome.rms["HOLDOUT_after"], abs(1 / 1.02 - 1), delta=1e-9)
        self.assertEqual(outcome.fit_count, 6)

    def test_noisy_frequencies_give_a_least_squares_point_with_signed_residuals(self):
        records = tuple((record, hz * (1 + 0.004 * (-1) ** record)) for record, hz in measured(52800.0, 4550.0))
        outcome = solve(records).selected
        self.assertEqual(outcome.status, stc.CANDIDATE)
        self.assertAlmostEqual(outcome.values["E1"], 52800.0, delta=600.0)
        signs = {np.sign(row.after) for row in outcome.rows}
        self.assertEqual(signs, {-1.0, 1.0})  # residuals keep their sign
        self.assertLess(outcome.rms["FIT_after"], 0.005)


class SensitivitySource(unittest.TestCase):
    def states(self, change=None):
        generator = np.random.default_rng(7)
        shapes = np.linalg.qr(generator.normal(size=(60, 5)))[0].T  # five orthonormal shapes on 60 DOFs
        numbers, hz = (7, 8, 9, 10, 11), np.array([20.0, 70.0, 75.0, 86.0, 88.0])
        s_e, s_g = np.array([0.02, 0.49, 0.49, 0.36, 0.37]), np.array([0.47, 0.0, 0.0, 0.12, 0.12])
        base_state = FEModalState("BASE", "g" * 64, "n" * 64, numbers, tuple(hz), shapes)
        factors = {"E_in_plane_mpa+": ("E_in_plane_mpa", 1.05), "E_in_plane_mpa-": ("E_in_plane_mpa", 0.95),
                   "G12_mpa+": ("G12_mpa", 1.05), "G12_mpa-": ("G12_mpa", 0.95)}
        states = {}
        for key, (parameter, factor) in factors.items():
            slope = s_e if parameter == "E_in_plane_mpa" else s_g
            frequencies, state_shapes, state_numbers = hz * factor ** slope, shapes.copy(), list(numbers)
            if change is not None:
                frequencies, state_shapes = change(key, frequencies, state_shapes)
            states[key] = FEModalState(key, "g" * 64, "n" * 64, tuple(state_numbers), tuple(frequencies), state_shapes)
        return base_state, states, factors, s_e, s_g

    def test_central_sensitivities_of_every_tracked_branch(self):
        base_state, states, factors, s_e, s_g = self.states()
        modes = stc.sensitivities_from_states(base_state, states, factors)
        self.assertTrue(all(m.resolved for m in modes))
        for item, e, g in zip(modes, s_e, s_g):
            self.assertAlmostEqual(item.s_e, e, delta=1e-12)
            self.assertAlmostEqual(item.s_g12, g, delta=1e-12)
            self.assertAlmostEqual(item.asymmetry, 0.0, delta=1e-12)

    def test_a_branch_is_followed_by_shape_when_the_mode_order_changes(self):
        def swap(key, frequencies, shapes):  # in the E+ state the 4th and 5th modes arrive in the other order
            if key == "E_in_plane_mpa+":
                frequencies, shapes = frequencies.copy(), shapes.copy()
                frequencies[[3, 4]] = frequencies[[4, 3]]
                shapes[[3, 4]] = shapes[[4, 3]]
            return frequencies, shapes

        base_state, states, factors, s_e, _s_g = self.states(swap)
        modes = {m.fe_mode: m for m in stc.sensitivities_from_states(base_state, states, factors)}
        self.assertEqual(modes[10].tracked["E_in_plane_mpa+"][0], 11)  # baseline FE 10 is mode 11 of that state
        self.assertAlmostEqual(modes[10].s_e, s_e[3], delta=1e-12)  # by mode number it would have been another value
        self.assertAlmostEqual(modes[11].s_e, s_e[4], delta=1e-12)

    def test_a_lost_branch_has_no_sensitivity_and_the_reason(self):
        def lose(key, frequencies, shapes):
            if key == "G12_mpa-":
                shapes = shapes.copy()
                shapes[2] = np.random.default_rng(1).normal(size=shapes.shape[1])  # no longer the baseline shape
            return frequencies, shapes

        base_state, states, factors, _e, _g = self.states(lose)
        modes = {m.fe_mode: m for m in stc.sensitivities_from_states(base_state, states, factors)}
        self.assertFalse(modes[9].resolved)
        self.assertIsNone(modes[9].s_e)
        self.assertIn("G12_mpa-: BRANCH_LOSS", modes[9].reason)
        self.assertTrue(modes[8].resolved)

    def test_two_baseline_modes_claiming_one_mode_are_both_refused(self):
        def merge(key, frequencies, shapes):
            if key == "E_in_plane_mpa-":
                shapes = shapes.copy()
                shapes[4] = shapes[3]  # the state's mode 11 has the shape of baseline FE 10
            return frequencies, shapes

        base_state, states, factors, _e, _g = self.states(merge)
        modes = {m.fe_mode: m for m in stc.sensitivities_from_states(base_state, states, factors)}
        self.assertFalse(modes[10].resolved)
        self.assertFalse(modes[11].resolved)

    def test_the_repository_records_alone_are_a_missing_evidence_diagnosis_not_a_response_model(self):
        found = stc.load_face_sensitivities({})
        self.assertEqual(found.status, stc.MISSING)
        self.assertFalse(found.usable)
        self.assertEqual(found.modes, ())  # no sensitivity is issued by mode number
        self.assertEqual(len(found.baseline_modes), 24)  # the baseline frequencies are still known
        self.assertEqual(found.baseline, {"E_in_plane_mpa": E0, "G12_mpa": G0})
        self.assertEqual(found.bounds, BOUNDS)
        self.assertIn("not available", found.reasons[0])
        with self.assertRaises(ValueError):
            stc.calculate(found, measured(E0, G0), {}, [rank(measured(E0, G0), evidence())], stc.FREQUENCY_ORDER)

    def test_an_environment_without_the_store_gives_no_roots_and_a_named_folder_gives_one(self):
        self.assertEqual(stc.archive_roots(None, {}), {})
        archive = Path("some") / "archive"
        self.assertEqual(stc.archive_roots(archive / "fe_shapes"), {stc.ARCHIVE_STORE: archive})
        self.assertEqual(stc.archive_roots(str(archive)), {stc.ARCHIVE_STORE: archive})
        self.assertEqual(stc.archive_roots(None, {"AUTO_ID_FIXTURE_ROOT_CARBON_PROJECT_ARCHIVE": str(archive)}),
                         {stc.ARCHIVE_STORE: archive})

    def test_a_changed_shape_pack_record_is_incompatible(self):
        with tempfile.TemporaryDirectory() as folder:
            copy = Path(folder)
            for name in ("docs/auto_id", "docs/registrations"):
                shutil.copytree(ROOT / name, copy / name)
            record = copy / "docs/auto_id/fe_shapes/SP13_0e861d03c333bb0b.shape-pack.json"
            text = record.read_text(encoding="utf-8")
            self.assertIn("34d69d7920f5819c49ad5b2ab1aded824055aadbea3cb0244f405ab1a1595826", text)
            record.write_text(text.replace("34d69d7920f5819c49ad5b2ab1aded824055aadbea3cb0244f405ab1a1595826", "0" * 64),
                              encoding="utf-8")
            found = stc.load_face_sensitivities({}, repo_root=copy)
        self.assertEqual(found.status, stc.INCOMPATIBLE)
        self.assertIn("another FE geometry", found.reasons[0])

    def test_a_folder_without_the_packs_is_missing_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            found = stc.load_face_sensitivities(stc.archive_roots(folder))
        self.assertEqual(found.status, stc.MISSING)

    @unittest.skipUnless((REAL_ARCHIVE / "fe_shapes").is_dir(), "the carbon project archive is not on this machine")
    def test_the_archived_packs_give_the_accepted_sensitivities(self):
        found = stc.load_face_sensitivities(stc.archive_roots(REAL_ARCHIVE))
        self.assertEqual(found.status, stc.VERIFIED, found.reasons)
        modes = {m.fe_mode: m for m in found.modes}
        self.assertEqual(sorted(modes), list(range(7, 31)))
        # the accepted strict freeze (docs/auto_id/registration_evidence/SP13_registration_reevaluation.json, PHYSICAL)
        self.assertAlmostEqual(modes[10].s_e, 0.3646065173716216, delta=1e-12)
        self.assertAlmostEqual(modes[10].s_g12, 0.12335622431587442, delta=1e-12)
        self.assertAlmostEqual(modes[13].s_e, 0.48340889242231694, delta=1e-12)
        self.assertAlmostEqual(modes[13].s_g12, 0.0024084034368166717, delta=1e-12)
        self.assertFalse(modes[30].resolved)  # lost in two states: no value by mode number
        self.assertTrue(all(modes[n].resolved for n in range(7, 30)))
        self.assertGreater(modes[7].s_g12, 0.4)  # the twist mode answers G12, hardly E
        self.assertTrue(any("reproduce the accepted strict freeze row R1" in text for text in found.checks))


class Identity(unittest.TestCase):
    def test_only_the_october_rotated_series_is_the_target(self):
        target = stc.classify_experimental(TARGET_SHA, 448211)
        self.assertEqual((target.status, target.series), (stc.TARGET, stc.TARGET_SERIES))
        self.assertTrue(target.accepted)
        self.assertIn("PHYSICAL_REGISTRATION_NOT_VERIFIED", target.text)
        september = stc.classify_experimental(SEPTEMBER_SHA, 38541973)
        self.assertEqual(september.status, stc.OTHER_SERIES)
        self.assertIn("SP13/best", september.text)
        self.assertFalse(september.accepted)
        other_panel = stc.classify_experimental(SP10_SHA, 448391)
        self.assertEqual(other_panel.status, stc.OTHER_SERIES)
        self.assertIn("SP-10", other_panel.text)
        unknown = stc.classify_experimental("ab" * 32, 448211)
        self.assertEqual(unknown.status, stc.NOT_RECORDED)
        self.assertFalse(unknown.accepted)

    def test_an_input_that_is_not_the_accepted_one_is_named_and_not_used(self):
        with tempfile.TemporaryDirectory() as folder:
            inp = Path(folder) / "SP13_mesh_local_v1_modal.inp"  # the accepted name does not make it the accepted file
            inp.write_text("*Heading\n*Material, name=CFRP_Face\n*Elastic, type=ENGINEERING CONSTANTS\n"
                           "52000.,52000., 6700.,  0.05,   0.3,   0.3, 4500., 2200.\n 2200.,\n", encoding="utf-8")
            (Path(folder) / "SP13_mesh_local_v1_modal.dat").write_text(
                " E I G E N V A L U E    O U T P U T\n\n       7       19967.         141.31         22.489         1.0000\n",
                encoding="utf-8")
            model = stc.read_fe_model(inp)
            self.assertFalse(model.accepted)
            self.assertIsNone(model.material)
            self.assertIn("is not the accepted SP-13 source input", model.reasons[0])
            self.assertEqual(model.dat_rows, ((7, 22.489),))  # its frequencies can still be shown
            usable, _checks, reasons = stc.model_binding(model, evidence())
            self.assertFalse(usable)
            self.assertTrue(reasons)
            modes, source = stc.fe_frequencies(model, evidence())
            self.assertEqual(modes, ((7, 22.489),))
            self.assertIn("not identified", source)

    def test_a_missing_input_is_a_reason_not_a_crash(self):
        model = stc.read_fe_model(Path(tempfile.gettempdir()) / "no such model.inp")
        self.assertFalse(model.accepted)
        self.assertTrue(model.reasons)

    def test_a_dat_of_other_frequencies_breaks_the_binding(self):
        ev = evidence()
        model = stc.FeModel("m.inp", "0" * 64, 1, True, "model", ("ok",), (), MATERIAL, "m.dat",
                            tuple((mode, hz) for mode, hz, _e, _g in MODES))
        self.assertTrue(stc.model_binding(model, ev)[0])
        shifted = stc.FeModel("m.inp", "0" * 64, 1, True, "model", ("ok",), (), MATERIAL, "m.dat",
                              tuple((mode, hz * 1.01) for mode, hz, _e, _g in MODES))
        usable, _checks, reasons = stc.model_binding(shifted, ev)
        self.assertFalse(usable)
        self.assertIn("does not hold the accepted baseline frequencies", reasons[0])

    def test_another_baseline_breaks_the_binding(self):
        other = stc.FaceMaterial(MATERIAL.name, dict(MATERIAL.constants, E1=60000.0, E2=60000.0), MATERIAL.tokens,
                                 MATERIAL.row_lengths, 11, 14, (15, 16))
        model = stc.FeModel("m.inp", "0" * 64, 1, True, "model", (), (), other)
        usable, _checks, reasons = stc.model_binding(model, evidence())
        self.assertFalse(usable)
        self.assertIn("not the baseline the sensitivities were computed about", reasons[0])

    @unittest.skipUnless(REAL_INP.is_file(), "the SP-13 Abaqus input is not on this machine")
    def test_the_real_input_is_the_accepted_model_and_its_face_record_is_read(self):
        before = (REAL_INP.stat().st_size, REAL_INP.stat().st_mtime_ns)
        model = stc.read_fe_model(REAL_INP)
        self.assertTrue(model.accepted, model.reasons)
        self.assertEqual(model.sha256, "9d4105840e527354dbd0bb4d0d0012f7708125aa94619b0dcc486fd76dc70571")
        self.assertEqual(model.material.name, "CFRP_Face")
        self.assertEqual(model.material.tokens, MATERIAL.tokens)
        self.assertEqual(model.material.row_lengths, (8, 1))
        self.assertEqual(model.material.data_lines, (1957765, 1957766))
        self.assertEqual(len(model.dat_rows), 24)
        self.assertEqual((REAL_INP.stat().st_size, REAL_INP.stat().st_mtime_ns), before)


class RankAndExtrapolation(unittest.TestCase):
    def test_one_fit_record_is_rank_deficient_and_gives_no_value(self):
        records = measured(53000.0, 4600.0)
        roles = {record: stc.EXCLUDED for record, _hz in records}
        roles[4] = stc.FIT
        result = solve(records, roles=roles)
        outcome = result.selected
        self.assertEqual(outcome.status, stc.RANK_DEFICIENT)
        self.assertEqual((outcome.rank, outcome.fit_count), (1, 1))
        self.assertEqual(outcome.values, {})
        self.assertIn("rank 1 < 2 parameters", outcome.reasons[0])
        self.assertIn("no single pair is issued", outcome.reasons[0])
        self.assertTrue(stc.export_unavailable(result, None))
        self.assertEqual(rm.sandwich_candidate_rows(result), ())

    def test_records_that_answer_only_e_cannot_separate_g12(self):
        records = measured(53000.0, 4600.0)
        roles = {record: stc.EXCLUDED for record, _hz in records}
        roles.update({2: stc.FIT, 3: stc.FIT, 7: stc.FIT})  # FE 8, 9 and 13: S_G12 about 0.001 to 0.002
        modes = tuple((m, hz, s_e, 0.001 * s_e) if m in (8, 9, 13) else (m, hz, s_e, s_g) for m, hz, s_e, s_g in MODES)
        outcome = solve(measured(53000.0, 4600.0, modes), evidence(modes=modes), roles).selected
        self.assertEqual(outcome.status, stc.RANK_DEFICIENT)  # proportional rows: exactly one direction
        self.assertEqual(outcome.rank, 1)
        self.assertEqual(outcome.values, {})
        self.assertGreater(abs(outcome.weakest_direction["G12"]), 0.99)  # G12 is the undetermined one

    def test_no_fit_record_is_rank_zero(self):
        records = measured(E0, G0)
        outcome = solve(records, roles={record: stc.HOLDOUT for record, _hz in records}).selected
        self.assertEqual((outcome.status, outcome.rank), (stc.RANK_DEFICIENT, 0))

    def test_a_change_beyond_the_interval_is_held_at_the_limit_and_said(self):
        result = solve(measured(58240.0, 4500.0))  # the frequencies ask for E +12 %
        outcome = result.selected
        self.assertEqual(outcome.status, stc.AT_LIMIT)
        self.assertEqual(outcome.at_limit, ("E_in_plane_mpa",))
        self.assertEqual(outcome.values["E1"], 54600.0)  # exactly the archived +5 % state, never beyond
        self.assertEqual(outcome.values["E2"], 54600.0)
        self.assertLessEqual(outcome.values["G12"], 4725.0)
        self.assertGreaterEqual(outcome.values["G12"], 4275.0)
        self.assertAlmostEqual(outcome.unconstrained_change["E_in_plane_mpa"], 0.12, delta=1e-9)
        self.assertIn("outside the verified +/-5 % interval", outcome.reasons[0])
        self.assertIn("NOT a value", outcome.reasons[0])
        self.assertIn("UNSUPPORTED EXTRAPOLATION", stc.STATUS_TEXT[outcome.status])
        self.assertTrue(any("not a minimum of the fit" in text for text in outcome.warnings))
        self.assertGreater(outcome.rms["FIT_after"], 0.01)  # the difference is not closed and is shown

    def test_both_parameters_can_be_held(self):
        outcome = solve(measured(40000.0, 6000.0)).selected
        self.assertEqual(outcome.status, stc.AT_LIMIT)
        self.assertEqual((outcome.values["E1"], outcome.values["G12"]), (49400.0, 4725.0))
        self.assertEqual(set(outcome.at_limit), {"E_in_plane_mpa", "G12_mpa"})

    def test_a_fit_record_on_a_mode_without_a_verified_sensitivity_is_refused(self):
        records = measured(53000.0, 4600.0)
        ev = evidence(unresolved=(12,))
        refused = solve(records, ev).selected
        self.assertEqual(refused.status, stc.REFUSED)
        self.assertIn("record 6 (FIT) is compared with FE 12, which has no verified sensitivity", refused.reasons[0])
        self.assertEqual(refused.values, {})
        held_out = solve(records, ev, {6: stc.HOLDOUT}).selected  # the user's own decision, never a silent drop
        self.assertEqual(held_out.status, stc.CANDIDATE)
        row = next(r for r in held_out.rows if r.record == 6)
        self.assertIsNone(row.predicted_hz)
        self.assertIn("not predicted", row.note)

    def test_two_records_on_one_fe_mode_and_an_unknown_fe_mode_are_refused(self):
        records = measured(E0, G0)
        twice = solve(records, declared={r: (8 if r in (2, 3) else 6 + r) for r, _hz in records}, selected=stc.DECLARED)
        self.assertEqual(twice.selected.status, stc.REFUSED)
        self.assertIn("records 2 and 3 are both compared with FE 8", twice.selected.reasons[0])
        unknown = solve(records, declared={r: 40 + r for r, _hz in records}, selected=stc.DECLARED)
        self.assertEqual(unknown.selected.status, stc.REFUSED)
        self.assertIn("not a mode of the verified FE states", unknown.selected.reasons[0])

    def test_unverified_evidence_is_never_calculated(self):
        missing = stc.FaceSensitivityEvidence(stc.MISSING, ("no packs",), ())
        with self.assertRaises(ValueError):
            stc.calculate(missing, measured(E0, G0), {}, [rank(measured(E0, G0), evidence())], stc.FREQUENCY_ORDER)


class Hypotheses(unittest.TestCase):
    def test_the_frequency_rank_keeps_record_one_on_the_lowest_fe_mode(self):
        records = measured(E0, G0)
        hypothesis = rank(records, evidence())
        self.assertEqual(hypothesis.pairs, tuple((k + 1, 7 + k) for k in range(8)))
        self.assertEqual(hypothesis.fe_mode(1), 7)

    def test_record_one_is_never_dropped_whatever_its_role(self):
        records = list(measured(53000.0, 4600.0))
        records[0] = (1, records[0][1] * 1.25)  # far from its FE mode, as a suspension effect would be
        for role in stc.ROLES:
            outcome = solve(tuple(records), roles={1: role}).selected
            first = outcome.rows[0]
            self.assertEqual((first.record, first.role, first.fe_mode), (1, role, 7))
            self.assertAlmostEqual(first.before, 1 / 1.25 - 1, delta=0.02)
            self.assertEqual(len(outcome.rows), 8)
        excluded = solve(tuple(records), roles={1: stc.EXCLUDED}).selected
        self.assertAlmostEqual(excluded.values["E1"], 53000.0, delta=1e-6)

    def test_a_record_is_never_moved_to_a_nearer_fe_mode(self):
        records = list(measured(E0, G0))
        records[1] = (2, 75.9)  # nearer FE 9 (76.0) than FE 8 (72.7): the rank hypothesis still says FE 8
        outcome = solve(tuple(records)).selected
        self.assertEqual(outcome.rows[1].fe_mode, 8)

    def test_another_stated_correspondence_is_reported_as_competing_and_not_chosen(self):
        records = measured(53500.0, 4400.0)
        swapped = {record: 6 + record for record, _hz in records}
        swapped[4], swapped[5] = 11, 10  # the close pair the other way round
        result = solve(records, declared=swapped)
        self.assertEqual(result.selected.hypothesis.key, stc.FREQUENCY_ORDER)
        self.assertAlmostEqual(result.selected.values["E1"], 53500.0, delta=1e-6)  # unchanged by the alternative
        self.assertEqual(len(result.alternatives), 1)
        other = result.alternatives[0]
        self.assertEqual(other.hypothesis.key, stc.DECLARED)
        self.assertTrue(other.numerical)
        self.assertNotAlmostEqual(other.values["G12"], result.selected.values["G12"], delta=1e-3)
        self.assertTrue(result.competing)
        chosen_declared = solve(records, declared=swapped, selected=stc.DECLARED)
        self.assertEqual(chosen_declared.selected.hypothesis.key, stc.DECLARED)
        self.assertEqual(chosen_declared.alternatives[0].hypothesis.key, stc.FREQUENCY_ORDER)

    def test_the_same_correspondence_stated_twice_is_not_an_alternative(self):
        records = measured(53500.0, 4400.0)
        result = solve(records, declared={record: 6 + record for record, _hz in records})
        self.assertEqual(result.alternatives, ())
        self.assertFalse(result.competing)

    def test_a_record_not_in_the_declared_list_can_only_be_excluded(self):
        records = measured(53500.0, 4400.0)
        declared = {record: 6 + record for record, _hz in records if record != 1}
        refused = solve(records, declared=declared, selected=stc.DECLARED).selected
        self.assertEqual(refused.status, stc.REFUSED)
        self.assertIn("record 1 (FIT) has no FE mode", refused.reasons[0])
        kept = solve(records, roles={1: stc.EXCLUDED}, declared=declared, selected=stc.DECLARED).selected
        self.assertEqual(kept.status, stc.CANDIDATE)
        self.assertEqual((kept.rows[0].record, kept.rows[0].fe_mode, kept.rows[0].role), (1, None, stc.EXCLUDED))

    def test_no_correspondence_no_calculation(self):
        records = measured(E0, G0)
        with self.assertRaises(ValueError):
            stc.calculate(evidence(), records, {}, [rank(records, evidence())], "")
        with self.assertRaises(ValueError):
            stc.declared_hypothesis(records, {99: 7})
        self.assertEqual(rm.parse_fe_modes("1:7, 2:9 ,3:8"), {1: 7, 2: 9, 3: 8})
        for bad in ("1-7", "1:7, 1:8", "a:7", "1:"):
            with self.assertRaises(ValueError):
                rm.parse_fe_modes(bad)


def _model(folder: Path) -> stc.FeModel:
    inp = folder / "model.inp"
    inp.write_text("*Material, name=CFRP_Face\n*Material, name=PLA_Basic_Core\n", encoding="utf-8")
    return stc.FeModel(str(inp), _sha(inp), inp.stat().st_size, True, "SP13_mesh_local_v1_modal/carbon-property-set-v1",
                       ("INP identified (test)",), (), MATERIAL, None, ())


def _sources(folder: Path, records, ev=None, identity=None, model=None) -> rm.SandwichSources:
    ev = ev or evidence()
    unv = folder / "exp.unv"
    unv.write_bytes(b"stand-in for the experimental file\n")
    model = model or _model(folder)
    usable, checks, reasons = stc.model_binding(model, ev)
    modes, source = stc.fe_frequencies(model, ev)
    return rm.SandwichSources(model, ev, usable, checks, reasons,
                              identity or stc.ExperimentalIdentity(stc.TARGET, stc.TARGET_SERIES, "SP-13 target (test)"),
                              str(unv), _sha(unv), "polymax_bravo", tuple(records), modes, source, "")


class Export(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.records = measured(53123.456789012345, 4411.1234567890123)
        self.sources = _sources(self.folder, self.records)
        self.result = rm.run_sandwich_trial(self.sources, {}, "", stc.FREQUENCY_ORDER)

    def documents(self):
        return stc.export_documents(self.result, self.sources.model, self.sources.evidence, {
            "path": self.sources.unv_path, "sha256": self.sources.unv_sha256, "set_title": "polymax_bravo", "identity": "t"})

    def test_the_face_record_keeps_the_inp_order_layout_and_fixed_tokens(self):
        values = self.result.selected.values
        lines = stc.abaqus_lines(MATERIAL, values)
        self.assertEqual(lines[0], "*Elastic, type=ENGINEERING CONSTANTS")
        first, second = [item.strip() for item in lines[1].split(",")], lines[2]
        self.assertEqual(len(first), 8)
        self.assertEqual(first[2:6] + first[7:], ["6700.", "0.05", "0.3", "0.3", "2200."])  # E3, nu12, nu13, nu23, G13
        self.assertEqual(second, "2200.,")  # G23, on its own line as in the INP
        self.assertEqual((float(first[0]), float(first[1]), float(first[6])), (values["E1"], values["E2"], values["G12"]))
        self.assertEqual(first[0], first[1])  # E1 = E2, the same text
        self.assertTrue(all(len(item) <= stc.ABAQUS_FIELD_CHARS for item in first))

    def test_every_digit_is_written(self):
        documents = self.documents()
        values = self.result.selected.values
        self.assertAlmostEqual(values["E1"], 53123.456789012345, delta=1e-6)
        for name in ("E1", "G12"):
            self.assertIn(repr(values[name]), documents["txt"])
            self.assertEqual(float(repr(values[name])), values[name])
        rows = list(csv.DictReader(io.StringIO(documents["csv"])))
        face = {row["item"]: row for row in rows if row["section"] == "face material"}
        self.assertEqual(list(face), list(stc.CONSTANT_NAMES))
        self.assertEqual(float(face["E1"]["value"]), values["E1"])
        self.assertEqual(face["E3"]["value"], "6700.")
        self.assertIn("fixed: as written in the INP", face["G13"]["note"])

    def test_the_files_say_what_the_values_are_and_never_name_another_material(self):
        documents = self.documents()
        text = documents["txt"]
        for needed in (stc.LABEL, "UNVERIFIED MODE CORRESPONDENCE", "NUMERICAL_CANDIDATE_WITHIN_VERIFIED_RANGE",
                       "Face material CFRP_Face", "Change nothing else", "D-077", "M8 GATE NOT_MET",
                       "Frequency rank", "FE baseline Hz", "predicted Hz"):
            self.assertIn(needed, text)
        self.assertNotIn("PLA", text)  # the core material is not written
        self.assertNotIn("*Density", text)
        self.assertNotIn("*Material", text)  # no material block is manufactured: the record's data lines only
        self.assertEqual(text.count("*Elastic, type=ENGINEERING CONSTANTS"), 1)
        records = [row for row in csv.DictReader(io.StringIO(documents["csv"])) if row["section"] == "frequencies"]
        self.assertEqual(len(records), 8)
        self.assertIn("role FIT; FE mode 7", records[0]["note"])

    def test_a_limit_value_is_marked_in_the_files(self):
        sources = _sources(self.folder, measured(58240.0, 4500.0))
        result = rm.run_sandwich_trial(sources, {}, "", stc.FREQUENCY_ORDER)
        text = stc.export_documents(result, sources.model, sources.evidence, {})["txt"]
        self.assertIn("TRIAL_POINT_AT_VERIFIED_RANGE_LIMIT", text)
        self.assertIn("UNSUPPORTED EXTRAPOLATION", text)
        self.assertIn("LIMIT of the verified +/-5 % interval, not a fitted value", text)
        self.assertIn("54600.0, 54600.0, 6700.", text)

    def test_nothing_is_written_without_a_value_or_without_a_verified_face_record(self):
        roles = {record: stc.EXCLUDED for record, _hz in self.records}
        no_value = rm.run_sandwich_trial(self.sources, roles, "", stc.FREQUENCY_ORDER)
        self.assertIn("no numerical value", rm.sandwich_export_unavailable(no_value, self.sources))
        with self.assertRaises(ValueError):
            rm.export_sandwich(no_value, self.sources, self.folder, "t")
        unverified = stc.FeModel("m.inp", "0" * 64, 1, False, "", (), ("not the accepted input",))
        self.assertIn("no material lines are written", stc.export_unavailable(self.result, unverified))
        with self.assertRaises(ValueError):
            stc.export_documents(self.result, unverified, self.sources.evidence, {})
        self.assertIn("calculate", rm.sandwich_export_unavailable(None, self.sources))
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ["exp.unv", "model.inp"])

    def test_the_files_are_written_once_and_the_sources_stay_as_they_were(self):
        before = {p.name: _sha(p) for p in self.folder.iterdir()}
        target = self.folder / "out"
        target.mkdir()
        written = rm.export_sandwich(self.result, self.sources, target, "20261114_120000")
        self.assertEqual([p.name for p in written], ["sp13_face_candidate_abaqus_20261114_120000.txt",
                                                     "sp13_face_candidate_abaqus_20261114_120000.csv"])
        self.assertEqual({p.name: _sha(p) for p in self.folder.iterdir() if p.is_file()}, before)
        with self.assertRaises(OSError):  # never replaced
            rm.export_sandwich(self.result, self.sources, target, "20261114_120000")
        with self.assertRaises(OSError):
            rm.export_sandwich(self.result, self.sources, self.folder / "absent", "t")

    def test_a_source_changed_after_the_reading_is_refused(self):
        Path(self.sources.unv_path).write_bytes(b"another measurement\n")
        target = self.folder / "out"
        target.mkdir()
        with self.assertRaises(ValueError) as caught:
            rm.export_sandwich(self.result, self.sources, target, "t")
        self.assertIn("experimental file changed on disk", str(caught.exception))
        self.assertEqual(list(target.iterdir()), [])


class Page(base._PageHarness):
    def loaded(self, sources):
        window, panel = self.window()
        panel.paths.update(inp=sources.model.inp_path, unv=sources.unv_path)
        panel._refresh()
        with mock.patch.object(rm, "read_sandwich_sources", return_value=sources) as reader:
            self.assertTrue(panel.sandwich_read_button.isEnabled())
            panel.sandwich_read_button.click()
            self.wait(panel)
        self.assertEqual(reader.call_count, 1)
        return window, panel

    def folder(self) -> Path:
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        return folder

    def test_the_section_is_in_the_normal_window_and_idle_until_the_files_are_chosen(self):
        from new_gui import production_window as pw

        window, panel = self.window()
        self.assertIsInstance(window, pw.ProductionWindow)
        self.assertTrue(panel.sandwich_card.isVisible())
        self.assertFalse(panel.sandwich_read_button.isEnabled())
        self.assertFalse(panel.sandwich_body.isVisible())
        self.assertFalse(panel.read_sandwich())
        self.assertIn("NOT A MATERIAL PROPERTY", panel.sandwich_badge.text())
        self.assertFalse(panel.run_sandwich())

    def test_calculate_and_export_from_the_page(self):
        folder = self.folder()
        sources = _sources(folder, measured(53500.0, 4400.0))
        window, panel = self.loaded(sources)
        self.assertTrue(panel.sandwich_body.isVisible())
        identity = dict(panel.table_cells("sw_identity")[:9])
        self.assertIn("TARGET_SERIES", identity["Measurement series"])
        self.assertIn("ACCEPTED SP-13 FE MODEL", identity["FE model"])
        self.assertEqual(identity["Experimental SHA-256"], sources.unv_sha256)
        self.assertEqual(len(panel.table_cells("sw_fe")), 8)
        self.assertEqual(panel.table_cells("sw_fe")[0][:4], ["7", "22.5000", "0.0130", "0.4680"])
        self.assertIn("UNVERIFIED MODE CORRESPONDENCE", panel.sandwich_warning.text())
        self.assertTrue(panel.sandwich_warning.isVisible())
        # no correspondence is chosen for the user: no comparison and no calculation yet
        self.assertEqual(panel.sandwich_hypothesis.value(), "")
        self.assertFalse(panel.sandwich_run_button.isEnabled())
        self.assertEqual(panel.sandwich_record_cells()[1], ["select a correspondence", "", ""])
        self.assertFalse(panel.run_sandwich())
        self.assertEqual(sorted(panel.sandwich_roles()), list(range(1, 9)))
        panel.sandwich_hypothesis.buttons[0].click()  # Frequency rank
        self.app.processEvents()
        self.assertEqual(panel.sandwich_record_cells()[1][0], "FE 7")
        self.assertEqual(panel.sandwich_record_cells()[4][:2], ["FE 10", "85.9000"])
        self.assertTrue(panel.sandwich_run_button.isEnabled())
        self.assertFalse(panel.sandwich_export_button.isEnabled())
        with mock.patch("subprocess.Popen", side_effect=AssertionError("no process")):
            panel.sandwich_run_button.click()
        self.app.processEvents()
        self.assertEqual(panel.sandwich_result.status, stc.CANDIDATE)
        self.assertTrue(panel.sandwich_result_body.isVisible())
        self.assertIn("NUMERICAL_CANDIDATE_WITHIN_VERIFIED_RANGE", panel.sandwich_status.text())
        candidate = panel.table_cells("sw_candidate")
        self.assertEqual([row[0] for row in candidate], ["E1", "E2", "G12"])
        self.assertEqual(candidate[0][2], candidate[1][2])
        self.assertAlmostEqual(float(candidate[0][2]), 53500.0, delta=1e-6)
        self.assertAlmostEqual(float(candidate[2][2]), 4400.0, delta=1e-6)
        frequencies = panel.table_cells("sw_frequencies")
        self.assertEqual(len(frequencies), 8)
        self.assertEqual(frequencies[0][:3], ["1", "FIT", "7"])
        self.assertEqual(frequencies[0][7], "+0.00%")
        self.assertIn("D-077", panel.sandwich_warnings.text())
        target = folder / "out"
        target.mkdir()
        panel._ask_folder = lambda start: str(target)
        self.assertTrue(panel.sandwich_export_button.isEnabled())
        panel.sandwich_export_button.click()
        self.app.processEvents()
        names = sorted(p.name for p in target.iterdir())
        self.assertEqual([n[:28] for n in names], ["sp13_face_candidate_abaqus_2"] * 2)
        self.assertIn("Exported for Abaqus", panel.sandwich_export_note.text())
        text = next(target.glob("*.txt")).read_text(encoding="utf-8")
        self.assertIn(candidate[0][2] + ", " + candidate[1][2] + ", 6700., 0.05, 0.3, 0.3, " + candidate[2][2] + ", 2200.", text)
        # a role change clears the result: old numbers never stand for new settings
        panel.set_sandwich_role(1, stc.EXCLUDED)
        self.app.processEvents()
        self.assertIsNone(panel.sandwich_result)
        self.assertFalse(panel.sandwich_result_body.isVisible())
        self.assertFalse(panel.sandwich_export_button.isEnabled())
        self.assertTrue(panel.run_sandwich())
        self.assertEqual(panel.table_cells("sw_frequencies")[0][:3], ["1", "EXCLUDED", "7"])  # record 1 is still listed

    def test_a_declared_list_is_used_only_when_selected_and_the_other_is_reported(self):
        sources = _sources(self.folder(), measured(53500.0, 4400.0))
        _window, panel = self.loaded(sources)
        panel.sandwich_declared.setText("1:7, 2:8, 3:9, 4:11, 5:10, 6:12, 7:13, 8:14")
        panel.sandwich_hypothesis.set_value(stc.DECLARED)
        self.app.processEvents()
        self.assertEqual(panel.sandwich_record_cells()[4][0], "FE 11")
        self.assertTrue(panel.run_sandwich())
        self.assertEqual(panel.sandwich_result.selected.hypothesis.key, stc.DECLARED)
        diagnostics = dict(panel.table_cells("sw_diagnostics"))
        self.assertIn("COMPETING SOLUTIONS", diagnostics)
        self.assertTrue(any(key.startswith("Other stated correspondence, NOT selected") for key in diagnostics))
        panel.sandwich_declared.setText("1:7, 2:x")
        self.app.processEvents()
        self.assertIsNone(panel.sandwich_result)
        self.assertTrue(panel.sandwich_declared_note.isVisible())
        self.assertFalse(panel.run_sandwich())
        self.assertIn("Declared list", panel.sandwich_message.text())

    def test_an_unsupported_extrapolation_is_shown_as_a_limit(self):
        sources = _sources(self.folder(), measured(58240.0, 4500.0))
        _window, panel = self.loaded(sources)
        panel.sandwich_hypothesis.set_value(stc.FREQUENCY_ORDER)
        self.assertTrue(panel.run_sandwich())
        self.assertIn("UNSUPPORTED EXTRAPOLATION", panel.sandwich_status.text())
        self.assertIn("NOT a fitted value", panel.table_cells("sw_candidate")[0][4])
        self.assertEqual(panel.table_cells("sw_candidate")[0][2], "54600.0")

    def test_missing_evidence_still_shows_the_sources_and_the_baseline_comparison(self):
        missing = stc.FaceSensitivityEvidence(stc.MISSING, ("the validated FE shape packs are not available (test)",),
                                              ("records pinned (test)",), {"E_in_plane_mpa": E0, "G12_mpa": G0},
                                              dict(BOUNDS), tuple((m, hz) for m, hz, _e, _g in MODES), (), "records")
        sources = _sources(self.folder(), measured(53500.0, 4400.0), ev=missing)
        _window, panel = self.loaded(sources)
        self.assertTrue(panel.sandwich_block.isVisible())
        self.assertIn("FACE_SENSITIVITY_EVIDENCE_MISSING", panel.sandwich_block.text())
        self.assertIn("no response model is assumed", panel.sandwich_block.text())
        self.assertEqual(len(panel.table_cells("sw_fe")), 8)
        self.assertEqual(panel.table_cells("sw_fe")[0][2:], ["—", "—", "no verified sensitivity"])
        panel.sandwich_hypothesis.set_value(stc.FREQUENCY_ORDER)
        self.app.processEvents()
        self.assertEqual(panel.sandwich_record_cells()[2][0], "FE 8")  # the frequency comparison is there
        self.assertTrue(panel.sandwich_record_cells()[2][2].endswith("%"))
        self.assertFalse(panel.sandwich_run_button.isEnabled())
        self.assertFalse(panel.run_sandwich())
        self.assertIsNone(panel.sandwich_result)

    def test_another_measurement_series_is_shown_and_not_calculated(self):
        other = stc.ExperimentalIdentity(stc.OTHER_SERIES, "SP13/best", "the frozen dataset of the accepted fixture (test)")
        sources = _sources(self.folder(), measured(53500.0, 4400.0), identity=other)
        _window, panel = self.loaded(sources)
        self.assertIn("not the target series", panel.sandwich_block.text())
        panel.sandwich_hypothesis.set_value(stc.FREQUENCY_ORDER)
        self.assertFalse(panel.sandwich_run_button.isEnabled())
        self.assertFalse(panel.run_sandwich())

    def test_choosing_another_file_clears_what_was_read(self):
        sources = _sources(self.folder(), measured(53500.0, 4400.0))
        _window, panel = self.loaded(sources)
        panel.sandwich_hypothesis.set_value(stc.FREQUENCY_ORDER)
        self.assertTrue(panel.run_sandwich())
        with mock.patch.object(rm, "read_sources", side_effect=rm.ReadFailed("not a plate (test)")):
            panel.choose_file("unv", sources.unv_path)
            self.wait(panel)
        self.assertIsNone(panel.sandwich)
        self.assertIsNone(panel.sandwich_result)
        self.assertFalse(panel.sandwich_body.isVisible())

    def test_a_failed_reading_is_said_in_the_section(self):
        window, panel = self.window()
        panel.paths.update(inp="a.inp", unv="b.unv")
        panel._refresh()
        with mock.patch.object(rm, "read_sandwich_sources", side_effect=rm.ReadFailed("no curve-fitted modal set")):
            self.assertTrue(panel.read_sandwich())
            self.wait(panel)
        self.assertIn("Not read: no curve-fitted modal set", panel.sandwich_state.text())
        self.assertIsNone(panel.sandwich)

    def test_the_archive_folder_is_passed_to_the_reading(self):
        folder = self.folder()
        sources = _sources(folder, measured(53500.0, 4400.0))
        window, panel = self.window()
        panel.paths.update(inp=sources.model.inp_path, unv=sources.unv_path)
        panel._ask_folder = lambda start: str(folder)
        panel.sandwich_folder_button.click()
        self.assertEqual(panel.sandwich_archive, str(folder))
        with mock.patch.object(rm, "read_sandwich_sources", return_value=sources) as reader:
            self.assertTrue(panel.read_sandwich())
            self.wait(panel)
        self.assertEqual(reader.call_args.args[3], str(folder))


@unittest.skipUnless(REAL_INP.is_file() and REAL_UNV.is_file(), "the SP-13 INP and the ROTATED PolyMAX UNV are not on "
                                                                 "this machine")
class RealSources(unittest.TestCase):
    """Reads read-only copies of the real SP-13 files. Nothing is fitted here: the owner runs any real calculation."""

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp())
        cls.unv = cls.folder / REAL_UNV.name
        cls.inp = cls.folder / REAL_INP.name
        shutil.copyfile(REAL_UNV, cls.unv)
        shutil.copyfile(REAL_INP, cls.inp)
        shutil.copyfile(REAL_INP.with_suffix(".dat"), cls.inp.with_suffix(".dat"))
        for path in cls.folder.iterdir():
            os.chmod(path, stat.S_IREAD)
        archive = REAL_ARCHIVE if (REAL_ARCHIVE / "fe_shapes").is_dir() else None
        cls.archive = archive
        cls.sources = rm.read_sandwich_sources(cls.inp, cls.unv, threading.Event(), archive)

    @classmethod
    def tearDownClass(cls):
        for path in cls.folder.iterdir():
            os.chmod(path, stat.S_IWRITE)
        shutil.rmtree(cls.folder, True)

    def test_the_october_rotated_set_and_the_accepted_fe_model_are_read(self):
        sources = self.sources
        self.assertEqual(sources.unv_sha256, TARGET_SHA)
        self.assertEqual(sources.identity.status, stc.TARGET)
        self.assertEqual(len(sources.records), 12)
        self.assertEqual([record for record, _hz in sources.records], list(range(1, 13)))
        self.assertAlmostEqual(sources.records[0][1], 28.8015, delta=1e-3)
        self.assertAlmostEqual(sources.records[11][1], 267.3612, delta=1e-3)
        self.assertTrue(sources.model.accepted, sources.model.reasons)
        self.assertEqual(len(sources.fe_modes), 24)
        self.assertEqual(sources.fe_modes[0], (7, 22.489444732666016))
        self.assertEqual(sources.fe_modes[-1][0], 30)
        self.assertEqual(len(sources.model.dat_rows), 24)

    def test_the_baseline_comparison_is_under_the_stated_rank_only(self):
        sources = self.sources
        self.assertEqual(rm.sandwich_record_texts(sources, None)[1], ("select a correspondence", "", ""))
        stated, problem = rm.sandwich_hypotheses(sources, "")
        self.assertEqual((len(stated), problem), (1, ""))
        texts = rm.sandwich_record_texts(sources, stated[0])
        self.assertEqual(texts[1][0], "FE 7")  # record 1 is kept, against the lowest elastic FE mode
        self.assertEqual(texts[12][0], "FE 18")
        self.assertEqual(texts[1][2], f"{(22.489444732666016 - sources.records[0][1]) / sources.records[0][1]:+.2%}")
        self.assertEqual(len(rm.sandwich_fe_rows(sources)), 24)

    def test_the_copies_are_unchanged(self):
        self.assertEqual(_sha(self.unv), TARGET_SHA)
        self.assertEqual(_sha(self.inp), "9d4105840e527354dbd0bb4d0d0012f7708125aa94619b0dcc486fd76dc70571")
        self.assertEqual(_sha(REAL_UNV), TARGET_SHA)

    def test_with_the_archive_the_trial_is_ready_and_without_it_the_diagnosis_is_given(self):
        if self.archive is None:
            self.assertEqual(self.sources.evidence.status, stc.MISSING)
            self.assertIn("FACE_SENSITIVITY_EVIDENCE_MISSING", rm.sandwich_blocked(self.sources))
            return
        self.assertEqual(self.sources.evidence.status, stc.VERIFIED, self.sources.evidence.reasons)
        self.assertTrue(self.sources.usable, self.sources.binding_reasons)
        self.assertEqual(rm.sandwich_blocked(self.sources), "")
        self.assertTrue(any("prints the accepted baseline frequencies of all 24" in t for t in self.sources.binding_checks))
        missing = rm.read_sandwich_sources(self.inp, self.unv, threading.Event(), str(self.folder))
        self.assertEqual(missing.evidence.status, stc.MISSING)
        self.assertIn("no response model is assumed", rm.sandwich_blocked(missing))
        self.assertEqual(len(missing.fe_modes), 24)  # the baseline comparison is still available


if __name__ == "__main__":
    unittest.main()
