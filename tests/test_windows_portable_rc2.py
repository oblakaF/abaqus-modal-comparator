"""WINDOWS PORTABLE RC2: the packaging stays in step with the program (no PyInstaller needed to run these tests).

- every report layer that report_export installs by name, and the Research Results services, are hidden imports;
- every reference file the new interface reads at a repository-relative path, the PRIORITY-6 SP-10 records included,
  is among the files put beside the portable program;
- the build refuses measurement, FE model, solver and extracted FE package files (the 3.1 GB SP-10 package);
- the reference files copied to another folder give the same research results there (the program's own paths);
- the RC1 packaging is unchanged, and the RC2 build never writes the RC1 desktop copies.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
from pathlib import Path, PurePosixPath
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / "packaging" / "portable_rc2"
sys.path.insert(0, str(ROOT / "src"))

from new_gui import known_sources, materials_model, report_export, workspace_state  # noqa: E402
from services import research_results_reader as rr  # noqa: E402
from services import sp10_fe_research as sf  # noqa: E402

RC1_FILES = {  # SHA-256 (LF) of packaging/portable_rc1 at 37fe476
    "AbaqusModalComparator_RC1.spec": "6fa841ee8fb260dcb7913402f9c9363897cd3a49edec123b0873c3a7a77b68c6",
    "build_portable.py": "678fcb21ee6baad666c678dda3dcc2d2a5b1028a10a275af75a5201c7c0950c6",
    "launch_new_gui.py": "22e45629fd671a2d3d71e1de65c5dbe23ac1964bf55fda8d420aee7ae4669792",
    "requirements-build.txt": "744d85c94bd61f92968088609ddb52cf8bdf541db7dc97270c16367eb562d7db",
    "rthook_open_audit.py": "0d7f6ae051bd05313ac67aa481cec4c016b31bd09a45d469677bb21cce669c0c",
}


def _build_module():
    spec = importlib.util.spec_from_file_location("build_portable_rc2", PACKAGING / "build_portable.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _spec_list(name: str) -> list:
    tree = ast.parse((PACKAGING / "AbaqusModalComparator_RC2.spec").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} is not in the spec")


class PortableRc2PackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = _build_module()
        cls.shipped = set(cls.build.tracked_documents())

    def test_the_names_and_the_hidden_imports(self):
        self.assertEqual((self.build.NAME, self.build.EXE), ("AbaqusModalComparator_RC2", "AbaqusModalComparator.exe"))
        hidden = set(_spec_list("REPORT_LAYERS"))
        for module_name, _function in report_export.REPORT_LAYERS:
            self.assertIn(module_name, hidden)
        self.assertEqual(set(_spec_list("RESEARCH_SERVICES")),
                         {"services.research_results_reader", "services.sp10_fe_research"})
        self.assertIn('name="AbaqusModalComparator_RC2"', (PACKAGING / "AbaqusModalComparator_RC2.spec").read_text(
            encoding="utf-8"))

    def test_the_reference_files_read_by_the_interface_are_shipped(self):
        needed = {relative for relative, _sha, _commit in rr.SNAPSHOT_FILES.values()}
        needed.update(relative for relative, _sha, _commit in sf.ARCHIVE_FILES.values())
        needed.add(known_sources.PROVENANCE.relative_to(known_sources.REPO_ROOT).as_posix())
        needed.add(workspace_state.STATUS_PATH.relative_to(ROOT).as_posix())
        needed.update({materials_model.CORRECTION, materials_model.PER_SPECIMEN, *materials_model.CAMPAIGNS.values()})
        needed.update(p.relative_to(ROOT).as_posix() for p in (ROOT / "docs" / "registrations").glob("*.json"))
        self.assertEqual(sorted(needed - self.shipped), [])

    def test_only_small_reference_files_are_shipped(self):
        for relative in self.shipped:
            self.assertIn(PurePosixPath(relative).suffix.lower(), self.build.DOC_SUFFIXES, relative)
            self.assertTrue(relative.startswith("docs/"), relative)
            self.assertIsNone(self.build.PACKAGE_FILE.match(PurePosixPath(relative).name), relative)

    def test_measurement_fe_solver_and_package_files_are_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "_internal" / "numpy").mkdir(parents=True)
            (root / "_internal" / "numpy" / "table.dat").write_bytes(b"library data")
            (root / "_internal" / "numpy" / "sample.npz").write_bytes(b"library sample data")  # as matplotlib's
            (root / "_internal" / "lib").mkdir()
            (root / "_internal" / "lib" / "manifest.json").write_text("{}", encoding="utf-8")  # a library's own
            (root / "docs").mkdir()
            (root / "docs" / "ok.json").write_text("{}", encoding="utf-8")
            self.build.check_contents(root)
            for name in ("model.odb", "test.unv", "test.uff", "project.lms", "model.inp", "job.sta", "job.dat",
                         "manifest.json", "geometry.csv", "mode_0017.csv", "pack.npz"):
                bad = root / "docs" / "package" / name
                bad.parent.mkdir(exist_ok=True)
                bad.write_bytes(b"x")
                with self.subTest(name=name), self.assertRaises(SystemExit):
                    self.build.check_contents(root)
                bad.unlink()

    def test_the_research_results_load_from_another_folder(self):
        with tempfile.TemporaryDirectory(prefix="RC2 other folder ") as folder:
            copied = self.build.copy_documents(Path(folder))
            self.assertTrue(copied)
            result = self.build.check_research(Path(folder))
        self.assertEqual(result["matching_rows"], {"PLATE": 11, "SP-13": 12, "SP-10": 12})
        self.assertEqual(result["scenarios"], ["S0", "H1", "H2"])
        sp10 = result["sp10_priority6"]
        self.assertEqual((sp10["fe_mode_count"], sp10["fe_modes"], sp10["diagnostic_rows"]), (19, [7, 25], 12))
        self.assertEqual(sp10["exp11_exp12"], ["EXP11 FE17 +0.98 %", "EXP12 FE18 +0.11 %"])

    def test_rc1_is_unchanged_and_never_overwritten(self):
        rc1 = ROOT / "packaging" / "portable_rc1"
        for name, expected in RC1_FILES.items():
            data = (rc1 / name).read_bytes().replace(b"\r\n", b"\n")
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected, name)
        self.assertEqual(self.build.PROTECTED_DESKTOP, ("AbaqusModalComparator_RC1", "AbaqusModalComparator_RC1.zip"))
        self.assertNotIn(self.build.NAME, self.build.PROTECTED_DESKTOP)


if __name__ == "__main__":
    unittest.main()
