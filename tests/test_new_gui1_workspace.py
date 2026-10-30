"""NEW-GUI.1: the workspace model of the new interface (``new_gui.workspace_state``), with no Qt.

The workspace starts empty; a chosen file is checked with the read-only ``local_input_registry.check_file`` (nothing
is written to the registry, the content is not read); a refused or cancelled choice changes nothing; the specimen
label is never looked up in the research archive; the archive is read only on request and a missing or damaged one
gives a problem text; the scientific status is read, never set; nothing is computed and no user file is changed.
The new interface never imports the Tkinter program. Temporary synthetic files only; no process but one Python
import check is started.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from new_gui import workspace_state as ws  # noqa: E402
from services import local_input_registry as registry  # noqa: E402
from services import specimen_catalog_view as catalog  # noqa: E402

CATALOGUE = ROOT / "docs" / "auto_id" / "specimen_catalog.json"
NEW_GUI = ROOT / "src" / "new_gui"
ARCHIVE_WORDS = ("GOVERNED", "PHYSICAL", "LEGACY", "catalogue", "archived specimen SP")


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _snapshot(folder: Path) -> dict:
    return {p.relative_to(folder).as_posix(): (_sha(p), p.stat().st_mtime_ns)
            for p in sorted(Path(folder).rglob("*")) if p.is_file()}


class _Files(unittest.TestCase):
    """A user's own arbitrary plate: synthetic FE and experimental files in a temporary folder."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)
        self.odb = self._file("plate_steel_200x300.odb", b"synthetic odb bytes")
        self.odb2 = self._file("plate_steel_200x300_fine.odb", b"another synthetic odb")
        self.unv = self._file("plate_hammer_test.unv", b"    -1\n   151\nsynthetic\n    -1\n")
        self.uff = self._file("plate_shaker.uff", b"synthetic uff")
        self.text = self._file("notes.txt", b"not an input")
        (self.folder / "extract").mkdir()
        self.manifest = self.folder / "extract" / "manifest.json"
        self.manifest.write_text("{}", encoding="utf-8")
        self.store = self.folder / "profile" / registry.STORE_NAME  # the registry must never be written
        patcher = mock.patch.object(registry, "default_store", return_value=self.store)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def _file(self, name: str, data: bytes) -> Path:
        path = self.folder / name
        path.write_bytes(data)
        return path


class EmptyStartTests(unittest.TestCase):
    def test_a_new_workspace_is_empty(self):
        workspace = ws.Workspace()
        self.assertTrue(workspace.empty)
        for kind in ws.KINDS:
            choice = workspace.choice(kind)
            self.assertFalse(choice.chosen)
            self.assertIsNone(choice.path)
            self.assertEqual(choice.status, ws.NOT_CHOSEN)
        self.assertEqual(workspace.specimen_label, "")
        self.assertEqual(workspace.label_text, "Unnamed (a name is optional)")
        self.assertEqual(workspace.analysis, ws.ANALYSIS_NOT_RUN)

    def test_the_model_holds_no_project_registration_preset_or_result(self):
        fields = set(ws.Workspace.__dataclass_fields__)
        self.assertEqual(fields, {"fe", "experimental", "specimen_label"})
        self.assertEqual(set(ws.FileChoice.__dataclass_fields__), {"kind", "path", "file_type"})


