"""APP-DATA.1: the local input file registry (File > Input file registry...).

The registry keeps the user's own FE / experimental file references (path and name) in the per-user profile. Using an
entry fills the matching field of 1. Files exactly as Browse does; nothing is loaded, compared or run, no file content
is read, FE and experimental entries are never paired, a missing file or a damaged registry is a clear error and a
damaged registry is never rewritten. Temporary synthetic files only; no process is started.
"""

from __future__ import annotations

import builtins
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from services import local_input_registry as registry  # noqa: E402
from test_app_p1_stale_results import STALE, _App  # noqa: E402


class _Folder(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="app_data1_"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.store = self.folder / "profile" / registry.STORE_NAME
        data = self.folder / "data"
        (data / "lms").mkdir(parents=True)
        (data / "lone").mkdir()
        self.odb = data / "plate.odb"
        self.manifest = data / "manifest.json"
        self.unv = data / "plate.unv"
        self.uff = data / "session.uff"
        self.lms = data / "lms" / "project.lms"
        self.lone_lms = data / "lone" / "project.lms"
        self.text = data / "notes.txt"
        for path in (self.odb, self.manifest, self.unv, self.uff, self.lms, self.lone_lms, self.text,
                     data / "lms" / "project.unv"):
            path.write_bytes(b"synthetic stand-in; the registry never reads it")


class ServiceTests(_Folder):
    def test_entries_are_added_and_found_again_by_a_new_read(self):
        fe, added_fe = registry.add_entry(self.store, registry.FE, self.odb, "Plate FE, mesh A")
        experiment, added_experiment = registry.add_entry(self.store, registry.EXPERIMENTAL, self.unv, "")
        self.assertTrue(added_fe and added_experiment)
        entries = registry.list_entries(self.store)
        self.assertEqual([(e["kind"], e["label"], e["path"]) for e in entries],
                         [(registry.FE, "Plate FE, mesh A", str(self.odb)),
                          (registry.EXPERIMENTAL, "plate.unv", str(self.unv))])  # default name: the file name
        self.assertEqual({e["id"] for e in entries}, {fe["id"], experiment["id"]})
        self.assertEqual(json.loads(self.store.read_text(encoding="utf-8"))["schema"], registry.SCHEMA)
        self.assertEqual(registry.usable_path(entries[0]), self.odb)

    def test_supported_file_types(self):
        registry.add_entry(self.store, registry.FE, self.manifest)
        registry.add_entry(self.store, registry.EXPERIMENTAL, self.uff)
        registry.add_entry(self.store, registry.EXPERIMENTAL, self.lms)  # its companion UNV lies beside it
        before = self.store.read_bytes()
        for kind, path, text in ((registry.FE, self.text, "not an FE result"),
                                 (registry.FE, self.unv, "not an FE result"),
                                 (registry.EXPERIMENTAL, self.odb, "not an experimental result"),
                                 (registry.EXPERIMENTAL, self.lone_lms, "no companion .unv/.uff"),
                                 ("PAIR", self.odb, "Unknown entry kind")):
            with self.subTest(kind=kind, path=path.name):
                with self.assertRaisesRegex(registry.RegistryError, text):
                    registry.add_entry(self.store, kind, path)
                self.assertEqual(self.store.read_bytes(), before)  # nothing added

    def test_the_same_file_twice_is_one_entry(self):
        first, added = registry.add_entry(self.store, registry.FE, self.odb, "Plate FE")
        self.assertTrue(added)
        same_forms = [self.odb, str(self.odb).upper() if os.name == "nt" else str(self.odb),
                      self.odb.parent / ".." / self.odb.parent.name / self.odb.name]
        for form in same_forms:
            with self.subTest(form=str(form)):
                again, added = registry.add_entry(self.store, registry.FE, form, "another name")
                self.assertFalse(added)
                self.assertEqual(again, first)  # name and path kept
        self.assertEqual(len(registry.list_entries(self.store)), 1)

    def test_a_missing_file_is_refused_and_nothing_is_substituted(self):
        with self.assertRaisesRegex(registry.RegistryError, "does not exist"):
            registry.add_entry(self.store, registry.FE, self.folder / "data" / "absent.odb")
        self.assertFalse(self.store.exists())
        entry, _ = registry.add_entry(self.store, registry.EXPERIMENTAL, self.unv, "Session 1")
        before = self.store.read_bytes()
        self.unv.unlink()
        self.assertEqual(registry.entry_state(entry), "missing")
        with self.assertRaisesRegex(registry.RegistryError, "'Session 1' cannot be used: .*does not exist"):
            registry.usable_path(entry)
        self.assertEqual(self.store.read_bytes(), before)
        self.assertEqual(registry.list_entries(self.store), [entry])  # the reference stays until a person removes it

    def test_a_damaged_registry_is_a_clear_error_and_is_never_rewritten(self):
        good = {"id": "a1", "kind": registry.FE, "label": "x", "path": str(self.odb), "added_at": "2026-10-25"}
        forms = {
            "invalid JSON": b"{not json",
            "not UTF-8": b"\xff\xfe\x00{",
            "a list": json.dumps([good]).encode(),
            "another schema": json.dumps({"schema": "other/v1", "entries": []}).encode(),
            "entries not a list": json.dumps({"schema": registry.SCHEMA, "entries": {}}).encode(),
            "entry not an object": json.dumps({"schema": registry.SCHEMA, "entries": ["x"]}).encode(),
            "entry without a path": json.dumps({"schema": registry.SCHEMA,
                                                "entries": [{**good, "path": ""}]}).encode(),
            "unknown kind": json.dumps({"schema": registry.SCHEMA, "entries": [{**good, "kind": "PAIR"}]}).encode(),
            "repeated id": json.dumps({"schema": registry.SCHEMA, "entries": [good, good]}).encode(),
        }
        for name, content in forms.items():
            with self.subTest(form=name):
                self.store.parent.mkdir(parents=True, exist_ok=True)
                self.store.write_bytes(content)
                for action in (lambda: registry.list_entries(self.store),
                               lambda: registry.add_entry(self.store, registry.EXPERIMENTAL, self.unv),
                               lambda: registry.remove_entry(self.store, "a1")):
                    with self.assertRaisesRegex(registry.RegistryError, "damaged .*left unchanged"):
                        action()
                self.assertEqual(self.store.read_bytes(), content)
                self.assertEqual(sorted(p.name for p in self.store.parent.iterdir()), [registry.STORE_NAME])

    def test_fe_and_experimental_entries_are_independent(self):
        fe, _ = registry.add_entry(self.store, registry.FE, self.odb, "plate")
        experiment, _ = registry.add_entry(self.store, registry.EXPERIMENTAL, self.unv, "plate")
        for entry in (fe, experiment):
            self.assertEqual(set(entry), {"id", "kind", "label", "path", "added_at"})  # no link to another entry
        self.assertNotEqual(fe["id"], experiment["id"])
        removed = registry.remove_entry(self.store, fe["id"])
        self.assertEqual(removed, fe)
        self.assertEqual(registry.list_entries(self.store), [experiment])
        self.assertTrue(self.odb.is_file())  # only the reference was removed
        with self.assertRaisesRegex(registry.RegistryError, "no longer in the registry"):
            registry.remove_entry(self.store, fe["id"])
        self.assertNotIn("pair", json.dumps(registry.list_entries(self.store)).lower())

    def test_file_contents_are_never_read(self):
        data_files = {os.path.normcase(str(p)) for p in (self.odb, self.manifest, self.unv, self.uff, self.lms,
                                                          self.folder / "data" / "lms" / "project.unv")}
        opened = []
        real_open = io.open

        def recording_open(file, *args, **kwargs):
            opened.append(os.path.normcase(os.fspath(file)) if isinstance(file, (str, os.PathLike)) else "")
            return real_open(file, *args, **kwargs)

        with mock.patch.object(builtins, "open", recording_open), mock.patch.object(io, "open", recording_open):
            for kind, path in ((registry.FE, self.odb), (registry.FE, self.manifest),
                               (registry.EXPERIMENTAL, self.unv), (registry.EXPERIMENTAL, self.uff),
                               (registry.EXPERIMENTAL, self.lms)):
                entry, _ = registry.add_entry(self.store, kind, path)
                registry.usable_path(entry)
                registry.entry_state(entry)
            registry.list_entries(self.store)
        self.assertTrue(opened)  # the registry file itself was read
        self.assertFalse(data_files & set(opened), sorted(data_files & set(opened)))

    def saved_registry(self):
        """A registry with one FE entry on disk; returns (its bytes, the entry)."""
        entry, _ = registry.add_entry(self.store, registry.FE, self.odb, "Plate FE")
        return self.store.read_bytes(), entry

    def assert_registry_kept(self, before: bytes, error: registry.RegistryError) -> None:
        self.assertIn("could not be saved", str(error))
        self.assertIn("left as it was; nothing was added or removed", str(error))
        self.assertEqual(self.store.read_bytes(), before)  # the previous JSON, byte for byte
        self.assertEqual(sorted(p.name for p in self.store.parent.iterdir()), [registry.STORE_NAME])  # no temp file
        json.loads(before)  # still a valid registry
        self.assertEqual(len(registry.list_entries(self.store)), 1)

    def test_a_failed_replace_on_add_keeps_the_registry(self):
        before, _ = self.saved_registry()
        with mock.patch.object(registry.os, "replace", side_effect=PermissionError(13, "Access is denied")):
            with self.assertRaises(registry.RegistryError) as raised:
                registry.add_entry(self.store, registry.EXPERIMENTAL, self.unv, "Session")
        self.assertIn("Access is denied", str(raised.exception))
        self.assert_registry_kept(before, raised.exception)

    def test_a_failed_replace_on_remove_keeps_the_registry(self):
        before, entry = self.saved_registry()
        with mock.patch.object(registry.os, "replace", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(registry.RegistryError) as raised:
                registry.remove_entry(self.store, entry["id"])
        self.assert_registry_kept(before, raised.exception)
        self.assertEqual(registry.list_entries(self.store), [entry])

    def test_folder_temporary_file_and_write_failures_are_registry_errors(self):
        before, _ = self.saved_registry()
        failures = {
            "temporary file": mock.patch.object(registry.tempfile, "mkstemp", side_effect=PermissionError(13, "denied")),
            "writing": mock.patch.object(registry.json, "dump", side_effect=OSError(28, "No space left on device")),
        }
        for name, patcher in failures.items():
            with self.subTest(failure=name), patcher:
                with self.assertRaises(registry.RegistryError) as raised:
                    registry.add_entry(self.store, registry.EXPERIMENTAL, self.unv)
                self.assert_registry_kept(before, raised.exception)
        # the profile folder cannot be created (a new profile; the same on Windows and POSIX)
        new_profile = self.folder / "new_profile"
        with mock.patch.object(registry.Path, "mkdir", side_effect=PermissionError(13, "denied")):
            with self.assertRaisesRegex(registry.RegistryError, "could not be saved: .*denied"):
                registry.add_entry(new_profile / registry.STORE_NAME, registry.FE, self.odb)
        self.assertFalse(new_profile.exists())

    def test_default_store_is_the_per_user_profile(self):
        with mock.patch.object(Path, "home", return_value=self.folder / "home"):
            self.assertEqual(registry.default_store(),
                             self.folder / "home" / ".abaqus_simcenter_modal_comparator" / registry.STORE_NAME)


class RegistryWindowTests(_App):
    """The real main window: File menu, the dialog, filling 1. Files, the stale-result reset (P-1)."""

    def dialog(self, application):
        import menu_ui

        self.store = self.folder / "profile" / registry.STORE_NAME
        application.local_input_registry_store = self.store
        dialog = menu_ui.InputRegistryDialog(application)
        self.addCleanup(lambda: dialog.window.destroy() if dialog.window.winfo_exists() else None)
        return dialog

    def add(self, kind, path, label=""):
        entry, _ = registry.add_entry(self.store, kind, path, label)
        return entry

    def use(self, dialog, entry):
        dialog.refresh(select=entry["id"])
        dialog.use_selected()
        self.settle(dialog.app)

    def test_the_file_menu_opens_the_registry(self):
        application = self.application()
        bar = application.menu_bar
        cascades = {bar.entrycget(i, "label"): bar.entrycget(i, "menu") for i in range(bar.index("end") + 1)
                    if bar.type(i) == "cascade"}
        file_menu = application.root.nametowidget(cascades["File"])
        commands = {file_menu.entrycget(index, "label"): index for index in range(file_menu.index("end") + 1)
                    if file_menu.type(index) == "command"}
        self.assertIn("Input file registry...", commands)
        before = set(application.root.winfo_children())
        application.local_input_registry_store = self.folder / "profile" / registry.STORE_NAME
        file_menu.invoke(commands["Input file registry..."])
        windows = [w for w in set(application.root.winfo_children()) - before if w.winfo_class() == "Toplevel"]
        self.assertEqual([w.title() for w in windows], ["Input file registry"])
        for window in windows:
            window.destroy()

    def test_use_fills_only_the_matching_field_and_runs_nothing(self):
        application = self.application()
        dialog = self.dialog(application)
        fe = self.add(registry.FE, self.other_odb, "Other FE")
        experiment = self.add(registry.EXPERIMENTAL, self.other_unv, "Other session")
        before_experiment = application.experimental_path.get()
        with mock.patch.object(application, "_start", side_effect=AssertionError("nothing is run")), \
                mock.patch.object(application, "_worker", side_effect=AssertionError("nothing is run")):
            self.use(dialog, fe)
            self.assertEqual(application.abaqus_path.get(), str(self.other_odb))
            self.assertEqual(application.experimental_path.get(), before_experiment)  # FE use leaves EXP alone
            self.assertEqual(application.tabs.select(), str(application.input_tab))
            self.use(dialog, experiment)
            self.assertEqual(application.experimental_path.get(), str(self.other_unv))
            self.assertEqual(application.abaqus_path.get(), str(self.other_odb))  # EXP use leaves FE alone
        self.assertFalse(application.running)
        self.assertIsNone(application.result)
        self.assertIn("Nothing was loaded or run", dialog.message.get())

    def test_using_another_file_clears_the_shown_result_like_browse(self):
        for kind in (registry.FE, registry.EXPERIMENTAL):
            with self.subTest(kind=kind):
                application = self.established(self.application())
                dialog = self.dialog(application)
                entry = self.add(kind, self.other_odb if kind == registry.FE else self.other_unv)
                self.use(dialog, entry)
                self.assert_inactive(application, STALE)

    def test_using_the_file_already_selected_keeps_the_result(self):
        application = self.established(self.application())
        dialog = self.dialog(application)
        self.use(dialog, self.add(registry.EXPERIMENTAL, self.fitted_path))
        self.assert_active_comparison(application)

    def test_a_missing_file_leaves_the_fields_unchanged(self):
        application = self.application()
        dialog = self.dialog(application)
        gone = self.folder / "gone.odb"
        gone.write_bytes(b"x")
        entry = self.add(registry.FE, gone, "Gone FE")
        gone.unlink()
        before = (application.abaqus_path.get(), application.experimental_path.get())
        with mock.patch("tkinter.messagebox.showwarning") as warned:
            self.use(dialog, entry)
        self.assertEqual((application.abaqus_path.get(), application.experimental_path.get()), before)
        self.assertIn("'Gone FE' cannot be used", warned.call_args.args[1])
        self.assertIn("left unchanged", warned.call_args.args[1])
        self.assertEqual(dialog.tree.set(entry["id"], "state"), "missing")

    def test_a_damaged_registry_disables_the_dialog_and_is_not_rewritten(self):
        application = self.application()
        self.store = self.folder / "profile" / registry.STORE_NAME
        self.store.parent.mkdir(parents=True)
        self.store.write_bytes(b"[1, 2, 3]")
        dialog = self.dialog(application)
        self.assertIn("damaged", dialog.message.get())
        for button in (dialog.add_fe_button, dialog.add_experimental_button, dialog.use_button, dialog.inspect_button,
                       dialog.inspect_experimental_button, dialog.remove_button):
            self.assertEqual(str(button.cget("state")), "disabled")
        self.assertEqual(dialog.tree.get_children(), ())
        self.assertEqual(self.store.read_bytes(), b"[1, 2, 3]")

    def test_adding_through_the_dialog_and_adding_the_same_file_again(self):
        application = self.application()
        dialog = self.dialog(application)
        with mock.patch("tkinter.filedialog.askopenfilename", return_value=str(self.other_odb)), \
                mock.patch("tkinter.simpledialog.askstring", return_value="Plate FE, mesh B"):
            dialog.add(registry.FE)
            self.assertIn("Added 'Plate FE, mesh B'", dialog.message.get())
            dialog.add(registry.FE)
        self.assertIn("already in the registry as 'Plate FE, mesh B'", dialog.message.get())
        self.assertEqual(len(registry.list_entries(self.store)), 1)
        self.assertEqual(application.abaqus_path.get(), str(self.folder / "plate.odb"))  # adding fills no field
        with mock.patch("tkinter.filedialog.askopenfilename", return_value=str(self.folder / "notes.txt")), \
                mock.patch("tkinter.simpledialog.askstring", return_value="notes"), \
                mock.patch("tkinter.messagebox.showerror") as refused:
            (self.folder / "notes.txt").write_text("x", encoding="utf-8")
            dialog.add(registry.FE)
        self.assertIn("Nothing was added", refused.call_args.args[1])
        self.assertEqual(len(registry.list_entries(self.store)), 1)

    def test_remove_drops_only_the_reference(self):
        application = self.application()
        dialog = self.dialog(application)
        entry = self.add(registry.FE, self.other_odb, "Other FE")
        dialog.refresh(select=entry["id"])
        with mock.patch("tkinter.messagebox.askyesno", return_value=True):
            dialog.remove_selected()
        self.assertEqual(registry.list_entries(self.store), [])
        self.assertTrue(self.other_odb.is_file())
        self.assertIn("the file was not touched", dialog.message.get())

    def test_a_failed_save_is_shown_and_the_registry_is_kept(self):
        application = self.application()
        dialog = self.dialog(application)
        entry = self.add(registry.FE, self.other_odb, "Other FE")
        before = self.store.read_bytes()
        dialog.refresh(select=entry["id"])
        denied = PermissionError(13, "Access is denied")
        with mock.patch.object(registry.os, "replace", side_effect=denied), \
                mock.patch("tkinter.filedialog.askopenfilename", return_value=str(self.other_unv)), \
                mock.patch("tkinter.simpledialog.askstring", return_value="Other session"), \
                mock.patch("tkinter.messagebox.askyesno", return_value=True), \
                mock.patch("tkinter.messagebox.showerror") as shown:
            dialog.add(registry.EXPERIMENTAL)
            dialog.refresh(select=entry["id"])
            dialog.remove_selected()
        add_message, remove_message = (call.args[1] for call in shown.call_args_list)
        self.assertIn("could not be saved", add_message)
        self.assertIn("Nothing was added", add_message)
        self.assertIn("could not be saved", remove_message)
        self.assertIn("left as it was", remove_message)
        self.assertNotIn("Removed", dialog.message.get())
        self.assertEqual(self.store.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in self.store.parent.iterdir()), [registry.STORE_NAME])
        self.assertEqual(dialog.tree.get_children(), (entry["id"],))  # the dialog still lists the kept entry
        self.assertEqual(str(dialog.add_fe_button.cget("state")), "normal")


if __name__ == "__main__":
    unittest.main()
