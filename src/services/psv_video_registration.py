"""Physical scan-to-panel registration from a stored Polytec PSV measurement — Auto-ID M6 / SP-13 gate
(SPEC §4.1, §11, §15; D-007; M6_DECISION_RECORD §17).

Read-only reconstruction of where the scan points lay on the physical panel, using only what the PSV
file stored at acquisition time:

- the camera frame (``Info/VideoBitmap``, JPEG);
- the per-point video coordinates (``Info/Geometry/MeasPoints``, normalised u, v);
- the default full-frame rectangle (``Info/APS_Mixed/MeshObject1/DefaultSettings``), which fixes the
  pixel normalisation;
- the video 2D-alignment points (``Info/VideoSettings``: scanner angles ↔ u, v), used only as an
  isotropy check;
- the UNV metric scan coordinates, used only to validate the parser (point order and geometry).

The panel edges are fitted in the frame. The physical scale comes from the measured panel
dimensions (spec, ruler and calipers; no instrument uncertainty recorded). **No modal data and no
MAC are used anywhere in this module**: the registration is fixed before any pairing is evaluated.
"""

from __future__ import annotations

import hashlib
import io
import math
import struct
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

SCHEMA = "auto-id/psv-physical-registration-reconstruction/v1"
_END, _FREE = 0xFFFFFFFE, 0xFFFFFFFF

# Edge-fitting method constants (image analysis, not physical thresholds; recorded with every result).
EDGE_SEARCH_WINDOW_PX = 150  # search band outward from the scan-grid hull
EDGE_MIN_STEP = 40.0  # grey-level step panel -> surroundings
EDGE_MIN_GRADIENT = 4.0  # local gradient maximum must exceed this
EDGE_CLUSTER_GAP_PX = 8.0  # samples farther apart than this belong to different structures
EDGE_CLUSTER_MIN_SHARE = 0.3  # the nearest cluster holding >= 30 % of samples is the panel edge
EDGE_CLIP_SIGMA = 2.5
EDGE_SAMPLES = 120
MEASPOINT_RECORD_BYTES = 40
MEASPOINT_UV_OFFSET = 106  # byte offset of (u, v) float32 of record 0 (validated against the UNV)


class PSVRegistrationError(ValueError):
    """The stored PSV data cannot support a reconstruction (format, validation or geometry failure)."""


# ----------------------------------------------------------------------------- compound file (OLE2) reader

