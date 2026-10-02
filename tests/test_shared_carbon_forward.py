"""CARBON-4B: deterministic shared-carbon forward-job construction (no Abaqus)."""

from pathlib import Path
import hashlib
import math
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from services.shared_carbon_forward import (
    CARBON_PROPERTY_SET_V1_FIXED,
    CarbonEngineeringConstants,
    ForwardJobPreparationError,
    SP02_REGISTRATION_HASH,
    SP13_REGISTRATION_HASH,
    SharedCarbonCandidate,
    SpecimenForwardBaseline,
    prepare_shared_carbon_jobs,
    sp02_forward_baseline,
    sp13_forward_baseline,
    write_forward_job_inp,
)


SOURCE_CONSTANTS = CarbonEngineeringConstants(
    E1=52000.0, E2=52000.0, E3=6700.0, nu12=0.05, nu13=0.3, nu23=0.3,
    G12=4500.0, G13=2200.0, G23=2200.0,
)

SYNTHETIC_INP = """*Heading
** Job name: SYN Model name: Model-1
*Part, name=Face
*Node
      1,           0.,           0.,           0.
      2,           3.,           0.,           0.
      3,           3.,           3.,           0.
      4,           0.,           3.,           0.
      5,           0.,           0.,        0.45
      6,           3.,           0.,        0.45
      7,           3.,           3.,        0.45
      8,           0.,           3.,        0.45
*Element, type=C3D8I
1, 1, 2, 3, 4, 5, 6, 7, 8
*Elset, elset=Set-1, generate
 1, 1, 1
*Orientation, name=Ori-1
          1.,           0.,           0.,           0.,           1.,           0.
3, 0.
*Solid Section, elset=Set-1, orientation=Ori-1, material=CFRP_Face
,
*Nonstructural Mass, elset=Set-1, units=TOTAL MASS, distribution=VOLUME PROPORTIONAL
3.32e-05,
*End Part
*Assembly, name=Assembly
*Instance, name=Face-1, part=Face
*End Instance
*Tie, name=T, adjust=yes, type=SURFACE TO SURFACE
s_Surf-3, m_Surf-3
*End Assembly
**
** MATERIALS
**
*Material, name=CFRP_Face
*Density
 1.57e-09,
*Elastic, type=ENGINEERING CONSTANTS
52000.,52000., 6700.,  0.05,   0.3,   0.3, 4500., 2200.
 2200.,
*Material, name=Core_PLA
*Density
 1.0475e-09,
*Elastic, type=ENGINEERING CONSTANTS
2580.,2580.,2060., 0.33, 0.33, 0.33, 970., 850.
 850.,
** ----------------------------------------------------------------
*Step, name=Modal, nlgeom=NO, perturbation
*Frequency, eigensolver=Lanczos, sim, acoustic coupling=on, normalization=mass
15, , , , ,
*End Step
"""

CARBON_DATA = (
    "52000.,52000., 6700.,  0.05,   0.3,   0.3, 4500., 2200.\n",
    " 2200.,\n",
)
FREQUENCY_DATA = "15, , , , ,\n"


def _floats(line: str) -> list[float]:
    return [float(token) for token in line.strip().replace(" ", "").split(",") if token]


class SharedCarbonForwardTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp())
        self.source = self.directory / "source.inp"
        self.source.write_bytes(SYNTHETIC_INP.encode("latin-1"))
        self.output = self.directory / "jobs"

    def baseline(self, **changes):
        values = dict(
            specimen_id="SP-SYN",
            job_prefix="SPSYN",
            source_inp=self.source,
            source_inp_sha256=hashlib.sha256(self.source.read_bytes()).hexdigest(),
            carbon_material_name="CFRP_Face",
            source_engineering_constants=SOURCE_CONSTANTS,
            source_eigenvalue_count=15,
            requested_eigenvalue_count=30,
            registration_hash="a" * 64,
        )
        values.update(changes)
        return SpecimenForwardBaseline(**values)

    def generate(self, candidate, baseline=None):
        job = write_forward_job_inp(baseline or self.baseline(), candidate, self.output)
        return job, job.generated_inp.read_bytes().decode("latin-1")

    def carbon_record(self, text):
        lines = text.splitlines(keepends=True)
        start = lines.index("*Material, name=CFRP_Face\n")
        elastic = lines.index("*Elastic, type=ENGINEERING CONSTANTS\n", start)
        return _floats(lines[elastic + 1]) + _floats(lines[elastic + 2])

    # A, B, C, D
    def test_in_plane_moduli_are_equal_and_g12_independent(self):
        _, text = self.generate(SharedCarbonCandidate(e_in_plane_mpa=48000.0, g12_mpa=3900.0))
        record = self.carbon_record(text)
        self.assertEqual(record[0], 48000.0)
        self.assertEqual(record[1], 48000.0)
        self.assertEqual(record[6], 3900.0)
        _, other = self.generate(SharedCarbonCandidate(e_in_plane_mpa=48000.0, g12_mpa=4100.0))
        self.assertEqual(self.carbon_record(other)[:6], record[:6])
        self.assertEqual(self.carbon_record(other)[6], 4100.0)

    def test_fixed_constants_are_unchanged(self):
        _, text = self.generate(SharedCarbonCandidate(47000.0, 4300.0))
        record = self.carbon_record(text)
        self.assertEqual(record[3], 0.05)  # nu12
        self.assertEqual(
            [record[2], record[4], record[5], record[7], record[8]],
            [6700.0, 0.3, 0.3, 2200.0, 2200.0],
        )
        self.assertEqual(len(record), 9)

    def test_candidate_exposes_abaqus_constants_without_nu12_field(self):
        candidate = SharedCarbonCandidate(50000.0, 4200.0)
        constants = candidate.engineering_constants()
        self.assertEqual((constants.E1, constants.E2, constants.G12), (50000.0, 50000.0, 4200.0))
        self.assertEqual(constants.nu12, CARBON_PROPERTY_SET_V1_FIXED["nu12"])
        self.assertFalse(hasattr(candidate, "nu12"))

    def test_candidate_validation(self):
        for bad in (float("nan"), float("inf"), 0.0, -1.0, True):
            with self.subTest(bad=bad):
                with self.assertRaises((TypeError, ValueError)):
                    SharedCarbonCandidate(bad, 4500.0)
                with self.assertRaises((TypeError, ValueError)):
                    SharedCarbonCandidate(52000.0, bad)

    # E, F, G, H, K
    def test_only_carbon_record_and_frequency_lines_change(self):
        source_lines = SYNTHETIC_INP.splitlines(keepends=True)
        for candidate in (SharedCarbonCandidate(52000.0, 4500.0), SharedCarbonCandidate(41000.0, 3700.0)):
            _, text = self.generate(candidate)
            generated = text.splitlines(keepends=True)
            self.assertEqual(len(generated), len(source_lines))
            changed = [i for i, (a, b) in enumerate(zip(source_lines, generated)) if a != b]
            allowed = {source_lines.index(line) for line in CARBON_DATA} | {source_lines.index(FREQUENCY_DATA)}
            self.assertTrue(set(changed) <= allowed, [source_lines[i] for i in changed])
            for keyword in (" 1.57e-09,\n", " 1.0475e-09,\n", "3.32e-05,\n",
                            "2580.,2580.,2060., 0.33, 0.33, 0.33, 970., 850.\n", " 850.,\n",
                            "1, 1, 2, 3, 4, 5, 6, 7, 8\n", "s_Surf-3, m_Surf-3\n"):
                self.assertIn(keyword, generated)

    # I
    def test_requested_eigenvalue_count_is_written(self):
        _, text = self.generate(SharedCarbonCandidate(52000.0, 4500.0))
        self.assertIn("30, , , , ,\n", text)
        self.assertNotIn(FREQUENCY_DATA, text)

    def test_sp02_forward_baseline_requests_24_elastic_modes(self):
        baseline = sp02_forward_baseline()
        self.assertEqual(baseline.source_eigenvalue_count, 15)
        self.assertEqual(baseline.requested_eigenvalue_count, 30)
        self.assertEqual(baseline.elastic_mode_count, 24)
        self.assertEqual(baseline.registration_hash, SP02_REGISTRATION_HASH)

    # J
    def test_sp13_forward_baseline_keeps_accepted_headroom(self):
        baseline = sp13_forward_baseline()
        self.assertEqual(baseline.source_eigenvalue_count, 30)
        self.assertEqual(baseline.requested_eigenvalue_count, 30)
        self.assertEqual(baseline.elastic_mode_count, 24)
        self.assertEqual(baseline.registration_hash, SP13_REGISTRATION_HASH)

    def test_unchanged_frequency_request_leaves_its_line_untouched(self):
        source = SYNTHETIC_INP.replace(FREQUENCY_DATA, "30, , , , ,\n")
        self.source.write_bytes(source.encode("latin-1"))
        baseline = self.baseline(source_eigenvalue_count=30, source_inp_sha256=None)
        _, text = self.generate(SharedCarbonCandidate(52000.0, 4500.0), baseline)
        self.assertIn("30, , , , ,\n", text)

    # L
    def test_deterministic_job_and_provenance(self):
        first, text_a = self.generate(SharedCarbonCandidate(49000.0, 4400.0))
        second, text_b = self.generate(SharedCarbonCandidate(49000.0, 4400.0))
        self.assertEqual(text_a, text_b)
        self.assertEqual(first.generated_inp_sha256, second.generated_inp_sha256)
        self.assertEqual(first.provenance_hash, second.provenance_hash)
        self.assertEqual(first.generated_inp, second.generated_inp)
        third, _ = self.generate(SharedCarbonCandidate(49000.0, 4400.5))
        self.assertNotEqual(third.provenance_hash, first.provenance_hash)
        self.assertEqual(
            first.generated_inp_sha256,
            hashlib.sha256(first.generated_inp.read_bytes()).hexdigest(),
        )
        document = first.provenance
        self.assertEqual(document["specimen_id"], "SP-SYN")
        self.assertEqual(document["candidate"], {"E_in_plane_mpa": 49000.0, "G12_mpa": 4400.0})
        self.assertEqual(document["engineering_constants"]["E2"], 49000.0)
        self.assertEqual(document["requested_eigenvalue_count"], 30)
        self.assertNotIn("generated_inp_path", document)

    # M
    def test_missing_or_ambiguous_targets_fail_loudly(self):
        with self.assertRaises(ForwardJobPreparationError):
            self.generate(SharedCarbonCandidate(52000.0, 4500.0), self.baseline(carbon_material_name="Missing"))
        duplicated = SYNTHETIC_INP.replace("*Material, name=Core_PLA", "*Material, name=CFRP_Face")
        self.source.write_bytes(duplicated.encode("latin-1"))
        with self.assertRaises(ForwardJobPreparationError):
            self.generate(SharedCarbonCandidate(52000.0, 4500.0), self.baseline(source_inp_sha256=None))

    def test_unexpected_source_constants_fail_loudly(self):
        changed = SYNTHETIC_INP.replace(" 2200.,\n", " 2300.,\n")
        self.source.write_bytes(changed.encode("latin-1"))
        with self.assertRaises(ForwardJobPreparationError):
            self.generate(SharedCarbonCandidate(52000.0, 4500.0), self.baseline(source_inp_sha256=None))

    def test_unexpected_frequency_or_source_hash_fails_loudly(self):
        with self.assertRaises(ForwardJobPreparationError):
            self.generate(SharedCarbonCandidate(52000.0, 4500.0), self.baseline(source_eigenvalue_count=20))
        with self.assertRaises(ForwardJobPreparationError):
            self.generate(SharedCarbonCandidate(52000.0, 4500.0), self.baseline(source_inp_sha256="0" * 64))
        two_steps = SYNTHETIC_INP + "*Step, name=Second\n*Frequency\n10,\n*End Step\n"
        self.source.write_bytes(two_steps.encode("latin-1"))
        with self.assertRaises(ForwardJobPreparationError):
            self.generate(SharedCarbonCandidate(52000.0, 4500.0), self.baseline(source_inp_sha256=None))

    # N
    def test_prepared_evaluation_carries_both_specimens_and_registrations(self):
        other_source = self.directory / "other.inp"
        other_source.write_bytes(SYNTHETIC_INP.replace(FREQUENCY_DATA, "30, , , , ,\n").encode("latin-1"))
        baselines = (
            self.baseline(specimen_id="SP-A", job_prefix="SPA", registration_hash="b" * 64),
            self.baseline(specimen_id="SP-B", job_prefix="SPB", source_inp=other_source,
                          source_inp_sha256=None, source_eigenvalue_count=30, registration_hash="c" * 64),
        )
        candidate = SharedCarbonCandidate(51000.0, 4450.0)
        evaluation = prepare_shared_carbon_jobs(candidate, self.output, baselines=baselines)
        self.assertEqual([job.specimen_id for job in evaluation.jobs], ["SP-A", "SP-B"])
        self.assertEqual([job.registration_hash for job in evaluation.jobs], ["b" * 64, "c" * 64])
        self.assertTrue(all(job.candidate == candidate for job in evaluation.jobs))
        self.assertTrue(all(job.engineering_constants.E1 == 51000.0 for job in evaluation.jobs))
        self.assertEqual(len(evaluation.evaluation_hash), 64)
        again = prepare_shared_carbon_jobs(candidate, self.output, baselines=baselines)
        self.assertEqual(again.evaluation_hash, evaluation.evaluation_hash)

    def test_default_baselines_are_the_accepted_pair(self):
        sp02, sp13 = sp02_forward_baseline(), sp13_forward_baseline()
        self.assertEqual((sp02.specimen_id, sp13.specimen_id), ("SP-02", "SP-13"))
        self.assertEqual(sp02.carbon_material_name, "CFRP_T300_PlainWeave")
        self.assertEqual(sp13.carbon_material_name, "CFRP_Face")
        for baseline in (sp02, sp13):
            self.assertEqual(baseline.source_engineering_constants, SOURCE_CONSTANTS)
            self.assertTrue(math.isfinite(baseline.source_engineering_constants.G23))


if __name__ == "__main__":
    unittest.main()
