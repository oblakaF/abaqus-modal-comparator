from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence


EM_DASH = "\u2014"


class LayoutMode(str, Enum):
    WIDE = "wide"
    MEDIUM = "medium"
    COMPACT = "compact"


class AnalysisState(str, Enum):
    NO_DATA = "no_data"
    READY = "ready"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    SUCCESS = "success"
    DIAGNOSTIC = "diagnostic"
    ERROR = "error"


FULL_TAB_LABELS = (
    "1. Files and analysis",
    "2. Comparison table",
    "3. Mode shapes",
    "4. MAC and frequencies",
    "5. FRF and quality",
    "6. Close modes \u2014 SVD",
    "7. AutoMAC and COMAC",
    "8. Manual review",
    "9. Details",
)

COMPACT_TAB_LABELS = (
    "1. Files",
    "2. Compare",
    "3. Shapes",
    "4. MAC",
    "5. FRF",
    "6. Close modes",
    "7. AutoMAC",
    "8. Review",
    "9. Details",
)


@dataclass(frozen=True)
class TableColumn:
    key: str
    heading: str
    width: int
    minimum: int
    anchor: str = "center"
    stretch: bool = False


COMPARISON_COLUMNS = (
    TableColumn("am", "Abaqus mode", 105, 90),
    TableColumn("em", "Experimental mode", 135, 115),
    TableColumn("af", "Abaqus frequency, Hz", 145, 125),
    TableColumn("ef", "Experimental frequency, Hz", 175, 145),
    TableColumn("err", "Frequency error, %", 135, 115),
    TableColumn("mac", "MAC", 80, 70),
    TableColumn("order", "Order changed", 115, 100),
    TableColumn("points", "Mapped points", 115, 100),
    TableColumn("status", "Status", 165, 130, "w", True),
    TableColumn("source", "Experimental source", 175, 145, "w", True),
    TableColumn("confidence", "Confidence", 145, 120, "w", True),
    TableColumn("manual", "Manual decision", 145, 120, "w", True),
    TableColumn("comment", "Comment", 240, 170, "w", True),
)

REVIEW_COLUMNS = (
    TableColumn("am", "Abaqus mode", 105, 90),
    TableColumn("af", "Abaqus frequency, Hz", 145, 125),
    TableColumn("auto_em", "Automatic experimental mode", 190, 155),
    TableColumn("current_em", "Reviewed experimental mode", 190, 155),
    TableColumn("ef", "Experimental frequency, Hz", 175, 145),
    TableColumn("err", "Frequency error, %", 135, 115),
    TableColumn("mac", "MAC", 80, 70),
    TableColumn("auto_status", "Automatic status", 160, 130, "w", True),
    TableColumn("decision", "Manual decision", 145, 120, "w", True),
    TableColumn("comment", "Comment", 280, 180, "w", True),
)

CANDIDATE_COLUMNS = (
    TableColumn("em", "Experimental mode", 135, 115),
    TableColumn("freq", "Experimental frequency, Hz", 175, 145),
    TableColumn("error", "Frequency error, %", 135, 115),
    TableColumn("mac", "MAC", 80, 70),
    TableColumn("source", "Experimental source", 190, 150, "w", True),
)

TABLE_COLUMN_POLICIES = {
    "comparison": COMPARISON_COLUMNS,
    "manual_review": REVIEW_COLUMNS,
    "candidate": CANDIDATE_COLUMNS,
}


STYLE_TOKENS = {
    "font_family": "Segoe UI",
    "application_title_size": 20,
    "section_title_size": 11,
    "metric_caption_size": 9,
    "metric_value_size": 18,
    "body_size": 10,
    "secondary_size": 9,
    "table_size": 9,
    "status_size": 9,
    "section_padding": 12,
    "section_spacing": 10,
    "row_spacing": 6,
    "table_row_height": 28,
}

UI_SCALE_PERCENT_VALUES = (80, 90, 100, 110, 125)

# This is the smallest physical desktop window that keeps the nine-tab
# notebook, primary file controls, and run/stop actions usable.  Interface
# scale remains an independent presentation preference; the vertically
# scrollable input page absorbs the additional height required at 125%.
MINIMUM_WINDOW_SIZE = (1120, 700)