class CompoundFile:
    """Minimal read-only Compound File Binary reader (the container format of Polytec .svd files)."""

    def __init__(self, data: bytes) -> None:
        if data[:8] != bytes.fromhex("d0cf11e0a1b11ae1"):
            raise PSVRegistrationError("not a compound file (.svd)")
        self.data = data
        self.sector = 1 << struct.unpack_from("<H", data, 30)[0]
        self.mini = 1 << struct.unpack_from("<H", data, 32)[0]
        n_fat = struct.unpack_from("<I", data, 44)[0]
        first_dir = struct.unpack_from("<I", data, 48)[0]
        self.cutoff = struct.unpack_from("<I", data, 56)[0]
        first_minifat = struct.unpack_from("<I", data, 60)[0]
        first_difat, n_difat = struct.unpack_from("<II", data, 68)
        difat = list(struct.unpack_from("<109I", data, 76))
        sect = first_difat
        for _ in range(n_difat):
            values = struct.unpack_from(f"<{self.sector // 4}I", data, self._offset(sect))
            difat += values[:-1]
            sect = values[-1]
        self.fat: list[int] = []
        for s in [s for s in difat if s not in (_FREE, _END)][:n_fat]:
            self.fat += struct.unpack_from(f"<{self.sector // 4}I", data, self._offset(s))
        directory = self._chain(first_dir)
        self.entries = []
        for k in range(len(directory) // 128):
            e = directory[k * 128:(k + 1) * 128]
            length = struct.unpack_from("<H", e, 64)[0]
            left, right, child = struct.unpack_from("<iii", e, 68)
            self.entries.append({"name": e[:max(0, length - 2)].decode("utf-16-le", "replace"), "type": e[66],
                                 "left": left, "right": right, "child": child,
                                 "start": struct.unpack_from("<I", e, 116)[0],
                                 "size": struct.unpack_from("<Q", e, 120)[0] & 0xFFFFFFFF})
        root = self.entries[0]
        self.mini_stream = self._chain(root["start"])[:root["size"]]
        raw = self._chain(first_minifat) if first_minifat != _END else b""
        self.minifat = list(struct.unpack_from(f"<{len(raw) // 4}I", raw)) if raw else []
        self.paths: dict[str, dict] = {}
        self._walk(root["child"], "")

    def _offset(self, sect: int) -> int:
        return (sect + 1) * self.sector

    def _chain(self, start: int) -> bytes:
        out, s, seen = bytearray(), start, set()
        while s not in (_END, _FREE) and s < len(self.fat) and s not in seen:
            seen.add(s)
            out += self.data[self._offset(s):self._offset(s) + self.sector]
            s = self.fat[s]
        return bytes(out)

    def _walk(self, index: int, prefix: str) -> None:
        if index < 0 or index >= len(self.entries):
            return
        entry = self.entries[index]
        self._walk(entry["left"], prefix)
        self.paths[prefix + entry["name"]] = entry
        if entry["type"] == 1:
            self._walk(entry["child"], prefix + entry["name"] + "/")
        self._walk(entry["right"], prefix)

    def read(self, path: str) -> bytes:
        if path not in self.paths:
            raise PSVRegistrationError(f"stream {path!r} not present in the .svd")
        entry = self.paths[path]
        if entry["size"] < self.cutoff:
            out, s = bytearray(), entry["start"]
            while s not in (_END, _FREE) and s < len(self.minifat):
                out += self.mini_stream[s * self.mini:(s + 1) * self.mini]
                s = self.minifat[s]
            return bytes(out[:entry["size"]])
        return self._chain(entry["start"])[:entry["size"]]


# ----------------------------------------------------------------------------- PSV records

def measpoints_uv(blob: bytes, count: int) -> np.ndarray:
    """Normalised video coordinates (u, v) of the scan points, in record order."""
    end = MEASPOINT_UV_OFFSET + MEASPOINT_RECORD_BYTES * (count - 1) + 8
    if len(blob) < end:
        raise PSVRegistrationError("MeasPoints stream is shorter than the scan-point count requires")
    return np.array([struct.unpack_from("<ff", blob, MEASPOINT_UV_OFFSET + MEASPOINT_RECORD_BYTES * k)
                     for k in range(count)], dtype=float)


def default_rectangle(blob: bytes) -> tuple[float, float, float, float]:
    """Full-frame rectangle (u_min, v_min, u_max, v_max) stored in the mesh default settings."""
    u0, v0, u1, v1 = struct.unpack_from("<4f", blob, 12)
    if not (u1 > u0 and v1 > v0):
        raise PSVRegistrationError("default full-frame rectangle is not a valid rectangle")
    return float(u0), float(v0), float(u1), float(v1)


def alignment_points(blob: bytes) -> np.ndarray:
    """2D video alignment: rows (scanner angle a, angle b, u, v)."""
    start = blob.find(bytes.fromhex("13000000"))
    if start < 0:
        raise PSVRegistrationError("video alignment table not found")
    count = struct.unpack_from("<I", blob, start)[0]
    rows = [struct.unpack_from("<Iddff", blob, start + 4 + 28 * k)[1:] for k in range(count)]
    return np.array(rows, dtype=float)


def video_frame(blob: bytes):
    from PIL import Image

    start = blob.find(bytes.fromhex("ffd8ff"))
    if start < 0:
        raise PSVRegistrationError("VideoBitmap holds no JPEG frame")
    image = Image.open(io.BytesIO(blob[start:]))
    image.load()
    return image


# ----------------------------------------------------------------------------- geometry helpers

def homography(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    rows = []
    for (x, y), (u, v) in zip(source, target):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y, -u])
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y, -v])
    _, _, vt = np.linalg.svd(np.array(rows, dtype=float))
    h = vt[-1].reshape(3, 3)
    return h / h[2, 2]


def apply_homography(h: np.ndarray, points: np.ndarray) -> np.ndarray:
    p = np.column_stack([points, np.ones(len(points))]) @ h.T
    return p[:, :2] / p[:, 2:3]