class ArbitraryPlateTests(_Files):
    def test_fe_and_unv_of_any_plate_are_chosen_without_the_archive(self):
        with mock.patch.object(catalog, "load_catalogue", side_effect=AssertionError("archive read")):
            workspace, message = ws.Workspace().choose(ws.FE, str(self.odb))
            self.assertEqual(message, "")
            workspace, message = workspace.choose(ws.EXPERIMENTAL, str(self.unv))
        self.assertEqual(message, "")
        self.assertFalse(workspace.empty)
        self.assertEqual(workspace.fe.path, self.odb.resolve())
        self.assertEqual(workspace.experimental.path, self.unv.resolve())
        for kind in ws.KINDS:
            self.assertEqual(workspace.choice(kind).status, "File chosen; content not checked")
        self.assertEqual(workspace.fe.file_type, "Abaqus output database (.odb) — not viewable in this interface")
        self.assertEqual(workspace.experimental.file_type, "Universal file (.unv)")
        self.assertEqual(workspace.analysis, ws.ANALYSIS_NOT_RUN)

    def test_every_supported_type_is_accepted_with_its_type(self):
        lms = self._file("plate_project.lms", b"synthetic lms")  # its companion: the single .unv / .uff beside it
        companion = self.folder / "plate_project.unv"
        companion.write_bytes(b"companion")
        cases = ((ws.FE, self.manifest, "Extracted FE manifest (manifest.json)"),
                 (ws.EXPERIMENTAL, self.uff, "Universal file (.uff)"),
                 (ws.EXPERIMENTAL, lms, "Simcenter Testlab project (.lms); companion universal file "
                                        "plate_project.unv"))
        for kind, path, text in cases:
            with self.subTest(path=path.name):
                workspace, message = ws.Workspace().choose(kind, str(path))
                self.assertEqual(message, "")
                self.assertEqual(workspace.choice(kind).file_type, text)

    def test_the_check_is_the_read_only_registry_contract(self):
        with mock.patch.object(registry, "check_file", wraps=registry.check_file) as check, \
                mock.patch.object(registry, "add_entry", side_effect=AssertionError("registry written")), \
                mock.patch.object(registry, "_write", side_effect=AssertionError("registry written")):
            ws.Workspace().choose(ws.FE, str(self.odb))
        check.assert_called_once_with(ws.FE, str(self.odb))
        self.assertFalse(self.store.exists())
        self.assertFalse(self.store.parent.exists())

    def test_the_file_content_is_not_read(self):
        real_open = open

        def guarded_open(file, *args, **kwargs):
            if Path(str(file)).resolve() in (self.odb.resolve(), self.unv.resolve()):
                raise AssertionError(f"content of {file} read")
            return real_open(file, *args, **kwargs)

        with mock.patch("builtins.open", guarded_open), \
                mock.patch.object(Path, "read_bytes", side_effect=AssertionError("content read")), \
                mock.patch.object(Path, "read_text", side_effect=AssertionError("content read")):
            workspace, _ = ws.Workspace().choose(ws.FE, str(self.odb))
            workspace, _ = workspace.choose(ws.EXPERIMENTAL, str(self.unv))
        self.assertTrue(workspace.fe.chosen and workspace.experimental.chosen)


