"""NEW-GUI.5: the archived physical registration applicability check of the read FE and experimental data (no Qt).

``new_gui.registration_check_model`` calls the existing ``services.new_odb_comparison.bind_registration_by_fe_geometry``
with the file the importer read (``ExperimentalPreview.source_path``), ``FePreview.dataset`` and the chosen set's
dataset, and only words its result. On the project's synthetic fixture world (G2c / G2d-1): the exact accepted source,
modal set and FE geometry are verified; another FE geometry, changed experimental bytes or another modal set are
refused with the service's reason. Nothing is chosen by itself, applied, paired, compared by MAC, imported again or
written, and no process is started. Cancellation, stale outcomes and one heavy check at a time (shared with the
frequency diagnostic) are covered.
"""

from __future__ import annotations

import contextlib
import hashlib
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from modal_core import ModalDataset  # noqa: E402
from new_gui import diagnostic_model as dm  # noqa: E402
from new_gui import registration_check_model as rm  # noqa: E402
from services import archived_sensitivity_evidence as ev  # noqa: E402
from services import local_experimental_preview as xp  # noqa: E402
from services import local_fe_preview as fp  # noqa: E402
from services import new_odb_comparison as service  # noqa: E402
from test_g2c_archived_sensitivity_evidence import World  # noqa: E402
from test_g2d1_governed_registration import experimental_dataset, fe_dataset  # noqa: E402
from test_new_odb_comparison import new_odb_dataset  # noqa: E402


def fingerprint(folder: Path) -> dict:
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.rglob("*")) if p.is_file()}


def fe_preview(path: Path, dataset: ModalDataset) -> fp.FePreview:
    """An FE preview as Inspect file returns it, holding ``dataset`` (the World's FE result)."""
    modes = tuple(fp.PreviewMode(m.number, m.frequency_hz, "manifest", len(m.node_ids)) for m in dataset.sorted_modes())
    return fp.FePreview(path, str(path), "Frequency", modes, (), dataset=dataset)


def other_set(unv: Path, fe: ModalDataset) -> ModalDataset:
    """The same records under another modal-set key (not the accepted set)."""
    dataset = experimental_dataset(unv, fe)
    dataset.metadata.update(modal_set_key="set-b", available_modal_sets=[{"key": "set-a"}, {"key": "set-b"}])
    return dataset


def experimental_preview(source: Path, datasets, selected: Path = None) -> xp.ExperimentalPreview:
    """A dataset-55 preview of ``source`` with one PreviewSet per dataset, as the importer's sets."""
    sets = tuple(xp._set_from(d, d.metadata.get("modal_set_key", ""), d.metadata.get("modal_set_key", ""),
                              "synthetic") for d in datasets)
    return xp.ExperimentalPreview(selected or source, source, xp.DATASET_55, (15, 55), 6, sets, (), ())


