"""M3 stage gate on real data: the universal builder is byte-identical to the accepted builder (SPEC §17 M3).

Needs the data store AUTO_ID_FIXTURE_ROOT_SNADWICH (the pinned reference INPs); skips with
the reason otherwise.  No Abaqus: jobs are prepared, never solved.

Two independent references:
- the live accepted builder ``services.shared_carbon_forward`` (unchanged since 121ba1d),
  run on the same reference INPs;
- the archived identities of the CARBON-4C / CARBON-5A jobs that were solved in Abaqus
  (``docs/auto_id/forward_models/accepted_forward_jobs.json``).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.experiment_fixture import fixture_roots_from_environment, load_experiment_fixture_manifest
from domain.forward_model_manifest import canonical_hash, carbon_candidate
from services.forward_builder import (
    forward_job_name,
    forward_job_provenance,
    load_bound_forward_model,
    prepare_forward_jobs,
    read_reference_input,
    render_forward_input,
)
from services.shared_carbon_forward import (
    SharedCarbonCandidate,
    sp02_forward_baseline,
    sp13_forward_baseline,
    write_forward_job_inp,
)
from domain.experiment_fixture import resolve_external_file


FORWARD_MODELS = ROOT / "docs" / "auto_id" / "forward_models"
FIXTURES = ROOT / "docs" / "auto_id" / "fixtures" / "real_experiment_fixtures.json"
ORACLE_BASELINES = {"SP02": sp02_forward_baseline, "SP13": sp13_forward_baseline}


def legacy_job_hash(legacy_specimen_id: str, provenance: dict) -> str:
    """The accepted builder's ``shared-carbon-forward-job/1`` hash, rebuilt from a generic job's facts."""
    return canonical_hash({
        "schema": "shared-carbon-forward-job/1",
        "specimen_id": legacy_specimen_id,
        "source_inp_sha256": provenance["source_inp"]["sha256"],
        "carbon_material_name": provenance["material"]["name"],
        "candidate": provenance["candidate"],
        "engineering_constants": provenance["engineering_constants"],
        "registration_hash": provenance["registration_hash"],
        "requested_eigenvalue_count": provenance["frequency_request"]["requested_eigenvalue_count"],
        "elastic_mode_count": provenance["frequency_request"]["elastic_mode_count"],
        "generated_inp_sha256": provenance["generated_inp"]["sha256"],
    })


class M3StageGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roots = fixture_roots_from_environment()
        if "snadwich" not in cls.roots:
            raise unittest.SkipTest("data store 'snadwich' (reference INPs) not configured")
        fixtures = load_experiment_fixture_manifest(FIXTURES)
        cls.models = {name: load_bound_forward_model(FORWARD_MODELS / f"{name}.forward.json", ROOT, fixtures)
                      for name in ("SP02", "SP13")}
        cls.sources = {name: read_reference_input(model, cls.roots) for name, model in cls.models.items()}
        with open(FORWARD_MODELS / "accepted_forward_jobs.json", encoding="utf-8") as handle:
            cls.accepted = json.load(handle)

    def test_byte_identical_to_the_accepted_builder_and_the_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            for record in self.accepted["candidates"]:
                candidate = carbon_candidate(record["e_in_plane_mpa"], record["g12_mpa"])
                legacy_hashes = []
                for name, model in self.models.items():
                    expected = record["jobs"][name]
                    with self.subTest(candidate=record["name"], specimen=name):
                        rendered = render_forward_input(model, candidate, self.sources[name])
                        # 1. Live accepted builder on the same reference INP: identical bytes.
                        source_path = resolve_external_file(model.manifest.model_input, self.roots,
                                                            verify_sha256=False)
                        oracle = write_forward_job_inp(
                            ORACLE_BASELINES[name](source_inp=source_path),
                            SharedCarbonCandidate(record["e_in_plane_mpa"], record["g12_mpa"]), Path(directory))
                        oracle_bytes = oracle.generated_inp.read_bytes()
                        oracle.generated_inp.unlink()
                        self.assertEqual(len(rendered.content), len(oracle_bytes))
                        self.assertTrue(rendered.content == oracle_bytes, "generated INP bytes differ")
                        # 2. Archived identity of the job that was solved in Abaqus.
                        self.assertEqual(rendered.sha256, expected["generated_inp_sha256"])
                        self.assertEqual([i + 1 for i in rendered.changed_lines], expected["changed_lines_1based"])
                        self.assertEqual(forward_job_name(model.manifest.job_prefix, rendered.sha256),
                                         oracle.generated_inp.stem)
                        # 3. The generic provenance carries every fact of the accepted provenance.
                        provenance = forward_job_provenance(model, candidate, rendered)
                        legacy = legacy_job_hash(expected["legacy_specimen_id"], provenance)
                        self.assertEqual(legacy, expected["legacy_provenance_hash"])
                        self.assertEqual(legacy, oracle.provenance_hash)
                        legacy_hashes.append(legacy)
                        del rendered, oracle_bytes
                with self.subTest(candidate=record["name"], evaluation=True):
                    evaluation = canonical_hash({"schema": "shared-carbon-forward-evaluation/1",
                                                 "candidate": candidate.to_dict(), "jobs": legacy_hashes})
                    self.assertEqual(evaluation, record["legacy_evaluation_hash"])

    def test_end_to_end_jobs_carry_the_archived_names(self):
        baseline = self.accepted["candidates"][0]
        self.assertEqual(baseline["name"], "CARBON-4C BASELINE")
        with tempfile.TemporaryDirectory() as directory:
            evaluation = prepare_forward_jobs(list(self.models.values()),
                                              carbon_candidate(baseline["e_in_plane_mpa"], baseline["g12_mpa"]),
                                              self.roots, Path(directory))
            for job, name in zip(evaluation.jobs, self.models):
                with self.subTest(specimen=name):
                    expected = baseline["jobs"][name]["generated_inp_sha256"]
                    self.assertEqual(job.generated_inp_sha256, expected)
                    self.assertEqual(hashlib.sha256(job.generated_inp.read_bytes()).hexdigest(), expected)
                    self.assertEqual(job.job_name, f"{self.models[name].manifest.job_prefix}_{expected[:16]}")
                    self.assertEqual(job.registration_hash, self.models[name].manifest.registration_hash)
                    self.assertEqual(job.engineering_constants.nu12, 0.05)
            again = prepare_forward_jobs(list(self.models.values()),
                                         carbon_candidate(baseline["e_in_plane_mpa"], baseline["g12_mpa"]),
                                         self.roots, Path(directory))
            self.assertEqual(again.evaluation_hash, evaluation.evaluation_hash)


if __name__ == "__main__":
    unittest.main()
