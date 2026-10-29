"""NEW-GUI.6: the verified modal comparison of the read FE and experimental data, with no Qt.

On the user's explicit command Run verified modal comparison, and only after the NEW-GUI.5 check has verified an
archived physical registration for exactly the current data, ``compare`` runs the project's scientific comparator on
the data Inspect file already read (``FePreview.dataset`` and ``ExperimentalPreview.sets[set_index].dataset``):

1. the registration is verified again, now, by the existing service
   ``services.new_odb_comparison.bind_registration_by_fe_geometry`` (fresh SHA-256 and size of the experimental file,
   FE geometry identity, the modal set's replay of the frozen registration, content compatibility, mapped FE nodes).
   A green status shown earlier is never relied on: a file changed on disk since the check is refused here, and so is
   a registration other than the one the check showed;
2. ``modal_core.compare_modal_datasets(abaqus, experimental, frozen_registration=...)``, the reviewed quality-control
   facade the existing program calls (``runtime_contracts``), with the frozen measured-point-to-FE-node mapping and
   rotation of that registration. No automatic orientation search runs, and no orientation, reflection, scale or
   point map is chosen by MAC or frequency; the comparator's rigid-body criterion, MAC, frequency and coverage gates
   and its one-to-one assignment are unchanged. The registration's provenance and warning are attached to the result
   exactly as the existing program attaches them (``runtime_hardening``).

Nothing is read again by the GUI, the read datasets are not changed, and no threshold is added. The comparator's
``ComparisonResult`` is kept as returned; ``comparison_view`` only words it for display. A dataset-58 FRF set
(PROVISIONAL — NOT A VALIDATED FITTED MODE) is not compared. An empty pair list is a valid scientific result.

The pairs are the comparator's numerical assignment by its admissibility gates. They are not Auto-ID observations:
their scientific use for Auto-ID is not assessed here.

NEW-GUI.6-F1: ``compare`` also receives the identities recorded when the files were read (``sources``). The FE
manifest is hashed again and the experimental file's fresh SHA-256 (from the service) is compared with them; a file
changed since it was read is refused before the comparator runs. The outcome keeps these identities: an export states
them, never a hash taken later.

One heavy operation at a time: the comparison shares the lock of the frequency diagnostic and the registration check
(NEW-GUI.4/5). ``ComparisonSlot`` keeps the current request; a replaced or cleared file, Inspect again, another modal
set, a new registration check or a closed window cancels it and its outcome is discarded. A request cancelled while
it waits for the lock never runs the comparator.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import shutil
import tempfile
import threading
from typing import Any, Optional

from new_gui import diagnostic_model as dm
from new_gui import registration_check_model as rm
from new_gui import shape_model as sm

TITLE = "Verified modal comparison"
RUN = "Run verified modal comparison"
NOT_RUN = "Not run"
RUNNING_BADGE = "Comparing..."
RUNNING_TEXT = "Verifying the registration again and running the scientific comparator..."
PAIRS_FOUND = "VERIFIED_COMPARISON"
NO_PAIR = "NO_ADMISSIBLE_PAIR"
REFUSED_BADGE = "Not run: registration not confirmed"
FAILED_BADGE = "Comparison not completed"
NEED_REGISTRATION = ("Check reference registration must verify an archived physical registration for exactly these "
                     "data first.")
PROVISIONAL_BLOCK = ("The chosen set holds FRF peak records (dataset 58): PROVISIONAL — NOT A VALIDATED FITTED MODE. "
                     "No verified comparison is run on them.")
HINT = ("Runs the project's scientific comparator with the archived physical registration verified above, after "
        "verifying it again now. MAC is computed only on the registered measured DOFs; the comparator's gates are "
        "unchanged. Nothing runs by itself.")
UNPAIRED_NOTE = ("UNPAIRED SHAPES — independent views. Each shape is drawn on its own coordinates; they are not "
                 "registered, overlaid or paired, and no MAC exists between them.")
PAIR_NOTE = ("Computed pair on the verified archived registration: both shapes are drawn on the same registered "
             "measured points (the comparator's pair data); the third view is the comparator's amplitude correlation.")
MAC_NOT_COMPUTED = "NOT_COMPUTED"
MAC_MISSING_NOTE = "frequency-only assignment: MAC not computed, shape identity NOT established"
AUTO_ID_USE = "NOT ASSESSED"
AUTO_ID_NOTE = ("The pairs are the comparator's numerical assignment by its unchanged admissibility gates. They are "
                "not Auto-ID observations: a pair enters Auto-ID only as a governed FIT / HOLDOUT observation of an "
                "accepted strict freeze, which this view neither creates nor checks.")
ENGINEERING_TARGET = ("Engineering target of the project: frequency agreement preferably within about 5 %, up to 10 % "
                      "with a correct modal identity. It is shown for orientation only and is not a criterion: the "
                      "comparator's gates decide the pairs.")
NO_PAIR_TEXT = ("No admissible pair: no FE / experimental candidate passed the comparator's unchanged frequency, MAC "
                "and coverage gates. This is a valid scientific result, not an application error; no correlation "
                "is shown for it.")
SIGN_NOTE = dm.SIGN_NOTE
LIMITS = (
    "Only the frozen geometric mapping of the archived registration is used; the frequencies and shapes are the read "
    "data's own.",
    "MAC is computed on the registered measured DOFs only; nothing is interpolated or filled in.",
    "The pairs are a numerical assignment by the comparator's gates, not a material identification and not Auto-ID "
    "observations.",
    "No material property is identified or implied.",
)
IDLE, RUNNING, DONE, REFUSED, FAILED = "idle", "running", "done", "refused", "failed"

PAIR_HEADERS = ("FE mode", "FE (Hz)", "Exp record", "Exp mode", "Exp (Hz)", "Error (%)", "MAC", "Comparator status",
                "Measured DOFs", "DOF coverage", "Points", "Order", "Close modes", "Auto-ID use")
CANDIDATE_HEADERS = ("Exp record", "Exp mode", "Exp (Hz)", "Best-MAC FE mode", "FE (Hz)", "MAC", "Error (%)",
                     "Coverage", "Admissible", "Rejected by", "Assigned")
UNMATCHED_HEADERS = ("Mode", "Frequency (Hz)")
RIGID_HEADERS = ("FE mode", "Frequency (Hz)", "Rigid-body residual")
DASH = dm.DASH


class ComparisonRefused(ValueError):
    """The verified comparison is not run for these data; the message says why."""


class ComparisonCancelled(RuntimeError):
    """The request was cancelled before the comparator ran."""


# ---------------------------------------------------------------------------------------------- availability


def unavailable(fe_preview, experimental_preview, set_index: Optional[int], registration_view) -> tuple:
    """Why the comparison cannot run yet (empty when it can), in the order the user acts."""
    reasons = list(dm.unavailable(fe_preview, experimental_preview, set_index))
    if not reasons and rm.set_is_provisional(experimental_preview, set_index):
        reasons.append(PROVISIONAL_BLOCK)
    if not reasons and registration_view is None:
        reasons.append(NEED_REGISTRATION)
    return tuple(reasons)


# ---------------------------------------------------------------------------------------------- the comparator


def check_sources(fe_preview, sources: Optional[dict], experimental_now: Optional[dict] = None,
                  cancel_event: Optional[threading.Event] = None) -> dict:
    """The read identities, confirmed against the files now; raises ``ComparisonRefused`` when one changed.

    PLATE-ONLY-R2-F1: when the read identities are given, the FE identity must cover the whole extracted package
    (manifest, geometry and mode files) and every file must be unchanged (``services.fe_package_identity``)."""
    from new_gui import preview_model as pm
    from services import fe_package_identity as fpi

    given = sources is not None
    sources = dict(sources or {})
    fe_read, experimental_read = sources.get("fe"), sources.get("experimental")
    if given or fe_read is not None:
        try:
            pm.confirm_fe_identity(fe_preview.manifest_path, fe_read, cancel_event)
        except fpi.PackageIdentityRefused as refusal:
            if refusal.kind == fpi.CANCELLED:
                raise ComparisonCancelled() from refusal
            raise ComparisonRefused(f"the FE package {fe_preview.manifest_path}: {refusal}") from refusal
        except fpi.PackageChanged as changed:
            raise ComparisonRefused(f"{changed}; the comparison is not run on data that no longer match the "
                                    "files. Inspect it again.") from changed
    if experimental_read is not None and experimental_now is not None \
            and experimental_now["sha256"] != experimental_read["sha256"]:
        raise ComparisonRefused(f"the experimental file is not the file that was read (SHA-256 "
                                f"{experimental_read['sha256'][:12]}… when read, {experimental_now['sha256'][:12]}… "
                                "now); Inspect it again.")
    return {"fe": fe_read, "experimental": experimental_read}


def compare(fe_preview, experimental_preview, set_index: int, registration_hash: Optional[str],
            cancel_event: Optional[threading.Event] = None, sources: Optional[dict] = None):
    """Verify the registration again and run the scientific comparator; returns (bound registration, result)."""
    if rm.set_is_provisional(experimental_preview, set_index):
        raise ComparisonRefused(PROVISIONAL_BLOCK)
    bound = rm.check(fe_preview, experimental_preview, set_index, cancel_event)  # fresh: raises its refusal
    if registration_hash is not None and bound.registration.registration_hash != registration_hash:
        raise ComparisonRefused(f"the verified registration is now {bound.registration.registration_hash[:12]}…, not "
                                f"the {registration_hash[:12]}… the check showed; check the registration again.")
    check_sources(fe_preview, sources, bound.experimental, cancel_event)
    if cancel_event is not None and cancel_event.is_set():
        raise ComparisonCancelled()
    from modal_core import compare_modal_datasets  # the reviewed quality-control facade (runtime_contracts)

    result = compare_modal_datasets(fe_preview.dataset, experimental_preview.sets[set_index].dataset,
                                    frozen_registration=bound.registration)
    result.metadata["geometry_verified_registration"] = bound.provenance()  # as runtime_hardening attaches it
    result.warnings.insert(0, bound.warning())
    return bound, result


@dataclass(frozen=True)
class ComparisonOutcome:
    """The end of one request: the comparator's result with its display wording, a refusal, an error or a
    cancellation."""

    token: int
    bound: Any = None  # GeometryVerifiedRegistration
    result: Any = None  # modal_core.ComparisonResult, as returned
    view: Any = None  # ComparisonView
    mac_image: bytes = b""
    sources: Any = None  # {"fe", "experimental"}: the identities recorded when the files were read (or None)
    refusal: str = ""
    error: str = ""
    cancelled: bool = False


def run_compare(fe_preview, experimental_preview, set_index: int, registration_hash: Optional[str], token: int,
                cancel_event: threading.Event, sources: Optional[dict] = None) -> ComparisonOutcome:
    """``compare`` and its display wording as an outcome; every failure becomes a message (worker thread)."""
    from services.new_odb_comparison import AcceptedReferenceRefusal

    try:
        with rm.SERVICE_LOCK:
            if cancel_event.is_set():  # cancelled while waiting: the comparator never runs
                return ComparisonOutcome(token, cancelled=True)
            bound, result = compare(fe_preview, experimental_preview, set_index, registration_hash, cancel_event,
                                    sources)
        if cancel_event.is_set():
            return ComparisonOutcome(token, cancelled=True)
        view = comparison_view(result, bound, fe_preview, experimental_preview, set_index)
        mac_image = render_mac_image(result, cancel_event)
    except (AcceptedReferenceRefusal, ComparisonRefused) as refusal:
        if cancel_event.is_set():
            return ComparisonOutcome(token, cancelled=True)
        return ComparisonOutcome(token, refusal=str(refusal))
    except Exception as error:  # noqa: BLE001  (cancellation, the comparator's errors or anything unexpected)
        if cancel_event.is_set() or type(error).__name__ in ("SensitivityCheckCancelled", "ComparisonCancelled"):
            return ComparisonOutcome(token, cancelled=True)
        return ComparisonOutcome(token, error=f"The comparison could not be completed ({type(error).__name__}: "
                                              f"{error}).")
    if cancel_event.is_set():  # the comparator does not stop midway: a late cancellation discards its result
        return ComparisonOutcome(token, cancelled=True)
    return ComparisonOutcome(token, bound=bound, result=result, view=view, mac_image=mac_image,
                             sources={"fe": (sources or {}).get("fe"),
                                      "experimental": (sources or {}).get("experimental")})


class ComparisonSlot:
    """The comparison request: only the outcome of the current request for the current inputs is shown."""

    def __init__(self) -> None:
        self.token = 0
        self.state = IDLE
        self.outcome: Optional[ComparisonOutcome] = None
        self.cancel_event: Optional[threading.Event] = None
        self.request: Any = None

    def start(self, request) -> tuple[int, threading.Event]:
        self.reset()
        self.state, self.request = RUNNING, request
        self.cancel_event = threading.Event()
        return self.token, self.cancel_event

    def reset(self) -> None:
        """Forget the result and cancel a running request (inputs replaced, another set, window closed)."""
        if self.cancel_event is not None:
            self.cancel_event.set()
        self.token += 1
        self.state, self.outcome, self.cancel_event, self.request = IDLE, None, None, None

    def finish(self, outcome: ComparisonOutcome) -> bool:
        if self.state != RUNNING or outcome.token != self.token:
            return False
        self.cancel_event = None
        if outcome.cancelled:
            self.state, self.request = IDLE, None
        elif outcome.view is not None:
            self.state, self.outcome = DONE, outcome
        elif outcome.refusal:
            self.state, self.outcome = REFUSED, outcome
        else:
            self.state, self.outcome = FAILED, outcome
        return True


# ---------------------------------------------------------------------------------------------- display wording


def _hz(value: Optional[float]) -> str:
    return DASH if value is None else f"{value:.4f}"


def _percent(value: Optional[float]) -> str:
    return DASH if value is None or not math.isfinite(value) else f"{value:+.2f}"


def _mac(value: Optional[float]) -> str:
    return MAC_NOT_COMPUTED if value is None or not math.isfinite(value) else f"{value:.3f}"


def _fraction(value: Optional[float]) -> str:
    return DASH if value is None or not math.isfinite(float(value)) else f"{100.0 * float(value):.0f} %"


def _record_positions(experimental_preview, set_index: int) -> dict:
    """Experimental mode number -> record position (1-based) in the chosen set, as the frequency diagnostic shows."""
    return {record.number: position + 1
            for position, record in enumerate(experimental_preview.sets[set_index].records)}


def _group_members(groups) -> dict:
    """Mode number -> the text of its close-mode group (the comparator's own groups)."""
    members = {}
    for group in groups or ():
        text = " / ".join(str(int(item["mode"])) for item in group)
        for item in group:
            members[int(item["mode"])] = text
    return members


@dataclass(frozen=True)
class PairRow:
    """One pair of ``ComparisonResult.pairs`` (its index there) with its display cells."""

    index: int
    abaqus_mode: int
    experimental_mode: int
    mac: Optional[float]
    frequency_error_percent: float
    cells: tuple


@dataclass(frozen=True)
class ComparisonView:
    status: str
    statement: str
    set_title: str
    specimen: str
    fixture_id: str
    registration: str
    registration_file: str
    pair_rows: tuple
    mac_fe_modes: tuple
    mac_experimental_modes: tuple
    mac_cells: tuple  # rows of formatted MAC values (FE rows x experimental columns)
    assigned_cells: frozenset  # (row, column) of the assigned pairs in the MAC table
    candidate_rows: tuple
    unmatched_fe_rows: tuple
    unmatched_experimental_rows: tuple
    unpaired_experimental: tuple  # every experimental record of the set without a pair
    rigid_rows: tuple
    close_groups: tuple
    warnings: tuple
    provenance: tuple  # (caption, value) of the registration and geometry facts
    gates: tuple  # (caption, value) of the comparator's admissibility gates, as recorded
    target_counts: str
    limits: tuple = LIMITS
    auto_id_note: str = AUTO_ID_NOTE


def comparison_view(result, bound, fe_preview, experimental_preview, set_index: int) -> ComparisonView:
    """The comparator's result worded for display; no value is computed, filtered or changed here."""
    import numpy as np

    positions = _record_positions(experimental_preview, set_index)
    metadata_fe = dict(getattr(result.abaqus, "metadata", None) or {})
    close_fe = _group_members(metadata_fe.get("close_abaqus_mode_groups"))
    close_exp = _group_members(metadata_fe.get("close_experimental_mode_groups"))
    rows = []
    for index, pair in enumerate(result.pairs):
        close = []
        if int(pair.abaqus_mode) in close_fe:
            close.append(f"FE {close_fe[int(pair.abaqus_mode)]}")
        if int(pair.experimental_mode) in close_exp:
            close.append(f"Exp {close_exp[int(pair.experimental_mode)]}")
        mac_text = _mac(pair.mac) if pair.mac is not None else f"{MAC_NOT_COMPUTED} ({MAC_MISSING_NOTE})"
        dof_count = getattr(pair, "measured_dof_count", None)
        cells = (str(pair.abaqus_mode), _hz(pair.abaqus_frequency_hz),
                 str(positions.get(pair.experimental_mode, DASH)), str(pair.experimental_mode),
                 _hz(pair.experimental_frequency_hz), _percent(pair.frequency_error_percent), mac_text,
                 str(pair.status), DASH if dof_count is None else str(dof_count),
                 _fraction(getattr(pair, "dof_coverage_fraction", None)), str(pair.mapped_points),
                 "changed" if pair.order_changed else "kept", "; ".join(close) or DASH, AUTO_ID_USE)
        rows.append(PairRow(index, int(pair.abaqus_mode), int(pair.experimental_mode), pair.mac,
                            float(pair.frequency_error_percent), cells))

    matrix = np.asarray(result.mac_matrix, dtype=float)
    fe_numbers = tuple(int(n) for n in result.abaqus_mode_numbers)
    exp_numbers = tuple(int(n) for n in result.experimental_mode_numbers)
    mac_cells = tuple(tuple(_mac(float(value)) if np.isfinite(value) else MAC_NOT_COMPUTED for value in row)
                      for row in matrix)
    assigned = frozenset((fe_numbers.index(int(p.abaqus_mode)), exp_numbers.index(int(p.experimental_mode)))
                         for p in result.pairs)

    assigned_pairs = {(int(p.abaqus_mode), int(p.experimental_mode)) for p in result.pairs}
    candidates = []
    best = (result.diagnostic_summaries or {}).get("best_mac_by_experimental") or []
    for number, candidate in zip(exp_numbers, best):
        if candidate is None:
            candidates.append((str(positions.get(number, DASH)), str(number), DASH, DASH, DASH, MAC_NOT_COMPUTED,
                               DASH, DASH, "no", "MAC not available on the measured DOFs", "no"))
            continue
        candidates.append((
            str(positions.get(candidate.experimental_mode, DASH)), str(candidate.experimental_mode),
            _hz(candidate.experimental_frequency_hz), str(candidate.abaqus_mode), _hz(candidate.abaqus_frequency_hz),
            _mac(candidate.mac), _percent(candidate.frequency_error_percent), str(candidate.coverage_status),
            "yes" if candidate.admissible else "no", ", ".join(candidate.rejection_reasons) or DASH,
            "yes" if (candidate.abaqus_mode, candidate.experimental_mode) in assigned_pairs else "no"))

    paired_exp = {int(p.experimental_mode) for p in result.pairs}
    unpaired = tuple(f"Exp record {position} (mode {record.number}, {record.frequency_hz:.4f} Hz)"
                     for position, record in ((positions[r.number], r)
                                              for r in experimental_preview.sets[set_index].records)
                     if record.number not in paired_exp)
    quality = dict(metadata_fe.get("quality_control") or {})
    residuals = quality.get("rigid_body_residual_fraction_by_mode") or {}
    fe_frequency = {int(m.number): float(m.frequency_hz) for m in fe_preview.modes}  # the read FE modes
    rigid_rows = tuple((str(n), _hz(fe_frequency.get(int(n))),
                        f"{float(residuals.get(int(n), residuals.get(str(n), float('nan')))):.2g}")
                       for n in quality.get("excluded_abaqus_modes") or ())
    close_groups = tuple(
        [f"FE modes {text}" for text in sorted(set(close_fe.values()))]
        + [f"Experimental modes {text}" for text in sorted(set(close_exp.values()))])

    provenance = bound.provenance()
    meta = dict(result.metadata or {})
    facts = [
        ("Specimen and fixture", f"{provenance['specimen']} — {provenance['fixture_id']}"),
        ("Frozen registration", f"{provenance['registration_hash']} ({provenance['registration_file']})"),
        ("Registration source", str(provenance["source"])),
        ("Archived modal set", str(provenance["modal_set"])),
        ("FE geometry identity", f"{provenance['fe_geometry_sha256']} ({provenance['fe_node_count']} nodes)"),
        ("Experimental SHA-256", str(provenance["experimental_sha256"])),
        ("Orientation source", str(meta.get("orientation_source", DASH))),
        ("Geometry candidates evaluated", str(meta.get("evaluated_geometry_candidate_count", DASH))),
        ("Mapping RMS / max residual (FE units)",
         f"{_float(meta.get('mapping_rms_in_abaqus_units'))} / {_float(meta.get('mapping_max_residual_in_abaqus_units'))}"),
        ("Matched point fraction", _fraction(getattr(result.geometry, "matched_fraction", None))),
        ("Comparator state", str(result.diagnostic_state)),
    ] + [(f"Check {number}", text) for number, text in enumerate(provenance["checks"], start=1)]
    gates = tuple((key.replace("_", " "), str(value))
                  for key, value in dict(meta.get("admissibility_gates") or {}).items())
    errors = [abs(r.frequency_error_percent) for r in rows]
    target = (f"Pairs with |error| ≤ 5 %: {sum(e <= 5.0 for e in errors)} of {len(errors)}; ≤ 10 %: "
              f"{sum(e <= 10.0 for e in errors)} of {len(errors)} (engineering target, not a criterion)."
              if errors else "No pair, so no frequency agreement is stated.")
    status = PAIRS_FOUND if result.pairs else NO_PAIR
    statement = (f"{status}: {len(result.pairs)} admissible pair{'s' if len(result.pairs) != 1 else ''} assigned by "
                 f"the comparator on the verified archived registration {provenance['fixture_id']}."
                 if result.pairs else f"{status}: {NO_PAIR_TEXT}")
    return ComparisonView(
        status=status, statement=statement, set_title=dm.set_title(experimental_preview, set_index),
        specimen=str(provenance["specimen"]), fixture_id=str(provenance["fixture_id"]),
        registration=str(provenance["registration_hash"]), registration_file=str(provenance["registration_file"]),
        pair_rows=tuple(rows), mac_fe_modes=fe_numbers, mac_experimental_modes=exp_numbers, mac_cells=mac_cells,
        assigned_cells=assigned, candidate_rows=tuple(candidates),
        unmatched_fe_rows=tuple((str(item["mode"]), _hz(item["frequency_hz"]))
                                for item in metadata_fe.get("unmatched_abaqus_modes") or ()),
        unmatched_experimental_rows=tuple((str(item["mode"]), _hz(item["frequency_hz"]))
                                          for item in metadata_fe.get("unmatched_experimental_candidates") or ()),
        unpaired_experimental=unpaired, rigid_rows=rigid_rows, close_groups=close_groups,
        warnings=tuple(str(w) for w in result.warnings), provenance=tuple(facts), gates=gates, target_counts=target)


def _float(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return DASH
    return f"{number:.4g}" if math.isfinite(number) else DASH


# ---------------------------------------------------------------------------------------------- images


def render_mac_image(result, cancel_event: Optional[threading.Event] = None) -> bytes:
    """The comparator's MAC matrix drawn by the program's final drawing owner, in a folder of this request only."""
    import reporting_hardening  # final owner of reporting.render_mac_matrix (src/main.py order)

    folder = Path(tempfile.mkdtemp(prefix="new_gui_mac_"))
    try:
        if cancel_event is not None and cancel_event.is_set():
            return b""
        with sm._RENDER:
            path = reporting_hardening.render_mac_matrix(result, folder / "mac_matrix.png")
        return Path(path).read_bytes()
    finally:
        shutil.rmtree(folder, ignore_errors=True)


@dataclass(frozen=True)
class PairImages:
    """The three images of one pair (FE and experimental on the registered points, amplitude correlation)."""

    token: int
    index: int
    images: tuple = ()  # (caption, PNG bytes)
    error: str = ""
    cancelled: bool = False


PAIR_CAPTIONS = (("abaqus", "FE (Abaqus) on the registered measured points"),
                 ("experimental", "Experimental on the same registered points"),
                 ("overlay", "Amplitude correlation (FE vs experimental)"))


def run_pair_images(result, index: int, token: int, cancel_event: threading.Event) -> PairImages:
    """Draw one pair with the program's final owner of ``reporting.render_pair_images``; no file is left."""
    import amplitude_correlation  # final owner of reporting.render_pair_images (runtime_contracts)

    folder = Path(tempfile.mkdtemp(prefix="new_gui_pair_"))
    try:
        if cancel_event.is_set():
            return PairImages(token, index, cancelled=True)
        with sm._RENDER:
            paths = amplitude_correlation.render_pair_images(result.pairs[index], folder)
        images = tuple((caption, Path(paths[key]).read_bytes()) for key, caption in PAIR_CAPTIONS)
        if cancel_event.is_set():
            return PairImages(token, index, cancelled=True)
        return PairImages(token, index, images=images)
    except Exception as error:  # noqa: BLE001
        if cancel_event.is_set():
            return PairImages(token, index, cancelled=True)
        return PairImages(token, index, error=f"The pair could not be drawn ({type(error).__name__}: {error}).")
    finally:
        shutil.rmtree(folder, ignore_errors=True)  # only this request's own folder


__all__ = ["ComparisonOutcome", "ComparisonRefused", "ComparisonSlot", "ComparisonView", "PairImages", "PairRow",
           "compare", "comparison_view", "render_mac_image", "run_compare", "run_pair_images", "unavailable"]
