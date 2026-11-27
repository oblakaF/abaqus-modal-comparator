"""Pixel normalisation of the PSV scan points (PLATE-0875-SCAN-NORMALIZATION-FIX-01).

The scan-point video coordinates of a PSV file are stored in a unit frame that the file itself records. The v1
reading used the default full-frame rectangle for them and compressed the grid horizontally when the file stored
them in another frame. These tests build synthetic PSV files in memory (no laboratory data), check the supported
normalisations, reproduce the defect with the v1 reading, and check that missing, unsupported or ambiguous
metadata are refused. No modal quantity appears anywhere.
"""

from __future__ import annotations

import contextlib
import inspect
import io
import json
import struct
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import services.psv_video_registration as V  # noqa: E402
from services.psv_video_registration import PSVRegistrationError  # noqa: E402

END, FAT_SECTOR, NONE = 0xFFFFFFFE, 0xFFFFFFFD, -1
FULL_16_9 = (-2.0 / 9.0, 0.0, 14.0 / 9.0, 1.0)
POINTS_4_3 = (0.0, 0.0, 4.0 / 3.0, 1.0)
REAL_SVD = Path(r"D:\git\abaqus-modal-comparator-work\external_models\v3_20261021\Plate\snadwich_Plate"
                r"\300by300_plate_only_1mm_261016.svd")
REAL_UNV = REAL_SVD.with_suffix(".unv")
REAL_M11 = Path(r"D:\git\abaqus-modal-comparator-work\runs\m11_carbon_plate\plate_reconstruction_W301xH300.json")
EVIDENCE = ROOT / "docs" / "auto_id" / "registration_evidence"


# ----------------------------------------------------------------------------- synthetic PSV streams

def to_uv(px: np.ndarray, frame, size) -> np.ndarray:
    """Pixels -> video coordinates of a frame (u0, v0, u1, v1) that spans the whole image."""
    u0, v0, u1, v1 = frame
    return np.column_stack([u0 + px[:, 0] * (u1 - u0) / size[0], v0 + px[:, 1] * (v1 - v0) / size[1]])


def measpoints_blob(uv: np.ndarray, full) -> bytes:
    blob = bytearray(V.MEASPOINT_UV_OFFSET + V.MEASPOINT_RECORD_BYTES * len(uv))
    struct.pack_into("<4f", blob, V.MEASPOINT_FRAME_OFFSET, *full)
    for k, (u, v) in enumerate(uv):
        struct.pack_into("<ff", blob, V.MEASPOINT_UV_OFFSET + V.MEASPOINT_RECORD_BYTES * k, u, v)
    return bytes(blob)


def defaults_blob(rectangle, point_frame) -> bytes:
    blob = bytearray(200)
    struct.pack_into("<3i", blob, 0, 0, 3, 101)
    struct.pack_into("<4f", blob, 12, *rectangle)
    if point_frame is not None:
        a, b = point_frame[2], point_frame[3]
        struct.pack_into("<3i", blob, 28, 1, 8, 13)
        struct.pack_into("<6f", blob, 40, 0.0, 0.0, a, 0.0, a, b)
    return bytes(blob)


def scan_objects_blob(rect, *, objects=1, corners=None, rotation=0) -> bytes:
    u0, v0, u1, v1 = rect
    outline = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)] if corners is None else corners
    blob = bytearray(140)
    struct.pack_into("<hh", blob, V.SCAN_GRID_ROTATION_OFFSET, rotation, 1)  # the stored rotation of the scan grid
    struct.pack_into("<5i", blob, 0, 2, objects, 3, 3, 101)
    struct.pack_into("<4f", blob, 20, *rect)
    struct.pack_into("<3i", blob, 36, 1, 8, len(outline))
    for k, (u, v) in enumerate(outline[:8]):
        struct.pack_into("<2f", blob, 48 + 8 * k, u, v)
    return bytes(blob)


def video_settings_blob(full, size) -> bytes:
    px = np.array([[x, y] for x in (300.0, 700.0, 1100.0, 1500.0) for y in (200.0, 540.0, 900.0)] + [[960.0, 400.0]])
    px = px * np.array([size[0] / 1920.0, size[1] / 1080.0])
    uv = to_uv(px, full, size)
    blob = bytearray(44)
    struct.pack_into("<I", blob, 40, len(px))
    for (x, y), (u, v) in zip(px, uv):
        a = np.degrees(np.arctan((x - 0.5 * size[0]) / 2000.0))
        b = np.degrees(np.arctan((y - 0.5 * size[1]) / 2000.0))
        blob += struct.pack("<Iddff", 1, a, b, u, v)
    blob += bytes(64) + struct.pack("<4f", *full)
    return bytes(blob)


def jpeg_frame(size, plate) -> bytes:
    """Dark panel on a brighter background: the polarity the edge search expects."""
    from PIL import Image

    left, right, top, bottom = plate
    gray = np.full((size[1], size[0]), 175, dtype=np.uint8)
    gray[top:bottom, left:right] = 45
    out = io.BytesIO()
    Image.fromarray(gray, "L").save(out, "JPEG", quality=95)
    return bytes(16) + out.getvalue()


