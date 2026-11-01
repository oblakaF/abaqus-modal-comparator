"""WINDOWS-RC1-A: portable inputs of the new interface (Qt ``offscreen`` where a window is needed).

- **Known sources in another folder.** The dialog's folder is chosen only by the user. A source is used only when the
  file under that folder (the delivery folder or its subfolder) has the declared size and SHA-256. A missing file,
  another content of the same name or a changed size is refused with the reason. The provenance map is still
  checked. The ordinary choice of one's own UNV keeps working, and nothing is read before Inspect file.
- **The plate's FE archive root.** The Plate Study page shows the root and lets the user choose another one. The
  family is verified there by its recorded SHA-256; members not found are MISSING and contribute nothing. A new root
  discards the earlier result and its export status. The whole extracted FE package identity still guards the study.
- **ODB.** An .odb can be chosen. The card says it cannot be viewed in this interface, and Inspect refuses with the
  reason before the importer chain is installed: no Abaqus, no subprocess. A plain manifest.json is still read.
- **Unchanged.** FREQUENCY_ONLY_DIAGNOSTIC, PHYSICAL_REGISTRATION_NOT_VERIFIED, NOT_IDENTIFIABLE and production
  Auto-ID BLOCKED.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

try:
    from PySide6.QtWidgets import QApplication  # noqa: F401
except ImportError as error:  # pragma: no cover - depends on the environment
    if os.environ.get("NEW_GUI_REQUIRE_QT") == "1":
        raise
    raise unittest.SkipTest(f"PySide6 is not installed ({error})")

from new_gui import known_sources as ks  # noqa: E402
from new_gui import preview_model as pm  # noqa: E402
from new_gui import workspace_state as ws  # noqa: E402
from services import plate_study as ps  # noqa: E402
from test_plate_study_qt import _PlateWindow  # noqa: E402

PLATE = ks.find("NEXP29/PLATE300-1MM/S261027-ROTATED")
REAL_PLATE = ks.DEFAULT_ROOT.joinpath(*Path(PLATE.relative_path.replace("\\", "/")).parts)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class KnownSourceServiceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name) / "moved delivery"
        content = b"synthetic dataset 55 " * 50
        self.file = self.root / "SPname_files_ROTATED_261028" / "plate.unv"
        self.file.parent.mkdir(parents=True)
        self.file.write_bytes(content)
        self.source = ks.KnownSource("SERIES", "PLATE", "session", r"SPname_files_ROTATED_261028\plate.unv",
                                     len(content), hashlib.sha256(content).hexdigest(), "note")

    def test_a_moved_source_is_found_in_the_delivery_folder_or_its_subfolder(self):
        for root in (self.root, self.root / "SPname_files_ROTATED_261028"):
            with self.subTest(root=root.name):
                self.assertEqual(ks.availability(self.source, root).state, ks.AVAILABLE)
                self.assertEqual(ks.verify(self.source, root), self.file)  # the declared SHA-256 is accepted

    def test_a_changed_a_missing_or_a_same_named_file_is_refused(self):
        self.file.write_bytes(b"X" * self.source.size_bytes)  # same name and size, another content
        with self.assertRaises(ks.ProvenanceMismatch) as refused:
            ks.verify(self.source, self.root)
        self.assertIn("is not the declared", str(refused.exception))
        self.file.write_bytes(b"short")
        self.assertEqual(ks.availability(self.source, self.root).state, ks.CHANGED)
        with self.assertRaises(ks.ProvenanceMismatch):
            ks.verify(self.source, self.root)
        self.file.unlink()
        found = ks.availability(self.source, self.root)
        self.assertEqual((found.state, found.text), (ks.MISSING, "Not found in the chosen folder"))
        with self.assertRaises(ks.ProvenanceMismatch):
            ks.verify(self.source, self.root)

    def test_another_folder_name_is_not_a_place_for_the_file(self):
        other = self.root.parent / "elsewhere"
        other.mkdir()
        shutil.copy2(self.file, other / "plate.unv")  # the right content, but not in the declared layout
        self.assertEqual(ks.availability(self.source, other).state, ks.MISSING)

    def test_the_provenance_map_is_still_required(self):
        self.assertEqual([s.series_id for s in ks.confirmed_sources()], [s.series_id for s in ks.KNOWN_SOURCES])
        broken = self.root.parent / "SOURCE_PROVENANCE.csv"
        broken.write_text("relative_path,series_id,size_bytes,sha256,source_status,file_type\n", encoding="utf-8")
        with self.assertRaises(ks.ProvenanceMismatch):
            ks.confirmed_sources(broken)


class KnownSourceDialogTests(_PlateWindow):
    def test_the_folder_is_chosen_by_the_user_and_checked_there(self):
        asked = []
        self.window._known_root = self.root / "absent"
        dialog = self.window.open_known_sources()
        dialog._ask_folder = lambda start: asked.append(start) or ""
        self.assertFalse(dialog.choose_folder())  # a cancelled choice changes nothing
        self.assertEqual(asked, [str(self.root / "absent")])
        self.assertIn("None of the known sources is in this folder", dialog.message.text())
        moved = self.root / "moved"
        moved.mkdir()
        self.assertTrue(dialog.choose_folder(str(moved)))
        self.assertEqual(dialog.folder_label.text(), f"Folder: {moved}")
        self.assertTrue(all(entry.state == ks.MISSING for entry in dialog.entries))
        self.assertFalse(dialog.use_button.isEnabled())
        dialog.reject()
        self.app.processEvents()
        self.assertEqual(self.window._known_root, moved)  # offered again in this session
        self.assertFalse(self.window.workspace.choice(ws.EXPERIMENTAL).chosen)  # nothing chosen or read

    @unittest.skipUnless(REAL_PLATE.is_file(), "the real 261027 working source is not on this computer")
    def test_the_real_working_source_moved_to_another_folder(self):
        moved = self.root / "D drive copy" / "SPname_files_ROTATED_261028"
        moved.mkdir(parents=True)
        shutil.copy2(REAL_PLATE, moved / REAL_PLATE.name)
        dialog = self.window.open_known_sources()
        self.assertTrue(dialog.choose_folder(str(moved)))  # the subfolder itself
        row = [entry.source for entry in dialog.entries].index(PLATE)
        self.assertEqual(dialog.entries[row].state, ks.AVAILABLE)
        dialog.list.setCurrentRow(row)
        self.app.processEvents()
        self.assertTrue(dialog.use_selected())
        self.app.processEvents()
        self.assertEqual(self.window.workspace.choice(ws.EXPERIMENTAL).path, (moved / REAL_PLATE.name).resolve())
        self.assertIsNone(self.window._read_preview(ws.EXPERIMENTAL))  # nothing read until Inspect file
        (moved / REAL_PLATE.name).write_bytes(REAL_PLATE.read_bytes()[:-1] + b"#")  # changed after the choice
        dialog = self.window.open_known_sources()
        dialog.list.setCurrentRow(row)
        self.app.processEvents()
        self.assertFalse(dialog.use_selected())
        self.assertIn("is not the declared", dialog.message.text())
        dialog.reject()


class FamilyRootTests(_PlateWindow):
    def run_study(self):
        self.assertTrue(self.panel.run())
        self.assertTrue(self.window.wait_for_reads(120))

    def moved_family(self) -> Path:
        moved = self.root / "moved archive"
        for member in ps.PLATE_FE_FAMILY:
            for item in (member.inp, member.manifest):
                target = moved / item.relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(self.root / item.relative, target)
        return moved

    def family_states(self) -> dict:
        table = self.panel.tables["family"]
        return {table.item(r, 0).text(): table.item(r, 4).text() for r in range(table.rowCount())}

    def test_the_family_is_used_from_another_root_and_a_new_root_resets_the_result(self):
        self.assertIn(f"FE archive folder: {self.root}", self.panel.root_label.text())
        self.read()
        moved = self.moved_family()
        self.assertTrue(self.panel.choose_family_root(str(moved)))
        self.run_study()
        self.assertTrue(all("MISSING" not in files and "CHANGED" not in files
                            for files in self.family_states().values()), self.family_states())
        self.assertGreater(self.panel.tables["sensitivity"].rowCount(), 0)
        self.assertTrue(self.panel.export())
        self.assertTrue(self.panel.export_message.startswith("Plate study report written"))
        empty = self.root / "empty archive"
        empty.mkdir()
        self.assertTrue(self.panel.choose_family_root(str(empty)))
        self.assertIsNone(self.panel.view)  # the earlier result and its export status are gone
        self.assertEqual(self.panel.export_message, "")
        self.assertFalse(self.panel.export_button.isEnabled())
        self.assertFalse(self.panel.choose_family_root(str(empty)))  # the same folder changes nothing
        self.assertFalse(self.panel.choose_family_root(""))  # a cancelled choice changes nothing
        self.run_study()
        states = self.family_states()
        self.assertTrue(all("MISSING" in files for files in states.values()), states)  # never invented
        self.assertEqual(self.panel.tables.get("sensitivity"), None)  # no variant: no sensitivity
        view = self.panel.view
        self.assertEqual(view.registration_status, "PHYSICAL_REGISTRATION_NOT_VERIFIED")
        self.assertTrue(view.status.startswith("FREQUENCY_ONLY"))
        self.assertEqual({o[1] for o in view.outcome_rows}, {ps.NOT_IDENTIFIABLE})
        self.assertFalse(self.panel.gate_button.isEnabled())
        missing = self.root / "not here"
        self.assertTrue(self.panel.choose_family_root(str(missing)))
        self.assertIn("not found on this computer", self.panel.root_label.text())

    def test_the_whole_package_identity_still_guards_the_study_after_a_new_root(self):
        self.read()
        self.assertTrue(self.panel.choose_family_root(str(self.moved_family())))
        self.files["base/geometry.csv"].write_text("changed", encoding="utf-8")  # the read package, not the root
        self.assertTrue(self.panel.run())
        self.assertTrue(self.window.wait_for_reads(120))
        self.assertIsNone(self.panel.view)
        self.assertIn("changed since Inspect file read it", self.panel.status.text())


class OdbTests(_PlateWindow):
    def test_an_odb_is_explained_and_never_read_and_a_manifest_still_is(self):
        odb = self.root / "model.odb"
        odb.write_bytes(b"synthetic odb")
        self.assertEqual(self.window.choose_file(ws.FE, str(odb)), "")
        card = self.window.cards[ws.FE]
        self.assertFalse(card.odb_note.isHidden())  # shown on the Workspace card
        self.assertIn("cannot be viewed in this version of the new interface", card.odb_note.text())
        self.assertIn("RUN_PROGRAM.cmd", card.odb_note.text())
        self.assertIn("not viewable in this interface", card.file_type.text())
        self.assertTrue(ws.DIALOG_FILTERS[ws.FE].startswith("Extracted FE package (manifest.json)"))
        with mock.patch("subprocess.Popen") as popen, \
                mock.patch("services.importer_runtime.ensure_application_importers") as importers:
            with self.assertRaises(pm.PreviewRefused) as refused:
                _original_read_preview(ws.FE, odb)  # the real function (the fixture patches pm.read_preview)
            popen.assert_not_called()
            importers.assert_not_called()
        self.assertIn("Abaqus is not started", str(refused.exception))
        self.assertIn("manifest.json", str(refused.exception))
        self.read()  # an ordinary manifest.json and UNV are still read
        self.assertTrue(card.odb_note.isHidden())
        self.assertIsNotNone(self.window._read_preview(ws.FE))
        self.assertIsNotNone(self.window._read_preview(ws.EXPERIMENTAL))


_original_read_preview = pm.read_preview  # captured before the fixture patches it


class StatusTests(unittest.TestCase):
    def test_production_auto_id_stays_blocked(self):
        rows = ws.scientific_status()
        self.assertTrue("BLOCKED" in rows[0].value or "NOT_AUTHORISED" in rows[0].value, rows[0])  # production Auto-ID
        values = " ".join(row.value for row in rows)
        self.assertIn("NOT_MET", values)
        self.assertIn("NO_GLOBAL_PARAMETER_VALUE", values)
        with self.assertRaises(ps.IterationNotAuthorised):
            ps.request_iteration()


if __name__ == "__main__":
    unittest.main()
