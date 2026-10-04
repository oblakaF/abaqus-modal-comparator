"""M4 guard: generic modules only, controlled Abaqus execution paths, no M3 contract changes.

M4.6 allow-list (M4_DECISION_RECORD.md §6.4):
- ``subprocess`` only in ``services/forward_solver.py``;
- ``abaqus_bridge`` only in ``services/shape_extraction.py`` and only ``run_abaqus_extraction``
  (execution helper); its path/size/mtime cache (``load_or_extract_odb``) is never used;
- ``forward_builder`` (M3) only in ``services/identification_pipeline.py`` and, for the twin's truth
  job and the ±5 % job names (M4.9 preparation; read-only use of the M3 API), ``services/synthetic_twin.py``;
- never ``shared_carbon_forward``, ``matrix_model_service``, ``sp13_evidence_adapter`` or ``modal_core``.
"""

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
    "src/services/fe_shape_pack.py",
    "src/domain/identification_run.py",
    "src/services/forward_solver.py",
    "src/services/shape_extraction.py",
    "src/services/identification_pipeline.py",
    "src/services/synthetic_twin.py",
)
FORBIDDEN_TEXT = ("SP02", "SP13", "SP-02", "SP-13", "Snadwich", "snadwich", "carbon_project_archive", "D:\\",
                  "CFRP_T300_PlainWeave", "CFRP_Face", "load_or_extract_odb", "_source_signature",
                  "_cache_is_valid", "fast_cache")
FORBIDDEN_IMPORTS = ("subprocess", "abaqus_bridge", "services.matrix_model_service", "matrix_model_service",
                     "services.shared_carbon_forward", "shared_carbon_forward", "services.forward_builder",
                     "forward_builder", "sp13_evidence_adapter", "modal_core")
ALLOWED = {
    "src/services/forward_solver.py": {"subprocess"},
    "src/services/shape_extraction.py": {"abaqus_bridge"},
    "src/services/identification_pipeline.py": {"forward_builder", "services.forward_builder"},
    "src/services/synthetic_twin.py": {"forward_builder", "services.forward_builder"},
}


def _imports(path: Path) -> list[tuple[str, tuple[str, ...]]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.module, tuple(alias.name for alias in node.names)))
        elif isinstance(node, ast.Import):
            found.extend((alias.name, ()) for alias in node.names)
    return found


def _matches(module: str, name: str) -> bool:
    return module == name or module.endswith("." + name)


class M4GuardTests(unittest.TestCase):
    def test_no_specimen_machine_or_legacy_cache_literals(self):
        for module in M4_MODULES:
            text = (ROOT / module).read_text(encoding="utf-8")
            for token in FORBIDDEN_TEXT:
                with self.subTest(module=module, token=token):
                    self.assertNotIn(token, text)

    def test_controlled_imports(self):
        for module in M4_MODULES:
            allowed = ALLOWED.get(module, set())
            for imported, names in _imports(ROOT / module):
                for name in FORBIDDEN_IMPORTS:
                    if _matches(imported, name):
                        with self.subTest(module=module, imported=imported):
                            self.assertTrue(any(_matches(imported, item) for item in allowed),
                                            f"{module} may not import {imported}")
                if _matches(imported, "abaqus_bridge"):
                    with self.subTest(module=module, names=names):
                        self.assertEqual(names, ("run_abaqus_extraction",))

    def test_subprocess_only_in_the_solver(self):
        users = [module for module in M4_MODULES
                 if any(_matches(imported, "subprocess") for imported, _ in _imports(ROOT / module))]
        self.assertEqual(users, ["src/services/forward_solver.py"])


if __name__ == "__main__":
    unittest.main()
