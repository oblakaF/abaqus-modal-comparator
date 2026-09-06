import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain import (
    CoreFamily,
    Design,
    FaceSectionFamily,
    IdentificationCampaign,
    IdentificationParameter,
    InclusionStatus,
    InterfaceFamily,
    ModalCluster,
    ModalObservation,
    ObservationUncertainty,
    ParameterPrior,
    ParameterResultStatus,
    ParameterRole,
    ParameterScope,
    PhysicalSpecimen,
    PrimaryMeasurement,
    TestRun,
)


def measurements(mass: float):
    return (
        PrimaryMeasurement("m", mass, 0.001, "kg"),
        PrimaryMeasurement("L", 0.300, 0.0002, "m"),
        PrimaryMeasurement("W", 0.300, 0.0002, "m"),
        PrimaryMeasurement("h_face", 0.00045, 0.00001, "m"),
        PrimaryMeasurement("H_total", 0.00286, 0.00002, "m"),
    )


class InverseIdentificationDomainTests(unittest.TestCase):
    def build_campaign(self):
        face = FaceSectionFamily("face_plain_045", "Plain weave 0.45 mm")
        core = CoreFamily("core_pla_honeycomb", "PLA honeycomb")
        interface = InterfaceFamily("interface_2216", "3M 2216")
        design = Design(
            "design_sp02_sp10",
            face.face_section_family_id,
            core.core_family_id,
            interface.interface_family_id,
            nominal_geometry={"length": 0.3, "width": 0.3},
        )
        sp02 = PhysicalSpecimen("SP-02", design.design_id, measurements(0.5884))
        sp10 = PhysicalSpecimen("SP-10", design.design_id, measurements(0.5910))
        runs = (
            TestRun("SP-02-run-1", sp02.physical_specimen_id),
            TestRun("SP-02-run-2", sp02.physical_specimen_id),
            TestRun("SP-10-run-1", sp10.physical_specimen_id),
        )
        global_parameter = IdentificationParameter(
            "face_A11",
            ParameterScope.GLOBAL,
            ParameterRole.FITTED,
            initial_value=1.0e7,
            prior=ParameterPrior(1.0e7, 1.0e6),
            lower_bound=1.0,
            transformation="log",
            result_status=ParameterResultStatus.WEAKLY_IDENTIFIABLE,
        )
        nuisance = IdentificationParameter(
            "SP-02_mass",
            ParameterScope.SPECIMEN,
            ParameterRole.FITTED,
            physical_specimen_id="SP-02",
            initial_value=0.5884,
            prior=ParameterPrior(0.5884, 0.001),
            lower_bound=0.0,
            transformation="log",
        )
        observations = (
            ModalObservation(
                "obs-02-6",
                "SP-02",
                "SP-02-run-1",
                6,
                1,
                105.0,
                103.0,
                0.93,
                uncertainty=ObservationUncertainty(
                    measurement=0.002, setup=0.004, manufacturing=0.006
                ),
            ),
            ModalObservation(
                "obs-02-7",
                "SP-02",
                "SP-02-run-1",
                7,
                2,
                108.0,
                107.0,
                0.82,
                InclusionStatus.DOWNWEIGHTED,
                "Near-degenerate pair requires review.",
            ),
        )
        cluster = ModalCluster(
            "cluster-02-6-7",
            "SP-02",
            "SP-02-run-1",
            ("obs-02-6", "obs-02-7"),
        )
        return IdentificationCampaign(
            "PLA-joint-identification",
            face_section_families=(face,),
            core_families=(core,),
            interface_families=(interface,),
            designs=(design,),
            physical_specimens=(sp02, sp10),
            test_runs=runs,
            parameters=(global_parameter, nuisance),
            observations=observations,
            modal_clusters=(cluster,),
            active_global_parameter_ids_by_specimen={
                "SP-02": ("face_A11",),
                "SP-10": ("face_A11",),
            },
        )

    def test_campaign_models_manufacturing_repeat_and_retests(self):
        campaign = self.build_campaign()
        self.assertEqual(len(campaign.physical_specimens), 2)
        self.assertEqual(
            {specimen.design_id for specimen in campaign.physical_specimens},
            {"design_sp02_sp10"},
        )
        self.assertEqual(
            [run.physical_specimen_id for run in campaign.test_runs].count("SP-02"),
            2,
        )
        self.assertNotEqual(
            campaign.physical_specimens[0].physical_specimen_id,
            campaign.physical_specimens[1].physical_specimen_id,
        )

    def test_global_and_specimen_parameters_remain_distinct(self):
        campaign = self.build_campaign()
        global_parameter, nuisance = campaign.parameters
        self.assertEqual(global_parameter.scope, ParameterScope.GLOBAL)
        self.assertIsNone(global_parameter.physical_specimen_id)
        self.assertEqual(nuisance.scope, ParameterScope.SPECIMEN)
        self.assertEqual(nuisance.physical_specimen_id, "SP-02")
        self.assertEqual(
            campaign.active_global_parameter_ids_by_specimen["SP-10"],
            ("face_A11",),
        )
        self.assertIs(
            campaign.active_global_parameters_for("SP-02")[0], global_parameter
        )

    def test_areal_mass_and_face_offset_are_derived(self):
        specimen = self.build_campaign().physical_specimens[0]
        self.assertAlmostEqual(specimen.areal_mass, 0.5884 / (0.3 * 0.3))
        self.assertAlmostEqual(specimen.face_offset, (0.00286 - 0.00045) / 2.0)
        self.assertNotIn(
            "areal_mass", {item.name for item in specimen.primary_measurements}
        )
        self.assertNotIn("d", {item.name for item in specimen.primary_measurements})

    def test_cluster_counts_as_one_statistical_observation(self):
        cluster = self.build_campaign().modal_clusters[0]
        self.assertEqual(len(cluster.observation_ids), 2)
        self.assertEqual(cluster.effective_observation_count, 1)

    def test_campaign_serialization_round_trip(self):
        campaign = self.build_campaign()
        payload = json.loads(json.dumps(campaign.to_dict()))
        restored = IdentificationCampaign.from_dict(payload)
        self.assertEqual(restored.to_dict(), campaign.to_dict())
        self.assertEqual(restored.physical_specimens[0].areal_mass, campaign.physical_specimens[0].areal_mass)

    def test_invalid_primary_measurements_and_parameter_bounds_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "derived"):
            PrimaryMeasurement("areal_mass", 6.5, 0.1, "kg/m2")
        with self.assertRaisesRegex(ValueError, "uncertainty"):
            PrimaryMeasurement("m", 0.5, 0.0, "kg")
        with self.assertRaisesRegex(ValueError, "lower_bound"):
            IdentificationParameter(
                "bad",
                ParameterScope.GLOBAL,
                ParameterRole.FITTED,
                lower_bound=2.0,
                upper_bound=1.0,
            )

    def test_duplicate_and_unknown_references_are_rejected(self):
        campaign = self.build_campaign()
        with self.assertRaisesRegex(ValueError, "Duplicate physical_specimen_id"):
            IdentificationCampaign(
                "duplicates",
                face_section_families=campaign.face_section_families,
                core_families=campaign.core_families,
                interface_families=campaign.interface_families,
                designs=campaign.designs,
                physical_specimens=(
                    campaign.physical_specimens[0],
                    campaign.physical_specimens[0],
                ),
                active_global_parameter_ids_by_specimen={"SP-02": ()},
            )
        with self.assertRaisesRegex(ValueError, "unknown physical specimen"):
            IdentificationCampaign(
                "bad-run",
                test_runs=(TestRun("run-unknown", "SP-404"),),
            )
        with self.assertRaisesRegex(ValueError, "unknown design"):
            IdentificationCampaign(
                "bad-specimen",
                physical_specimens=(PhysicalSpecimen("SP-404", "D-404"),),
                active_global_parameter_ids_by_specimen={"SP-404": ()},
            )

    def test_mapping_rejects_unknown_and_specimen_parameters(self):
        campaign = self.build_campaign()
        with self.assertRaisesRegex(ValueError, "unknown or non-global"):
            IdentificationCampaign(
                "bad-mapping",
                face_section_families=campaign.face_section_families,
                core_families=campaign.core_families,
                interface_families=campaign.interface_families,
                designs=campaign.designs,
                physical_specimens=campaign.physical_specimens,
                test_runs=campaign.test_runs,
                parameters=campaign.parameters,
                active_global_parameter_ids_by_specimen={
                    "SP-02": ("SP-02_mass",),
                    "SP-10": ("face_A11",),
                },
            )


if __name__ == "__main__":
    unittest.main()
