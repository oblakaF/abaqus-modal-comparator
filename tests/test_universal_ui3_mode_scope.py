"""UNIVERSAL-UI-3: one mode scope for Analyze; the full read data are used only to verify sources and the registration."""

from __future__ import annotations

import threading
import unittest
from unittest import mock

import numpy as np

from test_new_gui6_workbench import _Comparison
from test_universal_two_file_analysis import _Case, plate_nodes, write_shape_package

from modal_core import ModalDataset, ModeShape, compare_modal_datasets
from new_gui import analyze_model as am
from new_gui import comparison_model as cm
from new_gui import registration_check_model as rm
from new_gui.preview_model import file_identity
from new_gui.workspace_state import EXPERIMENTAL, FE
from services import new_odb_comparison as service

COMPETED_FE, COMPETED_RECORD = 11, 5  # EXP5 belongs to FE 11 in the scope; FE 21 beats it outside the scope
OUTSIDE_FE = 21
COMPETED_BY_RECORD_FE, OUTSIDE_RECORD, OWN_RECORD = 12, 21, 6  # FE 12 belongs to EXP6; EXP21 beats it outside the scope


def fe_hz(number: int) -> float:
    return 100.0 * 1.3 ** (number - 7)


def record_hz(number: int) -> float:
    """Each record 2 % from its own FE mode, number + 6 (the first elastic mode is 7)."""
    return fe_hz(number + 6) * 1.02


def shape(coordinates, seed: int) -> np.ndarray:
    random = np.random.default_rng(seed)
    x, y = coordinates[:, 0] / 10.0, coordinates[:, 1] / 10.0
    vectors = np.zeros((len(coordinates), 3))
    vectors[:, 2] = (np.cos(random.uniform(0.5, 4.0) * x + random.uniform(0.5, 4.0) * y + random.uniform(0, 3))
                     + 0.6 * random.standard_normal(len(coordinates)))
    return vectors


def rigid_shape(coordinates, index: int) -> np.ndarray:
    centred = coordinates - coordinates.mean(axis=0)
    vectors = np.zeros_like(centred)
    if index < 3:
        vectors[:, index] = 1.0
        return vectors
    axis = np.zeros(3)
    axis[index - 3] = 1.0
    return np.cross(axis, centred)


def thirty_fe_modes(base: ModalDataset) -> ModalDataset:
    """Six rigid-body modes, then elastic modes up to 30, on the registered mesh; FE 21 competes for EXP5."""
    first = base.sorted_modes()[0]
    coordinates = first.coordinates
    modes = [ModeShape(n + 1, 0.001 + 0.001 * n, first.node_ids, coordinates, rigid_shape(coordinates, n))
             for n in range(6)]
    for number in range(7, 31):
        vectors = shape(coordinates, number)
        vectors[11] = vectors[5]
        modes.append(ModeShape(number, fe_hz(number), first.node_ids, coordinates, vectors))
    competing = modes[OUTSIDE_FE - 1]
    modes[OUTSIDE_FE - 1] = ModeShape(OUTSIDE_FE, record_hz(COMPETED_RECORD) * 0.999, first.node_ids, coordinates,
                                      competing.vectors)
    return ModalDataset("FE", base.source_path, modes, metadata=dict(base.metadata))


def twenty_five_records(unv, fe: ModalDataset, accepted: ModalDataset) -> ModalDataset:
    """25 records on the frozen points. Each is its FE mode's U3 at FE nodes 1-6, except the two competed ones."""
    reference = accepted.sorted_modes()[0]
    shapes = {mode.number: mode.vectors[:6, 2] for mode in fe.modes}
    count = len(reference.node_ids)

    def record(number: int, hz: float, values) -> ModeShape:
        vectors = np.zeros((count, 3), dtype=complex)
        vectors[:, 2] = values
        return ModeShape(number, hz, reference.node_ids, reference.coordinates, vectors)

    modes = [record(n, record_hz(n), shapes.get(n + 6, shape(reference.coordinates, 100 + n)[:, 2]))
             for n in range(1, 26)]
    # EXP5 lies between FE 11 (its own, 2 % away) and FE 21 (0.1 % away, and more like it)
    modes[COMPETED_RECORD - 1] = record(COMPETED_RECORD, record_hz(COMPETED_RECORD),
                                        0.55 * shapes[COMPETED_FE] + 0.85 * shapes[OUTSIDE_FE])
    # FE 12 is close to EXP6 (its own, 2 % away, not exactly its shape) and identical to EXP21 (0.1 % away)
    modes[OWN_RECORD - 1] = record(OWN_RECORD, record_hz(OWN_RECORD),
                                   0.9 * shapes[COMPETED_BY_RECORD_FE] + 0.5 * shapes[COMPETED_FE])
    modes[OUTSIDE_RECORD - 1] = record(OUTSIDE_RECORD, fe_hz(COMPETED_BY_RECORD_FE) * 1.001,
                                       shapes[COMPETED_BY_RECORD_FE])
    return ModalDataset("PolyMAX", unv, modes, metadata=dict(accepted.metadata))