class ReplaceCancelInvalidTests(_Files):
    def test_replace_a_choice(self):
        workspace, _ = ws.Workspace().choose(ws.FE, str(self.odb))
        workspace, message = workspace.choose(ws.FE, str(self.odb2))
        self.assertEqual(message, "")
        self.assertEqual(workspace.fe.path, self.odb2.resolve())

    def test_a_cancelled_dialog_changes_nothing(self):
        workspace, _ = ws.Workspace().choose(ws.FE, str(self.odb))
        for cancelled in (None, "", "   "):
            with self.subTest(path=cancelled):
                same, message = workspace.choose(ws.FE, cancelled)
                self.assertIs(same, workspace)
                self.assertEqual(message, "")

    def test_a_missing_file_is_refused_and_nothing_is_chosen(self):
        missing = self.folder / "gone.odb"
        workspace, message = ws.Workspace().choose(ws.FE, str(missing))
        self.assertTrue(workspace.empty)
        self.assertIn("does not exist", message)
        self.assertIn("Nothing was chosen.", message)

    def test_a_refused_file_keeps_the_previous_choice(self):
        workspace, _ = ws.Workspace().choose(ws.FE, str(self.odb))
        for kind, bad, words in ((ws.FE, self.folder / "gone.odb", "does not exist"),
                                 (ws.FE, self.text, "is not an FE result"),
                                 (ws.FE, self.unv, "is not an FE result"),
                                 (ws.FE, self.folder, "does not exist (or is not a file)")):
            with self.subTest(bad=bad.name):
                kept, message = workspace.choose(kind, str(bad))
                self.assertEqual(kept, workspace)
                self.assertIn(words, message)
                self.assertIn("The previous choice is kept.", message)
        workspace, _ = workspace.choose(ws.EXPERIMENTAL, str(self.unv))
        kept, message = workspace.choose(ws.EXPERIMENTAL, str(self.odb))
        self.assertEqual(kept.experimental.path, self.unv.resolve())
        self.assertIn("is not an experimental result", message)

    def test_an_lms_without_companion_is_refused(self):
        alone = Path(tempfile.mkdtemp(dir=self.folder)) / "project.lms"
        alone.write_bytes(b"lms")
        workspace, message = ws.Workspace().choose(ws.EXPERIMENTAL, str(alone))
        self.assertTrue(workspace.empty)
        self.assertIn("no companion .unv/.uff", message)

    def test_clear_a_choice(self):
        workspace, _ = ws.Workspace().choose(ws.FE, str(self.odb))
        workspace, _ = workspace.choose(ws.EXPERIMENTAL, str(self.unv))
        workspace = workspace.clear(ws.FE)
        self.assertFalse(workspace.fe.chosen)
        self.assertEqual(workspace.fe.status, ws.NOT_CHOSEN)
        self.assertTrue(workspace.experimental.chosen)
        self.assertTrue(workspace.clear(ws.EXPERIMENTAL).empty)

    def test_an_unknown_kind_is_an_error(self):
        with self.assertRaises(ValueError):
            ws.Workspace().choose("MODEL", str(self.odb))
        with self.assertRaises(ValueError):
            ws.Workspace().clear("MODEL")


class SpecimenLabelTests(_Files):
    def test_sp02_is_a_label_only(self):
        with mock.patch.object(catalog, "load_catalogue", side_effect=AssertionError("archive read")):
            workspace, _ = ws.Workspace().with_label("  SP-02 ").choose(ws.EXPERIMENTAL, str(self.unv))
        self.assertEqual(workspace.specimen_label, "SP-02")
        self.assertEqual(workspace.label_text, "SP-02 (your label; not looked up in the research archive)")
        self.assertEqual(workspace.experimental.file_type, "Universal file (.unv)")
        shown = " ".join([workspace.label_text, workspace.experimental.status, workspace.experimental.file_type,
                          workspace.analysis])
        for word in ARCHIVE_WORDS:
            self.assertNotIn(word, shown)

    def test_an_archived_file_name_gets_no_archive_attribution(self):
        archived = self._file("SP02_Bravo_PolyMAX.unv", b"a new measurement with an archived name")
        workspace, message = ws.Workspace().with_label("SP-02").choose(ws.EXPERIMENTAL, str(archived))
        self.assertEqual(message, "")
        self.assertEqual(workspace.experimental.status, ws.CHOSEN_NOT_CHECKED)
        self.assertEqual(workspace.experimental.file_type, "Universal file (.unv)")

    def test_the_label_changes_no_file(self):
        workspace, _ = ws.Workspace().choose(ws.FE, str(self.odb))
        labelled = workspace.with_label("my plate")
        self.assertEqual((labelled.fe, labelled.experimental), (workspace.fe, workspace.experimental))
        self.assertEqual(labelled.with_label("").label_text, "Unnamed (a name is optional)")


