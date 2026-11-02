"""PRIORITY-0 / RC6: the ODB import service without Qt and without Abaqus (a fake runner stands for the bridge).

- nothing starts without the user's confirmation, and nothing starts when no Abaqus launcher was found;
- the ODB is identified by content (SHA-256) before the extraction and the identity is recorded beside the package;
- each extraction gets a new folder (nothing is overwritten); a complete package of the same content and range is
  reused without a run; an incomplete one is not;
- errors (no modal results, Abaqus failure, no space, cancellation) become messages; the folder is marked INCOMPLETE;
- the source re-check finds a change by content even when size and modification time are unchanged.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from abaqus_bridge import AbaqusExtractionError, AnalysisCancelled  # noqa: E402
from services import odb_import_service as svc  # noqa: E402
from test_local_fe_preview import described, write_package  # noqa: E402
from ui_policy import AbaqusInstallation  # noqa: E402

LAUNCHER = [AbaqusInstallation("Abaqus 2024 — detected ✓", "C:/SIMULIA/Commands/abaqus.bat")]
FOUND = lambda: LAUNCHER  # noqa: E731
NONE = lambda: []  # noqa: E731


def fake_runner(modes=(7, 8, 9), *, available=(1, 16)):
    """A runner with the bridge's signature that writes a format-2 package and a log like the extractor's."""
    calls = []

    def run(**kwargs):
        calls.append(kwargs)
        folder = Path(kwargs["output_directory"])
        start, end = kwargs["start_mode"], kwargs["end_mode"]
        chosen = [m for m in modes if start <= m <= end]
        if not chosen:
            raise AbaqusExtractionError("Abaqus could not extract the ODB results.\n\nRuntimeError: No "
                                        f"frequency-extraction frames with displacement output U were found for modes "
                                        f"{start}-{end}.")
        (folder / "abaqus_extraction.log").write_text(
            f"COMMAND\n...\n\nOUTPUT\nPROGRESS: opening ODB x.odb\nPROGRESS: modes available {available[0]}-"
            f"{available[1]}; requested {start}-{end}\n", encoding="utf-8")
        return write_package(folder, [(m, 10.0 * m, described(10.0 * m)) for m in chosen], start=start, end=end)

    run.calls = calls
    return run


class _Folder(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.odb = self.root / "inputs" / "plate model.odb"
        self.odb.parent.mkdir()
        self.odb.write_bytes(b"synthetic odb content; never opened by the service " * 100)
        self.results = self.root / "results"

    def plan(self, **kwargs):
        options = {"discover": FOUND}
        options.update(kwargs)
        return svc.plan_extraction(self.odb, self.results, **options)


class DetectionTests(_Folder):
    def test_no_launcher_is_a_state_with_fixes_and_the_extractor_never_runs(self):
        plan = self.plan(discover=NONE)
        self.assertFalse(plan.abaqus.available)
        self.assertFalse(plan.ready)
        self.assertIn("No Abaqus launcher was found", plan.abaqus.explanation)
        self.assertEqual(len(plan.abaqus.fixes), 3)
        run = fake_runner()
        with self.assertRaises(svc.OdbImportRefused):
            svc.run_extraction(plan, confirmed=True, runner=run)
        self.assertEqual(run.calls, [])
        self.assertFalse(self.results.exists())

    def test_a_detected_launcher_is_proposed_and_a_chosen_one_is_checked(self):
        plan = self.plan()
        self.assertTrue(plan.abaqus.available)
        self.assertEqual(plan.abaqus.command, "C:/SIMULIA/Commands/abaqus.bat")
        self.assertIn(("Abaqus 2024 — detected ✓", "C:/SIMULIA/Commands/abaqus.bat"), plan.abaqus.choices)
        chosen = self.plan(abaqus_command=str(self.root / "missing.bat"))
        self.assertFalse(chosen.abaqus.available)
        self.assertIn("does not exist", chosen.abaqus.explanation)
        bat = self.root / "my_abaqus.bat"
        bat.write_text("@echo off\n", encoding="utf-8")
        chosen = self.plan(abaqus_command=str(bat))
        self.assertTrue(chosen.abaqus.available)
        self.assertEqual(Path(chosen.abaqus.command), bat.resolve())

    def test_a_failing_search_is_reported_not_raised(self):
        def broken():
            raise RuntimeError("PATH is broken")

        found = svc.detect_abaqus(discover=broken)
        self.assertFalse(found.available)
        self.assertIn("PATH is broken", found.explanation)

    def test_the_extractor_script_is_the_one_the_bridge_runs(self):
        plan = self.plan()
        self.assertTrue(plan.extractor_present)
        self.assertEqual(plan.extractor, ROOT / "abaqus_scripts" / "extract_odb.py")


class PlanTests(_Folder):
    def test_the_file_is_checked_without_being_read(self):
        with self.assertRaises(svc.OdbImportRefused):
            svc.check_odb(self.root / "inputs" / "model.inp")
        with self.assertRaises(svc.OdbImportRefused):
            svc.check_odb(self.root / "inputs" / "missing.odb")
        empty = self.root / "inputs" / "empty.odb"
        empty.write_bytes(b"")
        with self.assertRaises(svc.OdbImportRefused):
            svc.check_odb(empty)
        check = svc.check_odb(self.odb)
        self.assertEqual(check.size, self.odb.stat().st_size)
        self.assertEqual(check.warnings, ())
        self.odb.with_suffix(".lck").write_text("", encoding="utf-8")
        self.assertIn("lock file", svc.check_odb(self.odb).warnings[0])

    def test_the_range_and_the_folder_are_checked(self):
        with self.assertRaises(svc.OdbImportRefused):
            self.plan(start_mode=0)
        with self.assertRaises(svc.OdbImportRefused):
            self.plan(start_mode=9, end_mode=7)
        with self.assertRaises(svc.OdbImportRefused):
            svc.plan_extraction(self.odb, "", discover=FOUND)
        with self.assertRaises(svc.OdbImportRefused):
            svc.plan_extraction(self.odb, self.odb, discover=FOUND)  # a file, not a folder
        plan = self.plan()
        self.assertEqual((plan.start_mode, plan.end_mode), (svc.DEFAULT_START_MODE, svc.DEFAULT_END_MODE))
        self.assertEqual(plan.start_mode, 1)  # the first elastic mode is never skipped by the default range
        self.assertGreater(plan.free_bytes, 0)
        self.assertEqual(dict(plan.summary())["Requested modes"][:4], "1-30")

    def test_too_little_free_space_is_refused_before_anything_starts(self):
        with mock.patch.object(svc.shutil, "disk_usage", return_value=os.statvfs_result((0,) * 10)
                               if hasattr(os, "statvfs_result") else mock.Mock(free=10 * 2**20)):
            with mock.patch.object(svc.shutil, "disk_usage", return_value=mock.Mock(free=10 * 2**20)):
                with self.assertRaises(svc.OdbImportRefused) as refused:
                    self.plan()
        self.assertIn("Not enough free space", str(refused.exception))


class RunTests(_Folder):
    def test_nothing_runs_without_confirmation(self):
        run = fake_runner()
        with self.assertRaises(svc.OdbImportRefused):
            svc.run_extraction(self.plan(), confirmed=False, runner=run)
        self.assertEqual(run.calls, [])

    def test_a_confirmed_run_writes_a_new_package_with_its_source_identity(self):
        run = fake_runner()
        lines = []
        result = svc.run_extraction(self.plan(), confirmed=True, runner=run, progress=lines.append)
        self.assertEqual(len(run.calls), 1)
        call = run.calls[0]
        self.assertEqual(Path(call["odb_path"]), self.odb.resolve())
        self.assertEqual((call["start_mode"], call["end_mode"]), (1, 30))
        self.assertEqual(call["abaqus_command"], "C:/SIMULIA/Commands/abaqus.bat")
        self.assertEqual(result.package_folder, self.results / "plate_model_modes_1-30")
        self.assertEqual(result.manifest_path, result.package_folder / "manifest.json")
        self.assertEqual(result.extracted_modes, (7, 8, 9))
        self.assertEqual(result.extracted_range_text, "7-9")
        self.assertEqual(result.available_range, (1, 16))
        self.assertIn("Requested Abaqus modes 1-30", result.range_notice)
        self.assertFalse(result.reused)
        record = json.loads((result.package_folder / svc.SOURCE_RECORD).read_text(encoding="utf-8"))
        self.assertEqual(record["schema"], svc.SCHEMA)
        self.assertEqual(record["odb"]["sha256"], svc.hash_file(self.odb)["sha256"])
        self.assertEqual(record["odb"]["size"], self.odb.stat().st_size)
        self.assertEqual((record["start_mode"], record["end_mode"], record["extracted_modes"]), (1, 30, [7, 8, 9]))
        self.assertTrue(record["read_only"])
        self.assertTrue(any("identifying the ODB content" in line for line in lines))
        self.assertTrue(any("starting Abaqus Python" in line for line in lines))
        self.assertEqual(self.odb.read_bytes(), b"synthetic odb content; never opened by the service " * 100)

    def test_a_second_run_reuses_the_package_and_a_changed_range_gets_a_new_folder(self):
        run = fake_runner()
        first = svc.run_extraction(self.plan(), confirmed=True, runner=run)
        second = svc.run_extraction(self.plan(), confirmed=True, runner=run)
        self.assertEqual(len(run.calls), 1)
        self.assertTrue(second.reused)
        self.assertEqual(second.package_folder, first.package_folder)
        self.assertEqual(second.extracted_modes, (7, 8, 9))
        third = svc.run_extraction(self.plan(start_mode=7, end_mode=8), confirmed=True, runner=run)
        self.assertEqual(len(run.calls), 2)
        self.assertEqual(third.package_folder, self.results / "plate_model_modes_7-8")
        self.assertEqual(third.extracted_modes, (7, 8))
        without = svc.run_extraction(self.plan(), confirmed=True, runner=run, reuse_existing=False)
        self.assertEqual(len(run.calls), 3)
        self.assertEqual(without.package_folder, self.results / "plate_model_modes_1-30_2")  # never overwritten
        self.assertTrue((first.package_folder / "manifest.json").is_file())

    def test_a_changed_odb_content_is_extracted_again_not_reused(self):
        run = fake_runner()
        first = svc.run_extraction(self.plan(), confirmed=True, runner=run)
        stat = self.odb.stat()
        self.odb.write_bytes(b"Synthetic odb content; never opened by the service " * 100)  # same size
        os.utime(self.odb, ns=(stat.st_atime_ns, stat.st_mtime_ns))  # same modification time
        second = svc.run_extraction(self.plan(), confirmed=True, runner=run)
        self.assertEqual(len(run.calls), 2)
        self.assertFalse(second.reused)
        self.assertNotEqual(second.package_folder, first.package_folder)

    def test_an_incomplete_package_is_never_reused(self):
        run = fake_runner()
        first = svc.run_extraction(self.plan(), confirmed=True, runner=run)
        (first.package_folder / "mode_0008.csv").unlink()
        second = svc.run_extraction(self.plan(), confirmed=True, runner=run)
        self.assertEqual(len(run.calls), 2)
        self.assertFalse(second.reused)

    def test_no_modal_results_in_the_range_is_explained_and_the_folder_is_marked(self):
        run = fake_runner(modes=(7, 8, 9))
        with self.assertRaises(svc.OdbImportRefused) as refused:
            svc.run_extraction(self.plan(start_mode=20, end_mode=25), confirmed=True, runner=run)
        text = str(refused.exception)
        self.assertIn("no modal results in the requested range", text)
        folder = self.results / "plate_model_modes_20-25"
        self.assertIn(str(folder), text)
        self.assertTrue((folder / "INCOMPLETE.txt").is_file())
        self.assertEqual(svc.existing_packages(self.results, svc.hash_file(self.odb)["sha256"], 20, 25), [])

    def test_abaqus_failure_space_and_cancellation_become_messages(self):
        def failing(**kwargs):
            raise AbaqusExtractionError("Abaqus could not extract the ODB results.\n\nlicense error\n\nFull log: x")

        with self.assertRaises(svc.OdbImportRefused) as refused:
            svc.run_extraction(self.plan(), confirmed=True, runner=failing)
        self.assertIn("license error", str(refused.exception))

        def no_space(**kwargs):
            raise OSError(28, "No space left on device")

        with self.assertRaises(svc.OdbImportRefused) as refused:
            svc.run_extraction(self.plan(), confirmed=True, runner=no_space)
        self.assertIn("No space left", str(refused.exception))

        def cancelled(**kwargs):
            raise AnalysisCancelled("Analysis stopped by user.")

        with self.assertRaises(svc.OdbImportCancelled):
            svc.run_extraction(self.plan(), confirmed=True, runner=cancelled)
        marked = sorted(p.name for p in self.results.iterdir())
        self.assertEqual(len(marked), 3)
        self.assertTrue(all((self.results / name / "INCOMPLETE.txt").is_file() for name in marked))

    def test_cancellation_during_the_hashing_starts_nothing(self):
        cancel = threading.Event()
        cancel.set()
        run = fake_runner()
        with self.assertRaises(svc.OdbImportCancelled):
            svc.run_extraction(self.plan(), confirmed=True, runner=run, cancel_event=cancel)
        self.assertEqual(run.calls, [])
        self.assertFalse(self.results.exists())


class VerificationTests(_Folder):
    def test_the_source_is_checked_by_content_not_by_size_and_time(self):
        result = svc.run_extraction(self.plan(), confirmed=True, runner=fake_runner())
        same = svc.verify_source(result.package_folder)
        self.assertEqual(same.status, svc.SOURCE_UNCHANGED)
        stat = self.odb.stat()
        self.odb.write_bytes(b"Synthetic odb content; never opened by the service " * 100)
        os.utime(self.odb, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        changed = svc.verify_source(result.package_folder)
        self.assertEqual(changed.status, svc.SOURCE_CHANGED)
        self.assertIn("size and modification time are the same", changed.text)
        self.odb.unlink()
        self.assertEqual(svc.verify_source(result.package_folder).status, svc.SOURCE_MISSING)
        plain = write_package(self.root / "plain", [(7, 70.0, None)])
        self.assertEqual(svc.verify_source(plain.parent).status, svc.SOURCE_NOT_RECORDED)


if __name__ == "__main__":
    unittest.main()