class _Scope(_Comparison):
    def setUp(self):
        super().setUp()
        accepted = self.exp_preview.sets[0].dataset
        self.full_fe = thirty_fe_modes(self.fe)
        self.full_exp = twenty_five_records(self.unv, self.full_fe, accepted)
        # The world pins the 4 records of its accepted set: the replay of that contract sees those records and records
        # what it was given. Every other check of the registration is the service's own.
        self.verified_counts = []
        real = service.verify_fixture_dataset

        def replay(fixture, registration, dataset):
            self.verified_counts.append(len(dataset.modes))
            return real(fixture, registration, accepted)

        patcher = mock.patch.object(service, "verify_fixture_dataset", side_effect=replay)
        patcher.start()
        self.addCleanup(patcher.stop)
        fe_prev, exp_prev = self.previews(self.full_fe, datasets=[self.full_exp])
        self.identities = dict(self.sources)
        self.inputs = am.scoped_inputs(fe_prev, exp_prev, self.identities)

    def analyse(self):
        return am.analyse(self.inputs, 0, threading.Event())


class ScopeOfTheDataTests(_Scope):
    def test_subsets_hold_modes_1_to_20_and_records_1_to_20(self):
        self.assertEqual([m.number for m in self.inputs.fe.modes], list(range(1, 21)))
        self.assertEqual([m.number for m in self.inputs.fe.dataset.modes], list(range(1, 21)))
        chosen = self.inputs.experimental.sets[0]
        self.assertEqual([r.number for r in chosen.records], list(range(1, 21)))
        self.assertEqual([m.number for m in chosen.dataset.modes], list(range(1, 21)))

    def test_the_read_data_stay_whole(self):
        self.assertEqual(len(self.inputs.full_fe.modes), 30)
        self.assertEqual(len(self.inputs.full_experimental.sets[0].records), 25)
        self.assertEqual(len(self.full_fe.modes), 30)
        self.assertIs(self.inputs.full_fe.dataset, self.full_fe)

    def test_the_subsets_cannot_be_written(self):
        fe = self.inputs.fe.dataset
        self.assertIsInstance(fe.modes, tuple)
        with self.assertRaises(ValueError):
            fe.modes[0].vectors[0, 0] = 1.0
        with self.assertRaises(ValueError):
            fe.modes[0].coordinates[0, 0] = 1.0
        with self.assertRaises(TypeError):
            fe.modes[0].metadata["x"] = 1
        fe.metadata["cache of a service"] = 1  # the dataset's own dict never reaches the read data
        self.assertNotIn("cache of a service", self.full_fe.metadata)
        self.assertTrue(self.full_fe.modes[0].vectors.flags.writeable)  # the read data keep their own flags

    def test_a_missing_low_mode_is_never_replaced_by_a_higher_one(self):
        modes = [m for m in self.full_fe.modes if m.number not in (1, 2)]
        reduced = ModalDataset("FE", self.full_fe.source_path, modes, metadata=dict(self.full_fe.metadata))
        fe_prev, exp_prev = self.previews(reduced, datasets=[self.full_exp])
        inputs = am.scoped_inputs(fe_prev, exp_prev, self.identities)
        self.assertEqual([m.number for m in inputs.fe.modes], list(range(3, 21)))

    def test_results_outside_the_requested_range_are_refused(self):
        modes = [m for m in self.full_fe.modes if m.number > 20]
        outside = ModalDataset("FE", self.full_fe.source_path, modes, metadata=dict(self.full_fe.metadata))
        fe_prev, exp_prev = self.previews(outside, datasets=[self.full_exp])
        with self.assertRaises(am.StepFailed):
            am.scoped_inputs(fe_prev, exp_prev, self.identities)


