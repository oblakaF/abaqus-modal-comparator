"""SP02-SP13-LEGACY-REGISTRATION-SUSPENSION-01 — the two affected v1 physical registrations are refused.

The accepted SP-02 and SP-13 physical registrations (PSV coordinate normalisation defect; corrected registration pending
acceptance) are suspended by their exact frozen identity, the sealed registration hash. Covered here:

- the identities: exactly the two hashes the fixture manifest pins and the frozen records seal; the frozen records, the
  legacy registrations of the same specimens and every other registration are not suspended;
- both archived binding routes refuse them (``bind_accepted_reference`` with ``match_accepted_files`` and
  ``check_archived_sensitivity_evidence``; ``bind_registration_by_fe_geometry``), with the reason, on the repository's
  own records (no data store) and on the synthetic world (G2c / G2d-1);
- an unrelated registration is bound as before;
- nothing replaces a suspended registration: the legacy worker runs no comparison with another registration, the
  NEW_GUI makes no pair and no MAC;
- the frequency diagnostic and the loaded mode shapes stay available;
- historical reproduction: the accepted strict freezes are still read from the repository records.

Synthetic data only; no data store, no Abaqus.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.experiment_fixture import load_experiment_fixture_manifest  # noqa: E402
from reviewed_core import GeometryOrientationAmbiguousError  # noqa: E402
from services import archived_sensitivity_evidence as ev  # noqa: E402
from services import new_odb_comparison as new  # noqa: E402
from services.experiment_fixture_regression import load_fixture_registration  # noqa: E402
from test_g2c_archived_sensitivity_evidence import EXP_HZ, World  # noqa: E402
from test_g2d1_governed_registration import experimental_dataset, fe_dataset  # noqa: E402
from test_new_gui5_registration import experimental_preview, fe_preview  # noqa: E402
from test_new_odb_comparison import NEW_HZ, ambiguity, new_odb_dataset  # noqa: E402

SUSPENDED = {"SP02": ("SP02/bravo-1-physical", "9b63f6c891331ba55a6ee2797f142bf0b75117d9bffbf3ab312ee08a418e882c"),
             "SP13": ("SP13/best-physical", "2eeeaa8698851baf33c640a5e741a91a67c6629b436700a920ba9333061cd823")}
LEGACY = ("SP02/bravo-1", "SP13/best")  # the legacy registrations of the same specimens: not suspended
REASON = "PSV coordinate normalisation defect; corrected registration pending acceptance."


def real_fixtures():
    return load_experiment_fixture_manifest(ROOT / ev.FIXTURE_MANIFEST)


class IdentityTests(unittest.TestCase):
    """The repository's own records; no data store."""

    def test_exactly_the_two_frozen_identities_are_suspended(self):
        self.assertEqual(set(ev.SUSPENDED_REGISTRATIONS), {digest for _, digest in SUSPENDED.values()})
        fixtures = real_fixtures()
        for specimen, (fixture_id, digest) in SUSPENDED.items():
            with self.subTest(specimen):
                fixture = fixtures.fixture(fixture_id)
                self.assertEqual(fixture.registration.registration_hash, digest)  # the manifest's pin
                sealed = load_fixture_registration(fixture, ROOT)  # the frozen record, unchanged and sealed
                self.assertEqual(sealed.registration_hash, digest)
                suspension = ev.registration_suspension(digest)
                self.assertEqual((suspension.specimen, suspension.fixture_id, suspension.registration_file),
                                 (specimen, fixture_id, fixture.registration.path))
                self.assertEqual(suspension.reason, REASON)
                self.assertIn(REASON, suspension.message())
                self.assertTrue(suspension.message().startswith(ev.SUSPENDED_MARK))
                with self.assertRaises(ev.RegistrationSuspended) as caught:
                    ev.require_registration_not_suspended(digest)
                self.assertEqual(caught.exception.specimen, specimen)

    def test_other_registrations_are_not_suspended(self):
        fixtures = real_fixtures()
        for fixture_id in LEGACY:
            digest = fixtures.fixture(fixture_id).registration.registration_hash
            self.assertIsNone(ev.registration_suspension(digest))
            ev.require_registration_not_suspended(digest)
        for digest in ("0" * 64, "", None, SUSPENDED["SP02"][1][:-1], SUSPENDED["SP02"][1].upper()):
            self.assertIsNone(ev.registration_suspension(digest))  # the exact identity only

    def test_the_accepted_reference_route_refuses_the_real_identities(self):
        fixtures = real_fixtures()
        for specimen, (fixture_id, _) in SUSPENDED.items():
            with self.subTest(specimen):
                fixture = fixtures.fixture(fixture_id)
                odb = {"sha256": fixture.fe.odb_reference.sha256, "size": fixture.fe.odb_reference.size_bytes}
                source = {"sha256": fixture.experimental_source.sha256, "size": fixture.experimental_source.size_bytes}
                loaders = (mock.patch.object(ev, "load_fixture_registration", side_effect=AssertionError("loaded")),
                           mock.patch.object(ev, "verify_fixture_dataset", side_effect=AssertionError("verified")))
                with mock.patch.object(ev, "fresh_content_identity", side_effect=[odb, source, odb, source]), \
                        loaders[0], loaders[1]:
                    with self.assertRaises(ev.RegistrationSuspended) as caught:
                        ev.match_accepted_files(Path("accepted.odb"), Path("accepted.unv"))
                    self.assertIn(REASON, str(caught.exception))
                    with self.assertRaises(ev.RegistrationSuspended):
                        ev.bind_accepted_reference(Path("accepted.odb"), Path("accepted.unv"), object(), object())

    def test_the_fe_geometry_route_refuses_the_real_identities(self):
        fixtures = real_fixtures()
        for specimen, (fixture_id, digest) in SUSPENDED.items():
            with self.subTest(specimen):
                fixture = fixtures.fixture(fixture_id)
                source = {"sha256": fixture.experimental_source.sha256, "size": fixture.experimental_source.size_bytes}
                accepted = fixture.fe.geometry_identity
                geometry = {"schema_version": accepted.schema_version, "sha256": accepted.sha256,
                            "node_count": accepted.node_count}
                with mock.patch.object(new, "fresh_content_identity", return_value=source), \
                        mock.patch.object(new, "modal_dataset_geometry_identity", return_value=geometry), \
                        mock.patch.object(new, "load_fixture_registration", side_effect=AssertionError("loaded")):
                    with self.assertRaises(new.GeometryReuseSuspended) as caught:
                        new.bind_registration_by_fe_geometry(Path("accepted.unv"), object(), object())
                error = caught.exception
                self.assertIsInstance(error, new.GeometryReuseRefusal)  # the callers' frequency-only path
                self.assertIsInstance(error, ev.RegistrationSuspended)
                self.assertEqual((error.specimen, error.suspension.registration_hash), (specimen, digest))
                self.assertIn(REASON, str(error))

    def test_historical_evidence_is_still_read(self):
        for specimen, (fixture_id, digest) in SUSPENDED.items():
            with self.subTest(specimen):
                freeze = ev.accepted_physical_freeze(fixture_id, repo_root=ROOT)
                self.assertEqual(freeze.registration.registration_hash, digest)
                self.assertEqual(freeze.freeze["status"], "FROZEN")
                self.assertEqual(len(freeze.freeze["strict_pairs"]), {"SP02": 3, "SP13": 2}[specimen])


