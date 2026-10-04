"""M3 universal forward builder: material location, generic rewrite, provenance (synthetic, no Abaqus)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import hashlib
import tempfile

from domain.forward_model_manifest import (
    CARBON_PROPERTY_SET_V1,
    EngineeringConstants,
    ForwardCandidate,
    carbon_candidate,
)
from m3_support import CARBON_DATA, FREQUENCY_DATA, SOURCE_CONSTANTS, SYNTHETIC_INP, synthetic_model
from services.forward_builder import (
    ForwardBuildError,
    locate_engineering_constants,
    render_forward_input,
    rewrite_engineering_constants,
    split_inp_lines,
)
from services.shared_carbon_forward import (
    CarbonEngineeringConstants,
    SharedCarbonCandidate,
    SpecimenForwardBaseline,
    write_forward_job_inp,
)


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


def carbon_record(text: str) -> list[float]:
    return list(locate_engineering_constants(lines_of(text), "CFRP_Face").values.as_tuple())


class CandidateTests(unittest.TestCase):
    """M3.2: a candidate sets only the parameterisation's parameters."""

    def test_carbon_candidate_sets_e1_e2_and_g12_only(self):
        candidate = carbon_candidate(48000.0, 3900.0)
        constants = candidate.engineering_constants()
        self.assertEqual((constants.E1, constants.E2, constants.G12), (48000.0, 48000.0, 3900.0))
        for name, value in CARBON_PROPERTY_SET_V1.fixed_constants.items():
            self.assertEqual(getattr(constants, name), value)
        self.assertEqual(candidate.to_dict(), {"E_in_plane_mpa": 48000.0, "G12_mpa": 3900.0})
        self.assertEqual(CARBON_PROPERTY_SET_V1.variable_constants, ("E1", "E2", "G12"))

    def test_candidate_validation(self):
        for bad in (float("nan"), float("inf"), 0.0, -1.0, True, "52000"):
            with self.subTest(bad=bad), self.assertRaises((TypeError, ValueError)):
                carbon_candidate(bad, 4500.0)
            with self.subTest(bad=bad), self.assertRaises((TypeError, ValueError)):
                carbon_candidate(52000.0, bad)
        with self.assertRaises(ValueError):  # fixed constants are not candidate fields
            ForwardCandidate.create("carbon-property-set/v1", E_in_plane_mpa=1.0, G12_mpa=1.0, nu12=0.3)
        with self.assertRaises(ValueError):
            ForwardCandidate.create("carbon-property-set/v1", E_in_plane_mpa=1.0)
        with self.assertRaises(ValueError):
            ForwardCandidate.create("carbon-e1-e2/v0", E1=1.0, E2=2.0)


class GenericRewriteTests(unittest.TestCase):
    """M3.2: only E1/E2/G12 of the located record and the eigenvalue request change."""

    def render(self, candidate, text=SYNTHETIC_INP, **overrides):
        model, raw = synthetic_model(text, **overrides)
        rendered = render_forward_input(model, candidate, raw)
        return rendered, rendered.content.decode("latin-1")

    def test_only_variable_constants_change(self):
        rendered, text = self.render(carbon_candidate(48000.0, 3900.0))
        record = carbon_record(text)
        self.assertEqual(record[0:2], [48000.0, 48000.0])
        self.assertEqual(record[6], 3900.0)
        self.assertEqual([record[2], record[3], record[4], record[5], record[7], record[8]],
                         [6700.0, 0.05, 0.3, 0.3, 2200.0, 2200.0])
        self.assertEqual(rendered.engineering_constants.G12, 3900.0)

    def test_only_authorised_lines_change(self):
        source = SYNTHETIC_INP.splitlines(keepends=True)
        for candidate in (carbon_candidate(52000.0, 4500.0), carbon_candidate(41000.0, 3700.0)):
            rendered, text = self.render(candidate)
            generated = text.splitlines(keepends=True)
            self.assertEqual(len(generated), len(source))
            changed = {i for i, (a, b) in enumerate(zip(source, generated)) if a != b}
            allowed = {source.index(line) for line in CARBON_DATA} | {source.index(FREQUENCY_DATA)}
            self.assertTrue(changed <= allowed)
            self.assertEqual(set(rendered.changed_lines), changed)
            for kept in (" 1.57e-09,\n", " 1.0475e-09,\n", " 1.2e-09,\n", " 1800., 0.38\n", "3.32e-05,\n",
                         "2580.,2580.,2060., 0.33, 0.33, 0.33, 970., 850.\n", " 850.,\n",
                         "1, 1, 2, 3, 4, 5, 6, 7, 8\n", "s_Surf-3, m_Surf-3\n"):
                self.assertIn(kept, generated)  # density, adhesive, NSM, core, mesh, ties

    def test_eigenvalue_request(self):
        _, text = self.render(carbon_candidate(52000.0, 4500.0))
        self.assertIn("30, , , , ,\n", text)
        self.assertNotIn(FREQUENCY_DATA, text)
        same = SYNTHETIC_INP.replace(FREQUENCY_DATA, "30, , , , ,\n")
        rendered, text = self.render(carbon_candidate(52000.0, 4500.0), same,
                                     frequency_request__source_eigenvalue_count=30)
        self.assertIn("30, , , , ,\n", text)
        record_lines = set(locate_engineering_constants(lines_of(same), "CFRP_Face").data_lines)
        self.assertTrue(set(rendered.changed_lines) <= record_lines)

    def test_source_disagreement_is_refused(self):
        model, raw = synthetic_model()
        with self.assertRaises(ForwardBuildError):  # bytes differ from the pinned SHA-256
            render_forward_input(model, carbon_candidate(52000.0, 4500.0), raw + b"\n")
        with self.assertRaises(ForwardBuildError):  # INP constants differ from the manifest
            self.render(carbon_candidate(52000.0, 4500.0), SYNTHETIC_INP.replace("4500., 2200.", "4400., 2200."))
        with self.assertRaises(ForwardBuildError):  # eigenvalue request differs from the manifest
            self.render(carbon_candidate(52000.0, 4500.0), frequency_request__source_eigenvalue_count=20)
        with self.assertRaises(ForwardBuildError):  # two *Frequency requests
            self.render(carbon_candidate(52000.0, 4500.0),
                        SYNTHETIC_INP + "*Step, name=Second\n*Frequency\n10,\n*End Step\n")
        with self.assertRaises(ForwardBuildError):  # the material named by the passport is absent
            self.render(carbon_candidate(52000.0, 4500.0), SYNTHETIC_INP.replace("name=CFRP_Face\n", "name=X\n"))

    def test_candidate_of_another_parameterisation_is_refused(self):
        model, raw = synthetic_model()
        with self.assertRaises(ForwardBuildError):
            render_forward_input(model, ForwardCandidate("other/v1", (("E1", 1.0),)), raw)

    def test_a_fixed_constant_can_never_be_rewritten(self):
        lines = lines_of(SYNTHETIC_INP)
        record = locate_engineering_constants(lines, "CFRP_Face")
        changed = EngineeringConstants(**(record.values.to_dict() | {"nu12": 0.3}))
        with self.assertRaises(ForwardBuildError):
            rewrite_engineering_constants(lines, record, changed, ("E1", "E2", "G12"))

    def test_deterministic(self):
        first, _ = self.render(carbon_candidate(49000.0, 4400.0))
        second, _ = self.render(carbon_candidate(49000.0, 4400.0))
        self.assertEqual(first.content, second.content)
        third, _ = self.render(carbon_candidate(49000.0, 4400.5))
        self.assertNotEqual(third.sha256, first.sha256)


