"""WORKING-DRAFT-R2: Save Project and Open Project. Standalone synthetic data; Qt ``offscreen``; no Abaqus.

The save and reopen route is the real one. The "archived registration" case uses a stand-in comparison view, because no
accepted registration can match synthetic files; that case proves only that a saved status is kept and never raised.
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from unittest import mock
import unittest
import zipfile

import numpy as np

import test_universal_reg3_confirmed as reg3
import test_universal_two_file_analysis as base

from PySide6.QtWidgets import QPushButton

from new_gui import analyze_model as am
from new_gui import analyze_panel
from new_gui import comparison_model as cm
from new_gui import preview_model as pm
from new_gui import production_window as pw
from new_gui import project_model as pj
from new_gui import registration_check_model as rm
from new_gui import shape_model as sm
from new_gui.analyze_panel import DONE, RUNNING
from new_gui.workspace_state import EXPERIMENTAL, FE
from services import analysis_project as ap
from services import odb_import_service as svc

ROOT = Path(__file__).resolve().parents[1]


def displayed(panel) -> dict:
    """Every number and word the result tables show, tab by tab."""
    tables = {}
    for key, table in panel.tables.items():
        headers = [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
        rows = [[table.item(r, c).text() if table.item(r, c) else "" for c in range(table.columnCount())]
                for r in range(table.rowCount())]
        tables[key] = (headers, rows)
    analysis = panel.analysis
    tabs = [panel.result_tabs.tabText(i) for i in range(panel.result_tabs.count())]
    return {"tables": tables, "tabs": tabs, "status": panel.status_label.text(), "summary": analysis.summary,
            "facts": analysis.facts, "notes": analysis.notes, "note": analysis.registration_note,
            "first_elastic": analysis.first_elastic, "rigid": analysis.rigid_modes, "set": analysis.set_title,
            "unavailable": analysis.unavailable_fe, "total": analysis.experimental_total}


def rewrite(path: Path, change=None, drop=(), add=None) -> None:
    """A copy of the project with one member changed, hashes kept valid unless ``change`` says otherwise."""
    with zipfile.ZipFile(path) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    if change is not None:
        document = json.loads(members[ap.PROJECT])
        change(document)
        members[ap.PROJECT] = json.dumps(document).encode("utf-8")
    for name in drop:
        del members[name]
    members.update(add or {})
    listed = {name: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in members.items()
              if name != ap.MANIFEST}
    members[ap.MANIFEST] = json.dumps({"schema": ap.SCHEMA, "members": listed,
                                       "members_sha256": ap._members_hash(listed)}).encode("utf-8")
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)


class _Project(reg3._Flow):
    def setUp(self):
        super().setUp()
        self.project = self.root / "saved results.mcproj"

    def saved(self, panel, path=None) -> Path:
        path = path or self.project
        self.assertTrue(panel.save_project_as(str(path)))
        self.wait(panel)
        self.assertEqual(panel.state, DONE, panel.message.text())
        self.assertTrue(path.is_file(), panel.message.text())
        return path

    def reopened(self, path=None):
        """A new window, as after closing the program; any read or comparison is an error here."""
        window = pw.ProductionWindow(analyze_options={"runner": self.fail_runner, "discover": base.FOUND,
                                                      "consent": self.consent})
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        panel = window.analyze
        window.show()
        with mock.patch.object(pm, "run_read", side_effect=AssertionError("a project reads no source file")), \
                mock.patch.object(cm, "compare_confirmed", side_effect=AssertionError("no comparison")), \
                mock.patch.object(cm, "run_compare", side_effect=AssertionError("no comparison")), \
                mock.patch.object(cm, "run_compare_confirmed", side_effect=AssertionError("no comparison")), \
                mock.patch.object(rm, "run_check", side_effect=AssertionError("no registration check")), \
                mock.patch.object(svc, "run_extraction", side_effect=AssertionError("no Abaqus")), \
                mock.patch.object(svc, "hash_file", side_effect=AssertionError("opening hashes no source file")):
            self.assertTrue(panel.open_project(str(path or self.project)))
            self.wait(panel)
        return window, panel

    @staticmethod
    def fail_runner(**_kwargs):
        raise AssertionError("Abaqus must not start")

    def check(self, panel):
        self.assertTrue(panel.check_sources())
        self.wait(panel)
        return panel.source_check

    def row(self, panel, role):
        return next(row for row in panel.source_check.rows if row.role == role)


class SaveAndReopenTests(_Project):
    def test_frequency_only_results_come_back_identical_without_any_computation(self):
        _window, panel = self.analysed()
        before = displayed(panel)
        self.saved(panel)
        _second, again = self.reopened()
        self.assertEqual(displayed(again), before)
        self.assertEqual(again.status_label.text(), am.REGISTRATION_REQUIRED)
        self.assertIsNone(again.analysis.comparison)
        self.assertNotIn("pairs", again.tables)
        self.assertNotIn("mac", again.tables)
        self.assertIsNone(again.inputs)

    def test_confirmed_results_come_back_identical_with_their_mac_and_pairs(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        analysis = self.compare(panel)
        self.assertEqual(analysis.status, am.CONFIRMED_COMPARISON)
        before = displayed(panel)
        self.saved(panel)
        _second, again = self.reopened()
        self.assertEqual(displayed(again), before)
        view, saved = analysis.comparison, again.analysis.comparison
        self.assertEqual(saved.pair_rows, view.pair_rows)
        self.assertEqual(saved.mac_cells, view.mac_cells)
        self.assertEqual(saved.mac_values, view.mac_values)  # every digit
        self.assertEqual(saved.assigned_cells, view.assigned_cells)
        self.assertEqual(saved, view)

    def test_the_saved_shapes_are_shown_for_the_chosen_row(self):
        _window, panel = self.analysed()
        self.saved(panel)
        _second, again = self.reopened()
        self.assertFalse(again.saved_shapes[FE].isHidden())
        self.assertFalse(again.saved_shapes[EXPERIMENTAL].isHidden())
        self.assertTrue(again.shape_panels[FE].isHidden())
        self.assertIsNotNone(again.saved_shapes[FE].image.source)
        self.assertTrue(again.show_candidate(2))
        row = again.analysis.nearest_rows[2]
        self.assertEqual(again.saved_shapes[EXPERIMENTAL].shown_number, row[1])
        self.assertEqual(again.saved_shapes[FE].shown_number, row[3])
        self.assertEqual(again.saved_shapes[FE].item_combo.count(), 20)
        self.assertEqual(again.saved_shapes[EXPERIMENTAL].item_combo.count(), reg3.RECORDS)
        self.assertFalse(again.shape_panels[FE].busy())

    def test_the_saved_file_records_sources_set_modes_and_hashes(self):
        _window, panel = self.analysed()
        self.saved(panel)
        document, images = ap.read_project(self.project)
        self.assertEqual(document["schema"], ap.SCHEMA)
        sources = document["sources"]
        self.assertEqual(sources["fe_odb"]["path"], str(self.odb.resolve()))
        self.assertEqual(sources["fe_odb"]["sha256"], base.sha(self.odb))
        self.assertEqual(sources["experimental"]["sha256"], base.sha(self.exp_path))
        self.assertEqual(sources["fe_package"]["package_sha256"], panel.inputs.identities["fe"]["package"]["package_sha256"])
        self.assertEqual(document["modal_set"]["key"], panel.inputs.full_experimental.sets[0].key)
        self.assertEqual([m["number"] for m in document["modes"]["fe"]], list(range(1, 21)))
        self.assertEqual(document["modes"]["experimental"][0]["record"], "EXP1")
        self.assertEqual(document["modes"]["fe"][6]["type"], "elastic")
        self.assertEqual(len(images), 20 + reg3.RECORDS)
        self.assertIsNone(document["comparison"])
        self.assertEqual(document["registration"]["kind"], ap.KIND_NONE)

    def test_the_first_record_and_the_first_elastic_mode_are_kept(self):
        _window, panel = self.analysed()
        self.saved(panel)
        _second, again = self.reopened()
        self.assertEqual(again.analysis.experimental_rows[0][0], "EXP1")
        self.assertEqual(again.analysis.first_elastic, "7")
        self.assertEqual(again.analysis.fe_rows[0][0], "1")

    def test_the_chosen_set_is_saved_by_its_identity(self):
        nodes = self.nodes()
        unv = self.unv(nodes, sets=(("Fitted A", (50.0, 75.0)), ("Fitted B", (51.0, 76.0, 90.0))), name="sets.unv")
        window = self.window()
        panel = window.analyze
        panel.choose_file(FE, str(self.odb))
        panel.choose_file(EXPERIMENTAL, str(unv))
        self.run_analysis(panel)
        self.assertTrue(panel.choose_set(1))
        self.wait(panel)
        before = displayed(panel)
        self.saved(panel)
        _second, again = self.reopened()
        self.assertEqual(displayed(again), before)
        document = again.snapshot.document
        self.assertEqual(document["modal_set"]["index"], 1)
        self.assertEqual(len(document["modal_set"]["all_sets"]), 2)
        self.assertIn("Fitted B", document["modal_set"]["title"])

    def test_nothing_of_the_multi_gb_sources_is_stored(self):
        _window, panel = self.analysed()
        self.saved(panel)
        with zipfile.ZipFile(self.project) as archive:
            names = archive.namelist()
        self.assertTrue(all(name in (ap.MANIFEST, ap.PROJECT) or name.startswith("images/") for name in names), names)
        self.assertFalse([name for name in names if name.endswith((".odb", ".unv", ".uff", ".npy", ".npz", ".pkl"))])

    def test_a_beam_and_arbitrary_geometry_are_saved_the_same_way(self):
        for nodes in (base.beam_nodes(), base.arbitrary_nodes()):
            with self.subTest(nodes=len(nodes)):
                self.nodes = lambda n=nodes: n
                self.modes = lambda n=nodes: base.fe_modes(n)
                window = self.window()
                panel = window.analyze
                panel.choose_file(FE, str(self.odb))
                panel.choose_file(EXPERIMENTAL, str(self.unv(nodes, (20.5, 41.0))))
                self.run_analysis(panel)
                before = displayed(panel)
                path = self.saved(panel, self.root / f"geometry {len(nodes)}.mcproj")
                _second, again = self.reopened(path)
                self.assertEqual(displayed(again), before)
                self.assertEqual(again.snapshot.document["registration"]["kind"], ap.KIND_NONE)

    def test_a_shape_the_service_refuses_is_saved_as_a_refusal(self):
        _window, panel = self.analysed()
        real = sm.run_render

        def refuse_first(kind, source, index, component, token, cancel, display=None):
            if kind == FE and index == 0:
                return sm.ShapeOutcome(kind, token, error="No spatial view of this mode")
            return real(kind, source, index, component, token, cancel, display)

        with mock.patch.object(sm, "run_render", side_effect=refuse_first):
            self.saved(panel)
        _second, again = self.reopened()
        shapes = again.saved_shapes[FE]
        shapes.item_combo.setCurrentIndex(0)
        self.assertIn("No spatial view", shapes.status.text())
        self.assertIsNone(shapes.image.source)


class SnapshotIsHistoricalTests(_Project):
    def test_the_page_says_it_is_a_saved_snapshot(self):
        _window, panel = self.analysed()
        self.saved(panel)
        window, again = self.reopened()
        self.assertIn(analyze_panel.SNAPSHOT_BADGE, window.windowTitle())
        badges = [label.text() for label in again.findChildren(analyze_panel.QLabel) if label.objectName() == "badge"]
        self.assertIn(analyze_panel.SNAPSHOT_BADGE, badges)
        self.assertIn("Nothing was recalculated", again.project_box.findChildren(analyze_panel.QLabel)[1].text())
        self.assertIn(self.project.name, again.snapshot_label.text())

    def test_a_snapshot_offers_no_registration_and_no_comparison(self):
        _window, panel = self.analysed()
        self.saved(panel)
        _second, again = self.reopened()
        self.assertIsNone(again.open_registration())
        self.assertFalse(again.open_confirmation(str(self.root / "any.json")))
        self.assertFalse(again.compare_confirmed())
        self.assertIsNone(again.registration_button)
        self.assertIsNone(again.compare_button)
        self.assertFalse(again.choose_set(0))

    def test_registration_required_is_not_raised(self):
        _window, panel = self.analysed()
        self.saved(panel)
        _second, again = self.reopened()
        self.assertEqual(again.status_label.text(), am.REGISTRATION_REQUIRED)
        self.assertEqual(again.status_label.property("state"), "chosen")

    def test_a_user_confirmation_stays_a_user_confirmation(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        self.compare(panel)
        self.saved(panel)
        _second, again = self.reopened()
        self.assertEqual(again.status_label.text(), am.CONFIRMED_COMPARISON)
        self.assertEqual(again.status_label.property("state"), "chosen")
        self.assertNotEqual(again.status_label.text(), cm.PAIRS_FOUND)
        registration = again.snapshot.document["registration"]
        self.assertEqual(registration["kind"], ap.KIND_CONFIRMED)
        self.assertEqual(registration["confirmed_by"], "A. Tester")
        self.assertEqual(registration["confirmation_path"], str(self.confirmation_path))
        self.assertEqual(registration["draft_path"], str(self.draft_path))
        self.assertTrue(registration["limits"])
        self.assertIn("not proof of physical correctness", again.snapshot_label.text())

    def test_a_verified_status_is_shown_as_saved_never_as_verified_now(self):
        _window, panel = self.analysed()
        view = cm.ComparisonView(
            status=cm.PAIRS_FOUND, statement="s", set_title="t", specimen="x", fixture_id="y", registration="h",
            registration_file="r.json", pair_rows=(), mac_fe_modes=(7,), mac_experimental_modes=(1,),
            mac_cells=(("0.900",),), assigned_cells=frozenset(), candidate_rows=(), unmatched_fe_rows=(),
            unmatched_experimental_rows=(), unpaired_experimental=(), rigid_rows=(), close_groups=(), warnings=(),
            provenance=(), gates=(), target_counts="c", mac_values=((0.9,),))
        analysis = pj.analysis_of(_document_with(panel, view))
        path = self.root / "verified.mcproj"
        document = pj.analysis_document(analysis, panel.inputs, panel.paths[FE], None,
                                        {"component": "magnitude", "fe": [], "experimental": []})
        ap.write_project(document, {}, path)
        _second, again = self.reopened(path)
        self.assertEqual(again.status_label.text(), cm.PAIRS_FOUND)
        self.assertEqual(again.status_label.property("state"), "chosen")  # the green badge is for a fresh check only
        statements = [label.text() for label in again.result_box.findChildren(analyze_panel.QLabel)]
        self.assertTrue(any(text.startswith(analyze_panel.AS_SAVED) for text in statements))

    def test_a_refused_confirmation_is_saved_as_registration_required(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        panel.confirmation = dict(panel.confirmation, confirmed_by="someone else")  # no longer the signed content
        analysis = self.compare(panel)
        self.assertEqual(analysis.status, am.REGISTRATION_REQUIRED)
        self.saved(panel)
        document, _images = ap.read_project(self.project)
        self.assertEqual(document["registration"]["kind"], ap.KIND_NONE)
        self.assertIsNone(document["comparison"])

    def test_a_file_cannot_claim_a_status_its_content_does_not_support(self):
        _window, panel = self.analysed()
        self.saved(panel)
        for status in (am.CONFIRMED_COMPARISON, cm.PAIRS_FOUND, "PHYSICALLY_VERIFIED"):
            with self.subTest(status=status):
                copy = self.root / f"edited {status}.mcproj"
                shutil.copy(self.project, copy)
                rewrite(copy, change=lambda d, s=status: d["result"].__setitem__("status", s))
                with self.assertRaises(ap.ProjectRefused) as refused:
                    ap.read_project(copy)
                self.assertEqual(refused.exception.code, ap.INVALID)


def _document_with(panel, view) -> dict:
    """The result document of the shown analysis with a stand-in comparison (status raising is the point under test)."""
    document = pj.analysis_document(panel.analysis, panel.inputs, panel.paths[FE], None,
                                    {"component": "magnitude", "fe": [], "experimental": []})
    document["result"]["status"] = view.status
    document["comparison"] = pj._comparison_document(view)
    return document


class SourceChecksTests(_Project):
    def opened_after_change(self, change):
        _window, panel = self.analysed()
        self.saved(panel)
        change()
        return self.reopened()[1]

    def test_opening_hashes_nothing_and_analyze_stays_blocked(self):
        _window, panel = self.analysed()
        self.saved(panel)
        _second, again = self.reopened()
        self.assertFalse(again.source_check.hashed)
        self.assertEqual(self.row(again, pj.ROLE_ODB).state, pj.NOT_CHECKED)
        self.assertFalse(again.analyze_button.isEnabled())
        self.assertFalse(again.analyze())
        self.assertIsNotNone(again.snapshot)
        self.assertEqual(self.runner.calls[-1:], self.runner.calls[:1])  # the earlier extraction only

    def test_unchanged_sources_unlock_a_fresh_analysis(self):
        _window, panel = self.analysed()
        calls = len(self.runner.calls)
        self.saved(panel)
        _second, again = self.reopened()
        check = self.check(again)
        self.assertTrue(check.can_analyze)
        self.assertEqual(self.row(again, pj.ROLE_ODB).state, pj.UNCHANGED)
        self.assertEqual(self.row(again, pj.ROLE_EXPERIMENTAL).state, pj.UNCHANGED)
        self.assertEqual(self.row(again, pj.ROLE_PACKAGE).state, pj.UNCHANGED)
        self.assertTrue(again.analyze_button.isEnabled())
        self.assertTrue(again.analyze())
        self.wait(again)
        self.assertEqual(again.state, DONE, again.message.text())
        self.assertIsNone(again.snapshot)
        self.assertIsNotNone(again.inputs)
        self.assertEqual(again.analysis.status, am.REGISTRATION_REQUIRED)
        self.assertEqual(len(self.runner.calls), calls)  # the saved extraction is reused
        self.assertIsNone(again.project_path)  # a fresh result does not overwrite the snapshot's file by itself
        labels = [label.text() for label in again.result_box.findChildren(analyze_panel.QLabel)]
        self.assertTrue(any(text.startswith("Fresh analysis of the current files") for text in labels))

    def test_a_fresh_analysis_uses_the_saved_set_without_asking(self):
        nodes = self.nodes()
        unv = self.unv(nodes, sets=(("Fitted A", (50.0, 75.0)), ("Fitted B", (51.0, 76.0, 90.0))), name="sets.unv")
        window = self.window()
        panel = window.analyze
        panel.choose_file(FE, str(self.odb))
        panel.choose_file(EXPERIMENTAL, str(unv))
        self.run_analysis(panel)
        self.assertTrue(panel.choose_set(1))
        self.wait(panel)
        self.saved(panel)
        _second, again = self.reopened()
        self.check(again)
        self.assertTrue(again.analyze())
        self.wait(again)
        self.assertEqual(again.state, DONE, again.message.text())
        self.assertEqual(again.analysis.set_index, 1)

    def test_a_confirmation_is_not_picked_up_by_a_fresh_analysis(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        self.compare(panel)
        self.saved(panel)
        _second, again = self.reopened()
        self.check(again)
        self.assertEqual(self.row(again, pj.ROLE_REGISTRATION).state, pj.NOT_REVALIDATED)
        self.assertIn("the confirmation file is there", self.row(again, pj.ROLE_REGISTRATION).detail)
        self.assertTrue(again.analyze())
        self.wait(again)
        self.assertEqual(again.analysis.status, am.REGISTRATION_REQUIRED)  # never carried over from the file
        self.assertIsNone(again.confirmation)
        labels = [label.text() for label in again.result_box.findChildren(analyze_panel.QLabel)]
        self.assertTrue(any(str(self.confirmation_path) in text for text in labels))
        self.assertTrue(again.open_confirmation(str(self.confirmation_path)))
        self.wait(again)
        again.confirmation_view.use_existing()
        self.assertTrue(again.compare_confirmed())
        self.wait(again)
        self.assertEqual(again.analysis.status, am.CONFIRMED_COMPARISON)  # through the full revalidation only

    def test_a_file_gone_after_the_check_keeps_the_saved_view_marked_as_saved(self):
        _window, panel = self.analysed()
        before = displayed(panel)
        self.saved(panel)
        _second, again = self.reopened()
        self.assertTrue(self.check(again).can_analyze)
        self.exp_path.unlink()
        self.assertFalse(again.analyze())
        self.assertIsNotNone(again.snapshot)  # not a current result
        self.assertEqual(displayed(again), before)
        self.assertIn("not found", again.file_error.text())
        self.assertEqual(again.status_label.property("state"), "chosen")

    def test_an_old_record_without_the_odb_size_saves_the_file_size(self):
        _window, panel = self.analysed()
        manifest = Path(panel.inputs.full_fe.manifest_path)
        path = manifest.parent / svc.SOURCE_RECORD
        record = json.loads(path.read_text(encoding="utf-8"))
        del record["odb"]["size"]
        path.write_text(json.dumps(record), encoding="utf-8")
        self.saved(panel)
        self.assertEqual(ap.read_project(self.project)[0]["sources"]["fe_odb"]["size"], self.odb.stat().st_size)

    def test_the_reminder_of_the_confirmation_goes_once_it_is_compared(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        self.compare(panel)
        self.saved(panel)
        _second, again = self.reopened()
        self.check(again)
        self.assertTrue(again.analyze())
        self.wait(again)
        self.assertTrue(again.open_confirmation(str(self.confirmation_path)))
        self.wait(again)
        again.confirmation_view.use_existing()
        self.assertTrue(again.compare_confirmed())
        self.wait(again)
        labels = [label.text() for label in again.result_box.findChildren(analyze_panel.QLabel)]
        self.assertTrue(any(text.startswith("Fresh analysis") for text in labels))
        self.assertFalse(any("It is not applied by itself" in text for text in labels))

    def test_a_changed_experimental_file_keeps_the_view_and_blocks_analyze(self):
        _window, panel = self.analysed()
        before = displayed(panel)
        self.saved(panel)
        with open(self.exp_path, "ab") as stream:
            stream.write(b"\n")
        _second, again = self.reopened()
        self.assertEqual(displayed(again), before)
        self.assertEqual(self.row(again, pj.ROLE_EXPERIMENTAL).state, pj.NOT_CHECKED)
        check = self.check(again)
        self.assertFalse(check.can_analyze)
        self.assertEqual(self.row(again, pj.ROLE_EXPERIMENTAL).state, pj.CHANGED)
        self.assertFalse(again.analyze_button.isEnabled())
        self.assertFalse(again.analyze())
        self.assertEqual(displayed(again), before)

    def test_same_size_different_content_is_found_only_by_the_hash(self):
        _window, panel = self.analysed()
        self.saved(panel)
        data = bytearray(self.exp_path.read_bytes())
        data[0] = ord("X") if data[0] != ord("X") else ord("Y")
        self.exp_path.write_bytes(bytes(data))
        _second, again = self.reopened()
        self.assertEqual(self.row(again, pj.ROLE_EXPERIMENTAL).state, pj.NOT_CHECKED)
        self.assertFalse(self.check(again).can_analyze)
        self.assertEqual(self.row(again, pj.ROLE_EXPERIMENTAL).state, pj.CHANGED)

    def test_a_changed_odb_blocks_analyze(self):
        _window, panel = self.analysed()
        self.saved(panel)
        self.odb.write_bytes(b"another model; same name")
        _second, again = self.reopened()
        self.assertFalse(self.check(again).can_analyze)
        self.assertEqual(self.row(again, pj.ROLE_ODB).state, pj.CHANGED)

    def test_absent_files_keep_the_view_and_block_analyze(self):
        _window, panel = self.analysed()
        before = displayed(panel)
        self.saved(panel)
        self.odb.unlink()
        self.exp_path.unlink()
        _second, again = self.reopened()
        self.assertEqual(displayed(again), before)
        self.assertEqual(self.row(again, pj.ROLE_ODB).state, pj.NOT_CHECKED)
        self.assertFalse(again.analyze_button.isEnabled())
        self.assertFalse(self.check(again).can_analyze)
        self.assertEqual(self.row(again, pj.ROLE_ODB).state, pj.MISSING)
        self.assertEqual(self.row(again, pj.ROLE_EXPERIMENTAL).state, pj.MISSING)
        self.assertFalse(again.analyze())
        self.assertIsNotNone(again.snapshot)

    def test_a_moved_file_is_accepted_by_its_content_and_another_is_not(self):
        _window, panel = self.analysed()
        self.saved(panel)
        moved = self.root / "moved folder"
        moved.mkdir()
        new_unv = moved / self.exp_path.name
        shutil.move(self.exp_path, new_unv)
        other = moved / "other.unv"
        other.write_bytes(new_unv.read_bytes() + b"\n")
        _second, again = self.reopened()
        self.assertEqual(again.choose_file(EXPERIMENTAL, str(other)), "")
        self.wait(again)
        self.assertFalse(again.source_check.can_analyze)
        self.assertEqual(self.row(again, pj.ROLE_EXPERIMENTAL).state, pj.CHANGED)
        again.choose_file(EXPERIMENTAL, str(new_unv))
        self.wait(again)
        self.assertTrue(again.source_check.can_analyze)
        self.assertEqual(self.row(again, pj.ROLE_EXPERIMENTAL).state, pj.MOVED)
        self.assertIsNotNone(again.snapshot)  # still the saved view until Analyze

    def test_save_as_records_a_confirmed_new_place_and_keeps_the_old_one(self):
        _window, panel = self.analysed()
        self.saved(panel)
        saved_at = ap.read_project(self.project)[0]["saved_at"]
        moved = self.root / "moved folder"
        moved.mkdir()
        new_unv = moved / self.exp_path.name
        shutil.move(self.exp_path, new_unv)
        _second, again = self.reopened()
        again.choose_file(EXPERIMENTAL, str(new_unv))
        self.wait(again)
        second = self.root / "second.mcproj"
        self.saved(again, second)
        document = ap.read_project(second)[0]
        experimental = document["sources"]["experimental"]
        self.assertEqual(experimental["path"], str(new_unv.resolve()))
        self.assertEqual(experimental["relocated_from"], [str(self.exp_path)])
        self.assertEqual(experimental["sha256"], base.sha(new_unv))
        self.assertEqual(document["saved_at"], saved_at)
        self.assertEqual(ap.read_project(self.project)[0]["sources"]["experimental"]["path"], str(self.exp_path))

    def test_a_moved_package_is_found_by_its_content_without_abaqus(self):
        _window, panel = self.analysed()
        calls = len(self.runner.calls)
        manifest = Path(panel.inputs.full_fe.manifest_path)
        self.saved(panel)
        folder = self.root / "packages elsewhere"
        shutil.move(manifest.parent.parent, folder)
        _second, again = self.reopened()
        self.assertEqual(self.row(again, pj.ROLE_PACKAGE).state, pj.NOT_CHECKED)
        check = self.check(again)
        self.assertTrue(check.can_analyze)
        self.assertEqual(self.row(again, pj.ROLE_PACKAGE).state, pj.MISSING)
        self.assertFalse(again.folder_button.isHidden())
        self.assertTrue(again.choose_folder(str(folder)))
        self.wait(again)
        self.assertEqual(self.row(again, pj.ROLE_PACKAGE).state, pj.MOVED)
        self.assertTrue(again.analyze())
        self.wait(again)
        self.assertEqual(again.state, DONE, again.message.text())
        self.assertEqual(len(self.runner.calls), calls)

    def test_without_the_package_analyze_still_asks_before_abaqus(self):
        _window, panel = self.analysed()
        manifest = Path(panel.inputs.full_fe.manifest_path)
        self.saved(panel)
        shutil.rmtree(manifest.parent.parent)
        _second, again = self.reopened()
        self.check(again)
        self.consent_answer = False
        asked = len(self.consents)
        self.assertTrue(again.analyze())
        self.wait(again)
        self.assertEqual(len(self.consents), asked + 1)  # asked; refused; nothing started (the runner here would fail)
        self.assertIn("Not started", again.message.text())

    def test_the_source_files_are_not_changed(self):
        _window, panel = self.analysed()
        before = (base.sha(self.odb), base.sha(self.exp_path))
        self.saved(panel)
        _second, again = self.reopened()
        self.check(again)
        self.assertEqual((base.sha(self.odb), base.sha(self.exp_path)), before)


NETWORK = "\\\\unreachable-host.invalid\\share\\"


class _FileAccess:
    """Every look at a file while active: Python's own audit events for opening and listing, and the stat calls."""

    active = None
    events = 0  # audit events received, watched or not: only an installed hook raises this

    def __enter__(self):
        _FileAccess.active = self.seen = []
        real_stat, real_exists, real_isfile = os.stat, os.path.exists, os.path.isfile

        def stat(path, *args, **kwargs):
            self.seen.append(str(path))
            return real_stat(path, *args, **kwargs)

        def exists(path):
            self.seen.append(str(path))
            return real_exists(path)

        def isfile(path):
            self.seen.append(str(path))
            return real_isfile(path)

        self.patches = [mock.patch.object(os, "stat", stat), mock.patch.object(os.path, "exists", exists),
                        mock.patch.object(os.path, "isfile", isfile)]
        for patch in self.patches:
            patch.start()
        return self

    def __exit__(self, *_details):
        for patch in self.patches:
            patch.stop()
        _FileAccess.active = None


