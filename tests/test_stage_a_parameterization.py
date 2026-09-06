import math
from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from services.abaqus_shell_section import (
    SectionStiffnessBlock,
    StageAShellSectionConfiguration,
    TransverseShearStiffness,
    build_stage_a_shell_section,
    generate_stage_a_shell_general_section,
)
from services.stage_a_parameterization import (
    StageAParameterization,
    physical_to_unconstrained,
    unconstrained_to_physical,
    validate_balanced_d_matrix,
)


class StageAParameterizationTests(unittest.TestCase):
    def test_physical_transformed_physical_round_trip(self):
        original = StageAParameterization.from_physical(12.75, 4.125, -0.37)
        transformed = physical_to_unconstrained(*original.physical)
        restored = unconstrained_to_physical(*transformed)

        for restored_value, original_value in zip(restored, original.physical):
            self.assertAlmostEqual(restored_value, original_value)
        self.assertEqual(original.D11, original.D22)
        self.assertEqual(original.D12, original.r * original.D)
        self.assertGreater(original.D, 0.0)
        self.assertGreater(original.D66, 0.0)

    def test_result_is_immutable(self):
        point = StageAParameterization.from_physical(12.75, 4.125, -0.37)
        with self.assertRaises(FrozenInstanceError):
            point.D = 20.0

    def test_r_immediately_inside_each_limit_is_supported(self):
        for r in (math.nextafter(-1.0, 0.0), math.nextafter(1.0, 0.0)):
            transformed = physical_to_unconstrained(10.0, 3.0, r)
            restored = unconstrained_to_physical(*transformed)
            self.assertAlmostEqual(restored[2], r)

    def test_invalid_physical_values_are_rejected(self):
        for bad_d in (0.0, -1.0):
            with self.subTest(D=bad_d), self.assertRaisesRegex(ValueError, "positive"):
                StageAParameterization(bad_d, 1.0, 0.0)
        for bad_d66 in (0.0, -1.0):
            with self.subTest(D66=bad_d66), self.assertRaisesRegex(ValueError, "positive"):
                StageAParameterization(1.0, bad_d66, 0.0)
        for bad_r in (-1.01, -1.0, 1.0, 1.01):
            with self.subTest(r=bad_r), self.assertRaisesRegex(ValueError, r"\|r\| < 1"):
                StageAParameterization(1.0, 1.0, bad_r)

    def test_non_finite_physical_and_transformed_values_are_rejected(self):
        for bad in (math.nan, math.inf, -math.inf):
            for constructor in (
                lambda: StageAParameterization(bad, 1.0, 0.0),
                lambda: StageAParameterization(1.0, bad, 0.0),
                lambda: StageAParameterization(1.0, 1.0, bad),
                lambda: unconstrained_to_physical(bad, 0.0, 0.0),
                lambda: unconstrained_to_physical(0.0, bad, 0.0),
                lambda: unconstrained_to_physical(0.0, 0.0, bad),
            ):
                with self.subTest(value=bad, constructor=constructor), self.assertRaises(ValueError):
                    constructor()

    def test_balanced_matrix_validation_accepts_valid_matrix(self):
        validate_balanced_d_matrix(10.0, 10.0, 3.0, 2.0, r=0.3)

    def test_balanced_matrix_validation_rejects_relations_and_determinant(self):
        with self.assertRaisesRegex(ValueError, "D11 == D22"):
            validate_balanced_d_matrix(10.0, 9.0, 3.0, 2.0, r=0.3)
        with self.assertRaisesRegex(ValueError, r"D12 == r\*D11"):
            validate_balanced_d_matrix(10.0, 10.0, 2.0, 2.0, r=0.3)
        with self.assertRaisesRegex(ValueError, "determinant"):
            validate_balanced_d_matrix(10.0, 10.0, 10.0, 2.0)


class AbaqusStageAShellSectionTests(unittest.TestCase):
    def setUp(self):
        self.A = SectionStiffnessBlock(101.0, 12.0, 103.0, 14.0, 15.0, 106.0)
        self.shear = TransverseShearStiffness(71.0, 7.2, 73.0)
        self.config = StageAShellSectionConfiguration("FACE", self.A, self.shear)
        self.parameters = StageAParameterization(11.0, 6.0, 0.25)

    def test_representation_preserves_a_zeros_b_and_inserts_d_literally(self):
        section = build_stage_a_shell_section(self.parameters, self.config)

        self.assertEqual(section.A, self.A)
        self.assertEqual(section.B, SectionStiffnessBlock.zero())
        self.assertEqual(
            section.D,
            SectionStiffnessBlock(11.0, 2.75, 11.0, 0.0, 0.0, 6.0),
        )
        self.assertEqual(section.transverse_shear, self.shear)

    def test_packed_general_section_order_and_explicit_shear(self):
        section = build_stage_a_shell_section(self.parameters, self.config)
        self.assertEqual(section.section_stiffness_values[:6], self.A.abaqus_values)
        self.assertEqual(section.section_stiffness_values[6:12], (0.0,) * 6)
        self.assertEqual(
            section.section_stiffness_values[12:],
            (11.0, 2.75, 11.0, 0.0, 0.0, 6.0),
        )

        text = generate_stage_a_shell_general_section(self.parameters, self.config)
        self.assertIn("*SHELL GENERAL SECTION, ELSET=FACE\n", text)
        self.assertIn("*TRANSVERSE SHEAR STIFFNESS\n71, 7.2000000000000002, 73\n", text)

    def test_changing_d_changes_only_the_d_entries(self):
        first = build_stage_a_shell_section(self.parameters, self.config)
        changed = build_stage_a_shell_section(
            StageAParameterization(13.0, 8.0, -0.5), self.config
        )
        differing_indexes = {
            index
            for index, (left, right) in enumerate(
                zip(first.section_stiffness_values, changed.section_stiffness_values)
            )
            if left != right
        }
        self.assertEqual(differing_indexes, {12, 13, 14, 17})
        self.assertEqual(first.A, changed.A)
        self.assertEqual(first.B, changed.B)
        self.assertEqual(first.transverse_shear, changed.transverse_shear)

    def test_rendering_is_byte_deterministic_and_round_trip_precise(self):
        first = generate_stage_a_shell_general_section(self.parameters, self.config)
        second = generate_stage_a_shell_general_section(self.parameters, self.config)
        self.assertEqual(first.encode("ascii"), second.encode("ascii"))
        self.assertIn("2.75", first)
        self.assertNotIn("E=", first)
        self.assertNotIn("NU=", first)
        self.assertNotIn("G=", first)

    def test_stage_a_configuration_rejects_nonzero_b(self):
        with self.assertRaisesRegex(ValueError, "B block"):
            StageAShellSectionConfiguration(
                "FACE",
                self.A,
                self.shear,
                B=SectionStiffnessBlock(1.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            )


if __name__ == "__main__":
    unittest.main()
