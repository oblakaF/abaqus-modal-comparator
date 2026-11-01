"""PRIORITY-7: the SP-10 FE results of PRIORITY-6 in the new interface (service headless; the page in Qt ``offscreen``).

Service (``services.sp10_fe_research``):
- the archived records give FE7–FE25 (19 modes; FE7 23.885853 Hz, FE25 457.613007 Hz) of SP10_NEW_E1=E2_NSM_DENSITY,
  step SP_10_MODAL_FREE, ODB 87a9036f…, FE manifest 035b274c…, every shape recorded as extracted;
- the same digest with CRLF and LF line ends; a changed file, damaged JSON / CSV, wrong or missing mode numbers,
  changed, non-finite or non-increasing frequencies, a foreign model / ODB / manifest / step refuse the view;
- the frequency diagnostic has 12 rows, the signed Δf = 100 (f_FE − f_EXP) / f_EXP, EXP11 → FE17 +0.98 %, EXP12 →
  FE18 +0.11 %, the close groups, and no MAC or confirmed pair anywhere;
- the Workspace match needs both SHA-256, the polymax_bravo set when one is chosen and the FE7–FE25 modes read.

Page / window:
- the three specimens switch; SP-10 shows the historical PRIORITY-1 table unchanged beside the PRIORITY-6 tables;
- without a local package the archived frequencies and FE SHAPES … LOCAL PACKAGE NOT LOADED are shown;
- matching sources, each SHA-256 different, a wrong modal set, a changed Workspace: the link follows at once and
  PHYSICAL_REGISTRATION_NOT_VERIFIED is always shown; the historical banner stays NOT VERIFIED;
- opening the page starts no process and reads no FE package (only small files under docs/).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from services import research_results_reader as rr  # noqa: E402
from services import sp10_fe_research as sf  # noqa: E402
from new_gui import research_results_model as rm  # noqa: E402

PACKAGE, TABLE = (sf.ARCHIVE_FILES[k][0] for k in ("PACKAGE", "FE_VS_DAT"))


def experimental():
    return [(r.exp_no, r.f_exp_hz) for r in rr.load_snapshot().matching["SP-10"]]


def workspace_context(results, set_names=("polymax_bravo", "polymax-bravo"), records=12, step=sf.STEP, modes=None):
    return {"modal_set": None if set_names is None else {"names": set_names, "records": records},
            "fe_modes": modes if modes is not None else tuple((m.number, m.frequency_hz) for m in results.fe_modes),
            "fe_step": step}


class ArchiveTests(unittest.TestCase):
    """The records are copied to a temporary root; a changed copy gets its own digest pinned, so the structural checks
    behind the SHA-256 are reached."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        for relative in (PACKAGE, TABLE):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / relative).read_bytes().replace(b"\r\n", b"\n"))
        self.record = json.loads((self.root / PACKAGE).read_text(encoding="utf-8"))

    @contextlib.contextmanager
    def pinned(self, key: str, text: str):
        """Write ``text`` as the archived file ``key`` and pin its digest (a test of the checks behind the SHA); the
        archived copy is restored afterwards."""
        relative, _sha, commit = sf.ARCHIVE_FILES[key]
        path = self.root / relative
        original = path.read_bytes()
        path.write_text(text, encoding="utf-8", newline="\n")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        try:
            with mock.patch.dict(sf.ARCHIVE_FILES, {key: (relative, digest, commit)}):
                yield
        finally:
            path.write_bytes(original)

    def refused_record(self, change, reason: str):
        record = json.loads(json.dumps(self.record))
        change(record)
        with self.pinned("PACKAGE", json.dumps(record)), self.assertRaises(sf.Sp10ResearchRefused) as caught:
            sf.load_results(self.root)
        self.assertIn(reason, str(caught.exception))

    def test_the_19_fe_modes_and_the_identity(self):
        results = sf.load_results(self.root)
        self.assertEqual([m.number for m in results.fe_modes], list(range(7, 26)))
        self.assertAlmostEqual(results.fe_modes[0].frequency_hz, 23.885853, places=5)
        self.assertAlmostEqual(results.fe_modes[-1].frequency_hz, 457.613007, places=5)
        self.assertEqual((results.model, results.step, results.nodes),
                         ("SP10_NEW_E1=E2_NSM_DENSITY", "SP_10_MODAL_FREE", 1667491))
        self.assertEqual(results.odb_sha256, "87a9036fb5dc314e14a1fcb0d9ef4e0175d80bc6dfb05ceeea926d1ae767302c")
        self.assertEqual(results.fe_manifest_sha256,
                         "035b274c43fb8b7143bceb4dec99fdb2926a0f094cdafe1a0355faa45d8b1542")
        self.assertTrue(all(m.shape_file == f"mode_{m.number:04d}.csv" and len(m.shape_sha256) == 64
                            for m in results.fe_modes))
        self.assertEqual([m.number for m in results.fe_modes if m.added], list(range(16, 26)))
        self.assertGreater(results.frequency(15), 220.0)  # FE15 is 220.044 Hz: "added" is FE16–FE25, not "> 220 Hz"
        self.assertFalse(results.fe_modes[8].added)

    def test_the_same_digest_with_crlf_and_lf(self):
        for relative in (PACKAGE, TABLE):
            path = self.root / relative
            path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(len(sf.load_results(self.root).fe_modes), 19)

    def test_a_changed_or_missing_file_is_refused(self):
        path = self.root / TABLE
        path.write_bytes(path.read_bytes().replace(b"23.886,", b"23.887,", 1))
        with self.assertRaises(sf.Sp10ResearchRefused) as caught:
            sf.load_results(self.root)
        self.assertIn("is not the archived", str(caught.exception))
        path.unlink()
        with self.assertRaisesRegex(sf.Sp10ResearchRefused, "is missing"):
            sf.load_results(self.root)

    def test_damaged_json_and_csv_are_refused(self):
        with self.pinned("PACKAGE", "{ not json"), self.assertRaisesRegex(sf.Sp10ResearchRefused, "not valid JSON"):
            sf.load_results(self.root)
        with self.pinned("FE_VS_DAT", "mode,odb_hz\n7,x\n"), self.assertRaisesRegex(sf.Sp10ResearchRefused,
                                                                                 "FE7–FE25 in order"):
            sf.load_results(self.root)
        text = (self.root / TABLE).read_text(encoding="utf-8").replace("23.885853", "24.5", 1)
        with self.pinned("FE_VS_DAT", text), self.assertRaisesRegex(sf.Sp10ResearchRefused, "disagree"):
            sf.load_results(self.root)

    def test_wrong_mode_numbers_are_refused(self):
        self.refused_record(lambda r: r["frequencies"].pop(), "not FE7–FE25")
        self.refused_record(lambda r: r["frequencies"][3].update(mode=7), "not FE7–FE25")

    def test_changed_frequencies_are_refused(self):
        self.refused_record(lambda r: r["frequencies"][0].update(odb_eigfreq_hz=25.0), "differ")
        self.refused_record(lambda r: (r["frequencies"][0].update(odb_eigfreq_hz=float("nan"))), "finite positive")
        self.refused_record(lambda r: (r["frequencies"][0].update(odb_eigfreq_hz=-1.0)), "finite positive")
        self.refused_record(lambda r: r["frequencies"][0].update(equal_to_dat=False), "does not equal the .dat")

        def swap(r):  # FE8 and FE9 exchanged in both tables: not increasing
            a, b = r["frequencies"][1], r["frequencies"][2]
            a["odb_eigfreq_hz"], b["odb_eigfreq_hz"] = b["odb_eigfreq_hz"], a["odb_eigfreq_hz"]
            a["dat_step2_hz"], b["dat_step2_hz"] = b["dat_step2_hz"], a["dat_step2_hz"]
            h = {x["mode"]: x for x in r["odb_history_vs_dat"]}
            h[8]["odb_eigfreq_hz"], h[9]["odb_eigfreq_hz"] = h[9]["odb_eigfreq_hz"], h[8]["odb_eigfreq_hz"]
        self.refused_record(swap, "not increasing")

    def test_a_foreign_identity_is_refused(self):
        self.refused_record(lambda r: r["source"].update(job="SP10newmash"), "is not SP10_NEW_E1=E2_NSM_DENSITY")
        self.refused_record(lambda r: r["source"].update(odb_sha256="0" * 64), "ODB SHA-256")
        self.refused_record(lambda r: r["identity"].update(manifest_sha256="1" * 64), "FE manifest SHA-256")
        self.refused_record(lambda r: r["extraction"].update(step="Modal_FreeFree"), "modal step")
        self.refused_record(lambda r: r["identity"]["files"].pop("mode_0017.csv"), "FE17: no extracted shape")
        self.refused_record(lambda r: r.update(result="REFUSED"), "not a passed verification")


class DiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = sf.load_results()
        cls.rows = sf.frequency_diagnostic(cls.results, experimental())

    def test_twelve_rows_with_the_signed_error(self):
        self.assertEqual([r.exp_no for r in self.rows], list(range(1, 13)))
        for r in self.rows:
            self.assertAlmostEqual(r.nearest.df_percent, 100 * (r.nearest.frequency_hz - r.f_exp_hz) / r.f_exp_hz)
            self.assertLessEqual(abs(r.nearest.df_percent), abs(r.second.df_percent))
        self.assertLess(self.rows[0].nearest.df_percent, 0)  # EXP1 26.50 Hz above FE7 23.89 Hz: FE lower, negative
        self.assertGreater(self.rows[1].nearest.df_percent, 0)

    def test_exp11_and_exp12(self):
        e11, e12 = self.rows[10], self.rows[11]
        self.assertEqual((e11.f_exp_hz, e11.nearest.fe), (262.4545, 17))
        self.assertAlmostEqual(e11.nearest.frequency_hz, 265.0355, places=4)
        self.assertEqual(f"{e11.nearest.df_percent:+.2f}", "+0.98")
        self.assertEqual((e12.f_exp_hz, e12.nearest.fe), (266.8519, 18))
        self.assertAlmostEqual(e12.nearest.frequency_hz, 267.1444, places=4)
        self.assertEqual(f"{e12.nearest.df_percent:+.2f}", "+0.11")
        self.assertTrue(e11.nearest_in_added_range and e12.nearest_in_added_range)

    def test_the_nearest_fe_of_every_row(self):
        self.assertEqual([r.nearest.fe for r in self.rows], [7, 8, 9, 11, 11, 12, 13, 14, 15, 16, 17, 18])
        self.assertEqual([r.exp_no for r in self.rows if r.group],
                         [4, 5, 7, 8, 11, 12])

    def test_no_mac_and_no_confirmed_pair(self):
        for r in self.rows:
            self.assertEqual(r.status, sf.PROXIMITY_ONLY)
        self.assertFalse(any(hasattr(r, name) for r in self.rows for name in ("mac", "pair", "assigned")))
        text = " ".join(" ".join(row) for row in rm.sp10_diagnostic_rows(self.rows))
        self.assertNotIn("MATCH_CONFIRMED", text)
        self.assertNotIn("MAC", text.replace("NOT A CONFIRMED MODE PAIR", ""))
        self.assertEqual(text.count(sf.PROXIMITY_ONLY), 12)

    def test_the_experimental_records_must_be_exp1_to_exp12(self):
        with self.assertRaises(sf.Sp10ResearchRefused):
            sf.frequency_diagnostic(self.results, experimental()[:11])
        with self.assertRaises(sf.Sp10ResearchRefused):
            sf.frequency_diagnostic(self.results, [(n, -hz) for n, hz in experimental()])


class WorkspaceMatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = sf.load_results()

    def match(self, exp=sf.EXPERIMENT_SHA256, fe=sf.FE_MANIFEST_SHA256, **context):
        c = workspace_context(self.results, **context)
        return sf.workspace_match(self.results, {"sha256": exp} if exp else None, {"sha256": fe} if fe else None,
                                  modal_set=c["modal_set"], fe_modes=c["fe_modes"], fe_step=c["fe_step"])

    def test_both_sha256_and_the_set_match(self):
        m = self.match()
        self.assertTrue(m.matched)
        self.assertEqual(m.headline, sf.MATCH)
        self.assertEqual(m.registration, "PHYSICAL_REGISTRATION_NOT_VERIFIED")
        self.assertTrue(m.package_loaded)
        self.assertTrue(m.package_line.startswith(sf.PACKAGE_LOADED))

    def test_each_sha256_mismatch_is_named(self):
        m = self.match(exp="5" * 64)
        self.assertFalse(m.matched)
        self.assertIn("the experimental file read in the Workspace is 555555555555…", m.headline)
        self.assertNotIn("FE manifest read", m.headline)
        m = self.match(fe="4" * 64)
        self.assertFalse(m.matched)
        self.assertIn("the FE manifest read in the Workspace is 444444444444…", m.headline)
        self.assertNotIn("experimental file read", m.headline)
        self.assertTrue(m.package_line.startswith(sf.PACKAGE_NOT_LOADED))

    def test_nothing_read(self):
        m = self.match(exp=None, fe=None, set_names=None, modes=(), step=None)
        self.assertFalse(m.matched)
        self.assertIn("is none", m.headline)
        self.assertTrue(m.package_line.startswith(sf.PACKAGE_NOT_LOADED))

    def test_the_modal_set(self):
        m = self.match(set_names=None)  # none chosen: the files match, the set is not claimed
        self.assertTrue(m.matched)
        self.assertIn("its identity with polymax_bravo is not claimed", " ".join(m.lines))
        m = self.match(set_names=("Processing", ""), records=15)
        self.assertFalse(m.matched)
        self.assertIn("the modal set chosen (Processing, 15 records) is not polymax_bravo", m.headline)
        self.assertFalse(self.match(records=11).matched)

    def test_the_fe_modes_read_must_be_the_archive(self):
        modes = tuple((m.number, m.frequency_hz) for m in self.results.fe_modes)
        self.assertFalse(self.match(modes=modes[:-1]).matched)
        self.assertFalse(self.match(modes=((7, 30.0),) + modes[1:]).matched)
        self.assertFalse(self.match(step="Modal_FreeFree").matched)


