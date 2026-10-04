"""M3 universal forward builder: material location, generic rewrite, provenance (synthetic, no Abaqus)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from m3_support import CARBON_DATA, SOURCE_CONSTANTS, SYNTHETIC_INP
from services.forward_builder import ForwardBuildError, locate_engineering_constants, split_inp_lines


def lines_of(text: str) -> list[str]:
    return split_inp_lines(text.encode("latin-1"))


class MaterialLocationTests(unittest.TestCase):
    """M3.1: the record is found by the passport material name, never by position or specimen."""

    def test_locates_the_named_record(self):
        lines = lines_of(SYNTHETIC_INP)
        record = locate_engineering_constants(lines, "CFRP_Face")
        self.assertEqual([lines[i] for i in record.data_lines], list(CARBON_DATA))
        self.assertEqual(record.values.to_dict(), SOURCE_CONSTANTS)
        self.assertEqual(lines[record.material_line], "*Material, name=CFRP_Face\n")
        self.assertEqual(lines[record.elastic_line], "*Elastic, type=ENGINEERING CONSTANTS\n")
        self.assertEqual(len(record.positions), 9)
        core = locate_engineering_constants(lines, "core_pla")  # names are case-insensitive, as in Abaqus
        self.assertEqual(core.values.E1, 2580.0)

    def test_comments_inside_the_record_are_skipped(self):
        text = SYNTHETIC_INP.replace(" 2200.,\n", "** G23 below\n 2200.,\n")
        record = locate_engineering_constants(lines_of(text), "CFRP_Face")
        self.assertEqual(record.values.G23, 2200.0)
        self.assertEqual(len(record.data_lines), 2)

    def test_line_endings_do_not_matter(self):
        record = locate_engineering_constants(lines_of(SYNTHETIC_INP.replace("\n", "\r\n")), "CFRP_Face")
        self.assertEqual(record.values.to_dict(), SOURCE_CONSTANTS)

    def test_missing_or_ambiguous_material_is_refused(self):
        with self.assertRaises(ForwardBuildError):
            locate_engineering_constants(lines_of(SYNTHETIC_INP), "Missing")
        duplicated = SYNTHETIC_INP.replace("*Material, name=Core_PLA", "*Material, name=CFRP_Face")
        with self.assertRaises(ForwardBuildError):
            locate_engineering_constants(lines_of(duplicated), "CFRP_Face")

    def test_wrong_or_repeated_elastic_option_is_refused(self):
        isotropic = SYNTHETIC_INP.replace("*Elastic, type=ENGINEERING CONSTANTS\n52000.", "*Elastic\n52000.", 1)
        with self.assertRaises(ForwardBuildError):
            locate_engineering_constants(lines_of(isotropic), "CFRP_Face")
        twice = SYNTHETIC_INP.replace(" 2200.,\n", " 2200.,\n*Elastic, type=ENGINEERING CONSTANTS\n1.,1.,1.,0.,0.,0.,1.,1.\n1.,\n")
        with self.assertRaises(ForwardBuildError):
            locate_engineering_constants(lines_of(twice), "CFRP_Face")
        none = SYNTHETIC_INP.replace("*Material, name=CFRP_Face\n*Density\n 1.57e-09,\n*Elastic, type=ENGINEERING CONSTANTS\n"
                                     + "".join(CARBON_DATA), "*Material, name=CFRP_Face\n*Density\n 1.57e-09,\n")
        with self.assertRaises(ForwardBuildError):
            locate_engineering_constants(lines_of(none), "CFRP_Face")

    def test_temperature_dependent_or_unreadable_record_is_refused(self):
        temperature = SYNTHETIC_INP.replace(" 2200.,\n", " 2200., 20.\n")
        with self.assertRaises(ForwardBuildError):
            locate_engineering_constants(lines_of(temperature), "CFRP_Face")
        unreadable = SYNTHETIC_INP.replace(" 2200.,\n", " abc,\n")
        with self.assertRaises(ForwardBuildError):
            locate_engineering_constants(lines_of(unreadable), "CFRP_Face")

    def test_split_and_join_are_lossless(self):
        from services.forward_builder import join_inp_lines

        for text in (SYNTHETIC_INP, SYNTHETIC_INP.replace("\n", "\r\n"), SYNTHETIC_INP + "no newline at end"):
            raw = text.encode("latin-1") + bytes([0xB0, 0x85, 0x0D, 0x0A])
            self.assertEqual(join_inp_lines(split_inp_lines(raw)), raw)


if __name__ == "__main__":
    unittest.main()
