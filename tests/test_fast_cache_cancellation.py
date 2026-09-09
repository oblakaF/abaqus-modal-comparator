from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import abaqus_bridge
import fast_cache


_ORIGINAL_LOADER = getattr(
    fast_cache,
    "_ORIGINAL_EXTRACTED_ODB_LOADER",
    abaqus_bridge.load_extracted_odb,
)


def _write_extracted_package(directory: Path) -> Path:
    mode_path = directory / "mode_0007.csv"
    mode_path.write_text(
        "instance,node_label,x,y,z,u1_real,u2_real,u3_real,u1_imag,u2_imag,u3_imag\n"
        "PART-1,1,1.0,2.0,3.0,0.1,0.2,0.3,0,0,0\n",
        encoding="utf-8",
    )
    manifest_path = directory / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "format_version": 1,
                "step_name": "Step-1",
                "start_mode": 7,
                "end_mode": 7,
                "modes": [
                    {
                        "mode": 7,
                        "frequency_hz": 24.1,
                        "file": mode_path.name,
                        "frame_index": 0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


class _CancelOnCheck:
    def __init__(self, cancelled_call: int):
        self.cancelled_call = cancelled_call
        self.calls = 0

    def is_set(self) -> bool:
        self.calls += 1
        return self.calls >= self.cancelled_call


class FastCacheCancellationTests(unittest.TestCase):
    def test_installed_wrapper_accepts_cancel_event_without_type_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = _write_extracted_package(root)
            event = threading.Event()
            with patch.object(
                fast_cache,
                "_ORIGINAL_EXTRACTED_ODB_LOADER",
                _ORIGINAL_LOADER,
                create=True,
            ), patch.object(
                fast_cache, "_user_cache_root", lambda: root / "binary"
            ), patch.object(
                abaqus_bridge,
                "load_extracted_odb",
                fast_cache._cached_extracted_odb_loader,
            ):
                dataset = abaqus_bridge.load_extracted_odb(
                    manifest_path, cancel_event=event
                )
        self.assertEqual(dataset.modes[0].frequency_hz, 24.1)

    def test_cache_miss_propagates_cancel_event_to_original_loader(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = _write_extracted_package(root)
            event = threading.Event()
            seen = []

            def loader(path, cancel_event=None):
                seen.append((Path(path), cancel_event))
                return _ORIGINAL_LOADER(path, cancel_event=cancel_event)

            with patch.object(
                fast_cache,
                "_ORIGINAL_EXTRACTED_ODB_LOADER",
                loader,
                create=True,
            ), patch.object(fast_cache, "_user_cache_root", lambda: root / "binary"):
                fast_cache._cached_extracted_odb_loader(
                    manifest_path, cancel_event=event
                )

        self.assertEqual(seen, [(manifest_path.resolve(), event)])

    def test_already_cancelled_fails_before_cache_work(self):
        event = threading.Event()
        event.set()
        with self.assertRaisesRegex(
            abaqus_bridge.AnalysisCancelled, "Analysis stopped by user"
        ):
            fast_cache._cached_extracted_odb_loader(
                Path("manifest-does-not-need-to-exist.json"), cancel_event=event
            )

    def test_disk_cache_hit_checks_after_load_and_before_return(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = _write_extracted_package(root)
            with patch.object(
                fast_cache,
                "_ORIGINAL_EXTRACTED_ODB_LOADER",
                _ORIGINAL_LOADER,
                create=True,
            ), patch.object(fast_cache, "_user_cache_root", lambda: root / "binary"):
                fast_cache._cached_extracted_odb_loader(manifest_path)

                original_pickle_load = fast_cache._pickle_load
                cancelled_after_load = threading.Event()

                def load_then_cancel(*args, **kwargs):
                    payload = original_pickle_load(*args, **kwargs)
                    cancelled_after_load.set()
                    return payload

                with patch.object(
                    fast_cache, "_pickle_load", side_effect=load_then_cancel
                ), self.assertRaises(abaqus_bridge.AnalysisCancelled):
                    fast_cache._cached_extracted_odb_loader(
                        manifest_path, cancel_event=cancelled_after_load
                    )

                cancelled_before_return = _CancelOnCheck(3)
                with self.assertRaises(abaqus_bridge.AnalysisCancelled):
                    fast_cache._cached_extracted_odb_loader(
                        manifest_path, cancel_event=cancelled_before_return
                    )
                self.assertEqual(cancelled_before_return.calls, 3)

    def test_ordinary_disk_cache_hit_returns_same_scientific_dataset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = _write_extracted_package(root)
            with patch.object(
                fast_cache,
                "_ORIGINAL_EXTRACTED_ODB_LOADER",
                _ORIGINAL_LOADER,
                create=True,
            ), patch.object(fast_cache, "_user_cache_root", lambda: root / "binary"):
                first = fast_cache._cached_extracted_odb_loader(manifest_path)
                second = fast_cache._cached_extracted_odb_loader(manifest_path)

        self.assertEqual(second.metadata["binary_odb_cache_reused"], True)
        self.assertEqual(first.modes[0].number, second.modes[0].number)
        self.assertEqual(first.modes[0].frequency_hz, second.modes[0].frequency_hz)
        self.assertEqual(
            first.modes[0].coordinates.tolist(), second.modes[0].coordinates.tolist()
        )
        self.assertEqual(first.modes[0].vectors.tolist(), second.modes[0].vectors.tolist())

    def test_load_or_extract_uses_valid_extraction_cache_with_wrapper_installed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            odb_path = root / "model.odb"
            odb_path.write_bytes(b"synthetic odb signature")
            extraction_cache = root / "extracted"
            extraction_cache.mkdir()
            manifest_path = _write_extracted_package(extraction_cache)
            signature = abaqus_bridge._source_signature(odb_path, "abaqus", 7, 7)
            (extraction_cache / "extraction_signature.json").write_text(
                json.dumps(signature), encoding="utf-8"
            )
            event = threading.Event()

            with patch.object(
                fast_cache,
                "_ORIGINAL_EXTRACTED_ODB_LOADER",
                _ORIGINAL_LOADER,
                create=True,
            ), patch.object(
                fast_cache, "_user_cache_root", lambda: root / "binary"
            ), patch.object(
                abaqus_bridge,
                "load_extracted_odb",
                fast_cache._cached_extracted_odb_loader,
            ), patch.object(
                abaqus_bridge,
                "run_abaqus_extraction",
                side_effect=AssertionError("valid extraction cache was not reused"),
            ):
                dataset = abaqus_bridge.load_or_extract_odb(
                    odb_path,
                    extraction_cache,
                    "abaqus",
                    7,
                    7,
                    cancel_event=event,
                )

        self.assertEqual(dataset.modes[0].frequency_hz, 24.1)
        self.assertTrue(dataset.metadata["extraction_cache_reused"])


if __name__ == "__main__":
    unittest.main()
