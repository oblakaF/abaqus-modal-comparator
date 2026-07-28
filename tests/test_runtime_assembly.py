from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class RuntimeAssemblyTests(unittest.TestCase):
    def test_main_assembles_expected_reviewed_runtime(self):
        import main
        from runtime_contracts import verify_runtime_contracts

        verify_runtime_contracts(main.app)
        self.assertEqual(
            main.app.ModalComparatorApp._worker.__module__,
            "runtime_hardening",
        )
        self.assertEqual(
            main.app.compare_modal_datasets.__module__,
            "modal_core",
        )


if __name__ == "__main__":
    unittest.main()
