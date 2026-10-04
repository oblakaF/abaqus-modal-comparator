"""External PolyMAX modal preparation provider (Auto-ID M1.3; D-023, D-026, D-027).

The first production ``ModalFittingProvider``.  It performs **no** FRF fitting: it
represents the validated external Simcenter Testlab PolyMAX workflow, whose fit of the
pinned FRFs is frozen in the same pinned export (dataset 55 next to the dataset-58 FRFs).

Chain (one call: ``prepare_external_polymax_modal_dataset``):

    pinned export --prepare_frf_input--> FrfInput (dataset-58 FRF block)
        --ExternalPolyMAXProvider.fit--> ModalFittingOutput
        --run_modal_fitting (registry admission + boundary validation)--> validated output
        --require_identification_input (M1.1)--> Auto-ID experimental input

``fit`` loads the frozen PolyMAX set through the M1.2 production path
(``load_production_modal_input``: pinned source SHA-256, FrozenRegistration, modal set,
counts, measured-DOF contract, M1.1 policy) and keeps its frequencies, shapes, point
order and measured DOFs unchanged.  Damping is PolyMAX's own estimate, read from the
stored dataset-55 pole (zeta = -Re(lambda)/|lambda|), because the reader leaves complex
PolyMAX damping unset.  No pole is extracted, selected or fitted here.
"""

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from cmif_separation import _build_multi_reference_frf_block
from domain.experiment_fixture import (
    ExperimentFixture,
    ExperimentFixtureManifest,
    fixture_roots_from_environment,
    load_experiment_fixture_manifest,
    resolve_external_file,
)
from domain.modal_fitting import (
    FittingWorkflow,
    FrfInput,
    ModalFittingOutput,
    ModalFittingProviderIdentity,
    ModalFittingProviderRegistry,
    ModalFittingRefusal,
    PoleSelection,
    ProviderKind,
    ValidatedModalFittingOutput,
    canonical_hash,
    run_modal_fitting,
)
from domain.modal_input_source import EXTERNAL_POLYMAX_MODE_SOURCE, require_identification_input
from modal_core import ModalDataset
import universal_reader

from .production_modal_input import FIXTURE_MANIFEST_PATH, REPO_ROOT, load_production_modal_input


EXTERNAL_POLYMAX_PROVIDER = ModalFittingProviderIdentity(
    name="external-polymax",
    version="1",
    kind=ProviderKind.EXTERNAL,
    mode_source=EXTERNAL_POLYMAX_MODE_SOURCE,
)
FITTING_METHOD = "Simcenter Testlab PolyMAX (external; frozen dataset-55 export)"
CONFIGURATION_KEYS = frozenset({"fixture_id", "modal_set", "frequency_band_hz"})
# UFF spec data types used to declare the FRF quantity (ordinate / denominator).
_SPEC_DATA_TYPES = {8: "displacement", 11: "velocity", 12: "acceleration", 13: "force"}


def admitted_provider_registry() -> ModalFittingProviderRegistry:
    """Registry of the providers admitted for production (explicit; D-021, D-027)."""
    return ModalFittingProviderRegistry((EXTERNAL_POLYMAX_PROVIDER,))


def _manifest(manifest: ExperimentFixtureManifest | None) -> ExperimentFixtureManifest:
    return load_experiment_fixture_manifest(FIXTURE_MANIFEST_PATH) if manifest is None else manifest


def _fixture(manifest: ExperimentFixtureManifest, fixture_id: object) -> ExperimentFixture:
    try:
        return manifest.fixture(str(fixture_id))
    except KeyError:
        raise ModalFittingRefusal("configuration.fixture_id", f"{fixture_id!r} is not an accepted fixture.") from None


def _frf_quantity(records: list[Mapping[str, Any]]) -> str:
    kinds = {(record.get("ordinate_spec_data_type"), record.get("orddenom_spec_data_type")) for record in records}
    if len(kinds) != 1:
        raise ModalFittingRefusal("frf.quantity", f"FRF records mix quantities {sorted(kinds, key=str)}.")
    numerator, denominator = next(iter(kinds))
    name = lambda code: _SPEC_DATA_TYPES.get(code, f"spec-{code}")
    return f"{name(numerator)}/{name(denominator)}"


