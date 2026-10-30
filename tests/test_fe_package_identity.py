"""PLATE-ONLY-R2-F1: the content identity of an extracted FE package (``services.fe_package_identity``, no Qt).

The identity covers exactly what ``abaqus_bridge.load_extracted_odb`` reads: ``manifest.json``, its geometry file and
the mode files of the entries the loader keeps. On real, readable packages (the NEW-GUI.4 writer):

- an unchanged package is confirmed; a changed mode CSV, a changed geometry CSV, a deleted file and another manifest
  with the same CSV files are each refused, naming the file;
- a mode entry the loader refuses (contradicting frequency records) is not a dependency;
- dependency paths outside the package folder are refused; a cancellation is a cancellation;
- the ODB named in the manifest is never read or hashed, and an ``.odb`` is never given a package identity;
- Inspect file records the package identity, and none when a package file changes during the read.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from new_gui import preview_model as pm  # noqa: E402
from new_gui import workspace_state as ws  # noqa: E402
from services import fe_package_identity as fpi  # noqa: E402
from test_new_gui4_diagnostic import write_fe_package  # noqa: E402


class _Package(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="fe_package_identity_"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.manifest = write_fe_package(self.folder / "package")
        self.recorded = fpi.identify(self.manifest)

    def content(self) -> dict:
        return json.loads(self.manifest.read_text(encoding="utf-8"))

    def rewrite(self, content: dict) -> None:
        self.manifest.write_text(json.dumps(content, indent=2), encoding="utf-8")


class IdentityTests(_Package):
    def test_the_identity_lists_the_manifest_and_every_file_the_loader_reads(self):
        roles = [f["role"] for f in self.recorded["files"]]
        content = self.content()
        self.assertEqual(roles, ["geometry"] + [f"mode {m['mode']}" for m in content["modes"]])
        self.assertEqual(self.recorded["schema"], fpi.SCHEMA)
        for item in self.recorded["files"]:
            self.assertEqual(len(item["sha256"]), 64)
            self.assertEqual(item["size"], (self.manifest.parent / item["relative"]).stat().st_size)
        self.assertEqual(fpi.confirm(self.manifest, self.recorded)["package_sha256"], self.recorded["package_sha256"])

    def test_a_mode_the_loader_refuses_is_not_a_dependency(self):
        content = self.content()
        content["modes"].insert(0, {"mode": 1, "frequency_hz": 1.0, "file": "mode_missing.csv",
                                    "description": "Mode         1: Value = -7.1E-05 Freq =   0.0000 (cycles/time)"})
        self.rewrite(content)
        identity = fpi.identify(self.manifest)  # the refused entry's file does not even exist
        self.assertNotIn("mode_missing.csv", [f["relative"] for f in identity["files"]])

    def test_the_odb_is_never_read_and_an_odb_gets_no_package_identity(self):
        odb = self.folder / "model.odb"
        odb.write_bytes(b"not an extracted package")
        content = self.content()
        content["odb_path"] = str(odb)
        self.rewrite(content)
        with mock.patch("builtins.open", wraps=open) as opened:
            identity = fpi.identify(self.manifest)
        self.assertNotIn(str(odb), [str(call.args[0]) for call in opened.call_args_list])
        self.assertIsNone(identity["odb_sha256"])
        self.assertEqual(identity["declared_odb_path"], str(odb))
        self.assertIn("ODB", identity["basis"])
        self.assertNotIn(str(odb), [str(self.manifest.parent / f["relative"]) for f in identity["files"]])
        with self.assertRaises(fpi.PackageIdentityRefused) as refused:
            fpi.identify(odb)
        self.assertEqual(refused.exception.kind, fpi.NOT_A_PACKAGE)
        self.assertIsNone(pm.fe_package_identity(odb))

    def test_a_dependency_path_outside_the_package_is_refused(self):
        outside = self.folder / "outside.csv"
        outside.write_text("x", encoding="utf-8")
        for relative in ("../outside.csv", str(outside), "C:/outside.csv", "/outside.csv", "sub/../../outside.csv",
                         "", 7):
            with self.subTest(relative=relative):
                content = self.content()
                content["geometry_file"] = relative
                self.rewrite(content)
                with self.assertRaises(fpi.PackageIdentityRefused) as refused:
                    fpi.identify(self.manifest)
                self.assertIn(refused.exception.kind, (fpi.INVALID_PATH, fpi.NOT_A_PACKAGE))

    def test_a_cancellation_is_a_cancellation(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(fpi.PackageIdentityRefused) as refused:
            fpi.identify(self.manifest, cancel)
        self.assertEqual(refused.exception.kind, fpi.CANCELLED)
        with self.assertRaises(fpi.PackageIdentityRefused) as refused:
            fpi.confirm(self.manifest, self.recorded, cancel)
        self.assertEqual(refused.exception.kind, fpi.CANCELLED)

    def test_without_a_recorded_package_identity_nothing_is_confirmed(self):
        for recorded in (None, {}, {"schema": "other"}):
            with self.subTest(recorded=recorded), self.assertRaises(fpi.PackageIdentityRefused):
                fpi.confirm(self.manifest, recorded)
        with self.assertRaises(fpi.PackageIdentityRefused):
            pm.confirm_fe_identity(self.manifest, {"path": str(self.manifest), "size": 1, "sha256": "0" * 64})


class ChangeTests(_Package):
    def assert_changed(self, text: str) -> None:
        with self.assertRaises(fpi.PackageChanged) as changed:
            fpi.confirm(self.manifest, self.recorded)
        self.assertIn(text, str(changed.exception))

    def test_one_changed_mode_csv_is_refused(self):
        mode = self.recorded["files"][2]
        path = self.manifest.parent / mode["relative"]
        path.write_bytes(path.read_bytes()[:-2] + b"9\n")  # same size, other content
        self.assert_changed(f"{mode['role']} ({mode['relative']}) changed")

    def test_a_changed_geometry_csv_is_refused(self):
        path = self.manifest.parent / "geometry.csv"
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.assert_changed("geometry (geometry.csv) changed")

    def test_a_deleted_file_is_refused(self):
        (self.manifest.parent / self.recorded["files"][1]["relative"]).unlink()
        self.assert_changed("cannot be identified now")

    def test_another_manifest_with_the_same_csv_files_is_refused(self):
        content = self.content()
        content["step_name"] = "Another step"  # the CSV files are unchanged
        self.rewrite(content)
        self.assert_changed("manifest.json changed")

    def test_a_manifest_reading_fewer_modes_is_refused(self):
        content = self.content()
        content["modes"] = content["modes"][:-1]
        self.rewrite(content)
        self.assert_changed("is no longer read")


class InspectTests(_Package):
    def setUp(self):
        super().setUp()
        cache = self.folder / "cache"
        cache.mkdir()
        patcher = mock.patch.dict(os.environ, {"LOCALAPPDATA": str(cache)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_inspect_file_records_the_package_identity(self):
        outcome = pm.run_read(ws.FE, self.manifest, 1, threading.Event())
        self.assertEqual(outcome.error, "")
        self.assertEqual(outcome.identity["sha256"], self.recorded["manifest"]["sha256"])
        self.assertEqual(outcome.identity["package"]["package_sha256"], self.recorded["package_sha256"])
        self.assertEqual(pm.confirm_fe_identity(self.manifest, outcome.identity)["package_sha256"],
                         self.recorded["package_sha256"])

    def test_a_mode_file_changed_during_the_read_gets_no_identity(self):
        real = pm.read_preview
        target = self.manifest.parent / self.recorded["files"][-1]["relative"]

        def read_and_change(kind, path, cancel_event=None):
            preview = real(kind, path, cancel_event)
            target.write_bytes(target.read_bytes() + b"\n")  # the package changes while it is read
            return preview

        with mock.patch.object(pm, "read_preview", side_effect=read_and_change):
            outcome = pm.run_read(ws.FE, self.manifest, 1, threading.Event())
        self.assertIsNotNone(outcome.preview)
        self.assertIsNone(outcome.identity)


if __name__ == "__main__":
    unittest.main()