class WorldCase(unittest.TestCase):
    """The G2c / G2d-1 synthetic world as the repository the service reads (pinned, below a temporary root)."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.world = World(directory.name)
        self.odb, self.unv = self.world.files["SP02"]
        self.fe = fe_dataset(self.odb)
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(self.world.pins())
        stack.enter_context(mock.patch.object(ev, "REPO_ROOT", self.world.root))
        stack.enter_context(mock.patch("subprocess.Popen", side_effect=AssertionError("no process for a check")))
        self.before = fingerprint(self.world.root)

    def previews(self, fe=None, source=None, datasets=None):
        source = source or self.unv
        return (fe_preview(self.odb, fe or self.fe),
                experimental_preview(source, datasets or [experimental_dataset(source, self.fe),
                                                          other_set(source, self.fe)]))

    def run_model(self, fe, experimental, set_index=0):
        outcome = rm.run_check(fe, experimental, set_index, 9, threading.Event())
        self.assertEqual((outcome.token, outcome.cancelled, outcome.error), (9, False, ""))
        return outcome

    def tearDown(self) -> None:
        self.assertEqual(fingerprint(self.world.root), self.before)  # no record, registration or file written


class ServiceTests(WorldCase):
    def test_the_exact_accepted_source_set_and_geometry_are_verified_by_the_service(self):
        fe, experimental = self.previews()
        with mock.patch.object(service, "bind_registration_by_fe_geometry",
                               wraps=service.bind_registration_by_fe_geometry) as spy:
            outcome = self.run_model(fe, experimental)
        path, abaqus, measured = spy.call_args.args
        self.assertEqual(path, self.unv)  # the file the importer read
        self.assertIs(abaqus, fe.dataset)  # the data already read, not a new import
        self.assertIs(measured, experimental.sets[0].dataset)
        bound = service.bind_registration_by_fe_geometry(self.unv, fe.dataset, experimental.sets[0].dataset)
        provenance = bound.provenance()
        view = outcome.view
        self.assertEqual((view.specimen, view.fixture_id), ("SP02", "SP02/bravo-1-physical"))
        self.assertEqual(view.archived_modal_set, "set-a")
        self.assertEqual(view.selected_set, dm.set_title(experimental, 0))
        self.assertEqual(view.registration, self.world.registrations["SP02"].registration_hash)
        self.assertEqual(view.registration_file, provenance["registration_file"])
        self.assertIn(provenance["fe_geometry_sha256"], view.fe_geometry)
        self.assertIn(provenance["experimental_sha256"], view.experimental_source)
        self.assertTrue(view.experimental_source.startswith(str(self.unv)))
        self.assertEqual(view.checks, tuple(provenance["checks"]))
        self.assertEqual(len(view.checks), 4)
        self.assertEqual(view.limits, service.REUSE_LIMITS)
        self.assertEqual(view.warning, "Verified archived reference for these selected data only. Registration not "
                                       "applied. Modal identity and MAC not established.")

    def test_an_lms_project_is_checked_with_the_companion_the_importer_read(self):
        fe, _ = self.previews()
        lms = self.unv.with_name("project.lms")
        experimental = experimental_preview(self.unv, [experimental_dataset(self.unv, self.fe)], selected=lms)
        with mock.patch.object(service, "bind_registration_by_fe_geometry",
                               wraps=service.bind_registration_by_fe_geometry) as spy:
            self.assertIsNotNone(self.run_model(fe, experimental).view)
        self.assertEqual(spy.call_args.args[0], self.unv)

    def test_another_fe_geometry_is_refused(self):
        for label, dataset in (("moved", new_odb_dataset(self.odb, self.fe, shift=0.5)),
                               ("rescaled", new_odb_dataset(self.odb, self.fe, scale=1.001))):
            with self.subTest(label):
                outcome = self.run_model(*self.previews(fe=dataset))
                self.assertIsNone(outcome.view)
                self.assertIn("is not the accepted SP02 FE geometry", outcome.refusal)

    def test_changed_experimental_bytes_are_refused(self):
        edited = self.unv.with_name("SP02_edited.unv")
        edited.write_bytes(self.unv.read_bytes() + b" edited")
        self.before = fingerprint(self.world.root)
        outcome = self.run_model(*self.previews(source=edited))
        self.assertIsNone(outcome.view)
        self.assertIn("is not the PolyMAX source of an accepted physical registration", outcome.refusal)

    def test_another_modal_set_is_refused_and_sets_are_never_mixed(self):
        fe, experimental = self.previews()
        refused = self.run_model(fe, experimental, 1)  # the "set-b" set of the same file
        self.assertIsNone(refused.view)
        self.assertIn("modal_set", refused.refusal)
        self.assertIsNotNone(self.run_model(fe, experimental, 0).view)  # the accepted set alone is verified

    def test_nothing_applied_compared_paired_or_read_again(self):
        fe, experimental = self.previews()
        import abaqus_bridge
        import modal_core
        import reviewed_core
        import universal_reader
        from services import specimen_catalog_view

        forbidden = [(modal_core, "modal_assurance_criterion"), (modal_core, "compare_modal_datasets"),
                     (reviewed_core, "compare_modal_datasets"), (reviewed_core, "geometry_alignment_candidates"),
                     (reviewed_core, "geometry_from_frozen_registration"),
                     (service, "frequency_only_diagnostic"), (ev, "check_archived_sensitivity_evidence"),
                     (specimen_catalog_view, "load_catalogue"), (abaqus_bridge, "load_extracted_odb"),
                     (universal_reader, "load_universal_modal_file"),
                     (universal_reader, "discover_experimental_modal_sets")]
        for module, name in forbidden:
            guard = mock.patch.object(module, name, side_effect=AssertionError(f"{name} called"))
            guard.start()
            self.addCleanup(guard.stop)
        outcome = self.run_model(fe, experimental)
        self.assertIsNotNone(outcome.view)
        self.assertNotIn("MAC", " ".join(outcome.view.checks))  # the checks are about identity, not modal agreement


class RequestTests(WorldCase):
    def test_no_set_or_unread_side_means_no_check(self):
        fe, experimental = self.previews()
        self.assertEqual(dm.unavailable(fe, experimental, None), (dm.NEED_SET,))
        self.assertEqual(dm.unavailable(None, experimental, 0), (dm.NEED_FE,))
        self.assertFalse(rm.set_is_provisional(experimental, 0))
        self.assertFalse(rm.set_is_provisional(experimental, None))

    def test_a_set_cancel_event_never_calls_the_service(self):
        event = threading.Event()
        event.set()
        with mock.patch.object(rm, "check", side_effect=AssertionError("not called")):
            outcome = rm.run_check(*self.previews(), 0, 3, event)
        self.assertEqual((outcome.cancelled, outcome.view, outcome.refusal, outcome.error), (True, None, "", ""))

    def test_a_cancel_during_the_service_discards_its_result(self):
        fe, experimental = self.previews()
        event = threading.Event()
        real = rm.check

        def cancelled_while_checking(*args):
            result = real(*args)
            event.set()  # the set was changed while the service ran
            return result

        with mock.patch.object(rm, "check", cancelled_while_checking):
            outcome = rm.run_check(fe, experimental, 0, 3, event)
        self.assertTrue(outcome.cancelled)
        self.assertIsNone(outcome.view)

    def test_the_services_cancellation_and_errors(self):
        fe, experimental = self.previews()
        with mock.patch.object(rm, "check", side_effect=ev.SensitivityCheckCancelled("stopped")):
            self.assertTrue(rm.run_check(fe, experimental, 0, 3, threading.Event()).cancelled)
        with mock.patch.object(rm, "check", side_effect=OSError("disk")):
            outcome = rm.run_check(fe, experimental, 0, 3, threading.Event())
        self.assertEqual(outcome.error, "The check could not be completed (OSError: disk).")
        self.assertEqual(outcome.refusal, "")

    def test_one_heavy_check_at_a_time_shared_with_the_frequency_diagnostic(self):
        fe, experimental = self.previews()
        outcomes, calls = {}, []
        real = rm.check

        def counted(*args):
            calls.append(args)
            return real(*args)

        waiting = threading.Event()
        with mock.patch.object(rm, "check", counted):
            with dm._SERVICE:  # a frequency diagnostic is running
                worker = threading.Thread(target=lambda: outcomes.setdefault(1, rm.run_check(
                    fe, experimental, 0, 1, waiting)))
                worker.start()
                worker.join(0.3)
                self.assertTrue(worker.is_alive())  # the check waits for it
                self.assertEqual(calls, [])
                waiting.set()  # cancelled while it waits
            worker.join(30)
        self.assertEqual(calls, [])  # a request cancelled while it waits never runs the service
        self.assertTrue(outcomes[1].cancelled)
        self.assertIs(rm.SERVICE_LOCK, dm._SERVICE)

    def test_only_the_current_request_is_shown(self):
        slot = rm.RegistrationSlot()
        token, event = slot.start(("fe", "exp", 0))
        stale = rm.RegistrationOutcome(token, refusal="old")
        slot.reset()  # another set, a replaced file, Inspect again or a closed window
        self.assertTrue(event.is_set())
        self.assertFalse(slot.finish(stale))
        self.assertEqual((slot.state, slot.outcome), (rm.IDLE, None))
        token, _ = slot.start(("fe", "exp", 1))
        self.assertFalse(slot.finish(stale))
        self.assertTrue(slot.finish(rm.RegistrationOutcome(token, refusal="not the accepted source")))
        self.assertEqual(slot.state, rm.REFUSED)
        self.assertFalse(slot.finish(rm.RegistrationOutcome(token, refusal="twice")))
        token, _ = slot.start(("fe", "exp", 1))
        self.assertTrue(slot.finish(rm.RegistrationOutcome(token, error="disk")))
        self.assertEqual(slot.state, rm.FAILED)
        token, _ = slot.start(("fe", "exp", 1))
        self.assertTrue(slot.finish(rm.RegistrationOutcome(token, cancelled=True)))
        self.assertEqual(slot.state, rm.IDLE)


class StartTests(unittest.TestCase):
    def test_importing_the_model_loads_no_service_and_writes_nothing(self):
        import os
        import subprocess

        with tempfile.TemporaryDirectory() as folder:
            code = ("import sys; sys.path.insert(0, sys.argv[1]); import new_gui.registration_check_model; "
                    "bad = sorted(m for m in sys.modules if m in ('main', 'tkinter', 'matplotlib', "
                    "'services.new_odb_comparison', 'services.archived_sensitivity_evidence', 'fast_cache')); "
                    "print(','.join(bad))")
            done = subprocess.run([sys.executable, "-c", code, str(ROOT / "src")], capture_output=True, text=True,
                                  timeout=120, env={**os.environ, "LOCALAPPDATA": folder})
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(done.stdout.strip(), "")
            self.assertEqual(list(Path(folder).rglob("*")), [])


if __name__ == "__main__":
    unittest.main()
