"""M3.4: the generic forward path has no hard-coded specimens, materials or machine paths."""

from __future__ import annotations

import ast
import hashlib
import inspect
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.experiment_fixture import FixtureSourceMismatchError, FixtureSourceUnavailableError
from domain.experiment_fixture import load_experiment_fixture_manifest
from domain.forward_model_manifest import bind_forward_model, carbon_candidate
from m3_support import FIXTURES, FORWARD_MODELS, SYNTHETIC_INP, forward_manifest, synthetic_passport
from services import forward_builder
from services.forward_builder import (
    ForwardBuildError,
    load_bound_forward_model,
    locate_engineering_constants,
    prepare_forward_jobs,
    read_reference_input,
    split_inp_lines,
)


GENERIC_MODULES = (ROOT / "src" / "domain" / "forward_model_manifest.py", ROOT / "src" / "services" / "forward_builder.py")
FORBIDDEN_TEXT = ("SP02", "SP13", "SP-02", "SP-13", "Snadwich", "snadwich", "carbon_project_archive", "D:\\",
                  "CFRP_T300_PlainWeave", "CFRP_Face", "SP02_Modal_V02", "SP13_mesh_local")
FORBIDDEN_IMPORTS = ("services.shared_carbon_forward", "shared_carbon_forward", "sp13_evidence_adapter")


class NoHardCodingTests(unittest.TestCase):
    def test_generic_modules_name_no_specimen_material_or_machine_path(self):
        for module in GENERIC_MODULES:
            text = module.read_text(encoding="utf-8")
            for token in FORBIDDEN_TEXT:
                with self.subTest(module=module.name, token=token):
                    self.assertNotIn(token, text)

    def test_generic_modules_do_not_use_the_legacy_builder(self):
        for module in GENERIC_MODULES:
            tree = ast.parse(module.read_text(encoding="utf-8"))
            imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
            imported |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
            for name in FORBIDDEN_IMPORTS:
                with self.subTest(module=module.name, name=name):
                    self.assertFalse(any(item == name or item.endswith("." + name) for item in imported))

    def test_no_default_specimens(self):
        for function in (prepare_forward_jobs, forward_builder.prepare_forward_evaluation,
                         forward_builder.prepare_forward_job, forward_builder.render_forward_input):
            with self.subTest(function=function.__name__):
                parameters = inspect.signature(function).parameters.values()
                self.assertTrue(all(parameter.default is inspect.Parameter.empty for parameter in parameters))
        with self.assertRaises(ForwardBuildError):
            prepare_forward_jobs([], carbon_candidate(52000.0, 4500.0), {}, Path(tempfile.gettempdir()))

    def test_accepted_manifests_hold_no_machine_paths(self):
        for path in sorted(FORWARD_MODELS.glob("*.forward.json")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn(":\\", text)
                self.assertNotIn("D:/", text)

    def test_accepted_models_load_from_manifests_alone(self):
        fixtures = load_experiment_fixture_manifest(FIXTURES)
        for name in ("SP02", "SP13"):
            with self.subTest(name=name):
                model = load_bound_forward_model(FORWARD_MODELS / f"{name}.forward.json", ROOT, fixtures)
                self.assertEqual(model.material_name, model.passport.materials["face"])
                self.assertEqual(model.manifest.model_input.location.store, "snadwich")


class ThirdSpecimenTests(unittest.TestCase):
    """A specimen the code has never seen: another store, material name, prefix and eigenvalue request."""

    TEXT = (SYNTHETIC_INP.replace("CFRP_Face", "CFRP_Twill_350").replace("15, , , , ,", "20, , , , ,"))

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.store = Path(self._directory.name) / "store"
        (self.store / "plates" / "twill").mkdir(parents=True)
        self.raw = self.TEXT.encode("latin-1")
        (self.store / "plates" / "twill" / "twill.inp").write_bytes(self.raw)
        passport = synthetic_passport(materials={"face": "CFRP_Twill_350", "core": "PLA_Auxetic", "adhesive": "DP420"},
                                      design_id="DES-TWILL", test_run_id="RUN-TWILL-1")
        manifest = forward_manifest(
            passport, self.raw, forward_model_id="TWILL/carbon-property-set-v1", job_prefix="TWILL",
            model_input__file_name="twill.inp",
            model_input__location={"store": "lab-store", "relative_path": "plates/twill/twill.inp"},
            frequency_request={"source_eigenvalue_count": 20, "requested_eigenvalue_count": 40})
        self.model = bind_forward_model(manifest, passport)

    def tearDown(self):
        self._directory.cleanup()

    def test_job_from_manifest_and_store_only(self):
        output = Path(self._directory.name) / "jobs"
        evaluation = prepare_forward_jobs([self.model], carbon_candidate(47000.0, 4100.0), {"lab-store": self.store},
                                          output)
        job = evaluation.jobs[0]
        self.assertTrue(job.job_name.startswith("TWILL_"))
        lines = split_inp_lines(job.generated_inp.read_bytes())
        record = locate_engineering_constants(lines, "CFRP_Twill_350")
        self.assertEqual((record.values.E1, record.values.E2, record.values.G12), (47000.0, 47000.0, 4100.0))
        self.assertIn("40, , , , ,\n", lines)
        self.assertEqual(job.provenance["material"]["name"], "CFRP_Twill_350")
        self.assertEqual(job.provenance["specimen"]["test_run_id"], "RUN-TWILL-1")
        self.assertEqual(job.elastic_mode_count, 34)

    def test_store_must_be_configured_and_match(self):
        with self.assertRaises(FixtureSourceUnavailableError):
            read_reference_input(self.model, {})
        (self.store / "plates" / "twill" / "twill.inp").write_bytes(self.raw + b"x")
        with self.assertRaises(FixtureSourceMismatchError):  # size pinned by the manifest
            read_reference_input(self.model, {"lab-store": self.store})
        same_size = bytearray(self.raw)
        same_size[-2] = ord("9")
        (self.store / "plates" / "twill" / "twill.inp").write_bytes(bytes(same_size))
        self.assertNotEqual(hashlib.sha256(bytes(same_size)).hexdigest(), self.model.manifest.model_input.sha256)
        with self.assertRaises(ForwardBuildError):  # SHA-256 checked on the bytes actually used
            prepare_forward_jobs([self.model], carbon_candidate(47000.0, 4100.0), {"lab-store": self.store},
                                 Path(self._directory.name) / "jobs")


if __name__ == "__main__":
    unittest.main()