UNIT_TO_METRES = {
    "mm": 1.0e-3,
    "m": 1.0,
    "cm": 1.0e-2,
    "\u00b5m": 1.0e-6,
}


def select_layout_mode(width: int) -> LayoutMode:
    width = max(1, int(width))
    if width >= 1500:
        return LayoutMode.WIDE
    if width >= 1120:
        return LayoutMode.MEDIUM
    return LayoutMode.COMPACT


def normalize_ui_scale_percent(value: object) -> int:
    try:
        percent = int(value)
    except (TypeError, ValueError):
        return 100
    return percent if percent in UI_SCALE_PERCENT_VALUES else 100


class SettledCallback:
    """One cancel-and-replace callback for the settled phase of a burst."""

    def __init__(self, scheduler, delay_ms: int, callback) -> None:
        self.scheduler = scheduler
        self.delay_ms = int(delay_ms)
        self.callback = callback
        self.job = None
        self.scheduled_count = 0
        self.cancelled_count = 0
        self.executed_count = 0

    def schedule(self):
        if self.job is not None:
            try:
                self.scheduler.after_cancel(self.job)
                self.cancelled_count += 1
            except Exception:
                pass
        self.scheduled_count += 1
        self.job = self.scheduler.after(self.delay_ms, self._run)
        return self.job

    def _run(self) -> None:
        self.job = None
        self.executed_count += 1
        self.callback()

    def cancel(self) -> None:
        if self.job is None:
            return
        try:
            self.scheduler.after_cancel(self.job)
            self.cancelled_count += 1
        except Exception:
            pass
        self.job = None


def logical_window_width(pixel_width: int, tk_scaling: float) -> int:
    """Normalize Tk's DPI-scaled pixel width to a 96-DPI layout width."""
    try:
        pixels = max(1.0, float(pixel_width))
        scaling = max(0.1, float(tk_scaling))
    except (TypeError, ValueError):
        return max(1, int(pixel_width))
    baseline = 96.0 / 72.0
    return max(1, int(round(pixels / (scaling / baseline))))


def responsive_layout_width(
    pixel_width: int,
    tk_scaling: float,
    ui_scale_percent: object,
) -> int:
    """Return layout width without mutating the independent UI-scale setting."""
    scale = normalize_ui_scale_percent(ui_scale_percent) / 100.0
    return max(1, int(round(logical_window_width(pixel_width, tk_scaling) / scale)))


def minimum_window_size() -> tuple[int, int]:
    return MINIMUM_WINDOW_SIZE


def metric_grid_columns(mode: LayoutMode, width: Optional[int] = None) -> int:
    if mode is LayoutMode.WIDE:
        return 4
    if mode is LayoutMode.COMPACT and width is not None and int(width) < 720:
        return 1
    return 2


def tab_labels_for(mode: LayoutMode) -> tuple[str, ...]:
    return FULL_TAB_LABELS if mode is LayoutMode.WIDE else COMPACT_TAB_LABELS


def text_wrap_width(width: int, mode: Optional[LayoutMode] = None) -> int:
    width = max(1, int(width))
    mode = mode or select_layout_mode(width)
    margin = {
        LayoutMode.WIDE: 210,
        LayoutMode.MEDIUM: 150,
        LayoutMode.COMPACT: 95,
    }[mode]
    return max(280, min(1320, width - margin))


def responsive_padding(mode: LayoutMode) -> tuple[int, int]:
    if mode is LayoutMode.WIDE:
        return 16, 12
    if mode is LayoutMode.MEDIUM:
        return 12, 9
    return 8, 6


def button_grid_columns(mode: LayoutMode, button_count: int) -> int:
    count = max(1, int(button_count))
    if mode is LayoutMode.WIDE:
        return count
    if mode is LayoutMode.MEDIUM:
        return min(3, count)
    return min(2, count)


def table_width_policy(table_kind: str) -> tuple[TableColumn, ...]:
    try:
        return TABLE_COLUMN_POLICIES[table_kind]
    except KeyError as error:
        raise ValueError(f"Unknown table kind: {table_kind}") from error


def non_empty_headings(
    columns: Sequence[str], headings: Mapping[str, str]
) -> bool:
    return all(bool(str(headings.get(str(column), "")).strip()) for column in columns)


