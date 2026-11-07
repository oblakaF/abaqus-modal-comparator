"""REAL-FIT.R4: static preparation of the two Abaqus S4R trial decks from the Ritz research minima."""

import asyncio
import contextlib
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

try:  # the Windows process-creation primitive under subprocess and multiprocessing
    import _winapi
except ImportError:  # pragma: no cover - not Windows
    _winapi = None
try:
    import _posixsubprocess
except ImportError:  # Windows
    _posixsubprocess = None

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from services import research_fe_trial_preflight as pf  # noqa: E402
from services import research_frequency_tuning as rft  # noqa: E402

A = {"E1": 59643.140320162354, "E2": 43592.56647783119, "G12": 4824.07010224442}
B = {"E1": 44170.77433673189, "E2": 58724.14887983508, "G12": 4817.417308245888}
COSTS = (0.0008452616410310549, 0.0008576605619306323)
ORIGINAL_POPEN = subprocess.Popen
# Process-launch entry points patched only for the duration of one preparation (absent names are skipped).
LAUNCH_ENTRY_POINTS = (
    [(subprocess, "Popen"), (asyncio, "create_subprocess_exec"), (asyncio, "create_subprocess_shell")]
    + [(os, n) for n in ("system", "popen", "startfile", "posix_spawn", "posix_spawnp", "fork", "forkpty",
                         "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe",
                         "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp", "execvpe")]
    + ([(_winapi, "CreateProcess")] if _winapi else [])
    + ([(_posixsubprocess, "fork_exec")] if _posixsubprocess else []))
ELASTIC = "*Elastic, type=ENGINEERING CONSTANTS\n56000.,56000., 8500.,  0.05,   0.3,   0.3, 5000., 3000.\n 3000.,\n"


def deck(elastic=ELASTIC, extra_material="", instance="        251.,         270.,           0.\n", flip=False) -> bytes:
    nodes, elements = [], []
    for j in range(3):
        for i in range(3):
            nodes.append(f"{j * 3 + i + 1:7d}, {-251.0 + 150.5 * i:12.6g}, {-270.0 + 150.0 * j:12.6g},           0.")
    for j in range(2):
        for i in range(2):
            n1 = j * 3 + i + 1
            order = (n1, n1 + 1, n1 + 4, n1 + 3) if not flip else (n1, n1 + 3, n1 + 4, n1 + 1)
            elements.append(f"{j * 2 + i + 1:5d}, " + ", ".join(f"{n:5d}" for n in order))
    text = ("*Heading\n CFRP test plate\n** Job name: test\n*Preprint, echo=NO, model=NO, history=NO, contact=NO\n**\n"
            "*Part, name=P\n*Node\n" + "\n".join(nodes) + "\n*Element, type=S4R\n" + "\n".join(elements) +
            "\n*Nset, nset=Set-1, generate\n 1, 9, 1\n*Elset, elset=Set-1, generate\n 1, 4, 1\n"
            "** Section: S\n*Shell Section, elset=Set-1, material=CFRP_T300_TEST\n0.875, 5\n*End Part\n"
            "*Assembly, name=Assembly\n*Instance, name=P-1, part=P\n" + instance + "*End Instance\n*End Assembly\n"
            "*Material, name=CFRP_T300_TEST\n*Density\n 1.498e-09,\n" + elastic + extra_material +
            "** STEP\n*Step, name=Modal, nlgeom=NO, perturbation\n*Frequency, eigensolver=Lanczos, normalization=mass\n"
            "20, , , , , \n*Output, field\n*Node Output\nU, \n*End Step\n")
    return text.replace("\n", "\r\n").encode("latin-1")


def export(inp_sha: str) -> dict:
    return {
        "schema": rft.SCHEMA, "status": rft.MIRROR, "label": rft.RESULT_LABEL,
        "request": {"parameterization": rft.FREE}, "inputs": {"inp_sha256": inp_sha}, "fitted": dict(A, nu12=0.05),
        "minima": [{"values": dict(A), "cost": COSTS[0]}, {"values": dict(B), "cost": COSTS[1]}],
        "axis_assignments": [
            {"assignment": "assignment A", "E1 (FE X)": A["E1"], "E2 (FE Y)": A["E2"], "G12": A["G12"], "cost": COSTS[0]},
            {"assignment": "assignment B", "E1 (FE X)": B["E1"], "E2 (FE Y)": B["E2"], "G12": B["G12"], "cost": COSTS[1]}],
        "sources": {},
    }


class Files:
    def __init__(self, data: bytes = None, document=None):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "src").mkdir()
        self.inp = root / "src" / "plate.inp"
        self.inp.write_bytes(data if data is not None else deck())
        self.export = root / "src" / "proposal_free.json"
        self.export.write_text(json.dumps(document if document is not None else export(pf.sha256_file(self.inp))), encoding="utf-8")
        self.out = root / "out"

    def close(self):
        self.tmp.cleanup()


