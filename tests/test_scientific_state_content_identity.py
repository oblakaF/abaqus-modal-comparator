from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import scientific_state
from scientific_state import (
    experimental_source_content_identity,
    experimental_source_identity,
    source_identity_matches,
)


class ExperimentalSourceContentIdentityTests(unittest.TestCase):
    def setUp(self):
        scientific_state._CONTENT_HASH_CACHE.clear()
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.directory = Path(self._directory.name)

    def write(self, name: str, payload: bytes) -> Path:
        path = self.directory / name
        path.write_bytes(payload)
        return path

    def test_identity_contains_path_metadata_and_sha256_of_content(self):
        source = self.write("SP13.unv", b"SP13 modal dataset")
        identity = experimental_source_content_identity(source)
        stat = source.stat()
        self.assertEqual(
            identity,
            {
                "path": os.path.normcase(str(source.resolve())),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "sha256": hashlib.sha256(b"SP13 modal dataset").hexdigest(),
            },
        )

    def test_same_content_at_different_paths_shares_sha256(self):
        first = self.write("SP13_a.unv", b"identical modal content")
        second = self.write("SP13_b.unv", b"identical modal content")
        first_identity = experimental_source_content_identity(first)
        second_identity = experimental_source_content_identity(second)
        self.assertEqual(first_identity["sha256"], second_identity["sha256"])
        self.assertNotEqual(first_identity["path"], second_identity["path"])

    def test_modified_content_changes_sha256(self):
        source = self.write("SP13.unv", b"original content")
        before = experimental_source_content_identity(source)
        source.write_bytes(b"modified content!")
        after = experimental_source_content_identity(source)
        self.assertNotEqual(before["sha256"], after["sha256"])
        self.assertEqual(
            after["sha256"], hashlib.sha256(b"modified content!").hexdigest()
        )

    def test_unchanged_path_size_and_mtime_reads_file_once(self):
        source = self.write("SP13.unv", b"cached content")
        with patch.object(
            scientific_state,
            "_file_sha256",
            wraps=scientific_state._file_sha256,
        ) as spy:
            first = experimental_source_content_identity(source)
            second = experimental_source_content_identity(str(source))
        self.assertEqual(spy.call_count, 1)
        self.assertEqual(first, second)

    def test_changed_size_or_mtime_recomputes_sha256(self):
        source = self.write("SP13.unv", b"version one")
        original_mtime_ns = source.stat().st_mtime_ns
        with patch.object(
            scientific_state,
            "_file_sha256",
            wraps=scientific_state._file_sha256,
        ) as spy:
            first = experimental_source_content_identity(source)
            # Same size, different content; force a distinct mtime_ns so the
            # test does not depend on file-system timestamp resolution.
            source.write_bytes(b"version two")
            os.utime(source, ns=(original_mtime_ns, original_mtime_ns + 1_000_000_000))
            second = experimental_source_content_identity(source)
            source.write_bytes(b"version three, longer")
            os.utime(source, ns=(original_mtime_ns, original_mtime_ns + 1_000_000_000))
            third = experimental_source_content_identity(source)
        self.assertEqual(spy.call_count, 3)
        self.assertEqual(second["size"], first["size"])
        self.assertNotEqual(second["mtime_ns"], first["mtime_ns"])
        self.assertEqual(second["sha256"], hashlib.sha256(b"version two").hexdigest())
        self.assertEqual(second["mtime_ns"], third["mtime_ns"])
        self.assertEqual(
            third["sha256"], hashlib.sha256(b"version three, longer").hexdigest()
        )

    def test_missing_empty_and_non_regular_paths_are_not_bindable(self):
        self.assertIsNone(
            experimental_source_content_identity(self.directory / "missing.unv")
        )
        self.assertIsNone(experimental_source_content_identity(""))
        self.assertIsNone(experimental_source_content_identity("   "))
        self.assertIsNone(experimental_source_content_identity(self.directory))

    def test_file_changed_while_hashing_is_not_cached_or_bound(self):
        source = self.write("SP13.unv", b"being written")

        def hash_then_modify(path):
            digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
            source.write_bytes(b"being written, now longer")
            return digest

        with patch.object(scientific_state, "_file_sha256", side_effect=hash_then_modify):
            self.assertIsNone(experimental_source_content_identity(source))
        self.assertEqual(scientific_state._CONTENT_HASH_CACHE, {})


class LegacyExperimentalSourceIdentityTests(unittest.TestCase):
    def test_legacy_identity_format_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "SP05.unv"
            source.write_bytes(b"SP05")
            stat = source.stat()
            identity = experimental_source_identity(source)
            self.assertEqual(
                identity,
                {
                    "path": os.path.normcase(str(source.resolve())),
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                },
            )
            self.assertNotIn("sha256", identity)
            # Existing saved bindings compare only the legacy keys, so a
            # content identity of the same file still matches them.
            self.assertTrue(
                source_identity_matches(
                    identity, experimental_source_content_identity(source)
                )
            )
            self.assertIsNone(experimental_source_identity(Path(directory) / "missing"))
            self.assertIsNone(experimental_source_identity(""))
            # Legacy behavior for directories is preserved (stat succeeds).
            self.assertEqual(
                set(experimental_source_identity(directory)),
                {"path", "size", "mtime_ns"},
            )


if __name__ == "__main__":
    unittest.main()