def validate_custom_scale(value: str | float) -> float:
    try:
        scale = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError) as error:
        raise ValueError("Enter a positive custom scale factor.") from error
    if scale <= 0.0:
        raise ValueError("Enter a positive custom scale factor.")
    return scale


def coordinate_scale_from_units(
    abaqus_model_unit: str,
    experimental_unit: str,
) -> float:
    if abaqus_model_unit == "custom" or experimental_unit == "custom":
        raise ValueError("Choose named units or use Custom scale factor.")
    try:
        return UNIT_TO_METRES[abaqus_model_unit] / UNIT_TO_METRES[experimental_unit]
    except KeyError as error:
        raise ValueError("Choose valid Abaqus and experimental coordinate units.") from error


def experimental_unit_from_metadata(metadata: Mapping[str, object]) -> tuple[str, str]:
    description = str(metadata.get("units_description") or "").lower()
    descriptions = (
        ("millimet", "mm"),
        ("millimeter", "mm"),
        ("microm", "\u00b5m"),
        ("centimet", "cm"),
        ("centimeter", "cm"),
        ("metre", "m"),
        ("meter", "m"),
    )
    for token, unit in descriptions:
        if token in description:
            return unit, "detected from UNV metadata"

    length_scale = metadata.get("length_scale")
    try:
        numeric = float(length_scale)
    except (TypeError, ValueError):
        numeric = 0.0
    for unit, scale in UNIT_TO_METRES.items():
        if abs(numeric - scale) <= max(1.0e-12, abs(scale) * 1.0e-9):
            return unit, "inferred from UNV length scale"
    return "m", "inferred; verify for this test setup"


@dataclass(frozen=True)
class AbaqusInstallation:
    label: str
    command: str
    detected: bool = True
    fallback_commands: tuple[str, ...] = ()


def _launcher_version(paths: Sequence[Path]) -> Optional[str]:
    for path in paths:
        match = re.search(r"(?:abq|abaqus)[-_ ]?(20\d{2})", path.stem, re.IGNORECASE)
        if match:
            return match.group(1)
    for path in paths:
        match = re.search(r"(?:^|[\\/])(20\d{2})(?:[\\/]|$)", str(path))
        if match:
            return match.group(1)
    return None


def _installation_label(command: str, version: Optional[str] = None) -> str:
    version = version or _launcher_version((Path(command),))
    if version:
        return f"Abaqus {version} \u2014 detected \u2713"
    return "Abaqus \u2014 detected \u2713"


def _referenced_launcher(path: Path) -> Optional[Path]:
    """Return the next launcher referenced by a small batch wrapper, if any."""
    if path.suffix.lower() not in {".bat", ".cmd"}:
        return None
    try:
        contents = path.read_text(encoding="utf-8", errors="ignore")[:65_536]
    except OSError:
        return None

    candidates = re.findall(r'"([^"\r\n]+\.(?:bat|cmd|exe))"', contents, re.IGNORECASE)
    candidates.extend(
        re.findall(
            r"(?:^|\s)([^\s\"']+\.(?:bat|cmd|exe))(?=\s|$)",
            contents,
            re.IGNORECASE | re.MULTILINE,
        )
    )
    for value in candidates:
        expanded = value.replace("%~dp0", str(path.parent) + os.sep)
        expanded = os.path.expandvars(expanded)
        candidate = Path(expanded)
        if not candidate.is_absolute():
            local = path.parent / candidate
            resolved = local if local.is_file() else Path(shutil.which(str(candidate)) or "")
        else:
            resolved = candidate
        try:
            if resolved.is_file() and resolved.resolve() != path.resolve():
                return resolved.resolve()
        except OSError:
            continue
    return None


def _launcher_chain(command: str) -> tuple[Path, ...]:
    current = Path(command).resolve()
    chain = [current]
    seen = {str(current).lower()}
    for _ in range(8):
        referenced = _referenced_launcher(current)
        if referenced is None or str(referenced).lower() in seen:
            break
        chain.append(referenced)
        seen.add(str(referenced).lower())
        current = referenced
    return tuple(chain)


def _prefer_explicit_launcher(commands: Sequence[str]) -> str:
    def score(command: str) -> tuple[int, int, str]:
        path = Path(command)
        explicit = _launcher_version((path,)) is not None
        batch_wrapper = path.suffix.lower() in {".bat", ".cmd"}
        return (int(explicit), int(batch_wrapper), command.lower())

    return max(commands, key=score)


