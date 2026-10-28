"""APP-WORKSPACE.2: the Current workspace panel of Home (real main window, synthetic data, no process).

The panel shows the program's own state through ``services.workspace_context``. Its working specimen is chosen
separately from the passport, Locate -> Verify -> Use is unchanged, nothing is run, a registration hash is never
taken as PHYSICAL, and production Auto-ID stays NOT_AUTHORISED.
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
CAPTIONS = ["Working specimen", "FE file", "Experimental file", "Modal set", "Analysis", "Registration",
            "Production Auto-ID"]


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


class PanelTests(_Workspace):
    def test_the_panel_sits_between_the_four_areas_and_the_passport(self):
        _application, home = self.home()
        titles = {key: [str(child.cget("text")) for child in card.winfo_children()
                        if child.winfo_class() == "TLabel"][0] for key, card in home.cards.items()}
        self.assertEqual(titles["workspace"], "Current workspace")
        self.assertEqual(titles["catalogue"], "5  Specimen catalogue / Паспорт образца")  # unchanged
        self.assertEqual(int(home.cards["workspace"].grid_info()["row"]) + 1,
                         int(home.cards["catalogue"].grid_info()["row"]))

    def test_the_initial_state_is_shown_without_guessing(self):
        _application, home = self.home()
        rows = self.rows(home)
        self.assertEqual(list(rows), CAPTIONS)
        self.assertEqual(home.working_specimen_choice.get(), H.NO_WORKING_SPECIMEN)
        self.assertIn("None chosen", rows["Working specimen"][1])
        self.assertIn(str(self.folder / "plate.odb"), rows["FE file"][1])  # the program's own field
        self.assertIn(str(self.fitted_path), rows["Experimental file"][1])
        self.assertNotIn("recorded for", rows["FE file"][1])  # no specimen: no catalogue name comparison
        self.assertTrue(rows["Analysis"][1].startswith(("READY", "NO_DATA")))
        self.assertTrue(rows["Registration"][1].startswith("NONE: no registration is applied"))
        self.assertTrue(rows["Production Auto-ID"][1].startswith("NOT_AUTHORISED: blocked."))
        self.assertEqual(rows["Production Auto-ID"][0], H.MARKS[H.NEEDED])


class SeparationTests(_Workspace):
    def test_the_working_specimen_and_the_passport_are_separate_choices(self):
        application, home = self.home()
        self.established(application)
        home = self.refreshed(application)
        before, passport = self.inputs(application), self.passport_state(home)
        with mock.patch.object(application, "_start", side_effect=AssertionError("analysis started")):
            home.working_specimen_choice.set(V.choice_text(home.catalogue.entry("SP-02")))
            home.working_specimen_combo.event_generate("<<ComboboxSelected>>")
            self.root.update()
        self.assertEqual(home.working_specimen_id, "SP-02")
        self.assertEqual(self.inputs(application), before)  # no field of the analysis changed
        self.assertEqual(self.passport_state(home), passport)  # the passport stays as it was (none shown)
        self.assertIn("SP-02: type sandwich, family old-T300-plain-0.45", self.rows(home)["Working specimen"][1])
        home.show_passport("SP-13")  # viewing a passport is another action
        self.root.update()
        self.assertEqual(home.working_specimen_id, "SP-02")
        self.assertEqual(home.working_specimen_choice.get(), V.choice_text(home.catalogue.entry("SP-02")))
        self.assertEqual(self.inputs(application), before)
        home.choose_working_specimen("SP-15")
        self.assertEqual(home.specimen_choice.get(), V.choice_text(home.catalogue.entry("SP-13")))  # untouched
        home.working_specimen_choice.set(H.NO_WORKING_SPECIMEN)
        home.choose_working_specimen()
        self.assertIsNone(home.working_specimen_id)
        self.assertIn("None chosen", self.rows(home)["Working specimen"][1])

    def test_use_from_the_passport_updates_the_panel_and_runs_nothing(self):
        application, home = self.home()
        home.choose_working_specimen("SP-02")
        home.show_passport("SP-02")
        item = next(item for item in home.local_sources if item.file_name == "SP02_polymax_retry_260803.unv")
        home.select_source(item)
        with mock.patch.object(H.filedialog, "askopenfilename", return_value=str(self.unv)):
            home.locate_local_file()
        self.assertEqual(home.local_check.status, L.BYTE_VERIFIED)
        self.assertNotIn(str(self.unv), self.rows(home)["Experimental file"][1])  # Locate / Verify change nothing
        with mock.patch.object(application, "_start", side_effect=AssertionError("analysis started")):
            home.use_local_file(V.EXPERIMENTAL_SIDE)
            self.root.update()
        self.assertEqual(application.experimental_path.get(), str(self.unv))
        home = self.refreshed(application)
        rows = self.rows(home)
        self.assertIn(str(self.unv), rows["Experimental file"][1])
        self.assertIn("is one recorded for SP-02 in the catalogue (name only: the file is not verified by this)",
                      rows["Experimental file"][1])
        self.assertFalse(application.running)
        self.assertNotIn("SUCCESS", rows["Analysis"][1])
        self.assertTrue(rows["Registration"][1].startswith("NONE"))


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
    def test_a_registration_hash_from_the_result_is_unknown_never_physical(self):
        application, home = self.home()
        self.established(application)
        home.choose_working_specimen("SP-02")
        home = self.with_registration_records(application, geometry_verified_registration={
            "registration_hash": SP02_PHYSICAL, "specimen": "SP02"})
        mark, text = self.rows(home)["Registration"]
        self.assertTrue(text.startswith("UNKNOWN: registration 9b63f6c89133… was applied by reuse by FE geometry "
                                        "identity, but its basis is not recorded"), text)
        self.assertIn("no binding to this working set is confirmed", text)
        self.assertIn("Catalogue (reference only): SP-02 records this hash as PHYSICAL", text)
        self.assertNotIn("PHYSICAL (as stated)", text)
        self.assertEqual(mark, H.MARKS[H.WARN])
        self.assertIs(home.workspace_context.registration.kind, W.RegistrationKind.UNKNOWN)
        self.assertFalse(home.workspace_context.registration.stated_physical_hash_recorded_in_catalogue)
        home.choose_working_specimen("SP-13")  # another specimen: the hash is not attributed to it
        text = self.rows(home)["Registration"][1]
        self.assertTrue(text.startswith("UNKNOWN"))
        self.assertNotIn("Catalogue (reference only)", text)
        self.assertIn("The registration is not recorded in the catalogue for this specimen.", text)

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
        self.assertNotIn("cross-reference", texts[W.RegistrationKind.LEGACY_REPLAY])
        self.assertNotEqual(H.REGISTRATION_STATES[W.RegistrationKind.PHYSICAL], H.OK)  # never a green "verified"


class ModalSetAndUnknownTests(_Workspace):
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
        self.assertIn("no recorded name",
                      H.selected_modal_set_name(app("x", SimpleNamespace(key="x", display_name=" ")))[1])
        context = W.build_workspace_context("SP-02", catalogue_view=V.load_catalogue())
        row = H.workspace_rows(context, modal_set_note="the selected modal set could not be identified")[3]
        self.assertEqual(row, (H.WARN, "Modal set", "NOT_CHECKED: the selected modal set could not be identified."))

    def test_a_catalogue_modal_set_status_is_never_shown_as_confirmed(self):
        context = W.build_workspace_context("SP-02", experimental_path=r"D:\x\SP02_polymax_retry_260803.unv",
                                            modal_set="Bravo (1)", catalogue_view=V.load_catalogue())
        self.assertIs(context.modal_set.status, W.ModalSetStatus.GOVERNED)
        state, caption, text = H.workspace_rows(context)[3]
        self.assertEqual((state, caption), (H.INFO, "Modal set"))  # never a green confirmation from names
        self.assertTrue(text.startswith("Bravo (1): catalogue status GOVERNED"), text)
        self.assertIn("Matched by the set name and the file name (SP02_polymax_retry_260803.unv) only; the file "
                      "content is not verified by this.", text)
        wrong = W.build_workspace_context("SP-02", experimental_path=r"D:\x\SP02_polymax_retry_260803.unv",
                                          modal_set="Bravo (2)", catalogue_view=V.load_catalogue())
        self.assertEqual(H.workspace_rows(wrong)[3][:2], (H.WARN, "Modal set"))
        self.assertIn("NOT_IN_CATALOGUE", H.workspace_rows(wrong)[3][2])

    def test_the_real_modal_set_of_a_non_catalogue_file_is_not_given_a_catalogue_status(self):
        _application, home = self.home()
        home.choose_working_specimen("SP-02")
        text = self.rows(home)["Modal set"][1]
        self.assertNotIn("GOVERNED", text.split(":")[1] if ":" in text else text)
        self.assertIsNot(home.workspace_context.modal_set.status, W.ModalSetStatus.GOVERNED)

    def test_unknown_specimen_and_unusable_catalogue(self):
        _application, home = self.home()
        home.choose_working_specimen("SP-99")
        self.assertIsNone(home.working_specimen_id)
        context = W.build_workspace_context("SP-99", catalogue_view=V.load_catalogue())
        self.assertIn("UNKNOWN: SP-99 is not in the catalogue", H.workspace_rows(context)[0][2])
        with mock.patch.object(V, "CATALOGUE_PATH", self.folder / "missing.json"):
            application, home = _Home.home(self)
        self.assertEqual(str(home.working_specimen_combo.cget("state")), "disabled")
        rows = self.rows(home)
        self.assertIn("UNKNOWN: the specimen catalogue cannot be used", rows["Working specimen"][1])
        self.assertTrue(rows["Production Auto-ID"][1].startswith("NOT_AUTHORISED"))


class BlockAndSwitchTests(_Workspace):
    def test_production_auto_id_stays_not_authorised(self):
        application, home = self.home()
        states = [self.rows(home)["Production Auto-ID"]]
        self.established(application)
        home.choose_working_specimen("SP-02")
        home = self.with_registration_records(application, geometry_verified_registration={
            "registration_hash": SP02_PHYSICAL})
        states.append(self.rows(home)["Production Auto-ID"])
        for mark, text in states:
            self.assertEqual(mark, H.MARKS[H.NEEDED])
            self.assertTrue(text.startswith("NOT_AUTHORISED: blocked. NO_TRUSTED_AUTHORISATION_SOURCE"), text)

    def test_home_and_expert_switching_keeps_the_working_specimen(self):
        application, home = self.home()
        self.established(application)
        home.choose_working_specimen("SP-02")
        before = (self.inputs(application), self.rows(home))
        for view in (H.EXPERT, H.HOME, H.EXPERT, H.HOME):
            application._show_view(view)
            self.root.update()
        home = self.refreshed(application)
        self.assertEqual(home.working_specimen_id, "SP-02")
        self.assertEqual((self.inputs(application), self.rows(home)), before)
        self.assertEqual(len(application.tabs.tabs()), 11)


if __name__ == "__main__":
    unittest.main()
