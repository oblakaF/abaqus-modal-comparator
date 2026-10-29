"""NEW-GUI.4: the frequency diagnostic of the read FE and experimental data (no Qt).

``new_gui.diagnostic_model`` calls the existing ``services.new_odb_comparison.frequency_only_diagnostic`` with the
data Inspect file already read (``FePreview.dataset``, ``ExperimentalPreview.sets[i].dataset``) and only words its
result: FREQUENCY_ONLY_DIAGNOSTIC, every experimental record (record 1 included) with the nearest and next elastic FE
frequencies and their signed differences, MAC NOT_COMPUTED, no mode pair, the FE rigid-body modes separated by the
comparator's shape criterion (never a frequency threshold), the out-of-range notes, PROVISIONAL for FRF peak records
(dataset 58) and the importer's classification and warnings for ambiguous records. Several dataset-55 sets are never
mixed. Nothing is read again, registered, paired, looked up in the research archive or written next to the inputs,
and no process is started. Synthetic files and an isolated LOCALAPPDATA.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from new_gui import diagnostic_model as dm  # noqa: E402
from new_gui import preview_model as pm  # noqa: E402
from new_gui import workspace_state as ws  # noqa: E402
import frf_unv_support as F  # noqa: E402
import synthetic_plate_support as S  # noqa: E402
from test_new_gui3_shapes import PLANE, geometry_4, mode_55_4  # noqa: E402
from test_universal_hardening import write_2414_unv  # noqa: E402

# FE modes by shape: rigid-body translation, a near-zero-frequency elastic (saddle) mode, a rigid-body rotation at
# 4.5 Hz, and two elastic modes. A frequency threshold would get modes 2 and 3 wrong; the shape criterion does not.
X = {n: x for _, n, x, _, _ in PLANE}
Y = {n: y for _, n, _, y, _ in PLANE}
SHAPES = {"translation": lambda n: 1.0, "rotation": lambda n: X[n] - 0.1,
          "saddle": lambda n: (X[n] - 0.1) * (Y[n] - 0.1) * 100.0, "bending": lambda n: (X[n] - 0.1) ** 2 * 100.0 - 0.6}
FE_MODES = [(1, 0.0011, "translation"), (2, 0.0012, "saddle"), (3, 4.5, "rotation"), (4, 101.25, "saddle"),
            (5, 133.5, "bending")]
RIGID_BY_SHAPE, ELASTIC_BY_SHAPE = (1, 3), (2, 4, 5)


def fingerprint(folder: Path) -> dict:
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.rglob("*")) if p.is_file()}


def write_fe_package(folder: Path, modes=FE_MODES) -> Path:
    """An extracted package (format 2) on the nine plane nodes, each mode with its own U3 shape."""
    folder.mkdir(parents=True, exist_ok=True)
    rows = ["instance,node_label,x,y,z"] + [f"{i},{n},{x},{y},{z}" for i, n, x, y, z in PLANE]
    (folder / "geometry.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    entries = []
    for number, frequency, shape in modes:
        name = f"mode_{number:04d}.csv"
        lines = ["instance,node_label,u1_real,u2_real,u3_real,u1_imag,u2_imag,u3_imag"]
        lines += [f"{i},{n},0,0,{SHAPES[shape](n):.12g},0,0,0" for i, n, *_ in PLANE]
        (folder / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
        entries.append({"mode": number, "frequency_hz": frequency, "file": name, "frame_index": number})
    numbers = [m[0] for m in modes]
    manifest = {"format_version": 2, "geometry_file": "geometry.csv", "step_name": "Frequency",
                "odb_path": "D:/synthetic/plate_model.odb", "start_mode": min(numbers), "end_mode": max(numbers),
                "modes": entries}
    path = folder / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


class _Folder(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="new_gui4_"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.inputs = self.folder / "inputs"
        self.inputs.mkdir()
        cache = self.folder / "cache"
        cache.mkdir()
        for patcher in (mock.patch.dict(os.environ, {"LOCALAPPDATA": str(cache)}),
                        mock.patch("subprocess.Popen", side_effect=AssertionError("no process for a diagnostic"))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def read(self, kind, path):
        outcome = pm.run_read(kind, path, 1, threading.Event())
        self.assertEqual(outcome.error, "")
        return outcome.preview

    def fe(self):
        return self.read(ws.FE, write_fe_package(self.inputs / "package"))

    def run_gui(self, fe, experimental, set_index=0):
        outcome = dm.run_diagnostic(fe, experimental, set_index, 5, threading.Event())
        self.assertEqual((outcome.token, outcome.error, outcome.cancelled), (5, "", False))
        return outcome


class ServiceParityTests(_Folder):
    def test_the_gui_shows_the_services_result_for_the_data_already_read(self):
        from services import new_odb_comparison as service

        fe = self.fe()
        experimental = self.read(ws.EXPERIMENTAL, S.write_experiment(self.inputs / "one.unv", S.E0, S.G0))
        chosen = experimental.sets[0]
        with mock.patch.object(service, "frequency_only_diagnostic",
                               wraps=service.frequency_only_diagnostic) as spy:
            outcome = self.run_gui(fe, experimental)
        spy.assert_called_once()
        abaqus, measured, reason = spy.call_args.args
        self.assertIs(abaqus, fe.dataset)  # the data already read, not a new import
        self.assertIs(measured, chosen.dataset)
        self.assertEqual(reason, dm.REASON)
        expected = service.frequency_only_diagnostic(fe.dataset, chosen.dataset, dm.REASON)
        self.assertEqual(outcome.diagnostic.to_dict(), expected.to_dict())
        view = outcome.view
        self.assertEqual(view.status, "FREQUENCY_ONLY_DIAGNOSTIC")
        self.assertEqual(view.statement, service.FREQUENCY_ONLY_STATEMENT)
        self.assertEqual(view.reason, dm.REASON)
        self.assertEqual(view.set_title, f"Modal set 1 of 1: {chosen.title}")
        self.assertEqual(view.experimental_source, expected.experimental_source)
        self.assertEqual((view.mac, view.mode_pairs), ("NOT_COMPUTED", "NONE (physical modal correspondence not "
                                                                       "verified)"))
        self.assertEqual(len(view.nearest_rows), len(expected.rows))
        for shown, row in zip(view.nearest_rows, expected.rows):
            with self.subTest(experimental_mode=row.experimental_mode):
                self.assertEqual(shown[1:10], (
                    str(row.experimental_mode), f"{row.experimental_hz:.4f}", str(row.nearest_fe_mode),
                    f"{row.nearest_fe_hz:.4f}", f"{row.nearest_difference_percent:+.2f}", str(row.next_fe_mode),
                    f"{row.next_fe_hz:.4f}", f"{row.next_difference_percent:+.2f}", "NOT_COMPUTED"))
                # the comparator's sign convention: (f_FE - f_exp) / f_exp * 100
                self.assertAlmostEqual(row.nearest_difference_percent,
                                       (row.nearest_fe_hz - row.experimental_hz) / row.experimental_hz * 100.0)
        self.assertEqual(view.fe_rows, tuple((str(n), f"{f:.4f}") for n, f in expected.fe_modes))
        self.assertEqual(view.experimental_rows,
                         tuple((str(i + 1), str(r.number), f"{r.frequency_hz:.4f}", r.label)
                               for i, r in enumerate(chosen.records)))

    def test_rigid_body_fe_modes_are_separated_by_shape_not_by_frequency(self):
        from services.new_odb_comparison import RIGID_BODY_CRITERION

        view = self.run_gui(self.fe(), self.read(ws.EXPERIMENTAL, S.write_experiment(
            self.inputs / "one.unv", S.E0, S.G0))).view
        self.assertEqual(tuple(int(row[0]) for row in view.rigid_rows), RIGID_BY_SHAPE)  # 4.5 Hz rotation included
        self.assertEqual(tuple(int(row[0]) for row in view.fe_rows), ELASTIC_BY_SHAPE)  # 0.0012 Hz saddle included
        self.assertTrue(all(float(row[2]) <= 0.02 for row in view.rigid_rows))  # the diagnostic residual is shown
        self.assertIn("no frequency threshold", view.rigid_criterion)
        self.assertEqual(view.rigid_criterion, RIGID_BODY_CRITERION)
        candidates = {row[3] for row in view.nearest_rows} | {row[6] for row in view.nearest_rows}
        self.assertFalse(candidates & {"1", "3"})  # rigid-body modes are never nearest-frequency candidates

    def test_frequencies_outside_the_extracted_fe_range_are_flagged(self):
        view = self.run_gui(self.fe(), self.read(ws.EXPERIMENTAL, S.write_experiment(
            self.inputs / "one.unv", S.E0, S.G0))).view
        above = [row for row in view.nearest_rows if float(row[2]) > 133.5]  # 140, 165 and 230 Hz
        self.assertEqual(len(above), 3)
        for row in above:
            self.assertIn("above the highest extracted FE mode (133.50 Hz)", row[11])
        self.assertEqual(len(view.range_warnings), 3)
        self.assertTrue(view.range_warnings[0].startswith(f"Exp record {above[0][0]} (mode {above[0][1]}"))


class ExperimentalDataTests(_Folder):
    def test_several_dataset_55_sets_are_never_mixed_and_record_1_is_kept(self):
        experimental = self.read(ws.EXPERIMENTAL, S.write_experiment(
            self.inputs / "two.unv", S.E0, S.G0, sets=(("bravo", 4), ("processing", 6))))
        fe = self.fe()
        self.assertEqual(dm.set_options(experimental), [(0, f"Modal set 1 of 2: {experimental.sets[0].title}"),
                                                        (1, f"Modal set 2 of 2: {experimental.sets[1].title}")])
        for index, chosen in enumerate(experimental.sets):
            with self.subTest(set=chosen.key):
                outcome = self.run_gui(fe, experimental, index)
                self.assertEqual([f for _, f in outcome.diagnostic.experimental_modes],
                                 [r.frequency_hz for r in chosen.records])  # this set's frequencies only
                self.assertEqual(outcome.view.set_title, f"Modal set {index + 1} of 2: {chosen.title}")
                self.assertEqual(outcome.view.nearest_rows[0][:2], ("1", "1"))  # record 1, not excluded
                self.assertEqual(len(outcome.view.nearest_rows), len(chosen.records))
                self.assertIn(f"modal set {chosen.key}", outcome.view.nearest_rows[0][10])
        self.assertEqual((len(experimental.sets[0].records), len(experimental.sets[1].records)), (4, 6))

    def test_dataset_2414_records(self):
        path = write_2414_unv(self.inputs / "real_2414.unv", [
            {"analysis_type": 2, "mode": 7, "frequency": 23.5, "label": 1},
            {"analysis_type": 2, "mode": 9, "frequency": 47.25, "label": 2}])
        experimental = self.read(ws.EXPERIMENTAL, path)
        view = self.run_gui(self.fe(), experimental).view
        self.assertEqual([row[:3] for row in view.nearest_rows], [("1", "7", "23.5000"), ("2", "9", "47.2500")])
        self.assertIn("dataset 2414 record 1 (physical, importer)", view.nearest_rows[0][10])
        self.assertFalse(view.provisional)

    def test_ambiguous_records_keep_the_importer_classification_and_warnings(self):
        import universal_reader

        path = self.inputs / "ambiguous.unv"
        path.write_text("synthetic records", encoding="utf-8")
        datasets = [geometry_4(), mode_55_4(1, 10.0), mode_55_4(2, 20.0, ambiguous=True)]
        pm.read_preview(ws.EXPERIMENTAL, F.write_frf_only(self.inputs / "warm.uff"))  # the chain is installed
        with mock.patch.object(universal_reader, "_read_universal_datasets", return_value=datasets):
            experimental = self.read(ws.EXPERIMENTAL, path)
        chosen = experimental.sets[0]
        view = self.run_gui(self.fe(), experimental).view
        self.assertEqual(len(view.nearest_rows), 2)  # the ambiguous record is kept, not excluded
        self.assertTrue(view.nearest_rows[1][10].startswith("AMBIGUOUS (importer) — dataset 55 record 2"))
        self.assertIn("AMBIGUOUS (importer)", view.nearest_rows[1][11])
        self.assertEqual(view.nearest_rows[1][10], chosen.records[1].label)
        self.assertNotIn("AMBIGUOUS", view.nearest_rows[0][10])
        self.assertTrue(chosen.warnings)
        self.assertEqual(view.importer_warnings, chosen.warnings)  # the importer's wording, unchanged

    def test_frf_peak_records_of_dataset_58_are_provisional(self):
        experimental = self.read(ws.EXPERIMENTAL, F.write_frf_only(self.inputs / "frf.uff"))
        view = self.run_gui(self.fe(), experimental).view
        self.assertTrue(view.provisional)
        self.assertIn("PROVISIONAL", view.experimental_source)
        for row in view.nearest_rows:
            self.assertEqual(row[10], "PROVISIONAL — NOT A VALIDATED FITTED MODE")
            self.assertTrue(row[11].startswith("PROVISIONAL — NOT A VALIDATED FITTED MODE"))
        self.assertEqual(view.nearest_rows[0][0], "1")


class GuardTests(_Folder):
    def test_no_mac_pair_registration_archive_or_second_import(self):
        fe = self.fe()
        path = S.write_experiment(self.inputs / "one.unv", S.E0, S.G0)
        experimental = self.read(ws.EXPERIMENTAL, path)
        before = fingerprint(self.inputs)
        import abaqus_bridge
        import modal_core
        import reviewed_core
        import universal_reader
        from services import experiment_fixture_regression, new_odb_comparison, specimen_catalog_view
        from services import archived_sensitivity_evidence

        forbidden = [(modal_core, "modal_assurance_criterion"), (modal_core, "compare_modal_datasets"),
                     (reviewed_core, "compare_modal_datasets"), (reviewed_core, "geometry_alignment_candidates"),
                     (reviewed_core, "geometry_from_frozen_registration"),
                     (new_odb_comparison, "bind_registration_by_fe_geometry"),
                     (new_odb_comparison, "load_fixture_registration"),
                     (new_odb_comparison, "fresh_content_identity"),
                     (experiment_fixture_regression, "load_fixture_registration"),
                     (archived_sensitivity_evidence, "fresh_content_identity"),
                     (specimen_catalog_view, "load_catalogue"), (abaqus_bridge, "load_extracted_odb"),
                     (universal_reader, "load_universal_modal_file"),
                     (universal_reader, "discover_experimental_modal_sets")]
        for module, name in forbidden:
            guard = mock.patch.object(module, name, side_effect=AssertionError(f"{name} called"))
            guard.start()
            self.addCleanup(guard.stop)
        outcome = self.run_gui(fe, experimental)
        self.assertEqual(outcome.view.mac, "NOT_COMPUTED")
        self.assertEqual(json.loads(json.dumps(outcome.diagnostic.to_dict()))["mode_pairs"],
                         "NONE (physical modal correspondence not verified)")
        self.assertEqual(fingerprint(self.inputs), before)
        self.assertEqual(sorted(p.name for p in self.inputs.iterdir()), ["one.unv", "package"])


class AvailabilityTests(unittest.TestCase):
    def test_the_reasons_name_what_is_missing(self):
        self.assertEqual(dm.unavailable(None, None, None), (dm.NEED_FE, dm.NEED_EXPERIMENTAL))
        self.assertEqual(dm.unavailable(object(), None, None), (dm.NEED_EXPERIMENTAL,))
        self.assertEqual(dm.unavailable(None, object(), 0), (dm.NEED_FE,))
        self.assertEqual(dm.unavailable(object(), object(), None), (dm.NEED_SET,))
        self.assertEqual(dm.unavailable(object(), object(), 0), ())


class RequestTests(_Folder):
    def test_a_set_cancel_event_gives_a_cancelled_outcome(self):
        event = threading.Event()
        event.set()
        with mock.patch.object(dm, "diagnose", side_effect=AssertionError("not called")):
            outcome = dm.run_diagnostic(object(), object(), 0, 3, event)
        self.assertEqual((outcome.cancelled, outcome.diagnostic, outcome.error), (True, None, ""))

    def test_a_cancel_during_the_service_discards_its_result(self):
        fe = self.fe()
        experimental = self.read(ws.EXPERIMENTAL, S.write_experiment(self.inputs / "one.unv", S.E0, S.G0))
        event = threading.Event()
        real = dm.diagnose

        def cancelled_while_computing(*args):
            result = real(*args)
            event.set()  # the set was changed while the service ran
            return result

        with mock.patch.object(dm, "diagnose", cancelled_while_computing):
            outcome = dm.run_diagnostic(fe, experimental, 0, 3, event)
        self.assertTrue(outcome.cancelled)
        self.assertIsNone(outcome.view)

    def test_one_diagnostic_at_a_time_and_a_request_cancelled_while_waiting_never_runs(self):
        fe = self.fe()
        experimental = self.read(ws.EXPERIMENTAL, S.write_experiment(self.inputs / "one.unv", S.E0, S.G0))
        started, release, calls, outcomes = threading.Event(), threading.Event(), [], {}
        real = dm.diagnose

        def slow(*args):
            calls.append(args)
            started.set()
            release.wait(30)
            return real(*args)

        first, second = threading.Event(), threading.Event()
        with mock.patch.object(dm, "diagnose", slow):
            workers = [threading.Thread(target=lambda e=e, t=t: outcomes.setdefault(t, dm.run_diagnostic(
                fe, experimental, 0, t, e))) for t, e in ((1, first), (2, second))]
            workers[0].start()
            self.assertTrue(started.wait(30))
            workers[1].start()
            workers[1].join(0.3)
            self.assertTrue(workers[1].is_alive())  # the second request waits for the first
            self.assertEqual(len(calls), 1)
            second.set()  # cancelled while it waits (another set was chosen)
            release.set()
            for worker in workers:
                worker.join(30)
        self.assertEqual(len(calls), 1)  # the cancelled request never ran the service
        self.assertTrue(outcomes[2].cancelled)
        self.assertEqual(outcomes[1].view.status, "FREQUENCY_ONLY_DIAGNOSTIC")

    def test_a_service_error_becomes_a_message(self):
        with mock.patch.object(dm, "diagnose", side_effect=ValueError("Experimental frequency must be finite")):
            outcome = dm.run_diagnostic(object(), mock.Mock(sets=[object()]), 0, 3, threading.Event())
        self.assertEqual(outcome.error, "The frequency diagnostic could not be computed (ValueError: Experimental "
                                        "frequency must be finite).")
        self.assertIsNone(outcome.view)

    def test_only_the_current_request_is_shown(self):
        slot = dm.DiagnosticSlot()
        token, event = slot.start(("fe", "exp", 0))
        stale = dm.DiagnosticOutcome(token, diagnostic="old", view="old")
        slot.reset()  # another set, a replaced file, Inspect again or a closed window
        self.assertTrue(event.is_set())
        self.assertFalse(slot.finish(stale))
        self.assertEqual((slot.state, slot.outcome), (dm.IDLE, None))
        token, _ = slot.start(("fe", "exp", 1))
        self.assertFalse(slot.finish(stale))
        self.assertTrue(slot.finish(dm.DiagnosticOutcome(token, diagnostic="new", view="new")))
        self.assertEqual(slot.state, dm.DONE)
        self.assertFalse(slot.finish(dm.DiagnosticOutcome(token, diagnostic="twice")))
        token, _ = slot.start(("fe", "exp", 1))
        self.assertTrue(slot.finish(dm.DiagnosticOutcome(token, error="refused")))
        self.assertEqual(slot.state, dm.FAILED)
        token, _ = slot.start(("fe", "exp", 1))
        self.assertTrue(slot.finish(dm.DiagnosticOutcome(token, cancelled=True)))
        self.assertEqual(slot.state, dm.IDLE)


class StartTests(unittest.TestCase):
    def test_importing_the_diagnostic_model_loads_no_service_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            code = ("import sys; sys.path.insert(0, sys.argv[1]); import new_gui.diagnostic_model; "
                    "bad = sorted(m for m in sys.modules if m in ('main', 'tkinter', 'matplotlib', "
                    "'services.new_odb_comparison', 'services.modal_data_viewer', 'fast_cache')); "
                    "print(','.join(bad))")
            done = subprocess.run([sys.executable, "-c", code, str(ROOT / "src")], capture_output=True, text=True,
                                  timeout=120, env={**os.environ, "LOCALAPPDATA": folder})
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(done.stdout.strip(), "")
            self.assertEqual(list(Path(folder).rglob("*")), [])


if __name__ == "__main__":
    unittest.main()