def discover_abaqus_installations(
    *,
    path: Optional[str] = None,
    search_directories: Optional[Iterable[Path]] = None,
) -> tuple[AbaqusInstallation, ...]:
    """Return only launchers that actually exist on this Windows installation."""
    found: dict[str, AbaqusInstallation] = {}
    environment_path = os.environ.get("PATH", "") if path is None else path
    candidate_names = ["abaqus"] + [f"abq{year}" for year in range(2017, 2036)]
    for name in candidate_names:
        resolved = shutil.which(name, path=environment_path)
        if resolved:
            canonical = str(Path(resolved).resolve())
            found[canonical.lower()] = AbaqusInstallation(
                _installation_label(canonical), canonical
            )

    directories = list(search_directories or ())
    if os.name == "nt" and search_directories is None:
        directories.extend(
            [
                Path("C:/SIMULIA/Commands"),
                Path("C:/Program Files/Dassault Systemes/SimulationServices"),
            ]
        )
    patterns = ("abaqus*.bat", "abaqus*.cmd", "abaqus*.exe", "abq20*.bat", "abq20*.cmd", "abq20*.exe")
    for directory in directories:
        if not directory.is_dir():
            continue
        for pattern in patterns:
            try:
                candidates = directory.glob(pattern)
                for candidate in candidates:
                    if candidate.is_file():
                        canonical = str(candidate.resolve())
                        found[canonical.lower()] = AbaqusInstallation(
                            _installation_label(canonical), canonical
                        )
            except OSError:
                continue

    equivalent: dict[str, list[str]] = {}
    chains: dict[str, tuple[Path, ...]] = {}
    for installation in found.values():
        chain = _launcher_chain(installation.command)
        identity = str(chain[-1]).lower()
        equivalent.setdefault(identity, []).append(installation.command)
        chains[installation.command.lower()] = chain

    deduplicated = []
    for commands in equivalent.values():
        preferred = _prefer_explicit_launcher(commands)
        chain = chains[preferred.lower()]
        version = _launcher_version(chain)
        fallbacks = tuple(
            command for command in sorted(commands, key=str.lower) if command != preferred
        )
        deduplicated.append(
            AbaqusInstallation(
                _installation_label(preferred, version),
                preferred,
                fallback_commands=fallbacks,
            )
        )

    installations = sorted(
        deduplicated, key=lambda item: (item.label.lower(), item.command.lower())
    )
    label_counts: dict[str, int] = {}
    for installation in installations:
        label_counts[installation.label] = label_counts.get(installation.label, 0) + 1
    return tuple(
        installation
        if label_counts[installation.label] == 1
        else AbaqusInstallation(
            f"{installation.label} [{installation.command}]",
            installation.command,
            installation.detected,
            installation.fallback_commands,
        )
        for installation in installations
    )


def select_abaqus_installation(
    installations: Sequence[AbaqusInstallation],
    current_command: str = "",
) -> Optional[AbaqusInstallation]:
    if current_command:
        current = str(Path(resolve_command(current_command) or current_command).expanduser()).lower()
        for installation in installations:
            commands = (installation.command, *installation.fallback_commands)
            if any(command.lower() == current for command in commands):
                return installation
    return installations[0] if len(installations) == 1 else None


def resolve_command(command: str) -> Optional[str]:
    value = str(command or "").strip().strip('"')
    if not value:
        return None
    path = Path(value)
    if path.is_file():
        if os.name == "nt":
            executable_suffixes = {
                item.lower()
                for item in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";")
                if item
            }
            if path.suffix.lower() not in executable_suffixes:
                return None
        elif not os.access(path, os.X_OK):
            return None
        return str(path.resolve())
    return shutil.which(value)


