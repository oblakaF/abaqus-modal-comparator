"""M4 development batch guard: generic modules only, no Abaqus execution, no M3 contract changes."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
M4_MODULES = (
    "src/domain/identification_pairing_policy.py",
    "src/services/identification_pairing.py",
    "src/domain/frozen_observations.py",
    "src/services/baseline_freeze.py",
    "src/services/archived_baseline.py",
    "src/services/modal_family_classifier.py",
    "src/services/identification_clusters.py",
    "src/services/branch_tracker.py",
    "src/services/identification_objective.py",
    "src/services/identification_step.py",
)
FORBIDDEN_TEXT = ("SP02", "SP13", "SP-02", "SP-13", "Snadwich", "snadwich", "carbon_project_archive", "D:\\",
                  "CFRP_T300_PlainWeave", "CFRP_Face")
# This batch executes no Abaqus (no solver, no Abaqus Python) and does not touch INP generation.
FORBIDDEN_IMPORTS = ("subprocess", "abaqus_bridge", "services.matrix_model_service", "matrix_model_service",
                     "services.shared_carbon_forward", "shared_carbon_forward", "services.forward_builder",
                     "forward_builder", "sp13_evidence_adapter", "modal_core")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    names |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    return names


class M4GuardTests(unittest.TestCase):
    def test_no_specimen_or_machine_literals(self):
        for module in M4_MODULES:
            text = (ROOT / module).read_text(encoding="utf-8")
            for token in FORBIDDEN_TEXT:
                with self.subTest(module=module, token=token):
                    self.assertNotIn(token, text)

    def test_no_abaqus_execution_or_inp_generation(self):
        for module in M4_MODULES:
            imported = _imports(ROOT / module)
            for name in FORBIDDEN_IMPORTS:
                with self.subTest(module=module, name=name):
                    self.assertFalse(any(item == name or item.endswith("." + name) for item in imported))


if __name__ == "__main__":
    unittest.main()
