"""APP-WORKSPACE.1: the headless workspace context (no Tkinter, no file opened but the accepted catalogue).

The accepted specimen catalogue is read as it is (read only); edge cases use small in-memory catalogue views.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.specimen_manifest import RegistrationBasisStatus  # noqa: E402
from services import specimen_catalog_view as catalog  # noqa: E402
from services import workspace_context as W  # noqa: E402
from ui_policy import AnalysisState  # noqa: E402

SP02_PHYSICAL = "9b63f6c891331ba55a6ee2797f142bf0b75117d9bffbf3ab312ee08a418e882c"
SP02_LEGACY = "9bf736d3650b491f8abf5f1a9abd60f6616639fa5f2f8811a896c5a04fbdc164"
SP13_PHYSICAL = "2eeeaa8698851baf33c640a5e741a91a67c6629b436700a920ba9333061cd823"
SP02_UNV = r"C:\copies\SP02_polymax_retry_260803.unv"  # a path is never opened; only its file name is compared


def view(entries, status="ACCEPTED", problem=""):
    return catalog.CatalogueView(Path("in-memory.json"), tuple(entries), problem,
                                 {"schema": catalog.CATALOGUE_SCHEMA, "status": status})


def context(specimen_id="SP-02", **kwargs):
    return W.build_workspace_context(specimen_id, **kwargs)


class AcceptedCatalogueTests(unittest.TestCase):
    def test_identity_family_and_statuses_come_from_the_accepted_catalogue(self):
        data = json.loads(catalog.CATALOGUE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "ACCEPTED")
        for entry in data["specimens"]:
            record = context(entry["specimen_id"]).specimen
            self.assertEqual(record.specimen_id, entry["specimen_id"])
            self.assertEqual(record.specimen_type, entry["type"])
            self.assertEqual(record.family_id, entry["family_id"])
            self.assertEqual(record.catalogue_auto_id_status, tuple(entry["auto_id_status"]))  # verbatim

    def test_reading_leaves_the_catalogue_unchanged(self):
        before = hashlib.sha256(catalog.CATALOGUE_PATH.read_bytes()).hexdigest()
        context("SP-02", experimental_path=SP02_UNV, modal_set="Bravo (1)")
        self.assertEqual(hashlib.sha256(catalog.CATALOGUE_PATH.read_bytes()).hexdigest(), before)

    def test_a_catalogue_that_is_not_accepted_or_not_readable_gives_no_specimen(self):
        entry = {"specimen_id": "SP-02", "type": "sandwich", "family_id": "f", "auto_id_status": []}
        for catalogue_view, words in ((view([entry], status="DRAFT"), "not accepted (status DRAFT)"),
                                      (view([entry], status=None), "not accepted (status UNKNOWN)"),
                                      (catalog.load_catalogue(ROOT / "no-such-catalogue.json"), "not found")):
            result = context("SP-02", catalogue_view=catalogue_view)
            self.assertIn(words, result.catalogue_problem)
            self.assertFalse(result.specimen_known)
            self.assertEqual((result.specimen_id, result.specimen_type, result.family_id),
                             (W.UNKNOWN, W.UNKNOWN, W.UNKNOWN))

    def test_missing_catalogue_values_stay_unknown(self):
        entry = {"specimen_id": "SP-X", "type": None, "family_id": " ", "auto_id_status": "NEEDS_GOVERNANCE",
                 "registration": {"physical": {"path": None, "registration_hash": "a" * 64}, "legacy": "broken"},
                 "experiments": [{"source": {"relative_path": "SP-X/x.unv"}, "fitted_sets": [{"set": "A"}, {"x": 1}]},
                                 "not an experiment"],
                 "fe_assets": None}
        record = context("SP-X", catalogue_view=view([entry])).specimen
        self.assertEqual((record.specimen_type, record.family_id), (W.UNKNOWN, W.UNKNOWN))
        self.assertEqual(record.catalogue_auto_id_status, ())  # not a list: no status is invented
        self.assertEqual([(s.name, s.mode_count, s.status) for s in record.modal_sets],
                         [("A", None, W.ModalSetStatus.NOT_GOVERNED)])
        self.assertEqual([(r.kind, r.path, r.status_text) for r in record.registrations],
                         [(W.RegistrationKind.PHYSICAL, W.UNKNOWN, W.UNKNOWN)])
        self.assertEqual(record.fe_source_names, ())


class UnknownSpecimenTests(unittest.TestCase):
    def test_an_unknown_specimen_is_represented_not_guessed(self):
        for specimen_id in ("SP-99", "SP02", "sp-02", "", "   ", None):
            result = context(specimen_id, fe_path=r"C:\x\SP02_Modal_V02.odb", experimental_path=SP02_UNV,
                             modal_set="Bravo (1)", registration_hash=SP02_PHYSICAL)
            self.assertFalse(result.specimen_known, specimen_id)
            self.assertEqual((result.specimen_id, result.specimen_type, result.family_id),
                             (W.UNKNOWN, W.UNKNOWN, W.UNKNOWN))
            self.assertEqual(result.catalogue_auto_id_status, ())
            self.assertEqual(result.missing[0], "specimen")
            self.assertEqual(result.modal_set.status, W.ModalSetStatus.UNKNOWN)
            self.assertEqual(result.registration.kind, W.RegistrationKind.UNKNOWN)  # never the catalogue's PHYSICAL
            self.assertFalse(result.fe_source.catalogue_name_match)
            self.assertFalse(result.experimental_source.catalogue_name_match)
            self.assertEqual(result.production_auto_id.status, "NOT_AUTHORISED")
        self.assertEqual(context("SP-99").requested_specimen_id, "SP-99")
        self.assertIsNone(context("  ").requested_specimen_id)


class SourceTests(unittest.TestCase):
    def test_incomplete_sources_are_listed_as_missing(self):
        self.assertEqual(context("SP-02").missing, ("FE source", "experimental source", "modal set", "registration"))
        only_fe = context("SP-02", fe_path=r"D:\models\SP02_Modal_V02.odb")
        self.assertEqual(only_fe.missing, ("experimental source", "modal set", "registration"))
        self.assertTrue(only_fe.fe_source.selected)
        self.assertEqual(only_fe.fe_source.file_name, "SP02_Modal_V02.odb")
        self.assertFalse(only_fe.experimental_source.selected)
        self.assertEqual(only_fe.experimental_source.file_name, W.UNKNOWN)
        only_experiment = context("SP-02", experimental_path=SP02_UNV, modal_set="Bravo (1)")
        self.assertEqual(only_experiment.missing, ("FE source", "registration"))
        complete = context("SP-02", fe_path=r"D:\x\manifest.json", experimental_path=SP02_UNV, modal_set="Bravo (1)",
                           registration_basis=RegistrationBasisStatus.PHYSICAL, registration_hash=SP02_PHYSICAL)
        self.assertEqual(complete.missing, ())

    def test_a_source_is_matched_to_the_catalogue_by_file_name_only(self):
        result = context("SP-02", fe_path=r"D:\models\sp02_modal_v02.ODB", experimental_path=SP02_UNV)
        self.assertTrue(result.fe_source.catalogue_name_match)
        self.assertTrue(result.experimental_source.catalogue_name_match)
        other = context("SP-02", fe_path=r"D:\x\manifest.json", experimental_path=r"D:\x\SP13_a_polymax.unv")
        self.assertFalse(other.fe_source.catalogue_name_match)
        self.assertFalse(other.experimental_source.catalogue_name_match)

    def test_no_source_file_is_opened(self):
        with mock.patch("builtins.open", side_effect=AssertionError("a source was opened")), \
                mock.patch.object(Path, "read_bytes", side_effect=AssertionError("a source was read")):
            context("SP-02", fe_path=r"Z:\absent\SP02_Modal_V02.odb", experimental_path=r"Z:\absent\x.unv",
                    catalogue_view=catalog.load_catalogue())


class ModalSetTests(unittest.TestCase):
    def test_the_catalogue_status_of_the_selected_set(self):
        governed = context("SP-02", experimental_path=SP02_UNV, modal_set="Bravo (1)").modal_set
        self.assertEqual(governed.status, W.ModalSetStatus.GOVERNED)
        self.assertEqual(governed.catalogue_set.mode_count, 9)
        other = context("SP-02", experimental_path=SP02_UNV, modal_set="Bravo").modal_set
        self.assertEqual(other.status, W.ModalSetStatus.OTHER)

    def test_a_wrong_modal_set_is_never_merged_with_a_similar_one(self):
        for name in ("Bravo (2)", "bravo (1)", "Bravo (1) ", "Bravo(1)"):
            state = context("SP-02", experimental_path=SP02_UNV, modal_set=name).modal_set
            self.assertEqual(state.status, W.ModalSetStatus.NOT_IN_CATALOGUE, name)
            self.assertIsNone(state.catalogue_set)
        foreign = context("SP-02", modal_set="Processing_nice").modal_set  # a set of SP-01, not of SP-02
        self.assertEqual(foreign.status, W.ModalSetStatus.NOT_IN_CATALOGUE)

    def test_a_listed_set_in_a_file_that_is_not_a_catalogue_source_is_not_assigned_a_status(self):
        for path in (None, r"D:\x\renamed.unv"):
            state = context("SP-02", experimental_path=path, modal_set="Bravo (1)").modal_set
            self.assertEqual(state.status, W.ModalSetStatus.NOT_CHECKED, path)
            self.assertIsNone(state.catalogue_set)

    def test_no_modal_set_is_not_selected(self):
        for name in (None, "", "  "):
            self.assertEqual(context("SP-02", experimental_path=SP02_UNV, modal_set=name).modal_set.status,
                             W.ModalSetStatus.NOT_SELECTED)


class RegistrationTests(unittest.TestCase):
    def test_no_registration(self):
        state = context("SP-02").registration
        self.assertEqual((state.kind, state.registration_hash, state.catalogue_match, state.issues),
                         (W.RegistrationKind.NONE, None, None, ()))
        self.assertFalse(state.physical_confirmed_by_catalogue)
        self.assertIn("registration", context("SP-02").missing)

    def test_physical_registration_confirmed_by_the_catalogue(self):
        for specimen_id, digest in (("SP-02", SP02_PHYSICAL), ("SP-13", SP13_PHYSICAL)):
            state = context(specimen_id, registration_basis=RegistrationBasisStatus.PHYSICAL,
                            registration_hash=digest).registration
            self.assertEqual(state.kind, W.RegistrationKind.PHYSICAL)
            self.assertTrue(state.physical_confirmed_by_catalogue, specimen_id)

    def test_legacy_replay_is_kept_apart_and_never_upgraded(self):
        replay = context("SP-02", registration_basis=RegistrationBasisStatus.LEGACY_REPLAY,
                         registration_hash=SP02_LEGACY).registration
        self.assertEqual(replay.kind, W.RegistrationKind.LEGACY_REPLAY)
        self.assertEqual(replay.catalogue_match.kind, W.RegistrationKind.LEGACY_REPLAY)
        self.assertEqual(replay.issues, ())
        self.assertFalse(replay.physical_confirmed_by_catalogue)
        by_hash = context("SP-02", registration_hash=SP02_LEGACY).registration
        self.assertEqual(by_hash.kind, W.RegistrationKind.LEGACY_REPLAY)  # the catalogue's own kind
        claimed = context("SP-02", registration_basis=RegistrationBasisStatus.PHYSICAL,
                          registration_hash=SP02_LEGACY).registration
        self.assertIn("records this registration as LEGACY_REPLAY, not PHYSICAL", claimed.issues[0])
        self.assertFalse(claimed.physical_confirmed_by_catalogue)  # a legacy replay is never physical
        downgraded = context("SP-02", registration_basis=RegistrationBasisStatus.LEGACY_REPLAY,
                             registration_hash=SP02_PHYSICAL).registration
        self.assertEqual(downgraded.kind, W.RegistrationKind.LEGACY_REPLAY)
        self.assertTrue(downgraded.issues)

    def test_incomplete_and_unrecorded_registrations(self):
        incomplete = context("SP-01", registration_basis=RegistrationBasisStatus.INCOMPLETE).registration
        self.assertEqual((incomplete.kind, incomplete.issues), (W.RegistrationKind.INCOMPLETE, ()))
        no_hash = context("SP-02", registration_basis=RegistrationBasisStatus.PHYSICAL).registration
        self.assertFalse(no_hash.physical_confirmed_by_catalogue)
        self.assertIn("without a registration hash", no_hash.issues[0])
        other_specimen = context("SP-01", registration_basis=RegistrationBasisStatus.PHYSICAL,
                                 registration_hash=SP02_PHYSICAL).registration
        self.assertIsNone(other_specimen.catalogue_match)
        self.assertFalse(other_specimen.physical_confirmed_by_catalogue)
        unknown = context("SP-02", registration_hash="0" * 64).registration
        self.assertEqual(unknown.kind, W.RegistrationKind.UNKNOWN)

    def test_a_malformed_registration_is_refused(self):
        with self.assertRaises(W.WorkspaceContextError):
            context("SP-02", registration_basis="PHYSICAL")
        with self.assertRaises(W.WorkspaceContextError):
            context("SP-02", registration_hash="  ")


class ResultTests(unittest.TestCase):
    def test_only_a_successful_comparison_carries_pairs_and_mac(self):
        self.assertEqual(context("SP-02").result, W.ResultState(AnalysisState.NO_DATA))
        success = W.ResultState(AnalysisState.SUCCESS, pair_count=6, mac_shown=True)
        self.assertEqual(context("SP-02", result=success).result.pair_count, 6)
        self.assertIsNone(W.ResultState(AnalysisState.SUCCESS).pair_count)  # unknown stays unknown
        for state in AnalysisState:
            if state is AnalysisState.SUCCESS:
                continue
            W.ResultState(state, pair_count=0)
            with self.assertRaises(W.WorkspaceContextError, msg=state):
                W.ResultState(state, mac_shown=True)  # e.g. no MAC for a FREQUENCY_ONLY diagnostic
            with self.assertRaises(W.WorkspaceContextError, msg=state):
                W.ResultState(state, pair_count=1)
        for count in (-1, 1.0, True, "6"):
            with self.assertRaises(W.WorkspaceContextError):
                W.ResultState(AnalysisState.SUCCESS, pair_count=count)
        with self.assertRaises(W.WorkspaceContextError):
            W.ResultState("success")
        with self.assertRaises(W.WorkspaceContextError):
            context("SP-02", result={"state": "success"})


class ScientificBlockTests(unittest.TestCase):
    def best_case(self, specimen_id="SP-02", digest=SP02_PHYSICAL):
        return context(specimen_id, fe_path=r"D:\x\SP02_Modal_V02.odb", experimental_path=SP02_UNV,
                       modal_set="Bravo (1)", registration_basis=RegistrationBasisStatus.PHYSICAL,
                       registration_hash=digest,
                       result=W.ResultState(AnalysisState.SUCCESS, pair_count=6, mac_shown=True))

    def test_production_auto_id_stays_not_authorised_in_every_state(self):
        from services.guarded_execution import PRODUCTION_AUTHORITY

        states = [self.best_case(), self.best_case("SP-13", SP13_PHYSICAL), context("SP-99"), context(None)]
        states += [context(sid) for sid in catalog.load_catalogue().ids]
        for state in states:
            status = state.production_auto_id
            self.assertEqual((status.status, status.blocked), ("NOT_AUTHORISED", True))
            self.assertEqual(status.reason, PRODUCTION_AUTHORITY.unavailable_reason)

    def test_the_status_is_read_from_the_authority_not_stored_in_the_context(self):
        field_names = {field.name for field in dataclasses.fields(W.WorkspaceContext)}
        self.assertFalse({name for name in field_names if "auto_id" in name or "author" in name})
        state = self.best_case()
        with self.assertRaises(TypeError):
            dataclasses.replace(state, production_auto_id=W.ProductionAutoIdStatus("AUTHORISED", False, ""))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            state.result = W.ResultState()
        available = mock.Mock(available=True, unavailable_reason="")
        with mock.patch("services.guarded_execution.PRODUCTION_AUTHORITY", available):
            status = state.production_auto_id  # even an available authority authorises nothing here
        self.assertEqual((status.status, status.blocked), ("NOT_AUTHORISED", True))
        self.assertIn("not an execution authorisation", status.reason)

    def test_the_catalogue_auto_id_statuses_are_kept_verbatim(self):
        self.assertEqual(self.best_case().catalogue_auto_id_status, ("NEEDS_GOVERNANCE",))
        self.assertEqual(context("SP-13").catalogue_auto_id_status, ("OBSERVATION_INSUFFICIENT", "NEEDS_GOVERNANCE"))


class HeadlessTests(unittest.TestCase):
    def test_the_context_imports_no_tkinter(self):
        code = ("import sys; sys.path.insert(0, 'src'); from services import workspace_context as W; "
                "W.build_workspace_context('SP-02', modal_set='Bravo (1)').production_auto_id; "
                "loaded = sorted(m for m in sys.modules if m in ('tkinter', '_tkinter') or m.startswith('tkinter.')); "
                "print(','.join(loaded))")
        run = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip(), "")
        self.assertNotIn("tkinter", (ROOT / "src" / "services" / "workspace_context.py").read_text(encoding="utf-8"))

    def test_the_context_is_immutable(self):
        state = context("SP-02", experimental_path=SP02_UNV, modal_set="Bravo (1)")
        for target, name in ((state, "specimen"), (state.specimen, "family_id"), (state.modal_set, "status"),
                             (state.registration, "kind"), (state.fe_source, "path")):
            with self.assertRaises(dataclasses.FrozenInstanceError):
                setattr(target, name, None)
        self.assertIsInstance(state.specimen.modal_sets, tuple)
        self.assertIsInstance(state.specimen.registrations, tuple)


if __name__ == "__main__":
    unittest.main()
