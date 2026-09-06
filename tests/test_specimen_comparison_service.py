from copy import deepcopy
from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain import InclusionStatus
from modal_core import (
    ComparisonResult,
    GeometryMatch,
    ModalDataset,
    ModePairResult,
)
from services import comparison_to_observations


def make_pair(
    abaqus_mode=2,
    experimental_mode=7,
    abaqus_frequency_hz=98.25,
    experimental_frequency_hz=100.0,
    frequency_error_percent=-1.75,
    mac=0.91,
    status="Excellent match",
):
    pair = ModePairResult(
        abaqus_mode=abaqus_mode,
        experimental_mode=experimental_mode,
        abaqus_frequency_hz=abaqus_frequency_hz,
        experimental_frequency_hz=experimental_frequency_hz,
        frequency_error_percent=frequency_error_percent,
        mac=mac,
        status=status,
        order_changed=False,
        mapped_points=2,
        abaqus_vector=np.array([[1.0 + 2.0j, 0.0, 0.0], [0.0, 1.0j, 0.0]]),
        experimental_vector=np.array([[2.0 + 1.0j, 0.0, 0.0], [0.0, 2.0j, 0.0]]),
        coordinates=np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
        node_ids=np.array([11, 12]),
    )
    pair.measured_dof_mask = np.array(
        [[True, False, False], [False, True, False]]
    )
    pair.measured_dof_count = 2
    pair.coverage_status = "accepted"
    pair.dof_coverage_fraction = 0.5
    pair.point_coverage_fraction = 1.0
    pair.spatial_coverage_fraction = 0.8
    return pair


def make_comparison(pairs):
    dataset = ModalDataset("fixture", Path("fixture.unv"), [])
    geometry = GeometryMatch(
        experimental_to_abaqus=np.array([0, 1]),
        distances=np.array([0.0, 0.01]),
        rotation=np.eye(3),
        coordinate_scale=1.0,
        translation=np.zeros(3),
        normalized_rms_distance=0.01,
        matched_fraction=1.0,
    )
    return ComparisonResult(
        abaqus=dataset,
        experimental=dataset,
        geometry=geometry,
        pairs=list(pairs),
        mac_matrix=np.array([[0.91]]),
        frequency_error_matrix=np.array([[-1.75]]),
        abaqus_mode_numbers=[pair.abaqus_mode for pair in pairs],
        experimental_mode_numbers=[pair.experimental_mode for pair in pairs],
        warnings=["fixture warning"],
        metadata={"quality": {"registration": "accepted"}},
    )


