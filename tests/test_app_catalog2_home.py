"""APP-CATALOG.2: a local file chosen from a specimen passport (no process, no Abaqus, no original data).

The sources come from the accepted specimen catalogue (read-only). The files are synthetic copies written in a
temporary folder; where a test needs a byte-verified copy, a temporary copy of the catalogue records the synthetic
file's SHA-256 for that source (the accepted catalogue itself is never changed). The tests check:

- the sources of SP-02, SP-13 (260909 and 260910 a apart), SP-08, SP-12 and SP-15;
- BYTE_VERIFIED, HASH_MISMATCH, NOT_VERIFIED_NO_REFERENCE, a missing file, an unsupported type, a file that is not an
  input, a zip member checked through its extracted copy;
- on the real main window: nothing changes before an explicit Use; Use sets exactly one field, as Browse does; the
  old result becomes inactive through P-1; no modal set, registration, MAC, project or registry change of its own; no
  process and no analysis.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import tkinter as tk
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import synthetic_plate_support as S  # noqa: E402
from services import local_input_registry as registry  # noqa: E402
from services import specimen_catalog_local_files as L  # noqa: E402
from services import specimen_catalog_view as V  # noqa: E402
import home_dashboard as H  # noqa: E402
from test_app_p1_stale_results import STALE  # noqa: E402
from test_app_ui1_home import _Home  # noqa: E402

CATALOGUE = ROOT / "docs" / "auto_id" / "specimen_catalog.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def entry(specimen_id: str) -> dict:
    return copy.deepcopy(V.load_catalogue().entry(specimen_id))


def source(entry_value: dict, file_name: str) -> V.CatalogueSource:
    return next(item for item in V.local_sources(entry_value) if item.file_name == file_name)


def recording(entry_value: dict, file_name: str, local: Path) -> dict:
    """A copy of the record whose reference SHA-256 and size are those of ``local`` (the accepted file is untouched)."""
    entry_value = copy.deepcopy(entry_value)
    for experiment in entry_value.get("experiments", []):
        reference = experiment.get("source", {})
        if reference.get("zip_member", Path(reference.get("relative_path", "")).name) == file_name:
            reference.update(sha256=_sha(local), size_bytes=local.stat().st_size)
            return entry_value
    raise AssertionError(file_name)


class _Folder(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="catalog2_"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.catalogue_before = (_sha(CATALOGUE), CATALOGUE.stat().st_mtime_ns)
        self.addCleanup(lambda: self.assertEqual((_sha(CATALOGUE), CATALOGUE.stat().st_mtime_ns),
                                                 self.catalogue_before))

    def write(self, name: str, content: bytes = b"synthetic UNV stand-in\n" * 50) -> Path:
        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path


# ------------------------------------------------------------------------------------------------ the sources

class SourceListTests(unittest.TestCase):
    def test_sp02_sources_and_the_polymax_reference(self):
        sources = V.local_sources(entry("SP-02"))
        polymax = source(entry("SP-02"), "SP02_polymax_retry_260803.unv")
        self.assertEqual((polymax.side, polymax.loadable, polymax.suffix), (V.EXPERIMENTAL_SIDE, True, ".unv"))
        self.assertEqual(polymax.sha256, "2671db01b6401a9a9bbec7d8c2aa2191b0b35b5ae791756b91c7ccd381a41785")
        self.assertIn("governed set Bravo (1) (active fixture SP02/bravo-1-physical)", polymax.status)
        odb = source(entry("SP-02"), "SP02_Modal_V02.odb")
        self.assertEqual((odb.side, odb.loadable, odb.sha256), (V.FE_SIDE, True, None))
        for name in ("SP02_Modal_V02.inp", "SP02_Honeycomb_V01_baseline.cae", "SP02_Honeycomb_V01_baseline.jnl",
                     "SP02_500by500_Glue420_honeycomb_full_scan_retry_260803.svd"):
            item = source(entry("SP-02"), name)
            self.assertFalse(item.loadable, name)
            self.assertIn("not", item.reason)
            self.assertTrue(V.source_choice_text(item).endswith("· not an input"))
        self.assertFalse(any(item.file_name == "manifest.json" for item in sources))  # never named by a folder
        self.assertTrue(V.source_choice_text(polymax).startswith("Experiment · 260803 retry"))

    def test_sp13_260909_and_260910_a_are_separate_sources(self):
        sp13 = entry("SP-13")
        frozen, best = source(sp13, "SP13_polymax.unv"), source(sp13, "SP13_a_polymax.unv")
        self.assertEqual((frozen.session, best.session), ("260909", "260910 a"))
        self.assertNotEqual(frozen.key, best.key)
        self.assertNotEqual(frozen.sha256, best.sha256)
        self.assertIn("FREQUENCY_ONLY", frozen.status)
        self.assertIn("Bravo (1)", frozen.status)
        self.assertNotIn("Best", frozen.status)
        self.assertIn("governed set Best", best.status)
        self.assertNotIn("FREQUENCY_ONLY", best.status)
        self.assertEqual(frozen.reference["zip_member"], "SP13_polymax.unv")
        self.assertEqual(frozen.reference["relative_path"], "SPname_files_260909_polymax.zip")
        sessions = [item.session for item in V.local_sources(sp13) if item.side == V.EXPERIMENTAL_SIDE]
        self.assertEqual(sessions, ["260909"] * 3 + ["260910 a"] * 3)

    def test_sp08_ungoverned_polymax_stays_ungoverned(self):
        polymax = [item for item in V.local_sources(entry("SP-08")) if "dataset 55" in item.data_kind]
        self.assertEqual(len(polymax), 1)
        self.assertIn("PolyMAX modal fit, not governed", polymax[0].status)
        self.assertNotIn("; governed set", polymax[0].status)

    def test_sp12_has_no_source(self):
        self.assertEqual(V.local_sources(entry("SP-12")), ())

    def test_sp15_ambiguous_identity_is_shown_with_every_source(self):
        sources = V.local_sources(entry("SP-15"))
        self.assertTrue(sources)
        for item in sources:
            self.assertEqual(item.identity, "AMBIGUOUS")
            self.assertIn(("Identity", "AMBIGUOUS: the link of this specimen record to a physical specimen is not "
                                       "established"), V.source_lines(item))

    def test_every_specimen_lists_its_sources_without_error(self):
        catalogue = V.load_catalogue()
        for specimen_id in catalogue.ids:
            for item in V.local_sources(catalogue.entry(specimen_id)):
                self.assertTrue(V.source_lines(item, catalogue))
                if item.side == V.FE_SIDE:
                    self.assertEqual(item.loadable, item.suffix == ".odb", item.file_name)
                else:
                    self.assertEqual(item.loadable, item.suffix in (".unv", ".uff"), item.file_name)


# ------------------------------------------------------------------------------------------------ the check

class LocalCheckTests(_Folder):
    def test_sp02_polymax_copy_with_the_reference_sha_is_byte_verified(self):
        copy_file = self.write("copies/SP02_polymax_retry_260803.unv")
        item = source(recording(entry("SP-02"), "SP02_polymax_retry_260803.unv", copy_file),
                      "SP02_polymax_retry_260803.unv")
        before = (_sha(copy_file), copy_file.stat().st_mtime_ns)
        check = L.check_local_file(item, copy_file)
        self.assertEqual(check.status, L.BYTE_VERIFIED)
        self.assertTrue(check.usable)
        self.assertFalse(check.needs_confirmation)
        self.assertEqual(check.sha256, _sha(copy_file))
        self.assertIn(L.IDENTITY_NOTE, check.message)  # byte identity is not a scientific confirmation
        self.assertEqual((_sha(copy_file), copy_file.stat().st_mtime_ns), before)  # read-only

    def test_the_real_reference_rejects_another_file(self):
        item = source(entry("SP-02"), "SP02_polymax_retry_260803.unv")  # the accepted reference SHA-256
        other = self.write("SP02_polymax_retry_260803.unv")
        check = L.check_local_file(item, other)
        self.assertEqual(check.status, L.HASH_MISMATCH)
        self.assertFalse(check.usable)
        self.assertIn("cannot match", check.message)  # the size differs: no hash needed
        self.assertIsNone(check.sha256)

    def test_a_wrong_sha_of_the_same_size_is_a_mismatch(self):
        local = self.write("x/SP02_polymax_retry_260803.unv", b"a" * 4000)
        item = source(recording(entry("SP-02"), "SP02_polymax_retry_260803.unv", local),
                      "SP02_polymax_retry_260803.unv")
        local.write_bytes(b"b" * 4000)
        check = L.check_local_file(item, local)
        self.assertEqual(check.status, L.HASH_MISMATCH)
        self.assertIn("differs from the reference", check.message)
        self.assertFalse(check.usable)

    def test_no_reference_sha_needs_confirmation_and_is_never_verified(self):
        item = source(entry("SP-02"), "SP02_Modal_V02.odb")
        local = self.write("SP02_Modal_V02.odb", b"synthetic ODB stand-in; never opened")
        check = L.check_local_file(item, local)
        self.assertEqual(check.status, L.NOT_VERIFIED_NO_REFERENCE)
        self.assertTrue(check.usable)
        self.assertTrue(check.needs_confirmation)
        self.assertIsNone(check.sha256)
        self.assertIn("differs from the size the catalogue records", check.message)
        self.assertIn("a hint only", check.message)
        self.assertNotIn("BYTE_VERIFIED", check.message)

    def test_a_missing_file_and_unsupported_types(self):
        polymax = source(entry("SP-02"), "SP02_polymax_retry_260803.unv")
        odb = source(entry("SP-02"), "SP02_Modal_V02.odb")
        self.assertEqual(L.check_local_file(polymax, self.folder / "absent.unv").status, L.FILE_MISSING)
        self.assertEqual(L.check_local_file(polymax, "").status, L.FILE_MISSING)
        self.assertEqual(L.check_local_file(polymax, self.folder).status, L.FILE_MISSING)  # a folder
        for name, item in (("data.txt", polymax), ("data.uff", polymax), ("model.inp", odb),
                           ("manifest.json", odb), ("SP02_Modal_V02.unv", odb)):
            check = L.check_local_file(item, self.write(name))
            self.assertEqual(check.status, L.UNSUPPORTED_TYPE, name)
            self.assertFalse(check.usable)

    def test_a_recorded_file_that_is_not_an_input_cannot_be_checked(self):
        for name in ("SP02_Modal_V02.inp", "SP02_Honeycomb_V01_baseline.cae",
                     "SP02_500by500_Glue420_honeycomb_full_scan_retry_260803.svd"):
            item = source(entry("SP-02"), name)
            check = L.check_local_file(item, self.write(name))
            self.assertEqual(check.status, L.NOT_AN_INPUT, name)
            self.assertEqual(L.allowed_suffixes(item), ())

    def test_a_zip_member_is_checked_through_its_extracted_copy(self):
        extracted = self.write("extracted/SP13_polymax.unv", b"extracted member " * 300)
        sp13 = recording(entry("SP-13"), "SP13_polymax.unv", extracted)
        item = source(sp13, "SP13_polymax.unv")
        check = L.check_local_file(item, extracted)
        self.assertEqual(check.status, L.BYTE_VERIFIED)
        self.assertIn("the member SP13_polymax.unv of SPname_files_260909_polymax.zip", check.message)
        archive = self.write("SPname_files_260909_polymax.zip", b"PK\x03\x04 not opened")
        refused = L.check_local_file(item, archive)
        self.assertEqual(refused.status, L.UNSUPPORTED_TYPE)  # never unpacked, never passed to the UNV reader
        self.assertIn("Extract SP13_polymax.unv", refused.message)
        best = source(sp13, "SP13_a_polymax.unv")  # the 260910 a source does not accept the 260909 member
        self.assertEqual(L.check_local_file(best, extracted).status, L.HASH_MISMATCH)

    def test_sha_is_computed_in_blocks(self):
        local = self.write("big.unv", os.urandom(50_000))
        reads = []
        real_open = open

        def spy(path, mode="r", *args, **kwargs):
            stream = real_open(path, mode, *args, **kwargs)
            self.assertEqual(mode, "rb")  # read-only
            original = stream.read
            stream.read = lambda size=-1: (reads.append(size), original(size))[1]
            return stream

        with mock.patch.object(L, "BLOCK", 4096), mock.patch("builtins.open", spy):
            digest = L.sha256_of(local)
        self.assertEqual(digest, _sha(local))
        self.assertTrue(reads and all(size == 4096 for size in reads))

    def test_a_changed_file_must_be_checked_again(self):
        local = self.write("SP02_Modal_V02.odb", b"x" * 100)
        check = L.check_local_file(source(entry("SP-02"), "SP02_Modal_V02.odb"), local)
        self.assertTrue(L.unchanged_since(check))
        local.write_bytes(b"y" * 101)
        self.assertFalse(L.unchanged_since(check))
        local.unlink()
        self.assertFalse(L.unchanged_since(check))


# ------------------------------------------------------------------------------------------------ Home

class HomeLocalFileTests(_Home):
    def setUp(self):
        super().setUp()
        self.copies = self.folder / "copies"
        self.copies.mkdir()
        self.unv = S.write_experiment(self.copies / "SP02_polymax_retry_260803.unv", S.E0 * 1.05, S.G0)
        self.odb = self.copies / "SP02_Modal_V02.odb"
        self.odb.write_bytes(b"another synthetic ODB stand-in; never opened")
        data = json.loads(CATALOGUE.read_text(encoding="utf-8"))
        sp02 = next(item for item in data["specimens"] if item["specimen_id"] == "SP-02")
        recorded = recording(sp02, "SP02_polymax_retry_260803.unv", self.unv)
        data["specimens"][data["specimens"].index(sp02)] = recorded
        self.test_catalogue = self.folder / "specimen_catalog.json"  # a test copy; the accepted file is untouched
        self.test_catalogue.write_text(json.dumps(data), encoding="utf-8")

    def home(self):
        with mock.patch.object(V, "CATALOGUE_PATH", self.test_catalogue):
            return super().home()

    def pick(self, home, specimen_id, file_name):
        home.show_passport(specimen_id)
        item = next(item for item in home.local_sources if item.file_name == file_name)
        home.select_source(item)
        self.root.update()
        return item

    def locate(self, home, path):
        with mock.patch.object(H.filedialog, "askopenfilename", return_value=str(path)) as dialog:
            home.locate_local_file()
        self.root.update()
        return dialog

    def inputs(self, application):
        return (application.abaqus_path.get(), application.experimental_path.get(),
                application.experimental_modal_set_key.get(), application.result)

    def states(self, home):
        return tuple(str(button.cget("state")) for button in (home.locate_button, home.use_fe_button,
                                                              home.use_experiment_button))

    def test_the_area_follows_the_specimen_and_the_source(self):
        _application, home = self.home()
        self.assertEqual(str(home.source_combo.cget("state")), "disabled")
        self.assertEqual(self.states(home), ("disabled",) * 3)
        home.show_passport("SP-12")
        self.assertEqual(str(home.source_combo.cget("state")), "disabled")
        self.assertIn("No FE or experimental source is recorded for SP-12", str(home.local_prompt.cget("text")))
        home.show_passport("SP-13")
        values = tuple(home.source_combo.cget("values"))
        self.assertIn("Experiment · 260909 · PolyMAX fitted modes (dataset 55) · SP13_polymax.unv", values)
        self.assertIn("Experiment · 260910 a · PolyMAX fitted modes (dataset 55) · SP13_a_polymax.unv", values)
        self.pick(home, "SP-02", "SP02_Modal_V02.inp")
        self.assertEqual(self.states(home), ("disabled",) * 3)  # not an input: nothing to locate
        self.pick(home, "SP-02", "SP02_polymax_retry_260803.unv")
        self.assertEqual(self.states(home), ("normal", "disabled", "disabled"))
        info = " ".join(str(label.cget("text")) for label in home.source_info.winfo_children())
        self.assertIn("SP-02/SP02_polymax_retry_260803.unv in store snadwich", info)
        self.assertIn("a located copy can be byte-verified", info)
        self.pick(home, "SP-15", "SP15_polymax.unv")
        info = " ".join(str(label.cget("text")) for label in home.source_info.winfo_children())
        self.assertIn("AMBIGUOUS", info)

    def test_nothing_changes_before_use_and_use_sets_only_the_experiment(self):
        application, home = self.home()
        self.established(application)
        home = self.refreshed(application)
        before = self.inputs(application)
        self.pick(home, "SP-02", "SP02_polymax_retry_260803.unv")
        dialog = self.locate(home, self.unv)
        dialog.assert_called_once()
        self.assertEqual(home.local_check.status, L.BYTE_VERIFIED)
        self.assertEqual(self.states(home), ("normal", "disabled", "normal"))  # an experiment: never Use as FE
        self.assertEqual(self.inputs(application), before)  # nothing changed before Use
        self.assertIs(application.result, before[3])
        home.use_local_file(V.FE_SIDE)  # the wrong field: ignored
        self.assertEqual(self.inputs(application), before)
        with mock.patch.object(registry, "_read", side_effect=AssertionError("registry read")), \
                mock.patch.object(registry, "_write", side_effect=AssertionError("registry written")), \
                mock.patch.object(application, "_start", side_effect=AssertionError("analysis started")):
            home.use_local_file(V.EXPERIMENTAL_SIDE)
            self.root.update()
        self.assertEqual(application.experimental_path.get(), str(self.unv))
        self.assertEqual(application.abaqus_path.get(), before[0])  # the FE input is unchanged
        self.assert_inactive(application)  # the old result: inactive through the existing P-1 mechanism
        self.assertIn(STALE, application.status.get())
        home = self.refreshed(application)
        self.assertIn(STALE, str(home.result_text.cget("text")))
        self.assertIn("is now the Experimental results file on 1. Files", str(home.local_status.cget("text")))
        self.assertIn("byte-verified", str(home.local_status.cget("text")))

    def test_use_as_fe_needs_confirmation_and_leaves_the_experiment(self):
        application, home = self.home()
        self.established(application)
        before = self.inputs(application)
        self.pick(home, "SP-02", "SP02_Modal_V02.odb")
        self.locate(home, self.odb)
        self.assertEqual(home.local_check.status, L.NOT_VERIFIED_NO_REFERENCE)
        self.assertEqual(self.states(home), ("normal", "normal", "disabled"))
        with mock.patch.object(H.messagebox, "askyesno", return_value=False) as asked:
            home.use_local_file(V.FE_SIDE)
        asked.assert_called_once()
        self.assertIn("cannot be byte-verified", asked.call_args.args[1])
        self.assertEqual(self.inputs(application), before)  # declined: nothing changed
        self.assertIn("Not used", str(home.local_status.cget("text")))
        with mock.patch.object(H.messagebox, "askyesno", return_value=True):
            home.use_local_file(V.FE_SIDE)
        self.root.update()
        self.assertEqual(application.abaqus_path.get(), str(self.odb))
        self.assertEqual(application.experimental_path.get(), before[1])  # the experiment is unchanged
        self.assert_inactive(application)
        self.assertIn("NOT byte-verified (confirmed by you)", str(home.local_status.cget("text")))

    def test_a_mismatch_a_missing_file_or_a_cancel_changes_nothing(self):
        application, home = self.home()
        before = self.inputs(application)
        self.pick(home, "SP-02", "SP02_polymax_retry_260803.unv")
        with mock.patch.object(H.filedialog, "askopenfilename", return_value=""):
            home.locate_local_file()  # cancelled
        self.assertIsNone(home.local_check)
        (self.folder / "wrong").mkdir()
        wrong = S.write_experiment(self.folder / "wrong" / "SP02_polymax_retry_260803.unv", S.E0, S.G0)
        self.locate(home, wrong)
        self.assertEqual(home.local_check.status, L.HASH_MISMATCH)
        self.assertEqual(self.states(home), ("normal", "disabled", "disabled"))
        home.use_local_file(V.EXPERIMENTAL_SIDE)
        self.locate(home, self.folder / "absent.unv")
        self.assertEqual(home.local_check.status, L.FILE_MISSING)
        self.assertIn("FILE_MISSING", str(home.local_status.cget("text")))
        home.use_local_file(V.EXPERIMENTAL_SIDE)
        self.assertEqual(self.inputs(application), before)

    def test_a_file_changed_after_its_check_is_not_used(self):
        application, home = self.home()
        before = self.inputs(application)
        self.pick(home, "SP-02", "SP02_polymax_retry_260803.unv")
        self.locate(home, self.unv)
        self.assertEqual(home.local_check.status, L.BYTE_VERIFIED)
        with open(self.unv, "ab") as stream:
            stream.write(b"\n")
        home.use_local_file(V.EXPERIMENTAL_SIDE)
        self.assertEqual(self.inputs(application), before)
        self.assertIn("changed or disappeared since it was checked", str(home.local_status.cget("text")))

    def test_use_is_exactly_the_browse_contract(self):
        """Use changes the window as setting the field with its Browse button does: no modal set, registration, MAC,
        project or other variable of its own."""
        def snapshot(application):
            return {name: value.get() for name, value in vars(application).items() if isinstance(value, tk.Variable)}

        browse, _ = self.home()
        browse.experimental_path.set(str(self.unv))  # what _choose_experiment does with a chosen path
        self.root.update()
        expected = snapshot(browse)
        application, home = self.home()
        self.pick(home, "SP-02", "SP02_polymax_retry_260803.unv")
        self.locate(home, self.unv)
        home.use_local_file(V.EXPERIMENTAL_SIDE)
        self.root.update()
        found = snapshot(application)
        self.assertEqual({k: v for k, v in found.items() if k != "status"},
                         {k: v for k, v in expected.items() if k != "status"})
        self.assertEqual(found["experimental_modal_set_key"], expected["experimental_modal_set_key"])

    def test_inputs_are_locked_while_an_analysis_runs(self):
        application, home = self.home()
        self.pick(home, "SP-02", "SP02_polymax_retry_260803.unv")
        self.locate(home, self.unv)
        before = self.inputs(application)
        self.start(application)  # the real Run, its worker not started
        home = self.refreshed(application)
        self.assertEqual(self.states(home), ("disabled",) * 3)
        home.use_local_file(V.EXPERIMENTAL_SIDE)
        self.assertEqual(self.inputs(application)[:3], before[:3])
        self.assertIn("An analysis is running", str(home.local_status.cget("text")))


if __name__ == "__main__":
    unittest.main()
