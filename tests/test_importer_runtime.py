"""NEW-GUI.2: one shared installation of the application's importer chain (services.importer_runtime).

``ensure_application_importers`` installs the five existing importer layers in the order of ``src/main.py``; the
existing program and the new interface both call it. These tests check, in fresh Python processes (``main`` cannot be
un-imported), that it gives the same function owners and the same previews as ``import main``, that it is idempotent
and refuses a foreign order, that it loads neither ``main`` nor Tkinter and writes nothing until a file is read, and
that the fast cache (in an isolated folder) changes nothing but its technical metadata. Synthetic temporary files only.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import abaqus_bridge  # noqa: E402
from services import importer_runtime  # noqa: E402
from services import local_fe_preview as fe_preview  # noqa: E402
import frf_unv_support as F  # noqa: E402
import synthetic_plate_support as S  # noqa: E402
from test_local_fe_preview import RIGID, described, write_package  # noqa: E402
from test_universal_hardening import write_2414_unv  # noqa: E402

ORDER = ("install_universal_hardening", "install_frf_review", "install_cmif_separation", "install_cmif_validation",
         "install_fast_cache")

# Run in a fresh process: install the importers one way, then print the function owners and a digest of every preview.
CHILD = r'''
import dataclasses, hashlib, json, sys, types
from pathlib import Path
src, mode, reads = sys.argv[1], sys.argv[2], int(sys.argv[3])
files = sys.argv[4:]
sys.path.insert(0, src)
if mode == "early-fe":  # the FE preview imported before the importers are installed
    from services import local_fe_preview
if mode == "main":
    import main
elif mode == "order":
    import fast_cache
    fast_cache.install_fast_cache()
    from services.importer_runtime import ensure_application_importers, installed_layers
    try:
        ensure_application_importers()
    except Exception as error:
        print(json.dumps({"error": type(error).__name__, "installed": list(installed_layers())}))
    raise SystemExit(0)
elif mode != "none":
    from services.importer_runtime import ensure_application_importers, installed_layers
    ensure_application_importers()
    ensure_application_importers()  # idempotent
import abaqus_bridge, universal_reader
owners = {f"{m.__name__}.{k}": f"{v.__module__}.{v.__qualname__}" for m in (universal_reader, abaqus_bridge)
          for k, v in vars(m).items() if isinstance(v, types.FunctionType)}
loaded = {name: name in sys.modules for name in ("main", "tkinter", "app")}
from services import local_experimental_preview as xp, local_fe_preview as fp

def plain(v):
    if dataclasses.is_dataclass(v):
        return {f.name: plain(getattr(v, f.name)) for f in dataclasses.fields(v) if f.compare}
    if isinstance(v, (list, tuple)):
        return [plain(x) for x in v]
    if isinstance(v, dict):
        return {str(k): plain(x) for k, x in v.items()}
    if isinstance(v, float):
        return repr(v)
    return v if isinstance(v, (int, str, bool, type(None))) else str(v)

TECH = ("unv_cache_reused", "binary_odb_cache_reused")
RUNTIME = {"unv_cache_reused", "unv_load_seconds", "unv_cache_write_failed", "binary_odb_cache_reused",
           "odb_dataset_load_seconds", "binary_odb_cache_write_failed"}  # the fast cache's technical metadata
previews = {}
for f in files:
    previews[f] = []
    for _ in range(reads):
        try:
            if f.endswith("manifest.json"):
                p = fp.preview_fe_package(f)
                datasets = [p.dataset]
            else:
                p = xp.preview_experimental_file(f)
                datasets = [s.dataset for s in p.sets]
        except Exception as error:
            previews[f].append({"error": str(error)})
            continue
        meta = [{k: v for k, v in (d.metadata or {}).items() if k not in RUNTIME} for d in datasets]
        body = {"preview": plain(p), "metadata": plain(meta)}
        previews[f].append({"digest": hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest(),
                            "tech": [next((d.metadata.get(k) for k in TECH if k in (d.metadata or {})), "absent")
                                     for d in datasets],
                            "records": [[(r.number, r.frequency_hz, r.classification, r.provisional) for r in s.records]
                                        for s in getattr(p, "sets", ())],
                            "modes": [(m.number, m.frequency_hz) for m in getattr(p, "modes", ())]})
print(json.dumps({"owners": owners, "loaded": loaded, "previews": previews,
                  "installed": list(__import__("services.importer_runtime").importer_runtime.installed_layers())}))
'''


def run_child(cache: Path, mode: str, files=(), reads: int = 1) -> dict:
    env = dict(os.environ, LOCALAPPDATA=str(cache), MPLBACKEND="Agg")
    done = subprocess.run([sys.executable, "-c", CHILD, str(ROOT / "src"), mode, str(reads), *map(str, files)],
                          capture_output=True, text=True, env=env, timeout=600)
    if done.returncode != 0:
        raise AssertionError(f"child process failed ({mode}):\n{done.stderr[-3000:]}")
    return json.loads(done.stdout.strip().splitlines()[-1])


def cache_files(cache: Path) -> list:
    return sorted(p.relative_to(cache).as_posix() for p in cache.rglob("*") if p.is_file())


class _Folder(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="importer_runtime_"))
        self.addCleanup(shutil.rmtree, self.folder, True)

    def cache(self, name: str) -> Path:
        path = self.folder / name
        path.mkdir()
        return path


class OrderTests(unittest.TestCase):
    def test_the_layers_are_the_existing_installs_in_the_application_order(self):
        self.assertEqual(importer_runtime.LAYER_NAMES, ORDER)
        for name, module, install in importer_runtime.IMPORTER_LAYERS:
            self.assertIs(getattr(module, name), install)  # the existing function, not a new layer

    def test_main_calls_the_shared_function_before_the_remaining_initialisation(self):
        source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
        calls = [node.value.func.id for node in ast.parse(source).body
                 if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                 and isinstance(node.value.func, ast.Name)]
        self.assertEqual(calls[:5], ["ensure_application_importers", "install_performance_tuning",
                                     "install_reporting_hardening", "install_amplitude_correlation",
                                     "install_metrics_normalization"])
        imported = [alias.name for node in ast.walk(ast.parse(source)) if isinstance(node, ast.ImportFrom)
                    for alias in node.names]
        self.assertEqual(set(ORDER) & set(imported + calls), set())  # installed only through the shared function
        self.assertEqual(calls.count("ensure_application_importers"), 1)

    def test_the_service_defines_no_new_layer(self):
        source = Path(importer_runtime.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        defined = [node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))]
        self.assertEqual(defined, ["ImporterOrderError", "installed_layers", "ensure_application_importers"])
        assigned = [target for node in ast.walk(tree) if isinstance(node, ast.Assign) for target in node.targets
                    if isinstance(target, ast.Attribute)]
        self.assertEqual(assigned, [])  # it replaces no module attribute itself


class ProcessTests(_Folder):
    def test_same_function_owners_as_import_main_without_main_or_tkinter_and_without_writing(self):
        shared_cache, main_cache = self.cache("shared"), self.cache("main")
        shared = run_child(shared_cache, "ensure")
        application = run_child(main_cache, "main")
        self.assertEqual(shared["owners"], application["owners"])
        self.assertEqual(shared["installed"], list(ORDER))
        self.assertEqual(application["installed"], list(ORDER))
        self.assertEqual(shared["owners"]["universal_reader.load_universal_modal_file"],
                         "fast_cache._cached_universal_loader")
        self.assertEqual(shared["owners"]["universal_reader._modes_from_frf_datasets"],
                         "cmif_validation._validated_modes_from_frf")
        self.assertEqual(shared["owners"]["abaqus_bridge.load_extracted_odb"],
                         "fast_cache._cached_extracted_odb_loader")
        self.assertEqual(shared["loaded"], {"main": False, "tkinter": False, "app": False})
        self.assertEqual(cache_files(shared_cache), [])  # installing creates no cache file
        bare = run_child(self.cache("bare"), "none")
        self.assertNotEqual(bare["owners"], shared["owners"])  # the chain does replace the base importer
        self.assertEqual(bare["installed"], [])

    def test_a_foreign_order_is_refused_and_nothing_more_is_installed(self):
        refused = run_child(self.cache("order"), "order")
        self.assertEqual(refused, {"error": "ImporterOrderError", "installed": ["install_fast_cache"]})

    def test_same_previews_as_import_main_and_from_memory_and_disk_cache(self):
        inputs = self.folder / "inputs"
        inputs.mkdir()
        frf = F.write_frf_only(inputs / "frf_only.uff")
        sets_55 = S.write_experiment(inputs / "two_sets.unv", S.E0, S.G0, sets=(("bravo", 4), ("processing", 6)))
        dataset_2414 = write_2414_unv(inputs / "records_2414.unv", [
            {"analysis_type": 2, "mode": 7, "frequency": 23.5, "label": 1},
            {"analysis_type": 3, "mode": 8, "frequency": 41.25, "label": 2},
            {"analysis_type": 5, "mode": 9, "frequency": 25.0, "label": 3, "name": "Frequency response"}])
        manifest = write_package(inputs / "package", [(n, f, None) for n, f in enumerate(RIGID, 1)]
                                 + [(7, 101.25, described(101.25))])
        files = [frf, sets_55, dataset_2414, manifest]
        before = {p: p.read_bytes() for p in inputs.rglob("*") if p.is_file()}

        shared_cache = self.cache("shared")
        first = run_child(shared_cache, "ensure", files, reads=2)  # first read, then from memory (UNV)
        written = cache_files(shared_cache)
        disk = run_child(shared_cache, "ensure", files, reads=1)  # a new process: from the disk cache
        application = run_child(self.cache("main"), "main", files, reads=1)
        uncached = run_child(self.cache("none"), "none", files, reads=1)

        for f in map(str, files):
            reference = application["previews"][f][0]
            for got in first["previews"][f] + disk["previews"][f]:
                self.assertEqual(got["digest"], reference["digest"], f)
                self.assertEqual((got["records"], got["modes"]), (reference["records"], reference["modes"]))
        unv = [str(frf), str(sets_55), str(dataset_2414)]
        for f in unv:  # only the technical cache metadata differ
            sets = len(first["previews"][f][0]["tech"])
            self.assertEqual(first["previews"][f][0]["tech"], [False] * sets)
            self.assertEqual(first["previews"][f][1]["tech"], ["memory"] * sets)
            self.assertEqual(disk["previews"][f][0]["tech"], ["disk"] * sets)
        self.assertEqual(uncached["previews"][str(frf)][0]["tech"], ["absent"])
        # without the chain the base importer does not read pyuff's positional dataset-2414 layout at all
        self.assertIn("No experimental modal vectors", uncached["previews"][str(dataset_2414)][0]["error"])
        self.assertEqual([p["tech"] for p in first["previews"][str(manifest)]], [[False], [True]])
        self.assertEqual(disk["previews"][str(manifest)][0]["tech"], [True])

        frf_records = application["previews"][str(frf)][0]["records"]
        self.assertTrue(frf_records[0])
        self.assertTrue(all(provisional for _, _, _, provisional in frf_records[0]))  # never a validated mode
        self.assertEqual(len(application["previews"][str(sets_55)][0]["records"]), 2)  # two sets, none merged
        self.assertEqual([m[0] for m in application["previews"][str(manifest)][0]["modes"]], list(range(1, 8)))

        self.assertEqual(sum(name.split("/")[-1].startswith("unv_") for name in written), 4)  # 1 + 2 sets + 1
        self.assertEqual(sum(name.split("/")[-1].startswith("odb_") for name in written), 1)
        self.assertTrue(all(name.startswith("AbaqusModalComparator/cache/") for name in written))
        self.assertEqual({p: p.read_bytes() for p in inputs.rglob("*") if p.is_file()}, before)  # inputs untouched

    def test_the_fe_preview_uses_the_cached_loader_even_when_imported_first(self):
        manifest = write_package(self.folder / "package", [(7, 101.25, described(101.25))])
        cache = self.cache("early")
        early = run_child(cache, "early-fe", [manifest], reads=2)
        self.assertEqual([p["tech"] for p in early["previews"][str(manifest)]], [[False], [True]])
        self.assertEqual(sum(name.endswith(".pkl.gz") for name in cache_files(cache)), 1)


class LateBindingTests(_Folder):
    def test_the_fe_preview_calls_the_loader_installed_at_read_time(self):
        manifest = write_package(self.folder / "package", [(7, 101.25, described(101.25))])
        real = abaqus_bridge.load_extracted_odb
        calls = []

        def installed_later(path, cancel_event=None):
            calls.append(Path(path))
            return real(path, cancel_event=cancel_event)

        with mock.patch.object(abaqus_bridge, "load_extracted_odb", installed_later):
            preview = fe_preview.preview_fe_package(manifest)
        self.assertEqual(calls, [manifest])
        self.assertEqual(preview.mode_numbers, [7])


if __name__ == "__main__":
    unittest.main()