class ArchiveTests(unittest.TestCase):
    def test_the_accepted_archive_is_listed_read_only(self):
        before = _sha(CATALOGUE)
        listing = ws.load_archive()
        self.assertEqual(listing.problem, "")
        ids = [specimen_id for specimen_id, _ in listing.records]
        self.assertEqual(len(ids), 14)
        self.assertIn("SP-02", ids)
        self.assertTrue(all(text.startswith(specimen_id) for specimen_id, text in listing.records))
        sections = listing.passport("SP-02")
        self.assertEqual(sections[0].title, "Identity and status")
        self.assertEqual(_sha(CATALOGUE), before)

    def test_a_missing_or_damaged_archive_is_a_problem_not_an_error(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / "bad.json").write_text("{not json", encoding="utf-8")
            (folder / "other.json").write_text(json.dumps({"schema": "x"}), encoding="utf-8")
            (folder / "empty.json").write_text(json.dumps({"schema": catalog.CATALOGUE_SCHEMA, "specimens": []}),
                                               encoding="utf-8")
            for name in ("missing.json", "bad.json", "other.json", "empty.json"):
                with self.subTest(archive=name):
                    listing = ws.load_archive(folder / name)
                    self.assertTrue(listing.problem)
                    self.assertEqual(listing.records, ())

    def test_an_unexpected_failure_is_a_problem(self):
        with mock.patch.object(catalog, "load_catalogue", side_effect=RuntimeError("disk")):
            listing = ws.load_archive()
        self.assertIn("could not be read (disk)", listing.problem)
        self.assertEqual(listing.records, ())

    def test_a_record_that_cannot_be_worded_does_not_stop_the_program(self):
        listing = ws.load_archive()
        with mock.patch.object(catalog, "passport_sections", side_effect=KeyError("geometry")):
            sections = listing.passport("SP-02")
        self.assertEqual(len(sections), 1)
        self.assertIn("SP-02 cannot be shown", sections[0].rows[0][1])
        self.assertIn("not in the archive", listing.passport("SP-99")[0].rows[0][1])


class ScientificStatusTests(unittest.TestCase):
    def test_the_recorded_status_is_shown_unchanged(self):
        from services.campaign_execution_plan import NOT_AUTHORISED
        from services.guarded_execution import PRODUCTION_AUTHORITY

        rows = {row.caption: row for row in ws.scientific_status()}
        self.assertEqual(list(rows), ["Production Auto-ID", "M8 gate", "D-077 formal output"])
        self.assertEqual(rows["Production Auto-ID"].value, NOT_AUTHORISED)
        self.assertEqual(rows["Production Auto-ID"].value, "NOT_AUTHORISED")
        self.assertFalse(PRODUCTION_AUTHORITY.available)
        self.assertEqual(rows["M8 gate"].value, "NOT_MET")
        self.assertEqual(rows["D-077 formal output"].value, "NO_GLOBAL_PARAMETER_VALUE")

    def test_an_unreadable_status_record_is_unknown_and_auto_id_stays_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            bad = Path(folder) / "STATUS.json"
            for content in (None, "{broken", json.dumps({"schema": "other"}),
                            json.dumps({"schema": "auto-id-project-status/v1", "m8": {}, "m7": {}})):
                with self.subTest(content=content):
                    if content is not None:
                        bad.write_text(content, encoding="utf-8")
                    rows = {row.caption: row for row in ws.scientific_status(bad)}
                    self.assertEqual(rows["Production Auto-ID"].value, "NOT_AUTHORISED")
                    self.assertEqual(rows["M8 gate"].value, "UNKNOWN")
                    self.assertEqual(rows["D-077 formal output"].value, "UNKNOWN")


class NothingComputedOrChangedTests(_Files):
    def test_choosing_clearing_and_reading_the_archive_change_no_file(self):
        before, catalogue = _snapshot(self.folder), _sha(CATALOGUE)
        workspace, _ = ws.Workspace().with_label("SP-02").choose(ws.FE, str(self.odb))
        workspace, _ = workspace.choose(ws.EXPERIMENTAL, str(self.unv))
        workspace, _ = workspace.choose(ws.FE, str(self.folder / "gone.odb"))
        workspace = workspace.clear(ws.FE)
        listing = ws.load_archive()
        listing.passport("SP-02")
        ws.scientific_status()
        self.assertEqual(_snapshot(self.folder), before)
        self.assertEqual(_sha(CATALOGUE), catalogue)
        self.assertFalse(self.store.exists())


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    return found | {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}


