from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmif_validation import _annotate_standard_mode, validate_close_mode_candidates
from modal_core import ModeShape


class ConservativeSvdValidationTests(unittest.TestCase):
    def setUp(self):
        x, y = np.meshgrid(np.linspace(-1.0, 1.0, 5), np.linspace(-1.0, 1.0, 5))
        self.coordinates = np.column_stack((x.ravel(), y.ravel(), np.zeros(x.size)))
        self.node_ids = np.arange(1, len(self.coordinates) + 1).astype(object)
        self.shape_1 = np.sin(np.pi * (x.ravel() + 1.0) / 2.0)
        self.shape_2 = np.sin(np.pi * (y.ravel() + 1.0) / 2.0)

    def mode(self, number, frequency, shape, source):
        vectors = np.zeros((len(self.coordinates), 3), dtype=complex)
        vectors[:, 2] = shape
        mode = ModeShape(
            number=number,
            frequency_hz=frequency,
            node_ids=self.node_ids,
            coordinates=self.coordinates,
            vectors=vectors,
            metadata={
                "dataset_type": 58,
                "mode_source": source,
                "close_mode_cluster_hz": [91.4, 92.2],
                "mean_coherence": 0.98,
            },
        )
        mask = np.zeros_like(vectors, dtype=bool)
        mask[:, 2] = True
        mode.measured_dofs = mask
        return mode

    def metadata(self, reference_count, second_ratio):
        return {
            "close_mode_separation": {
                "method": "test local SVD",
                "reference_count": reference_count,
                "added_mode_count": 1,
                "clusters": [
                    {
                        "cluster": [91.4, 92.2],
                        "cmif_max_second_to_first_singular_ratio": second_ratio,
                        "added_candidate_frequencies_hz": [91.8],
                    }
                ],
            }
        }

    def test_single_reference_candidate_is_diagnostic_only(self):
        base = self.mode(1, 91.7, self.shape_1, "FRF peak-derived experimental shape")
        candidate = self.mode(
            2,
            91.8,
            self.shape_2,
            "local response-matrix SVD close-mode candidate",
        )
        modes, metadata = validate_close_mode_candidates(
            [base, candidate], self.metadata(reference_count=1, second_ratio=0.25)
        )
        self.assertEqual(len(modes), 1)
        separation = metadata["close_mode_separation"]
        self.assertEqual(separation["added_mode_count"], 0)
        self.assertEqual(separation["rejected_mode_count"], 1)
        self.assertIn("single-reference", separation["rejected_candidates"][0]["reason"])

    def test_duplicate_multi_reference_candidate_is_rejected(self):
        base = self.mode(1, 91.7, self.shape_1, "FRF peak-derived experimental shape")
        candidate = self.mode(
            2,
            91.8,
            self.shape_1,
            "local response-matrix SVD close-mode candidate",
        )
        modes, metadata = validate_close_mode_candidates(
            [base, candidate], self.metadata(reference_count=2, second_ratio=0.25)
        )
        self.assertEqual(len(modes), 1)
        reason = metadata["close_mode_separation"]["rejected_candidates"][0]["reason"]
        self.assertIn("duplicate spatial shape", reason)

    def test_independent_multi_reference_candidate_can_be_accepted(self):
        base = self.mode(1, 91.7, self.shape_1, "FRF peak-derived experimental shape")
        candidate = self.mode(
            2,
            91.8,
            self.shape_2,
            "local response-matrix SVD close-mode candidate",
        )
        modes, metadata = validate_close_mode_candidates(
            [base, candidate], self.metadata(reference_count=2, second_ratio=0.25)
        )
        self.assertEqual(len(modes), 2)
        separation = metadata["close_mode_separation"]
        self.assertEqual(separation["added_mode_count"], 1)
        accepted = [mode for mode in modes if "SVD/CMIF" in mode.metadata.get("source_label", "")]
        self.assertEqual(len(accepted), 1)
        self.assertIn(accepted[0].metadata["confidence_label"], ("Medium", "High"))


class StandardModeConfidenceTests(unittest.TestCase):
    """ROADMAP Stage 2 #1: only genuinely computed coherence may raise an FRF
    peak's confidence; missing/unparsable coherence must not read as perfect."""

    def _mode(self, metadata):
        return ModeShape(
            number=1,
            frequency_hz=91.7,
            node_ids=np.array([1], dtype=object),
            coordinates=np.zeros((1, 3)),
            vectors=np.zeros((1, 3), dtype=complex),
            metadata=metadata,
        )

    def test_computed_high_coherence_yields_high_confidence(self):
        mode = self._mode(
            {
                "dataset_type": 58,
                "mode_source": "FRF peak-derived experimental shape",
                "mean_coherence": 0.98,
                "coherence_status": "computed",
            }
        )
        _annotate_standard_mode(mode)
        self.assertEqual(mode.metadata["confidence_label"], "High peak confidence")
        self.assertAlmostEqual(mode.metadata["confidence_score"], 0.98)

    def test_unavailable_coherence_does_not_yield_high_confidence(self):
        mode = self._mode(
            {
                "dataset_type": 58,
                "mode_source": "FRF peak-derived experimental shape",
                "mean_coherence": None,
                "coherence_status": "unavailable",
            }
        )
        _annotate_standard_mode(mode)
        self.assertNotIn("High", mode.metadata["confidence_label"])
        self.assertNotIn("Medium", mode.metadata["confidence_label"])
        self.assertEqual(mode.metadata["confidence_score"], 0.0)

    def test_parse_error_coherence_does_not_yield_high_confidence(self):
        mode = self._mode(
            {
                "dataset_type": 58,
                "mode_source": "FRF peak-derived experimental shape",
                "mean_coherence": None,
                "coherence_status": "parse_error",
            }
        )
        _annotate_standard_mode(mode)
        self.assertIn("parse error", mode.metadata["confidence_label"])
        self.assertEqual(mode.metadata["confidence_score"], 0.0)

    def test_missing_coherence_status_defaults_to_unavailable_not_perfect(self):
        """A mode built before this field existed (legacy cache/project data)
        must not be reinterpreted as computed coherence."""
        mode = self._mode(
            {
                "dataset_type": 58,
                "mode_source": "FRF peak-derived experimental shape",
                "mean_coherence": 1.0,
            }
        )
        _annotate_standard_mode(mode)
        self.assertNotEqual(mode.metadata["confidence_label"], "High peak confidence")
        self.assertEqual(mode.metadata["confidence_score"], 0.0)


if __name__ == "__main__":
    unittest.main()
