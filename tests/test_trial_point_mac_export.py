"""TRIAL-MAC-EXPORT-1: the archive of a completed exploratory trial. Synthetic plates only; no Qt, no Abaqus."""

from __future__ import annotations

import csv
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import test_trial_point_mac as plate  # noqa: E402

from services import trial_mac_export as te  # noqa: E402
from services import trial_point_mac as tp  # noqa: E402

LABEL = "EXPLORATORY MAC — UNCONFIRMED GEOMETRIC MAPPING"
PROVENANCE = {"sources": {"verification": "checked by the test", "experimental": {"verified_at_export": True, "sha256": "ab" * 32}},
              "modal_set": {"index": 0, "key": "set-1", "display_name": "Set 1", "record_count": 4},
              "rigid_body_fe_modes": [1, 2, 3, 4, 5, 6]}


def table(data: bytes) -> list:
    return list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))


def members(path) -> dict:
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        return {name: archive.read(name) for name in archive.namelist()}


class _Folder(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.target = self.folder / "trial.zip"

    def left(self) -> list:
        return sorted(p.name for p in self.folder.iterdir())


class ArchiveTests(_Folder):
    @classmethod
    def setUpClass(cls):
        cls.run_ = tp.run_trials(plate.fe_modes(), plate.experimental_modes())

    def setUp(self):
        super().setUp()
        self.assertEqual(te.write_archive(self.target, self.run_, PROVENANCE), self.target)
        self.files = members(self.target)

    def test_the_archive_holds_the_named_files_and_one_matrix_per_usable_placement(self):
        names = [t.name for t in self.run_.trials]
        self.assertEqual(len(names), 40)
        self.assertEqual(list(self.files), ["README.txt", "manifest.json", "placements.csv", "point_mapping.csv",
                                            "families.csv"] + [f"matrices/{name}.csv" for name in names])
        self.assertEqual(self.left(), ["trial.zip"])
        with zipfile.ZipFile(self.target) as archive:
            self.assertEqual(archive.comment.decode("utf-8"), LABEL)

    def test_every_matrix_is_the_runs_own_at_full_precision_with_mode_labels(self):
        run = self.run_
        for trial in run.trials:
            rows = table(self.files[f"matrices/{trial.name}.csv"])
            self.assertEqual((len(rows), {len(r) for r in rows}), (1 + 4, {2 + 14}), trial.name)
            self.assertIn(LABEL, rows[0][0])
            self.assertIn(f"placement {trial.name} ", rows[0][0])
            self.assertEqual(rows[0][1], "EXP frequency (Hz)")
            self.assertEqual(rows[0][2:], [f"FE {n} ({f!r} Hz)" for n, f in zip(run.fe_numbers, run.fe_frequencies)])
            self.assertEqual([r[0] for r in rows[1:]], [f"EXP {n}" for n in run.experimental_numbers])
            self.assertEqual([float(r[1]) for r in rows[1:]], list(run.experimental_frequencies))
            written = np.array([[float(v) for v in r[2:]] for r in rows[1:]])
            np.testing.assert_array_equal(written, trial.mac, err_msg=trial.name)  # exact: nothing rounded or recomputed

    def test_the_placement_table_is_every_trial_with_its_checks(self):
        rows = table(self.files["placements.csv"])
        self.assertEqual(tuple(rows[0]), te.PLACEMENT_HEADERS)
        self.assertEqual(len(rows), 41)
        for row, trial in zip(rows[1:], self.run_.trials):
            cell = dict(zip(rows[0], row))
            self.assertEqual(cell["status"], LABEL)
            self.assertEqual((cell["placement"], cell["fe_face"], int(cell["quarter_turns"])), (trial.name, trial.face, trial.turn))
            self.assertEqual((float(cell["shift_x"]), float(cell["shift_y"])), trial.shift)
            self.assertEqual((int(cell["points"]), int(cell["points_inside_and_near_a_node"]), int(cell["different_fe_nodes"])),
                             (25, 25, 25))
            self.assertEqual([float(cell[k]) for k in ("rms_distance", "max_distance", "edge_margin", "determinant")],
                             [trial.rms_distance, trial.max_distance, trial.edge_margin, trial.determinant])
            self.assertEqual(float(cell["distance_limit"]), self.run_.half_mesh_diagonal)
            self.assertEqual(float(cell["fe_face_z"]), self.run_.faces[trial.face])
            self.assertEqual(cell["scan_z_along_fe_z"], "+1" if trial.face == "T" else "-1")
            self.assertEqual((cell["usable"], cell["rejection_reason"], cell["matrix_file"]),
                             ("yes", "", f"matrices/{trial.name}.csv"))

    def test_the_point_mapping_is_every_point_of_every_placement_marked_unconfirmed(self):
        rows = table(self.files["point_mapping.csv"])
        self.assertEqual(tuple(rows[0]), te.POINT_HEADERS)
        self.assertEqual(len(rows), 1 + 40 * 25)
        body = iter(rows[1:])
        for trial in self.run_.trials:
            for order, point in enumerate(self.run_.point_ids):
                status, name, state, number, exp_id, node, x, y, z = next(body)
                self.assertEqual((status, name, state, int(number), exp_id, node),
                                 ("UNCONFIRMED", trial.name, "mapped under this assumption", order + 1, point,
                                  trial.node_ids[order]))
                self.assertEqual((float(x), float(y), float(z)),
                                 (trial.placed[order, 0], trial.placed[order, 1], self.run_.faces[trial.face]))

    def test_the_families_are_listed_in_the_fixed_order_and_nothing_is_chosen(self):
        rows = table(self.files["families.csv"])
        self.assertEqual(rows[0], ["status", "family", "placement"])
        self.assertEqual([r[1:] for r in rows[1:]], [[letter, name] for letter, names in zip("AB", self.run_.families)
                                                     for name in names])
        self.assertEqual({r[0] for r in rows[1:]}, {LABEL})
        headers = " ".join(te.PLACEMENT_HEADERS + te.POINT_HEADERS + te.FAMILY_HEADERS).lower()
        for word in ("best", "rank", "score", "preferred", "selected", "recommended", "likely"):
            self.assertNotIn(word, headers, word)

    def test_the_manifest_states_the_run_and_the_provenance_as_given(self):
        manifest = json.loads(self.files["manifest.json"].decode("utf-8"))
        run = self.run_
        self.assertEqual((manifest["schema"], manifest["label"]), ("trial-mac-export/1", LABEL))
        self.assertEqual(manifest["sources"], PROVENANCE["sources"])
        self.assertEqual(manifest["modal_set"], PROVENANCE["modal_set"])
        self.assertEqual(manifest["rigid_body_fe_modes_excluded"], [1, 2, 3, 4, 5, 6])
        self.assertIs(manifest["source_files_included"], False)
        self.assertEqual([(m["number"], m["frequency_hz"]) for m in manifest["fe_modes"]],
                         list(zip(run.fe_numbers, run.fe_frequencies)))
        self.assertEqual([(m["number"], m["frequency_hz"]) for m in manifest["experimental_modes"]],
                         list(zip(run.experimental_numbers, run.experimental_frequencies)))
        self.assertEqual(manifest["placements"], {"count": 40, "usable": [t.name for t in run.trials], "rejected": {}})
        self.assertEqual(manifest["families"], [list(f) for f in run.families])
        self.assertEqual(manifest["assumptions"]["experimental_to_fe_scale"], 1000.0)
        self.assertEqual(manifest["assumptions"]["distance_limit_half_mesh_diagonal"], run.half_mesh_diagonal)
        self.assertEqual(manifest["measured_grid"]["points"], 25)
        self.assertEqual(manifest["measured_grid"]["counts"], [5, 5])
        for word in ("physically confirmed registration", "verified modal pairs", "accepted material properties",
                     "production Auto-ID"):
            self.assertIn(word, " ".join(manifest["these_results_are_not"]))
        listed = manifest["files"]  # every other member, by its content
        self.assertEqual(set(listed), set(self.files) - {"README.txt", "manifest.json"})
        for name, entry in listed.items():
            self.assertEqual(entry, {"size": len(self.files[name]), "sha256": hashlib.sha256(self.files[name]).hexdigest()})

    def test_the_readme_states_the_status_in_plain_words(self):
        text = self.files["README.txt"].decode("utf-8-sig")
        self.assertTrue(text.startswith(LABEL + "\n"))
        for words in ("not:", "a physically confirmed registration", "verified modal pairs", "accepted material properties",
                      "a production Auto-ID result", "No placement is selected, preferred or put in an order",
                      "Placements: 40; mapped every point: 40; rejected: 0", "checked by the test",
                      "The original ODB / UNV / UFF files are not in this archive"):
            self.assertIn(words, text)

    def test_no_identity_is_claimed_when_none_is_given(self):
        other = self.folder / "bare.zip"
        te.write_archive(other, self.run_)
        files = members(other)
        self.assertEqual(json.loads(files["manifest.json"])["sources"], {"verification": "not verified by this export"})
        self.assertIn("Source files: not verified by this export", files["README.txt"].decode("utf-8-sig"))

    def test_exporting_changes_nothing_of_the_run(self):
        run = tp.run_trials(plate.fe_modes(), plate.experimental_modes())
        before = [(t.name, t.usable, t.node_ids, t.mac.copy(), t.placed.copy()) for t in run.trials]
        measured, families = run.experimental_z.copy(), run.families
        with mock.patch.object(tp, "run_trials", side_effect=AssertionError("nothing is recomputed")), \
                mock.patch("modal_core.modal_assurance_criterion", side_effect=AssertionError("no MAC is computed")):
            te.write_archive(self.folder / "again.zip", run, PROVENANCE)
        for trial, (name, usable, nodes, mac, placed) in zip(run.trials, before):
            self.assertEqual((trial.name, trial.usable, trial.node_ids), (name, usable, nodes))
            np.testing.assert_array_equal(trial.mac, mac)
            np.testing.assert_array_equal(trial.placed, placed)
        np.testing.assert_array_equal(run.experimental_z, measured)
        self.assertEqual(run.families, families)


class RejectedTests(_Folder):
    def test_a_rejected_placement_is_recorded_and_has_no_matrix_and_no_node(self):
        run = tp.run_trials(plate.fe_modes(), plate.experimental_modes(), scale=1200.0)
        rejected = [t.name for t in run.trials if not t.usable]
        self.assertTrue(rejected)
        self.assertTrue(run.usable)
        te.write_archive(self.target, run)
        files = members(self.target)
        self.assertEqual(sorted(n for n in files if n.startswith("matrices/")),
                         sorted(f"matrices/{t.name}.csv" for t in run.usable))
        rows = table(files["placements.csv"])
        self.assertEqual(len(rows), 41)
        for row, trial in zip(rows[1:], run.trials):
            cell = dict(zip(rows[0], row))
            if trial.usable:
                self.assertEqual((cell["usable"], cell["rejection_reason"]), ("yes", ""))
            else:
                self.assertEqual((cell["usable"], cell["rejection_reason"], cell["matrix_file"]),
                                 ("no", trial.rejected_because, ""))
                self.assertIn("outside the FE outline", cell["rejection_reason"])
        points = table(files["point_mapping.csv"])
        self.assertEqual(len(points), 1 + 40 * 25)
        for row in points[1:]:
            if row[1] in rejected:
                self.assertTrue(row[2].startswith("rejected: "))
                self.assertEqual(row[5], "")  # no assumed node is written for a placement that maps nothing
            else:
                self.assertNotEqual(row[5], "")
        manifest = json.loads(files["manifest.json"])
        self.assertEqual(manifest["placements"]["rejected"], {t.name: t.rejected_because for t in run.trials if not t.usable})
        self.assertIn(f"rejected: {len(rejected)}", files["README.txt"].decode("utf-8-sig"))

    def test_when_every_placement_is_rejected_there_is_no_matrix_and_no_family(self):
        run = tp.run_trials(plate.fe_modes(), plate.experimental_modes(), scale=250.0)
        self.assertEqual(len(run.usable), 0)
        te.write_archive(self.target, run)
        files = members(self.target)
        self.assertEqual(list(files), ["README.txt", "manifest.json", "placements.csv", "point_mapping.csv", "families.csv"])
        self.assertEqual(table(files["families.csv"]), [["status", "family", "placement"]])
        self.assertEqual({r[18] for r in table(files["placements.csv"])[1:]}, {"no"})

    def test_a_value_that_is_not_defined_is_an_empty_cell_never_a_number(self):
        run = tp.run_trials(plate.fe_modes(), plate.experimental_modes())
        mac = run.trials[0].mac.copy()
        mac[1, 2] = np.nan
        run = replace(run, trials=(replace(run.trials[0], mac=mac),) + run.trials[1:])
        te.write_archive(self.target, run)
        rows = table(members(self.target)["matrices/T0_C.csv"])
        self.assertEqual(rows[2][4], "")
        self.assertEqual(float(rows[2][3]), mac[1, 1])

    def test_no_trial_is_refused(self):
        for nothing in (None, replace(tp.run_trials(plate.fe_modes(), plate.experimental_modes()), trials=())):
            with self.assertRaisesRegex(te.ExportRefused, "no completed trial"):
                te.write_archive(self.target, nothing)
        self.assertEqual(self.left(), [])


class SafeWriteTests(_Folder):
    @classmethod
    def setUpClass(cls):
        cls.run_ = tp.run_trials(plate.fe_modes(), plate.experimental_modes())

    def test_an_existing_file_is_never_replaced(self):
        self.target.write_bytes(b"mine")
        with self.assertRaisesRegex(te.ExportRefused, "already exists and is not replaced"):
            te.write_archive(self.target, self.run_)
        self.assertEqual(self.target.read_bytes(), b"mine")
        self.assertEqual(self.left(), ["trial.zip"])

    def test_a_file_that_appears_while_the_archive_is_written_is_not_replaced(self):
        def appears() -> None:
            self.target.write_bytes(b"someone else's")

        no_links = mock.Mock(side_effect=OSError("no hard links here"))
        for link, rename_is_safe in ((os.link, te._RENAME_NEVER_REPLACES), (no_links, te._RENAME_NEVER_REPLACES), (no_links, False)):
            with self.subTest(link=link, rename_is_safe=rename_is_safe), mock.patch.object(os, "link", link),                     mock.patch.object(te, "_RENAME_NEVER_REPLACES", rename_is_safe):
                with self.assertRaisesRegex(te.ExportRefused, "already exists"):
                    te.write_archive(self.target, self.run_, verify=appears)
                self.assertEqual(self.target.read_bytes(), b"someone else's")
                self.assertEqual(self.left(), ["trial.zip"])
                self.target.unlink()

    def test_with_hard_links_the_archive_is_complete(self):
        (self.folder / "probe").write_bytes(b"")
        try:
            os.link(self.folder / "probe", self.folder / "probe2")
        except OSError:
            self.skipTest("this file system has no hard links")
        finally:
            for name in ("probe", "probe2"):
                (self.folder / name).unlink(missing_ok=True)
        with mock.patch.object(os, "rename", side_effect=AssertionError("not needed")),                 mock.patch.object(os, "replace", side_effect=AssertionError("never used")):
            te.write_archive(self.target, self.run_)
        self.assertEqual(len(members(self.target)), 45)
        self.assertEqual(self.left(), ["trial.zip"])

    @unittest.skipUnless(os.name == "nt", "only the Windows rename never replaces a file")
    def test_without_hard_links_the_archive_is_still_complete_on_windows(self):
        with mock.patch.object(os, "link", side_effect=OSError("no hard links here")):
            te.write_archive(self.target, self.run_)
        self.assertEqual(len(members(self.target)), 45)
        self.assertEqual(self.left(), ["trial.zip"])

    def test_without_hard_links_and_without_a_safe_rename_nothing_is_written(self):
        with mock.patch.object(os, "link", side_effect=OSError("no hard links here")),                 mock.patch.object(te, "_RENAME_NEVER_REPLACES", False),                 mock.patch.object(os, "rename", side_effect=AssertionError("never used")),                 mock.patch.object(os, "replace", side_effect=AssertionError("never used")):
            with self.assertRaisesRegex(te.ExportRefused, "without the risk of replacing another file.*no hard links here"):
                te.write_archive(self.target, self.run_)
        self.assertEqual(self.left(), [])

    def test_a_failure_after_the_fallback_began_leaves_no_file_at_all(self):
        for failure, words in ((OSError("the drive went away"), "could not be written.*the drive went away"),
                               (FileExistsError("taken meanwhile"), "already exists and is not replaced")):
            with self.subTest(failure=failure), mock.patch.object(os, "link", side_effect=OSError("no hard links here")),                     mock.patch.object(te, "_RENAME_NEVER_REPLACES", True), mock.patch.object(os, "rename", side_effect=failure),                     mock.patch.object(os, "replace", side_effect=AssertionError("never used")):
                with self.assertRaisesRegex(te.ExportRefused, words):
                    te.write_archive(self.target, self.run_)
                self.assertEqual(self.left(), [])  # neither an empty file under the name nor the temporary archive

    def test_no_way_of_publishing_reserves_the_name_or_replaces(self):
        text = (ROOT / "src" / "services" / "trial_mac_export.py").read_text(encoding="utf-8")
        for forbidden in ("os.replace", "O_EXCL", "O_CREAT"):
            self.assertNotIn(forbidden, text, forbidden)

    def test_a_failed_check_leaves_no_file(self):
        def fails() -> None:
            raise RuntimeError("a source changed")

        with self.assertRaisesRegex(RuntimeError, "a source changed"):
            te.write_archive(self.target, self.run_, verify=fails)
        self.assertEqual(self.left(), [])

    def test_a_write_failure_leaves_no_partial_archive(self):
        with mock.patch.object(zipfile.ZipFile, "writestr", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(te.ExportRefused, "could not be written.*disk full"):
                te.write_archive(self.target, self.run_)
        self.assertEqual(self.left(), [])

    def test_a_folder_that_does_not_exist_is_refused_in_words(self):
        with self.assertRaisesRegex(te.ExportRefused, "could not be written"):
            te.write_archive(self.folder / "missing" / "trial.zip", self.run_)
        self.assertEqual(self.left(), [])


class SourceGuards(unittest.TestCase):
    def test_the_export_computes_nothing_starts_nothing_and_chooses_nothing(self):
        text = (ROOT / "src" / "services" / "trial_mac_export.py").read_text(encoding="utf-8")
        for forbidden in ("subprocess", "abaqus_bridge", "install_", "modal_assurance_criterion", "run_trials", "argmax",
                          "argsort", "sorted(", "shutil"):
            self.assertNotIn(forbidden, text, forbidden)


if __name__ == "__main__":
    unittest.main()