class _World(unittest.TestCase):
    """The synthetic world with its SP-02 registration suspended (its SP-13 registration is unrelated)."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.world = World(directory.name)
        self.odb, self.unv = self.world.files["SP02"]
        self.fe = fe_dataset(self.odb)
        self.experimental = experimental_dataset(self.unv, self.fe)
        self.registration = self.world.registrations["SP02"]
        self.new_odb = Path(directory.name) / "data" / "SP02_new_model.odb"
        self.new_odb.write_bytes(b"another FE result with the accepted mesh " * 4000)
        self.new = new_odb_dataset(self.new_odb, self.fe)
        suspension = ev.RegistrationSuspension("SP02", "SP02/bravo-1-physical", "synthetic",
                                               self.registration.registration_hash)
        for patch in (self.world.pins(), mock.patch.object(ev, "REPO_ROOT", self.world.root),
                      mock.patch.object(ev, "SUSPENDED_REGISTRATIONS", {suspension.registration_hash: suspension})):
            patch.__enter__()
            self.addCleanup(patch.__exit__, None, None, None)

    def other(self):
        """The unrelated (SP-13) specimen of the world: files, FE result and modal set."""
        odb, unv = self.world.files["SP13"]
        fe = fe_dataset(odb)
        return odb, unv, fe, experimental_dataset(unv, fe)


class RouteTests(_World):
    def test_the_fe_geometry_route_refuses_and_an_unrelated_registration_is_bound(self):
        with self.assertRaises(new.GeometryReuseSuspended) as caught:
            new.bind_registration_by_fe_geometry(self.unv, self.new, self.experimental, repo_root=self.world.root)
        self.assertIn(REASON, str(caught.exception))
        _, unv, fe, experimental = self.other()
        bound = new.bind_registration_by_fe_geometry(unv, fe, experimental, repo_root=self.world.root)
        self.assertEqual(bound.registration.registration_hash, self.world.registrations["SP13"].registration_hash)

    def test_a_record_that_is_suspended_only_as_loaded_is_refused_too(self):
        real = new.load_fixture_registration
        with mock.patch.object(ev, "SUSPENDED_REGISTRATIONS", {}), \
                mock.patch.object(new, "load_fixture_registration") as load:
            load.side_effect = lambda *args: (real(*args), self.suspend())[0]
            with self.assertRaises(new.GeometryReuseSuspended):
                new.bind_registration_by_fe_geometry(self.unv, self.new, self.experimental, repo_root=self.world.root)

    def suspend(self):
        ev.SUSPENDED_REGISTRATIONS[self.registration.registration_hash] = ev.RegistrationSuspension(
            "SP02", "SP02/bravo-1-physical", "synthetic", self.registration.registration_hash)

    def test_the_accepted_reference_route_refuses_and_an_unrelated_registration_is_bound(self):
        with self.assertRaises(ev.RegistrationSuspended) as caught:
            ev.bind_accepted_reference(self.odb, self.unv, self.fe, self.experimental, repo_root=self.world.root)
        self.assertEqual(caught.exception.specimen, "SP02")
        with self.assertRaises(ev.RegistrationSuspended):
            ev.match_accepted_files(self.odb, self.unv, repo_root=self.world.root)  # the option is never offered
        odb, unv, fe, experimental = self.other()
        bound = ev.bind_accepted_reference(odb, unv, fe, experimental, repo_root=self.world.root)
        self.assertEqual(bound.registration.registration_hash, self.world.registrations["SP13"].registration_hash)

    def test_no_verified_evidence_governed_mac_or_sensitivity_is_shown(self):
        from modal_core import compare_modal_datasets

        # the engine itself is unchanged (historical reproduction); the evidence of the comparison is refused
        result = compare_modal_datasets(self.fe, self.experimental, frozen_registration=self.registration)
        result.metadata["comparison_inputs"] = ev.comparison_input_record(self.odb, self.unv, "set-a")
        evidence = ev.check_archived_sensitivity_evidence(result, repo_root=self.world.root)
        self.assertEqual((evidence.status, evidence.specimen), (ev.NOT_APPLICABLE, "SP02"))
        self.assertFalse(evidence.shows_sensitivities)
        self.assertEqual(evidence.rows, ())  # no governed MAC, no strict pair, no S_E / S_G12
        self.assertIn(ev.SUSPENDED_MARK, evidence.reasons[0])
        self.assertIn(REASON, evidence.reasons[0])


class LegacyWorkerTests(_World):
    """LEGACY_GUI: the analysis worker (``runtime_hardening``) with the suspended registration."""

    def run_worker(self, abaqus, governed: bool):
        import main
        import runtime_hardening

        calls, failures = [], []

        def compare(*_args, **kwargs):
            calls.append(kwargs)
            raise ambiguity()  # the automatic registration cannot choose an orientation

        class Root:
            @staticmethod
            def after(_delay, callback):
                callback()

        application = SimpleNamespace(
            root=Root(), _analysis_cancel_event=threading.Event(), _owned_analysis_process=None,
            _set_analysis_stage=lambda *_: None, _failed=failures.append, _complete=failures.append,
            _orientation_ambiguous=failures.append, _governed_registration_requested=governed,
            _active_orientation_selection=None, _write_summary=lambda *_: None)
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(runtime_hardening, "bind_registration_by_fe_geometry", functools.partial(
                    new.bind_registration_by_fe_geometry, repo_root=self.world.root)), \
                mock.patch.object(runtime_hardening, "bind_accepted_reference", functools.partial(
                    ev.bind_accepted_reference, repo_root=self.world.root)), \
                mock.patch.object(main.app, "load_or_extract_odb", return_value=abaqus), \
                mock.patch.object(runtime_hardening, "load_universal_modal_file", return_value=self.experimental), \
                mock.patch.object(main.app, "compare_modal_datasets", side_effect=compare), \
                mock.patch.object(main.app, "render_mac_matrix", side_effect=AssertionError("no MAC plot")):
            workspace = Path(directory)
            main.app.ModalComparatorApp._worker(application, abaqus.source_path, self.unv, workspace, 7, 13, "abaqus",
                                                1.0, "set-a")
            written = {path.name: json.loads(path.read_text(encoding="utf-8")) for path in workspace.rglob("*.json")}
        (failure,) = failures
        return calls, failure, written

    def assertFrequenciesOnly(self, diagnostic, written, fe_hz) -> None:
        self.assertEqual(diagnostic.status, new.FREQUENCY_ONLY)
        self.assertIn(ev.SUSPENDED_MARK, diagnostic.reason)
        self.assertIn(REASON, diagnostic.reason)
        self.assertEqual(dict(diagnostic.experimental_modes), EXP_HZ)  # every experimental frequency is kept
        self.assertEqual(dict(diagnostic.fe_modes) | {n: f for n, f, _ in diagnostic.rigid_fe_modes}, fe_hz)
        record = written["frequency_only_diagnostic.json"]
        self.assertEqual((record["mac"], record["status"]), ("NOT_COMPUTED", new.FREQUENCY_ONLY))
        self.assertTrue(record["mode_pairs"].startswith("NONE"))

    def test_the_geometry_reuse_is_refused_and_the_frequencies_are_kept(self):
        calls, failure, written = self.run_worker(self.new, governed=False)
        self.assertEqual([set(kwargs) for kwargs in calls], [{"coordinate_scale_override"}])  # no frozen registration
        self.assertIsInstance(failure, GeometryOrientationAmbiguousError)
        self.assertFrequenciesOnly(failure.frequency_only_diagnostic, written, NEW_HZ)
        loaded = failure.loaded_modal_data  # the individual mode shapes of both files stay viewable
        self.assertIs(loaded.abaqus, self.new)
        self.assertIs(loaded.experimental, self.experimental)
        self.assertIs(loaded.frequency_diagnostic, failure.frequency_only_diagnostic)

    def test_the_governed_option_is_refused_without_any_other_registration(self):
        import runtime_hardening

        calls, failure, written = self.run_worker(self.fe, governed=True)
        self.assertEqual(calls, [])  # no comparison at all: neither the suspended nor an automatic registration
        self.assertIsInstance(failure, runtime_hardening.GovernedRegistrationRefused)
        self.assertIn(ev.SUSPENDED_MARK, str(failure))
        self.assertIn(REASON, str(failure))
        self.assertIn("not run with any other registration", str(failure))
        loaded = failure.loaded_modal_data
        self.assertIs(loaded.abaqus, self.fe)
        self.assertIs(loaded.experimental, self.experimental)
        self.assertNotEqual(loaded.registration, runtime_hardening.ESTABLISHED)
        self.assertFrequenciesOnly(loaded.frequency_diagnostic, written,
                                   {m.number: m.frequency_hz for m in self.fe.sorted_modes()})


class NewGuiTests(_World):
    """NEW_GUI: the registration check and the analysis models (no Qt)."""

    def previews(self, fe, unv, experimental):
        return fe_preview(Path(self.world.root) / "package" / "manifest.json", fe), experimental_preview(unv, [experimental])

    def test_the_check_says_suspended_and_shows_no_registration(self):
        from new_gui import registration_check_model as rm

        fe, experimental = self.previews(self.new, self.unv, self.experimental)
        outcome = rm.run_check(fe, experimental, 0, 4, threading.Event())
        self.assertEqual((outcome.view, outcome.error, outcome.cancelled, outcome.suspended), (None, "", False, True))
        self.assertIn(REASON, outcome.refusal)
        slot = rm.RegistrationSlot()
        token, _ = slot.start((fe, experimental, 0))
        self.assertTrue(slot.finish(rm.RegistrationOutcome(token, refusal=outcome.refusal, suspended=True)))
        self.assertEqual(slot.state, rm.REFUSED)  # never the verified state
        self.assertIn("PSV coordinate normalisation defect; corrected registration pending acceptance",
                      rm.SUSPENDED_NOTE)
        _, unv, other_fe, other_experimental = self.other()
        unrelated = rm.run_check(*self.previews(other_fe, unv, other_experimental), 0, 5, threading.Event())
        self.assertIsNotNone(unrelated.view)
        self.assertFalse(unrelated.suspended)
        refused = rm.run_check(*self.previews(new_odb_dataset(self.new_odb, self.fe, shift=0.5), self.unv,
                                              self.experimental), 0, 6, threading.Event())
        self.assertEqual((refused.suspended, refused.view), (False, None))  # an ordinary refusal is not a suspension

    def test_the_analysis_makes_no_pair_and_no_mac(self):
        from new_gui import analyze_model as am
        from new_gui import comparison_model as cm

        fe, experimental = self.previews(self.new, self.unv, self.experimental)
        inputs = SimpleNamespace(full_fe=fe, full_experimental=experimental)
        with mock.patch.object(cm, "run_compare", side_effect=AssertionError("compared")), \
                mock.patch.object(cm, "run_compare_confirmed", side_effect=AssertionError("compared")):
            compared, reason, outcome = am._verified(inputs, 0, threading.Event())
        self.assertIsNone(compared)  # analyse() then reports REGISTRATION_REQUIRED: frequencies only
        self.assertEqual(outcome, am.SUSPENDED)
        self.assertIn(REASON, reason)
        self.assertEqual(am.REGISTRATION_NOTES[am.SUSPENDED], am.rm.SUSPENDED_NOTE)
        self.assertNotEqual(am.REGISTRATION_NOTES[am.SUSPENDED], am.REGISTRATION_NOTES[am.REFUSED])


if __name__ == "__main__":
    unittest.main()
