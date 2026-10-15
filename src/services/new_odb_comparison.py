"""A useful comparison for a new ODB when the automatic orientation is ambiguous (normal ODB / UNV comparator).

The automatic geometry registration stops when several physical orientations are equally plausible from geometry
alone (``GeometryOrientationAmbiguousError``). Two outcomes replace a discarded analysis; neither changes a gate:

1. ``bind_registration_by_fe_geometry``: a new ODB whose FE geometry identity (``modal_dataset_geometry_identity``)
   is exactly the FE geometry of an accepted physical registration may reuse that registration's frozen
   measured-point-to-FE-node mapping and rotation, provided the experimental file is, by fresh SHA-256 and size, the
   accepted PolyMAX source, the imported modal set replays the frozen registration (``verify_fixture_dataset``), the
   sealed registration is content-compatible with the loaded files and every mapped FE node is present. Only the
   geometric mapping is reused: the frequencies and mode shapes are the new ODB's own, the ODB is not assumed to be
   the accepted baseline ODB (its content is not hashed here), and archived sensitivities apply only when the
   separate check (11. Scaling) verifies the ODB as the accepted baseline ODB by SHA-256.
   A different geometry, experimental file or modal set, or an unverifiable registration, refuses the reuse.

2. ``frequency_only_diagnostic``: otherwise the extracted Abaqus frequencies, the PolyMAX frequencies and their
   differences are shown as ``FREQUENCY_ONLY_DIAGNOSTIC``. No orientation is chosen and no MAC is computed; the
   nearest-frequency columns describe proximity only and are never mode pairs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

import numpy as np

from domain.experiment_fixture import ExperimentFixture, load_experiment_fixture_manifest
from domain.registration import RegistrationMismatchError
from reviewed_core import frequency_error_percent
from scientific_state import modal_dataset_geometry_identity
from services import archived_sensitivity_evidence as evidence
from services.archived_sensitivity_evidence import AcceptedReferenceRefusal, fresh_content_identity
from services.experiment_fixture_regression import (
    FixtureRegressionError,
    load_fixture_registration,
    verify_fixture_dataset,
)

GEOMETRY_REUSE_SOURCE = "REUSED_PHYSICAL_REGISTRATION_BY_FE_GEOMETRY_IDENTITY"
FREQUENCY_ONLY = "FREQUENCY_ONLY_DIAGNOSTIC"
REUSE_LIMITS = (
    "only the frozen geometric mapping is reused: frequencies and mode shapes are this ODB's own",
    "this ODB is not assumed to be the accepted baseline ODB (its content is not hashed by this reuse)",
    "archived sensitivities apply only if 11. Scaling verifies this ODB as the accepted baseline ODB by SHA-256",
    "no acceptance gate or threshold is changed",
)
FREQUENCY_ONLY_STATEMENT = (
    "FREQUENCY_ONLY_DIAGNOSTIC: the physical orientation is not established, so no orientation was chosen and no MAC "
    "was computed. MAC and the physical modal correspondence are NOT verified; the nearest-frequency columns describe "
    "frequency proximity only and are not mode pairs.")


class GeometryReuseRefusal(AcceptedReferenceRefusal):
    """The accepted physical registration cannot be reused for this ODB / experimental file; the message says why."""


def _short(digest: object) -> str:
    return f"{str(digest)[:12]}…"


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise GeometryReuseRefusal(reason)


@dataclass(frozen=True)
class GeometryVerifiedRegistration:
    """An accepted physical registration whose FE geometry, experimental source and modal set the new files share."""

    specimen: str
    fixture: ExperimentFixture
    registration: Any  # the sealed, content-compatible FrozenRegistration
    fe_geometry: Mapping[str, Any]
    experimental: Mapping[str, Any]
    checks: tuple[str, ...]

    def provenance(self) -> dict:
        return {
            "source": GEOMETRY_REUSE_SOURCE,
            "specimen": self.specimen,
            "fixture_id": self.fixture.fixture_id,
            "registration_file": self.fixture.registration.path,
            "registration_hash": self.registration.registration_hash,
            "fe_geometry_sha256": self.fe_geometry["sha256"],
            "fe_node_count": self.fe_geometry["node_count"],
            "experimental_sha256": self.experimental["sha256"],
            "modal_set": self.fixture.modal_set.name,
            "accepted_baseline_odb_not_used": self.fixture.fe.odb_reference.file_name,
            "checks": list(self.checks),
            "limits": list(REUSE_LIMITS),
        }

    def warning(self) -> str:
        return (f"Physical registration reused by FE geometry identity ({GEOMETRY_REUSE_SOURCE}): {self.specimen} "
                f"{self.fixture.fixture_id}, registration {_short(self.registration.registration_hash)} (frozen "
                f"measured-point-to-FE-node mapping and rotation). This ODB has the accepted FE geometry "
                f"{_short(self.fe_geometry['sha256'])} ({self.fe_geometry['node_count']} nodes) and the accepted "
                f"PolyMAX source and modal set; " + "; ".join(REUSE_LIMITS) + ".")


def bind_registration_by_fe_geometry(experimental_path: Path, abaqus, experimental_dataset, *,
                                     repo_root: Optional[Path] = None, cancel=None) -> GeometryVerifiedRegistration:
    """The accepted physical registration for these files, verified independently of the ODB content, or refuse.

    Raises ``GeometryReuseRefusal`` with the reason, and ``SensitivityCheckCancelled`` when ``cancel`` is set.
    """

    repo_root = evidence.REPO_ROOT if repo_root is None else Path(repo_root)
    checks: list[str] = []
    experimental = fresh_content_identity(Path(experimental_path), cancel)
    try:
        fixtures = load_experiment_fixture_manifest(repo_root / evidence.FIXTURE_MANIFEST)
    except (OSError, ValueError, KeyError) as error:
        raise GeometryReuseRefusal(f"accepted fixture manifest unavailable: {error}") from error
    candidates = []
    for spec in evidence.SPECIMENS:  # the accepted physical registrations (SP-02, SP-13)
        try:
            fixture = fixtures.fixture(spec.fixture_id)
        except KeyError as error:
            raise GeometryReuseRefusal(
                f"accepted fixture {spec.fixture_id} is missing from {evidence.FIXTURE_MANIFEST}.") from error
        source = fixture.experimental_source
        if source.sha256 == experimental["sha256"] and source.size_bytes == experimental["size"]:
            candidates.append((spec, fixture))
    _require(bool(candidates), f"the experimental file SHA-256 {_short(experimental['sha256'])} "
                               f"({experimental['size']} bytes) is not the PolyMAX source of an accepted physical "
                               "registration.")
    _require(len(candidates) == 1, "the experimental file is the source of several accepted physical registrations; "
                                   "none is chosen.")
    spec, fixture = candidates[0]
    checks.append(f"experimental SHA-256 {_short(experimental['sha256'])} = {fixture.experimental_source.file_name} "
                  f"({fixture.fixture_id})")
    try:
        fe_geometry = modal_dataset_geometry_identity(abaqus)
    except ValueError as error:
        raise GeometryReuseRefusal(f"the ODB's FE geometry identity is unavailable: {error}") from error
    accepted = fixture.fe.geometry_identity
    _require(fe_geometry.get("schema_version") == accepted.schema_version
             and fe_geometry.get("sha256") == accepted.sha256 and fe_geometry.get("node_count") == accepted.node_count,
             f"the ODB's FE geometry {_short(fe_geometry.get('sha256'))} ({fe_geometry.get('node_count')} nodes) is "
             f"not the accepted {spec.specimen} FE geometry {_short(accepted.sha256)} ({accepted.node_count} nodes); "
             "the physical mapping is not reused.")
    checks.append(f"FE geometry identity {_short(fe_geometry['sha256'])} ({fe_geometry['node_count']} nodes) = "
                  f"accepted {spec.specimen} FE geometry ({fixture.fe.model_name})")
    try:
        registration = load_fixture_registration(fixture, repo_root)
        report = verify_fixture_dataset(fixture, registration, experimental_dataset)
    except FixtureRegressionError as error:
        raise GeometryReuseRefusal(f"fixture {fixture.fixture_id}: {error}") from error
    checks.append(f"PolyMAX modal set {report.modal_set_key!r} ({report.mode_count} modes, {report.point_count} "
                  f"points, measured {'/'.join(report.measured_dofs)}) replays the frozen registration")
    try:
        registration.check_content_compatible(experimental, fe_geometry)
    except (RegistrationMismatchError, ValueError) as error:
        raise GeometryReuseRefusal(f"physical registration {_short(registration.registration_hash)}: {error}") \
            from error
    loaded_nodes = {str(value) for value in np.asarray(abaqus.sorted_modes()[0].node_ids, dtype=object)}
    missing = [node for node in registration.mapped_fe_node_ids if node not in loaded_nodes]
    _require(not missing, f"{len(missing)} FE nodes of the frozen measured-node mapping are absent from the ODB.")
    checks.append(f"physical registration {_short(registration.registration_hash)} is sealed and content-compatible; "
                  f"all {len(registration.mapped_fe_node_ids)} mapped FE nodes present")
    return GeometryVerifiedRegistration(spec.specimen, fixture, registration, fe_geometry, experimental, tuple(checks))


# ----------------------------------------------------------------------------- frequency-only diagnostic

@dataclass(frozen=True)
class FrequencyOnlyRow:
    """One experimental mode with the nearest FE frequencies (proximity only; never a mode pair)."""

    experimental_mode: int
    experimental_hz: float
    nearest_fe_mode: Optional[int]
    nearest_fe_hz: Optional[float]
    nearest_difference_percent: Optional[float]  # (f_FE - f_exp) / f_exp * 100, the comparator's sign convention
    next_fe_mode: Optional[int]
    next_fe_hz: Optional[float]
    next_difference_percent: Optional[float]


@dataclass(frozen=True)
class FrequencyOnlyDiagnostic:
    status: str
    reason: str
    fe_modes: tuple[tuple[int, float], ...]
    experimental_modes: tuple[tuple[int, float], ...]
    rows: tuple[FrequencyOnlyRow, ...]
    statement: str = FREQUENCY_ONLY_STATEMENT
    experimental_source: str = "curve-fitted modal set (PolyMAX)"

    @property
    def provisional_experimental(self) -> bool:
        """True when the experimental frequencies are FRF peak candidates, not fitted modes."""
        return "PROVISIONAL" in self.experimental_source

    def to_dict(self) -> dict:
        return {
            "status": self.status, "statement": self.statement, "reason": self.reason,
            "experimental_frequency_source": self.experimental_source,
            "mac": "NOT_COMPUTED", "mode_pairs": "NONE (physical modal correspondence not verified)",
            "fe_modes": [{"mode": n, "frequency_hz": f} for n, f in self.fe_modes],
            "experimental_modes": [{"mode": n, "frequency_hz": f} for n, f in self.experimental_modes],
            "nearest_frequency_rows": [row.__dict__ for row in self.rows],
        }

    def text_lines(self) -> list[str]:
        lines = [FREQUENCY_ONLY, "=" * 80, self.statement, "", f"Why: {self.reason}", ""]
        lines.extend(["EXTRACTED ABAQUS FREQUENCIES", "-" * 80])
        lines.extend(f"FE mode {n}: {f:.4f} Hz" for n, f in self.fe_modes)
        if self.provisional_experimental:
            lines.extend(["", "EXPERIMENTAL FRF RESONANCE-PEAK CANDIDATES (dataset 58; PROVISIONAL, not validated "
                          "fitted modes)", "-" * 80])
            lines.extend(f"FRF peak {n}: {f:.4f} Hz" for n, f in self.experimental_modes)
        else:
            lines.extend(["", f"EXPERIMENTAL FREQUENCIES: {self.experimental_source}".upper(), "-" * 80])
            lines.extend(f"Experimental mode {n}: {f:.4f} Hz" for n, f in self.experimental_modes)
        lines.extend(["", "NEAREST FE FREQUENCIES (frequency proximity only; NOT mode pairs; MAC not computed)",
                      "-" * 80])
        for row in self.rows:
            if row.nearest_fe_mode is None:
                lines.append(f"Exp {row.experimental_mode} {row.experimental_hz:.4f} Hz: no FE frequency")
                continue
            text = (f"Exp {row.experimental_mode} {row.experimental_hz:.4f} Hz: nearest FE {row.nearest_fe_mode} "
                    f"{row.nearest_fe_hz:.4f} Hz ({row.nearest_difference_percent:+.2f} %)")
            if row.next_fe_mode is not None:
                text += (f"; next FE {row.next_fe_mode} {row.next_fe_hz:.4f} Hz "
                         f"({row.next_difference_percent:+.2f} %)")
            lines.append(text)
        return lines


def frequency_only_diagnostic(abaqus, experimental, reason: str) -> FrequencyOnlyDiagnostic:
    """Frequencies of both datasets and, per experimental mode, the two nearest FE frequencies (no shapes used)."""

    from services.modal_data_viewer import experimental_frequency_source

    fe = tuple((int(m.number), float(m.frequency_hz)) for m in abaqus.sorted_modes())
    exp = tuple((int(m.number), float(m.frequency_hz)) for m in experimental.sorted_modes())
    rows = []
    for number, hz in exp:
        ranked = sorted(fe, key=lambda item: (abs(item[1] - hz), item[0]))
        nearest = ranked[0] if ranked else None
        following = ranked[1] if len(ranked) > 1 else None
        rows.append(FrequencyOnlyRow(
            number, hz,
            None if nearest is None else nearest[0], None if nearest is None else nearest[1],
            None if nearest is None else frequency_error_percent(nearest[1], hz),
            None if following is None else following[0], None if following is None else following[1],
            None if following is None else frequency_error_percent(following[1], hz)))
    return FrequencyOnlyDiagnostic(FREQUENCY_ONLY, reason, fe, exp, tuple(rows),
                                   experimental_source=experimental_frequency_source(experimental))


def frequency_only_table_rows(diagnostic: FrequencyOnlyDiagnostic) -> list[tuple[str, ...]]:
    """Rows for the comparison table (its columns), visibly not pairs: MAC not computed, status FREQUENCY ONLY."""

    status = ("FREQUENCY ONLY — FRF peak (provisional), not a pair" if diagnostic.provisional_experimental
              else "FREQUENCY ONLY — not a pair")
    rows = []
    for row in diagnostic.rows:
        rows.append((
            "—" if row.nearest_fe_mode is None else f"{row.nearest_fe_mode} (nearest)", str(row.experimental_mode),
            "—" if row.nearest_fe_hz is None else f"{row.nearest_fe_hz:.4f}", f"{row.experimental_hz:.4f}",
            "—" if row.nearest_difference_percent is None else f"{row.nearest_difference_percent:.2f}",
            "not computed", "—", "—", status))
    return rows
