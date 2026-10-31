"""WINDOWS PORTABLE RC3-F2: the corrected build is made apart from RC3-F1 (no PyInstaller needed to run these tests).

- its name is AbaqusModalComparator_RC3_F2 and it never writes the RC1, RC2, RC3 or RC3-F1 desktop copies;
- the RC1, RC2, RC3 and RC3-F1 packaging are unchanged;
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
PACKAGING = ROOT / "packaging" / "portable_rc3_f2"
sys.path.insert(0, str(ROOT / "src"))

UNCHANGED = {  # SHA-256 (LF) of the RC1, RC2, RC3 and RC3-F1 packaging at ad49498
    "portable_rc1/AbaqusModalComparator_RC1.spec": "6fa841ee8fb260dcb7913402f9c9363897cd3a49edec123b0873c3a7a77b68c6",
    "portable_rc1/build_portable.py": "678fcb21ee6baad666c678dda3dcc2d2a5b1028a10a275af75a5201c7c0950c6",
    "portable_rc2/AbaqusModalComparator_RC2.spec": "b832b519692299a187e43116d9c5cd35ddaa4e8550d00fd2f446ad968af11d56",
    "portable_rc2/build_portable.py": "09e0d219c85cd2c61b83cfb5a40c4a4876d977f578ba3868900a326d5ba45e06",
    "portable_rc3/AbaqusModalComparator_RC3.spec": "88b68b36594dbe9d18941190c96b6ecfd27bca1c734e211dc114df8d9127c81d",
    "portable_rc3/build_portable.py": "99511fdecc93de41c59efa5764ce9eb111d1dcc91eace73f077e26d34352a195",
    "portable_rc3_f1/AbaqusModalComparator_RC3_F1.spec":
        "c6182b36c90a1aaa9f118469f5842ae8b5871f241f3e1aca5ec2990752c9dd5c",
    "portable_rc3_f1/build_portable.py": "3217fe3d8a808280e0687bdf2cad1180461e22dba40804ab6cdff8837b794d7b",
    "portable_rc3_f1/launch_new_gui.py": "a3dd30426ec7d7ab2c698d0d44752e880ff3f23cb3943b37b450cc400450740e",
    "portable_rc3_f1/requirements-build.txt": "5a2f5df5bb44e5c34f70713dba7cfbde4ced9069c32d573af21f560a44f2b1aa",
    "portable_rc3_f1/rthook_open_audit.py": "ba62e13e2927cfc32339665678af37d2ea54cf3314bfbfaadfd218119e1984b1",
}


def _build_module():
    spec = importlib.util.spec_from_file_location("build_portable_rc3_f2", PACKAGING / "build_portable.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PortableRc3F2PackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = _build_module()

    def test_a_separate_build_that_never_writes_the_earlier_ones(self):
        self.assertEqual(self.build.NAME, "AbaqusModalComparator_RC3_F2")
        self.assertIn('name="AbaqusModalComparator_RC3_F2"', (PACKAGING / "AbaqusModalComparator_RC3_F2.spec")
                      .read_text(encoding="utf-8"))
        self.assertEqual(set(self.build.PROTECTED_DESKTOP), {
            f"AbaqusModalComparator_{name}{suffix}" for name in ("RC1", "RC2", "RC3", "RC3_F1")
            for suffix in ("", ".zip")})
        self.assertNotIn(self.build.NAME, self.build.PROTECTED_DESKTOP)

    def test_rc1_to_rc3_f1_packaging_unchanged(self):
        for relative, expected in UNCHANGED.items():
            data = (ROOT / "packaging" / relative).read_bytes().replace(b"\r\n", b"\n")
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected, relative)

    def test_the_results_and_the_demonstration_run_from_another_folder(self):
        with tempfile.TemporaryDirectory(prefix="RC3 F2 other folder ") as folder:
            self.build.copy_documents(Path(folder))
            result = self.build.check_research(Path(folder))
        self.assertEqual(result["matching_rows"], {"PLATE": 11, "SP-13": 12, "SP-10": 12})
        self.assertEqual(result["single_plate_demo"]["lm"], "CONVERGED")


if __name__ == "__main__":
    unittest.main()
