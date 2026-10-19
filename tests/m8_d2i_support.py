"""M8-D2i test support: a synthetic two-specimen SPEC v1.2 campaign with archived packs and archived ODBs, a real
Execution Plan of it, and an ISOLATED simulated authorisation authority (tests only; never reachable from ``src``).

The synthetic world mirrors the real SP-02 + SP-13 plan:

- 4 initial points are reused from archived shape packs: A p0, B p0, B E+, B E-;
- 2 initial points are archived ODBs that need an extraction: A E+, A E-.

Every solve and extraction is a fake executor from the accepted M4.6 / M7 test support.  Nothing is written outside
the temporary folder.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import replace
import hashlib
import hmac
import json
import os
from pathlib import Path
import shutil
from unittest import mock

from domain.campaign_definition import ARCHIVE_REUSE_SCHEMA, CAMPAIGN_SCHEMA_V1_2, parse_campaign_definition
from domain.identification_run import canonical_hash
from m4_6_support import FakeExtractor, FakeSolver
from services import campaign_execution_plan as plan_module
from services import guarded_execution as guarded_module
from services import identification_campaign_run as campaign_module
from services.campaign_execution_plan import prepare_execution_plan
from services.guarded_execution import ExecutionAuthorisation, open_execution_context, operation_budget
from services.identification_pipeline import forward_jobs
from services.prerun_validation import SECTIONS, PrerunValidation
from services.shape_extraction import extract_shape_pack
import test_m7_campaign as m7

RELEASE = "Abaqus 2024"
REUSE_PATH = "docs/syn/SYN.archive-reuse.json"


class SimulatedAuthority:
    """TEST ONLY: a simulated trusted HUMAN authority (HMAC with a per-instance random key)."""

    name = "TEST-ONLY simulated HUMAN authority"
    simulated = True
    available = True
    unavailable_reason = ""

    def __init__(self) -> None:
        self._key = os.urandom(32)

    def _sign(self, authorisation: ExecutionAuthorisation) -> str:
        message = json.dumps(authorisation.binding(), sort_keys=True).encode("utf-8")
        return hmac.new(self._key, message, hashlib.sha256).hexdigest()

    def issue(self, context, operation: str, **override) -> ExecutionAuthorisation:
        fields = dict(operation=operation, authorisation_scope_hash=context.scope_hash,
                      campaign_hash=context.campaign_hash, manifest_hash=context.manifest_hash,
                      budget=operation_budget(context.scope, operation), authorised_by="TEST HUMAN (simulated)")
        fields.update(override)
        unsigned = ExecutionAuthorisation(attestation="", **fields)
        return replace(unsigned, attestation=self._sign(unsigned))

    def attests(self, authorisation: ExecutionAuthorisation) -> bool:
        return hmac.compare_digest(authorisation.attestation, self._sign(authorisation))

    def authorisation_for(self, context, operation: str) -> ExecutionAuthorisation:
        return self.issue(context, operation)


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _fake_odb(solver: FakeSolver, job, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    solver(f"job={job.job_name} input={job.generated_inp}", directory)
    return directory / f"{job.job_name}.odb"


class SyntheticWorld:
    """The synthetic campaign, its governed-looking records in a temporary repository and its data stores."""

    def __init__(self, tmp: Path, **definition_changes) -> None:
        self.tmp = Path(tmp)
        self.repo = self.tmp / "repo"
        (self.repo / "docs" / "syn").mkdir(parents=True)
        data = m7.synthetic_definition(schema=CAMPAIGN_SCHEMA_V1_2, scientific_question="MATERIAL_IDENTIFICATION",
                                       tau_mf=0.01, campaign_id="SYN/M8-D2i", archive_reuse=REUSE_PATH,
                                       decision="TEST: synthetic M8-D2i campaign", run_b_gate=None)
        data.update(definition_changes)
        self.data = data
        self.definition = parse_campaign_definition(data)
        self.definition_path = self.tmp / "definitions" / "syn.campaign.json"
        self.definition_path.parent.mkdir(parents=True)
        self.definition_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.items, store = [], None
        for label in ("A", "B"):
            item, store = m7.synthetic_specimen(self.definition, label, self.tmp)
            self.items.append(item)
        self.archive, self.governed_packs = self.tmp / "syn_archive", self.tmp / "syn_packs"
        self.roots = {"synthetic": store, "syn-archive": self.archive, "syn-archive-packs": self.governed_packs}
        self._archived_inputs()

    def _archived_inputs(self) -> None:
        points = campaign_module.initial_points(self.definition)
        solver, packs, odbs = FakeSolver(), [], []
        for item in self.items:
            jobs = forward_jobs(item.model, self.roots, points, self.tmp / "archive_jobs" / item.label)
            for point_id, job in jobs.items():
                if item.label == "A" and point_id != "p0":  # an archived accepted ODB: extraction needed
                    folder = self.archive / "runs" / job.job_name
                    odb = _fake_odb(solver, job, folder)
                    scratch = self.tmp / "scratch_extraction" / job.job_name
                    pack, _ = extract_shape_pack(job.job_name, job.generated_inp_sha256, odb, _sha(odb),
                                                 odb.stat().st_size, item.expectation, scratch, FakeExtractor(),
                                                 RELEASE)
                    shutil.rmtree(scratch)
                    relative = f"runs/{job.job_name}"
                    odbs.append({"specimen": item.label, "point": points[point_id], "job_name": job.job_name,
                                 "generated_inp_sha256": job.generated_inp_sha256,
                                 "odb": {"store": "syn-archive", "relative_path": f"{relative}/{job.job_name}.odb",
                                         "sha256": _sha(odb), "size_bytes": odb.stat().st_size,
                                         "pin_source": "synthetic archive (test)"},
                                 "status_files": {f"{relative}/{job.job_name}{suffix}":
                                                  _sha(folder / f"{job.job_name}{suffix}") for suffix in (".sta", ".dat")},
                                 "expected_frequencies": {"mode_numbers": list(pack.mode_numbers),
                                                          "frequencies_hz": list(pack.frequencies_hz),
                                                          "source": "synthetic (test)"},
                                 "excluded_attempts": []})
                else:  # a validated archived pack, governed by a record in the (temporary) repository
                    odb = _fake_odb(solver, job, self.tmp / "pack_solves" / job.job_name)
                    extract_shape_pack(job.job_name, job.generated_inp_sha256, odb, _sha(odb), odb.stat().st_size,
                                       item.expectation, self.governed_packs / "packs", FakeExtractor(), RELEASE)
                    record = f"docs/syn/{job.job_name}.shape-pack.json"
                    shutil.copyfile(self.governed_packs / "packs" / f"{job.job_name}.shape-pack.json", self.repo / record)
                    packs.append({"specimen": item.label, "point": points[point_id], "job_name": job.job_name,
                                  "generated_inp_sha256": job.generated_inp_sha256, "shape_pack_record": record,
                                  "pack_store": "syn-archive-packs"})
        self.reuse_document = {"schema": ARCHIVE_REUSE_SCHEMA, "packs": packs, "odbs": odbs,
                               "provenance": ["synthetic M8-D2i test archive (fake executors)"]}
        self.write_reuse(self.reuse_document)

    def write_reuse(self, document) -> None:
        (self.repo / REUSE_PATH).write_text(json.dumps(document, indent=1), encoding="utf-8")

    def passing_prerun(self, path, *args, **kwargs) -> PrerunValidation:
        sections = dict(zip(SECTIONS, ("FORMALLY_VALID", "SHA256_VERIFIED", "COUNT_CONDITIONS_MET", "NOT_ASSESSED",
                                       "NOT_EVALUATED", "NOT_AUTHORISED")))
        from domain.campaign_definition import load_campaign_definition

        return PrerunValidation(str(path), (), sections, load_campaign_definition(path).campaign_hash)

    @contextmanager
    def patched(self):
        """Pre-run passes (synthetic specimens are not governed records) and the specimens are the synthetic inputs;
        everything else is the real planning sequence and the real executor."""
        with ExitStack() as stack:
            for module in (plan_module, guarded_module):
                stack.enter_context(mock.patch.object(module, "prerun_validation", side_effect=self.passing_prerun))
            stack.enter_context(mock.patch.object(campaign_module, "prepare_campaign_specimens",
                                                  side_effect=lambda *a, **k: tuple(self.items)))
            yield

    def plan(self, work: Path):
        work.mkdir(parents=True, exist_ok=True)
        with self.patched():
            return prepare_execution_plan(self.definition_path, work, self.repo, None, self.roots, (self.repo,))

    def context(self, work: Path):
        with self.patched():
            return open_execution_context(work, self.repo, None, self.roots)

    def recheck(self, work: Path):
        return lambda: self.context(work)


def tree(folder: Path) -> dict:
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(folder).rglob("*")) if p.is_file()}


def journal_hash(path: Path) -> str:
    return canonical_hash(json.loads(Path(path).read_text(encoding="utf-8")))