def _audit(event, args):
    _FileAccess.events += 1
    seen = _FileAccess.active
    if seen is not None and event in ("open", "os.listdir", "os.scandir") and args and isinstance(args[0], (str, os.PathLike)):
        seen.append(os.fspath(args[0]))


# An audit hook can never be removed from its process, and discovery imports every test module before it runs one, so
# a hook installed on import would stay for the whole suite and through interpreter finalization. It lives only in the
# one child process that OfflineOpenTests run in (run_offline_child).
_AUDIT_ACTIVE = False
_OFFLINE_CHILD_CODE = ("import sys; import test_working_draft_r2_project as t; "
                       "sys.exit(t.run_offline_child(sys.argv[1]))")
_OFFLINE_CHILD_LIMIT = 600.0  # seconds: the child is killed after this, and each of its tests is then reported failed
_OFFLINE_CHILD_REPORT = None


class _OfflineChildResult(unittest.TestResult):
    """Each test's audit events; the outcomes are in the base class's own lists."""

    def __init__(self):
        super().__init__()
        self.events = {}

    def startTest(self, test):
        super().startTest(test)
        self.events[test._testMethodName] = -_FileAccess.events

    def stopTest(self, test):
        self.events[test._testMethodName] += _FileAccess.events
        super().stopTest(test)


