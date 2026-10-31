"""WINDOWS PORTABLE RC3-F1: the corrected build is made apart from RC3 (no PyInstaller needed to run these tests).

- its name is AbaqusModalComparator_RC3_F1 and it never writes the RC1, RC2 or RC3 desktop copies;
- the RC1, RC2 and RC3 packaging are unchanged;
- the reference files copied to another folder give the research results and the synthetic demonstration runs there.
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / "packaging" / "portable_rc3_f1"
sys.path.insert(0, str(ROOT / "src"))

UNCHANGED = {  # SHA-256 (LF) of the RC1, RC2 and RC3 packaging at 8da0521
    "portable_rc1/AbaqusModalComparator_RC1.spec": "6fa841ee8fb260dcb7913402f9c9363897cd3a49edec123b0873c3a7a77b68c6",
    "portable_rc1/build_portable.py": "678fcb21ee6baad666c678dda3dcc2d2a5b1028a10a275af75a5201c7c0950c6",
    "portable_rc2/AbaqusModalComparator_RC2.spec": "b832b519692299a187e43116d9c5cd35ddaa4e8550d00fd2f446ad968af11d56",
    "portable_rc2/build_portable.py": "09e0d219c85cd2c61b83cfb5a40c4a4876d977f578ba3868900a326d5ba45e06",
    "portable_rc3/AbaqusModalComparator_RC3.spec": "88b68b36594dbe9d18941190c96b6ecfd27bca1c734e211dc114df8d9127c81d",
    "portable_rc3/build_portable.py": "99511fdecc93de41c59efa5764ce9eb111d1dcc91eace73f077e26d34352a195",
    "portable_rc3/launch_new_gui.py": "063d9f97be9cc19c4fe14dd7a489607aaf9d0648357c2bc294a51db4aba02b7c",
    "portable_rc3/requirements-build.txt": "af07fc8af05f7576f85c2455d127d60e54e88e5f69ff57dcc5a7ac04f33d6efd",
    "portable_rc3/rthook_open_audit.py": "93cbafcdce13ac7477eb3a38bfad9dbb327a6beacb87cae8e9bba10805b29a0a",
}


def _build_module():
    spec = importlib.util.spec_from_file_location("build_portable_rc3_f1", PACKAGING / "build_portable.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PortableRc3F1PackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = _build_module()

    def test_a_separate_build_that_never_writes_the_earlier_ones(self):
        self.assertEqual(self.build.NAME, "AbaqusModalComparator_RC3_F1")
        self.assertIn('name="AbaqusModalComparator_RC3_F1"', (PACKAGING / "AbaqusModalComparator_RC3_F1.spec")
                      .read_text(encoding="utf-8"))
        self.assertEqual(set(self.build.PROTECTED_DESKTOP), {
            f"AbaqusModalComparator_{name}{suffix}" for name in ("RC1", "RC2", "RC3") for suffix in ("", ".zip")})
        self.assertNotIn(self.build.NAME, self.build.PROTECTED_DESKTOP)

    def test_rc1_rc2_rc3_packaging_unchanged(self):
        for relative, expected in UNCHANGED.items():
            data = (ROOT / "packaging" / relative).read_bytes().replace(b"\r\n", b"\n")
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected, relative)

    def test_the_results_and_the_demonstration_run_from_another_folder(self):
        with tempfile.TemporaryDirectory(prefix="RC3 F1 other folder ") as folder:
            self.build.copy_documents(Path(folder))
            result = self.build.check_research(Path(folder))
        self.assertEqual(result["matching_rows"], {"PLATE": 11, "SP-13": 12, "SP-10": 12})
        self.assertEqual(result["single_plate_demo"]["lm"], "CONVERGED")


if __name__ == "__main__":
    unittest.main()