class Transfer(unittest.TestCase):
    def setUp(self):
        self.files = Files()
        self.addCleanup(self.files.close)

    def test_both_minima_are_written_exactly(self):
        manifest = pf.prepare(self.files.export, self.files.inp, self.files.out)
        self.assertEqual(manifest["status"], "PREFLIGHT_PASSED")
        for record, values, name in zip(manifest["variants"], (A, B), ("M11_RITZ_MINIMUM_A.inp", "M11_RITZ_MINIMUM_B.inp")):
            path = self.files.out / name
            block = pf.elastic_block(pf._lines(path.read_bytes()))
            for key in pf.TARGETS:
                self.assertEqual(block.values[key], values[key])  # exact doubles, no rounding
            self.assertEqual(record["sha256"], pf.sha256_file(path))
            self.assertEqual(record["failed"], [])
        a, b = (self.files.out / n for _l, n in pf.VARIANTS)
        self.assertNotEqual(a.read_bytes(), b.read_bytes())

    def test_every_other_material_constant_is_kept(self):
        pf.prepare(self.files.export, self.files.inp, self.files.out)
        original = pf.elastic_block(pf._lines(self.files.inp.read_bytes())).values
        for _label, name in pf.VARIANTS:
            values = pf.elastic_block(pf._lines((self.files.out / name).read_bytes())).values
            for key in ("E3", "nu12", "nu13", "nu23", "G13", "G23"):
                self.assertEqual(values[key], original[key])
        lines = pf._lines((self.files.out / "M11_RITZ_MINIMUM_A.inp").read_bytes())
        idx = pf.elastic_block(lines).data_indexes
        self.assertEqual(pf._body(lines[idx[0]]),
                         "59643.140320162354,43592.56647783119, 8500.,  0.05,   0.3,   0.3, 4824.07010224442, 3000.")
        self.assertEqual(pf._body(lines[idx[1]]), " 3000.,")

    def test_model_structure_and_diff_are_limited_to_the_elastic_line(self):
        manifest = pf.prepare(self.files.export, self.files.inp, self.files.out)
        original = self.files.inp.read_bytes()
        for _label, name in pf.VARIANTS:
            variant = (self.files.out / name).read_bytes()
            self.assertEqual(pf.structure(original), pf.structure(variant))
            changed = [i for i, (x, y) in enumerate(zip(pf._lines(original), pf._lines(variant))) if x != y]
            self.assertEqual(len(changed), 1)
            self.assertIn(b"\r\n", variant)
        diff = manifest["variants"][0]["diff_against_original"]
        self.assertEqual(sum(1 for line in diff.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))), 2)
        axes = manifest["material_axes"]
        self.assertEqual(axes["status"], "ESTABLISHED_FROM_DECK_AND_ABAQUS_CONVENTION")
        self.assertEqual((axes["normals_plus_z"], axes["shell_elements"]), (4, 4))

    def test_sources_are_untouched_and_outputs_never_overwritten(self):
        before = {p: (pf.sha256_file(p), os.stat(p).st_mtime_ns) for p in (self.files.inp, self.files.export)}
        manifest = pf.prepare(self.files.export, self.files.inp, self.files.out)
        after = {p: (pf.sha256_file(p), os.stat(p).st_mtime_ns) for p in (self.files.inp, self.files.export)}
        self.assertEqual(before, after)
        self.assertTrue(manifest["sources_unchanged"])
        written = {n: (self.files.out / n).read_bytes() for _l, n in pf.VARIANTS}
        with self.assertRaises(pf.PreflightRefused):
            pf.prepare(self.files.export, self.files.inp, self.files.out)
        self.assertEqual(written, {n: (self.files.out / n).read_bytes() for _l, n in pf.VARIANTS})
        with self.assertRaises(pf.PreflightRefused):
            pf.prepare(self.files.export, self.files.inp, self.files.inp.parent)


