"""M8-D2h — Auto-ID Execution Plan of a saved SPEC v1.2 campaign definition (a plan only; execution NOT_AUTHORISED).

A definition exported by M8-D2g is re-checked by Pre-run Validation, prepared by the existing executor's planning
sequence (prepare_campaign_specimens, prepare_run_manifest — the same function as the M7 CLI) and written as a run
manifest and plan into an empty working directory outside the repository and data stores.  Execution is refused by
its entry point before any executor, extraction, run journal or LM; forbidding fake executors make any unexpected
attempt fail the test.  No Abaqus, Abaqus Python, FE or LM.
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))

from domain.campaign_definition import load_campaign_definition  # noqa: E402
from domain.experiment_fixture import FixtureSourceMismatchError, fixture_roots_from_environment  # noqa: E402
from domain.identification_run import canonical_hash  # noqa: E402
from services import campaign_execution_plan as plan_module  # noqa: E402
from services import identification_campaign_run as campaign_module  # noqa: E402
from services.auto_id_wizard import load_fixtures  # noqa: E402
from services.campaign_draft import bind_draft_observations  # noqa: E402
from services.campaign_execution_plan import (  # noqa: E402
    NOT_AUTHORISED,
    PLAN_SCHEMA,
    ExecutionNotAuthorised,
    ExecutionPlanError,
    check_work_directory,
    plan_problems,
    prepare_execution_plan,
    request_execution,
)
from services.campaign_finalisation import export_campaign_definition, finalise_campaign  # noqa: E402
from services.prerun_validation import SECTIONS, PrerunValidation  # noqa: E402
import test_m8_d2g_campaign_finalisation as d2g  # noqa: E402

M7_RUN_A_MANIFEST = "e4ba607f06a69311b4d7adab089b5b8fdbbf98aae9d2da0837849e6c5da5bde6"
NEVER = ("PASS", "PASSED", "IDENTIFIED", "RELEASED", "AUTHORISED", "EXECUTED", "ACCEPTED_CALIBRATION", "READY")
EXECUTION_TARGETS = ((campaign_module, "CampaignRun"), (campaign_module, "extract_archived_odbs"),
                     (campaign_module, "run_bounded_lm"), (campaign_module, "RunJournal"),
                     (campaign_module, "journalled_archive_records"), (campaign_module, "IdentificationPipeline"))


@contextlib.contextmanager
def forbid_execution():
    """Forbidding fake executors: any solve, extraction, run journal, LM or process fails the test."""

    import subprocess

    from services import forward_solver, shape_extraction

    def refuse(*args, **kwargs):
        raise AssertionError("an execution path was reached without an authorisation")

    with contextlib.ExitStack() as stack:
        for owner, name in EXECUTION_TARGETS:
            stack.enter_context(mock.patch.object(owner, name, side_effect=refuse))
        for owner, name in ((forward_solver, "subprocess_executor"), (shape_extraction, "pinned_script_executor"),
                            (shape_extraction, "extract_shape_pack"), (subprocess, "run"), (subprocess, "Popen")):
            stack.enter_context(mock.patch.object(owner, name, side_effect=refuse))
        yield


def fake_manifest(definition, sources=("archived-validated-pack", "archived-odb-extraction", "archived-validated-pack"),
                  new_points=()):
    """A run manifest of the prepare_run_manifest shape (used where the real stores are not needed)."""

    points = ("p0", "E_in_plane_mpa+", "E_in_plane_mpa-")
    initial, extraction = [], []
    for spec in definition.specimens:
        for point, source in zip(points, sources):
            job = f"{spec.label}_{hashlib.sha256((spec.label + point).encode()).hexdigest()[:16]}"
            initial.append({"specimen": spec.label, "point": point, "parameters": {"E_in_plane_mpa": 52000.0},
                            "job_name": job, "generated_inp_sha256": "0" * 64, "source": source})
            if source == "archived-odb-extraction":
                extraction.append({"specimen": spec.label, "point": point, "job_name": job,
                                   "odb": {"store": "archive", "relative_path": f"runs/{job}.odb", "sha256": "a" * 64,
                                           "size_bytes": 1}})
    lm = definition.lm.evaluation_budget
    return {"schema": campaign_module.CAMPAIGN_MANIFEST_SCHEMA, "campaign_id": definition.campaign_id,
            "campaign_hash": definition.campaign_hash, "archive_reuse_hash": "b" * 64,
            "specimens": [{"label": s.label, "registration_hash": "c" * 64, "observation_hash": "d" * 64,
                           "rows": [{"row_id": r.row_id, "experimental_mode": r.experimental_mode, "fe_mode": r.fe_mode,
                                     "role": r.role} for r in s.rows]} for s in definition.specimens],
            "initial_points": initial, "extraction_only_jobs": extraction, "new_solve_initial_points": list(new_points),
            "budgets": {"max_new_abaqus_solves": definition.abaqus_solve_budget,
                        "max_new_solve_extractions": definition.abaqus_solve_budget,
                        "archive_extractions": len(extraction),
                        "max_abaqus_python_extractions": definition.abaqus_solve_budget + len(extraction),
                        "lm_evaluation_budget": lm, "reused_initial_evaluations": len(points),
                        "max_new_campaign_evaluations": lm - len(points)}}


def tree(folder: Path) -> dict:
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(folder).rglob("*")) if p.is_file()}


class _Planning(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = load_fixtures(ROOT)
        cls._exports = tempfile.TemporaryDirectory(prefix="m8_d2h_exports_")
        cls.exports = Path(cls._exports.name)
        cls.draft = d2g.complete_draft(ROOT, cls.fixtures, decision="SUPERVISOR M8-D2h test decision")
        finalised = finalise_campaign(cls.draft, ROOT, cls.fixtures)
        cls.definition_path = export_campaign_definition(cls.draft, cls.exports / "sp02_sp13.campaign.json", ROOT,
                                                         cls.fixtures, (ROOT,), finalised.campaign_hash).path
        cls.definition = load_campaign_definition(cls.definition_path)

    @classmethod
    def tearDownClass(cls):
        cls._exports.cleanup()

    def work(self) -> Path:
        folder = Path(tempfile.mkdtemp(prefix="m8_d2h_work_"))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        return folder

    def copy_definition(self, change=None) -> Path:
        folder = self.work()
        data = json.loads(self.definition_path.read_text(encoding="utf-8"))
        if change is not None:
            change(data)
        target = folder / "definition.campaign.json"
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return target


# ----------------------------------------------------------------------------- without data stores (fake planning)

def passing_prerun(path, definition) -> PrerunValidation:
    sections = dict(zip(SECTIONS, ("FORMALLY_VALID", "SHA256_VERIFIED", "COUNT_CONDITIONS_MET", "NOT_ASSESSED",
                                   "NOT_EVALUATED", "NOT_AUTHORISED")))
    return PrerunValidation(str(path), tuple((s, "x", "y", v) for s, v in sections.items()), sections,
                            definition.campaign_hash)


class _FakePlan(_Planning):
    """The plan service around a fake planning sequence (Pre-run passed; the stores are not needed)."""

    def plan(self, path=None, work=None, manifest=None, during=None):
        path = path or self.definition_path
        definition = load_campaign_definition(path)
        work = work or self.work()
        manifest = manifest or fake_manifest(definition)

        def planning(definition, repo_root, fixtures, roots, jobs_directory, verify_odbs=True):
            Path(jobs_directory, "SP02").mkdir(parents=True)
            Path(jobs_directory, "SP02", "job.inp").write_text("*HEADING\n", encoding="utf-8")
            if during is not None:
                during()
            return None, (), manifest, canonical_hash(manifest)

        with mock.patch.object(plan_module, "prerun_validation", return_value=passing_prerun(path, definition)), \
                mock.patch.object(plan_module, "prepare_campaign_plan", side_effect=planning), forbid_execution():
            return prepare_execution_plan(path, work, ROOT, self.fixtures, {"store": ROOT}, (ROOT,))


class FakePlanningTests(_FakePlan):
    def test_plan_files_and_rows(self):
        work = self.work()
        plan = self.plan(work=work)
        self.assertEqual(sorted(p.name for p in work.iterdir()), ["execution_plan.json", "plan_jobs",
                                                                  "run_manifest.json"])
        self.assertEqual(canonical_hash(json.loads((work / "run_manifest.json").read_text(encoding="utf-8"))),
                         plan.manifest_hash)
        record = json.loads((work / "execution_plan.json").read_text(encoding="utf-8"))
        self.assertEqual(record["schema"], PLAN_SCHEMA)
        self.assertEqual(record["execution_status"], NOT_AUTHORISED)
        self.assertIn("AUTHORISES_NOTHING", record["labels"])
        self.assertIn("NOT_GOVERNED_EVIDENCE", record["labels"])
        self.assertEqual(record["authorisation_scope_hash"], plan.authorisation_scope_hash)
        self.assertEqual(record["numerical_identifiability"], "NOT_ASSESSED")
        self.assertEqual(plan.execution_status, NOT_AUTHORISED)
        statuses = {row[3] for row in plan.rows}
        self.assertTrue({"ARCHIVED_SHAPE_PACK_READY", "ARCHIVED_ODB_NEEDS_EXTRACTION", "REQUIRES_HUMAN_GATE",
                         NOT_AUTHORISED, "NOT_ASSESSED"} <= statuses)
        for row in plan.rows:
            self.assertNotIn(row[3], NEVER)
        self.assertEqual([g["gate"] for g in plan.gates], ["ARCHIVE_EXTRACTION", "CAMPAIGN_RUN"])
        self.assertTrue(all(g["status"] == NOT_AUTHORISED for g in plan.gates))
        self.assertEqual(plan_problems(plan), [])
        self.assertEqual(plan.operations["fit_rows"], 3)
        self.assertEqual(plan.operations["holdout_rows"], 2)

    def test_the_scope_binds_campaign_manifest_operations_and_budget(self):
        plan = self.plan()
        scope = plan.authorisation_scope
        self.assertEqual(scope["campaign_hash"], plan.campaign_hash)
        self.assertEqual(scope["manifest_hash"], plan.manifest_hash)
        self.assertEqual(scope["definition_file_sha256"],
                         hashlib.sha256(self.definition_path.read_bytes()).hexdigest())
        self.assertEqual(scope["operations"]["max_new_abaqus_solves"], self.definition.abaqus_solve_budget)
        self.assertEqual(scope["operations"]["lm_evaluation_budget"], self.definition.lm.evaluation_budget)
        other = fake_manifest(self.definition, sources=("archived-validated-pack",) * 3)
        self.assertNotEqual(self.plan(manifest=other).authorisation_scope_hash, plan.authorisation_scope_hash)

    def test_cross_checks_refuse_a_plan_that_differs_from_the_definition(self):
        manifest = fake_manifest(self.definition)
        manifest["specimens"][0]["rows"][2]["role"] = "FIT"  # a HOLDOUT promoted by the planning
        work = self.work()
        with self.assertRaisesRegex(ExecutionPlanError, "does not match the definition"):
            self.plan(work=work, manifest=manifest)
        self.assertEqual(list(work.iterdir()), [])  # nothing published, no staging left
        manifest = fake_manifest(self.definition)
        manifest["budgets"]["max_new_campaign_evaluations"] = -1
        with self.assertRaisesRegex(ExecutionPlanError, "LM evaluation budget"):
            self.plan(manifest=manifest)

    def test_definition_changed_while_planning_writes_nothing(self):
        path = self.copy_definition()
        work = self.work()
        with self.assertRaisesRegex(ExecutionPlanError, "changed while the plan was prepared"):
            self.plan(path=path, work=work, during=lambda: path.write_text(path.read_text(encoding="utf-8") + " ",
                                                                          encoding="utf-8"))
        self.assertEqual(list(work.iterdir()), [])

    def test_definition_changed_after_the_plan_is_stale_and_refused(self):
        path = self.copy_definition()
        work = self.work()
        plan = self.plan(path=path, work=work)
        self.assertEqual(plan_problems(plan), [])
        data = json.loads(path.read_text(encoding="utf-8"))
        data["decision"] = "changed after the plan"
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.assertIn("the campaign definition file changed after the plan was prepared", plan_problems(plan))
        with forbid_execution(), self.assertRaisesRegex(ExecutionNotAuthorised, "changed after the plan"):
            request_execution(plan)
        changed = load_campaign_definition(path)
        with self.assertRaisesRegex(ExecutionPlanError, "another campaign"):
            check_work_directory(work, (ROOT,), changed.campaign_hash)  # never mixed with the earlier plan
        (work / "run_manifest.json").write_text("{}", encoding="utf-8")
        self.assertIn("the run manifest in the working directory changed", plan_problems(plan))

    def test_replanning_the_same_campaign_in_its_directory(self):
        work = self.work()
        first = self.plan(work=work)
        before = tree(work)
        second = self.plan(work=work)
        self.assertEqual(second.manifest_hash, first.manifest_hash)
        self.assertEqual(tree(work), before)

    def test_working_directory_rules(self):
        definition_hash = self.definition.campaign_hash
        with self.assertRaisesRegex(ExecutionPlanError, "no working directory"):
            check_work_directory("", (ROOT,), definition_hash)
        with self.assertRaisesRegex(ExecutionPlanError, "does not exist"):
            check_work_directory(self.work() / "missing", (ROOT,), definition_hash)
        for inside in (ROOT / "docs", ROOT.parent):
            with self.subTest(folder=inside), self.assertRaisesRegex(ExecutionPlanError, "inside or above"):
                check_work_directory(inside, (ROOT,), definition_hash)
        store = self.work()
        with self.assertRaisesRegex(ExecutionPlanError, "inside or above"):
            check_work_directory(store, (ROOT, store), definition_hash)
        with self.assertRaisesRegex(ExecutionPlanError, "protected root could not be determined"):
            check_work_directory(self.work(), (None,), definition_hash)
        models = self.work()  # a folder of user files (for example external_models copies)
        (models / "SP02.inp").write_text("*HEADING\n", encoding="utf-8")
        with self.assertRaisesRegex(ExecutionPlanError, "not empty and holds no execution plan"):
            check_work_directory(models, (ROOT,), definition_hash)
        work = self.work()
        with self.assertRaisesRegex(ExecutionPlanError, "not empty"):
            self.plan(work=models)
        self.assertEqual([p.name for p in models.iterdir()], ["SP02.inp"])
        self.assertEqual(check_work_directory(work, (ROOT,), definition_hash), work.resolve())

    def test_prerun_refusals_stop_before_planning(self):
        for sections, reason in ((("INVALID", "NOT_EVALUATED"), "Definition INVALID"),
                                 (("HISTORICAL_V1_SCHEMA", "NOT_EVALUATED"), "archived M7 campaigns"),
                                 (("FORMALLY_VALID", "MISMATCH"), "Sources MISMATCH"),
                                 (("FORMALLY_VALID", "NOT_VERIFIED"), "Sources NOT_VERIFIED")):
            with self.subTest(sections=sections):
                values = dict(zip(SECTIONS, sections + ("NOT_EVALUATED",) * 3 + ("NOT_AUTHORISED",)))
                prerun = PrerunValidation(str(self.definition_path), (), values, self.definition.campaign_hash)
                work = self.work()
                with mock.patch.object(plan_module, "prerun_validation", return_value=prerun), \
                        mock.patch.object(plan_module, "prepare_campaign_plan",
                                          side_effect=AssertionError("planned after a Pre-run refusal")), \
                        forbid_execution(), self.assertRaisesRegex(ExecutionPlanError, reason):
                    prepare_execution_plan(self.definition_path, work, ROOT, self.fixtures, {}, (ROOT,))
                self.assertEqual(list(work.iterdir()), [])

    def test_m7_campaign_is_never_planned_here(self):
        work = self.work()
        with forbid_execution(), self.assertRaisesRegex(ExecutionPlanError, "HISTORICAL_V1_SCHEMA"):
            prepare_execution_plan(ROOT / "docs/auto_id/campaigns/M7_RUN_A.campaign.json", work, ROOT, self.fixtures,
                                   None, (ROOT,))
        self.assertEqual(list(work.iterdir()), [])

    def gated(self, change):
        """The real planning sequence behind a passed Pre-run: its own gate refuses before any preparation."""
        path = self.copy_definition(change)
        definition = load_campaign_definition(path)
        work = self.work()
        with mock.patch.object(plan_module, "prerun_validation", return_value=passing_prerun(path, definition)), \
                mock.patch.object(campaign_module, "prepare_campaign_specimens",
                                  side_effect=AssertionError("prepared despite the gate")), forbid_execution():
            try:
                prepare_execution_plan(path, work, ROOT, self.fixtures, {}, (ROOT,))
            finally:
                self.assertEqual(list(work.iterdir()), [])

    def test_run_b_without_its_own_gate_is_refused(self):
        def run_b(data):
            data.update(run_type="RUN_B", fitted_parameters=["E_in_plane_mpa", "G12_mpa"], fixed_parameters={},
                        start={**data["start"], "G12_mpa": 4500.0},
                        bounds={**data["bounds"], "G12_mpa": [2250.0, 9000.0]},
                        engineering_plausibility={**data["engineering_plausibility"], "G12_mpa": [3000.0, 6000.0]})

        with self.assertRaisesRegex(ExecutionPlanError, "run-type gate.*RUN_B"):
            self.gated(run_b)

    def test_specimen_engineering_calibration_is_blocked(self):
        def calibration(data):
            data.update(scientific_question=d2g.CALIBRATION, specimens=data["specimens"][:1])

        with self.assertRaisesRegex(ExecutionPlanError, "BLOCKED"):
            self.gated(calibration)


class ExecutionEntryTests(_FakePlan):
    def test_no_value_is_an_authorisation(self):
        plan = self.plan()
        before = tree(plan.work_directory)
        for authorisation in (None, plan.manifest_hash, plan.campaign_hash, plan.authorisation_scope_hash,
                              M7_RUN_A_MANIFEST, "AUTHORISED by SUPERVISOR: run it now",
                              {"decision": "SUPERVISOR authorised", "provenance": ["HUMAN gate"],
                               "manifest_hash": plan.manifest_hash}, True):
            with self.subTest(authorisation=authorisation), forbid_execution():
                with self.assertRaisesRegex(ExecutionNotAuthorised, "NOT_AUTHORISED.*Nothing executed"):
                    request_execution(plan, authorisation)
        with forbid_execution(), self.assertRaisesRegex(ExecutionNotAuthorised, "no execution plan"):
            request_execution(None)
        self.assertEqual(tree(plan.work_directory), before)  # no journal, no extraction, no job written

    def test_refusal_is_not_a_value_error(self):
        self.assertFalse(issubclass(ExecutionNotAuthorised, ValueError))

    def test_gui_prepares_the_plan_and_refuses_execution(self):
        import material_identification_ui as ui
        import test_m8_d1_campaign_draft as d1

        application = d1.GuiTests.application(self)
        buttons = d1.GuiTests.buttons(application)
        for label in (ui.AUTO_ID_PLAN_LABEL, ui.AUTO_ID_START_LABEL):
            self.assertIn(label, buttons)
        self.assertIn("Execution status: NOT_AUTHORISED (no execution plan)",
                      application.material_auto_id_execution_label.kwargs["text"])
        with forbid_execution():
            buttons[ui.AUTO_ID_START_LABEL]()
        self.assertIn("no execution plan prepared", application.material_auto_id_execution_label.kwargs["text"])
        with mock.patch.object(ui.filedialog, "askopenfilename", return_value=""):
            ui.prepare_auto_id_execution_plan(application)
        self.assertIn("cancelled", application.material_auto_id_plan_label.kwargs["text"])
        with mock.patch.object(ui.filedialog, "askdirectory", return_value=""):
            ui.prepare_auto_id_execution_plan(application, path=str(self.definition_path))
        self.assertIn("no working directory", application.material_auto_id_plan_label.kwargs["text"])
        work = self.work()
        manifest = fake_manifest(self.definition)
        definition = self.definition

        def planning(definition_, repo_root, fixtures, roots, jobs_directory, verify_odbs=True):
            Path(jobs_directory).mkdir(parents=True)
            return None, (), manifest, canonical_hash(manifest)

        with mock.patch.object(plan_module, "prerun_validation",
                               return_value=passing_prerun(self.definition_path, definition)), \
                mock.patch.object(plan_module, "prepare_campaign_plan", side_effect=planning), forbid_execution():
            plan = ui.prepare_auto_id_execution_plan(application, path=str(self.definition_path),
                                                     work_directory=str(work))
        self.assertIsNotNone(plan)
        self.assertIn(plan.manifest_hash, application.material_auto_id_plan_label.kwargs["text"])
        self.assertIn(f"manifest hash {plan.manifest_hash}", application.material_auto_id_execution_label.kwargs["text"])
        self.assertIn("plan current", application.material_auto_id_execution_label.kwargs["text"])
        rows = list(application.material_auto_id_plan_table.items.values())
        self.assertIn(("Execution", "Execution status"), {(r[0], r[1]) for r in rows})
        before = tree(work)
        with forbid_execution():
            buttons[ui.AUTO_ID_START_LABEL]()
            ui.request_auto_id_execution(application, plan.manifest_hash)
            ui.request_auto_id_execution(application, "AUTHORISED (SUPERVISOR decision text)")
        self.assertIn("Nothing executed", application.material_auto_id_execution_label.kwargs["text"])
        self.assertIn("Execution status: NOT_AUTHORISED", application.material_auto_id_execution_label.kwargs["text"])
        self.assertEqual(tree(work), before)
        ui.prepare_auto_id_execution_plan(application, path=str(ROOT / "docs/auto_id/campaigns/M7_RUN_A.campaign.json"),
                                          work_directory=str(self.work()))
        self.assertIn("No execution plan", application.material_auto_id_plan_label.kwargs["text"])
        self.assertIsNone(application.auto_id_execution_plan)


class GuardTests(unittest.TestCase):
    SERVICE = ROOT / "src/services/campaign_execution_plan.py"

    def test_one_planning_sequence_for_cli_and_gui(self):
        import auto_id_execution_plan as plan_tool
        import m7_campaign

        self.assertIs(plan_module.prepare_campaign_plan, campaign_module.prepare_campaign_plan)
        self.assertIs(m7_campaign.prepare_campaign_plan, campaign_module.prepare_campaign_plan)
        self.assertIs(plan_tool.prepare_execution_plan, plan_module.prepare_execution_plan)
        tree_ = ast.parse(Path(campaign_module.__file__).read_text(encoding="utf-8"))
        function = next(n for n in tree_.body if isinstance(n, ast.FunctionDef) and n.name == "prepare_campaign_plan")
        called = {n.func.id for n in ast.walk(function) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertTrue({"load_archive_reuse", "prepare_campaign_specimens", "prepare_run_manifest"} <= called)

    def test_the_plan_service_reaches_no_execution_path(self):
        text = self.SERVICE.read_text(encoding="utf-8")
        tree_ = ast.parse(text)
        imported = {alias.name for node in ast.walk(tree_) if isinstance(node, (ast.Import, ast.ImportFrom))
                    for alias in node.names}
        modules = {node.module for node in ast.walk(tree_) if isinstance(node, ast.ImportFrom) and node.module}
        for forbidden in ("CampaignRun", "CampaignRunConfig", "extract_archived_odbs", "run_bounded_lm", "RunJournal",
                          "subprocess_executor", "pinned_script_executor", "IdentificationPipeline",
                          "journalled_archive_records", "require_executable"):
            self.assertNotIn(forbidden, imported)
        self.assertFalse(any(m.endswith(("subprocess", "forward_solver", "shape_extraction", "abaqus_bridge"))
                             for m in modules))
        self.assertNotIn("require_executable", {n.attr for n in ast.walk(tree_) if isinstance(n, ast.Attribute)})
        tool = (ROOT / "tools/auto_id_execution_plan.py").read_text(encoding="utf-8")
        for token in ("subprocess", "CampaignRun", "extract_archived_odbs", "--abaqus", "authorised"):
            self.assertNotIn(token, tool)

    def test_evaluate_stored_run_and_progress_are_unchanged(self):
        import subprocess

        changed = subprocess.run(["git", "diff", "--name-only", "85b66872147549eeb949d2338e197362441d8155", "--",
                                  "src/services/stored_run_evidence.py", "src/services/run_progress.py",
                                  "src/services/campaign_scientific_backend.py",
                                  "src/services/campaign_lm_provenance.py"],
                                 cwd=ROOT, capture_output=True, text=True)
        if changed.returncode:
            self.skipTest("git history not available")
        self.assertEqual(changed.stdout.strip(), "")


# ----------------------------------------------------------------------------- real stores (SP-02 + SP-13; no Abaqus)

def _roots():
    try:
        return dict(fixture_roots_from_environment())
    except Exception:  # noqa: BLE001
        return {}


def _stat_snapshot(paths) -> dict:
    return {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in paths if p.is_file()}


class RealPlanTests(_Planning):
    @classmethod
    def setUpClass(cls):
        cls.roots = _roots()
        missing = sorted({"snadwich", "carbon-project-archive"} - set(cls.roots))
        if missing:
            raise unittest.SkipTest(f"data stores {missing} not configured")
        super().setUpClass()
        cls._work = tempfile.TemporaryDirectory(prefix="m8_d2h_real_")
        cls.work_root = Path(cls._work.name)
        cls.protected = (ROOT, *cls.roots.values())
        archive = Path(cls.roots["carbon-project-archive"])
        cls.originals = [archive / "carbon5a/runs/E_PLUS_SP02/SP02_13363f977809dbff.odb",
                         archive / "carbon5a/runs/E_MINUS_SP02_retry1/SP02_84753f636064e192.odb"]
        cls.originals += [p for name in ("m7-run-a", "m7-run-b") if name in cls.roots
                          for p in Path(cls.roots[name]).glob("campaign/*/journal.json")]
        cls.before = _stat_snapshot(cls.originals)
        cls.docs_before = tree(ROOT / "docs")
        with forbid_execution():
            cls.plan = prepare_execution_plan(cls.definition_path, cls.fresh(), ROOT, cls.fixtures, cls.roots,
                                              cls.protected)

    @classmethod
    def fresh(cls) -> Path:
        folder = Path(tempfile.mkdtemp(dir=cls.work_root))
        return folder

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "_work"):
            cls._work.cleanup()
        super().tearDownClass()

    def test_real_plan_of_sp02_plus_sp13(self):
        plan, manifest = self.plan, self.plan.manifest
        self.assertEqual(plan.campaign_hash, self.definition.campaign_hash)
        self.assertNotEqual(plan.manifest_hash, M7_RUN_A_MANIFEST)  # a new campaign, never the archived M7 plan
        self.assertEqual(manifest["campaign_hash"], self.definition.campaign_hash)
        self.assertEqual(dict(plan.prerun.sections), dict(zip(SECTIONS, (
            "FORMALLY_VALID", "SHA256_VERIFIED", "COUNT_CONDITIONS_MET", "NOT_ASSESSED", "NOT_EVALUATED",
            "NOT_AUTHORISED"))))
        sources = {(p["specimen"], p["point"]): p["source"] for p in manifest["initial_points"]}
        self.assertEqual(sources, {("SP02", "p0"): "archived-validated-pack",
                                   ("SP02", "E_in_plane_mpa+"): "archived-odb-extraction",
                                   ("SP02", "E_in_plane_mpa-"): "archived-odb-extraction",
                                   ("SP13", "p0"): "archived-validated-pack",
                                   ("SP13", "E_in_plane_mpa+"): "archived-validated-pack",
                                   ("SP13", "E_in_plane_mpa-"): "archived-validated-pack"})
        self.assertEqual(manifest["budgets"], {"max_new_abaqus_solves": 16, "max_new_solve_extractions": 16,
                                               "archive_extractions": 2, "max_abaqus_python_extractions": 18,
                                               "lm_evaluation_budget": 11, "reused_initial_evaluations": 3,
                                               "max_new_campaign_evaluations": 8})
        self.assertEqual(plan.operations["new_initial_point_solves"], 0)
        self.assertEqual(plan.operations["solves_the_lm_budget_could_need"], 16)
        self.assertEqual([g["gate"] for g in plan.gates], ["ARCHIVE_EXTRACTION", "CAMPAIGN_RUN"])
        for row in plan.rows:
            self.assertNotIn(row[3], NEVER)

    def test_prepared_rows_equal_the_frozen_records(self):
        draft, outcomes = bind_draft_observations(self.draft, ROOT, self.fixtures)  # bound again, now
        self.assertEqual({o.status for o in outcomes}, {"BOUND"})
        self.assertEqual([item["label"] for item in self.plan.manifest["specimens"]], ["SP02", "SP13"])
        for item in self.plan.manifest["specimens"]:
            spec = next(s for s in draft.specimens if s.label == item["label"])
            frozen = [(r.row_id, r.experimental_mode, r.fe_mode, r.role)
                      for r in draft.specimen_observations(spec.forward_model).rows]
            prepared = [(r["row_id"], r["experimental_mode"], r["fe_mode"], r["role"]) for r in item["rows"]]
            self.assertEqual(prepared, frozen, item["label"])
        self.assertEqual((self.plan.operations["fit_rows"], self.plan.operations["holdout_rows"]), (3, 2))

    def test_plan_and_manifest_hash_are_reproducible(self):
        with forbid_execution():
            again = prepare_execution_plan(self.definition_path, self.fresh(), ROOT, self.fixtures, self.roots,
                                           self.protected)
            direct = campaign_module.prepare_campaign_plan(self.definition, ROOT, self.fixtures, self.roots,
                                                           self.fresh() / "jobs")
        self.assertEqual(again.manifest_hash, self.plan.manifest_hash)
        self.assertEqual(direct[3], self.plan.manifest_hash)  # the plan is exactly the existing backend's manifest
        self.assertEqual(again.authorisation_scope_hash, self.plan.authorisation_scope_hash)
        self.assertEqual(again.manifest_path.read_bytes(), self.plan.manifest_path.read_bytes())
        self.assertEqual(tree(again.work_directory / "plan_jobs"), tree(self.plan.work_directory / "plan_jobs"))

    def test_an_archived_odb_with_another_sha256_is_refused(self):
        real = campaign_module.sha256_file
        work = self.fresh()

        def altered(path):
            return "0" * 64 if Path(path).suffix == ".odb" else real(path)

        with mock.patch.object(campaign_module, "sha256_file", side_effect=altered), forbid_execution():
            with self.assertRaisesRegex(ExecutionPlanError, "differs from its pin"):
                prepare_execution_plan(self.definition_path, work, ROOT, self.fixtures, self.roots, self.protected)
        self.assertEqual(list(work.iterdir()), [])

    def test_a_source_with_another_sha256_is_refused(self):
        from services import prerun_validation as prerun_module

        work = self.fresh()
        with mock.patch.object(prerun_module, "resolve_external_file",
                               side_effect=FixtureSourceMismatchError("altered copy")), forbid_execution():
            with self.assertRaisesRegex(ExecutionPlanError, "Sources MISMATCH.*altered copy"):
                prepare_execution_plan(self.definition_path, work, ROOT, self.fixtures, self.roots, self.protected)
        self.assertEqual(list(work.iterdir()), [])

    def test_missing_archived_data_is_refused(self):
        roots = dict(self.roots, **{"carbon-project-archive": self.fresh()})
        work = self.fresh()
        with forbid_execution(), self.assertRaisesRegex(ExecutionPlanError, "Sources MISMATCH"):
            prepare_execution_plan(self.definition_path, work, ROOT, self.fixtures, roots, self.protected)
        roots = {k: v for k, v in self.roots.items() if k != "carbon-project-archive"}
        with forbid_execution(), self.assertRaisesRegex(ExecutionPlanError, "Sources NOT_VERIFIED"):
            prepare_execution_plan(self.definition_path, work, ROOT, self.fixtures, roots, self.protected)
        self.assertEqual(list(work.iterdir()), [])

    def test_a_wrong_archive_reuse_plan_is_refused(self):
        repository = Path(tempfile.mkdtemp(dir=self.work_root))
        shutil.copytree(ROOT / "docs", repository / "docs")
        plan_path = repository / "docs/auto_id/campaigns/M7_RUN_A.archive-reuse.json"
        data = json.loads(plan_path.read_text(encoding="utf-8"))
        data["odbs"] = [o for o in data["odbs"] if o["job_name"] != "SP02_13363f977809dbff"]  # E+ of SP-02 dropped
        plan_path.write_text(json.dumps(data, indent=1), encoding="utf-8")
        work = self.fresh()
        with forbid_execution(), self.assertRaisesRegex(ExecutionPlanError, "need new solves"):
            prepare_execution_plan(self.definition_path, work, repository, load_fixtures(repository), self.roots,
                                   (repository, *self.roots.values()))
        self.assertEqual(list(work.iterdir()), [])

    def test_zz_originals_and_accepted_journals_are_unchanged(self):  # last: after every plan of this class
        self.assertEqual(_stat_snapshot(self.originals), self.before)
        self.assertEqual(tree(ROOT / "docs"), self.docs_before)
        for path in self.originals:
            self.assertFalse(str(path.resolve()).startswith(str(self.work_root.resolve())))


if __name__ == "__main__":
    unittest.main()
