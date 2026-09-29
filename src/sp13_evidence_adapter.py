"""Explicit historical import of the frozen SP13 identification evidence.

SP13 is a specimen; this module only reads its frozen REAL-4 artifacts and
wraps their stored values in the versioned evidence contracts.  It does not
run, recalculate, or infer any scientific result, and it is not an executor:
historical evidence never passes through the production runner.

Every imported record is UNBOUND (``scientific_binding=None``) and keeps its
frozen-artifact provenance.  REAL-4 predates the FrozenRegistration, the
MAC-evidence policy, the rank hard block, and the complex/rank-aware family
residual, so the import is HISTORICAL_NOT_REVALIDATED.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import ClassVar, Mapping

from domain.evidence import (
    EvidenceProvenance,
    EvidenceSourceIdentity,
    IdentificationEvidence,
    IdentifiabilityEvidence,
    SensitivityEvidence,
    ValidationEvidence,
)


HISTORICAL_STATUS = "HISTORICAL_NOT_REVALIDATED"


@dataclass(frozen=True)
class SP13EvidenceBundle:
    """Imported historical SP13 evidence; absent records stay ``None``.

    The bundle holds only UNBOUND records: it can never carry evidence bound
    to a current model definition or FrozenRegistration.
    """

    sensitivity: SensitivityEvidence | None
    identifiability: IdentifiabilityEvidence | None
    identification: IdentificationEvidence | None
    validation: ValidationEvidence | None

    historical_status: ClassVar[str] = HISTORICAL_STATUS
    binding_status: ClassVar[str] = "UNBOUND"

    def __post_init__(self) -> None:
        for name in ("sensitivity", "identifiability", "identification", "validation"):
            record = getattr(self, name)
            if getattr(record, "scientific_binding", None) is not None:
                raise ValueError(
                    f"A historical SP13 bundle holds only UNBOUND evidence; {name} "
                    "carries a scientific binding."
                )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact(path: Path, analysis_root: Path) -> EvidenceSourceIdentity:
    return EvidenceSourceIdentity(
        source_id=path.relative_to(analysis_root).as_posix(),
        source_type="frozen-sp13-artifact",
        uri=path.resolve().as_uri(),
        content_hash=_sha256(path),
    )


def _read_json(path: Path) -> Mapping[str, object]:
    with path.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, Mapping):
        raise ValueError(f"Frozen SP13 JSON artifact must contain an object: {path}")
    return dict(payload)


def _read_csv(path: Path) -> tuple[Mapping[str, str], ...]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return tuple(dict(row) for row in csv.DictReader(stream))


def _latest_timestamp(paths: tuple[Path, ...]) -> datetime:
    return datetime.fromtimestamp(
        max(path.stat().st_mtime for path in paths), tz=timezone.utc
    )


def _explicit_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"Invalid frozen SP13 timestamp {value!r}.") from error
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Frozen SP13 timestamps must include a timezone.")
    return timestamp.astimezone(timezone.utc)


def _record(
    record_type,
    *,
    analysis_root: Path,
    evidence_name: str,
    primary_path: Path,
    source_paths: tuple[Path, ...],
    content: Mapping[str, object],
    status: object,
    commit: object = None,
    timestamp: datetime | None = None,
):
    if not isinstance(status, str) or not status.strip():
        raise ValueError(f"Frozen SP13 {evidence_name} evidence has no stored status.")
    artifacts = tuple(_artifact(path, analysis_root) for path in source_paths)
    primary = next(item for item in artifacts if item.source_id == primary_path.relative_to(analysis_root).as_posix())
    provenance = EvidenceProvenance(
        producer="abaqus-modal-comparator frozen SP13 evidence adapter",
        commit=str(commit).strip() if isinstance(commit, str) and commit.strip() else None,
        method="read-only serialization of frozen stored artifacts",
        artifacts=artifacts,
        details={
            "specimen": "SP13",
            "historical_status": HISTORICAL_STATUS,
            "source_paths": [item.source_id for item in artifacts],
            "record_timestamp_basis": (
                "stored completed_utc"
                if timestamp is not None
                else "latest source-file modification time in UTC"
            ),
        },
    )
    record_timestamp = timestamp or _latest_timestamp(source_paths)
    content_hash = hashlib.sha256(
        json.dumps(
            content,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return record_type.create(
        evidence_id=f"sp13-{evidence_name}-{content_hash[:16]}",
        timestamp=record_timestamp,
        source_identity=primary,
        provenance=provenance,
        status=status,
        content=content,
        scientific_binding=None,
    )


def _sensitivity_evidence(analysis_root: Path) -> SensitivityEvidence | None:
    directory = analysis_root / "sp13_sensitivity_real2"
    raw_matrix = directory / "raw_sensitivity_matrix.csv"
    if not raw_matrix.is_file():
        return None
    sources = [raw_matrix]
    content: dict[str, object] = {
        "raw_sensitivity_matrix": _read_csv(raw_matrix),
    }
    optional_csv = {
        "family_observables": directory / "cluster_sensitivity.csv",
        "parameter_baseline": directory / "parameter_baseline.csv",
    }
    for key, path in optional_csv.items():
        if path.is_file():
            content[key] = _read_csv(path)
            sources.append(path)
    execution_path = directory / "execution_note.json"
    if not execution_path.is_file():
        return None
    execution = _read_json(execution_path)
    content["execution"] = execution
    sources.append(execution_path)
    protocol_path = directory / "protocol.json"
    if protocol_path.is_file():
        content["protocol"] = _read_json(protocol_path)
        sources.append(protocol_path)
    status = execution.get("final_state")
    timestamp = _explicit_timestamp(execution.get("completed_utc"))
    return _record(
        SensitivityEvidence,
        analysis_root=analysis_root,
        evidence_name="sensitivity",
        primary_path=raw_matrix,
        source_paths=tuple(sources),
        content=content,
        status=status,
        timestamp=timestamp,
    )


def _identifiability_evidence(
    analysis_root: Path,
) -> IdentifiabilityEvidence | None:
    directory = analysis_root / "sp13_sensitivity_real2"
    model_paths = {
        "U": directory / "svd_uniform.json",
        "P": directory / "svd_per_mode.json",
    }
    available = {key: path for key, path in model_paths.items() if path.is_file()}
    if not available:
        return None
    content: dict[str, object] = {
        "models": {key: _read_json(path) for key, path in available.items()}
    }
    sources = list(available.values())
    execution_path = directory / "execution_note.json"
    execution = None
    if execution_path.is_file():
        execution = _read_json(execution_path)
        content["execution"] = execution
        sources.append(execution_path)
    status = (
        execution.get("final_state")
        if execution
        else next(iter(content["models"].values())).get(
            "practical_precision_status"
        )
    )
    timestamp = _explicit_timestamp(execution.get("completed_utc")) if execution else None
    return _record(
        IdentifiabilityEvidence,
        analysis_root=analysis_root,
        evidence_name="identifiability",
        primary_path=next(iter(available.values())),
        source_paths=tuple(sources),
        content=content,
        status=status,
        timestamp=timestamp,
    )


def _identification_evidence(
    analysis_root: Path,
) -> IdentificationEvidence | None:
    final_directory = analysis_root / "sp13_final_effective_property_validation"
    identified_path = final_directory / "identified_properties.json"
    if not identified_path.is_file():
        return None
    identified = _read_json(identified_path)
    content: dict[str, object] = {"identified_properties": identified}
    sources = [identified_path]
    inverse_directory = analysis_root / "sp13_effective_cfrp_inverse"
    inverse_models: dict[str, object] = {}
    for key, name in (("U", "inverse_results_U.json"), ("P", "inverse_results_P.json")):
        path = inverse_directory / name
        if path.is_file():
            inverse_models[key] = _read_json(path)
            sources.append(path)
    if inverse_models:
        content["inverse_models"] = inverse_models
    comparison_path = inverse_directory / "parameter_comparison.csv"
    if comparison_path.is_file():
        content["parameter_comparison"] = _read_csv(comparison_path)
        sources.append(comparison_path)
    execution_path = inverse_directory / "execution_note.json"
    execution = None
    if execution_path.is_file():
        execution = _read_json(execution_path)
        content["execution"] = execution
        sources.append(execution_path)
    commit = identified.get("starting_head")
    status = identified.get("recommendation") or identified.get("record_status")
    if not isinstance(status, str) or not status.strip():
        return None
    return _record(
        IdentificationEvidence,
        analysis_root=analysis_root,
        evidence_name="identification",
        primary_path=identified_path,
        source_paths=tuple(sources),
        content=content,
        status=status,
        commit=commit,
    )


def _validation_evidence(analysis_root: Path) -> ValidationEvidence | None:
    directory = analysis_root / "sp13_final_effective_property_validation"
    summary_path = directory / "validation_summary.csv"
    if not summary_path.is_file():
        return None
    rows = _read_csv(summary_path)
    content: dict[str, object] = {"validation_rows": rows}
    sources = [summary_path]
    identified_path = directory / "identified_properties.json"
    if not identified_path.is_file():
        return None
    identified = _read_json(identified_path)
    content["identified_properties"] = identified
    sources.append(identified_path)
    limitations_path = directory / "limitations.md"
    if limitations_path.is_file():
        content["limitations_markdown"] = limitations_path.read_text(encoding="utf-8")
        sources.append(limitations_path)
    report_path = directory / "FINAL_REPORT.md"
    if report_path.is_file():
        content["report_markdown"] = report_path.read_text(encoding="utf-8")
        sources.append(report_path)
    status = identified.get("recommendation")
    if not isinstance(status, str) or not status.strip():
        return None
    commit = identified.get("starting_head")
    return _record(
        ValidationEvidence,
        analysis_root=analysis_root,
        evidence_name="validation",
        primary_path=summary_path,
        source_paths=tuple(sources),
        content=content,
        status=status,
        commit=commit,
    )


def load_frozen_sp13_evidence(analysis_root: str | Path) -> SP13EvidenceBundle:
    """Import available frozen SP13 evidence from an explicit analysis directory.

    This is the historical import path: it takes no session, produces UNBOUND
    records only, and leaves absent evidence types as ``None``.
    """

    root = Path(analysis_root)
    if not root.is_dir():
        raise FileNotFoundError(f"SP13 analysis directory does not exist: {root}")
    return SP13EvidenceBundle(
        sensitivity=_sensitivity_evidence(root),
        identifiability=_identifiability_evidence(root),
        identification=_identification_evidence(root),
        validation=_validation_evidence(root),
    )


__all__ = [
    "HISTORICAL_STATUS",
    "SP13EvidenceBundle",
    "load_frozen_sp13_evidence",
]
