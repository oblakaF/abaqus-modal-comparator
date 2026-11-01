"""WINDOWS PORTABLE RC1: the packaging stays in step with the program (no PyInstaller needed to run these tests).

- every report layer that report_export installs by name is declared as a hidden import of the frozen program;
- every reference file the new interface reads at a repository-relative path is among the files put beside the
  portable program;
- the build refuses measurement, FE and solver files.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path, PurePosixPath
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / "packaging" / "portable_rc1"
sys.path.insert(0, str(ROOT / "src"))

from new_gui import known_sources, materials_model, report_export, workspace_state  # noqa: E402
from services import research_results_reader as rr  # noqa: E402


def _build_module():
    spec = importlib.util.spec_from_file_location("build_portable", PACKAGING / "build_portable.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _spec_list(name: str) -> list:
    tree = ast.parse((PACKAGING / "AbaqusModalComparator_RC1.spec").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} is not in the spec")


class PortablePackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = _build_module()
        cls.shipped = set(cls.build.tracked_documents())

    def test_the_report_layers_are_hidden_imports(self):
        hidden = set(_spec_list("REPORT_LAYERS"))
        self.assertIn("reporting", hidden)
        for module_name, _function in report_export.REPORT_LAYERS:
            self.assertIn(module_name, hidden)

    def test_the_reference_files_read_by_the_interface_are_shipped(self):
        needed = {relative for relative, _sha, _commit in rr.SNAPSHOT_FILES.values()}
        needed.add(known_sources.PROVENANCE.relative_to(known_sources.REPO_ROOT).as_posix())
        needed.add(workspace_state.STATUS_PATH.relative_to(ROOT).as_posix())
        needed.update({materials_model.CORRECTION, materials_model.PER_SPECIMEN, *materials_model.CAMPAIGNS.values()})
        needed.update(p.relative_to(ROOT).as_posix() for p in (ROOT / "docs" / "registrations").glob("*.json"))
        self.assertEqual(sorted(needed - self.shipped), [])

    def test_only_small_reference_files_are_shipped(self):
        self.assertTrue(self.shipped)
        for relative in self.shipped:
            self.assertIn(PurePosixPath(relative).suffix.lower(), self.build.DOC_SUFFIXES, relative)
            self.assertTrue(relative.startswith("docs/"), relative)

    def test_measurement_fe_and_solver_files_are_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "_internal" / "numpy").mkdir(parents=True)
            (root / "_internal" / "numpy" / "table.dat").write_bytes(b"library data")
            (root / "docs").mkdir()
            (root / "docs" / "ok.json").write_text("{}", encoding="utf-8")
            self.build.check_contents(root)  # a library's own .dat is not a solver file
            for name in ("model.odb", "test.unv", "test.uff", "project.lms", "model.inp", "job.sta"):
                bad = root / "docs" / name
                bad.write_bytes(b"x")
                with self.subTest(name=name), self.assertRaises(SystemExit):
                    self.build.check_contents(root)
                bad.unlink()
            (root / "docs" / "job.dat").write_bytes(b"x")
            with self.assertRaises(SystemExit):
                self.build.check_contents(root)


if __name__ == "__main__":
    unittest.main()
