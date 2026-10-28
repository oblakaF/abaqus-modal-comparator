"""APP-WORKSPACE.2 / F1: the Current workspace panel of Home (real main window, synthetic data, no process).

The panel shows the user's own data through ``services.workspace_context``. It does not depend on the laboratory
archive:

- with no file chosen, it is an empty workspace that asks for the two files;
- any FE / UNV / UFF file is a workspace, with an optional label of the user's;
- nothing of the archive (modal-set status, registration, scientific status) is attributed to the data, not even to a
  new measurement of an archived specimen;
- the archive (SP-01 ... SP-15) is shown only after Open research archive...

Locate -> Verify -> Use is unchanged, nothing is run, a registration hash is never taken as PHYSICAL, and production
Auto-ID stays NOT_AUTHORISED.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import synthetic_plate_support as S  # noqa: E402
import home_dashboard as H  # noqa: E402
from domain.specimen_manifest import RegistrationBasisStatus  # noqa: E402
from services import specimen_catalog_local_files as L  # noqa: E402
from services import specimen_catalog_view as V  # noqa: E402
from services import workspace_context as W  # noqa: E402
from ui_policy import AnalysisState  # noqa: E402
from test_app_catalog2_home import CATALOGUE, recording  # noqa: E402
from test_app_p1_stale_results import DISCARDED, STALE  # noqa: E402
from test_app_ui1_home import _Home  # noqa: E402

SP02_PHYSICAL = "9b63f6c891331ba55a6ee2797f142bf0b75117d9bffbf3ab312ee08a418e882c"
SP02_LEGACY = "9bf736d3650b491f8abf5f1a9abd60f6616639fa5f2f8811a896c5a04fbdc164"
CAPTIONS = ["FE file", "Experimental file", "Modal set", "Analysis", "Registration", "Production Auto-ID"]
ARCHIVE_WORDS = ("GOVERNED", "catalogue", "Catalogue", "PHYSICAL", "OTHER", "NOT_GOVERNED")  # attributions


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _Workspace(_Home):
    def setUp(self):
        super().setUp()
        self.catalogue_before = _sha(CATALOGUE)
        self.addCleanup(lambda: self.assertEqual(_sha(CATALOGUE), self.catalogue_before))
        self.copies = self.folder / "copies"
        self.copies.mkdir()
        self.unv = S.write_experiment(self.copies / "SP02_polymax_retry_260803.unv", S.E0 * 1.05, S.G0)
        data = json.loads(CATALOGUE.read_text(encoding="utf-8"))
        sp02 = next(item for item in data["specimens"] if item["specimen_id"] == "SP-02")
        data["specimens"][data["specimens"].index(sp02)] = recording(sp02, "SP02_polymax_retry_260803.unv", self.unv)
        self.test_catalogue = self.folder / "specimen_catalog.json"  # a test copy; the accepted file is untouched
        self.test_catalogue.write_text(json.dumps(data), encoding="utf-8")

    def home(self):
        with mock.patch.object(V, "CATALOGUE_PATH", self.test_catalogue):
            return super().home()

    def rows(self, home):
        return {caption: (mark, text) for mark, caption, text in self.texts(home.workspace_rows)}

    def all_text(self, home):
        return " ".join(text for _mark, text in self.rows(home).values())

    def inputs(self, application):
        return (application.abaqus_path.get(), application.experimental_path.get(),
                application.experimental_modal_set_key.get(), application.experimental_modal_set_display.get(),
                application.start_mode.get(), application.end_mode.get(), application.result,
                application.analysis_state, application.dirty_tracker.dirty)

    def passport_state(self, home):
        return (home.specimen_choice.get(), len(home.passport.winfo_children()), home.local_source,
                home.local_check, home.source_choice.get())

    def with_registration_records(self, application, **records):
        application.result.metadata.update(records)
        return self.refreshed(application)

    def shown(self, widget):
        return bool(widget.winfo_manager())


class EmptyAndArbitraryDataTests(_Workspace):
    def test_an_empty_start_asks_for_the_two_files_and_lists_no_specimen(self):
        application, home = self.home()
        application.abaqus_path.set("")
        application.experimental_path.set("")
        home = self.refreshed(application)
        self.assertTrue(self.shown(home.workspace_empty))
        self.assertFalse(self.shown(home.workspace_details))
        self.assertIn("No data loaded yet. Choose an FE results file", str(home.workspace_empty_text.cget("text")))
        self.assertEqual([str(button.cget("text")) for button in (home.workspace_choose_fe,
                                                                  home.workspace_choose_experiment)],
                         ["Choose FE file...", "Choose experimental file..."])
        self.assertFalse(self.shown(home.cards["catalogue"]))  # no SP list by default
        self.assertFalse(home.research_archive_open)
        self.assertEqual(str(home.archive_button.cget("text")), "Open research archive...")
        workspace_text = " ".join(str(child.cget("text")) for child in home.cards["workspace"].winfo_children()
                                  if child.winfo_class() == "TLabel")
        self.assertNotIn("SP-0", workspace_text)
        with mock.patch.object(application, "_choose_abaqus") as chooser:  # the same handler as 1. Files
            home.workspace_choose_fe.configure(command=application._choose_abaqus)
            home.workspace_choose_fe.invoke()
        chooser.assert_called_once()

    def test_any_files_make_a_workspace_without_an_archive_record(self):
        application, home = self.home()
        fe = self.copies / "my_plate_model.odb"
        fe.write_bytes(b"a user's own ODB stand-in; never opened")
        experiment = S.write_experiment(self.copies / "bench_test_0428.unv", S.E0 * 0.97, S.G0)
        application.abaqus_path.set(str(fe))
        application.experimental_path.set(str(experiment))
        self.settle(application)
        home = self.refreshed(application)
        self.assertTrue(self.shown(home.workspace_details))
        self.assertFalse(self.shown(home.workspace_empty))
        rows = self.rows(home)
        self.assertEqual(list(rows), CAPTIONS)
        self.assertEqual(rows["FE file"][1], str(fe))  # the path only: no archive comparison of the name
        self.assertEqual(rows["Experimental file"][1], str(experiment))
        self.assertTrue(rows["Registration"][1].startswith("NONE"))
        self.assertTrue(rows["Production Auto-ID"][1].startswith("NOT_AUTHORISED: blocked."))
        self.assertFalse(any(word in self.all_text(home) for word in ARCHIVE_WORDS[:2]))
        self.assertEqual(home.workspace_context.requested_specimen_id, None)  # never an archive specimen

    def test_the_specimen_name_is_an_optional_label_only(self):
        application, home = self.home()
        before = self.inputs(application)
        self.assertEqual(home.specimen_name.get(), "")
        with mock.patch.object(application, "_start", side_effect=AssertionError("analysis started")):
            home.specimen_name.set("SP-02")  # an archive name typed by the user is still only a label
            self.root.update()
        self.assertEqual(self.inputs(application), before)
        self.assertIsNone(home.workspace_context.requested_specimen_id)
        self.assertFalse(home.workspace_context.specimen_known)
        label = H.workspace_rows(home.workspace_context, specimen_name=home.specimen_name.get())[0]
        self.assertEqual(label, (H.INFO, "Specimen", "SP-02 (your label; not looked up in any archive)."))
        self.assertEqual(H.workspace_rows(home.workspace_context)[0][2], "Unnamed (a name is optional).")


class NewSeriesTests(_Workspace):
    def test_a_new_measurement_of_sp02_gets_nothing_from_the_archive(self):
        application, home = self.home()
        series = S.write_experiment(self.copies / "SP02_remeasured_2026-10-28.unv", S.E0 * 1.02, S.G0)
        application.experimental_path.set(str(series))
        self.settle(application)
        home.specimen_name.set("SP-02")
        self.established(application)
        home = self.with_registration_records(application, geometry_verified_registration={
            "registration_hash": SP02_PHYSICAL})
        rows = self.rows(home)
        self.assertEqual(rows["Experimental file"][1], str(series))  # not an error, not "unknown"
        self.assertTrue(rows["Analysis"][1].startswith("SUCCESS"))
        registration = rows["Registration"][1]
        self.assertTrue(registration.startswith("UNKNOWN: registration 9b63f6c89133… was applied"), registration)
        for word in ARCHIVE_WORDS:
            self.assertNotIn(word, self.all_text(home), word)  # no old modal set, registration or status
        self.assertEqual(rows["Registration"][0], H.MARKS[H.WARN])
        self.assertIsNone(home.workspace_context.registration.catalogue_reference)

    def test_even_the_archived_file_name_gets_no_archive_status(self):
        application, home = self.home()
        application.experimental_path.set(str(self.unv))  # the name the archive records for SP-02
        self.settle(application)
        home.specimen_name.set("SP-02")
        home = self.refreshed(application)
        self.assertNotEqual(home.workspace_context.modal_set.status, W.ModalSetStatus.GOVERNED)
        for word in ARCHIVE_WORDS:
            self.assertNotIn(word, self.all_text(home), word)
        modal = self.rows(home)["Modal set"][1]
        if not modal.startswith(("NOT_SELECTED", "NOT_CHECKED")):
            self.assertIn("It is not compared with the research archive", modal)


class ArchiveTests(_Workspace):
    def test_the_research_archive_is_opened_only_by_its_explicit_action(self):
        application, home = self.home()
        before, rows = self.inputs(application), self.rows(home)
        self.assertFalse(self.shown(home.cards["catalogue"]))
        home.archive_button.invoke()
        self.root.update()
        self.assertTrue(home.research_archive_open)
        self.assertTrue(self.shown(home.cards["catalogue"]))
        self.assertEqual(int(home.cards["catalogue"].grid_info()["row"]),
                         int(home.cards["workspace"].grid_info()["row"]) + 1)
        self.assertEqual(len(home.specimen_combo.cget("values")), 14)  # the archive data are unchanged
        self.assertEqual(str(home.archive_button.cget("text")), "Close research archive")
        self.assertEqual((self.inputs(application), self.rows(home)), (before, rows))  # opening changes nothing
        home.show_passport("SP-13")
        self.root.update()
        self.assertEqual((self.inputs(application), self.rows(home)), (before, rows))  # a passport: no workspace
        home.archive_button.invoke()
        self.root.update()
        self.assertFalse(self.shown(home.cards["catalogue"]))
        self.assertEqual(home.specimen_choice.get(), V.choice_text(home.catalogue.entry("SP-13")))  # kept, hidden

    def test_locate_verify_use_from_the_archive_updates_the_workspace_and_runs_nothing(self):
        application, home = self.home()
        home.open_research_archive()
        home.show_passport("SP-02")
        item = next(item for item in home.local_sources if item.file_name == "SP02_polymax_retry_260803.unv")
        home.select_source(item)
        with mock.patch.object(H.filedialog, "askopenfilename", return_value=str(self.unv)):
            home.locate_local_file()
        self.assertEqual(home.local_check.status, L.BYTE_VERIFIED)
        self.assertNotEqual(self.rows(home)["Experimental file"][1], str(self.unv))  # Locate / Verify: nothing
        with mock.patch.object(application, "_start", side_effect=AssertionError("analysis started")):
            home.use_local_file(V.EXPERIMENTAL_SIDE)
            self.root.update()
        self.assertEqual(application.experimental_path.get(), str(self.unv))
        home = self.refreshed(application)
        self.assertEqual(self.rows(home)["Experimental file"][1], str(self.unv))
        self.assertFalse(application.running)
        for word in ARCHIVE_WORDS:  # a verified archive file still gets no archive status in the workspace
            self.assertNotIn(word, self.all_text(home), word)


class ResultTests(_Workspace):
    def test_pairs_and_mac_only_for_the_result_on_display(self):
        application, home = self.home()
        self.start(application)
        home = self.refreshed(application)
        self.assertTrue(self.rows(home)["Analysis"][1].startswith("RUNNING: no mode pairs and no MAC"))
        application._complete(self.comparison_result())
        home = self.refreshed(application)
        self.assertIs(application.analysis_state, AnalysisState.SUCCESS)
        pairs = len(application.result.pairs)
        self.assertGreater(pairs, 0)
        self.assertEqual(self.rows(home)["Analysis"][1], f"SUCCESS: {pairs} admissible mode pairs; MAC shown.")
        application.end_mode.set(8)  # the inputs change: the result is inactive (P-1)
        home = self.refreshed(application)
        analysis = self.rows(home)["Analysis"][1]
        self.assertNotIn("SUCCESS", analysis)
        self.assertIn("no mode pairs and no MAC on display", analysis)
        self.assertIn(STALE, analysis)

    def test_a_result_discarded_while_running_is_never_shown(self):
        application, home = self.home()
        self.start(application)
        application.experimental_path.set(str(self.unv))
        application._complete(self.comparison_result())
        home = self.refreshed(application)
        analysis = self.rows(home)["Analysis"][1]
        self.assertNotIn("SUCCESS", analysis)
        self.assertIn(DISCARDED, analysis)


class RegistrationTests(_Workspace):
    def test_conflicting_or_missing_registration_records(self):
        application, home = self.home()
        self.established(application)
        home = self.refreshed(application)
        self.assertTrue(self.rows(home)["Registration"][1].startswith(
            "NONE: no registration is applied (the result applied no frozen registration"))
        home = self.with_registration_records(
            application, geometry_verified_registration={"registration_hash": SP02_PHYSICAL},
            governed_registration={"registration_hash": SP02_LEGACY})
        text = self.rows(home)["Registration"][1]
        self.assertTrue(text.startswith("UNKNOWN: the result records conflicting or incomplete registrations"), text)

    def test_all_five_kinds_are_shown_distinctly(self):
        catalogue = V.load_catalogue()
        cases = {
            W.RegistrationKind.PHYSICAL: dict(registration_basis=RegistrationBasisStatus.PHYSICAL,
                                              registration_hash=SP02_PHYSICAL),
            W.RegistrationKind.LEGACY_REPLAY: dict(registration_basis=RegistrationBasisStatus.LEGACY_REPLAY,
                                                   registration_hash=SP02_LEGACY),
            W.RegistrationKind.INCOMPLETE: dict(registration_basis=RegistrationBasisStatus.INCOMPLETE),
            W.RegistrationKind.NONE: {},
            W.RegistrationKind.UNKNOWN: dict(registration_hash=SP02_PHYSICAL),
        }
        texts = {}
        for kind, arguments in cases.items():
            context = W.build_workspace_context("SP-02", catalogue_view=catalogue, **arguments)
            self.assertIs(context.registration.kind, kind)
            state, caption, text = H.workspace_rows(context, registration_how="a test")[5]
            self.assertEqual((caption, state), ("Registration", H.REGISTRATION_STATES[kind]))
            self.assertTrue(text.startswith(kind.value), text)
            texts[kind] = text
        self.assertEqual(len(set(texts.values())), 5)
        self.assertIn("cross-reference only, not a verification of the data", texts[W.RegistrationKind.PHYSICAL])
        self.assertNotEqual(H.REGISTRATION_STATES[W.RegistrationKind.PHYSICAL], H.OK)  # never a green "verified"
        user = W.build_workspace_context(None, registration_hash=SP02_PHYSICAL, catalogue_view=catalogue)
        text = H.workspace_rows(user, registration_how="a test")[5][2]  # the user's data: no archive words
        self.assertTrue(text.startswith("UNKNOWN"))
        self.assertNotIn("catalogue", text.lower())


class ModalSetTests(_Workspace):
    def test_the_modal_set_name_comes_from_the_discovered_set_object(self):
        def app(key, *sets):
            return SimpleNamespace(experimental_modal_set_key=SimpleNamespace(get=lambda: key),
                                   available_experimental_modal_sets=list(sets),
                                   experimental_modal_set_display=SimpleNamespace(get=lambda: "Bravo (1) — 9 modes"))

        bravo = SimpleNamespace(key="bravo-1", display_name="Bravo (1)")
        self.assertEqual(H.selected_modal_set_name(app("")), (None, ""))
        self.assertEqual(H.selected_modal_set_name(app("bravo-1", bravo)), ("Bravo (1)", ""))
        self.assertIn("could not be identified", H.selected_modal_set_name(app("other", bravo))[1])
        twin = SimpleNamespace(key="bravo-1-abc", display_name="Bravo (1)")
        self.assertIn("more than one set named", H.selected_modal_set_name(app("bravo-1", bravo, twin))[1])
        context = W.build_workspace_context(None, experimental_path=r"D:\x\SP02_polymax_retry_260803.unv",
                                            modal_set="Bravo (1)", catalogue_view=V.load_catalogue())
        state, caption, text = H.workspace_rows(context)[3]
        self.assertEqual((state, caption), (H.INFO, "Modal set"))
        self.assertEqual(text, "Bravo (1): selected in the experimental file. It is not compared with the research "
                               "archive, so no archive status is given to it.")
        unresolved = H.workspace_rows(context, modal_set_note="the selected modal set could not be identified")[3]
        self.assertEqual(unresolved, (H.WARN, "Modal set",
                                      "NOT_CHECKED: the selected modal set could not be identified."))


class BlockAndSwitchTests(_Workspace):
    def test_production_auto_id_stays_not_authorised(self):
        application, home = self.home()
        states = [self.rows(home)["Production Auto-ID"]]
        self.established(application)
        home.specimen_name.set("SP-02")
        home = self.with_registration_records(application, geometry_verified_registration={
            "registration_hash": SP02_PHYSICAL})
        states.append(self.rows(home)["Production Auto-ID"])
        for mark, text in states:
            self.assertEqual(mark, H.MARKS[H.NEEDED])
            self.assertTrue(text.startswith("NOT_AUTHORISED: blocked. NO_TRUSTED_AUTHORISATION_SOURCE"), text)

    def test_home_and_expert_switching_keeps_the_workspace(self):
        application, home = self.home()
        self.established(application)
        home.specimen_name.set("my plate")
        before = (self.inputs(application), self.rows(home), home.research_archive_open)
        for view in (H.EXPERT, H.HOME, H.EXPERT, H.HOME):
            application._show_view(view)
            self.root.update()
        home = self.refreshed(application)
        self.assertEqual(home.specimen_name.get(), "my plate")
        self.assertEqual((self.inputs(application), self.rows(home), home.research_archive_open), before)
        self.assertEqual(len(application.tabs.tabs()), 11)


if __name__ == "__main__":
    unittest.main()