def _edge_position(profile: np.ndarray, start: int, direction: int) -> float | None:
    stop = start + direction * EDGE_SEARCH_WINDOW_PX
    lo, hi = sorted((start, stop))
    lo, hi = max(lo, 2), min(hi, len(profile) - 3)
    segment = profile[lo:hi + 1].astype(float)
    if direction < 0:
        segment = segment[::-1]
    smooth = np.convolve(segment, np.ones(3) / 3.0, mode="same")
    gradient = np.gradient(smooth)
    for j in range(3, len(gradient) - 6):
        if gradient[j] >= gradient[j - 1] and gradient[j] >= gradient[j + 1] and gradient[j] > EDGE_MIN_GRADIENT:
            if smooth[j + 2:j + 6].mean() - smooth[max(j - 6, 0):j - 2].mean() >= EDGE_MIN_STEP:
                a, b, c = gradient[j - 1], gradient[j], gradient[j + 1]
                offset = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
                return start + direction * (j + offset)
    return None


def fit_panel_edges(gray: np.ndarray, grid_px: np.ndarray) -> dict:
    """Four panel edge lines (x = a*y + b for left/right, y = a*x + b for top/bottom) with residuals."""
    x0, x1 = grid_px[:, 0].min(), grid_px[:, 0].max()
    y0, y1 = grid_px[:, 1].min(), grid_px[:, 1].max()
    lines = {}
    for side in ("left", "right", "top", "bottom"):
        samples = []
        if side in ("left", "right"):
            for r in np.linspace(y0, y1, EDGE_SAMPLES).astype(int):
                p = _edge_position(gray[r], int(x0 if side == "left" else x1), -1 if side == "left" else 1)
                if p is not None:
                    samples.append((r, p))
        else:
            for c in np.linspace(x0, x1, EDGE_SAMPLES).astype(int):
                p = _edge_position(gray[:, c], int(y0 if side == "top" else y1), -1 if side == "top" else 1)
                if p is not None:
                    samples.append((c, p))
        s = np.array(samples, dtype=float)
        if len(s) < 10:
            raise PSVRegistrationError(f"panel edge {side!r}: too few edge samples")
        hull = {"left": x0, "right": x1, "top": y0, "bottom": y1}[side]
        distance = np.abs(s[:, 1] - hull)
        ordered = np.sort(distance)
        clusters = np.split(ordered, np.where(np.diff(ordered) > EDGE_CLUSTER_GAP_PX)[0] + 1)
        chosen = next((cl for cl in clusters if len(cl) >= EDGE_CLUSTER_MIN_SHARE * len(s)), None)
        if chosen is None:
            raise PSVRegistrationError(f"panel edge {side!r}: no dominant edge cluster")
        keep = (distance >= chosen.min() - 1e-9) & (distance <= chosen.max() + 1e-9)
        for _ in range(8):
            a, b = np.polyfit(s[keep, 0], s[keep, 1], 1)
            residual = s[:, 1] - (a * s[:, 0] + b)
            sd = max(float(residual[keep].std()), 0.15)
            keep = np.abs(residual - np.median(residual[keep])) < EDGE_CLIP_SIGMA * sd
        lines[side] = {"a": float(a), "b": float(b), "samples_used": int(keep.sum()), "samples": int(len(s)),
                       "rms_px": float(residual[keep].std()), "angle_deg": float(math.degrees(math.atan(a)))}
    return lines


def _corner(lines: Mapping[str, dict], vertical: str, horizontal: str) -> np.ndarray:
    av, bv = lines[vertical]["a"], lines[vertical]["b"]
    ah, bh = lines[horizontal]["a"], lines[horizontal]["b"]
    y = (ah * bv + bh) / (1 - ah * av)
    return np.array([av * y + bv, y])


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ----------------------------------------------------------------------------- reconstruction

@dataclass(frozen=True)
class Reconstruction:
    record: dict  # JSON-serialisable evidence record (no modal data, no MAC)
    panel_points_mm: np.ndarray  # scan points in the physical panel frame (x right, y towards the labelled top)