try:
    from PySide6.QtWidgets import QApplication, QLabel  # noqa: F401
    HAVE_QT = True
except ImportError:  # pragma: no cover - depends on the environment
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT or os.environ.get("NEW_GUI_REQUIRE_QT") == "1", "PySide6 is not installed")
class PageTests(unittest.TestCase):
    def setUp(self):
        from new_gui import window as wm

        self.wm = wm
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        patch = mock.patch.dict(os.environ, {"LOCALAPPDATA": directory.name})
        patch.start()
        self.addCleanup(patch.stop)
        self.app = QApplication.instance() or wm.create_application([])
        self.window = wm.MainWindow(ask_path=lambda kind, start: "")
        self.window.resize(1366, 768)
        self.window.show()
        self.addCleanup(self.window.close)
        self.page = self.window.research

    def texts(self) -> str:
        return " ".join(w.text() for w in self.page.findChildren(QLabel) if w.isVisibleTo(self.window))

    def test_nothing_archived_is_shown_at_start_up(self):
        texts = " ".join(w.text() for w in self.page.findChildren(QLabel))  # hidden labels included
        for word in ("SP-10", "Updated SP-10", "PHYSICAL_REGISTRATION", "FREQUENCY_PROXIMITY", "LOCAL PACKAGE",
                     "DATA SOURCES"):
            self.assertNotIn(word, texts)
        self.assertIsNone(self.page.sp10)

    def test_opening_reads_no_fe_package_and_starts_nothing(self):
        read = []
        original = Path.read_bytes

        def tracked(path):
            read.append(Path(path).resolve())
            return original(path)

        with mock.patch("subprocess.Popen") as popen, mock.patch("subprocess.run") as run, \
                mock.patch.object(Path, "read_bytes", autospec=True, side_effect=tracked), \
                mock.patch("services.local_fe_preview.preview_fe_package") as preview:
            self.window.nav.button(self.wm.RESEARCH_PAGE).click()
            for key in ("SP-10", "SP-13", "PLATE", "SP-10"):
                self.page.set_specimen(key)
                self.app.processEvents()
            popen.assert_not_called()
            run.assert_not_called()
            preview.assert_not_called()
        docs = (ROOT / "docs").resolve()
        self.assertTrue(read)
        self.assertTrue(all(docs in p.parents for p in read), read)
        self.assertLessEqual(max(p.stat().st_size for p in read), 2_000_000)

    def test_three_specimens_and_the_two_sp10_groups(self):
        self.window.show_page(self.wm.RESEARCH_PAGE)
        historical = rm.matching_rows(self.page.snapshot, "SP-10")
        for key, rows in (("PLATE", 11), ("SP-13", 12), ("SP-10", 12)):
            self.page.set_specimen(key)
            self.app.processEvents()
            self.assertEqual(self.page.tables["matching"].rowCount(), rows, key)
            self.assertEqual(self.page.sp10_card.isVisibleTo(self.window), key == "SP-10", key)
        table = self.page.tables["matching"]
        shown = tuple(tuple(table.item(r, c).text() for c in range(table.columnCount())) for r in range(12))
        self.assertEqual(shown, historical)  # the historical table, unchanged
        self.assertEqual({row[8] for row in shown}, {"FE_SHAPES_UNAVAILABLE"})
        self.assertEqual(self.page.tables["sp10_fe"].rowCount(), 19)
        self.assertEqual(self.page.tables["sp10_fe"].item(18, 0).text(), "FE25")
        self.assertEqual(self.page.tables["sp10_fe"].item(18, 1).text(), "457.6130")
        diagnostic = self.page.tables["sp10_diagnostic"]
        self.assertEqual(diagnostic.rowCount(), 12)
        self.assertEqual([diagnostic.item(10, c).text() for c in range(5)],
                         ["EXP11", "262.4545", "FE17", "265.0355", "+0.98"])
        self.assertEqual([diagnostic.item(11, c).text() for c in range(5)],
                         ["EXP12", "266.8519", "FE18", "267.1444", "+0.11"])
        texts = self.texts()
        for expected in (rm.SP10_HISTORICAL_HEADING, rm.SP10_TITLE, sf.PROXIMITY_ONLY, sf.REGISTRATION_STATUS,
                         "MAC NOT_AVAILABLE — FE shapes not extracted", rm.SP10_MAC_NOTE,
                         "not the current state of SP-10", "FE16–FE25"):
            self.assertIn(expected, texts)

    def test_without_a_local_package(self):
        self.window.show_page(self.wm.RESEARCH_PAGE)
        self.page.set_specimen("SP-10")
        self.app.processEvents()
        self.assertTrue(self.page.sp10_package.text().startswith(sf.PACKAGE_NOT_LOADED))
        self.assertTrue(self.page.sp10_link.text().startswith(sf.NO_MATCH))
        self.assertEqual(self.page.tables["sp10_fe"].rowCount(), 19)  # the archived frequencies all the same

    def test_the_link_follows_the_workspace(self):
        self.window.show_page(self.wm.RESEARCH_PAGE)
        self.page.set_specimen("SP-10")
        results = self.page.sp10
        exp, fe = {"sha256": sf.EXPERIMENT_SHA256}, {"sha256": sf.FE_MANIFEST_SHA256}
        self.page.set_workspace(exp, fe, workspace_context(results))
        self.assertEqual(self.page.sp10_link.text(), sf.MATCH)
        self.assertEqual(self.page.sp10_registration.text(), sf.REGISTRATION_STATUS)
        self.assertTrue(self.page.sp10_registration.isVisibleTo(self.window))
        self.assertTrue(self.page.sp10_package.text().startswith(sf.PACKAGE_LOADED))
        self.assertTrue(self.page.banner.text().startswith(rr.NOT_VERIFIED_BANNER))  # the historical banner: unchanged
        for args, reason in (((exp, {"sha256": "4" * 64}, workspace_context(results)), "FE manifest read"),
                             (({"sha256": "5" * 64}, fe, workspace_context(results)), "experimental file read"),
                             ((exp, fe, workspace_context(results, set_names=("Processing", ""), records=15)),
                              "modal set chosen"),
                             ((exp, None, workspace_context(results, modes=(), step=None)), "is none")):
            self.page.set_workspace(*args)
            self.assertTrue(self.page.sp10_link.text().startswith(sf.NO_MATCH), reason)
            self.assertIn(reason, self.page.sp10_link.text())
            self.page.set_workspace(exp, fe, workspace_context(results))
            self.assertEqual(self.page.sp10_link.text(), sf.MATCH)

    def test_the_window_passes_the_set_and_the_fe_modes(self):
        fe = SimpleNamespace(modes=(SimpleNamespace(number=7, frequency_hz=23.885853),), step_name=sf.STEP)
        sets = (SimpleNamespace(display_name="Processing", key="", records=(1,) * 15),
                SimpleNamespace(display_name="polymax_bravo", key="polymax-bravo", records=(1,) * 12))
        context = self.window._research_context(fe, SimpleNamespace(sets=sets), 1)
        self.assertEqual(context, {"modal_set": {"names": ("polymax_bravo", "polymax-bravo"), "records": 12},
                                   "fe_modes": ((7, 23.885853),), "fe_step": sf.STEP})
        self.assertIsNone(self.window._research_context(None, None, None)["modal_set"])
        self.assertIsNone(self.window._research_context(fe, SimpleNamespace(sets=sets), 5)["modal_set"])
        with mock.patch.object(self.page, "set_workspace", wraps=self.page.set_workspace) as spy:
            self.window.refresh()  # nothing read: no identity, no set, no FE modes
        exp_identity, fe_identity, context = spy.call_args.args
        self.assertEqual((exp_identity, fe_identity), (None, None))
        self.assertEqual(context, {"modal_set": None, "fe_modes": (), "fe_step": None})


if __name__ == "__main__":
    unittest.main()