def prepare_frf_input(
    fixture: ExperimentFixture,
    roots: Mapping[str, Path],
) -> FrfInput:
    """FRF preparation: the pinned export's dataset-58 FRFs as an ``FrfInput``.

    Uses the existing multi-reference FRF block builder unchanged; coherence is passed
    on only when that builder reports it as computed.
    """

    path = resolve_external_file(fixture.experimental_source, roots)
    datasets = universal_reader._read_universal_datasets(path)
    geometry, _ = universal_reader._read_geometry(datasets)
    frf_records = [item for item in datasets if universal_reader._dataset_type(item) == 58]
    if not frf_records:
        raise ModalFittingRefusal("frf", f"{fixture.experimental_source.file_name} contains no dataset-58 FRFs.")
    block = _build_multi_reference_frf_block(frf_records, geometry)
    transfer = [item for item in frf_records if int(item.get("func_type", -1)) == 4]
    computed = block.coherence_status == "computed"
    return FrfInput(
        frequency_hz=block.frequency,
        h=block.matrix,
        response_keys=tuple((int(node), int(direction)) for node, direction in block.row_keys),
        reference_keys=tuple((int(node), int(direction)) for node, direction in block.reference_keys),
        quantity=_frf_quantity(transfer or frf_records),
        coherence_status=block.coherence_status,
        coherence=np.asarray(block.mean_coherence, dtype=float) if computed else None,
        source_sha256=fixture.experimental_source.sha256,
    )


def default_configuration(fixture: ExperimentFixture, frf: FrfInput) -> dict[str, Any]:
    return {
        "fixture_id": fixture.fixture_id,
        "modal_set": fixture.modal_set.name,
        "frequency_band_hz": [float(frf.frequency_hz[0]), float(frf.frequency_hz[-1])],
    }