def run_offline_child(result_path: str) -> int:
    """The child process: install the hook, prove it sees what it must, run every OfflineOpenTests test, record it all."""
    global _AUDIT_ACTIVE
    sys.addaudithook(_audit)
    _AUDIT_ACTIVE = True
    here = Path(__file__)
    with _FileAccess() as watch:  # none of these goes through the watch's stat patches: only the hook can see them
        here.open("rb").close()
        os.listdir(here.parent)
        with os.scandir(here.parent):
            pass
    sees = {"open": str(here) in watch.seen, "os.listdir": str(here.parent) in watch.seen,
            "os.scandir": watch.seen.count(str(here.parent)) >= 2}
    result = _OfflineChildResult()
    unittest.defaultTestLoader.loadTestsFromTestCase(OfflineOpenTests).run(result)
    tests = {name: {"outcome": "passed", "detail": "", "events": events} for name, events in result.events.items()}
    other = []
    for kind, found in (("skipped", result.skipped), ("failed", result.failures), ("failed", result.errors)):
        for test, detail in found:
            name = getattr(test, "_testMethodName", None)
            if name in tests:
                tests[name].update(outcome=kind, detail=tests[name]["detail"] + detail)
            else:  # a class-level problem belongs to no one test
                other.append(f"{test}: {detail}")
    Path(result_path).write_text(json.dumps({"pid": os.getpid(), "hook_active": _AUDIT_ACTIVE, "hook_sees": sees,
                                             "tests": tests, "other": other}), encoding="utf-8")
    return 0 if result.wasSuccessful() and not other else 1


