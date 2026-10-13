"""Audit F5: a manifest.json left by an earlier extraction is never returned as the new result."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from abaqus_bridge import AbaqusExtractionError, run_abaqus_extraction  # noqa: E402


class _Done:
    pid = 4242
    returncode = 0

    def poll(self):
        return 0


class StaleManifestTests(unittest.TestCase):
    def test_launcher_without_output_does_not_return_the_old_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            output.mkdir()
            (output / "manifest.json").write_text('{"odb_path": "OLD.odb"}', encoding="utf-8")
            with patch("abaqus_bridge.subprocess.Popen", return_value=_Done()):
                with self.assertRaises(AbaqusExtractionError):
                    run_abaqus_extraction(Path(directory) / "new.odb", output, abaqus_command="abaqus")


if __name__ == "__main__":
    unittest.main()