_TRANSITIONS = {
    (AnalysisState.NO_DATA, "inputs_ready"): AnalysisState.READY,
    (AnalysisState.READY, "inputs_missing"): AnalysisState.NO_DATA,
    (AnalysisState.STOPPED, "inputs_ready"): AnalysisState.READY,
    (AnalysisState.ERROR, "inputs_ready"): AnalysisState.READY,
    (AnalysisState.SUCCESS, "run"): AnalysisState.RUNNING,
    (AnalysisState.DIAGNOSTIC, "run"): AnalysisState.RUNNING,
    (AnalysisState.STOPPED, "run"): AnalysisState.RUNNING,
    (AnalysisState.ERROR, "run"): AnalysisState.RUNNING,
    (AnalysisState.READY, "run"): AnalysisState.RUNNING,
    (AnalysisState.RUNNING, "stop"): AnalysisState.STOPPING,
    (AnalysisState.STOPPING, "stopped"): AnalysisState.STOPPED,
    (AnalysisState.RUNNING, "success"): AnalysisState.SUCCESS,
    (AnalysisState.RUNNING, "diagnostic"): AnalysisState.DIAGNOSTIC,
    (AnalysisState.RUNNING, "error"): AnalysisState.ERROR,
}


def transition_analysis_state(state: AnalysisState, event: str) -> AnalysisState:
    try:
        return _TRANSITIONS[(AnalysisState(state), str(event))]
    except KeyError as error:
        raise ValueError(f"Invalid analysis transition: {state} + {event}") from error


def completion_state(automatic_pair_count: int) -> AnalysisState:
    """Classify completion from scientific automatic acceptance only."""
    return AnalysisState.SUCCESS if int(automatic_pair_count) > 0 else AnalysisState.DIAGNOSTIC


def status_text(state: AnalysisState, *, pair_count: Optional[int] = None) -> str:
    messages = {
        AnalysisState.NO_DATA: "Select Abaqus and experimental files.",
        AnalysisState.READY: "Ready to analyze.",
        AnalysisState.RUNNING: "Analysis is running.",
        AnalysisState.STOPPING: "Stopping analysis...",
        AnalysisState.STOPPED: "Analysis stopped by user.",
        AnalysisState.ERROR: "Analysis could not be completed.",
    }
    if state is AnalysisState.SUCCESS:
        return f"Analysis complete \u2014 {int(pair_count or 0)} admissible pairs."
    if state is AnalysisState.DIAGNOSTIC:
        return (
            "Analysis complete \u2014 0 admissible pairs. "
            "Scientific acceptance gates were not satisfied."
        )
    return messages[state]


class DirtyTracker:
    def __init__(self) -> None:
        self._baseline = ""
        self._current = ""

    @staticmethod
    def _encode(payload: Mapping[str, object]) -> str:
        return json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)

    def reset(self, payload: Mapping[str, object]) -> None:
        encoded = self._encode(payload)
        self._baseline = encoded
        self._current = encoded

    def update(self, payload: Mapping[str, object]) -> bool:
        self._current = self._encode(payload)
        return self.dirty

    @property
    def dirty(self) -> bool:
        return self._current != self._baseline


class CloseDecision(str, Enum):
    STOP_AND_CLOSE = "stop_and_close"
    KEEP_RUNNING = "keep_running"
    SAVE = "save"
    DISCARD = "discard"
    CANCEL = "cancel"
    CLOSE = "close"


def close_decision(
    *,
    running: bool,
    dirty: bool,
    running_choice: Optional[str] = None,
    save_choice: Optional[str] = None,
) -> CloseDecision:
    if running:
        if running_choice == "stop":
            return CloseDecision.STOP_AND_CLOSE
        return CloseDecision.KEEP_RUNNING
    if dirty:
        if save_choice == "save":
            return CloseDecision.SAVE
        if save_choice == "discard":
            return CloseDecision.DISCARD
        return CloseDecision.CANCEL
    return CloseDecision.CLOSE


DEFAULT_RECOVERY_PREFERENCES = {
    "autosave_enabled": True,
    "restore_on_startup": True,
    "show_recovery_notice": True,
    "ui_scale_percent": 100,
}


def normalize_recovery_preferences(value: object) -> dict[str, object]:
    output = dict(DEFAULT_RECOVERY_PREFERENCES)
    if isinstance(value, Mapping):
        for key in ("autosave_enabled", "restore_on_startup", "show_recovery_notice"):
            if key in value:
                output[key] = bool(value[key])
        output["ui_scale_percent"] = normalize_ui_scale_percent(
            value.get("ui_scale_percent", 100)
        )
    return output
