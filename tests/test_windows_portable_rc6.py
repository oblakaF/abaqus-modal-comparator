"""WINDOWS PORTABLE RC6: the portable build with the direct ODB import (PRIORITY-0) is made apart from RC1-RC5 (no
PyInstaller needed to run these tests).

- its name is AbaqusModalComparator_RC6; it never writes the RC1-RC5 desktop copies, and nothing that exists in its
  build folder or on the desktop is deleted or replaced (no --replace);
- the RC1-RC5 packaging is unchanged (SHA-256 of every file);
- the ODB extractor abaqus_scripts/extract_odb.py is copied beside the program, where the frozen abaqus_bridge
  resolves it (_internal\\abaqus_bridge.pyc -> parents[1]/abaqus_scripts/extract_odb.py), byte-identical to the
  repository's, opening the ODB readOnly=True; the extractor itself is not changed by RC6;
- the research checks of RC5 still hold from another folder, the package list and the ZIP rules are those of RC5.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / "packaging" / "portable_rc6"
sys.path.insert(0, str(ROOT / "src"))

# SHA-256 (LF) of every RC1-RC5 packaging file at 3d4e38b (the RC5 branch RC6 starts from)
UNCHANGED = dict(line.split()[::-1] for line in """
6fa841ee8fb260dcb7913402f9c9363897cd3a49edec123b0873c3a7a77b68c6 portable_rc1/AbaqusModalComparator_RC1.spec
678fcb21ee6baad666c678dda3dcc2d2a5b1028a10a275af75a5201c7c0950c6 portable_rc1/build_portable.py
22e45629fd671a2d3d71e1de65c5dbe23ac1964bf55fda8d420aee7ae4669792 portable_rc1/launch_new_gui.py
744d85c94bd61f92968088609ddb52cf8bdf541db7dc97270c16367eb562d7db portable_rc1/requirements-build.txt
0d7f6ae051bd05313ac67aa481cec4c016b31bd09a45d469677bb21cce669c0c portable_rc1/rthook_open_audit.py
b832b519692299a187e43116d9c5cd35ddaa4e8550d00fd2f446ad968af11d56 portable_rc2/AbaqusModalComparator_RC2.spec
09e0d219c85cd2c61b83cfb5a40c4a4876d977f578ba3868900a326d5ba45e06 portable_rc2/build_portable.py
b19ccbd30c00faf57df966cba8eeb211b87032be64288bfe31f1099f81862810 portable_rc2/launch_new_gui.py
2cd98f1a55916f130720782a379c39b88e0e681f58edaaf9e6bd6dc01251bdc5 portable_rc2/requirements-build.txt
2c1f70ed0aea33426a641026a00ab069368c49a94d432ea87341b51a86179ff0 portable_rc2/rthook_open_audit.py
88b68b36594dbe9d18941190c96b6ecfd27bca1c734e211dc114df8d9127c81d portable_rc3/AbaqusModalComparator_RC3.spec
99511fdecc93de41c59efa5764ce9eb111d1dcc91eace73f077e26d34352a195 portable_rc3/build_portable.py
063d9f97be9cc19c4fe14dd7a489607aaf9d0648357c2bc294a51db4aba02b7c portable_rc3/launch_new_gui.py
af07fc8af05f7576f85c2455d127d60e54e88e5f69ff57dcc5a7ac04f33d6efd portable_rc3/requirements-build.txt
93cbafcdce13ac7477eb3a38bfad9dbb327a6beacb87cae8e9bba10805b29a0a portable_rc3/rthook_open_audit.py
c6182b36c90a1aaa9f118469f5842ae8b5871f241f3e1aca5ec2990752c9dd5c portable_rc3_f1/AbaqusModalComparator_RC3_F1.spec
3217fe3d8a808280e0687bdf2cad1180461e22dba40804ab6cdff8837b794d7b portable_rc3_f1/build_portable.py
a3dd30426ec7d7ab2c698d0d44752e880ff3f23cb3943b37b450cc400450740e portable_rc3_f1/launch_new_gui.py
5a2f5df5bb44e5c34f70713dba7cfbde4ced9069c32d573af21f560a44f2b1aa portable_rc3_f1/requirements-build.txt
ba62e13e2927cfc32339665678af37d2ea54cf3314bfbfaadfd218119e1984b1 portable_rc3_f1/rthook_open_audit.py
3019e28c8d5061d7c83fe53835fd3ede18c383ed7fc6b5351ae4bbc04a7a1447 portable_rc3_f2/AbaqusModalComparator_RC3_F2.spec
babf41bc5a6679795630976c61838fd3ee309dbace05e6edc278e40d7434be79 portable_rc3_f2/build_portable.py
184747142b5f2f2b8dc5b034b9ea5d69fc473ddcfb4675a18d2aa70bf7ca938b portable_rc3_f2/launch_new_gui.py
e8dad62bc1935fbaf3ee070d5dce95ccf5c3effda5b5f9eeba943df67da9f2c3 portable_rc3_f2/requirements-build.txt
44015afdfc29c666cda9870498c73b46f7a668da4ff0bda7edab494c727b73e6 portable_rc3_f2/rthook_open_audit.py
e2019f94f0487133e0f3926af223038c77649ea6d97ee5e033671c1fcb7df725 portable_rc4/AbaqusModalComparator_RC4.spec
d07991d8737caa8ff5f55fd5545c5040fe0c47761d60da68343ac1f3094200d7 portable_rc4/build_portable.py
44a8c606368f4f36f98b52f071d4104daf09782374863db51468406e6261c63b portable_rc4/launch_new_gui.py
931827bf082423e72b37664daeef529215dd24eca3c1ac1493246e93a817ccaa portable_rc4/requirements-build.txt
35e4ae8eee35fc3137037ffdf0713974d676faa4f7a663e9cb7ab239c44d80cb portable_rc4/rthook_open_audit.py
76e0bcb3ee69d6a7497e6a53e57f368b7b969026b1ea2f666c34a59bc5960ee6 portable_rc4_f1/AbaqusModalComparator_RC4_F1.spec
a6840c8df473a791a67a8f58645e5484fb213f2bfa9d356a393a249aea8d3215 portable_rc4_f1/build_portable.py
975bf8c0487a362cc75067af01b7d8adb267dc6757f6f47421b69f06c6ca9ca0 portable_rc4_f1/launch_new_gui.py
e374f726c378572d598743023da17a9abc8cbfad0c63f738343a0285f2b3f77f portable_rc4_f1/requirements-build.txt
b19a9f65004fd054cde8c359bb3457d62a4edf6d66dc520050b8ea0ed97387e1 portable_rc4_f1/rthook_open_audit.py
f47e196d12fd07e7801369ebf557bc45d5a1a2153c97d4fa948c90e9a7661004 portable_rc5/AbaqusModalComparator_RC5.spec
67009d61d507a1e27f02e059f66e0bf2cda0815551be789bb113f8d372feef6a portable_rc5/build_portable.py
44783cfaaac3a775e805b0f4a1170984f19df4e6a295ec8304dab28c389d154e portable_rc5/launch_new_gui.py
eb7d665c5ad62a8a2f6a25d537a717365f8fca02a6f5639a3e0154e252f62a38 portable_rc5/requirements-build.txt
82c9718e1b8e57ab343fd3c1c4738bd0777f99a1c831cd83904cfc879a2fc27d portable_rc5/rthook_open_audit.py
""".split("\n") if line.strip())
# the extractor as pinned by the RC6 route: PRIORITY-0 changes nothing in it
EXTRACTOR_SHA256 = hashlib.sha256((ROOT / "abaqus_scripts" / "extract_odb.py").read_bytes()
                                  .replace(b"\r\n", b"\n")).hexdigest()


def _build_module():
    spec = importlib.util.spec_from_file_location("build_portable_rc6", PACKAGING / "build_portable.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PortableRc6PackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = _build_module()

    def test_a_separate_build_that_never_writes_the_earlier_ones(self):
        self.assertEqual(self.build.NAME, "AbaqusModalComparator_RC6")
        spec = (PACKAGING / "AbaqusModalComparator_RC6.spec").read_text(encoding="utf-8")
        self.assertIn('name="AbaqusModalComparator_RC6"', spec)
        for module in ("services.odb_import_service", "abaqus_bridge", "ui_policy",
                       "services.single_plate_fe_response"):
            self.assertIn(f'"{module}"', spec)
        self.assertEqual(set(self.build.PROTECTED_DESKTOP), {
            f"AbaqusModalComparator_{name}{suffix}"
            for name in ("RC1", "RC2", "RC3", "RC3_F1", "RC3_F2", "RC4", "RC4_F1", "RC5") for suffix in ("", ".zip")})
        self.assertNotIn(self.build.NAME, self.build.PROTECTED_DESKTOP)

    def test_rc1_to_rc5_packaging_unchanged(self):
        packaging = ROOT / "packaging"
        earlier = sorted(p.relative_to(packaging).as_posix() for p in packaging.glob("portable_rc*/*")
                         if p.is_file() and p.parent.name != "portable_rc6" and p.suffix in {".py", ".spec", ".txt"})
        self.assertEqual(earlier, sorted(UNCHANGED))
        for relative, expected in UNCHANGED.items():
            data = (packaging / relative).read_bytes().replace(b"\r\n", b"\n")
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected, relative)

    def test_nothing_existing_is_deleted_or_replaced(self):
        with tempfile.TemporaryDirectory(prefix="RC6 existing ") as folder:
            folder = Path(folder)
            earlier = folder / "dist" / "AbaqusModalComparator_RC6" / "BUILD_INFO.json"
            earlier.parent.mkdir(parents=True)
            earlier.write_text("{}", encoding="utf-8")
            with self.assertRaises(SystemExit):
                self.build.refuse_existing(folder)
            with self.assertRaises(SystemExit):
                self.build.main(["--out", str(folder)])
            self.assertEqual(earlier.read_text(encoding="utf-8"), "{}")
            desktop = folder / "desktop"
            desktop.mkdir()
            self.assertEqual([t.name for t in self.build.desktop_targets(desktop)],
                             ["AbaqusModalComparator_RC6", "AbaqusModalComparator_RC6.zip",
                              "AbaqusModalComparator_RC6.zip.sha256"])
            (desktop / "AbaqusModalComparator_RC6.zip").write_bytes(b"earlier RC6")
            with self.assertRaises(SystemExit):
                self.build.desktop_targets(desktop)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):  # there is no --replace
            self.build.main(["--out", "unused", "--replace"])

    def test_the_extractor_is_packaged_where_the_frozen_bridge_resolves_it(self):
        with tempfile.TemporaryDirectory(prefix="RC6 extractor ") as folder:
            folder = Path(folder)
            with self.assertRaises(SystemExit):  # not there yet
                self.build.check_extractor(folder)
            copied = self.build.copy_extractor(folder)
            self.assertEqual(copied["path"], "abaqus_scripts/extract_odb.py")
            packaged = folder / "abaqus_scripts" / "extract_odb.py"
            self.assertTrue(packaged.is_file())
            self.assertEqual(packaged.read_bytes(), (ROOT / "abaqus_scripts" / "extract_odb.py").read_bytes())
            checked = self.build.check_extractor(folder)
            self.assertEqual(Path(checked["resolved_by_bridge"]), packaged.resolve())
            self.assertTrue(checked["read_only"])
            # the same path the service names in the source tree: parents[1] of abaqus_bridge + abaqus_scripts
            import abaqus_bridge
            from services import odb_import_service as svc
            self.assertEqual(svc.extractor_script_path(),
                             Path(abaqus_bridge.__file__).resolve().parents[1] / "abaqus_scripts" / "extract_odb.py")
            self.assertTrue(svc.extractor_script_path().is_file())
            # RC6 does not change the extractor
            self.assertEqual(hashlib.sha256(packaged.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
                             EXTRACTOR_SHA256)
            self.assertIn("readOnly=True", packaged.read_text(encoding="utf-8"))
            packaged.write_text("changed", encoding="utf-8")
            with self.assertRaises(SystemExit):
                self.build.check_extractor(folder)
            self.assertEqual(self.build.forbidden_files(folder), [])  # a .py beside the program is allowed

    def test_the_results_and_the_demonstration_run_from_another_folder(self):
        with tempfile.TemporaryDirectory(prefix="RC6 other folder ") as folder:
            self.build.copy_documents(Path(folder))
            self.assertEqual(self.build.forbidden_files(Path(folder)), [])
            result = self.build.check_research(Path(folder))
        self.assertEqual(result["matching_rows"], {"PLATE": 11, "SP-13": 12, "SP-10": 12})
        fe = result["fe_response"]
        self.assertEqual((fe["status"], fe["terms"], fe["fe7_f0_hz"]), ("ARCHIVED_FE_RESULT", 13, 19.07217))

    def test_package_list_zip_and_forbidden_files(self):
        with tempfile.TemporaryDirectory(prefix="RC6 package ") as folder:
            root = Path(folder) / "AbaqusModalComparator_RC6"
            for relative in ("AbaqusModalComparator.exe", "_internal/lib/sample.dat", "abaqus_scripts/extract_odb.py"):
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                (root / relative).write_bytes(relative.encode())
            self.assertEqual(self.build.forbidden_files(root), [])
            self.build.write_package_list(root)
            self.assertTrue(self.build.verify_folder(root)["verified"])
            archive = Path(folder) / "AbaqusModalComparator_RC6.zip"
            self.build.make_zip(root, archive)
            self.assertEqual(self.build.check_zip(root, archive), {"zip_files": 4, "crc": "OK"})
            with self.assertRaises(SystemExit):  # an existing ZIP is never replaced
                self.build.make_zip(root, archive)
            with mock.patch.object(self.build.os, "rename", os.replace), self.assertRaises(SystemExit):
                self.build.make_zip(root, archive)
            for relative in ("docs/model.inp", "docs/job.odb", "docs/pack/manifest.json", "data/test.unv"):
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                (root / relative).write_bytes(b"x")
            self.assertEqual(self.build.forbidden_files(root), sorted(
                ["docs/model.inp", "docs/job.odb", "docs/pack/manifest.json", "data/test.unv"]))


if __name__ == "__main__":
    unittest.main()