def reconstruct(svd_bytes: bytes, unv_xy_m: np.ndarray, unv_node_ids: Sequence[int], panel_width_mm: float,
                panel_height_mm: float, *, sources: Mapping[str, object]) -> Reconstruction:
    """Reconstruct the physical scan-point positions on the panel from the stored PSV frame.

    Frame convention: origin at the panel's bottom-left corner as seen by the scanner (the measured,
    labelled face), +x to the right in the camera image, +y towards the labelled top edge.
    """
    cf = CompoundFile(svd_bytes)
    count = len(unv_node_ids)
    meas = cf.read("Info/Geometry/MeasPoints")
    uv = measpoints_uv(meas, count)
    unv_mm = np.asarray(unv_xy_m, dtype=float) * 1000.0

    # 1. parser validation: record k <-> UNV node k (order) through one plane projective map
    h_scan = homography(unv_mm, uv)
    scan_residual = np.linalg.norm(apply_homography(h_scan, unv_mm) - uv, axis=1)
    if float(np.max(scan_residual)) > 2.0e-3:
        raise PSVRegistrationError("MeasPoints do not validate against the UNV geometry (point order / layout)")

    # 2. pixel normalisation from the stored default full-frame rectangle
    defaults = cf.read("Info/APS_Mixed/MeshObject1/DefaultSettings")
    u0, v0, u1, v1 = default_rectangle(defaults)
    frame_blob = cf.read("Info/VideoBitmap")
    image = video_frame(frame_blob)
    width, height = image.size
    px_per_u, px_per_v = width / (u1 - u0), height / (v1 - v0)
    px = np.column_stack([(uv[:, 0] - u0) * px_per_u, (uv[:, 1] - v0) * px_per_v])
    alignment_blob = cf.read("Info/VideoSettings")
    align = alignment_points(alignment_blob)
    tangent = np.tan(np.radians(align[:, :2]))
    design = np.column_stack([np.ones(len(align)), tangent])
    cu, *_ = np.linalg.lstsq(design, align[:, 2], rcond=None)
    cv, *_ = np.linalg.lstsq(design, align[:, 3], rcond=None)
    angle_isotropy = abs(cu[1]) / abs(cv[2])

    # 3. panel edges in the stored frame; physical panel frame through the four corners
    gray = np.asarray(image.convert("L"), dtype=float)
    lines = fit_panel_edges(gray, px)
    corners = {"left-bottom": _corner(lines, "left", "bottom"), "right-bottom": _corner(lines, "right", "bottom"),
               "right-top": _corner(lines, "right", "top"), "left-top": _corner(lines, "left", "top")}
    width_px = 0.5 * (np.linalg.norm(corners["right-top"] - corners["left-top"])
                      + np.linalg.norm(corners["right-bottom"] - corners["left-bottom"]))
    height_px = 0.5 * (np.linalg.norm(corners["left-top"] - corners["left-bottom"])
                       + np.linalg.norm(corners["right-top"] - corners["right-bottom"]))
    to_panel = homography(np.array([corners["left-bottom"], corners["right-bottom"], corners["right-top"],
                                    corners["left-top"]]),
                          np.array([[0.0, 0.0], [panel_width_mm, 0.0], [panel_width_mm, panel_height_mm],
                                    [0.0, panel_height_mm]]))
    panel = apply_homography(to_panel, px)

    # 4. UNV metric geometry vs physical: affine diagnostics (rotation, shear, per-axis scale)
    design_unv = np.column_stack([unv_mm, np.ones(count)])
    coef, *_ = np.linalg.lstsq(design_unv, panel, rcond=None)
    matrix = coef[:2, :2].T
    affine_residual = np.linalg.norm(design_unv @ coef - panel, axis=1)
    x_axis_deg = math.degrees(math.atan2(matrix[1, 0], matrix[0, 0]))
    y_axis_deg = math.degrees(math.atan2(matrix[1, 1], matrix[0, 1]))
    span_panel, span_unv = np.ptp(panel, axis=0), np.ptp(unv_mm, axis=0)

    # 5. legacy centred placement (historical registration convention) vs physical
    centre_unv = 0.5 * (unv_mm.min(0) + unv_mm.max(0))
    legacy = unv_mm - centre_unv + np.array([0.5 * panel_width_mm, 0.5 * panel_height_mm])
    legacy_error = np.linalg.norm(legacy - panel, axis=1)

    # 6. the M2 scan_to_panel_edges + camera_grid model (per-axis scale, translation, no rotation)
    window_w, window_h = float(span_panel[0]), float(span_panel[1])
    offset_x, offset_y = float(panel[:, 0].min()), float(panel[:, 1].min())
    model = np.column_stack([(unv_mm[:, 0] - unv_mm[:, 0].min()) * window_w / span_unv[0] + offset_x,
                             (unv_mm[:, 1] - unv_mm[:, 1].min()) * window_h / span_unv[1] + offset_y])
    model_error = np.linalg.norm(model - panel, axis=1)

    # 7. FE sign alternatives (physically indistinguishable on the finished panel): offsets to the FE
    #    minimum corner for each admissible sign mapping of the in-plane axes
    gaps = {"left": offset_x, "right": panel_width_mm - float(panel[:, 0].max()),
            "bottom": offset_y, "top": panel_height_mm - float(panel[:, 1].max())}
    alternatives = {
        "+x->+X, +y->+Y (TOP face, det +1)": {"x_mm": gaps["left"], "y_mm": gaps["bottom"]},
        "+x->-X, +y->-Y (TOP face, det +1, 180 deg)": {"x_mm": gaps["right"], "y_mm": gaps["top"]},
        "+x->-X, +y->+Y (BOTTOM face, det -1)": {"x_mm": gaps["right"], "y_mm": gaps["bottom"]},
        "+x->+X, +y->-Y (BOTTOM face, det -1)": {"x_mm": gaps["left"], "y_mm": gaps["top"]},
    }

    def stats(values):
        values = np.asarray(values, dtype=float)
        return {"median": float(np.median(values)), "p95": float(np.percentile(values, 95)),
                "max": float(values.max())}

    record = {
        "schema": SCHEMA,
        "sources": dict(sources),
        "stream_sha256": {name: sha256(cf.read(name)) for name in (
            "Info/Geometry/MeasPoints", "Info/VideoBitmap", "Info/VideoSettings",
            "Info/APS_Mixed/MeshObject1/DefaultSettings")},
        "method_constants": {
            "measpoint_record_bytes": MEASPOINT_RECORD_BYTES, "measpoint_uv_offset": MEASPOINT_UV_OFFSET,
            "edge_search_window_px": EDGE_SEARCH_WINDOW_PX, "edge_min_step": EDGE_MIN_STEP,
            "edge_min_gradient": EDGE_MIN_GRADIENT, "edge_cluster_gap_px": EDGE_CLUSTER_GAP_PX,
            "edge_cluster_min_share": EDGE_CLUSTER_MIN_SHARE, "edge_clip_sigma": EDGE_CLIP_SIGMA,
            "edge_samples": EDGE_SAMPLES},
        "parser_validation": {"point_count": count, "order": "MeasPoints record k <-> UNV node k (as listed)",
                              "uv_from_unv_homography_residual": stats(scan_residual)},
        "pixel_normalisation": {"default_rectangle_u": [u0, u1], "default_rectangle_v": [v0, v1],
                                "frame_px": [width, height], "px_per_u": px_per_u, "px_per_v": px_per_v,
                                "scanner_angle_isotropy_du_dv": float(angle_isotropy)},
        "panel_edges_px": lines,
        "panel_corners_px": {k: v.tolist() for k, v in corners.items()},
        "panel_size_px": [float(width_px), float(height_px)],
        "panel_dimensions_mm": [panel_width_mm, panel_height_mm],
        "dimension_consistency_px_per_mm_x_over_y": float((width_px / panel_width_mm) / (height_px / panel_height_mm)),
        "scan_points_panel_mm": [[round(float(x), 4), round(float(y), 4)] for x, y in panel],
        "scan_window_mm": {"width": window_w, "height": window_h},
        "grid_to_edge_gaps_mm": gaps,
        "unv_vs_physical": {"span_unv_mm": span_unv.tolist(), "span_physical_mm": span_panel.tolist(),
                            "scale_unv_over_physical": (span_unv / span_panel).tolist(),
                            "affine_matrix": matrix.tolist(), "x_axis_angle_deg": x_axis_deg,
                            "y_axis_angle_deg": y_axis_deg, "affine_residual_mm": stats(affine_residual)},
        "legacy_centred_error_mm": stats(legacy_error),
        "m2_model": {"physical_width_mm": window_w, "physical_height_mm": window_h,
                     "panel_edges_x_mm": gaps["left"], "panel_edges_y_mm": gaps["bottom"],
                     "residual_vs_reconstruction_mm": stats(model_error),
                     "axis_misalignment_deg": max(abs(x_axis_deg), abs(y_axis_deg - 90.0))},
        "fe_sign_alternatives": alternatives,
        "uses_modal_data": False,
    }
    return Reconstruction(record, panel)