def compound_file(streams: dict[str, bytes]) -> bytes:
    """Minimal compound file (512-byte sectors, no mini stream) holding ``Info/<path>`` streams."""
    sector = 512
    tree: dict = {}
    for path, data in streams.items():
        node = tree
        parts = path.split("/")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = data
    entries: list[dict] = [{"name": "Root Entry", "type": 5, "child": NONE, "right": NONE, "data": None}]

    def add(node: dict) -> int:
        first, previous = NONE, None
        for name, value in node.items():
            index = len(entries)
            entry = {"name": name, "type": 1 if isinstance(value, dict) else 2, "child": NONE, "right": NONE,
                     "data": None if isinstance(value, dict) else value}
            entries.append(entry)
            if isinstance(value, dict):
                entry["child"] = add(value)
            if previous is None:
                first = index
            else:
                previous["right"] = index
            previous = entry
        return first

    entries[0]["child"] = add(tree)
    n_dir = -(-len(entries) * 128 // sector)
    data_sectors = sum(-(-len(e["data"]) // sector) for e in entries if e["data"] is not None)
    n_fat = 1
    while n_fat * (sector // 4) < n_fat + n_dir + data_sectors:
        n_fat += 1
    assert n_fat <= 109
    fat = [FAT_SECTOR] * n_fat + [n_fat + k + 1 for k in range(n_dir - 1)] + [END]
    body = bytearray()
    for e in entries:
        if e["data"] is None:
            e["start"], e["size"] = (END if e["type"] == 5 else 0), 0
            continue
        count = -(-len(e["data"]) // sector)
        e["start"], e["size"] = len(fat), len(e["data"])
        fat += [len(fat) + k + 1 for k in range(count - 1)] + [END]
        body += e["data"] + bytes(count * sector - len(e["data"]))
    fat += [0xFFFFFFFF] * (n_fat * (sector // 4) - len(fat))
    directory = bytearray()
    for e in entries:
        name = e["name"].encode("utf-16-le")
        record = bytearray(128)
        record[:len(name)] = name
        struct.pack_into("<H", record, 64, len(name) + 2)
        record[66] = e["type"]
        struct.pack_into("<iii", record, 68, NONE, e["right"], e["child"])
        struct.pack_into("<I", record, 116, e["start"])
        struct.pack_into("<Q", record, 120, e["size"])
        directory += record
    directory += bytes(n_dir * sector - len(directory))
    header = bytearray(sector)
    header[:8] = bytes.fromhex("d0cf11e0a1b11ae1")
    struct.pack_into("<HHHHH", header, 24, 0x3E, 3, 0xFFFE, 9, 6)
    struct.pack_into("<I", header, 44, n_fat)
    struct.pack_into("<I", header, 48, n_fat)  # first directory sector
    struct.pack_into("<I", header, 56, 0)  # mini-stream cutoff 0: every stream is a regular stream
    struct.pack_into("<II", header, 60, END, 0)
    struct.pack_into("<II", header, 68, END, 0)
    struct.pack_into("<109I", header, 76, *(list(range(n_fat)) + [0xFFFFFFFF] * (109 - n_fat)))
    return bytes(header) + struct.pack(f"<{len(fat)}I", *fat) + bytes(directory) + bytes(body)


class SyntheticCase:
    """A panel of known size with a known scan grid, stored the way a PSV file stores it."""

    def __init__(self, *, size=(1920, 1080), full=FULL_16_9, points_frame=POINTS_4_3, list_frame="same",
                 plate=(480, 1320, 60, 1020), margin=20, n=9, default_v=(0.0, 1.0), rotation=0, turned_deg=None,
                 stretch=1.0, object_frame=None):
        """``rotation`` is the value the file stores for a scan grid turned inside its scan object (65536 per turn).
        The grid is turned by that angle about the object's centre unless ``turned_deg`` says otherwise;
        ``stretch`` scales the grid about the centre instead (a grid that does NOT lie on the scan object)."""
        self.size, self.full, self.points_frame, self.plate = size, full, points_frame, plate
        self.rotation = rotation
        left, right, top, bottom = plate
        self.panel_mm = ((right - left) / 2.0, (bottom - top) / 2.0)  # 2 px per mm on both axes
        xs, ys = np.linspace(left + margin, right - margin, n), np.linspace(top + margin, bottom - margin, n)
        self.true_px = np.array([[x, y] for y in ys for x in xs])
        hull = np.array([self.true_px.min(0), self.true_px.max(0)])  # the scan object: the grid before it is turned
        degrees = rotation * 360.0 / 65536.0 if turned_deg is None else turned_deg
        t, d = np.radians(degrees), (self.true_px - hull.mean(0)) * stretch
        self.true_px = np.column_stack([np.cos(t) * d[:, 0] - np.sin(t) * d[:, 1],
                                        np.sin(t) * d[:, 0] + np.cos(t) * d[:, 1]]) + hull.mean(0)
        self.true_mm = np.column_stack([(self.true_px[:, 0] - left) / 2.0, (bottom - self.true_px[:, 1]) / 2.0])
        self.uv = to_uv(self.true_px, points_frame, size).astype(np.float32).astype(float)
        self.object_rect = tuple(to_uv(hull, full if object_frame is None else object_frame, size).ravel())
        self.default_rect = (full[0], default_v[0], full[2], default_v[1])
        self.list_frame = points_frame if list_frame == "same" else list_frame
        self.ids = list(range(1, len(self.uv) + 1))
        self.unv_xy_m = self.true_mm * 0.87e-3 + np.array([0.01, -0.02])

    def blobs(self) -> dict[str, bytes]:
        return {"measpoints": measpoints_blob(self.uv, self.full), "defaults": defaults_blob(self.default_rect, self.list_frame),
                "scan_objects": scan_objects_blob(self.object_rect, rotation=self.rotation),
                "video_settings": video_settings_blob(self.full, self.size)}

    def resolve(self, **override):
        blobs = self.blobs()
        blobs.update(override)
        return V.resolve_pixel_normalisation(self.uv, self.size, **blobs)

    def svd(self, *, without=()) -> bytes:
        b = self.blobs()
        streams = {"Info/Geometry/MeasPoints": b["measpoints"], "Info/APS_Mixed/MeshObject1/DefaultSettings": b["defaults"],
                   "Info/APS_Mixed/MeshObject1/ScanObjects": b["scan_objects"], "Info/VideoBitmap": jpeg_frame(self.size, self.plate),
                   "Info/VideoSettings": b["video_settings"]}
        return compound_file({k: v for k, v in streams.items() if k not in without})

    def reconstruct(self, normalisation, **kwargs):
        return V.reconstruct(self.svd(**kwargs), self.unv_xy_m, self.ids, *self.panel_mm, sources={}, normalisation=normalisation)


# ----------------------------------------------------------------------------- tests

class SupportedNormalisationTests(unittest.TestCase):
    def test_points_in_the_default_point_list_frame_of_a_wide_frame(self):
        case = SyntheticCase()
        n = case.resolve()
        self.assertEqual(n.record["scan_points_frame"]["name"], "default point-list frame")
        self.assertEqual(n.record["scan_object_frame"]["name"], "full-frame rectangle")
        self.assertLess(np.abs(n.points_px(case.uv) - case.true_px).max(), 1e-3)
        self.assertAlmostEqual(n.record["px_per_u"], 1440.0, delta=1e-3)  # derived from the stored frame, not assumed

    def test_points_in_the_full_frame_rectangle_when_it_is_the_only_stored_frame(self):
        case = SyntheticCase(points_frame=FULL_16_9, list_frame=None)
        n = case.resolve()
        self.assertEqual(n.record["scan_points_frame"]["name"], "full-frame rectangle")
        self.assertLess(np.abs(n.points_px(case.uv) - case.true_px).max(), 1e-3)

    def test_one_frame_for_everything(self):
        frame = (0.0, 0.0, 4.0 / 3.0, 1.0)
        case = SyntheticCase(size=(1440, 1080), full=frame, points_frame=frame, plate=(240, 1200, 60, 1020))
        n = case.resolve()
        self.assertEqual(len(n.record["trials"]), 1)
        self.assertLess(np.abs(n.points_px(case.uv) - case.true_px).max(), 1e-3)

    def test_other_frame_size_and_aspect(self):
        case = SyntheticCase(size=(1280, 1024), full=(-0.1, 0.0, 1.15, 1.0), points_frame=(0.0, 0.0, 1.25, 1.0),
                             plate=(200, 1100, 62, 962))
        n = case.resolve()
        self.assertEqual(n.record["scan_points_frame"]["name"], "default point-list frame")
        self.assertLess(np.abs(n.points_px(case.uv) - case.true_px).max(), 1e-3)
        self.assertAlmostEqual(n.record["px_per_u"], 1024.0, delta=1e-3)

    def test_alignment_points_use_the_frame_of_the_scan_object(self):
        case = SyntheticCase()
        n = case.resolve()
        align = V.alignment_points(case.blobs()["video_settings"])
        px = n.object_px(align[:, 2:4])
        tangent = np.tan(np.radians(align[:, :2]))
        self.assertLess(np.abs(px - (tangent * 2000.0 + np.array([960.0, 540.0]))).max(), 1e-3)

    def test_default_settings_v_range_is_not_used(self):
        # the plate file of 261016 stores an anomalous v range there; two other streams store 0 ... 1
        case = SyntheticCase(default_v=(-2.4667, 1.0))
        self.assertLess(np.abs(case.resolve().points_px(case.uv) - case.true_px).max(), 1e-3)


class RefusalTests(unittest.TestCase):
    def test_points_in_no_stored_frame(self):
        case = SyntheticCase(points_frame=(0.0, 0.0, 1.2, 1.0), list_frame=POINTS_4_3)
        with self.assertRaisesRegex(PSVRegistrationError, "not supported"):
            case.resolve()

    def test_points_not_in_the_only_stored_frame(self):
        case = SyntheticCase(points_frame=POINTS_4_3, list_frame=None)  # the frame the points use is not recorded
        with self.assertRaisesRegex(PSVRegistrationError, "not supported"):
            case.resolve()

    def test_points_and_scan_object_in_one_unit_with_two_stored_frames(self):
        # hull and scan object then coincide under either frame: the file does not say which frame gives pixels
        case = SyntheticCase(points_frame=FULL_16_9, list_frame=POINTS_4_3)
        with self.assertRaisesRegex(PSVRegistrationError, "ambiguous"):
            case.resolve()

    def test_disagreeing_full_frame_rectangles(self):
        case = SyntheticCase()
        other = (-0.25, 0.0, 1.6, 1.0)
        with self.assertRaisesRegex(PSVRegistrationError, "ambiguous"):
            case.resolve(video_settings=video_settings_blob(other, case.size))
        with self.assertRaisesRegex(PSVRegistrationError, "ambiguous"):
            case.resolve(defaults=defaults_blob((other[0], 0.0, other[2], 1.0), POINTS_4_3))

    def test_unsupported_scan_objects(self):
        case = SyntheticCase()
        u0, v0, u1, v1 = case.object_rect
        bad = {"two objects": scan_objects_blob(case.object_rect, objects=2),
               "five corners": scan_objects_blob(case.object_rect, corners=[(u0, v0), (u1, v0), (u1, v1), (u0, v1), (u0, v0)]),
               "not a rectangle": scan_objects_blob(case.object_rect, corners=[(u0, v0), (u1, v0 + 0.05), (u1, v1), (u0, v1)]),
               "truncated": scan_objects_blob(case.object_rect)[:40],
               "empty rectangle": scan_objects_blob((u0, v0, u0, v1))}
        for name, blob in bad.items():
            with self.subTest(name=name), self.assertRaises(PSVRegistrationError):
                case.resolve(scan_objects=blob)

    def test_invalid_frame_rectangles_and_inputs(self):
        case = SyntheticCase()
        with self.assertRaises(PSVRegistrationError):
            case.resolve(measpoints=measpoints_blob(case.uv, (0.5, 0.0, 0.5, 1.0)))
        with self.assertRaises(PSVRegistrationError):
            case.resolve(video_settings=bytes(8))
        with self.assertRaises(PSVRegistrationError):
            V.resolve_pixel_normalisation(case.uv[:2], case.size, **case.blobs())
        with self.assertRaises(PSVRegistrationError):
            V.resolve_pixel_normalisation(case.uv, (0, 1080), **case.blobs())

    def test_reconstruct_refuses_a_file_without_scan_object_and_an_unknown_mode(self):
        case = SyntheticCase()
        with self.assertRaisesRegex(PSVRegistrationError, "ScanObjects"):
            case.reconstruct(V.NORMALISATION_INSTRUMENT, without=("Info/APS_Mixed/MeshObject1/ScanObjects",))
        with self.assertRaisesRegex(PSVRegistrationError, "unknown pixel normalisation"):
            case.reconstruct("guess")


class ReconstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = SyntheticCase()
        cls.corrected = cls.case.reconstruct(V.NORMALISATION_INSTRUMENT)
        cls.legacy = cls.case.reconstruct(V.NORMALISATION_LEGACY)

    def test_instrument_normalisation_recovers_the_known_grid(self):
        error = np.linalg.norm(self.corrected.panel_points_mm - self.case.true_mm, axis=1)
        self.assertLess(error.max(), 0.6)  # edge localisation in a JPEG frame at 2 px per mm
        record = self.corrected.record
        self.assertEqual(record["schema"], V.SCHEMA_INSTRUMENT)
        self.assertEqual(record["pixel_normalisation"]["mode"], V.NORMALISATION_INSTRUMENT)
        self.assertIn("Info/APS_Mixed/MeshObject1/ScanObjects", record["stream_sha256"])
        self.assertAlmostEqual(record["scan_window_mm"]["width"], np.ptp(self.case.true_mm[:, 0]), delta=0.6)
        self.assertAlmostEqual(record["pixel_normalisation"]["scanner_angle_isotropy_dpx_x_over_dpx_y"], 1.0, places=3)
        self.assertIs(record["uses_modal_data"], False)
        json.dumps(record)

    def test_legacy_reading_reproduces_the_horizontal_compression(self):
        """The defect of README 23: the grid at 3/4 of its width, shifted, with the vertical axis unaffected."""
        true, got = self.case.true_mm, self.legacy.panel_points_mm
        self.assertAlmostEqual(np.ptp(got[:, 0]) / np.ptp(true[:, 0]), 0.75, delta=0.003)
        self.assertAlmostEqual(np.ptp(got[:, 1]) / np.ptp(true[:, 1]), 1.0, delta=0.003)
        left, right = got[:, 0].min(), self.case.panel_mm[0] - got[:, 0].max()
        self.assertGreater(left, 60.0)  # true gaps: 10 mm on both sides
        self.assertGreater(right, 45.0)
        self.assertGreater(abs(left - right), 10.0)
        self.assertLess(np.abs(got[:, 1] - true[:, 1]).max(), 0.6)
        # pixel identity of the defect: x_legacy = origin + (frame ratio) * x_true, from the stored frames
        full, pts, size = self.case.full, self.case.points_frame, self.case.size
        ratio = (pts[2] - pts[0]) / (full[2] - full[0])
        px_legacy = (self.case.uv[:, 0] - full[0]) * size[0] / (full[2] - full[0])
        self.assertLess(np.abs(px_legacy - (-full[0] * size[0] / (full[2] - full[0]) + ratio * self.case.true_px[:, 0])).max(), 1e-3)
        self.assertAlmostEqual(ratio, 0.75)

    def test_legacy_record_keeps_the_v1_form(self):
        record = self.legacy.record
        self.assertEqual(record["schema"], V.SCHEMA)
        self.assertEqual(sorted(record["pixel_normalisation"]), ["default_rectangle_u", "default_rectangle_v", "frame_px", "px_per_u",
                                                                 "px_per_v", "scanner_angle_isotropy_du_dv"])
        self.assertEqual(sorted(record["stream_sha256"]), sorted(["Info/Geometry/MeasPoints", "Info/VideoBitmap", "Info/VideoSettings",
                                                                  "Info/APS_Mixed/MeshObject1/DefaultSettings"]))
        self.assertEqual(sorted(record), sorted(self.corrected.record))

    def test_both_readings_share_everything_but_the_pixels(self):
        for key in ("panel_dimensions_mm", "method_constants", "parser_validation"):
            self.assertEqual(self.legacy.record[key], self.corrected.record[key])


def tool():
    sys.path.insert(0, str(ROOT / "tools"))
    import reconstruct_psv_registration

    return reconstruct_psv_registration


class DefaultNormalisationTests(unittest.TestCase):
    """PSV-NORMALIZATION-INTEGRATION-01: a new reconstruction reads the instrument metadata; legacy is explicit only."""

    def test_service_and_tool_default_to_the_instrument_reading(self):
        self.assertEqual(inspect.signature(V.reconstruct).parameters["normalisation"].default, V.NORMALISATION_INSTRUMENT)
        build = inspect.signature(tool().build).parameters["normalisation"]
        self.assertEqual(build.default, V.NORMALISATION_INSTRUMENT)
        self.assertIs(build.kind, inspect.Parameter.KEYWORD_ONLY)

    def test_reconstruction_without_a_selection_is_the_corrected_one(self):
        case = SyntheticCase()
        result = V.reconstruct(case.svd(), case.unv_xy_m, case.ids, *case.panel_mm, sources={})
        self.assertEqual(result.record["schema"], V.SCHEMA_INSTRUMENT)
        self.assertEqual(result.record["pixel_normalisation"]["mode"], V.NORMALISATION_INSTRUMENT)
        self.assertLess(np.linalg.norm(result.panel_points_mm - case.true_mm, axis=1).max(), 0.6)
        explicit = case.reconstruct(V.NORMALISATION_INSTRUMENT)
        self.assertEqual(json.dumps(result.record, sort_keys=True), json.dumps(explicit.record, sort_keys=True))

    def test_default_refuses_and_does_not_fall_back_to_the_legacy_reading(self):
        """Files the legacy reading would accept: the default must refuse them, not answer with a v1 record."""
        undecidable = SyntheticCase(size=(1440, 1080), full=POINTS_4_3, points_frame=POINTS_4_3, list_frame=FULL_16_9,
                                    plate=(360, 1080, 60, 1020))
        no_object = SyntheticCase()
        cases = {"undecidable": (undecidable, {}), "no scan object": (no_object, {"without": ("Info/APS_Mixed/MeshObject1/ScanObjects",)})}
        for name, (case, kwargs) in cases.items():
            with self.subTest(case=name):
                legacy = case.reconstruct(V.NORMALISATION_LEGACY, **kwargs)  # the legacy reading does answer
                self.assertEqual(legacy.record["schema"], V.SCHEMA)
                with self.assertRaises(PSVRegistrationError):
                    V.reconstruct(case.svd(**kwargs), case.unv_xy_m, case.ids, *case.panel_mm, sources={})

    def test_no_reading_is_chosen_by_catching_a_refusal(self):
        """Neither the service nor the tool contains a path from a refusal to the other reading."""
        import ast

        for path in (ROOT / "src" / "services" / "psv_video_registration.py", ROOT / "tools" / "reconstruct_psv_registration.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
                    with self.subTest(path=path.name, line=node.lineno):
                        self.assertFalse(names & {"NORMALISATION_LEGACY", "reconstruct", "build", "default_rectangle"})

    def test_schema_names_the_reading_of_a_stored_record(self):
        t = tool()
        self.assertEqual(t.normalisation_of_record({"schema": V.SCHEMA}), V.NORMALISATION_LEGACY)
        self.assertEqual(t.normalisation_of_record({"schema": V.SCHEMA_INSTRUMENT}), V.NORMALISATION_INSTRUMENT)
        for record in ({}, {"schema": "auto-id/psv-physical-registration-reconstruction/v3"}):
            with self.assertRaises(PSVRegistrationError):
                t.normalisation_of_record(record)


def write_unv(path: Path, ids, xy_m) -> None:
    lines = ["    -1", "  2411"]
    for i, (x, y) in zip(ids, xy_m):
        lines += ["%10d%10d%10d%10d" % (i, 1, 1, 11), "%25.16E%25.16E%25.16E" % (x, y, 0.0)]
    path.write_text("\n".join(lines + ["    -1", ""]), encoding="latin-1")


class ToolIntegrationTests(unittest.TestCase):
    """The command-line tool on a synthetic data store (no real measurement is read)."""

    STORE = "psv-synthetic-test"

    def setUp(self):
        import os
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        key = "AUTO_ID_FIXTURE_ROOT_" + self.STORE.upper().replace("-", "_")
        previous = os.environ.get(key)
        os.environ[key] = str(self.root)
        self.addCleanup(lambda: os.environ.pop(key, None) if previous is None else os.environ.__setitem__(key, previous))
        self.case = SyntheticCase()
        (self.root / "good.svd").write_bytes(self.case.svd())
        (self.root / "no_object.svd").write_bytes(self.case.svd(without=("Info/APS_Mixed/MeshObject1/ScanObjects",)))
        write_unv(self.root / "scan.unv", self.case.ids, self.case.unv_xy_m)

    def run_tool(self, svd, out, *extra):
        argv = ["--store", self.STORE, "--svd", svd, "--unv", "scan.unv", "--width-mm", str(self.case.panel_mm[0]),
                "--height-mm", str(self.case.panel_mm[1]), "--dimension-source", "synthetic", "--out", str(self.root / out), *extra]
        with contextlib.redirect_stdout(io.StringIO()):
            tool().main(argv)
        return json.loads((self.root / out).read_text(encoding="utf-8"))

    def test_unv_written_for_the_test_is_read_back(self):
        ids, xy = tool().unv_scan_geometry(self.root / "scan.unv")
        self.assertEqual(ids, self.case.ids)
        self.assertLess(np.abs(xy - self.case.unv_xy_m).max(), 1e-15)

    def test_default_run_writes_the_corrected_v2_record(self):
        record = self.run_tool("good.svd", "default.json")
        self.assertEqual(record["schema"], V.SCHEMA_INSTRUMENT)
        self.assertEqual(record["pixel_normalisation"]["mode"], V.NORMALISATION_INSTRUMENT)
        self.assertEqual(record["unv_node_ids"], self.case.ids)
        self.assertEqual(record["sources"]["svd"]["relative_path"], "good.svd")
        self.assertEqual(len(record["sources"]["svd"]["sha256"]), 64)
        self.assertLess(np.linalg.norm(np.array(record["scan_points_panel_mm"]) - self.case.true_mm, axis=1).max(), 0.6)
        named = self.run_tool("good.svd", "named.json", "--normalisation", V.NORMALISATION_INSTRUMENT)
        self.assertEqual(named, record)

    def test_explicit_legacy_run_writes_the_v1_record(self):
        record = self.run_tool("good.svd", "legacy.json", "--normalisation", V.NORMALISATION_LEGACY)
        self.assertEqual(record["schema"], V.SCHEMA)
        self.assertNotIn("mode", record["pixel_normalisation"])
        direct = self.case.reconstruct(V.NORMALISATION_LEGACY).record
        self.assertEqual(record["scan_points_panel_mm"], direct["scan_points_panel_mm"])
        self.assertEqual(record["pixel_normalisation"], direct["pixel_normalisation"])
        self.assertEqual(record["stream_sha256"], direct["stream_sha256"])
        self.assertEqual(tool().normalisation_of_record(record), V.NORMALISATION_LEGACY)

    def test_refusal_writes_nothing_and_tries_no_other_reading(self):
        with self.assertRaises(SystemExit) as caught:
            self.run_tool("no_object.svd", "refused.json")
        self.assertIn("REFUSED (%s)" % V.NORMALISATION_INSTRUMENT, str(caught.exception))
        self.assertFalse((self.root / "refused.json").exists())
        legacy = self.run_tool("no_object.svd", "refused_legacy.json", "--normalisation", V.NORMALISATION_LEGACY)
        self.assertEqual(legacy["schema"], V.SCHEMA)  # the file is readable by the legacy reading: the default did not use it

    def test_unknown_reading_is_rejected_by_the_command_line(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            self.run_tool("good.svd", "x.json", "--normalisation", "auto")
        self.assertFalse((self.root / "x.json").exists())


class HistoricalReproducibilityTests(unittest.TestCase):
    def test_v1_schema_and_legacy_reading_stay_available_by_name(self):
        self.assertEqual(V.SCHEMA, "auto-id/psv-physical-registration-reconstruction/v1")
        self.assertEqual(V.SCHEMA_INSTRUMENT, "auto-id/psv-physical-registration-reconstruction/v2")
        self.assertEqual(V.NORMALISATION_LEGACY, "legacy-default-rectangle")
        self.assertEqual(V.NORMALISATION_BY_SCHEMA, {V.SCHEMA: V.NORMALISATION_LEGACY, V.SCHEMA_INSTRUMENT: V.NORMALISATION_INSTRUMENT})

    def test_stored_records_name_the_legacy_reading(self):
        for name in ("SP13_physical_registration_reconstruction.json", "SP02_physical_registration_reconstruction.json"):
            record = json.loads((EVIDENCE / name).read_text(encoding="utf-8"))
            with self.subTest(name=name):
                self.assertEqual(tool().normalisation_of_record(record), V.NORMALISATION_LEGACY)

    def test_store_reproduction_tests_select_the_reading_from_the_record(self):
        for name in ("test_sp02_physical_registration.py", "test_sp13_physical_registration.py"):
            with self.subTest(name=name):
                self.assertIn("normalisation=normalisation_of_record(record)", (ROOT / "tests" / name).read_text(encoding="utf-8"))

    def test_stored_records_are_v1_records(self):
        for name in ("SP13_physical_registration_reconstruction.json", "SP02_physical_registration_reconstruction.json"):
            record = json.loads((EVIDENCE / name).read_text(encoding="utf-8"))
            with self.subTest(name=name):
                self.assertEqual(record["schema"], V.SCHEMA)
                self.assertIn("default_rectangle_u", record["pixel_normalisation"])


# ----------------------------------------------------------------------------- PSV-SCAN-OBJECT-MARGIN-01

V1_PIXEL_KEYS = {"default_rectangle_u", "default_rectangle_v", "frame_px", "px_per_u", "px_per_v",
                 "scanner_angle_isotropy_du_dv"}
V2_PIXEL_KEYS = {"mode", "full_frame_rectangle", "default_settings_rectangle", "default_point_list_frame",
                 "scan_object_rectangle", "scan_points_hull_uv", "frame_px", "scan_points_frame", "scan_object_frame",
                 "px_per_u", "px_per_v", "match_tolerance_px", "trials", "scanner_angle_isotropy_dpx_x_over_dpx_y"}
SAME_UNIT = dict(full=(-0.25, 0.0, 1.0, 1.0), points_frame=(-0.25, 0.0, 1.0, 1.0), list_frame=(0.0, 0.0, 1.25, 1.0))


class TurnedScanGridTests(unittest.TestCase):
    """A scan grid the operator turned inside its scan object: the file stores the angle, the hull of the points is
    wider than the object on all four sides, and the frame is still decided by the stored metadata alone."""

    def test_the_stored_rotation_is_read_as_a_binary_angle(self):
        for stored, degrees in ((0, 0.0), (127, 0.69763), (-182, -0.99976), (-91, -0.49988), (16384, 90.0)):
            value, angle = V.scan_grid_rotation(scan_objects_blob((0.1, 0.1, 0.9, 0.9), rotation=stored))
            self.assertEqual(value, stored)
            self.assertAlmostEqual(angle, degrees, places=4)
        self.assertEqual((V.SCAN_GRID_ROTATION_OFFSET, V.SCAN_GRID_ROTATION_PER_TURN), (80, 65536.0))
        with self.assertRaisesRegex(PSVRegistrationError, "too short"):
            V.scan_grid_rotation(bytes(81))

    def test_symmetric_margins_are_accepted_by_the_separate_rule_at_the_unchanged_tolerance(self):
        self.assertEqual(V.NORMALISATION_MATCH_TOL_PX, 0.25)  # not widened
        for stored in (127, -182, -91, 300):
            with self.subTest(stored=stored):
                case = SyntheticCase(rotation=stored)
                n = case.resolve()
                record = n.record
                self.assertEqual(record["acceptance_rule"], V.RULE_ROTATED_GRID)
                self.assertEqual(record["scan_points_frame"]["name"], "default point-list frame")
                self.assertEqual(record["scan_object_frame"]["name"], "full-frame rectangle")
                self.assertEqual(record["match_tolerance_px"], 0.25)
                # the points are where the file stores them: turned, not moved onto the scan object
                self.assertLess(np.abs(n.points_px(case.uv) - case.true_px).max(), 1e-3)
                turn = record["scan_grid_rotation"]
                self.assertEqual((turn["stored_value"], turn["stream"], turn["byte_offset"]), (stored, "ScanObjects", 80))
                self.assertAlmostEqual(turn["degrees"], stored * 360.0 / 65536.0, places=9)
                outside = turn["hull_outside_scan_object_px"]
                expected = 0.5 * 800.0 * abs(np.sin(np.radians(turn["degrees"]))) - 400.0 * (1 - np.cos(np.radians(turn["degrees"])))
                for side in ("left", "right", "top", "bottom"):  # 800 x 920 px grid: the margin of the short side
                    self.assertGreater(outside[side], V.NORMALISATION_MATCH_TOL_PX)
                self.assertAlmostEqual(outside["top"], outside["bottom"], delta=0.01)
                self.assertAlmostEqual(outside["left"], outside["right"], delta=0.01)
                self.assertAlmostEqual(outside["top"], expected, delta=0.05)
                self.assertLess(turn["turned_back_hull_mismatch_px"], 0.01)
                # as stored, no pair coincides; turned back, exactly one does
                self.assertTrue(all(t["hull_mismatch_px"] > 0.25 for t in record["trials"]))
                passed = [t for t in turn["trials"] if t["turned_back_hull_mismatch_px"] <= 0.25]
                self.assertEqual([(t["scan_object_in"], t["scan_points_in"]) for t in passed],
                                 [("full-frame rectangle", "default point-list frame")])
                self.assertEqual(len(turn["trials"]), 4)
                self.assertGreater(min(t["turned_back_hull_mismatch_px"] for t in turn["trials"] if t not in passed), 50.0)

    def test_a_record_accepted_without_a_rotation_keeps_its_earlier_form(self):
        case = SyntheticCase()
        self.assertEqual(set(case.resolve().record), V2_PIXEL_KEYS - {"scanner_angle_isotropy_dpx_x_over_dpx_y"})
        self.assertEqual(set(case.reconstruct(V.NORMALISATION_INSTRUMENT).record["pixel_normalisation"]), V2_PIXEL_KEYS)
        self.assertEqual(set(case.reconstruct(V.NORMALISATION_LEGACY).record["pixel_normalisation"]), V1_PIXEL_KEYS)
        # a stored rotation too small to matter is accepted by the first rule, as stored
        tiny = SyntheticCase(rotation=1)
        self.assertNotIn("acceptance_rule", tiny.resolve().record)
        # the first rule does not read the rotation: a stream that ends before it is as supported as before
        short = case.resolve(scan_objects=scan_objects_blob(case.object_rect)[:80])
        self.assertEqual(short.record, case.resolve().record)

    def test_asymmetric_or_unexplained_margins_are_refused(self):
        cases = {
            "turned, no angle stored": SyntheticCase(rotation=0, turned_deg=0.7),
            "turned by another angle than stored": SyntheticCase(rotation=127, turned_deg=1.5),
            "turned the other way": SyntheticCase(rotation=127, turned_deg=-0.69763),
            "angle stored, grid not turned but wider on all sides": SyntheticCase(rotation=127, turned_deg=0.0, stretch=1.0125),
            "wider on all sides, no angle stored": SyntheticCase(stretch=1.0125),
            "narrower on all sides, angle stored": SyntheticCase(rotation=-182, turned_deg=0.0, stretch=0.99),
            "turned and stretched": SyntheticCase(rotation=127, stretch=1.004),
        }
        for name, case in cases.items():
            with self.subTest(name=name):
                with self.assertRaisesRegex(PSVRegistrationError, "not supported"):
                    case.resolve()
                with self.assertRaises(PSVRegistrationError):
                    case.reconstruct(V.NORMALISATION_INSTRUMENT)
        shifted = SyntheticCase(rotation=127)  # the turned grid moved off the centre of the scan object by 2 px
        shifted.uv = to_uv(shifted.true_px + np.array([2.0, 0.0]), shifted.points_frame, shifted.size)
        with self.assertRaisesRegex(PSVRegistrationError, "not supported") as refused:
            shifted.resolve()
        self.assertIn("turned back by the stored grid rotation 0.6976 deg", str(refused.exception))

    def test_a_turned_grid_in_an_ambiguous_file_is_still_refused(self):
        # scan object and points in one unit, two stored frames of one scale: either frame fits, turned or not
        with self.assertRaisesRegex(PSVRegistrationError, "ambiguous"):
            SyntheticCase(**SAME_UNIT).resolve()
        with self.assertRaisesRegex(PSVRegistrationError, "ambiguous") as refused:
            SyntheticCase(rotation=127, **SAME_UNIT).resolve()
        self.assertIn("more than one pair", str(refused.exception))
        # the points in a frame the file does not store: no rule accepts them
        with self.assertRaisesRegex(PSVRegistrationError, "not supported"):
            SyntheticCase(rotation=127, points_frame=(0.0, 0.0, 1.2, 1.0), list_frame=POINTS_4_3).resolve()
        with self.assertRaisesRegex(PSVRegistrationError, "not supported"):
            SyntheticCase(rotation=127, points_frame=POINTS_4_3, list_frame=None).resolve()

    def test_missing_metadata_of_a_turned_grid_is_refused(self):
        case = SyntheticCase(rotation=127)
        blob = case.blobs()["scan_objects"]
        with self.assertRaisesRegex(PSVRegistrationError, "too short to hold the scan-grid rotation"):
            case.resolve(scan_objects=blob[:81])
        with self.assertRaisesRegex(PSVRegistrationError, "not supported"):
            case.resolve(scan_objects=blob[:80] + bytes(60))  # the angle lost: the margins are unexplained
        with self.assertRaisesRegex(PSVRegistrationError, "ScanObjects"):
            case.reconstruct(V.NORMALISATION_INSTRUMENT, without=("Info/APS_Mixed/MeshObject1/ScanObjects",))
        with self.assertRaises(PSVRegistrationError):
            case.resolve(scan_objects=scan_objects_blob(case.object_rect, objects=2, rotation=127))

    def test_reconstruction_of_a_turned_grid_and_the_metric_export_as_a_second_witness(self):
        case = SyntheticCase(rotation=-182)
        result = case.reconstruct(V.NORMALISATION_INSTRUMENT)
        self.assertLess(np.linalg.norm(result.panel_points_mm - case.true_mm, axis=1).max(), 0.6)
        record = result.record
        self.assertEqual(record["schema"], V.SCHEMA_INSTRUMENT)  # the same reading; the rule is named in the record
        pixels = record["pixel_normalisation"]
        self.assertEqual(set(pixels), V2_PIXEL_KEYS | {"acceptance_rule", "scan_grid_rotation", "instrument_metric_export"})
        export = pixels["instrument_metric_export"]
        self.assertAlmostEqual(export["mm_per_px_x_over_y"], 1.0, places=4)
        self.assertEqual(list(export["ratio_if_points_were_in_another_stored_frame"]), ["full-frame rectangle"])
        self.assertAlmostEqual(export["ratio_if_points_were_in_another_stored_frame"]["full-frame rectangle"], 0.75, places=5)
        self.assertIs(record["uses_modal_data"], False)
        # the v1 reading of the same file is unchanged by the new rule: compressed, and without its keys
        legacy = case.reconstruct(V.NORMALISATION_LEGACY)
        self.assertEqual(set(legacy.record["pixel_normalisation"]), V1_PIXEL_KEYS)
        self.assertAlmostEqual(np.ptp(legacy.panel_points_mm[:, 0]) / np.ptp(result.panel_points_mm[:, 0]), 0.75, delta=0.01)
        # an instrument export that shows the ratio of the other stored frame contradicts the frame: refused
        squeezed = SyntheticCase(rotation=-182)
        squeezed.unv_xy_m = squeezed.unv_xy_m * np.array([0.75, 1.0])
        with self.assertRaisesRegex(PSVRegistrationError, "contradicted by the instrument's metric export"):
            squeezed.reconstruct(V.NORMALISATION_INSTRUMENT)
        plain = SyntheticCase()  # without a rotation the export is not consulted: the earlier behaviour
        plain.unv_xy_m = plain.unv_xy_m * np.array([0.75, 1.0])
        self.assertEqual(set(plain.reconstruct(V.NORMALISATION_INSTRUMENT).record["pixel_normalisation"]), V2_PIXEL_KEYS)

    def test_the_rule_takes_nothing_from_the_specimen_or_from_modal_data(self):
        source = inspect.getsource(V)
        for word in ("SP-02", "SP02", "SP-13", "SP13", "SP-10", "SP10", "260803", "260910", "260831", "260911"):
            self.assertNotIn(word, source.replace("M6 / SP-13 gate", ""), word)
        rule = inspect.getsource(V.resolve_pixel_normalisation) + inspect.getsource(V._turned_back)
        for word in ("mac", "frequenc", "eigen", "lstsq", "polyfit", "minimi"):  # nothing modal, nothing fitted
            self.assertNotIn(word, rule.lower(), word)
        self.assertEqual(rule.count("NORMALISATION_MATCH_TOL_PX"), 3)  # one tolerance: either rule, and the record


class NoOverwriteTests(ToolIntegrationTests):
    """PSV-SCAN-OBJECT-MARGIN-01: the tool never replaces an existing record."""

    def test_an_existing_output_is_refused_before_anything_is_read(self):
        from unittest import mock

        first = self.run_tool("good.svd", "record.json")
        stored = (self.root / "record.json").read_bytes()
        with mock.patch.object(tool(), "build", side_effect=AssertionError("the sources were read")):
            for extra in ((), ("--normalisation", V.NORMALISATION_LEGACY)):
                with self.assertRaises(SystemExit) as refused:
                    self.run_tool("good.svd", "record.json", *extra)
                self.assertIn("REFUSED", str(refused.exception))
                self.assertIn("never overwritten", str(refused.exception))
        self.assertEqual((self.root / "record.json").read_bytes(), stored)
        self.assertEqual(first["schema"], V.SCHEMA_INSTRUMENT)
        other = self.root / "notes.json"
        other.write_text("not a record", encoding="utf-8")
        with self.assertRaises(SystemExit):
            self.run_tool("good.svd", "notes.json")
        self.assertEqual(other.read_text(encoding="utf-8"), "not a record")
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):  # there is no way to force it
            self.run_tool("good.svd", "record.json", "--overwrite")

    def test_a_file_made_while_the_tool_works_is_kept(self):
        from unittest import mock

        target = self.root / "late.json"
        real = tool().build

        def build_then_someone_writes(*args, **kwargs):
            record = real(*args, **kwargs)
            target.write_text("written meanwhile", encoding="utf-8")
            return record

        with mock.patch.object(tool(), "build", side_effect=build_then_someone_writes):
            with self.assertRaises(SystemExit) as refused:
                self.run_tool("good.svd", "late.json")
        self.assertIn("never overwritten", str(refused.exception))
        self.assertEqual(target.read_text(encoding="utf-8"), "written meanwhile")

    def test_an_accepted_record_is_never_an_output_and_the_example_names_none(self):
        import hashlib

        for name in ("SP13_physical_registration_reconstruction.json", "SP02_physical_registration_reconstruction.json"):
            before = hashlib.sha256((EVIDENCE / name).read_bytes()).hexdigest()
            argv = ["--store", self.STORE, "--svd", "good.svd", "--unv", "scan.unv", "--width-mm", "420", "--height-mm", "480",
                    "--dimension-source", "synthetic", "--out", str(EVIDENCE / name)]
            for extra in ((), ("--normalisation", V.NORMALISATION_LEGACY)):
                with self.assertRaises(SystemExit) as refused:
                    tool().main(argv + list(extra))
                self.assertIn("never overwritten", str(refused.exception))
            self.assertEqual(hashlib.sha256((EVIDENCE / name).read_bytes()).hexdigest(), before)
        text = tool().__doc__
        self.assertEqual(text.count("--out "), 1)  # one example, and it writes outside the repository
        self.assertIn('--out "<work folder>/SP13_260910_reconstruction_v2_DIAGNOSTIC.json"', text)
        self.assertNotIn("--out docs/", text)
        self.assertIn("Nothing is overwritten", text)
        self.assertNotIn("--overwrite", inspect.getsource(tool()).replace('"--overwrite"', ""))

    def test_a_turned_grid_is_written_by_the_default_run_with_its_rule(self):
        case = SyntheticCase(rotation=127)
        (self.root / "turned.svd").write_bytes(case.svd())
        write_unv(self.root / "turned.unv", case.ids, case.unv_xy_m)
        argv = ["--store", self.STORE, "--svd", "turned.svd", "--unv", "turned.unv", "--width-mm", str(case.panel_mm[0]),
                "--height-mm", str(case.panel_mm[1]), "--dimension-source", "synthetic", "--out", str(self.root / "turned.json")]
        with contextlib.redirect_stdout(io.StringIO()):
            tool().main(argv)
        record = json.loads((self.root / "turned.json").read_text(encoding="utf-8"))
        self.assertEqual(record["schema"], V.SCHEMA_INSTRUMENT)
        self.assertEqual(record["pixel_normalisation"]["acceptance_rule"], V.RULE_ROTATED_GRID)
        self.assertEqual(record["pixel_normalisation"]["scan_grid_rotation"]["stored_value"], 127)


WORK = Path(r"D:\git\abaqus-modal-comparator-work")
SP10_STORE = WORK / "external_models" / "v2_20261019" / "SP-10" / "temp_12sampls_results_SP10"
# the four sandwich sessions of PSV-LEGACY-REGISTRATION-RISK-CHECK-01: SVD, its SHA-256, UNV, its SHA-256, panel mm,
# the stored rotation, the hull margin in px, and the scan-window width with the panel corners of the earlier record
REAL_SANDWICH = {
    "SP-02 260803": (Path(r"D:\Snadwich\SP-02\SP02_500by500_Glue420_honeycomb_full_scan_retry_260803.svd"),
                     "d974608c9dd4aa497edca69b760e917a2a746bcd99c2806f700bf9a4e1462425",
                     Path(r"D:\Snadwich\SP-02\SP02_polymax_retry_260803.unv"),
                     "2671db01b6401a9a9bbec7d8c2aa2191b0b35b5ae791756b91c7ccd381a41785", (510.0, 515.0), 127, 5.2, 492.2),
    "SP-13 260910": (Path(r"D:\Snadwich\SP-13\SP13_a_500by500_Glue420_Auxetic_newSP01_260910.svd"),
                     "41da4cc1d3a5daa038f558c571128793d44499f09605c7d79f0817b6744b0765",
                     Path(r"D:\Snadwich\SP-13\SP13_a_polymax.unv"),
                     "f268023583972f0a9c1660bc60631587e8f3330e4fb7495e52d8310906af39fe", (510.0, 520.0), -182, 7.4, 490.5),
    "SP-10 260831": (SP10_STORE / "SP10_500by500_Glue420_Honeycomb_PlainFiber_260831.svd",
                     "16833e048e7c3e40f3d17646a8227d64ec9ec16d258715175b29e41f2fed1c1f",
                     WORK / "runs" / "m9" / "polymax_zip_members" / "SP10_polymax.unv",
                     "b20549e6d8a0d747b042157dd4e2fbd2c27820c840ca7625dc4540b9f7a503bb", (520.0, 515.0), -91, 3.7, None),
    "SP-10 260911 b": (SP10_STORE / "SP10_b_rotated_500by500_Glue420_Honeycomb_PlainFiber_260911.svd",
                       "c1898e3a0eb2d752382ba930c2e2f067e7127170132ee15bdede841638ac8ca6",
                       SP10_STORE / "SP10_b_polymax.unv",
                       "497c7a47a3addff99f2feb8efd13f85accb73ece9d3c4a954181e6d897d38697", (515.0, 520.0), -91, 3.7, 493.3),
}


@unittest.skipUnless(all(row[0].is_file() and row[2].is_file() for row in REAL_SANDWICH.values()),
                     "the four sandwich PSV sessions are not on this machine")
class RealSandwichSessionsTests(unittest.TestCase):
    """The four sandwich sessions (RESEARCH_ONLY / diagnostic; no record is accepted here, no modal data is read)."""

    def test_each_file_is_accepted_by_the_turned_grid_rule_and_only_in_one_pair_of_frames(self):
        import hashlib

        sys.path.insert(0, str(ROOT / "tools"))
        from reconstruct_psv_registration import unv_scan_geometry

        for name, (svd, svd_sha, unv, unv_sha, panel, stored, margin, width) in REAL_SANDWICH.items():
            with self.subTest(name=name):
                data = svd.read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), svd_sha)
                self.assertEqual(hashlib.sha256(unv.read_bytes()).hexdigest(), unv_sha)
                ids, xy = unv_scan_geometry(unv)
                cf = V.CompoundFile(data)
                meas = cf.read("Info/Geometry/MeasPoints")
                uv = V.measpoints_uv(meas, len(ids))
                size = V.video_frame(cf.read("Info/VideoBitmap")).size
                n = V.resolve_pixel_normalisation(uv, size, measpoints=meas,
                                                  defaults=cf.read("Info/APS_Mixed/MeshObject1/DefaultSettings"),
                                                  scan_objects=cf.read("Info/APS_Mixed/MeshObject1/ScanObjects"),
                                                  video_settings=cf.read("Info/VideoSettings"))
                record = n.record
                self.assertEqual(record["acceptance_rule"], V.RULE_ROTATED_GRID)
                self.assertEqual(record["scan_points_frame"]["name"], "default point-list frame")
                self.assertEqual(record["scan_object_frame"]["name"], "full-frame rectangle")
                self.assertAlmostEqual(record["px_per_u"], 1440.0, delta=0.01)
                turn = record["scan_grid_rotation"]
                self.assertEqual(turn["stored_value"], stored)
                self.assertLess(turn["turned_back_hull_mismatch_px"], 0.01)  # as close as the unturned plate grid
                outside = turn["hull_outside_scan_object_px"]
                self.assertLess(max(outside.values()) - min(outside.values()), 0.1)
                self.assertAlmostEqual(outside["left"], margin, delta=0.1)
                self.assertGreater(min(t["hull_mismatch_px"] for t in record["trials"]), 3.0)  # none as stored
                others = [t["turned_back_hull_mismatch_px"] for t in turn["trials"]
                          if (t["scan_object_in"], t["scan_points_in"]) != ("full-frame rectangle", "default point-list frame")]
                self.assertEqual(len(others), 3)
                self.assertGreater(min(others), 90.0)
                # the v1 reading of the same file stays what it was: 0.75 of the width about pixel 960
                u0, _v0, u1, _v1 = V.default_rectangle(cf.read("Info/APS_Mixed/MeshObject1/DefaultSettings"))
                legacy_x = (uv[:, 0] - u0) * size[0] / (u1 - u0)
                self.assertLess(np.abs(legacy_x - (240.0 + 0.75 * n.points_px(uv)[:, 0])).max(), 0.01)
                if width is None:  # 260831: the unattended bottom-edge fit of this frame is a known open point (M10 3.2)
                    continue
                result = V.reconstruct(data, xy, ids, *panel, sources={})
                self.assertEqual(result.record["schema"], V.SCHEMA_INSTRUMENT)
                self.assertAlmostEqual(result.record["scan_window_mm"]["width"], width, delta=0.3)
                self.assertGreater(result.record["scan_window_mm"]["width"] / result.record["scan_window_mm"]["height"], 0.97)
                export = result.record["pixel_normalisation"]["instrument_metric_export"]
                self.assertAlmostEqual(export["mm_per_px_x_over_y"], 1.0, delta=0.01)
                for side, gap in result.record["grid_to_edge_gaps_mm"].items():
                    self.assertTrue(5.0 < gap < 15.0, (side, gap))


@unittest.skipUnless(REAL_SVD.is_file() and REAL_UNV.is_file(), "the 261016 plate measurement is not on this machine")
class RealPlate261016Tests(unittest.TestCase):
    """Session 261016 of the 0.875 mm plate (RESEARCH_ONLY / PHYSICAL_REGISTRATION_NOT_VERIFIED; README 23, 24)."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "tools"))
        from reconstruct_psv_registration import unv_scan_geometry

        cls.svd = REAL_SVD.read_bytes()
        cls.ids, cls.xy = unv_scan_geometry(REAL_UNV)
        cls.result = V.reconstruct(cls.svd, cls.xy, cls.ids, 301.0, 300.0, sources={}, normalisation=V.NORMALISATION_INSTRUMENT)

    def test_frame_of_the_scan_points_comes_from_the_file(self):
        n = self.result.record["pixel_normalisation"]
        self.assertEqual(n["scan_points_frame"]["name"], "default point-list frame")
        self.assertEqual(n["scan_object_frame"]["name"], "full-frame rectangle")
        self.assertAlmostEqual(n["px_per_u"], 1440.0, delta=0.01)
        matching = [t for t in n["trials"] if t["hull_mismatch_px"] <= n["match_tolerance_px"]]
        self.assertEqual(len(matching), 1)
        self.assertLess(matching[0]["hull_mismatch_px"], 0.01)
        self.assertGreater(min(t["hull_mismatch_px"] for t in n["trials"] if t not in matching), 100.0)
        # PSV-SCAN-OBJECT-MARGIN-01: this grid is not turned; it is accepted by the first rule, in its earlier form
        cf = V.CompoundFile(self.svd)
        self.assertEqual(V.scan_grid_rotation(cf.read("Info/APS_Mixed/MeshObject1/ScanObjects")), (0, 0.0))
        self.assertEqual(set(n), V2_PIXEL_KEYS)

    def test_window_is_about_287_by_285_mm(self):
        window, gaps = self.result.record["scan_window_mm"], self.result.record["grid_to_edge_gaps_mm"]
        self.assertAlmostEqual(window["width"], 287.1, delta=0.3)
        self.assertAlmostEqual(window["height"], 285.3, delta=1.0)  # the unattended bottom-edge fit differs from M11 (deviation 3)
        for side in ("left", "right", "bottom", "top"):
            self.assertTrue(5.0 < gaps[side] < 9.5, (side, gaps[side]))

    @unittest.skipUnless(REAL_M11.is_file(), "the M11 reconstruction record is not on this machine")
    def test_window_with_the_recorded_plate_corners(self):
        record = json.loads(REAL_M11.read_text(encoding="utf-8"))
        c = record["panel_corners_px"]
        cf = V.CompoundFile(self.svd)
        meas = cf.read("Info/Geometry/MeasPoints")
        uv = V.measpoints_uv(meas, len(self.ids))
        n = V.resolve_pixel_normalisation(uv, V.video_frame(cf.read("Info/VideoBitmap")).size, measpoints=meas,
                                          defaults=cf.read("Info/APS_Mixed/MeshObject1/DefaultSettings"),
                                          scan_objects=cf.read("Info/APS_Mixed/MeshObject1/ScanObjects"),
                                          video_settings=cf.read("Info/VideoSettings"))
        h = V.homography(np.array([c["left-bottom"], c["right-bottom"], c["right-top"], c["left-top"]]),
                         np.array([[0.0, 0.0], [301.0, 0.0], [301.0, 300.0], [0.0, 300.0]]))
        panel = V.apply_homography(h, n.points_px(uv))
        self.assertAlmostEqual(np.ptp(panel[:, 0]), 287.1, delta=0.05)
        self.assertAlmostEqual(np.ptp(panel[:, 1]), 285.3, delta=0.05)
        old = np.array(record["scan_points_panel_mm"])
        self.assertAlmostEqual(np.ptp(old[:, 0]) / np.ptp(panel[:, 0]), 0.75, delta=0.001)  # the recorded, compressed window
        self.assertAlmostEqual(np.linalg.norm(panel - old, axis=1).max(), 49.3, delta=0.1)


if __name__ == "__main__":
    unittest.main()