class ValidRegistrationTests(_Scope):
    def test_the_comparison_on_the_full_data_would_pair_the_competitors(self):
        """The control: without the scope the competitors win, so the tests below can tell the difference."""
        bound = rm.check(self.inputs.full_fe, self.inputs.full_experimental, 0)
        result = compare_modal_datasets(self.full_fe, self.full_exp, frozen_registration=bound.registration)
        pairs = {(int(p.abaqus_mode), int(p.experimental_mode)) for p in result.pairs}
        self.assertIn((OUTSIDE_FE, COMPETED_RECORD), pairs)
        self.assertIn((COMPETED_BY_RECORD_FE, OUTSIDE_RECORD), pairs)

    def test_the_registration_and_identities_are_verified_on_the_full_data(self):
        seen = []
        real = rm.check

        def recording(fe, experimental, set_index, cancel=None):
            seen.append((len(fe.dataset.modes), len(experimental.sets[set_index].dataset.modes)))
            return real(fe, experimental, set_index, cancel)

        with mock.patch.object(rm, "check", side_effect=recording):
            analysis = self.analyse()
        self.assertEqual(analysis.status, cm.PAIRS_FOUND, analysis.registration_reason)
        self.assertEqual(set(seen), {(30, 25)})
        self.assertEqual(set(self.verified_counts), {25})

    def test_no_mode_outside_the_scope_reaches_any_result(self):
        analysis = self.analyse()
        view = analysis.comparison
        self.assertIsNotNone(view, analysis.registration_reason)
        self.assertTrue(view.pair_rows)
        self.assertLessEqual(max(row.abaqus_mode for row in view.pair_rows), 20)
        self.assertLessEqual(max(row.experimental_mode for row in view.pair_rows), 20)
        self.assertLessEqual(max(view.mac_fe_modes), 20)
        self.assertLessEqual(max(view.mac_experimental_modes), 20)
        self.assertEqual(len(view.mac_experimental_modes), 20)
        self.assertEqual(len(view.mac_cells), 14)  # the elastic modes 7-20
        self.assertEqual({int(row[1]) for row in analysis.nearest_rows}, set(range(1, 21)))
        self.assertLessEqual(max(int(row[3]) for row in analysis.nearest_rows), 20)
        self.assertEqual([row[0] for row in analysis.fe_rows], [str(n) for n in range(1, 21)])
        self.assertEqual(len(analysis.experimental_rows), 20)
        self.assertEqual(len(view.unpaired_experimental), 20 - len(view.pair_rows))

    def test_the_competing_modes_do_not_change_the_displayed_assignment(self):
        pairs = {(row.abaqus_mode, row.experimental_mode) for row in self.analyse().comparison.pair_rows}
        self.assertIn((COMPETED_FE, COMPETED_RECORD), pairs)
        self.assertIn((COMPETED_BY_RECORD_FE, OWN_RECORD), pairs)

    def test_the_assignment_equals_that_of_data_holding_only_the_first_twenty(self):
        bound = rm.check(self.inputs.full_fe, self.inputs.full_experimental, 0)
        fe = ModalDataset("FE", self.full_fe.source_path, [m for m in self.full_fe.modes if m.number <= 20],
                          metadata=dict(self.full_fe.metadata))
        exp = ModalDataset("PolyMAX", self.unv, self.full_exp.modes[:20], metadata=dict(self.full_exp.metadata))
        alone = compare_modal_datasets(fe, exp, frozen_registration=bound.registration)
        expected = {(int(p.abaqus_mode), int(p.experimental_mode), round(float(p.mac), 9)) for p in alone.pairs}
        shown = {(r.abaqus_mode, r.experimental_mode, round(float(r.mac), 9))
                 for r in self.analyse().comparison.pair_rows}
        self.assertEqual(shown, expected)

    def test_rigid_body_classification_and_the_first_elastic_mode_are_preserved(self):
        analysis = self.analyse()
        self.assertEqual(analysis.rigid_modes, (1, 2, 3, 4, 5, 6))
        self.assertEqual(analysis.first_elastic, "7")
        self.assertEqual({row[0] for row in analysis.comparison.rigid_rows}, {str(n) for n in range(1, 7)})
        self.assertEqual(analysis.experimental_rows[0][:2], ("EXP1", "1"))
        self.assertIn(1, {row.experimental_mode for row in analysis.comparison.pair_rows})
        self.assertIn(7, {row.abaqus_mode for row in analysis.comparison.pair_rows})

    def test_the_read_data_are_unchanged_after_the_analysis(self):
        vectors = self.full_fe.modes[6].vectors.copy()
        self.analyse()
        np.testing.assert_array_equal(self.full_fe.modes[6].vectors, vectors)
        self.assertEqual(len(self.full_exp.modes), 25)

    def test_the_counts_are_reported(self):
        analysis = self.analyse()
        self.assertIn("20 of 20 requested modes", analysis.summary)
        self.assertIn("20 of 25 records analyzed", analysis.summary)
        self.assertIn("loaded 20 (1-20)", analysis.facts[0])
        self.assertIn("20 of 25 record(s) analyzed", analysis.facts[1])
        self.assertIn("not analyzed: 21-30", analysis.facts[2])
        self.assertIn("after EXP20, not analyzed: 5", analysis.facts[3])
        self.assertEqual(analysis.unavailable_fe, ())

    def test_a_foreign_scope_is_refused_before_the_comparator(self):
        other = am.scoped_fe(self.previews(thirty_fe_modes(self.fe), datasets=[self.full_exp])[0])
        foreign = am.replace(other.dataset)
        foreign.modes = tuple(am._read_only(ModeShape(m.number, m.frequency_hz * 1.5, m.node_ids, m.coordinates,
                                                      m.vectors)) for m in other.dataset.modes)
        with mock.patch("modal_core.compare_modal_datasets", side_effect=AssertionError("no comparator")):
            outcome = cm.run_compare(self.inputs.full_fe, self.inputs.full_experimental, 0, self.registration, 1,
                                     threading.Event(), self.identities,
                                     scope=(am.replace(other, dataset=foreign), self.inputs.experimental))
        self.assertIn("not modes of the verified data", outcome.refusal)


