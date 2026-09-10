from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional

import numpy as np


UNIT_TO_METRES = {
    "mm": 1.0e-3,
    "m": 1.0,
    "cm": 1.0e-2,
    "µm": 1.0e-6,
}

CALIBRATED_PHYSICAL = "calibrated_physical"
CAMERA_GRID = "camera_grid"
MANUAL = "manual"
LEGACY_GEOMETRIC_FIT = "legacy_geometric_fit"


@dataclass(frozen=True)
class CoordinateCalibration:
    """Reproducible geometry-calibration inputs, separate from registration."""

    mode: str
    abaqus_unit: str = "mm"
    experimental_unit: str = "m"
    scan_coverage: Optional[str] = None
    physical_width: Optional[float] = None
    physical_height: Optional[float] = None
    dimension_unit: Optional[str] = None
    provenance: str = ""
    manual_scale: Optional[float] = None

    def validate(self) -> None:
        if self.mode not in {
            CALIBRATED_PHYSICAL,
            CAMERA_GRID,
            MANUAL,
            LEGACY_GEOMETRIC_FIT,
        }:
            raise ValueError(f"Unknown coordinate calibration mode: {self.mode}")
        if self.abaqus_unit not in UNIT_TO_METRES:
            raise ValueError("Choose a valid Abaqus model length unit.")
        if self.mode == CALIBRATED_PHYSICAL:
            if self.experimental_unit not in UNIT_TO_METRES:
                raise ValueError("Choose a valid experimental coordinate unit.")
        elif self.mode == CAMERA_GRID:
            if self.scan_coverage not in {"full", "partial"}:
                raise ValueError("Choose Full specimen or Partial region scan coverage.")
            if self.dimension_unit not in UNIT_TO_METRES:
                raise ValueError("Choose a valid physical-dimension unit.")
            if self.physical_width is None or self.physical_height is None:
                if self.scan_coverage == "partial":
                    raise ValueError(
                        "A partial camera-grid scan requires the physical scan-window width and height; specimen dimensions alone must not be used."
                    )
                raise ValueError("Enter the physical specimen width and height for the full scan.")
            if not np.isfinite(self.physical_width) or self.physical_width <= 0:
                raise ValueError("Physical scan width must be a positive number.")
            if not np.isfinite(self.physical_height) or self.physical_height <= 0:
                raise ValueError("Physical scan height must be a positive number.")
        elif self.mode == MANUAL:
            if self.manual_scale is None or not np.isfinite(self.manual_scale) or self.manual_scale <= 0:
                raise ValueError("Manual coordinate scale must be a positive number.")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CoordinateCalibration":
        calibration = cls(
            mode=str(value.get("mode", LEGACY_GEOMETRIC_FIT)),
            abaqus_unit=str(value.get("abaqus_unit", "mm")),
            experimental_unit=str(value.get("experimental_unit", "m")),
            scan_coverage=value.get("scan_coverage"),
            physical_width=_optional_float(value.get("physical_width")),
            physical_height=_optional_float(value.get("physical_height")),
            dimension_unit=value.get("dimension_unit"),
            provenance=str(value.get("provenance", "")),
            manual_scale=_optional_float(value.get("manual_scale")),
        )
        calibration.validate()
        return calibration


def _optional_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    return float(str(value).replace(",", "."))


def scale_candidates(
    calibration: CoordinateCalibration,
    experimental_coordinates: np.ndarray,
) -> list[tuple[np.ndarray, dict[str, Any]]]:
    """Return admissible coordinate-scale vectors before registration.

    Scale components use the comparator's convention: FE coordinates are
    multiplied by them to enter the experimental raw-coordinate system.
    """
    calibration.validate()
    base = calibration.to_dict()
    if calibration.mode == CALIBRATED_PHYSICAL:
        scale = UNIT_TO_METRES[calibration.abaqus_unit] / UNIT_TO_METRES[calibration.experimental_unit]
        details = {**base, "scale_x": scale, "scale_y": scale, "axes_swapped": False}
        return [(np.full(3, scale, dtype=float), details)]
    if calibration.mode == MANUAL:
        scale = float(calibration.manual_scale)
        details = {**base, "scale_x": scale, "scale_y": scale, "axes_swapped": False}
        return [(np.full(3, scale, dtype=float), details)]
    if calibration.mode == LEGACY_GEOMETRIC_FIT:
        return []

    coordinates = np.asarray(experimental_coordinates, dtype=float)
    raw_span = np.ptp(coordinates, axis=0)
    if raw_span[0] <= 1.0e-30 or raw_span[1] <= 1.0e-30:
        raise ValueError("Camera-grid calibration requires non-zero raw X and Y spans.")
    width_model = (
        float(calibration.physical_width)
        * UNIT_TO_METRES[str(calibration.dimension_unit)]
        / UNIT_TO_METRES[calibration.abaqus_unit]
    )
    height_model = (
        float(calibration.physical_height)
        * UNIT_TO_METRES[str(calibration.dimension_unit)]
        / UNIT_TO_METRES[calibration.abaqus_unit]
    )
    output: list[tuple[np.ndarray, dict[str, Any]]] = []
    for swapped, target_x, target_y in (
        (False, width_model, height_model),
        (True, height_model, width_model),
    ):
        scale_x = float(raw_span[0] / target_x)
        scale_y = float(raw_span[1] / target_y)
        # The camera-grid plane has no independently calibrated depth. Its
        # geometric mean is harmless for a constant camera Z and avoids a
        # hidden affine/shear degree of freedom.
        scale_z = float(np.sqrt(scale_x * scale_y))
        scales = np.array([scale_x, scale_y, scale_z], dtype=float)
        details = {
            **base,
            "raw_span_x": float(raw_span[0]),
            "raw_span_y": float(raw_span[1]),
            "target_width_in_abaqus_units": width_model,
            "target_height_in_abaqus_units": height_model,
            "scale_x": scale_x,
            "scale_y": scale_y,
            "axes_swapped": swapped,
        }
        output.append((scales, details))
    return output


def legacy_project_calibration(inputs: Mapping[str, Any]) -> CoordinateCalibration:
    """Migrate schema-v1 coordinate_scale without changing its old meaning."""
    legacy = str(inputs.get("coordinate_scale", "auto")).strip().lower()
    if legacy in {"", "auto", "automatic"}:
        return CoordinateCalibration(
            mode=LEGACY_GEOMETRIC_FIT,
            provenance="Legacy project: coordinate_scale='auto' retained as extent-based geometric fit.",
        )
    return CoordinateCalibration(
        mode=MANUAL,
        manual_scale=float(legacy.replace(",", ".")),
        provenance="Legacy project: numeric coordinate scale retained as manual override.",
    )