class ExternalPolyMAXProvider:
    """``ModalFittingProvider`` for frozen external PolyMAX selections (D-026, D-027)."""

    identity = EXTERNAL_POLYMAX_PROVIDER

    def __init__(
        self,
        *,
        roots: Mapping[str, Path] | None = None,
        manifest: ExperimentFixtureManifest | None = None,
        repo_root: Path = REPO_ROOT,
    ) -> None:
        self.roots = fixture_roots_from_environment() if roots is None else dict(roots)
        self.manifest = _manifest(manifest)
        self.repo_root = Path(repo_root)

    def _configuration(self, frf: FrfInput, configuration: Mapping[str, Any]) -> tuple[ExperimentFixture, tuple]:
        if not isinstance(configuration, Mapping) or set(configuration) != CONFIGURATION_KEYS:
            raise ModalFittingRefusal("configuration", f"must contain exactly {sorted(CONFIGURATION_KEYS)}.")
        fixture = _fixture(self.manifest, configuration["fixture_id"])
        if configuration["modal_set"] != fixture.modal_set.name:
            raise ModalFittingRefusal(
                "configuration.modal_set",
                f"{configuration['modal_set']!r} is not the frozen modal set {fixture.modal_set.name!r} of "
                f"{fixture.fixture_id}.",
            )
        band = configuration["frequency_band_hz"]
        if not (isinstance(band, (list, tuple)) and len(band) == 2
                and all(isinstance(value, (int, float)) and math.isfinite(value) for value in band)
                and frf.frequency_hz[0] <= band[0] < band[1] <= frf.frequency_hz[-1]):
            raise ModalFittingRefusal("configuration.frequency_band_hz", "must be [low, high] inside the FRF axis.")
        if frf.source_sha256 != fixture.experimental_source.sha256:
            raise ModalFittingRefusal(
                "frf.source_sha256",
                "the FRFs do not come from the pinned export that holds the frozen PolyMAX selection.",
            )
        return fixture, (float(band[0]), float(band[1]))

    def fit(self, frf: FrfInput, configuration: Mapping[str, Any]) -> ModalFittingOutput:
        fixture, band = self._configuration(frf, configuration)
        # M1.2: pinned source, FrozenRegistration, modal set, counts, DOF contract, M1.1 policy.
        production = load_production_modal_input(
            fixture.fixture_id, roots=self.roots, manifest=self.manifest, repo_root=self.repo_root
        )
        source_path = resolve_external_file(fixture.experimental_source, self.roots)
        records = universal_reader._read_universal_datasets(source_path)
        indices = list(production.dataset.metadata.get("modal_set_record_indices", []))
        modes = production.dataset.sorted_modes()
        if len(indices) != len(modes):
            raise ModalFittingRefusal("dataset", "the frozen modal set records do not match its modes.")

        fitted, hooks = [], {}
        for mode, index in zip(modes, indices):
            record = records[index]
            pole = record.get("eig")
            if pole in (None, 0) or int(record.get("mode_n") or mode.number) != mode.number:
                raise ModalFittingRefusal("dataset", f"mode {mode.number} has no stored PolyMAX pole.")
            pole = complex(np.asarray(pole).ravel()[0])
            if not math.isclose(abs(pole.imag) / (2.0 * math.pi), mode.frequency_hz, rel_tol=1e-12, abs_tol=0.0):
                raise ModalFittingRefusal("dataset", f"mode {mode.number} frequency does not match its stored pole.")
            if not band[0] <= mode.frequency_hz <= band[1]:
                raise ModalFittingRefusal(
                    "configuration.frequency_band_hz",
                    f"frozen mode {mode.number} ({mode.frequency_hz:.3f} Hz) lies outside the band; "
                    "a frozen selection is never trimmed.",
                )
            damping = -pole.real / abs(pole)
            copied = copy.deepcopy(mode)
            copied.damping_ratio = float(damping)
            copied.metadata.update(
                mode_source=EXTERNAL_POLYMAX_MODE_SOURCE,
                polymax_pole=[pole.real, pole.imag],
                damping_source="PolyMAX dataset-55 pole: -Re(lambda)/|lambda|",
                frozen_selection=fixture.modal_set.name,
            )
            fitted.append(copied)
            line = int(np.argmin(np.abs(frf.frequency_hz - mode.frequency_hz)))
            resolution = float(np.median(np.diff(frf.frequency_hz)))
            hooks[mode.number] = {
                # Raw values for M1.4; no QC judgement is made here.
                "frequency_resolution_hz": resolution,
                "half_power_bandwidth_hz": float(2.0 * damping * mode.frequency_hz),
                "coherence_at_resonance": None if frf.coherence is None else float(frf.coherence[line]),
            }

        source = fixture.experimental_source
        dataset = ModalDataset(
            source_name=production.dataset.source_name,
            source_path=production.dataset.source_path,
            modes=fitted,
            metadata={
                **copy.deepcopy(production.dataset.metadata),
                "mode_source": EXTERNAL_POLYMAX_MODE_SOURCE,
                "fixture_id": fixture.fixture_id,
            },
            history=list(production.dataset.history),
        )
        configuration = dict(configuration)
        provenance = {
            "provider_name": self.identity.name,
            "provider_version": self.identity.version,
            "fitting_method": FITTING_METHOD,
            "fixture_id": fixture.fixture_id,
            "modal_set": production.report.modal_set_key,
            "source_file": {
                "file_name": source.file_name,
                "sha256": source.sha256,
                "size_bytes": source.size_bytes,
                "store": source.location.store,
                "relative_path": source.location.relative_path,
            },
            "frf_source_sha256": frf.source_sha256,
            "frf_content_hash": frf.content_hash,
            "frf_quantity": frf.quantity,
            "frf_coherence_status": frf.coherence_status,
            "configuration": configuration,
            "configuration_hash": canonical_hash(configuration),
            "frequency_band_hz": [band[0], band[1]],
            "pole_selection": PoleSelection.EXTERNAL_FROZEN_SELECTION.value,
            "registration_hash": production.report.registration_hash,
            "fe_geometry_sha256": production.report.fe_geometry_sha256,
            "measured_dofs": list(production.report.measured_dofs),
            "damping_source": "PolyMAX dataset-55 pole",
        }
        return ModalFittingOutput(
            dataset=dataset,
            provider=self.identity,
            provenance=provenance,
            qc_summary={"status": "NOT_EVALUATED", "hooks": hooks},
            # The PolyMAX export carries no uncertainty estimates.
            confidence={mode.number: {"frequency_sd_hz": None, "damping_sd": None} for mode in fitted},
        )


def prepare_external_polymax_modal_dataset(
    fixture_id: str,
    *,
    roots: Mapping[str, Path] | None = None,
    manifest: ExperimentFixtureManifest | None = None,
    repo_root: Path = REPO_ROOT,
    registry: ModalFittingProviderRegistry | None = None,
    workflow: FittingWorkflow = FittingWorkflow.PRODUCTION,
) -> ValidatedModalFittingOutput:
    """Full chain for one accepted fixture: FRF preparation -> provider -> validation -> M1.1."""

    manifest = _manifest(manifest)
    roots = fixture_roots_from_environment() if roots is None else roots
    fixture = _fixture(manifest, fixture_id)
    frf = prepare_frf_input(fixture, roots)
    provider = ExternalPolyMAXProvider(roots=roots, manifest=manifest, repo_root=repo_root)
    validated = run_modal_fitting(
        provider,
        frf,
        default_configuration(fixture, frf),
        registry=admitted_provider_registry() if registry is None else registry,
        workflow=workflow,
    )
    require_identification_input(validated.output.dataset)
    return validated
