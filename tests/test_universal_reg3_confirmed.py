"""UNIVERSAL-REG-3: two files, independent evidence, explicit confirmation, then pairs and MAC. Standalone synthetic data."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
import threading
import unittest
from unittest import mock

import numpy as np

import test_universal_two_file_analysis as base
import test_universal_reg1_registration as reg1
from test_universal_ui2_clean import FORBIDDEN, shown_text

from PySide6.QtWidgets import QCheckBox, QLabel, QPushButton

from domain.registration import FrozenRegistration
from domain.specimen_manifest import canonical_hash
import modal_core
from new_gui import analyze_model as am
from new_gui import comparison_model as cm
from new_gui import production_window as pw
from new_gui import registration_check_model as rm
from new_gui.analyze_panel import (COMPARE_CONFIRMED, DONE, OPEN_CONFIRMATION, READY_TEXT, RUNNING, UNUSABLE_TEXT,
                                   BLOCKED)
from new_gui.workspace_state import EXPERIMENTAL, FE
from services import confirmed_registration as cs
from services import generic_registration as gr
from services import new_odb_comparison as archived

ROOT = Path(__file__).resolve().parents[1]
RECORDS = 5
FIRST_ELASTIC = 7


def z_shape(count: int, k: int) -> np.ndarray:
    return np.random.default_rng(100 + k).standard_normal(count).astype(complex)


def fe_modes(nodes, sign=1.0, count=25):
    """Rigid modes 1-6, then elastic modes whose U3 is exactly experimental record k's shape, 2.4 % below it."""
    points = np.array([n[1:4] for n in nodes], dtype=float)
    rigid = base.rigid_shapes(nodes)
    modes = [(i + 1, 0.0011 + 0.0001 * i, shape) for i, shape in enumerate(rigid)]
    first = len(rigid) + 1
    for number in range(first, count + 1):
        k = number - first
        vectors = np.zeros_like(points)
        vectors[:, 2] = sign * z_shape(len(points), k).real
        modes.append((number, record_hz(k) * 0.976 if k < RECORDS else 5000.0 + 50.0 * number, vectors))
    return modes


def record_hz(k: int) -> float:
    return 50.0 * 1.5 ** k


def freqs(count=RECORDS):
    return tuple(record_hz(k) for k in range(count))


class _Flow(base._Case):
    nodes = staticmethod(base.plate_nodes)

    def window(self):
        nodes = self.nodes()
        self.runner = base.Runner(nodes, self.modes())
        window = pw.ProductionWindow(analyze_options={"runner": self.runner, "discover": base.FOUND,
                                                      "consent": self.consent})
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        window.show()
        return window

    def modes(self):
        return fe_modes(self.nodes())

    def analysed(self, frequencies=None, unv=None):
        window = self.window()
        panel = window.analyze
        panel.choose_file(FE, str(self.odb))
        self.exp_path = unv or self.unv(self.nodes(), frequencies or freqs())
        panel.choose_file(EXPERIMENTAL, str(self.exp_path))
        self.run_analysis(panel)
        self.assertEqual(panel.state, DONE, panel.message.text())
        self.assertEqual(panel.analysis.status, am.REGISTRATION_REQUIRED)
        return window, panel

    def state_evidence(self, dialog, panel, axes=("+X", "+Y", "+Z")):
        fe = panel.inputs.full_fe.dataset.modes[0]
        experimental = panel.inputs.full_experimental.sets[0].dataset.modes[0]
        for combo, value in ((dialog.fe_unit, "m"), (dialog.experimental_unit, "m"), (dialog.side, "+Z")):
            combo.setCurrentIndex(combo.findData(value))
        for combo, value in zip(dialog.axes, axes):
            combo.setCurrentIndex(combo.findData(value))
        dialog.dofs["z"].setChecked(True)
        dialog.landmarks.setPlainText(f"{experimental.node_ids[0]}, {fe.node_ids[0]}\n"
                                      f"{experimental.node_ids[-1]}, {fe.node_ids[-1]}")
        dialog.source.setText("marker photograph and measurement drawing")

    def draft(self, panel, name="draft.json"):
        """Evidence stated, checked, reviewed and saved: the state before the confirmation."""
        dialog = panel.open_registration()
        self.state_evidence(dialog, panel)
        self.assertTrue(dialog.check())
        self.wait(panel)
        self.assertEqual(dialog.proposal.status, gr.REGISTRATION_PROPOSED, dialog.proposal.problems)
        dialog.review_box.setChecked(True)
        self.draft_path = self.root / name
        self.assertTrue(dialog.save_draft(str(self.draft_path)))
        self.wait(panel)
        self.assertTrue(self.draft_path.is_file(), dialog.draft_note.text())
        return dialog

    def confirmation_dialog(self, dialog, panel):
        self.assertTrue(dialog.confirm_registration())
        self.wait(panel)
        self.assertIsNotNone(dialog.confirmation_dialog)
        return dialog.confirmation_dialog

    def sign(self, confirming, name="confirmation.json"):
        for box in confirming.boxes.values():
            box.setChecked(True)
        confirming.name.setText("A. Tester")
        confirming.location.setText("laboratory notebook 7, page 12")
        self.confirmation_path = self.root / name
        self.assertTrue(confirming.confirm(str(self.confirmation_path)))

    def confirmed(self, panel):
        dialog = self.draft(panel)
        confirming = self.confirmation_dialog(dialog, panel)
        self.sign(confirming)
        self.wait(panel)
        self.assertTrue(self.confirmation_path.is_file(), confirming.message.text())
        return dialog, confirming

    def compare(self, panel):
        self.assertTrue(panel.compare_confirmed())
        self.wait(panel)
        return panel.analysis

    def assert_frequency_only(self, panel):
        self.assertEqual(panel.analysis.status, am.REGISTRATION_REQUIRED)
        self.assertIsNone(panel.analysis.comparison)
        self.assertNotIn("pairs", panel.tables)
        self.assertNotIn("mac", panel.tables)
        self.assertTrue(panel.tables["nearest"].rowCount())


