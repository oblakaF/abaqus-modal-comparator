"""APP-CATALOG.1: specimen passports on Home, read from the accepted specimen catalogue (no process, no Abaqus).

The service ``services.specimen_catalog_view`` reads ``docs/auto_id/specimen_catalog.json`` and only words its values.
These tests use the real catalogue, read-only, and check:

- its 14 records are read, and SP-14 is absent;
- the passports of SP-02, SP-13, SP-12 and SP-15;
- the scientific distinctions:
  - a recorded value against a value the spec records as calculated;
  - nominal against recorded thickness;
  - template FE constants against material properties;
  - raw FRF against governed fitted modes;
  - an existing ODB against a governed FE model;
  - a historical against a physical registration;
- unknown values are shown as unknown, never as zero, and nothing missing is computed;
- a missing or damaged catalogue gives a warning while the rest of Home keeps working;
- on the real main window, choosing a specimen changes no input, result, MAC, analysis state or input file registry,
  and the Home / Expert switch keeps the passport and the analysis data.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from services import local_input_registry as registry  # noqa: E402
from services import specimen_catalog_view as V  # noqa: E402
import home_dashboard as H  # noqa: E402
from test_app_ui1_home import _Home  # noqa: E402

CATALOGUE = ROOT / "docs" / "auto_id" / "specimen_catalog.json"
EXPECTED_IDS = tuple(f"SP-{n:02d}" for n in range(1, 14)) + ("SP-15",)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sections(specimen_id: str, catalogue=None):
    catalogue = catalogue or V.load_catalogue()
    return {section.title: section for section in V.passport_sections(catalogue.entry(specimen_id), catalogue)}


def rows(section) -> dict:
    """caption -> text; repeated captions (modal sets, FE files) are joined."""
    found = {}
    for caption, text in section.rows:
        found[caption] = f"{found[caption]} | {text}" if caption in found else text
    return found


def all_texts(specimen_id: str) -> str:
    return "\n".join(f"{caption}: {text}" for section in sections(specimen_id).values()
                     for caption, text in section.rows)


def sandwich(**overrides) -> dict:
    entry = {"specimen_id": "SP-90", "type": "sandwich", "family_id": "test",
             "geometry": {"plan_mm": [500, 500], "total_thickness_mm": 3.0, "face_top_mm": 0.5,
                          "face_bottom_mm": 0.5, "core_thickness_mm": None},
             "mass": {"face_top_g": 100.0, "face_bottom_g": 100.0, "core_g": 50.0, "arithmetic_notes": []},
             "face_material": {"stock": "old", "weave": "plain", "designation": "T300", "nominal_thickness_mm": 0.45,
                               "constants": {"status": "ASSUMED/TEMPLATE", "values": {"E1_MPa": 52000}}},
             "core": {"material": "PLA", "topology": "honeycomb", "adhesive": "3M DP420",
                      "constants": {"status": "UNKNOWN", "values": None}},
             "experiments": [], "fe_assets": {"store": [], "governed_forward_model": None, "status": "none"},
             "registration": {"legacy": None, "physical": None, "status": "NONE"}, "auto_id_status": []}
    entry.update(overrides)
    return entry


# ------------------------------------------------------------------------------------------------ the service

class CatalogueReadTests(unittest.TestCase):
    def test_all_14_real_records_are_read_and_every_passport_is_shown(self):
        catalogue = V.load_catalogue()
        self.assertEqual(catalogue.problem, "")
        self.assertEqual(catalogue.path, CATALOGUE)
        self.assertEqual(catalogue.ids, EXPECTED_IDS)
        self.assertEqual(catalogue.header["status"], "ACCEPTED")
        for specimen_id in catalogue.ids:
            built = V.passport_sections(catalogue.entry(specimen_id), catalogue)
            titles = [section.title for section in built]
            self.assertEqual(titles[:4], ["Identity and status", "Dimensions", "Materials", "Masses"], specimen_id)
            self.assertEqual(titles[-2:], ["FE data", "Origin of the data"], specimen_id)
            self.assertTrue(any(title.startswith("Experimental data") for title in titles), specimen_id)
            for section in built:
                for caption, text in section.rows:
                    self.assertIsInstance(text, str)
                    self.assertTrue(text.strip(), (specimen_id, section.title, caption))
                    self.assertNotIn("None", text, (specimen_id, section.title, caption))  # null is never printed

    def test_sp14_is_absent_and_not_created(self):
        catalogue = V.load_catalogue()
        self.assertNotIn("SP-14", catalogue.ids)
        self.assertIsNone(catalogue.entry("SP-14"))
        self.assertFalse(any("SP-14" in V.choice_text(entry) for entry in catalogue.specimens))
        self.assertEqual(len(catalogue.specimens), 14)

    def test_viewing_never_changes_the_catalogue_and_opens_no_named_file(self):
        before = (_sha(CATALOGUE), CATALOGUE.stat().st_mtime_ns)
        opened = []
        original = Path.read_text

        def recorded(path, *args, **kwargs):
            opened.append(Path(path))
            return original(path, *args, **kwargs)

        with mock.patch.object(Path, "read_text", recorded), mock.patch.object(Path, "write_text",
                                                                              side_effect=AssertionError("write")):
            catalogue = V.load_catalogue()
            for specimen_id in catalogue.ids:
                V.passport_sections(catalogue.entry(specimen_id), catalogue)
        self.assertEqual(opened, [CATALOGUE])  # the catalogue only: no spec, UNV, ODB or registration file
        self.assertEqual((_sha(CATALOGUE), CATALOGUE.stat().st_mtime_ns), before)


class ControlSpecimenTests(unittest.TestCase):
    def test_sp02_passport(self):
        passport = sections("SP-02")
        identity, geometry = rows(passport["Identity and status"]), rows(passport["Dimensions"])
        materials, masses = rows(passport["Materials"]), rows(passport["Masses"])
        fe = rows(passport["FE data"])
        self.assertEqual(identity["Specimen ID"], "SP-02")
        self.assertIn("sandwich", identity["Type"])
        self.assertTrue(geometry["Panel plan"].startswith("515 × 510 mm"))
        self.assertTrue(geometry["Total thickness"].startswith("2.9 mm"))
        self.assertTrue(geometry["Top face sheet"].startswith("0.45 mm"))
        self.assertTrue(geometry["Bottom face sheet"].startswith("0.45 mm"))
        self.assertEqual((materials["Core material"], materials["Core topology"]), ("PLA", "honeycomb"))
        self.assertEqual(materials["Adhesive"], "3M DP420")
        self.assertEqual((materials["Face material"], materials["Weave"]), ("T300", "plain"))
        self.assertEqual(masses["Finished panel"], "582.71 g (recorded in the spec)")
        self.assertEqual(masses["Adhesive, real"], V.NOT_RECORDED)  # null: unknown, not zero
        self.assertIn("ACCEPTED", fe["Physical registration"])
        self.assertIn("SP02/bravo-1-physical", fe["Physical registration"])
        self.assertIn("SP02_physical_registration.json", fe["Physical registration"])
        self.assertIn("historical", fe["Legacy registration"])
        self.assertIn("SP02_Modal_V02/carbon-property-set-v1", fe["Governed FE model"])
        fitted = [rows(s) for title, s in passport.items() if title.startswith("Experimental data ")
                  and "dataset 55" in rows(s)["Data"]]
        self.assertEqual(len(fitted), 1)
        self.assertIn("governed fixture set Bravo (1) (active fixture SP02/bravo-1-physical)", fitted[0]["Data"])

    def test_sp13_passport_keeps_the_two_series_apart(self):
        passport = sections("SP-13")
        geometry, materials = rows(passport["Dimensions"]), rows(passport["Materials"])
        masses, fe = rows(passport["Masses"]), rows(passport["FE data"])
        self.assertTrue(geometry["Panel plan"].startswith("510 × 520 mm"))
        self.assertTrue(geometry["Total thickness"].startswith("2.85 mm"))
        self.assertTrue(geometry["Top face sheet"].startswith("0.425 mm"))
        self.assertTrue(geometry["Bottom face sheet"].startswith("0.425 mm"))
        self.assertIn("not a measurement", geometry["Core plan"])  # the CAD core plan is not the specimen
        self.assertEqual((materials["Core material"], materials["Core topology"], materials["Adhesive"]),
                         ("PLA", "auxetic", "3M DP420"))
        self.assertEqual(masses["Finished, real"], "584.6 g (recorded in the spec as the real value)")
        self.assertEqual(masses["Finished, calculated"], "590.24 g (recorded in the spec as a calculated value)")
        self.assertNotIn("Finished panel", masses)
        self.assertIn("SP13_physical_registration.json", fe["Physical registration"])
        series = {title: rows(s) for title, s in passport.items() if title.startswith("Experimental data ")}
        self.assertEqual([title.split("session ")[1] for title in series], ["260909", "260909", "260910 a",
                                                                             "260910 a"])
        for title, found in series.items():
            text = " ".join(found.values())
            if title.endswith("260909"):
                self.assertNotIn("Best", text)  # the 260910 a set is never shown with 260909
                self.assertNotIn("SP13_a_", found["Source"])
            else:
                self.assertNotIn("Bravo", text)
                self.assertIn("SP13_a_", found["Source"])  # the 260910 a files
        best = [found for found in series.values() if "Modal set" in found and "Best" in found["Modal set"]]
        self.assertEqual(len(best), 1)
        self.assertIn("SP13/best-physical", best[0]["Data"])
        self.assertIn("Best: 12 modes", best[0]["Modal set"])
        frozen = [found for title, found in series.items() if title.endswith("260909") and "Modal set" in found]
        self.assertIn("FREQUENCY_ONLY", frozen[0]["Data"])

    def test_sp12_has_no_experiment(self):
        passport = sections("SP-12")
        self.assertEqual([title for title in passport if title.startswith("Experimental data")],
                         ["Experimental data"])
        self.assertEqual(rows(passport["Experimental data"])["Measurements"],
                         "No experiment is recorded for this specimen in the catalogue.")
        self.assertEqual(rows(passport["Masses"])["Plate"], "30.1 g (recorded)")
        self.assertEqual(rows(passport["FE data"])["Governed FE model"], "none recorded")

    def test_sp15_identity_is_ambiguous_and_nothing_comes_from_sp12(self):
        passport = sections("SP-15")
        identity, geometry = rows(passport["Identity and status"]), rows(passport["Dimensions"])
        masses, materials = rows(passport["Masses"]), rows(passport["Materials"])
        self.assertEqual(identity["Identity"], "AMBIGUOUS")
        for value in (geometry["Panel plan"], geometry["Plate thickness"], materials["Face material"],
                      materials["Face stock"], materials["Nominal face"]):
            self.assertEqual(value, V.UNKNOWN_TEXT)
        self.assertEqual(masses["Plate"], V.NOT_RECORDED)
        recorded = " ".join(list(geometry.values()) + list(masses.values()) + list(materials.values()))
        for sp12_value in ("310", "0.245", "30.1"):  # SP-12 values are not carried over
            self.assertNotIn(sp12_value, recorded)


class DistinctionTests(unittest.TestCase):
    def test_recorded_and_calculated_masses_are_told_apart(self):
        masses = rows(sections("SP-05")["Masses"])
        self.assertTrue(masses["Total, calculated"].endswith("(recorded in the spec as a calculated value)"))
        self.assertTrue(masses["Finished panel"].endswith("(recorded in the spec)"))
        self.assertTrue(masses["Adhesive, calculated"].endswith("(recorded in the spec as a calculated value)"))
        masses = rows(sections("SP-08")["Masses"])
        self.assertTrue(masses["Finished, real"].endswith("(recorded in the spec as the real value)"))
        self.assertTrue(masses["Finished panel"].endswith("(recorded in the spec)"))

    def test_missing_masses_and_thicknesses_are_never_computed(self):
        built = {s.title: rows(s) for s in V.passport_sections(sandwich())}
        masses, geometry = built["Masses"], built["Dimensions"]
        self.assertEqual(masses["Finished panel"], V.NOT_RECORDED)
        self.assertEqual(masses["Adhesive, real"], V.NOT_RECORDED)
        self.assertNotIn("Without adhesive", masses)
        self.assertEqual(geometry["Core thickness"], V.UNKNOWN_TEXT)
        text = " ".join(list(masses.values()) + list(geometry.values()))
        self.assertNotIn("250", text)  # faces + core is not summed
        self.assertNotIn("2.0", text)  # total - faces is not derived

    def test_unknown_is_never_shown_as_zero(self):
        entry = sandwich(geometry={"plan_mm": None, "total_thickness_mm": None, "face_top_mm": None,
                                   "face_bottom_mm": None, "core_thickness_mm": None},
                         mass={"face_top_g": None, "adhesive_real_g": None})
        built = {s.title: rows(s) for s in V.passport_sections(entry)}
        for key in ("Panel plan", "Total thickness", "Top face sheet", "Bottom face sheet", "Core thickness"):
            self.assertEqual(built["Dimensions"][key], V.UNKNOWN_TEXT)
        for key in ("Top face sheet", "Bottom face sheet", "Core", "Adhesive, real", "Finished panel"):
            self.assertEqual(built["Masses"][key], V.NOT_RECORDED)
        self.assertNotRegex(" ".join(built["Masses"].values()), r"\b0(\.0)? g\b")
        self.assertIn("Неизвестно", V.UNKNOWN_TEXT)

    def test_nominal_and_recorded_thickness_are_told_apart(self):
        passport = sections("SP-02")
        self.assertIn("nominal stock thickness, not a measurement", rows(passport["Materials"])["Nominal face"])
        self.assertIn("not a face-sheet thickness", rows(passport["Dimensions"])["Total thickness"])

    def test_template_constants_are_never_material_properties(self):
        for specimen_id in ("SP-02", "SP-13"):
            materials = rows(sections(specimen_id)["Materials"])
            for key in ("Face FE constants", "Core FE constants"):
                self.assertIn("ASSUMED/TEMPLATE", materials[key])
                self.assertIn("not measured or identified material properties", materials[key])
            text = all_texts(specimen_id)
            self.assertNotRegex(text, r"\b(52000|2580|4500)\b")  # no template value is shown as a property
            self.assertNotRegex(text, r"\d\s*(GPa|MPa)\b")
        self.assertIn("no constants are recorded", rows(sections("SP-04")["Materials"])["Face FE constants"])

    def test_raw_frf_and_governed_fitted_modes_are_told_apart(self):
        found = [rows(s) for title, s in sections("SP-15").items() if title.startswith("Experimental data ")]
        self.assertIn("not fitted modes", found[0]["Data"])
        self.assertIn("not governed", found[1]["Data"])
        raw = [rows(s) for title, s in sections("SP-02").items() if title.startswith("Experimental data ")][0]
        self.assertTrue(raw["Data"].startswith("raw FRF (dataset 58): measured response functions"))

    def test_an_existing_odb_is_not_a_governed_fe_model(self):
        fe = rows(sections("SP-15")["FE data"])
        self.assertEqual(fe["Governed FE model"], "none recorded")
        self.assertIn("ODB", fe["Outside the store"])
        self.assertEqual(fe["FE status"], "FE exists, not governed")
        self.assertIn("not a governed FE model", sections("SP-15")["FE data"].note)

    def test_historical_and_physical_registration_are_told_apart(self):
        fe = rows(sections("SP-13")["FE data"])
        self.assertIn("historical", fe["Legacy registration"])
        self.assertIn("SP13_frozen_registration.json", fe["Legacy registration"])
        self.assertIn("production-ready", fe["Physical registration"])
        self.assertEqual(rows(sections("SP-01")["FE data"])["Physical registration"], "none (NONE)")

    def test_catalogue_acceptance_is_not_specimen_validation(self):
        origin = sections("SP-15")["Origin of the data"]
        self.assertIn("does not mean that every specimen is scientifically validated", origin.note)
        identity = rows(sections("SP-02")["Identity and status"])
        self.assertEqual(identity["Identification status"], "NEEDS_GOVERNANCE")
        self.assertIn("production Auto-ID is not authorised", identity[""])


class DamagedCatalogueTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="catalog1_"))
        self.addCleanup(shutil.rmtree, self.folder, True)

    def load(self, content) -> V.CatalogueView:
        path = self.folder / "specimen_catalog.json"
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
        return V.load_catalogue(path)

    def test_a_missing_or_damaged_catalogue_gives_a_problem_and_no_specimen(self):
        good = {"schema": V.CATALOGUE_SCHEMA, "specimens": [{"specimen_id": "SP-01"}]}
        cases = {
            "not found": None,
            "not readable JSON": "{ broken",
            "not readable JSON ": b"\xff\xfe\x00broken",
            "not a specimen catalogue": {"schema": "other", "specimens": []},
            "not a specimen catalogue ": [1, 2],
            "lists no specimen": {"schema": V.CATALOGUE_SCHEMA, "specimens": []},
            "lists no specimen ": {"schema": V.CATALOGUE_SCHEMA, "specimens": "SP-01"},
            "has no specimen ID": {"schema": V.CATALOGUE_SCHEMA, "specimens": [{"type": "sandwich"}]},
            "has no specimen ID ": {"schema": V.CATALOGUE_SCHEMA, "specimens": ["SP-01"]},
            "twice": {"schema": V.CATALOGUE_SCHEMA, "specimens": [{"specimen_id": "SP-01"}] * 2},
        }
        for expected, content in cases.items():
            view = V.load_catalogue(self.folder / "absent.json") if content is None else self.load(content)
            self.assertIn(expected.strip(), view.problem, expected)
            self.assertEqual(view.specimens, ())
        with mock.patch.object(V, "CATALOGUE_READ_LIMIT", 10):
            self.assertIn("too large", self.load(good).problem)
        self.assertEqual(self.load(good).problem, "")

    def test_a_damaged_record_is_shown_with_unknown_values(self):
        entry = {"specimen_id": "SP-99", "type": "sandwich", "geometry": "broken", "mass": [1, 2], "core": "x",
                 "experiments": "none", "fe_assets": None, "registration": 5, "identity": None,
                 "face_material": {"constants": "x"}}
        built = {s.title: rows(s) for s in V.passport_sections(entry)}
        self.assertEqual(built["Dimensions"]["Panel plan"], V.UNKNOWN_TEXT)
        self.assertEqual(built["Masses"]["Core"], V.NOT_RECORDED)
        self.assertEqual(built["Experimental data"]["Measurements"],
                         "No experiment is recorded for this specimen in the catalogue.")
        self.assertEqual(built["FE data"]["Governed FE model"], "none recorded")


# ------------------------------------------------------------------------------------------------ Home

class HomeCatalogueTests(_Home):
    def choose(self, home, specimen_id):
        text = next(value for value in home.specimen_combo.cget("values") if value.startswith(specimen_id + " "))
        home.specimen_choice.set(text)
        home.specimen_combo.event_generate("<<ComboboxSelected>>")
        self.root.update()

    def passport_texts(self, home) -> list[str]:
        return [str(label.cget("text")) for label in home.passport.winfo_children()]

    def test_the_block_lists_the_14_specimens_and_shows_no_passport_until_one_is_chosen(self):
        _application, home = self.home()
        card = home.cards["catalogue"]
        titles = [str(child.cget("text")) for child in card.winfo_children() if child.winfo_class() == "TLabel"]
        self.assertIn("5  Specimen catalogue / Паспорт образца", titles)
        values = tuple(home.specimen_combo.cget("values"))
        self.assertEqual(tuple(value.split()[0] for value in values), EXPECTED_IDS)
        self.assertEqual(home.specimen_choice.get(), "")
        self.assertEqual(home.passport.winfo_children(), [])
        self.assertIn("14 specimens in the catalogue (ACCEPTED). Choose a specimen",
                      str(home.catalogue_message.cget("text")))
        self.assertEqual(str(home.specimen_combo.cget("state")), "readonly")

    def test_the_control_passports_are_shown_on_home(self):
        _application, home = self.home()
        expected = {
            "SP-02": ("515 × 510 mm (recorded)", "582.71 g (recorded in the spec)", "honeycomb",
                      "SP02/bravo-1-physical"),
            "SP-13": ("510 × 520 mm (recorded)", "584.6 g (recorded in the spec as the real value)", "auxetic",
                      "SP13/best-physical"),
            "SP-12": ("310 × 310 mm (recorded)", "No experiment is recorded for this specimen in the catalogue.",
                      "30.1 g (recorded)"),
            "SP-15": ("AMBIGUOUS", V.NOT_RECORDED, "none recorded"),
        }
        for specimen_id, needles in expected.items():
            self.choose(home, specimen_id)
            texts = self.passport_texts(home)
            self.assertIn("Identity and status", texts)
            self.assertIn(f"Passport of {specimen_id}, as recorded in specimen_catalog.json (read only).",
                          str(home.catalogue_message.cget("text")))
            joined = "\n".join(texts)
            for needle in needles:
                self.assertIn(needle, joined, specimen_id)
            self.assertNotIn("SP-14", joined if specimen_id != "SP-15" else "")
        self.assertTrue(all(label.winfo_exists() for label, _card in home._wrapped))  # old rows are released

    def test_choosing_a_specimen_changes_no_input_result_mac_or_analysis_state(self):
        application, home = self.home()
        self.established(application)
        home = self.refreshed(application)

        def state():
            return (application.abaqus_path.get(), application.experimental_path.get(),
                    application.experimental_modal_set_key.get(), application.experimental_modal_set_display.get(),
                    application.start_mode.get(), application.end_mode.get(), application.workspace_path.get(),
                    application.result, application.analysis_state, application.status.get(),
                    application.dirty_tracker.dirty, str(application.excel_button.cget("state")),
                    str(application.metric_pairs.cget("text")), str(application.metric_error.cget("text")),
                    self.texts(home.check_rows), str(home.verdict.cget("text")),
                    str(home.result_text.cget("text")), self.result_values(home))

        before = state()
        pairs, mac = application.result.pairs, application.result.mac_matrix.copy()
        with mock.patch.object(registry, "_read", side_effect=AssertionError("registry read")), \
                mock.patch.object(registry, "_write", side_effect=AssertionError("registry written")), \
                mock.patch.object(application, "_start", side_effect=AssertionError("analysis started")):
            for specimen_id in ("SP-02", "SP-13", "SP-12", "SP-15", "SP-05"):
                self.choose(home, specimen_id)
                home = self.refreshed(application)
                self.assertEqual(state(), before, specimen_id)
        self.assertIs(application.result, before[7])
        self.assertIs(application.result.pairs, pairs)
        self.assertTrue((application.result.mac_matrix == mac).all())

    def test_the_home_expert_switch_keeps_the_passport_and_the_analysis_data(self):
        application, home = self.home()
        self.established(application)
        self.choose(home, "SP-13")
        shown = self.passport_texts(home)
        before = (application.abaqus_path.get(), application.experimental_path.get(), application.result,
                  application.dirty_tracker.dirty)
        for view in (H.EXPERT, H.HOME, H.EXPERT, H.HOME):
            application._show_view(view)
            self.root.update()
        self.assertEqual(home.specimen_choice.get().split()[0], "SP-13")
        self.assertEqual(self.passport_texts(home), shown)
        self.assertEqual((application.abaqus_path.get(), application.experimental_path.get(), application.result,
                          application.dirty_tracker.dirty), before)

    def test_the_wheel_over_the_list_scrolls_home_and_keeps_the_choice(self):
        _application, home = self.home()
        self.choose(home, "SP-02")
        with mock.patch.object(home, "_wheel") as wheel:
            self.assertEqual(home._combo_wheel(object()), "break")
        wheel.assert_called_once()
        self.assertTrue(home.specimen_choice.get().startswith("SP-02 "))

    def test_a_missing_or_damaged_catalogue_is_a_warning_and_home_keeps_working(self):
        folder = Path(tempfile.mkdtemp(prefix="catalog1_home_"))
        self.addCleanup(shutil.rmtree, folder, True)
        damaged = folder / "specimen_catalog.json"
        damaged.write_text("{ not json", encoding="utf-8")
        for path, reason in ((damaged, "not readable JSON"), (folder / "absent.json", "was not found")):
            with mock.patch.object(V, "CATALOGUE_PATH", path):
                application, home = self.home()
            message = str(home.catalogue_message.cget("text"))
            self.assertIn("The specimen catalogue cannot be shown", message)
            self.assertIn(reason, message)
            self.assertIn("The rest of the program is not affected", message)
            self.assertEqual(str(home.specimen_combo.cget("state")), "disabled")
            self.assertEqual(tuple(home.specimen_combo.cget("values")), ())
            self.assertEqual(home.passport.winfo_children(), [])
            self.assertEqual(len(self.texts(home.check_rows)), 6)  # the four areas work as before
            self.established(application)
            home = self.refreshed(application)
            self.assertIn("Comparison complete", str(home.result_text.cget("text")))

    def test_a_long_passport_wraps_inside_home_at_window_sizes_and_scales(self):
        application, home = self.home()
        self.choose(home, "SP-13")
        self.root.deiconify()
        try:
            for size, scale in (("1920x1080", 100), ("1366x768", 110), ("1120x700", 125), ("1120x700", 80)):
                application._apply_ui_scale(scale, persist=False)
                self.root.geometry(size)
                deadline = time.monotonic() + 2.0
                while time.monotonic() < deadline:
                    self.root.update()
                    time.sleep(0.02)
                card = home.cards["catalogue"]
                for label in home.passport.winfo_children():
                    if label.winfo_ismapped():
                        right = label.winfo_rootx() + label.winfo_reqwidth()
                        self.assertLessEqual(right, card.winfo_rootx() + card.winfo_width() + 2,
                                             (size, scale, str(label.cget("text"))[:50]))
                home.canvas.yview_moveto(1.0)  # the passport is reached by scrolling Home
                self.root.update()
                self.assertGreater(float(home.canvas.yview()[0]), 0.0)
                home.canvas.yview_moveto(0.0)
        finally:
            application._apply_ui_scale(100, persist=False)
            self.root.withdraw()


if __name__ == "__main__":
    unittest.main()