class AcceptedSetTests(_Comparison):
    """No replacement: the world's accepted set, whose pinned record count passes only on the whole set."""

    def test_the_unchanged_route_verifies_and_compares(self):
        inputs = am.scoped_inputs(self.fe_preview, self.exp_preview, dict(self.sources))
        analysis = am.analyse(inputs, 0, threading.Event())
        self.assertEqual(analysis.status, cm.PAIRS_FOUND, analysis.registration_reason)

    def test_a_shortened_set_would_not_verify(self):
        shortened = ModalDataset("PolyMAX", self.unv, self.exp_preview.sets[0].dataset.modes[:2],
                                 metadata=dict(self.exp_preview.sets[0].dataset.metadata))
        fe_prev, exp_prev = self.previews(datasets=[shortened])
        with self.assertRaisesRegex(ValueError, "mode_count"):
            rm.check(fe_prev, exp_prev, 0)


class UnavailableModesTests(_Scope):
    def reduced(self, kept):
        modes = [m for m in self.full_fe.modes if m.number in kept]
        dataset = ModalDataset("FE", self.full_fe.source_path, modes, metadata=dict(self.full_fe.metadata))
        fe_prev, exp_prev = self.previews(dataset, datasets=[self.full_exp])
        return am.analyse(am.scoped_inputs(fe_prev, exp_prev, self.identities), 0, threading.Event())

    def test_missing_high_modes_are_reported_with_the_actual_count(self):
        analysis = self.reduced(range(1, 13))
        self.assertEqual(analysis.unavailable_fe, tuple(range(13, 21)))
        self.assertIn("12 of 20 requested modes", analysis.summary)
        self.assertIn("Unavailable: 13-20.", analysis.summary)
        self.assertIn("Requested FE modes not available in the results: 13-20.", analysis.notes)

    def test_missing_low_modes_are_reported_and_the_first_elastic_mode_stays(self):
        analysis = self.reduced(range(3, 21))
        self.assertEqual(analysis.unavailable_fe, (1, 2))
        self.assertIn("Unavailable: 1-2.", analysis.summary)
        self.assertEqual(analysis.first_elastic, "7")