ORACLE_VARIANTS = {
    "lf": SYNTHETIC_INP,
    "crlf": SYNTHETIC_INP.replace("\n", "\r\n"),
    "comment_in_record": SYNTHETIC_INP.replace(" 2200.,\n", "** G23\n 2200.,\n"),
    "no_trailing_comma": SYNTHETIC_INP.replace(" 2200.,\n", " 2200.\n"),
    "trailing_spaces": SYNTHETIC_INP.replace(" 2200.,\n", " 2200.,   \n"),
    "single_line_record": SYNTHETIC_INP.replace("4500., 2200.\n 2200.,\n", "4500., 2200., 2200.\n"),
    "same_eigenvalue_request": SYNTHETIC_INP.replace(FREQUENCY_DATA, "30, , , , ,\n"),
    "lower_case_keywords": SYNTHETIC_INP.replace("*Elastic, type=ENGINEERING CONSTANTS\n52000.",
                                                 "*elastic, TYPE=engineering constants\n52000."),
}
ORACLE_CANDIDATES = ((52000.0, 4500.0), (49400.0, 4500.0), (54600.0, 4725.0), (48123.456789, 4011.1),
                     (1e5, 1e-3), (51999.99999999999, 4500.000000000001), (45000, 4000))


class OracleEquivalenceTests(unittest.TestCase):
    """M3.2: on synthetic inputs the generic rewrite is byte-identical to the accepted builder."""

    def test_byte_identical_to_the_shared_carbon_builder(self):
        with tempfile.TemporaryDirectory() as directory:
            for name, text in ORACLE_VARIANTS.items():
                raw = text.encode("latin-1")
                source = Path(directory) / f"{name}.inp"
                source.write_bytes(raw)
                count = 30 if name == "same_eigenvalue_request" else 15
                model, _ = synthetic_model(text, frequency_request__source_eigenvalue_count=count)
                baseline = SpecimenForwardBaseline(
                    specimen_id="SP-SYN", job_prefix="SYN", source_inp=source,
                    source_inp_sha256=hashlib.sha256(raw).hexdigest(), carbon_material_name="CFRP_Face",
                    source_engineering_constants=CarbonEngineeringConstants(**SOURCE_CONSTANTS),
                    source_eigenvalue_count=count, requested_eigenvalue_count=30, registration_hash="a" * 64)
                for e, g in ORACLE_CANDIDATES:
                    with self.subTest(variant=name, candidate=(e, g)):
                        oracle = write_forward_job_inp(baseline, SharedCarbonCandidate(e, g),
                                                       Path(directory) / "jobs")
                        rendered = render_forward_input(model, carbon_candidate(e, g), raw)
                        self.assertEqual(rendered.content, oracle.generated_inp.read_bytes())
                        self.assertEqual(rendered.sha256, oracle.generated_inp_sha256)
                        self.assertEqual(rendered.engineering_constants.to_dict(),
                                         oracle.engineering_constants.to_dict())


if __name__ == "__main__":
    unittest.main()