class SeparationTests(unittest.TestCase):
    PROJECT_MODULES = {"services.local_input_registry", "services.specimen_catalog_view",
                       "services.workspace_context", "universal_reader", "services",
                       # NEW-GUI.2: the shared importer chain and the read-only preview services
                       "services.importer_runtime", "services.local_fe_preview", "services.local_experimental_preview",
                       # NEW-GUI.4: the existing frequency-only diagnostic service
                       "services.new_odb_comparison",
                       # NEW-GUI.6: the report folder rule, fresh file identities, the diagnostic report's loaded data,
                       # and the read-only loaders of the governed material records
                       "services.report_directory", "services.archived_sensitivity_evidence",
                       "services.modal_data_viewer", "domain.campaign_definition", "domain.forward_model_manifest",
                       "domain.identification_run",
                       # PLATE-ONLY-R1: the research plate study service (no fit, no FE solve)
                       "services.plate_study"}
    # NEW-GUI.6: the scientific comparator and the program's own final drawing / report owners, each only in the one
    # module that calls it (the report layers are installed by report_export in src/main.py's order, tested there).
    SCIENTIFIC_MODULES = {"comparison_model.py": {"modal_core", "amplitude_correlation", "reporting_hardening",
                                                  "numpy"},
                          "report_export.py": {"reporting"}}

    def test_the_new_gui_imports_only_its_own_modules_and_the_read_only_services(self):
        files = sorted(NEW_GUI.glob("*.py"))
        self.assertEqual([p.name for p in files], ["__init__.py", "__main__.py", "archive_dialog.py",
                                                   "comparison_model.py", "comparison_panel.py",
                                                   "diagnostic_model.py", "diagnostic_panel.py", "known_sources.py",
                                                   "known_sources_dialog.py", "materials_model.py",
                                                   "materials_panel.py", "plate_study_model.py",
                                                   "plate_study_panel.py", "preview_model.py", "preview_panel.py",
                                                   "registration_check_model.py", "registration_check_panel.py",
                                                   "report_export.py", "shape_model.py", "shape_panel.py",
                                                   "window.py", "workspace_state.py"])
        stdlib = set(sys.stdlib_module_names) | {"__future__"}
        for path in files:
            for name in _imports(path):
                with self.subTest(module=path.name, imported=name):
                    top = name.split(".")[0]
                    if top in stdlib or top in ("PySide6", "new_gui"):
                        continue
                    self.assertIn(name, self.PROJECT_MODULES | self.SCIENTIFIC_MODULES.get(path.name, set()))

    def test_no_tkinter_program_no_install_layer_and_no_solver(self):
        forbidden = ("main", "home_dashboard", "tkinter", "subprocess", "abaqus_bridge", "modal_core",
                     "comparison_engine", "polymax_ui", "ui_workflow")
        for path in sorted(NEW_GUI.glob("*.py")):
            for name in _imports(path):
                with self.subTest(module=path.name, imported=name):
                    if path.name == "comparison_model.py" and name == "modal_core":
                        continue  # NEW-GUI.6: the reviewed comparator facade, called with a frozen registration
                    self.assertNotIn(name.split(".")[-1], forbidden)
                    self.assertFalse(name.split(".")[-1].startswith("install_"))
            tree = ast.parse(path.read_text(encoding="utf-8"))
            used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
            used |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
            used |= {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
            self.assertEqual(sorted(name for name in used if name.startswith("install_")), [], path.name)

    def test_importing_the_new_gui_loads_neither_the_old_program_nor_tkinter(self):
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import new_gui.workspace_state as w; "
                "w.load_archive(); w.scientific_status(); "
                "bad = sorted(m for m in sys.modules if m in ('main', 'home_dashboard', 'tkinter') "
                "or m.split('.')[-1].startswith('install_')); print(','.join(bad))")
        done = subprocess.run([sys.executable, "-c", code, str(ROOT / "src")], capture_output=True, text=True,
                              timeout=120, cwd=str(ROOT), env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "")

    def test_pyside6_is_not_a_requirement_of_the_existing_program(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
        self.assertNotIn("pyside", requirements)
        self.assertIn("pyside6", (ROOT / "requirements-new-gui.txt").read_text(encoding="utf-8").lower())


if __name__ == "__main__":
    unittest.main()