def start_offline_child(code: str = _OFFLINE_CHILD_CODE, limit: float = _OFFLINE_CHILD_LIMIT) -> dict:
    """Run one child to its end or its limit. Its exit code, output and result file all come back, whatever happened."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "offline_result.json"
        environment = dict(os.environ, PYTHONIOENCODING="utf-8")
        environment.setdefault("QT_QPA_PLATFORM", "offscreen")
        report = {"returncode": None, "timed_out": False, "result": None}
        try:
            done = subprocess.run([sys.executable, "-X", "faulthandler", "-c", code, str(path)], cwd=str(ROOT / "tests"),
                                  env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=limit, check=False)
        except subprocess.TimeoutExpired as expired:  # subprocess.run has already killed it and waited for it
            report.update(timed_out=True, stdout=_text(expired.stdout), stderr=_text(expired.stderr))
        else:
            report.update(returncode=done.returncode, stdout=done.stdout, stderr=done.stderr)
        if path.is_file():
            report["result"] = json.loads(path.read_text(encoding="utf-8"))
    return report


def _text(output) -> str:
    return output.decode("utf-8", "replace") if isinstance(output, bytes) else (output or "")


def offline_verdict(report: dict, name: str) -> tuple:
    """(passed, skipped or failed; the reason) of one test. Anything but a clean child under a working hook is a failure."""
    tail = (f"exit code {report['returncode']}, timed out: {report['timed_out']}\n"
            f"--- child stderr\n{report.get('stderr', '')[-4000:]}\n--- child stdout\n{report.get('stdout', '')[-1000:]}")
    result = report["result"]
    if report["timed_out"] or result is None:
        return "failed", "The child process gave no result.\n" + tail
    outcome = result["tests"].get(name)
    everything_passed = (not result["other"] and all(test["outcome"] in ("passed", "skipped")
                                                     for test in result["tests"].values()))
    if report["returncode"] != (0 if everything_passed else 1):
        return "failed", "The child process did not end as its results require.\n" + tail
    if not result["hook_active"] or not all(result["hook_sees"].values()):
        return "failed", f"The audit hook was not working: {result['hook_sees']}\n" + tail
    if outcome is None:
        return "failed", "This test did not run in the child process.\n" + "\n".join(result["other"]) + "\n" + tail
    if outcome["outcome"] == "skipped":
        return "skipped", outcome["detail"]
    if outcome["outcome"] == "failed":
        return "failed", outcome["detail"] + "\n" + tail
    if outcome["events"] <= 0:
        return "failed", "The hook received no event during this test.\n" + tail
    return "passed", ""


def _offline_report() -> dict:
    global _OFFLINE_CHILD_REPORT
    if _OFFLINE_CHILD_REPORT is None:
        _OFFLINE_CHILD_REPORT = start_offline_child()
        said = [line for line in _OFFLINE_CHILD_REPORT.get("stderr", "").splitlines()
                if line.strip() and not line.startswith("This plugin does not support")]
        if said:  # whatever the child said beyond the offscreen platform's notices stays visible in the log
            sys.stderr.write("[OfflineOpenTests child process]\n" + "\n".join(said) + "\n")
    return _OFFLINE_CHILD_REPORT


class OfflineOpenTests(_Project):
    """Open Project reads only the file chosen; the saved paths are text until Check source files.

    These tests need the audit hook, so all of them run in one child process that has it. Here each reports its own
    outcome there under its own name; see run_offline_child and OfflineOpenIsolationTests.
    """

    def run(self, result=None):
        if _AUDIT_ACTIVE:
            return super().run(result)
        result = self.defaultTestResult() if result is None else result
        result.startTest(self)
        try:
            kind, reason = offline_verdict(_offline_report(), self._testMethodName)
            if kind == "skipped":
                result.addSkip(self, reason)
            elif kind == "passed":
                result.addSuccess(self)
            else:
                try:
                    self.fail(reason)
                except self.failureException:
                    result.addFailure(self, sys.exc_info())
        except Exception:  # noqa: BLE001 - a failure of the reporting itself is this test's error, never a pass
            result.addError(self, sys.exc_info())
        finally:
            result.stopTest(self)
        return result

    def network_project(self, panel) -> Path:
        """A real project whose saved paths all name a host that does not exist."""
        self.saved(panel)

        def move(document):
            sources = document["sources"]
            sources["fe_odb"]["path"] = NETWORK + "model.odb"
            sources["fe_package"]["manifest_path"] = NETWORK + "package\\manifest.json"
            sources["experimental"]["path"] = sources["experimental"]["source_path"] = NETWORK + "data.unv"
            if document["registration"]["kind"] != ap.KIND_NONE:
                document["registration"]["confirmation_path"] = NETWORK + "confirmation.json"
                document["registration"]["draft_path"] = NETWORK + "draft.json"

        rewrite(self.project, change=move)
        return self.project

    def open_watched(self, path):
        window = pw.ProductionWindow(analyze_options={"runner": self.fail_runner, "discover": base.FOUND,
                                                      "consent": self.consent})
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        panel = window.analyze
        window.show()
        self.app.processEvents()
        with _FileAccess() as watch:
            self.assertTrue(panel.open_project(str(path)))
            self.wait(panel)
            for row in range(len(panel.analysis.nearest_rows)):
                panel.show_candidate(row)
            self.app.processEvents()
        return panel, watch.seen

    def test_no_saved_network_path_is_looked_at(self):
        _window, panel = self.analysed()
        before = displayed(panel)
        path = self.network_project(panel)
        again, seen = self.open_watched(path)
        self.assertEqual(again.state, DONE, again.message.text())
        self.assertEqual([item for item in seen if "unreachable-host" in item], [])
        self.assertTrue(any(item.endswith(path.name) for item in seen))  # the watch does see the project being read
        self.assertEqual(displayed(again), before)

    def test_no_saved_network_confirmation_is_looked_at(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        self.compare(panel)
        before = displayed(panel)
        path = self.network_project(panel)
        again, seen = self.open_watched(path)
        self.assertEqual([item for item in seen if "unreachable-host" in item], [])
        self.assertEqual(displayed(again), before)
        self.assertEqual(again.status_label.text(), am.CONFIRMED_COMPARISON)
        self.assertEqual(self.row(again, pj.ROLE_REGISTRATION).state, pj.NOT_CHECKED)
        self.assertIn("unreachable-host", self.row(again, pj.ROLE_REGISTRATION).path)

    def test_no_local_source_is_looked_at_either(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        self.compare(panel)
        manifest = Path(panel.inputs.full_fe.manifest_path)
        self.saved(panel)
        again, seen = self.open_watched(self.project)
        named = (str(self.odb), str(self.exp_path), str(manifest), str(self.confirmation_path), str(self.draft_path))
        self.assertEqual([item for item in seen if any(place in item for place in named)], [])
        self.assertIsNotNone(again.snapshot)

    def test_the_services_that_read_sources_are_not_called(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        self.compare(panel)
        path = self.network_project(panel)
        refuse = AssertionError("opening touches no source")
        with mock.patch.object(pj.gr, "read_draft", side_effect=refuse), mock.patch.object(pj.pm, "file_identity", side_effect=refuse), \
                mock.patch.object(pj.fpi, "identify", side_effect=refuse), mock.patch.object(svc, "existing_packages", side_effect=refuse), \
                mock.patch.object(svc, "hash_file", side_effect=refuse), mock.patch.object(svc, "read_source_record", side_effect=refuse):
            again, _seen = self.open_watched(path)
        self.assertEqual(again.state, DONE, again.message.text())

    def test_every_external_source_is_not_checked_until_asked(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        self.compare(panel)
        self.saved(panel)
        _second, again = self.reopened()
        self.assertEqual({row.role: row.state for row in again.source_check.rows},
                         {pj.ROLE_ODB: pj.NOT_CHECKED, pj.ROLE_PACKAGE: pj.NOT_CHECKED,
                          pj.ROLE_EXPERIMENTAL: pj.NOT_CHECKED, pj.ROLE_REGISTRATION: pj.NOT_CHECKED})
        self.assertFalse(again.source_check.hashed)
        self.check(again)
        self.assertEqual(self.row(again, pj.ROLE_ODB).state, pj.UNCHANGED)
        self.assertEqual(self.row(again, pj.ROLE_REGISTRATION).state, pj.NOT_REVALIDATED)

    def test_analyze_does_not_look_at_a_path_before_the_check(self):
        _window, panel = self.analysed()
        path = self.network_project(panel)
        again, _seen = self.open_watched(path)
        with _FileAccess() as watch:
            self.assertFalse(again.analyze())
        self.assertEqual([item for item in watch.seen if "unreachable-host" in item], [])
        self.assertIsNotNone(again.snapshot)
        self.assertIn("blocked", again.message.text())

    def test_saved_shapes_and_results_need_no_source(self):
        _window, panel = self.analysed()
        self.confirmed(panel)
        self.compare(panel)
        path = self.network_project(panel)
        again, _seen = self.open_watched(path)
        self.assertIsNotNone(again.saved_shapes[FE].image.source)
        self.assertIsNotNone(again.saved_shapes[EXPERIMENTAL].image.source)
        self.assertIn("pairs", again.tables)
        self.assertIn("mac", again.tables)

    def test_the_explicit_check_of_unavailable_paths_blocks_analyze(self):
        _window, panel = self.analysed()
        self.saved(panel)
        gone = self.root / "not mounted"

        def move(document):
            sources = document["sources"]
            sources["fe_odb"]["path"] = str(gone / "model.odb")
            sources["fe_package"]["manifest_path"] = str(gone / "package" / "manifest.json")
            sources["experimental"]["path"] = sources["experimental"]["source_path"] = str(gone / "data.unv")

        rewrite(self.project, change=move)
        _second, again = self.reopened()
        self.assertEqual(self.row(again, pj.ROLE_ODB).state, pj.NOT_CHECKED)
        self.assertFalse(self.check(again).can_analyze)
        self.assertEqual(self.row(again, pj.ROLE_ODB).state, pj.MISSING)
        self.assertEqual(self.row(again, pj.ROLE_EXPERIMENTAL).state, pj.MISSING)
        self.assertEqual(self.row(again, pj.ROLE_PACKAGE).state, pj.MISSING)
        self.assertFalse(again.analyze())


class OfflineOpenIsolationTests(unittest.TestCase):
    """MAT-4.F2: the hook stays out of this process, and the tests above really ran under it, in another process."""

    def test_importing_this_module_installs_no_hook_in_this_process(self):
        self.assertFalse(_AUDIT_ACTIVE)
        here = Path(__file__)
        before = _FileAccess.events
        with _FileAccess() as watch:
            here.open("rb").close()
            os.listdir(here.parent)
        self.assertEqual(watch.seen, [])
        self.assertEqual(_FileAccess.events, before)
        tree = ast.parse(here.read_text(encoding="utf-8"))
        callers = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)
                   and any(isinstance(call, ast.Attribute) and call.attr == "addaudithook" for call in ast.walk(node))]
        at_import = [node for node in tree.body if not isinstance(node, (ast.FunctionDef, ast.ClassDef))
                     and any(isinstance(call, ast.Attribute) and call.attr == "addaudithook" for call in ast.walk(node))]
        self.assertEqual(callers, ["run_offline_child"])
        self.assertEqual(at_import, [])

    def test_every_test_ran_under_the_hook_in_another_process(self):
        report = _offline_report()
        result = report["result"]
        self.assertIsNotNone(result, report)
        self.assertNotEqual(result["pid"], os.getpid())
        self.assertTrue(result["hook_active"])
        self.assertEqual(result["hook_sees"], {"open": True, "os.listdir": True, "os.scandir": True})
        names = unittest.defaultTestLoader.getTestCaseNames(OfflineOpenTests)
        self.assertEqual(len(names), 8)
        self.assertEqual(sorted(result["tests"]), sorted(names))
        for name in names:
            self.assertGreater(result["tests"][name]["events"], 0, name)

    def test_an_abort_reaches_the_parent_with_its_code_and_stderr(self):
        report = start_offline_child("import sys; sys.stderr.write('said before the abort'); sys.stderr.flush(); "
                                     "import os; os.abort()", 60.0)
        self.assertNotIn(report["returncode"], (0, 1))
        kind, reason = offline_verdict(report, "any_test")
        self.assertEqual(kind, "failed")
        self.assertIn(f"exit code {report['returncode']}", reason)
        self.assertIn("said before the abort", reason)

    def test_a_clean_exit_without_results_is_not_a_pass(self):
        report = start_offline_child("raise SystemExit(0)", 60.0)
        self.assertEqual(report["returncode"], 0)
        self.assertEqual(offline_verdict(report, "any_test")[0], "failed")

    def test_a_child_over_its_limit_is_stopped_and_reported(self):
        started = time.monotonic()
        report = start_offline_child("import sys, time; print('still here', flush=True); time.sleep(60)", 3.0)
        self.assertLess(time.monotonic() - started, 30.0)
        self.assertTrue(report["timed_out"])
        kind, reason = offline_verdict(report, "any_test")
        self.assertEqual(kind, "failed")
        self.assertIn("timed out: True", reason)

    def verdict_of(self, returncode, outcome="passed", other=(), events=5, sees=True):
        result = {"pid": 1, "hook_active": True, "hook_sees": {"open": sees}, "other": list(other),
                  "tests": {"named": {"outcome": outcome, "detail": "the child's traceback", "events": events}}}
        return offline_verdict({"returncode": returncode, "timed_out": False, "result": result, "stdout": "",
                                "stderr": "the child's stderr"}, "named")

    def test_each_way_a_child_can_be_wrong_is_a_failure(self):
        self.assertEqual(self.verdict_of(0), ("passed", ""))
        kind, reason = self.verdict_of(1, outcome="failed")
        self.assertEqual(kind, "failed")
        self.assertIn("the child's traceback", reason)
        self.assertIn("the child's stderr", reason)
        for wrong in (self.verdict_of(1),  # exit 1 although all passed
                      self.verdict_of(-6),  # every test passed, then the process crashed while ending
                      self.verdict_of(134),
                      self.verdict_of(0, outcome="failed"),  # exit 0 although a test failed
                      self.verdict_of(0, other=("class problem",)),
                      self.verdict_of(0, events=0),  # no hook event during the test
                      self.verdict_of(0, sees=False)):  # the hook does not see what it must
            self.assertEqual(wrong[0], "failed", wrong)
        self.assertEqual(self.verdict_of(0, outcome="skipped")[0], "skipped")


class DamagedFileTests(_Project):
    def good(self) -> Path:
        _window, panel = self.analysed()
        return self.saved(panel)

    def refused(self, path, code):
        with self.assertRaises(ap.ProjectRefused) as caught:
            ap.read_project(path)
        self.assertEqual(caught.exception.code, code, str(caught.exception))

    def test_truncated_and_foreign_files_are_refused(self):
        path = self.good()
        data = path.read_bytes()
        for name, content in (("truncated", data[:len(data) // 2]), ("empty", b""), ("text", b"not a project"),
                              ("pickle", b"\x80\x04\x95\x00")):
            with self.subTest(kind=name):
                target = self.root / f"{name}.mcproj"
                target.write_bytes(content)
                self.refused(target, ap.NOT_A_PROJECT)

    def test_a_changed_byte_in_a_member_is_refused(self):
        path = self.good()
        with zipfile.ZipFile(path) as archive:
            members = {name: archive.read(name) for name in archive.namelist()}
        name = next(n for n in members if n.startswith("images/"))
        members[name] = members[name][:-1] + bytes([members[name][-1] ^ 1])
        with zipfile.ZipFile(path, "w") as archive:
            for key, value in members.items():
                archive.writestr(key, value)
        self.refused(path, ap.DAMAGED)

    def test_another_version_is_refused_by_name(self):
        path = self.good()
        with zipfile.ZipFile(path) as archive:
            members = {name: archive.read(name) for name in archive.namelist()}
        manifest = json.loads(members[ap.MANIFEST])
        manifest["schema"] = "universal/analysis-project/v2"
        members[ap.MANIFEST] = json.dumps(manifest).encode()
        with zipfile.ZipFile(path, "w") as archive:
            for key, value in members.items():
                archive.writestr(key, value)
        self.refused(path, ap.OTHER_VERSION)

    def test_an_unknown_member_is_refused_and_nothing_is_unpickled(self):
        path = self.good()
        import pickle

        class Boom:
            def __reduce__(self):
                return (os.abort, ())

        for name in ("data.pkl", "../outside.png", "images/../../x.png", "model.odb", "images/fe_1.png.exe"):
            with self.subTest(name=name):
                copy = self.root / "with member.mcproj"
                shutil.copy(path, copy)
                rewrite(copy, add={name: pickle.dumps(Boom())})
                self.refused(copy, ap.DAMAGED)

    def test_oversized_members_are_refused_before_they_are_read(self):
        path = self.good()
        copy = self.root / "large.mcproj"
        with zipfile.ZipFile(copy, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(ap.PROJECT, b"0" * (ap.MAX_PROJECT_JSON_BYTES + 1))
            archive.writestr(ap.MANIFEST, b"{}")
        self.refused(copy, ap.TOO_LARGE)
        self.assertTrue(path.exists())

    def test_too_many_pictures_and_a_huge_picture_are_refused(self):
        path = self.good()
        png = next(iter(ap.read_project(path)[1].values()))
        many = self.root / "many.mcproj"
        shutil.copy(path, many)
        rewrite(many, add={f"images/fe_{1000 + i}.png": png for i in range(ap.MAX_IMAGES + 1)})
        self.refused(many, ap.TOO_LARGE)
        huge = bytearray(png)
        huge[16:24] = (100000).to_bytes(4, "big") * 2
        with self.assertRaises(ap.ProjectRefused) as caught:
            ap._check_png("images/fe_1.png", bytes(huge))
        self.assertEqual(caught.exception.code, ap.TOO_LARGE)

    def test_repeated_keys_and_nan_are_refused(self):
        path = self.good()
        with zipfile.ZipFile(path) as archive:
            members = {name: archive.read(name) for name in archive.namelist()}
        for text in (b'{"schema": 1, "schema": 2}', b'{"schema": NaN}'):
            with self.subTest(text=text):
                changed = dict(members, **{ap.PROJECT: text})
                copy = self.root / "strict.mcproj"
                listed = {n: {"size": len(d), "sha256": hashlib.sha256(d).hexdigest()} for n, d in changed.items()
                          if n != ap.MANIFEST}
                changed[ap.MANIFEST] = json.dumps({"schema": ap.SCHEMA, "members": listed,
                                                   "members_sha256": ap._members_hash(listed)}).encode()
                with zipfile.ZipFile(copy, "w") as archive:
                    for key, value in changed.items():
                        archive.writestr(key, value)
                self.refused(copy, ap.DAMAGED)

    def test_a_missing_field_and_a_comparison_without_registration_are_refused(self):
        path = self.good()
        for change in (lambda d: d.pop("sources"), lambda d: d["result"].pop("nearest_rows"),
                       lambda d: d.__setitem__("extra", 1),
                       lambda d: d["result"].__setitem__("fe_rows", "a table")):
            copy = self.root / "edited.mcproj"
            shutil.copy(path, copy)
            rewrite(copy, change=change)
            self.refused(copy, ap.INVALID)

    def test_a_corrupt_project_leaves_the_shown_result_and_says_why(self):
        _window, panel = self.analysed()
        before = displayed(panel)
        bad = self.root / "bad.mcproj"
        bad.write_bytes(b"not a project")
        self.assertTrue(panel.open_project(str(bad)))
        self.wait(panel)
        self.assertEqual(panel.state, DONE)
        self.assertEqual(displayed(panel), before)
        self.assertIsNone(panel.snapshot)
        self.assertIsNotNone(panel.inputs)
        self.assertIn("Project not opened", panel.message.text())

    def test_a_corrupt_project_on_an_empty_page_changes_nothing(self):
        window = self.window()
        panel = window.analyze
        bad = self.root / "bad.mcproj"
        bad.write_bytes(b"PK\x03\x04broken")
        self.assertTrue(panel.open_project(str(bad)))
        self.wait(panel)
        self.assertEqual(panel.state, analyze_panel.IDLE)
        self.assertIsNone(panel.analysis)
        self.assertIn("Project not opened", panel.message.text())


class AtomicSaveTests(_Project):
    def temporaries(self):
        return [path for path in self.root.iterdir() if path.name.endswith(".tmp")]

    def test_a_failed_write_keeps_the_existing_project_and_leaves_nothing(self):
        _window, panel = self.analysed()
        self.saved(panel)
        before = self.project.read_bytes()
        with mock.patch.object(ap.os, "replace", side_effect=OSError("disk full")):
            self.assertTrue(panel.save_project())
            self.wait(panel)
        self.assertIn("Project not saved", panel.message.text())
        self.assertEqual(self.project.read_bytes(), before)
        self.assertEqual(self.temporaries(), [])
        self.assertEqual(panel.state, DONE)
        self.assertIsNotNone(panel.analysis)

    def test_a_write_that_does_not_read_back_is_not_kept(self):
        _window, panel = self.analysed()
        self.saved(panel)
        before = self.project.read_bytes()
        with mock.patch.object(ap, "project_bytes", return_value=b"partial"):
            self.assertTrue(panel.save_project())
            self.wait(panel)
        self.assertIn("Project not saved", panel.message.text())
        self.assertEqual(self.project.read_bytes(), before)
        self.assertEqual(self.temporaries(), [])

    def test_cancel_during_save_leaves_no_file_and_keeps_the_result(self):
        _window, panel = self.analysed()
        before = displayed(panel)
        started = threading.Event()
        real = sm.run_render

        def slow(*args):
            started.set()
            time.sleep(0.05)
            return real(*args)

        with mock.patch.object(sm, "run_render", side_effect=slow):
            self.assertTrue(panel.save_project_as(str(self.project)))
            end = time.monotonic() + 30
            while not started.is_set() and time.monotonic() < end:
                self.app.processEvents()
                time.sleep(0.005)
            self.assertEqual(panel.state, RUNNING)
            panel.cancel()
            self.wait(panel)
        self.assertFalse(self.project.exists())
        self.assertEqual(self.temporaries(), [])
        self.assertEqual(panel.state, DONE)
        self.assertEqual(displayed(panel), before)

    def test_a_source_file_is_never_overwritten(self):
        _window, panel = self.analysed()
        odb, unv = base.sha(self.odb), base.sha(self.exp_path)
        for target in (self.odb, self.exp_path, Path(panel.inputs.full_fe.manifest_path)):
            with self.subTest(target=target.name):
                self.assertTrue(panel.save_project_as(str(target)))
                self.wait(panel)
                self.assertIn("Project not saved", panel.message.text())
        self.assertEqual((base.sha(self.odb), base.sha(self.exp_path)), (odb, unv))

    def test_a_source_named_like_a_project_is_refused(self):
        _window, panel = self.analysed()
        document = pj.analysis_document(panel.analysis, panel.inputs, panel.paths[FE], None,
                                        {"component": "magnitude", "fe": [], "experimental": []})
        target = self.root / "source.mcproj"
        target.write_bytes(b"precious")
        with self.assertRaises(ap.ProjectRefused):
            ap.write_project(document, {}, target, protected=(str(target),))
        self.assertEqual(target.read_bytes(), b"precious")

    def test_save_overwrites_the_same_project_and_save_needs_a_result(self):
        window = self.window()
        panel = window.analyze
        self.assertFalse(panel.can_save())
        self.assertFalse(panel.save_project())
        self.assertFalse(panel.save_project_button.isEnabled())
        self.assertFalse(window.project_actions["save"].isEnabled())
        panel.choose_file(FE, str(self.odb))
        self.exp_path = self.unv(self.nodes(), reg3.freqs())
        panel.choose_file(EXPERIMENTAL, str(self.exp_path))
        self.run_analysis(panel)
        self.assertTrue(panel.can_save())
        self.assertTrue(window.project_actions["save"].isEnabled())
        self.saved(panel)
        self.assertEqual(panel.project_path, self.project)
        self.assertIn(self.project.name, window.windowTitle())
        self.assertTrue(panel.save_project())
        self.wait(panel)
        self.assertEqual(ap.read_project(self.project)[0]["result"]["status"], am.REGISTRATION_REQUIRED)


class ResponsivenessAndSizeTests(_Project):
    def ticks_during(self, panel, start) -> int:
        ticks = 0
        self.assertTrue(start())
        end = time.monotonic() + 120
        while panel.busy() and time.monotonic() < end:
            self.app.processEvents()
            ticks += 1
            time.sleep(0.002)
        self.assertFalse(panel.busy())
        return ticks

    def test_the_window_keeps_working_during_a_slow_save(self):
        _window, panel = self.analysed()
        real = sm.run_render

        def slow(*args):
            time.sleep(0.02)
            return real(*args)

        with mock.patch.object(sm, "run_render", side_effect=slow):
            ticks = self.ticks_during(panel, lambda: panel.save_project_as(str(self.project)))
        self.assertGreater(ticks, 20)

    def test_the_window_keeps_working_during_a_slow_open_and_check(self):
        _window, panel = self.analysed()
        self.saved(panel)
        window = pw.ProductionWindow(analyze_options={"runner": self.fail_runner, "discover": base.FOUND,
                                                      "consent": self.consent})
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        other = window.analyze
        real = pj.open_project

        def slow(path):
            time.sleep(0.2)
            return real(path)

        with mock.patch.object(pj, "open_project", side_effect=slow):
            self.assertGreater(self.ticks_during(other, lambda: other.open_project(str(self.project))), 20)
        real_hash = svc.hash_file

        def slow_hash(*args, **kwargs):
            time.sleep(0.2)
            return real_hash(*args, **kwargs)

        with mock.patch.object(svc, "hash_file", side_effect=slow_hash):
            self.assertGreater(self.ticks_during(other, other.check_sources), 20)

    def test_a_large_fe_model_gives_a_project_of_the_same_order(self):
        """The saved results grow with the modes shown, not with the FE nodes: the sources are named, not stored."""
        sizes = {}
        for label, side in (("small", 5), ("large", 120)):
            nodes = [(i * side + j + 1, 0.01 * i, 0.01 * j, 0.0) for i in range(side) for j in range(side)]
            self.nodes = lambda n=nodes: n
            self.modes = lambda n=nodes: base.fe_modes(n, count=20)
            self.odb.write_bytes(label.encode() * 100)  # another ODB content: its own extraction, not the earlier one
            window = self.window()
            panel = window.analyze
            panel.choose_file(FE, str(self.odb))
            panel.choose_file(EXPERIMENTAL, str(self.unv(nodes[:25], (20.5, 41.0), name=f"{label}.unv")))
            self.run_analysis(panel)
            self.assertEqual(panel.state, DONE, panel.message.text())
            path = self.saved(panel, self.root / f"{label}.mcproj")
            sizes[label] = (path.stat().st_size, ap.read_project(path)[0]["sources"]["fe_package"]["total_bytes"])
            started = time.monotonic()
            _second, again = self.reopened(path)
            self.assertLess(time.monotonic() - started, 30)
            self.assertEqual(again.state, DONE)
        self.assertGreater(sizes["large"][1], 100 * sizes["small"][1])  # the FE data grew by far
        self.assertLess(sizes["large"][0], 3 * sizes["small"][0])  # the project did not grow with them
        self.assertLess(sizes["large"][0], 40 * 2 ** 20)


class MenuTests(_Project):
    def test_the_three_actions_are_visible(self):
        window = self.window()
        names = {button.text() for button in window.analyze.findChildren(QPushButton)}
        self.assertLessEqual({"Open Project...", "Save Project", "Save Project As..."}, names)
        menu = [action.text() for action in window.menuBar().actions()[0].menu().actions()]
        self.assertLessEqual({"Open Project...", "Save Project", "Save Project As...", "Close Project"}, set(menu))
        self.assertEqual({key: action.shortcut().toString() for key, action in window.project_actions.items()},
                         {"open": "Ctrl+O", "save": "Ctrl+S", "save_as": "Ctrl+Shift+S", "close": ""})

    def test_the_word_project_stays_forbidden_outside_the_commands(self):
        from test_universal_ui2_clean import FORBIDDEN

        for allowed in ("Open Project...", "Save Project", "Save Project As...", "Close Project"):
            self.assertIsNone(FORBIDDEN.search(allowed), allowed)
        for shown in ("Project SP-13", "the project archive", "Project"):
            self.assertIsNotNone(FORBIDDEN.search(shown), shown)

    def test_a_narrow_window_stacks_the_buttons_instead_of_scrolling(self):
        window = self.window()
        """Whatever the platform's font: the row stacks when it would not fit, and returns when it does."""
        direction = analyze_panel.QBoxLayout.Direction
        panel = window.analyze
        room = sum(b.sizeHint().width() for b in (panel.open_project_button, panel.save_project_button,
                                                  panel.save_as_button)) + analyze_panel.PROJECT_ROW_MARGIN
        for extra, expected in ((-20, direction.TopToBottom), (400, direction.LeftToRight)):
            panel.resizeEvent(analyze_panel.QResizeEvent(analyze_panel.QSize(room + extra, 400), panel.size()))
            self.assertEqual(panel.project_row.direction(), expected)
        window.resize(pw.ProductionWindow.minimumWidth(window) + 2000, 800)
        for _ in range(5):
            self.app.processEvents()
        self.assertEqual(panel.project_row.direction(), direction.LeftToRight)
        self.assertEqual(window.stack.currentWidget().horizontalScrollBar().maximum(), 0)

    def test_close_project_empties_the_page_and_keeps_the_file(self):
        _window, panel = self.analysed()
        self.saved(panel)
        _second, again = self.reopened()
        before = self.project.read_bytes()
        self.assertTrue(again.close_project())
        self.assertIsNone(again.snapshot)
        self.assertIsNone(again.analysis)
        self.assertEqual(again.paths[FE], None)
        self.assertTrue(again.saved_shapes[FE].isHidden())
        self.assertEqual(self.project.read_bytes(), before)

    def test_choosing_a_project_while_a_step_runs_is_not_started(self):
        _window, panel = self.analysed()
        self.saved(panel)
        panel.state = RUNNING
        self.assertFalse(panel.open_project(str(self.project)))
        self.assertFalse(panel.save_project())
        panel.state = DONE

    def test_the_format_is_documented(self):
        text = (ROOT / "docs" / "gui" / "PROJECT_FORMAT.md").read_text(encoding="utf-8")
        for word in (ap.SCHEMA, ap.SUFFIX, ap.MANIFEST, ap.PROJECT, "pickle", "not a signature"):
            self.assertIn(word, text)

    def test_the_project_code_has_no_specimen_knowledge_and_no_pickle(self):
        import ast

        for name in ("src/services/analysis_project.py", "src/new_gui/project_model.py", "src/new_gui/project_panel.py"):
            tree = ast.parse((ROOT / name).read_text(encoding="utf-8"))
            imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
            imported |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
            for banned in ("pickle", "marshal", "shelve", "dill", "subprocess", "numpy", "modal_core", "abaqus_bridge"):
                self.assertNotIn(banned, imported, name)
            text = (ROOT / name).read_text(encoding="utf-8")
            for specimen in ("SP-", "SP13", "CFRP", "sandwich", "plate"):
                self.assertNotIn(specimen, text, name)


if __name__ == "__main__":
    unittest.main()