class Refusals(unittest.TestCase):
    def _refused(self, document=None, data=None):
        files = Files(data, document)
        self.addCleanup(files.close)
        with self.assertRaises(pf.PreflightRefused):
            pf.prepare(files.export, files.inp, files.out)
        self.assertFalse(files.out.exists())

    def test_missing_or_ambiguous_minima_are_refused(self):
        sha = pf.sha256_bytes(deck())
        one = export(sha); one["minima"] = one["minima"][:1]
        three = export(sha); three["minima"].append(copy.deepcopy(three["minima"][1]))
        same = export(sha); same["minima"][1] = copy.deepcopy(same["minima"][0])
        same["axis_assignments"][1] = dict(same["axis_assignments"][0], assignment="assignment B")
        swapped = export(sha); swapped["minima"].reverse()
        mismatch = export(sha); mismatch["axis_assignments"][1]["G12"] = 4800.0
        missing = export(sha); del missing["minima"][1]["values"]["G12"]
        wrong_inp = export("0" * 64)
        unique = export(sha); unique["status"] = "DONE"
        tied = export(sha); tied["request"]["parameterization"] = rft.TIED
        for document in (one, three, same, swapped, mismatch, missing, wrong_inp, unique, tied):
            self._refused(document)

    def test_unsupported_material_definitions_are_refused(self):
        variants = [
            deck(elastic="*Elastic, type=LAMINA\n56000., 56000., 0.05, 5000., 3000., 3000.\n"),
            deck(elastic="*Elastic\n56000., 0.05\n"),
            deck(elastic="*Elastic, type=ENGINEERING CONSTANTS\n56000.,56000., 8500.,  0.05,   0.3,   0.3, 5000., 3000.\n 3000., 20.\n"),
            deck(elastic="*Elastic, type=ENGINEERING CONSTANTS, dependencies=1\n56000.,56000., 8500.,  0.05,   0.3,   0.3, 5000., 3000.\n 3000.,\n"),
            deck(extra_material="*Material, name=OTHER\n*Density\n 1e-09,\n"),
            deck(extra_material=ELASTIC),
            deck(elastic="*Elastic, type=ENGINEERING CONSTANTS\n-56000.,56000., 8500.,  0.05,   0.3,   0.3, 5000., 3000.\n 3000.,\n"),
        ]
        for data in variants:
            files = Files(data)
            self.addCleanup(files.close)
            with self.assertRaises(pf.PreflightRefused):
                pf.prepare(files.export, files.inp, files.out)
            self.assertFalse(files.out.exists())

    def test_unexpected_structural_changes_fail_the_checks(self):
        original = deck()
        good = pf.build_variant(original, A)
        self.assertEqual(pf._failed(pf.verify_variant(original, good, A)), [])
        tampered = [
            good.replace(b"0.875, 5", b"0.900, 5"),
            good.replace(b" 1.498e-09,", b" 1.500e-09,"),
            good.replace(b"20, , , , , ", b"30, , , , , "),
            good.replace(b"0.05,   0.3", b"0.06,   0.3"),
            good.replace(b"  -100.5", b"  -100.4"),
            good.replace(b"\r\n", b"\n"),
        ]
        for data in tampered:
            self.assertNotEqual(data, good)
            self.assertTrue(pf._failed(pf.verify_variant(original, data, A)))
        self.assertTrue(pf._failed(pf.verify_variant(original, pf.build_variant(original, B), A)))

    def test_axes_not_established_when_the_deck_rotates_or_orients(self):
        rotated = deck(instance="        251.,         270.,           0.\n 0., 0., 0., 0., 0., 1., 30.\n")
        self.assertEqual(pf.material_axes(rotated)["status"], "NOT_ESTABLISHED")
        oriented = deck(extra_material="*Orientation, name=Ori-1\n 1., 1., 0., -1., 1., 0.\n3, 0.\n")
        self.assertEqual(pf.material_axes(oriented)["status"], "NOT_ESTABLISHED")
        flipped = pf.material_axes(deck(flip=True))
        self.assertEqual((flipped["normals_minus_z"], flipped["status"]), (4, "ESTABLISHED_FROM_DECK_AND_ABAQUS_CONVENTION"))


@contextlib.contextmanager
def launch_guard():
    """Refuse every process-launch entry point for the duration of the block only; all are restored on exit."""
    calls = []
    with contextlib.ExitStack() as stack:
        for module, name in LAUNCH_ENTRY_POINTS:
            if hasattr(module, name):
                def refuse(*_args, _name=f"{module.__name__}.{name}", **_kwargs):
                    calls.append(_name)
                    raise AssertionError(f"{_name} called during preflight")
                stack.enter_context(mock.patch.object(module, name, refuse))
        yield calls


class NoAbaqus(unittest.TestCase):
    def test_preparation_cannot_launch_a_process(self):
        source = Path(pf.__file__).read_text(encoding="utf-8")
        for word in ("subprocess", "os.system", "Popen", "startfile", "spawn", "run_abaqus", "matrix_model_service"):
            self.assertNotIn(word, source)
        files = Files()
        self.addCleanup(files.close)
        with launch_guard() as calls:
            manifest = pf.prepare(files.export, files.inp, files.out)
        self.assertEqual(calls, [])
        self.assertEqual(manifest["abaqus"], "NOT_RUN")
        self.assertIn("NOT_RUN_IN_ABAQUS", manifest["label"])

    def test_the_guard_catches_a_launch_and_leaves_nothing_behind(self):
        originals = {(m.__name__, n): getattr(m, n) for m, n in LAUNCH_ENTRY_POINTS if hasattr(m, n)}
        with launch_guard() as calls:
            with self.assertRaises(AssertionError):
                subprocess.run([sys.executable, "-c", "pass"])  # refused before any process is created
            with self.assertRaises(AssertionError):
                os.system("exit 0")
        self.assertEqual(calls, ["subprocess.Popen", "os.system"])
        self.assertEqual(originals, {(m.__name__, n): getattr(m, n) for m, n in LAUNCH_ENTRY_POINTS if hasattr(m, n)})
        self.assertIs(subprocess.Popen, ORIGINAL_POPEN)

if __name__ == "__main__":
    unittest.main()