class PlateWorkflowTests(_Flow):
    def test_the_whole_workflow_gives_pairs_mac_errors_and_shapes(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        self.assertEqual(panel.compare_button.text(), COMPARE_CONFIRMED)
        self.assertFalse(panel.compare_button.isHidden())
        self.assertEqual(panel.proposal_label.text(), READY_TEXT)
        analysis = self.compare(panel)
        self.assertEqual(analysis.status, am.CONFIRMED_COMPARISON, analysis.registration_reason)
        self.assertEqual(panel.status_label.text(), am.CONFIRMED_COMPARISON)
        view = analysis.comparison
        self.assertEqual([(r.abaqus_mode, r.experimental_mode) for r in view.pair_rows],
                         [(FIRST_ELASTIC + k, k + 1) for k in range(RECORDS)])
        for row in view.pair_rows:
            self.assertGreater(row.mac, 0.999)
            self.assertAlmostEqual(row.frequency_error_percent, -2.4, places=2)
        self.assertEqual(panel.tables["pairs"].rowCount(), RECORDS)
        self.assertTrue(panel.tables["mac"].rowCount())
        self.assertEqual(panel.tables["pairs"].item(0, 6).text(), "1.000")
        self.assertEqual(panel.shape_panels[EXPERIMENTAL].slot.state, "shown")
        self.assertEqual(panel.shape_panels[FE].slot.state, "shown")
        self.assertTrue(panel.show_pair(2))
        self.wait(panel)
        self.assertEqual(panel.shape_panels[EXPERIMENTAL].chosen_index(), 2)
        self.assertEqual(panel.inputs.fe.modes[panel.shape_panels[FE].chosen_index()].number, FIRST_ELASTIC + 2)

    def test_the_statement_says_what_a_confirmation_is(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        analysis = self.compare(panel)
        self.assertIn("not independent proof", analysis.statement)
        self.assertTrue(any("not proof of physical correctness" in note for note in analysis.notes))
        self.assertNotEqual(panel.status_label.property("state"), "read")  # never shown as verified

    def test_experimental_mode_1_the_first_elastic_mode_and_rigid_modes_stay(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        analysis = self.compare(panel)
        self.assertEqual(analysis.rigid_modes, tuple(range(1, FIRST_ELASTIC)))
        self.assertEqual(analysis.first_elastic, str(FIRST_ELASTIC))
        first = analysis.comparison.pair_rows[0]
        self.assertEqual((first.abaqus_mode, first.experimental_mode), (FIRST_ELASTIC, 1))
        self.assertEqual({row[0] for row in analysis.comparison.rigid_rows}, {str(n) for n in range(1, FIRST_ELASTIC)})

    def test_the_comparator_receives_the_frozen_registration_of_the_confirmed_mapping(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        real = modal_core.compare_modal_datasets
        with mock.patch.object(modal_core, "compare_modal_datasets", side_effect=real) as comparator:
            self.compare(panel)
        comparator.assert_called_once()
        registration = comparator.call_args.kwargs["frozen_registration"]
        self.assertIsInstance(registration, FrozenRegistration)
        document = json.loads(self.confirmation_path.read_text(encoding="utf-8"))
        self.assertEqual(registration.registration_hash, document["registration_hash"])
        self.assertEqual(comparator.call_args.args[0].modes[0].number, 1)
        self.assertEqual(len(comparator.call_args.args[0].modes), 20)

    def test_the_first_twenty_scope_applies_to_the_comparison(self):
        nodes = self.nodes()
        _window, panel = self.analysed(tuple(record_hz(0) * 1.03 ** k for k in range(25)))
        self.assertEqual(len(panel.inputs.full_experimental.sets[0].records), 25)
        self.confirmed(panel)
        analysis = self.compare(panel)
        self.assertIsNotNone(analysis.comparison, analysis.registration_reason)
        self.assertEqual(len(analysis.comparison.mac_experimental_modes), 20)
        self.assertLessEqual(max(analysis.comparison.mac_fe_modes), 20)
        self.assertEqual(len(nodes), 25)

    def test_the_archived_registrations_are_never_consulted(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        with mock.patch.object(rm, "run_check", side_effect=AssertionError("no archived check")), \
                mock.patch.object(rm, "check", side_effect=AssertionError("no archived check")), \
                mock.patch.object(archived, "bind_registration_by_fe_geometry",
                                  side_effect=AssertionError("no archived registration")):
            analysis = self.compare(panel)
        self.assertEqual(analysis.status, am.CONFIRMED_COMPARISON)

    def test_a_scan_in_another_frame_is_transformed_by_the_stated_evidence(self):
        """Exp +x = FE -X and exp +z = FE -Z: positions and signs come from the statement."""
        nodes = self.nodes()
        turned = [(n[0], -n[1], n[2], -n[3]) for n in nodes]
        unv = base.write_unv(self.inputs / "turned.unv", turned, freqs())
        window = self.window()
        panel = window.analyze
        self.exp_path = unv
        panel.choose_file(FE, str(self.odb))
        panel.choose_file(EXPERIMENTAL, str(unv))
        self.run_analysis(panel)
        dialog = panel.open_registration()
        self.state_evidence(dialog, panel, axes=("-X", "+Y", "-Z"))
        self.assertTrue(dialog.check())
        self.wait(panel)
        self.assertTrue(dialog.proposal.proposed, dialog.proposal.problems)
        dialog.review_box.setChecked(True)
        self.draft_path = self.root / "d.json"
        dialog.save_draft(str(self.draft_path))
        self.wait(panel)
        confirming = self.confirmation_dialog(dialog, panel)
        self.sign(confirming)
        self.wait(panel)
        analysis = self.compare(panel)
        self.assertEqual(analysis.status, am.CONFIRMED_COMPARISON, analysis.registration_reason)
        self.assertEqual([r.experimental_mode for r in analysis.comparison.pair_rows], list(range(1, RECORDS + 1)))
        self.assertTrue(all(r.mac > 0.999 for r in analysis.comparison.pair_rows))

    def test_a_measured_direction_along_another_fe_axis_uses_the_stated_rotation(self):
        """Exp +z = FE +Y and exp +y = FE -Z: only the correct rotation brings FE U2 onto the measured component."""
        nodes = self.nodes()
        modes = [(number, hz, vectors[:, [0, 2, 1]]) if number >= FIRST_ELASTIC else (number, hz, vectors)
                 for number, hz, vectors in fe_modes(nodes)]
        turned = [(n[0], n[1], 0.0, n[2]) for n in nodes]  # x stays; FE Y lies along exp +z; the plate has no exp y
        unv = base.write_unv(self.inputs / "turned.unv", turned, freqs())
        window = pw.ProductionWindow(analyze_options={"runner": base.Runner(nodes, modes), "discover": base.FOUND,
                                                      "consent": self.consent})
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        panel = window.analyze
        self.exp_path = unv
        panel.choose_file(FE, str(self.odb))
        panel.choose_file(EXPERIMENTAL, str(unv))
        self.run_analysis(panel)
        dialog = panel.open_registration()
        self.state_evidence(dialog, panel, axes=("+X", "-Z", "+Y"))
        self.assertTrue(dialog.check())
        self.wait(panel)
        self.assertTrue(dialog.proposal.proposed, dialog.proposal.problems)
        self.assertEqual(dialog.proposal.axes_in_fe, ("+X", "-Z", "+Y"))
        dialog.review_box.setChecked(True)
        self.draft_path = self.root / "d.json"
        dialog.save_draft(str(self.draft_path))
        self.wait(panel)
        self.sign(self.confirmation_dialog(dialog, panel))
        self.wait(panel)
        real = modal_core.compare_modal_datasets
        seen = []

        def spy(fe, experimental, **kwargs):
            seen.append(real(fe, experimental, **kwargs))
            return seen[-1]

        with mock.patch.object(modal_core, "compare_modal_datasets", side_effect=spy):
            analysis = self.compare(panel)
        self.assertEqual(analysis.status, am.CONFIRMED_COMPARISON, analysis.registration_reason)
        self.assertLess(float(np.max(seen[0].geometry.distances)), 1.0e-9)
        self.assertEqual([r.experimental_mode for r in analysis.comparison.pair_rows], list(range(1, RECORDS + 1)))
        self.assertTrue(all(r.mac > 0.999 for r in analysis.comparison.pair_rows))

    def test_the_geometry_given_to_the_comparator_places_each_point_on_its_node(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        real = modal_core.compare_modal_datasets
        seen = []

        def spy(fe, experimental, **kwargs):
            result = real(fe, experimental, **kwargs)
            seen.append(result)
            return result

        with mock.patch.object(modal_core, "compare_modal_datasets", side_effect=spy):
            self.compare(panel)
        self.assertEqual(seen[0].metadata["orientation_source"], "frozen_registration")
        self.assertLess(float(np.max(seen[0].geometry.distances)), 1.0e-9)
        self.assertEqual(float(seen[0].geometry.matched_fraction), 1.0)


class BeamWorkflowTests(_Flow):
    nodes = staticmethod(base.beam_nodes)

    def test_a_beam_reaches_the_comparison(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        analysis = self.compare(panel)
        self.assertIsNotNone(analysis.comparison, analysis.registration_reason)
        self.assertEqual(analysis.status, am.CONFIRMED_COMPARISON)
        self.assertEqual(analysis.comparison.pair_rows[0].experimental_mode, 1)
        self.assertGreater(analysis.comparison.pair_rows[0].mac, 0.999)


class _Blocked(_Flow):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(modal_core, "compare_modal_datasets",
                                    side_effect=AssertionError("this must not reach the comparator"))
        self.comparator = patcher.start()
        self.addCleanup(patcher.stop)


class UnconfirmedTests(_Blocked):
    def test_no_comparison_without_a_confirmation(self):
        _window, panel = self.analysed()
        self.assertFalse(panel.compare_confirmed())
        self.assertTrue(panel.compare_button.isHidden())
        self.assert_frequency_only(panel)

    def test_a_reviewed_draft_is_not_a_confirmation(self):
        _window, panel = self.analysed()
        dialog = self.draft(panel)
        self.assertTrue(dialog.is_reviewed())
        self.assertIsNone(panel.confirmation)
        self.assertFalse(panel.compare_confirmed())
        self.assert_frequency_only(panel)

    def test_opening_the_confirmation_needs_a_saved_reviewed_draft(self):
        _window, panel = self.analysed()
        dialog = panel.open_registration()
        self.state_evidence(dialog, panel)
        self.assertTrue(dialog.check())
        self.wait(panel)
        self.assertFalse(dialog.confirm_button.isEnabled())
        self.assertFalse(dialog.confirm_registration())
        dialog.review_box.setChecked(True)
        self.assertFalse(dialog.confirm_registration())  # reviewed, but no draft file

    def test_every_statement_the_name_and_the_location_are_required(self):
        _window, panel = self.analysed()
        dialog = self.draft(panel)
        confirming = self.confirmation_dialog(dialog, panel)
        self.assertFalse(confirming.action.isEnabled())
        for box in confirming.boxes.values():
            box.setChecked(True)
        self.assertFalse(confirming.ready())
        confirming.name.setText("A. Tester")
        self.assertFalse(confirming.ready())
        confirming.location.setText("notebook")
        self.assertTrue(confirming.ready())
        next(iter(confirming.boxes.values())).setChecked(False)
        self.assertFalse(confirming.confirm(str(self.root / "c.json")))
        self.assertFalse((self.root / "c.json").exists())

    def test_a_form_changed_after_the_draft_cannot_be_confirmed(self):
        _window, panel = self.analysed()
        dialog = self.draft(panel)
        dialog.source.setText("another source")
        self.assertFalse(dialog.confirm_registration())
        self.assertIsNone(dialog.confirmation_dialog)

    def test_missing_evidence_stays_required(self):
        _window, panel = self.analysed()
        dialog = panel.open_registration()
        self.assertTrue(dialog.check())
        self.wait(panel)
        self.assertEqual(dialog.proposal.status, gr.REGISTRATION_REQUIRED)
        self.assertIsNone(dialog.review_box)
        self.assertFalse(dialog.confirm_button.isEnabled())
        self.assert_frequency_only(panel)

    def test_ambiguous_orientation_cannot_be_saved_or_confirmed(self):
        _window, panel = self.analysed()
        dialog = panel.open_registration()
        self.state_evidence(dialog, panel, axes=("", "", ""))
        self.assertTrue(dialog.check())
        self.wait(panel)
        self.assertIn(gr.AMBIGUOUS, [p.code for p in dialog.proposal.problems])
        self.assertFalse(dialog.save_button.isEnabled())
        self.assertFalse(dialog.confirm_button.isEnabled())
        self.assert_frequency_only(panel)

    def test_a_new_analysis_drops_the_confirmation(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        self.assertIsNotNone(panel.confirmation)
        self.run_analysis(panel)
        self.assertIsNone(panel.confirmation)
        self.assertFalse(panel.compare_confirmed())
        self.assert_frequency_only(panel)

    def test_a_replaced_file_drops_the_confirmation(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        panel.choose_file(EXPERIMENTAL, str(self.unv(self.nodes(), freqs(), name="another.unv")))
        self.assertIsNone(panel.confirmation)
        self.assertFalse(panel.compare_confirmed())


class StaleTests(_Blocked):
    def test_a_changed_experimental_file_stops_at_the_comparison(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        self.exp_path.write_bytes(self.exp_path.read_bytes() + b"\n")
        self.assertTrue(panel.compare_confirmed())
        self.wait(panel)
        self.assertEqual(panel.state, BLOCKED)
        self.assertEqual(panel.message.text(), am.STALE_TEXT)
        self.assertIsNone(panel.analysis)
        self.comparator.assert_not_called()

    def test_a_changed_fe_package_stops_at_the_comparison(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        mode_file = next(Path(panel.inputs.full_fe.manifest_path).parent.glob("mode_*.csv"))
        mode_file.write_bytes(mode_file.read_bytes() + b"\n")
        self.assertTrue(panel.compare_confirmed())
        self.wait(panel)
        self.assertEqual(panel.state, BLOCKED)
        self.comparator.assert_not_called()

    def test_a_file_changed_after_the_source_check_is_stopped_inside_the_comparison(self):
        """The comparison identifies the files itself, whatever happened before."""
        _window, panel = self.analysed()
        self.confirmed(panel)
        inputs = panel.inputs
        document = panel.confirmation
        self.exp_path.write_bytes(self.exp_path.read_bytes() + b"\n")
        with mock.patch.object(am, "confirm_sources"):
            analysis = am.analyse(inputs, 0, threading.Event(), document)
        self.assertEqual(analysis.status, am.REGISTRATION_REQUIRED)
        self.assertIsNone(analysis.comparison)
        self.assertEqual(analysis.registration_outcome, am.NOT_CONFIRMED)
        self.comparator.assert_not_called()

    def test_a_saved_confirmation_of_a_changed_file_is_not_usable(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        path = self.confirmation_path
        other = self.unv(self.nodes(), tuple(f * 1.01 for f in freqs()), name="other.unv")
        panel.choose_file(EXPERIMENTAL, str(other))
        self.run_analysis(panel)
        self.assertTrue(panel.open_confirmation(str(path)))
        self.wait(panel)
        self.assertTrue(panel.proposal_label.text().startswith(UNUSABLE_TEXT))
        self.assertIsNone(panel.confirmation)
        self.assertIsNone(panel.confirmation_view)
        self.assert_frequency_only(panel)


class _Altered(_Flow):
    """The confirmation content altered, as someone editing the file would, with its hash recomputed."""

    def prepared(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        self.document = json.loads(self.confirmation_path.read_text(encoding="utf-8"))
        return panel

    @staticmethod
    def rehash(document: dict) -> dict:
        body = {key: value for key, value in document.items() if key != "confirmation_sha256"}
        return dict(body, confirmation_sha256=canonical_hash(body))

    @staticmethod
    def rehash_draft(draft: dict) -> dict:
        body = {key: value for key, value in draft.items() if key != "draft_sha256"}
        return dict(body, draft_sha256=canonical_hash(body))

    def assert_refused(self, panel, document, word=""):
        patcher = mock.patch.object(modal_core, "compare_modal_datasets", side_effect=AssertionError("no comparator"))
        patcher.start()
        self.addCleanup(patcher.stop)
        analysis = am.analyse(panel.inputs, 0, threading.Event(), document)
        self.assertEqual(analysis.status, am.REGISTRATION_REQUIRED)
        self.assertIsNone(analysis.comparison)
        self.assertEqual(analysis.registration_outcome, am.NOT_CONFIRMED, analysis.registration_reason)
        self.assertTrue(analysis.nearest_rows)
        if word:
            self.assertIn(word, analysis.registration_reason)


class AlteredTests(_Altered):
    def test_a_change_without_a_new_hash(self):
        panel = self.prepared()
        document = copy.deepcopy(self.document)
        document["confirmed_by"] = "someone else"
        self.assert_refused(panel, document, "altered")

    def test_changed_evidence_with_every_hash_recomputed(self):
        panel = self.prepared()
        document = copy.deepcopy(self.document)
        draft = document["draft"]
        draft["evidence"]["source"] = "another source"
        evidence = {**draft["evidence"]}
        stated = gr.Evidence(evidence["fe_unit"], evidence["experimental_unit"], tuple(evidence["axes"]),
                             evidence["measured_side"], tuple(evidence["measured_dofs"]),
                             tuple(tuple(p) for p in evidence["landmarks"]), evidence["source"])
        draft["evidence_sha256"] = stated.evidence_hash
        document["draft"] = self.rehash_draft(draft)
        document["draft_sha256"] = document["draft"]["draft_sha256"]
        document["evidence_sha256"] = stated.evidence_hash
        self.assert_refused(panel, self.rehash(document))

    def test_an_altered_mapping_with_every_hash_recomputed(self):
        panel = self.prepared()
        document = copy.deepcopy(self.document)
        draft = document["draft"]
        mapping = draft["result"]["mapping"]
        mapping[1][1], mapping[2][1] = mapping[2][1], mapping[1][1]
        document["draft"] = self.rehash_draft(draft)
        document["draft_sha256"] = document["draft"]["draft_sha256"]
        self.assert_refused(panel, self.rehash(document), "differs")

    def test_an_altered_modal_set_with_every_hash_recomputed(self):
        panel = self.prepared()
        document = copy.deepcopy(self.document)
        document["draft"]["modal_set"]["key"] = "another set"
        document["draft"] = self.rehash_draft(document["draft"])
        document["draft_sha256"] = document["draft"]["draft_sha256"]
        self.assert_refused(panel, self.rehash(document), "modal set")

    def test_another_registration_hash(self):
        panel = self.prepared()
        document = copy.deepcopy(self.document)
        document["registration_hash"] = "e" * 64
        self.assert_refused(panel, self.rehash(document), "not the confirmed registration")

    def test_a_claim_of_governance(self):
        panel = self.prepared()
        for key in ("governed", "production_ready", "independent_verification"):
            document = copy.deepcopy(self.document)
            document[key] = True
            self.assert_refused(panel, self.rehash(document), "claims more")

    def test_a_missing_statement_or_field(self):
        panel = self.prepared()
        document = copy.deepcopy(self.document)
        document["statements"] = document["statements"][:-1]
        self.assert_refused(panel, self.rehash(document), "Not every physical statement")
        document = copy.deepcopy(self.document)
        del document["confirmed_by"]
        self.assert_refused(panel, self.rehash(document))
        document = copy.deepcopy(self.document)
        document["confirmed_by"] = " "
        self.assert_refused(panel, self.rehash(document))

    def test_a_diagnostic_draft_is_not_a_confirmation(self):
        panel = self.prepared()
        self.assert_refused(panel, self.document["draft"], "Not a registration confirmation")

    def test_a_confirmation_cannot_approve_other_heuristics(self):
        panel = self.prepared()
        document = copy.deepcopy(self.document)
        document["draft"]["provisional_heuristics"][0]["approved_scientific_gate"] = True
        document["draft"] = self.rehash_draft(document["draft"])
        document["draft_sha256"] = document["draft"]["draft_sha256"]
        self.assert_refused(panel, self.rehash(document))

    def test_opening_an_altered_file_is_refused_on_the_page(self):
        panel = self.prepared()
        self.document["confirmed_by"] = "someone else"
        self.confirmation_path.write_text(json.dumps(self.document), encoding="utf-8")
        self.run_analysis(panel)
        self.assertTrue(panel.open_confirmation(str(self.confirmation_path)))
        self.wait(panel)
        self.assertIn("altered", panel.proposal_label.text())
        self.assertFalse(panel.compare_confirmed())


class ProvisionalTests(_Flow):
    def test_frf_peak_records_are_rejected_for_a_comparison(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        document = panel.confirmation
        with mock.patch.object(rm, "set_is_provisional", return_value=True), \
                mock.patch.object(modal_core, "compare_modal_datasets", side_effect=AssertionError("no comparator")):
            analysis = am.analyse(panel.inputs, 0, threading.Event(), document)
        self.assertEqual(analysis.status, am.REGISTRATION_REQUIRED)
        self.assertIsNone(analysis.comparison)
        self.assertIn("PROVISIONAL", analysis.registration_reason)

    def test_frf_peak_records_cannot_be_confirmed_or_opened(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        with mock.patch.object(rm, "set_is_provisional", return_value=True):
            with self.assertRaises(cs.ConfirmationRefused):
                am.confirm_registration(panel.inputs, 0, self.draft_path, "A", "B", cs.STATEMENT_KEYS,
                                        self.root / "x.json", threading.Event())
            with self.assertRaises(cs.ConfirmationRefused):
                am.open_confirmation(panel.inputs, 0, self.confirmation_path, threading.Event())
        self.assertFalse((self.root / "x.json").exists())


class PersistenceTests(_Flow):
    def test_a_saved_confirmation_reopens_is_displayed_and_used_only_on_command(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        path = self.confirmation_path
        self.run_analysis(panel)
        self.assertIsNone(panel.confirmation)
        self.assertEqual(panel.open_confirmation_button.text(), OPEN_CONFIRMATION)
        self.assertTrue(panel.open_confirmation(str(path)))
        self.wait(panel)
        view = panel.confirmation_view
        self.assertIsNotNone(view)
        self.assertIsNone(panel.confirmation)  # displayed, not used
        self.assertFalse(panel.compare_confirmed())
        text = "\n".join(label.text() for label in view.findChildren(QLabel))
        self.assertIn("A. Tester", text)
        view.use_existing()
        self.assertIsNotNone(panel.confirmation)
        analysis = self.compare(panel)
        self.assertEqual(analysis.status, am.CONFIRMED_COMPARISON, analysis.registration_reason)

    def test_the_confirmation_is_a_separate_file_and_the_draft_is_untouched(self):
        _window, panel = self.analysed()
        dialog = self.draft(panel)
        before = self.draft_path.read_bytes()
        confirming = self.confirmation_dialog(dialog, panel)
        self.sign(confirming)
        self.wait(panel)
        self.assertEqual(self.draft_path.read_bytes(), before)
        self.assertNotEqual(self.confirmation_path, self.draft_path)
        draft = json.loads(before)
        self.assertIs(draft["accepted_physical_registration"], False)
        self.assertEqual(draft["status"], gr.DRAFT_STATUS)

    def test_the_draft_file_cannot_be_the_target(self):
        _window, panel = self.analysed()
        dialog = self.draft(panel)
        before = self.draft_path.read_bytes()
        confirming = self.confirmation_dialog(dialog, panel)
        for box in confirming.boxes.values():
            box.setChecked(True)
        confirming.name.setText("A. Tester")
        confirming.location.setText("notebook")
        self.assertTrue(confirming.confirm(str(self.draft_path)))
        self.wait(panel)
        self.assertIn("not overwritten", confirming.message.text())
        self.assertEqual(self.draft_path.read_bytes(), before)
        self.assertIsNone(panel.confirmation)

    def test_the_file_records_its_bindings_and_provenance(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        document = json.loads(self.confirmation_path.read_text(encoding="utf-8"))
        self.assertEqual(document["schema"], cs.CONFIRMATION_SCHEMA)
        self.assertEqual(document["status"], cs.CONFIRMED_STATUS)
        self.assertEqual(document["confirmed_by"], "A. Tester")
        self.assertEqual(document["evidence_location"], "laboratory notebook 7, page 12")
        self.assertTrue(document["confirmed_at"].endswith("+00:00"))
        self.assertEqual(document["statements"], list(cs.STATEMENT_KEYS))
        for key in ("governed", "production_ready", "independent_verification"):
            self.assertIs(document[key], False)
        self.assertIn("not proof of physical correctness", document["limits"][0])
        draft = document["draft"]
        self.assertEqual(document["draft_sha256"], draft["draft_sha256"])
        self.assertEqual(draft["sources"]["experimental"]["sha256"],
                         hashlib.sha256(self.exp_path.read_bytes()).hexdigest())
        self.assertEqual(draft["modal_set"]["record_count"], RECORDS)
        self.assertEqual({row["approved_scientific_gate"] for row in draft["provisional_heuristics"]}, {False})

    def test_no_source_file_changes(self):
        _window, panel = self.analysed()
        folder = Path(panel.inputs.full_fe.manifest_path).parent
        sources = [self.odb, self.exp_path] + sorted(p for p in folder.rglob("*") if p.is_file())
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in sources}
        self.confirmed(panel)
        self.compare(panel)
        self.assertEqual({p: (p.read_bytes(), p.stat().st_mtime_ns) for p in sources}, before)


class DisplayTests(_Flow):
    def test_everything_is_displayed_before_the_confirmation(self):
        _window, panel = self.analysed()
        dialog = self.draft(panel)
        confirming = self.confirmation_dialog(dialog, panel)
        text = "\n".join(label.text() for label in confirming.findChildren(QLabel))
        for word in ("Units: FE m, experimental m", "Stated axes: +x → +X", "Resulting axes", "Measured side (FE): +Z",
                     "Measured DOFs: z", "Experimental point", "marker photograph and measurement drawing",
                     "Experimental file SHA-256", "FE package SHA-256", "FE geometry SHA-256", "Modal set",
                     "not proof of physical correctness", "not approved scientific gates"):
            self.assertIn(word, text)
        self.assertEqual(confirming.table.rowCount(), 25)
        boxes = confirming.findChildren(QCheckBox)
        self.assertEqual(len(boxes), len(cs.STATEMENTS))
        self.assertFalse(any(box.isChecked() for box in boxes))

    def test_the_text_of_the_workflow_is_clean(self):
        window, panel = self.analysed()
        dialog = self.draft(panel)
        confirming = self.confirmation_dialog(dialog, panel)
        texts = [label.text() for label in confirming.findChildren(QLabel)]
        texts += [button.text() for button in confirming.findChildren(QPushButton)]
        texts += [box.text() for box in confirming.findChildren(QCheckBox)]
        self.assertEqual([t for t in texts if FORBIDDEN.search(t)], [])
        self.sign(confirming)
        self.wait(panel)
        self.compare(panel)
        found = [t for t in shown_text(window) if FORBIDDEN.search(t) and str(self.root) not in t]
        self.assertEqual(found, [])

    def test_a_cancelled_comparison_keeps_the_frequency_result(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        self.assertTrue(panel.compare_confirmed())
        self.assertEqual(panel.state, RUNNING)
        panel.cancel()
        self.assertEqual(panel.state, DONE)
        self.wait(panel)
        self.assert_frequency_only(panel)


class ServiceTests(unittest.TestCase):
    def test_no_modal_quantity_decides_the_registration(self):
        for name in ("generic_registration.py", "confirmed_registration.py"):
            tree = ast.parse((ROOT / "src" / "services" / name).read_text(encoding="utf-8"))
            attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
            self.assertFalse({"frequency_hz", "vectors", "mac", "mac_matrix", "pairs"} & attributes, name)
            names = {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names}
            self.assertFalse({"compare_modal_datasets", "geometry_alignment_candidates"} & names, name)

    def test_the_draft_service_still_builds_no_registration(self):
        tree = ast.parse((ROOT / "src" / "services" / "generic_registration.py").read_text(encoding="utf-8"))
        names = {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names}
        self.assertNotIn("FrozenRegistration", names)

    def test_the_transform_matches_the_comparators_convention(self):
        """x_fe = (s x_exp) R^T + t and x_exp = (x_fe R') s' + t' describe the same points."""
        rotation = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
        translation, scale = np.array([5.0, -2.0, 3.0]), 1000.0
        points = np.random.default_rng(3).standard_normal((9, 3))
        fe = (scale * points) @ rotation.T + translation
        back = (fe @ rotation) * (1.0 / scale) + (-(translation @ rotation) / scale)
        np.testing.assert_allclose(back, points, atol=1.0e-12)


if __name__ == "__main__":
    unittest.main()
