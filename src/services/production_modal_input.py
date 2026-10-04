"""Production experimental modal input for Auto-ID (M1.2): accepted PolyMAX fixtures only.

Auto-ID consumes experimental modes only through a record of the accepted fixture
manifest (docs/auto_id/fixtures/real_experiment_fixtures.json), selected by its
``fixture_id``; there is no free file-path entry.  Loading a fixture:

1. runs the M0.3 fixture verification on the production reader output (source
   store/size/SHA-256, hash-sealed FrozenRegistration and its bindings, pinned
   modal set, mode source, mode and point counts, measured-DOF contract replay);
2. applies the M1.1 identification input-source policy to every mode, so a
   peak-derived or unclassifiable mode is refused even inside a fitted set;
3. returns the reader's dataset unchanged (frequencies, shapes, damping, node
   order) together with the FrozenRegistration and a provenance record.

Every difference raises; nothing is repaired, substituted or re-selected.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from domain.experiment_fixture import (
    ExperimentFixture,
    ExperimentFixtureManifest,
    fixture_roots_from_environment,
    load_experiment_fixture_manifest,
)
from domain.modal_input_source import ModalInputSourceClassification, require_identification_input
from domain.registration import FrozenRegistration
from modal_core import ModalDataset
from universal_reader import load_universal_modal_file

from .experiment_fixture_regression import (
    FixtureRegressionError,
    FixtureRegressionReport,
    ModalLoader,
    verify_experiment_fixture,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_MANIFEST_PATH = REPO_ROOT / "docs" / "auto_id" / "fixtures" / "real_experiment_fixtures.json"


@dataclass(frozen=True)
class ProductionModalInput:
    fixture: ExperimentFixture
    dataset: ModalDataset
    registration: FrozenRegistration
    report: FixtureRegressionReport
    source_classification: ModalInputSourceClassification

    def provenance(self) -> dict[str, Any]:
        source = self.fixture.experimental_source
        return {
            "fixture_id": self.fixture.fixture_id,
            "specimen_id": self.fixture.specimen_id,
            "experimental_source": {
                "file_name": source.file_name,
                "sha256": source.sha256,
                "size_bytes": source.size_bytes,
                "store": source.location.store,
                "relative_path": source.location.relative_path,
            },
            "modal_set": self.report.modal_set_key,
            "mode_source": self.report.mode_source,
            "input_source_class": self.source_classification.source.value,
            "mode_count": self.report.mode_count,
            "measurement_point_count": self.report.point_count,
            "measured_dofs": list(self.report.measured_dofs),
            "registration_hash": self.report.registration_hash,
            "fe_geometry_sha256": self.report.fe_geometry_sha256,
        }


def load_production_modal_input(
    fixture_id: str,
    *,
    roots: Mapping[str, Path] | None = None,
    manifest: ExperimentFixtureManifest | None = None,
    repo_root: Path = REPO_ROOT,
    load_modal_dataset: ModalLoader = load_universal_modal_file,
) -> ProductionModalInput:
    """Load the accepted fixture ``fixture_id`` as Auto-ID experimental input, or refuse.

    Raises ``KeyError`` for an id not in the manifest, the fixture/source errors of
    ``verify_experiment_fixture`` for identity differences, and
    ``IdentificationInputSourceRefusal`` for non-curve-fitted modes.
    """

    manifest = load_experiment_fixture_manifest(FIXTURE_MANIFEST_PATH) if manifest is None else manifest
    fixture = manifest.fixture(fixture_id)
    roots = fixture_roots_from_environment() if roots is None else roots

    loaded: list[ModalDataset] = []

    def capture(path, **kwargs):
        dataset = load_modal_dataset(path, **kwargs)
        loaded.append(dataset)
        return dataset

    report = verify_experiment_fixture(fixture, roots, repo_root=repo_root, load_modal_dataset=capture)
    dataset = loaded[-1]
    classification = require_identification_input(dataset)

    with open(Path(repo_root) / fixture.registration.path, encoding="utf-8") as handle:
        registration = FrozenRegistration.from_dict(json.load(handle))
    if registration.registration_hash != report.registration_hash:
        raise FixtureRegressionError(
            "registration.registration_hash", "the registration file changed during loading."
        )
    return ProductionModalInput(fixture, dataset, registration, report, classification)