class SpecimenComparisonServiceTests(unittest.TestCase):
    def test_one_pair_becomes_one_observation_without_recalculation(self):
        pair = make_pair()
        observation = comparison_to_observations(
            make_comparison([pair]), "design-A", "SP-02", "run-1"
        )[0]

        self.assertEqual(observation.physical_specimen_id, "SP-02")
        self.assertEqual(observation.test_run_id, "run-1")
        self.assertEqual(observation.metadata["design_id"], "design-A")
        self.assertEqual(observation.fe_mode_id, pair.abaqus_mode)
        self.assertEqual(observation.experimental_mode_id, pair.experimental_mode)
        self.assertEqual(observation.fe_frequency_hz, pair.abaqus_frequency_hz)
        self.assertEqual(
            observation.experimental_frequency_hz, pair.experimental_frequency_hz
        )
        self.assertEqual(observation.mac, pair.mac)
        self.assertEqual(
            observation.metadata["frequency_error_percent"],
            pair.frequency_error_percent,
        )
        self.assertEqual(observation.inclusion_status, InclusionStatus.INCLUDED)

    def test_every_existing_pair_becomes_one_observation_in_source_order(self):
        pairs = [
            make_pair(),
            make_pair(3, 8, 121.0, 120.0, 0.8333333333333334, 0.84, "Good match"),
            make_pair(5, 10, 155.0, 150.0, 3.3333333333333335, 0.77, "Review"),
        ]
        observations = comparison_to_observations(
            make_comparison(pairs), "design-A", "SP-02", "run-1"
        )
        self.assertEqual(len(observations), len(pairs))
        self.assertEqual([item.fe_mode_id for item in observations], [2, 3, 5])
        self.assertEqual(
            [item.experimental_mode_id for item in observations], [7, 8, 10]
        )

    def test_review_decisions_are_mapped_without_new_numerical_rules(self):
        needs_review = make_pair(status="Review", mac=0.75)
        manually_accepted = make_pair(3, 8, status="Poor match", mac=0.55)
        manually_accepted.manual_decision = "accepted"
        manually_accepted.manual_comment = "Shape checked against test notes"
        rejected = make_pair(4, 9)
        rejected.manual_decision = "rejected"
        rejected.rejection_reasons = ["Sensor dropout"]
        downweighted = make_pair(5, 10, status="downweighted")

        observations = comparison_to_observations(
            make_comparison(
                [needs_review, manually_accepted, rejected, downweighted]
            ),
            "design-A",
            "SP-02",
            "run-1",
        )

        self.assertEqual(observations[0].inclusion_status, InclusionStatus.EXCLUDED)
        self.assertEqual(observations[1].inclusion_status, InclusionStatus.INCLUDED)
        self.assertIn("Shape checked", observations[1].reason)
        self.assertEqual(observations[2].inclusion_status, InclusionStatus.EXCLUDED)
        self.assertEqual(
            observations[2].metadata["source_pair"]["rejection_reasons"],
            ["Sensor dropout"],
        )
        self.assertEqual(
            observations[3].inclusion_status, InclusionStatus.DOWNWEIGHTED
        )

    def test_coverage_and_quality_metadata_are_preserved_but_vectors_are_not(self):
        pair = make_pair()
        pair.acceptance_reasons = ["MAC and frequency gates passed"]
        pair.quality_metadata = {"phase": "aligned", "score": 0.91}
        comparison = make_comparison([pair])
        observation = comparison_to_observations(
            comparison, "design-A", "SP-02", "run-1"
        )[0]
        source = observation.metadata["source_pair"]

        self.assertEqual(source["mapped_points"], 2)
        self.assertEqual(source["coverage_status"], "accepted")
        self.assertEqual(source["measured_dof_count"], 2)
        self.assertEqual(source["dof_coverage_fraction"], 0.5)
        self.assertEqual(source["acceptance_reasons"], ["MAC and frequency gates passed"])
        self.assertEqual(source["quality_metadata"]["phase"], "aligned")
        self.assertEqual(source["node_ids"], [11, 12])
        self.assertNotIn("abaqus_vector", source)
        self.assertNotIn("experimental_vector", source)
        self.assertEqual(
            observation.metadata["comparison_metadata"], comparison.metadata
        )
        self.assertEqual(
            observation.metadata["comparison_warnings"], comparison.warnings
        )

    def test_conversion_does_not_mutate_or_alias_comparison_metadata(self):
        pair = make_pair()
        comparison = make_comparison([pair])
        pair_snapshot = deepcopy(vars(pair))
        metadata_snapshot = deepcopy(comparison.metadata)
        warnings_snapshot = list(comparison.warnings)

        observation = comparison_to_observations(
            comparison, "design-A", "SP-02", "run-1"
        )[0]
        observation.metadata["comparison_metadata"]["quality"]["registration"] = "changed"
        observation.metadata["source_pair"]["coordinates"][0][0] = 99.0

        self.assertEqual(comparison.metadata, metadata_snapshot)
        self.assertEqual(comparison.warnings, warnings_snapshot)
        self.assertEqual(vars(pair).keys(), pair_snapshot.keys())
        for name, original in pair_snapshot.items():
            current = getattr(pair, name)
            if isinstance(original, np.ndarray):
                np.testing.assert_array_equal(current, original)
            else:
                self.assertEqual(current, original)


if __name__ == "__main__":
    unittest.main()
