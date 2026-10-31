"""WINDOWS PORTABLE RC3: the packaging stays in step with the program (no PyInstaller needed to run these tests).

- the report layers, the Research Results services and the single-plate workbench services are hidden imports;
- every reference file the interface reads, the PRIORITY-6 records and the synthetic single-plate demonstration
  included, is among the files put beside the portable program;
- measurement, FE model, solver and extracted FE package files are refused;
- the reference files copied to another folder give the same research results and the demonstration runs there;
- the RC1 and RC2 packaging are unchanged, and the RC3 build never writes the RC1 / RC2 desktop copies.
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
PACKAGING = ROOT / "packaging" / "portable_rc3"
sys.path.insert(0, str(ROOT / "src"))

from new_gui import report_export  # noqa: E402
from services import research_results_reader as rr  # noqa: E402
from services import sp10_fe_research as sf  # noqa: E402

UNCHANGED = {  # SHA-256 (LF) of the RC1 and RC2 packaging at 939adc3
    "portable_rc1/AbaqusModalComparator_RC1.spec": "6fa841ee8fb260dcb7913402f9c9363897cd3a49edec123b0873c3a7a77b68c6",
    "portable_rc1/build_portable.py": "678fcb21ee6baad666c678dda3dcc2d2a5b1028a10a275af75a5201c7c0950c6",
    "portable_rc1/launch_new_gui.py": "22e45629fd671a2d3d71e1de65c5dbe23ac1964bf55fda8d420aee7ae4669792",
    "portable_rc1/requirements-build.txt": "744d85c94bd61f92968088609ddb52cf8bdf541db7dc97270c16367eb562d7db",
    "portable_rc1/rthook_open_audit.py": "0d7f6ae051bd05313ac67aa481cec4c016b31bd09a45d469677bb21cce669c0c",
    "portable_rc2/AbaqusModalComparator_RC2.spec": "b832b519692299a187e43116d9c5cd35ddaa4e8550d00fd2f446ad968af11d56",
    "portable_rc2/build_portable.py": "09e0d219c85cd2c61b83cfb5a40c4a4876d977f578ba3868900a326d5ba45e06",
    "portable_rc2/launch_new_gui.py": "b19ccbd30c00faf57df966cba8eeb211b87032be64288bfe31f1099f81862810",
    "portable_rc2/requirements-build.txt": "2cd98f1a55916f130720782a379c39b88e0e681f58edaaf9e6bd6dc01251bdc5",
    "portable_rc2/rthook_open_audit.py": "2c1f70ed0aea33426a641026a00ab069368c49a94d432ea87341b51a86179ff0",
}
DEMO_FILES = ("DEMO_STUDY.json", "DEMO_SYNTHETIC_INPUTS.json", "DEMO_SENSITIVITIES.json", "DEMO_DECLARATION.json",
              "DEMO_DECLARATION_TWO_ROWS.json")


def _build_module():
    spec = importlib.util.spec_from_file_location("build_portable_rc3", PACKAGING / "build_portable.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _spec_list(name: str) -> list:
    tree = ast.parse((PACKAGING / "AbaqusModalComparator_RC3.spec").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} is not in the spec")


class PortableRc3PackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = _build_module()
        cls.shipped = set(cls.build.tracked_documents())

    def test_the_names_and_the_hidden_imports(self):
        self.assertEqual((self.build.NAME, self.build.EXE), ("AbaqusModalComparator_RC3", "AbaqusModalComparator.exe"))
        hidden = set(_spec_list("REPORT_LAYERS"))
        for module_name, _function in report_export.REPORT_LAYERS:
            self.assertIn(module_name, hidden)
        self.assertEqual(set(_spec_list("RESEARCH_SERVICES")), {
            "services.research_results_reader", "services.sp10_fe_research", "services.generic_plate_workbench",
            "services.generic_plate_evidence", "services.generic_plate_offline_study"})

    def test_the_reference_files_and_the_demonstration_are_shipped(self):
        needed = {relative for relative, _sha, _commit in rr.SNAPSHOT_FILES.values()}
        needed.update(relative for relative, _sha, _commit in sf.ARCHIVE_FILES.values())
        needed.update(f"docs/examples/generic_single_plate_demo/{name}" for name in DEMO_FILES)
        self.assertEqual(sorted(needed - self.shipped), [])
        for relative in self.shipped:
            self.assertIsNone(self.build.PACKAGE_FILE.match(PurePosixPath(relative).name), relative)

    def test_measurement_fe_solver_and_package_files_are_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "_internal" / "lib").mkdir(parents=True)
            (root / "_internal" / "lib" / "sample.npz").write_bytes(b"library sample")
            (root / "docs").mkdir()
            self.build.check_contents(root)
            for name in ("model.odb", "test.unv", "test.uff", "model.inp", "job.dat", "manifest.json", "geometry.csv",
                         "mode_0007.csv", "pack.npz"):
                bad = root / "docs" / name
                bad.write_bytes(b"x")
                with self.subTest(name=name), self.assertRaises(SystemExit):
                    self.build.check_contents(root)
                bad.unlink()

    def test_the_results_and_the_demonstration_run_from_another_folder(self):
        with tempfile.TemporaryDirectory(prefix="RC3 other folder ") as folder:
            self.build.copy_documents(Path(folder))
            result = self.build.check_research(Path(folder))
        self.assertEqual(result["matching_rows"], {"PLATE": 11, "SP-13": 12, "SP-10": 12})
        demo = result["single_plate_demo"]
        self.assertEqual((demo["specimen"], demo["evidence"], demo["lm"]),
                         ("DEMO-SPB-420x260", "EVIDENCE_COMPLETE_NOT_FROZEN", "CONVERGED"))
        self.assertEqual(demo["labels"], ["DIAGNOSTIC_OPTIMIZER_CANDIDATE", "NOT_A_RELEASE_VALUE",
                                          "NOT_A_MATERIAL_PROPERTY"])

    def test_rc1_and_rc2_are_unchanged_and_never_overwritten(self):
        for relative, expected in UNCHANGED.items():
            data = (ROOT / "packaging" / relative).read_bytes().replace(b"\r\n", b"\n")
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected, relative)
        self.assertEqual(set(self.build.PROTECTED_DESKTOP), {"AbaqusModalComparator_RC1", "AbaqusModalComparator_RC1.zip",
                                                             "AbaqusModalComparator_RC2",
                                                             "AbaqusModalComparator_RC2.zip"})


if __name__ == "__main__":
    unittest.main()