class MissingRegistrationTests(_Case):
    def read_data(self, count=25):
        nodes = plate_nodes()
        modes = [(n, 10.0 * n, np.random.default_rng(n).standard_normal((len(nodes), 3))) for n in range(1, 31)]
        manifest = write_shape_package(self.root / "package", nodes, modes)
        unv = self.unv(nodes, [10.5 * k for k in range(1, count + 1)])
        return am.read_inputs(manifest, unv, threading.Event())

    def test_frequency_only_on_the_same_scope_and_no_mac(self):
        inputs = self.read_data()
        with mock.patch.object(cm, "run_compare", side_effect=AssertionError("no comparison")):
            analysis = am.analyse(inputs, 0, threading.Event())
        self.assertEqual(analysis.status, am.REGISTRATION_REQUIRED)
        self.assertIsNone(analysis.comparison)
        self.assertEqual(len(analysis.fe_rows), 20)
        self.assertEqual(len(analysis.nearest_rows), 20)
        self.assertLessEqual(max(int(row[3]) for row in analysis.nearest_rows), 20)
        self.assertIn("20 of 25 records analyzed", analysis.summary)
        self.assertEqual(am.NEAREST_HEADERS.count("MAC"), 0)

    def test_the_registration_is_checked_on_the_full_data(self):
        inputs = self.read_data()
        with mock.patch.object(rm, "run_check", return_value=rm.RegistrationOutcome(0, refusal="no")) as check:
            am.analyse(inputs, 0, threading.Event())
        self.assertIs(check.call_args.args[0], inputs.full_fe)
        self.assertIs(check.call_args.args[1], inputs.full_experimental)

    def test_a_short_experimental_file_reports_its_actual_count(self):
        analysis = am.analyse(self.read_data(3), 0, threading.Event())
        self.assertIn("3 of 3 records analyzed", analysis.summary)
        self.assertEqual(len(analysis.nearest_rows), 3)

    def test_the_shape_choices_follow_the_scope(self):
        nodes = plate_nodes()
        panel = self.panel(experimental=self.unv(nodes, [10.5 * k for k in range(1, 26)]))
        self.run_analysis(panel)
        panel.show_candidate(19)
        self.wait(panel)
        self.assertEqual(panel.shape_panels[EXPERIMENTAL].item_combo.count(), 21)  # the prompt and EXP1-EXP20
        self.assertEqual(panel.shape_panels[FE].item_combo.count(), 21)


class StaleInputTests(_Case):
    def read_data(self):
        nodes = plate_nodes()
        modes = [(n, 10.0 * n, np.random.default_rng(n).standard_normal((len(nodes), 3))) for n in range(1, 26)]
        self.manifest = write_shape_package(self.root / "package", nodes, modes)
        self.source = self.unv(nodes, [10.5 * k for k in range(1, 26)])
        return am.read_inputs(self.manifest, self.source, threading.Event())

    def assert_stale(self, inputs):
        with mock.patch.object(rm, "run_check", side_effect=AssertionError("nothing is verified on stale data")), \
                mock.patch.object(am.dm, "run_diagnostic", side_effect=AssertionError("nothing is computed")):
            with self.assertRaises(am.StepFailed) as raised:
                am.analyse(inputs, 0, threading.Event())
        self.assertEqual(str(raised.exception), am.STALE_TEXT)

    def test_a_changed_experimental_file_stops_everything(self):
        inputs = self.read_data()
        self.source.write_bytes(self.source.read_bytes() + b"\n")
        self.assert_stale(inputs)

    def test_a_missing_experimental_file_stops_everything(self):
        inputs = self.read_data()
        self.source.unlink()
        self.assert_stale(inputs)

    def test_a_changed_fe_package_stops_everything(self):
        inputs = self.read_data()
        mode_file = next(self.manifest.parent.glob("mode_*.csv"))
        mode_file.write_bytes(mode_file.read_bytes() + b"\n")
        self.assert_stale(inputs)

    def test_an_unconfirmed_read_stops_everything(self):
        inputs = self.read_data()
        self.assert_stale(am.replace(inputs, identities={**inputs.identities, "experimental": None}))

    def test_a_cancelled_confirmation_is_a_cancellation(self):
        inputs = self.read_data()
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(am.StepCancelled):
            am.analyse(inputs, 0, cancel)

    def test_the_identity_check_uses_the_files_now(self):
        inputs = self.read_data()
        self.assertEqual(file_identity(self.source)["sha256"], inputs.identities["experimental"]["sha256"])
        am.confirm_sources(inputs, threading.Event())


if __name__ == "__main__":
    unittest.main()
