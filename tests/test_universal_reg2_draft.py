"""UNIVERSAL-REG-2: a generic registration proposal kept as a versioned draft; reopening never trusts the file."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

import numpy as np

import test_universal_reg1_registration as reg1
from test_universal_ui2_clean import FORBIDDEN

from PySide6.QtWidgets import QLabel, QPushButton

from domain.specimen_manifest import canonical_hash
from new_gui import analyze_model as am
from new_gui import comparison_model as cm
from new_gui.analyze_panel import PROPOSED_TEXT, REFUSED_TEXT, REVIEWED_TEXT
from new_gui.workspace_state import EXPERIMENTAL
from services import generic_registration as gr

ROOT = Path(__file__).resolve().parents[1]
MODAL_SET = {"key": "set-a", "display_name": "Fitted", "processing_name": "x", "record_count": 2}
SOURCES = {"fe": {"manifest_sha256": "a" * 64, "package_sha256": "b" * 64, "files": [["geometry", "g.csv", 9, "c" * 64]]},
           "experimental": {"sha256": "d" * 64, "size": 123}}


def rehash(document: dict) -> dict:
    """What someone altering the file on purpose would do: the SHA-256 alone proves nothing."""
    body = {key: value for key, value in document.items() if key != "draft_sha256"}
    return dict(body, draft_sha256=canonical_hash(body))


class _Service(unittest.TestCase):
    points = staticmethod(reg1.plate)
    stated: dict = {}

    def setUp(self):
        points = self.points()
        self.fe = reg1.fe_dataset(points)
        self.experimental = reg1.experimental_dataset(reg1.in_metres(points))
        self.evidence = reg1.evidence(**self.stated)
        self.proposal = gr.propose(self.fe, self.experimental, self.evidence)
        self.assertTrue(self.proposal.proposed, self.proposal.problems)
        self.document = gr.draft_document(self.proposal, self.evidence, self.experimental, modal_set=MODAL_SET,
                                          sources=SOURCES)

    def reopen(self, document=None, *, fe=None, experimental=None, modal_set=MODAL_SET, sources=SOURCES):
        return gr.revalidate_draft(json.loads(json.dumps(document or self.document)), fe or self.fe,
                                   experimental or self.experimental, modal_set=modal_set, sources=sources)

    def assert_rejected(self, result, code):
        self.assertEqual(result.proposal.status, gr.REGISTRATION_REQUIRED)
        self.assertIn(code, [problem.code for problem in result.proposal.problems])
        self.assertEqual(result.proposal.mapping, ())
        self.assertFalse(result.proposal.proposed)


class PlateDraftTests(_Service):
    def test_a_saved_draft_reopens_with_the_same_result(self):
        result = self.reopen()
        self.assertEqual(result.proposal, self.proposal)
        self.assertEqual(result.evidence, self.evidence)

    def test_the_file_holds_what_the_task_names(self):
        document = self.document
        self.assertEqual(document["schema"], "universal/registration-draft/v2")
        self.assertEqual(document["evidence"]["landmarks"], [["100", "PART-1:1"]])
        for key in ("fe_unit", "experimental_unit", "axes", "measured_side", "measured_dofs", "source"):
            self.assertIn(key, document["evidence"])
        self.assertEqual(len(document["result"]["mapping"]), len(self.points()))
        self.assertEqual(document["result"]["warnings"], list(self.proposal.warnings))
        self.assertEqual(document["modal_set"], MODAL_SET)
        self.assertEqual(document["sources"], SOURCES)
        self.assertEqual(document["fe_geometry_sha256"], self.proposal.fe_geometry_sha256)
        self.assertEqual(len(document["experimental_geometry_sha256"]), 64)

    def test_it_says_it_is_no_accepted_registration(self):
        self.assertIs(self.document["accepted_physical_registration"], False)
        self.assertIs(self.document["review_required"], True)
        self.assertEqual(self.document["status"], gr.DRAFT_STATUS)

    def test_the_heuristics_are_labelled_provisional_and_unchanged(self):
        rows = {row["name"]: row for row in self.document["provisional_heuristics"]}
        self.assertEqual({name: rows[name]["value"] for name in rows},
                         {"landmark_extent_ratio": 0.05, "stated_axis_angle": 5.0, "fe_node_tie": 0.01})
        for row in rows.values():
            self.assertEqual(row["status"], "PROVISIONAL_DIAGNOSTIC_HEURISTIC")
            self.assertIs(row["approved_scientific_gate"], False)
        self.assertIn("not approved scientific gates", self.proposal.heuristics_note)

    def test_the_same_inputs_give_the_same_bytes(self):
        again = gr.draft_document(gr.propose(self.fe, self.experimental, self.evidence), self.evidence, self.experimental,
                                  modal_set=MODAL_SET, sources=SOURCES)
        self.assertEqual(gr.draft_bytes(self.document), gr.draft_bytes(again))
        text = gr.draft_bytes(self.document).decode("utf-8").lower()
        for word in ("created", "timestamp", "c:\\\\", "d:\\\\"):
            self.assertNotIn(word, text)

    def test_only_a_proposal_can_be_saved(self):
        refused = gr.propose(self.fe, self.experimental, reg1.evidence(axes=("", "", "")))
        with self.assertRaises(gr.DraftRefused):
            gr.draft_document(refused, reg1.evidence(axes=("", "", "")), self.experimental, modal_set=MODAL_SET,
                              sources=SOURCES)

    def test_evidence_other_than_the_checked_one_cannot_be_saved(self):
        with self.assertRaises(gr.DraftRefused):
            gr.draft_document(self.proposal, reg1.evidence(source="another"), self.experimental, modal_set=MODAL_SET,
                              sources=SOURCES)


class BeamDraftTests(PlateDraftTests):
    points = staticmethod(reg1.beam)
    stated = {"landmarks": (("100", "PART-1:1"), ("120", "PART-1:21"))}

    def test_the_file_holds_what_the_task_names(self):
        self.assertEqual(len(self.document["result"]["mapping"]), 21)
        self.assertEqual(self.document["evidence"]["landmarks"], [["100", "PART-1:1"], ["120", "PART-1:21"]])


class ChangedSourceTests(_Service):
    def test_another_experimental_file(self):
        changed = copy.deepcopy(SOURCES)
        changed["experimental"]["sha256"] = "e" * 64
        self.assert_rejected(self.reopen(sources=changed), gr.DRAFT_CHANGED)

    def test_another_fe_package(self):
        changed = copy.deepcopy(SOURCES)
        changed["fe"]["package_sha256"] = "e" * 64
        self.assert_rejected(self.reopen(sources=changed), gr.DRAFT_CHANGED)

    def test_another_modal_set(self):
        self.assert_rejected(self.reopen(modal_set=dict(MODAL_SET, key="set-b")), gr.DRAFT_CHANGED)

    def test_another_fe_geometry(self):
        moved = reg1.plate() + np.array([0.0, 0.0, 1.0])
        self.assert_rejected(self.reopen(fe=reg1.fe_dataset(moved)), gr.DRAFT_CHANGED)

    def test_another_experimental_geometry(self):
        moved = reg1.in_metres(reg1.plate()) + 1.0
        self.assert_rejected(self.reopen(experimental=reg1.experimental_dataset(moved)), gr.DRAFT_CHANGED)


class TamperedDraftTests(_Service):
    def test_a_change_without_a_new_hash(self):
        document = copy.deepcopy(self.document)
        document["result"]["mapping"][0][1] = "PART-1:2"
        self.assert_rejected(self.reopen(document), gr.DRAFT_TAMPERED)

    def test_an_incorrect_mapping_with_a_recomputed_hash(self):
        document = copy.deepcopy(self.document)
        mapping = document["result"]["mapping"]
        mapping[3][1], mapping[4][1] = mapping[4][1], mapping[3][1]
        self.assert_rejected(self.reopen(rehash(document)), gr.DRAFT_NOT_REPRODUCED)

    def test_an_incorrect_distance_with_a_recomputed_hash(self):
        document = copy.deepcopy(self.document)
        document["result"]["mapping"][3][2] = 12.0
        self.assert_rejected(self.reopen(rehash(document)), gr.DRAFT_NOT_REPRODUCED)

    def test_a_shortened_mapping_with_a_recomputed_hash(self):
        document = copy.deepcopy(self.document)
        del document["result"]["mapping"][-1]
        self.assert_rejected(self.reopen(rehash(document)), gr.DRAFT_NOT_REPRODUCED)

    def test_a_removed_warning_with_a_recomputed_hash(self):
        document = copy.deepcopy(self.document)
        document["result"]["warnings"] = []
        self.assert_rejected(self.reopen(rehash(document)), gr.DRAFT_NOT_REPRODUCED)

    def test_another_rotation_with_a_recomputed_hash(self):
        document = copy.deepcopy(self.document)
        document["result"]["rotation"] = [[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]
        self.assert_rejected(self.reopen(rehash(document)), gr.DRAFT_NOT_REPRODUCED)

    def test_a_claim_of_acceptance_with_a_recomputed_hash(self):
        for key, value in (("accepted_physical_registration", True), ("review_required", False),
                           ("status", "ACCEPTED")):
            document = copy.deepcopy(self.document)
            document[key] = value
            self.assert_rejected(self.reopen(rehash(document)), gr.DRAFT_TAMPERED)

    def test_other_heuristics_with_a_recomputed_hash(self):
        document = copy.deepcopy(self.document)
        document["provisional_heuristics"][0]["value"] = 0.5
        self.assert_rejected(self.reopen(rehash(document)), gr.DRAFT_NOT_REPRODUCED)
        document = copy.deepcopy(self.document)
        document["provisional_heuristics"][0]["approved_scientific_gate"] = True
        self.assert_rejected(self.reopen(rehash(document)), gr.DRAFT_NOT_REPRODUCED)

    def test_evidence_that_no_longer_matches_its_hash(self):
        document = copy.deepcopy(self.document)
        document["evidence"]["source"] = "another"
        self.assert_rejected(self.reopen(rehash(document)), gr.DRAFT_TAMPERED)

    def test_evidence_and_all_hashes_altered_to_another_orientation(self):
        """Fully consistent forgery: the recomputation refuses it, since this evidence is not this mapping."""
        document = copy.deepcopy(self.document)
        document["evidence"]["axes"] = ["-X", "-Y", "+Z"]
        altered = gr.Evidence(document["evidence"]["fe_unit"], document["evidence"]["experimental_unit"],
                              ("-X", "-Y", "+Z"), "+Z", ("z",), (("100", "PART-1:1"),), "marker photograph")
        document["evidence_sha256"] = altered.evidence_hash
        self.assert_rejected(self.reopen(rehash(document)), gr.DRAFT_NOT_REPRODUCED)

    def test_ambiguous_orientation_with_all_hashes_recomputed(self):
        document = copy.deepcopy(self.document)
        document["evidence"]["axes"] = ["", "", ""]
        altered = reg1.evidence(axes=("", "", ""))
        document["evidence_sha256"] = altered.evidence_hash
        result = self.reopen(rehash(document))
        self.assert_rejected(result, gr.AMBIGUOUS)
        self.assert_rejected(result, gr.DRAFT_NOT_REPRODUCED)
        self.assertEqual(result.proposal.mapping, ())

    def test_values_of_the_wrong_type(self):
        for change in ({"landmarks": "100"}, {"axes": ["+X"]}, {"measured_dofs": [1]}, {"landmarks": [["100"]]}):
            document = copy.deepcopy(self.document)
            document["evidence"].update(change)
            self.assert_rejected(self.reopen(rehash(document)), gr.DRAFT_INVALID)

    def test_numbers_of_the_wrong_type_in_the_result(self):
        document = copy.deepcopy(self.document)
        document["result"]["mapping"][0][2] = "0"
        self.assert_rejected(self.reopen(rehash(document)), gr.DRAFT_NOT_REPRODUCED)
        document = copy.deepcopy(self.document)
        document["result"]["scale"] = None
        self.assert_rejected(self.reopen(rehash(document)), gr.DRAFT_NOT_REPRODUCED)


class IncompleteDraftTests(_Service):
    def test_each_missing_field_is_refused(self):
        for key in self.document:
            if key == "schema":
                continue
            document = copy.deepcopy(self.document)
            del document[key]
            self.assert_rejected(self.reopen(document), gr.DRAFT_INVALID)

    def test_a_missing_result_or_evidence_field_is_refused(self):
        for part, keys in (("result", gr._RESULT_KEYS), ("evidence", gr._EVIDENCE_KEYS)):
            for key in keys:
                document = copy.deepcopy(self.document)
                del document[part][key]
                self.assert_rejected(self.reopen(rehash(document)), gr.DRAFT_INVALID)

    def test_an_unexpected_field_is_refused(self):
        document = copy.deepcopy(self.document)
        document["accepted_by"] = "someone"
        self.assert_rejected(self.reopen(document), gr.DRAFT_INVALID)

    def test_another_version_is_refused(self):
        document = copy.deepcopy(self.document)
        document["schema"] = "universal/registration-draft/v1"
        self.assert_rejected(self.reopen(rehash(document)), gr.DRAFT_INVALID)


class FileTests(_Service):
    def setUp(self):
        super().setUp()
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)

    def test_a_written_file_reads_back(self):
        path = gr.write_draft(self.document, self.root / "draft.json")
        self.assertEqual(gr.read_draft(path), self.document)
        self.assertEqual([p.name for p in self.root.iterdir()], ["draft.json"])

    def test_bad_files_are_refused(self):
        cases = {"not json": b"{", "not an object": b"[1]", "repeated key": b'{"a":1,"a":2}', "nan": b'{"a":NaN}',
                 "infinity": b'{"a":Infinity}', "not text": b"\xff\xfe\x00"}
        for name, content in cases.items():
            path = self.root / "bad.json"
            path.write_bytes(content)
            with self.subTest(name), self.assertRaises(gr.DraftRefused):
                gr.read_draft(path)
        with self.assertRaises(gr.DraftRefused):
            gr.read_draft(self.root / "missing.json")

    def test_a_source_file_is_never_overwritten(self):
        source = self.root / "manifest.json"
        source.write_text("original", encoding="utf-8")
        with self.assertRaises(gr.DraftRefused):
            gr.write_draft(self.document, source, (source,))
        self.assertEqual(source.read_text(encoding="utf-8"), "original")

    def test_only_a_json_file_is_written(self):
        with self.assertRaises(gr.DraftRefused):
            gr.write_draft(self.document, self.root / "model.odb")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_a_failed_write_leaves_nothing_behind(self):
        with mock.patch("os.replace", side_effect=OSError("no")), self.assertRaises(gr.DraftRefused):
            gr.write_draft(self.document, self.root / "draft.json")
        self.assertEqual(list(self.root.iterdir()), [])


class NoAcceptanceTests(unittest.TestCase):
    def test_the_service_creates_no_frozen_registration_and_uses_no_modal_result(self):
        tree = ast.parse((ROOT / "src" / "services" / "generic_registration.py").read_text(encoding="utf-8"))
        names = {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names}
        self.assertFalse({"FrozenRegistration", "compare_modal_datasets", "build_frozen_registration"} & names)
        attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        self.assertFalse({"frequency_hz", "vectors", "mac", "mac_matrix", "pairs", "create"} & attributes)


def fingerprint(paths) -> dict:
    return {str(path): (hashlib.sha256(Path(path).read_bytes()).hexdigest(), Path(path).stat().st_mtime_ns)
            for path in paths}


class GuiTests(reg1._Gui):
    def proposed(self):
        window, panel = self.analysed()
        dialog = panel.open_registration()
        self.fill(dialog, panel)
        self.assertEqual(self.run_check(dialog, panel).status, gr.REGISTRATION_PROPOSED)
        return window, panel, dialog

    def save(self, dialog, panel, name="draft.json"):
        path = self.root / name
        dialog.review_box.setChecked(True)
        self.assertTrue(dialog.save_draft(str(path)))
        self.wait(panel)
        return path

    def sources(self, panel):
        folder = Path(panel.inputs.full_fe.manifest_path).parent
        return [self.odb, self.exp_path] + sorted(p for p in folder.rglob("*") if p.is_file())

    def test_saving_needs_the_explicit_review(self):
        _window, panel, dialog = self.proposed()
        self.assertFalse(dialog.save_button.isEnabled())
        self.assertFalse(dialog.save_draft(str(self.root / "draft.json")))
        self.assertFalse((self.root / "draft.json").exists())
        dialog.review_box.setChecked(True)
        self.assertTrue(dialog.save_button.isEnabled())
        self.assertEqual(panel.proposal_label.text(), REVIEWED_TEXT)
        dialog.review_box.setChecked(False)
        self.assertEqual(panel.proposal_label.text(), PROPOSED_TEXT)

    def test_a_refused_check_offers_no_review_and_no_save(self):
        _window, panel = self.analysed()
        dialog = panel.open_registration()
        self.run_check(dialog, panel)
        self.assertIsNone(dialog.review_box)
        self.assertFalse(dialog.save_button.isEnabled())

    def test_a_form_changed_after_the_check_is_not_saved(self):
        _window, panel, dialog = self.proposed()
        dialog.review_box.setChecked(True)
        dialog.source.setText("another source")
        self.assertFalse(dialog.save_draft(str(self.root / "draft.json")))
        self.assertIn("Check the evidence again", dialog.draft_note.text())
        self.assertFalse((self.root / "draft.json").exists())

    def test_save_and_reopen_in_a_new_dialog_fills_the_form_unreviewed(self):
        _window, panel, dialog = self.proposed()
        evidence = dialog.evidence()[0]
        proposal = dialog.proposal
        path = self.save(dialog, panel)
        self.assertIn("not an accepted physical registration", dialog.draft_note.text())
        panel._close_registration()
        again = panel.open_registration()
        self.assertEqual(again.evidence()[0].landmarks, ())
        self.assertTrue(again.open_draft(str(path)))
        self.wait(panel)
        self.assertEqual(again.proposal, proposal)
        self.assertEqual(again.evidence()[0], evidence)
        self.assertFalse(again.is_reviewed())
        self.assertFalse(again.save_button.isEnabled())
        self.assertIn("Review it", again.draft_note.text())
        self.assertIn("not an accepted physical registration", again.draft_note.text())
        self.assertEqual(panel.proposal_label.text(), PROPOSED_TEXT)
        self.assertEqual(again.table.rowCount(), len(proposal.mapping))

    def test_a_reopened_draft_changes_nothing_in_the_analysis(self):
        _window, panel, dialog = self.proposed()
        rows, nearest = panel.analysis.fe_rows, panel.analysis.nearest_rows
        path = self.save(dialog, panel)
        with mock.patch.object(cm, "run_compare", side_effect=AssertionError("no comparison")), \
                mock.patch.object(am.rm, "run_check", side_effect=AssertionError("no registration check")):
            self.assertTrue(dialog.open_draft(str(path)))
            self.wait(panel)
        self.assertEqual(panel.status_label.text(), am.REGISTRATION_REQUIRED)
        self.assertEqual(panel.analysis.status, am.REGISTRATION_REQUIRED)
        self.assertIsNone(panel.analysis.comparison)
        self.assertNotIn("pairs", panel.tables)
        self.assertNotIn("mac", panel.tables)
        self.assertEqual((panel.analysis.fe_rows, panel.analysis.nearest_rows), (rows, nearest))
        self.assertEqual(len(rows), 20)

    def test_a_draft_does_not_enter_a_new_analysis(self):
        _window, panel, dialog = self.proposed()
        self.save(dialog, panel)
        with mock.patch.object(cm, "run_compare", side_effect=AssertionError("no comparison")):
            self.run_analysis(panel)
        self.assertEqual(panel.analysis.status, am.REGISTRATION_REQUIRED)
        self.assertIsNone(panel.proposal)

    def test_a_changed_experimental_file_rejects_the_draft_and_leaves_the_form(self):
        _window, panel, dialog = self.proposed()
        path = self.save(dialog, panel)
        panel._close_registration()
        again = panel.open_registration()
        self.exp_path.write_bytes(self.exp_path.read_bytes() + b"\n")
        self.assertTrue(again.open_draft(str(path)))
        self.wait(panel)
        self.assertEqual(again.proposal.status, gr.REGISTRATION_REQUIRED)
        self.assertEqual(again.proposal.problems[0].code, gr.DRAFT_CHANGED)
        self.assertEqual(again.evidence()[0].landmarks, ())
        self.assertEqual(panel.proposal_label.text(), REFUSED_TEXT)
        self.assertIsNone(again.review_box)

    def test_a_changed_fe_package_rejects_the_draft(self):
        _window, panel, dialog = self.proposed()
        path = self.save(dialog, panel)
        mode_file = next(Path(panel.inputs.full_fe.manifest_path).parent.glob("mode_*.csv"))
        mode_file.write_bytes(mode_file.read_bytes() + b"\n")
        self.assertTrue(dialog.open_draft(str(path)))
        self.wait(panel)
        self.assertEqual(dialog.proposal.problems[0].code, gr.DRAFT_CHANGED)

    def test_a_draft_of_another_file_is_rejected_after_a_new_analysis(self):
        _window, panel, dialog = self.proposed()
        path = self.save(dialog, panel)
        other = self.unv(reg1.base.plate_nodes(), (20.5, 41.0, 77.0), name="another.unv")
        panel.choose_file(EXPERIMENTAL, str(other))
        self.run_analysis(panel)
        again = panel.open_registration()
        self.assertTrue(again.open_draft(str(path)))
        self.wait(panel)
        self.assertEqual(again.proposal.status, gr.REGISTRATION_REQUIRED)
        self.assertEqual(again.proposal.problems[0].code, gr.DRAFT_CHANGED)

    def test_a_tampered_file_is_rejected(self):
        _window, panel, dialog = self.proposed()
        path = self.save(dialog, panel)
        document = json.loads(path.read_text(encoding="utf-8"))
        document["result"]["mapping"][0][1] = document["result"]["mapping"][1][1]
        path.write_text(json.dumps(rehash(document)), encoding="utf-8")
        self.assertTrue(dialog.open_draft(str(path)))
        self.wait(panel)
        self.assertEqual(dialog.proposal.problems[0].code, gr.DRAFT_NOT_REPRODUCED)
        self.assertIsNone(dialog.table)

    def test_a_broken_file_is_a_message(self):
        _window, panel = self.analysed()
        dialog = panel.open_registration()
        path = self.root / "broken.json"
        path.write_text("{", encoding="utf-8")
        self.assertTrue(dialog.open_draft(str(path)))
        self.wait(panel)
        self.assertEqual(dialog.proposal.problems[0].code, gr.DRAFT_INVALID)

    def test_saving_and_opening_change_no_source_file(self):
        _window, panel, dialog = self.proposed()
        before = fingerprint(self.sources(panel))
        path = self.save(dialog, panel)
        self.assertTrue(dialog.open_draft(str(path)))
        self.wait(panel)
        self.assertEqual(fingerprint(self.sources(panel)), before)

    def test_a_source_file_is_refused_as_the_target(self):
        _window, panel, dialog = self.proposed()
        manifest = Path(panel.inputs.full_fe.manifest_path)
        before = manifest.read_bytes()
        dialog.review_box.setChecked(True)
        self.assertTrue(dialog.save_draft(str(manifest)))
        self.wait(panel)
        self.assertIn("not overwritten", dialog.draft_note.text())
        self.assertEqual(manifest.read_bytes(), before)

    def test_a_file_changed_before_saving_is_not_saved(self):
        _window, panel, dialog = self.proposed()
        dialog.review_box.setChecked(True)
        self.exp_path.write_bytes(self.exp_path.read_bytes() + b"\n")
        path = self.root / "draft.json"
        self.assertTrue(dialog.save_draft(str(path)))
        self.wait(panel)
        self.assertFalse(path.exists())
        self.assertIn("changed", dialog.draft_note.text())

    def test_the_saved_hashes_are_those_of_the_read_files(self):
        _window, panel, dialog = self.proposed()
        document = json.loads(self.save(dialog, panel).read_text(encoding="utf-8"))
        self.assertEqual(document["sources"]["experimental"]["sha256"],
                         hashlib.sha256(self.exp_path.read_bytes()).hexdigest())
        manifest = Path(panel.inputs.full_fe.manifest_path)
        self.assertEqual(document["sources"]["fe"]["manifest_sha256"], hashlib.sha256(manifest.read_bytes()).hexdigest())
        self.assertTrue(document["sources"]["fe"]["files"])
        self.assertNotIn(str(self.root), json.dumps(document))

    def test_the_dialog_names_the_heuristics_and_stays_clean(self):
        _window, panel, dialog = self.proposed()
        path = self.save(dialog, panel)
        self.assertTrue(dialog.open_draft(str(path)))
        self.wait(panel)
        texts = [label.text() for label in dialog.findChildren(QLabel)]
        self.assertTrue(any("Provisional diagnostic heuristics, not approved scientific gates" in text for text in texts))
        texts += [button.text() for button in dialog.findChildren(QPushButton)]
        cleaned = [text for text in texts if str(self.root) not in text]
        self.assertEqual([text for text in cleaned if FORBIDDEN.search(text)], [])

    def test_a_verified_result_still_offers_no_setup(self):
        verified = am.rm.RegistrationOutcome(0, view=mock.Mock(registration="hash-1"))
        cells = ("7", "20.0", "EXP1", "1", "20.5", "-2.44", "0.981", "paired", "")
        view = mock.Mock(status=cm.PAIRS_FOUND, pair_rows=(mock.Mock(cells=cells),), mac_cells=(("0.981",),),
                         mac_fe_modes=(7,), mac_experimental_modes=(1,), warnings=())
        with mock.patch.object(am.rm, "run_check", return_value=verified), \
                mock.patch.object(cm, "run_compare", return_value=cm.ComparisonOutcome(0, view=view)):
            _window, panel = self.analysed()
        self.assertEqual(panel.status_label.text(), cm.PAIRS_FOUND)
        self.assertIsNone(panel.open_registration())


class ModelTests(reg1._Gui):
    def test_save_is_refused_when_the_proposal_is_not_the_result_of_the_evidence(self):
        _window, panel = self.analysed()
        evidence = reg1.evidence()
        proposal = gr.Proposal(gr.REGISTRATION_PROPOSED, evidence_hash=evidence.evidence_hash)
        with self.assertRaises(gr.DraftRefused):
            am.save_registration_draft(panel.inputs, 0, evidence, proposal, self.root / "x.json", threading.Event())
        self.assertFalse((self.root / "x.json").exists())

    def test_a_cancelled_opening_is_a_cancellation(self):
        _window, panel = self.analysed()
        path = self.root / "x.json"
        path.write_text("{}", encoding="utf-8")
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(am.StepCancelled):
            am.open_registration_draft(panel.inputs, 0, path, cancel)


if __name__ == "__main__":
    unittest.main()
